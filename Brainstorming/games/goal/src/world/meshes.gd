class_name Meshes
extends RefCounted
## Every piece of geometry in the game, generated from numbers.
##
## The repository holds no binary asset, so there is no .glb to load: each mesh
## below is built with SurfaceTool at boot. Two engine facts drive the whole
## file, and both are easy to get wrong.
##
## WINDING. Godot treats a triangle as front facing when its three vertices are
## CLOCKWISE as seen from the front. Every builder here is written with the
## natural mathematical convention instead (counter clockwise as seen from
## outside the surface), and the single helper `_tri` reverses the order on the
## way into the SurfaceTool. One inversion, in one place, instead of a coin flip
## per face.
##
## NORMALS. `SurfaceTool.generate_normals()` produces FLAT, per triangle
## normals. That is exactly wrong for the ball, the limbs and the torso, which
## are curved surfaces and must be smooth. Every builder therefore sets its
## normals explicitly with `set_normal()`, from the analytic surface normal, and
## never calls `generate_normals()`. The trap the engine punishes is a mesh with
## NO normals at all (it renders black); explicit normals are strictly better
## than generated ones whenever the true normal is known, which here is always.
## `generate_tangents()` IS called on every surface: several materials carry a
## normal map, and tangents require the UVs to already be set, which they are.
##
## BALL AND ITS ATLAS. The ball is not a SphereMesh. It is a real truncated
## icosahedron: 12 pentagons and 20 hexagons, each subdivided, then every vertex
## projected onto the sphere of radius `Field.BALL_RADIUS`. A UV sphere would
## make the spin invisible, and the spin is how the player reads the curve in
## flight. The panels are what make the rotation legible, so they are built for
## real rather than painted on.
##
## The UV unwrap is face by face into a 6x6 grid atlas, which is the layout
## `Tex.ball_panels()` and `Tex.ball_normal()` must paint:
##
##   * The atlas is BALL_ATLAS_COLS x BALL_ATLAS_ROWS = 6 x 6 = 36 cells of side
##     1/6. Cell `i` occupies u in [(i % 6)/6, (i % 6 + 1)/6] and
##     v in [floor(i / 6)/6, (floor(i / 6) + 1)/6].
##   * Cells 0..11 hold the twelve PENTAGONS, cells 12..31 hold the twenty
##     HEXAGONS. Cells 32..35 are unused and may hold anything.
##   * Inside its cell each panel is a regular polygon centred on the cell
##     centre, inscribed in a circle whose radius, in CELL WIDTHS, is
##     BALL_PENTAGON_UV_RADIUS (0.400) for a pentagon and
##     BALL_HEXAGON_UV_RADIUS (0.470) for a hexagon.
##   * Those two radii are NOT free. A truncated icosahedron has one single edge
##     length, and a regular n-gon of edge a has circumradius
##     a / (2 sin(PI / n)), so the pentagon is 0.85065 of the hexagon. Unwrapping
##     both families with ONE metres to UV factor therefore yields
##     0.470 and 0.470 * 0.85065 = 0.400, and the printed seam comes out the same
##     width on every panel of the finished ball. Normalising both panels to the
##     same UV radius instead would fatten the pentagon seams by 17 percent, and
##     that is exactly the sort of thing the eye catches on a spinning ball.
##   * The polygon is phase locked: its vertex 0 sits straight UP in the image
##     (towards smaller v). So a pentagon in cell c can be painted as a regular
##     5-gon with one vertex at 12 o'clock, a hexagon as a regular 6-gon with one
##     vertex at 12 o'clock.
##   * The unwrap is UNMIRRORED, meaning u cross v_up equals the outward normal,
##     the same rule the box faces follow. The remaining vertices therefore run
##     counter clockwise on screen, the opposite way round from the numbering in
##     `Tex`. That is immaterial: a regular n-gon with a vertex at 12 o'clock is
##     mirror symmetric about the vertical, so both orders describe the very same
##     polygon in the very same cell.
##
## That convention is deliberately trivial to satisfy: paint a dark n-gon of
## radius 0.400 cell in the twelve pentagon cells, a light one of radius 0.470 in
## the twenty hexagon cells, and the classic black and white ball falls out.
##
## UNITS. Unless a signature says otherwise, UV is expressed in METRES: one UV
## unit is one metre of surface. A tiling material then picks its own repeat
## with `uv1_scale` and gets the same texel density on a post, a stand and the
## turf. `quad()` is the exception, it takes an explicit tile count.
##
## PLACEMENT. Every parameterised primitive is centred on its own origin and, if
## it has a main axis, that axis is +Y. `foot` is the one exception and is
## documented on `humanoid_parts()`.

## Atlas layout of the ball panels. Public so the texture generator can agree
## with it instead of guessing.
const BALL_ATLAS_COLS := 6
const BALL_ATLAS_ROWS := 6
const BALL_PANEL_COUNT := 32
const BALL_PENTAGON_COUNT := 12
const BALL_HEXAGON_COUNT := 20
## Panel circumradius inside its cell, in cell widths. The pentagon value is a
## consequence of the hexagon one, not an independent choice: see the class
## comment.
const BALL_HEXAGON_UV_RADIUS := 0.470
const BALL_PENTAGON_UV_RADIUS := 0.400

## Golden ratio, the icosahedron's whole personality.
const _PHI := 1.6180339887498949
## Two unit icosahedron vertices closer than this share an edge. The real
## distances are 1.0515 (edge), 1.7013 (second ring) and 2.0 (antipode), so the
## threshold has an enormous margin.
const _ICO_EDGE_MAX := 1.30

const _RING_SEGMENTS := 20
const _POST_SEGMENTS := 18
const _CAP_RINGS := 4

## Meshes with no parameter, or with a small closed set of them, are built once.
## Callers share the instance: a MeshInstance3D never mutates its mesh, it sets
## its own material, so sharing is safe and saves a rebuild per keeper limb.
static var _cache: Dictionary = {}


# ---------------------------------------------------------------------------
# Emission helpers
# ---------------------------------------------------------------------------

## Emits one triangle. `pa`, `pb`, `pc` are given COUNTER CLOCKWISE as seen from
## outside the surface. Godot wants front faces clockwise, so the order is
## reversed here, once, for the whole file.
static func _tri(
		st: SurfaceTool,
		pa: Vector3, pb: Vector3, pc: Vector3,
		na: Vector3, nb: Vector3, nc: Vector3,
		ua: Vector2, ub: Vector2, uc: Vector2) -> void:
	st.set_normal(na)
	st.set_uv(ua)
	st.add_vertex(pa)
	st.set_normal(nc)
	st.set_uv(uc)
	st.add_vertex(pc)
	st.set_normal(nb)
	st.set_uv(ub)
	st.add_vertex(pb)


