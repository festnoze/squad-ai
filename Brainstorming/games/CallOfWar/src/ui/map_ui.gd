## CALL OF WAR - full screen staff map (key M).
##
## Everything is painted in `_draw()`: there is no map texture in the project.
## The relief is the one exception, and only because sampling the heightfield
## costs real time: the 4096 m square is sampled ONCE on the first opening on a
## 128 x 128 grid, turned into contour bands plus a north west hill shade, and
## cached in an ImageTexture. Every later frame only re blits that texture, so
## panning and zooming never touch the heightfield again.
##
## Layout: this Control paints the paper background and the header, a clipped
## child paints the map itself (so a zoomed map cannot bleed over the frame),
## and a second child paints the legend and the campaign cartouche on top.
class_name MapUi
extends Control

signal closed()

# --- Paper palette -----------------------------------------------------------

const _BACKDROP := Color(0.07, 0.07, 0.06, 0.97)
const _PAPER := Color(0.80, 0.76, 0.62)
const _PAPER_DARK := Color(0.68, 0.64, 0.51)
const _INK := Color(0.10, 0.09, 0.08)
const _INK_SOFT := Color(0.10, 0.09, 0.08, 0.35)
const _STAMP := Color(0.66, 0.14, 0.11)
const _AXIS_RED := Color(0.62, 0.15, 0.12)
const _ALLIED_BLUE := Color(0.20, 0.34, 0.56)
const _WATER := Color(0.30, 0.42, 0.50)
const _ROAD := Color(0.34, 0.26, 0.16)

## World square, mirrors Heightfield.WORLD_SIZE.
const _WORLD := 4096.0
const _HALF := 2048.0
## Relief sampling resolution. 128 x 128 = 16384 height queries, done once.
const _RELIEF_RES := 128
## Metres between two contour bands.
const _BAND := 6.0
## Metres between two grid lines.
const _GRID := 256.0

const _ZOOM_MIN := 0.85
const _ZOOM_MAX := 9.0

const _SITE_LABELS: PackedStringArray = [
	"Village", "Ferme", "Bourg et église", "Aérodrome", "Bunker",
	"Camp de prisonniers", "Carrefour", "Pont", "Ruines",
]


## A bare Control forwarding `_draw` to a callable, so the map can own several
## stacked painting layers without extra script files.
class _Painter:
	extends Control

	var painter: Callable = Callable()

	func _draw() -> void:
		if painter.is_valid():
			painter.call(self)


var _world: GameWorld = null
var _player: Player = null
var _tracker: ObjectiveTracker = null

var _map_view: _Painter = null
var _chrome: _Painter = null
var _close_button: Button = null

var _relief: ImageTexture = null
var _relief_min: float = 0.0
var _relief_max: float = 1.0

var _open: bool = false
var _zoom: float = 1.0
## Centre of the view, in world (x, z) metres.
var _view_center: Vector2 = Vector2.ZERO
var _dragging: bool = false

static var _font_cache: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	close()


func _process(_delta: float) -> void:
	if not _open:
		return
	_map_view.queue_redraw()
	_chrome.queue_redraw()


# =============================================================================
# Public API (contract 2.35)
# =============================================================================

func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void:
	_world = game_world
	_player = player_node
	_tracker = tracker
	_relief = null


func open() -> void:
	if _open:
		return
	_open = true
	visible = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(true)
	_build_relief()
	_center_on_player()
	queue_redraw()
	_map_view.queue_redraw()
	_chrome.queue_redraw()
	_play("ui_open")


