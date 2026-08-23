class_name ChestStore
extends RefCounted
## Per-world contents of every placed storage chest.
##
## Chunk voxels only remember that a cell holds a CHEST block; the stacks
## inside live here, keyed by the world cell. The store is pure data (no scene
## nodes), owned by main, persisted through the world meta.json.
##
## Invariant shared with Inventory: an empty slot is exactly (Blocks.AIR, 0),
## a real id never carries a count of zero, and counts never exceed
## Inventory.STACK_MAX.

## Emitted after every mutation of one chest, with the cell that changed.
signal changed(cell: Vector3i)

## Slots per chest, one 9x3 grid like the inventory storage.
const SLOTS := 27

## "x:y:z" -> {"blocks": PackedInt32Array, "counts": PackedInt32Array}.
var _chests: Dictionary = {}


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

static func _key_of(cell: Vector3i) -> String:
	return "%d:%d:%d" % [cell.x, cell.y, cell.z]


## Parses an "x:y:z" key back into a cell. Returns false into `out` on garbage.
static func _parse_key(key: String, out: Array) -> bool:
	var parts := key.split(":")
	if parts.size() != 3:
		return false
	for part in parts:
		if not part.is_valid_int():
			return false
	out.clear()
	out.append(Vector3i(int(parts[0]), int(parts[1]), int(parts[2])))
	return true


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

func has_chest(cell: Vector3i) -> bool:
	return _chests.has(_key_of(cell))


## Creates an empty chest at the cell when none exists yet.
func ensure(cell: Vector3i) -> void:
	var key := _key_of(cell)
	if _chests.has(key):
		return
	_chests[key] = _empty_chest()
	changed.emit(cell)


# ---------------------------------------------------------------------------
# Slot access
# ---------------------------------------------------------------------------

## Block or item id of one slot. AIR when the chest or the slot does not exist.
func slot_block(cell: Vector3i, i: int) -> int:
	if i < 0 or i >= SLOTS:
		return Blocks.AIR
	var key := _key_of(cell)
	if not _chests.has(key):
		return Blocks.AIR
	var chest: Dictionary = _chests[key]
	return (chest["blocks"] as PackedInt32Array)[i]


## Stack size of one slot. 0 when the chest or the slot does not exist.
func slot_count(cell: Vector3i, i: int) -> int:
	if i < 0 or i >= SLOTS:
		return 0
	var key := _key_of(cell)
	if not _chests.has(key):
		return 0
	var chest: Dictionary = _chests[key]
	return (chest["counts"] as PackedInt32Array)[i]


## Overwrites one slot with the same normalisation rules as Inventory: AIR or a
## count of zero or less empties the slot, counts are clamped to STACK_MAX and
## an unknown id is rejected. Creates the chest when absent.
func set_slot(cell: Vector3i, i: int, id: int, count: int) -> void:
	if i < 0 or i >= SLOTS:
		return
	if id != Blocks.AIR and not Items.is_valid_id(id):
		push_warning("ChestStore.set_slot: unknown id %d" % id)
		return
	var chest := _chest_at(cell)
	var blocks: PackedInt32Array = chest["blocks"]
	var counts: PackedInt32Array = chest["counts"]
	if id == Blocks.AIR or count <= 0:
		blocks[i] = Blocks.AIR
		counts[i] = 0
	else:
		blocks[i] = id
		counts[i] = mini(count, Inventory.STACK_MAX)
	chest["blocks"] = blocks
	chest["counts"] = counts
	changed.emit(cell)


# ---------------------------------------------------------------------------
# Stock movement
# ---------------------------------------------------------------------------

## Stores a stack into the chest, topping up matching stacks before opening
## empty slots. Returns the leftover that found no room. Creates the chest.
func store_stack(cell: Vector3i, id: int, count: int) -> int:
	if count <= 0:
		return 0
	if id == Blocks.AIR or not Items.is_valid_id(id):
		return count
	var chest := _chest_at(cell)
	var blocks: PackedInt32Array = chest["blocks"]
	var counts: PackedInt32Array = chest["counts"]
	var left := count

	# Pass 1: top up matching stacks.
	for i in SLOTS:
		if left <= 0:
			break
		if blocks[i] != id:
			continue
		var room: int = Inventory.STACK_MAX - counts[i]
		if room <= 0:
			continue
		var moved: int = mini(room, left)
		counts[i] += moved
		left -= moved

	# Pass 2: open empty slots.
	for i in SLOTS:
		if left <= 0:
			break
		if blocks[i] != Blocks.AIR:
			continue
		var moved: int = mini(Inventory.STACK_MAX, left)
		blocks[i] = id
		counts[i] = moved
		left -= moved

	chest["blocks"] = blocks
	chest["counts"] = counts
	if left != count:
		changed.emit(cell)
	return left


## Erases the chest and returns what it held as an Array of [id, count] pairs.
## An absent chest yields an empty Array.
func remove_chest(cell: Vector3i) -> Array:
	var out: Array = []
	var key := _key_of(cell)
	if not _chests.has(key):
		return out
	var chest: Dictionary = _chests[key]
	var blocks: PackedInt32Array = chest["blocks"]
	var counts: PackedInt32Array = chest["counts"]
	for i in SLOTS:
		if blocks[i] != Blocks.AIR and counts[i] > 0:
			out.append([blocks[i], counts[i]])
	_chests.erase(key)
	changed.emit(cell)
	return out


