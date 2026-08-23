## Decides what grows where on the Normandy map, tile by tile.
##
## Scatter is a PURE module. It owns no mutable state, never touches the scene
## tree, never reads a global random source and never allocates a node: the
## terrain streamer calls `for_tile()` from a worker thread, so anything else
## would be a data race waiting to happen.
##
## Determinism comes from two sources, both derived from
## `(world_seed, tile x, tile z)`:
##
## - a local `RandomNumberGenerator` for the "how many of these in this tile"
##   decisions, whose sequence only depends on the tile;
## - an integer hash for anything anchored on a WORLD grid (wheat rows, orchard
##   quincunx, hedgerows), so that a prop sitting exactly on a tile border is
##   placed identically no matter which tile computes it.
##
## Every placement grid uses a step that divides 64 exactly. A cell therefore
## never straddles two tiles, which is what guarantees "no duplicate, no gap"
## along the seams.
##
## About `Instance.tint`: it is a MULTIPLICATIVE colour centred on white, meant
## to be fed to `MultiMesh.set_instance_color()` on top of the shared material
## albedo. It is never an absolute albedo, because a prop mesh carries several
## materials (a trunk and a canopy) and an absolute colour would paint the
## trunk green. Values stay inside 0.55 .. 1.35 per channel.
class_name Scatter
extends RefCounted

# --- Prop kinds ------------------------------------------------------------

const P_TREE_OAK := 0
const P_TREE_PINE := 1
const P_TREE_APPLE := 2
const P_BUSH := 3
const P_HEDGE := 4          # segment de bocage
const P_ROCK := 5
const P_GRASS_TUFT := 6
const P_WHEAT := 7
const P_FENCE := 8
const P_WRECK := 9          # epave de vehicule
const P_CRATER := 10
const P_SANDBAG := 11
const P_POLE := 12          # poteau telegraphique
const P_HAYSTACK := 13
const KIND_COUNT := 14


## One placed prop. Plain data, safe to hand from a worker to the main thread.
class Instance extends RefCounted:
	var kind: int = 0
	var position: Vector3 = Vector3.ZERO
	var rotation: float = 0.0      # radians around Y
	var scale: float = 1.0
	var tint: Color = Color(1.0, 1.0, 1.0, 1.0)


# --- Tuning ----------------------------------------------------------------

const TILE := 64.0
## Hard ceiling for one tile. Above roughly this the streaming budget collapses
## (one MultiMesh rebuild per tile plus the collision bodies of the big props).
const MAX_INSTANCES := 1800

## Placement grid steps, all exact divisors of TILE.
const STEP_WHEAT := 1.5        # 42 x 42 cells
const STEP_REED := 2.0         # marsh reeds, same density as wheat
const STEP_TUFT := 3.2         # 20 x 20 cells
const STEP_TREE := 4.0         # 16 x 16 cells
const STEP_BUSH := 3.2
const STEP_ROCK := 4.0
const STEP_HEDGE := 4.0        # matches the 4 m hedge segment mesh
const STEP_FENCE := 3.2        # matches the 3.2 m fence segment mesh
const ORCHARD_SPACING := 8.0   # rows every 8 m, staggered by half a row

## Acceptance probabilities per family, before the terrain rejection tests.
const DENSITY_WHEAT := 0.86
const DENSITY_REED := 0.62
const DENSITY_TUFT_MEADOW := 0.52
const DENSITY_TUFT_FIELD := 0.10
const DENSITY_FOREST_TREE := 0.62
const DENSITY_FOREST_BUSH := 0.34
const DENSITY_MEADOW_TREE := 0.045
const DENSITY_MEADOW_BUSH := 0.08
const DENSITY_ROCK := 0.40

## Slope limits, in radians.
const SLOPE_TREE := 0.60
const SLOPE_HEDGE := 0.55
const SLOPE_ROCK := 1.10
const SLOPE_GROUND_COVER := 0.85
const SLOPE_FLAT_PROP := 0.26    # wrecks, haystacks, sandbags, poles
const SLOPE_CRATER := 0.38

## Clearance above the water line before anything is allowed to grow.
const DRY_MARGIN := 0.05
const MARSH_MARGIN := 0.02

## Telegraph poles: one every 40 m along the road, offset off the verge.
const POLE_SPACING := 40.0
const POLE_VERGE := 2.6

## Fallback parcel grid used when a wide meadow has no biome border to hug.
const PARCEL_SIZE := 48.0
const PARCEL_GAP_CHANCE := 0.13

## Coarse biome survey resolution used to skip whole passes.
const SURVEY_RES := 8

const _MASK31 := 0x7FFFFFFF


# --- Public API ------------------------------------------------------------

