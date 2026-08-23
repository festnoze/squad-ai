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
##
## Sector states. A sector is in one of THREE states, never two: held by the
## Axis, liberated, or liberated then pushed back under Axis pressure by a
## counter attack (`War.is_sector_contested`). The three are told apart by SHAPE
## first and by colour second: a square chip, a pennant, and a slashed diamond
## over a hatched footprint. A player who cannot tell red from blue still reads
## the map at a glance, and the legend is a reminder rather than a decoder.
##
## Intelligence. A site says nothing about its garrison until its papers have
## been taken, either off a dead officer or through a reconnaissance objective.
## That silence is the point: it is what makes searching an officer worth the
## risk. See `reveal_intel`.
class_name MapUi
extends Control

signal closed()
## Raised when the player asks to travel to a liberated sector. This screen only
## asks: Main owns the decision and performs the move.
signal travel_requested(sector_id: int)

# --- Paper palette -----------------------------------------------------------

const _BACKDROP := Color(0.07, 0.07, 0.06, 0.97)
const _PAPER := Color(0.80, 0.76, 0.62)
const _PAPER_DARK := Color(0.68, 0.64, 0.51)
const _INK := Color(0.10, 0.09, 0.08)
const _INK_SOFT := Color(0.10, 0.09, 0.08, 0.35)
const _STAMP := Color(0.66, 0.14, 0.11)
const _AXIS_RED := Color(0.62, 0.15, 0.12)
const _ALLIED_BLUE := Color(0.20, 0.34, 0.56)
## Contested sectors get their own ink, but the hatching is what identifies them.
const _CONTESTED := Color(0.72, 0.43, 0.08)
const _INTEL := Color(0.16, 0.38, 0.28)
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

# --- Sector states -----------------------------------------------------------

const _STATE_AXIS := 0
const _STATE_FREE := 1
const _STATE_CONTESTED := 2

## Pixels the cursor may travel between press and release and still count as a
## click rather than as a pan. Without it every drag would also select a sector.
const _CLICK_SLOP := 6.0
## Pixels around a site that its click target covers, on top of its footprint.
const _PICK_SLACK := 18.0
## Seconds between two live garrison counts. The count walks the "axis" group,
## so it is throttled instead of running on every frame.
const _INTEL_INTERVAL := 0.5

const _SITE_LABELS: PackedStringArray = [
	"Village", "Ferme", "Bourg et église", "Aérodrome", "Bunker",
	"Camp de prisonniers", "Carrefour", "Pont", "Ruines",
]

## French names for the anchor keys published by SiteBuilder.BuiltSite. Written
## out rather than built from MissionDefs.ANCHOR_* so this screen keeps no
## compile time dependency on the mission module.
const _ANCHOR_LABELS: Dictionary = {
	"fuel": "Dépôt de carburant",
	"radio": "Mât radio",
	"flag": "Mât des couleurs",
	"cage": "Cages à prisonniers",
	"officer": "Poste de commandement",
	"aa": "Pièce antiaérienne",
}


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
var _travel_button: Button = null

var _relief: ImageTexture = null
var _relief_min: float = 0.0
var _relief_max: float = 1.0

var _open: bool = false
var _zoom: float = 1.0
## Centre of the view, in world (x, z) metres.
var _view_center: Vector2 = Vector2.ZERO
var _dragging: bool = false
## Cursor position when the left button went down, and how far it has travelled
## since. Together they separate a click from a pan.
var _press_at: Vector2 = Vector2.ZERO
var _press_travel: float = 0.0

## Site the player last clicked, -1 when nothing is selected. The context card
## and the travel button both hang off it.
var _selected: int = -1
## Sites whose papers have been read: id -> true.
var _intel: Dictionary = {}
## Live Axis count around each intelligenced site: id -> int. Rebuilt on a timer.
var _garrison: Dictionary = {}
var _intel_gap: float = 0.0
## Seconds the map has been on screen, drives the contested hatching pulse.
var _time: float = 0.0

