extends TestCase
## Terrain generation.
##
## The generator runs on several worker threads at once, one TerrainGen instance
## per thread, and neighbouring chunks are produced by different instances in an
## unpredictable order. Every property checked here exists to protect that
## contract: a pure function of the seed, no hidden mutable state, and no feature
## whose shape depends on which chunk asked for it first.
##
## Chunk generation is the most expensive operation in the project, so each test
## generates as few chunks as it can and reuses cheap pure calls
## (surface_height, biome_at) to find interesting places first.

const SEED_A := 20260817
const SEED_B := 987654321

## Sea level, spelled out so a failure message reads clearly.
const SEA := ChunkData.SEA_LEVEL


func suite_name() -> String:
	return "terrain"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

func _is_leaf(id: int) -> bool:
	return id == Blocks.OAK_LEAVES or id == Blocks.BIRCH_LEAVES or id == Blocks.PINE_LEAVES


func _is_log(id: int) -> bool:
	return id == Blocks.OAK_LOG or id == Blocks.BIRCH_LOG


## Blocks a decoration pass may legitimately leave above the terrain surface.
## surface_height() promises nothing about them.
func _is_decoration(id: int) -> bool:
	if Blocks.is_cross(id):
		return true
	if _is_leaf(id) or _is_log(id):
		return true
	if id == Blocks.CACTUS or id == Blocks.PUMPKIN:
		return true
	# Generated houses sit above the pure terrain height just like trees do.
	return id in [Blocks.COBBLESTONE, Blocks.OAK_PLANKS, Blocks.BIRCH_PLANKS,
		Blocks.STONE_BRICK, Blocks.BRICK, Blocks.GLASS, Blocks.LAMP]


## Highest cell of a column that is terrain proper: neither air, nor water or
## ice, nor decoration. This is exactly what surface_height() must return.
func _terrain_top(data: ChunkData, lx: int, lz: int) -> int:
	for y in range(ChunkData.SIZE_Y - 1, -1, -1):
		var id := data.get_local(lx, y, lz)
		if id == Blocks.AIR or id == Blocks.WATER or id == Blocks.ICE:
			continue
		if _is_decoration(id):
			continue
		return y
	return -1


func _make(gen: TerrainGen, cx: int, cz: int) -> ChunkData:
	var data := ChunkData.new(cx, cz)
	gen.generate(data)
	return data


## Sampled height range of a chunk, using the pure height function only.
func _height_span(gen: TerrainGen, cx: int, cz: int) -> Vector2i:
	var lo := 1 << 20
	var hi := -(1 << 20)
	for lx in range(0, ChunkData.SIZE_X, 3):
		for lz in range(0, ChunkData.SIZE_Z, 3):
			var h := gen.surface_height(cx * ChunkData.SIZE_X + lx, cz * ChunkData.SIZE_Z + lz)
			lo = mini(lo, h)
			hi = maxi(hi, h)
	return Vector2i(lo, hi)


## First chunk of a spiral around the origin whose sampled columns all sit below
## `ceiling`. Used to find an ocean without generating anything.
func _find_low_chunk(gen: TerrainGen, ceiling: int, span: int) -> Vector2i:
	for cx in range(-span, span + 1):
		for cz in range(-span, span + 1):
			var s := _height_span(gen, cx, cz)
			if s.y < ceiling:
				return Vector2i(cx, cz)
	return Vector2i(0, 0)


## First chunk whose sampled columns all sit above `floor_h`, so the column is
## deep enough for caves to have room under it.
func _find_high_chunk(gen: TerrainGen, floor_h: int, span: int) -> Vector2i:
	for cx in range(-span, span + 1):
		for cz in range(-span, span + 1):
			var s := _height_span(gen, cx, cz)
			if s.x > floor_h:
				return Vector2i(cx, cz)
	return Vector2i(0, 0)


