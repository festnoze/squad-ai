## The living world: site garrisons, roaming patrols, alert driven
## reinforcements, friendly maquisards and the ambient noise of a war that goes
## on whether the player is watching or not.
##
## Three rules shape everything here.
##
## 1. Budget. Never more than `MAX_SOLDIERS` live soldiers nor `MAX_SQUADS`
##    squads. Squads farther than `RECYCLE_DISTANCE` and not fighting are
##    recycled, which also keeps the physics step flat.
## 2. Never spawn in front of the player. An order is only executed when its
##    position is at least `MIN_SPAWN_DISTANCE` away and either behind the
##    player, far enough to be a dot, or hidden behind something solid. An
##    order that cannot be executed waits in the queue instead of cheating.
## 3. Never build the whole world on one frame. Orders are spent one at a time,
##    `SPAWN_GAP` seconds apart, and a garrison is cut into squads of at most
##    `SQUAD_MAX_SIZE` so a twelve man site fills up over several seconds
##    instead of popping into existence. `Squad.setup()` builds its own members
##    in a single call, so four soldiers is the finest grain the contract
##    allows; the staggering happens between squads.
##
## Garrison memory. `_garrison_left` keeps, for the whole session, how many men
## a site still owes. Killing four of the six defenders of a farm and walking
## away means two men are there when you come back, not six.
class_name Director
extends Node

signal event_announced(text: String)

# --- Budget ----------------------------------------------------------------

const MAX_SOLDIERS := 60
const MAX_SQUADS := 14
const SQUAD_MAX_SIZE := 4
const RECYCLE_DISTANCE := 320.0
const ALLY_MAX := 10

# --- Spawn safety ----------------------------------------------------------

const MIN_SPAWN_DISTANCE := 70.0
## Beyond this the player cannot tell a soldier appeared, so the cone test is
## skipped entirely.
const VIEW_CHECK_DISTANCE := 260.0
## Cosine of the half angle considered "in front of the player" (about 70 deg).
const VIEW_DOT := 0.34
## Seconds between two spawn orders.
const SPAWN_GAP := 0.55
## An order that never becomes safe is dropped after this many seconds.
const ORDER_LIFE := 45.0

# --- Rhythm ----------------------------------------------------------------

const SITE_SCAN_GAP := 0.8
const SITE_RANGE := 700.0
const PATROL_MIN := 190.0
const PATROL_MAX := 470.0
const PATROL_POINTS := 6
const REINFORCE_GAP := 30.0
const REINFORCE_MAX_WAVES := 3
const REINFORCE_RING_MIN := 150.0
const REINFORCE_RING_MAX := 250.0
const AMBIENCE_MIN := 40.0
const AMBIENCE_MAX := 120.0
const RECYCLE_GAP := 1.0

# --- Ambience --------------------------------------------------------------

const PLANE_SPEED := 92.0
const PLANE_ALTITUDE := 138.0
const PLANE_RUN := 860.0
const PLANE_SOUND_GAP := 1.15

const EV_ARTILLERY := 0
const EV_PLANE := 1
const EV_CONVOY := 2
const EV_PATROL := 3
const EV_BIRDS := 4

# --- Order kinds -----------------------------------------------------------

const K_GARRISON := 0
const K_PATROL := 1
const K_REINFORCE := 2
const K_ALLY := 3
const K_OFFICER := 4


## One pending spawn. Orders are the only way anything is created.
class _Order extends RefCounted:
	var kind: int = K_PATROL
	var site_id: int = -1
	var position: Vector3 = Vector3.ZERO
	var size: int = 3
	var faction: int = 1
	var patrol: PackedVector3Array = PackedVector3Array()
	var target: Vector3 = Vector3.ZERO
	var has_target: bool = false
	var anchor: Vector3 = Vector3.ZERO
	var radius: float = 30.0
	var life: float = ORDER_LIFE


## One delayed sound or blast, so an artillery salvo is spread over seconds.
class _Cue extends RefCounted:
	var delay: float = 0.0
	var sample: String = ""
	var position: Vector3 = Vector3.ZERO
	var volume: float = 0.0
	var pitch: float = 1.0
	var blast: float = 0.0


var _world: GameWorld = null
var _player: Player = null
var _tracker: ObjectiveTracker = null

var _squads: Array[Squad] = []
var _lone: Array[Soldier] = []
var _orders: Array[_Order] = []
var _cues: Array[_Cue] = []

