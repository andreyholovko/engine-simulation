"""GM LS2 (Corvette C6, 2005-2007) -- third validation target, and the first
naturally-aspirated one.

Published figures: 400hp (298.3kW) @ 6000rpm, 400lb-ft (542.4Nm) @ 4400rpm,
5967cc (6.0L), 10.9:1 compression, bore 101.6mm / stroke 92mm, redline
6500rpm. Paired with TURBO_NONE (presets/turbos/none.py) -- no boost at all,
so its torque curve has to rise to peak on VE alone (EngineSpec.ve_rise_rpm),
unlike the two turbocharged presets which get their low-end rise from boost
building instead.

See tests/test_ls2_validation.py for the validation against these figures.
"""

from engine_sim import CamSpec, EngineSpec

LS2_NA = EngineSpec(
    name="GM LS2 (Corvette C6, NA)",
    displacement_l=5.967,
    cylinders=8,
    compression_ratio=10.9,
    cam=CamSpec(intake_duration_deg=256.0, intake_lift_mm=11.0, overlap_deg=22.0),
    bore_mm=101.6,
    stroke_mm=92.0,
    firing_order=(1, 8, 7, 2, 6, 5, 4, 3),  # standard LS firing order
    idle_rpm=650.0,
    redline_rpm=6500.0,
    ve_peak=0.95,
    ve_floor_fraction=0.6,
    ve_rise_rpm=4200.0,  # no boost to do this job -- VE itself rises to the 4400rpm torque peak
    miller_cycle=False,
    friction_a_pa=38_000.0,
    friction_b_pa_per_rpm=10.5,
    friction_c_pa_per_rpm2=0.0011,
    combustion_efficiency=0.98,
    realism_factor=0.654,
    crank_inertia_kgm2=0.30,
)
