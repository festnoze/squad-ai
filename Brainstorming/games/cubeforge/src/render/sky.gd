class_name SkyController
extends Node
## Day and night cycle for CUBEFORGE.
##
## Owns the Environment, the Sky and the sky ShaderMaterial, all built by code,
## and drives them plus the sun and moon DirectionalLight3D every frame. The
## shader knows nothing about the time of day: this node feeds it colours and
## factors through uniforms.

signal night_changed(is_night: bool)

const SHADER_PATH := "res://src/render/shaders/sky.gdshader"

## 0 = midnight, 0.25 = dawn, 0.5 = noon, 0.75 = dusk.
var time_of_day: float = 0.30
## Seconds of real time for one full cycle.
var day_length: float = 600.0
var paused: bool = false

# ---------------------------------------------------------------------------
# Sun path
# ---------------------------------------------------------------------------

## The sun travels a great circle through east (+X) and a tilted up axis, which
## keeps it away from the exact zenith and gives long readable shadows.
const _AXIS_EAST := Vector3(1.0, 0.0, 0.0)
## Precomputed Vector3(0, cos(0.34), sin(0.34)), a 19.5 degree tilt towards +Z.
const _AXIS_TILTED_UP := Vector3(0.0, 0.942755, 0.333487)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

const _DAY_ZENITH := Color(0.17, 0.38, 0.78)
const _TWILIGHT_ZENITH := Color(0.24, 0.22, 0.46)
const _NIGHT_ZENITH := Color(0.035, 0.050, 0.115)

const _DAY_HORIZON := Color(0.68, 0.81, 0.95)
const _TWILIGHT_HORIZON := Color(0.96, 0.45, 0.22)
const _NIGHT_HORIZON := Color(0.085, 0.105, 0.185)

## Colour of the sky below the horizon. It is only ever seen past the edge of the
## loaded terrain, so it has to sit close to the horizon colour: a dark grey here
## draws a hard bar under the skyline on every wide shot.
const _DAY_GROUND := Color(0.56, 0.63, 0.70)
const _NIGHT_GROUND := Color(0.045, 0.055, 0.085)

## Half width, in sun elevation, of the warm twilight window. A few degrees
## would be astronomically right, but the sky reads better with a long afterglow.
const _TWILIGHT_SPAN := 0.32

const _SUN_HORIZON := Color(1.0, 0.40, 0.13)
const _SUN_ZENITH := Color(1.0, 0.975, 0.94)

const _GLOW_DAY := Color(1.0, 0.80, 0.60)
const _GLOW_TWILIGHT := Color(1.0, 0.38, 0.14)
const _GLOW_NIGHT := Color(0.22, 0.30, 0.52)

const _MOON_COLOR := Color(0.87, 0.91, 1.0)
const _MOON_LIGHT := Color(0.58, 0.70, 1.0)

const _CLOUD_LIT_DAY := Color(1.0, 0.995, 0.975)
const _CLOUD_LIT_TWILIGHT := Color(1.0, 0.66, 0.44)
const _CLOUD_LIT_NIGHT := Color(0.18, 0.22, 0.34)
const _CLOUD_DARK_DAY := Color(0.46, 0.52, 0.62)
const _CLOUD_DARK_TWILIGHT := Color(0.36, 0.28, 0.38)
const _CLOUD_DARK_NIGHT := Color(0.055, 0.070, 0.110)

const _AMBIENT_DAY := Color(0.72, 0.80, 0.94)
const _AMBIENT_NIGHT := Color(0.34, 0.44, 0.68)

## Ambient sits well under the sun on purpose. Voxel albedos are bright (the
## biome tinted grass top lands around 0.5, sand near 0.8), so sun plus ambient
## easily exceeds 1.0, and everything above 1.0 gets pushed into the shoulder of
## the ACES curve where it desaturates toward white. Keeping ambient at roughly a
## third of the sun leaves lit ground inside the linear part of the curve, which
## is what makes grass read as green rather than pale mint.
## Night keeps its own energy because it is fed by _AMBIENT_NIGHT alone (the sky
## contributes nothing once it is dark). Measured on a mid grey surface through
## the ACES curve: a face lit by ambient only reads about 0.05 at night against
## 0.33 in the daytime shade, dark enough to feel like night and light enough to
## walk around in.
const _NIGHT_AMBIENT_ENERGY := 0.42
const _DAY_AMBIENT_ENERGY := 0.40
const _MOON_LIGHT_ENERGY := 0.30

