class_name Weather
extends Node3D

## Rain, fog and wind over the Normandy pocket.
##
## The node owns a single rain emitter that is parked above the player and one
## additive layer of fog on top of whatever `SkyController` already computed.
##
## Ordering matters: `SkyController` rewrites `Environment.fog_density` and the
## fog range every frame from the time of day. Weather must therefore run AFTER
## it and only ever THICKEN what the sky set, never replace it. That is what
## `process_priority` is for, on top of the scene tree order (Sky is declared
## before Weather in `scenes/main.tscn`).

signal weather_changed(kind: int)

const CLEAR := 0
const OVERCAST := 1
const RAIN := 2
const FOG := 3
const STORM := 4
const SNOW := 5
const KIND_COUNT := 6

## Height of the rain box above the player, in metres.
const RAIN_ALTITUDE := 15.0
## Half extents of the rain emission box, in metres.
const RAIN_EXTENT := 24.0
## Number of raindrops allocated. The visible amount is driven by `amount_ratio`
## so that changing the weather never restarts the emitter.
const RAIN_BUDGET := 2600
## Snowflakes allocated. Far more than raindrops despite the smaller box: a
## flake crosses the frame in ten seconds instead of one, so the eye has time to
## count them, and a thin scatter reads as dust rather than as snowfall.
const SNOW_BUDGET := 7000
## Half extents of the snow emission box. Tighter than the rain box so the same
## budget buys four times the density in the volume the player actually sees.
const SNOW_EXTENT := 17.0
## Centre of the snow column above the player, in metres.
##
## Snow is emitted throughout a tall column, not off a thin plane the way rain
## is. Rain falls at 25 m/s and crosses the frame before the eye can find where
## it started; a flake takes ten seconds, which is long enough to see that it
## has a ceiling. Emitting off a plane at 9 m drew a hard diagonal edge across
## the sky wherever the box ended. A column has no ceiling to see.
const SNOW_CENTRE := 3.0
## Half height of that column. Covers roughly -9 m to +15 m around the player.
const SNOW_COLUMN := 12.0
## Peak alpha at the centre of a flake. Below 1 on purpose: a flake you can see
## a little of the world through layers into haze, and a screen full of opaque
## white dots reads as static rather than as weather.
##
## Carried by the particle colour ALONE. Godot multiplies the process material
## colour, the material albedo alpha and the texture alpha together, so setting
## a value below 1 in more than one of the three cubes the transparency and the
## snow vanishes; the other two are pinned at 1.
const FLAKE_PEAK_ALPHA := 0.85
## How many in-game hours an explicit `set_weather()` survives the hourly roll.
const MANUAL_HOURS := 3

# --- Local climate -----------------------------------------------------------

## Snow over Normandy in the summer of 1942 is an anachronism. It is enabled
## because the sky over the northern ridge is worth the liberty, and it is a
## single constant so the campaign can be put back in season without touching
## anything else: set this to false and the ridge gets cold rain instead.
const ALLOW_SNOW := true
## A site standing this high above sea level carries snow. The pocket tops out
## around 45 m (24 m of base relief plus the 25 m ridge in the north), so this
## only ever catches the wooded high ground.
const SNOW_ALTITUDE := 30.0
## Above this the ground is exposed enough to draw squalls off the sea.
const HIGH_GROUND := 26.0
## At or below this a site sits in the bottom of the valley, where mist collects.
## The pocket runs from about -1.5 m on the coastal flats to 42 m on the ridge.
const LOW_GROUND := 10.0
## Where the biome vote around a site is taken, as a multiple of its radius.
## Outside `Layout.SITE_OUTER` (1.35), so past anything the site flattened.
const BIOME_RING := 1.8
## Points on that ring. Eight is enough to tell a marsh from a wood and cheap
## enough to run for all twenty two sites in one frame at startup.
const BIOME_SAMPLES := 8
## Chance that an hourly roll inside a site's region keeps that site's signature
## weather rather than falling back to the campaign-wide roll. Below 1.0 so a
## place has a character without being frozen into a single sky forever.
const CLIMATE_BIAS := 0.62
## Seconds a local climate takes to move in when the player enters its region.
## Long: weather that snaps on a boundary reads as a bug, not as geography.
const CLIMATE_TRANSITION := 22.0
## Cold hue snow drags the fog towards. Applied at constant brightness, so that
## tinting the fog never lights up the night.
const COLD_TINT := Color(0.84, 0.90, 1.0)

var kind: int = CLEAR
## 0..1, drives sound and visibility.
var intensity: float = 0.0

