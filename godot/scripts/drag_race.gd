extends Node2D
## Quarter-mile drag race: wires DragController's live sim state to the
## scrolling parallax world, the car's wheels/smoke, and the countdown/
## results UI. All physics -- including the automatic transmission's own
## shift logic and the 3-second countdown gate on throttle -- lives in
## DragController (Python/engine_sim); this script only moves numbers into
## visuals, the same "thin coordinator" role dyno_ui.gd plays for the dyno
## scene.
##
## The car sprite never actually moves: it sits fixed at
## DragSceneLayout.CAR_SCREEN_X and the world scrolls under it instead (see
## _process() / _scroll_layer()), driven by the sim's own distance_m,
## converted to pixels by the same PIXELS_PER_METER every layer and the
## finish line agree on (see drag_scene_layout.gd). That's what makes the
## finish-line gantry visibly approach and then pass the car at exactly the
## moment DragController's own quarter-mile check fires.
##
## Background layers are plain Node2D nodes, each repositioned by hand every
## frame (_scroll_layer()) rather than Godot's built-in ParallaxBackground/
## ParallaxLayer. Found directly: with those nodes, `ParallaxBackground.
## scroll_offset` visibly updated correctly every frame (confirmed straight
## off the property) but the rendered layers never actually moved -- Godot's
## own parallax scroll turned out to be computed from the current Camera2D's
## position, not `scroll_offset` alone, and this scene's whole design (a
## screen-fixed car, a world that scrolls under it with no camera movement
## at all) doesn't fit that model. Wrapping each layer's own `position.x`
## with `fmod(distance, tile_width)` sidesteps the built-in node entirely --
## each bg_*.gd script draws enough repeated copies of its tile
## (REPEAT_FROM..REPEAT_TO) to cover the viewport at any wrap phase, the way
## ParallaxLayer.motion_mirroring used to.
##
## Acceleration "feel" (_update_acceleration_feel()) is driven by the sim's
## own real longitudinal acceleration -- d(speed)/dt, computed here from
## consecutive vehicle_speed_kmh readings -- not a scripted/fake effect: a
## hard launch under real wheelspin produces a real, large accel spike
## (torque-converter multiplication dumping onto barely-gripping tires),
## which is exactly when the shake/squat should read as strongest.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const QUARTER_MILE_M := 402.336
const SMOKE_SLIP_THRESHOLD := 0.18  # beyond the tire's peak-grip slip ratio -- see engine_sim.core.tire

# Hardcoded, matching engine_sim/presets/__init__.py's CAR_CHOICES/
# TURBO_CHOICES_BY_CAR order exactly -- same str-across-py4godot-boundary
# reasoning as dyno_ui.gd's own copy of these same lists (see that file for
# the full explanation). Keep in sync if either preset list changes.
const CAR_LABELS := [
	"VW/Audi Mk7 GTI (EA888 Gen3, IS20)",
	"BMW F30 340i xDrive (B58B30)",
	"Chevrolet C6 Corvette (LS2, NA)",
]
const TURBO_LABELS_BY_CAR := [
	["Stock IHI IS20", "IHI IS38 (hybrid swap)", "Aftermarket big-frame hybrid (TTE-class)"],
	["Stock MHI single twin-scroll (340i)", "BMW B58TU (M340i/Supra factory upgrade)", "Aftermarket big single (Pure Stage 2-class)"],
	["Naturally aspirated (stock)", "Twin-turbo kit (representative, stock-internals-safe)"],
]

# Hardcoded, matching engine_sim/presets/tires.py's TIRE_CHOICES order
# exactly -- same str-across-py4godot-boundary reasoning as CAR_LABELS.
# Independent of which car is selected (same three tires available on
# every car), unlike TURBO_LABELS_BY_CAR.
const TIRE_LABELS := [
	"225/45R17 Street All-Season",
	"245/40R18 Sport Summer",
	"315/40R18 Drag Radial",
]

# controller.drivetrain_layout_index (0/1/2) -> label -- must match
# drag_controller.py's own _DRIVETRAIN_LAYOUT_INDEX mapping (0=FWD, 1=RWD,
# 2=AWD), same reasoning as CAR_LABELS above.
const DRIVETRAIN_LABELS := ["FWD", "RWD", "AWD"]
const SLIP_NORMAL_COLOR := Color(1, 1, 1, 1)
const SLIP_SPINNING_COLOR := Color(1, 0.3, 0.2, 1)