static var _font_cache: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_build()
	close()


func _process(delta: float) -> void:
	if not _open:
		return
	_time += delta
	_intel_gap -= delta
	if _intel_gap <= 0.0:
		_intel_gap = _INTEL_INTERVAL
		_collect_recon_intel()
		_count_garrisons()
	_sync_travel_button()
	_map_view.queue_redraw()
	_chrome.queue_redraw()


# =============================================================================
# Public API (contract 2.35, extended by 11.9)
# =============================================================================

func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void:
	_world = game_world
	_player = player_node
	_tracker = tracker
	_relief = null
	_selected = -1
	_intel.clear()
	_garrison.clear()
	# Officer papers are consumed the instant they are picked up, so the map
	# listens to the pickup itself instead of hoping to find the node later.
	if _player != null and is_instance_valid(_player) \
			and not _player.used.is_connected(_on_player_used):
		_player.used.connect(_on_player_used)


## Marks a site as read: its remaining garrison and its objective anchors become
## visible on the map. Called for officer papers and reconnaissance objectives,
## and safe to call twice on the same site.
func reveal_intel(site_id: int) -> void:
	if site_id < 0 or _intel.has(site_id):
		return
	_intel[site_id] = true
	_count_garrisons()


func has_intel(site_id: int) -> bool:
	return _intel.has(site_id)


## Sorted, so two runs with the same events produce the same list.
func revealed_intel() -> PackedInt32Array:
	var ids: Array = []
	for id in _intel.keys():
		ids.append(int(id))
	ids.sort()
	var out: PackedInt32Array = PackedInt32Array()
	for id in ids:
		out.append(int(id))
	return out


func open() -> void:
	if _open:
		return
	_open = true
	visible = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	set_process(true)
	_build_relief()
	_center_on_player()
	_selected = -1
	_intel_gap = 0.0
	_collect_recon_intel()
	_count_garrisons()
	_sync_travel_button()
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
	_selected = -1
	set_process(false)
	if _travel_button != null:
		_travel_button.visible = false
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

	# Contextual, so it never sits on the map when there is nothing to travel to.
	# Placed by `_sync_travel_button` under the selected sector's card.
	_travel_button = Button.new()
	_travel_button.name = "Travel"
	_travel_button.text = "REJOINDRE"
	_travel_button.focus_mode = Control.FOCUS_NONE
	_travel_button.visible = false
	_style_button(_travel_button)
	_travel_button.add_theme_color_override("font_color", Color(0.94, 0.91, 0.80))
	_travel_button.pressed.connect(_on_travel_pressed)
	add_child(_travel_button)


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
		_press_travel += motion.relative.length()
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
	elif button.button_index == MOUSE_BUTTON_RIGHT and button.pressed:
		_select_site(-1)
		accept_event()
	elif button.button_index == MOUSE_BUTTON_LEFT:
		_dragging = button.pressed
		if button.pressed:
			_press_at = button.position
			_press_travel = 0.0
		elif _press_travel <= _CLICK_SLOP:
			# A press that did not pan the sheet is a click on whatever is under
			# the cursor.
			_select_site(_site_at(button.position - _map_view.position))
		accept_event()


## Nearest site to a point given in map view pixels, -1 when the click landed on
## open country. Sectors win ties: they are the only clickable destinations, and
## a satellite site sitting inside a sector must not steal its click.
func _site_at(local: Vector2) -> int:
	var layout := _layout()
	if layout == null:
		return -1
	var best_id: int = -1
	var best_score: float = 1.0e20
	for site in layout.sites:
		var at := _world_to_view(site.center)
		var reach := maxf(14.0, site.radius * _pixels_per_metre()) + _PICK_SLACK
		var distance := at.distance_to(local)
		if distance > reach:
			continue
		var score := distance
		if site.is_sector:
			score -= 24.0
		if score < best_score:
			best_score = score
			best_id = site.id
	return best_id


