class_name TerrainChunk
extends Node3D
## One 64 m terrain tile.
##
## The heavy part (heights, normals, vertex colours, prop placement) is produced
## by the static, pure function build_data(), which touches no node and can
## therefore run on a worker thread. apply() turns that dictionary into scene
## nodes and must run on the main thread.

const TILE := 64.0
## Vertex grid per LOD level, index = lod. LOD 0 is the finest.
const LOD_RES: PackedInt32Array = [32, 16, 8, 4]
const LOD_COUNT := 4

## Vertical drop of the border skirt that hides the cracks between two
## neighbouring tiles rendered at a different LOD.
const SKIRT := 3.0
## Side of the collision heightmap: 33 x 33 samples, one every 2 m over 64 m.
const COLLISION_RES := 33
## Vegetation level that carries everything, including the dense small props.
const PROPS_FULL := 0
## Vegetation level that only keeps what still reads at distance.
const PROPS_FAR := 1
## Vegetation level that carries nothing.
const PROPS_NONE := 2
## Terrain texture repeats every 8 m.
const UV_SCALE := 0.125
## Full prop nodes created per frame while a tile spreads its vegetation.
const NODE_JOB_SIZE := 12

var tx: int = 0
var tz: int = 0
var lod: int = -1

## One mesh instance per LOD level. Kept alive so a LOD swap is instant and can
## never leave a hole in the ground.
var _meshes: Array[MeshInstance3D] = [null, null, null, null]
var _heights: PackedFloat32Array = PackedFloat32Array()
var _body: StaticBody3D = null
var _props_root: Node3D = null
var _props_level: int = -1
var _placed := false
var _hf_ref: Heightfield = null
## Vegetation work left to do, one job per frame.
var _jobs: Array[Dictionary] = []

## Shared cylinder shapes for prop collision, keyed by rounded size.
static var _shape_cache: Dictionary = {}


func _ready() -> void:
	# Declaring _process() turns processing on by itself; a chunk only wants it
	# while it still has vegetation jobs to spend.
	set_process(false)


# ---------------------------------------------------------------------------
# Off thread data
# ---------------------------------------------------------------------------

## Data produced off thread. Pure function, no scene access, safe on a worker.
static func build_data(hf: Heightfield, tile_x: int, tile_z: int, level: int) -> Dictionary:
	if hf == null:
		push_error("TerrainChunk.build_data called without a heightfield")
		return {}
	var lv: int = clampi(level, 0, LOD_COUNT - 1)
	var res: int = LOD_RES[lv]
	var n: int = res + 1
	var step: float = TILE / float(res)
	var ox: float = float(tile_x) * TILE
	var oz: float = float(tile_z) * TILE

	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	var uvs := PackedVector2Array()
	verts.resize(n * n)
	norms.resize(n * n)
	cols.resize(n * n)
	uvs.resize(n * n)

	var min_y := 1.0e20
	var max_y := -1.0e20
	for j in n:
		var lz: float = float(j) * step
		var wz: float = oz + lz
		for i in n:
			var lx: float = float(i) * step
			var wx: float = ox + lx
			var h: float = hf.height_at(wx, wz)
			var idx: int = j * n + i
			verts[idx] = Vector3(lx, h, lz)
			norms[idx] = hf.normal_at(wx, wz)
			cols[idx] = hf.color_at(wx, wz)
			uvs[idx] = Vector2(wx, wz) * UV_SCALE
			min_y = minf(min_y, h)
			max_y = maxf(max_y, h)

	var indices := PackedInt32Array()
	for j in res:
		for i in res:
			var a: int = j * n + i
			var b: int = a + 1
			var c: int = a + n
			var d: int = c + 1
			# Same winding as the engine PlaneMesh, so the surface faces up.
			indices.append(a)
			indices.append(b)
			indices.append(c)
			indices.append(b)
			indices.append(d)
			indices.append(c)

	_append_skirt(verts, norms, cols, uvs, indices, n)

	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_COLOR] = cols
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices

	var heights := PackedFloat32Array()
	if lv == 0:
		heights.resize(COLLISION_RES * COLLISION_RES)
		if n == COLLISION_RES:
			# At LOD 0 the vertex grid and the collision grid share the very
			# same sample points, so reuse them instead of paying the (costly)
			# height function twice. Only the first n * n entries of verts are
			# grid vertices, the rest is skirt.
			for k in COLLISION_RES * COLLISION_RES:
				heights[k] = verts[k].y
		else:
			var cstep: float = TILE / float(COLLISION_RES - 1)
			for j in COLLISION_RES:
				var wz2: float = oz + float(j) * cstep
				for i in COLLISION_RES:
					heights[j * COLLISION_RES + i] = hf.height_at(ox + float(i) * cstep, wz2)

	var props: Array = []
	var plevel: int = prop_level(lv)
	if plevel != PROPS_NONE:
		var all: Array = Scatter.for_tile(hf, tile_x, tile_z)
		for raw in all:
			var inst := raw as Scatter.Instance
			if inst == null:
				continue
			if _prop_allowed(inst.kind, plevel):
				props.append(inst)

	var box := AABB(
			Vector3(0.0, min_y - SKIRT - 1.0, 0.0),
			Vector3(TILE, maxf(max_y - min_y, 0.1) + SKIRT + 13.0, TILE))

	return {
		"tile": Vector2i(tile_x, tile_z),
		"lod": lv,
		"mesh_arrays": arrays,
		"heights": heights,
		"props": props,
		"aabb": box,
	}


