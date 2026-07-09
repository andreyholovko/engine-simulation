extends Node2D
## Mid-distance scrolling layer -- a row of building silhouettes. Manually
## wrapped/repeated by drag_race.gd rather than ParallaxLayer's mirroring --
## see bg_mountains.gd's header comment for the full story.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const TILE_W := 600.0
const BUILDING_COLOR := Color(0.16, 0.18, 0.24)
const REPEAT_FROM := -1
const REPEAT_TO := 5  # (REPEAT_TO - REPEAT_FROM) * TILE_W must comfortably exceed Layout.VIEWPORT_W

# (x_fraction_of_tile, width_px, height_px) -- deterministic, not random, so
# the tile's own seam lines up with itself.
const BUILDINGS := [
	Vector2(0.02, 70.0), Vector2(0.14, 110.0), Vector2(0.3, 60.0),
	Vector2(0.4, 150.0), Vector2(0.58, 80.0), Vector2(0.7, 130.0),
	Vector2(0.85, 65.0),
]
const BUILDING_WIDTH_PX := 70.0


func _draw() -> void:
	var base_y := Layout.ROAD_Y
	for tile in range(REPEAT_FROM, REPEAT_TO):
		var shift := tile * TILE_W
		for b in BUILDINGS:
			# `b` comes out of iterating an untyped Array literal (BUILDINGS)
			# as a Variant, even though every element is actually a Vector2 --
			# the static analyzer won't infer a member access on it, same
			# "Cannot infer the type" failure documented in dyno_ui.gd's
			# _update_shift_buttons_enabled(). Explicit `: float` sidesteps it.
			var x: float = shift + b.x * TILE_W
			var height: float = b.y
			draw_rect(Rect2(x, base_y - height, BUILDING_WIDTH_PX, height), BUILDING_COLOR)
