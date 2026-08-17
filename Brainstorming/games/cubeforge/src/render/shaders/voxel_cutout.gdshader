// CUBEFORGE - alpha scissor voxel surface (leaves, glass, plants, torch).
//
// Same vertex data contract as voxel_opaque.gdshader. This is the surface where
// the wind sway actually matters: cross quads carry CUSTOM0.y = 1.0 on their top
// vertices and 0.0 at the foot, leaf cubes carry 0.35. The amplitude stays small
// (0.06 units at full sway) so foliage never tears away from its trunk.
shader_type spatial;
render_mode cull_disabled, depth_prepass_alpha;

uniform sampler2DArray tiles : source_color, filter_nearest_mipmap_anisotropic, repeat_disable;
// The atlas is authored in a bright palette for readability as 2D icons. Block
// albedo is scaled down here so lit faces stay inside the linear part of the
// tone curve instead of desaturating toward white in the shoulder.
uniform float albedo_scale : hint_range(0.2, 1.0) = 0.78;
uniform float wind_strength : hint_range(0.0, 2.0) = 1.0;

varying flat float tile_layer;

void vertex() {
	tile_layer = CUSTOM0.x;
	float sway = CUSTOM0.y * wind_strength;
	if (sway > 0.001) {
		// Phase driven by world position so adjacent chunks sway together.
		vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
		float phase = wp.x * 0.55 + wp.z * 0.43 + wp.y * 0.11;
		float gust = 0.70 + 0.30 * sin(TIME * 0.37 + wp.x * 0.11 - wp.z * 0.17);
		float amp = 0.06 * sway * gust;
		VERTEX.x += sin(TIME * 1.70 + phase) * amp;
		VERTEX.z += sin(TIME * 1.31 + phase * 1.37 + 1.7) * amp * 0.80;
		VERTEX.y += sin(TIME * 2.30 + phase * 0.70) * amp * 0.35;
	}
}

void fragment() {
	vec4 tex = texture(tiles, vec3(UV, tile_layer));
	ALBEDO = tex.rgb * COLOR.rgb * albedo_scale;
	ALPHA = tex.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	EMISSION = tex.rgb * COLOR.a * 2.5;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	METALLIC = 0.0;
}

