extends Node
## Screenshot probe. Needs a real window (not --headless):
##
##   godot --path . -- --shot
##
## Boots the game, walks through every level, and in each one captures a frame
## from the player's point of view plus one with the ghost preview up, into
## user://shots/. Meant for a human (or an agent) to eyeball the rendering.

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

	# Ghost preview of the bridge photo, from the level 1 gap edge.
	_main._load_level(0)
	await _frames_pass(30)
	player.placer.hold("passerelle")
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(10)
	await _shot("ghost_bridge")
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
	await _shot("ghost_door")
	player.placer.place()
	await _frames_pass(10)
	await _shot("placed_door")
	player.global_position = Vector3(0, 0.05, 10)
	await _frames_pass(10)
	await _shot("placed_door_wide")

	print("  shots dans %s" % ProjectSettings.globalize_path("user://shots"))
	get_tree().quit(0)
