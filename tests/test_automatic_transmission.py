import pytest

from engine_sim.core.automatic_drivetrain import AutomaticDrivetrain
from engine_sim.core.ecu import ECU
from engine_sim.core.engine import ParametricEngine
from engine_sim.core.torque_converter import TorqueConverter
from engine_sim.core.turbo import Turbo
from engine_sim.presets import EA888_GEN3_IS20, ROLLER_STANDARD, TIRE_STREET, TURBO_IS20
from engine_sim.specs import AutomaticTransmissionSpec, ClutchSpec, TorqueConverterSpec
from engine_sim.units import rad_s_to_rpm, rpm_to_rad_s


def _real_ecu() -> ECU:
    return ECU(ParametricEngine(EA888_GEN3_IS20), Turbo(TURBO_IS20, firing_order_length=4))


def _tc_spec(**overrides) -> TorqueConverterSpec:
    defaults = dict(
        name="test tc",
        capacity_nm_per_rads2=0.0055,
        stall_torque_ratio=2.0,
        coupling_speed_ratio=0.88,
        lockup_capacity_nm=400.0,
    )
    defaults.update(overrides)
    return TorqueConverterSpec(**defaults)


def _auto_spec(**overrides) -> AutomaticTransmissionSpec:
    defaults = dict(
        name="test auto",
        gear_ratios=(3.36, 2.09, 1.47, 1.14, 1.00, 0.80),
        final_drive_ratio=3.94,
        torque_converter=_tc_spec(),
    )
    defaults.update(overrides)
    return AutomaticTransmissionSpec(**defaults)


def _clutch_spec(capacity: float = 550.0) -> ClutchSpec:
    return ClutchSpec(name="pack", max_static_torque_nm=capacity)


def _automatic_drivetrain(**auto_overrides) -> AutomaticDrivetrain:
    return AutomaticDrivetrain(_auto_spec(**auto_overrides), _clutch_spec(), TIRE_STREET, ROLLER_STANDARD)


# --- TorqueConverter ---------------------------------------------------

def test_lockup_starts_disengaged():
    """Regression test for a real bug: Clutch.__init__ defaults engagement
    to 1.0 (right for the manual gearbox's dry clutch), but TorqueConverter
    reuses Clutch for its lockup element -- left at that default, a fresh
    session would start with the lockup clutch at full capacity even in 1st
    gear, dragging the engine down hard for ~lockup_release_time_s before
    the ramp unwound it (observed directly: engine rpm crashing from ~900
    to ~110 in the first few ticks of a fresh chassis session)."""
    tc = TorqueConverter(_tc_spec())
    assert tc.lockup_clutch.engagement == pytest.approx(0.0)


def test_torque_ratio_at_stall_equals_stall_torque_ratio():
    tc = TorqueConverter(_tc_spec())
    assert tc.torque_ratio(0.0) == pytest.approx(_tc_spec().stall_torque_ratio)


def test_torque_ratio_at_coupling_point_equals_one():
    spec = _tc_spec()
    tc = TorqueConverter(spec)
    assert tc.torque_ratio(spec.coupling_speed_ratio) == pytest.approx(1.0)


def test_torque_ratio_interpolates_linearly_between():
    spec = _tc_spec()
    tc = TorqueConverter(spec)
    halfway = spec.coupling_speed_ratio / 2.0
    expected = spec.stall_torque_ratio + (1.0 - spec.stall_torque_ratio) * 0.5
    assert tc.torque_ratio(halfway) == pytest.approx(expected)


def test_stall_phase_genuinely_multiplies_torque():
    """The whole point of a torque converter at low speed ratio: turbine
    receives *more* torque than the pump gives up, unlike a plain friction
    coupling which can never multiply."""
    tc = TorqueConverter(_tc_spec())
    omega_pump = rpm_to_rad_s(2000.0)
    pump_reaction, turbine_drive, reading = tc.tick(
        dt=0.001, omega_pump=omega_pump, torque_pump_available_nm=150.0, pump_inertia_kgm2=0.18,
        omega_turbine=0.0, turbine_load_nm=0.0, turbine_inertia_kgm2=0.03, lockup_commanded=False,
    )
    assert reading.speed_ratio == pytest.approx(0.0)
    assert turbine_drive > pump_reaction  # genuine multiplication


