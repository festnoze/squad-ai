class_name MapUi
extends Control
## Full screen world map, toggled with the map key.
##
## The map covers MAP_BLOCKS x MAP_BLOCKS world blocks centred on the player,
## sampled every SAMPLE_STEP blocks into a small RGBA8 image shown with nearest
## filtering. Sampling relies on TerrainGen through VoxelWorld.surface_height
## and biome_name_at, which are pure functions of the seed, so the map also
## covers chunks that were never loaded.
##
## Generation is spread over frames (ROWS_PER_FRAME image rows per _process
## call) so opening the map never freezes the game. Overlays (village houses,
## the world spawn, the player marker with its heading line) are stamped into
## the image once the terrain pass is complete.

signal closed()

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_COLOR := Color(0.94, 0.96, 0.98)
const TEXT_DIM := Color(0.68, 0.72, 0.78)
const DIM_COLOR := Color(0.0, 0.0, 0.0, 0.42)

## Covered area in world blocks, and the sampling stride.
const MAP_BLOCKS := 384
const SAMPLE_STEP := 2
const IMG_SIZE := 192              # MAP_BLOCKS / SAMPLE_STEP
const ROWS_PER_FRAME := 12
const TEXTURE_EVERY_BATCHES := 4

const BACKGROUND := Color(0.04, 0.05, 0.07, 1.0)
const OCEAN_SHALLOW := Color(0.20, 0.44, 0.68, 1.0)
const OCEAN_DEEP := Color(0.05, 0.13, 0.32, 1.0)
const UNKNOWN_BIOME := Color(0.5, 0.5, 0.5, 1.0)
const HOUSE_COLOR := Color(0.45, 0.28, 0.12, 1.0)
const SPAWN_COLOR := Color(1.0, 0.84, 0.25, 1.0)
const PLAYER_COLOR := Color(1.0, 1.0, 1.0, 1.0)

## Height at which the subtle lift toward white starts, and its ramp length.
const LIFT_START := 70
const LIFT_RANGE := 24.0
const LIFT_MAX := 0.45

var _world: VoxelWorld = null
var _player: Player = null
var _open := false
var _built := false

var _image: Image = null
var _texture: ImageTexture = null
var _origin_x := 0
var _origin_z := 0
var _row := IMG_SIZE               # >= IMG_SIZE means nothing left to sample
var _batches := 0

var _header: Label = null
var _map_view: TextureRect = null
var _status: Label = null


func _ready() -> void:
	_ensure_built()


func setup(world: VoxelWorld, player: Player) -> void:
	_ensure_built()
	_world = world
	_player = player


func open() -> void:
	_ensure_built()
	if not _open:
		_open = true
		visible = true
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	# Opening again while already open restarts the survey around the player.
	_restart()


func close() -> void:
	if not _open:
		return
	_open = false
	visible = false
	if not _other_screen_open():
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	closed.emit()


func is_open() -> bool:
	return _open


func _input(event: InputEvent) -> void:
	if not _open:
		return
	var wants_close := false
	if InputMap.has_action("pause") and event.is_action_pressed("pause"):
		wants_close = true
	elif InputMap.has_action("map") and event.is_action_pressed("map"):
		wants_close = true
	if wants_close:
		close()
		get_viewport().set_input_as_handled()


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

## Base map colour of a biome, keyed by the French names of
## TerrainGen.BIOME_NAMES. Unknown names get a neutral grey. Every colour is
## fully opaque.
static func biome_color(biome_name: String) -> Color:
	match biome_name:
		"Océan":
			return Color(0.16, 0.32, 0.58, 1.0)
		"Plage":
			return Color(0.86, 0.80, 0.55, 1.0)
		"Plaines":
			return Color(0.45, 0.66, 0.30, 1.0)
		"Forêt":
			return Color(0.23, 0.46, 0.20, 1.0)
		"Taïga":
			return Color(0.30, 0.52, 0.44, 1.0)
		"Désert":
			return Color(0.90, 0.74, 0.38, 1.0)
		"Savane":
			return Color(0.68, 0.64, 0.32, 1.0)
		"Montagnes":
			return Color(0.55, 0.55, 0.58, 1.0)
		"Toundra":
			return Color(0.82, 0.85, 0.88, 1.0)
		"Marais":
			return Color(0.36, 0.44, 0.28, 1.0)
	return UNKNOWN_BIOME


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
	frame.add_theme_stylebox_override("panel", _make_box(PANEL_BG, PANEL_BORDER, 2, 14.0))
	center.add_child(frame)

	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 10)
	column.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.add_child(column)

	_header = Label.new()
	_header.text = "Monde"
	_header.add_theme_color_override("font_color", TEXT_COLOR)
	_header.add_theme_font_size_override("font_size", 18)
	_header.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(_header)

	# The map itself sits inside its own 2 px bordered panel.
	var map_frame := PanelContainer.new()
	map_frame.add_theme_stylebox_override("panel",
			_make_box(Color(0.03, 0.04, 0.06, 0.95), PANEL_BORDER, 2, 2.0))
	map_frame.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	column.add_child(map_frame)

	_map_view = TextureRect.new()
	_map_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_map_view.stretch_mode = TextureRect.STRETCH_SCALE
	_map_view.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_map_view.custom_minimum_size = Vector2(480.0, 480.0)
	_map_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
	map_frame.add_child(_map_view)

	_status = Label.new()
	_status.text = "Cartographie..."
	_status.add_theme_color_override("font_color", TEXT_DIM)
	_status.add_theme_font_size_override("font_size", 13)
	_status.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	column.add_child(_status)

	column.add_child(_build_legend())


