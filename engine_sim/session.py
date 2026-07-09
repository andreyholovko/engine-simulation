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
from typing import Optional, Union

from engine_sim.core import (
    AutomaticDrivetrain,
    ChassisDynoLoop,
    ChassisDynoReading,
    DynoBrake,
    DynoReading,
    Drivetrain,
    ECU,
    ParametricEngine,
    SimulationLoop,
    Turbo,
)
from engine_sim.presets import (
    CLUTCH_PERFORMANCE,
    EA888_GEN3_IS20,
    ENGINE_CHOICES,
    ROLLER_STANDARD,
    TIRE_CHOICES,
    TRANSMISSION_CHOICES,
    TURBO_CHOICES_BY_ENGINE,
    TURBO_IS20,
)
from engine_sim.specs import AutomaticTransmissionSpec, EngineSpec, TurboSpec


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
    # Chassis-dyno-only fields (see ChassisDynoLoop/Drivetrain) -- default to
    # crank-mode-neutral values so every existing crank-mode snapshot stays
    # meaningful without a caller needing to branch on dyno_mode first.
    dyno_mode: str = "crank"
    gear: int = 0
    shifting: bool = False
    wheel_rpm: float = 0.0
    vehicle_speed_kmh: float = 0.0
    slip_ratio: float = 0.0
    clutch_engagement: float = 1.0
    clutch_locked: bool = False
    # Torque/power actually delivered to the roller -- what a real chassis
    # dyno graph plots (derived from roller acceleration, not read off the
    # engine crank, so clutch/tire slip show up here as a real shortfall).
    # In crank mode there's no separate wheel to speak of, so _snapshot()
    # sets these equal to torque_nm/power_kw there -- a consumer (like the
    # Godot graph) can plot wheel_torque_nm/wheel_power_kw unconditionally
    # and get the right curve either way, without branching on dyno_mode.
    wheel_torque_nm: float = 0.0
    wheel_power_kw: float = 0.0


