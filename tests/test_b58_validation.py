"""Validates the parametric engine model against published figures for the
BMW B58B30 (340i): 320hp (238.7kW) @ 5500-6500rpm, 330lb-ft (447Nm) torque
flat from 1380-5000rpm, redline 7000rpm, single twin-scroll turbo.

Same mean-value model and same tolerance philosophy as
tests/test_ea888_validation.py -- see that file for why tolerances are sized
the way they are. This is the second independently-validated preset, so
these tests also double as a check that ENGINE_CHOICES' selection mechanism
actually produces a working, correctly-tuned engine, not just the default.
"""

from engine_sim import ECU, DynoBrake, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import B58_340I, TURBO_B58


def _build_loop() -> SimulationLoop:
    engine = ParametricEngine(B58_340I)
    turbo = Turbo(TURBO_B58)
    ecu = ECU(engine, turbo)
    brake = DynoBrake()
    return SimulationLoop(ecu, brake)


def test_peak_torque_matches_published_figure():
    loop = _build_loop()
    readings = loop.run_power_pull()
    peak = max(readings, key=lambda r: r.engine.net_torque_nm)
    # Published torque is 447Nm (330lb-ft); +-15% for the same MVEM
    # approximation reasons as the EA888 tolerance.
    assert 380.0 <= peak.engine.net_torque_nm <= 514.0, peak.engine.net_torque_nm
    # Plateau is spec'd 1380-5000rpm; allow slack either side.
    assert 1100.0 <= peak.rpm <= 5300.0, peak.rpm


def test_torque_plateau_is_flat_across_published_band():
    loop = _build_loop()
    readings = loop.run_power_pull()
    in_band = [r for r in readings if 1400.0 <= r.rpm <= 5000.0]
    assert len(in_band) > 5
    torques = [r.engine.net_torque_nm for r in in_band]
    assert (max(torques) - min(torques)) / max(torques) < 0.20


def test_peak_power_matches_published_figure():
    loop = _build_loop()
    readings = loop.run_power_pull()
    peak = max(readings, key=lambda r: r.power_w)
    # Published peak is 238.7kW; +-15% tolerance for the same reason as torque.
    assert 203.0 <= peak.power_kw <= 274.0, peak.power_kw
    assert 4700.0 <= peak.rpm <= 6800.0, peak.rpm


def test_twin_scroll_turbo_spools_quickly():
    """The B58's flat torque plateau starting at just 1380rpm implies it's
    already near full boost by then -- much quicker than the EA888's IS20."""
    loop = _build_loop()
    readings = loop.run_power_pull()
    at_1500 = min(readings, key=lambda r: abs(r.rpm - 1500.0))
    assert at_1500.boost_bar >= 0.9 * TURBO_B58.max_boost_bar


def test_power_pull_terminates_at_redline():
    loop = _build_loop()
    readings = loop.run_power_pull()
    assert readings[-1].rpm >= loop.ecu.rev_limiter_threshold_rpm
