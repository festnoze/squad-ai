## Assembles one complete location out of the `Structures` library.
##
## `build()` is handed a `Layout.Site` (already flattened by
## `Heightfield.bake_sites()`) and returns everything the rest of the game needs
## to make that place live: the scene node, the AI cover points, a patrol loop,
## garrison spawn positions and the anchors the mission system aims its
## objectives at.
##
## Coordinate rule, and it is the easy one to get wrong: every builder works in
## SITE LOCAL space (origin at the site centre, +X along the site rotation,
## y = 0 at `site.ground`) but every value stored in `BuiltSite` is in WORLD
## space. `_Ctx` does that conversion once, in one place.
##
## Height rule: inside the flattened core the ground is exactly `site.ground`,
## so a local y of 0 is right. Anything reaching past the core is dropped onto
## `hf.height_at()` instead, and a building takes the LOWEST of five samples
## across its footprint so a corner never hangs in the air. The foundations
## built into every structure already reach 0.3 to 0.4 m below y = 0.
class_name SiteBuilder
extends RefCounted

## How high above the ground a spawn or patrol point sits.
const SPAWN_LIFT := 0.12
## Fraction of the site radius that is guaranteed flat (Layout.SITE_CORE).
const CORE := 0.66

## Occluder boxes are measured from a structure's bounds and then shrunk, so
## that the box is always strictly inside the solid it stands for. An occluder
## that claims more than the building fills culls geometry the player can
## actually see, which reads as holes opening in the world.
const _OCC_INSET := 0.78       # kept off the walls and inside the eaves
const _OCC_ROOF := 0.62        # capped under the pitch of the roof
const _OCC_MIN_SIDE := 3.0     # metres; below this a box hides nothing useful
const _OCC_MIN_HEIGHT := 2.2


## The result of building one site.
class BuiltSite extends RefCounted:
	var site_id: int = -1
	var node: Node3D = null
	var cover: Array = []              # Array[Structures.CoverPoint], WORLD space
	var patrol_points := PackedVector3Array()
	var garrison_spawns := PackedVector3Array()
	var interest_points := PackedVector3Array()
	var objective_anchors: Dictionary = {}


