extends ViewTest
## The in-game camera: world candidates filtered by the capture frustum and
## re-expressed in camera space. Since v4 the film captures EVERYTHING it
## frames, the void included, so capture() never returns an empty definition.
## Since v5.1 blocks are captured BY VOLUME, clipped to the frame, the same
## way a placement carves them.


func suite_name() -> String:
	return "photo_capture"


func _anchor_at(pos: Vector3, yaw: float) -> Transform3D:
	return Transform3D(Basis(Vector3.UP, yaw), pos)


func _box(center: Vector3, size: Vector3, color: String) -> Dictionary:
	return {"kind": "box", "xform": Transform3D(Basis(), center), "size": size, "color": color}


## capture() walks scene groups. Under --script the runner's root window is not
## inside the tree yet, so no node can be registered in a group here: the group
## walk itself is covered by tests/smoke_probe.gd, in the running game. What
## this suite can still exercise is the empty tree (the sky shot) and the whole
## pure core.
func _tree() -> SceneTree:
	return Engine.get_main_loop() as SceneTree


func _colors_of(props: Array) -> PackedStringArray:
	var out := PackedStringArray()
	for prop in props:
		out.append(prop.get("color", ""))
	return out


func test_frustum_filter() -> void:
	# Camera at the origin looking down -z: one box in frame, one behind,
	# one beyond the capture depth, one far off to the side.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var candidates := [
		_box(Vector3(0, 1.0, -4), Vector3(1, 1, 1), "erasable"),
		_box(Vector3(0, 1.0, 4), Vector3(1, 1, 1), "erasable"),
		_box(Vector3(0, 1.0, -20), Vector3(1, 1, 1), "erasable"),
		_box(Vector3(9, 1.0, -4), Vector3(1, 1, 1), "erasable"),
	]
	var props := PhotoCapture.props_from(candidates, anchor)
	eq(props.size(), 1, "seule la boite cadree est capturee")
	var prop: Dictionary = props[0]
	eq(prop["kind"], "box", "genre conserve")
	near(prop["pos"].z, -4.0, 0.001, "profondeur exprimee dans l'espace camera")
	near(prop["pos"].y, -0.62, 0.001, "hauteur relative a l'oeil")
	near(prop["pos"].x, 0.0, 0.001, "position laterale exacte")
	# A fully framed object is copied AS IT IS: same size, same place.
	eq(prop["size"], Vector3(1, 1, 1), "taille exacte d'une boite entierement cadree")
	done()


func test_framed_objects_are_exact() -> void:
	# Fidelity of the shot: whatever is entirely in frame comes back at its
	# real size and its real place, with no margin added by the clipping.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var sizes := [Vector3(1, 1, 1), Vector3(0.4, 2.2, 0.4), Vector3(1.3, 1.3, 1.3), Vector3(2.0, 0.3, 2.0)]
	var depths := [2.0, 4.0, 6.0, 9.0]
	for i in sizes.size():
		var size: Vector3 = sizes[i]
		var depth: float = depths[i]
		var center := Vector3(0.2, 1.62, -depth)
		var props := PhotoCapture.props_from([_box(center, size, "wood")], anchor)
		eq(props.size(), 1, "la boite %d est cadree" % i)
		if props.is_empty():
			continue
		eq(props[0]["size"], size, "taille inchangee pour la boite %d" % i)
		near(props[0]["pos"].x, 0.2, 0.001, "abscisse exacte pour la boite %d" % i)
		near(props[0]["pos"].y, 0.0, 0.001, "hauteur exacte pour la boite %d" % i)
		near(props[0]["pos"].z, -depth, 0.001, "profondeur exacte pour la boite %d" % i)
	done()


func test_ground_under_the_feet_is_captured() -> void:
	# THE case that volume clipping fixes. A 12 m platform seen from its
	# surface has its center behind and below the camera, so a center test
	# never copies it, while placing the photo WOULD carve the framed piece
	# away: the player would blow a hole in his own floor. The clip captures
	# the slab of ground that is actually in frame.
	var anchor := _anchor_at(Vector3(0, 1.62, 4), 0.0)
	var ground := _box(Vector3(0, -0.5, 0), Vector3(12, 1, 8), "platform")
	var center_in_camera := anchor.affine_inverse() * Vector3(0, -0.5, 0)
	check(not PhotoMath.point_in_frustum(center_in_camera, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, 0.5, 12.0),
		"le centre de la plateforme est bien hors cadre (l'ancien test le ratait)")
	var props := PhotoCapture.props_from([ground], anchor)
	eq(props.size(), 1, "le sol cadre est capture malgre son centre hors champ")
	var piece: Dictionary = props[0]
	eq(piece["color"], "platform", "c'est bien le sol")
	check(piece["size"].x < 12.0, "le sol est decoupe au cadre, pas copie en entier")
	near(piece["size"].y, 1.0, 0.001, "l'epaisseur du sol est exacte, sans marge ajoutee")
	check(-piece["pos"].z > 0.5, "le morceau capture est devant la camera")
	check(not piece.has("loose"), "un morceau de sol reste solidaire, il ne tombe pas")
	done()


