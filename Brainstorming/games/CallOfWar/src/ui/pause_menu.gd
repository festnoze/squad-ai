## CALL OF WAR - pause menu, built entirely from code.
##
## A field desk: a khaki sheet, a column of typed tabs on the left, the active
## page on the right. Settings are bound LIVE to the `Game` autoload, clamped by
## its own `*_MIN` / `*_MAX` constants, so moving a slider changes the game at
## once and never writes an illegal value. "Recommencer" and "Quitter" ask for a
## second press within three seconds, and forget about it if it does not come.
class_name PauseMenu
extends Control

signal resume_requested()
signal save_requested()
signal restart_requested()
signal quit_requested()

# --- Pages -------------------------------------------------------------------

const _PAGE_NONE := -1
const _PAGE_SETTINGS := 0
const _PAGE_STATS := 1

# --- Value formats -----------------------------------------------------------

const _FMT_FINE := 0        # 0.0024
const _FMT_DEGREES := 1     # 82 degres
const _FMT_TILES := 2       # 9 tuiles (576 m)
const _FMT_PERCENT := 3     # 85 %
const _FMT_DIFFICULTY := 4  # Soldat

# --- Paper palette -----------------------------------------------------------

const _BACKDROP := Color(0.05, 0.05, 0.04, 0.90)
const _PAPER := Color(0.79, 0.75, 0.61)
const _INK := Color(0.10, 0.09, 0.07)
const _INK_SOFT := Color(0.27, 0.25, 0.20)
const _STAMP := Color(0.63, 0.13, 0.10)
const _KHAKI := Color(0.24, 0.23, 0.17)

## Seconds a destructive button waits for its confirmation.
const _CONFIRM_SECONDS := 3.0
## Seconds the save receipt stays on screen.
const _RECEIPT_SECONDS := 2.4


var _sheet: PanelContainer = null
var _tab_column: VBoxContainer = null
var _pages: Control = null
var _settings_page: Control = null
var _stats_page: Control = null
var _stats_list: VBoxContainer = null
var _receipt: Label = null

var _restart_button: Button = null
var _quit_button: Button = null
var _tab_buttons: Array[Button] = []

var _open: bool = false
var _page: int = _PAGE_SETTINGS
var _syncing: bool = false
var _restart_confirm: float = 0.0
var _quit_confirm: float = 0.0
var _receipt_timer: float = 0.0
var _stats_accum: float = 0.0

## Rows: {"prop": String, "slider": HSlider, "value": Label, "format": int}.
var _slider_rows: Array[Dictionary] = []
## Rows: {"prop": String, "check": CheckBox}.
var _check_rows: Array[Dictionary] = []
## Rows: {"key": String, "value": Label}.
var _stat_rows: Array[Dictionary] = []

static var _font_cache: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	close()


func _process(delta: float) -> void:
	if not _open:
		return
	_tick_confirmations(delta)
	_tick_receipt(delta)
	_stats_accum += delta
	if _page == _PAGE_STATS and _stats_accum > 0.5:
		_stats_accum = 0.0
		_refresh_stats()


# =============================================================================
# Public API (contract 2.37)
# =============================================================================

func setup() -> void:
	if not Game.settings_changed.is_connected(_on_settings_changed):
		Game.settings_changed.connect(_on_settings_changed)
	_sync_settings()
	_refresh_stats()


func open() -> void:
	if _open:
		return
	_open = true
	visible = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(true)
	_reset_confirmations()
	_sync_settings()
	_refresh_stats()
	_select_page(_PAGE_SETTINGS)
	queue_redraw()
	_play("ui_open")


func close() -> void:
	var was_open := _open
	_open = false
	visible = false
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_process(false)
	_reset_confirmations()
	if was_open:
		_play("ui_close")


func is_open() -> bool:
	return _open


# =============================================================================
# Construction
# =============================================================================

