// CUBEFORGE - alpha blended voxel surface (ice).
//
// Same vertex data contract as voxel_opaque.gdshader, minus the sway: ice never
// moves, so this shader deliberately declares no wind_strength uniform and
// VoxelMaterials.set_wind skips it.
shader_type spatial;
render_mode cull_back, blend_mix, depth_draw_opaque;

uniform sampler2DArray tiles : source_color, filter_nearest_mipmap_anisotropic, repeat_disable;
// The atlas is authored in a bright palette for readability as 2D icons. Block
// albedo is scaled down here so lit faces stay inside the linear part of the
// tone curve instead of desaturating toward white in the shoulder.
uniform float albedo_scale : hint_range(0.2, 1.0) = 0.78;
uniform float translucency : hint_range(0.0, 1.0) = 0.72;

varying flat float tile_layer;

void vertex() {
	tile_layer = CUSTOM0.x;
}

void fragment() {
	vec4 tex = texture(tiles, vec3(UV, tile_layer));
	ALBEDO = tex.rgb * COLOR.rgb * albedo_scale;
	ALPHA = tex.a * translucency;
	EMISSION = tex.rgb * COLOR.a * 2.5;
	// Slightly polished so ice catches a hint of the sun without going plastic.
	ROUGHNESS = 0.18;
	SPECULAR = 0.45;
	METALLIC = 0.0;
}

