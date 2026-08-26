class_name WaterSurface
extends RefCounted
## Living water surface: the river, the flooded marshes and the eastern sea.
##
## The world still draws water as flat 128 m cells sitting exactly at
## `Heightfield.WATER_LEVEL`. Nothing moves in the vertex stage on purpose: a
## cell only carries a 3 x 3 lattice, so any displacement there would be a
## coarse, crawling wobble, and worse, a surface that lifts itself over the
## banks. Everything lives in the fragment stage instead, where the shading is
## per pixel and the plane can never climb out of its bed.
##
## Three ingredients:
##
##  - Waves. Three crossed sines over a value noise that both warps their phase
##    and adds a swell of its own, sampled three times to get a gradient, which
##    becomes the perturbed normal. Amplitude and wavelength are driven by `sea`,
##    a plain smoothstep on the world x, because the eastern sea is the only
##    water past the coast line while the river and the marshes all sit well
##    inland. Distance to the river spine would be more exact but it would mean
##    shipping the spine to the GPU for a distinction a single coordinate already
##    makes.
##
##  - Depth. Read from the depth buffer rather than passed per instance: a water
##    cell is 128 m wide while the foam fringe is a metre or two, so a single per
##    instance depth could never place it. The depth buffer gives the real water
##    column thickness per pixel, for free, and it works the same on the river,
##    in the marsh and along the beach.
##
##  - Sky. A spatial shader cannot sample the sky, so the grazing angle mixes in
##    a tint the world refreshes from the sky controller through `set_mood`.
##    Without that refresh the default is a plain daylight blue, which is the
##    fallback look rather than a broken one.
##
## Rain and storm feed `storm`, which adds a fast ripple octave and raises the
## roughness: the surface stops mirroring the sky and turns to a grey stipple.

## World x where the sea influence starts and where it is total. The beach
## profile in `Heightfield` runs from 1480 to 1960, so the sea water itself,
## which only exists past the wet sand, always lands at 1.0.
const SEA_X0 := 1500.0
const SEA_X1 := 1900.0

## Sky tint used at the two ends of `set_mood`'s warm parameter.
const DAY_TINT := Color(0.40, 0.55, 0.74)
const DUSK_TINT := Color(0.78, 0.48, 0.40)

## Shared instance. The material carries no per cell state, so one is enough for
## every water cell in the world.
static var _cache: ShaderMaterial = null


## The living water material. Always a ShaderMaterial, never null.
static func material() -> Material:
	if _cache != null:
		return _cache
	var shader := Shader.new()
	shader.code = _WATER_SHADER
	shader.resource_name = "water_surface_shader"
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("shallow_color", Color(0.070, 0.200, 0.190, 1.0))
	mat.set_shader_parameter("deep_color", Color(0.045, 0.100, 0.125, 1.0))
	mat.set_shader_parameter("foam_color", Color(0.80, 0.84, 0.83, 1.0))
	mat.set_shader_parameter("sky_tint", DAY_TINT)
	mat.set_shader_parameter("sky_energy", 1.0)
	mat.set_shader_parameter("storm", 0.0)
	mat.set_shader_parameter("sea_x0", SEA_X0)
	mat.set_shader_parameter("sea_x1", SEA_X1)
	mat.set_shader_parameter("amp_river", 0.17)
	mat.set_shader_parameter("amp_sea", 0.34)
	mat.set_shader_parameter("flow_speed", 1.15)
	mat.set_shader_parameter("base_alpha", 0.96)
	mat.set_shader_parameter("shore_fade", 0.6)
	mat.set_shader_parameter("depth_range", 3.6)
	mat.set_shader_parameter("foam_river", 0.28)
	mat.set_shader_parameter("foam_sea", 0.62)
	_cache = mat
	return _cache


## Live mood, pushed by the world a few times per second.
##
## `storm` 0 calm, 1 full squall. `sky_energy` 0 pitch black, 1 noon. `warm` 0
## a high sun, 1 a sun on the horizon. Anything that is not a ShaderMaterial is
## ignored, so the caller can hand over its fallback material blindly.
static func set_mood(mat: Material, storm: float, sky_energy: float, warm: float) -> void:
	var shaded := mat as ShaderMaterial
	if shaded == null:
		return
	shaded.set_shader_parameter("storm", clampf(storm, 0.0, 1.0))
	# The sky keeps glowing long after the sun stops lighting anything, so the
	# reflection never drops all the way down to the raw light level.
	shaded.set_shader_parameter("sky_energy", clampf(0.30 + 0.72 * sky_energy, 0.0, 1.5))
	shaded.set_shader_parameter("sky_tint", DAY_TINT.lerp(DUSK_TINT, clampf(warm, 0.0, 1.0)))


