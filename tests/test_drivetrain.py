from math import pi

import pytest

from engine_sim.core.clutch import Clutch, couple_two_inertias
from engine_sim.core.drivetrain import Drivetrain
from engine_sim.core.tire import Tire
from engine_sim.presets import (
    COMPOUND_STREET,
    ROLLER_STANDARD,
    TIRE_STREET,
    TRANSMISSION_6MT,
)
from engine_sim.specs import ClutchSpec, TireSpec


# --- Tire ------------------------------------------------------------------

def test_tire_slip_ratio_zero_when_speeds_match():
    tire = Tire(TIRE_STREET)
    assert tire.slip_ratio(wheel_surface_speed_mps=20.0, road_surface_speed_mps=20.0) == pytest.approx(0.0)


def test_tire_slip_ratio_zero_at_rest_no_div_by_zero():
    tire = Tire(TIRE_STREET)
    assert tire.slip_ratio(wheel_surface_speed_mps=0.0, road_surface_speed_mps=0.0) == pytest.approx(0.0)


def test_tire_friction_rises_linearly_to_peak():
    """friction_coefficient must be a straight line from 0 at zero slip to
    peak_mu at slip_ratio_at_peak -- pin the halfway point, not just the
    endpoints, which a step function could also satisfy."""
    tire = Tire(TIRE_STREET)
    s_peak = TIRE_STREET.compound.slip_ratio_at_peak
    half_slip_mu = tire.friction_coefficient(s_peak / 2.0)
    assert half_slip_mu == pytest.approx(tire.peak_mu * 0.5)
    assert tire.friction_coefficient(s_peak) == pytest.approx(tire.peak_mu)


def test_tire_friction_falls_off_toward_sliding_mu_beyond_peak():
    tire = Tire(TIRE_STREET)
    at_full_slip = tire.friction_coefficient(1.0)
    assert at_full_slip == pytest.approx(TIRE_STREET.compound.sliding_mu, abs=1e-6)
    # And it's genuinely a falloff, not a cliff -- somewhere between peak and
    # full slip should sit strictly between peak_mu and sliding_mu.
    midpoint = (TIRE_STREET.compound.slip_ratio_at_peak + 1.0) / 2.0
    mid_mu = tire.friction_coefficient(midpoint)
    assert tire.spec.compound.sliding_mu < mid_mu < tire.peak_mu


def test_tire_friction_symmetric_for_negative_slip():
    """Braking (negative slip) should deliver the same magnitude of grip as
    the equivalent positive (driving) slip -- only the force direction
    differs, not the friction curve itself."""
    tire = Tire(TIRE_STREET)
    assert tire.friction_coefficient(-0.05) == pytest.approx(tire.friction_coefficient(0.05))


def test_tire_width_above_reference_increases_grip():
    wide = TireSpec(
        name="wide", radius_m=0.316, width_mm=300.0, compound=COMPOUND_STREET,
        reference_width_mm=225.0, width_grip_sensitivity=0.15,
    )
    narrow = TireSpec(
        name="narrow", radius_m=0.316, width_mm=150.0, compound=COMPOUND_STREET,
        reference_width_mm=225.0, width_grip_sensitivity=0.15,
    )
    assert Tire(wide).peak_mu > COMPOUND_STREET.peak_mu > Tire(narrow).peak_mu


def test_tire_force_direction_follows_slip_sign():
    tire = Tire(TIRE_STREET)
    driving = tire.tick(wheel_omega_rad_s=10.0, road_omega_rad_s=5.0, road_radius_m=0.3, normal_force_n=4000.0)
    braking = tire.tick(wheel_omega_rad_s=5.0, road_omega_rad_s=10.0, road_radius_m=0.3, normal_force_n=4000.0)
    assert driving.longitudinal_force_n > 0.0
    assert braking.longitudinal_force_n < 0.0


