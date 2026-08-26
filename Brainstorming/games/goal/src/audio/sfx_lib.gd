class_name SfxLib
extends RefCounted
## Every sound in GOAL, synthesised from scratch into an AudioStreamWAV.
##
## There is no audio file in this repository and there never will be, so this
## file carries a small DSP toolkit (oscillators, filtered noise, envelopes, a
## one pole and a biquad filter, comb and allpass delays, a Schroeder reverb)
## and then builds each of the 25 ids of IDS out of it.
##
## Two design rules keep the bank from turning into twenty flavours of the same
## buzz:
##
## 1. Each sound is modelled on what physically makes it. A goalpost is a metal
##    tube, so post_ding is built from INHARMONIC partials with independent
##    decay rates (higher partials die first). A referee's whistle is two pipes
##    beating against each other, so it is two detuned tones plus a breath
##    layer, never a single sine. A crowd is thousands of voices, so the crowd
##    beds are noise shaped by vocal formants over a low rumble.
## 2. Everything is deterministic. Every generator seeds its own
##    RandomNumberGenerator, so a given id always produces the same bytes and
##    the cache is a pure memo.
##
## Engine traps this file is written around:
## - An AudioStreamWAV that stops on a non zero sample clicks. Every generator
##   ends with a fade out of at least 8 ms (see _finish).
## - A looping stream squats a voice forever, so exactly one id
##   (crowd_ambience) has a non zero loop_mode. Its loop is made seamless by
##   folding the tail back onto the head with an equal power crossfade, and the
##   whole body is then rotated so the loop point lands on a zero crossing.
##   The few milliseconds stored AFTER loop_end are never played back: they only
##   exist so the raw buffer still ends quietly.
## - Samples are written at 32766 peak, never 32767, so nothing sits exactly on
##   full scale.


const SAMPLE_RATE := 44100
## Peak the loudest sounds are normalised to. Kept under 1.0 so the mixer has
## headroom when three impacts land on the same frame.
const SAFE_PEAK := 0.86

## Every id below is a valid argument to stream().
const IDS: PackedStringArray = [
	"kick_soft", "kick_hard", "kick_curl", "miscue",
	"net_ripple", "post_ding", "bar_ding", "ball_bounce", "ball_roll",
	"glove_punch", "glove_catch", "keeper_grunt", "keeper_land",
	"whistle_short", "whistle_long",
	"crowd_ambience", "crowd_roar", "crowd_groan", "crowd_ooh", "crowd_clap",
	"ui_move", "ui_select", "ui_back", "charge_loop", "heartbeat",
]

# Biquad shapes, see _biquad.
const _BQ_LOW := 0
const _BQ_HIGH := 1
const _BQ_BAND := 2
const _BQ_NOTCH := 3

static var _cache: Dictionary = {}


## Returns the cached stream for an id, or null if the id is unknown.
static func stream(id: String) -> AudioStreamWAV:
	if _cache.has(id):
		return _cache[id] as AudioStreamWAV
	if not IDS.has(id):
		push_warning("SfxLib: unknown sound id '%s'" % id)
		return null
	var built: AudioStreamWAV = _build(id)
	if built == null:
		push_error("SfxLib: generator missing for id '%s'" % id)
		return null
	_cache[id] = built
	return built


## Frees every cached stream. Only the tests call this.
static func clear_cache() -> void:
	_cache.clear()


static func _build(id: String) -> AudioStreamWAV:
	match id:
		"kick_soft":
			return _make_kick_soft()
		"kick_hard":
			return _make_kick_hard()
		"kick_curl":
			return _make_kick_curl()
		"miscue":
			return _make_miscue()
		"net_ripple":
			return _make_net_ripple()
		"post_ding":
			return _make_metal(620.0, 1.35, 0.80)
		"bar_ding":
			return _make_metal(432.0, 1.75, 1.00)
		"ball_bounce":
			return _make_ball_bounce()
		"ball_roll":
			return _make_ball_roll()
		"glove_punch":
			return _make_glove_punch()
		"glove_catch":
			return _make_glove_catch()
		"keeper_grunt":
			return _make_keeper_grunt()
		"keeper_land":
			return _make_keeper_land()
		"whistle_short":
			return _make_whistle(0.44, false)
		"whistle_long":
			return _make_whistle(1.30, true)
		"crowd_ambience":
			return _make_crowd_ambience()
		"crowd_roar":
			return _make_crowd_roar()
		"crowd_groan":
			return _make_crowd_groan()
		"crowd_ooh":
			return _make_crowd_ooh()
		"crowd_clap":
			return _make_crowd_clap()
		"ui_move":
			return _make_ui_move()
		"ui_select":
			return _make_ui_select()
		"ui_back":
			return _make_ui_back()
		"charge_loop":
			return _make_charge()
		"heartbeat":
			return _make_heartbeat()
	return null


# ---------------------------------------------------------------------------
# Impacts on the ball
# ---------------------------------------------------------------------------

## A boot on a football is two events at once: a very short broadband transient
## (leather crushing against leather) riding on a fast decaying low body (the
## bladder resonating). Everything else is a variation on the balance between
## the two.
static func _strike_body(n: int, f_start: float, f_end: float, tau: float, amp: float) -> PackedFloat32Array:
	var body := _sweep(n, f_start, f_end, 0.05)
	_apply(body, _env_ad(n, 0.0015, tau))
	_gain(body, amp)
	return body


static func _make_kick_soft() -> AudioStreamWAV:
	var rng := _rng(11)
	var n := _frames(0.32)
	var out := _strike_body(n, 158.0, 62.0, 0.085, 0.9)

	var click := _noise(n, rng)
	_biquad(click, _BQ_BAND, 2400.0, 0.9)
	_apply(click, _env_ad(n, 0.0004, 0.0045))
	_mix(out, click, 0.55)

	var thud := _noise(n, rng)
	_lp1(thud, 700.0)
	_apply(thud, _env_ad(n, 0.001, 0.030))
	_mix(out, thud, 0.40)

	_soft_clip(out, 1.3)
	return _finish(out, 0.70, 0.016)


