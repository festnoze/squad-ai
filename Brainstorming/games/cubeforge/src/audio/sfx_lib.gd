class_name SfxLib
## Procedural sound effect library for CUBEFORGE.
##
## Nothing is loaded from disk. Every entry returned by build() is synthesised
## into an AudioStreamWAV: 16 bit signed mono at 22050 Hz, little endian.
##
## The 28 sounds are composed from one small toolbox instead of 28 unrelated
## loops: white noise, a one pole low pass, a one pole high pass, a state
## variable band pass, a decaying sine, an attack-decay envelope and a peak
## normaliser. Buffers are built as PackedFloat32Array in -1..1 and converted to
## bytes exactly once, in _stream().
##
## Hard invariant: every sample buffer starts and ends on exactly zero. The
## envelope is always the last shaping stage of any component and of the final
## mix, and it forces both ends to silence with at least a 2 ms attack and a
## 5 ms release. A buffer that opens on a non-zero sample clicks audibly on
## every single footstep, which is by far the most common failure of this kind
## of module.
##
## Loudness is deliberately uniform: each sound is normalised to PEAK. Relative
## balance between sounds is set by the volume_db passed at play time.

const MIX_RATE := 22050

## Peak amplitude every finished sound is normalised to. Below 1.0 so that the
## 16 bit conversion never clips and so that a pitch shift at play time keeps
## some headroom.
const PEAK := 0.85

const _MIN_ATTACK := 0.002
const _MIN_RELEASE := 0.005

## Shared tail settings of the final envelope. The percussive decay already
## lives in the components, so the master pass only guarantees clean edges.
const _TAIL_ATTACK := 0.002
const _TAIL_RELEASE := 0.007

## Cutoff of the DC blocker applied to the final mix. Heavily low passed noise
## (wool, swim) drifts off centre, which wastes headroom and thumps the speaker
## cone; 20 Hz is far below every tone used here so nothing audible is lost.
const _DC_CUTOFF := 20.0


## Builds every sound. Costly (called once at startup), roughly a few hundred
## thousand samples in total.
static func build() -> Dictionary:
	var lib: Dictionary = {}

	# Material sounds. dig_* are short taps, break_* are the same recipe made
	# longer and fuller, step_* are the shortest and driest of the three.
	lib["dig_stone"] = _finish(_stone_hit(0.060, 0.50, 0.30, 1101))
	lib["break_stone"] = _finish(_stone_break(0.200, 1102))
	lib["step_stone"] = _finish(_stone_hit(0.055, 0.35, 0.32, 1103))

	lib["dig_dirt"] = _finish(_dirt_hit(0.065, 700.0, 0.50, 1201))
	lib["break_dirt"] = _finish(_dirt_break(0.180, 1202))
	lib["step_dirt"] = _finish(_dirt_hit(0.060, 620.0, 0.38, 1203))

	lib["dig_grass"] = _finish(_rustle(0.070, 2200.0, 3000.0, 0.42, 1301))
	lib["break_grass"] = _finish(_rustle(0.190, 1900.0, 2600.0, 0.48, 1302))
	lib["step_grass"] = _finish(_rustle(0.065, 2000.0, 2800.0, 0.34, 1303))

	lib["dig_sand"] = _finish(_sand_hiss(0.050, 4500.0, 4.6, 1401))
	lib["break_sand"] = _finish(_sand_hiss(0.160, 3400.0, 3.2, 1402))
	lib["step_sand"] = _finish(_sand_hiss(0.055, 3800.0, 4.2, 1403))

	lib["dig_wood"] = _finish(_wood_knock(0.065, 1250.0, 225.0, 0.60, 1501))
	lib["break_wood"] = _finish(_wood_break(0.210, 1502))
	lib["step_wood"] = _finish(_wood_knock(0.060, 900.0, 240.0, 0.55, 1503))

	lib["dig_glass"] = _finish(_glass_tick(0.055, 1601))
	lib["break_glass"] = _finish(_glass_shatter(0.320, 1602))

	lib["dig_wool"] = _finish(_wool_pat(0.070, 340.0, 2.6, 1701))
	lib["break_wool"] = _finish(_wool_pat(0.170, 300.0, 2.4, 1702))

	lib["dig_plant"] = _finish(_plant_snap(0.055, 2600.0, 1800.0, 1801))
	lib["break_plant"] = _finish(_plant_snap(0.150, 2300.0, 1600.0, 1802))

	lib["step_snow"] = _finish(_snow_crunch(0.070, 1901))

	# Interaction and body sounds.
	lib["place"] = _finish(_place_thump(0.090, 2101))
	lib["pop"] = _finish(_pop(0.110, 2102))
	lib["click"] = _finish(_click(0.022, 2103))
	lib["land"] = _finish(_land(0.200, 2104))
	lib["splash"] = _finish(_splash(0.420, 2105))
	lib["swim"] = _finish(_swim(0.360, 2106))

	return lib


