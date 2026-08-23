## First person weapon model, child of the player camera.
##
## Everything here is animated by code: there is no AnimationPlayer and no
## imported animation in CALL OF WAR. Recoil is a damped spring on the Z axis
## and on the pitch, the reload drops the weapon, rolls it and brings it back,
## and the bolt of the Kar98k and the Garand really moves because it lives in
## its own child node.
##
## Node layout built by `setup()`:
##
##     Viewmodel            (identity, never moved: the wall probe lives on it)
##     +- Rig               (all the animation offsets are applied here)
##        +- Model          MeshInstance3D, Meshes.weapon_model(id)
##           +- Bolt        MeshInstance3D, cycles on every shot
##           +- Muzzle      Node3D, where the flash and the tracer start
##     +- WallProbe         RayCast3D, drives the weapon lowering
##
## Known trap this file exists to solve: a first person weapon sinks into any
## wall the player walks up to. The clean fix (a dedicated camera cull mask
## with a second camera) costs a whole render pass, so we do what most shooters
## of the era did and simply lower the weapon when a short probe finds a wall.
class_name Viewmodel
extends Node3D

## Seconds to blend between the hip pose and the aimed pose.
const AIM_BLEND := 0.12

## Uniform shrink applied to the world weapon mesh when it is held in first
## person. See the comment where it is applied in setup().
const VIEWMODEL_SCALE := 0.46
## How far ahead the wall probe looks, in metres.
const WALL_PROBE := 0.85
## Recoil spring constants, roughly critically damped.
const RECOIL_STIFFNESS := 260.0
const RECOIL_DAMPING := 27.0
## Metres of backwards travel for one unit of weapon recoil.
const RECOIL_TRAVEL := 2.6
const MELEE_SECONDS := 0.42

var _built: bool = false
var _weapon_id: int = WeaponDefs.NONE
var _aiming: bool = false
var _aim_blend: float = 0.0

var _rig: Node3D
var _model: MeshInstance3D
var _bolt: MeshInstance3D
var _muzzle: Node3D
var _probe: RayCast3D
var _probe_exceptions_done: bool = false

# Poses, filled by _apply_pose_for_weapon().
var _hip_position := Vector3(0.26, -0.22, -0.45)
var _hip_rotation := Vector3(0.02, -0.07, 0.035)
var _aim_position := Vector3(0.0, -0.055, -0.30)
var _aim_rotation := Vector3.ZERO
var _bolt_home := Vector3(0.055, 0.03, 0.02)
var _bolt_travel: float = 0.06

# Recoil spring state.
var _recoil_z: float = 0.0
var _recoil_z_vel: float = 0.0
var _recoil_pitch: float = 0.0
var _recoil_pitch_vel: float = 0.0
var _recoil_yaw: float = 0.0
var _recoil_yaw_vel: float = 0.0

# Bolt cycling.
var _bolt_time: float = 0.0
var _bolt_duration: float = 0.0
var _bolt_rotates: bool = false

# Reload and melee.
var _reload_time: float = 0.0
var _reload_duration: float = 0.0
var _reload_per_round: bool = false
var _reload_rounds: int = 5
var _melee_time: float = 0.0

# Sway and bob.
var _bob_phase: float = 0.0
var _sway := Vector2.ZERO
var _last_yaw: float = 0.0
var _last_pitch: float = 0.0
var _has_last_angles: bool = false
var _lower: float = 0.0

var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	setup()