def test_capacity_scales_with_pump_speed_squared():
    tc = TorqueConverter(_tc_spec())
    omega_pump = 100.0
    _, _, reading = tc.tick(
        dt=0.001, omega_pump=omega_pump, torque_pump_available_nm=0.0, pump_inertia_kgm2=0.18,
        omega_turbine=0.0, turbine_load_nm=0.0, turbine_inertia_kgm2=0.03, lockup_commanded=False,
    )
    expected = _tc_spec().capacity_nm_per_rads2 * omega_pump * omega_pump
    assert reading.pump_torque_nm == pytest.approx(expected)


def test_coupling_phase_no_longer_multiplies_torque():
    """Once speed_ratio reaches coupling_speed_ratio, a real converter's
    multiplication has ended -- pump and turbine sides of the fluid path
    should carry equal-magnitude torque (a friction-like coupling), not the
    stall phase's multiplied relationship."""
    spec = _tc_spec()
    tc = TorqueConverter(spec)
    omega_pump = 100.0
    omega_turbine = omega_pump * spec.coupling_speed_ratio  # exactly at the boundary
    _, _, reading = tc.tick(
        dt=0.001, omega_pump=omega_pump, torque_pump_available_nm=50.0, pump_inertia_kgm2=0.18,
        omega_turbine=omega_turbine, turbine_load_nm=10.0, turbine_inertia_kgm2=0.03, lockup_commanded=False,
    )
    assert reading.torque_ratio == pytest.approx(1.0)
    assert reading.pump_torque_nm == pytest.approx(reading.turbine_torque_nm)


def test_turbine_cannot_run_away_past_pump_speed():
    """Regression test for a real bug: once in the coupling phase, a flat
    torque_ratio=1 had no mechanism to stop the turbine actually outrunning
    the pump -- the car kept accelerating in 1st gear forever with engine
    rpm pinned at a stall-equivalent plateau, never reaching the upshift
    threshold. If the turbine is already faster than the pump, the fluid
    coupling must react by decelerating the turbine (or at least not
    continue accelerating it) -- not keep feeding it a flat positive
    torque regardless."""
    spec = _tc_spec()
    tc = TorqueConverter(spec)
    omega_pump = 200.0
    omega_turbine = omega_pump * 1.05  # turbine already ahead of the pump
    _, turbine_drive, reading = tc.tick(
        dt=0.0002, omega_pump=omega_pump, torque_pump_available_nm=50.0, pump_inertia_kgm2=0.18,
        omega_turbine=omega_turbine, turbine_load_nm=0.0, turbine_inertia_kgm2=0.03, lockup_commanded=False,
    )
    # Speed ratio clamps at 1.0 (still "coupling phase"), but the actual
    # torque transmitted must now oppose the overrun, not add to it.
    assert turbine_drive <= 0.0


def test_lockup_engagement_ramps_toward_commanded_target():
    tc = TorqueConverter(_tc_spec())
    for _ in range(2000):
        tc.tick(
            dt=0.001, omega_pump=300.0, torque_pump_available_nm=50.0, pump_inertia_kgm2=0.18,
            omega_turbine=300.0, turbine_load_nm=10.0, turbine_inertia_kgm2=0.03, lockup_commanded=True,
        )
    assert tc.lockup_clutch.engagement == pytest.approx(1.0, abs=0.02)  # exponential approach, never exactly 1.0

    for _ in range(2000):
        tc.tick(
            dt=0.001, omega_pump=300.0, torque_pump_available_nm=50.0, pump_inertia_kgm2=0.18,
            omega_turbine=300.0, turbine_load_nm=10.0, turbine_inertia_kgm2=0.03, lockup_commanded=False,
        )
    assert tc.lockup_clutch.engagement == pytest.approx(0.0, abs=0.02)


