## Shared visual effects of CALL OF WAR: tracers, muzzle flashes, impacts,
## decals, blood, shell casings, explosions, smoke and objective markers.
##
## Everything is POOLED. Allocating a node per bullet is the shortest known
## path to fifteen frames per second in a firefight, so every pool is built
## once in `setup()` and the oldest entry is recycled when the pool runs dry.
## After the warm up, firing an MG 42 allocates nothing at all.
##
## Getting hold of this node from anywhere:
##     var nodes := get_tree().get_nodes_in_group("vfx")
##     if not nodes.is_empty():
##         (nodes[0] as Vfx).impact(point, normal, surface)
##
## Two deliberate behaviours:
##   - `tracer()` only draws one streak out of TRACER_ONE_IN calls, the way a
##     real belt mixes one tracer round with several ball rounds. Callers do
##     not have to count anything;
##   - `explosion()` never touches the camera. The shake is applied by
##     Ballistics.explode() on whoever owns a camera rig, so a blast seen from
##     a hundred metres away does not rattle the screen.
class_name Vfx
extends Node3D

# --- Pool sizes ------------------------------------------------------------

const TRACER_POOL := 48
const FLASH_POOL := 24
const IMPACT_POOL := 64
const DECAL_POOL := 64
const CASING_POOL := 32
const EXPLOSION_POOL := 8
const SMOKE_POOL := 6

## One streak drawn out of this many bullets.
const TRACER_ONE_IN := 3
## Metres of visible streak behind the flying round.
const TRACER_LENGTH := 5.0
const TRACER_THICKNESS := 0.035
## Slowest a tracer may travel, so a pistol round stays readable.
const TRACER_MIN_SPEED := 160.0

const FLASH_SECONDS := 0.055
const DECAL_SECONDS := 14.0
const DECAL_FADE := 3.0
const CASING_SECONDS := 2.4
const EXPLOSION_SECONDS := 0.9
const MARKER_BOB := 0.18
const MARKER_BOB_SPEED := 1.7

# --- Pooled entries --------------------------------------------------------

class _Tracer extends RefCounted:
	var node: MeshInstance3D
	var origin: Vector3
	var direction: Vector3
	var speed: float = 400.0
	var travelled: float = 0.0
	var total: float = 0.0
	var active: bool = false


class _Flash extends RefCounted:
	var node: Node3D
	var mesh: MeshInstance3D
	var light: OmniLight3D
	var left: float = 0.0
	var size: float = 1.0
	var active: bool = false


class _Burst extends RefCounted:
	var node: GPUParticles3D
	var left: float = 0.0
	var active: bool = false


class _Decal extends RefCounted:
	var node: MeshInstance3D
	var material: StandardMaterial3D
	var left: float = 0.0
	var base_alpha: float = 0.7
	var active: bool = false


class _Casing extends RefCounted:
	var node: MeshInstance3D
	var velocity: Vector3 = Vector3.ZERO
	var spin: Vector3 = Vector3.ZERO
	var floor_y: float = 0.0
	var left: float = 0.0
	var active: bool = false


class _Blast extends RefCounted:
	var node: Node3D
	var ball: MeshInstance3D
	var material: StandardMaterial3D
	var light: OmniLight3D
	var debris: GPUParticles3D
	var radius: float = 6.0
	var left: float = 0.0
	var active: bool = false


class _Column extends RefCounted:
	var node: GPUParticles3D
	var left: float = 0.0
	## Time left for the last emitted puffs to finish once emission stopped.
	var drain: float = 0.0
	var active: bool = false


class _Marker extends RefCounted:
	var id: int = 0
	var node: Node3D
	var diamond: MeshInstance3D
	var label: Label3D
	var anchor: Vector3 = Vector3.ZERO
	var text: String = ""

# --- State -----------------------------------------------------------------

var _built: bool = false
var _time: float = 0.0
var _tracer_counter: int = 0
var _next_marker_id: int = 1

var _tracers: Array[_Tracer] = []
var _flashes: Array[_Flash] = []
var _impacts: Array[_Burst] = []
var _decals: Array[_Decal] = []
var _casings: Array[_Casing] = []
var _blasts: Array[_Blast] = []
var _columns: Array[_Column] = []
var _markers: Dictionary = {}

