## Runtime state of the campaign: which objective is available, which one is
## running, how far along it is.
##
## Zone detection is a plain per frame distance test rather than an `Area3D`.
## The objective list is around twenty five entries and only the handful that
## are active are tested, so the cost is a few dozen `distance_squared_to` per
## frame with no physics callback, no signal storm and no body ordering issue
## when the player teleports across the streaming grid.
##
## Deferred anchor resolution. `MissionDefs.build_campaign()` runs before any
## site is streamed in, so every objective starts on the centre of its host
## site. Every `_ANCHOR_INTERVAL` seconds the tracker asks
## `GameWorld.built_site()` for the sites it still needs and snaps the objective
## onto the real anchor (`"fuel"`, `"radio"`, `"flag"`, `"cage"`, `"officer"`,
## `"aa"`) the moment the site exists. The marker follows.
##
## Sound note: `objective_done` and `sector_captured` are played here only when
## nothing else listens to the matching signal. `main.gd` connects
## `objective_completed` and `War.sector_captured` and plays them itself, and
## two copies of the same sample in the same frame is an audible defect.
class_name ObjectiveTracker
extends Node

signal objective_started(obj: MissionDefs.Objective)
signal objective_progress(obj: MissionDefs.Objective, current: int, total: int)
signal objective_completed(obj: MissionDefs.Objective)
signal objective_failed(obj: MissionDefs.Objective)
signal campaign_completed()

# --- Objective states ------------------------------------------------------

const ST_LOCKED := 0
const ST_ACTIVE := 1
const ST_DONE := 2
const ST_FAILED := 3

# --- Tuning ----------------------------------------------------------------

## Seconds the player must hold a cleared zone for a capture.
const CAPTURE_HOLD := 10.0
## Seconds spent at an observation point for a recon.
const RECON_HOLD := 3.0
## Seconds holding `use` to place a demolition charge.
const PLANT_SECONDS := 4.0
## Seconds holding `use` to break the padlocks of a prison cage.
const CAGE_SECONDS := 2.5
## Fuse of a sabotage charge: long enough to walk out of the blast.
const SABOTAGE_FUSE := 12.0
## Fuse of a simple demolition (no retreat asked).
const DESTROY_FUSE := 3.5
## How far the player must be from a sabotage charge when it goes off.
const SAFE_BLAST_DISTANCE := 25.0
const BLAST_RADIUS := 11.0
const BLAST_DAMAGE := 220.0
## Seconds the player may spend outside a defended zone before it is lost.
const DEFEND_GRACE := 12.0
const DEFEND_WAVE_GAP := 38.0
const DEFEND_MAX_WAVES := 4
## A failed objective re-arms after this delay: the campaign never dead ends.
const RETRY_SECONDS := 30.0
## How close a freed prisoner must get to the friendly point to count.
const ESCORT_RADIUS := 14.0
## Distance under which an objective marker is not moved again.
const MARKER_EPSILON := 0.75

const _ENEMY_SCAN_INTERVAL := 0.35
const _ANCHOR_INTERVAL := 0.8
const _ESCORT_ORDER_INTERVAL := 1.4
## Vertical slack of a zone test: a village objective must still trigger from
## the church tower or from the bottom of a trench.
const _VERTICAL_TOLERANCE := 30.0


## Mutable per objective state. Only the scalar half is serialised.
class _Rt extends RefCounted:
	var hold: float = 0.0
	var charge: float = 0.0
	var planted: bool = false
	var fuse: float = 0.0
	var count: int = 0
	var outside: float = 0.0
	var timer: float = 0.0
	var waves: int = 0
	var wave_gap: float = 0.0
	var freed: bool = false
	var retry: float = 0.0
	var order_gap: float = 0.0
	var last_reported: int = -9999
	var target: Node3D = null
	var prisoners: Array[Node3D] = []
	var goal: Vector3 = Vector3.ZERO
	var has_goal: bool = false
	## Forced zone flag pushed by `report_player_in_zone()`.
	var forced_inside: bool = false
	var forced_valid: bool = false

	func to_dict() -> Dictionary:
		return {
			"hold": hold,
			"charge": charge,
			"planted": planted,
			"fuse": fuse,
			"count": count,
			"timer": timer,
			"waves": waves,
			"freed": freed,
		}

	func from_dict(data: Dictionary) -> void:
		hold = float(data.get("hold", 0.0))
		charge = float(data.get("charge", 0.0))
		planted = bool(data.get("planted", false))
		fuse = float(data.get("fuse", 0.0))
		count = int(data.get("count", 0))
		timer = float(data.get("timer", 0.0))
		waves = int(data.get("waves", 0))
		freed = bool(data.get("freed", false))


