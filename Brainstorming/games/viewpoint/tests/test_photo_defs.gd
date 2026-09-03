extends ViewTest
## Validity of the photo catalog and coherence of the computed thumbnails.

const KNOWN_KINDS := ["box", "cylinder", "battery", "bridge", "stairs", "arch", "photo"]


func suite_name() -> String:
	return "photo_defs"


func test_catalog() -> void:
	var ids := PhotoDefs.all_ids()
	eq(ids.size(), 8, "huit photos au catalogue")
	for id in ids:
		var def := PhotoDefs.get_def(id)
		check(not def.is_empty(), "definition presente pour %s" % id)
		check(def.get("title", "") != "", "%s : titre non vide" % id)
		check(not def.get("props", []).is_empty(), "%s : au moins un prop" % id)
		check(def.get("erase_depth", 0.0) > 0.0, "%s : profondeur d'effacement positive" % id)
	check(PhotoDefs.get_def("inexistante").is_empty(), "id inconnu : definition vide")
	done()


func test_props_valid() -> void:
	for id in PhotoDefs.all_ids():
		var def := PhotoDefs.get_def(id)
		for prop in def["props"]:
			check(KNOWN_KINDS.has(prop["kind"]), "%s : genre de prop connu (%s)" % [id, prop["kind"]])
			check(Palette.has_color(prop.get("color", "stone")), "%s : couleur connue" % id)
			var pos: Vector3 = prop["pos"]
			check(pos.z < 0.0, "%s : prop devant la camera (z = %f)" % [id, pos.z])
			if prop["kind"] == "photo":
				check(not PhotoDefs.get_def(prop["id"]).is_empty(), "%s : photo imbriquee %s au catalogue" % [id, prop["id"]])
	done()


func test_backdrop_universal() -> void:
	# v4: a photo is ALWAYS the 2D picture of a 3D space, so every def paints a
	# backdrop, and it stands far behind the carve rather than capping it.
	for id in PhotoDefs.all_ids():
		var def := PhotoDefs.get_def(id)
		var backdrop: Dictionary = def.get("backdrop", {})
		# One documented exception: a photo whose own geometry paves the frame
		# is sealed by it. The door is the case, and it MUST be: a backdrop is
		# a solid wall, so one behind the opening would plug the doorway.
		if def.get("seal", "") == "content":
			check(backdrop.is_empty(), "%s : scelle par son contenu, donc sans fond solide" % id)
			continue
		check(not backdrop.is_empty(), "%s : fond peint obligatoire" % id)
		if backdrop.is_empty():
			continue
		check(backdrop["depth"] > 0.0, "%s : backdrop a distance positive" % id)
		check(Palette.has_color(backdrop.get("top", "sky_top")), "%s : couleur haute du backdrop connue" % id)
		check(Palette.has_color(backdrop.get("bottom", "sky_horizon")), "%s : couleur basse du backdrop connue" % id)
		# v6.1 : le fond n'est plus le couvercle de la decoupe, c'est le
		# lointain de l'image. Il se tient TRES loin derriere le plan
		# d'effacement, sinon on retombe sur le defaut qui a motive le
		# changement : traverser un gouffre en marchant dans un mur de ciel.
		check(backdrop["depth"] > def["erase_depth"] * 2.5,
			"%s : le fond peint est un lointain, pas un couvercle (%.1f m pour une decoupe de %.1f m)"
				% [id, backdrop["depth"], def["erase_depth"]])
	done()


func test_no_photo_patches_the_ground() -> void:
	# The ground language (PRD 3.6): grey ground is PERMANENT, a photo placed
	# over it is added to it. So no photo carries a slab of grey ground: a
	# bridge photo lays a bridge, it does not repave the floor. Patching would
	# only stack a second floor on the first.
	for id in PhotoDefs.all_ids():
		for prop in PhotoDefs.get_def(id)["props"]:
			ne(prop.get("color", ""), "platform", "%s : aucune photo ne rapiece le sol permanent" % id)
	done()