var _tracer_at: int = 0
var _flash_at: int = 0
var _impact_at: int = 0
var _decal_at: int = 0
var _casing_at: int = 0
var _blast_at: int = 0
var _column_at: int = 0

var _rng := RandomNumberGenerator.new()

## Shared per surface resources, built once.
var _impact_process: Dictionary = {}
var _impact_mesh: Dictionary = {}
var _decal_color: Dictionary = {}
var _marker_materials: Dictionary = {}

var _tracer_mesh: BoxMesh
var _tracer_material: Material
var _flash_mesh: Mesh
var _flash_material: Material
var _casing_mesh: BoxMesh
var _casing_material: Material
var _diamond_mesh: Mesh
var _decal_mesh: QuadMesh
var _blood_process: ParticleProcessMaterial
var _blood_mesh: Mesh
var _smoke_process: ParticleProcessMaterial
var _smoke_mesh: Mesh
var _debris_process: ParticleProcessMaterial
var _debris_mesh: Mesh


func _ready() -> void:
	if not is_in_group("vfx"):
		add_to_group("vfx")
	_ensure_built()


## Builds every pool. Safe to call twice.
func setup() -> void:
	_ensure_built()


func _ensure_built() -> void:
	if _built:
		return
	_built = true
	_rng.randomize()
	_build_shared()
	_build_tracers()
	_build_flashes()
	_build_impacts()
	_build_decals()
	_build_casings()
	_build_blasts()
	_build_columns()

# --- Shared resources ------------------------------------------------------

func _build_shared() -> void:
	_tracer_mesh = BoxMesh.new()
	_tracer_mesh.size = Vector3(TRACER_THICKNESS, TRACER_THICKNESS, 1.0)
	_tracer_material = _flat(Palette.TRACER, true)

	_flash_mesh = _make_flash_mesh()
	_flash_material = _flat(Palette.MUZZLE, true)

	_casing_mesh = BoxMesh.new()
	_casing_mesh.size = Vector3(0.011, 0.011, 0.048)
	_casing_material = _flat(Color(0.34, 0.24, 0.08), false)

	_decal_mesh = QuadMesh.new()
	_decal_mesh.size = Vector2(0.34, 0.34)

	_diamond_mesh = _make_diamond_mesh()

	_decal_color = {
		"dirt": Color(0.07, 0.05, 0.03),
		"stone": Color(0.06, 0.06, 0.06),
		"wood": Color(0.05, 0.03, 0.02),
		"metal": Color(0.05, 0.05, 0.06),
		"flesh": Palette.BLOOD,
		"water": Color(0.04, 0.07, 0.08),
	}

	for surface in ["dirt", "stone", "wood", "metal", "water"]:
		_impact_process[surface] = _make_impact_process(surface)
		_impact_mesh[surface] = _make_impact_mesh(surface)

	_blood_process = _make_impact_process("flesh")
	_blood_mesh = _make_impact_mesh("flesh")
	_smoke_process = _make_smoke_process()
	_smoke_mesh = _make_debris_mesh(Palette.SMOKE, 0.55, false)
	_debris_process = _make_debris_process()
	_debris_mesh = _make_debris_mesh(Color(0.10, 0.08, 0.06), 0.16, false)


## Flat colour material, taken from the shared library when it is available so
## the whole game keeps a single material per colour.
func _flat(color: Color, emissive: bool) -> Material:
	var shared: Material = MatLib.flat(color, emissive)
	if shared != null:
		return shared
	return _local_flat(color, emissive)


func _local_flat(color: Color, emissive: bool) -> Material:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	if emissive:
		mat.emission_enabled = true
		mat.emission = color
		mat.emission_energy_multiplier = 3.0
	return mat


## Two crossed quads, cheap and always readable whatever the view angle.
func _make_flash_mesh() -> Mesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := 0.16
	var depth := 0.30
	for pass_index in 2:
		var side := Vector3(half, 0.0, 0.0) if pass_index == 0 else Vector3(0.0, half, 0.0)
		# The flash is built along +Z, not -Z. `_aligned_basis(direction, true)`
		# returns a basis whose Z column IS the firing direction, so a cone drawn
		# towards -Z came out of the muzzle backwards: it grew over the view model
		# and into the camera (the muzzle sits 45 to 66 cm from a 5 cm near plane)
		# instead of jetting out in front of the barrel. Every caller passes the
		# bullet direction, so the defect was systematic.
		var tip := Vector3(0.0, 0.0, depth)
		var back := Vector3(0.0, 0.0, -0.04)
		st.set_normal(Vector3.BACK)
		st.add_vertex(back + side)
		st.add_vertex(tip)
		st.add_vertex(back - side)
		st.set_normal(Vector3.BACK)
		st.add_vertex(back - side)
		st.add_vertex(tip)
		st.add_vertex(back + side)
	return st.commit()


