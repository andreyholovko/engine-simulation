extends Node2D
## The road surface itself -- scrolls at exactly the car's real ground speed
## (motion_scale 1.0; every other layer here is slower or faster than that
## for depth -- see drag_race.gd's _scroll_layer() calls). Manually wrapped/
## repeated rather than relying on ParallaxLayer's mirroring -- see
## bg_mountains.gd's header comment for the full story.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const TILE_W := 400.0
const ASPHALT_COLOR := Color(0.12, 0.12, 0.14)
const CURB_COLOR := Color(0.55, 0.1, 0.1)
const DASH_COLOR := Color(0.85, 0.75, 0.2)
const DASH_WIDTH := 60.0
const DASH_HEIGHT := 6.0
const REPEAT_FROM := -1
const REPEAT_TO := 6  # (REPEAT_TO - REPEAT_FROM) * TILE_W must comfortably exceed Layout.VIEWPORT_W


func _draw() -> void:
	var dash_y := Layout.ROAD_Y + Layout.ROAD_HEIGHT * 0.5
	for tile in range(REPEAT_FROM, REPEAT_TO):
		var shift := tile * TILE_W
		draw_rect(Rect2(shift, Layout.ROAD_Y, TILE_W, Layout.ROAD_HEIGHT), ASPHALT_COLOR)
		draw_rect(Rect2(shift, Layout.ROAD_Y, TILE_W, 6.0), CURB_COLOR)
		draw_rect(Rect2(shift + TILE_W * 0.25, dash_y, DASH_WIDTH, DASH_HEIGHT), DASH_COLOR)
		draw_rect(Rect2(shift + TILE_W * 0.75, dash_y, DASH_WIDTH, DASH_HEIGHT), DASH_COLOR)
