extends TestCase
## Pure tree-shape helpers of GrowthManager (src/entities/growth_manager.gd).
##
## Only the static functions run here: no scene tree, no world, no signals.
## Every RandomNumberGenerator is seeded by hand, so the expectations are exact
## and the suite can never flake.
##
## The script is preloaded by path rather than through its global class name,
## so the suite compiles even when the global class cache has not been rebuilt
## since the class was added.

const GrowthManagerScript := preload("res://src/entities/growth_manager.gd")


func suite_name() -> String:
	return "growth"


func _seeded(seed_value: int) -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value
	return rng


func test_trunk_height_range() -> void:
	var seen: Dictionary = {}
	for i in 64:
		var h: int = GrowthManagerScript.trunk_height_from(_seeded(i))
		check(h == 4 or h == 5, "hauteur de tronc hors de {4, 5}: %d" % h)
		seen[h] = true
	check(seen.has(4) and seen.has(5),
			"les deux hauteurs de tronc doivent apparaitre sur 64 graines")
	done()


func test_canopy_deterministic_for_fixed_seed() -> void:
	for trunk_height: int in [4, 5]:
		var a: Array[Vector3i] = GrowthManagerScript.canopy_offsets(trunk_height, _seeded(1234))
		var b: Array[Vector3i] = GrowthManagerScript.canopy_offsets(trunk_height, _seeded(1234))
		eq(a.size(), b.size(), "meme graine, meme nombre de feuilles")
		for i in a.size():
			eq(a[i], b[i], "meme graine, meme offset a l'index %d" % i)
	done()


func test_canopy_layout_and_bounds() -> void:
	for trunk_height: int in [4, 5]:
		for seed_value: int in [7, 91, 5000]:
			var offsets: Array[Vector3i] = GrowthManagerScript.canopy_offsets(
					trunk_height, _seeded(seed_value))
			var top := trunk_height - 1
			var unique: Dictionary = {}
			var lower_corners := 0
			var upper_corners := 0
			var top_cross := 0
			var caps := 0
			for offset in offsets:
				check(not unique.has(offset), "offset duplique %s" % str(offset))
				unique[offset] = true
				between(float(offset.x), -1.0, 1.0, "offset x hors bornes: %s" % str(offset))
				between(float(offset.z), -1.0, 1.0, "offset z hors bornes: %s" % str(offset))
				between(float(offset.y), float(top - 2), float(trunk_height),
						"offset y hors bornes: %s" % str(offset))
				check(not (offset.x == 0 and offset.z == 0 and offset.y <= top),
						"feuille sur une cellule de tronc: %s" % str(offset))
				var corner := absi(offset.x) == 1 and absi(offset.z) == 1
				if offset.y == top - 2 and corner:
					lower_corners += 1
				elif offset.y == top - 1 and corner:
					upper_corners += 1
				elif offset.y == top:
					top_cross += 1
					check(not corner, "la couche du sommet ne doit pas avoir de coin")
				elif offset.y == trunk_height:
					caps += 1
					eq(offset, Vector3i(0, trunk_height, 0),
							"la feuille de coiffe doit etre centree sur le tronc")
			eq(lower_corners, 4, "la couche basse garde ses 4 coins")
			between(float(upper_corners), 0.0, 4.0, "coins de la couche haute dans 0..4")
			eq(top_cross, 4, "la croix du sommet compte 4 feuilles")
			eq(caps, 1, "une seule feuille de coiffe")
			between(float(offsets.size()), 17.0, 21.0,
					"nombre total de feuilles dans 17..21")
	done()


func test_upper_corner_trim_varies_with_seed() -> void:
	var corner_counts: Dictionary = {}
	for seed_value in 64:
		var offsets: Array[Vector3i] = GrowthManagerScript.canopy_offsets(5, _seeded(seed_value))
		var corners := 0
		for offset in offsets:
			if offset.y == 3 and absi(offset.x) == 1 and absi(offset.z) == 1:
				corners += 1
		corner_counts[corners] = true
	check(corner_counts.size() >= 2,
			"le rognage des coins doit varier d'une graine a l'autre")
	done()