func test_clip_to_frustum() -> void:
	# The pure clip: a wall wider than the frame comes back narrowed to it.
	var identity := Transform3D()
	var far_wall := identity.translated(Vector3(0, 0, -6))
	var piece := PhotoCapture.clip_to_frustum(Vector3(20, 4, 0.5), far_wall)
	check(not piece.is_empty(), "un mur cadre est capture")
	var half := PhotoMath.half_extent_at(6.0, PhotoMath.PHOTO_FOV_DEG)
	check(piece["size"].x < 20.0, "le mur est retreci au cadre")
	between(piece["size"].x, half, half * 2.5, "la largeur retenue est celle de la trame")
	# Out of frame entirely: nothing at all.
	check(PhotoCapture.clip_to_frustum(Vector3(1, 1, 1), identity.translated(Vector3(0, 0, 6))).is_empty(),
		"derriere la camera : rien a capturer")
	check(PhotoCapture.clip_to_frustum(Vector3(1, 1, 1), identity.translated(Vector3(0, 0, -30))).is_empty(),
		"au dela de la portee : rien a capturer")
	done()


func test_yaw_is_relative() -> void:
	# Camera looking +x (yaw -90): a box 4 m along +x is straight ahead.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), -PI * 0.5)
	var props := PhotoCapture.props_from([_box(Vector3(4, 1.62, 0), Vector3(1, 1, 1), "erasable")], anchor)
	eq(props.size(), 1, "la boite face a la camera tournee est capturee")
	near(props[0]["pos"].z, -4.0, 0.001, "devant la camera quelle que soit l'orientation")
	near(props[0]["pos"].x, 0.0, 0.001, "centree dans le cadre")
	eq(props[0]["size"], Vector3(1, 1, 1), "taille conservee quelle que soit l'orientation")
	done()


func test_battery_capture() -> void:
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var candidates := [
		{"kind": "battery", "pos": Vector3(0.5, 0.0, -3), "size": Vector3.ZERO, "color": "battery"},
	]
	var props := PhotoCapture.props_from(candidates, anchor)
	eq(props.size(), 1, "la pile cadree est capturee")
	eq(props[0]["kind"], "battery", "elle reste une pile (donc dupliquee a la pose)")
	near(props[0]["pos"].y, -1.62, 0.001, "position de base conservee")
	done()


func test_too_close_ignored() -> void:
	# The near plane (0.5) keeps the shot from capturing what the player is
	# standing inside of.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var props := PhotoCapture.props_from([_box(Vector3(0, 1.62, -0.2), Vector3(0.3, 0.3, 0.3), "erasable")], anchor)
	eq(props.size(), 0, "trop pres : hors cliche")
	done()


func test_dynamic_registry() -> void:
	var def := {"title": "Cliche", "props": [{"kind": "battery", "pos": Vector3(0, -1, -3), "size": Vector3.ZERO, "color": "battery"}], "backdrop": {}, "erase_depth": 12.0}
	var id := PhotoDefs.register_dynamic(def)
	check(id.begins_with("cliche_"), "id dynamique nomme cliche_N")
	check(not PhotoDefs.get_def(id).is_empty(), "le cliche se lit comme une photo du catalogue")
	eq(PhotoDefs.battery_count(id), 1, "le compte de piles fonctionne sur un cliche")
	check(not PhotoDefs.all_ids().has(id), "le catalogue statique n'est pas pollue")
	PhotoDefs.clear_dynamic()
	check(PhotoDefs.get_def(id).is_empty(), "clear_dynamic purge les cliches")
	done()


func test_loose_rule() -> void:
	# A captured box is loose (it falls when placed) only when the ORIGINAL
	# object is small on EVERY axis: crates fall, walls and grounds do not,
	# whatever size the clipped piece ends up being.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var candidates := [
		_box(Vector3(0, 1.62, -3), Vector3(1.5, 1.5, 1.5), "wood"),
		_box(Vector3(0, 1.62, -4), Vector3(1.7, 1.0, 1.0), "wood"),
		_box(Vector3(0, 1.62, -5), Vector3(1.0, 1.0, 4.0), "wood"),
		_box(Vector3(0, 1.62, -6), Vector3(1.0, 3.5, 0.6), "erasable"),
		{"kind": "battery", "pos": Vector3(0, 1.0, -7), "size": Vector3.ZERO, "color": "battery"},
	]
	var props := PhotoCapture.props_from(candidates, anchor)
	eq(props.size(), 5, "les cinq candidats sont cadres")
	check(props[0].get("loose", false), "cube de 1.5 m : objet libre")
	check(not props[1].has("loose"), "1.7 m sur un axe : solidaire")
	check(not props[2].has("loose"), "planche de 4 m : solidaire")
	check(not props[3].has("loose"), "pan de mur de 3.5 m de haut : solidaire")
	check(not props[4].has("loose"), "une pile n'a pas de cle loose (elle est toujours physique)")
	near(PhotoCapture.LOOSE_MAX_EXTENT, 1.6, 0.001, "seuil d'objet libre a 1.6 m")
	done()


