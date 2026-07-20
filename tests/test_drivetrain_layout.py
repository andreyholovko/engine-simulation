"""Tests for CarSpec.drivetrain_layout (fwd/rwd/awd) and how it changes real
launch grip -- see RollerSpec.driven_axle_weight_fraction/presets.
ROLLER_BY_DRIVETRAIN_LAYOUT for what the layout actually controls, and
DynoSession._build_loop() for how a selected car's layout picks its roller.
"""

import pytest

from engine_sim import DynoSession
from engine_sim.core.drivetrain import Drivetrain
from engine_sim.core.ecu import ECU
from engine_sim.core.engine import ParametricEngine
from engine_sim.core.turbo import Turbo
from engine_sim.presets import (
    CAR_CHOICES,
    CLUTCH_PERFORMANCE,
    EA888_GEN3_IS20,
    ROLLER_AWD,
    ROLLER_BY_DRIVETRAIN_LAYOUT,
    ROLLER_FWD,
    ROLLER_RWD,
    TIRE_STREET,
    TRANSMISSION_6MT,
    TURBO_IS20,
)
from engine_sim.units import rad_s_to_rpm, rpm_to_rad_s

ROLLER_FIELDS_OTHER_THAN_GRIP = (
    "radius_m", "inertia_kgm2", "vehicle_mass_kg", "parasitic_torque_nm", "drag_coefficient", "frontal_area_m2",
    "downforce_coefficient",
)


# --- config-level: the CAR_CHOICES/ROLLER_BY_DRIVETRAIN_LAYOUT data itself ---

def test_every_car_has_a_real_drivetrain_layout():
    for key, car in CAR_CHOICES.items():
        assert car.drivetrain_layout in ("fwd", "rwd", "awd"), key


def test_the_three_cars_cover_all_three_layouts():
    """Not incidental -- CAR_CHOICES' own docstring says this is deliberate:
    one of each real layout, so fwd/rwd/awd are all actually exercised by
    the default car lineup instead of landing on the same layout twice."""
    layouts = {car.drivetrain_layout for car in CAR_CHOICES.values()}
    assert layouts == {"fwd", "rwd", "awd"}


def test_mk7_gti_is_fwd():
    """VW never sold a US-market Mk7 GTI with a driven rear axle."""
    assert CAR_CHOICES["mk7_gti"].drivetrain_layout == "fwd"


def test_f30_340i_is_awd():
    """Specifically the xDrive variant (see CAR_CHOICES/CarSpec.name) --
    the real factory AWD version of the same B58B30 the base RWD 340i
    also uses, picked deliberately so the three cars don't land on rwd
    twice (see test_the_three_cars_cover_all_three_layouts)."""
    assert CAR_CHOICES["f30_340i"].drivetrain_layout == "awd"
    assert "xDrive" in CAR_CHOICES["f30_340i"].name


def test_c6_corvette_is_rwd():
    """No AWD C6 Corvette generation ever existed."""
    assert CAR_CHOICES["c6_corvette"].drivetrain_layout == "rwd"


def test_roller_by_drivetrain_layout_covers_all_three():
    assert set(ROLLER_BY_DRIVETRAIN_LAYOUT.keys()) == {"fwd", "rwd", "awd"}


def test_grip_ordering_matches_the_real_world_fwd_lt_rwd_lt_awd():
    """The actual requirement, checked directly against the config values
    DynoSession builds from: FWD has less grip than RWD, AWD has more grip
    than RWD."""
    assert ROLLER_FWD.driven_axle_weight_fraction < ROLLER_RWD.driven_axle_weight_fraction
    assert ROLLER_RWD.driven_axle_weight_fraction < ROLLER_AWD.driven_axle_weight_fraction


def test_awd_roller_uses_effectively_the_whole_cars_weight():
    """AWD represents both axles driving at once -- close to the full
    vehicle weight, not some intermediate value part-way to RWD."""
    assert ROLLER_AWD.driven_axle_weight_fraction > 0.9


def test_three_roller_variants_share_every_other_physical_property():
    """Only traction should differ between drivetrain layouts -- not drum
    inertia, curb weight, aero, or parasitic drag. If those ever drifted
    apart between layouts, a grip comparison wouldn't actually be isolating
    grip anymore."""
    for field in ROLLER_FIELDS_OTHER_THAN_GRIP:
        assert getattr(ROLLER_FWD, field) == getattr(ROLLER_RWD, field) == getattr(ROLLER_AWD, field), field


# --- DynoSession wiring: the right roller actually gets used -------------

def test_selecting_each_car_picks_that_cars_own_roller():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for key, car in CAR_CHOICES.items():
        session.select_car(key)
        expected = ROLLER_BY_DRIVETRAIN_LAYOUT[car.drivetrain_layout]
        assert session.drivetrain.roller_spec.driven_axle_weight_fraction == expected.driven_axle_weight_fraction


