class_name GrowthManager
extends Node3D
## Grows planted saplings into small oak trees.
##
## setup() subscribes to VoxelWorld.block_changed: every cell that turns into
## Blocks.SAPLING is registered with a random growth delay, and any registered
## cell that changes to something else is dropped. A one second tick scans the
## registry; a due sapling grows only when it still stands and the four cells
## straight above it are replaceable, otherwise the attempt is postponed a few
## times before being forgotten.
##
## Known limitations, accepted by design:
##   - Pending saplings are not persisted across sessions: quitting the game
##     forgets every running timer.
##   - Saplings decorated by terrain generation (taiga, forest) are never
##     registered on their own. Only a block change touching the cell, for
##     example breaking and replanting the sapling, starts a growth timer.

## Registry hard cap. Beyond it the oldest pending sapling is dropped.
const MAX_TRACKED := 256

## Growth delay bounds in seconds.
const DELAY_MIN := 20.0
const DELAY_MAX := 40.0

## Scan period in seconds.
const TICK_INTERVAL := 1.0

## Delay added when a due sapling cannot grow yet.
const POSTPONE_DELAY := 10.0

## A sapling postponed more often than this is forgotten.
const MAX_POSTPONEMENTS := 3

## Cells straight above the sapling that must be replaceable before growing.
const CLEARANCE := 4

var _world: VoxelWorld = null

## Instance owned generator: growth delays, trunk heights and corner trims.
var _rng := RandomNumberGenerator.new()

## cell (Vector3i) -> {"due": float, "tries": int}. Godot dictionaries keep
## insertion order, which doubles as the age order used by the cap.
var _pending: Dictionary = {}

## Internal clock in seconds, advanced by _physics_process.
var _clock := 0.0
var _tick_accum := 0.0

## Cached Sfx autoload, resolved lazily so headless tests run without audio.
var _sfx: Node = null


func _init() -> void:
	_rng.randomize()


func setup(world: VoxelWorld) -> void:
	_world = world
	world.block_changed.connect(_on_block_changed)


func _physics_process(delta: float) -> void:
	if _world == null:
		return
	_clock += delta
	_tick_accum += delta
	if _tick_accum < TICK_INTERVAL:
		return
	_tick_accum = 0.0
	_tick()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

func _on_block_changed(cell: Vector3i, _old_id: int, new_id: int) -> void:
	if new_id == Blocks.SAPLING:
		_register(cell)
	elif _pending.has(cell):
		_pending.erase(cell)


func _register(cell: Vector3i) -> void:
	# Re-planting restarts the timer and moves the cell to the newest slot.
	if _pending.has(cell):
		_pending.erase(cell)
	while _pending.size() >= MAX_TRACKED:
		_pending.erase(_pending.keys()[0])
	_pending[cell] = {
		"due": _clock + _rng.randf_range(DELAY_MIN, DELAY_MAX),
		"tries": 0,
	}


# ---------------------------------------------------------------------------
# Tick
# ---------------------------------------------------------------------------

func _tick() -> void:
	if _pending.is_empty():
		return
	# Due cells are collected first: growing mutates the registry through the
	# block_changed signal, which must never happen mid iteration.
	var due: Array[Vector3i] = []
	for cell: Vector3i in _pending:
		var entry: Dictionary = _pending[cell]
		if float(entry["due"]) <= _clock:
			due.append(cell)
	for cell in due:
		_process_due(cell)


func _process_due(cell: Vector3i) -> void:
	var entry: Dictionary = _pending.get(cell, {})
	if entry.is_empty():
		return
	if not _can_grow(cell):
		var tries := int(entry["tries"]) + 1
		if tries > MAX_POSTPONEMENTS:
			_pending.erase(cell)
			return
		entry["tries"] = tries
		entry["due"] = _clock + POSTPONE_DELAY
		return
	# Erase first: the trunk write below re-emits block_changed for this cell.
	_pending.erase(cell)
	_grow_tree(cell)


