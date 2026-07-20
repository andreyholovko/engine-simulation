extends Control
## Wires the UI controls to the Python-backed dyno_controller node and
## refreshes the live readout every frame. All simulation math lives in
## engine_sim (pure Python) via DynoController -- this script only moves
## numbers between widgets and that node.

@onready var controller = $DynoController
@onready var car_option: OptionButton = $Layout/SetupSection/CarRow/CarOption
@onready var turbo_option: OptionButton = $Layout/SetupSection/TurboRow/TurboOption
@onready var boost_slider: HSlider = $Layout/TuningSection/BoostRow/BoostSlider
@onready var boost_target_label: Label = $Layout/TuningSection/BoostRow/BoostTargetLabel
@onready var afr_checkbox: CheckBox = $Layout/TuningSection/AfrRow/AfrCheckBox
@onready var afr_slider: HSlider = $Layout/TuningSection/AfrRow/AfrSlider
@onready var afr_value_label: Label = $Layout/TuningSection/AfrRow/AfrValueLabel
@onready var power_pull_button: Button = $Layout/RunSection/PowerPullRow/PowerPullButton
@onready var finish_pull_button: Button = $Layout/RunSection/PowerPullRow/FinishPullButton
@onready var clear_graph_button: Button = $Layout/RunSection/PowerPullRow/ClearGraphButton
@onready var throttle_slider: VSlider = $Layout/RunSection/ThrottleRow/ThrottleSlider
@onready var throttle_label: Label = $Layout/RunSection/ThrottleRow/ThrottleLabel
@onready var mode_checkbox: CheckBox = $Layout/SetupSection/ModeRow/ModeCheckBox
@onready var tire_option: OptionButton = $Layout/SetupSection/ModeRow/TireOption
@onready var transmission_option: OptionButton = $Layout/SetupSection/GearRow/TransmissionOption
@onready var gear_value: Label = $Layout/SetupSection/GearRow/GearValue
@onready var shift_down_button: Button = $Layout/SetupSection/GearRow/ShiftDownButton
@onready var shift_up_button: Button = $Layout/SetupSection/GearRow/ShiftUpButton
@onready var rpm_value: Label = $Layout/ReadoutsSection/Readouts/RpmValue
@onready var torque_value: Label = $Layout/ReadoutsSection/Readouts/TorqueValue
@onready var power_value: Label = $Layout/ReadoutsSection/Readouts/PowerValue
@onready var boost_value: Label = $Layout/ReadoutsSection/Readouts/BoostValue
@onready var afr_value: Label = $Layout/ReadoutsSection/Readouts/AfrValue
@onready var ve_value: Label = $Layout/ReadoutsSection/Readouts/VeValue
@onready var air_value: Label = $Layout/ReadoutsSection/Readouts/AirValue
@onready var fuel_value: Label = $Layout/ReadoutsSection/Readouts/FuelValue
@onready var cr_value: Label = $Layout/ReadoutsSection/Readouts/CrValue
@onready var iat_value: Label = $Layout/ReadoutsSection/Readouts/IatValue
@onready var rev_limiter_value: Label = $Layout/ReadoutsSection/Readouts/RevLimiterValue
@onready var wheel_rpm_value: Label = $Layout/ReadoutsSection/Readouts/WheelRpmValue
@onready var vehicle_speed_value: Label = $Layout/ReadoutsSection/Readouts/VehicleSpeedValue
@onready var slip_value: Label = $Layout/ReadoutsSection/Readouts/SlipValue
@onready var clutch_value: Label = $Layout/ReadoutsSection/Readouts/ClutchValue
@onready var drivetrain_value: Label = $Layout/ReadoutsSection/Readouts/DrivetrainValue
@onready var graph = $Layout/DynoGraph

