extends GoalTest
## The imported character must keep sampling the role-specific photographic
## atlas on every visible kit surface. This catches a missing asset as well as a
## later material refactor that silently falls back to the old flat colours.


func suite_name() -> String:
	return "CharacterModels"


## Loads an optional atlas. Returns null when assets/ is absent, which is a
## supported configuration and not a failure: ResourceLoader.exists() first,
## because load() on a missing path is a runtime error that would abort the whole
## test method silently.
func _optional_atlas(path: String) -> Texture2D:
	if not ResourceLoader.exists(path):
		return null
	return load(path) as Texture2D


func test_role_specific_kit_textures() -> void:
	var keeper_texture := _optional_atlas("res://assets/textures/kits/keeper_kit_albedo.png")
	var shooter_texture := _optional_atlas("res://assets/textures/kits/outfield_kit_albedo.png")
	var keeper_front := _optional_atlas("res://assets/textures/kits/keeper_front_albedo.png")
	var shooter_front := _optional_atlas("res://assets/textures/kits/outfield_front_albedo.png")

	# assets/ is optional by the project's core rule, so its absence switches
	# this suite from "the atlas is sampled correctly" to "the procedural
	# fallback still dresses both figures". Asserting the atlas unconditionally
	# would make the unit gate fail in a configuration that is meant to work.
	if keeper_texture == null or shooter_texture == null or keeper_front == null or shooter_front == null:
		check(keeper_texture == null and shooter_texture == null
			and keeper_front == null and shooter_front == null,
			"les quatre atlas sont absents ensemble, jamais un seul")
		_check_fallback(CharacterModels.ROLE_KEEPER, "gardien")
		_check_fallback(CharacterModels.ROLE_SHOOTER, "joueur")
		done()
		return

	check(keeper_texture.get_width() >= 1024 and keeper_texture.get_height() >= 1024,
		"atlas du gardien assez detaille")
	check(shooter_texture.get_width() >= 1024 and shooter_texture.get_height() >= 1024,
		"atlas du joueur assez detaille")
	check(keeper_front.get_width() >= 1024 and keeper_front.get_height() >= 1024,
		"devant du gardien assez detaille")
	check(shooter_front.get_width() >= 1024 and shooter_front.get_height() >= 1024,
		"devant du joueur assez detaille")

	_check_figure(CharacterModels.ROLE_KEEPER, keeper_texture, keeper_front, 3, "gardien")
	_check_figure(CharacterModels.ROLE_SHOOTER, shooter_texture, shooter_front, 2, "joueur")
	done()


func test_keeper_face_texture_is_role_specific() -> void:
	var expected := _optional_atlas(
		"res://assets/textures/characters/keeper_skin_albedo.png")
	if expected == null:
		check(CharacterModels.keeper_skin_texture() == null,
			"la texture de visage reste optionnelle sans assets")
		done()
		return

	var keeper := CharacterModels.build(CharacterModels.ROLE_KEEPER)
	var shooter := CharacterModels.build(CharacterModels.ROLE_SHOOTER)
	check(keeper != null and shooter != null, "les deux figures sont construites")
	if keeper != null:
		check(_skin_texture_of(keeper) == expected,
			"le gardien utilise l'atlas de visage photorealiste")
		keeper.free()
	if shooter != null:
		check(_skin_texture_of(shooter) == null,
			"le joueur conserve son materiau de peau sans visage de gardien")
		shooter.free()
	done()


