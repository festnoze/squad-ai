class_name SettlementManager
extends Node3D
## Streams villagers and dogs from the same deterministic house anchors used by
## terrain generation. Actors are scene nodes, so they are created and removed
## only here on the main thread.

const SCAN_INTERVAL := 1.0
const ACTIVE_RADIUS := 150.0
const DESPAWN_RADIUS := 190.0

var _world: VoxelWorld
var _player: Player
var _actors: Dictionary = {} # "house:actor" -> SettlementMob
var _scan_time := 0.0


func setup(world: VoxelWorld, player: Player) -> void:
	_world = world
	_player = player
	world.chunk_ready.connect(_on_chunk_ready)


func _process(delta: float) -> void:
	if _world == null or _player == null:
		return
	_scan_time -= delta
	if _scan_time <= 0.0:
		_scan_time = SCAN_INTERVAL
		_scan_near_player()
		_despawn_far_actors()


func _on_chunk_ready(cx: int, cz: int) -> void:
	_spawn_chunk(cx, cz)


func _scan_near_player() -> void:
	var pcx := VoxelWorld.chunk_of(floori(_player.global_position.x))
	var pcz := VoxelWorld.chunk_of(floori(_player.global_position.z))
	var chunks := ceili(ACTIVE_RADIUS / float(ChunkData.SIZE_X))
	for dx in range(-chunks, chunks + 1):
		for dz in range(-chunks, chunks + 1):
			var cx := pcx + dx
			var cz := pcz + dz
			if _world.has_chunk_at(cx * ChunkData.SIZE_X, cz * ChunkData.SIZE_Z):
				_spawn_chunk(cx, cz)


func _spawn_chunk(cx: int, cz: int) -> void:
	for house in _world.houses_in_chunk(cx, cz):
		var centre := Vector3(house.x + 0.5, house.y + 1.0, house.z + 0.5)
		if centre.distance_to(_player.global_position) > ACTIVE_RADIUS:
			continue
		for index in 3:
			var key := "%d:%d:%d" % [house.x, house.z, index]
			if _actors.has(key) and is_instance_valid(_actors[key]):
				continue
			var kind := SettlementMob.Kind.DOG if index == 2 else SettlementMob.Kind.VILLAGER
			var rotation := house.w & 3
			var offset := _front_offset(rotation, 4.5 + float(index) * 0.9)
			if index == 1:
				offset += _side_offset(rotation, 1.2)
			var spawn := centre + offset
			spawn.y = float(_world.surface_height(floori(spawn.x), floori(spawn.z)) + 1)
			var actor := SettlementMob.new()
			actor.name = "Dog" if kind == SettlementMob.Kind.DOG else "Villager"
			add_child(actor)
			var actor_seed := house.x * 73856093 ^ house.z * 19349663 ^ index * 83492791
			actor.setup(_world, kind, spawn, actor_seed)
			_actors[key] = actor
	for pen in _world.pens_in_chunk(cx, cz):
		_spawn_pen(pen)


func _spawn_pen(pen: Vector4i) -> void:
	var centre := Vector3(pen.x + 0.5, pen.y, pen.z + 0.5)
	if centre.distance_to(_player.global_position) > ACTIVE_RADIUS:
		return
	for index in 4:
		var key := "pen:%d:%d:%d" % [pen.x, pen.z, index]
		if _actors.has(key) and is_instance_valid(_actors[key]):
			continue
		var kind := SettlementMob.Kind.PIG if index < 2 else SettlementMob.Kind.COW
		var local_x := -1.4 if (index & 1) == 0 else 1.4
		var local_z := -1.2 if index < 2 else 1.2
		var offset := _side_offset(pen.w, local_x) + _front_offset(pen.w, local_z)
		var spawn := centre + offset
		spawn.y = float(_world.surface_height(floori(spawn.x), floori(spawn.z)) + 1)
		var actor := SettlementMob.new()
		actor.name = "Pig" if kind == SettlementMob.Kind.PIG else "Cow"
		add_child(actor)
		var actor_seed := pen.x * 92837111 ^ pen.z * 689287499 ^ index * 283923481
		actor.setup(_world, kind, spawn, actor_seed)
		_actors[key] = actor


func _front_offset(rotation_quarters: int, distance: float) -> Vector3:
	return Vector3(0.0, 0.0, distance).rotated(Vector3.UP, -float(rotation_quarters) * PI * 0.5)


func _side_offset(rotation_quarters: int, distance: float) -> Vector3:
	return Vector3(distance, 0.0, 0.0).rotated(Vector3.UP, -float(rotation_quarters) * PI * 0.5)


func _despawn_far_actors() -> void:
	var stale: Array[String] = []
	for key: String in _actors:
		var actor: SettlementMob = _actors[key]
		if not is_instance_valid(actor) or actor.global_position.distance_to(_player.global_position) > DESPAWN_RADIUS:
			if is_instance_valid(actor):
				actor.queue_free()
			stale.append(key)
	for key in stale:
		_actors.erase(key)
