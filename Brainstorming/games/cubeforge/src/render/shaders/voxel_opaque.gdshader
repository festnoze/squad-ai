// CUBEFORGE - opaque voxel surface (full solid cubes).
//
// Vertex data contract (see docs/CONTRACTS.md section 3):
//   UV         0..1 inside the tile
//   COLOR.rgb  face shading x sky light x ambient occlusion x biome tint
//   COLOR.a    emission 0..1
//   CUSTOM0.x  layer index inside the Texture2DArray
//   CUSTOM0.y  wind sway factor (0 static, 1 full sway)
//
// CUSTOM0 only exists in vertex(), so the layer travels to fragment() through a
// flat varying. Directional face shading is already baked in COLOR.rgb, so
// ALBEDO multiplies COLOR.rgb exactly once and never shades again.
shader_type spatial;
render_mode cull_back;

uniform sampler2DArray tiles : source_color, filter_nearest_mipmap_anisotropic, repeat_disable;
uniform sampler2DArray tiles_smooth : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform float realistic_mode : hint_range(0.0, 1.0) = 0.0;
// The atlas is authored in a bright palette for readability as 2D icons. Block
// albedo is scaled down here so lit faces stay inside the linear part of the
// tone curve instead of desaturating toward white in the shoulder.
uniform float albedo_scale : hint_range(0.2, 1.0) = 0.80;
// Chroma gain applied to the albedo before lighting. The daylight ambient is a
// bright bluish sky dome, and the tone mapper compresses the top of the range,
// so an albedo authored at its natural chroma comes out of the frame visibly
// washed out. Boosting the chroma here (never the luminance) is what makes grass
// read as grass and sand as warm sand instead of as pale sage and cream.
uniform float albedo_saturation : hint_range(0.5, 2.5) = 1.34;
uniform float wind_strength : hint_range(0.0, 2.0) = 1.0;

varying flat float tile_layer;
varying vec3 world_pos;

void vertex() {
	tile_layer = CUSTOM0.x;
	// Natural terrain corners carry a precomputed, cross-chunk-consistent height
	// adjustment. Classic mode multiplies it by zero and remains bit-identical.
	VERTEX.y += CUSTOM0.z * realistic_mode;
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float sway = CUSTOM0.y * wind_strength;
	if (sway > 0.001) {
		// World position keeps neighbouring chunks in phase: a per-chunk local
		// phase would make every chunk slide as one rigid block.
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
	vec4 crisp = texture(tiles, vec3(UV, tile_layer));
	vec4 smooth_tex = texture(tiles_smooth, vec3(UV, tile_layer));
	vec4 tex = mix(crisp, smooth_tex, realistic_mode);
	vec2 texel = 1.0 / vec2(textureSize(tiles_smooth, 0).xy);
	vec3 neighbour = texture(tiles_smooth, vec3(UV + texel, tile_layer)).rgb;
	float grain = dot(abs(neighbour - smooth_tex.rgb), vec3(0.30, 0.55, 0.15));
	float macro = sin(world_pos.x * 2.17 + world_pos.y * 1.31 + world_pos.z * 2.73) * 0.5 + 0.5;
	float detail = mix(1.0, 0.955 + macro * 0.055 + grain * 0.16, realistic_mode);
	ALBEDO = tex.rgb * COLOR.rgb * albedo_scale * detail;
	EMISSION = tex.rgb * COLOR.a * 2.5;
	ROUGHNESS = mix(1.0, 0.68, realistic_mode);
	SPECULAR = mix(0.0, 0.28, realistic_mode);
	METALLIC = 0.0;
}
