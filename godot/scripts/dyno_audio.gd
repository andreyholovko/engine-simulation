extends AudioStreamPlayer
## Procedurally synthesizes engine and turbo sound from the live
## DynoController state -- no audio assets.
##
## Built from scratch using a different technique than an earlier attempt
## (see git history: retriggered pulses with a separate decaying envelope,
## which clicked once pulses overlapped at higher rpm). Both oscillators here
## are pure functions of a single continuously-advancing phase, never hard-
## reset and never driven by a separate envelope variable that can jump.
## Cylinder-to-cylinder amplitude changes are timed to land exactly on the
## engine waveform's zero-crossings (see _engine_sample), so they can never
## introduce a discontinuity no matter how abruptly they change -- there is
## no click to fix because there's nothing left that can discontinuously
## jump.
##
## Godot audio practices followed here:
## - AudioStreamGenerator + AudioStreamGeneratorPlayback, refilled from
##   _process() by checking get_frames_available() every frame -- the
##   standard pattern for procedural/generated audio in Godot.
## - Every property read from `controller` is int/float/bool -- `str`
##   properties on that node are unconfirmed/risky in py4godot (see
##   dyno_controller.py's own comments); firing order crosses the boundary as
##   an index-addressed int, not an array.
## - No per-sample allocation (no Dictionary/Array literals, no node lookups)
##   in the hot path -- this runs 44100 times a second.

@onready var controller = $"../DynoController"

const SAMPLE_RATE := 44100.0
const MAX_CYLINDERS := 8

var _playback: AudioStreamGeneratorPlayback

# --- engine ---
# Phase is counted in *cylinders*, not radians: floor(phase) is which firing
# event (0..cylinders-1) we're in, fmod(phase, 1) is position within it.
var _engine_phase := 0.0
var _engine_lp := 0.0  # one-pole lowpass state -- bigger engines get a lower cutoff, hence deeper

# Per-cylinder amplitude signature, indexed by cylinder number (1-based, so
# index 0 is unused) -- a plain fixed-size array so the hot path never
# touches a Dictionary. Real cylinder-to-cylinder variance (manufacturing
# tolerance, runner length) is fixed for a given physical engine, so this is
# regenerated only when the engine actually changes, not per sample.
var _cylinder_amps: Array[float] = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
var _cached_engine_generation := -1

# --- turbo whine ---
var _turbo_phase := 0.0


func _ready() -> void:
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = SAMPLE_RATE
	gen.buffer_length = 0.1
	stream = gen
	play()
	_playback = get_stream_playback()


func _process(_delta: float) -> void:
	if _playback == null:
		return
	_refresh_cylinder_signature()
	var frames := _playback.get_frames_available()
	for i in frames:
		_playback.push_frame(_next_sample())


func _refresh_cylinder_signature() -> void:
	if controller.engine_generation == _cached_engine_generation:
		return
	_cached_engine_generation = controller.engine_generation
	# Deterministic per engine generation (not the shared/global RNG, and not
	# redrawn every firing event) -- a given engine's per-cylinder character
	# is fixed for the session.
	var rng := RandomNumberGenerator.new()
	rng.seed = _cached_engine_generation * 97 + 1
	for i in MAX_CYLINDERS:
		_cylinder_amps[i] = rng.randf_range(0.82, 1.0)


func _engine_sample(dt: float) -> float:
	var rpm: float = controller.rpm
	var cylinders: int = max(controller.cylinders, 1)
	var fire_hz: float = max(cylinders * rpm / 120.0, 1.0)

	_engine_phase = fmod(_engine_phase + fire_hz * dt, float(cylinders))
	var cycle_index: int = int(_engine_phase)
	var t: float = _engine_phase - float(cycle_index)  # 0..1 within this firing event

	var order_length: int = max(controller.firing_order_length, 1)
	var cyl: int = controller.get_firing_order_cylinder(cycle_index % order_length)
	var amp: float = _cylinder_amps[clampi(cyl - 1, 0, MAX_CYLINDERS - 1)]

	# One half-sine hump per firing event, cubed to sharpen it into more of a
	# percussive beat than a smooth tone. sin(PI*t) is exactly 0 at t=0 and
	# t=1 -- the zero-crossing `amp` (a different value every cylinder) rides
	# on, which is what makes changing it every firing event safe.
	var shape: float = sin(PI * t)
	var pulse: float = shape * shape * shape * amp

	# Bigger engine -> deeper: lower the lowpass cutoff as displacement rises.
	# Normalized around the EA888's 2.0L (cutoff ~2200Hz, brightest) down to
	# the B58's 3.0L (~650Hz, noticeably darker/deeper) despite similar
	# per-cylinder size -- total displacement is what's modeled, matching
	# "bigger engine sounds deeper" rather than "more cylinders sound deeper."
	var displacement_l: float = controller.displacement_l
	var cutoff_hz: float = lerp(2200.0, 650.0, clamp((displacement_l - 1.4) / 2.2, 0.0, 1.0))
	var lp_coeff: float = 1.0 - exp(-TAU * cutoff_hz * dt)
	_engine_lp += (pulse - _engine_lp) * lp_coeff

	var rpm_gate: float = clamp(rpm / 150.0, 0.0, 1.0)  # genuinely silent once the engine truly stops
	var loudness: float = lerp(0.35, 1.0, clamp((rpm - 500.0) / 6500.0, 0.0, 1.0))
	return _engine_lp * loudness * rpm_gate


func _turbo_sample(dt: float) -> float:
	var boost_bar: float = controller.boost_bar
	var max_boost_bar: float = max(controller.max_boost_bar, 0.01)
	var spool: float = clamp(boost_bar / max_boost_bar, 0.0, 1.0)

	var whine_hz: float = lerp(600.0, 3500.0, spool)
	_turbo_phase = fmod(_turbo_phase + whine_hz * dt, 1.0)
	# Gain is a conservative starting point (turbo whine is easy to overdo) --
	# retune by ear once this is actually running in Godot.
	return sin(TAU * _turbo_phase) * pow(spool, 1.4) * 0.0015


func _next_sample() -> Vector2:
	var dt := 1.0 / SAMPLE_RATE
	var mixed: float = clamp(_engine_sample(dt) * 0.8 + _turbo_sample(dt), -1.0, 1.0)
	return Vector2(mixed, mixed)