## Flat quad, corners counter clockwise seen from outside, one shared normal.
static func _quad_flat(
		st: SurfaceTool,
		p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3,
		n: Vector3,
		u0: Vector2, u1: Vector2, u2: Vector2, u3: Vector2) -> void:
	_tri(st, p0, p1, p2, n, n, n, u0, u1, u2)
	_tri(st, p0, p2, p3, n, n, n, u0, u2, u3)


## Orthonormal basis whose +Y column is `axis`. Used to aim a cylinder or a
## truss bar without building a second mesh.
static func _basis_from_axis(axis: Vector3) -> Basis:
	var y_axis := axis
	if y_axis.length_squared() < 1e-12:
		y_axis = Vector3.UP
	y_axis = y_axis.normalized()
	var reference := Vector3.UP
	if absf(y_axis.dot(reference)) > 0.99:
		reference = Vector3.RIGHT
	var x_axis := y_axis.cross(reference).normalized()
	var z_axis := x_axis.cross(y_axis)
	return Basis(x_axis, y_axis, z_axis)


## The six faces of a box as (normal, u axis, v axis). The v axis points UP in
## image space, and `u cross v == n` so the texture is never mirrored when the
## face is looked at from outside.
static func _box_faces() -> Array[PackedVector3Array]:
	var faces: Array[PackedVector3Array] = [
		PackedVector3Array([Vector3(1.0, 0.0, 0.0), Vector3(0.0, 0.0, -1.0), Vector3(0.0, 1.0, 0.0)]),
		PackedVector3Array([Vector3(-1.0, 0.0, 0.0), Vector3(0.0, 0.0, 1.0), Vector3(0.0, 1.0, 0.0)]),
		PackedVector3Array([Vector3(0.0, 1.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 0.0, -1.0)]),
		PackedVector3Array([Vector3(0.0, -1.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 0.0, 1.0)]),
		PackedVector3Array([Vector3(0.0, 0.0, 1.0), Vector3(1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)]),
		PackedVector3Array([Vector3(0.0, 0.0, -1.0), Vector3(-1.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0)]),
	]
	return faces


## Emits an oriented box. `uv_scale` is texture repeats per metre.
static func _emit_box(st: SurfaceTool, xform: Transform3D, size: Vector3, uv_scale: float) -> void:
	var h := size.abs() * 0.5
	for face in _box_faces():
		var n: Vector3 = face[0]
		var ua: Vector3 = face[1]
		var va: Vector3 = face[2]
		var hn := absf(n.x) * h.x + absf(n.y) * h.y + absf(n.z) * h.z
		var hu := absf(ua.x) * h.x + absf(ua.y) * h.y + absf(ua.z) * h.z
		var hv := absf(va.x) * h.x + absf(va.y) * h.y + absf(va.z) * h.z
		var centre := n * hn
		var p0 := centre - ua * hu - va * hv
		var p1 := centre + ua * hu - va * hv
		var p2 := centre + ua * hu + va * hv
		var p3 := centre - ua * hu + va * hv
		var wn := (xform.basis * n).normalized()
		var su := 2.0 * hu * uv_scale
		var sv := 2.0 * hv * uv_scale
		_quad_flat(st,
			xform * p0, xform * p1, xform * p2, xform * p3, wn,
			Vector2(0.0, sv), Vector2(su, sv), Vector2(su, 0.0), Vector2(0.0, 0.0))


## Lofts a stack of elliptical rings along +Y and emits it into `st`.
##
## Each ring is a Vector3 read as (y, radius_x, radius_z). The surface normal is
## analytic: for S(theta, t) = (rx cos, y, rz sin) the outward normal is
## (rz y' cos, -(rz rx' cos2 + rx rz' sin2), rx y' sin), which is what makes a
## tapered limb shade like a cone instead of like a stack of cylinders. The
## derivatives are secants over the neighbouring rings, so a coarse profile
## still shades smoothly.
static func _emit_tube(
		st: SurfaceTool,
		rings: Array[Vector3],
		segments: int,
		cap_bottom: bool,
		cap_top: bool,
		xform: Transform3D) -> void:
	var count := rings.size()
	if count < 2 or segments < 3:
		push_warning("Meshes._emit_tube: profil degenere, rien a emettre")
		return

	var r_ref := 0.0
	for ring in rings:
		r_ref = maxf(r_ref, maxf(absf(ring.y), absf(ring.z)))
	if r_ref <= 0.0:
		r_ref = 1.0

	# Profile arc length, so v stays in metres like every other UV here.
	var v_coord := PackedFloat32Array()
	v_coord.resize(count)
	v_coord[0] = 0.0
	for i in range(1, count):
		var d_y := rings[i].x - rings[i - 1].x
		var d_r := maxf(rings[i].y, rings[i].z) - maxf(rings[i - 1].y, rings[i - 1].z)
		v_coord[i] = v_coord[i - 1] + Vector2(d_y, d_r).length()

	var positions: Array[PackedVector3Array] = []
	var normals: Array[PackedVector3Array] = []
	for i in count:
		var ring: Vector3 = rings[i]
		var prev: Vector3 = rings[maxi(i - 1, 0)]
		var next: Vector3 = rings[mini(i + 1, count - 1)]
		var d_y := next.x - prev.x
		var d_rx := next.y - prev.y
		var d_rz := next.z - prev.z
		var row_p := PackedVector3Array()
		var row_n := PackedVector3Array()
		for k in range(segments + 1):
			var theta := TAU * float(k) / float(segments)
			var cs := cos(theta)
			var sn := sin(theta)
			var local_p := Vector3(ring.y * cs, ring.x, ring.z * sn)
			var local_n := Vector3(
				ring.z * d_y * cs,
				-(ring.z * d_rx * cs * cs + ring.y * d_rz * sn * sn),
				ring.y * d_y * sn)
			if local_n.length_squared() < 1e-14:
				# A pole ring has zero radius, so the formula collapses. The
				# only sane normal there is the axis itself.
				local_n = Vector3(0.0, -1.0 if i == 0 else 1.0, 0.0)
			row_p.append(xform * local_p)
			row_n.append((xform.basis * local_n).normalized())
		positions.append(row_p)
		normals.append(row_n)

	for i in range(count - 1):
		for k in range(segments):
			var a: Vector3 = positions[i][k]
			var b: Vector3 = positions[i + 1][k]
			var c: Vector3 = positions[i + 1][k + 1]
			var d: Vector3 = positions[i][k + 1]
			var na: Vector3 = normals[i][k]
			var nb: Vector3 = normals[i + 1][k]
			var nc: Vector3 = normals[i + 1][k + 1]
			var nd: Vector3 = normals[i][k + 1]
			var u0 := TAU * float(k) / float(segments) * r_ref
			var u1 := TAU * float(k + 1) / float(segments) * r_ref
			var v0 := v_coord[i]
			var v1 := v_coord[i + 1]
			_tri(st, a, b, c, na, nb, nc, Vector2(u0, v0), Vector2(u0, v1), Vector2(u1, v1))
			_tri(st, a, c, d, na, nc, nd, Vector2(u0, v0), Vector2(u1, v1), Vector2(u1, v0))

	if cap_bottom and maxf(rings[0].y, rings[0].z) > 1e-5:
		var n_down := (xform.basis * Vector3(0.0, -1.0, 0.0)).normalized()
		var o_down := xform * Vector3(0.0, rings[0].x, 0.0)
		for k in range(segments):
			var p_a: Vector3 = positions[0][k]
			var p_b: Vector3 = positions[0][k + 1]
			_tri(st, o_down, p_a, p_b, n_down, n_down, n_down,
				Vector2.ZERO,
				Vector2(rings[0].y * cos(TAU * float(k) / float(segments)), rings[0].z * sin(TAU * float(k) / float(segments))),
				Vector2(rings[0].y * cos(TAU * float(k + 1) / float(segments)), rings[0].z * sin(TAU * float(k + 1) / float(segments))))

	var last := count - 1
	if cap_top and maxf(rings[last].y, rings[last].z) > 1e-5:
		var n_up := (xform.basis * Vector3(0.0, 1.0, 0.0)).normalized()
		var o_up := xform * Vector3(0.0, rings[last].x, 0.0)
		for k in range(segments):
			var p_a: Vector3 = positions[last][k + 1]
			var p_b: Vector3 = positions[last][k]
			_tri(st, o_up, p_a, p_b, n_up, n_up, n_up,
				Vector2.ZERO,
				Vector2(rings[last].y * cos(TAU * float(k + 1) / float(segments)), rings[last].z * sin(TAU * float(k + 1) / float(segments))),
				Vector2(rings[last].y * cos(TAU * float(k) / float(segments)), rings[last].z * sin(TAU * float(k) / float(segments))))


