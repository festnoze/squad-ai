extends WarTest
## The world plan. Everything downstream (terrain flattening, missions, the map,
## enemy garrisons) reads this, and it must be a pure function of the seed: if
## two runs of the same seed disagree, saved campaigns land in the wrong place.


func suite_name() -> String:
	return "layout"


const SEED := 987654321


func _layout() -> Layout:
	return Layout.new(SEED)


func test_the_expected_number_of_sites_is_placed() -> void:
	var layout := _layout()
	eq(layout.sites.size(), Layout.SITE_COUNT,
			"le layout doit poser SITE_COUNT sites")
	eq(layout.world_seed, SEED, "le layout doit retenir sa graine")
	done()


func test_exactly_eight_sectors_are_capturable() -> void:
	var layout := _layout()
	var sectors := layout.sector_ids()
	eq(sectors.size(), 8, "la campagne repose sur exactement 8 secteurs")
	var flagged := 0
	for site in layout.sites:
		if site.is_sector:
			flagged += 1
			check(sectors.has(site.id), "le secteur %d manque dans sector_ids()" % site.id)
	eq(flagged, 8, "le nombre de sites marques secteur doit coller a sector_ids()")
	done()


func test_the_required_site_kinds_are_all_present() -> void:
	var layout := _layout()
	var counts := {}
	for site in layout.sites:
		counts[site.kind] = int(counts.get(site.kind, 0)) + 1
	check(int(counts.get(Layout.SITE_AIRFIELD, 0)) >= 1, "il faut au moins un aerodrome")
	check(int(counts.get(Layout.SITE_BUNKER, 0)) >= 2, "il faut au moins deux bunkers")
	check(int(counts.get(Layout.SITE_CHURCH_TOWN, 0)) >= 1, "il faut au moins un bourg a eglise")
	check(int(counts.get(Layout.SITE_FARM, 0)) >= 3, "il faut au moins trois fermes")
	check(int(counts.get(Layout.SITE_BRIDGE, 0)) >= 1, "il faut au moins un pont")
	check(int(counts.get(Layout.SITE_CAMP, 0)) >= 1, "il faut au moins un camp de prisonniers")
	check(int(counts.get(Layout.SITE_RUIN, 0)) >= 1, "il faut au moins un village en ruines")
	done()


func test_sites_never_overlap() -> void:
	# Two sites closer than 180 m would build a church inside a bunker.
	var layout := _layout()
	var offenders := 0
	for i in layout.sites.size():
		for j in range(i + 1, layout.sites.size()):
			if layout.sites[i].center.distance_to(layout.sites[j].center) < 180.0:
				offenders += 1
	eq(offenders, 0, "des sites se chevauchent")
	done()


func test_every_site_is_inside_the_playable_square() -> void:
	var layout := _layout()
	for site in layout.sites:
		check(absf(site.center.x) < Heightfield.HALF - site.radius,
				"le site %d deborde en x" % site.id)
		check(absf(site.center.y) < Heightfield.HALF - site.radius,
				"le site %d deborde en z" % site.id)
		check(site.radius > 0.0, "le site %d n'a pas d'emprise" % site.id)
		check(site.display_name.strip_edges() != "", "le site %d n'a pas de nom" % site.id)
		check(site.garrison >= 0, "le site %d a une garnison negative" % site.id)
	done()


func test_site_ids_are_unique_and_resolvable() -> void:
	var layout := _layout()
	var seen := {}
	for site in layout.sites:
		check(not seen.has(site.id), "identifiant de site duplique : %d" % site.id)
		seen[site.id] = true
		var found := layout.site_by_id(site.id)
		check(found != null, "site_by_id ne retrouve pas le site %d" % site.id)
		if found != null:
			eq(found.id, site.id, "site_by_id renvoie le mauvais site")
	check(layout.site_by_id(-999) == null, "un identifiant inconnu doit renvoyer null")
	done()


func test_names_are_not_reused() -> void:
	var layout := _layout()
	var names := {}
	for site in layout.sites:
		check(not names.has(site.display_name),
				"le nom '%s' est utilise deux fois" % site.display_name)
		names[site.display_name] = true
	done()


func test_roads_exist_and_stay_in_bounds() -> void:
	var layout := _layout()
	check(not layout.roads.is_empty(), "aucune route generee")
	for road in layout.roads:
		check(road.size() >= 2, "une route a besoin d'au moins deux points")
		for point in road:
			check(absf(point.x) <= Heightfield.HALF and absf(point.y) <= Heightfield.HALF,
					"un point de route sort du monde")
	done()


func test_the_layout_is_reproducible_from_its_seed() -> void:
	# This is the whole contract. If it breaks, a saved campaign reloads into a
	# world where the objectives sit in empty fields.
	var first := Layout.new(SEED)
	var second := Layout.new(SEED)
	eq(first.sites.size(), second.sites.size(), "deux layons de meme graine different en taille")
	for i in first.sites.size():
		check(first.sites[i].center.is_equal_approx(second.sites[i].center),
				"le site %d bouge entre deux constructions" % i)
		eq(first.sites[i].kind, second.sites[i].kind, "le type du site %d change" % i)
		eq(first.sites[i].display_name, second.sites[i].display_name,
				"le nom du site %d change" % i)
	eq(first.roads.size(), second.roads.size(), "le reseau routier n'est pas reproductible")
	done()


func test_a_different_seed_gives_a_different_world() -> void:
	var first := Layout.new(SEED)
	var other := Layout.new(SEED + 12345)
	var identical := 0
	for i in mini(first.sites.size(), other.sites.size()):
		if first.sites[i].center.is_equal_approx(other.sites[i].center):
			identical += 1
	check(identical < first.sites.size(),
			"deux graines differentes produisent le meme monde")
	done()


func test_road_influence_peaks_on_the_road_and_dies_off_it() -> void:
	var layout := _layout()
	var road: PackedVector2Array = layout.roads[0]
	var on_road: Vector2 = road[road.size() / 2]
	var influence_on := layout.road_influence(on_road.x, on_road.y)
	between(influence_on, 0.5, 1.001, "l'influence sur l'axe de la route doit etre forte")
	var far := on_road + Vector2(400.0, 400.0)
	if absf(far.x) < Heightfield.HALF and absf(far.y) < Heightfield.HALF:
		var influence_far := layout.road_influence(far.x, far.y)
		between(influence_far, 0.0, 0.2, "l'influence loin de toute route doit etre nulle")
	else:
		check(true, "point de controle hors monde, ignore")
	done()


func test_spawn_point_is_inside_the_world_and_near_a_site() -> void:
	var layout := _layout()
	var spawn := layout.spawn_point()
	check(Heightfield.in_bounds(spawn.x, spawn.y), "le point de depart est hors du monde")
	var nearest := layout.nearest_site(spawn.x, spawn.y)
	check(nearest != null, "aucun site pres du point de depart")
	if nearest != null:
		check(spawn.distance_to(nearest.center) < 400.0,
				"le joueur demarre trop loin de tout village")
	done()


func test_sites_in_tile_agrees_with_a_brute_force_scan() -> void:
	var layout := _layout()
	var site: Layout.Site = layout.sites[0]
	var tx := floori(site.center.x / Heightfield.TILE_SIZE)
	var tz := floori(site.center.y / Heightfield.TILE_SIZE)
	var found := layout.sites_in_tile(tx, tz)
	var has_it := false
	for candidate in found:
		if candidate.id == site.id:
			has_it = true
	check(has_it, "sites_in_tile oublie le site pose sur cette tuile")
	done()
