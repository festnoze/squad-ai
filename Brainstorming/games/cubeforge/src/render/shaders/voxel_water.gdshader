// CUBEFORGE - animated water surface.
//
// Same vertex data contract as voxel_opaque.gdshader.
//
// The motion is split in two on purpose, because the water surface only carries
// vertices at block corners (one unit apart):
//
//   * the geometry gets a long swell only, wavelengths of 20 to 37 world units.
//     A sine whose wavelength approaches the vertex spacing beats against the
//     lattice and paints a regular diagonal corduroy over the whole ocean, which
//     is exactly what the earlier short wave did. Twenty units advance the phase
//     by about 18 degrees per vertex, which the lattice samples smoothly.
//   * all the small detail lives in the fragment shader as a normal
//     perturbation, three crossing ripple trains evaluated analytically. Nothing
//     there touches the geometry, so it cannot alias against the lattice at all
//     and it stays sharp right up to the camera.
//
// The swell is a function of the WORLD position, never of the chunk local one, so
// two neighbouring chunks agree on the height of their shared edge and no crack
// opens on a chunk border. The displacement is applied to every vertex of the
// column, which keeps the lowered top face (y + 0.88) welded to the side quads.
//
// cull_disabled keeps the surface visible from underneath, when the player swims.
shader_type spatial;
render_mode cull_disabled, blend_mix, depth_draw_opaque;

uniform sampler2DArray tiles : source_color, filter_nearest_mipmap_anisotropic, repeat_disable;
uniform float wind_strength : hint_range(0.0, 2.0) = 1.0;
// 0 = midnight, 0.25 = dawn, 0.5 = noon, 0.75 = dusk. Pushed by
// VoxelMaterials.set_time so the water body follows the sky mood.
uniform float time_of_day : hint_range(0.0, 1.0) = 0.30;

// The body is a Fresnel blend of three tones: a dark teal looking straight down
// into the water, a brighter green teal on the ripple crests, and the sky at
// grazing angles. That gradient is what gives a flat one block deep sheet the
// impression of depth.
uniform vec3 deep_color : source_color = vec3(0.026, 0.104, 0.121);
uniform vec3 crest_color : source_color = vec3(0.070, 0.268, 0.271);
uniform vec3 sky_reflection : source_color = vec3(0.360, 0.560, 0.720);
uniform vec3 night_reflection : source_color = vec3(0.038, 0.062, 0.115);
uniform vec3 night_body : source_color = vec3(0.014, 0.038, 0.068);

uniform float wave_amplitude : hint_range(0.0, 0.2) = 0.055;
uniform float base_alpha : hint_range(0.0, 1.0) = 0.62;
// Slope gain of the fragment ripples. Zero gives a mirror flat sheet.
uniform float ripple_strength : hint_range(0.0, 3.0) = 1.0;

varying flat float tile_layer;
varying vec3 world_pos;
varying vec3 world_normal;

void vertex() {
	tile_layer = CUSTOM0.x;
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);

	// Wave numbers of 0.30 and 0.17 rad per unit: wavelengths of 21 and 37
	// units, both far longer than a block.
	float s1 = sin(world_pos.x * 0.30 + world_pos.z * 0.11 + TIME * 0.52);
	float s2 = sin(world_pos.z * 0.17 - world_pos.x * 0.13 - TIME * 0.37);
	float swell = s1 * 0.58 + s2 * 0.42;
	VERTEX.y += swell * wave_amplitude * clamp(wind_strength, 0.0, 2.0);
}

void fragment() {
	vec4 tex = texture(tiles, vec3(UV, tile_layer));

	// Three crossing ripple trains, wavelengths of roughly 5 to 9 units. Both
	// the height and its exact gradient come out of the same sines, so the
	// shading and the crest highlight always agree.
	vec2 p = world_pos.xz;
	vec2 k1 = vec2(0.86, 0.52);
	vec2 k2 = vec2(-0.41, 1.03);
	vec2 k3 = vec2(1.31, -0.94);
	float a1 = 0.034;
	float a2 = 0.026;
	float a3 = 0.015;
	float ph1 = dot(p, k1) + TIME * 1.28;
	float ph2 = dot(p, k2) - TIME * 0.96;
	float ph3 = dot(p, k3) + TIME * 1.83;
	float ripple = a1 * sin(ph1) + a2 * sin(ph2) + a3 * sin(ph3);
	vec2 slope = k1 * (a1 * cos(ph1)) + k2 * (a2 * cos(ph2)) + k3 * (a3 * cos(ph3));
	slope *= 4.2 * ripple_strength * clamp(wind_strength, 0.0, 2.0);

	// Only the horizontal faces get the ripple normal. The side quads of a water
	// column must keep their own normal or the shading of a shoreline flips.
	vec3 nw = world_normal;
	if (abs(world_normal.y) > 0.5) {
		vec3 bumped = normalize(vec3(-slope.x, 1.0, -slope.y));
		nw = world_normal.y < 0.0 ? -bumped : bumped;
	}
	vec3 nv = normalize((VIEW_MATRIX * vec4(nw, 0.0)).xyz);
	NORMAL = nv;

	// Sun elevation proxy: -1 at midnight, 0 at dawn and dusk, +1 at noon.
	float sun = sin((time_of_day - 0.25) * 6.28318530718);
	float day = smoothstep(-0.20, 0.24, sun);

	// The atlas tile is used as fine grain on the body colour rather than as the
	// colour itself, which is what keeps the ocean from reading as a flat sheet.
	float grain = dot(tex.rgb, vec3(0.28, 0.56, 0.16));
	float shade = clamp(grain * 0.55 + ripple * 5.0 + 0.22, 0.0, 1.0);

	vec3 body = mix(deep_color, crest_color, shade);
	body = mix(night_body, body, 0.16 + 0.84 * day);
	// COLOR.rgb carries face shading, sky light and ambient occlusion, so a
	// flooded cave stays as dark as the rock around it.
	body *= COLOR.rgb;

	float facing = clamp(dot(nv, normalize(VIEW)), 0.0, 1.0);
	float fresnel = pow(1.0 - facing, 5.0);
	// Seen from below there is no sky to reflect, only the dim total internal
	// reflection of the water body itself.
	float refl = FRONT_FACING ? fresnel : fresnel * 0.16;
	vec3 mirror = mix(night_reflection, sky_reflection, day);
	body = mix(body, mirror * max(COLOR.r, 0.20), clamp(refl * (0.30 + 0.62 * day), 0.0, 1.0));

	ALBEDO = body;
	// Clearly see-through at normal incidence, because the player swims in it,
	// and closing up towards the horizon the way real water does.
	ALPHA = clamp(base_alpha + refl * 0.30, 0.0, 0.94);
	ROUGHNESS = 0.08;
	SPECULAR = 0.72;
	METALLIC = 0.0;
}
