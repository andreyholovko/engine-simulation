"""Transmission/clutch/roller presets for chassis-dyno mode: a manual
gearbox and a torque-converter automatic (Aisin-class), same gear ratios and
final drive so the two are directly comparable -- swapping between them
should feel like swapping a real car's gearbox, not switching to a
different car.
"""

from dataclasses import replace

from engine_sim.specs import (
    AutomaticTransmissionSpec,
    ClutchSpec,
    RollerSpec,
    TorqueConverterSpec,
    TransmissionSpec,
)

# A representative close-ratio 6-speed manual + final drive, in the same
# ballpark as a MK7 GTI/340i-class compact performance car -- not pulled
# from one specific factory spec sheet, but realistic enough that gear
# spacing, launch RPM and top-gear cruise rpm all behave like a real car's.
TRANSMISSION_6MT = TransmissionSpec(
    name="6-speed manual",
    gear_ratios=(3.36, 2.09, 1.47, 1.14, 1.00, 0.80),
    final_drive_ratio=3.94,
    shift_time_s=0.25,
)

# Sized with real headroom over the EA888/LS2 stock outputs (torque in the
# 300-450Nm class); close to its limit against the B58's ~514Nm peak, so a
# WOT pull on that engine can genuinely slip the clutch rather than always
# locking solid -- a real-world "this clutch can't quite hold this engine"
# scenario, not a bug.
CLUTCH_PERFORMANCE = ClutchSpec(
    name="Performance organic/kevlar clutch",
    max_static_torque_nm=550.0,
)

# A single roller/drum representing the road: physical drum inertia
# (~large steel roller) plus a typical compact-performance-car curb weight
# reflected into the roller's own rotational inertia (see
# RollerSpec's docstring). Every car shares the same physical roller/curb
# weight -- only driven_axle_weight_fraction changes below, per drivetrain
# layout (see CarSpec.drivetrain_layout/ROLLER_BY_DRIVETRAIN_LAYOUT), so a
# grip difference between cars is provably just that one number, not a
# hidden difference in mass or drum inertia too.
#
# RWD is the unmodified baseline (0.5 -- roughly what a rear-biased-under-
# acceleration 2WD car actually launches on). FWD launches on meaningfully
# less than that: accelerating transfers weight rearward, off the driven
# (front) axle, right when it needs grip most -- 0.40 here, a real-world
# "why FWD hatchbacks chirp the tires off the line" number. AWD launches on
# effectively the whole car: both axles are putting power down into this
# same single-tire model at once, so nearly all the car's weight
# contributes to traction -- 0.95 (not a literal 1.0, leaving a little room
# for real-world imperfect front/rear torque split).
ROLLER_RWD = RollerSpec(
    name="Standard single-roller chassis dyno (RWD)",
    radius_m=0.25,
    inertia_kgm2=80.0,
    vehicle_mass_kg=1500.0,
    parasitic_torque_nm=15.0,
    driven_axle_weight_fraction=0.50,
)
ROLLER_FWD = replace(
    ROLLER_RWD, name="Standard single-roller chassis dyno (FWD)", driven_axle_weight_fraction=0.40,
)
ROLLER_AWD = replace(
    ROLLER_RWD, name="Standard single-roller chassis dyno (AWD)", driven_axle_weight_fraction=0.95,
)

# CarSpec.drivetrain_layout -> the RollerSpec DynoSession picks for it (see
# DynoSession._build_loop()). Every car with the same layout shares the
# exact same roller -- there's nothing per-car about traction beyond which
# of these three a car's own drivetrain_layout points at.
ROLLER_BY_DRIVETRAIN_LAYOUT = {
    "fwd": ROLLER_FWD,
    "rwd": ROLLER_RWD,
    "awd": ROLLER_AWD,
}

# Tuned against the EA888/IS20 (idle creep settles ~795rpm from an 900rpm
# idle, WOT stall speed ~2260rpm, both realistic for a compact turbo car) --
# see core/torque_converter.py for what each field actually does physically.
TORQUE_CONVERTER_STANDARD = TorqueConverterSpec(
    name="Standard 3-element torque converter",
    capacity_nm_per_rads2=0.0055,
    stall_torque_ratio=2.0,
    coupling_speed_ratio=0.88,
    lockup_capacity_nm=400.0,
)

TRANSMISSION_AUTO_6SPEED = AutomaticTransmissionSpec(
    name="6-speed automatic (Aisin-class)",
    gear_ratios=(3.36, 2.09, 1.47, 1.14, 1.00, 0.80),
    final_drive_ratio=3.94,
    torque_converter=TORQUE_CONVERTER_STANDARD,
    shift_time_s=0.5,
)

TRANSMISSION_CHOICES = {
    "manual_6speed": (TRANSMISSION_6MT, "6-Speed Manual"),
    "auto_6speed": (TRANSMISSION_AUTO_6SPEED, "6-Speed Automatic (Aisin-class)"),
}
