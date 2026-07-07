"""Data-driven engine/turbo/camshaft parameters.

An EngineSpec fully describes a physical engine build (displacement, cylinder
count, compression ratio, camshaft profile, friction characteristics). The
Engine model computes torque output from these parameters plus live
throttle/RPM/manifold-pressure inputs -- it never hardcodes a canned curve.
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class CamSpec:
    """Camshaft profile. Longer duration / higher lift shifts the engine's
    breathing (volumetric efficiency) sweet spot to a higher RPM band, at the
    cost of low-RPM torque -- the classic cam trade-off."""

    intake_duration_deg: float = 220.0
    intake_lift_mm: float = 9.5
    overlap_deg: float = 20.0


@dataclass(frozen=True)
class EngineSpec:
    name: str
    displacement_l: float
    cylinders: int
    compression_ratio: float
    cam: CamSpec = field(default_factory=CamSpec)

    # The actual firing order (1-indexed cylinder numbers), e.g. (1, 3, 4, 2)
    # for most transverse inline-4s or (1, 5, 3, 6, 2, 4) for a BMW inline-6.
    # Doesn't change pulse *spacing* for an even-firing inline engine (that's
    # cylinders*rpm/120 regardless of order) -- it's the sequence each
    # cylinder's fixed exhaust signature repeats in every revolution, which is
    # what audio synthesis (or anything else caring about per-cylinder
    # character) should actually consume, rather than guessing from cylinder
    # count alone. Defaults to a plain 1..N sequence for anything that hasn't
    # set a real one.
    firing_order: Tuple[int, ...] = ()

    bore_mm: float = 82.5
    stroke_mm: float = 92.8

    idle_rpm: float = 900.0
    redline_rpm: float = 6700.0

    # Volumetric efficiency shape: flat "plateau" up to ve_falloff_rpm, then
    # tapering off as breathing/flow limits bite at high RPM. The falloff
    # point shifts with cam duration (longer duration breathes further up
    # the rev range).
    ve_peak: float = 0.92
    ve_floor_fraction: float = 0.55

    # Miller/Otto-cycle engines (e.g. EA888 Gen3B "evo") vary *effective*
    # compression in real time via intake valve closing timing: early closure
    # (Miller) at low load for efficiency, later closure (near-Otto) under
    # load for power. Non-Miller engines just use compression_ratio as-is.
    miller_cycle: bool = False
    miller_compression_ratio: float = 0.0  # effective ratio at low load, if miller_cycle

    # FMEP-style friction model (Pa): fmep = a + b*rpm + c*rpm^2
    friction_a_pa: float = 35_000.0
    friction_b_pa_per_rpm: float = 10.0
    friction_c_pa_per_rpm2: float = 0.001

    combustion_efficiency: float = 0.98
    # Fraction of ideal Otto-cycle thermal efficiency actually realized once
    # heat loss, incomplete expansion etc. are accounted for.
    realism_factor: float = 0.80

    crank_inertia_kgm2: float = 0.18

    @property
    def displacement_m3(self) -> float:
        return self.displacement_l / 1000.0

    @property
    def firing_order_resolved(self) -> Tuple[int, ...]:
        """firing_order if set, else a plain 1..N sequence."""
        return self.firing_order or tuple(range(1, self.cylinders + 1))

    def ve_falloff_rpm(self) -> float:
        # Longer duration cams keep breathing well further up the rev range.
        return 4200.0 + (self.cam.intake_duration_deg - 200.0) * 25.0


@dataclass(frozen=True)
class TurboSpec:
    name: str
    max_boost_bar: float  # gauge pressure, bar
    # RPM at which the turbo reaches ~50% of max boost at WOT -- matches how
    # manufacturers quote "full boost by N rpm".
    spool_midpoint_rpm: float
    spool_width_rpm: float = 700.0
    spool_time_constant_s: float = 0.35
