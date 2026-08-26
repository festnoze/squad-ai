extends GoalTest
## Suite for `Meshes`.
##
## Procedural geometry fails silently: a mesh with a flipped face, a missing
## normal or a UV outside its atlas cell still loads, still renders, and only
## looks slightly wrong on screen at three in the morning. So the checks here go
## after the invariants that a human eye would miss:
##
##   * exact vertex and triangle counts, which pin the truncated icosahedron
##     down to the topology it claims to have,
##   * every ball vertex exactly on the sphere, because the projection step is
##     the one place a subdivision bug hides,
##   * every ball UV inside its own atlas cell, at the radius `Tex` paints,
##   * outward winding under Godot's CLOCKWISE front face rule, which is the
##     single most common procedural mesh bug in this engine,
##   * normals and tangents present and unit length,
##   * no NaN anywhere, in any mesh.


func suite_name() -> String:
	return "Meshes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

func vertices_of(mesh: ArrayMesh, surface: int = 0) -> PackedVector3Array:
	if mesh == null or mesh.get_surface_count() <= surface:
		return PackedVector3Array()
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays[Mesh.ARRAY_VERTEX] == null:
		return PackedVector3Array()
	return arrays[Mesh.ARRAY_VERTEX]


func normals_of(mesh: ArrayMesh, surface: int = 0) -> PackedVector3Array:
	if mesh == null or mesh.get_surface_count() <= surface:
		return PackedVector3Array()
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays[Mesh.ARRAY_NORMAL] == null:
		return PackedVector3Array()
	return arrays[Mesh.ARRAY_NORMAL]


func uvs_of(mesh: ArrayMesh, surface: int = 0) -> PackedVector2Array:
	if mesh == null or mesh.get_surface_count() <= surface:
		return PackedVector2Array()
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays[Mesh.ARRAY_TEX_UV] == null:
		return PackedVector2Array()
	return arrays[Mesh.ARRAY_TEX_UV]


func tangents_of(mesh: ArrayMesh, surface: int = 0) -> PackedFloat32Array:
	if mesh == null or mesh.get_surface_count() <= surface:
		return PackedFloat32Array()
	var arrays: Array = mesh.surface_get_arrays(surface)
	if arrays[Mesh.ARRAY_TANGENT] == null:
		return PackedFloat32Array()
	return arrays[Mesh.ARRAY_TANGENT]


## True when every position, normal and UV of every surface is finite.
func mesh_is_finite(mesh: ArrayMesh) -> bool:
	if mesh == null:
		return false
	for s in mesh.get_surface_count():
		for p in vertices_of(mesh, s):
			if not p.is_finite():
				return false
		for n in normals_of(mesh, s):
			if not n.is_finite():
				return false
		for uv in uvs_of(mesh, s):
			if not uv.is_finite():
				return false
		for t in tangents_of(mesh, s):
			if not is_finite(t):
				return false
	return true


## Checks the usual health of one surface: normals present and unit length,
## tangents present, four floats per vertex, unit length and not parallel to
## the normal. A material with a normal map needs all of that.
func check_surface_health(mesh: ArrayMesh, label: String, surface: int = 0) -> void:
	var verts := vertices_of(mesh, surface)
	var norms := normals_of(mesh, surface)
	var tans := tangents_of(mesh, surface)
	check(verts.size() > 0, "%s : surface vide" % label)
	eq(norms.size(), verts.size(), "%s : une normale par sommet" % label)
	eq(tans.size(), verts.size() * 4, "%s : quatre flottants de tangente par sommet" % label)

	var worst_normal := 0.0
	var worst_tangent := 0.0
	var worst_align := 0.0
	for i in norms.size():
		worst_normal = maxf(worst_normal, absf(norms[i].length() - 1.0))
	for i in verts.size():
		if tans.size() < (i + 1) * 4:
			break
		var t := Vector3(tans[i * 4], tans[i * 4 + 1], tans[i * 4 + 2])
		worst_tangent = maxf(worst_tangent, absf(t.length() - 1.0))
		if i < norms.size():
			worst_align = maxf(worst_align, absf(t.normalized().dot(norms[i])))
	check(worst_normal < 1e-3, "%s : normales unitaires (ecart max %f)" % [label, worst_normal])
	check(worst_tangent < 1e-3, "%s : tangentes unitaires (ecart max %f)" % [label, worst_tangent])
	check(worst_align < 0.99, "%s : tangente non colineaire a la normale (max %f)" % [label, worst_align])

	# Winding, on every mesh and not just the ball. Godot's front faces are
	# CLOCKWISE, so the front normal of a triangle read in array order is the
	# NEGATED right hand cross product. It must agree with the normal the
	# builder wrote, otherwise that face is inside out and will be culled away
	# at exactly the angle nobody tests from.
	var flipped := 0
	for t in int(verts.size() / 3):
		var a := verts[t * 3]
		var b := verts[t * 3 + 1]
		var c := verts[t * 3 + 2]
		var cross := (b - a).cross(c - a)
		if cross.length() < 1e-9:
			continue  # A pole triangle of a capped tube has zero area.
		if norms.size() < t * 3 + 3:
			break
		var front := -cross.normalized()
		var written := (norms[t * 3] + norms[t * 3 + 1] + norms[t * 3 + 2]).normalized()
		if front.dot(written) < 0.5:
			flipped += 1
	eq(flipped, 0, "%s : aucune face a l'envers" % label)


