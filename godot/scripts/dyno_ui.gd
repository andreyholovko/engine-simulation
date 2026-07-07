extends Control
## Wires the UI controls to the Python-backed dyno_controller node and
## refreshes the live readout every frame. All simulation math lives in
## engine_sim (pure Python) via DynoController -- this script only moves
## numbers between widgets and that node.

@onready var controller = $DynoController
@onready var engine_option: OptionButton = $Layout/EngineRow/EngineOption
@onready var boost_slider: HSlider = $Layout/BoostRow/BoostSlider
@onready var boost_target_label: Label = $Layout/BoostRow/BoostTargetLabel
@onready var afr_checkbox: CheckBox = $Layout/AfrRow/AfrCheckBox
@onready var afr_slider: HSlider = $Layout/AfrRow/AfrSlider
@onready var afr_value_label: Label = $Layout/AfrRow/AfrValueLabel
@onready var ramp_rate_slider: HSlider = $Layout/PowerPullRow/RampRateSlider
@onready var ramp_rate_label: Label = $Layout/PowerPullRow/RampRateLabel
@onready var power_pull_button: Button = $Layout/PowerPullRow/PowerPullButton
@onready var rpm_value: Label = $Layout/Readouts/RpmValue
@onready var torque_value: Label = $Layout/Readouts/TorqueValue
@onready var power_value: Label = $Layout/Readouts/PowerValue
@onready var boost_value: Label = $Layout/Readouts/BoostValue
@onready var afr_value: Label = $Layout/Readouts/AfrValue
@onready var ve_value: Label = $Layout/Readouts/VeValue
@onready var air_value: Label = $Layout/Readouts/AirValue
@onready var fuel_value: Label = $Layout/Readouts/FuelValue
@onready var cr_value: Label = $Layout/Readouts/CrValue
@onready var rev_limiter_value: Label = $Layout/Readouts/RevLimiterValue
@onready var graph = $Layout/DynoGraph


# Hardcoded, matching engine_sim/presets/__init__.py's ENGINE_CHOICES order
# exactly -- deliberately NOT read from controller.engine_choices (a `str`
# property), because py4godot's own examples only ever show int/float/bool/
# Vector3 properties, never str, and that was confirmed to be the actual
# cause of the engine picker not working at all: an empty/broken string
# meant an empty dropdown. Selection is driven by plain index (int), a type
# already confirmed working (cylinders, rpm, etc. all display correctly).
# Keep this list in sync with ENGINE_CHOICES if you add a third engine.
const ENGINE_LABELS := [
	"VW/Audi EA888 Gen3 (MK7 GTI, IS20)",
	"BMW B58B30 (340i)",
	"GM LS2 (Corvette C6, NA)",
]


func _ready() -> void:
	controller.power_pull_finished.connect(_on_power_pull_finished)
	_populate_engine_options()


func _populate_engine_options() -> void:
	for label in ENGINE_LABELS:
		engine_option.add_item(label)
	if engine_option.item_count > 0:
		engine_option.select(0)


func _process(_delta: float) -> void:
	rpm_value.text = "%.0f" % controller.rpm
	torque_value.text = "%.1f" % controller.torque_nm
	power_value.text = "%.1f" % controller.power_kw
	boost_value.text = "%.2f" % controller.boost_bar
	afr_value.text = "%.2f" % controller.afr_actual
	ve_value.text = "%.2f" % controller.volumetric_efficiency
	air_value.text = "%.2f" % controller.air_mass_flow_g_s
	fuel_value.text = "%.2f" % controller.fuel_mass_flow_g_s
	cr_value.text = "%.2f" % controller.effective_compression_ratio
	rev_limiter_value.text = "CUT" if controller.rev_limiter_active else "off"

	if controller.power_pull_active:
		graph.add_point(controller.rpm, controller.torque_nm, controller.power_kw)


func _on_engine_selected(index: int) -> void:
	controller.select_engine_by_index(index)
	# Switching engines always aborts any in-progress pull (DynoSession.
	# select_engine() resets it internally) -- but that happens synchronously
	# here, before the next _physics_process runs, so the usual True->False
	# transition _physics_process watches for to fire power_pull_finished
	# never happens (is_power_pull_active is already False by the time it
	# next checks). Reset the button/graph directly instead of relying on
	# that signal for this specific case.
	graph.clear_history()
	power_pull_button.disabled = false
	power_pull_button.text = "Start Power Pull (WOT sweep)"


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


func _on_ramp_rate_changed(value: float) -> void:
	ramp_rate_label.text = "Ramp: %d rpm/s" % int(value)
	controller.ramp_rate_rpm_s = value


func _on_power_pull_pressed() -> void:
	graph.clear_history()
	power_pull_button.disabled = true
	power_pull_button.text = "Power pull running..."
	controller.start_power_pull()


func _on_power_pull_finished() -> void:
	power_pull_button.disabled = false
	power_pull_button.text = "Start Power Pull (WOT sweep)"
