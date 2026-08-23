class_name Tex
extends RefCounted

## Texture library. Every surface pattern below is synthesised from a hand
## written fractal value noise, and each one is overridden at load time by the
## photographic CC0 set of the same name when `assets/textures` ships it (see
## `photo()`). The procedural side is therefore both the fallback and the source
## of everything that needs an alpha cut out, which the photo sets do not carry.
##
## Design notes worth keeping in mind before touching this file:
##
## 1. `noise2d()` is a PURE function of its arguments. It allocates nothing, it
##    keeps no state and it never touches `FastNoiseLite`, so terrain workers can
##    call it from any thread at any time.
## 2. The ground family ("grass", "dirt", "stone", "road", "sand", "noise") is
##    TILEABLE: the lattice of every octave wraps modulo its own period, so the
##    pattern loops seamlessly over the 256 px square.
## 3. Albedo textures are stored sRGB encoded. Godot binds an sRGB view for any
##    sampler hinted `source_color` (which is what StandardMaterial3D uses for
##    `albedo_texture`), so writing raw linear bytes there would darken every
##    surface by roughly a factor of three. `_enc()` does the encoding.
##    "water_normal" is the exception: a normal map is bound through a linear
##    view, so its bytes are written straight.
## 4. The palette colours are baked INTO the texture, and the materials that use
##    them keep `albedo_color` white. A modulation-only texture would have needed
##    values above 1.0, which an 8 bit format cannot store.

const SIZE := 256

## Number of floats in one cached noise field.
const _FIELD_LEN := SIZE * SIZE

## Every texture name the project may ask for.
const NAMES: PackedStringArray = [
	"grass", "dirt", "road", "stone", "wheat", "sand", "water_normal",
	"plaster", "wood", "roof_tile", "roof_slate", "concrete", "metal",
	"bark", "leaves", "noise", "cloud",
]

## Photographic CC0 texture sets shipped under assets/textures. When a set is
## present it overrides the procedural pattern of the same name, which stays in
## place as the fallback: delete the folder and the game still runs, it just
## looks synthetic again. See assets/textures/CREDITS.md for the sources.
##
## Each set carries three maps: `<name>_albedo.jpg`, `<name>_normal.jpg`
## (OpenGL convention) and `<name>_arm.jpg`, which packs ambient occlusion in
## red, roughness in green and metalness in blue.
const ASSET_DIR := "res://assets/textures"

const MAP_ALBEDO := "albedo"
const MAP_NORMAL := "normal"
const MAP_ARM := "arm"

static var _cache: Dictionary = {}
static var _fields: Dictionary = {}
static var _photo_cache: Dictionary = {}


## One map of a photographic set, or null when that set is not installed.
## Cached, including the misses, so a missing set costs one filesystem probe.
static func photo(texture_name: String, suffix: String) -> Texture2D:
	var key: String = "%s_%s" % [texture_name, suffix]
	if _photo_cache.has(key):
		return _photo_cache[key] as Texture2D
	var path: String = "%s/%s.jpg" % [ASSET_DIR, key]
	var found: Texture2D = null
	if ResourceLoader.exists(path):
		found = load(path) as Texture2D
	_photo_cache[key] = found
	return found


## True when a photographic albedo exists for this name.
static func has_photo(texture_name: String) -> bool:
	return photo(texture_name, MAP_ALBEDO) != null


## Horizontal slice of the blade atlas kept by `blade_texture()`, as fractions of
## its width. The source is a row of nine blades side by side; a blade quad
## samples the whole 0..1 UV range, so without a crop every single blade of grass
## in the world would display all nine at once, squashed. The window is a little
## wider than one blade so the crop never clips the tip.
const BLADE_CROP_LEFT := 0.285
const BLADE_CROP_RIGHT := 0.405

static var _blade_texture: Texture2D = null
static var _blade_tried := false


## One grass blade, cut out of the CC0 atlas and given a real alpha channel.
##
## The atlas ships colour and opacity as two separate images, and
## StandardMaterial3D has no opacity slot: alpha has to live in the albedo
## texture. So the two are merged here, once, then cropped to a single blade and
## mip mapped. Returns null when the atlas is not installed, in which case the
## caller falls back to the synthesised pattern.
static func blade_texture() -> Texture2D:
	if _blade_tried:
		return _blade_texture
	_blade_tried = true

	var color_source: Texture2D = _raw_asset("blade_color")
	var opacity_source: Texture2D = _raw_asset("blade_opacity")
	if color_source == null or opacity_source == null:
		return null

	var color_image: Image = color_source.get_image()
	var opacity_image: Image = opacity_source.get_image()
	if color_image == null or opacity_image == null:
		return null
	if color_image.is_compressed():
		color_image.decompress()
	if opacity_image.is_compressed():
		opacity_image.decompress()
	color_image.convert(Image.FORMAT_RGBA8)

	var full_width: int = color_image.get_width()
	var full_height: int = color_image.get_height()
	# The opacity map is authored at the same resolution, but resize defensively
	# rather than sampling out of bounds if that ever stops being true.
	if opacity_image.get_width() != full_width or opacity_image.get_height() != full_height:
		opacity_image.resize(full_width, full_height, Image.INTERPOLATE_BILINEAR)

	var left: int = clampi(int(BLADE_CROP_LEFT * float(full_width)), 0, full_width - 2)
	var right: int = clampi(int(BLADE_CROP_RIGHT * float(full_width)), left + 1, full_width)
	var crop_width: int = right - left

	var out := Image.create_empty(crop_width, full_height, true, Image.FORMAT_RGBA8)
	for y in full_height:
		for x in crop_width:
			var rgb: Color = color_image.get_pixel(left + x, y)
			# Opacity is a greyscale map: any channel carries the same value.
			rgb.a = opacity_image.get_pixel(left + x, y).r
			out.set_pixel(x, y, rgb)
	out.generate_mipmaps()

	_blade_texture = ImageTexture.create_from_image(out)
	return _blade_texture