## Border skirt. Each edge is walked so that (direction cross down) points away
## from the tile, which is the winding the engine needs to keep it visible.
static func _append_skirt(verts: PackedVector3Array, norms: PackedVector3Array,
		cols: PackedColorArray, uvs: PackedVector2Array,
		indices: PackedInt32Array, n: int) -> void:
	var south := PackedInt32Array()      # -z border, walked towards +x
	var east := PackedInt32Array()       # +x border, walked towards +z
	var north := PackedInt32Array()      # +z border, walked towards -x
	var west := PackedInt32Array()       # -x border, walked towards -z
	for i in n:
		south.append(i)
		east.append(i * n + (n - 1))
		north.append((n - 1) * n + (n - 1 - i))
		west.append((n - 1 - i) * n)
	var edges: Array = [south, east, north, west]

	var drop := Vector3(0.0, SKIRT, 0.0)
	for raw_edge in edges:
		var edge: PackedInt32Array = raw_edge
		var prev_top := -1
		var prev_bottom := -1
		for k in edge.size():
			var top: int = edge[k]
			var bottom: int = verts.size()
			verts.append(verts[top] - drop)
			norms.append(norms[top])
			cols.append(cols[top])
			uvs.append(uvs[top])
			if k > 0:
				indices.append(prev_top)
				indices.append(prev_bottom)
				indices.append(top)
				indices.append(top)
				indices.append(prev_bottom)
				indices.append(bottom)
			prev_top = top
			prev_bottom = bottom


## Vegetation level of a LOD level. The two close LOD levels share the very same
## set on purpose: crossing that ring is the most frequent transition of all, and
## rebuilding a whole tile of vegetation there would stutter at every step.
static func prop_level(level: int) -> int:
	if level <= 1:
		return PROPS_FULL
	if level == 2:
		return PROPS_FAR
	return PROPS_NONE


## Beyond the close rings only what still reads from far away is kept, and only
## if the kind is batched: a hundred loose nodes at 400 m is a waste.
static func _prop_allowed(kind: int, plevel: int) -> bool:
	if plevel == PROPS_FULL:
		return true
	if plevel == PROPS_FAR:
		if not Scatter.is_batched(kind):
			return false
		if kind == Scatter.P_TREE_OAK or kind == Scatter.P_TREE_PINE:
			return true
		return kind == Scatter.P_TREE_APPLE or kind == Scatter.P_HEDGE
	return false


# ---------------------------------------------------------------------------
# Main thread
# ---------------------------------------------------------------------------

## Applies data built by build_data. Main thread only.
func apply(hf: Heightfield, tile_x: int, tile_z: int, level: int, data: Dictionary) -> void:
	if data.is_empty():
		push_warning("TerrainChunk.apply got empty data for tile %d,%d" % [tile_x, tile_z])
		return
	_hf_ref = hf
	tx = tile_x
	tz = tile_z
	if not _placed:
		_placed = true
		name = "Chunk_%d_%d" % [tx, tz]
		position = Vector3(float(tx) * TILE, 0.0, float(tz) * TILE)

	var lv: int = clampi(level, 0, LOD_COUNT - 1)
	_apply_mesh(lv, data)
	_show_only(lv)
	lod = lv

	var heights: PackedFloat32Array = data.get("heights", PackedFloat32Array())
	if heights.size() == COLLISION_RES * COLLISION_RES:
		_heights = heights
		if _body != null and is_instance_valid(_body):
			_push_heights()

	var plevel: int = prop_level(lv)
	if _props_level != plevel:
		_rebuild_props(data.get("props", []), plevel)
		_props_level = plevel


