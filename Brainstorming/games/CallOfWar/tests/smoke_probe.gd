extends Node
## Integration probe. Runs inside the real boot path, because Godot does not
## register the project autoloads when a MainLoop is started with --script, and
## most of the project mentions Game / War / Sfx.
##
##   godot --headless --path . -- --smoke
##
## Exits 0 when every assertion holds, 1 otherwise. Assertions are written on
## invariants (ids valid, quantities coherent, ground present) rather than on
## first launch state, because the campaign save makes the run non hermetic.

var _main: Node3D
var _frames := 0
var _failures: PackedStringArray = PackedStringArray()
var _checks := 0
var _phase := 0
var _phase_frames := 0

## Frames to wait after boot before judging anything: the world streams on
## worker threads and the director spawns over several frames.
const WARMUP_FRAMES := 240
const PHASE_FRAMES := 90


func setup(main_node: Node3D) -> void:
	_main = main_node


func _process(_delta: float) -> void:
	_frames += 1
	if _frames < WARMUP_FRAMES:
		return
	_phase_frames += 1
	if _phase_frames < PHASE_FRAMES and _phase > 0:
		return
	_phase_frames = 0
	match _phase:
		0:
			_check_world()
		1:
			_check_player()
		2:
			_check_weapons()
		3:
			_check_campaign()
		4:
			_check_ai()
		5:
			_check_determinism()
		6:
			_check_war_v2()
		7:
			_check_modules_v2()
		8:
			_check_atmosphere()
		9:
			_check_heading()
		10:
			_check_playable()
		_:
			_finish()
			return
	_phase += 1


func _ok(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)


func _between(value: float, low: float, high: float, message: String) -> void:
	_checks += 1
	if value < low or value > high:
		_failures.append("%s (obtenu %f, attendu dans [%f, %f])" % [message, value, low, high])


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------

func _check_world() -> void:
	var world: GameWorld = _main.world
	_ok(world != null, "le noeud World est absent")
	if world == null:
		return
	var layout := world.layout()
	_ok(layout != null, "le layout est nul")
	if layout == null:
		return
	_ok(layout.sites.size() == Layout.SITE_COUNT,
			"nombre de sites inattendu : %d" % layout.sites.size())
	var sectors := layout.sector_ids()
	_ok(sectors.size() == 8, "il faut exactement 8 secteurs, obtenu %d" % sectors.size())
	_ok(not layout.roads.is_empty(), "aucune route dans le layout")

	# No two sites may overlap: that would put a church inside a bunker.
	var too_close := 0
	for i in layout.sites.size():
		for j in range(i + 1, layout.sites.size()):
			if layout.sites[i].center.distance_to(layout.sites[j].center) < 180.0:
				too_close += 1
	_ok(too_close == 0, "%d paires de sites a moins de 180 m" % too_close)

	_ok(world.loaded_chunk_count() > 0, "aucun chunk charge apres la montee en regime")

	# The height field must be finite and inside a believable range everywhere.
	var hf := world.heightfield()
	_ok(hf != null, "le height field est nul")
	if hf == null:
		return
	var lowest := INF
	var highest := -INF
	for i in 400:
		var x := -1900.0 + float(i % 20) * 190.0
		var z := -1900.0 + float(i / 20) * 190.0
		var h := hf.height_at(x, z)
		_checks += 1
		if not is_finite(h):
			_failures.append("hauteur non finie en (%f, %f)" % [x, z])
			break
		lowest = minf(lowest, h)
		highest = maxf(highest, h)
	_between(highest - lowest, 8.0, 200.0, "amplitude du relief invraisemblable")


func _check_player() -> void:
	var player: Player = _main.player
	var world: GameWorld = _main.world
	_ok(player != null, "le noeud Player est absent")
	if player == null or world == null:
		return
	_ok(player.is_alive(), "le joueur est mort au demarrage")
	_between(player.health, 1.0, Player.MAX_HEALTH, "sante du joueur hors bornes")

	# The classic streamed world bug: the player falls through the terrain
	# because he was released over a chunk that had no collision yet.
	var pos := player.global_position
	var ground := world.ground_y(pos.x, pos.z)
	_ok(pos.y > ground - 3.0,
			"le joueur est passe sous le terrain (y=%f, sol=%f)" % [pos.y, ground])
	_ok(pos.y < ground + 60.0,
			"le joueur flotte tres au dessus du sol (y=%f, sol=%f)" % [pos.y, ground])
	_ok(Heightfield.in_bounds(pos.x, pos.z), "le joueur est hors de la zone jouable")
	_ok(player.eye_position().y > pos.y, "les yeux ne sont pas au dessus des pieds")
	_ok(player.head_height() > 0.0, "head_height() ne renvoie rien d'exploitable")


