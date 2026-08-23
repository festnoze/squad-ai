class_name GameWorld
extends Node3D
## Open world streaming: terrain chunks, vegetation, water and sites.
##
## Threading model
## ---------------
## Chunk data is produced by TerrainChunk.build_data(), a pure static function
## that only reads the (immutable) Heightfield, so it runs on WorkerThreadPool
## tasks. Finished payloads are pushed into _results behind a Mutex and consumed
## by the main thread inside update_streaming(), a couple of chunks per frame.
## Node creation NEVER happens off thread.
##
## shutdown() waits for every task still in flight before freeing anything.
## Skipping that leaves the process hanging forever on exit.

signal world_ready()
signal chunk_ready(tile: Vector2i)

const TILE := 64.0
## Playable square is 4096 m centred on the origin, plus one tile of margin so
## the border never shows a void.
const MIN_TILE := -33
const MAX_TILE := 32

## LOD rings, in tiles of Chebyshev distance around the focus tile.
const RING_LOD0 := 2
const RING_LOD1 := 4
const RING_LOD2 := 7
## Only the closest ring carries a collision shape.
const COLLISION_RING := 2
## Hysteresis: collision is dropped one ring further out than it is added.
const COLLISION_KEEP := 3

## Node building budget per frame, in credits. A close chunk costs the whole
## budget, so it lands alone and walking stays smooth; two far ones may share a
## frame. Never more than two chunks per frame either way.
const APPLY_BUDGET := 2
const APPLY_COST: PackedInt32Array = [2, 2, 1, 1]

const SITE_LOAD_DIST := 700.0
const SITE_UNLOAD_DIST := 900.0

const WATER_CELL := 128.0
const WATER_RADIUS := 6
## Water cells probed per frame outside of the initial fill.
const WATER_PROBE_BUDGET := 2

## Vertical offset applied to the spawn point so the player starts standing.
const SPAWN_HEIGHT := 1.0

## Periodic re dispatch, catches requests dropped while a task was in flight.
const RESCAN_MS := 700

var _layout: Layout = null
var _hf: Heightfield = null

var _chunks: Dictionary = {}          # Vector2i -> TerrainChunk
var _wanted: Dictionary = {}          # Vector2i -> int (lod)
var _queue: Array[Dictionary] = []    # pending build requests, nearest first
var _queued: Dictionary = {}          # Vector2i -> int
var _inflight: Dictionary = {}        # task id -> Vector2i
var _inflight_tiles: Dictionary = {}  # Vector2i -> int
var _results: Array[Dictionary] = []  # guarded by _mutex
var _mutex: Mutex = null
var _max_tasks := 3

var _offsets: Array[Vector2i] = []
var _center := Vector2i(9999, 9999)
var _view_tiles := 0
var _last_scan_ms := 0
## Tiles allowed to sample their collision heights on the main thread, per frame.
var _sync_ground_budget := 1
var _started := false
var _shutdown_done := false

var _sites: Dictionary = {}           # site id -> SiteBuilder.BuiltSite
var _site_queue: Array[int] = []
var _site_queued: Dictionary = {}

var _water: MultiMeshInstance3D = null
var _water_cell := Vector2i(9999, 9999)
var _water_known: Dictionary = {}     # Vector2i -> bool
var _water_pending := false


func _init() -> void:
	_mutex = Mutex.new()
	_max_tasks = clampi(OS.get_processor_count() - 1, 1, 6)


func _exit_tree() -> void:
	# Last line of defence: without this the process can hang on exit.
	shutdown()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

func setup(world_seed: int) -> void:
	if _started:
		return
	_started = true
	_shutdown_done = false
	_layout = Layout.new(world_seed)
	_hf = Heightfield.new(_layout)
	_hf.bake_sites()
	_view_tiles = _view_distance()
	_build_offsets(_view_tiles)
	_build_water()
	_prime_spawn_area()
	_last_scan_ms = Time.get_ticks_msec()
	# Deferred so that whoever connects right after setup() still gets it.
	_announce_ready.call_deferred()


func _announce_ready() -> void:
	if not _shutdown_done:
		world_ready.emit()


func layout() -> Layout:
	return _layout


func heightfield() -> Heightfield:
	return _hf