## Peak sun energy at the zenith.
const _SUN_PEAK_ENERGY := 1.05

## Sun elevation thresholds of the night flag. The gap is the hysteresis that
## stops night_changed from chattering around dusk and dawn.
const _NIGHT_ENTER := -0.035
const _NIGHT_LEAVE := 0.055

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

var _world_env: WorldEnvironment
var _environment: Environment
var _sky: Sky
var _material: ShaderMaterial
var _sun: DirectionalLight3D
var _moon: DirectionalLight3D

var _sun_dir: Vector3 = Vector3.UP
var _moon_dir: Vector3 = Vector3.DOWN
var _is_night: bool = false
var _night_known: bool = false
var _elapsed: float = 0.0
var _day_index: int = 0
var _game: Node
var _render_distance: int = 8


func _ready() -> void:
	# Nothing to animate before setup() has produced an Environment.
	set_process(false)


## Builds the Environment, the Sky and the sky material by code, hooks them to
## `env`, then takes ownership of the two directional lights.
func setup(env: WorldEnvironment, sun: DirectionalLight3D, moon: DirectionalLight3D) -> void:
	_world_env = env
	_sun = sun
	_moon = moon

	_material = _build_material()
	_sky = Sky.new()
	_sky.sky_material = _material
	_sky.radiance_size = Sky.RADIANCE_SIZE_128
	# The sky changes every frame, so spread the radiance update over frames.
	_sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL

	_environment = _build_environment(_sky)
	if _world_env != null:
		_world_env.environment = _environment
	else:
		push_warning("SkyController.setup received a null WorldEnvironment")

	_configure_lights()

	_game = _find_game()
	if _game != null and _game.has_signal("settings_changed"):
		var cb := Callable(self, "_on_settings_changed")
		if not _game.is_connected("settings_changed", cb):
			_game.connect("settings_changed", cb)

	_apply_render_distance()
	_update(true)
	set_process(true)


func _process(delta: float) -> void:
	if _environment == null:
		return
	_elapsed += delta
	if not paused:
		var previous := time_of_day
		time_of_day = fposmod(time_of_day + delta / maxf(day_length, 1.0), 1.0)
		if time_of_day < previous:
			_day_index += 1
	_update(false)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

func is_night() -> bool:
	return _is_night


## Clock reading of the cycle, for example "06:24".
func time_string() -> String:
	var minutes := int(round(fposmod(time_of_day, 1.0) * 1440.0)) % 1440
	return "%02d:%02d" % [minutes / 60, minutes % 60]


## Jumps to a point of the cycle and refreshes everything immediately.
func skip_to(t: float) -> void:
	time_of_day = fposmod(t, 1.0)
	if _environment != null:
		_update(false)


## Unit vector pointing from the world towards the sun.
func sun_direction() -> Vector3:
	return _sun_dir


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

func _build_material() -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	var shader: Shader = load(SHADER_PATH) as Shader
	if shader == null:
		push_error("SkyController could not load %s" % SHADER_PATH)
		return mat
	mat.shader = shader

	# Static shape of the sky. The animated uniforms are written by _update().
	mat.set_shader_parameter("gradient_falloff", 3.0)
	mat.set_shader_parameter("sun_disc_size", 0.031)
	mat.set_shader_parameter("sun_disc_edge", 0.008)
	mat.set_shader_parameter("sun_halo_tightness", 7.0)
	mat.set_shader_parameter("horizon_glow_tightness", 5.5)
	mat.set_shader_parameter("horizon_glow_focus", 3.5)
	mat.set_shader_parameter("moon_size", 0.056)
	mat.set_shader_parameter("moon_halo_strength", 0.22)
	mat.set_shader_parameter("moon_halo_tightness", 26.0)
	mat.set_shader_parameter("star_color", Color(0.92, 0.95, 1.0))
	mat.set_shader_parameter("star_density", 96.0)
	mat.set_shader_parameter("star_sparsity", 0.93)
	mat.set_shader_parameter("star_size", 0.21)
	mat.set_shader_parameter("star_twinkle_speed", 0.7)
	# The cloud plane is sampled as tan(angle from zenith), so the scale sets how
	# many cloud clumps fit in the overhead cone. Too small and the whole sky is
	# one smeared blob. The drift is scaled with it to keep the same apparent
	# speed on screen.
	mat.set_shader_parameter("cloud_scale", 3.2)
	mat.set_shader_parameter("cloud_speed", 0.085)
	mat.set_shader_parameter("cloud_softness", 0.24)
	mat.set_shader_parameter("cloud_opacity", 0.80)
	mat.set_shader_parameter("cloud_shade_step", 0.55)
	mat.set_shader_parameter("cloud_shade_gain", 2.6)
	mat.set_shader_parameter("cloud_rim_glow", 0.35)
	mat.set_shader_parameter("cloud_horizon_fade", 0.055)
	return mat


