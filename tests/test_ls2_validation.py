"""Validates the parametric engine model against published figures for the
GM LS2 (Corvette C6): 400hp (298.3kW) @ 6000rpm, 400lb-ft (542.4Nm) @
4400rpm, 5967cc, redline 6500rpm, naturally aspirated (paired with
TURBO_NONE -- no boost at all).

Same mean-value model and tolerance philosophy as
tests/test_ea888_validation.py / tests/test_b58_validation.py. This is also
the only naturally-aspirated preset, so it's what actually exercises
EngineSpec.ve_rise_rpm (the turbocharged presets get their low-end torque
rise from boost building, not VE) and TURBO_NONE (max_boost_bar=0.0).
"""

from engine_sim import ECU, DynoBrake, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import LS2_NA, TURBO_NONE


def _build_loop() -> SimulationLoop:
    engine = ParametricEngine(LS2_NA)
    turbo = Turbo(TURBO_NONE)
    ecu = ECU(engine, turbo)
    brake = DynoBrake()
    return SimulationLoop(ecu, brake)


def test_peak_torque_matches_published_figure():
    loop = _build_loop()
    readings = loop.run_power_pull()
    peak = max(readings, key=lambda r: r.engine.net_torque_nm)
    # Published torque is 542.4Nm (400lb-ft); +-15% for the same MVEM
    # approximation reasons as the other presets.
    assert 461.0 <= peak.engine.net_torque_nm <= 624.0, peak.engine.net_torque_nm
    # Published peak is at 4400rpm; allow slack either side.
    assert 3600.0 <= peak.rpm <= 5200.0, peak.rpm


def test_peak_power_matches_published_figure():
    loop = _build_loop()
    readings = loop.run_power_pull()
    peak = max(readings, key=lambda r: r.power_w)
    # Published peak is 298.3kW; +-15% tolerance for the same reason as torque.
    assert 253.0 <= peak.power_kw <= 343.0, peak.power_kw
    assert 5000.0 <= peak.rpm <= 6500.0, peak.rpm


def test_torque_rises_from_idle_to_peak_on_ve_alone():
    """The thing that makes this preset different from the turbocharged
    ones: no boost, so torque must genuinely rise across the low/mid range
    on VE alone (ve_rise_rpm), not just hold a plateau from idle."""
    loop = _build_loop()
    readings = loop.run_power_pull()
    near_idle = min(readings, key=lambda r: abs(r.rpm - 900.0))
    near_peak = min(readings, key=lambda r: abs(r.rpm - 4200.0))
    assert near_idle.engine.net_torque_nm < near_peak.engine.net_torque_nm * 0.7


def test_naturally_aspirated_never_builds_boost():
    loop = _build_loop()
    readings = loop.run_power_pull()
    assert all(r.boost_bar < 1e-6 for r in readings)


def test_power_pull_terminates_at_redline():
    loop = _build_loop()
    readings = loop.run_power_pull()
    assert readings[-1].rpm >= loop.ecu.rev_limiter_threshold_rpm
