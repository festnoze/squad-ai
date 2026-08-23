extends WarTest
## Vegetation and clutter placement. It runs on the streaming worker threads, so
## it must be pure; and its density decides whether the game runs at 120 frames
## per second or at 12.


func suite_name() -> String:
	return "scatter"


const SEED := 13572468


func _field() -> Heightfield:
	var layout := Layout.new(SEED)
	var hf := Heightfield.new(layout)
	hf.bake_sites()
	return hf


func test_a_tile_produces_something_but_not_too_much() -> void:
	var hf := _field()
	var populated := 0
	var worst := 0
	for tx in range(-3, 4):
		for tz in range(-3, 4):
			var instances := Scatter.for_tile(hf, tx, tz)
			worst = maxi(worst, instances.size())
			if not instances.is_empty():
				populated += 1
	check(populated > 0, "aucune tuile ne produit de vegetation")
	check(worst <= Scatter.MAX_INSTANCES,
				"une tuile produit %d instances pour un plafond de %d, le streaming va s'ecrouler"
						% [worst, Scatter.MAX_INSTANCES])
	done()


func test_scatter_is_deterministic_per_tile() -> void:
	# The same tile is regenerated every time the player walks back, so a random
	# result would make the forest dance.
	var hf := _field()
	var first := Scatter.for_tile(hf, 2, -5)
	var second := Scatter.for_tile(hf, 2, -5)
	eq(first.size(), second.size(), "le nombre d'instances change entre deux appels")
	var drift := 0
	for i in mini(first.size(), second.size()):
		if not first[i].position.is_equal_approx(second[i].position):
			drift += 1
		if first[i].kind != second[i].kind:
			drift += 1
	eq(drift, 0, "le contenu d'une tuile n'est pas reproductible (%d ecarts)" % drift)
	done()


func test_neighbouring_tiles_do_not_share_content() -> void:
	var hf := _field()
	var here := Scatter.for_tile(hf, 4, 4)
	var there := Scatter.for_tile(hf, 5, 4)
	if here.is_empty() and there.is_empty():
		check(true, "les deux tuiles sont vides, rien a comparer")
		done()
		return
	var same := 0
	for i in mini(here.size(), there.size()):
		if here[i].position.is_equal_approx(there[i].position):
			same += 1
	check(same == 0, "deux tuiles voisines produisent les memes positions")
	done()


func test_every_instance_is_valid_and_inside_its_tile() -> void:
	var hf := _field()
	var tx := 6
	var tz := -2
	var instances := Scatter.for_tile(hf, tx, tz)
	var x0 := float(tx) * Heightfield.TILE_SIZE
	var z0 := float(tz) * Heightfield.TILE_SIZE
	for instance in instances:
		check(instance.kind >= 0 and instance.kind < Scatter.KIND_COUNT,
				"type de decor invalide : %d" % instance.kind)
		check(instance.scale > 0.0, "un decor a une echelle nulle ou negative")
		check(is_finite(instance.position.y), "un decor a une altitude non finie")
		# A margin is fine (a hedge straddles a boundary), a tile away is not.
		check(instance.position.x >= x0 - 8.0 and instance.position.x <= x0 + Heightfield.TILE_SIZE + 8.0,
				"un decor deborde largement de sa tuile en x")
		check(instance.position.z >= z0 - 8.0 and instance.position.z <= z0 + Heightfield.TILE_SIZE + 8.0,
				"un decor deborde largement de sa tuile en z")
	done()


func test_nothing_grows_under_water() -> void:
	var hf := _field()
	var drowned := 0
	var checked := 0
	for tx in range(-6, 7, 3):
		for tz in range(-6, 7, 3):
			for instance in Scatter.for_tile(hf, tx, tz):
				checked += 1
				if instance.position.y < Heightfield.WATER_LEVEL - 0.6:
					drowned += 1
	check(checked > 0, "aucune instance examinee")
	check(drowned == 0, "%d decors poussent sous le niveau de l'eau" % drowned)
	done()


func test_props_sit_on_the_terrain_not_above_it() -> void:
	var hf := _field()
	var floating := 0
	var checked := 0
	for instance in Scatter.for_tile(hf, 1, 1):
		checked += 1
		var ground := hf.height_at(instance.position.x, instance.position.z)
		if absf(instance.position.y - ground) > 2.5:
			floating += 1
	if checked == 0:
		check(true, "tuile vide, rien a verifier")
		done()
		return
	check(floating == 0, "%d decors flottent au dessus du sol ou sont enterres" % floating)
	done()