## Convenience wrapper: a whole ArrayMesh out of one lofted profile.
static func _tube(rings: Array[Vector3], segments: int, cap_bottom: bool, cap_top: bool, xform: Transform3D) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_emit_tube(st, rings, segments, cap_bottom, cap_top, xform)
	return _finish(st)


## Tangents plus commit, with the empty surface guarded. Returns an ArrayMesh
## that is always non null, so a caller never has to test for it.
static func _finish(st: SurfaceTool) -> ArrayMesh:
	st.generate_tangents()
	var mesh: ArrayMesh = st.commit()
	if mesh == null:
		push_warning("Meshes: surface vide, maillage de secours renvoye")
		return ArrayMesh.new()
	return mesh


# ---------------------------------------------------------------------------
# The ball: a real truncated icosahedron
# ---------------------------------------------------------------------------

## The twelve icosahedron vertices, on the unit sphere. Cyclic permutations of
## (0, +/-1, +/-phi). Their order fixes the pentagon cell indices 0..11 of the
## atlas, so it must stay exactly as written.
static func _icosahedron_vertices() -> PackedVector3Array:
	var raw := PackedVector3Array([
		Vector3(0.0, 1.0, _PHI), Vector3(0.0, -1.0, _PHI),
		Vector3(0.0, 1.0, -_PHI), Vector3(0.0, -1.0, -_PHI),
		Vector3(1.0, _PHI, 0.0), Vector3(-1.0, _PHI, 0.0),
		Vector3(1.0, -_PHI, 0.0), Vector3(-1.0, -_PHI, 0.0),
		Vector3(_PHI, 0.0, 1.0), Vector3(_PHI, 0.0, -1.0),
		Vector3(-_PHI, 0.0, 1.0), Vector3(-_PHI, 0.0, -1.0),
	])
	var out := PackedVector3Array()
	for v in raw:
		out.append(v.normalized())
	return out


## The twenty triangular faces, derived rather than typed in: any triple of
## mutually adjacent vertices is a face, and there are exactly twenty of them.
## Each triple is reordered so that (b - a) cross (c - a) points away from the
## centre, which is what lets the hexagon perimeter below be walked in a single
## direction. The a < b < c enumeration makes the order deterministic, and that
## order fixes the hexagon cell indices 12..31 of the atlas.
static func _icosahedron_faces(verts: PackedVector3Array) -> Array[Vector3i]:
	var faces: Array[Vector3i] = []
	var n := verts.size()
	for a in range(n):
		for b in range(a + 1, n):
			if verts[a].distance_to(verts[b]) > _ICO_EDGE_MAX:
				continue
			for c in range(b + 1, n):
				if verts[a].distance_to(verts[c]) > _ICO_EDGE_MAX:
					continue
				if verts[b].distance_to(verts[c]) > _ICO_EDGE_MAX:
					continue
				var centroid := (verts[a] + verts[b] + verts[c]) / 3.0
				if (verts[b] - verts[a]).cross(verts[c] - verts[a]).dot(centroid) > 0.0:
					faces.append(Vector3i(a, b, c))
				else:
					faces.append(Vector3i(a, c, b))
	return faces


## The five neighbours of vertex `index`, sorted counter clockwise as seen from
## outside the sphere. Sorting by the angle in the tangent frame (u, w) with
## w = axis cross u gives exactly that orientation.
static func _icosahedron_neighbours(verts: PackedVector3Array, index: int) -> PackedInt32Array:
	var v := verts[index]
	var axis := v.normalized()
	var found := PackedInt32Array()
	for i in verts.size():
		if i != index and verts[i].distance_to(v) <= _ICO_EDGE_MAX:
			found.append(i)
	if found.size() < 3:
		push_error("Meshes: sommet d'icosaedre sans voisinage complet")
		return found

	var u := verts[found[0]] - v
	u = (u - axis * u.dot(axis)).normalized()
	var w := axis.cross(u)

	var keyed: Array[Vector2] = []
	for i in found:
		var d := verts[i] - v
		d = d - axis * d.dot(axis)
		keyed.append(Vector2(atan2(d.dot(w), d.dot(u)), float(i)))
	keyed.sort_custom(func(p: Vector2, q: Vector2) -> bool: return p.x < q.x)

	var ordered := PackedInt32Array()
	for entry in keyed:
		ordered.append(int(entry.y))
	return ordered


