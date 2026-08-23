class_name TerrainGen
extends RefCounted
## Procedural world generator for CUBEFORGE.
##
## Threading contract: one instance lives per worker thread. Everything an
## instance owns is built inside _init and never mutated afterwards, so two
## threads generating two chunks at the same time cannot interfere. In
## particular there is no scratch RandomNumberGenerator field: every
## per-position random value comes from a pure integer hash of
## (coordinates, salt, seed), which also guarantees that neighbouring chunks
## agree on the features that straddle their border.
##
## generate() writes only into the ChunkData it receives.

enum Biome { OCEAN, BEACH, PLAINS, FOREST, TAIGA, DESERT, SAVANNA, MOUNTAINS, TUNDRA, SWAMP }

const BIOME_NAMES: PackedStringArray = [
	"Océan", "Plage", "Plaines", "Forêt", "Taïga",
	"Désert", "Savane", "Montagnes", "Toundra", "Marais",
]

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

## Control points of the continental spline: noise value -> base height.
const _CONT_X: PackedFloat32Array = [-1.0, -0.70, -0.45, -0.22, -0.05, 0.10, 0.35, 0.60, 0.85, 1.0]
const _CONT_Y: PackedFloat32Array = [26.0, 29.0, 33.0, 39.0, 45.0, 50.0, 55.0, 61.0, 70.0, 76.0]

## Continentalness gain and bias. The bias keeps land more common than ocean.
const _CONT_GAIN := 1.65
const _CONT_BIAS := 0.15

## Height above which the terrain is compressed so peaks converge near 88.
const _CAP_START := 82.0
const _CAP_SPAN := 10.0

const _MIN_HEIGHT := 6
const _MAX_HEIGHT := 90

## Deposit anchor grid: one candidate vein or pocket per cube of this size.
const _DEP_CELL := 6
## How far outside the chunk an anchor can still reach into it.
const _DEP_REACH := 6

## Tree candidate grid inside a chunk: one candidate per square of this size.
const _TREE_CELL := 4

## One deterministic village candidate per cell. Each accepted site owns two
## houses, paths and an animal pen, with enough margin to cross chunk borders.
const _VILLAGE_CELL := 128
const _VILLAGE_REACH := 22
const _HOUSE_HALF_WIDTH := 4
const _HOUSE_HALF_DEPTH := 3
const _HOUSE_HEIGHT := 7

const HOUSE_TIMBER := 0
const HOUSE_MASON := 1

const _SPECIES_OAK := 0
const _SPECIES_BIRCH := 1
const _SPECIES_PINE := 2

# Hash salts. Any two features must use different ones.
const _S_NOISE := 3
const _S_BEDROCK := 11
const _S_SOIL := 23
const _S_DEPOSIT := 41
const _S_VEIN := 47
const _S_TREE := 67
const _S_LEAF := 89
const _S_PLANT := 103
const _S_PLANT2 := 109
const _S_HOUSE := 127

# 64 bit mixing constants, all odd and all inside the signed 64 bit range.
const _MIX_A := 0x2545F4914F6CDD1D
const _MIX_B := 0x165667B19E3779F9
const _MIX_C := 0x27D4EB2F165667C5
const _KX := 0x3B97A57F2E1D4C9
const _KY := 0x1D8E4E27C47D124F
const _KZ := 0x51633E2D5134C4B
const _KS := 0x64F0C51CCD1B0335

const _DIRS: Array[Vector3i] = [
	Vector3i(1, 0, 0), Vector3i(-1, 0, 0),
	Vector3i(0, 1, 0), Vector3i(0, -1, 0),
	Vector3i(0, 0, 1), Vector3i(0, 0, -1),
]

# ---------------------------------------------------------------------------
# Immutable state
# ---------------------------------------------------------------------------

var _seed: int = 0
var _seed_a: int = 0

var _n_cont: FastNoiseLite
var _n_hills: FastNoiseLite
var _n_relief: FastNoiseLite
var _n_ridge: FastNoiseLite
var _n_temp: FastNoiseLite
var _n_humid: FastNoiseLite
var _n_tint: FastNoiseLite
var _n_cave_a: FastNoiseLite
var _n_cave_b: FastNoiseLite
var _n_cavern: FastNoiseLite


func _init(world_seed: int) -> void:
	_seed = world_seed
	_seed_a = _mix64(world_seed * 0x9E3779B1 + 0x7F4A7C15)

	_n_cont = _make_noise(1, 0.0019, FastNoiseLite.FRACTAL_FBM, 4, 0.5, 2.0)
	_n_hills = _make_noise(2, 0.0105, FastNoiseLite.FRACTAL_FBM, 4, 0.5, 2.1)
	_n_relief = _make_noise(3, 0.0013, FastNoiseLite.FRACTAL_FBM, 2, 0.5, 2.0)
	_n_ridge = _make_noise(4, 0.0062, FastNoiseLite.FRACTAL_RIDGED, 4, 0.55, 2.05)
	_n_temp = _make_noise(5, 0.0011, FastNoiseLite.FRACTAL_FBM, 2, 0.45, 2.0)
	_n_humid = _make_noise(6, 0.0013, FastNoiseLite.FRACTAL_FBM, 2, 0.45, 2.0)
	_n_tint = _make_noise(7, 0.0075, FastNoiseLite.FRACTAL_NONE, 1, 0.5, 2.0)
	_n_cave_a = _make_noise(8, 0.0125, FastNoiseLite.FRACTAL_FBM, 2, 0.5, 2.0)
	_n_cave_b = _make_noise(9, 0.0125, FastNoiseLite.FRACTAL_FBM, 2, 0.5, 2.0)
	_n_cavern = _make_noise(10, 0.0175, FastNoiseLite.FRACTAL_FBM, 3, 0.5, 2.0)


func _make_noise(index: int, frequency: float, fractal: int, octaves: int,
		gain: float, lacunarity: float) -> FastNoiseLite:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.seed = int(_hash3i(index, 0, 0, _S_NOISE) & 0x7FFFFFFF)
	n.frequency = frequency
	n.fractal_type = fractal as FastNoiseLite.FractalType
	n.fractal_octaves = octaves
	n.fractal_gain = gain
	n.fractal_lacunarity = lacunarity
	return n


# ---------------------------------------------------------------------------
# Deterministic hashing
# ---------------------------------------------------------------------------

## Logical right shift. GDScript ints are signed, so the arithmetic shift has to
## be masked to keep the result positive and reproducible.
static func _shr(v: int, n: int) -> int:
	return (v >> n) & ((1 << (64 - n)) - 1)


