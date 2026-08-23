class_name VoxelWorld
extends Node3D
## Chunk streaming, block editing and the worker thread pool.
##
## Lifecycle of a chunk, one state at a time:
##
##   MISSING -> GENERATING -> GENERATED -> MESHING -> LIVE
##
## Generation only needs the chunk itself, so it parallelises freely. Meshing
## needs the eight surrounding chunks because ambient occlusion samples diagonal
## neighbours, so a chunk is only queued for meshing once its whole 3x3
## neighbourhood has reached GENERATED. That is why the generation radius is one
## chunk wider than the visible radius.
##
## Threading rules, kept deliberately narrow so they are easy to hold in mind:
##   - Worker threads may read ChunkData and call TerrainGen and SaveManager.
##   - Worker threads never touch the scene tree.
##   - The padded volume is copied out under the mutex, then the expensive
##     meshing runs unlocked. Nothing else reads voxel data without the lock.
##   - Only the main thread mutates ChunkData, and only from set_block.

signal chunk_ready(cx: int, cz: int)
signal block_changed(cell: Vector3i, old_id: int, new_id: int)
signal initial_load_finished()

const WORLD_HEIGHT := ChunkData.SIZE_Y

## Extra ring generated beyond the visible radius so edge chunks can be meshed.
const GEN_MARGIN := 1

## Chunks are only dropped once they are this far past the visible radius,
## which stops a player pacing across a border from thrashing the pool.
const UNLOAD_MARGIN := 3

## Mesh uploads are the only unavoidable main thread cost, so they are rationed.
const UPLOADS_PER_FRAME := 3

## Cap on queued generation jobs, to keep the queue responsive to a moving
## player instead of committing to a stale ordering.
const GEN_QUEUE_LIMIT := 48

enum State { GENERATING, GENERATED, MESHING, LIVE }

enum Job { GENERATE, MESH }

var _seed: int = 0
var _world_name: String = "default"

var _atlas: Texture2DArray
var _materials: Array[Material] = []
var _save: SaveManager
var _terrain_main: TerrainGen

# --- shared state, guarded by _mutex -----------------------------------------
var _mutex := Mutex.new()
var _semaphore := Semaphore.new()
var _threads: Array[Thread] = []
var _terrains: Array[TerrainGen] = []
var _exiting := false

var _chunks: Dictionary = {}        ## Vector2i -> ChunkData
var _states: Dictionary = {}        ## Vector2i -> State
var _versions: Dictionary = {}      ## Vector2i -> int, bumped on every edit
var _queue: Array = []              ## pending jobs, each [Job, Vector2i, int version]
var _results: Array = []            ## finished jobs, same shape plus payload
var _in_flight: int = 0
# -----------------------------------------------------------------------------

var _nodes: Dictionary = {}         ## Vector2i -> ChunkNode, main thread only
var _pool: Array[ChunkNode] = []    ## recycled ChunkNode instances
var _spawn: Vector3 = Vector3.ZERO
var _initial_done := false
var _center := Vector2i(0, 0)
var _ready_for_jobs := false


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

## Floor division of a world coordinate by the chunk size. Arithmetic shift is
## used on purpose: it floors correctly for negatives, where GDScript integer
## division truncates toward zero and would fold -1 and 0 into the same chunk.
## Valid only while the chunk footprint stays 16 wide.
static func chunk_of(w: int) -> int:
	return w >> 4


## Positive remainder of a world coordinate inside its chunk.
static func local_of(w: int) -> int:
	return w & 15


# ---------------------------------------------------------------------------
# Setup and teardown
# ---------------------------------------------------------------------------