## Subdivides one flat panel, projects it onto the sphere and unwraps it into
## its atlas cell.
##
## `poly` is the flat polygon, already counter clockwise as seen from outside.
## The panel is fanned from its centroid into n corner triangles, each split
## into 4^subdivisions sub triangles on the FLAT face. The UV is taken from the
## flat position, so the unwrap stays affine and the panel keeps its shape, and
## only then is the position pushed out onto the sphere.
##
## `uv_unit` is the UV length of one unit of the flat, pre projection geometry.
## It is passed in rather than derived per panel precisely so that pentagons and
## hexagons share one scale and end up at 0.400 and 0.470 cell widths.
static func _add_panel(st: SurfaceTool, poly: PackedVector3Array, cell: int, subdivisions: int, radius: float, uv_unit: float) -> void:
	var n := poly.size()
	if n < 3:
		return
	var centre := Vector3.ZERO
	for p in poly:
		centre += p
	centre /= float(n)

	var axis := centre.normalized()
	var up := poly[0] - centre
	up = (up - axis * up.dot(axis)).normalized()
	# right cross up == axis, the same rule the box faces follow, which keeps
	# the atlas unmirrored when the panel is seen from outside.
	var right := up.cross(axis)
	var circum := (poly[0] - centre).length()
	if circum <= 0.0:
		return

	var cell_side := 1.0 / float(BALL_ATLAS_COLS)
	var col := cell % BALL_ATLAS_COLS
	var row := int(floor(float(cell) / float(BALL_ATLAS_COLS)))
	var uv_centre := Vector2((float(col) + 0.5) * cell_side, (float(row) + 0.5) * cell_side)
	var uv_scale := uv_unit

	var kd := 1 << maxi(subdivisions, 0)
	var inv_kd := 1.0 / float(kd)

	for k in n:
		var corner_b := poly[k]
		var corner_c := poly[(k + 1) % n]
		var grid_p := PackedVector3Array()
		var grid_uv := PackedVector2Array()
		# Barycentric grid over (centre, corner_b, corner_c). Row i holds i + 1
		# points and starts at index i * (i + 1) / 2.
		for i in range(kd + 1):
			for j in range(i + 1):
				var wa := 1.0 - float(i) * inv_kd
				var wc := float(j) * inv_kd
				var wb := 1.0 - wa - wc
				var flat := centre * wa + corner_b * wb + corner_c * wc
				var offset := flat - centre
				grid_uv.append(uv_centre + Vector2(offset.dot(right), -offset.dot(up)) * uv_scale)
				grid_p.append(flat.normalized() * radius)
		for i in range(1, kd + 1):
			var base := (i * (i + 1)) >> 1
			var prev := ((i - 1) * i) >> 1
			for j in range(i):
				_tri_sphere(st, grid_p, grid_uv, prev + j, base + j, base + j + 1)
			for j in range(i - 1):
				_tri_sphere(st, grid_p, grid_uv, prev + j, base + j + 1, prev + j + 1)


## One ball triangle. The normal of a spherified vertex is the vertex itself,
## normalized: exact, and smooth across the whole panel.
static func _tri_sphere(st: SurfaceTool, pos: PackedVector3Array, uvs: PackedVector2Array, ia: int, ib: int, ic: int) -> void:
	_tri(st,
		pos[ia], pos[ib], pos[ic],
		pos[ia].normalized(), pos[ib].normalized(), pos[ic].normalized(),
		uvs[ia], uvs[ib], uvs[ic])


## Truncated icosahedron, spherified, radius Field.BALL_RADIUS, with UVs.
## `subdivisions` 2 gives a smooth ball, 0 gives a visible faceted one.
##
## The truncation is done the honest way: every panel vertex sits at one third
## or two thirds along an icosahedron edge. A pentagon is the five one third
## points around an icosahedron vertex, a hexagon is the six points along the
## perimeter of an icosahedron face. That yields 60 vertices, 90 edges and 32
## faces, and the two families share their vertices exactly, so the ball has no
## crack in it.
##
## Triangle count is 180 * 4^subdivisions: 12 * 5 + 20 * 6 corner triangles,
## each split into 4^subdivisions. The mesh is deliberately NOT indexed: every
## panel needs its own UV island, so nothing can be shared across a panel
## boundary anyway, and an unindexed mesh keeps the vertex count at exactly
## three times the triangle count, which the test suite pins down.
static func ball_mesh(subdivisions: int = 2) -> ArrayMesh:
	var level := clampi(subdivisions, 0, 4)
	var key := "ball_%d" % level
	if _cache.has(key):
		return _cache[key]

	var radius: float = Field.BALL_RADIUS
	var verts := _icosahedron_vertices()
	var faces := _icosahedron_faces(verts)
	if faces.size() != BALL_HEXAGON_COUNT:
		push_error("Meshes.ball_mesh: %d faces d'icosaedre au lieu de 20" % faces.size())

	# One metres to UV factor for both panel families. The truncated icosahedron
	# edge is a third of the icosahedron edge, and a hexagon's circumradius IS
	# its edge, so pinning the hexagon at BALL_HEXAGON_UV_RADIUS drops the
	# pentagon onto BALL_PENTAGON_UV_RADIUS on its own.
	var ico_edge := 2.0 / sqrt(1.0 + _PHI * _PHI)
	var hex_circum := ico_edge / 3.0
	var uv_unit := (1.0 / float(BALL_ATLAS_COLS)) * BALL_HEXAGON_UV_RADIUS / hex_circum

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	for vi in verts.size():
		var neighbours := _icosahedron_neighbours(verts, vi)
		var pentagon := PackedVector3Array()
		for ni in neighbours:
			pentagon.append(verts[vi] + (verts[ni] - verts[vi]) / 3.0)
		_add_panel(st, pentagon, vi, level, radius, uv_unit)

	for fi in faces.size():
		var face: Vector3i = faces[fi]
		var va := verts[face.x]
		var vb := verts[face.y]
		var vc := verts[face.z]
		var hexagon := PackedVector3Array([
			va + (vb - va) / 3.0, va + (vb - va) * (2.0 / 3.0),
			vb + (vc - vb) / 3.0, vb + (vc - vb) * (2.0 / 3.0),
			vc + (va - vc) / 3.0, vc + (va - vc) * (2.0 / 3.0),
		])
		_add_panel(st, hexagon, BALL_PENTAGON_COUNT + fi, level, radius, uv_unit)

	var mesh := _finish(st)
	_cache[key] = mesh
	return mesh


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

