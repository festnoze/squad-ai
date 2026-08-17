extends Node3D
## Entry point. Owns nothing but wiring: it builds the inventory, calls setup on
## every subsystem in dependency order, routes the input that does not belong to
## a single subsystem, and makes sure the world is saved before the process ends.

@onready var world: VoxelWorld = $World
@onready var player: Player = $Player
@onready var interaction: Interaction = $Interaction
@onready var settlements: SettlementManager = $Settlements
@onready var world_environment: WorldEnvironment = $WorldEnvironment
@onready var sun: DirectionalLight3D = $Sun
@onready var moon: DirectionalLight3D = $Moon
@onready var sky: SkyController = $Sky
@onready var hud: Hud = $Hud
@onready var inventory_ui: InventoryUi = $Screens/InventoryUi
@onready var pause_menu: PauseMenu = $Screens/PauseMenu

var inventory: Inventory

var _quitting := false


func _ready() -> void:
	# Closing the window has to run through _quit_game so the world is written
	# to disk first, which means intercepting the request rather than letting
	# the tree tear itself down.
	get_tree().auto_accept_quit = false

	inventory = Inventory.new()
	inventory.creative = Game.creative

	# Order matters: the world builds the texture atlas and the materials that
	# the interface and the chunk nodes both need, so it goes first.
	world.setup(Game.world_seed, "monde")
	sky.setup(world_environment, sun, moon)

	player.setup(world)
	player.teleport(world.spawn_point())
	settlements.setup(world, player)
	interaction.setup(world, player, inventory)
	inventory_ui.setup(inventory)
	hud.setup(world, player, inventory, interaction, sky)

	inventory_ui.closed.connect(_on_screen_closed)
	pause_menu.resume_requested.connect(_on_screen_closed)
	pause_menu.save_requested.connect(_on_save_requested)
	pause_menu.quit_requested.connect(_quit_game)

	player.footstep.connect(_on_footstep)
	player.entered_water.connect(_on_entered_water)
	Game.settings_changed.connect(_on_settings_changed)

	_capture_mouse()
	_maybe_start_smoke_probe()
	_maybe_start_shot_probe()
	_maybe_start_generic_probe()


## Integration test hook. The probe has to live inside the real boot path,
## because Godot only registers the project autoloads for the default main loop
## and most of the project refers to Game, so a --script harness cannot even
## compile. Run it with: godot --headless --path . -- --smoke
func _maybe_start_smoke_probe() -> void:
	if not OS.get_cmdline_user_args().has("--smoke"):
		return
	if not ResourceLoader.exists("res://tests/smoke_probe.gd"):
		push_warning("--smoke demande mais tests/smoke_probe.gd est absent")
		return
	var probe_script: Script = load("res://tests/smoke_probe.gd")
	if probe_script == null:
		return
	var probe: Node = probe_script.new()
	probe.name = "SmokeProbe"
	add_child(probe)
	probe.setup(self)


## Screenshot harness hook: godot --path . -- --shot C:/output/dir
func _maybe_start_shot_probe() -> void:
	var user_args := OS.get_cmdline_user_args()
	var index := user_args.find("--shot")
	if index < 0 or index + 1 >= user_args.size():
		return
	if not ResourceLoader.exists("res://tests/shot_probe.gd"):
		push_warning("--shot demande mais tests/shot_probe.gd est absent")
		return
	var shot_script: Script = load("res://tests/shot_probe.gd")
	if shot_script == null:
		return
	var probe: Node = shot_script.new()
	probe.name = "ShotProbe"
	add_child(probe)
	probe.setup(self, user_args[index + 1])


## Generic diagnostic hook: godot --path . -- --probe res://tests/whatever.gd
## The probe receives setup(self) and is expected to quit the tree when finished.
func _maybe_start_generic_probe() -> void:
	var user_args := OS.get_cmdline_user_args()
	var index := user_args.find("--probe")
	if index < 0 or index + 1 >= user_args.size():
		return
	var path := user_args[index + 1]
	if not ResourceLoader.exists(path):
		push_warning("--probe: %s est introuvable" % path)
		return
	var probe_script: Script = load(path)
	if probe_script == null:
		return
	var probe: Node = probe_script.new()
	probe.name = "Probe"
	add_child(probe)
	probe.setup(self)