## Loads one raw image asset by bare file name, trying png then jpg.
static func _raw_asset(file_name: String) -> Texture2D:
	for extension in ["png", "jpg"]:
		var path: String = "%s/%s.%s" % [ASSET_DIR, file_name, extension]
		if ResourceLoader.exists(path):
			return load(path) as Texture2D
	return null


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Cached. Known names: "grass", "dirt", "road", "stone", "wheat", "sand",
## "water_normal", "plaster", "wood", "roof_tile", "roof_slate", "concrete",
## "metal", "bark", "leaves", "noise", "cloud".
static func get_texture(texture_name: String) -> Texture2D:
	if _cache.has(texture_name):
		return _cache[texture_name] as Texture2D
	# A photographic set, when installed, wins over the synthesised pattern.
	var tex: Texture2D = photo(texture_name, MAP_ALBEDO)
	if tex == null:
		tex = _build(texture_name)
	if tex == null:
		push_warning("Tex: unknown texture name '%s', falling back to noise." % texture_name)
		tex = _build("noise")
		if tex == null:
			return null
	_cache[texture_name] = tex
	return tex


## Fractal value noise in [0,1]. Deterministic, no state.
## Not tileable: this is the world space flavour used by the terrain and the
## scatter, where wrapping would create a visible 256 m repetition.
static func noise2d(x: float, y: float, octaves: int = 4) -> float:
	var count: int = clampi(octaves, 1, 8)
	var total: float = 0.0
	var amplitude: float = 1.0
	var sum_amplitude: float = 0.0
	var fx: float = x
	var fy: float = y
	for i in count:
		total += _value_noise(fx, fy, i * 7919) * amplitude
		sum_amplitude += amplitude
		amplitude *= 0.5
		fx *= 2.0
		fy *= 2.0
	if sum_amplitude <= 0.0:
		return 0.0
	return clampf(total / sum_amplitude, 0.0, 1.0)


## Ridged variant of `noise2d`, handy for cliffs and erosion. Also pure.
static func ridge2d(x: float, y: float, octaves: int = 4) -> float:
	var count: int = clampi(octaves, 1, 8)
	var total: float = 0.0
	var amplitude: float = 1.0
	var sum_amplitude: float = 0.0
	var fx: float = x
	var fy: float = y
	for i in count:
		var v: float = 1.0 - absf(_value_noise(fx, fy, i * 6151) * 2.0 - 1.0)
		total += v * v * amplitude
		sum_amplitude += amplitude
		amplitude *= 0.5
		fx *= 2.0
		fy *= 2.0
	if sum_amplitude <= 0.0:
		return 0.0
	return clampf(total / sum_amplitude, 0.0, 1.0)


static func clear_cache() -> void:
	_cache.clear()
	_fields.clear()
	_photo_cache.clear()
	_blade_texture = null
	_blade_tried = false


# ---------------------------------------------------------------------------
# Hand written value noise
# ---------------------------------------------------------------------------

## Deterministic integer hash mapped to [0,1]. 32 bit arithmetic kept inside a
## positive range so the shifts behave the same on every platform.
static func _hash2(ix: int, iy: int, salt: int) -> float:
	var h: int = (ix * 374761393 + iy * 668265263 + salt * 2147483647) & 0x7FFFFFFF
	h = (h ^ (h >> 13)) * 1274126177
	h = h & 0x7FFFFFFF
	h = h ^ (h >> 16)
	return float(h & 0xFFFFFF) / 16777215.0


static func _smooth(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)


## One octave of value noise at an arbitrary position.
static func _value_noise(x: float, y: float, salt: int) -> float:
	var ix: int = floori(x)
	var iy: int = floori(y)
	var fx: float = _smooth(x - float(ix))
	var fy: float = _smooth(y - float(iy))
	var v00: float = _hash2(ix, iy, salt)
	var v10: float = _hash2(ix + 1, iy, salt)
	var v01: float = _hash2(ix, iy + 1, salt)
	var v11: float = _hash2(ix + 1, iy + 1, salt)
	var a: float = v00 + (v10 - v00) * fx
	var b: float = v01 + (v11 - v01) * fx
	return a + (b - a) * fy


## Builds (and caches) a SIZE x SIZE tileable fractal field in [0,1].
## Every octave uses its own wrapped lattice, so the field loops seamlessly.
## The per-row x tables are precomputed: without them the inner loop costs three
## times as much, which is very visible when a dozen textures are built at once.
static func _field(salt: int, base_period: int, octaves: int) -> PackedFloat32Array:
	var key: String = "%d_%d_%d" % [salt, base_period, octaves]
	if _fields.has(key):
		return _fields[key] as PackedFloat32Array

	var out := PackedFloat32Array()
	out.resize(_FIELD_LEN)
	out.fill(0.0)

	var amplitude: float = 1.0
	var sum_amplitude: float = 0.0
	var period: int = maxi(2, base_period)

	for octave in octaves:
		if period > SIZE:
			period = SIZE
		# Wrapped lattice for this octave.
		var lattice := PackedFloat32Array()
		lattice.resize(period * period)
		for j in period:
			var row: int = j * period
			for i in period:
				lattice[row + i] = _hash2(i, j, salt + octave * 7919)

		var step: float = float(period) / float(SIZE)
		# Precomputed x tables.
		var xi0 := PackedInt32Array()
		var xi1 := PackedInt32Array()
		var xw := PackedFloat32Array()
		xi0.resize(SIZE)
		xi1.resize(SIZE)
		xw.resize(SIZE)
		for x in SIZE:
			var xf: float = float(x) * step
			var i0: int = int(xf)
			xw[x] = _smooth(xf - float(i0))
			i0 = i0 % period
			xi0[x] = i0
			xi1[x] = (i0 + 1) % period

		for y in SIZE:
			var yf: float = float(y) * step
			var j0: int = int(yf)
			var wy: float = _smooth(yf - float(j0))
			j0 = j0 % period
			var j1: int = (j0 + 1) % period
			var row0: int = j0 * period
			var row1: int = j1 * period
			var base: int = y * SIZE
			for x in SIZE:
				var a0: int = xi0[x]
				var a1: int = xi1[x]
				var wx: float = xw[x]
				var v00: float = lattice[row0 + a0]
				var v10: float = lattice[row0 + a1]
				var v01: float = lattice[row1 + a0]
				var v11: float = lattice[row1 + a1]
				var top: float = v00 + (v10 - v00) * wx
				var bot: float = v01 + (v11 - v01) * wx
				out[base + x] += (top + (bot - top) * wy) * amplitude

		sum_amplitude += amplitude
		amplitude *= 0.5
		period *= 2

	if sum_amplitude > 0.0:
		var inv: float = 1.0 / sum_amplitude
		for i in _FIELD_LEN:
			out[i] = out[i] * inv

	_fields[key] = out
	return out


