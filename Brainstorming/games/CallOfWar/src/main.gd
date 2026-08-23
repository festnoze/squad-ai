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
@onready var companions: CompanionManager = $Companions
@onready var music: Music = $Music
@onready var quality: QualityGovernor = $Quality
@onready var hud: Hud = $Hud
@onready var map_ui: MapUi = $Screens/MapUi
@onready var objectives_ui: ObjectivesUi = $Screens/ObjectivesUi
@onready var pause_menu: PauseMenu = $Screens/PauseMenu
@onready var debrief_ui: DebriefUi = $Screens/DebriefUi

## True once the ground under the player is guaranteed to exist. Until then the
## player is frozen: releasing him over a chunk that has no collision yet is the
## classic way to fall out of a streamed world.
var _player_released := false
var _spawn: Vector3 = Vector3.ZERO
## Seconds spent frozen so far, for the release guard.
var _hold_seconds := 0.0
## Seconds since the player was handed control, while the world still settles.
var _settle_seconds := 0.0
var _quitting := false

## True when no save was found, so this is the opening drop of a new campaign.
var _fresh_campaign := true
## Seconds left before the next look at which place the player is standing in.
var _climate_timer := 0.0
## Site id whose weather is currently in force, -1 out in the open.
var _climate_site := -1
## Site id -> signature weather, computed once from the finished world.
var _climates: Dictionary = {}

## Starting loadout of a fresh campaign.
const START_BANDAGES := 3
const START_GRENADES := 4

## Companions further than this from the player when he fast travels are left
## behind. They walked off on their own business; they do not teleport across
## Normandy because someone else did.
const TRAVEL_COMPANION_RANGE := 30.0

## Seconds between two checks of which place the player is standing in.
const CLIMATE_POLL := 0.5

## Longest the player may stay frozen waiting for ground before he is released
## regardless. Generous: a cold start on a slow disk legitimately takes a while.
const HOLD_LIMIT := 12.0
## Seconds after release during which frame times are still loading noise.
const SETTLE_LIMIT := 6.0


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
	companions.setup(world, player)
	music.setup()
	# Before the HUD, which reads the governor for its debug overlay.
	quality.setup(get_viewport())
	quality.set_enabled(Game.adaptive_quality)
	hud.setup(player, objectives, sky, weather, world)
	hud.set_quality(quality)

	map_ui.setup(world, player, objectives)
	objectives_ui.setup(objectives)
	pause_menu.setup()
	debrief_ui.setup(world, objectives)

	War.register_sectors(world.layout().sector_ids())

	_connect_signals()
	_build_climates()
	_load_campaign()
	# The drop happens at first light and has to be made unseen, so a brand new
	# campaign opens under mist whatever the seed rolled for that hour. A save
	# resumes under the weather its own place and hour prescribe instead.
	if _fresh_campaign:
		weather.begin_opening_fog()
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
	map_ui.travel_requested.connect(_on_travel_requested)
	debrief_ui.closed.connect(_on_screen_closed)
	debrief_ui.restart_requested.connect(_on_restart_requested)
	director.counter_attack_started.connect(_on_counter_attack_started)
	director.counter_attack_resolved.connect(_on_counter_attack_resolved)
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
	companions.tick(delta)
	music.tick(delta)
	_drive_music()
	_release_player_when_ground_is_ready(delta)
	_drive_climate(delta)


## Maps the campaign state onto the four musical states.
##
## The mapping is deliberately blunt: the alert level already encodes everything
## the music needs to say, and a second, cleverer heuristic would only produce
## contradictions between what the player hears and what the alert indicator
## shows. VICTORY is not driven from here; it is a one shot fired on a capture
## and it falls back to CALM on its own.
func _drive_music() -> void:
	if music.state() == Music.STATE_VICTORY:
		return
	var wanted := Music.STATE_CALM
	if War.alert_level >= War.ALERT_FULL:
		wanted = Music.STATE_COMBAT
	elif War.alert_level >= War.ALERT_SUSPICIOUS:
		wanted = Music.STATE_SEARCH
	if music.state() != wanted:
		music.set_state(wanted)