# ---------------------------------------------------------------------------
# Recipes
# ---------------------------------------------------------------------------

## Mid band noise plus a dry high transient and a faint body tone. The band pass
## around 950 Hz is what makes it read as rock rather than as gravel.
static func _stone_hit(dur: float, click_gain: float, low_gain: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_band_pass(_noise(n, rng_seed), 950.0, 1.3), 0.002, 0.006, _rate(dur, 3.6)), 0, 1.0)
	_add(out, _shape(_high_pass(_noise(_samples(0.010), rng_seed + 1), 3200.0), 0.002, 0.005, 0.0), 0, click_gain)
	_add(out, _shape(_sine(_samples(0.040), 190.0, 130.0), 0.002, 0.006, 90.0), 0, low_gain)
	return out


static func _stone_break(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_band_pass(_noise(n, rng_seed), 880.0, 1.1), 0.002, 0.008, _rate(dur, 3.0)), 0, 1.0)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 1), 420.0), 0.003, 0.010, _rate(dur, 2.4)), 0, 0.38)
	_add(out, _shape(_high_pass(_noise(_samples(0.014), rng_seed + 2), 3000.0), 0.002, 0.005, 0.0), 0, 0.46)
	_add(out, _shape(_sine(_samples(0.120), 150.0, 90.0), 0.002, 0.008, 26.0), 0, 0.55)
	return out


## Muffled low passed noise. Dirt has almost no high content, so the cutoff is
## the whole character of the sound.
static func _dirt_hit(dur: float, cutoff: float, low_gain: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), cutoff), 0.002, 0.006, _rate(dur, 3.6)), 0, 1.0)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 1), 250.0), 0.002, 0.007, _rate(dur, 2.6)), 0, low_gain)
	return out


static func _dirt_break(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), 550.0), 0.002, 0.008, _rate(dur, 3.2)), 0, 1.0)
	_add(out, _shape(_sine(_samples(0.100), 130.0, 85.0), 0.002, 0.008, 30.0), 0, 0.52)
	return out


## High passed noise with a resonant band on top: a brushing, rustling texture.
static func _rustle(dur: float, hp_cut: float, band_freq: float, band_gain: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), hp_cut), 0.003, 0.007, _rate(dur, 3.0)), 0, 1.0)
	_add(out, _shape(_band_pass(_noise(n, rng_seed + 1), band_freq, 1.8), 0.003, 0.007, _rate(dur, 3.4)), 0, band_gain)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 2), 500.0), 0.003, 0.008, _rate(dur, 4.0)), 0, 0.22)
	return out


## Very bright noise that dies quickly. `amount` sets how many e-foldings of
## decay fit in the duration, so a larger value is a snappier grain.
static func _sand_hiss(dur: float, hp_cut: float, amount: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), hp_cut), 0.002, 0.006, _rate(dur, amount)), 0, 1.0)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 1), 900.0), 0.002, 0.007, _rate(dur, amount * 0.8)), 0, 0.26)
	return out


