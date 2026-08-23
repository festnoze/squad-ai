class_name MatLib
extends RefCounted

## Shared material library. Every surface of the game pulls its material from
## here so that a single instance is reused everywhere: two MeshInstance3D that
## share the same Material are batched together by the renderer, and with a few
## thousand props on screen that is the difference between 60 and 20 fps.
##
## NEVER call `duplicate()` on a material handed out by this class unless you
## really need a one off variation, and never mutate one in place: you would be
## editing the material of every wall in Normandy at once.
##
## Rendering rules paid for in blood on a previous Godot project:
##  - Albedo stays inside 0.05 .. 0.38 (see `Palette`). Brighter than that and
##    the ACES shoulder desaturates the surface towards white.
##  - `metallic <= 0.6` and `roughness >= 0.3` on anything lit, otherwise metal
##    turns into a black hole as soon as it leaves direct sunlight. The two
##    deliberate exceptions are water and glass, which are NOT metallic: a low
##    roughness there buys a sun glint, not a black surface.
##  - The textures bake their palette colour in, so textured materials keep
##    `albedo_color` white (or a mild tint) instead of multiplying twice.

## Anisotropic filtering everywhere: ground textures seen at a grazing angle are
## the whole point of turning it on in project.godot.
const FILTER_ANISO := BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC

## Size of the private terrain detail texture. Small on purpose: it is only a
## luminance modulation, it never needs to be sharp.
const _DETAIL_SIZE := 96

## Maximum number of `flat()` materials kept alive before the pool is recycled.
const _FLAT_BUDGET := 192

## Placeholder handed out for an unknown key. Deliberately a colour that exists
## nowhere in Normandy, so a typo in a material key is visible from across the
## valley rather than quietly invisible.
const MISSING_COLOR := Color(0.55, 0.05, 0.50)

static var _cache: Dictionary = {}
static var _flats: Dictionary = {}
static var _detail_tex: Texture2D = null


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Known keys: "terrain", "road", "water", "stone", "plaster", "wood",
## "roof_tile", "roof_slate", "concrete", "metal", "rust", "glass",
## "foliage", "bark", "wheat", "sandbag", "barbed_wire",
## "uniform_axis", "uniform_allied", "uniform_resistance", "skin",
## "tracer", "muzzle", "blood", "smoke", "flag_axis", "flag_allied",
## "gun_metal", "gun_wood", "marker", "cloth", "blade"
##
## Two keys beyond the contract list, added for the prop and building builders:
## "straw" (thatch, haystacks, stable bedding) and "leather" (webbing, boots,
## harness). Nothing existing was renamed to make room for them.
static func get_material(key: String) -> Material:
	if _cache.has(key):
		return _cache[key] as Material
	var mat: Material = _build(key)
	if mat == null:
		# Never hand back null: the scatter and the building generators pick
		# their keys from data, and a null material there is a hard crash at
		# instantiation time. The placeholder is a loud unshaded magenta so a
		# missing key is obvious on screen instead of silently invisible.
		push_warning("MatLib: unknown material key '%s', using the magenta placeholder." % key)
		mat = flat(MISSING_COLOR)
		_cache[key] = mat
		return mat
	mat.resource_name = "mat_" + key
	_normalise_photo_tint(mat)
	_cache[key] = mat
	return mat


## Pulls an over unity albedo tint back under 1.0 on any material that ended up
## sampling a photographic set.
##
## Several builders brighten their surface with a tint above 1.0. That was right
## while the textures were synthetic and deliberately dark, and it is wrong the
## moment a correctly exposed photograph sits underneath: the sandbags came out
## as glowing yellow blocks that broke the whole palette. The tint is rescaled
## rather than clamped per channel so the hue survives, only the exposure moves.
## Materials with no photo set keep their tint untouched.
static func _normalise_photo_tint(mat: Material) -> void:
	var standard := mat as StandardMaterial3D
	if standard == null or not standard.has_meta("photo_backed"):
		return
	var tint: Color = standard.albedo_color
	var brightest: float = maxf(tint.r, maxf(tint.g, tint.b))
	if brightest <= 1.0:
		return
	var factor: float = 1.0 / brightest
	standard.albedo_color = Color(tint.r * factor, tint.g * factor,
			tint.b * factor, tint.a)


