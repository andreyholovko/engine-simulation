"""Drivetrain: the chassis-dyno load path from the clutch through a manual
gearbox to a tire slipping against the dyno's roller. Mirrors how ECU owns
Engine+Turbo: this owns Clutch+Tire+the wheel/roller state and is the only
thing that advances them together each tick. In neutral it deliberately
leaves the engine's own rotational state alone -- there's no path to it at
all, so the caller (see ChassisDynoLoop in core/dyno.py) integrates it
exactly like a crank dyno's idle/coast behavior, same as every other load
model here. In gear, this class integrates the engine's speed itself too
(see the sub-stepping note below) and hands the result straight back.

Gear shifting has no clutch pedal (by design -- see the '+'/'-' shift
buttons this drives): requesting a shift swaps the ratio immediately and
forces the clutch open, then ramps engagement 0 -> 1 over
TransmissionSpec.shift_time_s, the auto-clutch sequence a sequential
paddle-shift gearbox actually performs. The same two-mass lock/slip physics
that produces this ramp's torque interruption also produces a clutch launch
from a dead stop for free -- see couple_two_inertias's docstring (core/
clutch.py) -- there's nothing launch-specific in this file.

Reflecting the wheel's inertia and the tire's reaction torque through the
gear ratio to the clutch's own speed frame uses the standard results for an
ideal (massless, lossless, no-internal-slip) gear reduction of ratio r
(input shaft turns r times per turn of the output):
    apparent inertia at input  = J_output / r^2   (kinetic energy match)
    apparent torque at input   = T_output / r     (power match)
A gearbox set very low (large r, e.g. 1st gear) makes the wheel's own rigid
inertia nearly invisible to the engine (J/r^2 shrinks fast) while still
multiplying torque delivered to the wheel by r -- which is exactly why 1st
gear both revs eagerly *and* breaks traction easiest, without needing two
different explanations.
"""

from dataclasses import dataclass
from math import ceil
from typing import Optional

from engine_sim.core.clutch import Clutch, couple_two_inertias
from engine_sim.core.tire import Tire
from engine_sim.specs import RollerSpec, TireSpec, TransmissionSpec, ClutchSpec
from engine_sim.units import rad_s_to_rpm

G = 9.81  # m/s^2
RHO_AIR_KG_M3 = 1.225


@dataclass
class DrivetrainReading:
    gear: int  # 0 = neutral
    shifting: bool
    clutch_engagement: float
    clutch_locked: bool
    clutch_torque_nm: float
    # The engine's own rotational speed *after* this tick, already advanced
    # by this class's own (sub-stepped) integration -- only set when a gear
    # is engaged. None in neutral: there's no path to the engine at all, so
    # the caller keeps owning/integrating it exactly as it always did (see
    # ChassisDynoLoop.tick()).
    engine_omega_rad_s: Optional[float]
    wheel_rpm: float
    vehicle_speed_kmh: float
    slip_ratio: float
    tire_force_n: float
    tire_mu: float
    # Torque/power actually delivered to the roller -- what a real chassis
    # dyno measures (it's derived from roller acceleration, not read off the
    # engine). This is NOT engine_torque_nm/power carried through unchanged:
    # clutch slip and tire slip both show up here as a real shortfall, the
    # same way they'd show up on an actual dyno graph -- see Drivetrain.tick().
    wheel_torque_nm: float
    wheel_power_w: float


