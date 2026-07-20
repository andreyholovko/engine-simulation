import dataclasses
from math import exp, pi

import pytest

from engine_sim import ECU, DynoBrake, Engine, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import (
    B58_340I,
    EA888_GEN3B_IS38,
    EA888_GEN3_IS20,
    LS2_NA,
    TURBO_B58,
    TURBO_B58_BIG_SINGLE,
    TURBO_B58_TU,
    TURBO_EA888_BIG_SINGLE_HYBRID,
    TURBO_IS20,
    TURBO_IS38,
    TURBO_LS2_TWIN,
    TURBO_NONE,
    TURBO_CHOICES_BY_CAR,
)
from engine_sim.specs import CamSpec, EngineSpec, TurboSpec
from engine_sim.units import BAR_TO_PA


def test_engine_is_abstract():
    with pytest.raises(TypeError):
        Engine()  # type: ignore[abstract]


def test_ecu_afr_override(ecu):
    assert ecu.target_afr(load_fraction=1.0) == pytest.approx(12.5)
    ecu.set_target_afr(10.0)
    assert ecu.target_afr(load_fraction=1.0) == 10.0
    ecu.set_target_afr(None)
    assert ecu.target_afr(load_fraction=1.0) == pytest.approx(12.5)


def test_ecu_rev_limiter_cuts_fuel(ecu):
    reading = ecu.tick(dt=0.01, rpm=EA888_GEN3_IS20.redline_rpm, throttle=1.0)
    assert reading.rev_limiter_active
    assert reading.target_afr == 0.0


def _fresh_ea888_ecu() -> ECU:
    # Turbo carries spool-lag state, so two sequential .tick() calls on the
    # *same* ECU aren't independent snapshots -- these tests need genuinely
    # fresh instances to compare apples to apples.
    return ECU(ParametricEngine(EA888_GEN3_IS20), Turbo(TURBO_IS20, firing_order_length=4))


def test_torque_reduction_fraction_scales_indicated_torque_not_friction():
    """Shift torque management (see ECU.tick()'s docstring) reduces
    *indicated* torque only -- friction_torque_nm is real mechanical drag,
    not something ignition retard/fuel trimming touches."""
    baseline = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=0.0)
    cut = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=0.5)
    assert cut.engine.indicated_torque_nm == pytest.approx(baseline.engine.indicated_torque_nm * 0.5)
    assert cut.engine.friction_torque_nm == pytest.approx(baseline.engine.friction_torque_nm)
    assert cut.engine.net_torque_nm == pytest.approx(cut.engine.indicated_torque_nm - cut.engine.friction_torque_nm)


def test_torque_reduction_fraction_can_drive_net_torque_negative():
    """A severe enough cut lets friction dominate indicated torque -- the
    same 'engine braking' shape DFCO already produces, not floored at 0."""
    reading = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=1.0)
    assert reading.engine.indicated_torque_nm == pytest.approx(0.0)
    assert reading.engine.net_torque_nm == pytest.approx(-reading.engine.friction_torque_nm)


def test_torque_reduction_fraction_clamps_out_of_range_values():
    full_cut = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=1.0)
    over = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=1.5)
    assert over.engine.net_torque_nm == pytest.approx(full_cut.engine.net_torque_nm)

    no_cut = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=0.0)
    under = _fresh_ea888_ecu().tick(dt=0.01, rpm=4000.0, throttle=1.0, torque_reduction_fraction=-0.5)
    assert under.engine.net_torque_nm == pytest.approx(no_cut.engine.net_torque_nm)


def test_zero_throttle_uses_bounded_idle_air_not_full_atmospheric_map(ecu):
    """Zero throttle input must use the small, fixed idle-air-control
    opening (modest torque, held steady by the dyno brake in SimulationLoop)
    -- not full atmospheric MAP at stoich (the old bug: ~118Nm, enough to
    free-rev straight to the rev limiter against only ~3Nm of dyno drag) and
    not a hard fuel cut either (that stalls instead of idling)."""
    reading = ecu.tick(dt=0.01, rpm=EA888_GEN3_IS20.idle_rpm, throttle=0.0)
    assert reading.target_afr > 0.0  # not cut
    assert reading.map_pa < 40_000.0  # closed-throttle-ish vacuum, not atmospheric (~101325 Pa)
    assert 0.0 < reading.engine.net_torque_nm < 60.0  # modest, nowhere near the old ~118Nm bug