# Beyond the tire's own peak-grip slip ratio (see engine_sim.core.tire) --
# same threshold the drag scene's smoke effect uses (drag_race.gd's
# SMOKE_SLIP_THRESHOLD) -- past this the tire is genuinely spinning, not
# just working normally under load.
const WHEELSPIN_SLIP_THRESHOLD := 0.18
const SLIP_NORMAL_COLOR := Color(1, 1, 1, 1)
const SLIP_SPINNING_COLOR := Color(1, 0.3, 0.2, 1)

# Hardcoded, matching engine_sim/presets/tires.py's TIRE_CHOICES order
# exactly -- same str-across-py4godot-boundary reasoning as CAR_LABELS.
const TIRE_LABELS := [
	"225/45R17 Street All-Season",
	"245/40R18 Sport Summer",
	"315/40R18 Drag Radial",
]

# Hardcoded, matching engine_sim/presets/transmissions.py's
# TRANSMISSION_CHOICES order exactly -- same str-across-py4godot-boundary
# reasoning as TIRE_LABELS.
const TRANSMISSION_LABELS := [
	"6-Speed Manual",
	"6-Speed Automatic (Aisin-class)",
]


# Hardcoded, matching engine_sim/presets/__init__.py's CAR_CHOICES order
# exactly -- deliberately NOT read from controller.car_choices (a `str`
# property), because py4godot's own examples only ever show int/float/bool/
# Vector3 properties, never str, and that was confirmed to be the actual
# cause of the picker not working at all: an empty/broken string meant an
# empty dropdown. Selection is driven by plain index (int), a type already
# confirmed working (cylinders, rpm, etc. all display correctly). Keep this
# list in sync with CAR_CHOICES if you add a fourth car.
const CAR_LABELS := [
	"VW/Audi Mk7 GTI (EA888 Gen3, IS20)",
	"BMW F30 340i xDrive (B58B30)",
	"Chevrolet C6 Corvette (LS2, NA)",
]

# controller.drivetrain_layout_index (0/1/2) -> label -- same "int, not str"
# reasoning as CAR_LABELS above; must match dyno_controller.py's own
# _DRIVETRAIN_LAYOUT_INDEX mapping (0=FWD, 1=RWD, 2=AWD).
const DRIVETRAIN_LABELS := ["FWD", "RWD", "AWD"]

# Hardcoded per car, matching engine_sim/presets/__init__.py's
# TURBO_CHOICES_BY_CAR order exactly (index 0 is always that car's own
# stock/validated turbo) -- same "not read from a `str` property" reasoning
# as CAR_LABELS above. Outer index lines up with CAR_LABELS' order. Keep in
# sync with TURBO_CHOICES_BY_CAR if you add/reorder a turbo.
const TURBO_LABELS_BY_CAR := [
	["Stock IHI IS20", "IHI IS38 (hybrid swap)", "Aftermarket big-frame hybrid (TTE-class)"],
	["Stock MHI single twin-scroll (340i)", "BMW B58TU (M340i/Supra factory upgrade)", "Aftermarket big single (Pure Stage 2-class)"],
	["Naturally aspirated (stock)", "Twin-turbo kit (representative, stock-internals-safe)"],
]


func _ready() -> void:
	controller.power_pull_finished.connect(_on_power_pull_finished)
	_populate_car_options()
	_populate_turbo_options(0)
	_populate_tire_options()
	_populate_transmission_options()
	_update_gear_label()
	_update_shift_buttons_enabled()
	finish_pull_button.disabled = true


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


func _populate_transmission_options() -> void:
	for label in TRANSMISSION_LABELS:
		transmission_option.add_item(label)
	if transmission_option.item_count > 0:
		transmission_option.select(0)


func _update_gear_label() -> void:
	var label := "N" if controller.gear == 0 else str(controller.gear)
	if controller.shifting:
		label += " (shifting)"
	gear_value.text = label


