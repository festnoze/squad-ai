## CALL OF WAR - end of campaign debrief.
##
## The last thing the player sees, so it is treated as a real document rather
## than as a banner: a carbon copy of the operation report, typed on the
## company's machine, punched for the file, signed and stamped. Everything on it
## is read from `War`; this screen computes nothing about the campaign and
## changes nothing in it.
##
## The report types itself in. Rows are faded in one after the other instead of
## being shown one after the other: a hidden Control still takes no room in its
## container, so revealing them by visibility would make the whole sheet jump on
## every row. Any click finishes the typing at once.
##
## Closed, this Control is invisible, transparent to the mouse and not
## processing: a full screen `MOUSE_FILTER_STOP` left behind an invisible screen
## swallows every click in the game.
class_name DebriefUi
extends Control

signal closed()
signal restart_requested()

# --- Paper palette -----------------------------------------------------------

const _BACKDROP := Color(0.04, 0.04, 0.03, 0.94)
const _PAPER := Color(0.82, 0.78, 0.65)
const _INK := Color(0.11, 0.10, 0.08)
const _INK_SOFT := Color(0.28, 0.26, 0.21)
const _STAMP := Color(0.63, 0.13, 0.10)
const _SILENT := Color(0.16, 0.38, 0.28)
const _KHAKI := Color(0.24, 0.23, 0.17)

## Seconds a destructive button waits for its confirmation. Same three seconds
## as the pause menu, on purpose: one confirmation habit for the whole game.
const _CONFIRM_SECONDS := 3.0

## Seconds between two typed rows, and how long one row takes to appear.
const _REVEAL_STEP := 0.05
const _REVEAL_FADE := 0.22
## Extra seconds after the last row before the stamp comes down.
const _STAMP_DELAY := 0.45

const _SHEET_WIDTH := 1010.0
const _SHEET_HEIGHT := 690.0


## A bare Control forwarding `_draw` to a callable, so the report can carry a
## painted layer on top of its typed one without a second script file.
class _Painter:
	extends Control

	var painter: Callable = Callable()

	func _draw() -> void:
		if painter.is_valid():
			painter.call(self)


var _world: GameWorld = null
var _tracker: ObjectiveTracker = null

var _sheet: PanelContainer = null
var _marks: _Painter = null
var _stat_list: VBoxContainer = null
var _sector_list: VBoxContainer = null
var _sector_empty: Label = null
var _citation: Label = null
var _sign_zone: Control = null
var _continue_button: Button = null
var _restart_button: Button = null

var _open: bool = false
var _restart_confirm: float = 0.0
var _reveal: float = 0.0
## Rows to fade in, in typing order.
var _rows: Array[Control] = []
## Rows: {"key": String, "value": Label}.
var _stat_rows: Array[Dictionary] = []

static var _font_cache: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	resized.connect(_layout_sheet)
	_layout_sheet()
	close()


## Keeps the sheet inside the window. A fixed size document is fine until the
## player runs the game in 1280 x 720, where a 690 pixel tall sheet leaves no
## desk around it and the shadow falls off screen.
func _layout_sheet() -> void:
	if _sheet == null or not is_instance_valid(_sheet):
		return
	var width := minf(_SHEET_WIDTH, maxf(560.0, size.x - 72.0))
	var height := minf(_SHEET_HEIGHT, maxf(420.0, size.y - 64.0))
	_sheet.offset_left = -width * 0.5
	_sheet.offset_right = width * 0.5
	_sheet.offset_top = -height * 0.5
	_sheet.offset_bottom = height * 0.5


func _process(delta: float) -> void:
	if not _open:
		return
	_reveal += delta
	_apply_reveal()
	_tick_confirmation(delta)
	queue_redraw()
	if _marks != null:
		_marks.queue_redraw()


# =============================================================================
# Public API (contract 11.10)
# =============================================================================

func setup(game_world: GameWorld, tracker: ObjectiveTracker) -> void:
	_world = game_world
	_tracker = tracker
	_refresh()


func open() -> void:
	if _open:
		return
	_open = true
	visible = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(true)
	_restart_confirm = 0.0
	_reveal = 0.0
	_layout_sheet()
	_refresh_confirm_label()
	_refresh()
	_apply_reveal()
	queue_redraw()
	_play("ui_open")


