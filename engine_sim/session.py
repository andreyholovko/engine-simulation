"""DynoSession: the one interface every frontend talks to.

The CLI, the Godot UI, and any future consumer (a 3D drag-strip view, say)
render and drive things differently -- but they should never each construct
their own Engine/Turbo/ECU/SimulationLoop by hand, and never each hand-roll
their own flattening of a DynoReading into display fields. Do that once,
here, so every consumer is provably looking at the same simulation instead of
three copies that happen to agree today and can silently drift tomorrow.

`DynoSession()` with no arguments is *the* canonical dyno: EA888 Gen3 (IS20),
the preset validated against VW's own published figures. Pass a different
engine_spec/turbo_spec only for a deliberately different configuration (e.g.
a future engine-swap/garage screen) -- everyone who just wants "the dyno"
should call `DynoSession()` and get identical behavior.
"""

from dataclasses import dataclass
from typing import Optional

from engine_sim.core import DynoBrake, DynoReading, ECU, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import EA888_GEN3_IS20, ENGINE_CHOICES, TURBO_IS20
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
        turbo = Turbo(turbo_spec)
        ecu = ECU(engine, turbo)
        self.loop = SimulationLoop(ecu, brake if brake is not None else DynoBrake())
        self._power_pull_active = False
        self._ramp_rate_rpm_s = 400.0
        self.idle_rpm_target = engine_spec.idle_rpm
        self.engine_key = engine_key

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
        """Swap to a different engine+turbo from ENGINE_CHOICES, mid-session.
        Rebuilds Engine/Turbo/ECU (a different engine means different specs
        driving them) but keeps the same DynoBrake -- the dyno's own inertia/
        drag isn't a property of whichever engine happens to be mounted."""
        if key not in ENGINE_CHOICES:
            raise ValueError(f"unknown engine choice: {key!r}. Available: {sorted(ENGINE_CHOICES)}")
        engine_spec, turbo_spec, _ = ENGINE_CHOICES[key]
        engine = ParametricEngine(engine_spec)
        turbo = Turbo(turbo_spec)
        ecu = ECU(engine, turbo)
        self.loop = SimulationLoop(ecu, self.loop.brake)
        self.loop.brake.reset_pid()
        self._power_pull_active = False
        self.idle_rpm_target = engine_spec.idle_rpm
        self.engine_key = key

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

    # --- control surface: the only knobs any consumer should touch ---

    def set_afr_override(self, afr: Optional[float]) -> None:
        """None restores the ECU's own load-based control law."""
        self.loop.ecu.set_target_afr(afr)

    def set_boost_target_percent(self, percent: Optional[float]) -> None:
        """0-100, as a percentage of the turbo's max boost. None restores
        full wastegate authority."""
        fraction = None if percent is None else max(0.0, min(1.0, percent / 100.0))
        self.loop.ecu.set_boost_target_fraction(fraction)

    def start_power_pull(self, ramp_rate_rpm_s: float = 400.0) -> None:
        self.loop.rpm = self.loop.ecu.engine.spec.idle_rpm
        self.loop.time_s = 0.0
        self.loop.brake.reset_pid()
        self.loop.ecu.turbo.reset()
        self._ramp_rate_rpm_s = ramp_rate_rpm_s
        self._power_pull_active = True

    def stop_power_pull(self) -> None:
        self._power_pull_active = False

    def tick(self, dt: float, throttle_percent: float = 0.0) -> DynoSnapshot:
        """Advance one tick. While a power pull is active, WOT + the ramp
        mode governs regardless of throttle_percent -- a real dyno operator
        doesn't get to back off mid-pull. At zero throttle, the dyno brake
        holds `idle_rpm_target` (the way idle is also held against real
        accessory load, not just the ECU's own idle air) instead of free-
        revving or stalling. Above zero throttle, free-play (light parasitic
        load only, RPM responds like a free-revving engine on a stand)."""
        if self._power_pull_active:
            reading = self.loop.tick(
                dt, throttle=1.0, mode="ramp_rpm", ramp_rate_rpm_s=self._ramp_rate_rpm_s
            )
            if self.loop.rpm >= self.loop.ecu.rev_limiter_threshold_rpm:
                self._power_pull_active = False
            return self._snapshot(reading, throttle_percent=100.0, power_pull_active=self._power_pull_active)

        if throttle_percent <= 1e-6:
            reading = self.loop.tick(dt, throttle=0.0, mode="hold_rpm", target_rpm=self.idle_rpm_target)
        else:
            reading = self.loop.tick(dt, throttle=throttle_percent / 100.0, mode="free_accel")
        return self._snapshot(reading, throttle_percent=throttle_percent, power_pull_active=False)

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
            rev_limiter_active=self.loop.ecu.rev_limiter_active(reading.rpm),
            power_pull_active=power_pull_active,
        )
