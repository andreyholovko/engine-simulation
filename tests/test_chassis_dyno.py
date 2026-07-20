"""DynoSession's chassis-dyno mode: the crank/chassis toggle, gear shifting,
and everything session.py adds on top of core/drivetrain.py to make it a
first-class DynoSession mode alongside the original crank dyno.
"""

import pytest

from engine_sim import DynoSession
from engine_sim.core.automatic_drivetrain import AutomaticDrivetrain
from engine_sim.core.drivetrain import Drivetrain
from engine_sim.core.dyno import ChassisDynoLoop, SimulationLoop


def test_default_session_is_crank_mode():
    session = DynoSession()
    assert session.dyno_mode == "crank"
    assert isinstance(session.loop, SimulationLoop)
    assert session.drivetrain is None
    assert session.current_gear == 0


def test_select_dyno_mode_switches_to_chassis():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    assert session.dyno_mode == "chassis"
    assert isinstance(session.loop, ChassisDynoLoop)
    assert session.drivetrain is not None


def test_select_dyno_mode_rejects_unknown_mode():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_dyno_mode("automatic")


def test_select_dyno_mode_is_noop_when_already_in_that_mode():
    """Switching to chassis, shifting into gear, then 'switching' to chassis
    again (e.g. a UI toggle firing redundantly) must not silently reset an
    in-progress run."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.shift_up()
    drivetrain_before = session.drivetrain
    session.select_dyno_mode("chassis")
    assert session.drivetrain is drivetrain_before
    assert session.current_gear == 1


def test_switching_back_to_crank_clears_drivetrain():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_dyno_mode("crank")
    assert session.drivetrain is None
    assert isinstance(session.loop, SimulationLoop)


def test_shift_up_down_are_noop_outside_chassis_mode():
    session = DynoSession()
    session.shift_up()
    assert session.current_gear == 0


def test_shift_up_and_down_change_gear_in_chassis_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.shift_up()
    assert session.current_gear == 1
    # Advance past the shift ramp before requesting another -- request_shift
    # itself debounces mid-shift (see test_drivetrain.py), which isn't what
    # this test is checking.
    for _ in range(100):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    for _ in range(100):
        session.tick(dt=0.01, throttle_percent=0.0)
    assert session.current_gear == 2
    session.shift_down()
    for _ in range(100):
        session.tick(dt=0.01, throttle_percent=0.0)
    assert session.current_gear == 1


def test_select_car_preserves_chassis_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.shift_up()
    session.select_car("f30_340i")
    assert session.dyno_mode == "chassis"
    assert isinstance(session.loop, ChassisDynoLoop)
    # select_car() rebuilds the drivetrain -- a fresh session, back to
    # neutral, same reset-on-swap convention as every other axis.
    assert session.current_gear == 0


def test_select_turbo_preserves_chassis_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_turbo_by_index(1)
    assert session.dyno_mode == "chassis"
    assert isinstance(session.loop, ChassisDynoLoop)


def test_select_tire_rejects_unknown_key():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_tire("not_a_real_tire")


def test_list_tire_choices_includes_every_preset():
    keys = {key for key, _ in DynoSession.list_tire_choices()}
    assert {"street", "sport", "drag"} <= keys


def test_select_tire_by_index_matches_select_tire_by_key():
    by_index = DynoSession()
    by_index.select_dyno_mode("chassis")
    by_index.select_tire_by_index(2)
    by_key = DynoSession()
    by_key.select_dyno_mode("chassis")
    by_key.select_tire(DynoSession.list_tire_choices()[2][0])
    assert by_index.tire_key == by_key.tire_key == "drag"


def test_select_tire_by_index_rejects_out_of_range():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_tire_by_index(99)


def test_select_tire_while_already_in_chassis_mode_rebuilds_immediately():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.shift_up()
    drivetrain_before = session.drivetrain
    session.select_tire("sport")
    assert session.drivetrain is not drivetrain_before  # rebuilt, not mutated in place
    assert session.drivetrain.tire.spec.name == "245/40R18 sport"
    assert session.current_gear == 0  # rebuilding resets to neutral, same as any other swap


def test_select_tire_remembered_outside_chassis_mode_then_applied_on_switch():
    session = DynoSession()
    session.select_tire("drag")
    assert session.tire_key == "drag"
    assert session.drivetrain is None  # not built yet -- still crank mode
    session.select_dyno_mode("chassis")
    assert session.drivetrain.tire.spec.name == "315/40R18 drag radial"


def test_default_transmission_is_manual():
    session = DynoSession()
    assert session.transmission_key == "manual_6speed"


def test_list_transmission_choices_includes_manual_and_automatic():
    keys = {key for key, _ in DynoSession.list_transmission_choices()}
    assert {"manual_6speed", "auto_6speed"} <= keys


def test_select_transmission_rejects_unknown_key():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_transmission("cvt")


def test_select_transmission_by_index_matches_select_transmission_by_key():
    by_index = DynoSession()
    by_index.select_dyno_mode("chassis")
    by_index.select_transmission_by_index(1)
    by_key = DynoSession()
    by_key.select_dyno_mode("chassis")
    by_key.select_transmission(DynoSession.list_transmission_choices()[1][0])
    assert by_index.transmission_key == by_key.transmission_key == "auto_6speed"


def test_select_transmission_by_index_rejects_out_of_range():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_transmission_by_index(99)


def test_select_automatic_builds_an_automatic_drivetrain():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    assert isinstance(session.drivetrain, AutomaticDrivetrain)
    assert session.current_gear == 1  # automatics start in gear, no neutral


def test_select_manual_builds_a_plain_drivetrain():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    session.select_transmission("manual_6speed")
    assert type(session.drivetrain) is Drivetrain
    assert session.current_gear == 0  # back to neutral


def test_transmission_remembered_outside_chassis_mode_then_applied_on_switch():
    session = DynoSession()
    session.select_transmission("auto_6speed")
    assert session.drivetrain is None  # not built yet -- still crank mode
    session.select_dyno_mode("chassis")
    assert isinstance(session.drivetrain, AutomaticDrivetrain)


def test_shift_buttons_are_noop_on_automatic_transmission():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    session.shift_up()
    session.shift_down()
    assert session.current_gear == 1  # untouched -- automatic shift map owns gear selection


def test_automatic_transmission_auto_upshifts_and_reaches_high_gear():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    snapshot = None
    for _ in range(3000):
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    assert snapshot.gear >= 3  # genuinely climbed through several gears under WOT
    assert snapshot.vehicle_speed_kmh > 50.0


def test_automatic_transmission_cruise_at_partial_throttle_is_stable():
    """Regression test for a real bug: cruising at a steady part-throttle
    in a gear high enough for lockup to engage produced wild tick-to-tick
    oscillation in wheel_torque_nm and clutch_locked (the fluid coupling's
    own capacity and the lockup clutch's capacity fighting each other --
    see TorqueConverter.tick()'s docstring). At a genuinely steady cruise,
    consecutive readings must stay close to each other, not swing by
    hundreds of Nm tick to tick."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    for _ in range(3000):
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
        if snapshot.gear >= 3:
            break

    # Dropping from WOT to 40% throttle can itself trigger a genuine gear
    # change -- and, on a lower-grip car (see CarSpec.drivetrain_layout),
    # more wheelspin during the WOT launch above means gear 3 is reached at
    # a lower real road speed, which can itself sag low enough at 40%
    # throttle to warrant a further real downshift, then a multi-second
    # gradual re-acceleration back up through the gears before things
    # genuinely stop shifting -- verified directly (the default car, FWD,
    # takes ~15s of real sim time to fully settle here). 20s is a generous
    # margin past that, not a tight guess.
    for _ in range(2000):
        session.tick(dt=0.01, throttle_percent=40.0)

    prev_wheel_torque = None
    for _ in range(500):
        snapshot = session.tick(dt=0.01, throttle_percent=40.0)
        if prev_wheel_torque is not None:
            assert abs(snapshot.wheel_torque_nm - prev_wheel_torque) < 100.0
        prev_wheel_torque = snapshot.wheel_torque_nm


def test_switching_engine_preserves_automatic_transmission_choice():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_transmission("auto_6speed")
    session.select_car("f30_340i")
    assert isinstance(session.drivetrain, AutomaticDrivetrain)
    assert session.current_gear == 1


def test_run_power_pull_raises_in_chassis_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    with pytest.raises(ValueError):
        session.run_power_pull()


def test_run_power_pull_still_works_after_visiting_chassis_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_dyno_mode("crank")
    peak = max(session.run_power_pull(), key=lambda s: s.torque_nm)
    assert 272.0 <= peak.torque_nm <= 368.0  # same validated EA888 curve as test_session.py


def test_start_power_pull_resets_drivetrain_in_chassis_mode():
    """Regression test for a real bug: start_power_pull() reset the engine
    to idle but never touched the drivetrain, so calling it mid-drive left
    the engine snapped back to idle while gear/wheel_rpm/vehicle_speed kept
    whatever they were the instant before -- an inconsistent, obviously
    broken-looking reset."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    for _ in range(1000):
        session.tick(dt=0.01, throttle_percent=70.0)
    assert session.current_gear == 1  # sanity: actually moving, in gear, before the reset

    session.start_power_pull()
    snapshot = session.tick(dt=0.0, throttle_percent=0.0)
    assert snapshot.gear == 0
    assert snapshot.wheel_rpm == pytest.approx(0.0)
    assert snapshot.vehicle_speed_kmh == pytest.approx(0.0)
    assert snapshot.clutch_engagement == pytest.approx(1.0)
    assert not snapshot.shifting
    assert snapshot.rpm == pytest.approx(session.ecu.engine.spec.idle_rpm)


def test_start_power_pull_is_safe_in_crank_mode():
    """start_power_pull() must not blow up when self.drivetrain is None
    (crank mode) -- covers the branch the chassis-mode reset above added."""
    session = DynoSession()
    session.start_power_pull()
    assert session.is_power_pull_active


def test_crank_mode_snapshot_has_neutral_chassis_defaults():
    session = DynoSession()
    snapshot = session.tick(dt=0.01, throttle_percent=0.0)
    assert snapshot.dyno_mode == "crank"
    assert snapshot.gear == 0
    assert snapshot.clutch_engagement == pytest.approx(1.0)
    assert not snapshot.clutch_locked
    assert snapshot.vehicle_speed_kmh == pytest.approx(0.0)


def test_clutch_dump_from_high_rpm_never_chatters():
    """Regression test for a real bug: revving in neutral to near-redline
    and then engaging 1st gear (a hard clutch dump) used to make wheel_torque
    and slip_ratio flip sign wildly tick to tick (+1500Nm one tick, -1500Nm
    the next) instead of transitioning smoothly -- a numerical chatter at
    the wheel/tire's zero-slip crossing, not real physics. Every consecutive
    pair of ticks after the dump must move slip_ratio by a bounded amount,
    never flip its sign abruptly."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    for _ in range(300):
        session.tick(dt=0.01, throttle_percent=100.0)  # rev in neutral toward redline
    session.shift_up()

    # A fast same-direction swing (e.g. +0.48 -> +0.99 as the clutch bites)
    # is real physics under a hard launch, not the bug -- what must never
    # happen is the *sign* flipping between two ticks that both still have
    # meaningful magnitude (the chatter's actual signature: +0.9 one tick,
    # -1.0 the next).
    prev_slip = 0.0
    for i in range(300):
        snap = session.tick(dt=0.01, throttle_percent=100.0)
        if i > 0 and abs(prev_slip) > 0.2 and abs(snap.slip_ratio) > 0.2:
            assert (snap.slip_ratio > 0) == (prev_slip > 0), (
                f"slip sign-flipped {prev_slip:+.3f} -> {snap.slip_ratio:+.3f} at tick {i}"
            )
        prev_slip = snap.slip_ratio


def test_chassis_neutral_holds_idle_same_as_crank_mode():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    last = None
    for _ in range(3000):
        last = session.tick(dt=0.01, throttle_percent=0.0)
    assert abs(last.rpm - session.idle_rpm_target) < 50.0
    assert last.gear == 0


def test_chassis_launch_produces_forward_motion_in_gear_one():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    last = None
    for _ in range(1500):
        last = session.tick(dt=0.01, throttle_percent=60.0)
    assert last.gear == 1
    assert last.vehicle_speed_kmh > 5.0
    assert last.wheel_rpm > 0.0


def test_crank_mode_wheel_power_mirrors_engine_power():
    """Crank mode has no separate wheel -- wheel_torque_nm/wheel_power_kw
    must equal torque_nm/power_kw exactly, so a consumer (like the Godot
    graph) can plot wheel_* unconditionally and get the right curve in
    either mode without branching on dyno_mode."""
    session = DynoSession()
    snapshot = session.tick(dt=0.01, throttle_percent=80.0)
    assert snapshot.wheel_torque_nm == pytest.approx(snapshot.torque_nm)
    assert snapshot.wheel_power_kw == pytest.approx(snapshot.power_kw)


def test_chassis_mode_wheel_power_collapses_under_heavy_wheelspin():
    """Regression test for a real bug: the dyno graph was plotting engine
    crank power, which keeps climbing normally during a wheelspin even
    though almost none of it is reaching the roller -- not what a real
    chassis dyno would show. wheel_power_kw must read far below the engine's
    own power_kw while slip stays heavy."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.select_tire("street")  # lower grip -- easier to keep it slipping
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    # Sample across the whole window rather than trusting one exact final
    # tick -- a single sample can land right on a rev-limiter fuel-cut
    # instant (power_kw genuinely negative there), which is real but not
    # what this test is checking.
    snapshots = [session.tick(dt=0.01, throttle_percent=100.0) for _ in range(150)]
    peak_engine_kw = max(s.power_kw for s in snapshots)
    peak_wheel_kw = max(s.wheel_power_kw for s in snapshots)
    assert any(s.slip_ratio > 0.5 for s in snapshots)  # sanity: genuinely still breaking traction
    assert peak_engine_kw > 50.0  # engine made real power at some point
    assert peak_wheel_kw < peak_engine_kw * 0.5  # but most of it never reached the roller


def test_rev_limiter_holds_near_redline_while_driving_in_gear():
    """The ECU's rev limiter is computed once per outer tick from the
    start-of-tick rpm, then that same reading feeds Drivetrain's ~50
    sub-steps -- worth confirming that staleness doesn't let rpm run away
    past redline before the next tick's fuel cut catches it."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    redline = session.ecu.engine.spec.redline_rpm
    max_rpm = 0.0
    for _ in range(3000):
        snap = session.tick(dt=0.01, throttle_percent=100.0)
        max_rpm = max(max_rpm, snap.rpm)
    assert max_rpm < redline  # never actually reaches true redline, let alone overshoots it


def test_lifting_off_throttle_in_gear_decelerates_via_engine_braking():
    """A real car slows down under engine braking when you lift in gear --
    the clutch has to actually carry that braking torque from the engine to
    the wheel, not just let the car coast on its own drag."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    for _ in range(1500):
        snap = session.tick(dt=0.01, throttle_percent=70.0)
    speed_before, rpm_before = snap.vehicle_speed_kmh, snap.rpm
    assert snap.gear == 1  # sanity: still in gear, not coasting in neutral

    for _ in range(300):  # 3s of lift-off
        snap = session.tick(dt=0.01, throttle_percent=0.0)
    assert snap.gear == 1  # still locked in gear the whole time
    assert snap.vehicle_speed_kmh < speed_before
    assert snap.rpm < rpm_before


def test_live_pull_recording_is_paced_in_chassis_neutral_not_free_revving():
    """Regression test for a real interface gap found during development:
    ChassisDynoLoop.tick() originally didn't accept/forward
    ramp_rate_rpm_s at all, so DynoSession._drive()'s power-pull path would
    have raised a TypeError the first time anyone called start_power_pull()
    in chassis mode. Neutral chassis mode should behave exactly like a
    crank-mode paced sweep -- resisted, not a free-rev."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.start_power_pull()
    snapshot = None
    for _ in range(100):  # 1s at dt=0.01
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    # Paced ~400rpm/s from idle (800) should land close to 1200rpm -- a
    # free-rev would already be far past that (same tolerance as the
    # existing crank-mode equivalent, test_active_pull_resists_the_engine_
    # instead_of_free_revving in test_session.py).
    assert 1100.0 < snapshot.rpm < 1400.0


def test_casual_free_play_in_chassis_neutral_is_not_paced():
    """Counterpoint to the above -- outside a recorded pull, chassis-mode
    neutral free-revs same as crank mode's casual free-play."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    snapshot = None
    for _ in range(100):
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    assert snapshot.rpm > 1500.0


def test_downshift_under_load_lands_close_to_the_new_ratios_implied_rpm():
    """A downshift landing on a mismatched engine speed must slip briefly
    (not instantly snap) and then converge to a physically sane rpm for the
    new gear at the car's current speed -- never NaN, negative, or wildly
    off from what the ratio implies."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()  # 1st
    for _ in range(2000):
        snap = session.tick(dt=0.01, throttle_percent=100.0)
        if snap.gear == 1 and snap.rpm > 6300:
            session.shift_up()  # -> 2nd
            break
    for _ in range(500):
        snap = session.tick(dt=0.01, throttle_percent=100.0)

    session.shift_down()  # back to 1st, still moving
    for _ in range(200):
        snap = session.tick(dt=0.01, throttle_percent=0.0)
        assert snap.rpm == snap.rpm  # not NaN
        assert snap.rpm >= 0.0
        assert snap.vehicle_speed_kmh >= 0.0
    assert snap.gear == 1
    assert snap.clutch_locked  # converged, not left permanently slipping


def test_switching_engine_mid_shift_resets_shift_state_cleanly():
    """select_car()/select_tire()/select_dyno_mode() all build a brand
    new Drivetrain -- confirm that actually clears an in-progress shift
    rather than leaving a stale partial clutch engagement lying around."""
    session = DynoSession()
    session.select_dyno_mode("chassis")
    session.shift_up()
    assert session.drivetrain.is_shifting

    session.select_car("f30_340i")
    assert not session.drivetrain.is_shifting
    assert session.drivetrain.clutch.engagement == pytest.approx(1.0)
    assert session.current_gear == 0


def test_vehicle_speed_never_goes_negative_under_sustained_engine_braking_to_a_stop():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    for _ in range(500):
        session.tick(dt=0.01, throttle_percent=50.0)

    for _ in range(3000):  # long enough to brake all the way down to a stop
        snap = session.tick(dt=0.01, throttle_percent=0.0)
        assert snap.vehicle_speed_kmh >= 0.0
        assert snap.wheel_rpm >= 0.0


def test_shifting_to_neutral_while_moving_decouples_engine_but_keeps_speed():
    session = DynoSession()
    session.select_dyno_mode("chassis")
    for _ in range(50):
        session.tick(dt=0.01, throttle_percent=0.0)
    session.shift_up()
    for _ in range(1500):
        last = session.tick(dt=0.01, throttle_percent=60.0)
    speed_before = last.vehicle_speed_kmh

    session.shift_down()  # back to neutral
    for _ in range(100):  # 1s of neutral coast
        last = session.tick(dt=0.01, throttle_percent=0.0)
    assert last.gear == 0
    # Vehicle keeps rolling (only light drag now, no engine braking reaching
    # the wheels through a disconnected clutch) -- shouldn't have scrubbed
    # off more than a small fraction of a second's worth of speed.
    assert last.vehicle_speed_kmh > speed_before * 0.8
