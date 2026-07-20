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
from engine_sim.core.automatic_drivetrain import AutomaticDrivetrain  # noqa: E402
from engine_sim.presets import CAR_CHOICES  # noqa: E402

# CarSpec.drivetrain_layout ("fwd"/"rwd"/"awd") -> the int dyno_controller
# actually exposes (drivetrain_layout_index) -- see that property's own
# comment for why.
_DRIVETRAIN_LAYOUT_INDEX = {"fwd": 0, "rwd": 1, "awd": 2}


@gdclass
class dyno_controller(Node):
	"""Every attribute below is exactly what a real ECU could report on its
	data bus -- this drives the dyno's live readout, not a display-only mock.
	Inputs (set from the UI): afr_override, boost_target_percent,
	octane_override, throttle_percent, and the start_power_pull()/
	stop_power_pull()/select_car_by_index()/select_turbo_by_index()/
	select_dyno_mode_chassis()/select_tire_by_index()/shift_up()/shift_down()
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

	# --- chassis dyno: mode + drivetrain readout (see engine_sim.DynoSession
	# .select_dyno_mode()/DrivetrainReading) -- all zero/false/locked-neutral
	# while in crank mode, same "meaningful defaults" convention
	# DynoSnapshot's own dataclass fields use. ---
	dyno_mode_is_chassis: bool = False
	gear: int = 0  # 0 = neutral
	shifting: bool = False
	wheel_rpm: float = 0.0
	vehicle_speed_kmh: float = 0.0
	slip_ratio: float = 0.0
	clutch_engagement: float = 1.0
	clutch_locked: bool = False
	# Torque/power actually delivered to the roller -- what the graph should
	# plot (see DynoSnapshot's own docstring: clutch/tire slip show up here
	# as a real shortfall vs. torque_nm/power_kw, which are always the pure
	# engine-crank numbers regardless of mode). Equal to torque_nm/power_kw
	# in crank mode.
	wheel_torque_nm: float = 0.0
	wheel_power_kw: float = 0.0

	# --- tire picker: TIRE_CHOICES, addressed by index (int) for the same
	# str-across-py4godot-boundary reasoning as the car/turbo pickers. ---
	tire_count: int = 0
	tire_name: str = ""  # last-resort/debug only, same as car_name
	tire_choices: str = ""  # ditto

	# --- transmission picker: TRANSMISSION_CHOICES (manual vs automatic),
	# same index-addressed reasoning as the tire picker above. ---
	transmission_count: int = 0
	transmission_name: str = ""  # last-resort/debug only, same as car_name
	transmission_choices: str = ""  # ditto
	is_automatic_transmission: bool = False  # true once an AutomaticDrivetrain is live -- UI disables shift buttons

	# --- car picker: CAR_CHOICES, addressed by index (int) rather than key
	# (str) -- py4godot's own examples only ever show int/float/bool/
	# Vector3 properties, never str, so selection goes through
	# select_car_by_index() to stay on confirmed-safe types. Picking a car
	# picks its engine (and stock turbo) at once -- see CarSpec/CAR_CHOICES.
	car_count: int = 0
	car_name: str = ""  # last-resort/debug only, nothing load-bearing depends on this str
	car_choices: str = ""  # ditto

	# --- turbo picker: TURBO_CHOICES_BY_CAR for the CURRENT car, same
	# index-addressed reasoning as the car picker above. The list itself
	# changes whenever the car does (a different car has different turbo
	# options), which is why turbo_choices/turbo_count are refreshed from
	# _refresh_engine_facts() too, not just on their own.
	turbo_count: int = 0
	turbo_name: str = ""  # last-resort/debug only, same as car_name
	turbo_choices: str = ""  # ditto

	# --- engine/turbo facts, refreshed whenever the car changes -- for
	# audio synthesis (dyno_audio.gd). Kept as plain int/float, same reasoning
	# as car_count above.
	cylinders: int = 4
	displacement_l: float = 2.0
	max_boost_bar: float = 1.3
	firing_order_length: int = 4
	# Bumped every time the car (and so its engine) changes -- the cheap
	# int-only way for dyno_audio.gd to know its cached per-cylinder
	# signature is stale, without needing a str/object identity check
	# across the boundary.
	engine_generation: int = 0
	# CarSpec.drivetrain_layout, encoded as a plain int rather than the
	# "fwd"/"rwd"/"awd" string it actually is -- same str-across-py4godot-
	# boundary reasoning as every other picker here. 0=FWD, 1=RWD, 2=AWD
	# (see _DRIVETRAIN_LAYOUT_INDEX below); the UI maps this back to a label
	# via its own hardcoded array, same convention as car_option/
	# turbo_option's labels.
	drivetrain_layout_index: int = 0

	power_pull_finished = signal([])

	def __init__(self):
		super().__init__()
		self._session: Optional[DynoSession] = None

	def _ready(self) -> None:
		self._session = DynoSession()
		self.rpm = self._session.loop.rpm
		self.car_count = len(DynoSession.list_car_choices())
		self.car_choices = "|".join(
			f"{key}:{name}" for key, name in DynoSession.list_car_choices()
		)
		self.tire_count = len(DynoSession.list_tire_choices())
		self.tire_choices = "|".join(
			f"{key}:{name}" for key, name in DynoSession.list_tire_choices()
		)
		self.tire_name = DynoSession.list_tire_choices()[0][1]
		self.transmission_count = len(DynoSession.list_transmission_choices())
		self.transmission_choices = "|".join(
			f"{key}:{name}" for key, name in DynoSession.list_transmission_choices()
		)
		self.transmission_name = DynoSession.list_transmission_choices()[0][1]
		self._refresh_engine_facts()

	def _refresh_engine_facts(self) -> None:
		car_name = next(name for key, name in DynoSession.list_car_choices() if key == self._session.car_key)
		self.car_name = car_name
		spec = self._session.ecu.engine.spec
		self.cylinders = spec.cylinders
		self.displacement_l = spec.displacement_l
		self.firing_order_length = len(spec.firing_order_resolved)
		self.engine_generation += 1
		self.drivetrain_layout_index = _DRIVETRAIN_LAYOUT_INDEX[CAR_CHOICES[self._session.car_key].drivetrain_layout]
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

	def select_car_by_index(self, index: int) -> None:
		if self._session is None:
			return
		self._session.select_car_by_index(index)
		self._refresh_engine_facts()

	def select_car(self, key: str) -> None:
		if self._session is None:
			return
		self._session.select_car(key)
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

	def select_dyno_mode_chassis(self, is_chassis: bool) -> None:
		"""Crank/chassis toggle -- bool rather than the "crank"/"chassis"
		string DynoSession.select_dyno_mode() actually takes, same
		str-across-py4godot-boundary reasoning as every other picker here."""
		if self._session is None:
			return
		self._session.select_dyno_mode("chassis" if is_chassis else "crank")
		self.dyno_mode_is_chassis = is_chassis
		self.is_automatic_transmission = isinstance(self._session.drivetrain, AutomaticDrivetrain)

	def select_tire_by_index(self, index: int) -> None:
		if self._session is None:
			return
		self._session.select_tire_by_index(index)
		self.tire_name = DynoSession.list_tire_choices()[index][1]

	def select_transmission_by_index(self, index: int) -> None:
		if self._session is None:
			return
		self._session.select_transmission_by_index(index)
		self.transmission_name = DynoSession.list_transmission_choices()[index][1]
		self.is_automatic_transmission = isinstance(self._session.drivetrain, AutomaticDrivetrain)

	def shift_up(self) -> None:
		if self._session is not None:
			self._session.shift_up()

	def shift_down(self) -> None:
		if self._session is not None:
			self._session.shift_down()

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

		self.gear = snapshot.gear
		self.shifting = snapshot.shifting
		self.wheel_rpm = snapshot.wheel_rpm
		self.vehicle_speed_kmh = snapshot.vehicle_speed_kmh
		self.slip_ratio = snapshot.slip_ratio
		self.clutch_engagement = snapshot.clutch_engagement
		self.clutch_locked = snapshot.clutch_locked
		self.wheel_torque_nm = snapshot.wheel_torque_nm
		self.wheel_power_kw = snapshot.wheel_power_kw

	def start_power_pull(self) -> None:
		if self._session is None:
			return
		self._session.start_power_pull()

	def stop_power_pull(self) -> None:
		if self._session is not None:
			self._session.stop_power_pull()
