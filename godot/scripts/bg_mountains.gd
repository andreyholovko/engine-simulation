extends Node2D
## Farthest scrolling layer -- a static jagged silhouette, deterministic (not
## random) so it tiles seamlessly. drag_race.gd wraps this node's own
## `position.x` every frame with `fmod(distance, TILE_W)` (see its
## _scroll_layer() helper) rather than relying on ParallaxLayer's built-in
## mirroring -- see that script's header comment for why: ParallaxBackground/
## ParallaxLayer's scroll turned out to be driven by camera position, not the
## `scroll_offset` this scene needs to drive by hand (fixed camera, world
## scrolls under a screen-fixed car), so plain Node2D + manual wrapping
## replaced it entirely. Because wrapping only ever shifts this node within
## one tile width, _draw() has to lay down enough repeated copies itself
## (REPEAT_FROM..REPEAT_TO) to cover the full viewport at any wrap phase --
## the mirroring that used to do this for free.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const TILE_W := 800.0
const PEAK_COLOR := Color(0.24, 0.28, 0.38)
const REPEAT_FROM := -1
const REPEAT_TO := 4  # (REPEAT_TO - REPEAT_FROM) * TILE_W must comfortably exceed Layout.VIEWPORT_W

# Ridge line as fractions of (TILE_W, peak-height-above-base) -- deterministic
# zigzag, not random, so the tile's right edge silhouette matches its own
# left edge one tile over.
const RIDGE := [
	Vector2(0.0, 0.35), Vector2(0.12, 0.85), Vector2(0.22, 0.55),
	Vector2(0.35, 1.0), Vector2(0.48, 0.4), Vector2(0.6, 0.75),
	Vector2(0.72, 0.3), Vector2(0.85, 0.9), Vector2(1.0, 0.35),
]


func _draw() -> void:
	var base_y := Layout.ROAD_Y - 60.0
	var peak_span := 220.0
	for tile in range(REPEAT_FROM, REPEAT_TO):
		var shift := tile * TILE_W
		var points := PackedVector2Array()
		points.append(Vector2(shift, base_y))
		for p in RIDGE:
			points.append(Vector2(shift + p.x * TILE_W, base_y - p.y * peak_span))
		points.append(Vector2(shift + TILE_W, base_y))
		draw_colored_polygon(points, PEAK_COLOR)