var _world: GameWorld = null
var _player: Player = null

var _objectives: Array = []
var _by_id: Dictionary = {}
var _state: Dictionary = {}
var _rt: Dictionary = {}

var _axis_cache: Array = []
var _scan_gap: float = 0.0
var _anchor_gap: float = 0.0

var _marker_id: int = -1
var _marker_for: int = -1
var _marker_at: Vector3 = Vector3.ZERO
var _tracked_id: int = -1
## Victims already credited, so a death reported twice counts once.
var _counted: Dictionary = {}

var _completed_all: bool = false


func _ready() -> void:
	set_process(false)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

func setup(game_world: GameWorld, player_node: Player) -> void:
	_world = game_world
	_player = player_node
	if _world == null:
		push_error("ObjectiveTracker.setup: world is null, the campaign stays empty")
		return

	var layout: Layout = _world.layout()
	if layout == null:
		push_error("ObjectiveTracker.setup: the world has no layout yet")
		return

	_objectives = MissionDefs.build_campaign(layout, _world)
	_by_id.clear()
	_state.clear()
	_rt.clear()
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		_by_id[obj.id] = obj
		_state[obj.id] = ST_LOCKED
		_rt[obj.id] = _Rt.new()

	# The war state may already know the sectors when a save is being loaded.
	if War.sector_count() == 0:
		War.register_sectors(layout.sector_ids())

	if _player != null and not _player.died.is_connected(_on_player_died):
		_player.died.connect(_on_player_died)

	_unlock_ready()
	set_process(true)


# ---------------------------------------------------------------------------
# Public queries
# ---------------------------------------------------------------------------

## Every objective the player may work on right now.
func active() -> Array:
	var out: Array = []
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) == ST_ACTIVE:
			out.append(obj)
	return out


## The objective the HUD points at: the one the player selected in the journal
## while it is still active, otherwise the closest active one.
func current() -> MissionDefs.Objective:
	if _tracked_id >= 0 and _state.get(_tracked_id, ST_LOCKED) == ST_ACTIVE:
		return _by_id.get(_tracked_id)
	var here: Vector3 = _player_position()
	var best: MissionDefs.Objective = null
	var best_distance: float = INF
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE:
			continue
		var d: float = _marker_position(obj).distance_squared_to(here)
		if d < best_distance:
			best_distance = d
			best = obj
	return best


func all_objectives() -> Array:
	return _objectives


func is_done(objective_id: int) -> bool:
	return _state.get(objective_id, ST_LOCKED) == ST_DONE


## State of one objective, for the journal and the map.
func state_of(objective_id: int) -> int:
	return _state.get(objective_id, ST_LOCKED)


func progress_of(objective_id: int) -> Vector2:
	var obj: MissionDefs.Objective = _by_id.get(objective_id)
	if obj == null:
		return Vector2.ZERO
	var rt: _Rt = _rt.get(objective_id)
	if rt == null:
		return Vector2.ZERO
	if _state.get(objective_id, ST_LOCKED) == ST_DONE:
		var total_done: int = maxi(1, _total_of(obj))
		return Vector2(float(total_done), float(total_done))
	return Vector2(float(_current_of(obj, rt)), float(_total_of(obj)))


func objective_by_id(objective_id: int) -> MissionDefs.Objective:
	return _by_id.get(objective_id)


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

## Starts an objective, or simply tracks it when it already runs. The journal
## wires its selection signal here, so selecting a running mission just moves
## the HUD marker onto it.
func start(objective_id: int) -> void:
	var obj: MissionDefs.Objective = _by_id.get(objective_id)
	if obj == null:
		return
	var state: int = _state.get(objective_id, ST_LOCKED)
	if state == ST_ACTIVE:
		_tracked_id = objective_id
		return
	if state == ST_DONE:
		return
	_state[objective_id] = ST_ACTIVE
	var rt := _Rt.new()
	rt.timer = obj.time_limit
	_rt[objective_id] = rt
	_tracked_id = objective_id
	objective_started.emit(obj)