## The tile under the spawn point and its eight neighbours are built on the main
## thread, before anything else runs, so the player always has ground to land on.
func _prime_spawn_area() -> void:
	var sp: Vector2 = _layout.spawn_point()
	var t := _tile_of(sp.x, sp.y)
	_center = t
	for dz in range(-1, 2):
		for dx in range(-1, 2):
			var tt := Vector2i(t.x + dx, t.y + dz)
			if not _tile_in_world(tt):
				continue
			var data := TerrainChunk.build_data(_hf, tt.x, tt.y, 0)
			var chunk := _make_chunk(tt)
			chunk.apply(_hf, tt.x, tt.y, 0, data)
			chunk.set_collision_enabled(true)
			chunk_ready.emit(tt)
	_rebuild_wanted()
	# Whole window at once: this happens during loading, not during play.
	_update_water(Vector3(sp.x, 0.0, sp.y), true)


func _make_chunk(t: Vector2i) -> TerrainChunk:
	var chunk := TerrainChunk.new()
	_chunks[t] = chunk
	add_child(chunk)
	return chunk


# ---------------------------------------------------------------------------
# Streaming, called every frame by Main
# ---------------------------------------------------------------------------

func update_streaming(focus: Vector3) -> void:
	if _hf == null or _shutdown_done:
		return
	# At most one tile per frame may pay for a synchronous height sampling.
	_sync_ground_budget = 1
	var now := Time.get_ticks_msec()
	var vd := _view_distance()
	var t := _tile_of(focus.x, focus.z)
	if vd != _view_tiles:
		_view_tiles = vd
		_build_offsets(vd)
		_center = t
		_last_scan_ms = now
		_rebuild_wanted()
	elif t != _center:
		_center = t
		_last_scan_ms = now
		_rebuild_wanted()
	elif now - _last_scan_ms >= RESCAN_MS:
		# Cheap periodic pass: no set rebuild, only the missing requests.
		_last_scan_ms = now
		_queue_missing()
		_update_collision_ring()

	# Building a site is by far the heaviest thing that can land on the main
	# thread, so it never shares its frame with a chunk apply.
	if _update_sites(focus):
		_reap_tasks()
	else:
		_collect_results()
	_dispatch()
	_update_water(focus)


## Recomputes the wanted LOD of every tile in range and unloads what fell out.
## Only called when the focus tile or the view distance actually changed.
func _rebuild_wanted() -> void:
	_wanted.clear()
	var vd := _view_tiles
	for off in _offsets:
		var d: int = maxi(absi(off.x), absi(off.y))
		if d > vd:
			continue
		var t := Vector2i(_center.x + off.x, _center.y + off.y)
		if not _tile_in_world(t):
			continue
		_wanted[t] = _lod_for(d)

	for key in _chunks.keys():
		var t2: Vector2i = key
		if _cheb(t2) > vd + 1:
			var dead: TerrainChunk = _chunks[t2]
			_chunks.erase(t2)
			if is_instance_valid(dead):
				dead.queue_free()

	_queue_missing()
	_update_collision_ring()


## Queues every tile that is missing or stuck at the wrong LOD, nearest first.
func _queue_missing() -> void:
	_queue.clear()
	_queued.clear()
	var vd := _view_tiles
	# _offsets is sorted by distance, so the queue comes out sorted too.
	for off in _offsets:
		var d2: int = maxi(absi(off.x), absi(off.y))
		if d2 > vd:
			continue
		var t3 := Vector2i(_center.x + off.x, _center.y + off.y)
		if not _wanted.has(t3):
			continue
		var lv: int = _wanted[t3]
		var chunk: TerrainChunk = _chunks.get(t3, null)
		var needs := true
		if chunk != null and is_instance_valid(chunk):
			# set_lod keeps the old mesh on screen when the new one is missing.
			needs = chunk.set_lod(lv)
		if not needs:
			continue
		if int(_inflight_tiles.get(t3, -1)) == lv:
			continue
		if int(_queued.get(t3, -1)) == lv:
			continue
		_queued[t3] = lv
		_queue.append({"t": t3, "l": lv})


## Enables the heightmap collision on the closest ring, drops it further out.
func _update_collision_ring() -> void:
	for key in _chunks.keys():
		var t: Vector2i = key
		var chunk: TerrainChunk = _chunks[t]
		if not is_instance_valid(chunk):
			continue
		var d := _cheb(t)
		if d <= COLLISION_RING:
			if not chunk.has_collision():
				_try_enable_collision(chunk, d)
		elif d > COLLISION_KEEP and chunk.has_collision():
			chunk.set_collision_enabled(false)