func _update_shift_buttons_enabled() -> void:
	# The automatic shifts itself off throttle position -- no clutch pedal,
	# no shift buttons, same as a real automatic (see DynoSession.shift_up()
	# /shift_down()'s own no-op-on-automatic behavior).
	# `controller` has no static type (@onready var controller = $DynoController,
	# a py4godot-scripted node) -- reading a bool property off it is a
	# Variant to GDScript's static analysis, so `:=` type inference on an
	# expression built from it fails to compile ("Cannot infer the type").
	# Explicit `: bool` sidesteps that; this is exactly the bug that broke
	# this whole script (and so every handler in it, including the car/
	# turbo pickers) until it was fixed.
	var is_automatic: bool = controller.is_automatic_transmission
	shift_up_button.disabled = is_automatic
	shift_down_button.disabled = is_automatic


func _process(_delta: float) -> void:
	rpm_value.text = "%.0f" % controller.rpm
	# wheel_torque_nm/wheel_power_kw are what a real dyno actually measures
	# (roller-derived, not read off the engine crank) -- in crank mode
	# they're set equal to torque_nm/power_kw (there's no separate wheel to
	# speak of there), and in chassis mode clutch/tire slip show up here as
	# a real shortfall, exactly like a real chassis dyno graph would show.
	torque_value.text = "%.1f" % controller.wheel_torque_nm
	power_value.text = "%.1f" % controller.wheel_power_kw
	boost_value.text = "%.2f" % controller.boost_bar
	afr_value.text = "%.2f" % controller.afr_actual
	ve_value.text = "%.2f" % controller.volumetric_efficiency
	air_value.text = "%.2f" % controller.air_mass_flow_g_s
	fuel_value.text = "%.2f" % controller.fuel_mass_flow_g_s
	cr_value.text = "%.2f" % controller.effective_compression_ratio
	iat_value.text = "%.0f" % controller.intake_air_temp_c
	rev_limiter_value.text = "CUT" if controller.rev_limiter_active else "off"

	wheel_rpm_value.text = "%.0f" % controller.wheel_rpm
	vehicle_speed_value.text = "%.1f" % controller.vehicle_speed_kmh
	var slip_ratio: float = controller.slip_ratio
	# abs() is generically typed in GDScript (int/float/Vector*), so its
	# return doesn't statically resolve to float/bool -- same ":=" inference
	# failure documented in dyno_ui.gd's own _update_shift_buttons_enabled().
	# Explicit `: bool` sidesteps it.
	var is_spinning: bool = abs(slip_ratio) > WHEELSPIN_SLIP_THRESHOLD
	slip_value.text = "%+.3f%s" % [slip_ratio, " SPIN!" if is_spinning else ""]
	slip_value.add_theme_color_override("font_color", SLIP_SPINNING_COLOR if is_spinning else SLIP_NORMAL_COLOR)
	clutch_value.text = "%.0f%% %s" % [controller.clutch_engagement * 100.0, "locked" if controller.clutch_locked else "SLIP"]
	var drivetrain_layout_index: int = controller.drivetrain_layout_index
	drivetrain_value.text = DRIVETRAIN_LABELS[drivetrain_layout_index]
	_update_gear_label()

	if controller.power_pull_active:
		graph.add_point(controller.rpm, controller.wheel_torque_nm, controller.wheel_power_kw)


func _on_car_selected(index: int) -> void:
	controller.select_car_by_index(index)
	# A different car has a different turbo lineup entirely (DynoSession.
	# select_car() already resets to that car's own stock turbo) --
	# repopulate rather than leave the previous car's options showing.
	_populate_turbo_options(index)
	# Switching cars always aborts any in-progress pull (DynoSession.
	# select_car() resets it internally) -- but that happens synchronously
	# here, before the next _physics_process runs, so the usual True->False
	# transition _physics_process watches for to fire power_pull_finished
	# never happens (is_power_pull_active is already False by the time it
	# next checks). Reset the button/graph directly instead of relying on
	# that signal for this specific case.
	_reset_pull_ui()


func _on_turbo_selected(index: int) -> void:
	controller.select_turbo_by_index(index)
	# Same reasoning as _on_car_selected() above -- select_turbo() aborts
	# an in-progress pull too, and the graph/button need resetting the same
	# way (the car's engine, and so the turbo lineup, doesn't change here).
	_reset_pull_ui()