static func _make_kick_hard() -> AudioStreamWAV:
	# Louder, brighter and shorter than the placed shot: the contact time is
	# smaller, so the transient carries more of the energy and the body dies
	# faster.
	var rng := _rng(12)
	var n := _frames(0.27)
	var out := _strike_body(n, 205.0, 70.0, 0.058, 0.95)

	var crack := _noise(n, rng)
	_biquad(crack, _BQ_BAND, 4200.0, 0.7)
	_apply(crack, _env_ad(n, 0.0002, 0.0032))
	_mix(out, crack, 0.85)

	var snap := _noise(n, rng)
	_biquad(snap, _BQ_BAND, 1250.0, 1.1)
	_apply(snap, _env_ad(n, 0.0006, 0.014))
	_mix(out, snap, 0.5)

	_soft_clip(out, 1.8)
	return _finish(out, SAFE_PEAK, 0.014)


static func _make_kick_curl() -> AudioStreamWAV:
	# The instep wraps around the ball instead of going through it, so the
	# contact lasts longer and it scuffs: a grainy brushed layer over a duller
	# body.
	var rng := _rng(13)
	var n := _frames(0.36)
	var out := _strike_body(n, 146.0, 58.0, 0.105, 0.85)

	var scuff := _noise(n, rng)
	_band_sweep(scuff, 3100.0, 1200.0, 1.3)
	_tremolo(scuff, 96.0, 0.55, 0.0)
	_apply(scuff, _env_ad(n, 0.004, 0.055))
	_mix(out, scuff, 0.62)

	var brush := _noise(n, rng)
	_hp1(brush, 3500.0)
	_apply(brush, _env_ad(n, 0.008, 0.075))
	_mix(out, brush, 0.30)

	_soft_clip(out, 1.2)
	return _finish(out, 0.74, 0.018)


static func _make_miscue() -> AudioStreamWAV:
	# Bad contact: the ball leaves off the outside of the boot. Detuned, dull,
	# and noticeably weaker than a clean strike.
	var rng := _rng(14)
	var n := _frames(0.31)
	var out := _strike_body(n, 96.0, 54.0, 0.075, 0.8)
	var beat := _strike_body(n, 89.0, 51.0, 0.090, 0.6)
	_mix(out, beat, 1.0)

	var toc := _sine(n, 238.0, 0.0)
	_apply(toc, _env_ad(n, 0.0008, 0.020))
	_mix(out, toc, 0.35)

	var dust := _noise(n, rng)
	_lp1(dust, 850.0)
	_apply(dust, _env_ad(n, 0.002, 0.012))
	_mix(out, dust, 0.45)

	_lp1(out, 1400.0)
	return _finish(out, 0.58, 0.018)


static func _make_ball_bounce() -> AudioStreamWAV:
	var rng := _rng(15)
	var n := _frames(0.24)
	var out := _strike_body(n, 92.0, 58.0, 0.050, 0.9)

	var slap := _noise(n, rng)
	_lp1(slap, 1600.0)
	_apply(slap, _env_ad(n, 0.0008, 0.011))
	_mix(out, slap, 0.55)

	# The pressurised bladder rings briefly: a short comb gives it a pitch
	# without adding a tone that would sound synthetic.
	_comb(out, 1.0 / 300.0, 0.42)
	return _finish(out, 0.62, 0.016)


static func _make_ball_roll() -> AudioStreamWAV:
	# Grass under a rolling ball: low band limited noise, rustling, slowly
	# darkening as the ball loses speed.
	var rng := _rng(16)
	var n := _frames(0.95)
	var out := _noise(n, rng)
	_biquad(out, _BQ_BAND, 240.0, 0.8)
	_lp1_sweep(out, 900.0, 320.0)

	# The rustle layer is band limited on BOTH sides. A plain high pass leaves
	# the top octave at full level, and since a two pole band pass only rolls
	# off at 6 dB per octave the thin hiss then dominates the low roll it is
	# supposed to sit under.
	var rustle := _noise(n, rng)
	_biquad(rustle, _BQ_BAND, 2600.0, 1.1)
	_apply(rustle, _wobble(n, rng, 14.0, 0.9))
	_mix(out, rustle, 0.10)

	_lp1(out, 2600.0)
	_apply(out, _wobble(n, rng, 9.0, 0.35))
	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.06, 1.0), Vector2(0.55, 0.72),
		Vector2(0.95, 0.0),
	])))
	return _finish(out, 0.46, 0.040)


# ---------------------------------------------------------------------------
# The goal itself
# ---------------------------------------------------------------------------

static func _make_net_ripple() -> AudioStreamWAV:
	# This one plays on every goal, so it gets the most care. A ball entering a
	# net is a broadband burst (the mesh accelerating) that immediately turns
	# into a soft, faintly pitched rustle as the cords slap each other. The
	# pitch comes from two combs tuned to the cord spacing, not from an
	# oscillator: an oscillator here sounds like a doorbell.
	var rng := _rng(21)
	var n := _frames(0.95)
	var out := _noise(n, rng)
	_biquad(out, _BQ_BAND, 1750.0, 0.75)

	var low := _noise(n, rng)
	_biquad(low, _BQ_BAND, 640.0, 0.9)
	_mix(out, low, 0.85)

	_comb(out, 1.0 / 218.0, 0.55)
	_comb(out, 1.0 / 331.0, 0.38)
	_lp1_sweep(out, 5200.0, 900.0)

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.006, 1.0), Vector2(0.11, 0.34),
		Vector2(0.42, 0.13), Vector2(0.95, 0.0),
	])))
	_apply(out, _wobble(n, rng, 22.0, 0.28))
	_reverb(out, 0.75, 0.55, 0.22)
	return _finish(out, 0.80, 0.030)


