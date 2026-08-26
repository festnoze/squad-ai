class_name Tex
extends RefCounted
## Every texture in GOAL, synthesised from integer hashes at boot.
##
## Every generator here has to earn its pixels. None of them is a flat fill: the
## turf is real fractal noise, the ball is a real truncated icosahedron atlas, the
## net is a real cut-out and the crowd is two thousand individually coloured
## people.
##
## ---------------------------------------------------------------------------
## THE OPTIONAL PHOTOGRAPHIC LAYER - read this before touching `_photo()`
## ---------------------------------------------------------------------------
## A folder of CC0 photographic material sets may be present under
## `res://assets/textures/`. It is an ENHANCEMENT AND NEVER A DEPENDENCY.
##
## The rule is absolute and every function below obeys it: THE PROCEDURAL
## GENERATORS ARE THE TRUTH. Deleting `assets/` must leave the game fully
## playable, only coarser. Nothing here ever assumes a file exists, nothing here
## pushes an error when one is missing, and every entry point that can only be
## answered from a file (`surface_detail`, `surface_normal`, `surface_arm`)
## returns `null` rather than a placeholder, so the caller keeps the flat colour
## it already had.
##
## Two things are loaded, and they are loaded in two different ways:
##
##  - a photo that has to be BAKED INTO a generated image (the turf) is read
##    through `_photo()`, which pulls the imported texture back to the CPU,
##    decompresses it and hands over raw sRGB bytes plus the per channel gain
##    that brings its LINEAR mean to exactly 1.0. What is used from the photo is
##    therefore only its RATIO to its own average: the grain, the clumping and
##    the relative hue drift, never its absolute brightness. That is what keeps a
##    daylight photograph inside the `Palette` albedo band instead of blowing out
##    in the ACES shoulder, which is precisely the bug that put a wall of white
##    crowd in front of the goal once already.
##  - a photo that is USED AS IT IS (normal maps, ARM maps) is handed over as the
##    imported `CompressedTexture2D` itself, through `_asset_texture()`. Those are
##    non colour data, they are already mipmapped and GPU compressed by the
##    importer, and copying them through an `Image` would only throw that away.
##
## Engine trap, and it is silent: `Image.load_from_file()` also works on these
## paths, but it re-reads the source file, prints a warning on every call and
## breaks in an exported build. `ResourceLoader.load()` plus `Image.decompress()`
## is the path that reads what the importer actually produced.
##
## ---------------------------------------------------------------------------
## COLOUR SPACE - read this before touching a byte
## ---------------------------------------------------------------------------
## `Palette` is linear. `Image` is bytes. Godot binds a texture that feeds a
## `source_color` shader uniform (which is what `albedo_texture` is) through an
## sRGB image view, so the GPU decodes sRGB -> linear on every fetch. Writing
## linear bytes would therefore be decoded a SECOND time and the pitch would come
## out roughly half as bright as the palette says.
##
## So: every COLOUR texture stores sRGB ENCODED bytes, through `_srgb_table()`,
## and what the shader samples is exactly the linear palette value. Every NON
## colour texture (the two normal maps) stores RAW bytes, because `normal_texture`
## is not a `source_color` uniform and must not be decoded. Alpha is never
## encoded, in either case: the sRGB view only covers RGB.
##
## ---------------------------------------------------------------------------
## NOISE
## ---------------------------------------------------------------------------
## `randf()` per pixel is television static: it has no scale, so it neither tiles
## nor survives a mipmap. Everything here is built instead from `_hash2()`, an
## integer hash of the lattice coordinates, interpolated up through
## `_upsample2x()`. Because the upsample wraps at the edges, every field it
## produces TILES SEAMLESSLY, and because the hash is integer arithmetic the
## textures are byte for byte identical on every run and every machine.
##
## `_fbm_field()` is the workhorse: it starts from a coarse lattice and doubles
## its way to the target size, adding a fresh lattice at each step with a
## decaying amplitude. The final doubling deliberately adds NO new lattice: a
## fresh random value per texel is exactly the static we are trying to avoid.
## Fine detail comes from structured terms instead (grass blades, leather grain).
##
## ---------------------------------------------------------------------------
## MIPMAPS
## ---------------------------------------------------------------------------
## Everything seen in perspective calls `generate_mipmaps()` BEFORE
## `ImageTexture.create_from_image()`. Without it the turf boils and the crowd
## crawls as the camera moves. Only `ramp()` skips it, being a 1 pixel wide
## gradient that is never minified.
##
## ---------------------------------------------------------------------------
## BALL PANEL ATLAS - the convention `Meshes.ball_mesh()` MUST match
## ---------------------------------------------------------------------------
## `ball_panels()` and `ball_normal()` are 512x512 images divided into a 6 x 6
## grid of cells in NORMALISED UV space. A cell is exactly 1/6 wide and 1/6 tall,
## which is not a whole number of texels, so always reason in UV, never in
## pixels.
##
##   cell index c in 0..35,  column = c % 6,  row = c / 6  (integer division)
##   cell c spans u in [column/6, (column+1)/6], v in [row/6, (row+1)/6]
##   v grows DOWNWARDS, as everywhere in Godot UV space
##
##   c in  0..11   the 12 PENTAGONS, black panel
##   c in 12..31   the 20 HEXAGONS,  white panel
##   c in 32..35   unused, filled with seam colour so a wrong UV reads as a seam
##                 rather than as garbage
##
## Inside its cell a panel is a REGULAR polygon centred on the cell centre.
## Vertex j of an n sided panel sits at
##
##   u = cu + R * cos(-PI/2 + j * TAU/n)
##   v = cv + R * sin(-PI/2 + j * TAU/n)
##
## where (cu, cv) is the cell centre and R is expressed in CELL WIDTHS:
##
##   pentagons  R = 0.400
##   hexagons   R = 0.470
##
## Vertex 0 is therefore straight above the cell centre, and the numbering runs
## clockwise on screen because v points down. The two radii are in the 1 : 1.175
## ratio of a real truncated icosahedron, whose pentagons and hexagons share an
## edge length; that is what makes the printed seam come out the same width on
## every panel of the finished ball.
##
## ---------------------------------------------------------------------------
## CACHE
## ---------------------------------------------------------------------------
## Every generator memoises into `_cache`, keyed by its arguments. The turf alone
## is a million pixels of fractal noise; regenerating it once per material would
## add seconds to the boot. The two intermediate turf float fields are cached
## too, so `turf()` and `turf_normal()` share one height field - which is also
## the only way the normal map can line up with what you can actually see.

const _TURF_SIZE := 1024
const _BALL_SIZE := 512
const _NET_SIZE := 256
const _CROWD_SIZE := 512
const _CROWD_ATLASES: PackedStringArray = [
	"crowd/stadium_spectators_atlas.png",
	"crowd/stadium_spectators_atlas_02.png",
]
const _STADIUM_SEAT := "seats/stadium_seat_albedo.png"
const _LINE_SIZE := 256
const _FABRIC_SIZE := 256
const _ADVERT_W := 512
const _ADVERT_H := 128

## Mown bands per texture tile, as full sine periods, so a tile carries twice
## this many visible bands. An integer count is what keeps the tiling seamless.
##
## ONE, not two, and the number is tied to `Mats.TURF_TILE_METRES`. The pitch mesh
## hands out its UV in METRES, so the tile is whatever the turf material scales it
## to, and a band is a QUARTER of a tile at two periods. At the old pairing (one
## metre per tile, two periods) a mown band came out 25 cm wide: fine corduroy,
## not a rolled pitch, and it made the whole surface fizz under the sun. One
## period on a four metre tile gives 2 m bands, which is what a roller leaves, and
## it puts the texel density at 256 per metre so a blade clump is 4 mm wide.
const _TURF_STRIPES := 1
## How far the baked scuffing is allowed to pull the turf towards GRASS_WORN.
##
## It used to be 0.60, and it had to come down when the tile grew from one metre
## to four. The wear field is LOW FREQUENCY, so at a metre per tile its patches
## were 40 cm of invisible mottle; at four metres they are metre wide blobs that
## repeat seventeen times across the pitch, and on a rendered frame that repeat
## read plainly as a quilt over the middle distance. The honest scuffing is the
## `Pitch` scuff MultiMesh, which is placed where the game was actually played and
## never repeats at all. What is left here is only the faint unevenness of a real
## surface.
const _TURF_WEAR_BITE := 0.16
## A blade clump is one texel wide and this many texels tall.
const _BLADE_LENGTH := 6
const _BLADE_AMPLITUDE := 0.55
const _TURF_NORMAL_STRENGTH := 5.5

const _ATLAS_COLS := 6
const _PENTA_COUNT := 12
const _PANEL_COUNT := 32
const _PENTA_RADIUS := 0.400
const _HEXA_RADIUS := 0.470
## Printed seam border, in cell widths. About three texels at 512.
const _SEAM_WIDTH := 0.030

const _NET_PERIOD := 32
const _NET_HALF_CORD := 1.5

