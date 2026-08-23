extends WarTest
## Buildings. The recurring failure mode is a house whose collision is one convex
## hull, which plugs the doorway the geometry so carefully carved out. These
## checks look at what the builders actually produce.


func suite_name() -> String:
	return "structures"


func _rng() -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = 424242
	return rng


## Every builder, called uniformly, so a new one cannot silently escape the suite.
func _build_all() -> Array:
	var built: Array = []
	var cover: Array = []
	built.append({"name": "maison", "node": Structures.house(_rng(), 8.0, 6.0, 2, cover)})
	built.append({"name": "grange", "node": Structures.barn(_rng(), cover)})
	built.append({"name": "eglise", "node": Structures.church(_rng(), cover)})
	built.append({"name": "bunker", "node": Structures.bunker(_rng(), cover)})
	built.append({"name": "hangar", "node": Structures.hangar(_rng(), cover)})
	built.append({"name": "mirador", "node": Structures.watchtower(_rng(), cover)})
	built.append({"name": "sacs de sable", "node": Structures.sandbag_ring(_rng(), 4.0, cover)})
	built.append({"name": "tranchee", "node": Structures.trench(_rng(), 12.0, cover)})
	built.append({"name": "muret", "node": Structures.stone_wall(_rng(), 10.0, 1.2, cover)})
	built.append({"name": "depot", "node": Structures.fuel_depot(_rng(), cover)})
	built.append({"name": "canon aa", "node": Structures.aa_gun(_rng(), cover)})
	built.append({"name": "mat radio", "node": Structures.radio_mast(_rng(), cover)})
	built.append({"name": "cage", "node": Structures.prison_cage(_rng(), cover)})
	built.append({"name": "ruine", "node": Structures.ruin(_rng(), cover)})
	built.append({"name": "pont", "node": Structures.bridge(_rng(), 20.0, cover)})
	return built


func _release(built: Array) -> void:
	for entry in built:
		var node: Node3D = entry["node"]
		if node != null and is_instance_valid(node):
			node.free()


func _first_static_body(node: Node) -> StaticBody3D:
	if node is StaticBody3D:
		return node
	for child in node.get_children():
		var found := _first_static_body(child)
		if found != null:
			return found
	return null


func _count_of_type(node: Node, type_name: String) -> int:
	var total := 0
	if node.is_class(type_name):
		total += 1
	for child in node.get_children():
		total += _count_of_type(child, type_name)
	return total


func test_every_builder_returns_a_node() -> void:
	var built := _build_all()
	for entry in built:
		check(entry["node"] != null, "le constructeur '%s' ne renvoie rien" % entry["name"])
		check(entry["node"] is Node3D, "'%s' doit renvoyer un Node3D" % entry["name"])
	_release(built)
	done()


func test_every_building_has_geometry_and_collision() -> void:
	var built := _build_all()
	for entry in built:
		var node: Node3D = entry["node"]
		if node == null:
			continue
		check(_count_of_type(node, "MeshInstance3D") > 0,
				"'%s' n'a aucun maillage visible" % entry["name"])
		var body := _first_static_body(node)
		check(body != null, "'%s' n'a aucun corps de collision" % entry["name"])
		if body != null:
			check(_count_of_type(body, "CollisionShape3D") > 0,
					"'%s' a un corps sans aucune forme" % entry["name"])
	_release(built)
	done()


func test_collision_is_on_the_structure_layer_and_collides_with_nothing() -> void:
	# A static building that also has a collision mask wastes physics time
	# testing itself against every bullet and body in the world.
	var built := _build_all()
	for entry in built:
		var body := _first_static_body(entry["node"])
		if body == null:
			continue
		eq(body.collision_layer & Layers.STRUCTURE, Layers.STRUCTURE,
				"'%s' n'est pas sur la couche structure" % entry["name"])
		eq(body.collision_mask, 0,
				"'%s' ne doit rien tester activement" % entry["name"])
	_release(built)
	done()


func test_enterable_buildings_are_not_sealed_by_a_single_convex_hull() -> void:
	# The one mistake that ruins a village: the geometry has a door, the
	# collision is one box or one convex hull, and the player bounces off it.
	var cover: Array = []
	var house := Structures.house(_rng(), 8.0, 6.0, 2, cover)
	check(house != null, "la maison ne se construit pas")
	if house == null:
		done()
		return
	var body := _first_static_body(house)
	check(body != null, "la maison n'a pas de corps de collision")
	if body != null:
		var shapes := _count_of_type(body, "CollisionShape3D")
		check(shapes >= 4,
				"la maison n'a que %d forme(s) de collision : la porte est bouchee" % shapes)
	house.free()
	done()


func test_builders_report_cover_points() -> void:
	# Without cover points the Germans stand in the open and the firefights look
	# like a shooting gallery.
	var cover: Array = []
	var house := Structures.house(_rng(), 8.0, 6.0, 1, cover)
	check(not cover.is_empty(), "une maison doit exposer des points de couverture")
	for point in cover:
		check(point != null, "un point de couverture nul a ete ajoute")
		if point == null:
			continue
		check(is_finite(point.position.x) and is_finite(point.position.z),
				"un point de couverture a une position non finie")
		check(absf(point.normal.length() - 1.0) < 0.05,
				"la normale d'un point de couverture n'est pas unitaire")
	if house != null:
		house.free()
	done()


func test_low_walls_only_offer_crouch_cover() -> void:
	var cover: Array = []
	var wall := Structures.stone_wall(_rng(), 10.0, 0.9, cover)
	check(not cover.is_empty(), "un muret doit exposer des points de couverture")
	var high_points := 0
	for point in cover:
		if point != null and point.is_high:
			high_points += 1
	eq(high_points, 0, "un muret de 0.9 m ne protege pas un homme debout")
	if wall != null:
		wall.free()
	done()


func test_buildings_stay_within_a_sane_footprint() -> void:
	# A builder that accidentally scales by ten makes a house that swallows the
	# whole village. Check the visual bounds of each one.
	var built := _build_all()
	for entry in built:
		var node: Node3D = entry["node"]
		if node == null:
			continue
		var bounds := AABB()
		var first := true
		for child in node.get_children():
			var mesh_node := child as MeshInstance3D
			if mesh_node == null or mesh_node.mesh == null:
				continue
			var box := mesh_node.transform * mesh_node.mesh.get_aabb()
			if first:
				bounds = box
				first = false
			else:
				bounds = bounds.merge(box)
		if first:
			continue
		check(bounds.size.length() < 400.0,
				"'%s' occupe une emprise demesuree (%s)" % [entry["name"], str(bounds.size)])
		check(bounds.size.length() > 0.5,
				"'%s' est reduit a un point" % entry["name"])
	_release(built)
	done()


func test_builders_are_reproducible_for_a_given_seed() -> void:
	var cover_a: Array = []
	var cover_b: Array = []
	var first := Structures.house(_rng(), 8.0, 6.0, 2, cover_a)
	var second := Structures.house(_rng(), 8.0, 6.0, 2, cover_b)
	eq(cover_a.size(), cover_b.size(),
			"deux maisons de meme graine exposent des couvertures differentes")
	eq(_count_of_type(first, "MeshInstance3D"), _count_of_type(second, "MeshInstance3D"),
			"deux maisons de meme graine n'ont pas la meme geometrie")
	first.free()
	second.free()
	done()
