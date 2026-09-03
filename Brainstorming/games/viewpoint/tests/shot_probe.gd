extends Node
## Screenshot probe. Needs a real window (not --headless):
##
##   godot --path . -- --shot
##
## Boots the game, walks through every level, and in each one captures a frame
## from the player's point of view, plus the key v4 moments (photo raised on
## the HUD, world replaced by a placement), into user://shots/. Meant for a
## human (or an agent) to eyeball the rendering.

var _main: Node3D


func setup(main_node: Node3D) -> void:
	_main = main_node


func _ready() -> void:
	_run()


func _frames_pass(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	DirAccess.make_dir_recursive_absolute("user://shots")
	img.save_png("user://shots/%s.png" % name)
	print("  shot: %s" % name)


func _run() -> void:
	await _frames_pass(10)
	await _shot("title_menu")
	_main._start_game()
	await _frames_pass(80)
	var player: CharacterBody3D = _main.player

	for i in LevelDefs.count():
		_main._load_level(i)
		await _frames_pass(40)
		await _shot("level_%d" % (i + 1))

	# Aiming the bridge photo from the level 1 gap edge, then the result: there
	# is no 3D preview anymore, the deck only appears at placement.
	_main._load_level(0)
	await _frames_pass(30)
	player.placer.hold("passerelle")
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(10)
	await _shot("aim_bridge")
	player.placer.place()
	await _frames_pass(10)
	await _shot("placed_bridge")

	# The door photo placed on level 4's wall: the framed part of the wall is
	# carved out, the flanks stay, the door wall stands where it was aimed.
	_main._load_level(3)
	await _frames_pass(30)
	player.placer.hold("porte")
	player.global_position = Vector3(0, 0.05, 1.5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(10)
	await _shot("aim_door")
	player.placer.place()
	await _frames_pass(10)
	await _shot("placed_door")
	player.global_position = Vector3(0, 0.05, 10)
	await _frames_pass(10)
	await _shot("placed_door_wide")

	# Walk through the door and look back: the ground runs through it.
	player.global_position = Vector3(0, 0.3, -3.0)
	player.rotation = Vector3.ZERO
	player.control_enabled = true
	Input.action_press("move_forward")
	for i in 120:
		await get_tree().physics_frame
	Input.action_release("move_forward")
	for i in 20:
		await get_tree().physics_frame
	await _shot("door_walked_through")
	player.rotation = Vector3(0, PI, 0)
	for i in 5:
		await get_tree().physics_frame
	await _shot("door_looking_back")
	player.control_enabled = false

	# The raised photo (right click): the rendered picture aligned on the
	# placement frustum, then the identical content once placed.
	_main._load_level(0)
	await _frames_pass(30)
	player.placer.hold("passerelle")
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(10)
	await _shot("held_card")
	player.placer.raise_toggle()
	await _frames_pass(10)
	await _shot("raised_photo")
	player.placer.place()
	await _frames_pass(10)
	await _shot("raised_photo_placed")

	# The camera of level 16: framing the lavender plank, then the shot held.
	_main._load_level(15)
	await _frames_pass(30)
	Game.add_films(2)
	player.global_position = Vector3(4, 0.05, 8)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(5)
	await _shot("camera_lowered")
	# Right click first: the viewfinder frames what the shot would capture.
	player.toggle_viewfinder()
	await _frames_pass(5)
	await _shot("camera_framing")
	player.capture_photo()
	await _frames_pass(20)
	await _shot("camera_cliche")

	# Rewind: place a bridge, then hold R and catch the world unwinding.
	_main._load_level(0)
	await _frames_pass(40)
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	player.placer.hold("passerelle")
	for i in 60:
		await get_tree().physics_frame
	player.placer.place()
	for i in 60:
		await get_tree().physics_frame
	Input.action_press("rewind")
	for i in 30:
		await get_tree().physics_frame
	await _shot("rewinding")
	Input.action_release("rewind")

	print("  shots dans %s" % ProjectSettings.globalize_path("user://shots"))
	get_tree().quit(0)
