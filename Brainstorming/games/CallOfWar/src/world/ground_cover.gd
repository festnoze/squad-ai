class_name GroundCover
extends Node3D
## Dense grass ring around the player, purely cosmetic.
##
## The scatter plants a grass tuft every 3.2 m, which reads well from twenty
## metres out and leaves the ground bare under the player's own feet. This node
## fills that hole: a 26 m ring of individual blades, rebuilt cell by cell as
## the player walks, dropped once he is far enough away.
##
## Everything here is throwaway decoration:
##
## - no collision, ever. The player must never trip on a blade of grass;
## - no new material. Blades borrow `MatLib.get_material("blade")`, and "wheat"
##   over a cultivated field, so the ring costs zero extra shader compile;
## - no persistent state. A cell is a pure function of the world seed and of
##   the cell coordinates, so walking away and coming back rebuilds exactly the
##   same grass, and a rebuild never has to be recorded anywhere.
##
## Cost control has three separate valves:
##
## 1. at most `CELLS_PER_FRAME` cells are built per frame, so a teleport spreads
##    the work over a dozen frames instead of stalling one;
## 2. a hard global ceiling of `MAX_BLADES` instances, enforced while building
##    and nearest cell first, so the budget is always spent where it shows;
## 3. the density follows the quality ladder, read from `QualityGovernor`.
##
## The node is autonomous: the scene wires it with `setup(world, follow)` and
## then forgets about it.

# --- Geometry of the ring --------------------------------------------------

## Side of one rebuild cell, in metres.
const CELL := 8.0
## A cell whose centre is within this distance of the player is wanted.
const RING_RADIUS := 26.0
## A cell whose centre passes this distance is dropped.
const DROP_RADIUS := 34.0
## Cells rebuilt per frame, at most.
const CELLS_PER_FRAME := 2
## Hard ceiling on live blades, all cells together.
const MAX_BLADES := 24000

## Biome and height are sampled on a coarse lattice inside the cell rather than
## per blade: `biome_at` walks the road spine, the site list and the marsh mask,
## which is far too expensive to pay four hundred times per cell. Two metres is
## fine enough that a road verge or a river bank stays where it belongs, and the
## density is interpolated between samples so the grass thins out towards a
## forbidden biome instead of ending on a straight line.
const SUB := 4
const SUB_STEP := CELL / float(SUB)
const GRID := SUB + 1

# --- Density ---------------------------------------------------------------

## Blades in one full cell at quality level 0, indexed by `Heightfield.B_*`.
## Order matters and is asserted by the suite: the three open farmland biomes
## are dense, forest and marsh are sparse, and the four hard surfaces are bare.
const DENSITY: PackedInt32Array = [
	440,   # B_FIELD    : between the wheat rows
	560,   # B_MEADOW   : the thickest grass in the pocket
	192,   # B_FOREST   : sparse, the canopy starves the ground
	140,   # B_MARSH    : sparse, reeds already stand there
	0,     # B_ROAD
	0,     # B_VILLAGE
	0,     # B_WATER
	0,     # B_ROCK
	508,   # B_ORCHARD  : mown grass under the apple trees
]

## Candidate slots drawn per cell before the density test. Equal to the densest
## biome, so a full meadow cell accepts every slot it draws. 560 blades over a
## 64 m cell is nearly nine per square metre, which is what it takes to read as
## a mat rather than as scattered spikes; the ring holds around forty cells, so
## a meadow at level 0 lands just under the global ceiling.
const SLOTS := 560

## Density multiplier of each rung of the quality ladder. Level 0 is untouched,
## the worst rung keeps roughly a third of the blades.
const QUALITY_DENSITY: PackedFloat32Array = [1.0, 0.85, 0.70, 0.50, 0.35]

# --- Blade shape -----------------------------------------------------------