func close() -> void:
	var was_open := _open
	_open = false
	visible = false
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_process(false)
	_restart_confirm = 0.0
	_refresh_confirm_label()
	if was_open:
		_play("ui_close")
		closed.emit()


func is_open() -> bool:
	return _open


# =============================================================================
# Construction
# =============================================================================

func _build() -> void:
	_sheet = PanelContainer.new()
	_sheet.name = "Sheet"
	_sheet.set_anchors_preset(Control.PRESET_CENTER)
	_sheet.offset_left = -_SHEET_WIDTH * 0.5
	_sheet.offset_top = -_SHEET_HEIGHT * 0.5
	_sheet.offset_right = _SHEET_WIDTH * 0.5
	_sheet.offset_bottom = _SHEET_HEIGHT * 0.5
	_sheet.add_theme_stylebox_override("panel", _paper_box())
	add_child(_sheet)

	var margin := MarginContainer.new()
	# Wide left margin: the punched holes live there and nothing may be typed
	# over them.
	margin.add_theme_constant_override("margin_left", 62)
	margin.add_theme_constant_override("margin_right", 30)
	margin.add_theme_constant_override("margin_top", 24)
	margin.add_theme_constant_override("margin_bottom", 22)
	_sheet.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 8)
	margin.add_child(column)

	column.add_child(_build_header())
	column.add_child(_rule(2.0))
	column.add_child(_build_columns())
	column.add_child(_rule(1.0))
	column.add_child(_build_footer())

	# Painted on top of the typed sheet: grain, punched holes, signature, stamp.
	_marks = _Painter.new()
	_marks.name = "Marks"
	_marks.painter = Callable(self, "_draw_marks")
	_marks.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_marks.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_marks)


func _build_header() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 20)

	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.add_theme_constant_override("separation", 2)
	row.add_child(left)

	var service := Label.new()
	service.text = "QUARTIER GÉNÉRAL ALLIÉ - BUREAU DES OPÉRATIONS"
	_label_style(service, 12, _INK_SOFT, 4)
	left.add_child(service)
	_rows.append(service)

	var title := Label.new()
	title.text = "RAPPORT D'OPÉRATION"
	_label_style(title, 36, _INK, 8)
	left.add_child(title)
	_rows.append(title)

	var subtitle := Label.new()
	subtitle.text = "Poche de Normandie - été 1942"
	_label_style(subtitle, 14, _INK_SOFT, 1)
	left.add_child(subtitle)
	_rows.append(subtitle)

	var right := VBoxContainer.new()
	right.custom_minimum_size = Vector2(250.0, 0.0)
	right.alignment = BoxContainer.ALIGNMENT_END
	right.add_theme_constant_override("separation", 3)
	row.add_child(right)

	for text in ["CLASSIFICATION : SECRET", "EXEMPLAIRE UNIQUE", "DIFFUSION RESTREINTE"]:
		var line := Label.new()
		line.text = text
		line.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		_label_style(line, 11, _INK_SOFT, 3)
		right.add_child(line)
		_rows.append(line)
	return row


func _build_columns() -> Control:
	var row := HBoxContainer.new()
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	row.add_theme_constant_override("separation", 24)

	var left := VBoxContainer.new()
	left.custom_minimum_size = Vector2(430.0, 0.0)
	left.add_theme_constant_override("separation", 4)
	row.add_child(left)

	left.add_child(_section("BILAN GÉNÉRAL"))

	_stat_list = VBoxContainer.new()
	_stat_list.add_theme_constant_override("separation", 5)
	left.add_child(_stat_list)

	var keys: PackedStringArray = [
		"play_time", "kills", "accuracy", "headshots", "silent", "deaths",
		"intel", "objectives", "sectors", "contested",
	]
	var titles: PackedStringArray = [
		"Durée de l'opération", "Ennemis neutralisés", "Précision au tir",
		"Tirs à la tête", "Secteurs pris en silence", "Pertes personnelles",
		"Renseignements recueillis", "Objectifs accomplis", "Secteurs libérés",
		"Secteurs encore contestés",
	]
	for i in keys.size():
		_stat_rows.append({"key": keys[i], "value": _add_stat_row(titles[i])})

	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0.0, 10.0)
	gap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	left.add_child(gap)

	_citation = Label.new()
	_citation.text = ""
	_citation.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label_style(_citation, 14, _STAMP, 3)
	left.add_child(_citation)
	_rows.append(_citation)

	row.add_child(_rule(1.0, true))

	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 4)
	row.add_child(right)

	right.add_child(_section("CONDUITE PAR SECTEUR"))

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	right.add_child(head)
	_add_column_head(head, "SECTEUR", HORIZONTAL_ALIGNMENT_LEFT, 0.0, true)
	_add_column_head(head, "TEMPS", HORIZONTAL_ALIGNMENT_RIGHT, 88.0, false)
	_add_column_head(head, "STYLE", HORIZONTAL_ALIGNMENT_RIGHT, 124.0, false)
	right.add_child(_rule(1.0))

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	right.add_child(scroll)

	_sector_list = VBoxContainer.new()
	_sector_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sector_list.add_theme_constant_override("separation", 5)
	scroll.add_child(_sector_list)

	_sector_empty = Label.new()
	_sector_empty.text = "Aucun secteur enregistré."
	_sector_empty.visible = false
	_label_style(_sector_empty, 13, _INK_SOFT, 1)
	right.add_child(_sector_empty)
	return row


