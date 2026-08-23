class_name GravityManager
extends Node3D
## Gravity for sand and gravel.
##
## Listens to VoxelWorld.block_changed. A gravity block whose cell below has
## nothing colliding is removed from the grid, animated as a small falling
## cube, then written back at its rest cell. Chain reactions need no special
## code: every removal and every landing goes through set_block, which
## re-emits block_changed and re-triggers the support checks.
##
## Bookkeeping invariants:
##   - _tracked holds every START cell that is scheduled or airborne, so a
##     cell is never queued twice.
##   - _claimed holds every REST cell a faller is heading to, so two fallers
##     never target the same landing spot. If the claim turns out stale on
##     landing (a player built there mid-fall), the landing re-scans.

## Blocks affected by gravity. Kept local on purpose: Blocks stays untouched.
const GRAVITY_BLOCK_IDS: PackedByteArray = [Blocks.SAND, Blocks.GRAVEL]

## At most this many animated fallers at once. Beyond the cap a fall is
## applied instantly with set_block, with no visual.
const MAX_ACTIVE_VISUALS := 48

## Scheduled falls processed per physics frame, to bound per-frame work.
const FALLS_PER_FRAME := 16

var _world: VoxelWorld
var _pending: Array[Vector3i] = []
var _tracked: Dictionary = {}   ## start cell -> true while scheduled or airborne
var _claimed: Dictionary = {}   ## rest cell -> true while a faller targets it
var _active_visuals: int = 0
var _sfx: Node = null


func setup(world: VoxelWorld) -> void:
	_world = world
	world.block_changed.connect(_on_block_changed)


# ---------------------------------------------------------------------------
# Pure helpers (unit tested)
# ---------------------------------------------------------------------------

static func is_gravity_block(id: int) -> bool:
	return GRAVITY_BLOCK_IDS.has(id)


## Rest cell of a straight vertical drop from `start`: the lowest
## non-colliding cell above the first colliding block below. Liquids and
## cross plants do not collide, so the block falls through them (they get
## overwritten at the rest cell). With no collider anywhere the scan stops at
## y 0; in a generated column bedrock always collides so that never happens.
## `block_getter` is called as (wx, wy, wz) -> int, which keeps this scan
## pure and testable without a world.
static func scan_rest_cell(start: Vector3i, block_getter: Callable) -> Vector3i:
	var y := start.y - 1
	while y >= 0:
		var id: int = block_getter.call(start.x, y, start.z)
		if Blocks.collides(id):
			return Vector3i(start.x, y + 1, start.z)
		y -= 1
	return Vector3i(start.x, 0, start.z)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

func _on_block_changed(cell: Vector3i, _old_id: int, new_id: int) -> void:
	if _world == null:
		return
	# A gravity block appeared without support: it falls.
	if is_gravity_block(new_id) and not _supported(cell):
		_schedule(cell)
	# The change may have removed the support of the cell directly above.
	if not Blocks.collides(new_id):
		var above := cell + Vector3i.UP
		if is_gravity_block(_world.get_block(above.x, above.y, above.z)):
			_schedule(above)


func _schedule(cell: Vector3i) -> void:
	if _tracked.has(cell):
		return
	_tracked[cell] = true
	_pending.append(cell)


func _supported(cell: Vector3i) -> bool:
	if cell.y <= 0:
		return true
	return Blocks.collides(_world.get_block(cell.x, cell.y - 1, cell.z))


# ---------------------------------------------------------------------------
# Fall execution
# ---------------------------------------------------------------------------

func _physics_process(_delta: float) -> void:
	if _world == null or _pending.is_empty():
		return
	# The budget is fixed before the loop: falls triggered by the chain
	# reactions below land in _pending and wait for the next frame.
	var budget := mini(FALLS_PER_FRAME, _pending.size())
	for i in budget:
		var start: Vector3i = _pending.pop_front()
		_execute_fall(start)


func _execute_fall(start: Vector3i) -> void:
	var id := _world.get_block(start.x, start.y, start.z)
	if not is_gravity_block(id) or _supported(start):
		_tracked.erase(start)
		return
	var rest := scan_rest_cell(start, _world.get_block)
	# Never let two fallers target the same rest cell: stack upward over
	# active claims. Reaching the start cell again means there is nowhere to
	# go right now; the landing below will re-emit block_changed and this
	# cell gets re-checked then.
	while _claimed.has(rest) and rest.y < start.y:
		rest.y += 1
	if rest.y >= start.y:
		_tracked.erase(start)
		return
	_claimed[rest] = true
	_world.set_block(start.x, start.y, start.z, Blocks.AIR)
	# The block has left the grid: release the start cell now, so a gravity
	# block placed there mid-flight schedules its own fall instead of being
	# swallowed by the tracking guard and floating forever.
	_tracked.erase(start)
	if _active_visuals >= MAX_ACTIVE_VISUALS:
		_land(start, rest, id)
		return
	_active_visuals += 1
	var faller := FallingBlock.new()
	faller.name = "FallingBlock"
	faller.manager = self
	faller.block_id = id
	faller.start_cell = start
	faller.rest_cell = rest
	add_child(faller)
	faller.build_visual()
	faller.position = Vector3(start) + Vector3(0.5, 0.5, 0.5)


