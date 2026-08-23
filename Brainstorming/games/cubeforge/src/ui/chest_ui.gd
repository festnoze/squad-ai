class_name ChestUi
extends Control
## Storage chest screen: the chest grid above the player inventory.
##
## Opened by right-clicking a placed chest. Every widget is built in code,
## following the shared voxel interface style. The interaction model is click
## to transfer, no drag: clicking a non-empty chest slot moves that whole
## stack into the inventory, clicking a non-empty inventory slot moves that
## stack into the chest. Whatever finds no room stays where it was.

signal closed()

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.42)

const SLOT_SIZE := 54
const GRID_COLUMNS := 9
const GRID_GAP := 4

var _inventory: Inventory = null
var _store: ChestStore = null
var _cell: Vector3i = Vector3i.ZERO
var _open: bool = false
var _built: bool = false

## SLOTS entries, one ChestSlot per chest cell.
var _chest_slots: Array = []
## 36 entries (0..8 hotbar, 9..35 storage), one ChestSlot per inventory slot.
var _inv_slots: Array = []
var _hint_label: Label = null
var _preview_cache: Dictionary = {}
var _sfx: Node = null


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

func _ready() -> void:
	_ensure_built()


## Binds the two models. Safe before or after entering the tree, the widget
## tree is built lazily.
func setup(inventory: Inventory, store: ChestStore) -> void:
	_ensure_built()
	if _inventory != inventory:
		if _inventory != null and _inventory.changed.is_connected(_on_inventory_changed):
			_inventory.changed.disconnect(_on_inventory_changed)
		_inventory = inventory
		if _inventory != null:
			_inventory.changed.connect(_on_inventory_changed)
	if _store != store:
		if _store != null and _store.changed.is_connected(_on_store_changed):
			_store.changed.disconnect(_on_store_changed)
		_store = store
		if _store != null:
			_store.changed.connect(_on_store_changed)
	_refresh()


## Opens the screen bound to one placed chest, creating its record on first
## visit so the grid never shows a phantom.
func open(cell: Vector3i) -> void:
	_ensure_built()
	_cell = cell
	if _store != null:
		_store.ensure(cell)
	if _open:
		_refresh()
		return
	_open = true
	visible = true
	_refresh()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close() -> void:
	if not _open:
		return
	_open = false
	visible = false
	# Another overlay (the pause menu) may still need the pointer.
	if not _other_screen_open():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	closed.emit()


## Cell of the chest currently displayed, so main can close the screen when
## that block gets destroyed under it.
func open_cell() -> Vector3i:
	return _cell


func is_open() -> bool:
	return _open


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

func _input(event: InputEvent) -> void:
	if not _open:
		return
	var wants_close := false
	if InputMap.has_action("pause") and event.is_action_pressed("pause"):
		wants_close = true
	elif InputMap.has_action("inventory") and event.is_action_pressed("inventory"):
		wants_close = true
	if wants_close:
		close()
		get_viewport().set_input_as_handled()


# ---------------------------------------------------------------------------
# Transfers, called back by the slot widgets
# ---------------------------------------------------------------------------

## Chest slot clicked: move the whole stack into the inventory. The leftover
## that found no room stays in the chest slot.
func take_from_chest(slot: int) -> void:
	if _inventory == null or _store == null or not _open:
		return
	# Creative add() stores nothing and reports no leftover, which would
	# silently destroy the stack: in creative the chest is read-only outward.
	if _inventory.creative:
		return
	var id := _store.slot_block(_cell, slot)
	var count := _store.slot_count(_cell, slot)
	if id == Blocks.AIR or count <= 0:
		return
	var leftover := _inventory.add(id, count)
	if leftover >= count:
		return
	_store.set_slot(_cell, slot, id, leftover)
	_play_sound("click")


## Inventory slot clicked: move the whole stack into the chest. The leftover
## that found no room stays in the inventory slot.
func put_into_chest(slot: int) -> void:
	if _inventory == null or _store == null or not _open:
		return
	var id := _inventory.slot_block(slot)
	var count := _inventory.slot_count(slot)
	if id == Blocks.AIR or count <= 0:
		return
	var leftover := _store.store_stack(_cell, id, count)
	if leftover >= count:
		return
	_inventory.set_slot(slot, id, leftover)
	_play_sound("click")


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

