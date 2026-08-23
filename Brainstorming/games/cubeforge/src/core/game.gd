extends Node
## Global autoload holding player settings and the world seed.
##
## Registered as `Game` in project.godot, so every module reaches it directly
## (`Game.render_distance`, `Game.settings_changed`, ...).
##
## Two jobs:
##   1. Install the whole InputMap from code in `_ready()`. Nothing lives in
##      project.godot, and every key is bound by *physical* keycode so an AZERTY
##      keyboard drives ZQSD exactly where a QWERTY drives WASD.
##   2. Own the settings, clamped to safe ranges, persisted in
##      `user://settings.cfg` through ConfigFile. A missing or corrupt file is
##      never fatal: defaults take over and a fresh file is written.
##
## Every public setting is a property with a setter, so any mutation (pause menu
## sliders included) is clamped and announced through `settings_changed`.

## Emitted whenever a setting actually changed value, and once after
## `load_settings()` and `reset_settings()`.
signal settings_changed()

const SETTINGS_PATH := "user://settings.cfg"
const SETTINGS_SECTION := "settings"

const MOUSE_SENSITIVITY_MIN := 0.0004
const MOUSE_SENSITIVITY_MAX := 0.01
const FOV_MIN := 60.0
const FOV_MAX := 110.0
const RENDER_DISTANCE_MIN := 3
const RENDER_DISTANCE_MAX := 16
const SFX_VOLUME_MIN := 0.0
const SFX_VOLUME_MAX := 1.0

const DEFAULT_MOUSE_SENSITIVITY := 0.0022
const DEFAULT_INVERT_Y := false
const DEFAULT_FOV := 78.0
const DEFAULT_RENDER_DISTANCE := 8
const DEFAULT_CREATIVE := true
const DEFAULT_SFX_VOLUME := 0.8
const DEFAULT_SHOW_DEBUG := false
const DEFAULT_SHOW_FPS := false
const DEFAULT_FLY_MODE := false
const DEFAULT_REALISTIC := false
const DEFAULT_FULLSCREEN := false
const DEFAULT_WORLD_NAME := "monde"

## Suppression depth for `settings_changed`. Raised while a whole batch of
## settings is written (load, reset) so listeners get a single notification.
var _mute_depth: int = 0

## Radians of camera rotation per mouse pixel.
var mouse_sensitivity: float = DEFAULT_MOUSE_SENSITIVITY:
	set(value):
		var v := clampf(value, MOUSE_SENSITIVITY_MIN, MOUSE_SENSITIVITY_MAX)
		if is_equal_approx(v, mouse_sensitivity):
			return
		mouse_sensitivity = v
		_notify_changed()

## Inverts the vertical mouse axis.
var invert_y: bool = DEFAULT_INVERT_Y:
	set(value):
		if value == invert_y:
			return
		invert_y = value
		_notify_changed()

## Camera field of view in degrees.
var fov: float = DEFAULT_FOV:
	set(value):
		var v := clampf(value, FOV_MIN, FOV_MAX)
		if is_equal_approx(v, fov):
			return
		fov = v
		_notify_changed()

## Streaming radius in chunks around the player.
var render_distance: int = DEFAULT_RENDER_DISTANCE:
	set(value):
		var v := clampi(value, RENDER_DISTANCE_MIN, RENDER_DISTANCE_MAX)
		if v == render_distance:
			return
		render_distance = v
		_notify_changed()

## Seed of the terrain generator. Zero means "draw one on first launch"; the
## drawn value is persisted immediately so the same world comes back later.
var world_seed: int = 0:
	set(value):
		if value == world_seed:
			return
		world_seed = value
		_notify_changed()

## Name of the world being played. Sanitized on write so it always maps to a
## valid save folder; an unusable value falls back to the default world.
var world_name: String = DEFAULT_WORLD_NAME:
	set(value):
		var v := WorldsUi.sanitize_world_name(value)
		if v.is_empty():
			v = DEFAULT_WORLD_NAME
		if v == world_name:
			return
		world_name = v
		_notify_changed()

## Creative mode: no block consumption, flight allowed.
var creative: bool = DEFAULT_CREATIVE:
	set(value):
		if value == creative:
			return
		creative = value
		_notify_changed()

## Linear sound effect volume, 0 to 1.
var sfx_volume: float = DEFAULT_SFX_VOLUME:
	set(value):
		var v := clampf(value, SFX_VOLUME_MIN, SFX_VOLUME_MAX)
		if is_equal_approx(v, sfx_volume):
			return
		sfx_volume = v
		_notify_changed()

## Debug overlay visibility.
var show_debug: bool = DEFAULT_SHOW_DEBUG:
	set(value):
		if value == show_debug:
			return
		show_debug = value
		_notify_changed()

## Compact frames-per-second counter in the top-left corner.
var show_fps: bool = DEFAULT_SHOW_FPS:
	set(value):
		if value == show_fps:
			return
		show_fps = value
		_notify_changed()