func test_loose_props() -> void:
	# Loose box props materialize as falling rigid bodies. The other props hold
	# exact positions the puzzles depend on and must stay static.
	var crate: Dictionary = PhotoDefs.get_def("caisse")["props"][0]
	eq(crate["kind"], "box", "la caisse est une boite")
	check(crate.get("loose", false), "la caisse est un objet libre : elle tombe")
	for id in ["pile", "coffret"]:
		var base: Dictionary = PhotoDefs.get_def(id)["props"][0]
		check(not base.get("loose", false), "%s : le socle reste statique" % id)
	for id in ["console", "corniche"]:
		var slab: Dictionary = PhotoDefs.get_def(id)["props"][0]
		check(not slab.get("loose", false), "%s : la dalle reste statique" % id)

	# The expansion carries the key over to the primitives actually built.
	var prims := PhotoDefs.expand_prop(crate)
	eq(prims.size(), 1, "la caisse s'etend en une primitive")
	check(prims[0].get("loose", false), "l'expansion propage la cle loose")
	var fixed := PhotoDefs.expand_prop({"kind": "box", "pos": Vector3(0, -1, -3), "size": Vector3(2, 0.3, 2), "color": "stone"})
	check(not fixed[0].has("loose"), "une boite non libre n'herite d'aucune cle loose")
	var stairs := PhotoDefs.expand_prop({"kind": "stairs", "pos": Vector3(0, -1.6, -1.2), "size": Vector3(2.2, 4.6, 7.0), "color": "stone", "loose": true})
	for step in stairs:
		check(not step.has("loose"), "seules les boites propagent loose, pas les marches")
	done()


func test_expansion() -> void:
	for id in PhotoDefs.all_ids():
		var prims := PhotoDefs.expand_props(PhotoDefs.get_def(id))
		check(not prims.is_empty(), "%s : expansion non vide" % id)
		for prim in prims:
			check(["box", "cylinder", "battery", "photo_item"].has(prim["kind"]), "%s : primitive elementaire" % id)
			var size: Vector3 = prim["size"]
			check(size.x > 0 and size.y > 0 and size.z > 0, "%s : primitive de taille positive" % id)
			check(Palette.has_color(prim["color"]), "%s : couleur de primitive connue" % id)

	var stairs := PhotoDefs.expand_prop({"kind": "stairs", "pos": Vector3(0, -1.6, -1.2), "size": Vector3(2.2, 4.6, 7.0), "color": "stone"})
	eq(stairs.size(), 8, "l'escalier fait huit marches")
	for i in range(1, stairs.size()):
		check(stairs[i]["size"].y > stairs[i - 1]["size"].y, "marche %d plus haute que la precedente" % i)
		check(stairs[i]["center"].z < stairs[i - 1]["center"].z, "marche %d plus loin que la precedente" % i)
	var top: Dictionary = stairs[stairs.size() - 1]
	near(top["center"].y + top["size"].y * 0.5, -1.6 + 4.6, 0.001, "le sommet atteint la hauteur totale")
	done()


func test_battery_count() -> void:
	eq(PhotoDefs.battery_count("pile"), 1, "la photo Pile contient une pile")
	eq(PhotoDefs.battery_count("passerelle"), 0, "la Passerelle n'en contient pas")
	eq(PhotoDefs.battery_count("escalier"), 0, "l'Escalier n'en contient pas")
	eq(PhotoDefs.battery_count("porte"), 0, "la Porte n'en contient pas")
	eq(PhotoDefs.battery_count("coffret"), 0, "le Coffret n'a pas de pile directe")
	eq(PhotoDefs.battery_count_recursive("coffret"), 1, "le Coffret vaut une pile via la photo Pile")
	eq(PhotoDefs.battery_count_recursive("pile"), 1, "compte recursif stable sur une photo simple")
	# The visited guard: feeding an already-visited id returns zero instead of
	# looping forever, which is what protects a hypothetical cyclic catalog.
	eq(PhotoDefs.battery_count_recursive("pile", {"pile": true}), 0, "garde anti-cycle active")
	done()


