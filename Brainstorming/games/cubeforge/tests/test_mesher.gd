extends TestCase
## Mesher: padded volume assembly, hidden face elimination, vertex array layout,
## sky light, per column biome tint and cross block geometry.
##
## Every fixture is built by hand rather than generated, so each expected count is
## exact. A chunk of real terrain could only ever support vague assertions, while
## a single stone block pins the face count to the unit.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

## The 9 entry neighbour array of build_padded with only the central chunk set.
func _ring(centre: ChunkData) -> Array:
	return [null, null, null, null, centre, null, null, null, null]


func _padded_of(centre: ChunkData) -> PackedByteArray:
	return Mesher.build_padded(_ring(centre))


## PW * PD white tints, the neutral input of build_mesh_data.
func _white_tints() -> PackedColorArray:
	var tints := PackedColorArray()
	tints.resize(Mesher.PW * Mesher.PD)
	tints.fill(Color(1.0, 1.0, 1.0, 1.0))
	return tints


## Chunk entirely filled from y 0 to the world ceiling.
func _filled_chunk(id: int) -> ChunkData:
	var data := ChunkData.new()
	for x in ChunkData.SIZE_X:
		for z in ChunkData.SIZE_Z:
			data.fill_column(x, z, 0, ChunkData.SIZE_Y - 1, id)
	return data


## Chunk holding a single full plane of blocks at height y.
func _flat_chunk(y: int, id: int) -> ChunkData:
	var data := ChunkData.new()
	for x in ChunkData.SIZE_X:
		for z in ChunkData.SIZE_Z:
			data.set_local(x, y, z, id)
	return data


# ---------------------------------------------------------------------------
# Surface helpers
# ---------------------------------------------------------------------------

func _vertices(surfaces: Array, s: int) -> PackedVector3Array:
	var entry: Variant = surfaces[s]
	if entry == null:
		return PackedVector3Array()
	var arrays: Array = entry
	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	return verts


func _indices(surfaces: Array, s: int) -> PackedInt32Array:
	var entry: Variant = surfaces[s]
	if entry == null:
		return PackedInt32Array()
	var arrays: Array = entry
	var tris: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
	return tris


## Checks the whole vertex data contract of section 3: exactly six filled slots,
## matching lengths, CUSTOM0 four times the vertex count, indices in range and
## colours inside 0..1.
func _check_surface(entry: Variant, label: String) -> void:
	check(entry != null, "la surface %s existe" % label)
	if entry == null:
		return

	var arrays: Array = entry
	eq(arrays.size(), Mesh.ARRAY_MAX, "la surface %s a Mesh.ARRAY_MAX emplacements" % label)

	var filled: PackedInt32Array = [
		Mesh.ARRAY_VERTEX, Mesh.ARRAY_NORMAL, Mesh.ARRAY_TEX_UV,
		Mesh.ARRAY_COLOR, Mesh.ARRAY_CUSTOM0, Mesh.ARRAY_INDEX,
	]
	var wanted := {}
	for slot in filled:
		wanted[slot] = true
		check(arrays[slot] != null, "la surface %s remplit l'emplacement %d" % [label, slot])
	var extra := 0
	for slot in Mesh.ARRAY_MAX:
		if wanted.has(slot):
			continue
		if arrays[slot] != null:
			extra += 1
	eq(extra, 0, "la surface %s laisse tous les autres emplacements a null" % label)

	var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var norms: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
	var cols: PackedColorArray = arrays[Mesh.ARRAY_COLOR]
	var custom: PackedFloat32Array = arrays[Mesh.ARRAY_CUSTOM0]
	var tris: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]

	var count := verts.size()
	check(count > 0, "la surface %s porte des sommets" % label)
	eq(norms.size(), count, "la surface %s a une normale par sommet" % label)
	eq(uvs.size(), count, "la surface %s a un UV par sommet" % label)
	eq(cols.size(), count, "la surface %s a une couleur par sommet" % label)
	eq(custom.size(), count * 4, "la surface %s a quatre flottants CUSTOM0 par sommet" % label)
	eq(tris.size() % 3, 0, "la surface %s a un nombre d'indices multiple de 3" % label)

	var bad_index := 0
	for t in tris:
		if t < 0 or t >= count:
			bad_index += 1
	eq(bad_index, 0, "tous les indices de %s pointent dans la plage des sommets" % label)

	var bad_uv := 0
	for uv in uvs:
		if uv.x < 0.0 or uv.x > 1.0 or uv.y < 0.0 or uv.y > 1.0:
			bad_uv += 1
	eq(bad_uv, 0, "les UV de %s restent dans la tuile (0..1)" % label)

	var bad_colour := 0
	for c in cols:
		if c.r < 0.0 or c.r > 1.0 or c.g < 0.0 or c.g > 1.0:
			bad_colour += 1
		elif c.b < 0.0 or c.b > 1.0 or c.a < 0.0 or c.a > 1.0:
			bad_colour += 1
	eq(bad_colour, 0, "les couleurs de %s restent dans 0..1" % label)