## Post and bar share one generator because they are the same object at two
## lengths. What makes them read as metal rather than as a bell is that the
## partials are NOT integer multiples of the fundamental: a free bar rings at
## roughly 1, 2.76, 5.40, 8.93 and 13.34 times its first mode, and the higher
## modes bleed off much faster than the lower ones.
static func _make_metal(f0: float, seconds: float, weight: float) -> AudioStreamWAV:
	var rng := _rng(int(f0))
	var n := _frames(seconds)
	var out := _silence(n)

	var ratios := PackedFloat32Array([1.0, 2.756, 5.404, 8.933, 13.344, 19.12])
	var amps := PackedFloat32Array([1.0, 0.58, 0.36, 0.22, 0.13, 0.07])
	var taus := PackedFloat32Array([0.42, 0.24, 0.15, 0.085, 0.05, 0.03])
	for k in ratios.size():
		var freq := f0 * ratios[k] * (1.0 + rng.randf_range(-0.004, 0.004))
		if freq > float(SAMPLE_RATE) * 0.45:
			continue
		var partial := _sine(n, freq, rng.randf_range(0.0, TAU))
		_apply(partial, _env_ad(n, 0.0008, taus[k] * seconds))
		_mix(out, partial, amps[k])

	# A real tube is never perfectly round, so its fundamental splits into two
	# modes a fraction of a hertz apart. That beating is most of what tells the
	# ear "aluminium".
	var twin := _sine(n, f0 * 1.006, 1.1)
	_apply(twin, _env_ad(n, 0.001, 0.40 * seconds))
	_mix(out, twin, 0.45)

	# Low body: the impact travelling through the post into the ground.
	var clonk := _sweep(n, 150.0 * weight, 92.0 * weight, 0.04)
	_apply(clonk, _env_ad(n, 0.0008, 0.045))
	_mix(out, clonk, 0.55 * weight)

	var strike := _noise(n, rng)
	_biquad(strike, _BQ_BAND, 5600.0, 0.6)
	_apply(strike, _env_ad(n, 0.0002, 0.0035))
	_mix(out, strike, 0.70)

	_reverb(out, 1.0, 0.45, 0.16)
	return _finish(out, SAFE_PEAK, 0.025)


# ---------------------------------------------------------------------------
# The keeper
# ---------------------------------------------------------------------------

static func _make_glove_punch() -> AudioStreamWAV:
	# Latex driven into a ball at speed: a hard slap, a leather crack, and a
	# short low body from the hand behind it.
	var rng := _rng(31)
	var n := _frames(0.30)
	var out := _noise(n, rng)
	_biquad(out, _BQ_BAND, 1650.0, 0.8)
	_apply(out, _env_ad(n, 0.0004, 0.013))

	var crack := _noise(n, rng)
	_hp1(crack, 4200.0)
	_apply(crack, _env_ad(n, 0.0002, 0.0035))
	_mix(out, crack, 0.65)

	var body := _strike_body(n, 128.0, 74.0, 0.045, 0.8)
	_mix(out, body, 0.9)

	_soft_clip(out, 1.4)
	return _finish(out, 0.82, 0.016)


static func _make_glove_catch() -> AudioStreamWAV:
	# Same impact, absorbed instead of returned: duller, with the small squeak
	# of latex being gripped shut.
	var rng := _rng(32)
	var n := _frames(0.32)
	var out := _noise(n, rng)
	_lp1(out, 950.0)
	_apply(out, _env_ad(n, 0.004, 0.055))

	var thud := _strike_body(n, 105.0, 66.0, 0.055, 0.75)
	_mix(out, thud, 0.85)

	var squeak := _sine_vib(n, 1320.0, 26.0, 55.0, 0.4)
	_apply(squeak, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.03, 0.55), Vector2(0.13, 0.2),
		Vector2(0.26, 0.0),
	])))
	_mix(out, squeak, 0.22)

	_lp1(out, 3200.0)
	return _finish(out, 0.60, 0.020)


static func _make_keeper_grunt() -> AudioStreamWAV:
	# A voiced effort: a falling glottal pulse train pushed through two vowel
	# formants, plus the breath that escapes with it.
	var rng := _rng(33)
	var n := _frames(0.46)
	var glottis := _harmonic_sweep(n, 132.0, 98.0, 14, 1.05)

	var out := _band(glottis, 700.0, 2.4, 1.0)
	_mix(out, _band(glottis, 1180.0, 3.2, 0.55), 1.0)
	_mix(out, _band(glottis, 2550.0, 4.5, 0.20), 1.0)
	# A narrow band pass only lets one harmonic of the pulse train through, so
	# the voiced part comes out of the formant bank an order of magnitude below
	# the breath. Level it here, before the breath is mixed in, or the grunt is
	# nothing but hiss.
	_normalize(out, 1.0)

	var breath := _noise(n, rng)
	_biquad(breath, _BQ_BAND, 1900.0, 0.7)
	_apply(breath, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.4), Vector2(0.05, 1.0), Vector2(0.30, 0.35),
		Vector2(0.46, 0.0),
	])))
	_mix(out, breath, 0.22)
	_lp1(out, 3600.0)

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.025, 1.0), Vector2(0.16, 0.75),
		Vector2(0.33, 0.20), Vector2(0.46, 0.0),
	])))
	_apply(out, _wobble(n, rng, 18.0, 0.14))
	_soft_clip(out, 1.2)
	return _finish(out, 0.66, 0.030)


