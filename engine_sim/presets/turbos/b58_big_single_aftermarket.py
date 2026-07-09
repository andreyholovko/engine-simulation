"""Aftermarket big-single upgrade for the B58, representative of the class
of turbo-back kits sold by shops like Pure Turbos ("Pure Stage 2") -- real,
well-known in the B58/Supra tuning community, but this preset is generic/
representative of that category (600+whp class on supporting fuel/tune), not
a verified spec sheet for one specific catalog part.

Unlike the stock and B58TU units (both genuinely twin-scroll), these big
aftermarket kits commonly abandon the twin-scroll housing for a single big
turbine fed by a merged/log-style manifold -- a real, documented trade
(twin-scroll's pulse-separation benefit stops mattering once the turbine's
this much bigger than the exhaust pulses feeding it) -- hence
exhaust_scroll_groups=1 here, genuinely different pulse_quality character
from the other two B58 options, not just a bigger number."""

from engine_sim import TurboSpec

TURBO_B58_BIG_SINGLE = TurboSpec(
    name="Aftermarket big single (Pure Stage 2-class)",
    max_boost_bar=2.0,
    spool_midpoint_rpm=2800.0,
    spool_width_rpm=750.0,
    spool_time_constant_s=0.35,
    exhaust_scroll_groups=1,
)