## site id -> soldiers the site still owes, for the whole session.
var _garrison_left: Dictionary = {}
## site id -> Array[Squad] currently holding it.
var _garrison_squads: Dictionary = {}
## soldier instance id -> site id, so a death can be charged to a site.
var _soldier_site: Dictionary = {}
## site id -> true once its officer has been spawned (dead or alive).
var _officer_done: Dictionary = {}
## site id -> true once a friendly cell has been placed there.
var _ally_done: Dictionary = {}

var _rng := RandomNumberGenerator.new()
var _player_pos := Vector3.ZERO
var _last_known := Vector3.ZERO
## Site the player was parachuted next to: it always hosts a friendly cell.
var _home_site_id: int = -1

var _spawn_gap: float = 0.0
var _scan_gap: float = 0.4
var _patrol_gap: float = 25.0
var _ambience_gap: float = 22.0
var _recycle_gap: float = RECYCLE_GAP
var _wave_gap: float = 0.0
var _known_gap: float = 0.0
var _waves: int = 0

var _plane: Node3D = null
var _plane_dir := Vector3.FORWARD
var _plane_left: float = 0.0
var _plane_sound: float = 0.0

var _ready_to_run: bool = false


func _ready() -> void:
	add_to_group("director")
	set_process(false)
	set_physics_process(false)


func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void:
	_world = game_world
	_player = player_node
	_tracker = tracker
	if _world == null:
		push_error("Director.setup: world is null, the world will stay empty")
		return
	_rng.seed = int(Time.get_unix_time_from_system()) ^ 0x5F3759DF
	_player_pos = _player.global_position if _player != null else Vector3.ZERO
	_last_known = _player_pos

	var layout: Layout = _world.layout()
	if layout != null:
		var spawn: Vector2 = layout.spawn_point()
		var home: Layout.Site = layout.nearest_site(spawn.x, spawn.y)
		if home != null:
			_home_site_id = home.id
	if not War.sector_captured.is_connected(_on_sector_captured):
		War.sector_captured.connect(_on_sector_captured)

	_ambience_gap = _rng.randf_range(20.0, 45.0)
	_patrol_gap = _rng.randf_range(12.0, 25.0)
	_ready_to_run = true


## A liberated sector keeps no garrison: whoever was still standing pulls out.
func _on_sector_captured(sector_id: int) -> void:
	_garrison_left[sector_id] = 0
	var squads: Array = _garrison_squads.get(sector_id, [])
	for entry in squads.duplicate():
		var squad: Squad = entry
		if squad != null and is_instance_valid(squad) and squad.faction == War.AXIS:
			_release_squad(squad)
	_garrison_squads[sector_id] = []


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------

func tick(delta: float) -> void:
	if not _ready_to_run or _world == null:
		return
	if _player != null and is_instance_valid(_player):
		_player_pos = _player.global_position

	_prune()

	_scan_gap -= delta
	if _scan_gap <= 0.0:
		_scan_gap = SITE_SCAN_GAP
		_scan_sites()

	_patrol_gap -= delta
	if _patrol_gap <= 0.0:
		_patrol_gap = _patrol_interval()
		_queue_patrol(false)

	_tick_reinforcements(delta)

	_ambience_gap -= delta
	if _ambience_gap <= 0.0:
		_ambience_gap = _rng.randf_range(AMBIENCE_MIN, AMBIENCE_MAX)
		_fire_ambience()

	_tick_cues(delta)
	_tick_plane(delta)
	_tick_orders(delta)

	_recycle_gap -= delta
	if _recycle_gap <= 0.0:
		_recycle_gap = RECYCLE_GAP
		_recycle()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

func live_soldier_count() -> int:
	var total: int = 0
	for squad in _squads:
		if squad != null and is_instance_valid(squad):
			total += squad.alive_count()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier) and soldier.is_alive():
			total += 1
	return total


func live_squad_count() -> int:
	return _squads.size()


## Forces a reinforcement wave towards a position. Split into small squads that
## come in from a ring around the target, never from the player's face.
func send_reinforcements(pos: Vector3, count: int) -> void:
	if _world == null or count <= 0:
		return
	var remaining: int = mini(count, MAX_SOLDIERS)
	var guard: int = 0
	while remaining > 0 and guard < 6:
		guard += 1
		var size: int = mini(remaining, SQUAD_MAX_SIZE)
		remaining -= size
		var order := _Order.new()
		order.kind = K_REINFORCE
		order.size = size
		order.faction = War.AXIS
		order.position = _ring_point(pos, REINFORCE_RING_MIN, REINFORCE_RING_MAX)
		order.target = pos
		order.has_target = true
		order.anchor = pos
		order.radius = 40.0
		_orders.append(order)


