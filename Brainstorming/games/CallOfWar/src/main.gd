extends Node3D
## Entry point. Owns nothing but wiring: it calls setup on every subsystem in
## dependency order, routes the input that does not belong to a single
## subsystem, keeps the player from falling through a world that is still
## streaming, and makes sure the campaign is written to disk before the process
## ends.

@onready var world: GameWorld = $World
@onready var player: Player = $Player
@onready var world_environment: WorldEnvironment = $WorldEnvironment
@onready var sun: DirectionalLight3D = $Sun
@onready var moon: DirectionalLight3D = $Moon
@onready var sky: SkyController = $Sky
@onready var weather: Weather = $Weather
@onready var vfx: Vfx = $Vfx
@onready var objectives: ObjectiveTracker = $Objectives
@onready var director: Director = $Director
@onready var hud: Hud = $Hud
@onready var map_ui: MapUi = $Screens/MapUi
@onready var objectives_ui: ObjectivesUi = $Screens/ObjectivesUi
@onready var pause_menu: PauseMenu = $Screens/PauseMenu

## True once the ground under the player is guaranteed to exist. Until then the
## player is frozen: releasing him over a chunk that has no collision yet is the
## classic way to fall out of a streamed world.
var _player_released := false
var _spawn: Vector3 = Vector3.ZERO
var _quitting := false
var _weather_hour := -1

## Starting loadout of a fresh campaign.
const START_BANDAGES := 3
const START_GRENADES := 4


func _ready() -> void:
	# Closing the window has to run through _quit_game so the worker threads are
	# joined first, which means intercepting the request rather than letting the
	# tree tear itself down under them.
	get_tree().auto_accept_quit = false

	# Order matters and is fixed by docs/CONTRACTS.md section 5. The world builds
	# the layout, the height field and the shared materials that everything else
	# reads, so it goes first.
	_adopt_saved_seed()
	world.setup(Game.campaign_seed)
	sky.setup(world_environment, sun, moon)
	weather.setup(sky, player)
	vfx.setup()

	player.setup(world)
	_spawn = world.spawn_point()
	player.teleport(_spawn)
	_freeze_player(true)

	objectives.setup(world, player)
	director.setup(world, player, objectives)
	hud.setup(player, objectives, sky, weather, world)

	map_ui.setup(world, player, objectives)
	objectives_ui.setup(objectives)
	pause_menu.setup()

	War.register_sectors(world.layout().sector_ids())

	_connect_signals()
	_load_campaign()
	_apply_fullscreen()
	_capture_mouse()
	_announce_briefing()

	_maybe_start_smoke_probe()
	_maybe_start_shot_probe()
	_maybe_start_generic_probe()


func _connect_signals() -> void:
	player.died.connect(_on_player_died)
	player.damaged.connect(_on_player_damaged)
	player.footstep.connect(_on_footstep)
	player.used.connect(_on_player_used)

	objectives.objective_completed.connect(_on_objective_completed)
	objectives.objective_failed.connect(_on_objective_failed)
	objectives.campaign_completed.connect(_on_campaign_completed)
	director.event_announced.connect(_on_event_announced)

	War.sector_captured.connect(_on_sector_captured)
	War.war_won.connect(_on_campaign_completed)
	War.stat_changed.connect(_on_stat_changed)

	map_ui.closed.connect(_on_screen_closed)
	objectives_ui.closed.connect(_on_screen_closed)
	objectives_ui.objective_selected.connect(_on_objective_selected)
	pause_menu.resume_requested.connect(_on_screen_closed)
	pause_menu.save_requested.connect(_on_save_requested)
	pause_menu.restart_requested.connect(_on_restart_requested)
	pause_menu.quit_requested.connect(_quit_game)

	Game.settings_changed.connect(_on_settings_changed)


# ---------------------------------------------------------------------------
# Frame loop
# ---------------------------------------------------------------------------

func _process(delta: float) -> void:
	world.update_streaming(player.global_position)
	War.tick(delta)
	director.tick(delta)
	_release_player_when_ground_is_ready()
	_roll_weather()


## The player stays frozen at the spawn point until the chunk under him carries
## its collision. Without this he spends the first frames in free fall and lands
## under the terrain once it finally appears.
func _release_player_when_ground_is_ready() -> void:
	if _player_released:
		return
	if not world.is_ground_ready(_spawn):
		return
	_player_released = true
	player.teleport(_spawn)
	_freeze_player(false)


func _freeze_player(frozen: bool) -> void:
	player.process_mode = Node.PROCESS_MODE_DISABLED if frozen else Node.PROCESS_MODE_INHERIT
	if frozen:
		player.velocity = Vector3.ZERO


## Weather is rolled once per in game hour, deterministically, so a given
## campaign always gets the same sky at the same time.
func _roll_weather() -> void:
	var hour := int(sky.time_of_day * 24.0)
	if hour == _weather_hour:
		return
	_weather_hour = hour
	var wanted := Weather.roll(Game.campaign_seed, hour)
	if wanted != weather.kind:
		weather.set_weather(wanted)


