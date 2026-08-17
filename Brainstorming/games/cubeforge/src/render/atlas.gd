class_name VoxelAtlas
## Procedural texture atlas for CUBEFORGE.
##
## Every one of the 53 tiles listed in Blocks.TILE_NAMES is painted by code into
## a 32x32 RGBA8 Image, then stacked into a Texture2DArray whose layer index is
## exactly the index in Blocks.TILE_NAMES.
##
## Two invariants drive the whole file:
##
## 1. Tiles must be seamlessly tileable. Every noise field wraps on a lattice
##    whose period divides the tile size, every scatter primitive writes through
##    a wrapping setter, and every centred motif (log top, pumpkin top) carries a
##    uniform border so opposite edges match.
## 2. Tiles must be byte identical on every launch. Randomness comes from a
##    RandomNumberGenerator seeded with a hash of the tile name and from an
##    integer lattice hash, never from the global RNG or from time.
##
## Biome tinted tiles (grass_top, oak_leaves, birch_leaves, grass_tuft, fern,
## sapling) are painted in near-white greyscale because the vertex colour
## multiplies them. Every other tile carries its final colour.

## Edge length of one tile, in pixels.
const S := Blocks.TILE_PIXELS

## Green used to preview biome tinted tiles in the interface, where no vertex
## colour exists to do the tinting.
const PREVIEW_TINT := Color(0.44, 0.72, 0.38)

const CLEAR := Color(0.0, 0.0, 0.0, 0.0)

## tile name -> painted Image (without mipmaps). Callers always receive a copy.
static var _cache: Dictionary = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Builds the complete Texture2DArray. Expensive, called once at startup.
static func build() -> Texture2DArray:
	var images: Array[Image] = []
	images.resize(Blocks.TILE_COUNT)
	for i in Blocks.TILE_COUNT:
		var img := tile_image(Blocks.TILE_NAMES[i])
		# Mipmaps feed the anisotropic filtering of the voxel shaders, without
		# them distant terrain turns into a shimmering moire.
		var err := img.generate_mipmaps()
		if err != OK:
			push_warning("VoxelAtlas: mipmaps failed for tile '%s'" % Blocks.TILE_NAMES[i])
		images[i] = img
	var tex := Texture2DArray.new()
	var create_err := tex.create_from_images(images)
	if create_err != OK:
		push_error("VoxelAtlas: create_from_images failed with error %d" % create_err)
	return tex


## RGBA8 32x32 image of one named tile, handy for 2D previews and particles.
## The returned image is a fresh copy, callers may modify it freely.
static func tile_image(tile_name: String) -> Image:
	if _cache.has(tile_name):
		var cached: Image = _cache[tile_name]
		return cached.duplicate() as Image
	var img := Image.create_empty(S, S, false, Image.FORMAT_RGBA8)
	img.fill(CLEAR)
	_draw_tile(tile_name, img)
	if img.detect_alpha() != Image.ALPHA_NONE:
		# Transparent pixels keep black rgb otherwise, which bleeds dark halos
		# into the mipmap chain of leaves and plants.
		_bleed_alpha(img)
	_cache[tile_name] = img
	return img.duplicate() as Image


## Square 2D preview of a block for the hotbar and the inventory. Uses the top
## face for cubes and the single tile for cross blocks, scaled up with nearest
## neighbour so the pixel art stays crisp.
static func block_preview(block_id: int, size: int = 48) -> ImageTexture:
	var px := maxi(size, 8)
	if block_id < 0 or block_id >= Blocks.COUNT or Blocks.is_air(block_id):
		var blank := Image.create_empty(px, px, false, Image.FORMAT_RGBA8)
		blank.fill(CLEAR)
		return ImageTexture.create_from_image(blank)

	var face := Blocks.FACE_PY
	if Blocks.is_cross(block_id):
		face = Blocks.FACE_PX
	var layer := Blocks.tile_of(block_id, face)
	var img := tile_image(Blocks.TILE_NAMES[layer])
	# Face bit layout of Blocks is 1 << face, so a shift is enough.
	if (Blocks.tint_mask(block_id) & (1 << face)) != 0:
		_multiply(img, PREVIEW_TINT)
	img.resize(px, px, Image.INTERPOLATE_NEAREST)
	return ImageTexture.create_from_image(img)


# ---------------------------------------------------------------------------
# Deterministic hashing and wrapping value noise
# ---------------------------------------------------------------------------

## Per tile seed. String.hash() is stable across launches and platforms.
static func _seed_of(tile_name: String) -> int:
	return tile_name.hash() & 0x7FFFFFFF


## Integer lattice hash in 0..1. Every multiplication stays inside int64.
static func _lattice(ix: int, iy: int, seed_i: int) -> float:
	var h: int = (ix * 73856093) ^ (iy * 19349663) ^ ((seed_i & 0xFFFFF) * 83492791)
	h = h & 0x7FFFFFFF
	h = ((h ^ (h >> 15)) * 2246822519) & 0x7FFFFFFF
	h = ((h ^ (h >> 13)) * 3266489917) & 0x7FFFFFFF
	h = h ^ (h >> 16)
	return float(h & 0xFFFFFF) / 16777215.0


static func _smooth(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)


## Value noise field of S * S floats in 0..1, bilinearly interpolated over a
## lattice of px by py cells. Wrapping the lattice indices makes the field
## tileable for any positive px and py.
static func _noise_field(px: int, py: int, seed_i: int) -> PackedFloat32Array:
	var cx := maxi(px, 1)
	var cy := maxi(py, 1)
	var lat := PackedFloat32Array()
	lat.resize(cx * cy)
	for iy in cy:
		for ix in cx:
			lat[iy * cx + ix] = _lattice(ix, iy, seed_i)

	var out := PackedFloat32Array()
	out.resize(S * S)
	var step_x := float(cx) / float(S)
	var step_y := float(cy) / float(S)
	for y in S:
		var fy := float(y) * step_y
		var iy0 := int(floor(fy))
		var ty := _smooth(fy - float(iy0))
		var row0 := posmod(iy0, cy) * cx
		var row1 := posmod(iy0 + 1, cy) * cx
		var base := y * S
		for x in S:
			var fx := float(x) * step_x
			var ix0 := int(floor(fx))
			var tx := _smooth(fx - float(ix0))
			var col0 := posmod(ix0, cx)
			var col1 := posmod(ix0 + 1, cx)
			var top := lerpf(lat[row0 + col0], lat[row0 + col1], tx)
			var bottom := lerpf(lat[row1 + col0], lat[row1 + col1], tx)
			out[base + x] = lerpf(top, bottom, ty)
	return out


## Fractal sum of _noise_field. An axis whose cell count is 1 stays at 1, which
## keeps strictly horizontal or vertical patterns (strata, fibres) clean.
static func _fbm_field(px: int, py: int, octaves: int, seed_i: int) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(S * S)
	var ax := maxi(px, 1)
	var ay := maxi(py, 1)
	var amp := 1.0
	var norm := 0.0
	for o in maxi(octaves, 1):
		var f := _noise_field(ax, ay, seed_i + o * 977)
		for i in S * S:
			out[i] += amp * f[i]
		norm += amp
		amp *= 0.5
		ax = mini(ax * 2, S) if px > 1 else 1
		ay = mini(ay * 2, S) if py > 1 else 1
	if norm > 0.0:
		for i in S * S:
			out[i] /= norm
	return out


# ---------------------------------------------------------------------------
# Pixel primitives, all of them wrapping so nothing breaks tileability
# ---------------------------------------------------------------------------

static func _px(img: Image, x: int, y: int, col: Color) -> void:
	img.set_pixel(posmod(x, S), posmod(y, S), col)


## Source over destination compositing on a wrapped coordinate.
static func _blend_px(img: Image, x: int, y: int, col: Color) -> void:
	if col.a >= 0.999:
		_px(img, x, y, col)
		return
	if col.a <= 0.001:
		return
	var sx := posmod(x, S)
	var sy := posmod(y, S)
	var dst := img.get_pixel(sx, sy)
	var out_a := col.a + dst.a * (1.0 - col.a)
	if out_a <= 0.0001:
		img.set_pixel(sx, sy, CLEAR)
		return
	var inv := dst.a * (1.0 - col.a)
	img.set_pixel(sx, sy, Color(
		(col.r * col.a + dst.r * inv) / out_a,
		(col.g * col.a + dst.g * inv) / out_a,
		(col.b * col.a + dst.b * inv) / out_a,
		out_a))