def test_fluid_and_lockup_capacities_dont_fight_in_the_coupling_phase():
    """Regression test for a real bug found during development: at/above
    coupling_speed_ratio, the fluid path's own residual capacity and the
    lockup clutch's capacity were resolved as two independent
    couple_two_inertias calls, each reasoning as if it were the only torque
    acting between pump and turbine -- so they fought, and the reported
    torque/lock state oscillated wildly every tick at a steady cruise
    instead of settling. Hold pump/turbine already synced (coupling phase)
    with lockup commanded, and confirm consecutive ticks agree with each
    other instead of alternating."""
    tc = TorqueConverter(_tc_spec())
    omega = 300.0
    readings = []
    for _ in range(50):
        _, _, reading = tc.tick(
            dt=0.001, omega_pump=omega, torque_pump_available_nm=50.0, pump_inertia_kgm2=0.18,
            omega_turbine=omega, turbine_load_nm=45.0, turbine_inertia_kgm2=0.03, lockup_commanded=True,
        )
        readings.append(reading)
    # Once settled (skip the first few ticks while lockup engagement is
    # still ramping in), locked state must be stable, not flapping.
    settled = readings[10:]
    assert all(r.lockup_locked for r in settled) or not any(r.lockup_locked for r in settled)


# --- AutomaticDrivetrain -------------------------------------------------

def test_starts_in_first_gear_not_neutral():
    """Unlike the manual gearbox, an automatic has no driver-selected
    neutral -- 'Drive' from a stop is the resting state."""
    dt_train = _automatic_drivetrain()
    assert dt_train.gear == 1


def test_shift_never_fully_disengages_the_clutch_pack():
    """An automatic's clutch-to-clutch shift keeps some torque path alive
    throughout (the incoming gear's element overlaps the outgoing one) --
    unlike the manual gearbox's hard declutch-to-0, engagement should never
    reach 0 during an automatic shift."""
    dt_train = _automatic_drivetrain()
    dt_train.request_shift(1)
    assert dt_train.clutch.engagement == pytest.approx(dt_train._SHIFT_OVERLAP_FLOOR)
    assert dt_train.clutch.engagement > 0.0

    total = dt_train.transmission_spec.shift_time_s
    min_engagement = dt_train.clutch.engagement
    for _ in range(int(total / 0.01) + 2):
        dt_train.tick(dt=0.01, omega_engine_rad_s=300.0, engine_torque_nm=50.0, engine_inertia_kgm2=0.18, throttle=0.3)
        min_engagement = min(min_engagement, dt_train.clutch.engagement)
    assert min_engagement >= dt_train._SHIFT_OVERLAP_FLOOR - 1e-9
    assert not dt_train.is_shifting
    assert dt_train.clutch.engagement == pytest.approx(1.0)


def test_request_shift_ignored_while_already_shifting():
    dt_train = _automatic_drivetrain()
    dt_train.request_shift(1)
    assert dt_train.gear == 2
    dt_train.request_shift(1)  # still mid-shift from the first request -- ignored
    assert dt_train.gear == 2


def test_request_shift_is_noop_past_top_gear():
    dt_train = _automatic_drivetrain()
    dt_train.gear = dt_train.max_gear
    dt_train.request_shift(1)
    assert dt_train.gear == dt_train.max_gear
    assert not dt_train.is_shifting


def test_reset_returns_to_gear_one():
    dt_train = _automatic_drivetrain()
    dt_train.gear = 4
    dt_train.omega_turbine = 100.0
    dt_train.reset()
    assert dt_train.gear == 1
    assert dt_train.omega_turbine == pytest.approx(0.0)


def _drive_with_real_engine(dt_train, throttle, ticks, idle_rpm=900.0):
    ecu = _real_ecu()
    rpm = idle_rpm
    reading = None
    for _ in range(ticks):
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=throttle)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=throttle,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
    return reading, rpm


def test_idle_creep_settles_without_a_stall_like_crash():
    """Regression test for the lockup-init bug: a fresh session idling in
    Drive must settle near a stable balance rpm without first crashing well
    below any believable idle."""
    dt_train = _automatic_drivetrain()
    min_rpm = 900.0
    reading, rpm = None, 900.0
    ecu = _real_ecu()
    for _ in range(300):
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=0.0)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=0.0,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
        min_rpm = min(min_rpm, rpm)
    assert min_rpm > 500.0  # never crashes toward a stall
    assert abs(rpm - 900.0) < 200.0  # settles in a believable idle-ish band
    assert reading.vehicle_speed_kmh > 0.0  # genuinely creeping forward


