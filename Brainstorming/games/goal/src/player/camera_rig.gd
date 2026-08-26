## GOAL - the camera rig: four framings and one honest follow.
##
## Why this module is built the way it is.
##
## 1. There is a single Camera3D, moved between framings, rather than four
##    cameras taking turns. A view change is a cut: the spring state is snapped
##    at the same time, so switching never produces a two second swoop across
##    the stadium. Everything the HUD needs is one node, always the same one.
##
## 2. The follow is a critically damped spring WITH A CAPPED ANGULAR RATE. An
##    uncapped spring locked onto a 30 m/s ball whips the whole frame around in
##    a fifth of a second, which is unreadable and genuinely nauseating. The cap
##    lets the ball slide out of frame for a few hundredths of a second instead,
##    and the eye follows that far better than it follows a whip pan. The spring
##    itself is the implicit form, so a frame hitch cannot blow it up.
##
## 3. The shake is an impulse that decays over time, sampled from a value noise
##    table built once from a fixed seed. Calling randf() per frame gives white
##    noise, which reads as a judder rather than a knock. The noise is sampled
##    by TIME, so it stays smooth at any frame rate and slows down properly
##    when Engine.time_scale drops for the slow motion flight.
##
## 4. Nothing here counts frames. Every motion is driven by the delta handed in,
##    or by the replay clock handed to orbit_replay(), which is what keeps the
##    rig correct under a scaled time step.
##
## 5. Game is reached through get_node_or_null("/root/Game") rather than by
##    naming the autoload, so the file still parses under
##    `--check-only --script`, where autoloads do not exist.
class_name CameraRig
extends Node3D

enum View { DERRIERE, BUT, TELE, REPLAY }

# --- Tuning -----------------------------------------------------------------

## Spring stiffness of the position follow, in Hz.
const FOLLOW_FREQ := 1.30
## The rig never travels faster than this, whatever the spring asks for.
const MAX_FOLLOW_SPEED := 12.0
## Hard ceiling on the pan rate. This is the anti motion sickness rule.
const MAX_TURN_RATE := 1.92          # rad/s, about 110 degrees
## Exponential sharpness of the aim, under the rate cap.
const TURN_SHARP := 5.5

## Shake decay, per second, plus a linear term so it truly reaches zero.
const SHAKE_DAMP := 3.4
const SHAKE_FLOOR := 0.06
## Metres and radians at full shake.
const SHAKE_POS := 0.075
const SHAKE_ROT := 0.030
## Shake noise frequency, Hz.
const SHAKE_HZ := 11.0

## Permanent hand held drift, so a still frame is never dead.
const HAND_POS := 0.012
const HAND_ROT := 0.0032
const HAND_HZ := 0.45

const NOISE_SIZE := 96

## Replay orbit.
const ORBIT_RADIUS := 7.4
const ORBIT_RATE := 0.42             # rad/s
const ORBIT_START := 0.65
const ORBIT_DOLLY := 0.55            # metres per second of slow push in

## Where the broadcast frame is aimed across the goal line, in metres of x. The
## rig sits a short way to one side and aims at the middle of the mouth: the
## small remaining yaw is what gives the shot its depth without tipping the goal
## line off the level.
const TELE_LOOK_X := 0.0
## Height the broadcast lens is aimed at, in metres. It is deliberately just
## above the crossbar: aiming at the turf drops the goal into the middle of the
## frame and fills the bottom half with an empty green plane.
const TELE_LOOK_Y := 2.60

const FOV_DERRIERE := 30.0
const FOV_BUT := 40.0
const FOV_TELE := 21.0
const FOV_REPLAY := 38.0

# --- Contract state ---------------------------------------------------------

var view: int = View.DERRIERE
var shake: float = 0.0

# --- Internals --------------------------------------------------------------

var _built: bool = false
var _cam: Camera3D = null
var _game: Node = null

var _pos: Vector3 = Vector3.ZERO
var _vel: Vector3 = Vector3.ZERO
var _fwd: Vector3 = Vector3.FORWARD
var _last_target: Vector3 = Vector3.ZERO

var _shake_time: float = 0.0
var _hand_time: float = 0.0
var _shake_setting: float = 0.7
var _orbit_t: float = 0.0

var _noise: PackedFloat32Array = PackedFloat32Array()

var _p_derriere: Vector3 = Vector3.ZERO
var _p_but: Vector3 = Vector3.ZERO
var _p_tele: Vector3 = Vector3.ZERO