## Unlocks every objective whose prerequisite is satisfied.
func _unlock_ready() -> void:
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_LOCKED:
			continue
		if obj.prerequisite < 0 or _state.get(obj.prerequisite, ST_LOCKED) == ST_DONE:
			var keep: int = _tracked_id
			start(obj.id)
			# Auto unlocking must not steal the marker from the player choice.
			if keep >= 0 and _state.get(keep, ST_LOCKED) == ST_ACTIVE:
				_tracked_id = keep


# ---------------------------------------------------------------------------
# Frame update
# ---------------------------------------------------------------------------

func _process(delta: float) -> void:
	if _world == null or _player == null:
		return

	_anchor_gap -= delta
	if _anchor_gap <= 0.0:
		_anchor_gap = _ANCHOR_INTERVAL
		_resolve_anchors()

	_scan_gap -= delta
	if _scan_gap <= 0.0:
		_scan_gap = _ENEMY_SCAN_INTERVAL
		_axis_cache = get_tree().get_nodes_in_group("axis")

	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		var state: int = _state.get(obj.id, ST_LOCKED)
		var rt: _Rt = _rt.get(obj.id)
		if rt == null:
			continue
		if state == ST_FAILED:
			rt.retry -= delta
			if rt.retry <= 0.0:
				var fresh := _Rt.new()
				fresh.timer = obj.time_limit
				_rt[obj.id] = fresh
				_state[obj.id] = ST_ACTIVE
				objective_started.emit(obj)
			continue
		if state != ST_ACTIVE:
			continue
		_tick_objective(obj, rt, delta)

	_update_marker()


