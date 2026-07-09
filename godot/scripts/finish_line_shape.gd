extends Node2D
## The quarter-mile marker -- a checkered gantry drawn once; drag_race.gd
## moves this node's own `position.x` every frame (it isn't inside a
## ParallaxLayer -- it represents one fixed point in the world, not a
## tiling background, so it needs its own true position, computed the same
## way the road layer scrolls: world distance * PIXELS_PER_METER).

const Layout = preload("res://scripts/drag_scene_layout.gd")

const POLE_COLOR := Color(0.2, 0.2, 0.2)
const SQUARE := 18.0
const COLUMNS := 2
const ROWS := 10
const GANTRY_HEIGHT := ROWS * SQUARE


func _draw() -> void:
	var base_y := Layout.ROAD_Y
	var top_y := base_y - GANTRY_HEIGHT
	draw_rect(Rect2(-4.0, top_y, 8.0, GANTRY_HEIGHT), POLE_COLOR)
	for row in range(ROWS):
		for col in range(COLUMNS):
			var is_white := (row + col) % 2 == 0
			var color := Color.WHITE if is_white else Color.BLACK
			draw_rect(Rect2(col * SQUARE, top_y + row * SQUARE, SQUARE, SQUARE), color)
