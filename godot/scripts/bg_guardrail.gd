extends Node2D
## Nearest scrolling layer -- a trackside guardrail passing close to the
## viewer, scrolls faster than the road itself (the standard "something
## rushing by in the foreground" speed cue -- see drag_race.gd's
## _scroll_layer() calls). Manually wrapped/repeated rather than relying on
## ParallaxLayer's mirroring -- see bg_mountains.gd's header comment for the
## full story.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const TILE_W := 200.0
const RAIL_COLOR := Color(0.75, 0.75, 0.78)
const POST_COLOR := Color(0.3, 0.3, 0.32)
const RAIL_Y := 40.0  # px above the road surface
const POST_WIDTH := 8.0
const POST_HEIGHT := 50.0
const REPEAT_FROM := -1
const REPEAT_TO := 10  # (REPEAT_TO - REPEAT_FROM) * TILE_W must comfortably exceed Layout.VIEWPORT_W


func _draw() -> void:
	var base_y := Layout.ROAD_Y - RAIL_Y
	for tile in range(REPEAT_FROM, REPEAT_TO):
		var shift := tile * TILE_W
		draw_rect(Rect2(shift, base_y, TILE_W, 10.0), RAIL_COLOR)
		draw_rect(Rect2(shift + TILE_W * 0.15, base_y, POST_WIDTH, POST_HEIGHT), POST_COLOR)
		draw_rect(Rect2(shift + TILE_W * 0.65, base_y, POST_WIDTH, POST_HEIGHT), POST_COLOR)