func _tick_objective(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	match obj.kind:
		MissionDefs.O_CAPTURE:
			_tick_capture(obj, rt, delta)
		MissionDefs.O_DEFEND:
			_tick_defend(obj, rt, delta)
		MissionDefs.O_SABOTAGE:
			_tick_charge(obj, rt, delta, SABOTAGE_FUSE, true)
		MissionDefs.O_DESTROY:
			_tick_charge(obj, rt, delta, DESTROY_FUSE, false)
		MissionDefs.O_RESCUE:
			_tick_rescue(obj, rt, delta)
		MissionDefs.O_ASSASSINATE:
			_tick_assassinate(obj, rt, delta)
		MissionDefs.O_RECON:
			_tick_recon(obj, rt, delta)
		MissionDefs.O_AMBUSH:
			_tick_ambush(obj, rt, delta)


# --- Capture ---------------------------------------------------------------

func _tick_capture(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	var enemies: int = _axis_in_radius(obj.position, obj.radius + 12.0)
	var inside: bool = _player_inside(obj)
	if enemies > 0:
		# Contested: the clock crawls back down instead of resetting brutally.
		rt.hold = maxf(0.0, rt.hold - delta * 0.6)
	elif inside and _player_alive():
		rt.hold += delta
	else:
		rt.hold = maxf(0.0, rt.hold - delta)

	_emit_progress(obj, rt, mini(int(rt.hold), int(CAPTURE_HOLD)), int(CAPTURE_HOLD))
	if rt.hold >= CAPTURE_HOLD:
		_complete(obj)


# --- Defend ----------------------------------------------------------------

func _tick_defend(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	if not _player_alive():
		_fail(obj, rt)
		return

	if _player_inside(obj):
		rt.outside = 0.0
	else:
		rt.outside += delta
		if rt.outside >= DEFEND_GRACE:
			_fail(obj, rt)
			return

	var total: float = maxf(1.0, obj.time_limit)
	rt.timer = maxf(0.0, rt.timer - delta)

	rt.wave_gap -= delta
	if rt.wave_gap <= 0.0 and rt.waves < DEFEND_MAX_WAVES and rt.timer > 12.0:
		rt.wave_gap = DEFEND_WAVE_GAP
		rt.waves += 1
		_call_reinforcements(obj.position, 3 + mini(rt.waves, 3))
		War.raise_alert(War.ALERT_FULL)

	_emit_progress(obj, rt, int(total - rt.timer), int(total))
	if rt.timer <= 0.0:
		_complete(obj)


# --- Sabotage and destroy --------------------------------------------------

## Both kinds share the demolition mechanic: walk up to the anchor, hold `use`
## to place the charge, then wait for the fuse. Sabotage asks for a retreat of
## `SAFE_BLAST_DISTANCE`; a straight destruction does not, it just goes off.
## `report_destroyed()` short circuits the whole thing when another system
## (an `Emplacement` blowing up, a grenade, a scripted event) does the job.
func _tick_charge(obj: MissionDefs.Objective, rt: _Rt, delta: float,
		fuse: float, needs_retreat: bool) -> void:
	var here: Vector3 = _player_position()
	var distance: float = here.distance_to(obj.position)

	if not rt.planted:
		var reach: float = maxf(6.0, obj.radius * 0.6)
		var can_plant: bool = distance <= reach and _player_alive() and _use_held()
		if can_plant:
			rt.charge += delta
		else:
			rt.charge = maxf(0.0, rt.charge - delta * 2.0)
		_emit_progress(obj, rt, int(rt.charge / PLANT_SECONDS * 100.0), 100)
		if rt.charge >= PLANT_SECONDS:
			rt.planted = true
			rt.fuse = fuse
			Sfx.play_at("grenade_pin", obj.position, -2.0, 0.85)
			War.raise_alert(War.ALERT_SUSPICIOUS)
		return

	rt.fuse = maxf(0.0, rt.fuse - delta)
	_emit_progress(obj, rt, int(ceil(rt.fuse)), int(fuse))
	if rt.fuse > 0.0:
		return
	if needs_retreat and distance < SAFE_BLAST_DISTANCE:
		# The charge does not wait for the player. He simply eats the blast.
		push_warning("ObjectiveTracker: sabotage charge detonated with the player inside the blast")
	_detonate(obj)
	_complete(obj)


func _detonate(obj: MissionDefs.Objective) -> void:
	var at: Vector3 = obj.position + Vector3.UP * 1.0
	var vfx: Node = _vfx()
	if vfx != null:
		vfx.explosion(at, BLAST_RADIUS)
		vfx.smoke_column(at, 22.0)
	Sfx.play_at("explosion", at, 4.0, 0.9)
	Sfx.play_at("explosion_far", at, 0.0, 0.7)
	var space: World3D = _world_3d()
	if space != null:
		Ballistics.explode(space, at, BLAST_RADIUS, BLAST_DAMAGE, self)
	War.raise_alert(War.ALERT_FULL)


# --- Rescue ----------------------------------------------------------------

func _tick_rescue(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	if not rt.freed:
		var distance: float = _player_position().distance_to(obj.position)
		if distance <= maxf(6.0, obj.radius * 0.4) and _player_alive() and _use_held():
			rt.charge += delta
		else:
			rt.charge = maxf(0.0, rt.charge - delta * 2.0)
		_emit_progress(obj, rt, int(rt.charge / CAGE_SECONDS * 100.0), 100)
		if rt.charge >= CAGE_SECONDS:
			_open_cages(obj, rt)
		return

	# Escort phase: the freed men walk after the player until he brings them
	# close enough to a friendly position.
	rt.order_gap -= delta
	var goal: Vector3 = rt.goal if rt.has_goal else obj.position
	var here: Vector3 = _player_position()
	var survivors: Array[Node3D] = []
	for man in rt.prisoners:
		if man == null or not is_instance_valid(man):
			continue
		if man.has_method("is_alive") and not man.is_alive():
			continue
		if man.global_position.distance_to(goal) <= ESCORT_RADIUS:
			rt.count += 1
			if man.has_method("order_hold"):
				man.order_hold(man.global_position)
			continue
		survivors.append(man)
		if rt.order_gap <= 0.0 and man.has_method("order_move_to"):
			man.order_move_to(here)
	rt.prisoners = survivors
	if rt.order_gap <= 0.0:
		rt.order_gap = _ESCORT_ORDER_INTERVAL

	_emit_progress(obj, rt, mini(rt.count, obj.target_count), obj.target_count)
	if rt.count >= obj.target_count or rt.prisoners.is_empty():
		_complete(obj)


func _open_cages(obj: MissionDefs.Objective, rt: _Rt) -> void:
	rt.freed = true
	rt.goal = _friendly_point(obj.position)
	rt.has_goal = true
	Sfx.play_at("french_ok", obj.position, 0.0, 1.0)
	War.raise_alert(War.ALERT_SEARCHING)

	var director: Node = _director()
	var spawned: Array = []
	if director != null and director.has_method("_spawn_prisoners"):
		spawned = director._spawn_prisoners(obj.position, obj.target_count)
	for entry in spawned:
		var man: Node3D = entry
		if man != null:
			rt.prisoners.append(man)
	if rt.prisoners.is_empty():
		# No director, no bodies to escort. Degrade gracefully: opening the
		# cages is the whole mission rather than a dead end.
		rt.count = obj.target_count
		push_warning("ObjectiveTracker: no director available, rescue resolved on the cages alone")


# --- Assassinate -----------------------------------------------------------

func _tick_assassinate(obj: MissionDefs.Objective, rt: _Rt, _delta: float) -> void:
	if rt.target != null and not is_instance_valid(rt.target):
		rt.target = null
	if rt.target != null and rt.target.has_method("is_alive") and not rt.target.is_alive():
		rt.target = null
	if rt.target == null:
		rt.target = _find_officer(obj)
	_emit_progress(obj, rt, 1 if rt.target != null else 0, 1)


func _find_officer(obj: MissionDefs.Objective) -> Node3D:
	var best: Node3D = null
	var best_distance: float = obj.radius + 90.0
	for entry in _axis_cache:
		# Validity has to be tested on the raw entry: casting an already freed
		# object is itself the error, so `entry as Node3D` would have thrown
		# before any check on the result could run.
		if not is_instance_valid(entry):
			continue
		var node: Node3D = entry as Node3D
		if node == null:
			continue
		var soldier: Soldier = node as Soldier
		if soldier == null or not soldier.is_alive():
			continue
		if soldier.rank != Soldier.R_OFFICER:
			continue
		var d: float = soldier.global_position.distance_to(obj.position)
		if d < best_distance:
			best_distance = d
			best = soldier
	return best


# --- Recon -----------------------------------------------------------------

func _tick_recon(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	if _player_inside(obj) and _player_alive():
		rt.hold += delta
	else:
		rt.hold = maxf(0.0, rt.hold - delta * 1.5)
	_emit_progress(obj, rt, mini(int(rt.hold), int(RECON_HOLD)), int(RECON_HOLD))
	if rt.hold >= RECON_HOLD:
		_complete(obj)


# --- Ambush ----------------------------------------------------------------

func _tick_ambush(obj: MissionDefs.Objective, rt: _Rt, delta: float) -> void:
	# The escort is asked for once, when the player reaches the ambush spot.
	if rt.waves == 0 and _player_position().distance_to(obj.position) <= obj.radius * 2.0:
		rt.waves = 1
		_call_reinforcements(obj.position, obj.target_count + 1)
	rt.wave_gap = maxf(0.0, rt.wave_gap - delta)
	_emit_progress(obj, rt, mini(rt.count, obj.target_count), obj.target_count)
	if rt.count >= obj.target_count:
		_complete(obj)


# ---------------------------------------------------------------------------
# Reports fed by the rest of the game
# ---------------------------------------------------------------------------

func report_kill(victim: Node, killer: Node) -> void:
	if victim == null:
		return
	# The same death can be reported twice (the weapon code and the director
	# both see it), so credit a victim only once.
	var key: int = victim.get_instance_id()
	if _counted.has(key):
		return
	if _counted.size() > 256:
		_counted.clear()
	_counted[key] = true
	var victim_3d: Node3D = victim as Node3D
	var at: Vector3 = victim_3d.global_position if victim_3d != null else Vector3.ZERO
	var by_player: bool = killer == null or killer == _player
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE:
			continue
		var rt: _Rt = _rt.get(obj.id)
		if rt == null:
			continue
		if obj.kind == MissionDefs.O_ASSASSINATE:
			var is_target: bool = victim == rt.target
			if not is_target and victim is Soldier:
				var soldier: Soldier = victim
				is_target = soldier.rank == Soldier.R_OFFICER \
					and at.distance_to(obj.position) <= obj.radius + 40.0
			if is_target:
				rt.target = null
				Sfx.play_at("german_death", at, 0.0, 0.95)
				_complete(obj)
		elif obj.kind == MissionDefs.O_AMBUSH:
			if by_player and victim.is_in_group("axis") \
					and at.distance_to(obj.position) <= obj.radius + 25.0:
				rt.count += 1


## `tag` is the loose identifier of whatever blew up. An objective accepts it
## when the tag carries its own tag or its anchor key, or simply when the blast
## happened on top of the objective.
func report_destroyed(tag: String, position: Vector3) -> void:
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE:
			continue
		if obj.kind != MissionDefs.O_DESTROY and obj.kind != MissionDefs.O_SABOTAGE:
			continue
		var matched: bool = false
		if not tag.is_empty():
			if tag == obj._tag:
				matched = true
			elif not obj._anchor.is_empty() and tag.contains(obj._anchor):
				matched = true
		if not matched and position.distance_to(obj.position) <= maxf(obj.radius, 15.0):
			matched = true
		if matched:
			War.raise_alert(War.ALERT_FULL)
			_complete(obj)


func report_rescued(count: int) -> void:
	if count <= 0:
		return
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE or obj.kind != MissionDefs.O_RESCUE:
			continue
		var rt: _Rt = _rt.get(obj.id)
		if rt == null:
			continue
		rt.freed = true
		rt.count += count
		_emit_progress(obj, rt, mini(rt.count, obj.target_count), obj.target_count)
		if rt.count >= obj.target_count:
			_complete(obj)
		return


## External zone trigger. It overrides the internal distance test for that
## objective, so an `Area3D` placed by a site builder wins when it exists.
func report_player_in_zone(objective_id: int, inside: bool) -> void:
	var rt: _Rt = _rt.get(objective_id)
	if rt == null:
		return
	rt.forced_valid = true
	rt.forced_inside = inside


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

func _complete(obj: MissionDefs.Objective) -> void:
	if _state.get(obj.id, ST_LOCKED) == ST_DONE:
		return
	_state[obj.id] = ST_DONE
	var rt: _Rt = _rt.get(obj.id)
	if rt != null:
		rt.prisoners.clear()
		rt.target = null
	if _marker_for == obj.id:
		_drop_marker()
	if _tracked_id == obj.id:
		_tracked_id = -1
	if objective_completed.get_connections().is_empty():
		Sfx.play("objective_done")
	objective_completed.emit(obj)
	_unlock_ready()
	_check_sector(obj.sector_id)
	_check_campaign()


func _fail(obj: MissionDefs.Objective, rt: _Rt) -> void:
	if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE:
		return
	_state[obj.id] = ST_FAILED
	rt.retry = RETRY_SECONDS
	rt.hold = 0.0
	rt.outside = 0.0
	rt.timer = obj.time_limit
	rt.waves = 0
	rt.wave_gap = 0.0
	rt.last_reported = -9999
	if _marker_for == obj.id:
		_drop_marker()
	objective_failed.emit(obj)


func _check_sector(sector_id: int) -> void:
	if sector_id < 0 or War.is_sector_captured(sector_id):
		return
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if obj.sector_id != sector_id:
			continue
		if _state.get(obj.id, ST_LOCKED) != ST_DONE:
			return
	if War.sector_captured.get_connections().is_empty():
		Sfx.play("sector_captured")
	War.capture_sector(sector_id)


func _check_campaign() -> void:
	if _completed_all or _objectives.is_empty():
		return
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if _state.get(obj.id, ST_LOCKED) != ST_DONE:
			return
	_completed_all = true
	campaign_completed.emit()


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------

func _update_marker() -> void:
	var obj: MissionDefs.Objective = current()
	if obj == null:
		_drop_marker()
		return
	var at: Vector3 = _marker_position(obj) + Vector3.UP * 2.2
	if _marker_for != obj.id:
		_drop_marker()
		var vfx: Node = _vfx()
		if vfx == null:
			return
		_marker_id = vfx.add_marker(at, MissionDefs._marker_color(obj.kind), obj.title)
		_marker_for = obj.id
		_marker_at = at
		return
	if _marker_id >= 0 and at.distance_to(_marker_at) > MARKER_EPSILON:
		var vfx_node: Node = _vfx()
		if vfx_node != null:
			vfx_node.move_marker(_marker_id, at)
		_marker_at = at


func _drop_marker() -> void:
	if _marker_id >= 0:
		var vfx: Node = _vfx()
		if vfx != null:
			vfx.remove_marker(_marker_id)
	_marker_id = -1
	_marker_for = -1


## Where the marker sits: on the escort goal once the cages are open, on the
## officer while he is visible, on the objective otherwise.
func _marker_position(obj: MissionDefs.Objective) -> Vector3:
	var rt: _Rt = _rt.get(obj.id)
	if rt == null:
		return obj.position
	if obj.kind == MissionDefs.O_RESCUE and rt.freed and rt.has_goal:
		return rt.goal
	if obj.kind == MissionDefs.O_ASSASSINATE and rt.target != null and is_instance_valid(rt.target):
		return rt.target.global_position
	return obj.position


# ---------------------------------------------------------------------------
# Anchors
# ---------------------------------------------------------------------------

## Snaps objectives onto the real anchors of the sites that are now streamed.
func _resolve_anchors() -> void:
	if _world == null:
		return
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if obj._anchor_done or obj._site_id < 0:
			continue
		if _state.get(obj.id, ST_LOCKED) == ST_DONE:
			obj._anchor_done = true
			continue
		var built: SiteBuilder.BuiltSite = _world.built_site(obj._site_id)
		if built == null:
			continue
		obj._anchor_done = true
		if obj._anchor.is_empty():
			# No anchor wanted: still lift the objective onto a real point of
			# interest when the site published one.
			if not built.interest_points.is_empty():
				obj.position = built.interest_points[0]
			continue
		var anchor: Variant = built.objective_anchors.get(obj._anchor)
		if typeof(anchor) == TYPE_VECTOR3:
			obj.position = anchor
		elif not built.interest_points.is_empty():
			obj.position = built.interest_points[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

func _player_position() -> Vector3:
	if _player == null or not is_instance_valid(_player):
		return Vector3.ZERO
	return _player.global_position


func _player_alive() -> bool:
	return _player != null and is_instance_valid(_player) and _player.is_alive()


func _player_inside(obj: MissionDefs.Objective) -> bool:
	var rt: _Rt = _rt.get(obj.id)
	if rt != null and rt.forced_valid:
		return rt.forced_inside
	var here: Vector3 = _player_position()
	if absf(here.y - obj.position.y) > _VERTICAL_TOLERANCE:
		return false
	var dx: float = here.x - obj.position.x
	var dz: float = here.z - obj.position.z
	return dx * dx + dz * dz <= obj.radius * obj.radius


func _axis_in_radius(at: Vector3, radius: float) -> int:
	var count: int = 0
	var squared: float = radius * radius
	for entry in _axis_cache:
		# Validity has to be tested on the raw entry: casting an already freed
		# object is itself the error, so `entry as Node3D` would have thrown
		# before any check on the result could run.
		if not is_instance_valid(entry):
			continue
		var node: Node3D = entry as Node3D
		if node == null:
			continue
		if node.has_method("is_alive") and not node.is_alive():
			continue
		if node.global_position.distance_squared_to(at) <= squared:
			count += 1
	return count


func _use_held() -> bool:
	if not InputMap.has_action("use"):
		return false
	return Input.is_action_pressed("use")


func _emit_progress(obj: MissionDefs.Objective, rt: _Rt, value: int, total: int) -> void:
	if value == rt.last_reported:
		return
	rt.last_reported = value
	objective_progress.emit(obj, value, total)


func _current_of(obj: MissionDefs.Objective, rt: _Rt) -> int:
	match obj.kind:
		MissionDefs.O_CAPTURE:
			return mini(int(rt.hold), int(CAPTURE_HOLD))
		MissionDefs.O_RECON:
			return mini(int(rt.hold), int(RECON_HOLD))
		MissionDefs.O_DEFEND:
			return int(maxf(0.0, obj.time_limit - rt.timer))
		MissionDefs.O_RESCUE:
			return mini(rt.count, obj.target_count)
		MissionDefs.O_AMBUSH:
			return mini(rt.count, obj.target_count)
		MissionDefs.O_SABOTAGE, MissionDefs.O_DESTROY:
			if rt.planted:
				return 100
			return int(rt.charge / PLANT_SECONDS * 100.0)
	return 0


func _total_of(obj: MissionDefs.Objective) -> int:
	match obj.kind:
		MissionDefs.O_CAPTURE:
			return int(CAPTURE_HOLD)
		MissionDefs.O_RECON:
			return int(RECON_HOLD)
		MissionDefs.O_DEFEND:
			return int(obj.time_limit)
		MissionDefs.O_RESCUE, MissionDefs.O_AMBUSH:
			return obj.target_count
		MissionDefs.O_SABOTAGE, MissionDefs.O_DESTROY:
			return 100
	return 1


## Closest liberated sector, falling back to the drop zone village.
func _friendly_point(from: Vector3) -> Vector3:
	var layout: Layout = _world.layout() if _world != null else null
	if layout == null:
		return from
	var best: Vector3 = Vector3.ZERO
	var best_distance: float = INF
	var found: bool = false
	for site in layout.sites:
		if not site.is_sector or not War.is_sector_captured(site.id):
			continue
		var pos := Vector3(site.center.x, site.ground, site.center.y)
		var d: float = pos.distance_to(from)
		if d < best_distance:
			best_distance = d
			best = pos
			found = true
	if found:
		return best
	var spawn: Vector2 = layout.spawn_point()
	return Vector3(spawn.x, _world.ground_y(spawn.x, spawn.y), spawn.y)


func _call_reinforcements(pos: Vector3, count: int) -> void:
	var director: Node = _director()
	if director != null and director.has_method("send_reinforcements"):
		director.send_reinforcements(pos, count)


func _director() -> Node:
	var nodes: Array = get_tree().get_nodes_in_group("director")
	if not nodes.is_empty():
		return nodes[0]
	var parent: Node = get_parent()
	if parent != null:
		return parent.get_node_or_null("Director")
	return null


func _vfx() -> Node:
	var nodes: Array = get_tree().get_nodes_in_group("vfx")
	if nodes.is_empty():
		return null
	return nodes[0]


func _world_3d() -> World3D:
	if _player != null and is_instance_valid(_player):
		return _player.get_world_3d()
	if _world != null and is_instance_valid(_world):
		return _world.get_world_3d()
	return null


func _on_player_died() -> void:
	# Only a defence can be lost by dying: everything else simply waits.
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		if obj.kind != MissionDefs.O_DEFEND:
			continue
		if _state.get(obj.id, ST_LOCKED) != ST_ACTIVE:
			continue
		var rt: _Rt = _rt.get(obj.id)
		if rt != null:
			_fail(obj, rt)


func debug_line() -> String:
	var done: int = 0
	for entry in _objectives:
		if _state.get((entry as MissionDefs.Objective).id, ST_LOCKED) == ST_DONE:
			done += 1
	return "Objectifs %d/%d, actifs %d" % [done, _objectives.size(), active().size()]


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------

func to_dict() -> Dictionary:
	var states: Dictionary = {}
	var runtime: Dictionary = {}
	var positions: Dictionary = {}
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		var key: String = str(obj.id)
		states[key] = int(_state.get(obj.id, ST_LOCKED))
		var rt: _Rt = _rt.get(obj.id)
		if rt != null:
			runtime[key] = rt.to_dict()
		if obj._anchor_done:
			positions[key] = [obj.position.x, obj.position.y, obj.position.z]
	return {
		"version": 1,
		"tracked": _tracked_id,
		"completed": _completed_all,
		"states": states,
		"runtime": runtime,
		"positions": positions,
	}


func from_dict(data: Dictionary) -> void:
	if data.is_empty():
		return
	var states: Dictionary = data.get("states", {})
	var runtime: Dictionary = data.get("runtime", {})
	var positions: Dictionary = data.get("positions", {})
	_drop_marker()
	for entry in _objectives:
		var obj: MissionDefs.Objective = entry
		var key: String = str(obj.id)
		if states.has(key):
			_state[obj.id] = int(states[key])
		var rt := _Rt.new()
		rt.timer = obj.time_limit
		if runtime.has(key):
			rt.from_dict(runtime[key])
		# Node references never survive a save.
		rt.prisoners.clear()
		rt.target = null
		if obj.kind == MissionDefs.O_RESCUE and rt.freed and rt.count < obj.target_count:
			# The escort cannot be restored, so credit what was already earned
			# and let the player open the cages again.
			rt.freed = false
			rt.charge = 0.0
		_rt[obj.id] = rt
		if positions.has(key):
			var raw: Array = positions[key]
			if raw.size() == 3:
				obj.position = Vector3(float(raw[0]), float(raw[1]), float(raw[2]))
				obj._anchor_done = true
	_tracked_id = int(data.get("tracked", -1))
	_completed_all = bool(data.get("completed", false))
	_unlock_ready()