## SplitMix style avalanche. Multiplications wrap around, which is exactly what
## a 64 bit integer hash wants.
static func _mix64(v: int) -> int:
	var x: int = v * _MIX_A
	x = (x ^ _shr(x, 31)) * _MIX_B
	x = (x ^ _shr(x, 29)) * _MIX_C
	return x ^ _shr(x, 32)


## Non negative hash of three integers plus a salt, folded with the world seed.
func _hash3i(a: int, b: int, c: int, salt: int) -> int:
	var h: int = _seed_a + salt * _KS
	h = _mix64(h ^ (a * _KX))
	h = _mix64(h ^ (b * _KY))
	h = _mix64(h ^ (c * _KZ))
	return h & 0x7FFFFFFFFFFFFFFF


func _rand01(a: int, b: int, c: int, salt: int) -> float:
	return float(_hash3i(a, b, c, salt) & 0xFFFFFF) / 16777216.0


static func _floor_div(a: int, b: int) -> int:
	var q: int = a / b
	if (a % b) != 0 and ((a < 0) != (b < 0)):
		q -= 1
	return q


# ---------------------------------------------------------------------------
# Height field
# ---------------------------------------------------------------------------

static func _spline(xs: PackedFloat32Array, ys: PackedFloat32Array, t: float) -> float:
	var n := xs.size()
	if t <= xs[0]:
		return ys[0]
	if t >= xs[n - 1]:
		return ys[n - 1]
	for i in range(1, n):
		if t < xs[i]:
			var u := (t - xs[i - 1]) / (xs[i] - xs[i - 1])
			return lerpf(ys[i - 1], ys[i], smoothstep(0.0, 1.0, u))
	return ys[n - 1]


## Continuous terrain height. The single source of truth: generate() and
## surface_height() both go through here, so they can never disagree.
func _height_f(wx: int, wz: int) -> float:
	var fx := float(wx)
	var fz := float(wz)

	var cont := clampf(_n_cont.get_noise_2d(fx, fz) * _CONT_GAIN + _CONT_BIAS, -1.0, 1.0)
	var base := _spline(_CONT_X, _CONT_Y, cont)

	# Relief drives local amplitude: near zero the plains stay flat, near one
	# the ground turns rough.
	var relief := clampf(_n_relief.get_noise_2d(fx, fz) * 0.75 + 0.5, 0.0, 1.0)
	var hills := _n_hills.get_noise_2d(fx, fz)
	var amp := 1.2 + relief * relief * 9.5

	# Flatten the coastal band a little so beaches are not a cliff.
	var coast := 1.0 - 0.35 * (1.0 - absf(clampf(cont * 9.0, -1.0, 1.0)))
	var h := base + hills * amp * coast

	var gate := smoothstep(0.34, 0.78, cont) * (0.30 + 0.70 * relief)
	if gate > 0.002:
		var ridge := clampf(_n_ridge.get_noise_2d(fx, fz) * 0.5 + 0.5, 0.0, 1.0)
		h += gate * ridge * ridge * 32.0

	if h > _CAP_START:
		var over := h - _CAP_START
		h = _CAP_START + over / (1.0 + over / _CAP_SPAN)
	return h


func _height_int(wx: int, wz: int) -> int:
	return clampi(int(floor(_height_f(wx, wz))), _MIN_HEIGHT, _MAX_HEIGHT)


func surface_height(wx: int, wz: int) -> int:
	return _height_int(wx, wz)


# ---------------------------------------------------------------------------
# Climate and biomes
# ---------------------------------------------------------------------------

func _temp_at(wx: int, wz: int) -> float:
	return clampf(_n_temp.get_noise_2d(float(wx), float(wz)) * 1.45, -1.0, 1.0)


func _humid_at(wx: int, wz: int) -> float:
	return clampf(_n_humid.get_noise_2d(float(wx), float(wz)) * 1.45, -1.0, 1.0)


func _biome_from(h: int, t: float, hu: float) -> int:
	if h < ChunkData.SEA_LEVEL - 2:
		return Biome.OCEAN
	if h <= ChunkData.SEA_LEVEL + 1:
		if t < -0.42:
			return Biome.TUNDRA
		if hu > 0.40 and t > 0.05:
			return Biome.SWAMP
		return Biome.BEACH
	if h >= 70:
		return Biome.MOUNTAINS
	if t < -0.34:
		return Biome.TAIGA if hu > -0.02 else Biome.TUNDRA
	if t < 0.04:
		return Biome.TAIGA if hu > 0.40 else Biome.PLAINS
	if t < 0.44:
		if hu > 0.44 and h <= 54:
			return Biome.SWAMP
		if hu > -0.08:
			return Biome.FOREST
		return Biome.PLAINS
	if hu < -0.30:
		return Biome.DESERT
	if hu < 0.20:
		return Biome.SAVANNA
	return Biome.FOREST


func biome_at(wx: int, wz: int) -> int:
	return _biome_from(_height_int(wx, wz), _temp_at(wx, wz), _humid_at(wx, wz))


static func biome_name(b: int) -> String:
	if b < 0 or b >= BIOME_NAMES.size():
		return "Inconnu"
	return BIOME_NAMES[b]


## Grass and foliage tint. Interpolated on the raw climate noises so no hard
## seam appears along a biome border.
func grass_color_at(wx: int, wz: int) -> Color:
	var t := clampf(_temp_at(wx, wz) * 0.5 + 0.5, 0.0, 1.0)
	var hu := clampf(_humid_at(wx, wz) * 0.5 + 0.5, 0.0, 1.0)

	# These are multipliers applied to a near neutral grey tile (about 0.63 in
	# linear space), so they double as the final albedo. They have to stay dark and
	# saturated: a tint around 0.6 lands the albedo near 0.4, which is far brighter
	# than any real vegetation and comes out of the tone mapper as pale sage rather
	# than as grass. Target albedo is roughly 0.16 to 0.24 in linear space.
	var cold_dry := Color(0.28, 0.36, 0.24)
	var cold_wet := Color(0.17, 0.34, 0.21)
	var hot_dry := Color(0.44, 0.40, 0.14)
	var hot_wet := Color(0.13, 0.40, 0.10)

	var cold := cold_dry.lerp(cold_wet, hu)
	var hot := hot_dry.lerp(hot_wet, hu)
	var c := cold.lerp(hot, t)

	# High ground fades toward a muted alpine green. Not toward a pale grey: that
	# turns every mountainside into bare white once the tile brightness is applied.
	var alt := clampf((_height_f(wx, wz) - 58.0) / 26.0, 0.0, 1.0)
	c = c.lerp(Color(0.32, 0.37, 0.30), alt * 0.45)

	var v := _n_tint.get_noise_2d(float(wx), float(wz)) * 0.045
	return Color(
		clampf(c.r + v, 0.0, 1.0),
		clampf(c.g + v, 0.0, 1.0),
		clampf(c.b + v, 0.0, 1.0),
		1.0)