## THE TRAP the shaping had to clear, asserted directly rather than argued about.
##
## The kit is a shell modelled 6 mm outside the skin. The shaping moves both, so
## the only thing that can put the body through the shirt is the map CLOSING that
## gap somewhere. This walks a grid over the whole figure, offsets each sample by
## the shell's own 6 mm along six directions, and checks the pair is still at
## least 4.5 mm apart afterwards. It is the shell clearance itself, measured, and
## it holds for every surface at once because every surface goes through this one
## function.
func test_shaping_keeps_the_kit_off_the_skin() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_SHOOTER):
		check(CharacterModels.build(CharacterModels.ROLE_SHOOTER) == null,
			"sans modele il n'y a rien a deformer")
		done()
		return
	# build() is what resolves the shaping against the rest skeleton.
	var figure := CharacterModels.build(CharacterModels.ROLE_SHOOTER)
	check(figure != null, "figure construite avant de mesurer la deformation")
	if figure == null:
		done()
		return
	figure.free()

	# The real shell, on the real body: every vertex of the imported mesh, offset
	# along its OWN normal by the 6 mm the kit is modelled at. Sampled on the raw
	# file because that is the bind pose the shaping reads.
	var raw := _raw_mesh()
	check(raw != null, "le maillage source est lisible")
	if raw == null:
		done()
		return
	var shell := 0.006
	var worst := 1.0
	var worst_at := Vector3.ZERO
	var sampled := 0
	for surface in raw.get_surface_count():
		var arrays := raw.surface_get_arrays(surface)
		if arrays.size() <= Mesh.ARRAY_NORMAL or arrays[Mesh.ARRAY_NORMAL] == null:
			continue
		var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		for i in vertices.size():
			var p := vertices[i]
			var gap := CharacterModels._shape(p).distance_to(
				CharacterModels._shape(p + normals[i] * shell)) / shell
			sampled += 1
			if gap < worst:
				worst = gap
				worst_at = p
	check(sampled > 10000, "toute la peau et toute la tenue sont echantillonnees (%d)" % sampled)
	# Not 1.0: the shaping narrows the hips and the seat on PURPOSE, so a shell
	# offset lying along a direction that narrows comes back shorter, and that is
	# the shirt following the body rather than a fault. What it may never do is
	# COLLAPSE, because that is the body through the shirt.
	#
	# The floor is set against the real budget rather than against taste. The shell
	# is modelled 6 mm out; at 0.80 that is still 4.8 mm, and the materials add
	# another 10 mm on top of it at draw time (`_KIT_GROW` 6 mm out, `_SKIN_SHRINK`
	# 4 mm in), which is what absorbs the skinning drift of a hard shoulder
	# rotation. The worst the shipped shaping actually reaches is 0.877, on a
	# finger, so this leaves real margin and is not a number tuned to pass.
	check(worst >= 0.80,
		"la coque du maillot garde son jeu sur la peau partout (pire %.3f de l'ecart modelise en %s)"
			% [worst, str(worst_at)])
	done()


## The shaping may never turn the body inside out. A negative Jacobian determinant
## is a fold, and a fold is geometry passing through itself: the one failure this
## map can have that no amount of shader clearance can rescue. Checked over the
## whole box the figure lives in, empty space included, because a fold in the air
## beside a knee today is a fold in the knee the next time a gain is nudged.
func test_shaping_never_folds_the_body() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_SHOOTER):
		check(CharacterModels.build(CharacterModels.ROLE_SHOOTER) == null,
			"sans modele il n'y a rien a replier")
		done()
		return
	var figure := CharacterModels.build(CharacterModels.ROLE_SHOOTER)
	check(figure != null, "figure construite avant de mesurer le repliement")
	if figure == null:
		done()
		return
	figure.free()

	var step := 0.0015
	var worst := 1.0e9
	var worst_at := Vector3.ZERO
	for ix in 17:
		for iy in 31:
			for iz in 11:
				var p := Vector3(
					lerpf(-0.60, 0.60, float(ix) / 16.0),
					lerpf(-0.05, 1.85, float(iy) / 30.0),
					lerpf(-0.16, 0.36, float(iz) / 10.0))
				var here := CharacterModels._shape(p)
				var jacobian := Basis(
					(CharacterModels._shape(p + Vector3(step, 0.0, 0.0)) - here) / step,
					(CharacterModels._shape(p + Vector3(0.0, step, 0.0)) - here) / step,
					(CharacterModels._shape(p + Vector3(0.0, 0.0, step)) - here) / step)
				var volume := jacobian.determinant()
				if volume < worst:
					worst = volume
					worst_at = p
	check(worst > 0.25,
		"la mise en forme ne replie le corps nulle part (pire volume local %.3f en %s)"
			% [worst, str(worst_at)])
	done()


## The imported mesh as the file ships it, or null with no model installed.
func _raw_mesh() -> Mesh:
	var skeleton := _rest_skeleton()
	if skeleton == null:
		return null
	var root := _rest_root(skeleton)
	var out: Mesh = null
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh != null:
			out = mesh_instance.mesh
			break
	if root != null:
		root.free()
	return out


