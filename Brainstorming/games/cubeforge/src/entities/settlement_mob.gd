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
var _visual_rng := RandomNumberGenerator.new()
var _visual_seed: int = 0
var _realistic: bool = false
var _target := Vector3.ZERO
var _decision_time := 0.0
var _walk_phase := 0.0
var _legs: Array[Node3D] = []
var _tail: Node3D
var _material_cache: Dictionary = {}


func _ready() -> void:
	var game := get_node_or_null(^"/root/Game")
	if game == null:
		return
	_realistic = bool(game.get("realistic"))
	var callback := Callable(self, "_on_render_settings_changed")
	if game.has_signal("settings_changed") and not game.is_connected("settings_changed", callback):
		game.connect("settings_changed", callback)


func setup(world: VoxelWorld, mob_kind: Kind, spawn: Vector3, actor_seed: int) -> void:
	_world = world
	kind = mob_kind
	home = spawn
	global_position = spawn
	_rng.seed = actor_seed
	_visual_seed = actor_seed
	_visual_rng.seed = actor_seed
	_build_model()
	_choose_routine()


func _on_render_settings_changed() -> void:
	var game := get_node_or_null(^"/root/Game")
	if game == null:
		return
	var active := bool(game.get("realistic"))
	if active == _realistic:
		return
	_realistic = active
	if get_child_count() > 0:
		_rebuild_model()


func _rebuild_model() -> void:
	for child in get_children():
		remove_child(child)
		child.free()
	_legs.clear()
	_tail = null
	_material_cache.clear()
	_visual_rng.seed = _visual_seed
	_build_model()


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
			var visual_y := next_y
			if _realistic:
				# Collision remains voxel-safe, but the visible body eases between
				# neighbouring elevations instead of popping up one full block.
				visual_y = lerpf(global_position.y, next_y, 1.0 - exp(-12.0 * delta))
			global_position = Vector3(next.x, visual_y, next.z)
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
	if _realistic and _rounded_part(name_):
		var mesh := SphereMesh.new()
		mesh.radius = 1.0
		mesh.height = 2.0
		mesh.radial_segments = 16
		mesh.rings = 8
		mesh_node.mesh = mesh
		mesh_node.scale = size * 0.5
	else:
		var mesh := BoxMesh.new()
		mesh.size = size
		mesh_node.mesh = mesh
	mesh_node.material_override = _material(color)
	mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	pivot.add_child(mesh_node)
	return pivot


func _rounded_part(part_name: String) -> bool:
	return part_name in ["Body", "Head", "Muzzle", "Snout", "Nose", "NoseTip",
		"Arms", "Hands", "Udder"] or part_name.begins_with("Leg") \
		or part_name.begins_with("Ear") or part_name.begins_with("Horn") \
		or part_name.begins_with("Tail")


func _material(color: Color) -> StandardMaterial3D:
	var key := color.to_rgba32()
	if _material_cache.has(key):
		return _material_cache[key]
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.58 if _realistic else 0.92
	material.metallic_specular = 0.34 if _realistic else 0.08
	_material_cache[key] = material
	return material


## Layered voxel eyes stay readable without image assets: white plate, coloured
## pupil and a tiny highlight, each slightly forward to avoid z-fighting.
func _eye(name_: String, x: float, y: float, z: float, scale: float,
		iris: Color = Color(0.16, 0.28, 0.20)) -> void:
	_box(self, name_ + "White", Vector3(0.13, 0.105, 0.025) * scale,
			Vector3(x, y, z), Color(0.94, 0.95, 0.90))
	_box(self, name_ + "Pupil", Vector3(0.052, 0.075, 0.026) * scale,
			Vector3(x, y - 0.004 * scale, z + 0.021 * scale), iris)
	_box(self, name_ + "Glint", Vector3(0.016, 0.021, 0.012) * scale,
			Vector3(x - 0.012 * scale, y + 0.020 * scale, z + 0.038 * scale), Color.WHITE)


func _eyebrow(name_: String, x: float, y: float, z: float, width: float,
		color: Color, angle: float = 0.0) -> void:
	var brow := _box(self, name_, Vector3(width, 0.045, 0.035), Vector3(x, y, z), color)
	brow.rotation.z = angle