## Shared state while a single site is being assembled.
class _Ctx extends RefCounted:
	var site: Layout.Site
	var hf: Heightfield
	var bs: BuiltSite
	var root: Node3D
	var rng := RandomNumberGenerator.new()
	var xform := Transform3D.IDENTITY
	var radius := 40.0
	var core := 26.0
	## Box occluders measured from the placed structures, as
	## {"xf": Transform3D in site space, "size": Vector3}.
	var occluders: Array[Dictionary] = []

	## Occupied footprints, Vector3(local x, local z, radius).
	var blocked: Array[Vector3] = []

	func _init(new_site: Layout.Site, new_hf: Heightfield,
			new_bs: BuiltSite) -> void:
		site = new_site
		hf = new_hf
		bs = new_bs
		radius = maxf(12.0, site.radius)
		core = radius * CORE
		var s := site.seed
		if s == 0:
			s = site.id * 7919 + 104729
		rng.seed = s
		root = Node3D.new()
		root.name = "Site_%d" % site.id
		xform = Transform3D(Basis(Vector3.UP, site.rotation),
				Vector3(site.center.x, site.ground, site.center.y))
		root.transform = xform
		bs.site_id = site.id
		bs.node = root

	func to_world(local: Vector3) -> Vector3:
		return xform * local

	## Terrain height, in world metres, under a site local x/z.
	func world_ground(lx: float, lz: float) -> float:
		var w := xform * Vector3(lx, 0.0, lz)
		return hf.height_at(w.x, w.z)

	func local_ground(lx: float, lz: float) -> float:
		return world_ground(lx, lz) - site.ground

	## Lowest local ground across a footprint, so no corner ever floats.
	func footprint_y(lx: float, lz: float, foot: float) -> float:
		var y := local_ground(lx, lz)
		var r := maxf(0.6, foot)
		for i in 4:
			var a := TAU * float(i) / 4.0 + PI * 0.25
			y = minf(y, local_ground(lx + cos(a) * r, lz + sin(a) * r))
		return y

	## Drops a built structure onto the terrain and folds its cover points into
	## world space. Returns the local transform that was used.
	func place(node: Node3D, local_cover: Array, lx: float, lz: float,
			yaw: float, foot: float) -> Transform3D:
		return place_at(node, local_cover,
				Vector3(lx, footprint_y(lx, lz, foot), lz), yaw, foot)

	func place_at(node: Node3D, local_cover: Array, pos: Vector3, yaw: float,
			foot: float) -> Transform3D:
		var child := Transform3D(Basis(Vector3.UP, yaw), pos)
		node.transform = child
		root.add_child(node)
		blocked.append(Vector3(pos.x, pos.z, maxf(0.5, foot)))
		# Measured here and not later because `_merge_meshes` frees the very
		# nodes this reads before anything else gets a chance to look at them.
		_note_occluder(node, child)
		var b := xform.basis * child.basis
		for raw in local_cover:
			var cp := raw as Structures.CoverPoint
			if cp == null:
				continue
			bs.cover.append(Structures.CoverPoint.new(
					xform * (child * cp.position),
					(b * cp.normal).normalized(), cp.is_high))
		return child

	## Records a box occluder for a structure solid enough to hide what is
	## behind it, so the renderer can skip that geometry instead of drawing it
	## and throwing it away at the depth test.
	##
	## An occluder MUST stay inside the real solid. Claim more than the building
	## actually fills and the renderer culls things that are in fact visible,
	## which reads as holes opening in the world as the player walks. So the
	## measured bounds are inset hard: `_OCC_INSET` off the sides, and only up
	## to `_OCC_ROOF` of the height, which keeps the box under the pitch of the
	## roof and inside the eaves.
	##
	## Small structures are skipped outright. A fence post occludes nothing and
	## every occluder costs time in the rasteriser.
	func _note_occluder(node: Node3D, child: Transform3D) -> void:
		var box: AABB = _local_bounds(node)
		if box.size == Vector3.ZERO:
			return
		var w: float = box.size.x * _OCC_INSET
		var d: float = box.size.z * _OCC_INSET
		var h: float = box.size.y * _OCC_ROOF
		if w < _OCC_MIN_SIDE or d < _OCC_MIN_SIDE or h < _OCC_MIN_HEIGHT:
			return
		# Centre of the inset box, in the structure's own space, then carried
		# into site space by the transform it was just placed with.
		var centre := Vector3(
			box.position.x + box.size.x * 0.5,
			box.position.y + h * 0.5,
			box.position.z + box.size.z * 0.5)
		occluders.append({
			"xf": child * Transform3D(Basis.IDENTITY, centre),
			"size": Vector3(w, h, d),
		})

	## Merged bounds of every mesh under a node, in that node's own space.
	static func _local_bounds(node: Node3D) -> AABB:
		var out := AABB()
		var first := true
		var stack: Array[Node] = [node]
		while not stack.is_empty():
			var current: Node = stack.pop_back()
			for c in current.get_children():
				stack.append(c)
			var mi := current as MeshInstance3D
			if mi == null or mi.mesh == null:
				continue
			# Relative to `node`, so a mesh nested under an offset holder counts
			# where it actually sits rather than at the structure origin. Walked
			# by hand rather than through `global_transform`, which would depend
			# on whether the site root happens to be in the tree yet.
			var local: AABB = _relative_xf(node, mi) * mi.mesh.get_aabb()
			if first:
				out = local
				first = false
			else:
				out = out.merge(local)
		return out

	## Transform of `mi` expressed in `node` space, walked by hand because the
	## structure is measured before it is ever inside the scene tree.
	static func _relative_xf(node: Node3D, mi: Node3D) -> Transform3D:
		var xf := Transform3D.IDENTITY
		var current: Node = mi
		while current != null and current != node:
			var as_3d := current as Node3D
			if as_3d != null:
				xf = as_3d.transform * xf
			current = current.get_parent()
		return xf

	## Reserves a footprint without building anything (squares, roads, yards).
	func mark(lx: float, lz: float, r: float) -> void:
		blocked.append(Vector3(lx, lz, r))

	func is_blocked(lx: float, lz: float, pad: float) -> bool:
		for b in blocked:
			var dx := lx - b.x
			var dz := lz - b.y
			var r := b.z + pad
			if dx * dx + dz * dz < r * r:
				return true
		return false

	## A spot near (cx, cz) that is not inside anything already built.
	func free_spot(cx: float, cz: float, spread: float, pad: float) -> Vector2:
		for i in 32:
			var a := rng.randf_range(0.0, TAU)
			var d := spread * (0.2 + 0.8 * sqrt(rng.randf()))
			d *= 1.0 + float(i) * 0.035
			var p := Vector2(cx + cos(a) * d, cz + sin(a) * d)
			if not is_blocked(p.x, p.y, pad):
				return p
		var fa := rng.randf_range(0.0, TAU)
		return Vector2(cx + cos(fa) * spread * 2.0,
				cz + sin(fa) * spread * 2.0)

	func add_spawn(lx: float, lz: float) -> void:
		var w := xform * Vector3(lx, 0.0, lz)
		bs.garrison_spawns.append(Vector3(w.x,
				hf.height_at(w.x, w.z) + SPAWN_LIFT, w.z))

	func add_free_spawn(cx: float, cz: float, spread: float) -> void:
		var p := free_spot(cx, cz, spread, 1.4)
		add_spawn(p.x, p.y)

	func add_patrol(lx: float, lz: float) -> void:
		var w := xform * Vector3(lx, 0.0, lz)
		bs.patrol_points.append(Vector3(w.x,
				hf.height_at(w.x, w.z) + SPAWN_LIFT, w.z))

	## Patrol point at a forced local height, for a bridge deck or a platform.
	func add_patrol_y(lx: float, ly: float, lz: float) -> void:
		bs.patrol_points.append(xform * Vector3(lx, ly + SPAWN_LIFT, lz))

	func add_interest(lx: float, ly: float, lz: float) -> void:
		var w := xform * Vector3(lx, 0.0, lz)
		bs.interest_points.append(Vector3(w.x,
				hf.height_at(w.x, w.z) + ly, w.z))

	func add_interest_local(local: Vector3) -> void:
		bs.interest_points.append(xform * local)

	func set_anchor(key: String, lx: float, ly: float, lz: float) -> void:
		var w := xform * Vector3(lx, 0.0, lz)
		bs.objective_anchors[key] = Vector3(w.x,
				hf.height_at(w.x, w.z) + ly, w.z)

	func set_anchor_local(key: String, local: Vector3) -> void:
		bs.objective_anchors[key] = xform * local


# ===========================================================================
# Entry point
# ===========================================================================

## Builds the site at its world position, terrain aligned. The returned node is
## NOT yet in the tree; the caller adds it.
static func build(site: Layout.Site, hf: Heightfield) -> BuiltSite:
	if site == null or hf == null:
		push_error("SiteBuilder.build needs both a site and a heightfield")
		return null
	var bs := BuiltSite.new()
	var ctx := _Ctx.new(site, hf, bs)
	match site.kind:
		Layout.SITE_VILLAGE:
			_build_village(ctx, false)
		Layout.SITE_CHURCH_TOWN:
			_build_village(ctx, true)
		Layout.SITE_FARM:
			_build_farm(ctx)
		Layout.SITE_AIRFIELD:
			_build_airfield(ctx)
		Layout.SITE_BUNKER:
			_build_bunker(ctx)
		Layout.SITE_CAMP:
			_build_camp(ctx)
		Layout.SITE_CROSSROADS:
			_build_crossroads(ctx)
		Layout.SITE_BRIDGE:
			_build_bridge(ctx)
		Layout.SITE_RUIN:
			_build_ruin(ctx)
		_:
			_build_village(ctx, false)
	_finalise(ctx)
	return bs


# ===========================================================================
# Orientation helpers
# ===========================================================================

## Yaw that aims the LOCAL +X axis at the horizontal direction (dx, dz).
## Used for anything built along its own X axis: walls, fences, trenches.
static func _yaw_along(dx: float, dz: float) -> float:
	return atan2(-dz, dx)


## Yaw that aims the LOCAL -Z axis (where every door faces) at (dx, dz).
static func _yaw_facing(dx: float, dz: float) -> float:
	return atan2(-dx, -dz)


# ===========================================================================
# Composite pieces reused by several site kinds
# ===========================================================================