## Every prop instance for one 64 m tile. Deterministic on (seed, tx, tz).
static func for_tile(hf: Heightfield, tx: int, tz: int) -> Array[Instance]:
	var out: Array[Instance] = []
	if hf == null:
		push_error("Scatter.for_tile called without a Heightfield")
		return out

	var base_x: float = float(tx) * TILE
	var base_z: float = float(tz) * TILE
	# Cheap whole tile rejection: fully outside the playable square.
	if base_x + TILE < -Heightfield.HALF or base_x > Heightfield.HALF:
		return out
	if base_z + TILE < -Heightfield.HALF or base_z > Heightfield.HALF:
		return out

	var world_seed: int = int(hf.world_seed)
	var rng := RandomNumberGenerator.new()
	rng.seed = _tile_seed(world_seed, tx, tz)

	var survey: PackedInt32Array = _survey(hf, base_x, base_z)

	# Order matters. Rare, hand placed props come first so that the instance
	# budget, when it bites, only eats into the wheat and grass filler.
	_pass_poles(hf, rng, base_x, base_z, out)
	_pass_village(hf, rng, base_x, base_z, survey, out)
	_pass_battle_scars(hf, rng, base_x, base_z, out)

	if survey[Heightfield.B_ROCK] > 0:
		_pass_rocks(hf, world_seed, base_x, base_z, out)
	if survey[Heightfield.B_ORCHARD] > 0:
		_pass_orchard(hf, world_seed, base_x, base_z, out)
		_pass_border(hf, world_seed, base_x, base_z, Heightfield.B_ORCHARD,
				P_FENCE, STEP_FENCE, out)
	if survey[Heightfield.B_MEADOW] > 0:
		_pass_hedgerows(hf, world_seed, base_x, base_z, survey, out)
	if survey[Heightfield.B_FOREST] > 0:
		_pass_forest(hf, world_seed, base_x, base_z, out)
	if survey[Heightfield.B_FIELD] > 0:
		_pass_haystacks(hf, rng, base_x, base_z, out)
	if survey[Heightfield.B_MEADOW] > 0:
		_pass_meadow_trees(hf, world_seed, base_x, base_z, out)
	if survey[Heightfield.B_MARSH] > 0:
		_pass_marsh(hf, world_seed, base_x, base_z, out)

	# Ground cover last: it is the filler the budget is allowed to trim.
	_pass_tufts(hf, world_seed, base_x, base_z, survey, out)
	if survey[Heightfield.B_FIELD] > 0:
		_pass_wheat(hf, world_seed, base_x, base_z, out)

	return out


## True when the prop kind should get a collision body (trees, rocks, hedges).
static func has_collision(kind: int) -> bool:
	match kind:
		P_TREE_OAK, P_TREE_PINE, P_TREE_APPLE, P_HEDGE, P_ROCK, P_FENCE, \
		P_WRECK, P_POLE, P_HAYSTACK, P_SANDBAG:
			return true
		_:
			# Bushes, grass, wheat and craters are walked straight through.
			return false


## Collision cylinder radius and height for a colliding kind, Vector2(r, h).
## Returns Vector2.ZERO for a kind that has no body, so a caller that forgets
## to test `has_collision` builds nothing instead of crashing.
static func collision_size(kind: int, prop_scale: float) -> Vector2:
	var s: float = maxf(prop_scale, 0.05)
	match kind:
		P_TREE_OAK:
			return Vector2(0.46 * s, 5.9 * s)
		P_TREE_PINE:
			return Vector2(0.34 * s, 8.6 * s)
		P_TREE_APPLE:
			return Vector2(0.28 * s, 2.6 * s)
		P_HEDGE:
			# The hedge mesh is a 4 m slab; the body is a fat cylinder sized to
			# stop a running soldier without eating the whole verge.
			return Vector2(0.90 * s, 1.95 * s)
		P_ROCK:
			return Vector2(0.72 * s, 0.85 * s)
		P_FENCE:
			return Vector2(0.16 * s, 1.25 * s)
		P_WRECK:
			return Vector2(2.30 * s, 2.10 * s)
		P_POLE:
			return Vector2(0.22 * s, 7.6 * s)
		P_HAYSTACK:
			return Vector2(1.80 * s, 2.50 * s)
		P_SANDBAG:
			return Vector2(1.05 * s, 1.00 * s)
		_:
			return Vector2.ZERO


## Whether the kind is drawn as a MultiMesh (true) or a full node (false).
##
## Rule of thumb: anything that appears by the hundred is batched, anything
## rare enough to deserve a proper collider and a bit of hand placed care is a
## real node. Fences are batched (an orchard has a lot of them) even though
## they collide: the streamer builds their bodies separately.
static func is_batched(kind: int) -> bool:
	match kind:
		P_TREE_OAK, P_TREE_PINE, P_TREE_APPLE, P_BUSH, P_HEDGE, P_ROCK, \
		P_GRASS_TUFT, P_WHEAT, P_FENCE:
			return true
		_:
			# P_WRECK, P_CRATER, P_SANDBAG, P_POLE, P_HAYSTACK.
			return false