## Reads a cached field with integer frequency multipliers. Multiplying the
## coordinates by an integer keeps the 256 px wrap intact, which is how the
## stretched patterns (wood grain, bark furrows, brushed metal) stay tileable.
static func _sample(field: PackedFloat32Array, x: int, y: int, sx: int, sy: int) -> float:
	var px: int = (x * sx) % SIZE
	var py: int = (y * sy) % SIZE
	return field[py * SIZE + px]


# ---------------------------------------------------------------------------
# Shared noise fields
# ---------------------------------------------------------------------------
#
# Building a 256 x 256 fractal field is the expensive part of this file (tens of
# thousands of interpolations), so the whole library draws from a small fixed
# set of fields instead of asking for a private one per texture. Seventeen
# textures then cost seven field builds rather than thirty five, which takes the
# cold start from about 4.5 s down to well under a second.
#
# Reusing a field across textures is safe: no two of them are ever seen side by
# side at the same scale, and each one recombines the fields differently.

## Very large features: dry patches, damp zones, rust blooms.
static func _f_broad() -> PackedFloat32Array:
	return _field(1103, 3, 3)

## Large features, second flavour, decorrelated from `_f_broad`.
static func _f_broad2() -> PackedFloat32Array:
	return _field(2207, 5, 3)

## Mid scale: mottling, stains, clumps.
static func _f_mid() -> PackedFloat32Array:
	return _field(3301, 9, 3)

## Mid scale, second flavour.
static func _f_mid2() -> PackedFloat32Array:
	return _field(4409, 14, 3)

## Fine grain: blades, gravel, plaster tooth.
static func _f_fine() -> PackedFloat32Array:
	return _field(5501, 22, 2)

## Very fine speckle: sand, pits, rivets.
static func _f_speck() -> PackedFloat32Array:
	return _field(6607, 38, 2)

## Directional source, stretched by `_sample` into grain and brushing.
static func _f_streak() -> PackedFloat32Array:
	return _field(7703, 16, 3)


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

## Resolution of the linear to sRGB lookup table.
const _LUT_SIZE := 4096
## Multiplier from a 0..1 linear value to a lookup table index.
const _LUT_SCALE := 4095.0
## Ceiling every albedo texel is clamped to. See `Palette.ALBEDO_MAX`: brighter
## than this and the ACES shoulder desaturates the surface towards white.
const _BAND := 0.38

static var _srgb_lut: PackedByteArray = PackedByteArray()


## Linear value to an sRGB encoded byte.
##
## Table driven: the closed form needs a `pow()` per channel, which works out at
## roughly three million calls to build the whole library and completely
## dominates the cost of this file. The table is built once, in one pass.
static func _enc(v: float) -> int:
	if _srgb_lut.is_empty():
		_build_srgb_lut()
	return _srgb_lut[int(clampf(v, 0.0, 1.0) * float(_LUT_SIZE - 1))]


static func _build_srgb_lut() -> void:
	var lut := PackedByteArray()
	lut.resize(_LUT_SIZE)
	for i in _LUT_SIZE:
		var c: float = float(i) / float(_LUT_SIZE - 1)
		var s: float = 0.0
		if c <= 0.0031308:
			s = 12.92 * c
		else:
			s = 1.055 * pow(c, 1.0 / 2.4) - 0.055
		lut[i] = int(clampf(s * 255.0 + 0.5, 0.0, 255.0))
	_srgb_lut = lut


## Raw linear value to a byte (normal maps, data textures).
static func _raw(v: float) -> int:
	return int(clampf(v * 255.0 + 0.5, 0.0, 255.0))


static func _make_rgb(data: PackedByteArray) -> ImageTexture:
	var img := Image.create_from_data(SIZE, SIZE, false, Image.FORMAT_RGB8, data)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


static func _make_rgba(data: PackedByteArray) -> ImageTexture:
	var img := Image.create_from_data(SIZE, SIZE, false, Image.FORMAT_RGBA8, data)
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


static func _new_rgb_buffer() -> PackedByteArray:
	var data := PackedByteArray()
	data.resize(_FIELD_LEN * 3)
	return data


static func _new_rgba_buffer() -> PackedByteArray:
	var data := PackedByteArray()
	data.resize(_FIELD_LEN * 4)
	return data


## Writes one sRGB encoded RGB texel, clamped into the safe albedo band.
##
## Takes loose floats rather than a Color on purpose: these writers run 65536
## times per texture, and building a Color per texel (plus the static calls on
## Palette that would go with it) costs more than everything else in this file
## put together.
static func _put3(data: PackedByteArray, index: int, r: float, g: float, b: float) -> void:
	if _srgb_lut.is_empty():
		_build_srgb_lut()
	var lut: PackedByteArray = _srgb_lut
	var o: int = index * 3
	data[o] = lut[int(clampf(r, 0.0, _BAND) * _LUT_SCALE)]
	data[o + 1] = lut[int(clampf(g, 0.0, _BAND) * _LUT_SCALE)]
	data[o + 2] = lut[int(clampf(b, 0.0, _BAND) * _LUT_SCALE)]


## Same, with an alpha channel. Still band clamped: leaves and wheat are lit
## surfaces like any other.
static func _put4(data: PackedByteArray, index: int, r: float, g: float, b: float, a: float) -> void:
	if _srgb_lut.is_empty():
		_build_srgb_lut()
	var lut: PackedByteArray = _srgb_lut
	var o: int = index * 4
	data[o] = lut[int(clampf(r, 0.0, _BAND) * _LUT_SCALE)]
	data[o + 1] = lut[int(clampf(g, 0.0, _BAND) * _LUT_SCALE)]
	data[o + 2] = lut[int(clampf(b, 0.0, _BAND) * _LUT_SCALE)]
	data[o + 3] = int(clampf(a, 0.0, 1.0) * 255.0 + 0.5)


