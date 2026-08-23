class_name Heightfield
extends RefCounted
## Pure terrain function of the Normandy pocket.
##
## THREAD SAFETY CONTRACT. Everything this class needs is built inside `_init`
## (and, once, inside `bake_sites()` which runs on the main thread before the
## workers start). After that the object is READ ONLY: `height_at()` and its
## friends never write a member, never cache anything, never allocate an Array,
## and never touch the scene. They are therefore safe to call from any number of
## generation threads at the same time, and always return the same value for the
## same input.
##
## The noise is a hand written integer hash plus smooth interpolation rather
## than FastNoiseLite, so the terrain is bit for bit reproducible from the seed
## alone, with no engine object involved.
##
## GEOGRAPHY (compass convention of the project: NORTH = -Z, SOUTH = +Z,
## EAST = +X, WEST = -X):
##  - rolling bocage everywhere, roughly 25 m of amplitude, hedged fields;
##  - a wooded RIDGE in the NORTH, rising from z = -1150 to about 45 m near
##    z = -1900, cut by the river gorge;
##  - MARSHES in the SOUTH WEST, around (-1250, 1250), sitting at water level
##    and muddy, with pools below WATER_LEVEL;
##  - a RIVER meandering from north to south (plus one tributary), bed carved
##    about 3 m below WATER_LEVEL, spanned by the SITE_BRIDGE sites;
##  - on the EAST edge, a descent towards a BEACH, interrupted by two stretches
##    of CLIFF (B_ROCK, very steep) around z = -520 and z = 880;
##  - the sea itself beyond x = 1960.
##
## Roads and site footprints FLATTEN the ground: the natural relief is blended
## towards a target height with a smoothstep weight, so a village never sits at
## the top of an artificial cliff.

# --- Contract constants -------------------------------------------------------

const WORLD_SIZE := 4096.0
const HALF := 2048.0
const WATER_LEVEL := 2.0
const TILE_SIZE := 64.0

# Biomes
const B_FIELD := 0        # champ cultive, ble
const B_MEADOW := 1       # prairie, bocage
const B_FOREST := 2
const B_MARSH := 3
const B_ROAD := 4
const B_VILLAGE := 5
const B_WATER := 6
const B_ROCK := 7
const B_ORCHARD := 8

# --- Tuning -------------------------------------------------------------------

## Acceleration grid: 128 m cells over the 4096 m square, same layout as Layout.
const _CELL := 128.0
const _GRID := 32
## Settlement proximity mask, one byte per 64 m tile.
const _SETTLE_CELL := 64.0
const _SETTLE_GRID := 64
const _SETTLE_RANGE := 300.0

## Base relief.
const _BASE_LEVEL := 7.0
const _BASE_AMPLITUDE := 24.0
const _BASE_FREQ := 0.0016
const _DETAIL_FREQ := 0.0062
const _WARP_FREQ := 0.00042
const _WARP_AMOUNT := 260.0

## Northern ridge.
const _RIDGE_START := -1150.0
const _RIDGE_TOP := -1900.0
const _RIDGE_HEIGHT := 25.0

## Marshes.
const _MARSH_X := -1250.0
const _MARSH_Z := 1250.0
const _MARSH_RX := 700.0
const _MARSH_RZ := 560.0

## Eastern shore.
const _COAST_START := 1480.0
const _DUNE_X := 1820.0
const _SHORE_X := 1960.0
const _CLIFF_TOP := 22.0

## River cross section: full bed under _CHANNEL, banks up to _BANK, flood plain
## up to _VALLEY.
const _RIVER_CHANNEL := 7.0
const _RIVER_BANK := 17.0
const _RIVER_VALLEY := 62.0
const _RIVER_DEPTH := 3.2

## Parcel size of the bocage, in metres. Fields are cellular, never a gradient.
const _PARCEL := 96.0

## Noise seeds (added to the world seed).
const _S_WARP := 101
const _S_BASE := 211
const _S_DETAIL := 337
const _S_RIDGE := 449
const _S_MARSH := 557
const _S_CLIFF := 661
const _S_PARCEL := 773
const _S_COLOR := 887
const _S_BED := 941

# --- Public state --------------------------------------------------------------

var world_seed: int = 0
var layout: Layout = null

# --- Private, built once in _init, read only afterwards ------------------------