# ---------------------------------------------------------------------------
# Input that belongs to no single subsystem
# ---------------------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("pause"):
		_toggle_pause()
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

	if event.is_action_pressed("debug"):
		Game.show_debug = not Game.show_debug
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("map"):
		_toggle_screen(map_ui)
		get_viewport().set_input_as_handled()
		return

	if event.is_action_pressed("objectives"):
		_toggle_screen(objectives_ui)
		get_viewport().set_input_as_handled()
		return


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

## Every overlay except the pause menu, in closing priority order.
func _overlays() -> Array:
	return [map_ui, objectives_ui]


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


func _toggle_screen(screen: Control) -> void:
	if pause_menu.is_open():
		return
	var was_open: bool = screen.is_open()
	_close_overlays()
	if not was_open:
		screen.open()
	_sync_screen_state()


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
	if _player_released:
		player.process_mode = Node.PROCESS_MODE_DISABLED if open else Node.PROCESS_MODE_INHERIT
	hud.set_paused(open)
	if open:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	else:
		_capture_mouse()


func _capture_mouse() -> void:
	if DisplayServer.get_name() == "headless":
		return
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

func _on_footstep(surface: String) -> void:
	Sfx.play_step(surface, player.global_position)


func _on_player_damaged(_amount: float, from_direction: Vector3) -> void:
	hud.flash_damage(from_direction)


## Death is not a game over: the resistance drags you back to the safe house and
## the sectors you already took stay taken.
func _on_player_died() -> void:
	War.deaths += 1
	hud.show_banner("VOUS ETES TOMBE", "La Resistance vous ramene a la planque", 4.0)
	var respawn := _friendly_respawn()
	player.revive(respawn)
	_spawn = respawn
	Sfx.play("death")


## The nearest liberated sector, or the starting safe house when none is taken.
func _friendly_respawn() -> Vector3:
	var best := world.spawn_point()
	var best_distance := INF
	var here := player.global_position
	for site in world.layout().sites:
		if not site.is_sector or not War.is_sector_captured(site.id):
			continue
		var pos := Vector3(site.center.x, site.ground + 1.0, site.center.y)
		var distance := pos.distance_to(here)
		if distance < best_distance:
			best_distance = distance
			best = pos
	return best


func _on_player_used(target: Node) -> void:
	if target == null:
		return
	hud.set_prompt("")


func _on_objective_completed(obj: MissionDefs.Objective) -> void:
	War.objectives_done += 1
	Sfx.play("objective_done")
	hud.show_banner(obj.title, obj.reward_text if obj.reward_text != "" else "Objectif accompli", 3.2)


func _on_objective_failed(obj: MissionDefs.Objective) -> void:
	hud.show_banner("ECHEC", obj.title, 3.2)


func _on_sector_captured(sector_id: int) -> void:
	var site := world.layout().site_by_id(sector_id)
	var place := site.display_name if site != null else "Secteur"
	Sfx.play("sector_captured")
	hud.show_banner("%s LIBERE" % place.to_upper(),
			"%d secteurs sur %d" % [War.captured_count(), War.sector_count()], 4.0)
	_save_campaign()


func _on_campaign_completed() -> void:
	hud.show_banner("LA POCHE EST LIBEREE",
			"Precision %d%%, %d ennemis neutralises" % [int(War.accuracy() * 100.0), War.kills], 8.0)
	_save_campaign()


func _on_event_announced(text: String) -> void:
	hud.show_toast(text, 3.0)


## The only kill feedback available without reaching inside Ballistics: War is
## told about every kill by whoever died, so the hit marker rides on that.
func _on_stat_changed(key: String) -> void:
	if key == "kills":
		hud.flash_hitmarker(true, false)


func _on_objective_selected(_objective_id: int) -> void:
	_on_screen_closed()


func _on_settings_changed() -> void:
	_apply_fullscreen()
	hud.refresh_settings()
	if player.rig != null:
		player.rig.set_base_fov(Game.fov)


# ---------------------------------------------------------------------------
# Campaign persistence
# ---------------------------------------------------------------------------

## Takes the world seed from the campaign save when the two disagree, BEFORE the
## world is built from it.
##
## `settings.cfg` is the weaker of the two records: deleting it is what a player
## does to reset their options, and a failed write leaves it missing entirely. In
## both cases Game draws a brand new random seed, the loader below then sees a
## seed that does not match the save, and it silently throws away liberated
## sectors, objectives, inventory and statistics. The next autosave overwrites the
## file and the loss becomes permanent. The save knows which world it belongs to,
## so it wins.
func _adopt_saved_seed() -> void:
	var data := SaveManager.read(Game.campaign_name)
	if data.is_empty():
		return
	var stored: Variant = data.get("seed")
	if not (stored is float or stored is int):
		return
	var wanted := int(stored)
	if wanted == 0 or wanted == Game.campaign_seed:
		return
	Game.campaign_seed = wanted
	Game.save_settings()


