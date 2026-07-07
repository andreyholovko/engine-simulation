"""BMW B58B30 (340i, non-M340i) -- second validation target.

Published figures: 320hp (238.7kW) @ 5500-6500rpm, 330lb-ft (447Nm) torque,
flat from 1380-5000rpm, 2998cc, 11.0:1 compression, bore 82mm / stroke
94.6mm, redline 7000rpm. Despite being colloquially called "twin-turbo," the
B58 uses a single turbocharger with a twin-scroll housing (two separate
exhaust-gas paths feeding one turbo, not two turbos) -- paired with
TURBO_B58 in presets/turbos/b58_single_twin_scroll.py, one turbo, same as
every other preset here.

See tests/test_b58_validation.py for the validation against these figures.
"""

from engine_sim import CamSpec, EngineSpec

B58_340I = EngineSpec(
    name="BMW B58B30 (340i)",
    displacement_l=2.998,
    cylinders=6,
    compression_ratio=11.0,
    cam=CamSpec(intake_duration_deg=232.0, intake_lift_mm=9.8, overlap_deg=18.0),
    bore_mm=82.0,
    stroke_mm=94.6,
    firing_order=(1, 5, 3, 6, 2, 4),  # BMW's inline-6 firing order
    idle_rpm=700.0,
    redline_rpm=7000.0,
    ve_peak=0.94,
    ve_floor_fraction=0.55,
    miller_cycle=False,
    friction_a_pa=34_000.0,
    friction_b_pa_per_rpm=9.5,
    friction_c_pa_per_rpm2=0.0009,
    combustion_efficiency=0.98,
    realism_factor=0.471,
    crank_inertia_kgm2=0.24,
)