var _sky: SkyController = null
var _follow: Node3D = null
var _env: Environment = null
var _rain: GPUParticles3D = null
var _rain_material: ParticleProcessMaterial = null
var _snow: GPUParticles3D = null
var _snow_material: ParticleProcessMaterial = null

## Built on first use and shared by every Weather node.
static var _flake_cache: ImageTexture = null

## Signature weather of the place the player is standing in, or -1 out in the
## open where only the campaign roll applies. Written by `set_climate()`.
var _climate: int = -1

## Blend state between the previous mood and the requested one.
var _from: PackedFloat32Array = PackedFloat32Array()
var _to: PackedFloat32Array = PackedFloat32Array()
var _blend: float = 1.0
var _blend_speed: float = 0.0
var _prev_kind: int = CLEAR

var _wind := Vector3(0.6, 0.0, 0.35)
var _wind_phase: float = 0.0
var _thunder_timer: float = 12.0
var _gust_timer: float = 7.0
var _last_hour: int = -1
var _auto: bool = true
## Number of hourly rolls still owed to an explicit `set_weather()` call.
var _manual_skip: int = 0
var _rain_y: float = 0.0
var _ready_ok: bool = false

## Index layout of the blended parameter vectors.
const _P_OVERCAST := 0
const _P_RAIN := 1
const _P_FOG_OPACITY := 2
const _P_FOG_RANGE := 3
const _P_WIND := 4
const _P_SIGHT := 5
const _P_INTENSITY := 6
const _P_SNOW := 7
const _P_COLD := 8
const _P_COUNT := 9


func _ready() -> void:
	# Runs after SkyController, which owns the baseline fog.
	process_priority = 20
	set_process(true)


func setup(sky: SkyController, follow: Node3D) -> void:
	_sky = sky
	_follow = follow
	_env = _find_environment()
	if _env == null:
		push_warning("Weather.setup: no WorldEnvironment found, fog will not be driven.")
	_build_rain()
	_build_snow()
	_from = _params_for(CLEAR)
	_to = _params_for(CLEAR)
	_blend = 1.0
	_blend_speed = 0.0
	kind = CLEAR
	_prev_kind = CLEAR
	_ready_ok = true
	_apply(_to)

	# Open on the sky the seed prescribes for the current hour instead of always
	# starting clear and sliding into the real weather a minute later.
	if _sky != null:
		var hour: int = int(_sky.time_of_day * 24.0) % 24
		_last_hour = hour
		_set_weather(roll(_campaign_seed(), hour), 0.05)


func set_weather(new_kind: int, transition: float = 8.0) -> void:
	# An explicit call wins over the hourly roll for the next few in-game hours,
	# otherwise a mission that forces a storm would be wiped out by the very next
	# turn of the clock.
	_manual_skip = MANUAL_HOURS
	_set_weather(new_kind, transition)


## Same thing without claiming manual control. Used by the hourly roll.
func _set_weather(new_kind: int, transition: float) -> void:
	var target: int = clampi(new_kind, 0, KIND_COUNT - 1)
	if target == kind and _blend >= 1.0:
		return
	_from = _current_params()
	_to = _params_for(target)
	_prev_kind = kind
	kind = target
	_blend = 0.0
	_blend_speed = 1.0 / maxf(transition, 0.05)
	weather_changed.emit(kind)


## Hands the weather the signature sky of the place the player just walked into,
## or -1 once he is back out in the open fields.
##
## The climate takes over at once so that crossing into the marshes is a thing
## you SEE happen, and it then biases the hourly roll for as long as the player
## stays, which is what stops a place from being locked to one sky forever.
## An explicit `set_weather()` still wins for its few hours: a scripted storm is
## not something a change of scenery should quietly cancel.
func set_climate(new_climate: int, transition: float = CLIMATE_TRANSITION) -> void:
	var target: int = new_climate
	if target < 0 or target >= KIND_COUNT:
		target = -1
	if target == _climate:
		return
	_climate = target
	if _manual_skip > 0:
		return
	if target >= 0:
		_set_weather(target, transition)
		return
	# Out in the open again: hand the sky back to the campaign roll rather than
	# leaving the last village's weather trailing behind the player.
	var hour: int = _hour()
	if hour >= 0:
		_set_weather(roll(_campaign_seed(), hour), transition)


## The climate currently in force, or -1 for none.
func climate() -> int:
	return _climate


## Opens a fresh campaign under mist, whatever the seed rolled for that hour.
##
## The drop happens at first light and the player is meant to reach his first
## objective unseen; the sky says so before the briefing does. It lasts
## `MANUAL_HOURS` in-game hours and then the weather resumes on its own.
func begin_opening_fog() -> void:
	set_weather(FOG, 2.5)


