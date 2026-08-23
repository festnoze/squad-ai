class_name SkyController
extends Node

## Day / night cycle and general mood of the Normandy pocket.
##
## The node does NOT own the WorldEnvironment: `setup()` receives it, along with
## the two directional lights, so the scene keeps control of its own tree.
##
## Photometric traps this file exists to avoid:
##  - `ambient_light_energy` is completely INERT while
##    `ambient_light_sky_contribution` is 1.0. To drive the ambient term by hand
##    the contribution has to come down (0.25 here) and the colour has to be set
##    through `ambient_light_color`.
##  - `fog_density` in FOG_MODE_DEPTH is a MAXIMUM OPACITY, not a density per
##    metre. Pushing it to 1.0 makes distant hills vanish behind a flat wall.
##  - `fog_sky_affect = 0` draws a hard bar along the horizon where the fogged
##    terrain meets the unfogged sky. It stays above zero, always.
##  - The sky colour below the horizon must stay close to the horizon colour,
##    otherwise every wide shot shows a grey band across the bottom half.
##  - Two visible directional lights means two shadow maps. The light that is
##    under the horizon is hidden outright.

signal phase_changed(is_night: bool)

## 0.0 = minuit, 0.5 = midi. Avance tout seul.
var time_of_day: float = 0.34
## Real seconds for a full day. Default 1200 (20 min).
var day_length: float = 1200.0

## Sunrise and sunset, in `time_of_day` units. The day is deliberately longer
## than the night: this is Normandy at the end of summer.
const SUNRISE := 0.25
const SUNSET := 0.79

## Highest the sun ever climbs, in radians (about 58 degrees).
const MAX_ELEVATION := 1.012

## Ratio of the sky term in the ambient mix. Anything close to 1.0 makes
## `ambient_light_color` and `ambient_light_energy` useless.
const SKY_CONTRIBUTION := 0.25

## Fog opacity at maximum range, per weather mood.
const FOG_DENSITY_CLEAR := 0.42
const FOG_DENSITY_OVERCAST := 0.78

var _env_holder: WorldEnvironment = null
var _env: Environment = null
var _sun: DirectionalLight3D = null
var _moon: DirectionalLight3D = null
var _sky_material: ShaderMaterial = null

var _overcast: float = 0.15
var _was_night: bool = false
var _ready_ok: bool = false

## Cached sun elevation sine, refreshed by `_apply()`.
var _sun_up: Vector3 = Vector3(0.0, 0.5, 0.5)
var _moon_up: Vector3 = Vector3(0.0, -0.5, -0.5)


func _ready() -> void:
	set_process(true)


func _process(delta: float) -> void:
	if not _ready_ok:
		return
	if day_length > 0.1:
		time_of_day = fposmod(time_of_day + delta / day_length, 1.0)
	_apply()
	var night: bool = is_night()
	if night != _was_night:
		_was_night = night
		phase_changed.emit(night)


func setup(env_holder: WorldEnvironment, sun: DirectionalLight3D, moon: DirectionalLight3D) -> void:
	if env_holder == null or sun == null or moon == null:
		push_error("SkyController.setup: missing WorldEnvironment, sun or moon.")
		return
	_env_holder = env_holder
	_sun = sun
	_moon = moon

	_env = env_holder.environment
	if _env == null:
		_env = Environment.new()
		env_holder.environment = _env

	_build_sky()
	_configure_environment()
	_configure_lights()

	_ready_ok = true
	_was_night = is_night()
	_apply()


## True while the sun is at or under the horizon.
##
## Defined from the actual elevation rather than from the SUNRISE / SUNSET
## window, so that it can never disagree with the lights: at exactly t = SUNSET
## the window says night while sin(PI) is a hair above zero, which used to leave
## a lit sun during a "night" frame.
func is_night() -> bool:
	return _to_sun(time_of_day).y <= 0.0


func skip_to(new_time: float) -> void:
	time_of_day = fposmod(new_time, 1.0)
	if _ready_ok:
		_apply()
	var night: bool = is_night()
	if night != _was_night:
		_was_night = night
		phase_changed.emit(night)


func time_string() -> String:
	var minutes: int = int(round(time_of_day * 1440.0)) % 1440
	return "%02d:%02d" % [minutes / 60, minutes % 60]


## Sun direction, unit vector pointing FROM the sun TOWARDS the world.
func sun_direction() -> Vector3:
	return -_to_sun(time_of_day)


