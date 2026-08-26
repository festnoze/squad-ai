## The ball, integrated by hand at 120 Hz through `Aero`.
##
## Why not a RigidBody3D: Godot's solver has linear damping, not quadratic drag,
## and no Magnus force at all. A penalty without Magnus is not a penalty, and a
## penalty without the drag crisis flies about a metre too far. So the state
## (position, velocity, spin) lives here and every step goes through `Aero`.
##
## `_physics_process` runs exactly the ordered sequence the contract lists, and
## the order is load bearing:
##   1. one `Aero.integrate` step,
##   2. `Field.sweep_frame` over the segment travelled, bounce if it hits,
##   3. the segment is offered to the keeper (see `probe_keeper` below),
##   4. the goal plane, then the net panels, then the ground,
##   5. the visual mesh is rotated by the spin.
##
## Sub stepping: a step is not resolved in one shot. Within one physics step the
## four tests above are run in that order over a segment that is TRUNCATED by
## each event as it is found, so the earliest event wins and no test can react to
## a part of the path the ball never reached. The ball is then advanced to the
## contact point, reflected by `Aero.bounce`, and the REMAINDER of the step is
## integrated again. Without that remainder, a ball that clips a post would sit
## motionless for a frame, which reads as a bug. It also means rebounds count: a
## shot off the post that then crosses the line is a goal, so no verdict is ever
## latched here on frame contact. This module reports events, it never judges.
##
## Spin is integrated as a real rotation: each sub step builds a quaternion from
## the angular velocity vector and composes it on the left of the accumulated
## basis. The panels of the truncated icosahedron therefore spin about the true
## axis, which is how the player reads the curve in flight. A fixed axis fake
## would be visibly wrong the moment side spin and back spin are mixed.
##
## Keeper handshake: the ball must ask a question and get an answer inside the
## same physics step, which a plain signal cannot do. Both routes are supported,
## and `Main` picks one:
##   - assign `keeper_probe` a Callable of the shape
##     `func(from: Vector3, to: Vector3) -> Dictionary` (typically
##     `keeper.attempt_save`), or
##   - connect `probe_keeper` and call `report_save()` from the handler. Signal
##     emission is synchronous, so the answer is back before `emit` returns.
##
## A SAVE IS A PHYSICAL EVENT, and this is the file that makes it one. The answer
## carries a "catch" flag, and the two outcomes could not be more different:
##
##   - a CATCH ends the flight. The ball stops dead, its spin goes to zero and it
##     is HELD: from that step on it is not integrated at all, it simply sits
##     where `keeper_hold` says the gloves are, every physics step, for the rest
##     of the dive, the landing and the celebration. An integrated ball would
##     drift out of the hand within a frame, which is why `held` is a state and
##     not a velocity of zero.
##
##   - a PARRY puts the ball back into play, and it is given a floor: whatever
##     the reflection says, a parried ball ALWAYS leaves the contact travelling
##     back up the pitch. See `_parry`. A glove that only grazes the ball and
##     leaves it drifting into the net is the exact frame that makes a correct
##     ARRET verdict look like a broken game.
##
## Before any of this the ball never asked the keeper anything at all: nothing
## ever assigned `keeper_probe`, the whole branch below was dead, and a saved
## penalty carried on into the net while the scoreboard said "arret".
class_name Ball
extends Node3D

signal struck(velocity: Vector3, spin: Vector3)
signal frame_hit(part: int, point: Vector3, speed: float)
signal net_hit(point: Vector3, velocity: Vector3)
signal ground_hit(point: Vector3, speed: float)
signal crossed_line(point: Vector3, inside: bool)
signal came_to_rest()
## Emitted once per resolved sub segment while flying, when no `keeper_probe`
## Callable is set. The handler answers with `report_save()`.
signal probe_keeper(from: Vector3, to: Vector3)

## Restitution and friction per surface. The frame value is the one the contract
## quotes for `Aero.bounce`; the net barely gives anything back.
const FRAME_RESTITUTION := 0.75
const FRAME_FRICTION := 0.32
const TURF_RESTITUTION := 0.45
const TURF_FRICTION := 0.42
const NET_RESTITUTION := 0.12
const NET_FRICTION := 0.72
const GLOVE_RESTITUTION := 0.50
const GLOVE_FRICTION := 0.55

