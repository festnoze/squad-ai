class_name DebugOverlay
extends Control
## Diagnostic panel pinned to the top left corner, toggled by the
## `debug_overlay` action (F3) and hidden by default.
##
## Cost matters: the text is rebuilt about six times per second from a Timer,
## never once per frame, and nothing at all happens while the panel is hidden.
## Every reading is guarded, so a missing world, player or target only removes
## one line instead of raising an error.

const REFRESH_HZ := 6.0
const LABEL_WIDTH := 340.0
const MARGIN := 12.0

const PANEL_BG := Color(0.06, 0.07, 0.09, 0.78)
const PANEL_BORDER := Color(0.85, 0.88, 0.92, 0.25)
const TEXT_MAIN := Color(0.94, 0.96, 0.98)
const OUTLINE_COLOR := Color(0.02, 0.02, 0.03, 0.85)
const BORDER_PX := 2
const PANEL_PAD := 8.0

var _world: VoxelWorld
var _player: Player
var _interaction: Interaction
var _sky: SkyController

var _panel: PanelContainer
var _label: Label
var _timer: Timer

## The Game autoload, resolved by path instead of by its global identifier so
## this module also compiles under `--check-only`, where no SceneTree exists and
## autoload globals are therefore never registered.
var _game: Node

## Last hit reported by Interaction.target_changed. Empty when nothing is aimed at.
var _target: Dictionary = {}
var _built: bool = false


func _ready() -> void:
	_build()
	visible = bool(_read_setting(&"show_debug", false))
	if visible:
		_refresh()


func setup(world: VoxelWorld, player: Player, interaction: Interaction, sky: SkyController) -> void:
	_build()
	_world = world
	_player = player
	_interaction = interaction
	_sky = sky
	if interaction != null and not interaction.target_changed.is_connected(_on_target_changed):
		interaction.target_changed.connect(_on_target_changed)
	if visible:
		_refresh()


func _input(event: InputEvent) -> void:
	if not InputMap.has_action("debug_overlay"):
		return
	if not event.is_action_pressed("debug_overlay"):
		return
	visible = not visible
	_write_setting(&"show_debug", visible)
	if visible:
		_refresh()


## Reads a property of the Game autoload, falling back when it is absent.
func _read_setting(key: StringName, fallback: Variant) -> Variant:
	var game := _game_node()
	if game == null:
		return fallback
	var value: Variant = game.get(key)
	return fallback if value == null else value


func _write_setting(key: StringName, value: Variant) -> void:
	var game := _game_node()
	if game != null:
		game.set(key, value)


func _game_node() -> Node:
	if _game == null and is_inside_tree():
		_game = get_tree().root.get_node_or_null(^"Game")
	return _game


func _on_target_changed(hit: Dictionary) -> void:
	_target = hit


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

func _on_timer() -> void:
	if not visible:
		return
	_refresh()


func _refresh() -> void:
	var lines := PackedStringArray()
	lines.append(_header())
	lines.append(_row("Position", _position_text()))
	lines.append(_row("Chunk", _chunk_text()))
	lines.append(_row("Biome", _biome_text()))
	lines.append(_row("Visé", _target_text()))
	lines.append(_row("Monde", _world_text()))
	lines.append(_row("Heure", _time_text()))
	lines.append(_row("Mode", _mode_text()))
	lines.append(_row("Rendu", _render_text()))
	_label.text = "\n".join(lines)


func _header() -> String:
	var fps: float = Performance.get_monitor(Performance.TIME_FPS)
	var frame_ms: float = Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
	return "CUBEFORGE  %d ips  (%.1f ms)" % [int(roundf(fps)), frame_ms]


func _row(label: String, value: String) -> String:
	return "%-9s %s" % [label, value]


## The player is only asked for its transform while it really sits in the tree,
## otherwise Node3D complains once per refresh.
func _has_player() -> bool:
	return _player != null and _player.is_inside_tree()


func _position_text() -> String:
	if not _has_player():
		return "-"
	var p := _player.global_position
	return "%.2f  %.2f  %.2f" % [p.x, p.y, p.z]


func _chunk_text() -> String:
	if not _has_player():
		return "-"
	var p := _player.global_position
	var wx := floori(p.x)
	var wz := floori(p.z)
	var cx := VoxelWorld.chunk_of(wx)
	var cz := VoxelWorld.chunk_of(wz)
	return "(%d, %d)  local (%d, %d)" % [cx, cz, VoxelWorld.local_of(wx), VoxelWorld.local_of(wz)]