func suite_name() -> String:
	return "mesher"


# ---------------------------------------------------------------------------
# Padded volume
# ---------------------------------------------------------------------------

func test_padded_shape_and_cell_mapping() -> void:
	eq(Mesher.PW, ChunkData.SIZE_X + 2, "largeur rembourree")
	eq(Mesher.PH, ChunkData.SIZE_Y + 2, "hauteur rembourree")
	eq(Mesher.PD, ChunkData.SIZE_Z + 2, "profondeur rembourree")
	eq(Mesher.PVOLUME, 18 * 98 * 18, "volume rembourre")

	eq(Mesher.padded_index(0, 0, 0), 0, "origine du volume rembourre")
	eq(Mesher.padded_index(0, 1, 0), Mesher.PSTRIDE_Y, "pas en Y")
	eq(Mesher.padded_index(0, 0, 1), Mesher.PSTRIDE_Z, "pas en Z")
	eq(Mesher.padded_index(1, 0, 0), Mesher.PSTRIDE_X, "pas en X")
	eq(Mesher.padded_index(Mesher.PW - 1, Mesher.PH - 1, Mesher.PD - 1), Mesher.PVOLUME - 1,
		"derniere cellule rembourree")

	var data := ChunkData.new()
	data.set_local(0, 0, 0, Blocks.STONE)
	data.set_local(15, 95, 15, Blocks.DIRT)
	data.set_local(3, 40, 9, Blocks.SAND)

	var padded := Mesher.build_padded(_ring(data))
	eq(padded.size(), Mesher.PVOLUME, "build_padded renvoie PVOLUME octets")
	eq(padded[Mesher.padded_index(1, 1, 1)], Blocks.STONE, "la cellule (0,0,0) va en (1,1,1)")
	eq(padded[Mesher.padded_index(16, 96, 16)], Blocks.DIRT, "la cellule (15,95,15) va en (16,96,16)")
	eq(padded[Mesher.padded_index(4, 41, 10)], Blocks.SAND, "la cellule (3,40,9) va en (4,41,10)")
	eq(padded[Mesher.padded_index(4, 41, 11)], Blocks.AIR, "la colonne voisine en Z reste vide")
	eq(padded[Mesher.padded_index(5, 41, 10)], Blocks.AIR, "la colonne voisine en X reste vide")
	eq(padded[Mesher.padded_index(4, 42, 10)], Blocks.AIR, "la cellule du dessus reste vide")
	done()