## River segments, 6 floats each: x1, z1, x2, z2, bed1, bed2.
var _river_seg := PackedFloat32Array()
var _river_cells: Array[PackedInt32Array] = []
## Road segments, 6 floats each: x1, z1, x2, z2, height1, height2.
var _road_seg := PackedFloat32Array()
var _road_cells: Array[PackedInt32Array] = []
## Bridge footprints, 3 floats each: x, z, radius. Roads do not flatten there.
var _bridges := PackedFloat32Array()
## 1 when the 64 m tile is close to a village, a farm or the church town.
var _settle := PackedByteArray()


func _init(new_layout: Layout) -> void:
	layout = new_layout
	world_seed = new_layout.world_seed if new_layout != null else 0
	_build_river_spine()
	_build_bridges()
	_build_road_spine()
	_build_settlement_mask()

# --- Main query ----------------------------------------------------------------

## Terrain height in metres. Deterministic, thread safe, no mutating cache.
func height_at(x: float, z: float) -> float:
	var river := _river_query(x, z)
	var h := _relief(x, z, river)
	# Safety net: nothing is allowed to dam the river. Whatever a road or a
	# village would like to do, the channel itself keeps its carved bed, so the
	# water always has somewhere to flow even when a lane fords the stream.
	var open := 1.0 - _channel_protection(river.x)
	if open <= 0.0:
		return h
	# Roads press a flat ribbon into the slope, except where a bridge spans the
	# river: there the bed must stay open under the deck.
	var road := _road_sample(x, z)
	if road.x > 0.0:
		h = lerpf(h, road.y, road.x * open)
	# Site footprints win over roads, so a street inside a village follows the
	# village ground. Before bake_sites() the weight is 0 and nothing happens.
	if layout != null:
		var flat := layout.site_flatten(x, z)
		if flat.x > 0.0:
			h = lerpf(h, flat.y, flat.x * open)
	return h


## 1 inside the river channel, 0 past the top of the banks. Used to protect the
## bed from every flattening pass.
func _channel_protection(river_distance: float) -> float:
	if river_distance >= _RIVER_BANK:
		return 0.0
	return smoothstep(0.0, 1.0, (_RIVER_BANK - river_distance) / (_RIVER_BANK - _RIVER_CHANNEL))


## Surface normal from finite differences.
func normal_at(x: float, z: float) -> Vector3:
	var e := 0.8
	var hl := height_at(x - e, z)
	var hr := height_at(x + e, z)
	var hb := height_at(x, z - e)
	var hf := height_at(x, z + e)
	return Vector3(hl - hr, 2.0 * e, hb - hf).normalized()


## Slope in radians, 0 = flat.
func slope_at(x: float, z: float) -> float:
	return acos(clampf(normal_at(x, z).y, -1.0, 1.0))


func is_water(x: float, z: float) -> bool:
	return height_at(x, z) < WATER_LEVEL


func biome_at(x: float, z: float) -> int:
	var h := height_at(x, z)
	if h < WATER_LEVEL:
		return B_WATER
	if layout != null:
		var flat := layout.site_flatten(x, z)
		if flat.x > 0.55:
			return B_VILLAGE
	if _road_sample(x, z).x > 0.45:
		return B_ROAD
	if _is_cliff_face(x, z):
		return B_ROCK
	if _is_sand(x, z, h):
		return B_ROCK
	if _marsh_amount(x, z) > 0.45 and h < WATER_LEVEL + 3.0:
		return B_MARSH
	return _parcel_kind(x, z)


## Surface name for footsteps: "grass","dirt","stone","wood","water".
func surface_at(x: float, z: float) -> String:
	var biome := biome_at(x, z)
	match biome:
		B_WATER:
			return "water"
		B_MARSH:
			return "water" if height_at(x, z) < WATER_LEVEL + 0.7 else "dirt"
		B_ROAD:
			return "dirt"
		B_VILLAGE:
			return "stone"
		B_ROCK:
			# The shingle of the beach walks like dirt, the cliff like stone.
			return "stone" if _is_cliff_face(x, z) else "dirt"
		_:
			return "grass"


