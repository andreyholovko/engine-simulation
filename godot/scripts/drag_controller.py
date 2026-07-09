"""py4godot Node driving a quarter-mile drag race on top of DynoSession's
chassis dyno mode -- same "thin adapter, all the math lives in engine_sim"
role as dyno_controller.py, just wired for a timed race instead of free-play
dyno tuning: forces chassis mode + the automatic transmission (no gearbox
picker here -- see DynoSession.select_transmission()), runs a fixed 3-second
countdown before the car will accept throttle at all, and tracks the
race-specific state (distance down the strip, elapsed time, trap speed,
0-100/0-200 splits) that DynoSession itself has no reason to know about.
"""

import sys
from pathlib import Path
from typing import Optional

from py4godot.classes import gdclass
from py4godot.classes.Node import Node
from py4godot.signals import signal


def _ensure_engine_sim_importable() -> None:
	# This script lives at <repo_root>/godot/scripts/drag_controller.py.
	here = Path(__file__).resolve()
	repo_root = here.parents[2]
	if str(repo_root) not in sys.path:
		sys.path.insert(0, str(repo_root))


_ensure_engine_sim_importable()

from engine_sim import DynoSession  # noqa: E402

QUARTER_MILE_M = 402.336
COUNTDOWN_S = 3.0

# race_state values -- plain int across the py4godot boundary (same
# reasoning as every enum-shaped property in dyno_controller.py: no
# confirmed-safe way to pass a str/enum there).
STATE_COUNTDOWN = 0
STATE_RACING = 1
STATE_FINISHED = 2

# Sentinel for "not reached yet" on the 0-100/0-200 splits -- -1 rather than
# 0.0 because 0.0 is a real (if implausible) elapsed time, and this needs to
# be unambiguously distinguishable from "already timed at the green light."
SPLIT_NOT_REACHED = -1.0