## Frees every spawned squad. Called on shutdown and on scene reload.
func clear_all() -> void:
	for squad in _squads:
		if squad != null and is_instance_valid(squad):
			_detach_squad(squad)
			squad.despawn()
			squad.queue_free()
	_squads.clear()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier):
			if soldier.died.is_connected(_on_soldier_died):
				soldier.died.disconnect(_on_soldier_died)
			soldier.queue_free()
	_lone.clear()
	_orders.clear()
	_cues.clear()
	_garrison_squads.clear()
	_soldier_site.clear()
	if _plane != null and is_instance_valid(_plane):
		_plane.queue_free()
	_plane = null
	_plane_left = 0.0
	if War.sector_captured.is_connected(_on_sector_captured):
		War.sector_captured.disconnect(_on_sector_captured)
	_ready_to_run = false


func debug_line() -> String:
	return "Director %d soldats, %d escouades, %d ordres, alerte %s" % [
		live_soldier_count(), _squads.size(), _orders.size(), War.alert_name()]


# ---------------------------------------------------------------------------
# Garrisons
# ---------------------------------------------------------------------------

func _scan_sites() -> void:
	var layout: Layout = _world.layout()
	if layout == null:
		return
	for site in layout.sites:
		var dx: float = site.center.x - _player_pos.x
		var dz: float = site.center.y - _player_pos.z
		if dx * dx + dz * dz > SITE_RANGE * SITE_RANGE:
			continue
		var built: SiteBuilder.BuiltSite = _world.built_site(site.id)
		if built == null:
			continue
		if site.is_sector and War.is_sector_captured(site.id):
			_ensure_allies(site, built)
			continue
		# The drop zone village always hides a Resistance cell, captured or not.
		if site.id == _home_site_id:
			_ensure_allies(site, built)
		_ensure_garrison(site, built)


