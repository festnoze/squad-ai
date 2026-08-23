## Procedural building library for CALL OF WAR, Normandy 1942.
##
## Every public builder returns a finished `Node3D`: a handful of
## `MeshInstance3D` children (one per material, so the renderer sees as few
## surfaces as possible) plus exactly one `StaticBody3D` carrying every
## `CollisionShape3D`.
##
## Collision is deliberately made of many axis aligned boxes rather than one
## convex hull: a convex hull would seal the doorways shut and the player would
## bounce off an opening he can plainly see through. Every wall is cut into
## piers, sills and lintels around its real openings, and those pieces are what
## become collision shapes, so a hole in the mesh is a hole in the physics too.
##
## Reference sizes used throughout (a player capsule is 0.40 m of radius and
## 1.80 m tall, so every door is at least 1.55 m wide and 2.10 m tall):
##   wall thickness  0.35 m stone, 0.22 m plank, 0.70 m concrete
##   floor height    2.90 m
##   door            1.60 x 2.20 m
##   window          0.95 x 1.35 m, sill at 1.05 m
##
## All coordinates are LOCAL to the returned node, ground level is y = 0 and the
## foundations already reach down to about -0.40 m so a caller can drop the node
## straight onto the terrain height without it looking like it floats.
class_name Structures
extends RefCounted

# --- Tuning ----------------------------------------------------------------

const WALL_T := 0.35
const PLANK_T := 0.22
const CONCRETE_T := 0.70
const FLOOR_HEIGHT := 2.90
const DOOR_W := 1.60
const DOOR_H := 2.20
const WINDOW_W := 0.95
const WINDOW_H := 1.35
const WINDOW_SILL := 1.05
const COVER_SPACING := 2.5
const COVER_OFFSET := 0.62


## A cover point exposed by a built structure, for the AI.
class CoverPoint extends RefCounted:
	var position: Vector3
	var normal: Vector3     # direction the cover protects FROM
	var is_high: bool       # true = standing cover, false = crouch only

	func _init(new_position: Vector3 = Vector3.ZERO,
			new_normal: Vector3 = Vector3.FORWARD,
			new_is_high: bool = true) -> void:
		position = new_position
		normal = new_normal
		is_high = new_is_high


## One collision box waiting to be turned into a CollisionShape3D.
class _Box extends RefCounted:
	var xform: Transform3D
	var size: Vector3

	func _init(new_xform: Transform3D, new_size: Vector3) -> void:
		xform = new_xform
		size = new_size


## Geometry accumulator. Triangles are grouped per material key so a whole
## building collapses into a handful of draw calls, and collision boxes are
## collected next to them.
##
## Winding note, verified against BoxMesh in this exact engine build: Godot
## treats CLOCKWISE triangles as front facing. `quad()` and `tri()` therefore
## take their vertices counter clockwise as seen from OUTSIDE and flip the
## emission order internally, which keeps every call site readable.
class _Mesher extends RefCounted:
	var _surfaces: Dictionary = {}
	var _shapes: Array = []

	func _st(key: String) -> SurfaceTool:
		if _surfaces.has(key):
			return _surfaces[key] as SurfaceTool
		var st := SurfaceTool.new()
		st.begin(Mesh.PRIMITIVE_TRIANGLES)
		_surfaces[key] = st
		return st

	func _project(p: Vector3, origin: Vector3, u_axis: Vector3,
			v_axis: Vector3, uv_scale: float) -> Vector2:
		var d := p - origin
		return Vector2(d.dot(u_axis), d.dot(v_axis)) * uv_scale

	func _emit(st: SurfaceTool, n: Vector3, a: Vector3, b: Vector3, c: Vector3,
			ua: Vector2, ub: Vector2, uc: Vector2) -> void:
		# Reversed on purpose: see the winding note above.
		st.set_normal(n)
		st.set_uv(ua)
		st.add_vertex(a)
		st.set_normal(n)
		st.set_uv(uc)
		st.add_vertex(c)
		st.set_normal(n)
		st.set_uv(ub)
		st.add_vertex(b)

	## Triangle given counter clockwise as seen from the visible side.
	func tri(a: Vector3, b: Vector3, c: Vector3, key: String,
			uv_scale: float = 0.5) -> void:
		var n := (b - a).cross(c - a)
		if n.length_squared() < 1e-10:
			return
		n = n.normalized()
		var u_axis := (b - a).normalized()
		var v_axis := n.cross(u_axis).normalized()
		var st := _st(key)
		_emit(st, n, a, b, c,
				_project(a, a, u_axis, v_axis, uv_scale),
				_project(b, a, u_axis, v_axis, uv_scale),
				_project(c, a, u_axis, v_axis, uv_scale))

	## Quad given counter clockwise as seen from the visible side.
	func quad(a: Vector3, b: Vector3, c: Vector3, d: Vector3, key: String,
			uv_scale: float = 0.5) -> void:
		var n := (b - a).cross(d - a)
		if n.length_squared() < 1e-10:
			return
		n = n.normalized()
		var u_axis := (b - a).normalized()
		var v_axis := n.cross(u_axis).normalized()
		var st := _st(key)
		var ua := _project(a, a, u_axis, v_axis, uv_scale)
		var ub := _project(b, a, u_axis, v_axis, uv_scale)
		var uc := _project(c, a, u_axis, v_axis, uv_scale)
		var ud := _project(d, a, u_axis, v_axis, uv_scale)
		_emit(st, n, a, b, c, ua, ub, uc)
		_emit(st, n, a, c, d, ua, uc, ud)

	## Oriented box. `solid` also registers a collision shape.
	func box_x(xform: Transform3D, size: Vector3, key: String,
			solid: bool = true, uv_scale: float = 0.5) -> void:
		var h := size * 0.5
		var p000 := xform * Vector3(-h.x, -h.y, -h.z)
		var p100 := xform * Vector3(h.x, -h.y, -h.z)
		var p110 := xform * Vector3(h.x, h.y, -h.z)
		var p010 := xform * Vector3(-h.x, h.y, -h.z)
		var p001 := xform * Vector3(-h.x, -h.y, h.z)
		var p101 := xform * Vector3(h.x, -h.y, h.z)
		var p111 := xform * Vector3(h.x, h.y, h.z)
		var p011 := xform * Vector3(-h.x, h.y, h.z)
		quad(p001, p101, p111, p011, key, uv_scale)   # +Z
		quad(p100, p000, p010, p110, key, uv_scale)   # -Z
		quad(p101, p100, p110, p111, key, uv_scale)   # +X
		quad(p000, p001, p011, p010, key, uv_scale)   # -X
		quad(p011, p111, p110, p010, key, uv_scale)   # +Y
		quad(p000, p100, p101, p001, key, uv_scale)   # -Y
		if solid:
			_shapes.append(_Box.new(xform, size))

	## Axis aligned box centred on `center`.
	func box(center: Vector3, size: Vector3, key: String, solid: bool = true,
			uv_scale: float = 0.5) -> void:
		box_x(Transform3D(Basis.IDENTITY, center), size, key, solid, uv_scale)

	## Collision only, no triangles. Used for ramps and gables where the visual
	## is cheaper to draw than the shape is to describe.
	func collider(xform: Transform3D, size: Vector3) -> void:
		_shapes.append(_Box.new(xform, size))

	func collider_at(center: Vector3, size: Vector3) -> void:
		_shapes.append(_Box.new(Transform3D(Basis.IDENTITY, center), size))

	## Cylinder standing on `base`, extruded along the local +Y of `basis`.
	func cylinder(base: Vector3, radius: float, height: float, sides: int,
			key: String, solid: bool = false,
			basis: Basis = Basis.IDENTITY) -> void:
		var n := maxi(4, sides)
		var top_c := base + basis * Vector3(0.0, height, 0.0)
		for i in n:
			var a0 := TAU * float(i) / float(n)
			var a1 := TAU * float(i + 1) / float(n)
			var r0 := basis * Vector3(cos(a0) * radius, 0.0, sin(a0) * radius)
			var r1 := basis * Vector3(cos(a1) * radius, 0.0, sin(a1) * radius)
			var b0 := base + r0
			var b1 := base + r1
			var t0 := top_c + r0
			var t1 := top_c + r1
			quad(b1, b0, t0, t1, key)
			tri(top_c, t0, t1, key)
			tri(base, b1, b0, key)
		if solid:
			var xf := Transform3D(basis,
					base + basis * Vector3(0.0, height * 0.5, 0.0))
			_shapes.append(_Box.new(xf,
					Vector3(radius * 1.75, height, radius * 1.75)))

	## Square based pyramid, used for spires and roof caps.
	func pyramid(base_center: Vector3, base_size: float, height: float,
			key: String) -> void:
		var h := base_size * 0.5
		var apex := base_center + Vector3(0.0, height, 0.0)
		var c0 := base_center + Vector3(-h, 0.0, -h)
		var c1 := base_center + Vector3(h, 0.0, -h)
		var c2 := base_center + Vector3(h, 0.0, h)
		var c3 := base_center + Vector3(-h, 0.0, h)
		tri(c1, c0, apex, key)
		tri(c2, c1, apex, key)
		tri(c3, c2, apex, key)
		tri(c0, c3, apex, key)

	func shape_count() -> int:
		return _shapes.size()

	## Turns everything accumulated into the final node.
	func finish(node_name: String) -> Node3D:
		var root := Node3D.new()
		root.name = node_name
		var keys := _surfaces.keys()
		keys.sort()
		for k in keys:
			var key := String(k)
			var st := _surfaces[key] as SurfaceTool
			st.generate_tangents()
			var mesh := st.commit()
			if mesh == null:
				continue
			var mi := MeshInstance3D.new()
			mi.name = "M_" + key
			mi.mesh = mesh
			mi.material_override = MatLib.get_material(key)
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			root.add_child(mi)
		var body := StaticBody3D.new()
		body.name = "Body"
		body.collision_layer = Layers.STRUCTURE
		body.collision_mask = 0
		for s in _shapes:
			var b := s as _Box
			if b.size.x <= 0.01 or b.size.y <= 0.01 or b.size.z <= 0.01:
				continue
			var cs := CollisionShape3D.new()
			var shape := BoxShape3D.new()
			shape.size = b.size
			cs.shape = shape
			cs.transform = b.xform
			body.add_child(cs)
		root.add_child(body)
		return root


# --- Cover helpers ---------------------------------------------------------

static func _add_cover(cover_out: Array, position: Vector3, normal: Vector3,
		is_high: bool) -> void:
	var n := normal
	if n.length_squared() < 1e-8:
		n = Vector3.FORWARD
	cover_out.append(CoverPoint.new(position, n.normalized(), is_high))


## Cover points evenly spread along a segment, all sharing one normal.
static func _cover_line(cover_out: Array, from: Vector3, to: Vector3,
		normal: Vector3, spacing: float, is_high: bool) -> void:
	var seg := to - from
	var seg_len := seg.length()
	if seg_len < 0.05:
		return
	var count := maxi(1, int(seg_len / maxf(0.5, spacing)))
	for k in count:
		var t := (float(k) + 0.5) / float(count)
		_add_cover(cover_out, from + seg * t, normal, is_high)


## Cover all the way around a rectangular footprint, normals pointing outwards.
static func _perimeter_cover(cover_out: Array, hw: float, hd: float, y: float,
		offset: float, spacing: float, is_high: bool) -> void:
	var corners: Array[Vector3] = [
		Vector3(-hw, y, -hd), Vector3(hw, y, -hd),
		Vector3(hw, y, hd), Vector3(-hw, y, hd),
	]
	var normals: Array[Vector3] = [
		Vector3(0.0, 0.0, -1.0), Vector3(1.0, 0.0, 0.0),
		Vector3(0.0, 0.0, 1.0), Vector3(-1.0, 0.0, 0.0),
	]
	for i in 4:
		var a: Vector3 = corners[i] + normals[i] * offset
		var b: Vector3 = corners[(i + 1) % 4] + normals[i] * offset
		_cover_line(cover_out, a, b, normals[i], spacing, is_high)


## The four outside corners, which is where the AI likes to peek from.
static func _corner_cover(cover_out: Array, hw: float, hd: float, y: float,
		offset: float, is_high: bool) -> void:
	var signs: Array[Vector2] = [
		Vector2(-1.0, -1.0), Vector2(1.0, -1.0),
		Vector2(1.0, 1.0), Vector2(-1.0, 1.0),
	]
	for s in signs:
		var n := Vector3(s.x, 0.0, s.y).normalized()
		_add_cover(cover_out, Vector3(hw * s.x, y, hd * s.y) + n * offset, n,
				is_high)


# --- Wall helpers ----------------------------------------------------------

## Sorts openings left to right without a lambda, so the helper stays usable
## from a static context on every engine build.
static func _sort_openings(openings: Array) -> Array:
	var out: Array = []
	for raw in openings:
		var op: Vector4 = raw
		var inserted := false
		for i in out.size():
			var other: Vector4 = out[i]
			if op.x < other.x:
				out.insert(i, op)
				inserted = true
				break
		if not inserted:
			out.append(op)
	return out


