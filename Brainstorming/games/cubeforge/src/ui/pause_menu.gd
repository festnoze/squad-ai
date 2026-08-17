class_name PauseMenu
extends Control
## Pause screen and settings panel, built entirely in code.
##
## The menu owns no game reference: it reports intent through its three signals
## and writes player preferences straight into the Game autoload. Quitting goes
## through `quit_requested` so main.gd can flush the world to disk first.
##
## Closing the menu always emits `resume_requested`, whether it came from the
## button or from the Escape key, so the caller has a single place to unpause.

signal resume_requested()
signal quit_requested()
signal save_requested()

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const MUTED_COLOR := Color(0.72, 0.76, 0.82)
const ACCENT_COLOR := Color(1.0, 0.86, 0.35)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.52)

const RENDER_DISTANCE_MIN := 3
const RENDER_DISTANCE_MAX := 16

var _open: bool = false
var _built: bool = false
## True while the widgets are being filled from Game, so the change handlers do
## not write the values straight back and save a hundred times.
var _syncing: bool = false

var _main_page: VBoxContainer = null
var _settings_page: VBoxContainer = null
var _resume_button: Button = null
var _settings_button: Button = null
var _status_label: Label = null
var _status_timer: Timer = null

var _sensitivity_slider: HSlider = null
var _sensitivity_value: Label = null
var _fov_slider: HSlider = null
var _fov_value: Label = null
var _distance_slider: HSlider = null
var _distance_value: Label = null
var _volume_slider: HSlider = null
var _volume_value: Label = null
var _invert_check: CheckBox = null
var _creative_check: CheckBox = null
var _fps_check: CheckBox = null
var _fly_check: CheckBox = null

## Value label produced by the last _add_slider call, so the caller can keep a
## typed reference without walking the grid again.
var _last_value_label: Label = null

## The Game autoload, reached through the scene tree rather than the `Game`
## identifier: it is the very same node, but this form also compiles under
## `godot --check-only`, which does not register autoload globals.
var _game: Node = null


## Never null once the node is in the tree. Returns null only if the autoload is
## missing, in which case the settings panel stays inert instead of crashing.
func _game_ref() -> Node:
	if _game == null:
		if not is_inside_tree():
			return null
		_game = get_node_or_null(^"/root/Game")
		if _game == null:
			push_warning("PauseMenu: autoload Game introuvable, réglages désactivés")
	return _game


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

func _ready() -> void:
	_ensure_built()


func open() -> void:
	_ensure_built()
	if _open:
		return
	_open = true
	visible = true
	_show_settings(false)
	# Always mirror the live values instead of resetting to defaults.
	_sync_from_game()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if _resume_button != null and _resume_button.is_inside_tree():
		_resume_button.grab_focus()


func close() -> void:
	if not _open:
		return
	_open = false
	visible = false
	_show_settings(false)
	# The inventory may still be open behind us and needs the pointer.
	if not _other_screen_open():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	resume_requested.emit()


func is_open() -> bool:
	return _open


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

func _input(event: InputEvent) -> void:
	if not InputMap.has_action("pause"):
		return
	if not event.is_action_pressed("pause"):
		return
	if _open:
		if _settings_page != null and _settings_page.visible:
			_show_settings(false)
		else:
			close()
		get_viewport().set_input_as_handled()
		return
	# Another screen is up: it owns Escape and closes itself first.
	if _other_screen_open():
		return
	open()
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
	margin.add_theme_constant_override("margin_left", 26)
	margin.add_theme_constant_override("margin_right", 26)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 22)
	margin.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	margin.add_child(column)

	var title := Label.new()
	title.text = "CUBEFORGE"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_color", TEXT_COLOR)
	title.add_theme_font_size_override("font_size", 30)
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "Partie en pause"
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	subtitle.add_theme_color_override("font_color", MUTED_COLOR)
	subtitle.add_theme_font_size_override("font_size", 14)
	subtitle.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(subtitle)

	column.add_child(_make_rule())

	_build_main_page(column)
	_build_settings_page(column)

	_status_label = Label.new()
	_status_label.text = ""
	_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_status_label.add_theme_color_override("font_color", ACCENT_COLOR)
	_status_label.add_theme_font_size_override("font_size", 14)
	_status_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.add_child(_status_label)

	_status_timer = Timer.new()
	_status_timer.one_shot = true
	_status_timer.wait_time = 2.2
	_status_timer.process_mode = Node.PROCESS_MODE_ALWAYS
	_status_timer.timeout.connect(_on_status_timeout)
	add_child(_status_timer)