## Writes the block back into the grid. `rest` is the claim taken at launch;
## if something non-replaceable landed there in the meantime, look for a
## lower opening first, then stack on top of the obstacle.
func _land(start: Vector3i, rest: Vector3i, id: int) -> void:
	# The start cell was already released at launch; erasing it again here
	# could swallow the guard of a fall scheduled for that cell mid-flight.
	_claimed.erase(rest)
	if _world == null:
		return
	var final := rest
	if not Blocks.is_replaceable(_world.get_block(final.x, final.y, final.z)):
		var lower := scan_rest_cell(rest, _world.get_block)
		if lower != rest and Blocks.is_replaceable(_world.get_block(lower.x, lower.y, lower.z)):
			final = lower
		else:
			final = rest
			while final.y < VoxelWorld.WORLD_HEIGHT and not Blocks.is_replaceable(_world.get_block(final.x, final.y, final.z)):
				final.y += 1
			if final.y >= VoxelWorld.WORLD_HEIGHT:
				push_warning("GravityManager: no rest cell left in column (%d, %d), block lost" % [rest.x, rest.z])
				return
	if not _world.set_block(final.x, final.y, final.z, id):
		push_warning("GravityManager: rest chunk unloaded at (%d, %d, %d), block lost" % [final.x, final.y, final.z])
		return
	_play_place_sound(Vector3(final) + Vector3(0.5, 0.5, 0.5))


## Immediately writes every airborne block into the grid at its claimed rest
## cell. Called by main before a world switch or quit: the airborne cells were
## already set to AIR at launch, so freeing the fallers mid-flight would erase
## those blocks from the save for good.
func settle_all() -> void:
	for child in get_children():
		var faller := child as FallingBlock
		if faller == null or faller.is_queued_for_deletion():
			continue
		faller.set_physics_process(false)
		_land(faller.start_cell, faller.rest_cell, faller.block_id)
		faller.queue_free()
	# Pending falls never left the grid, so they need no write-back.
	_pending.clear()
	_tracked.clear()
	_claimed.clear()
	_active_visuals = 0


func _on_visual_landed(faller: FallingBlock) -> void:
	_active_visuals = maxi(_active_visuals - 1, 0)
	_land(faller.start_cell, faller.rest_cell, faller.block_id)
	faller.queue_free()


func _play_place_sound(at: Vector3) -> void:
	if _sfx == null or not is_instance_valid(_sfx):
		_sfx = get_node_or_null(^"/root/Sfx")
	if _sfx != null and _sfx.has_method("play_at"):
		_sfx.call("play_at", "place", at, -6.0, 0.8)


# ---------------------------------------------------------------------------
# Falling visual
# ---------------------------------------------------------------------------

## One airborne block. Purely cosmetic: the voxel grid already treats the
## cell as air, and the manager writes the block back on landing.
class FallingBlock:
	extends MeshInstance3D

	const FALL_GRAVITY := 20.0
	const FALL_MAX_SPEED := 30.0

	var manager: GravityManager
	var block_id: int = 0
	var start_cell: Vector3i = Vector3i.ZERO
	var rest_cell: Vector3i = Vector3i.ZERO

	var _speed: float = 0.0
	var _landed: bool = false

	func build_visual() -> void:
		var box := BoxMesh.new()
		box.size = Vector3.ONE
		var material := StandardMaterial3D.new()
		var tile: String = Blocks.TILE_NAMES[Blocks.tile_of(block_id, Blocks.FACE_PX)]
		material.albedo_texture = ImageTexture.create_from_image(VoxelAtlas.tile_image(tile))
		material.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
		material.roughness = 1.0
		box.material = material
		mesh = box

	func _physics_process(delta: float) -> void:
		if _landed:
			return
		_speed = minf(_speed + FALL_GRAVITY * delta, FALL_MAX_SPEED)
		position.y -= _speed * delta
		var target_y := float(rest_cell.y) + 0.5
		if position.y <= target_y:
			position.y = target_y
			_landed = true
			if manager != null and is_instance_valid(manager):
				manager._on_visual_landed(self)
			else:
				queue_free()
