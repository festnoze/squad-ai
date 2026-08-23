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
var monsters: MonsterManager
var gravity: GravityManager
var growth: GrowthManager
var crafting_ui: CraftingUi
var chest_store: ChestStore
var chest_ui: ChestUi
var worlds_ui: WorldsUi
var map_ui: MapUi

var _quitting := false

## Search radius, in blocks, of the "am I near a crafting table" scan.
const TABLE_REACH := 3


func _ready() -> void:
	# Closing the window has to run through _quit_game so the world is written
	# to disk first, which means intercepting the request rather than letting
	# the tree tear itself down.
	get_tree().auto_accept_quit = false

	inventory = Inventory.new()
	inventory.creative = Game.creative

	# Order matters: the world builds the texture atlas and the materials that
	# the interface and the chunk nodes both need, so it goes first.
	world.setup(Game.world_seed, Game.world_name)
	VoxelMaterials.set_realistic(world.materials(), Game.realistic)
	sky.setup(world_environment, sun, moon)

	player.setup(world)
	player.teleport(world.spawn_point())
	settlements.setup(world, player)
	interaction.setup(world, player, inventory)
	inventory_ui.setup(inventory)
	hud.setup(world, player, inventory, interaction, sky)

	# Night-time hostiles and their arrows, survival only (the manager watches
	# Game.creative and the sky on its own).
	monsters = MonsterManager.new()
	monsters.name = "Monsters"
	add_child(monsters)
	monsters.setup(world, player, sky)
	monsters.loot_dropped.connect(_on_loot_dropped)
	interaction.set_combat(monsters)

	# Sand and gravel fall when unsupported, listening to world block edits.
	# Sits at the scene origin: the falling visuals use world coordinates.
	gravity = GravityManager.new()
	gravity.name = "Gravity"
	add_child(gravity)
	gravity.setup(world)

	# Sapling growth: planted saplings become oaks after a random delay.
	growth = GrowthManager.new()
	growth.name = "Growth"
	add_child(growth)
	growth.setup(world)

	crafting_ui = CraftingUi.new()
	crafting_ui.name = "CraftingUi"
	$Screens.add_child(crafting_ui)
	crafting_ui.setup(inventory)
	crafting_ui.closed.connect(_on_screen_closed)
	interaction.crafting_requested.connect(_on_crafting_table_used)

	chest_store = ChestStore.new()
	chest_ui = ChestUi.new()
	chest_ui.name = "ChestUi"
	$Screens.add_child(chest_ui)
	chest_ui.setup(inventory, chest_store)
	chest_ui.closed.connect(_on_screen_closed)
	interaction.chest_requested.connect(_on_chest_requested)
	world.block_changed.connect(_on_block_changed_for_chests)

	worlds_ui = WorldsUi.new()
	worlds_ui.name = "WorldsUi"
	$Screens.add_child(worlds_ui)
	worlds_ui.setup()
	worlds_ui.closed.connect(_on_screen_closed)
	worlds_ui.world_chosen.connect(_on_world_chosen)
	pause_menu.worlds_requested.connect(_on_worlds_requested)

	map_ui = MapUi.new()
	map_ui.name = "MapUi"
	$Screens.add_child(map_ui)
	map_ui.setup(world, player)
	map_ui.closed.connect(_on_screen_closed)

	inventory_ui.closed.connect(_on_screen_closed)
	pause_menu.resume_requested.connect(_on_screen_closed)
	pause_menu.save_requested.connect(_on_save_requested)
	pause_menu.quit_requested.connect(_quit_game)

	player.footstep.connect(_on_footstep)
	player.entered_water.connect(_on_entered_water)
	player.health_changed.connect(_on_health_changed)
	player.damaged.connect(_on_player_damaged)
	player.died.connect(_on_player_died)
	Game.settings_changed.connect(_on_settings_changed)

	_restore_player_data()
	hud.set_health(player.health, Player.MAX_HEALTH)

	_apply_fullscreen()
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

	if event.is_action_pressed("craft"):
		_toggle_crafting()
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("map"):
		_toggle_map()
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("fullscreen"):
		Game.fullscreen = not Game.fullscreen
		Game.save_settings()
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