func setup(world_seed: int, world_name: String) -> void:
	assert(ChunkData.SIZE_X == 16 and ChunkData.SIZE_Z == 16,
		"chunk_of and local_of assume a 16 wide chunk footprint")
	_world_name = world_name

	_atlas = VoxelAtlas.build()
	_materials = VoxelMaterials.build(_atlas)

	# The seed stored in the world meta wins over the seed passed in: an
	# existing world must keep the terrain it was generated with even if the
	# settings seed changed since. Only a world without a stored seed (fresh
	# folder, or a save predating the seed field) adopts the caller's seed.
	# JSON numbers come back as floats, hence the double type test.
	_save = SaveManager.new(world_name)
	var meta := _save.load_meta()
	var stored_seed := 0
	var raw_seed: Variant = meta.get("seed")
	if raw_seed is int or raw_seed is float:
		stored_seed = int(raw_seed)
	_seed = stored_seed if stored_seed != 0 else world_seed

	_terrain_main = TerrainGen.new(_seed)
	_spawn = _terrain_main.spawn_point()

	# The player wakes up inside the timber house of the nearest village. The
	# search is deterministic, so it beats any spawn stored by an older save;
	# worlds without a reachable village fall back to the stored or open-air
	# spawn point.
	var home := _terrain_main.nearest_house(int(floor(_spawn.x)), int(floor(_spawn.z)))
	if home != Vector4i.ZERO:
		_spawn = Vector3(float(home.x) + 0.5, float(home.y) + 1.0, float(home.z) + 0.5)
	elif meta.has("spawn_x") and meta.has("spawn_y") and meta.has("spawn_z"):
		_spawn = Vector3(float(meta["spawn_x"]), float(meta["spawn_y"]), float(meta["spawn_z"]))
	meta["seed"] = _seed
	meta["spawn_x"] = _spawn.x
	meta["spawn_y"] = _spawn.y
	meta["spawn_z"] = _spawn.z
	_save.save_meta(meta)

	var worker_count: int = clampi(OS.get_processor_count() - 2, 1, 4)
	for i in worker_count:
		_terrains.append(TerrainGen.new(_seed))
	for i in worker_count:
		var t := Thread.new()
		t.start(_worker_loop.bind(i))
		_threads.append(t)

	_center = Vector2i(chunk_of(int(floor(_spawn.x))), chunk_of(int(floor(_spawn.z))))
	_ready_for_jobs = true
	update_streaming(_spawn)


func shutdown() -> void:
	if not _ready_for_jobs:
		return
	_ready_for_jobs = false

	_mutex.lock()
	_exiting = true
	_queue.clear()
	_mutex.unlock()
	for i in _threads.size():
		_semaphore.post()
	for t in _threads:
		t.wait_to_finish()
	_threads.clear()

	save_all()


func save_all() -> void:
	if _save == null:
		return
	_mutex.lock()
	var dirty: Array = []
	for key in _chunks:
		var data: ChunkData = _chunks[key]
		if data.modified:
			dirty.append([key, data.serialize()])
			data.modified = false
	_mutex.unlock()
	for entry in dirty:
		var key: Vector2i = entry[0]
		_save.save_chunk(key.x, key.y, entry[1])


func materials() -> Array[Material]:
	return _materials


func atlas() -> Texture2DArray:
	return _atlas


func spawn_point() -> Vector3:
	return _spawn


## World metadata (JSON), used by main to persist player state alongside the
## chunk saves. Returns an empty Dictionary when nothing is stored yet.
func load_meta() -> Dictionary:
	if _save == null:
		return {}
	return _save.load_meta()


## Merges `extra` into the stored metadata and writes it back.
func store_meta(extra: Dictionary) -> void:
	if _save == null:
		return
	var meta := _save.load_meta()
	meta.merge(extra, true)
	_save.save_meta(meta)


# ---------------------------------------------------------------------------
# Block access
# ---------------------------------------------------------------------------

## Reads a cell in world coordinates. Returns AIR outside the vertical range and
## inside chunks that are not loaded yet. Use has_chunk_at to tell those apart:
## collision code has to treat unloaded ground as solid, not as empty air.
func get_block(wx: int, wy: int, wz: int) -> int:
	if wy < 0 or wy >= WORLD_HEIGHT:
		return Blocks.AIR
	var key := Vector2i(chunk_of(wx), chunk_of(wz))
	_mutex.lock()
	var data: ChunkData = _chunks.get(key)
	var id := Blocks.AIR
	if data != null:
		id = data.voxels[(local_of(wx) * ChunkData.SIZE_Z + local_of(wz)) * ChunkData.SIZE_Y + wy]
	_mutex.unlock()
	return id


func is_solid(wx: int, wy: int, wz: int) -> bool:
	return Blocks.collides(get_block(wx, wy, wz))


