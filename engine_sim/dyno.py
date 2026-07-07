"""Engine dyno: load model + the tick loop tying Engine/Turbo/ECU together.

This is a crank/engine dyno -- it loads the engine directly (no transmission,
no wheels, no tire-road friction; that only exists in the drag-strip mode
built later). Three load modes:

  * "ramp_rpm": the brake controls torque so RPM climbs at a fixed rate
    (rpm/s) -- this is how a real dyno "power pull" is actually run (a large
    roller/eddy-current brake paces the sweep, typically ~300-500 rpm/s so
    it takes ~15-20s idle-to-redline). It matters here because the turbo's
    "full boost by N rpm" spec implicitly assumes this pacing -- spool is a
    function of *time* as much as RPM, so sweeping unrealistically fast
    would never let it catch up.
  * "free_accel": the brake applies only its own small parasitic drag and
    lets the engine free-rev at WOT, the way an inertia dyno (Dynojet-style)
    works -- power is derived from how fast a known inertia accelerates.
    Realistic for an unloaded engine, but sweeps far faster than a paced
    power pull.
  * "hold_rpm": a PID controls brake torque to pin RPM at a target, the way
    an eddy-current/water-brake dyno steps through discrete plateaus, and
    what interactive free-play throttle control needs underneath it.
"""

from dataclasses import dataclass
from math import pi
from typing import Literal, Optional

from .ecu import ECU
from .engine import Engine, EngineReading
from .turbo import Turbo
from .units import rpm_to_rad_s, rad_s_to_rpm, power_watts

DynoMode = Literal["ramp_rpm", "free_accel", "hold_rpm"]


@dataclass
class DynoReading:
    time_s: float
    rpm: float
    throttle: float
    engine: EngineReading
    boost_bar: float
    load_fraction: float
    brake_torque_nm: float
    power_w: float

    @property
    def power_kw(self) -> float:
        return self.power_w / 1000.0

    @property
    def power_hp(self) -> float:
        return self.power_w / 745.7


class DynoBrake:
    def __init__(
        self,
        dyno_inertia_kgm2: float = 0.05,
        parasitic_torque_nm: float = 3.0,
        pid_kp: float = 2.5,
        pid_ki: float = 1.2,
        pid_kd: float = 0.05,
    ):
        self.dyno_inertia_kgm2 = dyno_inertia_kgm2
        self.parasitic_torque_nm = parasitic_torque_nm
        self.pid_kp = pid_kp
        self.pid_ki = pid_ki
        self.pid_kd = pid_kd
        self._integral = 0.0
        self._prev_error = 0.0

    def reset_pid(self) -> None:
        self._integral = 0.0
        self._prev_error = 0.0

    def load_torque(
        self,
        mode: DynoMode,
        rpm: float,
        dt: float,
        target_rpm: Optional[float] = None,
        engine_torque_nm: Optional[float] = None,
        total_inertia_kgm2: Optional[float] = None,
        ramp_rate_rpm_s: Optional[float] = None,
    ) -> float:
        if mode == "ramp_rpm":
            assert engine_torque_nm is not None and total_inertia_kgm2 is not None
            assert ramp_rate_rpm_s is not None
            alpha_target = ramp_rate_rpm_s * (2.0 * pi / 60.0)
            required = engine_torque_nm - total_inertia_kgm2 * alpha_target
            # A passive brake can only absorb torque, never drive the engine
            # -- if there isn't enough torque to hold the pace, the sweep
            # simply falls behind schedule rather than going negative.
            return max(0.0, required)
        if mode == "free_accel" or target_rpm is None:
            return self.parasitic_torque_nm
        error = rpm - target_rpm
        self._integral += error * dt
        derivative = (error - self._prev_error) / dt if dt > 0 else 0.0
        self._prev_error = error
        control = self.pid_kp * error + self.pid_ki * self._integral + self.pid_kd * derivative
        # A passive brake can only absorb torque, never drive the engine.
        return max(0.0, self.parasitic_torque_nm + control)


class SimulationLoop:
    """Owns live state (rpm, turbo boost) and advances it one tick at a time."""

    def __init__(self, engine: Engine, turbo: Turbo, ecu: ECU, brake: DynoBrake):
        self.engine = engine
        self.turbo = turbo
        self.ecu = ecu
        self.brake = brake
        self.rpm = engine.spec.idle_rpm
        self.time_s = 0.0

    @property
    def _total_inertia(self) -> float:
        return self.engine.spec.crank_inertia_kgm2 + self.brake.dyno_inertia_kgm2

    def tick(
        self,
        dt: float,
        throttle: float,
        mode: DynoMode = "free_accel",
        target_rpm: Optional[float] = None,
        ramp_rate_rpm_s: Optional[float] = None,
        intake_temp_k: float = 313.0,
    ) -> DynoReading:
        throttle = max(0.0, min(1.0, throttle))

        ecu_reading = self.ecu.tick(self.rpm, throttle, self.turbo.state.boost_pa)
        boost_pa = self.turbo.tick(dt, self.rpm, throttle, ecu_reading.wastegate_duty)
        # Re-derive MAP with the freshly-ticked boost so it's not one tick stale.
        map_pa = self.ecu.intake_manifold_pressure(throttle, boost_pa)
        load_fraction = self.ecu.load_fraction(map_pa, boost_pa)

        engine_reading = self.engine.compute(
            throttle=throttle,
            rpm=self.rpm,
            map_pa=map_pa,
            target_afr=ecu_reading.target_afr,
            load_fraction=load_fraction,
            intake_temp_k=intake_temp_k,
        )

        brake_torque = self.brake.load_torque(
            mode,
            self.rpm,
            dt,
            target_rpm=target_rpm,
            engine_torque_nm=engine_reading.net_torque_nm,
            total_inertia_kgm2=self._total_inertia,
            ramp_rate_rpm_s=ramp_rate_rpm_s,
        )
        net_torque = engine_reading.net_torque_nm - brake_torque

        omega = rpm_to_rad_s(self.rpm)
        omega += (net_torque / self._total_inertia) * dt
        omega = max(0.0, omega)
        self.rpm = rad_s_to_rpm(omega)
        self.time_s += dt

        power_w = power_watts(engine_reading.net_torque_nm, rpm_to_rad_s(self.rpm))

        return DynoReading(
            time_s=self.time_s,
            rpm=self.rpm,
            throttle=throttle,
            engine=engine_reading,
            boost_bar=self.turbo.boost_bar,
            load_fraction=load_fraction,
            brake_torque_nm=brake_torque,
            power_w=power_w,
        )

    def run_power_pull(
        self,
        dt: float = 0.01,
        start_rpm: Optional[float] = None,
        mode: DynoMode = "ramp_rpm",
        ramp_rate_rpm_s: float = 400.0,
    ) -> list[DynoReading]:
        """WOT sweep from idle to redline, paced like a real dyno power pull
        (default ~400rpm/s, ~15s idle-to-redline); returns the full curve."""
        self.rpm = start_rpm if start_rpm is not None else self.engine.spec.idle_rpm
        self.time_s = 0.0
        self.brake.reset_pid()
        self.turbo.reset()
        readings: list[DynoReading] = []
        max_ticks = int(60.0 / dt)  # 60s safety cap
        for _ in range(max_ticks):
            reading = self.tick(dt, throttle=1.0, mode=mode, ramp_rate_rpm_s=ramp_rate_rpm_s)
            readings.append(reading)
            if self.rpm >= self.ecu.rev_limiter_threshold_rpm:
                break
        return readings