func _build_environment(sky: Sky) -> Environment:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.background_energy_multiplier = 1.0

	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_color = _AMBIENT_DAY
	env.ambient_light_energy = _DAY_AMBIENT_ENERGY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	# ACES with a white point of 1.0: filmic highlights, no clipped sun.
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_white = 1.0
	env.tonemap_exposure = 1.0

	# Screen space effects stay off, this is a voxel world with big flat faces
	# and a wide render distance.
	env.ssao_enabled = false
	env.ssil_enabled = false
	env.ssr_enabled = false
	env.sdfgi_enabled = false
	env.volumetric_fog_enabled = false

	# Subtle bloom only. A wide cloud field plus the sun disc feeds the glow a lot
	# of energy, and anything stronger than this washes the blue out of the sky.
	env.glow_enabled = true
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	env.glow_intensity = 0.14
	env.glow_strength = 1.0
	env.glow_bloom = 0.0
	env.glow_hdr_threshold = 1.25
	env.glow_hdr_scale = 2.0
	env.set_glow_level(1, 0.0)
	env.set_glow_level(2, 0.4)
	env.set_glow_level(3, 1.0)
	env.set_glow_level(4, 0.6)
	env.set_glow_level(5, 0.0)
	env.set_glow_level(6, 0.0)

	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = _DAY_HORIZON
	env.fog_light_energy = 1.0
	env.fog_sun_scatter = 0.12
	env.fog_density = 0.45
	env.fog_aerial_perspective = 0.10
	# A little fog on the sky too. At zero the fogged terrain meets an unfogged
	# sky in a hard band along the horizon, which is exactly the seam the fog is
	# supposed to hide.
	env.fog_sky_affect = 0.30
	env.fog_height = 0.0
	env.fog_height_density = 0.0
	env.fog_depth_curve = 1.6

	env.adjustment_enabled = true
	env.adjustment_brightness = 1.0
	env.adjustment_contrast = 1.03
	env.adjustment_saturation = 1.06
	return env


func _configure_lights() -> void:
	if _sun != null:
		_sun.light_color = _SUN_ZENITH
		_sun.light_energy = _SUN_PEAK_ENERGY
		_sun.light_specular = 0.15
		_sun.light_angular_distance = 0.55
		_sun.shadow_enabled = true
		_sun.shadow_bias = 0.04
		_sun.shadow_normal_bias = 1.4
		_sun.shadow_blur = 1.0
		_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
		_sun.directional_shadow_blend_splits = true
		_sun.directional_shadow_split_1 = 0.06
		_sun.directional_shadow_split_2 = 0.18
		_sun.directional_shadow_split_3 = 0.45
		_sun.directional_shadow_fade_start = 0.85
	if _moon != null:
		# Cool dim counter light, no shadows to keep the night cheap.
		_moon.light_color = _MOON_LIGHT
		_moon.light_energy = 0.0
		_moon.light_specular = 0.05
		_moon.light_angular_distance = 1.6
		_moon.shadow_enabled = false
		_moon.visible = false


# ---------------------------------------------------------------------------
# Per frame update
# ---------------------------------------------------------------------------