## Vertex colour of the terrain at this point (already linear, 0.05..0.38).
func color_at(x: float, z: float) -> Color:
	var biome := biome_at(x, z)
	var n := _value_noise(x * 0.011, z * 0.011, world_seed + _S_COLOR)
	var base := Palette.GRASS_SUMMER
	match biome:
		B_FIELD:
			# Pulled down from the raw WHEAT tone, which sits near the top of the
			# safe albedo band. At full strength the bare soil between the stalks
			# glares under the noon sun and the standing wheat reads as black
			# spikes against it: the ground has to stay darker than the crop.
			base = Palette.WHEAT.lerp(Palette.DIRT, 0.34 + n * 0.26)
		B_MEADOW:
			base = Palette.GRASS_SUMMER.lerp(Palette.GRASS_DRY, n * 0.55)
		B_ORCHARD:
			base = Palette.GRASS_SUMMER.lerp(Palette.LEAF_LIGHT, 0.25 + n * 0.2)
		B_FOREST:
			base = Palette.LEAF_DARK.lerp(Palette.DIRT, 0.35 + n * 0.3)
		B_MARSH:
			base = Palette.MUD.lerp(Palette.GRASS_DRY, n * 0.4)
		B_ROAD:
			base = Palette.ROAD.lerp(Palette.DIRT, n * 0.6)
		B_VILLAGE:
			# A village green is trodden earth AND surviving grass in patches.
			# Without the grass mix the whole flattened footprint reads as one
			# uniform beige plaza, which is the single largest surface in every
			# village shot and the one that most makes it look unfinished.
			base = Palette.DIRT.lerp(Palette.STONE, 0.25 + n * 0.30)
			base = base.lerp(Palette.GRASS_DRY, clampf(n * 1.7 - 0.38, 0.0, 0.58))
		B_WATER:
			base = Palette.WATER.lerp(Palette.MUD, n * 0.5)
		B_ROCK:
			if _is_cliff_face(x, z):
				base = Palette.STONE_DARK.lerp(Palette.STONE, n)
			else:
				base = Palette.GRASS_DRY.lerp(Palette.STONE, 0.45 + n * 0.3)
		_:
			base = Palette.GRASS_SUMMER
	# Steep ground shows earth and rock instead of grass. The gradient is read
	# from the natural relief only (two extra samples), which keeps the cost of
	# this call bounded.
	if biome != B_WATER and biome != B_VILLAGE and biome != B_ROAD:
		var e := 2.5
		var h0 := _natural_height(x, z)
		var gx := _natural_height(x + e, z) - h0
		var gz := _natural_height(x, z + e) - h0
		var steep := clampf(sqrt(gx * gx + gz * gz) / e * 1.7 - 0.28, 0.0, 1.0)
		if steep > 0.0:
			base = base.lerp(Palette.DIRT.lerp(Palette.STONE_DARK, 0.45), steep * 0.75)
	return base


## Fills every Site.ground of the layout. Called once by GameWorld.setup().
##
## INITIALISATION ORDER, the trap of this module: while this runs, no site has a
## ground yet, so `Layout.site_flatten()` returns a zero weight and `height_at()`
## degrades to the natural relief. We therefore sample `_natural_height()`
## directly, which is the UNFLATTENED terrain, and average it over two rings
## around the centre. The result is the height the village will be levelled to.
## Calling `height_at()` here would be self referential.
func bake_sites() -> void:
	if layout == null:
		return
	for s: Layout.Site in layout.sites:
		if s.kind == Layout.SITE_BRIDGE:
			# A bridge deck rides above the water, and never flattens the bed.
			s.set_ground(WATER_LEVEL + 3.4)
			continue
		var total := _natural_height(s.center.x, s.center.y) * 3.0
		var weight := 3.0
		for ring in 2:
			var r := s.radius * (0.45 if ring == 0 else 0.85)
			var w := 2.0 if ring == 0 else 1.0
			for k in 8:
				var a := TAU * float(k) / 8.0 + float(ring) * 0.39
				total += _natural_height(s.center.x + cos(a) * r, s.center.y + sin(a) * r) * w
				weight += w
		var ground := total / weight
		# No settlement is ever built below the water table.
		ground = maxf(ground, WATER_LEVEL + 1.2)
		s.set_ground(ground)


## True when the position is inside the playable square minus a 32 m margin.
static func in_bounds(x: float, z: float) -> bool:
	return absf(x) <= HALF - 32.0 and absf(z) <= HALF - 32.0