# ---------------------------------------------------------------------------
# The ball
# ---------------------------------------------------------------------------

func test_ball_counts() -> void:
	# 12 pentagons of 5 corner triangles plus 20 hexagons of 6, each corner
	# triangle split into 4^level. The mesh is not indexed, so a vertex per
	# triangle corner.
	for level in [0, 1, 2]:
		var expected_tris := 180 * int(pow(4.0, float(level)))
		var mesh := Meshes.ball_mesh(level)
		eq(mesh.get_surface_count(), 1, "ballon niveau %d : une seule surface" % level)
		var verts := vertices_of(mesh)
		eq(verts.size(), expected_tris * 3, "ballon niveau %d : nombre de sommets" % level)
		eq(verts.size() % 3, 0, "ballon niveau %d : sommets multiples de trois" % level)
		var arrays: Array = mesh.surface_get_arrays(0)
		check(arrays[Mesh.ARRAY_INDEX] == null, "ballon niveau %d : maillage non indexe" % level)
		eq(mesh.surface_get_primitive_type(0), Mesh.PRIMITIVE_TRIANGLES, "ballon niveau %d : triangles" % level)
	done()


func test_ball_vertices_on_sphere() -> void:
	var radius: float = Field.BALL_RADIUS
	var mesh := Meshes.ball_mesh(2)
	var verts := vertices_of(mesh)
	check(verts.size() > 0, "ballon : des sommets")
	var worst := 0.0
	for p in verts:
		worst = maxf(worst, absf(p.length() - radius))
	check(worst < 1e-5, "ballon : tous les sommets sur la sphere (ecart max %f)" % worst)

	# A faceted ball must still be inscribed, never bulging past the radius.
	var flat := Meshes.ball_mesh(0)
	var worst_flat := 0.0
	for p in vertices_of(flat):
		worst_flat = maxf(worst_flat, absf(p.length() - radius))
	check(worst_flat < 1e-5, "ballon facette : sommets sur la sphere (ecart max %f)" % worst_flat)
	near(mesh.get_aabb().size.x, radius * 2.0, 1e-4, "ballon : diametre de la boite englobante")
	done()


func test_ball_uv_atlas() -> void:
	var cols: int = Meshes.BALL_ATLAS_COLS
	var cell_side := 1.0 / float(cols)
	var mesh := Meshes.ball_mesh(1)
	var uvs := uvs_of(mesh)
	eq(uvs.size(), vertices_of(mesh).size(), "ballon : une UV par sommet")

	var used: Dictionary = {}
	var worst_penta := 0.0
	var worst_hexa := 0.0
	var outside := 0
	for uv in uvs:
		if uv.x < 0.0 or uv.x > 1.0 or uv.y < 0.0 or uv.y > 1.0:
			outside += 1
			continue
		var col := mini(int(uv.x * float(cols)), cols - 1)
		var row := mini(int(uv.y * float(cols)), cols - 1)
		var cell := row * cols + col
		used[cell] = true
		var centre := Vector2((float(col) + 0.5) * cell_side, (float(row) + 0.5) * cell_side)
		var r := (uv - centre).length() / cell_side
		if cell < Meshes.BALL_PENTAGON_COUNT:
			worst_penta = maxf(worst_penta, r)
		else:
			worst_hexa = maxf(worst_hexa, r)

	eq(outside, 0, "ballon : aucune UV hors de [0, 1]")
	eq(used.size(), Meshes.BALL_PANEL_COUNT, "ballon : trente deux cellules d'atlas occupees")
	var max_cell := 0
	for cell in used.keys():
		max_cell = maxi(max_cell, int(cell))
	check(max_cell < Meshes.BALL_PANEL_COUNT, "ballon : aucune UV dans les cellules inutilisees")
	# The two radii Tex paints, and the 1 : 1.175 ratio that keeps the printed
	# seam the same width on every panel.
	near(worst_penta, Meshes.BALL_PENTAGON_UV_RADIUS, 1e-3, "ballon : rayon UV des pentagones")
	near(worst_hexa, Meshes.BALL_HEXAGON_UV_RADIUS, 1e-3, "ballon : rayon UV des hexagones")
	done()


