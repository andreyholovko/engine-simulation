"""Representative twin-turbo kit for the LS2 -- turbocharging an LS engine
is arguably the single most common American V8 tuning path (Nelson Racing
Engines, Boostline, Hellion, and others all sell real, well-known LS twin-
turbo kits), but there's no one canonical "the LS2 turbo" the way there's an
OEM upgrade path for the EA888/B58 -- these are custom, kit-dependent builds.
This preset is a conservative, stock-internals-safe representative point
(~10psi/0.7 bar), not a specific catalog kit's verified spec sheet.

Modeled as a single TurboSpec representing the matched pair, same
simplification this project already uses for the B58's twin-scroll housing
(one turbo per bank of 4 cylinders is the same "half the cylinders feed one
turbine path" shape as twin-scroll, hence exhaust_scroll_groups=2 here too)."""

from engine_sim import TurboSpec

TURBO_LS2_TWIN = TurboSpec(
    name="Twin-turbo kit (representative, stock-internals-safe)",
    max_boost_bar=0.7,
    spool_midpoint_rpm=3200.0,
    spool_width_rpm=800.0,
    spool_time_constant_s=0.35,
    exhaust_scroll_groups=2,
)