## Unclamped RGBA writer, for the one texture that is not an albedo: the cloud
## sheet is an overlay in the sky, not a lit surface, so the 0.38 ceiling does
## not apply to it.
static func _put4_raw(data: PackedByteArray, index: int, r: float, g: float, b: float, a: float) -> void:
	if _srgb_lut.is_empty():
		_build_srgb_lut()
	var lut: PackedByteArray = _srgb_lut
	var o: int = index * 4
	data[o] = lut[int(clampf(r, 0.0, 1.0) * _LUT_SCALE)]
	data[o + 1] = lut[int(clampf(g, 0.0, 1.0) * _LUT_SCALE)]
	data[o + 2] = lut[int(clampf(b, 0.0, 1.0) * _LUT_SCALE)]
	data[o + 3] = int(clampf(a, 0.0, 1.0) * 255.0 + 0.5)



# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

static func _build(texture_name: String) -> Texture2D:
	match texture_name:
		"grass": return _build_grass()
		"dirt": return _build_dirt()
		"road": return _build_road()
		"stone": return _build_stone()
		"wheat": return _build_wheat()
		"sand": return _build_sand()
		"water_normal": return _build_water_normal()
		"plaster": return _build_plaster()
		"wood": return _build_wood()
		"roof_tile": return _build_roof_tile()
		"roof_slate": return _build_roof_slate()
		"concrete": return _build_concrete()
		"metal": return _build_metal()
		"bark": return _build_bark()
		"leaves": return _build_leaves()
		"noise": return _build_noise_map()
		"cloud": return _build_cloud()
	return null

# ---------------------------------------------------------------------------
# Ground family (tileable)
# ---------------------------------------------------------------------------
#
# Every builder below works in loose floats and writes through `_put3` / `_put4`.
# The obvious version (a Color per texel, mixed through Palette.mix and
# Palette.shade) is three times slower: 65536 texels times seventeen textures is
# a great many allocations for a job that is pure arithmetic.

static func _build_grass() -> ImageTexture:
	# Two scales: broad dry / green patches, then a fine blade speckle, with a
	# few bare earth scuffs where the turf has been walked through.
	var patches := _f_broad()
	var blades := _f_fine()
	var scuff := _f_broad2()
	var data := _new_rgb_buffer()
	var wr: float = Palette.GRASS_SUMMER.r
	var wg: float = Palette.GRASS_SUMMER.g
	var wb: float = Palette.GRASS_SUMMER.b
	var dr: float = Palette.GRASS_DRY.r
	var dg: float = Palette.GRASS_DRY.g
	var db: float = Palette.GRASS_DRY.b
	var er: float = Palette.DIRT.r
	var eg: float = Palette.DIRT.g
	var eb: float = Palette.DIRT.b
	for i in _FIELD_LEN:
		var dry: float = clampf(patches[i] * 1.5 - 0.35, 0.0, 1.0)
		var r: float = wr + (dr - wr) * dry
		var g: float = wg + (dg - wg) * dry
		var b: float = wb + (db - wb) * dry
		var bare: float = clampf((scuff[i] - 0.78) * 6.0, 0.0, 1.0) * 0.7
		r += (er - r) * bare
		g += (eg - g) * bare
		b += (eb - b) * bare
		# Biased dark so a whole field never washes out under the noon sun.
		var blade: float = 0.74 + blades[i] * 0.46
		_put3(data, i, r * blade, g * blade, b * blade)
	return _make_rgb(data)


static func _build_dirt() -> ImageTexture:
	var coarse := _f_broad()
	var grain := _f_fine()
	var pebbles := _f_speck()
	var data := _new_rgb_buffer()
	var ar: float = Palette.DIRT.r
	var ag: float = Palette.DIRT.g
	var ab: float = Palette.DIRT.b
	var mr: float = Palette.MUD.r
	var mg: float = Palette.MUD.g
	var mb: float = Palette.MUD.b
	var sr: float = Palette.STONE.r
	var sg: float = Palette.STONE.g
	var sb: float = Palette.STONE.b
	for i in _FIELD_LEN:
		var wet: float = clampf(coarse[i] * 1.4 - 0.3, 0.0, 1.0)
		var r: float = ar + (mr - ar) * wet
		var g: float = ag + (mg - ag) * wet
		var b: float = ab + (mb - ab) * wet
		var lum: float = 0.78 + grain[i] * 0.5
		r *= lum
		g *= lum
		b *= lum
		var stone: float = clampf((pebbles[i] - 0.84) * 9.0, 0.0, 1.0) * 0.8
		_put3(data, i, r + (sr - r) * stone, g + (sg - g) * stone, b + (sb - b) * stone)
	return _make_rgb(data)


static func _build_road() -> ImageTexture:
	# Packed gravel: a dense speckle with a slow patchiness on top, plus mud
	# tracked in from the fields on either side.
	var gravel := _f_speck()
	var patch := _f_broad()
	var mud := _f_mid()
	var data := _new_rgb_buffer()
	var ar: float = Palette.ROAD.r
	var ag: float = Palette.ROAD.g
	var ab: float = Palette.ROAD.b
	var kr: float = Palette.STONE_DARK.r
	var kg: float = Palette.STONE_DARK.g
	var kb: float = Palette.STONE_DARK.b
	var mr: float = Palette.MUD.r
	var mg: float = Palette.MUD.g
	var mb: float = Palette.MUD.b
	for i in _FIELD_LEN:
		var t: float = patch[i]
		var r: float = ar + (kr - ar) * t
		var g: float = ag + (kg - ag) * t
		var b: float = ab + (kb - ab) * t
		var lum: float = 0.80 + gravel[i] * 0.48
		r *= lum
		g *= lum
		b *= lum
		var dirty: float = clampf((mud[i] - 0.62) * 3.2, 0.0, 1.0) * 0.45
		_put3(data, i, r + (mr - r) * dirty, g + (mg - g) * dirty, b + (mb - b) * dirty)
	return _make_rgb(data)