func test_ball_normals_and_tangents() -> void:
	var mesh := Meshes.ball_mesh(2)
	check_surface_health(mesh, "ballon")
	var verts := vertices_of(mesh)
	var norms := normals_of(mesh)
	# On a sphere centred on the origin the normal IS the direction of the
	# vertex, so anything else is a smoothing bug.
	var worst := 1.0
	for i in mini(verts.size(), norms.size()):
		worst = minf(worst, norms[i].dot(verts[i].normalized()))
	check(worst > 0.9999, "ballon : normales exactement radiales (pire produit %f)" % worst)
	done()


func test_ball_winding_is_outward() -> void:
	# Godot's front faces are CLOCKWISE, so the front normal of a triangle read
	# in array order is the NEGATED right hand cross product. Every ball face
	# must have that pointing away from the centre.
	var mesh := Meshes.ball_mesh(1)
	var verts := vertices_of(mesh)
	var bad := 0
	var degenerate := 0
	for t in int(verts.size() / 3):
		var a := verts[t * 3]
		var b := verts[t * 3 + 1]
		var c := verts[t * 3 + 2]
		var cross := (b - a).cross(c - a)
		if cross.length() < 1e-12:
			degenerate += 1
			continue
		var outward := -cross.normalized()
		var centroid := (a + b + c) / 3.0
		if outward.dot(centroid.normalized()) < 0.9:
			bad += 1
	eq(bad, 0, "ballon : toutes les faces tournees vers l'exterieur")
	eq(degenerate, 0, "ballon : aucun triangle degenere")
	done()


func test_ball_cache_and_no_nan() -> void:
	Meshes.clear_cache()
	var first := Meshes.ball_mesh(1)
	var second := Meshes.ball_mesh(1)
	check(first == second, "ballon : le cache renvoie la meme instance")
	check(mesh_is_finite(first), "ballon : aucun NaN")
	Meshes.clear_cache()
	var third := Meshes.ball_mesh(1)
	check(third != first, "ballon : clear_cache force une reconstruction")
	# Out of range subdivisions are clamped, never crash.
	check(mesh_is_finite(Meshes.ball_mesh(-3)), "ballon : subdivision negative bornee")
	check(mesh_is_finite(Meshes.ball_mesh(9)), "ballon : subdivision excessive bornee")
	done()


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

