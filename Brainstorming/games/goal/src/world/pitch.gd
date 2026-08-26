## The playing surface: turf, painted markings, ground collider and wear marks.
##
## Design notes, because several choices here are deliberate:
##
## 1. The markings are real geometry, not decals. A decal projected onto a
##    surface that is almost perfectly parallel to it fights for depth along its
##    whole footprint, and a penalty pitch is as flat as a surface gets. Every
##    line is instead a flat ribbon raised one centimetre above the turf, which
##    can never z fight because it is simply in front.
##
## 2. Two ribbons that overlap (the touchline meeting the goal line, the halfway
##    line crossing the centre circle) would be coplanar and would fight each
##    other instead. So each strip is issued its own height off a very fine
##    ladder (0.6 mm per strip): invisible to the eye, decisive to the depth
##    buffer.
##
## 3. The layout is the regulation one, taken from Field. In particular the
##    penalty arc is NOT a semicircle: it is only the part of the 9.15 m circle
##    centred on the spot that falls OUTSIDE the 16.5 m box. Getting that wrong
##    is the single detail a football supporter spots in the first second.
##
## 4. Arcs are sampled into polylines here and pushed through Meshes.line_strip
##    rather than through Meshes.arc_strip, so that every marking shares one code
##    path, one width and one height ladder, and so that the plane an arc lives
##    in is decided by the points themselves and never by a convention.
##
## 5. All the ribbons are merged into a single surface, so the whole set of
##    markings costs one draw call instead of fifteen.
##
## 6. Scuffs are a MultiMesh with a fixed, recycled pool. A long practice session
##    then visibly wears the six yard box without the node count ever growing.
class_name Pitch
extends Node3D

## Metres between two turf vertices. Fine enough for the spot lights and the
## ground fog to have something to shade, coarse enough to stay cheap.
const TURF_STEP := 0.75

## Regulation paint is 12 cm wide.
const LINE_WIDTH := 0.12
## Height of the first ribbon above the turf.
const LINE_LIFT := 0.010
## Extra height handed to each following ribbon, see note 2 above.
const LINE_LIFT_STEP := 0.0006

## Halfway line of a regulation 105 m pitch, measured from our goal line.
const HALFWAY_Z := 52.5
const CENTRE_CIRCLE_RADIUS := 9.15
const CORNER_RADIUS := 1.0
## Diameter of the penalty spot and of the centre mark is 22 cm.
const MARK_RADIUS := 0.11

## Target chord length when sampling an arc, and the floor on segment count.
const ARC_SEGMENT_LENGTH := 0.5
const MIN_ARC_SEGMENTS := 12

## Crown of the pitch, in metres. Zero today: the turf mesh is a flat plane, so
## anything else here would leave the ball floating. Kept as a named constant
## because ground_height() is written to support it the day the mesh follows.
const CAMBER_RISE := 0.0

## The ground collider is a thick slab rather than an infinite plane, so a body
## that leaves the built area falls instead of skating over the void.
const GROUND_THICKNESS := 1.0

## Wear marks.
const MAX_SCUFFS := 96
const SCUFF_LIFT := 0.006
const SCUFF_SEED := 0x5C0FF

var _built := false
var _turf: MeshInstance3D = null
var _markings: Node3D = null
var _scuffs: MultiMeshInstance3D = null
var _ground: StaticBody3D = null
var _paint_material: Material = null
var _scuff_material: StandardMaterial3D = null
var _scuff_count := 0
var _lift_index := 0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	build()


## Builds turf, markings and the ground collider. Idempotent.
func build() -> void:
	if _built and is_instance_valid(_turf):
		return
	_discard()
	_rng.seed = SCUFF_SEED
	_lift_index = 0
	_build_turf()
	_build_markings()
	_build_ground()
	_build_scuffs()
	_built = true


## Height of the turf under a world point. Flat for now, but the ball asks
## through this so a cambered pitch stays possible.
func ground_height(x: float, z: float) -> float:
	if CAMBER_RISE == 0.0:
		return 0.0
	# Parabolic crown, highest along the middle of the pitch and falling to zero
	# at both touchlines, which is how a drained pitch is actually laid.
	var across := clampf(absf(x) / maxf(Field.PITCH_HALF_X, 0.001), 0.0, 1.0)
	var depth := maxf(Field.PITCH_MAX_Z - Field.PITCH_MIN_Z, 0.001)
	var along := clampf((z - Field.PITCH_MIN_Z) / depth, 0.0, 1.0)
	return CAMBER_RISE * (1.0 - across * across) * (0.6 + 0.4 * sin(along * PI))