## Turning the collision on costs nothing once the LOD 0 heights are there. When
## they are not, the chunk has to sample the heightfield on the spot (about a
## thousand calls), so only the tiles the player could actually fall through are
## allowed to do it, one per frame.
func _try_enable_collision(chunk: TerrainChunk, distance: int) -> void:
	if chunk.has_height_data():
		chunk.set_collision_enabled(true)
		return
	if distance > 1 or _sync_ground_budget <= 0:
		return
	_sync_ground_budget -= 1
	chunk.set_collision_enabled(true)


func _dispatch() -> void:
	var slots := _max_tasks - _inflight.size()
	while slots > 0 and not _queue.is_empty():
		var req: Dictionary = _queue.pop_front()
		var t: Vector2i = req["t"]
		var lv: int = req["l"]
		if int(_queued.get(t, -1)) == lv:
			_queued.erase(t)
		if int(_wanted.get(t, -1)) != lv:
			continue
		if _inflight_tiles.has(t):
			continue
		var id := WorkerThreadPool.add_task(
				Callable(self, "_worker_build").bind(t, lv), false, "cow_chunk")
		_inflight[id] = t
		_inflight_tiles[t] = lv
		slots -= 1


## Runs on a worker thread. Reads the heightfield only, never the scene.
func _worker_build(t: Vector2i, lv: int) -> void:
	# A task that has not started yet when shutdown lands drops out at once,
	# which is what keeps a scene reload from waiting on the whole backlog.
	_mutex.lock()
	var stopping: bool = _shutdown_done
	_mutex.unlock()
	if stopping:
		return
	var data := TerrainChunk.build_data(_hf, t.x, t.y, lv)
	_mutex.lock()
	if not _shutdown_done:
		_results.append({"t": t, "l": lv, "d": data})
	_mutex.unlock()


## Joins the tasks that are done. Always called, even on a frame where no chunk
## is applied, so that no task id is ever left dangling in the pool.
func _reap_tasks() -> void:
	for key in _inflight.keys():
		var id: int = key
		if WorkerThreadPool.is_task_completed(id):
			WorkerThreadPool.wait_for_task_completion(id)
			var t: Vector2i = _inflight[id]
			_inflight.erase(id)
			if _inflight_tiles.has(t):
				_inflight_tiles.erase(t)


func _collect_results() -> void:
	_reap_tasks()
	var budget := APPLY_BUDGET
	while budget > 0:
		_mutex.lock()
		var item: Dictionary = {}
		if not _results.is_empty():
			item = _results.pop_front()
		_mutex.unlock()
		if item.is_empty():
			return
		budget -= _apply_result(item)


func _apply_result(item: Dictionary) -> int:
	if _shutdown_done:
		return APPLY_BUDGET
	var t: Vector2i = item["t"]
	var lv: int = clampi(int(item["l"]), 0, TerrainChunk.LOD_COUNT - 1)
	var data: Dictionary = item["d"]
	if data.is_empty():
		return 1
	var chunk: TerrainChunk = _chunks.get(t, null)
	if chunk == null or not is_instance_valid(chunk):
		if not _wanted.has(t):
			return 1              # the tile drifted out of range while building
		chunk = _make_chunk(t)
	chunk.apply(_hf, t.x, t.y, lv, data)
	var d := _cheb(t)
	if d <= COLLISION_RING and not chunk.has_collision():
		_try_enable_collision(chunk, d)
	chunk_ready.emit(t)
	return APPLY_COST[lv]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

## Ground height under a world position (terrain only, ignores structures).
func ground_y(x: float, z: float) -> float:
	if _hf == null:
		return 0.0
	return _hf.height_at(x, z)


## Player spawn, on the ground, already offset to standing height.
func spawn_point() -> Vector3:
	if _layout == null or _hf == null:
		return Vector3(0.0, SPAWN_HEIGHT, 0.0)
	var sp: Vector2 = _layout.spawn_point()
	return Vector3(sp.x, _hf.height_at(sp.x, sp.y) + SPAWN_HEIGHT, sp.y)


## True once the tile under pos has its collision in place. Main waits on this
## before releasing the player, otherwise he falls through the world.
func is_ground_ready(pos: Vector3) -> bool:
	var chunk: TerrainChunk = _chunks.get(_tile_of(pos.x, pos.z), null)
	if chunk == null or not is_instance_valid(chunk):
		return false
	return chunk.has_collision()


