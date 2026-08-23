## CALL OF WAR - mission journal (key J).
##
## The campaign notebook: every objective the staff ever handed out, grouped by
## sector, with its state, its full briefing, and the distance from the agent.
## Built entirely from code, styled as a typed carbon copy sheet: khaki paper,
## black ink, a red stamp for whatever is burning right now.
class_name ObjectivesUi
extends Control

signal closed()
signal objective_selected(objective_id: int)

# --- States ------------------------------------------------------------------

const _S_TODO := 0
const _S_ACTIVE := 1
const _S_DONE := 2
const _S_FAILED := 3

const _STATE_LABELS: PackedStringArray = ["À FAIRE", "EN COURS", "ACCOMPLI", "ÉCHOUÉ"]

# --- Paper palette -----------------------------------------------------------

const _BACKDROP := Color(0.06, 0.06, 0.05, 0.92)
const _PAPER := Color(0.78, 0.74, 0.60)
const _PAPER_LINE := Color(0.62, 0.59, 0.47)
const _INK := Color(0.10, 0.09, 0.07)
const _INK_SOFT := Color(0.26, 0.24, 0.19)
const _STAMP := Color(0.62, 0.13, 0.10)
const _DONE_GREEN := Color(0.18, 0.32, 0.16)
const _TODO_GREY := Color(0.36, 0.34, 0.27)

## Seconds between two distance refreshes while the journal is open.
const _DISTANCE_PERIOD := 0.30


var _tracker: ObjectiveTracker = null
var _player: Player = null
var _layout: Layout = null

var _sheet: PanelContainer = null
var _list: VBoxContainer = null
var _summary: Label = null
var _empty_label: Label = null

var _open: bool = false
var _selected_id: int = -1
var _distance_accum: float = 0.0

## Objective id -> true, filled by the objective_failed signal.
var _failed: Dictionary = {}
## Rows currently displayed: {"id": int, "distance": Label, "button": Button}.
var _rows: Array[Dictionary] = []

static var _font_cache: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	close()


func _process(delta: float) -> void:
	if not _open:
		return
	_distance_accum += delta
	if _distance_accum < _DISTANCE_PERIOD:
		return
	_distance_accum = 0.0
	_refresh_distances()


# =============================================================================
# Public API (contract 2.36)
# =============================================================================

func setup(tracker: ObjectiveTracker) -> void:
	_tracker = tracker
	_failed.clear()
	if _tracker != null:
		_connect(_tracker, "objective_started", _on_journal_dirty)
		_connect(_tracker, "objective_progress", _on_progress_dirty)
		_connect(_tracker, "objective_completed", _on_journal_dirty)
		_connect(_tracker, "objective_failed", _on_objective_failed)
		_connect(_tracker, "campaign_completed", _on_campaign_completed)


func open() -> void:
	if _open:
		return
	_open = true
	visible = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(true)
	_rebuild()
	queue_redraw()
	_play("ui_open")


func close() -> void:
	var was_open := _open
	_open = false
	visible = false
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_process(false)
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
	_sheet.set_anchors_preset(Control.PRESET_FULL_RECT)
	_sheet.offset_left = 90.0
	_sheet.offset_top = 60.0
	_sheet.offset_right = -90.0
	_sheet.offset_bottom = -60.0
	_sheet.add_theme_stylebox_override("panel", _paper_box())
	add_child(_sheet)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 26)
	margin.add_theme_constant_override("margin_right", 26)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 20)
	_sheet.add_child(margin)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	margin.add_child(column)

	column.add_child(_build_header())

	var rule := Panel.new()
	rule.custom_minimum_size = Vector2(0.0, 2.0)
	var rule_box := StyleBoxFlat.new()
	rule_box.bg_color = Color(_INK.r, _INK.g, _INK.b, 0.55)
	rule_box.set_corner_radius_all(0)
	rule.add_theme_stylebox_override("panel", rule_box)
	column.add_child(rule)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	column.add_child(scroll)

	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 8)
	scroll.add_child(_list)

	_empty_label = Label.new()
	_empty_label.text = "Aucun ordre reçu pour le moment. Prenez contact avec la Résistance."
	_label_style(_empty_label, 15, _INK_SOFT, 1)
	_empty_label.visible = false
	column.add_child(_empty_label)


