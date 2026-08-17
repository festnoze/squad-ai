class_name Inventory
extends RefCounted
## Player inventory: one flat array of 36 slots.
##
## Slots 0..8 are the hotbar, slots 9..35 the storage grid shown by the
## inventory screen. Each slot holds a block id plus a count, kept in two
## parallel packed arrays so the HUD can read them without allocating.
##
## Invariant enforced by every mutation: an empty slot is exactly
## (Blocks.AIR, 0). A real block never carries a count of zero, and AIR never
## carries a non-zero count.
##
## In creative mode the inventory is bottomless: consume_selected() always
## succeeds without decrementing, add() places nothing and reports no
## leftover, and count_of() answers STACK_MAX so the interface can hide the
## counters.

## Emitted by every mutation except a selection change.
signal changed()

## Emitted only by select() and cycle().
signal selection_changed(slot: int)

const HOTBAR_SLOTS := 9
const STORAGE_SLOTS := 27

## Total slot count, hotbar plus storage.
const TOTAL_SLOTS := HOTBAR_SLOTS + STORAGE_SLOTS

const STACK_MAX := 999

## Schema tag written by to_dict(), checked loosely by from_dict().
const SAVE_VERSION := 1

var creative: bool = true

## Active hotbar slot, always inside 0..HOTBAR_SLOTS - 1.
var selected: int = 0

var _blocks: PackedByteArray
var _counts: PackedInt32Array


func _init() -> void:
	_blocks = PackedByteArray()
	_blocks.resize(TOTAL_SLOTS)
	_counts = PackedInt32Array()
	_counts.resize(TOTAL_SLOTS)
	_clear_all()
	# The hotbar starts on the first page of the creative palette.
	_write_palette_page(0)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

func selected_block() -> int:
	return _blocks[selected]


## Selects a hotbar slot. An index outside 0..8 is ignored.
func select(slot: int) -> void:
	if slot < 0 or slot >= HOTBAR_SLOTS:
		return
	selected = slot
	selection_changed.emit(selected)


## Moves the selection by `delta`, wrapping in both directions. Any magnitude
## is accepted, including deltas larger than HOTBAR_SLOTS.
func cycle(delta: int) -> void:
	selected = posmod(selected + delta, HOTBAR_SLOTS)
	selection_changed.emit(selected)


# ---------------------------------------------------------------------------
# Slot access
# ---------------------------------------------------------------------------

## Block held by a slot (0..8 hotbar, 9..35 storage). Out of range gives AIR.
func slot_block(slot: int) -> int:
	if slot < 0 or slot >= TOTAL_SLOTS:
		return Blocks.AIR
	return _blocks[slot]


## Stack size of a slot. Out of range gives 0.
func slot_count(slot: int) -> int:
	if slot < 0 or slot >= TOTAL_SLOTS:
		return 0
	return _counts[slot]


## Overwrites a slot. A count of zero or less, or an AIR id, empties the slot.
## Counts above STACK_MAX are clamped. An invalid index or block id is ignored.
func set_slot(slot: int, block_id: int, count: int) -> void:
	if slot < 0 or slot >= TOTAL_SLOTS:
		return
	if block_id < 0 or block_id >= Blocks.COUNT:
		push_warning("Inventory.set_slot: unknown block id %d" % block_id)
		return
	_write(slot, block_id, count)
	changed.emit()


## Exchanges the contents of two slots. Driven by mouse drag from the
## interface, so an out of range index is a plain no-op.
func swap_slots(a: int, b: int) -> void:
	if a < 0 or a >= TOTAL_SLOTS or b < 0 or b >= TOTAL_SLOTS:
		return
	if a == b:
		return
	var block_a: int = _blocks[a]
	var count_a: int = _counts[a]
	_blocks[a] = _blocks[b]
	_counts[a] = _counts[b]
	_blocks[b] = block_a
	_counts[b] = count_a
	changed.emit()


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------

