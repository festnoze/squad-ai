## Flight trail of the ball, drawn as a camera facing ribbon.
##
## Why a ribbon and not a particle system: the trail exists to make the CURVE of
## the shot readable. A continuous strip shows the curvature of the path in one
## glance, while a spray of billboards only shows where the ball has been. The
## ribbon is rebuilt every frame from a short ring buffer of world space samples
## pushed by the ball at physics rate (120 Hz), which is far denser than the
## frame rate: the strip is smooth even on a 30 m/s shot.
##
## Three engine details this file depends on:
##  - The node sets `top_level = true` and keeps an identity transform, so the
##    vertices can be stored and emitted in WORLD space even though the trail is
##    a child of the moving ball. Without that, every point would be dragged
##    along by the ball and the ribbon would collapse to a dot.
##  - The material comes from `Mats.additive` but its albedo is forced to white
##    and `vertex_color_use_as_albedo` is turned on. The hot/cold colour is
##    carried by the vertex colour ONLY, so the tint is applied exactly once
##    rather than multiplied by both the material and the vertex.
##  - Additive blending ignores destination alpha, so the fade is baked into the
##    RGB of the vertex colour (premultiplied) as well as into its alpha.
##
## API, deliberately tiny: build() once, push(position, speed) per physics step,
## clear() when the ball is replaced on the spot.
class_name BallTrail
extends Node3D

## Ring buffer length. 96 samples at 120 Hz is 0.8 s of history, more than the
## lifetime below ever needs, so the buffer never truncates a live segment.
const MAX_POINTS := 96
## Seconds a sample stays visible.
const LIFETIME := 0.42
## Samples closer than this are dropped: a still ball must not pile up vertices.
const MIN_SPACING := 0.02
## Ribbon half width at the head (near the ball) and at the tail.
const WIDTH_HEAD := 0.085
const WIDTH_TAIL := 0.012
## Speed band mapped onto TRAIL_COLD .. TRAIL_HOT, in m/s.
const COLD_SPEED := 8.0
const HOT_SPEED := 32.0

var _mesh_instance: MeshInstance3D = null
var _mesh: ImmediateMesh = null
var _material: StandardMaterial3D = null
var _points: PackedVector3Array = PackedVector3Array()
var _born: PackedFloat32Array = PackedFloat32Array()
var _speeds: PackedFloat32Array = PackedFloat32Array()
var _now: float = 0.0
var _built: bool = false


## Creates the ribbon mesh and its material. Idempotent.
func build() -> void:
	if _built:
		return
	_built = true
	top_level = true
	transform = Transform3D.IDENTITY
	_mesh = ImmediateMesh.new()
	_mesh_instance = MeshInstance3D.new()
	_mesh_instance.name = "TrailRibbon"
	_mesh_instance.mesh = _mesh
	_mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_mesh_instance.material_override = _build_material()
	add_child(_mesh_instance)


func _ready() -> void:
	build()


func _process(delta: float) -> void:
	if not _built:
		return
	_now += delta
	_expire()
	_rebuild()


## Adds one world space sample. `speed` is the ball speed in m/s and drives the
## colour of that section of the ribbon.
func push(position: Vector3, speed: float) -> void:
	if not _built:
		build()
	var count: int = _points.size()
	if count > 0 and _points[count - 1].distance_to(position) < MIN_SPACING:
		return
	_points.append(position)
	_born.append(_now)
	_speeds.append(maxf(speed, 0.0))
	while _points.size() > MAX_POINTS:
		_points.remove_at(0)
		_born.remove_at(0)
		_speeds.remove_at(0)


## Drops every sample and empties the mesh.
func clear() -> void:
	_points.clear()
	_born.clear()
	_speeds.clear()
	if _mesh != null:
		_mesh.clear_surfaces()


# --- internals ---------------------------------------------------------------


func _build_material() -> StandardMaterial3D:
	var made: StandardMaterial3D = null
	var base: StandardMaterial3D = Mats.additive(Color(1.0, 1.0, 1.0, 1.0))
	if base != null:
		made = base.duplicate() as StandardMaterial3D
	if made == null:
		# Defensive fallback so the trail still renders if the cache handed back
		# something unexpected. Same intent: unshaded, additive, two sided.
		made = StandardMaterial3D.new()
		made.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		made.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		made.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	made.albedo_color = Color(1.0, 1.0, 1.0, 1.0)
	made.vertex_color_use_as_albedo = true
	made.cull_mode = BaseMaterial3D.CULL_DISABLED
	made.disable_receive_shadows = true
	_material = made
	return made


func _expire() -> void:
	while _points.size() > 0 and _now - _born[0] > LIFETIME:
		_points.remove_at(0)
		_born.remove_at(0)
		_speeds.remove_at(0)


func _eye_position() -> Vector3:
	if is_inside_tree():
		var viewport: Viewport = get_viewport()
		if viewport != null:
			var cam: Camera3D = viewport.get_camera_3d()
			if cam != null and is_instance_valid(cam):
				return cam.global_position
	return Vector3(0.0, 1.6, 20.0)


func _rebuild() -> void:
	if _mesh == null:
		return
	_mesh.clear_surfaces()
	var count: int = _points.size()
	if count < 2:
		return
	var eye: Vector3 = _eye_position()
	var last: float = float(count - 1)
	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP, _material)
	for i in count:
		var point: Vector3 = _points[i]
		var forward: Vector3 = _tangent(i, count)
		var view: Vector3 = eye - point
		if view.length_squared() < 1.0e-9:
			view = Vector3.UP
		var side: Vector3 = forward.cross(view.normalized())
		if side.length_squared() < 1.0e-8:
			side = forward.cross(Vector3.UP)
		if side.length_squared() < 1.0e-8:
			side = Vector3.RIGHT
		side = side.normalized()

		var age: float = clampf((_now - _born[i]) / LIFETIME, 0.0, 1.0)
		var head: float = float(i) / last
		var fade: float = pow(1.0 - age, 1.6) * (0.22 + 0.78 * head)
		var half_width: float = lerpf(WIDTH_TAIL, WIDTH_HEAD, head) * (0.35 + 0.65 * (1.0 - age))
		var hot: float = clampf((_speeds[i] - COLD_SPEED) / (HOT_SPEED - COLD_SPEED), 0.0, 1.0)
		var tint: Color = Palette.mix(Palette.TRAIL_COLD, Palette.TRAIL_HOT, hot)
		# Premultiplied on purpose: additive blending never reads the alpha.
		var vertex_colour := Color(tint.r * fade, tint.g * fade, tint.b * fade, fade)

		_mesh.surface_set_color(vertex_colour)
		_mesh.surface_set_uv(Vector2(0.0, head))
		_mesh.surface_add_vertex(point - side * half_width)
		_mesh.surface_set_color(vertex_colour)
		_mesh.surface_set_uv(Vector2(1.0, head))
		_mesh.surface_add_vertex(point + side * half_width)
	_mesh.surface_end()


## Central difference tangent, so the ribbon does not kink on a curved path.
func _tangent(index: int, count: int) -> Vector3:
	var raw: Vector3
	if index == 0:
		raw = _points[1] - _points[0]
	elif index == count - 1:
		raw = _points[count - 1] - _points[count - 2]
	else:
		raw = _points[index + 1] - _points[index - 1]
	if raw.length_squared() < 1.0e-9:
		return Vector3.FORWARD
	return raw.normalized()
