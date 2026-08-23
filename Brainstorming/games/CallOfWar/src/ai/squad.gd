## A coordinated group of 3 to 6 soldiers.
##
## The squad is what turns a pile of individual state machines into something
## that reads as trained infantry:
##  * shared knowledge, one man seeing the player puts the whole squad on it,
##    with a slower reaction for the ones who only heard it on the radio;
##  * roles, the closest men fix the target from the front while a veteran goes
##    around the side, and posted weapons stay posted;
##  * a rally point, so a squad ordered to defend spreads over the local cover
##    instead of piling up on one spot.
##
## The node itself never moves: it stays at the origin of the scene so a member
## added before the squad is in the tree still lands on the right world spot.
class_name Squad
extends Node3D

signal wiped(squad: Squad)

const MIN_SIZE := 3
const MAX_SIZE := 6

## How far a shouted contact carries. Past that a member only gets a vague
## direction instead of a locked target.
const VOICE_RANGE := 60.0
## Contact knowledge older than this stops being pushed around.
const CONTACT_MEMORY := 22.0
## A member further than this from the squad centre is called back, unless he
## is busy fighting.
const COHESION_RANGE := 55.0

var faction: int = 1
var members: Array[Soldier] = []

var _world: GameWorld = null
var _rng := RandomNumberGenerator.new()
var _patrol: PackedVector3Array = PackedVector3Array()
var _spawn := Vector3.ZERO
var _rally := Vector3.ZERO
var _has_rally := false
var _defend_radius := 12.0
var _last_contact: Node3D = null
var _last_contact_pos := Vector3.ZERO
var _contact_age := 999.0
var _share_timer := 0.0
var _role_timer := 0.0
var _wiped_sent := false


func _ready() -> void:
	set_process(true)


func setup(game_world: GameWorld, faction_id: int, spawn: Vector3, size: int,
		patrol: PackedVector3Array) -> void:
	_world = game_world
	faction = faction_id
	_spawn = spawn
	_patrol = patrol
	_rally = spawn
	transform = Transform3D.IDENTITY
	_rng.seed = int(abs(spawn.x * 2749.0 + spawn.z * 33179.0)) + Time.get_ticks_usec()

	var count := clampi(size, MIN_SIZE, MAX_SIZE)
	var ranks := _compose(count)
	for i in ranks.size():
		_spawn_member(ranks[i], i, ranks.size())
	_share_timer = _rng.randf() * 1.2
	_role_timer = _rng.randf() * 2.0


## Rank list for a squad of `count` men. One leader, at most one support
## weapon, the rest of the line filled with regulars and conscripts.
func _compose(count: int) -> PackedInt32Array:
	var ranks := PackedInt32Array()
	if _rng.randf() < 0.2:
		ranks.append(Soldier.R_OFFICER)
	else:
		ranks.append(Soldier.R_VETERAN)
	if count >= 5 and _rng.randf() < 0.4:
		ranks.append(Soldier.R_MACHINE_GUNNER)
	elif count >= 4 and _rng.randf() < 0.15:
		ranks.append(Soldier.R_SNIPER)
	while ranks.size() < count:
		ranks.append(Soldier.R_REGULAR if _rng.randf() < 0.6 else Soldier.R_CONSCRIPT)
	return ranks


func _spawn_member(member_rank: int, index: int, total: int) -> void:
	var soldier := Soldier.new()
	soldier.name = "Soldat%d" % index
	add_child(soldier)
	var angle := TAU * float(index) / float(maxi(1, total))
	var radius := 1.6 + _rng.randf() * 2.2
	var home := _spawn + Vector3(cos(angle) * radius, 0.0, sin(angle) * radius)
	if _world != null:
		home.y = _world.ground_y(home.x, home.z)
	soldier.setup(_world, faction, member_rank, home)
	soldier.set_squad(self)
	if not _patrol.is_empty() and member_rank != Soldier.R_SNIPER \
			and member_rank != Soldier.R_MACHINE_GUNNER:
		soldier.set_patrol_route(_offset_route(_patrol, index))
	soldier.died.connect(_on_member_died)
	soldier.spotted_enemy.connect(_on_member_spotted)
	members.append(soldier)


## Same route for everybody would stack the whole squad on one line, so each
## man walks his own lane a couple of metres beside it.
func _offset_route(route: PackedVector3Array, index: int) -> PackedVector3Array:
	var lane := (float(index) - 1.0) * 1.4
	var result := PackedVector3Array()
	for i in route.size():
		var point := route[i]
		var next := route[(i + 1) % route.size()]
		var direction := next - point
		direction.y = 0.0
		if direction.length() < 0.01:
			direction = Vector3.FORWARD
		var side := direction.normalized().cross(Vector3.UP)
		result.append(point + side * lane)
	return result


func _process(delta: float) -> void:
	if members.is_empty():
		return
	_contact_age += delta
	_share_timer -= delta
	if _share_timer <= 0.0:
		_share_timer = 1.2
		_share_knowledge()
	_role_timer -= delta
	if _role_timer <= 0.0:
		_role_timer = 3.0
		if _contact_age < CONTACT_MEMORY:
			_assign_roles(_last_contact_pos)
		_check_cohesion()