## Visibility multiplier for AI sight range, 1.0 clear down to 0.35 in a storm.
func sight_factor() -> float:
	if _from.size() < _P_COUNT or _to.size() < _P_COUNT:
		return 1.0
	var t: float = _blend * _blend * (3.0 - 2.0 * _blend)
	return clampf(lerpf(_from[_P_SIGHT], _to[_P_SIGHT], t), 0.30, 1.0)


func kind_name() -> String:
	return name_of(kind)


## Display name of any weather kind. Static so the table can be addressed
## without a live Weather node, which is what makes it testable.
static func name_of(k: int) -> String:
	match k:
		CLEAR: return "Ciel degage"
		OVERCAST: return "Couvert"
		RAIN: return "Pluie"
		FOG: return "Brouillard"
		STORM: return "Orage"
		SNOW: return "Neige"
	return "Ciel degage"


## Deterministic weather roll for a given world seed and in-game hour.
##
## Pure function of its two arguments: the same campaign always gets the same
## sky at the same hour, whatever the player did in between. The distribution is
## Normandy in late summer, so overcast dominates and mist belongs to the early
## morning.
##
## Storms are weighted towards the afternoon by the 13h-20h rule but are not
## confined to it: the ordinary daytime tail can still break one in the morning.
## The night band is the only hard guarantee, and it excludes both storm and
## fog. Snow never comes out of this roll at all; it reaches the sky only
## through `climate_for()`, so that it stays a property of a place.
static func roll(world_seed: int, hour: int) -> int:
	var h: int = posmod(hour, 24)
	var a: float = _hash01(world_seed, h * 17 + 3)
	var b: float = _hash01(world_seed + 91711, h * 5 + 41)

	# Dawn mist over the marshes.
	if h >= 4 and h <= 8 and a < 0.28:
		return FOG
	# Afternoon thunderstorm.
	if h >= 13 and h <= 20 and b > 0.93:
		return STORM
	# Nights are calmer, the wind drops.
	if h >= 22 or h <= 3:
		if a < 0.45:
			return CLEAR
		if a < 0.86:
			return OVERCAST
		return RAIN

	if a < 0.32:
		return CLEAR
	if a < 0.71:
		return OVERCAST
	if a < 0.93:
		return RAIN
	return STORM


## Same roll, leaning towards the signature weather of wherever the player is.
##
## `climate` is a weather kind or -1 for open country. The bias is a coin flip
## per hour rather than a certainty: the marshes are foggy, they are not foggy
## every single hour of the campaign. Note that `roll()` alone never produces
## SNOW, so snow only ever reaches the sky through a place that carries it.
static func roll_at(world_seed: int, hour: int, climate: int) -> int:
	if climate < 0 or climate >= KIND_COUNT:
		return roll(world_seed, hour)
	var c: float = _hash01(world_seed + 20443, posmod(hour, 24) * 13 + 5)
	if c < CLIMATE_BIAS:
		return climate
	return roll(world_seed, hour)


## Dominant natural biome in the ring around a site.
##
## Sampling the biome AT a site centre is useless: every site is flattened and
## carries a road or village surface there, so the probe comes back B_ROAD for
## all twenty two of them and the marshes never get their mist. What decides the
## weather over a place is the country it sits in, so this reads a ring outside
## the flattened footprint and drops the two man-made surfaces from the vote.
static func site_biome(field: Heightfield, center: Vector2, radius: float) -> int:
	if field == null:
		return Heightfield.B_MEADOW
	var reach: float = maxf(radius, 20.0) * BIOME_RING
	var tally := {}
	var best: int = Heightfield.B_MEADOW
	var best_count: int = 0
	for i in BIOME_SAMPLES:
		var a: float = TAU * float(i) / float(BIOME_SAMPLES)
		var b: int = field.biome_at(center.x + cos(a) * reach, center.y + sin(a) * reach)
		if b == Heightfield.B_ROAD or b == Heightfield.B_VILLAGE:
			continue
		var n: int = int(tally.get(b, 0)) + 1
		tally[b] = n
		if n > best_count:
			best_count = n
			best = b
	return best