## Wide enough that nine blades per square metre close into a mat rather than
## dotting the ground, narrow enough that one blade still reads as a blade.
const BLADE_WIDTH := 0.145
## Short on purpose. Tall cards at this spacing stand out one by one, which is
## the "plastic spike" look; keeping them low lets them close up.
const BLADE_HEIGHT := 0.40
## Wheat stands taller than meadow grass.
const WHEAT_SCALE := 1.45
## Largest lean off vertical, in radians. A field of perfectly upright cards
## reads as a bed of nails.
const MAX_TILT := 0.28
## Blades never sit this close to the water line.
const DRY_MARGIN := 0.25

## Packed layout of one blade: x, y, z, yaw, scale, kind, tint, tilt.
const STRIDE := 8
const KIND_GRASS := 0
const KIND_WHEAT := 1

const _MASK31 := 0x7FFFFFFF
const _SALT := 0x63A1

# --- State -----------------------------------------------------------------

var _world: GameWorld = null
var _follow: Node3D = null
var _hf: Heightfield = null

## Cell coordinates -> Array[MultiMeshInstance3D]. One entry per live cell.
var _cells: Dictionary = {}
## Cell coordinates -> int, blades held by that cell.
var _counts: Dictionary = {}
## Cells wanted but not built yet, nearest first.
var _pending: Array[Vector2i] = []

var _total := 0
var _scale := 1.0
var _center := Vector2i(0x3FFFFFFF, 0x3FFFFFFF)
var _rescan := 0.0

static var _mesh_cache: Mesh = null


func _ready() -> void:
	# After the world streamer, so a cell asked for this frame sees the chunk
	# that landed this frame rather than the one from the previous.
	process_priority = 30
	# setup() may land before or after _ready depending on how the scene wires
	# the node, so the gate is re-evaluated here rather than simply cleared.
	set_process(_world != null and _follow != null)


## Wires the ring to a world and to the node it follows, usually the player.
##
## Safe to call before the world has generated: the height field is picked up
## on the first frame where it exists, so the wiring order in the scene is not
## a trap for whoever integrates this.
func setup(world: GameWorld, follow: Node3D) -> void:
	_drop_all()
	_world = world
	_follow = follow
	_hf = world.heightfield() if world != null else null
	_scale = quality_scale()
	_center = Vector2i(0x3FFFFFFF, 0x3FFFFFFF)
	_rescan = 0.0
	set_process(_world != null and _follow != null)


## Blades currently standing, all cells together.
func blade_count() -> int:
	return _total


## Live cells, for diagnostics.
func cell_count() -> int:
	return _cells.size()


func _process(delta: float) -> void:
	if _world == null or _follow == null:
		return
	# The node followed can outlive its usefulness (a dead player is freed while
	# the ring is still up), and reading a freed object through a typed variable
	# is a hard error in GDScript, so check before touching it.
	if not is_instance_valid(_follow):
		_follow = null
		set_process(false)
		return
	if _hf == null:
		# The world was still priming when setup() ran. Wait for it rather than
		# forcing the caller into a particular order.
		_hf = _world.heightfield()
		if _hf == null:
			return

	# A rung change on the quality ladder rescales every cell, so the simplest
	# correct answer is to throw the ring away and let it grow back over the
	# next few frames. Rungs move at most once every couple of seconds.
	var wanted_scale := quality_scale()
	if not is_equal_approx(wanted_scale, _scale):
		_scale = wanted_scale
		_drop_all()
		_center = Vector2i(0x3FFFFFFF, 0x3FFFFFFF)

	var focus: Vector3 = _follow.global_position
	var here := _cell_of(focus.x, focus.z)
	_rescan -= delta
	if here != _center or _rescan <= 0.0:
		_center = here
		# Cells skipped because their ground was not streamed in yet come back
		# through this rescan, which is why it also runs on a timer.
		_rescan = 0.35
		_drop_far(focus)
		_rebuild_pending(focus)

	var built := 0
	while built < CELLS_PER_FRAME and not _pending.is_empty():
		if _total >= MAX_BLADES:
			break
		var cell: Vector2i = _pending.pop_front()
		if _cells.has(cell):
			continue
		if not _build_cell(cell):
			continue
		built += 1


# ---------------------------------------------------------------------------
# Pure content
# ---------------------------------------------------------------------------