## Stores `amount` blocks and returns the leftover that found no room.
## Existing partial stacks are topped up before a fresh slot is opened, and the
## hotbar is served before the storage. Always returns 0 in creative mode.
func add(block_id: int, amount: int = 1) -> int:
	if creative:
		return 0
	if amount <= 0:
		return 0
	if not _is_real_block(block_id):
		return amount

	var left := amount

	# Pass 1: top up matching stacks. Ascending order visits the hotbar first.
	for slot in TOTAL_SLOTS:
		if left <= 0:
			break
		if _blocks[slot] != block_id:
			continue
		var room: int = STACK_MAX - _counts[slot]
		if room <= 0:
			continue
		var moved: int = mini(room, left)
		_counts[slot] += moved
		left -= moved

	# Pass 2: open empty slots, hotbar first again.
	for slot in TOTAL_SLOTS:
		if left <= 0:
			break
		if _blocks[slot] != Blocks.AIR:
			continue
		var moved: int = mini(STACK_MAX, left)
		_blocks[slot] = block_id
		_counts[slot] = moved
		left -= moved

	if left != amount:
		changed.emit()
	return left


## Takes `amount` blocks out of the selected hotbar slot. Returns false when
## the stock is insufficient, leaving the slot untouched. Always true in
## creative mode, and never decrements there.
func consume_selected(amount: int = 1) -> bool:
	if creative:
		return true
	if amount <= 0:
		return true
	var block_id: int = _blocks[selected]
	if block_id == Blocks.AIR:
		return false
	if _counts[selected] < amount:
		return false
	_write(selected, block_id, _counts[selected] - amount)
	changed.emit()
	return true


## Total stock of a block across hotbar and storage. Reports STACK_MAX in
## creative mode so the interface knows the counter is meaningless.
func count_of(block_id: int) -> int:
	if not _is_real_block(block_id):
		return 0
	if creative:
		return STACK_MAX
	var total := 0
	for slot in TOTAL_SLOTS:
		if _blocks[slot] == block_id:
			total += _counts[slot]
	return total


## True when at least one more unit of the block fits somewhere.
func has_room_for(block_id: int) -> bool:
	if not _is_real_block(block_id):
		return false
	if creative:
		return true
	for slot in TOTAL_SLOTS:
		var id: int = _blocks[slot]
		if id == Blocks.AIR:
			return true
		if id == block_id and _counts[slot] < STACK_MAX:
			return true
	return false


## Empties every slot. The selection is left where it is.
func clear() -> void:
	_clear_all()
	changed.emit()


# ---------------------------------------------------------------------------
# Creative palette
# ---------------------------------------------------------------------------

## Loads page `page` of Blocks.PALETTE into the hotbar. The last page may be
## partial: hotbar slots without a matching palette entry are emptied. An out
## of range page is ignored.
func load_palette_page(page: int) -> void:
	if page < 0 or page >= palette_page_count():
		return
	_write_palette_page(page)
	changed.emit()


## Number of full and partial pages of nine in Blocks.PALETTE.
func palette_page_count() -> int:
	var size: int = Blocks.PALETTE.size()
	if size <= 0:
		return 0
	return (size + HOTBAR_SLOTS - 1) / HOTBAR_SLOTS


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

## Plain data snapshot, JSON friendly (only ints, bools and Arrays of ints).
func to_dict() -> Dictionary:
	var blocks: Array = []
	var counts: Array = []
	blocks.resize(TOTAL_SLOTS)
	counts.resize(TOTAL_SLOTS)
	for slot in TOTAL_SLOTS:
		blocks[slot] = int(_blocks[slot])
		counts[slot] = int(_counts[slot])
	return {
		"version": SAVE_VERSION,
		"selected": selected,
		"creative": creative,
		"blocks": blocks,
		"counts": counts,
	}


