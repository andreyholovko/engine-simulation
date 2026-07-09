"""Simulation core: Engine, Turbo, ECU, DynoBrake/SimulationLoop.

All Godot-agnostic, all driven by the data-only specs in `engine_sim.specs`.
"""

from engine_sim.core.engine import Engine, ParametricEngine, EngineReading
from engine_sim.core.turbo import Turbo, TurboState, TurboReading
from engine_sim.core.ecu import ECU, EcuReading
from engine_sim.core.tire import Tire, TireReading
from engine_sim.core.clutch import Clutch, couple_two_inertias
from engine_sim.core.drivetrain import Drivetrain, DrivetrainReading
from engine_sim.core.torque_converter import TorqueConverter, TorqueConverterReading
from engine_sim.core.automatic_drivetrain import AutomaticDrivetrain
from engine_sim.core.dyno import (
    DynoBrake,
    SimulationLoop,
    DynoReading,
    DynoMode,
    ChassisDynoLoop,
    ChassisDynoReading,
)

__all__ = [
    "Engine",
    "ParametricEngine",
    "EngineReading",
    "Turbo",
    "TurboState",
    "TurboReading",
    "ECU",
    "EcuReading",
    "Tire",
    "TireReading",
    "Clutch",
    "couple_two_inertias",
    "Drivetrain",
    "DrivetrainReading",
    "TorqueConverter",
    "TorqueConverterReading",
    "AutomaticDrivetrain",
    "DynoBrake",
    "SimulationLoop",
    "DynoReading",
    "DynoMode",
    "ChassisDynoLoop",
    "ChassisDynoReading",
]
