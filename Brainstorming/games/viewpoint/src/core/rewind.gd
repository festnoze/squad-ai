class_name Rewind
extends Node
## Time rewind, held on R. Two tracks, because a level changes in two very
## different ways:
##
## - MOTION, continuous: the player and the loose rigid bodies. Sampled at a
##   fixed rate into a ring of snapshots, replayed backwards with interpolation.
## - STRUCTURE, discrete and rare: a photo placed, a wall carved, a cage
##   broken, a battery taken. Recorded as timestamped events.
##
## The structural side is exact rather than reconstructed: while a level is
## running NOTHING is really freed. A "destroyed" node is pulled out of the
## tree into a graveyard, which takes it out of every group and out of physics
## just like a free would, but keeps it whole. Undoing is putting it back.
## Nodes only die for good when their event falls out of the history window.
##
## The counters (batteries, film) and the held photo ride along in the motion
## snapshots, so they rewind with everything else.

static var instance: Rewind

## Motion snapshots per second. 20 Hz is invisible at rewind speed and cheap:
## a snapshot is the player plus a handful of rigid bodies.
const SAMPLE_HZ := 20.0
## History ceiling, about five minutes. Older samples (and the events they
## covered) are dropped, which is also when retired nodes are truly freed.
const MAX_SAMPLES := 6000
## Seconds of history undone per second of holding R.
const REWIND_SPEED := 2.5

var _player: Player
var _level_root: Node3D
var _graveyard: Node

## Motion track, oldest first. Each entry is the dictionary built by _capture.
var _samples: Array = []
## Structural track, oldest first: {t, kind, node, parent, index}.
var _events: Array = []
## Rigid bodies whose transform must be recorded (placed crates, batteries).
var _tracked: Array[RigidBody3D] = []

var _time := 0.0
var _since_sample := 0.0
var _rewinding := false
## Playback head while rewinding, in the same clock as _time.
var _cursor := 0.0


func _ready() -> void:
	instance = self
	# Deliberately NOT a child of this node: an orphan holds its children
	# alive but OUTSIDE the SceneTree, which is what takes a retired node out
	# of every group query and out of physics, exactly like a free would.
	_graveyard = Node.new()
	_graveyard.name = "Graveyard"


func _exit_tree() -> void:
	if is_instance_valid(_graveyard):
		_graveyard.free()
	_graveyard = null


func setup(player: Player, level_root: Node3D) -> void:
	_player = player
	_level_root = level_root


## Called once the new level is built and Game holds its counters: the history
## restarts from this state and nothing of the previous level survives.
func begin_level() -> void:
	_rewinding = false
	_samples.clear()
	_events.clear()
	_tracked.clear()
	for node in _graveyard.get_children():
		_graveyard.remove_child(node)
		node.free()
	_time = 0.0
	_since_sample = 0.0
	_cursor = 0.0
	_samples.append(_capture())


func is_rewinding() -> bool:
	return _rewinding


## Size of each track, for the probe and for tuning.
func sample_count() -> int:
	return _samples.size()


func event_count() -> int:
	return _events.size()


## How far back the history can still go, in seconds.
func available_seconds() -> float:
	if _samples.is_empty():
		return 0.0
	return maxf(0.0, (_cursor if _rewinding else _time) - float(_samples[0]["t"]))


# --- Recording ---------------------------------------------------------------


## Recording rides the physics clock, not the render clock: its delta is fixed,
## so the history means the same thing whatever the frame rate does.
func _physics_process(delta: float) -> void:
	if _rewinding or _player == null:
		return
	_time += delta
	_since_sample += delta
	if _since_sample < 1.0 / SAMPLE_HZ:
		return
	_since_sample = 0.0
	_samples.append(_capture())
	_trim()


## Registers a rigid body whose motion must be rewindable.
static func track_body(body: RigidBody3D) -> void:
	if instance != null and not instance._tracked.has(body):
		instance._tracked.append(body)


## Records a node that just appeared. Undoing its creation retires it.
static func notice_spawn(node: Node) -> void:
	if instance == null or instance._rewinding:
		return
	instance._events.append({
		"t": instance._time,
		"kind": "spawn",
		"node": node,
		"parent": node.get_parent(),
		"index": node.get_index(),
	})


## Destroys a node the rewindable way: out of the tree, into the graveyard,
## so it leaves every group and the physics world but stays whole. Falls back
## to a plain queue_free when no rewind is running (unit tests, tooling).
static func retire(node: Node) -> void:
	if node == null or not is_instance_valid(node):
		return
	if instance == null or not is_instance_valid(instance):
		node.queue_free()
		return
	instance._retire(node)


func _retire(node: Node) -> void:
	var parent := node.get_parent()
	if parent == null:
		return
	if not _rewinding:
		_events.append({
			"t": _time,
			"kind": "retire",
			"node": node,
			"parent": parent,
			"index": node.get_index(),
		})
	parent.remove_child(node)
	_graveyard.add_child(node)
	if node is Node3D:
		# A retired node keeps its place: putting it back must not move it.
		node.set_meta("rewind_transform", (node as Node3D).transform)