static func _paint_field(img: Image, field: PackedFloat32Array, low: Color, high: Color) -> void:
	for y in S:
		var base := y * S
		for x in S:
			img.set_pixel(x, y, low.lerp(high, field[base + x]))


## Multiplies the existing pixels by a noise field to add grain without
## touching the overall hue. `strength` is the peak to peak amplitude.
static func _grain(img: Image, field: PackedFloat32Array, strength: float) -> void:
	for y in S:
		var base := y * S
		for x in S:
			var c := img.get_pixel(x, y)
			if c.a <= 0.001:
				continue
			var f := 1.0 + (field[base + x] - 0.5) * strength
			img.set_pixel(x, y, Color(
				clampf(c.r * f, 0.0, 1.0),
				clampf(c.g * f, 0.0, 1.0),
				clampf(c.b * f, 0.0, 1.0),
				c.a))


static func _multiply(img: Image, tint: Color) -> void:
	for y in S:
		for x in S:
			var c := img.get_pixel(x, y)
			img.set_pixel(x, y, Color(c.r * tint.r, c.g * tint.g, c.b * tint.b, c.a))


static func _disc(img: Image, cx: int, cy: int, r: int, col: Color) -> void:
	if r <= 0:
		_blend_px(img, cx, cy, col)
		return
	var limit := r * r + r
	for dy in range(-r, r + 1):
		for dx in range(-r, r + 1):
			if dx * dx + dy * dy <= limit:
				_blend_px(img, cx + dx, cy + dy, col)


## Bresenham line, wrapped. Used for cracks and twigs.
static func _line(img: Image, x0: int, y0: int, x1: int, y1: int, col: Color) -> void:
	var x := x0
	var y := y0
	var dx := absi(x1 - x0)
	var dy := absi(y1 - y0)
	var sx := 1 if x1 >= x0 else -1
	var sy := 1 if y1 >= y0 else -1
	var err := dx - dy
	var guard := 0
	while guard < 256:
		guard += 1
		_blend_px(img, x, y, col)
		if x == x1 and y == y1:
			return
		var e2 := err * 2
		if e2 > -dy:
			err -= dy
			x += sx
		if e2 < dx:
			err += dx
			y += sy


## Scatters small discs, the workhorse for mineral flecks and grit.
static func _speckle(img: Image, rng: RandomNumberGenerator, count: int, col_a: Color, col_b: Color, max_radius: int) -> void:
	for _i in count:
		var cx := rng.randi_range(0, S - 1)
		var cy := rng.randi_range(0, S - 1)
		var r := rng.randi_range(0, maxi(max_radius, 0))
		_disc(img, cx, cy, r, col_a.lerp(col_b, rng.randf()))


## Pebble field built from a wrapped Voronoi diagram: each cell is one stone,
## the gap between cells becomes mortar. `joint` is the mortar half width in
## pixels, zero disables it (loose gravel). `relief` shades cells towards their
## own border to fake roundness.
static func _stones(img: Image, rng: RandomNumberGenerator, count: int, low: Color, high: Color, mortar: Color, joint: float, relief: float) -> void:
	var seeds := count
	var sx := PackedInt32Array()
	var sy := PackedInt32Array()
	var tone := PackedFloat32Array()
	sx.resize(seeds)
	sy.resize(seeds)
	tone.resize(seeds)
	for i in seeds:
		sx[i] = rng.randi_range(0, S - 1)
		sy[i] = rng.randi_range(0, S - 1)
		tone[i] = rng.randf()

	for y in S:
		for x in S:
			var best := 1.0e9
			var second := 1.0e9
			var best_i := 0
			for i in seeds:
				var dx := absi(x - sx[i])
				dx = mini(dx, S - dx)
				var dy := absi(y - sy[i])
				dy = mini(dy, S - dy)
				var d := float(dx * dx + dy * dy)
				if d < best:
					second = best
					best = d
					best_i = i
				elif d < second:
					second = d
			var edge := sqrt(second) - sqrt(best)
			if joint > 0.0 and edge < joint:
				img.set_pixel(x, y, mortar)
				continue
			var c := low.lerp(high, tone[best_i])
			var lift := clampf((edge - joint) / maxf(relief, 0.001), 0.0, 1.0)
			img.set_pixel(x, y, c.darkened((1.0 - lift) * 0.26))


## Regular masonry. `running_bond` shifts every other course by half a brick.
static func _brick_courses(img: Image, rows: int, cols: int, mortar: Color, low: Color, high: Color, mortar_px: int, running_bond: bool, seed_i: int) -> void:
	var row_h := maxi(S / maxi(rows, 1), 2)
	var col_w := maxi(S / maxi(cols, 1), 2)
	var grain := _fbm_field(8, 8, 3, seed_i + 313)
	for y in S:
		var row := y / row_h
		var shift := 0
		if running_bond and row % 2 == 1:
			shift = col_w / 2
		var iy := y % row_h
		for x in S:
			var lx := posmod(x - shift, S)
			var g := grain[y * S + x]
			if iy < mortar_px or (lx % col_w) < mortar_px:
				img.set_pixel(x, y, mortar.lerp(mortar.lightened(0.14), g))
				continue
			var base := low.lerp(high, _lattice(lx / col_w, row, seed_i))
			var c := base.lerp(base.darkened(0.20), 1.0 - g)
			if iy == mortar_px:
				c = c.lightened(0.10)
			elif iy == row_h - 1:
				c = c.darkened(0.14)
			img.set_pixel(x, y, c)


## Horizontal boards with a dark seam, a lengthwise grain and a few butt joints.
static func _plank_courses(img: Image, rng: RandomNumberGenerator, rows: int, low: Color, high: Color, seam: Color, seed_i: int) -> void:
	var row_h := maxi(S / maxi(rows, 1), 2)
	# Grain runs along X: little variation across X, plenty along Y.
	var grain := _fbm_field(3, 24, 3, seed_i + 61)
	for y in S:
		var row := y / row_h
		var iy := y % row_h
		var board := low.lerp(high, _lattice(row, 3, seed_i))
		for x in S:
			var g := grain[y * S + x]
			var c := board.lerp(board.darkened(0.26), 1.0 - g)
			if iy == 0:
				c = seam
			elif iy == 1:
				c = c.lightened(0.10)
			elif iy == row_h - 1:
				c = c.darkened(0.12)
			img.set_pixel(x, y, c)
	# Butt joints, one per board, never at x = 0 so the wrap stays clean.
	for row in S / row_h:
		var jx := rng.randi_range(4, S - 5)
		for iy in range(2, row_h - 1):
			_px(img, jx, row * row_h + iy, seam.lightened(0.08))


## Vertical fibres, the base of every log side.
static func _fibres(img: Image, low: Color, high: Color, cells_x: int, seed_i: int) -> void:
	var field := _fbm_field(cells_x, 2, 3, seed_i + 131)
	_paint_field(img, field, low, high)


## Soft radial darkening towards the tile border. Symmetric, so it stays
## tileable: a dark edge always meets another dark edge.
static func _vignette(img: Image, strength: float) -> void:
	var centre := float(S - 1) * 0.5
	var max_d := sqrt(2.0) * centre
	for y in S:
		for x in S:
			var dx := float(x) - centre
			var dy := float(y) - centre
			var t := clampf(sqrt(dx * dx + dy * dy) / max_d, 0.0, 1.0)
			var c := img.get_pixel(x, y)
			if c.a <= 0.001:
				continue
			var k := 1.0 - strength * t * t
			img.set_pixel(x, y, Color(c.r * k, c.g * k, c.b * k, c.a))


## Stamps a small sprite. Each row is a string, "." leaves the pixel untouched,
## any other character is looked up in `palette`.
static func _stamp(img: Image, ox: int, oy: int, rows: PackedStringArray, palette: Dictionary) -> void:
	for r in rows.size():
		var line: String = rows[r]
		for c in line.length():
			var ch := line[c]
			if not palette.has(ch):
				continue
			var col: Color = palette[ch]
			_blend_px(img, ox + c, oy + r, col)


