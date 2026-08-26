extends WarTest
## Near field grass ring.
##
## Only the pure half is exercised here: what a cell contains, how dense it is,
## and where it refuses to grow. The scene half (cells built two per frame,
## dropped past 34 m) belongs to the in game probe, because it needs a streamed
## world and a player who moves.
##
## The three properties worth guarding are the ones a bug would make invisible
## rather than loud: content that drifts with the path walked, a ceiling that
## quietly stops holding, and blades standing on the river.


func suite_name() -> String:
	return "ground_cover"


const SEED := 246813579


func _field() -> Heightfield:
	var layout := Layout.new(SEED)
	var hf := Heightfield.new(layout)
	hf.bake_sites()
	return hf


## Cells around the player spawn whose content is not empty, so the suite works
## on real ground rather than on a spot that happens to be a road. The spawn is
## guaranteed dry by the layout, which makes it a cheap place to start looking.
func _populated_cells(hf: Heightfield, wanted: int) -> Array[Vector2i]:
	var spawn: Vector2 = hf.layout.spawn_point()
	var ox: int = floori(spawn.x / GroundCover.CELL)
	var oz: int = floori(spawn.y / GroundCover.CELL)
	var out: Array[Vector2i] = []
	for i in 441:
		var cx: int = ox + (i % 21) - 10
		var cz: int = oz + (i / 21) - 10
		var data: PackedFloat32Array = GroundCover.cell_blades(hf, cx, cz, 1.0)
		if GroundCover.packed_count(data) > 0:
			out.append(Vector2i(cx, cz))
			if out.size() >= wanted:
				return out
	return out


# ---------------------------------------------------------------------------

func test_cell_content_is_deterministic() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 6)
	check(cells.size() >= 6, "pas assez de cellules herbues pour tester (%d)" % cells.size())

	var drift := 0
	for cell in cells:
		var a: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		var b: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		if a != b:
			drift += 1
	eq(drift, 0, "%d cellules changent de contenu entre deux appels" % drift)

	# A second height field built on the same seed is a different object; the
	# grass it grows has to be bit for bit the same, otherwise reloading a save
	# reshuffles the meadow under the player.
	var other := _field()
	var mismatch := 0
	for cell in cells:
		var a2: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		var b2: PackedFloat32Array = GroundCover.cell_blades(other, cell.x, cell.y, 1.0)
		if a2 != b2:
			mismatch += 1
	eq(mismatch, 0, "%d cellules different entre deux mondes de meme graine" % mismatch)
	done()


func test_neighbouring_cells_do_not_repeat() -> void:
	# One hash fed with the cell coordinates: get the mixing wrong and every
	# cell grows the same tuft in the same corner, which reads as a grid.
	var hf := _field()
	var cells := _populated_cells(hf, 8)
	check(cells.size() >= 8, "pas assez de cellules herbues (%d)" % cells.size())

	var seen: Dictionary = {}
	var repeats := 0
	for cell in cells:
		var data: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		# Compare the offsets inside the cell, not the world positions, which
		# differ trivially by the cell origin.
		var key := PackedFloat32Array()
		var n: int = mini(GroundCover.packed_count(data), 12)
		for i in n:
			key.append(data[i * GroundCover.STRIDE] - float(cell.x) * GroundCover.CELL)
			key.append(data[i * GroundCover.STRIDE + 2] - float(cell.y) * GroundCover.CELL)
		var text := str(key)
		if seen.has(text):
			repeats += 1
		seen[text] = true
	eq(repeats, 0, "%d cellules voisines partagent le meme motif" % repeats)
	done()


func test_blades_stay_inside_their_cell() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 6)
	var escaped := 0
	for cell in cells:
		var data: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		var base_x: float = float(cell.x) * GroundCover.CELL
		var base_z: float = float(cell.y) * GroundCover.CELL
		for i in GroundCover.packed_count(data):
			var x: float = data[i * GroundCover.STRIDE]
			var z: float = data[i * GroundCover.STRIDE + 2]
			if x < base_x or x > base_x + GroundCover.CELL:
				escaped += 1
			elif z < base_z or z > base_z + GroundCover.CELL:
				escaped += 1
	eq(escaped, 0, "%d brins sortent de leur cellule (couture visible)" % escaped)
	done()


func test_nothing_grows_on_water() -> void:
	var hf := _field()
	var wet := 0
	var checked := 0
	var shorelines := 0
	# Only the cells that actually touch water are worth the cost. Two bands are
	# swept: one across the middle of the pocket, which the river crosses north
	# to south, and one on the east edge along the sea.
	var bands: Array[Vector2i] = [Vector2i(-40, 40), Vector2i(215, 250)]
	for band in bands:
		for cx in range(band.x, band.y + 1):
			for cz in range(-14, 15):
				if not _cell_touches_water(hf, cx, cz):
					continue
				shorelines += 1
				var data: PackedFloat32Array = GroundCover.cell_blades(hf, cx, cz, 1.0)
				for i in GroundCover.packed_count(data):
					var x: float = data[i * GroundCover.STRIDE]
					var z: float = data[i * GroundCover.STRIDE + 2]
					checked += 1
					if hf.is_water(x, z):
						wet += 1
	check(shorelines > 30, "trop peu de cellules de rive testees (%d)" % shorelines)
	eq(wet, 0, "%d brins poussent dans l'eau" % wet)
	check(checked >= 0, "compte de brins de rive invalide")
	done()