func close() -> void:
	var was_open := _open
	_open = false
	visible = false
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_dragging = false
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
	_map_view = _Painter.new()
	_map_view.name = "MapView"
	_map_view.painter = Callable(self, "_draw_map")
	_map_view.clip_contents = true
	_map_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_map_view.set_anchors_preset(Control.PRESET_FULL_RECT)
	_map_view.offset_left = 52.0
	_map_view.offset_top = 86.0
	_map_view.offset_right = -52.0
	_map_view.offset_bottom = -56.0
	add_child(_map_view)

	_chrome = _Painter.new()
	_chrome.name = "Chrome"
	_chrome.painter = Callable(self, "_draw_chrome")
	_chrome.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_chrome.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_chrome)

	_close_button = Button.new()
	_close_button.name = "Close"
	_close_button.text = "FERMER (M)"
	_close_button.focus_mode = Control.FOCUS_NONE
	_close_button.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_close_button.offset_left = -186.0
	_close_button.offset_top = 26.0
	_close_button.offset_right = -52.0
	_close_button.offset_bottom = 62.0
	_style_button(_close_button)
	_close_button.pressed.connect(_on_close_pressed)
	add_child(_close_button)


func _style_button(button: Button) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color(0.24, 0.23, 0.17, 0.95)
	normal.border_color = Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.55)
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(0)
	normal.content_margin_left = 12.0
	normal.content_margin_right = 12.0
	normal.content_margin_top = 6.0
	normal.content_margin_bottom = 6.0
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.36, 0.34, 0.24, 0.98)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.85)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("focus", normal)
	button.add_theme_stylebox_override("disabled", normal)
	button.add_theme_color_override("font_color", _PAPER)
	button.add_theme_color_override("font_hover_color", Color(0.94, 0.91, 0.80))
	button.add_theme_color_override("font_pressed_color", Color(0.96, 0.94, 0.88))
	button.add_theme_font_size_override("font_size", 14)
	var font := _spaced_font(3)
	if font != null:
		button.add_theme_font_override("font", font)


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
# Relief cache
# =============================================================================

## Samples the heightfield once and bakes contour bands plus a hill shade into
## an ImageTexture. Called on the first `open()` and never again.
func _build_relief() -> void:
	if _relief != null:
		return
	if _world == null:
		return
	var hf: Heightfield = _world.heightfield()
	if hf == null:
		return
	var heights := PackedFloat32Array()
	heights.resize(_RELIEF_RES * _RELIEF_RES)
	var step := _WORLD / float(_RELIEF_RES)
	_relief_min = 1.0e20
	_relief_max = -1.0e20
	for j in _RELIEF_RES:
		var wz := -_HALF + (float(j) + 0.5) * step
		for i in _RELIEF_RES:
			var wx := -_HALF + (float(i) + 0.5) * step
			var h := hf.height_at(wx, wz)
			heights[j * _RELIEF_RES + i] = h
			_relief_min = minf(_relief_min, h)
			_relief_max = maxf(_relief_max, h)
	if _relief_max - _relief_min < 0.001:
		_relief_max = _relief_min + 1.0

	var image := Image.create_empty(_RELIEF_RES, _RELIEF_RES, false, Image.FORMAT_RGB8)
	for j in _RELIEF_RES:
		for i in _RELIEF_RES:
			image.set_pixel(i, j, _relief_pixel(heights, i, j))
	_relief = ImageTexture.create_from_image(image)


func _relief_pixel(heights: PackedFloat32Array, i: int, j: int) -> Color:
	var h := heights[j * _RELIEF_RES + i]
	if h <= Heightfield.WATER_LEVEL:
		var depth := clampf((Heightfield.WATER_LEVEL - h) / 8.0, 0.0, 1.0)
		return _WATER.lerp(Color(0.16, 0.24, 0.31), depth)
	# Contour banding: every _BAND metres the paper gets one shade darker.
	var band := floori((h - Heightfield.WATER_LEVEL) / _BAND)
	var tone := _PAPER.lerp(Color(0.44, 0.40, 0.27), clampf(float(band) * 0.085, 0.0, 0.85))
	# North west hill shade from finite differences of the sampled grid.
	var left := heights[j * _RELIEF_RES + maxi(0, i - 1)]
	var right := heights[j * _RELIEF_RES + mini(_RELIEF_RES - 1, i + 1)]
	var up := heights[maxi(0, j - 1) * _RELIEF_RES + i]
	var down := heights[mini(_RELIEF_RES - 1, j + 1) * _RELIEF_RES + i]
	var slope := (right - left) + (down - up)
	var shade := clampf(0.5 - slope * 0.045, 0.0, 1.0)
	tone = tone.lerp(Color(0.20, 0.18, 0.13), (1.0 - shade) * 0.55)
	tone = tone.lerp(Color(0.92, 0.89, 0.78), maxf(0.0, shade - 0.5) * 0.45)
	return tone