## 0 = pitch black, 1 = full noon. Used by the AI to shorten sight range.
func light_level() -> float:
	var elevation: float = _to_sun(time_of_day).y
	var base: float = clampf((elevation + 0.03) / 0.62, 0.0, 1.0)
	# A thick overcast really does steal a third of the usable light.
	return clampf(base * (1.0 - _overcast * 0.30), 0.0, 1.0)


## Applies the weather mood: 0 clear, 1 overcast. Called by Weather.
func set_overcast(amount: float) -> void:
	_overcast = clampf(amount, 0.0, 1.0)
	if _ready_ok:
		_apply()


# ---------------------------------------------------------------------------
# Celestial geometry
# ---------------------------------------------------------------------------

## Unit vector from the world TOWARDS the sun, for a given time of day.
##
## The arc is parameterised by an angle that is 0 at sunrise, PI at sunset and
## 2 PI at the next sunrise, so it stays continuous across midnight even though
## the day is longer than the night.
func _to_sun(t: float) -> Vector3:
	var day_span: float = SUNSET - SUNRISE
	var night_span: float = 1.0 - day_span
	var theta: float = 0.0
	if t >= SUNRISE and t < SUNSET:
		theta = (t - SUNRISE) / day_span * PI
	else:
		var tt: float = t if t >= SUNSET else t + 1.0
		theta = PI + (tt - SUNSET) / night_span * PI
	# East is +X, west is -X, south is +Z: the arc culminates in the south, the
	# way it does at 49 degrees north.
	var s: float = sin(theta)
	var dir := Vector3(cos(theta), s * sin(MAX_ELEVATION), s * cos(MAX_ELEVATION))
	return dir.normalized()


## Unit vector from the world TOWARDS the moon. Roughly opposite the sun, tipped
## a little so the two never share the exact same track across the sky.
func _to_moon(t: float) -> Vector3:
	var opposite: Vector3 = -_to_sun(t)
	return opposite.rotated(Vector3.FORWARD, 0.22).normalized()


# ---------------------------------------------------------------------------
# Per frame application
# ---------------------------------------------------------------------------

func _apply() -> void:
	_sun_up = _to_sun(time_of_day)
	_moon_up = _to_moon(time_of_day)

	var elevation: float = _sun_up.y
	var height: float = clampf(elevation / sin(MAX_ELEVATION), 0.0, 1.0)
	var day: float = light_level()
	var sun_visible: bool = elevation > 0.0

	_aim_light(_sun, -_sun_up)
	_aim_light(_moon, -_moon_up)
	# Only ever one visible directional light: two of them means two full
	# shadow map passes for nothing.
	_sun.visible = sun_visible
	_moon.visible = not sun_visible

	var sun_tint: Color = _sun_tint(height)
	var sun_energy: float = 0.0
	if sun_visible:
		# Weak and grazing at the horizon, strong at noon, dimmed by cloud.
		sun_energy = lerpf(0.28, 1.45, pow(height, 0.72)) * (1.0 - _overcast * 0.62)
	_sun.light_color = sun_tint
	_sun.light_energy = sun_energy
	_sun.light_angular_distance = lerpf(1.6, 0.55, 1.0 - _overcast)
	_sun.shadow_enabled = sun_visible and sun_energy > 0.08

	var moon_energy: float = 0.0
	if not sun_visible:
		moon_energy = lerpf(0.02, 0.11, clampf(_moon_up.y * 2.0, 0.0, 1.0)) * (1.0 - _overcast * 0.75)
	_moon.light_color = Palette.MOON_LIGHT
	_moon.light_energy = moon_energy
	_moon.light_angular_distance = 1.2
	_moon.shadow_enabled = (not sun_visible) and moon_energy > 0.045

	_apply_sky(height, day, sun_visible)
	_apply_ambient(day)
	_apply_fog(day)


func _aim_light(light: DirectionalLight3D, forward: Vector3) -> void:
	if light == null or not light.is_inside_tree():
		return
	var dir: Vector3 = forward.normalized()
	if dir.length_squared() < 0.0001:
		return
	var up: Vector3 = Vector3.UP
	if absf(dir.dot(up)) > 0.995:
		up = Vector3.FORWARD
	light.global_transform = Transform3D(Basis.looking_at(dir, up), light.global_transform.origin)


## Rosy at dawn, broken white at noon, orange at dusk, near nothing at night.
func _sun_tint(height: float) -> Color:
	var low: Color = Palette.SUN_DAWN if time_of_day < 0.52 else Palette.SUN_DUSK
	var warm: float = clampf(1.0 - height * 2.6, 0.0, 1.0)
	var tint: Color = Palette.mix(Palette.SUN_NOON, low, warm)
	# Cloud cover drains the colour out of the light before it drains the power.
	return Palette.desaturate(tint, _overcast * 0.55)