## True once the chunk covering this column holds voxel data. Meshing may still
## be pending, but the terrain is decided and safe to collide against.
func has_chunk_at(wx: int, wz: int) -> bool:
	var key := Vector2i(chunk_of(wx), chunk_of(wz))
	_mutex.lock()
	var state = _states.get(key)
	_mutex.unlock()
	return state != null and state != State.GENERATING


## Writes a cell and schedules every mesh that the change can affect. Returns
## false when the cell is out of range or its chunk is not loaded.
func set_block(wx: int, wy: int, wz: int, id: int) -> bool:
	if wy < 0 or wy >= WORLD_HEIGHT:
		return false
	var key := Vector2i(chunk_of(wx), chunk_of(wz))
	var lx := local_of(wx)
	var lz := local_of(wz)

	_mutex.lock()
	var data: ChunkData = _chunks.get(key)
	if data == null or _states.get(key) == State.GENERATING:
		_mutex.unlock()
		return false
	var old: int = data.get_local(lx, wy, lz)
	if old == id:
		_mutex.unlock()
		return true
	data.set_local(lx, wy, lz, id)
	data.modified = true
	_mutex.unlock()

	# Ambient occlusion reads diagonal neighbours, so any chunk holding a cell
	# within one block of the edit has a stale mesh, diagonals included.
	for dx in [-1, 0, 1]:
		for dz in [-1, 0, 1]:
			var touches_x: bool = dx == 0 or (dx == -1 and lx == 0) or (dx == 1 and lx == ChunkData.SIZE_X - 1)
			var touches_z: bool = dz == 0 or (dz == -1 and lz == 0) or (dz == 1 and lz == ChunkData.SIZE_Z - 1)
			if touches_x and touches_z:
				_request_mesh(Vector2i(key.x + dx, key.y + dz), true)

	block_changed.emit(Vector3i(wx, wy, wz), old, id)
	return true


func surface_height(wx: int, wz: int) -> int:
	return _terrain_main.surface_height(wx, wz)


func biome_name_at(wx: int, wz: int) -> String:
	return TerrainGen.biome_name(_terrain_main.biome_at(wx, wz))


func grass_color_at(wx: int, wz: int) -> Color:
	return _terrain_main.grass_color_at(wx, wz)


## Deterministic settlement metadata for actors. Structure blocks themselves
## are emitted by TerrainGen; this exposes only the owning house anchors.
func houses_in_chunk(cx: int, cz: int) -> Array[Vector4i]:
	return _terrain_main.houses_in_chunk(cx, cz)


func pens_in_chunk(cx: int, cz: int) -> Array[Vector4i]:
	return _terrain_main.pens_in_chunk(cx, cz)


func pending_jobs() -> int:
	_mutex.lock()
	var n: int = _queue.size() + _in_flight + _results.size()
	_mutex.unlock()
	return n


func loaded_chunk_count() -> int:
	return _nodes.size()


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

func update_streaming(center: Vector3) -> void:
	if not _ready_for_jobs:
		return
	_center = Vector2i(chunk_of(int(floor(center.x))), chunk_of(int(floor(center.z))))
	_schedule()
	_drain_results()
	_check_initial_load()


func _schedule() -> void:
	var view: int = Game.render_distance
	var gen_radius: int = view + GEN_MARGIN
	var unload_radius: int = view + UNLOAD_MARGIN

	_mutex.lock()

	# Drop anything far away, saving player edits on the way out.
	var to_unload: Array = []
	for key in _chunks:
		var d: int = maxi(absi(key.x - _center.x), absi(key.y - _center.y))
		if d > unload_radius and _states.get(key) != State.MESHING:
			to_unload.append(key)
	for key in to_unload:
		var data: ChunkData = _chunks[key]
		if data.modified:
			_save.save_chunk(key.x, key.y, data.serialize())
		_chunks.erase(key)
		_states.erase(key)
		_versions.erase(key)

	var queued: int = _queue.size()
	var posts := 0

	# Nearest first: a player walking forward should see the ground appear ahead
	# of them, not in whatever order the dictionary happens to iterate.
	var wanted: Array = []
	for dx in range(-gen_radius, gen_radius + 1):
		for dz in range(-gen_radius, gen_radius + 1):
			var key := Vector2i(_center.x + dx, _center.y + dz)
			if _states.has(key):
				continue
			var dist_sq: int = dx * dx + dz * dz
			if dist_sq > gen_radius * gen_radius:
				continue
			wanted.append([dist_sq, key])
	wanted.sort_custom(func(a, b): return a[0] < b[0])

	for entry in wanted:
		if queued >= GEN_QUEUE_LIMIT:
			break
		var key: Vector2i = entry[1]
		_states[key] = State.GENERATING
		_versions[key] = 0
		_queue.append([Job.GENERATE, key, 0])
		queued += 1
		posts += 1

	# Anything already generated whose neighbourhood is complete can be meshed.
	var meshable: Array = []
	for key in _states:
		if _states[key] != State.GENERATED:
			continue
		var d: int = maxi(absi(key.x - _center.x), absi(key.y - _center.y))
		if d > view:
			continue
		if not _neighbourhood_ready_locked(key):
			continue
		var ddx: int = key.x - _center.x
		var ddz: int = key.y - _center.y
		meshable.append([ddx * ddx + ddz * ddz, key])
	meshable.sort_custom(func(a, b): return a[0] < b[0])

	for entry in meshable:
		var key: Vector2i = entry[1]
		_states[key] = State.MESHING
		_queue.append([Job.MESH, key, _versions.get(key, 0)])
		posts += 1

	_mutex.unlock()

	for i in posts:
		_semaphore.post()


