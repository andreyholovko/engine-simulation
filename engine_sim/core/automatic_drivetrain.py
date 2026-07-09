"""AutomaticDrivetrain: a torque-converter automatic (Aisin-class). Reuses
Drivetrain directly (subclassed, not reimplemented) for everything that's
identical to the manual gearbox -- tire/roller physics, gear-ratio
reflection, and the shift-ramp clutch-pack mechanic that opens the current
gear's pack and ramps in the next one. What's actually different:

  * The engine couples to the gearbox through a TorqueConverter instead of a
    plain dry clutch -- see core/torque_converter.py. That adds one more
    mass to the system: engine (pump) -> converter -> turbine/gearbox input
    -> clutch-pack (same ratio-reflected math the manual box already uses)
    -> wheel -> tire -> roller. The manual's two-mass sub-stepped loop
    becomes three; everything downstream of the turbine is unchanged.
  * Gear changes are decided every tick from throttle position and rpm (see
    _decide_shift()) instead of a driver's +/- button -- "user input" for
    this transmission is just the accelerator, exactly like a real
    automatic (see AutomaticTransmissionSpec's docstring for the shift map).
  * There's no neutral: an automatic in Drive at a stop just creeps, held
    back by the torque converter's own stall slip, not a driver-selected
    gear -- gear starts (and a reset returns) at 1, never 0.

The engine/turbine/clutch-pack coupling within one sub-step has a genuine
circular dependency (the clutch-pack's demand on the turbine depends on how
much torque the converter delivers it, and the converter's own lockup
coupling wants to know the turbine's load) -- resolved with a one-sub-step
lag on the clutch-pack's demand fed back into the converter, the same
"lagged by one step because this tick's true value depends on itself"
trick ECU.wastegate_duty() already uses for load_fraction. Sub-steps are
0.0002s, so the lag is negligible in practice.
"""

from typing import Optional

from engine_sim.core.clutch import couple_two_inertias
from engine_sim.core.drivetrain import RHO_AIR_KG_M3, Drivetrain, DrivetrainReading
from engine_sim.core.torque_converter import TorqueConverter
from engine_sim.specs import AutomaticTransmissionSpec, ClutchSpec, RollerSpec, TireSpec
from engine_sim.units import rad_s_to_rpm
from math import ceil, pi, sin