## Builds the node hierarchy. Safe to call twice.
func setup() -> void:
	if _built:
		return
	_built = true
	_rng.randomize()

	_rig = Node3D.new()
	_rig.name = "Rig"
	add_child(_rig)

	_model = MeshInstance3D.new()
	_model.name = "Model"
	_model.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_model.extra_cull_margin = 4.0
	# The world models are built at true scale (a Garand really is 1.20 m), and a
	# true scale rifle held 45 cm from the eye at an 82 degree field of view eats
	# the lower right quarter of the screen. Every first person shooter shrinks
	# its view model for exactly this reason. Scaling the model rather than the
	# rig keeps the rig free for the recoil and sway animation, and the muzzle
	# node rides along so the flash and the tracer still start at the barrel.
	_model.scale = Vector3(VIEWMODEL_SCALE, VIEWMODEL_SCALE, VIEWMODEL_SCALE)
	_rig.add_child(_model)

	_bolt = MeshInstance3D.new()
	_bolt.name = "Bolt"
	_bolt.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_bolt.extra_cull_margin = 4.0
	_bolt.visible = false
	_model.add_child(_bolt)

	_muzzle = Node3D.new()
	_muzzle.name = "Muzzle"
	_model.add_child(_muzzle)

	_probe = RayCast3D.new()
	_probe.name = "WallProbe"
	_probe.target_position = Vector3(0.0, 0.0, -WALL_PROBE)
	_probe.collision_mask = Layers.WALK_MASK
	_probe.enabled = true
	_probe.exclude_parent = true
	add_child(_probe)

	visible = false

# --- Weapon selection ------------------------------------------------------

## Swaps the displayed model. `WeaponDefs.NONE` hides the viewmodel entirely.
func show_weapon(weapon_id: int) -> void:
	setup()
	_weapon_id = weapon_id
	if not WeaponDefs.is_valid(weapon_id):
		visible = false
		return
	visible = true
	var mesh: Mesh = Meshes.weapon_model(weapon_id)
	if mesh == null:
		mesh = _fallback_mesh(weapon_id)
	_model.mesh = mesh
	_apply_pose_for_weapon(weapon_id)
	_reset_animation()


func weapon_id() -> int:
	return _weapon_id


## Muzzle position in world space, where the flash and tracer start.
func muzzle_position() -> Vector3:
	if _muzzle == null:
		return global_position
	return _muzzle.global_position


## Direction the barrel points at, world space.
func muzzle_direction() -> Vector3:
	if _muzzle == null:
		return -global_transform.basis.z
	return -_muzzle.global_transform.basis.z


## Per weapon poses. The numbers are hand tuned: a pistol sits high and close,
## a machine gun sits low, wide and far, a scoped rifle centres on the optic.
func _apply_pose_for_weapon(id: int) -> void:
	var barrel := -0.58
	match id:
		WeaponDefs.M1911:
			_hip_position = Vector3(0.20, -0.19, -0.36)
			_aim_position = Vector3(0.0, -0.045, -0.26)
			_bolt_home = Vector3(0.0, 0.035, 0.0)
			_bolt_travel = 0.045
			_bolt_rotates = false
			barrel = -0.26
		WeaponDefs.THOMPSON, WeaponDefs.MP40:
			_hip_position = Vector3(0.25, -0.22, -0.44)
			_aim_position = Vector3(0.0, -0.052, -0.30)
			_bolt_home = Vector3(0.048, 0.030, 0.0)
			_bolt_travel = 0.055
			_bolt_rotates = false
			barrel = -0.48
		WeaponDefs.M1_GARAND:
			_hip_position = Vector3(0.26, -0.23, -0.46)
			_aim_position = Vector3(0.0, -0.050, -0.30)
			_bolt_home = Vector3(0.052, 0.032, -0.02)
			_bolt_travel = 0.075
			_bolt_rotates = false
			barrel = -0.66
		WeaponDefs.KAR98K:
			_hip_position = Vector3(0.26, -0.23, -0.46)
			_aim_position = Vector3(0.0, -0.048, -0.29)
			_bolt_home = Vector3(0.060, 0.030, 0.02)
			_bolt_travel = 0.090
			_bolt_rotates = true
			barrel = -0.64
		WeaponDefs.SPRINGFIELD:
			_hip_position = Vector3(0.27, -0.24, -0.48)
			_aim_position = Vector3(0.0, -0.028, -0.22)
			_bolt_home = Vector3(0.060, 0.030, 0.02)
			_bolt_travel = 0.090
			_bolt_rotates = true
			barrel = -0.68
		WeaponDefs.MG42:
			_hip_position = Vector3(0.30, -0.28, -0.52)
			_aim_position = Vector3(0.0, -0.075, -0.34)
			_bolt_home = Vector3(0.070, 0.040, 0.0)
			_bolt_travel = 0.085
			_bolt_rotates = false
			barrel = -0.80
		WeaponDefs.GRENADE:
			_hip_position = Vector3(0.22, -0.24, -0.38)
			_aim_position = Vector3(0.14, -0.16, -0.34)
			_bolt_home = Vector3.ZERO
			_bolt_travel = 0.0
			_bolt_rotates = false
			barrel = -0.10
		_:
			_hip_position = Vector3(0.26, -0.22, -0.45)
			_aim_position = Vector3(0.0, -0.055, -0.30)

	_hip_rotation = Vector3(0.02, -0.07, 0.035)
	_aim_rotation = Vector3.ZERO
	_muzzle.position = Vector3(0.0, 0.03, barrel)

	if _bolt_travel > 0.0:
		var bolt_mesh := BoxMesh.new()
		bolt_mesh.size = Vector3(0.035, 0.035, 0.11)
		_bolt.mesh = bolt_mesh
		_bolt.material_override = _gun_metal()
		_bolt.position = _bolt_home
		_bolt.visible = true
	else:
		_bolt.visible = false