## Marks the turf where the ball was struck or where the keeper landed.
func add_scuff(position: Vector3, radius: float) -> void:
	if not is_instance_valid(_scuffs):
		push_warning("Pitch: add_scuff called before build(), the mark is dropped.")
		return
	var multi := _scuffs.multimesh
	if multi == null:
		return
	if not position.is_finite() or not is_finite(radius):
		push_warning("Pitch: add_scuff got a non finite argument, the mark is dropped.")
		return
	var spot_x := clampf(position.x, -Field.PITCH_HALF_X, Field.PITCH_HALF_X)
	var spot_z := clampf(position.z, Field.PITCH_MIN_Z, Field.PITCH_MAX_Z)
	var size := clampf(radius, 0.05, 1.5) * 2.0
	var stretch := _rng.randf_range(0.8, 1.3)
	var yaw := _rng.randf() * TAU
	# The quad comes out of Meshes in the XY plane facing +Z, so it is laid down
	# by a quarter turn about X, then spun about Y for variety, then scaled in
	# its own plane (right multiplication, so local axes and not world ones).
	var basis := Basis(Vector3.UP, yaw) * Basis(Vector3.RIGHT, -PI * 0.5)
	basis = basis * Basis.from_scale(Vector3(size * stretch, size, 1.0))
	var origin := Vector3(spot_x, ground_height(spot_x, spot_z) + SCUFF_LIFT, spot_z)
	# The material albedo stays white on purpose: the worn colour is carried by
	# the instance colour alone, so the tint is never applied twice.
	var tint := Palette.vary(Palette.GRASS_WORN, _rng.randf(), 0.10)
	tint.a = _rng.randf_range(0.35, 0.70)
	var index := _scuff_count % MAX_SCUFFS
	multi.set_instance_transform(index, Transform3D(basis, origin))
	multi.set_instance_color(index, tint)
	_scuff_count += 1
	multi.visible_instance_count = mini(_scuff_count, MAX_SCUFFS)


# --- construction -----------------------------------------------------------


func _discard() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_turf = null
	_markings = null
	_scuffs = null
	_ground = null
	_paint_material = null
	_scuff_count = 0
	_built = false


func _build_turf() -> void:
	_turf = MeshInstance3D.new()
	_turf.name = "Turf"
	var mesh := Meshes.pitch_plane(
		Field.PITCH_HALF_X, Field.PITCH_MIN_Z, Field.PITCH_MAX_Z, TURF_STEP
	)
	if mesh == null:
		push_error("Pitch: Meshes.pitch_plane returned nothing, the turf is missing.")
	_turf.mesh = mesh
	_turf.material_override = Mats.turf()
	# The ground is the only thing under the floodlights that cannot usefully
	# cast a shadow, and shadow casting is the first cost of the whole scene.
	_turf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_turf)


func _build_markings() -> void:
	_markings = Node3D.new()
	_markings.name = "Markings"
	add_child(_markings)

	var half_x := Field.PITCH_HALF_X
	var parts: Array[ArrayMesh] = []

	# Goal line, then the two touchlines running away from us.
	_add_strip(parts, PackedVector2Array([Vector2(-half_x, 0.0), Vector2(half_x, 0.0)]), false)
	_add_strip(
		parts,
		PackedVector2Array([Vector2(-half_x, 0.0), Vector2(-half_x, Field.PITCH_MAX_Z)]),
		false
	)
	_add_strip(
		parts,
		PackedVector2Array([Vector2(half_x, 0.0), Vector2(half_x, Field.PITCH_MAX_Z)]),
		false
	)

	# Penalty area: 40.32 wide, 16.5 deep, open on the goal line.
	_add_strip(
		parts,
		PackedVector2Array([
			Vector2(-Field.BOX_HALF, 0.0),
			Vector2(-Field.BOX_HALF, Field.BOX_DEPTH),
			Vector2(Field.BOX_HALF, Field.BOX_DEPTH),
			Vector2(Field.BOX_HALF, 0.0),
		]),
		false
	)

	# Six yard box: 18.32 wide, 5.5 deep.
	_add_strip(
		parts,
		PackedVector2Array([
			Vector2(-Field.SIX_HALF, 0.0),
			Vector2(-Field.SIX_HALF, Field.SIX_DEPTH),
			Vector2(Field.SIX_HALF, Field.SIX_DEPTH),
			Vector2(Field.SIX_HALF, 0.0),
		]),
		false
	)

	# The penalty arc: only the part of the 9.15 m circle around the spot that
	# lies beyond the front of the box. sin(angle) = (box front - spot) / radius,
	# and the sweep is trimmed by half a line width so the paint butts against
	# the box line instead of lying on top of it.
	var reach := (Field.BOX_DEPTH + LINE_WIDTH * 0.5 - Field.SPOT_Z) / Field.ARC_RADIUS
	if absf(reach) < 1.0:
		var start_angle := asin(clampf(reach, -1.0, 1.0))
		_add_strip(
			parts,
			_arc_points(0.0, Field.SPOT_Z, Field.ARC_RADIUS, start_angle, PI - start_angle, false),
			false
		)
	else:
		push_warning("Pitch: the penalty arc never leaves the box, check the Field constants.")

	# Corner arcs, quarter circles biting into the pitch at the two near corners.
	_add_strip(parts, _arc_points(-half_x, 0.0, CORNER_RADIUS, 0.0, PI * 0.5, false), false)
	_add_strip(parts, _arc_points(half_x, 0.0, CORNER_RADIUS, PI * 0.5, PI, false), false)

	# Halfway line and centre circle, both inside the built area.
	if HALFWAY_Z + CENTRE_CIRCLE_RADIUS < Field.PITCH_MAX_Z:
		_add_strip(
			parts,
			PackedVector2Array([Vector2(-half_x, HALFWAY_Z), Vector2(half_x, HALFWAY_Z)]),
			false
		)
		_add_strip(
			parts,
			_arc_points(0.0, HALFWAY_Z, CENTRE_CIRCLE_RADIUS, 0.0, TAU, true),
			true
		)
		_add_dot(parts, 0.0, HALFWAY_Z)

	# The penalty spot itself, last so it sits on top of everything else.
	_add_dot(parts, 0.0, Field.SPOT_Z)

	var merged := _merge(parts)
	if merged != null:
		_markings.add_child(_marking_instance(merged, "Paint"))
		return
	# Fallback: one instance per ribbon. Costs a handful of draw calls, but the
	# pitch is never left unmarked.
	push_warning("Pitch: could not merge the markings, falling back to one node per line.")
	for i in parts.size():
		_markings.add_child(_marking_instance(parts[i], "Paint%d" % i))