func test_batching_and_collision_flags_are_coherent() -> void:
	for kind in Scatter.KIND_COUNT:
		# Asking for a collision size on a colliding kind must give something
		# usable, otherwise the world builder creates zero sized shapes.
		if Scatter.has_collision(kind):
			var size := Scatter.collision_size(kind, 1.0)
			check(size.x > 0.0, "le type %d collisionne mais son rayon est nul" % kind)
			check(size.y > 0.0, "le type %d collisionne mais sa hauteur est nulle" % kind)
	# Wheat and grass tufts are the two mass produced kinds: they must be
	# batched, or a field of wheat becomes ten thousand nodes.
	check(Scatter.is_batched(Scatter.P_WHEAT), "le ble doit etre instancie en MultiMesh")
	check(Scatter.is_batched(Scatter.P_GRASS_TUFT), "les touffes d'herbe doivent etre batchees")
	check(not Scatter.has_collision(Scatter.P_WHEAT), "le ble ne doit pas bloquer le joueur")
	check(not Scatter.has_collision(Scatter.P_GRASS_TUFT), "l'herbe ne doit pas bloquer le joueur")
	check(Scatter.has_collision(Scatter.P_TREE_OAK), "un chene doit arreter le joueur")
	done()


func test_collision_size_scales_with_the_prop() -> void:
	var small := Scatter.collision_size(Scatter.P_TREE_OAK, 0.5)
	var large := Scatter.collision_size(Scatter.P_TREE_OAK, 2.0)
	check(large.x > small.x, "un gros arbre doit avoir un tronc plus large")
	check(large.y > small.y, "un gros arbre doit etre plus haut")
	done()


## Regression guard for the bug that made every tree in Normandy a clone.
##
## The tile hash carries 31 bits, and callers draw several independent values out
## of it by shifting (`_rand01(h >> 13)`, `_rand01(h >> 17)`, ...). While `_rand01`
## masked the low 24 bits instead of re-mixing, anything past a shift of 7 was
## capped near zero: rotations collapsed to a fraction of a degree, scales pinned
## to the bottom of their range, and every instance of a family received the exact
## same tint. Nothing crashed, no test failed, and the whole world grew aligned
## like a printed pattern. Variety is a property worth asserting.
func test_props_actually_vary_within_a_family() -> void:
	var hf := _field()
	var by_kind := {}
	for tx in range(-8, 9, 2):
		for tz in range(-8, 9, 2):
			for instance in Scatter.for_tile(hf, tx, tz):
				if not by_kind.has(instance.kind):
					by_kind[instance.kind] = []
				var bucket: Array = by_kind[instance.kind]
				if bucket.size() < 400:
					bucket.append(instance)

	var families_checked := 0
	for kind in by_kind:
		var bucket: Array = by_kind[kind]
		if bucket.size() < 40:
			continue
		families_checked += 1

		var lowest_rotation := INF
		var highest_rotation := -INF
		var lowest_scale := INF
		var highest_scale := -INF
		var tints := {}
		for entry in bucket:
			lowest_rotation = minf(lowest_rotation, entry.rotation)
			highest_rotation = maxf(highest_rotation, entry.rotation)
			lowest_scale = minf(lowest_scale, entry.scale)
			highest_scale = maxf(highest_scale, entry.scale)
			# Bucket the tint coarsely: exact float equality would pass on two
			# values that differ in the seventh decimal and look identical.
			tints["%d_%d_%d" % [int(entry.tint.r * 40.0), int(entry.tint.g * 40.0),
					int(entry.tint.b * 40.0)]] = true

		# Half a turn of spread over forty or more instances. The broken version
		# produced less than a hundredth of a radian.
		check(highest_rotation - lowest_rotation > 0.5,
				"le type %d ne tourne quasiment pas (%f rad d'ecart sur %d instances)"
						% [kind, highest_rotation - lowest_rotation, bucket.size()])
		check(highest_scale - lowest_scale > 0.02,
				"le type %d a une taille figee (%f d'ecart)" % [kind, highest_scale - lowest_scale])
		check(tints.size() >= 3,
				"le type %d n'a que %d teinte(s) distincte(s)" % [kind, tints.size()])

	check(families_checked >= 3,
			"seulement %d famille(s) assez peuplee(s) pour juger la variete" % families_checked)
	done()


func test_forest_is_denser_than_a_wheat_field_in_trees() -> void:
	# A weak but meaningful sanity check on the biome rules: somewhere in the
	# world, trees must actually cluster.
	var hf := _field()
	var best_trees := 0
	for tx in range(-12, 13, 2):
		for tz in range(-12, 13, 2):
			var trees := 0
			for instance in Scatter.for_tile(hf, tx, tz):
				if instance.kind == Scatter.P_TREE_OAK or instance.kind == Scatter.P_TREE_PINE:
					trees += 1
			best_trees = maxi(best_trees, trees)
	check(best_trees >= 8,
			"la tuile la plus boisee du monde ne contient que %d arbres" % best_trees)
	done()