func _apply_mesh(lv: int, data: Dictionary) -> void:
	var arrays: Array = data.get("mesh_arrays", [])
	if arrays.size() != Mesh.ARRAY_MAX:
		return
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	if verts.is_empty():
		return
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = MatLib.terrain_material()
	mi.custom_aabb = data.get("aabb", AABB())
	if lv <= 1:
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	else:
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# The new mesh is added before the old one goes away: no hole, ever.
	add_child(mi)
	var previous: MeshInstance3D = _meshes[lv]
	_meshes[lv] = mi
	if previous != null and is_instance_valid(previous):
		previous.queue_free()


func _show_only(lv: int) -> void:
	for k in LOD_COUNT:
		var mi: MeshInstance3D = _meshes[k]
		if mi != null and is_instance_valid(mi):
			mi.visible = (k == lv)


## Swaps the visual LOD. Returns true when the chunk needs a rebuild because the
## data for that lod is missing.
func set_lod(new_lod: int) -> bool:
	var lv: int = clampi(new_lod, 0, LOD_COUNT - 1)
	var mi: MeshInstance3D = _meshes[lv]
	if mi == null or not is_instance_valid(mi):
		# Keep whatever is currently on screen until the new data lands.
		return true
	if lv != lod:
		_show_only(lv)
		lod = lv
	var plevel: int = prop_level(lv)
	return _props_level != plevel and plevel != PROPS_NONE


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------

## Adds/removes the HeightMapShape3D collision (only the closest ring has it).
func set_collision_enabled(enabled: bool) -> void:
	if not enabled:
		if _body != null and is_instance_valid(_body):
			_body.queue_free()
		_body = null
		return
	if _body != null and is_instance_valid(_body):
		return
	if _heights.size() != COLLISION_RES * COLLISION_RES:
		# Safety net: the tile was streamed in at a coarse LOD but the player
		# stands on it, so sample the collision grid right now rather than let
		# him fall through the world.
		if _hf_ref == null:
			return
		_sample_heights()
	var shape := HeightMapShape3D.new()
	shape.map_width = COLLISION_RES
	shape.map_depth = COLLISION_RES
	shape.map_data = _heights
	var cs := CollisionShape3D.new()
	cs.shape = shape
	# The shape spans (COLLISION_RES - 1) units, stretch it over the 64 m tile.
	var s: float = TILE / float(COLLISION_RES - 1)
	cs.scale = Vector3(s, 1.0, s)
	cs.position = Vector3(TILE * 0.5, 0.0, TILE * 0.5)
	var body := StaticBody3D.new()
	body.name = "Ground"
	body.collision_layer = Layers.TERRAIN
	body.collision_mask = 0
	body.add_child(cs)
	add_child(body)
	_body = body


func has_collision() -> bool:
	return _body != null and is_instance_valid(_body)


## True when the LOD 0 heights are already here, so set_collision_enabled()
## costs nothing. When false it has to sample the heightfield on the spot, which
## is expensive: the caller should budget those.
func has_height_data() -> bool:
	return _heights.size() == COLLISION_RES * COLLISION_RES


func _sample_heights() -> void:
	_heights.resize(COLLISION_RES * COLLISION_RES)
	var step: float = TILE / float(COLLISION_RES - 1)
	var ox: float = float(tx) * TILE
	var oz: float = float(tz) * TILE
	for j in COLLISION_RES:
		var wz: float = oz + float(j) * step
		for i in COLLISION_RES:
			_heights[j * COLLISION_RES + i] = _hf_ref.height_at(ox + float(i) * step, wz)


func _push_heights() -> void:
	if _body.get_child_count() == 0:
		return
	var cs := _body.get_child(0) as CollisionShape3D
	if cs == null:
		return
	var shape := cs.shape as HeightMapShape3D
	if shape == null:
		return
	shape.map_data = _heights


# ---------------------------------------------------------------------------
# Vegetation and props
# ---------------------------------------------------------------------------

## Sorts the instances into jobs, then lets _process() spend them one per frame.
## Building a whole tile of vegetation in a single frame is a visible hitch.
func _rebuild_props(props: Array, plevel: int) -> void:
	_jobs.clear()
	set_process(false)
	if _props_root != null and is_instance_valid(_props_root):
		_props_root.queue_free()
	_props_root = null
	if props.is_empty():
		return
	var root := Node3D.new()
	root.name = "Props"
	add_child(root)
	_props_root = root

	var batches: Dictionary = {}
	var loose: Array = []
	for raw in props:
		var inst := raw as Scatter.Instance
		if inst == null:
			continue
		if Scatter.is_batched(inst.kind):
			# A MultiMesh carries no collision: is_batched drives the visual,
			# has_collision drives the physics, and both can be true at once.
			if not batches.has(inst.kind):
				batches[inst.kind] = []
			var bucket: Array = batches[inst.kind]
			bucket.append(inst)
		elif plevel == PROPS_FULL:
			loose.append(inst)
	for kind in batches:
		_jobs.append({"kind": int(kind), "list": batches[kind], "level": plevel})
	while not loose.is_empty():
		var slice: Array = loose.slice(0, NODE_JOB_SIZE)
		loose = loose.slice(NODE_JOB_SIZE)
		_jobs.append({"kind": -1, "list": slice, "level": plevel})
	if not _jobs.is_empty():
		set_process(true)


