class_name SettlementMob
extends Node3D
## Lightweight voxel-world actor. It deliberately uses the same height/block
## queries as the player instead of Godot collision bodies, because terrain
## chunks are procedural meshes without StaticBody3D nodes.

enum Kind { VILLAGER, DOG, PIG, COW }

const VILLAGER_SPEED := 1.35
const DOG_SPEED := 2.0
const PIG_SPEED := 1.15
const COW_SPEED := 0.95
const TURN_SPEED := 7.0
const ARRIVAL_DISTANCE := 0.35
const MAX_STEP := 1

var kind: Kind = Kind.VILLAGER
var home := Vector3.ZERO

var _world: VoxelWorld
var _rng := RandomNumberGenerator.new()
var _target := Vector3.ZERO
var _decision_time := 0.0
var _walk_phase := 0.0
var _legs: Array[Node3D] = []
var _tail: Node3D


func setup(world: VoxelWorld, mob_kind: Kind, spawn: Vector3, actor_seed: int) -> void:
	_world = world
	kind = mob_kind
	home = spawn
	global_position = spawn
	_rng.seed = actor_seed
	_build_model()
	_choose_routine()


func _physics_process(delta: float) -> void:
	if _world == null:
		return
	_decision_time -= delta
	var flat := Vector2(_target.x - global_position.x, _target.z - global_position.z)
	if _decision_time <= 0.0 or flat.length() <= ARRIVAL_DISTANCE:
		_choose_routine()
		flat = Vector2(_target.x - global_position.x, _target.z - global_position.z)

	var moving := flat.length() > ARRIVAL_DISTANCE
	if moving:
		var direction := flat.normalized()
		var speed := _move_speed()
		var next := global_position + Vector3(direction.x, 0.0, direction.y) * speed * delta
		var next_y := _walkable_height(next)
		if next_y > -1000.0 and absf(next_y - global_position.y) <= float(MAX_STEP) + 0.05:
			global_position = Vector3(next.x, next_y, next.z)
			var desired_yaw := atan2(direction.x, direction.y)
			rotation.y = lerp_angle(rotation.y, desired_yaw, minf(1.0, TURN_SPEED * delta))
			_walk_phase += delta * speed * 5.5
		else:
			_choose_routine()
			moving = false
	_animate_walk(moving, delta)


func _choose_routine() -> void:
	# Pauses are part of the routine, which keeps a settlement from looking like
	# every actor is perpetually circling its house.
	if _rng.randf() < 0.28:
		_target = global_position
		_decision_time = _rng.randf_range(1.0, 3.8)
		return
	var radius := 12.0
	if kind == Kind.DOG:
		radius = 8.0
	elif kind == Kind.PIG or kind == Kind.COW:
		# Pen inner dimensions are 11x9. Keeping targets within 3.4 blocks of
		# home leaves body room before the solid one-block barrier.
		radius = 3.4
	for attempt in 12:
		var angle := _rng.randf_range(0.0, TAU)
		var distance := _rng.randf_range(2.0, radius)
		var candidate := home + Vector3(cos(angle) * distance, 0.0, sin(angle) * distance)
		var y := _walkable_height(candidate)
		if y > -1000.0:
			_target = Vector3(candidate.x, y, candidate.z)
			_decision_time = _rng.randf_range(3.0, 7.0)
			return
	_target = home
	_decision_time = 2.0


func _walkable_height(point: Vector3) -> float:
	var wx := floori(point.x)
	var wz := floori(point.z)
	if not _world.has_chunk_at(wx, wz):
		return -10000.0
	var h := _world.surface_height(wx, wz)
	if h < ChunkData.SEA_LEVEL:
		return -10000.0
	# Actors avoid liquids and generated structure walls. Cross-shaped plants do
	# not collide, so they remain valid walking cells.
	if Blocks.is_liquid(_world.get_block(wx, h + 1, wz)):
		return -10000.0
	var feet_y := h + 1
	while feet_y < ChunkData.SIZE_Y - 2 and Blocks.collides(_world.get_block(wx, feet_y, wz)):
		feet_y += 1
	if Blocks.collides(_world.get_block(wx, feet_y + 1, wz)):
		return -10000.0
	return float(feet_y)


func _box(parent: Node3D, name_: String, size: Vector3, pos: Vector3, color: Color) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = name_
	pivot.position = pos
	parent.add_child(pivot)
	var mesh_node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh_node.mesh = mesh
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.9
	mesh_node.material_override = material
	mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	pivot.add_child(mesh_node)
	return pivot


func _build_model() -> void:
	match kind:
		Kind.DOG:
			_build_dog()
		Kind.PIG:
			_build_pig()
		Kind.COW:
			_build_cow()
		_:
			_build_villager()


func _move_speed() -> float:
	match kind:
		Kind.DOG:
			return DOG_SPEED
		Kind.PIG:
			return PIG_SPEED
		Kind.COW:
			return COW_SPEED
		_:
			return VILLAGER_SPEED


