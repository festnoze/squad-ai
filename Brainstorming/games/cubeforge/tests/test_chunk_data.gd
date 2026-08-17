extends TestCase
## Chunk storage: index layout, the column_top bookkeeping the mesher relies on,
## and the run length encoding used for saves.


func suite_name() -> String:
	return "chunk_data"


func test_index_layout() -> void:
	eq(ChunkData.VOLUME, 16 * 96 * 16, "volume du chunk")
	eq(ChunkData.local_index(0, 0, 0), 0, "origine")
	eq(ChunkData.local_index(0, 1, 0), ChunkData.STRIDE_Y, "pas en Y")
	eq(ChunkData.local_index(0, 0, 1), ChunkData.STRIDE_Z, "pas en Z")
	eq(ChunkData.local_index(1, 0, 0), ChunkData.STRIDE_X, "pas en X")
	eq(ChunkData.local_index(15, 95, 15), ChunkData.VOLUME - 1, "derniere cellule")

	# Every cell must map to a distinct index, which is the whole point of the
	# stride arithmetic the mesher uses instead of calling local_index.
	var seen := {}
	for x in ChunkData.SIZE_X:
		for y in ChunkData.SIZE_Y:
			for z in ChunkData.SIZE_Z:
				var idx := ChunkData.local_index(x, y, z)
				check(not seen.has(idx), "index duplique en (%d, %d, %d)" % [x, y, z])
				seen[idx] = true
	eq(seen.size(), ChunkData.VOLUME, "toutes les cellules doivent etre atteintes")
	done()


func test_bounds_are_forgiving_on_read() -> void:
	var data := ChunkData.new(3, -2)
	eq(data.cx, 3, "coordonnee cx")
	eq(data.cz, -2, "coordonnee cz")
	eq(data.get_local(-1, 0, 0), Blocks.AIR, "lecture hors bornes renvoie de l'air")
	eq(data.get_local(0, -1, 0), Blocks.AIR, "lecture sous le monde renvoie de l'air")
	eq(data.get_local(0, ChunkData.SIZE_Y, 0), Blocks.AIR, "lecture au-dessus du monde renvoie de l'air")
	eq(data.get_local(16, 0, 0), Blocks.AIR, "lecture a droite du chunk renvoie de l'air")
	check(not data.set_local(-1, 0, 0, Blocks.STONE), "ecriture hors bornes refusee")
	check(not data.set_local(0, 200, 0, Blocks.STONE), "ecriture trop haute refusee")
	done()


func test_solid_count_tracks_writes() -> void:
	var data := ChunkData.new()
	eq(data.solid_count, 0, "un chunk neuf est vide")
	check(data.is_empty(), "un chunk neuf se declare vide")

	data.set_local(2, 10, 3, Blocks.STONE)
	eq(data.solid_count, 1, "un bloc pose")
	data.set_local(2, 10, 3, Blocks.DIRT)
	eq(data.solid_count, 1, "remplacer un bloc ne change pas le compte")
	data.set_local(2, 10, 3, Blocks.AIR)
	eq(data.solid_count, 0, "retirer le bloc remet le compte a zero")
	check(data.is_empty(), "le chunk redevient vide")
	done()


func test_column_top_follows_the_peak() -> void:
	var data := ChunkData.new()
	eq(data.top_of(4, 5), -1, "colonne vide")

	data.set_local(4, 10, 5, Blocks.STONE)
	eq(data.top_of(4, 5), 10, "sommet apres une pose")

	data.set_local(4, 20, 5, Blocks.STONE)
	eq(data.top_of(4, 5), 20, "le sommet monte")

	data.set_local(4, 15, 5, Blocks.STONE)
	eq(data.top_of(4, 5), 20, "poser plus bas ne change pas le sommet")

	# Removing the peak has to walk back down to the next solid cell, not just
	# decrement, otherwise the sky light in the mesher goes wrong.
	data.set_local(4, 20, 5, Blocks.AIR)
	eq(data.top_of(4, 5), 15, "retirer le sommet revele le bloc suivant")
	data.set_local(4, 15, 5, Blocks.AIR)
	eq(data.top_of(4, 5), 10, "puis celui d'en dessous")
	data.set_local(4, 10, 5, Blocks.AIR)
	eq(data.top_of(4, 5), -1, "la colonne redevient vide")

	eq(data.top_of(-1, 0), -1, "sommet hors bornes")
	eq(data.top_of(0, 99), -1, "sommet hors bornes en Z")
	done()