func test_box_and_quad() -> void:
	var size := Vector3(0.4, 1.2, 0.25)
	var box := Meshes.box(size, 2.0)
	var aabb := box.get_aabb()
	near_vec(aabb.size, size, 1e-5, "box : dimensions de la boite englobante")
	near_vec(aabb.position, -size * 0.5, 1e-5, "box : centree sur l'origine")
	eq(vertices_of(box).size(), 36, "box : six faces de deux triangles")
	check_surface_health(box, "box")
	check(mesh_is_finite(box), "box : aucun NaN")

	# BoxMesh gives every face the same 0..1 UV; box() must not, or a tiling
	# material stretches on the long faces.
	var uvs := uvs_of(box)
	var u_max := 0.0
	var v_max := 0.0
	for uv in uvs:
		u_max = maxf(u_max, uv.x)
		v_max = maxf(v_max, uv.y)
	near(maxf(u_max, v_max), 1.2 * 2.0, 1e-4, "box : UV en metres fois l'echelle")

	var quad := Meshes.quad(3.0, 2.0, Vector2(4.0, 3.0))
	var qa := quad.get_aabb()
	near(qa.size.x, 3.0, 1e-5, "quad : largeur")
	near(qa.size.y, 2.0, 1e-5, "quad : hauteur")
	near(qa.size.z, 0.0, 1e-4, "quad : plat en Z")
	eq(vertices_of(quad).size(), 6, "quad : deux triangles")
	var qn := normals_of(quad)
	# Godot stores normals octahedrally compressed, so the readback is a few
	# units in the last place off the value that was written. Compare with a dot
	# product rather than component by component.
	check(qn[0].dot(Vector3(0.0, 0.0, 1.0)) > 0.9999, "quad : oriente vers +Z (obtenu %s)" % str(qn[0]))
	var q_uv := uvs_of(quad)
	var q_max := Vector2.ZERO
	for uv in q_uv:
		q_max = Vector2(maxf(q_max.x, uv.x), maxf(q_max.y, uv.y))
	near_vec(Vector3(q_max.x, q_max.y, 0.0), Vector3(4.0, 3.0, 0.0), 1e-5, "quad : nombre de repetitions UV")
	check_surface_health(quad, "quad")
	done()


func test_capsule_limb_post_ring() -> void:
	var caps := Meshes.capsule(0.12, 0.9)
	var ca := caps.get_aabb()
	near(ca.size.y, 0.9, 1e-3, "capsule : hauteur totale caps comprises")
	near(ca.size.x, 0.24, 1e-3, "capsule : diametre")
	near(ca.get_center().y, 0.0, 1e-4, "capsule : centree sur l'origine")
	check_surface_health(caps, "capsule")
	check(mesh_is_finite(caps), "capsule : aucun NaN")

	# The taper is the point of limb(): a uniform tube would give the same
	# radius at both ends and the legs would read as pipes.
	var seg := Meshes.limb(0.04, 0.09, 0.5)
	var la := seg.get_aabb()
	near(la.size.y, 0.5, 1e-4, "limb : longueur")
	near(la.size.x, 0.18, 1e-3, "limb : diametre du plus large des deux bouts")
	near(la.get_center().y, 0.0, 1e-4, "limb : centree sur l'origine")
	var narrow := 0.0
	var wide := 0.0
	for p in vertices_of(seg):
		if p.y < -0.24:
			narrow = maxf(narrow, Vector2(p.x, p.z).length())
		elif p.y > 0.24:
			wide = maxf(wide, Vector2(p.x, p.z).length())
	near(narrow, 0.04, 1e-3, "limb : rayon r0 en bas")
	near(wide, 0.09, 1e-3, "limb : rayon r1 en haut")
	check_surface_health(seg, "limb")

	var bar := Meshes.post_mesh(7.32, 0.06, Vector3(1.0, 0.0, 0.0))
	var ba := bar.get_aabb()
	near(ba.size.x, 7.32, 1e-4, "post : longueur suivant l'axe demande")
	# The section is an 18-gon inscribed in the circle, so its bounding box is
	# between twice the apothem and twice the radius, never exactly either.
	var apothem := 0.06 * cos(PI / 18.0)
	between(ba.size.y, 2.0 * apothem - 1e-4, 0.12 + 1e-4, "post : section inscrite en Y")
	between(ba.size.z, 2.0 * apothem - 1e-4, 0.12 + 1e-4, "post : section inscrite en Z")
	# What must be exact is the radius itself, measured around the bar axis.
	var worst_r := 0.0
	for p in vertices_of(bar):
		worst_r = maxf(worst_r, Vector2(p.y, p.z).length())
	near(worst_r, 0.06, 1e-4, "post : rayon exact")
	check_surface_health(bar, "post")
	check(mesh_is_finite(bar), "post : aucun NaN")

	var target := Meshes.ring(0.25, 0.32, 32)
	var ra := target.get_aabb()
	near(ra.size.x, 0.64, 1e-3, "ring : diametre exterieur")
	near(ra.size.z, 0.0, 1e-5, "ring : plat en Z")
	eq(vertices_of(target).size(), 32 * 6, "ring : deux triangles par segment")
	check_surface_health(target, "ring")
	done()


