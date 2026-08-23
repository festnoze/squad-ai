## CALL OF WAR - in game head up display.
##
## Art direction: 1942 military paperwork. Washed out khaki, black ink, red
## rubber stamps, typewriter capitals. The in game layer stays DISCREET: a war
## FPS is played by looking at the world, not at gauges, so every widget is
## semi transparent and any element that has not changed for five seconds fades
## back to a whisper.
##
## Everything is drawn from code. Two full screen painters sandwich the widget
## layer: `_back` carries the vignette, the dynamic crosshair, the damage arcs
## and the hitmarker, `_front` carries the scope mask and the death fade so
## they cover the labels.
class_name Hud
extends CanvasLayer

# --- Paper palette -----------------------------------------------------------

const _PAPER := Color(0.86, 0.83, 0.71)
const _PAPER_DIM := Color(0.72, 0.69, 0.58)
const _INK := Color(0.05, 0.05, 0.04)
const _STAMP := Color(0.72, 0.16, 0.12)
const _KHAKI := Color(0.42, 0.42, 0.29)

## Seconds a widget stays at full opacity after its last change.
const _HOLD_SECONDS := 5.0
## Seconds the fade down to the resting opacity takes.
const _FADE_SECONDS := 1.4
## Resting opacity of an untouched widget.
const _REST_ALPHA := 0.42

const _DAMAGE_MARK_LIFE := 1.5
const _HITMARKER_LIFE := 0.26
const _BANNER_FADE := 0.45
## Compass half span in degrees.
const _COMPASS_SPAN := 60.0

const _CARDINALS: PackedStringArray = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
const _BIOME_NAMES: PackedStringArray = [
	"Champ", "Prairie", "Foret", "Marais", "Route", "Village", "Eau", "Roche", "Verger",
]


## A bare Control that forwards `_draw` to a callable. Lets the HUD own several
## independent painting layers without one script file per layer.
class _Painter:
	extends Control

	var painter: Callable = Callable()

	func _draw() -> void:
		if painter.is_valid():
			painter.call(self)


# --- Wiring ------------------------------------------------------------------

var _player: Player = null
var _tracker: ObjectiveTracker = null
var _sky: SkyController = null
var _weather: Weather = null
var _world: GameWorld = null

# --- Layers ------------------------------------------------------------------

var _back: _Painter = null
var _front: _Painter = null
var _root: Control = null
var _gameplay: Control = null
var _overlay: Control = null

# --- Widgets -----------------------------------------------------------------

var _compass: _Painter = null
var _obj_box: VBoxContainer = null
var _obj_title: Label = null
var _obj_desc: Label = null
var _obj_progress: Label = null
var _obj_timer: Label = null
var _ammo_box: VBoxContainer = null
var _weapon_label: Label = null
var _mag_label: Label = null
var _reserve_label: Label = null
var _grenade_label: Label = null
var _health_label: Label = null
var _alert_label: Label = null
var _prompt_label: Label = null
var _toast_box: VBoxContainer = null
var _banner_box: VBoxContainer = null
var _banner_title: Label = null
var _banner_sub: Label = null
var _fps_label: Label = null
var _debug_label: Label = null
var _death_box: VBoxContainer = null
var _death_hint: Label = null

# --- Runtime state -----------------------------------------------------------

var _time: float = 0.0
var _paused: bool = false
var _dead: bool = false
var _death_t: float = 0.0

var _health: float = 100.0
var _health_max: float = 100.0
var _bandages: int = 0

var _spread_rad: float = 0.02
var _is_aiming: bool = false
var _has_scope: bool = false
var _scope_t: float = 0.0

var _hitmarker_t: float = 0.0
var _hit_killed: bool = false
var _hit_headshot: bool = false

## Each entry: {"dir": Vector3, "t": float}.
var _damage_marks: Array[Dictionary] = []
## Each entry: {"label": Label, "t": float, "life": float}.
var _toasts: Array[Dictionary] = []

var _banner_t: float = 0.0
var _banner_life: float = 0.0

var _prompt_override: String = ""
var _prompt_probed: bool = false
var _prompt_available: bool = false

## Objective id -> seconds elapsed since it started, for the countdown.
var _obj_elapsed: Dictionary = {}

# Timestamps of the last meaningful change, used by the fade out.
var _t_ammo: float = -999.0
var _t_health: float = -999.0
var _t_objective: float = -999.0
var _t_alert: float = -999.0

var _debug_accum: float = 0.0
var _debug_cache: String = ""

static var _font_cache: Dictionary = {}


func _ready() -> void:
	# Leave `layer` alone: the HUD sits on the default canvas layer, and the
	# `Screens` CanvasLayer that follows it in the scene tree draws above it.
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build()
	refresh_settings()


func _process(delta: float) -> void:
	_time += delta
	_tick_timers(delta)
	if not _paused:
		_refresh_gameplay(delta)
	_refresh_overlay(delta)
	_back.queue_redraw()
	_front.queue_redraw()
	_compass.queue_redraw()


# =============================================================================
# Public API (contract 2.34)
# =============================================================================