func _ready() -> void:
	build()


# --- Construction -----------------------------------------------------------

func build() -> void:
	if _built:
		return
	_built = true
	_build_noise()

	var spot_z: float = Field.SPOT_Z
	# Over the taker's right shoulder, and deliberately WELL back from it. The
	# taker starts at z = spot + 3.35, so a lens parked two metres behind him
	# turns his head into a full quarter of the frame. Standing 4.85 m behind him
	# and 0.9 m above his head puts him in the lower third as a readable body,
	# leaves the whole mouth plus the reticle margin inside the frame, and still
	# reads as an over the shoulder shot rather than a floating drone.
	_p_derriere = Vector3(-0.62, 2.62, spot_z + 8.20)
	# The goal camera. It used to sit 1.55 m behind the back net, where a 7 m wide
	# net panel covers every pixel and the unlit run off behind the goal makes the
	# whole frame black. It now stands 6.2 m further back and a metre above the
	# net top, so the cord grid reads as a foreground layer over a lit pitch and
	# the mouth, the keeper and the ball are all legible through it.
	_p_but = Vector3(0.0, 3.05, -9.00)
	# Broadcast frame. The old rig sat at x = 17 for a z distance of 11: a 46
	# degree yaw, which drags the vanishing point of the goal line on screen and
	# lays every painted line across the frame on a diagonal. Aiming a few metres
	# wide of the goal fixed the tilt but parked the mouth against the right edge
	# with half the frame given over to bare turf.
	#
	# Two numbers decide whether the goal line reads as level: the lateral offset
	# and the distance. What tips the line is the RATIO of the distances to the
	# two posts, not the yaw. At 5 m across and 24 m back that ratio is 1.06,
	# under three degrees of tilt on screen, which the eye reads as level, so the
	# rig can aim straight down the middle of the mouth. The lens is long, 21
	# degrees, so the mouth is big, and the aim sits just over the bar, which
	# drops the goal into the lower two thirds and lets the near stand rather
	# than an empty turf plane fill the rest of the frame.
	_p_tele = Vector3(-5.00, 5.40, spot_z + 13.00)
	_last_target = Field.SPOT

	if _cam == null:
		_cam = Camera3D.new()
		_cam.name = "Camera3D"
		add_child(_cam)
	_cam.near = 0.08
	_cam.far = 500.0
	_cam.keep_aspect = Camera3D.KEEP_HEIGHT
	_cam.fov = FOV_DERRIERE
	_cam.current = true

	_refresh_setting()
	set_view(View.DERRIERE)


func _build_noise() -> void:
	# One table, one fixed seed, sampled by time. Deterministic, and identical
	# on every machine, which matters when a replay is compared frame to frame.
	var rng := RandomNumberGenerator.new()
	rng.seed = 0x5EEDCA11
	_noise.resize(NOISE_SIZE)
	for i in NOISE_SIZE:
		_noise[i] = rng.randf() * 2.0 - 1.0


func camera() -> Camera3D:
	if not _built:
		build()
	return _cam


# --- Views ------------------------------------------------------------------

func set_view(new_view: int) -> void:
	if not _built:
		build()
	if new_view < int(View.DERRIERE) or new_view > int(View.REPLAY):
		push_warning("CameraRig: unknown view %d, ignored." % new_view)
		return
	view = new_view
	if _cam != null:
		_cam.fov = _fov_for(view)
	# A view change is a cut, not a travelling shot: snap the spring.
	_pos = _desired_position(_last_target, false)
	_vel = Vector3.ZERO
	var to: Vector3 = _desired_look(_last_target, false) - _pos
	_fwd = to.normalized() if to.length_squared() > 1.0e-6 else Vector3.FORWARD
	_orbit_t = 0.0
	_apply_transform()


func cycle_view() -> void:
	set_view((view + 1) % (int(View.REPLAY) + 1))


func _fov_for(v: int) -> float:
	match v:
		View.BUT:
			return FOV_BUT
		View.TELE:
			return FOV_TELE
		View.REPLAY:
			return FOV_REPLAY
		_:
			return FOV_DERRIERE