# =============================================================================
# View transform
# =============================================================================

func _pixels_per_metre() -> float:
	var view := _map_view.size
	return minf(view.x, view.y) / _WORLD * _zoom


func _world_to_view(p: Vector2) -> Vector2:
	return (p - _view_center) * _pixels_per_metre() + _map_view.size * 0.5


func _view_to_world(p: Vector2) -> Vector2:
	var ppm := _pixels_per_metre()
	if ppm <= 0.0001:
		return _view_center
	return (p - _map_view.size * 0.5) / ppm + _view_center


func _center_on_player() -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var pos := _player.global_position
	_view_center = Vector2(pos.x, pos.z)
	_clamp_view()


func _clamp_view() -> void:
	_view_center.x = clampf(_view_center.x, -_HALF, _HALF)
	_view_center.y = clampf(_view_center.y, -_HALF, _HALF)


# =============================================================================
# Input
# =============================================================================

func _gui_input(event: InputEvent) -> void:
	if not _open:
		return
	var button := event as InputEventMouseButton
	if button != null:
		_handle_button(button)
		return
	var motion := event as InputEventMouseMotion
	if motion != null and _dragging:
		_view_center -= motion.relative / maxf(0.0001, _pixels_per_metre())
		_clamp_view()
		accept_event()


func _handle_button(button: InputEventMouseButton) -> void:
	if button.button_index == MOUSE_BUTTON_WHEEL_UP and button.pressed:
		_zoom_at(button.position, 1.18)
		accept_event()
	elif button.button_index == MOUSE_BUTTON_WHEEL_DOWN and button.pressed:
		_zoom_at(button.position, 1.0 / 1.18)
		accept_event()
	elif button.button_index == MOUSE_BUTTON_LEFT:
		_dragging = button.pressed
		accept_event()


## Zooms while keeping the world point under the cursor pinned to the cursor.
func _zoom_at(screen_position: Vector2, factor: float) -> void:
	var local := screen_position - _map_view.position
	var before := _view_to_world(local)
	_zoom = clampf(_zoom * factor, _ZOOM_MIN, _ZOOM_MAX)
	var after := _view_to_world(local)
	_view_center += before - after
	_clamp_view()


func _on_close_pressed() -> void:
	close()


# =============================================================================
# Painting: background and frame
# =============================================================================

func _draw() -> void:
	var rect := Rect2(Vector2.ZERO, size)
	draw_rect(rect, _BACKDROP, true)
	var font := ThemeDB.fallback_font
	if font == null:
		return
	draw_string(font, Vector2(52.0, 46.0), "CARTE D'ÉTAT-MAJOR",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 26, _PAPER)
	draw_string(font, Vector2(52.0, 70.0),
			"POCHE DE NORMANDIE - JUIN 1942 - ÉCHELLE 1:25 000",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 13, _PAPER_DARK)
	# Frame around the map view.
	var frame := Rect2(_map_view.position - Vector2.ONE * 2.0, _map_view.size + Vector2.ONE * 4.0)
	draw_rect(frame, Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.55), false, 2.0)
	draw_string(font, Vector2(52.0, size.y - 26.0),
			"MOLETTE : ZOOM     CLIC MAINTENU : DÉPLACER",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.6))


# =============================================================================
# Painting: the map itself (clipped child)
# =============================================================================

func _draw_map(c: Control) -> void:
	var full := Rect2(Vector2.ZERO, c.size)
	c.draw_rect(full, Color(0.13, 0.14, 0.13), true)
	if _relief != null:
		var origin := _world_to_view(Vector2(-_HALF, -_HALF))
		var span := _WORLD * _pixels_per_metre()
		c.draw_texture_rect(_relief, Rect2(origin, Vector2(span, span)), false, Color.WHITE)
	_draw_grid(c)
	_draw_water(c)
	_draw_roads(c)
	_draw_sites(c)
	_draw_objectives(c)
	_draw_player(c)