def test_auto_upshifts_near_wot_threshold():
    dt_train = _automatic_drivetrain()
    reading, rpm = _drive_with_real_engine(dt_train, throttle=1.0, ticks=150)
    assert reading.gear >= 2
    assert rpm < AutomaticTransmissionSpec(
        name="t", gear_ratios=(1,), final_drive_ratio=1, torque_converter=_tc_spec(),
    ).upshift_rpm_wot + 500.0  # sanity: shifted somewhere near the configured ceiling, not way past it


def test_upshift_ceiling_clamps_below_a_tight_rev_limiter():
    """Regression test for a real bug: AutomaticTransmissionSpec's
    upshift_rpm_wot (6200 by default) is one fixed number shared by every
    engine choice in the Godot UI, not calibrated per engine -- paired with
    the B58 preset (redline 6000, rev limiter cuts at 5850, both below
    6200), WOT rpm never reached the shift map's own upshift ceiling at
    all, so the car just bounced off the rev limiter in 1st gear forever
    (verified directly against the real B58/auto_6speed DynoSession combo).
    Passing a tight rev_limiter_rpm here reproduces the same shape without
    needing a second engine spec: the drivetrain must still find a way to
    upshift out of 1st well before an engine limiter that's below the
    spec's own configured ceiling."""
    dt_train = _automatic_drivetrain()
    ecu = _real_ecu()
    tight_rev_limiter_rpm = 5850.0  # below the default upshift_rpm_wot=6200
    rpm = 900.0
    max_gear_seen = dt_train.gear
    for _ in range(3000):
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=1.0)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0, rev_limiter_rpm=tight_rev_limiter_rpm,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
        max_gear_seen = max(max_gear_seen, reading.gear)
        if max_gear_seen >= 2:
            break
    assert max_gear_seen >= 2, "never upshifted out of 1st gear against a rev limiter below the spec's own ceiling"


def test_never_shifts_below_first_gear():
    dt_train = _automatic_drivetrain()
    _drive_with_real_engine(dt_train, throttle=0.0, ticks=500)
    assert dt_train.gear >= 1


def test_kickdown_downshifts_when_flooring_it_at_cruise():
    """A sudden floor-it from a light-throttle cruise (in a tall gear, low
    rpm for that gear) should trigger an immediate downshift -- real
    automatic kickdown behavior."""
    dt_train = _automatic_drivetrain()
    dt_train.gear = 6
    dt_train.omega_wheel = 60.0
    dt_train.omega_turbine = 60.0 * dt_train._overall_ratio
    dt_train.omega_roller = 60.0 * TIRE_STREET.radius_m / ROLLER_STANDARD.radius_m
    low_cruise_rpm = rad_s_to_rpm(dt_train.omega_turbine)

    dt_train._decide_shift(throttle=1.0, rpm=low_cruise_rpm)
    assert dt_train.is_shifting
    assert dt_train.gear < 6


def test_ideal_gear_falls_back_to_top_gear_when_no_gear_fits_the_ceiling():
    """At an extreme enough wheel speed, even top gear's implied rpm can
    exceed the upshift ceiling -- there's no gear left to pick, so it must
    fall back to the tallest one available rather than raise an error or
    return something out of range."""
    dt_train = _automatic_drivetrain()
    dt_train.omega_wheel = 300.0  # an unrealistically high wheel speed
    assert dt_train._ideal_gear(throttle=0.0) == dt_train.max_gear


def test_kickdown_can_skip_multiple_gears():
    """Flooring it from a tall gear at low speed should jump straight to
    the right gear for real acceleration, not step down one gear at a time
    like a driver rowing a manual shifter."""
    dt_train = _automatic_drivetrain()
    dt_train.gear = 6
    dt_train.omega_wheel = 20.0  # low speed for 6th gear -- a hard kickdown wants several gears down
    dt_train.omega_turbine = 20.0 * dt_train._overall_ratio
    dt_train.omega_roller = 20.0 * TIRE_STREET.radius_m / ROLLER_STANDARD.radius_m
    low_speed_rpm = rad_s_to_rpm(dt_train.omega_turbine)

    dt_train._decide_shift(throttle=1.0, rpm=low_speed_rpm)
    assert dt_train.is_shifting
    assert dt_train.gear <= 4  # skipped past at least one intermediate gear