## Clamps a position back inside the playable area.
static func clamp_to_bounds(pos: Vector3) -> Vector3:
	var limit := HALF - 32.0
	return Vector3(clampf(pos.x, -limit, limit), pos.y, clampf(pos.z, -limit, limit))

# --- Natural relief ------------------------------------------------------------

## The terrain before roads and villages flatten it. Everything that shapes the
## pocket lives here, in this order: base bocage, northern ridge, south western
## marshes, eastern shore, river carving.
func _natural_height(x: float, z: float) -> float:
	return _relief(x, z, _river_query(x, z))


## Same thing with the river lookup already done, so `height_at()` pays for it
## only once.
func _relief(x: float, z: float, river: Vector2) -> float:
	var h := _base_relief(x, z)
	h += _ridge_add(x, z, river.x)
	h = _marsh_mix(h, x, z)
	h = _coast_mix(h, x, z)
	h = _river_carve(h, river)
	return h


## Rolling bocage: a domain warped fractal, plus a small high frequency layer.
func _base_relief(x: float, z: float) -> float:
	var warp := (_value_noise(x * _WARP_FREQ, z * _WARP_FREQ, world_seed + _S_WARP) - 0.5) * _WARP_AMOUNT
	var h := _BASE_LEVEL
	h += _fbm(x + warp, z - warp, _BASE_FREQ, 4, world_seed + _S_BASE) * _BASE_AMPLITUDE
	h += (_fbm(x, z, _DETAIL_FREQ, 2, world_seed + _S_DETAIL) - 0.5) * 4.6
	return h


## Wooded ridge closing the north of the pocket. It dips where the river gorge
## cuts through it, so the water is not trapped behind a wall.
func _ridge_add(x: float, z: float, river_distance: float) -> float:
	var t := smoothstep(_RIDGE_START, _RIDGE_TOP, z)
	if t <= 0.0:
		return 0.0
	var lumps := 0.65 + 0.7 * _value_noise(x * 0.0012, z * 0.0012, world_seed + _S_RIDGE)
	# The gorge fade must stay inside the range where `_river_query()` is exact
	# (_RIVER_VALLEY), otherwise it reads a distance that depends on the
	# acceleration grid and the ridge grows a hard step at a cell boundary.
	var gorge := 0.35 + 0.65 * smoothstep(25.0, _RIVER_VALLEY, river_distance)
	return _RIDGE_HEIGHT * t * lumps * gorge


## 0 outside the marshes, 1 in the middle of them.
func _marsh_amount(x: float, z: float) -> float:
	var dx := (x - _MARSH_X) / _MARSH_RX
	var dz := (z - _MARSH_Z) / _MARSH_RZ
	var d := sqrt(dx * dx + dz * dz)
	# Early out before touching the noise: the wobble below can only move `d` by
	# 0.17, so anything past 1.35 is dry land whatever the noise says. This skips
	# one octave over most of the map, and the hot path is worth it.
	if d > 1.35:
		return 0.0
	d += (_value_noise(x * 0.0038, z * 0.0038, world_seed + _S_MARSH) - 0.5) * 0.34
	return 1.0 - smoothstep(0.55, 1.0, d)


## Pulls the ground down to the water table, with pools slightly below it.
func _marsh_mix(h: float, x: float, z: float) -> float:
	var amount := _marsh_amount(x, z)
	if amount <= 0.0:
		return h
	var pools := (_value_noise(x * 0.022, z * 0.022, world_seed + _S_MARSH + 7) - 0.5) * 1.5
	var level := WATER_LEVEL + 0.35 + pools
	return lerpf(h, level, smoothstep(0.0, 1.0, amount))


## 1 where the eastern shore is a cliff, 0 where it is a beach.
func _cliff_band(z: float) -> float:
	var b1 := 1.0 - smoothstep(0.0, 1.0, absf(z + 520.0) / 430.0)
	var b2 := 1.0 - smoothstep(0.0, 1.0, absf(z - 880.0) / 300.0)
	return clampf(maxf(b1, b2), 0.0, 1.0)


## Where the cliff face starts, in x, for a given z.
func _cliff_edge(z: float) -> float:
	return 1876.0 + (_value_noise(z * 0.0085, 0.0, world_seed + _S_CLIFF) - 0.5) * 70.0