func test_padded_pulls_every_neighbour() -> void:
	# One distinct block id per neighbour, laid flat at y 30, so a probe in each
	# of the nine padded regions names the chunk it came from.
	var ids: PackedInt32Array = [
		Blocks.STONE, Blocks.DIRT, Blocks.SAND,
		Blocks.GRAVEL, Blocks.CLAY, Blocks.COBBLESTONE,
		Blocks.BRICK, Blocks.MARBLE, Blocks.GRANITE,
	]
	var neighbours: Array = []
	for i in 9:
		neighbours.append(_flat_chunk(30, ids[i]))

	var padded := Mesher.build_padded(neighbours)
	eq(padded.size(), Mesher.PVOLUME, "build_padded renvoie PVOLUME octets")
	for i in 3:
		var dx := i - 1
		var px := 5
		if dx < 0:
			px = 0
		elif dx > 0:
			px = Mesher.PW - 1
		for j in 3:
			var dz := j - 1
			var pz := 5
			if dz < 0:
				pz = 0
			elif dz > 0:
				pz = Mesher.PD - 1
			eq(padded[Mesher.padded_index(px, 31, pz)], ids[(dx + 1) * 3 + dz + 1],
				"la colonne rembourree (%d, %d) vient du voisin (%d, %d)" % [px, pz, dx, dz])

	# Which cell of a neighbour feeds a border column: the west chunk must give
	# its x 15 and its z pz - 1, not the cell next door.
	var west: ChunkData = neighbours[1]
	west.set_local(15, 40, 7, Blocks.DIAMOND_ORE)
	west.set_local(14, 40, 7, Blocks.GOLD_ORE)
	west.set_local(15, 40, 6, Blocks.COAL_ORE)

	var east: ChunkData = neighbours[7]
	east.set_local(0, 50, 3, Blocks.PUMPKIN)
	east.set_local(1, 50, 3, Blocks.BOOKSHELF)

	var north: ChunkData = neighbours[3]
	north.set_local(6, 60, 15, Blocks.OBSIDIAN)
	north.set_local(6, 60, 14, Blocks.SNOW_BLOCK)

	var south: ChunkData = neighbours[5]
	south.set_local(6, 70, 0, Blocks.ICE)
	south.set_local(6, 70, 1, Blocks.WOOL_RED)

	padded = Mesher.build_padded(neighbours)
	eq(padded[Mesher.padded_index(0, 41, 8)], Blocks.DIAMOND_ORE,
		"la colonne px 0 lit x 15 du voisin ouest")
	eq(padded[Mesher.padded_index(0, 41, 7)], Blocks.COAL_ORE,
		"la colonne pz 7 lit z 6 du voisin ouest")
	eq(padded[Mesher.padded_index(Mesher.PW - 1, 51, 4)], Blocks.PUMPKIN,
		"la colonne px 17 lit x 0 du voisin est")
	eq(padded[Mesher.padded_index(7, 61, 0)], Blocks.OBSIDIAN,
		"la colonne pz 0 lit z 15 du voisin nord")
	eq(padded[Mesher.padded_index(7, 71, Mesher.PD - 1)], Blocks.ICE,
		"la colonne pz 17 lit z 0 du voisin sud")
	done()


func test_padded_treats_a_null_neighbour_as_air() -> void:
	var neighbours: Array = []
	for i in 9:
		neighbours.append(_flat_chunk(30, Blocks.STONE))
	neighbours[1] = null

	var padded := Mesher.build_padded(neighbours)
	eq(padded.size(), Mesher.PVOLUME, "build_padded renvoie PVOLUME octets malgre un voisin null")

	var non_air := 0
	for pz in range(1, Mesher.PD - 1):
		for py in Mesher.PH:
			if padded[Mesher.padded_index(0, py, pz)] != Blocks.AIR:
				non_air += 1
	eq(non_air, 0, "la bande du voisin null est entierement de l'air")

	eq(padded[Mesher.padded_index(5, 31, 5)], Blocks.STONE, "le chunk central reste lu")
	eq(padded[Mesher.padded_index(Mesher.PW - 1, 31, 5)], Blocks.STONE, "le voisin est reste lu")
	eq(padded[Mesher.padded_index(5, 31, 0)], Blocks.STONE, "le voisin nord reste lu")
	eq(padded[Mesher.padded_index(0, 31, 0)], Blocks.STONE, "le coin nord-ouest reste lu")
	done()


