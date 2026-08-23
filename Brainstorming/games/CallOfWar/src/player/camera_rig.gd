class_name CameraRig
extends Node3D
## First person camera rig.
##
## Node hierarchy built by [method setup]:
##   CameraRig (this node, carries the yaw)
##     PitchPivot (Node3D, carries the pitch, sits at eye height)
##       Camera (Camera3D, carries bob, sway and shake offsets)
##
## The rig is a child of the player and is expected to sit at the player origin
## (the feet). The eye height is fed every frame through [method update] as
## `stance_height`, and the pivot glides towards it so a crouch never snaps.
##
## Recoil is a two part spring: a kick is split between a transient part that
## springs back to zero and a permanent part folded straight into `yaw` and
## `pitch`. That permanent share is what makes a burst climb and drift instead
## of returning exactly where it started.

## Hard limit of the vertical aim, in radians (about 86 degrees).
const PITCH_LIMIT := 1.5
## Seconds to blend in or out of the aiming field of view.
const AIM_BLEND_TIME := 0.12
## Share of a recoil kick that never comes back. This is the muzzle climb.
const RECOIL_PERMANENT := 0.26
## Spring constants of the transient recoil.
const RECOIL_STIFFNESS := 210.0
const RECOIL_DAMPING := 25.0
## How fast the transient recoil target melts back towards zero.
const RECOIL_DECAY := 9.5
## Extra velocity injected on a kick so the first frame is violent.
const RECOIL_IMPULSE := 7.0

## Mouse motion to sway conversion, in radians per pixel.
const SWAY_GAIN := 0.0017
const SWAY_STIFFNESS := 150.0
const SWAY_DAMPING := 12.0
const SWAY_MAX := 0.030
const SWAY_AIM_SCALE := 0.16

const BOB_FREQUENCY := 8.6
const BOB_AMPLITUDE := 0.048
const BOB_AIM_SCALE := 0.16
const BOB_REFERENCE_SPEED := 4.4

const ROLL_PER_SPEED := 0.0075
const ROLL_MAX := 0.055
const SHAKE_FREQUENCY := 26.0

## The camera itself. Valid after [method setup].
var camera: Camera3D = null
## Horizontal aim, radians. Free running, never clamped.
var yaw: float = 0.0
## Vertical aim, radians, clamped to +/- PITCH_LIMIT.
var pitch: float = 0.0

var _pivot: Node3D = null
var _built := false
var _base_fov := 82.0
var _aim_blend := 0.0
var _eye_height := 1.68
var _height_seeded := false

var _recoil := Vector2.ZERO
var _recoil_target := Vector2.ZERO
var _recoil_velocity := Vector2.ZERO

var _sway := Vector2.ZERO
var _sway_velocity := Vector2.ZERO
var _mouse_delta := Vector2.ZERO

var _bob_phase := 0.0
var _bob_offset := Vector3.ZERO
var _roll := 0.0

var _shake_strength := 0.0
var _shake_left := 0.0
var _shake_total := 0.0
var _shake_offset := Vector2.ZERO
var _shake_seed := 0.0

var _time := 0.0


func _ready() -> void:
	if not _built:
		setup()


## Builds the pivot and the camera. Safe to call twice.
func setup() -> void:
	if _built:
		return
	_built = true
	_shake_seed = float(Time.get_ticks_usec() % 100000) * 0.001

	_pivot = Node3D.new()
	_pivot.name = "PitchPivot"
	_pivot.position = Vector3(0.0, _eye_height, 0.0)
	add_child(_pivot)

	camera = Camera3D.new()
	camera.name = "Camera"
	camera.fov = _base_fov
	camera.near = 0.05
	camera.far = 1400.0
	camera.current = true
	_pivot.add_child(camera)