## Pushed off a surface by this much after a bounce so the next sweep starts
## outside it, otherwise a grazing contact can retrigger for ever.
const SEPARATION := 0.004
## Hard cap on contacts resolved inside one physics step.
const MAX_SUBSTEPS := 6
## Below this speed on the ground the ball is considered at rest, m/s.
const REST_SPEED := 0.32
## Rolling resistance of mown turf, m/s2.
const ROLL_DECEL := 1.75
## How fast a rolling ball's spin is dragged onto the pure rolling spin, per
## second. About a quarter of a second of memory.
const ROLL_SPIN_RATE := 4.0
## A vertical impact slower than this is a settle, not a bounce, and stays quiet.
const BOUNCE_MIN_SPEED := 0.38
## The flight is abandoned after this many seconds, whatever happened.
const MAX_FLIGHT_TIME := 12.0
## Hard cap on the flight log, so a stuck ball cannot eat memory.
const MAX_LOG := 4096
## The keeper is only asked about segments this close to the line, m.
const KEEPER_PROBE_Z := 8.0
## Minimum speed back up the pitch, m/s, a parried ball leaves the glove with.
## Deliberately modest: this is a floor that stops a graze from trickling in, not
## a cannon that fires every deflection to the halfway line.
const PARRY_MIN_Z := 2.6
## How the momentum taken out of the -Z direction is paid back, as a fraction of
## the correction: sideways (wide of the post) and upwards (over the bar). They
## are what makes a parry look like a parry rather than like a wall bounce.
const PARRY_SPREAD := 0.60
const PARRY_LIFT := 0.42
## Physics steps without a seek_replay() call after which a held ball goes back
## to tracking the glove itself. Same handover as Keeper.REPLAY_HANDOVER, and for
## the same reason: the playhead is scrubbed from _process, so several physics
## steps can pass between two calls and the two writers must not fight.
const REPLAY_HANDOVER := 12
## Sampling step of `predict`. Coarser than the physics step on purpose: the HUD
## arc wants a metre or so of ground covered per point, not eight milliseconds.
const PREVIEW_DELTA := 1.0 / 60.0
const TIME_EPS := 1.0e-6

var velocity: Vector3 = Vector3.ZERO
var spin: Vector3 = Vector3.ZERO
var flying: bool = false
## True while the ball is in the keeper's gloves. `flying` is false at the same
## time: a held ball is not in flight, it is furniture attached to a hand. It is
## cleared by `place_on_spot()` and by `halt()`, so no attempt can ever start
## with the ball still stuck to the previous dive.
var held: bool = false
## Filled while flying, one entry per physics step: {"t", "position", "spin"}.
var flight_log: Array[Dictionary] = []
## Steady wind, shared with every `Aero` call so the preview matches the flight.
var wind: Vector3 = Vector3.ZERO
## Set by `Main`, or found among the siblings by `build()`.
var goal_frame: GoalFrame = null
var pitch: Pitch = null
## Optional synchronous keeper query, see the file docstring.
var keeper_probe: Callable = Callable()
## Where the gloves are, asked every physics step while the ball is held.
## Shape: `func() -> Vector3`, typically `keeper.hold_point`. When it is not set
## a catch degrades to a parry, because a ball with nothing to hold on to would
## simply hang in the air.
var keeper_hold: Callable = Callable()

var _mesh: MeshInstance3D = null
var _trail: BallTrail = null
var _pos: Vector3 = Field.SPOT
var _spin_basis: Basis = Basis.IDENTITY
## Visual basis per logged step, so the replay shows the same rotation.
var _log_basis: Array[Basis] = []
var _elapsed: float = 0.0
var _log_delta: float = 1.0 / 120.0
var _launch_position: Vector3 = Field.SPOT
var _launch_velocity: Vector3 = Vector3.ZERO
var _built: bool = false
var _rest_emitted: bool = true
var _plane_reported: bool = false
var _rolling: bool = false
var _curve_index: int = -1
var _curve_value: float = 0.0
var _curve_log_size: int = -1
var _pending_save: Dictionary = {}
var _has_pending_save: bool = false
var _replay_last_t: float = -1.0
var _net_panels: Array[Dictionary] = []
## Physics frame of the last seek_replay() call, see REPLAY_HANDOVER.
var _replay_frame: int = -1000


func _ready() -> void:
	build()


## Creates the mesh, the trail and the net panel table. Idempotent.
func build() -> void:
	if not _built:
		_built = true
		_build_net_panels()
		_mesh = MeshInstance3D.new()
		_mesh.name = "BallMesh"
		_mesh.mesh = Meshes.ball_mesh(2)
		_mesh.material_override = Mats.ball()
		_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		add_child(_mesh)
		_trail = BallTrail.new()
		_trail.name = "Trail"
		add_child(_trail)
		_trail.build()
		place_on_spot()
	_autowire()