## True when the cell still holds a sapling and the CLEARANCE cells straight
## above it are all inside the world and replaceable.
func _can_grow(cell: Vector3i) -> bool:
	if _world.get_block(cell.x, cell.y, cell.z) != Blocks.SAPLING:
		return false
	for dy in range(1, CLEARANCE + 1):
		var wy := cell.y + dy
		if wy >= VoxelWorld.WORLD_HEIGHT:
			return false
		if not Blocks.is_replaceable(_world.get_block(cell.x, wy, cell.z)):
			return false
	return true


# ---------------------------------------------------------------------------
# Tree shape
# ---------------------------------------------------------------------------

## Trunk height of a grown oak, 4 or 5 cells including the base.
static func trunk_height_from(rng: RandomNumberGenerator) -> int:
	return 4 + int(rng.randi() % 2)


## Leaf offsets of an oak canopy, relative to the trunk base cell, for a trunk
## occupying local y 0 .. trunk_height - 1. Mirrors the look of the natural
## oaks emitted by TerrainGen. Pure function of the RNG stream, so a seeded
## generator makes the result fully deterministic and testable headless.
## The trunk column is never included: those cells hold logs.
static func canopy_offsets(trunk_height: int, rng: RandomNumberGenerator) -> Array[Vector3i]:
	var out: Array[Vector3i] = []
	var top := trunk_height - 1
	# Two full 3x3 layers under the trunk top. The upper of the two loses each
	# of its four corners half of the time, like naturally generated oaks.
	for layer_y: int in [top - 2, top - 1]:
		for dx in range(-1, 2):
			for dz in range(-1, 2):
				if dx == 0 and dz == 0:
					continue
				var corner := absi(dx) == 1 and absi(dz) == 1
				if corner and layer_y == top - 1 and rng.randf() < 0.5:
					continue
				out.append(Vector3i(dx, layer_y, dz))
	# A 3x3 cross (no corners) at the trunk top.
	for side: Vector2i in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
		out.append(Vector3i(side.x, top, side.y))
	# A single leaf capping the tree.
	out.append(Vector3i(0, trunk_height, 0))
	return out


# ---------------------------------------------------------------------------
# Growth
# ---------------------------------------------------------------------------

func _grow_tree(cell: Vector3i) -> void:
	var trunk_height := trunk_height_from(_rng)
	# The trunk base is the one write allowed to replace a non air cell: it
	# consumes the sapling itself, confirmed by _can_grow just before.
	_world.set_block(cell.x, cell.y, cell.z, Blocks.OAK_LOG)
	for dy in range(1, trunk_height):
		_set_if_replaceable(Vector3i(cell.x, cell.y + dy, cell.z), Blocks.OAK_LOG)
	for offset in canopy_offsets(trunk_height, _rng):
		_set_if_replaceable(cell + offset, Blocks.OAK_LEAVES)
	_play_growth_sound(cell)


## Writes through world.set_block so the surrounding meshes refresh, but only
## into replaceable cells: solid blocks, logs and existing structures are never
## overwritten. Failed writes are simply skipped.
func _set_if_replaceable(cell: Vector3i, id: int) -> void:
	if cell.y < 0 or cell.y >= VoxelWorld.WORLD_HEIGHT:
		return
	if not Blocks.is_replaceable(_world.get_block(cell.x, cell.y, cell.z)):
		return
	_world.set_block(cell.x, cell.y, cell.z, id)


func _play_growth_sound(base: Vector3i) -> void:
	if _sfx == null or not is_instance_valid(_sfx):
		_sfx = get_node_or_null(^"/root/Sfx")
	if _sfx == null or not _sfx.has_method("play_at"):
		return
	var sound := "place"
	var library: Variant = _sfx.get("_library")
	if library is Dictionary and (library as Dictionary).has("break_plant"):
		sound = "break_plant"
	var centre := Vector3(base) + Vector3(0.5, 0.5, 0.5)
	_sfx.call("play_at", sound, centre, -4.0, 1.1)