static func _build_sand() -> ImageTexture:
	var grain := _f_speck()
	var ripple := _f_mid()
	var shells := _f_speck()
	var data := _new_rgb_buffer()
	# Normandy beach sand: grey and cold, nowhere near a postcard yellow.
	var br: float = 0.30
	var bg: float = 0.27
	var bb: float = 0.21
	var yr: float = Palette.GRASS_DRY.r
	var yg: float = Palette.GRASS_DRY.g
	var yb: float = Palette.GRASS_DRY.b
	var pr: float = Palette.PLASTER.r
	var pg: float = Palette.PLASTER.g
	var pb: float = Palette.PLASTER.b
	for i in _FIELD_LEN:
		var t: float = ripple[i] * 0.35
		var r: float = br + (yr - br) * t
		var g: float = bg + (yg - bg) * t
		var b: float = bb + (yb - bb) * t
		var lum: float = 0.86 + grain[i] * 0.28
		r *= lum
		g *= lum
		b *= lum
		var shell: float = clampf((shells[i] - 0.9) * 12.0, 0.0, 1.0) * 0.6
		_put3(data, i, r + (pr - r) * shell, g + (pg - g) * shell, b + (pb - b) * shell)
	return _make_rgb(data)


static func _build_stone() -> ImageTexture:
	# Limestone masonry: eight courses of blocks, half offset, deep grout.
	var course_h: int = 32
	var block_w: int = 64
	var grout: int = 3
	var cols: int = SIZE / block_w
	var rows: int = SIZE / course_h
	var mottle := _f_fine()
	var wear := _f_broad2()
	var data := _new_rgb_buffer()

	# One tone per block, resolved before the pixel loop instead of hashing
	# 65536 times for 32 distinct answers.
	var tone := PackedFloat32Array()
	tone.resize(cols * rows)
	for row in rows:
		for col in cols:
			tone[row * cols + col] = _hash2(col, row, 7717) * 0.55

	var lr: float = Palette.STONE.r
	var lg: float = Palette.STONE.g
	var lb: float = Palette.STONE.b
	var kr: float = Palette.STONE_DARK.r
	var kg: float = Palette.STONE_DARK.g
	var kb: float = Palette.STONE_DARK.b
	# Grout: dark stone dragged towards mud, then knocked back a notch.
	var gr: float = (kr + (Palette.MUD.r - kr) * 0.4) * 0.9
	var gg: float = (kg + (Palette.MUD.g - kg) * 0.4) * 0.9
	var gb: float = (kb + (Palette.MUD.b - kb) * 0.4) * 0.9
	var vr: float = Palette.GRASS_SUMMER.r
	var vg: float = Palette.GRASS_SUMMER.g
	var vb: float = Palette.GRASS_SUMMER.b

	for y in SIZE:
		var base: int = y * SIZE
		var course: int = y / course_h
		var y_in: int = y - course * course_h
		var offset: int = (course % 2) * (block_w / 2)
		var edge_y: float = clampf(float(mini(y_in, course_h - 1 - y_in)) / 5.0, 0.0, 1.0)
		var grout_row: bool = y_in < grout
		var tone_row: int = course * cols
		for x in SIZE:
			var i: int = base + x
			var xs: int = (x + offset) % SIZE
			var block: int = xs / block_w
			var x_in: int = xs - block * block_w
			var r: float
			var g: float
			var b: float
			if grout_row or x_in < grout:
				r = gr
				g = gg
				b = gb
			else:
				var t: float = tone[tone_row + block]
				r = lr + (kr - lr) * t
				g = lg + (kg - lg) * t
				b = lb + (kb - lb) * t
				# Each block is slightly domed, so its rim reads darker.
				var edge_x: float = clampf(float(mini(x_in, block_w - 1 - x_in)) / 7.0, 0.0, 1.0)
				var lum: float = (0.85 + mottle[i] * 0.30) * (0.82 + 0.18 * minf(edge_x, edge_y))
				r *= lum
				g *= lum
				b *= lum
			# Lichen and damp streaks creeping over everything, grout included.
			var damp: float = clampf((wear[i] - 0.7) * 3.4, 0.0, 1.0) * 0.22
			_put3(data, i, r + (vr - r) * damp, g + (vg - g) * damp, b + (vb - b) * damp)
	return _make_rgb(data)


static func _build_noise_map() -> ImageTexture:
	# Generic greyscale utility map, tileable, spanning three scales. Written
	# raw and not through the sRGB table: this is data, not colour. A shader
	# that binds it as `source_color` will see it gamma shifted, which is the
	# caller's problem to solve.
	var broad := _f_broad()
	var mid := _f_mid()
	var fine := _f_fine()
	var data := _new_rgb_buffer()
	for i in _FIELD_LEN:
		var v: float = clampf(broad[i] * 0.52 + mid[i] * 0.31 + fine[i] * 0.17, 0.0, 1.0)
		var o: int = i * 3
		var b: int = _raw(v)
		data[o] = b
		data[o + 1] = b
		data[o + 2] = b
	return _make_rgb(data)


# ---------------------------------------------------------------------------
# Built surfaces
# ---------------------------------------------------------------------------

static func _build_plaster() -> ImageTexture:
	var mottle := _f_broad2()
	var fine := _f_fine()
	var crack := _f_mid()
	var data := _new_rgb_buffer()
	var pr: float = Palette.PLASTER.r
	var pg: float = Palette.PLASTER.g
	var pb: float = Palette.PLASTER.b
	var sr: float = Palette.STONE.r
	var sg: float = Palette.STONE.g
	var sb: float = Palette.STONE.b
	var kr: float = Palette.STONE_DARK.r
	var kg: float = Palette.STONE_DARK.g
	var kb: float = Palette.STONE_DARK.b
	var mr: float = Palette.MUD.r
	var mg: float = Palette.MUD.g
	var mb: float = Palette.MUD.b
	for y in SIZE:
		var base: int = y * SIZE
		# Damp climbing out of the ground, strongest at the foot of the wall.
		var rise: float = 1.0 - float(y) / float(SIZE)
		var rise2: float = rise * rise
		for x in SIZE:
			var i: int = base + x
			var t: float = mottle[i] * 0.5
			var r: float = pr + (sr - pr) * t
			var g: float = pg + (sg - pg) * t
			var b: float = pb + (sb - pb) * t
			var lum: float = 0.88 + fine[i] * 0.24
			r *= lum
			g *= lum
			b *= lum
			# Hairline cracks: the zero crossing of a noise field draws a
			# wandering curve through the wall for free.
			var d: float = absf(crack[i] - 0.5)
			if d < 0.012:
				var k: float = (1.0 - d / 0.012) * 0.85
				r += (kr - r) * k
				g += (kg - g) * k
				b += (kb - b) * k
			var stain: float = clampf((mottle[i] - 0.55) * 2.4, 0.0, 1.0) * rise2 * 0.35
			_put3(data, i, r + (mr - r) * stain, g + (mg - g) * stain, b + (mb - b) * stain)
	return _make_rgb(data)