## Every blade of one cell, packed flat, `STRIDE` floats each.
##
## Deterministic on (world seed, cell): the same cell rebuilt an hour later, or
## approached from the other side, holds exactly the same blades. Nothing here
## touches the scene tree, which is what makes it testable on its own.
##
## The heights come from `Heightfield.height_at`, which is precisely what
## `GameWorld.ground_y` returns; going through the height field directly keeps
## this function free of the scene.
static func cell_blades(hf: Heightfield, cx: int, cz: int,
		density_scale: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	if hf == null:
		return out

	var base_x: float = float(cx) * CELL
	var base_z: float = float(cz) * CELL

	# Coarse lattice: density, height and biome at each node.
	var dens := PackedFloat32Array()
	var hgt := PackedFloat32Array()
	var biomes := PackedInt32Array()
	dens.resize(GRID * GRID)
	hgt.resize(GRID * GRID)
	biomes.resize(GRID * GRID)
	var any := false
	for i in GRID:
		for j in GRID:
			var sx: float = base_x + float(i) * SUB_STEP
			var sz: float = base_z + float(j) * SUB_STEP
			var k: int = i * GRID + j
			hgt[k] = hf.height_at(sx, sz)
			var b: int = hf.biome_at(sx, sz)
			biomes[k] = b
			var d: float = float(biome_density(b))
			dens[k] = d
			if d > 0.0:
				any = true
	if not any:
		return out

	var scale: float = clampf(density_scale, 0.0, 1.0)
	var slots: int = int(round(float(SLOTS) * scale))
	if slots <= 0:
		return out

	var cell_hash: int = _hash4(int(hf.world_seed), cx, cz, _SALT)
	var water: float = Heightfield.WATER_LEVEL + DRY_MARGIN

	for slot in slots:
		var h: int = _mix(cell_hash, slot)
		var u: float = _rand01(h)
		var v: float = _rand01(h >> 4)
		var want: float = _bilerp(dens, u, v) * scale
		if float(slot) >= want:
			continue
		var y: float = _bilerp(hgt, u, v)
		# Never over water, whatever the interpolated density says. This is the
		# one biome rule that has to hold blade by blade rather than on average.
		if y < water:
			continue
		var kind: int = KIND_WHEAT if _nearest_biome(biomes, u, v) == Heightfield.B_FIELD else KIND_GRASS
		# Biased small: a real sward is mostly short with a few tall stems, and
		# a uniform draw gives a suspiciously even carpet.
		var raw: float = _rand01(h >> 8)
		var blade_scale: float = 0.62 + raw * raw * 0.98
		if kind == KIND_WHEAT:
			blade_scale *= WHEAT_SCALE
		out.append(base_x + u * CELL)
		out.append(y)
		out.append(base_z + v * CELL)
		out.append(_rand01(h >> 12) * TAU)
		out.append(blade_scale)
		out.append(float(kind))
		out.append(_rand01(h >> 16))
		out.append((_rand01(h >> 20) - 0.5) * 2.0 * MAX_TILT)

	return out


## Blades held by a packed cell payload.
static func packed_count(data: PackedFloat32Array) -> int:
	return data.size() / STRIDE


## Blades of a full cell of this biome at quality level 0.
static func biome_density(biome: int) -> int:
	if biome < 0 or biome >= DENSITY.size():
		return 0
	return DENSITY[biome]


## Current rung of the quality ladder, deduced from the prop draw distance the
## governor publishes. The governor belongs to the scene, not to this lot, so it
## is only ever read.
static func quality_level() -> int:
	var d: float = QualityGovernor.prop_draw_distance
	var best := 0
	var best_gap: float = INF
	for i in QualityGovernor.PROP_DISTANCE.size():
		var gap: float = absf(QualityGovernor.PROP_DISTANCE[i] - d)
		if gap < best_gap:
			best_gap = gap
			best = i
	return best


## Density multiplier of the current rung, 1.0 at level 0.
static func quality_scale() -> float:
	var level: int = clampi(quality_level(), 0, QUALITY_DENSITY.size() - 1)
	return QUALITY_DENSITY[level]


# ---------------------------------------------------------------------------
# Cell lifetime
# ---------------------------------------------------------------------------

## Builds one cell. Returns false when nothing was spawned, either because the
## ground under it is not streamed in yet, because the budget is spent, or
## because the cell is bare ground. Only the first case is worth retrying, and
## the rescan timer picks it up on its own.
func _build_cell(cell: Vector2i) -> bool:
	var base_x: float = float(cell.x) * CELL
	var base_z: float = float(cell.y) * CELL
	var mid := Vector3(base_x + CELL * 0.5, 0.0, base_z + CELL * 0.5)
	mid.y = _world.ground_y(mid.x, mid.z)
	if not _world.is_ground_ready(mid):
		return false

	var room: int = MAX_BLADES - _total
	if room <= 0:
		return false

	var data: PackedFloat32Array = cell_blades(_hf, cell.x, cell.y, _scale)
	var count: int = packed_count(data)
	if count > room:
		count = room
		data = data.slice(0, room * STRIDE)

	var nodes: Array[MultiMeshInstance3D] = []
	if count > 0:
		var grass := PackedInt32Array()
		var wheat := PackedInt32Array()
		for i in count:
			if int(data[i * STRIDE + 5]) == KIND_WHEAT:
				wheat.append(i)
			else:
				grass.append(i)
		var g_node: MultiMeshInstance3D = _spawn_batch(data, grass, base_x, base_z, "blade")
		if g_node != null:
			nodes.append(g_node)
		var w_node: MultiMeshInstance3D = _spawn_batch(data, wheat, base_x, base_z, "wheat")
		if w_node != null:
			nodes.append(w_node)

	_cells[cell] = nodes
	_counts[cell] = count
	_total += count
	return true


func _spawn_batch(data: PackedFloat32Array, picks: PackedInt32Array,
		base_x: float, base_z: float, material_key: String) -> MultiMeshInstance3D:
	if picks.is_empty():
		return null
	var mesh: Mesh = blade_mesh()
	if mesh == null:
		return null
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = picks.size()

	var low: float = INF
	var high: float = -INF
	for n in picks.size():
		var i: int = picks[n]
		var x: float = data[i * STRIDE] - base_x
		var y: float = data[i * STRIDE + 1]
		var z: float = data[i * STRIDE + 2] - base_z
		var yaw: float = data[i * STRIDE + 3]
		var s: float = data[i * STRIDE + 4]
		var tint: float = data[i * STRIDE + 6]
		var tilt: float = data[i * STRIDE + 7]
		var basis := Basis(Vector3.UP, yaw)
		# Lean about the blade's own base, so the root stays planted.
		basis = Basis(basis.x, tilt) * basis
		mm.set_instance_transform(n,
				Transform3D(basis.scaled(Vector3.ONE * s), Vector3(x, y, z)))
		mm.set_instance_color(n, _blade_tint(tint))
		low = minf(low, y)
		high = maxf(high, y + BLADE_HEIGHT * s)

	var mmi := MultiMeshInstance3D.new()
	mmi.name = "Cover_%s_%d_%d" % [material_key, int(base_x), int(base_z)]
	mmi.multimesh = mm
	mmi.position = Vector3(base_x, 0.0, base_z)
	mmi.material_override = MatLib.get_material(material_key)
	# The culler cannot guess the extent of a MultiMesh, and a wrong guess makes
	# whole cells blink as the camera turns.
	mmi.custom_aabb = AABB(Vector3(-0.5, low - 0.5, -0.5),
			Vector3(CELL + 1.0, maxf(high - low, 0.1) + 1.0, CELL + 1.0))
	# Ground cover is the last thing that should ever cast a shadow: thousands
	# of alpha tested cards in the shadow atlas buy nothing at this range.
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mmi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	# Dissolve the outermost cells instead of dropping them in one frame.
	mmi.visibility_range_end = DROP_RADIUS
	mmi.visibility_range_end_margin = DROP_RADIUS - RING_RADIUS
	mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
	add_child(mmi)
	return mmi


func _drop_cell(cell: Vector2i) -> void:
	var nodes: Array = _cells.get(cell, [])
	for node in nodes:
		if is_instance_valid(node):
			node.queue_free()
	_total -= int(_counts.get(cell, 0))
	_cells.erase(cell)
	_counts.erase(cell)
	if _total < 0:
		_total = 0


func _drop_all() -> void:
	for cell in _cells.keys():
		_drop_cell(cell)
	_cells.clear()
	_counts.clear()
	_pending.clear()
	_total = 0


func _drop_far(focus: Vector3) -> void:
	var drop2: float = DROP_RADIUS * DROP_RADIUS
	var doomed: Array[Vector2i] = []
	for cell in _cells:
		if _cell_distance2(cell, focus) > drop2:
			doomed.append(cell)
	for cell in doomed:
		_drop_cell(cell)


## Rebuilds the queue of missing cells, nearest first, so the budget and the
## global ceiling are both spent on what the player is standing in.
func _rebuild_pending(focus: Vector3) -> void:
	_pending.clear()
	var reach: int = int(ceil(RING_RADIUS / CELL)) + 1
	var ring2: float = RING_RADIUS * RING_RADIUS
	var found: Array[Vector2i] = []
	for dx in range(-reach, reach + 1):
		for dz in range(-reach, reach + 1):
			var cell := Vector2i(_center.x + dx, _center.y + dz)
			if _cells.has(cell):
				continue
			if _cell_distance2(cell, focus) > ring2:
				continue
			found.append(cell)
	found.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
		return _cell_distance2(a, focus) < _cell_distance2(b, focus))
	_pending = found


