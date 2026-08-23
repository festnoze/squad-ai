## The two resistance fighters the player is allowed to take with him.
##
## A companion is not a new kind of creature: he is an ordinary allied `Soldier`
## already living in a liberated sector, whose leash changes hands. That is the
## whole design, and it buys three things.
##
##  * The combat AI is already written. This module never aims, never shoots and
##    never picks cover; it recruits, gives one of two orders, and buries.
##  * The soldier budget stays honest. Recruiting converts a man who was already
##    counted, it never spawns one, so two companions cost nothing on top of the
##    sixty live soldiers.
##  * Death stays final. A lost companion is a dead `Soldier` like any other, no
##    revive, no respawn; the player has to walk into another liberated sector
##    and talk somebody else into it.
##
## Fire discipline is the reason this node exists at all. Left alone, two allied
## soldiers would open up on the first sentry they see and hand the alert to the
## garrison before the player has taken a step. So while the war is calm and the
## player has not fired yet, every companion is stripped of his target on each
## frame. A soldier without a target leaves `S_COMBAT` on the spot, and a fresh
## re-acquisition always re-arms his reaction timer, which is longer than the
## frame it would need to squeeze a round off. The restraint lifts the moment the
## player fires, and comes back when the alert falls to calm again.
class_name CompanionManager
extends Node

const MAX_COMPANIONS := 2

## Group the player looks in to find this node.
const GROUP_NAME := "companions"

## Trailing distance of the first and second companion. Two different values,
## otherwise both men fight for the same square metre behind the player.
const FOLLOW_BASE := 3.6
const FOLLOW_STEP := 1.6

## A follower stuck further than this for `LOST_GRACE` seconds is put back on
## the player's heels. Doorways are 1.6 m wide in this world and two soldiers
## plus a player do get wedged in one.
const LOST_DISTANCE := 40.0
const LOST_GRACE := 6.0
const REJOIN_DISTANCE := 8.0

## Follow orders are only re-sent when the man has drifted and is not fighting.
const ORDER_REFRESH := 1.5
const DRIFT_FACTOR := 2.5

## How long one player shot keeps the companions free to fire while the war is
## still officially calm. Long enough to finish the fight he started.
const FIRE_RELEASE_SECONDS := 20.0

## Radius of the little circle companions are dropped in after a fast travel.
const REGROUP_RADIUS := 2.6

signal recruited(companion: Soldier)
signal companion_lost(companion: Soldier)
signal order_changed(companion: Soldier, following: bool)


## One recruited fighter and the single order he carries.
class _Slot extends RefCounted:
	var soldier: Soldier = null
	var following: bool = true
	var lost_timer: float = 0.0


var _world: GameWorld = null
var _player: Player = null
var _slots: Array = []
var _rng := RandomNumberGenerator.new()

var _release_timer := 0.0
var _refresh_timer := 0.0

## Player position as of the last tick. Fast travel teleports the player before
## it asks who follows, so the answer has to be measured against where he was.
var _player_pos := Vector3.ZERO
var _has_player_pos := false


func _ready() -> void:
	add_to_group(GROUP_NAME)
	_rng.randomize()
	# The clamp also runs on the physics step: perception and firing live there,
	# and a frame skipped by a slow render must not become a free shot.
	set_physics_process(true)


func setup(game_world: GameWorld, player_node: Player) -> void:
	_world = game_world
	_player = player_node
	if _player != null and is_instance_valid(_player):
		if not _player.fired.is_connected(_on_player_fired):
			_player.fired.connect(_on_player_fired)
		if _player.is_inside_tree():
			_player_pos = _player.global_position
			_has_player_pos = true
	if not War.alert_changed.is_connected(_on_alert_changed):
		War.alert_changed.connect(_on_alert_changed)


func tick(delta: float) -> void:
	_release_timer = maxf(0.0, _release_timer - delta)
	if _player != null and is_instance_valid(_player) and _player.is_inside_tree():
		_player_pos = _player.global_position
		_has_player_pos = true

	_prune()
	if _slots.is_empty():
		return

	if holding_fire():
		_clamp_fire()

	_refresh_timer -= delta
	var refresh := _refresh_timer <= 0.0
	if refresh:
		_refresh_timer = ORDER_REFRESH
	for index in _slots.size():
		var slot: _Slot = _slots[index]
		_tick_slot(slot, index, delta, refresh)


func _physics_process(_delta: float) -> void:
	if _slots.is_empty():
		return
	if holding_fire():
		_clamp_fire()


# ---------------------------------------------------------------------------
# Recruiting
# ---------------------------------------------------------------------------