## Mouse look. Applies Game.mouse_sensitivity and Game.invert_y.
func look(relative: Vector2) -> void:
	if not _built:
		setup()
	var sensitivity := 0.0024
	var inverted := false
	if Game != null:
		sensitivity = Game.mouse_sensitivity
		inverted = Game.invert_y
	# Aiming narrows the field of view, so scale the sensitivity with it and
	# keep the same angular travel per centimetre of mouse.
	var zoom_scale := 1.0
	if camera != null and _base_fov > 1.0:
		zoom_scale = clampf(camera.fov / _base_fov, 0.35, 1.0)
	var step := sensitivity * zoom_scale
	yaw -= relative.x * step
	var vertical := relative.y * step
	if inverted:
		vertical = -vertical
	pitch = clampf(pitch - vertical, -PITCH_LIMIT, PITCH_LIMIT)
	# The weapon drags behind the mouse: feed the sway spring.
	_mouse_delta += relative


## Adds a recoil kick. Both in radians. A positive pitch pushes the muzzle up.
func add_recoil(pitch_kick: float, yaw_kick: float) -> void:
	if not _built:
		setup()
	var transient := 1.0 - RECOIL_PERMANENT
	_recoil_target.x += pitch_kick * transient
	_recoil_target.y += yaw_kick * transient
	_recoil_velocity += Vector2(pitch_kick, yaw_kick) * RECOIL_IMPULSE
	# The permanent share moves the actual aim, which is the drift.
	pitch = clampf(pitch + pitch_kick * RECOIL_PERMANENT, -PITCH_LIMIT, PITCH_LIMIT)
	yaw += yaw_kick * RECOIL_PERMANENT


## Per frame update: recoil recovery, bob, sway, aim transition.
func update(delta: float, velocity: Vector3, is_grounded: bool, is_aiming: bool,
		aim_fov_scale: float, stance_height: float) -> void:
	if not _built:
		setup()
	var step := clampf(delta, 0.0, 0.1)
	_time += step
	_update_recoil(step)
	_update_sway(step, velocity, is_aiming)
	_update_bob(step, velocity, is_grounded, is_aiming)
	_update_shake(step)
	_update_height(step, stance_height)
	_update_fov(step, is_aiming, aim_fov_scale)
	_apply()


## Camera shake, e.g. explosions. `amount` in radians.
func shake(amount: float, seconds: float) -> void:
	if amount <= 0.0 or seconds <= 0.0:
		return
	if amount >= _shake_strength or _shake_left <= 0.0:
		_shake_strength = maxf(_shake_strength, amount)
		_shake_total = maxf(seconds, 0.02)
		_shake_left = _shake_total
	else:
		# A weaker shake during a stronger one only extends it a little.
		_shake_left = maxf(_shake_left, minf(seconds, _shake_total))


## Where a bullet leaves from and where it goes.
func aim_ray() -> Transform3D:
	if camera == null:
		return global_transform
	return camera.global_transform


func forward() -> Vector3:
	if camera == null:
		return -global_transform.basis.z
	return -camera.global_transform.basis.z


func set_base_fov(fov: float) -> void:
	_base_fov = clampf(fov, 40.0, 130.0)
	if camera != null and _aim_blend <= 0.0:
		camera.fov = _base_fov


# --- internals ---------------------------------------------------------------


func _update_recoil(delta: float) -> void:
	var to_target := _recoil_target - _recoil
	var accel := to_target * RECOIL_STIFFNESS - _recoil_velocity * RECOIL_DAMPING
	_recoil_velocity += accel * delta
	_recoil += _recoil_velocity * delta
	var melt := 1.0 - exp(-RECOIL_DECAY * delta)
	_recoil_target = _recoil_target.lerp(Vector2.ZERO, melt)
	if _recoil.length() < 0.00005 and _recoil_target.length() < 0.00005:
		_recoil = Vector2.ZERO
		_recoil_target = Vector2.ZERO
		_recoil_velocity = Vector2.ZERO


