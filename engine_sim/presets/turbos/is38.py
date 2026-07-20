"""IHI IS38 -- OE on the Golf R/S3, and one of the most common real-world
upgrades for an IS20-equipped car (the "IS38 swap"/"IS38 hybrid" is a
well-known path in the VW/Audi tuning community -- physically larger
compressor and turbine than the IS20, same basic single-scroll I4 layout).
Selectable in ENGINE_SIM's TURBO_CHOICES_BY_CAR for EA888_GEN3_IS20 (see
presets/__init__.py) -- fitting the "wrong" (bigger, later-spooling) turbo
on the same engine spec and watching torque/power/spool timing all shift is
the point.

max_boost_bar corrected from an old decorative placeholder (3.35 bar, ~49psi
-- nothing real runs anywhere near that) to ~1.8 bar, in line with a
tuned/hybrid IS38 on pump fuel or E85 (stock IS38 on the Golf R/S3 itself
runs closer to 1.5-1.6 bar)."""

from engine_sim import TurboSpec

TURBO_IS38 = TurboSpec(
    name="IHI IS38 (hybrid swap)",
    max_boost_bar=1.8,
    # Physically bigger turbo: spools later and less decisively than the
    # IS20 (spool_midpoint 1100/width 250), and reacts a touch slower too.
    spool_midpoint_rpm=2300.0,
    spool_width_rpm=600.0,
    spool_time_constant_s=0.30,
)
