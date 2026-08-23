class_name MonsterMob
extends Node3D
## Hostile night creature. Same voxel-surface locomotion as SettlementMob (no
## physics body, terrain queries only), plus health, chase and attack routines.
##
## Four kinds:
##   ZOMBIE    slow melee chaser
##   SKELETON  keeps its distance and shoots arrows
##   SPIDER    fast, climbs two-block steps, weak bite
##   CREEPER   closes in, hisses, then explodes and carves the terrain

signal loot_dropped(item_id: int, count: int)

enum Kind { ZOMBIE, SKELETON, SPIDER, CREEPER }

const TURN_SPEED := 8.0
const ARRIVAL_DISTANCE := 0.35
const DETECT_RANGE := 18.0
const MELEE_RANGE := 1.8
const MELEE_INTERVAL := 1.2

const SKELETON_NEAR := 6.0
const SKELETON_FAR := 12.0
const SKELETON_SHOOT_RANGE := 15.0
const SKELETON_SHOOT_INTERVAL := 2.2
const SKELETON_ARROW_SPEED := 19.0

const CREEPER_FUSE_RANGE := 2.8
const CREEPER_FUSE_TIME := 1.4
const CREEPER_BLAST_RADIUS := 2.6
const CREEPER_HURT_RADIUS := 5.0
const CREEPER_MAX_DAMAGE := 14

var kind: Kind = Kind.ZOMBIE
var home := Vector3.ZERO

var _world: VoxelWorld
var _player: Player
var _manager: Node
var _rng := RandomNumberGenerator.new()
var _hp: int = 20
var _dying := false
var _target := Vector3.ZERO
var _decision_time := 0.0
var _walk_phase := 0.0
var _legs: Array[Node3D] = []
var _material_cache: Dictionary = {}
var _attack_timer := 0.0
var _shoot_timer := 1.0
var _fuse := -1.0
var _flash := 0.0
var _knockback := Vector3.ZERO
var _sfx: Node = null


func setup(world: VoxelWorld, player: Player, manager: Node, mob_kind: Kind,
		spawn: Vector3, actor_seed: int) -> void:
	_world = world
	_player = player
	_manager = manager
	kind = mob_kind
	home = spawn
	global_position = spawn
	_rng.seed = actor_seed
	_hp = _max_hp()
	add_to_group("monsters")
	_build_model()
	_choose_wander()


func alive() -> bool:
	return not _dying and _hp > 0


## World-space hit box, used by melee swings and arrows.
func aabb() -> AABB:
	match kind:
		Kind.SPIDER:
			return AABB(global_position + Vector3(-0.75, 0.0, -0.75), Vector3(1.5, 0.95, 1.5))
		Kind.CREEPER:
			return AABB(global_position + Vector3(-0.35, 0.0, -0.35), Vector3(0.7, 1.8, 0.7))
		_:
			return AABB(global_position + Vector3(-0.4, 0.0, -0.4), Vector3(0.8, 1.95, 0.8))


func take_damage(amount: int, from: Vector3) -> void:
	if _dying:
		return
	_hp -= amount
	_flash = 0.22
	_apply_flash(Color(1.0, 0.15, 0.1), 0.9)
	var away := global_position - from
	away.y = 0.0
	if away.length_squared() > 1e-6:
		_knockback = away.normalized() * 6.0
	_play_at("land", global_position, -6.0, 1.5)
	if _hp <= 0:
		_die(true)


## Dawn or creative mode removal: same poof as a death, but no loot.
func banish() -> void:
	if _dying:
		return
	_die(false)


func _physics_process(delta: float) -> void:
	if _dying or _world == null or _player == null:
		return

	if _attack_timer > 0.0:
		_attack_timer -= delta
	if _shoot_timer > 0.0:
		_shoot_timer -= delta
	if _flash > 0.0:
		_flash -= delta
		if _flash <= 0.0 and _fuse < 0.0:
			_apply_flash(Color.BLACK, 0.0)

	_apply_knockback(delta)

	var to_player := _player.global_position - global_position
	var flat_dist := Vector2(to_player.x, to_player.z).length()
	var chasing := flat_dist <= DETECT_RANGE and not _player.frozen

	if kind == Kind.CREEPER:
		_creeper_brain(chasing, flat_dist, delta)
	elif kind == Kind.SKELETON:
		_skeleton_brain(chasing, flat_dist)
	else:
		_melee_brain(chasing, flat_dist)

	_move(delta)


# ---------------------------------------------------------------------------
# Brains
# ---------------------------------------------------------------------------