func _ensure_garrison(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	if not _garrison_left.has(site.id):
		_garrison_left[site.id] = maxi(0, site.garrison)
	var left: int = _garrison_left[site.id]
	if left <= 0:
		return
	if _pending_for(site.id):
		return

	var present: int = _garrison_alive(site.id)
	var missing: int = left - present
	if missing > 0 and _has_room(mini(missing, SQUAD_MAX_SIZE)):
		var order := _Order.new()
		order.kind = K_GARRISON
		order.site_id = site.id
		order.size = mini(missing, SQUAD_MAX_SIZE)
		order.faction = War.AXIS
		order.position = _pick_spawn(built.garrison_spawns, site)
		order.patrol = _trim_route(built.patrol_points)
		order.anchor = Vector3(site.center.x, site.ground, site.center.y)
		order.radius = maxf(20.0, site.radius * 0.8)
		_orders.append(order)
		return

	# One officer per sector, on his anchor: he is the assassination target and
	# he does not count against the garrison strength.
	if site.is_sector and not _officer_done.has(site.id) and _has_room(1):
		var anchor: Variant = built.objective_anchors.get(MissionDefs.ANCHOR_OFFICER)
		var at: Vector3 = anchor if typeof(anchor) == TYPE_VECTOR3 else _site_anchor(site)
		var officer := _Order.new()
		officer.kind = K_OFFICER
		officer.site_id = site.id
		officer.size = 1
		officer.faction = War.AXIS
		officer.position = at
		officer.anchor = at
		officer.radius = maxf(18.0, site.radius * 0.6)
		_orders.append(officer)


func _site_anchor(site: Layout.Site) -> Vector3:
	return Vector3(site.center.x, site.ground, site.center.y)


func _garrison_alive(site_id: int) -> int:
	var squads: Array = _garrison_squads.get(site_id, [])
	var total: int = 0
	for entry in squads:
		var squad: Squad = entry
		if squad != null and is_instance_valid(squad):
			total += squad.alive_count()
	for soldier in _lone:
		if soldier == null or not is_instance_valid(soldier) or not soldier.is_alive():
			continue
		if _soldier_site.get(soldier.get_instance_id(), -1) == site_id and soldier.faction == War.AXIS:
			total += 1
	return total


# ---------------------------------------------------------------------------
# Allies
# ---------------------------------------------------------------------------

func _ensure_allies(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	if _ally_done.has(site.id) or not _has_room(3):
		return
	if _ally_count() >= ALLY_MAX or _pending_for(site.id):
		return
	_ally_done[site.id] = true
	var order := _Order.new()
	order.kind = K_ALLY
	order.site_id = site.id
	order.size = _rng.randi_range(2, 3)
	order.faction = War.ALLIED
	order.position = _pick_spawn(built.garrison_spawns, site)
	order.patrol = _trim_route(built.patrol_points)
	order.anchor = _site_anchor(site)
	order.radius = maxf(25.0, site.radius * 0.9)
	_orders.append(order)


func _ally_count() -> int:
	var total: int = 0
	for squad in _squads:
		if squad != null and is_instance_valid(squad) and squad.faction == War.ALLIED:
			total += squad.alive_count()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier) and soldier.is_alive() \
				and soldier.faction == War.ALLIED:
			total += 1
	return total


## Private extension used by `ObjectiveTracker` for a rescue: freed prisoners
## are plain allied soldiers who follow the player. They are exempt from the
## view cone rule since the player is the one opening their cage.
func _spawn_prisoners(pos: Vector3, count: int) -> Array:
	var out: Array = []
	if _world == null or count <= 0:
		return out
	var wanted: int = mini(count, 8)
	for i in wanted:
		if not _has_room(1):
			break
		var angle: float = TAU * float(i) / float(maxi(1, wanted))
		var at := pos + Vector3(cos(angle), 0.0, sin(angle)) * _rng.randf_range(1.5, 3.5)
		at.y = _world.ground_y(at.x, at.z)
		var man := _make_soldier(War.ALLIED, Soldier.R_CONSCRIPT, at, -1)
		if man == null:
			break
		man.order_move_to(_player_pos if _player != null else pos)
		out.append(man)
	if not out.is_empty():
		event_announced.emit("Les prisonniers sont libres, ramenez-les en zone amie.")
	return out


# ---------------------------------------------------------------------------
# Patrols
# ---------------------------------------------------------------------------

func _patrol_interval() -> float:
	# A calm sector is quiet; a general alert fills the roads.
	var base: float = 58.0 - 11.0 * float(War.alert_level)
	return _rng.randf_range(base * 0.7, base * 1.3)


func _queue_patrol(is_convoy: bool) -> void:
	if _squads.size() >= MAX_SQUADS - 2 or not _has_room(SQUAD_MAX_SIZE):
		return
	var route: PackedVector3Array = _road_route()
	if route.size() < 2:
		return
	var order := _Order.new()
	order.kind = K_PATROL
	order.faction = War.AXIS
	order.size = _rng.randi_range(3, SQUAD_MAX_SIZE) if is_convoy else _rng.randi_range(2, 3)
	order.position = route[0]
	order.patrol = route
	order.anchor = route[0]
	order.radius = 30.0
	_orders.append(order)
	if is_convoy:
		var layout: Layout = _world.layout()
		var near: Layout.Site = layout.nearest_site(route[0].x, route[0].z) if layout != null else null
		var place: String = near.display_name if near != null else "la vallee"
		event_announced.emit("Un convoi allemand circule sur la route de %s." % place)


## A slice of a real road, far enough from the player to be spawned on.
func _road_route() -> PackedVector3Array:
	var out := PackedVector3Array()
	var layout: Layout = _world.layout()
	if layout == null or layout.roads.is_empty():
		return out
	var candidates: Array[Vector2i] = []
	for road_index in layout.roads.size():
		var road: PackedVector2Array = layout.roads[road_index]
		for point_index in road.size():
			var p: Vector2 = road[point_index]
			var dx: float = p.x - _player_pos.x
			var dz: float = p.y - _player_pos.z
			var d: float = sqrt(dx * dx + dz * dz)
			if d >= PATROL_MIN and d <= PATROL_MAX:
				candidates.append(Vector2i(road_index, point_index))
	if candidates.is_empty():
		return out
	var pick: Vector2i = candidates[_rng.randi_range(0, candidates.size() - 1)]
	var chosen: PackedVector2Array = layout.roads[pick.x]
	var step: int = 2
	var index: int = pick.y
	var forward: bool = _rng.randf() < 0.5
	for i in PATROL_POINTS:
		if index < 0 or index >= chosen.size():
			break
		var p2: Vector2 = chosen[index]
		out.append(Vector3(p2.x, _world.ground_y(p2.x, p2.y), p2.y))
		index += step if forward else -step
	return out


func _trim_route(points: PackedVector3Array) -> PackedVector3Array:
	if points.size() <= PATROL_POINTS:
		return points
	var out := PackedVector3Array()
	var stride: int = maxi(1, points.size() / PATROL_POINTS)
	var i: int = 0
	while i < points.size() and out.size() < PATROL_POINTS:
		out.append(points[i])
		i += stride
	return out


# ---------------------------------------------------------------------------
# Reinforcements
# ---------------------------------------------------------------------------

func _tick_reinforcements(delta: float) -> void:
	if _player == null or not is_instance_valid(_player):
		return
	if War.alert_level < War.ALERT_FULL:
		_waves = 0
		_wave_gap = 8.0
		_last_known = _player_pos
		return

	_known_gap -= delta
	if _known_gap <= 0.0:
		_known_gap = 2.5
		# Last known position, not the live one: they hunt where you were.
		_last_known = _player_pos

	_wave_gap -= delta
	if _wave_gap > 0.0 or _waves >= REINFORCE_MAX_WAVES:
		return
	_wave_gap = REINFORCE_GAP
	_waves += 1
	send_reinforcements(_last_known, 3 + _waves)
	if _waves == 1:
		event_announced.emit("Des renforts allemands convergent vers votre position.")


## A point on a ring around `pos`, preferring one the player cannot watch.
func _ring_point(pos: Vector3, min_radius: float, max_radius: float) -> Vector3:
	var best := pos
	var best_score: float = -1.0
	var start: float = _rng.randf() * TAU
	for i in 8:
		var angle: float = start + TAU * float(i) / 8.0
		var radius: float = _rng.randf_range(min_radius, max_radius)
		var candidate := pos + Vector3(cos(angle), 0.0, sin(angle)) * radius
		candidate = Heightfield.clamp_to_bounds(candidate)
		candidate.y = _world.ground_y(candidate.x, candidate.z)
		if _spawn_safe(candidate):
			return candidate
		var score: float = candidate.distance_to(_player_pos)
		if score > best_score:
			best_score = score
			best = candidate
	return best


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

func _tick_orders(delta: float) -> void:
	if _orders.is_empty():
		return
	var index: int = _orders.size() - 1
	while index >= 0:
		var order: _Order = _orders[index]
		order.life -= delta
		if order.life <= 0.0:
			_orders.remove_at(index)
		index -= 1

	_spawn_gap -= delta
	if _spawn_gap > 0.0 or _orders.is_empty():
		return
	for i in _orders.size():
		var order: _Order = _orders[i]
		if not _has_room(order.size):
			return
		if not _spawn_safe(order.position):
			continue
		_orders.remove_at(i)
		_execute(order)
		_spawn_gap = SPAWN_GAP
		return


func _execute(order: _Order) -> void:
	if order.kind == K_OFFICER:
		_officer_done[order.site_id] = true
		var officer := _make_soldier(order.faction, Soldier.R_OFFICER, order.position, -1)
		if officer != null:
			officer.order_hold(order.position)
		return

	var squad := Squad.new()
	squad.name = "Squad%d" % (Time.get_ticks_msec() & 0xFFFF)
	add_child(squad)
	squad.setup(_world, order.faction, order.position, order.size, order.patrol)
	if not squad.wiped.is_connected(_on_squad_wiped):
		squad.wiped.connect(_on_squad_wiped)
	_squads.append(squad)

	for member in squad.members:
		if member == null or not is_instance_valid(member):
			continue
		if not member.died.is_connected(_on_soldier_died):
			member.died.connect(_on_soldier_died)
		if order.site_id >= 0:
			_soldier_site[member.get_instance_id()] = order.site_id

	if order.kind == K_GARRISON or order.kind == K_ALLY:
		if order.site_id >= 0:
			var list: Array = _garrison_squads.get(order.site_id, [])
			list.append(squad)
			_garrison_squads[order.site_id] = list
		squad.order_defend(order.anchor, order.radius)
	elif order.has_target:
		squad.order_attack(order.target)


func _pending_for(site_id: int) -> bool:
	for order in _orders:
		if order.site_id == site_id:
			return true
	return false


func _has_room(extra: int) -> bool:
	if _squads.size() >= MAX_SQUADS:
		return false
	return live_soldier_count() + extra <= MAX_SOLDIERS


## The single most visible flaw of a badly tuned director is an enemy popping
## into existence in front of the player. This is the guard against it.
func _spawn_safe(pos: Vector3) -> bool:
	if _player == null or not is_instance_valid(_player):
		return true
	if not Heightfield.in_bounds(pos.x, pos.z):
		return false
	var distance: float = pos.distance_to(_player_pos)
	if distance < MIN_SPAWN_DISTANCE:
		return false
	if distance > VIEW_CHECK_DISTANCE:
		return true

	var eye: Vector3 = _player.eye_position()
	var to: Vector3 = pos - eye
	to.y = 0.0
	if to.length_squared() < 1.0:
		return false
	to = to.normalized()
	var facing: Vector3 = _player.aim_direction()
	facing.y = 0.0
	if facing.length_squared() < 0.01:
		return true
	facing = facing.normalized()
	if facing.dot(to) < VIEW_DOT:
		return true                     # behind him, safe

	var space: World3D = _player.get_world_3d()
	if space == null:
		return false
	# In the cone: only allowed when something solid hides the spot.
	return not Ballistics.line_of_sight(space, eye, pos + Vector3.UP * 1.6, [_player])


func _pick_spawn(points: PackedVector3Array, site: Layout.Site) -> Vector3:
	var fallback := _site_anchor(site)
	if points.is_empty():
		return fallback
	var best := fallback
	var best_score: float = -1.0
	var start: int = _rng.randi_range(0, points.size() - 1)
	for i in points.size():
		var candidate: Vector3 = points[(start + i) % points.size()]
		if _spawn_safe(candidate):
			return candidate
		var score: float = candidate.distance_to(_player_pos)
		if score > best_score:
			best_score = score
			best = candidate
	return best


func _make_soldier(faction: int, rank: int, at: Vector3, site_id: int) -> Soldier:
	var soldier := Soldier.new()
	soldier.name = "Soldier%d" % (Time.get_ticks_usec() & 0xFFFFF)
	add_child(soldier)
	soldier.setup(_world, faction, rank, at)
	if not soldier.died.is_connected(_on_soldier_died):
		soldier.died.connect(_on_soldier_died)
	if site_id >= 0:
		_soldier_site[soldier.get_instance_id()] = site_id
	_lone.append(soldier)
	return soldier


# ---------------------------------------------------------------------------
# Recycling and bookkeeping
# ---------------------------------------------------------------------------

func _prune() -> void:
	var i: int = _squads.size() - 1
	while i >= 0:
		var squad: Squad = _squads[i]
		if squad == null or not is_instance_valid(squad):
			_squads.remove_at(i)
		i -= 1
	var j: int = _lone.size() - 1
	while j >= 0:
		var soldier: Soldier = _lone[j]
		if soldier == null or not is_instance_valid(soldier):
			_lone.remove_at(j)
		j -= 1


func _recycle() -> void:
	var i: int = _squads.size() - 1
	while i >= 0:
		var squad: Squad = _squads[i]
		i -= 1
		if squad == null or not is_instance_valid(squad):
			continue
		if squad.alive_count() <= 0:
			_release_squad(squad)
			continue
		if squad.center().distance_to(_player_pos) < RECYCLE_DISTANCE:
			continue
		if _engaged(squad):
			continue
		_release_squad(squad)


func _engaged(squad: Squad) -> bool:
	for member in squad.members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		var state: int = member.state
		if state != Soldier.S_IDLE and state != Soldier.S_PATROL and state != Soldier.S_DEAD:
			return true
	return false


## Sends a squad away without counting its members as casualties: they are
## still alive somewhere off screen, they simply stopped being simulated.
func _release_squad(squad: Squad) -> void:
	_detach_squad(squad)
	_squads.erase(squad)
	squad.despawn()
	squad.queue_free()


func _detach_squad(squad: Squad) -> void:
	if squad.wiped.is_connected(_on_squad_wiped):
		squad.wiped.disconnect(_on_squad_wiped)
	for member in squad.members:
		if member == null or not is_instance_valid(member):
			continue
		if member.died.is_connected(_on_soldier_died):
			member.died.disconnect(_on_soldier_died)
		_soldier_site.erase(member.get_instance_id())
	for site_id in _garrison_squads.keys():
		var list: Array = _garrison_squads[site_id]
		list.erase(squad)
		_garrison_squads[site_id] = list


func _on_squad_wiped(squad: Squad) -> void:
	if squad != null and is_instance_valid(squad):
		_squads.erase(squad)
		squad.queue_free()


func _on_soldier_died(soldier: Soldier) -> void:
	if soldier == null:
		return
	var key: int = soldier.get_instance_id()
	if _soldier_site.has(key):
		var site_id: int = _soldier_site[key]
		if soldier.faction == War.AXIS and _garrison_left.has(site_id):
			_garrison_left[site_id] = maxi(0, int(_garrison_left[site_id]) - 1)
		_soldier_site.erase(key)
	if _tracker != null and is_instance_valid(_tracker):
		# The tracker also hears about kills from the weapon code; reporting the
		# same death twice is harmless, an objective only completes once.
		_tracker.report_kill(soldier, null)


# ---------------------------------------------------------------------------
# Ambience
# ---------------------------------------------------------------------------

func _fire_ambience() -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var roll: int = _rng.randi_range(0, 99)
	var event: int = EV_ARTILLERY
	if roll < 30:
		event = EV_ARTILLERY
	elif roll < 52:
		event = EV_PLANE
	elif roll < 70:
		event = EV_CONVOY
	elif roll < 84:
		event = EV_PATROL
	else:
		event = EV_BIRDS

	if event == EV_BIRDS and _light_level() < 0.35:
		event = EV_ARTILLERY          # no birdsong at night

	match event:
		EV_ARTILLERY:
			_event_artillery()
		EV_PLANE:
			_event_plane()
		EV_CONVOY:
			_queue_patrol(true)
		EV_PATROL:
			_event_patrol_voice()
		EV_BIRDS:
			_event_birds()


func _event_artillery() -> void:
	var angle: float = _rng.randf() * TAU
	var direction := Vector3(cos(angle), 0.0, sin(angle))
	var center: Vector3 = _player_pos + direction * _rng.randf_range(280.0, 580.0)
	center = Heightfield.clamp_to_bounds(center)
	center.y = _world.ground_y(center.x, center.z)

	Sfx.play_at("distant_battle", center, -2.0, _rng.randf_range(0.85, 1.05))
	_cue("artillery_incoming", center, 0.6, -4.0, 1.0, 0.0)

	var salvo: int = _rng.randi_range(4, 7)
	for i in salvo:
		var spread := Vector3(_rng.randf_range(-60.0, 60.0), 0.0, _rng.randf_range(-60.0, 60.0))
		var at: Vector3 = Heightfield.clamp_to_bounds(center + spread)
		at.y = _world.ground_y(at.x, at.z)
		_cue("artillery_hit", at, 1.4 + float(i) * _rng.randf_range(0.5, 1.4), 2.0,
				_rng.randf_range(0.85, 1.1), _rng.randf_range(6.0, 11.0))

	event_announced.emit("Bombardement lointain %s." % _compass_word(direction))


func _event_plane() -> void:
	if _plane_left > 0.0:
		return
	_build_plane()
	if _plane == null:
		return
	var angle: float = _rng.randf() * TAU
	_plane_dir = Vector3(cos(angle), 0.0, sin(angle))
	var side: Vector3 = _plane_dir.rotated(Vector3.UP, PI * 0.5)
	var start: Vector3 = _player_pos - _plane_dir * (PLANE_RUN * 0.5) \
			+ side * _rng.randf_range(-150.0, 150.0)
	start.y = _player_pos.y + PLANE_ALTITUDE + _rng.randf_range(-25.0, 45.0)
	_plane.global_position = start
	_plane.look_at(start + _plane_dir, Vector3.UP)
	_plane.visible = true
	_plane_left = PLANE_RUN / PLANE_SPEED
	_plane_sound = 0.0
	event_announced.emit("Un appareil traverse le ciel vers %s." % _compass_word(_plane_dir))


func _event_patrol_voice() -> void:
	var best: Squad = null
	var best_distance: float = 220.0
	for squad in _squads:
		if squad == null or not is_instance_valid(squad) or squad.faction != War.AXIS:
			continue
		if squad.alive_count() <= 0 or _engaged(squad):
			continue
		var d: float = squad.center().distance_to(_player_pos)
		if d > 70.0 and d < best_distance:
			best_distance = d
			best = squad
	if best == null:
		return
	var at: Vector3 = best.center()
	for i in 3:
		_cue("german_shout", at, float(i) * _rng.randf_range(1.2, 2.4), -6.0,
				_rng.randf_range(0.85, 1.15), 0.0)


func _event_birds() -> void:
	for i in _rng.randi_range(3, 6):
		var offset := Vector3(_rng.randf_range(-38.0, 38.0), _rng.randf_range(2.0, 9.0),
				_rng.randf_range(-38.0, 38.0))
		_cue("bird", _player_pos + offset, float(i) * _rng.randf_range(0.4, 1.6), -5.0,
				_rng.randf_range(0.9, 1.25), 0.0)


func _cue(sample: String, at: Vector3, delay: float, volume: float, pitch: float,
		blast: float) -> void:
	var cue := _Cue.new()
	cue.sample = sample
	cue.position = at
	cue.delay = delay
	cue.volume = volume
	cue.pitch = pitch
	cue.blast = blast
	_cues.append(cue)


func _tick_cues(delta: float) -> void:
	if _cues.is_empty():
		return
	var i: int = _cues.size() - 1
	while i >= 0:
		var cue: _Cue = _cues[i]
		cue.delay -= delta
		if cue.delay <= 0.0:
			Sfx.play_at(cue.sample, cue.position, cue.volume, cue.pitch)
			if cue.blast > 0.0:
				var vfx: Node = _vfx()
				if vfx != null:
					vfx.explosion(cue.position + Vector3.UP * 0.6, cue.blast)
					vfx.smoke_column(cue.position, 14.0)
			_cues.remove_at(i)
		i -= 1


func _tick_plane(delta: float) -> void:
	if _plane == null or not is_instance_valid(_plane) or _plane_left <= 0.0:
		return
	_plane_left -= delta
	_plane.global_position += _plane_dir * PLANE_SPEED * delta
	_plane_sound -= delta
	if _plane_sound <= 0.0:
		_plane_sound = PLANE_SOUND_GAP
		# No engine sample exists in the bank, so the deep rumble of the distant
		# battle is pitched right down into a droning motor.
		Sfx.play_at("distant_battle", _plane.global_position, -3.0, 0.4)
	if _plane_left <= 0.0:
		_plane.visible = false


func _build_plane() -> void:
	if _plane != null and is_instance_valid(_plane):
		return
	var root := Node3D.new()
	root.name = "AmbientPlane"
	var material: Material = MatLib.get_material("metal")

	var fuselage := MeshInstance3D.new()
	var body := BoxMesh.new()
	body.size = Vector3(2.0, 2.2, 12.0)
	fuselage.mesh = body
	fuselage.material_override = material
	root.add_child(fuselage)

	var wings := MeshInstance3D.new()
	var wing := BoxMesh.new()
	wing.size = Vector3(17.0, 0.5, 2.6)
	wings.mesh = wing
	wings.position = Vector3(0.0, 0.1, 0.6)
	wings.material_override = material
	root.add_child(wings)

	var tail := MeshInstance3D.new()
	var fin := BoxMesh.new()
	fin.size = Vector3(5.0, 0.4, 1.6)
	tail.mesh = fin
	tail.position = Vector3(0.0, 0.7, -5.2)
	tail.material_override = material
	root.add_child(tail)

	root.visible = false
	add_child(root)
	_plane = root


func _compass_word(direction: Vector3) -> String:
	var angle: float = atan2(direction.x, -direction.z)
	if angle < 0.0:
		angle += TAU
	var index: int = int(round(angle / (PI * 0.25))) % 8
	match index:
		0:
			return "au nord"
		1:
			return "au nord-est"
		2:
			return "à l'est"
		3:
			return "au sud-est"
		4:
			return "au sud"
		5:
			return "au sud-ouest"
		6:
			return "à l'ouest"
	return "au nord-ouest"


func _light_level() -> float:
	var parent: Node = get_parent()
	if parent == null:
		return 1.0
	var sky: Node = parent.get_node_or_null("Sky")
	if sky != null and sky.has_method("light_level"):
		return sky.light_level()
	return 1.0


func _vfx() -> Node:
	var nodes: Array = get_tree().get_nodes_in_group("vfx")
	if nodes.is_empty():
		return null
	return nodes[0]


func _exit_tree() -> void:
	_ready_to_run = false