class Drivetrain:
    def __init__(
        self,
        transmission_spec: TransmissionSpec,
        clutch_spec: ClutchSpec,
        tire_spec: TireSpec,
        roller_spec: RollerSpec,
    ):
        self.transmission_spec = transmission_spec
        self.clutch = Clutch(clutch_spec)
        self.tire = Tire(tire_spec)
        self.roller_spec = roller_spec

        self.gear = 0  # start in neutral -- no unrequested creep on a fresh session
        self.omega_wheel = 0.0
        self.omega_roller = 0.0

        self._shift_timer_s = 0.0
        self._shift_total_s = 0.0

    @property
    def max_gear(self) -> int:
        return len(self.transmission_spec.gear_ratios)

    @property
    def is_shifting(self) -> bool:
        return self._shift_timer_s > 0.0

    def shift_torque_reduction_fraction(self) -> float:
        """0-1: how much the ECU should cut indicated torque this tick for
        shift management (see ECU.tick()'s own docstring). The manual
        gearbox never asks for this -- a real driver-operated clutch
        already handles the torque interruption themselves; only
        AutomaticDrivetrain overrides this."""
        return 0.0

    def reset(self) -> None:
        """Back to neutral, stationary, clutch fully engaged -- what a fresh
        session (or a fresh recorded pull) starts from. Same "reset this
        component's own state" role as Turbo.reset()/DynoBrake.reset_pid();
        DynoSession.start_power_pull() calls this so resetting the engine to
        idle doesn't leave the wheel/roller at whatever speed -- and the
        clutch mid-ramp from whatever gear -- they had from before, which
        would read as the sim being broken (engine snaps to idle, wheel
        speed and gear don't move) rather than a real reset."""
        self.gear = 0
        self.omega_wheel = 0.0
        self.omega_roller = 0.0
        self.clutch.engagement = 1.0
        self._shift_timer_s = 0.0
        self._shift_total_s = 0.0

    @property
    def _overall_ratio(self) -> float:
        """input-shaft speed per unit wheel speed, current gear. 0 in neutral
        (no rigid connection at all -- not "a very tall ratio", genuinely
        disconnected)."""
        if self.gear == 0:
            return 0.0
        return self.transmission_spec.gear_ratios[self.gear - 1] * self.transmission_spec.final_drive_ratio

    def request_shift(self, delta: int) -> None:
        """delta=+1 upshift, -1 downshift, from the '+'/'-' shift buttons.
        Ignored while already mid-shift -- a real sequential 'box doesn't
        accept a second shift request until the current one's actuator
        cycle finishes, and queuing one up would need its own (currently
        undesigned) behavior rather than silently overwriting the ramp."""
        if self.is_shifting:
            return
        target = max(0, min(self.max_gear, self.gear + delta))
        if target == self.gear:
            return
        self.gear = target
        self._shift_total_s = max(self.transmission_spec.shift_time_s, 1e-3)
        self._shift_timer_s = self._shift_total_s
        self.clutch.engagement = 0.0

    def _advance_shift(self, dt: float) -> None:
        if not self.is_shifting:
            return
        self._shift_timer_s = max(0.0, self._shift_timer_s - dt)
        progress = 1.0 - self._shift_timer_s / self._shift_total_s
        self.clutch.engagement = min(1.0, progress)

    # The wheel/tire's own rotational inertia is small (a real wheel+tire,
    # not a whole car), but the torque reaching it through a low gear is
    # large (a gearbox multiplies torque by the same ratio it divides
    # speed) -- that combination is numerically stiff: explicit-Euler at a
    # normal ~100Hz outer tick overshoots and oscillates (verified directly:
    # a launch would swing the wheel's rpm wildly tick to tick instead of
    # climbing smoothly). The engine and roller sides are comparatively
    # gentle (much larger inertia), so rather than raising the whole sim's
    # tick rate, this loop alone sub-steps at a much finer interval,
    # re-resolving the tire and clutch forces every sub-step so it's
    # actually integrating the stiff system, not just spreading one stale
    # torque over smaller steps.
    _SUBSTEP_DT_S = 0.0002

    @property
    def _normal_force_n(self) -> float:
        """Static weight on the driven axle plus its share of aero
        downforce -- the tire's actual available grip grows with speed, not
        just a fixed fraction of curb weight (see RollerSpec.
        downforce_coefficient's own docstring on why this stays small at
        normal driving speeds and only really shows up on a drag-strip-
        length pull)."""
        static_n = self.roller_spec.vehicle_mass_kg * G * self.roller_spec.driven_axle_weight_fraction
        vehicle_speed_mps = self.omega_roller * self.roller_spec.radius_m
        downforce_n = (
            0.5 * RHO_AIR_KG_M3 * self.roller_spec.downforce_coefficient
            * self.roller_spec.frontal_area_m2 * vehicle_speed_mps * vehicle_speed_mps
        )
        return static_n + downforce_n * self.roller_spec.driven_axle_weight_fraction

    def _integrate_wheel(self, alpha_wheel: float, sub_dt: float) -> None:
        """Advances omega_wheel by alpha_wheel*sub_dt, clamped so it can
        never overshoot straight through the zero-slip crossing (wheel
        surface speed == roller surface speed) within one sub-step.

        Found necessary during development: the wheel's tiny inertia,
        combined with a tire force that flips sign right at that crossing,
        meant a full-magnitude sub-step could jump clean over the "near
        zero slip, near zero force" zone into meaningful slip the *other*
        direction -- which flips the force again next sub-step, then
        again, oscillating (verified directly: wheel speed cycling through
        the same few values every few sub-steps, tire force sign flipping
        each time) instead of settling. Same stiff-crossing problem
        couple_two_inertias's own dt-aware guard solves for the clutch,
        applied here to the wheel/tire's crossing instead -- the tire model
        has no equivalent two-mass lock/slip state to hook that guard into
        directly, so it's handled at the integration step instead. The
        roller barely moves within a single sub-step (far larger inertia),
        so it's treated as stationary for this check."""
        predicted_wheel = self.omega_wheel + alpha_wheel * sub_dt
        road_surface = self.omega_roller * self.roller_spec.radius_m
        current_gap = self.omega_wheel * self.tire.spec.radius_m - road_surface
        predicted_gap = predicted_wheel * self.tire.spec.radius_m - road_surface
        if current_gap != 0.0 and (predicted_gap > 0.0) != (current_gap > 0.0):
            self.omega_wheel = max(0.0, road_surface / self.tire.spec.radius_m)
        else:
            self.omega_wheel = max(0.0, predicted_wheel)

    def tick(
        self,
        dt: float,
        omega_engine_rad_s: float,
        engine_torque_nm: float,
        engine_inertia_kgm2: float,
        throttle: float = 0.0,
        rev_limiter_rpm: Optional[float] = None,
    ) -> DrivetrainReading:
        """throttle/rev_limiter_rpm are unused here -- the manual gearbox's
        driver-operated clutch doesn't need either -- but are part of the
        signature so ChassisDynoLoop can call either this or
        AutomaticDrivetrain.tick() identically; the automatic subclass
        overrides this and actually uses both (shift map + lockup
        conditions; rev_limiter_rpm keeps its own shift map's upshift
        ceiling from ever exceeding whatever engine it's actually paired
        with -- see AutomaticDrivetrain._effective_upshift_rpm())."""
        self._advance_shift(dt)

        ratio = self._overall_ratio
        omega_engine = omega_engine_rad_s
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
            # Positive under normal forward drive -- the torque the tire's
            # reaction demands the wheel give up, opposing the wheel's own spin.
            wheel_load_nm = tire_reading.longitudinal_force_n * self.tire.spec.radius_m

            if ratio == 0.0:
                # Neutral (or, transiently, a ratio of exactly 0.0 -- never a
                # real gear): no path to the engine at all. Wheel freewheels
                # under the tire's own reaction only; engine is the
                # caller's problem entirely (same as before this class
                # existed -- see ChassisDynoLoop.tick()).
                clutch_torque_nm = 0.0
                locked = False
                alpha_wheel = -wheel_load_nm / self.tire.spec.inertia_kgm2
            else:
                omega_gearbox_in = ratio * self.omega_wheel
                reflected_inertia = self.tire.spec.inertia_kgm2 / (ratio * ratio)
                reflected_load_nm = wheel_load_nm / ratio

                clutch_torque_nm, locked = couple_two_inertias(
                    omega_engine, engine_torque_nm, engine_inertia_kgm2,
                    omega_gearbox_in, reflected_load_nm, reflected_inertia,
                    self.clutch.capacity_nm(), dt=sub_dt,
                )
                wheel_drive_nm = clutch_torque_nm * ratio
                alpha_wheel = (wheel_drive_nm - wheel_load_nm) / self.tire.spec.inertia_kgm2
                alpha_engine = (engine_torque_nm - clutch_torque_nm) / engine_inertia_kgm2
                omega_engine = max(0.0, omega_engine + alpha_engine * sub_dt)

            self._integrate_wheel(alpha_wheel, sub_dt)

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

        # Power actually delivered to the roller: the tractive force the
        # tire is putting down times how fast the roller surface is
        # actually moving. Deliberately NOT engine_torque_nm/power carried
        # through -- a locked driveline at zero road speed (stalled launch)
        # correctly reads 0W here even at WOT, and heavy tire slip caps this
        # at whatever the grip-limited force can actually push the roller
        # with, exactly what a real chassis dyno's roller-acceleration-based
        # measurement would show.
        wheel_power_w = tire_reading.longitudinal_force_n * vehicle_speed_mps
        # "Wheel torque" on a real chassis dyno is NOT force-at-the-roller
        # times roller radius -- that number includes whatever the current
        # gear's ratio happens to multiply it by (over 13x in 1st gear here,
        # i.e. up to ~1800Nm even though the engine itself never makes more
        # than a few hundred). Real dyno software instead derives it from
        # the measured wheel *power* (which power conservation keeps in the
        # engine's own ballpark regardless of gear) divided by the ENGINE's
        # own rpm -- "what torque would the engine have to be making right
        # now to produce this much power at this rpm" -- which is why a
        # dyno graph's torque number always reads comparable to the engine's
        # spec sheet, never inflated by the gearbox. omega_engine here is
        # this tick's already-updated engine speed (or, in neutral, just the
        # value passed in -- wheel_power_w is ~0 there anyway).
        wheel_torque_nm = wheel_power_w / max(omega_engine, 1.0)

        return DrivetrainReading(
            gear=self.gear,
            shifting=self.is_shifting,
            clutch_engagement=self.clutch.engagement,
            clutch_locked=locked,
            clutch_torque_nm=clutch_torque_nm,
            engine_omega_rad_s=omega_engine if ratio != 0.0 else None,
            wheel_rpm=wheel_rpm,
            vehicle_speed_kmh=vehicle_speed_kmh,
            slip_ratio=tire_reading.slip_ratio,
            tire_force_n=tire_reading.longitudinal_force_n,
            tire_mu=tire_reading.mu,
            wheel_torque_nm=wheel_torque_nm,
            wheel_power_w=wheel_power_w,
        )