func _process(delta: float) -> void:
	world.update_streaming(player.global_position)
	VoxelMaterials.set_time(world.materials(), sky.time_of_day)
	# Wind eases off at night, which reads as the world settling down.
	var wind: float = 0.75 + 0.35 * sin(Time.get_ticks_msec() * 0.00013)
	if sky.is_night():
		wind *= 0.55
	VoxelMaterials.set_wind(world.materials(), wind)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("pause"):
		_toggle_pause()
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("inventory"):
		_toggle_inventory()
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("screenshot"):
		_take_screenshot()
		get_viewport().set_input_as_handled()
		return

	if _any_screen_open():
		return

	if event.is_action_pressed("time_forward"):
		sky.skip_to(sky.time_of_day + 0.045)
		hud.show_toast("Heure : %s" % sky.time_string())
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("hotbar_next"):
		inventory.cycle(1)
		return
	if event.is_action_pressed("hotbar_prev"):
		inventory.cycle(-1)
		return

	for i in Inventory.HOTBAR_SLOTS:
		if event.is_action_pressed("hotbar_%d" % (i + 1)):
			inventory.select(i)
			return


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

func _any_screen_open() -> bool:
	return inventory_ui.is_open() or pause_menu.is_open()


func _toggle_inventory() -> void:
	if pause_menu.is_open():
		return
	if inventory_ui.is_open():
		inventory_ui.close()
	else:
		inventory_ui.open()
	_sync_screen_state()


## Escape closes whatever is on top rather than always opening the pause menu,
## so the key never stacks two screens.
func _toggle_pause() -> void:
	if inventory_ui.is_open():
		inventory_ui.close()
	elif pause_menu.is_open():
		pause_menu.close()
	else:
		pause_menu.open()
	_sync_screen_state()


func _on_screen_closed() -> void:
	if inventory_ui.is_open():
		inventory_ui.close()
	if pause_menu.is_open():
		pause_menu.close()
	_sync_screen_state()


## A single place decides whether the player is driving or a menu is. Leaving
## this to the individual screens is how the mouse ends up captured behind an
## open panel.
func _sync_screen_state() -> void:
	var open := _any_screen_open()
	player.process_mode = Node.PROCESS_MODE_DISABLED if open else Node.PROCESS_MODE_INHERIT
	interaction.process_mode = Node.PROCESS_MODE_DISABLED if open else Node.PROCESS_MODE_INHERIT
	hud.set_paused(open)
	if open:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	else:
		_capture_mouse()


func _capture_mouse() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

func _on_footstep(block_id: int) -> void:
	Sfx.play_step(block_id, player.global_position)


func _on_entered_water() -> void:
	Sfx.play_at("splash", player.global_position)


func _on_settings_changed() -> void:
	inventory.creative = Game.creative
	player.set_fly_mode(Game.fly_mode and Game.creative)
	if player.camera != null:
		player.camera.fov = Game.fov
	hud.refresh_settings()


func _on_save_requested() -> void:
	world.save_all()
	hud.show_toast("Monde sauvegardé")


func _take_screenshot() -> void:
	var image := get_viewport().get_texture().get_image()
	var dir := "user://screenshots"
	DirAccess.make_dir_recursive_absolute(dir)
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var path := "%s/cubeforge_%s.png" % [dir, stamp]
	if image.save_png(path) == OK:
		hud.show_toast("Capture enregistrée")
	else:
		hud.show_toast("Échec de la capture")


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_quit_game()


func _quit_game() -> void:
	if _quitting:
		return
	_quitting = true
	Game.save_settings()
	world.shutdown()
	get_tree().quit()
