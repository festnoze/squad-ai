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

void vertex() {
	tile_layer = CUSTOM0.x;
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
	vec4 tex = texture(tiles, vec3(UV, tile_layer));
	ALBEDO = tex.rgb * COLOR.rgb * albedo_scale;
	EMISSION = tex.rgb * COLOR.a * 2.5;
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
	METALLIC = 0.0;
}