## Flat unshaded colour material, cached per colour. For markers and vfx.
static func flat(color: Color, emissive: bool = false) -> Material:
	var key: String = "%.3f_%.3f_%.3f_%.3f_%d" % [color.r, color.g, color.b, color.a, int(emissive)]
	if _flats.has(key):
		return _flats[key] as Material
	if _flats.size() >= _FLAT_BUDGET:
		# Callers are allowed to ask for arbitrary colours, so the pool has to be
		# bounded. Dropping it wholesale is fine: the materials already handed
		# out stay alive as long as something references them.
		_flats.clear()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = color
	mat.vertex_color_use_as_albedo = true
	if color.a < 1.0:
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	if emissive:
		mat.emission_enabled = true
		mat.emission = Color(color.r, color.g, color.b, 1.0)
		mat.emission_energy_multiplier = 3.0
		mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.resource_name = "flat_" + key
	_flats[key] = mat
	return mat


## The terrain material is vertex coloured: mesh builders must write COLOR.
static func terrain_material() -> Material:
	return get_material("terrain")


static func clear_cache() -> void:
	_cache.clear()
	_flats.clear()
	_detail_tex = null


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

static func _build(key: String) -> Material:
	match key:
		"terrain": return _build_terrain()
		"road": return _build_road()
		"water": return _build_water()
		"stone": return _build_stone()
		"plaster": return _build_plaster()
		"wood": return _build_wood()
		"roof_tile": return _build_roof_tile()
		"roof_slate": return _build_roof_slate()
		"concrete": return _build_concrete()
		"metal": return _build_metal()
		"rust": return _build_rust()
		"glass": return _build_glass()
		"foliage": return _build_foliage()
		"bark": return _build_bark()
		"wheat": return _build_wheat()
		"blade": return _build_grass_blade()
		"sandbag": return _build_sandbag()
		"barbed_wire": return _build_barbed_wire()
		"uniform_axis": return _build_uniform(Palette.FELDGRAU)
		"uniform_allied": return _build_uniform(Palette.KHAKI)
		"uniform_resistance": return _build_uniform(Palette.RESISTANCE)
		"skin": return _build_skin()
		"tracer": return _build_tracer()
		"muzzle": return _build_muzzle()
		"blood": return _build_blood()
		"smoke": return _build_smoke()
		"flag_axis": return _build_flag(Color(0.23, 0.05, 0.04))
		"flag_allied": return _build_flag(Color(0.10, 0.12, 0.24))
		"gun_metal": return _build_gun_metal()
		"gun_wood": return _build_gun_wood()
		"marker": return _build_marker()
		"cloth": return _build_cloth()
		"straw": return _build_straw()
		"leather": return _build_leather()
	return null


## Common skeleton for an opaque, textured, triplanar surface.
## Triplanar mapping is used on purpose: the mesh builders assemble buildings
## from boxes and extruded polygons whose UVs are inconsistent (and sometimes
## absent). Object space triplanar gives every one of them a correct, stable
## mapping without asking anybody to unwrap anything.
static func _textured(texture_name: String, world_scale: float, roughness: float,
		metallic: float = 0.0, world_space: bool = false) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = Tex.get_texture(texture_name)
	mat.texture_filter = FILTER_ANISO
	mat.roughness = roughness
	mat.metallic = metallic
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = world_space
	mat.uv1_scale = Vector3(world_scale, world_scale, world_scale)
	mat.uv1_triplanar_sharpness = 2.0
	_attach_photo_maps(mat, texture_name)
	return mat


