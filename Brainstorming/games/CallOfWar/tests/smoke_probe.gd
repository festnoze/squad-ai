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