func setup(player_node: Player, tracker: ObjectiveTracker, sky_ctl: SkyController,
		weather_node: Weather, game_world: GameWorld) -> void:
	_player = player_node
	_tracker = tracker
	_sky = sky_ctl
	_weather = weather_node
	_world = game_world

	if _player != null:
		_health_max = maxf(1.0, float(Player.MAX_HEALTH))
		_health = _player.health
		_bandages = _player.bandages
		_connect(_player, "health_changed", _on_health_changed)
		_connect(_player, "died", _on_player_died)
		_connect(_player, "weapon_changed", _on_weapon_changed)
		_connect(_player, "ammo_changed", _on_ammo_changed)
		_connect(_player, "damaged", _on_player_damaged)
		_connect(_player, "bandages_changed", _on_bandages_changed)
	if _tracker != null:
		_connect(_tracker, "objective_started", _on_objective_started)
		_connect(_tracker, "objective_progress", _on_objective_progress)
		_connect(_tracker, "objective_completed", _on_objective_completed)
		_connect(_tracker, "objective_failed", _on_objective_failed)
		_connect(_tracker, "campaign_completed", _on_campaign_completed)
	_connect(War, "sector_captured", _on_sector_captured)
	_connect(War, "alert_changed", _on_alert_changed)
	_connect(Game, "settings_changed", refresh_settings)

	_dead = false
	_death_t = 0.0
	_death_box.visible = false
	_death_hint.text = "Appuyez sur %s pour reprendre le combat." % _action_key_label("use")
	_touch_all()
	refresh_settings()


## Small stacked message in the top right corner.
func show_toast(text: String, seconds: float = 2.2) -> void:
	if text.strip_edges().is_empty():
		return
	var label := Label.new()
	label.text = text.to_upper()
	_style_label(label, 15, _PAPER, 1)
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_toast_box.add_child(label)
	_toasts.append({"label": label, "t": 0.0, "life": maxf(0.4, seconds)})
	while _toasts.size() > 6:
		_drop_toast(0)


## Big centred banner, for a captured sector or a failed mission.
func show_banner(title: String, subtitle: String, seconds: float = 3.5) -> void:
	_banner_title.text = title.to_upper()
	_banner_sub.text = subtitle
	_banner_life = maxf(0.6, seconds)
	_banner_t = 0.0
	_banner_box.visible = true
	_banner_box.modulate.a = 0.0


func flash_damage(from_direction: Vector3) -> void:
	var dir := from_direction
	dir.y = 0.0
	if dir.length_squared() < 0.0001:
		dir = Vector3(0.0, 0.0, -1.0)
	_damage_marks.append({"dir": dir.normalized(), "t": 0.0})
	while _damage_marks.size() > 8:
		_damage_marks.remove_at(0)
	_t_health = _time


func flash_hitmarker(killed: bool, headshot: bool) -> void:
	_hitmarker_t = _HITMARKER_LIFE
	_hit_killed = killed
	_hit_headshot = headshot
	var pitch := 1.85
	if killed:
		pitch = 1.25
	if headshot:
		pitch += 0.25
	_play("ui_click", -6.0, pitch)


func set_paused(paused: bool) -> void:
	_paused = paused
	_gameplay.visible = not paused
	_back.visible = not paused


## "" hides the action prompt.
func set_prompt(text: String) -> void:
	_prompt_override = text


func refresh_settings() -> void:
	if _fps_label == null:
		return
	_fps_label.visible = bool(Game.show_fps)
	_debug_label.visible = bool(Game.show_debug)


# =============================================================================
# Construction
# =============================================================================

func _build() -> void:
	_back = _Painter.new()
	_back.name = "Back"
	_back.painter = Callable(self, "_draw_back")
	_full_rect(_back)
	add_child(_back)

	_root = Control.new()
	_root.name = "Widgets"
	_full_rect(_root)
	add_child(_root)

	_gameplay = Control.new()
	_gameplay.name = "Gameplay"
	_full_rect(_gameplay)
	_root.add_child(_gameplay)

	_overlay = Control.new()
	_overlay.name = "Overlay"
	_full_rect(_overlay)
	_root.add_child(_overlay)

	_front = _Painter.new()
	_front.name = "Front"
	_front.painter = Callable(self, "_draw_front")
	_full_rect(_front)
	add_child(_front)

	_build_compass()
	_build_objective()
	_build_ammo()
	_build_status()
	_build_prompt()
	_build_overlay()


func _full_rect(c: Control) -> void:
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	c.mouse_filter = Control.MOUSE_FILTER_IGNORE


func _build_compass() -> void:
	_compass = _Painter.new()
	_compass.name = "Compass"
	_compass.painter = Callable(self, "_draw_compass")
	_full_rect(_compass)
	_gameplay.add_child(_compass)


func _build_objective() -> void:
	_obj_box = VBoxContainer.new()
	_obj_box.name = "Objective"
	_obj_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_obj_box.set_anchors_preset(Control.PRESET_CENTER_LEFT)
	_obj_box.offset_left = 26.0
	_obj_box.offset_top = -46.0
	_obj_box.offset_right = 426.0
	_obj_box.offset_bottom = 120.0
	_obj_box.add_theme_constant_override("separation", 3)
	_gameplay.add_child(_obj_box)

	_obj_title = Label.new()
	_style_label(_obj_title, 18, _PAPER, 3)
	_obj_box.add_child(_obj_title)

	_obj_desc = Label.new()
	_style_label(_obj_desc, 13, _PAPER_DIM, 0)
	_obj_desc.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_obj_desc.custom_minimum_size = Vector2(400.0, 0.0)
	_obj_box.add_child(_obj_desc)

	_obj_progress = Label.new()
	_style_label(_obj_progress, 14, _KHAKI.lightened(0.35), 1)
	_obj_box.add_child(_obj_progress)

	_obj_timer = Label.new()
	_style_label(_obj_timer, 16, _STAMP, 2)
	_obj_box.add_child(_obj_timer)