func _build() -> void:
	_sheet = PanelContainer.new()
	_sheet.name = "Sheet"
	_sheet.set_anchors_preset(Control.PRESET_CENTER)
	_sheet.offset_left = -520.0
	_sheet.offset_top = -320.0
	_sheet.offset_right = 520.0
	_sheet.offset_bottom = 320.0
	_sheet.add_theme_stylebox_override("panel", _paper_box())
	add_child(_sheet)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 26)
	margin.add_theme_constant_override("margin_right", 26)
	margin.add_theme_constant_override("margin_top", 22)
	margin.add_theme_constant_override("margin_bottom", 22)
	_sheet.add_child(margin)

	var columns := HBoxContainer.new()
	columns.add_theme_constant_override("separation", 24)
	margin.add_child(columns)

	columns.add_child(_build_tabs())

	var rule := Panel.new()
	rule.custom_minimum_size = Vector2(2.0, 0.0)
	var rule_box := StyleBoxFlat.new()
	rule_box.bg_color = Color(_INK.r, _INK.g, _INK.b, 0.45)
	rule_box.set_corner_radius_all(0)
	rule.add_theme_stylebox_override("panel", rule_box)
	columns.add_child(rule)

	_pages = Control.new()
	_pages.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_pages.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_pages.mouse_filter = Control.MOUSE_FILTER_IGNORE
	columns.add_child(_pages)

	_settings_page = _build_settings_page()
	_pages.add_child(_settings_page)
	_stats_page = _build_stats_page()
	_pages.add_child(_stats_page)
	_select_page(_PAGE_SETTINGS)


func _build_tabs() -> Control:
	_tab_column = VBoxContainer.new()
	_tab_column.custom_minimum_size = Vector2(268.0, 0.0)
	_tab_column.add_theme_constant_override("separation", 8)

	var title := Label.new()
	title.text = "PAUSE"
	_label_style(title, 34, _INK, 8)
	_tab_column.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "Opération Normandie - 1942"
	_label_style(subtitle, 12, _INK_SOFT, 1)
	_tab_column.add_child(subtitle)

	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0.0, 14.0)
	gap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_tab_column.add_child(gap)

	_add_tab("REPRENDRE", _on_resume_pressed)
	_add_tab("RÉGLAGES", _on_settings_pressed)
	_add_tab("STATISTIQUES", _on_stats_pressed)
	_add_tab("SAUVEGARDER", _on_save_pressed)
	_restart_button = _add_tab("RECOMMENCER", _on_restart_pressed)
	_quit_button = _add_tab("QUITTER", _on_quit_pressed)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_tab_column.add_child(spacer)

	_receipt = Label.new()
	_receipt.text = ""
	_label_style(_receipt, 13, _STAMP, 2)
	_tab_column.add_child(_receipt)
	return _tab_column


func _add_tab(text: String, handler: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.custom_minimum_size = Vector2(0.0, 40.0)
	_button_style(button)
	button.pressed.connect(handler)
	_tab_column.add_child(button)
	_tab_buttons.append(button)
	return button


func _build_settings_page() -> Control:
	var scroll := ScrollContainer.new()
	scroll.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED

	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 6)
	scroll.add_child(column)

	column.add_child(_section("VISÉE ET CAMÉRA"))
	_add_slider(column, "mouse_sensitivity", "Sensibilité souris",
			Game.MOUSE_SENSITIVITY_MIN, Game.MOUSE_SENSITIVITY_MAX, 0.0001, _FMT_FINE)
	_add_check(column, "invert_y", "Inverser l'axe vertical")
	_add_slider(column, "fov", "Champ de vision", Game.FOV_MIN, Game.FOV_MAX, 1.0, _FMT_DEGREES)
	_add_check(column, "head_bob", "Balancement de la tête")

	column.add_child(_section("AFFICHAGE"))
	_add_slider(column, "view_distance", "Distance de vue",
			float(Game.VIEW_DISTANCE_MIN), float(Game.VIEW_DISTANCE_MAX), 1.0, _FMT_TILES)
	_add_check(column, "fullscreen", "Plein écran")
	_add_check(column, "show_fps", "Compteur d'images")
	_add_check(column, "show_debug", "Informations de débogage")
	_add_check(column, "blood_effects", "Effets de sang")

	column.add_child(_section("SON"))
	_add_slider(column, "sfx_volume", "Volume des effets",
			Game.VOLUME_MIN, Game.VOLUME_MAX, 0.01, _FMT_PERCENT)
	_add_slider(column, "music_volume", "Volume de la musique",
			Game.VOLUME_MIN, Game.VOLUME_MAX, 0.01, _FMT_PERCENT)

	column.add_child(_section("DIFFICULTÉ"))
	_add_slider(column, "difficulty", "Niveau", 0.0, 2.0, 1.0, _FMT_DIFFICULTY)

	var reset := Button.new()
	reset.text = "RÉINITIALISER LES RÉGLAGES"
	reset.focus_mode = Control.FOCUS_NONE
	reset.custom_minimum_size = Vector2(0.0, 34.0)
	_button_style(reset)
	reset.pressed.connect(_on_reset_pressed)
	column.add_child(reset)
	return scroll


