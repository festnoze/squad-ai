class_name Player
extends Node3D
## First person character of CUBEFORGE.
##
## The node tree is built entirely in _ready(): a "Head" Node3D carrying the eye
## height and the head bob, and a Camera3D under it. Yaw lives on this node,
## pitch on the head, so the movement basis never inherits the pitch.
##
## No Godot physics body is involved. Collision goes through VoxelBody, which
## sweeps an AABB against the voxel grid, and the whole simulation runs in
## _physics_process() with a fixed delta.

signal entered_water()
signal left_water()
signal fly_mode_changed(active: bool)
signal footstep(block_id: int)

# --- Body dimensions -------------------------------------------------------

const BODY_RADIUS := 0.30
const STAND_HEIGHT := 1.80
const CROUCH_HEIGHT := 1.45
const STAND_EYE := 1.62
const CROUCH_EYE := 1.28

# --- Ground movement -------------------------------------------------------

const WALK_SPEED := 4.6
const SPRINT_SPEED := 6.8
const CROUCH_SPEED := 2.0
const GROUND_ACCEL := 12.0
## Fraction of the ground acceleration that still applies while airborne.
const AIR_CONTROL := 0.30
## Extra braking factor applied when the player releases the movement keys.
const GROUND_BRAKE := 1.8

# --- Jump and fall ---------------------------------------------------------

## 8.4 against a gravity of 26.0 peaks at about 1.36 unit, which clears a single
## block with a small margin. Changing one without the other breaks traversal.
const JUMP_SPEED := 8.4
const GRAVITY := 26.0
const MAX_FALL_SPEED := 55.0
## Downward speed above which touching the ground counts as an impact.
const LAND_IMPACT_SPEED := 5.0

# --- Swimming --------------------------------------------------------------

const WATER_GRAVITY_DIVIDER := 5.0
const WATER_SPEED_SCALE := 0.60
const WATER_RISE_SPEED := 3.1
## A surface breach needs more lift than a land jump: while floating, the feet
## sit well below the waterline and a one-block bank can be almost two units
## above them. This one-shot impulse lets forward movement carry the body onto
## the bank instead of pinning it against the shoreline.
const WATER_EXIT_SPEED := 10.0
const WATER_SINK_MAX := 5.0
## Proportional vertical drag, per second. It has to stay below the water
## gravity (26 / 5) or the player would hover forever instead of sinking; the
## ratio of the two sets the terminal sink speed, here about 1.7 u/s.
const WATER_DRAG := 3.0
const WATER_ACCEL_SCALE := 0.55
## Submersion fraction above which the player counts as being in the water.
const WATER_ENTER_RATIO := 0.08
## Once wet, the box has to leave the liquid completely before swimming stops.
## Without that hysteresis, floating at the surface flips the state every frame.
const WATER_LEAVE_RATIO := 0.001
## Shortest delay between two splashes, so bobbing at the surface stays quiet.
const SPLASH_COOLDOWN_MSEC := 500
## Swimming up stops below this submersion, which parks the head just above the
## surface instead of shooting the whole body out of the water.
const WATER_FLOAT_RATIO := 0.35
## At or below this submersion, swimming up becomes a water-exit jump.
const WATER_EXIT_RATIO := 0.48
## Standing in a single block of water still allows a real jump to hop out.
const WATER_HOP_RATIO := 0.60

# --- Flight ----------------------------------------------------------------

const FLY_SPEED := 12.0
## God mode keeps normal flight controllable, while holding Run enables a
## deliberate five-times traversal boost for crossing the procedural world.
const FLY_SPRINT_MULTIPLIER := 5.0
const FLY_SPRINT_SPEED := FLY_SPEED * FLY_SPRINT_MULTIPLIER
const FLY_ACCEL_SCALE := 1.6
const FLY_VERTICAL_ACCEL := 70.0

# --- View ------------------------------------------------------------------