func test_pitch_plane_extents() -> void:
	var half_x := 34.0
	var min_z := -6.0
	var max_z := 62.0
	var mesh := Meshes.pitch_plane(half_x, min_z, max_z, 4.0)
	var aabb := mesh.get_aabb()
	near(aabb.position.x, -half_x, 1e-4, "pelouse : bord -X exact")
	near(aabb.end.x, half_x, 1e-4, "pelouse : bord +X exact")
	near(aabb.position.z, min_z, 1e-4, "pelouse : bord min Z exact")
	near(aabb.end.z, max_z, 1e-4, "pelouse : bord max Z exact")
	near(aabb.size.y, 0.0, 1e-4, "pelouse : parfaitement plate")

	# 68 by 68 metres at a 4 m step is 17 by 17 cells, two triangles each.
	eq(vertices_of(mesh).size(), 17 * 17 * 6, "pelouse : nombre de cellules")
	var worst_up := 1.0
	for n in normals_of(mesh):
		worst_up = minf(worst_up, n.dot(Vector3(0.0, 1.0, 0.0)))
	check(worst_up > 0.9999, "pelouse : normales verticales (pire produit %f)" % worst_up)
	check_surface_health(mesh, "pelouse")
	check(mesh_is_finite(mesh), "pelouse : aucun NaN")

	# A step coarser than the pitch must still cover it exactly, not overshoot.
	var coarse := Meshes.pitch_plane(10.0, 0.0, 15.0, 40.0)
	near(coarse.get_aabb().end.z, 15.0, 1e-4, "pelouse grossiere : bord max Z exact")
	near(coarse.get_aabb().size.x, 20.0, 1e-4, "pelouse grossiere : largeur exacte")
	done()


func test_line_strip_mitres_its_corners() -> void:
	# A right angle: the outer corner vertex must sit at exactly half a width
	# along BOTH offsets, which is the mitre. A butted joint would leave it at
	# half a width along one of them only, and a wedge of bare turf at the
	# corner of the penalty area.
	var w := 0.12
	var pts := PackedVector3Array([
		Vector3(0.0, 0.01, 10.0),
		Vector3(0.0, 0.01, 0.0),
		Vector3(10.0, 0.01, 0.0),
	])
	var mesh := Meshes.line_strip(pts, w, false)
	eq(vertices_of(mesh).size(), 2 * 6, "ligne : deux quads pour deux segments")

	var outer := Vector3(w * 0.5, 0.01, w * 0.5)
	var inner := Vector3(-w * 0.5, 0.01, -w * 0.5)
	var found_outer := false
	var found_inner := false
	for p in vertices_of(mesh):
		if p.distance_to(outer) < 1e-5:
			found_outer = true
		if p.distance_to(inner) < 1e-5:
			found_inner = true
	check(found_outer, "ligne : coin exterieur onglete a %s" % str(outer))
	check(found_inner, "ligne : coin interieur onglete a %s" % str(inner))
	near(mesh.get_aabb().size.y, 0.0, 1e-4, "ligne : ruban plat")
	check_surface_health(mesh, "ligne")

	# Degenerate input must warn and return an empty mesh, never crash.
	eq(Meshes.line_strip(PackedVector3Array([Vector3.ZERO]), w, false).get_surface_count(), 0,
		"ligne : un seul point donne un maillage vide")
	eq(Meshes.line_strip(PackedVector3Array(), w, true).get_surface_count(), 0,
		"ligne : aucun point donne un maillage vide")
	done()


func test_arc_strip_closes_the_centre_circle() -> void:
	var w := 0.12
	var radius := 9.15
	var circle := Meshes.arc_strip(Vector3(0.0, 0.01, 11.0), radius, 0.0, TAU, w, 64)
	eq(vertices_of(circle).size(), 64 * 6, "cercle : un quad par segment, sans doublon de fermeture")
	var aabb := circle.get_aabb()
	# The ribbon straddles the radius, so the outer edge is radius + w / 2 at
	# the four cardinal points.
	near(aabb.size.x, 2.0 * (radius + w * 0.5), 1e-3, "cercle : diametre exterieur")
	near(aabb.get_center().z, 11.0, 1e-3, "cercle : centre sur le point de penalty")
	check_surface_health(circle, "cercle")
	check(mesh_is_finite(circle), "cercle : aucun NaN")

	var arc := Meshes.arc_strip(Vector3.ZERO, 5.0, 0.0, PI, w, 16)
	eq(vertices_of(arc).size(), 16 * 6, "arc ouvert : un quad par segment")
	near(arc.get_aabb().end.x, 5.0 + w * 0.5, 1e-3, "arc ouvert : rayon exterieur")
	done()