func _melee_brain(chasing: bool, flat_dist: float) -> void:
	if not chasing:
		_wander_tick()
		return
	_target = _player.global_position
	if flat_dist <= MELEE_RANGE and _attack_timer <= 0.0:
		_attack_timer = MELEE_INTERVAL
		_player.take_damage(_melee_damage(), global_position)
		_play_at("dig_wool", global_position, -2.0, 0.8)


func _skeleton_brain(chasing: bool, flat_dist: float) -> void:
	if not chasing:
		_wander_tick()
		return
	if flat_dist < SKELETON_NEAR:
		# Back away while keeping the player in sight.
		var away := (global_position - _player.global_position)
		away.y = 0.0
		if away.length_squared() > 1e-6:
			_target = global_position + away.normalized() * 5.0
	elif flat_dist > SKELETON_FAR:
		_target = _player.global_position
	else:
		_target = global_position
	if flat_dist <= SKELETON_SHOOT_RANGE and _shoot_timer <= 0.0 and _manager != null \
			and _manager.has_method("spawn_arrow"):
		_shoot_timer = SKELETON_SHOOT_INTERVAL
		var origin := global_position + Vector3(0.0, 1.45, 0.0)
		var aim := (_player.eye_position() - origin)
		# A pinch of upward arc plus deterministic spread keeps shots dodgeable.
		aim += Vector3(0.0, aim.length() * 0.05, 0.0)
		aim = aim.normalized()
		aim += Vector3(_rng.randf_range(-0.04, 0.04), _rng.randf_range(-0.02, 0.03),
				_rng.randf_range(-0.04, 0.04))
		_manager.call("spawn_arrow", origin, aim.normalized() * SKELETON_ARROW_SPEED, false)
		_play_at("pop", origin, -4.0, 0.7)


func _creeper_brain(chasing: bool, flat_dist: float, delta: float) -> void:
	if _fuse >= 0.0:
		# Committed: stand still, blink faster and faster, then blow up.
		_target = global_position
		_fuse -= delta
		var pulse := 0.5 + 0.5 * sin(_fuse * 24.0)
		_apply_flash(Color(1.0, 1.0, 0.85), pulse * 1.4)
		if flat_dist > CREEPER_FUSE_RANGE + 2.5:
			# The player escaped, stand down.
			_fuse = -1.0
			_apply_flash(Color.BLACK, 0.0)
		elif _fuse <= 0.0:
			_explode()
		return
	if not chasing:
		_wander_tick()
		return
	_target = _player.global_position
	if flat_dist <= CREEPER_FUSE_RANGE:
		_fuse = CREEPER_FUSE_TIME
		_play_at("dig_sand", global_position, 2.0, 0.6)


func _explode() -> void:
	var centre := global_position + Vector3(0.0, 0.9, 0.0)
	var r := CREEPER_BLAST_RADIUS
	var reach := int(ceil(r))
	var cx := floori(centre.x)
	var cy := floori(centre.y)
	var cz := floori(centre.z)
	for dy in range(-reach, reach + 1):
		for dx in range(-reach, reach + 1):
			for dz in range(-reach, reach + 1):
				if Vector3(dx, dy, dz).length() > r:
					continue
				var wx := cx + dx
				var wy := cy + dy
				var wz := cz + dz
				var id := _world.get_block(wx, wy, wz)
				if Blocks.is_breakable(id):
					_world.set_block(wx, wy, wz, Blocks.AIR)
	var d := centre.distance_to(_player.global_position + Vector3(0.0, 0.9, 0.0))
	if d < CREEPER_HURT_RADIUS:
		var damage := int(round(float(CREEPER_MAX_DAMAGE) * (1.0 - d / CREEPER_HURT_RADIUS)))
		_player.take_damage(maxi(damage, 1), centre)
	_play_at("break_stone", centre, 8.0, 0.5)
	_dying = true
	queue_free()


# ---------------------------------------------------------------------------
# Locomotion (shared with the settlement actors by design, not by inheritance)
# ---------------------------------------------------------------------------

func _wander_tick() -> void:
	_decision_time -= get_physics_process_delta_time()
	var flat := Vector2(_target.x - global_position.x, _target.z - global_position.z)
	if _decision_time <= 0.0 or flat.length() <= ARRIVAL_DISTANCE:
		_choose_wander()