func _check_weapons() -> void:
	var player: Player = _main.player
	if player == null:
		return
	var weapon := player.current_weapon()
	_ok(weapon != null, "le joueur n'a aucune arme en main")
	if weapon == null:
		return
	_ok(weapon.id >= 0 and weapon.id < WeaponDefs.COUNT,
			"identifiant d'arme invalide : %d" % weapon.id)
	_ok(weapon.in_magazine >= 0 and weapon.in_magazine <= WeaponDefs.magazine(weapon.id),
			"chargeur incoherent : %d" % weapon.in_magazine)
	_ok(weapon.reserve >= 0, "reserve negative")
	_ok(WeaponDefs.display_name(weapon.id) != "", "l'arme n'a pas de nom affichable")

	# Every weapon definition must be complete, or a pickup crashes the game.
	for id in WeaponDefs.all_ids():
		_checks += 1
		if WeaponDefs.display_name(id) == "":
			_failures.append("arme %d sans nom" % id)
			continue
		_checks += 1
		if WeaponDefs.damage(id) <= 0.0:
			_failures.append("arme %d sans degats" % id)
		_checks += 1
		if not Sfx.has_sample(WeaponDefs.fire_sample(id)):
			_failures.append("arme %d : echantillon de tir inconnu (%s)"
					% [id, WeaponDefs.fire_sample(id)])
		_checks += 1
		var far := WeaponDefs.falloff(id, 400.0)
		if far <= 0.0 or far > 1.0:
			_failures.append("arme %d : falloff hors bornes a 400 m (%f)" % [id, far])


func _check_campaign() -> void:
	var tracker: ObjectiveTracker = _main.objectives
	_ok(tracker != null, "le noeud Objectives est absent")
	if tracker == null:
		return
	var all_objectives := tracker.all_objectives()
	_ok(all_objectives.size() >= 8,
			"campagne trop courte : %d objectifs" % all_objectives.size())
	_ok(not tracker.active().is_empty(), "aucun objectif actif au demarrage")

	var seen_ids := {}
	for entry in all_objectives:
		var obj: MissionDefs.Objective = entry
		_checks += 1
		if seen_ids.has(obj.id):
			_failures.append("identifiant d'objectif duplique : %d" % obj.id)
		seen_ids[obj.id] = true
		_checks += 1
		if obj.title.strip_edges() == "" or obj.description.strip_edges() == "":
			_failures.append("objectif %d sans titre ou sans description" % obj.id)
		_checks += 1
		if not Heightfield.in_bounds(obj.position.x, obj.position.z):
			_failures.append("objectif %d hors de la zone jouable" % obj.id)
		_checks += 1
		if obj.prerequisite >= 0 and obj.prerequisite == obj.id:
			_failures.append("objectif %d se prerequiert lui meme" % obj.id)

	_ok(War.sector_count() == 8, "War ne connait pas 8 secteurs")


func _check_ai() -> void:
	var director: Director = _main.director
	_ok(director != null, "le noeud Director est absent")
	if director == null:
		return
	_ok(director.live_soldier_count() <= 60,
			"budget de soldats depasse : %d" % director.live_soldier_count())
	_ok(director.live_squad_count() <= 14,
			"budget d'escouades depasse : %d" % director.live_squad_count())

	var soldiers := get_tree().get_nodes_in_group("damageable")
	_ok(not soldiers.is_empty(), "aucune entite damageable dans la scene")

	# The damage contract is what every bullet in the game relies on.
	var incomplete := 0
	for node in soldiers:
		if not node.has_method("take_damage") or not node.has_method("is_alive") \
				or not node.has_method("head_height"):
			incomplete += 1
	_ok(incomplete == 0, "%d entites damageable ne tiennent pas le contrat" % incomplete)

	# Nobody may spawn under the terrain either.
	var world: GameWorld = _main.world
	var buried := 0
	for node in get_tree().get_nodes_in_group("axis"):
		var body := node as Node3D
		if body == null:
			continue
		if body.global_position.y < world.ground_y(body.global_position.x,
				body.global_position.z) - 3.0:
			buried += 1
	_ok(buried == 0, "%d soldats sont sous le terrain" % buried)