func _select_site(site_id: int) -> void:
	if _selected == site_id:
		return
	_selected = site_id
	_sync_travel_button()
	if site_id >= 0:
		_play("ui_click")


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


func _on_travel_pressed() -> void:
	var site := _selected_site()
	if site == null or not _can_travel(site):
		return
	_play("ui_click")
	# The map only asks. Main owns the world, the companions and the clock, so it
	# is Main that decides whether the march happens and what it costs.
	travel_requested.emit(site.id)


## Fired by the player on every successful interaction. Officer papers are a
## pickup carrying `intel_site`, so this is where the map learns a garrison.
func _on_player_used(target: Node) -> void:
	if target == null or not is_instance_valid(target):
		return
	if not target.has_meta("intel_site"):
		return
	reveal_intel(int(target.get_meta("intel_site")))


# =============================================================================
# Intelligence
# =============================================================================

## Completed reconnaissance objectives count as intelligence too, per 11.8.
func _collect_recon_intel() -> void:
	if _tracker == null or not is_instance_valid(_tracker):
		return
	for entry in _tracker.all_objectives():
		var obj := entry as MissionDefs.Objective
		if obj == null or obj.kind != MissionDefs.O_RECON:
			continue
		if not _tracker.is_done(obj.id):
			continue
		reveal_intel(_objective_site(obj))


## Site an objective physically sits on, falling back to its sector.
func _objective_site(obj: MissionDefs.Objective) -> int:
	var raw: Variant = obj.get("_site_id")
	if raw != null and int(raw) >= 0:
		return int(raw)
	return obj.sector_id


## Live Axis strength around every intelligenced site. Walks the "axis" group
## once per `_INTEL_INTERVAL`, never per frame, and only while the map is up.
func _count_garrisons() -> void:
	_garrison.clear()
	if _intel.is_empty():
		return
	var layout := _layout()
	var tree := get_tree()
	if layout == null or tree == null:
		return
	var watched: Array[Layout.Site] = []
	for id in _intel.keys():
		var site := layout.site_by_id(int(id))
		if site != null:
			watched.append(site)
			_garrison[site.id] = 0
	if watched.is_empty():
		return
	for node in tree.get_nodes_in_group("axis"):
		if not is_instance_valid(node):
			continue
		var body := node as Node3D
		if body == null:
			continue
		if body.has_method("is_alive") and not bool(body.call("is_alive")):
			continue
		var at := Vector2(body.global_position.x, body.global_position.z)
		for site in watched:
			var reach := site.radius * 1.45
			if at.distance_squared_to(site.center) <= reach * reach:
				_garrison[site.id] = int(_garrison[site.id]) + 1
				break


## True while the site is streamed in: only then is the live count meaningful.
## Out of streaming range the map falls back to the establishment strength.
func _site_is_loaded(site_id: int) -> bool:
	if _world == null or not is_instance_valid(_world):
		return false
	return _world.built_site(site_id) != null


func _anchor_names(site_id: int) -> PackedStringArray:
	var out := PackedStringArray()
	if _world == null or not is_instance_valid(_world):
		return out
	var built := _world.built_site(site_id)
	if built == null:
		return out
	var keys: Array = built.objective_anchors.keys()
	keys.sort()
	for key in keys:
		var anchor := String(key)
		out.append(String(_ANCHOR_LABELS.get(anchor, anchor.capitalize())))
	return out


