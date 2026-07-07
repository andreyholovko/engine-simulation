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