func _build_ammo() -> void:
	_ammo_box = VBoxContainer.new()
	_ammo_box.name = "Ammo"
	_ammo_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ammo_box.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	_ammo_box.offset_left = -360.0
	_ammo_box.offset_top = -136.0
	_ammo_box.offset_right = -28.0
	_ammo_box.offset_bottom = -22.0
	_ammo_box.alignment = BoxContainer.ALIGNMENT_END
	_ammo_box.add_theme_constant_override("separation", 0)
	_gameplay.add_child(_ammo_box)

	_weapon_label = Label.new()
	_style_label(_weapon_label, 15, _PAPER_DIM, 3)
	_weapon_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_ammo_box.add_child(_weapon_label)

	var row := HBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	_ammo_box.add_child(row)

	var spacer := Control.new()
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)

	_mag_label = Label.new()
	_style_label(_mag_label, 46, _PAPER, 0)
	_mag_label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	row.add_child(_mag_label)

	_reserve_label = Label.new()
	_style_label(_reserve_label, 19, _PAPER_DIM, 0)
	_reserve_label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	row.add_child(_reserve_label)

	_grenade_label = Label.new()
	_style_label(_grenade_label, 14, _PAPER_DIM, 2)
	_grenade_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_ammo_box.add_child(_grenade_label)


func _build_status() -> void:
	_health_label = Label.new()
	_health_label.name = "Health"
	_style_label(_health_label, 14, _PAPER_DIM, 2)
	_health_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_health_label.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	_health_label.offset_left = 28.0
	_health_label.offset_top = -78.0
	_health_label.offset_right = 340.0
	_health_label.offset_bottom = -56.0
	_gameplay.add_child(_health_label)

	_alert_label = Label.new()
	_alert_label.name = "Alert"
	_style_label(_alert_label, 13, _KHAKI.lightened(0.4), 3)
	_alert_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_alert_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_alert_label.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_alert_label.offset_left = -340.0
	_alert_label.offset_top = 58.0
	_alert_label.offset_right = -26.0
	_alert_label.offset_bottom = 80.0
	_gameplay.add_child(_alert_label)


func _build_prompt() -> void:
	_prompt_label = Label.new()
	_prompt_label.name = "Prompt"
	_style_label(_prompt_label, 17, _PAPER, 2)
	_prompt_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_prompt_label.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_prompt_label.offset_left = -400.0
	_prompt_label.offset_top = -172.0
	_prompt_label.offset_right = 400.0
	_prompt_label.offset_bottom = -146.0
	_prompt_label.visible = false
	_gameplay.add_child(_prompt_label)


func _build_overlay() -> void:
	_toast_box = VBoxContainer.new()
	_toast_box.name = "Toasts"
	_toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_toast_box.alignment = BoxContainer.ALIGNMENT_BEGIN
	_toast_box.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_toast_box.offset_left = -440.0
	_toast_box.offset_top = 86.0
	_toast_box.offset_right = -26.0
	_toast_box.offset_bottom = 420.0
	_toast_box.add_theme_constant_override("separation", 4)
	_overlay.add_child(_toast_box)

	_banner_box = VBoxContainer.new()
	_banner_box.name = "Banner"
	_banner_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_banner_box.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_banner_box.offset_left = -540.0
	_banner_box.offset_top = 148.0
	_banner_box.offset_right = 540.0
	_banner_box.offset_bottom = 288.0
	_banner_box.add_theme_constant_override("separation", 6)
	_banner_box.visible = false
	_overlay.add_child(_banner_box)

	_banner_title = Label.new()
	_style_label(_banner_title, 44, _STAMP, 6)
	_banner_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner_box.add_child(_banner_title)

	_banner_sub = Label.new()
	_style_label(_banner_sub, 19, _PAPER, 2)
	_banner_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner_box.add_child(_banner_sub)

	_fps_label = Label.new()
	_fps_label.name = "Fps"
	_style_label(_fps_label, 13, _PAPER_DIM, 1)
	_fps_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fps_label.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_fps_label.offset_left = 26.0
	_fps_label.offset_top = 12.0
	_fps_label.offset_right = 300.0
	_fps_label.offset_bottom = 32.0
	_fps_label.visible = false
	_overlay.add_child(_fps_label)

	_debug_label = Label.new()
	_debug_label.name = "Debug"
	_style_label(_debug_label, 12, _PAPER_DIM, 0)
	_debug_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_debug_label.set_anchors_preset(Control.PRESET_TOP_LEFT)
	_debug_label.offset_left = 26.0
	_debug_label.offset_top = 34.0
	_debug_label.offset_right = 620.0
	_debug_label.offset_bottom = 260.0
	_debug_label.visible = false
	_overlay.add_child(_debug_label)

	_death_box = VBoxContainer.new()
	_death_box.name = "Death"
	_death_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_death_box.set_anchors_preset(Control.PRESET_CENTER)
	_death_box.offset_left = -540.0
	_death_box.offset_top = -72.0
	_death_box.offset_right = 540.0
	_death_box.offset_bottom = 72.0
	_death_box.add_theme_constant_override("separation", 14)
	_death_box.visible = false
	_overlay.add_child(_death_box)

	var death_title := Label.new()
	_style_label(death_title, 52, Color(0.80, 0.72, 0.62), 8)
	death_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	death_title.text = "TUÉ AU COMBAT"
	_death_box.add_child(death_title)

	_death_hint = Label.new()
	_style_label(_death_hint, 18, Color(0.70, 0.62, 0.54), 3)
	_death_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_death_hint.text = "Appuyez sur E pour reprendre le combat."
	_death_box.add_child(_death_hint)


