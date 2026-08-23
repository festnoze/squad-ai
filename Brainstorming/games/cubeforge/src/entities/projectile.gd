class_name Projectile
extends Node3D
## Arrow projectile, shared by the player bow and the skeleton archers.
##
## No physics body: each step sweeps a segment through the voxel grid with the
## same Amanatides and Woo traversal the interaction module uses, then tests
## the segment against actor boxes. Player arrows hurt monsters, monster
## arrows hurt the player, and nothing hurts its own side.

const GRAVITY := 18.0
const LIFETIME := 8.0
const STUCK_LIFETIME := 2.5

var _world: VoxelWorld
var _player: Player
var _velocity := Vector3.ZERO
var _from_player := false
var _damage := 6
var _life := 0.0
var _stuck := false
var _stuck_left := STUCK_LIFETIME


func setup(world: VoxelWorld, player: Player, start: Vector3, velocity: Vector3,
		from_player: bool, damage: int) -> void:
	_world = world
	_player = player
	_velocity = velocity
	_from_player = from_player
	_damage = damage
	global_position = start
	_build_visual()
	_orient()


func _physics_process(delta: float) -> void:
	if _world == null:
		queue_free()
		return
	_life += delta
	if _life > LIFETIME:
		queue_free()
		return
	if _stuck:
		_stuck_left -= delta
		if _stuck_left <= 0.0:
			queue_free()
		return

	_velocity.y -= GRAVITY * delta
	var start := global_position
	var motion := _velocity * delta
	var seg := motion.length()
	if seg <= 1e-6:
		return
	var dir := motion / seg

	# Actors first: an arrow crossing a mob inside the same block as a wall
	# should still connect with the mob it reaches first.
	var block_hit := Interaction.raycast(_world, start, dir, seg)
	var block_t: float = block_hit["distance"] if bool(block_hit["hit"]) else INF

	var actor_t := INF
	var actor: Node3D = null
	if _from_player:
		for mob in get_tree().get_nodes_in_group("monsters"):
			var monster := mob as MonsterMob
			if monster == null or not monster.alive():
				continue
			var t := _ray_aabb(start, dir, seg, monster.aabb())
			if t >= 0.0 and t < actor_t:
				actor_t = t
				actor = monster
	elif _player != null and not _player.frozen:
		var r: float = _player.body.radius if _player.body != null else 0.3
		var h: float = _player.body.height if _player.body != null else 1.8
		var box := AABB(_player.global_position - Vector3(r, 0.0, r), Vector3(r * 2.0, h, r * 2.0))
		var t := _ray_aabb(start, dir, seg, box)
		if t >= 0.0:
			actor_t = t
			actor = _player

	if actor != null and actor_t <= block_t:
		if actor is MonsterMob:
			(actor as MonsterMob).take_damage(_damage, start)
		elif actor is Player:
			(actor as Player).take_damage(_damage, start)
		queue_free()
		return

	if block_t < INF:
		global_position = start + dir * maxf(block_t - 0.05, 0.0)
		_stuck = true
		var sfx := get_node_or_null(^"/root/Sfx")
		if sfx != null and sfx.has_method("play_at"):
			sfx.call("play_at", "click", global_position, -4.0, 0.8)
		return

	global_position = start + motion
	_orient()


## Slab test of a ray against an AABB. Returns the entry parameter along the
## segment (0..max_d) or -1.0 when there is no hit.
static func _ray_aabb(origin: Vector3, dir: Vector3, max_d: float, box: AABB) -> float:
	var t_min := 0.0
	var t_max := max_d
	for axis in 3:
		var d: float = dir[axis]
		var o: float = origin[axis]
		var lo: float = box.position[axis]
		var hi: float = box.position[axis] + box.size[axis]
		if absf(d) < 1e-8:
			if o < lo or o > hi:
				return -1.0
			continue
		var inv := 1.0 / d
		var t0 := (lo - o) * inv
		var t1 := (hi - o) * inv
		if t0 > t1:
			var tmp := t0
			t0 = t1
			t1 = tmp
		t_min = maxf(t_min, t0)
		t_max = minf(t_max, t1)
		if t_min > t_max:
			return -1.0
	return t_min


func _orient() -> void:
	if _velocity.length_squared() > 1e-6:
		look_at(global_position + _velocity.normalized(), Vector3.UP)


func _build_visual() -> void:
	var shaft := MeshInstance3D.new()
	shaft.name = "Shaft"
	var shaft_mesh := BoxMesh.new()
	shaft_mesh.size = Vector3(0.045, 0.045, 0.52)
	shaft.mesh = shaft_mesh
	var wood := StandardMaterial3D.new()
	wood.albedo_color = Color(0.45, 0.30, 0.15)
	wood.roughness = 0.9
	shaft.material_override = wood
	add_child(shaft)

	var head := MeshInstance3D.new()
	head.name = "Head"
	var head_mesh := BoxMesh.new()
	head_mesh.size = Vector3(0.07, 0.07, 0.10)
	head.mesh = head_mesh
	head.position = Vector3(0.0, 0.0, -0.30)
	var steel := StandardMaterial3D.new()
	steel.albedo_color = Color(0.75, 0.77, 0.82)
	steel.roughness = 0.5
	head.material_override = steel
	add_child(head)

	var fletch := MeshInstance3D.new()
	fletch.name = "Fletching"
	var fletch_mesh := BoxMesh.new()
	fletch_mesh.size = Vector3(0.14, 0.14, 0.08)
	fletch.mesh = fletch_mesh
	fletch.position = Vector3(0.0, 0.0, 0.24)
	var feather := StandardMaterial3D.new()
	feather.albedo_color = Color(0.90, 0.90, 0.86)
	feather.roughness = 1.0
	fletch.material_override = feather
	add_child(fletch)