def test_easing_off_can_skip_multiple_upshifts():
    """Lifting to a light throttle while already spinning fast in a low
    gear should jump straight to a tall cruising gear, not creep up one
    gear at a time."""
    dt_train = _automatic_drivetrain()
    dt_train.gear = 1
    dt_train.omega_wheel = 60.0  # a speed that's comfortably cruise-able in a much taller gear
    dt_train.omega_turbine = 60.0 * dt_train._overall_ratio
    dt_train.omega_roller = 60.0 * TIRE_STREET.radius_m / ROLLER_STANDARD.radius_m
    high_rpm_in_1st = rad_s_to_rpm(dt_train.omega_turbine)

    dt_train._decide_shift(throttle=0.05, rpm=high_rpm_in_1st)
    assert dt_train.is_shifting
    assert dt_train.gear >= 3  # skipped past at least one intermediate gear


def test_shift_torque_reduction_is_a_smooth_dip_not_a_held_cut():
    """The cut must be a continuous dip -- zero at both endpoints, peaking
    at the shift's midpoint -- not a hold-near-max-then-release-late shape
    (an earlier version did this; it produced a real torque *step* right as
    the clutch-pack overlap was still ramping in, reading as harsh/jerky
    even though the clutch engagement itself was already smooth)."""
    dt_train = _automatic_drivetrain()
    dt_train.request_shift(1)
    assert dt_train.shift_torque_reduction_fraction() == pytest.approx(0.0)  # zero at the very start, not the peak

    total = dt_train.transmission_spec.shift_time_s
    dt_train.tick(dt=total * 0.5, omega_engine_rad_s=300.0, engine_torque_nm=50.0, engine_inertia_kgm2=0.18, throttle=1.0)
    assert dt_train.shift_torque_reduction_fraction() == pytest.approx(dt_train._MAX_SHIFT_TORQUE_REDUCTION, abs=0.02)

    dt_train.tick(dt=total * 0.5, omega_engine_rad_s=300.0, engine_torque_nm=50.0, engine_inertia_kgm2=0.18, throttle=1.0)
    assert not dt_train.is_shifting
    assert dt_train.shift_torque_reduction_fraction() == pytest.approx(0.0)  # zero again by the end


def test_no_gear_hunting_under_sustained_wot():
    """Regression test for a real bug: the shift torque cut made rpm fall
    fast enough that, right as a shift completed, rpm had already crossed
    back below the downshift threshold for the gear just left -- triggering
    an immediate reversal, then another, hunting continuously instead of
    settling (verified directly: 1<->2 alternating under sustained WOT).
    Under constant full throttle, gear must never decrease."""
    dt_train = _automatic_drivetrain()
    ecu = _real_ecu()
    rpm = 900.0
    max_gear_seen = dt_train.gear
    for _ in range(3000):
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=1.0)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
        assert reading.gear >= max_gear_seen, f"gear dropped from {max_gear_seen} to {reading.gear} under sustained WOT"
        max_gear_seen = reading.gear
        if reading.gear >= 4:
            break
    assert max_gear_seen >= 4


def test_wheel_and_slip_never_sign_flip_chatter_during_launch():
    """Same regression class as the manual gearbox's chatter fix -- a WOT
    launch must transition smoothly, no tick-to-tick slip sign flips."""
    dt_train = _automatic_drivetrain()
    ecu = _real_ecu()
    rpm = 900.0
    prev_slip = None
    for _ in range(500):
        er = ecu.tick(dt=0.01, rpm=rpm, throttle=1.0)
        reading = dt_train.tick(
            dt=0.01, omega_engine_rad_s=rpm_to_rad_s(rpm), engine_torque_nm=er.engine.net_torque_nm,
            engine_inertia_kgm2=0.18, throttle=1.0,
        )
        rpm = rad_s_to_rpm(reading.engine_omega_rad_s)
        if prev_slip is not None and abs(prev_slip) > 0.2 and abs(reading.slip_ratio) > 0.2:
            assert (reading.slip_ratio > 0) == (prev_slip > 0)
        prev_slip = reading.slip_ratio
