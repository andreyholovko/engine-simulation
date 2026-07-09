"""ECU: the central controller.

The ECU owns the Engine and Turbo and is the *only* thing that talks to them
each tick -- exactly like a real car, where the ECU reads sensors and drives
the throttle body/injectors/wastegate, rather than some external loop poking
each component by hand. `tick()` runs the full sensor-to-actuator sequence in
the right order (decide wastegate duty -> spool the turbo -> derive manifold
pressure/load from the *resulting* boost -> decide fuel/rev-limit -> ask the
engine for torque) and returns one reading with everything in it. Real ECU
responsibilities modeled here: closed-loop fuel control (AFR target),
wastegate duty (boost target), and the rev limiter.

AFR target and boost target both have a sane default control law, but can be
overridden live -- exactly the "adjustable in real time" knobs the dyno needs.

`tick()` also accepts a `torque_reduction_fraction` -- a real ECU responsibility
too: automatic transmissions command a momentary torque cut (ignition retard
or a partial fuel cut, not touched here at the AFR-control level) during a
shift, both to protect the clutch packs from a full-torque hit and to make
the shift feel controlled rather than jerky. Modeled as a reduction of
*indicated* torque specifically (friction_torque_nm is untouched -- real
mechanical drag doesn't go away just because combustion torque is being
managed), so a severe enough cut can genuinely make net torque go negative
for a moment, the same "engine braking" shape DFCO already produces.
"""

from dataclasses import dataclass, replace
from typing import Optional

from engine_sim.core.engine import Engine, EngineReading
from engine_sim.core.turbo import Turbo, TurboReading
from engine_sim.units import P_ATM, IDLE_MAP_PA, T_INTAKE_DEFAULT, STOICH_AFR


@dataclass
class EcuReading:
    engine: EngineReading
    turbo: TurboReading
    map_pa: float
    load_fraction: float
    target_afr: float
    wastegate_duty: float
    rev_limiter_active: bool

    @property
    def boost_bar(self) -> float:
        return self.turbo.boost_bar


