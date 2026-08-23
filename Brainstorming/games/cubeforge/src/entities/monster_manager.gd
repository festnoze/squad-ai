class_name MonsterManager
extends Node3D
## Night-time hostile spawning, survival mode only.
##
## Monsters exist only while it is night AND creative mode is off: the very
## first tick of dawn (or a switch to creative) banishes the whole population.
## Spawns land on the surface, outside the ocean, in a ring around the player
## that is far enough to stay unseen but close enough to matter.
##
## This node also owns every arrow in flight, and is the combat lookup used by
## the interaction module (ray_pick) so melee swings can find a target.

signal loot_dropped(item_id: int, count: int)

const MAX_MONSTERS := 12
const SPAWN_INTERVAL := 1.5
const SPAWN_ATTEMPTS := 2
const SPAWN_MIN := 24.0
const SPAWN_MAX := 44.0
const DESPAWN_RADIUS := 80.0

## Player arrow damage; skeleton arrows use their own value.
const PLAYER_ARROW_DAMAGE := 7
const SKELETON_ARROW_DAMAGE := 4

var _world: VoxelWorld
var _player: Player
var _sky: SkyController
var _rng := RandomNumberGenerator.new()
var _timer := 0.0
var _game: Node = null


func setup(world: VoxelWorld, player: Player, sky: SkyController) -> void:
	_world = world
	_player = player
	_sky = sky
	_rng.randomize()


func _physics_process(delta: float) -> void:
	if _world == null or _player == null or _sky == null:
		return
	_timer -= delta
	if _timer > 0.0:
		return
	_timer = SPAWN_INTERVAL

	if _creative() or not _sky.is_night():
		_banish_all()
		return

	_despawn_far()
	if _player.frozen:
		return
	var alive := _monster_count()
	for attempt in SPAWN_ATTEMPTS:
		if alive >= MAX_MONSTERS:
			break
		if _try_spawn():
			alive += 1


func monster_count() -> int:
	return _monster_count()


## Nearest living monster crossed by the ray, or null. Used by melee attacks.
func ray_pick(origin: Vector3, direction: Vector3, max_distance: float) -> MonsterMob:
	if direction.length_squared() < 1e-9:
		return null
	var dir := direction.normalized()
	var best: MonsterMob = null
	var best_t := INF
	for node in get_tree().get_nodes_in_group("monsters"):
		var mob := node as MonsterMob
		if mob == null or not mob.alive():
			continue
		var t := Projectile._ray_aabb(origin, dir, max_distance, mob.aabb())
		if t >= 0.0 and t < best_t:
			best_t = t
			best = mob
	return best


## Spawns one arrow. Player arrows hurt monsters, other arrows hurt the player.
func spawn_arrow(start: Vector3, velocity: Vector3, from_player: bool) -> void:
	var arrow := Projectile.new()
	arrow.name = "Arrow"
	add_child(arrow)
	var damage := PLAYER_ARROW_DAMAGE if from_player else SKELETON_ARROW_DAMAGE
	arrow.setup(_world, _player, start, velocity, from_player, damage)


# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------

func _try_spawn() -> bool:
	var angle := _rng.randf_range(0.0, TAU)
	var distance := _rng.randf_range(SPAWN_MIN, SPAWN_MAX)
	var wx := floori(_player.global_position.x + cos(angle) * distance)
	var wz := floori(_player.global_position.z + sin(angle) * distance)
	if not _world.has_chunk_at(wx, wz):
		return false
	var h := _world.surface_height(wx, wz)
	if h < ChunkData.SEA_LEVEL or h >= ChunkData.SIZE_Y - 4:
		return false
	if Blocks.is_liquid(_world.get_block(wx, h + 1, wz)):
		return false
	if Blocks.collides(_world.get_block(wx, h + 1, wz)) or Blocks.collides(_world.get_block(wx, h + 2, wz)):
		return false

	var kind := _pick_kind()
	var mob := MonsterMob.new()
	mob.name = _kind_name(kind)
	add_child(mob)
	mob.setup(_world, _player, self, kind, Vector3(float(wx) + 0.5, float(h + 1), float(wz) + 0.5), _rng.randi())
	mob.loot_dropped.connect(_on_loot_dropped)
	return true


func _pick_kind() -> MonsterMob.Kind:
	var roll := _rng.randf()
	if roll < 0.35:
		return MonsterMob.Kind.ZOMBIE
	if roll < 0.60:
		return MonsterMob.Kind.SKELETON
	if roll < 0.85:
		return MonsterMob.Kind.SPIDER
	return MonsterMob.Kind.CREEPER


func _kind_name(kind: MonsterMob.Kind) -> String:
	match kind:
		MonsterMob.Kind.SKELETON:
			return "Skeleton"
		MonsterMob.Kind.SPIDER:
			return "Spider"
		MonsterMob.Kind.CREEPER:
			return "Creeper"
		_:
			return "Zombie"


func _on_loot_dropped(item_id: int, count: int) -> void:
	loot_dropped.emit(item_id, count)


# ---------------------------------------------------------------------------
# Despawning
# ---------------------------------------------------------------------------

func _monster_count() -> int:
	var count := 0
	for node in get_tree().get_nodes_in_group("monsters"):
		var mob := node as MonsterMob
		if mob != null and mob.alive():
			count += 1
	return count


func _banish_all() -> void:
	for node in get_tree().get_nodes_in_group("monsters"):
		var mob := node as MonsterMob
		if mob != null:
			mob.banish()


func _despawn_far() -> void:
	for node in get_tree().get_nodes_in_group("monsters"):
		var mob := node as MonsterMob
		if mob == null or not mob.alive():
			continue
		if mob.global_position.distance_to(_player.global_position) > DESPAWN_RADIUS:
			mob.banish()


func _creative() -> bool:
	if _game == null:
		_game = get_node_or_null(^"/root/Game")
	if _game == null:
		return true
	var value: Variant = _game.get("creative")
	return bool(value) if value is bool else true