@gdclass
class drag_controller(Node):
	"""Inputs: throttle_percent (0-100, driven by the UI's throttle slider --
	ignored by the sim itself before the light goes green or after the
	finish line, see _physics_process()), select_engine_by_index()/
	select_turbo_by_index() (same index-addressed convention as
	dyno_controller.py). Outputs: everything else, updated every physics
	tick; race_state/countdown_s/race_time_s/distance_m/trap_speed_kmh/
	finish_time_s/time_to_100_kmh_s/time_to_200_kmh_s are this scene's own
	bookkeeping on top of the same DrivetrainReading fields
	dyno_controller.py already exposes.
	"""

	# --- input ---
	throttle_percent: float = 0.0

	# --- live drivetrain readout (same fields/units as dyno_controller.py) ---
	rpm: float = 0.0
	gear: int = 1
	wheel_rpm: float = 0.0
	vehicle_speed_kmh: float = 0.0
	slip_ratio: float = 0.0
	wheel_torque_nm: float = 0.0
	# The real tire radius (metres) behind wheel_rpm above -- drag_race.gd
	# needs this to spin the wheel sprites at a rate that visually matches
	# how fast the road is scrolling (see its WHEEL_VISUAL_SCALE comment):
	# the sprite's own drawn radius is picked for legibility (26px), not
	# scaled 1:1 from PIXELS_PER_METER the way the real tire is, so the raw
	# angular velocity alone isn't enough -- it needs the real radius too.
	tire_radius_m: float = 0.316
	boost_bar: float = 0.0

	# --- engine/turbo facts, refreshed whenever either changes -- same
	# fields dyno_audio.gd already reads off dyno_controller.py, so
	# drag_audio.gd can drive identical synthesis from here. ---
	cylinders: int = 4
	displacement_l: float = 2.0
	max_boost_bar: float = 1.3
	firing_order_length: int = 4
	engine_generation: int = 0

	# --- race bookkeeping ---
	race_state: int = STATE_COUNTDOWN
	countdown_s: float = COUNTDOWN_S  # counts down to 0 during the light sequence
	race_time_s: float = 0.0  # counts up from the green light, freezes at the line
	distance_m: float = 0.0  # 0 at the start line, keeps advancing past the finish (coasting)
	trap_speed_kmh: float = 0.0  # vehicle_speed_kmh at the exact instant the line was crossed
	finish_time_s: float = 0.0  # race_time_s at that same instant
	time_to_100_kmh_s: float = SPLIT_NOT_REACHED
	time_to_200_kmh_s: float = SPLIT_NOT_REACHED

	race_started = signal([])
	race_finished = signal([])

	def __init__(self):
		super().__init__()
		self._session: Optional[DynoSession] = None
		self._elapsed_since_ready_s = 0.0
		self._engine_key = "ea888_gen3_is20"
		self._turbo_index = 0  # index into TURBO_CHOICES_BY_ENGINE[_engine_key]; 0 = stock

	def _ready(self) -> None:
		self._session = DynoSession()
		self._session.select_dyno_mode("chassis")
		self._session.select_transmission("auto_6speed")
		self._refresh_engine_facts()
		self._arm_countdown()

	def _refresh_engine_facts(self) -> None:
		self.tire_radius_m = self._session.drivetrain.tire.spec.radius_m
		engine_spec = self._session.ecu.engine.spec
		self.cylinders = engine_spec.cylinders
		self.displacement_l = engine_spec.displacement_l
		self.firing_order_length = len(engine_spec.firing_order_resolved)
		self.max_boost_bar = self._session.ecu.turbo.spec.max_boost_bar
		self.engine_generation += 1

	def _arm_countdown(self) -> None:
		"""Resets every piece of race-run state and re-arms the 3-second
		light sequence, WITHOUT touching the engine/turbo choice -- the
		shared tail end of both restart_race() (explicit Restart button)
		and select_engine_by_index()/select_turbo_by_index() (an engine/
		turbo swap always voids whatever run was in progress, same as
		DynoSession.select_engine()/select_turbo() already abort an
		in-progress dyno pull)."""
		self._elapsed_since_ready_s = 0.0
		self.countdown_s = COUNTDOWN_S
		self.race_time_s = 0.0
		self.distance_m = 0.0
		self.trap_speed_kmh = 0.0
		self.finish_time_s = 0.0
		self.time_to_100_kmh_s = SPLIT_NOT_REACHED
		self.time_to_200_kmh_s = SPLIT_NOT_REACHED
		self.race_state = STATE_COUNTDOWN

	def restart_race(self) -> None:
		"""Rebuilds the session from scratch and re-arms the countdown --
		callable from a Restart button once a run has finished. A full fresh
		DynoSession (not just _arm_countdown()) so a stuck/unusual
		drivetrain state from the previous run can never carry over. Restores
		BOTH the current engine and turbo choice -- select_engine() alone
		would silently revert to that engine's stock turbo, quietly
		discarding a turbo swap the driver made before hitting Restart."""
		self._session = DynoSession()
		self._session.select_dyno_mode("chassis")
		self._session.select_transmission("auto_6speed")
		self._session.select_engine(self._engine_key)
		if self._turbo_index != 0:
			self._session.select_turbo_by_index(self._turbo_index)
		self._refresh_engine_facts()
		self._arm_countdown()

	def select_engine_by_index(self, index: int) -> None:
		"""Same index-addressed convention as dyno_controller.py's own
		method of this name (str properties aren't safe across the
		py4godot boundary -- see that file). Swapping engines always voids
		an in-progress run (DynoSession.select_engine() already resets the
		drivetrain to a fresh gear-1/stationary state internally), so this
		re-arms the countdown too rather than leaving the race mid-run
		against a car that just silently changed engines under it. Always
		resets to that engine's own stock turbo (DynoSession.select_engine()
		does this internally too) -- a turbo choice from the previous engine
		isn't necessarily valid, or even meaningful, on a different one."""
		if self._session is None:
			return
		from engine_sim.presets import ENGINE_CHOICES

		keys = list(ENGINE_CHOICES.keys())
		if not 0 <= index < len(keys):
			return
		self._engine_key = keys[index]
		self._turbo_index = 0
		self._session.select_engine(self._engine_key)
		self._refresh_engine_facts()
		self._arm_countdown()

	def select_turbo_by_index(self, index: int) -> None:
		"""Same reasoning as select_engine_by_index() -- turbo choices are
		per-engine (see TURBO_CHOICES_BY_ENGINE), addressed against
		whichever engine is currently selected."""
		if self._session is None:
			return
		self._turbo_index = index
		self._session.select_turbo_by_index(index)
		self._refresh_engine_facts()
		self._arm_countdown()

	def get_firing_order_cylinder(self, index: int) -> int:
		"""Same role as dyno_controller.py's own method of this name: index
		into the current engine's firing order, returning a cylinder number
		rather than the tuple itself -- an arbitrary-length Python sequence
		isn't safe across the py4godot boundary, plain int in/out is."""
		if self._session is None:
			return index + 1
		firing_order = self._session.ecu.engine.spec.firing_order_resolved
		return firing_order[index]

	def _refresh_readout(self, snapshot) -> None:
		self.rpm = snapshot.rpm
		self.gear = snapshot.gear
		self.wheel_rpm = snapshot.wheel_rpm
		self.vehicle_speed_kmh = snapshot.vehicle_speed_kmh
		self.slip_ratio = snapshot.slip_ratio
		self.wheel_torque_nm = snapshot.wheel_torque_nm
		self.boost_bar = snapshot.boost_bar

	def _physics_process(self, delta: float) -> None:
		if self._session is None:
			return

		# Throttle authority is the only thing gated by race_state -- closed
		# before green (no jumping the light) and cut again past the finish
		# (a real racer lifts after the line too).
		if self.race_state == STATE_RACING:
			throttle = self.throttle_percent
		else:
			throttle = 0.0

		snapshot = self._session.tick(delta, throttle_percent=throttle)

		if self.race_state == STATE_COUNTDOWN:
			# A torque-converter automatic creeps forward on idle alone --
			# real behavior (see AutomaticDrivetrain), not something to
			# suppress in general (chassis-dyno mode leaves it alone
			# entirely). But a real drag launch starts with the driver
			# standing on the brake against that same creep, holding the
			# car dead still until the light goes green -- without
			# modeling a brake, the closest equivalent is clamping the
			# wheel/roller speed right back to zero every tick, right after
			# integrating it, the same "held at a dead stop" state a brake
			# would actually produce. Engine/turbo/rpm are left alone --
			# idle sounds and reads normally waiting for green; the
			# reported snapshot below still carries that one tick's worth
			# of (sub-millimeter, imperceptible) creep before the reset
			# below erases it for next tick's integration -- not worth
			# re-ticking just to scrub it from the display too.
			self._session.drivetrain.omega_wheel = 0.0
			self._session.drivetrain.omega_roller = 0.0

		self._refresh_readout(snapshot)
		speed_mps = snapshot.vehicle_speed_kmh / 3.6
		self.distance_m += speed_mps * delta

		if self.race_state == STATE_COUNTDOWN:
			self._elapsed_since_ready_s += delta
			self.countdown_s = max(0.0, COUNTDOWN_S - self._elapsed_since_ready_s)
			if self._elapsed_since_ready_s >= COUNTDOWN_S:
				self.race_state = STATE_RACING
				self.race_started.emit()
		elif self.race_state == STATE_RACING:
			self.race_time_s += delta
			if self.time_to_100_kmh_s == SPLIT_NOT_REACHED and snapshot.vehicle_speed_kmh >= 100.0:
				self.time_to_100_kmh_s = self.race_time_s
			if self.time_to_200_kmh_s == SPLIT_NOT_REACHED and snapshot.vehicle_speed_kmh >= 200.0:
				self.time_to_200_kmh_s = self.race_time_s
			if self.distance_m >= QUARTER_MILE_M:
				self.trap_speed_kmh = snapshot.vehicle_speed_kmh
				self.finish_time_s = self.race_time_s
				self.race_state = STATE_FINISHED
				self.race_finished.emit()
