"""Simulation core: Engine, Turbo, ECU, DynoBrake/SimulationLoop.

All Godot-agnostic, all driven by the data-only specs in `engine_sim.specs`.
"""

from engine_sim.core.engine import Engine, ParametricEngine, EngineReading
from engine_sim.core.turbo import Turbo, TurboState, TurboReading
from engine_sim.core.ecu import ECU, EcuReading
from engine_sim.core.dyno import DynoBrake, SimulationLoop, DynoReading, DynoMode

__all__ = [
    "Engine",
    "ParametricEngine",
    "EngineReading",
    "Turbo",
    "TurboState",
    "TurboReading",
    "ECU",
    "EcuReading",
    "DynoBrake",
    "SimulationLoop",
    "DynoReading",
    "DynoMode",
]
