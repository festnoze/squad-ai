extends Node3D
## Entry point. Wires the subsystems, owns the level lifecycle (build, fade,
## teleport, victory) and the pause flow. With "--smoke" in the user args it
## attaches the integration probe instead of waiting for a human.

@onready var world_environment: WorldEnvironment = $WorldEnvironment
@onready var level_root: Node3D = $LevelRoot
@onready var player: Player = $Player
@onready var hud: Hud = $Hud
@onready var menu: Menu = $Menu

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
	player.setup(level_root)
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
	elif event.is_action_pressed("reset_level"):
		# Photos are consumable, so a complex level can be spent into a dead
		# end. R rebuilds the current level from its definition.
		_load_level(Game.level_index)


func _process(_delta: float) -> void:
	hud.visible = menu.mode == Menu.Mode.HIDDEN
	if menu.mode == Menu.Mode.HIDDEN and not _transitioning:
		hud.set_prompt(player.interact_prompt)
		hud.set_held(player.placer.held_title())
	else:
		hud.set_prompt("")


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
	# Immediate free, not queue_free: the old level's group members (erasable,
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

	var def := LevelDefs.get_def(index)
	var teleporter := LevelBuilder.build(level_root, def)
	teleporter.depart_requested.connect(_on_depart)
	player.set_spawn(def["spawn"], def["spawn_yaw"], def["kill_y"])
	Game.begin_level(index, def["teleporter"]["required"])
	hud.show_banner("Niveau %d : %s" % [index + 1, def["name"]], def["subtitle"])
	hud.fade_in()


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