# ---------------------------------------------------------------------------
# Caves
# ---------------------------------------------------------------------------

## Pure cave test. Callers clamp the vertical range so the top crust of the
## terrain and the bedrock floor are never pierced.
func _is_cave(wx: int, y: int, wz: int) -> bool:
	var fx := float(wx)
	var fz := float(wz)
	# Vertical squash: caves are wider than they are tall.
	var ya := float(y) * 1.75
	var t1 := absf(_n_cave_a.get_noise_3d(fx, ya, fz))
	if t1 < 0.075:
		var t2 := absf(_n_cave_b.get_noise_3d(fx, ya, fz))
		if t2 < 0.075:
			return true
	var c := _n_cavern.get_noise_3d(fx, float(y) * 1.30, fz)
	var thr := 0.36 + 0.32 * clampf(float(y - 24) / 34.0, 0.0, 1.0)
	return c > thr


# ---------------------------------------------------------------------------
# Surface cover
# ---------------------------------------------------------------------------

## Returns (top block, filler block, total cover depth).
func _cover_of(b: int, h: int, wx: int, wz: int) -> Vector3i:
	var depth := 3 + (_hash3i(wx, 7, wz, _S_SOIL) % 3)

	if h >= 80:
		return Vector3i(Blocks.SNOW_BLOCK, Blocks.STONE, 2)
	if b == Biome.MOUNTAINS:
		if h >= 74:
			return Vector3i(Blocks.GRAVEL, Blocks.STONE, 2)
		return Vector3i(Blocks.GRASS, Blocks.DIRT, depth)
	if b == Biome.OCEAN:
		if h < ChunkData.SEA_LEVEL - 10:
			return Vector3i(Blocks.GRAVEL, Blocks.SAND, depth)
		return Vector3i(Blocks.SAND, Blocks.SAND, depth)
	if b == Biome.BEACH or b == Biome.DESERT:
		return Vector3i(Blocks.SAND, Blocks.SANDSTONE, depth)
	if b == Biome.TUNDRA:
		if h < ChunkData.SEA_LEVEL:
			return Vector3i(Blocks.GRAVEL, Blocks.DIRT, depth)
		return Vector3i(Blocks.SNOW_BLOCK, Blocks.DIRT, depth)
	if b == Biome.SWAMP:
		if h <= ChunkData.SEA_LEVEL:
			return Vector3i(Blocks.CLAY, Blocks.DIRT, depth)
		return Vector3i(Blocks.GRASS, Blocks.DIRT, depth)
	if h < ChunkData.SEA_LEVEL:
		return Vector3i(Blocks.SAND, Blocks.DIRT, depth)
	return Vector3i(Blocks.GRASS, Blocks.DIRT, depth)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

## Fills data completely: strata, caves, deposits, water and decoration.
func generate(data: ChunkData) -> void:
	var x0 := data.cx * ChunkData.SIZE_X
	var z0 := data.cz * ChunkData.SIZE_Z
	var columns := ChunkData.SIZE_X * ChunkData.SIZE_Z

	var heights := PackedInt32Array()
	heights.resize(columns)
	var biomes := PackedInt32Array()
	biomes.resize(columns)
	var temps := PackedFloat32Array()
	temps.resize(columns)

	# --- strata and caves, column by column ---
	for lx in ChunkData.SIZE_X:
		var wx := x0 + lx
		for lz in ChunkData.SIZE_Z:
			var wz := z0 + lz
			var i := lx * ChunkData.SIZE_Z + lz
			var t := _temp_at(wx, wz)
			var hu := _humid_at(wx, wz)
			var h := _height_int(wx, wz)
			var b := _biome_from(h, t, hu)
			heights[i] = h
			biomes[i] = b
			temps[i] = t

			var cover := _cover_of(b, h, wx, wz)
			data.fill_column(lx, lz, 1, h, Blocks.STONE)

			var soil_from := maxi(4, h - cover.z + 1)
			if soil_from <= h - 1:
				data.fill_column(lx, lz, soil_from, h - 1, cover.y)
			data.set_local_raw(lx, h, lz, cover.x)

			# Bedrock floor plus a ragged fringe up to y 3.
			data.set_local_raw(lx, 0, lz, Blocks.BEDROCK)
			for y in range(1, 4):
				if _rand01(wx, y, wz, _S_BEDROCK) < 0.88 - 0.28 * float(y):
					data.set_local_raw(lx, y, lz, Blocks.BEDROCK)

			# Caves stop short of the surface so the ground never opens into
			# the sky or into the ocean.
			var cave_top := h - 3
			if h < ChunkData.SEA_LEVEL:
				cave_top = h - 5
			for y in range(4, cave_top + 1):
				if _is_cave(wx, y, wz):
					data.set_local_raw(lx, y, lz, Blocks.AIR)

	_place_deposits(data)
	_fill_water(data, heights, biomes, temps)

	# --- decoration over the 3x3 chunk window ---
	var trees: Array[Vector4i] = []
	for dcx in range(-1, 2):
		for dcz in range(-1, 2):
			_collect_trees(data.cx + dcx, data.cz + dcz, trees)
	# Two ordered passes so the result never depends on the order features were
	# enumerated in: leaves merge by lowest id, logs then win over leaves.
	for t in trees:
		_emit_leaves(data, t, x0, z0)
	for t in trees:
		_emit_logs(data, t, x0, z0)

	_decorate_ground(data, heights, biomes, x0, z0)
	_place_villages(data, x0, z0)

	data.recompute_tops()


func _fill_water(data: ChunkData, heights: PackedInt32Array,
		biomes: PackedInt32Array, temps: PackedFloat32Array) -> void:
	var sea := ChunkData.SEA_LEVEL
	for lx in ChunkData.SIZE_X:
		for lz in ChunkData.SIZE_Z:
			var i := lx * ChunkData.SIZE_Z + lz
			var h: int = heights[i]
			if h >= sea:
				continue
			var frozen: bool = biomes[i] == Biome.TUNDRA or temps[i] < -0.42
			var y := sea
			while y > h:
				if data.get_local(lx, y, lz) != Blocks.AIR:
					break
				var id := Blocks.WATER
				if y == sea and frozen:
					id = Blocks.ICE
				data.set_local_raw(lx, y, lz, id)
				y -= 1