## The player stays frozen at the spawn point until the chunk under him carries
## its collision. Without this he spends the first frames in free fall and lands
## under the terrain once it finally appears.
func _release_player_when_ground_is_ready(delta: float) -> void:
	if _player_released:
		# The world keeps streaming hard for a few seconds after the player is
		# handed control. Those frames are still loading frames.
		if _settle_seconds < SETTLE_LIMIT:
			_settle_seconds += delta
			quality.defer()
		return
	# Loading frames say nothing about how the game runs. Without this the
	# ladder reads a priming stall as a hopeless machine and lands on its worst
	# rung before the player has seen a single playable frame.
	quality.defer()
	_hold_seconds += delta
	if world.is_ground_ready(_spawn):
		_player_released = true
		player.teleport(_spawn)
		_freeze_player(false)
		return
	# Dead man's handle. A frozen player has no keyboard and no mouse, so any
	# bug that stops the ground from ever being reported ready costs the whole
	# session rather than one bad landing. Past this point, hand control back
	# and re-seat him on whatever the height field says is under him: falling
	# through a tile is recoverable, an unplayable game is not.
	if _hold_seconds < HOLD_LIMIT:
		return
	push_warning("Main: ground under %s never became ready after %.0f s, " %
			[str(_spawn), HOLD_LIMIT] + "releasing the player anyway.")
	_player_released = true
	var here: Vector3 = player.global_position
	player.teleport(Vector3(here.x, world.ground_y(here.x, here.z) + 1.2, here.z))
	_freeze_player(false)


func _freeze_player(frozen: bool) -> void:
	player.process_mode = Node.PROCESS_MODE_DISABLED if frozen else Node.PROCESS_MODE_INHERIT
	if frozen:
		player.velocity = Vector3.ZERO


## Tells the weather which place the player is standing in.
##
## The hourly campaign roll itself lives in `Weather._tick_auto()`; Main used to
## run a second, competing roll here, which only ever suppressed the first one
## for three hours at a time through `set_weather()`'s manual hold. There is now
## one owner of the sky, and Main only supplies the geography.
##
## Polled rather than driven by a signal because there is no "entered a site"
## event to hang it on, and twice a second is far below the transition time.
func _drive_climate(delta: float) -> void:
	_climate_timer -= delta
	if _climate_timer > 0.0:
		return
	_climate_timer = CLIMATE_POLL

	var site := world.layout().nearest_site(player.global_position.x, player.global_position.z)
	var wanted := -1
	if site != null:
		var here := Vector2(player.global_position.x, player.global_position.z)
		if here.distance_to(site.center) <= _climate_region(site):
			wanted = site.id

	if wanted == _climate_site:
		return
	_climate_site = wanted
	weather.set_climate(int(_climates.get(wanted, -1)))


## How far a site's weather reaches beyond its own footprint.
##
## Deliberately short of half the Poisson spacing, so there is open country
## between two places where the campaign roll rules and the change of sky is
## something the player crosses into rather than a seam between two villages.
func _climate_region(site: Layout.Site) -> float:
	return clampf(site.radius * 4.0, 190.0, 400.0)


## Reads the signature weather of every site off the finished world, once.
##
## Done here and not in Weather because it needs the height field and the
## layout, which Weather has no business holding.
func _build_climates() -> void:
	_climates.clear()
	var field := world.heightfield()
	if field == null:
		return
	for site: Layout.Site in world.layout().sites:
		var biome := Weather.site_biome(field, site.center, site.radius)
		var ground := field.height_at(site.center.x, site.center.y)
		_climates[site.id] = Weather.climate_for(biome, ground, Game.campaign_seed, site.id)


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
	return [map_ui, objectives_ui, debrief_ui]


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
	# The death banner belongs to the HUD ("MISSION INTERROMPUE"), which words it
	# better and already owns the death fade it sits on. Main used to raise a
	# second one in the same frame and whichever landed last won.
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
	music.set_state(Music.STATE_VICTORY)
	# The banner lives here rather than in the HUD because Main is the only place
	# that holds both the sector name and the campaign tally. A silent capture is
	# an achievement, not a formality, and it gets its own wording.
	var result: Dictionary = War.sector_result(sector_id)
	var silent: bool = bool(result.get("silent", false))
	var tally := "%d secteurs sur %d" % [War.captured_count(), War.sector_count()]
	if silent:
		hud.show_banner("%s LIBERE EN SILENCE" % place.to_upper(),
				"%s, sans qu'ils sachent d'ou venait le coup" % tally, 4.5)
	else:
		hud.show_banner("%s LIBERE" % place.to_upper(), tally, 4.0)
	_save_campaign()