func _mouth(name_: String, y: float, z: float, width: float, color: Color) -> void:
	_box(self, name_, Vector3(width, 0.045, 0.028), Vector3(0.0, y, z), color)


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
	var cloths: Array[Color] = [
		Color(0.42, 0.18, 0.10), Color(0.18, 0.34, 0.44),
		Color(0.36, 0.30, 0.12), Color(0.34, 0.17, 0.38),
	]
	var skins: Array[Color] = [
		Color(0.72, 0.48, 0.30), Color(0.58, 0.36, 0.22), Color(0.40, 0.24, 0.16),
	]
	var cloth: Color = cloths[_visual_rng.randi_range(0, cloths.size() - 1)]
	var skin: Color = skins[_visual_rng.randi_range(0, skins.size() - 1)]
	var hair := Color(0.16, 0.09, 0.05) if _visual_rng.randf() < 0.55 else Color(0.34, 0.22, 0.09)
	var iris := Color(0.12, 0.28, 0.18) if _visual_rng.randf() < 0.5 else Color(0.17, 0.25, 0.36)
	var leather := Color(0.18, 0.10, 0.06)

	_box(self, "Body", Vector3(0.62, 0.78, 0.34), Vector3(0.0, 1.05, 0.0), cloth)
	_box(self, "TunicCollar", Vector3(0.34, 0.11, 0.035), Vector3(0.0, 1.36, 0.19), cloth.lightened(0.20))
	_box(self, "Belt", Vector3(0.64, 0.10, 0.37), Vector3(0.0, 0.82, 0.0), leather)
	_box(self, "Buckle", Vector3(0.12, 0.09, 0.035), Vector3(0.0, 0.82, 0.205), Color(0.78, 0.61, 0.22))
	_box(self, "Head", Vector3(0.56, 0.56, 0.56), Vector3(0.0, 1.72, 0.0), skin)
	_box(self, "HairTop", Vector3(0.58, 0.13, 0.58), Vector3(0.0, 2.005, -0.01), hair)
	_box(self, "HairBack", Vector3(0.58, 0.38, 0.10), Vector3(0.0, 1.78, -0.285), hair)
	_box(self, "EarLeft", Vector3(0.10, 0.16, 0.12), Vector3(-0.325, 1.72, 0.0), skin.darkened(0.04))
	_box(self, "EarRight", Vector3(0.10, 0.16, 0.12), Vector3(0.325, 1.72, 0.0), skin.darkened(0.04))
	_eye("EyeLeft", -0.145, 1.79, 0.292, 1.0, iris)
	_eye("EyeRight", 0.145, 1.79, 0.292, 1.0, iris)
	_eyebrow("BrowLeft", -0.145, 1.895, 0.302, 0.17, hair, -0.08)
	_eyebrow("BrowRight", 0.145, 1.895, 0.302, 0.17, hair, 0.08)
	_box(self, "Nose", Vector3(0.16, 0.18, 0.20), Vector3(0.0, 1.66, 0.36), skin.darkened(0.08))
	_box(self, "NoseTip", Vector3(0.11, 0.08, 0.035), Vector3(0.0, 1.63, 0.475), skin.darkened(0.16))
	_mouth("Mouth", 1.535, 0.302, 0.20, Color(0.25, 0.07, 0.06))
	_box(self, "Arms", Vector3(0.72, 0.20, 0.22), Vector3(0.0, 1.02, 0.25), cloth.darkened(0.10))
	_box(self, "Hands", Vector3(0.24, 0.17, 0.24), Vector3(0.0, 1.00, 0.39), skin)
	_legs.append(_box(self, "LegLeft", Vector3(0.24, 0.66, 0.27), Vector3(-0.17, 0.34, 0.0), cloth.darkened(0.3)))
	_legs.append(_box(self, "LegRight", Vector3(0.24, 0.66, 0.27), Vector3(0.17, 0.34, 0.0), cloth.darkened(0.3)))
	_box(_legs[0], "ShoeLeft", Vector3(0.25, 0.16, 0.34), Vector3(0.0, -0.26, 0.045), leather)
	_box(_legs[1], "ShoeRight", Vector3(0.25, 0.16, 0.34), Vector3(0.0, -0.26, 0.045), leather)