## Spectator grid of crowd(). It is deliberately coarse: `Stadium` crops ONE cell
## per spectator sprite, so a cell is what a single person is drawn from, and at
## 512 pixels a 64 x 34 grid left only 8 x 15 texels per person, which is why the
## old crowd read as a wall of pale blobs rather than as people. 32 x 22 gives
## 16 x 23 texels each, enough for a torso, a head and dark seating around them.
const _CROWD_SEATS := 32
const _CROWD_ROWS := 22
const _CROWD_STRIDE := 9

## The stands are the darkest thing in a floodlit night match, and the crowd has
## to sit BELOW the pitch, the goal and the keeper on the contrast ladder. The
## palette colours a spectator is drawn from are legal albedos for a lit surface,
## so they are scaled down hard here: a spectator lands around 0.10 .. 0.20
## linear, against a pitch that sits near 0.35.
const _CROWD_BODY_GAIN := 0.34
## Seating is darker still, so the gaps between spectators read as holes.
const _CROWD_SEAT_GAIN := 0.24
## One spectator in twenty wears something pale that catches the stand lighting.
## Those are the only glints allowed in the mass, and the gain is DELIBERATELY
## modest: `Stadium` applies a second, independent glint on top of this one, and
## when both landed on the same spectator the old 2.1 blew straight through the
## tonemap and put pure white rectangles all over the stand.
const _CROWD_GLINT_GAIN := 1.45
const _CROWD_GLINT_ODDS := 0.05

## Cloud panorama. Equirectangular, so the width is twice the height and one full
## turn of the horizon fits across it. It is fed to
## ProceduralSkyMaterial.sky_cover, which ADDS it to the sky gradient rather than
## replacing it, so the image is black wherever the sky must stay bare.
const _CLOUD_W := 1024
const _CLOUD_H := 512
## Coverage. Noise below the threshold is clear sky, and the band above it is the
## soft edge a cloud fades in across. A high threshold with a wide edge is what
## makes broken cumulus rather than a grey overcast.
const _CLOUD_COVER := 0.585
const _CLOUD_SOFT := 0.30
## Peak radiance a cloud adds to the sky. It is ADDED to a zenith that sits around
## 0.09 and a horizon around 0.55, so this puts a cloud top comfortably brighter
## than the blue behind it without ever reaching the glow threshold.
const _CLOUD_GAIN := 0.46

const _ADVERT_DESIGNS := 6
## Every colour of the artwork is scaled by this on the way in. A perimeter board
## is both LIT by the pylons and EMISSIVE, so its painted value is counted roughly
## twice, and the boards form an unbroken band right across the frame at the exact
## height of the goal line. Painted at full palette strength that band came out
## brighter than the goal posts and pulled the eye off the goal, which is the one
## thing the whole art direction is built to avoid.
const _ADVERT_GAIN := 0.60

## Resolution of the linear -> sRGB byte table. 4096 keeps the quantisation step
## below one output level even at the bottom of the curve, where sRGB is steep
## and a coarse table would band the shadows.
const _LUT_SIZE := 4096
## _LUT_SIZE - 1 as a float constant, so the pixel loops never convert it.
const _LUT_SCALE := 4095.0

const _KEY_TURF_HEIGHT := "field:turf_height"
const _KEY_TURF_WEAR := "field:turf_wear"

## --------------------------------------------------------------------------
## Optional photographic assets. See the class comment.
## --------------------------------------------------------------------------

const _ASSET_DIR := "res://assets/textures/"
const _ASSET_ALBEDO := "_albedo.jpg"
const _ASSET_NORMAL := "_normal.jpg"
const _ASSET_ARM := "_arm.jpg"

## Side of a baked detail texture. Half the source, on purpose: a stand wall is
## tiled every three metres, so 512 is still 170 texels per metre, and halving the
## side quarters the bake loop, which is a quarter of a million texels of GDScript
## either way.
const _DETAIL_SIZE := 512
## Mean LINEAR value a `surface_detail()` texture is centred on, and the number
## every material that uses one has to divide its own albedo by.
##
## IT IS A HALF, NOT A NINE TENTHS, and getting that wrong is the whole reason
## the first pass of this work shipped invisible textures. A detail map is
## MULTIPLIED onto a palette albedo, so the obvious choice is to centre it near
## 1.0 and change nothing. But a texture cannot go above 1.0: centred at 0.93 the
## entire bright half of a photograph clips to white, and the concrete came out at
## a measured standard deviation of SIX byte levels, which on screen is a flat
## grey wall. Centred at a half, the same photograph has room to swing both ways.
##
## The cost is that the multiply is no longer neutral, so a material that binds a
## detail map must scale its `albedo_color` by `1.0 / DETAIL_MEAN`. That colour
## then sits above the `Palette` band ON PAPER while the albedo the renderer
## actually sees, colour times texture, averages exactly what the palette said.
## See `Mats._detail_tint`, which is the only place that division is done.
const DETAIL_MEAN := 0.50
## Gain on the photograph's own contrast in the ratio remap, for the surfaces of
## the stadium.
##
## ABOVE ONE, which is not what it should be, and the reason is measured rather
## than assumed. These CC0 sets are clean, evenly lit studio scans, and their
## albedos carry almost no variation at all: over the source images the standard
## deviation of the green channel is 5.7 byte levels for the concrete, 7.1 for the
## painted metal and 4.1 for the galvanised steel, out of 255. Passed through at
## unit gain a stand wall would come back a flat fill with a rounding error on it,
## which is a texture nobody can see and a texture fetch nobody should pay for.
##
## What variation there IS, is real: pits, pour lines, staining, chipped paint. So
## it is amplified rather than invented. The `_RATIO_MIN` / `_RATIO_MAX` clamp
## still holds, so no amount of gain can drive a texel out of the band.
##
## (The one set this cannot rescue is the moulded seat plastic, whose albedo
## measures a standard deviation of 0.49 byte levels: it is a solid colour with a
## file size, and the seats are drawn without it. See `Mats.seat`.)
const _DETAIL_STRENGTH := 1.60
## How much of the grass photograph's contrast survives on the pitch. Higher than
## a wall's: a lawn photographed from straight above carries almost no baked
## lighting, only blades, so its contrast IS the detail we came for.
const _TURF_DETAIL_STRENGTH := 0.92
## Hard stops on the ratio, so one blown highlight or one black speck in a source
## JPEG can never become a hole in a surface.
const _RATIO_MIN := 0.12
const _RATIO_MAX := 2.60

static var _cache: Dictionary = {}
static var _srgb_lut: PackedByteArray = PackedByteArray()
static var _linear_lut: PackedFloat32Array = PackedFloat32Array()