func test_padded_floor_and_ceiling_planes_stay_air() -> void:
	var neighbours: Array = []
	for i in 9:
		neighbours.append(_filled_chunk(Blocks.STONE))

	var padded := Mesher.build_padded(neighbours)
	var floor_bad := 0
	var ceiling_bad := 0
	var interior_bad := 0
	for px in Mesher.PW:
		for pz in Mesher.PD:
			if padded[Mesher.padded_index(px, 0, pz)] != Blocks.AIR:
				floor_bad += 1
			if padded[Mesher.padded_index(px, Mesher.PH - 1, pz)] != Blocks.AIR:
				ceiling_bad += 1
			if padded[Mesher.padded_index(px, 1, pz)] != Blocks.STONE:
				interior_bad += 1
			elif padded[Mesher.padded_index(px, Mesher.PH - 2, pz)] != Blocks.STONE:
				interior_bad += 1
	eq(floor_bad, 0, "le plan py 0 est entierement de l'air")
	eq(ceiling_bad, 0, "le plan py PH-1 est entierement de l'air")
	eq(interior_bad, 0, "les plans py 1 et py PH-2 portent le contenu des chunks")
	done()


# ---------------------------------------------------------------------------
# Hidden face elimination
# ---------------------------------------------------------------------------

func test_a_single_block_makes_exactly_one_cube() -> void:
	var data := ChunkData.new()
	data.set_local(8, 40, 8, Blocks.STONE)

	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var surfaces: Array = out["surfaces"]
	eq(surfaces.size(), Blocks.SURFACE_COUNT, "une entree par surface de rendu")

	_check_surface(surfaces[Blocks.Surface.OPAQUE], "opaque")
	eq(_vertices(surfaces, Blocks.Surface.OPAQUE).size(), 24, "six faces de quatre sommets")
	eq(_indices(surfaces, Blocks.Surface.OPAQUE).size(), 36, "six faces de deux triangles")

	check(surfaces[Blocks.Surface.CUTOUT] == null, "aucune surface cutout pour un bloc de pierre")
	check(surfaces[Blocks.Surface.TRANSLUCENT] == null, "aucune surface translucide")
	check(surfaces[Blocks.Surface.WATER] == null, "aucune surface d'eau")

	var lights: PackedVector3Array = out["lights"]
	var light_ids: PackedInt32Array = out["light_ids"]
	eq(lights.size(), 0, "la pierre n'emet pas de lumiere")
	eq(light_ids.size(), 0, "aucun id de lumiere")

	# The cube must sit exactly on its cell, from (8, 40, 8) to (9, 41, 9).
	var verts := _vertices(surfaces, Blocks.Surface.OPAQUE)
	var outside := 0
	for v in verts:
		if v.x < 8.0 or v.x > 9.0 or v.y < 40.0 or v.y > 41.0 or v.z < 8.0 or v.z > 9.0:
			outside += 1
	eq(outside, 0, "le cube tient dans sa cellule en coordonnees locales")
	done()


