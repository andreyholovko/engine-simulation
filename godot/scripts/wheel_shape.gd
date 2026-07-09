extends Node2D
## A single wheel -- tire + rim + spokes, drawn around this node's own
## origin so setting `rotation` (done every physics frame from
## drag_race.gd, driven by the sim's real wheel_rpm) spins it visibly in
## place. Purely a shape; no per-frame logic of its own.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const TIRE_COLOR := Color(0.05, 0.05, 0.05)
const RIM_COLOR := Color(0.65, 0.65, 0.68)
const SPOKE_COLOR := Color(0.4, 0.4, 0.42)
const SPOKE_COUNT := 5


func _draw() -> void:
	var r := Layout.WHEEL_RADIUS_PX
	draw_circle(Vector2.ZERO, r, TIRE_COLOR)
	draw_circle(Vector2.ZERO, r * 0.55, RIM_COLOR)
	for i in range(SPOKE_COUNT):
		var angle := TAU * float(i) / float(SPOKE_COUNT)
		var tip := Vector2(cos(angle), sin(angle)) * r * 0.5
		draw_line(Vector2.ZERO, tip, SPOKE_COLOR, 4.0)