## Restores a snapshot produced by to_dict(). Malformed input is rejected
## whole: the inventory is only written once every entry has been validated,
## so a bad payload never leaves it half loaded.
func from_dict(data: Dictionary) -> void:
	if not data.has("blocks") or not data.has("counts"):
		push_warning("Inventory.from_dict: missing 'blocks' or 'counts'")
		return

	var blocks := _coerce_int_list(data["blocks"])
	var counts := _coerce_int_list(data["counts"])
	if blocks.size() != TOTAL_SLOTS or counts.size() != TOTAL_SLOTS:
		push_warning("Inventory.from_dict: expected %d slots" % TOTAL_SLOTS)
		return

	# Validate and normalise into scratch arrays before touching the real ones.
	var new_blocks := PackedByteArray()
	new_blocks.resize(TOTAL_SLOTS)
	var new_counts := PackedInt32Array()
	new_counts.resize(TOTAL_SLOTS)
	for slot in TOTAL_SLOTS:
		var id: int = blocks[slot]
		var count: int = counts[slot]
		if id < 0 or id >= Blocks.COUNT:
			push_warning("Inventory.from_dict: unknown block id %d in slot %d" % [id, slot])
			return
		if id == Blocks.AIR or count <= 0:
			new_blocks[slot] = Blocks.AIR
			new_counts[slot] = 0
		else:
			new_blocks[slot] = id
			new_counts[slot] = mini(count, STACK_MAX)

	var new_selected := selected
	if data.has("selected"):
		var raw_selected: Variant = data["selected"]
		var t := typeof(raw_selected)
		if t != TYPE_INT and t != TYPE_FLOAT:
			push_warning("Inventory.from_dict: 'selected' is not a number")
			return
		new_selected = clampi(int(raw_selected), 0, HOTBAR_SLOTS - 1)

	var new_creative := creative
	if data.has("creative"):
		var raw_creative: Variant = data["creative"]
		if typeof(raw_creative) != TYPE_BOOL:
			push_warning("Inventory.from_dict: 'creative' is not a bool")
			return
		new_creative = bool(raw_creative)

	_blocks = new_blocks
	_counts = new_counts
	selected = new_selected
	creative = new_creative
	changed.emit()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _is_real_block(block_id: int) -> bool:
	return block_id > Blocks.AIR and block_id < Blocks.COUNT


## Single write path, so the (id, count) agreement can never drift.
func _write(slot: int, block_id: int, count: int) -> void:
	if block_id == Blocks.AIR or count <= 0:
		_blocks[slot] = Blocks.AIR
		_counts[slot] = 0
		return
	_blocks[slot] = block_id
	_counts[slot] = mini(count, STACK_MAX)


func _clear_all() -> void:
	_blocks.fill(Blocks.AIR)
	_counts.fill(0)


## Fills the hotbar from the palette without emitting, used by _init too.
func _write_palette_page(page: int) -> void:
	var palette := Blocks.PALETTE
	var base := page * HOTBAR_SLOTS
	for i in HOTBAR_SLOTS:
		var index := base + i
		if index >= palette.size():
			_write(i, Blocks.AIR, 0)
			continue
		var id: int = palette[index]
		if not _is_real_block(id):
			_write(i, Blocks.AIR, 0)
			continue
		# A palette stack is a full stack: creative hides the counter, and
		# survival still gets a coherent non-zero count.
		_write(i, id, STACK_MAX)


## Reads an array of integers out of untrusted data. Accepts Array,
## PackedByteArray, PackedInt32Array, PackedInt64Array and the float packed
## arrays, plus the floats JSON produces for whole numbers. Returns an empty
## array when the value is not a usable list of numbers.
func _coerce_int_list(value: Variant) -> PackedInt32Array:
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
				out.append(item)
		TYPE_PACKED_FLOAT32_ARRAY:
			var floats32: PackedFloat32Array = value
			for item in floats32:
				if is_nan(item) or is_inf(item):
					return PackedInt32Array()
				out.append(int(roundf(item)))
		TYPE_PACKED_FLOAT64_ARRAY:
			var floats64: PackedFloat64Array = value
			for item in floats64:
				if is_nan(item) or is_inf(item):
					return PackedInt32Array()
				out.append(int(roundf(item)))
		_:
			return PackedInt32Array()
	return out