func _ensure_built() -> void:
	if _built:
		return
	_built = true

	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	visible = false

	_chest_slots.resize(ChestStore.SLOTS)
	_inv_slots.resize(Inventory.HOTBAR_SLOTS + Inventory.STORAGE_SLOTS)

	var dim := ColorRect.new()
	dim.color = DIM_COLOR
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)

	var center := CenterContainer.new()
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center)

	var frame := PanelContainer.new()
	frame.add_theme_stylebox_override("panel", _make_box(PANEL_BG, PANEL_BORDER, 2))
	center.add_child(frame)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 20)
	margin.add_theme_constant_override("margin_right", 20)
	margin.add_theme_constant_override("margin_top", 16)
	margin.add_theme_constant_override("margin_bottom", 18)
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.add_child(column)

	column.add_child(_make_title("Coffre", 24))

	var chest_grid := _make_grid()
	column.add_child(chest_grid)
	for i in ChestStore.SLOTS:
		var slot := ChestSlot.new()
		slot.configure(self, SLOT_SIZE, true, i)
		chest_grid.add_child(slot)
		_chest_slots[i] = slot

	column.add_child(_make_rule())
	column.add_child(_make_title("Inventaire", 16))

	var storage_grid := _make_grid()
	column.add_child(storage_grid)
	for i in Inventory.STORAGE_SLOTS:
		var index: int = Inventory.HOTBAR_SLOTS + i
		var slot := ChestSlot.new()
		slot.configure(self, SLOT_SIZE, false, index)
		storage_grid.add_child(slot)
		_inv_slots[index] = slot

	var hotbar_grid := _make_grid()
	column.add_child(hotbar_grid)
	for i in Inventory.HOTBAR_SLOTS:
		var slot := ChestSlot.new()
		slot.configure(self, SLOT_SIZE, false, i)
		hotbar_grid.add_child(slot)
		_inv_slots[i] = slot

	_hint_label = Label.new()
	_hint_label.text = "Cliquez une pile pour la transférer d'un côté à l'autre."
	_hint_label.add_theme_color_override("font_color", Color(0.72, 0.76, 0.82))
	_hint_label.add_theme_font_size_override("font_size", 13)
	_hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_hint_label)


func _make_grid() -> GridContainer:
	var grid := GridContainer.new()
	grid.columns = GRID_COLUMNS
	grid.add_theme_constant_override("h_separation", GRID_GAP)
	grid.add_theme_constant_override("v_separation", GRID_GAP)
	grid.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return grid


func _make_title(text: String, font_size: int) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", TEXT_COLOR)
	label.add_theme_font_size_override("font_size", font_size)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label


func _make_rule() -> Control:
	var rule := ColorRect.new()
	rule.color = Color(0.85, 0.88, 0.92, 0.18)
	rule.custom_minimum_size = Vector2(0.0, 2.0)
	rule.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return rule