func _draw_grid(c: Control) -> void:
	var font := ThemeDB.fallback_font
	var color := Color(_INK.r, _INK.g, _INK.b, 0.20)
	var count := int(_WORLD / _GRID)
	for i in range(count + 1):
		var w := -_HALF + float(i) * _GRID
		var vertical_top := _world_to_view(Vector2(w, -_HALF))
		var vertical_bottom := _world_to_view(Vector2(w, _HALF))
		c.draw_line(vertical_top, vertical_bottom, color, 1.0, false)
		var horizontal_left := _world_to_view(Vector2(-_HALF, w))
		var horizontal_right := _world_to_view(Vector2(_HALF, w))
		c.draw_line(horizontal_left, horizontal_right, color, 1.0, false)
		if font == null or i >= count:
			continue
		var label_pos := _world_to_view(Vector2(w + 6.0, -_HALF + 6.0))
		label_pos.y = clampf(label_pos.y, 14.0, c.size.y - 4.0)
		label_pos.x = clampf(label_pos.x, 2.0, c.size.x - 20.0)
		c.draw_string(font, label_pos, "%s%d" % [char(65 + i), i + 1],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, Color(_INK.r, _INK.g, _INK.b, 0.45))


func _draw_water(c: Control) -> void:
	var layout := _layout()
	if layout == null:
		return
	var width := maxf(1.6, 3.0 * sqrt(_zoom))
	for river in layout.rivers:
		if river.size() < 2:
			continue
		var points := PackedVector2Array()
		for p in river:
			points.append(_world_to_view(p))
		c.draw_polyline(points, Color(_WATER.r, _WATER.g, _WATER.b, 0.95), width, true)


func _draw_roads(c: Control) -> void:
	var layout := _layout()
	if layout == null:
		return
	var width := maxf(1.4, 2.6 * sqrt(_zoom))
	for road in layout.roads:
		if road.size() < 2:
			continue
		var points := PackedVector2Array()
		for p in road:
			points.append(_world_to_view(p))
		c.draw_polyline(points, Color(0.22, 0.18, 0.12, 0.9), width + 1.6, true)
		c.draw_polyline(points, Color(_ROAD.r, _ROAD.g, _ROAD.b, 0.95), width, true)


func _draw_sites(c: Control) -> void:
	var layout := _layout()
	if layout == null:
		return
	var font := ThemeDB.fallback_font
	for site in layout.sites:
		var at := _world_to_view(site.center)
		if at.x < -80.0 or at.y < -80.0 or at.x > c.size.x + 80.0 or at.y > c.size.y + 80.0:
			continue
		var color := _INK
		if site.is_sector:
			color = _ALLIED_BLUE if War.is_sector_captured(site.id) else _AXIS_RED
		var radius := 8.0 if site.is_sector else 6.0
		if site.is_sector:
			# Hold circle, drawn at the real footprint radius when zoomed in.
			var footprint := maxf(radius + 4.0, site.radius * _pixels_per_metre())
			c.draw_arc(at, footprint, 0.0, TAU, 48, Color(color.r, color.g, color.b, 0.55), 1.6, true)
		_draw_site_icon(c, site.kind, at, radius, color)
		if font == null:
			continue
		var label := site.display_name.to_upper()
		var text_size := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		var text_at := at + Vector2(-text_size.x * 0.5, radius + 15.0)
		c.draw_string(font, text_at + Vector2.ONE, label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.95, 0.93, 0.85, 0.55))
		c.draw_string(font, text_at, label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, _INK)
		if site.garrison > 0 and _zoom > 1.6:
			c.draw_string(font, text_at + Vector2(0.0, 13.0), "garnison %d" % site.garrison,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color(_INK.r, _INK.g, _INK.b, 0.65))