## Everyone who has nothing keeps getting told where the trouble is, so a squad
## never has one man fighting while the others stare at a hedge.
func _share_knowledge() -> void:
	if _contact_age > CONTACT_MEMORY:
		return
	var fresh := _last_contact_pos
	if _last_contact != null and is_instance_valid(_last_contact):
		for member in members:
			if member != null and is_instance_valid(member) and member.is_alive() \
					and member.target == _last_contact and member.is_engaged():
				fresh = _last_contact.global_position
				_last_contact_pos = fresh
				_contact_age = 0.0
				break
	for member in members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		if member.is_engaged() and member.target != null:
			continue
		member.alert_to(fresh, 0.6)


func _check_cohesion() -> void:
	if not _has_rally:
		return
	var anchor := _rally
	for member in members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		if member.is_engaged():
			continue
		if member.global_position.distance_to(anchor) > COHESION_RANGE:
			member.order_move_to(anchor)


## Shared knowledge: one member seeing the player alerts everyone in the squad.
func report_contact(enemy: Node3D, at: Vector3) -> void:
	if enemy == null or not is_instance_valid(enemy):
		return
	_last_contact = enemy
	_last_contact_pos = at
	_contact_age = 0.0
	for member in members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		var distance := member.global_position.distance_to(at)
		if distance <= VOICE_RANGE:
			member.notice_enemy(enemy)
		else:
			member.alert_to(at, 0.55)
	_assign_roles(at)


## Two men pin the target down, one goes around, posted weapons support. The
## roles are only hints: the soldier state machine decides when to use them.
func _assign_roles(at: Vector3) -> void:
	var alive := _alive_members()
	if alive.is_empty():
		return
	alive.sort_custom(func(a: Soldier, b: Soldier) -> bool:
		return a.global_position.distance_squared_to(at) \
				< b.global_position.distance_squared_to(at))
	var flanker: Soldier = null
	for i in alive.size():
		var member := alive[i]
		if member.rank == Soldier.R_SNIPER or member.rank == Soldier.R_MACHINE_GUNNER:
			member.set_role(Soldier.ROLE_SUPPORT)
			continue
		if i < 2:
			member.set_role(Soldier.ROLE_FIX)
		else:
			member.set_role(Soldier.ROLE_FREE)
			if flanker == null or member.rank == Soldier.R_VETERAN:
				flanker = member
	# Never flank alone: somebody has to keep the target's head down.
	if flanker != null and alive.size() >= 3:
		flanker.set_role(Soldier.ROLE_FLANK)


func order_attack(pos: Vector3) -> void:
	_rally = pos
	_has_rally = true
	_last_contact_pos = pos
	_contact_age = minf(_contact_age, CONTACT_MEMORY - 1.0)
	var alive := _alive_members()
	for i in alive.size():
		var member := alive[i]
		var angle := TAU * float(i) / float(maxi(1, alive.size()))
		var offset := Vector3(cos(angle), 0.0, sin(angle)) * (3.0 + float(i))
		member.alert_to(pos, 0.75)
		member.order_move_to(pos + offset)


func order_defend(pos: Vector3, radius: float) -> void:
	_rally = pos
	_has_rally = true
	_defend_radius = maxf(3.0, radius)
	var alive := _alive_members()
	var cover: Array = []
	if _world != null:
		cover = _world.cover_points_near(pos, _defend_radius * 1.6)
	for i in alive.size():
		var member := alive[i]
		var spot := pos
		if i < cover.size():
			spot = cover[i].position
		else:
			var angle := TAU * float(i) / float(maxi(1, alive.size()))
			spot = pos + Vector3(cos(angle), 0.0, sin(angle)) * _defend_radius
			if _world != null:
				spot.y = _world.ground_y(spot.x, spot.z)
		if not cover.is_empty():
			member.set_cover_points(cover)
		member.order_hold(spot)


func alive_count() -> int:
	var count := 0
	for member in members:
		if member != null and is_instance_valid(member) and member.is_alive():
			count += 1
	return count


func center() -> Vector3:
	var total := Vector3.ZERO
	var count := 0
	for member in members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		total += member.global_position
		count += 1
	if count == 0:
		return _spawn
	return total / float(count)


## Frees every member. Safe to call twice.
func despawn() -> void:
	for member in members:
		if member == null or not is_instance_valid(member):
			continue
		if member.died.is_connected(_on_member_died):
			member.died.disconnect(_on_member_died)
		if member.spotted_enemy.is_connected(_on_member_spotted):
			member.spotted_enemy.disconnect(_on_member_spotted)
		member.queue_free()
	members.clear()
	_last_contact = null
	queue_free()


func _alive_members() -> Array[Soldier]:
	var result: Array[Soldier] = []
	for member in members:
		if member != null and is_instance_valid(member) and member.is_alive():
			result.append(member)
	return result


func _on_member_died(soldier: Soldier) -> void:
	if soldier != null and is_instance_valid(soldier):
		# A man going down tells the others where the fire came from.
		var from := soldier.known_target_position()
		for member in _alive_members():
			member.alert_to(from, 0.7)
	if alive_count() > 0:
		return
	if _wiped_sent:
		return
	_wiped_sent = true
	wiped.emit(self)


func _on_member_spotted(soldier: Soldier, enemy: Node3D) -> void:
	if enemy == null or not is_instance_valid(enemy):
		return
	_last_contact = enemy
	_last_contact_pos = enemy.global_position
	_contact_age = 0.0
	if soldier != null and is_instance_valid(soldier):
		_assign_roles(_last_contact_pos)


func debug_line() -> String:
	return "escouade %d/%d contact=%.0fs" % [alive_count(), members.size(), _contact_age]
