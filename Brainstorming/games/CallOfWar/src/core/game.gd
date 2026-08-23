## Autoload `Game`: input map owner and settings owner.
##
## Two responsibilities and nothing else:
##  1. Install the whole InputMap from code in `_ready()`, using PHYSICAL
##     keycodes so an AZERTY keyboard drives ZQSD exactly where a QWERTY one
##     drives WASD. No editor bound action is required for the game to run.
##  2. Hold every player setting, clamped to a legal range and persisted in
##     `user://settings.cfg` through `ConfigFile`. A missing or corrupted file
##     is never fatal: defaults are restored and a clean file is rewritten.
##
## Every public setting is a property whose setter clamps the incoming value,
## returns early when nothing actually moves, and funnels through
## `_notify_changed()`. A batch load raises `_mute_depth` so `settings_changed`
## fires once for the whole batch instead of once per field.
extends Node

signal settings_changed()

const SETTINGS_PATH := "user://settings.cfg"

# Bounds
const MOUSE_SENSITIVITY_MIN := 0.0004
const MOUSE_SENSITIVITY_MAX := 0.010
const FOV_MIN := 60.0
const FOV_MAX := 110.0
const VIEW_DISTANCE_MIN := 4      # in 64 m tiles
const VIEW_DISTANCE_MAX := 14
const VOLUME_MIN := 0.0
const VOLUME_MAX := 1.0

# Difficulty steps
const DIFF_EASY := 0
const DIFF_NORMAL := 1
const DIFF_VETERAN := 2

# Defaults, private so `reset_settings()` and `load_settings()` share them.
const _DEF_MOUSE_SENSITIVITY := 0.0024
const _DEF_INVERT_Y := false
const _DEF_FOV := 82.0
const _DEF_VIEW_DISTANCE := 9
const _DEF_SFX_VOLUME := 0.85
const _DEF_MUSIC_VOLUME := 0.5
const _DEF_DIFFICULTY := 1
const _DEF_SHOW_FPS := false
const _DEF_SHOW_DEBUG := false
const _DEF_FULLSCREEN := false
const _DEF_BLOOD_EFFECTS := true
const _DEF_HEAD_BOB := true
const _DEF_CAMPAIGN_NAME := "normandie"

# ConfigFile sections.
const _SEC_INPUT := "input"
const _SEC_VIDEO := "video"
const _SEC_AUDIO := "audio"
const _SEC_GAMEPLAY := "gameplay"
const _SEC_CAMPAIGN := "campaign"

## Keyboard bindings, by PHYSICAL keycode. A physical keycode names the
## POSITION of the key on the board, so KEY_W is the key labelled Z on an
## AZERTY layout: the same finger movement on every keyboard in the world.
const _KEY_BINDINGS := {
	"move_forward": [KEY_W, KEY_UP],
	"move_back": [KEY_S, KEY_DOWN],
	"move_left": [KEY_A, KEY_LEFT],
	"move_right": [KEY_D, KEY_RIGHT],
	"jump": [KEY_SPACE],
	"sprint": [KEY_SHIFT],
	"crouch": [KEY_CTRL],
	"prone": [KEY_X],
	"reload": [KEY_R],
	"melee": [KEY_V],
	"grenade": [KEY_G],
	"use": [KEY_E],
	"heal": [KEY_H],
	"binoculars": [KEY_B],
	"weapon_1": [KEY_1],
	"weapon_2": [KEY_2],
	"weapon_3": [KEY_3],
	"weapon_4": [KEY_4],
	"map": [KEY_M],
	"objectives": [KEY_J],
	"pause": [KEY_ESCAPE],
	"fullscreen": [KEY_F11],
	"screenshot": [KEY_F2],
	"debug": [KEY_F3],
}

## Mouse bindings. Wheel steps behave as one shot buttons.
const _MOUSE_BINDINGS := {
	"fire": MOUSE_BUTTON_LEFT,
	"aim": MOUSE_BUTTON_RIGHT,
	"weapon_next": MOUSE_BUTTON_WHEEL_UP,
	"weapon_prev": MOUSE_BUTTON_WHEEL_DOWN,
}

## Deadzone for every action we install. Keyboard and mouse are digital, so a
## small value only filters analogue noise coming from a gamepad.
const _ACTION_DEADZONE := 0.2

var mouse_sensitivity: float = _DEF_MOUSE_SENSITIVITY:
	set(value):
		var v: float = clampf(value, MOUSE_SENSITIVITY_MIN, MOUSE_SENSITIVITY_MAX)
		if is_equal_approx(v, mouse_sensitivity):
			return
		mouse_sensitivity = v
		_notify_changed()

