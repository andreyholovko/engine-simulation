"""Real-world car/engine/turbo presets, one file per engine and per turbo.

engines/ea888_gen3_is20.py + turbos/is20.py, engines/b58_340i.py +
turbos/b58_single_twin_scroll.py, and engines/ls2_na.py + turbos/none.py are
all validated against published figures (see tests/test_ea888_validation.py,
tests/test_b58_validation.py, tests/test_ls2_validation.py) and are what
`CAR_CHOICES` below offers for selection -- each car always paired with its
own stock/validated turbo. engines/ea888_gen3b_is38.py exists for variety
(and as the Miller-cycle example) but is explicitly *not* validated -- see
that file's docstring -- so it's deliberately left out of CAR_CHOICES.

`TURBO_CHOICES_BY_CAR` is a separate axis: real (or representative, clearly
labeled as such) turbo upgrade paths for each CAR_CHOICES car, swappable via
`DynoSession.select_turbo()` *without* changing the car (or its engine) --
the whole point is watching the same validated engine spec produce a
genuinely different torque/power curve and spool timing under a different
turbo, the same way a real turbo swap does. Each car's list always starts
with its own stock/validated unit (index 0 matches what CAR_CHOICES already
pairs it with).
"""

from engine_sim.presets.engines import EA888_GEN3_IS20, EA888_GEN3B_IS38, B58_340I, LS2_NA
from engine_sim.presets.turbos import (
    TURBO_IS20,
    TURBO_IS38,
    TURBO_B58,
    TURBO_B58_TU,
    TURBO_B58_BIG_SINGLE,
    TURBO_EA888_BIG_SINGLE_HYBRID,
    TURBO_LS2_TWIN,
    TURBO_NONE,
)
from engine_sim.presets.tires import (
    COMPOUND_STREET,
    COMPOUND_SPORT,
    COMPOUND_DRAG,
    TIRE_STREET,
    TIRE_SPORT,
    TIRE_DRAG,
    TIRE_CHOICES,
)
from engine_sim.presets.transmissions import (
    TRANSMISSION_6MT,
    TRANSMISSION_AUTO_6SPEED,
    TORQUE_CONVERTER_STANDARD,
    CLUTCH_PERFORMANCE,
    ROLLER_FWD,
    ROLLER_RWD,
    ROLLER_AWD,
    ROLLER_BY_DRIVETRAIN_LAYOUT,
    TRANSMISSION_CHOICES,
)
from engine_sim.specs import CarSpec

# key -> CarSpec. The key is what DynoSession.select_car() and every UI
# (Godot, CLI) address a choice by; CarSpec.name is what a human should see.
# Add a new selectable car by adding one entry here once its engine/turbo
# preset files exist. CarSpec.turbo_spec here is always that car's *stock*
# turbo -- see TURBO_CHOICES_BY_CAR for swappable alternatives on the same
# car; CarSpec.drivetrain_layout picks its RollerSpec (traction) via
# ROLLER_BY_DRIVETRAIN_LAYOUT.
#
# One of each real layout, deliberately: the Mk7 GTI is genuinely FWD (VW
# never sold a US-market GTI with a driven rear axle), the C6 Corvette is
# genuinely RWD (no AWD C6 ever existed), and the 340i here is specifically
# the xDrive variant -- the real, factory AWD version of the same B58B30
# engine BMW also sold RWD -- rather than the base RWD 340i, precisely so
# these three cars cover fwd/rwd/awd instead of landing on rwd twice.
CAR_CHOICES = {
    "mk7_gti": CarSpec(
        name="VW/Audi Mk7 GTI (EA888 Gen3, IS20)",
        engine_spec=EA888_GEN3_IS20, turbo_spec=TURBO_IS20, drivetrain_layout="fwd",
    ),
    "f30_340i": CarSpec(
        name="BMW F30 340i xDrive (B58B30)",
        engine_spec=B58_340I, turbo_spec=TURBO_B58, drivetrain_layout="awd",
    ),
    "c6_corvette": CarSpec(
        name="Chevrolet C6 Corvette (LS2, NA)",
        engine_spec=LS2_NA, turbo_spec=TURBO_NONE, drivetrain_layout="rwd",
    ),
}

# car key -> [(turbo_key, TurboSpec, display name), ...], index 0 always the
# stock unit CAR_CHOICES already pairs that car with.
# DynoSession.select_turbo(key)/select_turbo_by_index(index) look a choice up
# by the CURRENT car's own list -- a turbo key from one car's list is not
# valid for another car's, even if they happen to share an engine.
TURBO_CHOICES_BY_CAR = {
    "mk7_gti": [
        ("is20", TURBO_IS20, "Stock IHI IS20"),
        ("is38", TURBO_IS38, "IHI IS38 (hybrid swap)"),
        ("big_single_hybrid", TURBO_EA888_BIG_SINGLE_HYBRID, "Aftermarket big-frame hybrid (TTE-class)"),
    ],
    "f30_340i": [
        ("stock", TURBO_B58, "Stock MHI single twin-scroll (340i)"),
        ("b58tu", TURBO_B58_TU, "BMW B58TU (M340i/Supra factory upgrade)"),
        ("big_single", TURBO_B58_BIG_SINGLE, "Aftermarket big single (Pure Stage 2-class)"),
    ],
    "c6_corvette": [
        ("none", TURBO_NONE, "Naturally aspirated (stock)"),
        ("twin_turbo", TURBO_LS2_TWIN, "Twin-turbo kit (representative, stock-internals-safe)"),
    ],
}

__all__ = [
    "EA888_GEN3_IS20",
    "EA888_GEN3B_IS38",
    "B58_340I",
    "LS2_NA",
    "TURBO_IS20",
    "TURBO_IS38",
    "TURBO_B58",
    "TURBO_B58_TU",
    "TURBO_B58_BIG_SINGLE",
    "TURBO_EA888_BIG_SINGLE_HYBRID",
    "TURBO_LS2_TWIN",
    "TURBO_NONE",
    "CAR_CHOICES",
    "TURBO_CHOICES_BY_CAR",
    "COMPOUND_STREET",
    "COMPOUND_SPORT",
    "COMPOUND_DRAG",
    "TIRE_STREET",
    "TIRE_SPORT",
    "TIRE_DRAG",
    "TIRE_CHOICES",
    "TRANSMISSION_6MT",
    "TRANSMISSION_AUTO_6SPEED",
    "TORQUE_CONVERTER_STANDARD",
    "CLUTCH_PERFORMANCE",
    "ROLLER_FWD",
    "ROLLER_RWD",
    "ROLLER_AWD",
    "ROLLER_BY_DRIVETRAIN_LAYOUT",
    "TRANSMISSION_CHOICES",
]