def test_closed_throttle_map_is_vacuum_not_atmospheric(ecu):
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


def test_effective_compression_ratio_clamps_out_of_range_load_fraction():
    """max(0, min(1, load_fraction)) clamps are pure expressions, not
    control-flow branches -- invisible to line/branch coverage tools, so a
    100% branch-covered suite can still never have exercised the actual
    clamp boundary. Call with genuinely out-of-range values directly."""
    engine = ParametricEngine(EA888_GEN3B_IS38)
    assert engine.effective_compression_ratio(1.5) == pytest.approx(engine.effective_compression_ratio(1.0))
    assert engine.effective_compression_ratio(-0.5) == pytest.approx(engine.effective_compression_ratio(0.0))


def test_non_miller_engine_compression_is_static():
    engine = ParametricEngine(EA888_GEN3_IS20)
    assert engine.effective_compression_ratio(0.0) == EA888_GEN3_IS20.compression_ratio
    assert engine.effective_compression_ratio(1.0) == EA888_GEN3_IS20.compression_ratio


def test_firing_orders_are_real_and_engine_specific():
    """Firing order is a genuine per-engine fact (like cylinders/displacement),
    not something to guess from cylinder count alone -- two engines can share
    a cylinder count and not share a firing order."""
    assert EA888_GEN3_IS20.firing_order == (1, 3, 4, 2)
    assert B58_340I.firing_order == (1, 5, 3, 6, 2, 4)
    assert sorted(EA888_GEN3_IS20.firing_order) == list(range(1, EA888_GEN3_IS20.cylinders + 1))
    assert sorted(B58_340I.firing_order) == list(range(1, B58_340I.cylinders + 1))


def test_firing_order_resolved_falls_back_to_plain_sequence():
    spec = EngineSpec(name="unspecified", displacement_l=2.0, cylinders=4, compression_ratio=10.0)
    assert spec.firing_order == ()
    assert spec.firing_order_resolved == (1, 2, 3, 4)


def test_ve_rise_phase_is_opt_in_only():
    """Every turbocharged preset relies on boost, not VE, for its low-end
    torque rise -- ve_rise_rpm must default to a no-op so their VE is
    ve_peak from idle, exactly as before this field existed."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    assert EA888_GEN3_IS20.ve_rise_rpm == 0.0
    assert engine.volumetric_efficiency(EA888_GEN3_IS20.idle_rpm) == pytest.approx(EA888_GEN3_IS20.ve_peak)
    assert engine.volumetric_efficiency(EA888_GEN3_IS20.idle_rpm + 50.0) == pytest.approx(EA888_GEN3_IS20.ve_peak)


def test_ve_rise_phase_ramps_for_opted_in_engines():
    """LS2 (naturally aspirated, no boost to lean on) opts in: VE should
    genuinely climb from a reduced value at idle up to ve_peak by
    ve_rise_rpm, not jump straight there."""
    engine = ParametricEngine(LS2_NA)
    assert LS2_NA.ve_rise_rpm > LS2_NA.idle_rpm
    at_idle = engine.volumetric_efficiency(LS2_NA.idle_rpm)
    at_half = engine.volumetric_efficiency((LS2_NA.idle_rpm + LS2_NA.ve_rise_rpm) / 2.0)
    at_rise_rpm = engine.volumetric_efficiency(LS2_NA.ve_rise_rpm)
    assert at_idle < at_half < at_rise_rpm == pytest.approx(LS2_NA.ve_peak)


def test_charge_air_heats_up_under_sustained_boost():
    """A real (even intercooled) turbo delivers hotter-than-ambient charge
    air once it's actually making boost, and that heat builds up the longer
    boost is sustained -- not a flat ambient temp forever."""
    turbo = Turbo(TURBO_IS20, firing_order_length=4)
    ambient = 313.0
    reading = None
    for _ in range(300):  # 3s at dt=0.01, long enough to spool and heat-soak partway
        reading = turbo.tick(dt=0.01, rpm=4000.0, throttle=1.0, wastegate_duty=1.0, ambient_temp_k=ambient)
    assert reading.boost_pa > 0.0  # sanity: it actually spooled
    assert reading.intake_air_temp_k > ambient


def test_charge_air_temp_stays_at_ambient_with_no_boost():
    """TURBO_NONE (naturally aspirated) never builds boost, so charge temp
    must never rise above ambient either -- no special-casing needed, same
    principle as max_boost_bar==0 already guarding boost itself."""
    turbo = Turbo(TURBO_NONE, firing_order_length=8)
    ambient = 313.0
    reading = None
    for _ in range(300):
        reading = turbo.tick(dt=0.01, rpm=4000.0, throttle=1.0, wastegate_duty=1.0, ambient_temp_k=ambient)
    assert reading.boost_pa == pytest.approx(0.0, abs=1e-6)
    assert reading.intake_air_temp_k == pytest.approx(ambient, abs=1e-6)


def test_higher_intake_air_temp_actually_reduces_torque():
    """Real gap found by direct manual testing: existing tests only checked
    that intake_air_temp_k *rises* under sustained boost, never that this
    rise actually costs anything -- the whole point of modeling it. Air
    density (and so air_mass_flow, and so torque) must scale down as
    intake_temp_k rises (ideal gas law: R_AIR*intake_temp_k is the
    denominator in ParametricEngine.compute()'s air_mass_flow)."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    kwargs = dict(rpm=4000.0, map_pa=180_000.0, target_afr=12.5, load_fraction=1.0,
                  octane=EA888_GEN3_IS20.knock_octane_requirement)
    cool = engine.compute(intake_temp_k=293.15, **kwargs)   # 20C
    hot = engine.compute(intake_temp_k=373.15, **kwargs)    # 100C
    assert hot.air_mass_flow_kg_s < cool.air_mass_flow_kg_s
    assert hot.net_torque_nm < cool.net_torque_nm