func _update(force: bool) -> void:
	_sun_dir = _sun_dir_at(time_of_day)
	# The moon sits opposite the sun, nudged sideways so it is never an exact
	# antisolar point. A rotation around Y keeps its elevation mirrored.
	_moon_dir = (-_sun_dir).rotated(Vector3.UP, 0.42).normalized()

	var el := _sun_dir.y
	var day := clampf(smoothstep(-0.02, 0.20, el), 0.0, 1.0)
	var twilight := clampf(1.0 - absf(el) / _TWILIGHT_SPAN, 0.0, 1.0)
	twilight = twilight * twilight * (3.0 - 2.0 * twilight)
	var night := clampf(smoothstep(0.04, -0.11, el), 0.0, 1.0)
	# The ambient has to follow the sky rather than the sun: at sunset the disc
	# is already gone while the sky still throws a lot of light around.
	var ambient_ramp := clampf(smoothstep(-0.12, 0.18, el), 0.0, 1.0)

	var zenith := _NIGHT_ZENITH.lerp(_TWILIGHT_ZENITH, twilight).lerp(_DAY_ZENITH, day)
	var horizon := _NIGHT_HORIZON.lerp(_TWILIGHT_HORIZON, twilight).lerp(_DAY_HORIZON, day)
	# Below the horizon, warm the ground colour towards a dimmed horizon during
	# twilight, otherwise dusk paints a flat black bar under a blazing sky.
	var dim := lerpf(0.30, 0.60, day)
	var ground := _NIGHT_GROUND.lerp(_DAY_GROUND, day).lerp(
		Color(horizon.r * dim, horizon.g * dim, horizon.b * dim), twilight * 0.85)

	var high := clampf(pow(clampf(el / 0.34, 0.0, 1.0), 0.65), 0.0, 1.0)
	var sun_tint := _SUN_HORIZON.lerp(_SUN_ZENITH, high)
	var glow_tint := _GLOW_NIGHT.lerp(_GLOW_TWILIGHT, twilight).lerp(_GLOW_DAY, day * (1.0 - twilight))

	var sun_visible := clampf(smoothstep(-0.075, 0.005, el), 0.0, 1.0)
	var moon_visible := clampf(smoothstep(-0.05, 0.09, _moon_dir.y), 0.0, 1.0) * (0.30 + 0.70 * night)

	if _material != null and _material.shader != null:
		_material.set_shader_parameter("zenith_color", zenith)
		_material.set_shader_parameter("horizon_color", horizon)
		_material.set_shader_parameter("ground_color", ground)

		_material.set_shader_parameter("sun_direction", _sun_dir)
		_material.set_shader_parameter("sun_disc_color", sun_tint)
		_material.set_shader_parameter("sun_glow_color", glow_tint)
		_material.set_shader_parameter("sun_visibility", sun_visible)
		_material.set_shader_parameter("sun_halo_strength", 0.32 + 0.55 * twilight)
		_material.set_shader_parameter("horizon_glow_strength", 0.20 * day + 1.70 * twilight)

		_material.set_shader_parameter("moon_direction", _moon_dir)
		_material.set_shader_parameter("moon_color", _MOON_COLOR)
		_material.set_shader_parameter("moon_visibility", moon_visible)
		_material.set_shader_parameter("moon_phase", _moon_phase())

		_material.set_shader_parameter("star_intensity", night)

		var lit := _CLOUD_LIT_NIGHT.lerp(_CLOUD_LIT_TWILIGHT, twilight).lerp(_CLOUD_LIT_DAY, day * (1.0 - 0.55 * twilight))
		var dark := _CLOUD_DARK_NIGHT.lerp(_CLOUD_DARK_TWILIGHT, twilight).lerp(_CLOUD_DARK_DAY, day * (1.0 - 0.55 * twilight))
		_material.set_shader_parameter("cloud_light_color", lit)
		_material.set_shader_parameter("cloud_shadow_color", dark)
		# Slow breathing of the cover so the sky is never twice the same. The
		# fbm averages around 0.53, so this threshold keeps a partly cloudy sky.
		_material.set_shader_parameter("cloud_coverage", 0.63 + 0.06 * sin(_elapsed * 0.017))

	if _environment != null:
		_environment.ambient_light_color = _AMBIENT_NIGHT.lerp(_AMBIENT_DAY, day)
		# Never let the sky alone carry the ambient at night: the night sky
		# radiance is nearly black, so a pure sky ambient would leave the world
		# unplayable. At night the tuned floor colour carries all of it, by day
		# the sky radiance does, which is both prettier and physically right.
		_environment.ambient_light_sky_contribution = ambient_ramp
		_environment.ambient_light_energy = lerpf(_NIGHT_AMBIENT_ENERGY, _DAY_AMBIENT_ENERGY, ambient_ramp)

		_environment.fog_light_color = horizon.lerp(Color(1.0, 1.0, 1.0), 0.05)
		_environment.fog_light_energy = lerpf(0.50, 1.0, ambient_ramp)
		_environment.fog_sun_scatter = clampf(0.10 + 0.55 * twilight, 0.0, 1.0)

	_aim_light(_sun, _sun_dir)
	_aim_light(_moon, _moon_dir)

	if _sun != null:
		var sun_energy := clampf(smoothstep(-0.05, 0.14, el), 0.0, 1.0) * _SUN_PEAK_ENERGY
		_sun.light_color = sun_tint
		_sun.light_energy = sun_energy
		_sun.visible = sun_energy > 0.002
	if _moon != null:
		var moon_energy := clampf(smoothstep(-0.04, 0.16, _moon_dir.y), 0.0, 1.0) * _MOON_LIGHT_ENERGY
		_moon.light_energy = moon_energy
		_moon.visible = moon_energy > 0.002

	_update_night_flag(el, force)