func _build_legend() -> Control:
	var legend := HBoxContainer.new()
	legend.add_theme_constant_override("separation", 14)
	legend.alignment = BoxContainer.ALIGNMENT_CENTER
	legend.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var entries: Array = [
		["Plaines", biome_color("Plaines")],
		["Forêt", biome_color("Forêt")],
		["Désert", biome_color("Désert")],
		["Montagnes", biome_color("Montagnes")],
		["Océan", biome_color("Océan")],
		["Toundra", biome_color("Toundra")],
		["Village", HOUSE_COLOR],
		["Apparition", SPAWN_COLOR],
	]
	for entry: Array in entries:
		var item := HBoxContainer.new()
		item.add_theme_constant_override("separation", 5)
		item.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var square := ColorRect.new()
		square.color = entry[1]
		square.custom_minimum_size = Vector2(12.0, 12.0)
		square.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		square.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item.add_child(square)
		var label := Label.new()
		label.text = entry[0]
		label.add_theme_color_override("font_color", TEXT_DIM)
		label.add_theme_font_size_override("font_size", 13)
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item.add_child(label)
		legend.add_child(item)
	return legend


static func _make_box(bg: Color, border: Color, width: int, margin: float) -> StyleBoxFlat:
	var box := StyleBoxFlat.new()
	box.bg_color = bg
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(0)
	box.content_margin_left = margin
	box.content_margin_right = margin
	box.content_margin_top = margin
	box.content_margin_bottom = margin
	return box


# ---------------------------------------------------------------------------
# Survey
# ---------------------------------------------------------------------------

## (Re)starts the survey around the player's current position.
func _restart() -> void:
	if _world == null or _player == null:
		return
	var px := floori(_player.global_position.x)
	var pz := floori(_player.global_position.z)
	_origin_x = px - MAP_BLOCKS / 2
	_origin_z = pz - MAP_BLOCKS / 2
	_row = 0
	_batches = 0
	_image = Image.create(IMG_SIZE, IMG_SIZE, false, Image.FORMAT_RGBA8)
	_image.fill(BACKGROUND)
	_texture = ImageTexture.create_from_image(_image)
	_map_view.texture = _texture
	_status.visible = true
	_update_header(px, pz)
	_fit_to_viewport()


func _update_header(px: int, pz: int) -> void:
	var world_name := "monde"
	var game := get_node_or_null(^"/root/Game")
	if game != null:
		var stored: Variant = game.get("world_name")
		if stored is String and not (stored as String).is_empty():
			world_name = stored
	var world_seed := int(_world.load_meta().get("seed", 0))
	_header.text = "Monde %s  -  graine %d  -  x %d z %d" % [world_name, world_seed, px, pz]


## Scales the map view to roughly 70 percent of the viewport height.
func _fit_to_viewport() -> void:
	if not is_inside_tree():
		return
	var side := floorf(get_viewport_rect().size.y * 0.7)
	side = maxf(side, 192.0)
	_map_view.custom_minimum_size = Vector2(side, side)


func _process(_delta: float) -> void:
	if not _open or _image == null or _row >= IMG_SIZE:
		return
	var last := mini(_row + ROWS_PER_FRAME, IMG_SIZE)
	while _row < last:
		_sample_row(_row)
		_row += 1
	_batches += 1
	if _row >= IMG_SIZE:
		_draw_overlays()
		_texture.update(_image)
		_status.visible = false
	elif _batches % TEXTURE_EVERY_BATCHES == 0:
		_texture.update(_image)