## Pushes the colour of opaque pixels into their transparent neighbours while
## keeping alpha at zero, so mipmap averaging never mixes in black.
static func _bleed_alpha(img: Image) -> void:
	var filled := PackedByteArray()
	filled.resize(S * S)
	for y in S:
		for x in S:
			filled[y * S + x] = 1 if img.get_pixel(x, y).a > 0.02 else 0
	for _pass in 3:
		var next := filled.duplicate()
		var changed := false
		for y in S:
			for x in S:
				if filled[y * S + x] == 1:
					continue
				var sr := 0.0
				var sg := 0.0
				var sb := 0.0
				var n := 0
				for dy in range(-1, 2):
					for dx in range(-1, 2):
						if dx == 0 and dy == 0:
							continue
						var nx := posmod(x + dx, S)
						var ny := posmod(y + dy, S)
						if filled[ny * S + nx] == 0:
							continue
						var s := img.get_pixel(nx, ny)
						sr += s.r
						sg += s.g
						sb += s.b
						n += 1
				if n == 0:
					continue
				var inv := 1.0 / float(n)
				img.set_pixel(x, y, Color(sr * inv, sg * inv, sb * inv, 0.0))
				next[y * S + x] = 1
				changed = true
		filled = next
		if not changed:
			return


# ---------------------------------------------------------------------------
# Tile dispatch
# ---------------------------------------------------------------------------

static func _draw_tile(tile_name: String, img: Image) -> void:
	var seed_i := _seed_of(tile_name)
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_i
	match tile_name:
		"stone":
			_t_stone(img, rng, seed_i)
		"grass_top":
			_t_grass_top(img, rng, seed_i)
		"grass_side":
			_t_grass_side(img, rng, seed_i)
		"dirt":
			_t_dirt(img, rng, seed_i)
		"cobblestone":
			_t_cobblestone(img, rng, seed_i)
		"stone_brick":
			_t_stone_brick(img, seed_i)
		"granite":
			_t_granite(img, rng, seed_i)
		"marble":
			_t_marble(img, rng, seed_i)
		"mossy_cobble":
			_t_mossy_cobble(img, rng, seed_i)
		"sand":
			_t_sand(img, rng, seed_i)
		"sandstone_top":
			_t_sandstone_top(img, rng, seed_i)
		"sandstone_side":
			_t_sandstone_side(img, rng, seed_i)
		"gravel":
			_t_gravel(img, rng, seed_i)
		"clay":
			_t_clay(img, rng, seed_i)
		"snow":
			_t_snow(img, rng, seed_i)
		"snow_side":
			_t_snow_side(img, rng, seed_i)
		"ice":
			_t_ice(img, rng, seed_i)
		"obsidian":
			_t_obsidian(img, rng, seed_i)
		"bedrock":
			_t_bedrock(img, rng, seed_i)
		"coal_ore":
			_t_ore(img, rng, seed_i, Color(0.09, 0.09, 0.10), Color(0.22, 0.22, 0.24))
		"iron_ore":
			_t_ore(img, rng, seed_i, Color(0.85, 0.68, 0.50), Color(0.60, 0.42, 0.30))
		"gold_ore":
			_t_ore(img, rng, seed_i, Color(0.99, 0.85, 0.30), Color(0.72, 0.55, 0.14))
		"diamond_ore":
			_t_ore(img, rng, seed_i, Color(0.66, 0.95, 0.97), Color(0.30, 0.66, 0.78))
		"oak_log_side":
			_t_oak_log_side(img, rng, seed_i)
		"oak_log_top":
			_t_log_top(img, seed_i, Color(0.29, 0.20, 0.11), Color(0.40, 0.28, 0.16), Color(0.55, 0.40, 0.23), Color(0.72, 0.56, 0.34))
		"oak_planks":
			_t_plank_tile(img, rng, seed_i, Color(0.52, 0.37, 0.21), Color(0.69, 0.52, 0.31), Color(0.33, 0.22, 0.12))
		"oak_leaves":
			_t_leaves_grey(img, rng, seed_i, 0.70, 1.00, 0.385, 6)
		"birch_log_side":
			_t_birch_log_side(img, rng, seed_i)
		"birch_log_top":
			_t_log_top(img, seed_i, Color(0.80, 0.79, 0.74), Color(0.93, 0.92, 0.88), Color(0.78, 0.70, 0.53), Color(0.90, 0.84, 0.68))
		"birch_planks":
			_t_plank_tile(img, rng, seed_i, Color(0.76, 0.68, 0.51), Color(0.90, 0.84, 0.67), Color(0.56, 0.47, 0.33))
		"birch_leaves":
			_t_leaves_grey(img, rng, seed_i, 0.76, 1.00, 0.400, 9)
		"pine_leaves":
			_t_pine_leaves(img, rng, seed_i)
		"bookshelf":
			_t_bookshelf(img, rng, seed_i)
		"cactus_side":
			_t_cactus_side(img, rng, seed_i)
		"cactus_top":
			_t_cactus_top(img, rng, seed_i)
		"pumpkin_side":
			_t_pumpkin_side(img, rng, seed_i)
		"pumpkin_top":
			_t_pumpkin_top(img, rng, seed_i)
		"brick":
			_t_brick(img, seed_i)
		"glass":
			_t_glass(img, seed_i)
		"lamp":
			_t_lamp(img, rng, seed_i)
		"wool_white":
			_t_wool(img, rng, seed_i, Color(0.91, 0.92, 0.94))
		"wool_red":
			_t_wool(img, rng, seed_i, Color(0.71, 0.19, 0.17))
		"wool_yellow":
			_t_wool(img, rng, seed_i, Color(0.90, 0.77, 0.21))
		"wool_green":
			_t_wool(img, rng, seed_i, Color(0.30, 0.60, 0.25))
		"wool_blue":
			_t_wool(img, rng, seed_i, Color(0.22, 0.36, 0.72))
		"water":
			_t_water(img, rng, seed_i)
		"grass_tuft":
			_t_grass_tuft(img, rng, seed_i)
		"fern":
			_t_fern(img, seed_i)
		"dead_bush":
			_t_dead_bush(img, rng)
		"flower_red":
			_t_flower_red(img, seed_i)
		"flower_yellow":
			_t_flower_yellow(img, seed_i)
		"sapling":
			_t_sapling(img, rng, seed_i)
		"torch":
			_t_torch(img, seed_i)
		_:
			push_warning("VoxelAtlas: unknown tile '%s', painting the fallback" % tile_name)
			_t_missing(img)


static func _t_missing(img: Image) -> void:
	for y in S:
		for x in S:
			var checker := ((x / 4) + (y / 4)) % 2 == 0
			img.set_pixel(x, y, Color(0.90, 0.0, 0.85) if checker else Color(0.10, 0.0, 0.12))


# ---------------------------------------------------------------------------
# Rock family
# ---------------------------------------------------------------------------

static func _t_stone(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(8, 8, 3, seed_i), Color(0.40, 0.40, 0.43), Color(0.60, 0.60, 0.63))
	_grain(img, _noise_field(S, S, seed_i + 17), 0.10)
	_speckle(img, rng, 12, Color(0.28, 0.28, 0.31), Color(0.35, 0.35, 0.38), 1)
	_speckle(img, rng, 10, Color(0.66, 0.66, 0.69), Color(0.72, 0.72, 0.74), 0)