## Puts the ball back on the spot, at rest, log cleared.
func place_on_spot() -> void:
	_pos = Field.SPOT
	velocity = Vector3.ZERO
	spin = Vector3.ZERO
	flying = false
	_release()
	_rolling = false
	_elapsed = 0.0
	_launch_position = _pos
	_launch_velocity = Vector3.ZERO
	_spin_basis = Basis.IDENTITY
	flight_log.clear()
	_log_basis.clear()
	# Nothing is in flight, so there is nothing left to come to rest from.
	_rest_emitted = true
	_plane_reported = false
	_replay_last_t = -1.0
	_invalidate_curve()
	_apply_transform()
	if _trail != null:
		_trail.clear()


## Launches it. Starts the flight log and emits `struck`.
func strike(new_velocity: Vector3, new_spin: Vector3) -> void:
	if not _built:
		build()
	velocity = new_velocity
	spin = new_spin
	flying = true
	_release()
	_rolling = false
	_elapsed = 0.0
	_log_delta = 1.0 / maxf(1.0, float(Engine.physics_ticks_per_second))
	_launch_position = _pos
	_launch_velocity = new_velocity
	flight_log.clear()
	_log_basis.clear()
	_rest_emitted = false
	_plane_reported = false
	_replay_last_t = -1.0
	_invalidate_curve()
	if _trail != null:
		_trail.clear()
	_record_log()
	struck.emit(new_velocity, new_spin)


## Freezes the ball where it is, without clearing the log. A held ball is LET GO
## by this call and left exactly where the gloves had it, which is why `Main`
## does not halt a ball the keeper is holding: it would hang in the air while he
## stands up and walks the hands away from it.
func halt() -> void:
	flying = false
	_release()
	_rolling = false
	velocity = Vector3.ZERO
	spin = Vector3.ZERO


## Puts the ball in the keeper's gloves and keeps it there. `anchor` is a
## `func() -> Vector3` giving the current world point the ball sits at, asked
## again every physics step: nothing is parented, so this works identically on
## the imported figure and on the procedural fallback.
##
## The flight ends here. `flying` goes false so every caller that waits on a
## settled ball settles, and `held` goes true so `_physics_process` stops
## integrating rather than merely integrating a zero velocity, which would still
## let gravity pull the ball out of the hand within two frames.
func hold(anchor: Callable) -> void:
	if not anchor.is_valid():
		return
	keeper_hold = anchor
	held = true
	flying = false
	_rolling = false
	velocity = Vector3.ZERO
	spin = Vector3.ZERO
	_note_curve_cut()
	if _trail != null:
		_trail.clear()
	_track_hold()
	_record_log()
	if not _rest_emitted:
		_rest_emitted = true
		came_to_rest.emit()


## Drops the hold without moving the ball.
func _release() -> void:
	held = false


## Seconds since the strike, 0 when not flying.
func flight_time() -> float:
	if not flying:
		return 0.0
	return _elapsed


## Answer to `probe_keeper`, expected to be called from inside the handler.
## `result` is the dictionary returned by `KeeperBrain.try_save`.
func report_save(result: Dictionary) -> void:
	_pending_save = result
	_has_pending_save = true


func _physics_process(delta: float) -> void:
	if held:
		_advance_hold(delta)
		return
	if not flying:
		return
	_elapsed += delta
	_advance(delta)
	if held:
		# The flight ended in the gloves. hold() has already placed and logged the
		# ball, and nothing below applies to a ball that is being carried.
		return
	# Spin decay is applied once per physics step, never per sub step: a decay
	# applied twice down the chain would eat the curve.
	spin = Aero.decay_spin(spin, delta)
	_settle(delta)
	_apply_transform()
	_record_log()
	if _trail != null:
		_trail.push(_pos, velocity.length())
	if flying and (Field.is_out_of_area(_pos) or _elapsed > MAX_FLIGHT_TIME):
		_finish_flight()


# --- the held ball -----------------------------------------------------------


## One step of a ball that is in the gloves. No integration at all: the position
## is whatever the hand says.
##
## The log KEEPS RUNNING for the whole hold, and that is deliberate: the keeper
## records his body for exactly as long as he is holding the ball, so the two
## logs cover the same window and a replay scrubbed to any point inside it shows
## the hand and the ball in the same place. Stop one of them early and the replay
## of a catch ends with the ball hanging in the air while the man walks off.
func _advance_hold(delta: float) -> void:
	# The replay playhead owns the ball while it is being scrubbed. Same handover
	# as the keeper's body, and without it the two would fight over the position
	# every other frame.
	if Engine.get_physics_frames() - _replay_frame < REPLAY_HANDOVER:
		return
	if not keeper_hold.is_valid():
		return
	_elapsed += delta
	_track_hold()
	_record_log()