func test_fill_column_clamps() -> void:
	var data := ChunkData.new()
	data.fill_column(1, 1, -20, 5, Blocks.STONE)
	eq(data.get_local(1, 0, 1), Blocks.STONE, "le bas est rempli malgre une borne negative")
	eq(data.get_local(1, 5, 1), Blocks.STONE, "le haut demande est rempli")
	eq(data.get_local(1, 6, 1), Blocks.AIR, "rien au-dela")

	data.fill_column(2, 2, 90, 500, Blocks.DIRT)
	eq(data.get_local(2, 95, 2), Blocks.DIRT, "le plafond est rempli malgre une borne trop haute")

	# An inverted range is a no-op rather than an error, which lets the terrain
	# generator pass computed bounds without guarding every call.
	data.fill_column(3, 3, 10, 5, Blocks.STONE)
	eq(data.get_local(3, 7, 3), Blocks.AIR, "un intervalle inverse n'ecrit rien")
	done()


func test_recompute_tops_rebuilds_after_raw_writes() -> void:
	var data := ChunkData.new()
	# set_local_raw deliberately skips the bookkeeping, so the state is stale
	# until recompute_tops runs. This is exactly what the generator does.
	data.set_local_raw(0, 30, 0, Blocks.STONE)
	data.set_local_raw(0, 31, 0, Blocks.STONE)
	eq(data.solid_count, 0, "les ecritures brutes ne mettent pas le compte a jour")
	eq(data.top_of(0, 0), -1, "les ecritures brutes ne mettent pas le sommet a jour")

	data.recompute_tops()
	eq(data.solid_count, 2, "recompute_tops retrouve le compte")
	eq(data.top_of(0, 0), 31, "recompute_tops retrouve le sommet")
	done()


func test_serialisation_round_trip() -> void:
	var data := ChunkData.new(7, 9)
	for x in ChunkData.SIZE_X:
		for z in ChunkData.SIZE_Z:
			data.fill_column(x, z, 0, 40 + (x + z) % 7, Blocks.STONE)
			data.set_local_raw(x, 41 + (x + z) % 7, z, Blocks.GRASS)
	data.set_local_raw(3, 60, 4, Blocks.DIAMOND_ORE)
	data.recompute_tops()

	var payload := data.serialize()
	check(payload.size() > 0, "la serialisation produit des octets")
	check(payload.size() < ChunkData.VOLUME,
		"le RLE doit compresser un chunk regulier (obtenu %d octets)" % payload.size())

	var restored := ChunkData.new(7, 9)
	check(restored.deserialize(payload), "la deserialisation reussit")
	eq(restored.voxels, data.voxels, "les voxels sont identiques apres aller-retour")
	eq(restored.solid_count, data.solid_count, "le compte est reconstruit")
	eq(restored.column_top, data.column_top, "les sommets sont reconstruits")
	done()


func test_serialisation_handles_an_empty_chunk() -> void:
	var data := ChunkData.new()
	var payload := data.serialize()
	var restored := ChunkData.new()
	restored.set_local(0, 0, 0, Blocks.STONE)
	check(restored.deserialize(payload), "un chunk vide se deserialise")
	eq(restored.solid_count, 0, "le chunk redevient vide")
	eq(restored.top_of(0, 0), -1, "aucun sommet ne subsiste")
	done()


func test_deserialise_rejects_garbage() -> void:
	var data := ChunkData.new()
	data.set_local(1, 1, 1, Blocks.STONE)
	var before := data.voxels

	check(not data.deserialize(PackedByteArray([1, 2])), "une longueur non multiple de 3 est rejetee")
	check(not data.deserialize(PackedByteArray([1, 0, 0])), "une serie de longueur nulle est rejetee")

	# A payload that decodes to fewer cells than the chunk holds is truncated
	# and must not be accepted half applied.
	check(not data.deserialize(PackedByteArray([Blocks.STONE, 10, 0])), "un contenu trop court est rejete")
	eq(data.voxels, before, "un rejet laisse le chunk intact")
	done()