func loaded_chunk_count() -> int:
	return _chunks.size()


## Cover points of every loaded site, for the AI.
func cover_points_near(pos: Vector3, radius: float) -> Array:
	var out: Array = []
	var r2 := radius * radius
	for key in _sites:
		var built: SiteBuilder.BuiltSite = _sites[key]
		if built == null:
			continue
		for raw in built.cover:
			var cp := raw as Structures.CoverPoint
			if cp == null:
				continue
			if cp.position.distance_squared_to(pos) <= r2:
				out.append(cp)
	return out


## The BuiltSite for a site id, or null when it is not streamed in.
func built_site(site_id: int) -> SiteBuilder.BuiltSite:
	var built: SiteBuilder.BuiltSite = _sites.get(site_id, null)
	return built


func debug_line() -> String:
	return "Monde: %d tuiles, %d taches, %d en file, %d sites, tuile (%d, %d), vue %d" % [
		_chunks.size(), _inflight.size(), _queue.size(), _sites.size(),
		_center.x, _center.y, _view_tiles]


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

## Sites are built within 700 m and released past 900 m. The gap is what keeps a
## site from being rebuilt at every step on the boundary. Returns true when a
## site was built this frame.
func _update_sites(focus: Vector3) -> bool:
	if _layout == null:
		return false
	var p := Vector2(focus.x, focus.z)
	for raw in _layout.sites:
		var site: Layout.Site = raw
		if site == null:
			continue
		var d := p.distance_to(site.center)
		if d <= SITE_LOAD_DIST:
			if not _sites.has(site.id) and not _site_queued.has(site.id):
				_site_queued[site.id] = true
				_site_queue.append(site.id)
		elif d > SITE_UNLOAD_DIST:
			if _sites.has(site.id):
				_free_site(site.id)
			if _site_queued.has(site.id):
				_site_queued.erase(site.id)
				_site_queue.erase(site.id)

	# One site per frame at most: building one is heavy.
	while not _site_queue.is_empty():
		var id: int = _site_queue.pop_front()
		_site_queued.erase(id)
		if _sites.has(id):
			continue
		_build_site(id)
		return true
	return false


func _build_site(site_id: int) -> void:
	var site: Layout.Site = _layout.site_by_id(site_id)
	if site == null:
		return
	var built: SiteBuilder.BuiltSite = SiteBuilder.build(site, _hf)
	if built == null or built.node == null:
		push_warning("SiteBuilder returned nothing for site %d" % site_id)
		return
	_sites[site_id] = built
	add_child(built.node)


func _free_site(site_id: int) -> void:
	var built: SiteBuilder.BuiltSite = _sites.get(site_id, null)
	_sites.erase(site_id)
	if built != null and built.node != null and is_instance_valid(built.node):
		built.node.queue_free()


# ---------------------------------------------------------------------------
# Water
# ---------------------------------------------------------------------------

func _build_water() -> void:
	var plane := PlaneMesh.new()
	plane.size = Vector2(WATER_CELL, WATER_CELL)
	plane.subdivide_width = 1
	plane.subdivide_depth = 1
	plane.material = MatLib.get_material("water")
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = plane
	mm.instance_count = 0
	_water = MultiMeshInstance3D.new()
	_water.name = "Water"
	_water.multimesh = mm
	_water.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_water)


