extends WarTest
## The imported characters are the one part of the game that can break without
## anyone touching a line of code: a re-import, a renamed bone or a refreshed
## download is enough. These tests pin the handful of facts the adapter relies
## on, all of which were wrong at least once while it was being written.
##
## Every test is skipped cleanly when `assets/models` is absent, because running
## without it is a supported configuration, not a failure.

const _SPECIES := [CharacterModels.SPECIES_SOLDIER, CharacterModels.SPECIES_ZOMBIE]

# Faction ids, mirrored rather than read from `War`: the suite runs under
# --script, where autoloads do not exist. Same reason `Meshes` mirrors them.
const _ALLIED := 0
const _AXIS := 1

# What each rig is expected to carry. Kept here rather than read back out of
# `CharacterModels` so a typo in the table is a failure and not a tautology.
const _EXPECTED := {
	CharacterModels.SPECIES_SOLDIER: {
		"hand": "Wrist.R",
		"clips": ["idle", "idle_aim", "walk", "run", "run_aim", "fire", "hit", "death"],
		"name": "soldat",
	},
	CharacterModels.SPECIES_ZOMBIE: {
		"hand": "RightHand",
		"clips": ["idle", "walk", "run", "fire"],
		"name": "zombie",
	},
}


func suite_name() -> String:
	return "character_models"


## True when no model is installed, which is a supported configuration rather
## than a failure. Asserts the box soldier really took over on the way out, so
## an asset-less run still proves something: the runner counts a method that
## checks nothing as a failure, and rightly so.
func _no_models() -> bool:
	if CharacterModels.available(CharacterModels.SPECIES_SOLDIER):
		return false
	var box := Meshes.soldier_body(_AXIS, 0, CharacterModels.SPECIES_SOLDIER)
	check(box != null and box.find_child("Torso", true, false) != null,
			"sans assets/models, Meshes doit rendre le soldat en boites")
	if box != null:
		box.free()
	return true


func test_both_species_are_installed_or_none_is() -> void:
	# A half-installed folder is the confusing case: soldiers imported, zombies
	# silently procedural. Flag it rather than let it pass unnoticed.
	if _no_models():
		done()
		return
	for species in _SPECIES:
		check(CharacterModels.available(species),
				"espece %d absente alors que le dossier de modeles existe" % species)
	done()


func test_a_body_keeps_the_shape_its_callers_expect() -> void:
	if _no_models():
		done()
		return
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		check(body != null, "aucun corps pour l'espece %d" % species)
		if body == null:
			continue
		eq(body.name, "SoldierBody", "le nom racine attendu par Soldier a change")
		# Soldier fires from this node: without it the bullets come from the
		# soldier's feet. `find_child` recursive is exactly how Soldier looks.
		check(body.find_child("Weapon", true, false) != null,
				"espece %d sans noeud Weapon" % species)
		body.free()
	done()


func test_the_model_is_scaled_to_human_height() -> void:
	if _no_models():
		done()
		return
	for species in _SPECIES:
		var body := Meshes.soldier_body(_ALLIED, 0, species)
		if body == null:
			continue
		check(_skeleton(body) != null, "espece %d sans Skeleton3D" % species)
		# Largest mesh dimension, brought into world units. Deliberately not the
		# bone pose: out of the tree a skeleton reports its bind pose, and the
		# soldier's is a crouch that measures 0.8 m on a perfectly good model.
		#
		# A loose band on purpose. These meshes are authored Z-up, so the tall
		# axis is not always Y, and the zombie's bind-space bounds are inflated
		# by a third. What it catches is the blunder that actually happens: a
		# forgotten armature factor, or the two species' scales swapped, both of
		# which land orders of magnitude outside it.
		var span := _visual_span(body)
		between(span, 1.40, 2.40,
				"espece %d : taille hors norme humaine (%.2f m)" % [species, span])
		body.free()
	done()


func test_the_model_is_turned_to_face_minus_z() -> void:
	if _no_models():
		done()
		return
	# Both models are authored facing +Z; the whole project assumes -Z. The Rig
	# node is where that gets corrected, and nothing else in the game does it.
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		if body == null:
			continue
		var rig := body.get_node_or_null("Rig") as Node3D
		check(rig != null, "espece %d sans noeud Rig" % species)
		if rig != null:
			near(absf(rig.rotation.y), PI, 0.01,
					"espece %d : le demi-tour de face n'est plus applique" % species)
		body.free()
	done()


func test_the_weapon_survives_the_armature_scale() -> void:
	if _no_models():
		done()
		return
	# The armature exports at ~100x. A weapon parented to a hand bone inherits
	# that, and without the counter-scale the rifle comes out the size of a
	# telegraph pole. This is the exact bug this test exists for.
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		if body == null:
			continue
		var weapon := body.find_child("Weapon", true, false) as Node3D
		if weapon != null:
			var world := weapon.scale.y * _scale_to(weapon, body)
			near(world, 1.0, 0.05,
					"espece %d : l'arme sort a l'echelle %.2f au lieu de 1"
							% [species, world])
		body.free()
	done()