func _apply_sky(height: float, day: float, sun_visible: bool) -> void:
	if _sky_material == null:
		return
	var clear_top: Color = Palette.mix(Palette.SKY_TOP_NIGHT, Palette.SKY_TOP_DAY, day)
	var clear_hzn: Color = Palette.mix(Palette.SKY_HZN_NIGHT, Palette.SKY_HZN_DAY, day)
	# Warm the horizon while the sun is low, the way a Normandy dusk does.
	var dusk: float = 0.0
	if sun_visible:
		dusk = clampf(1.0 - height * 3.0, 0.0, 1.0)
	clear_hzn = Palette.mix(clear_hzn, Palette.mix(Palette.SUN_DUSK, Palette.SKY_HZN_DAY, 0.45), dusk * 0.6)

	var top: Color = Palette.mix(clear_top, Palette.shade(Palette.SKY_TOP_OVERCAST, 0.25 + day * 0.85), _overcast)
	var hzn: Color = Palette.mix(clear_hzn, Palette.shade(Palette.SKY_HZN_OVERCAST, 0.25 + day * 0.85), _overcast)
	# The ground half of the sky sphere stays deliberately close to the horizon
	# colour: a darker value here prints a grey band across every wide shot.
	var ground: Color = Palette.mix(hzn, Palette.shade(hzn, 0.62), 0.75)

	_sky_material.set_shader_parameter("top_color", top)
	_sky_material.set_shader_parameter("horizon_color", hzn)
	_sky_material.set_shader_parameter("ground_color", ground)
	_sky_material.set_shader_parameter("sun_dir", _sun_up)
	_sky_material.set_shader_parameter("sun_color", _sun_tint(height))
	_sky_material.set_shader_parameter("sun_energy", 1.0 if sun_visible else 0.0)
	_sky_material.set_shader_parameter("moon_dir", _moon_up)
	_sky_material.set_shader_parameter("moon_energy", 0.0 if sun_visible else clampf(_moon_up.y * 2.0, 0.0, 1.0))
	_sky_material.set_shader_parameter("overcast", _overcast)
	_sky_material.set_shader_parameter("night", 1.0 - day)
	_sky_material.set_shader_parameter("dusk", dusk)


func _apply_ambient(day: float) -> void:
	if _env == null:
		return
	var ambient: Color = Palette.mix(Palette.AMBIENT_NIGHT, Palette.AMBIENT_DAY, day)
	# An overcast sky is a giant softbox: less directional light, more ambient.
	ambient = Palette.mix(ambient, Palette.mix(ambient, Palette.SKY_HZN_OVERCAST, 0.35), _overcast)
	_env.ambient_light_color = ambient
	_env.ambient_light_energy = lerpf(0.22, 0.95, day) * (1.0 + _overcast * 0.35)
	_env.ambient_light_sky_contribution = SKY_CONTRIBUTION


func _apply_fog(day: float) -> void:
	if _env == null:
		return
	var fog_color: Color = Palette.mix(Palette.FOG_NIGHT, Palette.FOG_DAY, day)
	fog_color = Palette.mix(fog_color, Palette.mix(fog_color, Palette.SKY_HZN_OVERCAST, 0.5), _overcast)
	_env.fog_light_color = fog_color
	_env.fog_light_energy = lerpf(0.30, 1.0, day)
	# Max opacity, NOT a per metre density.
	_env.fog_density = lerpf(FOG_DENSITY_CLEAR, FOG_DENSITY_OVERCAST, _overcast)
	var far: float = _view_distance_metres()
	_env.fog_depth_begin = far * 0.22
	_env.fog_depth_end = far
	_env.fog_sun_scatter = 0.14 * (1.0 - _overcast * 0.8)


# ---------------------------------------------------------------------------
# One time construction
# ---------------------------------------------------------------------------

func _build_sky() -> void:
	var shader := Shader.new()
	shader.code = _SKY_SHADER
	shader.resource_name = "sky_shader"
	_sky_material = ShaderMaterial.new()
	_sky_material.shader = shader

	var sky := Sky.new()
	sky.sky_material = _sky_material
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	# The sun moves every frame, so the radiance map is refreshed a slice at a
	# time instead of being rebuilt whole.
	sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL

	_env.background_mode = Environment.BG_SKY
	_env.sky = sky