## A grid of quads following the player. A cell is only instanced when the
## terrain actually dips under the water level somewhere inside it.
##
## Probing a cell costs a few dozen height samples, so unknown cells are probed
## a couple per frame (the whole window at once during setup). The previous
## water stays on screen meanwhile.
func _update_water(focus: Vector3, unlimited: bool = false) -> void:
	if _water == null or not is_instance_valid(_water):
		return
	var cell := Vector2i(floori(focus.x / WATER_CELL), floori(focus.z / WATER_CELL))
	if cell != _water_cell:
		_water_cell = cell
		_water_pending = true
	if not _water_pending:
		return
	var budget: int = 1000000 if unlimited else WATER_PROBE_BUDGET
	for dz in range(-WATER_RADIUS, WATER_RADIUS + 1):
		for dx in range(-WATER_RADIUS, WATER_RADIUS + 1):
			var c := Vector2i(cell.x + dx, cell.y + dz)
			if _water_known.has(c):
				continue
			if budget <= 0:
				return          # the rest of the probing waits for next frame
			budget -= 1
			_water_known[c] = _probe_cell(c)
	_water_pending = false

	var spots: Array[Vector3] = []
	for dz in range(-WATER_RADIUS, WATER_RADIUS + 1):
		for dx in range(-WATER_RADIUS, WATER_RADIUS + 1):
			var c := Vector2i(cell.x + dx, cell.y + dz)
			if not bool(_water_known.get(c, false)):
				continue
			spots.append(Vector3(
					(float(c.x) + 0.5) * WATER_CELL,
					Heightfield.WATER_LEVEL,
					(float(c.y) + 0.5) * WATER_CELL))
	var mm := _water.multimesh
	mm.instance_count = spots.size()
	_water.visible = not spots.is_empty()
	if spots.is_empty():
		return
	var box := AABB()
	var half := WATER_CELL * 0.5
	for i in spots.size():
		mm.set_instance_transform(i, Transform3D(Basis(), spots[i]))
		var b := AABB(spots[i] - Vector3(half, 0.5, half), Vector3(WATER_CELL, 1.0, WATER_CELL))
		box = b if i == 0 else box.merge(b)
	_water.custom_aabb = box


## True when the terrain dips to the water level anywhere in the cell.
func _probe_cell(c: Vector2i) -> bool:
	var x0 := float(c.x) * WATER_CELL
	var z0 := float(c.y) * WATER_CELL
	var step := WATER_CELL / 6.0
	for j in 7:
		for i in 7:
			if _hf.height_at(x0 + float(i) * step, z0 + float(j) * step) < Heightfield.WATER_LEVEL + 0.15:
				return true
	return false


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

## Joins the worker threads and frees everything. MUST be called before the
## scene is reloaded or the process hangs on exit. Idempotent, and safe even
## when setup() was never called.
func shutdown() -> void:
	if _shutdown_done:
		return
	# Raise the flag first: the workers watch it and give up as soon as they can.
	if _mutex != null:
		_mutex.lock()
		_shutdown_done = true
		_results.clear()
		_mutex.unlock()
	else:
		_shutdown_done = true
	_queue.clear()
	_queued.clear()
	# Every task still in flight must be joined before anything is freed.
	for key in _inflight.keys():
		WorkerThreadPool.wait_for_task_completion(int(key))
	_inflight.clear()
	_inflight_tiles.clear()
	if _mutex != null:
		_mutex.lock()
		_results.clear()
		_mutex.unlock()

	for key in _chunks.keys():
		var chunk: TerrainChunk = _chunks[key]
		if chunk != null and is_instance_valid(chunk):
			chunk.queue_free()
	_chunks.clear()
	_wanted.clear()

	for key in _sites.keys():
		_free_site(int(key))
	_sites.clear()
	_site_queue.clear()
	_site_queued.clear()

	if _water != null and is_instance_valid(_water):
		_water.queue_free()
	_water = null
	_started = false


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

func _tile_of(x: float, z: float) -> Vector2i:
	return Vector2i(floori(x / TILE), floori(z / TILE))


func _tile_in_world(t: Vector2i) -> bool:
	return t.x >= MIN_TILE and t.x <= MAX_TILE and t.y >= MIN_TILE and t.y <= MAX_TILE


func _cheb(t: Vector2i) -> int:
	return maxi(absi(t.x - _center.x), absi(t.y - _center.y))


static func _lod_for(distance_in_tiles: int) -> int:
	if distance_in_tiles <= RING_LOD0:
		return 0
	if distance_in_tiles <= RING_LOD1:
		return 1
	if distance_in_tiles <= RING_LOD2:
		return 2
	return 3


## Bounds mirror Game.VIEW_DISTANCE_MIN / MAX from the contract.
func _view_distance() -> int:
	return clampi(int(Game.view_distance), 4, 14)


func _build_offsets(vd: int) -> void:
	_offsets.clear()
	for dz in range(-vd, vd + 1):
		for dx in range(-vd, vd + 1):
			_offsets.append(Vector2i(dx, dz))
	_offsets.sort_custom(Callable(self, "_offset_closer"))


func _offset_closer(a: Vector2i, b: Vector2i) -> bool:
	var da: int = maxi(absi(a.x), absi(a.y))
	var db: int = maxi(absi(b.x), absi(b.y))
	if da != db:
		return da < db
	return a.x * a.x + a.y * a.y < b.x * b.x + b.y * b.y