## Applies the typewriter look: engine default font, extra glyph spacing, an ink
## coloured outline so pale text survives over a bright field.
func _style_label(label: Label, size: int, color: Color, spacing: int) -> void:
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.add_theme_color_override("font_shadow_color", Color(_INK.r, _INK.g, _INK.b, 0.8))
	label.add_theme_constant_override("shadow_offset_x", 1)
	label.add_theme_constant_override("shadow_offset_y", 1)
	label.add_theme_color_override("font_outline_color", Color(_INK.r, _INK.g, _INK.b, 0.72))
	label.add_theme_constant_override("outline_size", 3)
	var font := _spaced_font(spacing)
	if font != null:
		label.add_theme_font_override("font", font)


## Cached FontVariation over the engine fallback font. Extra glyph spacing is
## what sells the typewriter without shipping a font file.
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
# Per frame refresh
# =============================================================================

func _tick_timers(delta: float) -> void:
	_hitmarker_t = maxf(0.0, _hitmarker_t - delta)
	var keep: Array[Dictionary] = []
	for mark in _damage_marks:
		var age := float(mark["t"]) + delta
		if age < _DAMAGE_MARK_LIFE:
			mark["t"] = age
			keep.append(mark)
	_damage_marks = keep
	if _dead:
		_death_t += delta
	for key in _obj_elapsed.keys():
		_obj_elapsed[key] = float(_obj_elapsed[key]) + delta


func _refresh_gameplay(delta: float) -> void:
	_refresh_weapon(delta)
	_refresh_health()
	_refresh_objective()
	_refresh_alert()
	_refresh_prompt()


func _refresh_weapon(delta: float) -> void:
	var weapon: Weapon = null
	if _player != null:
		weapon = _player.current_weapon()
	_is_aiming = _player != null and _player.is_aiming
	if weapon == null:
		_weapon_label.text = "MAINS NUES"
		_mag_label.text = "-"
		_reserve_label.text = ""
		_spread_rad = 0.0
		_has_scope = false
	else:
		var moving := false
		var crouched := false
		if _player != null:
			moving = _player.velocity.length() > 0.6
			crouched = _player.stance > 0
		_is_aiming = _player != null and _player.is_aiming
		_spread_rad = weapon.current_spread(_is_aiming, moving, crouched)
		_has_scope = WeaponDefs.has_scope(weapon.id)
		_weapon_label.text = WeaponDefs.display_name(weapon.id).to_upper()
		_mag_label.text = str(weapon.in_magazine)
		_reserve_label.text = "/ %d" % weapon.reserve
		if weapon.is_reloading:
			_reserve_label.text = "RECHARGE"
		var empty := weapon.in_magazine <= 0 and not weapon.is_reloading
		if empty:
			var blink := 0.55 + 0.45 * sin(_time * 9.0)
			_mag_label.add_theme_color_override("font_color", _STAMP.lerp(_PAPER, blink))
		else:
			_mag_label.add_theme_color_override("font_color", _PAPER)
	_grenade_label.text = "GRENADES  %d" % _grenade_count()
	var target := 0.0
	if _has_scope and _is_aiming:
		target = 1.0
	_scope_t = move_toward(_scope_t, target, delta * 6.0)
	_ammo_box.modulate.a = _fade_alpha(_t_ammo)


func _refresh_health() -> void:
	if _player != null:
		_health = _player.health
		_bandages = _player.bandages
	_health_label.text = "BANDAGES  %d      %d PV" % [_bandages, int(round(_health))]
	if _health <= 30.0:
		_health_label.add_theme_color_override("font_color", _STAMP.lightened(0.15))
	else:
		_health_label.add_theme_color_override("font_color", _PAPER_DIM)
	_health_label.modulate.a = _fade_alpha(_t_health)


func _refresh_objective() -> void:
	var obj: MissionDefs.Objective = _current_objective()
	if obj == null:
		_obj_box.visible = false
		return
	_obj_box.visible = true
	_obj_title.text = "%s  %s" % [MissionDefs.kind_icon(obj.kind), obj.title.to_upper()]
	_obj_desc.text = obj.description
	var progress := Vector2.ZERO
	if _tracker != null:
		progress = _tracker.progress_of(obj.id)
	if progress.y > 0.0:
		_obj_progress.visible = true
		_obj_progress.text = "AVANCEMENT  %d / %d" % [int(progress.x), int(progress.y)]
	else:
		_obj_progress.visible = false
	if obj.time_limit > 0.0:
		var elapsed := float(_obj_elapsed.get(obj.id, 0.0))
		var left := maxf(0.0, obj.time_limit - elapsed)
		_obj_timer.visible = true
		_obj_timer.text = "TEMPS RESTANT  %s" % _clock(left)
		if left < 30.0:
			_obj_timer.add_theme_color_override("font_color", _STAMP.lightened(0.2))
		else:
			_obj_timer.add_theme_color_override("font_color", _KHAKI.lightened(0.4))
	else:
		_obj_timer.visible = false
	_obj_box.modulate.a = _fade_alpha(_t_objective)


func _refresh_alert() -> void:
	var level := int(War.alert_level)
	_alert_label.text = "ALERTE : %s" % String(War.alert_name()).to_upper()
	_alert_label.add_theme_color_override("font_color", _alert_color(level))
	var alpha := _fade_alpha(_t_alert)
	if level >= War.ALERT_SEARCHING:
		alpha = 1.0
	_alert_label.modulate.a = alpha


func _refresh_prompt() -> void:
	var text := _prompt_override
	if text.is_empty():
		text = _read_player_prompt()
	if text.strip_edges().is_empty():
		_prompt_label.visible = false
		return
	_prompt_label.visible = true
	_prompt_label.text = text