## Eastern shore: a long descent to the sand, or a plateau ending in a wall of
## rock. Untouched inland.
func _coast_mix(h: float, x: float, z: float) -> float:
	if x < _COAST_START:
		return h
	var cliffness := _cliff_band(z)
	# Beach profile: bocage, then dunes, then the wet sand, then the sea.
	var beach := 0.0
	if x < _DUNE_X:
		beach = lerpf(h, 4.5, smoothstep(_COAST_START, _DUNE_X, x))
	elif x < _SHORE_X:
		beach = lerpf(4.5, WATER_LEVEL - 0.3, smoothstep(_DUNE_X, _SHORE_X, x))
	else:
		beach = lerpf(WATER_LEVEL - 0.3, -2.4, smoothstep(_SHORE_X, HALF + 40.0, x))
	if cliffness <= 0.001:
		return beach
	# Cliff profile: the plateau keeps its height, then falls almost vertically.
	var plateau := lerpf(h, maxf(h, _CLIFF_TOP), smoothstep(_COAST_START, 1800.0, x))
	var cliff := plateau
	var edge := _cliff_edge(z)
	if x > edge:
		cliff = lerpf(plateau, -1.6, smoothstep(0.0, 34.0, x - edge))
	return lerpf(beach, cliff, cliffness)


## Carves the river: a flood plain, then banks, then the bed itself, always
## under WATER_LEVEL so the water plane has somewhere to sit.
func _river_carve(h: float, river: Vector2) -> float:
	var d := river.x
	if d >= _RIVER_VALLEY:
		return h
	var bed := river.y
	var out := h
	var valley := smoothstep(0.0, 1.0, (_RIVER_VALLEY - d) / (_RIVER_VALLEY - _RIVER_BANK))
	out = lerpf(out, minf(out, bed + 5.5), valley)
	if d < _RIVER_BANK:
		var channel := smoothstep(0.0, 1.0, (_RIVER_BANK - d) / (_RIVER_BANK - _RIVER_CHANNEL))
		out = lerpf(out, bed, channel)
	return out

# --- Rivers --------------------------------------------------------------------

## Densifies the layout polylines and stores a bed height per vertex. The bed is
## always below WATER_LEVEL, with a slow downstream drift so the water reads as
## flowing rather than as a canal.
func _build_river_spine() -> void:
	_river_cells = _new_cells()
	_river_seg = PackedFloat32Array()
	if layout == null:
		return
	for line_index in layout.rivers.size():
		var pts := _densify(layout.rivers[line_index], 14.0)
		if pts.size() < 2:
			continue
		var depth := _RIVER_DEPTH if line_index == 0 else 2.1
		for i in pts.size() - 1:
			var a := pts[i]
			var b := pts[i + 1]
			var index := _river_seg.size() / 6
			_river_seg.append(a.x)
			_river_seg.append(a.y)
			_river_seg.append(b.x)
			_river_seg.append(b.y)
			_river_seg.append(_bed_height(a, depth))
			_river_seg.append(_bed_height(b, depth))
			_bin(_river_cells, index, a, b, _RIVER_VALLEY)


func _bed_height(p: Vector2, depth: float) -> float:
	var wobble := (_value_noise(p.x * 0.006, p.y * 0.006, world_seed + _S_BED) - 0.5) * 0.7
	return WATER_LEVEL - depth + wobble


## Distance to the river network and interpolated bed height at that point.
## Returns Vector2(distance, bed_height).
##
## The distance is only EXACT below `_RIVER_VALLEY`, because that is the pad the
## segments were binned with. Past that limit the function returns 1e9 on
## purpose: a caller that compared a longer distance against a threshold would
## otherwise read a value that depends on the acceleration grid and would grow a
## visible step at a cell boundary.
func _river_query(x: float, z: float) -> Vector2:
	var ids := _river_cells[_cell_index(x, z)]
	if ids.is_empty():
		return Vector2(1.0e9, WATER_LEVEL)
	var best_d2 := 1.0e18
	var bed := WATER_LEVEL
	for i: int in ids:
		var b := i * 6
		var x1 := _river_seg[b]
		var z1 := _river_seg[b + 1]
		var x2 := _river_seg[b + 2]
		var z2 := _river_seg[b + 3]
		var vx := x2 - x1
		var vz := z2 - z1
		var wx := x - x1
		var wz := z - z1
		var len2 := vx * vx + vz * vz
		var t := 0.0
		if len2 > 0.000001:
			t = clampf((wx * vx + wz * vz) / len2, 0.0, 1.0)
		var dx := wx - vx * t
		var dz := wz - vz * t
		var d2 := dx * dx + dz * dz
		if d2 < best_d2:
			best_d2 = d2
			bed = lerpf(_river_seg[b + 4], _river_seg[b + 5], t)
	if best_d2 >= _RIVER_VALLEY * _RIVER_VALLEY:
		return Vector2(1.0e9, WATER_LEVEL)
	return Vector2(sqrt(best_d2), bed)

