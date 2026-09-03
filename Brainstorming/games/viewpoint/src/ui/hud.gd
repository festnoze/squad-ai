class_name Hud
extends CanvasLayer
## In-game overlay: crosshair, battery counter, interaction prompt, held photo
## panel, level banner and the black fade used between levels. Built entirely
## in code; main drives it every frame.

var _battery_label: Label
var _films_label: Label
var _prompt_label: Label
var _toast_label: Label
var _toast_timer := 0.0
var _photo_view: TextureRect
var _viewfinder: Control
var _rewind_tint: ColorRect
var _rewind_label: Label
var _held_panel: PanelContainer
var _held_thumb: PhotoCard
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

	_films_label = Label.new()
	_films_label.add_theme_font_size_override("font_size", 20)
	_films_label.add_theme_color_override("font_color", Color(0.75, 0.95, 0.93))
	_films_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	_films_label.add_theme_constant_override("outline_size", 6)
	_films_label.position = Vector2(24, 52)
	_films_label.visible = false
	root.add_child(_films_label)

	# The raised photo: the picture drawn over the exact screen region the
	# placement frustum covers (photo fov 50 inside the camera fov 75),
	# rotated with the mouse wheel. There is no 3D preview: the picture is
	# all the player sees before placing.
	_photo_view = TextureRect.new()
	_photo_view.stretch_mode = TextureRect.STRETCH_SCALE
	_photo_view.set_anchors_preset(Control.PRESET_CENTER)
	_photo_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_photo_view.visible = false
	root.add_child(_photo_view)

	# The viewfinder: the square the camera would actually capture, dimmed
	# outside, so the player frames the shot before pressing the shutter.
	_viewfinder = Control.new()
	_viewfinder.set_anchors_preset(Control.PRESET_FULL_RECT)
	_viewfinder.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_viewfinder.visible = false
	_viewfinder.draw.connect(_draw_viewfinder)
	root.add_child(_viewfinder)

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
	_held_thumb = PhotoCard.new()
	_held_thumb.custom_minimum_size = Vector2(86, 78)
	_held_thumb.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	_held_thumb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	held_box.add_child(_held_thumb)
	_held_title = Label.new()
	_held_title.add_theme_font_size_override("font_size", 22)
	held_box.add_child(_held_title)
	var held_hint := Label.new()
	held_hint.add_theme_font_size_override("font_size", 15)
	held_hint.add_theme_color_override("font_color", Color(1, 1, 1, 0.75))
	held_hint.text = "Clic gauche : poser   Clic droit : lever   Molette : pivoter   F : reposer"
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

	_rewind_tint = ColorRect.new()
	_rewind_tint.color = Color(0.35, 0.55, 0.85, 0.18)
	_rewind_tint.set_anchors_preset(Control.PRESET_FULL_RECT)
	_rewind_tint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rewind_tint.visible = false
	root.add_child(_rewind_tint)

	_rewind_label = Label.new()
	_rewind_label.add_theme_font_size_override("font_size", 30)
	_rewind_label.add_theme_color_override("font_color", Color(0.85, 0.94, 1.0))
	_rewind_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	_rewind_label.add_theme_constant_override("outline_size", 8)
	_rewind_label.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_rewind_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_rewind_label.position.y = 170
	_rewind_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_rewind_label.visible = false
	root.add_child(_rewind_label)

	_toast_label = Label.new()
	_toast_label.add_theme_font_size_override("font_size", 20)
	_toast_label.add_theme_color_override("font_color", Color(1, 0.85, 0.6))
	_toast_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	_toast_label.add_theme_constant_override("outline_size", 6)
	_toast_label.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_toast_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_toast_label.position.y = -160
	_toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_toast_label.visible = false
	root.add_child(_toast_label)

	Game.batteries_changed.connect(_on_batteries_changed)
	Game.films_changed.connect(_on_films_changed)
	_on_batteries_changed(0, 0, 0)


func _process(delta: float) -> void:
	if _banner_timer > 0.0:
		_banner_timer -= delta
		_banner.modulate.a = clampf(minf(_banner_timer, 4.5 - _banner_timer) * 1.5, 0.0, 1.0)
	else:
		_banner.modulate.a = 0.0
	if _toast_timer > 0.0:
		_toast_timer -= delta
		if _toast_timer <= 0.0:
			_toast_label.visible = false