## Band passed noise plus a low resonance, the hollow knock of a log.
static func _wood_knock(dur: float, band_freq: float, res_freq: float, res_gain: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_band_pass(_noise(n, rng_seed), band_freq, 1.6), 0.002, 0.006, _rate(dur, 3.6)), 0, 1.0)
	_add(out, _shape(_sine(_samples(minf(dur, 0.055)), res_freq, res_freq * 0.94), 0.002, 0.006, _rate(minf(dur, 0.055), 3.0)), 0, res_gain)
	_add(out, _shape(_high_pass(_noise(_samples(0.008), rng_seed + 1), 2800.0), 0.002, 0.005, 0.0), 0, 0.34)
	return out


static func _wood_break(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_band_pass(_noise(n, rng_seed), 1100.0, 1.4), 0.002, 0.008, _rate(dur, 3.2)), 0, 1.0)
	_add(out, _shape(_sine(_samples(0.160), 215.0, 188.0), 0.002, 0.008, 20.0), 0, 0.78)
	_add(out, _shape(_high_pass(_noise(_samples(0.012), rng_seed + 1), 3500.0), 0.002, 0.005, 0.0), 0, 0.52)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 2), 380.0), 0.003, 0.009, _rate(dur, 2.6)), 0, 0.24)
	return out


## Sharp metallic tick: a very bright noise transient plus two high partials.
static func _glass_tick(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), 5200.0), 0.002, 0.005, _rate(dur, 5.0)), 0, 0.80)
	_add(out, _shape(_sine(_samples(0.040), 2600.0, 2520.0), 0.002, 0.005, 70.0), 0, 0.72)
	_add(out, _shape(_sine(_samples(0.030), 3900.0, 3780.0), 0.002, 0.005, 95.0), 0, 0.46)
	return out


## Bright burst followed by a trail of tinkling shards at random pitches.
static func _glass_shatter(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), 4200.0), 0.002, 0.008, _rate(dur, 4.2)), 0, 0.62)
	_add(out, _shape(_band_pass(_noise(_samples(0.050), rng_seed + 1), 3200.0, 2.4), 0.002, 0.006, 60.0), 0, 0.40)

	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed + 77
	var shard_dur := 0.075
	for k in 8:
		var freq: float = rng.randf_range(2300.0, 5400.0)
		var offset: int = int(rng.randf_range(0.012, dur - shard_dur - 0.01) * float(MIX_RATE))
		var tinkle := _shape(_sine(_samples(shard_dur), freq, freq * 0.965), 0.002, 0.006, 48.0)
		_add(out, tinkle, offset, rng.randf_range(0.22, 0.55))
	return out


## Very dull and soft: a heavily low passed thud with no transient at all.
static func _wool_pat(dur: float, cutoff: float, amount: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), cutoff), 0.004, 0.010, _rate(dur, amount)), 0, 1.0)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 1), 700.0), 0.004, 0.010, _rate(dur, amount * 1.4)), 0, 0.24)
	return out


## Dry snap of a plant being torn: bright and short with a narrow band body.
static func _plant_snap(dur: float, hp_cut: float, band_freq: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), hp_cut), 0.002, 0.006, _rate(dur, 4.0)), 0, 1.0)
	_add(out, _shape(_band_pass(_noise(n, rng_seed + 1), band_freq, 2.2), 0.002, 0.006, _rate(dur, 3.4)), 0, 0.52)
	return out


## Squeaky compression: a low passed body plus a tight mid band for the crunch.
static func _snow_crunch(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), 1300.0), 0.003, 0.008, _rate(dur, 3.0)), 0, 0.90)
	_add(out, _shape(_band_pass(_noise(n, rng_seed + 1), 1600.0, 3.0), 0.002, 0.006, _rate(dur, 5.0)), 0, 0.58)
	_add(out, _shape(_low_pass(_noise(n, rng_seed + 2), 260.0), 0.003, 0.008, _rate(dur, 2.6)), 0, 0.30)
	return out