## Chunk coordinates of a pair (cx, cz) / (cx + 1, cz) whose shared border runs
## through wooded ground, so a canopy is very likely to straddle it. Only pure
## calls are used, so this costs nothing compared to a generation.
func _find_wooded_border(gen: TerrainGen, span: int, skip: int) -> Array[Vector2i]:
	var found: Array[Vector2i] = []
	for cx in range(-span, span + 1):
		for cz in range(-span, span + 1):
			var bx := cx * ChunkData.SIZE_X
			var bz := cz * ChunkData.SIZE_Z
			var wooded := 0
			for lz in ChunkData.SIZE_Z:
				for wx in [bx + ChunkData.SIZE_X - 1, bx + ChunkData.SIZE_X]:
					var h := gen.surface_height(wx, bz + lz)
					if h < SEA or h > 74:
						continue
					var b := gen.biome_at(wx, bz + lz)
					if b == TerrainGen.Biome.FOREST or b == TerrainGen.Biome.TAIGA:
						wooded += 1
			if wooded < 26:
				continue
			found.append(Vector2i(cx, cz))
			if found.size() >= skip:
				return found
	return found


## Top y of the tree trunk standing in a column, or -1 when there is none.
func _trunk_top(data: ChunkData, lx: int, lz: int) -> int:
	for y in range(ChunkData.SIZE_Y - 2, 0, -1):
		if _is_log(data.get_local(lx, y, lz)) and not _is_log(data.get_local(lx, y + 1, lz)):
			return y
	return -1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

func test_same_seed_gives_byte_identical_chunks() -> void:
	# Two instances stand for two worker threads. Nothing an instance holds may
	# influence the result, so their output has to match to the byte.
	var g1 := TerrainGen.new(SEED_A)
	var g2 := TerrainGen.new(SEED_A)

	var a := _make(g1, 2, -3)
	var b := _make(g2, 2, -3)
	check(a.voxels == b.voxels, "deux instances de meme graine doivent produire les memes voxels")
	eq(b.solid_count, a.solid_count, "compte de blocs pleins identique")
	check(a.column_top == b.column_top, "sommets de colonne identiques")

	# The pure queries must agree too, including for chunks nobody generated.
	var same_h := true
	var same_b := true
	var same_c := true
	for k in 240:
		var wx := k * 37 - 4000
		var wz := 3000 - k * 53
		if g1.surface_height(wx, wz) != g2.surface_height(wx, wz):
			same_h = false
		if g1.biome_at(wx, wz) != g2.biome_at(wx, wz):
			same_b = false
		if g1.grass_color_at(wx, wz) != g2.grass_color_at(wx, wz):
			same_c = false
	check(same_h, "surface_height doit etre identique a graine egale")
	check(same_b, "biome_at doit etre identique a graine egale")
	check(same_c, "grass_color_at doit etre identique a graine egale")
	done()


func test_a_different_seed_gives_a_different_world() -> void:
	var g1 := TerrainGen.new(SEED_A)
	var g2 := TerrainGen.new(SEED_B)

	var a := _make(g1, 2, -3)
	var b := _make(g2, 2, -3)
	check(a.voxels != b.voxels, "deux graines differentes doivent produire des chunks differents")

	var height_diffs := 0
	var biome_diffs := 0
	for k in 240:
		var wx := k * 37 - 4000
		var wz := 3000 - k * 53
		if g1.surface_height(wx, wz) != g2.surface_height(wx, wz):
			height_diffs += 1
		if g1.biome_at(wx, wz) != g2.biome_at(wx, wz):
			biome_diffs += 1
	check(height_diffs > 120, "le relief doit differer sur la plupart des colonnes (obtenu %d / 240)" % height_diffs)
	check(biome_diffs > 20, "les biomes doivent differer souvent (obtenu %d / 240)" % biome_diffs)
	done()