## Caller must hold _mutex. A chunk may only be meshed once every one of its
## eight neighbours holds voxel data, otherwise the border faces and the ambient
## occlusion on them would be computed against air and have to be redone.
func _neighbourhood_ready_locked(key: Vector2i) -> bool:
	for dx in [-1, 0, 1]:
		for dz in [-1, 0, 1]:
			var state = _states.get(Vector2i(key.x + dx, key.y + dz))
			if state == null or state == State.GENERATING:
				return false
	return true


## Queues a remesh. Player edits pass urgent = true and jump the queue so the
## world reacts on the next frame instead of behind a wall of streaming work.
func _request_mesh(key: Vector2i, urgent: bool) -> void:
	_mutex.lock()
	var state = _states.get(key)
	if state == null or state == State.GENERATING:
		_mutex.unlock()
		return
	if not _neighbourhood_ready_locked(key):
		# Not meshable yet. Leaving it GENERATED lets _schedule pick it up as
		# soon as the missing neighbour lands.
		if state == State.LIVE:
			_states[key] = State.GENERATED
		_mutex.unlock()
		return
	_versions[key] = int(_versions.get(key, 0)) + 1
	_states[key] = State.MESHING
	var job := [Job.MESH, key, _versions[key]]
	if urgent:
		_queue.push_front(job)
	else:
		_queue.append(job)
	_mutex.unlock()
	_semaphore.post()


# ---------------------------------------------------------------------------
# Worker threads
# ---------------------------------------------------------------------------

func _worker_loop(index: int) -> void:
	var terrain: TerrainGen = _terrains[index]
	while true:
		_semaphore.wait()

		_mutex.lock()
		if _exiting:
			_mutex.unlock()
			return
		if _queue.is_empty():
			_mutex.unlock()
			continue
		var job: Array = _queue.pop_front()
		_in_flight += 1
		_mutex.unlock()

		var kind: Job = job[0]
		var key: Vector2i = job[1]
		var version: int = job[2]

		if kind == Job.GENERATE:
			var data := ChunkData.new(key.x, key.y)
			var stored := _save.load_chunk(key.x, key.y)
			if stored.is_empty() or not data.deserialize(stored):
				terrain.generate(data)
			else:
				data.modified = false
			_mutex.lock()
			_results.append([Job.GENERATE, key, version, data])
			_in_flight -= 1
			_mutex.unlock()
			continue

		# Meshing. Copy the padded volume out under the lock, then do the
		# expensive part unlocked so workers do not serialise on each other.
		_mutex.lock()
		var still_wanted: bool = _states.get(key) == State.MESHING and int(_versions.get(key, -1)) == version
		var padded := PackedByteArray()
		if still_wanted:
			var neighbours: Array = []
			neighbours.resize(9)
			for dx in [-1, 0, 1]:
				for dz in [-1, 0, 1]:
					neighbours[(dx + 1) * 3 + (dz + 1)] = _chunks.get(Vector2i(key.x + dx, key.y + dz))
			padded = Mesher.build_padded(neighbours)
		_mutex.unlock()

		if not still_wanted:
			_mutex.lock()
			_in_flight -= 1
			_mutex.unlock()
			continue

		var tints := _build_tints(terrain, key.x, key.y)
		var mesh_data := Mesher.build_mesh_data(padded, tints)

		_mutex.lock()
		_results.append([Job.MESH, key, version, mesh_data])
		_in_flight -= 1
		_mutex.unlock()