## Soft wooden thump used when a block is set down.
static func _place_thump(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), 900.0), 0.002, 0.007, _rate(dur, 4.0)), 0, 0.80)
	_add(out, _shape(_sine(_samples(0.070), 265.0, 200.0), 0.002, 0.007, 44.0), 0, 1.0)
	_add(out, _shape(_high_pass(_noise(_samples(0.009), rng_seed + 1), 2600.0), 0.002, 0.005, 0.0), 0, 0.26)
	return out


## Short sine whose pitch rises, the classic pick up blip.
static func _pop(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_sine(n, 330.0, 900.0), 0.003, 0.008, _rate(dur, 2.2)), 0, 1.0)
	_add(out, _shape(_sine(n, 660.0, 1800.0), 0.003, 0.008, _rate(dur, 3.2)), 0, 0.26)
	_add(out, _shape(_high_pass(_noise(_samples(0.008), rng_seed), 3000.0), 0.002, 0.005, 0.0), 0, 0.18)
	return out


## Interface tick. Kept extremely brief so a menu never feels sluggish.
static func _click(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_high_pass(_noise(n, rng_seed), 3800.0), 0.002, 0.005, _rate(dur, 5.5)), 0, 1.0)
	_add(out, _shape(_band_pass(_noise(n, rng_seed + 1), 1800.0, 2.0), 0.002, 0.005, _rate(dur, 6.0)), 0, 0.34)
	return out


