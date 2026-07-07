"""Real-world engine/turbo presets, one file per engine and per turbo.

engines/ea888_gen3_is20.py + turbos/is20.py is the validation target and the
pair actually wired into dyno_controller.py / dyno_cli.py. engines/
ea888_gen3b_is38.py + turbos/is38.py exist for variety (and as the
Miller-cycle example) but nothing constructs them -- see each file's
docstring.
"""

from engine_sim.presets.engines import EA888_GEN3_IS20, EA888_GEN3B_IS38
from engine_sim.presets.turbos import TURBO_IS20, TURBO_IS38

__all__ = ["EA888_GEN3_IS20", "EA888_GEN3B_IS38", "TURBO_IS20", "TURBO_IS38"]