func _add_column_head(parent: Control, text: String, alignment: int,
		width: float, expand: bool) -> void:
	var label := Label.new()
	label.text = text
	label.horizontal_alignment = alignment
	if expand:
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	else:
		label.custom_minimum_size = Vector2(width, 0.0)
	_label_style(label, 11, _INK_SOFT, 4)
	parent.add_child(label)


func _build_footer() -> Control:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 20)

	# Left of the footer stays empty on purpose: the signature and the rubber
	# stamp are painted there, and typed text would end up under them.
	_sign_zone = Control.new()
	_sign_zone.custom_minimum_size = Vector2(0.0, 104.0)
	_sign_zone.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_sign_zone.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(_sign_zone)

	var actions := VBoxContainer.new()
	actions.custom_minimum_size = Vector2(330.0, 0.0)
	actions.alignment = BoxContainer.ALIGNMENT_END
	actions.add_theme_constant_override("separation", 8)
	row.add_child(actions)

	_continue_button = Button.new()
	_continue_button.text = "CONTINUER À EXPLORER"
	_continue_button.focus_mode = Control.FOCUS_NONE
	_continue_button.custom_minimum_size = Vector2(0.0, 40.0)
	_button_style(_continue_button)
	_continue_button.pressed.connect(_on_continue_pressed)
	actions.add_child(_continue_button)

	_restart_button = Button.new()
	_restart_button.text = "NOUVELLE CAMPAGNE"
	_restart_button.focus_mode = Control.FOCUS_NONE
	_restart_button.custom_minimum_size = Vector2(0.0, 40.0)
	_button_style(_restart_button)
	_restart_button.pressed.connect(_on_restart_pressed)
	actions.add_child(_restart_button)

	var hint := Label.new()
	hint.text = "La Normandie reste ouverte : le monde continue après le rapport."
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label_style(hint, 11, _INK_SOFT, 1)
	actions.add_child(hint)
	return row


func _add_stat_row(title: String) -> Label:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	_stat_list.add_child(row)
	_rows.append(row)

	var name_label := Label.new()
	name_label.text = title
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_label_style(name_label, 14, _INK_SOFT, 1)
	row.add_child(name_label)

	var dots := Label.new()
	dots.text = "................"
	dots.clip_text = true
	dots.custom_minimum_size = Vector2(46.0, 0.0)
	_label_style(dots, 13, Color(_INK.r, _INK.g, _INK.b, 0.35), 1)
	row.add_child(dots)

	var value_label := Label.new()
	value_label.text = "-"
	value_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	value_label.custom_minimum_size = Vector2(160.0, 0.0)
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
	box.add_child(_rule(1.0))
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0.0, 6.0)
	gap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_child(gap)
	_rows.append(label)
	return box


func _rule(thickness: float, vertical: bool = false) -> Control:
	var rule := Panel.new()
	if vertical:
		rule.custom_minimum_size = Vector2(thickness, 0.0)
	else:
		rule.custom_minimum_size = Vector2(0.0, thickness)
	var box := StyleBoxFlat.new()
	box.bg_color = Color(_INK.r, _INK.g, _INK.b, 0.42)
	box.set_corner_radius_all(0)
	rule.add_theme_stylebox_override("panel", box)
	rule.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return rule


# =============================================================================
# Content
# =============================================================================

func _refresh() -> void:
	_refresh_stats()
	_rebuild_sectors()
	if _citation != null:
		_citation.text = _citation_text()


