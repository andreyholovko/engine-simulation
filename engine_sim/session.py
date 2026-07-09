"""DynoSession: the one interface every frontend talks to.

The CLI and the Godot UI render and drive things differently -- but they
should never each construct their own Engine/Turbo/ECU/SimulationLoop by
hand, and never each hand-roll their own flattening of a DynoReading into
display fields. Do that once, here, so every consumer is provably looking at
the same simulation instead of three copies that happen to agree today and
can silently drift tomorrow.

`DynoSession()` with no arguments is *the* canonical dyno: EA888 Gen3 (IS20),
the preset validated against VW's own published figures. Pass a different
engine_spec/turbo_spec only for a deliberately different configuration --
everyone who just wants "the dyno" should call `DynoSession()` and get
identical behavior.
"""

from dataclasses import dataclass
from typing import Optional

from engine_sim.core import DynoBrake, DynoReading, ECU, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import EA888_GEN3_IS20, ENGINE_CHOICES, TURBO_CHOICES_BY_ENGINE, TURBO_IS20
from engine_sim.specs import EngineSpec, TurboSpec


@dataclass
class DynoSnapshot:
    """One tick's worth of everything a dyno display needs -- the flattened,
    display-ready shape the CLI and the Godot controller each used to build
    by hand from a raw DynoReading. Built once, here, instead."""

    time_s: float
    rpm: float
    throttle_percent: float
    torque_nm: float
    power_kw: float
    power_hp: float
    boost_bar: float
    target_boost_bar: float
    spool_fraction: float
    afr_actual: float
    volumetric_efficiency: float
    air_mass_flow_g_s: float
    fuel_mass_flow_g_s: float
    effective_compression_ratio: float
    intake_air_temp_k: float
    rev_limiter_active: bool
    power_pull_active: bool