## Asks the hand where it is and puts the ball there. A hand that answers with
## something that is not a finite Vector3 simply leaves the ball where it was.
func _track_hold() -> void:
	if not keeper_hold.is_valid():
		return
	var answer: Variant = keeper_hold.call()
	if not (answer is Vector3):
		return
	var point: Vector3 = answer
	if not point.is_finite():
		return
	_pos = point
	_apply_transform()


# --- integration and collisions ----------------------------------------------


func _advance(delta: float) -> void:
	var remaining: float = delta
	var guard: int = 0
	while remaining > TIME_EPS and guard < MAX_SUBSTEPS and flying:
		guard += 1
		var from_pos: Vector3 = _pos
		var stepped: Array = Aero.integrate(from_pos, velocity, spin, wind, remaining)
		var to_pos: Vector3 = stepped[0]
		var to_vel: Vector3 = stepped[1]

		var event: Dictionary = _first_event(from_pos, to_pos)
		var kind: String = String(event.get("kind", ""))
		var fraction: float = 1.0
		if not kind.is_empty():
			fraction = clampf(float(event.get("t", 1.0)), 0.0, 1.0)
		var used: float = remaining * fraction
		var contact: Vector3 = from_pos.lerp(to_pos, fraction)

		# The goal plane is a report, not a collision, so it is answered for the
		# part of the path actually travelled during this sub step.
		_report_plane(from_pos, contact)
		# Step 5 of the sequence, applied over the time really consumed.
		_rotate_visual(used)

		if kind.is_empty():
			_pos = to_pos
			velocity = to_vel
			remaining = 0.0
			break

		# Velocity at contact. Over an eight millisecond step the velocity curve
		# is straight to well under a millimetre per second, so a lerp is exact
		# enough here and saves a second RK4 pass.
		var v_in: Vector3 = velocity.lerp(to_vel, fraction)
		var normal: Vector3 = (event.get("normal", Vector3.UP) as Vector3).normalized()
		if normal.length_squared() < 0.5:
			normal = Vector3.UP
		var speed_in: float = v_in.length()

		# A clean catch is not a bounce. It is the end of the flight, so it is
		# resolved before Aero ever sees the contact.
		if kind == "keeper" and bool(event.get("catch", false)) and keeper_hold.is_valid():
			_pos = contact
			_note_curve_cut()
			hold(keeper_hold)
			return

		var reflected: Array = Aero.bounce(
			v_in, spin, normal,
			float(event.get("restitution", 0.5)),
			float(event.get("friction", 0.4))
		)
		velocity = reflected[0]
		spin = reflected[1]
		if kind == "keeper":
			velocity = _parry(velocity, contact, normal)
		_pos = contact + normal * SEPARATION
		_note_curve_cut()
		_emit_event(event, contact, v_in, speed_in)
		remaining -= maxf(used, TIME_EPS)