func _choose_wander() -> void:
	if _rng.randf() < 0.3:
		_target = global_position
		_decision_time = _rng.randf_range(1.0, 3.0)
		return
	for attempt in 10:
		var angle := _rng.randf_range(0.0, TAU)
		var distance := _rng.randf_range(3.0, 10.0)
		var candidate := global_position + Vector3(cos(angle) * distance, 0.0, sin(angle) * distance)
		var y := _walkable_height(candidate)
		if y > -1000.0:
			_target = Vector3(candidate.x, y, candidate.z)
			_decision_time = _rng.randf_range(2.0, 5.0)
			return
	_target = global_position
	_decision_time = 2.0


func _move(delta: float) -> void:
	var flat := Vector2(_target.x - global_position.x, _target.z - global_position.z)
	var moving := flat.length() > ARRIVAL_DISTANCE
	if moving and _fuse < 0.0:
		var direction := flat.normalized()
		var speed := _move_speed()
		var next := global_position + Vector3(direction.x, 0.0, direction.y) * speed * delta
		var next_y := _walkable_height(next)
		if next_y > -1000.0 and absf(next_y - global_position.y) <= float(_max_step()) + 0.05:
			global_position = Vector3(next.x, next_y, next.z)
			var desired_yaw := atan2(direction.x, direction.y)
			rotation.y = lerp_angle(rotation.y, desired_yaw, minf(1.0, TURN_SPEED * delta))
			_walk_phase += delta * speed * 5.0
		else:
			_choose_wander()
			moving = false
	# Face the player while holding position (skeleton aiming, creeper fusing).
	if not moving and _player != null:
		var look := _player.global_position - global_position
		if Vector2(look.x, look.z).length() > 0.5:
			var yaw := atan2(look.x, look.z)
			rotation.y = lerp_angle(rotation.y, yaw, minf(1.0, TURN_SPEED * delta))
	_animate_walk(moving, delta)


func _apply_knockback(delta: float) -> void:
	if _knockback.length_squared() < 0.01:
		_knockback = Vector3.ZERO
		return
	var next := global_position + _knockback * delta
	var next_y := _walkable_height(next)
	if next_y > -1000.0 and absf(next_y - global_position.y) <= 1.1:
		global_position = Vector3(next.x, next_y, next.z)
	_knockback = _knockback.lerp(Vector3.ZERO, minf(1.0, 6.0 * delta))


func _walkable_height(point: Vector3) -> float:
	var wx := floori(point.x)
	var wz := floori(point.z)
	if not _world.has_chunk_at(wx, wz):
		return -10000.0
	var h := _world.surface_height(wx, wz)
	if h < ChunkData.SEA_LEVEL:
		return -10000.0
	if Blocks.is_liquid(_world.get_block(wx, h + 1, wz)):
		return -10000.0
	var feet_y := h + 1
	while feet_y < ChunkData.SIZE_Y - 2 and Blocks.collides(_world.get_block(wx, feet_y, wz)):
		feet_y += 1
	if Blocks.collides(_world.get_block(wx, feet_y + 1, wz)):
		return -10000.0
	return float(feet_y)


func _animate_walk(moving: bool, delta: float) -> void:
	var amount := 0.55 if moving else 0.0
	for i in _legs.size():
		var side := -1.0 if (i & 1) else 1.0
		var target_angle := sin(_walk_phase) * amount * side
		_legs[i].rotation.x = lerpf(_legs[i].rotation.x, target_angle, minf(1.0, delta * 10.0))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

func _max_hp() -> int:
	match kind:
		Kind.SKELETON:
			return 16
		Kind.SPIDER:
			return 14
		Kind.CREEPER:
			return 18
		_:
			return 20


func _move_speed() -> float:
	match kind:
		Kind.SKELETON:
			return 1.9
		Kind.SPIDER:
			return 2.7
		Kind.CREEPER:
			return 2.0
		_:
			return 1.7


func _max_step() -> int:
	return 2 if kind == Kind.SPIDER else 1


func _melee_damage() -> int:
	return 3 if kind == Kind.SPIDER else 4


func _die(with_loot: bool) -> void:
	_dying = true
	if with_loot:
		match kind:
			Kind.ZOMBIE:
				if _rng.randf() < 0.30:
					loot_dropped.emit(Items.COAL, 1)
			Kind.SKELETON:
				loot_dropped.emit(Items.ARROW, 2)
				if _rng.randf() < 0.15:
					loot_dropped.emit(Items.BOW, 1)
			Kind.SPIDER:
				if _rng.randf() < 0.25:
					loot_dropped.emit(Items.STICK, 2)
			Kind.CREEPER:
				loot_dropped.emit(Items.COAL, 1 + _rng.randi_range(0, 1))
		_play_at("break_plant", global_position, 0.0, 0.7)
	var tween := create_tween()
	tween.tween_property(self, "scale", Vector3(0.05, 0.05, 0.05), 0.22)
	tween.tween_callback(queue_free)