static func _make_keeper_land() -> AudioStreamWAV:
	# Hip and shoulder hitting wet turf, then the grass sliding under the body.
	var rng := _rng(34)
	var n := _frames(0.52)
	var out := _strike_body(n, 78.0, 44.0, 0.075, 1.0)

	var whump := _noise(n, rng)
	_lp1(whump, 520.0)
	_apply(whump, _env_ad(n, 0.002, 0.048))
	_mix(out, whump, 0.75)

	var slide := _noise(n, rng)
	_hp1(slide, 2400.0)
	_lp1(slide, 6000.0)
	_apply(slide, _wobble(n, rng, 26.0, 0.8))
	_apply(slide, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.02, 0.9), Vector2(0.18, 0.45),
		Vector2(0.45, 0.0),
	])))
	_mix(out, slide, 0.26)

	_soft_clip(out, 1.3)
	return _finish(out, 0.78, 0.028)


# ---------------------------------------------------------------------------
# The referee
# ---------------------------------------------------------------------------

## A pea whistle is two pipes slightly out of tune plus a rattling ball, and it
## sounds completely wrong built from a single oscillator: the beating between
## the two pipes IS the sound. The pea adds a fast amplitude warble, and a
## breath layer sits under everything.
static func _make_whistle(seconds: float, long_blast: bool) -> AudioStreamWAV:
	var rng := _rng(41 if long_blast else 42)
	var n := _frames(seconds)
	var attack := 0.022
	var release := 0.075 if long_blast else 0.055

	var vib := 16.0 if long_blast else 21.0
	var a := _sine_vib(n, 3160.0, vib, 26.0, 0.0)
	var b := _sine_vib(n, 3129.0, vib * 0.87, 20.0, 1.7)
	var out := a
	_mix(out, b, 0.85)

	# Second register, quiet, keeps the tone from sounding like a test signal.
	var upper := _sine_vib(n, 6290.0, vib, 30.0, 0.6)
	_mix(out, upper, 0.16)

	var air := _noise(n, rng)
	_biquad(air, _BQ_BAND, 3200.0, 0.35)
	_mix(out, air, 0.22)

	var hiss := _noise(n, rng)
	_hp1(hiss, 5200.0)
	_lp1(hiss, 9000.0)
	_mix(out, hiss, 0.07)

	# The pea rattling inside the chamber.
	_tremolo(out, 34.0 if long_blast else 30.0, 0.30, 0.0)

	var env := _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(attack, 1.0),
		Vector2(seconds - release, 0.92), Vector2(seconds, 0.0),
	]))
	_apply(out, env)
	_reverb(out, 1.2, 0.5, 0.18)
	return _finish(out, 0.72, 0.020)


# ---------------------------------------------------------------------------
# The crowd
# ---------------------------------------------------------------------------

## A crowd bed: noise pushed through three vowel formants over a low rumble.
## Thousands of voices average out into coloured noise, which is exactly what
## this is, and the formants are what stop it sounding like rain.
static func _voice_bed(n: int, rng: RandomNumberGenerator, f1: float, f2: float, f3: float) -> PackedFloat32Array:
	var src := _noise(n, rng)
	_lp1(src, 5200.0)

	var out := _band(src, f1, 2.0, 1.0)
	_mix(out, _band(src, f2, 3.0, 0.60), 1.0)
	_mix(out, _band(src, f3, 4.2, 0.26), 1.0)

	var rumble := src.duplicate()
	_lp1(rumble, 170.0)
	_mix(out, rumble, 0.55)
	return out


static func _make_crowd_ambience() -> AudioStreamWAV:
	# The only looping id in the game. Built one crossfade longer than the loop
	# itself, then folded back onto its own head so the seam is inaudible, then
	# rotated so loop_begin sits on a zero crossing.
	var rng := _rng(51)
	var loop_frames := _frames(6.0)
	var fade_frames := _frames(0.60)
	var n := loop_frames + fade_frames

	var out := _voice_bed(n, rng, 480.0, 1150.0, 2500.0)
	_lp1(out, 1500.0)

	# Chatter sizzle, kept narrow and quiet: a wide band pass here passes so
	# much bandwidth that it out shouts the whole bed it is meant to garnish.
	var sizzle := _noise(n, rng)
	_biquad(sizzle, _BQ_BAND, 3200.0, 1.4)
	_mix(out, sizzle, 0.05)

	# The slow swell of a stadium between two shots. Every component is an
	# exact harmonic of the loop length, so the modulation itself is periodic
	# and the crossfade only has to hide the noise, not the shape.
	var period := float(loop_frames) / float(SAMPLE_RATE)
	var mod := _silence(n)
	var partials := PackedFloat32Array([1.0, 2.0, 3.0, 5.0, 8.0])
	var depths := PackedFloat32Array([0.16, 0.10, 0.07, 0.05, 0.03])
	for k in partials.size():
		var freq := partials[k] / period
		var wave := _sine(n, freq, rng.randf_range(0.0, TAU))
		_mix(mod, wave, depths[k])
	for i in n:
		out[i] = out[i] * (1.0 + mod[i])

	var body := _crossfade_loop(out, fade_frames)
	body = _rotate_to_zero(body)
	_normalize(body, 0.62)

	# A short tail past loop_end: never played, it just keeps the raw buffer
	# from ending on a live sample.
	var tail_frames := _frames(0.03)
	var full := body.duplicate()
	full.resize(body.size() + tail_frames)
	for i in tail_frames:
		var w := 1.0 - float(i) / float(tail_frames)
		full[body.size() + i] = body[i % body.size()] * w * w

	return _to_stream(full, AudioStreamWAV.LOOP_FORWARD, 0, body.size())


static func _make_crowd_roar() -> AudioStreamWAV:
	# A goal: the sound swells rather than starts, because a crowd needs a
	# quarter of a second to realise what it saw.
	var rng := _rng(52)
	var n := _frames(2.70)
	var out := _voice_bed(n, rng, 760.0, 1250.0, 2700.0)
	_band_sweep(out, 900.0, 1600.0, 0.7)

	var shout := _noise(n, rng)
	_biquad(shout, _BQ_BAND, 2100.0, 1.0)
	_mix(out, shout, 0.16)
	_lp1(out, 4200.0)

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.05), Vector2(0.10, 0.35), Vector2(0.30, 1.0),
		Vector2(0.85, 0.86), Vector2(1.80, 0.45), Vector2(2.70, 0.0),
	])))
	_apply(out, _wobble(n, rng, 3.5, 0.22))
	_reverb(out, 1.6, 0.7, 0.30)
	_soft_clip(out, 1.15)
	return _finish(out, 0.84, 0.060)