## The invariant the whole shaping rests on: it moves x and z and never y. Every
## height this module depends on (the shirt hem, the collar band, the sock top and
## above all the sole the figure stands on) is therefore untouched by it.
func test_shaping_never_moves_a_vertex_in_y() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_SHOOTER):
		check(CharacterModels.metrics(CharacterModels.ROLE_SHOOTER).is_empty(),
			"sans modele il n'y a pas de metriques a preserver")
		done()
		return
	var figure := CharacterModels.build(CharacterModels.ROLE_SHOOTER)
	check(figure != null, "figure construite avant de mesurer l'invariant")
	if figure == null:
		done()
		return
	figure.free()

	var worst := 0.0
	for ix in 17:
		for iy in 31:
			for iz in 11:
				var p := Vector3(
					lerpf(-0.60, 0.60, float(ix) / 16.0),
					lerpf(-0.05, 1.85, float(iy) / 30.0),
					lerpf(-0.16, 0.36, float(iz) / 10.0))
				worst = maxf(worst, absf(CharacterModels._shape(p).y - p.y))
	check(worst == 0.0, "la mise en forme ne deplace aucun sommet en hauteur (pire %f)" % worst)
	done()


## What the shaping is FOR: shoulders clearly wider than hips. That single ratio
## is what an eye reads as a man, and the source mesh had it the wrong way round
## (0.24 across the shoulders against 0.23 across the hips). Measured on the mesh
## that is actually drawn, in the model's own units.
func test_the_figures_are_built_like_men() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_KEEPER):
		check(CharacterModels.build(CharacterModels.ROLE_KEEPER) == null,
			"sans modele la silhouette est celle de Meshes.humanoid_parts()")
		done()
		return
	var figure := CharacterModels.build(CharacterModels.ROLE_KEEPER)
	check(figure != null, "figure construite avant de mesurer la silhouette")
	if figure == null:
		done()
		return
	var shoulders := _half_width(figure, 1.42, 1.48)
	var hips := _half_width(figure, 0.78, 0.94)
	figure.free()
	check(shoulders > 0.0 and hips > 0.0, "les deux bandes portent de la geometrie")
	check(shoulders > hips * 1.20,
		"les epaules sont nettement plus larges que les hanches (%.3f contre %.3f)"
			% [shoulders, hips])
	done()


## Both figures now carry the same oversized head, not just the keeper.
##
## `pose()` writes it on the head bone and refuses to touch a figure that is not
## in the live tree, and a suite runs inside `SceneTree._initialize` where the
## root window is not in its own tree yet, so there is no honest way to drive a
## real pose from here. What CAN be pinned down here is the thing that was
## actually wrong: the scale was chosen by role, and one branch of that choice was
## the literal 1.0 the shooter was stuck on. There is now a single constant and
## both names resolve to it. The rendered result was checked in an image.
func test_both_figures_get_the_same_big_head() -> void:
	check(CharacterModels.HEAD_SCALE == CharacterModels.KEEPER_HEAD_SCALE,
		"le gardien et le tireur partagent une seule echelle de tete")
	check(CharacterModels.HEAD_SCALE >= 2.0,
		"la tete est agrandie au moins deux fois")
	done()


