"""Aftermarket big-frame hybrid single, representative of the TTE500/600
class of upgrade for the 2.0 TSI/TFSI (EA888) platform -- TTE (Turbo Tuning
Engineering) is a real, well-known shop in this exact space, but this preset
is deliberately generic/representative of that whole category rather than
one specific catalog part number: treat the numbers as plausible for a
built-fueling, E85-capable big-single setup (500-600whp class), not a
verified spec sheet.

Same single-scroll I4 layout as the stock IS20/IS38 (no exhaust_scroll_groups
override) -- what differs is sheer size: spools later and a bit slower
(bigger turbine has more rotational inertia to spin up) but carries far more
boost once it's in."""

from engine_sim import TurboSpec

TURBO_EA888_BIG_SINGLE_HYBRID = TurboSpec(
    name="Aftermarket big-frame hybrid (TTE-class)",
    max_boost_bar=2.1,
    spool_midpoint_rpm=3000.0,
    spool_width_rpm=700.0,
    spool_time_constant_s=0.40,
)