func _marking_instance(mesh: ArrayMesh, node_name: String) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	instance.mesh = mesh
	instance.material_override = _paint()
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return instance


## The paint material, with one local change: a ribbon lying on the ground is
## only ever looked at from above, so making it two sided costs nothing and
## makes the paint immune to whichever winding the strip builder chose. Godot
## flips the shading normal on back faces of a two sided material, so the lines
## stay correctly lit either way. The material is duplicated so the change never
## leaks into the shared cached one.
func _paint() -> Material:
	if _paint_material != null:
		return _paint_material
	var base := Mats.line()
	if base == null:
		push_error("Pitch: Mats.line() returned nothing, the markings are unpainted.")
		return null
	var copy := base.duplicate() as StandardMaterial3D
	if copy == null:
		_paint_material = base
		return _paint_material
	copy.cull_mode = BaseMaterial3D.CULL_DISABLED
	_paint_material = copy
	return _paint_material


func _build_ground() -> void:
	_ground = StaticBody3D.new()
	_ground.name = "Ground"
	_ground.collision_layer = Layers.PITCH
	# Nothing queries the pitch through its own mask: bodies and sweeps come to
	# it, never the other way round.
	_ground.collision_mask = 0
	var surface := PhysicsMaterial.new()
	surface.friction = 0.9
	surface.bounce = 0.25
	_ground.physics_material_override = surface

	var slab := BoxShape3D.new()
	var depth := Field.PITCH_MAX_Z - Field.PITCH_MIN_Z
	slab.size = Vector3(Field.PITCH_HALF_X * 2.0, GROUND_THICKNESS, depth)
	var collider := CollisionShape3D.new()
	collider.name = "GroundShape"
	collider.shape = slab
	# Sunk so that the top face of the slab is exactly the turf surface.
	collider.position = Vector3(
		0.0,
		ground_height(0.0, Field.SPOT_Z) - GROUND_THICKNESS * 0.5,
		(Field.PITCH_MIN_Z + Field.PITCH_MAX_Z) * 0.5
	)
	_ground.add_child(collider)
	add_child(_ground)