## Signature weather of one site, read off the country it stands in.
##
## Pure function of its arguments, so a given place keeps the same character for
## the whole campaign and the whole thing is testable without a world. `biome`
## is a `Heightfield.B_*` value, normally the one `site_biome()` voted for, and
## `ground` the height of the site in metres.
##
## The mapping is geography, not decoration: standing water breeds mist, the
## bare high ground in the north is cold and exposed, woods hold damp, and the
## open farmland is left to the ordinary Normandy mixture.
static func climate_for(biome: int, ground: float, world_seed: int, site_id: int) -> int:
	var h: float = _hash01(world_seed + 4409, site_id * 31 + 7)

	if ground >= SNOW_ALTITUDE:
		# Cold rain when the campaign is kept strictly in season.
		return SNOW if ALLOW_SNOW else RAIN

	match biome:
		Heightfield.B_MARSH, Heightfield.B_WATER:
			return FOG
		Heightfield.B_ROCK:
			return SNOW if ALLOW_SNOW else STORM

	# Mist pools in the bottoms. Without this rule fog reaches the map only
	# through the marsh biome, which the Poisson placement does not always put a
	# site inside, and a whole campaign can end up without a single foggy place.
	if ground <= LOW_GROUND:
		return FOG

	if biome == Heightfield.B_FOREST:
		return FOG if h < 0.45 else OVERCAST

	if ground >= HIGH_GROUND:
		return STORM if h < 0.45 else RAIN

	if h < 0.28:
		return RAIN
	if h < 0.54:
		return OVERCAST
	if h < 0.86:
		return CLEAR
	return STORM


# ---------------------------------------------------------------------------
# Per frame
# ---------------------------------------------------------------------------

func _process(delta: float) -> void:
	if not _ready_ok:
		return

	if _blend < 1.0:
		_blend = minf(_blend + _blend_speed * delta, 1.0)

	var p: PackedFloat32Array = _current_params()
	_apply(p)
	_track_player(delta)
	_tick_auto()
	_tick_sound(delta, p)


func _current_params() -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(_P_COUNT)
	if _from.size() < _P_COUNT or _to.size() < _P_COUNT:
		return _params_for(CLEAR)
	# Smoothstep the blend so a weather change eases in and out instead of
	# ramping linearly, which reads as a lighting glitch.
	var t: float = _blend * _blend * (3.0 - 2.0 * _blend)
	for i in _P_COUNT:
		out[i] = lerpf(_from[i], _to[i], t)
	return out


func _apply(p: PackedFloat32Array) -> void:
	intensity = clampf(p[_P_INTENSITY], 0.0, 1.0)

	if _sky != null:
		_sky.set_overcast(p[_P_OVERCAST])

	if _env != null:
		# Only ever thicken what the sky already decided. Overwriting it would
		# undo the day / night fog colour and range.
		_env.fog_density = maxf(_env.fog_density, p[_P_FOG_OPACITY])
		var far: float = _env.fog_depth_end * p[_P_FOG_RANGE]
		_env.fog_depth_end = maxf(far, 45.0)
		# Thick weather starts biting close to the eye; a clear day's haze only
		# shows up in the distance. Fixed at 0.16 the near field stayed crisp
		# inside a fog bank, which read as a short draw distance, not as fog.
		_env.fog_depth_begin = _env.fog_depth_end * lerpf(0.16, 0.04, intensity)
		# Rain and mist wash the sun scatter out of the fog. Written with minf
		# rather than a multiply so that reapplying it every frame converges
		# instead of decaying the value to zero.
		_env.fog_sun_scatter = minf(_env.fog_sun_scatter, 0.14 * (1.0 - intensity * 0.6))
		_apply_cold(clampf(p[_P_COLD], 0.0, 1.0))

	var rain_amount: float = clampf(p[_P_RAIN], 0.0, 1.0)
	if _rain != null:
		_rain.amount_ratio = rain_amount
		_rain.emitting = rain_amount > 0.01
	if _rain_material != null and rain_amount > 0.01:
		var strength: float = p[_P_WIND]
		var slant: Vector3 = _wind * strength * 6.0
		_rain_material.gravity = Vector3(slant.x, -26.0 - strength * 10.0, slant.z)
		_rain_material.initial_velocity_min = 12.0 + strength * 5.0
		_rain_material.initial_velocity_max = 17.0 + strength * 7.0

	var snow_amount: float = clampf(p[_P_SNOW], 0.0, 1.0)
	if _snow != null:
		_snow.amount_ratio = snow_amount
		_snow.emitting = snow_amount > 0.01
	if _snow_material != null and snow_amount > 0.01:
		# A flake weighs nothing: the wind moves it far more than gravity does,
		# which is the whole difference between snow and rain on screen.
		var drift: float = p[_P_WIND]
		var push: Vector3 = _wind * (0.6 + drift * 2.2)
		_snow_material.gravity = Vector3(push.x, -1.2 - drift * 0.5, push.z)