func _on_boost_target_changed(value: float) -> void:
	boost_target_label.text = "Target Boost: %d%%" % int(value)
	controller.boost_target_percent = value


func _on_afr_override_toggled(enabled: bool) -> void:
	afr_slider.editable = enabled
	controller.afr_override = afr_slider.value if enabled else -1.0


func _on_afr_slider_changed(value: float) -> void:
	afr_value_label.text = "%.1f" % value
	if afr_checkbox.button_pressed:
		controller.afr_override = value


func _on_throttle_changed(value: float) -> void:
	# Live, while running -- this is what actually paces a pull now (see
	# DynoSession.start_power_pull()'s docstring): the user's own slider
	# position each frame, not a fixed rpm/s the sim used to enforce.
	throttle_label.text = "Throttle: %d%%" % int(value)
	controller.throttle_percent = value


func _on_power_pull_pressed() -> void:
	graph.clear_history()
	power_pull_button.disabled = true
	power_pull_button.text = "Power pull running..."
	finish_pull_button.disabled = false
	throttle_slider.value = 0.0
	controller.start_power_pull()


func _on_power_pull_finished() -> void:
	# Fires from the controller's own signal when the pull ends itself (rev
	# limiter reached) -- a manual Finish press (see
	# _on_finish_power_pull_pressed()) calls the session directly instead,
	# so it goes through the same reset rather than this handler.
	_reset_pull_ui()


func _on_finish_power_pull_pressed() -> void:
	# Ends the pull early, on demand, instead of only ever auto-ending at the
	# rev limiter -- e.g. a partial-throttle pull that isn't climbing toward
	# redline at all. Calling stop_power_pull() directly (rather than
	# waiting for the controller's signal) means is_power_pull_active is
	# already False by the time _physics_process next checks it, so that
	# True->False edge never fires power_pull_finished -- same reasoning as
	# _on_car_selected()'s direct reset, reused here via _reset_pull_ui().
	controller.stop_power_pull()
	_reset_pull_ui()


func _on_clear_graph_pressed() -> void:
	# Wipes the recorded torque/power-vs-rpm curve without starting a new
	# pull or touching anything else -- the live RPM/torque/power/etc.
	# readouts above always reflect the sim's current tick regardless
	# (see _process()), so there's nothing to "clear" about those; this is
	# specifically for getting a clean graph before/without a fresh run.
	graph.clear_history()


func _reset_pull_ui() -> void:
	"""Shared by every path that ends/aborts a pull -- the rev limiter
	finishing it, a manual Finish press, or switching car/turbo/mode/tire/
	transmission mid-pull -- so the Start/Finish buttons and throttle slider
	always land back in the same "ready for a fresh pull" state regardless
	of which of those actually happened."""
	graph.clear_history()
	power_pull_button.disabled = false
	power_pull_button.text = "Start Power Pull"
	finish_pull_button.disabled = true
	throttle_slider.value = 0.0
	_on_throttle_changed(0.0)


func _on_mode_toggled(enabled: bool) -> void:
	controller.select_dyno_mode_chassis(enabled)
	# Chassis vs crank mode aren't comparable on the same torque/power graph
	# (a chassis pull is driven, geared and slip-limited, not a paced crank
	# sweep) -- clear it same as a car/turbo swap does.
	_reset_pull_ui()
	_update_gear_label()
	_update_shift_buttons_enabled()


func _on_tire_selected(index: int) -> void:
	controller.select_tire_by_index(index)


func _on_transmission_selected(index: int) -> void:
	controller.select_transmission_by_index(index)
	_reset_pull_ui()
	_update_gear_label()
	_update_shift_buttons_enabled()


func _on_shift_up_pressed() -> void:
	controller.shift_up()


func _on_shift_down_pressed() -> void:
	controller.shift_down()