## Octahedron used as the objective marker.
func _make_diamond_mesh() -> Mesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var top := Vector3(0.0, 0.42, 0.0)
	var bottom := Vector3(0.0, -0.42, 0.0)
	var ring: Array[Vector3] = [
		Vector3(0.26, 0.0, 0.0), Vector3(0.0, 0.0, 0.26),
		Vector3(-0.26, 0.0, 0.0), Vector3(0.0, 0.0, -0.26),
	]
	for i in ring.size():
		var a: Vector3 = ring[i]
		var b: Vector3 = ring[(i + 1) % ring.size()]
		st.set_normal((a + b + top).normalized())
		st.add_vertex(top)
		st.add_vertex(a)
		st.add_vertex(b)
		st.set_normal((a + b + bottom).normalized())
		st.add_vertex(bottom)
		st.add_vertex(b)
		st.add_vertex(a)
	return st.commit()


func _make_impact_mesh(surface: String) -> Mesh:
	match surface:
		"stone", "metal":
			return _make_debris_mesh(Palette.MUZZLE, 0.030, true)
		"water":
			return _make_debris_mesh(Color(0.16, 0.24, 0.28), 0.035, false)
		"flesh":
			return _make_debris_mesh(Palette.BLOOD, 0.038, false)
		"wood":
			return _make_debris_mesh(Palette.WOOD_LIGHT, 0.034, false)
		_:
			return _make_debris_mesh(Palette.DIRT, 0.040, false)


func _make_debris_mesh(color: Color, size: float, emissive: bool) -> Mesh:
	var mesh := BoxMesh.new()
	mesh.size = Vector3(size, size, size)
	mesh.material = _flat(color, emissive)
	return mesh


func _make_impact_process(surface: String) -> ParticleProcessMaterial:
	var mat := ParticleProcessMaterial.new()
	mat.direction = Vector3(0.0, 1.0, 0.0)
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	mat.emission_sphere_radius = 0.05
	mat.gravity = Vector3(0.0, -12.0, 0.0)
	mat.scale_min = 0.5
	mat.scale_max = 1.0
	match surface:
		"stone", "metal":
			mat.spread = 42.0
			mat.initial_velocity_min = 5.0
			mat.initial_velocity_max = 11.0
			mat.damping_min = 3.0
			mat.damping_max = 7.0
		"water":
			mat.spread = 26.0
			mat.initial_velocity_min = 3.5
			mat.initial_velocity_max = 6.5
			mat.gravity = Vector3(0.0, -15.0, 0.0)
		"wood":
			mat.spread = 38.0
			mat.initial_velocity_min = 2.5
			mat.initial_velocity_max = 5.5
		"flesh":
			mat.spread = 48.0
			mat.initial_velocity_min = 1.8
			mat.initial_velocity_max = 4.2
			mat.gravity = Vector3(0.0, -9.0, 0.0)
		_:
			mat.spread = 34.0
			mat.initial_velocity_min = 2.0
			mat.initial_velocity_max = 5.0
	return mat


func _make_smoke_process() -> ParticleProcessMaterial:
	var mat := ParticleProcessMaterial.new()
	mat.direction = Vector3(0.0, 1.0, 0.0)
	mat.spread = 14.0
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	mat.emission_sphere_radius = 0.5
	mat.initial_velocity_min = 1.2
	mat.initial_velocity_max = 2.6
	mat.gravity = Vector3(0.4, 1.1, 0.2)
	mat.damping_min = 0.4
	mat.damping_max = 1.0
	mat.scale_min = 1.0
	mat.scale_max = 3.4
	return mat