func _configure_environment() -> void:
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	_env.ambient_light_sky_contribution = SKY_CONTRIBUTION
	_env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	_env.tonemap_mode = Environment.TONE_MAPPER_ACES
	_env.tonemap_exposure = 1.0
	_env.tonemap_white = 6.0

	# Light contact shadowing in the hedgerows and inside buildings. Kept cheap:
	# a heavy SSAO on an open world costs more than it gives.
	_env.ssao_enabled = true
	_env.ssao_radius = 1.4
	_env.ssao_intensity = 1.35
	_env.ssao_power = 1.4
	_env.ssao_detail = 0.4
	_env.ssao_horizon = 0.06
	_env.ssao_sharpness = 0.98
	_env.ssao_light_affect = 0.12
	_env.ssao_ao_channel_affect = 0.0
	_env.ssil_enabled = false
	_env.sdfgi_enabled = false

	# Discreet glow: it exists for tracers, muzzle flashes and fires, not to
	# make the whole frame bloom.
	_env.glow_enabled = true
	_env.glow_normalized = true
	_env.glow_intensity = 0.55
	_env.glow_strength = 1.0
	_env.glow_bloom = 0.02
	_env.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	_env.glow_hdr_threshold = 1.10
	_env.glow_hdr_scale = 2.0
	# set_glow_level() is ZERO based even though the inspector labels the same
	# sliders 1 to 7. Passing 7 fails an ERR_FAIL_INDEX at runtime.
	_env.set_glow_level(0, 0.0)   # level 1, the sharpest: left off, it aliases
	_env.set_glow_level(1, 0.4)   # level 2
	_env.set_glow_level(2, 1.0)   # level 3
	_env.set_glow_level(3, 1.0)   # level 4
	_env.set_glow_level(4, 0.6)   # level 5
	_env.set_glow_level(5, 0.0)   # level 6
	_env.set_glow_level(6, 0.0)   # level 7

	_env.fog_enabled = true
	_env.fog_mode = Environment.FOG_MODE_DEPTH
	_env.fog_depth_curve = 1.35
	_env.fog_aerial_perspective = 0.45
	# Never zero: at zero the fogged terrain meets a clean sky and stamps a hard
	# line right across the horizon.
	_env.fog_sky_affect = 0.35
	_env.volumetric_fog_enabled = false

	# The washed out, cold war film look: pull the saturation down a touch and
	# lift the contrast slightly to keep the image from going flat.
	_env.adjustment_enabled = true
	_env.adjustment_brightness = 1.0
	_env.adjustment_contrast = 1.06
	_env.adjustment_saturation = 0.84


func _configure_lights() -> void:
	_sun.shadow_enabled = true
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	_sun.directional_shadow_split_1 = 0.05
	_sun.directional_shadow_split_2 = 0.14
	_sun.directional_shadow_split_3 = 0.42
	_sun.directional_shadow_blend_splits = true
	_sun.directional_shadow_max_distance = 220.0
	_sun.directional_shadow_fade_start = 0.85
	_sun.shadow_bias = 0.04
	_sun.shadow_normal_bias = 1.4
	_sun.shadow_opacity = 0.92
	_sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY

	_moon.shadow_enabled = true
	_moon.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	_moon.directional_shadow_max_distance = 90.0
	_moon.shadow_bias = 0.05
	_moon.shadow_normal_bias = 1.6
	_moon.shadow_opacity = 0.5
	_moon.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY


## View distance in metres, read from the Game autoload when it exists.
## The autoload is looked up by path on purpose: naming `Game` directly would
## make this file impossible to compile under `--check-only --script`, which
## does not register the project autoloads.
func _view_distance_metres() -> float:
	var loop := Engine.get_main_loop()
	if loop is SceneTree:
		var root: Window = (loop as SceneTree).root
		if root != null:
			var game: Node = root.get_node_or_null("Game")
			if game != null:
				var tiles: int = int(game.get("view_distance"))
				if tiles > 0:
					return clampf(float(tiles) * 64.0 * 0.92, 220.0, 900.0)
	return 460.0


# ---------------------------------------------------------------------------
# Sky shader
# ---------------------------------------------------------------------------