## Drags the fog towards a cold hue at constant brightness.
##
## `SkyController` rewrites `fog_light_color` from the time of day every frame
## and Weather runs after it, so this reads a fresh value each time and never
## compounds. Scaling `COLD_TINT` by the current peak channel keeps the night
## dark: tinting towards a literal pale colour would light the fog up at 3 am.
func _apply_cold(cold: float) -> void:
	if cold <= 0.001:
		return
	var base: Color = _env.fog_light_color
	var level: float = maxf(base.r, maxf(base.g, base.b))
	var cold_col := Color(COLD_TINT.r * level, COLD_TINT.g * level, COLD_TINT.b * level, base.a)
	_env.fog_light_color = base.lerp(cold_col, cold * 0.8)


func _track_player(delta: float) -> void:
	if _follow == null or not is_instance_valid(_follow) or not _follow.is_inside_tree():
		return
	var target: Vector3 = _follow.global_position
	# The contract asks for XZ tracking. The vertical is smoothed rather than
	# snapped so that climbing a hill does not teleport the emission plane, and
	# because the particles live in global space the box can move freely without
	# dragging the drops already in the air.
	_rain_y = lerpf(_rain_y, target.y + RAIN_ALTITUDE, clampf(delta * 1.6, 0.0, 1.0))
	if _rain != null and _rain.is_inside_tree():
		_rain.global_position = Vector3(target.x, _rain_y, target.z)
	if _snow != null and _snow.is_inside_tree():
		# Same smoothed height as the rain, brought down to the column centre.
		_snow.global_position = Vector3(
				target.x, _rain_y - (RAIN_ALTITUDE - SNOW_CENTRE), target.z)

	# Slow wind rotation so the rain never falls at exactly the same angle.
	_wind_phase += delta * 0.07
	_wind = Vector3(cos(_wind_phase), 0.0, sin(_wind_phase * 0.83)).normalized()


func _tick_auto() -> void:
	if not _auto or _sky == null:
		return
	var hour: int = int(_sky.time_of_day * 24.0) % 24
	if hour == _last_hour:
		return
	_last_hour = hour
	if _manual_skip > 0:
		_manual_skip -= 1
		# The hold has just expired over a place with its own weather. Give that
		# place its sky back now rather than waiting for the next hour to turn.
		if _manual_skip == 0 and _climate >= 0:
			_set_weather(_climate, CLIMATE_TRANSITION)
		return
	_set_weather(roll_at(_campaign_seed(), hour, _climate), 14.0)


func _tick_sound(delta: float, p: PackedFloat32Array) -> void:
	var sfx: Node = _sfx()
	if sfx == null:
		return

	_gust_timer -= delta
	if _gust_timer <= 0.0:
		_gust_timer = randf_range(8.0, 17.0)
		if intensity > 0.20:
			sfx.call("play", "wind", linear_to_db(clampf(intensity, 0.05, 1.0)) - 4.0, randf_range(0.85, 1.15))

	if kind != STORM or p[_P_RAIN] < 0.4:
		return
	_thunder_timer -= delta
	if _thunder_timer <= 0.0:
		_thunder_timer = randf_range(9.0, 26.0)
		sfx.call("play", "explosion_far", -5.0, randf_range(0.55, 0.78))


# ---------------------------------------------------------------------------
# Weather table
# ---------------------------------------------------------------------------