func _process(_delta: float) -> void:
	if _jobs.is_empty() or _props_root == null or not is_instance_valid(_props_root):
		_jobs.clear()
		set_process(false)
		return
	var job: Dictionary = _jobs.pop_front()
	var origin := Vector3(float(tx) * TILE, 0.0, float(tz) * TILE)
	var plevel: int = job["level"]
	var list: Array = job["list"]
	var kind: int = job["kind"]
	if kind >= 0:
		_spawn_batch(kind, list, origin, plevel)
	else:
		for raw in list:
			var inst := raw as Scatter.Instance
			if inst != null:
				_spawn_prop_node(inst, origin, plevel)
	if _jobs.is_empty():
		set_process(false)


## One MultiMesh per prop kind per tile.
func _spawn_batch(kind: int, list: Array, origin: Vector3, plevel: int) -> void:
	if list.is_empty():
		return
	var mesh: Mesh = Meshes.prop_mesh(kind, 0)
	if mesh == null:
		return
	var base: AABB = mesh.get_aabb()
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = list.size()
	var box := AABB()
	var collides: bool = plevel == PROPS_FULL and Scatter.has_collision(kind)
	for i in list.size():
		var inst := list[i] as Scatter.Instance
		if inst == null:
			continue
		var local: Vector3 = inst.position - origin
		var b3 := Basis(Vector3.UP, inst.rotation).scaled(Vector3.ONE * maxf(inst.scale, 0.01))
		var xf := Transform3D(b3, local)
		mm.set_instance_transform(i, xf)
		mm.set_instance_color(i, inst.tint)
		var ib: AABB = xf * base
		box = ib if i == 0 else box.merge(ib)
		if collides:
			_spawn_prop_body(inst, local)
	var mmi := MultiMeshInstance3D.new()
	mmi.name = "Batch_%d" % kind
	mmi.multimesh = mm
	# Without an explicit AABB the culler guesses wrong and the vegetation
	# flickers as the camera turns.
	mmi.custom_aabb = box.grow(1.0)
	if plevel == PROPS_FULL:
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	else:
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_props_root.add_child(mmi)


func _spawn_prop_node(inst: Scatter.Instance, origin: Vector3, plevel: int) -> void:
	var mesh: Mesh = Meshes.prop_mesh(inst.kind, 0)
	var local: Vector3 = inst.position - origin
	if mesh != null:
		var holder := Node3D.new()
		holder.position = local
		holder.rotation.y = inst.rotation
		holder.scale = Vector3.ONE * maxf(inst.scale, 0.01)
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		if plevel == PROPS_FULL:
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		else:
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		holder.add_child(mi)
		_props_root.add_child(holder)
	if Scatter.has_collision(inst.kind):
		_spawn_prop_body(inst, local)


## Collision body kept outside of the scaled visual node, because
## Scatter.collision_size already accounts for the instance scale.
func _spawn_prop_body(inst: Scatter.Instance, local: Vector3) -> void:
	var size: Vector2 = Scatter.collision_size(inst.kind, inst.scale)
	if size.x <= 0.01 or size.y <= 0.01:
		return
	var body := StaticBody3D.new()
	body.collision_layer = Layers.PROP
	body.collision_mask = 0
	body.position = local + Vector3(0.0, size.y * 0.5, 0.0)
	var cs := CollisionShape3D.new()
	cs.shape = _cylinder_shape(size)
	body.add_child(cs)
	_props_root.add_child(body)


static func _cylinder_shape(size: Vector2) -> CylinderShape3D:
	var r: float = maxf(snappedf(size.x, 0.05), 0.05)
	var h: float = maxf(snappedf(size.y, 0.25), 0.25)
	var key := "%.2f_%.2f" % [r, h]
	var cached: CylinderShape3D = _shape_cache.get(key, null)
	if cached != null:
		return cached
	var shape := CylinderShape3D.new()
	shape.radius = r
	shape.height = h
	_shape_cache[key] = shape
	return shape