## The world must be a pure function of the seed: the same query twice has to
## give the same answer, otherwise saves and the map would drift.
func _check_determinism() -> void:
	var hf: Heightfield = _main.world.heightfield()
	if hf == null:
		return
	var drift := 0
	for i in 64:
		var x := -1500.0 + float(i) * 47.0
		var z := 900.0 - float(i) * 31.0
		if not is_equal_approx(hf.height_at(x, z), hf.height_at(x, z)):
			drift += 1
	_ok(drift == 0, "height_at n'est pas deterministe (%d divergences)" % drift)

	var fresh := Layout.new(Game.campaign_seed)
	var world: GameWorld = _main.world
	var reference: Layout = world.layout()
	var mismatch := 0
	for i in mini(fresh.sites.size(), reference.sites.size()):
		if not fresh.sites[i].center.is_equal_approx(reference.sites[i].center):
			mismatch += 1
	_ok(mismatch == 0, "le layout n'est pas reproductible (%d sites differents)" % mismatch)


## v2 campaign state. These live in the probe rather than in a unit suite
## because `War` is an autoload, and Godot does not register autoloads when a
## SceneTree is started with --script (contract section 6).
func _check_war_v2() -> void:
	# Explicitly typed: `_main.world` is reached through an untyped property, so
	# the chain returns a Variant and `:=` has nothing to infer from.
	var world: GameWorld = _main.world
	var sectors: PackedInt32Array = world.layout().sector_ids()
	if sectors.is_empty():
		_ok(false, "aucun secteur, impossible de tester l'etat de campagne")
		return
	var probe_sector: int = sectors[0]

	# The load bearing invariant of the whole counter attack feature: a captured
	# sector STAYS captured. Contested is a flag beside it, never an undo, or the
	# sector tally could walk backwards and war_won could replay in reverse.
	var captured_before := War.captured_count()
	War.capture_sector(probe_sector)
	var captured_after_capture := War.captured_count()
	War.mark_contested(probe_sector)
	_ok(War.is_sector_contested(probe_sector), "mark_contested ne prend pas effet")
	_ok(War.is_sector_captured(probe_sector),
			"un secteur conteste ne doit JAMAIS perdre sa capture")
	_ok(War.captured_count() == captured_after_capture,
			"le compte de secteurs a bouge en marquant un secteur conteste")
	_ok(War.contested_ids().has(probe_sector), "contested_ids oublie le secteur marque")
	War.clear_contested(probe_sector)
	_ok(not War.is_sector_contested(probe_sector), "clear_contested ne prend pas effet")
	_ok(War.captured_count() >= captured_before, "le compte de secteurs a regresse")

	# Peak alert is what decides whether a capture counts as silent.
	War.reset_peak_alert()
	var quiet_peak := War.peak_alert()
	War.raise_alert(War.ALERT_FULL)
	_ok(War.peak_alert() >= War.ALERT_FULL,
			"peak_alert ne retient pas le pic (obtenu %d)" % War.peak_alert())
	_ok(War.peak_alert() >= quiet_peak, "peak_alert a regresse pendant une alerte")
	War.reset_peak_alert()

	var intel_before := War.intel_found
	War.record_intel()
	_ok(War.intel_found == intel_before + 1, "record_intel n'incremente pas")
	var silent_before := War.silent_captures
	War.record_silent_capture()
	_ok(War.silent_captures == silent_before + 1, "record_silent_capture n'incremente pas")

	War.record_sector_result(probe_sector, 123.5, true)
	var result: Dictionary = War.sector_result(probe_sector)
	_ok(not result.is_empty(), "sector_result ne retrouve pas le bilan enregistre")
	if not result.is_empty():
		_ok(bool(result.get("silent", false)), "le style du secteur n'a pas ete conserve")
	_ok(War.sector_result(-999).is_empty(),
			"sector_result doit rendre un dictionnaire vide pour un secteur inconnu")

	# A v1 save carries none of the v2 keys. Loading one must not fail nor lose
	# anything, which is the compatibility rule of contract section 11.0.
	var snapshot := War.to_dict()
	War.from_dict({"kills": 7})
	_ok(War.kills == 7, "from_dict n'a pas relu une sauvegarde minimale")
	War.from_dict(snapshot)
	_ok(War.silent_captures == silent_before + 1,
			"un aller retour to_dict/from_dict perd les compteurs v2")