def test_tire_force_capped_by_mu_times_normal_load():
    tire = Tire(TIRE_STREET)
    reading = tire.tick(wheel_omega_rad_s=100.0, road_omega_rad_s=0.0, road_radius_m=0.3, normal_force_n=4000.0)
    assert reading.longitudinal_force_n == pytest.approx(reading.mu * 4000.0)


# --- Clutch / couple_two_inertias ------------------------------------------

def test_couple_slips_when_speeds_differ_regardless_of_torque_balance():
    """Two rigid bodies at genuinely different speeds cannot be 'locked' no
    matter how much capacity the coupling has -- this is the actual bug this
    project hit during development (a fresh launch was reported as
    instantly 'locked' from a pure torque balance, crashing engine rpm to 0
    in well under a second)."""
    torque, locked = couple_two_inertias(
        omega_1=90.0, torque_1_nm=50.0, inertia_1_kgm2=0.18,
        omega_2=0.0, torque_2_nm=10.0, inertia_2_kgm2=0.01,
        capacity_nm=550.0,
    )
    assert not locked
    assert torque == pytest.approx(550.0)  # capacity, signed toward the slower side


def test_couple_slip_direction_drags_slower_side_up():
    torque, locked = couple_two_inertias(
        omega_1=0.0, torque_1_nm=0.0, inertia_1_kgm2=1.0,
        omega_2=50.0, torque_2_nm=0.0, inertia_2_kgm2=1.0,
        capacity_nm=100.0,
    )
    assert not locked
    assert torque == pytest.approx(-100.0)  # side 1 is slower -- torque pulls it up (negative on this convention)


def test_couple_locks_when_synced_and_within_capacity():
    """Pinned locked-condition formula: Tc = (J2*T1 + J1*T2) / (J1 + J2)."""
    torque, locked = couple_two_inertias(
        omega_1=100.0, torque_1_nm=200.0, inertia_1_kgm2=0.18,
        omega_2=100.0, torque_2_nm=50.0, inertia_2_kgm2=0.02,
        capacity_nm=500.0,
    )
    expected = (0.02 * 200.0 + 0.18 * 50.0) / (0.18 + 0.02)
    assert locked
    assert torque == pytest.approx(expected)


def test_couple_breaks_loose_again_when_synced_but_capacity_insufficient():
    torque, locked = couple_two_inertias(
        omega_1=100.0, torque_1_nm=1000.0, inertia_1_kgm2=0.18,
        omega_2=100.0, torque_2_nm=0.0, inertia_2_kgm2=0.02,
        capacity_nm=50.0,
    )
    assert not locked
    assert torque == pytest.approx(50.0)  # capped at capacity, signed like the (huge) required torque


def test_couple_without_dt_applies_full_slip_torque_even_if_it_would_overshoot():
    """Backward-compatible default: omitting dt keeps the exact pre-fix
    behavior, even in a case that (with dt given) would be recognized as
    about to overshoot the sync point."""
    torque, locked = couple_two_inertias(
        omega_1=10.0, torque_1_nm=0.0, inertia_1_kgm2=1.0,
        omega_2=8.0, torque_2_nm=0.0, inertia_2_kgm2=1.0,
        capacity_nm=100.0,
    )
    assert not locked
    assert torque == pytest.approx(100.0)


def test_couple_with_dt_prevents_overshoot_chatter_at_the_crossing():
    """Regression test for a real bug found during development: a large
    capacity applied to small, closely-matched inertias can make one full
    step of slip torque overshoot *past* the sync point (omega_diff crosses
    zero and comes out the other side) -- next step's sign flips too, and it
    never converges, chattering between +capacity and -capacity forever
    (verified directly: a clutch dump from high rpm produced a torque
    reading flipping between +1500Nm and -1500Nm tick to tick). Passing dt
    predicts this and falls through to the locked-torque check instead --
    same numbers as the test above, but with dt=0.02 (chosen so the full
    slip torque would swing omega_diff from +2.0 to -2.0, a clean
    overshoot) it must land on the locked result instead."""
    torque, locked = couple_two_inertias(
        omega_1=10.0, torque_1_nm=0.0, inertia_1_kgm2=1.0,
        omega_2=8.0, torque_2_nm=0.0, inertia_2_kgm2=1.0,
        capacity_nm=100.0, dt=0.02,
    )
    assert locked
    assert torque == pytest.approx(0.0)  # required = (1*0 + 1*0)/(1+1) = 0, well within capacity