## Runs the four collision tests over a segment truncated by each event found,
## and returns the earliest one. Ties go to the keeper, then to the earlier test.
##
## The keeper is asked LAST, and that is not the same thing as the keeper coming
## last. Every other test only narrows the segment; the keeper's question has a
## SIDE EFFECT, because answering it is what makes him claim the save, play his
## sound and latch the verdict. So he is asked once the segment has been cut down
## to the part of the path the ball genuinely reaches, and if he touched it there
## he wins outright: his contact is inside a window that already ends at the
## first solid thing. Ask him earlier, as this used to, and a ball that clips the
## turf 3 mm before the glove is claimed as a save the ball then bounces away
## from, which is the same disagreement between the verdict and the picture that
## this whole pass exists to remove.
func _first_event(from_pos: Vector3, to_pos: Vector3) -> Dictionary:
	var event: Dictionary = _no_event()
	var end_t: float = 1.0
	var end_pos: Vector3 = to_pos

	# 1. The goal frame.
	var sweep: Dictionary = Field.sweep_frame(from_pos, to_pos)
	if bool(sweep.get("hit", false)):
		var frame_t: float = clampf(float(sweep.get("t", 0.0)), 0.0, 1.0)
		event = {
			"kind": "frame",
			"t": frame_t,
			"point": sweep.get("point", from_pos.lerp(to_pos, frame_t)),
			"normal": sweep.get("normal", Vector3.UP),
			"part": int(sweep.get("part", Field.FRAME_NONE)),
			"limb": "",
			"restitution": FRAME_RESTITUTION,
			"friction": FRAME_FRICTION,
		}
		end_t = frame_t
		end_pos = from_pos.lerp(to_pos, frame_t)

	# 2. The net panels.
	var net_event: Dictionary = _net_event(from_pos, end_pos)
	if bool(net_event.get("hit", false)):
		var net_t: float = float(net_event.get("t", 1.0)) * end_t
		event = {
			"kind": "net",
			"t": net_t,
			"point": net_event.get("point", end_pos),
			"normal": net_event.get("normal", Vector3.FORWARD),
			"part": Field.FRAME_NONE,
			"limb": "",
			"restitution": NET_RESTITUTION,
			"friction": NET_FRICTION,
		}
		end_t = net_t
		end_pos = from_pos.lerp(to_pos, net_t)

	# 3. The turf.
	var ground: Dictionary = _ground_event(from_pos, end_pos)
	if bool(ground.get("hit", false)):
		var ground_t: float = float(ground.get("t", 1.0)) * end_t
		event = {
			"kind": "ground",
			"t": ground_t,
			"point": ground.get("point", end_pos),
			"normal": Vector3.UP,
			"part": Field.FRAME_NONE,
			"limb": "",
			"restitution": TURF_RESTITUTION,
			"friction": TURF_FRICTION,
		}
		end_t = ground_t
		end_pos = from_pos.lerp(to_pos, ground_t)

	# 4. The keeper, over the part of the path the ball actually reaches.
	var save: Dictionary = _probe_keeper(from_pos, end_pos)
	if bool(save.get("saved", false)):
		var glove_point: Vector3 = save.get("point", end_pos)
		var glove_t: float = _segment_fraction(from_pos, end_pos, glove_point) * end_t
		var glove_normal: Vector3 = save.get("normal", Vector3.ZERO)
		if glove_normal.length_squared() < 1.0e-8:
			glove_normal = from_pos - glove_point
		if glove_normal.length_squared() < 1.0e-8:
			glove_normal = Vector3.BACK
		event = {
			"kind": "keeper",
			"t": glove_t,
			"point": glove_point,
			"normal": glove_normal.normalized(),
			"part": Field.FRAME_NONE,
			"limb": String(save.get("limb", "")),
			"catch": bool(save.get("catch", false)),
			"restitution": GLOVE_RESTITUTION,
			"friction": GLOVE_FRICTION,
		}

	return event


## A parry always clears. This is the one place the ball is not left to pure
## reflection, and it is deliberate.
##
## A glove that meets the ball edge on takes a few metres per second out of it
## and changes its direction by a handful of degrees, which is honest physics and
## a terrible game: the player watches "Arret du gardien" appear on screen while
## the ball he just watched being touched trickles over the line behind the
## keeper. So a keeper contact that is not a catch is given a floor. The ball
## always leaves travelling back up the pitch at PARRY_MIN_Z, and the momentum
## the correction took out of the -Z direction is paid back sideways and upwards,
## which is where a real punched clearance goes: wide of the post, or over.
##
## The side it is pushed towards is the side the contact happened on, so a save
## out by the left post clears to the left rather than back across the face of
## the goal. The verdict is not involved: it was already latched as ARRET by the
## keeper's own signal, and nothing here can change it.
func _parry(out_velocity: Vector3, contact: Vector3, normal: Vector3) -> Vector3:
	var out: Vector3 = out_velocity
	if not out.is_finite():
		out = Vector3(0.0, 1.0, PARRY_MIN_Z)
	if out.z >= PARRY_MIN_Z:
		return out
	var deficit: float = PARRY_MIN_Z - out.z
	out.z = PARRY_MIN_Z
	var side: float = signf(contact.x)
	if absf(contact.x) < 0.05:
		side = signf(normal.x) if absf(normal.x) > 0.001 else 1.0
	out.x += side * deficit * PARRY_SPREAD
	out.y += deficit * PARRY_LIFT
	return out


func _no_event() -> Dictionary:
	return {
		"kind": "",
		"t": 1.0,
		"point": Vector3.ZERO,
		"normal": Vector3.UP,
		"part": Field.FRAME_NONE,
		"limb": "",
		"catch": false,
		"restitution": 0.5,
		"friction": 0.4,
	}


func _emit_event(event: Dictionary, contact: Vector3, v_in: Vector3, speed_in: float) -> void:
	var kind: String = String(event.get("kind", ""))
	var point: Vector3 = event.get("point", contact)
	match kind:
		"frame":
			frame_hit.emit(int(event.get("part", Field.FRAME_NONE)), point, speed_in)
		"net":
			net_hit.emit(point, v_in)
			if goal_frame != null and is_instance_valid(goal_frame):
				goal_frame.net_impulse(point, v_in)
		"ground":
			if absf(v_in.y) >= BOUNCE_MIN_SPEED:
				ground_hit.emit(point, speed_in)
		_:
			# A keeper contact is announced by the keeper itself, through its own
			# `saved` signal. Announcing it twice would double every reaction.
			pass