## Numeric mood of one weather kind. Everything is blended between two of these
## vectors, which is what makes a transition a single lerp instead of a pile of
## special cases.
static func _params_for(k: int) -> PackedFloat32Array:
	var p := PackedFloat32Array()
	p.resize(_P_COUNT)
	match k:
		CLEAR:
			p[_P_OVERCAST] = 0.08
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.0
			p[_P_FOG_RANGE] = 1.0
			p[_P_WIND] = 0.15
			p[_P_SIGHT] = 1.0
			p[_P_INTENSITY] = 0.0
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.0
		OVERCAST:
			p[_P_OVERCAST] = 0.88
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.60
			p[_P_FOG_RANGE] = 0.80
			p[_P_WIND] = 0.35
			p[_P_SIGHT] = 0.88
			p[_P_INTENSITY] = 0.30
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.06
		RAIN:
			p[_P_OVERCAST] = 0.95
			p[_P_RAIN] = 0.55
			p[_P_FOG_OPACITY] = 0.82
			p[_P_FOG_RANGE] = 0.45
			p[_P_WIND] = 0.55
			p[_P_SIGHT] = 0.68
			p[_P_INTENSITY] = 0.65
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.18
		FOG:
			# Opacity has to clear what the sky already put down on its own. The
			# baseline runs 0.42 clear to 0.78 overcast, so the old 0.55 here was
			# below it and the `maxf` in `_apply` discarded it outright: a fog
			# bank read exactly like a plain overcast afternoon.
			p[_P_OVERCAST] = 0.62
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.97
			p[_P_FOG_RANGE] = 0.12
			p[_P_WIND] = 0.06
			p[_P_SIGHT] = 0.45
			p[_P_INTENSITY] = 0.55
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.10
		STORM:
			p[_P_OVERCAST] = 1.0
			p[_P_RAIN] = 1.0
			p[_P_FOG_OPACITY] = 0.90
			p[_P_FOG_RANGE] = 0.30
			p[_P_WIND] = 1.0
			p[_P_SIGHT] = 0.35
			p[_P_INTENSITY] = 1.0
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.22
		SNOW:
			# Snow does not blind like rain does, it whitens. The sight penalty
			# sits between fog and rain, and the wind stays low so the flakes
			# hang in the air instead of being driven sideways.
			p[_P_OVERCAST] = 0.92
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.93
			p[_P_FOG_RANGE] = 0.24
			p[_P_WIND] = 0.24
			p[_P_SIGHT] = 0.55
			p[_P_INTENSITY] = 0.70
			p[_P_SNOW] = 0.80
			p[_P_COLD] = 1.0
		_:
			p[_P_OVERCAST] = 0.08
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.0
			p[_P_FOG_RANGE] = 1.0
			p[_P_WIND] = 0.15
			p[_P_SIGHT] = 1.0
			p[_P_INTENSITY] = 0.0
			p[_P_SNOW] = 0.0
			p[_P_COLD] = 0.0
	return p


# ---------------------------------------------------------------------------
# Rain emitter
# ---------------------------------------------------------------------------

func _build_rain() -> void:
	if _rain != null:
		return

	var quad := QuadMesh.new()
	# Long and thin: a raindrop seen at 18 m/s is a streak, never a dot.
	quad.size = Vector2(0.035, 0.85)
	quad.orientation = PlaneMesh.FACE_Z

	var draw_mat := StandardMaterial3D.new()
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	draw_mat.albedo_color = Color(0.52, 0.58, 0.64, 0.32)
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	draw_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	draw_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	draw_mat.vertex_color_use_as_albedo = true
	draw_mat.no_depth_test = false
	# FIXED_Y keeps the streak upright while still turning to face the camera.
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	draw_mat.billboard_keep_scale = true
	draw_mat.disable_receive_shadows = true
	draw_mat.render_priority = 1
	quad.material = draw_mat

	_rain_material = ParticleProcessMaterial.new()
	_rain_material.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	_rain_material.emission_box_extents = Vector3(RAIN_EXTENT, 0.5, RAIN_EXTENT)
	_rain_material.direction = Vector3(0.0, -1.0, 0.0)
	_rain_material.spread = 3.0
	_rain_material.initial_velocity_min = 13.0
	_rain_material.initial_velocity_max = 19.0
	_rain_material.gravity = Vector3(2.0, -28.0, 1.0)
	_rain_material.scale_min = 0.7
	_rain_material.scale_max = 1.5
	_rain_material.color = Color(0.55, 0.60, 0.66, 0.35)
	_rain_material.damping_min = 0.0
	_rain_material.damping_max = 0.0

	_rain = GPUParticles3D.new()
	_rain.name = "Rain"
	_rain.process_material = _rain_material
	_rain.draw_pass_1 = quad
	_rain.amount = RAIN_BUDGET
	_rain.lifetime = 1.7
	_rain.preprocess = 1.5
	_rain.explosiveness = 0.0
	_rain.randomness = 0.35
	_rain.fixed_fps = 0
	_rain.interpolate = true
	_rain.local_coords = false
	_rain.amount_ratio = 0.0
	_rain.emitting = false
	# Without an explicit AABB the emitter is culled as soon as its origin
	# leaves the frustum, which happens constantly since it sits overhead.
	_rain.visibility_aabb = AABB(
		Vector3(-RAIN_EXTENT - 6.0, -46.0, -RAIN_EXTENT - 6.0),
		Vector3(RAIN_EXTENT * 2.0 + 12.0, 60.0, RAIN_EXTENT * 2.0 + 12.0))
	add_child(_rain)

	if _follow != null and is_instance_valid(_follow) and _follow.is_inside_tree() and _rain.is_inside_tree():
		var here: Vector3 = _follow.global_position
		_rain_y = here.y + RAIN_ALTITUDE
		_rain.global_position = Vector3(here.x, _rain_y, here.z)