func _biome_text() -> String:
	if _world == null or not _has_player():
		return "-"
	var p := _player.global_position
	var wx := floori(p.x)
	var wz := floori(p.z)
	var ground := _world.surface_height(wx, wz)
	return "%s  (sol y %d)" % [_world.biome_name_at(wx, wz), ground]


func _target_text() -> String:
	if not bool(_target.get("hit", false)):
		return "rien"
	var id := int(_target.get("id", Blocks.AIR))
	if id < 0 or id >= Blocks.COUNT:
		return "rien"
	var cell: Vector3i = _target.get("cell", Vector3i.ZERO)
	var distance := float(_target.get("distance", 0.0))
	return "%s  (%d, %d, %d)  a %.1f m" % [Blocks.display_name(id), cell.x, cell.y, cell.z, distance]


func _world_text() -> String:
	if _world == null:
		return "-"
	return "%d chunks chargés, %d en attente" % [_world.loaded_chunk_count(), _world.pending_jobs()]


func _time_text() -> String:
	if _sky == null:
		return "-"
	var phase := "nuit" if _sky.is_night() else "jour"
	return "%s  (%s)" % [_sky.time_string(), phase]


func _mode_text() -> String:
	var parts := PackedStringArray()
	parts.append("créatif" if bool(_read_setting(&"creative", true)) else "survie")
	if _player != null:
		if _player.fly_mode:
			parts.append("vol")
		if _player.in_water:
			parts.append("dans l'eau")
		elif _player.on_floor():
			parts.append("au sol")
		else:
			parts.append("en l'air")
		parts.append("%.1f u/s" % _player.horizontal_speed())
	return ", ".join(parts)


func _render_text() -> String:
	var prims: float = Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
	var vram: float = Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED)
	return "%s prim., VRAM %.0f Mo" % [_grouped(int(prims)), vram / 1048576.0]


## Thousands separated with a plain space, easier to read at a glance.
func _grouped(value: int) -> String:
	var digits := str(absi(value))
	var out := ""
	var count := 0
	for i in range(digits.length() - 1, -1, -1):
		out = digits[i] + out
		count += 1
		if count % 3 == 0 and i > 0:
			out = " " + out
	return ("-" + out) if value < 0 else out


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

func _build() -> void:
	if _built:
		return
	_built = true

	name = "DebugOverlay"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Keep reporting while the tree is paused by the pause menu.
	process_mode = Node.PROCESS_MODE_ALWAYS
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	offset_left = 0.0
	offset_top = 0.0
	offset_right = 0.0
	offset_bottom = 0.0
	visible = false

	_panel = PanelContainer.new()
	_panel.name = "Panel"
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel.add_theme_stylebox_override("panel", _panel_style())
	# Anchored to the top left corner with a zero sized box: the container
	# minimum size then drives the real size, so a longer line never clips.
	_panel.anchor_left = 0.0
	_panel.anchor_top = 0.0
	_panel.anchor_right = 0.0
	_panel.anchor_bottom = 0.0
	_panel.offset_left = MARGIN
	_panel.offset_top = MARGIN
	_panel.offset_right = MARGIN
	_panel.offset_bottom = MARGIN
	add_child(_panel)

	_label = Label.new()
	_label.name = "Text"
	_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	_label.custom_minimum_size = Vector2(LABEL_WIDTH, 0.0)
	_label.label_settings = _mono_settings()
	_label.text = "CUBEFORGE"
	_panel.add_child(_label)

	_timer = Timer.new()
	_timer.name = "Refresh"
	_timer.wait_time = 1.0 / REFRESH_HZ
	_timer.one_shot = false
	_timer.autostart = true
	_timer.timeout.connect(_on_timer)
	add_child(_timer)


func _panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = PANEL_BG
	style.border_color = PANEL_BORDER
	style.set_border_width_all(BORDER_PX)
	style.set_corner_radius_all(0)
	style.content_margin_left = PANEL_PAD
	style.content_margin_right = PANEL_PAD
	style.content_margin_top = PANEL_PAD
	style.content_margin_bottom = PANEL_PAD
	return style


## Monospace keeps the columns still while the numbers change. No font file is
## shipped: a SystemFont picks a fixed pitch family already installed, and falls
## back to the engine default when none of them answers.
func _mono_settings() -> LabelSettings:
	var settings := LabelSettings.new()
	var mono := SystemFont.new()
	mono.font_names = PackedStringArray([
		"Consolas", "DejaVu Sans Mono", "Liberation Mono",
		"Courier New", "monospace",
	])
	mono.allow_system_fallback = true
	settings.font = mono
	settings.font_size = 14
	settings.font_color = TEXT_MAIN
	settings.outline_size = 4
	settings.outline_color = OUTLINE_COLOR
	settings.line_spacing = 2.0
	return settings