# --- Roads ---------------------------------------------------------------------

## Bakes a height along every road polyline. The height is the natural relief
## under the centreline, smoothed along the road so the grade stays gentle, and
## clamped above the water table so a road never dives into the river. Because
## the height travels with the segment, the hot path never evaluates the noise
## twice and the road stays flat across its width.
func _build_road_spine() -> void:
	_road_cells = _new_cells()
	_road_seg = PackedFloat32Array()
	if layout == null:
		return
	for line: PackedVector2Array in layout.roads:
		var pts := _densify(line, 13.0)
		var count := pts.size()
		if count < 2:
			continue
		var hs := PackedFloat32Array()
		hs.resize(count)
		for i in count:
			hs[i] = maxf(_natural_height(pts[i].x, pts[i].y), WATER_LEVEL + 1.2)
		for smoothing in 3:
			var copy := hs.duplicate()
			for i in range(1, count - 1):
				hs[i] = copy[i - 1] * 0.25 + copy[i] * 0.5 + copy[i + 1] * 0.25
		for i in count - 1:
			var index := _road_seg.size() / 6
			_road_seg.append(pts[i].x)
			_road_seg.append(pts[i].y)
			_road_seg.append(pts[i + 1].x)
			_road_seg.append(pts[i + 1].y)
			_road_seg.append(hs[i])
			_road_seg.append(hs[i + 1])
			_bin(_road_cells, index, pts[i], pts[i + 1], Layout.ROAD_HALF_WIDTH + Layout.ROAD_FADE)


## Flattening weight and target height of the nearest road.
## Returns Vector2(weight, height); the weight is 0 when there is no road, and
## also inside a bridge footprint, where the river bed must stay open.
func _road_sample(x: float, z: float) -> Vector2:
	var ids := _road_cells[_cell_index(x, z)]
	if ids.is_empty():
		return Vector2.ZERO
	var outer := Layout.ROAD_HALF_WIDTH + Layout.ROAD_FADE
	var limit := outer * outer
	var best_d2 := limit
	var height := 0.0
	for i: int in ids:
		var b := i * 6
		var x1 := _road_seg[b]
		var z1 := _road_seg[b + 1]
		var x2 := _road_seg[b + 2]
		var z2 := _road_seg[b + 3]
		var vx := x2 - x1
		var vz := z2 - z1
		var wx := x - x1
		var wz := z - z1
		var len2 := vx * vx + vz * vz
		var t := 0.0
		if len2 > 0.000001:
			t = clampf((wx * vx + wz * vz) / len2, 0.0, 1.0)
		var dx := wx - vx * t
		var dz := wz - vz * t
		var d2 := dx * dx + dz * dz
		if d2 < best_d2:
			best_d2 = d2
			height = lerpf(_road_seg[b + 4], _road_seg[b + 5], t)
	if best_d2 >= limit:
		return Vector2.ZERO
	var d := sqrt(best_d2)
	var weight := 1.0
	if d > Layout.ROAD_HALF_WIDTH:
		weight = smoothstep(0.0, 1.0, (outer - d) / Layout.ROAD_FADE)
	weight *= 1.0 - _bridge_mask(x, z)
	if weight <= 0.0:
		return Vector2.ZERO
	return Vector2(weight, height)


func _build_bridges() -> void:
	_bridges = PackedFloat32Array()
	if layout == null:
		return
	for s: Layout.Site in layout.sites:
		if s.kind != Layout.SITE_BRIDGE:
			continue
		_bridges.append(s.center.x)
		_bridges.append(s.center.y)
		_bridges.append(s.radius)