func _cell_distance2(cell: Vector2i, focus: Vector3) -> float:
	var dx: float = float(cell.x) * CELL + CELL * 0.5 - focus.x
	var dz: float = float(cell.y) * CELL + CELL * 0.5 - focus.z
	return dx * dx + dz * dz


static func _cell_of(x: float, z: float) -> Vector2i:
	return Vector2i(floori(x / CELL), floori(z / CELL))


# ---------------------------------------------------------------------------
# Blade geometry
# ---------------------------------------------------------------------------

## One blade, drawn as a crossed card so it reads from every angle. Cached: the
## same mesh serves every cell and both materials, which is what keeps the ring
## down to two draw calls per cell.
static func blade_mesh() -> Mesh:
	if _mesh_cache != null:
		return _mesh_cache
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_card(st, 0.0)
	_card(st, PI * 0.5)
	_mesh_cache = st.commit()
	return _mesh_cache


## One card of the cross, standing on the origin.
##
## Cut in two segments and bent over rather than drawn as one straight quad: a
## straight card at this size reads as a spike stuck in the ground, and the arc
## is what makes it read as a blade of grass. Four extra triangles per blade is
## a cheap price next to doubling the instance count.
##
## UV runs V=1 at the root and V=0 at the tip, which is the orientation the
## blade cut out of the atlas expects. The vertex colour darkens towards the
## root: the blade material multiplies it into the albedo, and a uniform card
## reads as a flat green sticker without it.
static func _card(st: SurfaceTool, yaw: float) -> void:
	var side := Vector3(cos(yaw), 0.0, sin(yaw)) * BLADE_WIDTH * 0.5
	# The blade bends across its own plane, not along it, so the arc stays
	# visible from the front.
	var bend := Vector3(cos(yaw + PI * 0.5), 0.0, sin(yaw + PI * 0.5)) * BLADE_HEIGHT
	var root := Vector3.ZERO
	var mid: Vector3 = Vector3(0.0, BLADE_HEIGHT * 0.58, 0.0) + bend * 0.10
	var tip: Vector3 = Vector3(0.0, BLADE_HEIGHT * 0.96, 0.0) + bend * 0.34

	var c0 := Color(0.46, 0.46, 0.46, 1.0)
	var c1 := Color(0.80, 0.80, 0.80, 1.0)
	var c2 := Color(1.0, 1.0, 1.0, 1.0)
	_segment(st, root, mid, side, side * 0.72, 1.0, 0.44, c0, c1)
	_segment(st, mid, tip, side * 0.72, side * 0.22, 0.44, 0.0, c1, c2)


