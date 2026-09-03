extends Node
## Integration probe, run inside the real boot path because the autoload Game
## is not registered under --script:
##
##   godot --headless --path . -- --smoke
##
## Drives one full loop of level 1 (pick photo, place, cross, battery, insert,
## teleport), then the v4 mechanics (total replacement, empty sky photo, loose
## physics, putting a battery back down) and finally builds every level.
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


## Physics frames, not idle frames: gravity advances on the fixed step, and
## headless idle frames run far faster than real time.
func _physics_frames_pass(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


func _group(name: String) -> Array:
	return get_tree().get_nodes_in_group(name).filter(func(n): return is_instance_valid(n) and not n.is_queued_for_deletion())


## First rigid body under any of the given roots: the loose props (crates,
## placed batteries) materialize as physical shells inside the placed content.
func _first_rigid_body(node: Node) -> RigidBody3D:
	for child in node.get_children():
		if child is RigidBody3D:
			return child
		var found := _first_rigid_body(child)
		if found != null:
			return found
	return null


func _find_rigid_body(roots: Array) -> RigidBody3D:
	for root in roots:
		var found := _first_rigid_body(root)
		if found != null:
			return found
	return null


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

	# THE GROUND LANGUAGE (v5.5): grey stays, pale goes. Every block can be
	# photographed, but only the pale and lavender ones can be carved.
	_check(Player.INTERACT_RANGE == 1.7, "portee d'interaction reduite a 1.7 m")
	var carvable := _group("carvable")
	var photographable := _group("photographable")
	var grey_stays := true
	for platform in _group("platform"):
		if carvable.has(platform):
			grey_stays = false
		if not photographable.has(platform):
			_fail("une plateforme doit rester photographiable")
	_check(grey_stays, "le sol gris n'est pas decoupable : une photo s'y ajoute")
	_check(photographable.size() > carvable.size(), "on photographie plus de choses qu'on n'en decoupe")
	for block in carvable:
		_check(photographable.has(block), "tout ce qui est decoupable est aussi photographiable")

	# Pick up the bridge photo. There is NO 3D ghost anymore: the placer stays
	# an empty anchor node, the picture is raised on the HUD instead.
	var photo: Node = _group("photo_item")[0]
	photo.interact(player)
	_check(player.placer.held_id == "passerelle", "photo Passerelle en main")
	_check(player.placer.get_child_count() == 0, "aucun fantome 3D sous le placeur")

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

	# Duplication: placing the battery photo must yield a real battery, which
	# is physical since v4 and falls onto its socle.
	var before := _group("battery").size()
	var pile_photo: Node = _group("photo_item")[0]
	pile_photo.interact(player)
	player.global_position = Vector3(0, 0.05, 0)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la photo Pile acceptee")
	await _frames_pass(5)
	_check(_group("battery").size() == before + 1, "une vraie pile dupliquee par la photo")
	var placed_battery := _find_rigid_body(_group("placed_content"))
	_check(placed_battery != null, "la pile posee est portee par une coquille physique")

	# Carve check on level 4: the framed part of the wall is cut out, the
	# flanks survive as fragments, and the placed door is sealed by its own
	# painted backdrop (the seal rule became universal in v4).
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
	# Straight through the door opening: the original wall is gone there and
	# NOTHING plugs the doorway. A backdrop is a solid wall, so the door has
	# none: its own wall is the seal, and the way through stays open.
	var through := PhysicsRayQueryParameters3D.create(Vector3(0, 1.67, 1), Vector3(0, 1.67, -11), 1)
	var through_hit := space.intersect_ray(through)
	if through_hit.is_empty():
		_check(true, "l'ouverture de la porte est franche, rien ne la bouche")
	else:
		_check(through_hit["position"].z < -6.0, "rien ne bouche l'ouverture de la porte (obstacle a %.2f)" % through_hit["position"].z)
	# THE door bug: the frame dips under the standing plane past 3.47 m, so the
	# placement carves the floor right where the player must walk. The photo
	# shows that ground and puts it back, otherwise the door opens onto a pit.
	for probe_z in [-2.5, -3.5, -4.4, -5.2, -5.8]:
		var under := PhysicsRayQueryParameters3D.create(Vector3(0, 1.2, probe_z), Vector3(0, -1.5, probe_z), 1)
		var under_hit := space.intersect_ray(under)
		_check(not under_hit.is_empty(), "du sol sous les pieds en z = %.1f apres la pose de la porte" % probe_z)
		if not under_hit.is_empty():
			_check_between(under_hit["position"].y, -0.4, 0.35, "le sol de la photo affleure le plan de marche (z = %.1f)" % probe_z)
	# And the player really walks it: stand him before the door, walk him
	# forward, and check he ends up on the far side, still on his feet.
	player.global_position = Vector3(0, 0.3, -3.0)
	player.rotation = Vector3.ZERO
	player.control_enabled = true
	await _physics_frames_pass(20)
	_check(player.is_on_floor(), "le joueur a bien un sol sous les pieds devant la porte")
	Input.action_press("move_forward")
	await _physics_frames_pass(120)
	Input.action_release("move_forward")
	await _physics_frames_pass(20)
	_check(player.global_position.z < -4.8, "le joueur a franchi la porte (z = %.2f)" % player.global_position.z)
	_check(player.global_position.y > -1.0, "il ne tombe pas en la franchissant")
	_check(player.is_on_floor(), "il retombe sur du sol de l'autre cote")
	player.control_enabled = false

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

	# v4 mechanics on level 6 (a wide open platform with a cage).
	_main._load_level(5)
	await _frames_pass(10)
	var cages := _group("breakable")
	_check(cages.size() == 1, "niveau 6 : la cage est dans le groupe cassable")
	_check(_group("erasable").is_empty(), "une cage n'est plus marquee effacable")
	_check(cages[0].has_meta("cage_size"), "la cage porte sa taille pour l'objectif")
	_check(player.placer.hold("porte"), "photo Porte en main pour la cage")
	player.global_position = Vector3(4, 0.05, 2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose face a la cage acceptee")
	await _frames_pass(5)
	_check(_group("breakable").is_empty(), "la cage encadree a disparu")
	_check(_group("battery").size() == 2, "les piles encagees sont toujours la, desormais accessibles")

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

	# THE WHEEL TURNS ONE WAY, measured in the world. A quarter turn is the only
	# roll that can tell the two conventions apart (a 180 looks the same either
	# way, which is why the bug lived through twenty-five levels). The corniche
	# slab starts low on the RIGHT at (1.6, -0.6); one step down on the wheel
	# must take it low on the LEFT, at (-0.6, -1.6), where the raised picture
	# shows it. Standing at z = 5 with the eye at 1.67, that is world
	# (-0.6, 0.07, 1.8), a panel on edge whose top is at 0.97.
	_check(player.placer.hold("corniche"), "photo Corniche en main pour le quart de tour")
	player.placer.rotate_held(1)
	_check(player.placer.roll_steps == 1, "un cran de molette")
	player.global_position = Vector3(0, 0.05, 5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la corniche au quart de tour acceptee")
	await _frames_pass(5)
	var cw_ray := PhysicsRayQueryParameters3D.create(Vector3(-0.6, 3.0, 1.8), Vector3(-0.6, 0.5, 1.8), 1)
	var cw_hit := space.intersect_ray(cw_ray)
	_check(not cw_hit.is_empty(), "la corniche tournee d'un cran est passee a GAUCHE, comme sur l'image")
	if not cw_hit.is_empty():
		_check(absf(cw_hit["position"].y - 0.97) < 0.35,
			"sommet du panneau la ou l'image le montre (obtenu %.2f)" % cw_hit["position"].y)
	# And nowhere else: the old counter-clockwise placer put it high on the
	# right instead, at y = 3.27. Nothing may answer there.
	var ccw_ray := PhysicsRayQueryParameters3D.create(Vector3(0.6, 4.6, 1.8), Vector3(0.6, 2.0, 1.8), 1)
	_check(space.intersect_ray(ccw_ray).is_empty(),
		"rien en haut a droite : le monde ne tourne plus a l'envers de l'image")

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

	# Backdrop as floor: aiming down, the pile photo's painted back becomes
	# walkable ground (docs/LEVELS_V2.md section 1.4). Since v6.1 the painted
	# back stands three times further out, so this floor is a DISTANT ramp
	# rather than a step under the feet. The expected place is computed from
	# the photo's own depth: no number is written down twice.
	var pitch := -1.4
	var depth: float = PhotoDefs.get_def("pile")["backdrop"]["depth"]
	var eye_y := 0.05 + Player.EYE_HEIGHT
	var expect_y: float = eye_y - depth * sin(-pitch)
	var expect_z: float = -depth * cos(-pitch)
	_check(player.placer.hold("pile"), "photo Pile en main")
	player.global_position = Vector3(0, 0.05, 0)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3(pitch, 0, 0)
	_check(player.placer.place(), "pose piquee vers le bas acceptee")
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(5)
	var floor_ray := PhysicsRayQueryParameters3D.create(
		Vector3(0, expect_y + 6.0, expect_z), Vector3(0, expect_y - 6.0, expect_z), 1)
	var floor_hit := space.intersect_ray(floor_ray)
	_check(not floor_hit.is_empty(), "le backdrop vise au sol est devenu un plancher")
	if not floor_hit.is_empty():
		_check_between(floor_hit["position"].y, expect_y - 1.5, expect_y + 1.5,
			"plancher de backdrop a la profondeur que dicte la photo")
	_check(depth > 20.0, "le fond peint est bien un lointain, pas un couvercle")

	# Reloading the current level clears every placement and consumption.
	_check(InputMap.has_action("rewind"), "l'action R (rembobiner) est enregistree")
	_main._load_level(5)
	await _frames_pass(5)
	_check(_group("placed_content").is_empty(), "reset : plus aucun contenu pose")
	var level6_photos: int = LevelDefs.get_def(5)["photos"].size()
	_check(_group("photo_item").size() == level6_photos, "reset : les photos du niveau sont de retour")
	_check(_group("breakable").size() == 1, "reset : la cage est reconstruite")

	# REWIND. Level 6: take the photo, break the cage with it, then hold R and
	# watch the cage come back whole, the photo return to hand, and the player
	# walk backwards to where he stood.
	var rewind: Rewind = _main.rewind
	_main._load_level(5)
	await _physics_frames_pass(40)
	var start_pos := Vector3(0, 0.05, 5)
	player.global_position = start_pos
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _physics_frames_pass(30)
	# Take the door specifically: the level hands out more than one photo now,
	# and the group order is not the level order.
	var cage_photo: Node = null
	for node in _group("photo_item"):
		if node._def_id == "porte":
			cage_photo = node
	_check(cage_photo != null, "la photo Porte est dans le decor")
	if cage_photo != null:
		cage_photo.interact(player)
	_check(player.placer.held_id == "porte", "photo prise avant le rembobinage")
	_check(_group("photo_item").size() == level6_photos - 1, "la photo ramassee a quitte le decor")
	await _physics_frames_pass(30)
	player.global_position = Vector3(4, 0.05, 0)
	await _physics_frames_pass(30)
	_check(player.placer.place(), "pose faite, la cage est cassee")
	await _physics_frames_pass(30)
	_check(_group("breakable").is_empty(), "cage cassee avant le rembobinage")
	_check(_group("placed_content").size() == 1, "contenu pose avant le rembobinage")
	_check(player.placer.held_id == "", "les mains sont vides apres la pose")
	_check(rewind.available_seconds() > 1.0, "l'historique couvre les actions faites")
	_check(rewind.sample_count() > 20, "la piste de mouvement s'est remplie")
	# Photo taken, cage broken, wall carved, content placed: every structural
	# change of the level is on the undo track.
	_check(rewind.event_count() >= 3, "les changements de structure sont traces")

	# Hold R: 2.5 s of history per second, so a generous scrub goes back past
	# the placement AND past the pickup.
	# Hold the real key: main drives the rewind on the physics clock.
	Input.action_press("rewind")
	await _physics_frames_pass(2)
	_check(rewind.is_rewinding(), "le rembobinage est actif")
	await _physics_frames_pass(150)
	_check(_group("breakable").size() == 1, "la cage est revenue entiere")
	_check(_group("placed_content").is_empty(), "le contenu pose a ete defait")
	_check(_group("photo_item").size() == level6_photos, "la photo est de retour dans le decor")
	_check(player.placer.held_id == "", "les mains sont vides comme avant la prise")
	_check(player.global_position.distance_to(start_pos) < 1.5, "le joueur est revenu a son point de depart")
	Input.action_release("rewind")
	await _physics_frames_pass(2)
	_check(not rewind.is_rewinding(), "le rembobinage s'arrete au relachement")

	# The rewound future is gone: history restarts here, and the world stays
	# exactly as the rewind left it.
	await _physics_frames_pass(20)
	_check(_group("breakable").size() == 1, "la cage reste entiere apres le relachement")
	_check(_group("photo_item").size() == level6_photos, "la photo reste dans le decor")
	await _physics_frames_pass(20)

	# Rewinding a battery pickup gives the battery back to the world.
	var battery_before := _group("battery").size()
	var some_battery: Node = _group("battery")[0]
	some_battery.interact(player)
	_check(Game.carried_batteries == 1, "pile ramassee avant le rembobinage")
	_check(_group("battery").size() == battery_before - 1, "la pile ramassee a quitte le sol")
	await _physics_frames_pass(30)
	Input.action_press("rewind")
	await _physics_frames_pass(60)
	Input.action_release("rewind")
	await _physics_frames_pass(2)
	_check(Game.carried_batteries == 0, "le rembobinage rend la pile portee")
	_check(_group("battery").size() == battery_before, "la pile est de retour a sa place")

	# Physics of loose objects: a crate placed upside down from the ground
	# materializes above the head and FALLS. Hanging boxes in the air is over.
	_check(player.placer.hold("caisse"), "photo Caisse en main")
	player.placer.rotate_held(1)
	player.placer.rotate_held(1)
	_check(player.placer.roll_steps == 2, "caisse retournee a 180 degres")
	player.global_position = Vector3(0, 0.05, 5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose de la caisse retournee acceptee")
	await _frames_pass(2)
	var crate := _find_rigid_body(_group("placed_content"))
	_check(crate != null, "la caisse posee est un corps physique")
	if crate != null:
		var spawn_y: float = crate.global_position.y
		_check(spawn_y > 2.0, "la caisse retournee apparait en hauteur (obtenu %.2f)" % spawn_y)
		await _physics_frames_pass(60)
		if is_instance_valid(crate):
			_check(crate.global_position.y < spawn_y - 0.5,
				"la caisse est tombee sous sa hauteur de pose (%.2f puis %.2f)" % [spawn_y, crate.global_position.y])
			_check(crate.global_position.y > -5.0, "la caisse a fini sa chute sur la plateforme")
		else:
			_fail("la caisse posee a disparu pendant sa chute")

	# STACKING, the whole point of the falling crate and the load bearing move
	# of levels 23 and 25. A crate placed the right way up lands at the player's
	# feet, top at 1.3. A second one placed UPSIDE DOWN from the same spot
	# appears a metre above the eye, 2.6 m ahead, and drops onto the first:
	# top at 2.6, which a jump turns into 4.1. Placing it the right way up would
	# only ever give 1.3, so this is the one move that cannot be improvised.
	_main._load_level(0)
	await _frames_pass(20)
	player.global_position = Vector3(0, 0.05, 4)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _physics_frames_pass(4)
	_check(player.placer.hold("caisse"), "premiere caisse en main")
	_check(player.placer.place(), "premiere caisse posee a l'endroit")
	await _physics_frames_pass(60)
	var first_crate := _find_rigid_body(_group("placed_content"))
	var first_top := 0.0
	if first_crate == null:
		_fail("la premiere caisse n'a pas ete construite")
	else:
		first_top = first_crate.global_position.y + 0.65
		_check_between(first_top, 1.1, 1.5, "la premiere caisse repose au sol, sommet a %.2f m" % first_top)

	# Same spot, same aim, photo turned over: the target is the crate itself.
	_check(player.placer.hold("caisse"), "seconde caisse en main")
	player.placer.rotate_held(1)
	player.placer.rotate_held(1)
	_check(player.placer.roll_steps == 2, "seconde caisse retournee")
	_check(player.placer.place(), "seconde caisse posee retournee")
	await _physics_frames_pass(90)
	var top_crate: RigidBody3D = null
	var lower_crate: RigidBody3D = null
	for node in _group("placed_content"):
		var body := _first_rigid_body(node)
		if body == null or not is_instance_valid(body):
			continue
		if top_crate == null or body.global_position.y > top_crate.global_position.y:
			lower_crate = top_crate
			top_crate = body
		else:
			lower_crate = body
	if top_crate == null or lower_crate == null:
		_fail("les deux caisses ne coexistent pas apres la seconde pose")
	else:
		var stack_top: float = top_crate.global_position.y + 0.65
		_check_between(stack_top, 2.3, 2.9, "la pile de deux caisses culmine a %.2f m" % stack_top)
		_check(stack_top > first_top + 1.0,
			"la seconde caisse est retombee SUR la premiere, pas a cote (%.2f puis %.2f)" % [first_top, stack_top])
		# A jump from the top of the stack clears 4.1 m: that is the number the
		# towers of levels 23 and 25 are cut to.
		_check(stack_top + 1.5 >= 4.0, "l'empilement plus un saut atteint bien 4 m")
		# Placing a photo never carves a crate: they are rigid bodies, not
		# blocks, so a stack survives the next placement.
		_check(is_instance_valid(lower_crate) and lower_crate.is_inside_tree(),
			"la premiere caisse a survecu a la pose de la seconde")

	# E without a target puts one carried battery back on the ground. Stand in
	# an empty corner: the prompt only appears when the ray finds nothing.
	player.global_position = Vector3(7, 0.05, 6)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(2)
	var batteries_before_drop := _group("battery").size()
	Game.collect_battery()
	player._update_interact_target()
	_check(player.interact_prompt == "E : reposer une pile", "invite de repose affichee les mains pleines")
	_check(Game.drop_battery() == "normal", "drop_battery accepte avec une pile portee")
	player._spawn_dropped_battery(false)
	await _frames_pass(3)
	_check(_group("battery").size() == batteries_before_drop + 1, "la pile reposee est de retour au sol")
	_check(_group("copyable_battery").size() == _group("battery").size(),
		"une pile ordinaire reposee reste photocopiable")
	_check(Game.carried_batteries == 0, "plus rien en main apres la repose")
	_check(Game.drop_battery() == "", "reposer sans pile est refuse")

	# The lead never launders itself: carried leaden, put back leaden, and the
	# thing on the ground is still invisible to film.
	var copyable_before_lead := _group("copyable_battery").size()
	Game.collect_battery(true)
	_check(Game.carried_sealed == 1, "une pile plombee en main est comptee comme telle")
	_check(Game.drop_battery() == "sealed", "c'est bien du plomb qui redescend")
	player._spawn_dropped_battery(true)
	await _frames_pass(3)
	_check(_group("battery").size() == batteries_before_drop + 2, "la pile plombee est au sol")
	_check(_group("copyable_battery").size() == copyable_before_lead,
		"une pile plombee reposee reste hors de portee de la pellicule")

	# Raised photo (right click): the 2D picture replaces the old ghost, it
	# turns with the wheel on the HUD, and placing while raised lowers it.
	_check(player.placer.hold("passerelle"), "photo en main pour la levee")
	player.placer.raise_toggle()
	_check(player.placer.raised, "clic droit : photo levee")
	player.placer.raise_toggle()
	_check(not player.placer.raised, "second clic droit : photo baissee")
	player.placer.raise_toggle()
	player.placer.rotate_held(1)
	await _frames_pass(3)
	var photo_view: Control = _main.hud._photo_view
	_check(photo_view.visible, "l'image levee s'affiche sur le HUD")
	_check(absf(photo_view.rotation - PI * 0.5) < 0.01, "l'image levee est tournee d'un cran de molette")
	_check(photo_view.pivot_offset.x > 0.0, "pivot de rotation place au centre de l'image")
	player.placer.rotate_held(-1)
	player.global_position = Vector3(0, 0.05, 4)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose acceptee pendant que la photo est levee")
	_check(not player.placer.raised, "la photo levee retombe apres la pose")
	await _frames_pass(3)
	_check(not photo_view.visible, "l'image disparait du HUD une fois posee")

	# Level 16: the camera. The sky is a legitimate subject, the film is always
	# consumed, and the empty photo pierces whatever it frames.
	_main._load_level(15)
	await _frames_pass(10)
	_check(Game.level_index == 15, "niveau 16 charge")
	_check(Game.camera_films == 0, "pellicule vide avant l'appareil")
	var camera_items := _group("camera_item")
	_check(camera_items.size() == 1, "niveau 16 : un appareil photo")
	if camera_items.size() == 1:
		camera_items[0].interact(player)
	_check(Game.camera_films == 2, "pellicule chargee : 2 vues")

	player.global_position = Vector3(0, 0.05, 0.5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3(1.2, 0, 0)
	# The shutter answers only through the viewfinder: aim first, shoot second.
	_check(not player.capture_photo(), "declencher sans viser est refuse")
	_check(Game.camera_films == 2, "un declenchement refuse ne coute pas de pellicule")
	_check(player.toggle_viewfinder(), "clic droit mains vides : appareil a l'oeil")
	_check(player.viewfinder, "le viseur est actif")
	_check(player.capture_photo(), "cliche du ciel accepte : le vide est un sujet")
	_check(not player.viewfinder, "le viseur se referme apres le declenchement")
	_check(Game.camera_films == 1, "la photo vide consomme bien une vue")
	_check(player.placer.raised, "le cliche sort leve, comme un polaroid frais")
	var sky_def := PhotoDefs.get_def(player.placer.held_id)
	_check(not sky_def.is_empty(), "le cliche du ciel est une definition valide")
	_check(sky_def.get("props", []).is_empty(), "le cliche du ciel ne contient aucun prop")
	_check(absf(float(sky_def["backdrop"]["depth"]) - 36.0) < 0.001, "fond peint du cliche a 36 m")
	_check(absf(float(sky_def["erase_depth"]) - 12.0) < 0.001, "le cliche efface sur les 12 m qu'il a captures")

	player.camera.rotation = Vector3.ZERO
	_check(_group("breakable").size() == 1, "niveau 16 : le teleporteur est encage")
	_check(player.placer.place(), "pose de la photo vide acceptee")
	await _frames_pass(5)
	_check(_group("breakable").is_empty(), "la photo vide a fauche la cage")

	# Capture is a COPY: the lavender plank stays where it is, and the copy
	# placed over the gap becomes a walkable deck.
	_check(_group("erasable").size() == 1, "niveau 16 : une planche lavande")
	var plank: ErasableBlock = _group("erasable")[0]
	var plank_pos := plank.global_position
	var plank_size := plank.block_size
	player.global_position = Vector3(4, 0.05, 7.6)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	var shot_anchor: Transform3D = player.camera.global_transform
	player.toggle_viewfinder()
	_check(player.capture_photo(), "cliche pris sur la planche lavande")
	_check(player.placer.held_id.begins_with("cliche_"), "le cliche est en main")
	_check(Game.camera_films == 0, "seconde vue consommee")
	var plank_def := PhotoDefs.get_def(player.placer.held_id)
	var lavender_props := 0
	for prop in plank_def.get("props", []):
		if prop.get("color", "") == "erasable":
			lavender_props += 1
			_check(not prop.has("loose"), "une planche de 4 m reste solidaire sur le cliche")
	_check(lavender_props == 1, "la planche lavande figure sur le cliche")
	# FIDELITY: an object entirely in frame is on the photo at its real size
	# and its real place, so placing the shot from where it was taken lays the
	# copy exactly over the original.
	var expected_pos: Vector3 = shot_anchor.affine_inverse() * plank_pos
	for prop in plank_def.get("props", []):
		if prop.get("color", "") != "erasable":
			continue
		var offset: float = (prop["pos"] as Vector3).distance_to(expected_pos)
		_check(offset < 0.01, "la planche est au bon endroit sur le cliche (ecart %.3f m)" % offset)
		var size_error: float = (prop["size"] as Vector3).distance_to(plank_size)
		_check(size_error < 0.01, "la planche est a la bonne taille sur le cliche (ecart %.3f m)" % size_error)
	# v5.1: the ground in the frame is on the photo too. Without it, placing
	# the shot would carve the floor away and drop the player through his own
	# picture (capture tested centers while placement carves volumes).
	var ground_props := 0
	for prop in plank_def.get("props", []):
		if prop.get("color", "") == "platform":
			ground_props += 1
			_check(not prop.has("loose"), "un morceau de sol reste solidaire")
	_check(ground_props > 0, "le sol cadre figure sur le cliche")
	player.global_position = Vector3(0, 0.05, 1.5)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose du cliche acceptee")
	await _frames_pass(5)
	var copy_ray := PhysicsRayQueryParameters3D.create(Vector3(0, 1, -1.5), Vector3(0, -1, -1.5), 1)
	var copy_hit := space.intersect_ray(copy_ray)
	_check(not copy_hit.is_empty(), "la copie de la planche enjambe le vide")
	_check(not _group("erasable").is_empty(), "l'originale n'a pas ete detruite : c'est une copie")
	# The reported symptom, guarded: the ground framed by the shot is part of
	# the shot, so placing it cannot drop the player through his own picture.
	var floor_check := PhysicsRayQueryParameters3D.create(Vector3(0, 1.5, 1.5), Vector3(0, -2.0, 1.5), 1)
	_check(not space.intersect_ray(floor_check).is_empty(), "le sol reste sous les pieds apres la pose du cliche")
	player.control_enabled = true
	await _physics_frames_pass(40)
	_check(player.global_position.y > -1.0, "le joueur ne tombe pas a travers sa propre photo")
	_check(player.is_on_floor(), "le joueur tient toujours debout sur le sol")

	# Level 19: the capture is geometric, bars do not block it.
	_main._load_level(18)
	await _frames_pass(10)
	_group("camera_item")[0].interact(player)
	_check(Game.camera_films == 2, "niveau 19 : 2 vues")
	var batteries_before := _group("battery").size()
	_check(batteries_before == 3, "niveau 19 : trois piles dont deux encagees")
	player.global_position = Vector3(0, 0.05, -2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	player.toggle_viewfinder()
	_check(player.capture_photo(), "cliche pris a travers les barreaux")
	var cliche_def := PhotoDefs.get_def(player.placer.held_id)
	var captured_batteries := 0
	var captured_cage := 0
	for prop in cliche_def.get("props", []):
		if prop["kind"] == "battery":
			captured_batteries += 1
		if prop.get("color", "") in ["battery_tip", "sealed"]:
			captured_cage += 1
	_check(captured_batteries == 2, "les deux piles encagees sont sur le cliche")
	# The bars are a lattice, not a volume: a copied cage would materialize
	# around the copied batteries and seal them in.
	_check(captured_cage == 0, "la cage elle-meme n'est pas copiee")
	player.global_position = Vector3(-4, 0.05, 2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	var copyable_before_shot := _group("copyable_battery").size()
	_check(player.placer.place(), "pose du cliche de piles acceptee")
	await _frames_pass(5)
	_check(_group("battery").size() == batteries_before + 2, "deux vraies piles dupliquees hors de la cage")
	# FILM DOES NOT PRINT FILM. The copies are leaden, so the count of subjects
	# has not moved: without this a player photographs a copy next to its
	# original and doubles his batteries at every shot.
	_check(_group("copyable_battery").size() == copyable_before_shot,
		"les copies ne sont pas elles-memes photographiables")

	# Level 21: steel. No placement opens it, and the way out is the lens.
	_main._load_level(20)
	await _frames_pass(10)
	_check(_group("cage").size() == 1, "niveau 21 : une cage")
	_check(_group("breakable").is_empty(), "niveau 21 : l'acier n'est pas cassable")
	var steel_cage: Node = _group("cage")[0]
	player.global_position = Vector3(0, 0.05, -2.6)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _frames_pass(2)
	# A placement squarely on the cage: a lavender one would vanish here.
	_check(player.placer.hold("caisse"), "photo en main face a l'acier")
	_check(player.placer.place(), "pose acceptee face a l'acier")
	await _frames_pass(5)
	_check(is_instance_valid(steel_cage) and steel_cage.is_inside_tree(),
		"la cage d'acier survit a une pose qui attrape son centre")
	# The interaction ray does not pass either: the caged battery is a model.
	player._update_interact_target()
	_check(player.interact_prompt != "E : ramasser la pile", "la pile sous acier reste hors de portee")
	# But the lens does pass.
	_group("camera_item")[0].interact(player)
	player.toggle_viewfinder()
	_check(player.capture_photo(), "cliche pris a travers l'acier")
	var steel_shot := PhotoDefs.get_def(player.placer.held_id)
	var steel_batteries := 0
	for prop in steel_shot.get("props", []):
		if prop["kind"] == "battery":
			steel_batteries += 1
	# Both caged batteries at once: from the corail mark the cage is 3.4 m away,
	# the half frame is 1.59 m, and they stand at x = +/-0.8. One shot, two
	# copies, and there is no other battery in the level: the steel cage is the
	# only way through, which is the entire point of the level that teaches it.
	_check(steel_batteries == 2, "les deux piles sous acier tiennent dans un seul cliche")
	player.placer.drop()

	# Level 22: lead. The battery is there, the film does not see it.
	_main._load_level(21)
	await _frames_pass(10)
	var lead_def := LevelDefs.get_def(21)
	_check(_group("battery").size() == lead_def["batteries"].size() + lead_def["sealed_batteries"].size(),
		"niveau 22 : toutes les piles construites, plombees comprises")
	_check(_group("copyable_battery").size() == lead_def["batteries"].size(),
		"niveau 22 : seules les piles vives sont photocopiables")
	var lead_battery: Node = null
	for node in _group("battery"):
		if not node.is_in_group("copyable_battery"):
			lead_battery = node
	_check(lead_battery != null, "la pile plombee est dans le decor")
	if lead_battery != null:
		# Stand right under it and shoot: the film comes back without it.
		player.global_position = lead_battery.global_position + Vector3(0, 0.05, 3.2)
		player.rotation = Vector3.ZERO
		player.camera.rotation = Vector3.ZERO
		await _frames_pass(2)
		_group("camera_item")[0].interact(player)
		player.toggle_viewfinder()
		_check(player.capture_photo(), "cliche pris sur la pile plombee")
		var lead_shot := PhotoDefs.get_def(player.placer.held_id)
		var printed := 0
		for prop in lead_shot.get("props", []):
			if prop["kind"] == "battery":
				printed += 1
		_check(printed == 0, "aucune pile plombee ne s'imprime sur la pellicule")
		player.placer.drop()

	# Level 13: A FLIGHT PLACED FROM THE LANDING OF A FLIGHT. This is the whole
	# level, and it is the kind of claim that has to be measured rather than
	# asserted: the sky ramp it used to be built on died when the painted back
	# moved out to three times its old distance, and nothing but a run in the
	# engine proves what replaced it actually carries the player.
	_main._load_level(12)
	await _frames_pass(10)
	var tower_top := 8.0
	player.global_position = Vector3(0, 0.05, 3.0)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _physics_frames_pass(4)
	_check(player.placer.hold("escalier"), "premiere volee en main")
	_check(player.placer.place(), "premiere volee posee depuis le sol")
	await _physics_frames_pass(10)
	# The invisible walkable ramp of a flight, sampled near its top.
	var ramp_ray := PhysicsRayQueryParameters3D.create(Vector3(0, 7.0, -4.6), Vector3(0, 0.5, -4.6), 1)
	var ramp_hit := space.intersect_ray(ramp_ray)
	_check(not ramp_hit.is_empty(), "la premiere volee offre une surface ou marcher")
	var landing := 0.0
	if not ramp_hit.is_empty():
		landing = ramp_hit["position"].y
		_check_between(landing, 3.5, 5.2, "palier de la premiere volee a la hauteur prevue")

	# Stand ON that landing and place the second flight from there.
	player.global_position = Vector3(0, landing + 0.1, -4.6)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	await _physics_frames_pass(8)
	_check(player.is_on_floor(), "le joueur tient debout sur la volee posee")
	_check(player.placer.hold("escalier"), "seconde volee en main")
	_check(player.placer.place(), "seconde volee posee depuis le palier de la premiere")
	await _physics_frames_pass(10)
	# Somewhere along the second flight there must be ground high enough that a
	# jump reaches the tower. Sample it just in front of the tower face.
	var high_ray := PhysicsRayQueryParameters3D.create(Vector3(0, 12.0, -9.8), Vector3(0, 4.0, -9.8), 1)
	var high_hit := space.intersect_ray(high_ray)
	_check(not high_hit.is_empty(), "la seconde volee monte bien au dessus de la premiere")
	if not high_hit.is_empty():
		var reached: float = high_hit["position"].y
		_check(reached > landing + 1.0, "la seconde volee gagne de la hauteur sur la premiere (%.2f puis %.2f)" % [landing, reached])
		_check(reached + 1.509 >= tower_top,
			"depuis la seconde volee, un saut atteint le sommet de la tour (%.2f + 1.51 pour %.2f)" % [reached, tower_top])

	# Every level must build without error and honor its own definition.
	for i in LevelDefs.count():
		_main._load_level(i)
		await _frames_pass(3)
		var def := LevelDefs.get_def(i)
		var sealed_batteries: Array = def.get("sealed_batteries", [])
		var breakable_cages := 0
		for cage in def.get("cages", []):
			if not cage.get("sealed", false):
				breakable_cages += 1
		_check(_group("photo_item").size() == def["photos"].size(), "niveau %d : photos construites" % (i + 1))
		_check(_group("battery").size() == def["batteries"].size() + sealed_batteries.size(),
			"niveau %d : piles construites" % (i + 1))
		_check(_group("copyable_battery").size() == def["batteries"].size(),
			"niveau %d : le plomb reste hors de la pellicule" % (i + 1))
		_check(_group("teleporter").size() == 1, "niveau %d : teleporteur construit" % (i + 1))
		_check(_group("platform").size() == def["platforms"].size(), "niveau %d : plateformes construites" % (i + 1))
		_check(_group("cage").size() == def.get("cages", []).size(), "niveau %d : cages construites" % (i + 1))
		_check(_group("breakable").size() == breakable_cages, "niveau %d : cages cassables construites" % (i + 1))
	_check(Game.required_batteries == 5, "niveau 25 : cinq piles requises")

	# Losing costs the level: falling below kill_y rebuilds it from scratch,
	# so nothing the player had placed or carried survives the fall.
	_main._load_level(0)
	await _frames_pass(30)
	_check(player.placer.hold("passerelle"), "photo en main avant la chute")
	player.global_position = Vector3(0, 0.05, -2.2)
	player.rotation = Vector3.ZERO
	player.camera.rotation = Vector3.ZERO
	_check(player.placer.place(), "pose faite avant la chute")
	var battery_before_fall: Node = _group("battery")[0]
	battery_before_fall.interact(player)
	_check(Game.carried_batteries == 1, "pile portee avant la chute")
	await _frames_pass(5)
	_check(_group("placed_content").size() == 1, "contenu pose present avant la chute")

	player.global_position = Vector3(0, -50, 0)
	await _physics_frames_pass(4)
	await _frames_pass(30)
	_check(player.global_position.y > -10.0, "chute rattrapee : le joueur est revenu au depart")
	_check(_group("placed_content").is_empty(), "la chute efface les poses du niveau")
	_check(_group("photo_item").size() == 1, "la chute rend la photo consommee")
	_check(_group("battery").size() == 1, "la chute remet la pile ramassee dans le decor")
	_check(Game.carried_batteries == 0, "la chute vide l'inventaire de piles")
	_check(player.control_enabled, "le joueur reprend la main apres la chute")

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
