## Procedural sound bank for CALL OF WAR.
##
## The project ships zero binary assets, so every sample is synthesised from
## code at load time. Output is always mono 16 bit PCM at 22050 Hz wrapped in an
## AudioStreamWAV.
##
## The synthesis toolbox is a handful of private primitives (noise bursts with a
## time varying low pass, decaying sines, exponential sweeps, two pole
## resonators) that the 49 public samples recombine. Nothing here touches the
## scene tree, so the whole bank can be built in headless mode.
class_name SfxLib
extends RefCounted

const MIX_RATE := 22050
## Peak the samples are normalised to, leaving a little room before clipping.
const HEAD_ROOM := 0.94
## Length of the anti click fade applied to the tail of every one shot sample.
const FADE_SAMPLES := 110
## Maps the inline generator state (0 .. 2^31) onto -1 .. 1. Inlining the noise
## instead of calling into RandomNumberGenerator once per sample is what keeps
## the whole bank under a fraction of a second.
const NOISE_SCALE := 9.31322574615e-10
## Amplitude under which a decaying voice is considered finished.
const SILENCE := 0.0006

## Every sample name the project may ask for. Exactly these keys.
const NAMES: PackedStringArray = [
	"rifle_m1", "rifle_kar98", "smg_thompson", "smg_mp40", "pistol_1911",
	"sniper_springfield", "mg42", "garand_ping", "dry_fire",
	"reload_in", "reload_out", "bolt", "grenade_pin", "grenade_throw",
	"explosion", "explosion_far", "artillery_incoming", "artillery_hit",
	"impact_dirt", "impact_stone", "impact_wood", "impact_metal", "impact_flesh",
	"ricochet", "whizz", "shell_casing",
	"step_grass", "step_dirt", "step_stone", "step_wood", "step_water",
	"hurt", "death", "breath", "bandage", "heartbeat",
	"german_alert", "german_shout", "german_death", "french_ok", "french_go",
	"ui_click", "ui_open", "ui_close", "objective_done", "sector_captured",
	"distant_battle", "bird", "wind",
]

