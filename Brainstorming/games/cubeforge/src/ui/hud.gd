class_name Hud
extends CanvasLayer
## In game heads up display for CUBEFORGE.
##
## Everything is built in code: no scene file, no external font, no image on
## disk. Block previews come from VoxelAtlas, which paints them at startup.
##
## Layout uses anchors only, so the whole interface survives a window resize:
## crosshair and dig ring centred, hotbar bottom centre, toast just above the
## hotbar, loading panel centred, debug overlay top left.

# ---------------------------------------------------------------------------
# Shared style, see docs/CONTRACTS.md section 4.12
# ---------------------------------------------------------------------------

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BG_ACTIVE := Color(0.13, 0.15, 0.19, 0.86)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const PANEL_BORDER_ACTIVE := Color(0.98, 0.99, 1.0, 0.85)
const TEXT_MAIN := Color(0.94, 0.96, 0.98)
const TEXT_DIM := Color(0.68, 0.72, 0.78)
const OUTLINE_COLOR := Color(0.02, 0.02, 0.03, 0.85)
const BORDER_PX := 2

const CELL_PX := 56
const CELL_GAP := 4
const PANEL_PAD := 6
const HOTBAR_MARGIN := 16
const PREVIEW_PX := 40
const CROSSHAIR_PX := 26
const RING_PX := 54
const TOAST_FADE := 0.35
const LOADING_TICK := 0.12
const FPS_TICK := 0.25
## Safety net: if the world reports no pending work for that long without ever
## emitting initial_load_finished, the loading panel steps aside anyway.
const LOADING_GRACE := 1.5

# ---------------------------------------------------------------------------
# Hand drawn widgets
# ---------------------------------------------------------------------------

## Two thin bars with a dark backing, so the shape reads both on white snow
## (dark halo visible) and inside a black cave (light core visible).
class Crosshair extends Control:

	func _draw() -> void:
		var centre := size * 0.5
		var arm := size.x * 0.42
		var gap := 3.0
		_bars(centre, arm + 1.0, gap - 1.0, 4.0, Color(0.0, 0.0, 0.0, 0.62))
		_bars(centre, arm, gap, 2.0, Color(0.96, 0.98, 1.0, 0.93))

	func _bars(centre: Vector2, arm: float, gap: float, thick: float, col: Color) -> void:
		var half := thick * 0.5
		var span := maxf(arm - gap, 1.0)
		draw_rect(Rect2(centre.x - arm, centre.y - half, span, thick), col, true)
		draw_rect(Rect2(centre.x + gap, centre.y - half, span, thick), col, true)
		draw_rect(Rect2(centre.x - half, centre.y - arm, thick, span), col, true)
		draw_rect(Rect2(centre.x - half, centre.y + gap, thick, span), col, true)


## Survival health bar: ten pixel-art hearts, two hit points each. Painted with
## draw_rect from a tiny bitmap so no font glyph or asset is involved.
class Hearts extends Control:

	const HEART_W := 7
	const HEART_H := 6
	const PIXEL := 3.0
	const GAP := 6.0
	const FULL := Color(0.86, 0.16, 0.18)
	const EMPTY := Color(0.22, 0.10, 0.11)
	const ROWS: PackedStringArray = [
		".XX.XX.",
		"XXXXXXX",
		"XXXXXXX",
		".XXXXX.",
		"..XXX..",
		"...X...",
	]

	var current: int = 20
	var maximum: int = 20

	func set_health(new_current: int, new_maximum: int) -> void:
		if new_current == current and new_maximum == maximum:
			return
		current = new_current
		maximum = maxi(new_maximum, 2)
		queue_redraw()

	func _draw() -> void:
		var hearts := maximum / 2
		for i in hearts:
			var origin := Vector2(float(i) * (HEART_W * PIXEL + GAP), 0.0)
			var points := current - i * 2
			_heart(origin, EMPTY, HEART_W)
			if points >= 2:
				_heart(origin, FULL, HEART_W)
			elif points == 1:
				# Left half only: a readable half heart.
				_heart(origin, FULL, 4)

	func _heart(origin: Vector2, col: Color, max_x: int) -> void:
		for r in ROWS.size():
			var line: String = ROWS[r]
			for c in mini(line.length(), max_x):
				if line[c] != "X":
					continue
				draw_rect(Rect2(origin + Vector2(c * PIXEL, r * PIXEL), Vector2(PIXEL, PIXEL)), col, true)