func _build_stats_page() -> Control:
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 6)

	root.add_child(_section("RAPPORT DE CAMPAGNE"))

	_stats_list = VBoxContainer.new()
	_stats_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_stats_list.add_theme_constant_override("separation", 5)
	root.add_child(_stats_list)

	var keys: PackedStringArray = [
		"sectors", "objectives", "kills", "headshots", "shots_fired", "shots_hit",
		"accuracy", "deaths", "play_time", "alert", "difficulty",
	]
	var titles: PackedStringArray = [
		"Secteurs libérés", "Objectifs accomplis", "Ennemis abattus", "Tirs à la tête",
		"Coups tirés", "Coups au but", "Précision", "Pertes personnelles",
		"Temps de campagne", "Niveau d'alerte", "Difficulté",
	]
	for i in keys.size():
		_stat_rows.append({"key": keys[i], "value": _add_stat_row(titles[i])})
	return root


func _add_stat_row(title: String) -> Label:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	_stats_list.add_child(row)

	var name_label := Label.new()
	name_label.text = title
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_label_style(name_label, 14, _INK_SOFT, 1)
	row.add_child(name_label)

	var value_label := Label.new()
	value_label.text = "-"
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value_label.custom_minimum_size = Vector2(150.0, 0.0)
	_label_style(value_label, 15, _INK, 2)
	row.add_child(value_label)
	return value_label


func _section(title: String) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	var label := Label.new()
	label.text = title
	_label_style(label, 14, _STAMP, 5)
	box.add_child(label)
	var rule := Panel.new()
	rule.custom_minimum_size = Vector2(0.0, 1.0)
	var rule_box := StyleBoxFlat.new()
	rule_box.bg_color = Color(_INK.r, _INK.g, _INK.b, 0.35)
	rule_box.set_corner_radius_all(0)
	rule.add_theme_stylebox_override("panel", rule_box)
	box.add_child(rule)
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0.0, 6.0)
	gap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(gap)
	return box


## One labelled slider bound live to a `Game` property.
func _add_slider(parent: Control, prop: String, title: String, min_value: float,
		max_value: float, step: float, format: int) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	parent.add_child(row)

	var name_label := Label.new()
	name_label.text = title
	name_label.custom_minimum_size = Vector2(196.0, 0.0)
	_label_style(name_label, 14, _INK_SOFT, 1)
	row.add_child(name_label)

	var slider := HSlider.new()
	slider.min_value = min_value
	slider.max_value = max_value
	slider.step = step
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.custom_minimum_size = Vector2(0.0, 26.0)
	slider.focus_mode = Control.FOCUS_NONE
	_slider_style(slider)
	row.add_child(slider)

	var value_label := Label.new()
	value_label.text = "-"
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value_label.custom_minimum_size = Vector2(132.0, 0.0)
	_label_style(value_label, 14, _INK, 2)
	row.add_child(value_label)

	slider.value_changed.connect(_on_slider_changed.bind(prop))
	_slider_rows.append({"prop": prop, "slider": slider, "value": value_label, "format": format})


## One labelled checkbox bound live to a `Game` property.
func _add_check(parent: Control, prop: String, title: String) -> void:
	var check := CheckBox.new()
	check.text = title
	check.focus_mode = Control.FOCUS_NONE
	check.custom_minimum_size = Vector2(0.0, 28.0)
	check.add_theme_color_override("font_color", _INK_SOFT)
	check.add_theme_color_override("font_hover_color", _INK)
	check.add_theme_color_override("font_pressed_color", _INK)
	check.add_theme_font_size_override("font_size", 14)
	var font := _spaced_font(1)
	if font != null:
		check.add_theme_font_override("font", font)
	parent.add_child(check)
	check.toggled.connect(_on_check_toggled.bind(prop))
	_check_rows.append({"prop": prop, "check": check})


# =============================================================================
# Styling
# =============================================================================

func _paper_box() -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = _PAPER
	box.border_color = Color(_INK.r, _INK.g, _INK.b, 0.9)
	box.set_border_width_all(3)
	box.set_corner_radius_all(0)
	box.shadow_color = Color(0.0, 0.0, 0.0, 0.55)
	box.shadow_size = 12
	return box


