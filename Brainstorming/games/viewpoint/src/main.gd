extends Node3D
## Entry point. Wires the subsystems, owns the level lifecycle (build, fade,
## teleport, victory) and the pause flow. With "--smoke" in the user args it
## attaches the integration probe instead of waiting for a human.

@onready var world_environment: WorldEnvironment = $WorldEnvironment
@onready var level_root: Node3D = $LevelRoot
@onready var player: Player = $Player
@onready var hud: Hud = $Hud
@onready var menu: Menu = $Menu

## Time machine of the current level, built in _ready.
var rewind: Rewind

var _transitioning := false


## Pastel sky and soft fog. Ambient comes from the sky, with an explicit
## contribution below 1 so ambient_light_energy actually has an effect.
func _setup_environment() -> void:
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Palette.color("sky_top")
	sky_mat.sky_horizon_color = Palette.color("sky_horizon")
	sky_mat.ground_bottom_color = Palette.color("sky_horizon").darkened(0.15)
	sky_mat.ground_horizon_color = Palette.color("sky_horizon")
	var sky := Sky.new()
	sky.sky_material = sky_mat
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 0.5
	env.ambient_light_energy = 0.8
	env.fog_enabled = true
	env.fog_light_color = Palette.color("sky_horizon")
	env.fog_density = 0.0012
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	world_environment.environment = env


func _ready() -> void:
	_setup_environment()
	add_child(PhotoSnaps.new())
	rewind = Rewind.new()
	add_child(rewind)
	rewind.setup(player, level_root)
	player.setup(level_root)
	player.fell_out.connect(_on_player_fell)
	menu.start_requested.connect(_start_game)
	menu.resume_requested.connect(_resume)
	menu.restart_requested.connect(_start_game)
	menu.level_selected.connect(_start_at)
	menu.show_title()

	if OS.get_cmdline_user_args().has("--smoke"):
		var probe: Node = load("res://tests/smoke_probe.gd").new()
		probe.setup(self)
		add_child(probe)
	elif OS.get_cmdline_user_args().has("--shot"):
		var shot_probe: Node = load("res://tests/shot_probe.gd").new()
		shot_probe.setup(self)
		add_child(shot_probe)


func _unhandled_input(event: InputEvent) -> void:
	# Fullscreen works everywhere: in game, in the menus, during a fade.
	if event.is_action_pressed("toggle_fullscreen"):
		if DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN:
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
		else:
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
		return
	if menu.mode != Menu.Mode.HIDDEN or _transitioning:
		return
	if event.is_action_pressed("pause"):
		_pause()
	# R is not a key press but a hold: see _drive_rewind.


## Falling out is losing: the level restarts from scratch, placements and
## carried batteries included. Deferred because freeing collision bodies from
## inside a physics callback is not allowed.
func _on_player_fell() -> void:
	if _transitioning:
		return
	_restart_after_fall.call_deferred()


func _restart_after_fall() -> void:
	_load_level(Game.level_index)
	player.control_enabled = menu.mode == Menu.Mode.HIDDEN
	hud.show_toast("Chute : le niveau recommence a zero.")


## Rewind is a hold, not a press: R keeps scrubbing the history backwards for
## as long as it is down, and releasing it makes that moment the new present.
func _drive_rewind(delta: float) -> void:
	var wanted := Input.is_action_pressed("rewind") and menu.mode == Menu.Mode.HIDDEN and not _transitioning
	if wanted and not rewind.is_rewinding():
		rewind.start_rewind()
		player.control_enabled = false
	if wanted:
		rewind.step_rewind(delta)
	elif rewind.is_rewinding():
		rewind.stop_rewind()
		player.control_enabled = menu.mode == Menu.Mode.HIDDEN
	hud.set_rewinding(rewind.is_rewinding(), rewind.available_seconds())


## Playback rides the physics clock like the recording does, so a rewind
## unwinds the same amount of history whatever the frame rate.
func _physics_process(delta: float) -> void:
	_drive_rewind(delta)


func _process(_delta: float) -> void:
	hud.visible = menu.mode == Menu.Mode.HIDDEN
	if menu.mode == Menu.Mode.HIDDEN and not _transitioning:
		hud.set_prompt(player.interact_prompt)
		var held_id := player.placer.held_id
		hud.set_held(player.placer.held_title(), PhotoSnaps.get_texture(held_id) if held_id != "" else null, player.placer.raised)
		hud.set_photo_view(PhotoSnaps.get_texture(held_id) if player.placer.raised else null, player.placer.roll_steps)
		hud.set_viewfinder(player.viewfinder)
	else:
		hud.set_prompt("")
		hud.set_photo_view(null)
		hud.set_viewfinder(false)


func _start_game() -> void:
	_start_at(0)


## Entry point of the level-select menu. reset() clears the run, not the
## persisted progression, so the other unlocked levels stay unlocked.
func _start_at(index: int) -> void:
	if not Game.is_level_unlocked(index):
		return
	Game.reset()
	menu.hide_menu()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_load_level(index)
	player.control_enabled = true


func _resume() -> void:
	menu.hide_menu()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	player.control_enabled = true


func _pause() -> void:
	player.control_enabled = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	menu.show_pause()


func _load_level(index: int) -> void:
	# Immediate free, not queue_free: the old level's group members (carvable,
	# photo_item...) must be gone before the new level starts querying groups.
	for child in level_root.get_children():
		level_root.remove_child(child)
		child.free()
	# A held photo does not survive the jump: photos belong to their level.
	if player.placer.held_id != "":
		player.placer.drop()
		for child in level_root.get_children():
			level_root.remove_child(child)
			child.free()

	# Photos taken with the camera belong to their level, like placed content.
	PhotoDefs.clear_dynamic()

	var def := LevelDefs.get_def(index)
	var teleporter := LevelBuilder.build(level_root, def)
	teleporter.depart_requested.connect(_on_depart)
	player.set_spawn(def["spawn"], def["spawn_yaw"], def["kill_y"])
	Game.begin_level(index, def["teleporter"]["required"])
	hud.show_banner("Niveau %d : %s" % [index + 1, def["name"]], def["subtitle"])
	hud.fade_in()
	# History belongs to a level: a fresh one starts from this exact state.
	rewind.begin_level()


func _on_depart() -> void:
	if _transitioning:
		return
	_transitioning = true
	player.control_enabled = false
	await hud.fade_out()
	if Game.has_next_level():
		Game.advance_level()
		_load_level(Game.level_index)
		player.control_enabled = true
		_transitioning = false
	else:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		menu.show_victory()
		hud.fade_in()
		_transitioning = false