## One ink glyph per site kind, all built from primitives.
func _draw_site_icon(c: Control, kind: int, at: Vector2, r: float, color: Color) -> void:
	var thin := 1.8
	if kind == Layout.SITE_VILLAGE:
		c.draw_rect(Rect2(at - Vector2(r, r), Vector2(r * 2.0, r * 2.0)), color, false, thin)
		c.draw_rect(Rect2(at - Vector2(r * 0.35, r * 0.35), Vector2(r * 0.7, r * 0.7)), color, true)
	elif kind == Layout.SITE_FARM:
		c.draw_rect(Rect2(at - Vector2(r, 0.0), Vector2(r * 2.0, r)), color, false, thin)
		c.draw_polyline(PackedVector2Array([
			at + Vector2(-r, 0.0), at + Vector2(0.0, -r), at + Vector2(r, 0.0)]),
			color, thin, true)
	elif kind == Layout.SITE_CHURCH_TOWN:
		c.draw_arc(at, r, 0.0, TAU, 24, color, thin, true)
		c.draw_line(at + Vector2(0.0, -r * 1.5), at + Vector2(0.0, r * 0.4), color, thin, true)
		c.draw_line(at + Vector2(-r * 0.6, -r * 0.9), at + Vector2(r * 0.6, -r * 0.9), color, thin, true)
	elif kind == Layout.SITE_AIRFIELD:
		c.draw_line(at + Vector2(-r * 1.3, 0.0), at + Vector2(r * 1.3, 0.0), color, thin, true)
		c.draw_line(at + Vector2(0.0, -r), at + Vector2(0.0, r * 0.9), color, thin, true)
		c.draw_line(at + Vector2(-r * 0.5, r * 0.9), at + Vector2(r * 0.5, r * 0.9), color, thin, true)
	elif kind == Layout.SITE_BUNKER:
		c.draw_colored_polygon(PackedVector2Array([
			at + Vector2(-r, r * 0.7), at + Vector2(-r * 0.6, -r * 0.6),
			at + Vector2(r * 0.6, -r * 0.6), at + Vector2(r, r * 0.7)]), color)
	elif kind == Layout.SITE_CAMP:
		c.draw_rect(Rect2(at - Vector2(r, r * 0.8), Vector2(r * 2.0, r * 1.6)), color, false, thin)
		c.draw_line(at + Vector2(-r, -r * 0.8), at + Vector2(r, r * 0.8), color, thin, true)
		c.draw_line(at + Vector2(-r, r * 0.8), at + Vector2(r, -r * 0.8), color, thin, true)
	elif kind == Layout.SITE_CROSSROADS:
		c.draw_line(at + Vector2(-r, -r), at + Vector2(r, r), color, thin, true)
		c.draw_line(at + Vector2(-r, r), at + Vector2(r, -r), color, thin, true)
	elif kind == Layout.SITE_BRIDGE:
		c.draw_line(at + Vector2(-r, -r * 0.4), at + Vector2(r, -r * 0.4), color, thin, true)
		c.draw_line(at + Vector2(-r, r * 0.4), at + Vector2(r, r * 0.4), color, thin, true)
		c.draw_line(at + Vector2(-r * 0.4, -r), at + Vector2(-r * 0.4, r), color, thin, true)
		c.draw_line(at + Vector2(r * 0.4, -r), at + Vector2(r * 0.4, r), color, thin, true)
	else:
		c.draw_line(at + Vector2(-r, r * 0.6), at + Vector2(-r * 0.2, -r * 0.5), color, thin, true)
		c.draw_line(at + Vector2(-r * 0.2, -r * 0.5), at + Vector2(r * 0.3, r * 0.2), color, thin, true)
		c.draw_line(at + Vector2(r * 0.3, r * 0.2), at + Vector2(r, -r * 0.7), color, thin, true)


