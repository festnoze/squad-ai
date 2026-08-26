## Material factory for the whole game.
##
## Every surface in GOAL is drawn with a StandardMaterial3D built here and never
## anywhere else, for three reasons.
##
## 1. Cost. A StandardMaterial3D is a shader variant plus a uniform buffer. The
##    stadium alone has thousands of instances (seats, spectators, boards); if
##    each builder made its own material the renderer would rebind constantly.
##    Every parameterless material is therefore cached and shared, and the
##    parameterised ones are cached per argument value.
## 2. Consistency. The stadium is lit by one low afternoon sun plus a sky
##    ambient. Roughness and metallic are what decide whether a surface reads as
##    painted steel, wet turf or latex, and those values only stay coherent if
##    one file owns them.
## 3. The double multiply trap. Tex already bakes the Palette colours into the
##    images it generates, so a textured material keeps `albedo_color` at pure
##    white: tinting an already tinted texture darkens it twice and the pitch
##    ends up looking like a car park. The only materials that carry a tint are
##    the ones whose texture is deliberately neutral detail (fabric weave) or
##    that have no texture at all.
##
## Physical intent, surface by surface:
##  - turf: fully rough dielectric with a normal map, so the mown stripes catch
##    the low sun at grazing angles instead of reading as flat paint.
##  - ball: leather is not matte. Roughness 0.34 plus a light clearcoat gives the
##    moving highlight that lets the eye read the spin, which is the entire point
##    of the truncated icosahedron mesh.
##  - posts: painted metal, so metallic stays at 0 (paint is a dielectric) and
##    the metal look comes from low roughness plus clearcoat.
##  - net: TRANSPARENCY_ALPHA_SCISSOR, never TRANSPARENCY_ALPHA. Alpha blended
##    geometry sorts per object, and a net is a box of panels that overlap
##    themselves from every angle, so blending makes it flicker. Scissor is
##    opaque as far as sorting is concerned. CULL_DISABLED because the ball is
##    seen through the back of the net from the goal camera.
##  - lamps: emissive well above 1.0 at night so they, and only they, cross the
##    glow threshold set by SkyController. Off, and reflecting the sky, by day.
##
## `daylight` below is the second half of the time of day switch, the first being
## `SkyController.evening`. Several materials carry a tiny self illumination whose
## only purpose is keeping a surface off pure black under four spotlights aimed
## somewhere else; under a sun those floors are light that answers to nothing, so
## they are cut. See `_floor()`.
##
## Engine trap, and it cost this game its whole night look once already:
## `emission_operator` defaults to EMISSION_OP_ADD. With ADD the shader computes
## `EMISSION = (emission_color + emission_texel) * emission_energy`, so leaving
## `emission` at white while supplying an `emission_texture` adds a FULL WHITE
## UNIT to every texel before the energy multiplier. A crowd painted at 0.15 and
## an advertising board painted at 0.5 both came out clipped to paper white and
## dominated every frame. Any material here that carries an emission_texture must
## either set EMISSION_OP_MULTIPLY (the texture IS the emission) or set
## `emission` to black (the texture is ADDED to nothing).
##
## Player facing text: none in this file.
class_name Mats
extends RefCounted

## Which hour the materials are built for. See `_floor()`.
##
## MUST BE SET BEFORE THE FIRST MATERIAL IS BUILT, because every material here is
## cached: flipping this later changes nothing that already exists. It is a
## build time switch, not an animation knob, and it is the second half of the
## night look, the first being `SkyController.evening`. Set both or neither.
static var daylight: bool = true

## Metres of pitch covered by one tile of the turf texture.
##
## `Meshes.pitch_plane` hands out its UV in METRES, so this material is the only
## thing that decides the physical size of a turf tile, and the number is shared
## with `Tex._TURF_STRIPES`: the mown band is a quarter of a tile at two sine
## periods, a half at one. One period on a four metre tile is a 2 m band, which is
## what a roller leaves, and it puts the 1024 texture at 256 texels per metre.
##
## Raising it widens the stripes and softens the grass; lowering it sharpens the
## grass and turns the stripes into corduroy. It was tuned on a rendered frame
## against the 7.32 m goal.
const TURF_TILE_METRES := 4.0

## Shared cache. Key is a stable string, value is a StandardMaterial3D.
static var _cache: Dictionary = {}

## Neutral tint used by every material whose texture already carries its colour.
const _NEUTRAL := Color(1.0, 1.0, 1.0, 1.0)