## Goal plane crossing. Reported once per crossing, and re armed only when the
## ball has come back well into the field of play, so a rebound off the net that
## leaves the goal and goes back in is reported twice, as it should be.
func _report_plane(from_pos: Vector3, to_pos: Vector3) -> void:
	if from_pos.z > 0.2:
		_plane_reported = false
	if _plane_reported:
		return
	var crossing: Dictionary = Field.cross_goal_plane(from_pos, to_pos)
	if not bool(crossing.get("crossed", false)):
		return
	_plane_reported = true
	var point: Vector3 = crossing.get("point", to_pos)
	_note_curve_cut()
	crossed_line.emit(point, Field.is_inside_mouth(point))


func _probe_keeper(from_pos: Vector3, to_pos: Vector3) -> Dictionary:
	if not flying:
		return {}
	if from_pos.z > KEEPER_PROBE_Z and to_pos.z > KEEPER_PROBE_Z:
		return {}
	_pending_save = {}
	_has_pending_save = false
	if keeper_probe.is_valid():
		var answer: Variant = keeper_probe.call(from_pos, to_pos)
		if answer is Dictionary:
			return answer as Dictionary
		return {}
	probe_keeper.emit(from_pos, to_pos)
	if _has_pending_save:
		return _pending_save
	return {}


# --- net and turf ------------------------------------------------------------


## The netted volume is described as four inward facing planes: the back panel,
## the two sides and the sloping roof. A contact is a crossing from the inside
## outwards, which is exactly what a ball entering the goal does.
func _build_net_panels() -> void:
	var roof_normal := Vector3(0.0, -Field.NET_DEPTH, Field.GOAL_HEIGHT - Field.NET_BACK_TOP)
	var panels: Array[Dictionary] = []
	panels.append({
		"kind": "back",
		"origin": Vector3(0.0, 0.0, -Field.NET_DEPTH),
		"normal": Vector3.BACK,
	})
	panels.append({
		"kind": "side",
		"origin": Vector3(-Field.GOAL_HALF, 0.0, 0.0),
		"normal": Vector3.RIGHT,
	})
	panels.append({
		"kind": "side",
		"origin": Vector3(Field.GOAL_HALF, 0.0, 0.0),
		"normal": Vector3.LEFT,
	})
	panels.append({
		"kind": "roof",
		"origin": Vector3(0.0, Field.GOAL_HEIGHT, 0.0),
		"normal": roof_normal.normalized(),
	})
	_net_panels = panels


## Height of the sloping net roof above a given depth. It hangs from the bar at
## the mouth and drops to NET_BACK_TOP at the back panel.
func _roof_height(z: float) -> float:
	var depth: float = clampf(-z / Field.NET_DEPTH, 0.0, 1.0)
	return Field.GOAL_HEIGHT + (Field.NET_BACK_TOP - Field.GOAL_HEIGHT) * depth


func _net_event(from_pos: Vector3, to_pos: Vector3) -> Dictionary:
	# Nothing to test while the whole segment is still in front of the line.
	if from_pos.z > 0.0 and to_pos.z > 0.0:
		return {"hit": false}
	var best_t: float = 2.0
	var best_point: Vector3 = to_pos
	var best_normal: Vector3 = Vector3.FORWARD
	for panel in _net_panels:
		var origin: Vector3 = panel["origin"]
		var normal: Vector3 = panel["normal"]
		var d_from: float = (from_pos - origin).dot(normal) - Field.BALL_RADIUS
		var d_to: float = (to_pos - origin).dot(normal) - Field.BALL_RADIUS
		if d_from <= 0.0 or d_to > 0.0:
			continue
		var span: float = d_from - d_to
		if span <= 1.0e-9:
			continue
		var t: float = clampf(d_from / span, 0.0, 1.0)
		var point: Vector3 = from_pos.lerp(to_pos, t)
		if not _panel_contains(String(panel["kind"]), point):
			continue
		if t < best_t:
			best_t = t
			best_point = point
			best_normal = normal
	if best_t > 1.0:
		return {"hit": false}
	return {"hit": true, "t": best_t, "point": best_point, "normal": best_normal}


