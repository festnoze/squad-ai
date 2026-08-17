class_name InventoryUi
extends Control
## Full screen inventory: storage grid, hotbar and the creative block palette.
##
## Every widget is built in code. The screen releases the mouse when it opens and
## captures it again when it closes, but only when no other overlay is still up:
## the pause menu may sit on top of it.
##
## Slots support drag and drop through the standard Control virtuals, and route
## the result to Inventory.swap_slots. A drag released outside any slot simply
## does nothing, so the inventory is never touched by a cancelled drag.

signal closed()

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.42)

const SLOT_SIZE := 54
const PALETTE_SLOT_SIZE := 46
const GRID_COLUMNS := 9
const GRID_GAP := 4

## Payload tag of a slot drag, checked by _can_drop_data.
const DRAG_TYPE := "cubeforge_slot"

var _inventory: Inventory = null
var _open: bool = false
var _built: bool = false

## 36 entries (0..8 hotbar, 9..35 storage), each a SlotView. Some stay null
## until the tree is built.
var _slots: Array = []
var _palette_section: VBoxContainer = null
var _palette_grid: GridContainer = null
var _hint_label: Label = null
var _preview_cache: Dictionary = {}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

func _ready() -> void:
	_ensure_built()


## Binds the inventory model. Safe to call before or after the node enters the
## tree because the widget tree is built lazily.
func setup(inventory: Inventory) -> void:
	_ensure_built()
	if _inventory == inventory:
		_refresh()
		return
	if _inventory != null:
		if _inventory.changed.is_connected(_on_inventory_changed):
			_inventory.changed.disconnect(_on_inventory_changed)
		if _inventory.selection_changed.is_connected(_on_selection_changed):
			_inventory.selection_changed.disconnect(_on_selection_changed)
	_inventory = inventory
	if _inventory != null:
		_inventory.changed.connect(_on_inventory_changed)
		_inventory.selection_changed.connect(_on_selection_changed)
	_refresh()


func open() -> void:
	_ensure_built()
	if _open:
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


func is_open() -> bool:
	return _open


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

func _input(event: InputEvent) -> void:
	if InputMap.has_action("inventory") and event.is_action_pressed("inventory"):
		if _open:
			close()
		elif not _other_screen_open():
			open()
		else:
			return
		get_viewport().set_input_as_handled()
		return
	if not _open:
		return
	if InputMap.has_action("pause") and event.is_action_pressed("pause"):
		close()
		# Swallowed so the pause menu does not open in the same frame.
		get_viewport().set_input_as_handled()


# ---------------------------------------------------------------------------
# Actions called back by the slot widgets
# ---------------------------------------------------------------------------

## Drop target result: exchange two inventory slots.
func request_swap(from_slot: int, to_slot: int) -> void:
	if _inventory == null or from_slot == to_slot:
		return
	if from_slot < 0 or to_slot < 0:
		return
	var total: int = Inventory.HOTBAR_SLOTS + Inventory.STORAGE_SLOTS
	if from_slot >= total or to_slot >= total:
		return
	_inventory.swap_slots(from_slot, to_slot)
	_refresh()


## Creative palette click: put the block into the currently selected hotbar slot.
func assign_palette(block_id: int) -> void:
	if _inventory == null:
		return
	_inventory.set_slot(_inventory.selected, block_id, 1)
	_refresh()


func select_hotbar(slot: int) -> void:
	if _inventory == null:
		return
	_inventory.select(slot)
	_refresh()


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

	_slots.resize(Inventory.HOTBAR_SLOTS + Inventory.STORAGE_SLOTS)

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

	column.add_child(_make_title("Inventaire", 24))

	var storage_grid := _make_grid()
	column.add_child(storage_grid)
	for i in Inventory.STORAGE_SLOTS:
		var index: int = Inventory.HOTBAR_SLOTS + i
		var slot := SlotView.new()
		slot.configure(self, SLOT_SIZE)
		slot.slot_index = index
		storage_grid.add_child(slot)
		_slots[index] = slot

	column.add_child(_make_rule())
	column.add_child(_make_title("Barre d'action", 16))

	var hotbar_grid := _make_grid()
	column.add_child(hotbar_grid)
	for i in Inventory.HOTBAR_SLOTS:
		var slot := SlotView.new()
		slot.configure(self, SLOT_SIZE)
		slot.slot_index = i
		hotbar_grid.add_child(slot)
		_slots[i] = slot

	_palette_section = VBoxContainer.new()
	_palette_section.add_theme_constant_override("separation", 8)
	_palette_section.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_palette_section)

	_palette_section.add_child(_make_rule())
	_palette_section.add_child(_make_title("Palette créative", 16))

	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.custom_minimum_size = Vector2(0.0, 4.0 * float(PALETTE_SLOT_SIZE + GRID_GAP))
	_palette_section.add_child(scroll)

	_palette_grid = _make_grid()
	_palette_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_palette_grid)
	for i in Blocks.PALETTE.size():
		var block_id: int = int(Blocks.PALETTE[i])
		var entry := SlotView.new()
		entry.configure(self, PALETTE_SLOT_SIZE)
		entry.palette_id = block_id
		entry.set_content(block_id, 0, false, _preview(block_id, PALETTE_SLOT_SIZE - 10))
		_palette_grid.add_child(entry)

	_hint_label = Label.new()
	_hint_label.text = "Glissez un bloc d'une case à l'autre. Cliquez la palette pour remplir la case active."
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
	_refresh()