# ---------------------------------------------------------------------------
# Ores and pockets
# ---------------------------------------------------------------------------

func _place_deposits(data: ChunkData) -> void:
	var x0 := data.cx * ChunkData.SIZE_X
	var z0 := data.cz * ChunkData.SIZE_Z
	var gx_min := _floor_div(x0 - _DEP_REACH, _DEP_CELL)
	var gx_max := _floor_div(x0 + ChunkData.SIZE_X - 1 + _DEP_REACH, _DEP_CELL)
	var gz_min := _floor_div(z0 - _DEP_REACH, _DEP_CELL)
	var gz_max := _floor_div(z0 + ChunkData.SIZE_Z - 1 + _DEP_REACH, _DEP_CELL)
	var gy_max := ChunkData.SIZE_Y / _DEP_CELL

	for gx in range(gx_min, gx_max + 1):
		for gz in range(gz_min, gz_max + 1):
			for gy in range(0, gy_max + 1):
				var hsh := _hash3i(gx, gy, gz, _S_DEPOSIT)
				var px := gx * _DEP_CELL + (hsh % _DEP_CELL)
				var py := gy * _DEP_CELL + ((hsh >> 4) % _DEP_CELL)
				var pz := gz * _DEP_CELL + ((hsh >> 8) % _DEP_CELL)
				var r := float((hsh >> 14) & 0xFFFF) / 65536.0

				var id := Blocks.AIR
				var pocket := false
				if r < 0.110:
					if py >= 5 and py <= 70:
						id = Blocks.COAL_ORE
				elif r < 0.168:
					if py >= 5 and py <= 55:
						id = Blocks.IRON_ORE
				elif r < 0.183:
					if py >= 4 and py <= 30:
						id = Blocks.GOLD_ORE
				elif r < 0.190:
					if py >= 2 and py <= 16:
						id = Blocks.DIAMOND_ORE
				elif r < 0.206:
					if py >= 4 and py <= 60:
						id = Blocks.GRANITE
						pocket = true
				elif r < 0.221:
					if py >= 4 and py <= 62:
						id = Blocks.MARBLE
						pocket = true
				elif r < 0.239:
					if py >= 34 and py <= 54:
						id = Blocks.CLAY
						pocket = true
				if id == Blocks.AIR:
					continue

				if pocket:
					_emit_pocket(data, px, py, pz, id, 2 + ((hsh >> 30) % 3), x0, z0)
				else:
					_emit_vein(data, px, py, pz, id, 3 + ((hsh >> 30) % 7), x0, z0)


func _emit_vein(data: ChunkData, px: int, py: int, pz: int, id: int, steps: int,
		x0: int, z0: int) -> void:
	var cur := Vector3i(px, py, pz)
	for k in steps:
		_replace_stone(data, cur.x, cur.y, cur.z, id, x0, z0)
		var d: int = _hash3i(px + k * 7, py, pz - k * 3, _S_VEIN) % 6
		cur += _DIRS[d]
		if cur.y < 1:
			cur.y = 1
		elif cur.y > ChunkData.SIZE_Y - 2:
			cur.y = ChunkData.SIZE_Y - 2


func _emit_pocket(data: ChunkData, px: int, py: int, pz: int, id: int, radius: int,
		x0: int, z0: int) -> void:
	var r2 := radius * radius + 1
	for dx in range(-radius, radius + 1):
		for dy in range(-radius, radius + 1):
			for dz in range(-radius, radius + 1):
				if dx * dx + dy * dy + dz * dz > r2:
					continue
				_replace_stone(data, px + dx, py + dy, pz + dz, id, x0, z0)


func _replace_stone(data: ChunkData, wx: int, wy: int, wz: int, id: int,
		x0: int, z0: int) -> void:
	var lx := wx - x0
	var lz := wz - z0
	if lx < 0 or lx >= ChunkData.SIZE_X or lz < 0 or lz >= ChunkData.SIZE_Z:
		return
	if wy < 1 or wy >= ChunkData.SIZE_Y:
		return
	var cur := data.get_local(lx, wy, lz)
	if cur == Blocks.STONE:
		data.set_local_raw(lx, wy, lz, id)
	elif id == Blocks.CLAY and (cur == Blocks.DIRT or cur == Blocks.SAND):
		data.set_local_raw(lx, wy, lz, id)


# ---------------------------------------------------------------------------
# Trees
# ---------------------------------------------------------------------------

func _tree_density(b: int) -> float:
	match b:
		Biome.FOREST:
			return 0.72
		Biome.TAIGA:
			return 0.62
		Biome.SWAMP:
			return 0.30
		Biome.PLAINS:
			return 0.055
		Biome.SAVANNA:
			return 0.085
		Biome.MOUNTAINS:
			return 0.05
		_:
			return 0.0


## Enumerates every tree of one chunk. Pure function of the chunk coordinates
## and the seed, so the chunk to the east enumerates exactly the same trees and
## both agree on the canopy that crosses their border.
func _collect_trees(tcx: int, tcz: int, out: Array[Vector4i]) -> void:
	var bx := tcx * ChunkData.SIZE_X
	var bz := tcz * ChunkData.SIZE_Z
	var cells_x := ChunkData.SIZE_X / _TREE_CELL
	var cells_z := ChunkData.SIZE_Z / _TREE_CELL
	for gx in cells_x:
		for gz in cells_z:
			var cell_x := bx + gx * _TREE_CELL
			var cell_z := bz + gz * _TREE_CELL
			var hsh := _hash3i(cell_x, 0, cell_z, _S_TREE)
			var wx := cell_x + (hsh % _TREE_CELL)
			var wz := cell_z + ((hsh >> 3) % _TREE_CELL)
			var r := float((hsh >> 8) & 0xFFFF) / 65536.0

			var h := _height_int(wx, wz)
			if h < ChunkData.SEA_LEVEL or h > 78:
				continue
			var t := _temp_at(wx, wz)
			var hu := _humid_at(wx, wz)
			var b := _biome_from(h, t, hu)
			var density := _tree_density(b)
			if density <= 0.0 or r >= density:
				continue

			var pick := float((hsh >> 26) & 0xFF) / 256.0
			var species := _SPECIES_OAK
			var trunk := 4
			if b == Biome.TAIGA or (b == Biome.MOUNTAINS and t < 0.1):
				species = _SPECIES_PINE
				trunk = 6 + ((hsh >> 40) % 5)
			elif pick < 0.28 and (b == Biome.FOREST or b == Biome.PLAINS):
				species = _SPECIES_BIRCH
				trunk = 6 + ((hsh >> 40) % 4)
			else:
				species = _SPECIES_OAK
				trunk = 4 + ((hsh >> 40) % 4)
			out.append(Vector4i(wx, h, wz, species * 64 + trunk))


