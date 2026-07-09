extends RefCounted
## Shared screen-space constants for the drag race scene -- every drawing
## script (bg_*.gd, car_body.gd, wheel_shape.gd) and drag_race.gd itself
## preload this instead of each hardcoding its own copy of "where's the
## road" / "how many pixels is a meter," so the horizon, road surface and
## car all agree on the same geometry.

const VIEWPORT_W := 1280.0
const VIEWPORT_H := 720.0

# Where the road surface (and so the car's wheels) sits vertically.
const ROAD_Y := 560.0
const ROAD_HEIGHT := 90.0

# World distance -> screen pixels for the scrolling layers/finish line, AND
# for wheel rotation (see drag_race.gd's wheel_visual_scale) -- one shared
# constant is what keeps those two in sync at all, so it isn't picked freely
# for "looks nice" pacing. Anchored to the car sprite's own real-world size
# instead: car_body.gd's silhouette spans 225px nose-to-tail (-110..115,
# excluding the rear wing), and a compact-to-mid performance car (this
# scene's whole GTI/340i/Corvette theme) is realistically ~4.5m long, so
# 225px / 4.5m ~= 50 px/m. At that scale a real wheel radius (tire_radius_m,
# ~0.316m) would draw at ~16px -- too small to read as a wheel at all, which
# is exactly why WHEEL_RADIUS_PX below is drawn bigger than true scale calls
# for; wheel_visual_scale is what keeps that oversized sprite's *rotation
# rate* physically correct regardless (a non-slipping wheel's rim still
# tracks the road's own scroll speed exactly), even though its drawn *size*
# isn't literal.
const PIXELS_PER_METER := 50.0

# The car sprite never actually moves -- the world scrolls under it (see
# drag_race.gd) -- so its screen X is fixed here, roughly a third of the way
# across so there's runway ahead to watch the finish line approach.
const CAR_SCREEN_X := 360.0
const CAR_WHEELBASE_PX := 130.0
const WHEEL_RADIUS_PX := 26.0
