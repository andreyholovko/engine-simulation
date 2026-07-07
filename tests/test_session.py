"""DynoSession is the one interface every frontend (CLI, Godot, and any
future consumer) is supposed to drive instead of each hand-rolling its own
Engine/Turbo/ECU/SimulationLoop construction. These tests exist to catch
future drift: if two independently-constructed sessions ever stop agreeing,
something broke the "one shared source" guarantee this session exists for.
"""

import pytest

from engine_sim import DynoSession


def test_default_session_matches_validated_curve():
    session = DynoSession()
    snapshots = session.run_power_pull()
    peak_t = max(snapshots, key=lambda s: s.torque_nm)
    peak_p = max(snapshots, key=lambda s: s.power_kw)
    # Same tolerances as tests/test_ea888_validation.py -- this is the same
    # preset, just reached through the session interface instead of raw core.
    assert 272.0 <= peak_t.torque_nm <= 368.0
    assert 125.0 <= peak_p.power_kw <= 169.0


def test_two_independent_sessions_agree():
    """Two consumers building their own DynoSession() (as the CLI and the
    Godot controller each do) must get bit-identical results -- proving they
    share one source, not two copies that happen to agree today."""
    session_a = DynoSession()
    session_b = DynoSession()
    snapshots_a = session_a.run_power_pull()
    snapshots_b = session_b.run_power_pull()
    assert len(snapshots_a) == len(snapshots_b)
    for a, b in zip(snapshots_a, snapshots_b):
        assert a.rpm == b.rpm
        assert a.torque_nm == b.torque_nm
        assert a.power_kw == b.power_kw
        assert a.boost_bar == b.boost_bar


def test_afr_override_through_session():
    session = DynoSession()
    snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    assert snapshot.afr_actual == pytest.approx(12.5)
    session.set_afr_override(10.0)
    snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    assert snapshot.afr_actual == pytest.approx(10.0)


def test_boost_target_through_session():
    session_full = DynoSession()
    session_half = DynoSession()
    session_half.set_boost_target_percent(50.0)

    peak_full = max(session_full.run_power_pull(), key=lambda s: s.torque_nm)
    peak_half = max(session_half.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_half.torque_nm < peak_full.torque_nm


def test_session_starts_at_idle_and_holds_it():
    """Regression test for a real bug: zero-throttle used to have nothing
    but ~3Nm of dyno drag opposing the engine's own torque, so it free-revved
    straight to the rev limiter instead of idling. A session should start at
    the engine's idle RPM and stay near it, not run away."""
    session = DynoSession()
    assert session.loop.rpm == pytest.approx(session.idle_rpm_target)

    last_rpm = session.loop.rpm
    for _ in range(3000):
        snapshot = session.tick(dt=0.01, throttle_percent=0.0)
        last_rpm = snapshot.rpm
    # Steady-state PI error, not an exact hold -- generous band, but nowhere
    # near a stall (0) or a runaway to the rev limiter (~6550).
    assert abs(last_rpm - session.idle_rpm_target) < 50.0


def test_idle_recovers_after_a_power_pull():
    session = DynoSession()
    session.run_power_pull()
    assert session.loop.rpm > 6000.0  # sanity: it really did end the pull way up high

    for _ in range(3000):
        snapshot = session.tick(dt=0.01, throttle_percent=0.0)
    assert abs(snapshot.rpm - session.idle_rpm_target) < 50.0


def test_select_engine_switches_to_a_validated_curve():
    session = DynoSession()
    assert session.engine_key == "ea888_gen3_is20"

    session.select_engine("b58_340i")
    assert session.engine_key == "b58_340i"
    assert session.loop.rpm == pytest.approx(700.0)  # B58's idle, not the EA888's 800

    peak_t = max(session.run_power_pull(), key=lambda s: s.torque_nm)
    peak_p = max(session.run_power_pull(), key=lambda s: s.power_kw)
    # Same tolerances as tests/test_b58_validation.py.
    assert 380.0 <= peak_t.torque_nm <= 514.0
    assert 203.0 <= peak_p.power_kw <= 274.0


def test_select_engine_rejects_unknown_key():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_engine("does_not_exist")


def test_list_engine_choices_includes_both_validated_engines():
    keys = {key for key, _ in DynoSession.list_engine_choices()}
    assert {"ea888_gen3_is20", "b58_340i"} <= keys


def test_select_engine_by_index_matches_select_engine_by_key():
    """The Godot-facing path (index-based, avoiding str across the py4godot
    boundary) must land on the exact same engine as the key-based one."""
    by_index = DynoSession()
    by_index.select_engine_by_index(1)
    by_key = DynoSession()
    by_key.select_engine("b58_340i")
    assert by_index.engine_key == by_key.engine_key == "b58_340i"
    assert by_index.ecu.engine.spec.name == by_key.ecu.engine.spec.name


def test_select_engine_by_index_rejects_out_of_range():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_engine_by_index(99)


def test_power_pull_transitions_active_flag():
    session = DynoSession()
    assert not session.is_power_pull_active
    session.start_power_pull()
    assert session.is_power_pull_active
    snapshot = None
    for _ in range(100_000):
        snapshot = session.tick(dt=0.01)
        if not session.is_power_pull_active:
            break
    assert not session.is_power_pull_active
    assert snapshot is not None and not snapshot.power_pull_active