func test_stand_and_floodlight() -> void:
	var block := Meshes.stand(30.0, 12, 0.85, 0.42)
	var aabb := block.get_aabb()
	near(aabb.size.x, 30.0, 1e-4, "tribune : largeur")
	near(aabb.end.z, 12.0 * 0.85, 1e-4, "tribune : profondeur des douze rangs")
	near(aabb.end.y, 12.0 * 0.42, 1e-4, "tribune : hauteur du dernier rang")
	near(aabb.position.y, 0.0, 1e-5, "tribune : posee sur le sol")
	check_surface_health(block, "tribune")
	check(mesh_is_finite(block), "tribune : aucun NaN")

	var head := Meshes.floodlight_head(4, 3)
	eq(head.get_surface_count(), 2, "projecteur : deux surfaces, treillis et lampes")
	eq(head.surface_get_name(0), "truss", "projecteur : surface 0 nommee truss")
	eq(head.surface_get_name(1), "lamps", "projecteur : surface 1 nommee lamps")
	eq(vertices_of(head, 1).size(), 12 * 6, "projecteur : douze faces de lampe")
	var worst_lamp := 1.0
	for n in normals_of(head, 1):
		worst_lamp = minf(worst_lamp, n.dot(Vector3(0.0, 0.0, -1.0)))
	check(worst_lamp > 0.9999, "projecteur : lampes tournees vers -Z (pire produit %f)" % worst_lamp)
	check_surface_health(head, "projecteur treillis", 0)
	check_surface_health(head, "projecteur lampes", 1)
	check(mesh_is_finite(head), "projecteur : aucun NaN")
	done()


func test_humanoid_proportions() -> void:
	var parts := Meshes.humanoid_parts()
	var expected := ["pelvis", "torso", "head", "upper_arm", "fore_arm", "hand", "thigh", "shin", "foot"]
	for key in expected:
		check(parts.has(key), "humanoide : partie %s presente" % key)
	eq(parts.size(), expected.size(), "humanoide : neuf parties, ni plus ni moins")

	for key in expected:
		if not parts.has(key):
			continue
		var mesh: ArrayMesh = parts[key]
		check(mesh != null, "humanoide : %s est un maillage" % key)
		if mesh == null:
			continue
		check(vertices_of(mesh).size() > 0, "humanoide : %s non vide" % key)
		check(mesh.get_aabb().get_volume() > 1e-6, "humanoide : %s non degeneree" % key)
		check(mesh_is_finite(mesh), "humanoide : %s sans NaN" % key)
		check_surface_health(mesh, "humanoide %s" % key)

	# The ratios that make the figure read as a person rather than a mannequin.
	var height := 1.88
	var head: ArrayMesh = parts["head"]
	near(head.get_aabb().size.y, height / 7.5, 0.012, "humanoide : tete a un septieme et demi de la taille")
	var torso: ArrayMesh = parts["torso"]
	near(torso.get_aabb().size.x, height / 4.0, 0.012, "humanoide : largeur d'epaules au quart de la taille")
	near(parts["thigh"].get_aabb().size.y + parts["shin"].get_aabb().size.y, 0.91, 0.02,
		"humanoide : cuisse plus tibia font la jambe")
	near(parts["upper_arm"].get_aabb().size.y, 0.186 * height, 0.01, "humanoide : longueur du bras")
	near(parts["fore_arm"].get_aabb().size.y, 0.146 * height, 0.01, "humanoide : longueur de l'avant bras")

	# The boot is the one part that is not centred and not along Y: origin at
	# the ankle, toes towards -Z, sole below.
	var foot: ArrayMesh = parts["foot"]
	var fa := foot.get_aabb()
	check(fa.size.z > fa.size.x, "humanoide : la chaussure est plus longue que large")
	check(fa.position.z < 0.0, "humanoide : les orteils pointent vers -Z")
	near(fa.position.y, -0.0375, 1e-4, "humanoide : semelle sous l'origine de la cheville")

	check(Meshes.humanoid_parts() == parts, "humanoide : le cache renvoie le meme dictionnaire")
	done()