func _anchor_points(site_id: int) -> Array[Vector2]:
	var out: Array[Vector2] = []
	if _world == null or not is_instance_valid(_world):
		return out
	var built := _world.built_site(site_id)
	if built == null:
		return out
	var keys: Array = built.objective_anchors.keys()
	keys.sort()
	for key in keys:
		var point: Vector3 = built.objective_anchors[key]
		out.append(Vector2(point.x, point.z))
	return out


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
			"MOLETTE : ZOOM     CLIC MAINTENU : DÉPLACER     CLIC : SÉLECTIONNER UN SITE",
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
		var state := _sector_state(site)
		var color := _state_color(site, state)
		var radius := 8.0 if site.is_sector else 6.0
		if site.is_sector:
			# Hold circle, drawn at the real footprint radius when zoomed in.
			var footprint := maxf(radius + 4.0, site.radius * _pixels_per_metre())
			_draw_sector_footprint(c, at, footprint, state)
		if _selected == site.id:
			c.draw_arc(at, radius + 11.0, 0.0, TAU, 28, Color(_INK.r, _INK.g, _INK.b, 0.85), 1.6, true)
		_draw_site_icon(c, site.kind, at, radius, color)
		if site.is_sector:
			# Fixed pixel badge: the footprint hatching disappears when zoomed
			# out, this never does.
			_draw_state_badge(c, at + Vector2(radius + 6.0, -radius - 4.0), state)
		if _intel.has(site.id):
			_draw_intel_marks(c, site, at, radius)
		# The context card already spells out everything the labels say, and it
		# is pinned right where they are drawn. Two copies of the same words on
		# top of each other help nobody.
		if font == null or _selected == site.id:
			continue
		var label := site.display_name.to_upper()
		var text_size := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		var text_at := at + Vector2(-text_size.x * 0.5, radius + 15.0)
		c.draw_string(font, text_at + Vector2.ONE, label,
				HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(0.95, 0.93, 0.85, 0.55))
		c.draw_string(font, text_at, label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, _INK)
		var below := text_at + Vector2(0.0, 17.0)
		if state == _STATE_CONTESTED:
			_draw_contested_stamp(c, font, Vector2(at.x, below.y))
			below.y += 19.0
		# Garrison strength is intelligence, not scenery: a site that has not
		# been searched says nothing at all.
		if _intel.has(site.id):
			c.draw_string(font, below, _garrison_line(site),
					HORIZONTAL_ALIGNMENT_LEFT, -1, 10, _INTEL)


## Which of the three states a site is in. Non sector sites are reported as
## `_STATE_AXIS`, they have no campaign state of their own.
func _sector_state(site: Layout.Site) -> int:
	if not site.is_sector:
		return _STATE_AXIS
	if not War.is_sector_captured(site.id):
		return _STATE_AXIS
	return _STATE_CONTESTED if War.is_sector_contested(site.id) else _STATE_FREE


func _state_color(site: Layout.Site, state: int) -> Color:
	if not site.is_sector:
		return _INK
	if state == _STATE_FREE:
		return _ALLIED_BLUE
	if state == _STATE_CONTESTED:
		return _CONTESTED
	return _AXIS_RED


func _state_label(state: int) -> String:
	if state == _STATE_FREE:
		return "SECTEUR LIBÉRÉ"
	if state == _STATE_CONTESTED:
		return "SECTEUR CONTESTÉ"
	return "TENU PAR L'AXE"


## The sector footprint, drawn differently for each state so the ring itself
## carries the information: a plain crenellated ring for the Axis, a double ring
## for a liberated sector, and diagonal hatching under a broken ring for a
## contested one. Hatching is the cartographic mark for disputed ground and it
## survives any colour blindness.
func _draw_sector_footprint(c: Control, at: Vector2, radius: float, state: int) -> void:
	var color := _AXIS_RED
	if state == _STATE_FREE:
		color = _ALLIED_BLUE
	elif state == _STATE_CONTESTED:
		color = _CONTESTED
	var soft := Color(color.r, color.g, color.b, 0.55)
	if state == _STATE_FREE:
		c.draw_arc(at, radius, 0.0, TAU, 48, soft, 1.6, true)
		c.draw_arc(at, radius - 4.0, 0.0, TAU, 48, Color(color.r, color.g, color.b, 0.30), 1.2, true)
		return
	if state == _STATE_AXIS:
		c.draw_arc(at, radius, 0.0, TAU, 48, soft, 1.6, true)
		# Outward ticks, the cartographic mark of a held line.
		for i in 12:
			var a := TAU * float(i) / 12.0
			var dir := Vector2(cos(a), sin(a))
			c.draw_line(at + dir * radius, at + dir * (radius + 4.0), soft, 1.4, true)
		return
	_draw_hatched_disc(c, at, radius, Color(color.r, color.g, color.b, 0.34))
	# Broken ring, slowly turning, for ground that is changing hands.
	var pulse := 0.55 + 0.25 * sin(_time * 2.4)
	var spin := _time * 0.35
	for i in 10:
		var start := spin + TAU * float(i) / 10.0
		c.draw_arc(at, radius, start, start + TAU / 18.0, 6,
				Color(color.r, color.g, color.b, pulse), 2.2, true)