## A goal post or the crossbar: a capped cylinder along `axis`, length `length`.
## Centred on the origin, so a post is placed at its own midpoint. UV is in
## metres: u runs around the circumference, v along the length.
static func post_mesh(length: float, radius: float, axis: Vector3) -> ArrayMesh:
	var half := maxf(length, 0.001) * 0.5
	var r := maxf(radius, 0.001)
	var rings: Array[Vector3] = [
		Vector3(-half, r, r),
		Vector3(half, r, r),
	]
	return _tube(rings, _POST_SEGMENTS, true, true, Transform3D(_basis_from_axis(axis), Vector3.ZERO))


## A flat quad in the XY plane, centred, facing +Z, with UVs. For nets and
## adverts. `uv_tiles` is a repeat count, not a size: this is the one builder
## whose UV is not expressed in metres, because a net panel and an advert both
## want to control their own tiling exactly.
static func quad(width: float, height: float, uv_tiles: Vector2 = Vector2.ONE) -> ArrayMesh:
	var hw := width * 0.5
	var hh := height * 0.5
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_quad_flat(st,
		Vector3(-hw, -hh, 0.0), Vector3(hw, -hh, 0.0), Vector3(hw, hh, 0.0), Vector3(-hw, hh, 0.0),
		Vector3(0.0, 0.0, 1.0),
		Vector2(0.0, uv_tiles.y), Vector2(uv_tiles.x, uv_tiles.y), Vector2(uv_tiles.x, 0.0), Vector2.ZERO)
	return _finish(st)


## A box with proper UVs and tangents, centred on the origin. SurfaceTool and
## not BoxMesh: BoxMesh gives every face the same 0..1 UV, so a tiling material
## stretches on the long faces and there is no way to fix it from the material.
## `uv_scale` is texture repeats per metre.
static func box(size: Vector3, uv_scale: float = 1.0) -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_emit_box(st, Transform3D.IDENTITY, size, uv_scale)
	return _finish(st)


## A capsule along Y, for limbs and torsos. `height` is the TOTAL height, caps
## included, which is the CapsuleMesh convention, so swapping one for the other
## never changes a silhouette.
static func capsule(radius: float, height: float) -> ArrayMesh:
	var r := maxf(radius, 0.001)
	var total := maxf(height, 2.0 * r)
	var mid := maxf(total - 2.0 * r, 0.0)
	var half_mid := mid * 0.5

	var rings: Array[Vector3] = []
	for i in range(_CAP_RINGS + 1):
		var phi := lerpf(-PI * 0.5, 0.0, float(i) / float(_CAP_RINGS))
		var ring_r := r * cos(phi)
		rings.append(Vector3(-half_mid + r * sin(phi), ring_r, ring_r))
	for i in range(1, _CAP_RINGS + 1):
		var phi := lerpf(0.0, PI * 0.5, float(i) / float(_CAP_RINGS))
		var ring_r := r * cos(phi)
		rings.append(Vector3(half_mid + r * sin(phi), ring_r, ring_r))
	return _tube(rings, _RING_SEGMENTS, false, false, Transform3D.IDENTITY)


## A tapered limb segment: a cone frustum from `r0` to `r1` over `length`, along
## Y and centred on the origin, so `r0` is at y = -length / 2 and `r1` at
## y = +length / 2. Centred like every other primitive here, which is what lets
## a limb be placed at the midpoint between two joints and simply aimed.
static func limb(r0: float, r1: float, length: float) -> ArrayMesh:
	var half := maxf(length, 0.001) * 0.5
	var a := maxf(r0, 0.0005)
	var b := maxf(r1, 0.0005)
	var rings: Array[Vector3] = [
		Vector3(-half, a, a),
		Vector3(half, b, b),
	]
	return _tube(rings, _RING_SEGMENTS, true, true, Transform3D.IDENTITY)


## A ring lying in the XY plane, facing +Z, for the Defi mode targets. Facing
## +Z means facing the shooter, who stands at positive z and looks towards -Z.
static func ring(inner: float, outer: float, segments: int = 48) -> ArrayMesh:
	var seg := maxi(segments, 3)
	var r_in := maxf(minf(inner, outer), 0.0)
	var r_out := maxf(outer, r_in + 0.001)
	var n := Vector3(0.0, 0.0, 1.0)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for k in range(seg):
		var a0 := TAU * float(k) / float(seg)
		var a1 := TAU * float(k + 1) / float(seg)
		var p0 := Vector3(cos(a0) * r_in, sin(a0) * r_in, 0.0)
		var p1 := Vector3(cos(a0) * r_out, sin(a0) * r_out, 0.0)
		var p2 := Vector3(cos(a1) * r_out, sin(a1) * r_out, 0.0)
		var p3 := Vector3(cos(a1) * r_in, sin(a1) * r_in, 0.0)
		var u0 := float(k) / float(seg)
		var u1 := float(k + 1) / float(seg)
		_quad_flat(st, p0, p1, p2, p3, n,
			Vector2(u0, 1.0), Vector2(u0, 0.0), Vector2(u1, 0.0), Vector2(u1, 1.0))
	return _finish(st)


# ---------------------------------------------------------------------------
# Pitch surface and painted markings
# ---------------------------------------------------------------------------

## The pitch surface: a subdivided plane so the light and the fog have vertices
## to work with. Spans x in [-half_x, half_x], z in [min_z, max_z].
##
## The subdivision matters: a single quad under four spotlights bakes all of its
## lighting into four vertices, and the specular sweep of a floodlight across
## wet grass simply disappears. UV is in metres so the turf material picks its
## own repeat and the pitch can be resized without retuning it.
##
## Vertex positions are computed by lerp on the cell index rather than by
## accumulating `step`, so the last column lands exactly on `half_x` and the
## last row exactly on `max_z`, whatever rounding `step` implies.
static func pitch_plane(half_x: float, min_z: float, max_z: float, step: float) -> ArrayMesh:
	var width := half_x * 2.0
	var depth := max_z - min_z
	if width <= 0.0 or depth <= 0.0:
		push_warning("Meshes.pitch_plane: etendue nulle, maillage vide")
		return ArrayMesh.new()

	var cell := maxf(step, 0.05)
	var cols := maxi(1, int(ceil(width / cell)))
	var rows := maxi(1, int(ceil(depth / cell)))
	var n := Vector3(0.0, 1.0, 0.0)

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for r in range(rows):
		var z0 := lerpf(min_z, max_z, float(r) / float(rows))
		var z1 := lerpf(min_z, max_z, float(r + 1) / float(rows))
		for c in range(cols):
			var x0 := lerpf(-half_x, half_x, float(c) / float(cols))
			var x1 := lerpf(-half_x, half_x, float(c + 1) / float(cols))
			_quad_flat(st,
				Vector3(x0, 0.0, z0), Vector3(x0, 0.0, z1), Vector3(x1, 0.0, z1), Vector3(x1, 0.0, z0),
				n,
				Vector2(x0, z0), Vector2(x0, z1), Vector2(x1, z1), Vector2(x1, z0))
	return _finish(st)