func _refresh_overlay(delta: float) -> void:
	_update_toasts(delta)
	_update_banner(delta)
	if _fps_label.visible:
		_fps_label.text = "%d IPS" % int(Engine.get_frames_per_second())
	if _debug_label.visible:
		_debug_accum += delta
		if _debug_accum > 0.25:
			_debug_accum = 0.0
			_debug_cache = _build_debug_text()
		_debug_label.text = _debug_cache


func _update_toasts(delta: float) -> void:
	var index := 0
	while index < _toasts.size():
		var entry := _toasts[index]
		var age := float(entry["t"]) + delta
		entry["t"] = age
		var life := float(entry["life"])
		var label := entry["label"] as Label
		if label == null or not is_instance_valid(label):
			_toasts.remove_at(index)
			continue
		if age >= life:
			_drop_toast(index)
			continue
		var fade_in := clampf(age / 0.18, 0.0, 1.0)
		var fade_out := clampf((life - age) / 0.5, 0.0, 1.0)
		label.modulate.a = minf(fade_in, fade_out)
		index += 1


func _drop_toast(index: int) -> void:
	if index < 0 or index >= _toasts.size():
		return
	var label := _toasts[index]["label"] as Label
	_toasts.remove_at(index)
	if label != null and is_instance_valid(label):
		label.queue_free()


func _update_banner(delta: float) -> void:
	if not _banner_box.visible:
		return
	_banner_t += delta
	if _banner_t >= _banner_life:
		_banner_box.visible = false
		return
	var fade_in := clampf(_banner_t / _BANNER_FADE, 0.0, 1.0)
	var fade_out := clampf((_banner_life - _banner_t) / _BANNER_FADE, 0.0, 1.0)
	_banner_box.modulate.a = minf(fade_in, fade_out)


func _build_debug_text() -> String:
	var lines: PackedStringArray = []
	if _world != null:
		lines.append(_world.debug_line())
	if _player != null:
		var pos := _player.global_position
		lines.append("POS  x %.1f  y %.1f  z %.1f" % [pos.x, pos.y, pos.z])
		if _world != null:
			var hf: Heightfield = _world.heightfield()
			if hf != null:
				lines.append("BIOME  %s   SOL %.1f m" % [
					_biome_name(hf.biome_at(pos.x, pos.z)), _world.ground_y(pos.x, pos.z)])
	if _sky != null:
		lines.append("HEURE  %s   LUMIERE %.2f" % [_sky.time_string(), _sky.light_level()])
	if _weather != null:
		lines.append("METEO  %s   %.0f%%" % [_weather.kind_name(), _weather.intensity * 100.0])
	lines.append("SOLDATS  axe %d   allies %d" % [
		get_tree().get_nodes_in_group("axis").size(),
		get_tree().get_nodes_in_group("allies").size()])
	lines.append("ALERTE %d   SECTEURS %d / %d" % [
		int(War.alert_level), War.captured_count(), War.sector_count()])
	return "\n".join(lines)


# =============================================================================
# Painting: back layer
# =============================================================================

func _draw_back(c: Control) -> void:
	var rect := Rect2(Vector2.ZERO, c.size)
	_draw_vignette(c, rect)
	_draw_health_bar(c, rect)
	_draw_damage_marks(c, rect)
	if _scope_t < 0.5 and not _is_aiming:
		_draw_crosshair(c, rect)
	_draw_hitmarker(c, rect)


## Red vignette creeping in from the borders as health drops. The radial
## gradient is approximated by concentric rectangle outlines, which costs a few
## dozen draw calls and needs no texture.
func _draw_vignette(c: Control, rect: Rect2) -> void:
	var missing := clampf(1.0 - _health / _health_max, 0.0, 1.0)
	# Nothing at all above 80 PV: a scratch must not paint the screen red.
	var strength := pow(clampf((missing - 0.20) / 0.80, 0.0, 1.0), 1.30)
	if strength <= 0.01:
		return
	if _health <= 30.0:
		strength *= 1.0 + 0.30 * sin(_time * 6.5)
	var rings := 22
	var reach := minf(rect.size.x, rect.size.y) * 0.34
	var step := reach / float(rings)
	for i in rings:
		var t := float(i) / float(rings - 1)
		var inset := t * reach
		var alpha := strength * pow(1.0 - t, 2.7) * 0.50
		if alpha <= 0.003:
			continue
		var band := Rect2(rect.position + Vector2(inset, inset),
				rect.size - Vector2(inset * 2.0, inset * 2.0))
		if band.size.x <= 2.0 or band.size.y <= 2.0:
			break
		c.draw_rect(band, Color(0.46, 0.03, 0.02, alpha), false, step + 1.0)


## Discreet health gauge, bottom left, under the bandage count.
func _draw_health_bar(c: Control, rect: Rect2) -> void:
	var alpha := _fade_alpha(_t_health)
	if alpha <= 0.02:
		return
	var frac := clampf(_health / _health_max, 0.0, 1.0)
	var origin := Vector2(rect.position.x + 28.0, rect.position.y + rect.size.y - 48.0)
	var full := Vector2(210.0, 5.0)
	c.draw_rect(Rect2(origin, full), Color(_INK.r, _INK.g, _INK.b, 0.55 * alpha), true)
	var tint := Color(0.42, 0.44, 0.28).lerp(Color(0.66, 0.14, 0.10), 1.0 - frac)
	tint.a = 0.85 * alpha
	c.draw_rect(Rect2(origin, Vector2(full.x * frac, full.y)), tint, true)
	c.draw_rect(Rect2(origin, full), Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.35 * alpha), false, 1.0)


