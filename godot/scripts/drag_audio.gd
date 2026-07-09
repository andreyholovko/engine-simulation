extends AudioStreamPlayer
## Procedurally synthesizes engine and turbo sound for the drag race scene --
## identical synthesis to dyno_audio.gd (see that file for the full
## rationale: continuous-phase oscillators, zero-crossing-timed cylinder
## variance, a resonant exhaust filter, turbo whine sized off max_boost_bar),
## just pointed at DragController instead of DynoController. Kept as its own
## copy rather than a shared/parameterized script -- this scene's controller
## exposes the same field *names* dyno_audio.gd already reads (cylinders,
## displacement_l, firing_order_length, get_firing_order_cylinder(),
## engine_generation, boost_bar, max_boost_bar, rpm) but is a different node
## at a different relative path, and duplicating one small self-contained
## script is simpler than adding a configurable path to the working one.

@onready var controller = $"../DragController"

const SAMPLE_RATE := 44100.0
const MAX_CYLINDERS := 8

var _playback: AudioStreamGeneratorPlayback

# --- engine ---
var _engine_phase := 0.0
var _engine_lp := 0.0

var _cylinder_amps: Array[float] = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
var _cached_engine_generation := -1

# --- exhaust ---
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
	var t: float = _engine_phase - float(cycle_index)

	var order_length: int = max(controller.firing_order_length, 1)
	var cyl: int = controller.get_firing_order_cylinder(cycle_index % order_length)
	var amp: float = _cylinder_amps[clampi(cyl - 1, 0, MAX_CYLINDERS - 1)]

	var shape: float = sin(PI * t)
	var pulse: float = shape * shape * shape * amp

	var displacement_l: float = controller.displacement_l
	var cutoff_hz: float = lerp(1700.0, 500.0, clamp((displacement_l - 1.4) / 2.2, 0.0, 1.0))
	var lp_coeff: float = 1.0 - exp(-TAU * cutoff_hz * dt)
	_engine_lp += (pulse - _engine_lp) * lp_coeff

	var rpm_gate: float = clamp(rpm / 150.0, 0.0, 1.0)
	var loudness: float = lerp(0.35, 1.0, clamp((rpm - 500.0) / 6500.0, 0.0, 1.0))
	return _engine_lp * loudness * rpm_gate


func _exhaust_filter(input: float, dt: float) -> float:
	var displacement_l: float = controller.displacement_l
	var cutoff_hz: float = lerp(220.0, 90.0, clamp((displacement_l - 1.4) / 2.2, 0.0, 1.0))
	var f: float = 2.0 * sin(PI * cutoff_hz * dt)
	var damping := 1.1
	_exhaust_low += f * _exhaust_band
	var high: float = input - _exhaust_low - damping * _exhaust_band
	_exhaust_band += f * high
	return _exhaust_low


func _turbo_sample(dt: float) -> float:
	var boost_bar: float = controller.boost_bar
	var max_boost_bar: float = max(controller.max_boost_bar, 0.01)
	var spool: float = clamp(boost_bar / max_boost_bar, 0.0, 1.0)

	var size_fraction: float = clamp((max_boost_bar - 1.0) / 1.3, 0.0, 1.0)
	var pitch_low: float = lerp(600.0, 350.0, size_fraction)
	var pitch_high: float = lerp(3500.0, 2200.0, size_fraction)
	var whine_hz: float = lerp(pitch_low, pitch_high, spool)
	_turbo_phase = fmod(_turbo_phase + whine_hz * dt, 1.0)

	var pressure_gain: float = clamp(boost_bar / 1.3, 0.0, 1.6)
	return sin(TAU * _turbo_phase) * pow(spool, 1.4) * pressure_gain * 0.0015


func _next_sample() -> Vector2:
	var dt := 1.0 / SAMPLE_RATE
	var exhaust_note: float = _exhaust_filter(_engine_sample(dt), dt)
	var mixed: float = clamp(exhaust_note * 0.8 + _turbo_sample(dt), -1.0, 1.0)
	return Vector2(mixed, mixed)