func _draw_objectives(c: Control) -> void:
	if _tracker == null:
		return
	var font := ThemeDB.fallback_font
	for entry in _tracker.active():
		var obj := entry as MissionDefs.Objective
		if obj == null:
			continue
		var at := _world_to_view(Vector2(obj.position.x, obj.position.z))
		c.draw_arc(at, 13.0, 0.0, TAU, 32, _STAMP, 2.4, true)
		c.draw_arc(at, 17.0, 0.0, TAU, 32, Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.45), 1.2, true)
		if obj.radius > 1.0:
			c.draw_arc(at, obj.radius * _pixels_per_metre(), 0.0, TAU, 48,
					Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.28), 1.4, true)
		if font == null:
			continue
		var icon := MissionDefs.kind_icon(obj.kind)
		var icon_size := font.get_string_size(icon, HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		c.draw_string(font, at + Vector2(-icon_size.x * 0.5, 5.0), icon,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 14, _STAMP)
		var label := obj.title.to_upper()
		var text_size := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		c.draw_string(font, at + Vector2(-text_size.x * 0.5, -22.0), label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, _STAMP)


func _draw_player(c: Control) -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var pos := _player.global_position
	var at := _world_to_view(Vector2(pos.x, pos.z))
	var forward := -_player.global_transform.basis.z
	var heading := atan2(forward.x, -forward.z)
	# Field of view cone, 60 m long.
	var cone_length := 60.0 * _pixels_per_metre()
	var half_angle := deg_to_rad(clampf(float(Game.fov), 40.0, 120.0)) * 0.5
	var fan := PackedVector2Array()
	fan.append(at)
	var steps := 12
	for i in range(steps + 1):
		var a := heading - half_angle + (half_angle * 2.0) * float(i) / float(steps)
		fan.append(at + Vector2(sin(a), -cos(a)) * cone_length)
	c.draw_colored_polygon(fan, Color(0.94, 0.86, 0.42, 0.20))
	# The soldier arrow itself, stamped inside a ring so it reads at any zoom.
	c.draw_arc(at, 15.0, 0.0, TAU, 28, Color(0.96, 0.94, 0.86, 0.75), 2.0, true)
	var tip := at + Vector2(sin(heading), -cos(heading)) * 15.0
	var left := at + Vector2(sin(heading + 2.45), -cos(heading + 2.45)) * 11.0
	var right := at + Vector2(sin(heading - 2.45), -cos(heading - 2.45)) * 11.0
	var tail := at - Vector2(sin(heading), -cos(heading)) * 3.0
	c.draw_colored_polygon(PackedVector2Array([tip, left, tail, right]), Color(0.08, 0.08, 0.07))
	c.draw_colored_polygon(PackedVector2Array([tip, left, tail]), Color(0.94, 0.92, 0.84))


# =============================================================================
# Painting: legend and campaign cartouche
# =============================================================================

func _draw_chrome(c: Control) -> void:
	var font := ThemeDB.fallback_font
	if font == null:
		return
	_draw_legend(c, font)
	_draw_cartouche(c, font)
	_draw_scale_bar(c, font)
	# SECRET stamp, top right of the sheet.
	var stamp_rect := Rect2(c.size.x - 400.0, 30.0, 190.0, 40.0)
	c.draw_set_transform(stamp_rect.position + stamp_rect.size * 0.5, -0.14, Vector2.ONE)
	var local := Rect2(-stamp_rect.size * 0.5, stamp_rect.size)
	c.draw_rect(local, Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.85), false, 3.0)
	c.draw_string(font, Vector2(-72.0, 8.0), "SECRET", HORIZONTAL_ALIGNMENT_LEFT, -1, 24,
			Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.9))
	c.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_legend(c: Control, font: Font) -> void:
	var box := Rect2(_map_view.position + Vector2(14.0, 14.0), Vector2(232.0, 278.0))
	_draw_paper_box(c, box)
	var cursor := box.position + Vector2(14.0, 24.0)
	c.draw_string(font, cursor, "LÉGENDE", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, _INK)
	cursor.y += 18.0
	for kind in _SITE_LABELS.size():
		var icon_at := cursor + Vector2(9.0, 5.0)
		_draw_site_icon(c, kind, icon_at, 6.0, _INK)
		c.draw_string(font, cursor + Vector2(26.0, 9.0), _SITE_LABELS[kind],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
		cursor.y += 17.0
	cursor.y += 4.0
	c.draw_rect(Rect2(cursor + Vector2(3.0, 0.0), Vector2(12.0, 8.0)), _AXIS_RED, true)
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Tenu par l'Axe",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
	cursor.y += 17.0
	c.draw_rect(Rect2(cursor + Vector2(3.0, 0.0), Vector2(12.0, 8.0)), _ALLIED_BLUE, true)
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Secteur libéré",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
	cursor.y += 17.0
	c.draw_arc(cursor + Vector2(9.0, 4.0), 6.0, 0.0, TAU, 20, _STAMP, 2.0, true)
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Objectif en cours",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)


func _draw_cartouche(c: Control, font: Font) -> void:
	var box := Rect2(
		_map_view.position + _map_view.size - Vector2(272.0, 190.0),
		Vector2(258.0, 176.0))
	_draw_paper_box(c, box)
	var cursor := box.position + Vector2(14.0, 24.0)
	c.draw_string(font, cursor, "ÉTAT DE LA CAMPAGNE", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, _INK)
	cursor.y += 8.0
	c.draw_line(cursor + Vector2(0.0, 4.0), cursor + Vector2(box.size.x - 28.0, 4.0), _INK_SOFT, 1.0)
	cursor.y += 20.0
	var rows: Array[PackedStringArray] = [
		PackedStringArray(["Secteurs libérés", "%d / %d" % [War.captured_count(), War.sector_count()]]),
		PackedStringArray(["Objectifs remplis", str(War.objectives_done)]),
		PackedStringArray(["Ennemis abattus", str(War.kills)]),
		PackedStringArray(["Tirs à la tête", str(War.headshots)]),
		PackedStringArray(["Précision", "%d %%" % int(round(War.accuracy() * 100.0))]),
		PackedStringArray(["Pertes", str(War.deaths)]),
		PackedStringArray(["Temps de campagne", _clock(War.play_seconds)]),
		PackedStringArray(["Alerte", String(War.alert_name())]),
	]
	for row in rows:
		c.draw_string(font, cursor, row[0], HORIZONTAL_ALIGNMENT_LEFT, -1, 11,
				Color(_INK.r, _INK.g, _INK.b, 0.75))
		var value_size := font.get_string_size(row[1], HORIZONTAL_ALIGNMENT_LEFT, -1, 11)
		c.draw_string(font, cursor + Vector2(box.size.x - 28.0 - value_size.x, 0.0), row[1],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
		cursor.y += 16.0


func _draw_scale_bar(c: Control, font: Font) -> void:
	var metres := 200.0
	var pixels := metres * _pixels_per_metre()
	if pixels < 24.0:
		metres = 1000.0
		pixels = metres * _pixels_per_metre()
	elif pixels > 260.0:
		metres = 50.0
		pixels = metres * _pixels_per_metre()
	var origin := _map_view.position + Vector2(16.0, _map_view.size.y - 28.0)
	c.draw_rect(Rect2(origin - Vector2(6.0, 16.0), Vector2(pixels + 60.0, 26.0)),
			Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.75), true)
	c.draw_line(origin, origin + Vector2(pixels, 0.0), _INK, 2.0)
	c.draw_line(origin, origin + Vector2(0.0, -6.0), _INK, 2.0)
	c.draw_line(origin + Vector2(pixels, 0.0), origin + Vector2(pixels, -6.0), _INK, 2.0)
	c.draw_string(font, origin + Vector2(pixels + 8.0, 4.0), "%d m" % int(metres),
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)


func _draw_paper_box(c: Control, box: Rect2) -> void:
	c.draw_rect(box, Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.93), true)
	c.draw_rect(box, Color(_INK.r, _INK.g, _INK.b, 0.75), false, 2.0)
	c.draw_rect(box.grow(-4.0), Color(_INK.r, _INK.g, _INK.b, 0.25), false, 1.0)


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


func _play(sample: String) -> void:
	if Sfx == null or not Sfx.has_sample(sample):
		return
	Sfx.play(sample, -6.0, 1.0)