func test_a_solid_chunk_keeps_only_its_shell() -> void:
	var data := _filled_chunk(Blocks.STONE)
	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var surfaces: Array = out["surfaces"]

	# Neighbours are null, so the four sides are exposed over their full height
	# and the two horizontal caps over the chunk footprint. Everything else is
	# interior and must be eliminated.
	var expected_faces := 4 * ChunkData.SIZE_X * ChunkData.SIZE_Y + 2 * ChunkData.SIZE_X * ChunkData.SIZE_Z
	eq(expected_faces, 6656, "coque attendue: 4 cotes de 16 x 96 plus 2 faces de 16 x 16")

	_check_surface(surfaces[Blocks.Surface.OPAQUE], "opaque")
	eq(_vertices(surfaces, Blocks.Surface.OPAQUE).size(), expected_faces * 4,
		"seule la coque exterieure est maillee")
	eq(_indices(surfaces, Blocks.Surface.OPAQUE).size(), expected_faces * 6,
		"deux triangles par face de coque")
	check(surfaces[Blocks.Surface.CUTOUT] == null, "aucune surface cutout")
	check(surfaces[Blocks.Surface.WATER] == null, "aucune surface d'eau")
	done()


func test_adjacent_water_cells_share_no_interior_face() -> void:
	var data := ChunkData.new()
	data.set_local(5, 40, 5, Blocks.WATER)
	data.set_local(6, 40, 5, Blocks.WATER)

	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var surfaces: Array = out["surfaces"]

	_check_surface(surfaces[Blocks.Surface.WATER], "eau")
	check(surfaces[Blocks.Surface.OPAQUE] == null, "l'eau ne va pas sur la surface opaque")
	# Ten faces, not twelve: the two cells merge along their shared plane.
	eq(_vertices(surfaces, Blocks.Surface.WATER).size(), 40, "cinq faces par cellule d'eau")
	eq(_indices(surfaces, Blocks.Surface.WATER).size(), 60, "deux triangles par face d'eau")

	# The liquid top is dipped to y + 0.88 because the cell above holds no liquid.
	var verts := _vertices(surfaces, Blocks.Surface.WATER)
	var top := 0.0
	var too_high := 0
	for v in verts:
		top = maxf(top, v.y)
		if v.y > 40.9:
			too_high += 1
	near(top, 40.88, 0.002, "la surface de l'eau est abaissee a y + 0.88")
	eq(too_high, 0, "aucun sommet d'eau ne monte au plafond de la cellule")
	done()


func test_glass_merges_with_glass_but_not_with_stone() -> void:
	var pair := ChunkData.new()
	pair.set_local(5, 40, 5, Blocks.GLASS)
	pair.set_local(6, 40, 5, Blocks.GLASS)
	var merged: Array = Mesher.build_mesh_data(_padded_of(pair), _white_tints())["surfaces"]

	_check_surface(merged[Blocks.Surface.CUTOUT], "cutout verre contre verre")
	eq(_vertices(merged, Blocks.Surface.CUTOUT).size(), 40,
		"deux verres voisins fusionnent leur face commune (10 faces)")
	check(merged[Blocks.Surface.OPAQUE] == null, "le verre ne va pas sur la surface opaque")

	var mixed := ChunkData.new()
	mixed.set_local(5, 40, 5, Blocks.GLASS)
	mixed.set_local(6, 40, 5, Blocks.STONE)
	var split: Array = Mesher.build_mesh_data(_padded_of(mixed), _white_tints())["surfaces"]

	_check_surface(split[Blocks.Surface.CUTOUT], "cutout verre contre pierre")
	_check_surface(split[Blocks.Surface.OPAQUE], "opaque pierre contre verre")
	# The glass hides its own face against the opaque stone, but the stone still
	# draws towards the glass, so the pair keeps 11 faces instead of 10.
	eq(_vertices(split, Blocks.Surface.CUTOUT).size(), 20,
		"le verre perd sa face contre la pierre opaque")
	eq(_vertices(split, Blocks.Surface.OPAQUE).size(), 24,
		"la pierre garde ses six faces, dont celle qui regarde le verre")
	done()


# ---------------------------------------------------------------------------
# Vertex data
# ---------------------------------------------------------------------------