## Shows (or hides, with null) the raised photo, sized so the picture covers
## exactly what the placement frustum covers on screen, and rotated by the
## held roll (90 degree steps) so what the player sees is what gets placed.
func set_photo_view(texture: Texture2D, roll_steps := 0) -> void:
	_photo_view.visible = texture != null
	if texture == null:
		return
	_photo_view.texture = texture
	var viewport_h := _photo_view.get_viewport_rect().size.y
	var side := viewport_h * tan(deg_to_rad(PhotoMath.PHOTO_FOV_DEG * 0.5)) / tan(deg_to_rad(37.5))
	# Anchors sit on the parent's center: offsets spread the square around it.
	_photo_view.offset_left = -side * 0.5
	_photo_view.offset_top = -side * 0.5
	_photo_view.offset_right = side * 0.5
	_photo_view.offset_bottom = side * 0.5
	# Pivot at the center, set AFTER the size, so the square spins in place.
	_photo_view.pivot_offset = Vector2(side, side) * 0.5
	_photo_view.rotation = roll_steps * PI / 2


## The rewind banner and its blue wash, shown while R is held.
func set_rewinding(active: bool, seconds_left: float) -> void:
	_rewind_tint.visible = active
	_rewind_label.visible = active
	if active:
		_rewind_label.text = "REMBOBINAGE   %.1f s d'historique" % seconds_left


func set_viewfinder(active: bool) -> void:
	if _viewfinder.visible == active:
		return
	_viewfinder.visible = active
	_viewfinder.queue_redraw()


## The capture frustum shares the placement fov, so the framed square is the
## very region PhotoCapture will keep.
func _draw_viewfinder() -> void:
	var rect := _viewfinder.get_rect()
	var side := rect.size.y * tan(deg_to_rad(PhotoMath.PHOTO_FOV_DEG * 0.5)) / tan(deg_to_rad(37.5))
	var frame := Rect2(rect.size * 0.5 - Vector2(side, side) * 0.5, Vector2(side, side))

	var dim := Color(0.05, 0.06, 0.10, 0.35)
	_viewfinder.draw_rect(Rect2(0, 0, rect.size.x, frame.position.y), dim)
	_viewfinder.draw_rect(Rect2(0, frame.end.y, rect.size.x, rect.size.y - frame.end.y), dim)
	_viewfinder.draw_rect(Rect2(0, frame.position.y, frame.position.x, frame.size.y), dim)
	_viewfinder.draw_rect(Rect2(frame.end.x, frame.position.y, rect.size.x - frame.end.x, frame.size.y), dim)

	var edge := Color(1, 1, 1, 0.5)
	_viewfinder.draw_rect(frame, edge, false, 2.0)
	# Corner brackets, the camera look.
	var arm := side * 0.16
	var bracket := Color(1, 1, 1, 0.95)
	for corner: Vector2 in [Vector2(0, 0), Vector2(1, 0), Vector2(0, 1), Vector2(1, 1)]:
		var origin: Vector2 = frame.position + frame.size * corner
		var dir := Vector2(1.0 - corner.x * 2.0, 1.0 - corner.y * 2.0)
		# Dark stroke under the white one: the brackets have to read against a
		# bright sky as well as against the ground.
		_viewfinder.draw_line(origin, origin + Vector2(arm * dir.x, 0), Color(0.05, 0.06, 0.10, 0.7), 7.0)
		_viewfinder.draw_line(origin, origin + Vector2(0, arm * dir.y), Color(0.05, 0.06, 0.10, 0.7), 7.0)
		_viewfinder.draw_line(origin, origin + Vector2(arm * dir.x, 0), bracket, 3.0)
		_viewfinder.draw_line(origin, origin + Vector2(0, arm * dir.y), bracket, 3.0)


func show_toast(text: String) -> void:
	_toast_label.text = text
	_toast_label.visible = true
	_toast_timer = 2.2


func set_prompt(text: String) -> void:
	_prompt_label.text = text


## The little tilted card of the held photo. It steps aside while the photo is
## raised: the full picture in front of the player replaces it.
func set_held(title: String, texture: Texture2D = null, raised := false) -> void:
	_held_panel.visible = title != ""
	_held_title.text = ("Photo : « %s »" % title) if title != "" else ""
	_held_thumb.texture = texture
	_held_thumb.visible = texture != null and not raised


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


func _on_films_changed(films: int) -> void:
	_films_label.visible = films > 0
	_films_label.text = "Pellicule : %d   (clic droit : viser   clic gauche : declencher)" % films


func _on_batteries_changed(carried: int, inserted: int, required: int) -> void:
	_battery_label.text = "Piles : %d portee%s   |   Teleporteur : %d / %d" % [
		carried, "s" if carried > 1 else "", inserted, required
	]