func _button_style(button: Button) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(_KHAKI.r, _KHAKI.g, _KHAKI.b, 0.94)
	normal.border_color = Color(_INK.r, _INK.g, _INK.b, 0.85)
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(0)
	normal.content_margin_left = 14.0
	normal.content_margin_right = 14.0
	normal.content_margin_top = 8.0
	normal.content_margin_bottom = 8.0
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.36, 0.34, 0.24, 0.98)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.92)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("focus", normal)
	button.add_theme_color_override("font_color", Color(0.86, 0.83, 0.71))
	button.add_theme_color_override("font_hover_color", Color(0.96, 0.94, 0.86))
	button.add_theme_color_override("font_pressed_color", Color(0.98, 0.96, 0.90))
	button.add_theme_font_size_override("font_size", 15)
	var font := _spaced_font(4)
	if font != null:
		button.add_theme_font_override("font", font)


func _slider_style(slider: HSlider) -> void:
	var groove := StyleBoxFlat.new()
	groove.bg_color = Color(_INK.r, _INK.g, _INK.b, 0.45)
	groove.set_corner_radius_all(0)
	groove.content_margin_top = 3.0
	groove.content_margin_bottom = 3.0
	var filled := StyleBoxFlat.new()
	filled.bg_color = Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.85)
	filled.set_corner_radius_all(0)
	filled.content_margin_top = 3.0
	filled.content_margin_bottom = 3.0
	slider.add_theme_stylebox_override("slider", groove)
	slider.add_theme_stylebox_override("grabber_area", filled)
	slider.add_theme_stylebox_override("grabber_area_highlight", filled)


func _label_style(label: Label, size: int, color: Color, spacing: int) -> void:
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	var font := _spaced_font(spacing)
	if font != null:
		label.add_theme_font_override("font", font)


static func _spaced_font(spacing: int) -> Font:
	if spacing <= 0:
		return null
	if _font_cache.has(spacing):
		return _font_cache[spacing] as Font
	var base := ThemeDB.fallback_font
	if base == null:
		return null
	var variation := FontVariation.new()
	variation.base_font = base
	variation.spacing_glyph = spacing
	_font_cache[spacing] = variation
	return variation


# =============================================================================
# Pages
# =============================================================================

func _select_page(page: int) -> void:
	_page = page
	if _settings_page != null:
		_settings_page.visible = page == _PAGE_SETTINGS
	if _stats_page != null:
		_stats_page.visible = page == _PAGE_STATS
	if page == _PAGE_STATS:
		_refresh_stats()


# =============================================================================
# Settings binding
# =============================================================================

func _sync_settings() -> void:
	_syncing = true
	for row in _slider_rows:
		var slider := row["slider"] as HSlider
		if slider == null or not is_instance_valid(slider):
			continue
		var raw: Variant = Game.get(String(row["prop"]))
		var value: float = slider.min_value
		if raw != null:
			value = float(raw)
		slider.value = value
		_update_slider_label(row, value)
	for row in _check_rows:
		var check := row["check"] as CheckBox
		if check == null or not is_instance_valid(check):
			continue
		var raw: Variant = Game.get(String(row["prop"]))
		check.button_pressed = raw != null and bool(raw)
	_syncing = false


func _update_slider_label(row: Dictionary, value: float) -> void:
	var label := row["value"] as Label
	if label == null or not is_instance_valid(label):
		return
	label.text = _format_value(int(row["format"]), value)


func _format_value(format: int, value: float) -> String:
	if format == _FMT_FINE:
		return "%.4f" % value
	if format == _FMT_DEGREES:
		return "%d degrés" % int(round(value))
	if format == _FMT_TILES:
		var tiles := int(round(value))
		return "%d tuiles (%d m)" % [tiles, tiles * 64]
	if format == _FMT_PERCENT:
		return "%d %%" % int(round(value * 100.0))
	if format == _FMT_DIFFICULTY:
		return String(Game.difficulty_name())
	return "%.2f" % value


func _on_slider_changed(value: float, prop: String) -> void:
	if _syncing:
		return
	if prop == "view_distance" or prop == "difficulty":
		Game.set(prop, int(round(value)))
	else:
		Game.set(prop, value)
	# Read back: the Game setter clamps, so the label must show what was kept.
	for row in _slider_rows:
		if String(row["prop"]) != prop:
			continue
		var raw: Variant = Game.get(prop)
		var kept: float = value
		if raw != null:
			kept = float(raw)
		_update_slider_label(row, kept)
		break


func _on_check_toggled(pressed: bool, prop: String) -> void:
	if _syncing:
		return
	Game.set(prop, pressed)
	_play("ui_click")


func _on_settings_changed() -> void:
	if _syncing:
		return
	_sync_settings()


func _on_reset_pressed() -> void:
	Game.reset_settings()
	_sync_settings()
	_show_receipt("Réglages réinitialisés")
	_play("ui_click")