def test_couple_two_inertias_rejects_nonpositive_inertia():
    with pytest.raises(ValueError):
        couple_two_inertias(0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0)


def test_clutch_capacity_scales_with_engagement_and_clamps():
    clutch = Clutch(ClutchSpec(name="test", max_static_torque_nm=400.0))
    clutch.engagement = 0.5
    assert clutch.capacity_nm() == pytest.approx(200.0)
    clutch.engagement = 1.5  # out of range -- must clamp, not extrapolate past full capacity
    assert clutch.capacity_nm() == pytest.approx(400.0)
    clutch.engagement = -0.5
    assert clutch.capacity_nm() == pytest.approx(0.0)


# --- Drivetrain --------------------------------------------------------

def _drivetrain(clutch_capacity_nm: float = 550.0) -> Drivetrain:
    clutch_spec = ClutchSpec(name="test clutch", max_static_torque_nm=clutch_capacity_nm)
    return Drivetrain(TRANSMISSION_6MT, clutch_spec, TIRE_STREET, ROLLER_STANDARD)


def test_drivetrain_starts_in_neutral():
    dt_train = _drivetrain()
    assert dt_train.gear == 0
    assert dt_train._overall_ratio == 0.0


def test_integrate_wheel_lands_at_zero_slip_instead_of_overshooting_past_it():
    """Regression test for a real bug found during development: the wheel's
    tiny inertia meant a single sub-step's alpha could jump straight through
    the zero-slip crossing (wheel surface speed == roller surface speed)
    into meaningful slip the *other* direction, and since tire force flips
    sign there, that overshoot got kicked back just as hard next sub-step --
    an oscillation that never settled (verified directly: wheel speed
    cycling through the same handful of values every few sub-steps, visible
    on the dyno graph as a "1500Nm" reading flipping to "-1500Nm" and back).
    A naive clamp (just floor at 0) doesn't fix this -- it has to land AT
    the road-matching speed, not overshoot past it toward zero either."""
    dt_train = _drivetrain()
    dt_train.omega_wheel = 10.0
    dt_train.omega_roller = 5.0
    # A deliberately huge negative alpha -- enough to send the wheel far
    # past matching the roller's surface speed if applied naively.
    dt_train._integrate_wheel(alpha_wheel=-1.0e6, sub_dt=0.01)
    expected_wheel_omega = (dt_train.omega_roller * ROLLER_STANDARD.radius_m) / TIRE_STREET.radius_m
    assert dt_train.omega_wheel == pytest.approx(expected_wheel_omega)
    assert dt_train.omega_wheel > 0.0  # not just floored at 0 -- landed at the actual crossing point


def test_integrate_wheel_applies_normally_when_no_crossing_is_predicted():
    """Counterpoint to the above -- a gentle alpha that doesn't cross the
    sync point should integrate exactly as plain Euler would, unclamped."""
    dt_train = _drivetrain()
    dt_train.omega_wheel = 10.0
    dt_train.omega_roller = 0.0
    dt_train._integrate_wheel(alpha_wheel=1.0, sub_dt=0.01)
    assert dt_train.omega_wheel == pytest.approx(10.01)