## --------------------------------------------------------------------------
## Internal helpers
## --------------------------------------------------------------------------

## Stable cache key for a colour keyed material. Color.to_html() clamps to
## 0..255 per channel, which would collide for the HDR colours used by the
## additive material, so the raw floats are formatted instead.
static func _colour_key(prefix: String, colour: Color) -> String:
	return "%s:%.4f,%.4f,%.4f,%.4f" % [prefix, colour.r, colour.g, colour.b, colour.a]


## Picks an emission floor for the current hour.
##
## Several materials here carry a tiny self illumination whose only job is keeping
## a surface off PURE BLACK. Under floodlights that job is real: four spots aimed
## at the penalty area reach the stands with about one percent of their energy, so
## lit alone the concrete, the seats and the net are indistinguishable from the
## night behind them.
##
## In DAYLIGHT the same floors are a bug. The sun and the sky ambient light every
## one of those surfaces for free, so an emission on top is light that answers to
## nothing: it flattens the shading it is added to, and on a large surface like
## the roof slab it reads as a self lit slab rather than as concrete in shade.
## Daylight therefore keeps only a token of each floor, or none at all.
static func _floor(night_value: float, day_value: float) -> float:
	return day_value if daylight else night_value


## The tint a material must carry once it binds a `Tex.surface_detail()` map.
##
## The map averages `Tex.DETAIL_MEAN`, deliberately (a multiplier centred on one
## has no room to brighten anything and clips its whole upper half), so the colour
## it multiplies has to be divided by the same number. The result sits ABOVE the
## `Palette` albedo band as a number, and that is correct rather than a violation:
## what the renderer sees is colour TIMES texture, whose average is exactly the
## palette colour that went in. Clamping it back into the band here would halve
## every textured surface in the stadium, which is the mistake this function
## exists to make impossible.
static func _detail_tint(colour: Color) -> Color:
	var k := 1.0 / maxf(Tex.DETAIL_MEAN, 0.01)
	return Color(colour.r * k, colour.g * k, colour.b * k, colour.a)


## Wires an optional ARM map into the three inputs it actually carries.
##
## AN ARM MAP IS NOT THREE GREYSCALE TEXTURES, it is ONE image whose channels are
## ambient occlusion (R), roughness (G) and metallic (B). Assigning it to
## `roughness_texture` and stopping there samples the RED channel, so the surface
## gets a roughness shaped like its own occlusion: the trap is silent, the render
## simply comes out wrong. Every `*_texture_channel` below is therefore mandatory.
##
## Two more things that are easy to get wrong:
##  - `roughness_texture` and `metallic_texture` MULTIPLY the scalar `roughness`
##    and `metallic` of the material, they do not replace them. A map with a mean
##    roughness of 0.70 on a material set to 0.94 lands at 0.66, so the scalar has
##    to be re-read as a gain once a map is present.
##  - the metallic channel is only wired when the source really carries one.
##    Every dielectric set in this project ships a flat zero there, and binding a
##    flat black map costs a texture fetch to multiply a zero by a zero.
##
## `ao_light_affect` stays at 0: baked occlusion belongs to the ambient term, and
## letting it bite into direct sunlight is what makes a photographed surface look
## dirty rather than shaded.
static func _wire_arm(mat: StandardMaterial3D, arm: Texture2D, metallic_is_real: bool) -> void:
	if arm == null:
		return
	mat.ao_enabled = true
	mat.ao_texture = arm
	mat.ao_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_RED
	mat.ao_light_affect = 0.0
	mat.roughness_texture = arm
	mat.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
	if metallic_is_real:
		mat.metallic_texture = arm
		mat.metallic_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_BLUE


## Attaches an optional photographic normal map, and ONLY if there is one.
##
## `normal_enabled` with no `normal_texture` is not a no-op: the shader then reads
## the fallback white texture, decodes (1, 1, 1) as a normal and tilts the whole
## surface. So the flag and the texture are always set together, or neither is.
static func _wire_normal(mat: StandardMaterial3D, normal: Texture2D, scale: float) -> void:
	if normal == null:
		return
	mat.normal_enabled = true
	mat.normal_texture = normal
	mat.normal_scale = scale


