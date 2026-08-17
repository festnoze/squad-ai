class_name VoxelMaterials
## Voxel surface materials for CUBEFORGE.
##
## One ShaderMaterial per Blocks.Surface, each wired to the shared atlas
## Texture2DArray. The shaders read the vertex data described in section 3 of
## docs/CONTRACTS.md: tile layer in CUSTOM0.x, wind factor in CUSTOM0.y, baked
## light and biome tint in COLOR.rgb, emission in COLOR.a.
##
## Nothing here touches the scene tree, so the class stays usable from a tool
## script or a test harness.

## Folder holding the four voxel shaders.
const SHADER_DIR := "res://src/render/shaders/"

## Shader file per Blocks.Surface value, in enum order.
## (OPAQUE, CUTOUT, TRANSLUCENT, WATER)
const SURFACE_SHADERS: PackedStringArray = [
	"voxel_opaque.gdshader",
	"voxel_cutout.gdshader",
	"voxel_translucent.gdshader",
	"voxel_water.gdshader",
]

## Uniform names shared with the rest of the project.
const UNIFORM_TILES := "tiles"
const UNIFORM_WIND := "wind_strength"
const UNIFORM_TIME := "time_of_day"

## Declared uniform names of every shader this class has instantiated, keyed by
## the Shader resource itself. set_time() and set_wind() consult it so they never
## push a parameter into a shader that does not declare it (the translucent
## shader has no wind, the opaque one has no time of day).
static var _declared_uniforms: Dictionary = {}


## Returns an Array of Blocks.SURFACE_COUNT ShaderMaterial, indexed by
## Blocks.Surface. Loads the .gdshader files and binds the atlas.
static func build(atlas: Texture2DArray) -> Array[Material]:
	var out: Array[Material] = []
	out.resize(Blocks.SURFACE_COUNT)
	for surface in Blocks.SURFACE_COUNT:
		out[surface] = _build_surface(surface, atlas)
	return out


## Block selection outline material: unshaded black lines, vertex coloured, drawn
## on top of the world so the highlighted cube never hides behind its own face.
static func outline_material() -> Material:
	var mat := StandardMaterial3D.new()
	mat.resource_name = "voxel_outline"
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	# Multiplied by the mesh vertex colour, which defaults to white: an
	# ImmediateMesh line list needs no colour of its own to come out black.
	mat.albedo_color = Color(0.03, 0.03, 0.04, 0.88)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.no_depth_test = true
	mat.disable_receive_shadows = true
	mat.disable_fog = true
	mat.render_priority = 2
	return mat


## Pushes the time of day (0 midnight, 0.5 noon) to the materials that use it.
static func set_time(materials: Array[Material], t: float) -> void:
	_push_uniform(materials, UNIFORM_TIME, fposmod(t, 1.0))


## Global wind sway factor, 0 to freeze foliage and water.
static func set_wind(materials: Array[Material], strength: float) -> void:
	_push_uniform(materials, UNIFORM_WIND, maxf(strength, 0.0))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


static func _build_surface(surface: int, atlas: Texture2DArray) -> Material:
	var file: String = SURFACE_SHADERS[surface]
	var shader := _load_shader(SHADER_DIR + file)
	if shader == null:
		return _fallback_material(file)

	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.resource_name = file.get_basename()

	var uniforms := _uniforms_of(shader)
	if atlas != null and uniforms.has(UNIFORM_TILES):
		mat.set_shader_parameter(UNIFORM_TILES, atlas)
	elif atlas == null:
		push_warning("VoxelMaterials: no atlas given, %s will sample black" % file)

	# Water draws last among the blended surfaces so a frozen lake edge (ice)
	# composites underneath it instead of fighting for the same depth slice.
	if surface == Blocks.Surface.WATER:
		mat.render_priority = 1
	return mat


static func _load_shader(path: String) -> Shader:
	if not ResourceLoader.exists(path):
		push_error("VoxelMaterials: shader not found at %s" % path)
		return null
	var res: Resource = load(path)
	var shader := res as Shader
	if shader == null:
		push_error("VoxelMaterials: %s is not a Shader resource" % path)
		return null
	return shader


## Names of the uniforms a shader really declares, cached per Shader resource.
## The rendering server owns that list, but a headless run has no shader compiler
## and reports nothing, so the source code is scanned as a fallback.
static func _uniforms_of(shader: Shader) -> Dictionary:
	if _declared_uniforms.has(shader):
		return _declared_uniforms[shader]
	var names: Dictionary = {}
	for entry in shader.get_shader_uniform_list(false):
		var info: Dictionary = entry
		if info.has("name"):
			names[String(info["name"])] = true
	if names.is_empty():
		names = _scan_uniform_names(shader.code)
	_declared_uniforms[shader] = names
	return names


## Reads `uniform <type> <name>` declarations straight out of the shader source.
static func _scan_uniform_names(code: String) -> Dictionary:
	var names: Dictionary = {}
	if code.is_empty():
		return names
	var re := RegEx.new()
	if re.compile("(?m)^\\s*uniform\\s+[A-Za-z_][A-Za-z0-9_]*\\s+([A-Za-z_][A-Za-z0-9_]*)") != OK:
		push_warning("VoxelMaterials: uniform scanner regex failed to compile")
		return names
	for m in re.search_all(code):
		names[m.get_string(1)] = true
	return names


## Sets one uniform on every material of the array that declares it. Tolerates
## null entries and non shader materials, because the world array may be
## partially built while chunks are still streaming in.
static func _push_uniform(materials: Array[Material], uniform: String, value: Variant) -> void:
	for entry in materials:
		if entry == null:
			continue
		var mat := entry as ShaderMaterial
		if mat == null:
			continue
		var shader := mat.shader
		if shader == null:
			continue
		if _uniforms_of(shader).has(uniform):
			mat.set_shader_parameter(uniform, value)


## Last resort material used when a shader file cannot be loaded. It still shows
## the baked vertex colours, so the world stays readable instead of turning into
## an unlit black mass while the failure is reported.
static func _fallback_material(file: String) -> Material:
	push_error("VoxelMaterials: falling back to an untextured material for %s" % file)
	var mat := StandardMaterial3D.new()
	mat.resource_name = "voxel_fallback"
	mat.vertex_color_use_as_albedo = true
	mat.albedo_color = Color(1.0, 1.0, 1.0)
	mat.roughness = 1.0
	mat.metallic_specular = 0.0
	return mat