## Hangs the normal and the packed AO/roughness/metalness maps of a photographic
## set onto a material, when that set is installed. Without this the photo albedo
## would render as a flat sticker: the relief and the varying roughness are what
## actually make stone read as stone.
##
## Godot has no ORM channel support on StandardMaterial3D, so the packed map is
## bound three times, once per channel, which is exactly what the engine expects.
## The scalar `roughness` and `metallic` still multiply their texture, so they
## keep acting as a per material trim.
static func _attach_photo_maps(mat: StandardMaterial3D, texture_name: String) -> void:
	if not Tex.has_photo(texture_name):
		return
	# Marked so get_material() can rescale an over unity tint afterwards, once
	# the calling builder has had its say on albedo_color.
	mat.set_meta("photo_backed", true)
	var normal_map: Texture2D = Tex.photo(texture_name, Tex.MAP_NORMAL)
	if normal_map != null:
		mat.normal_enabled = true
		mat.normal_texture = normal_map
		mat.normal_scale = 1.0
	var arm: Texture2D = Tex.photo(texture_name, Tex.MAP_ARM)
	if arm == null:
		return
	mat.ao_enabled = true
	mat.ao_texture = arm
	mat.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	mat.ao_light_affect = 0.4
	mat.roughness_texture = arm
	mat.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	mat.metallic_texture = arm
	mat.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE


static func _build_terrain() -> Material:
	# Vertex colours carry the biome tint (Heightfield.color_at), so the only
	# thing the texture may do is modulate luminance. Its mean sits near 0.83:
	# a mean of 0.5 (a plain noise map) would halve the ground albedo and crush
	# the whole landscape into mud.
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.albedo_color = Color(1.0, 1.0, 1.0, 1.0)
	mat.albedo_texture = _ground_detail()
	mat.texture_filter = FILTER_ANISO
	mat.roughness = 0.95
	mat.metallic = 0.0
	mat.metallic_specular = 0.25
	# World space triplanar: object space would restart the pattern on every
	# 64 m chunk and print a visible grid across the whole map.
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = true
	mat.uv1_scale = Vector3(0.31, 0.31, 0.31)
	mat.uv1_triplanar_sharpness = 1.4
	# The photographic ground set contributes its relief and its roughness, but
	# NOT its albedo: the biome tint lives in the vertex colours, and a photo
	# albedo on top would multiply two colours and mud the whole landscape.
	# Relief alone is most of the visual gain anyway.
	var normal_map: Texture2D = Tex.photo("grass", Tex.MAP_NORMAL)
	if normal_map != null:
		mat.normal_enabled = true
		mat.normal_texture = normal_map
		mat.normal_scale = 0.85
	var arm: Texture2D = Tex.photo("grass", Tex.MAP_ARM)
	if arm != null:
		mat.ao_enabled = true
		mat.ao_texture = arm
		mat.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
		mat.ao_light_affect = 0.35
		mat.roughness_texture = arm
		mat.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	return mat


static func _build_road() -> Material:
	var mat := _textured("road", 0.22, 0.92, 0.0, true)
	mat.metallic_specular = 0.3
	return mat


static func _build_stone() -> Material:
	return _textured("stone", 0.40, 0.86)


static func _build_plaster() -> Material:
	return _textured("plaster", 0.34, 0.92)


static func _build_wood() -> Material:
	var mat := _textured("wood", 0.50, 0.82)
	mat.metallic_specular = 0.35
	return mat


static func _build_roof_tile() -> Material:
	return _textured("roof_tile", 0.60, 0.78)


static func _build_roof_slate() -> Material:
	var mat := _textured("roof_slate", 0.50, 0.62)
	mat.metallic_specular = 0.55
	return mat


static func _build_concrete() -> Material:
	return _textured("concrete", 0.25, 0.90)


