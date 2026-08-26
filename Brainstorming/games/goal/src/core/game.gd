extends Node
## Autoload `Game`: the input map, the settings and the window mode.
##
## Three jobs, all of them boring on purpose so that nothing else in the project
## has to think about them.
##
## 1. The whole InputMap is declared here, in code, and NOT in project.godot.
##    Every key is bound by PHYSICAL keycode, which means the engine resolves it
##    by position on the keyboard rather than by the letter printed on the cap.
##    An AZERTY player therefore drives ZQSD and a QWERTY player drives WASD
##    with the same three lines of code, and neither has to visit an options
##    screen before the first penalty. Declaring the map from code also means a
##    corrupted project.godot cannot silently break the controls.
##
## 2. The settings live in user://settings.cfg through ConfigFile. Reading them
##    is defensive from end to end: a missing file is the normal first run, a
##    corrupt file is a bad shutdown, and a value of the wrong type is somebody
##    editing the file by hand. None of the three is ever fatal, they all fall
##    back to the default and carry on.
##
## 3. F11 toggles fullscreen, and the choice is persisted like any other
##    setting, so the game reopens the way the player left it.
##
## `seed_value` is drawn once, on the very first run, and then kept forever: it
## is what makes a player's campaign reproducible.

signal settings_changed()

const SETTINGS_PATH := "user://settings.cfg"

## Section names inside the config file.
const _SECTION_SETTINGS := "settings"
const _SECTION_CAMPAIGN := "campaign"

## Every action this game declares. Anything not in this list does not exist.
const ACTIONS: PackedStringArray = [
	"aim_left", "aim_right", "aim_up", "aim_down",
	"strike", "feint", "spin_left", "spin_right",
	"next_shot", "replay", "camera_cycle", "pause",
	"menu_accept", "menu_back", "restart", "fullscreen",
]

## Default value of every persisted setting, and the reference for its type.
const DEFAULTS: Dictionary = {
	"mouse_sensitivity": 1.0,
	"master_volume": 0.8,
	"muted": false,
	"keeper_level": 1,
	"sweep_level": 1,
	"show_trajectory": true,
	"show_replay": true,
	"camera_shake": 0.7,
	"fullscreen": false,
}

## Seconds between a setting change and the write to disk. A volume slider being
## dragged must not hit the filesystem sixty times a second.
const _SAVE_DELAY := 0.75

var mouse_sensitivity: float = 1.0
var master_volume: float = 0.8
var muted: bool = false
var keeper_level: int = 1
## Second difficulty axis: how fast the precision marker sweeps the timing lane.
## An index into Shooter.SWEEP_SCALES, so the taker owns the actual rates and the
## settings only carry the choice.
var sweep_level: int = 1
var show_trajectory: bool = true
var show_replay: bool = true
var camera_shake: float = 0.7
var fullscreen: bool = false
var seed_value: int = 0

## True once a change is waiting for its deferred write.
var _save_pending: bool = false


func _ready() -> void:
	# The pause menu still needs its keys, so the autoload keeps running while
	# the tree is paused.
	process_mode = Node.PROCESS_MODE_ALWAYS
	_install_input_map()
	load_settings()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_PREDELETE:
		if _save_pending:
			_save_pending = false
			save_settings()


# --------------------------------------------------------------------------
# Input map
# --------------------------------------------------------------------------

## Declares an action from scratch, wiping whatever project.godot may have left
## behind so the code stays the single source of truth.
func _declare(action: StringName) -> void:
	if InputMap.has_action(action):
		InputMap.action_erase_events(action)
	else:
		InputMap.add_action(action, 0.2)


func _bind_key(action: StringName, physical: Key) -> void:
	var event := InputEventKey.new()
	# physical_keycode, never keycode: this is the whole AZERTY story.
	event.physical_keycode = physical
	InputMap.action_add_event(action, event)


func _bind_mouse(action: StringName, button: MouseButton) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = button
	InputMap.action_add_event(action, event)


