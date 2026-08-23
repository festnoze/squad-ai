class_name WorldsUi
extends Control
## World selection screen: list, load, delete and create worlds.
##
## Every widget is built in code, following the shared voxel interface style.
## The screen never switches worlds itself: it only emits `world_chosen` and
## lets main.gd persist the choice and reload the scene. Deleting a world takes
## two clicks on the same button within three seconds, and the world currently
## being played can be neither loaded again nor deleted.

signal closed()

## `world_seed` of 0 means "keep the stored seed, or draw a random one for a
## brand new world". Any other value seeds the terrain of a fresh world.
signal world_chosen(world_name: String, world_seed: int)

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const TEXT_DIM := Color(0.68, 0.72, 0.78)
const ACCENT_COLOR := Color(1.0, 0.86, 0.35)
const DANGER_COLOR := Color(0.92, 0.48, 0.42)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.42)

const MAX_NAME_LENGTH := 24
const CONFIRM_WINDOW_MS := 3000
const ROW_HEIGHT := 56
const SEED_MASK := 0x7FFFFFFF

var _open := false
var _built := false
## Name of the world currently being played, as main.gd knows it.
var _current := "monde"

var _list: VBoxContainer = null
var _name_edit: LineEdit = null
var _seed_edit: LineEdit = null
var _status: Label = null
var _sfx: Node = null

## Double click confirmation state of the delete buttons. Only one deletion can
## be pending at a time: arming a second button disarms the first.
var _pending_delete := ""
var _pending_delete_at := 0
var _pending_button: Button = null
var _confirm_timer: Timer = null


# ---------------------------------------------------------------------------
# Pure helpers (unit tested)
# ---------------------------------------------------------------------------

## Cleans a player typed world name: trims, keeps only ASCII letters, digits,
## spaces, dashes and underscores, collapses runs of spaces, and caps the
## length at MAX_NAME_LENGTH. An unusable input yields the empty string.
static func sanitize_world_name(raw: String) -> String:
	var out := ""
	var last_space := false
	for i in raw.length():
		var c := raw[i]
		var code := c.unicode_at(0)
		var kept := (code >= 48 and code <= 57) \
				or (code >= 65 and code <= 90) \
				or (code >= 97 and code <= 122) \
				or c == "-" or c == "_"
		if kept:
			out += c
			last_space = false
		elif c == " ":
			# Collapse runs and drop leading spaces in the same move.
			if not last_space and not out.is_empty():
				out += " "
			last_space = true
	out = out.strip_edges()
	if out.length() > MAX_NAME_LENGTH:
		out = out.substr(0, MAX_NAME_LENGTH).strip_edges()
	return out


## Turns the seed field into an integer seed. Empty means 0 ("random or keep
## existing"). Integer text is folded to a positive non-zero 31 bit value so it
## round-trips through JSON and the settings file. Anything else is hashed
## deterministically, so the same phrase always yields the same world.
static func parse_seed(raw: String) -> int:
	var text := raw.strip_edges()
	if text.is_empty():
		return 0
	if text.is_valid_int():
		var value: int = absi(text.to_int()) & SEED_MASK
		return value if value != 0 else 1
	var hashed: int = text.hash() & SEED_MASK
	return hashed if hashed != 0 else 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

func _ready() -> void:
	_ensure_built()


## Reads the name of the world currently being played from the Game autoload.
## Reached through the tree so this file also compiles under --check-only.
func setup() -> void:
	_ensure_built()
	_current = "monde"
	var game := get_node_or_null(^"/root/Game")
	if game != null:
		var raw: Variant = game.get("world_name")
		if raw is String and not (raw as String).is_empty():
			_current = raw


func open() -> void:
	_ensure_built()
	if _open:
		return
	_open = true
	visible = true
	_status.text = ""
	_name_edit.text = ""
	_seed_edit.text = ""
	_refresh()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func close() -> void:
	if not _open:
		return
	_open = false
	visible = false
	_reset_pending()
	if not _other_screen_open():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	closed.emit()


func is_open() -> bool:
	return _open


