extends Node2D
## Car silhouette -- static shape, drawn once, in the Car node's own local
## space (origin sits on the road surface, midway between the wheels; +x is
## forward/right, -y is up). Purely decorative: drag_race.gd never touches
## this node directly, only the wheel children (for rotation) and the
## SmokeParticles child (for wheelspin).

const Layout = preload("res://scripts/drag_scene_layout.gd")

const BODY_COLOR := Color(0.78, 0.12, 0.12)
const WINDOW_COLOR := Color(0.55, 0.75, 0.85, 0.9)
const SPOILER_COLOR := Color(0.1, 0.1, 0.12)
const SHADOW_COLOR := Color(0.0, 0.0, 0.0, 0.35)

const HALF_WHEELBASE := Layout.CAR_WHEELBASE_PX * 0.5
const RIDE_HEIGHT := Layout.WHEEL_RADIUS_PX  # chassis floor sits level with the wheel centers -- a low, drag-car ride height


func _draw() -> void:
	# A contact shadow, not just relying on the wheels touching y=0 exactly
	# -- without one the car reads as floating above the road even when the
	# geometry is pixel-flush, because there's no visual cue actually tying
	# it down to the ground plane. Drawn first (and so under everything
	# else this node and the wheel nodes draw -- see Car's own child order
	# in DragRace.tscn) so it sits beneath the body/wheels, not on top.
	_draw_shadow()

	var floor_y := -RIDE_HEIGHT
	var body := PackedVector2Array([
		Vector2(-HALF_WHEELBASE - 45, floor_y),
		Vector2(-HALF_WHEELBASE - 45, floor_y - 30),
		Vector2(-HALF_WHEELBASE - 10, floor_y - 55),
		Vector2(HALF_WHEELBASE - 25, floor_y - 60),
		Vector2(HALF_WHEELBASE + 20, floor_y - 30),
		Vector2(HALF_WHEELBASE + 50, floor_y - 18),
		Vector2(HALF_WHEELBASE + 50, floor_y),
	])
	draw_colored_polygon(body, BODY_COLOR)

	var window := PackedVector2Array([
		Vector2(-HALF_WHEELBASE, floor_y - 32),
		Vector2(-HALF_WHEELBASE + 20, floor_y - 52),
		Vector2(HALF_WHEELBASE - 40, floor_y - 56),
		Vector2(HALF_WHEELBASE - 20, floor_y - 32),
	])
	draw_colored_polygon(window, WINDOW_COLOR)

	# Rear wing -- struts + blade, the "unmistakably a drag car" detail.
	var strut_x := -HALF_WHEELBASE - 30
	draw_rect(Rect2(strut_x, floor_y - 30, 6, 30), SPOILER_COLOR)
	draw_rect(Rect2(strut_x - 20, floor_y - 40, 46, 10), SPOILER_COLOR)


func _draw_shadow() -> void:
	# Flattened ellipse at wheel-contact height (y=0, this node's own
	# origin), roughly spanning the car's own footprint plus a small margin
	# -- draw_colored_polygon has no ellipse primitive, so it's approximated
	# with a ring of points.
	var center_x := (HALF_WHEELBASE + 50 - HALF_WHEELBASE - 45) * 0.5
	var rx := HALF_WHEELBASE + 60.0
	var ry := 10.0
	var segments := 24
	var points := PackedVector2Array()
	for i in segments:
		var a := TAU * float(i) / float(segments)
		points.append(Vector2(center_x + cos(a) * rx, sin(a) * ry))
	draw_colored_polygon(points, SHADOW_COLOR)