# ---------------------------------------------------------------------------
# Sound helper
# ---------------------------------------------------------------------------

func _play_at(sound: String, position: Vector3, volume_db: float, pitch: float) -> void:
	if _sfx == null or not is_instance_valid(_sfx):
		_sfx = get_node_or_null(^"/root/Sfx")
	if _sfx != null and _sfx.has_method("play_at"):
		_sfx.call("play_at", sound, position, volume_db, pitch)


# ---------------------------------------------------------------------------
# Procedural models
# ---------------------------------------------------------------------------

func _build_model() -> void:
	match kind:
		Kind.SKELETON:
			_build_skeleton()
		Kind.SPIDER:
			_build_spider()
		Kind.CREEPER:
			_build_creeper()
		_:
			_build_zombie()


func _box(parent: Node3D, name_: String, size: Vector3, pos: Vector3, color: Color,
		emissive: float = 0.0) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = name_
	pivot.position = pos
	parent.add_child(pivot)
	var mesh_node := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh_node.mesh = mesh
	mesh_node.material_override = _material(color, emissive)
	mesh_node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	pivot.add_child(mesh_node)
	return pivot


func _material(color: Color, emissive: float = 0.0) -> StandardMaterial3D:
	var key := color.to_rgba32() * 2 + (1 if emissive > 0.0 else 0)
	if _material_cache.has(key):
		return _material_cache[key]
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.92
	material.metallic_specular = 0.05
	if emissive > 0.0:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = emissive
	_material_cache[key] = material
	return material


## Hit flash and creeper fuse pulse: overrides emission on every cached body
## material at once, which reads clearly even in the dark of night.
func _apply_flash(color: Color, energy: float) -> void:
	for key: int in _material_cache:
		var material: StandardMaterial3D = _material_cache[key]
		if energy <= 0.0:
			# Emissive parts (eyes) keep their own glow.
			if (key & 1) == 0:
				material.emission_enabled = false
			continue
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = energy


func _build_zombie() -> void:
	var skin := Color(0.36, 0.55, 0.30)
	var cloth := Color(0.16, 0.22, 0.30)
	var pants := Color(0.22, 0.18, 0.32)
	_box(self, "Body", Vector3(0.62, 0.78, 0.34), Vector3(0.0, 1.05, 0.0), cloth)
	_box(self, "Head", Vector3(0.56, 0.56, 0.56), Vector3(0.0, 1.72, 0.0), skin)
	_box(self, "EyeLeft", Vector3(0.12, 0.09, 0.03), Vector3(-0.14, 1.79, 0.29), Color(0.10, 0.08, 0.06))
	_box(self, "EyeRight", Vector3(0.12, 0.09, 0.03), Vector3(0.14, 1.79, 0.29), Color(0.10, 0.08, 0.06))
	_box(self, "Mouth", Vector3(0.22, 0.05, 0.03), Vector3(0.0, 1.55, 0.29), Color(0.12, 0.16, 0.10))
	# Both arms stretched forward: the classic silhouette.
	_box(self, "ArmLeft", Vector3(0.18, 0.18, 0.68), Vector3(-0.22, 1.30, 0.42), skin.darkened(0.08))
	_box(self, "ArmRight", Vector3(0.18, 0.18, 0.68), Vector3(0.22, 1.30, 0.42), skin.darkened(0.08))
	_legs.append(_box(self, "LegLeft", Vector3(0.24, 0.66, 0.27), Vector3(-0.17, 0.34, 0.0), pants))
	_legs.append(_box(self, "LegRight", Vector3(0.24, 0.66, 0.27), Vector3(0.17, 0.34, 0.0), pants))


