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
"""

from dataclasses import dataclass
from typing import Optional

from engine_sim.core.engine import Engine, EngineReading
from engine_sim.core.turbo import Turbo, TurboReading
from engine_sim.units import P_ATM, IDLE_MAP_PA


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
        self._rev_limiter_headroom_rpm = 150.0

        # Idle air control: real ECUs hold idle via a small, fixed bypass air
        # opening (or electronic throttle held at a calculated idle crack),
        # not by cutting fuel -- DFCO (fuel cut) only kicks in on decel
        # *above* idle. This isn't enough on its own to land exactly on a
        # target RPM (that's SimulationLoop's job, holding it with the dyno
        # brake the way a real idle is also held against accessory load) --
        # it just needs to produce *some* modest, non-runaway torque instead
        # of either "full atmospheric MAP at stoich" (the old bug) or a hard
        # cut (stalls instead of idling).
        self.idle_throttle_equivalent = 0.06

    def set_target_afr(self, afr: Optional[float]) -> None:
        """Operator override for target AFR (None restores the default
        load-based control law)."""
        self._afr_override = afr

    def set_boost_target_fraction(self, fraction: Optional[float]) -> None:
        """Operator override for wastegate duty, as a fraction of the
        turbo's max boost (None restores full authority)."""
        self._boost_target_override = fraction

    def target_afr(self, throttle: float) -> float:
        if self._afr_override is not None:
            return self._afr_override
        # Default control law: stoichiometric cruise, enrichen toward a
        # power-safe ratio as throttle opens.
        stoich = 14.7
        power_afr = 12.5
        t = max(0.0, min(1.0, throttle))
        return stoich + (power_afr - stoich) * t

    def wastegate_duty(self, rpm: float, throttle: float) -> float:
        if self._boost_target_override is not None:
            return max(0.0, min(1.0, self._boost_target_override))
        return 1.0  # full authority: let the turbo spec's own spool curve govern

    @property
    def rev_limiter_threshold_rpm(self) -> float:
        return self.engine.spec.redline_rpm - self._rev_limiter_headroom_rpm

    def rev_limiter_active(self, rpm: float) -> bool:
        return rpm >= self.rev_limiter_threshold_rpm

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

    def tick(self, dt: float, rpm: float, throttle: float, intake_temp_k: float = 313.0) -> EcuReading:
        throttle = max(0.0, min(1.0, throttle))
        effective_throttle = throttle if throttle > 1e-6 else self.idle_throttle_equivalent

        wastegate_duty = self.wastegate_duty(rpm, effective_throttle)
        turbo_reading = self.turbo.tick(dt, rpm, effective_throttle, wastegate_duty)
        map_pa = self.intake_manifold_pressure(effective_throttle, turbo_reading.boost_pa)
        load_fraction = self.load_fraction(map_pa, turbo_reading.boost_pa)

        limiter = self.rev_limiter_active(rpm)
        # Ignition/fuel cut: starve it back below the limiter threshold. Idle
        # air is never cut -- that's what actually holds idle instead of
        # stalling.
        target_afr = 0.0 if limiter else self.target_afr(effective_throttle)

        engine_reading = self.engine.compute(
            rpm=rpm,
            map_pa=map_pa,
            target_afr=target_afr,
            load_fraction=load_fraction,
            intake_temp_k=intake_temp_k,
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