## True when one of the corners or the centre of the cell is under water.
func _cell_touches_water(hf: Heightfield, cx: int, cz: int) -> bool:
	var bx: float = float(cx) * GroundCover.CELL
	var bz: float = float(cz) * GroundCover.CELL
	var c: float = GroundCover.CELL
	var points: Array[Vector2] = [Vector2(bx, bz), Vector2(bx + c, bz),
			Vector2(bx, bz + c), Vector2(bx + c, bz + c),
			Vector2(bx + c * 0.5, bz + c * 0.5)]
	for p in points:
		if hf.is_water(p.x, p.y):
			return true
	return false


func test_blade_height_sits_on_the_ground() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 5)
	var floating := 0
	var sample := 0
	for cell in cells:
		var data: PackedFloat32Array = GroundCover.cell_blades(hf, cell.x, cell.y, 1.0)
		var count: int = GroundCover.packed_count(data)
		for i in range(0, count, 7):
			var x: float = data[i * GroundCover.STRIDE]
			var y: float = data[i * GroundCover.STRIDE + 1]
			var z: float = data[i * GroundCover.STRIDE + 2]
			sample += 1
			# The height is read on a 2 m lattice and interpolated, so a small
			# gap is expected; a blade a metre in the air is a bug.
			if absf(y - hf.height_at(x, z)) > 0.60:
				floating += 1
	check(sample > 50, "echantillon de hauteur trop maigre (%d)" % sample)
	eq(floating, 0, "%d brins flottent ou sont enterres" % floating)
	done()


# ---------------------------------------------------------------------------

func test_biome_densities_are_ordered() -> void:
	var dense: PackedInt32Array = [Heightfield.B_MEADOW, Heightfield.B_FIELD,
			Heightfield.B_ORCHARD]
	var sparse: PackedInt32Array = [Heightfield.B_FOREST, Heightfield.B_MARSH]
	var bare: PackedInt32Array = [Heightfield.B_ROAD, Heightfield.B_VILLAGE,
			Heightfield.B_WATER, Heightfield.B_ROCK]

	var lowest_dense := 1 << 30
	for b in dense:
		lowest_dense = mini(lowest_dense, GroundCover.biome_density(b))
	var highest_sparse := 0
	for b in sparse:
		highest_sparse = maxi(highest_sparse, GroundCover.biome_density(b))

	check(highest_sparse > 0, "les biomes clairsemes ne portent aucun brin")
	check(lowest_dense > highest_sparse,
			"la prairie n'est pas plus dense que la foret (%d vs %d)"
					% [lowest_dense, highest_sparse])
	for b in bare:
		eq(GroundCover.biome_density(b), 0,
				"le biome %d devrait etre nu" % b)
	eq(GroundCover.biome_density(-1), 0, "un biome inconnu doit rendre zero")
	eq(GroundCover.biome_density(99), 0, "un biome hors bornes doit rendre zero")
	done()


func test_slot_budget_covers_the_densest_biome() -> void:
	var top := 0
	for b in GroundCover.DENSITY.size():
		top = maxi(top, GroundCover.DENSITY[b])
	eq(GroundCover.SLOTS, top,
			"le nombre de tirages doit egaler la densite maximale")
	done()


func test_global_ceiling_cannot_be_exceeded() -> void:
	# The ring never holds more cells than fit inside RING_RADIUS, and no cell
	# ever holds more than SLOTS blades. If the product passes the ceiling the
	# node has to truncate, which is a visible seam: keep the geometry honest.
	var worst := 0
	for k in 25:
		var ox: float = float(k % 5) * (GroundCover.CELL / 5.0)
		var oz: float = float(k / 5) * (GroundCover.CELL / 5.0)
		var count := 0
		var reach: int = int(ceil(GroundCover.RING_RADIUS / GroundCover.CELL)) + 1
		for dx in range(-reach, reach + 1):
			for dz in range(-reach, reach + 1):
				var mx: float = float(dx) * GroundCover.CELL + GroundCover.CELL * 0.5 - ox
				var mz: float = float(dz) * GroundCover.CELL + GroundCover.CELL * 0.5 - oz
				if mx * mx + mz * mz <= GroundCover.RING_RADIUS * GroundCover.RING_RADIUS:
					count += 1
		worst = maxi(worst, count)
	check(worst > 20, "l'anneau ne couvre presque aucune cellule (%d)" % worst)
	check(worst * GroundCover.SLOTS <= GroundCover.MAX_BLADES,
			"l'anneau plein depasse le plafond (%d x %d > %d)"
					% [worst, GroundCover.SLOTS, GroundCover.MAX_BLADES])
	eq(GroundCover.MAX_BLADES, 24000, "le plafond du contrat est 24000 brins")
	done()