# ---------------------------------------------------------------------------
# Snow emitter
# ---------------------------------------------------------------------------

## Separate emitter rather than a mode of the rain one.
##
## Rain and snow disagree on everything that costs a restart to change: mesh,
## billboard mode, lifetime, particle count. Swapping them on one emitter would
## reset it mid-transition and drop every drop already in the air, so the two
## live side by side and only one of them is ever emitting.
func _build_snow() -> void:
	if _snow != null:
		return

	var quad := QuadMesh.new()
	# A flake at 1 m/s is a soft blob, not a streak. Wider than a raindrop
	# because most of the quad is taken up by the falloff, not by the flake,
	# but kept small: the emission column contains the camera, so whatever size
	# is chosen here will sometimes be seen from thirty centimetres away.
	quad.size = Vector2(0.10, 0.10)
	quad.orientation = PlaneMesh.FACE_Z

	var draw_mat := StandardMaterial3D.new()
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	# Alpha pinned at 1 here: see FLAKE_PEAK_ALPHA for why only one of the three
	# alpha sources may be below full.
	draw_mat.albedo_color = Color(0.94, 0.96, 1.0, 1.0)
	# An untextured quad is a square, and a square the size of a snowflake reads
	# as exactly that up close. The round falloff below is what makes it a flake.
	draw_mat.albedo_texture = _flake_texture()
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	draw_mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	draw_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	draw_mat.vertex_color_use_as_albedo = true
	# Full billboard, unlike the rain: a flake has no up.
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	draw_mat.billboard_keep_scale = true
	draw_mat.disable_receive_shadows = true
	draw_mat.render_priority = 1
	# The emission column contains the camera, so flakes pass within centimetres
	# of the eye and one of them fills a quarter of the screen as a white blob.
	# Fading them in over the first couple of metres removes that without
	# touching anything the player is actually looking at.
	draw_mat.distance_fade_mode = BaseMaterial3D.DISTANCE_FADE_PIXEL_ALPHA
	draw_mat.distance_fade_min_distance = 0.6
	draw_mat.distance_fade_max_distance = 2.6
	quad.material = draw_mat

	_snow_material = ParticleProcessMaterial.new()
	_snow_material.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	_snow_material.emission_box_extents = Vector3(SNOW_EXTENT, SNOW_COLUMN, SNOW_EXTENT)
	_snow_material.direction = Vector3(0.0, -1.0, 0.0)
	# Wide spread: a flake leaves the cloud in whatever direction the air took it.
	_snow_material.spread = 42.0
	_snow_material.initial_velocity_min = 0.15
	_snow_material.initial_velocity_max = 0.75
	_snow_material.gravity = Vector3(0.5, -1.2, 0.3)
	# Real snow reaches a terminal velocity of about 1 m/s and stays there, it
	# does not keep accelerating like a raindrop. Light gravity fought by heavy
	# damping settles at roughly g/damping, so this band lands between 1.0 and
	# 2.0 m/s and, crucially, differs from one flake to the next.
	_snow_material.damping_min = 0.6
	_snow_material.damping_max = 1.2
	_snow_material.scale_min = 0.5
	_snow_material.scale_max = 1.35
	_snow_material.color = Color(0.95, 0.97, 1.0, FLAKE_PEAK_ALPHA)
	# Turbulence is what sells snow: without it flakes fall on rails and read as
	# white rain. A coarse noise scale gives long lazy sway rather than jitter,
	# and animating it stops the whole cloud drifting as one block.
	_snow_material.turbulence_enabled = true
	_snow_material.turbulence_noise_strength = 1.15
	_snow_material.turbulence_noise_scale = 1.3
	_snow_material.turbulence_noise_speed = Vector3(0.12, 0.05, 0.09)
	_snow_material.turbulence_influence_min = 0.35
	_snow_material.turbulence_influence_max = 0.85

	_snow = GPUParticles3D.new()
	_snow.name = "Snow"
	_snow.process_material = _snow_material
	_snow.draw_pass_1 = quad
	_snow.amount = SNOW_BUDGET
	# About 1.4 m/s over 12 s is 17 m, which carries a flake from the top of the
	# column to below the player's feet. Kept no longer than that because a
	# flake spawned near the bottom is out of sight for the rest of its life and
	# every one of those is budget spent on nothing.
	#
	# Preprocess fills the column before the first visible frame, so a change to
	# snow never opens on an empty sky that fills in from the top.
	_snow.lifetime = 12.0
	_snow.preprocess = 11.0
	_snow.explosiveness = 0.0
	_snow.randomness = 0.5
	_snow.fixed_fps = 0
	_snow.interpolate = true
	_snow.local_coords = false
	_snow.amount_ratio = 0.0
	_snow.emitting = false
	# Same reason as the rain: an overhead emitter is culled the moment its
	# origin leaves the frustum unless the AABB is spelled out.
	_snow.visibility_aabb = AABB(
		Vector3(-SNOW_EXTENT - 14.0, -SNOW_COLUMN - 24.0, -SNOW_EXTENT - 14.0),
		Vector3(SNOW_EXTENT * 2.0 + 28.0, SNOW_COLUMN * 2.0 + 36.0, SNOW_EXTENT * 2.0 + 28.0))
	add_child(_snow)

	if _follow != null and is_instance_valid(_follow) and _follow.is_inside_tree() and _snow.is_inside_tree():
		var here: Vector3 = _follow.global_position
		_snow.global_position = Vector3(here.x, here.y + SNOW_CENTRE, here.z)


