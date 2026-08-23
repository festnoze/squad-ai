extends Node
## Screenshot harness. Walks the camera through a handful of set pieces and
## writes a PNG of each, so the rendering can actually be looked at instead of
## guessed at.
##
##   godot --path . -- --shot C:/some/output/dir
##
## It deliberately avoids `await`: a coroutine whose caller never awaits it stops
## forever the moment the tree quits, silently. A frame counted state machine
## cannot fall into that trap.

var _main: Node3D
var _out_dir: String
var _frames := 0
var _index := -1
var _wait := 0
var _shots: Array = []

## Frames spent streaming before the first shot, then between two shots. The
## world generates on worker threads, so a shot taken too early is a grey void.
const BOOT_FRAMES := 200
const SETTLE_FRAMES := 110


func setup(main_node: Node3D, out_dir: String) -> void:
	_main = main_node
	_out_dir = out_dir
	DirAccess.make_dir_recursive_absolute(_out_dir)
	# The probe drives the camera itself, so it has no use for the mouse. Give
	# the cursor back: this harness runs on the developer's desktop and must not
	# confiscate the pointer for the length of the capture run.
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	# Judge the rendering in the reference condition, not in whatever weather the
	# campaign seed happened to roll. A storm at dusk hides every lighting defect
	# behind its own murk, which makes the captures useless for tuning.
	if _main.sky != null:
		_main.sky.skip_to(0.46)
		_main.sky.set_process(false)
	if _main.weather != null:
		_main.weather.set_weather(Weather.CLEAR, 0.0)


func _build_shot_list() -> void:
	var layout: Layout = _main.world.layout()
	_shots.append({"name": "01_spawn", "pos": _main.world.spawn_point(), "yaw": 0.0, "pitch": -0.1})
	# One shot per interesting site kind, framed from outside looking in.
	var wanted := [Layout.SITE_VILLAGE, Layout.SITE_CHURCH_TOWN, Layout.SITE_FARM,
			Layout.SITE_AIRFIELD, Layout.SITE_BUNKER, Layout.SITE_CAMP,
			Layout.SITE_BRIDGE, Layout.SITE_RUIN]
	var taken := {}
	for kind in wanted:
		for site in layout.sites:
			if site.kind != kind or taken.has(site.id):
				continue
			taken[site.id] = true
			var offset := site.radius + 30.0
			var pos := Vector3(site.center.x - offset, 0.0, site.center.y - offset)
			pos.y = _main.world.ground_y(pos.x, pos.z) + 6.0
			_shots.append({
				"name": "%02d_%s" % [_shots.size() + 1, _kind_slug(kind)],
				"pos": pos,
				"yaw": PI * 0.25,
				"pitch": -0.18,
			})
			break
	# A wide landscape shot, high up, to judge the terrain and the fog.
	var high := Vector3(0.0, 0.0, 0.0)
	high.y = _main.world.ground_y(0.0, 0.0) + 55.0
	_shots.append({"name": "%02d_paysage" % (_shots.size() + 1), "pos": high,
			"yaw": 0.6, "pitch": -0.22})


func _kind_slug(kind: int) -> String:
	match kind:
		Layout.SITE_VILLAGE: return "village"
		Layout.SITE_CHURCH_TOWN: return "bourg"
		Layout.SITE_FARM: return "ferme"
		Layout.SITE_AIRFIELD: return "aerodrome"
		Layout.SITE_BUNKER: return "bunker"
		Layout.SITE_CAMP: return "camp"
		Layout.SITE_BRIDGE: return "pont"
		Layout.SITE_RUIN: return "ruines"
		_: return "site"


func _process(_delta: float) -> void:
	# Main re-rolls the weather once per in game hour, which would undo the
	# reference condition set in setup(). Re-assert it every frame instead of
	# reaching into Main's private state.
	if _main.weather != null and _main.weather.kind != Weather.CLEAR:
		_main.weather.set_weather(Weather.CLEAR, 0.0)
	_frames += 1
	if _frames < BOOT_FRAMES:
		return
	if _index < 0:
		_build_shot_list()
		_index = 0
		_move_to(_shots[0])
		_wait = SETTLE_FRAMES
		return
	if _wait > 0:
		_wait -= 1
		# Keep streaming while we wait, the camera just teleported far away.
		_main.world.update_streaming(_main.player.global_position)
		# Teleporting lands the player over a tile that has no collision yet, so
		# he free falls and ends up UNDER the terrain once it finally appears,
		# which frames the shot on the underside of the world. Main's own guard
		# only covers the initial spawn, so the probe re-seats him itself until
		# the ground is actually there.
		_reseat_if_fallen()
		return

	_capture(_shots[_index]["name"])
	_index += 1
	if _index >= _shots.size():
		if _main.has_method("_shutdown_world"):
			_main.call("_shutdown_world")
		get_tree().quit(0)
		return
	_move_to(_shots[_index])
	_wait = SETTLE_FRAMES


## Puts the player back on top of the terrain whenever he has dropped through it,
## and holds him still so he does not build up fall speed while the chunk under
## him is still being meshed on a worker.
func _reseat_if_fallen() -> void:
	var player: Player = _main.player
	var pos: Vector3 = player.global_position
	var ground: float = _main.world.ground_y(pos.x, pos.z)
	if pos.y > ground - 1.0 and pos.y < ground + 40.0:
		return
	player.teleport(Vector3(pos.x, ground + 1.2, pos.z))
	player.velocity = Vector3.ZERO


func _move_to(shot: Dictionary) -> void:
	var player: Player = _main.player
	player.teleport(shot["pos"])
	if player.rig != null:
		player.rig.yaw = shot["yaw"]
		player.rig.pitch = shot["pitch"]


func _capture(shot_name: String) -> void:
	var image := get_viewport().get_texture().get_image()
	if image == null:
		push_warning("capture impossible pour %s" % shot_name)
		return
	var path := "%s/%s.png" % [_out_dir, shot_name]
	if image.save_png(path) != OK:
		push_warning("echec de l'ecriture de %s" % path)