static func _build_metal() -> Material:
	# metallic capped at 0.55, roughness kept well above 0.3: a fully metallic,
	# smooth surface reads as pure black in overcast Normandy light.
	var mat := _textured("metal", 0.55, 0.48, 0.55)
	mat.metallic_specular = 0.5
	return mat


static func _build_rust() -> Material:
	# Same plate, eaten through. The tint stays a mild multiplier so the final
	# albedo remains inside the safe band.
	var mat := _textured("metal", 0.45, 0.88, 0.10)
	mat.albedo_color = Color(1.30, 0.78, 0.62, 1.0)
	return mat


static func _build_glass() -> Material:
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(0.09, 0.11, 0.12, 0.30)
	# Low roughness exception: metallic is 0, so there is no black metal risk,
	# and window panes need a real specular highlight to read as glass.
	mat.roughness = 0.10
	mat.metallic = 0.0
	mat.metallic_specular = 0.85
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	return mat


static func _build_foliage() -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = Tex.get_texture("leaves")
	mat.texture_filter = FILTER_ANISO
	# Cards are double sided and cut out, never blended: alpha blending on a few
	# thousand leaf quads costs a fortune and sorts badly.
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mat.alpha_scissor_threshold = 0.5
	mat.roughness = 0.94
	mat.metallic = 0.0
	mat.metallic_specular = 0.15
	# Leaves let some light through from behind, which is what stops a hedge
	# from turning into a black wall when the sun is on the far side.
	mat.backlight_enabled = true
	mat.backlight = Color(0.07, 0.11, 0.05)
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_bark() -> Material:
	return _textured("bark", 1.00, 0.93)