func _build_scuffs() -> void:
	_scuff_material = StandardMaterial3D.new()
	_scuff_material.albedo_color = Color(1.0, 1.0, 1.0, 1.0)
	_scuff_material.albedo_texture = Tex.radial(64)
	_scuff_material.vertex_color_use_as_albedo = true
	_scuff_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	# Soft edges rule out alpha scissor here, so the patches must not write
	# depth: overlapping marks then blend in any order without ever fighting.
	_scuff_material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	# The quad's facing depends on how Meshes builds it, so both sides are lit.
	_scuff_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	_scuff_material.roughness = 1.0
	_scuff_material.metallic = 0.0
	_scuff_material.specular_mode = BaseMaterial3D.SPECULAR_DISABLED

	var multi := MultiMesh.new()
	# Flags before the instance count: changing them afterwards throws the
	# buffer away and every mark already written with it.
	multi.transform_format = MultiMesh.TRANSFORM_3D
	multi.use_colors = true
	multi.mesh = Meshes.quad(1.0, 1.0)
	multi.instance_count = MAX_SCUFFS
	multi.visible_instance_count = 0

	_scuffs = MultiMeshInstance3D.new()
	_scuffs.name = "Scuffs"
	_scuffs.multimesh = multi
	_scuffs.material_override = _scuff_material
	_scuffs.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# A generous explicit bound: the instance transforms are rewritten at run
	# time, and a stale computed bound is how a MultiMesh vanishes on screen.
	_scuffs.custom_aabb = AABB(
		Vector3(-Field.PITCH_HALF_X, -1.0, Field.PITCH_MIN_Z),
		Vector3(Field.PITCH_HALF_X * 2.0, 2.0, Field.PITCH_MAX_Z - Field.PITCH_MIN_Z)
	)
	add_child(_scuffs)
	_scuff_count = 0


# --- marking helpers --------------------------------------------------------


## Next height off the anti coplanarity ladder, see note 2 at the top.
func _next_lift() -> float:
	var lift := LINE_LIFT + float(_lift_index) * LINE_LIFT_STEP
	_lift_index += 1
	return lift


## Lifts a flat (x, z) polyline onto the turf at the next free height.
func _lift_points(flat: PackedVector2Array, lift: float) -> PackedVector3Array:
	var out := PackedVector3Array()
	out.resize(flat.size())
	for i in flat.size():
		var p := flat[i]
		out[i] = Vector3(p.x, ground_height(p.x, p.y) + lift, p.y)
	return out


func _add_strip(
	parts: Array[ArrayMesh], flat: PackedVector2Array, closed: bool, width: float = LINE_WIDTH
) -> void:
	if flat.size() < 2:
		return
	var mesh := Meshes.line_strip(_lift_points(flat, _next_lift()), width, closed)
	if mesh == null or mesh.get_surface_count() == 0:
		push_warning("Pitch: Meshes.line_strip produced no surface for a marking.")
		return
	parts.append(mesh)


## A painted dot (penalty spot, centre mark). Drawn as one very fat closed
## ribbon rather than as a disc: it leaves a millimetric pinhole at the exact
## centre, which is invisible, and it avoids the degenerate triangles a zero
## radius inner edge would produce.
func _add_dot(parts: Array[ArrayMesh], cx: float, cz: float) -> void:
	var inner := MARK_RADIUS * 0.05
	var mid := (MARK_RADIUS + inner) * 0.5
	_add_strip(parts, _arc_points(cx, cz, mid, 0.0, TAU, true), true, MARK_RADIUS - inner)


## Samples a circle arc in the pitch plane. Angles are measured in the XZ plane,
## x = cx + cos(a) * radius and z = cz + sin(a) * radius. A closed arc drops the
## duplicated end point, since line_strip closes the loop itself.
func _arc_points(
	cx: float, cz: float, radius: float, from_angle: float, to_angle: float, closed: bool
) -> PackedVector2Array:
	var span := absf(to_angle - from_angle)
	var arc_length := span * maxf(radius, 0.001)
	var segments := clampi(int(ceil(arc_length / ARC_SEGMENT_LENGTH)), MIN_ARC_SEGMENTS, 256)
	var count := segments if closed else segments + 1
	var out := PackedVector2Array()
	out.resize(count)
	for i in count:
		var angle := lerpf(from_angle, to_angle, float(i) / float(segments))
		out[i] = Vector2(cx + cos(angle) * radius, cz + sin(angle) * radius)
	return out


## Welds every ribbon into one surface, so the paint costs a single draw call.
## Returns null when there is nothing to weld.
func _merge(parts: Array[ArrayMesh]) -> ArrayMesh:
	if parts.is_empty():
		return null
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	var used := 0
	var normals_present := true
	for mesh in parts:
		if mesh == null or mesh.get_surface_count() == 0:
			continue
		if (mesh.surface_get_format(0) & Mesh.ARRAY_FORMAT_NORMAL) == 0:
			normals_present = false
		tool.append_from(mesh, 0, Transform3D.IDENTITY)
		used += 1
	if used == 0:
		return null
	# Only rebuild the normals when the source had none: a ribbon that already
	# carries them is flat and facing up, and recomputing would gain nothing.
	if not normals_present:
		tool.generate_normals()
	var merged := tool.commit()
	if merged == null or merged.get_surface_count() == 0:
		return null
	return merged