class AutomaticDrivetrain(Drivetrain):
    def __init__(
        self,
        transmission_spec: AutomaticTransmissionSpec,
        clutch_spec: ClutchSpec,
        tire_spec: TireSpec,
        roller_spec: RollerSpec,
    ):
        super().__init__(transmission_spec, clutch_spec, tire_spec, roller_spec)
        self.torque_converter = TorqueConverter(transmission_spec.torque_converter)
        self.omega_turbine = 0.0
        self._last_clutch_pack_torque_nm = 0.0
        self._shift_cooldown_remaining_s = 0.0
        # Set fresh every tick() call (see its own rev_limiter_rpm param) --
        # None until the first tick, same as a manual box that's never been
        # given a rev-limiter ceiling to respect.
        self._rev_limiter_rpm: Optional[float] = None
        # No neutral to creep-protect against -- see class docstring.
        self.gear = 1

    def reset(self) -> None:
        super().reset()
        self.omega_turbine = 0.0
        self._last_clutch_pack_torque_nm = 0.0
        self._shift_cooldown_remaining_s = 0.0
        self.gear = 1

    # Minimum clutch-pack engagement maintained throughout a shift, instead
    # of Drivetrain's plain 0 -> 1 ramp. Real automatics shift clutch-to-
    # clutch: the incoming gear's element starts taking load before the
    # outgoing one fully releases (an overlap), so torque never actually
    # interrupts the way a manual's single-clutch declutch-then-reclutch
    # does -- that overlap is what makes an automatic's shift *feel*
    # different from a paddle-shift sequential box, not just a longer
    # shift_time_s. Found directly: without this, the automatic's shifts
    # behaved identically in character to the manual gearbox's.
    _SHIFT_OVERLAP_FLOOR = 0.35

    def request_shift(self, delta: int) -> None:
        if self.is_shifting:
            return
        target = max(0, min(self.max_gear, self.gear + delta))
        if target == self.gear:
            return
        self.gear = target
        self._shift_total_s = max(self.transmission_spec.shift_time_s, 1e-3)
        self._shift_timer_s = self._shift_total_s
        self.clutch.engagement = self._SHIFT_OVERLAP_FLOOR

    # Minimum time after a shift completes before another one can be
    # decided ("shift busyness" protection, standard real TCU behavior).
    # Without it, the torque cut above makes rpm fall fast enough during a
    # shift that by the time it completes, rpm has already crossed back
    # over the downshift threshold for the gear just left -- triggering an
    # immediate shift right back, then another, hunting continuously
    # instead of settling. Found directly: 1<->2 alternating every ~0.5s
    # under sustained WOT.
    _SHIFT_COOLDOWN_S = 0.6

    def _advance_shift(self, dt: float) -> None:
        if self._shift_cooldown_remaining_s > 0.0:
            self._shift_cooldown_remaining_s = max(0.0, self._shift_cooldown_remaining_s - dt)
        if not self.is_shifting:
            return
        self._shift_timer_s = max(0.0, self._shift_timer_s - dt)
        progress = self._shift_progress()
        self.clutch.engagement = self._SHIFT_OVERLAP_FLOOR + (1.0 - self._SHIFT_OVERLAP_FLOOR) * progress
        if self._shift_timer_s <= 0.0:
            self._shift_cooldown_remaining_s = self._SHIFT_COOLDOWN_S

    def _shift_progress(self) -> float:
        """0 at the instant a shift is requested, 1 once it's complete."""
        if self._shift_total_s <= 0.0:
            return 1.0
        return min(1.0, 1.0 - self._shift_timer_s / self._shift_total_s)

    # Peak indicated-torque cut commanded during a shift (see ECU.tick()'s
    # torque_reduction_fraction) -- a smooth, continuous dip shaped by
    # sin(pi * progress): 0 at the instant the shift starts, peaking at the
    # shift's midpoint, back to 0 exactly as it completes. Deliberately not
    # a hold-then-release shape (an earlier version held near max cut
    # through most of the shift, releasing sharply near the end) -- that
    # produced a real torque *step* right as the clutch-pack overlap was
    # still ramping in, which read as harsh/jerky despite the clutch
    # engagement itself always having been smooth. A continuous curve with
    # zero slope at both endpoints matches how the clutch-pack overlap ramp
    # already feels: a gentle dip and recovery, not a cliff.
    _MAX_SHIFT_TORQUE_REDUCTION = 0.5

    def shift_torque_reduction_fraction(self) -> float:
        if not self.is_shifting:
            return 0.0
        return self._MAX_SHIFT_TORQUE_REDUCTION * sin(pi * self._shift_progress())

    # Real TCUs calibrate a transmission's own shift map against whatever
    # engine it's actually paired with -- AutomaticTransmissionSpec's
    # upshift_rpm_wot is one fixed number shared by every engine choice
    # here, though, so it isn't automatically safe for all of them. Found
    # directly: paired with the B58 (redline 6000, rev limiter cuts at
    # 5850 -- see ECU.rev_limiter_threshold_rpm), the spec's default 6200
    # upshift ceiling is ABOVE the rev limiter's own cut point, so WOT rpm
    # never reaches it at all -- the engine just bounces off the limiter in
    # 1st gear forever, never shifting. _effective_upshift_rpm() clamps the
    # spec's own ceiling to stay a real margin below whatever rev limiter
    # the current engine actually has (see tick()'s rev_limiter_rpm param),
    # so an upshift always has room to actually happen before the limiter
    # would otherwise cut in first.
    _UPSHIFT_REV_LIMITER_MARGIN_RPM = 400.0

    def _effective_upshift_rpm(self, throttle: float) -> float:
        spec: AutomaticTransmissionSpec = self.transmission_spec  # type: ignore[assignment]
        upshift_rpm = spec.upshift_rpm_light + (spec.upshift_rpm_wot - spec.upshift_rpm_light) * throttle
        if self._rev_limiter_rpm is not None:
            upshift_rpm = min(upshift_rpm, self._rev_limiter_rpm - self._UPSHIFT_REV_LIMITER_MARGIN_RPM)
        return upshift_rpm

    def _decide_shift(self, throttle: float, rpm: float) -> None:
        if self.is_shifting or self._shift_cooldown_remaining_s > 0.0:
            return
        spec: AutomaticTransmissionSpec = self.transmission_spec  # type: ignore[assignment]
        throttle = max(0.0, min(1.0, throttle))
        upshift_rpm = self._effective_upshift_rpm(throttle)
        downshift_rpm = spec.downshift_rpm_light + (spec.downshift_rpm_wot - spec.downshift_rpm_light) * throttle

        if downshift_rpm <= rpm <= upshift_rpm:
            return  # current gear is still a fine fit -- this band is the hysteresis, same as before

        target = self._ideal_gear(throttle)
        if target != self.gear:
            self.request_shift(target - self.gear)

    def _ideal_gear(self, throttle: float) -> int:
        """Lowest gear whose implied engine rpm (at the current wheel speed)
        doesn't exceed this throttle's upshift ceiling -- computed directly
        from wheel speed and each gear's own ratio, not stepped from the
        current gear one at a time. This is what makes a shift able to skip
        straight to the right gear -- a hard kickdown from a light-throttle
        cruise dropping several gears at once for real acceleration, or
        easing off skipping an upshift or two on the way to a taller
        cruising gear -- instead of always working through every gear in
        between like a driver rowing a manual shifter."""
        spec: AutomaticTransmissionSpec = self.transmission_spec  # type: ignore[assignment]
        upshift_rpm = self._effective_upshift_rpm(throttle)
        wheel_rpm = rad_s_to_rpm(self.omega_wheel)
        for gear in range(1, self.max_gear + 1):
            ratio = spec.gear_ratios[gear - 1] * spec.final_drive_ratio
            if wheel_rpm * ratio <= upshift_rpm:
                return gear
        return self.max_gear

    def _lockup_commanded(self, throttle: float) -> bool:
        spec: AutomaticTransmissionSpec = self.transmission_spec  # type: ignore[assignment]
        return self.gear >= spec.lockup_min_gear and throttle <= spec.lockup_max_throttle and not self.is_shifting

    def tick(
        self,
        dt: float,
        omega_engine_rad_s: float,
        engine_torque_nm: float,
        engine_inertia_kgm2: float,
        throttle: float = 0.0,
        rev_limiter_rpm: Optional[float] = None,
    ) -> DrivetrainReading:
        """Same signature as Drivetrain.tick() plus rev_limiter_rpm -- the
        current engine's actual rev-limiter cut point (see ECU.
        rev_limiter_threshold_rpm), used to keep the shift map's own
        upshift ceiling from ever exceeding it (see
        _effective_upshift_rpm()). Optional/defaults to None (no clamp) so
        any caller that doesn't know/care about a specific engine's limiter
        still works, same as before this param existed."""
        throttle = max(0.0, min(1.0, throttle))
        self._rev_limiter_rpm = rev_limiter_rpm
        self._decide_shift(throttle, rad_s_to_rpm(omega_engine_rad_s))
        self._advance_shift(dt)
        lockup_commanded = self._lockup_commanded(throttle)

        ratio = self._overall_ratio  # always > 0 -- automatics have no neutral (see class docstring)
        omega_engine = omega_engine_rad_s
        turbine_inertia = self.torque_converter.spec.turbine_inertia_kgm2
        roller_inertia_total = (
            self.roller_spec.inertia_kgm2 + self.roller_spec.vehicle_mass_kg * self.roller_spec.radius_m ** 2
        )

        n_substeps = max(1, ceil(dt / self._SUBSTEP_DT_S))
        sub_dt = dt / n_substeps

        tire_reading = None
        clutch_torque_nm = 0.0
        locked = False

        for _ in range(n_substeps):
            tire_reading = self.tire.tick(
                wheel_omega_rad_s=self.omega_wheel,
                road_omega_rad_s=self.omega_roller,
                road_radius_m=self.roller_spec.radius_m,
                normal_force_n=self._normal_force_n,
            )
            wheel_load_nm = tire_reading.longitudinal_force_n * self.tire.spec.radius_m

            omega_gearbox_in = ratio * self.omega_wheel
            reflected_inertia = self.tire.spec.inertia_kgm2 / (ratio * ratio)
            reflected_load_nm = wheel_load_nm / ratio

            pump_reaction_nm, turbine_drive_nm, _tc_reading = self.torque_converter.tick(
                sub_dt,
                omega_engine, engine_torque_nm, engine_inertia_kgm2,
                self.omega_turbine, self._last_clutch_pack_torque_nm, turbine_inertia,
                lockup_commanded,
            )

            clutch_torque_nm, locked = couple_two_inertias(
                self.omega_turbine, turbine_drive_nm, turbine_inertia,
                omega_gearbox_in, reflected_load_nm, reflected_inertia,
                self.clutch.capacity_nm(), dt=sub_dt,
            )
            self._last_clutch_pack_torque_nm = clutch_torque_nm

            wheel_drive_nm = clutch_torque_nm * ratio
            alpha_wheel = (wheel_drive_nm - wheel_load_nm) / self.tire.spec.inertia_kgm2
            alpha_turbine = (turbine_drive_nm - clutch_torque_nm) / turbine_inertia
            alpha_engine = (engine_torque_nm - pump_reaction_nm) / engine_inertia_kgm2

            self._integrate_wheel(alpha_wheel, sub_dt)
            self.omega_turbine = max(0.0, self.omega_turbine + alpha_turbine * sub_dt)
            omega_engine = max(0.0, omega_engine + alpha_engine * sub_dt)

            roller_drive_nm = tire_reading.longitudinal_force_n * self.roller_spec.radius_m
            vehicle_speed_mps = self.omega_roller * self.roller_spec.radius_m
            aero_drag_n = (
                0.5 * RHO_AIR_KG_M3 * self.roller_spec.drag_coefficient
                * self.roller_spec.frontal_area_m2 * vehicle_speed_mps * vehicle_speed_mps
            )
            rolling_nm = self.roller_spec.parasitic_torque_nm if self.omega_roller > 1e-6 else 0.0
            parasitic_nm = rolling_nm + aero_drag_n * self.roller_spec.radius_m
            alpha_roller = (roller_drive_nm - parasitic_nm) / roller_inertia_total
            self.omega_roller = max(0.0, self.omega_roller + alpha_roller * sub_dt)

        wheel_rpm = rad_s_to_rpm(self.omega_wheel)
        vehicle_speed_mps = self.omega_roller * self.roller_spec.radius_m
        vehicle_speed_kmh = vehicle_speed_mps * 3.6
        wheel_power_w = tire_reading.longitudinal_force_n * vehicle_speed_mps
        # See Drivetrain.tick()'s docstring on this same computation -- a
        # real dyno's "wheel torque" is wheel power divided by ENGINE rpm,
        # not force-at-the-roller times roller radius (which would include
        # this gear's own torque multiplication, badly inflating it).
        wheel_torque_nm = wheel_power_w / max(omega_engine, 1.0)

        return DrivetrainReading(
            gear=self.gear,
            shifting=self.is_shifting,
            clutch_engagement=self.clutch.engagement,
            clutch_locked=locked,
            clutch_torque_nm=clutch_torque_nm,
            engine_omega_rad_s=omega_engine,
            wheel_rpm=wheel_rpm,
            vehicle_speed_kmh=vehicle_speed_kmh,
            slip_ratio=tire_reading.slip_ratio,
            tire_force_n=tire_reading.longitudinal_force_n,
            tire_mu=tire_reading.mu,
            wheel_torque_nm=wheel_torque_nm,
            wheel_power_w=wheel_power_w,
        )