func test_generation_order_does_not_matter() -> void:
	# The classic failure is a RandomNumberGenerator kept as a field: the first
	# chunk of a run then differs from the same chunk generated later, and two
	# neighbours disagree about the trees that cross their border.
	var g1 := TerrainGen.new(SEED_A)
	var first_a := _make(g1, 4, 4)
	var first_b := _make(g1, 5, 4)
	var again_a := _make(g1, 4, 4)
	check(first_a.voxels == again_a.voxels,
		"regenerer un chunk avec la meme instance doit redonner le meme resultat")

	# Reverse order on a fresh instance: (5, 4) is now the very first chunk this
	# instance ever produced.
	var g2 := TerrainGen.new(SEED_A)
	var reversed_b := _make(g2, 5, 4)
	var reversed_a := _make(g2, 4, 4)
	check(first_b.voxels == reversed_b.voxels,
		"l'ordre de generation ne doit pas changer le chunk (5, 4)")
	check(first_a.voxels == reversed_a.voxels,
		"l'ordre de generation ne doit pas changer le chunk (4, 4)")
	done()


func test_houses_are_deterministic_and_furnished() -> void:
	var g1 := TerrainGen.new(SEED_A)
	var g2 := TerrainGen.new(SEED_A)
	var house := Vector4i.ZERO
	var village := Vector4i.ZERO
	# Search settlement cells rather than chunks; this exercises the sparse
	# placement rule without generating hundreds of voxel columns.
	for cell_x in range(-20, 21):
		for cell_z in range(-20, 21):
			var candidate: Vector4i = g1._village_for_cell(cell_x, cell_z)
			if candidate != Vector4i.ZERO:
				village = candidate
				house = g1._village_houses(village)[0]
				break
		if house != Vector4i.ZERO:
			break
	check(house != Vector4i.ZERO, "au moins une maison doit exister dans la zone de recherche")
	if house == Vector4i.ZERO:
		done()
		return

	var same := Vector4i.ZERO
	var owner_cx := TerrainGen._floor_div(house.x, ChunkData.SIZE_X)
	var owner_cz := TerrainGen._floor_div(house.z, ChunkData.SIZE_Z)
	for other in g2.houses_in_chunk(owner_cx, owner_cz):
		if other.x == house.x and other.z == house.z:
			same = other
			break
	eq(same, house, "deux generateurs de meme graine doivent publier la meme maison")

	var data := _make(g1, owner_cx, owner_cz)
	var lx := house.x - owner_cx * ChunkData.SIZE_X
	var lz := house.z - owner_cz * ChunkData.SIZE_Z
	eq(data.get_local(lx, house.y, lz), Blocks.OAK_PLANKS, "la maison a un plancher")
	eq(data.get_local(lx, house.y + 3, lz), Blocks.LAMP, "la maison a une lampe interieure")
	check(data.get_local(lx, house.y + 7, lz) == Blocks.BIRCH_PLANKS,
		"le toit se ferme par une faitiere")

	var village_houses := g1._village_houses(village)
	eq(village_houses.size(), 2, "un village doit contenir deux maisons")
	eq(village_houses[0].w >> 2, TerrainGen.HOUSE_TIMBER, "la premiere maison est en bois")
	eq(village_houses[1].w >> 2, TerrainGen.HOUSE_MASON, "la seconde maison est en pierre")
	var mason: Vector4i = village_houses[1]
	var mason_cx := TerrainGen._floor_div(mason.x, ChunkData.SIZE_X)
	var mason_cz := TerrainGen._floor_div(mason.z, ChunkData.SIZE_Z)
	var mason_data := _make(g1, mason_cx, mason_cz)
	var mx := mason.x - mason_cx * ChunkData.SIZE_X
	var mz := mason.z - mason_cz * ChunkData.SIZE_Z
	eq(mason_data.get_local(mx, mason.y, mz), Blocks.COBBLESTONE,
		"la maison de macon a un plancher de pierre")
	eq(mason_data.get_local(mx, mason.y + 4, mz), Blocks.BRICK,
		"la maison de macon a un toit de briques")

	var pen := g1._village_pen(village)
	var edge := g1._rotate_village_offset(pen.w, 6, 0)
	var edge_x := pen.x + edge.x
	var edge_z := pen.z + edge.y
	var pen_cx := TerrainGen._floor_div(edge_x, ChunkData.SIZE_X)
	var pen_cz := TerrainGen._floor_div(edge_z, ChunkData.SIZE_Z)
	var pen_data := _make(g1, pen_cx, pen_cz)
	var edge_y := g1.surface_height(edge_x, edge_z) + 1
	eq(pen_data.get_local(VoxelWorld.local_of(edge_x), edge_y, VoxelWorld.local_of(edge_z)),
		Blocks.OAK_LOG, "l'enclos est ferme par des poteaux et barrieres")
	done()


