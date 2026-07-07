"""IHI IS38 -- paired with EA888_GEN3B_IS38. Decorative only: nothing in
dyno_controller.py or dyno_cli.py constructs this preset, so editing it has
no visible effect anywhere. Change TURBO_IS20 instead for the live dyno."""

from engine_sim import TurboSpec

TURBO_IS38 = TurboSpec(
    name="IHI IS38",
    max_boost_bar=3.35,
    spool_midpoint_rpm=2300.0,
    spool_width_rpm=600.0,
    spool_time_constant_s=0.30,
)