func test_every_clip_the_adapter_names_really_exists() -> void:
	if _no_models():
		done()
		return
	# A renamed animation is silent: the driver simply never plays it.
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		if body == null:
			continue
		var driver := CharacterAnim.attach(body, species)
		check(driver != null, "espece %d sans AnimationPlayer" % species)
		if driver != null:
			for key in _EXPECTED[species]["clips"]:
				check(driver.has(key), "espece %s : clip '%s' introuvable"
						% [_EXPECTED[species]["name"], key])
		body.free()
	done()


func test_the_zombie_declares_its_missing_death_clip() -> void:
	if _no_models():
		done()
		return
	# Soldier reads this to decide between the death animation and the
	# procedural tip-over. If it ever lies, corpses freeze upright.
	var zombie := Meshes.soldier_body(_AXIS, 0, CharacterModels.SPECIES_ZOMBIE)
	if zombie != null:
		var driver := CharacterAnim.attach(zombie, CharacterModels.SPECIES_ZOMBIE)
		if driver != null:
			check(not driver.has("death"),
					"le zombie annonce une animation de mort qu'il n'a pas")
		zombie.free()

	var soldier := Meshes.soldier_body(_AXIS, 0, CharacterModels.SPECIES_SOLDIER)
	if soldier != null:
		var driver := CharacterAnim.attach(soldier, CharacterModels.SPECIES_SOLDIER)
		if driver != null:
			check(driver.has("death"), "le soldat a perdu son animation de mort")
		soldier.free()
	done()


func test_the_hand_bone_is_still_named_as_the_table_says() -> void:
	if _no_models():
		done()
		return
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		if body == null:
			continue
		var skeleton := _skeleton(body)
		if skeleton != null:
			var bone: String = _EXPECTED[species]["hand"]
			check(skeleton.find_bone(bone) >= 0,
					"espece %s : os de main '%s' disparu, l'arme tomberait aux pieds"
							% [_EXPECTED[species]["name"], bone])
		body.free()
	done()


func test_locomotion_clips_loop() -> void:
	if _no_models():
		done()
		return
	# glTF import brings every clip in as a one-shot. A walk cycle that does not
	# loop leaves the soldier frozen mid-stride after one second.
	for species in _SPECIES:
		var body := Meshes.soldier_body(_AXIS, 0, species)
		if body == null:
			continue
		var player := _player(body)
		var prefix := CharacterModels.clip_prefix(species)
		var clips := CharacterModels.clips(species)
		if player != null:
			for key in ["idle", "walk", "run"]:
				if not clips.has(key):
					continue
				var full: String = "%s%s" % [prefix, clips[key]]
				if player.has_animation(full):
					eq(player.get_animation(full).loop_mode, Animation.LOOP_LINEAR,
							"espece %d : le clip '%s' ne boucle pas" % [species, key])
		body.free()
	done()


func test_an_unknown_species_falls_back_instead_of_crashing() -> void:
	# The procedural box soldier is the contract for anything unrecognised.
	check(not CharacterModels.available(999), "une espece inconnue se dit disponible")
	var body := Meshes.soldier_body(_AXIS, 0, 999)
	check(body != null, "aucun repli pour une espece inconnue")
	if body != null:
		# The box soldier, and only it, exposes the named limbs.
		check(body.find_child("Torso", true, false) != null,
				"le repli n'est pas le soldat en boites")
		body.free()
	done()


# --- helpers -----------------------------------------------------------------

func _skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node as Skeleton3D
	for child in node.get_children():
		var hit := _skeleton(child)
		if hit != null:
			return hit
	return null


func _player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node as AnimationPlayer
	for child in node.get_children():
		var hit := _player(child)
		if hit != null:
			return hit
	return null


## Largest dimension of any mesh under `body`, expressed in world units.
func _visual_span(body: Node3D) -> float:
	var best := 0.0
	for mi in _meshes(body):
		if mi.mesh == null:
			continue
		var size := mi.mesh.get_aabb().size
		var longest: float = maxf(size.x, maxf(size.y, size.z))
		best = maxf(best, longest * _scale_to(mi, body))
	return best


func _meshes(node: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if node is MeshInstance3D:
		out.append(node as MeshInstance3D)
	for child in node.get_children():
		out.append_array(_meshes(child))
	return out


## Product of the scales between `node` and `stop`, exclusive. Walked by hand:
## these bodies are never added to the tree, so `global_transform` is unusable.
func _scale_to(node: Node3D, stop: Node3D) -> float:
	var out := 1.0
	var cur: Node = node.get_parent()
	while cur != null and cur != stop and cur is Node3D:
		out *= (cur as Node3D).scale.y
		cur = cur.get_parent()
	return out
