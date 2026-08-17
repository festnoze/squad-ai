extends Node
## Screenshot harness. Boots the real game, walks the camera through a handful of
## vantage points and lighting conditions, and writes a PNG for each one.
##
##   godot --path . -- --shot C:/some/output/dir
##
## Rendering quality is the one thing a headless assertion cannot judge, so this
## exists to put actual frames in front of a human (or a reviewing agent). It is
## not part of the automated suite and never fails a build.

## Vantage points. `offset` is added to the spawn point, `yaw` and `pitch` are in
## degrees, `time` is the time of day to force (negative leaves it alone).
const SHOTS: Array[Dictionary] = [
	{"name": "01_spawn_midday", "offset": Vector3(0, 0, 0), "yaw": 25.0, "pitch": -8.0, "time": 0.5},
	{"name": "02_landscape_high", "offset": Vector3(0, 34, 0), "yaw": 25.0, "pitch": -28.0, "time": 0.5},
	{"name": "03_landscape_far", "offset": Vector3(120, 44, 120), "yaw": 215.0, "pitch": -22.0, "time": 0.46},
	{"name": "04_sunrise", "offset": Vector3(0, 26, 0), "yaw": 90.0, "pitch": -6.0, "time": 0.255},
	{"name": "05_sunset", "offset": Vector3(0, 26, 0), "yaw": 270.0, "pitch": -6.0, "time": 0.775},
	{"name": "06_night", "offset": Vector3(0, 24, 0), "yaw": 40.0, "pitch": 6.0, "time": 0.02},
	{"name": "07_ground_detail", "offset": Vector3(0, 0, 0), "yaw": 0.0, "pitch": -42.0, "time": 0.52},
	{"name": "08_underground", "offset": Vector3(0, -26, 0), "yaw": 0.0, "pitch": -4.0, "time": 0.5},
]

## Frames to wait after moving before capturing, so streaming and the sky catch up.
const FRAMES_AFTER_MOVE := 40

## Hard cap on how long one vantage point may wait for its chunks.
const MAX_WAIT_FRAMES := 900

var _main: Node = null
var _out_dir: String = ""
var _running := false


func setup(main_node: Node, output_dir: String) -> void:
	_main = main_node
	_out_dir = output_dir.rstrip("/\\")


func _process(_delta: float) -> void:
	if _running or _main == null:
		return
	var world: VoxelWorld = _main.get_node_or_null("World")
	if world == null:
		return
	if world.loaded_chunk_count() <= 0 or world.pending_jobs() > 0:
		return
	_running = true
	_capture_all()


func _capture_all() -> void:
	var world: VoxelWorld = _main.get_node_or_null("World")
	var player: Player = _main.get_node_or_null("Player")
	var sky: SkyController = _main.get_node_or_null("Sky")
	var hud: Node = _main.get_node_or_null("Hud")
	if world == null or player == null:
		get_tree().quit(1)
		return

	# Drive the camera by hand: the controller would fight the placement with
	# gravity, and a falling player produces a different frame every capture.
	player.process_mode = Node.PROCESS_MODE_DISABLED
	if sky != null:
		sky.paused = true

	var spawn: Vector3 = world.spawn_point()
	var written: PackedStringArray = PackedStringArray()

	for shot in SHOTS:
		var target: Vector3 = spawn + (shot["offset"] as Vector3)
		target.y = clampf(target.y, 2.0, float(VoxelWorld.WORLD_HEIGHT) - 3.0)
		player.global_position = target
		player.rotation.y = deg_to_rad(float(shot["yaw"]))
		if player.head != null:
			player.head.rotation.x = deg_to_rad(float(shot["pitch"]))
		var when: float = float(shot["time"])
		if sky != null and when >= 0.0:
			sky.skip_to(when)

		# The world streams around the player, so wait for the new ring to land
		# before judging the frame. A timeout keeps a stubborn vantage point from
		# stalling the whole run.
		var waited := 0
		while world.pending_jobs() > 0 and waited < MAX_WAIT_FRAMES:
			await get_tree().process_frame
			waited += 1
		for _i in FRAMES_AFTER_MOVE:
			await get_tree().process_frame

		# One frame must actually be drawn before the viewport texture holds it.
		await RenderingServer.frame_post_draw
		var image: Image = get_viewport().get_texture().get_image()
		if image == null:
			push_warning("shot: viewport image indisponible pour %s" % shot["name"])
			continue
		var path: String = "%s/%s.png" % [_out_dir, shot["name"]]
		if image.save_png(path) == OK:
			written.append(path)
			print("shot ecrit : %s  (%dx%d)" % [path, image.get_width(), image.get_height()])
		else:
			push_warning("shot: echec d'ecriture de %s" % path)

	# Same view as shot 02 but with the interface hidden, to judge the world on
	# its own and the interface separately.
	if hud != null:
		hud.visible = false
		player.global_position = spawn + Vector3(0, 34, 0)
		player.rotation.y = deg_to_rad(25.0)
		if player.head != null:
			player.head.rotation.x = deg_to_rad(-28.0)
		if sky != null:
			sky.skip_to(0.5)
		var waited2 := 0
		while world.pending_jobs() > 0 and waited2 < MAX_WAIT_FRAMES:
			await get_tree().process_frame
			waited2 += 1
		for _i in FRAMES_AFTER_MOVE:
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var clean: Image = get_viewport().get_texture().get_image()
		if clean != null:
			var path2: String = "%s/09_landscape_no_hud.png" % _out_dir
			if clean.save_png(path2) == OK:
				written.append(path2)
				print("shot ecrit : %s" % path2)

	print("")
	print("%d captures ecrites dans %s" % [written.size(), _out_dir])
	world.shutdown()
	get_tree().quit(0)