static func _build_wood() -> ImageTexture:
	# Horizontal planks with a grain stretched along X.
	var plank_h: int = 32
	var grain := _f_streak()
	var knots := _f_mid()
	var data := _new_rgb_buffer()
	var wr: float = Palette.WOOD.r
	var wg: float = Palette.WOOD.g
	var wb: float = Palette.WOOD.b
	var lr: float = Palette.WOOD_LIGHT.r
	var lg: float = Palette.WOOD_LIGHT.g
	var lb: float = Palette.WOOD_LIGHT.b
	var kr: float = Palette.STONE_DARK.r
	var kg: float = Palette.STONE_DARK.g
	var kb: float = Palette.STONE_DARK.b
	for y in SIZE:
		var base: int = y * SIZE
		var plank: int = y / plank_h
		var y_in: int = y - plank * plank_h
		var plank_tone: float = 0.82 + _hash2(plank, 3, 5501) * 0.34
		var gap: bool = y_in < 2
		for x in SIZE:
			var i: int = base + x
			if gap:
				# The shadowed joint between two boards.
				_put3(data, i, wr * 0.45, wg * 0.45, wb * 0.45)
				continue
			# Squeezing the sampling in Y stretches the grain along X.
			var t: float = _sample(grain, x, y, 1, 6)
			var r: float = wr + (lr - wr) * t
			var g: float = wg + (lg - wg) * t
			var b: float = wb + (lb - wb) * t
			var lum: float = plank_tone * (0.88 + t * 0.20)
			r *= lum
			g *= lum
			b *= lum
			# A knot: a dark disc where the low frequency field peaks.
			var k: float = clampf((knots[i] - 0.86) * 8.0, 0.0, 1.0) * 0.8
			_put3(data, i, r + (kr - r) * k, g + (kg - g) * k, b + (kb - b) * k)
	return _make_rgb(data)


static func _build_bark() -> ImageTexture:
	# Deep vertical furrows: the noise is squeezed hard along X.
	var furrow := _f_streak()
	var rough := _f_speck()
	var data := _new_rgb_buffer()
	var br: float = Palette.WOOD.r + (Palette.STONE_DARK.r - Palette.WOOD.r) * 0.35
	var bg: float = Palette.WOOD.g + (Palette.STONE_DARK.g - Palette.WOOD.g) * 0.35
	var bb: float = Palette.WOOD.b + (Palette.STONE_DARK.b - Palette.WOOD.b) * 0.35
	var lr: float = Palette.LEAF_DARK.r
	var lg: float = Palette.LEAF_DARK.g
	var lb: float = Palette.LEAF_DARK.b
	var inv_size: float = 1.0 / float(SIZE)
	for y in SIZE:
		var base: int = y * SIZE
		for x in SIZE:
			var i: int = base + x
			var f: float = _sample(furrow, x, y, 5, 1)
			var groove: float = absf(f - 0.5) * 2.0
			var lum: float = (0.55 + groove * 0.72) * (0.9 + rough[i] * 0.2)
			var r: float = br * lum
			var g: float = bg * lum
			var b: float = bb * lum
			# Moss, and only on one side of the trunk.
			var side: float = clampf(1.0 - absf(float(x) * inv_size - 0.25) * 4.0, 0.0, 1.0)
			var moss: float = clampf((rough[i] - 0.66) * 2.6, 0.0, 1.0) * side * 0.35
			_put3(data, i, r + (lr - r) * moss, g + (lg - g) * moss, b + (lb - b) * moss)
	return _make_rgb(data)


static func _build_roof_tile() -> ImageTexture:
	# Curved terracotta pantiles: 8 columns, 8 rows, offset every other row.
	var col_w: int = 32
	var row_h: int = 32
	var cols: int = SIZE / col_w
	var rows: int = SIZE / row_h
	var mottle := _f_fine()
	var age := _f_broad2()
	var data := _new_rgb_buffer()

	var tone := PackedFloat32Array()
	tone.resize(cols * rows)
	for row in rows:
		for col in cols:
			tone[row * cols + col] = 0.80 + _hash2(col, row, 9127) * 0.40
	# Barrel shading across the width of a tile, resolved once.
	var curve := PackedFloat32Array()
	curve.resize(col_w)
	for k in col_w:
		curve[k] = sin(float(k) / float(col_w) * PI)

	var tr: float = Palette.ROOF_TILE.r
	var tg: float = Palette.ROOF_TILE.g
	var tb: float = Palette.ROOF_TILE.b
	var ur: float = Palette.RUST.r
	var ug: float = Palette.RUST.g
	var ub: float = Palette.RUST.b
	var sr: float = Palette.STONE.r
	var sg: float = Palette.STONE.g
	var sb: float = Palette.STONE.b

	for y in SIZE:
		var base: int = y * SIZE
		var row: int = y / row_h
		var y_in: int = y - row * row_h
		var offset: int = (row % 2) * (col_w / 2)
		# The course above overlaps this one and casts a shadow on its head.
		var overlap: float = 1.0
		if y_in < 4:
			overlap = 0.42 + float(y_in) * 0.12
		var tone_row: int = row * cols
		for x in SIZE:
			var i: int = base + x
			var xs: int = (x + offset) % SIZE
			var col: int = xs / col_w
			var x_in: int = xs - col * col_w
			var t: float = mottle[i] * 0.45
			var r: float = tr + (ur - tr) * t
			var g: float = tg + (ug - tg) * t
			var b: float = tb + (ub - tb) * t
			var lum: float = tone[tone_row + col] * (0.52 + curve[x_in] * 0.62) * overlap
			r *= lum
			g *= lum
			b *= lum
			# Lichen greying the whole roof with age.
			var old: float = clampf((age[i] - 0.6) * 2.6, 0.0, 1.0) * 0.42
			_put3(data, i, r + (sr - r) * old, g + (sg - g) * old, b + (sb - b) * old)
	return _make_rgb(data)


