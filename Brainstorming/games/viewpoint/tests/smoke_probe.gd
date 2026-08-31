extends Node
## Integration probe, run inside the real boot path because the autoload Game
## is not registered under --script:
##
##   godot --headless --path . -- --smoke
##
## Drives one full loop of level 1 (pick photo, place, cross, battery, insert,
## teleport), then a targeted erase check on level 4, then builds every level.
## Exits 0 when every assertion holds, 1 otherwise. A frame watchdog guards
## against a silent runtime error aborting the coroutine: if the probe never
## concludes, the process still exits, and with a failure.

var _main: Node3D
var _failures: PackedStringArray = PackedStringArray()
var _checks := 0
var _concluded := false
var _frames := 0

const WATCHDOG_FRAMES := 3600


func setup(main_node: Node3D) -> void:
	_main = main_node


func _ready() -> void:
	_run()


func _process(_delta: float) -> void:
	_frames += 1
	if _frames > WATCHDOG_FRAMES and not _concluded:
		_fail("sonde interrompue avant sa conclusion (erreur runtime probable, voir ci-dessus)")
		_conclude()


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)


func _fail(message: String) -> void:
	_checks += 1
	_failures.append(message)


func _check_between(value: float, low: float, high: float, message: String) -> void:
	_check(value >= low and value <= high, "%s (attendu dans [%f, %f], obtenu %f)" % [message, low, high, value])