static func _segment(st: SurfaceTool, low: Vector3, high: Vector3,
		low_side: Vector3, high_side: Vector3, low_v: float, high_v: float,
		low_color: Color, high_color: Color) -> void:
	var a: Vector3 = low - low_side
	var b: Vector3 = low + low_side
	var c: Vector3 = high + high_side
	var d: Vector3 = high - high_side
	var geo: Vector3 = (b - a).cross(c - a)
	if geo.length_squared() < 1e-12:
		return
	# A mostly vertical normal keeps thin vegetation out of the black when the
	# sun rakes across it, which a strict geometric normal does not.
	var n: Vector3 = (geo.normalized() * 0.35 + Vector3.UP * 0.65).normalized()
	_vertex(st, a, n, Vector2(0.0, low_v), low_color)
	_vertex(st, b, n, Vector2(1.0, low_v), low_color)
	_vertex(st, c, n, Vector2(1.0, high_v), high_color)
	_vertex(st, a, n, Vector2(0.0, low_v), low_color)
	_vertex(st, c, n, Vector2(1.0, high_v), high_color)
	_vertex(st, d, n, Vector2(0.0, high_v), high_color)


static func _vertex(st: SurfaceTool, p: Vector3, n: Vector3, uv: Vector2,
		c: Color) -> void:
	st.set_normal(n)
	st.set_uv(uv)
	st.set_color(c)
	st.add_vertex(p)


