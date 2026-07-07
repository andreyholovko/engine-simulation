extends Control
## Minimal live torque/power-vs-rpm plot, filled during a power pull.
## Blue = torque (Nm), orange = power (kW). Axes auto-scale to the largest
## rpm/torque/power seen so far this run rather than a fixed ceiling -- with
## engines now selectable (EA888 peaks ~324Nm/156kW/6700rpm, B58 ~446Nm/
## 236kW/7000rpm), a hardcoded constant sized for one engine clips the other.

var rpm_history: Array[float] = []
var torque_history: Array[float] = []
var power_history: Array[float] = []

var _max_rpm := 7000.0
var _max_torque := 400.0
var _max_power := 200.0

const HEADROOM := 1.1  # keep the peak off the very top/right edge


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


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color(0.5, 0.5, 0.5, 0.08), true)
	draw_line(Vector2(0, size.y), Vector2(size.x, size.y), Color.GRAY, 1.0)
	draw_line(Vector2(0, 0), Vector2(0, size.y), Color.GRAY, 1.0)

	if rpm_history.size() < 2:
		return

	var torque_points := PackedVector2Array()
	var power_points := PackedVector2Array()
	for i in rpm_history.size():
		var x: float = (rpm_history[i] / _max_rpm) * size.x
		var ty: float = size.y - (torque_history[i] / _max_torque) * size.y
		var py: float = size.y - (power_history[i] / _max_power) * size.y
		torque_points.append(Vector2(x, ty))
		power_points.append(Vector2(x, py))

	draw_polyline(torque_points, Color(0.2, 0.6, 1.0), 2.0, true)
	draw_polyline(power_points, Color(1.0, 0.5, 0.1), 2.0, true)