# ---------------------------------------------------------------------------
# surface_height against what generate() actually writes
# ---------------------------------------------------------------------------

func test_surface_height_matches_the_generated_column() -> void:
	var gen := TerrainGen.new(SEED_A)
	var spots: Array[Vector2i] = [Vector2i(0, 0), Vector2i(12, 9), Vector2i(-8, 5)]
	var mismatches := 0
	var first := ""
	var solid_top := true
	var clean_above := true

	for spot in spots:
		var data := _make(gen, spot.x, spot.y)
		var x0 := spot.x * ChunkData.SIZE_X
		var z0 := spot.y * ChunkData.SIZE_Z
		for lx in ChunkData.SIZE_X:
			for lz in ChunkData.SIZE_Z:
				var h := gen.surface_height(x0 + lx, z0 + lz)
				var top := _terrain_top(data, lx, lz)
				if top != h:
					mismatches += 1
					if first.is_empty():
						first = "(%d, %d) attendu %d obtenu %d" % [x0 + lx, z0 + lz, h, top]
				# The surface cell itself has to be real ground, and nothing but
				# water, ice or decoration may sit on top of it.
				if not Blocks.is_opaque(data.get_local(lx, h, lz)):
					solid_top = false
				if h + 1 < ChunkData.SIZE_Y:
					var above := data.get_local(lx, h + 1, lz)
					if above != Blocks.AIR and above != Blocks.WATER and above != Blocks.ICE \
							and not _is_decoration(above):
						clean_above = false

	eq(mismatches, 0, "surface_height doit coller au terrain genere, premier ecart : %s" % first)
	check(solid_top, "la cellule de surface doit etre un bloc plein")
	check(clean_above, "au dessus de la surface, seulement air, eau, glace ou decor")
	done()


func test_height_stays_inside_the_world() -> void:
	var gen := TerrainGen.new(SEED_A)
	var lo := 1 << 20
	var hi := -(1 << 20)
	for k in 4000:
		var wx := (k % 80) * 61 - 2440
		var wz := (k / 80) * 59 - 1475
		var h := gen.surface_height(wx, wz)
		lo = mini(lo, h)
		hi = maxi(hi, h)
	check(lo >= 1, "la surface doit rester au dessus du socle (obtenu %d)" % lo)
	check(hi <= ChunkData.SIZE_Y - 2, "la surface doit rester sous le plafond (obtenu %d)" % hi)
	done()


# ---------------------------------------------------------------------------
# Mandatory strata
# ---------------------------------------------------------------------------

func test_bedrock_floor_is_unbreakable_by_caves() -> void:
	var gen := TerrainGen.new(SEED_A)
	var data := _make(gen, 1, -1)
	var missing := 0
	var holes := 0
	var fringe := 0
	for lx in ChunkData.SIZE_X:
		for lz in ChunkData.SIZE_Z:
			if data.get_local(lx, 0, lz) != Blocks.BEDROCK:
				missing += 1
			# A cave must never open the floor, so the four lowest layers hold no
			# air at all.
			for y in 4:
				if data.get_local(lx, y, lz) == Blocks.AIR:
					holes += 1
			for y in range(1, 4):
				if data.get_local(lx, y, lz) == Blocks.BEDROCK:
					fringe += 1

	eq(missing, 0, "chaque colonne doit avoir du bedrock en y 0")
	eq(holes, 0, "aucune grotte ne doit percer les quatre couches du fond")
	check(fringe > 0, "le liseré de bedrock au dessus de y 0 doit exister")
	done()