def test_request_shift_clamps_to_valid_gear_range():
    dt_train = _drivetrain()
    dt_train.request_shift(-5)  # can't go below neutral
    assert dt_train.gear == 0
    for _ in range(dt_train.max_gear + 5):
        dt_train.request_shift(1)
        dt_train.tick(dt=1.0, omega_engine_rad_s=100.0, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    assert dt_train.gear == dt_train.max_gear


def test_request_shift_ignored_while_already_shifting():
    """Regression guard for a named edge case: a rapid double-tap on the
    shift button mid-ramp must not restart or stack a second shift."""
    dt_train = _drivetrain()
    dt_train.request_shift(1)
    assert dt_train.gear == 1
    assert dt_train.is_shifting
    dt_train.request_shift(1)  # should be ignored -- still mid-shift from the first request
    assert dt_train.gear == 1  # not 2


def test_shift_forces_clutch_open_then_ramps_back_to_engaged():
    dt_train = _drivetrain()
    dt_train.request_shift(1)
    assert dt_train.clutch.engagement == pytest.approx(0.0)

    total = TRANSMISSION_6MT.shift_time_s
    for _ in range(int(total / 0.01) + 2):
        dt_train.tick(dt=0.01, omega_engine_rad_s=100.0, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    assert not dt_train.is_shifting
    assert dt_train.clutch.engagement == pytest.approx(1.0)


def test_neutral_wheel_freewheels_with_no_clutch_torque_and_engine_untouched():
    dt_train = _drivetrain()
    dt_train.omega_wheel = 50.0
    reading = dt_train.tick(dt=0.01, omega_engine_rad_s=200.0, engine_torque_nm=300.0, engine_inertia_kgm2=0.18)
    assert reading.clutch_torque_nm == pytest.approx(0.0)
    assert reading.engine_omega_rad_s is None  # caller owns the engine entirely in neutral


def test_wheel_power_is_zero_when_stationary_regardless_of_clutch_torque():
    """Regression test for a real gap found during development: the graph
    was plotting engine crank power, which climbs normally even while the
    car isn't moving at all (a stalled launch, WOT) -- what a real chassis
    dyno actually measures is power delivered to the roller, which must be
    genuinely 0 while vehicle speed is 0, no matter how hard the clutch is
    working."""
    dt_train = _drivetrain()
    dt_train.request_shift(1)
    omega_engine = 900.0 * 2.0 * pi / 60.0
    engine_power_w = 150.0 * omega_engine  # what the engine itself is putting out this instant
    reading = dt_train.tick(dt=0.01, omega_engine_rad_s=omega_engine, engine_torque_nm=150.0, engine_inertia_kgm2=0.18)
    # One outer tick's worth of sub-stepped acceleration from a dead stop is
    # a genuinely tiny (but nonzero) roller speed -- not literally 0, just
    # negligible relative to what the engine itself is making.
    assert dt_train.omega_roller < 1.0
    assert reading.wheel_power_w < engine_power_w * 0.05


def test_wheel_power_matches_tire_force_formula():
    """Pinned formula: wheel_power_w = tire_force * vehicle_speed_mps."""
    dt_train = _drivetrain()
    dt_train.omega_roller = 20.0  # already moving, so there's a real vehicle_speed_mps
    reading = dt_train.tick(dt=0.001, omega_engine_rad_s=100.0, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    vehicle_speed_mps = dt_train.omega_roller * ROLLER_STANDARD.radius_m
    assert reading.wheel_power_w == pytest.approx(reading.tire_force_n * vehicle_speed_mps, rel=1e-2)


def test_wheel_torque_is_power_referenced_to_engine_rpm_not_roller_torque():
    """Regression test for a real bug: wheel_torque_nm used to be
    force-at-the-roller times roller radius -- physically real, but not
    what a chassis dyno actually displays as "wheel torque" (that number
    includes whatever the current gear multiplies it by, up to ~13x in 1st
    gear here, badly inflating the graph -- reported directly as "1300Nm in
    the graph" looking wrong). Real dyno software derives it from wheel
    power divided by engine rpm instead, which power conservation keeps in
    the engine's own ballpark regardless of gear -- pin that formula
    directly rather than the old (now wrong) one."""
    dt_train = _drivetrain()
    dt_train.omega_roller = 20.0
    omega_engine_in = 100.0
    reading = dt_train.tick(dt=0.001, omega_engine_rad_s=omega_engine_in, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    # Neutral (gear 0): Drivetrain never touches the engine's own speed, so
    # the reference rpm for this formula is just what was passed in.
    assert reading.wheel_torque_nm == pytest.approx(reading.wheel_power_w / omega_engine_in)
    # And it must stay in a believable engine-torque ballpark, not the
    # roller-multiplied thousands-of-Nm range the old formula produced.
    assert abs(reading.wheel_torque_nm) < 1000.0


def test_launch_from_stop_slips_before_locking():
    """A clutch launch must start slipping (large speed mismatch between the
    idling engine and the stationary wheel/wheel-referred gearbox input) and
    only lock once they've actually converged -- never an instant lock."""
    dt_train = _drivetrain()
    dt_train.request_shift(1)
    idle_omega = 900.0 * 2.0 * pi / 60.0

    first = dt_train.tick(dt=0.01, omega_engine_rad_s=idle_omega, engine_torque_nm=60.0, engine_inertia_kgm2=0.18)
    assert not first.clutch_locked

    locked_eventually = False
    omega_engine = idle_omega
    for _ in range(2000):
        reading = dt_train.tick(dt=0.01, omega_engine_rad_s=omega_engine, engine_torque_nm=80.0, engine_inertia_kgm2=0.18)
        omega_engine = reading.engine_omega_rad_s
        if reading.clutch_locked:
            locked_eventually = True
            break
    assert locked_eventually


def test_clutch_too_weak_for_engine_never_locks():
    """A clutch sized far below what the load demands should stay in
    controlled slip indefinitely, not eventually snap to locked -- models a
    real underpowered/worn clutch that can never fully hold the engine."""
    dt_train = _drivetrain(clutch_capacity_nm=5.0)  # deliberately far too weak
    dt_train.request_shift(1)
    dt_train.omega_wheel = 0.0
    omega_engine = 900.0 * 2.0 * pi / 60.0
    ever_locked = False
    for _ in range(1000):
        reading = dt_train.tick(dt=0.01, omega_engine_rad_s=omega_engine, engine_torque_nm=150.0, engine_inertia_kgm2=0.18)
        omega_engine = reading.engine_omega_rad_s
        ever_locked = ever_locked or reading.clutch_locked
    assert not ever_locked


def test_wheel_and_engine_speed_track_the_gear_ratio_once_locked():
    dt_train = _drivetrain()
    dt_train.request_shift(1)
    ratio = TRANSMISSION_6MT.gear_ratios[0] * TRANSMISSION_6MT.final_drive_ratio
    omega_engine = 900.0 * 2.0 * pi / 60.0
    reading = None
    for _ in range(3000):
        reading = dt_train.tick(dt=0.01, omega_engine_rad_s=omega_engine, engine_torque_nm=90.0, engine_inertia_kgm2=0.18)
        omega_engine = reading.engine_omega_rad_s
        if reading.clutch_locked:
            break
    assert reading.clutch_locked
    assert omega_engine == pytest.approx(ratio * dt_train.omega_wheel, rel=1e-2)


def test_vehicle_speed_derived_from_roller_surface_speed():
    dt_train = _drivetrain()
    dt_train.omega_roller = 40.0
    reading = dt_train.tick(dt=0.001, omega_engine_rad_s=100.0, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    assert reading.vehicle_speed_kmh == pytest.approx(40.0 * ROLLER_STANDARD.radius_m * 3.6, rel=0.05)


def test_aero_drag_decelerates_roller_at_high_speed_with_no_drive_force():
    dt_train = _drivetrain()
    dt_train.omega_roller = 90.0  # a genuinely high roller speed
    before = dt_train.omega_roller
    # Neutral, wheel at rest -- no tire force reaches the roller worth
    # mentioning at this wheel speed, so drag should be the dominant effect.
    dt_train.tick(dt=0.5, omega_engine_rad_s=100.0, engine_torque_nm=0.0, engine_inertia_kgm2=0.18)
    assert dt_train.omega_roller < before