static func _make_crowd_groan() -> AudioStreamWAV:
	# A miss: it arrives immediately and falls away, formants sliding down.
	var rng := _rng(53)
	var n := _frames(2.10)
	var out := _voice_bed(n, rng, 560.0, 980.0, 2200.0)
	_band_sweep(out, 1450.0, 420.0, 0.9)
	_lp1_sweep(out, 2200.0, 620.0)

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.10), Vector2(0.14, 1.0), Vector2(0.70, 0.62),
		Vector2(1.40, 0.26), Vector2(2.10, 0.0),
	])))
	_apply(out, _wobble(n, rng, 2.8, 0.18))
	_reverb(out, 1.5, 0.6, 0.26)
	return _finish(out, 0.74, 0.060)


static func _make_crowd_ooh() -> AudioStreamWAV:
	# A near miss: a short rise, then the crowd cuts itself off when it sees
	# the ball was never going in.
	var rng := _rng(54)
	var n := _frames(1.15)
	var out := _voice_bed(n, rng, 330.0, 880.0, 2400.0)
	_band_sweep(out, 520.0, 1350.0, 1.0)

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.34, 1.0), Vector2(0.68, 0.90),
		Vector2(0.80, 0.22), Vector2(1.15, 0.0),
	])))
	_reverb(out, 1.3, 0.5, 0.22)
	return _finish(out, 0.70, 0.040)


static func _make_crowd_clap() -> AudioStreamWAV:
	# Applause is not a texture, it is a few hundred discrete impacts. Building
	# it that way costs nothing and sounds like nothing else.
	var rng := _rng(55)
	var n := _frames(2.45)
	var out := _silence(n)
	var claps := 260
	var span := 2.05

	for c in claps:
		var t: float = pow(rng.randf(), 0.72) * span
		var start := int(t * float(SAMPLE_RATE))
		var burst_frames := _frames(rng.randf_range(0.005, 0.013))
		var burst := _noise(burst_frames, rng)
		_biquad(burst, _BQ_BAND, rng.randf_range(1150.0, 2450.0), 1.4)
		_hp1(burst, 700.0)
		_apply(burst, _env_ad(burst_frames, 0.0003, rng.randf_range(0.0018, 0.005)))
		_add_at(out, burst, start, rng.randf_range(0.35, 1.0))

	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.35), Vector2(0.25, 1.0), Vector2(1.30, 0.85),
		Vector2(1.95, 0.35), Vector2(2.45, 0.0),
	])))
	_reverb(out, 1.4, 0.6, 0.28)
	return _finish(out, 0.76, 0.050)


# ---------------------------------------------------------------------------
# Interface and tension
# ---------------------------------------------------------------------------

static func _make_ui_move() -> AudioStreamWAV:
	var n := _frames(0.09)
	var out := _sine(n, 880.0, 0.0)
	_mix(out, _sine(n, 1760.0, 0.0), 0.22)
	_apply(out, _env_ad(n, 0.0008, 0.018))
	return _finish(out, 0.34, 0.010)


static func _make_ui_select() -> AudioStreamWAV:
	# Two steps up: the ear reads a rising interval as confirmation.
	var n := _frames(0.18)
	var out := _silence(n)
	var step := _frames(0.055)

	var low := _sine(step, 659.0, 0.0)
	_mix(low, _sine(step, 1318.0, 0.0), 0.25)
	_apply(low, _env_ad(step, 0.0008, 0.030))
	_add_at(out, low, 0, 1.0)

	var rest := n - step
	var high := _sine(rest, 988.0, 0.0)
	_mix(high, _sine(rest, 1976.0, 0.0), 0.25)
	_apply(high, _env_ad(rest, 0.0008, 0.045))
	_add_at(out, high, step, 1.0)

	return _finish(out, 0.46, 0.012)


static func _make_ui_back() -> AudioStreamWAV:
	var n := _frames(0.16)
	var out := _sweep(n, 620.0, 392.0, 0.6)
	_mix(out, _sweep(n, 1240.0, 784.0, 0.6), 0.20)
	_apply(out, _env_ad(n, 0.0010, 0.040))
	_lp1(out, 4000.0)
	return _finish(out, 0.40, 0.012)


static func _make_charge() -> AudioStreamWAV:
	# Played once when the power bar starts filling, not looped: a looping
	# stream would squat a voice, and the ramp already covers the longest
	# possible charge.
	var rng := _rng(61)
	var n := _frames(1.45)
	var out := _harmonic_sweep(n, 88.0, 268.0, 8, 1.15)
	_band_sweep(out, 620.0, 3100.0, 2.6)
	_lp1_sweep(out, 1400.0, 5200.0)

	var air := _noise(n, rng)
	_biquad(air, _BQ_BAND, 2600.0, 0.6)
	_apply(air, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(1.45, 0.5),
	])))
	_mix(out, air, 0.12)

	_tremolo_sweep(out, 5.0, 17.0, 0.22)
	_apply(out, _env_shape(n, PackedVector2Array([
		Vector2(0.0, 0.0), Vector2(0.06, 0.30), Vector2(1.20, 1.0),
		Vector2(1.45, 0.85),
	])))
	_soft_clip(out, 1.2)
	return _finish(out, 0.58, 0.030)


static func _make_heartbeat() -> AudioStreamWAV:
	# The held breath before a decisive penalty. Two thumps, the second softer
	# and lower, with a touch of second harmonic so it survives a laptop
	# speaker that cannot reproduce 45 Hz at all.
	var n := _frames(1.25)
	var out := _silence(n)
	_add_at(out, _thump(0.0), 0, 1.0)
	_add_at(out, _thump(-0.06), int(0.335 * float(SAMPLE_RATE)), 0.72)
	_lp1(out, 420.0)
	return _finish(out, 0.66, 0.045)