## Biome grass colours for the padded footprint, in the layout the mesher wants:
## PW by PD entries indexed px * PD + pz, one world column per entry.
func _build_tints(terrain: TerrainGen, cx: int, cz: int) -> PackedColorArray:
	var out := PackedColorArray()
	out.resize(Mesher.PW * Mesher.PD)
	var base_x: int = cx * ChunkData.SIZE_X - Mesher.PAD
	var base_z: int = cz * ChunkData.SIZE_Z - Mesher.PAD
	for px in Mesher.PW:
		var wx: int = base_x + px
		var row: int = px * Mesher.PD
		for pz in Mesher.PD:
			out[row + pz] = terrain.grass_color_at(wx, base_z + pz)
	return out


# ---------------------------------------------------------------------------
# Main thread result handling
# ---------------------------------------------------------------------------

func _drain_results() -> void:
	var uploads := 0
	while true:
		_mutex.lock()
		if _results.is_empty():
			_mutex.unlock()
			return
		# Generation results are cheap to install, so take them all. Mesh
		# uploads touch the rendering server and are rationed per frame.
		var pick := -1
		for i in _results.size():
			if _results[i][0] == Job.GENERATE:
				pick = i
				break
		if pick < 0:
			if uploads >= UPLOADS_PER_FRAME:
				_mutex.unlock()
				return
			pick = 0
		var result: Array = _results.pop_at(pick)
		_mutex.unlock()

		var kind: Job = result[0]
		var key: Vector2i = result[1]
		var version: int = result[2]

		if kind == Job.GENERATE:
			_mutex.lock()
			# A chunk unloaded while its job was in flight must not come back.
			if _states.get(key) == State.GENERATING:
				_chunks[key] = result[3]
				_states[key] = State.GENERATED
			_mutex.unlock()
			continue

		uploads += 1
		_mutex.lock()
		var accept: bool = _states.get(key) == State.MESHING and int(_versions.get(key, -1)) == version
		if accept:
			_states[key] = State.LIVE
		_mutex.unlock()
		if not accept:
			continue

		_apply_mesh(key, result[3])
		chunk_ready.emit(key.x, key.y)


func _apply_mesh(key: Vector2i, mesh_data: Dictionary) -> void:
	var node: ChunkNode = _nodes.get(key)
	if node == null:
		node = _pool.pop_back() if not _pool.is_empty() else null
		if node == null:
			node = ChunkNode.new()
			add_child(node)
		node.setup(key.x, key.y, _materials)
		_nodes[key] = node
	node.apply(mesh_data)


func _process(_delta: float) -> void:
	if not _ready_for_jobs:
		return
	_release_orphan_nodes()


## Nodes whose chunk data has been unloaded go back to the pool.
func _release_orphan_nodes() -> void:
	if _nodes.is_empty():
		return
	var stale: Array = []
	_mutex.lock()
	for key in _nodes:
		if not _states.has(key):
			stale.append(key)
	_mutex.unlock()
	for key in stale:
		var node: ChunkNode = _nodes[key]
		node.release()
		_nodes.erase(key)
		if _pool.size() < 64:
			_pool.append(node)
		else:
			node.queue_free()


## The player may only be released once the ground beneath the spawn point and
## its immediate ring are drawn, otherwise they drop through a hole.
func _check_initial_load() -> void:
	if _initial_done:
		return
	var spawn_chunk := Vector2i(chunk_of(int(floor(_spawn.x))), chunk_of(int(floor(_spawn.z))))
	_mutex.lock()
	var ok := true
	for dx in [-1, 0, 1]:
		for dz in [-1, 0, 1]:
			if _states.get(Vector2i(spawn_chunk.x + dx, spawn_chunk.y + dz)) != State.LIVE:
				ok = false
				break
		if not ok:
			break
	_mutex.unlock()
	if ok:
		_initial_done = true
		initial_load_finished.emit()