## Multiplicative per instance tint, centred just under white. The blade
## material already carries a tint above 1.0 to lift the shaded photograph out
## of the dark, so this one stays below unity: pushing both above 1.0 is how a
## meadow turns into a sheet of neon.
static func _blade_tint(t: float) -> Color:
	var v: float = 0.46 + t * 0.34
	# A meadow is not one green. Some blades run to hay, some stay cold.
	var warm: float = 0.84 + t * 0.30
	return Color(v * warm, v, v * 0.70, 1.0)


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

## Bilinear read of a GRID x GRID lattice at cell relative coordinates.
static func _bilerp(grid: PackedFloat32Array, u: float, v: float) -> float:
	var fx: float = clampf(u, 0.0, 1.0) * float(SUB)
	var fz: float = clampf(v, 0.0, 1.0) * float(SUB)
	var i0: int = clampi(int(fx), 0, SUB - 1)
	var j0: int = clampi(int(fz), 0, SUB - 1)
	var tx: float = fx - float(i0)
	var tz: float = fz - float(j0)
	var a: float = grid[i0 * GRID + j0]
	var b: float = grid[(i0 + 1) * GRID + j0]
	var c: float = grid[i0 * GRID + j0 + 1]
	var d: float = grid[(i0 + 1) * GRID + j0 + 1]
	return lerpf(lerpf(a, b, tx), lerpf(c, d, tx), tz)


## Nearest lattice biome, used only to pick between grass and wheat.
static func _nearest_biome(grid: PackedInt32Array, u: float, v: float) -> int:
	var i: int = clampi(int(round(clampf(u, 0.0, 1.0) * float(SUB))), 0, SUB)
	var j: int = clampi(int(round(clampf(v, 0.0, 1.0) * float(SUB))), 0, SUB)
	return grid[i * GRID + j]


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
#
# Deliberately a local copy of the scheme the scatter uses rather than a call
# into it: this file has to stand on its own, and a shared private helper is a
# dependency waiting to drift. Everything stays inside 31 positive bits so the
# result is identical on every platform.

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


## Hash bits to a float in [0, 1). The input is re-mixed rather than masked so
## that callers can draw several independent values out of one hash by shifting
## it: a plain mask collapses towards zero past a shift of seven, and every
## blade in the cell would end up with the same rotation and the same height.
static func _rand01(h: int) -> float:
	return float(_mix(0x9E3779B1, h) & 0xFFFFFF) / 16777216.0