func _is_leaf(id: int) -> bool:
	return id == Blocks.OAK_LEAVES or id == Blocks.BIRCH_LEAVES or id == Blocks.PINE_LEAVES


func _is_log(id: int) -> bool:
	return id == Blocks.OAK_LOG or id == Blocks.BIRCH_LOG


## Leaf writes must be commutative: two overlapping canopies resolve to the
## lowest block id whichever order they were emitted in.
func _place_leaf(data: ChunkData, lx: int, ly: int, lz: int, id: int) -> void:
	if lx < 0 or lx >= ChunkData.SIZE_X or lz < 0 or lz >= ChunkData.SIZE_Z:
		return
	if ly < 0 or ly >= ChunkData.SIZE_Y:
		return
	var cur := data.get_local(lx, ly, lz)
	if cur == Blocks.AIR:
		data.set_local_raw(lx, ly, lz, id)
	elif _is_leaf(cur):
		data.set_local_raw(lx, ly, lz, mini(cur, id))


func _place_log(data: ChunkData, lx: int, ly: int, lz: int, id: int) -> void:
	if lx < 0 or lx >= ChunkData.SIZE_X or lz < 0 or lz >= ChunkData.SIZE_Z:
		return
	if ly < 0 or ly >= ChunkData.SIZE_Y:
		return
	var cur := data.get_local(lx, ly, lz)
	if cur == Blocks.AIR or _is_leaf(cur):
		data.set_local_raw(lx, ly, lz, id)
	elif _is_log(cur):
		data.set_local_raw(lx, ly, lz, mini(cur, id))


func _emit_leaves(data: ChunkData, tree: Vector4i, x0: int, z0: int) -> void:
	var wx := tree.x
	var ground := tree.y
	var wz := tree.z
	var species := tree.w >> 6
	var trunk := tree.w & 63
	var top := ground + trunk
	var lx0 := wx - x0
	var lz0 := wz - z0
	# Cheap rejection: no canopy reaches further than 3 blocks sideways.
	if lx0 < -4 or lx0 > ChunkData.SIZE_X + 3 or lz0 < -4 or lz0 > ChunkData.SIZE_Z + 3:
		return

	if species == _SPECIES_PINE:
		var leaf_id := Blocks.PINE_LEAVES
		var start := ground + 3
		for ly in range(start, top + 2):
			var d := top - ly
			var radius := 0
			if d < 0:
				radius = 0
			elif d == 0:
				radius = 1
			else:
				radius = clampi(1 + int(float(d) * 0.34), 1, 3)
				if (d % 3) == 1:
					radius = maxi(1, radius - 1)
			for dx in range(-radius, radius + 1):
				for dz in range(-radius, radius + 1):
					if absi(dx) + absi(dz) > radius:
						continue
					_place_leaf(data, lx0 + dx, ly, lz0 + dz, leaf_id)
		return

	var leaf := Blocks.BIRCH_LEAVES if species == _SPECIES_BIRCH else Blocks.OAK_LEAVES
	var low := -3 if species == _SPECIES_BIRCH else -2
	for dy in range(low, 2):
		var ly := top + dy
		var radius := 1
		if species == _SPECIES_BIRCH:
			radius = 2 if (dy == -2 or dy == -1) else 1
		else:
			radius = 2 if dy < 1 else 1
		for dx in range(-radius, radius + 1):
			for dz in range(-radius, radius + 1):
				if absi(dx) == radius and absi(dz) == radius:
					# Trim the corners, deterministically per world position.
					if _rand01(wx + dx, ly, wz + dz, _S_LEAF) < 0.55:
						continue
				_place_leaf(data, lx0 + dx, ly, lz0 + dz, leaf)


func _emit_logs(data: ChunkData, tree: Vector4i, x0: int, z0: int) -> void:
	var lx0 := tree.x - x0
	var lz0 := tree.z - z0
	if lx0 < 0 or lx0 >= ChunkData.SIZE_X or lz0 < 0 or lz0 >= ChunkData.SIZE_Z:
		return
	var species := tree.w >> 6
	var trunk := tree.w & 63
	var log_id := Blocks.BIRCH_LOG if species == _SPECIES_BIRCH else Blocks.OAK_LOG
	for ly in range(tree.y + 1, tree.y + trunk + 1):
		_place_log(data, lx0, ly, lz0, log_id)


# ---------------------------------------------------------------------------
# Ground cover: plants, cacti, pumpkins
# ---------------------------------------------------------------------------

func _decorate_ground(data: ChunkData, heights: PackedInt32Array,
		biomes: PackedInt32Array, x0: int, z0: int) -> void:
	for lx in ChunkData.SIZE_X:
		var wx := x0 + lx
		for lz in ChunkData.SIZE_Z:
			var i := lx * ChunkData.SIZE_Z + lz
			var h: int = heights[i]
			if h < ChunkData.SEA_LEVEL or h + 1 >= ChunkData.SIZE_Y:
				continue
			if data.get_local(lx, h + 1, lz) != Blocks.AIR:
				continue
			var wz := z0 + lz
			var ground := data.get_local(lx, h, lz)
			var b: int = biomes[i]
			var r := _rand01(wx, 1, wz, _S_PLANT)
			var id := Blocks.AIR

			if b == Biome.DESERT:
				if ground != Blocks.SAND:
					continue
				if r < 0.004:
					_grow_cactus(data, lx, h, lz, wx, wz)
					continue
				if r < 0.020:
					id = Blocks.DEAD_BUSH
			elif b == Biome.PLAINS:
				if ground != Blocks.GRASS:
					continue
				if r < 0.130:
					id = Blocks.GRASS_TUFT
				elif r < 0.160:
					id = Blocks.FLOWER_RED
				elif r < 0.190:
					id = Blocks.FLOWER_YELLOW
				elif r < 0.200:
					id = Blocks.FERN
				elif r < 0.2015:
					id = Blocks.PUMPKIN
			elif b == Biome.FOREST:
				if ground != Blocks.GRASS:
					continue
				if r < 0.110:
					id = Blocks.GRASS_TUFT
				elif r < 0.190:
					id = Blocks.FERN
				elif r < 0.200:
					id = Blocks.FLOWER_RED
				elif r < 0.2012:
					id = Blocks.PUMPKIN
				elif r < 0.2055:
					id = Blocks.SAPLING
			elif b == Biome.SWAMP:
				if ground != Blocks.GRASS:
					continue
				if r < 0.090:
					id = Blocks.FERN
				elif r < 0.130:
					id = Blocks.GRASS_TUFT
			elif b == Biome.SAVANNA:
				if ground != Blocks.GRASS:
					continue
				if r < 0.075:
					id = Blocks.GRASS_TUFT
				elif r < 0.082:
					id = Blocks.DEAD_BUSH
			elif b == Biome.TAIGA:
				if ground != Blocks.GRASS:
					continue
				if r < 0.045:
					id = Blocks.FERN
				elif r < 0.060:
					id = Blocks.GRASS_TUFT
				elif r < 0.064:
					id = Blocks.SAPLING
			elif b == Biome.MOUNTAINS:
				if ground != Blocks.GRASS:
					continue
				if r < 0.030:
					id = Blocks.GRASS_TUFT
			elif b == Biome.BEACH:
				if ground == Blocks.SAND and r < 0.006:
					id = Blocks.DEAD_BUSH
			if id != Blocks.AIR:
				data.set_local_raw(lx, h + 1, lz, id)