var invert_y: bool = _DEF_INVERT_Y:
	set(value):
		if value == invert_y:
			return
		invert_y = value
		_notify_changed()

var fov: float = _DEF_FOV:
	set(value):
		var v: float = clampf(value, FOV_MIN, FOV_MAX)
		if is_equal_approx(v, fov):
			return
		fov = v
		_notify_changed()

var view_distance: int = _DEF_VIEW_DISTANCE:
	set(value):
		var v: int = clampi(value, VIEW_DISTANCE_MIN, VIEW_DISTANCE_MAX)
		if v == view_distance:
			return
		view_distance = v
		_notify_changed()

var sfx_volume: float = _DEF_SFX_VOLUME:
	set(value):
		var v: float = clampf(value, VOLUME_MIN, VOLUME_MAX)
		if is_equal_approx(v, sfx_volume):
			return
		sfx_volume = v
		_notify_changed()

var music_volume: float = _DEF_MUSIC_VOLUME:
	set(value):
		var v: float = clampf(value, VOLUME_MIN, VOLUME_MAX)
		if is_equal_approx(v, music_volume):
			return
		music_volume = v
		_notify_changed()

var difficulty: int = _DEF_DIFFICULTY:
	set(value):
		var v: int = clampi(value, DIFF_EASY, DIFF_VETERAN)
		if v == difficulty:
			return
		difficulty = v
		_notify_changed()

var show_fps: bool = _DEF_SHOW_FPS:
	set(value):
		if value == show_fps:
			return
		show_fps = value
		_notify_changed()

var show_debug: bool = _DEF_SHOW_DEBUG:
	set(value):
		if value == show_debug:
			return
		show_debug = value
		_notify_changed()

var fullscreen: bool = _DEF_FULLSCREEN:
	set(value):
		if value == fullscreen:
			return
		fullscreen = value
		_apply_fullscreen()
		_notify_changed()

var blood_effects: bool = _DEF_BLOOD_EFFECTS:
	set(value):
		if value == blood_effects:
			return
		blood_effects = value
		_notify_changed()

var head_bob: bool = _DEF_HEAD_BOB:
	set(value):
		if value == head_bob:
			return
		head_bob = value
		_notify_changed()

## World seed. Drawn once on the very first launch and written immediately, so
## the same Normandy comes back on every later launch.
var campaign_seed: int = 0:
	set(value):
		var v: int = absi(value)
		if v == 0:
			v = 1942
		if v == campaign_seed:
			return
		campaign_seed = v
		_notify_changed()

var campaign_name: String = _DEF_CAMPAIGN_NAME:
	set(value):
		var v: String = _sanitize_campaign(value)
		if v == campaign_name:
			return
		campaign_name = v
		_notify_changed()

## Depth of the current batch. Above zero, `settings_changed` is held back.
var _mute_depth: int = 0
## True when a change happened while muted, so the batch emits exactly once.
var _pending_signal: bool = false
## True when the in memory settings differ from the file on disk.
var _dirty_on_disk: bool = false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_install_input_map()
	load_settings()
	_apply_fullscreen()


func _exit_tree() -> void:
	# Last chance write, so a value tweaked right before quitting survives.
	if _dirty_on_disk:
		save_settings()


# ---------------------------------------------------------------- input map --

## Rebuilds every action from scratch. Idempotent: an action that already
## exists (from the editor, or from a previous call) is erased first.
func _install_input_map() -> void:
	for key in _KEY_BINDINGS.keys():
		var action_name: String = str(key)
		_reset_action(action_name)
		var codes: Array = _KEY_BINDINGS[key]
		for code in codes:
			_bind_key(action_name, int(code))
	for key in _MOUSE_BINDINGS.keys():
		var action_name: String = str(key)
		_reset_action(action_name)
		_bind_mouse(action_name, int(_MOUSE_BINDINGS[key]))


## Erases the action when present, then recreates it empty.
func _reset_action(action_name: String) -> void:
	if InputMap.has_action(action_name):
		InputMap.erase_action(action_name)
	InputMap.add_action(action_name, _ACTION_DEADZONE)


## Adds one physical key event to an action.
func _bind_key(action_name: String, physical_code: int) -> void:
	var event := InputEventKey.new()
	# Physical only: `keycode` stays 0 so the active layout is irrelevant.
	event.physical_keycode = physical_code
	InputMap.action_add_event(action_name, event)


## Adds one mouse button (or wheel step) event to an action.
func _bind_mouse(action_name: String, button_index: int) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = button_index
	InputMap.action_add_event(action_name, event)