## Can this node be recruited right now (free resistance fighter, cap not hit)?
## Called every frame by the player to decide whether to show the prompt, so it
## stays a handful of comparisons and never touches the scene tree.
func can_recruit(candidate: Node) -> bool:
	if count() >= MAX_COMPANIONS:
		return false
	# Validity is tested on the raw entry: casting an already freed object is
	# itself the error, a check on the cast result would come too late.
	if candidate == null or not is_instance_valid(candidate):
		return false
	var man := candidate as Soldier
	if man == null:
		return false
	if man.faction != War.ALLIED or not man.is_alive():
		return false
	if not man.is_inside_tree():
		return false
	return _slot_of(man) == null


func recruit(candidate: Node) -> bool:
	if not can_recruit(candidate):
		return false
	var man := candidate as Soldier
	if man == null:
		return false

	_adopt(man)
	var slot := _Slot.new()
	slot.soldier = man
	slot.following = true
	slot.lost_timer = 0.0
	_slots.append(slot)
	if not man.died.is_connected(_on_companion_died):
		man.died.connect(_on_companion_died)
	_apply_order(slot, _slots.size() - 1)
	recruited.emit(man)
	return true


## Takes the man out of his squad and under this node. Without it the Director
## would recycle his squad from under him and free a live companion.
func _adopt(man: Soldier) -> void:
	var parent := man.get_parent()
	if parent != null and is_instance_valid(parent):
		var squad := parent as Squad
		if squad != null:
			squad.release_member(man)
	man.set_squad(null)
	if parent == self:
		return
	var pose := man.global_transform
	if parent != null and is_instance_valid(parent):
		parent.remove_child(man)
	man.name = "Compagnon%d" % (Time.get_ticks_usec() & 0xFFFFF)
	add_child(man)
	man.global_transform = pose


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

## Switches an already recruited companion between following and holding.
func toggle_order(candidate: Node) -> void:
	if candidate == null or not is_instance_valid(candidate):
		return
	var man := candidate as Soldier
	if man == null:
		return
	var index := _index_of(man)
	if index < 0:
		return
	var slot: _Slot = _slots[index]
	if not man.is_alive():
		return
	slot.following = not slot.following
	slot.lost_timer = 0.0
	_apply_order(slot, index)
	order_changed.emit(man, slot.following)


func _apply_order(slot: _Slot, index: int) -> void:
	var man := slot.soldier
	if man == null or not is_instance_valid(man) or not man.is_alive():
		return
	if slot.following and _player != null and is_instance_valid(_player):
		man.order_follow(_player, _follow_distance(index))
	else:
		man.order_hold(man.global_position)


func _follow_distance(index: int) -> float:
	return FOLLOW_BASE + FOLLOW_STEP * float(maxi(0, index))


func _tick_slot(slot: _Slot, index: int, delta: float, refresh: bool) -> void:
	var man := slot.soldier
	if man == null or not is_instance_valid(man) or not man.is_alive():
		return
	if not slot.following:
		return
	if _player == null or not is_instance_valid(_player) or not _player.is_inside_tree():
		return

	var gap := _flat_distance(man.global_position, _player.global_position)
	if gap > LOST_DISTANCE:
		slot.lost_timer += delta
		if slot.lost_timer >= LOST_GRACE:
			slot.lost_timer = 0.0
			_rejoin(man)
			man.order_follow(_player, _follow_distance(index))
			return
	else:
		slot.lost_timer = 0.0

	# Re-sent only when he has drifted and has nothing better to do, so an order
	# never pulls a man out of a firefight he is winning.
	if refresh and gap > _follow_distance(index) * DRIFT_FACTOR and not man.is_engaged():
		man.order_follow(_player, _follow_distance(index))


## Soft teleport behind the player, for the man wedged in a farmhouse door.
func _rejoin(man: Soldier) -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var back := -_player.global_transform.basis.z
	back.y = 0.0
	if back.length() < 0.01:
		back = Vector3.FORWARD
	var spot := _player.global_position - back.normalized() * REJOIN_DISTANCE
	spot += Vector3(_rng.randf_range(-1.2, 1.2), 0.0, _rng.randf_range(-1.2, 1.2))
	_place(man, spot)


func _place(man: Soldier, spot: Vector3) -> void:
	var at := spot
	if _world != null and is_instance_valid(_world):
		at.y = _world.ground_y(at.x, at.z) + 0.1
	man.velocity = Vector3.ZERO
	man.global_position = at


# ---------------------------------------------------------------------------
# Fire discipline
# ---------------------------------------------------------------------------

## True while the companions are forbidden to shoot: the war is calm and the
## player has not opened fire.
func holding_fire() -> bool:
	return War.alert_level == War.ALERT_CALM and _release_timer <= 0.0