def test_twin_scroll_firing_order_spools_smoother_than_single_scroll():
    """The B58's twin-scroll grouping (from its actual firing order, not a
    hand-picked constant) should derive a pulse_quality > 1.0 -- smoother/
    quicker than the single-scroll-I4 baseline the existing tuned constants
    already assume (pulse_quality == 1.0)."""
    is20_like = Turbo(TURBO_IS20, firing_order_length=4)
    b58_like = Turbo(TURBO_B58, firing_order_length=6)
    assert is20_like._pulse_quality == pytest.approx(1.0)
    assert b58_like._pulse_quality > is20_like._pulse_quality


def test_single_scroll_six_cylinder_spools_peakier_than_reference():
    """Cramming 6 cylinders into ONE shared scroll (no twin-scroll split)
    should be peakier/slower than the single-scroll-I4 reference, the
    opposite direction from the twin-scroll case above -- same firing
    order length, different exhaust_scroll_groups, genuinely different
    pulse spacing (720/6=120deg vs the I4's 720/4=180deg)."""
    log_manifold_i6 = TurboSpec(
        name="single-scroll I6 (test only)",
        max_boost_bar=1.0,
        spool_midpoint_rpm=1000.0,
        exhaust_scroll_groups=1,
    )
    turbo = Turbo(log_manifold_i6, firing_order_length=6)
    assert turbo._pulse_quality < 1.0


def test_wastegate_duty_ramps_with_load_and_rpm(ecu):
    # Low load (partial throttle/light MAP) should hold back authority.
    ecu._last_load_fraction = 0.2  # simulate a light-load previous tick
    assert ecu.wastegate_duty(rpm=4000.0, throttle=1.0) == pytest.approx(0.0)
    ecu._last_load_fraction = 1.0  # WOT-equivalent previous tick
    assert ecu.wastegate_duty(rpm=4000.0, throttle=1.0) == pytest.approx(1.0)
    # ...and so should being just off idle, even at full load.
    idle = EA888_GEN3_IS20.idle_rpm
    assert ecu.wastegate_duty(rpm=idle, throttle=1.0) == pytest.approx(0.0)


def test_boost_target_override_clamps_out_of_range_values(ecu):
    """The session pre-clamps set_boost_target_percent()'s 0-100 input
    before it ever reaches the ECU, so this defensive clamp inside
    set_boost_target_fraction()/wastegate_duty() itself was never actually
    exercised by any existing test -- only ever hit in-range. Call the ECU
    directly, bypassing the session, with genuinely out-of-range values."""
    ecu.set_boost_target_fraction(1.5)
    assert ecu.wastegate_duty(rpm=4000.0, throttle=1.0) == pytest.approx(1.0)
    ecu.set_boost_target_fraction(-0.5)
    assert ecu.wastegate_duty(rpm=4000.0, throttle=1.0) == pytest.approx(0.0)


