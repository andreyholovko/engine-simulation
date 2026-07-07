"""EA888 Gen3 (MK7 GTI, IS20) -- the validation target.

See tests/test_ea888_validation.py: the simulated curve is checked against
VW's own published figures (147kW/200PS, 320Nm torque plateau 1500-4400rpm).
This is the preset `dyno_controller.py` and `dyno_cli.py` actually use.
"""

from engine_sim import CamSpec, EngineSpec

EA888_GEN3_IS20 = EngineSpec(
    name="EA888 Gen3 (MK7 GTI, IS20)",
    displacement_l=1.984,
    cylinders=4,
    compression_ratio=9.6,
    cam=CamSpec(intake_duration_deg=208.0, intake_lift_mm=9.3, overlap_deg=16.0),
    bore_mm=82.5,
    stroke_mm=92.8,
    idle_rpm=800.0,
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