## 45 degree hatching clipped to a disc, computed chord by chord: `draw_arc` has
## no fill and a stencil would need a texture the project does not have.
func _draw_hatched_disc(c: Control, at: Vector2, radius: float, color: Color) -> void:
	var step := maxf(5.0, radius * 0.22)
	var axis := Vector2(0.7071, 0.7071)
	var normal := Vector2(-0.7071, 0.7071)
	var offset := -radius + step * 0.5
	while offset < radius:
		var half := sqrt(maxf(0.0, radius * radius - offset * offset))
		if half > 1.0:
			var mid := at + normal * offset
			c.draw_line(mid - axis * half, mid + axis * half, color, 1.4, true)
		offset += step


## Three fixed size chips, one shape each: square for the Axis, pennant for a
## liberated sector, slashed diamond for a contested one. Shared with the legend
## so the map and its key can never drift apart.
func _draw_state_badge(c: Control, at: Vector2, state: int) -> void:
	if state == _STATE_FREE:
		var mast := at + Vector2(-4.0, 6.0)
		c.draw_line(mast, mast + Vector2(0.0, -12.0), _INK, 1.4, true)
		c.draw_colored_polygon(PackedVector2Array([
			mast + Vector2(0.0, -12.0), mast + Vector2(10.0, -8.0),
			mast + Vector2(0.0, -4.0)]), _ALLIED_BLUE)
		return
	if state == _STATE_CONTESTED:
		var points := PackedVector2Array([
			at + Vector2(0.0, -7.0), at + Vector2(7.0, 0.0),
			at + Vector2(0.0, 7.0), at + Vector2(-7.0, 0.0)])
		c.draw_colored_polygon(points, _CONTESTED)
		c.draw_polyline(PackedVector2Array([points[0], points[1], points[2],
				points[3], points[0]]), _INK, 1.2, true)
		c.draw_line(at + Vector2(-4.4, 4.4), at + Vector2(4.4, -4.4), _INK, 1.8, true)
		return
	var square := Rect2(at - Vector2(6.0, 6.0), Vector2(12.0, 12.0))
	c.draw_rect(square, _AXIS_RED, true)
	c.draw_rect(square, _INK, false, 1.2)


## Rubber stamp under the name of a sector the Wehrmacht has taken back.
func _draw_contested_stamp(c: Control, font: Font, at: Vector2) -> void:
	var text := "CONTESTÉ"
	var text_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 10)
	var box := Rect2(at - Vector2(text_size.x * 0.5 + 5.0, 9.0),
			Vector2(text_size.x + 10.0, 14.0))
	c.draw_rect(box, Color(_CONTESTED.r, _CONTESTED.g, _CONTESTED.b, 0.85), false, 1.4)
	c.draw_string(font, at - Vector2(text_size.x * 0.5, 0.0), text,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 10, _CONTESTED)