## Dig progress ring drawn around the crosshair. Redrawn only when the ratio
## moved enough to be visible, never once per frame for nothing.
class DigRing extends Control:

	const STEP := 0.01

	var ratio: float = 0.0

	func set_ratio(value: float) -> void:
		var clamped := clampf(value, 0.0, 1.0)
		if is_equal_approx(clamped, ratio):
			return
		if absf(clamped - ratio) < STEP and clamped > 0.0 and ratio > 0.0:
			return
		ratio = clamped
		queue_redraw()

	func _draw() -> void:
		if ratio <= 0.0:
			return
		var centre := size * 0.5
		var radius := minf(size.x, size.y) * 0.5 - 4.0
		if radius <= 1.0:
			return
		var start := -PI * 0.5
		draw_arc(centre, radius, start, start + TAU, 48, Color(0.0, 0.0, 0.0, 0.55), 4.0, true)
		draw_arc(centre, radius, start, start + TAU * ratio, 48, Color(0.98, 0.87, 0.38, 0.95), 3.0, true)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

var _world: VoxelWorld
var _player: Player
var _inventory: Inventory
var _interaction: Interaction
var _sky: SkyController

var _root: Control
var _veil: ColorRect
var _hurt_veil: ColorRect
var _hearts: Hearts
var _hurt_flash: float = 0.0
var _crosshair: Crosshair
var _dig_ring: DigRing
var _hotbar_panel: PanelContainer
var _toast_row: CenterContainer
var _toast_panel: PanelContainer
var _toast_label: Label
var _loading_row: CenterContainer
var _loading_title: Label
var _loading_count: Label
var _debug: DebugOverlay
var _fps_label: Label

var _cells: Array[Panel] = []
var _cell_icons: Array[TextureRect] = []
var _cell_counts: Array[Label] = []
var _cell_style: StyleBoxFlat
var _cell_style_active: StyleBoxFlat
var _preview_cache: Dictionary = {}

var _built: bool = false
var _paused: bool = false
var _dig_ratio: float = 0.0
var _toast_left: float = 0.0
var _loading_active: bool = true
var _loading_tick: float = 0.0
var _idle_time: float = 0.0
var _fps_tick: float = 0.0


func _ready() -> void:
	_build()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

func setup(world: VoxelWorld, player: Player, inventory: Inventory, interaction: Interaction, sky: SkyController) -> void:
	_build()
	_world = world
	_player = player
	_inventory = inventory
	_interaction = interaction
	_sky = sky

	if inventory != null:
		if not inventory.selection_changed.is_connected(_on_selection_changed):
			inventory.selection_changed.connect(_on_selection_changed)
		if not inventory.changed.is_connected(_on_inventory_changed):
			inventory.changed.connect(_on_inventory_changed)
	if interaction != null:
		if not interaction.dig_progress.is_connected(_on_dig_progress):
			interaction.dig_progress.connect(_on_dig_progress)
	if player != null:
		if not player.entered_water.is_connected(_on_entered_water):
			player.entered_water.connect(_on_entered_water)
		if not player.left_water.is_connected(_on_left_water):
			player.left_water.connect(_on_left_water)
	if world != null:
		if not world.initial_load_finished.is_connected(_on_initial_load_finished):
			world.initial_load_finished.connect(_on_initial_load_finished)
	else:
		_hide_loading()

	_debug.setup(world, player, interaction, sky)
	_refresh_hotbar()
	_update_loading_text()


## Short message just above the hotbar. Also used for the selected block name.
func show_toast(text: String, seconds: float = 1.6) -> void:
	_build()
	if text.is_empty():
		return
	_toast_label.text = text
	_toast_left = maxf(seconds, 0.1)
	_toast_panel.modulate = Color(1.0, 1.0, 1.0, 1.0)
	_toast_row.visible = not _paused