class DynoSession:
    def __init__(
        self,
        engine_spec: EngineSpec = EA888_GEN3_IS20,
        turbo_spec: TurboSpec = TURBO_IS20,
        brake: Optional[DynoBrake] = None,
        engine_key: str = "ea888_gen3_is20",
    ):
        engine = ParametricEngine(engine_spec)
        turbo = Turbo(turbo_spec, firing_order_length=len(engine_spec.firing_order_resolved))
        ecu = ECU(engine, turbo)
        self.loop = SimulationLoop(ecu, brake if brake is not None else DynoBrake())
        self._power_pull_active = False
        # True while off-throttle rpm is decelerating naturally toward idle
        # (see _drive()) rather than being actively PID-held there yet --
        # tracked so the PID's integral only resets once, at the moment it
        # actually takes over, not stale from whatever it was doing before.
        self._coasting = False
        self.idle_rpm_target = engine_spec.idle_rpm
        self.engine_key = engine_key
        # Stock/default turbo for this engine by TURBO_CHOICES_BY_ENGINE
        # convention (index 0) -- only meaningful when engine_key is an
        # actual ENGINE_CHOICES key, same assumption the default args make.
        turbo_choices = TURBO_CHOICES_BY_ENGINE.get(engine_key, [])
        self.turbo_key = turbo_choices[0][0] if turbo_choices else None

    @property
    def ecu(self) -> ECU:
        return self.loop.ecu

    @property
    def is_power_pull_active(self) -> bool:
        return self._power_pull_active

    @staticmethod
    def list_engine_choices() -> list[tuple[str, str]]:
        """[(key, display_name), ...] for every engine select_engine() accepts."""
        return [(key, name) for key, (_, _, name) in ENGINE_CHOICES.items()]

    def select_engine(self, key: str) -> None:
        """Swap to a different engine+its stock turbo from ENGINE_CHOICES,
        mid-session. Rebuilds Engine/Turbo/ECU (a different engine means
        different specs driving them) but keeps the same DynoBrake -- the
        dyno's own inertia/drag isn't a property of whichever engine happens
        to be mounted. Always resets to that engine's own stock turbo (see
        TURBO_CHOICES_BY_ENGINE) -- a turbo choice from the previous engine
        isn't necessarily valid, or even meaningful, on a different one."""
        if key not in ENGINE_CHOICES:
            raise ValueError(f"unknown engine choice: {key!r}. Available: {sorted(ENGINE_CHOICES)}")
        engine_spec, turbo_spec, _ = ENGINE_CHOICES[key]
        engine = ParametricEngine(engine_spec)
        turbo = Turbo(turbo_spec, firing_order_length=len(engine_spec.firing_order_resolved))
        ecu = ECU(engine, turbo)
        self.loop = SimulationLoop(ecu, self.loop.brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self._coasting = False
        self.idle_rpm_target = engine_spec.idle_rpm
        self.engine_key = key
        turbo_choices = TURBO_CHOICES_BY_ENGINE.get(key, [])
        self.turbo_key = turbo_choices[0][0] if turbo_choices else None

    def select_engine_by_index(self, index: int) -> None:
        """Same as select_engine(), addressed by position in ENGINE_CHOICES
        (dict insertion order) instead of by string key. Exists for
        boundaries where passing/returning `str` is a real risk -- py4godot's
        own examples only ever show int/float/bool/Vector3 properties, never
        str, so the Godot-facing side of engine selection goes through this
        instead of the key-based method."""
        keys = list(ENGINE_CHOICES.keys())
        if not 0 <= index < len(keys):
            raise ValueError(f"engine index {index} out of range (0..{len(keys) - 1})")
        self.select_engine(keys[index])

    @staticmethod
    def list_turbo_choices_for_engine(engine_key: str) -> list[tuple[str, str]]:
        """[(key, display_name), ...] of turbo choices for a given engine key
        -- each engine has its own list (see TURBO_CHOICES_BY_ENGINE), so
        this doesn't assume "the current engine" the way an instance method
        would; useful for a UI populating a picker before/without switching."""
        return [(key, name) for key, _, name in TURBO_CHOICES_BY_ENGINE.get(engine_key, [])]

    def list_turbo_choices(self) -> list[tuple[str, str]]:
        """Turbo choices for whichever engine is *currently* selected."""
        return self.list_turbo_choices_for_engine(self.engine_key)

    def select_turbo(self, key: str) -> None:
        """Swap to a different turbo from the CURRENT engine's own
        TURBO_CHOICES_BY_ENGINE list, keeping the same EngineSpec -- this is
        the actual point of the feature: watch one validated engine produce
        a genuinely different torque/power curve and spool timing under a
        different turbo, the way a real turbo swap does, without also
        changing which engine is "mounted." Aborts any in-progress pull and
        resets to idle, same as select_engine()."""
        choices = TURBO_CHOICES_BY_ENGINE.get(self.engine_key, [])
        turbo_spec = next((spec for k, spec, _ in choices if k == key), None)
        if turbo_spec is None:
            available = [k for k, _, _ in choices]
            raise ValueError(
                f"unknown turbo choice {key!r} for engine {self.engine_key!r}. Available: {available}"
            )
        engine_spec = self.loop.ecu.engine.spec
        engine = ParametricEngine(engine_spec)
        turbo = Turbo(turbo_spec, firing_order_length=len(engine_spec.firing_order_resolved))
        ecu = ECU(engine, turbo)
        self.loop = SimulationLoop(ecu, self.loop.brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self._coasting = False
        self.turbo_key = key

    def select_turbo_by_index(self, index: int) -> None:
        """Same as select_turbo(), addressed by position in the current
        engine's TURBO_CHOICES_BY_ENGINE list instead of by string key --
        same str-across-py4godot-boundary reasoning as
        select_engine_by_index()."""
        choices = TURBO_CHOICES_BY_ENGINE.get(self.engine_key, [])
        if not 0 <= index < len(choices):
            raise ValueError(
                f"turbo index {index} out of range (0..{len(choices) - 1}) for engine {self.engine_key!r}"
            )
        self.select_turbo(choices[index][0])

    # --- control surface: the only knobs any consumer should touch ---

    def set_afr_override(self, afr: Optional[float]) -> None:
        """None restores the ECU's own load-based control law."""
        self.loop.ecu.set_target_afr(afr)

    def set_boost_target_percent(self, percent: Optional[float]) -> None:
        """0-100, as a percentage of the turbo's max boost. None restores
        full wastegate authority."""
        fraction = None if percent is None else max(0.0, min(1.0, percent / 100.0))
        self.loop.ecu.set_boost_target_fraction(fraction)

    def set_octane_override(self, octane: Optional[float]) -> None:
        """Pump octane the engine is actually running on. None restores the
        engine's own knock_octane_requirement (no knock penalty)."""
        self.loop.ecu.set_fuel_octane(octane)

    def start_power_pull(self) -> None:
        """Reset to idle/cold-boost and start recording a run -- the actual
        sweep is driven live by whatever throttle_percent the caller passes
        to tick() each frame from here on (a vertical throttle slider, a
        held key, etc.), the way a real inertia-dyno pull is driven by the
        operator's own right foot rather than an artificially paced sweep."""
        self.loop.rpm = self.loop.ecu.engine.spec.idle_rpm
        self.loop.time_s = 0.0
        self.loop.brake.reset_pid()
        self.loop.ecu.turbo.reset()
        self._power_pull_active = True
        self._coasting = False

    def stop_power_pull(self) -> None:
        self._power_pull_active = False

    # A real engine dyno loads the engine hard during a pull -- that's the
    # whole point of the machine -- rather than letting it free-rev against
    # nothing but bearing drag. This is the pace the brake actively resists
    # to hold at full throttle (matches SimulationLoop.run_power_pull()'s
    # own default, and real dyno sweep rates -- see core/dyno.py); at
    # partial throttle mid-pull the target pace scales down with it, so the
    # operator's own throttle position still controls the sweep.
    _PULL_MAX_RAMP_RATE_RPM_S = 400.0

    def _drive(self, dt: float, throttle_percent: float) -> DynoReading:
        """Advance one tick for a given live throttle position (0-100).

        Above zero throttle during an active pull: `ramp_rpm` mode -- the
        brake actively resists the engine to hold a controlled sweep pace
        (scaled by throttle position), the way a real engine dyno's brake
        genuinely loads the engine rather than letting it free-rev against
        nothing. Above zero throttle otherwise (casual free-play, not
        recording a run): free_accel, RPM responds to the engine's own net
        torque against just the dyno's light parasitic drag and inertia.

        At zero throttle, well above idle: still free_accel, so the engine
        decelerates under its own engine braking (friction now genuinely
        exceeds the near-zero off-throttle indicated torque -- see
        ParametricEngine.compute()) plus the dyno's rotating inertia and
        parasitic drag, the way a real car actually decelerates on a dyno
        when you lift -- not an artificial snap back to a target.

        At zero throttle, near idle: hands off to the dyno brake's hold_rpm
        PID, which pins it at idle_rpm_target the way a real idle is also
        held against accessory load (see DynoBrake) -- resetting the PID's
        integral exactly once, at the moment it takes over, not every tick
        it's active. This handoff uses the ECU's own dfco_reengage_rpm, the
        same number that decides whether the ECU itself is still fuel-
        cutting -- if the PID engaged first, its correction would stack on
        top of real engine-braking torque instead of trimming a small
        residual once the engine's back to idle-equivalent fueling.
        """
        if throttle_percent > 1e-6:
            self._coasting = False
            throttle = min(throttle_percent, 100.0) / 100.0
            if self._power_pull_active:
                ramp_rate = self._PULL_MAX_RAMP_RATE_RPM_S * throttle
                return self.loop.tick(dt, throttle=throttle, mode="ramp_rpm", ramp_rate_rpm_s=ramp_rate)
            return self.loop.tick(dt, throttle=throttle, mode="free_accel")

        idle_target = self.idle_rpm_target
        if self.loop.rpm > self.loop.ecu.dfco_reengage_rpm:
            self._coasting = True
            return self.loop.tick(dt, throttle=0.0, mode="free_accel")

        if self._coasting:
            # Seed the derivative baseline with the *real* current error
            # (rpm is still meaningfully above idle_target here) -- leaving
            # it at the reset() default of 0.0 would make this tick's
            # derivative term see a fake jump from 0 to the real error,
            # spiking brake torque well beyond even the (already firm)
            # proportional correction.
            self.loop.brake.reset_pid(prev_error=self.loop.rpm - idle_target)
        self._coasting = False
        return self.loop.tick(dt, throttle=0.0, mode="hold_rpm", target_rpm=idle_target)

    def tick(self, dt: float, throttle_percent: float = 0.0) -> DynoSnapshot:
        """Advance one tick (see _drive() for the off-throttle coast-down
        vs. idle-hold split). While a pull is "active" this is exactly the
        same physics, just tracked/recorded and auto-ending at the rev
        limiter."""
        reading = self._drive(dt, throttle_percent)
        if self._power_pull_active and self.loop.rpm >= self.loop.ecu.rev_limiter_threshold_rpm:
            self._power_pull_active = False
        return self._snapshot(reading, throttle_percent=throttle_percent, power_pull_active=self._power_pull_active)

    def run_power_pull(self, ramp_rate_rpm_s: float = 400.0, dt: float = 0.01) -> list[DynoSnapshot]:
        """Batch convenience for consumers that don't need live per-frame
        updates (the CLI's `sweep`): the full paced WOT curve in one call."""
        readings = self.loop.run_power_pull(dt=dt, ramp_rate_rpm_s=ramp_rate_rpm_s)
        self._power_pull_active = False
        return [self._snapshot(r, throttle_percent=100.0, power_pull_active=True) for r in readings]

    def _snapshot(self, reading: DynoReading, throttle_percent: float, power_pull_active: bool) -> DynoSnapshot:
        return DynoSnapshot(
            time_s=reading.time_s,
            rpm=reading.rpm,
            throttle_percent=throttle_percent,
            torque_nm=reading.engine.net_torque_nm,
            power_kw=reading.power_kw,
            power_hp=reading.power_hp,
            boost_bar=reading.turbo.boost_bar,
            target_boost_bar=reading.turbo.target_boost_bar,
            spool_fraction=reading.turbo.spool_fraction,
            afr_actual=reading.engine.afr_actual,
            volumetric_efficiency=reading.engine.ve,
            air_mass_flow_g_s=reading.engine.air_mass_flow_kg_s * 1000.0,
            fuel_mass_flow_g_s=reading.engine.fuel_mass_flow_kg_s * 1000.0,
            effective_compression_ratio=reading.engine.effective_compression_ratio,
            intake_air_temp_k=reading.engine.intake_temp_k,
            rev_limiter_active=self.loop.ecu.rev_limiter_active(reading.rpm),
            power_pull_active=power_pull_active,
        )