## Objective anchors of a searched site: small surveyor crosses, labelled once
## the sheet is zoomed in far enough for the names to have room.
func _draw_intel_marks(c: Control, site: Layout.Site, at: Vector2, radius: float) -> void:
	var font := ThemeDB.fallback_font
	var names := _anchor_names(site.id)
	var points := _anchor_points(site.id)
	# The read papers themselves, a small dog eared sheet beside the icon.
	var corner := at + Vector2(-radius - 13.0, -radius - 3.0)
	c.draw_rect(Rect2(corner, Vector2(9.0, 11.0)), Color(0.94, 0.92, 0.84, 0.95), true)
	c.draw_rect(Rect2(corner, Vector2(9.0, 11.0)), _INTEL, false, 1.2)
	c.draw_line(corner + Vector2(2.0, 3.5), corner + Vector2(7.0, 3.5), _INTEL, 1.0)
	c.draw_line(corner + Vector2(2.0, 6.5), corner + Vector2(7.0, 6.5), _INTEL, 1.0)
	for i in points.size():
		var mark := _world_to_view(points[i])
		c.draw_line(mark + Vector2(-4.0, 0.0), mark + Vector2(4.0, 0.0), _INTEL, 1.4, true)
		c.draw_line(mark + Vector2(0.0, -4.0), mark + Vector2(0.0, 4.0), _INTEL, 1.4, true)
		c.draw_arc(mark, 5.5, 0.0, TAU, 16, Color(_INTEL.r, _INTEL.g, _INTEL.b, 0.6), 1.0, true)
		if font == null or _zoom < 2.4 or i >= names.size():
			continue
		c.draw_string(font, mark + Vector2(8.0, 4.0), names[i],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 10, _INTEL)


## Remaining strength of a searched site. Streamed in, the count is the real one;
## out of streaming range only the establishment strength is honest.
func _garrison_line(site: Layout.Site) -> String:
	if not _site_is_loaded(site.id):
		if site.garrison <= 0:
			return "aucune garnison signalée"
		return "garnison estimée %d" % site.garrison
	var live: int = int(_garrison.get(site.id, 0))
	var establishment: int = maxi(live, site.garrison)
	if establishment <= 0:
		return "position vide"
	return "garnison %d / %d sur place" % [live, establishment]


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
	# Off the camera rig, not off the body: the CharacterBody3D never rotates,
	# `Player._move` builds its own basis from `rig.rotation.y` instead. Reading
	# the body left this cone permanently aimed at world north, so the map never
	# told the player which way he was actually looking. The rig carries yaw and
	# only yaw, pitch being on a child pivot, so no tilt leaks into the heading.
	var pivot: Node3D = _player
	if _player.rig != null and is_instance_valid(_player.rig):
		pivot = _player.rig
	var forward := -pivot.global_transform.basis.z
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
	_draw_card(c, font)
	# SECRET stamp, top right of the sheet.
	var stamp_rect := Rect2(c.size.x - 400.0, 30.0, 190.0, 40.0)
	c.draw_set_transform(stamp_rect.position + stamp_rect.size * 0.5, -0.14, Vector2.ONE)
	var local := Rect2(-stamp_rect.size * 0.5, stamp_rect.size)
	c.draw_rect(local, Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.85), false, 3.0)
	c.draw_string(font, Vector2(-72.0, 8.0), "SECRET", HORIZONTAL_ALIGNMENT_LEFT, -1, 24,
			Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.9))
	c.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)