## Every action name this build installs, sorted. For the options screen and
## for the smoke probe, which checks that nothing is missing.
func _action_names() -> PackedStringArray:
	var names: PackedStringArray = []
	for key in _KEY_BINDINGS.keys():
		names.append(str(key))
	for key in _MOUSE_BINDINGS.keys():
		names.append(str(key))
	names.sort()
	return names


# ----------------------------------------------------------------- settings --

func load_settings() -> void:
	var cfg := ConfigFile.new()
	var err: int = cfg.load(SETTINGS_PATH)
	if err != OK:
		# A missing file on a fresh install is the normal case, not a failure.
		# A corrupted file is reported once, then silently replaced.
		if err != ERR_FILE_NOT_FOUND and err != ERR_FILE_CANT_OPEN:
			push_warning("Reglages illisibles (code %d), valeurs par defaut restaurees." % err)
		_begin_batch()
		_assign_defaults()
		campaign_seed = _draw_seed()
		_end_batch()
		save_settings()
		return

	var must_write: bool = false
	_begin_batch()
	mouse_sensitivity = _read_float(cfg, _SEC_INPUT, "mouse_sensitivity", _DEF_MOUSE_SENSITIVITY)
	invert_y = _read_bool(cfg, _SEC_INPUT, "invert_y", _DEF_INVERT_Y)
	fov = _read_float(cfg, _SEC_VIDEO, "fov", _DEF_FOV)
	view_distance = _read_int(cfg, _SEC_VIDEO, "view_distance", _DEF_VIEW_DISTANCE)
	fullscreen = _read_bool(cfg, _SEC_VIDEO, "fullscreen", _DEF_FULLSCREEN)
	show_fps = _read_bool(cfg, _SEC_VIDEO, "show_fps", _DEF_SHOW_FPS)
	show_debug = _read_bool(cfg, _SEC_VIDEO, "show_debug", _DEF_SHOW_DEBUG)
	blood_effects = _read_bool(cfg, _SEC_VIDEO, "blood_effects", _DEF_BLOOD_EFFECTS)
	head_bob = _read_bool(cfg, _SEC_VIDEO, "head_bob", _DEF_HEAD_BOB)
	sfx_volume = _read_float(cfg, _SEC_AUDIO, "sfx_volume", _DEF_SFX_VOLUME)
	music_volume = _read_float(cfg, _SEC_AUDIO, "music_volume", _DEF_MUSIC_VOLUME)
	difficulty = _read_int(cfg, _SEC_GAMEPLAY, "difficulty", _DEF_DIFFICULTY)
	campaign_name = _read_string(cfg, _SEC_CAMPAIGN, "name", _DEF_CAMPAIGN_NAME)

	var stored_seed: int = _read_int(cfg, _SEC_CAMPAIGN, "seed", 0)
	if stored_seed == 0:
		# No seed on file yet: draw the world once, and keep it forever.
		stored_seed = _draw_seed()
		must_write = true
	campaign_seed = stored_seed
	_end_batch()

	if must_write:
		save_settings()


func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value(_SEC_INPUT, "mouse_sensitivity", mouse_sensitivity)
	cfg.set_value(_SEC_INPUT, "invert_y", invert_y)
	cfg.set_value(_SEC_VIDEO, "fov", fov)
	cfg.set_value(_SEC_VIDEO, "view_distance", view_distance)
	cfg.set_value(_SEC_VIDEO, "fullscreen", fullscreen)
	cfg.set_value(_SEC_VIDEO, "show_fps", show_fps)
	cfg.set_value(_SEC_VIDEO, "show_debug", show_debug)
	cfg.set_value(_SEC_VIDEO, "blood_effects", blood_effects)
	cfg.set_value(_SEC_VIDEO, "head_bob", head_bob)
	cfg.set_value(_SEC_AUDIO, "sfx_volume", sfx_volume)
	cfg.set_value(_SEC_AUDIO, "music_volume", music_volume)
	cfg.set_value(_SEC_GAMEPLAY, "difficulty", difficulty)
	cfg.set_value(_SEC_CAMPAIGN, "name", campaign_name)
	cfg.set_value(_SEC_CAMPAIGN, "seed", campaign_seed)
	var err: int = cfg.save(SETTINGS_PATH)
	if err != OK:
		push_warning("Impossible d'ecrire les reglages (code %d)." % err)
		return
	_dirty_on_disk = false


## Restores every default. The campaign identity (seed and name) is kept on
## purpose: resetting the options must never throw the current world away.
func reset_settings() -> void:
	_begin_batch()
	_assign_defaults()
	_end_batch()
	_apply_fullscreen()
	save_settings()