def test_afr_control_law_is_load_based_not_throttle_based(ecu):
    assert ecu.target_afr(load_fraction=0.0) == pytest.approx(14.7)
    assert ecu.target_afr(load_fraction=1.0) == pytest.approx(12.5)
    mid = ecu.target_afr(load_fraction=0.5)
    assert 12.5 < mid < 14.7


def test_rev_limiter_bounces_with_hysteresis_instead_of_flatlining(ecu):
    cut = ecu.rev_limiter_threshold_rpm
    band = ecu._rev_limiter_bounce_band_rpm

    assert not ecu.rev_limiter_active(cut - 1.0)
    assert ecu.rev_limiter_active(cut)  # crosses the cut point -> engages
    # Dropping back just under the cut point must NOT resume fuel yet --
    # that's the whole point of hysteresis (a real bounce, not chatter
    # right at one boundary).
    assert ecu.rev_limiter_active(cut - 1.0)
    assert ecu.rev_limiter_active(cut - band + 1.0)
    # Only drops below the *resume* point does it actually resume.
    assert not ecu.rev_limiter_active(cut - band - 1.0)


def test_dfco_reengage_rpm_is_pinned_to_a_real_value_not_just_self_consistent(ecu):
    """Regression test for a real gap found by mutation testing: the other
    DFCO test below reads ecu.dfco_reengage_rpm as its own reference point,
    so it would still "pass" even if the underlying 1.2x-idle constant were
    badly wrong (e.g. disabled by setting it to 100x) -- it only checks
    behavior is consistent *around whatever the threshold currently is*,
    never that the threshold itself is a sane, real value. Pin the actual
    number here, independent of what the property returns."""
    assert ecu.dfco_reengage_rpm == pytest.approx(EA888_GEN3_IS20.idle_rpm * 1.2)
    # And it must be a real, modest margin above idle -- not so large that
    # DFCO effectively never engages during normal operation.
    assert EA888_GEN3_IS20.idle_rpm < ecu.dfco_reengage_rpm < EA888_GEN3_IS20.idle_rpm * 2.0


def test_decel_fuel_cut_engages_above_idle_reengage_rpm_not_below(ecu):
    """Closed throttle near idle keeps the small idle-air-equivalent
    fueling (never stalls); closed throttle well above idle is a real DFCO
    fuel cut instead -- the same idle-air fueling at high rpm would flow
    (and burn) far more air than intended, the opposite of what a lifted
    throttle should do."""
    reengage = ecu.dfco_reengage_rpm

    near_idle = ecu.tick(dt=0.01, rpm=EA888_GEN3_IS20.idle_rpm, throttle=0.0)
    assert near_idle.target_afr > 0.0
    assert near_idle.engine.net_torque_nm > 0.0

    decelerating = ecu.tick(dt=0.01, rpm=reengage + 500.0, throttle=0.0)
    assert decelerating.target_afr == 0.0
    # Real engine braking: friction now genuinely exceeds the (zero) fueled
    # indicated torque, so net torque goes negative instead of flooring at 0.
    assert decelerating.engine.net_torque_nm < 0.0


