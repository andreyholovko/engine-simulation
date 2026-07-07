import pytest

from engine_sim import ECU, Engine, ParametricEngine, Turbo
from engine_sim.presets import EA888_GEN3B_IS38, EA888_GEN3_IS20, TURBO_IS20


def test_engine_is_abstract():
    with pytest.raises(TypeError):
        Engine()  # type: ignore[abstract]


def _build_ecu(engine_spec=EA888_GEN3_IS20) -> ECU:
    return ECU(ParametricEngine(engine_spec), Turbo(TURBO_IS20))


def test_ecu_afr_override():
    ecu = _build_ecu()
    assert ecu.target_afr(throttle=1.0) == pytest.approx(12.5)
    ecu.set_target_afr(10.0)
    assert ecu.target_afr(throttle=1.0) == 10.0
    ecu.set_target_afr(None)
    assert ecu.target_afr(throttle=1.0) == pytest.approx(12.5)


def test_ecu_rev_limiter_cuts_fuel():
    ecu = _build_ecu()
    reading = ecu.tick(dt=0.01, rpm=EA888_GEN3_IS20.redline_rpm, throttle=1.0)
    assert reading.rev_limiter_active
    assert reading.target_afr == 0.0


def test_zero_throttle_uses_bounded_idle_air_not_full_atmospheric_map():
    """Zero throttle input must use the small, fixed idle-air-control
    opening (modest torque, held steady by the dyno brake in SimulationLoop)
    -- not full atmospheric MAP at stoich (the old bug: ~118Nm, enough to
    free-rev straight to the rev limiter against only ~3Nm of dyno drag) and
    not a hard fuel cut either (that stalls instead of idling)."""
    ecu = _build_ecu()
    reading = ecu.tick(dt=0.01, rpm=EA888_GEN3_IS20.idle_rpm, throttle=0.0)
    assert reading.target_afr > 0.0  # not cut
    assert reading.map_pa < 40_000.0  # closed-throttle-ish vacuum, not atmospheric (~101325 Pa)
    assert 0.0 < reading.engine.net_torque_nm < 60.0  # modest, nowhere near the old ~118Nm bug


def test_closed_throttle_map_is_vacuum_not_atmospheric():
    ecu = _build_ecu()
    map_pa = ecu.intake_manifold_pressure(throttle=0.0, boost_pa=0.0)
    assert map_pa < 40_000.0  # closed-throttle vacuum, nowhere near the ~101325 Pa atmospheric
    assert ecu.intake_manifold_pressure(throttle=1.0, boost_pa=0.0) == pytest.approx(101_325.0)


def test_turbo_spools_toward_target_with_lag():
    turbo = Turbo(TURBO_IS20)
    reading_1 = turbo.tick(dt=0.01, rpm=4000.0, throttle=1.0, wastegate_duty=1.0)
    reading_2 = turbo.tick(dt=0.01, rpm=4000.0, throttle=1.0, wastegate_duty=1.0)
    assert 0.0 < reading_1.boost_pa < reading_2.boost_pa
    assert 0.0 < reading_1.spool_fraction < reading_2.spool_fraction < 1.0


def test_turbo_no_spool_at_closed_throttle():
    turbo = Turbo(TURBO_IS20)
    for _ in range(50):
        turbo.tick(dt=0.02, rpm=4000.0, throttle=0.0, wastegate_duty=1.0)
    assert turbo.boost_bar == pytest.approx(0.0, abs=1e-6)


def test_miller_cycle_compression_rises_with_load():
    engine = ParametricEngine(EA888_GEN3B_IS38)
    low_load = engine.effective_compression_ratio(load_fraction=0.0)
    high_load = engine.effective_compression_ratio(load_fraction=1.0)
    assert low_load == pytest.approx(EA888_GEN3B_IS38.miller_compression_ratio)
    assert high_load == pytest.approx(EA888_GEN3B_IS38.compression_ratio)
    assert low_load < high_load


def test_non_miller_engine_compression_is_static():
    engine = ParametricEngine(EA888_GEN3_IS20)
    assert engine.effective_compression_ratio(0.0) == EA888_GEN3_IS20.compression_ratio
    assert engine.effective_compression_ratio(1.0) == EA888_GEN3_IS20.compression_ratio
