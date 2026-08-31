class_name Menu
extends CanvasLayer
## Title, pause and victory screens. Emits intents; main decides what happens.

signal start_requested
signal resume_requested
signal restart_requested
signal level_selected(index: int)

enum Mode { HIDDEN, TITLE, PAUSED, VICTORY }

var mode: Mode = Mode.HIDDEN

var _root: Control
var _title: Label
var _subtitle: Label
var _hint: Label
var _levels_label: Label
var _level_buttons: Array[Button] = []


func _ready() -> void:
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_root)

	var dim := ColorRect.new()
	dim.color = Color(0.08, 0.10, 0.14, 0.82)
	dim.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.add_child(dim)

	var box := VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	_root.add_child(box)

	_title = Label.new()
	_title.add_theme_font_size_override("font_size", 72)
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_title)

	_subtitle = Label.new()
	_subtitle.add_theme_font_size_override("font_size", 22)
	_subtitle.add_theme_color_override("font_color", Color(1, 1, 1, 0.85))
	_subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_subtitle)

	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, 30)
	box.add_child(spacer)

	_hint = Label.new()
	_hint.add_theme_font_size_override("font_size", 24)
	_hint.add_theme_color_override("font_color", Color(1, 0.82, 0.5))
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_hint)

	var grid_spacer := Control.new()
	grid_spacer.custom_minimum_size = Vector2(0, 26)
	box.add_child(grid_spacer)

	_levels_label = Label.new()
	_levels_label.add_theme_font_size_override("font_size", 18)
	_levels_label.add_theme_color_override("font_color", Color(1, 1, 1, 0.7))
	_levels_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_levels_label)

	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 8)
	grid.add_theme_constant_override("v_separation", 8)
	grid.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	box.add_child(grid)
	for i in LevelDefs.count():
		var button := Button.new()
		button.custom_minimum_size = Vector2(180, 36)
		button.add_theme_font_size_override("font_size", 14)
		button.focus_mode = Control.FOCUS_NONE
		var index := i
		button.pressed.connect(func() -> void: level_selected.emit(index))
		grid.add_child(button)
		_level_buttons.append(button)

	hide_menu()


## Reflects the persisted progression: reached levels are playable, the rest
## are visible but locked, so the player sees how far the road goes.
func _refresh_levels() -> void:
	for i in _level_buttons.size():
		var button := _level_buttons[i]
		var unlocked: bool = Game.is_level_unlocked(i)
		button.disabled = not unlocked
		var def := LevelDefs.get_def(i)
		if unlocked:
			button.text = "%d. %s" % [i + 1, def.get("name", "?")]
			button.tooltip_text = def.get("subtitle", "")
		else:
			button.text = "%d. Verrouille" % (i + 1)
			button.tooltip_text = "Atteignez ce niveau pour le debloquer."
	var reached: int = clampi(Game.furthest_level + 1, 1, LevelDefs.count())
	_levels_label.text = "Choisir un niveau (%d / %d atteints)" % [reached, LevelDefs.count()]


func show_title() -> void:
	mode = Mode.TITLE
	_root.visible = true
	_refresh_levels()
	_title.text = "VIEWPOINT"
	_subtitle.text = "Posez des photos. Elles deviennent le monde.\n\nZQSD/WASD bouger   Souris regarder   Espace sauter\nE interagir   Clic gauche poser la photo   Clic droit la reposer\nMolette pivoter la photo   R recommencer le niveau   F11 plein ecran"
	_hint.text = "Entree : commencer au niveau 1   ou cliquez un niveau ci-dessous"


func show_pause() -> void:
	mode = Mode.PAUSED
	_root.visible = true
	_refresh_levels()
	_title.text = "PAUSE"
	_subtitle.text = "Le monde attend votre prochaine photo."
	_hint.text = "Echap : reprendre    Entree : recommencer la partie"


func show_victory() -> void:
	mode = Mode.VICTORY
	_root.visible = true
	_refresh_levels()
	_title.text = "EXAMEN REUSSI"
	_subtitle.text = "Les quinze iles sont derriere vous.\nChaque photo posee est restee exactement la ou vous l'avez vue."
	_hint.text = "Entree : rejouer"


func hide_menu() -> void:
	mode = Mode.HIDDEN
	_root.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if mode == Mode.HIDDEN:
		return
	if event.is_action_pressed("ui_start"):
		match mode:
			Mode.TITLE:
				start_requested.emit()
			Mode.PAUSED:
				restart_requested.emit()
			Mode.VICTORY:
				restart_requested.emit()
	elif event.is_action_pressed("pause") and mode == Mode.PAUSED:
		resume_requested.emit()