static func _build_roof_slate() -> ImageTexture:
	# Flat rectangular slates, 8 courses of 8, half offset.
	var col_w: int = 32
	var row_h: int = 32
	var cols: int = SIZE / col_w
	var rows: int = SIZE / row_h
	var grain := _f_fine()
	var data := _new_rgb_buffer()

	var tone := PackedFloat32Array()
	tone.resize(cols * rows)
	for row in rows:
		for col in cols:
			tone[row * cols + col] = 0.75 + _hash2(col, row, 3391) * 0.55

	var sr: float = Palette.ROOF_SLATE.r
	var sg: float = Palette.ROOF_SLATE.g
	var sb: float = Palette.ROOF_SLATE.b

	for y in SIZE:
		var base: int = y * SIZE
		var row: int = y / row_h
		var y_in: int = y - row * row_h
		var offset: int = (row % 2) * (col_w / 2)
		var tone_row: int = row * cols
		# Slates are laid overlapping, so the head is in shadow and the tail
		# catches the light.
		var head: bool = y_in < 3
		var tail: bool = y_in > row_h - 6
		for x in SIZE:
			var i: int = base + x
			var xs: int = (x + offset) % SIZE
			var col: int = xs / col_w
			var lum: float = tone[tone_row + col] * (0.9 + grain[i] * 0.24)
			if head:
				lum *= 0.35
			elif xs - col * col_w < 2:
				lum *= 0.55
			elif tail:
				lum *= 1.12
			_put3(data, i, sr * lum, sg * lum, sb * lum)
	return _make_rgb(data)


static func _build_concrete() -> ImageTexture:
	var speckle := _f_speck()
	var stain := _f_broad()
	var form := _f_mid()
	var data := _new_rgb_buffer()
	var cr: float = Palette.CONCRETE.r
	var cg: float = Palette.CONCRETE.g
	var cb: float = Palette.CONCRETE.b
	var kr: float = Palette.STONE_DARK.r
	var kg: float = Palette.STONE_DARK.g
	var kb: float = Palette.STONE_DARK.b
	var dr: float = Palette.DIRT.r
	var dg: float = Palette.DIRT.g
	var db: float = Palette.DIRT.b
	for y in SIZE:
		var base: int = y * SIZE
		# The line left by the edge of a formwork board.
		var board: float = 0.72 if (y % 64) < 2 else 1.0
		for x in SIZE:
			var i: int = base + x
			var lum: float = (0.86 + speckle[i] * 0.26) * board
			var r: float = cr * lum
			var g: float = cg * lum
			var b: float = cb * lum
			# Water streaks and blast soot.
			var s: float = clampf((stain[i] - 0.5) * 2.2, 0.0, 1.0) * 0.45
			r += (kr - r) * s
			g += (kg - g) * s
			b += (kb - b) * s
			# Chipped corners showing the aggregate underneath.
			var chip: float = clampf((form[i] - 0.88) * 9.0, 0.0, 1.0) * 0.7
			_put3(data, i, r + (dr - r) * chip, g + (dg - g) * chip, b + (db - b) * chip)
	return _make_rgb(data)


static func _build_metal() -> ImageTexture:
	# Brushed plate with rust creeping in from the low frequency field.
	var brush := _f_streak()
	var rust := _f_broad()
	var pit := _f_speck()
	var data := _new_rgb_buffer()
	var mr: float = Palette.METAL.r
	var mg: float = Palette.METAL.g
	var mb: float = Palette.METAL.b
	var ur: float = Palette.RUST.r
	var ug: float = Palette.RUST.g
	var ub: float = Palette.RUST.b
	for y in SIZE:
		var base: int = y * SIZE
		var rivet_row: bool = (y % 32) > 27
		for x in SIZE:
			var i: int = base + x
			var lum: float = 0.82 + _sample(brush, x, y, 1, 8) * 0.4
			var r: float = mr * lum
			var g: float = mg * lum
			var b: float = mb * lum
			var rusty: float = clampf((rust[i] - 0.48) * 2.6, 0.0, 1.0) * 0.85
			r += (ur - r) * rusty
			g += (ug - g) * rusty
			b += (ub - b) * rusty
			var pitting: float = 1.0 - clampf((pit[i] - 0.85) * 8.0, 0.0, 1.0) * 0.45
			# A line of rivets down the seam of the plate.
			if rivet_row and (x % 64) > 60:
				pitting *= 1.25
			_put3(data, i, r * pitting, g * pitting, b * pitting)
	return _make_rgb(data)


# ---------------------------------------------------------------------------
# Cut out textures (alpha scissor)
# ---------------------------------------------------------------------------

static func _build_leaves() -> ImageTexture:
	# A foliage card: an irregular clump of leaves with holes through it.
	# The alpha is hard, never gradual, because the material cuts it with
	# ALPHA_SCISSOR at 0.5 rather than blending it.
	var clump := _f_broad()
	var detail := _f_mid2()
	var tone := _f_mid()
	var data := _new_rgba_buffer()
	var half: float = float(SIZE) * 0.5
	var dr: float = Palette.LEAF_DARK.r
	var dg: float = Palette.LEAF_DARK.g
	var db: float = Palette.LEAF_DARK.b
	var lr: float = Palette.LEAF_LIGHT.r
	var lg: float = Palette.LEAF_LIGHT.g
	var lb: float = Palette.LEAF_LIGHT.b
	for y in SIZE:
		var base: int = y * SIZE
		var dy: float = (float(y) - half) / half
		var dy2: float = dy * dy
		for x in SIZE:
			var i: int = base + x
			var dx: float = (float(x) - half) / half
			# Radial falloff keeps the clump from filling its whole quad.
			var radius: float = sqrt(dx * dx + dy2)
			var mask: float = clump[i] * 0.65 + detail[i] * 0.35
			mask -= clampf((radius - 0.45) * 1.35, 0.0, 1.0)
			var alpha: float = 1.0 if mask > 0.45 else 0.0
			var t: float = tone[i]
			# Leaves catch the light at their tips and go dark in the mass.
			var lum: float = 0.72 + detail[i] * 0.5
			_put4(data, i,
					(dr + (lr - dr) * t) * lum,
					(dg + (lg - dg) * t) * lum,
					(db + (lb - db) * t) * lum,
					alpha)
	return _make_rgba(data)