## Soft round flake, generated once and shared by every particle.
##
## Built rather than shipped, like every other texture the game falls back on.
## Three things make it read as snow instead of a white dot: the alpha falls off
## over most of the radius so the edge never draws a hard rim, the outline is
## slightly lumpy rather than a perfect circle, and the whole thing peaks below
## full opacity so flakes layer into a haze instead of stacking into white
## paint.
static func _flake_texture() -> ImageTexture:
	if _flake_cache != null:
		return _flake_cache
	var size := 32
	var image := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var half := float(size) * 0.5
	for y in size:
		for x in size:
			var dx: float = (float(x) + 0.5 - half) / half
			var dy: float = (float(y) + 0.5 - half) / half
			var r: float = sqrt(dx * dx + dy * dy)
			# Lumpy outline, but only just: at 0.14 the three lobes were deep
			# enough to read as a notch and every flake near the camera looked
			# like a heart. Enough to break the perfect circle, no more.
			var a: float = atan2(dy, dx)
			r *= 1.0 + 0.055 * sin(a * 3.0 + 0.7) + 0.03 * sin(a * 5.0 - 1.9)
			# Gentle falloff over the whole disc. A steeper curve leaves only a
			# hard pinpoint core visible and the flake disappears against
			# anything but the sky; `smoothstep` alone leaves a visible edge.
			var alpha: float = pow(clampf(1.0 - r, 0.0, 1.0), 1.5)
			image.set_pixel(x, y, Color(1.0, 1.0, 1.0, alpha))
	image.generate_mipmaps()
	_flake_cache = ImageTexture.create_from_image(image)
	return _flake_cache


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

## Current in-game hour, or -1 when there is no sky to ask.
func _hour() -> int:
	if _sky == null:
		return -1
	return int(_sky.time_of_day * 24.0) % 24

## Walks the tree looking for the WorldEnvironment. Weather is handed a
## SkyController, not the environment, so it has to find it on its own.
func _find_environment() -> Environment:
	if not is_inside_tree():
		return null
	var tree := get_tree()
	if tree == null:
		return null
	var root: Node = tree.current_scene
	if root == null:
		root = tree.root
	var holder: WorldEnvironment = _find_world_environment(root)
	if holder == null:
		return null
	return holder.environment


static func _find_world_environment(node: Node) -> WorldEnvironment:
	if node == null:
		return null
	if node is WorldEnvironment:
		return node as WorldEnvironment
	for child in node.get_children():
		var found: WorldEnvironment = _find_world_environment(child)
		if found != null:
			return found
	return null


## The Sfx autoload, looked up by path so that this file still compiles under
## `--check-only --script`, which does not register the project autoloads.
func _sfx() -> Node:
	if not is_inside_tree():
		return null
	var tree := get_tree()
	if tree == null:
		return null
	return tree.root.get_node_or_null("Sfx")


## Campaign seed from the Game autoload, same indirection, with a stable
## fallback so that `roll()` never becomes non deterministic.
func _campaign_seed() -> int:
	if not is_inside_tree():
		return 1942
	var tree := get_tree()
	if tree == null:
		return 1942
	var game: Node = tree.root.get_node_or_null("Game")
	if game == null:
		return 1942
	var value: Variant = game.get("campaign_seed")
	if value == null:
		return 1942
	return int(value)


## Deterministic 32 bit hash of two integers, mapped to [0,1].
static func _hash01(a: int, b: int) -> float:
	var h: int = (a * 374761393 + b * 668265263) & 0x7FFFFFFF
	h = (h ^ (h >> 13)) * 1274126177
	h = h & 0x7FFFFFFF
	h = h ^ (h >> 16)
	return float(h & 0xFFFFFF) / 16777215.0