# Acceleration -> screen-shake/squat tuning. Divisors are "accel (m/s^2) that
# maxes out the effect" -- picked against what a real launch actually
# produces here (verified directly: a WOT launch peaks around 8-10 m/s^2 in
# 1st gear before tapering), not arbitrary.
const SHAKE_ACCEL_FOR_MAX_MPS2 := 9.0
const SHAKE_MAX_PX := 5.0
const SHAKE_DEADZONE_PX := 0.05  # below this, snap to (0,0) instead of a constant sub-pixel jitter
const TILT_ACCEL_FOR_MAX_MPS2 := 10.0
const TILT_MAX_RAD := 0.045  # ~2.6 degrees -- a squat/dive cue, not a cartoon wheelie
const TILT_SMOOTHING_PER_S := 6.0

@onready var controller = $DragController
@onready var car: Node2D = $Car
@onready var mountains_shape: Node2D = $MountainsShape
@onready var city_shape: Node2D = $CityShape
@onready var road_shape: Node2D = $RoadShape
@onready var guardrail_shape: Node2D = $GuardrailShape
@onready var finish_line: Node2D = $FinishLine
@onready var wheel_front: Node2D = $Car/WheelFront
@onready var wheel_rear: Node2D = $Car/WheelRear
@onready var smoke_front: CPUParticles2D = $Car/WheelFront/SmokeParticles
@onready var smoke_rear: CPUParticles2D = $Car/WheelRear/SmokeParticles

@onready var countdown_label: Label = $UI/CountdownLabel
@onready var throttle_slider: VSlider = $UI/ThrottleRow/ThrottleSlider
@onready var throttle_label: Label = $UI/ThrottleRow/ThrottleLabel
@onready var rpm_value: Label = $UI/StatsPanel/RpmValue
@onready var gear_value: Label = $UI/StatsPanel/GearValue
@onready var speed_value: Label = $UI/StatsPanel/SpeedValue
@onready var distance_value: Label = $UI/StatsPanel/DistanceValue
@onready var time_value: Label = $UI/StatsPanel/TimeValue
@onready var split_100_value: Label = $UI/StatsPanel/Split100Value
@onready var split_200_value: Label = $UI/StatsPanel/Split200Value
@onready var slip_value: Label = $UI/StatsPanel/SlipValue
@onready var drivetrain_value: Label = $UI/StatsPanel/DrivetrainValue
@onready var results_panel: Control = $UI/ResultsPanel
@onready var result_time_label: Label = $UI/ResultsPanel/ResultTimeLabel
@onready var result_trap_label: Label = $UI/ResultsPanel/ResultTrapLabel
@onready var restart_button: Button = $UI/RestartButton
@onready var car_option: OptionButton = $UI/CarRow/CarOption
@onready var turbo_option: OptionButton = $UI/CarRow/TurboOption
@onready var tire_option: OptionButton = $UI/CarRow/TireOption

var _prev_speed_mps := 0.0


func _ready() -> void:
	controller.race_started.connect(_on_race_started)
	controller.race_finished.connect(_on_race_finished)
	results_panel.visible = false
	_populate_car_options()
	_populate_turbo_options(0)
	_populate_tire_options()


func _populate_car_options() -> void:
	for label in CAR_LABELS:
		car_option.add_item(label)
	if car_option.item_count > 0:
		car_option.select(0)


func _populate_turbo_options(car_index: int) -> void:
	turbo_option.clear()
	for label in TURBO_LABELS_BY_CAR[car_index]:
		turbo_option.add_item(label)
	if turbo_option.item_count > 0:
		turbo_option.select(0)


func _populate_tire_options() -> void:
	for label in TIRE_LABELS:
		tire_option.add_item(label)
	if tire_option.item_count > 0:
		tire_option.select(0)