class ECU:
    def __init__(self, engine: Engine, turbo: Turbo):
        self.engine = engine
        self.turbo = turbo
        self._afr_override: Optional[float] = None
        self._boost_target_override: Optional[float] = None  # fraction 0..1 of max boost
        self._octane_override: Optional[float] = None
        self._rev_limiter_headroom_rpm = 150.0
        # Hysteresis band: fuel resumes only once rpm drops this far below
        # the cut point, not the instant it dips under threshold -- gives a
        # real bounce (climb, cut, fall, resume, climb again) instead of
        # chattering right at one boundary or flatlining dead-level.
        self._rev_limiter_bounce_band_rpm = 120.0
        self._rev_limiter_engaged = False
        # Wastegate duty needs a load signal, but load_fraction this same
        # tick isn't known yet (it depends on the boost this call is about
        # to produce) -- one-tick-lagged, same trick a real MAP-based ECU
        # effectively has (it's reacting to the last sample too). Defaults
        # to 1.0 so the very first tick behaves as full authority, same as
        # before this existed.
        self._last_load_fraction = 1.0

        # Idle air control: real ECUs hold idle via a small, fixed bypass air
        # opening (or electronic throttle held at a calculated idle crack),
        # not by cutting fuel. This isn't enough on its own to land exactly
        # on a target RPM (that's SimulationLoop's job, holding it with the
        # dyno brake the way a real idle is also held against accessory
        # load) -- it just needs to produce *some* modest, non-runaway
        # torque instead of either "full atmospheric MAP at stoich" (the old
        # bug) or a hard cut (stalls instead of idling).
        self.idle_throttle_equivalent = 0.06
        # DFCO (deceleration fuel cut-off): closed throttle is only treated
        # as "idle" up to this multiple of idle_rpm. Above it, real ECUs cut
        # fuel entirely on a trailing throttle rather than keep feeding the
        # same idle-air-equivalent opening (which would flow *more* air, and
        # so make *more* torque, at higher rpm -- the opposite of what a
        # lifted throttle should do). The resulting zero indicated torque
        # against real friction is exactly what makes a lifted throttle
        # decelerate like genuine engine braking instead of coasting on the
        # dyno's own light drag alone.
        self._dfco_reengage_factor = 1.2

    def set_target_afr(self, afr: Optional[float]) -> None:
        """Operator override for target AFR (None restores the default
        load-based control law)."""
        self._afr_override = afr

    def set_boost_target_fraction(self, fraction: Optional[float]) -> None:
        """Operator override for wastegate duty, as a fraction of the
        turbo's max boost (None restores full authority)."""
        self._boost_target_override = fraction

    def set_fuel_octane(self, octane: Optional[float]) -> None:
        """Operator override for pump octane (None restores the engine's own
        knock_octane_requirement -- no knock penalty, the default)."""
        self._octane_override = octane

    def target_afr(self, load_fraction: float) -> float:
        """RPM/load-based control law: real speed-density ECUs index the
        base fuel table primarily on MAP (load), not throttle position --
        stoichiometric at low load/cruise, enrichening toward a power-safe
        ratio as load rises toward WOT. RPM's influence is already folded
        in here rather than duplicated: it shapes load_fraction's own
        evolution (via turbo spool timing), the same way a real table's RPM
        axis and MAP axis aren't independent of each other."""
        if self._afr_override is not None:
            return self._afr_override
        power_afr = 12.5  # "best power" mixture for gasoline WOT, richer than stoich
        load = max(0.0, min(1.0, load_fraction))
        return STOICH_AFR + (power_afr - STOICH_AFR) * load

    def wastegate_duty(self, rpm: float, throttle: float) -> float:
        if self._boost_target_override is not None:
            return max(0.0, min(1.0, self._boost_target_override))
        # Real ECUs don't target full boost away from high load/WOT, and
        # hold back just above idle even at WOT (driveability/knock margin)
        # -- ramp authority in with both load and RPM rather than a flat
        # full-open. At WOT past a couple hundred rpm off idle both terms
        # are already 1.0 (na_map alone reaches atmospheric at throttle=1,
        # independent of boost), so every existing WOT-based validated pull
        # is unaffected -- this only bites at partial throttle/low RPM.
        load_term = max(0.0, min(1.0, (self._last_load_fraction - 0.3) / 0.5))
        idle_rpm = self.engine.spec.idle_rpm
        rpm_term = max(0.0, min(1.0, (rpm - idle_rpm * 1.1) / max(idle_rpm * 0.4, 1.0)))
        return load_term * rpm_term

    @property
    def dfco_reengage_rpm(self) -> float:
        """Above this, a closed throttle is a real fuel cut, not idle-air.
        The single source of truth for "still decelerating under engine
        braking" vs. "back to idle-equivalent fueling" -- DynoSession's own
        coast-vs-PID-hold handoff uses this exact number too, so the two
        never independently drift out of step (a PID engaging while the ECU
        is still fuel-cutting would stack its correction on top of real
        engine-braking torque -- a much harder brake than either alone)."""
        return self.engine.spec.idle_rpm * self._dfco_reengage_factor

    @property
    def rev_limiter_threshold_rpm(self) -> float:
        return self.engine.spec.redline_rpm - self._rev_limiter_headroom_rpm

    def rev_limiter_active(self, rpm: float) -> bool:
        cut_rpm = self.rev_limiter_threshold_rpm
        resume_rpm = cut_rpm - self._rev_limiter_bounce_band_rpm
        if rpm >= cut_rpm:
            self._rev_limiter_engaged = True
        elif rpm < resume_rpm:
            self._rev_limiter_engaged = False
        return self._rev_limiter_engaged

    def intake_manifold_pressure(self, throttle: float, boost_pa: float) -> float:
        """Naturally-aspirated MAP blends from a closed-throttle vacuum floor
        up to atmospheric as the throttle plate opens (this is what actually
        restricts airflow at low throttle -- boost_pa on its own never did;
        it only ever added on top). Boost then adds on top, scaled by
        throttle same as before -- unchanged at WOT (throttle=1), where this
        reduces exactly to the old P_ATM + boost_pa."""
        throttle = max(0.0, min(1.0, throttle))
        na_map_pa = IDLE_MAP_PA + (P_ATM - IDLE_MAP_PA) * throttle
        return na_map_pa + throttle * boost_pa

    def load_fraction(self, map_pa: float, boost_pa: float) -> float:
        max_map = P_ATM + boost_pa if boost_pa > 0 else P_ATM
        return max(0.0, min(1.0, map_pa / max_map)) if max_map > 0 else 0.0

    def tick(
        self,
        dt: float,
        rpm: float,
        throttle: float,
        ambient_temp_k: float = T_INTAKE_DEFAULT,
        torque_reduction_fraction: float = 0.0,
    ) -> EcuReading:
        throttle = max(0.0, min(1.0, throttle))
        torque_reduction_fraction = max(0.0, min(1.0, torque_reduction_fraction))
        closed_throttle = throttle <= 1e-6
        decel_fuel_cut = closed_throttle and rpm > self.dfco_reengage_rpm
        # Idle-air-equivalent opening only near idle -- well above it on a
        # closed throttle, MAP still reflects the closed plate (real vacuum
        # regardless of rpm) but fueling is handled by decel_fuel_cut below,
        # not by this substitute throttle value.
        effective_throttle = self.idle_throttle_equivalent if (closed_throttle and not decel_fuel_cut) else (
            0.0 if closed_throttle else throttle
        )

        wastegate_duty = self.wastegate_duty(rpm, effective_throttle)
        turbo_reading = self.turbo.tick(dt, rpm, effective_throttle, wastegate_duty, ambient_temp_k)
        map_pa = self.intake_manifold_pressure(effective_throttle, turbo_reading.boost_pa)
        load_fraction = self.load_fraction(map_pa, turbo_reading.boost_pa)
        self._last_load_fraction = load_fraction

        limiter = self.rev_limiter_active(rpm)
        # Ignition/fuel cut: rev limiter, or a real DFCO event. Idle air is
        # never cut near idle -- that's what actually holds idle instead of
        # stalling.
        target_afr = 0.0 if (limiter or decel_fuel_cut) else self.target_afr(load_fraction)
        octane = self._octane_override if self._octane_override is not None else self.engine.spec.knock_octane_requirement

        engine_reading = self.engine.compute(
            rpm=rpm,
            map_pa=map_pa,
            target_afr=target_afr,
            load_fraction=load_fraction,
            intake_temp_k=turbo_reading.intake_air_temp_k,
            octane=octane,
        )

        if torque_reduction_fraction > 0.0:
            reduced_indicated = engine_reading.indicated_torque_nm * (1.0 - torque_reduction_fraction)
            engine_reading = replace(
                engine_reading,
                indicated_torque_nm=reduced_indicated,
                net_torque_nm=reduced_indicated - engine_reading.friction_torque_nm,
            )

        return EcuReading(
            engine=engine_reading,
            turbo=turbo_reading,
            map_pa=map_pa,
            load_fraction=load_fraction,
            target_afr=target_afr,
            wastegate_duty=wastegate_duty,
            rev_limiter_active=limiter,
        )