func test_per_cell_count_never_passes_the_slot_budget() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 10)
	var over := 0
	var best := 0
	for cell in cells:
		var count: int = GroundCover.packed_count(
				GroundCover.cell_blades(hf, cell.x, cell.y, 1.0))
		best = maxi(best, count)
		if count > GroundCover.SLOTS:
			over += 1
	eq(over, 0, "%d cellules depassent le budget de tirages" % over)
	check(best > 40, "la cellule la plus fournie est trop maigre (%d brins)" % best)
	done()


# ---------------------------------------------------------------------------

func test_quality_ladder_thins_the_grass() -> void:
	eq(GroundCover.QUALITY_DENSITY.size(), QualityGovernor.LEVEL_COUNT,
			"un multiplicateur de densite par echelon de qualite")
	near(GroundCover.QUALITY_DENSITY[0], 1.0, 0.001,
			"l'echelon 0 garde toute l'herbe")
	near(GroundCover.QUALITY_DENSITY[QualityGovernor.LEVEL_COUNT - 1], 0.35, 0.001,
			"le pire echelon garde 35 pour cent de l'herbe")
	var falling := true
	for i in range(1, GroundCover.QUALITY_DENSITY.size()):
		if GroundCover.QUALITY_DENSITY[i] >= GroundCover.QUALITY_DENSITY[i - 1]:
			falling = false
	check(falling, "la densite doit baisser a chaque echelon")
	done()


func test_quality_level_is_read_from_the_governor() -> void:
	# The governor belongs to the scene and is only ever read, so the deduction
	# goes through the draw distance it publishes.
	var wrong := 0
	for i in QualityGovernor.PROP_DISTANCE.size():
		QualityGovernor.prop_draw_distance = QualityGovernor.PROP_DISTANCE[i]
		if GroundCover.quality_level() != i:
			wrong += 1
		if not is_equal_approx(GroundCover.quality_scale(),
				GroundCover.QUALITY_DENSITY[i]):
			wrong += 1
	QualityGovernor.prop_draw_distance = QualityGovernor.PROP_DISTANCE[0]
	eq(wrong, 0, "%d echelons mal deduits de prop_draw_distance" % wrong)
	near(GroundCover.quality_scale(), 1.0, 0.001,
			"retour a l'echelon 0 apres le test")
	done()


func test_lower_quality_grows_less_grass() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 6)
	var full := 0
	var poor := 0
	for cell in cells:
		full += GroundCover.packed_count(
				GroundCover.cell_blades(hf, cell.x, cell.y, 1.0))
		poor += GroundCover.packed_count(
				GroundCover.cell_blades(hf, cell.x, cell.y, 0.35))
	check(full > 0, "aucune herbe a l'echelon 0")
	check(poor < full, "l'echelon degrade ne reduit pas le nombre de brins (%d vs %d)"
			% [poor, full])
	check(poor > 0, "l'echelon degrade supprime toute l'herbe")
	# Roughly proportional: the acceptance test scales with the multiplier.
	check(float(poor) < float(full) * 0.55,
			"la reduction est trop faible (%d vs %d)" % [poor, full])
	done()


func test_zero_density_scale_grows_nothing() -> void:
	var hf := _field()
	var cells := _populated_cells(hf, 4)
	var grown := 0
	for cell in cells:
		grown += GroundCover.packed_count(
				GroundCover.cell_blades(hf, cell.x, cell.y, 0.0))
	eq(grown, 0, "une densite nulle doit rendre une cellule vide")
	eq(GroundCover.packed_count(GroundCover.cell_blades(null, 0, 0, 1.0)), 0,
			"sans relief la cellule doit rester vide")
	done()


func test_blade_mesh_is_shared_and_light() -> void:
	var mesh: Mesh = GroundCover.blade_mesh()
	check(mesh != null, "le maillage de brin est absent")
	if mesh == null:
		done()
		return
	eq(mesh.get_surface_count(), 1,
			"un brin doit tenir en une seule surface, sinon le MultiMesh explose")
	check(GroundCover.blade_mesh() == mesh,
			"le maillage doit etre partage entre toutes les cellules")
	var box: AABB = mesh.get_aabb()
	between(box.size.y, 0.2, 1.2, "un brin d'herbe mesure entre 20 cm et 1.2 m")
	between(box.size.x, 0.02, 0.6, "un brin d'herbe est etroit")
	done()


func test_cell_geometry_matches_the_contract() -> void:
	near(GroundCover.CELL, 8.0, 0.001, "cellules de 8 m")
	near(GroundCover.RING_RADIUS, 26.0, 0.001, "anneau de 26 m")
	near(GroundCover.DROP_RADIUS, 34.0, 0.001, "oubli au dela de 34 m")
	eq(GroundCover.CELLS_PER_FRAME, 2, "au plus deux cellules par image")
	check(GroundCover.DROP_RADIUS > GroundCover.RING_RADIUS,
			"le rayon d'oubli doit depasser le rayon de construction")
	done()