func _make_debris_process() -> ParticleProcessMaterial:
	var mat := ParticleProcessMaterial.new()
	mat.direction = Vector3(0.0, 1.0, 0.0)
	mat.spread = 70.0
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	mat.emission_sphere_radius = 0.6
	mat.initial_velocity_min = 6.0
	mat.initial_velocity_max = 16.0
	mat.gravity = Vector3(0.0, -14.0, 0.0)
	mat.damping_min = 1.0
	mat.damping_max = 4.0
	mat.scale_min = 0.6
	mat.scale_max = 2.0
	return mat

# --- Pool construction -----------------------------------------------------

func _build_tracers() -> void:
	for i in TRACER_POOL:
		var entry := _Tracer.new()
		entry.node = MeshInstance3D.new()
		entry.node.mesh = _tracer_mesh
		entry.node.material_override = _tracer_material
		entry.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		entry.node.visible = false
		add_child(entry.node)
		_tracers.append(entry)


func _build_flashes() -> void:
	for i in FLASH_POOL:
		var entry := _Flash.new()
		entry.node = Node3D.new()
		entry.mesh = MeshInstance3D.new()
		entry.mesh.mesh = _flash_mesh
		entry.mesh.material_override = _flash_material
		entry.mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		entry.node.add_child(entry.mesh)
		entry.light = OmniLight3D.new()
		entry.light.light_color = Palette.MUZZLE
		entry.light.omni_range = 7.0
		entry.light.light_energy = 0.0
		entry.light.shadow_enabled = false
		entry.node.add_child(entry.light)
		entry.node.visible = false
		add_child(entry.node)
		_flashes.append(entry)


func _build_impacts() -> void:
	for i in IMPACT_POOL:
		var entry := _Burst.new()
		entry.node = GPUParticles3D.new()
		entry.node.amount = 10
		entry.node.lifetime = 0.6
		entry.node.one_shot = true
		entry.node.explosiveness = 1.0
		entry.node.local_coords = false
		entry.node.emitting = false
		entry.node.process_material = _impact_process["dirt"]
		entry.node.draw_pass_1 = _impact_mesh["dirt"]
		entry.node.visible = false
		add_child(entry.node)
		_impacts.append(entry)


func _build_decals() -> void:
	for i in DECAL_POOL:
		var entry := _Decal.new()
		entry.material = StandardMaterial3D.new()
		entry.material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		entry.material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		entry.material.cull_mode = BaseMaterial3D.CULL_DISABLED
		entry.material.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
		entry.material.albedo_color = Color(0.05, 0.04, 0.03, 0.0)
		entry.node = MeshInstance3D.new()
		entry.node.mesh = _decal_mesh
		entry.node.material_override = entry.material
		entry.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		entry.node.visible = false
		add_child(entry.node)
		_decals.append(entry)


func _build_casings() -> void:
	for i in CASING_POOL:
		var entry := _Casing.new()
		entry.node = MeshInstance3D.new()
		entry.node.mesh = _casing_mesh
		entry.node.material_override = _casing_material
		entry.node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		entry.node.visible = false
		add_child(entry.node)
		_casings.append(entry)


func _build_blasts() -> void:
	var ball_mesh := SphereMesh.new()
	ball_mesh.radius = 1.0
	ball_mesh.height = 2.0
	ball_mesh.radial_segments = 12
	ball_mesh.rings = 6
	for i in EXPLOSION_POOL:
		var entry := _Blast.new()
		entry.node = Node3D.new()
		entry.material = StandardMaterial3D.new()
		entry.material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		entry.material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		entry.material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		entry.material.cull_mode = BaseMaterial3D.CULL_DISABLED
		entry.material.albedo_color = Palette.FIRE
		entry.ball = MeshInstance3D.new()
		entry.ball.mesh = ball_mesh
		entry.ball.material_override = entry.material
		entry.ball.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		entry.node.add_child(entry.ball)
		entry.light = OmniLight3D.new()
		entry.light.light_color = Palette.FIRE
		entry.light.omni_range = 24.0
		entry.light.light_energy = 0.0
		entry.light.shadow_enabled = false
		entry.node.add_child(entry.light)
		entry.debris = GPUParticles3D.new()
		entry.debris.amount = 26
		entry.debris.lifetime = 1.4
		entry.debris.one_shot = true
		entry.debris.explosiveness = 0.95
		entry.debris.local_coords = false
		entry.debris.emitting = false
		entry.debris.process_material = _debris_process
		entry.debris.draw_pass_1 = _debris_mesh
		entry.node.add_child(entry.debris)
		entry.node.visible = false
		add_child(entry.node)
		_blasts.append(entry)