## Every overlay screen except the pause menu, in closing priority order.
func _overlays() -> Array:
	return [inventory_ui, crafting_ui, chest_ui, worlds_ui, map_ui]


func _any_screen_open() -> bool:
	if pause_menu.is_open():
		return true
	for screen in _overlays():
		if screen.is_open():
			return true
	return false


func _close_overlays() -> void:
	for screen in _overlays():
		if screen.is_open():
			screen.close()


func _toggle_inventory() -> void:
	if pause_menu.is_open():
		return
	var was_open: bool = inventory_ui.is_open()
	_close_overlays()
	if not was_open:
		inventory_ui.open()
	_sync_screen_state()


## The craft key opens the recipe book anywhere. Table recipes stay locked
## unless a crafting table stands within reach of the player.
func _toggle_crafting() -> void:
	if pause_menu.is_open():
		return
	var was_open: bool = crafting_ui.is_open()
	_close_overlays()
	if not was_open:
		crafting_ui.open(_table_nearby())
	_sync_screen_state()


## The map key surveys the terrain around the player, exclusive with the other
## screens like the inventory.
func _toggle_map() -> void:
	if pause_menu.is_open():
		return
	var was_open: bool = map_ui.is_open()
	_close_overlays()
	if not was_open:
		map_ui.open()
	_sync_screen_state()


## Right click on a placed table: full recipe access.
func _on_crafting_table_used() -> void:
	if _any_screen_open():
		return
	crafting_ui.open(true)
	_sync_screen_state()


## Right click on a placed chest: open its contents.
func _on_chest_requested(cell: Vector3i) -> void:
	if _any_screen_open():
		return
	chest_ui.open(cell)
	_sync_screen_state()


## Breaking a chest spills its contents into the player inventory.
func _on_block_changed_for_chests(cell: Vector3i, old_id: int, new_id: int) -> void:
	if old_id != Blocks.CHEST or new_id == Blocks.CHEST:
		return
	# A creeper can destroy the chest while its screen is open: close it, or
	# the next click would recreate a phantom record at an empty cell.
	if chest_ui.is_open() and chest_ui.open_cell() == cell:
		chest_ui.close()
		_sync_screen_state()
	var leftover := chest_store.dump_into(cell, inventory)
	if leftover > 0:
		hud.show_toast("Coffre cassé : %d objets perdus" % leftover, 2.4)


func _on_worlds_requested() -> void:
	# Close the pause menu first: its close() emits resume_requested, which
	# runs _on_screen_closed while the worlds screen is not open yet.
	if pause_menu.is_open():
		pause_menu.close()
	worlds_ui.open()
	_sync_screen_state()


func _on_world_chosen(new_world_name: String, new_world_seed: int) -> void:
	# Airborne sand/gravel already left the voxel grid: write it back first,
	# or the save flushed by shutdown() would lose those blocks.
	gravity.settle_all()
	_store_player_data()
	if new_world_seed != 0:
		Game.world_seed = new_world_seed
	Game.world_name = new_world_name
	Game.save_settings()
	# shutdown() MUST run before the reload: it drains the job queue and joins
	# the worker threads with wait_to_finish(). The workers park on a semaphore
	# owned by this VoxelWorld node, so reloading the scene while they run
	# would free the node under them and nobody would ever join them; the
	# process then hangs on exit. shutdown() also flushes every edited chunk.
	world.shutdown()
	get_tree().reload_current_scene()


## True when a crafting table block sits within TABLE_REACH of the player feet.
func _table_nearby() -> bool:
	var base := Vector3i(floori(player.global_position.x),
			floori(player.global_position.y + 0.9), floori(player.global_position.z))
	for dy in range(-TABLE_REACH, TABLE_REACH + 1):
		for dx in range(-TABLE_REACH, TABLE_REACH + 1):
			for dz in range(-TABLE_REACH, TABLE_REACH + 1):
				if world.get_block(base.x + dx, base.y + dy, base.z + dz) == Blocks.CRAFTING_TABLE:
					return true
	return false


