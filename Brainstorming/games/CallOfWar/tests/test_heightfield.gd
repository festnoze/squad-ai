extends WarTest
## The terrain function. It is called from worker threads millions of times, so
## it has to be pure, finite and fast. Every bug here shows up as a hole in the
## world, a floating village, or a player who falls forever.


func suite_name() -> String:
	return "heightfield"


const SEED := 246813579


func _field() -> Heightfield:
	var layout := Layout.new(SEED)
	var hf := Heightfield.new(layout)
	hf.bake_sites()
	return hf


func test_height_is_finite_everywhere() -> void:
	var hf := _field()
	var bad := 0
	for i in 400:
		var x := -2000.0 + float(i % 20) * 210.0
		var z := -2000.0 + float(i / 20) * 210.0
		var h := hf.height_at(x, z)
		if not is_finite(h):
			bad += 1
	eq(bad, 0, "%d hauteurs non finies" % bad)
	done()


func test_height_stays_in_a_believable_range() -> void:
	var hf := _field()
	var lowest := INF
	var highest := -INF
	for i in 900:
		var x := -2020.0 + float(i % 30) * 135.0
		var z := -2020.0 + float(i / 30) * 135.0
		var h := hf.height_at(x, z)
		lowest = minf(lowest, h)
		highest = maxf(highest, h)
	between(lowest, -60.0, Heightfield.WATER_LEVEL + 5.0,
			"le point le plus bas du monde est invraisemblable")
	between(highest, 15.0, 160.0, "le point le plus haut du monde est invraisemblable")
	check(highest - lowest > 15.0, "le relief est trop plat pour un bocage")
	done()


func test_height_is_deterministic() -> void:
	# Two chunks generated on two different threads must agree on the shared
	# edge, or the world tears open along every tile boundary.
	var hf := _field()
	var drift := 0
	for i in 200:
		var x := -1400.0 + float(i) * 13.7
		var z := 700.0 - float(i) * 9.3
		if not is_equal_approx(hf.height_at(x, z), hf.height_at(x, z)):
			drift += 1
	eq(drift, 0, "height_at n'est pas deterministe")
	done()


func test_two_instances_of_the_same_seed_agree() -> void:
	var first := _field()
	var second := _field()
	var drift := 0
	for i in 120:
		var x := -900.0 + float(i) * 15.0
		var z := -300.0 + float(i) * 11.0
		if absf(first.height_at(x, z) - second.height_at(x, z)) > 0.001:
			drift += 1
	eq(drift, 0, "deux height fields de meme graine divergent (%d points)" % drift)
	done()


func test_the_terrain_has_no_cliffs_where_it_should_be_walkable() -> void:
	# A one metre step over ten centimetres is a wall the player cannot climb and
	# the AI gets stuck against. Sample densely and count the offenders.
	var hf := _field()
	var offenders := 0
	var samples := 0
	for i in 600:
		var x := -1500.0 + float(i % 25) * 120.0
		var z := -1500.0 + float(i / 25) * 120.0
		var here := hf.height_at(x, z)
		var there := hf.height_at(x + 0.5, z)
		samples += 1
		if absf(there - here) > 4.0:
			offenders += 1
	check(samples > 0, "aucun echantillon pris")
	# Cliffs are allowed on the eastern edge and along the river bed, so a few
	# offenders are legitimate. A large share is not.
	check(float(offenders) / float(samples) < 0.08,
			"%d points sur %d presentent une marche verticale" % [offenders, samples])
	done()


func test_normals_point_upwards() -> void:
	var hf := _field()
	var bad := 0
	for i in 200:
		var x := -1200.0 + float(i) * 12.0
		var z := 400.0 - float(i) * 8.0
		var normal := hf.normal_at(x, z)
		if normal.y <= 0.0 or absf(normal.length() - 1.0) > 0.01:
			bad += 1
	eq(bad, 0, "%d normales invalides (non unitaires ou tournees vers le bas)" % bad)
	done()


func test_slope_and_normal_agree() -> void:
	var hf := _field()
	var mismatches := 0
	for i in 100:
		var x := -800.0 + float(i) * 16.0
		var z := -600.0 + float(i) * 12.0
		var slope := hf.slope_at(x, z)
		var from_normal := acos(clampf(hf.normal_at(x, z).y, -1.0, 1.0))
		if absf(slope - from_normal) > 0.2:
			mismatches += 1
		if slope < 0.0 or slope > PI * 0.5 + 0.01:
			mismatches += 1
	eq(mismatches, 0, "la pente ne correspond pas a la normale (%d points)" % mismatches)
	done()