func _gun_metal() -> Material:
	var mat: Material = MatLib.get_material("gun_metal")
	if mat != null:
		return mat
	var fallback := StandardMaterial3D.new()
	fallback.albedo_color = Palette.METAL
	fallback.metallic = 0.5
	fallback.roughness = 0.45
	return fallback


## Very rough stand in used only when the mesh library has nothing for this id,
## so a missing model never turns into an invisible weapon.
func _fallback_mesh(id: int) -> Mesh:
	var mesh := BoxMesh.new()
	match WeaponDefs.slot_of(id):
		WeaponDefs.SLOT_SECONDARY:
			mesh.size = Vector3(0.05, 0.13, 0.22)
		WeaponDefs.SLOT_THROWN:
			mesh.size = Vector3(0.09, 0.12, 0.09)
		_:
			mesh.size = Vector3(0.06, 0.12, 0.90)
	mesh.material = _gun_metal()
	return mesh

# --- Animation triggers ----------------------------------------------------

## One shot: kicks the spring and cycles the action.
func play_fire() -> void:
	setup()
	var kick: float = WeaponDefs.recoil_pitch(_weapon_id)
	_recoil_z_vel += RECOIL_TRAVEL * maxf(kick, 0.004) * 9.0
	_recoil_pitch_vel += kick * 14.0
	_recoil_yaw_vel += _rng.randf_range(-1.0, 1.0) * WeaponDefs.recoil_yaw(_weapon_id) * 12.0
	if WeaponDefs.is_bolt_action(_weapon_id):
		_bolt_duration = 0.55
	else:
		_bolt_duration = 0.09
	_bolt_time = _bolt_duration


## Plays the reload motion for `seconds`. `per_round` swaps the single drop and
## rise for the repeated push of a bolt action being topped off.
func play_reload(seconds: float, per_round: bool) -> void:
	setup()
	if seconds <= 0.0:
		return
	_reload_duration = seconds
	_reload_time = seconds
	_reload_per_round = per_round
	_reload_rounds = maxi(WeaponDefs.magazine(_weapon_id), 1)
	_bolt_time = 0.0


func play_melee() -> void:
	setup()
	_melee_time = MELEE_SECONDS


func set_aiming(aiming: bool) -> void:
	_aiming = aiming


func is_aiming() -> bool:
	return _aiming


## True while a reload motion is still playing.
func is_busy() -> bool:
	return _reload_time > 0.0 or _melee_time > 0.0


func _reset_animation() -> void:
	_recoil_z = 0.0
	_recoil_z_vel = 0.0
	_recoil_pitch = 0.0
	_recoil_pitch_vel = 0.0
	_recoil_yaw = 0.0
	_recoil_yaw_vel = 0.0
	_bolt_time = 0.0
	_reload_time = 0.0
	_melee_time = 0.0
	if _bolt != null:
		_bolt.position = _bolt_home
		_bolt.rotation = Vector3.ZERO

# --- Frame update ----------------------------------------------------------