func _grow_cactus(data: ChunkData, lx: int, h: int, lz: int, wx: int, wz: int) -> void:
	var tall := 1 + (_hash3i(wx, 5, wz, _S_PLANT2) % 3)
	for k in tall:
		var y := h + 1 + k
		if y >= ChunkData.SIZE_Y:
			return
		if data.get_local(lx, y, lz) != Blocks.AIR:
			return
		data.set_local_raw(lx, y, lz, Blocks.CACTUS)


# ---------------------------------------------------------------------------
# Villages
# ---------------------------------------------------------------------------

## Returns the village owned by one large map cell, or Vector4i.ZERO when the
## broad site is wet, mountainous or too uneven. Fields are centre x, reference
## height, centre z and quarter-turn rotation.
func _village_for_cell(cell_x: int, cell_z: int) -> Vector4i:
	var base_x := cell_x * _VILLAGE_CELL
	var base_z := cell_z * _VILLAGE_CELL
	var hsh := _hash3i(cell_x, 0, cell_z, _S_HOUSE)
	var margin := _VILLAGE_REACH + 5
	var wx := base_x + margin + (hsh % (_VILLAGE_CELL - margin * 2))
	var wz := base_z + margin + ((hsh >> 9) % (_VILLAGE_CELL - margin * 2))
	var rotation := int((hsh >> 18) & 3)

	var lo := ChunkData.SIZE_Y
	var hi := 0
	# Sample the whole village footprint. Individual foundations handle the
	# remaining block-scale variation, but the village as a whole stays gentle.
	for dx in range(-18, 19, 2):
		for dz in range(-14, 17, 2):
			var ground := _height_int(wx + dx, wz + dz)
			lo = mini(lo, ground)
			hi = maxi(hi, ground)
			if ground < ChunkData.SEA_LEVEL + 1 or ground > ChunkData.SIZE_Y - _HOUSE_HEIGHT - 3:
				return Vector4i.ZERO
	if hi - lo > 7:
		return Vector4i.ZERO
	var biome := biome_at(wx, wz)
	if biome not in [Biome.PLAINS, Biome.FOREST, Biome.TAIGA, Biome.SAVANNA]:
		return Vector4i.ZERO
	return Vector4i(wx, hi, wz, rotation)


func _rotate_village_offset(rotation: int, x: int, z: int) -> Vector2i:
	match rotation & 3:
		1:
			return Vector2i(-z, x)
		2:
			return Vector2i(-x, -z)
		3:
			return Vector2i(z, -x)
		_:
			return Vector2i(x, z)


func _make_house(village: Vector4i, local_x: int, local_z: int, house_kind: int) -> Vector4i:
	var offset := _rotate_village_offset(village.w, local_x, local_z)
	var wx := village.x + offset.x
	var wz := village.z + offset.y
	var hi := 0
	var rotation := village.w & 3
	var rx := _HOUSE_HALF_DEPTH if (rotation & 1) else _HOUSE_HALF_WIDTH
	var rz := _HOUSE_HALF_WIDTH if (rotation & 1) else _HOUSE_HALF_DEPTH
	for dx in range(-rx, rx + 1):
		for dz in range(-rz, rz + 1):
			hi = maxi(hi, _height_int(wx + dx, wz + dz))
	# w packs house kind above the two rotation bits.
	return Vector4i(wx, hi + 1, wz, (house_kind << 2) | rotation)


func _village_houses(village: Vector4i) -> Array[Vector4i]:
	var out: Array[Vector4i] = []
	out.append(_make_house(village, -10, -6, HOUSE_TIMBER))
	out.append(_make_house(village, 10, -6, HOUSE_MASON))
	return out


func _village_pen(village: Vector4i) -> Vector4i:
	var offset := _rotate_village_offset(village.w, 0, 10)
	var wx := village.x + offset.x
	var wz := village.z + offset.y
	return Vector4i(wx, _height_int(wx, wz) + 1, wz, village.w & 3)


## Compatibility helper used by the focused terrain regression: the first
## house is always the timber house of an accepted village cell.
func _house_for_cell(cell_x: int, cell_z: int) -> Vector4i:
	var village := _village_for_cell(cell_x, cell_z)
	if village == Vector4i.ZERO:
		return Vector4i.ZERO
	return _village_houses(village)[0]


## Public metadata used by the settlement actor manager. Only anchors whose
## centre belongs to this chunk are returned, so every house gets one owner.
func houses_in_chunk(cx: int, cz: int) -> Array[Vector4i]:
	var out: Array[Vector4i] = []
	var min_x := cx * ChunkData.SIZE_X
	var min_z := cz * ChunkData.SIZE_Z
	var max_x := min_x + ChunkData.SIZE_X - 1
	var max_z := min_z + ChunkData.SIZE_Z - 1
	for cell_x in range(_floor_div(min_x - _VILLAGE_REACH, _VILLAGE_CELL),
			_floor_div(max_x + _VILLAGE_REACH, _VILLAGE_CELL) + 1):
		for cell_z in range(_floor_div(min_z - _VILLAGE_REACH, _VILLAGE_CELL),
				_floor_div(max_z + _VILLAGE_REACH, _VILLAGE_CELL) + 1):
			var village := _village_for_cell(cell_x, cell_z)
			if village == Vector4i.ZERO:
				continue
			for house in _village_houses(village):
				if house.x >= min_x and house.x <= max_x and house.z >= min_z and house.z <= max_z:
					out.append(house)
	return out