func _build_villager() -> void:
	var cloth := Color(0.42, 0.18, 0.10)
	var skin := Color(0.58, 0.36, 0.22)
	_box(self, "Body", Vector3(0.62, 0.78, 0.34), Vector3(0.0, 1.05, 0.0), cloth)
	_box(self, "Head", Vector3(0.56, 0.56, 0.56), Vector3(0.0, 1.72, 0.0), skin)
	_box(self, "Nose", Vector3(0.16, 0.18, 0.20), Vector3(0.0, 1.66, 0.36), skin.darkened(0.08))
	_box(self, "Arms", Vector3(0.72, 0.20, 0.22), Vector3(0.0, 1.02, 0.25), skin.darkened(0.15))
	_legs.append(_box(self, "LegLeft", Vector3(0.24, 0.66, 0.27), Vector3(-0.17, 0.34, 0.0), cloth.darkened(0.3)))
	_legs.append(_box(self, "LegRight", Vector3(0.24, 0.66, 0.27), Vector3(0.17, 0.34, 0.0), cloth.darkened(0.3)))


func _build_dog() -> void:
	var fur := Color(0.56, 0.55, 0.51)
	_box(self, "Body", Vector3(0.45, 0.48, 0.88), Vector3(0.0, 0.55, 0.0), fur)
	_box(self, "Head", Vector3(0.48, 0.50, 0.48), Vector3(0.0, 0.79, 0.58), fur.lightened(0.06))
	_box(self, "Muzzle", Vector3(0.30, 0.22, 0.25), Vector3(0.0, 0.70, 0.91), Color(0.35, 0.30, 0.25))
	_box(self, "EarLeft", Vector3(0.14, 0.28, 0.16), Vector3(-0.18, 1.04, 0.56), fur.darkened(0.25))
	_box(self, "EarRight", Vector3(0.14, 0.28, 0.16), Vector3(0.18, 1.04, 0.56), fur.darkened(0.25))
	for x in [-0.15, 0.15]:
		for z in [-0.28, 0.28]:
			_legs.append(_box(self, "Leg", Vector3(0.15, 0.45, 0.16), Vector3(x, 0.23, z), fur.darkened(0.12)))
	_tail = _box(self, "Tail", Vector3(0.12, 0.12, 0.55), Vector3(0.0, 0.73, -0.58), fur)
	_tail.rotation.x = -0.55


func _build_pig() -> void:
	var pink := Color(0.92, 0.55, 0.61)
	_box(self, "Body", Vector3(0.72, 0.62, 1.05), Vector3(0.0, 0.62, 0.0), pink)
	_box(self, "Head", Vector3(0.62, 0.58, 0.54), Vector3(0.0, 0.72, 0.70), pink.lightened(0.04))
	_box(self, "Snout", Vector3(0.38, 0.24, 0.18), Vector3(0.0, 0.65, 1.05), Color(0.96, 0.66, 0.70))
	_box(self, "EarLeft", Vector3(0.16, 0.20, 0.12), Vector3(-0.22, 1.08, 0.72), pink.darkened(0.08))
	_box(self, "EarRight", Vector3(0.16, 0.20, 0.12), Vector3(0.22, 1.08, 0.72), pink.darkened(0.08))
	for x in [-0.24, 0.24]:
		for z in [-0.32, 0.32]:
			_legs.append(_box(self, "Leg", Vector3(0.18, 0.42, 0.18), Vector3(x, 0.22, z), pink.darkened(0.18)))


func _build_cow() -> void:
	var hide := Color(0.30, 0.20, 0.14)
	var white := Color(0.88, 0.84, 0.74)
	_box(self, "Body", Vector3(0.92, 0.86, 1.35), Vector3(0.0, 0.88, 0.0), hide)
	_box(self, "Patch", Vector3(0.94, 0.42, 0.50), Vector3(0.0, 0.98, -0.12), white)
	_box(self, "Head", Vector3(0.72, 0.70, 0.62), Vector3(0.0, 1.02, 0.92), hide.darkened(0.06))
	_box(self, "Muzzle", Vector3(0.48, 0.28, 0.20), Vector3(0.0, 0.88, 1.32), Color(0.70, 0.48, 0.42))
	_box(self, "HornLeft", Vector3(0.12, 0.18, 0.12), Vector3(-0.30, 1.43, 0.93), white)
	_box(self, "HornRight", Vector3(0.12, 0.18, 0.12), Vector3(0.30, 1.43, 0.93), white)
	for x in [-0.32, 0.32]:
		for z in [-0.42, 0.42]:
			_legs.append(_box(self, "Leg", Vector3(0.20, 0.64, 0.22), Vector3(x, 0.33, z), hide.darkened(0.12)))
	_tail = _box(self, "Tail", Vector3(0.12, 0.12, 0.68), Vector3(0.0, 1.05, -0.88), hide)
	_tail.rotation.x = -0.45


func _animate_walk(moving: bool, delta: float) -> void:
	var amount := 0.55 if moving else 0.0
	for i in _legs.size():
		var side := -1.0 if (i & 1) else 1.0
		var target_angle := sin(_walk_phase) * amount * side
		_legs[i].rotation.x = lerpf(_legs[i].rotation.x, target_angle, minf(1.0, delta * 10.0))
	if _tail != null:
		_tail.rotation.y = sin(Time.get_ticks_msec() * 0.008) * 0.45