func _build_columns() -> void:
	for i in SMOKE_POOL:
		var entry := _Column.new()
		entry.node = GPUParticles3D.new()
		entry.node.amount = 28
		entry.node.lifetime = 3.6
		entry.node.one_shot = false
		entry.node.explosiveness = 0.0
		entry.node.local_coords = false
		entry.node.emitting = false
		entry.node.process_material = _smoke_process
		entry.node.draw_pass_1 = _smoke_mesh
		entry.node.visible = false
		add_child(entry.node)
		_columns.append(entry)

# --- Public API ------------------------------------------------------------

## A visible round travelling from `from` to `to` at the muzzle velocity of the
## weapon. Only one call out of TRACER_ONE_IN actually draws anything.
func tracer(from: Vector3, to: Vector3, speed: float) -> void:
	_ensure_built()
	_tracer_counter += 1
	if _tracer_counter % TRACER_ONE_IN != 0:
		return
	var delta := to - from
	var length := delta.length()
	if length < 0.5:
		return
	var entry := _take_tracer()
	entry.origin = from
	entry.direction = delta / length
	entry.total = length
	entry.speed = maxf(speed, TRACER_MIN_SPEED)
	entry.travelled = 0.0
	entry.active = true
	entry.node.visible = true
	_place_tracer(entry)


func muzzle_flash(at: Vector3, direction: Vector3, size: float = 1.0) -> void:
	_ensure_built()
	var entry := _take_flash()
	entry.active = true
	entry.left = FLASH_SECONDS
	entry.size = size
	entry.node.visible = true
	entry.node.global_transform = Transform3D(_aligned_basis(direction, true), at)
	entry.mesh.scale = Vector3.ONE * (size * _rng.randf_range(0.85, 1.25))
	entry.mesh.rotation.z = _rng.randf() * TAU
	entry.light.light_energy = 6.0 * size
	entry.light.omni_range = 7.0 * size


## A small burst of debris coloured by the surface, plus a fading decal.
func impact(at: Vector3, normal: Vector3, surface: String) -> void:
	_ensure_built()
	var key := surface
	if not _impact_process.has(key):
		key = "dirt"
	var entry := _take_impact()
	entry.node.process_material = _impact_process[key]
	entry.node.draw_pass_1 = _impact_mesh[key]
	entry.node.global_transform = Transform3D(_aligned_basis(normal, false), at + normal * 0.02)
	entry.node.visible = true
	entry.active = true
	entry.left = float(entry.node.lifetime) + 0.1
	entry.node.restart()
	entry.node.emitting = true
	if key != "water":
		_add_decal(at, normal, key, 0.7, _rng.randf_range(0.7, 1.25))


func blood(at: Vector3, normal: Vector3) -> void:
	_ensure_built()
	if not _blood_enabled():
		return
	var entry := _take_impact()
	entry.node.process_material = _blood_process
	entry.node.draw_pass_1 = _blood_mesh
	entry.node.global_transform = Transform3D(_aligned_basis(normal, false), at + normal * 0.02)
	entry.node.visible = true
	entry.active = true
	entry.left = float(entry.node.lifetime) + 0.1
	entry.node.restart()
	entry.node.emitting = true


## Flash, growing fireball, debris and a smoke column. The camera shake is NOT
## applied here: Ballistics.explode() gives it to whoever owns a camera rig.
func explosion(at: Vector3, radius: float) -> void:
	_ensure_built()
	var entry := _take_blast()
	entry.active = true
	entry.left = EXPLOSION_SECONDS
	entry.radius = maxf(radius, 1.0)
	entry.node.visible = true
	entry.node.global_position = at
	entry.ball.scale = Vector3.ONE * (entry.radius * 0.28)
	entry.material.albedo_color = Color(Palette.FIRE, 1.0)
	entry.light.light_energy = 14.0
	entry.light.omni_range = entry.radius * 3.0
	entry.debris.restart()
	entry.debris.emitting = true
	smoke_column(at + Vector3.UP * 0.4, 2.6)