static func _wall_piece(m: _Mesher, base_center: Vector3, a: float, b: float,
		y0: float, y1: float, thickness: float, axis_x: bool, key: String,
		solid: bool) -> void:
	var run := b - a
	var tall := y1 - y0
	if run <= 0.03 or tall <= 0.03:
		return
	var mid := (a + b) * 0.5
	var cy := base_center.y + (y0 + y1) * 0.5
	if axis_x:
		m.box(Vector3(base_center.x + mid, cy, base_center.z),
				Vector3(run, tall, thickness), key, solid)
	else:
		m.box(Vector3(base_center.x, cy, base_center.z + mid),
				Vector3(thickness, tall, run), key, solid)


## One straight wall band with REAL holes in it.
##
## `base_center.y` is the bottom of the band, `height` its total height.
## `openings` are Vector4(offset along the wall, width, bottom, top), all
## relative to the band. Openings must not overlap horizontally inside one
## band: stack floors by calling this once per floor instead.
static func _wall(m: _Mesher, base_center: Vector3, length: float,
		height: float, thickness: float, axis_x: bool, openings: Array,
		key: String, solid: bool = true) -> void:
	var half := length * 0.5
	var cursor := -half
	for raw in _sort_openings(openings):
		var op: Vector4 = raw
		var left := maxf(op.x - op.y * 0.5, -half)
		var right := minf(op.x + op.y * 0.5, half)
		if right <= cursor + 0.03:
			continue
		var bottom := maxf(op.z, 0.0)
		var top := minf(op.w, height)
		if top <= bottom + 0.05:
			continue
		if left > cursor + 0.03:
			_wall_piece(m, base_center, cursor, left, 0.0, height, thickness,
					axis_x, key, solid)
		if bottom > 0.03:
			_wall_piece(m, base_center, left, right, 0.0, bottom, thickness,
					axis_x, key, solid)
		if top < height - 0.03:
			_wall_piece(m, base_center, left, right, top, height, thickness,
					axis_x, key, solid)
		cursor = right
	if cursor < half - 0.03:
		_wall_piece(m, base_center, cursor, half, 0.0, height, thickness,
				axis_x, key, solid)


## Adds a horizontal cut level, ignoring duplicates within a few centimetres.
static func _add_cut(cuts: Array[float], value: float) -> void:
	for c in cuts:
		if absf(c - value) < 0.04:
			return
	cuts.append(value)


## Wall builder for the case `_wall` cannot express: several openings stacked
## ABOVE ONE ANOTHER at the same offset (a church tower has a portal, a rose
## window and a belfry louvre all on the centre line). The wall is sliced into
## horizontal bands at every opening edge, and each band is then a plain
## `_wall` whose openings no longer overlap.
##
## Getting this wrong is how a cathedral ends up with a walled up front door:
## `_wall` walks its openings left to right, so a tall opening processed first
## fills the whole column below it and seals whatever sat underneath.
static func _wall_bands(m: _Mesher, base_center: Vector3, length: float,
		height: float, thickness: float, axis_x: bool, openings: Array,
		key: String, solid: bool = true) -> void:
	var cuts: Array[float] = [0.0, height]
	for raw in openings:
		var op: Vector4 = raw
		_add_cut(cuts, clampf(op.z, 0.0, height))
		_add_cut(cuts, clampf(op.w, 0.0, height))
	cuts.sort()
	for i in cuts.size() - 1:
		var y0: float = cuts[i]
		var y1: float = cuts[i + 1]
		if y1 - y0 < 0.06:
			continue
		var band: Array = []
		for raw2 in openings:
			var op2: Vector4 = raw2
			if op2.z <= y0 + 0.03 and op2.w >= y1 - 0.03:
				band.append(Vector4(op2.x, op2.y, 0.0, y1 - y0))
		_wall(m, Vector3(base_center.x, base_center.y + y0, base_center.z),
				length, y1 - y0, thickness, axis_x, band, key, solid)


## Rectangular slab with a rectangular hole punched through it, split into up
## to four boxes. Used for upper floors around a stairwell.
static func _slab_with_hole(m: _Mesher, center: Vector3, size_x: float,
		size_z: float, y_top: float, thick: float, hole_min: Vector2,
		hole_max: Vector2, key: String, solid: bool = true) -> void:
	var x0 := center.x - size_x * 0.5
	var x1 := center.x + size_x * 0.5
	var z0 := center.z - size_z * 0.5
	var z1 := center.z + size_z * 0.5
	var hx0 := clampf(hole_min.x, x0, x1)
	var hx1 := clampf(hole_max.x, x0, x1)
	var hz0 := clampf(hole_min.y, z0, z1)
	var hz1 := clampf(hole_max.y, z0, z1)
	var cy := y_top - thick * 0.5
	if hx1 - hx0 < 0.05 or hz1 - hz0 < 0.05:
		m.box(Vector3(center.x, cy, center.z), Vector3(size_x, thick, size_z),
				key, solid)
		return
	var pieces: Array[Vector4] = [
		Vector4(x0, x1, z0, hz0),
		Vector4(x0, x1, hz1, z1),
		Vector4(x0, hx0, hz0, hz1),
		Vector4(hx1, x1, hz0, hz1),
	]
	for p in pieces:
		var w := p.y - p.x
		var d := p.w - p.z
		if w < 0.05 or d < 0.05:
			continue
		m.box(Vector3((p.x + p.y) * 0.5, cy, (p.z + p.w) * 0.5),
				Vector3(w, thick, d), key, solid)


## A flight of stairs: cheap visual steps plus ONE sloped box collider, so the
## physics engine gets a single smooth ramp to walk instead of thirty ledges.
## Keep the run at least 1.4 times the rise or the ramp exceeds the engine
## default floor angle and nobody can climb it.
static func _stairs(m: _Mesher, start: Vector3, top: Vector3, width: float,
		key: String) -> void:
	var flat := Vector3(top.x - start.x, 0.0, top.z - start.z)
	var run := flat.length()
	var rise := top.y - start.y
	if run < 0.4 or rise < 0.3:
		return
	var dir := flat / run
	var steps := clampi(int(round(rise / 0.19)), 4, 32)
	var side := Vector3.UP.cross(dir).normalized()
	var step_basis := Basis(side, Vector3.UP, dir)
	for i in steps:
		var f := float(i + 1) / float(steps)
		var tread_y := start.y + rise * f
		var along := run * (float(i) + 0.5) / float(steps)
		var centre := start + dir * along + Vector3(0.0, rise * f * 0.5, 0.0)
		m.box_x(Transform3D(step_basis, centre),
				Vector3(width, maxf(rise * f, 0.05), run / float(steps)),
				key, false)
	var fwd := Vector3(flat.x, rise, flat.z).normalized()
	var right := Vector3.UP.cross(fwd).normalized()
	var up := fwd.cross(right).normalized()
	var mid := (start + top) * 0.5 - up * 0.17
	m.collider(Transform3D(Basis(right, up, fwd), mid),
			Vector3(width, 0.34, sqrt(run * run + rise * rise)))


## Two roof slopes meeting on a ridge, with the gable triangles that close the
## two ends. The slopes get real collision, the gables get a stepped
## approximation (cheaper than a triangle mesh and good enough to stop a body).
static func _gable_roof(m: _Mesher, center: Vector3, w: float, d: float,
		rise: float, ridge_along_x: bool, overhang: float, key: String,
		gable_key: String, thickness: float = 0.20, solid: bool = true) -> void:
	var yaw := 0.0 if ridge_along_x else PI * 0.5
	var rot := Basis(Vector3.UP, yaw)
	var ww := w if ridge_along_x else d
	var dd := d if ridge_along_x else w
	var hd := dd * 0.5 + overhang
	var slope_len := sqrt(hd * hd + rise * rise)
	var angle := atan2(rise, hd)
	var panel_size := Vector3(ww + overhang * 2.0, thickness, slope_len)
	for s in [1.0, -1.0]:
		var sign_f: float = s
		var tilt := Basis(Vector3.RIGHT, angle * sign_f)
		var normal := rot * (tilt * Vector3.UP)
		var mid := rot * Vector3(0.0, rise * 0.5, hd * 0.5 * sign_f)
		var pos := center + mid + normal * (thickness * 0.5)
		m.box_x(Transform3D(rot * tilt, pos), panel_size, key, solid, 0.35)
	var hd0 := dd * 0.5
	for s2 in [1.0, -1.0]:
		var sx: float = s2
		var gx := ww * 0.5 * sx
		var a := center + rot * Vector3(gx, 0.0, -hd0)
		var b := center + rot * Vector3(gx, 0.0, hd0)
		var apex := center + rot * Vector3(gx, rise, 0.0)
		# Both faces, so the loft is not open to the sky from the inside.
		m.tri(a, b, apex, gable_key)
		m.tri(b, a, apex, gable_key)
		if solid:
			var bands := 4
			for i in bands:
				var f0 := float(i) / float(bands)
				var f1 := float(i + 1) / float(bands)
				var wz := hd0 * (1.0 - (f0 + f1) * 0.5) * 2.0
				if wz < 0.2:
					continue
				var cy := rise * (f0 + f1) * 0.5
				m.collider(Transform3D(rot, center + rot * Vector3(gx, cy, 0.0)),
						Vector3(0.30, rise / float(bands), wz))


## Generates a plausible opening list for one floor band of a wall.
static func _floor_openings(rng: RandomNumberGenerator, length: float,
		door_at: float, has_door: bool, sill: float, chance: float) -> Array:
	var ops: Array = []
	if has_door:
		ops.append(Vector4(door_at, DOOR_W, 0.0, DOOR_H))
	var bays := maxi(1, int(floor(length / 2.55)))
	var step := length / float(bays)
	for b in bays:
		var cx := -length * 0.5 + step * (float(b) + 0.5)
		if has_door and absf(cx - door_at) < (DOOR_W + WINDOW_W) * 0.5 + 0.30:
			continue
		if absf(cx) > length * 0.5 - WINDOW_W * 0.5 - 0.45:
			continue
		if rng.randf() > chance:
			continue
		ops.append(Vector4(cx, WINDOW_W, sill, sill + WINDOW_H))
	return ops


## Wooden lintel and stone sill trim around every opening of a band, so the
## holes read as real windows and not as missing geometry.
static func _opening_trim(m: _Mesher, base_center: Vector3, openings: Array,
		thickness: float, axis_x: bool) -> void:
	for raw in openings:
		var op: Vector4 = raw
		var t := thickness + 0.12
		var lintel_y := base_center.y + op.w + 0.09
		var sill_y := base_center.y + op.z - 0.06
		if axis_x:
			m.box(Vector3(base_center.x + op.x, lintel_y, base_center.z),
					Vector3(op.y + 0.35, 0.18, t), "wood", false)
			if op.z > 0.2:
				m.box(Vector3(base_center.x + op.x, sill_y, base_center.z),
						Vector3(op.y + 0.30, 0.12, t), "stone", false)
		else:
			m.box(Vector3(base_center.x, lintel_y, base_center.z + op.x),
					Vector3(t, 0.18, op.y + 0.35), "wood", false)
			if op.z > 0.2:
				m.box(Vector3(base_center.x, sill_y, base_center.z + op.x),
						Vector3(t, 0.12, op.y + 0.30), "stone", false)


## A pair of open wooden shutters flanking a window opening.
static func _shutters(m: _Mesher, base_center: Vector3, openings: Array,
		thickness: float, axis_x: bool, outward: float) -> void:
	for raw in openings:
		var op: Vector4 = raw
		if op.z < 0.4:
			continue
		var h := op.w - op.z
		var cy := base_center.y + (op.z + op.w) * 0.5
		var off := op.y * 0.5 + 0.22
		var depth := thickness * 0.5 + 0.05
		for s in [-1.0, 1.0]:
			var sf: float = s
			if axis_x:
				m.box(Vector3(base_center.x + op.x + off * sf, cy,
						base_center.z + depth * outward),
						Vector3(0.42, h, 0.07), "wood", false)
			else:
				m.box(Vector3(base_center.x + depth * outward, cy,
						base_center.z + op.x + off * sf),
						Vector3(0.07, h, 0.42), "wood", false)


## Cover for whoever fires from a window: he is behind the sill, so it is low
## cover, and the threat comes from outside.
static func _window_cover(cover_out: Array, base_center: Vector3,
		openings: Array, axis_x: bool, outward: Vector3, inset: float) -> void:
	for raw in openings:
		var op: Vector4 = raw
		if op.z < 0.4:
			continue
		var p: Vector3
		if axis_x:
			p = Vector3(base_center.x + op.x, base_center.y, base_center.z)
		else:
			p = Vector3(base_center.x, base_center.y, base_center.z + op.x)
		_add_cover(cover_out, p - outward * inset, outward, false)