# =============================================================================
# Statistics
# =============================================================================

func _refresh_stats() -> void:
	for row in _stat_rows:
		var label := row["value"] as Label
		if label == null or not is_instance_valid(label):
			continue
		label.text = _stat_text(String(row["key"]))


func _stat_text(key: String) -> String:
	if key == "sectors":
		return "%d / %d" % [War.captured_count(), War.sector_count()]
	if key == "objectives":
		return str(War.objectives_done)
	if key == "kills":
		return str(War.kills)
	if key == "headshots":
		return str(War.headshots)
	if key == "shots_fired":
		return str(War.shots_fired)
	if key == "shots_hit":
		return str(War.shots_hit)
	if key == "accuracy":
		return "%d %%" % int(round(War.accuracy() * 100.0))
	if key == "deaths":
		return str(War.deaths)
	if key == "play_time":
		return _clock(War.play_seconds)
	if key == "alert":
		return String(War.alert_name())
	if key == "difficulty":
		return String(Game.difficulty_name())
	return "-"


# =============================================================================
# Tab handlers
# =============================================================================

func _on_resume_pressed() -> void:
	_play("ui_click")
	close()
	resume_requested.emit()


func _on_settings_pressed() -> void:
	_play("ui_click")
	_reset_confirmations()
	_select_page(_PAGE_SETTINGS)


func _on_stats_pressed() -> void:
	_play("ui_click")
	_reset_confirmations()
	_select_page(_PAGE_STATS)


func _on_save_pressed() -> void:
	_play("ui_click")
	_reset_confirmations()
	_show_receipt("Partie sauvegardée")
	save_requested.emit()


func _on_restart_pressed() -> void:
	_play("ui_click")
	if _restart_confirm > 0.0:
		_reset_confirmations()
		restart_requested.emit()
		return
	_quit_confirm = 0.0
	_restart_confirm = _CONFIRM_SECONDS
	_refresh_confirm_labels()


func _on_quit_pressed() -> void:
	_play("ui_click")
	if _quit_confirm > 0.0:
		_reset_confirmations()
		quit_requested.emit()
		return
	_restart_confirm = 0.0
	_quit_confirm = _CONFIRM_SECONDS
	_refresh_confirm_labels()


func _tick_confirmations(delta: float) -> void:
	if _restart_confirm <= 0.0 and _quit_confirm <= 0.0:
		return
	_restart_confirm = maxf(0.0, _restart_confirm - delta)
	_quit_confirm = maxf(0.0, _quit_confirm - delta)
	_refresh_confirm_labels()


func _refresh_confirm_labels() -> void:
	if _restart_button != null:
		if _restart_confirm > 0.0:
			_restart_button.text = "CONFIRMER ? %d s" % int(ceil(_restart_confirm))
		else:
			_restart_button.text = "RECOMMENCER"
	if _quit_button != null:
		if _quit_confirm > 0.0:
			_quit_button.text = "CONFIRMER ? %d s" % int(ceil(_quit_confirm))
		else:
			_quit_button.text = "QUITTER"


func _reset_confirmations() -> void:
	_restart_confirm = 0.0
	_quit_confirm = 0.0
	_refresh_confirm_labels()


func _show_receipt(text: String) -> void:
	if _receipt == null:
		return
	_receipt.text = text.to_upper()
	_receipt_timer = _RECEIPT_SECONDS


func _tick_receipt(delta: float) -> void:
	if _receipt_timer <= 0.0:
		return
	_receipt_timer = maxf(0.0, _receipt_timer - delta)
	if _receipt_timer <= 0.0 and _receipt != null:
		_receipt.text = ""


# =============================================================================
# Painting: the backdrop behind the sheet
# =============================================================================

func _draw() -> void:
	var rect := Rect2(Vector2.ZERO, size)
	draw_rect(rect, _BACKDROP, true)
	var line := Color(0.0, 0.0, 0.0, 0.10)
	var y := 0.0
	while y < size.y:
		draw_line(Vector2(0.0, y), Vector2(size.x, y), line, 1.0)
		y += 4.0


# =============================================================================
# Helpers
# =============================================================================

func _clock(seconds: float) -> String:
	var total := int(maxf(0.0, seconds))
	return "%02d:%02d:%02d" % [total / 3600, (total / 60) % 60, total % 60]


func _play(sample: String) -> void:
	if Sfx == null or not Sfx.has_sample(sample):
		return
	Sfx.play(sample, -6.0, 1.0)