## Dull low impact for touching the ground.
static func _land(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	_add(out, _shape(_sine(_samples(0.160), 115.0, 70.0), 0.002, 0.008, 22.0), 0, 1.0)
	_add(out, _shape(_low_pass(_noise(n, rng_seed), 420.0), 0.002, 0.008, _rate(dur, 4.0)), 0, 0.58)
	_add(out, _shape(_high_pass(_noise(_samples(0.012), rng_seed + 1), 2500.0), 0.002, 0.005, 0.0), 0, 0.24)
	return out


## Noise that swells and falls back, with the low pass opening as it rises so
## the water seems to break the surface rather than just fade in.
static func _splash(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	var body := _sweep_low_pass(_noise(n, rng_seed), 700.0, 2900.0)
	_add(out, _shape(body, 0.100, 0.120, _rate(dur, 3.6)), 0, 1.0)
	_add(out, _shape(_high_pass(_noise(n, rng_seed + 1), 3200.0), 0.060, 0.100, _rate(dur, 4.4)), 0, 0.42)
	_add(out, _shape(_sine(_samples(0.140), 165.0, 110.0), 0.004, 0.010, 24.0), 0, 0.30)
	return out


## Slow muffled surge with a gentle wobble, for moving through water.
static func _swim(dur: float, rng_seed: int) -> PackedFloat32Array:
	var n := _samples(dur)
	var out := _blank(n)
	var body := _low_pass(_noise(n, rng_seed), 320.0)
	_tremolo(body, 6.0, 0.35)
	_add(out, _shape(body, 0.080, 0.100, _rate(dur, 2.0)), 0, 1.0)
	var top := _low_pass(_noise(n, rng_seed + 1), 780.0)
	_tremolo(top, 4.5, 0.45)
	_add(out, _shape(top, 0.070, 0.100, _rate(dur, 2.6)), 0, 0.28)
	return out


# ---------------------------------------------------------------------------
# Synthesis toolbox
# ---------------------------------------------------------------------------

## Sample count for a duration in seconds, never shorter than a few samples so
## the envelope always has room to work.
static func _samples(seconds: float) -> int:
	return maxi(16, int(round(seconds * float(MIX_RATE))))


static func _blank(n: int) -> PackedFloat32Array:
	var buf := PackedFloat32Array()
	buf.resize(n)
	buf.fill(0.0)
	return buf


## Decay rate in nepers per second such that `amount` e-foldings fit in `dur`.
static func _rate(dur: float, amount: float) -> float:
	return amount / maxf(dur, 0.001)


## Deterministic white noise in -1..1. A fixed seed keeps every launch of the
## game identical, which matters because these buffers are cached in memory.
static func _noise(n: int, rng_seed: int) -> PackedFloat32Array:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var buf := PackedFloat32Array()
	buf.resize(n)
	for i in n:
		buf[i] = rng.randf_range(-1.0, 1.0)
	return buf


## One pole low pass, y += a * (x - y).
static func _low_pass(src: PackedFloat32Array, cutoff_hz: float) -> PackedFloat32Array:
	var n := src.size()
	var out := PackedFloat32Array()
	out.resize(n)
	var fc: float = clampf(cutoff_hz, 20.0, float(MIX_RATE) * 0.45)
	var a: float = 1.0 - exp(-TAU * fc / float(MIX_RATE))
	var y := 0.0
	for i in n:
		y += a * (src[i] - y)
		out[i] = y
	return out


## One pole low pass whose cutoff sweeps linearly from f_start to f_end.
static func _sweep_low_pass(src: PackedFloat32Array, f_start: float, f_end: float) -> PackedFloat32Array:
	var n := src.size()
	var out := PackedFloat32Array()
	out.resize(n)
	var denom: float = float(maxi(n - 1, 1))
	var y := 0.0
	for i in n:
		var fc: float = clampf(lerpf(f_start, f_end, float(i) / denom), 20.0, float(MIX_RATE) * 0.45)
		var a: float = 1.0 - exp(-TAU * fc / float(MIX_RATE))
		y += a * (src[i] - y)
		out[i] = y
	return out


## One pole high pass (RC differentiator), y = a * (y + x - x_prev).
static func _high_pass(src: PackedFloat32Array, cutoff_hz: float) -> PackedFloat32Array:
	var n := src.size()
	var out := PackedFloat32Array()
	out.resize(n)
	var fc: float = clampf(cutoff_hz, 20.0, float(MIX_RATE) * 0.45)
	var rc: float = 1.0 / (TAU * fc)
	var dt: float = 1.0 / float(MIX_RATE)
	var a: float = rc / (rc + dt)
	var y := 0.0
	var prev := 0.0
	for i in n:
		var x: float = src[i]
		y = a * (y + x - prev)
		prev = x
		out[i] = y
	return out


## Chamberlin state variable band pass. Stability requires the tuning
## coefficient to stay well below 1, which caps the centre frequency near a
## sixth of the sample rate; anything brighter should use _high_pass instead.
static func _band_pass(src: PackedFloat32Array, freq_hz: float, q: float) -> PackedFloat32Array:
	var n := src.size()
	var out := PackedFloat32Array()
	out.resize(n)
	var fc: float = clampf(freq_hz, 20.0, float(MIX_RATE) / 6.5)
	var f: float = 2.0 * sin(PI * fc / float(MIX_RATE))
	var damp: float = clampf(1.0 / clampf(q, 0.4, 8.0), 0.06, 1.6)
	var low := 0.0
	var band := 0.0
	for i in n:
		var high: float = src[i] - low - damp * band
		band += f * high
		low += f * band
		out[i] = band
	return out


## Sine sweeping linearly from f_start to f_end. Amplitude is left flat here:
## the decay comes from the envelope so that both stages stay independent.
static func _sine(n: int, f_start: float, f_end: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(n)
	var inv: float = 1.0 / float(MIX_RATE)
	var denom: float = float(maxi(n - 1, 1))
	var phase := 0.0
	for i in n:
		out[i] = sin(phase)
		var f: float = lerpf(f_start, f_end, float(i) / denom)
		phase += TAU * f * inv
	return out


## Sinusoidal amplitude modulation, depth 0 keeps the signal untouched.
static func _tremolo(buf: PackedFloat32Array, rate_hz: float, depth: float) -> void:
	var n := buf.size()
	var d: float = clampf(depth, 0.0, 1.0)
	var inv: float = 1.0 / float(MIX_RATE)
	for i in n:
		var lfo: float = 1.0 - d * 0.5 * (1.0 - cos(TAU * rate_hz * float(i) * inv))
		buf[i] = buf[i] * lfo


## Attack-decay envelope applied in place. `curve` is the exponential decay rate
## in nepers per second (0 keeps a flat body). Both ends are forced to exactly
## zero: the attack ramp starts at sample 0 with gain 0 and the release ramp
## ends at the last sample with gain 0.
static func _envelope(buf: PackedFloat32Array, attack: float, release: float, curve: float) -> void:
	var n := buf.size()
	if n < 4:
		buf.fill(0.0)
		return
	var a: int = maxi(1, int(round(maxf(attack, _MIN_ATTACK) * float(MIX_RATE))))
	var r: int = maxi(1, int(round(maxf(release, _MIN_RELEASE) * float(MIX_RATE))))
	# Short buffers cannot host both ramps at full length, so share the room.
	var room: int = n - 1
	if a + r > room:
		var total: int = a + r
		a = clampi(a * room / total, 1, room - 1)
		r = maxi(1, room - a)
	var inv: float = 1.0 / float(MIX_RATE)
	var last: int = n - 1
	for i in n:
		var e: float = exp(-curve * float(i) * inv)
		if i < a:
			e *= float(i) / float(a)
		var tail: int = last - i
		if tail < r:
			e *= float(tail) / float(r)
		buf[i] = buf[i] * e


## Scales in place so the largest absolute sample equals `peak`. A silent buffer
## is left alone rather than amplified into noise.
static func _normalise(buf: PackedFloat32Array, peak: float) -> void:
	var m := 0.0
	for i in buf.size():
		var v: float = absf(buf[i])
		if v > m:
			m = v
	if m < 0.000001:
		return
	var gain: float = peak / m
	for i in buf.size():
		buf[i] = buf[i] * gain


## Envelope then normalise to unit peak, for a component about to be mixed.
## Returns the same array so calls can be chained.
static func _shape(buf: PackedFloat32Array, attack: float, release: float, curve: float) -> PackedFloat32Array:
	_envelope(buf, attack, release, curve)
	_normalise(buf, 1.0)
	return buf


## Mixes `src` into `dst` at a sample offset, clipping to the destination.
static func _add(dst: PackedFloat32Array, src: PackedFloat32Array, offset: int, gain: float) -> void:
	var n := dst.size()
	var m := src.size()
	for i in m:
		var j: int = offset + i
		if j < 0:
			continue
		if j >= n:
			break
		dst[j] = dst[j] + src[i] * gain


## Final stage of every sound: DC removal, then the master envelope that
## guarantees silent edges (it must stay last, so that the ramps decide the
## first and last sample), then normalisation to PEAK, then the single float to
## 16 bit conversion.
static func _finish(buf: PackedFloat32Array) -> AudioStreamWAV:
	var mix := _high_pass(buf, _DC_CUTOFF)
	_envelope(mix, _TAIL_ATTACK, _TAIL_RELEASE, 0.0)
	_normalise(mix, PEAK)
	return _stream(mix)


## Packs a -1..1 float buffer into a mono 16 bit little endian AudioStreamWAV.
static func _stream(buf: PackedFloat32Array) -> AudioStreamWAV:
	var n := buf.size()
	var bytes := PackedByteArray()
	bytes.resize(n * 2)
	for i in n:
		var v: int = clampi(int(round(clampf(buf[i], -1.0, 1.0) * 32767.0)), -32768, 32767)
		bytes.encode_s16(i * 2, v)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = MIX_RATE
	stream.stereo = false
	stream.loop_mode = AudioStreamWAV.LOOP_DISABLED
	stream.data = bytes
	return stream