## Mown turf: fine blade noise plus the roller stripe pattern. 1024x1024, tiles.
##
## THE STRIPES ARE THE POINT and they are always synthesised here, whatever else
## is available: they are a per row function of the tile, so they stay exactly as
## wide and as seamless as `_TURF_STRIPES` says.
##
## What the optional photographs change is the GRAIN INSIDE a band, never the
## band. Two CC0 lawns are used, and using two is the whole trick: the light band
## takes its detail from one and the dark band from the other, so the stripe reads
## as grass laid in two directions rather than as one lawn with a gradient painted
## over it. Both are reduced to their ratio to their own mean (see the class
## comment), so the average colour of a band is still exactly the `Palette` grass
## it always was, and the finished image cannot leave the albedo band.
##
## With a photograph present the hashed blade field is dropped rather than added
## on top: two independent grains multiplied together is noise, and the whole
## point of the photograph is that its grain is real. That also means the fractal
## height field is never built on that path, which is most of a second of boot.
static func turf() -> ImageTexture:
	var key := "turf"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _TURF_SIZE
	var wear := _turf_wear_field()
	var lut := _srgb_table()

	# The two photographic lawns, if the assets folder is there at all.
	var photo_light := _photo("turf" + _ASSET_ALBEDO, n)
	var photo_dark := _photo("turf_stripe" + _ASSET_ALBEDO, n)
	if photo_dark.is_empty():
		# One lawn is enough: both bands then share a grain and only the palette
		# colour separates them, which is exactly the pre asset look.
		photo_dark = photo_light
	var has_photo := not photo_light.is_empty()
	var light_data := PackedByteArray()
	var dark_data := PackedByteArray()
	var light_gain := PackedFloat32Array()
	var dark_gain := PackedFloat32Array()
	var inv := _linear_table()
	if has_photo:
		light_data = photo_light["data"]
		light_gain = photo_light["gain"]
		dark_data = photo_dark["data"]
		dark_gain = photo_dark["gain"]

	# Only the fallback path needs the fractal blade field, and building it costs
	# a million texels of noise, so it is asked for only when it is used.
	var height := PackedFloat32Array()
	if not has_photo:
		height = _turf_height_field()

	# The roller bands are constant along u, so their profile is a per row value.
	# `sin` pushed through a hard clamp gives broad FLAT bands with a soft edge,
	# which is what a roller actually leaves. The multiplier has to be big: a
	# gentle sine reads as a stain, and the stripes are the single feature that
	# says "professional pitch" the moment the camera comes up.
	var stripe := PackedFloat32Array()
	stripe.resize(n)
	for j in n:
		var phase := (float(j) / float(n)) * float(_TURF_STRIPES) * TAU
		stripe[j] = clampf(sin(phase) * 3.4, -1.0, 1.0) * 0.5 + 0.5

	var lr := Palette.GRASS_LIGHT.r
	var lg := Palette.GRASS_LIGHT.g
	var lb := Palette.GRASS_LIGHT.b
	var dr := Palette.GRASS_DARK.r
	var dg := Palette.GRASS_DARK.g
	var db := Palette.GRASS_DARK.b
	var wr := Palette.GRASS_WORN.r
	var wg := Palette.GRASS_WORN.g
	var wb := Palette.GRASS_WORN.b

	var strength := _TURF_DETAIL_STRENGTH

	var data := PackedByteArray()
	data.resize(n * n * 3)
	var p := 0
	for j in n:
		var s := stripe[j]
		var row := j * n
		for i in n:
			var wv := wear[row + i]
			# The band edge wanders, but it wanders on the LOW frequency field:
			# a roller drifts over metres, it does not jitter from blade to
			# blade. Wobbling with the fine field instead would dissolve the
			# stripe into the noise, which is exactly what it used to do.
			var t := clampf(s + (wv - 0.5) * 0.20, 0.0, 1.0)
			var cr := dr + (lr - dr) * t
			var cg := dg + (lg - dg) * t
			var cb := db + (lb - db) * t
			if has_photo:
				# Ratio to the photograph's own mean, blended across the stripe so
				# the two lawns cross fade exactly where the mown band does.
				var q := p
				var ra := inv[light_data[q]] * light_gain[0]
				var ga := inv[light_data[q + 1]] * light_gain[1]
				var ba := inv[light_data[q + 2]] * light_gain[2]
				var rb := inv[dark_data[q]] * dark_gain[0]
				var gb := inv[dark_data[q + 1]] * dark_gain[1]
				var bb := inv[dark_data[q + 2]] * dark_gain[2]
				# The remap is inlined rather than calling `_ratio`: three million
				# VM call frames cost more than the arithmetic inside them.
				cr = cr * clampf(1.0 + (rb + (ra - rb) * t - 1.0) * strength,
						_RATIO_MIN, _RATIO_MAX)
				cg = cg * clampf(1.0 + (gb + (ga - gb) * t - 1.0) * strength,
						_RATIO_MIN, _RATIO_MAX)
				cb = cb * clampf(1.0 + (bb + (ba - bb) * t - 1.0) * strength,
						_RATIO_MIN, _RATIO_MAX)
			else:
				var lum := 0.82 + height[row + i] * 0.34
				cr = cr * lum
				cg = cg * lum
				cb = cb * lum
			# Wear only bites at the very top of the low frequency field, so the
			# scuffed ground comes as a few honest patches rather than as a
			# camouflage pattern over the whole pitch.
			var w := clampf((wv - 0.74) * 3.4, 0.0, 1.0) * _TURF_WEAR_BITE
			cr = cr + (wr - cr) * w
			cg = cg + (wg - cg) * w
			cb = cb + (wb - cb) * w
			data[p] = lut[int(clampf(cr, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(cg, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(cb, 0.0, 1.0) * _LUT_SCALE)]
			p += 3

	var tex := _make_texture(n, n, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## Normal map matching turf(). Same size, tiles.
##
## Derived from the very same height field `turf()` shades with, by central
## finite differences. That is the whole point: a normal map built from an
## unrelated noise makes the light disagree with the albedo, and the pitch reads
## as a flat photograph with sparkle on it.
static func turf_normal() -> ImageTexture:
	var key := "turf_normal"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var data := _normal_bytes(_turf_height_field(), _TURF_SIZE, _TURF_NORMAL_STRENGTH, true)
	var tex := _make_texture(_TURF_SIZE, _TURF_SIZE, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## Painted line paint with a slightly frayed edge, for decals. 256x256.
##
## v runs ACROSS the width of the line, u runs along it and tiles. The alpha
## channel carries the coverage, and the RGB fades towards grass at the frayed
## edge as well, so the texture still looks right if it is ever used opaque.
static func line_paint() -> ImageTexture:
	var key := "line_paint"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _LINE_SIZE
	var field := _fbm_field(8, n, 5, 0.60, 5501)
	_normalise(field)
	var lut := _srgb_table()

	var pr := Palette.LINE_WHITE.r
	var pg := Palette.LINE_WHITE.g
	var pb := Palette.LINE_WHITE.b
	var gr := Palette.GRASS_LIGHT.r * 0.7
	var gg := Palette.GRASS_LIGHT.g * 0.7
	var gb := Palette.GRASS_LIGHT.b * 0.7

	# One texel of softness, expressed in normalised v.
	var soft := float(n) / 1.6

	var data := PackedByteArray()
	data.resize(n * n * 4)
	var p := 0
	for j in n:
		var vv := (float(j) + 0.5) / float(n)
		var row := j * n
		for i in n:
			var top_edge := 0.055 + field[2 * n + i] * 0.055
			var bot_edge := 0.945 - field[200 * n + i] * 0.055
			var cover := clampf((vv - top_edge) * soft, 0.0, 1.0)
			cover = cover * clampf((bot_edge - vv) * soft, 0.0, 1.0)
			var grain := field[row + i]
			# Bald patches where the paint has been walked off.
			if grain > 0.88:
				cover = cover * 0.35
			# Never above 1.0: this texture carries LINE_WHITE, which already sits
			# at the top of the albedo band, and a modulation over unity would
			# push the finished albedo out of it.
			var lum := 0.88 + grain * 0.12
			var edge := 1.0 - cover
			var cr := (pr * lum) + (gr - pr * lum) * edge
			var cg := (pg * lum) + (gg - pg * lum) * edge
			var cb := (pb * lum) + (gb - pb * lum) * edge
			data[p] = lut[int(clampf(cr, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(cg, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(cb, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 3] = int(clampf(cover, 0.0, 1.0) * 255.0)
			p += 4

	var tex := _make_texture(n, n, Image.FORMAT_RGBA8, data, true)
	_cache[key] = tex
	return tex


## The classic truncated icosahedron panel colouring, laid out for the UV of
## Meshes.ball_mesh(). Black pentagons on white, with panel seams. 512x512.
## See the atlas convention in the class comment.
static func ball_panels() -> ImageTexture:
	var key := "ball_panels"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _BALL_SIZE
	var lut := _srgb_table()
	var penta_normals := _edge_normals(5)
	var hexa_normals := _edge_normals(6)
	var penta_apothem := _PENTA_RADIUS * cos(PI / 5.0)
	var hexa_apothem := _HEXA_RADIUS * cos(PI / 6.0)

	# Leather mottle: coherent, so it survives minification, unlike a per texel
	# hash which would average out to a flat grey two mip levels down.
	var mottle := _ball_grain_field()
	var grain_base: int = 991 * 1274126177

	var wr := Palette.BALL_WHITE.r
	var wg := Palette.BALL_WHITE.g
	var wb := Palette.BALL_WHITE.b
	var kr := Palette.BALL_BLACK.r
	var kg := Palette.BALL_BLACK.g
	var kb := Palette.BALL_BLACK.b
	# The stitched seam is darker than the black panels: it is a shadowed groove.
	var seam := Palette.shade(Palette.BALL_BLACK, 0.80)
	var sr := seam.r
	var sg := seam.g
	var sb := seam.b

	var data := PackedByteArray()
	data.resize(n * n * 3)
	var p := 0
	for j in n:
		var vv := (float(j) + 0.5) / float(n) * float(_ATLAS_COLS)
		var cell_row := mini(int(vv), _ATLAS_COLS - 1)
		var py := vv - float(cell_row) - 0.5
		var row := j * n
		for i in n:
			var uu := (float(i) + 0.5) / float(n) * float(_ATLAS_COLS)
			var cell_col := mini(int(uu), _ATLAS_COLS - 1)
			var px := uu - float(cell_col) - 0.5
			var cell := cell_row * _ATLAS_COLS + cell_col

			# The polygon distance is inlined rather than called: a quarter of a
			# million VM call frames costs more than the dot products inside.
			var d := 1.0
			var br := sr
			var bg := sg
			var bb := sb
			if cell < _PENTA_COUNT:
				d = -1.0e20
				for k in 5:
					var e := px * penta_normals[k * 2] + py * penta_normals[k * 2 + 1]
					if e > d:
						d = e
				d -= penta_apothem
				br = kr
				bg = kg
				bb = kb
			elif cell < _PANEL_COUNT:
				d = -1.0e20
				for k in 6:
					var e := px * hexa_normals[k * 2] + py * hexa_normals[k * 2 + 1]
					if e > d:
						d = e
				d -= hexa_apothem
				br = wr
				bg = wg
				bb = wb

			# 0 well inside the panel, 1 on the seam and everywhere outside.
			var t := clampf((d + _SEAM_WIDTH) / _SEAM_WIDTH, 0.0, 1.0)
			var m := mottle[row + i]
			var micro: int = i * 374761393 + grain_base + j * 668265263
			micro = (micro ^ (micro >> 13)) * 1274126177
			micro = micro ^ (micro >> 16)
			# Capped at 1.0 for the same reason as the line paint: BALL_WHITE is
			# already near the ceiling of the albedo band.
			var lum := 0.86 + m * 0.12 + (float(micro & 0x3fffffff) / 1073741824.0 - 0.5) * 0.045
			var cr := br * lum
			var cg := bg * lum
			var cb := bb * lum
			cr = cr + (sr - cr) * t
			cg = cg + (sg - cg) * t
			cb = cb + (sb - cb) * t
			data[p] = lut[int(clampf(cr, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(cg, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(cb, 0.0, 1.0) * _LUT_SCALE)]
			p += 3

	var tex := _make_texture(n, n, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## Ball normal map: the seams pressed in, plus fine leather grain. 512x512.
## Same atlas convention as ball_panels(), and derived from a height field built
## with the same polygon distance, so the groove sits exactly under the printed
## seam.
static func ball_normal() -> ImageTexture:
	var key := "ball_normal"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _BALL_SIZE
	var penta_normals := _edge_normals(5)
	var hexa_normals := _edge_normals(6)
	var penta_apothem := _PENTA_RADIUS * cos(PI / 5.0)
	var hexa_apothem := _HEXA_RADIUS * cos(PI / 6.0)
	var mottle := _ball_grain_field()
	var grain_base: int = 4423 * 1274126177

	var height := PackedFloat32Array()
	height.resize(n * n)
	var q := 0
	for j in n:
		var vv := (float(j) + 0.5) / float(n) * float(_ATLAS_COLS)
		var cell_row := mini(int(vv), _ATLAS_COLS - 1)
		var py := vv - float(cell_row) - 0.5
		var row := j * n
		for i in n:
			var uu := (float(i) + 0.5) / float(n) * float(_ATLAS_COLS)
			var cell_col := mini(int(uu), _ATLAS_COLS - 1)
			var px := uu - float(cell_col) - 0.5
			var cell := cell_row * _ATLAS_COLS + cell_col

			var d := 1.0
			if cell < _PENTA_COUNT:
				d = -1.0e20
				for k in 5:
					var e := px * penta_normals[k * 2] + py * penta_normals[k * 2 + 1]
					if e > d:
						d = e
				d -= penta_apothem
			elif cell < _PANEL_COUNT:
				d = -1.0e20
				for k in 6:
					var e := px * hexa_normals[k * 2] + py * hexa_normals[k * 2 + 1]
					if e > d:
						d = e
				d -= hexa_apothem

			# The panel bulges: full height in the middle, falling into the
			# stitched gutter over roughly nine texels.
			var bulge := clampf(-d / 0.09, 0.0, 1.0)
			bulge = bulge * bulge * (3.0 - 2.0 * bulge)
			var micro: int = i * 374761393 + grain_base + j * 668265263
			micro = (micro ^ (micro >> 13)) * 1274126177
			micro = micro ^ (micro >> 16)
			var grain := mottle[row + i] * 0.7 + (float(micro & 0x3fffffff) / 1073741824.0) * 0.3
			height[q] = bulge * 0.86 + grain * 0.14
			q += 1

	# Clamped edges, not wrapped: cell 0 and cell 5 are unrelated panels, so
	# wrapping the difference across the atlas border would invent a fake ridge.
	var data := _normal_bytes(height, n, 3.4, false)
	var tex := _make_texture(n, n, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## Net cord grid with a cut out alpha. 256x256, tiles.
## The alpha channel is 0 in the holes and 1 on the cord.
##
## The cords run at 45 degrees, on the two diagonals, because that is how a goal
## net is actually knotted: a square grid aligned with the UV would read as a
## fence. Both diagonal periods divide the texture size, so the pattern tiles.
##
## Note for whoever wires the material: this is a CUT OUT, so it wants
## TRANSPARENCY_ALPHA_SCISSOR at 0.5 and CULL_DISABLED, never plain alpha
## blending, which sorts against itself and flickers.
static func net() -> ImageTexture:
	var key := "net"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _NET_SIZE
	var lut := _srgb_table()
	var cr := Palette.NET_CORD.r
	var cg := Palette.NET_CORD.g
	var cb := Palette.NET_CORD.b
	var diag := sqrt(0.5)

	var data := PackedByteArray()
	data.resize(n * n * 4)
	var p := 0
	for j in n:
		for i in n:
			var a := posmod(i + j, _NET_PERIOD)
			var b := posmod(i - j, _NET_PERIOD)
			# Perpendicular distance to the nearest cord of each family.
			var ra := float(mini(a, _NET_PERIOD - a)) * diag
			var rb := float(mini(b, _NET_PERIOD - b)) * diag
			# A knot is where the two families cross: the cord swells there.
			var knot := clampf(1.0 - maxf(ra, rb) / (_NET_HALF_CORD * 2.4), 0.0, 1.0)
			var half := _NET_HALF_CORD + knot * 0.9
			var d := minf(ra, rb)
			var cover := clampf(half + 0.5 - d, 0.0, 1.0)
			# Cylindrical shading across the cord, so it reads as twine and not
			# as a painted line.
			var round_off := clampf(d / maxf(half, 0.001), 0.0, 1.0)
			var lum := 0.55 + 0.45 * cos(round_off * PI * 0.5) + knot * 0.12
			data[p] = lut[int(clampf(cr * lum, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(cg * lum, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(cb * lum, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 3] = int(cover * 255.0)
			p += 4

	var tex := _make_texture(n, n, Image.FORMAT_RGBA8, data, true)
	_cache[key] = tex
	return tex


## A block of spectators seen from the pitch: coloured specks on dark seating,
## CUT OUT against a transparent background. 512x512, tiles horizontally.
##
## 32 seats across by 22 rows is 704 individual people, each with their own torso
## colour, head colour, presence and lateral offset, all drawn from the hash so
## the stand is identical on every boot. The per person data is computed once into
## a flat float array and then only indexed per pixel: hashing inside the pixel
## loop would cost four times as much for the same picture.
##
## THE ALPHA CHANNEL IS THE POINT OF THIS TEXTURE, and it is what stopped the
## stands reading as a quilt of postcards. `Stadium` crops ONE cell of this image
## per spectator sprite, so whatever a cell contains is what an entire spectator
## quad shows. While the cell was opaque, every spectator was drawn as a solid
## rectangle of painted seating with a small person in the middle of it: those
## rectangles tiled over the whole stand, each one outlined against its neighbour
## because each cell carries a slightly different seat tone, and the real
## architecture behind them (the treads, the seat blocks, the gangway, the roof)
## was covered up completely. Alpha 1 on the person and 0 on the seating fixes
## both at once: the sprite is now the person and nothing else, and the stand is
## seen BETWEEN the spectators instead of behind them.
##
## The coverage is a soft edge about one texel wide rather than a hard test. The
## crowd is minified hard (the far stand is seventy metres away), so a binary
## cut-out would either crawl with aliasing or, through the mip chain, thin out to
## nothing. A soft edge blends down into a dark, busy wash instead, which is
## exactly what a distant crowd looks like.
##
## VALUE RANGE, and why it is so low. This image is the background of every frame
## of the game, behind the goal, so the eye must land on the goal, the keeper and
## the ball long before it lands here. A spectator is scaled by _CROWD_BODY_GAIN
## down to roughly 0.10 linear, against a lit pitch near 0.35, and only the rare
## _CROWD_GLINT_GAIN spectator catches the stand lighting. The seating RGB is kept
## painted, dark, under the transparent part: bilinear filtering and the mip chain
## both bleed it into the silhouette edge, so it has to be the colour of a shadow
## rather than a leftover.
static func crowd(atlas_index: int = 0) -> Texture2D:
	var selected := posmod(atlas_index, _CROWD_ATLASES.size())
	var key := "crowd:%d" % selected
	if _cache.has(key):
		return _cache[key] as Texture2D

	# The generated atlas is an optional visual enhancement. The procedural
	# silhouettes below remain the asset-free fallback.
	var atlas := _asset_texture(_CROWD_ATLASES[selected]) if crowd_uses_asset() else null
	if atlas != null:
		_cache[key] = atlas
		return atlas

	var n := _CROWD_SIZE
	var lut := _srgb_table()
	var people := _crowd_people()

	var seat_a := Palette.SEAT_A
	var seat_b := Palette.SEAT_B

	var data := PackedByteArray()
	data.resize(n * n * 4)
	var p := 0
	for j in n:
		var fv := (float(j) + 0.5) / float(n) * float(_CROWD_ROWS)
		var row := mini(int(fv), _CROWD_ROWS - 1)
		var ly := fv - float(row)
		# Higher rows are further away: they lose contrast to the night haze.
		var depth := 0.72 + 0.28 * (float(j) / float(n))
		# Odd rows are offset by half a seat. Real seating is staggered, and
		# without this the stand comes out as a perfect lattice of dots that the
		# eye reads instantly as a pattern rather than as people. Offsetting by
		# exactly half a cell keeps the horizontal tiling intact.
		var shift := 0.5 if (row & 1) == 1 else 0.0
		for i in n:
			var fu := (float(i) + 0.5) / float(n) * float(_CROWD_SEATS) + shift
			var seat := floori(fu)
			var col := posmod(seat, _CROWD_SEATS)
			var lx := fu - float(seat)
			var base := (row * _CROWD_SEATS + col) * _CROWD_STRIDE

			# Painted seating, only ever seen through the filtering. Kept as the
			# shadow the spectator sits in rather than as a surface of its own.
			var tone := people[base + 8]
			var back := seat_a.lerp(seat_b, tone)
			var shade := _CROWD_SEAT_GAIN * (0.42 + 0.58 * ly * ly)
			var cr := back.r * shade
			var cg := back.g * shade
			var cb := back.b * shade
			var alpha := 0.0

			if people[base] > 0.5:
				var dx := people[base + 7]
				var ox := lx - 0.5 - dx
				# Torso: a squat ellipse a little over half the cell wide, so two
				# neighbours never merge into a continuous band of shoulders.
				var ty := ly - 0.70
				var body := (ox * ox) / 0.075 + (ty * ty) / 0.055
				# Head: a small disc above it, just touching the shoulders.
				var hy := ly - 0.33
				var skull := (ox * ox + hy * hy) / 0.017
				# One texel of softness on each silhouette, in the units of its
				# own quadratic. See the class comment for why it is not a test.
				var cover_body := clampf((1.0 - body) * 2.2, 0.0, 1.0)
				var cover_head := clampf((1.0 - skull) * 1.4, 0.0, 1.0)
				alpha = maxf(cover_body, cover_head)
				if cover_body > 0.0:
					# Shoulders roll away from the centre line: a flat fill turns
					# a torso into a rectangle as soon as it is minified.
					var round_off := 0.72 + 0.28 * clampf(1.0 - body, 0.0, 1.0)
					cr = people[base + 1] * round_off
					cg = people[base + 2] * round_off
					cb = people[base + 3] * round_off
				if cover_head > 0.0:
					cr = people[base + 4]
					cg = people[base + 5]
					cb = people[base + 6]

			cr = cr * depth
			cg = cg * depth
			cb = cb * depth
			data[p] = lut[int(clampf(cr, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(cg, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(cb, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 3] = int(clampf(alpha, 0.0, 1.0) * 255.0)
			p += 4

	var tex := _make_texture(n, n, Image.FORMAT_RGBA8, data, true)
	_cache[key] = tex
	return tex


static func crowd_uses_asset() -> bool:
	for file_name in _CROWD_ATLASES:
		if not ResourceLoader.exists(_ASSET_DIR + file_name):
			return false
	return true


## Photographic cutout used by every instanced stadium seat, or null for the
## original flat quad fallback when assets/ is absent.
static func stadium_seat() -> Texture2D:
	return _asset_texture(_STADIUM_SEAT)


## Perimeter advertising board, abstract blocks of colour, no readable text.
## 512x128. Six designs, cycled with the index, so a run of boards around the
## pitch never repeats twice in a row.
static func advert(index: int) -> ImageTexture:
	var design := posmod(index, _ADVERT_DESIGNS)
	var key := "advert:%d" % design
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var w := _ADVERT_W
	var h := _ADVERT_H
	var buf := PackedFloat32Array()
	buf.resize(w * h * 3)

	var warm := design % 2 == 0
	var base_hue: Color = Palette.ADVERT_A if warm else Palette.ADVERT_B
	var ink_hue: Color = Palette.ADVERT_B if warm else Palette.ADVERT_A
	var base := Palette.shade(Palette.vary(base_hue, float(design) * 3.7, 0.30), _ADVERT_GAIN)
	var ink := Palette.shade(Palette.vary(ink_hue, float(design) * 9.1, 0.30), _ADVERT_GAIN)
	# The "lit" element of the artwork. It used to be desaturated to near grey and
	# lightened to 0.65, which is paper white once the board also emits: a LED
	# board that goes white stops reading as a colour and starts competing with
	# the goal posts. It keeps most of its hue and stays under a third of the way
	# up the albedo band instead, while still being clearly the brightest thing ON
	# the board.
	# `base` already carries _ADVERT_GAIN, so it is not applied a second time here.
	var pale := Palette.clamp_albedo(Palette.desaturate(base, 0.40).lightened(0.16))

	_fill(buf, w, h, 0, 0, w, h, base)

	# A diagonal sweep across the whole board.
	var slope := 0.55 + 0.25 * float(design % 3)
	for j in h:
		var x0 := int(float(w) * 0.30 + float(j) * slope * 2.0)
		_fill(buf, w, h, x0, j, x0 + int(float(w) * 0.16), j + 1, ink)

	# A stack of bars on the left: the abstract "mark".
	var bars := 3 + design % 3
	for k in bars:
		var y0 := 14 + k * 22
		var bw := 34 + k * 26
		_fill(buf, w, h, 26, y0, 26 + bw, y0 + 14, pale)

	# A ring, off centre.
	_disc(buf, w, h, float(w) * 0.52, float(h) * 0.48, float(h) * 0.31, pale)
	_disc(buf, w, h, float(w) * 0.52, float(h) * 0.48, float(h) * 0.19, base)

	# A row of blocks of uneven width, which reads as a wordmark from thirty
	# metres away without ever forming a letter.
	var x := int(float(w) * 0.66)
	var block := 0
	while x < w - 24 and block < 9:
		var bw2 := 10 + int(_hash2(design, block, 3301) * 22.0)
		var by := 44 + int(_hash2(design, block, 7717) * 10.0)
		_fill(buf, w, h, x, by, x + bw2, by + 38, pale)
		x += bw2 + 8
		block += 1

	var tex := _make_texture(w, h, Image.FORMAT_RGB8, _encode_rgb(buf), true)
	_cache[key] = tex
	return tex


## Woven fabric for the jerseys, subtle. 256x256, tiles.
##
## A plain weave: warp and weft alternate over and under in blocks of one thread,
## and whichever is on top gets the cylindrical highlight. Centred near 0.93 so a
## material can multiply it straight onto a palette albedo without darkening the
## kit by a third - the value is applied ONCE, here, and never again downstream.
static func fabric() -> ImageTexture:
	var key := "fabric"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := _FABRIC_SIZE
	var period := 8
	var lut := _srgb_table()
	var data := PackedByteArray()
	data.resize(n * n * 3)
	var p := 0
	for j in n:
		var jy := j % period
		var jb := j / period
		for i in n:
			var ix := i % period
			var ib := i / period
			var s := 0.0
			if (ib + jb) % 2 == 0:
				s = sin(PI * (float(ix) + 0.5) / float(period))
			else:
				s = sin(PI * (float(jy) + 0.5) / float(period))
			var lum := 0.80 + 0.16 * s
			lum = lum * (0.97 + _hash2(i, j, 2237) * 0.06)
			var b := lut[int(clampf(lum, 0.0, 1.0) * _LUT_SCALE)]
			data[p] = b
			data[p + 1] = b
			data[p + 2] = b
			p += 3

	var tex := _make_texture(n, n, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## Broken afternoon cumulus, as an equirectangular panorama for the sky cover.
## 1024x512, black where the sky must stay bare.
##
## It is ADDITIVE, and everything about the image follows from that. Godot's
## ProceduralSkyMaterial adds `sky_cover` to the gradient it already computed
## rather than compositing it, so there is no alpha to author and no cut out: a
## texel of 0 is clear sky, and a texel of 0.55 is a cloud top. That also means the
## clouds cannot hide the blue behind them, which is why they are kept well under
## 1.0 and why the darker parts of a cloud are drawn as LESS ADDED LIGHT rather
## than as grey paint.
##
## Two fields, mixed three to one: a coarse one for the shape of each cloud and a
## finer one for the ragged edges. Both come out of `_fbm_field`, which wraps, so
## the panorama joins itself cleanly at the seam behind the far stand. The
## coverage is then thresholded with a wide soft edge: a low threshold gives
## overcast, this one leaves most of the dome blue and puts real gaps between the
## clouds, which is what an afternoon looks like.
##
## The elevation mask does the rest. Clouds fade in below the zenith (a hole
## straight overhead reads as a mistake), thicken through the middle of the dome
## where perspective foreshortens them, and are cut off just above the horizon so
## the band the stadium roofs are silhouetted against stays clean. Nothing at all
## is drawn below the horizon: the lower hemisphere feeds the sky ambient, and a
## cloud down there would be light arriving from underneath the pitch.
static func clouds() -> ImageTexture:
	var key := "clouds"
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var shape := _fbm_field(8, 512, 6, 0.56, 6421)
	_normalise(shape)
	var wisp := _fbm_field(16, 512, 5, 0.50, 9137)
	_normalise(wisp)

	var lut := _srgb_table()
	var data := PackedByteArray()
	data.resize(_CLOUD_W * _CLOUD_H * 4)
	var p := 0
	for j in _CLOUD_H:
		# 0 at the zenith, 1 at the horizon, 2 at the nadir.
		var elevation := float(j) * 2.0 / float(_CLOUD_H)
		var band := 0.0
		if elevation < 1.0:
			band = smoothstep(0.02, 0.34, elevation) * (1.0 - smoothstep(0.90, 0.99, elevation))
		var row := (j * 512) / _CLOUD_H
		if band <= 0.0:
			# Whole row is bare sky. Writing it straight is worth a branch: half the
			# panorama is below the horizon and never has anything on it.
			for i in _CLOUD_W:
				data[p] = 0
				data[p + 1] = 0
				data[p + 2] = 0
				data[p + 3] = 255
				p += 4
			continue
		var base := row * 512
		for i in _CLOUD_W:
			var idx := base + (i * 512) / _CLOUD_W
			var density := shape[idx] * 0.75 + wisp[idx] * 0.25
			var cover := clampf((density - _CLOUD_COVER) / _CLOUD_SOFT, 0.0, 1.0)
			# Smoothstep on the coverage, so a cloud has a soft shoulder instead of
			# a linear ramp that shows its own gradient as a hard rim.
			cover = cover * cover * (3.0 - 2.0 * cover)
			var value := cover * band * _CLOUD_GAIN
			# The thin edge of a cloud is lit through and reads slightly cooler than
			# its sunlit crown, which is what stops the mass looking like felt.
			var warmth := 0.80 + 0.20 * cover
			data[p] = lut[int(clampf(value * warmth, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 1] = lut[int(clampf(value * (0.88 + 0.12 * cover), 0.0, 1.0) * _LUT_SCALE)]
			data[p + 2] = lut[int(clampf(value, 0.0, 1.0) * _LUT_SCALE)]
			data[p + 3] = 255
			p += 4

	var tex := _make_texture(_CLOUD_W, _CLOUD_H, Image.FORMAT_RGBA8, data, true)
	_cache[key] = tex
	return tex


## Soft radial falloff, white centre to transparent edge. For sprites and glow.
##
## The falloff is squared rather than linear: a linear cone has a visible hard
## rim where its derivative jumps, which shows up as a ring around every halo.
##
## The RGB is a flat 1.0, deliberately above the albedo band. This texture never
## feeds a lit surface: it modulates an unshaded additive material, where the
## colour is ADDED to the frame rather than reflected, so the band does not apply
## any more than it applies to `Palette.FLOODLIGHT`.
static func radial(size: int = 128) -> ImageTexture:
	var n := clampi(size, 8, 512)
	var key := "radial:%d" % n
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var half := float(n) * 0.5
	var data := PackedByteArray()
	data.resize(n * n * 4)
	var p := 0
	for j in n:
		var dy := (float(j) + 0.5) - half
		for i in n:
			var dx := (float(i) + 0.5) - half
			var r := sqrt(dx * dx + dy * dy) / half
			var a := clampf(1.0 - r, 0.0, 1.0)
			a = a * a * (1.4 - 0.4 * a)
			data[p] = 255
			data[p + 1] = 255
			data[p + 2] = 255
			data[p + 3] = int(clampf(a, 0.0, 1.0) * 255.0)
			p += 4

	var tex := _make_texture(n, n, Image.FORMAT_RGBA8, data, true)
	_cache[key] = tex
	return tex


## A 1x256 vertical ramp between two colours, for gradient driven shaders.
## Row 0 is `top`. Stored sRGB encoded like every other colour texture here, so
## sample it through a `source_color` uniform.
static func ramp(top: Color, bottom: Color) -> ImageTexture:
	var key := "ramp:%.4f,%.4f,%.4f,%.4f|%.4f,%.4f,%.4f,%.4f" % [
		top.r, top.g, top.b, top.a, bottom.r, bottom.g, bottom.b, bottom.a]
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var n := 256
	var lut := _srgb_table()
	var data := PackedByteArray()
	data.resize(n * 4)
	var p := 0
	for j in n:
		var t := float(j) / float(n - 1)
		var c := Palette.mix(top, bottom, t)
		data[p] = lut[int(clampf(c.r, 0.0, 1.0) * _LUT_SCALE)]
		data[p + 1] = lut[int(clampf(c.g, 0.0, 1.0) * _LUT_SCALE)]
		data[p + 2] = lut[int(clampf(c.b, 0.0, 1.0) * _LUT_SCALE)]
		data[p + 3] = int(clampf(c.a, 0.0, 1.0) * 255.0)
		p += 4

	# No mipmaps: a one pixel wide gradient is never minified, and mipping it
	# would only smear the two ends together.
	var tex := _make_texture(1, n, Image.FORMAT_RGBA8, data, false)
	_cache[key] = tex
	return tex


## Neutral photographic surface detail for `name`, or NULL when the optional
## asset is not in the project.
##
## `name` is a material set prefix under `res://assets/textures/`, so "concrete"
## reads `concrete_albedo.jpg`. What comes back is the photograph reduced to its
## RATIO to its own mean and re-centred on `DETAIL_MEAN`: a tileable multiplier
## that a material lays straight over a `Palette` albedo the way `fabric()` is
## laid over a jersey. It carries the grain, the staining and the relative hue
## drift of the real surface and none of its absolute brightness, which is what
## keeps a photograph from lifting a stand out of the albedo band.
##
## THE CALLER OWES IT A DIVISION. The map averages `DETAIL_MEAN`, not one, so a
## material that binds it must scale its albedo by `1.0 / Tex.DETAIL_MEAN` or the
## surface comes out half as bright as the palette says. See `DETAIL_MEAN` for why
## it cannot simply average one.
##
## NULL IS THE NORMAL ANSWER on a checkout with no assets folder, and it is not an
## error. The caller must simply keep its flat colour: the game is then coarser
## and completely playable.
static func surface_detail(name: String) -> ImageTexture:
	var key := "detail:" + name
	if _cache.has(key):
		return _cache[key] as ImageTexture

	var photo := _photo(name + _ASSET_ALBEDO, _DETAIL_SIZE)
	if photo.is_empty():
		_cache[key] = null
		return null

	var n := _DETAIL_SIZE
	var src: PackedByteArray = photo["data"]
	var gain: PackedFloat32Array = photo["gain"]
	var inv := _linear_table()
	var lut := _srgb_table()

	var total := n * n * 3
	var data := PackedByteArray()
	data.resize(total)
	# A `while` and not `for p in range(...)`: the three argument `range` builds a
	# real Array first, which for a 512 image is a quarter of a million integers
	# allocated to be thrown away one at a time.
	var p := 0
	while p < total:
		for c in 3:
			var ratio := clampf(
				1.0 + (inv[src[p + c]] * gain[c] - 1.0) * _DETAIL_STRENGTH,
				_RATIO_MIN, _RATIO_MAX)
			data[p + c] = lut[int(clampf(ratio * DETAIL_MEAN, 0.0, 1.0) * _LUT_SCALE)]
		p += 3

	var tex := _make_texture(n, n, Image.FORMAT_RGB8, data, true)
	_cache[key] = tex
	return tex


## The imported normal map of a photographic material set, or NULL when absent.
##
## Handed over exactly as the importer produced it: mipmapped, GPU compressed, and
## in the OpenGL +Y up convention Godot expects. It is non colour data, so it is
## never pulled through an `Image` here.
static func surface_normal(name: String) -> Texture2D:
	return _asset_texture(name + _ASSET_NORMAL)


## The imported ARM map of a photographic material set, or NULL when absent.
##
## ONE image, THREE inputs, wired PER CHANNEL by whoever uses it:
##   R = ambient occlusion, G = roughness, B = metallic.
## Assigning it whole to any single one of `ao_texture`, `roughness_texture` or
## `metallic_texture` without also setting the matching `*_texture_channel` reads
## the red channel for all three, which puts a roughness of "the AO map" on the
## surface. See `Mats._wire_arm`, which is the only place this is done.
static func surface_arm(name: String) -> Texture2D:
	return _asset_texture(name + _ASSET_ARM)


## Frees every cached texture. Only the tests call this.
static func clear_cache() -> void:
	_cache.clear()


# ---------------------------------------------------------------------------
# Optional photographic assets
# ---------------------------------------------------------------------------

## The imported texture at `res://assets/textures/<file_name>`, or null.
##
## `ResourceLoader.exists` FIRST, always: `load()` on a missing path pushes an
## engine error, and a missing asset here is a legal state, not a fault.
static func _asset_texture(file_name: String) -> Texture2D:
	var key := "asset:" + file_name
	if _cache.has(key):
		return _cache[key] as Texture2D
	var out: Texture2D = null
	var path := _ASSET_DIR + file_name
	if ResourceLoader.exists(path):
		out = ResourceLoader.load(path) as Texture2D
	_cache[key] = out
	return out


## Raw sRGB bytes of an optional photograph, square, at `size`, plus the per
## channel gain that takes its LINEAR mean to 1.0.
##
## Returns `{"data": PackedByteArray, "gain": PackedFloat32Array}` or an EMPTY
## dictionary when there is no such asset, which every caller treats as "use the
## procedural path".
##
## The image comes back from the importer GPU compressed and mipmapped, so it is
## copied (never mutate a cached resource), decompressed, stripped of its mips and
## converted to RGB8 before a single byte is read. Skipping the copy corrupts the
## texture the renderer is already drawing with; skipping the decompress reads
## block data as if it were pixels.
static func _photo(file_name: String, size: int) -> Dictionary:
	var key := "photo:%s:%d" % [file_name, size]
	if _cache.has(key):
		return _cache[key] as Dictionary

	var out := {}
	var tex := _asset_texture(file_name)
	if tex != null:
		var source := tex.get_image()
		if source == null:
			push_warning("Tex: %s a ete importee sans image lisible." % file_name)
		else:
			var image := Image.new()
			image.copy_from(source)
			var ok := true
			if image.is_compressed():
				ok = image.decompress() == OK
			if not ok:
				push_warning("Tex: decompression impossible de %s." % file_name)
			else:
				if image.has_mipmaps():
					image.clear_mipmaps()
				image.convert(Image.FORMAT_RGB8)
				if image.get_width() != size or image.get_height() != size:
					image.resize(size, size, Image.INTERPOLATE_LANCZOS)
				var bytes := image.get_data()
				out = {"data": bytes, "gain": _photo_gain(bytes)}

	_cache[key] = out
	return out


## Per channel 1 / linear mean of a raw RGB8 buffer.
##
## Subsampled, because the answer is an average: every sixteenth texel is a
## sixteenth of the work and lands within a thousandth of the full sum. The gain
## is clamped so a nearly black source (a burnt out normal map handed in by
## mistake) cannot turn into a multiplier of a thousand.
static func _photo_gain(bytes: PackedByteArray) -> PackedFloat32Array:
	var inv := _linear_table()
	var sums := PackedFloat32Array([0.0, 0.0, 0.0])
	var count := 0
	var limit := bytes.size() - 2
	var p := 0
	while p < limit:
		sums[0] += inv[bytes[p]]
		sums[1] += inv[bytes[p + 1]]
		sums[2] += inv[bytes[p + 2]]
		count += 1
		p += 3 * 16
	var out := PackedFloat32Array([1.0, 1.0, 1.0])
	if count == 0:
		return out
	for c in 3:
		out[c] = clampf(float(count) / maxf(sums[c], 0.0001), 0.05, 20.0)
	return out


# ---------------------------------------------------------------------------
# Turf fields
# ---------------------------------------------------------------------------

## The shared turf height field, 0..1, 1024x1024, tiling.
##
## The GAIN IS ABOVE ONE on purpose, and it is the difference between grass and
## camouflage. A textbook fbm halves its amplitude at every octave, so the
## coarsest lattice dominates and the result is a field of big soft blobs. Turf
## is the opposite: it is almost all high frequency, with only a whisper of
## large scale variation. Feeding the octaves a gain of 1.08 puts the energy
## where the blades are.
##
## Then the blade clumps go on top: one texel wide, six tall, hashed per column
## and held over those six rows, which is why they read as upright grass rather
## than as salt and pepper. At a tile of a few metres that is a clump about eight
## millimetres wide and five centimetres long, which is a real blade of grass.
static func _turf_height_field() -> PackedFloat32Array:
	if _cache.has(_KEY_TURF_HEIGHT):
		var hit: PackedFloat32Array = _cache[_KEY_TURF_HEIGHT]
		return hit

	var n := _TURF_SIZE
	var field := _fbm_field(16, n, 6, 1.08, 1013)
	# Hash inlined: a million call frames is most of a second on its own.
	var salt_base: int = 7717 * 1274126177
	for j in n:
		var band: int = j / _BLADE_LENGTH
		var yb: int = salt_base + band * 668265263
		var row := j * n
		for i in n:
			var h: int = i * 374761393 + yb
			h = (h ^ (h >> 13)) * 1274126177
			h = h ^ (h >> 16)
			var r := float(h & 0x3fffffff) / 1073741824.0 - 0.5
			field[row + i] = field[row + i] + r * _BLADE_AMPLITUDE
	_normalise(field)
	_cache[_KEY_TURF_HEIGHT] = field
	return field


## Coherent leather mottle for the ball, 0..1, 512x512. Shared and cached
## because `ball_panels()` and `ball_normal()` both want it, and building it
## twice is a third of a second of noise for an identical result.
static func _ball_grain_field() -> PackedFloat32Array:
	var key := "field:ball_grain"
	if _cache.has(key):
		var hit: PackedFloat32Array = _cache[key]
		return hit

	var field := _fbm_field(8, _BALL_SIZE, 5, 0.60, 8191)
	_normalise(field)
	_cache[key] = field
	return field


## Low frequency wear field, 0..1, 1024x1024, tiling. Three octaves only: wear
## comes in broad patches, and any detail in it would fight the blade noise.
static func _turf_wear_field() -> PackedFloat32Array:
	if _cache.has(_KEY_TURF_WEAR):
		var hit: PackedFloat32Array = _cache[_KEY_TURF_WEAR]
		return hit

	var field := _fbm_field(8, _TURF_SIZE, 3, 0.55, 4441)
	_normalise(field)
	_cache[_KEY_TURF_WEAR] = field
	return field


# ---------------------------------------------------------------------------
# Crowd data
# ---------------------------------------------------------------------------

## Flat per spectator table, `_CROWD_STRIDE` floats each:
##   0        present (0 or 1)
##   1, 2, 3  torso colour
##   4, 5, 6  head colour
##   7        lateral offset in cell widths
##   8        seat tone under this person
## Laid out flat rather than as an array of dictionaries so the pixel loop only
## ever pays an integer index.
static func _crowd_people() -> PackedFloat32Array:
	var key := "field:crowd_people"
	if _cache.has(key):
		var hit: PackedFloat32Array = _cache[key]
		return hit

	var count := _CROWD_SEATS * _CROWD_ROWS
	var out := PackedFloat32Array()
	out.resize(count * _CROWD_STRIDE)
	var tones: Array[Color] = [Palette.CROWD_A, Palette.CROWD_B, Palette.CROWD_C]

	for row in _CROWD_ROWS:
		for col in _CROWD_SEATS:
			var base := (row * _CROWD_SEATS + col) * _CROWD_STRIDE
			var h0 := _hash2(col, row, 61)
			var h1 := _hash2(col, row, 227)
			var h2 := _hash2(col, row, 809)
			var h3 := _hash2(col, row, 1381)
			# One seat in eight is empty: a full stand looks like wallpaper.
			out[base] = 1.0 if h0 < 0.87 else 0.0
			# The brightness gain is applied HERE, once, on the way into the
			# table. It is what keeps the crowd below the pitch on the contrast
			# ladder, and doing it here instead of per pixel leaves the pixel
			# loop as a plain array read.
			var glint := _hash2(col, row, 2749) < _CROWD_GLINT_ODDS
			var gain := _CROWD_BODY_GAIN * (_CROWD_GLINT_GAIN if glint else 1.0)
			var torso: Color = Palette.vary(tones[int(h1 * 3.0) % 3], h1 * 137.0 + float(row), 0.34)
			if glint:
				# A pale shirt catching the stand lighting, not a brighter
				# version of the same shirt.
				torso = Palette.desaturate(torso, 0.7)
			out[base + 1] = torso.r * gain
			out[base + 2] = torso.g * gain
			out[base + 3] = torso.b * gain
			var head := Palette.vary(Palette.SKIN, h2 * 91.0 + float(col), 0.26)
			if h3 < 0.34:
				head = Palette.mix(head, Palette.HAIR, 0.65)
			# A head is never a glint. A stand full of bright faces reads as a
			# grid of lamps, which is the exact failure this scaling avoids.
			out[base + 4] = head.r * _CROWD_BODY_GAIN
			out[base + 5] = head.g * _CROWD_BODY_GAIN
			out[base + 6] = head.b * _CROWD_BODY_GAIN
			out[base + 7] = (h2 - 0.5) * 0.16
			out[base + 8] = h3
	_cache[key] = out
	return out


# ---------------------------------------------------------------------------
# Noise plumbing
# ---------------------------------------------------------------------------

## Deterministic integer hash of a lattice coordinate into 0..1.
## Three odd multipliers, two xor-shift rounds: enough avalanche that adjacent
## coordinates are uncorrelated, and cheap enough to call a million times.
static func _hash2(x: int, y: int, salt: int) -> float:
	var h: int = x * 374761393 + y * 668265263 + salt * 1274126177
	h = (h ^ (h >> 13)) * 1274126177
	h = h ^ (h >> 16)
	return float(h & 0x3fffffff) / 1073741824.0


## A square lattice of hashed values in -0.5 .. 0.5.
##
## `_hash2` is inlined here rather than called. At the top octave this loop runs
## a quarter of a million times, and in the GDScript VM the call frame costs more
## than the arithmetic inside it.
static func _lattice(w: int, salt: int) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(w * w)
	var base: int = salt * 1274126177
	var p := 0
	for y in w:
		var yb: int = base + y * 668265263
		for x in w:
			var h: int = x * 374761393 + yb
			h = (h ^ (h >> 13)) * 1274126177
			h = h ^ (h >> 16)
			out[p] = float(h & 0x3fffffff) / 1073741824.0 - 0.5
			p += 1
	return out


## Bilinear doubling of a square field, WRAPPING at the edges. Wrapping is what
## makes every field built on top of this tile seamlessly.
##
## Written as two separable passes because the weights of an exact 2x bilinear
## upsample are only ever 0.25 and 0.75: the general form would cost four reads
## and three lerps per output texel, this costs two reads and two multiplies.
## Over a field that ends at a million texels that is the difference between a
## boot you notice and one you do not.
static func _upsample2x(src: PackedFloat32Array, w: int) -> PackedFloat32Array:
	var w2 := w * 2

	var tmp := PackedFloat32Array()
	tmp.resize(w2 * w)
	for y in w:
		var sbase := y * w
		var dbase := y * w2
		for k in w:
			var a := src[sbase + (k - 1 if k > 0 else w - 1)]
			var b := src[sbase + k]
			var c := src[sbase + (k + 1 if k < w - 1 else 0)]
			tmp[dbase + k * 2] = 0.25 * a + 0.75 * b
			tmp[dbase + k * 2 + 1] = 0.75 * b + 0.25 * c

	var dst := PackedFloat32Array()
	dst.resize(w2 * w2)
	for y in w:
		var rm := (y - 1 if y > 0 else w - 1) * w2
		var rc := y * w2
		var rp := (y + 1 if y < w - 1 else 0) * w2
		var d0 := (y * 2) * w2
		var d1 := d0 + w2
		for x in w2:
			var a := tmp[rm + x]
			var b := tmp[rc + x]
			var c := tmp[rp + x]
			dst[d0 + x] = 0.25 * a + 0.75 * b
			dst[d1 + x] = 0.75 * b + 0.25 * c
	return dst


## Fractal value noise from `start_size` up to `target_size`, both powers of two.
##
## The last doubling adds no lattice on purpose: a fresh hash per texel at the
## final resolution is uncorrelated noise, which is exactly the television static
## this module exists to avoid. Fine detail is added afterwards, in a structured
## form, by whoever asked for the field.
static func _fbm_field(start_size: int, target_size: int, octaves: int, gain: float, salt: int) -> PackedFloat32Array:
	var size := start_size
	var field := _lattice(size, salt)
	var amp := 1.0
	var added := 1
	while size < target_size:
		field = _upsample2x(field, size)
		size *= 2
		if added < octaves:
			amp = amp * gain
			var octave := _lattice(size, salt + size * 31)
			for i in field.size():
				field[i] = field[i] + octave[i] * amp
			added += 1
	return field


## Rescales a field in place so its extremes land exactly on 0 and 1.
static func _normalise(field: PackedFloat32Array) -> void:
	var lo := 1.0e20
	var hi := -1.0e20
	for i in field.size():
		var v := field[i]
		if v < lo:
			lo = v
		if v > hi:
			hi = v
	var scale := 1.0 / maxf(hi - lo, 0.000001)
	for i in field.size():
		field[i] = (field[i] - lo) * scale


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

## Outward unit normals of the edges of a regular n-gon whose vertex 0 sits
## straight above the centre, as flat (nx, ny) pairs.
##
## The two ball generators use these to get a signed distance from the panel, in
## the half plane form: `max over edges of dot(p, n) - apothem`, negative inside.
## That form is exact along an edge and slightly conservative near a corner,
## which for a seam three texels wide is invisible, and it costs one dot product
## per edge instead of a square root.
##
## Precomputed once per generator because calling `cos`/`sin` six times inside a
## quarter million pixel loop is a lot of trigonometry for a table of twelve
## numbers.
static func _edge_normals(sides: int) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(sides * 2)
	var step := TAU / float(sides)
	for k in sides:
		var a := -PI * 0.5 + PI / float(sides) + float(k) * step
		out[k * 2] = cos(a)
		out[k * 2 + 1] = sin(a)
	return out


## Central differences of a square height field into a tangent space normal map.
##
## Godot's convention is X+, Y-, Z+, and `j` here is the image row index, which
## grows downwards; that is why the green channel takes `+dH/dj` while red takes
## `-dH/di`. `wrap` is true for a tiling field and false for an atlas, where the
## opposite edge belongs to a different panel and differencing across it would
## invent a ridge that is not there.
static func _normal_bytes(height: PackedFloat32Array, n: int, strength: float, wrap: bool) -> PackedByteArray:
	var data := PackedByteArray()
	data.resize(n * n * 3)
	var p := 0
	for j in n:
		var jm := j - 1
		var jp := j + 1
		if jm < 0:
			jm = n - 1 if wrap else 0
		if jp >= n:
			jp = 0 if wrap else n - 1
		var rc := j * n
		var rm := jm * n
		var rp := jp * n
		for i in n:
			var im := i - 1
			var ip := i + 1
			if im < 0:
				im = n - 1 if wrap else 0
			if ip >= n:
				ip = 0 if wrap else n - 1
			var dx := (height[rc + ip] - height[rc + im]) * strength
			var dy := (height[rp + i] - height[rm + i]) * strength
			var inv := 1.0 / sqrt(dx * dx + dy * dy + 1.0)
			data[p] = clampi(int((-dx * inv) * 127.5 + 127.5), 0, 255)
			data[p + 1] = clampi(int((dy * inv) * 127.5 + 127.5), 0, 255)
			data[p + 2] = clampi(int(inv * 127.5 + 127.5), 0, 255)
			p += 3
	return data


# ---------------------------------------------------------------------------
# Raster helpers (adverts)
# ---------------------------------------------------------------------------

## Axis aligned rectangle into a linear float RGB buffer, clipped.
static func _fill(buf: PackedFloat32Array, w: int, h: int, x0: int, y0: int, x1: int, y1: int, c: Color) -> void:
	var ax := clampi(mini(x0, x1), 0, w)
	var bx := clampi(maxi(x0, x1), 0, w)
	var ay := clampi(mini(y0, y1), 0, h)
	var by := clampi(maxi(y0, y1), 0, h)
	for y in range(ay, by):
		var p := (y * w + ax) * 3
		for _x in range(ax, bx):
			buf[p] = c.r
			buf[p + 1] = c.g
			buf[p + 2] = c.b
			p += 3


## Filled disc into a linear float RGB buffer, clipped.
static func _disc(buf: PackedFloat32Array, w: int, h: int, cx: float, cy: float, radius: float, c: Color) -> void:
	var ax := clampi(int(cx - radius) - 1, 0, w)
	var bx := clampi(int(cx + radius) + 1, 0, w)
	var ay := clampi(int(cy - radius) - 1, 0, h)
	var by := clampi(int(cy + radius) + 1, 0, h)
	var r2 := radius * radius
	for y in range(ay, by):
		var dy := float(y) + 0.5 - cy
		for x in range(ax, bx):
			var dx := float(x) + 0.5 - cx
			if dx * dx + dy * dy <= r2:
				var p := (y * w + x) * 3
				buf[p] = c.r
				buf[p + 1] = c.g
				buf[p + 2] = c.b


## Linear float RGB buffer to sRGB encoded bytes.
static func _encode_rgb(buf: PackedFloat32Array) -> PackedByteArray:
	var lut := _srgb_table()
	var out := PackedByteArray()
	var count := buf.size()
	out.resize(count)
	for i in count:
		out[i] = lut[int(clampf(buf[i], 0.0, 1.0) * _LUT_SCALE)]
	return out


# ---------------------------------------------------------------------------
# Image plumbing
# ---------------------------------------------------------------------------

## Linear -> sRGB byte table. Built once, then it is a single array read per
## channel instead of a `pow()` per channel: on the turf alone that is three
## million calls to `pow` saved.
static func _srgb_table() -> PackedByteArray:
	if _srgb_lut.size() == _LUT_SIZE:
		return _srgb_lut
	_srgb_lut.resize(_LUT_SIZE)
	for i in _LUT_SIZE:
		var l := float(i) / _LUT_SCALE
		var s := (12.92 * l) if l <= 0.0031308 else (1.055 * pow(l, 1.0 / 2.4) - 0.055)
		_srgb_lut[i] = clampi(int(round(clampf(s, 0.0, 1.0) * 255.0)), 0, 255)
	return _srgb_lut


## sRGB byte -> linear float table, the exact inverse of `_srgb_table()`.
##
## Only 256 entries are possible, because a byte is what a photograph gives, so
## unlike the forward table there is nothing to trade off: it is exact.
static func _linear_table() -> PackedFloat32Array:
	if _linear_lut.size() == 256:
		return _linear_lut
	_linear_lut.resize(256)
	for i in 256:
		var s := float(i) / 255.0
		_linear_lut[i] = (s / 12.92) if s <= 0.04045 else pow((s + 0.055) / 1.055, 2.4)
	return _linear_lut


## Wraps a byte buffer into an ImageTexture, with mipmaps generated BEFORE the
## texture is created. Doing it afterwards is a silent no-op: the ImageTexture
## has already taken its copy of the image data.
static func _make_texture(w: int, h: int, format: Image.Format, data: PackedByteArray, mipmaps: bool) -> ImageTexture:
	var image := Image.create_from_data(w, h, false, format, data)
	if image == null:
		push_error("Tex: creation d'image impossible (%dx%d)" % [w, h])
		return ImageTexture.new()
	if mipmaps:
		image.generate_mipmaps()
	return ImageTexture.create_from_image(image)
