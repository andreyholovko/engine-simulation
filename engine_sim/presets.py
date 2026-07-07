"""Real-world engine/turbo presets, built from published parameters.

EA888_GEN3_IS20 is the validation target: VW/Audi's own published figures for
the MK7 GTI (147kW/200PS, 320Nm torque plateau 1500-4400rpm, peak power
4400-6000rpm, IHI IS20 turbo full boost by ~3200rpm) -- see
tests/test_ea888_validation.py, which checks the simulated curve lands in
that neighborhood.

EA888_GEN3B_IS38 (Golf R / S3, Miller-cycle "evo") is provided for variety
but its curve is not independently validated against a published dyno sheet
here -- treat its numbers as plausible, not verified.
"""

from .specs import CamSpec, EngineSpec, TurboSpec

EA888_GEN3_IS20 = EngineSpec(
    name="EA888 Gen3 (MK7 GTI, IS20)",
    displacement_l=1.984,
    cylinders=4,
    compression_ratio=9.6,
    cam=CamSpec(intake_duration_deg=208.0, intake_lift_mm=9.3, overlap_deg=16.0),
    bore_mm=82.5,
    stroke_mm=92.8,
    idle_rpm=900.0,
    redline_rpm=6700.0,
    ve_peak=0.93,
    ve_floor_fraction=0.55,
    miller_cycle=False,
    friction_a_pa=32_000.0,
    friction_b_pa_per_rpm=9.0,
    friction_c_pa_per_rpm2=0.00085,
    combustion_efficiency=0.98,
    # Lumped factor covering heat loss, incomplete expansion, and the
    # thermal-efficiency penalty of running rich (~12.5 AFR) at WOT for
    # detonation margin -- not modeled explicitly, folded in here.
    realism_factor=0.52,
    crank_inertia_kgm2=0.18,
)

TURBO_IS20 = TurboSpec(
    name="IHI IS20",
    max_boost_bar=1.3,
    spool_midpoint_rpm=1100.0,
    spool_width_rpm=250.0,
    spool_time_constant_s=0.15,
)

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

TURBO_IS38 = TurboSpec(
    name="IHI IS38",
    max_boost_bar=1.35,
    spool_midpoint_rpm=2300.0,
    spool_width_rpm=600.0,
    spool_time_constant_s=0.30,
)