func _desired_position(_target: Vector3, flying: bool) -> Vector3:
	match view:
		View.BUT:
			# Behind and above the net, looking back down the barrel of the shot.
			return _p_but + (Vector3(0.0, -0.18, 0.45) if flying else Vector3.ZERO)
		View.TELE:
			# High and off to one side, long lens, the broadcast frame.
			return _p_tele + (Vector3(-0.6, -0.30, -1.2) if flying else Vector3.ZERO)
		View.REPLAY:
			return _pos
		_:
			# Over the taker's right shoulder, goal filling the frame. When the
			# ball goes, the rig rises and creeps forward rather than chasing.
			return _p_derriere + (Vector3(0.10, 0.22, -0.55) if flying else Vector3.ZERO)


func _desired_look(target: Vector3, flying: bool) -> Vector3:
	if flying:
		return target
	# Idle framing. `target` is only a nudge here: the aim reticle may be well
	# outside the mouth, and the frame must not follow it out to the corner flag.
	var tx: float = clampf(target.x, -6.0, 6.0)
	var ty: float = clampf(target.y, 0.0, 3.0)
	match view:
		View.BUT:
			return Vector3(tx * 0.08, 1.30, Field.SPOT_Z + 1.10)
		View.TELE:
			# Aimed at the middle of the mouth, at bar height, on the goal line
			# itself. Aiming short of the line, at mid pitch, tilts the lens down
			# and buys nothing but bare turf across the bottom of the frame. The
			# reticle nudge stays small, so a wide aim cannot drag the goal out of
			# the shot.
			return Vector3(TELE_LOOK_X + tx * 0.10, TELE_LOOK_Y, 0.0)
		View.REPLAY:
			return _pos + _fwd
		_:
			return Vector3(tx * 0.30, 1.05 + ty * 0.22, 0.0)


# --- Follow -----------------------------------------------------------------

func track(target: Vector3, flying: bool, delta: float) -> void:
	if not _built:
		build()
	var dt: float = clampf(delta, 0.0, 0.10)
	_last_target = target
	_advance_shake(dt)
	if view == View.REPLAY:
		# orbit_replay owns the pose while the replay runs.
		return
	_spring_to(_desired_position(target, flying), dt)
	_turn_to(_desired_look(target, flying), dt)
	_apply_transform()


## Implicit critically damped spring. The implicit form is used on purpose: the
## explicit one goes unstable the first time a frame takes 100 ms, and a camera
## that explodes once is a camera nobody trusts again.
func _spring_to(goal: Vector3, dt: float) -> void:
	if dt <= 0.0:
		return
	var omega: float = TAU * FOLLOW_FREQ
	var f: float = 1.0 + 2.0 * dt * omega
	var oo: float = omega * omega
	var hoo: float = dt * oo
	var hhoo: float = dt * hoo
	var det_inv: float = 1.0 / (f + hhoo)
	var det_x: Vector3 = _pos * f + _vel * dt + goal * hhoo
	var det_v: Vector3 = _vel + (goal - _pos) * hoo
	_pos = det_x * det_inv
	_vel = det_v * det_inv
	var speed: float = _vel.length()
	if speed > MAX_FOLLOW_SPEED:
		_vel *= MAX_FOLLOW_SPEED / speed


## Turns towards a point, smoothly, and never faster than MAX_TURN_RATE.
func _turn_to(look_point: Vector3, dt: float) -> void:
	var to: Vector3 = look_point - _pos
	if to.length_squared() < 1.0e-8:
		return
	var want: Vector3 = to.normalized()
	var angle: float = _fwd.angle_to(want)
	if angle < 1.0e-5:
		_fwd = want
		return
	if angle > PI - 1.0e-3:
		# Exactly opposite: slerp has no axis to work with, so nudge it first.
		want = (want + Vector3(0.0, 0.02, 0.0)).normalized()
		angle = _fwd.angle_to(want)
	var step: float = angle * (1.0 - exp(-TURN_SHARP * dt))
	step = minf(step, MAX_TURN_RATE * dt)
	_fwd = _fwd.slerp(want, clampf(step / angle, 0.0, 1.0)).normalized()