static func _thump(detune: float) -> PackedFloat32Array:
	var n := _frames(0.30)
	var scale := 1.0 + detune
	var out := _sweep(n, 78.0 * scale, 42.0 * scale, 0.045)
	_mix(out, _sweep(n, 156.0 * scale, 84.0 * scale, 0.045), 0.30)
	_apply(out, _env_ad(n, 0.006, 0.075))
	return out


# ---------------------------------------------------------------------------
# Synthesis toolkit
# ---------------------------------------------------------------------------

static func _rng(seed_value: int) -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = 9176411 + seed_value * 7919
	return rng


static func _frames(seconds: float) -> int:
	return maxi(2, int(round(seconds * float(SAMPLE_RATE))))


static func _silence(n: int) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	buf.fill(0.0)
	return buf


static func _noise(n: int, rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	for i in n:
		buf[i] = rng.randf_range(-1.0, 1.0)
	return buf


static func _sine(n: int, freq: float, phase: float) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	var step := TAU * freq / float(SAMPLE_RATE)
	var p := phase
	for i in n:
		buf[i] = sin(p)
		p += step
	return buf


## A sine with vibrato, in cents so the depth stays musical whatever the pitch.
static func _sine_vib(n: int, freq: float, vib_hz: float, vib_cents: float, phase: float) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	var p := phase
	var vp := 0.0
	var vstep := TAU * vib_hz / float(SAMPLE_RATE)
	var ratio := vib_cents / 1200.0
	for i in n:
		var f: float = freq * pow(2.0, ratio * sin(vp))
		p += TAU * f / float(SAMPLE_RATE)
		vp += vstep
		buf[i] = sin(p)
	return buf


## Exponential pitch sweep from f0 to f1 over `tau` seconds, then holding f1.
## Percussive bodies glide down fast and then sit, which is what a real drum
## head does as its tension drops back.
static func _sweep(n: int, f0: float, f1: float, tau: float) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	var p := 0.0
	var inv := 1.0 / float(SAMPLE_RATE)
	var safe_tau := maxf(tau, 0.0005)
	for i in n:
		var t := float(i) * inv
		var k: float = exp(-t / safe_tau)
		var f: float = f1 + (f0 - f1) * k
		p += TAU * f * inv
		buf[i] = sin(p)
	return buf


## A stack of harmonics over a sweeping fundamental, band limited by hand:
## partials above Nyquist are simply skipped, which is cheaper and cleaner than
## letting them fold back as aliasing.
static func _harmonic_sweep(n: int, f0: float, f1: float, partials: int, tilt: float) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	var phase := 0.0
	var inv := 1.0 / float(SAMPLE_RATE)
	var limit := float(SAMPLE_RATE) * 0.45
	var norm := 0.0
	for k in range(1, partials + 1):
		norm += 1.0 / pow(float(k), tilt)
	if norm <= 0.0:
		norm = 1.0
	for i in n:
		var u := float(i) / float(n - 1)
		var f: float = f0 * pow(f1 / maxf(f0, 0.001), u)
		phase += TAU * f * inv
		var acc := 0.0
		for k in range(1, partials + 1):
			if f * float(k) > limit:
				break
			acc += sin(phase * float(k)) / pow(float(k), tilt)
		buf[i] = acc / norm
	return buf


## Slow random modulation in [1 - depth, 1 + depth]. Smoothed noise, not a sine:
## a sine reads as a tremolo effect, smoothed noise reads as a living surface.
static func _wobble(n: int, rng: RandomNumberGenerator, hz: float, depth: float) -> PackedFloat32Array:
	var buf := _noise(n, rng)
	_lp1(buf, hz)
	var peak := _peak(buf)
	if peak > 0.00001:
		_gain(buf, 1.0 / peak)
	for i in n:
		buf[i] = 1.0 + depth * buf[i]
	return buf


static func _env_ad(n: int, attack: float, tau: float) -> PackedFloat32Array:
	var env := PackedFloat32Array()
	env.resize(n)
	var inv := 1.0 / float(SAMPLE_RATE)
	var safe_attack := maxf(attack, inv)
	var safe_tau := maxf(tau, 0.0002)
	for i in n:
		var t := float(i) * inv
		var rise: float = minf(t / safe_attack, 1.0)
		env[i] = rise * exp(-maxf(t - safe_attack, 0.0) / safe_tau)
	return env


## Piecewise linear envelope from (time in seconds, level) breakpoints.
static func _env_shape(n: int, breaks: PackedVector2Array) -> PackedFloat32Array:
	var env := PackedFloat32Array()
	env.resize(n)
	if breaks.is_empty():
		env.fill(1.0)
		return env
	var last := breaks.size() - 1
	var k := 0
	var inv := 1.0 / float(SAMPLE_RATE)
	for i in n:
		var t := float(i) * inv
		while k < last and t > breaks[k + 1].x:
			k += 1
		if k >= last:
			env[i] = breaks[last].y
			continue
		var a := breaks[k]
		var b := breaks[k + 1]
		var span := maxf(b.x - a.x, 0.000001)
		env[i] = lerpf(a.y, b.y, clampf((t - a.x) / span, 0.0, 1.0))
	return env


static func _apply(buf: PackedFloat32Array, env: PackedFloat32Array) -> void:
	var n := mini(buf.size(), env.size())
	for i in n:
		buf[i] = buf[i] * env[i]


static func _mix(dst: PackedFloat32Array, src: PackedFloat32Array, gain: float) -> void:
	var n := mini(dst.size(), src.size())
	for i in n:
		dst[i] = dst[i] + src[i] * gain


## Adds `src` into `dst` starting at a frame offset, clipped to the buffer.
static func _add_at(dst: PackedFloat32Array, src: PackedFloat32Array, start: int, gain: float) -> void:
	if start >= dst.size():
		return
	var count := mini(src.size(), dst.size() - start)
	for i in count:
		dst[start + i] = dst[start + i] + src[i] * gain


static func _gain(buf: PackedFloat32Array, g: float) -> void:
	for i in buf.size():
		buf[i] = buf[i] * g


static func _tremolo(buf: PackedFloat32Array, hz: float, depth: float, phase: float) -> void:
	var step := TAU * hz / float(SAMPLE_RATE)
	var p := phase
	for i in buf.size():
		buf[i] = buf[i] * (1.0 - depth * 0.5 * (1.0 - cos(p)))
		p += step


static func _tremolo_sweep(buf: PackedFloat32Array, hz0: float, hz1: float, depth: float) -> void:
	var n := buf.size()
	var p := 0.0
	var inv := 1.0 / float(SAMPLE_RATE)
	for i in n:
		var u := float(i) / float(maxi(n - 1, 1))
		var hz: float = lerpf(hz0, hz1, u)
		buf[i] = buf[i] * (1.0 - depth * 0.5 * (1.0 - cos(p)))
		p += TAU * hz * inv


static func _peak(buf: PackedFloat32Array) -> float:
	var top := 0.0
	for i in buf.size():
		top = maxf(top, absf(buf[i]))
	return top


static func _normalize(buf: PackedFloat32Array, target: float) -> void:
	var top := _peak(buf)
	if top < 0.000001:
		return
	_gain(buf, target / top)


## Odd order polynomial saturation. Tames the peaks of a summed impact without
## the metallic edge of a hard clip.
static func _soft_clip(buf: PackedFloat32Array, drive: float) -> void:
	for i in buf.size():
		var x: float = clampf(buf[i] * drive, -1.5, 1.5)
		buf[i] = x - (x * x * x) / 6.0


static func _fade_in(buf: PackedFloat32Array, seconds: float) -> void:
	var count := mini(int(seconds * float(SAMPLE_RATE)), buf.size())
	for i in count:
		buf[i] = buf[i] * (float(i) / float(count))


static func _fade_out(buf: PackedFloat32Array, seconds: float) -> void:
	var n := buf.size()
	var count := mini(int(seconds * float(SAMPLE_RATE)), n)
	if count <= 1:
		return
	for i in count:
		var w := float(count - i) / float(count)
		buf[n - count + i] = buf[n - count + i] * w * w


# --- filters ---------------------------------------------------------------

static func _lp1(buf: PackedFloat32Array, cutoff: float) -> void:
	var alpha: float = 1.0 - exp(-TAU * maxf(cutoff, 1.0) / float(SAMPLE_RATE))
	alpha = clampf(alpha, 0.0, 1.0)
	var y := 0.0
	for i in buf.size():
		y += alpha * (buf[i] - y)
		buf[i] = y


static func _hp1(buf: PackedFloat32Array, cutoff: float) -> void:
	var alpha: float = 1.0 - exp(-TAU * maxf(cutoff, 1.0) / float(SAMPLE_RATE))
	alpha = clampf(alpha, 0.0, 1.0)
	var y := 0.0
	for i in buf.size():
		y += alpha * (buf[i] - y)
		buf[i] = buf[i] - y


## One pole low pass whose cutoff glides exponentially across the buffer. Used
## everywhere something should get darker as it dies away, which is what real
## decaying sounds do: high frequencies are absorbed first.
static func _lp1_sweep(buf: PackedFloat32Array, c0: float, c1: float) -> void:
	var n := buf.size()
	var y := 0.0
	var a := maxf(c0, 1.0)
	var b := maxf(c1, 1.0)
	for i in n:
		var u := float(i) / float(maxi(n - 1, 1))
		var cutoff: float = a * pow(b / a, u)
		var alpha: float = clampf(1.0 - exp(-TAU * cutoff / float(SAMPLE_RATE)), 0.0, 1.0)
		y += alpha * (buf[i] - y)
		buf[i] = y


## RBJ cookbook biquad, direct form I.
static func _biquad(buf: PackedFloat32Array, mode: int, freq: float, q: float) -> void:
	var f: float = clampf(freq, 10.0, float(SAMPLE_RATE) * 0.45)
	var qq: float = maxf(q, 0.05)
	var w0 := TAU * f / float(SAMPLE_RATE)
	var cw := cos(w0)
	var sw := sin(w0)
	var alpha := sw / (2.0 * qq)

	var b0 := 0.0
	var b1 := 0.0
	var b2 := 0.0
	var a0 := 1.0 + alpha
	var a1 := -2.0 * cw
	var a2 := 1.0 - alpha

	match mode:
		_BQ_LOW:
			b0 = (1.0 - cw) * 0.5
			b1 = 1.0 - cw
			b2 = b0
		_BQ_HIGH:
			b0 = (1.0 + cw) * 0.5
			b1 = -(1.0 + cw)
			b2 = b0
		_BQ_BAND:
			b0 = alpha
			b1 = 0.0
			b2 = -alpha
		_BQ_NOTCH:
			b0 = 1.0
			b1 = -2.0 * cw
			b2 = 1.0

	b0 /= a0
	b1 /= a0
	b2 /= a0
	a1 /= a0
	a2 /= a0

	var x1 := 0.0
	var x2 := 0.0
	var y1 := 0.0
	var y2 := 0.0
	for i in buf.size():
		var x := buf[i]
		var y := b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
		x2 = x1
		x1 = x
		y2 = y1
		y1 = y
		buf[i] = y


## Band pass whose centre frequency glides. Coefficients are refreshed every 32
## frames: often enough that the sweep is smooth, rarely enough that the cost of
## the trigonometry stays negligible.
static func _band_sweep(buf: PackedFloat32Array, f0: float, f1: float, q: float) -> void:
	var n := buf.size()
	var qq: float = maxf(q, 0.05)
	var a := clampf(f0, 10.0, float(SAMPLE_RATE) * 0.45)
	var b := clampf(f1, 10.0, float(SAMPLE_RATE) * 0.45)

	var b0 := 0.0
	var b1 := 0.0
	var b2 := 0.0
	var a1 := 0.0
	var a2 := 0.0
	var x1 := 0.0
	var x2 := 0.0
	var y1 := 0.0
	var y2 := 0.0

	for i in n:
		if i % 32 == 0:
			var u := float(i) / float(maxi(n - 1, 1))
			var f: float = a * pow(b / a, u)
			var w0 := TAU * f / float(SAMPLE_RATE)
			var cw := cos(w0)
			var alpha := sin(w0) / (2.0 * qq)
			var norm := 1.0 + alpha
			b0 = alpha / norm
			b1 = 0.0
			b2 = -alpha / norm
			a1 = (-2.0 * cw) / norm
			a2 = (1.0 - alpha) / norm
		var x := buf[i]
		var y := b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
		x2 = x1
		x1 = x
		y2 = y1
		y1 = y
		buf[i] = y


static func _band(src: PackedFloat32Array, freq: float, q: float, gain: float) -> PackedFloat32Array:
	var out := src.duplicate()
	_biquad(out, _BQ_BAND, freq, q)
	_gain(out, gain)
	return out


## Feedback comb. Its resonance sits at 1 / delay, which is how the net and the
## ball get a pitch without an oscillator anywhere near them.
static func _comb(buf: PackedFloat32Array, delay_seconds: float, feedback: float) -> void:
	var d := maxi(1, int(delay_seconds * float(SAMPLE_RATE)))
	var fb: float = clampf(feedback, -0.95, 0.95)
	var n := buf.size()
	if d >= n:
		return
	for i in range(d, n):
		buf[i] = buf[i] + fb * buf[i - d]


static func _allpass(buf: PackedFloat32Array, delay_seconds: float, g: float) -> void:
	var d := maxi(1, int(delay_seconds * float(SAMPLE_RATE)))
	var n := buf.size()
	if d >= n:
		return
	var dry := buf.duplicate()
	for i in range(d, n):
		buf[i] = -g * dry[i] + dry[i - d] + g * buf[i - d]


## Schroeder reverb: four parallel combs into two allpasses. Not a convincing
## hall, but exactly the short slap a stadium bowl gives back, and it costs four
## passes over the buffer.
static func _reverb(buf: PackedFloat32Array, size: float, decay: float, wet: float) -> void:
	if wet <= 0.0:
		return
	var delays := PackedFloat32Array([0.0297, 0.0371, 0.0411, 0.0437])
	var acc := _silence(buf.size())
	for k in delays.size():
		var branch := buf.duplicate()
		_comb(branch, delays[k] * size, clampf(decay * 0.85, 0.0, 0.92))
		_mix(acc, branch, 0.25)
	_allpass(acc, 0.0050 * size, 0.5)
	_allpass(acc, 0.0017 * size, 0.5)
	_lp1(acc, 4200.0)
	_mix(buf, acc, wet)


# --- loop helpers ----------------------------------------------------------

## Folds the last `fade_frames` of the buffer back onto its head with an equal
## power crossfade and returns the shortened, seamless body. Equal power and not
## linear: the two halves are uncorrelated noise, and a linear crossfade of
## uncorrelated noise dips by 3 dB in the middle, which is audible as a pulse
## once per loop.
static func _crossfade_loop(buf: PackedFloat32Array, fade_frames: int) -> PackedFloat32Array:
	var loop_frames := buf.size() - fade_frames
	if loop_frames <= fade_frames:
		return buf.duplicate()
	var out := buf.slice(0, loop_frames)
	for i in fade_frames:
		var u := float(i) / float(fade_frames)
		out[i] = buf[loop_frames + i] * sqrt(1.0 - u) + buf[i] * sqrt(u)
	return out


## Rotates a seamless loop so that frame 0 lands on a rising zero crossing. A
## circular rotation of a seamless loop is still seamless, and it puts both
## loop_begin and loop_end on a value the mixer can jump across silently.
static func _rotate_to_zero(body: PackedFloat32Array) -> PackedFloat32Array:
	var n := body.size()
	var best := 0
	var best_value := absf(body[0])
	var window := mini(n - 1, 4000)
	for i in range(1, window):
		if body[i - 1] <= 0.0 and body[i] > 0.0:
			var v := absf(body[i])
			if v < best_value:
				best_value = v
				best = i
	if best == 0:
		return body
	var out := PackedFloat32Array()
	out.resize(n)
	for i in n:
		out[i] = body[(i + best) % n]
	return out


# --- output ----------------------------------------------------------------

## Shared tail of every one shot: fade out, normalise, encode. The fade happens
## before the normalisation so the published peak is exact, and neither gain is
## applied twice.
static func _finish(buf: PackedFloat32Array, target_peak: float, fade_seconds: float) -> AudioStreamWAV:
	_fade_out(buf, maxf(fade_seconds, 0.008))
	_normalize(buf, target_peak)
	return _to_stream(buf, AudioStreamWAV.LOOP_DISABLED, 0, 0)


static func _to_stream(buf: PackedFloat32Array, loop_mode: int, loop_begin: int, loop_end: int) -> AudioStreamWAV:
	var n := buf.size()
	var bytes := PackedByteArray()
	bytes.resize(n * 2)
	for i in n:
		var v := clampf(buf[i], -1.0, 1.0)
		bytes.encode_s16(i * 2, int(round(v * 32766.0)))

	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = SAMPLE_RATE
	wav.stereo = false
	wav.data = bytes
	wav.loop_mode = loop_mode as AudioStreamWAV.LoopMode
	wav.loop_begin = loop_begin
	wav.loop_end = loop_end
	return wav