## The counter attack is the campaign answering back. It gets a banner rather
## than a toast: the player has ninety seconds to decide whether to defend the
## village he took or let it go, and that decision deserves to interrupt him.
func _on_counter_attack_started(sector_id: int) -> void:
	var site := world.layout().site_by_id(sector_id)
	var place := site.display_name if site != null else "un secteur"
	hud.show_banner("CONTRE-ATTAQUE",
			"Une colonne allemande converge sur %s" % place, 4.5)


func _on_counter_attack_resolved(sector_id: int, held: bool) -> void:
	var site := world.layout().site_by_id(sector_id)
	var place := site.display_name if site != null else "Le secteur"
	if held:
		hud.show_banner("ASSAUT REPOUSSE", "%s tient toujours" % place, 4.0)
	else:
		hud.show_banner("%s EST REPRIS" % place.to_upper(),
				"Il faudra y retourner", 4.5)
	_save_campaign()


## Winning used to be a three line banner after several hours of play, which
## read as an anticlimax. The campaign now ends on a real operation report, and
## the player chooses between keeping the sandbox and starting over.
func _on_campaign_completed() -> void:
	_save_campaign()
	if debrief_ui.is_open():
		return
	_close_overlays()
	if pause_menu.is_open():
		pause_menu.close()
	debrief_ui.open()
	_sync_screen_state()


## Fast travel between liberated sectors. The map only asks; Main decides,
## because it is the only node that knows about the player, the streaming guard
## and the companions at once.
func _on_travel_requested(sector_id: int) -> void:
	if not War.is_sector_captured(sector_id) or War.is_sector_contested(sector_id):
		hud.show_toast("Ce secteur n'est pas sur")
		return
	if War.alert_level > War.ALERT_CALM:
		hud.show_toast("Impossible de decrocher maintenant")
		return
	var site := world.layout().site_by_id(sector_id)
	if site == null:
		return

	_close_overlays()
	_sync_screen_state()

	var destination := Vector3(site.center.x, site.ground + 1.0, site.center.y)
	# The ground under the destination has not streamed yet, so the player is
	# frozen and re-seated exactly like at spawn. Releasing him over a chunk with
	# no collision is how a streamed world swallows its player.
	_spawn = destination
	_player_released = false
	player.teleport(destination)
	_freeze_player(true)

	# The march itself costs the better part of an afternoon.
	sky.skip_to(sky.time_of_day + 0.012)
	var followed := companions.regroup_at(destination, TRAVEL_COMPANION_RANGE)
	if companions.count() > followed:
		hud.show_toast("Des compagnons sont restes sur place", 3.0)
	hud.show_banner("EN ROUTE", site.display_name, 2.5)
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
	# Past the seed check the save is genuinely ours, so this is a campaign being
	# resumed, not the opening drop.
	_fresh_campaign = false
	var war_data: Variant = data.get("war")
	if war_data is Dictionary:
		War.from_dict(war_data)
	var player_data: Variant = data.get("player")
	if player_data is Dictionary:
		player.from_dict(player_data)
		# The save has just moved the player away from the drop zone, so the
		# hold point has to follow. `_release_player_when_ground_is_ready`
		# waits for ground under `_spawn`, and the streaming follows the
		# PLAYER: left pointing at the drop zone, it waits for a tile that is
		# 1700 m behind and will never be loaded, and the player stays frozen
		# for the whole session with no keyboard and no mouse.
		_spawn = player.global_position
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
	companions.dismiss_all()
	music.stop_all()
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