## Peripheral red arc pointing at the source of the last hits.
func _draw_damage_marks(c: Control, rect: Rect2) -> void:
	if _damage_marks.is_empty():
		return
	var center := rect.position + rect.size * 0.5
	var radius := minf(rect.size.x, rect.size.y) * 0.32
	var facing := _player_heading_rad()
	for mark in _damage_marks:
		var age := float(mark["t"])
		var fade := 1.0 - clampf(age / _DAMAGE_MARK_LIFE, 0.0, 1.0)
		var dir := mark["dir"] as Vector3
		var bearing := atan2(dir.x, -dir.z)
		var relative := wrapf(bearing - facing, -PI, PI)
		var angle := relative - PI * 0.5
		var color := Color(0.78, 0.11, 0.08, 0.85 * fade)
		c.draw_arc(center, radius, angle - 0.24, angle + 0.24, 20, color, 8.0, true)
		c.draw_arc(center, radius + 7.0, angle - 0.14, angle + 0.14, 12,
				Color(0.95, 0.55, 0.35, 0.5 * fade), 3.0, true)


## Four ticks opening with the weapon spread cone.
func _draw_crosshair(c: Control, rect: Rect2) -> void:
	if _dead:
		return
	var center := rect.position + rect.size * 0.5
	var gap := 5.0 + _spread_pixels(rect.size.y)
	gap = minf(gap, minf(rect.size.x, rect.size.y) * 0.42)
	var length := 9.0
	var color := Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.78)
	var shade := Color(_INK.r, _INK.g, _INK.b, 0.55)
	var dirs: Array[Vector2] = [Vector2.UP, Vector2.DOWN, Vector2.LEFT, Vector2.RIGHT]
	for d in dirs:
		var from := center + d * gap
		var to := center + d * (gap + length)
		c.draw_line(from + Vector2.ONE, to + Vector2.ONE, shade, 3.0, true)
		c.draw_line(from, to, color, 1.6, true)
	c.draw_rect(Rect2(center - Vector2.ONE, Vector2(2.0, 2.0)), color, true)


## Converts a cone half angle in radians into a screen radius in pixels.
func _spread_pixels(view_height: float) -> float:
	var fov := clampf(float(Game.fov), 30.0, 150.0)
	var half := tan(deg_to_rad(fov) * 0.5)
	if half <= 0.0001:
		return 0.0
	return tan(clampf(_spread_rad, 0.0, 0.6)) / half * view_height * 0.5


func _draw_hitmarker(c: Control, rect: Rect2) -> void:
	if _hitmarker_t <= 0.0:
		return
	var alpha := clampf(_hitmarker_t / _HITMARKER_LIFE, 0.0, 1.0)
	var center := rect.position + rect.size * 0.5
	var color := Color(0.95, 0.94, 0.88, alpha)
	if _hit_killed:
		color = Color(0.86, 0.18, 0.12, alpha)
	var width := 2.0
	if _hit_headshot:
		width = 3.6
	var inner := 6.0
	var outer := 14.0
	var diag: Array[Vector2] = [
		Vector2(-1.0, -1.0), Vector2(1.0, -1.0), Vector2(-1.0, 1.0), Vector2(1.0, 1.0),
	]
	for d in diag:
		var n := d.normalized()
		c.draw_line(center + n * inner, center + n * outer, color, width, true)


# =============================================================================
# Painting: front layer (scope mask, death fade)
# =============================================================================

func _draw_front(c: Control) -> void:
	var rect := Rect2(Vector2.ZERO, c.size)
	if _scope_t > 0.01:
		_draw_scope(c, rect)
	if _dead:
		_draw_death(c, rect)


## Full screen black mask pierced by a circle, with a cross reticle and mil
## graduations. Built from a fan of quads so no texture is needed.
func _draw_scope(c: Control, rect: Rect2) -> void:
	var center := rect.position + rect.size * 0.5
	var radius := minf(rect.size.x, rect.size.y) * 0.40
	var reach := rect.size.length()
	var alpha := clampf(_scope_t, 0.0, 1.0)
	var mask := Color(0.0, 0.0, 0.0, alpha)
	var segments := 96
	for i in segments:
		var a0 := TAU * float(i) / float(segments)
		var a1 := TAU * float(i + 1) / float(segments)
		var quad := PackedVector2Array([
			center + Vector2(cos(a0), sin(a0)) * radius,
			center + Vector2(cos(a1), sin(a1)) * radius,
			center + Vector2(cos(a1), sin(a1)) * reach,
			center + Vector2(cos(a0), sin(a0)) * reach,
		])
		c.draw_colored_polygon(quad, mask)
	# Soft inner falloff so the glass edge is not a hard cut.
	for i in 8:
		var t := float(i) / 7.0
		c.draw_arc(center, radius * (1.0 - t * 0.10), 0.0, TAU, 96,
				Color(0.0, 0.0, 0.0, alpha * (1.0 - t) * 0.30), radius * 0.02, true)
	var ink := Color(0.02, 0.02, 0.02, alpha)
	c.draw_arc(center, radius, 0.0, TAU, 128, ink, 3.0, true)
	# Cross reticle.
	c.draw_line(center - Vector2(radius, 0.0), center + Vector2(radius, 0.0), ink, 1.4, true)
	c.draw_line(center - Vector2(0.0, radius), center + Vector2(0.0, radius), ink, 1.4, true)
	# Mil graduations along the lower and horizontal arms.
	var step := radius / 6.0
	for i in range(1, 6):
		var d := step * float(i)
		var arm := 7.0 if i % 2 == 0 else 4.0
		c.draw_line(center + Vector2(d, -arm), center + Vector2(d, arm), ink, 1.4, true)
		c.draw_line(center + Vector2(-d, -arm), center + Vector2(-d, arm), ink, 1.4, true)
		c.draw_line(center + Vector2(-arm, d), center + Vector2(arm, d), ink, 1.4, true)
	# Thick posts, left, right and bottom, like a period telescopic sight.
	var post := 5.0
	c.draw_line(center + Vector2(-radius, 0.0), center + Vector2(-radius * 0.42, 0.0), ink, post, true)
	c.draw_line(center + Vector2(radius, 0.0), center + Vector2(radius * 0.42, 0.0), ink, post, true)
	c.draw_line(center + Vector2(0.0, radius), center + Vector2(0.0, radius * 0.42), ink, post, true)