func test_colours_carry_emission_of_their_own_block() -> void:
	var data := ChunkData.new()
	data.set_local(8, 40, 8, Blocks.LAMP)
	data.set_local(2, 40, 2, Blocks.STONE)
	data.set_local(12, 40, 12, Blocks.TORCH)

	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var surfaces: Array = out["surfaces"]
	_check_surface(surfaces[Blocks.Surface.OPAQUE], "opaque")
	_check_surface(surfaces[Blocks.Surface.CUTOUT], "cutout")

	var opaque: Array = surfaces[Blocks.Surface.OPAQUE]
	var verts: PackedVector3Array = opaque[Mesh.ARRAY_VERTEX]
	var cols: PackedColorArray = opaque[Mesh.ARRAY_COLOR]
	eq(verts.size(), 48, "deux cubes opaques")

	var bad_alpha := 0
	for i in verts.size():
		var expected: float = Blocks.emission(Blocks.LAMP) if verts[i].x > 7.0 else Blocks.emission(Blocks.STONE)
		if absf(cols[i].a - expected) > 0.002:
			bad_alpha += 1
	eq(bad_alpha, 0, "COLOR.a vaut Blocks.emission du bloc auquel la face appartient")

	var cutout: Array = surfaces[Blocks.Surface.CUTOUT]
	var plant_cols: PackedColorArray = cutout[Mesh.ARRAY_COLOR]
	var bad_torch := 0
	for c in plant_cols:
		if absf(c.a - Blocks.emission(Blocks.TORCH)) > 0.002:
			bad_torch += 1
	eq(bad_torch, 0, "la torche porte son emission sur la surface cutout")

	var lights: PackedVector3Array = out["lights"]
	var light_ids: PackedInt32Array = out["light_ids"]
	eq(lights.size(), 2, "une lumiere par bloc emissif")
	eq(light_ids.size(), lights.size(), "un id de bloc par lumiere")
	var lamp_found := false
	var torch_found := false
	for i in lights.size():
		if lights[i].is_equal_approx(Vector3(8.5, 40.5, 8.5)) and light_ids[i] == Blocks.LAMP:
			lamp_found = true
		if lights[i].is_equal_approx(Vector3(12.5, 40.5, 12.5)) and light_ids[i] == Blocks.TORCH:
			torch_found = true
	check(lamp_found, "la lampe est listee au centre de sa cellule")
	check(torch_found, "la torche est listee au centre de sa cellule")
	done()


func test_sky_light_darkens_buried_faces() -> void:
	# A solid block of stone up to y 60 with one air cell hollowed at y 30. The
	# pocket sits under thirty opaque blocks and its eight side columns are just
	# as high, so no side sample can rescue it.
	var data := ChunkData.new()
	for x in ChunkData.SIZE_X:
		for z in ChunkData.SIZE_Z:
			data.fill_column(x, z, 0, 60, Blocks.STONE)
	data.set_local(8, 30, 8, Blocks.AIR)

	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var opaque: Array = out["surfaces"][Blocks.Surface.OPAQUE]
	_check_surface(opaque, "opaque")

	var verts: PackedVector3Array = opaque[Mesh.ARRAY_VERTEX]
	var norms: PackedVector3Array = opaque[Mesh.ARRAY_NORMAL]
	var cols: PackedColorArray = opaque[Mesh.ARRAY_COLOR]

	var sunlit_min := 2.0
	var sunlit_count := 0
	var buried_max := 0.0
	var buried_count := 0
	for i in verts.size():
		var v := verts[i]
		var lum: float = cols[i].r
		if norms[i].y > 0.9 and absf(v.y - 61.0) < 0.001:
			sunlit_count += 1
			sunlit_min = minf(sunlit_min, lum)
		elif v.x >= 8.0 and v.x <= 9.0 and v.y >= 30.0 and v.y <= 31.0 and v.z >= 8.0 and v.z <= 9.0:
			buried_count += 1
			buried_max = maxf(buried_max, lum)

	eq(sunlit_count, ChunkData.SIZE_X * ChunkData.SIZE_Z * 4, "une face de dessus par colonne au grand jour")
	eq(buried_count, 6 * 4, "les six faces de la poche d'air sont echantillonnees")
	near(sunlit_min, 1.0, 0.003, "une face de dessus degagee recoit toute la lumiere du ciel")
	check(buried_max < 0.2,
		"une face enterree sous trente blocs reste sombre (obtenu %f)" % buried_max)
	check(buried_max < sunlit_min,
		"les faces enterrees sont plus sombres que les faces au soleil (%f contre %f)"
			% [buried_max, sunlit_min])
	done()


