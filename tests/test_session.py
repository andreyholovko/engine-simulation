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


def test_throttle_position_produces_monotonically_more_torque():
    """Real gap found by direct manual testing: existing tests only ever
    checked throttle=0 (idle) and throttle=100 (WOT) explicitly -- nothing
    asserted that intermediate throttle positions actually produce
    intermediate output. A single tick from idle (before any rev-limiter/
    rpm-climb effects confound it) must show strictly increasing torque as
    throttle rises."""
    torques = []
    for tp in (10.0, 25.0, 50.0, 75.0, 100.0):
        s = DynoSession()
        snapshot = s.tick(dt=0.01, throttle_percent=tp)
        torques.append(snapshot.torque_nm)
    assert torques == sorted(torques)
    assert torques[0] < torques[-1]


def test_boost_target_through_session():
    session_full = DynoSession()
    session_half = DynoSession()
    session_half.set_boost_target_percent(50.0)

    peak_full = max(session_full.run_power_pull(), key=lambda s: s.torque_nm)
    peak_half = max(session_half.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_half.torque_nm < peak_full.torque_nm


def test_boost_target_percent_clamps_out_of_range_values():
    """set_boost_target_percent()'s 0-100 clamp is a pure expression
    (max(0, min(1, percent/100))), invisible to coverage tools -- never
    actually exercised with genuinely out-of-range input by any existing
    test (50.0 above is already in-range)."""
    over = DynoSession()
    over.set_boost_target_percent(150.0)
    at_max = DynoSession()
    at_max.set_boost_target_percent(100.0)
    peak_over = max(over.run_power_pull(), key=lambda s: s.torque_nm)
    peak_at_max = max(at_max.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_over.torque_nm == pytest.approx(peak_at_max.torque_nm)

    under = DynoSession()
    under.set_boost_target_percent(-50.0)
    at_zero = DynoSession()
    at_zero.set_boost_target_percent(0.0)
    peak_under = max(under.run_power_pull(), key=lambda s: s.torque_nm)
    peak_at_zero = max(at_zero.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_under.torque_nm == pytest.approx(peak_at_zero.torque_nm)


def test_throttle_percent_clamps_out_of_range_values():
    """Same class of gap as the boost clamp above, for throttle -- the CLI
    parses throttle straight from user input (float(parts[1])), so an
    out-of-range value is a real reachable case, not just a theoretical one."""
    session = DynoSession()
    over = session.tick(dt=0.01, throttle_percent=150.0)
    session2 = DynoSession()
    at_max = session2.tick(dt=0.01, throttle_percent=100.0)
    assert over.torque_nm == pytest.approx(at_max.torque_nm)
    assert over.afr_actual == pytest.approx(at_max.afr_actual)


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


def test_select_car_switches_to_a_validated_curve():
    session = DynoSession()
    assert session.car_key == "mk7_gti"

    session.select_car("f30_340i")
    assert session.car_key == "f30_340i"
    assert session.loop.rpm == pytest.approx(700.0)  # B58's idle, not the EA888's 800

    peak_t = max(session.run_power_pull(), key=lambda s: s.torque_nm)
    peak_p = max(session.run_power_pull(), key=lambda s: s.power_kw)
    # Same tolerances as tests/test_b58_validation.py.
    assert 380.0 <= peak_t.torque_nm <= 514.0
    assert 203.0 <= peak_p.power_kw <= 274.0


def test_select_car_rejects_unknown_key():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_car("does_not_exist")


def test_list_car_choices_includes_both_validated_engines():
    keys = {key for key, _ in DynoSession.list_car_choices()}
    assert {"mk7_gti", "f30_340i"} <= keys


def test_select_car_by_index_matches_select_car_by_key():
    """The Godot-facing path (index-based, avoiding str across the py4godot
    boundary) must land on the exact same engine as the key-based one."""
    by_index = DynoSession()
    by_index.select_car_by_index(1)
    by_key = DynoSession()
    by_key.select_car("f30_340i")
    assert by_index.car_key == by_key.car_key == "f30_340i"
    assert by_index.ecu.engine.spec.name == by_key.ecu.engine.spec.name


def test_select_car_by_index_rejects_out_of_range():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_car_by_index(99)


def test_power_pull_transitions_active_flag():
    """A pull is now driven live by whatever throttle the caller passes each
    tick (a vertical slider in Godot) instead of an auto-paced sweep --
    holding WOT throughout still reaches the rev limiter and auto-ends,
    same as the old paced version did."""
    session = DynoSession()
    assert not session.is_power_pull_active
    session.start_power_pull()
    assert session.is_power_pull_active
    snapshot = None
    for _ in range(100_000):
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
        if not session.is_power_pull_active:
            break
    assert not session.is_power_pull_active
    assert snapshot is not None and not snapshot.power_pull_active


def test_lifting_off_throttle_coasts_down_without_a_pid_snap():
    """Regression test for a real bug: the coast-vs-PID-hold handoff used to
    live on its own hand-tuned rpm threshold, independent of the ECU's own
    dfco_reengage_rpm -- if the PID engaged while the ECU was still
    fuel-cutting (real engine braking, negative torque), its correction
    stacked on top of that braking torque and crashed rpm toward zero in a
    couple of ticks instead of a smooth coast-down. Both now share
    ECU.dfco_reengage_rpm (see DynoSession._drive()) specifically to prevent
    this. This test drives the exact scenario that used to crash."""
    session = DynoSession()
    session.start_power_pull()
    for _ in range(2000):  # get well up into the rev range at WOT
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
        if snapshot.rpm > 5000.0:
            break
    assert snapshot.rpm > 5000.0  # sanity: actually got up there

    # Seed with the rpm right *before* the lift -- the old bug's catastrophic
    # crash happened on the very first post-lift tick, so comparing only
    # among post-lift samples (never against this baseline) would have
    # completely missed it.
    rpms = [snapshot.rpm]
    for _ in range(3000):  # 30s of coasting at throttle=0
        snapshot = session.tick(dt=0.01, throttle_percent=0.0)
        rpms.append(snapshot.rpm)

    # The old bug's signature: rpm collapsing far below idle in a handful of
    # ticks (dt=0.01, so 100 ticks/s -- a real coast-down takes several
    # seconds, never drops more than a few hundred rpm in 0.1s).
    for i in range(1, len(rpms)):
        assert rpms[i] > rpms[i - 1] - 300.0, f"rpm crashed from {rpms[i - 1]:.0f} to {rpms[i]:.0f} in one tick"
    # And it must actually reach a real idle, not get stuck coasting forever.
    assert abs(rpms[-1] - session.idle_rpm_target) < 50.0


def test_octane_override_through_session_changes_torque_under_load():
    session_good = DynoSession()
    session_bad = DynoSession()
    session_bad.set_octane_override(session_bad.ecu.engine.spec.knock_octane_requirement - 15.0)

    peak_good = max(session_good.run_power_pull(), key=lambda s: s.torque_nm)
    peak_bad = max(session_bad.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_bad.torque_nm < peak_good.torque_nm

    # Restoring via a *fresh* session -- run_power_pull() deliberately does
    # NOT reset the turbo's heat-soak state (see Turbo.reset()), so reusing
    # session_bad here would compare a warmed-up second pull against a cold
    # first one and conflate two different effects.
    session_restored = DynoSession()
    session_restored.set_octane_override(100.0)
    session_restored.set_octane_override(None)  # restores the engine's own requirement
    peak_restored = max(session_restored.run_power_pull(), key=lambda s: s.torque_nm)
    assert peak_restored.torque_nm == pytest.approx(peak_good.torque_nm)


def test_stop_power_pull_clears_active_flag_and_resumes_normal_ticking():
    session = DynoSession()
    session.start_power_pull()
    assert session.is_power_pull_active
    session.tick(dt=0.01, throttle_percent=100.0)

    session.stop_power_pull()
    assert not session.is_power_pull_active

    snapshot = session.tick(dt=0.01, throttle_percent=0.0)
    assert not snapshot.power_pull_active


def test_selecting_a_new_car_aborts_an_active_pull():
    session = DynoSession()
    session.start_power_pull()
    assert session.is_power_pull_active

    session.select_car("c6_corvette")
    assert not session.is_power_pull_active

    session2 = DynoSession()
    session2.start_power_pull()
    session2.select_car_by_index(2)  # c6_corvette
    assert not session2.is_power_pull_active


def test_active_pull_resists_the_engine_instead_of_free_revving():
    """Regression test for a real complaint: an active pull used to run
    free_accel (just ~3Nm of dyno drag), so it free-revved as fast as the
    engine's own torque allowed instead of feeling like a loaded dyno. A
    real engine dyno's brake actively resists to hold a controlled sweep --
    verify the rpm climb during a WOT pull is paced, not a free-rev."""
    session = DynoSession()
    session.start_power_pull()
    for _ in range(100):  # 1s at dt=0.01
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    # At the (paced) max rate of 400rpm/s, 1s of WOT from idle (800) should
    # land close to 1200rpm -- a free-rev would already be well past that
    # (the EA888 free-accelerates far quicker than 400rpm/s once boosted).
    assert 1100.0 < snapshot.rpm < 1400.0


def test_active_pull_ramp_pace_scales_with_partial_throttle():
    session_full = DynoSession()
    session_full.start_power_pull()
    session_half = DynoSession()
    session_half.start_power_pull()

    for _ in range(100):
        snap_full = session_full.tick(dt=0.01, throttle_percent=100.0)
        snap_half = session_half.tick(dt=0.01, throttle_percent=50.0)
    assert snap_half.rpm < snap_full.rpm


def test_casual_free_play_outside_a_pull_is_not_artificially_paced():
    """Outside of an active/recorded pull, throttle input is still plain
    free_accel (casual revving, e.g. the CLI's `throttle`/`step`) -- only a
    recorded pull gets the resisted, paced sweep."""
    session = DynoSession()
    assert not session.is_power_pull_active
    for _ in range(100):
        snapshot = session.tick(dt=0.01, throttle_percent=100.0)
    # Free-accelerating (no brake resistance beyond ~3Nm drag) climbs much
    # faster than the paced 400rpm/s a pull would enforce.
    assert snapshot.rpm > 1500.0


def test_back_to_back_pulls_run_measurably_weaker_from_heat_soak():
    """Real gap found by direct manual testing: heat-soak state persisting
    across pulls (Turbo.reset() deliberately doesn't clear intake_air_temp_k)
    is the whole point of the feature, but nothing asserted it actually
    shows up as less peak torque on a second, already-warmed-up pull."""
    session = DynoSession()
    first = session.run_power_pull()
    peak_first = max(r.torque_nm for r in first)

    second = session.run_power_pull()
    peak_second = max(r.torque_nm for r in second)

    assert peak_second < peak_first


@pytest.mark.parametrize("car_key", ["mk7_gti", "f30_340i", "c6_corvette"])
def test_afr_behaves_correctly_across_every_selectable_car(car_key):
    """Real gap: existing AFR tests only ever exercised the default EA888
    session. The control law is deliberately NOT engine-parameterized (see
    ECU.target_afr()), so every engine should show the exact same idle vs.
    WOT AFR readings -- assert that explicitly per engine rather than
    trusting it by extrapolation from one."""
    session = DynoSession()
    session.select_car(car_key)
    assert session.car_key == car_key

    idle = session.tick(dt=0.01, throttle_percent=0.0)
    assert idle.afr_actual > 12.5  # richer-than-power-AFR is wrong; near-stoich at idle is right
    assert idle.afr_actual < 14.7  # some enrichment from the idle-air-equivalent load, not pure stoich

    wot = session.tick(dt=0.01, throttle_percent=100.0)
    assert wot.afr_actual == pytest.approx(12.5)


@pytest.mark.parametrize("car_key", ["mk7_gti", "f30_340i", "c6_corvette"])
def test_afr_varies_with_partial_throttle_on_every_selectable_car(car_key):
    """Companion to the above: load-based variation (not just the idle/WOT
    endpoints) must also hold for every engine. A full WOT run_power_pull()
    doesn't actually exercise this -- load_fraction reaches ~1.0 on the very
    first tick at throttle=1.0 (na_map alone reaches atmospheric), so AFR
    is a constant 12.5 throughout a real pull. Partial throttle is what
    actually varies load_fraction meaningfully, per engine's own turbo/NA
    characteristics."""
    session = DynoSession()
    session.select_car(car_key)
    partial = session.tick(dt=0.01, throttle_percent=40.0)
    assert 12.5 < partial.afr_actual < 14.7


@pytest.mark.parametrize("car_key", ["mk7_gti", "f30_340i", "c6_corvette"])
def test_turbo_choices_are_listed_with_stock_first(car_key):
    session = DynoSession()
    session.select_car(car_key)
    choices = session.list_turbo_choices()
    assert len(choices) >= 2  # every engine has at least a stock + one alternative
    keys = [key for key, _ in choices]
    assert len(keys) == len(set(keys))  # no duplicate keys
    assert session.turbo_key == keys[0]  # freshly selected engine starts on its stock turbo


@pytest.mark.parametrize("car_key", ["mk7_gti", "f30_340i", "c6_corvette"])
def test_selecting_a_different_turbo_changes_the_dyno_curve_on_the_same_car(car_key):
    """The actual point of the feature: swap only the turbo, keep the same
    validated engine, and the curve must genuinely differ -- not just
    accept the call and silently keep behaving like the stock unit."""
    session = DynoSession()
    session.select_car(car_key)
    choices = session.list_turbo_choices()
    stock_key, alt_key = choices[0][0], choices[1][0]

    session.select_turbo(stock_key)
    peak_stock = max(session.run_power_pull(), key=lambda r: r.torque_nm)
    assert session.car_key == car_key  # still the same engine

    session.select_turbo(alt_key)
    peak_alt = max(session.run_power_pull(), key=lambda r: r.torque_nm)
    assert session.car_key == car_key  # selecting a turbo never changes the engine

    assert peak_alt.torque_nm != pytest.approx(peak_stock.torque_nm, rel=0.01)


def test_select_turbo_by_index_matches_select_turbo_by_key():
    by_index = DynoSession()
    by_index.select_turbo_by_index(1)
    by_key = DynoSession()
    by_key.select_turbo(by_key.list_turbo_choices()[1][0])
    assert by_index.turbo_key == by_key.turbo_key
    assert by_index.ecu.turbo.spec.name == by_key.ecu.turbo.spec.name


def test_select_turbo_rejects_unknown_key_for_current_car():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_turbo("not_a_real_turbo")


def test_select_turbo_by_index_rejects_out_of_range():
    session = DynoSession()
    with pytest.raises(ValueError):
        session.select_turbo_by_index(99)


def test_selecting_a_new_car_resets_turbo_to_that_cars_stock_unit():
    """A non-stock turbo choice from one engine isn't valid (or even
    meaningful) on a different engine -- select_car() must reset to the
    new engine's own stock turbo, not silently carry over the old key."""
    session = DynoSession()
    session.select_turbo_by_index(1)  # a non-stock EA888 turbo
    assert session.turbo_key != session.list_turbo_choices()[0][0]

    session.select_car("f30_340i")
    assert session.turbo_key == session.list_turbo_choices()[0][0]  # back to B58's own stock unit


def test_select_turbo_aborts_an_active_pull():
    session = DynoSession()
    session.start_power_pull()
    assert session.is_power_pull_active

    session.select_turbo_by_index(1)
    assert not session.is_power_pull_active
