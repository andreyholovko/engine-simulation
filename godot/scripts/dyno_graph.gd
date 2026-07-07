extends Control
## Live torque/power-vs-rpm plot, filled during a power pull.
## Blue = torque (Nm, left axis), orange = power (kW, right axis), rpm along
## the bottom. Axes auto-scale to the largest rpm/torque/power seen so far
## this run rather than a fixed ceiling -- with engines now selectable
## (EA888 ~324Nm/156kW/6700rpm, B58 ~446Nm/236kW/7000rpm, LS2 ~539Nm/310kW/
## 6500rpm), a hardcoded constant sized for one engine clips the others.

const TORQUE_COLOR := Color(0.2, 0.6, 1.0)
const POWER_COLOR := Color(1.0, 0.5, 0.1)
const GRID_COLOR := Color(0.6, 0.6, 0.6, 0.35)
const TEXT_COLOR := Color(0.85, 0.85, 0.85)

const MARGIN_LEFT := 56.0    # room for torque (Nm) axis labels
const MARGIN_RIGHT := 56.0   # room for power (kW) axis labels
const MARGIN_TOP := 22.0     # room for the legend
const MARGIN_BOTTOM := 26.0  # room for rpm axis labels
const GRID_DIVISIONS := 4    # 5 gridlines (0%, 25%, 50%, 75%, 100%)
const HEADROOM := 1.1        # keep the peak off the very top/right edge

var rpm_history: Array[float] = []
var torque_history: Array[float] = []
var power_history: Array[float] = []

var _max_rpm := 7000.0
var _max_torque := 400.0
var _max_power := 200.0


func clear_history() -> void:
	rpm_history.clear()
	torque_history.clear()
	power_history.clear()
	_max_rpm = 7000.0
	_max_torque = 400.0
	_max_power = 200.0
	queue_redraw()


func add_point(rpm: float, torque_nm: float, power_kw: float) -> void:
	rpm_history.append(rpm)
	torque_history.append(torque_nm)
	power_history.append(power_kw)
	_max_rpm = max(_max_rpm, rpm * HEADROOM)
	_max_torque = max(_max_torque, torque_nm * HEADROOM)
	_max_power = max(_max_power, power_kw * HEADROOM)
	queue_redraw()


func _plot_rect() -> Rect2:
	return Rect2(
		MARGIN_LEFT,
		MARGIN_TOP,
		max(size.x - MARGIN_LEFT - MARGIN_RIGHT, 1.0),
		max(size.y - MARGIN_TOP - MARGIN_BOTTOM, 1.0),
	)


func _draw() -> void:
	var plot := _plot_rect()
	var font := get_theme_default_font()
	var font_size := get_theme_default_font_size()

	draw_rect(plot, Color(0.5, 0.5, 0.5, 0.08), true)
	_draw_gridlines_and_axis_labels(plot, font, font_size)
	_draw_legend(font, font_size)

	if rpm_history.size() < 2:
		return

	var torque_points := PackedVector2Array()
	var power_points := PackedVector2Array()
	for i in rpm_history.size():
		var x: float = plot.position.x + (rpm_history[i] / _max_rpm) * plot.size.x
		var ty: float = plot.position.y + plot.size.y - (torque_history[i] / _max_torque) * plot.size.y
		var py: float = plot.position.y + plot.size.y - (power_history[i] / _max_power) * plot.size.y
		torque_points.append(Vector2(x, ty))
		power_points.append(Vector2(x, py))

	draw_polyline(torque_points, TORQUE_COLOR, 2.0, true)
	draw_polyline(power_points, POWER_COLOR, 2.0, true)


func _draw_gridlines_and_axis_labels(plot: Rect2, font: Font, font_size: int) -> void:
	# Horizontal gridlines: left labels are the torque scale, right labels
	# are the power scale -- same gridline, two different meanings, colored
	# to match whichever line they belong to.
	for i in GRID_DIVISIONS + 1:
		var frac: float = float(i) / float(GRID_DIVISIONS)
		var y: float = plot.position.y + plot.size.y * (1.0 - frac)
		draw_line(Vector2(plot.position.x, y), Vector2(plot.position.x + plot.size.x, y), GRID_COLOR, 1.0)

		var torque_label := "%.0f" % (frac * _max_torque)
		var torque_text_size := font.get_string_size(torque_label, HORIZONTAL_ALIGNMENT_RIGHT, -1, font_size)
		draw_string(font, Vector2(plot.position.x - 8.0 - torque_text_size.x, y + font_size * 0.3),
			torque_label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TORQUE_COLOR)

		var power_label := "%.0f" % (frac * _max_power)
		draw_string(font, Vector2(plot.position.x + plot.size.x + 8.0, y + font_size * 0.3),
			power_label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, POWER_COLOR)

	# Vertical gridlines: rpm along the bottom.
	for i in GRID_DIVISIONS + 1:
		var frac: float = float(i) / float(GRID_DIVISIONS)
		var x: float = plot.position.x + plot.size.x * frac
		draw_line(Vector2(x, plot.position.y), Vector2(x, plot.position.y + plot.size.y), GRID_COLOR, 1.0)

		var rpm_label := "%.0f" % (frac * _max_rpm)
		var rpm_text_size := font.get_string_size(rpm_label, HORIZONTAL_ALIGNMENT_CENTER, -1, font_size)
		draw_string(font, Vector2(x - rpm_text_size.x / 2.0, plot.position.y + plot.size.y + font_size + 4.0),
			rpm_label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TEXT_COLOR)

	# X-axis title. (Y-axis meaning is conveyed by the legend + the colored
	# numeric labels themselves -- blue numbers are the torque scale, orange
	# numbers are the power scale.)
	draw_string(font, Vector2(plot.position.x, size.y - 4.0), "RPM",
		HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TEXT_COLOR)


func _draw_legend(font: Font, font_size: int) -> void:
	var x := size.x - 150.0
	var y := 4.0
	draw_line(Vector2(x, y + font_size * 0.4), Vector2(x + 20.0, y + font_size * 0.4), TORQUE_COLOR, 2.0)
	draw_string(font, Vector2(x + 26.0, y + font_size), "Torque (Nm)",
		HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, TORQUE_COLOR)

	y += font_size + 4.0
	draw_line(Vector2(x, y + font_size * 0.4), Vector2(x + 20.0, y + font_size * 0.4), POWER_COLOR, 2.0)
	draw_string(font, Vector2(x + 26.0, y + font_size), "Power (kW)",
		HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, POWER_COLOR)