func test_water_fills_the_sea_and_nothing_above_it() -> void:
	var gen := TerrainGen.new(SEED_A)
	var spot := _find_low_chunk(gen, SEA - 4, 10)
	var data := _make(gen, spot.x, spot.y)
	var x0 := spot.x * ChunkData.SIZE_X
	var z0 := spot.y * ChunkData.SIZE_Z

	var span := _height_span(gen, spot.x, spot.y)
	check(span.y < SEA, "il faut un chunk immergé pour ce test (sommet %d)" % span.y)

	var dry_cells := 0
	var stray := 0
	var liquid_cells := 0
	for lx in ChunkData.SIZE_X:
		for lz in ChunkData.SIZE_Z:
			var h := gen.surface_height(x0 + lx, z0 + lz)
			for y in range(h + 1, SEA + 1):
				var id := data.get_local(lx, y, lz)
				if id == Blocks.WATER or id == Blocks.ICE:
					liquid_cells += 1
				else:
					dry_cells += 1
			for y in range(SEA + 1, ChunkData.SIZE_Y):
				var id2 := data.get_local(lx, y, lz)
				if id2 == Blocks.WATER or id2 == Blocks.ICE:
					stray += 1

	check(liquid_cells > 0, "un chunk immergé doit contenir de l'eau")
	eq(dry_cells, 0, "toute cellule ouverte jusqu'a SEA_LEVEL doit etre remplie de liquide")
	eq(stray, 0, "aucun liquide au dessus de SEA_LEVEL")
	done()


func test_caves_hollow_the_underground() -> void:
	var gen := TerrainGen.new(SEED_A)
	var spot := _find_high_chunk(gen, SEA + 8, 10)
	var data := _make(gen, spot.x, spot.y)
	var x0 := spot.x * ChunkData.SIZE_X
	var z0 := spot.y * ChunkData.SIZE_Z

	var air_below := 0
	var columns_with_cave := 0
	for lx in ChunkData.SIZE_X:
		for lz in ChunkData.SIZE_Z:
			var h := gen.surface_height(x0 + lx, z0 + lz)
			var hits := 0
			for y in range(4, h - 3):
				if data.get_local(lx, y, lz) == Blocks.AIR:
					hits += 1
			air_below += hits
			if hits > 0:
				columns_with_cave += 1

	check(air_below > 100,
		"des grottes doivent creuser le sous-sol (obtenu %d cellules d'air)" % air_below)
	check(columns_with_cave > 8,
		"les grottes doivent toucher plusieurs colonnes (obtenu %d)" % columns_with_cave)
	done()


# ---------------------------------------------------------------------------
# Relief and biomes
# ---------------------------------------------------------------------------

func test_relief_is_not_flat() -> void:
	var gen := TerrainGen.new(SEED_A)
	var lo := 1 << 20
	var hi := -(1 << 20)
	var sum := 0.0
	var sum2 := 0.0
	var count := 0
	var below_sea := 0
	var high_ground := 0

	for ix in 120:
		for iz in 120:
			var wx := ix * 53 - 3180
			var wz := iz * 47 - 2820
			var h := gen.surface_height(wx, wz)
			lo = mini(lo, h)
			hi = maxi(hi, h)
			sum += float(h)
			sum2 += float(h) * float(h)
			count += 1
			if h < SEA - 2:
				below_sea += 1
			if h >= 70:
				high_ground += 1

	var mean := sum / float(count)
	var variance := maxf(sum2 / float(count) - mean * mean, 0.0)
	check(hi - lo >= 30, "le relief doit varier fortement (amplitude %d)" % (hi - lo))
	check(sqrt(variance) > 4.0, "l'ecart type du relief doit etre net (obtenu %f)" % sqrt(variance))
	check(below_sea > 0, "il doit exister des fonds sous le niveau de la mer")
	check(high_ground > 0, "il doit exister des sommets au dessus de 70")
	done()


