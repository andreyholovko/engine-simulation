extends Node2D
## Backmost layer -- static sky (motion_scale = (0,0) in the scene, so it
## never scrolls at all, the same way a real horizon barely appears to move).
## Covers the full viewport once; unlike the other bg_*.gd layers this one
## has no ParallaxLayer.motion_mirroring to keep in sync with, since it
## never needs to tile.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const SKY_TOP := Color(0.35, 0.55, 0.85)
const SKY_HORIZON := Color(0.75, 0.82, 0.85)
const SUN_COLOR := Color(1.0, 0.95, 0.75)


func _draw() -> void:
	var horizon_y := Layout.ROAD_Y - 260.0
	draw_rect(Rect2(0.0, 0.0, Layout.VIEWPORT_W, horizon_y * 0.6), SKY_TOP)
	draw_rect(Rect2(0.0, horizon_y * 0.6, Layout.VIEWPORT_W, horizon_y * 0.4), SKY_HORIZON)
	draw_circle(Vector2(Layout.VIEWPORT_W * 0.78, horizon_y * 0.3), 45.0, SUN_COLOR)