## Drives every spring and offset. Called by the player once per frame.
func update(delta: float, velocity: Vector3, is_aiming: bool) -> void:
	if not _built or not visible:
		return
	var step: float = clampf(delta, 0.0, 0.1)
	_aiming = is_aiming
	_ensure_probe_exceptions()

	var target := 1.0 if _aiming else 0.0
	_aim_blend = move_toward(_aim_blend, target, step / maxf(AIM_BLEND, 0.001))
	var blend := _smooth(_aim_blend)

	_advance_recoil(step)
	_advance_bolt(step)
	_advance_timers(step)
	_advance_sway(step, velocity)
	_advance_lowering(step)

	var pos: Vector3 = _hip_position.lerp(_aim_position, blend)
	var rot: Vector3 = _hip_rotation.lerp(_aim_rotation, blend)

	pos += _sway_offset(blend)
	rot += _sway_rotation(blend)

	pos += _reload_position()
	rot += _reload_rotation()

	pos += _melee_position()
	rot += _melee_rotation()

	pos.z += _recoil_z
	rot.x += _recoil_pitch
	rot.y += _recoil_yaw

	# Weapon lowering: pull the weapon back, drop it and point the muzzle up so
	# it stops eating the wall the player is leaning against.
	pos.z += 0.22 * _lower
	pos.y -= 0.06 * _lower
	rot.x += 0.62 * _lower
	rot.z += 0.22 * _lower

	_rig.position = pos
	_rig.rotation = rot


func _smooth(t: float) -> float:
	return t * t * (3.0 - 2.0 * t)


## Three damped springs (backwards travel, pitch, yaw), integrated in place.
## A spring rather than a curve is what makes a Thompson burst feel different
## from a Garand shot without a single keyframe.
func _advance_recoil(delta: float) -> void:
	_recoil_z_vel += (-RECOIL_STIFFNESS * _recoil_z - RECOIL_DAMPING * _recoil_z_vel) * delta
	_recoil_z += _recoil_z_vel * delta
	_recoil_pitch_vel += (-RECOIL_STIFFNESS * _recoil_pitch \
			- RECOIL_DAMPING * _recoil_pitch_vel) * delta
	_recoil_pitch += _recoil_pitch_vel * delta
	_recoil_yaw_vel += (-RECOIL_STIFFNESS * _recoil_yaw \
			- RECOIL_DAMPING * _recoil_yaw_vel) * delta
	_recoil_yaw += _recoil_yaw_vel * delta


## The bolt travels back then forward. A bolt action also rolls its handle up,
## which is the whole reason the node exists instead of a baked animation.
func _advance_bolt(delta: float) -> void:
	if _bolt == null or not _bolt.visible:
		return
	if _bolt_time <= 0.0:
		_bolt.position = _bolt_home
		_bolt.rotation = Vector3.ZERO
		return
	_bolt_time = maxf(_bolt_time - delta, 0.0)
	var progress := 1.0 - _bolt_time / maxf(_bolt_duration, 0.001)
	var curve := sin(clampf(progress, 0.0, 1.0) * PI)
	_bolt.position = _bolt_home + Vector3(0.0, 0.0, _bolt_travel * curve)
	if _bolt_rotates:
		_bolt.rotation = Vector3(0.0, 0.0, -1.15 * curve)


func _advance_timers(delta: float) -> void:
	if _reload_time > 0.0:
		_reload_time = maxf(_reload_time - delta, 0.0)
	if _melee_time > 0.0:
		_melee_time = maxf(_melee_time - delta, 0.0)


## Magazine reload: one long drop, roll and rise. Per round reload: a shallow
## dip plus a repeated push, one beat per round going in.
func _reload_position() -> Vector3:
	if _reload_time <= 0.0:
		return Vector3.ZERO
	var progress := 1.0 - _reload_time / maxf(_reload_duration, 0.001)
	var envelope := sin(clampf(progress, 0.0, 1.0) * PI)
	if _reload_per_round:
		var beat := sin(progress * PI * 2.0 * float(_reload_rounds))
		return Vector3(0.02 * beat, -0.09 * envelope - 0.02 * absf(beat), 0.03 * envelope)
	return Vector3(-0.05 * envelope, -0.24 * envelope, 0.10 * envelope)