func _install_input_map() -> void:
	for action in ACTIONS:
		_declare(action)

	# Aim: WASD by position (so ZQSD on AZERTY) plus the arrow keys.
	_bind_key("aim_left", KEY_A)
	_bind_key("aim_left", KEY_LEFT)
	_bind_key("aim_right", KEY_D)
	_bind_key("aim_right", KEY_RIGHT)
	_bind_key("aim_up", KEY_W)
	_bind_key("aim_up", KEY_UP)
	_bind_key("aim_down", KEY_S)
	_bind_key("aim_down", KEY_DOWN)

	# Striking.
	_bind_mouse("strike", MOUSE_BUTTON_LEFT)
	_bind_key("strike", KEY_SPACE)
	_bind_key("feint", KEY_SHIFT)

	# Curl. The contract puts these on the AZERTY A and E, which are the
	# physical Q and E keys.
	_bind_key("spin_left", KEY_Q)
	_bind_key("spin_right", KEY_E)

	# Flow.
	_bind_key("next_shot", KEY_ENTER)
	_bind_key("next_shot", KEY_KP_ENTER)
	_bind_key("next_shot", KEY_SPACE)
	_bind_key("replay", KEY_R)
	_bind_key("camera_cycle", KEY_C)
	_bind_key("pause", KEY_ESCAPE)

	# Menus.
	_bind_key("menu_accept", KEY_ENTER)
	_bind_key("menu_accept", KEY_KP_ENTER)
	_bind_key("menu_accept", KEY_SPACE)
	_bind_key("menu_back", KEY_ESCAPE)
	_bind_key("menu_back", KEY_BACKSPACE)
	_bind_key("restart", KEY_F5)

	# Window. F11 only, deliberately: Alt+Enter is the other common binding, but
	# Godot matches an action bound to a bare Enter even when Alt is held, so
	# adding it would make Alt+Enter confirm a menu and toggle the window at the
	# same time.
	_bind_key("fullscreen", KEY_F11)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

## Reads a value defensively: anything that is not a number falls back.
func _as_float(value: Variant, fallback: float) -> float:
	var kind := typeof(value)
	if kind == TYPE_FLOAT or kind == TYPE_INT:
		var out := float(value)
		if is_finite(out):
			return out
	return fallback


func _as_int(value: Variant, fallback: int) -> int:
	var kind := typeof(value)
	if kind == TYPE_INT:
		return int(value)
	if kind == TYPE_FLOAT and is_finite(float(value)):
		return int(round(float(value)))
	return fallback


func _as_bool(value: Variant, fallback: bool) -> bool:
	var kind := typeof(value)
	if kind == TYPE_BOOL:
		return bool(value)
	if kind == TYPE_INT or kind == TYPE_FLOAT:
		return float(value) != 0.0
	return fallback


## Assigns one setting, clamped to its legal band. Returns false for an unknown
## key so callers can complain once instead of guessing.
func _assign(key: String, value: Variant) -> bool:
	match key:
		"mouse_sensitivity":
			mouse_sensitivity = clampf(_as_float(value, 1.0), 0.2, 3.0)
		"master_volume":
			master_volume = clampf(_as_float(value, 0.8), 0.0, 1.0)
		"muted":
			muted = _as_bool(value, false)
		"keeper_level":
			# KeeperBrain.Level has four entries, Debutant to Legende.
			keeper_level = clampi(_as_int(value, 1), 0, 3)
		"sweep_level":
			# Four steps, Lent to Fulgurant. Clamped against Shooter.SWEEP_SCALES
			# by hand rather than by reading it: this autoload is loaded before any
			# scene script and must not depend on one.
			sweep_level = clampi(_as_int(value, 1), 0, 3)
		"show_trajectory":
			show_trajectory = _as_bool(value, true)
		"show_replay":
			show_replay = _as_bool(value, true)
		"camera_shake":
			camera_shake = clampf(_as_float(value, 0.7), 0.0, 1.0)
		"fullscreen":
			fullscreen = _as_bool(value, false)
		_:
			return false
	return true


## Pushes the audio settings onto the master bus. Doing it here rather than in
## Sfx means the level is right even before the first sound is played.
func _apply_audio() -> void:
	var bus := AudioServer.get_bus_index("Master")
	if bus < 0:
		return
	# A linear slider at 0 must be silence, and linear_to_db(0) is -inf, which
	# the server dislikes: floor it instead.
	var db := -80.0
	if master_volume > 0.001:
		db = linear_to_db(master_volume)
	AudioServer.set_bus_volume_db(bus, db)
	AudioServer.set_bus_mute(bus, muted)


# --------------------------------------------------------------------------
# Window mode
# --------------------------------------------------------------------------

## F11 is handled here rather than in Main so that it works everywhere: on the
## home menu, mid flight, during a replay and while the tree is paused. This
## autoload runs with PROCESS_MODE_ALWAYS, so it is the one node guaranteed to
## be listening at every moment of the game.
##
## _input and not _unhandled_input: the menus and the HUD are Controls, and a
## focused Control eats keys before they ever reach the unhandled pass. Taking
## the event early and marking it handled is what stops F11 from being swallowed
## by whatever happens to have focus.
func _input(event: InputEvent) -> void:
	if event.is_action_pressed("fullscreen", false, true):
		toggle_fullscreen()
		get_viewport().set_input_as_handled()