func smoke_column(at: Vector3, seconds: float) -> void:
	_ensure_built()
	var entry := _take_column()
	entry.active = true
	entry.left = maxf(seconds, 0.2)
	entry.drain = 0.0
	entry.node.global_position = at
	entry.node.visible = true
	entry.node.restart()
	entry.node.emitting = true


## An ejected case, thrown to the side of `direction` and left to bounce once.
func shell_casing(at: Vector3, direction: Vector3) -> void:
	_ensure_built()
	var dir := direction.normalized()
	if dir.length_squared() < 0.5:
		dir = Vector3.FORWARD
	var side := dir.cross(Vector3.UP).normalized()
	if side.length_squared() < 0.5:
		side = Vector3.RIGHT
	var entry := _take_casing()
	entry.active = true
	entry.left = CASING_SECONDS
	entry.floor_y = at.y - 1.35
	entry.node.global_position = at
	entry.node.visible = true
	entry.node.scale = Vector3.ONE
	entry.velocity = -side * _rng.randf_range(1.6, 2.8) \
			+ Vector3.UP * _rng.randf_range(1.1, 2.0) \
			+ dir * _rng.randf_range(-0.4, 0.6)
	entry.spin = Vector3(
		_rng.randf_range(-12.0, 12.0),
		_rng.randf_range(-12.0, 12.0),
		_rng.randf_range(-18.0, 18.0))

# --- Markers ---------------------------------------------------------------

## A floating world space marker (objective diamond). Returns its id.
##
## Markers are always drawn on top of the geometry so an objective stays
## readable through a hedge or a wall, with the distance under the label.
func add_marker(at: Vector3, color: Color, label: String) -> int:
	_ensure_built()
	var entry := _Marker.new()
	entry.id = _next_marker_id
	_next_marker_id += 1
	entry.anchor = at
	entry.text = label
	entry.node = Node3D.new()

	entry.diamond = MeshInstance3D.new()
	entry.diamond.mesh = _diamond_mesh
	entry.diamond.material_override = _marker_material(color)
	entry.diamond.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	entry.node.add_child(entry.diamond)

	entry.label = Label3D.new()
	entry.label.text = label
	entry.label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	entry.label.no_depth_test = true
	entry.label.fixed_size = true
	entry.label.pixel_size = 0.0006
	entry.label.font_size = 48
	entry.label.outline_size = 14
	entry.label.modulate = color
	entry.label.outline_modulate = Color(0.0, 0.0, 0.0, 0.85)
	entry.label.render_priority = 20
	entry.label.position = Vector3(0.0, 0.75, 0.0)
	entry.node.add_child(entry.label)

	add_child(entry.node)
	entry.node.global_position = at
	_markers[entry.id] = entry
	return entry.id


func move_marker(marker_id: int, at: Vector3) -> void:
	if not _markers.has(marker_id):
		return
	var entry: _Marker = _markers[marker_id]
	entry.anchor = at


func remove_marker(marker_id: int) -> void:
	if not _markers.has(marker_id):
		return
	var entry: _Marker = _markers[marker_id]
	if is_instance_valid(entry.node):
		entry.node.queue_free()
	_markers.erase(marker_id)


func marker_count() -> int:
	return _markers.size()


func _marker_material(color: Color) -> Material:
	var key := color.to_rgba32()
	if _marker_materials.has(key):
		return _marker_materials[key]
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 2.0
	mat.no_depth_test = true
	mat.render_priority = 18
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_marker_materials[key] = mat
	return mat

# --- Housekeeping ----------------------------------------------------------

## Hides everything and drops every marker. Called when a scene is reloaded.
func clear_all() -> void:
	if not _built:
		return
	for entry in _tracers:
		entry.active = false
		entry.node.visible = false
	for flash in _flashes:
		flash.active = false
		flash.node.visible = false
		flash.light.light_energy = 0.0
	for burst in _impacts:
		burst.active = false
		burst.node.emitting = false
		burst.node.visible = false
	for decal in _decals:
		decal.active = false
		decal.node.visible = false
	for casing in _casings:
		casing.active = false
		casing.node.visible = false
	for blast in _blasts:
		blast.active = false
		blast.node.visible = false
		blast.light.light_energy = 0.0
		blast.debris.emitting = false
	for column in _columns:
		column.active = false
		column.left = 0.0
		column.drain = 0.0
		column.node.visible = false
		column.node.emitting = false
	for marker_id in _markers.keys():
		var marker: _Marker = _markers[marker_id]
		if is_instance_valid(marker.node):
			marker.node.queue_free()
	_markers.clear()