## A run of dry stone wall from a to b, split into segments short enough to
## follow the ground.
static func _wall_line(ctx: _Ctx, a: Vector2, b: Vector2, height: float) -> void:
	var d := b - a
	var l := d.length()
	if l < 1.5:
		return
	var segments := maxi(1, int(ceil(l / 16.0)))
	var seg_len := l / float(segments)
	var yaw := _yaw_along(d.x, d.y)
	for i in segments:
		var t := (float(i) + 0.5) / float(segments)
		var mid := a + d * t
		var cover: Array = []
		var n := Structures.stone_wall(ctx.rng, seg_len, height, cover)
		ctx.place(n, cover, mid.x, mid.y, yaw, seg_len * 0.35)


static func _fence_line(ctx: _Ctx, a: Vector2, b: Vector2) -> void:
	var d := b - a
	var l := d.length()
	if l < 1.5:
		return
	var segments := maxi(1, int(ceil(l / 18.0)))
	var seg_len := l / float(segments)
	var yaw := _yaw_along(d.x, d.y)
	for i in segments:
		var t := (float(i) + 0.5) / float(segments)
		var mid := a + d * t
		var cover: Array = []
		var n := Structures._wood_fence(ctx.rng, seg_len, cover)
		ctx.place(n, cover, mid.x, mid.y, yaw, seg_len * 0.35)


static func _wire_line(ctx: _Ctx, a: Vector2, b: Vector2) -> void:
	var d := b - a
	var l := d.length()
	if l < 1.5:
		return
	var segments := maxi(1, int(ceil(l / 20.0)))
	var seg_len := l / float(segments)
	var yaw := _yaw_along(d.x, d.y)
	for i in segments:
		var t := (float(i) + 0.5) / float(segments)
		var mid := a + d * t
		var empty: Array = []
		var n := Structures._wire_fence(ctx.rng, seg_len)
		ctx.place(n, empty, mid.x, mid.y, yaw, seg_len * 0.35)


## Wire fence all the way round a rectangle, with one gap for the gate.
static func _wire_rect(ctx: _Ctx, hx: float, hz: float, gate_w: float) -> void:
	var g := gate_w * 0.5
	_wire_line(ctx, Vector2(-hx, -hz), Vector2(-g, -hz))
	_wire_line(ctx, Vector2(g, -hz), Vector2(hx, -hz))
	_wire_line(ctx, Vector2(hx, -hz), Vector2(hx, hz))
	_wire_line(ctx, Vector2(hx, hz), Vector2(-hx, hz))
	_wire_line(ctx, Vector2(-hx, hz), Vector2(-hx, -hz))


## German road control point: sandbag pit, boom barrier, two spawns.
static func _checkpoint(ctx: _Ctx, lx: float, lz: float, yaw: float) -> void:
	var cover: Array = []
	var ring := Structures.sandbag_ring(ctx.rng, 2.7, cover)
	ctx.place(ring, cover, lx, lz, yaw, 3.4)
	var cover2: Array = []
	var barrier := Structures._barrier(ctx.rng, cover2)
	var bx := lx + cos(yaw) * 4.2
	var bz := lz - sin(yaw) * 4.2
	ctx.place(barrier, cover2, bx, bz, yaw + PI * 0.5, 2.5)
	ctx.add_spawn(lx + cos(yaw) * 1.4, lz - sin(yaw) * 1.4)
	ctx.add_spawn(lx - cos(yaw) * 2.6, lz + sin(yaw) * 2.6)
	ctx.add_interest(lx, 1.2, lz)


static func _flag(ctx: _Ctx, lx: float, lz: float) -> void:
	var cover: Array = []
	var pole := Structures._flagpole(ctx.rng, cover)
	ctx.place(pole, cover, lx, lz, ctx.rng.randf_range(0.0, TAU), 1.4)
	ctx.set_anchor("flag", lx, 1.5, lz)


## A closed patrol loop shaped like a rounded rectangle.
static func _loop_patrol(ctx: _Ctx, hx: float, hz: float, cz: float,
		steps: int) -> void:
	var n := maxi(6, steps)
	for i in n:
		var a := TAU * float(i) / float(n)
		var px := cos(a) * hx
		var pz := cz + sin(a) * hz
		if ctx.is_blocked(px, pz, 1.2):
			var pushed := Vector2(px, pz).normalized() * 3.5
			px += pushed.x
			pz += pushed.y
		ctx.add_patrol(px, pz)


# ===========================================================================
# Village and church town
# ===========================================================================

