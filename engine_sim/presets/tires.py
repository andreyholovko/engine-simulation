"""Tire presets: a few real-world-representative compounds and sizes, the
same "swap one axis, keep everything else" pattern as
TURBO_CHOICES_BY_CAR -- watch the same car's slip behavior change under a
different tire the way a real tire swap does, without touching the engine
or the transmission.
"""

from engine_sim.specs import TireCompound, TireSpec

COMPOUND_STREET = TireCompound(
    name="Street all-season",
    peak_mu=1.0,
    slip_ratio_at_peak=0.12,
    sliding_mu=0.75,
)

COMPOUND_SPORT = TireCompound(
    name="Sport summer",
    peak_mu=1.15,
    slip_ratio_at_peak=0.11,
    sliding_mu=0.85,
)

COMPOUND_DRAG = TireCompound(
    name="Drag radial",
    peak_mu=1.5,
    slip_ratio_at_peak=0.15,
    sliding_mu=1.05,
)

# 225/45R17-ish rolling radius (~0.316m), a common GTI/340i-class OE size.
TIRE_STREET = TireSpec(
    name="225/45R17 street",
    radius_m=0.316,
    width_mm=225.0,
    compound=COMPOUND_STREET,
    inertia_kgm2=1.1,
)

# 245/40R18-ish, wider and lower -- a typical sport/performance upgrade.
TIRE_SPORT = TireSpec(
    name="245/40R18 sport",
    radius_m=0.318,
    width_mm=245.0,
    compound=COMPOUND_SPORT,
    inertia_kgm2=1.3,
)

# 315mm drag radial on the same general rolling radius -- much wider contact
# patch and a stickier compound, the "launch off the line" combination.
TIRE_DRAG = TireSpec(
    name="315/40R18 drag radial",
    radius_m=0.322,
    width_mm=315.0,
    compound=COMPOUND_DRAG,
    inertia_kgm2=1.6,
)

# key -> (TireSpec, display name). Index 0 is the default a fresh chassis
# session starts on.
TIRE_CHOICES = {
    "street": (TIRE_STREET, "225/45R17 Street All-Season"),
    "sport": (TIRE_SPORT, "245/40R18 Sport Summer"),
    "drag": (TIRE_DRAG, "315/40R18 Drag Radial"),
}