func _input(event: InputEvent) -> void:
	if not _open:
		return
	if InputMap.has_action("pause") and event.is_action_pressed("pause"):
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

	var title := Label.new()
	title.text = "Mondes"
	title.add_theme_color_override("font_color", TEXT_COLOR)
	title.add_theme_font_size_override("font_size", 24)
	column.add_child(title)

	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.custom_minimum_size = Vector2(620.0, 5.0 * float(ROW_HEIGHT))
	column.add_child(scroll)

	_list = VBoxContainer.new()
	_list.add_theme_constant_override("separation", 6)
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(_list)

	column.add_child(_make_rule())

	var heading := Label.new()
	heading.text = "Nouveau monde"
	heading.add_theme_color_override("font_color", TEXT_COLOR)
	heading.add_theme_font_size_override("font_size", 18)
	column.add_child(heading)

	var form := HBoxContainer.new()
	form.add_theme_constant_override("separation", 10)
	column.add_child(form)

	_name_edit = _make_edit("nom du monde")
	_name_edit.max_length = MAX_NAME_LENGTH
	_name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	form.add_child(_name_edit)

	_seed_edit = _make_edit("graine (vide = hasard)")
	_seed_edit.custom_minimum_size = Vector2(220.0, 0.0)
	form.add_child(_seed_edit)

	var create_button := _make_button("Créer et jouer", Vector2(180.0, 40.0))
	create_button.pressed.connect(_on_create_pressed)
	form.add_child(create_button)

	_status = Label.new()
	_status.text = ""
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status.add_theme_color_override("font_color", ACCENT_COLOR)
	_status.add_theme_font_size_override("font_size", 13)
	column.add_child(_status)

	_confirm_timer = Timer.new()
	_confirm_timer.one_shot = true
	_confirm_timer.wait_time = float(CONFIRM_WINDOW_MS) / 1000.0
	_confirm_timer.process_mode = Node.PROCESS_MODE_ALWAYS
	_confirm_timer.timeout.connect(_reset_pending)
	add_child(_confirm_timer)


func _make_edit(placeholder: String) -> LineEdit:
	var edit := LineEdit.new()
	edit.placeholder_text = placeholder
	edit.custom_minimum_size = Vector2(0.0, 36.0)
	edit.add_theme_color_override("font_color", TEXT_COLOR)
	edit.add_theme_color_override("font_placeholder_color", TEXT_DIM)
	edit.add_theme_stylebox_override("normal", _make_box(Color(0.10, 0.12, 0.15, 0.90), PANEL_BORDER, 2))
	edit.add_theme_stylebox_override("focus", _make_box(Color(0.10, 0.12, 0.15, 0.94), ACCENT_COLOR, 2))
	return edit


func _make_button(text: String, minimum: Vector2 = Vector2(110.0, 36.0)) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = minimum
	button.focus_mode = Control.FOCUS_ALL
	button.add_theme_font_size_override("font_size", 15)
	button.add_theme_color_override("font_color", TEXT_COLOR)
	button.add_theme_color_override("font_hover_color", Color(1.0, 1.0, 1.0))
	button.add_theme_color_override("font_pressed_color", ACCENT_COLOR)
	button.add_theme_color_override("font_focus_color", TEXT_COLOR)
	button.add_theme_stylebox_override("normal", _make_box(Color(0.12, 0.14, 0.18, 0.90), PANEL_BORDER, 2))
	button.add_theme_stylebox_override("hover", _make_box(Color(0.19, 0.23, 0.29, 0.94), Color(0.85, 0.88, 0.92, 0.55), 2))
	button.add_theme_stylebox_override("pressed", _make_box(Color(0.08, 0.10, 0.13, 0.94), ACCENT_COLOR, 2))
	button.add_theme_stylebox_override("focus", _make_box(Color(0.0, 0.0, 0.0, 0.0), Color(1.0, 0.86, 0.35, 0.55), 2))
	button.add_theme_stylebox_override("disabled", _make_box(Color(0.10, 0.11, 0.13, 0.70), Color(0.6, 0.62, 0.66, 0.20), 2))
	return button


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
	box.set_corner_radius_all(0)
	box.content_margin_left = 10.0
	box.content_margin_right = 10.0
	box.content_margin_top = 6.0
	box.content_margin_bottom = 6.0
	return box


# ---------------------------------------------------------------------------
# World list
# ---------------------------------------------------------------------------

func _refresh() -> void:
	if not _built:
		return
	_reset_pending()
	for child in _list.get_children():
		_list.remove_child(child)
		child.queue_free()

	var names := SaveManager.list_worlds()
	if names.is_empty():
		var empty := Label.new()
		empty.text = "Aucun monde sauvegardé pour l'instant."
		empty.add_theme_color_override("font_color", TEXT_DIM)
		empty.add_theme_font_size_override("font_size", 14)
		_list.add_child(empty)
		return

	var current_folder := _folder_name(_current)
	for world_name in names:
		_list.add_child(_build_row(world_name, world_name == current_folder))


