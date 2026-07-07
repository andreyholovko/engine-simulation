"""IHI IS20 -- paired with EA888_GEN3_IS20. This is the turbo preset
dyno_controller.py and dyno_cli.py actually use; edit max_boost_bar here to
change the running dyno's boost ceiling."""

from engine_sim import TurboSpec

TURBO_IS20 = TurboSpec(
    name="IHI IS20",
    max_boost_bar=1.3,
    spool_midpoint_rpm=1100.0,
    spool_width_rpm=250.0,
    spool_time_constant_s=0.15,
)