func test_prop_cap() -> void:
	# Forty framed boxes, capped at 32, closest kept first: a shot of a dense
	# level stays a placeable photo instead of a scene dump.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var candidates: Array = []
	for i in 40:
		candidates.append(_box(Vector3(0, 1.62, -1.0 - i * 0.25), Vector3(0.5, 0.5, 0.5), "stone"))
	var props := PhotoCapture.props_from(candidates, anchor)
	eq(props.size(), PhotoCapture.MAX_PROPS, "plafond de 32 props")
	for i in range(1, props.size()):
		check(-props[i]["pos"].z >= -props[i - 1]["pos"].z, "props tries par profondeur croissante")
	check(-props[0]["pos"].z < -props[props.size() - 1]["pos"].z, "les plus proches sont gardes, les lointains coupes")
	done()


func test_every_family_captured() -> void:
	# The film sees both families of subject: blocks of every color (permanent
	# platforms as well as lavender ones) and batteries. Cages are NOT a family
	# any more: bars are a lattice the lens goes through, so what the film keeps
	# of a cage is whatever stands behind its bars.
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var candidates := [
		_box(Vector3(0, -1, -8), Vector3(6, 1, 6), "platform"),
		_box(Vector3(1, 1, -4), Vector3(1.2, 1.2, 1.2), "erasable"),
		{"kind": "battery", "pos": Vector3(0.5, 0, -3), "size": Vector3.ZERO, "color": "battery"},
		_box(Vector3(0, 1, 6), Vector3(1, 1, 1), "wood"),
	]
	var props := PhotoCapture.props_from(candidates, anchor)
	eq(props.size(), 3, "trois sujets cadres, le bloc derriere la camera exclu")
	var colors := _colors_of(props)
	check(colors.has("platform"), "la plateforme non lavande est capturee")
	check(colors.has("erasable"), "le bloc lavande est capture")
	check(not colors.has("wood"), "ce qui est derriere la camera reste hors du cliche")
	var kinds := PackedStringArray()
	for prop in props:
		kinds.append(prop["kind"])
	check(kinds.has("battery"), "la pile est capturee comme une pile")
	near(props[0]["pos"].z, -3.0, 0.001, "le sujet le plus proche vient en tete")
	done()


func test_cage_is_not_a_capturable_kind() -> void:
	# A caged battery must come out of the film as a battery and nothing else.
	# If a cage were copied as a solid box, the copy would materialize AROUND
	# the copied battery and seal it in: the one puzzle a steel cage exists for
	# would be unsolvable. Feeding a cage-shaped candidate now yields a clipped
	# box like any other volume, and the scene never produces one (the group
	# walk in capture() does not read cages at all: see smoke_probe).
	var anchor := _anchor_at(Vector3(0, 1.62, 0), 0.0)
	var props := PhotoCapture.props_from([
		{"kind": "battery", "pos": Vector3(0, 0, -5), "size": Vector3.ZERO, "color": "battery"},
	], anchor)
	eq(props.size(), 1, "seule la pile en cage est sur la pellicule")
	eq(props[0]["kind"], "battery", "et elle en sort comme une pile, libre")
	done()


func test_empty_capture_is_valid() -> void:
	# Framing nothing but the sky is not a failure: the shot is an empty photo
	# of sky, and placed it pierces the world.
	var tree := _tree()
	if tree == null:
		fail("aucun SceneTree disponible pour la sonde de capture")
		done()
		return
	var def := PhotoCapture.capture(_anchor_at(Vector3(0, 1.62, 0), 0.0), tree)
	check(not def.is_empty(), "un cliche vide reste une definition valide")
	check(def.get("title", "") != "", "le cliche vide a un titre")
	eq(def["props"].size(), 0, "aucun prop sur le cliche du ciel")
	near(def["backdrop"]["depth"], 36.0, 0.001, "fond peint loin derriere, a 36 m")
	near(def["erase_depth"], PhotoCapture.CAPTURE_DEPTH, 0.001, "le cliche efface juste ce qu'il a capture")
	check(def["backdrop"]["depth"] > def["erase_depth"] * 2.5,
		"le ciel du cliche est un lointain, pas un mur au bout du bras")
	check(Palette.has_color(def["backdrop"]["top"]), "couleur haute du fond connue")
	check(Palette.has_color(def["backdrop"]["bottom"]), "couleur basse du fond connue")
	done()