func _build_row(world_name: String, is_current: bool) -> Control:
	var row := PanelContainer.new()
	row.add_theme_stylebox_override("panel", _make_box(Color(0.10, 0.12, 0.15, 0.86), Color(0.85, 0.88, 0.92, 0.20), 2))
	row.custom_minimum_size = Vector2(0.0, float(ROW_HEIGHT))

	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 12)
	row.add_child(line)

	var texts := VBoxContainer.new()
	texts.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	texts.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	texts.add_theme_constant_override("separation", 2)
	line.add_child(texts)

	var name_label := Label.new()
	name_label.text = world_name + (" (actuel)" if is_current else "")
	name_label.add_theme_color_override("font_color", ACCENT_COLOR if is_current else TEXT_COLOR)
	name_label.add_theme_font_size_override("font_size", 16)
	texts.add_child(name_label)

	var seed_label := Label.new()
	var seed_value := _read_meta_seed(world_name)
	seed_label.text = "graine : %d" % seed_value if seed_value != 0 else "graine inconnue"
	seed_label.add_theme_color_override("font_color", TEXT_DIM)
	seed_label.add_theme_font_size_override("font_size", 13)
	texts.add_child(seed_label)

	var play_button := _make_button("Jouer")
	play_button.disabled = is_current
	play_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	play_button.pressed.connect(_on_play_pressed.bind(world_name))
	line.add_child(play_button)

	var delete_button := _make_button("Supprimer")
	delete_button.disabled = is_current
	delete_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	delete_button.add_theme_color_override("font_color", DANGER_COLOR)
	delete_button.pressed.connect(_on_delete_pressed.bind(world_name, delete_button))
	line.add_child(delete_button)

	return row


## Seed of a saved world, read straight from its meta.json without touching the
## rest of the save. 0 when the file is missing, unreadable or seedless.
## JSON numbers come back as floats, hence the double type test.
static func _read_meta_seed(world_name: String) -> int:
	var path := "user://saves/%s/meta.json" % world_name
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return 0
	var text := file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary:
		var raw: Variant = (parsed as Dictionary).get("seed")
		if raw is float or raw is int:
			return int(raw)
	return 0


## Folder a world name maps to on disk. Mirrors SaveManager._sanitize_name so
## the "(actuel)" mark matches the folder that list_worlds() returns even when
## the live name contains spaces.
static func _folder_name(raw: String) -> String:
	var out := ""
	for i in raw.length():
		var c := raw[i]
		var code := c.unicode_at(0)
		var kept := (code >= 48 and code <= 57) \
				or (code >= 65 and code <= 90) \
				or (code >= 97 and code <= 122) \
				or c == "-" or c == "_"
		if kept:
			out += c
		elif c == " " or c == ".":
			out += "_"
	out = out.lstrip("_-").rstrip("_-. ")
	if out.length() > 48:
		out = out.substr(0, 48)
	if out.is_empty():
		out = "monde"
	return out


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

func _on_play_pressed(world_name: String) -> void:
	if world_name == _folder_name(_current):
		return
	_play_sound("click")
	# Seed 0: the world's own stored seed drives the terrain.
	world_chosen.emit(world_name, 0)


func _on_create_pressed() -> void:
	var new_name := sanitize_world_name(_name_edit.text)
	if new_name.is_empty():
		_status.text = "Nom de monde invalide"
		return
	# A name colliding with an existing save folder would silently load that
	# old world (its stored seed wins) instead of creating anything.
	if SaveManager.list_worlds().has(_folder_name(new_name)):
		_status.text = "Ce monde existe déjà : choisissez-le dans la liste"
		return
	var seed_value := parse_seed(_seed_edit.text)
	if seed_value == 0:
		# Empty field: honour the placeholder promise and draw a real random
		# seed instead of inheriting the current settings seed, which would
		# clone the terrain of the world being played.
		var rng := RandomNumberGenerator.new()
		rng.randomize()
		seed_value = rng.randi_range(1, 0x7FFFFFFF)
	_play_sound("pop")
	world_chosen.emit(new_name, seed_value)


func _on_delete_pressed(world_name: String, button: Button) -> void:
	if world_name == _folder_name(_current):
		_status.text = "Impossible de supprimer le monde en cours"
		return
	var now := Time.get_ticks_msec()
	if _pending_delete == world_name and now - _pending_delete_at <= CONFIRM_WINDOW_MS:
		_reset_pending()
		var save := SaveManager.new(world_name)
		save.delete_world()
		_play_sound("break_wood")
		_status.text = "Monde supprimé : %s" % world_name
		_refresh()
		return
	# First click, or the window expired: arm this button and disarm any other.
	_reset_pending()
	_pending_delete = world_name
	_pending_delete_at = now
	_pending_button = button
	button.text = "Confirmer ?"
	if _confirm_timer != null and _confirm_timer.is_inside_tree():
		_confirm_timer.start()


func _reset_pending() -> void:
	_pending_delete = ""
	_pending_delete_at = 0
	if _pending_button != null and is_instance_valid(_pending_button):
		_pending_button.text = "Supprimer"
	_pending_button = null
	if _confirm_timer != null and not _confirm_timer.is_stopped():
		_confirm_timer.stop()


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