## Fills one image row (a line of constant wz). The hillshade compares each
## sample with its western neighbour, which is simply the previous sample of
## the same row, so every column costs a single extra surface_height call.
func _sample_row(py: int) -> void:
	var wz := _origin_z + py * SAMPLE_STEP
	var west_h := _world.surface_height(_origin_x - SAMPLE_STEP, wz)
	for px in IMG_SIZE:
		var wx := _origin_x + px * SAMPLE_STEP
		var h := _world.surface_height(wx, wz)
		_image.set_pixel(px, py, _sample_color(wx, wz, h, west_h))
		west_h = h


func _sample_color(wx: int, wz: int, h: int, west_h: int) -> Color:
	if h < ChunkData.SEA_LEVEL:
		var depth := clampf(float(ChunkData.SEA_LEVEL - h) / 18.0, 0.0, 1.0)
		return OCEAN_SHALLOW.lerp(OCEAN_DEEP, depth)
	var base := biome_color(_world.biome_name_at(wx, wz))
	# West-facing slopes darken, east-facing slopes brighten: cheap hillshade.
	var shade := clampf(1.0 + float(h - west_h) * 0.06, 0.75, 1.25)
	var c := Color(clampf(base.r * shade, 0.0, 1.0),
			clampf(base.g * shade, 0.0, 1.0),
			clampf(base.b * shade, 0.0, 1.0), 1.0)
	if h > LIFT_START:
		var lift := clampf(float(h - LIFT_START) / LIFT_RANGE, 0.0, 1.0) * LIFT_MAX
		c = c.lerp(Color(1.0, 1.0, 1.0, 1.0), lift)
	c.a = 1.0
	return c


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

func _draw_overlays() -> void:
	_draw_houses()
	_draw_spawn()
	_draw_player()


## Village houses inside the covered area, as 3x3 brown squares. Chunks are
## enumerated over the whole area: houses_in_chunk is deterministic terrain
## metadata, so it also works for chunks that were never streamed in.
func _draw_houses() -> void:
	var c_min_x := VoxelWorld.chunk_of(_origin_x)
	var c_max_x := VoxelWorld.chunk_of(_origin_x + MAP_BLOCKS - 1)
	var c_min_z := VoxelWorld.chunk_of(_origin_z)
	var c_max_z := VoxelWorld.chunk_of(_origin_z + MAP_BLOCKS - 1)
	for cx in range(c_min_x, c_max_x + 1):
		for cz in range(c_min_z, c_max_z + 1):
			for house in _world.houses_in_chunk(cx, cz):
				_stamp_world_square(house.x, house.z, HOUSE_COLOR)


func _draw_spawn() -> void:
	var sp := _world.spawn_point()
	_stamp_world_square(floori(sp.x), floori(sp.z), SPAWN_COLOR)


## The player sits at the exact centre of the covered area. A 5 px white
## square plus a short line showing where the player looks. Forward is -Z
## rotated by yaw; on the image +x is east (+wx) and +y is south (+wz).
func _draw_player() -> void:
	var center := IMG_SIZE / 2
	_fill_square(center, center, 2, PLAYER_COLOR)
	var yaw := _player.rotation.y
	var dir := Vector2(-sin(yaw), -cos(yaw))
	for i in range(3, 9):
		var px := center + roundi(dir.x * float(i))
		var py := center + roundi(dir.y * float(i))
		_set_pixel_safe(px, py, PLAYER_COLOR)


## 3x3 square around a world position, skipped when outside the covered area.
func _stamp_world_square(wx: int, wz: int, color: Color) -> void:
	var dx := wx - _origin_x
	var dz := wz - _origin_z
	if dx < 0 or dz < 0 or dx >= MAP_BLOCKS or dz >= MAP_BLOCKS:
		return
	_fill_square(dx / SAMPLE_STEP, dz / SAMPLE_STEP, 1, color)


func _fill_square(cx: int, cy: int, radius: int, color: Color) -> void:
	for dy in range(-radius, radius + 1):
		for dx in range(-radius, radius + 1):
			_set_pixel_safe(cx + dx, cy + dy, color)


func _set_pixel_safe(px: int, py: int, color: Color) -> void:
	if px < 0 or py < 0 or px >= IMG_SIZE or py >= IMG_SIZE:
		return
	_image.set_pixel(px, py, color)


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