func set_paused(paused: bool) -> void:
	_build()
	_paused = paused
	_crosshair.visible = not paused
	_dig_ring.visible = not paused and _dig_ratio > 0.0
	_hotbar_panel.modulate = Color(1.0, 1.0, 1.0, 0.45 if paused else 1.0)
	if paused:
		_toast_row.visible = false
	elif _toast_left > 0.0:
		_toast_row.visible = true


## Applies display preferences immediately after the Game autoload changes.
func refresh_settings() -> void:
	if not _built or _fps_label == null:
		return
	var game := get_node_or_null(^"/root/Game")
	var wants_fps := game != null and bool(game.get("show_fps"))
	# F3 already includes FPS in its first line, so avoid drawing two counters
	# on top of one another in the same corner.
	_fps_label.visible = wants_fps and (_debug == null or not _debug.visible)
	if _fps_label.visible:
		_update_fps()
	# Hearts only matter in survival: creative ignores damage entirely.
	if _hearts != null:
		_hearts.visible = game != null and not bool(game.get("creative"))


## Survival health display, wired to Player.health_changed by main.
func set_health(current: int, maximum: int) -> void:
	_build()
	_hearts.set_health(current, maximum)


## Short red flash over the whole view when the player takes a hit.
func flash_damage() -> void:
	_build()
	_hurt_flash = 0.35
	_hurt_veil.visible = true
	_hurt_veil.modulate = Color(1.0, 1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Frame update, kept to the two things that really need it
# ---------------------------------------------------------------------------

func _process(delta: float) -> void:
	if _fps_label != null and _fps_label.visible:
		_fps_tick -= delta
		if _fps_tick <= 0.0:
			_fps_tick = FPS_TICK
			_update_fps()
	if _toast_left > 0.0:
		_toast_left -= delta
		if _toast_left <= 0.0:
			_toast_left = 0.0
			_toast_row.visible = false
		elif _toast_left < TOAST_FADE:
			_toast_panel.modulate = Color(1.0, 1.0, 1.0, _toast_left / TOAST_FADE)

	if _hurt_flash > 0.0:
		_hurt_flash -= delta
		if _hurt_flash <= 0.0:
			_hurt_veil.visible = false
		else:
			_hurt_veil.modulate = Color(1.0, 1.0, 1.0, _hurt_flash / 0.35)

	if _loading_active:
		_loading_tick -= delta
		if _loading_tick <= 0.0:
			_loading_tick = LOADING_TICK
			_update_loading_text()


# ---------------------------------------------------------------------------
# Signal handlers
# ---------------------------------------------------------------------------

func _on_selection_changed(slot: int) -> void:
	_update_selection(slot)
	if _inventory != null:
		var id := _inventory.selected_block()
		if id != Blocks.AIR:
			show_toast(Items.display_name_any(id), 1.6)


func _on_inventory_changed() -> void:
	_refresh_hotbar()


func _on_dig_progress(ratio: float) -> void:
	_dig_ratio = clampf(ratio, 0.0, 1.0)
	_dig_ring.set_ratio(_dig_ratio)
	_dig_ring.visible = not _paused and _dig_ratio > 0.0


func _on_entered_water() -> void:
	_veil.visible = true


func _on_left_water() -> void:
	_veil.visible = false


func _on_initial_load_finished() -> void:
	_hide_loading()


# ---------------------------------------------------------------------------
# Hotbar
# ---------------------------------------------------------------------------

func _refresh_hotbar() -> void:
	if _inventory == null:
		return
	var creative: bool = _inventory.creative
	for slot in Inventory.HOTBAR_SLOTS:
		var id := _inventory.slot_block(slot)
		var icon := _cell_icons[slot]
		if id == Blocks.AIR:
			icon.texture = null
		else:
			icon.texture = _preview_of(id)
		var count_label := _cell_counts[slot]
		var count := _inventory.slot_count(slot)
		if creative or id == Blocks.AIR or count <= 1:
			count_label.visible = false
		else:
			count_label.visible = true
			count_label.text = str(count)
	_update_selection(_inventory.selected)


func _update_selection(slot: int) -> void:
	var active := clampi(slot, 0, Inventory.HOTBAR_SLOTS - 1)
	for i in _cells.size():
		var style := _cell_style_active if i == active else _cell_style
		_cells[i].add_theme_stylebox_override("panel", style)
		_cell_icons[i].modulate = Color(1.0, 1.0, 1.0, 1.0 if i == active else 0.82)


## Previews are expensive to paint, so each one is generated once. Items and
## blocks both go through the Items dispatcher.
func _preview_of(block_id: int) -> Texture2D:
	if _preview_cache.has(block_id):
		return _preview_cache[block_id] as Texture2D
	var tex := Items.preview_any(block_id, PREVIEW_PX)
	_preview_cache[block_id] = tex
	return tex


# ---------------------------------------------------------------------------
# Loading message
# ---------------------------------------------------------------------------

func _update_loading_text() -> void:
	if not _loading_active:
		return
	if _world == null:
		_hide_loading()
		return
	var pending := _world.pending_jobs()
	if pending > 0:
		_idle_time = 0.0
	else:
		_idle_time += LOADING_TICK
		if _idle_time >= LOADING_GRACE:
			_hide_loading()
			return
	_loading_row.visible = true
	if pending == 1:
		_loading_count.text = "1 chunk restant"
	else:
		_loading_count.text = "%d chunks restants" % pending


func _hide_loading() -> void:
	_loading_active = false
	if _loading_row != null:
		_loading_row.visible = false


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

func _build() -> void:
	if _built:
		return
	_built = true
	layer = 2

	_root = Control.new()
	_root.name = "HudRoot"
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_full_rect(_root)
	add_child(_root)

	_build_veil()
	_build_crosshair()
	_build_hotbar()
	_build_hearts()
	_build_toast()
	_build_loading()
	_build_fps()

	_debug = DebugOverlay.new()
	_debug.name = "DebugOverlay"
	_root.add_child(_debug)
	refresh_settings()


func _build_fps() -> void:
	_fps_label = Label.new()
	_fps_label.name = "FpsCounter"
	_fps_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fps_label.position = Vector2(12.0, 10.0)
	_fps_label.text = "0 FPS"
	_style_label(_fps_label, 18, TEXT_MAIN)
	_fps_label.visible = false
	_root.add_child(_fps_label)


func _update_fps() -> void:
	_fps_label.text = "%d FPS" % roundi(Performance.get_monitor(Performance.TIME_FPS))


func _build_veil() -> void:
	_veil = ColorRect.new()
	_veil.name = "WaterVeil"
	_veil.color = Color(0.13, 0.34, 0.58, 0.30)
	_veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_veil.visible = false
	_full_rect(_veil)
	_root.add_child(_veil)

	_hurt_veil = ColorRect.new()
	_hurt_veil.name = "HurtVeil"
	_hurt_veil.color = Color(0.72, 0.08, 0.08, 0.30)
	_hurt_veil.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hurt_veil.visible = false
	_full_rect(_hurt_veil)
	_root.add_child(_hurt_veil)


## Hearts sit just above the hotbar, aligned with its left edge.
func _build_hearts() -> void:
	var total_w := Inventory.HOTBAR_SLOTS * CELL_PX + (Inventory.HOTBAR_SLOTS - 1) * CELL_GAP + 2 * PANEL_PAD
	var total_h := CELL_PX + 2 * PANEL_PAD
	var hearts_w := 10.0 * (Hearts.HEART_W * Hearts.PIXEL + Hearts.GAP)
	var hearts_h := Hearts.HEART_H * Hearts.PIXEL
	_hearts = Hearts.new()
	_hearts.name = "Hearts"
	_hearts.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hearts.anchor_left = 0.5
	_hearts.anchor_right = 0.5
	_hearts.anchor_top = 1.0
	_hearts.anchor_bottom = 1.0
	_hearts.offset_left = -total_w * 0.5 + PANEL_PAD
	_hearts.offset_right = -total_w * 0.5 + PANEL_PAD + hearts_w
	_hearts.offset_top = -float(HOTBAR_MARGIN + total_h) - hearts_h - 8.0
	_hearts.offset_bottom = -float(HOTBAR_MARGIN + total_h) - 8.0
	_hearts.visible = false
	_root.add_child(_hearts)


func _build_crosshair() -> void:
	_dig_ring = DigRing.new()
	_dig_ring.name = "DigRing"
	_dig_ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_dig_ring.visible = false
	_centre_rect(_dig_ring, RING_PX, RING_PX)
	_root.add_child(_dig_ring)

	_crosshair = Crosshair.new()
	_crosshair.name = "Crosshair"
	_crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_centre_rect(_crosshair, CROSSHAIR_PX, CROSSHAIR_PX)
	_root.add_child(_crosshair)


func _build_hotbar() -> void:
	_cell_style = _panel_style(PANEL_BG, PANEL_BORDER)
	_cell_style_active = _panel_style(PANEL_BG_ACTIVE, PANEL_BORDER_ACTIVE)

	var total_w := Inventory.HOTBAR_SLOTS * CELL_PX + (Inventory.HOTBAR_SLOTS - 1) * CELL_GAP + 2 * PANEL_PAD
	var total_h := CELL_PX + 2 * PANEL_PAD

	_hotbar_panel = PanelContainer.new()
	_hotbar_panel.name = "Hotbar"
	_hotbar_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_hotbar_panel.add_theme_stylebox_override("panel", _panel_style(PANEL_BG, PANEL_BORDER))
	_hotbar_panel.anchor_left = 0.5
	_hotbar_panel.anchor_right = 0.5
	_hotbar_panel.anchor_top = 1.0
	_hotbar_panel.anchor_bottom = 1.0
	_hotbar_panel.offset_left = -total_w * 0.5
	_hotbar_panel.offset_right = total_w * 0.5
	_hotbar_panel.offset_top = -float(HOTBAR_MARGIN + total_h)
	_hotbar_panel.offset_bottom = -float(HOTBAR_MARGIN)
	_root.add_child(_hotbar_panel)

	var row := HBoxContainer.new()
	row.name = "Cells"
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_theme_constant_override("separation", CELL_GAP)
	_hotbar_panel.add_child(row)

	for slot in Inventory.HOTBAR_SLOTS:
		row.add_child(_build_cell(slot))


func _build_cell(slot: int) -> Panel:
	var cell := Panel.new()
	cell.name = "Cell%d" % slot
	cell.custom_minimum_size = Vector2(CELL_PX, CELL_PX)
	cell.mouse_filter = Control.MOUSE_FILTER_IGNORE
	cell.add_theme_stylebox_override("panel", _cell_style)

	var icon := TextureRect.new()
	icon.name = "Icon"
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_full_rect(icon, 6.0)
	cell.add_child(icon)

	var key := Label.new()
	key.name = "Key"
	key.text = str(slot + 1)
	key.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_style_label(key, 10, TEXT_DIM)
	key.anchor_left = 0.0
	key.anchor_right = 0.0
	key.anchor_top = 0.0
	key.anchor_bottom = 0.0
	key.offset_left = 4.0
	key.offset_top = 1.0
	key.offset_right = 18.0
	key.offset_bottom = 15.0
	cell.add_child(key)

	var count := Label.new()
	count.name = "Count"
	count.mouse_filter = Control.MOUSE_FILTER_IGNORE
	count.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_style_label(count, 12, TEXT_MAIN)
	count.anchor_left = 0.0
	count.anchor_right = 1.0
	count.anchor_top = 1.0
	count.anchor_bottom = 1.0
	count.offset_left = 2.0
	count.offset_right = -4.0
	count.offset_top = -17.0
	count.offset_bottom = -2.0
	count.visible = false
	cell.add_child(count)

	_cells.append(cell)
	_cell_icons.append(icon)
	_cell_counts.append(count)
	return cell


func _build_toast() -> void:
	var total_h := CELL_PX + 2 * PANEL_PAD

	_toast_row = CenterContainer.new()
	_toast_row.name = "ToastRow"
	_toast_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_row.anchor_left = 0.0
	_toast_row.anchor_right = 1.0
	_toast_row.anchor_top = 1.0
	_toast_row.anchor_bottom = 1.0
	_toast_row.offset_top = -float(HOTBAR_MARGIN + total_h + 44)
	_toast_row.offset_bottom = -float(HOTBAR_MARGIN + total_h + 8)
	_toast_row.visible = false
	_root.add_child(_toast_row)

	_toast_panel = PanelContainer.new()
	_toast_panel.name = "Toast"
	_toast_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := _panel_style(PANEL_BG, PANEL_BORDER)
	style.content_margin_left = 14.0
	style.content_margin_right = 14.0
	style.content_margin_top = 5.0
	style.content_margin_bottom = 5.0
	_toast_panel.add_theme_stylebox_override("panel", style)
	_toast_row.add_child(_toast_panel)

	_toast_label = Label.new()
	_toast_label.name = "Text"
	_toast_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_label(_toast_label, 17, TEXT_MAIN)
	_toast_panel.add_child(_toast_label)


func _build_loading() -> void:
	_loading_row = CenterContainer.new()
	_loading_row.name = "LoadingRow"
	_loading_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_full_rect(_loading_row)
	_root.add_child(_loading_row)

	var panel := PanelContainer.new()
	panel.name = "Loading"
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := _panel_style(PANEL_BG, PANEL_BORDER)
	style.content_margin_left = 26.0
	style.content_margin_right = 26.0
	style.content_margin_top = 16.0
	style.content_margin_bottom = 16.0
	panel.add_theme_stylebox_override("panel", style)
	_loading_row.add_child(panel)

	var box := VBoxContainer.new()
	box.name = "Lines"
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	box.add_theme_constant_override("separation", 6)
	panel.add_child(box)

	_loading_title = Label.new()
	_loading_title.name = "Title"
	_loading_title.text = "Génération du monde..."
	_loading_title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_loading_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_label(_loading_title, 22, TEXT_MAIN)
	box.add_child(_loading_title)

	_loading_count = Label.new()
	_loading_count.name = "Count"
	_loading_count.text = "Préparation..."
	_loading_count.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_loading_count.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_label(_loading_count, 15, TEXT_DIM)
	box.add_child(_loading_count)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

func _panel_style(bg: Color, border: Color) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = bg
	style.border_color = border
	style.set_border_width_all(BORDER_PX)
	style.set_corner_radius_all(0)
	style.content_margin_left = PANEL_PAD
	style.content_margin_right = PANEL_PAD
	style.content_margin_top = PANEL_PAD
	style.content_margin_bottom = PANEL_PAD
	return style


func _style_label(label: Label, font_size: int, colour: Color) -> void:
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", colour)
	label.add_theme_color_override("font_outline_color", OUTLINE_COLOR)
	label.add_theme_constant_override("outline_size", 4)


func _full_rect(ctrl: Control, margin: float = 0.0) -> void:
	ctrl.anchor_left = 0.0
	ctrl.anchor_top = 0.0
	ctrl.anchor_right = 1.0
	ctrl.anchor_bottom = 1.0
	ctrl.offset_left = margin
	ctrl.offset_top = margin
	ctrl.offset_right = -margin
	ctrl.offset_bottom = -margin


func _centre_rect(ctrl: Control, width: float, height: float) -> void:
	ctrl.anchor_left = 0.5
	ctrl.anchor_top = 0.5
	ctrl.anchor_right = 0.5
	ctrl.anchor_bottom = 0.5
	ctrl.offset_left = -width * 0.5
	ctrl.offset_top = -height * 0.5
	ctrl.offset_right = width * 0.5
	ctrl.offset_bottom = height * 0.5