func _build_header() -> Control:
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 18)

	var titles := VBoxContainer.new()
	titles.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	titles.add_theme_constant_override("separation", 2)
	header.add_child(titles)

	var title := Label.new()
	title.text = "CARNET DE CAMPAGNE"
	_label_style(title, 26, _INK, 6)
	titles.add_child(title)

	var subtitle := Label.new()
	subtitle.text = "Ordres du commandement allié - opération en Normandie"
	_label_style(subtitle, 13, _INK_SOFT, 1)
	titles.add_child(subtitle)

	_summary = Label.new()
	_summary.text = ""
	_label_style(_summary, 15, _STAMP, 3)
	_summary.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	header.add_child(_summary)

	var close_button := Button.new()
	close_button.text = "FERMER (J)"
	close_button.focus_mode = Control.FOCUS_NONE
	_button_style(close_button)
	close_button.pressed.connect(_on_close_pressed)
	header.add_child(close_button)
	return header


func _paper_box() -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = _PAPER
	box.border_color = Color(_INK.r, _INK.g, _INK.b, 0.85)
	box.set_border_width_all(3)
	box.set_corner_radius_all(0)
	box.shadow_color = Color(0.0, 0.0, 0.0, 0.5)
	box.shadow_size = 10
	return box


func _button_style(button: Button) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.24, 0.23, 0.17, 0.95)
	normal.border_color = Color(_INK.r, _INK.g, _INK.b, 0.8)
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(0)
	normal.content_margin_left = 14.0
	normal.content_margin_right = 14.0
	normal.content_margin_top = 7.0
	normal.content_margin_bottom = 7.0
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.36, 0.34, 0.24, 0.98)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.9)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("focus", normal)
	button.add_theme_color_override("font_color", Color(0.86, 0.83, 0.71))
	button.add_theme_color_override("font_hover_color", Color(0.95, 0.93, 0.84))
	button.add_theme_font_size_override("font_size", 14)
	var font := _spaced_font(3)
	if font != null:
		button.add_theme_font_override("font", font)


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
# Journal content
# =============================================================================

func _rebuild() -> void:
	for child in _list.get_children():
		_list.remove_child(child)
		child.queue_free()
	_rows.clear()
	if _tracker == null:
		_empty_label.visible = true
		_summary.text = ""
		return

	var objectives: Array = _tracker.all_objectives()
	_empty_label.visible = objectives.is_empty()
	var done := 0
	for entry in objectives:
		var obj := entry as MissionDefs.Objective
		if obj != null and _tracker.is_done(obj.id):
			done += 1
	_summary.text = "%d / %d ACCOMPLIS" % [done, objectives.size()]

	# Group by sector, keeping the order the campaign hands them out.
	var order: Array[int] = []
	var groups: Dictionary = {}
	for entry in objectives:
		var obj := entry as MissionDefs.Objective
		if obj == null:
			continue
		if not groups.has(obj.sector_id):
			groups[obj.sector_id] = []
			order.append(obj.sector_id)
		var bucket: Array = groups[obj.sector_id]
		bucket.append(obj)

	var active_ids := _active_ids()
	for sector_id in order:
		_list.add_child(_build_sector_header(sector_id))
		var bucket: Array = groups[sector_id]
		for entry in bucket:
			var obj := entry as MissionDefs.Objective
			if obj == null:
				continue
			_list.add_child(_build_row(obj, _state_of(obj, active_ids)))
	_refresh_distances()


func _build_sector_header(sector_id: int) -> Control:
	var box := HBoxContainer.new()
	box.add_theme_constant_override("separation", 10)

	var label := Label.new()
	label.text = _sector_name(sector_id).to_upper()
	_label_style(label, 17, _INK, 5)
	box.add_child(label)

	var status := Label.new()
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	if War.is_sector_captured(sector_id):
		status.text = "- SECTEUR LIBÉRÉ"
		_label_style(status, 13, _DONE_GREEN, 2)
	else:
		status.text = "- SOUS CONTRÔLE ALLEMAND"
		_label_style(status, 13, _STAMP, 2)
	box.add_child(status)
	return box