## v2 modules: weapons, music, companions, director, binoculars, debrief.
func _check_modules_v2() -> void:
	# Two weapons were appended in v2. The eight v1 ids must not have moved:
	# they are written into player save files.
	_ok(WeaponDefs.COUNT == 10, "COUNT devrait valoir 10, obtenu %d" % WeaponDefs.COUNT)
	_ok(WeaponDefs.M1_GARAND == 0 and WeaponDefs.GRENADE == 7,
			"un identifiant d'arme v1 a bouge, les sauvegardes sont cassees")
	_ok(WeaponDefs.has_scope(WeaponDefs.KAR98K_SCOPED),
			"le Kar98k a lunette doit avoir une lunette")
	_ok(not WeaponDefs.has_scope(WeaponDefs.KAR98K),
			"le Kar98k nu ne doit pas avoir de lunette")
	_ok(WeaponDefs.ammo_type(WeaponDefs.LUGER) == WeaponDefs.ammo_type(WeaponDefs.MP40),
			"le Luger doit partager le 9 mm de la MP40")
	_ok(WeaponDefs.is_axis_weapon(WeaponDefs.LUGER), "le Luger est une arme de l'Axe")

	# A save carrying a weapon id from another build must not poison the game.
	var salvaged := Weapon.new(WeaponDefs.M1911, true)
	salvaged.from_dict({"id": 4242, "in_magazine": 3, "reserve": 10})
	_ok(salvaged.id >= 0 and salvaged.id < WeaponDefs.COUNT,
			"un identifiant d'arme invalide n'a pas ete borne (obtenu %d)" % salvaged.id)

	var music_node: Music = _main.music
	_ok(music_node != null, "le noeud Music est absent")
	if music_node != null:
		music_node.set_state(Music.STATE_SEARCH)
		_ok(music_node.state() == Music.STATE_SEARCH, "la musique ne change pas d'etat")
		_ok(Music.state_name(Music.STATE_COMBAT) != "", "un etat musical sans nom affichable")
		music_node.set_state(Music.STATE_CALM)

	var companion_node: CompanionManager = _main.companions
	_ok(companion_node != null, "le noeud Companions est absent")
	if companion_node != null:
		_ok(companion_node.count() <= CompanionManager.MAX_COMPANIONS,
				"le plafond de compagnons est depasse")
		_ok(not companion_node.is_companion(_main.player),
				"le joueur ne doit pas se compter lui meme comme compagnon")

	var director_node: Director = _main.director
	_ok(director_node.active_counter_attack() == -1,
			"une contre-attaque est active au demarrage")
	# Explicitly typed: `_main.world` is reached through an untyped property, so
	# the chain returns a Variant and `:=` has nothing to infer from.
	var world: GameWorld = _main.world
	var sectors: PackedInt32Array = world.layout().sector_ids()
	if not sectors.is_empty():
		var site_id: int = sectors[0]
		_ok(not director_node.is_site_isolated(site_id),
				"un site est isole avant toute destruction de radio")
		director_node.isolate_site(site_id)
		_ok(director_node.is_site_isolated(site_id), "isolate_site ne prend pas effet")

	# Binoculars: the B key was in the input map and in the README since v1 and
	# did nothing at all. It has to actually move the camera now.
	var player: Player = _main.player
	var fov_before: float = player.rig.camera.fov if player.rig != null and player.rig.camera != null else 0.0
	player.toggle_binoculars()
	_ok(player.is_scoping, "les jumelles ne s'activent pas")
	player.toggle_binoculars()
	_ok(not player.is_scoping, "les jumelles ne se referment pas")
	_ok(fov_before > 0.0, "la camera du joueur est introuvable")

	_ok(not _main.debrief_ui.is_open(), "le debriefing est ouvert au demarrage")