func _build_main_page(parent: Control) -> void:
	_main_page = VBoxContainer.new()
	_main_page.add_theme_constant_override("separation", 8)
	_main_page.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(_main_page)

	_resume_button = _make_button("Reprendre")
	_resume_button.pressed.connect(_on_resume_pressed)
	_main_page.add_child(_resume_button)

	_settings_button = _make_button("Réglages")
	_settings_button.pressed.connect(_on_settings_pressed)
	_main_page.add_child(_settings_button)

	var save_button := _make_button("Sauvegarder")
	save_button.pressed.connect(_on_save_pressed)
	_main_page.add_child(save_button)

	var quit_button := _make_button("Quitter")
	quit_button.pressed.connect(_on_quit_pressed)
	_main_page.add_child(quit_button)


func _build_settings_page(parent: Control) -> void:
	_settings_page = VBoxContainer.new()
	_settings_page.add_theme_constant_override("separation", 10)
	_settings_page.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_settings_page.visible = false
	parent.add_child(_settings_page)

	var heading := Label.new()
	heading.text = "Réglages"
	heading.add_theme_color_override("font_color", TEXT_COLOR)
	heading.add_theme_font_size_override("font_size", 20)
	heading.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_settings_page.add_child(heading)

	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 12)
	grid.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_settings_page.add_child(grid)

	# Range mirrors Game.MOUSE_SENSITIVITY_MIN/MAX so a stored value is never
	# silently clamped by the widget.
	_sensitivity_slider = _add_slider(grid, "Sensibilité souris", 0.0004, 0.0100, 0.0001)
	_sensitivity_value = _last_value_label
	_sensitivity_slider.value_changed.connect(_on_sensitivity_changed)

	_fov_slider = _add_slider(grid, "Champ de vision", 60.0, 110.0, 1.0)
	_fov_value = _last_value_label
	_fov_slider.value_changed.connect(_on_fov_changed)

	_distance_slider = _add_slider(grid, "Distance d'affichage",
			float(RENDER_DISTANCE_MIN), float(RENDER_DISTANCE_MAX), 1.0)
	# Integer stepped: the streamer only understands whole chunks.
	_distance_slider.rounded = true
	_distance_value = _last_value_label
	_distance_slider.value_changed.connect(_on_distance_changed)

	_volume_slider = _add_slider(grid, "Volume", 0.0, 1.0, 0.01)
	_volume_value = _last_value_label
	_volume_slider.value_changed.connect(_on_volume_changed)

	_invert_check = _add_check(grid, "Inverser l'axe Y")
	_invert_check.toggled.connect(_on_invert_toggled)

	_creative_check = _add_check(grid, "Mode créatif")
	_creative_check.toggled.connect(_on_creative_toggled)

	_fps_check = _add_check(grid, "Afficher les FPS")
	_fps_check.toggled.connect(_on_fps_toggled)

	_fly_check = _add_check(grid, "God mode")
	_fly_check.toggled.connect(_on_fly_toggled)

	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 10)
	buttons.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_settings_page.add_child(buttons)

	var reset_button := _make_button("Valeurs par défaut")
	reset_button.custom_minimum_size = Vector2(180.0, 40.0)
	reset_button.pressed.connect(_on_reset_pressed)
	buttons.add_child(reset_button)

	var back_button := _make_button("Retour")
	back_button.custom_minimum_size = Vector2(180.0, 40.0)
	back_button.pressed.connect(_on_back_pressed)
	buttons.add_child(back_button)


func _add_slider(grid: GridContainer, text: String, minimum: float, maximum: float, step: float) -> HSlider:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", TEXT_COLOR)
	label.add_theme_font_size_override("font_size", 15)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	grid.add_child(label)

	var slider := HSlider.new()
	slider.min_value = minimum
	slider.max_value = maximum
	slider.step = step
	slider.custom_minimum_size = Vector2(260.0, 24.0)
	slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	grid.add_child(slider)

	var value := Label.new()
	value.text = ""
	value.custom_minimum_size = Vector2(84.0, 0.0)
	value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value.add_theme_color_override("font_color", ACCENT_COLOR)
	value.add_theme_font_size_override("font_size", 15)
	value.mouse_filter = Control.MOUSE_FILTER_IGNORE
	grid.add_child(value)

	_last_value_label = value
	return slider


func _add_check(grid: GridContainer, text: String) -> CheckBox:
	var label := Label.new()
	label.text = text
	label.add_theme_color_override("font_color", TEXT_COLOR)
	label.add_theme_font_size_override("font_size", 15)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	grid.add_child(label)

	var check := CheckBox.new()
	check.text = ""
	check.add_theme_color_override("font_color", TEXT_COLOR)
	grid.add_child(check)

	var filler := Control.new()
	filler.mouse_filter = Control.MOUSE_FILTER_IGNORE
	grid.add_child(filler)
	return check


func _make_button(text: String) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(320.0, 44.0)
	button.focus_mode = Control.FOCUS_ALL
	button.add_theme_font_size_override("font_size", 18)
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
	# Square corners on purpose: the whole interface follows the voxel look.
	box.set_corner_radius_all(0)
	box.content_margin_left = 12.0
	box.content_margin_right = 12.0
	box.content_margin_top = 8.0
	box.content_margin_bottom = 8.0
	return box


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