## A single blade of grass or of wheat, cut out of the CC0 atlas.
##
## Blades are the one family the photographic sets cannot serve directly: they
## need a real alpha cut out, and a flat photograph has none. `Tex.blade_texture`
## merges the atlas colour with its separate opacity map and crops one blade, so
## a blade quad shows a blade. When the atlas is absent it falls back to the
## synthesised pattern and the game still runs, it just looks coarser.
##
## `alpha_antialiasing_mode` matters here: with a plain scissor at distance the
## mip chain thins the alpha until whole fields dissolve into torn rags, which is
## exactly how this looked before. Alpha to coverage keeps the silhouette.
static func _build_blade(tint: Color, backlight: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	var cutout: Texture2D = Tex.blade_texture()
	mat.albedo_texture = cutout if cutout != null else Tex.get_texture("wheat")
	mat.albedo_color = tint
	mat.texture_filter = FILTER_ANISO
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mat.alpha_scissor_threshold = 0.42
	mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE
	mat.roughness = 0.92
	mat.metallic = 0.0
	mat.metallic_specular = 0.18
	# Thin vegetation is lit from behind as much as from the front.
	mat.backlight_enabled = true
	mat.backlight = backlight
	mat.vertex_color_use_as_albedo = true
	return mat


## Meadow grass. Kept apart from "foliage", which also dresses tree canopies:
## sharing one key would paste blades of grass over every crown in the bocage.
## The tint runs above 1.0 on purpose. The atlas photograph is a blade shot in
## shade, so its own albedo is already low, and the chain that reaches the screen
## multiplies it three more times (this tint, the mesh vertex colour, and the
## per instance colour the scatter pushes through the MultiMesh). Left at unity
## the whole meadow came out as black spikes standing in a bright field. This is
## not a photo backed material, so `_normalise_photo_tint` leaves it alone.
static func _build_grass_blade() -> Material:
	return _build_blade(Color(1.75, 2.05, 1.25, 1.0), Color(0.16, 0.24, 0.09))


static func _build_wheat() -> Material:
	# Same cut out blade, pushed to ripe gold.
	var cutout: Texture2D = Tex.blade_texture()
	if cutout != null:
		return _build_blade(Color(2.45, 1.95, 0.90, 1.0), Color(0.26, 0.20, 0.07))
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = Tex.get_texture("wheat")
	mat.texture_filter = FILTER_ANISO
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mat.alpha_scissor_threshold = 0.5
	mat.roughness = 0.90
	mat.metallic = 0.0
	mat.metallic_specular = 0.20
	mat.backlight_enabled = true
	mat.backlight = Color(0.13, 0.11, 0.05)
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_sandbag() -> Material:
	var mat := _textured("dirt", 1.30, 0.97)
	mat.albedo_color = Color(1.55, 1.42, 1.05, 1.0)
	return mat


static func _build_barbed_wire() -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Palette.shade(Palette.METAL, 1.25)
	mat.roughness = 0.55
	mat.metallic = 0.45
	mat.metallic_specular = 0.5
	# Wire is modelled as thin crossed strips, so both faces must draw.
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	return mat


static func _build_uniform(color: Color) -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.96
	mat.metallic = 0.0
	mat.metallic_specular = 0.12
	# Soldiers are built from boxes and tinted per instance through COLOR.
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_skin() -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Palette.SKIN
	mat.roughness = 0.68
	mat.metallic = 0.0
	mat.metallic_specular = 0.30
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_tracer() -> Material:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Palette.TRACER
	mat.emission_enabled = true
	mat.emission = Palette.TRACER
	mat.emission_energy_multiplier = 7.0
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	mat.render_priority = 2
	return mat


static func _build_muzzle() -> Material:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Palette.MUZZLE
	mat.emission_enabled = true
	mat.emission = Palette.MUZZLE
	mat.emission_energy_multiplier = 11.0
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	mat.render_priority = 3
	return mat


static func _build_blood() -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(Palette.BLOOD.r, Palette.BLOOD.g, Palette.BLOOD.b, 0.88)
	mat.roughness = 0.42
	mat.metallic = 0.0
	mat.metallic_specular = 0.55
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_smoke() -> Material:
	var mat := StandardMaterial3D.new()
	# Lit, not unshaded: smoke that ignores the sun looks like a paper cutout,
	# and unshaded Palette.SMOKE would just be a black blob.
	mat.albedo_color = Color(0.21, 0.20, 0.19, 1.0)
	mat.roughness = 1.0
	mat.metallic = 0.0
	mat.metallic_specular = 0.0
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_MIX
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.particles_anim_h_frames = 1
	mat.particles_anim_v_frames = 1
	mat.particles_anim_loop = false
	mat.disable_receive_shadows = true
	mat.render_priority = 1
	return mat


static func _build_flag(color: Color) -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Palette.clamp_albedo(color)
	mat.roughness = 0.93
	mat.metallic = 0.0
	mat.metallic_specular = 0.18
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	return mat


## The two gun materials deliberately carry NO texture at all.
##
## They used to sample the shared "metal" and "wood" sets at a large triplanar
## scale, which worked while those sets were synthetic noise. With photographic
## sets installed it stopped working: the wood set is a plank WALL and the metal
## set is diamond tread plate, so a rifle came out looking like a fence post
## bolted to a stair nosing. A weapon is the one object in the game the player
## sees from twenty centimetres away every single frame, and at that distance a
## clean shaded surface reads far better than a photograph at the wrong scale.
static func _build_gun_metal() -> Material:
	var mat := StandardMaterial3D.new()
	# Blued steel: dark, fairly smooth, and metallic enough to catch the sky.
	# Dark, but not so dark that the rifle reads as a black bar against a bright
	# sky: at 0.055 the whole silhouette collapsed into one flat shape.
	mat.albedo_color = Color(0.095, 0.100, 0.112, 1.0)
	mat.roughness = 0.34
	mat.metallic = 0.72
	mat.metallic_specular = 0.6
	mat.texture_filter = FILTER_ANISO
	return mat


static func _build_gun_wood() -> Material:
	var mat := StandardMaterial3D.new()
	# Oiled walnut stock: warm, dark, almost no specular break up.
	mat.albedo_color = Color(0.115, 0.062, 0.032, 1.0)
	mat.roughness = 0.46
	mat.metallic = 0.0
	mat.metallic_specular = 0.42
	mat.texture_filter = FILTER_ANISO
	return mat


static func _build_marker() -> Material:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(0.85, 0.80, 0.55, 0.85)
	mat.emission_enabled = true
	mat.emission = Color(0.85, 0.78, 0.50)
	mat.emission_energy_multiplier = 2.2
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	# Objective diamonds must be readable through a hedge or a farmhouse.
	mat.no_depth_test = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	mat.fixed_size = true
	mat.render_priority = 8
	return mat


static func _build_cloth() -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.21, 0.19, 0.16, 1.0)
	mat.roughness = 0.98
	mat.metallic = 0.0
	mat.metallic_specular = 0.10
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_straw() -> Material:
	# Thatch, haystacks and stable bedding. The wheat texture read at a much
	# larger scale gives the right matted, strand by strand look, and the cut
	# out is dropped because straw in bulk is a solid mass.
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = Tex.get_texture("wheat")
	mat.albedo_color = Color(1.0, 0.96, 0.86, 1.0)
	mat.texture_filter = FILTER_ANISO
	mat.roughness = 0.98
	mat.metallic = 0.0
	mat.metallic_specular = 0.12
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = false
	mat.uv1_scale = Vector3(0.75, 0.75, 0.75)
	mat.uv1_triplanar_sharpness = 2.0
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.vertex_color_use_as_albedo = true
	return mat