class DynoSession:
    def __init__(
        self,
        engine_spec: EngineSpec = EA888_GEN3_IS20,
        turbo_spec: TurboSpec = TURBO_IS20,
        brake: Optional[DynoBrake] = None,
        engine_key: str = "ea888_gen3_is20",
    ):
        # dyno_mode/tire_key/transmission_key must exist before _build_loop()
        # is first called (it reads them to decide what kind of loop to
        # construct).
        self.dyno_mode = "crank"
        self.tire_key = "street"
        self.transmission_key = "manual_6speed"
        self.drivetrain: Optional[Union[Drivetrain, AutomaticDrivetrain]] = None

        self.loop = self._build_loop(engine_spec, turbo_spec, brake if brake is not None else DynoBrake())
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

    def _build_loop(
        self, engine_spec: EngineSpec, turbo_spec: TurboSpec, brake: DynoBrake
    ) -> Union[SimulationLoop, ChassisDynoLoop]:
        """The one place every select_*() method that touches the engine or
        turbo goes through, so a chassis-mode session stays a chassis-mode
        session across an engine/turbo swap instead of silently reverting to
        a crank loop. Side effect: (re)sets self.drivetrain to match --
        None in crank mode, a fresh Drivetrain or AutomaticDrivetrain
        (current tire_key/transmission_key) in chassis mode. Which class
        depends entirely on the type of spec TRANSMISSION_CHOICES hands
        back for transmission_key -- an AutomaticTransmissionSpec carries
        its own TorqueConverterSpec, so that alone is enough to tell them
        apart (see AutomaticDrivetrain's docstring for why it needs a
        different class rather than a flag on Drivetrain)."""
        engine = ParametricEngine(engine_spec)
        turbo = Turbo(turbo_spec, firing_order_length=len(engine_spec.firing_order_resolved))
        ecu = ECU(engine, turbo)
        if self.dyno_mode == "crank":
            self.drivetrain = None
            return SimulationLoop(ecu, brake)
        tire_spec, _ = TIRE_CHOICES[self.tire_key]
        transmission_spec, _ = TRANSMISSION_CHOICES[self.transmission_key]
        if isinstance(transmission_spec, AutomaticTransmissionSpec):
            self.drivetrain = AutomaticDrivetrain(transmission_spec, CLUTCH_PERFORMANCE, tire_spec, ROLLER_STANDARD)
        else:
            self.drivetrain = Drivetrain(transmission_spec, CLUTCH_PERFORMANCE, tire_spec, ROLLER_STANDARD)
        return ChassisDynoLoop(ecu, brake, self.drivetrain)

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
        self.loop = self._build_loop(engine_spec, turbo_spec, self.loop.brake)
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
        self.loop = self._build_loop(engine_spec, turbo_spec, self.loop.brake)
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

    def select_dyno_mode(self, mode: str) -> None:
        """Switch between the crank dyno (loads the engine directly -- no
        transmission, no wheels) and the chassis dyno (drives through a
        clutch, manual gearbox and a tire slipping against the roller -- see
        ChassisDynoLoop/Drivetrain). Rebuilds the loop and aborts any
        in-progress pull, same reset-on-switch convention as
        select_engine()/select_turbo(); a no-op if already in that mode
        (so a UI toggle can call this freely without resetting an
        in-progress chassis run by accident)."""
        if mode not in ("crank", "chassis"):
            raise ValueError(f"unknown dyno mode: {mode!r}. Available: ['crank', 'chassis']")
        if mode == self.dyno_mode:
            return
        engine_spec = self.loop.ecu.engine.spec
        turbo_spec = self.loop.ecu.turbo.spec
        brake = self.loop.brake
        self.dyno_mode = mode
        self.loop = self._build_loop(engine_spec, turbo_spec, brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self._coasting = False
        self.idle_rpm_target = engine_spec.idle_rpm

    @staticmethod
    def list_tire_choices() -> list[tuple[str, str]]:
        """[(key, display_name), ...] for every tire select_tire() accepts."""
        return [(key, name) for key, (_, name) in TIRE_CHOICES.items()]

    def select_tire_by_index(self, index: int) -> None:
        """Same as select_tire(), addressed by position in TIRE_CHOICES
        instead of by string key -- same str-across-py4godot-boundary
        reasoning as select_engine_by_index()."""
        keys = list(TIRE_CHOICES.keys())
        if not 0 <= index < len(keys):
            raise ValueError(f"tire index {index} out of range (0..{len(keys) - 1})")
        self.select_tire(keys[index])

    def select_tire(self, key: str) -> None:
        """Swap tire size/compound in chassis mode -- same 'swap one axis'
        pattern as select_turbo(): watch the same car's slip behavior change
        under a different tire without touching the engine or transmission.
        Always remembered even outside chassis mode (so switching to chassis
        mode later starts on the tire last chosen); only rebuilds the live
        loop (aborting any in-progress pull) when chassis mode is already
        active."""
        if key not in TIRE_CHOICES:
            raise ValueError(f"unknown tire choice: {key!r}. Available: {sorted(TIRE_CHOICES)}")
        self.tire_key = key
        if self.dyno_mode != "chassis":
            return
        engine_spec = self.loop.ecu.engine.spec
        turbo_spec = self.loop.ecu.turbo.spec
        self.loop = self._build_loop(engine_spec, turbo_spec, self.loop.brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self._coasting = False

    @staticmethod
    def list_transmission_choices() -> list[tuple[str, str]]:
        """[(key, display_name), ...] for every transmission
        select_transmission() accepts -- currently a manual gearbox and a
        torque-converter automatic (see TRANSMISSION_CHOICES)."""
        return [(key, name) for key, (_, name) in TRANSMISSION_CHOICES.items()]

    def select_transmission_by_index(self, index: int) -> None:
        """Same as select_transmission(), addressed by position in
        TRANSMISSION_CHOICES -- same str-across-py4godot-boundary reasoning
        as select_engine_by_index()."""
        keys = list(TRANSMISSION_CHOICES.keys())
        if not 0 <= index < len(keys):
            raise ValueError(f"transmission index {index} out of range (0..{len(keys) - 1})")
        self.select_transmission(keys[index])

    def select_transmission(self, key: str) -> None:
        """Swap manual <-> automatic in chassis mode -- same 'swap one axis'
        pattern as select_tire()/select_turbo(). Always remembered even
        outside chassis mode; only rebuilds the live loop (aborting any
        in-progress pull, resetting to neutral/1st) when chassis mode is
        already active."""
        if key not in TRANSMISSION_CHOICES:
            raise ValueError(f"unknown transmission choice: {key!r}. Available: {sorted(TRANSMISSION_CHOICES)}")
        self.transmission_key = key
        if self.dyno_mode != "chassis":
            return
        engine_spec = self.loop.ecu.engine.spec
        turbo_spec = self.loop.ecu.turbo.spec
        self.loop = self._build_loop(engine_spec, turbo_spec, self.loop.brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self._coasting = False

    def shift_up(self) -> None:
        """The '+' shift button -- no-op outside chassis mode, before a
        Drivetrain exists, or when the current transmission is automatic
        (its own throttle/rpm shift map decides gears -- see
        AutomaticDrivetrain._decide_shift() -- there's no manual override
        button for it, same as a real automatic has no clutch pedal)."""
        if self.drivetrain is not None and not isinstance(self.drivetrain, AutomaticDrivetrain):
            self.drivetrain.request_shift(1)

    def shift_down(self) -> None:
        """The '-' shift button, symmetric with shift_up()."""
        if self.drivetrain is not None and not isinstance(self.drivetrain, AutomaticDrivetrain):
            self.drivetrain.request_shift(-1)

    @property
    def current_gear(self) -> int:
        return self.drivetrain.gear if self.drivetrain is not None else 0

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
        operator's own right foot rather than an artificially paced sweep.
        In chassis mode this also resets the drivetrain to neutral/stationary
        (see Drivetrain.reset()) -- otherwise the engine would snap back to
        idle while the wheel/roller/gear kept whatever state they had from
        before, an inconsistent reset no real dyno produces."""
        self.loop.rpm = self.loop.ecu.engine.spec.idle_rpm
        self.loop.time_s = 0.0
        self.loop.brake.reset_pid()
        self.loop.ecu.turbo.reset()
        if self.drivetrain is not None:
            self.drivetrain.reset()
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

    def _drive(self, dt: float, throttle_percent: float) -> Union[DynoReading, ChassisDynoReading]:
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
        updates (the CLI's `sweep`): the full paced WOT curve in one call.
        Crank-mode only -- a paced auto-sweep doesn't have an in-gear
        equivalent (see ChassisDynoLoop's docstring); run a chassis session
        live via tick() instead."""
        if not isinstance(self.loop, SimulationLoop):
            raise ValueError("run_power_pull() only supports crank dyno mode -- drive chassis mode live via tick()")
        readings = self.loop.run_power_pull(dt=dt, ramp_rate_rpm_s=ramp_rate_rpm_s)
        self._power_pull_active = False
        return [self._snapshot(r, throttle_percent=100.0, power_pull_active=True) for r in readings]

    def _snapshot(
        self, reading: Union[DynoReading, ChassisDynoReading], throttle_percent: float, power_pull_active: bool
    ) -> DynoSnapshot:
        drivetrain_reading = reading.drivetrain if isinstance(reading, ChassisDynoReading) else None
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
            dyno_mode=self.dyno_mode,
            gear=drivetrain_reading.gear if drivetrain_reading else 0,
            shifting=drivetrain_reading.shifting if drivetrain_reading else False,
            wheel_rpm=drivetrain_reading.wheel_rpm if drivetrain_reading else 0.0,
            vehicle_speed_kmh=drivetrain_reading.vehicle_speed_kmh if drivetrain_reading else 0.0,
            slip_ratio=drivetrain_reading.slip_ratio if drivetrain_reading else 0.0,
            clutch_engagement=drivetrain_reading.clutch_engagement if drivetrain_reading else 1.0,
            clutch_locked=drivetrain_reading.clutch_locked if drivetrain_reading else False,
            # Crank mode has no separate wheel -- the dyno *is* measuring at
            # the crank there, so these just mirror torque_nm/power_kw
            # (see DynoSnapshot's own docstring on this pair).
            wheel_torque_nm=drivetrain_reading.wheel_torque_nm if drivetrain_reading else reading.engine.net_torque_nm,
            wheel_power_kw=drivetrain_reading.wheel_power_w / 1000.0 if drivetrain_reading else reading.power_kw,
        )
