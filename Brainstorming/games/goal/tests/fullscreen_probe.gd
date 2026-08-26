extends SceneTree
## Probe: proves F11 really toggles the window mode.
##
##   godot --path . --script res://tests/fullscreen_probe.gd
##
## Needs a real window, so it must NOT be run with --headless.
##
## Godot does not register the project autoloads under --script, so this probe
## instantiates src/core/game.gd itself and mounts it as "Game". That is enough,
## because the window mode logic is entirely inside that one file.
##
## The F11 press is synthesised through the input queue rather than by calling
## toggle_fullscreen() directly, so the whole chain is under test: the InputMap
## binding, the autoload's _input handler, and DisplayServer.

var _game: Node = null
var _frames := 0
var _step := 0
var _checks := 0
var _failures: PackedStringArray = PackedStringArray()


func _initialize() -> void:
	var script: Script = load("res://src/core/game.gd")
	_game = script.new()
	_game.name = "Game"
	root.add_child(_game)


func _is_full() -> bool:
	var mode := DisplayServer.window_get_mode()
	return (
		mode == DisplayServer.WINDOW_MODE_FULLSCREEN
		or mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN
	)


func _ok(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)


func _tap_f11() -> void:
	var down := InputEventKey.new()
	down.physical_keycode = KEY_F11
	down.pressed = true
	Input.parse_input_event(down)
	var up := InputEventKey.new()
	up.physical_keycode = KEY_F11
	up.pressed = false
	Input.parse_input_event(up)


func _process(_delta: float) -> bool:
	_frames += 1
	# A window needs a few frames to settle after a mode change, so the steps are
	# spaced out rather than run back to back.
	if _frames % 40 != 0:
		return false

	match _step:
		0:
			_ok(InputMap.has_action("fullscreen"),
					"l'action fullscreen n'existe pas")
			var bound := false
			for event in InputMap.action_get_events("fullscreen"):
				var key := event as InputEventKey
				if key != null and key.physical_keycode == KEY_F11:
					bound = true
			_ok(bound, "F11 n'est pas liee a l'action fullscreen")
			_ok(not _is_full(), "la sonde doit demarrer en fenetre")
			_tap_f11()
		1:
			_ok(_is_full(), "F11 n'a pas bascule en plein ecran")
			_ok(bool(_game.get("fullscreen")),
					"le reglage fullscreen est reste faux apres bascule")
			_tap_f11()
		2:
			_ok(not _is_full(), "un second F11 n'est pas revenu en fenetre")
			_ok(not bool(_game.get("fullscreen")),
					"le reglage fullscreen n'est pas revenu a false")
			_report()
			return true
	_step += 1
	return false


func _report() -> void:
	print("")
	print("=== GOAL - sonde plein ecran ===")
	for message in _failures:
		print("  ECHEC  %s" % message)
	print("")
	print("  %d verifications, %d echecs" % [_checks, _failures.size()])
	print("================================")
	print("")
	if _failures.size() > 0:
		quit(1)
	else:
		quit(0)