func _process(delta: float) -> void:
	# `controller` (a py4godot-scripted Node) has no static type, so every
	# property read below is a Variant to GDScript's static analysis --
	# explicit typed locals sidestep the same ":=" inference failure that
	# broke the dyno UI script once already (see dyno_ui.gd's
	# _update_shift_buttons_enabled() for the full story).
	var distance_m: float = controller.distance_m
	var race_state: int = controller.race_state
	var race_time_s: float = controller.race_time_s

	# motion_scale per layer matches the old ParallaxLayer setup exactly
	# (sky excluded -- it never scrolled, motion_scale was 0): mountains
	# slowest (farthest), city faster, road at true 1:1 ground speed,
	# guardrail fastest (nearest -- the classic foreground speed cue).
	_scroll_layer(mountains_shape, distance_m, 0.15, mountains_shape.TILE_W)
	_scroll_layer(city_shape, distance_m, 0.4, city_shape.TILE_W)
	_scroll_layer(road_shape, distance_m, 1.0, road_shape.TILE_W)
	_scroll_layer(guardrail_shape, distance_m, 1.3, guardrail_shape.TILE_W)
	finish_line.position.x = Layout.CAR_SCREEN_X + (QUARTER_MILE_M - distance_m) * Layout.PIXELS_PER_METER

	# The sprite's drawn wheel radius (Layout.WHEEL_RADIUS_PX, picked so the
	# rim/spokes are actually legible) has nothing to do with the real tire
	# radius PIXELS_PER_METER is calibrated against, so the sim's raw
	# angular velocity can't drive the sprite's rotation directly -- applied
	# as-is, a visually-big wheel sweeps far more screen-space tread per
	# radian than the same-radius patch of road actually scrolls, which is
	# exactly why the wheel looked like it was spinning faster than the
	# ground moved. WHEEL_VISUAL_SCALE corrects for it: a wheel rolling
	# with zero slip ends up rotating at exactly the rate that makes its
	# rim's edge track the road's own scroll speed, and real wheelspin
	# (wheel_rpm running ahead of what the road speed alone implies) still
	# shows up as visibly faster rotation on top of that, same as a real
	# tire breaking loose.
	var tire_radius_m: float = controller.tire_radius_m
	var wheel_visual_scale := tire_radius_m * Layout.PIXELS_PER_METER / Layout.WHEEL_RADIUS_PX
	var vehicle_speed_kmh: float = controller.vehicle_speed_kmh
	var vehicle_speed_mps := vehicle_speed_kmh / 3.6

	# wheel_rpm is the DRIVEN axle's own (possibly slip-affected) speed --
	# the sim only models one tire, standing in for whichever axle the
	# current car's drivetrain_layout actually powers (see
	# DynoSession._build_loop()/ROLLER_BY_DRIVETRAIN_LAYOUT). The OTHER
	# axle gets no engine torque at all, so it can't slip -- it just rolls
	# with the car's real ground speed at zero slip, the ordinary
	# "vehicle_speed / tire_radius" relationship every free-rolling wheel
	# has. That's what makes a spinning driven axle visibly outrun the
	# free-rolling one instead of both wheels always matching.
	var wheel_rpm: float = controller.wheel_rpm
	var driven_delta_rad := wheel_rpm * TAU / 60.0 * wheel_visual_scale * delta
	var free_omega_rad_s := vehicle_speed_mps / tire_radius_m
	var free_delta_rad := free_omega_rad_s * wheel_visual_scale * delta

	# 0=FWD (front driven), 1=RWD (rear driven), 2=AWD (both driven -- no
	# free-rolling wheel at all) -- must match drag_controller.py's own
	# _DRIVETRAIN_LAYOUT_INDEX.
	var drivetrain_layout_index: int = controller.drivetrain_layout_index
	var front_driven: bool = drivetrain_layout_index == 0 or drivetrain_layout_index == 2
	var rear_driven: bool = drivetrain_layout_index == 1 or drivetrain_layout_index == 2
	wheel_front.rotation += driven_delta_rad if front_driven else free_delta_rad
	wheel_rear.rotation += driven_delta_rad if rear_driven else free_delta_rad

	var slip_ratio: float = controller.slip_ratio
	# abs() is generically typed in GDScript, so its return doesn't
	# statically resolve to float -- same ":=" inference failure documented
	# in dyno_ui.gd's _update_shift_buttons_enabled(). Explicit `: bool`
	# sidesteps it.
	var is_spinning: bool = abs(slip_ratio) > SMOKE_SLIP_THRESHOLD
	# Smoke only comes off the axle that's actually spinning: a FWD car's
	# rear wheels never see engine torque at all, so they never smoke no
	# matter how hard the fronts break loose, and vice versa for RWD; AWD
	# can smoke at both since both axles are genuinely driven.
	smoke_front.emitting = is_spinning and front_driven
	smoke_rear.emitting = is_spinning and rear_driven
	slip_value.text = "Slip: %+.3f%s" % [slip_ratio, " SPIN!" if is_spinning else ""]
	slip_value.add_theme_color_override("font_color", SLIP_SPINNING_COLOR if is_spinning else SLIP_NORMAL_COLOR)

	_update_acceleration_feel(vehicle_speed_kmh, delta)

	rpm_value.text = "%.0f rpm" % controller.rpm
	var gear: int = controller.gear
	gear_value.text = "Gear: %s" % ("N" if gear == 0 else str(gear))
	speed_value.text = "%.1f km/h" % vehicle_speed_kmh
	distance_value.text = "%.0f / %.0f m" % [distance_m, QUARTER_MILE_M]
	time_value.text = "%.2f s" % race_time_s
	split_100_value.text = _format_split("0-100 km/h", controller.time_to_100_kmh_s)
	split_200_value.text = _format_split("0-200 km/h", controller.time_to_200_kmh_s)
	drivetrain_value.text = "Drivetrain: %s" % DRIVETRAIN_LABELS[drivetrain_layout_index]

	if race_state == 0:
		var secs: float = controller.countdown_s
		countdown_label.text = str(int(ceil(secs))) if secs > 0.0 else "GO!"
	elif race_state == 1 and race_time_s < 1.0:
		countdown_label.text = "GO!"
	else:
		countdown_label.text = ""