static func _t_cobblestone(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_stones(img, rng, 13, Color(0.42, 0.42, 0.45), Color(0.68, 0.68, 0.70), Color(0.24, 0.24, 0.27), 1.15, 3.0)
	_grain(img, _fbm_field(16, 16, 2, seed_i + 5), 0.14)
	_speckle(img, rng, 8, Color(0.32, 0.32, 0.35), Color(0.38, 0.38, 0.41), 0)


static func _t_stone_brick(img: Image, seed_i: int) -> void:
	# Stacked bond plus a dark joint, clearly different from the red brick.
	_brick_courses(img, 4, 2, Color(0.30, 0.30, 0.33), Color(0.48, 0.48, 0.52), Color(0.62, 0.62, 0.65), 1, false, seed_i)
	_grain(img, _noise_field(S, S, seed_i + 23), 0.09)


static func _t_granite(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(6, 6, 3, seed_i), Color(0.50, 0.34, 0.30), Color(0.70, 0.52, 0.46))
	_speckle(img, rng, 34, Color(0.86, 0.82, 0.79), Color(0.94, 0.90, 0.86), 0)
	_speckle(img, rng, 30, Color(0.16, 0.12, 0.12), Color(0.26, 0.20, 0.19), 0)
	_speckle(img, rng, 8, Color(0.62, 0.30, 0.26), Color(0.74, 0.40, 0.34), 1)
	_grain(img, _noise_field(S, S, seed_i + 41), 0.10)


static func _t_marble(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(4, 4, 3, seed_i), Color(0.84, 0.84, 0.87), Color(0.97, 0.97, 0.98))
	_veins(img, _fbm_field(3, 3, 3, seed_i + 91), 0.055, Color(0.58, 0.59, 0.66), 0.85)
	_veins(img, _fbm_field(5, 5, 3, seed_i + 173), 0.028, Color(0.68, 0.69, 0.75), 0.55)
	_speckle(img, rng, 10, Color(0.76, 0.76, 0.80), Color(0.82, 0.82, 0.86), 0)


## Draws the zero crossing of a field as a soft wandering vein.
static func _veins(img: Image, field: PackedFloat32Array, width: float, col: Color, strength: float) -> void:
	for y in S:
		var base := y * S
		for x in S:
			var d := absf(field[base + x] - 0.5)
			if d >= width:
				continue
			var k := (1.0 - d / width) * strength
			_blend_px(img, x, y, Color(col.r, col.g, col.b, k))


static func _t_mossy_cobble(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_t_cobblestone(img, rng, seed_i)
	var moss := _fbm_field(5, 5, 3, seed_i + 211)
	for y in S:
		var base := y * S
		for x in S:
			var m := moss[base + x]
			if m <= 0.52:
				continue
			var k := clampf((m - 0.52) * 3.4, 0.0, 0.95)
			var shade := _lattice(x, y, seed_i + 7)
			var green := Color(0.20, 0.38, 0.16).lerp(Color(0.34, 0.55, 0.22), shade)
			_blend_px(img, x, y, Color(green.r, green.g, green.b, k))
	_speckle(img, rng, 14, Color(0.26, 0.46, 0.20), Color(0.38, 0.60, 0.26), 0)


static func _t_gravel(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_stones(img, rng, 26, Color(0.34, 0.33, 0.32), Color(0.64, 0.63, 0.61), Color(0.26, 0.25, 0.24), 0.55, 1.8)
	_grain(img, _noise_field(S, S, seed_i + 3), 0.22)
	_speckle(img, rng, 16, Color(0.44, 0.37, 0.29), Color(0.54, 0.46, 0.36), 1)
	_speckle(img, rng, 10, Color(0.22, 0.21, 0.21), Color(0.28, 0.27, 0.26), 0)


static func _t_clay(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(4, 4, 3, seed_i), Color(0.54, 0.57, 0.66), Color(0.79, 0.81, 0.86))
	# Shrinkage cracks, the trait that tells clay apart from smooth stone.
	_veins(img, _fbm_field(4, 4, 2, seed_i + 219), 0.035, Color(0.44, 0.47, 0.56), 0.7)
	_grain(img, _noise_field(S, S, seed_i + 13), 0.10)
	_speckle(img, rng, 16, Color(0.48, 0.51, 0.60), Color(0.58, 0.61, 0.69), 1)
	_speckle(img, rng, 10, Color(0.84, 0.86, 0.90), Color(0.88, 0.90, 0.93), 0)


static func _t_obsidian(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(8, 8, 3, seed_i), Color(0.05, 0.04, 0.09), Color(0.16, 0.12, 0.23))
	_veins(img, _fbm_field(4, 4, 3, seed_i + 77), 0.05, Color(0.34, 0.22, 0.48), 0.75)
	_speckle(img, rng, 18, Color(0.28, 0.18, 0.40), Color(0.42, 0.30, 0.56), 0)
	_speckle(img, rng, 6, Color(0.50, 0.40, 0.66), Color(0.58, 0.48, 0.74), 0)
	_grain(img, _noise_field(S, S, seed_i + 5), 0.16)


static func _t_bedrock(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_stones(img, rng, 17, Color(0.17, 0.17, 0.19), Color(0.54, 0.54, 0.57), Color(0.12, 0.12, 0.13), 0.0, 1.4)
	_grain(img, _fbm_field(16, 16, 2, seed_i + 9), 0.40)
	_speckle(img, rng, 14, Color(0.08, 0.08, 0.09), Color(0.14, 0.14, 0.15), 2)
	_speckle(img, rng, 10, Color(0.56, 0.56, 0.59), Color(0.64, 0.64, 0.66), 0)


static func _t_ore(img: Image, rng: RandomNumberGenerator, seed_i: int, core: Color, edge: Color) -> void:
	_t_stone(img, rng, seed_i)
	for _i in 6:
		var cx := rng.randi_range(0, S - 1)
		var cy := rng.randi_range(0, S - 1)
		var r := rng.randi_range(2, 3)
		_disc(img, cx, cy, r, edge)
		_disc(img, cx, cy, r - 1, core)
		_disc(img, cx - 1, cy - 1, 0, core.lightened(0.20))
		for _k in rng.randi_range(1, 3):
			var ox := rng.randi_range(-r - 1, r + 1)
			var oy := rng.randi_range(-r - 1, r + 1)
			_disc(img, cx + ox, cy + oy, 0, core.lerp(edge, 0.5))


# ---------------------------------------------------------------------------
# Soil family
# ---------------------------------------------------------------------------

static func _t_dirt(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(8, 8, 3, seed_i), Color(0.33, 0.24, 0.16), Color(0.52, 0.38, 0.25))
	_grain(img, _noise_field(S, S, seed_i + 19), 0.16)
	_speckle(img, rng, 22, Color(0.25, 0.18, 0.11), Color(0.31, 0.23, 0.15), 1)
	_speckle(img, rng, 12, Color(0.45, 0.40, 0.34), Color(0.55, 0.50, 0.43), 0)


static func _t_grass_top(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	# Near white greyscale: the vertex colour carries the biome tint.
	var clumps := _fbm_field(6, 6, 3, seed_i)
	var fine := _fbm_field(16, 16, 2, seed_i + 31)
	for y in S:
		var base := y * S
		for x in S:
			var g := 0.68 + 0.30 * clumps[base + x] + 0.07 * (fine[base + x] - 0.5) * 2.0
			g = clampf(g, 0.66, 1.0)
			img.set_pixel(x, y, Color(g, g, g, 1.0))
	# Short blade marks so the top face does not read as flat noise.
	for _i in 26:
		var bx := rng.randi_range(0, S - 1)
		var by := rng.randi_range(0, S - 1)
		var g := rng.randf_range(0.67, 0.74)
		var h := rng.randi_range(1, 3)
		for k in h:
			_px(img, bx, by + k, Color(g, g, g, 1.0))
	_speckle(img, rng, 18, Color(0.98, 0.98, 0.98), Color(1.0, 1.0, 1.0), 0)
	_clamp_grey(img, 0.66)


static func _t_grass_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_t_dirt(img, rng, seed_i + 501)
	# The fringe is painted in a plausible green because Blocks only tints the
	# top face of grass, never the sides.
	_fringe(img, seed_i, 10, 5,
		Color(0.26, 0.48, 0.20), Color(0.44, 0.72, 0.32),
		Color(0.18, 0.34, 0.14), rng)


static func _t_snow_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_t_dirt(img, rng, seed_i + 733)
	_fringe(img, seed_i, 11, 4,
		Color(0.83, 0.86, 0.93), Color(1.0, 1.0, 1.0),
		Color(0.68, 0.73, 0.85), rng)


## Paints a cover layer over the top of the tile with an irregular lower edge
## that spills a few strands further down, the classic grass side look. Row 0 is
## the top of the face, so the cover occupies the small y values.
static func _fringe(img: Image, seed_i: int, mean_height: int, amplitude: int, low: Color, high: Color, shade: Color, rng: RandomNumberGenerator) -> void:
	var profile := _fbm_field(6, 1, 2, seed_i + 401)
	var detail := _fbm_field(16, 16, 2, seed_i + 409)
	var heights := PackedInt32Array()
	heights.resize(S)
	for x in S:
		var h := mean_height + int(round((profile[x] - 0.5) * 2.0 * float(amplitude)))
		heights[x] = clampi(h, 3, S / 2)
	for x in S:
		var h: int = heights[x]
		for y in h:
			var t := clampf(float(y) / float(maxi(h - 1, 1)), 0.0, 1.0)
			var c := high.lerp(low, t * 0.85 + 0.15 * detail[y * S + x])
			img.set_pixel(x, y, Color(c.r, c.g, c.b, 1.0))
		# Shaded lip right under the cover, then a couple of dangling strands.
		img.set_pixel(x, h, shade.lerp(low, detail[h * S + x]))
		var extra := int(round(_lattice(x, 3, seed_i + 417) * 2.6))
		for k in extra:
			var y2 := h + 1 + k
			if y2 >= S:
				break
			var c2 := low.lerp(shade, float(k) / 3.0)
			img.set_pixel(x, y2, Color(c2.r, c2.g, c2.b, 1.0))
	# A few isolated strands hanging lower, breaks the horizontal rhythm.
	for _i in 7:
		var x := rng.randi_range(0, S - 1)
		var h: int = heights[x] + 2
		var strand := rng.randi_range(2, 4)
		for k in strand:
			var y := h + k
			if y >= S:
				break
			_px(img, x, y, low.lerp(shade, float(k) / float(strand)))


static func _t_sand(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(16, 16, 2, seed_i), Color(0.83, 0.75, 0.51), Color(0.95, 0.89, 0.67))
	_grain(img, _noise_field(S, S, seed_i + 29), 0.10)
	_speckle(img, rng, 54, Color(0.74, 0.65, 0.42), Color(0.80, 0.72, 0.49), 0)
	_speckle(img, rng, 26, Color(0.97, 0.93, 0.76), Color(1.0, 0.98, 0.84), 0)


static func _t_sandstone_top(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(6, 6, 3, seed_i), Color(0.78, 0.69, 0.46), Color(0.91, 0.84, 0.62))
	_grain(img, _noise_field(S, S, seed_i + 37), 0.07)
	_speckle(img, rng, 20, Color(0.70, 0.61, 0.39), Color(0.76, 0.67, 0.44), 1)
	_speckle(img, rng, 12, Color(0.94, 0.89, 0.72), Color(0.98, 0.94, 0.79), 0)


static func _t_sandstone_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	# Horizontal strata: the field only varies along Y.
	var bands := _fbm_field(1, 8, 3, seed_i)
	var grain := _fbm_field(16, 16, 2, seed_i + 43)
	for y in S:
		var base := y * S
		for x in S:
			var c := Color(0.76, 0.67, 0.44).lerp(Color(0.92, 0.85, 0.63), bands[base + x])
			var f := 1.0 + (grain[base + x] - 0.5) * 0.10
			img.set_pixel(x, y, Color(clampf(c.r * f, 0.0, 1.0), clampf(c.g * f, 0.0, 1.0), clampf(c.b * f, 0.0, 1.0), 1.0))
	# Bedding planes every 8 pixels, which divides 32 so the tile still wraps.
	for y in range(0, S, 8):
		for x in S:
			var c := img.get_pixel(x, y)
			img.set_pixel(x, y, c.darkened(0.22))
	_speckle(img, rng, 18, Color(0.70, 0.61, 0.39), Color(0.78, 0.70, 0.47), 0)


static func _t_snow(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(8, 8, 3, seed_i), Color(0.86, 0.89, 0.95), Color(1.0, 1.0, 1.0))
	_grain(img, _noise_field(S, S, seed_i + 47), 0.05)
	_speckle(img, rng, 22, Color(1.0, 1.0, 1.0), Color(1.0, 1.0, 1.0), 0)
	_speckle(img, rng, 14, Color(0.80, 0.85, 0.94), Color(0.86, 0.90, 0.96), 1)


static func _t_ice(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(4, 4, 3, seed_i), Color(0.58, 0.75, 0.90), Color(0.80, 0.91, 0.98))
	_veins(img, _fbm_field(3, 3, 2, seed_i + 61), 0.05, Color(0.93, 0.98, 1.0), 0.9)
	# Straight fractures, wrapped so both ends meet on the opposite edge.
	for _i in 3:
		var x0 := rng.randi_range(0, S - 1)
		var y0 := rng.randi_range(0, S - 1)
		var dx := rng.randi_range(-14, 14)
		var dy := rng.randi_range(-14, 14)
		_line(img, x0, y0, x0 + dx, y0 + dy, Color(0.95, 0.99, 1.0, 0.8))
	_grain(img, _noise_field(S, S, seed_i + 71), 0.06)
	_speckle(img, rng, 10, Color(0.52, 0.70, 0.87), Color(0.60, 0.77, 0.92), 1)


static func _t_water(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(6, 6, 3, seed_i), Color(0.08, 0.30, 0.60), Color(0.19, 0.50, 0.80))
	# Ripple streaks running along X.
	var ripple := _fbm_field(3, 14, 2, seed_i + 83)
	for y in S:
		var base := y * S
		for x in S:
			var r := ripple[base + x]
			if r <= 0.62:
				continue
			var k := clampf((r - 0.62) * 2.2, 0.0, 0.55)
			_blend_px(img, x, y, Color(0.62, 0.86, 0.98, k))
	_speckle(img, rng, 12, Color(0.72, 0.92, 1.0), Color(0.80, 0.96, 1.0), 0)
	_grain(img, _noise_field(S, S, seed_i + 89), 0.08)


# ---------------------------------------------------------------------------
# Wood family
# ---------------------------------------------------------------------------

static func _t_oak_log_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_fibres(img, Color(0.34, 0.24, 0.13), Color(0.56, 0.41, 0.24), 12, seed_i)
	# Deep bark furrows: full height lines, so the tile keeps tiling vertically.
	for _i in 5:
		var x := rng.randi_range(0, S - 1)
		var dark := rng.randf_range(0.20, 0.32)
		for y in S:
			var c := img.get_pixel(posmod(x, S), y)
			_px(img, x, y, c.darkened(dark))
			if rng.randf() < 0.35:
				_px(img, x + 1, y, c.darkened(dark * 0.5))
	# A knot, drawn as a small closed ring.
	var kx := rng.randi_range(0, S - 1)
	var ky := rng.randi_range(0, S - 1)
	_disc(img, kx, ky, 3, Color(0.30, 0.21, 0.11))
	_disc(img, kx, ky, 2, Color(0.44, 0.32, 0.18))
	_disc(img, kx, ky, 1, Color(0.26, 0.18, 0.09))
	_grain(img, _noise_field(S, S, seed_i + 97), 0.12)


static func _t_birch_log_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_fibres(img, Color(0.82, 0.81, 0.76), Color(0.96, 0.95, 0.91), 16, seed_i)
	# The signature dark dashes of birch bark.
	for _i in 9:
		var x := rng.randi_range(0, S - 1)
		var y := rng.randi_range(0, S - 1)
		var w := rng.randi_range(3, 8)
		var h := rng.randi_range(1, 2)
		var col := Color(0.20, 0.19, 0.18).lerp(Color(0.36, 0.34, 0.31), rng.randf())
		for dy in h:
			for dx in w:
				_px(img, x + dx, y + dy, col)
		_px(img, x - 1, y, col.lightened(0.25))
		_px(img, x + w, y, col.lightened(0.25))
	_speckle(img, rng, 16, Color(0.70, 0.68, 0.63), Color(0.78, 0.76, 0.71), 0)
	_grain(img, _noise_field(S, S, seed_i + 101), 0.08)


static func _t_log_top(img: Image, seed_i: int, bark_low: Color, bark_high: Color, ring_low: Color, ring_high: Color) -> void:
	var centre := float(S - 1) * 0.5
	var wobble := _fbm_field(6, 6, 2, seed_i + 107)
	var grain := _noise_field(S, S, seed_i + 109)
	for y in S:
		var base := y * S
		for x in S:
			var dx := float(x) - centre
			var dy := float(y) - centre
			var d := sqrt(dx * dx + dy * dy) + (wobble[base + x] - 0.5) * 2.4
			var c: Color
			if d > 12.5:
				# Uniform bark border keeps opposite edges identical.
				c = bark_low.lerp(bark_high, grain[base + x])
			else:
				var ring := 0.5 + 0.5 * sin(d * 1.9)
				c = ring_low.lerp(ring_high, ring)
				if d < 1.6:
					c = ring_low.darkened(0.25)
			var f := 1.0 + (grain[base + x] - 0.5) * 0.10
			img.set_pixel(x, y, Color(clampf(c.r * f, 0.0, 1.0), clampf(c.g * f, 0.0, 1.0), clampf(c.b * f, 0.0, 1.0), 1.0))


static func _t_plank_tile(img: Image, rng: RandomNumberGenerator, seed_i: int, low: Color, high: Color, seam: Color) -> void:
	_plank_courses(img, rng, 4, low, high, seam, seed_i)
	_speckle(img, rng, 10, seam.lightened(0.15), low.darkened(0.10), 0)
	_grain(img, _noise_field(S, S, seed_i + 113), 0.07)


static func _t_bookshelf(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_plank_courses(img, rng, 4, Color(0.48, 0.34, 0.19), Color(0.62, 0.46, 0.27), Color(0.30, 0.20, 0.11), seed_i)
	var gap := Color(0.16, 0.11, 0.07)
	var spines: Array[Color] = [
		Color(0.64, 0.18, 0.16),
		Color(0.20, 0.34, 0.64),
		Color(0.24, 0.50, 0.26),
		Color(0.58, 0.44, 0.14),
		Color(0.42, 0.22, 0.50),
		Color(0.16, 0.46, 0.48),
	]
	# Two shelves of books, wood bands top, middle and bottom.
	var bands: Array[Vector2i] = [Vector2i(4, 14), Vector2i(18, 28)]
	for band in bands:
		var y0: int = band.x
		var y1: int = band.y
		for y in range(y0, y1 + 1):
			for x in S:
				img.set_pixel(x, y, gap)
		var cursor := 1
		while cursor <= S - 4:
			var w := rng.randi_range(2, 4)
			if cursor + w > S - 2:
				break
			var col: Color = spines[rng.randi_range(0, spines.size() - 1)]
			var top := y0 + rng.randi_range(0, 2)
			for x in range(cursor, cursor + w):
				for y in range(top, y1 + 1):
					var shade := col.darkened(0.20) if x == cursor + w - 1 else col
					if y == top:
						shade = col.lightened(0.25)
					img.set_pixel(x, y, shade)
			cursor += w + 1
	_grain(img, _noise_field(S, S, seed_i + 127), 0.10)
	_vignette(img, 0.12)


# ---------------------------------------------------------------------------
# Foliage and plants
# ---------------------------------------------------------------------------

## Leafy cutout painted in near-white greyscale so the biome tint applies.
static func _t_leaves_grey(img: Image, rng: RandomNumberGenerator, seed_i: int, lo: float, hi: float, hole: float, cells: int) -> void:
	_t_foliage(img, seed_i, Color(lo, lo, lo), Color(hi, hi, hi), hole, cells, cells)
	# Bright highlights on a few leaves, still pure grey.
	for _i in 14:
		var x := rng.randi_range(0, S - 1)
		var y := rng.randi_range(0, S - 1)
		if img.get_pixel(x, y).a < 0.5:
			continue
		img.set_pixel(x, y, Color(hi, hi, hi, 1.0))
	_clamp_grey(img, 0.66)


## Forces every visible pixel back into the near-white greyscale window the
## contract demands for biome tinted tiles, whatever the shading did before.
static func _clamp_grey(img: Image, floor_grey: float) -> void:
	for y in S:
		for x in S:
			var c := img.get_pixel(x, y)
			if c.a <= 0.001:
				continue
			var g := clampf(maxf(maxf(c.r, c.g), c.b), floor_grey, 1.0)
			img.set_pixel(x, y, Color(g, g, g, c.a))


static func _t_pine_leaves(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	# Not biome tinted, so it carries its own dark needle green.
	_t_foliage(img, seed_i, Color(0.08, 0.26, 0.14), Color(0.22, 0.48, 0.25), 0.40, 18, 7)
	for _i in 18:
		var x := rng.randi_range(0, S - 1)
		var y := rng.randi_range(0, S - 1)
		if img.get_pixel(x, y).a < 0.5:
			continue
		img.set_pixel(x, y, Color(0.30, 0.56, 0.30, 1.0))


## Blobby cutout foliage: a mask field carves the holes, a second field shades.
static func _t_foliage(img: Image, seed_i: int, low: Color, high: Color, hole: float, px: int, py: int) -> void:
	var mask := _fbm_field(px, py, 3, seed_i + 11)
	var tone := _fbm_field(16, 16, 2, seed_i + 29)
	for y in S:
		var base := y * S
		for x in S:
			var m := mask[base + x]
			if m < hole:
				continue
			var t := clampf(tone[base + x] * 0.65 + (m - hole) * 1.5, 0.0, 1.0)
			var c := low.lerp(high, t)
			img.set_pixel(x, y, Color(c.r, c.g, c.b, 1.0))
	# Darken the rim of every hole so leaf clusters read as separate leaves.
	for y in S:
		for x in S:
			if img.get_pixel(x, y).a < 0.5:
				continue
			var open := false
			if img.get_pixel(posmod(x + 1, S), y).a < 0.5:
				open = true
			elif img.get_pixel(posmod(x - 1, S), y).a < 0.5:
				open = true
			elif img.get_pixel(x, posmod(y + 1, S)).a < 0.5:
				open = true
			elif img.get_pixel(x, posmod(y - 1, S)).a < 0.5:
				open = true
			if not open:
				continue
			var c := img.get_pixel(x, y)
			img.set_pixel(x, y, Color(c.r * 0.84, c.g * 0.84, c.b * 0.84, 1.0))


## One curved blade rising from the bottom row of the tile.
static func _blade(img: Image, x0: int, top_y: int, lean: float, base_grey: float, tip_grey: float, thick: bool) -> void:
	var h := maxi(S - 1 - top_y, 1)
	for y in range(S - 1, top_y - 1, -1):
		var t := float(S - 1 - y) / float(h)
		var x := x0 + int(round(lean * t * t * float(h) * 0.30))
		var g := lerpf(base_grey, tip_grey, t)
		_px(img, x, y, Color(g, g, g, 1.0))
		if thick and t < 0.40:
			var g2 := maxf(g * 0.94, 0.66)
			_px(img, x + 1, y, Color(g2, g2, g2, 1.0))


static func _t_grass_tuft(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	for i in 9:
		var x0 := 2 + i * 3 + rng.randi_range(0, 1)
		var top := rng.randi_range(6, 18)
		var lean := rng.randf_range(-1.0, 1.0)
		_blade(img, x0, top, lean, 0.70, rng.randf_range(0.90, 1.0), rng.randf() < 0.5)
	# Ground litter so the base of the tuft is not a row of bare stalks.
	for _i in 12:
		var x := rng.randi_range(0, S - 1)
		var y := rng.randi_range(S - 4, S - 1)
		var g := rng.randf_range(0.70, 0.82)
		_px(img, x, y, Color(g, g, g, 1.0))
	_clamp_grey(img, 0.66)
	_unused_seed(seed_i)


static func _t_fern(img: Image, seed_i: int) -> void:
	# Three fronds with paired leaflets, near-white greyscale for the tint.
	_frond(img, 16, S - 1, 5, 0.0, seed_i)
	_frond(img, 9, S - 1, 12, -0.7, seed_i + 17)
	_frond(img, 23, S - 1, 12, 0.7, seed_i + 31)
	_clamp_grey(img, 0.66)


static func _frond(img: Image, base_x: int, base_y: int, top_y: int, lean: float, seed_i: int) -> void:
	var h := maxi(base_y - top_y, 2)
	var stem := 0.72
	var xs := PackedInt32Array()
	xs.resize(h + 1)
	for k in h + 1:
		var t := float(k) / float(h)
		xs[k] = base_x + int(round(lean * t * t * 5.0))
		_px(img, xs[k], base_y - k, Color(stem, stem, stem, 1.0))
	# Leaflets every third row, longest in the middle of the frond. Leaving a
	# clear gap between pairs is what makes a fern read as feathery.
	for k in range(2, h, 3):
		var t := float(k) / float(h)
		var span := int(round(lerpf(2.0, 5.0, sin(t * PI))))
		var g := lerpf(0.78, 1.0, t)
		for s in span:
			var y := base_y - k - int(round(float(s) * 0.75))
			_px(img, xs[k] + 1 + s, y, Color(g, g, g, 1.0))
			var g2 := maxf(g * 0.94, 0.66)
			_px(img, xs[k] - 1 - s, y - (1 if s == span - 1 else 0), Color(g2, g2, g2, 1.0))


static func _t_dead_bush(img: Image, rng: RandomNumberGenerator) -> void:
	var dark := Color(0.34, 0.25, 0.13)
	var mid := Color(0.47, 0.35, 0.18)
	var light := Color(0.58, 0.45, 0.24)
	# A short trunk with bare twigs fanning out.
	for y in range(S - 1, 19, -1):
		_px(img, 16, y, mid)
	for _i in 7:
		var y0 := rng.randi_range(14, 26)
		var x0 := 16
		var x1 := x0 + rng.randi_range(-11, 11)
		var y1 := y0 - rng.randi_range(3, 12)
		_line(img, x0, y0, x1, y1, dark if rng.randf() < 0.5 else mid)
		# One small side twig per branch.
		_line(img, (x0 + x1) / 2, (y0 + y1) / 2, (x0 + x1) / 2 + rng.randi_range(-4, 4), (y0 + y1) / 2 - rng.randi_range(2, 5), light)
	for _i in 10:
		var x := rng.randi_range(4, S - 5)
		var y := rng.randi_range(10, S - 2)
		if img.get_pixel(x, y).a < 0.5:
			continue
		_px(img, x, y, light)


static func _t_flower_red(img: Image, seed_i: int) -> void:
	_flower_stem(img, seed_i)
	var pal := {
		"r": Color(0.58, 0.09, 0.09),
		"R": Color(0.84, 0.16, 0.15),
		"K": Color(0.16, 0.09, 0.07),
	}
	var rows := PackedStringArray([
		"..rrrr..",
		".rRRRRr.",
		"rRRKKRRr",
		"rRRKKRRr",
		".rRRRRr.",
		"..rrrr..",
	])
	_stamp(img, 12, 7, rows, pal)


static func _t_flower_yellow(img: Image, seed_i: int) -> void:
	_flower_stem(img, seed_i + 91)
	var pal := {
		"y": Color(0.72, 0.56, 0.10),
		"Y": Color(0.95, 0.82, 0.18),
		"W": Color(1.0, 0.95, 0.58),
	}
	var rows := PackedStringArray([
		"..yYYy..",
		".yYWWYy.",
		"yYWWWWYy",
		".yYWWYy.",
		"..yyyy..",
	])
	_stamp(img, 12, 9, rows, pal)


static func _flower_stem(img: Image, seed_i: int) -> void:
	var stem := Color(0.20, 0.42, 0.17)
	var stem_light := Color(0.30, 0.56, 0.24)
	for y in range(S - 1, 12, -1):
		var t := float(S - 1 - y) / 20.0
		var x := 15 + int(round(sin(t * 2.2 + _lattice(1, 1, seed_i) * 3.0) * 1.4))
		_px(img, x, y, stem)
		_px(img, x + 1, y, stem_light)
	# Two leaves low on the stem.
	for k in 4:
		_px(img, 15 - 1 - k, 24 - k / 2, stem_light)
		_px(img, 16 + 1 + k, 20 - k / 2, stem)


static func _t_sapling(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	# Fully greyscale: Blocks tints every face of the sapling.
	var trunk := 0.74
	var trunk_dark := 0.67
	for y in range(S - 1, 15, -1):
		_px(img, 15, y, Color(trunk, trunk, trunk, 1.0))
		_px(img, 16, y, Color(trunk_dark, trunk_dark, trunk_dark, 1.0))
	# Two young side shoots, so the seedling is not a lollipop.
	for k in 3:
		_px(img, 14 - k, 22 - k, Color(trunk, trunk, trunk, 1.0))
		_px(img, 17 + k, 26 - k, Color(trunk_dark, trunk_dark, trunk_dark, 1.0))
	var crown := _fbm_field(7, 7, 3, seed_i + 55)
	for y in range(2, 19):
		for x in S:
			var dx := float(x) - 15.5
			var dy := float(y) - 10.0
			var d := sqrt(dx * dx * 1.15 + dy * dy * 1.7)
			if d > 8.5:
				continue
			var m := crown[y * S + x] + (8.5 - d) * 0.05
			if m < 0.52:
				continue
			var g := clampf(0.76 + 0.22 * crown[y * S + x], 0.68, 1.0)
			img.set_pixel(x, y, Color(g, g, g, 1.0))
	for _i in 10:
		var x := rng.randi_range(8, 23)
		var y := rng.randi_range(3, 18)
		if img.get_pixel(x, y).a < 0.5:
			continue
		img.set_pixel(x, y, Color(1.0, 1.0, 1.0, 1.0))
	_clamp_grey(img, 0.66)


static func _t_torch(img: Image, seed_i: int) -> void:
	var stick_light := Color(0.55, 0.40, 0.22)
	var stick := Color(0.40, 0.28, 0.15)
	var stick_dark := Color(0.28, 0.19, 0.10)
	for y in range(15, S):
		var jitter := 1.0 + (_lattice(y, 2, seed_i) - 0.5) * 0.12
		_px(img, 14, y, Color(stick_dark.r * jitter, stick_dark.g * jitter, stick_dark.b * jitter, 1.0))
		_px(img, 15, y, Color(stick_light.r * jitter, stick_light.g * jitter, stick_light.b * jitter, 1.0))
		_px(img, 16, y, Color(stick.r * jitter, stick.g * jitter, stick.b * jitter, 1.0))
		_px(img, 17, y, Color(stick_dark.r * jitter, stick_dark.g * jitter, stick_dark.b * jitter, 1.0))
	var pal := {
		"o": Color(0.94, 0.46, 0.08),
		"f": Color(0.99, 0.70, 0.16),
		"F": Color(1.0, 0.88, 0.36),
		"W": Color(1.0, 0.98, 0.82),
	}
	var rows := PackedStringArray([
		"..oo..",
		".ofFo.",
		".fFWF.",
		"oFWWFo",
		".fFFf.",
		"..oo..",
	])
	_stamp(img, 13, 9, rows, pal)


# ---------------------------------------------------------------------------
# Crops, decoration and manufactured blocks
# ---------------------------------------------------------------------------

static func _t_cactus_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(4, 10, 3, seed_i), Color(0.14, 0.38, 0.18), Color(0.29, 0.57, 0.29))
	# Ribs every 8 pixels, a divisor of 32, so the tile wraps.
	for x in range(0, S, 8):
		for y in S:
			var c := img.get_pixel(x, y)
			img.set_pixel(x, y, c.darkened(0.34))
			var c2 := img.get_pixel(posmod(x + 1, S), y)
			img.set_pixel(posmod(x + 1, S), y, c2.lightened(0.14))
	# Spines sitting on the ribs.
	var spine := Color(0.93, 0.94, 0.82)
	for x in range(4, S, 8):
		for y in range(2, S, 5):
			var oy := y + int(round(_lattice(x, y, seed_i) * 2.0))
			_px(img, x, oy, spine)
			_px(img, x, oy + 1, spine.darkened(0.30))
	_grain(img, _noise_field(S, S, seed_i + 151), 0.10)
	_speckle(img, rng, 10, Color(0.10, 0.30, 0.14), Color(0.16, 0.36, 0.18), 0)


static func _t_cactus_top(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	var centre := float(S - 1) * 0.5
	var noise := _fbm_field(8, 8, 3, seed_i)
	for y in S:
		var base := y * S
		for x in S:
			var dx := float(x) - centre
			var dy := float(y) - centre
			var d := sqrt(dx * dx + dy * dy)
			var c: Color
			if d > 12.0:
				c = Color(0.11, 0.30, 0.14).lerp(Color(0.18, 0.40, 0.20), noise[base + x])
			else:
				c = Color(0.20, 0.48, 0.24).lerp(Color(0.34, 0.63, 0.33), noise[base + x])
				if d < 4.0:
					c = c.darkened(0.18)
			img.set_pixel(x, y, c)
	# Areoles on a ring, plus the crown depression in the middle.
	for i in 8:
		var ang := TAU * float(i) / 8.0
		var x := int(round(centre + cos(ang) * 8.5))
		var y := int(round(centre + sin(ang) * 8.5))
		_px(img, x, y, Color(0.90, 0.92, 0.80))
	_disc(img, 16, 16, 1, Color(0.16, 0.40, 0.20))
	_speckle(img, rng, 12, Color(0.14, 0.34, 0.16), Color(0.20, 0.42, 0.20), 0)


static func _t_pumpkin_side(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(4, 8, 3, seed_i), Color(0.74, 0.41, 0.09), Color(0.92, 0.58, 0.15))
	# Deep grooves every 8 pixels with a lit shoulder to their right.
	for x in range(0, S, 8):
		for y in S:
			var c := img.get_pixel(x, y)
			img.set_pixel(x, y, c.darkened(0.38))
			var cl := img.get_pixel(posmod(x + 1, S), y)
			img.set_pixel(posmod(x + 1, S), y, cl.lightened(0.16))
			var cr := img.get_pixel(posmod(x - 1, S), y)
			img.set_pixel(posmod(x - 1, S), y, cr.darkened(0.14))
	# Dry creases on the rind, kept wrapping so the tile still tiles vertically.
	var crease := _fbm_field(2, 12, 2, seed_i + 251)
	for y in S:
		var base := y * S
		for x in S:
			if absf(crease[base + x] - 0.5) > 0.045:
				continue
			img.set_pixel(x, y, img.get_pixel(x, y).darkened(0.18))
	_grain(img, _noise_field(S, S, seed_i + 157), 0.10)
	_speckle(img, rng, 12, Color(0.62, 0.32, 0.06), Color(0.70, 0.38, 0.09), 0)


static func _t_pumpkin_top(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	var centre := float(S - 1) * 0.5
	var noise := _fbm_field(8, 8, 3, seed_i)
	for y in S:
		var base := y * S
		for x in S:
			var dx := float(x) - centre
			var dy := float(y) - centre
			var d := sqrt(dx * dx + dy * dy)
			var ang := atan2(dy, dx)
			var rib := 0.5 + 0.5 * sin(ang * 8.0)
			var c: Color
			if d > 12.0:
				c = Color(0.62, 0.32, 0.07).lerp(Color(0.76, 0.43, 0.11), noise[base + x])
			else:
				c = Color(0.74, 0.41, 0.09).lerp(Color(0.93, 0.60, 0.16), noise[base + x] * 0.5 + rib * 0.5)
			img.set_pixel(x, y, c)
	# Woody stem in the middle.
	_disc(img, 16, 16, 3, Color(0.40, 0.44, 0.18))
	_disc(img, 16, 16, 2, Color(0.52, 0.56, 0.24))
	_disc(img, 15, 15, 0, Color(0.62, 0.66, 0.32))
	_grain(img, _noise_field(S, S, seed_i + 163), 0.08)
	_speckle(img, rng, 10, Color(0.66, 0.34, 0.08), Color(0.72, 0.40, 0.10), 0)


static func _t_brick(img: Image, seed_i: int) -> void:
	_brick_courses(img, 4, 2, Color(0.79, 0.75, 0.70), Color(0.56, 0.23, 0.17), Color(0.73, 0.34, 0.25), 2, true, seed_i)
	_grain(img, _noise_field(S, S, seed_i + 167), 0.10)


static func _t_glass(img: Image, seed_i: int) -> void:
	# Opaque frame, fully transparent centre.
	var frame := Color(0.80, 0.90, 0.95)
	var inner := Color(0.60, 0.76, 0.85)
	var shade := _noise_field(S, S, seed_i + 179)
	for y in S:
		for x in S:
			var edge := mini(mini(x, S - 1 - x), mini(y, S - 1 - y))
			if edge > 1:
				continue
			var c := frame if edge == 0 else inner
			var f := 1.0 + (shade[y * S + x] - 0.5) * 0.16
			img.set_pixel(x, y, Color(clampf(c.r * f, 0.0, 1.0), clampf(c.g * f, 0.0, 1.0), clampf(c.b * f, 0.0, 1.0), 1.0))
	# Corner braces, still part of the frame.
	for k in 4:
		_px(img, 2 + k, 2, inner.darkened(0.10))
		_px(img, 2, 2 + k, inner.darkened(0.10))
		_px(img, S - 3 - k, S - 3, inner.darkened(0.10))
		_px(img, S - 3, S - 3 - k, inner.darkened(0.10))


static func _t_lamp(img: Image, rng: RandomNumberGenerator, seed_i: int) -> void:
	_paint_field(img, _fbm_field(8, 8, 3, seed_i), Color(0.80, 0.66, 0.30), Color(0.97, 0.90, 0.58))
	# Four by four glowing cells, each with a hot core and a dark rim.
	for cy in 4:
		for cx in 4:
			var ox := cx * 8 + 4
			var oy := cy * 8 + 4
			var jitter_x := int(round((_lattice(cx, cy, seed_i) - 0.5) * 2.0))
			var jitter_y := int(round((_lattice(cy, cx, seed_i + 3) - 0.5) * 2.0))
			_disc(img, ox + jitter_x, oy + jitter_y, 2, Color(1.0, 0.93, 0.62))
			_disc(img, ox + jitter_x, oy + jitter_y, 1, Color(1.0, 0.99, 0.86))
	# Dark metal frame between the cells, on a grid that divides the tile.
	for y in S:
		for x in S:
			if x % 8 != 0 and y % 8 != 0:
				continue
			img.set_pixel(x, y, img.get_pixel(x, y).darkened(0.34))
	_grain(img, _noise_field(S, S, seed_i + 181), 0.10)
	_speckle(img, rng, 10, Color(1.0, 0.98, 0.88), Color(1.0, 1.0, 0.94), 0)
	_vignette(img, 0.10)


static func _t_wool(img: Image, rng: RandomNumberGenerator, seed_i: int, base: Color) -> void:
	_paint_field(img, _fbm_field(12, 12, 3, seed_i), base.darkened(0.20), base.lightened(0.16))
	# Cross hatched fibres: one field stretched along X, one along Y. The two
	# together give the knitted look that keeps wool from reading as a flat area.
	var warp := _fbm_field(16, 4, 2, seed_i + 191)
	var weft := _fbm_field(4, 16, 2, seed_i + 197)
	for y in S:
		var row := y * S
		for x in S:
			var c := img.get_pixel(x, y)
			var f := 1.0 + (warp[row + x] - 0.5) * 0.26 + (weft[row + x] - 0.5) * 0.26
			img.set_pixel(x, y, Color(clampf(c.r * f, 0.0, 1.0), clampf(c.g * f, 0.0, 1.0), clampf(c.b * f, 0.0, 1.0), 1.0))
	# Loop shadows on a four pixel knit, a divisor of the tile so it wraps.
	for y in range(3, S, 4):
		for x in range(0, S, 4):
			var ox := x + (2 if (y / 4) % 2 == 1 else 0)
			_blend_px(img, ox, y, Color(0.0, 0.0, 0.0, 0.14))
			_blend_px(img, ox + 1, y - 1, Color(1.0, 1.0, 1.0, 0.10))
	_speckle(img, rng, 24, base.lightened(0.30), base.lightened(0.38), 0)
	_speckle(img, rng, 20, base.darkened(0.30), base.darkened(0.20), 0)


## Keeps a seed argument meaningful for tiles whose pattern comes from the rng
## alone, without leaving an unused parameter warning.
static func _unused_seed(seed_i: int) -> void:
	if seed_i == 0:
		push_warning("VoxelAtlas: tile seed collapsed to zero")
