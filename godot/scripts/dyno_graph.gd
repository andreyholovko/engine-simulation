extends Control
## Minimal live torque/power-vs-rpm plot, filled during a power pull.
## Blue = torque (Nm), orange = power (kW). Axis maxima are sized for the
## EA888 Gen3 preset; revisit if you add a bigger engine.

var rpm_history: Array[float] = []
var torque_history: Array[float] = []
var power_history: Array[float] = []

const MAX_RPM := 7000.0
const MAX_TORQUE := 400.0
const MAX_POWER := 200.0


func clear_history() -> void:
	rpm_history.clear()
	torque_history.clear()
	power_history.clear()
	queue_redraw()


func add_point(rpm: float, torque_nm: float, power_kw: float) -> void:
	rpm_history.append(rpm)
	torque_history.append(torque_nm)
	power_history.append(power_kw)
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
		var x: float = (rpm_history[i] / MAX_RPM) * size.x
		var ty: float = size.y - (torque_history[i] / MAX_TORQUE) * size.y
		var py: float = size.y - (power_history[i] / MAX_POWER) * size.y
		torque_points.append(Vector2(x, ty))
		power_points.append(Vector2(x, py))

	draw_polyline(torque_points, Color(0.2, 0.6, 1.0), 2.0, true)
	draw_polyline(power_points, Color(1.0, 0.5, 0.1), 2.0, true)