static func _build_village(ctx: _Ctx, with_church: bool) -> void:
	var core := ctx.core
	var street_half := core * 0.9
	var rng := ctx.rng

	# The street itself: a packed dirt ribbon down the middle of the site.
	var strip := Structures._ground_strip(street_half * 2.0 + 14.0, 7.5, "road")
	ctx.place_at(strip, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)

	var church_z := 0.0
	if with_church:
		church_z = 21.0
		var ccover: Array = []
		var ch := Structures.church(rng, ccover)
		var cx := rng.randf_range(-4.0, 4.0)
		var xf := ctx.place(ch, ccover, cx, church_z, 0.0, 11.0)
		ctx.mark(cx, church_z, 15.0)
		# The square in front of the porch.
		var square := Structures._ground_strip(26.0, 15.0, "road")
		ctx.place_at(square, [], Vector3(cx, 0.03, 7.5), 0.0, 0.0)
		ctx.mark(cx, 7.5, 8.0)
		# The belfry: an observation post, and where a sniper is posted.
		var belfry := xf * Vector3(0.0, Structures.CHURCH_BELFRY_Y,
				Structures.CHURCH_TOWER_Z)
		ctx.add_interest_local(belfry)
		ctx.bs.garrison_spawns.append(ctx.to_world(belfry
				+ Vector3(0.0, 0.15, 0.0)))
		ctx.set_anchor_local("officer", belfry)
		_flag(ctx, cx + 9.0, 3.0)
	else:
		_flag(ctx, rng.randf_range(-6.0, 6.0), -6.5)

	# Houses down both sides of the street.
	var wanted := clampi(int(street_half / 6.2), 6, 12)
	var built := 0
	for i in wanted + 4:
		if built >= wanted:
			break
		var t := (float(i) + 0.5) / float(wanted + 4)
		var hx := -street_half + street_half * 2.0 * t
		var side := 1.0 if (i % 2) == 0 else -1.0
		var w := rng.randf_range(6.5, 11.0)
		var d := rng.randf_range(5.5, 8.0)
		var floors := 1
		if rng.randf() < 0.55:
			floors = 2
		if rng.randf() < 0.1:
			floors = 3
		var hz := side * (7.0 + d * 0.5 + rng.randf_range(0.0, 2.5))
		var foot := sqrt(w * w + d * d) * 0.5
		if ctx.is_blocked(hx, hz, foot + 1.5):
			continue
		if Vector2(hx, hz).length() > core + 6.0:
			continue
		var cover: Array = []
		var node := Structures.house(rng, w, d, floors, cover)
		# Doors face the street: a house is entered from the road side.
		var yaw := _yaw_facing(0.0, -side) + rng.randf_range(-0.09, 0.09)
		ctx.place(node, cover, hx, hz, yaw, foot)
		built += 1
		ctx.add_spawn(hx + rng.randf_range(-2.0, 2.0), hz - side * (d * 0.5 + 2.2))
		if rng.randf() < 0.5:
			ctx.add_interest(hx, 1.4, hz - side * (d * 0.5 + 1.2))
		# Garden wall behind the house.
		if rng.randf() < 0.65:
			var back := hz + side * (d * 0.5 + 5.5)
			_wall_line(ctx, Vector2(hx - w * 0.5 - 1.0, back),
					Vector2(hx + w * 0.5 + 1.0, back),
					rng.randf_range(0.95, 1.7))
		# Low wall along the street frontage, between neighbours.
		if rng.randf() < 0.45:
			var front := side * 4.2
			_wall_line(ctx, Vector2(hx - w * 0.5, front),
					Vector2(hx + w * 0.5, front), rng.randf_range(0.8, 1.15))

	# The well, off to one side of the street.
	var wp := ctx.free_spot(rng.randf_range(-street_half * 0.3,
			street_half * 0.3), 5.0, 6.0, 3.0)
	var wcover: Array = []
	ctx.place(Structures._well(rng, wcover), wcover, wp.x, wp.y,
			rng.randf_range(0.0, TAU), 2.0)

	# Control points at both ends of the street.
	if ctx.site.garrison > 0:
		_checkpoint(ctx, -street_half - 5.0, 0.0, PI)
		_checkpoint(ctx, street_half + 5.0, 0.0, 0.0)

	# Clutter: crates, haystacks, a stretch of wire.
	for i in 3:
		var p := ctx.free_spot(rng.randf_range(-street_half, street_half),
				rng.randf_range(-core * 0.6, core * 0.6), 10.0, 2.5)
		var ccover2: Array = []
		if rng.randf() < 0.5:
			ctx.place(Structures._crate_stack(rng, ccover2), ccover2, p.x, p.y,
					rng.randf_range(0.0, TAU), 2.2)
		else:
			ctx.place(Structures._haystack(rng, ccover2), ccover2, p.x, p.y,
					rng.randf_range(0.0, TAU), 2.6)

	# Patrol: down the street, then a wide sweep back along the north side.
	var steps := 7
	for i in steps + 1:
		ctx.add_patrol(-street_half + street_half * 2.0 * float(i)
				/ float(steps), 0.0)
	ctx.add_patrol(street_half + 9.0, core * 0.62)
	for i in steps:
		var t2 := 1.0 - (float(i) + 0.5) / float(steps)
		ctx.add_patrol(-street_half + street_half * 2.0 * t2, core * 0.72)
	ctx.add_patrol(-street_half - 9.0, core * 0.5)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-street_half, street_half),
				rng.randf_range(-core * 0.55, core * 0.55), 9.0)


# ===========================================================================
# Farm
# ===========================================================================

static func _build_farm(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var yard_hx := 11.0
	var yard_hz := 8.5

	var yard := Structures._ground_strip(yard_hx * 2.0, yard_hz * 2.0, "road")
	ctx.place_at(yard, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)

	# Farmhouse on the west side, door onto the yard.
	var hcover: Array = []
	var house := Structures.house(rng, rng.randf_range(10.0, 13.0),
			rng.randf_range(6.5, 7.5), 2, hcover)
	ctx.place(house, hcover, -yard_hx - 4.5, -1.0, _yaw_facing(1.0, 0.0), 7.0)
	ctx.add_spawn(-yard_hx + 1.5, -1.0)

	# Barn closing the north side.
	var bcover: Array = []
	var barn := Structures.barn(rng, bcover)
	ctx.place(barn, bcover, 1.0, yard_hz + 5.5, _yaw_facing(0.0, -1.0), 9.5)
	ctx.add_spawn(1.0, yard_hz + 0.5)
	ctx.add_interest(1.0, 1.5, yard_hz + 1.5)

	# Cart shed and stone walls closing the yard.
	_wall_line(ctx, Vector2(yard_hx + 1.0, -yard_hz - 2.0),
			Vector2(yard_hx + 1.0, yard_hz + 2.0), 1.55)
	_wall_line(ctx, Vector2(-yard_hx - 1.0, -yard_hz - 3.0),
			Vector2(yard_hx - 3.0, -yard_hz - 3.0), 1.25)

	var wcover: Array = []
	ctx.place(Structures._well(rng, wcover), wcover, yard_hx - 3.5,
			-yard_hz + 3.0, rng.randf_range(0.0, TAU), 2.0)

	for i in 3:
		var p := ctx.free_spot(rng.randf_range(-6.0, 14.0),
				-yard_hz - 9.0 - float(i) * 2.0, 7.0, 3.0)
		var scover: Array = []
		ctx.place(Structures._haystack(rng, scover), scover, p.x, p.y,
				rng.randf_range(0.0, TAU), 2.8)

	var ccover: Array = []
	ctx.place(Structures._crate_stack(rng, ccover), ccover, -3.0, -yard_hz + 2.0,
			rng.randf_range(0.0, TAU), 2.2)

	# Paddock fence around the eastern field.
	var fx := yard_hx + 6.0
	var fz := ctx.core * 0.75
	_fence_line(ctx, Vector2(fx, -fz), Vector2(fx + 22.0, -fz))
	_fence_line(ctx, Vector2(fx + 22.0, -fz), Vector2(fx + 22.0, fz))
	_fence_line(ctx, Vector2(fx + 22.0, fz), Vector2(fx, fz))

	if ctx.site.garrison > 0:
		_flag(ctx, yard_hx - 2.0, yard_hz - 2.0)
		_checkpoint(ctx, -yard_hx - 3.0, -yard_hz - 8.0, PI * 0.5)

	var loop: Array[Vector2] = [
		Vector2(-yard_hx - 2.0, -yard_hz - 6.0),
		Vector2(yard_hx + 4.0, -yard_hz - 6.0),
		Vector2(fx + 20.0, -fz + 2.0),
		Vector2(fx + 20.0, fz - 2.0),
		Vector2(yard_hx + 4.0, yard_hz + 12.0),
		Vector2(-yard_hx - 6.0, yard_hz + 8.0),
		Vector2(-yard_hx - 8.0, 0.0),
	]
	for p in loop:
		ctx.add_patrol(p.x, p.y)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-yard_hx, yard_hx),
				rng.randf_range(-yard_hz, yard_hz), 10.0)