# --- Passes ----------------------------------------------------------------

## Telegraph poles along the road verge, every POLE_SPACING metres.
## Walks the layout polylines rather than the biome map: the spacing has to be
## regular ALONG the road, which a per tile grid cannot give.
static func _pass_poles(hf: Heightfield, rng: RandomNumberGenerator,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var layout: Layout = hf.layout
	if layout == null:
		return
	var roads: Array = layout.roads
	if roads.is_empty():
		return

	var max_x: float = base_x + TILE
	var max_z: float = base_z + TILE
	var verge: float = Layout.ROAD_HALF_WIDTH + POLE_VERGE

	for r in roads.size():
		var line: PackedVector2Array = roads[r]
		if line.size() < 2:
			continue
		# Poles start at a stable offset per road so two roads never line up.
		var next_at: float = POLE_SPACING * (0.25 + 0.5 * _rand01(_hash4(r, 17, 91, 3)))
		var travelled: float = 0.0
		for i in range(line.size() - 1):
			var a: Vector2 = line[i]
			var b: Vector2 = line[i + 1]
			var seg: Vector2 = b - a
			var seg_len: float = seg.length()
			if seg_len < 0.01:
				continue
			var dir: Vector2 = seg / seg_len
			var nrm := Vector2(-dir.y, dir.x)
			while next_at <= travelled + seg_len:
				var t: float = next_at - travelled
				var p: Vector2 = a + dir * t + nrm * verge
				next_at += POLE_SPACING
				if p.x < base_x or p.x >= max_x or p.y < base_z or p.y >= max_z:
					continue
				var y: float = _ground(hf, p.x, p.y, SLOPE_FLAT_PROP, DRY_MARGIN)
				if is_nan(y):
					continue
				# The crossarm runs across the road, so the pole faces along it.
				var yaw: float = _yaw_for(dir.x, dir.y)
				_push(out, P_POLE, Vector3(p.x, y, p.y), yaw,
						rng.randf_range(0.94, 1.06), _tint(rng.randf(), 0.06))
			travelled += seg_len


## Villages are built by SiteBuilder, so the scatter only adds the leftovers of
## an occupation: a sandbag position at a corner, a burnt out vehicle.
static func _pass_village(hf: Heightfield, rng: RandomNumberGenerator,
		base_x: float, base_z: float, survey: PackedInt32Array,
		out: Array[Instance]) -> void:
	if survey[Heightfield.B_VILLAGE] <= 0:
		return
	var bags: int = rng.randi_range(0, 3)
	for i in bags:
		var x: float = base_x + rng.randf() * TILE
		var z: float = base_z + rng.randf() * TILE
		if hf.biome_at(x, z) != Heightfield.B_VILLAGE:
			continue
		var y: float = _ground(hf, x, z, SLOPE_FLAT_PROP, DRY_MARGIN)
		if is_nan(y):
			continue
		_push(out, P_SANDBAG, Vector3(x, y, z), rng.randf() * TAU,
				rng.randf_range(0.9, 1.25), _tint(rng.randf(), 0.08))
	if rng.randf() < 0.22:
		_try_wreck(hf, rng, base_x, base_z, out)


## Shell craters and burnt vehicles, everywhere, rare. This is what sells the
## "the front went through here" mood without cluttering the fields.
static func _pass_battle_scars(hf: Heightfield, rng: RandomNumberGenerator,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var roll: float = rng.randf()
	var craters: int = 0
	if roll > 0.70:
		craters = 1
	if roll > 0.90:
		craters = 2
	if roll > 0.975:
		craters = 4      # a stick of shells landed in this tile
	for i in craters:
		var x: float = base_x + rng.randf() * TILE
		var z: float = base_z + rng.randf() * TILE
		var biome: int = hf.biome_at(x, z)
		if biome == Heightfield.B_WATER or biome == Heightfield.B_VILLAGE:
			continue
		var y: float = _ground(hf, x, z, SLOPE_CRATER, DRY_MARGIN)
		if is_nan(y):
			continue
		_push(out, P_CRATER, Vector3(x, y, z), rng.randf() * TAU,
				rng.randf_range(0.55, 1.15), _tint(rng.randf(), 0.10))
	if rng.randf() < 0.05:
		_try_wreck(hf, rng, base_x, base_z, out)


## Picks the best of a few candidates for a wreck, favouring the roadside.
static func _try_wreck(hf: Heightfield, rng: RandomNumberGenerator,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var layout: Layout = hf.layout
	var best := Vector3.ZERO
	var best_score: float = -1.0
	for attempt in 6:
		var x: float = base_x + rng.randf() * TILE
		var z: float = base_z + rng.randf() * TILE
		var biome: int = hf.biome_at(x, z)
		if biome == Heightfield.B_WATER or biome == Heightfield.B_FOREST:
			continue
		var y: float = _ground(hf, x, z, SLOPE_FLAT_PROP, DRY_MARGIN)
		if is_nan(y):
			continue
		var score: float = 0.1
		if layout != null:
			score += layout.road_influence(x, z) * 2.0
		if score > best_score:
			best_score = score
			best = Vector3(x, y, z)
	if best_score < 0.0:
		return
	# Away from any road a wreck looks staged, so thin those out.
	if best_score < 0.4 and rng.randf() > 0.35:
		return
	_push(out, P_WRECK, best, rng.randf() * TAU, rng.randf_range(0.94, 1.08),
			_tint(rng.randf(), 0.10, -0.2))


## Bare rock outcrops: many sizes, from a football to a small boulder.
static func _pass_rocks(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var cells: int = int(TILE / STEP_ROCK)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_ROCK
			var cz: float = base_z + float(iz) * STEP_ROCK
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 101)
			if _rand01(h) > DENSITY_ROCK:
				continue
			var x: float = cx + _rand01(h >> 4) * STEP_ROCK
			var z: float = cz + _rand01(h >> 9) * STEP_ROCK
			if hf.biome_at(x, z) != Heightfield.B_ROCK:
				continue
			var y: float = _ground(hf, x, z, SLOPE_ROCK, DRY_MARGIN)
			if is_nan(y):
				continue
			var t: float = _rand01(h >> 14)
			# Cubed so most rocks are pebbles and a few are real cover.
			var s: float = 0.35 + t * t * t * 2.1
			if not _push(out, P_ROCK, Vector3(x, y - 0.12 * s, z),
					_rand01(h >> 18) * TAU, s, _tint(_rand01(h >> 22), 0.12)):
				return


## An orchard is planted, not grown: regular rows, staggered by half a spacing
## (quincunx). The grid is anchored on world coordinates so rows stay straight
## across tile borders, and a tree belongs to the tile holding its UNJITTERED
## base position, which is what keeps the seams free of duplicates.
static func _pass_orchard(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var i0: int = floori(base_x / ORCHARD_SPACING)
	var i1: int = floori((base_x + TILE - 0.001) / ORCHARD_SPACING)
	var j0: int = floori(base_z / ORCHARD_SPACING) - 1
	var j1: int = floori((base_z + TILE - 0.001) / ORCHARD_SPACING)
	for i in range(i0, i1 + 1):
		for j in range(j0, j1 + 1):
			var bx: float = float(i) * ORCHARD_SPACING
			var bz: float = float(j) * ORCHARD_SPACING
			if (i & 1) == 1:
				bz += ORCHARD_SPACING * 0.5
			if bz < base_z or bz >= base_z + TILE:
				continue
			var h: int = _hash4(world_seed, i, j, 211)
			# A real orchard has gaps: dead trees, rows never replanted.
			if _rand01(h) < 0.09:
				continue
			var x: float = bx + (_rand01(h >> 3) - 0.5) * 1.1
			var z: float = bz + (_rand01(h >> 8) - 0.5) * 1.1
			if hf.biome_at(x, z) != Heightfield.B_ORCHARD:
				continue
			var y: float = _ground(hf, x, z, SLOPE_TREE, DRY_MARGIN)
			if is_nan(y):
				continue
			if not _push(out, P_TREE_APPLE, Vector3(x, y, z),
					_rand01(h >> 13) * TAU, 0.86 + _rand01(h >> 17) * 0.32,
					_tint(_rand01(h >> 21), 0.09)):
				return


## Dense woodland: oaks with pine stands, and a bush understorey.
static func _pass_forest(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var cells: int = int(TILE / STEP_TREE)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_TREE
			var cz: float = base_z + float(iz) * STEP_TREE
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 307)
			if _rand01(h) > DENSITY_FOREST_TREE:
				continue
			var x: float = cx + _rand01(h >> 3) * STEP_TREE
			var z: float = cz + _rand01(h >> 8) * STEP_TREE
			if hf.biome_at(x, z) != Heightfield.B_FOREST:
				continue
			var y: float = _ground(hf, x, z, SLOPE_TREE, DRY_MARGIN)
			if is_nan(y):
				continue
			# Pines grow in stands, so the species is picked on a coarse 32 m
			# cell instead of per tree.
			var stand: int = _hash4(world_seed, floori(x / 32.0), floori(z / 32.0), 409)
			var pine: bool = _rand01(stand) < 0.35
			var kind: int = P_TREE_PINE if pine else P_TREE_OAK
			var s: float = 0.82 + _rand01(h >> 13) * 0.46
			if not _push(out, kind, Vector3(x, y, z), _rand01(h >> 17) * TAU, s,
					_tint(_rand01(h >> 21), 0.13)):
				return

	var bcells: int = int(TILE / STEP_BUSH)
	for ix2 in bcells:
		for iz2 in bcells:
			var cx2: float = base_x + float(ix2) * STEP_BUSH
			var cz2: float = base_z + float(iz2) * STEP_BUSH
			var h2: int = _hash4(world_seed, int(cx2 * 4.0), int(cz2 * 4.0), 503)
			if _rand01(h2) > DENSITY_FOREST_BUSH:
				continue
			var x2: float = cx2 + _rand01(h2 >> 3) * STEP_BUSH
			var z2: float = cz2 + _rand01(h2 >> 8) * STEP_BUSH
			if hf.biome_at(x2, z2) != Heightfield.B_FOREST:
				continue
			var y2: float = _ground(hf, x2, z2, SLOPE_GROUND_COVER, DRY_MARGIN)
			if is_nan(y2):
				continue
			if not _push(out, P_BUSH, Vector3(x2, y2, z2), _rand01(h2 >> 13) * TAU,
					0.7 + _rand01(h2 >> 17) * 0.8, _tint(_rand01(h2 >> 21), 0.14)):
				return


## The signature of Normandy: hedgerows along the parcel boundaries.
##
## A parcel boundary is where the biome changes, so the pass walks a 4 m grid,
## keeps the samples sitting on the meadow side of a border, and lays a hedge
## segment along the TANGENT of that border. When a meadow is so wide that no
## border shows up in the tile, a world anchored 48 m parcel grid takes over so
## the bocage never degenerates into an open field.
static func _pass_hedgerows(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, survey: PackedInt32Array,
		out: Array[Instance]) -> void:
	var placed: int = _pass_border(hf, world_seed, base_x, base_z,
			Heightfield.B_MEADOW, P_HEDGE, STEP_HEDGE, out)
	var meadow_share: float = float(survey[Heightfield.B_MEADOW]) \
			/ float(SURVEY_RES * SURVEY_RES)
	if placed >= 8 or meadow_share < 0.55:
		return
	_pass_parcel_grid(hf, world_seed, base_x, base_z, out)


## Lays a linear prop (hedge or fence) along the border of `biome`.
## Returns how many segments were placed.
static func _pass_border(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, biome: int, kind: int, step: float,
		out: Array[Instance]) -> int:
	var placed: int = 0
	var cells: int = int(TILE / step)
	var probe: float = step * 0.75
	for ix in cells:
		for iz in cells:
			var x: float = base_x + (float(ix) + 0.5) * step
			var z: float = base_z + (float(iz) + 0.5) * step
			if hf.biome_at(x, z) != biome:
				continue
			var grad: Vector2 = _border_gradient(hf, x, z, biome, probe)
			if grad.length_squared() < 0.25:
				continue
			var h: int = _hash4(world_seed, int(x * 4.0), int(z * 4.0), 601)
			# Gates and gaps: a solid wall of hedge is unplayable.
			if _rand01(h) < 0.10:
				continue
			var normal: Vector2 = grad.normalized()
			var tangent := Vector2(-normal.y, normal.x)
			# Nudge the segment onto the border itself rather than the sample.
			var px: float = x + normal.x * step * 0.32
			var pz: float = z + normal.y * step * 0.32
			var y: float = _ground(hf, px, pz, SLOPE_HEDGE, DRY_MARGIN)
			if is_nan(y):
				continue
			var s: float = 0.88 + _rand01(h >> 5) * 0.34
			if kind == P_FENCE:
				s = 0.95 + _rand01(h >> 5) * 0.12
			if not _push(out, kind, Vector3(px, y, pz),
					_yaw_for(tangent.x, tangent.y), s,
					_tint(_rand01(h >> 11), 0.11)):
				return placed
			placed += 1
	return placed


## Fallback bocage: hedges along a world anchored 48 m parcel grid.
static func _pass_parcel_grid(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var k0: int = floori(base_x / PARCEL_SIZE)
	var k1: int = floori((base_x + TILE) / PARCEL_SIZE)
	for k in range(k0, k1 + 1):
		# Per line wobble, so parcels are not perfect graph paper.
		var wob: float = (_rand01(_hash4(world_seed, k, 0, 733)) - 0.5) * 9.0
		_parcel_line(hf, world_seed, base_x, base_z,
				float(k) * PARCEL_SIZE + wob, true, out)
	var m0: int = floori(base_z / PARCEL_SIZE)
	var m1: int = floori((base_z + TILE) / PARCEL_SIZE)
	for m in range(m0, m1 + 1):
		var wob2: float = (_rand01(_hash4(world_seed, 0, m, 739)) - 0.5) * 9.0
		_parcel_line(hf, world_seed, base_x, base_z,
				float(m) * PARCEL_SIZE + wob2, false, out)


## Walks one parcel line across the tile and drops hedge segments on it.
## `vertical` means the line runs along Z at a fixed x.
static func _parcel_line(hf: Heightfield, world_seed: int, base_x: float,
		base_z: float, coord: float, vertical: bool,
		out: Array[Instance]) -> void:
	if vertical:
		if coord < base_x or coord >= base_x + TILE:
			return
	else:
		if coord < base_z or coord >= base_z + TILE:
			return
	var span_min: float = base_z if vertical else base_x
	var steps: int = int(TILE / STEP_HEDGE)
	for i in steps:
		var along: float = span_min + (float(i) + 0.5) * STEP_HEDGE
		var x: float = coord if vertical else along
		var z: float = along if vertical else coord
		# The line bends a little, the way a hedge planted on an earth bank
		# follows the lie of the land.
		var bend: float = (_rand01(_hash4(world_seed, int(along * 0.5),
				int(coord * 0.5), 811)) - 0.5) * 2.4
		if vertical:
			x += bend
		else:
			z += bend
		if hf.biome_at(x, z) != Heightfield.B_MEADOW:
			continue
		var h: int = _hash4(world_seed, int(x * 4.0), int(z * 4.0), 823)
		if _rand01(h) < PARCEL_GAP_CHANCE:
			continue
		var y: float = _ground(hf, x, z, SLOPE_HEDGE, DRY_MARGIN)
		if is_nan(y):
			continue
		var yaw: float = _yaw_for(0.0, 1.0) if vertical else _yaw_for(1.0, 0.0)
		yaw += (_rand01(h >> 7) - 0.5) * 0.22
		if not _push(out, P_HEDGE, Vector3(x, y, z), yaw,
				0.9 + _rand01(h >> 13) * 0.3, _tint(_rand01(h >> 17), 0.11)):
			return


## A meadow keeps a few isolated trees, the ones a farmer left for the shade.
static func _pass_meadow_trees(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var cells: int = int(TILE / STEP_TREE)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_TREE
			var cz: float = base_z + float(iz) * STEP_TREE
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 907)
			var r: float = _rand01(h)
			if r > DENSITY_MEADOW_TREE + DENSITY_MEADOW_BUSH:
				continue
			var x: float = cx + _rand01(h >> 3) * STEP_TREE
			var z: float = cz + _rand01(h >> 8) * STEP_TREE
			if hf.biome_at(x, z) != Heightfield.B_MEADOW:
				continue
			var is_tree: bool = r < DENSITY_MEADOW_TREE
			var limit: float = SLOPE_TREE if is_tree else SLOPE_GROUND_COVER
			var y: float = _ground(hf, x, z, limit, DRY_MARGIN)
			if is_nan(y):
				continue
			if is_tree:
				# Standing alone, they grow wide.
				if not _push(out, P_TREE_OAK, Vector3(x, y, z),
						_rand01(h >> 13) * TAU, 1.0 + _rand01(h >> 17) * 0.45,
						_tint(_rand01(h >> 21), 0.12)):
					return
			else:
				if not _push(out, P_BUSH, Vector3(x, y, z), _rand01(h >> 13) * TAU,
						0.8 + _rand01(h >> 17) * 0.7, _tint(_rand01(h >> 21), 0.14)):
					return


## Marsh: reeds by the thousand (drawn as tinted grass tufts) and the odd half
## drowned tree on a drier hummock.
static func _pass_marsh(hf: Heightfield, world_seed: int,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var cells: int = int(TILE / STEP_REED)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_REED
			var cz: float = base_z + float(iz) * STEP_REED
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 1009)
			if _rand01(h) > DENSITY_REED:
				continue
			var x: float = cx + _rand01(h >> 3) * STEP_REED
			var z: float = cz + _rand01(h >> 8) * STEP_REED
			if hf.biome_at(x, z) != Heightfield.B_MARSH:
				continue
			var y: float = _ground(hf, x, z, SLOPE_GROUND_COVER, MARSH_MARGIN)
			if is_nan(y):
				continue
			# Reeds are taller and browner than meadow grass.
			if not _push(out, P_GRASS_TUFT, Vector3(x, y, z),
					_rand01(h >> 13) * TAU, 1.25 + _rand01(h >> 17) * 0.75,
					_tint(_rand01(h >> 21), 0.10, 0.55)):
				return

	var tcells: int = int(TILE / STEP_TREE)
	for ix2 in tcells:
		for iz2 in tcells:
			var cx2: float = base_x + float(ix2) * STEP_TREE
			var cz2: float = base_z + float(iz2) * STEP_TREE
			var h2: int = _hash4(world_seed, int(cx2 * 4.0), int(cz2 * 4.0), 1013)
			if _rand01(h2) > 0.035:
				continue
			var x2: float = cx2 + _rand01(h2 >> 3) * STEP_TREE
			var z2: float = cz2 + _rand01(h2 >> 8) * STEP_TREE
			if hf.biome_at(x2, z2) != Heightfield.B_MARSH:
				continue
			var y2: float = _ground(hf, x2, z2, SLOPE_TREE, DRY_MARGIN + 0.35)
			if is_nan(y2):
				continue
			if not _push(out, P_TREE_OAK, Vector3(x2, y2, z2),
					_rand01(h2 >> 13) * TAU, 0.7 + _rand01(h2 >> 17) * 0.3,
					_tint(_rand01(h2 >> 21), 0.12, 0.3)):
				return


## Round haystacks, a handful per cultivated tile.
static func _pass_haystacks(hf: Heightfield, rng: RandomNumberGenerator,
		base_x: float, base_z: float, out: Array[Instance]) -> void:
	var count: int = 0
	var roll: float = rng.randf()
	if roll > 0.45:
		count = 1
	if roll > 0.75:
		count = 2
	if roll > 0.93:
		count = 3
	for i in count:
		var x: float = base_x + rng.randf() * TILE
		var z: float = base_z + rng.randf() * TILE
		if hf.biome_at(x, z) != Heightfield.B_FIELD:
			continue
		var y: float = _ground(hf, x, z, SLOPE_FLAT_PROP, DRY_MARGIN)
		if is_nan(y):
			continue
		_push(out, P_HAYSTACK, Vector3(x, y, z), rng.randf() * TAU,
				rng.randf_range(0.85, 1.20), _tint(rng.randf(), 0.09, 0.35))


## Grass tufts. A meadow gets a carpet, a field gets a few weeds at the margins.
static func _pass_tufts(hf: Heightfield, world_seed: int, base_x: float,
		base_z: float, survey: PackedInt32Array, out: Array[Instance]) -> void:
	if survey[Heightfield.B_MEADOW] <= 0 and survey[Heightfield.B_FIELD] <= 0 \
			and survey[Heightfield.B_ORCHARD] <= 0:
		return
	var cells: int = int(TILE / STEP_TUFT)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_TUFT
			var cz: float = base_z + float(iz) * STEP_TUFT
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 1223)
			var x: float = cx + _rand01(h >> 3) * STEP_TUFT
			var z: float = cz + _rand01(h >> 8) * STEP_TUFT
			var biome: int = hf.biome_at(x, z)
			var density: float = 0.0
			if biome == Heightfield.B_MEADOW:
				density = DENSITY_TUFT_MEADOW
			elif biome == Heightfield.B_FIELD:
				density = DENSITY_TUFT_FIELD
			elif biome == Heightfield.B_ORCHARD:
				density = DENSITY_TUFT_MEADOW * 0.7
			else:
				continue
			if _rand01(h) > density:
				continue
			var y: float = _ground(hf, x, z, SLOPE_GROUND_COVER, DRY_MARGIN)
			if is_nan(y):
				continue
			if not _push(out, P_GRASS_TUFT, Vector3(x, y, z),
					_rand01(h >> 13) * TAU, 0.8 + _rand01(h >> 17) * 0.6,
					_tint(_rand01(h >> 21), 0.14)):
				return


## Wheat: the densest family in the game, and the one the budget trims first.
static func _pass_wheat(hf: Heightfield, world_seed: int, base_x: float,
		base_z: float, out: Array[Instance]) -> void:
	var cells: int = int(TILE / STEP_WHEAT)
	for ix in cells:
		for iz in cells:
			var cx: float = base_x + float(ix) * STEP_WHEAT
			var cz: float = base_z + float(iz) * STEP_WHEAT
			var h: int = _hash4(world_seed, int(cx * 4.0), int(cz * 4.0), 1301)
			if _rand01(h) > DENSITY_WHEAT:
				continue
			var x: float = cx + _rand01(h >> 3) * STEP_WHEAT
			var z: float = cz + _rand01(h >> 8) * STEP_WHEAT
			if hf.biome_at(x, z) != Heightfield.B_FIELD:
				continue
			var y: float = _ground(hf, x, z, SLOPE_GROUND_COVER, DRY_MARGIN)
			if is_nan(y):
				continue
			if not _push(out, P_WHEAT, Vector3(x, y, z), _rand01(h >> 13) * TAU,
					0.85 + _rand01(h >> 17) * 0.4,
					_tint(_rand01(h >> 21), 0.12, 0.25)):
				return


# --- Helpers ---------------------------------------------------------------

## Coarse biome census of the tile, used to skip whole passes. Index = biome
## id, value = number of samples out of SURVEY_RES squared.
static func _survey(hf: Heightfield, base_x: float, base_z: float) -> PackedInt32Array:
	var counts := PackedInt32Array()
	counts.resize(Heightfield.B_ORCHARD + 1)
	counts.fill(0)
	var step: float = TILE / float(SURVEY_RES)
	for ix in SURVEY_RES:
		for iz in SURVEY_RES:
			var x: float = base_x + (float(ix) + 0.5) * step
			var z: float = base_z + (float(iz) + 0.5) * step
			var b: int = hf.biome_at(x, z)
			if b >= 0 and b < counts.size():
				counts[b] += 1
	return counts


## Ground height at a spot, or NAN when the spot must be rejected.
## Rejects: outside the playable square, at or below the water line, too steep.
static func _ground(hf: Heightfield, x: float, z: float, max_slope: float,
		margin: float) -> float:
	if not Heightfield.in_bounds(x, z):
		return NAN
	var y: float = hf.height_at(x, z)
	if y <= Heightfield.WATER_LEVEL + margin:
		return NAN
	if max_slope < 1.5 and hf.slope_at(x, z) > max_slope:
		return NAN
	return y


## Gradient of the "is this `biome`" indicator field, sampled at plus and minus
## `d`. A zero length result means the sample is not near a border.
static func _border_gradient(hf: Heightfield, x: float, z: float, biome: int,
		d: float) -> Vector2:
	var left: float = 1.0 if hf.biome_at(x - d, z) == biome else 0.0
	var right: float = 1.0 if hf.biome_at(x + d, z) == biome else 0.0
	var back: float = 1.0 if hf.biome_at(x, z - d) == biome else 0.0
	var front: float = 1.0 if hf.biome_at(x, z + d) == biome else 0.0
	# Points AWAY from the biome, i.e. towards the neighbouring parcel.
	return Vector2(left - right, back - front)


## Yaw that maps the prop local +X axis onto the world direction (dx, dz).
## Godot rotates +X to (cos a, 0, -sin a) around Y, hence the negated dz.
## Linear props (hedges, fences, telegraph crossarms) are modelled along +X.
static func _yaw_for(dx: float, dz: float) -> float:
	if absf(dx) < 1e-6 and absf(dz) < 1e-6:
		return 0.0
	return atan2(-dz, dx)


## Multiplicative instance colour centred on white. `warm` above zero pushes
## towards straw, below zero towards cold grey.
static func _tint(r: float, spread: float, warm: float = 0.0) -> Color:
	var t: float = fposmod(r, 1.0)
	var k: float = 1.0 + (t * 2.0 - 1.0) * spread
	var g: float = 1.0 + (fposmod(t * 3.13 + 0.27, 1.0) * 2.0 - 1.0) * spread * 0.6
	return Color(
		clampf(k * (1.0 + warm * 0.12), 0.55, 1.35),
		clampf(k * g * (1.0 + warm * 0.03), 0.55, 1.35),
		clampf(k * (1.0 - warm * 0.16), 0.55, 1.35),
		1.0)


## Appends an instance. Returns false once the tile budget is spent, which is
## the signal for the calling pass to stop early.
static func _push(out: Array[Instance], kind: int, pos: Vector3, rot: float,
		prop_scale: float, tint: Color) -> bool:
	if out.size() >= MAX_INSTANCES:
		return false
	var inst := Instance.new()
	inst.kind = kind
	inst.position = pos
	inst.rotation = rot
	inst.scale = prop_scale
	inst.tint = tint
	out.append(inst)
	return true


## Seed of a tile: stable for a given world, decorrelated between neighbours.
static func _tile_seed(world_seed: int, tx: int, tz: int) -> int:
	return _hash4(world_seed, tx, tz, 0x5F3A)


## Small integer hash, folded into 31 bits so it never overflows int64 when
## multiplied. Deterministic across platforms because every intermediate value
## stays positive.
static func _hash4(a: int, b: int, c: int, d: int) -> int:
	var h: int = (a & _MASK31) ^ 0x27D4EB2D
	h = _mix(h, b)
	h = _mix(h, c)
	h = _mix(h, d)
	return h


static func _mix(h: int, v: int) -> int:
	var x: int = (h ^ (v & _MASK31)) & _MASK31
	x = (x * 0x45D9F3B) & _MASK31
	x = (x ^ (x >> 15)) & _MASK31
	x = (x * 0x45D9F3B) & _MASK31
	x = (x ^ (x >> 13)) & _MASK31
	return x


## Hash bits to a float in [0, 1).
##
## The input is re-mixed rather than merely masked, and that is load bearing.
## Callers draw several independent values out of one hash by shifting it
## (`_rand01(h >> 13)`, `_rand01(h >> 17)`, ...). `_hash4` only produces 31 bits,
## so a plain low-bit mask would hand back a value capped at `2^(31-k)/2^24`:
## past a shift of 7 the result collapses towards zero, and every tree in the
## world ends up with the same rotation, the same scale and the same tint.
## Re-mixing spreads whatever bits survive the shift back across the full range,
## so each shifted window behaves as an independent draw.
static func _rand01(h: int) -> float:
	return float(_mix(0x9E3779B1, h) & 0xFFFFFF) / 16777216.0