const _WATER_SHADER := """
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley,
		specular_schlick_ggx, world_vertex_coords;

uniform vec4 shallow_color : source_color = vec4(0.070, 0.200, 0.190, 1.0);
uniform vec4 deep_color : source_color = vec4(0.045, 0.100, 0.125, 1.0);
uniform vec4 foam_color : source_color = vec4(0.80, 0.84, 0.83, 1.0);
uniform vec4 sky_tint : source_color = vec4(0.40, 0.55, 0.74, 1.0);
uniform float sky_energy = 1.0;
uniform float storm = 0.0;
uniform float sea_x0 = 1500.0;
uniform float sea_x1 = 1900.0;
uniform float amp_river = 0.17;
uniform float amp_sea = 0.34;
uniform float flow_speed = 1.15;
uniform float base_alpha = 0.96;
uniform float shore_fade = 0.6;
uniform float depth_range = 3.6;
uniform float foam_river = 0.28;
uniform float foam_sea = 0.62;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 world_pos;

float hash21(vec2 p) {
	vec3 q = fract(vec3(p.x, p.y, p.x) * 0.1031);
	q += dot(q, q.yzx + 33.33);
	return fract((q.x + q.y) * q.z);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash21(i);
	float b = hash21(i + vec2(1.0, 0.0));
	float c = hash21(i + vec2(0.0, 1.0));
	float d = hash21(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

// Height field of the surface, in arbitrary units. Only its gradient is used.
// `flow` slides the whole pattern downstream, so the river reads as running
// while the sea, whose flow is zero, only bobs in place.
// `detail` fades the short wavelengths out with distance. Without it the fine
// noise falls below one ripple per pixel and turns the far water into a boiling
// stipple, which is the classic way an analytic wave normal betrays itself.
float wave_h(vec2 p, float t, float sea, vec2 flow, float detail) {
	vec2 q = (p - flow * t) * mix(1.0, 0.30, sea);
	// One noise sample, used three times: as a slow phase warp on the two main
	// sines, which is what stops the crests reading as corduroy, and as a swell
	// of its own. Warping is free here, a second noise lookup would not be.
	float n = vnoise(q * 0.22 + vec2(t * 0.05, t * 0.035));
	float h = sin(dot(q, vec2(0.33, 0.19)) + t * 1.10 + n * 2.40) * 0.62;
	h += sin(dot(q, vec2(-0.21, 0.44)) - t * 0.83 - n * 1.70) * 0.46;
	h += sin(dot(q, vec2(0.52, -0.47)) + t * 1.70) * 0.26 * detail;
	h += (n - 0.5) * 0.55;
	// Rain stipple: short, fast, and only there when the weather asks for it.
	h += (vnoise(p * 0.35 - flow * t * 1.4 + vec2(t * 0.8, t * 0.55)) - 0.5)
			* 0.90 * storm * detail;
	return h;
}

vec3 wave_normal(vec2 p, float t, float sea, vec2 flow, float amp, float detail) {
	float e = mix(0.9, 2.6, sea);
	float h0 = wave_h(p, t, sea, flow, detail);
	float hx = wave_h(p + vec2(e, 0.0), t, sea, flow, detail);
	float hz = wave_h(p + vec2(0.0, e), t, sea, flow, detail);
	float k = amp / e;
	return normalize(vec3(-(hx - h0) * k, 1.0, -(hz - h0) * k));
}

void vertex() {
	world_pos = VERTEX;
}

void fragment() {
	vec2 p = world_pos.xz;
	float sea = smoothstep(sea_x0, sea_x1, p.x);
	// North to south drift on the river, nothing on the sea.
	vec2 flow = vec2(0.0, flow_speed * (1.0 - sea));
	float amp = mix(amp_river, amp_sea, sea) * (1.0 + storm * 1.6);
	float view_dist = length(VERTEX);
	float detail = 1.0 - smoothstep(35.0, 160.0, view_dist);
	vec3 n_world = wave_normal(p, TIME, sea, flow, amp, detail);
	vec3 n_view = normalize((VIEW_MATRIX * vec4(n_world, 0.0)).xyz);
	NORMAL = n_view;

	// Water column thickness: linear view depth of the opaque geometry behind
	// us, minus our own. Land in front of the plane never reaches this code,
	// the depth test has already dropped it.
	float raw = texture(depth_tex, SCREEN_UV).x;
	vec4 upos = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	float scene_z = -(upos.z / upos.w);
	float thickness = max(scene_z + VERTEX.z, 0.0);

	float deep = clamp(thickness / depth_range, 0.0, 1.0);
	float edge = clamp(thickness / shore_fade, 0.0, 1.0);

	// Foam fringe: a bright band where the column goes thin, crawling with the
	// flow and pulsing so the waterline breathes instead of sitting still.
	float band_depth = mix(foam_river, foam_sea, sea);
	float band = smoothstep(band_depth, 0.0, thickness);
	float crawl = vnoise(p * 0.85 - flow * TIME * 0.7 + vec2(0.0, TIME * 0.12));
	float pulse = 0.5 + 0.5 * sin(thickness * mix(9.0, 2.6, sea)
			- TIME * mix(1.6, 0.9, sea) + crawl * 6.2831);
	float speckle = mix(0.55, 1.0, vnoise(p * 1.9 + vec2(TIME * 0.25, TIME * 0.11)));
	float foam = clamp(band * (0.30 + 0.70 * pulse) * speckle, 0.0, 1.0);

	// Fresnel: looking straight down shows the bottom tint, grazing angles hand
	// the pixel over to the sky.
	float fres = pow(1.0 - clamp(dot(n_view, VIEW), 0.0, 1.0), 4.0);
	vec3 body = mix(shallow_color.rgb, deep_color.rgb, deep);
	vec3 sky = sky_tint.rgb * sky_energy;

	ALBEDO = mix(mix(body, sky, fres * 0.55), foam_color.rgb, foam * 0.85);
	// A touch of the horizon carried by emission, so the reflection survives in
	// a shadow or under a cloud instead of blinking out with the diffuse term.
	EMISSION = sky * fres * 0.45 * (1.0 - foam);
	METALLIC = 0.0;
	SPECULAR = 0.5;
	ROUGHNESS = clamp(mix(0.24, 0.46, storm) + foam * 0.40, 0.0, 1.0);
	// Opacity grows with the column: a hand deep over the sand shows the sand,
	// three metres of river do not. `edge` then dissolves the last centimetres
	// so the waterline is a fade and not a stamped outline.
	float opacity = base_alpha * mix(0.52, 1.0, deep);
	ALPHA = clamp(mix(opacity, 1.0, fres) * edge + foam * 0.6, 0.0, 1.0);
}
"""