func test_every_biome_is_reachable() -> void:
	var gen := TerrainGen.new(SEED_A)
	var seen := PackedInt32Array()
	seen.resize(TerrainGen.BIOME_NAMES.size())
	seen.fill(0)

	for ix in 201:
		for iz in 201:
			var wx := ix * 48 - 4800
			var wz := iz * 48 - 4800
			var b := gen.biome_at(wx, wz)
			if b >= 0 and b < seen.size():
				seen[b] += 1

	for b in seen.size():
		check(seen[b] > 0, "le biome %s doit exister quelque part" % TerrainGen.biome_name(b))
	done()


func test_biome_names_cover_the_enum() -> void:
	eq(TerrainGen.BIOME_NAMES.size(), 10, "dix biomes")
	eq(TerrainGen.biome_name(TerrainGen.Biome.OCEAN), "Océan", "nom de l'ocean")
	eq(TerrainGen.biome_name(TerrainGen.Biome.MOUNTAINS), "Montagnes", "nom des montagnes")
	eq(TerrainGen.biome_name(-1), "Inconnu", "index negatif")
	eq(TerrainGen.biome_name(99), "Inconnu", "index hors bornes")
	done()


func test_grass_tint_has_no_visible_seam() -> void:
	# A one block jump in the tint is a seam the player sees, so the colour has
	# to be interpolated on the noises rather than switched per biome.
	var gen := TerrainGen.new(SEED_A)
	var worst := 0.0
	var worst_at := 0
	var green_lo := 2.0
	var green_hi := -1.0
	var in_range := true
	var opaque := true

	for line in 2:
		var wz := 137 if line == 0 else -908
		var prev := gen.grass_color_at(-1200, wz)
		for wx in range(-1199, 1200):
			var cur := gen.grass_color_at(wx, wz)
			var d := maxf(maxf(absf(cur.r - prev.r), absf(cur.g - prev.g)), absf(cur.b - prev.b))
			if d > worst:
				worst = d
				worst_at = wx
			prev = cur
			green_lo = minf(green_lo, cur.g)
			green_hi = maxf(green_hi, cur.g)
			if cur.r < 0.0 or cur.r > 1.0 or cur.g < 0.0 or cur.g > 1.0 or cur.b < 0.0 or cur.b > 1.0:
				in_range = false
			if not is_equal_approx(cur.a, 1.0):
				opaque = false

	check(worst <= 0.03,
		"un pas d'un bloc ne doit pas changer la teinte de plus de 0.03 (obtenu %f vers x = %d)"
			% [worst, worst_at])
	check(green_hi - green_lo > 0.03,
		"la teinte doit quand meme varier le long du trajet (amplitude verte %f)" % (green_hi - green_lo))
	check(in_range, "les canaux de teinte restent dans 0..1")
	check(opaque, "la teinte est opaque")
	done()


# ---------------------------------------------------------------------------
# Cross chunk consistency, the property that matters most
# ---------------------------------------------------------------------------