func _apply_transform() -> void:
	if _cam == null:
		return
	var basis: Basis = _basis_from_forward(_fwd)
	var pos: Vector3 = _pos

	# Hand held drift, always on, tiny. Scaled by the comfort setting so a player
	# who turned the shake off gets a locked off camera.
	var drift: float = _shake_setting
	if drift > 0.0:
		var hx: float = _noise_at(_hand_time * HAND_HZ, 0)
		var hy: float = _noise_at(_hand_time * HAND_HZ, 1)
		var hr: float = _noise_at(_hand_time * HAND_HZ, 2)
		pos += basis * Vector3(hx, hy, 0.0) * (HAND_POS * drift)
		basis = basis.rotated(basis.z, hr * HAND_ROT * drift)

	if shake > 0.001:
		# Quadratic so a small knock stays subtle and a post rattles the frame.
		# `shake` already carries the comfort setting from add_shake(): scaling
		# it a second time here would be the classic double multiplier bug.
		var amp: float = shake * shake
		var t: float = _shake_time * SHAKE_HZ
		var nx: float = _noise_at(t, 3)
		var ny: float = _noise_at(t, 4)
		var nz: float = _noise_at(t, 5)
		var np: float = _noise_at(t * 0.83, 6)
		var nyw: float = _noise_at(t * 0.91, 7)
		var nr: float = _noise_at(t * 0.71, 8)
		pos += basis * Vector3(nx, ny, nz * 0.4) * (SHAKE_POS * amp)
		basis = basis.rotated(basis.x, np * SHAKE_ROT * amp)
		basis = basis.rotated(basis.y, nyw * SHAKE_ROT * amp)
		basis = basis.rotated(basis.z, nr * SHAKE_ROT * 1.4 * amp)

	_cam.transform = Transform3D(basis.orthonormalized(), pos)


func _basis_from_forward(forward: Vector3) -> Basis:
	# A Camera3D looks down its own -Z.
	var z: Vector3 = -forward.normalized()
	var x: Vector3 = Vector3.UP.cross(z)
	if x.length_squared() < 1.0e-6:
		x = Vector3.RIGHT
	x = x.normalized()
	var y: Vector3 = z.cross(x).normalized()
	return Basis(x, y, z)


# --- Shake ------------------------------------------------------------------

func add_shake(amount: float) -> void:
	if not _built:
		build()
	_refresh_setting()
	# The comfort setting is applied here, once, and nowhere else.
	shake = clampf(shake + clampf(amount, 0.0, 1.0) * _shake_setting, 0.0, 1.4)


func _advance_shake(dt: float) -> void:
	_shake_time += dt
	_hand_time += dt
	if shake <= 0.0:
		return
	shake = maxf(shake * exp(-SHAKE_DAMP * dt) - SHAKE_FLOOR * dt, 0.0)


## Value noise: two table entries and a smoothstep between them. Continuous in
## time, so it reads as a camera being knocked rather than as a per frame jitter.
func _noise_at(t: float, channel: int) -> float:
	if _noise.size() < 2:
		return 0.0
	var x: float = t + float(channel) * 13.37
	var i: int = int(floor(x))
	var f: float = x - float(i)
	var a: float = _noise[posmod(i, NOISE_SIZE)]
	var b: float = _noise[posmod(i + 1, NOISE_SIZE)]
	return lerpf(a, b, f * f * (3.0 - 2.0 * f))


# --- Replay orbit -----------------------------------------------------------

func orbit_replay(centre: Vector3, t: float) -> void:
	if not _built:
		build()
	# The replay clock is the only time source here, so the orbit stays right
	# whatever Engine.time_scale is doing to the flight being replayed.
	var dt: float = clampf(t - _orbit_t, 0.0, 0.20)
	_orbit_t = t
	_advance_shake(dt)
	if _cam != null:
		_cam.fov = FOV_REPLAY

	var angle: float = ORBIT_START + t * ORBIT_RATE
	var radius: float = maxf(ORBIT_RADIUS - t * ORBIT_DOLLY, 3.2)
	var height: float = 1.95 + 0.55 * sin(t * 0.8) + radius * 0.10
	_pos = centre + Vector3(sin(angle) * radius, height, cos(angle) * radius)
	_vel = Vector3.ZERO

	var look: Vector3 = centre + Vector3(0.0, 0.25, 0.0)
	var to: Vector3 = look - _pos
	if to.length_squared() > 1.0e-8:
		_fwd = to.normalized()
	_apply_transform()


# --- Autoload access without naming the singleton ---------------------------

func _refresh_setting() -> void:
	_shake_setting = clampf(_setting_float("camera_shake", 0.7), 0.0, 1.0)


func _setting_float(key: String, fallback: float) -> float:
	if _game == null or not is_instance_valid(_game):
		if not is_inside_tree():
			return fallback
		_game = get_tree().root.get_node_or_null(^"Game")
	if _game == null:
		return fallback
	var v: Variant = _game.get(key)
	if typeof(v) == TYPE_FLOAT or typeof(v) == TYPE_INT:
		return float(v)
	return fallback