func _draw_death(c: Control, rect: Rect2) -> void:
	var t := clampf(_death_t / 1.4, 0.0, 1.0)
	c.draw_rect(rect, Color(0.16, 0.02, 0.02, 0.82 * t), true)
	c.draw_rect(rect, Color(0.0, 0.0, 0.0, 0.35 * t), true)


# =============================================================================
# Painting: compass band
# =============================================================================

func _draw_compass(c: Control) -> void:
	if _player == null:
		return
	var rect := Rect2(Vector2.ZERO, c.size)
	var width := clampf(rect.size.x * 0.52, 360.0, 760.0)
	var height := 30.0
	var origin := Vector2(rect.position.x + (rect.size.x - width) * 0.5, rect.position.y + 16.0)
	var band := Rect2(origin, Vector2(width, height))
	var alpha := 0.85
	c.draw_rect(band, Color(_INK.r, _INK.g, _INK.b, 0.34 * alpha), true)
	c.draw_line(origin, origin + Vector2(width, 0.0),
			Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.30), 1.0, true)
	c.draw_line(origin + Vector2(0.0, height), origin + Vector2(width, height),
			Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.30), 1.0, true)

	var font := ThemeDB.fallback_font
	var heading := rad_to_deg(_player_heading_rad())
	var per_degree := width / (_COMPASS_SPAN * 2.0)
	var center_x := origin.x + width * 0.5

	for degrees in range(0, 360, 5):
		var delta := wrapf(float(degrees) - heading, -180.0, 180.0)
		if absf(delta) > _COMPASS_SPAN:
			continue
		var x := center_x + delta * per_degree
		var tall: bool = degrees % 45 == 0
		var tick := 11.0 if tall else 5.0
		var tick_alpha := 0.75 if tall else 0.38
		c.draw_line(Vector2(x, origin.y + height - tick), Vector2(x, origin.y + height - 2.0),
				Color(_PAPER.r, _PAPER.g, _PAPER.b, tick_alpha), 1.4, true)
		if tall and font != null:
			var cardinal := _CARDINALS[(degrees / 45) % 8]
			var text_size := font.get_string_size(cardinal, HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
			c.draw_string(font, Vector2(x - text_size.x * 0.5, origin.y + 14.0), cardinal,
					HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.92))

	_draw_compass_markers(c, band, heading, per_degree, center_x, font)

	# Centre index, a small stamped triangle.
	var tip := Vector2(center_x, origin.y + height + 7.0)
	c.draw_colored_polygon(PackedVector2Array([
		tip, tip + Vector2(-6.0, 8.0), tip + Vector2(6.0, 8.0)]), _STAMP)


func _draw_compass_markers(c: Control, band: Rect2, heading: float, per_degree: float,
		center_x: float, font: Font) -> void:
	if _tracker == null or _player == null:
		return
	var origin := _player.global_position
	var actives: Array = _tracker.active()
	for entry in actives:
		var obj := entry as MissionDefs.Objective
		if obj == null:
			continue
		var to := obj.position - origin
		var bearing := rad_to_deg(atan2(to.x, -to.z))
		var delta := wrapf(bearing - heading, -180.0, 180.0)
		if absf(delta) > _COMPASS_SPAN:
			continue
		var x := center_x + delta * per_degree
		var top := band.position.y + 2.0
		c.draw_colored_polygon(PackedVector2Array([
			Vector2(x, top),
			Vector2(x - 5.0, top + 6.0),
			Vector2(x, top + 12.0),
			Vector2(x + 5.0, top + 6.0),
		]), Color(_STAMP.r, _STAMP.g, _STAMP.b, 0.92))
		if font == null:
			continue
		var meters := Vector2(to.x, to.z).length()
		var text := "%d m" % int(round(meters))
		var text_size := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12)
		c.draw_string(font, Vector2(x - text_size.x * 0.5, band.position.y + band.size.y + 26.0),
				text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12,
				Color(_PAPER.r, _PAPER.g, _PAPER.b, 0.8))


# =============================================================================
# Signal handlers
# =============================================================================

func _on_health_changed(current: float, maximum: float) -> void:
	_health = current
	_health_max = maxf(1.0, maximum)
	_t_health = _time
	if _dead and current > 0.0:
		_dead = false
		_death_t = 0.0
		_death_box.visible = false


func _on_player_died() -> void:
	_dead = true
	_death_t = 0.0
	_death_box.visible = true
	_death_hint.text = "Appuyez sur %s pour reprendre le combat." % _action_key_label("use")
	show_banner("MISSION INTERROMPUE", "Vous êtes tombé au combat.", 4.0)


func _on_weapon_changed(weapon: Weapon) -> void:
	_t_ammo = _time
	if weapon != null:
		show_toast(WeaponDefs.display_name(weapon.id), 1.6)


func _on_ammo_changed(_weapon: Weapon) -> void:
	_t_ammo = _time


func _on_player_damaged(_amount: float, from_direction: Vector3) -> void:
	flash_damage(from_direction)


func _on_bandages_changed(_count: int) -> void:
	_t_health = _time


