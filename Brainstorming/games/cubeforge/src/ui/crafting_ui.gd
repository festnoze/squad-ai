class_name CraftingUi
extends Control
## Crafting screen: the full recipe book in one scrollable list.
##
## Opened by right-clicking a placed crafting table (full access) or with the
## craft key anywhere (hand recipes only, unless a table stands nearby). Every
## widget is built in code, following the shared voxel interface style.
##
## A row shows the output preview, the produced quantity, the ingredient list
## with live have/need counts, and a craft button. Table-only recipes are
## locked away from the table.

signal closed()

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const TEXT_DIM := Color(0.68, 0.72, 0.78)
const TEXT_MISSING := Color(0.92, 0.48, 0.42)
const TEXT_LOCKED := Color(0.55, 0.58, 0.64)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.42)

const ICON_PX := 40
const ROW_HEIGHT := 56

var _inventory: Inventory = null
var _open := false
var _built := false
var _near_table := false

var _title: Label = null
var _hint: Label = null
var _rows: Array[Dictionary] = []
var _sfx: Node = null


func _ready() -> void:
	_ensure_built()


func setup(inventory: Inventory) -> void:
	_ensure_built()
	if _inventory == inventory:
		return
	if _inventory != null and _inventory.changed.is_connected(_on_inventory_changed):
		_inventory.changed.disconnect(_on_inventory_changed)
	_inventory = inventory
	if _inventory != null:
		_inventory.changed.connect(_on_inventory_changed)


## `near_table` unlocks the table-only recipes for this visit.
func open(near_table: bool) -> void:
	_ensure_built()
	if _open:
		_near_table = near_table
		_refresh()
		return
	_open = true
	_near_table = near_table
	visible = true
	_refresh()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close() -> void:
	if not _open:
		return
	_open = false
	visible = false
	if not _other_screen_open():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	closed.emit()


func is_open() -> bool:
	return _open


func _input(event: InputEvent) -> void:
	if not _open:
		return
	var wants_close := false
	if InputMap.has_action("pause") and event.is_action_pressed("pause"):
		wants_close = true
	elif InputMap.has_action("craft") and event.is_action_pressed("craft"):
		wants_close = true
	elif InputMap.has_action("inventory") and event.is_action_pressed("inventory"):
		wants_close = true
	if wants_close:
		close()
		get_viewport().set_input_as_handled()


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
	frame.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	margin.add_child(column)

	_title = Label.new()
	_title.text = "Fabrication"
	_title.add_theme_color_override("font_color", TEXT_COLOR)
	_title.add_theme_font_size_override("font_size", 24)
	column.add_child(_title)

	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.custom_minimum_size = Vector2(620.0, 7.5 * float(ROW_HEIGHT))
	column.add_child(scroll)

	var list := VBoxContainer.new()
	list.add_theme_constant_override("separation", 6)
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)

	for recipe in Recipes.all():
		list.add_child(_build_row(recipe))

	_hint = Label.new()
	_hint.text = ""
	_hint.add_theme_color_override("font_color", TEXT_DIM)
	_hint.add_theme_font_size_override("font_size", 13)
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(_hint)


func _build_row(recipe: Dictionary) -> Control:
	var row := PanelContainer.new()
	row.add_theme_stylebox_override("panel", _make_box(Color(0.10, 0.12, 0.15, 0.86), Color(0.85, 0.88, 0.92, 0.20), 2))
	row.custom_minimum_size = Vector2(0.0, float(ROW_HEIGHT))

	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 12)
	row.add_child(line)

	var icon := TextureRect.new()
	icon.custom_minimum_size = Vector2(ICON_PX, ICON_PX)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	icon.texture = Items.preview_any(recipe["output"], ICON_PX)
	icon.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	line.add_child(icon)

	var texts := VBoxContainer.new()
	texts.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	texts.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	texts.add_theme_constant_override("separation", 2)
	line.add_child(texts)

	var name_label := Label.new()
	var count: int = recipe["count"]
	var display := Items.display_name_any(recipe["output"])
	name_label.text = display if count <= 1 else "%s x%d" % [display, count]
	name_label.add_theme_color_override("font_color", TEXT_COLOR)
	name_label.add_theme_font_size_override("font_size", 16)
	texts.add_child(name_label)

	var needs_label := Label.new()
	needs_label.add_theme_font_size_override("font_size", 13)
	texts.add_child(needs_label)

	var button := Button.new()
	button.text = "Fabriquer"
	button.custom_minimum_size = Vector2(110.0, 36.0)
	button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	button.pressed.connect(_on_craft_pressed.bind(recipe))
	line.add_child(button)

	_rows.append({
		"recipe": recipe,
		"needs": needs_label,
		"button": button,
	})
	return row


static func _make_box(bg: Color, border: Color, width: int) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = bg
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(0)
	box.content_margin_left = 10.0
	box.content_margin_right = 10.0
	box.content_margin_top = 6.0
	box.content_margin_bottom = 6.0
	return box


# ---------------------------------------------------------------------------
# Refresh and crafting
# ---------------------------------------------------------------------------

func _on_inventory_changed() -> void:
	if _open:
		_refresh()


func _on_craft_pressed(recipe: Dictionary) -> void:
	if _inventory == null:
		return
	if bool(recipe["table"]) and not _near_table:
		return
	if Recipes.craft(recipe, _inventory):
		_play_sound("pop")
	# Inventory.changed already triggers the refresh.


func _refresh() -> void:
	if not _built or _inventory == null:
		return
	_title.text = "Fabrication (table)" if _near_table else "Fabrication"
	if _near_table:
		_hint.text = "Clic droit sur une table posée pour fabriquer, Maj + clic droit pour construire contre elle."
	else:
		_hint.text = "Recettes de base seulement. Posez une table de fabrication et cliquez-la pour tout débloquer."
	for entry in _rows:
		var recipe: Dictionary = entry["recipe"]
		var needs: Label = entry["needs"]
		var button: Button = entry["button"]
		var locked: bool = bool(recipe["table"]) and not _near_table
		var can_craft := not locked and Recipes.craftable(recipe, _inventory)
		var missing := false

		var parts: PackedStringArray = []
		for input: Array in recipe["inputs"]:
			var have: int = _inventory.count_of(input[0])
			var need: int = input[1]
			if have < need:
				missing = true
			parts.append("%s %d/%d" % [Items.display_name_any(input[0]), mini(have, 999), need])
		if locked:
			needs.text = "Nécessite une table de fabrication - " + ", ".join(parts)
			needs.add_theme_color_override("font_color", TEXT_LOCKED)
		else:
			needs.text = ", ".join(parts)
			needs.add_theme_color_override("font_color", TEXT_MISSING if missing and not _inventory.creative else TEXT_DIM)
		button.disabled = not can_craft


# ---------------------------------------------------------------------------
# Cooperation with the other screens
# ---------------------------------------------------------------------------

func _other_screen_open() -> bool:
	if not is_inside_tree():
		return false
	var tree := get_tree()
	if tree == null or tree.get_root() == null:
		return false
	return _scan_open(tree.get_root())


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
