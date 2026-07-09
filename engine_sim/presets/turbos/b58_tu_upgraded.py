"""The updated B58 ("B58TU") factory turbo used on the M340i/M440i and the
Toyota Supra 3.0 -- a real, documented BMW running change: a genuinely
bigger compressor/turbine than the base 340i's unit (presets/turbos/
b58_single_twin_scroll.py), still a single twin-scroll housing, producing
382hp factory-rated versus the 340i's 320hp at a higher boost level.

Selectable in TURBO_CHOICES_BY_ENGINE for B58_340I (presets/__init__.py) --
same short-block/tune otherwise, fitting the bigger factory turbo alone
should visibly lift the whole curve, the same direction the real M340i/
Supra differ from the base 340i."""

from engine_sim import TurboSpec

TURBO_B58_TU = TurboSpec(
    name="BMW B58TU (M340i/Supra factory upgrade)",
    max_boost_bar=1.45,
    # Bigger than the base 340i unit (midpoint 800/width 200) -- spools
    # slightly later and less sharply, same twin-scroll character.
    spool_midpoint_rpm=850.0,
    spool_width_rpm=210.0,
    spool_time_constant_s=0.13,
    # Still genuinely twin-scroll, same as the base 340i unit.
    exhaust_scroll_groups=2,
)