static func _make_box(bg: Color, border: Color, width: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = bg
	box.border_color = border
	box.set_border_width_all(width)
	# Square corners on purpose: the whole interface follows the voxel look.
	box.set_corner_radius_all(0)
	return box


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

func _on_inventory_changed() -> void:
	if _open:
		_refresh()


func _on_store_changed(cell: Vector3i) -> void:
	if _open and cell == _cell:
		_refresh()


func _refresh() -> void:
	if not _built or _inventory == null or _store == null:
		return

	for i in _chest_slots.size():
		var slot: ChestSlot = _chest_slots[i]
		if slot == null:
			continue
		var id := _store.slot_block(_cell, i)
		var count := _store.slot_count(_cell, i)
		slot.set_content(id, count, count > 1, _preview(id, SLOT_SIZE - 10))

	var creative: bool = _inventory.creative
	for index in _inv_slots.size():
		var slot: ChestSlot = _inv_slots[index]
		if slot == null:
			continue
		var id := _inventory.slot_block(index)
		var count := _inventory.slot_count(index)
		slot.set_content(id, count, not creative and count > 1, _preview(id, SLOT_SIZE - 10))


func _preview(id: int, size: int) -> Texture2D:
	if id == Blocks.AIR:
		return null
	var key: int = id * 4096 + size
	if _preview_cache.has(key):
		return _preview_cache[key] as Texture2D
	var texture: Texture2D = Items.preview_any(id, size)
	_preview_cache[key] = texture
	return texture


# ---------------------------------------------------------------------------
# Overlay cooperation
# ---------------------------------------------------------------------------

## True when some other screen still holds the pointer. Keeps the mouse visible
## when this one closes underneath the pause menu.
func _other_screen_open() -> bool:
	if not is_inside_tree():
		return false
	var tree := get_tree()
	if tree == null:
		return false
	var root := tree.get_root()
	if root == null:
		return false
	return _scan_open(root)


func _scan_open(node: Node) -> bool:
	for child in node.get_children():
		if child is Node3D:
			continue
		if child != self and child is Control and child.has_method("is_open"):
			var state: Variant = child.call("is_open")
			if state is bool and state:
				return true
		if _scan_open(child):
			return true
	return false


func _play_sound(sound: String) -> void:
	if _sfx == null or not is_instance_valid(_sfx):
		_sfx = get_node_or_null(^"/root/Sfx")
	if _sfx != null and _sfx.has_method("play"):
		_sfx.call("play", sound, 0.0, 1.1)


# ---------------------------------------------------------------------------
# Slot widget
# ---------------------------------------------------------------------------

## One cell of the screen, either a chest slot or an inventory slot. Click to
## transfer, no drag.
class ChestSlot extends Panel:

	const BG := Color(0.10, 0.12, 0.15, 0.86)
	const BORDER := Color(0.85, 0.88, 0.92, 0.20)
	const BORDER_HOVER := Color(0.85, 0.88, 0.92, 0.62)
	const TEXT := Color(0.94, 0.96, 0.98)

	var ui: ChestUi = null
	var in_chest: bool = false
	var slot_index: int = -1
	var block_id: int = Blocks.AIR

	var _icon: TextureRect = null
	var _count: Label = null
	var _hovered: bool = false

	func configure(owner_ui: ChestUi, box_size: int, chest_side: bool, index: int) -> void:
		ui = owner_ui
		in_chest = chest_side
		slot_index = index
		mouse_filter = Control.MOUSE_FILTER_STOP
		custom_minimum_size = Vector2(float(box_size), float(box_size))

		_icon = TextureRect.new()
		_icon.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT, Control.PRESET_MODE_MINSIZE, 5)
		_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		_icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		_icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(_icon)

		_count = Label.new()
		_count.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT, Control.PRESET_MODE_MINSIZE, 3)
		_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		_count.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
		_count.add_theme_color_override("font_color", TEXT)
		_count.add_theme_font_size_override("font_size", 12)
		_count.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(_count)

		mouse_entered.connect(_on_mouse_entered)
		mouse_exited.connect(_on_mouse_exited)
		_restyle()

	func set_content(new_block_id: int, count: int, show_count: bool, texture: Texture2D) -> void:
		block_id = new_block_id
		if _icon != null:
			_icon.texture = texture if block_id != Blocks.AIR else null
		if _count != null:
			_count.text = str(count) if show_count else ""
		tooltip_text = "" if block_id == Blocks.AIR else Items.display_name_any(block_id)

	func _on_mouse_entered() -> void:
		_hovered = true
		_restyle()

	func _on_mouse_exited() -> void:
		_hovered = false
		_restyle()

	func _restyle() -> void:
		var box := StyleBoxFlat.new()
		box.bg_color = BG
		box.border_color = BORDER_HOVER if _hovered else BORDER
		box.set_border_width_all(2)
		box.set_corner_radius_all(0)
		add_theme_stylebox_override("panel", box)

	func _gui_input(event: InputEvent) -> void:
		if ui == null:
			return
		if event is InputEventMouseButton:
			var button := event as InputEventMouseButton
			if button.pressed and button.button_index == MOUSE_BUTTON_LEFT:
				if in_chest:
					ui.take_from_chest(slot_index)
				else:
					ui.put_into_chest(slot_index)
				# Never let the click reach the world behind the screen.
				accept_event()

	func _make_custom_tooltip(for_text: String) -> Object:
		if for_text.is_empty():
			return null
		var frame := PanelContainer.new()
		var box := StyleBoxFlat.new()
		box.bg_color = Color(0.06, 0.07, 0.09, 0.94)
		box.border_color = Color(0.85, 0.88, 0.92, 0.25)
		box.set_border_width_all(2)
		box.set_corner_radius_all(0)
		box.content_margin_left = 8.0
		box.content_margin_right = 8.0
		box.content_margin_top = 4.0
		box.content_margin_bottom = 4.0
		frame.add_theme_stylebox_override("panel", box)
		var label := Label.new()
		label.text = for_text
		label.add_theme_color_override("font_color", TEXT)
		label.add_theme_font_size_override("font_size", 14)
		frame.add_child(label)
		return frame