## A flat ribbon following a polyline at a fixed height, for painted lines. The
## ribbon lies in the XZ plane at the y of its points and faces +Y.
##
## The joints are MITRED, not butted: at an interior vertex the offset direction
## is the bisector of the two segment normals, lengthened by 1 / cos(half angle)
## so the outer edges of the two segments meet exactly. Butting them instead
## leaves a wedge of bare turf at every corner of the penalty area, which is the
## first thing the eye catches on a pitch. The lengthening is capped at 4x so a
## near reversal produces a blunt corner rather than a spike shooting across the
## pitch.
##
## UV: u spans 0..1 across the width, v is the arc length divided by the width,
## so the paint texture keeps its aspect ratio however long the line is.
static func line_strip(points: PackedVector3Array, width: float, closed: bool) -> ArrayMesh:
	var w := maxf(width, 0.001)

	# Duplicate points give a zero length segment and a NaN direction, so they
	# are dropped before anything else looks at the polyline.
	var pts := PackedVector3Array()
	for p in points:
		if pts.is_empty() or pts[pts.size() - 1].distance_to(p) > 1e-6:
			pts.append(p)
	if closed and pts.size() > 1 and pts[0].distance_to(pts[pts.size() - 1]) <= 1e-6:
		pts.remove_at(pts.size() - 1)

	var count := pts.size()
	if count < 2 or (closed and count < 3):
		push_warning("Meshes.line_strip: polyligne trop courte, maillage vide")
		return ArrayMesh.new()

	var seg_count := count if closed else count - 1
	var dirs := PackedVector3Array()
	var norms := PackedVector3Array()
	for i in range(seg_count):
		var d := pts[(i + 1) % count] - pts[i]
		d.y = 0.0
		d = d.normalized()
		dirs.append(d)
		norms.append(Vector3(-d.z, 0.0, d.x))

	var half := w * 0.5
	var left := PackedVector3Array()
	var right := PackedVector3Array()
	for j in range(count):
		var offset: Vector3
		if not closed and j == 0:
			offset = norms[0]
		elif not closed and j == count - 1:
			offset = norms[seg_count - 1]
		else:
			var n_prev: Vector3 = norms[(j - 1 + seg_count) % seg_count]
			var n_next: Vector3 = norms[j % seg_count]
			var bisector := n_prev + n_next
			if bisector.length_squared() < 1e-10:
				offset = n_next
			else:
				bisector = bisector.normalized()
				offset = bisector / maxf(bisector.dot(n_next), 0.25)
		left.append(pts[j] + offset * half)
		right.append(pts[j] - offset * half)

	var arc := PackedFloat32Array()
	arc.resize(count)
	arc[0] = 0.0
	for j in range(1, count):
		arc[j] = arc[j - 1] + pts[j - 1].distance_to(pts[j])

	var n_up := Vector3(0.0, 1.0, 0.0)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(seg_count):
		var j0 := i
		var j1 := (i + 1) % count
		var v0 := arc[j0] / w
		var v1 := (arc[j1] if j1 > j0 else arc[count - 1] + pts[count - 1].distance_to(pts[0])) / w
		_quad_flat(st,
			left[j0], left[j1], right[j1], right[j0],
			n_up,
			Vector2(0.0, v0), Vector2(0.0, v1), Vector2(1.0, v1), Vector2(1.0, v0))
	return _finish(st)


## A circle arc as a painted line ribbon. Angles are measured in the XZ plane:
## the point at angle `a` is centre + (cos(a) * radius, 0, sin(a) * radius). A
## full turn is detected and drawn as a closed ribbon, so the centre circle has
## a mitred joint where it meets itself instead of a seam.
static func arc_strip(centre: Vector3, radius: float, from_angle: float, to_angle: float, width: float, segments: int) -> ArrayMesh:
	var seg := maxi(segments, 3)
	var span := to_angle - from_angle
	var is_closed := absf(absf(span) - TAU) < 1e-4
	var count := seg if is_closed else seg + 1
	var pts := PackedVector3Array()
	for i in range(count):
		var a := from_angle + span * float(i) / float(seg)
		pts.append(centre + Vector3(cos(a) * radius, 0.0, sin(a) * radius))
	return line_strip(pts, width, is_closed)


# ---------------------------------------------------------------------------
# Stadium furniture
# ---------------------------------------------------------------------------