func _build_row(obj: MissionDefs.Objective, state: int) -> Control:
	var row := Button.new()
	row.focus_mode = Control.FOCUS_NONE
	row.custom_minimum_size = Vector2(0.0, 104.0)
	row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_row_style(row, state, obj.id == _selected_id)
	row.pressed.connect(_on_row_pressed.bind(obj.id))

	var column := VBoxContainer.new()
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	column.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	column.offset_left = 16.0
	column.offset_right = -16.0
	column.offset_top = 9.0
	column.offset_bottom = -9.0
	column.add_theme_constant_override("separation", 2)
	row.add_child(column)

	var top := HBoxContainer.new()
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	top.add_theme_constant_override("separation", 10)
	column.add_child(top)

	var state_label := Label.new()
	state_label.text = "[%s]" % _STATE_LABELS[state]
	_label_style(state_label, 12, _state_color(state), 2)
	top.add_child(state_label)

	var title := Label.new()
	title.text = "%s  %s" % [MissionDefs.kind_icon(obj.kind), obj.title.to_upper()]
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_label_style(title, 17, (_INK if state != _S_DONE else _INK_SOFT), 3)
	top.add_child(title)

	var distance := Label.new()
	distance.text = ""
	distance.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_label_style(distance, 13, _INK_SOFT, 1)
	top.add_child(distance)

	var kind_line := Label.new()
	kind_line.text = "%s - %s" % [MissionDefs.kind_name(obj.kind), _progress_text(obj)]
	_label_style(kind_line, 12, _INK_SOFT, 1)
	column.add_child(kind_line)

	var description := Label.new()
	description.text = obj.description
	description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_label_style(description, 13, _INK_SOFT, 0)
	column.add_child(description)

	if not obj.reward_text.strip_edges().is_empty():
		var reward := Label.new()
		reward.text = "Récompense : %s" % obj.reward_text
		_label_style(reward, 12, _DONE_GREEN, 0)
		column.add_child(reward)

	_rows.append({"id": obj.id, "distance": distance, "button": row})
	return row


func _row_style(row: Button, state: int, selected: bool) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.72, 0.68, 0.55, 0.85)
	if state == _S_DONE:
		normal.bg_color = Color(0.68, 0.66, 0.55, 0.55)
	elif state == _S_FAILED:
		normal.bg_color = Color(0.56, 0.44, 0.40, 0.65)
	normal.border_color = Color(_INK.r, _INK.g, _INK.b, 0.55)
	normal.set_border_width_all(1)
	normal.border_width_left = 5 if state == _S_ACTIVE else 1
	if state == _S_ACTIVE:
		normal.border_color = _STAMP
	if selected:
		normal.border_color = Color(0.12, 0.20, 0.38)
		normal.set_border_width_all(2)
		normal.border_width_left = 5
	normal.set_corner_radius_all(0)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = normal.bg_color.lightened(0.10)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = normal.bg_color.darkened(0.10)
	row.add_theme_stylebox_override("normal", normal)
	row.add_theme_stylebox_override("hover", hover)
	row.add_theme_stylebox_override("pressed", pressed)
	row.add_theme_stylebox_override("focus", normal)


func _refresh_distances() -> void:
	var agent := _player_node()
	for row in _rows:
		var label := row["distance"] as Label
		if label == null or not is_instance_valid(label):
			continue
		var obj := _objective_by_id(int(row["id"]))
		if obj == null or agent == null:
			label.text = ""
			continue
		var origin := agent.global_position
		var to := Vector2(obj.position.x - origin.x, obj.position.z - origin.z)
		label.text = "%d m" % int(round(to.length()))


# =============================================================================
# Signal handlers
# =============================================================================

func _on_row_pressed(objective_id: int) -> void:
	_selected_id = objective_id
	_play("ui_click")
	objective_selected.emit(objective_id)
	_rebuild()


func _on_close_pressed() -> void:
	close()