## Live entries, for the debug overlay.
func debug_line() -> String:
	var live := 0
	for entry in _tracers:
		if entry.active:
			live += 1
	return "vfx tracers=%d decals=%d marqueurs=%d" % [live, _decals.size(), _markers.size()]

# --- Frame update ----------------------------------------------------------

func _process(delta: float) -> void:
	if not _built:
		return
	_time += delta
	_update_tracers(delta)
	_update_flashes(delta)
	_update_bursts(delta)
	_update_decals(delta)
	_update_casings(delta)
	_update_blasts(delta)
	_update_columns(delta)
	_update_markers()


func _update_tracers(delta: float) -> void:
	for entry in _tracers:
		if not entry.active:
			continue
		entry.travelled += entry.speed * delta
		if entry.travelled >= entry.total:
			entry.active = false
			entry.node.visible = false
			continue
		_place_tracer(entry)


func _place_tracer(entry: _Tracer) -> void:
	var head: float = minf(entry.travelled, entry.total)
	var tail: float = maxf(head - TRACER_LENGTH, 0.0)
	var length: float = maxf(head - tail, 0.05)
	var middle := entry.origin + entry.direction * ((head + tail) * 0.5)
	entry.node.global_transform = Transform3D(_aligned_basis(entry.direction, true), middle)
	entry.node.scale = Vector3(1.0, 1.0, length)


func _update_flashes(delta: float) -> void:
	for entry in _flashes:
		if not entry.active:
			continue
		entry.left -= delta
		if entry.left <= 0.0:
			entry.active = false
			entry.node.visible = false
			entry.light.light_energy = 0.0
			continue
		var ratio := entry.left / FLASH_SECONDS
		entry.light.light_energy = 6.0 * entry.size * ratio


func _update_bursts(delta: float) -> void:
	for entry in _impacts:
		if not entry.active:
			continue
		entry.left -= delta
		if entry.left <= 0.0:
			entry.active = false
			entry.node.visible = false
			entry.node.emitting = false


func _update_decals(delta: float) -> void:
	for entry in _decals:
		if not entry.active:
			continue
		entry.left -= delta
		if entry.left <= 0.0:
			entry.active = false
			entry.node.visible = false
			continue
		if entry.left < DECAL_FADE:
			var color := entry.material.albedo_color
			color.a = entry.base_alpha * (entry.left / DECAL_FADE)
			entry.material.albedo_color = color


func _update_casings(delta: float) -> void:
	for entry in _casings:
		if not entry.active:
			continue
		entry.left -= delta
		if entry.left <= 0.0:
			entry.active = false
			entry.node.visible = false
			continue
		entry.velocity.y -= 19.6 * delta
		var next := entry.node.global_position + entry.velocity * delta
		if next.y <= entry.floor_y:
			next.y = entry.floor_y
			entry.velocity.y = -entry.velocity.y * 0.28
			entry.velocity.x *= 0.5
			entry.velocity.z *= 0.5
			entry.spin *= 0.4
		entry.node.global_position = next
		entry.node.rotate_x(entry.spin.x * delta)
		entry.node.rotate_y(entry.spin.y * delta)
		entry.node.rotate_z(entry.spin.z * delta)
		if entry.left < 0.4:
			entry.node.scale = Vector3.ONE * (entry.left / 0.4)


func _update_blasts(delta: float) -> void:
	for entry in _blasts:
		if not entry.active:
			continue
		entry.left -= delta
		if entry.left <= 0.0:
			entry.active = false
			entry.node.visible = false
			entry.light.light_energy = 0.0
			continue
		var ratio := 1.0 - entry.left / EXPLOSION_SECONDS
		entry.ball.scale = Vector3.ONE * (entry.radius * lerpf(0.28, 1.15, sqrt(ratio)))
		var color := entry.material.albedo_color
		color.a = clampf(1.0 - ratio * 1.35, 0.0, 1.0)
		color.r = lerpf(Palette.FIRE.r, 0.25, ratio)
		color.g = lerpf(Palette.FIRE.g, 0.20, ratio)
		color.b = lerpf(Palette.FIRE.b, 0.18, ratio)
		entry.material.albedo_color = color
		entry.light.light_energy = 14.0 * maxf(1.0 - ratio * 2.2, 0.0)