def test_engine_braking_is_not_floored_at_zero():
    """ParametricEngine.compute() must let net torque go negative when
    friction exceeds indicated torque (e.g. zero fueling) -- flooring it at
    0 was what made a lifted throttle just coast on the dyno's own light
    drag instead of decelerating like a real engine on a dyno."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    reading = engine.compute(
        rpm=6000.0, map_pa=30_000.0, target_afr=0.0,
        load_fraction=0.0, intake_temp_k=313.0, octane=EA888_GEN3_IS20.knock_octane_requirement,
    )
    assert reading.fuel_mass_flow_kg_s == 0.0
    assert reading.net_torque_nm < 0.0


def test_session_coast_and_ecu_dfco_thresholds_never_drift_apart():
    """DynoSession._drive()'s coast-vs-PID-hold handoff must use the exact
    same rpm the ECU itself uses to decide DFCO -- if the PID engaged while
    the ECU was still fuel-cutting, its correction would stack on top of
    real engine-braking torque instead of trimming a small residual error,
    producing a physically-absurd combined brake torque."""
    from engine_sim import DynoSession

    session = DynoSession()
    session.loop.rpm = session.loop.ecu.dfco_reengage_rpm + 1.0
    reading = session._drive(dt=0.01, throttle_percent=0.0)
    assert session._coasting  # still above the shared threshold -> coasting, not PID-held
    assert reading.engine.net_torque_nm < 0.0  # ECU is genuinely still fuel-cutting here


def test_knock_penalty_reduces_torque_only_under_load_and_low_octane():
    engine = ParametricEngine(EA888_GEN3_IS20)
    required = EA888_GEN3_IS20.knock_octane_requirement

    def torque(load_fraction: float, octane: float) -> float:
        reading = engine.compute(
            rpm=4000.0, map_pa=180_000.0, target_afr=12.5,
            load_fraction=load_fraction, intake_temp_k=313.0, octane=octane,
        )
        return reading.net_torque_nm

    # Sufficient octane: no penalty regardless of load.
    assert torque(1.0, required) == pytest.approx(torque(1.0, required + 5.0))
    # Low octane under high load: real torque loss.
    assert torque(1.0, required - 10.0) < torque(1.0, required)
    # Low octane at zero load: knock risk requires cylinder pressure, so
    # low load shouldn't cost anything even on bad fuel.
    assert torque(0.0, required - 10.0) == pytest.approx(torque(0.0, required))


# --- Isolated parameter/physics unit tests -----------------------------
# Line coverage on this package is already ~99% -- these exist for a
# different reason: asserting specific per-parameter behaviors directly,
# in isolation, rather than only ever observing them indirectly through a
# full validated pull curve.

def test_fmep_friction_torque_matches_documented_formula():
    """FMEP -> torque: fmep = a + b*rpm + c*rpm^2, then torque = fmep*Vd/(4*pi)
    (ParametricEngine._friction_torque's own docstring) -- assert the actual
    numbers, not just that friction exists."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    spec = EA888_GEN3_IS20
    rpm = 4000.0
    fmep_pa = spec.friction_a_pa + spec.friction_b_pa_per_rpm * rpm + spec.friction_c_pa_per_rpm2 * rpm * rpm
    expected = fmep_pa * spec.displacement_m3 / (4.0 * pi)
    assert engine._friction_torque(rpm) == pytest.approx(expected)


def test_ve_never_drops_below_its_floor_even_far_past_redline():
    """The high-rpm falloff is a Gaussian-ish taper toward ve_peak *
    ve_floor_fraction -- it must approach that floor, never overshoot past
    it to zero, even evaluated well beyond redline."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    spec = EA888_GEN3_IS20
    floor = spec.ve_peak * spec.ve_floor_fraction
    far_past_redline = engine.volumetric_efficiency(spec.redline_rpm * 3.0)
    assert far_past_redline == pytest.approx(floor, abs=1e-6)
    assert far_past_redline >= floor - 1e-9


def test_combustion_efficiency_scales_torque_proportionally():
    """combustion_efficiency is a flat multiplier on fuel energy release --
    doubling it (holding everything else fixed) should scale indicated (and
    therefore net-above-friction) torque by the same factor."""
    base_spec = EA888_GEN3_IS20
    low = ParametricEngine(dataclasses.replace(base_spec, combustion_efficiency=0.5))
    high = ParametricEngine(dataclasses.replace(base_spec, combustion_efficiency=1.0))
    kwargs = dict(rpm=4000.0, map_pa=180_000.0, target_afr=12.5, load_fraction=1.0,
                  intake_temp_k=313.0, octane=base_spec.knock_octane_requirement)
    r_low = low.compute(**kwargs)
    r_high = high.compute(**kwargs)
    low_indicated = r_low.net_torque_nm + r_low.friction_torque_nm
    high_indicated = r_high.net_torque_nm + r_high.friction_torque_nm
    assert high_indicated == pytest.approx(2.0 * low_indicated)


def test_realism_factor_scales_torque_proportionally():
    """realism_factor is a flat multiplier on thermal efficiency -- same
    proportionality expectation as combustion_efficiency above."""
    base_spec = EA888_GEN3_IS20
    low = ParametricEngine(dataclasses.replace(base_spec, realism_factor=0.4))
    high = ParametricEngine(dataclasses.replace(base_spec, realism_factor=0.8))
    kwargs = dict(rpm=4000.0, map_pa=180_000.0, target_afr=12.5, load_fraction=1.0,
                  intake_temp_k=313.0, octane=base_spec.knock_octane_requirement)
    r_low = low.compute(**kwargs)
    r_high = high.compute(**kwargs)
    low_indicated = r_low.net_torque_nm + r_low.friction_torque_nm
    high_indicated = r_high.net_torque_nm + r_high.friction_torque_nm
    assert high_indicated == pytest.approx(2.0 * low_indicated)


def test_crank_inertia_changes_acceleration_rate_not_torque():
    """crank_inertia_kgm2 only affects how fast rpm changes for a given net
    torque (SimulationLoop's integration), not the torque number itself --
    a lighter crank should accelerate faster under identical net torque."""
    light_spec = dataclasses.replace(EA888_GEN3_IS20, crank_inertia_kgm2=0.10)
    heavy_spec = dataclasses.replace(EA888_GEN3_IS20, crank_inertia_kgm2=0.40)

    def build(spec):
        engine = ParametricEngine(spec)
        turbo = Turbo(TURBO_IS20, firing_order_length=4)
        ecu = ECU(engine, turbo)
        return SimulationLoop(ecu, DynoBrake())

    light_loop = build(light_spec)
    heavy_loop = build(heavy_spec)
    light_loop.rpm = heavy_loop.rpm = 3000.0
    r_light = light_loop.tick(dt=0.01, throttle=1.0, mode="free_accel")
    r_heavy = heavy_loop.tick(dt=0.01, throttle=1.0, mode="free_accel")
    # Same starting point, same throttle -- torque this instant is ~equal
    # (inertia doesn't feed back into torque calculation at all)...
    assert r_light.engine.net_torque_nm == pytest.approx(r_heavy.engine.net_torque_nm, rel=1e-6)
    # ...but the lighter crank must have accelerated further in the same dt.
    assert r_light.rpm > r_heavy.rpm


def test_turbo_spool_logistic_curve_is_half_spooled_at_its_midpoint():
    """_target_boost_pa's logistic curve should read exactly 50% of max
    boost at rpm == spool_midpoint_rpm (ignoring the first-order lag --
    this is the instantaneous target, not the boost gauge itself), the same
    curve shape manufacturers mean by 'full boost by N rpm.'"""
    turbo = Turbo(TURBO_IS20, firing_order_length=4)  # pulse_quality == 1.0, no width change
    target = turbo._target_boost_pa(rpm=TURBO_IS20.spool_midpoint_rpm, throttle=1.0, wastegate_duty=1.0)
    assert target == pytest.approx(TURBO_IS20.max_boost_bar * BAR_TO_PA * 0.5)


def test_turbo_spool_time_constant_matches_63_percent_rule():
    """A first-order lag reaches ~63.2% (1 - e^-1) of its target after one
    time constant -- verify Turbo.tick()'s boost lag actually behaves like
    the RC-style lag its docstring claims, not just 'eventually gets
    there.'"""
    turbo = Turbo(TURBO_IS20, firing_order_length=4)
    tau = TURBO_IS20.spool_time_constant_s
    dt = 0.001
    steps = int(tau / dt)
    reading = None
    for _ in range(steps):
        # rpm far above spool_midpoint_rpm so spool_fraction is ~1.0 and the
        # only thing left varying is the lag itself.
        reading = turbo.tick(dt=dt, rpm=8000.0, throttle=1.0, wastegate_duty=1.0)
    target = turbo._target_boost_pa(rpm=8000.0, throttle=1.0, wastegate_duty=1.0)
    assert reading.boost_pa / target == pytest.approx(1.0 - exp(-1.0), rel=0.02)


def test_pulse_quality_is_clamped_at_extremes():
    """_compute_pulse_quality must stay within its documented [0.7, 1.4]
    bounds even for degenerate inputs (more scroll groups than cylinders,
    a single-cylinder firing order) -- it modifies existing tuned constants,
    so it must never swing wide enough to invert or nullify them."""
    # Few pulses sharing one path -> wide spacing -> smoother/quicker ->
    # clamped at the upper bound.
    absurdly_split = TurboSpec(
        name="test", max_boost_bar=1.0, spool_midpoint_rpm=1000.0, exhaust_scroll_groups=8,
    )
    turbo = Turbo(absurdly_split, firing_order_length=4)  # 0.5 pulses/group -- way past the reference
    assert turbo._pulse_quality == pytest.approx(1.4)

    # Many pulses crammed into one shared path -> narrow spacing -> peakier/
    # slower -> clamped at the lower bound.
    log_manifold_v16 = TurboSpec(
        name="test", max_boost_bar=1.0, spool_midpoint_rpm=1000.0, exhaust_scroll_groups=1,
    )
    crowded = Turbo(log_manifold_v16, firing_order_length=16)
    assert crowded._pulse_quality == pytest.approx(0.7)


def test_dyno_brake_free_accel_mode_is_flat_parasitic_drag():
    brake = DynoBrake(parasitic_torque_nm=3.0)
    torque = brake.load_torque(mode="free_accel", rpm=5000.0, dt=0.01)
    assert torque == pytest.approx(3.0)


def test_dyno_brake_ramp_rpm_mode_matches_documented_formula():
    """ramp_rpm: required = engine_torque - inertia*alpha_target, clamped
    to >= 0 (a passive brake can only absorb torque, never drive the
    engine)."""
    brake = DynoBrake()
    alpha_target = 400.0 * (2.0 * pi / 60.0)  # 400 rpm/s
    expected = max(0.0, 250.0 - 0.3 * alpha_target)
    torque = brake.load_torque(
        mode="ramp_rpm", rpm=3000.0, dt=0.01,
        engine_torque_nm=250.0, total_inertia_kgm2=0.3, ramp_rate_rpm_s=400.0,
    )
    assert torque == pytest.approx(expected)

    # Not enough torque to hold the pace -- falls back to 0, never negative
    # (the brake can't push the engine along).
    starved = brake.load_torque(
        mode="ramp_rpm", rpm=1000.0, dt=0.01,
        engine_torque_nm=0.0, total_inertia_kgm2=0.3, ramp_rate_rpm_s=400.0,
    )
    assert starved == 0.0


def test_dyno_brake_hold_rpm_pid_accumulates_integral_and_resets_cleanly():
    brake = DynoBrake()
    # First call carries a derivative kick (prev_error starts at 0.0 while
    # the real error is already 100 -- see the dedicated kick test below),
    # so compare two calls *after* that transient, where error is steady
    # and only the integral term is still moving.
    t1 = brake.load_torque(mode="hold_rpm", rpm=900.0, dt=0.1, target_rpm=800.0)
    t2 = brake.load_torque(mode="hold_rpm", rpm=900.0, dt=0.1, target_rpm=800.0)
    t3 = brake.load_torque(mode="hold_rpm", rpm=900.0, dt=0.1, target_rpm=800.0)
    # t2 vs t3 only: steady error from here on, so derivative is 0 for both
    # and the integral term alone must keep growing call over call.
    assert t3 > t2

    brake.reset_pid()
    t_after_reset = brake.load_torque(mode="hold_rpm", rpm=900.0, dt=0.1, target_rpm=800.0)
    assert t_after_reset == pytest.approx(t1)  # back to the same as a fresh first call


def test_dyno_brake_reset_pid_seeds_derivative_baseline_to_avoid_kick():
    """Regression test for a real bug: reset_pid() defaulting prev_error to
    0.0 caused a one-tick derivative-kick torque spike whenever the actual
    error at reset time was large (DynoSession's coast-to-idle-hold
    handoff). Seeding it with the real error must make the derivative term
    read ~0 on the very next call."""
    brake = DynoBrake()
    real_error = 160.0
    brake.reset_pid(prev_error=real_error)
    torque = brake.load_torque(mode="hold_rpm", rpm=800.0 + real_error, dt=0.01, target_rpm=800.0)
    # No derivative kick: torque should reflect only P (+ a fresh I term for
    # this one tick), not a spurious D-term jump from an assumed-0 baseline.
    expected_without_kick = brake.parasitic_torque_nm + brake.pid_kp * real_error + brake.pid_ki * real_error * 0.01
    assert torque == pytest.approx(expected_without_kick, rel=1e-6)


@pytest.mark.parametrize("margin_below_cut", [1000.0, 500.0, 200.0])
def test_rev_limiter_never_engages_well_below_cut_rpm(ecu, margin_below_cut):
    cut = ecu.rev_limiter_threshold_rpm
    assert not ecu.rev_limiter_active(cut - margin_below_cut)


def test_bore_stroke_and_cam_lift_overlap_are_descriptive_only():
    """bore_mm, stroke_mm, CamSpec.intake_lift_mm and CamSpec.overlap_deg
    are stored per-engine facts but not consumed by any formula in the
    physics core (displacement_l/cylinders/compression_ratio and
    intake_duration_deg are what actually drive VE/torque) -- this locks in
    that current design intent so a future change that starts consuming one
    of them updates this test deliberately instead of by accident."""
    engine = ParametricEngine(EA888_GEN3_IS20)
    kwargs = dict(rpm=4000.0, map_pa=180_000.0, target_afr=12.5, load_fraction=1.0,
                  intake_temp_k=313.0, octane=EA888_GEN3_IS20.knock_octane_requirement)
    baseline = engine.compute(**kwargs)

    varied_spec = dataclasses.replace(
        EA888_GEN3_IS20,
        bore_mm=999.0,
        stroke_mm=999.0,
        cam=dataclasses.replace(EA888_GEN3_IS20.cam, intake_lift_mm=999.0, overlap_deg=999.0),
    )
    varied = ParametricEngine(varied_spec).compute(**kwargs)
    assert varied.net_torque_nm == pytest.approx(baseline.net_torque_nm)
    assert varied.ve == pytest.approx(baseline.ve)


# --- Turbo variety (TURBO_CHOICES_BY_CAR) -----------------------------

def test_is38_max_boost_is_realistic_not_the_old_placeholder():
    """Regression guard: TURBO_IS38 used to carry a decorative placeholder
    of 3.35 bar (~49psi -- nothing real runs anywhere near that), harmless
    back when nothing constructed it. Now that it's a real selectable
    option (the "IS38 hybrid swap"), it must stay in a plausible tuned-
    turbo range."""
    assert 1.0 < TURBO_IS38.max_boost_bar < 2.5


@pytest.mark.parametrize("car_key", ["mk7_gti", "f30_340i", "c6_corvette"])
def test_every_turbo_choice_has_a_unique_max_boost(car_key):
    """Sanity check on the data itself: if two options in the same engine's
    list carried the same max_boost_bar, they wouldn't actually be
    offering a meaningfully different choice."""
    specs = [spec for _, spec, _ in TURBO_CHOICES_BY_CAR[car_key]]
    boosts = [s.max_boost_bar for s in specs]
    assert len(boosts) == len(set(boosts))


def test_b58_big_single_and_ea888_big_single_are_genuinely_single_scroll():
    """The two aftermarket "big single" upgrades are documented as
    abandoning the factory twin-scroll housing -- lock in that they're
    actually configured that way (exhaust_scroll_groups=1), not just
    described that way in a docstring."""
    assert TURBO_B58_BIG_SINGLE.exhaust_scroll_groups == 1
    # EA888's only ever been single-scroll (stock IS20 already is), so its
    # big-single hybrid uses the class default rather than needing an
    # explicit override -- confirm that default is still 1.
    assert TURBO_EA888_BIG_SINGLE_HYBRID.exhaust_scroll_groups == 1


def test_b58tu_and_ls2_twin_stay_multi_scroll():
    """Counterpoint to the above: the B58TU keeps BMW's factory twin-scroll
    housing (bigger unit, same layout), and a twin-turbo LS kit is one
    turbo per bank of 4 cylinders -- the same "half the cylinders feed one
    turbine path" shape as twin-scroll."""
    assert TURBO_B58_TU.exhaust_scroll_groups == 2
    assert TURBO_LS2_TWIN.exhaust_scroll_groups == 2


def test_bigger_turbo_options_spool_later_than_stock():
    """Real-world direction check: within each engine's list, a bigger
    max_boost_bar option should spool_midpoint_rpm later than the stock
    unit -- physically larger turbines take more exhaust energy/rpm to
    spin up, the same trait TURBO_IS38's own docstring describes."""
    for car_key in ("mk7_gti", "f30_340i", "c6_corvette"):
        choices = TURBO_CHOICES_BY_CAR[car_key]
        stock_spec = choices[0][1]
        for _, spec, name in choices[1:]:
            assert spec.max_boost_bar > stock_spec.max_boost_bar, name
            assert spec.spool_midpoint_rpm >= stock_spec.spool_midpoint_rpm, name