## Lays a photographic material set onto a surface built out of scaled unit cubes.
##
## WORLD TRIPLANAR, and it is not a stylistic choice. `Stadium` draws its roof
## slabs, walls, aisles and rails as ONE unit cube scaled by each instance
## transform, and `Meshes.box` bakes its UV at unit size: an 82 m roof and a 6 cm
## handrail therefore carry the same 0..1 UV, so any tiling texture is stretched
## across the roof and compressed into the rail. Triplanar in WORLD space ignores
## the UV entirely and samples on the world position, which gives every one of
## those boxes the same physical texel size, for free, whatever it was scaled to.
##
## It also gives the seating something a shared UV never can: ten thousand
## identical quads all sample the same 0..1 patch, so a texture on them is a
## constant tint, while a world projection lands every seat on a different piece
## of the sheet and breaks the lattice.
##
## `scale` is texture repeats per metre.
static func _wire_triplanar(mat: StandardMaterial3D, scale: float) -> void:
	mat.uv1_triplanar = true
	mat.uv1_world_triplanar = true
	mat.uv1_scale = Vector3(scale, scale, scale)
	# A soft blend between the three projections. Sharper than this and the seam
	# on a 45 degree face reads as a crease.
	mat.uv1_triplanar_sharpness = 1.0


## Base material with the settings every opaque surface of the game shares.
static func _base() -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	mat.diffuse_mode = BaseMaterial3D.DIFFUSE_BURLEY
	mat.specular_mode = BaseMaterial3D.SPECULAR_SCHLICK_GGX
	mat.metallic = 0.0
	mat.roughness = 0.8
	mat.albedo_color = _NEUTRAL
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	return mat