func _update_columns(delta: float) -> void:
	for entry in _columns:
		if not entry.active:
			continue
		if entry.left > 0.0:
			entry.left -= delta
			if entry.left <= 0.0:
				# Stop feeding the column but leave the last puffs to rise and
				# fade, otherwise the smoke vanishes in a hard cut.
				entry.node.emitting = false
				entry.drain = float(entry.node.lifetime)
			continue
		entry.drain -= delta
		if entry.drain <= 0.0:
			entry.active = false
			entry.node.visible = false


func _update_markers() -> void:
	if _markers.is_empty():
		return
	var camera := get_viewport().get_camera_3d() if is_inside_tree() else null
	var bob := sin(_time * MARKER_BOB_SPEED) * MARKER_BOB
	for marker_id in _markers:
		var entry: _Marker = _markers[marker_id]
		if not is_instance_valid(entry.node):
			continue
		entry.node.global_position = entry.anchor + Vector3(0.0, bob, 0.0)
		entry.diamond.rotate_y(0.02)
		if camera == null:
			continue
		var distance := camera.global_position.distance_to(entry.anchor)
		entry.label.text = "%s\n%d m" % [entry.text, int(round(distance))]

# --- Pool helpers ----------------------------------------------------------

func _add_decal(at: Vector3, normal: Vector3, surface: String, alpha: float, size: float) -> void:
	var entry := _take_decal()
	entry.active = true
	entry.left = DECAL_SECONDS
	entry.base_alpha = alpha
	var base: Color = _decal_color.get(surface, Color(0.06, 0.05, 0.04))
	entry.material.albedo_color = Color(base.r, base.g, base.b, alpha)
	entry.node.global_transform = Transform3D(_aligned_basis(normal, true), at + normal * 0.015)
	entry.node.scale = Vector3(size, size, 1.0)
	entry.node.visible = true


func _take_tracer() -> _Tracer:
	var entry: _Tracer = _tracers[_tracer_at]
	_tracer_at = (_tracer_at + 1) % _tracers.size()
	return entry


func _take_flash() -> _Flash:
	var entry: _Flash = _flashes[_flash_at]
	_flash_at = (_flash_at + 1) % _flashes.size()
	return entry


func _take_impact() -> _Burst:
	var entry: _Burst = _impacts[_impact_at]
	_impact_at = (_impact_at + 1) % _impacts.size()
	return entry


func _take_decal() -> _Decal:
	var entry: _Decal = _decals[_decal_at]
	_decal_at = (_decal_at + 1) % _decals.size()
	return entry


func _take_casing() -> _Casing:
	var entry: _Casing = _casings[_casing_at]
	_casing_at = (_casing_at + 1) % _casings.size()
	return entry


func _take_blast() -> _Blast:
	var entry: _Blast = _blasts[_blast_at]
	_blast_at = (_blast_at + 1) % _blasts.size()
	return entry


func _take_column() -> _Column:
	var entry: _Column = _columns[_column_at]
	_column_at = (_column_at + 1) % _columns.size()
	return entry


## Reads the blood setting through the node path instead of the `Game`
## identifier, so this file still compiles in a context without autoloads
## (which is exactly what the headless unit runner is). Defaults to on.
func _blood_enabled() -> bool:
	if not is_inside_tree():
		return true
	var settings := get_node_or_null(^"/root/Game")
	if settings == null:
		return true
	var value: Variant = settings.get("blood_effects")
	if value == null:
		return true
	return bool(value)


## Orthonormal basis whose Z axis (use_z) or Y axis follows `dir`.
func _aligned_basis(dir: Vector3, use_z: bool) -> Basis:
	var n := dir
	if n.length_squared() < 0.000001:
		n = Vector3.UP
	n = n.normalized()
	var reference := Vector3.UP
	if absf(n.dot(reference)) > 0.985:
		reference = Vector3.RIGHT
	var x := reference.cross(n).normalized()
	if use_z:
		var y := n.cross(x).normalized()
		return Basis(x, y, n)
	var z := x.cross(n).normalized()
	return Basis(x, n, z)