## Local atmospheric conditions, in the running game.
##
## The pure half of this lives in tests/test_weather.gd. What can only be
## checked here is the wiring: that Main really read a climate for every site,
## that handing one to Weather moves the sky, and that both emitters exist and
## stay mutually exclusive.
func _check_atmosphere() -> void:
	var weather: Weather = _main.weather
	_ok(weather != null, "le noeud Weather est absent")
	if weather == null:
		return

	_ok(weather.kind >= 0 and weather.kind < Weather.KIND_COUNT,
			"ciel invalide en jeu (obtenu %d)" % weather.kind)
	_between(weather.sight_factor(), 0.30, 1.0, "facteur de vue hors bornes")
	_ok(not weather.kind_name().is_empty(), "le ciel courant n'a pas de nom affichable")

	# Main builds the climate map from the finished world. An empty map means
	# the whole feature is inert and nothing else here would notice.
	var climates: Dictionary = _main._climates
	var world: GameWorld = _main.world
	var sites: Array[Layout.Site] = world.layout().sites
	_ok(climates.size() == sites.size(),
			"climats manquants : %d pour %d lieux" % [climates.size(), sites.size()])
	var distinct := {}
	for site: Layout.Site in sites:
		var c: int = int(climates.get(site.id, -1))
		_ok(c >= 0 and c < Weather.KIND_COUNT,
				"climat invalide pour le lieu %d (obtenu %d)" % [site.id, c])
		distinct[c] = true
	_ok(distinct.size() >= 2, "les vingt deux lieux partagent tous le meme ciel")

	# Both sides of the priority rule, forced rather than observed: whether a
	# manual hold happens to be running depends on how far into the opening fog
	# this probe starts, and a test that only exercises whichever branch it
	# lands in is not a test. `_manual_skip` is private and written here on
	# purpose, which is also why this lives in the probe and not in a unit suite.
	var restore: int = weather.climate()

	# Any kind EXCEPT the one already on: hardcoding one made this fail whenever
	# the campaign roll happened to have put that same sky up, which says
	# nothing about whether the priority rule works.
	var other: int = Weather.STORM if weather.kind != Weather.STORM else Weather.FOG
	weather._manual_skip = 1
	weather.set_climate(other, 0.05)
	_ok(weather.climate() == other,
			"un climat doit etre enregistre meme pendant une meteo imposee")
	_ok(weather.kind != other,
			"une meteo imposee doit tenir face au climat local")

	weather._manual_skip = 0
	weather.set_climate(-1, 0.05)
	weather.set_climate(Weather.SNOW, 0.05)
	_ok(weather.climate() == Weather.SNOW, "set_climate n'enregistre pas le climat")
	_ok(weather.kind == Weather.SNOW, "un climat impose ne change pas le ciel")

	# Leaving a place hands the sky back to the campaign roll, which never snows.
	weather.set_climate(-1, 0.05)
	_ok(weather.climate() == -1, "on ne peut pas revenir en plein champ")
	_ok(weather.kind != Weather.SNOW, "la neige d'un lieu quitte ne se dissipe pas")

	# An out of range climate must be refused, not stored.
	weather.set_climate(Weather.KIND_COUNT + 3, 0.05)
	_ok(weather.climate() == -1, "un climat hors plage est accepte")

	# Rain and snow are two emitters and never both run.
	weather.set_climate(Weather.SNOW, 0.05)
	weather._process(0.5)
	var snow_node: GPUParticles3D = weather.get_node_or_null("Snow")
	var rain_node: GPUParticles3D = weather.get_node_or_null("Rain")
	_ok(snow_node != null, "l'emetteur de neige n'a pas ete construit")
	_ok(rain_node != null, "l'emetteur de pluie a disparu")
	if snow_node != null and rain_node != null:
		_ok(snow_node.amount <= Weather.SNOW_BUDGET,
				"le budget de flocons est depasse")
		_ok(not (snow_node.emitting and rain_node.emitting),
				"la pluie et la neige tombent en meme temps")
	weather.set_climate(restore, 0.05)