func test_grass_tint_follows_its_own_column() -> void:
	# A distinguishable tint per column: red carries px, green carries pz. A
	# uniform tint array would hide an indexing mistake, this one cannot.
	var data := _flat_chunk(40, Blocks.GRASS)
	var tints := PackedColorArray()
	tints.resize(Mesher.PW * Mesher.PD)
	for px in Mesher.PW:
		for pz in Mesher.PD:
			tints[px * Mesher.PD + pz] = Color(float(px) / 64.0, float(pz) / 64.0, 1.0, 1.0)

	var out := Mesher.build_mesh_data(_padded_of(data), tints)
	var opaque: Array = out["surfaces"][Blocks.Surface.OPAQUE]
	_check_surface(opaque, "opaque")

	var verts: PackedVector3Array = opaque[Mesh.ARRAY_VERTEX]
	var norms: PackedVector3Array = opaque[Mesh.ARRAY_NORMAL]
	var cols: PackedColorArray = opaque[Mesh.ARRAY_COLOR]

	var tops := 0
	var wrong_red := 0
	var wrong_green := 0
	var tinted_sides := 0
	var quad := 0
	while quad * 4 < verts.size():
		var base := quad * 4
		if norms[base].y > 0.9:
			# A flat plane under an empty sky: sky light and ambient occlusion are
			# both 1.0 on the top faces, so the colour is the tint itself.
			var cell_x := verts[base].x
			var cell_z := verts[base].z
			for k in range(1, 4):
				cell_x = minf(cell_x, verts[base + k].x)
				cell_z = minf(cell_z, verts[base + k].z)
			var px := int(roundf(cell_x)) + 1
			var pz := int(roundf(cell_z)) + 1
			var want: Color = tints[px * Mesher.PD + pz]
			tops += 1
			for k in 4:
				if absf(cols[base + k].r - want.r) > 0.003:
					wrong_red += 1
				if absf(cols[base + k].g - want.g) > 0.003:
					wrong_green += 1
		else:
			# Only the +Y face of grass is in its tint mask, so every other face
			# must stay grey (r == g == b).
			for k in 4:
				var c := cols[base + k]
				if absf(c.r - c.g) > 0.003 or absf(c.g - c.b) > 0.003:
					tinted_sides += 1
		quad += 1

	eq(tops, ChunkData.SIZE_X * ChunkData.SIZE_Z, "une face de dessus par colonne du chunk")
	eq(wrong_red, 0, "le rouge de la teinte vient de la colonne px de la face")
	eq(wrong_green, 0, "le vert de la teinte vient de la colonne pz de la face")
	eq(tinted_sides, 0, "seule la face de dessus de l'herbe est teintee")
	done()


