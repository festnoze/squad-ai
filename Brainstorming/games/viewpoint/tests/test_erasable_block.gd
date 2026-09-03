extends ViewTest
## The box-minus-box decomposition that powers partial erasure (carving).


func suite_name() -> String:
	return "erasable_block"


func _volume(pieces: Array) -> float:
	var total := 0.0
	for piece in pieces:
		var s: Vector3 = piece["size"]
		total += s.x * s.y * s.z
	return total


func test_create_keeps_identity() -> void:
	# Fragments are rebuilt with the same color, emissive and extra groups, so
	# a carved platform stays a platform and a lavender block stays lavender.
	var plain := ErasableBlock.create(Vector3(2, 1, 3), "wood")
	eq(plain.block_size, Vector3(2, 1, 3), "taille memorisee")
	eq(plain.color_key, "wood", "couleur memorisee")
	near(plain.block_emissive, 0.0, 0.001, "pas d'emission par defaut")
	eq(plain.block_extra_groups.size(), 0, "aucun groupe supplementaire par defaut")
	check(plain.show_mesh, "un bloc est visible par defaut")
	plain.free()

	var marked := ErasableBlock.create(Vector3(1, 1, 1), "erasable", 0.25, PackedStringArray(["erasable"]))
	near(marked.block_emissive, 0.25, 0.001, "emission lavande memorisee")
	eq(marked.block_extra_groups, PackedStringArray(["erasable"]), "groupe marqueur memorise")
	marked.free()

	var platform := ErasableBlock.create(Vector3(10, 1, 10), "platform", 0.0, PackedStringArray(["platform"]))
	eq(platform.block_extra_groups, PackedStringArray(["platform"]), "la plateforme garde son groupe")
	platform.free()
	done()


func test_center_hole_thin_wall() -> void:
	# A door-sized hole through a thin wall, full height: only the two
	# flanks survive.
	var size := Vector3(10, 3.5, 0.6)
	var pieces := ErasableBlock.decompose(size, Vector3(-2, -1.75, -0.3), Vector3(2, 1.75, 0.3))
	eq(pieces.size(), 2, "trou pleine hauteur : deux flancs")
	near(_volume(pieces), (10.0 - 4.0) * 3.5 * 0.6, 0.001, "volume conserve hors du trou")
	for piece in pieces:
		near(absf(piece["center"].x), 3.5, 0.001, "flancs centres de part et d'autre")
		near(piece["size"].x, 3.0, 0.001, "flancs de la bonne largeur")
	done()


func test_corner_hole() -> void:
	# A hole in one corner of a cube: three slabs remain, volumes add up.
	var size := Vector3(4, 4, 4)
	var pieces := ErasableBlock.decompose(size, Vector3(0, 0, 0), Vector3(2, 2, 2))
	eq(pieces.size(), 3, "trou en coin : trois morceaux")
	near(_volume(pieces), 64.0 - 8.0, 0.001, "volume total = boite moins trou")
	done()


func test_inner_hole() -> void:
	# A hole strictly inside the volume: all six slabs.
	var size := Vector3(4, 4, 4)
	var pieces := ErasableBlock.decompose(size, Vector3(-1, -1, -1), Vector3(1, 1, 1))
	eq(pieces.size(), 6, "trou interieur : six morceaux")
	near(_volume(pieces), 64.0 - 8.0, 0.001, "volume total = boite moins trou")
	done()


func test_hole_swallows_box() -> void:
	var size := Vector3(1.2, 1.2, 1.2)
	var pieces := ErasableBlock.decompose(size, Vector3(-3, -3, -3), Vector3(3, 3, 3))
	eq(pieces.size(), 0, "trou plus grand que la boite : plus rien")
	done()


func test_hole_outside() -> void:
	# A hole entirely off the box clamps to a zero-thickness slice on the
	# boundary: the whole box survives as one piece.
	var size := Vector3(2, 2, 2)
	var pieces := ErasableBlock.decompose(size, Vector3(5, -1, -1), Vector3(7, 1, 1))
	eq(pieces.size(), 1, "trou hors de la boite : un seul morceau")
	near(_volume(pieces), 8.0, 0.001, "la boite entiere subsiste")
	done()


func test_slivers_dropped() -> void:
	# Remainders thinner than MIN_FRAGMENT are dropped instead of leaving
	# unplayable films floating in the level.
	var size := Vector3(4, 4, 4)
	var pieces := ErasableBlock.decompose(size, Vector3(-1.98, -2, -2), Vector3(2, 2, 2))
	eq(pieces.size(), 0, "pellicule de 2 cm : aucun fragment")
	done()