func _load_campaign() -> void:
	var data := SaveManager.read(Game.campaign_name)
	if data.is_empty():
		_give_starter_kit()
		return
	var stored_seed: Variant = data.get("seed")
	# A save made in another world is useless: the sites would not line up.
	if stored_seed is float or stored_seed is int:
		if int(stored_seed) != Game.campaign_seed:
			_give_starter_kit()
			return
	var war_data: Variant = data.get("war")
	if war_data is Dictionary:
		War.from_dict(war_data)
	var player_data: Variant = data.get("player")
	if player_data is Dictionary:
		player.from_dict(player_data)
	else:
		_give_starter_kit()
	var objective_data: Variant = data.get("objectives")
	if objective_data is Dictionary:
		objectives.from_dict(objective_data)
	var stored_time: Variant = data.get("time_of_day")
	if stored_time is float or stored_time is int:
		sky.skip_to(float(stored_time))


func _give_starter_kit() -> void:
	player.give_weapon(WeaponDefs.M1_GARAND, WeaponDefs.reserve_max(WeaponDefs.M1_GARAND))
	player.give_weapon(WeaponDefs.M1911, WeaponDefs.reserve_max(WeaponDefs.M1911))
	player.give_weapon(WeaponDefs.GRENADE, START_GRENADES)
	player.give_bandage(START_BANDAGES)
	player.select_slot(WeaponDefs.SLOT_PRIMARY)


func _save_campaign() -> void:
	SaveManager.write(Game.campaign_name, {
		"seed": Game.campaign_seed,
		"war": War.to_dict(),
		"player": player.to_dict(),
		"objectives": objectives.to_dict(),
		"time_of_day": sky.time_of_day,
	})


func _on_save_requested() -> void:
	_save_campaign()
	Game.save_settings()
	hud.show_toast("Campagne sauvegardee")


func _on_restart_requested() -> void:
	SaveManager.erase(Game.campaign_name)
	War.reset_campaign()
	_shutdown_world()
	get_tree().reload_current_scene()


func _announce_briefing() -> void:
	var site := world.layout().site_by_id(world.layout().sector_ids()[0]) \
			if world.layout().sector_ids().size() > 0 else null
	var place := site.display_name if site != null else "la poche"
	hud.show_banner("NORMANDIE, ETE 1942",
			"Liberer %s. Ouvrez le journal avec J." % place, 6.0)


func _take_screenshot() -> void:
	var image := get_viewport().get_texture().get_image()
	var dir := "user://screenshots"
	DirAccess.make_dir_recursive_absolute(dir)
	var stamp := Time.get_datetime_string_from_system().replace(":", "-").replace("T", "_")
	var path := "%s/callofwar_%s.png" % [dir, stamp]
	if image.save_png(path) == OK:
		hud.show_toast("Capture enregistree")
	else:
		hud.show_toast("Echec de la capture")


# ---------------------------------------------------------------------------
# Test harness hooks
# ---------------------------------------------------------------------------

## Integration test hook. The probe has to live inside the real boot path,
## because Godot only registers the project autoloads for the default main loop
## and most of the project refers to Game, so a --script harness cannot even
## compile. Run it with: godot --headless --path . -- --smoke
func _maybe_start_smoke_probe() -> void:
	if not OS.get_cmdline_user_args().has("--smoke"):
		return
	_start_probe("res://tests/smoke_probe.gd", "SmokeProbe", "")


## Screenshot harness hook: godot --path . -- --shot C:/output/dir
func _maybe_start_shot_probe() -> void:
	var user_args := OS.get_cmdline_user_args()
	var index := user_args.find("--shot")
	if index < 0 or index + 1 >= user_args.size():
		return
	_start_probe("res://tests/shot_probe.gd", "ShotProbe", user_args[index + 1])


## Generic diagnostic hook: godot --path . -- --probe res://tests/whatever.gd
func _maybe_start_generic_probe() -> void:
	var user_args := OS.get_cmdline_user_args()
	var index := user_args.find("--probe")
	if index < 0 or index + 1 >= user_args.size():
		return
	_start_probe(user_args[index + 1], "Probe", "")


func _start_probe(path: String, probe_name: String, argument: String) -> void:
	if not ResourceLoader.exists(path):
		push_warning("sonde demandee mais %s est absent" % path)
		return
	var probe_script: Script = load(path)
	if probe_script == null or not probe_script.can_instantiate():
		push_warning("sonde illisible : %s" % path)
		return
	var probe: Node = probe_script.new()
	probe.name = probe_name
	add_child(probe)
	if argument != "":
		probe.setup(self, argument)
	else:
		probe.setup(self)


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_quit_game()


## Joins the streaming threads. MUST run before the tree is torn down or the
## workers park on a semaphore owned by a freed node and the process hangs on
## exit forever.
func _shutdown_world() -> void:
	director.clear_all()
	vfx.clear_all()
	world.shutdown()


func _quit_game() -> void:
	if _quitting:
		return
	_quitting = true
	Game.save_settings()
	_save_campaign()
	_shutdown_world()
	get_tree().quit()