func _assign_defaults() -> void:
	mouse_sensitivity = _DEF_MOUSE_SENSITIVITY
	invert_y = _DEF_INVERT_Y
	fov = _DEF_FOV
	view_distance = _DEF_VIEW_DISTANCE
	sfx_volume = _DEF_SFX_VOLUME
	music_volume = _DEF_MUSIC_VOLUME
	difficulty = _DEF_DIFFICULTY
	show_fps = _DEF_SHOW_FPS
	show_debug = _DEF_SHOW_DEBUG
	fullscreen = _DEF_FULLSCREEN
	blood_effects = _DEF_BLOOD_EFFECTS
	head_bob = _DEF_HEAD_BOB
	if campaign_name.is_empty():
		campaign_name = _DEF_CAMPAIGN_NAME


## Damage multiplier applied to the player, from `difficulty`.
## 0 -> 0.5, 1 -> 1.0, 2 -> 1.75
func incoming_damage_scale() -> float:
	match difficulty:
		DIFF_EASY:
			return 0.5
		DIFF_VETERAN:
			return 1.75
		_:
			return 1.0


## Enemy accuracy multiplier from `difficulty`. 0 -> 0.6, 1 -> 1.0, 2 -> 1.35
func enemy_accuracy_scale() -> float:
	match difficulty:
		DIFF_EASY:
			return 0.6
		DIFF_VETERAN:
			return 1.35
		_:
			return 1.0


func difficulty_name() -> String:
	match difficulty:
		DIFF_EASY:
			return "Recrue"
		DIFF_VETERAN:
			return "Veteran"
		_:
			return "Soldat"


# ------------------------------------------------------------------ helpers --

## Opens a batch: `settings_changed` is held until the matching `_end_batch()`.
func _begin_batch() -> void:
	_mute_depth += 1


## Closes a batch and emits once, when at least one value actually moved.
func _end_batch() -> void:
	_mute_depth -= 1
	if _mute_depth > 0:
		return
	_mute_depth = 0
	if _pending_signal:
		_pending_signal = false
		settings_changed.emit()


## Single funnel used by every setter.
func _notify_changed() -> void:
	_dirty_on_disk = true
	if _mute_depth > 0:
		_pending_signal = true
		return
	settings_changed.emit()


func _apply_fullscreen() -> void:
	if DisplayServer.get_name() == "headless":
		return
	var wanted: int = DisplayServer.WINDOW_MODE_WINDOWED
	if fullscreen:
		wanted = DisplayServer.WINDOW_MODE_FULLSCREEN
	if int(DisplayServer.window_get_mode()) == wanted:
		return
	DisplayServer.window_set_mode(wanted)


## A never zero, always positive world seed.
func _draw_seed() -> int:
	randomize()
	var value: int = absi(randi())
	if value == 0:
		value = 1942
	return value


## Campaign names double as file names, so only safe characters survive.
func _sanitize_campaign(raw: String) -> String:
	var source: String = raw.strip_edges().to_lower()
	var cleaned: String = ""
	for i in source.length():
		var c: String = source[i]
		if c == "_" or c == "-" or c.is_valid_identifier() or (c >= "0" and c <= "9"):
			cleaned += c
	if cleaned.is_empty():
		return _DEF_CAMPAIGN_NAME
	if cleaned.length() > 40:
		cleaned = cleaned.substr(0, 40)
	return cleaned


func _read_float(cfg: ConfigFile, section: String, key: String, fallback: float) -> float:
	var value: Variant = cfg.get_value(section, key, fallback)
	var kind: int = typeof(value)
	if kind == TYPE_FLOAT or kind == TYPE_INT:
		return float(value)
	return fallback


func _read_int(cfg: ConfigFile, section: String, key: String, fallback: int) -> int:
	var value: Variant = cfg.get_value(section, key, fallback)
	var kind: int = typeof(value)
	if kind == TYPE_INT or kind == TYPE_FLOAT:
		return int(value)
	return fallback


func _read_bool(cfg: ConfigFile, section: String, key: String, fallback: bool) -> bool:
	var value: Variant = cfg.get_value(section, key, fallback)
	var kind: int = typeof(value)
	if kind == TYPE_BOOL:
		return bool(value)
	if kind == TYPE_INT:
		return int(value) != 0
	return fallback


func _read_string(cfg: ConfigFile, section: String, key: String, fallback: String) -> String:
	var value: Variant = cfg.get_value(section, key, fallback)
	var kind: int = typeof(value)
	if kind == TYPE_STRING or kind == TYPE_STRING_NAME:
		return str(value)
	return fallback
