extends Node
## Autoload "Game". Owns the campaign progression (which level, how many
## batteries carried and inserted) and registers the InputMap actions in code,
## which is more robust than hand-serialized [input] sections and keeps the
## project file readable.
##
## This script deliberately references no other autoload and no scene node, so
## the unit suites can load() and exercise it headless.

signal batteries_changed(carried: int, inserted: int, required: int)
signal level_started(index: int)

var level_index := 0
var carried_batteries := 0
var inserted_batteries := 0
var required_batteries := 0

## Highest level index ever reached, persisted across sessions. Drives the
## level-select menu: a level is playable once it has been reached.
var furthest_level := 0

const PROGRESS_PATH := "user://progress.cfg"


func _init() -> void:
	_register_inputs()


func _ready() -> void:
	load_progress()


func reset() -> void:
	level_index = 0
	carried_batteries = 0
	inserted_batteries = 0
	required_batteries = 0


func begin_level(index: int, required: int) -> void:
	level_index = index
	carried_batteries = 0
	inserted_batteries = 0
	required_batteries = required
	if index > furthest_level:
		furthest_level = index
		save_progress()
	level_started.emit(index)
	batteries_changed.emit(carried_batteries, inserted_batteries, required_batteries)


func is_level_unlocked(index: int) -> bool:
	return index >= 0 and index < LevelDefs.count() and index <= furthest_level


func load_progress(path := PROGRESS_PATH) -> void:
	var cfg := ConfigFile.new()
	if cfg.load(path) == OK:
		furthest_level = clampi(int(cfg.get_value("progress", "furthest_level", 0)), 0, LevelDefs.count() - 1)


func save_progress(path := PROGRESS_PATH) -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("progress", "furthest_level", furthest_level)
	cfg.save(path)


func collect_battery() -> void:
	carried_batteries += 1
	batteries_changed.emit(carried_batteries, inserted_batteries, required_batteries)


## Moves carried batteries into the teleporter, up to the requirement.
## Returns how many were actually inserted.
func insert_batteries() -> int:
	var wanted := required_batteries - inserted_batteries
	var moved := mini(carried_batteries, maxi(wanted, 0))
	if moved <= 0:
		return 0
	carried_batteries -= moved
	inserted_batteries += moved
	batteries_changed.emit(carried_batteries, inserted_batteries, required_batteries)
	return moved


func can_teleport() -> bool:
	return required_batteries > 0 and inserted_batteries >= required_batteries


func has_next_level() -> bool:
	return level_index + 1 < LevelDefs.count()


func advance_level() -> void:
	level_index += 1


func _register_inputs() -> void:
	_key_action("move_forward", KEY_W)
	_key_action("move_back", KEY_S)
	_key_action("move_left", KEY_A)
	_key_action("move_right", KEY_D)
	_key_action("jump", KEY_SPACE)
	_key_action("sprint", KEY_SHIFT)
	_key_action("interact", KEY_E)
	_key_action("reset_level", KEY_R)
	_key_action("toggle_fullscreen", KEY_F11)
	_key_action("ui_start", KEY_ENTER)
	_key_action("pause", KEY_ESCAPE)
	_mouse_action("place_photo", MOUSE_BUTTON_LEFT)
	_mouse_action("drop_photo", MOUSE_BUTTON_RIGHT)
	_mouse_action("rotate_photo_cw", MOUSE_BUTTON_WHEEL_DOWN)
	_mouse_action("rotate_photo_ccw", MOUSE_BUTTON_WHEEL_UP)


func _key_action(action: String, physical_key: Key) -> void:
	if InputMap.has_action(action):
		return
	InputMap.add_action(action)
	var ev := InputEventKey.new()
	ev.physical_keycode = physical_key
	InputMap.action_add_event(action, ev)


func _mouse_action(action: String, button: MouseButton) -> void:
	if InputMap.has_action(action):
		return
	InputMap.add_action(action)
	var ev := InputEventMouseButton.new()
	ev.button_index = button
	InputMap.action_add_event(action, ev)