## 1 inside a bridge footprint, fading to 0 a little further out. There are only
## a couple of bridges in the pocket, so a flat loop is cheaper than a grid.
func _bridge_mask(x: float, z: float) -> float:
	var best := 0.0
	var count := _bridges.size() / 3
	for i in count:
		var b := i * 3
		var dx := x - _bridges[b]
		var dz := z - _bridges[b + 1]
		var r := _bridges[b + 2]
		var d := sqrt(dx * dx + dz * dz)
		if d >= r + 26.0:
			continue
		var m := 1.0 if d <= r else smoothstep(0.0, 1.0, (r + 26.0 - d) / 26.0)
		if m > best:
			best = m
	return best

# --- Bocage parcels -------------------------------------------------------------

## Cellular partition of the countryside. Each Worley cell is one field, with a
## single crisp kind, which is what gives the bocage its hedged parcels instead
## of a blurry gradient.
func _parcel_kind(x: float, z: float) -> int:
	var gx := floori(x / _PARCEL)
	var gz := floori(z / _PARCEL)
	var best_d2 := 1.0e18
	var owner_x := gx
	var owner_z := gz
	for oz in range(-1, 2):
		for ox in range(-1, 2):
			var cx := gx + ox
			var cz := gz + oz
			var jx := (float(cx) + _hash01(cx, cz, world_seed + _S_PARCEL)) * _PARCEL
			var jz := (float(cz) + _hash01(cx, cz, world_seed + _S_PARCEL + 31)) * _PARCEL
			var dx := jx - x
			var dz := jz - z
			var d2 := dx * dx + dz * dz
			if d2 < best_d2:
				best_d2 = d2
				owner_x = cx
				owner_z = cz
	var roll := _hash01(owner_x, owner_z, world_seed + _S_PARCEL + 97)
	# The ridge and its northern slopes are wooded.
	var forest_bias := smoothstep(_RIDGE_START + 260.0, _RIDGE_TOP, z) * 0.72 + 0.16
	if roll < forest_bias:
		return B_FOREST
	# Orchards only make sense next to a farm or a village.
	if _settle_at(x, z) > 0 and roll < forest_bias + 0.06:
		return B_ORCHARD
	if roll < forest_bias + 0.55:
		return B_FIELD
	return B_MEADOW


## 1 when the 64 m tile is within _SETTLE_RANGE of a farm, a village or the
## church town. Precomputed so the parcel test stays a single array read.
func _build_settlement_mask() -> void:
	_settle = PackedByteArray()
	_settle.resize(_SETTLE_GRID * _SETTLE_GRID)
	_settle.fill(0)
	if layout == null:
		return
	for s: Layout.Site in layout.sites:
		if s.kind != Layout.SITE_VILLAGE and s.kind != Layout.SITE_FARM \
				and s.kind != Layout.SITE_CHURCH_TOWN:
			continue
		var reach := s.radius + _SETTLE_RANGE
		var x0 := _settle_axis(s.center.x - reach)
		var x1 := _settle_axis(s.center.x + reach)
		var z0 := _settle_axis(s.center.y - reach)
		var z1 := _settle_axis(s.center.y + reach)
		for cz in range(z0, z1 + 1):
			for cx in range(x0, x1 + 1):
				_settle[cz * _SETTLE_GRID + cx] = 1


func _settle_at(x: float, z: float) -> int:
	return _settle[_settle_axis(z) * _SETTLE_GRID + _settle_axis(x)]


static func _settle_axis(v: float) -> int:
	return clampi(floori((v + HALF) / _SETTLE_CELL), 0, _SETTLE_GRID - 1)

# --- Shore helpers ---------------------------------------------------------------

## True on the rock face of the eastern cliffs (very steep, B_ROCK).
func _is_cliff_face(x: float, z: float) -> bool:
	if x < 1700.0:
		return false
	if _cliff_band(z) <= 0.5:
		return false
	return x > _cliff_edge(z) - 14.0


## True on the sand and shingle of the eastern beach.
func _is_sand(x: float, z: float, h: float) -> bool:
	return x > 1700.0 and _cliff_band(z) <= 0.5 and h < 5.0

# --- Acceleration grid ------------------------------------------------------------

static func _new_cells() -> Array[PackedInt32Array]:
	var cells: Array[PackedInt32Array] = []
	cells.resize(_GRID * _GRID)
	for i in _GRID * _GRID:
		cells[i] = PackedInt32Array()
	return cells