func _on_selection_changed(_slot: int) -> void:
	_refresh()


func _refresh() -> void:
	if not _built or _inventory == null:
		return
	var creative: bool = _inventory.creative
	if _palette_section != null:
		_palette_section.visible = creative
	var selected: int = _inventory.selected
	for index in _slots.size():
		var slot: SlotView = _slots[index]
		if slot == null:
			continue
		var block_id: int = _inventory.slot_block(index)
		var count: int = _inventory.slot_count(index)
		var show_count: bool = not creative and count > 1
		var texture: Texture2D = null
		if block_id != Blocks.AIR:
			texture = _preview(block_id, SLOT_SIZE - 10)
		slot.set_content(block_id, count, show_count, texture)
		slot.set_selected(index < Inventory.HOTBAR_SLOTS and index == selected)


func _preview(block_id: int, size: int) -> Texture2D:
	if block_id == Blocks.AIR:
		return null
	var key: int = block_id * 4096 + size
	if _preview_cache.has(key):
		return _preview_cache[key] as Texture2D
	var texture: Texture2D = VoxelAtlas.block_preview(block_id, size)
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


# ---------------------------------------------------------------------------
# Slot widget
# ---------------------------------------------------------------------------

## One cell of the interface. It is either an inventory slot (`slot_index` set,
## draggable) or a creative palette entry (`palette_id` set, clickable only).
class SlotView extends Panel:

	const DRAG_TYPE := "cubeforge_slot"
	const BG := Color(0.10, 0.12, 0.15, 0.86)
	const BORDER := Color(0.85, 0.88, 0.92, 0.20)
	const BORDER_HOVER := Color(0.85, 0.88, 0.92, 0.62)
	const BORDER_SELECTED := Color(1.0, 0.86, 0.35, 0.95)
	const TEXT := Color(0.94, 0.96, 0.98)

	var slot_index: int = -1
	var palette_id: int = -1
	var block_id: int = Blocks.AIR
	var ui: InventoryUi = null

	var _icon: TextureRect = null
	var _count: Label = null
	var _selected: bool = false
	var _hovered: bool = false

	func configure(owner_ui: InventoryUi, box_size: int) -> void:
		ui = owner_ui
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
			_icon.texture = texture
		if _count != null:
			_count.text = str(count) if show_count else ""
		tooltip_text = "" if block_id == Blocks.AIR else Blocks.display_name(block_id)

	func set_selected(value: bool) -> void:
		if _selected == value:
			return
		_selected = value
		_restyle()

	func _on_mouse_entered() -> void:
		_hovered = true
		_restyle()

	func _on_mouse_exited() -> void:
		_hovered = false
		_restyle()

	func _restyle() -> void:
		var border: Color = BORDER
		if _selected:
			border = BORDER_SELECTED
		elif _hovered:
			border = BORDER_HOVER
		var box := StyleBoxFlat.new()
		box.bg_color = BG
		box.border_color = border
		box.set_border_width_all(2)
		box.set_corner_radius_all(0)
		add_theme_stylebox_override("panel", box)

	func _gui_input(event: InputEvent) -> void:
		if ui == null:
			return
		if event is InputEventMouseButton:
			var button := event as InputEventMouseButton
			if button.pressed and button.button_index == MOUSE_BUTTON_LEFT:
				if palette_id >= 0:
					ui.assign_palette(palette_id)
				elif slot_index >= 0 and slot_index < Inventory.HOTBAR_SLOTS:
					ui.select_hotbar(slot_index)
				# Never let the click reach the world behind the screen.
				accept_event()

	func _get_drag_data(_at_position: Vector2) -> Variant:
		if palette_id >= 0 or slot_index < 0 or block_id == Blocks.AIR:
			return null
		var preview := TextureRect.new()
		preview.texture = _icon.texture
		preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		preview.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		preview.size = Vector2(42.0, 42.0)
		preview.position = Vector2(-21.0, -21.0)
		preview.modulate = Color(1.0, 1.0, 1.0, 0.85)
		var holder := Control.new()
		holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
		holder.add_child(preview)
		set_drag_preview(holder)
		return {"type": DRAG_TYPE, "slot": slot_index}

	func _can_drop_data(_at_position: Vector2, data: Variant) -> bool:
		if palette_id >= 0 or slot_index < 0:
			return false
		if typeof(data) != TYPE_DICTIONARY:
			return false
		var payload: Dictionary = data
		if String(payload.get("type", "")) != DRAG_TYPE:
			return false
		return int(payload.get("slot", -1)) != slot_index

	func _drop_data(_at_position: Vector2, data: Variant) -> void:
		if ui == null or typeof(data) != TYPE_DICTIONARY:
			return
		var payload: Dictionary = data
		if String(payload.get("type", "")) != DRAG_TYPE:
			return
		ui.request_swap(int(payload.get("slot", -1)), slot_index)

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