func _on_objective_started(obj: MissionDefs.Objective) -> void:
	if obj == null:
		return
	_obj_elapsed[obj.id] = 0.0
	_t_objective = _time
	show_toast("Nouvel ordre : %s" % obj.title, 3.0)
	_play("ui_open", -8.0, 1.0)


func _on_objective_progress(_obj: MissionDefs.Objective, _current: int, _total: int) -> void:
	_t_objective = _time


func _on_objective_completed(obj: MissionDefs.Objective) -> void:
	_t_objective = _time
	if obj == null:
		return
	_obj_elapsed.erase(obj.id)
	show_banner("OBJECTIF ACCOMPLI", obj.title, 3.0)
	_play("objective_done", -4.0, 1.0)


func _on_objective_failed(obj: MissionDefs.Objective) -> void:
	_t_objective = _time
	if obj == null:
		return
	_obj_elapsed.erase(obj.id)
	show_banner("OBJECTIF ÉCHOUÉ", obj.title, 3.0)


func _on_campaign_completed() -> void:
	show_banner("LA POCHE EST LIBÉRÉE", "Toute la Normandie est aux mains des Alliés.", 6.0)


func _on_sector_captured(sector_id: int) -> void:
	var label := "Secteur %d" % sector_id
	if _world != null:
		var layout: Layout = _world.layout()
		if layout != null:
			var site: Layout.Site = layout.site_by_id(sector_id)
			if site != null:
				label = site.display_name
	show_banner("SECTEUR LIBÉRÉ", label, 4.0)
	_play("sector_captured", -3.0, 1.0)


func _on_alert_changed(level: int) -> void:
	_t_alert = _time
	if level >= War.ALERT_FULL:
		show_toast("Alerte générale dans le secteur", 2.6)


# =============================================================================
# Helpers
# =============================================================================

func _connect(source: Object, signal_name: String, target: Callable) -> void:
	if source == null or not is_instance_valid(source):
		return
	if not source.has_signal(signal_name):
		push_warning("Hud: missing signal %s on %s" % [signal_name, source])
		return
	if source.is_connected(signal_name, target):
		return
	source.connect(signal_name, target)


func _play(sample: String, volume_db: float, pitch: float) -> void:
	if Sfx == null:
		return
	if not Sfx.has_sample(sample):
		return
	Sfx.play(sample, volume_db, pitch)


## Alpha of a widget from the timestamp of its last change: full for five
## seconds, then a slow fade down to a whisper.
func _fade_alpha(last_change: float) -> float:
	var age := _time - last_change
	if age <= _HOLD_SECONDS:
		return 1.0
	var t := clampf((age - _HOLD_SECONDS) / _FADE_SECONDS, 0.0, 1.0)
	return lerpf(1.0, _REST_ALPHA, t)


func _touch_all() -> void:
	_t_ammo = _time
	_t_health = _time
	_t_objective = _time
	_t_alert = _time


func _current_objective() -> MissionDefs.Objective:
	if _tracker == null:
		return null
	return _tracker.current()


func _grenade_count() -> int:
	if _player == null:
		return 0
	var slot := WeaponDefs.SLOT_THROWN
	if slot < 0 or slot >= _player.weapons.size():
		return 0
	var thrown: Weapon = _player.weapons[slot]
	if thrown == null:
		return 0
	return thrown.in_magazine + thrown.reserve


## Player heading in radians, 0 pointing north (world -Z), growing clockwise.
func _player_heading_rad() -> float:
	if _player == null:
		return 0.0
	var forward := -_player.global_transform.basis.z
	return atan2(forward.x, -forward.z)


func _alert_color(level: int) -> Color:
	# An `if` chain, not a `match`: an autoload constant is a runtime property
	# access, which is not a legal match pattern.
	if level <= War.ALERT_CALM:
		return Color(0.55, 0.60, 0.44)
	if level == War.ALERT_SUSPICIOUS:
		return Color(0.78, 0.70, 0.36)
	if level == War.ALERT_SEARCHING:
		return Color(0.86, 0.52, 0.18)
	return Color(0.88, 0.22, 0.16)


func _biome_name(biome: int) -> String:
	if biome < 0 or biome >= _BIOME_NAMES.size():
		return "?"
	return _BIOME_NAMES[biome]


func _clock(seconds: float) -> String:
	var total := int(maxf(0.0, seconds))
	return "%02d:%02d" % [total / 60, total % 60]


## Reads `Player.prompt_text` when that public field exists, and stays silent
## when it does not: the field is optional in the player contract.
func _read_player_prompt() -> String:
	if _player == null or not is_instance_valid(_player):
		return ""
	if not _prompt_probed:
		_prompt_probed = true
		for entry in _player.get_property_list():
			if String(entry.get("name", "")) == "prompt_text":
				_prompt_available = true
				break
	if not _prompt_available:
		return ""
	var value: Variant = _player.get("prompt_text")
	if typeof(value) != TYPE_STRING:
		return ""
	return String(value)


## Human readable label of the first key bound to an action, for the hints.
func _action_key_label(action: String) -> String:
	if not InputMap.has_action(action):
		return "?"
	for event in InputMap.action_get_events(action):
		var key := event as InputEventKey
		if key == null:
			continue
		var code := key.physical_keycode
		if code == 0:
			code = key.keycode
		# keyboard_get_keycode_from_physical is not implemented by the headless
		# display server: calling it there raises an engine error instead of
		# returning a keycode, which floods the test harness output.
		if DisplayServer.get_name() == "headless":
			return OS.get_keycode_string(code)
		return OS.get_keycode_string(DisplayServer.keyboard_get_keycode_from_physical(code))
	return "?"