const PITCH_LIMIT := 1.5533431   ## 89 degrees in radians.
const CAMERA_NEAR := 0.08
## Wide enough to cover the largest render distance without clipping chunks.
const CAMERA_FAR := 512.0
const SPRINT_FOV_BONUS := 6.0
const FOV_SMOOTHING := 8.0
const EYE_SMOOTHING := 12.0
const BOB_AMPLITUDE := 0.045
const BOB_SMOOTHING := 9.0

# --- Footsteps -------------------------------------------------------------

const STEP_DISTANCE := 0.9

var camera: Camera3D
var head: Node3D
var velocity: Vector3 = Vector3.ZERO
var fly_mode: bool = false
var in_water: bool = false
var body: VoxelBody
## True until the chunk under the spawn point exists. A frozen player ignores
## gravity and input, otherwise the very first frames drop him through a world
## that has not been generated yet.
var frozen: bool = true

var _world: VoxelWorld = null
## Source of truth for the view angles. Never accumulate on rotation directly.
var _yaw: float = 0.0
var _pitch: float = 0.0
var _on_floor: bool = false
var _crouching: bool = false
var _sprinting: bool = false
var _eye_height: float = STAND_EYE
var _fov: float = DEFAULT_FOV
var _bob_phase: float = 0.0
var _bob_amount: float = 0.0
var _step_travel: float = 0.0
## Fraction of the body under a liquid, refreshed once per physics step.
var _submersion: float = 0.0
## Prevents held Space from applying the exit impulse every physics frame.
var _water_exit_boosted: bool = false
var _last_splash_msec: int = -SPLASH_COOLDOWN_MSEC
var _game: Node = null
var _sfx: Node = null


func _ready() -> void:
	body = VoxelBody.new()
	body.radius = BODY_RADIUS
	body.height = STAND_HEIGHT

	head = Node3D.new()
	head.name = "Head"
	head.position = Vector3(0.0, STAND_EYE, 0.0)
	add_child(head)

	camera = Camera3D.new()
	camera.name = "Camera3D"
	camera.near = CAMERA_NEAR
	camera.far = CAMERA_FAR
	camera.fov = _base_fov()
	camera.current = true
	head.add_child(camera)

	_fov = camera.fov
	_sfx = get_node_or_null("/root/Sfx")
	rotation = Vector3(0.0, _yaw, 0.0)


func setup(world: VoxelWorld) -> void:
	_world = world
	set_fly_mode(_setting_bool(&"fly_mode", false) and _creative())
	frozen = true
	velocity = Vector3.ZERO
	_on_floor = false


## Moves the feet to an absolute world position. The freeze state is left alone
## so that a spawn teleport issued before the terrain exists still gets snapped
## onto the ground once the chunk arrives.
func teleport(feet_position: Vector3) -> void:
	global_position = feet_position
	velocity = Vector3.ZERO
	_on_floor = false
	_step_travel = 0.0


## World position of the eye, bob included, which is where the view ray starts.
func eye_position() -> Vector3:
	if camera != null:
		return camera.global_position
	return global_position + Vector3(0.0, _eye_height, 0.0)


func look_direction() -> Vector3:
	if camera != null:
		return -camera.global_transform.basis.z.normalized()
	return Vector3.FORWARD.rotated(Vector3.UP, _yaw)


func horizontal_speed() -> float:
	return Vector2(velocity.x, velocity.z).length()


func on_floor() -> bool:
	return _on_floor


## Shared entry point for the F shortcut and the settings checkbox.
func set_fly_mode(active: bool) -> void:
	var next := active and _creative()
	if fly_mode == next:
		return
	fly_mode = next
	velocity.y = 0.0
	_crouching = false
	_on_floor = false
	fly_mode_changed.emit(fly_mode)


# ---------------------------------------------------------------------------
# Look
# ---------------------------------------------------------------------------

func _input(event: InputEvent) -> void:
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var motion := event as InputEventMouseMotion
	if motion == null:
		return
	_apply_look(motion.relative)


