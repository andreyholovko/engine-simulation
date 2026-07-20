"""DynoSession's `surface` param ("dyno" vs "road") and RollerSpec's aero
downforce term -- both added to close the gap between the sim's simulated
0-100 time and a real Mk7 GTI's published figure.

Root cause found: the drag-strip scene (drag_controller.py) reused the same
RollerSpec as the physical chassis-dyno bench (dyno_controller.py), which
carries a real dyno drum's own rotational inertia (inertia_kgm2=80.0) as
resistance. On an open road there's no such drum, but reflected through
RollerSpec's own math (mass_equivalent = inertia_kgm2 / radius_m**2) that
drum inertia was still adding ~1280kg of phantom vehicle mass -- silently
making the open-road drag strip nearly twice as heavy as the car it claims
to simulate. ROLLER_ROAD_BY_DRIVETRAIN_LAYOUT (inertia_kgm2=0.0, otherwise
identical) fixes this for `surface="road"` while leaving the actual dyno
bench (`surface="dyno"`, the default) untouched -- a real bench really does
have to fight a real drum's inertia.
"""

import pytest

from engine_sim import DynoSession
from engine_sim.presets import ROLLER_BY_DRIVETRAIN_LAYOUT, ROLLER_ROAD_BY_DRIVETRAIN_LAYOUT


def test_default_surface_is_dyno():
    session = DynoSession()
    assert session.surface == "dyno"


def test_dyno_surface_rejects_unknown_value():
    with pytest.raises(ValueError):
        DynoSession(surface="orbit")


def test_dyno_surface_uses_the_real_drum_inertia():
    session = DynoSession(car_key="mk7_gti", surface="dyno")
    session.select_dyno_mode("chassis")
    assert session.drivetrain.roller_spec.inertia_kgm2 == ROLLER_BY_DRIVETRAIN_LAYOUT["fwd"].inertia_kgm2
    assert session.drivetrain.roller_spec.inertia_kgm2 > 0.0


def test_road_surface_has_zero_drum_inertia():
    session = DynoSession(car_key="mk7_gti", surface="road")
    session.select_dyno_mode("chassis")
    assert session.drivetrain.roller_spec.inertia_kgm2 == 0.0


def test_road_and_dyno_surfaces_agree_on_everything_except_drum_inertia():
    """The whole point of splitting these into two RollerSpec families is
    that ONLY the drum inertia differs -- grip, curb weight, drag,
    downforce should all stay identical, or a road/dyno swap would be
    silently changing more than "is there a physical roller"."""
    for layout in ("fwd", "rwd", "awd"):
        dyno_roller = ROLLER_BY_DRIVETRAIN_LAYOUT[layout]
        road_roller = ROLLER_ROAD_BY_DRIVETRAIN_LAYOUT[layout]
        assert road_roller.inertia_kgm2 == 0.0
        assert dyno_roller.inertia_kgm2 > 0.0
        assert road_roller.radius_m == dyno_roller.radius_m
        assert road_roller.vehicle_mass_kg == dyno_roller.vehicle_mass_kg
        assert road_roller.parasitic_torque_nm == dyno_roller.parasitic_torque_nm
        assert road_roller.driven_axle_weight_fraction == dyno_roller.driven_axle_weight_fraction
        assert road_roller.drag_coefficient == dyno_roller.drag_coefficient
        assert road_roller.frontal_area_m2 == dyno_roller.frontal_area_m2
        assert road_roller.downforce_coefficient == dyno_roller.downforce_coefficient


def _time_to_100_kmh_s(session: DynoSession) -> float:
    dt = 0.01
    t = 0.0
    for _ in range(int(30.0 / dt)):
        snapshot = session.tick(dt, throttle_percent=100.0)
        t += dt
        if snapshot.vehicle_speed_kmh >= 100.0:
            return t
    raise AssertionError("never reached 100 km/h within 30s")


def test_road_surface_launches_meaningfully_faster_than_dyno_surface():
    """Same car, same tire, same transmission, same WOT launch -- the only
    difference is whether a phantom dyno drum's inertia is along for the
    ride. Removing it should roughly halve the 0-100 time (empirically:
    ~14.3s on "dyno" vs ~7.7s on "road"), not just nudge it."""
    times = {}
    for surface in ("dyno", "road"):
        session = DynoSession(car_key="mk7_gti", surface=surface)
        session.select_dyno_mode("chassis")
        session.select_transmission("auto_6speed")
        session.select_tire("sport")
        times[surface] = _time_to_100_kmh_s(session)

    assert times["road"] < times["dyno"] * 0.7
    # Sanity bound so a future change can't silently reintroduce a huge
    # regression (or an equally-broken "too fast") without a test noticing.
    assert 5.0 < times["road"] < 11.0


def test_downforce_grows_normal_force_with_speed():
    session = DynoSession(car_key="mk7_gti", surface="road")
    session.select_dyno_mode("chassis")
    drivetrain = session.drivetrain

    drivetrain.omega_wheel = 0.0
    drivetrain.omega_roller = 0.0
    static_n = drivetrain._normal_force_n

    drivetrain.omega_roller = (200.0 / 3.6) / drivetrain.roller_spec.radius_m
    fast_n = drivetrain._normal_force_n

    assert fast_n > static_n


def test_downforce_is_small_relative_to_static_weight_at_highway_speed():
    """The point of downforce_coefficient's small default is that it stays
    a minor effect for a stock street car up to normal speeds -- it's not
    meant to be doing the heavy lifting on the 0-100 fix (that's the
    drum-inertia removal above)."""
    session = DynoSession(car_key="mk7_gti", surface="road")
    session.select_dyno_mode("chassis")
    drivetrain = session.drivetrain

    drivetrain.omega_wheel = 0.0
    drivetrain.omega_roller = 0.0
    static_n = drivetrain._normal_force_n

    drivetrain.omega_roller = (100.0 / 3.6) / drivetrain.roller_spec.radius_m
    highway_n = drivetrain._normal_force_n

    assert highway_n < static_n * 1.05
