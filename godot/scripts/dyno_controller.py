"""py4godot Node wrapping the pure-Python engine_sim simulation core.

This is the *only* place Godot and engine_sim touch. Everything upstream of
here (Engine/Turbo/ECU/DynoBrake) is plain, Godot-agnostic Python, importable
and testable with plain pytest -- see repo root `engine_sim/` and `tests/`.
If py4godot's embedding ever becomes a dead end, only this adapter needs
replacing, not the simulation itself.
"""

import sys
from pathlib import Path
from typing import Optional

from py4godot.classes import gdclass
from py4godot.classes.Node import Node
from py4godot.signals import signal


def _ensure_engine_sim_importable() -> None:
	# This script lives at <repo_root>/godot/scripts/dyno_controller.py.
	here = Path(__file__).resolve()
	repo_root = here.parents[2]
	if str(repo_root) not in sys.path:
		sys.path.insert(0, str(repo_root))


_ensure_engine_sim_importable()

from engine_sim import ECU, DynoBrake, ParametricEngine, SimulationLoop, Turbo  # noqa: E402
from engine_sim.presets import EA888_GEN3_IS20, TURBO_IS20  # noqa: E402


@gdclass
class dyno_controller(Node):
	"""Every attribute below is exactly what a real ECU could report on its
	data bus -- this drives the dyno's live readout, not a display-only mock.
	Inputs (set from the UI): afr_override, boost_target_percent, power_pull_active.
	Outputs (read by the UI every frame): everything else.
	"""

	# --- inputs, driven by the UI scene ---
	afr_override: float = -1.0  # -1 = let the ECU's own control law decide
	boost_target_percent: float = 100.0  # wastegate authority, 0-100% of max boost
	power_pull_active: bool = False
	ramp_rate_rpm_s: float = 400.0

	# --- live readout, updated every physics tick ---
	rpm: float = 0.0
	torque_nm: float = 0.0
	power_kw: float = 0.0
	boost_bar: float = 0.0
	afr_actual: float = 0.0
	air_mass_flow_g_s: float = 0.0
	fuel_mass_flow_g_s: float = 0.0
	effective_compression_ratio: float = 0.0
	volumetric_efficiency: float = 0.0
	rev_limiter_active: bool = False

	power_pull_finished = signal([])

	def __init__(self):
		super().__init__()
		self._loop: Optional[SimulationLoop] = None

	def _ready(self) -> None:
		engine = ParametricEngine(EA888_GEN3_IS20)
		turbo = Turbo(TURBO_IS20)
		ecu = ECU(EA888_GEN3_IS20, TURBO_IS20)
		brake = DynoBrake()
		self._loop = SimulationLoop(engine, turbo, ecu, brake)
		self.rpm = self._loop.rpm

	def _physics_process(self, delta: float) -> None:
		if self._loop is None:
			return

		ecu = self._loop.ecu
		ecu.set_target_afr(self.afr_override if self.afr_override >= 0.0 else None)
		ecu.set_boost_target_fraction(max(0.0, min(1.0, self.boost_target_percent / 100.0)))

		if self.power_pull_active:
			reading = self._loop.tick(
				delta,
				throttle=1.0,
				mode="ramp_rpm",
				ramp_rate_rpm_s=self.ramp_rate_rpm_s,
			)
			if self._loop.rpm >= ecu.rev_limiter_threshold_rpm:
				self.power_pull_active = False
				self.power_pull_finished.emit()
		else:
			# Idle: no throttle input in this UI, engine sits off between pulls.
			reading = self._loop.tick(delta, throttle=0.0, mode="free_accel")

		self.rpm = reading.rpm
		self.torque_nm = reading.engine.net_torque_nm
		self.power_kw = reading.power_kw
		self.boost_bar = reading.boost_bar
		self.afr_actual = reading.engine.afr_actual
		self.air_mass_flow_g_s = reading.engine.air_mass_flow_kg_s * 1000.0
		self.fuel_mass_flow_g_s = reading.engine.fuel_mass_flow_kg_s * 1000.0
		self.effective_compression_ratio = reading.engine.effective_compression_ratio
		self.volumetric_efficiency = reading.engine.ve
		self.rev_limiter_active = ecu.rev_limiter_active(reading.rpm)

	def start_power_pull(self) -> None:
		if self._loop is None:
			return
		self._loop.rpm = self._loop.engine.spec.idle_rpm
		self._loop.turbo.reset()
		self.power_pull_active = True

	def stop_power_pull(self) -> None:
		self.power_pull_active = False
