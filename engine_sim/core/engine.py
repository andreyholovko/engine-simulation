"""Engine models.

`Engine` is an abstract base so new engine types (different combustion
cycles, fuels, forced-induction schemes) can be added without touching the
ECU, Turbo or DynoBrake code -- they all talk to whatever `Engine` they're
given through this interface only.

`ParametricEngine` is the concrete spark-ignition (Otto/Miller cycle) mean
value engine model (MVEM): given throttle, RPM and manifold pressure it
computes air mass flow, fuel flow and net crank torque from first-principles
engine parameters (displacement, cylinders, compression ratio, cam profile),
the same technique used in real hardware-in-the-loop ECU test rigs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import exp

from engine_sim.specs import EngineSpec
from engine_sim.units import R_AIR, LHV_GASOLINE


@dataclass
class EngineReading:
    """One tick's worth of engine sensor/diagnostic data -- exactly what a
    real ECU would have available and what the dyno display reads out."""

    rpm: float
    map_pa: float
    ve: float
    air_mass_flow_kg_s: float
    fuel_mass_flow_kg_s: float
    afr_actual: float
    effective_compression_ratio: float
    indicated_torque_nm: float
    friction_torque_nm: float
    net_torque_nm: float


class Engine(ABC):
    """Abstract engine. Concrete engines compute net crank torque for a tick
    given current RPM, intake manifold pressure (already reflects throttle --
    the ECU derives it from throttle position + boost before calling this)
    and an ECU-commanded target AFR / effective-compression hint. Rev-limiting
    is the ECU's job (it zeroes target_afr, which zeroes torque here through
    the ordinary physics) -- an engine never needs its own separate cutoff."""

    spec: EngineSpec

    @abstractmethod
    def compute(
        self,
        rpm: float,
        map_pa: float,
        target_afr: float,
        load_fraction: float,
        intake_temp_k: float,
    ) -> EngineReading:
        """Compute torque and diagnostics for the current tick. Does not
        integrate rotational dynamics -- that's the simulation loop's job."""
        raise NotImplementedError


class ParametricEngine(Engine):
    """Mean-value spark-ignition engine model, parametric in displacement,
    cylinder count, compression ratio and camshaft profile."""

    def __init__(self, spec: EngineSpec):
        self.spec = spec

    def volumetric_efficiency(self, rpm: float) -> float:
        spec = self.spec
        floor = spec.ve_peak * spec.ve_floor_fraction

        # Rising phase, only for engines that opted in (ve_rise_rpm >
        # idle_rpm -- the default 0 never satisfies this, so every existing
        # preset falls straight through to the original flat-plateau
        # behavior, unchanged).
        if spec.ve_rise_rpm > spec.idle_rpm and rpm <= spec.ve_rise_rpm:
            span = max(spec.ve_rise_rpm - spec.idle_rpm, 1.0)
            x = max(0.0, (rpm - spec.idle_rpm) / span)
            return floor + (spec.ve_peak - floor) * x

        falloff_rpm = spec.ve_falloff_rpm()
        if rpm <= falloff_rpm:
            return spec.ve_peak
        # Gaussian-ish taper above the falloff point as flow/breathing limits
        # bite; floor set by ve_floor_fraction so it never goes to zero.
        span = max(spec.redline_rpm - falloff_rpm, 1.0)
        x = (rpm - falloff_rpm) / span
        return floor + (spec.ve_peak - floor) * exp(-2.2 * x * x)

    def effective_compression_ratio(self, load_fraction: float) -> float:
        spec = self.spec
        if not spec.miller_cycle:
            return spec.compression_ratio
        # ECU shifts intake valve closing timing in real time: early closure
        # (Miller, low effective ratio) at low load for efficiency, later
        # closure (near geometric ratio) under load for power.
        low = spec.miller_compression_ratio
        high = spec.compression_ratio
        load_fraction = max(0.0, min(1.0, load_fraction))
        return low + (high - low) * load_fraction

    def _thermal_efficiency(self, compression_ratio: float) -> float:
        gamma = 1.3  # real-gas ratio of specific heats, not ideal air-standard 1.4
        eta_otto_ideal = 1.0 - compression_ratio ** (-(gamma - 1.0))
        return eta_otto_ideal * self.spec.realism_factor

    def _friction_torque(self, rpm: float) -> float:
        spec = self.spec
        fmep_pa = (
            spec.friction_a_pa
            + spec.friction_b_pa_per_rpm * rpm
            + spec.friction_c_pa_per_rpm2 * rpm * rpm
        )
        # FMEP -> torque for a 4-stroke engine: T = fmep * Vd / (4*pi)
        return fmep_pa * spec.displacement_m3 / (4.0 * 3.141592653589793)

    def compute(
        self,
        rpm: float,
        map_pa: float,
        target_afr: float,
        load_fraction: float,
        intake_temp_k: float,
    ) -> EngineReading:
        spec = self.spec
        rpm = max(rpm, 1.0)
        ve = self.volumetric_efficiency(rpm)

        # Air mass flow: one intake stroke per cylinder every 2 crank
        # revolutions (4-stroke) -> cycles/sec = rpm / 120.
        air_mass_flow = ve * map_pa * spec.displacement_m3 * (rpm / 120.0) / (
            R_AIR * intake_temp_k
        )

        fuel_mass_flow = air_mass_flow / target_afr if target_afr > 0 else 0.0
        afr_actual = target_afr

        eff_cr = self.effective_compression_ratio(load_fraction)
        eta_thermal = self._thermal_efficiency(eff_cr)

        fuel_power_w = fuel_mass_flow * LHV_GASOLINE * spec.combustion_efficiency
        indicated_power_w = fuel_power_w * eta_thermal
        omega = rpm * 2.0 * 3.141592653589793 / 60.0
        indicated_torque = indicated_power_w / omega if omega > 0 else 0.0

        friction_torque = self._friction_torque(rpm)
        net_torque = max(0.0, indicated_torque - friction_torque)

        return EngineReading(
            rpm=rpm,
            map_pa=map_pa,
            ve=ve,
            air_mass_flow_kg_s=air_mass_flow,
            fuel_mass_flow_kg_s=fuel_mass_flow,
            afr_actual=afr_actual,
            effective_compression_ratio=eff_cr,
            indicated_torque_nm=indicated_torque,
            friction_torque_nm=friction_torque,
            net_torque_nm=net_torque,
        )