## Samples that are meant to be played as a continuous bed and therefore get a
## forward loop plus an internal cross fade instead of a tail fade.
const _LOOPING: PackedStringArray = ["wind", "distant_battle"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Builds every sample once. Returns name -> AudioStreamWAV.
static func build_all() -> Dictionary:
	var bank: Dictionary = {}
	for sample_name: String in NAMES:
		var stream: AudioStreamWAV = build(sample_name)
		if stream != null:
			bank[sample_name] = stream
	return bank


## Builds a single sample by name. Returns null for an unknown name.
static func build(sample_name: String) -> AudioStreamWAV:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(sample_name) + 7771
	var buf: PackedFloat32Array = _render(sample_name, rng)
	if buf.is_empty():
		return null
	var loops: bool = _LOOPING.has(sample_name)
	if loops:
		_loopify(buf, 0.12)
	else:
		_fade_out(buf)
	return _to_stream(buf, loops)


# ---------------------------------------------------------------------------
# Sample table
# ---------------------------------------------------------------------------

## Dispatches a name to its generator. Returns an empty buffer when unknown.
static func _render(sample_name: String, rng: RandomNumberGenerator) -> PackedFloat32Array:
	match sample_name:
		# --- Firearms -------------------------------------------------------
		"rifle_m1":
			# Semi auto .30-06: dry, hard crack, medium body.
			return _shot(0.54, 1.00, 50.0, 9500.0, 1100.0, 106.0, 0.78, 25.0, 0.34, 8.0, rng)
		"rifle_kar98":
			# Bolt action 7.92: sharper and a touch higher than the Garand.
			return _shot(0.50, 1.00, 58.0, 10500.0, 1350.0, 126.0, 0.72, 28.0, 0.30, 9.5, rng)
		"sniper_springfield":
			# Long barrel: less crack, more boom, longer valley tail.
			return _shot(0.66, 0.92, 42.0, 8200.0, 950.0, 92.0, 0.86, 21.0, 0.40, 6.2, rng)
		"smg_thompson":
			# .45 ACP, fat and slow sounding for a submachine gun.
			return _shot(0.32, 0.86, 74.0, 6400.0, 1000.0, 142.0, 0.60, 40.0, 0.20, 15.0, rng)
		"smg_mp40":
			# 9 mm, drier and clackier than the Thompson.
			return _shot(0.29, 0.84, 86.0, 5600.0, 880.0, 156.0, 0.54, 46.0, 0.17, 18.0, rng)
		"pistol_1911":
			return _shot(0.28, 0.88, 92.0, 7000.0, 1300.0, 178.0, 0.50, 52.0, 0.15, 20.0, rng)
		"mg42":
			# Retriggered at 1200 rpm (50 ms apart), so it must stay very short.
			return _shot(0.13, 0.90, 155.0, 7600.0, 1600.0, 205.0, 0.46, 95.0, 0.09, 42.0, rng)
		"garand_ping":
			return _garand_ping(rng)
		"dry_fire":
			return _dry_fire(rng)

		# --- Handling -------------------------------------------------------
		"reload_in":
			return _reload(rng, true)
		"reload_out":
			return _reload(rng, false)
		"bolt":
			return _bolt(rng)
		"grenade_pin":
			return _grenade_pin(rng)
		"grenade_throw":
			return _grenade_throw(rng)

		# --- Blasts ---------------------------------------------------------
		"explosion":
			return _explosion(1.10, 1.00, 3600.0, 120.0, 88.0, 0.55, 3.4, rng)
		"explosion_far":
			return _explosion_far(1.30, 0.62, rng)
		"artillery_incoming":
			return _artillery_incoming(rng)
		"artillery_hit":
			return _explosion(1.22, 1.00, 2600.0, 90.0, 62.0, 0.70, 2.6, rng)

		# --- Impacts --------------------------------------------------------
		"impact_dirt":
			return _impact_dirt(rng)
		"impact_stone":
			return _impact_stone(rng)
		"impact_wood":
			return _impact_wood(rng)
		"impact_metal":
			return _impact_metal(rng)
		"impact_flesh":
			return _impact_flesh(rng)
		"ricochet":
			return _ricochet(rng)
		"whizz":
			return _whizz(rng)
		"shell_casing":
			return _shell_casing(rng)

		# --- Footsteps ------------------------------------------------------
		"step_grass":
			return _step_grass(rng)
		"step_dirt":
			return _step_dirt(rng)
		"step_stone":
			return _step_stone(rng)
		"step_wood":
			return _step_wood(rng)
		"step_water":
			return _step_water(rng)

		# --- Player body ----------------------------------------------------
		"hurt":
			return _hurt(rng)
		"death":
			return _death(rng)
		"breath":
			return _breath(rng)
		"bandage":
			return _bandage(rng)
		"heartbeat":
			return _heartbeat(rng)

		# --- Stylised voices ------------------------------------------------
		"german_alert":
			return _german_alert(rng)
		"german_shout":
			return _german_shout(rng)
		"german_death":
			return _german_death(rng)
		"french_ok":
			return _french_ok(rng)
		"french_go":
			return _french_go(rng)

		# --- Interface ------------------------------------------------------
		"ui_click":
			return _ui_click()
		"ui_open":
			return _ui_slide(true)
		"ui_close":
			return _ui_slide(false)
		"objective_done":
			return _objective_done()
		"sector_captured":
			return _sector_captured(rng)

		# --- Ambience -------------------------------------------------------
		"distant_battle":
			return _distant_battle(rng)
		"bird":
			return _bird(rng)
		"wind":
			return _wind(rng)
	return PackedFloat32Array()


# ---------------------------------------------------------------------------
# Firearms
# ---------------------------------------------------------------------------

## Generic gunshot: a filtered noise crack with a near instant attack, a low
## frequency body for the muzzle blast, and a duller, longer reverberation tail.
static func _shot(seconds: float, crack_amp: float, crack_decay: float,
		cut_hi: float, cut_lo: float, body_freq: float, body_amp: float,
		body_decay: float, tail_amp: float, tail_decay: float,
		rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(seconds)
	_noise_burst(buf, rng, crack_amp, crack_decay, cut_hi, cut_lo, 0.0, 0.0006)
	# Muzzle blast body: a short downward pitched thump.
	_sweep(buf, body_freq * 1.45, body_freq * 0.62, body_amp, body_decay, 0.0, 0.0008)
	_tone(buf, body_freq * 2.35, body_amp * 0.30, body_decay * 1.7, 0.0, 0.0008)
	# Valley tail: dull noise that swells slightly after the crack.
	var tail: PackedFloat32Array = _buf(seconds)
	_noise_burst(tail, rng, tail_amp, tail_decay, 1500.0, 280.0, 0.020, 0.055)
	_lowpass(tail, 850.0)
	_mix(buf, tail, 1.0)
	_normalize(buf, HEAD_ROOM)
	return buf


## The famous en bloc clip flying out of an emptied M1 Garand.
static func _garand_ping(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.72)
	# Tiny metallic scrape as the clip leaves the receiver.
	_noise_burst(buf, rng, 0.30, 130.0, 8000.0, 3000.0, 0.0, 0.0008)
	# Fundamental plus a fifth above, the interval that makes the ping sing.
	_tone(buf, 2600.0, 0.62, 5.0, 0.004, 0.001)
	_tone(buf, 3900.0, 0.40, 6.4, 0.004, 0.001)
	_tone(buf, 5220.0, 0.16, 11.0, 0.004, 0.001)
	_tone(buf, 1310.0, 0.12, 9.0, 0.004, 0.001)
	_normalize(buf, HEAD_ROOM * 0.82)
	return buf


## Hammer falling on an empty chamber.
static func _dry_fire(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.10)
	_noise_burst(buf, rng, 0.85, 260.0, 9000.0, 2200.0, 0.0, 0.0004)
	_tone(buf, 1850.0, 0.30, 90.0, 0.0, 0.0004)
	_tone(buf, 620.0, 0.22, 70.0, 0.0, 0.0006)
	_highpass(buf, 350.0)
	_normalize(buf, HEAD_ROOM * 0.65)
	return buf


# ---------------------------------------------------------------------------
# Weapon handling
# ---------------------------------------------------------------------------

## Magazine going in (`inserting`) or coming out. Two or three metal clacks.
static func _reload(rng: RandomNumberGenerator, inserting: bool) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.46)
	if inserting:
		_metal_click(buf, 0.00, 0.55, 900.0, rng)
		_metal_click(buf, 0.14, 0.42, 1400.0, rng)
		_metal_click(buf, 0.25, 0.90, 640.0, rng)   # the magazine seating
		_tone(buf, 190.0, 0.30, 34.0, 0.25, 0.001)
	else:
		_metal_click(buf, 0.00, 0.85, 1150.0, rng)  # release catch
		# Magazine sliding free, a short filtered rasp.
		_noise_burst(buf, rng, 0.26, 22.0, 3200.0, 900.0, 0.06, 0.03)
		_metal_click(buf, 0.28, 0.40, 780.0, rng)
	_highpass(buf, 130.0)
	_normalize(buf, HEAD_ROOM * 0.72)
	return buf


## Bolt cycling: pull back, ride forward, lock down.
static func _bolt(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.40)
	_metal_click(buf, 0.00, 0.70, 1250.0, rng)
	_noise_burst(buf, rng, 0.22, 30.0, 4200.0, 1200.0, 0.03, 0.02)
	_metal_click(buf, 0.17, 0.62, 880.0, rng)
	_metal_click(buf, 0.27, 0.80, 1650.0, rng)
	_highpass(buf, 160.0)
	_normalize(buf, HEAD_ROOM * 0.70)
	return buf


## Safety pin torn out of a grenade: a tick and a small spring.
static func _grenade_pin(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.26)
	_metal_click(buf, 0.00, 0.55, 2100.0, rng)
	_tone(buf, 3300.0, 0.22, 26.0, 0.01, 0.001)
	_tone(buf, 4700.0, 0.12, 34.0, 0.01, 0.001)
	_metal_click(buf, 0.11, 0.45, 1550.0, rng)
	_highpass(buf, 400.0)
	_normalize(buf, HEAD_ROOM * 0.62)
	return buf


## Arm swinging through the air, cloth and a whoosh.
static func _grenade_throw(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.30)
	var n: int = buf.size()
	var st: int = _seed_of(rng)
	# Bell shaped amplitude, band moving upwards then away.
	for i: int in n:
		var t: float = float(i) / float(n)
		st = (st * 1103515245 + 12345) & 0x7fffffff
		var nz: float = float(st) * NOISE_SCALE - 1.0
		# Parabolic bell: indistinguishable from a half sine and far cheaper.
		var env: float = 4.0 * t * (1.0 - t)
		buf[i] = nz * env * env
	var swept: PackedFloat32Array = _resonate(buf, 1450.0, 900.0, 1.0)
	_mix(swept, _resonate(buf, 700.0, 600.0, 0.7), 1.0)
	_highpass(swept, 260.0)
	_normalize(swept, HEAD_ROOM * 0.55)
	return swept


# ---------------------------------------------------------------------------
# Blasts
# ---------------------------------------------------------------------------

## Nearby detonation: broadband noise whose cut off collapses over time, a very
## low sweep for the pressure wave, and a long rumbling tail.
static func _explosion(seconds: float, amp: float, cut_hi: float, cut_lo: float,
		low_freq: float, tail_amp: float, tail_decay: float,
		rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(seconds)
	_noise_burst(buf, rng, amp, 9.0, cut_hi, cut_lo, 0.0, 0.0015)
	_sweep(buf, low_freq * 2.0, low_freq * 0.42, amp * 0.85, 5.5, 0.0, 0.002)
	_sweep(buf, low_freq * 0.9, low_freq * 0.30, amp * 0.55, 3.0, 0.010, 0.008)
	# Debris rattle just after the blast.
	var debris: PackedFloat32Array = _buf(seconds)
	_noise_burst(debris, rng, 0.35, 6.0, 2600.0, 400.0, 0.09, 0.05)
	_lowpass(debris, 2200.0)
	_mix(buf, debris, 0.5)
	# Rolling tail.
	var tail: PackedFloat32Array = _buf(seconds)
	_noise_burst(tail, rng, tail_amp, tail_decay, 700.0, 110.0, 0.05, 0.12)
	_lowpass(tail, 420.0)
	_mix(buf, tail, 1.0)
	_normalize(buf, HEAD_ROOM)
	return buf


## The same event heard from far away: no crack left, only a muffled thump and
## the valley echo. Also used as the distance layer of `play_shot`.
static func _explosion_far(seconds: float, amp: float,
		rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(seconds)
	_noise_burst(buf, rng, amp, 4.2, 520.0, 90.0, 0.0, 0.030)
	_sweep(buf, 74.0, 34.0, amp * 0.9, 3.2, 0.0, 0.020)
	var echo: PackedFloat32Array = _buf(seconds)
	_noise_burst(echo, rng, amp * 0.55, 2.4, 320.0, 70.0, 0.22, 0.16)
	_mix(buf, echo, 1.0)
	var echo2: PackedFloat32Array = _buf(seconds)
	_noise_burst(echo2, rng, amp * 0.30, 2.0, 240.0, 60.0, 0.55, 0.22)
	_mix(buf, echo2, 1.0)
	_lowpass(buf, 400.0)
	_lowpass(buf, 400.0)
	_normalize(buf, HEAD_ROOM * 0.85)
	return buf


## The falling shell: a descending, wavering whistle that swells until impact.
static func _artillery_incoming(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(1.05)
	var n: int = buf.size()
	var inv: float = TAU / float(MIX_RATE)
	var inv_n: float = 1.0 / float(n)
	# Vibrato on a sine recurrence, carrier on a rotating unit phasor whose
	# angle is only refreshed every few dozen samples (the glide is slow).
	var wv: float = TAU * 5.5 / float(MIX_RATE)
	var cv: float = 2.0 * cos(wv)
	var pv: float = 0.0
	var qv: float = sin(wv)
	var re: float = 1.0
	var im: float = 0.0
	var cr: float = 1.0
	var sr: float = 0.0
	var refresh: int = 0
	for i: int in n:
		var t: float = float(i) * inv_n
		if refresh <= 0:
			var freq: float = lerpf(1750.0, 430.0, t * t) * (1.0 + pv * 0.02)
			var w: float = freq * inv
			cr = cos(w)
			sr = sin(w)
			var mag: float = sqrt(re * re + im * im)
			if mag > 0.0001:
				re /= mag
				im /= mag
			refresh = 32
		refresh -= 1
		# Swell towards the end, then a sharp cut for the impact to take over.
		var env: float = t * t * 0.85 + 0.05
		if t > 0.94:
			env *= (1.0 - t) / 0.06
		buf[i] = im * env
		var nre: float = re * cr - im * sr
		im = re * sr + im * cr
		re = nre
		var nv: float = cv * qv - pv
		pv = qv
		qv = nv
	# A breath of wind noise riding along with the shell.
	var air: PackedFloat32Array = _buf(1.05)
	_noise_burst(air, rng, 0.30, 0.0, 2400.0, 900.0, 0.0, 0.5)
	_mix(buf, air, 0.35)
	_normalize(buf, HEAD_ROOM * 0.80)
	return buf


# ---------------------------------------------------------------------------
# Impacts
# ---------------------------------------------------------------------------

static func _impact_dirt(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.20)
	_noise_burst(buf, rng, 0.85, 40.0, 1700.0, 320.0, 0.0, 0.001)
	_sweep(buf, 150.0, 70.0, 0.55, 32.0, 0.0, 0.002)
	_lowpass(buf, 1400.0)
	_normalize(buf, HEAD_ROOM * 0.80)
	return buf


static func _impact_stone(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.18)
	_noise_burst(buf, rng, 0.95, 90.0, 9000.0, 1800.0, 0.0, 0.0004)
	_tone(buf, 2350.0, 0.24, 55.0, 0.0, 0.0006)
	_tone(buf, 3700.0, 0.14, 70.0, 0.0, 0.0006)
	_sweep(buf, 260.0, 130.0, 0.30, 60.0, 0.0, 0.001)
	_highpass(buf, 200.0)
	_normalize(buf, HEAD_ROOM * 0.82)
	return buf


static func _impact_wood(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.24)
	_noise_burst(buf, rng, 0.75, 70.0, 5000.0, 900.0, 0.0, 0.0005)
	var body: PackedFloat32Array = _buf(0.24)
	_noise_burst(body, rng, 0.9, 80.0, 6000.0, 800.0, 0.0, 0.0005)
	var res: PackedFloat32Array = _resonate(body, 430.0, 120.0, 1.0)
	_mix(res, _resonate(body, 910.0, 200.0, 0.6), 1.0)
	_mix(res, _resonate(body, 1720.0, 380.0, 0.3), 1.0)
	_mix(buf, res, 0.9)
	_normalize(buf, HEAD_ROOM * 0.80)
	return buf


static func _impact_metal(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.38)
	_noise_burst(buf, rng, 0.80, 150.0, 10000.0, 2500.0, 0.0, 0.0004)
	_tone(buf, 1780.0, 0.34, 13.0, 0.0, 0.0006)
	_tone(buf, 2690.0, 0.26, 17.0, 0.0, 0.0006)
	_tone(buf, 3970.0, 0.18, 22.0, 0.0, 0.0006)
	_tone(buf, 5400.0, 0.09, 30.0, 0.0, 0.0006)
	_highpass(buf, 380.0)
	_normalize(buf, HEAD_ROOM * 0.78)
	return buf


static func _impact_flesh(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.17)
	_noise_burst(buf, rng, 0.90, 62.0, 900.0, 180.0, 0.0, 0.001)
	_sweep(buf, 190.0, 80.0, 0.60, 46.0, 0.0, 0.002)
	# A wet slap on top, kept dull.
	_noise_burst(buf, rng, 0.30, 150.0, 2600.0, 700.0, 0.0, 0.0008)
	_lowpass(buf, 1100.0)
	_normalize(buf, HEAD_ROOM * 0.80)
	return buf


## Bullet skipping off stone or steel: a bright band sliding downwards.
static func _ricochet(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.42)
	_noise_burst(buf, rng, 0.55, 110.0, 9000.0, 2400.0, 0.0, 0.0005)
	_sweep(buf, 3400.0, 780.0, 0.55, 11.0, 0.0, 0.002)
	_sweep(buf, 4600.0, 1180.0, 0.30, 14.0, 0.006, 0.002)
	_sweep(buf, 2100.0, 520.0, 0.22, 9.0, 0.012, 0.004)
	_highpass(buf, 420.0)
	_normalize(buf, HEAD_ROOM * 0.72)
	return buf


## Round passing close to the ear: a very short filtered noise glissando.
static func _whizz(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var seconds: float = 0.16
	var src: PackedFloat32Array = _buf(seconds)
	var n: int = src.size()
	var st: int = _seed_of(rng)
	for i: int in n:
		var t: float = float(i) / float(n)
		st = (st * 1103515245 + 12345) & 0x7fffffff
		var nz: float = float(st) * NOISE_SCALE - 1.0
		var env: float = 4.0 * t * (1.0 - t)
		src[i] = nz * env * env
	var out: PackedFloat32Array = _resonate(src, 2300.0, 700.0, 1.0)
	_mix(out, _resonate(src, 1150.0, 500.0, 0.6), 1.0)
	# The Doppler drop, faked with a fast falling sine.
	_sweep(out, 2500.0, 850.0, 0.30, 16.0, 0.0, 0.004)
	_highpass(out, 500.0)
	_normalize(out, HEAD_ROOM * 0.62)
	return out


## Brass hitting the ground and bouncing twice.
static func _shell_casing(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.38)
	_brass_tick(buf, 0.00, 0.85, 3150.0, rng)
	_brass_tick(buf, 0.11, 0.48, 3620.0, rng)
	_brass_tick(buf, 0.19, 0.28, 4210.0, rng)
	_brass_tick(buf, 0.25, 0.15, 4680.0, rng)
	_highpass(buf, 700.0)
	_normalize(buf, HEAD_ROOM * 0.58)
	return buf


# ---------------------------------------------------------------------------
# Footsteps
# ---------------------------------------------------------------------------

static func _step_grass(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.17)
	# Soft rubbing rather than a hit: slow attack, high passed.
	_noise_burst(buf, rng, 0.80, 34.0, 5200.0, 1500.0, 0.0, 0.012)
	_highpass(buf, 1100.0)
	_sweep(buf, 130.0, 80.0, 0.16, 45.0, 0.0, 0.003)
	_normalize(buf, HEAD_ROOM * 0.45)
	return buf


static func _step_dirt(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.16)
	_noise_burst(buf, rng, 0.80, 52.0, 2100.0, 600.0, 0.0, 0.004)
	_sweep(buf, 145.0, 78.0, 0.42, 42.0, 0.0, 0.002)
	_lowpass(buf, 2400.0)
	_normalize(buf, HEAD_ROOM * 0.50)
	return buf


static func _step_stone(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.15)
	_noise_burst(buf, rng, 0.85, 105.0, 8500.0, 2000.0, 0.0, 0.0008)
	_tone(buf, 1420.0, 0.18, 60.0, 0.0, 0.001)
	_sweep(buf, 210.0, 120.0, 0.26, 55.0, 0.0, 0.002)
	_highpass(buf, 250.0)
	_normalize(buf, HEAD_ROOM * 0.52)
	return buf


static func _step_wood(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.22)
	var src: PackedFloat32Array = _buf(0.22)
	_noise_burst(src, rng, 0.9, 95.0, 6000.0, 1200.0, 0.0, 0.001)
	var res: PackedFloat32Array = _resonate(src, 265.0, 95.0, 1.0)
	_mix(res, _resonate(src, 530.0, 160.0, 0.55), 1.0)
	_mix(res, _resonate(src, 1180.0, 320.0, 0.25), 1.0)
	_mix(buf, res, 1.0)
	_mix(buf, src, 0.35)
	_highpass(buf, 110.0)
	_normalize(buf, HEAD_ROOM * 0.52)
	return buf


static func _step_water(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.30)
	# Splash: bright spray on the attack, then the water closing back in.
	_noise_burst(buf, rng, 0.90, 26.0, 6500.0, 900.0, 0.0, 0.006)
	_noise_burst(buf, rng, 0.35, 12.0, 1400.0, 300.0, 0.05, 0.05)
	# Droplets.
	_tone(buf, 1900.0, 0.10, 40.0, 0.10, 0.002)
	_tone(buf, 2400.0, 0.08, 45.0, 0.15, 0.002)
	_sweep(buf, 320.0, 170.0, 0.20, 22.0, 0.01, 0.008)
	_normalize(buf, HEAD_ROOM * 0.58)
	return buf


# ---------------------------------------------------------------------------
# Player body
# ---------------------------------------------------------------------------

static func _hurt(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _voice(0.34, 145.0, 105.0,
			PackedFloat32Array([560.0, 1080.0, 2350.0]), rng, 0.45, 0.9)
	_shape(buf, 0.010, 6.0)
	_normalize(buf, HEAD_ROOM * 0.70)
	return buf


static func _death(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _voice(0.62, 130.0, 62.0,
			PackedFloat32Array([500.0, 950.0, 2100.0]), rng, 0.75, 1.3)
	_shape(buf, 0.030, 2.6)
	# Final breath escaping.
	var air: PackedFloat32Array = _buf(0.62)
	_noise_burst(air, rng, 0.22, 3.0, 1600.0, 500.0, 0.30, 0.12)
	_mix(buf, air, 1.0)
	_normalize(buf, HEAD_ROOM * 0.72)
	return buf


static func _breath(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.52)
	var src: PackedFloat32Array = _buf(0.52)
	_noise_burst(src, rng, 1.0, 0.0, 3000.0, 3000.0, 0.0, 0.0)
	var res: PackedFloat32Array = _resonate(src, 620.0, 420.0, 1.0)
	_mix(res, _resonate(src, 1500.0, 700.0, 0.5), 1.0)
	_mix(buf, res, 1.0)
	# One inhale swell.
	var n: int = buf.size()
	for i: int in n:
		var t: float = float(i) / float(n)
		buf[i] *= 4.0 * t * (1.0 - t) * (0.55 + 0.45 * t)
	_normalize(buf, HEAD_ROOM * 0.42)
	return buf


## Tearing a field dressing and wrapping it: granular cloth noise.
static func _bandage(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.55)
	var n: int = buf.size()
	var st: int = _seed_of(rng)
	var y: float = 0.0
	var alpha: float = _lp_alpha(4200.0)
	var wg: float = TAU * 47.0 / float(MIX_RATE)
	var cg: float = 2.0 * cos(wg)
	var pg: float = 0.0
	var qg: float = sin(wg)
	var inv_n: float = 1.0 / float(n)
	for i: int in n:
		var t: float = float(i) * inv_n
		st = (st * 1103515245 + 12345) & 0x7fffffff
		var nz: float = float(st) * NOISE_SCALE - 1.0
		y += alpha * (nz - y)
		# Amplitude modulation gives the fibre by fibre tearing texture, the
		# noise itself supplying the slower irregularity.
		var am: float = 0.55 + 0.45 * pg * nz
		var ng: float = cg * qg - pg
		pg = qg
		qg = ng
		buf[i] = y * am * 4.0 * t * (1.0 - t)
	_highpass(buf, 900.0)
	_normalize(buf, HEAD_ROOM * 0.45)
	return buf


static func _heartbeat(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.70)
	_sweep(buf, 78.0, 42.0, 0.95, 14.0, 0.00, 0.012)
	_noise_burst(buf, rng, 0.16, 40.0, 420.0, 120.0, 0.00, 0.010)
	_sweep(buf, 66.0, 38.0, 0.62, 16.0, 0.26, 0.012)
	_noise_burst(buf, rng, 0.10, 44.0, 380.0, 110.0, 0.26, 0.010)
	_lowpass(buf, 260.0)
	_normalize(buf, HEAD_ROOM * 0.85)
	return buf


# ---------------------------------------------------------------------------
# Stylised voices
#
# No real words: a pitched impulse train pushed through two or three formant
# resonators, gated into syllables. German sits lower and harder, French higher
# and more open.
# ---------------------------------------------------------------------------

static func _german_alert(rng: RandomNumberGenerator) -> PackedFloat32Array:
	# Two hard syllables, "Ach-tung".
	var buf: PackedFloat32Array = _voice(0.52, 118.0, 96.0,
			PackedFloat32Array([540.0, 1120.0, 2380.0]), rng, 0.20, 0.35)
	_syllables(buf, PackedVector2Array([Vector2(0.02, 0.20), Vector2(0.25, 0.50)]))
	# Leading plosive, kept dark so the shout stays chesty.
	_noise_burst(buf, rng, 0.26, 190.0, 3400.0, 900.0, 0.0, 0.001)
	_shape(buf, 0.006, 1.2)
	_lowpass(buf, 3200.0)
	_normalize(buf, HEAD_ROOM * 0.72)
	return buf


static func _german_shout(rng: RandomNumberGenerator) -> PackedFloat32Array:
	# Three barked syllables, louder and with a rising last one.
	var buf: PackedFloat32Array = _voice(0.62, 132.0, 152.0,
			PackedFloat32Array([500.0, 1250.0, 2500.0]), rng, 0.18, 0.45)
	_syllables(buf, PackedVector2Array([
		Vector2(0.01, 0.15), Vector2(0.19, 0.33), Vector2(0.38, 0.60)]))
	_noise_burst(buf, rng, 0.20, 210.0, 3600.0, 1100.0, 0.0, 0.001)
	_noise_burst(buf, rng, 0.16, 210.0, 3600.0, 1100.0, 0.38, 0.001)
	_shape(buf, 0.005, 1.0)
	_lowpass(buf, 3400.0)
	_normalize(buf, HEAD_ROOM * 0.78)
	return buf


static func _german_death(rng: RandomNumberGenerator) -> PackedFloat32Array:
	# A falling, breaking cry that trails into breath.
	var buf: PackedFloat32Array = _voice(0.66, 150.0, 58.0,
			PackedFloat32Array([480.0, 900.0, 2050.0]), rng, 0.70, 1.5)
	_shape(buf, 0.012, 2.4)
	var air: PackedFloat32Array = _buf(0.66)
	_noise_burst(air, rng, 0.20, 2.6, 1300.0, 380.0, 0.34, 0.14)
	_mix(buf, air, 1.0)
	_lowpass(buf, 2900.0)
	_normalize(buf, HEAD_ROOM * 0.74)
	return buf


static func _french_ok(rng: RandomNumberGenerator) -> PackedFloat32Array:
	# Short, higher, friendlier: "d'accord".
	var buf: PackedFloat32Array = _voice(0.38, 168.0, 148.0,
			PackedFloat32Array([700.0, 1520.0, 2720.0]), rng, 0.12, 0.20)
	_syllables(buf, PackedVector2Array([Vector2(0.01, 0.13), Vector2(0.16, 0.36)]))
	_shape(buf, 0.010, 1.4)
	_highpass(buf, 190.0)
	_normalize(buf, HEAD_ROOM * 0.66)
	return buf


static func _french_go(rng: RandomNumberGenerator) -> PackedFloat32Array:
	# Rising exclamation: "on y va".
	var buf: PackedFloat32Array = _voice(0.46, 165.0, 215.0,
			PackedFloat32Array([740.0, 1620.0, 2850.0]), rng, 0.14, 0.25)
	_syllables(buf, PackedVector2Array([
		Vector2(0.01, 0.11), Vector2(0.14, 0.24), Vector2(0.27, 0.44)]))
	_shape(buf, 0.008, 1.2)
	_highpass(buf, 200.0)
	_normalize(buf, HEAD_ROOM * 0.70)
	return buf


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

static func _ui_click() -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.07)
	_tone(buf, 1250.0, 0.60, 75.0, 0.0, 0.0012)
	_tone(buf, 1875.0, 0.24, 95.0, 0.0, 0.0012)
	_normalize(buf, HEAD_ROOM * 0.50)
	return buf


static func _ui_slide(opening: bool) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.19)
	var a: float = 620.0
	var b: float = 1180.0
	if not opening:
		a = 1180.0
		b = 560.0
	_sweep(buf, a, b, 0.55, 18.0, 0.0, 0.004)
	_sweep(buf, a * 1.5, b * 1.5, 0.20, 24.0, 0.02, 0.004)
	_normalize(buf, HEAD_ROOM * 0.50)
	return buf


static func _objective_done() -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.62)
	_chime(buf, 659.0, 0.00, 0.55, 6.0)
	_chime(buf, 880.0, 0.09, 0.55, 6.0)
	_chime(buf, 1319.0, 0.19, 0.60, 4.5)
	_normalize(buf, HEAD_ROOM * 0.62)
	return buf


## Short martial flourish when a sector falls into allied hands.
static func _sector_captured(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.95)
	_chime(buf, 392.0, 0.00, 0.50, 5.0)
	_chime(buf, 523.0, 0.14, 0.50, 5.0)
	_chime(buf, 659.0, 0.27, 0.55, 4.4)
	_chime(buf, 784.0, 0.40, 0.72, 3.0)
	# A discreet snare roll under the fanfare.
	var snare: PackedFloat32Array = _buf(0.95)
	for k: int in 5:
		_noise_burst(snare, rng, 0.16, 90.0, 5000.0, 1400.0, 0.02 * float(k), 0.001)
	_highpass(snare, 900.0)
	_mix(buf, snare, 0.5)
	_normalize(buf, HEAD_ROOM * 0.72)
	return buf


# ---------------------------------------------------------------------------
# Ambience
# ---------------------------------------------------------------------------

## Muffled fighting somewhere over the hedgerows. Loops.
static func _distant_battle(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(1.40)
	var count: int = 6
	for k: int in count:
		var at: float = rng.randf_range(0.02, 1.20)
		var amp: float = rng.randf_range(0.20, 0.85)
		var lo: float = rng.randf_range(55.0, 130.0)
		_noise_burst(buf, rng, amp * 0.6, rng.randf_range(4.0, 11.0), 430.0, 80.0, at, 0.03)
		_sweep(buf, lo * 1.6, lo * 0.6, amp, rng.randf_range(5.0, 12.0), at, 0.02)
	# A thin bed of small arms crackle far away.
	var crackle: PackedFloat32Array = _buf(1.40)
	for k: int in 12:
		_noise_burst(crackle, rng, rng.randf_range(0.05, 0.18), 70.0,
				900.0, 240.0, rng.randf_range(0.0, 1.3), 0.002)
	_mix(buf, crackle, 0.7)
	_lowpass(buf, 520.0)
	_lowpass(buf, 520.0)
	_normalize(buf, HEAD_ROOM * 0.65)
	return buf


## A few chirps for the daytime countryside.
static func _bird(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var buf: PackedFloat32Array = _buf(0.48)
	var count: int = rng.randi_range(3, 4)
	var at: float = 0.0
	for k: int in count:
		var f: float = rng.randf_range(2900.0, 4400.0)
		var up: bool = rng.randf() > 0.45
		var f2: float = f * (1.45 if up else 0.68)
		_sweep(buf, f, f2, 0.55, 40.0, at, 0.004)
		_sweep(buf, f * 2.0, f2 * 2.0, 0.14, 55.0, at, 0.004)
		at += rng.randf_range(0.07, 0.12)
	_highpass(buf, 1600.0)
	_normalize(buf, HEAD_ROOM * 0.42)
	return buf


## Low wind bed. Loops.
static func _wind(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var seconds: float = 1.70
	var src: PackedFloat32Array = _buf(seconds)
	var n: int = src.size()
	var st: int = _seed_of(rng)
	var y: float = 0.0
	var alpha: float = _lp_alpha(1400.0)
	for i: int in n:
		st = (st * 1103515245 + 12345) & 0x7fffffff
		y += alpha * (float(st) * NOISE_SCALE - 1.0 - y)
		src[i] = y
	var out: PackedFloat32Array = _resonate(src, 380.0, 340.0, 1.0)
	_mix(out, _resonate(src, 820.0, 620.0, 0.55), 1.0)
	_mix(out, src, 0.25)
	# Slow gusting. The two modulator periods divide the loop length exactly so
	# the bed still matches itself at the seam. Both run on a sine recurrence.
	var w1: float = TAU * (2.0 / seconds) / float(MIX_RATE)
	var w2: float = TAU * (1.0 / seconds) / float(MIX_RATE)
	var c1: float = 2.0 * cos(w1)
	var c2: float = 2.0 * cos(w2)
	var p1: float = 0.0
	var q1: float = sin(w1)
	var p2: float = 0.0
	var q2: float = sin(w2)
	for i: int in n:
		out[i] *= 0.45 + 0.35 * p1 + 0.20 * p2
		var n1: float = c1 * q1 - p1
		p1 = q1
		q1 = n1
		var n2: float = c2 * q2 - p2
		p2 = q2
		q2 = n2
	_lowpass(out, 2200.0)
	_normalize(out, HEAD_ROOM * 0.40)
	return out


# ---------------------------------------------------------------------------
# Synthesis primitives
# ---------------------------------------------------------------------------

## Allocates a silent buffer of the requested length in seconds.
static func _buf(seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(maxi(1, int(seconds * float(MIX_RATE))))
	out.fill(0.0)
	return out


## Pulls a non zero seed for the inline linear congruential noise generator.
## A dedicated RNG call per sample would cost more than the noise itself.
static func _seed_of(rng: RandomNumberGenerator) -> int:
	return (int(rng.randi()) & 0x7fffffff) | 1


## Value of an exponential decay after `t` seconds at `rate` nepers per second.
static func _env_exp(t: float, rate: float) -> float:
	return exp(-maxf(t, 0.0) * rate)


## Per sample multiplier equivalent to `_env_exp` advanced by one sample.
static func _decay_step(rate: float) -> float:
	return exp(-rate / float(MIX_RATE))


## One pole low pass coefficient for a cut off in Hz.
static func _lp_alpha(cutoff_hz: float) -> float:
	var c: float = clampf(cutoff_hz, 15.0, float(MIX_RATE) * 0.45)
	return clampf(1.0 - exp(-TAU * c / float(MIX_RATE)), 0.0, 1.0)


## Adds a low passed noise burst whose cut off glides from `cut_start` to
## `cut_end` over the remaining buffer, with an exponential amplitude decay.
static func _noise_burst(buf: PackedFloat32Array, rng: RandomNumberGenerator,
		amp: float, decay: float, cut_start: float, cut_end: float,
		start_time: float = 0.0, attack: float = 0.0) -> void:
	var n: int = buf.size()
	var i0: int = int(start_time * float(MIX_RATE))
	if i0 >= n or amp <= 0.0:
		return
	var span: float = float(maxi(1, n - i0))
	var a: float = _lp_alpha(cut_start)
	var da: float = (_lp_alpha(cut_end) - a) / span
	var k: float = _decay_step(decay)
	var atk: float = maxf(attack, 0.0) * float(MIX_RATE)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var y: float = 0.0
	var st: int = _seed_of(rng)
	var i: int = i0
	var t: float = 0.0
	while i < n:
		st = (st * 1103515245 + 12345) & 0x7fffffff
		y += a * (float(st) * NOISE_SCALE - 1.0 - y)
		a += da
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += y * e
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## Adds a decaying sine.
static func _tone(buf: PackedFloat32Array, freq: float, amp: float, decay: float,
		start_time: float = 0.0, attack: float = 0.002) -> void:
	var n: int = buf.size()
	var i0: int = int(start_time * float(MIX_RATE))
	if i0 >= n or amp <= 0.0:
		return
	# Exact sine recurrence: sin((n+1)w) = 2cos(w)sin(nw) - sin((n-1)w).
	# One multiply per sample instead of a call into sin().
	var w: float = TAU * freq / float(MIX_RATE)
	var two_cos: float = 2.0 * cos(w)
	var s_prev: float = 0.0
	var s_cur: float = sin(w)
	var k: float = _decay_step(decay)
	var atk: float = maxf(attack, 0.0) * float(MIX_RATE)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var i: int = i0
	var t: float = 0.0
	while i < n:
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += s_prev * e
		var s_next: float = two_cos * s_cur - s_prev
		s_prev = s_cur
		s_cur = s_next
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## Adds a decaying sine whose frequency glides linearly from `f0` to `f1` over
## the remaining buffer.
static func _sweep(buf: PackedFloat32Array, f0: float, f1: float, amp: float,
		decay: float, start_time: float = 0.0, attack: float = 0.002) -> void:
	var n: int = buf.size()
	var i0: int = int(start_time * float(MIX_RATE))
	if i0 >= n or amp <= 0.0:
		return
	var span: float = float(maxi(1, n - i0))
	var inv: float = TAU / float(MIX_RATE)
	var k: float = _decay_step(decay)
	var atk: float = maxf(attack, 0.0) * float(MIX_RATE)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var ph: float = 0.0
	var f: float = f0 * inv
	var df: float = (f1 - f0) * inv / span
	var i: int = i0
	var t: float = 0.0
	while i < n:
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += sin(ph) * e
		ph += f
		f += df
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## In place one pole low pass.
static func _lowpass(buf: PackedFloat32Array, cutoff_hz: float) -> void:
	var a: float = _lp_alpha(cutoff_hz)
	var y: float = 0.0
	var n: int = buf.size()
	for i: int in n:
		y += a * (buf[i] - y)
		buf[i] = y


## In place one pole high pass.
static func _highpass(buf: PackedFloat32Array, cutoff_hz: float) -> void:
	var rc: float = 1.0 / maxf(TAU * cutoff_hz, 0.001)
	var dt: float = 1.0 / float(MIX_RATE)
	var a: float = rc / (rc + dt)
	var y: float = 0.0
	var prev: float = 0.0
	var n: int = buf.size()
	for i: int in n:
		var x: float = buf[i]
		y = a * (y + x - prev)
		prev = x
		buf[i] = y


## Two pole resonator (band pass). Returns a new buffer, leaves `src` untouched.
static func _resonate(src: PackedFloat32Array, freq: float, bandwidth: float,
		gain: float) -> PackedFloat32Array:
	var n: int = src.size()
	var out := PackedFloat32Array()
	out.resize(n)
	var f: float = clampf(freq, 20.0, float(MIX_RATE) * 0.45)
	var r: float = exp(-PI * maxf(bandwidth, 5.0) / float(MIX_RATE))
	var theta: float = TAU * f / float(MIX_RATE)
	var b1: float = 2.0 * r * cos(theta)
	var b2: float = -r * r
	var norm: float = (1.0 - r) * sqrt(maxf(1.0 - 2.0 * r * cos(2.0 * theta) + r * r, 0.0001))
	var a0: float = norm * gain
	var y1: float = 0.0
	var y2: float = 0.0
	for i: int in n:
		var y: float = a0 * src[i] + b1 * y1 + b2 * y2
		y2 = y1
		y1 = y
		out[i] = y
	return out


## Adds `src` scaled by `gain` into `dst`. Both must be the same length.
static func _mix(dst: PackedFloat32Array, src: PackedFloat32Array, gain: float) -> void:
	var n: int = mini(dst.size(), src.size())
	for i: int in n:
		dst[i] += src[i] * gain


## Applies a linear attack and an exponential release over the whole buffer.
static func _shape(buf: PackedFloat32Array, attack: float, decay: float) -> void:
	var n: int = buf.size()
	var atk: float = maxf(attack, 0.0001) * float(MIX_RATE)
	var k: float = _decay_step(decay)
	var env: float = 1.0
	for i: int in n:
		var e: float = env
		var t: float = float(i)
		if t < atk:
			e *= t / atk
		buf[i] *= e
		env *= k


## Gates the buffer into syllables. Segments are (start, end) in seconds, and
## each gets a short ramp so the voice does not click.
static func _syllables(buf: PackedFloat32Array, segments: PackedVector2Array) -> void:
	var n: int = buf.size()
	var gate := PackedFloat32Array()
	gate.resize(n)
	gate.fill(0.0)
	var ramp: int = int(0.014 * float(MIX_RATE))
	for seg: Vector2 in segments:
		var s0: int = clampi(int(seg.x * float(MIX_RATE)), 0, n)
		var s1: int = clampi(int(seg.y * float(MIX_RATE)), 0, n)
		var width: int = s1 - s0
		if width <= 2:
			continue
		var r: int = mini(ramp, width / 2)
		var inv_r: float = 1.0 if r <= 0 else 1.0 / float(r)
		var j: int = s0
		while j < s1:
			var d: int = mini(j - s0, s1 - j)
			var g: float = float(d) * inv_r
			if g > 1.0:
				g = 1.0
			if g > gate[j]:
				gate[j] = g
			j += 1
	for i: int in n:
		buf[i] *= gate[i]


## Pitched impulse train pushed through formant resonators. The base of every
## stylised voice in the game.
static func _voice(seconds: float, f0_start: float, f0_end: float,
		formants: PackedFloat32Array, rng: RandomNumberGenerator,
		breath: float, rough: float) -> PackedFloat32Array:
	var src: PackedFloat32Array = _buf(seconds)
	var n: int = src.size()
	var st: int = _seed_of(rng)
	var ph: float = 0.0
	var jitter: float = 0.0
	var inv: float = 1.0 / float(MIX_RATE)
	var f0: float = f0_start * inv
	var df0: float = (f0_end - f0_start) * inv / float(n)
	var breath_gain: float = breath * 0.22
	var rough_gain: float = rough * 0.35
	for i: int in n:
		st = (st * 1103515245 + 12345) & 0x7fffffff
		var nz: float = float(st) * NOISE_SCALE - 1.0
		jitter += (nz - jitter) * 0.06
		var inc: float = f0 * (1.0 + rough_gain * jitter)
		ph += inc
		f0 += df0
		# The pulse train is made zero mean by subtracting its own duty cycle,
		# otherwise the formant filters pass a DC offset down the chain.
		var v: float = -inc
		if ph >= 1.0:
			ph -= 1.0
			v += 1.0
		src[i] = v + nz * breath_gain
	var out: PackedFloat32Array = _buf(seconds)
	var count: int = formants.size()
	for k: int in count:
		var g: float = 1.0 / (1.0 + float(k) * 0.85)
		_mix(out, _resonate(src, formants[k], 85.0 + float(k) * 80.0, g), 1.0)
	return out


## Short metallic clack used by every weapon handling sound.
static func _metal_click(buf: PackedFloat32Array, at: float, amp: float,
		freq: float, rng: RandomNumberGenerator) -> void:
	_noise_burst(buf, rng, amp * 0.75, 230.0, 7500.0, 1800.0, at, 0.0004)
	_tone(buf, freq, amp * 0.42, 100.0, at, 0.0006)
	_tone(buf, freq * 1.83, amp * 0.22, 130.0, at, 0.0006)
	_tone(buf, freq * 0.51, amp * 0.18, 80.0, at, 0.0008)


## A single bounce of a brass case on the ground.
static func _brass_tick(buf: PackedFloat32Array, at: float, amp: float,
		freq: float, rng: RandomNumberGenerator) -> void:
	_noise_burst(buf, rng, amp * 0.35, 420.0, 11000.0, 4000.0, at, 0.0003)
	_tone(buf, freq, amp * 0.55, 46.0, at, 0.0004)
	_tone(buf, freq * 1.62, amp * 0.30, 58.0, at, 0.0004)
	_tone(buf, freq * 2.41, amp * 0.14, 72.0, at, 0.0004)


## Bell like note with a couple of harmonics, for the interface jingles.
static func _chime(buf: PackedFloat32Array, freq: float, at: float, amp: float,
		decay: float) -> void:
	_tone(buf, freq, amp, decay, at, 0.004)
	_tone(buf, freq * 2.0, amp * 0.34, decay * 1.45, at, 0.004)
	_tone(buf, freq * 3.01, amp * 0.15, decay * 2.0, at, 0.004)


# ---------------------------------------------------------------------------
# Finishing
# ---------------------------------------------------------------------------

## Scales the buffer so its loudest sample reaches `peak`.
static func _normalize(buf: PackedFloat32Array, peak: float) -> void:
	var n: int = buf.size()
	var top: float = 0.0
	for i: int in n:
		var v: float = buf[i]
		if v < 0.0:
			v = -v
		if v > top:
			top = v
	if top < 0.000001:
		return
	var g: float = peak / top
	for i: int in n:
		buf[i] *= g


## Short linear fade on the tail so a one shot never ends on a click.
static func _fade_out(buf: PackedFloat32Array) -> void:
	var n: int = buf.size()
	var f: int = mini(FADE_SAMPLES, n)
	if f <= 1:
		return
	for i: int in f:
		buf[n - f + i] *= 1.0 - float(i) / float(f - 1)


## Makes the buffer seamlessly loopable. The last `fade_seconds` are treated as
## the pre roll of the next cycle and blended into the head, then dropped, so
## the final sample flows straight back into the first one.
static func _loopify(buf: PackedFloat32Array, fade_seconds: float) -> void:
	var n: int = buf.size()
	var f: int = mini(int(fade_seconds * float(MIX_RATE)), n / 3)
	if f <= 2:
		return
	var body: int = n - f
	for i: int in f:
		var w: float = float(i) / float(f - 1)
		buf[i] = buf[i] * w + buf[body + i] * (1.0 - w)
	buf.resize(body)


## Packs float samples into signed 16 bit little endian PCM.
static func _to_stream(buf: PackedFloat32Array, looping: bool) -> AudioStreamWAV:
	var n: int = buf.size()
	var bytes := PackedByteArray()
	bytes.resize(n * 2)
	var j: int = 0
	for i: int in n:
		var v: float = buf[i] * 32767.0
		if v > 32767.0:
			v = 32767.0
		elif v < -32767.0:
			v = -32767.0
		var s: int = int(v)
		if s < 0:
			s += 65536
		bytes[j] = s & 255
		bytes[j + 1] = (s >> 8) & 255
		j += 2
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = MIX_RATE
	stream.stereo = false
	stream.data = bytes
	if looping:
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = n
	else:
		stream.loop_mode = AudioStreamWAV.LOOP_DISABLED
	return stream
