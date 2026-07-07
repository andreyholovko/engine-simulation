"""Real-world engine/turbo presets, one file per engine and per turbo.

engines/ea888_gen3_is20.py + turbos/is20.py, engines/b58_340i.py +
turbos/b58_single_twin_scroll.py, and engines/ls2_na.py + turbos/none.py are
all validated against published figures (see tests/test_ea888_validation.py,
tests/test_b58_validation.py, tests/test_ls2_validation.py) and are what
`ENGINE_CHOICES` below offers for selection. engines/ea888_gen3b_is38.py +
turbos/is38.py exist for variety (and as the Miller-cycle example) but are
explicitly *not* validated -- see that file's docstring -- so they're
deliberately left out of ENGINE_CHOICES rather than presented as an
equally-trustworthy option.
"""

from engine_sim.presets.engines import EA888_GEN3_IS20, EA888_GEN3B_IS38, B58_340I, LS2_NA
from engine_sim.presets.turbos import TURBO_IS20, TURBO_IS38, TURBO_B58, TURBO_NONE

# key -> (EngineSpec, TurboSpec, display name). The key is what
# DynoSession.select_engine() and every UI (Godot, CLI) address a choice by;
# the display name is what a human should see. Add a new selectable engine
# by adding one entry here once its preset files exist.
ENGINE_CHOICES = {
    "ea888_gen3_is20": (EA888_GEN3_IS20, TURBO_IS20, "VW/Audi EA888 Gen3 (MK7 GTI, IS20)"),
    "b58_340i": (B58_340I, TURBO_B58, "BMW B58B30 (340i)"),
    "ls2_na": (LS2_NA, TURBO_NONE, "GM LS2 (Corvette C6, NA)"),
}

__all__ = [
    "EA888_GEN3_IS20",
    "EA888_GEN3B_IS38",
    "B58_340I",
    "LS2_NA",
    "TURBO_IS20",
    "TURBO_IS38",
    "TURBO_B58",
    "TURBO_NONE",
    "ENGINE_CHOICES",
]
