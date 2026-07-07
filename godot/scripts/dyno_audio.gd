extends AudioStreamPlayer
## Procedurally synthesizes engine, turbo whine, off-throttle flutter, and
## exhaust pops from the live DynoController state every audio sample -- no
## audio assets, this is pure DSP driven by rpm/throttle/spool_fraction/
## boost_bar. First pass: simple per-sample sine/noise synthesis. If this
## turns out to be too heavy for the audio thread on real hardware (untested
## here -- no Godot in the environment that authored it), the fix is
## wavetable lookup instead of calling sin() per sample, not a redesign.

@onready var controller = $"../DynoController"

const SAMPLE_RATE := 44100.0

var _playback: AudioStreamGeneratorPlayback
var _phase_fire := 0.0
var _phase_whine := 0.0
var _phase_flutter := 0.0
var _phase_pop := 0.0
var _release_env := 0.0
var _release_lp := 0.0
var _prev_throttle_percent := 0.0
var _rng := RandomNumberGenerator.new()

# Exhaust pops: a lift-off event schedules a short, randomly-spaced burst of
# 1-3 pops rather than one clean bang -- real overrun crackle stutters like
# that, it doesn't fire once and stop.
var _dsp_time := 0.0
var _pending_pop_times: Array[float] = []
var _pop_env := 0.0
var _pop_crack_env := 0.0
var _pop_freq := 90.0
var _phase_pop_sub := 0.0

var _intake_lp := 0.0


func _ready() -> void:
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = SAMPLE_RATE
	gen.buffer_length = 0.1
	stream = gen
	_rng.randomize()
	play()
	_playback = get_stream_playback()
	controller.power_pull_finished.connect(_on_power_pull_finished)


func _on_power_pull_finished() -> void:
	# The reliable trigger: dyno_controller.py's own _physics_process runs at
	# 240Hz (project.godot) and emits this signal exactly once, the instant
	# the pull ends. Signals are queued/guaranteed by Godot regardless of
	# when _process happens to run next -- polling throttle_percent here
	# instead used to miss this almost every time, because _process runs at
	# the display's frame rate (~60Hz, unsynchronized with the 240Hz physics
	# tick), so it would very often only ever observe throttle_percent
	# *after* it had already dropped to 0, never catching the single tick
	# where it was still >50%. That's why the pop/flutter at the end of a
	# run was inaudible essentially every time.
	if controller.boost_bar > 0.2:
		_release_env = 1.0
		_schedule_pop_sequence()


func _process(_delta: float) -> void:
	if _playback == null:
		return

	# Off-throttle flutter/blow-off/pops also cover a manual throttle lift
	# (if throttle-driven free-play ever returns) via plain polling -- fine
	# for a human-paced lift, just not reliable for the single-tick end of a
	# power pull, which is why that case uses the signal above instead.
	var throttle_now: float = controller.throttle_percent
	if _prev_throttle_percent > 50.0 and throttle_now <= 50.0 and controller.boost_bar > 0.2:
		_release_env = 1.0
		_schedule_pop_sequence()
	_prev_throttle_percent = throttle_now

	var frames := _playback.get_frames_available()
	for i in frames:
		_playback.push_frame(_next_sample())


func _schedule_pop_sequence() -> void:
	var count := _rng.randi_range(1, 3)
	var t := _dsp_time
	for i in count:
		t += _rng.randf_range(0.05, 0.22)
		_pending_pop_times.append(t)


