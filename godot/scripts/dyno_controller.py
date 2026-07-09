"""py4godot Node wrapping DynoSession -- the single interface every dyno
frontend (this Godot UI and the CLI) drives. All the simulation math lives
in engine_sim (pure Python, Godot-agnostic, tested with plain pytest); this
file's only job is moving numbers between DynoSession and Godot's exported
node properties. If py4godot's embedding ever becomes a dead end, only this
adapter needs replacing, not the simulation itself.
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
	Inputs (set from the UI): afr_override, boost_target_percent,
	octane_override, throttle_percent, and the start_power_pull()/
	stop_power_pull()/select_engine_by_index()/select_turbo_by_index()
	methods. Outputs (read by the UI every frame): everything else,
	including power_pull_active, which mirrors the session's own state --
	it is not itself a control input.
	"""

	# --- inputs, driven by the UI scene ---
	afr_override: float = -1.0  # -1 = let the ECU's own control law decide
	boost_target_percent: float = 100.0  # wastegate authority, 0-100% of max boost
	octane_override: float = -1.0  # -1 = use the engine's own knock_octane_requirement
	# Live throttle, 0-100 -- driven by the UI's vertical throttle slider,
	# read every physics tick. Replaces the old fixed-pace ramp_rate_rpm_s:
	# the user's own slider position paces the sweep now, the way a real
	# inertia dyno is driven by the operator's right foot.
	throttle_percent: float = 0.0

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
	intake_air_temp_c: float = 0.0
	rev_limiter_active: bool = False
	power_pull_active: bool = False

	# --- engine picker: ENGINE_CHOICES, addressed by index (int) rather than
	# key (str) -- py4godot's own examples only ever show int/float/bool/
	# Vector3 properties, never str, so selection goes through
	# select_engine_by_index() to stay on confirmed-safe types.
	engine_count: int = 0
	engine_name: str = ""  # last-resort/debug only, nothing load-bearing depends on this str
	engine_choices: str = ""  # ditto

	# --- turbo picker: TURBO_CHOICES_BY_ENGINE for the CURRENT engine, same
	# index-addressed reasoning as the engine picker above. The list itself
	# changes whenever the engine does (a different engine has different
	# turbo options), which is why turbo_choices/turbo_count are refreshed
	# from _refresh_engine_facts() too, not just on their own.
	turbo_count: int = 0
	turbo_name: str = ""  # last-resort/debug only, same as engine_name
	turbo_choices: str = ""  # ditto

	# --- engine/turbo facts, refreshed whenever the engine changes -- for
	# audio synthesis (dyno_audio.gd). Kept as plain int/float, same reasoning
	# as engine_count above.
	cylinders: int = 4
	displacement_l: float = 2.0
	max_boost_bar: float = 1.3
	firing_order_length: int = 4
	# Bumped every time the engine changes -- the cheap int-only way for
	# dyno_audio.gd to know its cached per-cylinder signature is stale,
	# without needing a str/object identity check across the boundary.
	engine_generation: int = 0

	power_pull_finished = signal([])

	def __init__(self):
		super().__init__()
		self._session: Optional[DynoSession] = None

	def _ready(self) -> None:
		self._session = DynoSession()
		self.rpm = self._session.loop.rpm
		self.engine_count = len(DynoSession.list_engine_choices())
		self.engine_choices = "|".join(
			f"{key}:{name}" for key, name in DynoSession.list_engine_choices()
		)
		self._refresh_engine_facts()

	def _refresh_engine_facts(self) -> None:
		spec = self._session.ecu.engine.spec
		self.engine_name = spec.name
		self.cylinders = spec.cylinders
		self.displacement_l = spec.displacement_l
		self.firing_order_length = len(spec.firing_order_resolved)
		self.engine_generation += 1
		self._refresh_turbo_choices()
		self._refresh_turbo_facts()

	def _refresh_turbo_choices(self) -> None:
		choices = self._session.list_turbo_choices()
		self.turbo_count = len(choices)
		self.turbo_choices = "|".join(f"{key}:{name}" for key, name in choices)

	def _refresh_turbo_facts(self) -> None:
		# Deliberately separate from _refresh_turbo_choices(): switching
		# turbos changes these but not the choice list itself (still the
		# same engine), while switching engines changes both.
		self.max_boost_bar = self._session.ecu.turbo.spec.max_boost_bar
		self.turbo_name = self._session.ecu.turbo.spec.name

	def get_firing_order_cylinder(self, index: int) -> int:
		"""index into the current engine's firing order (0-based), e.g. for
		EA888 (1,3,4,2): index 0 -> 1, index 1 -> 3, etc. Returns cylinder
		numbers (int) rather than the tuple itself -- an arbitrary-length
		Python sequence is exactly the kind of thing not to trust across the
		py4godot boundary; plain int in, plain int out is safe."""
		if self._session is None:
			return index + 1
		firing_order = self._session.ecu.engine.spec.firing_order_resolved
		return firing_order[index]

	def select_engine_by_index(self, index: int) -> None:
		if self._session is None:
			return
		self._session.select_engine_by_index(index)
		self._refresh_engine_facts()

	def select_engine(self, key: str) -> None:
		if self._session is None:
			return
		self._session.select_engine(key)
		self._refresh_engine_facts()

	def select_turbo_by_index(self, index: int) -> None:
		if self._session is None:
			return
		self._session.select_turbo_by_index(index)
		self._refresh_turbo_facts()

	def select_turbo(self, key: str) -> None:
		if self._session is None:
			return
		self._session.select_turbo(key)
		self._refresh_turbo_facts()

	def _physics_process(self, delta: float) -> None:
		if self._session is None:
			return

		self._session.set_afr_override(self.afr_override if self.afr_override >= 0.0 else None)
		self._session.set_boost_target_percent(self.boost_target_percent)
		self._session.set_octane_override(self.octane_override if self.octane_override >= 0.0 else None)

		was_active = self._session.is_power_pull_active
		snapshot = self._session.tick(delta, throttle_percent=self.throttle_percent)

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
		self.intake_air_temp_c = snapshot.intake_air_temp_k - 273.15
		self.rev_limiter_active = snapshot.rev_limiter_active

	def start_power_pull(self) -> None:
		if self._session is None:
			return
		self._session.start_power_pull()

	def stop_power_pull(self) -> None:
		if self._session is not None:
			self._session.stop_power_pull()