## Yaw and pitch are held as plain floats and assigned, never accumulated onto
## the rotation vectors, so the yaw cannot drift out of range over a long session.
func _apply_look(relative: Vector2) -> void:
	var sensitivity := _sensitivity()
	_yaw = wrapf(_yaw - relative.x * sensitivity, -PI, PI)
	var pitch_delta := relative.y * sensitivity
	if _invert_y():
		_pitch = clampf(_pitch + pitch_delta, -PITCH_LIMIT, PITCH_LIMIT)
	else:
		_pitch = clampf(_pitch - pitch_delta, -PITCH_LIMIT, PITCH_LIMIT)
	rotation = Vector3(0.0, _yaw, 0.0)
	head.rotation = Vector3(_pitch, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

func _physics_process(delta: float) -> void:
	if _world == null or body == null:
		return

	if frozen:
		velocity = Vector3.ZERO
		_sprinting = false
		_try_unfreeze()
		_update_view(delta)
		return

	var feet := global_position
	_update_fly_toggle()
	_update_water(feet)
	_update_crouch(feet)

	var wish := _wish_direction()
	_sprinting = Input.is_action_pressed("sprint") and wish != Vector3.ZERO and not _crouching
	_apply_horizontal(wish, delta)
	_apply_vertical(delta)

	var result: Dictionary = body.move(_world, feet, velocity * delta)
	var landed_speed := -velocity.y
	var new_feet: Vector3 = result.get("position", feet)
	var travel := new_feet - feet
	global_position = new_feet

	if bool(result.get("hit_x", false)):
		velocity.x = 0.0
	if bool(result.get("hit_z", false)):
		velocity.z = 0.0
	if bool(result.get("on_ceiling", false)) and velocity.y > 0.0:
		velocity.y = 0.0

	var was_on_floor := _on_floor
	_on_floor = bool(result.get("on_floor", false))
	if _on_floor and velocity.y < 0.0:
		velocity.y = 0.0

	if _on_floor and not was_on_floor and landed_speed > LAND_IMPACT_SPEED and not in_water:
		_step_travel = 0.0
		footstep.emit(_ground_block())
	else:
		_track_footsteps(travel)

	_update_view(delta)


## Unfreezes as soon as the column under the feet is loaded, then drops the feet
## onto the surface so the player never starts inside the ground or in the air.
func _try_unfreeze() -> void:
	var wx := floori(global_position.x)
	var wz := floori(global_position.z)
	if not _world.has_chunk_at(wx, wz):
		return

	var probe := Vector3(global_position.x, float(_world.surface_height(wx, wz) + 1), global_position.z)
	# Decorations (a tree grown on the spawn column) are not part of
	# surface_height(), so climb out of anything solid still overlapping.
	var guard := 0
	while guard < 12 and body.overlaps_solid(_world, probe):
		probe.y += 1.0
		guard += 1

	global_position = probe
	velocity = Vector3.ZERO
	_on_floor = true
	_step_travel = 0.0
	frozen = false


func _update_fly_toggle() -> void:
	var creative := _creative()
	if Input.is_action_just_pressed("fly_toggle") and creative:
		set_fly_mode(not fly_mode)
		var game := _game_node()
		if game != null:
			game.set(&"fly_mode", fly_mode)
		return
	if fly_mode and not creative:
		set_fly_mode(false)
		var game := _game_node()
		if game != null:
			game.set(&"fly_mode", false)


func _update_water(feet: Vector3) -> void:
	_submersion = body.submersion(_world, feet)
	var wet := _submersion > (WATER_LEAVE_RATIO if in_water else WATER_ENTER_RATIO)
	if wet == in_water:
		return
	in_water = wet
	if in_water:
		# Kill the fall so a dive does not shoot straight to the bottom.
		velocity.y = maxf(velocity.y, -WATER_SINK_MAX)
		entered_water.emit()
		var now := Time.get_ticks_msec()
		if now - _last_splash_msec >= SPLASH_COOLDOWN_MSEC:
			_last_splash_msec = now
			_play_sound("splash")
	else:
		_water_exit_boosted = false
		left_water.emit()


func _update_crouch(feet: Vector3) -> void:
	var wants := Input.is_action_pressed("crouch") and not fly_mode
	if wants:
		_crouching = true
	elif _crouching:
		# Only stand up when the taller box fits, otherwise the head would end
		# up inside the ceiling block.
		body.height = STAND_HEIGHT
		_crouching = body.overlaps_solid(_world, feet)
	body.height = CROUCH_HEIGHT if _crouching else STAND_HEIGHT


## Horizontal input rotated by the yaw only, normalised so diagonals are not
## faster than a straight line.
func _wish_direction() -> Vector3:
	var ix := Input.get_axis("move_left", "move_right")
	var iz := Input.get_axis("move_forward", "move_back")
	if is_zero_approx(ix) and is_zero_approx(iz):
		return Vector3.ZERO
	var dir := Vector3(ix, 0.0, iz).rotated(Vector3.UP, _yaw)
	dir.y = 0.0
	if dir.length_squared() > 1.0:
		dir = dir.normalized()
	return dir


func _apply_horizontal(wish: Vector3, delta: float) -> void:
	var speed := WALK_SPEED
	if fly_mode:
		speed = FLY_SPRINT_SPEED if _sprinting else FLY_SPEED
	elif _crouching:
		speed = CROUCH_SPEED
	elif _sprinting:
		speed = SPRINT_SPEED
	if in_water and not fly_mode:
		speed *= WATER_SPEED_SCALE

	var accel := GROUND_ACCEL
	if fly_mode:
		accel *= FLY_ACCEL_SCALE
	elif in_water:
		accel *= WATER_ACCEL_SCALE
	elif not _on_floor:
		accel *= AIR_CONTROL

	var target := wish * speed
	if target == Vector3.ZERO and (_on_floor or fly_mode or in_water):
		accel *= GROUND_BRAKE

	var flat := Vector3(velocity.x, 0.0, velocity.z).move_toward(target, accel * delta)
	velocity.x = flat.x
	velocity.z = flat.z


func _apply_vertical(delta: float) -> void:
	if fly_mode:
		var want := 0.0
		if Input.is_action_pressed("jump"):
			want += 1.0
		if Input.is_action_pressed("crouch"):
			want -= 1.0
		var vertical_speed := FLY_SPRINT_SPEED if _sprinting else FLY_SPEED
		velocity.y = move_toward(velocity.y, want * vertical_speed, FLY_VERTICAL_ACCEL * delta)
		return

	if in_water:
		var holding_jump := Input.is_action_pressed("jump")
		if holding_jump and _on_floor and _submersion < WATER_HOP_RATIO:
			# Wading through a single block of water, so a normal jump gets out.
			velocity.y = JUMP_SPEED
			_on_floor = false
			return
		# Swimming and leaving the water are intentionally different motions.
		# Once the player reaches the surface, Space gives one decisive breach
		# impulse; horizontal input then carries the body over a one-block bank.
		if holding_jump and _submersion <= WATER_EXIT_RATIO and not _water_exit_boosted:
			velocity.y = WATER_EXIT_SPEED
			_water_exit_boosted = true
			_on_floor = false
			return
		if not holding_jump or _submersion > WATER_EXIT_RATIO + 0.12:
			_water_exit_boosted = false
		velocity.y -= (GRAVITY / WATER_GRAVITY_DIVIDER) * delta
		velocity.y *= maxf(0.0, 1.0 - WATER_DRAG * delta)
		if holding_jump and _submersion >= WATER_FLOAT_RATIO:
			velocity.y = WATER_RISE_SPEED
		velocity.y = clampf(velocity.y, -WATER_SINK_MAX, WATER_RISE_SPEED)
		return

	if Input.is_action_pressed("jump") and _on_floor:
		velocity.y = JUMP_SPEED
		_on_floor = false
	else:
		velocity.y -= GRAVITY * delta
		if velocity.y < -MAX_FALL_SPEED:
			velocity.y = -MAX_FALL_SPEED


func _track_footsteps(travel: Vector3) -> void:
	if not _on_floor or in_water or fly_mode:
		_step_travel = 0.0
		return
	_step_travel += Vector2(travel.x, travel.z).length()
	if _step_travel < STEP_DISTANCE:
		return
	_step_travel -= STEP_DISTANCE
	footstep.emit(_ground_block())


## Block the feet rest on, sampled one cell below the feet plane. The small bias
## absorbs the separation margin left by the collision solver.
func _ground_block() -> int:
	var wx := floori(global_position.x)
	var wy := floori(global_position.y - 0.1)
	var wz := floori(global_position.z)
	return _world.get_block(wx, wy, wz)


# ---------------------------------------------------------------------------
# View smoothing
# ---------------------------------------------------------------------------

func _update_view(delta: float) -> void:
	var eye_target := CROUCH_EYE if _crouching else STAND_EYE
	_eye_height = lerpf(_eye_height, eye_target, _smooth(EYE_SMOOTHING, delta))

	var bob_target := 0.0
	if _on_floor and not fly_mode:
		bob_target = clampf(horizontal_speed() / WALK_SPEED, 0.0, 1.4)
	_bob_amount = lerpf(_bob_amount, bob_target, _smooth(BOB_SMOOTHING, delta))
	_bob_phase = wrapf(_bob_phase + delta * (4.0 + horizontal_speed() * 1.6), -TAU, TAU)

	var amp := BOB_AMPLITUDE * _bob_amount
	head.position = Vector3(
		cos(_bob_phase) * amp * 0.7,
		_eye_height + absf(sin(_bob_phase)) * amp - amp * 0.5,
		0.0
	)
	head.rotation = Vector3(_pitch, 0.0, 0.0)

	var fov_target := _base_fov()
	if _sprinting:
		fov_target += SPRINT_FOV_BONUS
	_fov = lerpf(_fov, fov_target, _smooth(FOV_SMOOTHING, delta))
	camera.fov = _fov


## Frame rate independent exponential smoothing weight.
func _smooth(rate: float, delta: float) -> float:
	return 1.0 - exp(-rate * delta)


# ---------------------------------------------------------------------------
# Settings and audio access
# ---------------------------------------------------------------------------
#
# The Game and Sfx autoloads are reached through /root so the controller stays
# usable on its own (headless checks and unit tests never instance autoloads).

const DEFAULT_SENSITIVITY := 0.0022
const DEFAULT_FOV := 78.0


func _game_node() -> Node:
	if _game == null:
		_game = get_node_or_null(^"/root/Game")
	return _game


func _setting_float(key: StringName, fallback: float) -> float:
	var node := _game_node()
	if node == null:
		return fallback
	var value: Variant = node.get(key)
	if value is float or value is int:
		return float(value)
	return fallback


func _setting_bool(key: StringName, fallback: bool) -> bool:
	var node := _game_node()
	if node == null:
		return fallback
	var value: Variant = node.get(key)
	if value is bool:
		return value
	return fallback


func _sensitivity() -> float:
	return maxf(_setting_float(&"mouse_sensitivity", DEFAULT_SENSITIVITY), 0.00001)


func _invert_y() -> bool:
	return _setting_bool(&"invert_y", false)


func _base_fov() -> float:
	return clampf(_setting_float(&"fov", DEFAULT_FOV), 50.0, 120.0)


func _creative() -> bool:
	return _setting_bool(&"creative", true)


func _play_sound(name: String) -> void:
	if _sfx == null:
		_sfx = get_node_or_null("/root/Sfx")
	if _sfx == null:
		return
	if _sfx.has_method("play_at"):
		_sfx.call("play_at", name, global_position, 0.0, 1.0)
	elif _sfx.has_method("play"):
		_sfx.call("play", name, 0.0, 1.0)