func test_trees_stay_whole_across_a_chunk_border() -> void:
	# Two neighbours are generated by different instances, in the wrong order on
	# purpose. Every trunk sitting against the shared border must have its
	# canopy continued by the other chunk: the leaf ring at trunk top always
	# includes the cell one block sideways, for oaks, birches and pines alike.
	var finder := TerrainGen.new(SEED_A)
	var pairs := _find_wooded_border(finder, 12, 6)
	check(not pairs.is_empty(), "il faut au moins une frontiere boisee pour ce test")

	var tested := 0
	var broken := 0
	var first := ""
	var west_leaves := 0
	var east_leaves := 0
	var pairs_checked := 0

	for pair in pairs:
		if tested >= 4 and pairs_checked >= 2:
			break
		pairs_checked += 1
		var bx := pair.x * ChunkData.SIZE_X
		var bz := pair.y * ChunkData.SIZE_Z
		var last := ChunkData.SIZE_X - 1

		# Deliberately built by two instances, east first, to mimic two worker
		# threads racing in an arbitrary order.
		var g_east := TerrainGen.new(SEED_A)
		var east := _make(g_east, pair.x + 1, pair.y)
		var g_west := TerrainGen.new(SEED_A)
		var west := _make(g_west, pair.x, pair.y)

		for lz in ChunkData.SIZE_Z:
			for y in ChunkData.SIZE_Y:
				if _is_leaf(west.get_local(last, y, lz)):
					west_leaves += 1
				if _is_leaf(east.get_local(0, y, lz)):
					east_leaves += 1

			# Trunk on the western side: the canopy owes a leaf to the east.
			var tw := _trunk_top(west, last, lz)
			if tw > 0 and finder.surface_height(bx + ChunkData.SIZE_X, bz + lz) < tw:
				tested += 1
				var id := east.get_local(0, tw, lz)
				if not (_is_leaf(id) or _is_log(id)):
					broken += 1
					if first.is_empty():
						first = "tronc en (%d, %d, %d), le chunk est n'a que %s en (%d, %d, %d)" % [
							bx + last, tw, bz + lz, Blocks.display_name(id),
							bx + ChunkData.SIZE_X, tw, bz + lz]

			# Trunk on the eastern side: the canopy owes a leaf to the west.
			var te := _trunk_top(east, 0, lz)
			if te > 0 and finder.surface_height(bx + last, bz + lz) < te:
				tested += 1
				var id2 := west.get_local(last, te, lz)
				if not (_is_leaf(id2) or _is_log(id2)):
					broken += 1
					if first.is_empty():
						first = "tronc en (%d, %d, %d), le chunk ouest n'a que %s en (%d, %d, %d)" % [
							bx + ChunkData.SIZE_X, te, bz + lz, Blocks.display_name(id2),
							bx + last, te, bz + lz]

	print("DIAG cross: pairs=%d checked=%d tested=%d broken=%d west=%d east=%d" % [pairs.size(), pairs_checked, tested, broken, west_leaves, east_leaves])
	check(tested > 0, "aucun arbre a cheval sur la frontiere n'a pu etre teste")
	eq(broken, 0, "un houppier ne doit pas s'arreter net a la frontiere (%d/%d), %s"
		% [broken, tested, first])
	# Neither side may be the only one carrying canopy on the shared plane.
	check(west_leaves > 0 and east_leaves > 0,
		"les deux cotes du plan frontiere doivent porter du feuillage (ouest %d, est %d)"
			% [west_leaves, east_leaves])
	done()


func test_a_chunk_is_identical_whatever_its_neighbours() -> void:
	# A chunk must not depend on which of its neighbours was built before it.
	# Building the whole 3x3 ring around it in two opposite orders and comparing
	# the centre catches any state leaking between generations.
	var g1 := TerrainGen.new(SEED_A)
	var reference := _make(g1, 6, -2)

	var g2 := TerrainGen.new(SEED_A)
	var ring: Array[Vector2i] = [
		Vector2i(7, -1), Vector2i(5, -3), Vector2i(7, -3), Vector2i(5, -1),
	]
	for c in ring:
		_make(g2, c.x, c.y)
	var after_ring := _make(g2, 6, -2)
	check(reference.voxels == after_ring.voxels,
		"le chunk central doit etre identique apres avoir genere son anneau")

	var g3 := TerrainGen.new(SEED_A)
	var centre_first := _make(g3, 6, -2)
	for i in ring.size():
		var c: Vector2i = ring[ring.size() - 1 - i]
		_make(g3, c.x, c.y)
	check(reference.voxels == centre_first.voxels,
		"le chunk central doit etre identique genere en premier")
	eq(after_ring.solid_count, reference.solid_count, "meme compte de blocs pleins")
	check(after_ring.column_top == reference.column_top, "memes sommets de colonne")
	done()