## The heading every compass rose in the game is drawn from.
##
## The bug this guards: the HUD compass band, the HUD damage arcs and the map's
## view cone all read the heading off `Player.global_transform`. The player body
## is a CharacterBody3D that never rotates -- movement builds its own basis from
## `rig.rotation.y` -- so all three were frozen pointing at world north for the
## whole campaign. Turning has to move the reading.
func _check_heading() -> void:
	var player: Player = _main.player
	var hud_node: Hud = _main.hud
	if player == null or player.rig == null or hud_node == null:
		_ok(false, "joueur, support de camera ou HUD absent")
		return

	var restore: float = player.rig.yaw
	var seen: Array[float] = []
	# Four quarter turns. Compared through the HUD's own private helper, which
	# is the exact value the compass band is drawn from.
	for step in 4:
		player.rig.yaw = float(step) * PI * 0.5
		_settle_rig(player.rig)
		seen.append(hud_node._player_heading_rad())

	for i in seen.size():
		for j in range(i + 1, seen.size()):
			var apart: float = absf(wrapf(seen[i] - seen[j], -PI, PI))
			_ok(apart > 1.0,
					"deux caps a un quart de tour d'ecart se lisent pareil (%f et %f)"
							% [seen[i], seen[j]])

	# North must read as zero, or the band would turn with the camera but print
	# the wrong cardinal under the index.
	player.rig.yaw = 0.0
	_settle_rig(player.rig)
	_between(absf(wrapf(hud_node._player_heading_rad(), -PI, PI)), 0.0, 0.01,
			"lacet nul doit se lire plein nord")

	# East is +X, and the project's compass convention makes that +PI/2.
	player.rig.yaw = -PI * 0.5
	_settle_rig(player.rig)
	_between(wrapf(hud_node._player_heading_rad(), -PI, PI), PI * 0.5 - 0.01, PI * 0.5 + 0.01,
			"un quart de tour a droite doit se lire plein est")

	player.rig.yaw = restore
	_settle_rig(player.rig)


## The player must actually be playable, and his weapon must be in his hands.
##
## The bug this guards cost a whole session: `_release_player_when_ground_is_ready`
## waited for ground under `_spawn`, but `_load_campaign` moves the player to
## his saved position AFTER `_spawn` is set to the drop zone. Loading a save
## made 1700 m away left it waiting for a tile the streaming, which follows the
## PLAYER, was never going to build. The player stayed frozen for ever, and a
## frozen player has no keyboard and no mouse.
##
## The second symptom came free with the first and is worth pinning separately:
## `Viewmodel.update()` is driven from `Player.tick`, so a frozen player also
## leaves the weapon at the rig origin, which puts the camera inside the stock
## and fills a third of the screen with a black slab.
func _check_playable() -> void:
	var player: Player = _main.player
	_ok(_main._player_released, "le joueur n'a jamais ete libere")
	_ok(player.can_process(), "le joueur ne traite pas: ni clavier ni souris")
	_ok(player.process_mode != Node.PROCESS_MODE_DISABLED,
			"le joueur est encore gele")

	# The hold point has to be where the player actually is, not where the
	# campaign started, or the release condition can never be met.
	var here: Vector3 = player.global_position
	var hold: Vector3 = _main._spawn
	_between(Vector2(here.x - hold.x, here.z - hold.z).length(), 0.0, 220.0,
			"le point d'attente a derive loin du joueur")

	var world: GameWorld = _main.world
	_ok(world.is_ground_ready(here), "pas de sol sous le joueur")

	# Weapon in the hands, not at the eye.
	var rig: CameraRig = player.rig
	var vm_rig: Node3D = null
	if rig != null and rig.camera != null:
		vm_rig = rig.camera.get_node_or_null("Viewmodel/Rig")
	_ok(vm_rig != null, "le modele d'arme en vue subjective est absent")
	if vm_rig != null:
		_ok(vm_rig.position.length() > 0.05,
				"l'arme est restee a l'origine du support: la camera est dedans")
		_between(vm_rig.position.z, -1.2, -0.2,
				"l'arme est trop pres ou trop loin de l'oeil")


## Pushes a freshly written `yaw` all the way into the node transform.
##
## `CameraRig.yaw` is a plain variable; `rotation.y` is only written from it in
## `_apply()`, which normally runs once per frame from `_process`. A probe that
## sets yaw and reads the transform in the same frame would otherwise measure
## the previous frame's angle and wrongly conclude that nothing moved.
func _settle_rig(rig: CameraRig) -> void:
	rig._apply()
	rig.force_update_transform()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

func _finish() -> void:
	print("")
	print("=== CALL OF WAR smoke ===")
	for message in _failures:
		print("  ECHEC  %s" % message)
	# A probe that asserted nothing is a broken probe, not a passing run.
	if _checks == 0:
		print("  ECHEC  aucune verification executee")
		_failures.append("sonde vide")
	print("")
	print("  %d verifications, %d echecs" % [_checks, _failures.size()])
	print("=========================")
	print("")
	var code := 1 if not _failures.is_empty() else 0
	# Join the streaming threads before leaving, or the process hangs on exit.
	if _main != null and _main.has_method("_shutdown_world"):
		_main.call("_shutdown_world")
	get_tree().quit(code)