## Nearest timber-house anchor to a world position, scanning village cells ring
## by ring. Deterministic, so it makes a stable world spawn. Returns
## Vector4i.ZERO when no village exists within `max_rings` cells. One extra
## ring is scanned after the first hit because in-cell offsets can place a
## nearer village in the following ring.
func nearest_house(near_wx: int, near_wz: int, max_rings: int = 24) -> Vector4i:
	var cell_x := _floor_div(near_wx, _VILLAGE_CELL)
	var cell_z := _floor_div(near_wz, _VILLAGE_CELL)
	var best := Vector4i.ZERO
	var best_d := INF
	var found_ring := -1
	for ring in max_rings:
		if found_ring >= 0 and ring > found_ring + 1:
			break
		for cx in range(cell_x - ring, cell_x + ring + 1):
			for cz in range(cell_z - ring, cell_z + ring + 1):
				if maxi(absi(cx - cell_x), absi(cz - cell_z)) != ring:
					continue
				var village := _village_for_cell(cx, cz)
				if village == Vector4i.ZERO:
					continue
				var house := _village_houses(village)[0]
				var d := Vector2(float(house.x - near_wx), float(house.z - near_wz)).length()
				if d < best_d:
					best_d = d
					best = house
		if best_d < INF and found_ring < 0:
			found_ring = ring
	return best


## Pen centres owned by a chunk, consumed by SettlementManager for livestock.
func pens_in_chunk(cx: int, cz: int) -> Array[Vector4i]:
	var out: Array[Vector4i] = []
	var min_x := cx * ChunkData.SIZE_X
	var min_z := cz * ChunkData.SIZE_Z
	var max_x := min_x + ChunkData.SIZE_X - 1
	var max_z := min_z + ChunkData.SIZE_Z - 1
	for cell_x in range(_floor_div(min_x - _VILLAGE_REACH, _VILLAGE_CELL),
			_floor_div(max_x + _VILLAGE_REACH, _VILLAGE_CELL) + 1):
		for cell_z in range(_floor_div(min_z - _VILLAGE_REACH, _VILLAGE_CELL),
				_floor_div(max_z + _VILLAGE_REACH, _VILLAGE_CELL) + 1):
			var village := _village_for_cell(cell_x, cell_z)
			if village == Vector4i.ZERO:
				continue
			var pen := _village_pen(village)
			if pen.x >= min_x and pen.x <= max_x and pen.z >= min_z and pen.z <= max_z:
				out.append(pen)
	return out


## Emits complete villages that can touch this chunk. Every component derives
## from a pure cell anchor, preserving cross-chunk generation order invariance.
func _place_villages(data: ChunkData, x0: int, z0: int) -> void:
	var min_x := x0 - _VILLAGE_REACH
	var min_z := z0 - _VILLAGE_REACH
	var max_x := x0 + ChunkData.SIZE_X - 1 + _VILLAGE_REACH
	var max_z := z0 + ChunkData.SIZE_Z - 1 + _VILLAGE_REACH
	for cell_x in range(_floor_div(min_x, _VILLAGE_CELL), _floor_div(max_x, _VILLAGE_CELL) + 1):
		for cell_z in range(_floor_div(min_z, _VILLAGE_CELL), _floor_div(max_z, _VILLAGE_CELL) + 1):
			var village := _village_for_cell(cell_x, cell_z)
			if village == Vector4i.ZERO:
				continue
			_emit_village_paths(data, village, x0, z0)
			for house in _village_houses(village):
				_emit_house(data, house, x0, z0)
			_emit_pen(data, _village_pen(village), x0, z0)


func _house_world_offset(house: Vector4i, hx: int, hz: int) -> Vector2i:
	return _rotate_village_offset(house.w & 3, hx, hz)


func _house_set(data: ChunkData, house: Vector4i, x0: int, z0: int,
		hx: int, y: int, hz: int, id: int) -> void:
	var offset := _house_world_offset(house, hx, hz)
	var lx := house.x + offset.x - x0
	var lz := house.z + offset.y - z0
	if ChunkData.in_bounds(lx, y, lz):
		data.set_local_raw(lx, y, lz, id)


func _emit_house(data: ChunkData, house: Vector4i, x0: int, z0: int) -> void:
	assert(house.y > ChunkData.SEA_LEVEL, "houses must have a dry foundation")
	assert(house.y + _HOUSE_HEIGHT < ChunkData.SIZE_Y, "house exceeds world height")
	var floor_y := house.y
	var house_kind := house.w >> 2
	var floor_id := Blocks.COBBLESTONE if house_kind == HOUSE_MASON else Blocks.OAK_PLANKS
	var wall_id := Blocks.STONE_BRICK if house_kind == HOUSE_MASON else Blocks.OAK_PLANKS

	# Clear trees and plants from the complete structure volume, then bridge the
	# one-block terrain variation with a cobblestone foundation.
	for hx in range(-_HOUSE_HALF_WIDTH, _HOUSE_HALF_WIDTH + 1):
		for hz in range(-_HOUSE_HALF_DEPTH, _HOUSE_HALF_DEPTH + 1):
			var offset := _house_world_offset(house, hx, hz)
			var ground := _height_int(house.x + offset.x, house.z + offset.y)
			for y in range(ground + 1, floor_y + _HOUSE_HEIGHT + 1):
				_house_set(data, house, x0, z0, hx, y, hz, Blocks.AIR)
			for y in range(ground + 1, floor_y):
				_house_set(data, house, x0, z0, hx, y, hz, Blocks.COBBLESTONE)
			_house_set(data, house, x0, z0, hx, floor_y, hz, floor_id)

	# Timber corners and plank walls, with a two-block front door and windows.
	for y in range(floor_y + 1, floor_y + 4):
		for hx in range(-_HOUSE_HALF_WIDTH, _HOUSE_HALF_WIDTH + 1):
			for hz in range(-_HOUSE_HALF_DEPTH, _HOUSE_HALF_DEPTH + 1):
				if absi(hx) != _HOUSE_HALF_WIDTH and absi(hz) != _HOUSE_HALF_DEPTH:
					continue
				var id := wall_id
				if absi(hx) == _HOUSE_HALF_WIDTH and absi(hz) == _HOUSE_HALF_DEPTH:
					id = Blocks.OAK_LOG
				var door := hz == _HOUSE_HALF_DEPTH and hx == 0 and y <= floor_y + 2
				var window := y == floor_y + 2 and ((absi(hx) == _HOUSE_HALF_WIDTH and hz == 0) \
						or (absi(hz) == _HOUSE_HALF_DEPTH and absi(hx) == 2))
				if door:
					id = Blocks.AIR
				elif window:
					id = Blocks.GLASS
				_house_set(data, house, x0, z0, hx, y, hz, id)

	if house_kind == HOUSE_MASON:
		# Broad brick workshop roof plus a stone chimney differentiates the second
		# house silhouette even from the far side of a village.
		for hx in range(-_HOUSE_HALF_WIDTH - 1, _HOUSE_HALF_WIDTH + 2):
			for hz in range(-_HOUSE_HALF_DEPTH - 1, _HOUSE_HALF_DEPTH + 2):
				_house_set(data, house, x0, z0, hx, floor_y + 4, hz, Blocks.BRICK)
		for y in range(floor_y + 5, floor_y + 8):
			_house_set(data, house, x0, z0, 2, y, -1, Blocks.COBBLESTONE)
	else:
		# The timber home keeps its steep pale gable.
		for layer in 4:
			var roof_y := floor_y + 4 + layer
			var depth := _HOUSE_HALF_DEPTH - layer
			for hx in range(-_HOUSE_HALF_WIDTH - 1, _HOUSE_HALF_WIDTH + 2):
				for hz in [-depth, depth]:
					_house_set(data, house, x0, z0, hx, roof_y, hz, Blocks.BIRCH_PLANKS)
	_house_set(data, house, x0, z0, 0, floor_y + 3, 0, Blocks.LAMP)