## Pours the whole chest into an inventory through inv.add and erases it
## regardless of the outcome. Returns the total units that did NOT fit.
func dump_into(cell: Vector3i, inv: Inventory) -> int:
	var pairs := remove_chest(cell)
	var leftover := 0
	for pair: Array in pairs:
		var id := int(pair[0])
		var count := int(pair[1])
		# A creative inventory absorbs nothing (add() is a no-op there), so the
		# whole stack is reported as lost instead of pretending it fit.
		if inv == null or inv.creative:
			leftover += count
			continue
		leftover += inv.add(id, count)
	return leftover


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

## JSON safe snapshot: string cell keys, each chest a Dictionary of two plain
## Arrays of ints.
func to_dict() -> Dictionary:
	var out: Dictionary = {}
	for key: String in _chests:
		var chest: Dictionary = _chests[key]
		var src_blocks: PackedInt32Array = chest["blocks"]
		var src_counts: PackedInt32Array = chest["counts"]
		var blocks: Array = []
		var counts: Array = []
		blocks.resize(SLOTS)
		counts.resize(SLOTS)
		for i in SLOTS:
			blocks[i] = int(src_blocks[i])
			counts[i] = int(src_counts[i])
		out[key] = {"blocks": blocks, "counts": counts}
	return out


## Restores a snapshot produced by to_dict(). Each malformed chest is skipped
## individually with a warning, so one corrupt entry never wipes the rest.
func from_dict(data: Dictionary) -> void:
	_chests = {}
	for raw_key: Variant in data:
		if typeof(raw_key) != TYPE_STRING:
			push_warning("ChestStore.from_dict: non string key skipped")
			continue
		var key: String = raw_key
		var parsed: Array = []
		if not _parse_key(key, parsed):
			push_warning("ChestStore.from_dict: bad cell key '%s' skipped" % key)
			continue

		var raw_chest: Variant = data[key]
		if typeof(raw_chest) != TYPE_DICTIONARY:
			push_warning("ChestStore.from_dict: chest '%s' is not a Dictionary" % key)
			continue
		var chest_data: Dictionary = raw_chest
		var blocks := _coerce_int_list(chest_data.get("blocks"))
		var counts := _coerce_int_list(chest_data.get("counts"))
		if blocks.size() != SLOTS or counts.size() != SLOTS:
			push_warning("ChestStore.from_dict: chest '%s' expected %d slots" % [key, SLOTS])
			continue

		# Validate and normalise into a scratch chest before keeping it.
		var new_blocks := PackedInt32Array()
		new_blocks.resize(SLOTS)
		var new_counts := PackedInt32Array()
		new_counts.resize(SLOTS)
		var valid := true
		for i in SLOTS:
			var id: int = blocks[i]
			var count: int = counts[i]
			if id != Blocks.AIR and not Items.is_valid_id(id):
				push_warning("ChestStore.from_dict: chest '%s' has unknown id %d" % [key, id])
				valid = false
				break
			if id == Blocks.AIR or count <= 0:
				new_blocks[i] = Blocks.AIR
				new_counts[i] = 0
			else:
				new_blocks[i] = id
				new_counts[i] = mini(count, Inventory.STACK_MAX)
		if not valid:
			continue

		_chests[key] = {"blocks": new_blocks, "counts": new_counts}
		changed.emit(parsed[0] as Vector3i)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

static func _empty_chest() -> Dictionary:
	var blocks := PackedInt32Array()
	blocks.resize(SLOTS)
	var counts := PackedInt32Array()
	counts.resize(SLOTS)
	return {"blocks": blocks, "counts": counts}


## Chest of a cell, created silently when absent. Internal write path only:
## callers emit `changed` themselves, exactly once per public mutation.
func _chest_at(cell: Vector3i) -> Dictionary:
	var key := _key_of(cell)
	if not _chests.has(key):
		_chests[key] = _empty_chest()
	return _chests[key]


## Reads an array of integers out of untrusted data. Accepts the Arrays JSON
## produces (ints stored as floats included) and the packed integer arrays a
## live snapshot may carry. Empty on anything else.
static func _coerce_int_list(value: Variant) -> PackedInt32Array:
	var out := PackedInt32Array()
	match typeof(value):
		TYPE_ARRAY:
			var source: Array = value
			for item in source:
				var t := typeof(item)
				if t == TYPE_INT:
					out.append(int(item))
				elif t == TYPE_FLOAT:
					var f: float = item
					if is_nan(f) or is_inf(f):
						return PackedInt32Array()
					out.append(int(roundf(f)))
				else:
					return PackedInt32Array()
		TYPE_PACKED_BYTE_ARRAY:
			var bytes: PackedByteArray = value
			for item in bytes:
				out.append(item)
		TYPE_PACKED_INT32_ARRAY:
			var ints32: PackedInt32Array = value
			for item in ints32:
				out.append(item)
		TYPE_PACKED_INT64_ARRAY:
			var ints64: PackedInt64Array = value
			for item in ints64:
				out.append(int(item))
		_:
			return PackedInt32Array()
	return out
