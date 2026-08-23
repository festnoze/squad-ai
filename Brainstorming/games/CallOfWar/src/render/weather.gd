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
const KIND_COUNT := 5

## Height of the rain box above the player, in metres.
const RAIN_ALTITUDE := 15.0
## Half extents of the rain emission box, in metres.
const RAIN_EXTENT := 24.0
## Number of raindrops allocated. The visible amount is driven by `amount_ratio`
## so that changing the weather never restarts the emitter.
const RAIN_BUDGET := 2600
## How many in-game hours an explicit `set_weather()` survives the hourly roll.
const MANUAL_HOURS := 3

var kind: int = CLEAR
## 0..1, drives sound and visibility.
var intensity: float = 0.0

var _sky: SkyController = null
var _follow: Node3D = null
var _env: Environment = null
var _rain: GPUParticles3D = null
var _rain_material: ParticleProcessMaterial = null

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
const _P_COUNT := 7


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


## Visibility multiplier for AI sight range, 1.0 clear down to 0.35 in a storm.
func sight_factor() -> float:
	if _from.size() < _P_COUNT or _to.size() < _P_COUNT:
		return 1.0
	var t: float = _blend * _blend * (3.0 - 2.0 * _blend)
	return clampf(lerpf(_from[_P_SIGHT], _to[_P_SIGHT], t), 0.30, 1.0)


func kind_name() -> String:
	match kind:
		CLEAR: return "Ciel degage"
		OVERCAST: return "Couvert"
		RAIN: return "Pluie"
		FOG: return "Brouillard"
		STORM: return "Orage"
	return "Ciel degage"


## Deterministic weather roll for a given world seed and in-game hour.
##
## Pure function of its two arguments: the same campaign always gets the same
## sky at the same hour, whatever the player did in between. The distribution is
## Normandy in late summer, so overcast dominates, mist belongs to the early
## morning and real storms are rare and only ever break in the afternoon.
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
		_env.fog_depth_begin = _env.fog_depth_end * 0.16
		# Rain and mist wash the sun scatter out of the fog. Written with minf
		# rather than a multiply so that reapplying it every frame converges
		# instead of decaying the value to zero.
		_env.fog_sun_scatter = minf(_env.fog_sun_scatter, 0.14 * (1.0 - intensity * 0.6))

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


func _track_player(delta: float) -> void:
	if _rain == null:
		return
	if _follow == null or not is_instance_valid(_follow) or not _follow.is_inside_tree():
		return
	if not _rain.is_inside_tree():
		return
	var target: Vector3 = _follow.global_position
	# The contract asks for XZ tracking. The vertical is smoothed rather than
	# snapped so that climbing a hill does not teleport the emission plane, and
	# because the particles live in global space the box can move freely without
	# dragging the drops already in the air.
	_rain_y = lerpf(_rain_y, target.y + RAIN_ALTITUDE, clampf(delta * 1.6, 0.0, 1.0))
	_rain.global_position = Vector3(target.x, _rain_y, target.z)

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
		return
	_set_weather(roll(_campaign_seed(), hour), 14.0)


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
		OVERCAST:
			p[_P_OVERCAST] = 0.88
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.10
			p[_P_FOG_RANGE] = 0.86
			p[_P_WIND] = 0.35
			p[_P_SIGHT] = 0.88
			p[_P_INTENSITY] = 0.30
		RAIN:
			p[_P_OVERCAST] = 0.95
			p[_P_RAIN] = 0.55
			p[_P_FOG_OPACITY] = 0.18
			p[_P_FOG_RANGE] = 0.62
			p[_P_WIND] = 0.55
			p[_P_SIGHT] = 0.68
			p[_P_INTENSITY] = 0.65
		FOG:
			p[_P_OVERCAST] = 0.62
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.55
			p[_P_FOG_RANGE] = 0.22
			p[_P_WIND] = 0.06
			p[_P_SIGHT] = 0.45
			p[_P_INTENSITY] = 0.55
		STORM:
			p[_P_OVERCAST] = 1.0
			p[_P_RAIN] = 1.0
			p[_P_FOG_OPACITY] = 0.30
			p[_P_FOG_RANGE] = 0.46
			p[_P_WIND] = 1.0
			p[_P_SIGHT] = 0.35
			p[_P_INTENSITY] = 1.0
		_:
			p[_P_OVERCAST] = 0.08
			p[_P_RAIN] = 0.0
			p[_P_FOG_OPACITY] = 0.0
			p[_P_FOG_RANGE] = 1.0
			p[_P_WIND] = 0.15
			p[_P_SIGHT] = 1.0
			p[_P_INTENSITY] = 0.0
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
# Lookups
# ---------------------------------------------------------------------------

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