static func _bin(cells: Array[PackedInt32Array], index: int, a: Vector2, b: Vector2,
		pad: float) -> void:
	var x0 := _cell_axis(minf(a.x, b.x) - pad)
	var x1 := _cell_axis(maxf(a.x, b.x) + pad)
	var z0 := _cell_axis(minf(a.y, b.y) - pad)
	var z1 := _cell_axis(maxf(a.y, b.y) + pad)
	for cz in range(z0, z1 + 1):
		for cx in range(x0, x1 + 1):
			cells[cz * _GRID + cx].append(index)


static func _cell_axis(v: float) -> int:
	return clampi(floori((v + HALF) / _CELL), 0, _GRID - 1)


static func _cell_index(x: float, z: float) -> int:
	return _cell_axis(z) * _GRID + _cell_axis(x)


static func _densify(line: PackedVector2Array, step: float) -> PackedVector2Array:
	if line.size() < 2:
		return line
	var out := PackedVector2Array()
	out.append(line[0])
	for i in line.size() - 1:
		var a := line[i]
		var b := line[i + 1]
		var span := a.distance_to(b)
		var steps := maxi(1, int(ceil(span / step)))
		for k in range(1, steps + 1):
			out.append(a.lerp(b, float(k) / float(steps)))
	return out

# --- Noise -----------------------------------------------------------------------

## Deterministic integer hash in 0..1. The whole terrain rests on this function,
## so it is written inline in _value_noise as well: the duplication is on purpose
## and buys a measurable amount of speed on the generation threads.
static func _hash01(ix: int, iz: int, s: int) -> float:
	var h := (ix * 73856093) ^ (iz * 19349663) ^ (s * 83492791)
	h &= 0x7FFFFFFF
	h = (h ^ (h >> 13)) * 1274126177
	h &= 0x7FFFFFFF
	h = h ^ (h >> 15)
	return float(h & 0xFFFFFF) / 16777215.0


## Smoothly interpolated value noise in 0..1. Coordinates are already scaled.
static func _value_noise(x: float, z: float, s: int) -> float:
	var xi := floori(x)
	var zi := floori(z)
	var xf := x - float(xi)
	var zf := z - float(zi)
	var u := xf * xf * (3.0 - 2.0 * xf)
	var v := zf * zf * (3.0 - 2.0 * zf)
	var s0 := s * 83492791
	var h00 := ((xi * 73856093) ^ (zi * 19349663) ^ s0) & 0x7FFFFFFF
	h00 = ((h00 ^ (h00 >> 13)) * 1274126177) & 0x7FFFFFFF
	var a := float(((h00 ^ (h00 >> 15))) & 0xFFFFFF) / 16777215.0
	var h10 := (((xi + 1) * 73856093) ^ (zi * 19349663) ^ s0) & 0x7FFFFFFF
	h10 = ((h10 ^ (h10 >> 13)) * 1274126177) & 0x7FFFFFFF
	var b := float(((h10 ^ (h10 >> 15))) & 0xFFFFFF) / 16777215.0
	var h01 := ((xi * 73856093) ^ ((zi + 1) * 19349663) ^ s0) & 0x7FFFFFFF
	h01 = ((h01 ^ (h01 >> 13)) * 1274126177) & 0x7FFFFFFF
	var c := float(((h01 ^ (h01 >> 15))) & 0xFFFFFF) / 16777215.0
	var h11 := (((xi + 1) * 73856093) ^ ((zi + 1) * 19349663) ^ s0) & 0x7FFFFFFF
	h11 = ((h11 ^ (h11 >> 13)) * 1274126177) & 0x7FFFFFFF
	var d := float(((h11 ^ (h11 >> 15))) & 0xFFFFFF) / 16777215.0
	var top := a + (b - a) * u
	var bottom := c + (d - c) * u
	return top + (bottom - top) * v


## Fractal value noise in 0..1, lacunarity 2, gain 0.5.
static func _fbm(x: float, z: float, freq: float, octaves: int, s: int) -> float:
	var total := 0.0
	var norm := 0.0
	var amp := 1.0
	var f := freq
	for i in octaves:
		total += amp * _value_noise(x * f, z * f, s + i * 7919)
		norm += amp
		amp *= 0.5
		f *= 2.0
	if norm <= 0.0:
		return 0.0
	return total / norm
