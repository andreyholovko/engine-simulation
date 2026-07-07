"""MHI single twin-scroll turbo, paired with B58_340I.

A twin-scroll housing (two separate exhaust-gas paths feeding one turbine,
one per exhaust bank of three cylinders) spools noticeably faster than a
comparable single-scroll turbo -- consistent with the B58's torque plateau
starting at just 1380rpm, barely above idle."""

from engine_sim import TurboSpec

TURBO_B58 = TurboSpec(
    name="MHI single twin-scroll (B58)",
    max_boost_bar=1.2,
    spool_midpoint_rpm=800.0,
    spool_width_rpm=200.0,
    spool_time_constant_s=0.12,
)