func _build_skeleton() -> void:
	var bone := Color(0.86, 0.86, 0.80)
	var dark := Color(0.30, 0.30, 0.28)
	_box(self, "Body", Vector3(0.44, 0.72, 0.24), Vector3(0.0, 1.06, 0.0), bone)
	_box(self, "Ribs", Vector3(0.46, 0.08, 0.26), Vector3(0.0, 1.16, 0.0), dark)
	_box(self, "Ribs2", Vector3(0.46, 0.08, 0.26), Vector3(0.0, 0.98, 0.0), dark)
	_box(self, "Head", Vector3(0.52, 0.52, 0.52), Vector3(0.0, 1.70, 0.0), bone.lightened(0.05))
	_box(self, "EyeLeft", Vector3(0.12, 0.12, 0.03), Vector3(-0.13, 1.76, 0.27), Color(0.05, 0.05, 0.05))
	_box(self, "EyeRight", Vector3(0.12, 0.12, 0.03), Vector3(0.13, 1.76, 0.27), Color(0.05, 0.05, 0.05))
	_box(self, "ArmLeft", Vector3(0.14, 0.60, 0.14), Vector3(-0.30, 1.10, 0.0), bone.darkened(0.06))
	_box(self, "ArmRight", Vector3(0.14, 0.14, 0.55), Vector3(0.30, 1.32, 0.28), bone.darkened(0.06))
	# Held bow: a flat brown arc stub in the raised hand.
	_box(self, "Bow", Vector3(0.06, 0.55, 0.10), Vector3(0.30, 1.32, 0.56), Color(0.45, 0.30, 0.15))
	_legs.append(_box(self, "LegLeft", Vector3(0.16, 0.66, 0.16), Vector3(-0.13, 0.34, 0.0), bone.darkened(0.10)))
	_legs.append(_box(self, "LegRight", Vector3(0.16, 0.66, 0.16), Vector3(0.13, 0.66 * 0.5, 0.0), bone.darkened(0.10)))


func _build_spider() -> void:
	var body := Color(0.12, 0.10, 0.12)
	var fuzz := Color(0.20, 0.16, 0.18)
	_box(self, "Abdomen", Vector3(1.05, 0.55, 1.10), Vector3(0.0, 0.55, -0.35), body)
	_box(self, "Back", Vector3(0.70, 0.06, 0.75), Vector3(0.0, 0.85, -0.35), fuzz)
	_box(self, "Head", Vector3(0.62, 0.48, 0.55), Vector3(0.0, 0.50, 0.45), fuzz)
	_box(self, "EyeLeft", Vector3(0.10, 0.10, 0.03), Vector3(-0.15, 0.58, 0.73), Color(0.85, 0.12, 0.10), 1.4)
	_box(self, "EyeRight", Vector3(0.10, 0.10, 0.03), Vector3(0.15, 0.58, 0.73), Color(0.85, 0.12, 0.10), 1.4)
	_box(self, "EyeLeft2", Vector3(0.06, 0.06, 0.03), Vector3(-0.26, 0.52, 0.73), Color(0.85, 0.12, 0.10), 1.4)
	_box(self, "EyeRight2", Vector3(0.06, 0.06, 0.03), Vector3(0.26, 0.52, 0.73), Color(0.85, 0.12, 0.10), 1.4)
	for i in 4:
		var z := 0.35 - float(i) * 0.28
		var left := _box(self, "LegL%d" % i, Vector3(0.9, 0.08, 0.10), Vector3(-0.62, 0.55, z), body)
		left.rotation.z = 0.5
		_legs.append(left)
		var right := _box(self, "LegR%d" % i, Vector3(0.9, 0.08, 0.10), Vector3(0.62, 0.55, z), body)
		right.rotation.z = -0.5
		_legs.append(right)


func _build_creeper() -> void:
	var green := Color(0.30, 0.62, 0.28)
	var dark := Color(0.16, 0.36, 0.15)
	_box(self, "Body", Vector3(0.50, 1.10, 0.34), Vector3(0.0, 0.95, 0.0), green)
	_box(self, "Patch", Vector3(0.52, 0.30, 0.10), Vector3(0.0, 1.10, 0.14), dark)
	_box(self, "Head", Vector3(0.55, 0.55, 0.55), Vector3(0.0, 1.78, 0.0), green.lightened(0.05))
	_box(self, "EyeLeft", Vector3(0.14, 0.14, 0.03), Vector3(-0.13, 1.86, 0.28), Color(0.05, 0.05, 0.05))
	_box(self, "EyeRight", Vector3(0.14, 0.14, 0.03), Vector3(0.13, 1.86, 0.28), Color(0.05, 0.05, 0.05))
	_box(self, "MouthTop", Vector3(0.14, 0.16, 0.03), Vector3(0.0, 1.68, 0.28), Color(0.05, 0.05, 0.05))
	_box(self, "MouthLeft", Vector3(0.08, 0.20, 0.03), Vector3(-0.10, 1.60, 0.28), Color(0.05, 0.05, 0.05))
	_box(self, "MouthRight", Vector3(0.08, 0.20, 0.03), Vector3(0.10, 1.60, 0.28), Color(0.05, 0.05, 0.05))
	for x in [-0.15, 0.15]:
		for z in [-0.17, 0.17]:
			_legs.append(_box(self, "Leg", Vector3(0.22, 0.40, 0.24), Vector3(x, 0.20, z), dark))