## Half timbered facade decoration (colombage): posts, rails and braces glued
## on the outside of a plaster wall. Visual only, zero collision cost.
static func _timber_frame(m: _Mesher, base_center: Vector3, length: float,
		height: float, axis_x: bool, outward: float, thickness: float) -> void:
	var face := thickness * 0.5 + 0.035
	var posts := maxi(2, int(length / 1.6))
	for i in posts + 1:
		var cx := -length * 0.5 + length * float(i) / float(posts)
		if axis_x:
			m.box(Vector3(base_center.x + cx, base_center.y + height * 0.5,
					base_center.z + face * outward),
					Vector3(0.16, height, 0.07), "wood", false)
		else:
			m.box(Vector3(base_center.x + face * outward,
					base_center.y + height * 0.5, base_center.z + cx),
					Vector3(0.07, height, 0.16), "wood", false)
	for band in [0.0, height - 0.16]:
		var by: float = band
		if axis_x:
			m.box(Vector3(base_center.x, base_center.y + by + 0.08,
					base_center.z + face * outward),
					Vector3(length, 0.16, 0.07), "wood", false)
		else:
			m.box(Vector3(base_center.x + face * outward,
					base_center.y + by + 0.08, base_center.z),
					Vector3(0.07, 0.16, length), "wood", false)


## An open door leaf hanging on the side of an opening, so a doorway reads as a
## door without ever blocking it.
static func _door_leaf(m: _Mesher, hinge: Vector3, width: float, height: float,
		yaw: float) -> void:
	var b := Basis(Vector3.UP, yaw)
	var centre := hinge + b * Vector3(width * 0.5, height * 0.5, 0.0)
	m.box_x(Transform3D(b, centre), Vector3(width, height, 0.08), "wood", false)


## A short arc of stacked sandbags, courses offset like real bricklaying.
static func _sandbag_arc(m: _Mesher, centre: Vector3, radius: float,
		from_angle: float, to_angle: float, courses: int,
		solid: bool = true) -> void:
	var arc := to_angle - from_angle
	var span := absf(arc) * radius
	var per_course := maxi(3, int(span / 0.78))
	for c in courses:
		var y := centre.y + 0.19 + float(c) * 0.34
		var jitter := 0.5 if (c % 2) == 1 else 0.0
		for i in per_course:
			var t := (float(i) + 0.5 + jitter) / float(per_course)
			var ang := from_angle + arc * t
			var p := centre + Vector3(cos(ang) * radius, y - centre.y,
					sin(ang) * radius)
			var b := Basis(Vector3.UP, -ang)
			m.box_x(Transform3D(b, p), Vector3(0.30, 0.32, 0.76), "sandbag",
					false)
	if solid:
		var chunks := maxi(3, int(span / 1.6))
		var height := float(courses) * 0.34 + 0.04
		for i in chunks:
			var t := (float(i) + 0.5) / float(chunks)
			var ang := from_angle + arc * t
			var p := centre + Vector3(cos(ang) * radius, height * 0.5,
					sin(ang) * radius)
			m.collider(Transform3D(Basis(Vector3.UP, -ang), p),
					Vector3(0.55, height, span / float(chunks) + 0.25))


## Barbed wire fence run along local X: leaning posts and five taut strands.
static func _wire_run(m: _Mesher, centre: Vector3, length: float,
		solid: bool = true) -> void:
	var posts := maxi(2, int(length / 2.6))
	for i in posts + 1:
		var x := centre.x - length * 0.5 + length * float(i) / float(posts)
		var lean := Basis(Vector3.FORWARD, 0.05 * (1.0 if (i % 2) == 0 else -1.0))
		m.box_x(Transform3D(lean, Vector3(x, centre.y + 0.68, centre.z)),
				Vector3(0.12, 1.36, 0.12), "wood", false)
	for k in 5:
		var y := centre.y + 0.28 + float(k) * 0.26
		m.box(Vector3(centre.x, y, centre.z), Vector3(length, 0.05, 0.05),
				"barbed_wire", false)
	for k2 in 2:
		var y2 := centre.y + 0.45 + float(k2) * 0.55
		m.box(Vector3(centre.x, y2, centre.z), Vector3(length, 0.04, 0.04),
				"barbed_wire", false)
	if solid:
		var chunks := maxi(1, int(length / 6.0))
		for i in chunks:
			var t := (float(i) + 0.5) / float(chunks)
			m.collider_at(Vector3(centre.x - length * 0.5 + length * t,
					centre.y + 0.65, centre.z),
					Vector3(length / float(chunks), 1.30, 0.40))


## Clips a list of absolute openings Vector4(offset, width, y_bottom, y_top)
## into one wall band, returning them relative to the band bottom.
static func _clip_openings(openings: Array, y0: float, y1: float) -> Array:
	var out: Array = []
	for raw in openings:
		var op: Vector4 = raw
		var b := maxf(op.z, y0)
		var t := minf(op.w, y1)
		if t <= b + 0.05:
			continue
		out.append(Vector4(op.x, op.y, b - y0, t - y0))
	return out


# --- Church geometry, published so a site can aim a sniper at the belfry ----

const CHURCH_NAVE_W := 10.0
const CHURCH_NAVE_D := 20.0
const CHURCH_TOWER_SIZE := 6.4
const CHURCH_TOWER_H := 17.0
const CHURCH_BELFRY_Y := 13.4
const CHURCH_TOWER_Z := -(CHURCH_NAVE_D * 0.5 + CHURCH_TOWER_SIZE * 0.5 - 0.4)


# ===========================================================================
# Public builders
# ===========================================================================

## A Normandy village house: rubble limestone or half timbering, very steep
## slate or tile roof, stone chimney on the gable. Hollow, with a real front
## doorway, real window holes, a floor per storey and a staircase when there is
## more than one.
static func house(rng: RandomNumberGenerator, width: float, depth: float,
		floors: int, cover_out: Array) -> Node3D:
	var w := clampf(width, 5.0, 16.0)
	var d := clampf(depth, 4.5, 12.0)
	var n_floors := clampi(floors, 1, 3)
	var m := _Mesher.new()
	var hw := w * 0.5
	var hd := d * 0.5
	var half_timber := rng.randf() < 0.42
	var wall_key := "plaster" if half_timber else "stone"
	var roof_key := "roof_slate" if rng.randf() < 0.58 else "roof_tile"
	var eave := FLOOR_HEIGHT * float(n_floors) + 0.25
	var side_len := d - WALL_T * 2.0

	# Foundations, sunk well below ground so the house never floats.
	m.box(Vector3(0.0, -0.22, 0.0), Vector3(w + 0.34, 0.44, d + 0.34), "stone")

	var front_z := -hd + WALL_T * 0.5
	var back_z := hd - WALL_T * 0.5
	var left_x := -hw + WALL_T * 0.5
	var right_x := hw - WALL_T * 0.5
	var door_at := roundf(rng.randf_range(-w * 0.22, w * 0.22) * 4.0) * 0.25
	var back_door := rng.randf() < 0.5
	var back_door_at := roundf(rng.randf_range(-w * 0.2, w * 0.2) * 4.0) * 0.25

	for f in n_floors:
		var y0 := FLOOR_HEIGHT * float(f)
		var band := FLOOR_HEIGHT if f < n_floors - 1 else eave - y0
		var sill := WINDOW_SILL if f == 0 else 0.85
		var front_ops := _floor_openings(rng, w, door_at, f == 0, sill, 0.9)
		var back_ops := _floor_openings(rng, w, back_door_at,
				back_door and f == 0, sill, 0.75)
		var left_ops := _floor_openings(rng, side_len, 0.0, false, sill, 0.62)
		var right_ops := _floor_openings(rng, side_len, 0.0, false, sill, 0.62)
		var front_c := Vector3(0.0, y0, front_z)
		var back_c := Vector3(0.0, y0, back_z)
		var left_c := Vector3(left_x, y0, 0.0)
		var right_c := Vector3(right_x, y0, 0.0)
		_wall(m, front_c, w, band, WALL_T, true, front_ops, wall_key)
		_wall(m, back_c, w, band, WALL_T, true, back_ops, wall_key)
		_wall(m, left_c, side_len, band, WALL_T, false, left_ops, wall_key)
		_wall(m, right_c, side_len, band, WALL_T, false, right_ops, wall_key)
		_opening_trim(m, front_c, front_ops, WALL_T, true)
		_opening_trim(m, back_c, back_ops, WALL_T, true)
		_opening_trim(m, left_c, left_ops, WALL_T, false)
		_opening_trim(m, right_c, right_ops, WALL_T, false)
		_shutters(m, front_c, front_ops, WALL_T, true, -1.0)
		_shutters(m, back_c, back_ops, WALL_T, true, 1.0)
		if half_timber and f > 0:
			_timber_frame(m, front_c, w, band, true, -1.0, WALL_T)
			_timber_frame(m, back_c, w, band, true, 1.0, WALL_T)
		if f == 0:
			_window_cover(cover_out, front_c, front_ops, true,
					Vector3(0.0, 0.0, -1.0), 0.75)
			_window_cover(cover_out, back_c, back_ops, true,
					Vector3(0.0, 0.0, 1.0), 0.75)
			_window_cover(cover_out, left_c, left_ops, false,
					Vector3(-1.0, 0.0, 0.0), 0.75)
			_window_cover(cover_out, right_c, right_ops, false,
					Vector3(1.0, 0.0, 0.0), 0.75)

	# Open door leaves, so a doorway reads as a door yet never blocks it.
	_door_leaf(m, Vector3(door_at - DOOR_W * 0.5, 0.02, front_z - WALL_T * 0.5),
			DOOR_W * 0.92, DOOR_H - 0.08, -0.9)
	if back_door:
		_door_leaf(m, Vector3(back_door_at + DOOR_W * 0.5, 0.02,
				back_z + WALL_T * 0.5), DOOR_W * 0.92, DOOR_H - 0.08, PI + 0.9)

	# Upper floors plus their staircase, hugging the back wall.
	var inner_w := w - WALL_T * 2.0
	var inner_d := d - WALL_T * 2.0
	var stair_w := minf(1.30, inner_d - 0.6)
	var run := clampf(inner_w - 0.5, 3.7, 4.6)
	var stair_z := hd - WALL_T - stair_w * 0.5 - 0.1
	var x_start := -inner_w * 0.5 + 0.2
	for f in range(1, n_floors):
		var y_top := FLOOR_HEIGHT * float(f)
		var hole_min := Vector2(x_start + run - 2.6, stair_z - stair_w * 0.6)
		var hole_max := Vector2(x_start + run + 0.4, stair_z + stair_w * 0.6)
		_slab_with_hole(m, Vector3.ZERO, inner_w + 0.25, inner_d + 0.25, y_top,
				0.22, hole_min, hole_max, "wood")
		_stairs(m, Vector3(x_start, y_top - FLOOR_HEIGHT, stair_z),
				Vector3(x_start + run, y_top, stair_z), stair_w, "wood")
		# Two visible ceiling beams under the slab.
		for k in 2:
			var bz := -inner_d * 0.25 + inner_d * 0.5 * float(k)
			m.box(Vector3(0.0, y_top - 0.34, bz), Vector3(inner_w, 0.20, 0.20),
					"wood", false)

	# Roof and chimney.
	var rise := clampf(d * 0.62, 2.2, 5.2)
	_gable_roof(m, Vector3(0.0, eave, 0.0), w, d, rise, true, 0.45, roof_key,
			wall_key)
	var chim_side := 1.0 if rng.randf() < 0.5 else -1.0
	var chim_x := (hw - 0.55) * chim_side
	var chim_z := rng.randf_range(-hd * 0.3, hd * 0.3)
	var chim_bottom := eave - 1.2
	var chim_top := eave + rise + 1.35
	m.box(Vector3(chim_x, (chim_bottom + chim_top) * 0.5, chim_z),
			Vector3(0.95, chim_top - chim_bottom, 0.95), "stone")
	m.box(Vector3(chim_x, chim_top + 0.09, chim_z), Vector3(1.15, 0.18, 1.15),
			"stone", false)

	# Cover: the whole outside wall line, the four corners, both door jambs.
	_perimeter_cover(cover_out, hw, hd, 0.0, COVER_OFFSET, COVER_SPACING, true)
	_corner_cover(cover_out, hw, hd, 0.0, 0.85, true)
	for s in [-1.0, 1.0]:
		var sf: float = s
		_add_cover(cover_out,
				Vector3(door_at + sf * (DOOR_W * 0.5 + 0.55), 0.0, -hd - 0.5),
				Vector3(0.0, 0.0, -1.0), true)
	return m.finish("House")