# ===========================================================================
# Airfield
# ===========================================================================

static func _build_airfield(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var core := ctx.core
	var strip_half := core * 0.86
	var apron_z := 26.0

	var strip := Structures._ground_strip(strip_half * 2.0, 30.0, "road")
	ctx.place_at(strip, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)
	var taxi := Structures._ground_strip(strip_half * 1.1, 12.0, "road")
	ctx.place_at(taxi, [], Vector3(0.0, 0.03, apron_z - 5.0), 0.0, 0.0)
	ctx.mark(0.0, 0.0, 18.0)

	# Two hangars facing the runway.
	for i in 2:
		var hx := -22.0 + 46.0 * float(i)
		var cover: Array = []
		var hangar := Structures.hangar(rng, cover)
		ctx.place(hangar, cover, hx, apron_z + 9.0, _yaw_facing(0.0, -1.0), 14.0)
		ctx.add_spawn(hx, apron_z + 1.5)
		ctx.add_interest(hx, 1.6, apron_z + 2.5)

	# Control tower.
	var tcover: Array = []
	ctx.place(Structures.watchtower(rng, tcover), tcover, 12.0, apron_z - 1.0,
			rng.randf_range(0.0, TAU), 4.0)
	ctx.add_interest(12.0, 8.4, apron_z - 1.0)
	ctx.add_spawn(12.0 + 3.5, apron_z - 1.0)

	# Fuel dump: the demolition objective.
	var fcover: Array = []
	ctx.place(Structures.fuel_depot(rng, fcover), fcover, -52.0, apron_z + 4.0,
			_yaw_facing(0.0, -1.0), 6.0)
	ctx.set_anchor("fuel", -52.0, 1.0, apron_z + 4.0)
	ctx.add_interest(-52.0, 1.0, apron_z + 4.0)
	ctx.add_spawn(-48.0, apron_z - 1.0)

	# Flak battery.
	var acover: Array = []
	ctx.place(Structures.aa_gun(rng, acover), acover, 52.0, -22.0,
			rng.randf_range(0.0, TAU), 4.5)
	ctx.set_anchor("aa", 52.0, 1.2, -22.0)
	ctx.add_interest(52.0, 1.2, -22.0)
	ctx.add_spawn(52.0, -17.0)
	var acover2: Array = []
	ctx.place(Structures.aa_gun(rng, acover2), acover2, -46.0, -26.0,
			rng.randf_range(0.0, TAU), 4.5)
	ctx.add_spawn(-46.0, -21.0)

	# Barracks and colours.
	var bcover: Array = []
	ctx.place(Structures._barracks(rng, bcover), bcover, 2.0, apron_z + 26.0,
			_yaw_facing(0.0, -1.0), 8.5)
	ctx.set_anchor("officer", 2.0, 1.5, apron_z + 22.0)
	for i in 4:
		ctx.add_spawn(-6.0 + float(i) * 4.0, apron_z + 21.5)
	_flag(ctx, 26.0, apron_z + 20.0)

	# Weapon pits along the runway.
	for i in 3:
		var px := -strip_half * 0.7 + strip_half * 0.7 * float(i)
		var scover: Array = []
		ctx.place(Structures.sandbag_ring(rng, 3.0, scover), scover, px, -21.0,
				rng.randf_range(0.0, TAU), 3.8)
		ctx.add_spawn(px, -21.0)

	# Wire around the perimeter.
	var wx := strip_half + 12.0
	var wz := core * 0.92
	_wire_line(ctx, Vector2(-wx, -wz), Vector2(wx, -wz))
	_wire_line(ctx, Vector2(wx, -wz), Vector2(wx, wz))
	_wire_line(ctx, Vector2(wx, wz), Vector2(24.0, wz))
	_wire_line(ctx, Vector2(-24.0, wz), Vector2(-wx, wz))
	_wire_line(ctx, Vector2(-wx, wz), Vector2(-wx, -wz))
	_checkpoint(ctx, 0.0, wz + 3.0, PI * 0.5)

	for i in 4:
		var p := ctx.free_spot(rng.randf_range(-40.0, 40.0), apron_z + 14.0,
				12.0, 3.0)
		var kcover: Array = []
		ctx.place(Structures._crate_stack(rng, kcover), kcover, p.x, p.y,
				rng.randf_range(0.0, TAU), 2.2)

	var loop: Array[Vector2] = [
		Vector2(-strip_half, -17.0), Vector2(strip_half, -17.0),
		Vector2(strip_half + 8.0, apron_z * 0.5),
		Vector2(strip_half * 0.5, apron_z + 3.0),
		Vector2(-strip_half * 0.5, apron_z + 3.0),
		Vector2(-strip_half - 8.0, apron_z * 0.5),
	]
	# Densified: the runway legs are long, and a patrol route with 60 m gaps
	# makes the soldiers walk in unreadable straight lines.
	for i in loop.size():
		var a: Vector2 = loop[i]
		var b: Vector2 = loop[(i + 1) % loop.size()]
		var cuts := maxi(1, int(a.distance_to(b) / 28.0))
		for k in cuts:
			var p := a.lerp(b, float(k) / float(cuts))
			ctx.add_patrol(p.x, p.y)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-strip_half * 0.8, strip_half * 0.8),
				apron_z * rng.randf_range(-0.4, 1.1), 12.0)


# ===========================================================================
# Bunker
# ===========================================================================