func _on_journal_dirty(_obj: MissionDefs.Objective) -> void:
	if _open:
		_rebuild()


func _on_progress_dirty(_obj: MissionDefs.Objective, _current: int, _total: int) -> void:
	if _open:
		_rebuild()


func _on_objective_failed(obj: MissionDefs.Objective) -> void:
	if obj != null:
		_failed[obj.id] = true
	if _open:
		_rebuild()


func _on_campaign_completed() -> void:
	if _open:
		_rebuild()


# =============================================================================
# Painting: the backdrop behind the sheet
# =============================================================================

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), _BACKDROP, true)
	# Faint ruled lines, like a real field notebook seen through the sheet.
	var line := Color(_PAPER_LINE.r, _PAPER_LINE.g, _PAPER_LINE.b, 0.05)
	var y := 40.0
	while y < size.y:
		draw_line(Vector2(0.0, y), Vector2(size.x, y), line, 1.0)
		y += 26.0


# =============================================================================
# Helpers
# =============================================================================

func _active_ids() -> Dictionary:
	var ids: Dictionary = {}
	if _tracker == null:
		return ids
	for entry in _tracker.active():
		var obj := entry as MissionDefs.Objective
		if obj != null:
			ids[obj.id] = true
	return ids


func _state_of(obj: MissionDefs.Objective, active_ids: Dictionary) -> int:
	if _tracker != null and _tracker.is_done(obj.id):
		return _S_DONE
	if _failed.has(obj.id):
		return _S_FAILED
	if active_ids.has(obj.id):
		return _S_ACTIVE
	return _S_TODO


func _state_color(state: int) -> Color:
	if state == _S_DONE:
		return _DONE_GREEN
	if state == _S_FAILED:
		return _STAMP
	if state == _S_ACTIVE:
		return _STAMP
	return _TODO_GREY


func _progress_text(obj: MissionDefs.Objective) -> String:
	if _tracker == null:
		return "avancement inconnu"
	var progress := _tracker.progress_of(obj.id)
	if progress.y <= 0.0:
		return "secteur %s" % _sector_name(obj.sector_id)
	return "avancement %d / %d" % [int(progress.x), int(progress.y)]


func _objective_by_id(objective_id: int) -> MissionDefs.Objective:
	if _tracker == null:
		return null
	for entry in _tracker.all_objectives():
		var obj := entry as MissionDefs.Objective
		if obj != null and obj.id == objective_id:
			return obj
	return null


func _sector_name(sector_id: int) -> String:
	var layout := _find_layout()
	if layout != null:
		var site: Layout.Site = layout.site_by_id(sector_id)
		if site != null:
			return site.display_name
	return "Secteur %d" % sector_id


## The journal only gets the tracker in `setup()`, so the world is looked up
## once through the scene tree and cached.
func _find_layout() -> Layout:
	if _layout != null:
		return _layout
	var tree := get_tree()
	if tree == null:
		return null
	var world := _search_world(tree.root, 0)
	if world == null:
		return null
	_layout = world.layout()
	return _layout


func _search_world(node: Node, depth: int) -> GameWorld:
	if depth > 6:
		return null
	for child in node.get_children():
		var world := child as GameWorld
		if world != null:
			return world
		var found := _search_world(child, depth + 1)
		if found != null:
			return found
	return null


## The journal only receives the tracker, so the player is looked up by group.
func _player_node() -> Player:
	if _player != null and is_instance_valid(_player):
		return _player
	var tree := get_tree()
	if tree == null:
		return null
	_player = tree.get_first_node_in_group("player") as Player
	return _player


func _connect(source: Object, signal_name: String, target: Callable) -> void:
	if source == null or not is_instance_valid(source):
		return
	if not source.has_signal(signal_name):
		push_warning("ObjectivesUi: missing signal %s" % signal_name)
		return
	if source.is_connected(signal_name, target):
		return
	source.connect(signal_name, target)


func _play(sample: String) -> void:
	if Sfx == null or not Sfx.has_sample(sample):
		return
	Sfx.play(sample, -6.0, 1.0)
