"""py4godot Node wrapping DynoSession -- the single interface every dyno
frontend (this Godot UI, the CLI, and any future consumer, e.g. a 3D
drag-strip view) drives. All the simulation math lives in engine_sim (pure
Python, Godot-agnostic, tested with plain pytest); this file's only job is
moving numbers between DynoSession and Godot's exported node properties. If
py4godot's embedding ever becomes a dead end, only this adapter needs
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

from engine_sim import DynoSession  # noqa: E402


@gdclass
class dyno_controller(Node):
	"""Every attribute below is exactly what a real ECU could report on its
	data bus -- this drives the dyno's live readout, not a display-only mock.
	Inputs (set from the UI): afr_override, boost_target_percent, and the
	start_power_pull()/stop_power_pull() methods. Outputs (read by the UI
	every frame): everything else, including power_pull_active, which mirrors
	the session's own state -- it is not itself a control input.
	"""

	# --- inputs, driven by the UI scene ---
	afr_override: float = -1.0  # -1 = let the ECU's own control law decide
	boost_target_percent: float = 100.0  # wastegate authority, 0-100% of max boost
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
	power_pull_active: bool = False
	throttle_percent: float = 0.0  # what the sim actually used this tick (output, not an input)
	spool_fraction: float = 0.0  # turbo boost as a fraction of max, 0-1 -- for turbo whine/BOV audio

	# --- static engine facts, set once in _ready() -- for audio synthesis ---
	cylinders: int = 4

	power_pull_finished = signal([])

	def __init__(self):
		super().__init__()
		self._session: Optional[DynoSession] = None

	def _ready(self) -> None:
		self._session = DynoSession()
		self.rpm = self._session.loop.rpm
		self.cylinders = self._session.ecu.engine.spec.cylinders

	def _physics_process(self, delta: float) -> None:
		if self._session is None:
			return

		self._session.set_afr_override(self.afr_override if self.afr_override >= 0.0 else None)
		self._session.set_boost_target_percent(self.boost_target_percent)

		was_active = self._session.is_power_pull_active
		snapshot = self._session.tick(delta, throttle_percent=0.0)

		self.power_pull_active = snapshot.power_pull_active
		if was_active and not snapshot.power_pull_active:
			self.power_pull_finished.emit()

		self.rpm = snapshot.rpm
		self.torque_nm = snapshot.torque_nm
		self.power_kw = snapshot.power_kw
		self.boost_bar = snapshot.boost_bar
		self.afr_actual = snapshot.afr_actual
		self.air_mass_flow_g_s = snapshot.air_mass_flow_g_s
		self.fuel_mass_flow_g_s = snapshot.fuel_mass_flow_g_s
		self.effective_compression_ratio = snapshot.effective_compression_ratio
		self.volumetric_efficiency = snapshot.volumetric_efficiency
		self.rev_limiter_active = snapshot.rev_limiter_active
		self.throttle_percent = snapshot.throttle_percent
		self.spool_fraction = snapshot.spool_fraction

	def start_power_pull(self) -> None:
		if self._session is None:
			return
		self._session.start_power_pull(self.ramp_rate_rpm_s)

	def stop_power_pull(self) -> None:
		if self._session is not None:
			self._session.stop_power_pull()