func _next_sample() -> Vector2:
	var dt := 1.0 / SAMPLE_RATE
	var rpm: float = controller.rpm
	var throttle: float = controller.throttle_percent / 100.0
	var spool: float = controller.spool_fraction
	var cylinders: float = float(controller.cylinders)

	# Engine: harmonics of the firing frequency (a 4-stroke engine fires
	# `cylinders` times every 2 crank revolutions).
	var fire_hz: float = max(cylinders * rpm / 120.0, 1.0)
	_phase_fire = fmod(_phase_fire + fire_hz * dt, 1.0)
	var wave := sin(TAU * _phase_fire) \
		+ sin(TAU * _phase_fire * 2.0) * 0.5 \
		+ sin(TAU * _phase_fire * 3.0) * 0.28 \
		+ sin(TAU * _phase_fire * 4.0) * 0.15
	# Intake hiss: real induction roar comes from actual air rushing in, so
	# this is driven by air_mass_flow_g_s (idle ~5g/s, WOT up towards
	# 170g/s+) rather than a flat noise floor -- quiet and dull at idle,
	# rising in both loudness and brightness as the engine actually breathes
	# harder. That's also what used to read as "constant white noise even at
	# idle": it was scaled by throttle/load, not by how much air was moving.
	var air_g_s: float = controller.air_mass_flow_g_s
	var intake_gain: float = clamp(air_g_s / 150.0, 0.0, 1.0)
	var intake_raw := (_rng.randf() * 2.0 - 1.0)
	_intake_lp += (intake_raw - _intake_lp) * lerp(0.05, 0.35, intake_gain)
	var intake_noise: float = _intake_lp * intake_gain * 0.35

	var load := 0.25 + 0.75 * throttle
	# Gate by actual RPM, not just throttle -- an engine that has genuinely
	# stopped turning (rpm ~0) must be silent regardless of throttle/load,
	# otherwise the idle floor above leaks a constant hiss even with the
	# engine stalled/off.
	var rpm_gate: float = clamp(rpm / 150.0, 0.0, 1.0)
	var engine_sample: float = (wave * 0.45 * load + intake_noise) * rpm_gate

	# Turbo whine: pitch and volume both rise with spool -- the "hiss up to a
	# whistle" as it comes on boost.
	var whine_hz: float = lerp(700.0, 4200.0, spool)
	_phase_whine = fmod(_phase_whine + whine_hz * dt, 1.0)
	var whine: float = sin(TAU * _phase_whine) * pow(spool, 1.5) * 0.35

	# Off-throttle flutter: filtered noise, gated by a fast (~15Hz) chattery
	# on/off oscillator rather than a smooth hiss -- that stutter is what
	# actually reads as "flutter" instead of a plain blow-off hiss. Decays
	# over ~0.6s as the released boost bleeds off.
	_phase_flutter = fmod(_phase_flutter + 15.0 * dt, 1.0)
	var flutter_gate: float = 1.0 if sin(TAU * _phase_flutter) > 0.0 else 0.25
	var release_raw := (_rng.randf() * 2.0 - 1.0) * _release_env * flutter_gate
	_release_lp += (release_raw - _release_lp) * 0.25
	_release_env = max(_release_env - 1.6 * dt, 0.0)

	# Exhaust pops: loud, low, bassy "bang" -- a body oscillator plus a sub
	# oscillator one octave down for real low-end weight, a brief broadband
	# "crack" at the onset, soft-saturated (tanh) for punch/loudness without
	# harsh digital clipping, and a brief ducking of every other layer so the
	# pop actually cuts through the mix instead of just summing into the
	# limiter with everything else still at full volume.
	_dsp_time += dt
	if _pending_pop_times.size() > 0 and _dsp_time >= _pending_pop_times[0]:
		_pending_pop_times.pop_front()
		_pop_env = 1.0
		_pop_crack_env = 1.0
		_pop_freq = _rng.randf_range(65.0, 110.0)
	_phase_pop = fmod(_phase_pop + _pop_freq * dt, 1.0)
	_phase_pop_sub = fmod(_phase_pop_sub + _pop_freq * 0.5 * dt, 1.0)
	var pop_body := sin(TAU * _phase_pop) * _pop_env
	var pop_sub := sin(TAU * _phase_pop_sub) * _pop_env
	var pop_crack := (_rng.randf() * 2.0 - 1.0) * _pop_crack_env
	_pop_env = max(_pop_env - 7.0 * dt, 0.0)  # ~140ms body decay -- more weight than before
	_pop_crack_env = max(_pop_crack_env - 40.0 * dt, 0.0)  # ~25ms crack decay
	var pop_raw: float = pop_body * 1.3 + pop_sub * 1.2 + pop_crack * 0.8
	var pop_sample: float = tanh(pop_raw * 1.6)

	var duck: float = 1.0 - _pop_env * 0.55
	var mixed: float = clamp((engine_sample + whine + _release_lp * 0.9) * duck + pop_sample, -1.0, 1.0)
	return Vector2(mixed, mixed)