func _capture() -> Dictionary:
	var bodies := {}
	for body in _tracked:
		if is_instance_valid(body) and body.is_inside_tree():
			var t := body.global_transform
			var q := t.basis.get_rotation_quaternion()
			bodies[body.get_instance_id()] = PackedFloat32Array([
				t.origin.x, t.origin.y, t.origin.z, q.x, q.y, q.z, q.w
			])
	return {
		"t": _time,
		"pos": _player.global_position,
		"yaw": _player.rotation.y,
		"pitch": _player.camera.rotation.x,
		"carried": Game.carried_batteries,
		"sealed": Game.carried_sealed,
		"inserted": Game.inserted_batteries,
		"required": Game.required_batteries,
		"films": Game.camera_films,
		"held": _player.placer.held_id,
		"roll": _player.placer.roll_steps,
		"bodies": bodies,
	}


## Drops history beyond the ceiling. Events that fall out can never be undone
## again, so the nodes they retired are freed for real here.
func _trim() -> void:
	if _samples.size() <= MAX_SAMPLES:
		return
	_samples = _samples.slice(_samples.size() - MAX_SAMPLES)
	var horizon: float = _samples[0]["t"]
	var kept: Array = []
	for event in _events:
		if float(event["t"]) >= horizon:
			kept.append(event)
			continue
		var node: Node = event["node"]
		if event["kind"] == "retire" and is_instance_valid(node) and node.get_parent() == _graveyard:
			_graveyard.remove_child(node)
			node.free()
	_events = kept


# --- Playback ----------------------------------------------------------------


func start_rewind() -> void:
	if _rewinding or _samples.is_empty():
		return
	_rewinding = true
	_cursor = _time
	for body in _tracked:
		if is_instance_valid(body):
			body.freeze = true


## Walks the playback head back by delta seconds of holding.
func step_rewind(delta: float) -> void:
	if not _rewinding:
		return
	_cursor = maxf(_cursor - delta * REWIND_SPEED, float(_samples[0]["t"]))
	_undo_events_after(_cursor)
	_apply(sample_at(_samples, _cursor))


func stop_rewind() -> void:
	if not _rewinding:
		return
	# The rewound future is gone: history restarts from the playback head.
	var index := locate(_samples, _cursor)
	_samples = _samples.slice(0, index + 1)
	_samples.append(_capture_at(_cursor))
	_time = _cursor
	_since_sample = 0.0
	_rewinding = false
	for body in _tracked:
		if is_instance_valid(body):
			body.freeze = false


func _undo_events_after(t: float) -> void:
	while not _events.is_empty() and float(_events[_events.size() - 1]["t"]) > t:
		var event: Dictionary = _events.pop_back()
		var node: Node = event["node"]
		if not is_instance_valid(node):
			continue
		if event["kind"] == "spawn":
			_retire(node)
		else:
			_revive(node, event["parent"], int(event["index"]))


func _revive(node: Node, parent: Node, index: int) -> void:
	if not is_instance_valid(parent):
		return
	if node.get_parent() != null:
		node.get_parent().remove_child(node)
	parent.add_child(node)
	if index >= 0 and index < parent.get_child_count():
		parent.move_child(node, index)
	if node is Node3D and node.has_meta("rewind_transform"):
		(node as Node3D).transform = node.get_meta("rewind_transform")


func _apply(state: Dictionary) -> void:
	if state.is_empty() or _player == null:
		return
	_player.global_position = state["pos"]
	_player.rotation = Vector3(0, state["yaw"], 0)
	_player.camera.rotation.x = state["pitch"]
	_player.velocity = Vector3.ZERO
	Game.restore_counters(state["carried"], state["inserted"], state["required"], state["films"], state.get("sealed", 0))
	_player.placer.restore_held(state["held"], state["roll"])
	var bodies: Dictionary = state["bodies"]
	for body in _tracked:
		if not is_instance_valid(body) or not body.is_inside_tree():
			continue
		var id := body.get_instance_id()
		if not bodies.has(id):
			continue
		var raw: PackedFloat32Array = bodies[id]
		var q := Quaternion(raw[3], raw[4], raw[5], raw[6]).normalized()
		body.global_transform = Transform3D(Basis(q), Vector3(raw[0], raw[1], raw[2]))
		body.linear_velocity = Vector3.ZERO
		body.angular_velocity = Vector3.ZERO


## Snapshot of the playback head, used to restart the history on release.
func _capture_at(t: float) -> Dictionary:
	var state := sample_at(_samples, t).duplicate()
	state["t"] = t
	return state


# --- Pure helpers, unit tested ----------------------------------------------


## Index of the last sample at or before t (0 when t precedes the history).
static func locate(samples: Array, t: float) -> int:
	if samples.is_empty():
		return -1
	var low := 0
	var high := samples.size() - 1
	while low < high:
		var mid := (low + high + 1) / 2
		if float(samples[mid]["t"]) <= t:
			low = mid
		else:
			high = mid - 1
	return low


## State at an arbitrary time: the bracketing samples blended for the smooth
## fields, the discrete ones taken from the earlier sample (a battery is
## picked up at one instant, it is never half picked up).
static func sample_at(samples: Array, t: float) -> Dictionary:
	var index := locate(samples, t)
	if index < 0:
		return {}
	var before: Dictionary = samples[index]
	if index + 1 >= samples.size():
		return before
	var after: Dictionary = samples[index + 1]
	var span: float = float(after["t"]) - float(before["t"])
	var ratio := 0.0 if span <= 0.0 else clampf((t - float(before["t"])) / span, 0.0, 1.0)
	var blended := before.duplicate()
	blended["t"] = t
	blended["pos"] = (before["pos"] as Vector3).lerp(after["pos"], ratio)
	blended["yaw"] = lerp_angle(before["yaw"], after["yaw"], ratio)
	blended["pitch"] = lerpf(before["pitch"], after["pitch"], ratio)
	return blended