func _refresh_stats() -> void:
	for row in _stat_rows:
		var label := row["value"] as Label
		if label == null or not is_instance_valid(label):
			continue
		label.text = _stat_text(String(row["key"]))


func _stat_text(key: String) -> String:
	if key == "play_time":
		return _clock(War.play_seconds)
	if key == "kills":
		return str(War.kills)
	if key == "accuracy":
		return "%d %% (%d / %d)" % [int(round(War.accuracy() * 100.0)),
				War.shots_hit, War.shots_fired]
	if key == "headshots":
		return str(War.headshots)
	if key == "silent":
		return "%d / %d" % [War.silent_captures, maxi(1, War.sector_count())]
	if key == "deaths":
		return str(War.deaths)
	if key == "intel":
		return str(War.intel_found)
	if key == "objectives":
		return "%d / %d" % [War.objectives_done, _objective_total()]
	if key == "sectors":
		return "%d / %d" % [War.captured_count(), War.sector_count()]
	if key == "contested":
		return str(War.contested_ids().size())
	return "-"


func _objective_total() -> int:
	if _tracker == null or not is_instance_valid(_tracker):
		return maxi(War.objectives_done, 0)
	return maxi(War.objectives_done, _tracker.all_objectives().size())


## One line per sector, ordered as the campaign was fought: from the drop zone
## inland, which is the order `MissionDefs` builds the chains in.
func _rebuild_sectors() -> void:
	if _sector_list == null:
		return
	for child in _sector_list.get_children():
		var row := child as Control
		if row != null:
			_rows.erase(row)
		_sector_list.remove_child(child)
		child.queue_free()
	var layout := _layout()
	if layout == null:
		if _sector_empty != null:
			_sector_empty.visible = true
		return
	var sites: Array[Layout.Site] = []
	for id in layout.sector_ids():
		var site := layout.site_by_id(id)
		if site != null:
			sites.append(site)
	var spawn := layout.spawn_point()
	sites.sort_custom(func(a: Layout.Site, b: Layout.Site) -> bool:
		return a.center.distance_squared_to(spawn) < b.center.distance_squared_to(spawn))
	if _sector_empty != null:
		_sector_empty.visible = sites.is_empty()
	for site in sites:
		_add_sector_row(site)


func _add_sector_row(site: Layout.Site) -> void:
	var result := War.sector_result(site.id)
	var taken := not result.is_empty()
	var contested := War.is_sector_contested(site.id)
	var silent := taken and bool(result.get("silent", false))

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	_sector_list.add_child(row)
	_rows.append(row)

	var name_label := Label.new()
	name_label.text = site.display_name
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	# Ellipsis rather than a hard cut: "Terrain d'aviation de Mo" reads like a
	# rendering bug, "Terrain d'aviation de..." reads like a narrow column.
	name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	name_label.clip_text = true
	_label_style(name_label, 14, _INK if taken else _INK_SOFT, 1)
	row.add_child(name_label)

	var time_label := Label.new()
	time_label.text = _short_clock(float(result.get("seconds", 0.0))) if taken else "-"
	time_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	time_label.custom_minimum_size = Vector2(88.0, 0.0)
	_label_style(time_label, 14, _INK if taken else _INK_SOFT, 2)
	row.add_child(time_label)

	var style_label := Label.new()
	style_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	style_label.custom_minimum_size = Vector2(124.0, 0.0)
	if not taken:
		style_label.text = "Non pris"
		_label_style(style_label, 13, _INK_SOFT, 1)
	elif contested:
		# The ledger says how the sector was taken, the map says who holds it
		# now. Both belong on the report, so the style keeps its word and the
		# contested state is added to it.
		style_label.text = ("Silencieux, contesté" if silent else "Assaut, contesté")
		_label_style(style_label, 13, _STAMP, 1)
	else:
		style_label.text = "Silencieux" if silent else "Assaut"
		_label_style(style_label, 13, _SILENT if silent else _INK, 2)
	row.add_child(style_label)


## A single line of praise, decided by the way the campaign was actually played.
func _citation_text() -> String:
	var sectors := War.sector_count()
	if sectors > 0 and War.silent_captures >= sectors:
		return "MENTION : toute la poche reprise sans donner l'alerte."
	if War.deaths == 0 and War.captured_count() > 0:
		return "MENTION : opération menée sans une seule évacuation sanitaire."
	if War.accuracy() >= 0.5 and War.shots_fired >= 60:
		return "MENTION : discipline de feu remarquable."
	if War.kills > 0 and War.headshots * 3 >= War.kills:
		return "MENTION : tir de précision constant sous le feu."
	if War.intel_found >= 4:
		return "MENTION : renseignement d'une valeur inestimable pour la suite."
	return "MENTION : mission conduite avec ténacité."