static func _build_leather() -> Material:
	# Webbing, boots, map cases, harness. Worn leather is dark, faintly glossy
	# and never quite uniform, so it borrows the bark grain at a small scale.
	var mat := _textured("bark", 3.0, 0.55)
	mat.albedo_color = Color(1.15, 0.92, 0.78, 1.0)
	mat.metallic_specular = 0.4
	return mat


# ---------------------------------------------------------------------------
# Water shader
# ---------------------------------------------------------------------------

const _WATER_SHADER := """
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley,
		specular_schlick_ggx, world_vertex_coords;

// Shallow Normandy water: rivers, flooded marshes and the beach edge.
// Deliberately cheap. The only clever bits are the analytic wave normal (no
// normal map, so no tangents required from the mesh builder) and the depth
// buffer read that fades the shoreline instead of stamping a hard waterline.

uniform vec4 water_color : source_color = vec4(0.05, 0.10, 0.12, 1.0);
uniform vec4 deep_color : source_color = vec4(0.02, 0.045, 0.065, 1.0);
uniform vec4 foam_color : source_color = vec4(0.30, 0.31, 0.30, 1.0);
uniform float wave_height = 0.085;
uniform float wave_speed = 0.75;
uniform float base_alpha = 0.84;
uniform float shore_fade = 1.7;
uniform float depth_range = 6.0;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 wave_n;

float wave_h(vec2 p, float t) {
	float h = sin(p.x * 0.31 + t * 1.05) * 0.50;
	h += sin(p.y * 0.24 - t * 0.83) * 0.38;
	h += sin((p.x + p.y) * 0.57 + t * 1.61) * 0.20;
	h += sin((p.x - p.y * 1.7) * 0.93 - t * 2.20) * 0.10;
	return h;
}

void vertex() {
	float t = TIME * wave_speed;
	vec2 p = VERTEX.xz;
	float h = wave_h(p, t);
	VERTEX.y += h * wave_height;
	float e = 0.4;
	float hx = wave_h(p + vec2(e, 0.0), t);
	float hz = wave_h(p + vec2(0.0, e), t);
	wave_n = normalize(vec3(
			-(hx - h) * wave_height / e,
			1.0,
			-(hz - h) * wave_height / e));
}

void fragment() {
	vec3 n_view = normalize((VIEW_MATRIX * vec4(wave_n, 0.0)).xyz);
	NORMAL = n_view;

	// Linear view space depth of whatever opaque geometry sits behind us.
	float raw = texture(depth_tex, SCREEN_UV).x;
	vec4 upos = INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, raw, 1.0);
	float scene_z = -(upos.z / upos.w);
	float water_z = -VERTEX.z;
	float thickness = max(scene_z - water_z, 0.0);

	float deep = clamp(thickness / depth_range, 0.0, 1.0);
	float edge = clamp(thickness / shore_fade, 0.0, 1.0);
	float foam = smoothstep(0.40, 0.0, thickness);

	vec3 body = mix(water_color.rgb, deep_color.rgb, deep);
	ALBEDO = mix(body, foam_color.rgb, foam * 0.55);

	float fres = pow(1.0 - clamp(dot(n_view, VIEW), 0.0, 1.0), 4.0);
	ROUGHNESS = mix(0.32, 0.11, edge);
	METALLIC = 0.0;
	SPECULAR = 0.6;
	ALPHA = clamp(mix(base_alpha, 1.0, fres) * edge + foam * 0.45, 0.0, 1.0);
}
"""