func _build_dog() -> void:
	var furs: Array[Color] = [Color(0.56, 0.55, 0.51), Color(0.50, 0.34, 0.20), Color(0.74, 0.66, 0.48)]
	var fur: Color = furs[_visual_rng.randi_range(0, furs.size() - 1)]
	var dark := fur.darkened(0.38)
	_box(self, "Body", Vector3(0.45, 0.48, 0.88), Vector3(0.0, 0.55, 0.0), fur)
	_box(self, "BackPatch", Vector3(0.34, 0.035, 0.42), Vector3(-0.04, 0.807, -0.08), dark)
	_box(self, "Chest", Vector3(0.34, 0.36, 0.035), Vector3(0.0, 0.57, 0.456), fur.lightened(0.22))
	_box(self, "Head", Vector3(0.48, 0.50, 0.48), Vector3(0.0, 0.79, 0.58), fur.lightened(0.06))
	_box(self, "Muzzle", Vector3(0.30, 0.22, 0.25), Vector3(0.0, 0.70, 0.91), fur.lightened(0.18))
	_box(self, "EarLeft", Vector3(0.14, 0.28, 0.16), Vector3(-0.18, 1.04, 0.56), fur.darkened(0.25))
	_box(self, "EarRight", Vector3(0.14, 0.28, 0.16), Vector3(0.18, 1.04, 0.56), fur.darkened(0.25))
	_eye("EyeLeft", -0.125, 0.855, 0.828, 0.78, Color(0.09, 0.07, 0.04))
	_eye("EyeRight", 0.125, 0.855, 0.828, 0.78, Color(0.09, 0.07, 0.04))
	_eyebrow("BrowLeft", -0.125, 0.942, 0.833, 0.13, dark, -0.06)
	_eyebrow("BrowRight", 0.125, 0.942, 0.833, 0.13, dark, 0.06)
	_box(self, "Nose", Vector3(0.17, 0.12, 0.065), Vector3(0.0, 0.735, 1.07), Color(0.055, 0.045, 0.04))
	_mouth("Mouth", 0.625, 1.048, 0.19, Color(0.10, 0.045, 0.035))
	_box(self, "Tongue", Vector3(0.09, 0.08, 0.035), Vector3(0.0, 0.575, 1.048), Color(0.84, 0.30, 0.37))
	_box(self, "Collar", Vector3(0.47, 0.10, 0.19), Vector3(0.0, 0.72, 0.31), Color(0.65, 0.08, 0.07))
	_box(self, "Tag", Vector3(0.08, 0.10, 0.035), Vector3(0.0, 0.66, 0.42), Color(0.90, 0.72, 0.20))
	for x in [-0.15, 0.15]:
		for z in [-0.28, 0.28]:
			var leg := _box(self, "Leg", Vector3(0.15, 0.45, 0.16), Vector3(x, 0.23, z), fur.darkened(0.12))
			_legs.append(leg)
			_box(leg, "Paw", Vector3(0.17, 0.10, 0.22), Vector3(0.0, -0.19, 0.035), dark)
	_tail = _box(self, "Tail", Vector3(0.12, 0.12, 0.55), Vector3(0.0, 0.73, -0.58), fur)
	_tail.rotation.x = -0.55
	_box(_tail, "TailTip", Vector3(0.13, 0.13, 0.18), Vector3(0.0, 0.0, -0.19), fur.lightened(0.32))


func _build_pig() -> void:
	var pink := Color(0.92, 0.55, 0.61).lightened(_visual_rng.randf_range(0.0, 0.05))
	var dark_pink := pink.darkened(0.22)
	_box(self, "Body", Vector3(0.72, 0.62, 1.05), Vector3(0.0, 0.62, 0.0), pink)
	_box(self, "BackPatch", Vector3(0.50, 0.035, 0.42), Vector3(0.08, 0.948, -0.12), pink.darkened(0.09))
	_box(self, "SidePatch", Vector3(0.035, 0.28, 0.40), Vector3(-0.378, 0.64, -0.08), pink.lightened(0.10))
	_box(self, "Head", Vector3(0.62, 0.58, 0.54), Vector3(0.0, 0.72, 0.70), pink.lightened(0.04))
	_box(self, "Snout", Vector3(0.38, 0.24, 0.18), Vector3(0.0, 0.65, 1.05), Color(0.96, 0.66, 0.70))
	_box(self, "EarLeft", Vector3(0.16, 0.20, 0.12), Vector3(-0.22, 1.08, 0.72), pink.darkened(0.08))
	_box(self, "EarRight", Vector3(0.16, 0.20, 0.12), Vector3(0.22, 1.08, 0.72), pink.darkened(0.08))
	_eye("EyeLeft", -0.175, 0.84, 0.978, 0.80, Color(0.10, 0.07, 0.06))
	_eye("EyeRight", 0.175, 0.84, 0.978, 0.80, Color(0.10, 0.07, 0.06))
	_eyebrow("BrowLeft", -0.175, 0.932, 0.983, 0.14, dark_pink, -0.05)
	_eyebrow("BrowRight", 0.175, 0.932, 0.983, 0.14, dark_pink, 0.05)
	_box(self, "NostrilLeft", Vector3(0.055, 0.060, 0.025), Vector3(-0.09, 0.68, 1.152), dark_pink.darkened(0.25))
	_box(self, "NostrilRight", Vector3(0.055, 0.060, 0.025), Vector3(0.09, 0.68, 1.152), dark_pink.darkened(0.25))
	_mouth("Mouth", 0.555, 1.143, 0.20, Color(0.34, 0.08, 0.10))
	for x in [-0.24, 0.24]:
		for z in [-0.32, 0.32]:
			var leg := _box(self, "Leg", Vector3(0.18, 0.42, 0.18), Vector3(x, 0.22, z), pink.darkened(0.14))
			_legs.append(leg)
			_box(leg, "Hoof", Vector3(0.19, 0.11, 0.20), Vector3(0.0, -0.17, 0.015), Color(0.27, 0.14, 0.13))
	_tail = _box(self, "Tail", Vector3(0.10, 0.10, 0.34), Vector3(0.0, 0.75, -0.61), dark_pink)
	_tail.rotation.x = -0.38
	_box(_tail, "TailCurl", Vector3(0.18, 0.10, 0.10), Vector3(0.08, 0.0, -0.13), dark_pink)