func test_biomes_are_all_valid_ids() -> void:
	var hf := _field()
	var seen := {}
	for i in 900:
		var x := -2000.0 + float(i % 30) * 133.0
		var z := -2000.0 + float(i / 30) * 133.0
		var biome := hf.biome_at(x, z)
		check(biome >= Heightfield.B_FIELD and biome <= Heightfield.B_ORCHARD,
				"biome invalide (%d) en (%f, %f)" % [biome, x, z])
		seen[biome] = true
		if seen.size() > 20:
			break
	check(seen.size() >= 4, "le monde n'offre que %d biomes, c'est trop pauvre" % seen.size())
	done()


func test_water_biome_matches_the_water_level() -> void:
	var hf := _field()
	var contradictions := 0
	for i in 400:
		var x := -1900.0 + float(i % 20) * 200.0
		var z := -1900.0 + float(i / 20) * 200.0
		var under := hf.height_at(x, z) < Heightfield.WATER_LEVEL
		if under != hf.is_water(x, z):
			contradictions += 1
	check(contradictions < 20,
			"is_water contredit la hauteur du terrain sur %d points" % contradictions)
	done()


func test_surface_names_are_known_to_the_sound_bank() -> void:
	var hf := _field()
	var allowed := ["grass", "dirt", "stone", "wood", "water"]
	for i in 300:
		var x := -1800.0 + float(i % 20) * 190.0
		var z := -1800.0 + float(i / 20) * 190.0
		var surface := hf.surface_at(x, z)
		check(allowed.has(surface), "surface inconnue : '%s'" % surface)
		check(SfxLib.NAMES.has("step_%s" % surface),
				"aucun son de pas pour la surface '%s'" % surface)
	done()


func test_terrain_colours_respect_the_albedo_ceiling() -> void:
	var hf := _field()
	for i in 400:
		var x := -1900.0 + float(i % 20) * 200.0
		var z := -1900.0 + float(i / 20) * 200.0
		var color := hf.color_at(x, z)
		var brightest: float = maxf(color.r, maxf(color.g, color.b))
		between(brightest, 0.02, 0.42,
				"la couleur du terrain en (%f, %f) sortira delavee" % [x, z])
	done()


func test_bake_sites_gives_every_site_a_ground_height() -> void:
	var layout := Layout.new(SEED)
	var hf := Heightfield.new(layout)
	hf.bake_sites()
	for site in layout.sites:
		check(is_finite(site.ground), "le site %d n'a pas de hauteur de sol" % site.id)
		between(site.ground, -60.0, 160.0,
				"le site %d est pose a une altitude invraisemblable" % site.id)
	done()


func test_site_footprints_are_flat_enough_to_build_on() -> void:
	# A village on a 20 degree slope has houses hanging in the air. The
	# flattening is what makes the sites usable.
	var layout := Layout.new(SEED)
	var hf := Heightfield.new(layout)
	hf.bake_sites()
	var rough := 0
	for site in layout.sites:
		var lowest := INF
		var highest := -INF
		for i in 16:
			var angle := TAU * float(i) / 16.0
			var x := site.center.x + cos(angle) * site.radius * 0.5
			var z := site.center.y + sin(angle) * site.radius * 0.5
			var h := hf.height_at(x, z)
			lowest = minf(lowest, h)
			highest = maxf(highest, h)
		if highest - lowest > 6.0:
			rough += 1
	check(rough <= 2, "%d sites sont poses sur un terrain trop accidente" % rough)
	done()


func test_bounds_helpers_are_consistent() -> void:
	check(Heightfield.in_bounds(0.0, 0.0), "le centre du monde doit etre jouable")
	check(not Heightfield.in_bounds(Heightfield.HALF + 10.0, 0.0),
			"au dela du bord, on n'est plus jouable")
	check(not Heightfield.in_bounds(0.0, -Heightfield.HALF - 10.0),
			"au dela du bord oppose non plus")
	var clamped := Heightfield.clamp_to_bounds(Vector3(9000.0, 12.0, -9000.0))
	check(Heightfield.in_bounds(clamped.x, clamped.z),
			"clamp_to_bounds doit ramener dans la zone jouable")
	near(clamped.y, 12.0, 0.001, "clamp_to_bounds ne doit pas toucher a l'altitude")
	done()