## The long Normandy barn: stone plinth, plank walls, exposed truss, a cart
## sized doorway on the long side and a hay loft at one end.
static func barn(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := rng.randf_range(15.0, 20.0)
	var d := rng.randf_range(8.5, 11.0)
	var hw := w * 0.5
	var hd := d * 0.5
	var wall_h := 4.7
	var plinth := 1.15
	var side_len := d - WALL_T * 2.0
	var big_door_w := 4.2
	var big_door_h := 3.8

	m.box(Vector3(0.0, -0.22, 0.0), Vector3(w + 0.3, 0.44, d + 0.3), "stone")

	var front_c := Vector3(0.0, 0.0, -hd + WALL_T * 0.5)
	var back_c := Vector3(0.0, 0.0, hd - WALL_T * 0.5)
	var left_c := Vector3(-hw + WALL_T * 0.5, 0.0, 0.0)
	var right_c := Vector3(hw - WALL_T * 0.5, 0.0, 0.0)
	var front_abs: Array = [Vector4(0.0, big_door_w, 0.0, big_door_h)]
	var back_abs: Array = [Vector4(hw * 0.4, DOOR_W, 0.0, DOOR_H)]
	var side_abs: Array = []
	for k in 2:
		side_abs.append(Vector4(-side_len * 0.24 + side_len * 0.48 * float(k),
				0.85, 3.05, 3.85))
	var left_abs: Array = side_abs.duplicate()
	var right_abs: Array = side_abs.duplicate()
	right_abs.append(Vector4(-side_len * 0.05, DOOR_W, 0.0, DOOR_H))

	var bands: Array[Vector2] = [Vector2(0.0, plinth), Vector2(plinth, wall_h)]
	var band_keys: PackedStringArray = ["stone", "wood"]
	for i in bands.size():
		var y0: float = bands[i].x
		var y1: float = bands[i].y
		var key := band_keys[i]
		_wall(m, Vector3(front_c.x, y0, front_c.z), w, y1 - y0, WALL_T, true,
				_clip_openings(front_abs, y0, y1), key)
		_wall(m, Vector3(back_c.x, y0, back_c.z), w, y1 - y0, WALL_T, true,
				_clip_openings(back_abs, y0, y1), key)
		_wall(m, Vector3(left_c.x, y0, left_c.z), side_len, y1 - y0, WALL_T,
				false, _clip_openings(left_abs, y0, y1), key)
		_wall(m, Vector3(right_c.x, y0, right_c.z), side_len, y1 - y0, WALL_T,
				false, _clip_openings(right_abs, y0, y1), key)

	# Vertical plank battens on the long walls.
	_timber_frame(m, Vector3(0.0, plinth, front_c.z), w, wall_h - plinth, true,
			-1.0, WALL_T)
	_timber_frame(m, Vector3(0.0, plinth, back_c.z), w, wall_h - plinth, true,
			1.0, WALL_T)
	m.box(Vector3(0.0, big_door_h + 0.14, front_c.z),
			Vector3(big_door_w + 0.7, 0.28, WALL_T + 0.2), "wood", false)

	# Interior: posts, tie beams, hay loft and its stair.
	var inner_w := w - WALL_T * 2.0
	var inner_d := d - WALL_T * 2.0
	var loft_x0 := hw - WALL_T - inner_w * 0.36
	for k in 4:
		var px := -inner_w * 0.36 + inner_w * 0.24 * float(k)
		for pz in [-inner_d * 0.28, inner_d * 0.28]:
			var pzz: float = pz
			m.box(Vector3(px, 1.85, pzz), Vector3(0.26, 3.7, 0.26), "wood")
		m.box(Vector3(px, 3.85, 0.0), Vector3(0.22, 0.22, inner_d), "wood",
				false)
	var loft_w := (hw - WALL_T) - loft_x0
	m.box(Vector3(loft_x0 + loft_w * 0.5, 3.0 - 0.11, 0.0),
			Vector3(loft_w, 0.22, inner_d), "wood")
	m.box(Vector3(loft_x0, 3.45, 0.0), Vector3(0.14, 0.9, inner_d), "wood",
			false)
	_stairs(m, Vector3(loft_x0 - 4.1, 0.0, -inner_d * 0.5 + 0.75),
			Vector3(loft_x0 + 0.2, 3.0, -inner_d * 0.5 + 0.75), 1.15, "wood")

	var rise := d * 0.52
	_gable_roof(m, Vector3(0.0, wall_h, 0.0), w, d, rise, true, 0.5,
			"roof_tile", "wood")

	_perimeter_cover(cover_out, hw, hd, 0.0, COVER_OFFSET, COVER_SPACING, true)
	_corner_cover(cover_out, hw, hd, 0.0, 0.9, true)
	for s in [-1.0, 1.0]:
		var sf: float = s
		_add_cover(cover_out, Vector3(sf * (big_door_w * 0.5 + 0.6), 0.0,
				-hd - 0.5), Vector3(0.0, 0.0, -1.0), true)
		_add_cover(cover_out, Vector3(sf * (big_door_w * 0.5 + 0.6), 0.0,
				-hd + 1.3), Vector3(0.0, 0.0, -1.0), false)
	_add_cover(cover_out, Vector3(loft_x0 + loft_w * 0.5, 3.0, -inner_d * 0.5),
			Vector3(0.0, 0.0, -1.0), false)
	return m.finish("Barn")


## Village church: stone nave, square bell tower with an internal stair that
## really goes up, louvred belfry openings and a slate spire. The belfry
## platform sits at CHURCH_BELFRY_Y and is meant to hold a sniper.
static func church(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := CHURCH_NAVE_W
	var d := CHURCH_NAVE_D
	var hw := w * 0.5
	var hd := d * 0.5
	var wall_h := 7.2
	var t := 0.55
	var side_len := d - t * 2.0
	var tower := CHURCH_TOWER_SIZE
	var ht := tower * 0.5
	var tz := CHURCH_TOWER_Z
	var tower_t := 0.60
	var tower_h := CHURCH_TOWER_H
	var arch_w := 2.4
	var arch_h := 3.4

	m.box(Vector3(0.0, -0.24, 0.0), Vector3(w + 0.4, 0.48, d + 0.4), "stone")
	m.box(Vector3(0.0, -0.24, tz), Vector3(tower + 0.5, 0.48, tower + 0.5),
			"stone")

	# --- Nave -------------------------------------------------------------
	var nave_side: Array = []
	var bays := 5
	for b in bays:
		var cz := -side_len * 0.5 + side_len * (float(b) + 0.5) / float(bays)
		nave_side.append(Vector4(cz, 0.85, 2.6, 5.4))
	var front_c := Vector3(0.0, 0.0, -hd + t * 0.5)
	var back_c := Vector3(0.0, 0.0, hd - t * 0.5)
	var left_c := Vector3(-hw + t * 0.5, 0.0, 0.0)
	var right_c := Vector3(hw - t * 0.5, 0.0, 0.0)
	_wall(m, front_c, w, wall_h, t, true,
			[Vector4(0.0, arch_w, 0.0, arch_h)], "stone")
	_wall(m, back_c, w, wall_h, t, true,
			[Vector4(0.0, 1.5, 3.4, 4.9)], "stone")
	_wall(m, left_c, side_len, wall_h, t, false, nave_side, "stone")
	_wall(m, right_c, side_len, wall_h, t, false,
			nave_side + [Vector4(side_len * 0.32, DOOR_W, 0.0, DOOR_H)],
			"stone")
	_opening_trim(m, left_c, nave_side, t, false)
	_opening_trim(m, right_c, nave_side, t, false)
	_window_cover(cover_out, left_c, nave_side, false, Vector3(-1.0, 0.0, 0.0),
			0.8)
	_window_cover(cover_out, right_c, nave_side, false, Vector3(1.0, 0.0, 0.0),
			0.8)
	# Buttresses along the nave.
	for b2 in bays + 1:
		var bz := -side_len * 0.5 + side_len * float(b2) / float(bays)
		for s in [-1.0, 1.0]:
			var sf: float = s
			m.box(Vector3(sf * (hw + 0.28), 2.4, bz),
					Vector3(0.65, 4.8, 0.75), "stone")
	_gable_roof(m, Vector3(0.0, wall_h, 0.0), w, d, 5.0, false, 0.4,
			"roof_slate", "stone")

	# Nave interior: flagstone floor, pews and an altar.
	m.box(Vector3(0.0, -0.06, 0.0), Vector3(w - t * 2.0, 0.12, side_len),
			"stone")
	var rows := 9
	for r in rows:
		var pz := -side_len * 0.38 + side_len * 0.66 * float(r) / float(rows)
		for s2 in [-1.0, 1.0]:
			var sf2: float = s2
			m.box(Vector3(sf2 * 2.1, 0.45, pz), Vector3(3.0, 0.14, 0.42),
					"wood", false)
			m.box(Vector3(sf2 * 2.1, 0.78, pz + 0.22),
					Vector3(3.0, 0.72, 0.10), "wood", false)
	m.box(Vector3(0.0, 0.45, hd - 2.4), Vector3(2.6, 0.9, 1.1), "stone")

	# --- Tower ------------------------------------------------------------
	var belfry_ops: Array = [Vector4(0.0, 1.25, CHURCH_BELFRY_Y + 0.3,
			CHURCH_BELFRY_Y + 2.9)]
	var tower_walls: Array[Vector3] = [
		Vector3(0.0, 0.0, tz - ht + tower_t * 0.5),
		Vector3(0.0, 0.0, tz + ht - tower_t * 0.5),
		Vector3(-ht + tower_t * 0.5, 0.0, tz),
		Vector3(ht - tower_t * 0.5, 0.0, tz),
	]
	var tower_side := tower - tower_t * 2.0
	for i in 4:
		var axis_x := i < 2
		var length := tower if axis_x else tower_side
		var ops: Array = belfry_ops.duplicate()
		if i == 0:
			ops.append(Vector4(0.0, 1.9, 0.0, 2.9))          # main portal
			ops.append(Vector4(0.0, 1.2, 4.4, 6.2))          # rose window
		elif i == 1:
			ops.append(Vector4(0.0, arch_w, 0.0, arch_h))    # into the nave
		else:
			ops.append(Vector4(0.0, 0.75, 6.5, 8.3))
			ops.append(Vector4(0.0, 0.75, 9.8, 11.6))
		_wall_bands(m, tower_walls[i], length, tower_h, tower_t, axis_x, ops,
				"stone")
	# Corner pilasters.
	for cx in [-1.0, 1.0]:
		for cz in [-1.0, 1.0]:
			var fx: float = cx
			var fz: float = cz
			m.box(Vector3(fx * (ht - 0.15), tower_h * 0.5, tz + fz * (ht - 0.15)),
					Vector3(0.75, tower_h, 0.75), "stone", false)
	m.box(Vector3(0.0, tower_h + 0.22, tz), Vector3(tower + 0.9, 0.44,
			tower + 0.9), "stone")
	m.pyramid(Vector3(0.0, tower_h + 0.44, tz), tower + 0.6, 7.4, "roof_slate")

	# Tower stair: four flights around the inside, landings in the corners.
	var inner := tower - tower_t * 2.0
	var reach := inner * 0.5 - 0.42
	var flight_rise := CHURCH_BELFRY_Y / 4.0
	var stair_w := 1.15
	# The first flight starts on the +X wall on purpose: a flight across the
	# -Z wall would hang right in front of the portal and block the entrance.
	var corners: Array[Vector3] = [
		Vector3(reach, 0.0, tz - reach),
		Vector3(reach, 0.0, tz + reach),
		Vector3(-reach, 0.0, tz + reach),
		Vector3(-reach, 0.0, tz - reach),
	]
	for i in 4:
		var a: Vector3 = corners[i]
		var b: Vector3 = corners[(i + 1) % 4]
		var y0 := flight_rise * float(i)
		var y1 := flight_rise * float(i + 1)
		_stairs(m, Vector3(a.x, y0, a.z), Vector3(b.x, y1, b.z), stair_w,
				"wood")
		m.box(Vector3(b.x, y1 - 0.11, b.z), Vector3(1.35, 0.22, 1.35), "wood")
	var hole_min := Vector2(reach - 2.0, tz - reach - 0.8)
	var hole_max := Vector2(reach + 0.9, tz - reach + 0.8)
	_slab_with_hole(m, Vector3(0.0, 0.0, tz), inner + 0.2, inner + 0.2,
			CHURCH_BELFRY_Y, 0.24, hole_min, hole_max, "wood")
	# The bell.
	m.cylinder(Vector3(0.0, CHURCH_BELFRY_Y + 2.6, tz), 0.55, 0.9, 10, "metal")

	# Cover: nave perimeter, tower base, and the belfry itself.
	_perimeter_cover(cover_out, hw, hd, 0.0, COVER_OFFSET, COVER_SPACING, true)
	_corner_cover(cover_out, hw, hd, 0.0, 0.95, true)
	_perimeter_cover(cover_out, ht, ht, 0.0, COVER_OFFSET, COVER_SPACING * 1.4,
			true)
	var belfry_normals: Array[Vector3] = [
		Vector3(0.0, 0.0, -1.0), Vector3(0.0, 0.0, 1.0),
		Vector3(-1.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0),
	]
	for n in belfry_normals:
		_add_cover(cover_out, Vector3(0.0, CHURCH_BELFRY_Y, tz)
				+ n * (ht - 1.1), n, false)
	return m.finish("Church")


## German coastal bunker: raw concrete, two firing embrasures on the front, a
## protected entrance at the back, an earth and sandbag revetment that makes it
## look half buried, and an outside ramp up to the roof.
##
## The floor is kept at y = 0 rather than dug in: the terrain is a heightfield
## and cannot be carved, so a buried floor would simply be unreachable.
static func bunker(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := 11.4
	var d := 8.6
	var hw := w * 0.5
	var hd := d * 0.5
	var t := CONCRETE_T
	var wall_h := 3.15
	var side_len := d - t * 2.0

	m.box(Vector3(0.0, -0.3, 0.0), Vector3(w + 0.5, 0.6, d + 0.5), "concrete")
	m.box(Vector3(0.0, -0.05, 0.0), Vector3(w - t * 2.0, 0.1, side_len),
			"concrete")

	var emb_h := 0.68
	var emb_y := 1.32
	var front_ops: Array = [
		Vector4(-w * 0.22, 2.7, emb_y, emb_y + emb_h),
		Vector4(w * 0.22, 2.7, emb_y, emb_y + emb_h),
	]
	var back_ops: Array = [Vector4(-w * 0.24, DOOR_W, 0.0, DOOR_H)]
	var side_ops: Array = [Vector4(side_len * 0.22, 1.1, emb_y, emb_y + emb_h)]
	var front_c := Vector3(0.0, 0.0, -hd + t * 0.5)
	var back_c := Vector3(0.0, 0.0, hd - t * 0.5)
	var left_c := Vector3(-hw + t * 0.5, 0.0, 0.0)
	var right_c := Vector3(hw - t * 0.5, 0.0, 0.0)
	_wall(m, front_c, w, wall_h, t, true, front_ops, "concrete")
	_wall(m, back_c, w, wall_h, t, true, back_ops, "concrete")
	_wall(m, left_c, side_len, wall_h, t, false, side_ops, "concrete")
	_wall(m, right_c, side_len, wall_h, t, false, [], "concrete")

	# Roof slab and its drip lip.
	m.box(Vector3(0.0, wall_h + 0.32, 0.0), Vector3(w + 0.7, 0.64, d + 0.7),
			"concrete")
	for s in [-1.0, 1.0]:
		var sf: float = s
		m.box(Vector3(0.0, wall_h + 0.86, sf * (hd + 0.2)),
				Vector3(w + 0.7, 0.44, 0.3), "concrete")
		m.box(Vector3(sf * (hw + 0.2), wall_h + 0.86, 0.0),
				Vector3(0.3, 0.44, d + 0.7), "concrete")

	# Blast wall shielding the doorway.
	m.box(Vector3(-w * 0.24 + 1.55, 1.35, hd + 1.65), Vector3(0.55, 2.7, 3.1),
			"concrete")
	m.box(Vector3(-w * 0.24 + 0.4, 1.35, hd + 3.05), Vector3(3.2, 2.7, 0.55),
			"concrete")

	# Firing step under the embrasures, so a soldier inside reaches them.
	m.box(Vector3(0.0, 0.22, -hd + t + 0.55), Vector3(w - t * 2.0, 0.44, 1.1),
			"concrete")

	# Earth and rubble revetment, the "half buried" look.
	var berm_h := 1.75
	for i in 3:
		var f := float(i) / 3.0
		var y := berm_h * (1.0 - f) * 0.5
		var thick := 2.6 * (1.0 - f) + 0.4
		var hgt := berm_h * (1.0 - f)
		if hgt < 0.2:
			continue
		m.box(Vector3(0.0, y, -hd - thick * 0.5), Vector3(w + thick, hgt, thick),
				"stone", i == 0)
		# Only the -X flank gets a berm: the +X flank carries the roof ramp.
		m.box(Vector3(-(hw + thick * 0.5), y, 0.0), Vector3(thick, hgt, d),
				"stone", i == 0)
	_sandbag_arc(m, Vector3(0.0, wall_h + 0.64, 0.0), hw + 0.15, PI * 0.62,
			PI * 1.38, 2, true)

	# Ramp to the roof on the +X side.
	_stairs(m, Vector3(hw + 6.0, 0.0, -hd * 0.4),
			Vector3(hw - 0.2, wall_h + 0.64, -hd * 0.4), 1.4, "concrete")

	# Cover.
	_perimeter_cover(cover_out, hw + 1.2, hd + 1.2, 0.0, 0.5, COVER_SPACING,
			true)
	_corner_cover(cover_out, hw, hd, 0.0, 1.4, true)
	for raw in front_ops:
		var op: Vector4 = raw
		_add_cover(cover_out, Vector3(op.x, 0.44, -hd + t + 0.9),
				Vector3(0.0, 0.0, -1.0), false)
	_perimeter_cover(cover_out, hw - 0.5, hd - 0.5, wall_h + 0.64, -0.4, 3.0,
			false)
	_add_cover(cover_out, Vector3(-w * 0.24, 0.0, hd + 1.2),
			Vector3(0.0, 0.0, 1.0), true)
	return m.finish("Bunker")


## Luftwaffe field hangar: steel frame, corrugated sheet cladding, a completely
## open front so an aircraft fits through, and a service door at the back.
static func hangar(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := rng.randf_range(22.0, 26.0)
	var d := rng.randf_range(15.0, 18.0)
	var hw := w * 0.5
	var hd := d * 0.5
	var wall_h := 7.2
	var t := 0.30
	var side_len := d - t * 2.0
	var mouth := w * 0.62

	m.box(Vector3(0.0, -0.22, 0.0), Vector3(w + 0.4, 0.44, d + 0.4), "concrete")
	m.box(Vector3(0.0, -0.04, 0.0), Vector3(w - 0.2, 0.08, d - 0.2), "concrete")

	var front_c := Vector3(0.0, 0.0, -hd + t * 0.5)
	var back_c := Vector3(0.0, 0.0, hd - t * 0.5)
	var left_c := Vector3(-hw + t * 0.5, 0.0, 0.0)
	var right_c := Vector3(hw - t * 0.5, 0.0, 0.0)
	_wall(m, front_c, w, wall_h, t, true,
			[Vector4(0.0, mouth, 0.0, 6.6)], "metal")
	_wall(m, back_c, w, wall_h, t, true,
			[Vector4(w * 0.3, DOOR_W, 0.0, DOOR_H),
			Vector4(-w * 0.3, DOOR_W, 0.0, DOOR_H)], "metal")
	_wall(m, left_c, side_len, wall_h, t, false,
			[Vector4(0.0, 2.2, 4.6, 6.0)], "metal")
	_wall(m, right_c, side_len, wall_h, t, false,
			[Vector4(0.0, 2.2, 4.6, 6.0)], "metal")

	# Steel frame: portal columns and a truss under every ridge bay.
	var bays := 5
	for i in bays + 1:
		var x := -hw + w * float(i) / float(bays)
		for s in [-1.0, 1.0]:
			var sf: float = s
			m.box(Vector3(x, wall_h * 0.5, sf * (hd - 0.35)),
					Vector3(0.32, wall_h, 0.32), "metal", i > 0 and i < bays)
		m.box(Vector3(x, wall_h + 0.25, 0.0), Vector3(0.24, 0.24, d), "metal",
				false)
	m.box(Vector3(0.0, 6.75, -hd + 0.2), Vector3(mouth + 1.6, 0.5, 0.5),
			"metal", false)

	var rise := d * 0.22
	_gable_roof(m, Vector3(0.0, wall_h, 0.0), w, d, rise, true, 0.55, "metal",
			"metal")

	# A little clutter inside: crates and drums.
	for i in 6:
		var cx := rng.randf_range(-hw + 2.0, hw - 2.0)
		var cz := rng.randf_range(1.0, hd - 1.5)
		var sz := rng.randf_range(0.7, 1.2)
		m.box_x(Transform3D(Basis(Vector3.UP, rng.randf_range(0.0, TAU)),
				Vector3(cx, sz * 0.5, cz)), Vector3(sz * 1.4, sz, sz * 1.1),
				"wood")
		_add_cover(cover_out, Vector3(cx, 0.0, cz - sz), Vector3(0.0, 0.0, -1.0),
				false)
	for i in 4:
		var bx := -hw + 1.4 + float(i) * 0.8
		m.cylinder(Vector3(bx, 0.0, hd - 1.6), 0.32, 0.92, 10, "rust", true)

	_perimeter_cover(cover_out, hw, hd, 0.0, COVER_OFFSET, COVER_SPACING, true)
	_corner_cover(cover_out, hw, hd, 0.0, 1.0, true)
	for s2 in [-1.0, 1.0]:
		var sf2: float = s2
		_add_cover(cover_out, Vector3(sf2 * (mouth * 0.5 + 0.7), 0.0, -hd + 1.2),
				Vector3(0.0, 0.0, -1.0), true)
	return m.finish("Hangar")


## Guard tower (mirador): four legs, an outside stair that really climbs, a
## railed platform and a plank roof. The platform is high cover for a sentry.
static func watchtower(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var leg := 2.25
	var reach := 2.75
	var deck_y := 8.1
	var deck_half := 3.25
	var rail_h := 1.05

	m.box(Vector3(0.0, -0.2, 0.0), Vector3(leg * 2.0 + 1.0, 0.4,
			leg * 2.0 + 1.0), "stone")
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var fx: float = sx
			var fz: float = sz
			m.box(Vector3(fx * leg, deck_y * 0.5, fz * leg),
					Vector3(0.34, deck_y, 0.34), "wood")
	# Cross bracing between the legs.
	for i in 3:
		var y := 1.9 + float(i) * 2.1
		for s in [-1.0, 1.0]:
			var sf: float = s
			m.box(Vector3(sf * leg, y, 0.0), Vector3(0.16, 0.16, leg * 2.0),
					"wood", false)
			m.box(Vector3(0.0, y, sf * leg), Vector3(leg * 2.0, 0.16, 0.16),
					"wood", false)

	# Three flights wrapping the outside of the legs.
	var corners: Array[Vector3] = [
		Vector3(reach, 0.0, -reach),
		Vector3(reach, 0.0, reach),
		Vector3(-reach, 0.0, reach),
		Vector3(-reach, 0.0, -reach),
	]
	var flight := deck_y / 3.0
	for i in 3:
		var a: Vector3 = corners[i]
		var b: Vector3 = corners[i + 1]
		_stairs(m, Vector3(a.x, flight * float(i), a.z),
				Vector3(b.x, flight * float(i + 1), b.z), 1.1, "wood")
		m.box(Vector3(b.x, flight * float(i + 1) - 0.11, b.z),
				Vector3(1.3, 0.22, 1.3), "wood")

	# Deck with the stair hole in the corner the last flight arrives at.
	_slab_with_hole(m, Vector3.ZERO, deck_half * 2.0, deck_half * 2.0, deck_y,
			0.24, Vector2(-reach - 0.85, -reach - 0.85),
			Vector2(-reach + 0.85, -reach + 1.6), "wood")
	# Railing, waist high, with a gap above the stair hole.
	var rail_ops: Array = [Vector4(-reach, 2.1, 0.0, rail_h)]
	_wall(m, Vector3(0.0, deck_y, -deck_half + 0.09), deck_half * 2.0, rail_h,
			0.18, true, rail_ops, "wood")
	_wall(m, Vector3(0.0, deck_y, deck_half - 0.09), deck_half * 2.0, rail_h,
			0.18, true, [], "wood")
	_wall(m, Vector3(-deck_half + 0.09, deck_y, 0.0), deck_half * 2.0 - 0.36,
			rail_h, 0.18, false, rail_ops, "wood")
	_wall(m, Vector3(deck_half - 0.09, deck_y, 0.0), deck_half * 2.0 - 0.36,
			rail_h, 0.18, false, [], "wood")
	# Roof on four short posts, plus a searchlight box.
	for sx2 in [-1.0, 1.0]:
		for sz2 in [-1.0, 1.0]:
			var gx: float = sx2
			var gz: float = sz2
			m.box(Vector3(gx * (deck_half - 0.4), deck_y + 1.25,
					gz * (deck_half - 0.4)), Vector3(0.18, 2.5, 0.18), "wood",
					false)
	_gable_roof(m, Vector3(0.0, deck_y + 2.5, 0.0), deck_half * 2.0 + 0.5,
			deck_half * 2.0 + 0.5, 0.9, true, 0.25, "wood", "wood", 0.16, false)
	m.box(Vector3(0.0, deck_y + 1.15, -deck_half + 0.4),
			Vector3(0.7, 0.55, 0.55), "metal", false)

	_perimeter_cover(cover_out, deck_half - 0.45, deck_half - 0.45, deck_y,
			-0.35, 2.0, false)
	_perimeter_cover(cover_out, leg + 0.3, leg + 0.3, 0.0, 0.4, 2.4, false)
	return m.finish("Watchtower")


## A ring of sandbags with one entrance gap: the standard German weapon pit.
static func sandbag_ring(rng: RandomNumberGenerator, radius: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var r := clampf(radius, 1.6, 7.0)
	var gap := rng.randf_range(0.55, 0.85)
	var gap_at := rng.randf_range(0.0, TAU)
	var courses := 3
	_sandbag_arc(m, Vector3.ZERO, r, gap_at + gap, gap_at + TAU - gap, courses,
			true)
	# Trodden earth inside the pit.
	m.cylinder(Vector3(0.0, -0.08, 0.0), r + 0.35, 0.1, 14, "stone", false)
	var height := float(courses) * 0.34
	var stations := maxi(4, int((TAU - gap * 2.0) * r / 1.7))
	for i in stations:
		var t := (float(i) + 0.5) / float(stations)
		var ang := gap_at + gap + (TAU - gap * 2.0) * t
		var n := Vector3(cos(ang), 0.0, sin(ang))
		_add_cover(cover_out, n * (r - 0.75), n, false)
	_add_cover(cover_out, Vector3(cos(gap_at), 0.0, sin(gap_at)) * (r + 1.0),
			Vector3(cos(gap_at), 0.0, sin(gap_at)), false)
	return m.finish("SandbagRing")


## A stretch of trench. The terrain cannot be dug, so it is built upwards: two
## parapets with a 1.8 m lane between them, revetted with planks, duckboards on
## the floor and sandbags crowning the enemy facing side.
static func trench(rng: RandomNumberGenerator, length: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var len_x := clampf(length, 6.0, 60.0)
	var lane := 1.8
	var front_h := 1.42
	var rear_h := 1.0
	var thick := 1.15
	var front_z := -(lane * 0.5 + thick * 0.5)
	var rear_z := lane * 0.5 + thick * 0.5

	m.box(Vector3(0.0, front_h * 0.5, front_z), Vector3(len_x, front_h, thick),
			"stone")
	m.box(Vector3(0.0, rear_h * 0.5, rear_z), Vector3(len_x, rear_h, thick),
			"stone")
	# Plank revetment facing the lane.
	m.box(Vector3(0.0, front_h * 0.5, front_z + thick * 0.5 + 0.05),
			Vector3(len_x, front_h, 0.1), "wood", false)
	m.box(Vector3(0.0, rear_h * 0.5, rear_z - thick * 0.5 - 0.05),
			Vector3(len_x, rear_h, 0.1), "wood", false)
	# Duckboards.
	var boards := maxi(2, int(len_x / 0.6))
	for i in boards:
		var x := -len_x * 0.5 + len_x * (float(i) + 0.5) / float(boards)
		m.box(Vector3(x, 0.05, 0.0), Vector3(len_x / float(boards) - 0.08, 0.1,
				lane - 0.1), "wood", false)
	# Sandbag crown on the enemy side, plus a few firing steps.
	var bags := maxi(3, int(len_x / 0.8))
	for i in bags:
		var x := -len_x * 0.5 + len_x * (float(i) + 0.5) / float(bags)
		m.box(Vector3(x, front_h + 0.16, front_z), Vector3(0.74, 0.32, thick
				- 0.2), "sandbag", false)
	m.collider_at(Vector3(0.0, front_h + 0.16, front_z),
			Vector3(len_x, 0.32, thick - 0.2))
	var steps := maxi(2, int(len_x / 6.0))
	for i in steps:
		var x := -len_x * 0.5 + len_x * (float(i) + 0.5) / float(steps)
		m.box(Vector3(x, 0.22, front_z + thick * 0.5 + 0.35),
				Vector3(1.6, 0.44, 0.7), "wood")
	# Traverse spurs that break blast without blocking the lane.
	var spurs := maxi(1, int(len_x / 9.0))
	for i in spurs:
		var x := -len_x * 0.5 + len_x * (float(i) + 0.7) / float(spurs)
		m.box(Vector3(x, front_h * 0.5, 0.35), Vector3(0.7, front_h, 0.9),
				"stone")

	_cover_line(cover_out, Vector3(-len_x * 0.5, 0.0, front_z + thick * 0.5
			+ 0.55), Vector3(len_x * 0.5, 0.0, front_z + thick * 0.5 + 0.55),
			Vector3(0.0, 0.0, -1.0), 2.0, false)
	_cover_line(cover_out, Vector3(-len_x * 0.5, 0.0, rear_z - thick * 0.5
			- 0.55), Vector3(len_x * 0.5, 0.0, rear_z - thick * 0.5 - 0.55),
			Vector3(0.0, 0.0, 1.0), 3.0, false)
	return m.finish("Trench")


## Dry stone field wall (muret) with capstones and, sometimes, a gateway gap.
static func stone_wall(rng: RandomNumberGenerator, length: float, height: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var len_x := clampf(length, 1.5, 70.0)
	var h := clampf(height, 0.6, 3.2)
	var t := 0.46
	var ops: Array = []
	if len_x > 7.0 and rng.randf() < 0.45:
		var gate_at := rng.randf_range(-len_x * 0.3, len_x * 0.3)
		ops.append(Vector4(gate_at, 1.9, 0.0, h + 0.4))
	_wall(m, Vector3.ZERO, len_x, h, t, true, ops, "stone")
	# Capstones on top, with a little height noise so it never looks extruded.
	var caps := maxi(2, int(len_x / 0.85))
	for i in caps:
		var x := -len_x * 0.5 + len_x * (float(i) + 0.5) / float(caps)
		var skip := false
		for raw in ops:
			var op: Vector4 = raw
			if absf(x - op.x) < op.y * 0.5 + 0.2:
				skip = true
		if skip:
			continue
		var jitter := rng.randf_range(-0.05, 0.06)
		m.box(Vector3(x, h + 0.09 + jitter, 0.0),
				Vector3(len_x / float(caps) - 0.05, 0.2, t + 0.14), "stone",
				false)
	var is_high := h >= 1.55
	for s in [-1.0, 1.0]:
		var sf: float = s
		var n := Vector3(0.0, 0.0, sf)
		_cover_line(cover_out, Vector3(-len_x * 0.5, 0.0, sf * (t * 0.5 + 0.5)),
				Vector3(len_x * 0.5, 0.0, sf * (t * 0.5 + 0.5)), n,
				COVER_SPACING, is_high)
	return m.finish("StoneWall")


## Fuel dump: stacked drums, crates and a sandbag blast wall. This is the
## target of the "detruire le depot" objectives, hence the tight cluster.
static func fuel_depot(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	m.box(Vector3(0.0, -0.08, 0.0), Vector3(9.0, 0.16, 7.0), "stone", false)
	# Standing drums, four by three.
	for ix in 4:
		for iz in 3:
			if rng.randf() < 0.12:
				continue
			var x := -1.9 + float(ix) * 0.78
			var z := -0.9 + float(iz) * 0.78
			var key := "rust" if rng.randf() < 0.45 else "metal"
			m.cylinder(Vector3(x, 0.0, z), 0.31, 0.92, 10, key, false)
	m.collider_at(Vector3(-0.75, 0.46, 0.0), Vector3(3.6, 0.92, 2.4))
	# A leaning pyramid of drums on their side.
	for row in 3:
		var count := 4 - row
		for i in count:
			var x := 2.6 + float(i) * 0.95 + float(row) * 0.48
			var y := 0.31 + float(row) * 0.6
			m.cylinder(Vector3(x, y, -1.6), 0.30, 0.90, 10, "rust", false,
					Basis(Vector3.RIGHT, PI * 0.5))
	m.collider_at(Vector3(3.9, 0.75, -1.15), Vector3(4.0, 1.5, 1.2))
	# Crates and a sandbag blast wall on the exposed side.
	for i in 5:
		var cx := rng.randf_range(-3.4, 3.4)
		var s := rng.randf_range(0.65, 1.0)
		m.box_x(Transform3D(Basis(Vector3.UP, rng.randf_range(0.0, TAU)),
				Vector3(cx, s * 0.5, 2.3)), Vector3(s * 1.5, s, s * 1.1),
				"wood")
	_sandbag_arc(m, Vector3(0.0, 0.0, -3.1), 4.6, PI * 1.16, PI * 1.84, 3, true)
	_cover_line(cover_out, Vector3(-3.6, 0.0, 1.6), Vector3(3.6, 0.0, 1.6),
			Vector3(0.0, 0.0, 1.0), 2.0, false)
	_cover_line(cover_out, Vector3(-3.6, 0.0, -1.9), Vector3(3.6, 0.0, -1.9),
			Vector3(0.0, 0.0, -1.0), 2.0, false)
	return m.finish("FuelDepot")


## Flakvierling style anti aircraft mount on a concrete pad ringed by sandbags.
static func aa_gun(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var pad_r := 3.4
	m.cylinder(Vector3(0.0, -0.3, 0.0), pad_r, 0.42, 14, "concrete", true)
	_sandbag_arc(m, Vector3(0.0, 0.12, 0.0), pad_r + 0.55, 0.55, TAU - 0.55, 3,
			true)
	# Pedestal, turntable, seats.
	var yaw := rng.randf_range(0.0, TAU)
	var turret := Basis(Vector3.UP, yaw)
	m.cylinder(Vector3(0.0, 0.12, 0.0), 0.62, 0.55, 10, "gun_metal", true)
	m.box_x(Transform3D(turret, Vector3(0.0, 0.92, 0.0)),
			Vector3(1.5, 0.5, 1.5), "gun_metal")
	m.box_x(Transform3D(turret, turret * Vector3(0.0, 1.25, -0.85)),
			Vector3(0.55, 0.18, 0.5), "gun_metal", false)
	# Four barrels, elevated.
	var elev := rng.randf_range(0.5, 0.95)
	var barrel_basis := turret * Basis(Vector3.RIGHT, -elev)
	for ix in 2:
		for iy in 2:
			var off := turret * Vector3(-0.24 + 0.48 * float(ix),
					1.18 + 0.36 * float(iy), 0.0)
			m.cylinder(Vector3(0.0, 0.0, 0.0) + off, 0.075, 2.3, 8, "gun_metal",
					false, barrel_basis)
	m.box_x(Transform3D(turret, turret * Vector3(0.0, 1.35, 0.45)),
			Vector3(1.9, 1.0, 0.12), "gun_metal", false)
	# Ammunition boxes.
	for i in 4:
		var ang := TAU * float(i) / 4.0 + 0.4
		m.box_x(Transform3D(Basis(Vector3.UP, -ang),
				Vector3(cos(ang) * 2.5, 0.35, sin(ang) * 2.5)),
				Vector3(0.7, 0.45, 0.4), "metal")
	var stations := 8
	for i in stations:
		var ang2 := TAU * float(i) / float(stations)
		var n := Vector3(cos(ang2), 0.0, sin(ang2))
		_add_cover(cover_out, n * (pad_r - 0.4), n, false)
	return m.finish("AaGun")


## Radio mast: a tapering lattice tower with guy wires and a signals hut you
## can walk into. Target of the "detruire le mat radio" objective.
static func radio_mast(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var height := 23.0
	var base_r := 1.15
	var top_r := 0.32
	var sections := 11
	m.box(Vector3(0.0, -0.25, 0.0), Vector3(3.4, 0.5, 3.4), "concrete")
	for i in sections:
		var y0 := height * float(i) / float(sections)
		var y1 := height * float(i + 1) / float(sections)
		var r0 := lerpf(base_r, top_r, float(i) / float(sections))
		var r1 := lerpf(base_r, top_r, float(i + 1) / float(sections))
		for c in 4:
			var ang := TAU * float(c) / 4.0 + PI * 0.25
			var p0 := Vector3(cos(ang) * r0, y0, sin(ang) * r0)
			var p1 := Vector3(cos(ang) * r1, y1, sin(ang) * r1)
			var mid := (p0 + p1) * 0.5
			var dir := (p1 - p0)
			var l := dir.length()
			var fwd := dir / l
			var right := Vector3.UP.cross(fwd)
			if right.length_squared() < 1e-6:
				right = Vector3.RIGHT
			right = right.normalized()
			var up := fwd.cross(right).normalized()
			m.box_x(Transform3D(Basis(right, up, fwd), mid),
					Vector3(0.11, 0.11, l), "metal", false)
			# Horizontal girt plus one diagonal per face.
			var ang_n := TAU * float((c + 1) % 4) / 4.0 + PI * 0.25
			var q1 := Vector3(cos(ang_n) * r1, y1, sin(ang_n) * r1)
			_strut(m, p1, q1, 0.08, "metal")
			_strut(m, p0, q1, 0.07, "metal")
	m.collider_at(Vector3(0.0, height * 0.5, 0.0),
			Vector3(base_r * 1.4, height, base_r * 1.4))
	# Guy wires down to three concrete anchors.
	for i in 3:
		var ang3 := TAU * float(i) / 3.0
		var anchor := Vector3(cos(ang3) * 8.0, 0.4, sin(ang3) * 8.0)
		m.box(anchor + Vector3(0.0, -0.35, 0.0), Vector3(0.7, 0.7, 0.7),
				"concrete")
		_strut(m, Vector3(0.0, height * 0.72, 0.0), anchor, 0.05,
				"barbed_wire")
	# Signals hut.
	_hut_geometry(m, Vector3(4.6, 0.0, 3.4), 3.6, 3.0, 2.55, "wood",
			"roof_tile", false, cover_out)
	_add_cover(cover_out, Vector3(0.0, 0.0, -base_r - 0.9),
			Vector3(0.0, 0.0, -1.0), false)
	return m.finish("RadioMast")


## Prisoner cage: barbed wire panels on wooden posts, a gate left open so the
## rescue objective is actually completable, and a plank lean to for shelter.
static func prison_cage(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var half := 4.6
	var gate_w := 2.0
	m.box(Vector3(0.0, -0.06, 0.0), Vector3(half * 2.0, 0.12, half * 2.0),
			"stone", false)
	for side in 4:
		var ang := TAU * float(side) / 4.0
		var n := Vector3(cos(ang), 0.0, sin(ang))
		var tang := Vector3(-sin(ang), 0.0, cos(ang))
		var centre := n * half
		var posts := 5
		for i in posts + 1:
			var p := centre + tang * (-half + 2.0 * half * float(i)
					/ float(posts))
			m.box(p + Vector3(0.0, 1.1, 0.0), Vector3(0.14, 2.2, 0.14), "wood",
					false)
		for k in 7:
			var y := 0.22 + float(k) * 0.3
			var a := centre - tang * half + Vector3(0.0, y, 0.0)
			var b := centre + tang * half + Vector3(0.0, y, 0.0)
			if side == 0:
				# Leave the gate opening free of wire and of collision.
				_strut(m, a, centre - tang * (gate_w * 0.5)
						+ Vector3(0.0, y, 0.0), 0.045, "barbed_wire")
				_strut(m, centre + tang * (gate_w * 0.5)
						+ Vector3(0.0, y, 0.0), b, 0.045, "barbed_wire")
			else:
				_strut(m, a, b, 0.045, "barbed_wire")
		if side == 0:
			for s in [-1.0, 1.0]:
				var sf: float = s
				var seg := half - gate_w * 0.5
				m.collider_at(centre + tang * (sf * (gate_w * 0.5 + seg * 0.5))
						+ Vector3(0.0, 1.05, 0.0),
						Vector3(absf(tang.x) * seg + absf(n.x) * 0.3, 2.1,
						absf(tang.z) * seg + absf(n.z) * 0.3))
			# Gate leaf, swung wide open.
			_door_leaf(m, centre - tang * (gate_w * 0.5) + Vector3(0.0, 0.05,
					0.0), gate_w * 0.9, 2.0, ang + PI * 0.5 + 1.2)
		else:
			m.collider_at(centre + Vector3(0.0, 1.05, 0.0),
					Vector3(absf(tang.x) * half * 2.0 + absf(n.x) * 0.3, 2.1,
					absf(tang.z) * half * 2.0 + absf(n.z) * 0.3))
		m.box(centre + Vector3(0.0, 2.3, 0.0),
				Vector3(absf(tang.x) * half * 2.0 + 0.16, 0.12,
				absf(tang.z) * half * 2.0 + 0.16), "wood", false)
	# Lean to shelter with a straw floor.
	m.box(Vector3(-half * 0.45, 1.0, half * 0.5), Vector3(3.6, 2.0, 0.14),
			"wood")
	m.box_x(Transform3D(Basis(Vector3.RIGHT, -0.42),
			Vector3(-half * 0.45, 2.1, half * 0.5 - 1.1)),
			Vector3(3.8, 0.12, 2.6), "wood")
	m.box(Vector3(-half * 0.45, 0.06, half * 0.5 - 1.1),
			Vector3(3.6, 0.12, 2.2), "wheat", false)
	_add_cover(cover_out, Vector3(-half * 0.45, 0.0, half * 0.5 - 0.45),
			Vector3(0.0, 0.0, 1.0), false)
	_perimeter_cover(cover_out, half, half, 0.0, 0.8, 3.2, false)
	return m.finish("PrisonCage")


## A bombed out house. Gutted walls of random height, a chimney still standing,
## fallen beams and heaps of rubble. Excellent close quarters ground.
static func ruin(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := rng.randf_range(7.5, 11.0)
	var d := rng.randf_range(6.0, 8.5)
	var hw := w * 0.5
	var hd := d * 0.5
	var t := WALL_T
	m.box(Vector3(0.0, -0.18, 0.0), Vector3(w + 0.3, 0.36, d + 0.3), "stone")

	var sides: Array[Vector3] = [
		Vector3(0.0, 0.0, -hd + t * 0.5), Vector3(hw - t * 0.5, 0.0, 0.0),
		Vector3(0.0, 0.0, hd - t * 0.5), Vector3(-hw + t * 0.5, 0.0, 0.0),
	]
	var normals: Array[Vector3] = [
		Vector3(0.0, 0.0, -1.0), Vector3(1.0, 0.0, 0.0),
		Vector3(0.0, 0.0, 1.0), Vector3(-1.0, 0.0, 0.0),
	]
	for i in 4:
		var axis_x := (i % 2) == 0
		var length := w if axis_x else d - t * 2.0
		var pieces := maxi(3, int(length / 1.9))
		for k in pieces:
			if rng.randf() < 0.22:
				continue
			var seg := length / float(pieces)
			var off := -length * 0.5 + seg * (float(k) + 0.5)
			var h := rng.randf_range(0.55, 3.3)
			if rng.randf() < 0.2:
				h = rng.randf_range(3.3, 4.4)
			var c := sides[i]
			if axis_x:
				m.box(Vector3(c.x + off, h * 0.5, c.z),
						Vector3(seg + 0.02, h, t), "stone")
			else:
				m.box(Vector3(c.x, h * 0.5, c.z + off),
						Vector3(t, h, seg + 0.02), "stone")
			var p := Vector3(c.x, 0.0, c.z) + normals[i] * 0.6
			if axis_x:
				p.x += off
			else:
				p.z += off
			_add_cover(cover_out, p, normals[i], h >= 1.55)
			_add_cover(cover_out, p - normals[i] * 1.35, -normals[i],
					h >= 1.55)
	# The chimney stack always survives.
	var cx := (hw - 0.6) * (1.0 if rng.randf() < 0.5 else -1.0)
	var chim_h := rng.randf_range(4.5, 7.0)
	m.box(Vector3(cx, chim_h * 0.5, rng.randf_range(-hd * 0.3, hd * 0.3)),
			Vector3(0.9, chim_h, 0.9), "stone")
	# Fallen roof beams.
	for i in 4:
		var ang := rng.randf_range(0.0, TAU)
		var tilt := rng.randf_range(0.35, 1.1)
		var b := Basis(Vector3.UP, ang) * Basis(Vector3.RIGHT, tilt)
		m.box_x(Transform3D(b, Vector3(rng.randf_range(-hw, hw), 0.6,
				rng.randf_range(-hd, hd))), Vector3(0.22, 0.22,
				rng.randf_range(3.0, 6.0)), "wood", false)
	# Rubble heaps, inside and out.
	for i in 9:
		var rx := rng.randf_range(-hw - 2.5, hw + 2.5)
		var rz := rng.randf_range(-hd - 2.5, hd + 2.5)
		var rh := rng.randf_range(0.4, 1.15)
		m.box_x(Transform3D(Basis(Vector3.UP, rng.randf_range(0.0, TAU)),
				Vector3(rx, rh * 0.4, rz)),
				Vector3(rng.randf_range(1.4, 3.0), rh,
				rng.randf_range(1.2, 2.6)), "stone")
		_add_cover(cover_out, Vector3(rx, 0.0, rz - 1.4),
				Vector3(0.0, 0.0, -1.0), false)
	return m.finish("Ruin")


## Stone arch bridge. The deck top sits at y = 0 so it lines straight up with
## the road, and the piers reach down to the river bed.
static func bridge(rng: RandomNumberGenerator, span: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var length := clampf(span, 14.0, 70.0)
	var width := 6.8
	var half_w := width * 0.5
	var deck_bottom := -0.75
	var foot := -7.5
	var arches := clampi(int(length / 11.0), 1, 4)
	var pier_w := 2.4
	var abut := 2.4
	var opening := (length - abut * 2.0 - pier_w * float(arches - 1))
	opening = clampf(opening / float(arches), 3.5, 9.0)
	var used := opening * float(arches) + pier_w * float(arches - 1)
	abut = maxf(1.2, (length - used) * 0.5)

	# Deck.
	m.box(Vector3(0.0, deck_bottom * 0.5, 0.0),
			Vector3(length, -deck_bottom, width), "stone")
	# Abutments and piers.
	for s in [-1.0, 1.0]:
		var sf: float = s
		m.box(Vector3(sf * (length * 0.5 - abut * 0.5),
				(foot + deck_bottom) * 0.5, 0.0),
				Vector3(abut, deck_bottom - foot, width), "stone")
	var first := -length * 0.5 + abut
	for i in arches - 1:
		var px := first + opening * float(i + 1) + pier_w * (float(i) + 0.5)
		m.box(Vector3(px, (foot + deck_bottom) * 0.5, 0.0),
				Vector3(pier_w, deck_bottom - foot, width), "stone")
		# Cutwater on the upstream side.
		m.box_x(Transform3D(Basis(Vector3.UP, PI * 0.25),
				Vector3(px, -2.4, -half_w)), Vector3(1.5, 5.6, 1.5), "stone",
				false)
	# Spandrel columns following each arch curve.
	var r := opening * 0.5
	var spring := deck_bottom - 0.35 - r
	for i in arches:
		var centre := first + opening * (float(i) + 0.5) + pier_w * float(i)
		var cols := maxi(8, int(opening / 0.45))
		for k in cols:
			var u := -r + opening * (float(k) + 0.5) / float(cols)
			var dy := sqrt(maxf(r * r - u * u, 0.0))
			var bottom := spring + dy
			if bottom >= deck_bottom - 0.05:
				continue
			m.box(Vector3(centre + u, (bottom + deck_bottom) * 0.5, 0.0),
					Vector3(opening / float(cols) + 0.02,
					deck_bottom - bottom, width), "stone", k % 3 == 0)
	# Parapets with capstones.
	for s2 in [-1.0, 1.0]:
		var sf2: float = s2
		var pz := sf2 * (half_w - 0.24)
		m.box(Vector3(0.0, 0.52, pz), Vector3(length, 1.04, 0.48), "stone")
		var caps := maxi(4, int(length / 0.9))
		for k in caps:
			var x := -length * 0.5 + length * (float(k) + 0.5) / float(caps)
			m.box(Vector3(x, 1.11, pz), Vector3(length / float(caps) - 0.04,
					0.14, 0.64), "stone", false)
		_cover_line(cover_out,
				Vector3(-length * 0.5 + 1.0, 0.0, pz - sf2 * 0.6),
				Vector3(length * 0.5 - 1.0, 0.0, pz - sf2 * 0.6),
				Vector3(0.0, 0.0, sf2), COVER_SPACING, false)
	return m.finish("Bridge")


# ===========================================================================
# Small props. Private, but SiteBuilder leans on them to dress a site.
# ===========================================================================

## A thin oriented bar between two points: bracing, wires, guy lines.
static func _strut(m: _Mesher, a: Vector3, b: Vector3, thickness: float,
		key: String) -> void:
	var dir := b - a
	var l := dir.length()
	if l < 0.05:
		return
	var fwd := dir / l
	var right := Vector3.UP.cross(fwd)
	if right.length_squared() < 1e-6:
		right = Vector3.RIGHT
	right = right.normalized()
	var up := fwd.cross(right).normalized()
	m.box_x(Transform3D(Basis(right, up, fwd), (a + b) * 0.5),
			Vector3(thickness, thickness, l), key, false)


## Four walls, a floor, a real doorway on the -Z side and a gable roof, drawn
## straight into an existing mesher. Used for huts, guard posts and barracks.
static func _hut_geometry(m: _Mesher, centre: Vector3, w: float, d: float,
		h: float, key: String, roof_key: String, extra_doors: bool,
		cover_out: Array) -> void:
	var t := 0.24
	var hw := w * 0.5
	var hd := d * 0.5
	var side_len := d - t * 2.0
	var door_w := minf(DOOR_W, w - 1.0)
	var door_h := minf(DOOR_H, h - 0.25)
	m.box(centre + Vector3(0.0, -0.18, 0.0),
			Vector3(w + 0.24, 0.36, d + 0.24), "stone")
	var front_ops: Array = [Vector4(0.0, door_w, 0.0, door_h)]
	var back_ops: Array = []
	if extra_doors:
		back_ops.append(Vector4(0.0, door_w, 0.0, door_h))
	var side_ops: Array = []
	var bays := maxi(1, int(side_len / 2.4))
	for b in bays:
		var cz := -side_len * 0.5 + side_len * (float(b) + 0.5) / float(bays)
		side_ops.append(Vector4(cz, 0.85, h * 0.42, h * 0.42 + 0.9))
	_wall(m, centre + Vector3(0.0, 0.0, -hd + t * 0.5), w, h, t, true,
			front_ops, key)
	_wall(m, centre + Vector3(0.0, 0.0, hd - t * 0.5), w, h, t, true,
			back_ops, key)
	_wall(m, centre + Vector3(-hw + t * 0.5, 0.0, 0.0), side_len, h, t, false,
			side_ops, key)
	_wall(m, centre + Vector3(hw - t * 0.5, 0.0, 0.0), side_len, h, t, false,
			side_ops, key)
	_gable_roof(m, centre + Vector3(0.0, h, 0.0), w, d, d * 0.34, true, 0.32,
			roof_key, key)
	_perimeter_cover(cover_out, hw, hd, centre.y, COVER_OFFSET, COVER_SPACING,
			true)
	_window_cover(cover_out, centre + Vector3(-hw + t * 0.5, 0.0, 0.0),
			side_ops, false, Vector3(-1.0, 0.0, 0.0), 0.7)
	_window_cover(cover_out, centre + Vector3(hw - t * 0.5, 0.0, 0.0),
			side_ops, false, Vector3(1.0, 0.0, 0.0), 0.7)


## Village well: stone kerb, a timber frame and a bucket.
static func _well(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	m.cylinder(Vector3(0.0, -0.15, 0.0), 1.05, 1.05, 12, "stone", true)
	m.cylinder(Vector3(0.0, 0.86, 0.0), 0.82, 0.06, 12, "stone", false)
	for s in [-1.0, 1.0]:
		var sf: float = s
		m.box(Vector3(sf * 0.95, 1.45, 0.0), Vector3(0.16, 2.0, 0.16), "wood")
	m.box(Vector3(0.0, 2.4, 0.0), Vector3(2.3, 0.14, 0.14), "wood", false)
	m.cylinder(Vector3(-0.5, 2.2, 0.0), 0.12, 1.0, 8, "wood", false,
			Basis(Vector3.FORWARD, PI * 0.5))
	_strut(m, Vector3(0.35, 2.33, 0.0), Vector3(0.35, 1.35, 0.0), 0.04,
			"barbed_wire")
	m.cylinder(Vector3(0.35, 1.05, 0.0), 0.22, 0.3, 8, "wood", false)
	_gable_roof(m, Vector3(0.0, 2.4, 0.0), 2.6, 2.0, 0.7, true, 0.25,
			"roof_tile", "wood", 0.12, false)
	var ring := 6
	for i in ring:
		var ang := TAU * float(i) / float(ring)
		var n := Vector3(cos(ang), 0.0, sin(ang))
		_add_cover(cover_out, n * 1.65, n, false)
	return m.finish("Well")


## Post and rail fence, one straight run along local X.
static func _wood_fence(rng: RandomNumberGenerator, length: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var len_x := clampf(length, 2.0, 60.0)
	var posts := maxi(2, int(len_x / 2.3))
	for i in posts + 1:
		var x := -len_x * 0.5 + len_x * float(i) / float(posts)
		m.box(Vector3(x, 0.62, 0.0), Vector3(0.15, 1.35, 0.15), "wood", false)
	for k in 2:
		m.box(Vector3(0.0, 0.55 + float(k) * 0.52, 0.0),
				Vector3(len_x, 0.11, 0.07), "wood", false)
	var chunks := maxi(1, int(len_x / 5.0))
	for i in chunks:
		var t := (float(i) + 0.5) / float(chunks)
		m.collider_at(Vector3(-len_x * 0.5 + len_x * t, 0.6, 0.0),
				Vector3(len_x / float(chunks), 1.2, 0.2))
	_cover_line(cover_out, Vector3(-len_x * 0.5, 0.0, -0.55),
			Vector3(len_x * 0.5, 0.0, -0.55), Vector3(0.0, 0.0, -1.0), 4.0,
			false)
	return m.finish("Fence")


## Barbed wire entanglement, one straight run along local X.
static func _wire_fence(rng: RandomNumberGenerator, length: float) -> Node3D:
	var m := _Mesher.new()
	_wire_run(m, Vector3.ZERO, clampf(length, 2.0, 80.0), true)
	return m.finish("Wire")


## Round hay stack, the classic bit of Normandy field cover.
static func _haystack(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var r := rng.randf_range(1.7, 2.4)
	var h := rng.randf_range(1.5, 2.1)
	m.cylinder(Vector3(0.0, 0.0, 0.0), r, h, 10, "wheat", true)
	m.pyramid(Vector3(0.0, h, 0.0), r * 1.9, r * 0.95, "wheat")
	var ring := 6
	for i in ring:
		var ang := TAU * float(i) / float(ring) + rng.randf_range(0.0, 0.5)
		var n := Vector3(cos(ang), 0.0, sin(ang))
		_add_cover(cover_out, n * (r + 0.6), n, h >= 1.75)
	return m.finish("Haystack")


## Checkpoint boom barrier with its counterweight and concrete blocks.
static func _barrier(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	m.box(Vector3(0.0, 0.25, 0.0), Vector3(0.6, 0.5, 0.6), "concrete")
	m.box(Vector3(0.0, 0.85, 0.0), Vector3(0.22, 1.2, 0.22), "wood")
	var lifted := rng.randf() < 0.35
	var boom_len := 5.4
	if lifted:
		m.box_x(Transform3D(Basis(Vector3.FORWARD, PI * 0.42),
				Vector3(0.35, 1.35 + boom_len * 0.45, 0.0)),
				Vector3(boom_len, 0.16, 0.16), "wood", false)
	else:
		m.box(Vector3(boom_len * 0.5, 1.35, 0.0),
				Vector3(boom_len, 0.16, 0.16), "wood", false)
		m.collider_at(Vector3(boom_len * 0.5, 1.05, 0.0),
				Vector3(boom_len, 0.9, 0.3))
		m.box(Vector3(boom_len - 0.4, 0.75, 0.0), Vector3(0.1, 1.05, 0.1),
				"wood", false)
	m.box(Vector3(-0.75, 1.35, 0.0), Vector3(0.5, 0.42, 0.42), "metal", false)
	for s in [-1.0, 1.0]:
		var sf: float = s
		m.box_x(Transform3D(Basis(Vector3.UP, 0.35 * sf),
				Vector3(boom_len * 0.75, 0.45, sf * 1.7)),
				Vector3(1.3, 0.9, 0.7), "concrete")
	_add_cover(cover_out, Vector3(boom_len * 0.75, 0.0, 2.4),
			Vector3(0.0, 0.0, 1.0), false)
	_add_cover(cover_out, Vector3(boom_len * 0.75, 0.0, -2.4),
			Vector3(0.0, 0.0, -1.0), false)
	return m.finish("Barrier")


## Sentry box (guerite): tiny, but a soldier really does fit inside.
static func _guard_hut(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	_hut_geometry(m, Vector3.ZERO, 2.6, 2.6, 2.55, "wood", "roof_tile", false,
			cover_out)
	m.box(Vector3(0.0, 0.35, 0.0), Vector3(2.1, 0.1, 2.1), "wood", false)
	return m.finish("GuardHut")


## Wehrmacht barracks hut: long, plank walled, a door at each end.
static func _barracks(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var w := rng.randf_range(13.0, 16.0)
	var d := 5.6
	_hut_geometry(m, Vector3.ZERO, w, d, 2.85, "wood", "roof_tile", true,
			cover_out)
	# Bunks and a stove.
	var bunks := 5
	for i in bunks:
		var x := -w * 0.35 + w * 0.7 * float(i) / float(bunks - 1)
		for s in [-1.0, 1.0]:
			var sf: float = s
			m.box(Vector3(x, 0.42, sf * (d * 0.5 - 1.1)),
					Vector3(0.9, 0.14, 1.85), "wood", false)
			m.box(Vector3(x, 1.32, sf * (d * 0.5 - 1.1)),
					Vector3(0.9, 0.14, 1.85), "wood", false)
	m.cylinder(Vector3(0.0, 0.0, 0.0), 0.35, 1.0, 8, "metal", true)
	m.cylinder(Vector3(0.0, 1.0, 0.0), 0.11, 2.6, 6, "metal", false)
	_corner_cover(cover_out, w * 0.5, d * 0.5, 0.0, 0.9, true)
	return m.finish("Barracks")


## Shell crater. The heightfield cannot be carved, so the hole is faked with a
## raised earth lip and a darker floor: from eye level it reads correctly and
## the lip is genuine crouch cover.
static func _crater(rng: RandomNumberGenerator, radius: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var r := clampf(radius, 1.5, 7.0)
	var lumps := maxi(8, int(r * 4.0))
	for i in lumps:
		var ang := TAU * float(i) / float(lumps)
		var rr := r * rng.randf_range(0.92, 1.12)
		var h := rng.randf_range(0.35, 0.8)
		m.box_x(Transform3D(Basis(Vector3.UP, -ang),
				Vector3(cos(ang) * rr, h * 0.35, sin(ang) * rr)),
				Vector3(r * 0.55, h, TAU * r / float(lumps) + 0.35), "stone")
	m.cylinder(Vector3(0.0, -0.12, 0.0), r * 0.82, 0.14, 12, "stone", false)
	var ring := maxi(4, int(r * 1.6))
	for i in ring:
		var ang2 := TAU * float(i) / float(ring)
		var n := Vector3(cos(ang2), 0.0, sin(ang2))
		_add_cover(cover_out, n * (r * 0.7), n, false)
	return m.finish("Crater")


## Flag mast with a hanging axis banner. The "flag" objective anchor.
static func _flagpole(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	m.box(Vector3(0.0, -0.1, 0.0), Vector3(1.4, 0.5, 1.4), "concrete")
	m.cylinder(Vector3(0.0, 0.15, 0.0), 0.11, 9.0, 8, "metal", true)
	var a := Vector3(0.11, 8.6, 0.0)
	var b := Vector3(2.6, 8.6, 0.0)
	var c := Vector3(2.6, 7.0, 0.0)
	var d := Vector3(0.11, 7.0, 0.0)
	m.quad(a, b, c, d, "flag_axis", 0.4)
	m.quad(d, c, b, a, "flag_axis", 0.4)
	_add_cover(cover_out, Vector3(0.0, 0.0, -1.2), Vector3(0.0, 0.0, -1.0),
			false)
	return m.finish("Flagpole")


## Stack of supply crates: quick, solid, waist high cover.
static func _crate_stack(rng: RandomNumberGenerator, cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var count := rng.randi_range(3, 7)
	for i in count:
		var s := rng.randf_range(0.7, 1.15)
		var x := rng.randf_range(-1.3, 1.3)
		var z := rng.randf_range(-1.0, 1.0)
		var y := s * 0.5
		if i >= 4:
			y += s
		m.box_x(Transform3D(Basis(Vector3.UP, rng.randf_range(0.0, TAU)),
				Vector3(x, y, z)), Vector3(s * 1.35, s, s * 1.1), "wood")
	for i in 4:
		var ang := TAU * float(i) / 4.0 + 0.6
		var n := Vector3(cos(ang), 0.0, sin(ang))
		_add_cover(cover_out, n * 2.0, n, false)
	return m.finish("Crates")


## Heap of masonry rubble.
static func _rubble_pile(rng: RandomNumberGenerator, radius: float,
		cover_out: Array) -> Node3D:
	var m := _Mesher.new()
	var r := clampf(radius, 0.8, 5.0)
	var count := maxi(4, int(r * 3.0))
	for i in count:
		var ang := rng.randf_range(0.0, TAU)
		var dist := rng.randf_range(0.0, r)
		var h := rng.randf_range(0.3, 0.95) * (1.0 - dist / (r * 1.4))
		if h < 0.12:
			continue
		m.box_x(Transform3D(Basis(Vector3.UP, rng.randf_range(0.0, TAU)),
				Vector3(cos(ang) * dist, h * 0.45, sin(ang) * dist)),
				Vector3(rng.randf_range(0.8, 1.8), h,
				rng.randf_range(0.7, 1.5)), "stone")
	_add_cover(cover_out, Vector3(0.0, 0.0, -r - 0.6), Vector3(0.0, 0.0, -1.0),
			false)
	_add_cover(cover_out, Vector3(0.0, 0.0, r + 0.6), Vector3(0.0, 0.0, 1.0),
			false)
	return m.finish("Rubble")


## Marked minefield: warning posts, a low wire and a few half buried plates.
## Purely decorative, nothing here ever explodes.
static func _mine_field(rng: RandomNumberGenerator, w: float,
		d: float) -> Node3D:
	var m := _Mesher.new()
	var posts := maxi(3, int(w / 4.0))
	for i in posts + 1:
		var x := -w * 0.5 + w * float(i) / float(posts)
		m.box(Vector3(x, 0.45, -d * 0.5), Vector3(0.1, 0.9, 0.1), "wood",
				false)
		m.box_x(Transform3D(Basis(Vector3.UP, 0.2),
				Vector3(x, 0.85, -d * 0.5)), Vector3(0.42, 0.3, 0.05),
				"cloth", false)
	m.box(Vector3(0.0, 0.62, -d * 0.5), Vector3(w, 0.04, 0.04), "barbed_wire",
			false)
	for i in 14:
		var mx := rng.randf_range(-w * 0.45, w * 0.45)
		var mz := rng.randf_range(-d * 0.42, d * 0.42)
		m.cylinder(Vector3(mx, -0.03, mz), 0.16, 0.09, 8, "rust", false)
	return m.finish("MineField")


## Demolition charge lashed to a bridge pier: crate, wires and a detonator.
static func _explosive_charge(rng: RandomNumberGenerator) -> Node3D:
	var m := _Mesher.new()
	m.box(Vector3(0.0, 0.28, 0.0), Vector3(0.85, 0.55, 0.5), "wood")
	for k in 2:
		m.box(Vector3(-0.25 + 0.5 * float(k), 0.28, 0.0),
				Vector3(0.06, 0.6, 0.55), "metal", false)
	m.box(Vector3(0.0, 0.62, 0.0), Vector3(0.3, 0.16, 0.3), "gun_metal", false)
	_strut(m, Vector3(0.0, 0.66, 0.0), Vector3(1.6, 0.15, 1.2), 0.04,
			"barbed_wire")
	return m.finish("Charge")


## Flat ground patch: airfield strip, courtyard, village square. Visual only,
## the terrain collision underneath already holds the player up.
static func _ground_strip(w: float, d: float, key: String) -> Node3D:
	var m := _Mesher.new()
	var hw := w * 0.5
	var hd := d * 0.5
	var y := 0.06
	m.quad(Vector3(-hw, y, hd), Vector3(hw, y, hd), Vector3(hw, y, -hd),
			Vector3(-hw, y, -hd), key, 0.12)
	return m.finish("Ground")