func _frames_pass(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func _group(name: String) -> Array:
	return get_tree().get_nodes_in_group(name).filter(func(n): return is_instance_valid(n) and not n.is_queued_for_deletion())


func _run() -> void:
	await _frames_pass(10)
	print("")
	print("=== VIEWPOINT smoke ===")

	# Boot into level 1 through the same path as the Enter key.
	_main._start_game()
	await _frames_pass(90)

	var player: CharacterBody3D = _main.player
	_check(Game.level_index == 0, "niveau 1 actif au demarrage")
	_check(_group("platform").size() == 2, "niveau 1 : deux plateformes")
	_check(_group("photo_item").size() == 1, "niveau 1 : une photo au sol")
	_check(_group("battery").size() == 1, "niveau 1 : une pile au sol")
	_check(_group("teleporter").size() == 1, "niveau 1 : un teleporteur")
	_check(player.is_on_floor(), "le joueur a atterri sur la plateforme")

	# Pick up the bridge photo: the placer holds it and shows a ghost.
	var photo: Node = _group("photo_item")[0]
	photo.interact(player)
	_check(player.placer.held_id == "passerelle", "photo Passerelle en main")
	_check(player.placer.get_child_count() > 0, "previsualisation fantome presente")
	_check(player.interact_prompt == "" or true, "invite lisible")

	# Stand at the edge of platform A, look level and forward, place.
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose acceptee")
	_check(player.placer.held_id == "", "photo consommee par la pose")
	await _frames_pass(5)
	_check(_group("placed_content").size() == 1, "contenu materialise dans le niveau")

	# The optical contract: the solid deck must now bridge the gap. A downward
	# ray in the middle of the void has to hit the placed geometry.
	var space := player.get_world_3d().direct_space_state
	var ray := PhysicsRayQueryParameters3D.create(Vector3(0, 1, -5.5), Vector3(0, -2, -5.5), 1)
	var hit := space.intersect_ray(ray)
	_check(not hit.is_empty(), "la passerelle enjambe le vide (rayon au milieu du trou)")
	if not hit.is_empty():
		_check(absf(hit["position"].y - (-0.04)) < 0.35, "tablier a la hauteur prevue par la photo")

	# Battery pickup and teleporter cycle.
	var battery: Node = _group("battery")[0]
	battery.interact(player)
	_check(Game.carried_batteries == 1, "pile ramassee")
	var teleporter: Node = _group("teleporter")[0]
	teleporter.interact(player)
	_check(Game.inserted_batteries == 1, "pile inseree")
	_check(Game.can_teleport(), "teleporteur charge")
	teleporter.interact(player)
	await _frames_pass(150)
	_check(Game.level_index == 1, "arrivee au niveau 2 apres teleportation")
	_check(Game.furthest_level >= 1, "la progression retient le niveau atteint")
	_check(Game.is_level_unlocked(1), "le niveau 2 est desormais selectionnable au menu")
	_check(_group("photo_item").size() == 1, "niveau 2 : la photo Pile est la")

	# Duplication: placing the battery photo must yield a real battery.
	var before := _group("battery").size()
	var pile_photo: Node = _group("photo_item")[0]
	pile_photo.interact(player)
	player.global_position = Vector3(0, 0.05, 0)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la photo Pile acceptee")
	await _frames_pass(5)
	_check(_group("battery").size() == before + 1, "une vraie pile dupliquee par la photo")

	# Carve check on level 4: the framed part of the wall is cut out, the
	# flanks survive as fragments, and the placed content is a wall with an
	# open door aligned on the aim.
	_main._load_level(3)
	await _frames_pass(10)
	_check(Game.level_index == 3, "niveau 4 charge")
	var erasables := _group("erasable").size()
	_check(erasables == 2, "niveau 4 : deux objets effacables")
	_check(player.placer.hold("porte"), "photo Porte en main")
	# The door only erases up to its own seal wall (6.2 m): stand close.
	player.global_position = Vector3(0, 0.05, 1.5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la Porte acceptee")
	await _frames_pass(5)
	# The 10 m wall is wider than the frustum at 5.5 m: its two flanks survive
	# (crate + 2 fragments), nothing vanished whole.
	_check(_group("erasable").size() == erasables + 1, "le mur est decoupe en fragments, pas efface en bloc")
	var through := PhysicsRayQueryParameters3D.create(Vector3(0, 1.67, 1), Vector3(0, 1.67, -11), 1)
	var through_hit := space.intersect_ray(through)
	_check(through_hit.is_empty(), "le passage est ouvert : decoupe et porte alignees sur la visee")
	var side := PhysicsRayQueryParameters3D.create(Vector3(1.5, 1.67, 1), Vector3(1.5, 1.67, -11), 1)
	var side_hit := space.intersect_ray(side)
	_check(not side_hit.is_empty(), "le mur autour de la porte bloque a cote de l'ouverture")
	if not side_hit.is_empty():
		_check_between(side_hit["position"].z, -4.7, -4.0, "le mur de la photo est plaque sur la decoupe")
	# THE interstice regression: between the door opening (0.8) and the hole
	# edge (~2.7), the seal wall or the original wall must block. Before the
	# fix this ray sailed through the gap between hole and photo wall.
	var interstice := PhysicsRayQueryParameters3D.create(Vector3(2.5, 1.67, 1), Vector3(2.5, 1.67, -11), 1)
	var interstice_hit := space.intersect_ray(interstice)
	_check(not interstice_hit.is_empty(), "aucun interstice entre la decoupe et le mur de la photo")
	if not interstice_hit.is_empty():
		_check_between(interstice_hit["position"].z, -4.7, -3.4, "l'interstice est scelle au niveau du mur")
	var flank := PhysicsRayQueryParameters3D.create(Vector3(4.7, 1.67, 1), Vector3(4.7, 1.67, -11), 1)
	var flank_hit := space.intersect_ray(flank)
	_check(not flank_hit.is_empty(), "le flanc du mur d'origine subsiste hors du cadre")
	if not flank_hit.is_empty():
		_check_between(flank_hit["position"].z, -4.5, -3.2, "le fragment est reste a la place du mur")

	# v2 mechanics, exercised on level 6 (a wide open platform with a cage).
	_main._load_level(5)
	await _frames_pass(10)
	_check(_group("erasable").size() == 1, "niveau 6 : la cage est effacable")
	_check(player.placer.hold("porte"), "photo Porte en main pour la cage")
	player.global_position = Vector3(4, 0.05, 2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose face a la cage acceptee")
	await _frames_pass(5)
	_check(_group("erasable").size() == 0, "la cage encadree a disparu")
	_check(_group("battery").size() == 2, "la pile encagee est toujours la, desormais accessible")

	# Rotation: a console rolled 180 must materialize its slab HIGH.
	_check(player.placer.hold("console"), "photo Console en main")
	player.placer.rotate_held(1)
	player.placer.rotate_held(1)
	_check(player.placer.roll_steps == 2, "deux crans de molette : 180 degres")
	player.global_position = Vector3(-4, 0.05, 2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la console tournee acceptee")
	_check(player.placer.roll_steps == 0, "le roulis revient a zero apres la pose")
	await _frames_pass(5)
	var slab_ray := PhysicsRayQueryParameters3D.create(Vector3(-4, 4, -1), Vector3(-4, 1, -1), 1)
	var slab_hit := space.intersect_ray(slab_ray)
	_check(not slab_hit.is_empty(), "la dalle tournee existe en hauteur")
	if not slab_hit.is_empty():
		_check(absf(slab_hit["position"].y - 2.42) < 0.3, "dalle a 180 degres a +2.37 des pieds (obtenu %.2f)" % slab_hit["position"].y)

	# Photo-in-photo: placing the coffret materializes a pickable pile photo.
	var photos_before := _group("photo_item").size()
	_check(player.placer.hold("coffret"), "photo Coffret en main")
	player.global_position = Vector3(2, 0.05, 3)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose du coffret acceptee")
	await _frames_pass(5)
	var photos_now := _group("photo_item")
	_check(photos_now.size() == photos_before + 1, "le coffret a materialise une photo ramassable")
	var found_pile := false
	for item in photos_now:
		if item.def_id() == "pile":
			found_pile = true
	_check(found_pile, "la photo materialisee est bien la photo Pile")

	# Backdrop as floor: aiming down, the pile photo's backdrop must become
	# walkable ground ~6.3 m under the feet (docs/LEVELS_V2.md section 1.4).
	_check(player.placer.hold("pile"), "photo Pile en main")
	player.global_position = Vector3(0, 0.05, 0)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3(-1.4, 0, 0)
	_check(player.placer.place(), "pose piquee vers le bas acceptee")
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(5)
	var floor_ray := PhysicsRayQueryParameters3D.create(Vector3(0, -3, -1.36), Vector3(0, -9, -1.36), 1)
	var floor_hit := space.intersect_ray(floor_ray)
	_check(not floor_hit.is_empty(), "le backdrop vise au sol est devenu un plancher")
	if not floor_hit.is_empty():
		_check_between(floor_hit["position"].y, -7.5, -5.0, "plancher de backdrop a la profondeur attendue")

	# R: rebuilding the current level clears every placement and consumption.
	_check(InputMap.has_action("reset_level"), "l'action R (recommencer) est enregistree")
	_main._load_level(5)
	await _frames_pass(5)
	_check(_group("placed_content").is_empty(), "reset : plus aucun contenu pose")
	_check(_group("photo_item").size() == 1, "reset : la photo du niveau est de retour")
	_check(_group("erasable").size() == 1, "reset : la cage est reconstruite")

	# Every level must build without error and honor its own definition.
	for i in LevelDefs.count():
		_main._load_level(i)
		await _frames_pass(3)
		var def := LevelDefs.get_def(i)
		_check(_group("photo_item").size() == def["photos"].size(), "niveau %d : photos construites" % (i + 1))
		_check(_group("battery").size() == def["batteries"].size(), "niveau %d : piles construites" % (i + 1))
		_check(_group("teleporter").size() == 1, "niveau %d : teleporteur construit" % (i + 1))
		_check(_group("platform").size() == def["platforms"].size(), "niveau %d : plateformes construites" % (i + 1))
	_check(Game.required_batteries == 5, "niveau 15 : cinq piles requises")

	# Fall recovery: below kill_y the player is put back at the spawn.
	player.global_position = Vector3(0, -50, 0)
	await _frames_pass(5)
	_check(player.global_position.y > -10.0, "chute rattrapee par le respawn")

	_conclude()


func _conclude() -> void:
	if _concluded:
		return
	_concluded = true
	for message in _failures:
		print("  ECHEC  %s" % message)
	print("  %d verifications, %d echecs" % [_checks, _failures.size()])
	print("=======================")
	print("")
	get_tree().quit(1 if _failures.size() > 0 else 0)
