class_name ChunkNode
extends MeshInstance3D
## Scene-side representation of one chunk column.
##
## The node owns the ArrayMesh built by Mesher.build_mesh_data() plus one
## OmniLight3D per emissive block of the chunk. Instances are pooled by the
## world: setup() rebinds a recycled node to another chunk and release() puts it
## back into a clean state without leaking the previous mesh or lights.
##
## Everything here touches the scene tree, so every method must run on the main
## thread only.

## Hard cap on lights per chunk. A cave full of torches would otherwise blow the
## renderer's per-object light budget.
const MAX_LIGHTS := 32

## Padding of the custom AABB, in world units. Vertex wind displacement moves
## geometry slightly outside the chunk box and the renderer must not cull a
## chunk the player is standing next to.
const _AABB_MARGIN := 1.0

const _LAMP_COLOR := Color(1.0, 0.95, 0.82)
const _LAMP_ENERGY := 1.6
const _LAMP_RANGE := 9.0

const _TORCH_COLOR := Color(1.0, 0.72, 0.36)
const _TORCH_ENERGY := 1.1
const _TORCH_RANGE := 7.0

var cx: int = 0
var cz: int = 0

## Materials indexed by Blocks.Surface, handed over by the world.
var _materials: Array[Material] = []

## Live OmniLight3D children, owned by this node.
var _lights: Array[OmniLight3D] = []


func _init() -> void:
	# The mesh is authored in chunk local space and the node carries the offset,
	# so the AABB is the chunk column grown by the wind margin.
	custom_aabb = AABB(
		Vector3(-_AABB_MARGIN, -_AABB_MARGIN, -_AABB_MARGIN),
		Vector3(
			float(ChunkData.SIZE_X) + 2.0 * _AABB_MARGIN,
			float(ChunkData.SIZE_Y) + 2.0 * _AABB_MARGIN,
			float(ChunkData.SIZE_Z) + 2.0 * _AABB_MARGIN
		)
	)
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON


## Binds the node to a chunk: moves it to the right world position and stores
## the surface materials (indexed by Blocks.Surface).
func setup(chunk_x: int, chunk_z: int, surface_materials: Array[Material]) -> void:
	cx = chunk_x
	cz = chunk_z
	_materials = surface_materials
	position = Vector3(float(cx * ChunkData.SIZE_X), 0.0, float(cz * ChunkData.SIZE_Z))
	name = "Chunk_%d_%d" % [cx, cz]


## Uploads the output of Mesher.build_mesh_data() and rebuilds the light set.
## Main thread only. Safe to call again on every edit of the chunk.
func apply(mesh_data: Dictionary) -> void:
	release()
	if mesh_data.is_empty():
		return

	var surfaces: Array = mesh_data.get("surfaces", []) as Array
	var arr_mesh := ArrayMesh.new()
	var flags: int = Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT

	# The mesh surface index is the running count of surfaces actually added, not
	# the Blocks.Surface constant, so keep an explicit parallel list of the
	# material each created surface expects.
	var created_materials: Array[Material] = []

	for surface_id in surfaces.size():
		var entry: Variant = surfaces[surface_id]
		if entry == null:
			continue
		if not (entry is Array):
			push_warning("ChunkNode(%d, %d): surface %d is not an Array" % [cx, cz, surface_id])
			continue
		var arrays: Array = entry
		if arrays.size() != Mesh.ARRAY_MAX:
			push_warning("ChunkNode(%d, %d): surface %d has %d slots, expected %d"
					% [cx, cz, surface_id, arrays.size(), Mesh.ARRAY_MAX])
			continue
		var vertex_slot: Variant = arrays[Mesh.ARRAY_VERTEX]
		if not (vertex_slot is PackedVector3Array):
			continue
		var verts: PackedVector3Array = vertex_slot
		if verts.is_empty():
			continue
		arr_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, flags)
		created_materials.append(_material_for(surface_id))

	if not created_materials.is_empty():
		mesh = arr_mesh
		for i in created_materials.size():
			var mat: Material = created_materials[i]
			if mat != null:
				set_surface_override_material(i, mat)

	_spawn_lights(
		mesh_data.get("lights", PackedVector3Array()) as PackedVector3Array,
		mesh_data.get("light_ids", PackedInt32Array()) as PackedInt32Array
	)


## Drops the mesh and every light child. Leaves the node ready for reuse.
func release() -> void:
	for light in _lights:
		if is_instance_valid(light):
			if light.get_parent() == self:
				remove_child(light)
			light.queue_free()
	_lights.clear()
	# Dropping the reference frees the previous ArrayMesh and clears the surface
	# override slots along with it.
	mesh = null


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


func _material_for(surface_id: int) -> Material:
	if surface_id < 0 or surface_id >= _materials.size():
		return null
	return _materials[surface_id]


func _spawn_lights(positions: PackedVector3Array, ids: PackedInt32Array) -> void:
	var count: int = mini(positions.size(), ids.size())
	if count <= 0:
		return
	if positions.size() != ids.size():
		push_warning("ChunkNode(%d, %d): lights and light_ids differ in size" % [cx, cz])

	# Highest lights first: when a chunk exceeds the budget, the ones near the
	# surface are the ones the player actually sees.
	var order: Array[int] = []
	order.resize(count)
	for i in count:
		order[i] = i
	var heights := positions
	order.sort_custom(func(a: int, b: int) -> bool: return heights[a].y > heights[b].y)

	var limit: int = mini(count, MAX_LIGHTS)
	for k in limit:
		var index: int = order[k]
		var light := _make_light(ids[index])
		light.position = positions[index]
		add_child(light)
		_lights.append(light)


func _make_light(block_id: int) -> OmniLight3D:
	var light := OmniLight3D.new()
	light.shadow_enabled = false
	light.light_specular = 0.25
	match block_id:
		Blocks.LAMP:
			light.light_color = _LAMP_COLOR
			light.light_energy = _LAMP_ENERGY
			light.omni_range = _LAMP_RANGE
		Blocks.TORCH:
			light.light_color = _TORCH_COLOR
			light.light_energy = _TORCH_ENERGY
			light.omni_range = _TORCH_RANGE
		_:
			# Any other emissive block: derive a sane glow from its emission.
			var emission: float = 0.0
			if block_id >= 0 and block_id < Blocks.COUNT:
				emission = Blocks.emission(block_id)
			light.light_color = _TORCH_COLOR.lerp(_LAMP_COLOR, emission)
			light.light_energy = 0.6 + 1.0 * emission
			light.omni_range = _TORCH_RANGE
	light.omni_attenuation = 1.4
	return light