## Persistent God-mode state, controlled by F or the settings menu. It grants
## flight and the full block and tool palettes, and is deliberately independent
## of `creative`: a survival world keeps its monsters, its damage and its
## resource costs while the player flies and picks any tool.
var fly_mode: bool = DEFAULT_FLY_MODE:
	set(value):
		if value == fly_mode:
			return
		fly_mode = value
		_notify_changed()

## Enhanced filtered materials and rounded inhabitant models.
var realistic: bool = DEFAULT_REALISTIC:
	set(value):
		if value == realistic:
			return
		realistic = value
		_notify_changed()

## Borderless fullscreen window. Applied by main at startup and on every change.
var fullscreen: bool = DEFAULT_FULLSCREEN:
	set(value):
		if value == fullscreen:
			return
		fullscreen = value
		_notify_changed()


func _ready() -> void:
	_install_input_map()
	load_settings()


# ---------------------------------------------------------------------------
# Input map
# ---------------------------------------------------------------------------

## Declares every action of the game. Already existing actions are left
## untouched, so calling this twice never duplicates an event.
func _install_input_map() -> void:
	_add_key_action(&"move_forward", [KEY_W, KEY_UP])
	_add_key_action(&"move_back", [KEY_S, KEY_DOWN])
	_add_key_action(&"move_left", [KEY_A, KEY_LEFT])
	_add_key_action(&"move_right", [KEY_D, KEY_RIGHT])
	_add_key_action(&"jump", [KEY_SPACE])
	_add_key_action(&"sprint", [KEY_SHIFT])
	_add_key_action(&"crouch", [KEY_CTRL])
	_add_key_action(&"fly_toggle", [KEY_F])

	_add_mouse_action(&"dig", [MOUSE_BUTTON_LEFT])
	_add_mouse_action(&"place", [MOUSE_BUTTON_RIGHT])
	_add_mouse_action(&"pick_block", [MOUSE_BUTTON_MIDDLE])
	_add_mouse_action(&"hotbar_next", [MOUSE_BUTTON_WHEEL_DOWN])
	_add_mouse_action(&"hotbar_prev", [MOUSE_BUTTON_WHEEL_UP])

	# KEY_1 .. KEY_9 are contiguous keycodes, so the row maps by offset.
	for i in 9:
		_add_key_action(StringName("hotbar_%d" % (i + 1)), [KEY_1 + i])

	_add_key_action(&"inventory", [KEY_E])
	_add_key_action(&"craft", [KEY_C])
	_add_key_action(&"map", [KEY_M])
	_add_key_action(&"fullscreen", [KEY_F11])
	_add_key_action(&"debug_overlay", [KEY_F3])
	_add_key_action(&"pause", [KEY_ESCAPE])
	_add_key_action(&"screenshot", [KEY_F2])
	_add_key_action(&"time_forward", [KEY_T])


## Creates `action` bound to physical keys, unless the action already exists.
func _add_key_action(action: StringName, physical_keys: Array) -> void:
	if InputMap.has_action(action):
		return
	InputMap.add_action(action)
	for key in physical_keys:
		var event := InputEventKey.new()
		event.physical_keycode = int(key)
		InputMap.action_add_event(action, event)


## Creates `action` bound to mouse buttons, unless the action already exists.
func _add_mouse_action(action: StringName, buttons: Array) -> void:
	if InputMap.has_action(action):
		return
	InputMap.add_action(action)
	for button in buttons:
		var event := InputEventMouseButton.new()
		event.button_index = int(button)
		InputMap.action_add_event(action, event)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

## Writes every setting to user://settings.cfg. Failures only warn: a read only
## user directory must not break the game.
func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value(SETTINGS_SECTION, "mouse_sensitivity", mouse_sensitivity)
	cfg.set_value(SETTINGS_SECTION, "invert_y", invert_y)
	cfg.set_value(SETTINGS_SECTION, "fov", fov)
	cfg.set_value(SETTINGS_SECTION, "render_distance", render_distance)
	cfg.set_value(SETTINGS_SECTION, "world_seed", world_seed)
	cfg.set_value(SETTINGS_SECTION, "world_name", world_name)
	cfg.set_value(SETTINGS_SECTION, "creative", creative)
	cfg.set_value(SETTINGS_SECTION, "sfx_volume", sfx_volume)
	cfg.set_value(SETTINGS_SECTION, "show_debug", show_debug)
	cfg.set_value(SETTINGS_SECTION, "show_fps", show_fps)
	cfg.set_value(SETTINGS_SECTION, "fly_mode", fly_mode)
	cfg.set_value(SETTINGS_SECTION, "realistic", realistic)
	cfg.set_value(SETTINGS_SECTION, "fullscreen", fullscreen)
	var err := cfg.save(SETTINGS_PATH)
	if err != OK:
		push_warning("Game: could not write %s (error %d)" % [SETTINGS_PATH, err])