const _SKY_SHADER := """
shader_type sky;

// Gradient sky with a sun disc, a moon disc, stars and a drifting cloud sheet.
// Written by hand rather than using ProceduralSkyMaterial so that the night has
// stars and the overcast has structure.
//
// The colour under the horizon stays deliberately close to the horizon colour:
// a dark ground half prints a grey band across every wide shot of the bocage.

uniform vec4 top_color : source_color = vec4(0.24, 0.38, 0.58, 1.0);
uniform vec4 horizon_color : source_color = vec4(0.62, 0.66, 0.68, 1.0);
uniform vec4 ground_color : source_color = vec4(0.40, 0.42, 0.44, 1.0);
uniform vec4 sun_color : source_color = vec4(1.0, 0.97, 0.90, 1.0);

uniform vec3 sun_dir = vec3(0.0, 0.7, 0.7);
uniform vec3 moon_dir = vec3(0.0, -0.7, -0.7);
uniform float sun_energy = 1.0;
uniform float moon_energy = 0.0;
uniform float overcast = 0.2;
uniform float night = 0.0;
uniform float dusk = 0.0;

float hash12(vec2 p) {
	vec3 p3 = fract(vec3(p.x, p.y, p.x) * 0.1031);
	p3 += dot(p3, vec3(p3.y, p3.z, p3.x) + 33.33);
	return fract((p3.x + p3.y) * p3.z);
}

float hash13(vec3 p) {
	vec3 p3 = fract(p * 0.1031);
	p3 += dot(p3, vec3(p3.y, p3.z, p3.x) + 31.32);
	return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash12(i);
	float b = hash12(i + vec2(1.0, 0.0));
	float c = hash12(i + vec2(0.0, 1.0));
	float d = hash12(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) {
		v += vnoise(p) * a;
		p *= 2.03;
		a *= 0.5;
	}
	return v;
}

void sky() {
	vec3 d = normalize(EYEDIR);
	float up = d.y;

	// Base gradient. Below the horizon the colour barely leaves the horizon
	// value, which is what keeps the bottom half from banding.
	vec3 col;
	if (up >= 0.0) {
		col = mix(horizon_color.rgb, top_color.rgb, pow(clamp(up, 0.0, 1.0), 0.55));
	} else {
		col = mix(horizon_color.rgb, ground_color.rgb, clamp(-up * 2.2, 0.0, 1.0));
	}

	// Warm band along the horizon, on the sun side, at dawn and dusk.
	vec3 flat_sun = vec3(sun_dir.x, 0.0, sun_dir.z);
	float flat_len = max(length(flat_sun), 0.0001);
	float azimuth = clamp(dot(normalize(vec3(d.x, 0.0, d.z) + vec3(0.0001, 0.0, 0.0)), flat_sun / flat_len), 0.0, 1.0);
	float band = pow(1.0 - clamp(abs(up), 0.0, 1.0), 7.0);
	col += sun_color.rgb * pow(azimuth, 3.0) * band * dusk * 0.55 * sun_energy;

	// Stars. Only at night, and only above the horizon.
	if (night > 0.05 && up > -0.02) {
		vec3 cell = d * 190.0;
		vec3 ip = floor(cell);
		float h = hash13(ip);
		float present = step(0.9958, h);
		vec3 f = fract(cell) - 0.5;
		float tight = smoothstep(0.14, 0.0, dot(f, f));
		float twinkle = 0.55 + 0.45 * sin(TIME * 1.7 + h * 210.0);
		float star = present * tight * twinkle;
		col += vec3(0.72, 0.76, 0.90) * star * night * (1.0 - overcast * 0.95) * 1.6;
	}

	// Cloud sheet, projected on a plane well above the camera.
	float py = max(up, 0.045);
	vec2 cuv = vec2(d.x, d.z) / py * 0.32 + vec2(TIME * 0.0040, TIME * 0.0021);
	float cl = fbm(cuv);
	float threshold = mix(0.62, 0.20, overcast);
	float cmask = smoothstep(threshold, threshold + 0.26, cl);
	cmask *= smoothstep(0.0, 0.16, up);
	float lit = (0.30 + 0.55 * sun_energy) * (1.0 - night * 0.82);
	vec3 cloud_top = mix(vec3(0.55, 0.56, 0.58), vec3(0.30, 0.31, 0.34), overcast);
	vec3 cloud_col = cloud_top * lit + horizon_color.rgb * 0.25;
	col = mix(col, cloud_col, cmask * (0.40 + 0.55 * overcast));

	// Sun disc and its halo, mostly swallowed by a thick overcast.
	float sd = dot(d, normalize(sun_dir));
	float disc = smoothstep(0.99930, 0.99975, sd);
	float halo = pow(max(sd, 0.0), 260.0) * 0.55 + pow(max(sd, 0.0), 9.0) * 0.09;
	col += sun_color.rgb * (disc * 16.0 + halo) * sun_energy * (1.0 - overcast * 0.88);

	// Moon disc.
	float md = dot(d, normalize(moon_dir));
	float mdisc = smoothstep(0.99900, 0.99960, md);
	float mhalo = pow(max(md, 0.0), 900.0) * 0.30;
	col += vec3(0.74, 0.79, 0.94) * (mdisc * 2.6 + mhalo) * moon_energy * (1.0 - overcast * 0.9);

	COLOR = max(col, vec3(0.0));
}
"""