func _show_settings(value: bool) -> void:
	if _main_page == null or _settings_page == null:
		return
	_settings_page.visible = value
	_main_page.visible = not value
	if not value and _open and _resume_button != null and _resume_button.is_inside_tree():
		_resume_button.grab_focus()


# ---------------------------------------------------------------------------
# Settings binding
# ---------------------------------------------------------------------------

func _sync_from_game() -> void:
	if _sensitivity_slider == null:
		return
	var game := _game_ref()
	if game == null:
		return
	_syncing = true
	_sensitivity_slider.value = clampf(game.mouse_sensitivity,
			_sensitivity_slider.min_value, _sensitivity_slider.max_value)
	_fov_slider.value = clampf(game.fov, _fov_slider.min_value, _fov_slider.max_value)
	_distance_slider.value = float(clampi(game.render_distance, RENDER_DISTANCE_MIN, RENDER_DISTANCE_MAX))
	_volume_slider.value = clampf(game.sfx_volume, 0.0, 1.0)
	_invert_check.button_pressed = game.invert_y
	_creative_check.button_pressed = game.creative
	_fps_check.button_pressed = game.show_fps
	_fly_check.button_pressed = game.fly_mode and game.creative
	_syncing = false
	_update_sensitivity_label(_sensitivity_slider.value)
	_update_fov_label(_fov_slider.value)
	_update_distance_label(_distance_slider.value)
	_update_volume_label(_volume_slider.value)


func _update_sensitivity_label(value: float) -> void:
	if _sensitivity_value != null:
		_sensitivity_value.text = "%.2f" % (value * 1000.0)


func _update_fov_label(value: float) -> void:
	if _fov_value != null:
		_fov_value.text = "%d°" % roundi(value)


func _update_distance_label(value: float) -> void:
	if _distance_value != null:
		_distance_value.text = "%d ch." % roundi(value)


func _update_volume_label(value: float) -> void:
	if _volume_value != null:
		_volume_value.text = "%d %%" % roundi(value * 100.0)


func _on_sensitivity_changed(value: float) -> void:
	_update_sensitivity_label(value)
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.mouse_sensitivity = value
	game.save_settings()


func _on_fov_changed(value: float) -> void:
	_update_fov_label(value)
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.fov = value
	game.save_settings()


func _on_distance_changed(value: float) -> void:
	_update_distance_label(value)
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.render_distance = clampi(roundi(value), RENDER_DISTANCE_MIN, RENDER_DISTANCE_MAX)
	game.save_settings()


func _on_volume_changed(value: float) -> void:
	_update_volume_label(value)
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.sfx_volume = clampf(value, 0.0, 1.0)
	game.save_settings()


func _on_invert_toggled(pressed: bool) -> void:
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.invert_y = pressed
	game.save_settings()


func _on_creative_toggled(pressed: bool) -> void:
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.creative = pressed
	if not pressed:
		game.fly_mode = false
		if _fly_check != null:
			_fly_check.button_pressed = false
	game.save_settings()


func _on_fps_toggled(pressed: bool) -> void:
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	game.show_fps = pressed
	game.save_settings()


func _on_fly_toggled(pressed: bool) -> void:
	if _syncing:
		return
	var game := _game_ref()
	if game == null:
		return
	# God mode includes creative privileges. Keeping this checkbox interactive
	# avoids a disabled, nearly invisible control when the game is in survival.
	if pressed and not game.creative:
		game.creative = true
		if _creative_check != null:
			_syncing = true
			_creative_check.button_pressed = true
			_syncing = false
	game.fly_mode = pressed
	game.save_settings()


func _on_reset_pressed() -> void:
	var game := _game_ref()
	if game == null:
		return
	game.reset_settings()
	_sync_from_game()
	game.save_settings()
	_show_status("Réglages réinitialisés")


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

func _on_resume_pressed() -> void:
	close()


func _on_settings_pressed() -> void:
	_sync_from_game()
	_show_settings(true)


func _on_save_pressed() -> void:
	save_requested.emit()
	_show_status("Monde sauvegardé")


func _on_quit_pressed() -> void:
	# Never quit here: main.gd saves the world, then closes the game.
	quit_requested.emit()


func _on_back_pressed() -> void:
	_show_settings(false)


func _show_status(text: String) -> void:
	if _status_label == null:
		return
	_status_label.text = text
	if _status_timer != null and _status_timer.is_inside_tree():
		_status_timer.start()


func _on_status_timeout() -> void:
	if _status_label != null:
		_status_label.text = ""


# ---------------------------------------------------------------------------
# Overlay cooperation
# ---------------------------------------------------------------------------

## True when some other screen still holds the pointer. Keeps the mouse visible
## when this one closes on top of the inventory.
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
