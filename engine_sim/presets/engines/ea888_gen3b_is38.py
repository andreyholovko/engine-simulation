"""EA888 Gen3B "evo" (Golf R / S3, Miller-cycle, paired with the IS38 turbo).

Not independently validated against a published dyno sheet -- treat its
numbers as plausible, not verified. Also not wired into dyno_controller.py
or dyno_cli.py; those hardcode EA888_GEN3_IS20. Provided for variety and as
the Miller-cycle (variable effective compression) example.
"""

from engine_sim import CamSpec, EngineSpec

EA888_GEN3B_IS38 = EngineSpec(
    name="EA888 Gen3B evo (Golf R/S3, Miller, IS38)",
    displacement_l=1.984,
    cylinders=4,
    compression_ratio=11.6,
    cam=CamSpec(intake_duration_deg=214.0, intake_lift_mm=9.8, overlap_deg=18.0),
    bore_mm=82.5,
    stroke_mm=92.8,
    idle_rpm=900.0,
    redline_rpm=6800.0,
    ve_peak=0.95,
    ve_floor_fraction=0.55,
    miller_cycle=True,
    miller_compression_ratio=8.2,
    friction_a_pa=33_000.0,
    friction_b_pa_per_rpm=9.5,
    friction_c_pa_per_rpm2=0.0009,
    combustion_efficiency=0.98,
    realism_factor=0.82,
    crank_inertia_kgm2=0.18,
)