func _format_split(label: String, split_s: float) -> String:
	return "%s: --" % label if split_s < 0.0 else "%s: %.2f s" % [label, split_s]


func _update_acceleration_feel(vehicle_speed_kmh: float, delta: float) -> void:
	"""Real longitudinal acceleration (d(speed)/dt off consecutive sim
	readings, not a scripted effect) drives two cheap "feel" cues: a small
	world shake (this node's own position -- shakes the car/road/background
	together, leaves the UI CanvasLayer rock-steady since CanvasLayers
	ignore their parent's Node2D transform) and a squat/dive tilt on the Car
	node (nose lifts under hard acceleration, dips under hard braking -- the
	standard weight-transfer cue, see this file's header for the sign-
	convention reasoning)."""
	if delta <= 0.0:
		return
	var speed_mps := vehicle_speed_kmh / 3.6
	var accel_mps2 := (speed_mps - _prev_speed_mps) / delta
	_prev_speed_mps = speed_mps

	# clamp() is generically typed in GDScript (works across int/float/
	# Vector*), so its return type doesn't statically resolve to float --
	# the same ":=" inference failure documented in dyno_ui.gd's
	# _update_shift_buttons_enabled(). Explicit `: float` sidesteps it.
	var shake_mag: float = clamp(abs(accel_mps2) / SHAKE_ACCEL_FOR_MAX_MPS2, 0.0, 1.0) * SHAKE_MAX_PX
	if shake_mag > SHAKE_DEADZONE_PX:
		position = Vector2(randf_range(-shake_mag, shake_mag), randf_range(-shake_mag, shake_mag))
	else:
		position = Vector2.ZERO

	var tilt_target: float = -clamp(accel_mps2 / TILT_ACCEL_FOR_MAX_MPS2, -1.0, 1.0) * TILT_MAX_RAD
	car.rotation = lerp(car.rotation, tilt_target, clamp(delta * TILT_SMOOTHING_PER_S, 0.0, 1.0))


func _scroll_layer(layer: Node2D, distance_m: float, motion_scale: float, tile_w: float) -> void:
	"""Wraps `layer`'s own position.x into [-tile_w, 0] -- always negative or
	zero so the layer's own repeated tile copies (drawn from index -1
	onward, see bg_mountains.gd etc.) stay lined up with x=0 instead of
	drifting positive and exposing the seam at the left edge of the
	viewport."""
	layer.position.x = -fmod(distance_m * Layout.PIXELS_PER_METER * motion_scale, tile_w)


func _on_throttle_changed(value: float) -> void:
	throttle_label.text = "Throttle: %d%%" % int(value)
	controller.throttle_percent = value


func _on_race_started() -> void:
	results_panel.visible = false


func _on_race_finished() -> void:
	result_time_label.text = "Time: %.2f s" % controller.finish_time_s
	result_trap_label.text = "Trap speed: %.1f km/h" % controller.trap_speed_kmh
	results_panel.visible = true


func _on_restart_pressed() -> void:
	controller.restart_race()
	_reset_ui_for_new_run()


func _on_car_selected(index: int) -> void:
	controller.select_car_by_index(index)
	# A different car has a different turbo lineup entirely (same
	# reasoning as dyno_ui.gd's _on_car_selected()) -- repopulate rather
	# than leave the previous car's options showing. select_car_by_
	# index() already re-arms the countdown on the controller side (see
	# drag_controller.py), so only the UI itself needs resetting here --
	# NOT another controller.restart_race() call, which would just rebuild
	# a second, redundant fresh session on top of the one already built.
	_populate_turbo_options(index)
	_reset_ui_for_new_run()


func _on_turbo_selected(index: int) -> void:
	controller.select_turbo_by_index(index)
	_reset_ui_for_new_run()


func _on_tire_selected(index: int) -> void:
	controller.select_tire_by_index(index)
	_reset_ui_for_new_run()


func _reset_ui_for_new_run() -> void:
	"""Shared by every path that (re)arms a fresh countdown -- the Restart
	button and a car/turbo swap -- so the results panel and throttle
	slider always land back in the same "ready for the light" state."""
	results_panel.visible = false
	throttle_slider.value = 0.0
	_on_throttle_changed(0.0)
