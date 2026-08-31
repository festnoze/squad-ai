class_name Hud
extends CanvasLayer
## In-game overlay: crosshair, battery counter, interaction prompt, held photo
## panel, level banner and the black fade used between levels. Built entirely
## in code; main drives it every frame.

var _battery_label: Label
var _prompt_label: Label
var _held_panel: PanelContainer
var _held_title: Label
var _banner: VBoxContainer
var _banner_title: Label
var _banner_subtitle: Label
var _fade: ColorRect
var _banner_timer := 0.0


func _ready() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	var crosshair := ColorRect.new()
	crosshair.color = Color(1, 1, 1, 0.85)
	crosshair.size = Vector2(5, 5)
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.position = Vector2(-2.5, -2.5)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(crosshair)

	_battery_label = Label.new()
	_battery_label.add_theme_font_size_override("font_size", 22)
	_battery_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_battery_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	_battery_label.add_theme_constant_override("outline_size", 6)
	_battery_label.position = Vector2(24, 20)
	root.add_child(_battery_label)

	_prompt_label = Label.new()
	_prompt_label.add_theme_font_size_override("font_size", 22)
	_prompt_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_prompt_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	_prompt_label.add_theme_constant_override("outline_size", 6)
	_prompt_label.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_prompt_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_prompt_label.position.y = -120
	_prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	root.add_child(_prompt_label)

	_held_panel = PanelContainer.new()
	_held_panel.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_held_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	_held_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_held_panel.position = Vector2(-24, -24)
	var held_box := VBoxContainer.new()
	_held_title = Label.new()
	_held_title.add_theme_font_size_override("font_size", 22)
	held_box.add_child(_held_title)
	var held_hint := Label.new()
	held_hint.add_theme_font_size_override("font_size", 15)
	held_hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.75))
	held_hint.text = "Clic gauche : poser   Molette : pivoter   Clic droit : reposer"
	held_box.add_child(held_hint)
	_held_panel.add_child(held_box)
	_held_panel.visible = false
	root.add_child(_held_panel)

	_banner = VBoxContainer.new()
	_banner.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_banner.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_banner.position.y = 70
	_banner_title = Label.new()
	_banner_title.add_theme_font_size_override("font_size", 44)
	_banner_title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	_banner_title.add_theme_constant_override("outline_size", 8)
	_banner_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner.add_child(_banner_title)
	_banner_subtitle = Label.new()
	_banner_subtitle.add_theme_font_size_override("font_size", 20)
	_banner_subtitle.add_theme_color_override("font_color", Color(1, 1, 1, 0.85))
	_banner_subtitle.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.5))
	_banner_subtitle.add_theme_constant_override("outline_size", 6)
	_banner_subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner.add_child(_banner_subtitle)
	_banner.modulate.a = 0.0
	root.add_child(_banner)

	_fade = ColorRect.new()
	_fade.color = Color(0.05, 0.05, 0.08, 1)
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fade.modulate.a = 0.0
	root.add_child(_fade)

	Game.batteries_changed.connect(_on_batteries_changed)
	_on_batteries_changed(0, 0, 0)


func _process(delta: float) -> void:
	if _banner_timer > 0.0:
		_banner_timer -= delta
		_banner.modulate.a = clampf(minf(_banner_timer, 4.5 - _banner_timer) * 1.5, 0.0, 1.0)
	else:
		_banner.modulate.a = 0.0


func set_prompt(text: String) -> void:
	_prompt_label.text = text


func set_held(title: String) -> void:
	_held_panel.visible = title != ""
	_held_title.text = ("Photo : « %s »" % title) if title != "" else ""


func show_banner(title: String, subtitle: String) -> void:
	_banner_title.text = title
	_banner_subtitle.text = subtitle
	_banner_timer = 4.5


func fade_out() -> void:
	var tween := create_tween()
	tween.tween_property(_fade, "modulate:a", 1.0, 0.6)
	await tween.finished


func fade_in() -> void:
	var tween := create_tween()
	tween.tween_property(_fade, "modulate:a", 0.0, 0.6)


func _on_batteries_changed(carried: int, inserted: int, required: int) -> void:
	_battery_label.text = "Piles : %d portee%s   |   Teleporteur : %d / %d" % [
		carried, "s" if carried > 1 else "", inserted, required
	]
