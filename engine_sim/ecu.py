"""ECU: the central controller.

Real ECU responsibilities, modeled here: closed-loop fuel control (AFR
target), wastegate duty (boost target), rev limiter, and computing intake
manifold pressure from throttle position + current boost. Every reading the
dyno displays is something a real ECU could actually report on its data bus.

AFR target and boost target both have a sane default control law, but can be
overridden live -- exactly the "adjustable in real time" knobs the dyno needs.
"""

from dataclasses import dataclass
from typing import Optional

from .specs import EngineSpec, TurboSpec
from .units import P_ATM


@dataclass
class EcuReading:
    map_pa: float
    load_fraction: float
    target_afr: float
    wastegate_duty: float
    rev_limiter_active: bool


class ECU:
    def __init__(self, engine_spec: EngineSpec, turbo_spec: Optional[TurboSpec] = None):
        self.engine_spec = engine_spec
        self.turbo_spec = turbo_spec
        self._afr_override: Optional[float] = None
        self._boost_target_override: Optional[float] = None  # fraction 0..1 of max boost
        self._rev_limiter_headroom_rpm = 150.0

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
        return self.engine_spec.redline_rpm - self._rev_limiter_headroom_rpm

    def rev_limiter_active(self, rpm: float) -> bool:
        return rpm >= self.rev_limiter_threshold_rpm

    def intake_manifold_pressure(self, throttle: float, boost_pa: float) -> float:
        throttle = max(0.0, min(1.0, throttle))
        return P_ATM + throttle * boost_pa

    def load_fraction(self, map_pa: float, boost_pa: float) -> float:
        max_map = P_ATM + boost_pa if boost_pa > 0 else P_ATM
        return max(0.0, min(1.0, map_pa / max_map)) if max_map > 0 else 0.0

    def tick(self, rpm: float, throttle: float, boost_pa: float) -> EcuReading:
        map_pa = self.intake_manifold_pressure(throttle, boost_pa)
        load_fraction = self.load_fraction(map_pa, boost_pa)
        afr = self.target_afr(throttle)
        limiter = self.rev_limiter_active(rpm)
        if limiter:
            # Ignition/fuel cut: starve it back below the limiter threshold.
            afr = 0.0
        return EcuReading(
            map_pa=map_pa,
            load_fraction=load_fraction,
            target_afr=afr,
            wastegate_duty=self.wastegate_duty(rpm, throttle),
            rev_limiter_active=limiter,
        )