func _panel_contains(kind: String, point: Vector3) -> bool:
	match kind:
		"back":
			return absf(point.x) <= Field.GOAL_HALF + 0.05 \
				and point.y >= -0.05 and point.y <= Field.NET_BACK_TOP + 0.05
		"side":
			return point.z <= 0.02 and point.z >= -Field.NET_DEPTH - 0.05 \
				and point.y >= -0.05 and point.y <= _roof_height(point.z) + 0.05
		"roof":
			return absf(point.x) <= Field.GOAL_HALF + 0.05 \
				and point.z <= 0.02 and point.z >= -Field.NET_DEPTH - 0.05
		_:
			return false


## Turf height for the ball centre. The ball always asks the pitch, so a cambered
## surface would work without touching this file.
func _ground_level(x: float, z: float) -> float:
	if pitch != null and is_instance_valid(pitch):
		return pitch.ground_height(x, z) + Field.BALL_RADIUS
	return Field.BALL_RADIUS


func _ground_event(from_pos: Vector3, to_pos: Vector3) -> Dictionary:
	var level: float = _ground_level(to_pos.x, to_pos.z)
	if to_pos.y > level:
		return {"hit": false}
	if from_pos.y <= level + 1.0e-4:
		# Already on the deck: this is rolling, handled by _settle, not a bounce.
		return {"hit": false}
	var drop: float = from_pos.y - to_pos.y
	var t: float = 0.0
	if drop > 1.0e-9:
		t = clampf((from_pos.y - level) / drop, 0.0, 1.0)
	var point: Vector3 = from_pos.lerp(to_pos, t)
	point.y = level
	return {"hit": true, "t": t, "point": point, "normal": Vector3.UP}


## Ground contact that is too gentle to bounce: the ball is clamped onto the
## turf, rolling resistance is applied and the spin is locked to the roll so the
## panels turn at the right rate instead of sliding.
func _settle(delta: float) -> void:
	if not flying:
		return
	var level: float = _ground_level(_pos.x, _pos.z)
	if _pos.y > level + 0.0015:
		_rolling = false
		return
	_pos.y = level
	if velocity.y < 0.0:
		velocity.y = 0.0
	_rolling = true

	var horizontal := Vector3(velocity.x, 0.0, velocity.z)
	var speed: float = horizontal.length()
	if speed > 1.0e-5:
		var slowed: float = maxf(0.0, speed - ROLL_DECEL * delta)
		var direction: Vector3 = horizontal / speed
		velocity = direction * slowed
		if slowed > 0.05:
			# Eased towards the rolling spin instead of snapped onto it: a driven
			# shot that skims the turf keeps most of its curl for a while, which
			# is both true and the only way a low shot can still bend.
			var roll_spin: Vector3 = Vector3.UP.cross(direction) * (slowed / Field.BALL_RADIUS)
			spin = spin.lerp(roll_spin, clampf(delta * ROLL_SPIN_RATE, 0.0, 1.0))
		else:
			spin = Vector3.ZERO
	else:
		velocity = Vector3.ZERO
		spin = Vector3.ZERO

	if velocity.length() < REST_SPEED:
		_finish_flight()


func _finish_flight() -> void:
	flying = false
	_rolling = false
	velocity = Vector3.ZERO
	spin = Vector3.ZERO
	if not _rest_emitted:
		_rest_emitted = true
		came_to_rest.emit()


# --- visual ------------------------------------------------------------------


## Composes the rotation of one sub step onto the accumulated basis. The axis is
## the angular velocity itself, so a mix of side spin and back spin tumbles the
## panels exactly as the physics says it should.
func _rotate_visual(dt: float) -> void:
	if dt <= 0.0:
		return
	var rate: float = spin.length()
	if rate < 1.0e-5:
		return
	var step := Quaternion(spin / rate, rate * dt)
	_spin_basis = (Basis(step) * _spin_basis).orthonormalized()


func _apply_transform() -> void:
	if is_inside_tree():
		global_position = _pos
	else:
		position = _pos
	if _mesh != null:
		_mesh.transform = Transform3D(_spin_basis, Vector3.ZERO)


func _record_log() -> void:
	if flight_log.size() >= MAX_LOG:
		return
	flight_log.append({"t": _elapsed, "position": _pos, "spin": spin})
	_log_basis.append(_spin_basis)


# --- queries -----------------------------------------------------------------