## Reads user://settings.cfg when present, clamps every value, then makes sure a
## non-zero world seed exists and is on disk. Emits settings_changed once.
func load_settings() -> void:
	var cfg := ConfigFile.new()
	var err := cfg.load(SETTINGS_PATH)
	var had_file := err == OK
	if not had_file and err != ERR_FILE_NOT_FOUND and err != ERR_FILE_CANT_OPEN:
		push_warning("Game: could not read %s (error %d), using defaults" % [SETTINGS_PATH, err])

	_mute_depth += 1
	if had_file:
		mouse_sensitivity = _read_float(cfg, "mouse_sensitivity", DEFAULT_MOUSE_SENSITIVITY)
		invert_y = _read_bool(cfg, "invert_y", DEFAULT_INVERT_Y)
		fov = _read_float(cfg, "fov", DEFAULT_FOV)
		render_distance = _read_int(cfg, "render_distance", DEFAULT_RENDER_DISTANCE)
		world_seed = _read_int(cfg, "world_seed", 0)
		world_name = _read_string(cfg, "world_name", DEFAULT_WORLD_NAME)
		creative = _read_bool(cfg, "creative", DEFAULT_CREATIVE)
		sfx_volume = _read_float(cfg, "sfx_volume", DEFAULT_SFX_VOLUME)
		show_debug = _read_bool(cfg, "show_debug", DEFAULT_SHOW_DEBUG)
		show_fps = _read_bool(cfg, "show_fps", DEFAULT_SHOW_FPS)
		fly_mode = _read_bool(cfg, "fly_mode", DEFAULT_FLY_MODE)
		realistic = _read_bool(cfg, "realistic", DEFAULT_REALISTIC)
		fullscreen = _read_bool(cfg, "fullscreen", DEFAULT_FULLSCREEN)
	else:
		_assign_defaults()

	var fresh_seed := world_seed == 0
	if fresh_seed:
		world_seed = _draw_world_seed()
	_mute_depth -= 1

	# A brand new install, a broken file or a freshly drawn seed all deserve an
	# immediate write so the very same world comes back on the next launch.
	if not had_file or fresh_seed:
		save_settings()
	settings_changed.emit()


## Restores every tunable setting to its default. The world seed survives,
## because losing it would replace the player's world.
func reset_settings() -> void:
	_mute_depth += 1
	_assign_defaults()
	if world_seed == 0:
		world_seed = _draw_world_seed()
	_mute_depth -= 1
	save_settings()
	settings_changed.emit()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _assign_defaults() -> void:
	mouse_sensitivity = DEFAULT_MOUSE_SENSITIVITY
	invert_y = DEFAULT_INVERT_Y
	fov = DEFAULT_FOV
	render_distance = DEFAULT_RENDER_DISTANCE
	creative = DEFAULT_CREATIVE
	sfx_volume = DEFAULT_SFX_VOLUME
	show_debug = DEFAULT_SHOW_DEBUG
	show_fps = DEFAULT_SHOW_FPS
	fly_mode = DEFAULT_FLY_MODE
	realistic = DEFAULT_REALISTIC
	fullscreen = DEFAULT_FULLSCREEN
	world_name = DEFAULT_WORLD_NAME


func _notify_changed() -> void:
	if _mute_depth == 0:
		settings_changed.emit()


## Non-zero pseudo random seed, drawn from an owned generator so the global one
## keeps whatever state the rest of the game gave it.
func _draw_world_seed() -> int:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	var value := rng.randi_range(1, 0x7FFFFFFF)
	if value == 0:
		value = 1
	return value


func _read_float(cfg: ConfigFile, key: String, fallback: float) -> float:
	var raw: Variant = cfg.get_value(SETTINGS_SECTION, key, fallback)
	if raw is float or raw is int:
		return float(raw)
	push_warning("Game: setting '%s' is not a number, using %f" % [key, fallback])
	return fallback


func _read_int(cfg: ConfigFile, key: String, fallback: int) -> int:
	var raw: Variant = cfg.get_value(SETTINGS_SECTION, key, fallback)
	if raw is int:
		return int(raw)
	if raw is float:
		return int(roundf(float(raw)))
	push_warning("Game: setting '%s' is not a number, using %d" % [key, fallback])
	return fallback


func _read_string(cfg: ConfigFile, key: String, fallback: String) -> String:
	var raw: Variant = cfg.get_value(SETTINGS_SECTION, key, fallback)
	if raw is String:
		return raw
	push_warning("Game: setting '%s' is not a string, using %s" % [key, fallback])
	return fallback


func _read_bool(cfg: ConfigFile, key: String, fallback: bool) -> bool:
	var raw: Variant = cfg.get_value(SETTINGS_SECTION, key, fallback)
	if raw is bool:
		return raw
	if raw is int or raw is float:
		return float(raw) != 0.0
	push_warning("Game: setting '%s' is not a boolean, using %s" % [key, str(fallback)])
	return fallback