## Flips the window mode and persists the choice.
func toggle_fullscreen() -> void:
	set_setting("fullscreen", not fullscreen)


## Brings the actual window in line with the `fullscreen` setting.
##
## WINDOW_MODE_FULLSCREEN and not EXCLUSIVE_FULLSCREEN: borderless fullscreen
## keeps alt tab instant and lets the compositor keep working, which matters on
## a laptop. Exclusive mode buys a fraction of a frame of latency and costs a
## mode switch every time the player alt tabs.
func _apply_window_mode() -> void:
	# The headless driver has no window at all, and the smoke probe runs there.
	if DisplayServer.get_name() == "headless":
		return
	var mode := DisplayServer.window_get_mode()
	var is_full := (
		mode == DisplayServer.WINDOW_MODE_FULLSCREEN
		or mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN
	)
	if is_full == fullscreen:
		return
	DisplayServer.window_set_mode(
		DisplayServer.WINDOW_MODE_FULLSCREEN if fullscreen
		else DisplayServer.WINDOW_MODE_WINDOWED
	)


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

func load_settings() -> void:
	for key: String in DEFAULTS:
		_assign(key, DEFAULTS[key])

	var config := ConfigFile.new()
	var err := config.load(SETTINGS_PATH)
	if err == OK:
		for key: String in DEFAULTS:
			if config.has_section_key(_SECTION_SETTINGS, key):
				_assign(key, config.get_value(_SECTION_SETTINGS, key, DEFAULTS[key]))
	elif err != ERR_FILE_NOT_FOUND:
		# A truncated or hand mangled file is a bad shutdown, not a crash.
		push_warning("GOAL: settings illisibles (%d), retour aux valeurs par defaut." % err)

	# The campaign seed is drawn exactly once in the life of an installation.
	var stored_seed := 0
	if err == OK and config.has_section_key(_SECTION_CAMPAIGN, "seed_value"):
		stored_seed = _as_int(config.get_value(_SECTION_CAMPAIGN, "seed_value", 0), 0)
	if stored_seed == 0:
		seed_value = _draw_seed()
		save_settings()
	else:
		seed_value = stored_seed

	_apply_audio()
	_apply_window_mode()
	settings_changed.emit()


func _draw_seed() -> int:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	# Positive and non zero, because zero is the "no seed stored" marker.
	return (rng.randi() & 0x7FFFFFFF) | 1


func save_settings() -> void:
	# Written from scratch rather than merged into whatever is on disk: this
	# script owns every key in the file, and re-reading a corrupt file here
	# would print a second parse error for a value we are about to overwrite.
	var config := ConfigFile.new()
	for key: String in DEFAULTS:
		config.set_value(_SECTION_SETTINGS, key, get_setting(key))
	config.set_value(_SECTION_CAMPAIGN, "seed_value", seed_value)
	var write_err := config.save(SETTINGS_PATH)
	if write_err != OK:
		push_warning("GOAL: impossible d'ecrire %s (%d)." % [SETTINGS_PATH, write_err])


## Applies a setting by name with clamping, then emits settings_changed.
func set_setting(key: String, value: Variant) -> void:
	if not _assign(key, value):
		push_warning("GOAL: reglage inconnu '%s'." % key)
		return
	_apply_audio()
	_apply_window_mode()
	_queue_save()
	settings_changed.emit()


func get_setting(key: String) -> Variant:
	match key:
		"mouse_sensitivity":
			return mouse_sensitivity
		"master_volume":
			return master_volume
		"muted":
			return muted
		"keeper_level":
			return keeper_level
		"sweep_level":
			return sweep_level
		"show_trajectory":
			return show_trajectory
		"show_replay":
			return show_replay
		"camera_shake":
			return camera_shake
		"fullscreen":
			return fullscreen
		"seed_value":
			return seed_value
	push_warning("GOAL: reglage inconnu '%s'." % key)
	return null


## Resets every setting to its default and saves. The campaign seed survives:
## it is an identity, not a preference.
func reset_settings() -> void:
	for key: String in DEFAULTS:
		_assign(key, DEFAULTS[key])
	_apply_audio()
	_apply_window_mode()
	_save_pending = false
	save_settings()
	settings_changed.emit()


## Delays the write so a dragged slider does not hammer the disk.
func _queue_save() -> void:
	if _save_pending:
		return
	_save_pending = true
	var tree := get_tree()
	if tree == null:
		_save_pending = false
		save_settings()
		return
	var timer := tree.create_timer(_SAVE_DELAY, true, false, true)
	timer.timeout.connect(_flush_save, CONNECT_ONE_SHOT)


func _flush_save() -> void:
	if not _save_pending:
		return
	_save_pending = false
	save_settings()