func test_cross_block_makes_two_swaying_quads() -> void:
	var data := ChunkData.new()
	data.set_local(8, 40, 8, Blocks.FERN)

	var out := Mesher.build_mesh_data(_padded_of(data), _white_tints())
	var surfaces: Array = out["surfaces"]
	_check_surface(surfaces[Blocks.Surface.CUTOUT], "cutout")
	check(surfaces[Blocks.Surface.OPAQUE] == null, "une plante n'emet aucune face de cube")
	check(surfaces[Blocks.Surface.TRANSLUCENT] == null, "aucune surface translucide")
	check(surfaces[Blocks.Surface.WATER] == null, "aucune surface d'eau")

	var cutout: Array = surfaces[Blocks.Surface.CUTOUT]
	var verts: PackedVector3Array = cutout[Mesh.ARRAY_VERTEX]
	var custom: PackedFloat32Array = cutout[Mesh.ARRAY_CUSTOM0]
	var tris: PackedInt32Array = cutout[Mesh.ARRAY_INDEX]
	eq(verts.size(), 8, "deux quads en diagonale, pas six faces")
	eq(tris.size(), 12, "deux quads triangules")
	eq(custom.size(), 32, "quatre flottants CUSTOM0 par sommet")

	var layer := float(Blocks.tile_of(Blocks.FERN, Blocks.FACE_PX))
	var bad_layer := 0
	var bad_wave := 0
	var lows := 0
	var highs := 0
	var out_of_cell := 0
	for i in verts.size():
		if absf(custom[i * 4] - layer) > 0.001:
			bad_layer += 1
		var wave: float = custom[i * 4 + 1]
		if absf(verts[i].y - 40.0) < 0.001:
			lows += 1
			if absf(wave) > 0.0001:
				bad_wave += 1
		elif absf(verts[i].y - 41.0) < 0.001:
			highs += 1
			if wave <= 0.0:
				bad_wave += 1
		# Inset 0.146 plus a jitter of at most 0.18 keeps the quads near the cell.
		if verts[i].x < 7.8 or verts[i].x > 9.2 or verts[i].z < 7.8 or verts[i].z > 9.2:
			out_of_cell += 1

	eq(lows, 4, "quatre sommets de pied a y")
	eq(highs, 4, "quatre sommets de tete a y + 1")
	eq(bad_layer, 0, "CUSTOM0.x porte le calque de tuile de la plante")
	eq(bad_wave, 0, "CUSTOM0.y vaut 0 en bas et plus de 0 en haut")
	eq(out_of_cell, 0, "les quads restent au voisinage de leur cellule")

	var lights: PackedVector3Array = out["lights"]
	eq(lights.size(), 0, "une fougere n'emet pas de lumiere")
	done()


func test_realistic_corner_offsets_smooth_natural_steps_only() -> void:
	var terrain := ChunkData.new()
	for x in ChunkData.SIZE_X:
		var y := 40 if x < 8 else 41
		for z in ChunkData.SIZE_Z:
			terrain.set_local(x, y, z, Blocks.GRASS)

	var terrain_out := Mesher.build_mesh_data(_padded_of(terrain), _white_tints())
	var opaque: Array = terrain_out["surfaces"][Blocks.Surface.OPAQUE]
	var custom: PackedFloat32Array = opaque[Mesh.ARRAY_CUSTOM0]
	var displaced := 0
	var out_of_bounds := 0
	for i in range(2, custom.size(), 4):
		if absf(custom[i]) > 0.001:
			displaced += 1
		if absf(custom[i]) > 0.421:
			out_of_bounds += 1
	check(displaced > 0, "une marche de terrain naturel porte des coins lisses")
	eq(out_of_bounds, 0, "le lissage reste un chanfrein borne sous un demi-bloc")

	# An authored block uses the same vertex channel, but must keep it at zero so
	# houses and barriers retain deliberate, closed silhouettes.
	var structure := ChunkData.new()
	structure.set_local(8, 40, 8, Blocks.OAK_PLANKS)
	var structure_out := Mesher.build_mesh_data(_padded_of(structure), _white_tints())
	var structure_surface: Array = structure_out["surfaces"][Blocks.Surface.OPAQUE]
	var structure_custom: PackedFloat32Array = structure_surface[Mesh.ARRAY_CUSTOM0]
	var structure_offsets := 0
	for i in range(2, structure_custom.size(), 4):
		if absf(structure_custom[i]) > 0.001:
			structure_offsets += 1
	eq(structure_offsets, 0, "les blocs construits restent cubiques")
	done()