func _stamp_text() -> String:
	if War.sector_count() > 0 and War.captured_count() >= War.sector_count():
		return "MISSION ACCOMPLIE"
	return "RAPPORT PROVISOIRE"


# =============================================================================
# Typing animation
# =============================================================================

func _apply_reveal() -> void:
	for i in _rows.size():
		var row := _rows[i]
		if row == null or not is_instance_valid(row):
			continue
		var start := float(i) * _REVEAL_STEP
		row.modulate.a = clampf((_reveal - start) / _REVEAL_FADE, 0.0, 1.0)


func _reveal_done() -> float:
	return float(_rows.size()) * _REVEAL_STEP + _REVEAL_FADE


## Any click on the sheet finishes the typing at once. Waiting for a report to
## finish printing is not gameplay.
func _gui_input(event: InputEvent) -> void:
	if not _open:
		return
	var button := event as InputEventMouseButton
	if button == null or not button.pressed:
		return
	if _reveal < _reveal_done() + _STAMP_DELAY:
		_reveal = _reveal_done() + _STAMP_DELAY
		_apply_reveal()
		accept_event()


# =============================================================================
# Buttons
# =============================================================================

func _on_continue_pressed() -> void:
	_play("ui_click")
	# The world stays playable: closing IS the answer, Main takes it from there.
	close()


func _on_restart_pressed() -> void:
	_play("ui_click")
	if _restart_confirm > 0.0:
		_restart_confirm = 0.0
		_refresh_confirm_label()
		restart_requested.emit()
		return
	_restart_confirm = _CONFIRM_SECONDS
	_refresh_confirm_label()


func _tick_confirmation(delta: float) -> void:
	if _restart_confirm <= 0.0:
		return
	_restart_confirm = maxf(0.0, _restart_confirm - delta)
	_refresh_confirm_label()


func _refresh_confirm_label() -> void:
	if _restart_button == null or not is_instance_valid(_restart_button):
		return
	if _restart_confirm > 0.0:
		_restart_button.text = "CONFIRMER ? %d s" % int(ceil(_restart_confirm))
	else:
		_restart_button.text = "NOUVELLE CAMPAGNE"


# =============================================================================
# Painting
# =============================================================================

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), _BACKDROP, true)
	var line := Color(0.0, 0.0, 0.0, 0.10)
	var y := 0.0
	while y < size.y:
		draw_line(Vector2(0.0, y), Vector2(size.x, y), line, 1.0)
		y += 4.0


## Everything that is not typed: the grain of the paper, the punched holes, the
## signature block and the rubber stamp.
func _draw_marks(c: Control) -> void:
	if _sheet == null or not is_instance_valid(_sheet):
		return
	var sheet := Rect2(_sheet.position, _sheet.size)
	if sheet.size.x < 40.0 or sheet.size.y < 40.0:
		return
	_draw_grain(c, sheet)
	_draw_holes(c, sheet)
	var font := ThemeDB.fallback_font
	if font == null:
		return
	_draw_signature(c, font)
	_draw_stamp(c, font, sheet)


func _draw_grain(c: Control, sheet: Rect2) -> void:
	var line := Color(0.0, 0.0, 0.0, 0.045)
	var y := sheet.position.y + 3.0
	while y < sheet.end.y:
		c.draw_line(Vector2(sheet.position.x, y), Vector2(sheet.end.x, y), line, 1.0)
		y += 3.0
	# Carbon copy shadow along the binding edge.
	c.draw_rect(Rect2(sheet.position, Vector2(30.0, sheet.size.y)),
			Color(0.0, 0.0, 0.0, 0.07), true)


func _draw_holes(c: Control, sheet: Rect2) -> void:
	var x := sheet.position.x + 30.0
	for i in 2:
		var y := sheet.position.y + sheet.size.y * (0.30 + 0.40 * float(i))
		c.draw_circle(Vector2(x, y), 8.0, Color(0.05, 0.05, 0.04, 0.85))
		c.draw_arc(Vector2(x, y), 8.0, 0.0, TAU, 20, Color(0.0, 0.0, 0.0, 0.35), 1.4, true)