## Unshaded base, for anything that must ignore the stadium lighting.
static func _unshaded(colour: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = colour
	# A mesh with no COLOR array feeds white here, so this is always safe and it
	# lets a trail or a gizmo fade itself out with per vertex alpha.
	mat.vertex_color_use_as_albedo = true
	mat.disable_receive_shadows = true
	mat.disable_ambient_light = true
	return mat


## --------------------------------------------------------------------------
## Pitch
## --------------------------------------------------------------------------

## The pitch.
##
## `Tex.turf()` already carries the mown stripes and the `Palette` grass colour,
## whether it was synthesised or baked from a photograph, so the albedo tint stays
## neutral as always.
##
## The relief comes from the photographed normal map when the assets are there and
## from the generated one otherwise. They are NOT interchangeable in strength: the
## generated map is a finite difference of the same fractal field the albedo was
## shaded with, so the two agree by construction and it can be driven hard; the
## photographed one is a real height scan of a real lawn, an order of magnitude
## more detailed, and at the same scale it turns the pitch into gravel under a low
## sun. Half as much is what makes it read as grass.
static func turf() -> StandardMaterial3D:
	var key := "turf"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_texture = Tex.turf()

	var photo_normal := Tex.surface_normal("turf")
	if photo_normal != null:
		_wire_normal(mat, photo_normal, 0.38)
	else:
		# Grass blades are tiny. A strong normal scale at this texel density turns
		# into visible noise under the spotlights, so it stays under 1.
		_wire_normal(mat, Tex.turf_normal(), 0.75)

	mat.roughness = 0.94
	mat.metallic = 0.0
	mat.metallic_specular = 0.18
	# The grass ARM carries a real baked occlusion between the blades and a real
	# roughness variation. Metallic is flat zero in it, so it is left unbound.
	#
	# Its roughness averages 0.70 and MULTIPLIES the scalar above, which would land
	# the pitch at 0.66: glossy enough to hang a sheet of sun reflection across the
	# whole six yard box. The scalar is therefore re-read as a gain and pushed to
	# the ceiling, so the map's own variation lands around 0.70 instead.
	var arm := Tex.surface_arm("turf")
	if arm != null:
		mat.roughness = 1.0
		_wire_arm(mat, arm, false)

	# The pitch mesh hands out its UV in metres, so this is what fixes the physical
	# size of a tile and therefore the width of a mown band. See TURF_TILE_METRES.
	var tiles := 1.0 / TURF_TILE_METRES
	mat.uv1_scale = Vector3(tiles, tiles, 1.0)
	_cache[key] = mat
	return mat


static func line() -> StandardMaterial3D:
	var key := "line"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_texture = Tex.line_paint()
	# The frayed edge of the paint lives in the alpha channel. Scissor, not
	# blend: these ribbons sit one centimetre above the turf and overlap each
	# other at the corners, and blended overlaps would sort at random.
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mat.alpha_scissor_threshold = 0.4
	mat.roughness = 0.62
	mat.metallic_specular = 0.3
	# Fresh paint is slightly wetter than the grass around it, which is what
	# makes the lines pop under floodlights.
	_cache[key] = mat
	return mat


## --------------------------------------------------------------------------
## Ball and goal
## --------------------------------------------------------------------------

static func ball() -> StandardMaterial3D:
	var key := "ball"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_texture = Tex.ball_panels()
	mat.normal_enabled = true
	mat.normal_texture = Tex.ball_normal()
	mat.normal_scale = 1.0
	# Coated leather: glossy enough for a travelling highlight, never a mirror.
	mat.roughness = 0.34
	mat.metallic = 0.0
	mat.metallic_specular = 0.55
	mat.clearcoat_enabled = true
	mat.clearcoat = 0.3
	mat.clearcoat_roughness = 0.18
	# A touch of rim keeps the silhouette readable when the ball flies out of
	# the lit cone and in front of the dark stands.
	mat.rim_enabled = true
	mat.rim = 0.25
	mat.rim_tint = 0.4
	_cache[key] = mat
	return mat


static func post() -> StandardMaterial3D:
	var key := "post"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.POST_WHITE
	# Paint is a dielectric, so metallic stays at zero. The metal reading comes
	# from the low roughness and the clearcoat lobe on top.
	mat.metallic = 0.0
	mat.roughness = 0.26
	mat.metallic_specular = 0.6
	mat.clearcoat_enabled = true
	mat.clearcoat = 0.45
	mat.clearcoat_roughness = 0.1
	# The goal is what the eye is supposed to find first, and the frame is four
	# thin cylinders standing at the edge of the lit cone: seen from behind the
	# shooter almost none of the floodlight reaches the face turned towards him,
	# and the posts came out darker than the crowd behind them. This floor is tiny
	# in absolute terms (about 0.04 linear, a tenth of the lit turf) but it is
	# enough to guarantee the white frame always reads against the dark stands.
	# In daylight the sun does that job properly and the floor is dropped to a
	# third: the frame is the brightest thing in the image on its own merits, and
	# any more than this starts to flatten the cylinder shading of the posts.
	mat.emission_enabled = true
	mat.emission = Palette.POST_WHITE
	mat.emission_energy_multiplier = _floor(0.10, 0.035)
	_cache[key] = mat
	return mat


static func net() -> StandardMaterial3D:
	var key := "net"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_texture = Tex.net()
	# Mandated by the contract: alpha blending makes a self overlapping net
	# flicker, scissor does not.
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
	mat.alpha_scissor_threshold = 0.5
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	# ALPHA TO COVERAGE, and it is what turns this net from a shimmering dot
	# screen into cord. A bare scissor is a BINARY test: a texel is cord or it is
	# nothing, there is no partial coverage, so every cord edge aliases at every
	# distance and the whole mesh crawls as the camera moves. Two separate things
	# make it worse here than on a normal cut out:
	#  - the cord covers about 22 % of `Tex.net()`, so each deeper mip level
	#    averages the alpha further DOWN. Past mip 2 the average is already under
	#    a 0.5 threshold, so the test starts failing on texels that are half cord:
	#    the net thins out with distance and the survivors sparkle in and out as
	#    the sub texel sampling moves. That is the shimmer, and no threshold value
	#    fixes it on its own because the right threshold is different per mip.
	#  - the goal shows two or three layers of net at once (back, roof, side) and
	#    two aliasing grids over each other beat into a moire pattern far more
	#    visible than either one.
	#
	# Godot's alpha antialiasing solves both at the source, and it is the standard
	# foliage fix (Wyman and McGuire, "Anti Aliased Alpha Test"). It rescales the
	# sampled alpha by the mip level being read, which keeps the coverage of the
	# cord constant with distance instead of letting it evaporate, then sharpens
	# the result across one pixel with a screen space derivative and resolves the
	# edge through the MSAA coverage mask. The project runs 4x MSAA, so there are
	# four coverage steps to spend on a cord edge.
	#
	# THE REAL CUT OFF IS `alpha_antialiasing_edge`, NOT the scissor threshold.
	# The sharpening remaps alpha to (alpha - edge) / fwidth(alpha) + 0.5, which
	# leaves the value far outside 0..1, so the contract mandated 0.5 scissor test
	# that runs afterwards simply reads the sign of that expression: it stays
	# exactly 0.5 and the cord width is set here. Below the texture's own mean
	# coverage on purpose, so a cord half covering its texel still counts as cord.
	mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE_AND_TO_ONE
	mat.alpha_antialiasing_edge = 0.25
	mat.roughness = 0.72
	mat.metallic = 0.0
	mat.metallic_specular = 0.35
	# The inside of the goal is the darkest place on the pitch and the net is
	# what the player watches on a goal, so three things lift it:
	# the shadow of the frame is ignored, light bleeds through the cords, and a
	# very small self emission keeps it off pure black against the night sky.
	mat.disable_receive_shadows = true
	mat.backlight_enabled = true
	mat.backlight = Color(0.22, 0.22, 0.24, 1.0)
	mat.emission_enabled = true
	mat.emission = Palette.NET_CORD
	mat.emission_energy_multiplier = _floor(0.09, 0.03)
	_cache[key] = mat
	return mat


## --------------------------------------------------------------------------
## Characters
## --------------------------------------------------------------------------

static func jersey(colour: Color) -> StandardMaterial3D:
	var key := _colour_key("jersey", colour)
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	# The fabric texture is neutral weave detail, so tinting it here is the
	# intended use and not a double multiply.
	mat.albedo_texture = Tex.fabric()
	mat.albedo_color = Palette.clamp_albedo(colour)
	mat.roughness = 0.86
	mat.metallic = 0.0
	mat.metallic_specular = 0.24
	# Cloth catches a rim of light from the pylon behind the goal.
	mat.rim_enabled = true
	mat.rim = 0.35
	mat.rim_tint = 0.6
	_cache[key] = mat
	return mat


static func skin() -> StandardMaterial3D:
	var key := "skin"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.SKIN
	mat.roughness = 0.52
	mat.metallic = 0.0
	mat.metallic_specular = 0.42
	# Only two humanoids are ever on screen, so a little scattering is affordable
	# and it stops arms and faces reading as plastic under a hard key light.
	mat.subsurf_scatter_enabled = true
	mat.subsurf_scatter_strength = 0.22
	_cache[key] = mat
	return mat


static func glove() -> StandardMaterial3D:
	var key := "glove"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.KEEPER_GLOVE
	# Latex palm: grippy, so fairly rough, but with a broad soft highlight.
	mat.roughness = 0.62
	mat.metallic = 0.0
	mat.metallic_specular = 0.5
	mat.rim_enabled = true
	mat.rim = 0.4
	mat.rim_tint = 0.3
	_cache[key] = mat
	return mat


static func boot() -> StandardMaterial3D:
	var key := "boot"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.BOOT
	mat.roughness = 0.22
	mat.metallic = 0.0
	mat.metallic_specular = 0.65
	mat.clearcoat_enabled = true
	mat.clearcoat = 0.55
	mat.clearcoat_roughness = 0.12
	_cache[key] = mat
	return mat


## --------------------------------------------------------------------------
## Stadium
## --------------------------------------------------------------------------

## Bare concrete of the bowl: the raked steps, the perimeter wall, the roof slab.
##
## At NIGHT the four spotlights are aimed at the penalty area and reach the stands
## with about one percent of their energy, and the night ambient is a tenth of
## that again, so lit alone this material is indistinguishable from black and the
## stand loses every trace of its architecture. `Stadium` mounts its own dim
## gantry lights under the roof to model the rake, and a large emission floor is
## what keeps the steps off pure black in the corners those never reach.
##
## In DAYLIGHT the sky ambient does that for free, over the whole bowl, at a level
## the night floor cannot compete with. The floor is therefore cut to a token: the
## roof slab and the back wall are big flat surfaces facing away from the sun, and
## a real emission on them makes them glow like a light box instead of sitting in
## shade the way the eye expects a stand to.
##
## The albedo is also lifted a little in daylight, but only within the band. This
## is not a brightness trick: concrete really is a mid grey, the night value was
## pulled down so the stands would recede into the dark, and under a sun that
## makes them read as asphalt.
static func concrete() -> StandardMaterial3D:
	var key := "concrete"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.shade(Palette.STAND_CONCRETE, _floor(1.35, 1.45))
	mat.roughness = 0.95
	mat.metallic = 0.0
	mat.metallic_specular = 0.12
	mat.emission_enabled = true
	mat.emission = Palette.STAND_CONCRETE
	# No emission_texture, so EMISSION is simply emission * energy.
	#
	# This number looks enormous next to the other emission floors in this file and
	# it is not: measured on a rendered frame, the perimeter wall comes out at 20
	# of 255, against 27 for the crowd, 44 for the goal posts and 58 for the lit
	# turf. It has to be this high because of where the floor of the image really
	# sits. SkyController runs an ACES tonemap and then a contrast adjustment just
	# over 1.0, and Godot applies contrast as `mix(0.5, colour, contrast)`, which
	# pushes everything near the bottom of the tonemapped range down into the clip.
	# The whole night image therefore lives in a very narrow band, and an emission
	# an order of magnitude below the lit turf still lands on pure black. The old
	# 0.12 was one of those: the stands rendered as a void with a crowd floating
	# over it, which is precisely the "no structure" this is here to fix.
	mat.emission_energy_multiplier = _floor(0.85, 0.06)

	# The photographic set, when it is there. `Tex.surface_detail` returns a
	# NEUTRAL multiplier centred just under one, so it lays the grain, the pour
	# lines and the staining of real concrete over the palette colour above
	# WITHOUT changing what that colour is: the stands cannot brighten, which is
	# the whole reason this is a detail map and not a photographic albedo.
	#
	# Triplanar, because these surfaces are unit cubes scaled from a handrail to an
	# 82 m roof. See `_wire_triplanar`.
	var detail := Tex.surface_detail("concrete")
	if detail != null:
		mat.albedo_texture = detail
		mat.albedo_color = _detail_tint(mat.albedo_color)
		_wire_normal(mat, Tex.surface_normal("concrete"), 0.85)
		var arm := Tex.surface_arm("concrete")
		if arm != null:
			# The ARM roughness averages 0.74 and MULTIPLIES the scalar, so the
			# scalar is re-read as a gain. Only when the map is really there: raising
			# it with nothing bound would simply make the concrete rougher.
			mat.roughness = 1.0
			_wire_arm(mat, arm, false)
		# One tile every 3.3 m. Big enough that the pour lines read as formwork on
		# a wall the size of a building, small enough that the grain survives on a
		# 55 cm roof slab edge.
		_wire_triplanar(mat, 0.30)
	_cache[key] = mat
	return mat


static func seat(colour: Color) -> StandardMaterial3D:
	var key := _colour_key("seat", colour)
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	# Barely lifted in daylight, and that restraint is the lesson. The rake sits in
	# the shadow of its own roof, the seats looked dark, and lifting the plastic by
	# 40 % brought back the exact failure this material was written to cure: ten
	# thousand small bright shapes in a regular lattice, which the eye finds faster
	# than anything else in a frame, sitting in front of the crowd instead of
	# behind it. The seating is the BACKGROUND of the background. What needed
	# lifting was the crowd, and that is where the lift went.
	var tint := Palette.clamp_albedo(Palette.shade(colour, _floor(1.0, 1.05)))
	mat.albedo_color = tint
	# Moulded plastic, but MATTE moulded plastic. A seat is a small shape repeated
	# ten thousand times in a regular lattice, and the eye finds a lattice of small
	# bright shapes faster than it finds anything else in a frame. At roughness
	# 0.55 with a 0.45 specular the gantry lights lit a hard highlight on every one
	# of them, the hue washed out of the plastic, and the stand came back as a pale
	# grid brighter than the crowd sitting in it. Rough and nearly non specular
	# keeps the seating as a dark navy field with the rake read off its shading.
	mat.roughness = 0.86
	mat.metallic = 0.0
	mat.metallic_specular = 0.08
	# Same floor as the concrete, and for the same reason: the rows of seats are
	# what draws the rake from the television camera, so they may not be black.
	# Kept BELOW the concrete floor in absolute terms, for the lattice reason above,
	# and dropped to nothing in daylight where the sky ambient reaches every row.
	mat.emission_enabled = true
	mat.emission = tint
	mat.emission_energy_multiplier = _floor(0.05, 0.0)

	# NO TEXTURE, and that is a measured decision rather than an omission.
	#
	# There is a CC0 moulded seat plastic set in `assets/`, and it was tried here.
	# Its albedo measures a standard deviation of 0.49 byte levels over the whole
	# 1024 image (values run 164 to 170): it is a solid colour stored as a JPEG, and
	# multiplying the seats by it changes nothing anyone can see while costing a
	# texture fetch on ten thousand instances.
	#
	# Its ARM is worse than useless here. That roughness averages 0.36, and dropping
	# this material to a glossy plastic lights a hard specular highlight on every one
	# of ten thousand small shapes in a regular lattice, which is exactly the failure
	# the matte roughness above was written to cure.
	#
	# What actually breaks up the seating is per instance colour, and `Stadium`
	# already does that with Palette.vary over blocks of alternating SEAT_A / SEAT_B.
	_cache[key] = mat
	return mat


## Spectator sprite material.
##
## UNSHADED, on purpose, and this is the whole fix for the crowd.
##
## It used to be a lit material carrying Tex.crowd() as albedo AND the same image
## again as an emission texture. Two things went wrong with that. First, the
## brightness of the image was counted twice, once as lit albedo and once as self
## illumination. Second, and far worse, `emission` was left at white while
## `emission_operator` defaults to ADD, so the shader computed
## `(vec3(1.0) + crowd_texel) * energy`: every spectator emitted at least the
## energy multiplier no matter how dark the texture was, which is how a crowd
## painted in 0.05 .. 0.20 albedo ended up as the brightest object in the frame,
## brighter than the floodlit turf and than the white goal posts.
##
## Unshaded removes the whole class of bug rather than tuning a number down. The
## crowd is a mass of camera facing cards fifty metres from any light in the
## scene; there is no lighting information worth computing on it. What comes out
## is exactly `Tex.crowd()` times the per instance gain `Stadium` writes into the
## instance colour, which is a value this file and that one can reason about, and
## which can never blow out. Fog still applies, so the far stand still recedes.
##
## STAYS UNSHADED IN DAYLIGHT, and that is a decision rather than an oversight.
## A billboarded card has no honest normal to light: it swings to face the camera,
## so a lit crowd would brighten and dim as the player cycled the cameras, which
## is exactly the kind of instability the stands must not have. Unshaded, the mass
## is a fixed value that `Stadium` places on the contrast ladder deliberately, and
## the only thing that had to change for the sun is the size of that value, since
## the daylight exposure is lower. See `Stadium.CROWD_DAY_GAIN`.
##
## TRANSPARENT, and that is the second half of the fix. `Tex.crowd()` is a cut out
## with the spectator on alpha 1 and the seating on alpha 0. Drawn opaque, every
## sprite was a solid rectangle of painted seating and the stands came out as a
## quilt of postcards with the architecture hidden behind them; drawn as a cut
## out, a sprite is the person and the real stand is seen between the people.
##
## ALPHA BLEND rather than ALPHA_SCISSOR, which is the opposite of the rule the
## net follows, for a reason that is specific to this material. A spectator covers
## barely a third of its cell, and the crowd is minified brutally (the far stand
## is seventy metres away): pushed through the mip chain, a scissor test at any
## threshold makes the distant crowd vanish and leaves the back of the ground
## empty. Blending lets it fade into a dark busy wash instead. The usual objection
## to blending, that overlapping panels sort against each other, does not bite
## here: the spectators barely overlap, they are all within a few percent of the
## same brightness, and depth writing is off so nothing punches a hole in anything
## behind it.
static func crowd() -> StandardMaterial3D:
	var key := "crowd"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _unshaded(_NEUTRAL)
	mat.albedo_texture = Tex.crowd()
	mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_cache[key] = mat
	return mat


static func advert(index: int) -> StandardMaterial3D:
	var key := "advert:%d" % index
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var texture: ImageTexture = Tex.advert(index)
	var mat := _base()
	mat.albedo_texture = texture
	mat.roughness = 0.42
	mat.metallic = 0.0
	mat.metallic_specular = 0.5
	# Perimeter boards are LED panels, so they emit their own image.
	#
	# EMISSION_OP_MULTIPLY is not optional here. The operator defaults to ADD,
	# and with `emission` left at white ADD computes `(1.0 + texel) * energy`,
	# which adds a full white unit to every texel of the board: the boards came
	# out as flat clipped white rectangles brighter than the goal posts. MULTIPLY
	# is what "the board emits its own artwork" actually means.
	#
	# Energy is then well under 1: the board is lit as well as emitting, and the
	# two together have to stay under the goal frame on the contrast ladder. The
	# glow threshold in SkyController is always set above them, so the boards never
	# bloom and never steal a halo.
	#
	# Daylight cuts the emission to a third of the night value. A real LED board in
	# afternoon sun is the one time its own light barely matters, and the sunlit
	# component alone already puts these boards near the top of what the frame can
	# afford: they sit directly under the goal, so any brighter and the eye lands on
	# the advertising instead of on the target.
	mat.emission_enabled = true
	mat.emission_operator = BaseMaterial3D.EMISSION_OP_MULTIPLY
	mat.emission_texture = texture
	mat.emission = _NEUTRAL
	mat.emission_energy_multiplier = _floor(0.15, 0.05)
	# Boards in daylight take the shadow of the goal and of the keeper across them,
	# which is free grounding: it is only at night, where the shadow of the frame
	# would black out a whole board, that this has to be refused.
	mat.disable_receive_shadows = not daylight
	_cache[key] = mat
	return mat


static func steel() -> StandardMaterial3D:
	var key := "steel"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Palette.STEEL
	# Galvanised truss: really metallic, but weathered, so far from a mirror.
	mat.metallic = 0.88
	mat.metallic_specular = 0.5
	mat.roughness = 0.42

	# Galvanised sheet, and this is the ONE set in the project whose metallic
	# channel is real (it measures 0.996), so it is the one place `_wire_arm` is
	# asked to bind it. That map is what breaks the pylons out of a single flat
	# metal value and puts weathering down their masts.
	#
	# The scalars are re-read as gains, as always: 0.88 metallic times a map that
	# is nearly 1 stays where it was, while the roughness map averages 0.37 and
	# would take 0.42 down to 0.15, which is a chrome pylon. Pushed back to 1.0 the
	# map's own values are what the surface ends up with.
	var detail := Tex.surface_detail("steel")
	if detail != null:
		mat.albedo_texture = detail
		mat.albedo_color = _detail_tint(mat.albedo_color)
		_wire_normal(mat, Tex.surface_normal("steel"), 0.7)
		var arm := Tex.surface_arm("steel")
		if arm != null:
			mat.roughness = 1.0
			_wire_arm(mat, arm, true)
		# Masts and trusses are long and thin, so the tile is kept small enough
		# that a 1 m section still shows structure.
		_wire_triplanar(mat, 0.85)
	_cache[key] = mat
	return mat


## --------------------------------------------------------------------------
## Effects
## --------------------------------------------------------------------------

## Unshaded additive material for the flight trail and the light halos.
## Deliberately untextured: it has to stay usable on a ribbon built without UVs,
## where any albedo texture would sample texel (0, 0) and vanish. Callers shape
## the falloff with per vertex colour, which this material reads.
static func additive(colour: Color) -> StandardMaterial3D:
	var key := _colour_key("additive", colour)
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _unshaded(colour)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	# Additive geometry that writes depth occludes the additive geometry behind
	# it, which would punch holes in its own trail.
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.disable_fog = true
	_cache[key] = mat
	return mat


## Unshaded flat colour, used by debug gizmos and the target rings.
static func flat(colour: Color) -> StandardMaterial3D:
	var key := _colour_key("flat", colour)
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _unshaded(colour)
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	if colour.a < 1.0:
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_OPAQUE_ONLY
	_cache[key] = mat
	return mat


## Lamp face for the floodlight heads. Emissive at night, dark glass in daylight.
##
## At night everything the eye sees comes from the emission, which is pushed well
## past 1.0 so the lamp faces are the only thing in the scene crossing the glow
## HDR threshold.
##
## In DAYLIGHT the floodlights are OFF, and an unlit lamp is not a dim lamp: it is
## a slab of glass in front of a mirror, so it takes its whole appearance from the
## sky it reflects. Emission goes to zero, the ambient light is let back in and the
## albedo is lifted to a grey glass, which is why the pylon heads still read as
## banks of lamps at midday instead of as four black rectangles.
static func lamp() -> StandardMaterial3D:
	var key := "lamp"
	if _cache.has(key):
		return _cache[key] as StandardMaterial3D
	var mat := _base()
	mat.albedo_color = Color(0.06, 0.06, 0.07, 1.0) if not daylight else Color(0.30, 0.32, 0.35, 1.0)
	mat.roughness = 0.2
	mat.metallic = _floor(0.0, 0.55)
	mat.metallic_specular = 0.8
	mat.emission_enabled = not daylight
	mat.emission = Palette.FLOODLIGHT
	mat.emission_energy_multiplier = _floor(6.0, 0.0)
	mat.disable_receive_shadows = true
	mat.disable_ambient_light = not daylight
	_cache[key] = mat
	return mat


static func clear_cache() -> void:
	_cache.clear()
