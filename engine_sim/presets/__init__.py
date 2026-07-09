"""Real-world engine/turbo presets, one file per engine and per turbo.

engines/ea888_gen3_is20.py + turbos/is20.py, engines/b58_340i.py +
turbos/b58_single_twin_scroll.py, and engines/ls2_na.py + turbos/none.py are
all validated against published figures (see tests/test_ea888_validation.py,
tests/test_b58_validation.py, tests/test_ls2_validation.py) and are what
`ENGINE_CHOICES` below offers for selection -- always paired with their
stock/validated turbo. engines/ea888_gen3b_is38.py exists for variety (and as
the Miller-cycle example) but is explicitly *not* validated -- see that
file's docstring -- so it's deliberately left out of ENGINE_CHOICES.

`TURBO_CHOICES_BY_ENGINE` is a separate axis: real (or representative,
clearly labeled as such) turbo upgrade paths for each ENGINE_CHOICES engine,
swappable via `DynoSession.select_turbo()` *without* changing the engine --
the whole point is watching the same validated engine spec produce a
genuinely different torque/power curve and spool timing under a different
turbo, the same way a real turbo swap does. Each engine's list always starts
with its own stock/validated unit (index 0 matches what ENGINE_CHOICES
already pairs it with).
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
    ROLLER_STANDARD,
    TRANSMISSION_CHOICES,
)

# key -> (EngineSpec, TurboSpec, display name). The key is what
# DynoSession.select_engine() and every UI (Godot, CLI) address a choice by;
# the display name is what a human should see. Add a new selectable engine
# by adding one entry here once its preset files exist. TurboSpec here is
# always that engine's *stock* turbo -- see TURBO_CHOICES_BY_ENGINE for
# swappable alternatives on the same engine.
ENGINE_CHOICES = {
    "ea888_gen3_is20": (EA888_GEN3_IS20, TURBO_IS20, "VW/Audi EA888 Gen3 (MK7 GTI, IS20)"),
    "b58_340i": (B58_340I, TURBO_B58, "BMW B58B30 (340i)"),
    "ls2_na": (LS2_NA, TURBO_NONE, "GM LS2 (Corvette C6, NA)"),
}

# engine key -> [(turbo_key, TurboSpec, display name), ...], index 0 always
# the stock unit ENGINE_CHOICES already pairs that engine with.
# DynoSession.select_turbo(key)/select_turbo_by_index(index) look a choice up
# by the CURRENT engine's own list -- a turbo key from one engine's list is
# not valid for another engine's.
TURBO_CHOICES_BY_ENGINE = {
    "ea888_gen3_is20": [
        ("is20", TURBO_IS20, "Stock IHI IS20"),
        ("is38", TURBO_IS38, "IHI IS38 (hybrid swap)"),
        ("big_single_hybrid", TURBO_EA888_BIG_SINGLE_HYBRID, "Aftermarket big-frame hybrid (TTE-class)"),
    ],
    "b58_340i": [
        ("stock", TURBO_B58, "Stock MHI single twin-scroll (340i)"),
        ("b58tu", TURBO_B58_TU, "BMW B58TU (M340i/Supra factory upgrade)"),
        ("big_single", TURBO_B58_BIG_SINGLE, "Aftermarket big single (Pure Stage 2-class)"),
    ],
    "ls2_na": [
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
    "ENGINE_CHOICES",
    "TURBO_CHOICES_BY_ENGINE",
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
    "ROLLER_STANDARD",
    "TRANSMISSION_CHOICES",
]