## Escape closes whatever is on top rather than always opening the pause menu,
## so the key never stacks two screens.
func _toggle_pause() -> void:
	var overlay_open := false
	for screen in _overlays():
		if screen.is_open():
			overlay_open = true
			break
	if overlay_open:
		_close_overlays()
	elif pause_menu.is_open():
		pause_menu.close()
	else:
		pause_menu.open()
	_sync_screen_state()


func _on_screen_closed() -> void:
	_close_overlays()
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


## Pushes the fullscreen setting onto the window. Skipped without a real
## windowing server, so the headless harnesses stay unaffected.
func _apply_fullscreen() -> void:
	if DisplayServer.get_name() == "headless":
		return
	var wanted := DisplayServer.WINDOW_MODE_FULLSCREEN if Game.fullscreen \
			else DisplayServer.WINDOW_MODE_WINDOWED
	if DisplayServer.window_get_mode() != wanted:
		DisplayServer.window_set_mode(wanted)


# ---------------------------------------------------------------------------
# Reactions
# ---------------------------------------------------------------------------

func _on_footstep(block_id: int) -> void:
	Sfx.play_step(block_id, player.global_position)


func _on_entered_water() -> void:
	Sfx.play_at("splash", player.global_position)


func _on_health_changed(current: int, maximum: int) -> void:
	hud.set_health(current, maximum)


func _on_player_damaged(_amount: int) -> void:
	hud.flash_damage()


## Death is gentle: full heal, respawn in the home house, inventory kept.
func _on_player_died() -> void:
	hud.show_toast("Vous êtes mort... retour à la maison", 3.5)
	player.revive(world.spawn_point())


func _on_loot_dropped(item_id: int, count: int) -> void:
	var left := inventory.add(item_id, count)
	var gained := count - left
	if gained > 0:
		hud.show_toast("+%d %s" % [gained, Items.display_name_any(item_id)], 1.6)


# ---------------------------------------------------------------------------
# Player persistence (survival progression lives in the world meta file)
# ---------------------------------------------------------------------------

func _restore_player_data() -> void:
	var meta := world.load_meta()
	var stored: Variant = meta.get("inventory")
	if stored is Dictionary:
		inventory.from_dict(stored)
		# Live settings always win over the snapshot taken at save time.
		inventory.creative = Game.creative
	elif not Game.creative:
		_give_starter_kit()
	var stored_health: Variant = meta.get("health")
	if stored_health is float or stored_health is int:
		player.health = clampi(int(stored_health), 1, Player.MAX_HEALTH)
	var stored_chests: Variant = meta.get("chests")
	if stored_chests is Dictionary:
		chest_store.from_dict(stored_chests)


## First survival session: a wooden kit and enough torches for the night.
func _give_starter_kit() -> void:
	inventory.clear()
	inventory.set_slot(0, Items.WOOD_PICKAXE, 1)
	inventory.set_slot(1, Items.WOOD_SWORD, 1)
	inventory.set_slot(2, Blocks.TORCH, 8)
	inventory.select(0)


func _store_player_data() -> void:
	world.store_meta({
		"inventory": inventory.to_dict(),
		"health": player.health,
		"chests": chest_store.to_dict(),
	})


func _on_settings_changed() -> void:
	inventory.creative = Game.creative
	# God mode is independent of creative: flying in a survival world keeps its
	# monsters, its damage and its resource costs.
	player.set_fly_mode(Game.fly_mode)
	_apply_fullscreen()
	if player.camera != null:
		player.camera.fov = Game.fov
	hud.refresh_settings()
	VoxelMaterials.set_realistic(world.materials(), Game.realistic)


func _on_save_requested() -> void:
	world.save_all()
	_store_player_data()
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
	if gravity != null:
		gravity.settle_all()
	_store_player_data()
	world.shutdown()
	get_tree().quit()