def test_constructing_a_session_directly_on_a_non_default_car_uses_the_right_roller():
    """Regression-shaped: car_key has to be set before _build_loop() runs
    the very first time (inside __init__), not just from select_car()
    onward -- otherwise a session constructed directly on a non-default
    car (DynoSession(car_key=...)) would silently build its very first
    chassis loop against the wrong roller."""
    for key, car in CAR_CHOICES.items():
        session = DynoSession(car_key=key)
        session.select_dyno_mode("chassis")
        expected = ROLLER_BY_DRIVETRAIN_LAYOUT[car.drivetrain_layout]
        assert session.drivetrain.roller_spec.driven_axle_weight_fraction == expected.driven_axle_weight_fraction


def test_switching_dyno_mode_preserves_the_current_cars_roller():
    """Round-tripping crank -> chassis -> crank -> chassis must keep using
    the same car's own roller, not silently fall back to some default."""
    session = DynoSession(car_key="f30_340i")
    session.select_dyno_mode("chassis")
    session.select_dyno_mode("crank")
    session.select_dyno_mode("chassis")
    assert session.drivetrain.roller_spec.driven_axle_weight_fraction == pytest.approx(
        ROLLER_AWD.driven_axle_weight_fraction
    )


# --- the actual physics: grip translates into real launch traction -------

def _launch_speed_after_3s(roller_spec) -> float:
    """Identical engine/tire/transmission/launch technique across every
    call -- roller_spec (and so driven_axle_weight_fraction) is the *only*
    thing that varies, isolating grip's own effect from any of the real
    cars' own engine/turbo differences."""
    ecu = ECU(ParametricEngine(EA888_GEN3_IS20), Turbo(TURBO_IS20, firing_order_length=4))
    dt_train = Drivetrain(TRANSMISSION_6MT, CLUTCH_PERFORMANCE, TIRE_STREET, roller_spec)
    dt_train.request_shift(1)
    rpm = 900.0
    reading = None
    for _ in range(300):  # 3s at dt=0.01 -- a real launch's wheelspin phase
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=1.0)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
    return reading.vehicle_speed_kmh


def test_more_grip_launches_faster_holding_everything_else_constant():
    """The actual point of the feature, not just the config numbers: given
    the exact same engine, tire, transmission and WOT launch, more grip
    must produce real, measurably faster acceleration -- less of the
    engine's torque wasted spinning the tire instead of moving the car.
    Verified directly: at 3s in, FWD/RWD/AWD reach ~17.6/22.3/32.6 km/h
    respectively here -- a peak-slip-ratio comparison alone doesn't show
    this cleanly (an initial clutch-dump launch saturates all three near
    the tire's own slip ceiling for an instant), but the speed actually
    covered over the launch does."""
    speed_fwd = _launch_speed_after_3s(ROLLER_FWD)
    speed_rwd = _launch_speed_after_3s(ROLLER_RWD)
    speed_awd = _launch_speed_after_3s(ROLLER_AWD)
    assert speed_fwd < speed_rwd < speed_awd


def test_awd_has_recovered_most_of_its_grip_by_3s_fwd_has_not():
    """A second, independent look at the same launch: by 3s in, AWD's own
    slip ratio should have decayed back down near the tire's real peak-grip
    point (see engine_sim.core.tire), while FWD -- launching on much less
    of the car's weight -- should still be deep in wheelspin."""
    ecu_fwd = ECU(ParametricEngine(EA888_GEN3_IS20), Turbo(TURBO_IS20, firing_order_length=4))
    dt_fwd = Drivetrain(TRANSMISSION_6MT, CLUTCH_PERFORMANCE, TIRE_STREET, ROLLER_FWD)
    dt_fwd.request_shift(1)
    ecu_awd = ECU(ParametricEngine(EA888_GEN3_IS20), Turbo(TURBO_IS20, firing_order_length=4))
    dt_awd = Drivetrain(TRANSMISSION_6MT, CLUTCH_PERFORMANCE, TIRE_STREET, ROLLER_AWD)
    dt_awd.request_shift(1)

    rpm_fwd = rpm_awd = 900.0
    reading_fwd = reading_awd = None
    for _ in range(300):
        er = ecu_fwd.tick(dt=0.01, rpm=rpm_fwd, throttle=1.0)
        reading_fwd = dt_fwd.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm_fwd), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0,
        )
        rpm_fwd = rad_s_to_rpm(reading_fwd.engine_omega_rad_s)

        er = ecu_awd.tick(dt=0.01, rpm=rpm_awd, throttle=1.0)
        reading_awd = dt_awd.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm_awd), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0,
        )
        rpm_awd = rad_s_to_rpm(reading_awd.engine_omega_rad_s)

    assert reading_awd.slip_ratio < 0.2  # essentially gripped up again
    assert reading_fwd.slip_ratio > 0.5  # still well into wheelspin
    assert reading_fwd.slip_ratio > reading_awd.slip_ratio