static func _build_wheat() -> ImageTexture:
	# A card of standing wheat: vertical stalks with heavy ears near the top.
	# Row 0 is the top of the card, so the stalks grow upwards on screen.
	var jitter := _f_speck()
	var data := _new_rgba_buffer()
	var stalk_w: int = 6
	var tops := PackedInt32Array()
	var widths := PackedInt32Array()
	var tones := PackedFloat32Array()
	tops.resize(SIZE)
	widths.resize(SIZE)
	tones.resize(SIZE)
	for x in SIZE:
		var col: int = x / stalk_w
		tops[x] = int(12.0 + _hash2(col, 11, 4813) * 46.0)
		widths[x] = 2 + int(_hash2(col, 27, 991) * 2.0)
		tones[x] = 0.72 + _hash2(col, 41, 1327) * 0.5

	var wr: float = Palette.WHEAT.r
	var wg: float = Palette.WHEAT.g
	var wb: float = Palette.WHEAT.b
	# The ear: fatter and paler than the stem.
	var er: float = wr + (Palette.GRASS_DRY.r - wr) * 0.25
	var eg: float = wg + (Palette.GRASS_DRY.g - wg) * 0.25
	var eb: float = wb + (Palette.GRASS_DRY.b - wb) * 0.25
	var sr: float = Palette.GRASS_SUMMER.r
	var sg: float = Palette.GRASS_SUMMER.g
	var sb: float = Palette.GRASS_SUMMER.b
	var inv_size: float = 1.0 / float(SIZE)

	for y in SIZE:
		var base: int = y * SIZE
		for x in SIZE:
			var i: int = base + x
			var col: int = x / stalk_w
			var x_in: int = x - col * stalk_w
			var lean: int = int((jitter[i] - 0.5) * 3.0)
			var top: int = tops[x]
			var tone: float = tones[x]
			var alpha: float = 0.0
			var r: float = wr
			var g: float = wg
			var b: float = wb
			if x_in >= lean and x_in < widths[x] + lean:
				if y >= top:
					alpha = 1.0
					if y < top + 40:
						r = er * tone * 1.12
						g = eg * tone * 1.12
						b = eb * tone * 1.12
					else:
						# The stem: greener and darker the further down it goes.
						var depth: float = float(y - top) * inv_size
						var k: float = clampf(depth * 1.4, 0.0, 0.7)
						var lum: float = tone * (1.0 - depth * 0.35)
						r = (wr + (sr - wr) * k) * lum
						g = (wg + (sg - wg) * k) * lum
						b = (wb + (sb - wb) * k) * lum
				elif y >= top - 3:
					# A ragged tip, so the head of the ear is not a flat cut.
					alpha = 1.0 if jitter[i] > 0.45 else 0.0
					r = wr * tone
					g = wg * tone
					b = wb * tone
			_put4(data, i, r, g, b, alpha)
	return _make_rgba(data)


static func _build_cloud() -> ImageTexture:
	# Overcast cloud sheet: RGB is a light grey, alpha carries the coverage.
	# Not the albedo of a lit surface, so the 0.38 band does not apply here.
	var f := _f_broad()
	var g := _f_mid()
	var h := _f_mid2()
	var data := _new_rgba_buffer()
	for i in _FIELD_LEN:
		var v: float = clampf((f[i] * 0.58 + g[i] * 0.27 + h[i] * 0.15 - 0.34) * 2.3, 0.0, 1.0)
		var alpha: float = v * v * (3.0 - 2.0 * v)
		# Cloud bases are darker than their tops.
		var lit: float = 0.42 + alpha * 0.46
		_put4_raw(data, i, lit, lit * 1.01, lit * 1.05, alpha)
	return _make_rgba(data)


# ---------------------------------------------------------------------------
# Normal map
# ---------------------------------------------------------------------------

static func _build_water_normal() -> ImageTexture:
	# Two crossed ripple trains, encoded as a tangent space normal map.
	# Written raw on purpose: Godot binds a normal map through a LINEAR view, so
	# running these bytes through the sRGB table would tilt every normal.
	var a := _f_mid()
	var b := _f_mid2()
	var height := PackedFloat32Array()
	height.resize(_FIELD_LEN)
	for y in SIZE:
		var base: int = y * SIZE
		var y_term: float = float(y) * 0.13
		for x in SIZE:
			var i: int = base + x
			var wave: float = sin(float(x) * 0.19 + a[i] * 6.0) * 0.5
			wave += sin(y_term + b[i] * 5.0) * 0.35
			height[i] = wave * 0.5 + a[i] * 0.4

	var data := _new_rgb_buffer()
	var strength: float = 2.4
	for y in SIZE:
		var base: int = y * SIZE
		var up: int = ((y - 1 + SIZE) % SIZE) * SIZE
		var down: int = ((y + 1) % SIZE) * SIZE
		for x in SIZE:
			var i: int = base + x
			var xl: int = (x - 1 + SIZE) % SIZE
			var xr: int = (x + 1) % SIZE
			var dhdx: float = (height[base + xr] - height[base + xl]) * strength
			var dhdy: float = (height[down + x] - height[up + x]) * strength
			var n := Vector3(-dhdx, -dhdy, 1.0).normalized()
			var o: int = i * 3
			data[o] = _raw(n.x * 0.5 + 0.5)
			data[o + 1] = _raw(n.y * 0.5 + 0.5)
			data[o + 2] = _raw(n.z * 0.5 + 0.5)
	return _make_rgb(data)
