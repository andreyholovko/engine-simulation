"""Turbocharger model: spool lag + wastegate-controlled boost target.

Simplified to what actually matters for a real-time dyno: boost pressure
chases a target (set by RPM/exhaust energy and ECU wastegate duty) with a
first-order lag, which is what produces turbo lag and the "hits boost" feel.
"""

from dataclasses import dataclass
from math import exp

from engine_sim.specs import TurboSpec
from engine_sim.units import BAR_TO_PA


@dataclass
class TurboState:
    boost_pa: float = 0.0  # current gauge boost pressure


@dataclass
class TurboReading:
    """One tick's worth of turbo sensor/diagnostic data -- what a boost gauge
    and the ECU's boost-control logic would actually have available. Mirrors
    EngineReading: the rich, structured result of a tick, not a bare number."""

    boost_pa: float
    target_boost_pa: float  # what the turbo is chasing this tick (spool target)
    wastegate_duty: float  # ECU's commanded wastegate authority this tick, 0-1
    spool_fraction: float  # current boost as a fraction of max_boost_bar, 0-1

    @property
    def boost_bar(self) -> float:
        return self.boost_pa / BAR_TO_PA

    @property
    def target_boost_bar(self) -> float:
        return self.target_boost_pa / BAR_TO_PA


class Turbo:
    def __init__(self, spec: TurboSpec):
        self.spec = spec
        self.state = TurboState()

    def reset(self) -> None:
        self.state.boost_pa = 0.0

    def _target_boost_pa(self, rpm: float, throttle: float, wastegate_duty: float) -> float:
        spec = self.spec
        # Logistic spool curve centered on spool_midpoint_rpm; scaled by
        # throttle as a proxy for exhaust energy (no throttle -> no exhaust
        # flow -> no spool) and by wastegate duty (ECU's boost target cap).
        x = (rpm - spec.spool_midpoint_rpm) / max(spec.spool_width_rpm, 1.0)
        spool_fraction = 1.0 / (1.0 + exp(-x))
        return spec.max_boost_bar * BAR_TO_PA * spool_fraction * throttle * wastegate_duty

    def tick(self, dt: float, rpm: float, throttle: float, wastegate_duty: float) -> TurboReading:
        target = self._target_boost_pa(rpm, throttle, wastegate_duty)
        tau = self.spec.spool_time_constant_s
        alpha = 1.0 - exp(-dt / tau) if tau > 0 else 1.0
        self.state.boost_pa += (target - self.state.boost_pa) * alpha
        self.state.boost_pa = max(0.0, self.state.boost_pa)

        max_boost_pa = self.spec.max_boost_bar * BAR_TO_PA
        spool_fraction = self.state.boost_pa / max_boost_pa if max_boost_pa > 0 else 0.0

        return TurboReading(
            boost_pa=self.state.boost_pa,
            target_boost_pa=target,
            wastegate_duty=wastegate_duty,
            spool_fraction=max(0.0, min(1.0, spool_fraction)),
        )

    @property
    def boost_bar(self) -> float:
        return self.state.boost_pa / BAR_TO_PA