func _village_ground_set(data: ChunkData, village: Vector4i, x0: int, z0: int,
		local_x: int, local_z: int, id: int) -> void:
	var offset := _rotate_village_offset(village.w, local_x, local_z)
	var wx := village.x + offset.x
	var wz := village.z + offset.y
	var lx := wx - x0
	var lz := wz - z0
	var y := _height_int(wx, wz)
	if ChunkData.in_bounds(lx, y, lz):
		data.set_local_raw(lx, y, lz, id)
		# Roads are kept walkable even when the village lands in a forest.
		for clear_y in range(y + 1, mini(y + 7, ChunkData.SIZE_Y)):
			data.set_local_raw(lx, clear_y, lz, Blocks.AIR)


func _emit_village_paths(data: ChunkData, village: Vector4i, x0: int, z0: int) -> void:
	# A central lane joins both front doors, then runs north to the livestock pen.
	for px in range(-10, 11):
		for pz in range(-1, 2):
			_village_ground_set(data, village, x0, z0, px, pz, Blocks.COBBLESTONE)
	for px in [-10, 10]:
		for pz in range(-3, 1):
			_village_ground_set(data, village, x0, z0, px, pz, Blocks.COBBLESTONE)
	for px in range(-1, 2):
		for pz in range(0, 6):
			_village_ground_set(data, village, x0, z0, px, pz, Blocks.COBBLESTONE)


func _pen_set(data: ChunkData, pen: Vector4i, x0: int, z0: int,
		px: int, pz: int, y: int, id: int) -> void:
	var offset := _rotate_village_offset(pen.w, px, pz)
	var lx := pen.x + offset.x - x0
	var lz := pen.z + offset.y - z0
	if ChunkData.in_bounds(lx, y, lz):
		data.set_local_raw(lx, y, lz, id)


func _emit_pen(data: ChunkData, pen: Vector4i, x0: int, z0: int) -> void:
	const HALF_X := 6
	const HALF_Z := 5
	# Clear trunks, leaves and plants throughout the pen before closing it.
	for px in range(-HALF_X, HALF_X + 1):
		for pz in range(-HALF_Z, HALF_Z + 1):
			var clear_offset := _rotate_village_offset(pen.w, px, pz)
			var clear_ground := _height_int(pen.x + clear_offset.x, pen.z + clear_offset.y)
			for y in range(clear_ground + 1, mini(clear_ground + 6, ChunkData.SIZE_Y)):
				_pen_set(data, pen, x0, z0, px, pz, y, Blocks.AIR)
	for px in range(-HALF_X, HALF_X + 1):
		for pz in range(-HALF_Z, HALF_Z + 1):
			if absi(px) != HALF_X and absi(pz) != HALF_Z:
				continue
			var offset := _rotate_village_offset(pen.w, px, pz)
			var ground := _height_int(pen.x + offset.x, pen.z + offset.y)
			var post := (absi(px) == HALF_X and absi(pz) == HALF_Z) \
					or (absi(px) == HALF_X and pz % 3 == 0) \
					or (absi(pz) == HALF_Z and px % 3 == 0)
			_pen_set(data, pen, x0, z0, px, pz, ground + 1,
					Blocks.OAK_LOG if post else Blocks.OAK_PLANKS)
			if absi(px) == HALF_X and absi(pz) == HALF_Z:
				_pen_set(data, pen, x0, z0, px, pz, ground + 2, Blocks.LAMP)


# ---------------------------------------------------------------------------
# Spawn
# ---------------------------------------------------------------------------

## True when no tree trunk stands close enough for its canopy to swallow the
## column. Leaves collide, so spawning inside one would trap the player.
func _tree_free(wx: int, wz: int) -> bool:
	var ccx := _floor_div(wx, ChunkData.SIZE_X)
	var ccz := _floor_div(wz, ChunkData.SIZE_Z)
	var trees: Array[Vector4i] = []
	for dcx in range(-1, 2):
		for dcz in range(-1, 2):
			_collect_trees(ccx + dcx, ccz + dcz, trees)
	for t in trees:
		if absi(t.x - wx) <= 3 and absi(t.z - wz) <= 3:
			return false
	return true


## Safe spawn: dry land above sea level, as close to the origin as possible.
func spawn_point() -> Vector3:
	var fallback := Vector3(0.5, float(ChunkData.SEA_LEVEL + 4), 0.5)
	for ring in 96:
		var d := ring * 5
		var samples := 1 if ring == 0 else 12
		for k in samples:
			var wx := 0
			var wz := 0
			if ring > 0:
				var ang := TAU * float(k) / float(samples)
				wx = int(round(cos(ang) * float(d)))
				wz = int(round(sin(ang) * float(d)))
			var h := _height_int(wx, wz)
			if h < ChunkData.SEA_LEVEL + 1 or h > 76:
				continue
			var b := _biome_from(h, _temp_at(wx, wz), _humid_at(wx, wz))
			if b == Biome.OCEAN:
				continue
			if not _tree_free(wx, wz):
				continue
			return Vector3(float(wx) + 0.5, float(h + 1), float(wz) + 0.5)
	return fallback