## Latches the night flag with hysteresis so dusk and dawn emit exactly once.
func _update_night_flag(elevation: float, force: bool) -> void:
	var wanted := _is_night
	if elevation < _NIGHT_ENTER:
		wanted = true
	elif elevation > _NIGHT_LEAVE:
		wanted = false
	if not _night_known:
		_night_known = true
		_is_night = wanted
		if force:
			return
	if wanted != _is_night:
		_is_night = wanted
		night_changed.emit(_is_night)


## Moon phase, walking from a crescent to nearly full over a handful of in game
## days. The first night lands mid way so the carved crescent is visible at once.
func _moon_phase() -> float:
	var wave := 0.5 + 0.5 * sin(float(_day_index) * 0.8)
	return lerpf(0.38, 1.06, wave)


func _sun_dir_at(t: float) -> Vector3:
	# theta = 0 at dawn, PI / 2 at noon, PI at dusk, -PI / 2 at midnight.
	var theta := (fposmod(t, 1.0) - 0.25) * TAU
	return (_AXIS_EAST * cos(theta) + _AXIS_TILTED_UP * sin(theta)).normalized()


## Points the light so its beam travels along -dir, meaning it shines from the
## sky position `dir`. Built by hand instead of look_at() to stay safe when the
## direction lines up with the world up axis, and only the basis is touched so
## the caller keeps control of where it parked the node.
func _aim_light(light: DirectionalLight3D, dir: Vector3) -> void:
	if light == null:
		return
	var z := dir.normalized()
	if z.length_squared() < 0.5:
		return
	var reference := Vector3.UP
	if absf(z.y) > 0.999:
		reference = Vector3(0.0, 0.0, 1.0)
	var x := reference.cross(z).normalized()
	var y := z.cross(x).normalized()
	var basis := Basis(x, y, z)
	if light.is_inside_tree():
		light.global_basis = basis
	else:
		light.basis = basis


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

func _on_settings_changed() -> void:
	_apply_render_distance()


## Fog and shadow reach follow the loaded ring, so a short render distance
## hides its own boundary instead of showing a hard edge against the sky.
func _apply_render_distance() -> void:
	_render_distance = _read_render_distance()
	if _environment == null:
		return
	var far := float(_render_distance * ChunkData.SIZE_X)
	# Fog starts past the middle of the loaded ring. Any earlier and it eats the
	# terrain the player is actually looking at, which reads as a washed out world
	# rather than as distance.
	var begin := far * 0.55
	_environment.fog_depth_begin = begin
	_environment.fog_depth_end = maxf(far * 0.98, begin + 8.0)
	# fog_density is the peak opacity in depth mode, not a per unit density. A
	# tight ring needs a thicker fog to swallow its edge, but never a full one, or
	# the horizon turns into a flat wall of colour.
	_environment.fog_density = lerpf(0.62, 0.34, clampf(float(_render_distance - 3) / 13.0, 0.0, 1.0))
	if _sun != null:
		_sun.directional_shadow_max_distance = maxf(96.0, far * 0.80)


func _read_render_distance() -> int:
	if _game == null:
		_game = _find_game()
	if _game != null and "render_distance" in _game:
		return clampi(int(_game.render_distance), 3, 16)
	return 8


## Looks the Game autoload up through the main loop rather than through an
## absolute path, which works even when this node is not in the tree yet.
func _find_game() -> Node:
	var loop := Engine.get_main_loop() as SceneTree
	if loop == null or loop.root == null:
		return null
	return loop.root.get_node_or_null(^"Game")