func _update_sway(delta: float, velocity: Vector3, is_aiming: bool) -> void:
	var target := Vector2(
		clampf(-_mouse_delta.x * SWAY_GAIN, -SWAY_MAX, SWAY_MAX),
		clampf(-_mouse_delta.y * SWAY_GAIN, -SWAY_MAX, SWAY_MAX))
	if is_aiming:
		target *= SWAY_AIM_SCALE
	var accel := (target - _sway) * SWAY_STIFFNESS - _sway_velocity * SWAY_DAMPING
	_sway_velocity += accel * delta
	_sway += _sway_velocity * delta
	_sway.x = clampf(_sway.x, -SWAY_MAX, SWAY_MAX)
	_sway.y = clampf(_sway.y, -SWAY_MAX, SWAY_MAX)
	_mouse_delta = Vector2.ZERO

	# Strafing rolls the view slightly, in the local frame of the rig.
	var lateral := 0.0
	var flat := Vector3(velocity.x, 0.0, velocity.z)
	if flat.length_squared() > 0.01:
		lateral = flat.dot(global_transform.basis.x)
	var roll_target := clampf(-lateral * ROLL_PER_SPEED, -ROLL_MAX, ROLL_MAX)
	if is_aiming:
		roll_target *= 0.35
	roll_target += _sway.x * 0.45
	_roll = lerpf(_roll, roll_target, 1.0 - exp(-7.0 * delta))


func _update_bob(delta: float, velocity: Vector3, is_grounded: bool, is_aiming: bool) -> void:
	var enabled := true
	if Game != null:
		enabled = Game.head_bob
	var speed := Vector2(velocity.x, velocity.z).length()
	if not enabled or not is_grounded or speed < 0.6:
		_bob_offset = _bob_offset.lerp(Vector3.ZERO, 1.0 - exp(-9.0 * delta))
		return
	var ratio := clampf(speed / BOB_REFERENCE_SPEED, 0.3, 1.8)
	var amplitude := BOB_AMPLITUDE * ratio
	if is_aiming:
		amplitude *= BOB_AIM_SCALE
	_bob_phase += delta * BOB_FREQUENCY * ratio
	if _bob_phase > TAU * 64.0:
		_bob_phase -= TAU * 64.0
	# Discrete lissajous: a flattened figure of eight, the horizontal axis at
	# half the vertical rate, which is what reads as a footfall.
	var target := Vector3(
		sin(_bob_phase) * amplitude,
		sin(_bob_phase * 2.0) * amplitude * 0.62,
		0.0)
	_bob_offset = _bob_offset.lerp(target, 1.0 - exp(-15.0 * delta))


func _update_shake(delta: float) -> void:
	if _shake_left <= 0.0:
		_shake_offset = _shake_offset.lerp(Vector2.ZERO, 1.0 - exp(-14.0 * delta))
		return
	_shake_left = maxf(0.0, _shake_left - delta)
	var fade := _shake_left / maxf(_shake_total, 0.001)
	var magnitude := _shake_strength * fade * fade
	var t := (_time + _shake_seed) * SHAKE_FREQUENCY
	_shake_offset = Vector2(
		sin(t * 1.13) * magnitude,
		sin(t * 0.87 + 1.7) * magnitude * 1.25)
	if _shake_left <= 0.0:
		_shake_strength = 0.0


func _update_height(delta: float, stance_height: float) -> void:
	var target := maxf(stance_height, 0.2)
	if not _height_seeded:
		_height_seeded = true
		_eye_height = target
	else:
		_eye_height = lerpf(_eye_height, target, 1.0 - exp(-11.0 * delta))


func _update_fov(delta: float, is_aiming: bool, aim_fov_scale: float) -> void:
	var goal := 1.0 if is_aiming else 0.0
	var rate := delta / maxf(AIM_BLEND_TIME, 0.001)
	_aim_blend = move_toward(_aim_blend, goal, rate)
	if camera == null:
		return
	var eased := _aim_blend * _aim_blend * (3.0 - 2.0 * _aim_blend)
	var scale := clampf(aim_fov_scale, 0.2, 1.0)
	camera.fov = lerpf(_base_fov, _base_fov * scale, eased)


func _apply() -> void:
	rotation.y = yaw + _recoil.y + _shake_offset.y * 0.5
	if _pivot != null:
		var total_pitch := pitch + _recoil.x + _shake_offset.x
		_pivot.rotation.x = clampf(total_pitch, -PITCH_LIMIT - 0.25, PITCH_LIMIT + 0.25)
		_pivot.position.y = _eye_height
	if camera != null:
		camera.position = _bob_offset
		camera.rotation = Vector3(_sway.y, _sway.x, _roll)