## Strips every companion of his target. `_state_combat` drops back to `S_ALERT`
## on a null target and `_try_fire` needs one, so this is the whole gate. It is
## deliberately not a flag inside `Soldier`: the combat AI belongs to somebody
## else and stays untouched.
func _clamp_fire() -> void:
	for entry in _slots:
		var slot: _Slot = entry
		var man := slot.soldier
		if man == null or not is_instance_valid(man):
			continue
		if man.target != null:
			man.target = null


func _on_player_fired(_weapon_id: int) -> void:
	_release_timer = FIRE_RELEASE_SECONDS


func _on_alert_changed(level: int) -> void:
	if level == War.ALERT_CALM:
		# The garrison went back to sleep: so does the trigger finger.
		_release_timer = 0.0


# ---------------------------------------------------------------------------
# Life cycle
# ---------------------------------------------------------------------------

func is_companion(candidate: Node) -> bool:
	if candidate == null or not is_instance_valid(candidate):
		return false
	var man := candidate as Soldier
	if man == null:
		return false
	return _slot_of(man) != null


func count() -> int:
	var total := 0
	for entry in _slots:
		var slot: _Slot = entry
		var man := slot.soldier
		if man != null and is_instance_valid(man) and man.is_alive():
			total += 1
	return total


func members() -> Array:
	var result: Array = []
	for entry in _slots:
		var slot: _Slot = entry
		var man := slot.soldier
		if man != null and is_instance_valid(man) and man.is_alive():
			result.append(man)
	return result


## Frees every companion. Called when the world is torn down, safe to call twice.
func dismiss_all() -> void:
	for entry in _slots:
		var slot: _Slot = entry
		var man := slot.soldier
		slot.soldier = null
		if man == null or not is_instance_valid(man):
			continue
		if man.died.is_connected(_on_companion_died):
			man.died.disconnect(_on_companion_died)
		man.queue_free()
	_slots.clear()


## Puts the companions who were close enough around a new position, and leaves
## the others where they stand. Returns how many made the trip.
func regroup_at(pos: Vector3, max_distance: float) -> int:
	var reference := _player_pos if _has_player_pos else pos
	var limit := maxf(0.0, max_distance)
	var moved := 0
	for index in _slots.size():
		var slot: _Slot = _slots[index]
		var man := slot.soldier
		if man == null or not is_instance_valid(man) or not man.is_alive():
			continue
		if _flat_distance(man.global_position, reference) > limit:
			# He was off on his own business, he is not dragged across Normandy.
			# Holding is the only sane order for a man left a sector behind.
			if slot.following:
				slot.following = false
				slot.lost_timer = 0.0
				man.order_hold(man.global_position)
				order_changed.emit(man, false)
			continue
		var angle := TAU * float(moved) / float(MAX_COMPANIONS) + _rng.randf_range(-0.3, 0.3)
		var spot := pos + Vector3(cos(angle), 0.0, sin(angle)) * REGROUP_RADIUS
		_place(man, spot)
		slot.lost_timer = 0.0
		_apply_order(slot, index)
		moved += 1
	_player_pos = pos
	_has_player_pos = true
	return moved


func _on_companion_died(soldier: Soldier) -> void:
	if soldier == null or not is_instance_valid(soldier):
		return
	var index := _index_of(soldier)
	if index < 0:
		return
	var slot: _Slot = _slots[index]
	slot.soldier = null
	_slots.remove_at(index)
	# No revive anywhere in this module: the corpse stays, sinks and is gone.
	companion_lost.emit(soldier)


## Drops entries whose soldier was freed or died without the signal reaching us.
func _prune() -> void:
	var i := _slots.size() - 1
	while i >= 0:
		var slot: _Slot = _slots[i]
		var man := slot.soldier
		if man == null or not is_instance_valid(man):
			_slots.remove_at(i)
		elif not man.is_alive():
			slot.soldier = null
			_slots.remove_at(i)
			companion_lost.emit(man)
		i -= 1


func _slot_of(man: Soldier) -> _Slot:
	var index := _index_of(man)
	return _slots[index] if index >= 0 else null


func _index_of(man: Soldier) -> int:
	if man == null:
		return -1
	for i in _slots.size():
		var slot: _Slot = _slots[i]
		var held := slot.soldier
		if held != null and is_instance_valid(held) and held == man:
			return i
	return -1


func _flat_distance(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


func debug_line() -> String:
	return "compagnons %d/%d %s" % [count(), MAX_COMPANIONS,
			"tir retenu" if holding_fire() else "tir libre"]
