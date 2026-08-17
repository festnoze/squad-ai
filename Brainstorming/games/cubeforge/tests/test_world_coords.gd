extends TestCase
## World to chunk coordinate conversion.
##
## This is a two line function that is nevertheless worth pinning down, because
## GDScript integer division truncates toward zero: a naive wx / 16 folds x = -1
## and x = 0 into the same chunk, which produces a seam of duplicated terrain
## along the west and north sides of the origin that is maddening to diagnose
## later.


func suite_name() -> String:
	return "world_coords"


func test_chunk_of_floors_toward_negative() -> void:
	eq(VoxelWorld.chunk_of(0), 0, "x = 0")
	eq(VoxelWorld.chunk_of(1), 0, "x = 1")
	eq(VoxelWorld.chunk_of(15), 0, "derniere colonne du chunk 0")
	eq(VoxelWorld.chunk_of(16), 1, "premiere colonne du chunk 1")
	eq(VoxelWorld.chunk_of(31), 1, "derniere colonne du chunk 1")
	eq(VoxelWorld.chunk_of(32), 2, "premiere colonne du chunk 2")

	eq(VoxelWorld.chunk_of(-1), -1, "x = -1 appartient au chunk -1")
	eq(VoxelWorld.chunk_of(-16), -1, "premiere colonne du chunk -1")
	eq(VoxelWorld.chunk_of(-17), -2, "derniere colonne du chunk -2")
	eq(VoxelWorld.chunk_of(-32), -2, "premiere colonne du chunk -2")
	eq(VoxelWorld.chunk_of(-33), -3, "derniere colonne du chunk -3")
	done()


func test_local_of_is_always_positive() -> void:
	eq(VoxelWorld.local_of(0), 0, "x = 0")
	eq(VoxelWorld.local_of(15), 15, "x = 15")
	eq(VoxelWorld.local_of(16), 0, "x = 16 revient a 0")
	eq(VoxelWorld.local_of(-1), 15, "x = -1 est la derniere colonne")
	eq(VoxelWorld.local_of(-16), 0, "x = -16 est la premiere colonne")
	eq(VoxelWorld.local_of(-17), 15, "x = -17 est la derniere colonne du chunk precedent")

	for w in range(-64, 65):
		between(float(VoxelWorld.local_of(w)), 0.0, 15.0, "local_of(%d) doit rester dans 0..15" % w)
	done()


func test_conversion_is_a_bijection() -> void:
	# Reassembling the chunk index and the local offset must give the original
	# coordinate back for every value, negatives included.
	for w in range(-200, 201):
		var reassembled: int = VoxelWorld.chunk_of(w) * ChunkData.SIZE_X + VoxelWorld.local_of(w)
		eq(reassembled, w, "chunk_of et local_of doivent recomposer %d" % w)
	done()