## Stadium stand: a raked block of steps rising away from the pitch.
##
## Local frame: x spans [-width / 2, width / 2], the front edge of the first
## step is at z = 0 and y = 0, and the rake climbs towards +Z. Row r therefore
## carries a riser at z = r * row_depth and a tread at y = (r + 1) * row_rise.
##
## The block is closed on the sides and at the back. It is tempting to emit only
## the visible risers and treads, but a stand is seen from the corner flag as
## well as from the penalty spot, and an open side reads as a hole in the world.
## The side walls are cut into one rectangle per row rather than fanned from a
## corner: the staircase profile is not star shaped from any of its corners, so
## a fan would fold over itself.
static func stand(width: float, rows: int, row_depth: float, row_rise: float) -> ArrayMesh:
	var w := maxf(width, 0.1)
	var count := maxi(rows, 1)
	var depth := maxf(row_depth, 0.05)
	var rise := maxf(row_rise, 0.02)
	var hx := w * 0.5

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)

	var n_front := Vector3(0.0, 0.0, -1.0)
	var n_up := Vector3(0.0, 1.0, 0.0)
	var n_right := Vector3(1.0, 0.0, 0.0)
	var n_left := Vector3(-1.0, 0.0, 0.0)
	var n_back := Vector3(0.0, 0.0, 1.0)

	for r in range(count):
		var z0 := float(r) * depth
		var z1 := float(r + 1) * depth
		var y0 := float(r) * rise
		var y1 := float(r + 1) * rise

		# Riser, facing the pitch.
		_quad_flat(st,
			Vector3(hx, y0, z0), Vector3(-hx, y0, z0), Vector3(-hx, y1, z0), Vector3(hx, y1, z0),
			n_front,
			Vector2(0.0, rise), Vector2(w, rise), Vector2(w, 0.0), Vector2(0.0, 0.0))

		# Tread, the step itself.
		_quad_flat(st,
			Vector3(-hx, y1, z0), Vector3(-hx, y1, z1), Vector3(hx, y1, z1), Vector3(hx, y1, z0),
			n_up,
			Vector2(0.0, z0), Vector2(0.0, z1), Vector2(w, z1), Vector2(w, z0))

		# Side walls: the full column of masonry under this tread.
		_quad_flat(st,
			Vector3(hx, 0.0, z1), Vector3(hx, 0.0, z0), Vector3(hx, y1, z0), Vector3(hx, y1, z1),
			n_right,
			Vector2(0.0, y1), Vector2(depth, y1), Vector2(depth, 0.0), Vector2(0.0, 0.0))
		_quad_flat(st,
			Vector3(-hx, y1, z1), Vector3(-hx, y1, z0), Vector3(-hx, 0.0, z0), Vector3(-hx, 0.0, z1),
			n_left,
			Vector2(0.0, 0.0), Vector2(depth, 0.0), Vector2(depth, y1), Vector2(0.0, y1))

	var z_back := float(count) * depth
	var y_back := float(count) * rise
	_quad_flat(st,
		Vector3(-hx, 0.0, z_back), Vector3(hx, 0.0, z_back), Vector3(hx, y_back, z_back), Vector3(-hx, y_back, z_back),
		n_back,
		Vector2(0.0, y_back), Vector2(w, y_back), Vector2(w, 0.0), Vector2(0.0, 0.0))

	return _finish(st)


## Floodlight pylon head: a truss frame carrying a grid of lamp faces.
##
## The head EMITS ALONG -Z, so a Node3D holding it can simply `look_at` the
## centre circle and be correctly aimed, the same convention Godot uses for
## cameras and lights.
##
## The returned ArrayMesh has TWO surfaces, named so they cannot be mixed up:
## surface 0 "truss" wants Mats.steel(), surface 1 "lamps" wants Mats.lamp().
## They are separate because a lamp face is emissive and a truss bar is not, and
## an emissive truss at night looks like a bug rather than a stadium.
static func floodlight_head(columns: int, rows: int) -> ArrayMesh:
	var cols := maxi(columns, 1)
	var rws := maxi(rows, 1)

	var lamp_w := 0.90
	var lamp_h := 0.62
	var gap := 0.10
	var depth := 0.14
	var total_w := float(cols) * lamp_w + float(cols + 1) * gap
	var total_h := float(rws) * lamp_h + float(rws + 1) * gap

	var truss := SurfaceTool.new()
	truss.begin(Mesh.PRIMITIVE_TRIANGLES)
	var lamps := SurfaceTool.new()
	lamps.begin(Mesh.PRIMITIVE_TRIANGLES)

	# Outer frame: two horizontal bars, two vertical bars.
	var half_w := total_w * 0.5
	var half_h := total_h * 0.5
	for sign_y in [-1.0, 1.0]:
		_emit_box(truss,
			Transform3D(Basis.IDENTITY, Vector3(0.0, sign_y * (half_h - gap * 0.5), 0.0)),
			Vector3(total_w, gap, depth), 1.5)
	for sign_x in [-1.0, 1.0]:
		_emit_box(truss,
			Transform3D(Basis.IDENTITY, Vector3(sign_x * (half_w - gap * 0.5), 0.0, 0.0)),
			Vector3(gap, total_h - 2.0 * gap, depth), 1.5)

	# Separators between the lamp cells.
	for c in range(1, cols):
		var x := -half_w + gap * 0.5 + float(c) * (lamp_w + gap)
		_emit_box(truss, Transform3D(Basis.IDENTITY, Vector3(x, 0.0, 0.0)),
			Vector3(gap, total_h - 2.0 * gap, depth * 0.8), 1.5)
	for r in range(1, rws):
		var y := -half_h + gap * 0.5 + float(r) * (lamp_h + gap)
		_emit_box(truss, Transform3D(Basis.IDENTITY, Vector3(0.0, y, 0.0)),
			Vector3(total_w - 2.0 * gap, gap, depth * 0.8), 1.5)

	# Back structure: a spine plus two braces, which is what stops the head
	# reading as a flat billboard when the camera swings behind the goal.
	var spine_z := 0.55
	_emit_box(truss, Transform3D(Basis.IDENTITY, Vector3(0.0, 0.0, spine_z)),
		Vector3(0.16, 0.16, 0.55), 1.5)
	for sign_x2 in [-1.0, 1.0]:
		var anchor := Vector3(sign_x2 * (half_w - gap), half_h - gap, 0.06)
		var hub := Vector3(0.0, 0.0, spine_z)
		var brace := hub - anchor
		var length := brace.length()
		if length > 0.01:
			var xform := Transform3D(_basis_from_axis(brace), anchor + brace * 0.5)
			_emit_box(truss, xform, Vector3(0.07, length, 0.07), 1.5)

	# Lamp faces, recessed a little behind the frame front so the truss casts a
	# shadow line across the glass.
	var lamp_z := 0.03
	for r2 in range(rws):
		for c2 in range(cols):
			var cx := -half_w + gap + lamp_w * 0.5 + float(c2) * (lamp_w + gap)
			var cy := -half_h + gap + lamp_h * 0.5 + float(r2) * (lamp_h + gap)
			var hw := lamp_w * 0.5
			var hh := lamp_h * 0.5
			_quad_flat(lamps,
				Vector3(cx + hw, cy - hh, lamp_z),
				Vector3(cx - hw, cy - hh, lamp_z),
				Vector3(cx - hw, cy + hh, lamp_z),
				Vector3(cx + hw, cy + hh, lamp_z),
				Vector3(0.0, 0.0, -1.0),
				Vector2(0.0, 1.0), Vector2(1.0, 1.0), Vector2(1.0, 0.0), Vector2(0.0, 0.0))

	var mesh := ArrayMesh.new()
	truss.generate_tangents()
	truss.commit(mesh)
	lamps.generate_tangents()
	lamps.commit(mesh)
	if mesh.get_surface_count() == 2:
		mesh.surface_set_name(0, "truss")
		mesh.surface_set_name(1, "lamps")
	return mesh


# ---------------------------------------------------------------------------
# The humanoid
# ---------------------------------------------------------------------------