static func _build_bunker(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var sc := clampf(ctx.radius / 30.0, 0.85, 1.25)

	var cover: Array = []
	var bunker := Structures.bunker(rng, cover)
	ctx.place(bunker, cover, 0.0, 0.0, 0.0, 8.5)
	ctx.add_spawn(0.0, 6.5)
	ctx.add_spawn(-3.2, 2.0)
	ctx.add_interest(0.0, 4.2, 0.0)
	ctx.set_anchor("officer", 0.0, 1.5, 3.0)

	# Trenches on three approaches, parapets facing outwards.
	var trench_specs: Array[Vector3] = [
		Vector3(0.0, -13.0 * sc, 0.0),
		Vector3(-15.0 * sc, 3.0, -PI * 0.5),
		Vector3(15.0 * sc, 3.0, PI * 0.5),
	]
	for spec in trench_specs:
		var tcover: Array = []
		var length := 15.0 * sc
		var node := Structures.trench(rng, length, tcover)
		ctx.place(node, tcover, spec.x, spec.y, spec.z, length * 0.4)
		ctx.add_spawn(spec.x, spec.y)
		ctx.add_spawn(spec.x + cos(spec.z) * 4.0, spec.y - sin(spec.z) * 4.0)

	# Machine gun nest ahead of the bunker.
	var mcover: Array = []
	ctx.place(Structures.sandbag_ring(rng, 2.8, mcover), mcover, 0.0,
			-19.0 * sc, 0.0, 3.6)
	ctx.add_interest(0.0, 1.1, -19.0 * sc)
	ctx.add_spawn(0.0, -19.0 * sc)

	# Wire and dummy mines across the front.
	var wz := -24.0 * sc
	_wire_line(ctx, Vector2(-22.0 * sc, wz), Vector2(22.0 * sc, wz))
	_wire_line(ctx, Vector2(-22.0 * sc, wz), Vector2(-24.0 * sc, 6.0 * sc))
	_wire_line(ctx, Vector2(22.0 * sc, wz), Vector2(24.0 * sc, 6.0 * sc))
	var empty: Array = []
	ctx.place(Structures._mine_field(rng, 34.0 * sc, 9.0), empty, 0.0,
			wz - 6.0, 0.0, 4.0)

	_flag(ctx, 7.5, 8.0)

	var scover: Array = []
	ctx.place(Structures._crate_stack(rng, scover), scover, -7.5, 8.5,
			rng.randf_range(0.0, TAU), 2.2)

	_loop_patrol(ctx, 17.0 * sc, 15.0 * sc, -2.0, 8)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-14.0, 14.0) * sc,
				rng.randf_range(-16.0, 10.0) * sc, 8.0)


# ===========================================================================
# Prisoner camp
# ===========================================================================

static func _build_camp(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var sc := clampf(ctx.radius / 65.0, 0.8, 1.3)
	var hx := 30.0 * sc
	var hz := 24.0 * sc

	var yard := Structures._ground_strip(hx * 1.9, hz * 1.9, "road")
	ctx.place_at(yard, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)

	_wire_rect(ctx, hx, hz, 5.0)
	var gcover: Array = []
	ctx.place(Structures._guard_hut(rng, gcover), gcover, 5.0, -hz - 1.5,
			_yaw_facing(0.0, -1.0), 2.2)
	ctx.add_spawn(2.5, -hz - 3.0)
	ctx.add_interest(0.0, 1.4, -hz - 2.0)

	# The cages, in a row along the north half.
	var cage_count := 4
	for i in cage_count:
		var cx := -hx * 0.62 + hx * 1.24 * float(i) / float(cage_count - 1)
		var cover: Array = []
		var cage := Structures.prison_cage(rng, cover)
		ctx.place(cage, cover, cx, hz * 0.42, _yaw_facing(0.0, -1.0), 5.2)
		if i == 0:
			ctx.set_anchor("cage", cx, 1.0, hz * 0.42)
		ctx.add_interest(cx, 1.0, hz * 0.42)
		ctx.add_spawn(cx, hz * 0.42 - 6.5)

	# Guard barracks on the south half, the second one is the officer's.
	for i in 2:
		var bx := -hx * 0.42 + hx * 0.84 * float(i)
		var bcover: Array = []
		ctx.place(Structures._barracks(rng, bcover), bcover, bx, -hz * 0.5,
				_yaw_facing(0.0, 1.0), 8.0)
		ctx.add_spawn(bx - 3.0, -hz * 0.5 + 4.5)
		ctx.add_spawn(bx + 3.0, -hz * 0.5 + 4.5)
		if i == 1:
			ctx.set_anchor("officer", bx, 1.5, -hz * 0.5 + 4.0)

	# Towers on two opposite corners.
	var tower_at: Array[Vector2] = [
		Vector2(-hx + 3.0, -hz + 3.0), Vector2(hx - 3.0, hz - 3.0),
	]
	for p in tower_at:
		var tcover: Array = []
		ctx.place(Structures.watchtower(rng, tcover), tcover, p.x, p.y,
				_yaw_facing(-p.x, -p.y), 4.0)
		ctx.add_interest(p.x, 8.4, p.y)
		ctx.add_spawn(p.x + (3.5 if p.x < 0.0 else -3.5), p.y)

	_flag(ctx, 0.0, -hz * 0.14)

	for i in 3:
		var p2 := ctx.free_spot(rng.randf_range(-hx * 0.6, hx * 0.6),
				rng.randf_range(-hz * 0.2, hz * 0.2), 8.0, 3.0)
		var kcover: Array = []
		ctx.place(Structures._crate_stack(rng, kcover), kcover, p2.x, p2.y,
				rng.randf_range(0.0, TAU), 2.2)

	_loop_patrol(ctx, hx - 4.0, hz - 4.0, 0.0, 10)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-hx * 0.8, hx * 0.8),
				rng.randf_range(-hz * 0.8, hz * 0.8), 9.0)


# ===========================================================================
# Crossroads
# ===========================================================================