## Lateral deviation from a spin free flight, in metres. The HUD shows it as the
## "curve" figure after the shot. Signed: positive is towards the shooter's
## right (+X for a shot down the middle).
##
## The reference is a real `Aero.sample_flight` from the same launch state with
## the spin zeroed, not a parabola and not an approximation, so drag is present
## in both flights and only the Magnus term is left in the difference. The two
## are compared at the moment the real ball first met something (the line, the
## frame, a glove, the turf), which is the moment the figure is about.
func curve_amount() -> float:
	if _curve_log_size == flight_log.size():
		return _curve_value
	_curve_log_size = flight_log.size()
	_curve_value = 0.0
	if flight_log.size() < 2:
		return 0.0
	var index: int = _curve_index
	if index < 0:
		index = flight_log.size() - 1
	index = clampi(index, 1, flight_log.size() - 1)

	var forward := Vector3(_launch_velocity.x, 0.0, _launch_velocity.z)
	if forward.length_squared() < 1.0e-8:
		return 0.0
	forward = forward.normalized()

	var reference: PackedVector3Array = Aero.sample_flight(
		_launch_position, _launch_velocity, Vector3.ZERO, wind, _log_delta, index + 1
	)
	if reference.is_empty():
		return 0.0
	var actual: Vector3 = flight_log[index]["position"]
	var ideal: Vector3 = reference[clampi(index, 0, reference.size() - 1)]
	# forward is horizontal and unit, so this cross product is already unit.
	var right: Vector3 = forward.cross(Vector3.UP)
	_curve_value = (actual - ideal).dot(right)
	return _curve_value


## Replays a logged position. `t` is seconds since the strike.
##
## A caught ball replays as caught for free: the log kept running while the ball
## sat in the gloves, on the same clock as `Keeper.pose_log`, so scrubbing both
## from one value shows the hand and the ball arriving together.
func seek_replay(t: float) -> void:
	# The playhead now owns the position, see _advance_hold.
	_replay_frame = Engine.get_physics_frames()
	var last: int = flight_log.size() - 1
	if last < 0:
		return
	var first_t: float = float(flight_log[0]["t"])
	var last_t: float = float(flight_log[last]["t"])
	var wanted: float = clampf(t, first_t, last_t)

	var index: int = 0
	if _log_delta > 0.0:
		index = clampi(int(floor((wanted - first_t) / _log_delta)), 0, last)
	while index < last and float(flight_log[index + 1]["t"]) < wanted:
		index += 1
	while index > 0 and float(flight_log[index]["t"]) > wanted:
		index -= 1

	var blend: float = 0.0
	var from_point: Vector3 = flight_log[index]["position"]
	var to_point: Vector3 = from_point
	if index < last:
		var t0: float = float(flight_log[index]["t"])
		var t1: float = float(flight_log[index + 1]["t"])
		to_point = flight_log[index + 1]["position"]
		if t1 > t0:
			blend = clampf((wanted - t0) / (t1 - t0), 0.0, 1.0)
	_pos = from_point.lerp(to_point, blend)

	if index < _log_basis.size():
		var b0: Basis = _log_basis[index]
		var b1: Basis = _log_basis[mini(index + 1, _log_basis.size() - 1)]
		var q: Quaternion = b0.get_rotation_quaternion().slerp(b1.get_rotation_quaternion(), blend)
		_spin_basis = Basis(q)
	_apply_transform()

	if _trail != null:
		if wanted < _replay_last_t:
			_trail.clear()
		else:
			_trail.push(_pos, from_point.distance_to(to_point) / maxf(_log_delta, TIME_EPS))
	_replay_last_t = wanted


## The predicted path from the current state, for the HUD preview.
func predict(velocity_guess: Vector3, spin_guess: Vector3, steps: int) -> PackedVector3Array:
	if steps <= 0:
		return PackedVector3Array()
	return Aero.sample_flight(_pos, velocity_guess, spin_guess, wind, PREVIEW_DELTA, steps)


# --- wiring ------------------------------------------------------------------


## Finds the goal frame and the pitch among the siblings when `Main` has not
## assigned them. Duck free: both are real types, this only avoids an ordering
## dependency at boot.
func _autowire() -> void:
	var parent: Node = get_parent()
	if parent == null:
		return
	for child in parent.get_children():
		if goal_frame == null and child is GoalFrame:
			goal_frame = child as GoalFrame
		if pitch == null and child is Pitch:
			pitch = child as Pitch


func _segment_fraction(from_pos: Vector3, to_pos: Vector3, point: Vector3) -> float:
	var span: Vector3 = to_pos - from_pos
	var length_squared: float = span.length_squared()
	if length_squared < 1.0e-12:
		return 0.0
	return clampf((point - from_pos).dot(span) / length_squared, 0.0, 1.0)


## Freezes the index the curve figure is measured at, on the first thing the
## ball met. Everything after that is a rebound and says nothing about the shot.
func _note_curve_cut() -> void:
	if _curve_index < 0:
		_curve_index = maxi(flight_log.size() - 1, 0)
		_curve_log_size = -1


func _invalidate_curve() -> void:
	_curve_index = -1
	_curve_value = 0.0
	_curve_log_size = -1
