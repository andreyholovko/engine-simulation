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
## The raw per-cylinder pulse train is deliberately NOT the final output --
## real exhaust note doesn't sound like individually-audible cylinder hits,
## because it's been through a manifold and a muffler by the time it reaches
## your ear, both of which are resonant acoustic chambers that let one
## firing pulse ring into and blend with the next rather than decaying to
## silence between hits. _exhaust_filter() models that stage explicitly and
## separately from the engine's own combustion-tone filtering (_engine_lp).
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

# --- exhaust (muffler/manifold resonance, applied after the raw per-
# cylinder pulses -- see _exhaust_filter) ---
var _exhaust_low := 0.0
var _exhaust_band := 0.0

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
	# Normalized around the EA888's 2.0L (cutoff ~1382Hz, brightest) down to
	# the B58's 3.0L (~829Hz) and the LS2's 6.0L (~500Hz floor) -- total
	# displacement is what's modeled, matching "bigger engine sounds deeper"
	# rather than "more cylinders sound deeper." Range lowered ~25% across
	# the board (was 2200-650Hz) for an overall deeper tone on every engine --
	# note this is the harmonic-brightness knob, not the firing rate itself
	# (fire_hz stays tied to real rpm; changing that would decouple the sound
	# from the actual physics rather than just darken its tone).
	var displacement_l: float = controller.displacement_l
	var cutoff_hz: float = lerp(1700.0, 500.0, clamp((displacement_l - 1.4) / 2.2, 0.0, 1.0))
	var lp_coeff: float = 1.0 - exp(-TAU * cutoff_hz * dt)
	_engine_lp += (pulse - _engine_lp) * lp_coeff

	var rpm_gate: float = clamp(rpm / 150.0, 0.0, 1.0)  # genuinely silent once the engine truly stops
	var loudness: float = lerp(0.35, 1.0, clamp((rpm - 500.0) / 6500.0, 0.0, 1.0))
	return _engine_lp * loudness * rpm_gate


func _exhaust_filter(input: float, dt: float) -> float:
	# Muffler/manifold as a resonant chamber, not just a duller copy of the
	# cylinder pulse -- this is what actually turns "hear every cylinder
	# click individually" into "one continuous note coming out of a pipe."
	# A state-variable (Chamberlin) 2-pole lowpass: mild resonance lets
	# consecutive firing pulses ring into and blend with each other instead
	# of decaying to silence between hits, the way a real exhaust's
	# resonant cavity behaves -- a plain one-pole filter (as used for
	# _engine_lp, modeling the combustion tone itself, a separate stage)
	# only softens each pulse's edges without blending it into the next.
	# Two state floats, no allocation -- safe in this 44.1kHz hot path.
	#
	# Cutoff is calibrated against real firing frequencies (cylinders*rpm/120,
	# ~25-450Hz across idle-to-redline for these engines), not just "lower
	# than _engine_lp's" -- that's what actually matters for whether
	# consecutive pulses blend. Below cutoff (idle/low rpm) pulses stay
	# fairly distinct (a real idle IS somewhat "lopey", not a pure hum);
	# once firing rate climbs past cutoff (cruise/high rpm) they blend into
	# a continuous roar, same as a real exhaust. Bigger engines get a lower
	# cutoff -- bigger, more muffled systems, and a lower idle firing rate
	# to begin with.
	var displacement_l: float = controller.displacement_l
	var cutoff_hz: float = lerp(220.0, 90.0, clamp((displacement_l - 1.4) / 2.2, 0.0, 1.0))
	var f: float = 2.0 * sin(PI * cutoff_hz * dt)
	var damping := 1.1  # > 1 = safely damped -- richer tone, never self-oscillates/whistles
	_exhaust_low += f * _exhaust_band
	var high: float = input - _exhaust_low - damping * _exhaust_band
	_exhaust_band += f * high
	return _exhaust_low


func _turbo_sample(dt: float) -> float:
	var boost_bar: float = controller.boost_bar
	var max_boost_bar: float = max(controller.max_boost_bar, 0.01)
	var spool: float = clamp(boost_bar / max_boost_bar, 0.0, 1.0)

	# Turbo SIZE character (which turbo is fitted -- max_boost_bar as a
	# proxy for compressor/turbine size), separate from spool (how spooled
	# THIS turbo currently is). A physically bigger turbine spins slower at
	# full chat than a small one -- a lower-pitched, more "whoosh" whine --
	# real and audible (e.g. a big aftermarket single vs. a small stock
	# twin-scroll unit), not just "the same curve, higher number."
	var size_fraction: float = clamp((max_boost_bar - 1.0) / 1.3, 0.0, 1.0)
	var pitch_low: float = lerp(600.0, 350.0, size_fraction)
	var pitch_high: float = lerp(3500.0, 2200.0, size_fraction)
	var whine_hz: float = lerp(pitch_low, pitch_high, spool)
	_turbo_phase = fmod(_turbo_phase + whine_hz * dt, 1.0)

	# Loudness scales with the actual boost PRESSURE reached, not just
	# relative spool fraction -- a big turbo genuinely making 2 bar is a
	# more prominent sound event than a small one topping out at 0.7 bar,
	# even though both read "100% spooled" in relative terms. 1.3 bar is
	# the reference point (today's stock EA888/B58 ceiling); gain scales
	# up past it for bigger setups and down for smaller ones (e.g. a mild
	# LS2 twin-turbo kit reading quieter than a big aftermarket single).
	var pressure_gain: float = clamp(boost_bar / 1.3, 0.0, 1.6)
	# Gain is a conservative starting point (turbo whine is easy to overdo) --
	# retune by ear once this is actually running in Godot.
	return sin(TAU * _turbo_phase) * pow(spool, 1.4) * pressure_gain * 0.0015


func _next_sample() -> Vector2:
	var dt := 1.0 / SAMPLE_RATE
	# Turbo whine is intake/compressor-side, not exhaust -- only the engine's
	# own combustion pulses go through the exhaust stage before mixing.
	var exhaust_note: float = _exhaust_filter(_engine_sample(dt), dt)
	var mixed: float = clamp(exhaust_note * 0.8 + _turbo_sample(dt), -1.0, 1.0)
	return Vector2(mixed, mixed)