## Every mesh of a procedural humanoid, keyed by part name. Keys:
## "pelvis", "torso", "head", "upper_arm", "fore_arm", "hand",
## "thigh", "shin", "foot". Sized for a 1.88 m keeper; scale for the shooter.
##
## The proportions are the classical anthropometric ratios for H = 1.88 m, not
## eyeballed boxes: head 1 / 7.5 of the height, biacromial (shoulder) width
## H / 4, hip joint at 0.53 H, acromion at 0.818 H, upper arm 0.186 H, forearm
## 0.146 H, thigh 0.25 H, shin 0.234 H. Get those wrong and the keeper reads as
## a mannequin however good the animation is, because the eye knows what a human
## looks like long before it knows what a dive looks like.
##
## PLACEMENT. Every part is centred on its own origin and its long axis is +Y,
## so a limb is placed at the MIDPOINT of its two joints and simply aimed. The
## one exception is "foot", whose long axis is -Z (Godot's forward), with the
## origin at the ankle and the sole 0.0375 m below it.
##
## Standing skeleton, so the two body agents can assemble without guessing:
##
##   ankle    y = 0.075      hip       y = 0.985     acromion  y = 1.538
##   knee     y = 0.515      waist     y = 1.165     neck top  y = 1.630
##   wrist    y = 0.880      elbow     y = 1.155     crown     y = 1.880
##   shoulder joint y = 1.505, x = +/- 0.215
##   hip joint      x = +/- 0.095
##
## Part centres follow from those: pelvis 1.055, torso 1.3925, head 1.755,
## upper_arm 1.330, fore_arm 1.0175, hand 0.775, thigh 0.750, shin 0.295,
## foot 0.0375.
static func humanoid_parts() -> Dictionary:
	if _cache.has("humanoid"):
		return _cache["humanoid"]

	var pelvis_rings: Array[Vector3] = [
		Vector3(-0.110, 0.140, 0.098),
		Vector3(-0.040, 0.163, 0.112),
		Vector3(0.045, 0.166, 0.115),
		Vector3(0.110, 0.150, 0.106),
	]
	var torso_rings: Array[Vector3] = [
		Vector3(-0.2375, 0.150, 0.108),
		Vector3(-0.100, 0.172, 0.120),
		Vector3(0.060, 0.196, 0.126),
		Vector3(0.145, 0.235, 0.118),
		Vector3(0.190, 0.130, 0.100),
		Vector3(0.2375, 0.062, 0.062),
	]
	var head_rings: Array[Vector3] = [
		Vector3(-0.125, 0.030, 0.034),
		Vector3(-0.090, 0.058, 0.068),
		Vector3(-0.040, 0.072, 0.090),
		Vector3(0.010, 0.079, 0.098),
		Vector3(0.065, 0.070, 0.086),
		Vector3(0.110, 0.040, 0.048),
		Vector3(0.125, 0.012, 0.014),
	]
	var hand_rings: Array[Vector3] = [
		Vector3(-0.105, 0.030, 0.018),
		Vector3(-0.060, 0.052, 0.026),
		Vector3(0.000, 0.060, 0.030),
		Vector3(0.060, 0.052, 0.030),
		Vector3(0.105, 0.040, 0.028),
	]

	var parts: Dictionary = {
		"pelvis": _tube(pelvis_rings, _RING_SEGMENTS, true, true, Transform3D.IDENTITY),
		"torso": _tube(torso_rings, _RING_SEGMENTS, true, true, Transform3D.IDENTITY),
		"head": _tube(head_rings, _RING_SEGMENTS, true, true, Transform3D.IDENTITY),
		"upper_arm": limb(0.042, 0.056, 0.350),
		"fore_arm": limb(0.032, 0.045, 0.275),
		"hand": _tube(hand_rings, 14, true, true, Transform3D.IDENTITY),
		"thigh": limb(0.070, 0.098, 0.470),
		"shin": limb(0.046, 0.064, 0.440),
		"foot": _boot_mesh(),
	}
	_cache["humanoid"] = parts
	return parts


## The boot: a tapered hexahedron rather than a box, because a football boot is
## wider and taller at the heel than at the toe and a plain box reads as a
## brick. The sole is flat and horizontal, the instep slopes down towards the
## toe. Origin at the ankle, toes towards -Z, sole at y = -0.0375.
static func _boot_mesh() -> ArrayMesh:
	var z_heel := 0.085
	var z_toe := -0.185
	var hw_heel := 0.048
	var hw_toe := 0.036
	var y_sole := -0.0375
	var y_heel := 0.048
	var y_toe := -0.004

	var c := PackedVector3Array([
		Vector3(-hw_heel, y_sole, z_heel),
		Vector3(hw_heel, y_sole, z_heel),
		Vector3(hw_toe, y_sole, z_toe),
		Vector3(-hw_toe, y_sole, z_toe),
		Vector3(-hw_heel, y_heel, z_heel),
		Vector3(hw_heel, y_heel, z_heel),
		Vector3(hw_toe, y_toe, z_toe),
		Vector3(-hw_toe, y_toe, z_toe),
	])

	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_face(st, c, 0, 3, 2, 1)
	_face(st, c, 4, 5, 6, 7)
	_face(st, c, 0, 1, 5, 4)
	_face(st, c, 2, 3, 7, 6)
	_face(st, c, 1, 2, 6, 5)
	_face(st, c, 0, 4, 7, 3)
	return _finish(st)


## One planar quad of a hexahedron, corners counter clockwise seen from outside.
## The normal is derived from the corners rather than declared, so a corner
## typo shows up as a black face instead of as a silently wrong shading.
static func _face(st: SurfaceTool, c: PackedVector3Array, i0: int, i1: int, i2: int, i3: int) -> void:
	var p0 := c[i0]
	var p1 := c[i1]
	var p2 := c[i2]
	var p3 := c[i3]
	var n := (p1 - p0).cross(p2 - p0)
	if n.length_squared() < 1e-12:
		return
	n = n.normalized()
	# Planar UV in metres, taken in the two widest axes of the face.
	var u_axis := (p1 - p0).normalized()
	var v_axis := n.cross(u_axis)
	var uvs := PackedVector2Array()
	for p in [p0, p1, p2, p3]:
		var d: Vector3 = p - p0
		uvs.append(Vector2(d.dot(u_axis), -d.dot(v_axis)))
	_quad_flat(st, p0, p1, p2, p3, n, uvs[0], uvs[1], uvs[2], uvs[3])


static func clear_cache() -> void:
	_cache.clear()