static func _build_crossroads(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var reach := maxf(14.0, ctx.core)

	var road_a := Structures._ground_strip(reach * 2.0, 7.5, "road")
	ctx.place_at(road_a, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)
	var road_b := Structures._ground_strip(reach * 2.0, 7.5, "road")
	ctx.place_at(road_b, [], Vector3(0.0, 0.03, 0.0), PI * 0.5, 0.0)

	_checkpoint(ctx, -9.0, 0.0, PI)
	_checkpoint(ctx, 9.0, 0.0, 0.0)

	var gcover: Array = []
	ctx.place(Structures._guard_hut(rng, gcover), gcover, 6.5, 7.0,
			_yaw_facing(-0.6, -1.0), 2.2)
	ctx.add_spawn(6.5, 4.5)

	var rcover: Array = []
	ctx.place(Structures.radio_mast(rng, rcover), rcover, -11.0, -11.0,
			rng.randf_range(0.0, TAU), 3.0)
	ctx.set_anchor("radio", -11.0, 1.4, -11.0)
	ctx.add_interest(-11.0, 1.4, -11.0)
	ctx.add_spawn(-8.0, -8.5)

	var scover: Array = []
	ctx.place(Structures.sandbag_ring(rng, 2.6, scover), scover, -6.5, 7.5,
			rng.randf_range(0.0, TAU), 3.4)
	ctx.add_spawn(-6.5, 7.5)

	var kcover: Array = []
	ctx.place(Structures._crate_stack(rng, kcover), kcover, 10.0, -7.0,
			rng.randf_range(0.0, TAU), 2.2)

	_wire_line(ctx, Vector2(-16.0, 5.0), Vector2(-16.0, 14.0))
	_wire_line(ctx, Vector2(16.0, -5.0), Vector2(16.0, -14.0))
	_flag(ctx, 3.0, 6.0)

	_loop_patrol(ctx, minf(reach * 0.75, 15.0), minf(reach * 0.75, 15.0), 0.0, 8)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-9.0, 9.0),
				rng.randf_range(-9.0, 9.0), 7.0)


# ===========================================================================
# Bridge
# ===========================================================================

## Direction of the river closest to the site, in world x/z, or ZERO.
static func _river_direction(ctx: _Ctx) -> Vector2:
	var lay := ctx.hf.layout
	if lay == null:
		return Vector2.ZERO
	var best := Vector2.ZERO
	var best_d := 1e20
	var c := ctx.site.center
	for raw in lay.rivers:
		var poly: PackedVector2Array = raw
		for i in maxi(0, poly.size() - 1):
			var a := poly[i]
			var b := poly[i + 1]
			var mid := (a + b) * 0.5
			var d := mid.distance_squared_to(c)
			if d < best_d and (b - a).length_squared() > 0.01:
				best_d = d
				best = (b - a).normalized()
	return best