static func _build_water() -> Material:
	var shader := Shader.new()
	shader.code = _WATER_SHADER
	shader.resource_name = "water_shader"
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("water_color", Palette.WATER)
	mat.set_shader_parameter("deep_color", Color(0.02, 0.045, 0.065, 1.0))
	mat.set_shader_parameter("foam_color", Color(0.30, 0.31, 0.30, 1.0))
	mat.set_shader_parameter("wave_height", 0.085)
	mat.set_shader_parameter("wave_speed", 0.75)
	mat.set_shader_parameter("base_alpha", 0.84)
	mat.set_shader_parameter("shore_fade", 1.7)
	mat.set_shader_parameter("depth_range", 6.0)
	return mat


# ---------------------------------------------------------------------------
# Private terrain detail texture
# ---------------------------------------------------------------------------

## A tileable luminance map in roughly 0.66 .. 1.0, multiplied onto the terrain
## vertex colour. It is built here rather than in `Tex` because it is not one of
## the contract texture names and because it must NOT average 0.5 the way a
## normal noise map does.
##
## Tileability comes from the classic four shifted copies trick: blending
## n(u,v), n(u-1,v), n(u,v-1) and n(u-1,v-1) with bilinear weights makes the
## edges match exactly, whatever the underlying noise does.
static func _ground_detail() -> Texture2D:
	if _detail_tex != null:
		return _detail_tex
	var n: int = _DETAIL_SIZE
	var data := PackedByteArray()
	data.resize(n * n * 3)
	var freq: float = 5.0
	for y in n:
		var v: float = float(y) / float(n)
		for x in n:
			var u: float = float(x) / float(n)
			var a: float = Tex.noise2d(u * freq, v * freq, 2)
			var b: float = Tex.noise2d((u - 1.0) * freq, v * freq, 2)
			var c: float = Tex.noise2d(u * freq, (v - 1.0) * freq, 2)
			var d: float = Tex.noise2d((u - 1.0) * freq, (v - 1.0) * freq, 2)
			var blend: float = a * (1.0 - u) * (1.0 - v) \
					+ b * u * (1.0 - v) \
					+ c * (1.0 - u) * v \
					+ d * u * v
			# The blend compresses the range, so it is stretched back out.
			var t: float = clampf((blend - 0.34) / 0.32, 0.0, 1.0)
			var lum: float = 0.66 + t * 0.34
			var srgb: float = 1.055 * pow(lum, 1.0 / 2.4) - 0.055
			var byte: int = int(clampf(srgb * 255.0 + 0.5, 0.0, 255.0))
			var o: int = (y * n + x) * 3
			data[o] = byte
			data[o + 1] = byte
			data[o + 2] = byte
	var img := Image.create_from_data(n, n, false, Image.FORMAT_RGB8, data)
	img.generate_mipmaps()
	_detail_tex = ImageTexture.create_from_image(img)
	return _detail_tex