func test_rotation_geometry() -> void:
	# The design contract of the flips (docs/LEVELS_V2.md section 2): a console
	# slab is boardable at roll 0 (top under the 1.5 jump) and NOT boardable
	# from its own placement spot at roll 180.
	var slab: Dictionary = PhotoDefs.expand_props(PhotoDefs.get_def("console"))[0]
	var eye := 1.62
	var top_roll0: float = eye + slab["center"].y + slab["size"].y * 0.5
	between(top_roll0, 0.6, 1.5, "console 0 deg sautable depuis le sol")
	var top_roll180: float = eye - slab["center"].y + slab["size"].y * 0.5
	check(top_roll180 > 1.5, "console 180 deg exige un appui intermediaire")
	check(top_roll180 < top_roll0 + 1.5, "console 180 deg atteignable depuis la console 0 deg")
	var ledge: Dictionary = PhotoDefs.expand_props(PhotoDefs.get_def("corniche"))[0]
	check(absf(ledge["center"].x) > 0.5, "corniche decalee lateralement : la rotation change le cote")
	done()


func test_porte_seal() -> void:
	# The airtightness rule: a photo with a seal wall only erases up to the
	# seal plane, and the seal covers the whole frustum cross-section there.
	# Otherwise the carved hole is wider than the placed wall and the player
	# slips through the gap (the reported "interstice" bug).
	var def := PhotoDefs.get_def("porte")
	var wall_depth := 6.0
	# The carve runs a little past the wall so the ground continues behind the
	# doorway, but not so far that it eats what the wall does not cover.
	between(def["erase_depth"], wall_depth, wall_depth + 1.6, "la porte decoupe juste ce qu'il faut derriere son mur")
	check(def.get("seal", "") == "content", "la porte est scellee par son mur, pas par un fond solide")
	check(def.get("backdrop", {}).is_empty(), "aucun fond solide ne bouche l'ouverture")
	var half := PhotoMath.half_extent_at(wall_depth, PhotoMath.PHOTO_FOV_DEG)
	between(half, 2.7, 2.8, "demi-trame du frustum a 6 m connue")

	# Sample the frustum cross-section at the seal plane: every point must be
	# either inside the door opening or covered by a wall panel.
	var walls: Array = []
	for prop in def["props"]:
		if prop["color"] == "frame":
			walls.append(prop)
	var uncovered := 0
	var steps := 21
	for ix in steps:
		for iy in steps:
			var x := (float(ix) / (steps - 1) * 2.0 - 1.0) * half
			var y := (float(iy) / (steps - 1) * 2.0 - 1.0) * half
			var in_opening: bool = absf(x) < 0.8 and y < 0.98
			if in_opening:
				continue
			var covered := false
			for wall in walls:
				var pos: Vector3 = wall["pos"]
				var size: Vector3 = wall["size"]
				if absf(x - pos.x) <= size.x * 0.5 + 0.02 and absf(y - pos.y) <= size.y * 0.5 + 0.02:
					covered = true
					break
			if not covered:
				uncovered += 1
	eq(uncovered, 0, "le mur de la porte pave toute la trame hors ouverture")
	done()


func test_thumbnail() -> void:
	for id in PhotoDefs.all_ids():
		var tex := PhotoDefs.thumbnail(id)
		ne(tex, null, "%s : vignette produite" % id)
		var img := tex.get_image()
		eq(img.get_width(), 256, "%s : vignette de 256 px de large" % id)
		eq(img.get_height(), 256, "%s : vignette de 256 px de haut" % id)
		# The frame corner must differ from the picture center: the drawing
		# actually painted something inside the polaroid.
		var corner := img.get_pixel(2, 2)
		var center := img.get_pixel(128, 110)
		check(not corner.is_equal_approx(center), "%s : image non uniforme" % id)
	check(PhotoDefs.thumbnail("pile") == PhotoDefs.thumbnail("pile"), "vignette mise en cache")
	done()