func _draw_signature(c: Control, font: Font) -> void:
	if _sign_zone == null or not is_instance_valid(_sign_zone):
		return
	var zone := Rect2(_sign_zone.global_position - global_position, _sign_zone.size)
	if zone.size.x < 200.0:
		return
	var alpha := clampf((_reveal - _reveal_done() * 0.8) / 0.5, 0.0, 1.0)
	if alpha <= 0.01:
		return
	var origin := zone.position + Vector2(6.0, 18.0)
	c.draw_string(font, origin, "Pour le commandement du secteur,",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(_INK_SOFT.r, _INK_SOFT.g, _INK_SOFT.b, alpha))
	# A signature drawn as a damped wave: no font in this project can fake a pen.
	var ink := Color(0.14, 0.16, 0.32, alpha * 0.9)
	var points := PackedVector2Array()
	var base := origin + Vector2(10.0, 44.0)
	for i in 44:
		var t := float(i) / 43.0
		var wobble := sin(t * 11.0) * 13.0 * (1.0 - t * 0.55)
		var drift := sin(t * 3.1 + 0.6) * 5.0
		points.append(base + Vector2(t * 190.0, wobble * 0.7 + drift))
	c.draw_polyline(points, ink, 2.0, true)
	c.draw_line(base + Vector2(-4.0, 22.0), base + Vector2(212.0, 22.0),
			Color(_INK.r, _INK.g, _INK.b, alpha * 0.45), 1.0)
	c.draw_string(font, base + Vector2(-4.0, 38.0), "Cpt. R. VASSEUR - 2e Bureau",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11,
			Color(_INK_SOFT.r, _INK_SOFT.g, _INK_SOFT.b, alpha))


func _draw_stamp(c: Control, font: Font, sheet: Rect2) -> void:
	var since := _reveal - (_reveal_done() + _STAMP_DELAY)
	if since <= 0.0:
		return
	var text := _stamp_text()
	var settle := clampf(since / 0.22, 0.0, 1.0)
	# The stamp comes down: it lands slightly too big, then settles.
	var scale := 1.0 + (1.0 - settle) * 0.5
	var alpha := settle
	var text_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 30)
	var centre := Vector2(sheet.position.x + sheet.size.x * 0.44,
			sheet.end.y - 104.0)
	c.draw_set_transform(centre, -0.16, Vector2(scale, scale))
	var box := Rect2(-text_size.x * 0.5 - 22.0, -30.0, text_size.x + 44.0, 60.0)
	var ink := Color(_STAMP.r, _STAMP.g, _STAMP.b, alpha * 0.88)
	c.draw_rect(box, ink, false, 4.0)
	c.draw_rect(box.grow(-7.0), Color(ink.r, ink.g, ink.b, alpha * 0.45), false, 1.6)
	c.draw_string(font, Vector2(-text_size.x * 0.5, 10.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 30, ink)
	c.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


# =============================================================================
# Styling
# =============================================================================

func _paper_box() -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = _PAPER
	box.border_color = Color(_INK.r, _INK.g, _INK.b, 0.9)
	box.set_border_width_all(3)
	box.set_corner_radius_all(0)
	box.shadow_color = Color(0.0, 0.0, 0.0, 0.6)
	box.shadow_size = 16
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


func _label_style(label: Label, size: int, color: Color, spacing: int) -> void:
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var font := _spaced_font(spacing)
	if font != null:
		label.add_theme_font_override("font", font)


## Glyph spacing is what turns the fallback font into a typewriter. Cached: one
## FontVariation per spacing for the whole game.
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
# Helpers
# =============================================================================

func _layout() -> Layout:
	if _world == null or not is_instance_valid(_world):
		return null
	return _world.layout()


func _clock(seconds: float) -> String:
	var total := int(maxf(0.0, seconds))
	return "%02d:%02d:%02d" % [total / 3600, (total / 60) % 60, total % 60]


func _short_clock(seconds: float) -> String:
	var total := int(maxf(0.0, seconds))
	if total >= 3600:
		return "%dh%02d" % [total / 3600, (total / 60) % 60]
	return "%d min %02d" % [total / 60, total % 60]


func _play(sample: String) -> void:
	if Sfx == null or not Sfx.has_sample(sample):
		return
	Sfx.play(sample, -6.0, 1.0)