## The keeper's arms are no longer drawn as rubber. `Keeper` hands over a chain
## stretched by up to 30 percent (its MAX_STRETCH), and what `_relax_arms` makes
## of it has to be a believable arm: each segment within `_ARM_STRETCH_MAX` of its
## own rest length, the shoulder girdle sliding no further than `_GIRDLE_GIVE` to
## pay for the difference, and the glove following the wrist it hangs off.
##
## Driven on the private helper rather than through `pose()` for the reason given
## above, and that is the better test anyway: it is the arithmetic itself, on the
## real rest skeleton, with no renderer in between.
func test_a_stretched_arm_is_drawn_as_an_arm() -> void:
	var skeleton := _rest_skeleton()
	if skeleton == null:
		check(not CharacterModels.available(CharacterModels.ROLE_KEEPER),
			"sans modele le gardien garde son corps procedural")
		done()
		return
	var rest_upper := _rest_span(skeleton, "upperarm01.L", "lowerarm01.L")
	var rest_fore := _rest_span(skeleton, "lowerarm01.L", "wrist.L")
	check(rest_upper > 0.1 and rest_fore > 0.1, "les os du bras ont une longueur mesurable")

	var ceiling := CharacterModels._ARM_STRETCH_MAX
	var stretched := _arm_joints(skeleton, 1.30)
	var girdle: Dictionary = CharacterModels._relax_arms(skeleton, stretched)
	for side in ["l", "r"]:
		var shoulder: Vector3 = stretched["shoulder_%s" % side]
		var elbow: Vector3 = stretched["elbow_%s" % side]
		var wrist: Vector3 = stretched["wrist_%s" % side]
		var glove: Vector3 = stretched["glove_%s" % side]
		check(shoulder.distance_to(elbow) <= rest_upper * ceiling + 0.001,
			"cote %s : le bras dessine reste un bras (%.3f pour un os de %.3f)"
				% [side, shoulder.distance_to(elbow), rest_upper])
		check(elbow.distance_to(wrist) <= rest_fore * ceiling + 0.001,
			"cote %s : l'avant bras dessine reste un avant bras (%.3f pour un os de %.3f)"
				% [side, elbow.distance_to(wrist), rest_fore])
		# The hand is never stretched, it only follows its wrist.
		near(wrist.distance_to(glove), 0.07, 0.001,
			"cote %s : la main garde sa taille, elle suit le poignet" % side)
	check(girdle.size() == 2, "les deux ceintures scapulaires ont paye (%d)" % girdle.size())
	for bone in girdle:
		var slide: Vector3 = girdle[bone]
		check(slide.length() <= CharacterModels._GIRDLE_GIVE + 0.0001,
			"%s : l'epaule ne glisse que de ce qu'une ceinture scapulaire donne (%.3f)"
				% [bone, slide.length()])
		check(slide.length() > 0.001, "%s : la ceinture a bien encaisse quelque chose" % bone)

	# And the correction only ever runs at the limit. An arm the caller solved
	# inside its own rest length must come out untouched, to the millimetre,
	# because that is every ordinary frame of the game.
	var easy := _arm_joints(skeleton, 0.85)
	var before: Vector3 = easy["shoulder_l"]
	var before_elbow: Vector3 = easy["elbow_l"]
	var quiet: Dictionary = CharacterModels._relax_arms(skeleton, easy)
	check(quiet.is_empty(), "un bras a l'aise ne fait glisser aucune epaule")
	near_vec(easy["shoulder_l"], before, 0.000001,
		"un bras a l'aise garde l'epaule exactement ou l'appelant l'a mise")
	near_vec(easy["elbow_l"], before_elbow, 0.000001,
		"un bras a l'aise garde le coude exactement ou l'appelant l'a mis")
	# Free the WHOLE instantiated scene, not the skeleton's immediate parent. The
	# imported hierarchy is player [Node3D] -> GoalPlayer [Node3D] -> Skeleton3D,
	# so freeing get_parent() left the instantiated root alive for the rest of the
	# process and Godot reported it as a leaked Node3D under --verbose.
	var root := _rest_root(skeleton)
	if root != null:
		root.free()
	done()


## The imported rest skeleton, out of the tree, or null with no model installed.
## Only the rest pose is read, and that needs no tree.
func _rest_skeleton() -> Skeleton3D:
	var path := "res://assets/models/player.glb"
	if not ResourceLoader.exists(path):
		return null
	var scene := load(path) as PackedScene
	if scene == null:
		return null
	var root := scene.instantiate()
	var found := _find_skeleton(root)
	if found == null:
		root.free()
	return found


## The node `_rest_skeleton()` actually instantiated, which is what has to be
## freed: the skeleton sits two levels down (player -> GoalPlayer -> Skeleton3D),
## so freeing its immediate parent orphans the top of the scene forever. Every
## caller of `_rest_skeleton()` must hand its return value to this and free the
## result, and the ownership is stated here once rather than re-derived on site.
func _rest_root(node: Node) -> Node:
	var root := node
	while root != null and root.get_parent() != null:
		root = root.get_parent()
	return root


func _find_skeleton(node: Node) -> Skeleton3D:
	if node is Skeleton3D:
		return node as Skeleton3D
	for child in node.get_children():
		var hit := _find_skeleton(child)
		if hit != null:
			return hit
	return null


func _rest_span(skeleton: Skeleton3D, from_bone: String, to_bone: String) -> float:
	var a := skeleton.find_bone(from_bone)
	var b := skeleton.find_bone(to_bone)
	if a < 0 or b < 0:
		return 0.0
	return skeleton.get_bone_global_rest(a).origin.distance_to(
		skeleton.get_bone_global_rest(b).origin)


## Both arms reaching sideways and down with every segment `stretch` times its own
## rest length, in the skeleton's own frame. At 1.30 it is the worst case
## `Keeper.MAX_STRETCH` allows, which is exactly what this module has to survive.
func _arm_joints(skeleton: Skeleton3D, stretch: float) -> Dictionary:
	var upper := _rest_span(skeleton, "upperarm01.L", "lowerarm01.L") * stretch
	var fore := _rest_span(skeleton, "lowerarm01.L", "wrist.L") * stretch
	var out: Dictionary = {}
	for side in [-1.0, 1.0]:
		var key := "l" if side < 0.0 else "r"
		var reach := Vector3(side, -0.35, 0.1).normalized()
		var shoulder := Vector3(side * 0.181, 1.449, 0.016)
		var elbow := shoulder + reach * upper
		var wrist := elbow + reach * fore
		out["shoulder_%s" % key] = shoulder
		out["elbow_%s" % key] = elbow
		out["wrist_%s" % key] = wrist
		out["glove_%s" % key] = wrist + reach * 0.07
	return out