func _reload_rotation() -> Vector3:
	if _reload_time <= 0.0:
		return Vector3.ZERO
	var progress := 1.0 - _reload_time / maxf(_reload_duration, 0.001)
	var envelope := sin(clampf(progress, 0.0, 1.0) * PI)
	if _reload_per_round:
		var beat := sin(progress * PI * 2.0 * float(_reload_rounds))
		return Vector3(0.18 * envelope, 0.10 * beat, 0.30 * envelope)
	return Vector3(0.34 * envelope, 0.22 * envelope, 0.62 * envelope)


func _melee_position() -> Vector3:
	if _melee_time <= 0.0:
		return Vector3.ZERO
	var progress := 1.0 - _melee_time / MELEE_SECONDS
	var thrust := sin(clampf(progress, 0.0, 1.0) * PI)
	return Vector3(-0.10 * thrust, 0.05 * thrust, -0.26 * thrust)


func _melee_rotation() -> Vector3:
	if _melee_time <= 0.0:
		return Vector3.ZERO
	var progress := 1.0 - _melee_time / MELEE_SECONDS
	var thrust := sin(clampf(progress, 0.0, 1.0) * PI)
	return Vector3(-0.45 * thrust, 0.55 * thrust, -0.30 * thrust)


## Weapon lag: the model trails the camera rotation, then catches up. Aiming
## divides the amplitude, walking feeds the bob.
func _advance_sway(delta: float, velocity: Vector3) -> void:
	var yaw := global_rotation.y
	var pitch := global_rotation.x
	if not _has_last_angles:
		_last_yaw = yaw
		_last_pitch = pitch
		_has_last_angles = true
	var delta_yaw := wrapf(yaw - _last_yaw, -PI, PI)
	var delta_pitch := pitch - _last_pitch
	_last_yaw = yaw
	_last_pitch = pitch

	var damping: float = clampf(1.0 - delta * 9.0, 0.0, 1.0)
	_sway.x = clampf(_sway.x * damping - delta_yaw * 0.55, -0.09, 0.09)
	_sway.y = clampf(_sway.y * damping + delta_pitch * 0.45, -0.07, 0.07)

	var planar := Vector2(velocity.x, velocity.z).length()
	var bob_speed: float = clampf(planar, 0.0, 9.0)
	_bob_phase += delta * (5.5 + bob_speed * 0.55)
	if _bob_phase > TAU * 64.0:
		_bob_phase -= TAU * 64.0


func _sway_offset(blend: float) -> Vector3:
	var scale: float = lerpf(1.0, 0.28, blend)
	var amplitude: float = 0.012 * scale
	var bob := Vector3(
		sin(_bob_phase) * amplitude,
		absf(cos(_bob_phase)) * amplitude * 0.8 - amplitude * 0.4,
		0.0)
	return Vector3(_sway.x * scale, _sway.y * scale, 0.0) + bob


func _sway_rotation(blend: float) -> Vector3:
	var scale: float = lerpf(1.0, 0.30, blend)
	return Vector3(-_sway.y * 1.6 * scale, _sway.x * 1.4 * scale, _sway.x * 2.0 * scale)


## Reads the short probe and eases the lowering factor so the weapon does not
## snap up and down when the player brushes past a doorframe.
func _advance_lowering(delta: float) -> void:
	var target := 0.0
	if _probe != null and _probe.is_colliding():
		var distance := global_position.distance_to(_probe.get_collision_point())
		target = clampf(1.0 - distance / WALL_PROBE, 0.0, 1.0)
	var rate: float = 10.0 if target > _lower else 6.0
	_lower = move_toward(_lower, target, delta * rate)


## The probe must not report the body carrying the camera, otherwise the
## weapon is permanently lowered.
func _ensure_probe_exceptions() -> void:
	if _probe_exceptions_done or _probe == null:
		return
	var node: Node = self
	var hops := 0
	while node != null and hops < 6:
		var body := node as CollisionObject3D
		if body != null:
			_probe.add_exception(body)
			_probe_exceptions_done = true
			return
		node = node.get_parent()
		hops += 1
	_probe_exceptions_done = true