func _build_cow() -> void:
	var hide := Color(0.30, 0.20, 0.14) if _visual_rng.randf() < 0.65 else Color(0.10, 0.09, 0.08)
	var white := Color(0.88, 0.84, 0.74)
	var hoof := Color(0.12, 0.09, 0.07)
	_box(self, "Body", Vector3(0.92, 0.86, 1.35), Vector3(0.0, 0.88, 0.0), hide)
	_box(self, "BackPatch", Vector3(0.52, 0.035, 0.58), Vector3(-0.12, 1.328, -0.18), white)
	_box(self, "SidePatchLeft", Vector3(0.035, 0.42, 0.54), Vector3(-0.478, 0.98, -0.10), white)
	_box(self, "SidePatchRight", Vector3(0.035, 0.32, 0.38), Vector3(0.478, 0.78, 0.22), white.darkened(0.05))
	_box(self, "Head", Vector3(0.72, 0.70, 0.62), Vector3(0.0, 1.02, 0.92), hide.darkened(0.06))
	_box(self, "Muzzle", Vector3(0.48, 0.28, 0.20), Vector3(0.0, 0.88, 1.32), Color(0.70, 0.48, 0.42))
	_box(self, "HornLeft", Vector3(0.12, 0.18, 0.12), Vector3(-0.30, 1.43, 0.93), white)
	_box(self, "HornRight", Vector3(0.12, 0.18, 0.12), Vector3(0.30, 1.43, 0.93), white)
	_box(self, "EarLeft", Vector3(0.22, 0.14, 0.16), Vector3(-0.45, 1.28, 0.91), hide.lightened(0.06))
	_box(self, "EarRight", Vector3(0.22, 0.14, 0.16), Vector3(0.45, 1.28, 0.91), hide.lightened(0.06))
	_eye("EyeLeft", -0.205, 1.13, 1.238, 0.90, Color(0.12, 0.09, 0.04))
	_eye("EyeRight", 0.205, 1.13, 1.238, 0.90, Color(0.12, 0.09, 0.04))
	_eyebrow("BrowLeft", -0.205, 1.235, 1.245, 0.16, hide.darkened(0.35), -0.07)
	_eyebrow("BrowRight", 0.205, 1.235, 1.245, 0.16, hide.darkened(0.35), 0.07)
	_box(self, "NostrilLeft", Vector3(0.065, 0.065, 0.026), Vector3(-0.125, 0.91, 1.432), hoof)
	_box(self, "NostrilRight", Vector3(0.065, 0.065, 0.026), Vector3(0.125, 0.91, 1.432), hoof)
	_mouth("Mouth", 0.785, 1.425, 0.25, Color(0.22, 0.07, 0.06))
	_box(self, "ForeheadMark", Vector3(0.25, 0.26, 0.035), Vector3(0.0, 1.30, 1.245), white)
	_box(self, "Udder", Vector3(0.48, 0.22, 0.46), Vector3(0.0, 0.40, 0.12), Color(0.78, 0.48, 0.48))
	for x in [-0.32, 0.32]:
		for z in [-0.42, 0.42]:
			var leg := _box(self, "Leg", Vector3(0.20, 0.64, 0.22), Vector3(x, 0.33, z), hide.darkened(0.12))
			_legs.append(leg)
			_box(leg, "Hoof", Vector3(0.22, 0.14, 0.25), Vector3(0.0, -0.255, 0.02), hoof)
	_tail = _box(self, "Tail", Vector3(0.12, 0.12, 0.68), Vector3(0.0, 1.05, -0.88), hide)
	_tail.rotation.x = -0.45
	_box(_tail, "TailTuft", Vector3(0.20, 0.20, 0.22), Vector3(0.0, 0.0, -0.27), hoof)


func _animate_walk(moving: bool, delta: float) -> void:
	var amount := 0.55 if moving else 0.0
	for i in _legs.size():
		var side := -1.0 if (i & 1) else 1.0
		var target_angle := sin(_walk_phase) * amount * side
		_legs[i].rotation.x = lerpf(_legs[i].rotation.x, target_angle, minf(1.0, delta * 10.0))
	if _tail != null:
		_tail.rotation.y = sin(Time.get_ticks_msec() * 0.008) * 0.45