func _draw_legend(c: Control, font: Font) -> void:
	var box := Rect2(_map_view.position + Vector2(14.0, 14.0), Vector2(232.0, 366.0))
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
	cursor.y += 6.0
	c.draw_line(cursor + Vector2(0.0, -2.0), cursor + Vector2(box.size.x - 28.0, -2.0),
			_INK_SOFT, 1.0)
	cursor.y += 8.0
	# The same three badges the map draws, so the key is a reminder and never a
	# decoder ring.
	var states: PackedInt32Array = [_STATE_AXIS, _STATE_FREE, _STATE_CONTESTED]
	var hints: PackedStringArray = [
		"Tenu par l'Axe", "Secteur libéré", "Contesté, contre-attaque",
	]
	for i in states.size():
		_draw_state_badge(c, cursor + Vector2(9.0, 4.0), states[i])
		c.draw_string(font, cursor + Vector2(26.0, 9.0), hints[i],
				HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
		cursor.y += 19.0
	_draw_hatched_disc(c, cursor + Vector2(9.0, 4.0), 8.0,
			Color(_CONTESTED.r, _CONTESTED.g, _CONTESTED.b, 0.55))
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Zone disputée (hachures)",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
	cursor.y += 18.0
	c.draw_arc(cursor + Vector2(9.0, 4.0), 6.0, 0.0, TAU, 20, _STAMP, 2.0, true)
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Objectif en cours",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)
	cursor.y += 18.0
	c.draw_line(cursor + Vector2(5.0, 4.0), cursor + Vector2(13.0, 4.0), _INTEL, 1.4, true)
	c.draw_line(cursor + Vector2(9.0, 0.0), cursor + Vector2(9.0, 8.0), _INTEL, 1.4, true)
	c.draw_string(font, cursor + Vector2(26.0, 9.0), "Renseignement obtenu",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 11, _INK)


# =============================================================================
# Painting: the context card of the selected site
# =============================================================================

## One card line: `text`, plus a tone deciding its ink and its size.
const _TONE_TITLE := 0
const _TONE_STATE := 1
const _TONE_BODY := 2
const _TONE_INTEL := 3
const _TONE_DENIED := 4

const _CARD_WIDTH := 246.0
const _CARD_LINE := 15.0
const _CARD_TOP := 30.0
const _CARD_BOTTOM := 12.0
const _CARD_BUTTON := 38.0


func _selected_site() -> Layout.Site:
	if _selected < 0:
		return null
	var layout := _layout()
	if layout == null:
		return null
	return layout.site_by_id(_selected)


## A liberated sector that is not being fought over is the only place worth
## marching to. The final word still belongs to Main.
func _can_travel(site: Layout.Site) -> bool:
	if site == null or not site.is_sector:
		return false
	return War.is_sector_captured(site.id) and not War.is_sector_contested(site.id)


## Why the march is refused, "" when it is not. Saying it out loud is what stops
## the player from thinking the map is broken.
func _travel_denial(site: Layout.Site) -> String:
	if site == null or not site.is_sector or _can_travel(site):
		return ""
	if not War.is_sector_captured(site.id):
		return "Secteur ennemi : pas de ralliement"
	return "Contre-attaque : ralliement suspendu"


func _card_lines(site: Layout.Site) -> Array[Dictionary]:
	var lines: Array[Dictionary] = []
	if site == null:
		return lines
	lines.append({"text": site.display_name.to_upper(), "tone": _TONE_TITLE})
	if site.is_sector:
		lines.append({"text": _state_label(_sector_state(site)), "tone": _TONE_STATE})
	else:
		var kind := site.kind
		var kind_label := String(_SITE_LABELS[kind]) if kind < _SITE_LABELS.size() else "Position"
		lines.append({"text": kind_label.to_upper(), "tone": _TONE_STATE})
	if _intel.has(site.id):
		var strength := _garrison_line(site)
		# Only the first letter, `capitalize` would title case the whole line.
		strength = strength.substr(0, 1).to_upper() + strength.substr(1)
		lines.append({"text": strength, "tone": _TONE_INTEL})
		var names := _anchor_names(site.id)
		if names.is_empty():
			lines.append({"text": "Ancres hors de portée", "tone": _TONE_BODY})
		for anchor in names:
			lines.append({"text": "- " + anchor, "tone": _TONE_INTEL})
	else:
		lines.append({"text": "Renseignement inconnu", "tone": _TONE_BODY})
		lines.append({"text": "Fouiller un officier", "tone": _TONE_BODY})
	var denial := _travel_denial(site)
	if not denial.is_empty():
		lines.append({"text": denial, "tone": _TONE_DENIED})
	return lines


## Card rectangle in MapUi coordinates, anchored to the selected site and kept
## inside the sheet. Empty when nothing is selected.
func _card_rect() -> Rect2:
	var site := _selected_site()
	if site == null or _map_view == null:
		return Rect2()
	var lines := _card_lines(site)
	var height := _CARD_TOP + float(lines.size()) * _CARD_LINE + _CARD_BOTTOM
	if _can_travel(site):
		height += _CARD_BUTTON
	var anchor := _map_view.position + _world_to_view(site.center) + Vector2(16.0, 14.0)
	var limit_x := _map_view.position.x + _map_view.size.x - _CARD_WIDTH - 10.0
	var limit_y := _map_view.position.y + _map_view.size.y - height - 10.0
	anchor.x = clampf(anchor.x, _map_view.position.x + 10.0, maxf(limit_x, _map_view.position.x + 10.0))
	anchor.y = clampf(anchor.y, _map_view.position.y + 10.0, maxf(limit_y, _map_view.position.y + 10.0))
	return Rect2(anchor, Vector2(_CARD_WIDTH, height))


func _draw_card(c: Control, font: Font) -> void:
	var site := _selected_site()
	if site == null:
		return
	var box := _card_rect()
	if box.size.x <= 0.0:
		return
	_draw_paper_box(c, box)
	# Leader line back to the site, so a clamped card still points at its owner.
	var target := _map_view.position + _world_to_view(site.center)
	var edge := Vector2(clampf(target.x, box.position.x, box.end.x),
			clampf(target.y, box.position.y, box.end.y))
	c.draw_line(edge, target, Color(_INK.r, _INK.g, _INK.b, 0.55), 1.2, true)
	var cursor := box.position + Vector2(14.0, 24.0)
	for line in _card_lines(site):
		var tone := int(line["tone"])
		var text := String(line["text"])
		if tone == _TONE_TITLE:
			c.draw_string(font, cursor, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, _INK)
			c.draw_line(cursor + Vector2(0.0, 5.0), cursor + Vector2(box.size.x - 28.0, 5.0),
					_INK_SOFT, 1.0)
			cursor.y += _CARD_LINE + 5.0
			continue
		var color := Color(_INK.r, _INK.g, _INK.b, 0.75)
		if tone == _TONE_STATE:
			color = _state_color(site, _sector_state(site)) if site.is_sector else _INK
		elif tone == _TONE_INTEL:
			color = _INTEL
		elif tone == _TONE_DENIED:
			color = _STAMP
		c.draw_string(font, cursor, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 11, color)
		cursor.y += _CARD_LINE


## Keeps the real Button glued under the card. It is a child of this Control and
## not a painted rectangle, so the click goes through the normal focus and hover
## path instead of a hand rolled hit test.
func _sync_travel_button() -> void:
	if _travel_button == null:
		return
	var site := _selected_site()
	if not _open or site == null or not _can_travel(site):
		_travel_button.visible = false
		return
	var box := _card_rect()
	_travel_button.text = "REJOINDRE " + site.display_name.to_upper()
	_travel_button.visible = true
	_travel_button.position = box.position + Vector2(12.0, box.size.y - _CARD_BUTTON - 2.0)
	_travel_button.size = Vector2(box.size.x - 24.0, 32.0)


func _draw_cartouche(c: Control, font: Font) -> void:
	var box := Rect2(
		_map_view.position + _map_view.size - Vector2(272.0, 222.0),
		Vector2(258.0, 208.0))
	_draw_paper_box(c, box)
	var cursor := box.position + Vector2(14.0, 24.0)
	c.draw_string(font, cursor, "ÉTAT DE LA CAMPAGNE", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, _INK)
	cursor.y += 8.0
	c.draw_line(cursor + Vector2(0.0, 4.0), cursor + Vector2(box.size.x - 28.0, 4.0), _INK_SOFT, 1.0)
	cursor.y += 20.0
	var rows: Array[PackedStringArray] = [
		PackedStringArray(["Secteurs libérés", "%d / %d" % [War.captured_count(), War.sector_count()]]),
		PackedStringArray(["Secteurs contestés", str(War.contested_ids().size())]),
		PackedStringArray(["Objectifs remplis", str(War.objectives_done)]),
		PackedStringArray(["Renseignements", str(War.intel_found)]),
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