static func _build_bridge(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var span := clampf(ctx.radius * 1.9, 26.0, 48.0)
	# The deck must cross the water, so it runs perpendicular to the river.
	var flow := _river_direction(ctx)
	var deck_yaw := 0.0
	if flow != Vector2.ZERO:
		var axis := Vector2(-flow.y, flow.x)
		deck_yaw = _yaw_along(axis.x, axis.y) - ctx.site.rotation
	var cover: Array = []
	var deck := Structures.bridge(rng, span, cover)
	ctx.place_at(deck, cover, Vector3.ZERO, deck_yaw, span * 0.45)

	var ca := cos(deck_yaw)
	var sa := -sin(deck_yaw)
	var half := span * 0.5

	# Guard posts, sandbags and barriers at both ends.
	for s in [-1.0, 1.0]:
		var sf: float = s
		var ex := ca * half * sf
		var ez := sa * half * sf
		var ox := ex + ca * 6.0 * sf
		var oz := ez + sa * 6.0 * sf
		var side_x := -sa * 5.5
		var side_z := ca * 5.5
		var hcover: Array = []
		ctx.place(Structures._guard_hut(rng, hcover), hcover, ox + side_x,
				oz + side_z, _yaw_facing(-ca * sf, -sa * sf), 2.2)
		var scover: Array = []
		ctx.place(Structures.sandbag_ring(rng, 2.6, scover), scover,
				ox - side_x, oz - side_z, 0.0, 3.4)
		var bcover: Array = []
		ctx.place(Structures._barrier(rng, bcover), bcover, ex + ca * 2.5 * sf,
				ez + sa * 2.5 * sf, deck_yaw + PI * 0.5, 2.5)
		ctx.add_spawn(ox, oz)
		ctx.add_spawn(ox - side_x, oz - side_z)
		ctx.add_interest(ox, 1.3, oz)
		ctx.add_patrol_y(ca * (half - 2.0) * sf, 0.0, sa * (half - 2.0) * sf)

	# Demolition charges lashed under the deck: the sabotage target.
	for i in 3:
		var t := -0.4 + 0.4 * float(i)
		var cx := ca * span * t
		var cz := sa * span * t
		var empty: Array = []
		ctx.place_at(Structures._explosive_charge(rng), empty,
				Vector3(cx - sa * 2.6, -1.1, cz + ca * 2.6), deck_yaw, 1.0)
		ctx.add_interest_local(Vector3(cx - sa * 2.6, -0.6, cz + ca * 2.6))
		if i == 1:
			ctx.set_anchor_local("fuel", Vector3(cx, 0.4, cz))
	_flag(ctx, ca * (half + 7.0), sa * (half + 7.0))

	_wire_line(ctx, Vector2(ca * (half + 4.0) - sa * 8.0,
			sa * (half + 4.0) + ca * 8.0),
			Vector2(ca * (half + 14.0) - sa * 8.0,
			sa * (half + 14.0) + ca * 8.0))

	# Patrol: across the deck and back along the bank.
	var steps := 5
	for i in steps + 1:
		var t2 := -1.0 + 2.0 * float(i) / float(steps)
		ctx.add_patrol_y(ca * half * t2 * 0.92, 0.0, sa * half * t2 * 0.92)
	ctx.add_patrol(ca * (half + 9.0) - sa * 7.0, sa * (half + 9.0) + ca * 7.0)
	ctx.add_patrol(-ca * (half + 9.0) - sa * 7.0, -sa * (half + 9.0) + ca * 7.0)

	var extra := maxi(0, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		var sf2 := 1.0 if (i % 2) == 0 else -1.0
		ctx.add_free_spawn(ca * (half + 8.0) * sf2, sa * (half + 8.0) * sf2, 7.0)


# ===========================================================================
# Bombed out village
# ===========================================================================

static func _build_ruin(ctx: _Ctx) -> void:
	var rng := ctx.rng
	var core := ctx.core
	var spread := core * 0.78

	var count := clampi(int(spread / 7.0), 4, 8)
	for i in count:
		var a := TAU * float(i) / float(count) + rng.randf_range(-0.35, 0.35)
		var d := spread * rng.randf_range(0.18, 0.95)
		var px := cos(a) * d
		var pz := sin(a) * d
		if ctx.is_blocked(px, pz, 8.0):
			continue
		var cover: Array = []
		var node := Structures.ruin(rng, cover)
		ctx.place(node, cover, px, pz, rng.randf_range(0.0, TAU), 6.5)
		ctx.add_spawn(px + cos(a) * 7.0, pz + sin(a) * 7.0)
		ctx.add_interest(px, 1.3, pz)

	for i in 5:
		var p := ctx.free_spot(rng.randf_range(-spread, spread),
				rng.randf_range(-spread, spread), 9.0, 3.0)
		var ccover: Array = []
		ctx.place(Structures._crater(rng, rng.randf_range(2.5, 5.0), ccover),
				ccover, p.x, p.y, rng.randf_range(0.0, TAU), 4.0)

	for i in 4:
		var p2 := ctx.free_spot(rng.randf_range(-spread, spread),
				rng.randf_range(-spread, spread), 9.0, 2.5)
		var rcover: Array = []
		ctx.place(Structures._rubble_pile(rng, rng.randf_range(1.6, 3.2),
				rcover), rcover, p2.x, p2.y, rng.randf_range(0.0, TAU), 2.8)

	# A couple of broken garden walls, still very usable cover.
	for i in 3:
		var a2 := rng.randf_range(0.0, TAU)
		var d2 := spread * rng.randf_range(0.4, 1.0)
		var from := Vector2(cos(a2) * d2, sin(a2) * d2)
		var dir := Vector2(cos(a2 + 1.4), sin(a2 + 1.4)) * rng.randf_range(8.0,
				16.0)
		_wall_line(ctx, from, from + dir, rng.randf_range(0.9, 1.8))

	var lone := Structures._ground_strip(spread * 1.6, 6.0, "road")
	ctx.place_at(lone, [], Vector3(0.0, 0.02, 0.0), 0.0, 0.0)
	if ctx.site.garrison > 0:
		_flag(ctx, spread * 0.35, -spread * 0.3)

	_loop_patrol(ctx, spread * 0.95, spread * 0.85, 0.0, 9)

	var extra := maxi(2, ctx.site.garrison - ctx.bs.garrison_spawns.size())
	for i in extra:
		ctx.add_free_spawn(rng.randf_range(-spread, spread),
				rng.randf_range(-spread, spread), 8.0)


# ===========================================================================
# Finishing pass
# ===========================================================================

static func _finalise(ctx: _Ctx) -> void:
	var bs := ctx.bs
	# Always enough spawn positions for the whole garrison.
	var guard := 0
	while bs.garrison_spawns.size() < ctx.site.garrison and guard < 200:
		guard += 1
		ctx.add_free_spawn(ctx.rng.randf_range(-ctx.core, ctx.core),
				ctx.rng.randf_range(-ctx.core, ctx.core), ctx.core * 0.5)
	if bs.garrison_spawns.is_empty():
		ctx.add_spawn(0.0, ctx.core * 0.4)
	# A patrol route has to be a loop, so it needs at least a triangle.
	if bs.patrol_points.size() < 4:
		bs.patrol_points = PackedVector3Array()
		_loop_patrol(ctx, ctx.core * 0.7, ctx.core * 0.6, 0.0, 8)
	if bs.interest_points.is_empty():
		ctx.add_interest(0.0, 1.5, 0.0)
	# Occluders first: the merge frees the meshes they were measured from, and
	# the occluder nodes themselves carry no mesh, so the merge ignores them.
	_spawn_occluders(ctx)
	_merge_meshes(ctx.root)


## Turns the measured boxes into occluder nodes, when occlusion culling is on.
##
## MEASURED AND TURNED OFF. Godot rasterises the occluders on the CPU every
## frame, and the pocket is open bocage: standing in the largest village of the
## map produced fourteen boxes, which is nowhere near enough cover to pay for
## the pass. Three runs each way at 1600x900 averaged 17.0 ms with it against
## 15.1 ms without, with enough run to run spread that the only safe reading is
## "no gain here, possibly a loss".
##
## The generation is kept and gated on the project setting rather than deleted,
## because the conclusion is about THIS world, not about the technique: a denser
## town, taller buildings or a bigger draw distance would move the balance, and
## then it is one flag away.
static func _spawn_occluders(ctx: _Ctx) -> void:
	if ctx.occluders.is_empty():
		return
	if not bool(ProjectSettings.get_setting(
			"rendering/occlusion_culling/use_occlusion_culling", false)):
		return
	for entry in ctx.occluders:
		var shape := BoxOccluder3D.new()
		shape.size = entry["size"] as Vector3
		var node := OccluderInstance3D.new()
		node.occluder = shape
		node.transform = entry["xf"] as Transform3D
		ctx.root.add_child(node)


## Collapses every static MeshInstance3D of the site into one mesh per
## material. A village is a few dozen buildings, which would otherwise be a few
## hundred draw calls; after this pass it is under ten. Collision bodies are
## left exactly where they are.
static func _merge_meshes(root: Node3D) -> void:
	var tools: Dictionary = {}
	var mats: Dictionary = {}
	var doomed: Array[Node] = []
	_collect_meshes(root, Transform3D.IDENTITY, tools, mats, doomed)
	for node in doomed:
		var parent := node.get_parent()
		if parent != null:
			parent.remove_child(node)
		node.free()
	var keys := tools.keys()
	keys.sort()
	for k in keys:
		var st: SurfaceTool = tools[k]
		var mesh := st.commit()
		if mesh == null:
			continue
		var mi := MeshInstance3D.new()
		mi.name = "Merged_%s" % String(k)
		mi.mesh = mesh
		mi.material_override = mats[k]
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		root.add_child(mi)


static func _collect_meshes(node: Node, xf: Transform3D, tools: Dictionary,
		mats: Dictionary, doomed: Array[Node]) -> void:
	for child in node.get_children():
		if child is MeshInstance3D:
			var mi := child as MeshInstance3D
			if mi.mesh == null:
				continue
			var mat := mi.material_override
			var key := "0" if mat == null else str(mat.get_instance_id())
			if not tools.has(key):
				var st := SurfaceTool.new()
				st.begin(Mesh.PRIMITIVE_TRIANGLES)
				tools[key] = st
				mats[key] = mat
			var tool_ref: SurfaceTool = tools[key]
			var world := xf * mi.transform
			for s in mi.mesh.get_surface_count():
				tool_ref.append_from(mi.mesh, s, world)
			doomed.append(mi)
		elif child is StaticBody3D:
			continue
		elif child is Node3D:
			_collect_meshes(child, xf * (child as Node3D).transform, tools,
					mats, doomed)