## Half width of the drawn mesh over one height band, in the model's own units.
func _half_width(figure: Node3D, low: float, high: float) -> float:
	var out := 0.0
	for node in figure.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null:
			continue
		for surface in mesh_instance.mesh.get_surface_count():
			var arrays := mesh_instance.mesh.surface_get_arrays(surface)
			if arrays.size() <= Mesh.ARRAY_VERTEX or arrays[Mesh.ARRAY_VERTEX] == null:
				continue
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			for v in vertices:
				if v.y >= low and v.y <= high:
					out = maxf(out, absf(v.x))
	return out


func _skin_texture_of(figure: Node3D) -> Texture2D:
	for node in figure.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null:
			continue
		for surface in mesh_instance.mesh.get_surface_count():
			var source := mesh_instance.mesh.surface_get_material(surface)
			if source == null or source.resource_name != CharacterModels.SURFACE_FACE:
				continue
			var material := mesh_instance.get_surface_override_material(surface) as StandardMaterial3D
			return material.albedo_texture if material != null else null
	return null


## Without assets/ there is no glTF either, so the contract for this module is
## simply that it says so HONESTLY and cheaply: available() reports false and
## build() returns null instead of erroring or handing back a half built figure.
## Dressing the procedural body is Keeper's and Shooter's job, not this module's,
## which is why nothing here asserts a colour in this configuration.
func _check_fallback(role: int, label: String) -> void:
	check(not CharacterModels.available(role),
		"%s : available() doit etre faux sans modele" % label)
	var figure := CharacterModels.build(role)
	check(figure == null,
		"%s : build() doit rendre null sans modele, pas une figure vide" % label)
	if figure != null:
		figure.free()


func _check_figure(role: int, expected: Texture2D, expected_front: Texture2D,
		minimum: int, label: String) -> void:
	var figure := CharacterModels.build(role)
	check(figure != null, "%s construit" % label)
	if figure == null:
		return
	var textured := 0
	var front_textured := 0
	var sampled := 0
	var black := 0
	var image := expected.get_image() if expected != null else null
	for node in figure.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance := node as MeshInstance3D
		if mesh_instance.mesh == null:
			continue
		for surface in mesh_instance.mesh.get_surface_count():
			var source := mesh_instance.mesh.surface_get_material(surface)
			var material := mesh_instance.get_surface_override_material(surface) as StandardMaterial3D
			if source != null and source.resource_name == CharacterModels.SURFACE_JERSEY_FRONT:
				check(material != null and material.albedo_texture == expected_front,
					"%s : devant sans numero applique au torse avant" % label)
				front_textured += 1
			if source != null and source.resource_name == CharacterModels.SURFACE_JERSEY_BACK:
				check(material != null and material.albedo_texture == expected,
					"%s : maillot numerote applique au dos" % label)
			if material != null and material.albedo_texture == expected:
				textured += 1
				if image == null:
					continue
				var arrays := mesh_instance.mesh.surface_get_arrays(surface)
				var uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
				for uv in uvs:
					var mapped := Vector2(
						uv.x * material.uv1_scale.x + material.uv1_offset.x,
						uv.y * material.uv1_scale.y + material.uv1_offset.y)
					var x := clampi(int(mapped.x * image.get_width()), 0, image.get_width() - 1)
					var y := clampi(int(mapped.y * image.get_height()), 0, image.get_height() - 1)
					var pixel := image.get_pixel(x, y)
					if maxf(pixel.r, maxf(pixel.g, pixel.b)) < 0.03:
						black += 1
					sampled += 1
	check(textured >= minimum,
		"%s : atlas applique aux surfaces de tenue (%d trouvees)" % [label, textured])
	check(front_textured == 1,
		"%s : exactement une surface de torse avant" % label)
	check(sampled > 0, "%s : UV de tenue echantillonnees" % label)
	if sampled > 0:
		check(float(black) / float(sampled) < 0.10,
			"%s : moins de 10 %% des sommets de tenue tombent sur du noir (%d/%d)"
				% [label, black, sampled])
	figure.free()
