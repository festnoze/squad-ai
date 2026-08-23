class_name Player
extends CharacterBody3D
## First person player: locomotion, stances, weapons, health and interaction.
##
## The node origin sits at the feet. The collision capsule is offset upwards by
## half its height, and the camera rig (a child at the origin) is fed the eye
## height every frame so a stance change glides instead of snapping.
##
## The player never touches the HUD. It exposes signals, `prompt_text` and
## `noise_radius()`, and lets the interface read them.

signal health_changed(current: float, maximum: float)
signal died()
signal weapon_changed(weapon: Weapon)
signal ammo_changed(weapon: Weapon)
signal damaged(amount: float, from_direction: Vector3)
signal footstep(surface: String)
signal fired(weapon_id: int)
signal used(target: Node)
signal bandages_changed(count: int)

const MAX_HEALTH := 100.0
const STAND_HEIGHT := 1.80
const CROUCH_HEIGHT := 1.20
const PRONE_HEIGHT := 0.60
const EYE_OFFSET := 0.12          # eyes below the top of the capsule

# Stances
const STANCE_STAND := 0
const STANCE_CROUCH := 1
const STANCE_PRONE := 2

const BODY_RADIUS := 0.38

# Locomotion, metres per second.
const WALK_SPEED := 4.4
const SPRINT_SPEED := 7.2
const CROUCH_SPEED := 2.2
const PRONE_SPEED := 1.0
const AIM_SPEED := 2.6
## Exponential approach rates. Strong on the ground, nearly nothing in the air.
const GROUND_ACCEL := 12.0
const AIR_ACCEL := 2.0
const JUMP_HEIGHT := 1.05
const STANCE_CHANGE_TIME := 0.28

# Health.
const REGEN_DELAY := 6.0
const REGEN_RATE := 7.0
const REGEN_STEP := 25.0
const LOW_HEALTH := 30.0
const BANDAGE_TIME := 2.5
const BANDAGE_HEAL := 40.0
const MAX_BANDAGES := 5

# Combat.
const MELEE_DAMAGE := 55.0
const MELEE_RANGE := 2.2
const MELEE_RECOVERY := 0.8
const MELEE_WINDUP := 0.14
const MELEE_BACK_MULTIPLIER := 3.0
const USE_RANGE := 2.5
const BOLT_TIME := 1.05
const HEAVY_RELOAD_TIME := 2.2
const TRACER_RANGE := 420.0

# Noise, in metres of hearing radius.
const NOISE_SHOT := 180.0
const NOISE_SHOT_DECAY := 260.0
const NOISE_SPRINT := 26.0
const NOISE_WALK := 14.0
const NOISE_CROUCH := 6.0
const NOISE_PRONE := 3.0

const GRENADE_SCRIPT := "res://src/weapons/grenade.gd"
const GRENADE_FUSE := 3.6
const GRENADE_THROW_SPEED := 15.0
const GRENADE_MIN_FUSE := 0.4

var health: float = MAX_HEALTH
var rig: CameraRig = null
var weapons: Array[Weapon] = []    # index = WeaponDefs.SLOT_*
var current_slot: int = WeaponDefs.SLOT_PRIMARY
var bandages: int = 3
var is_aiming: bool = false
var is_sprinting: bool = false
var stance: int = STANCE_STAND

## Action prompt for the HUD, in French. Empty when nothing is targeted.
## The HUD reads this every frame; the player never calls the HUD itself.
var prompt_text: String = ""

var _world: GameWorld = null
var _viewmodel: Viewmodel = null
var _shape: CollisionShape3D = null
var _capsule: CapsuleShape3D = null
var _rng := RandomNumberGenerator.new()

var _alive := true
var _now := 0.0
var _gravity := 19.6
var _jump_speed := 6.42
var _built := false

var _stance_height := STAND_HEIGHT
var _prone_toggled := false
var _stance_locked := 0.0

var _trigger_ready := true
var _dry_attempts := 0
var _dry_cooldown := 0.0
var _bolt_timer := 0.0
var _bolt_kicked := false
var _was_aiming := false

var _melee_timer := 0.0
var _melee_windup := -1.0

var _bandage_timer := 0.0
var _bandaging := false
var _regen_timer := 0.0
var _heartbeat_timer := 0.0
var _breath_timer := 0.0

var _cooking := false
var _cook_time := 0.0

var _shot_noise := 0.0
var _step_distance := 0.0
var _last_surface := "dirt"
var _was_grounded := true
var _fall_speed := 0.0

var _look_target: Node = null
var _mounted: Node3D = null
var _mount_cooldown := 0.0


func _ready() -> void:
	_rng.randomize()
	_gravity = float(ProjectSettings.get_setting("physics/3d/default_gravity", 19.6))
	_jump_speed = sqrt(2.0 * _gravity * JUMP_HEIGHT)
	collision_layer = Layers.PLAYER
	collision_mask = Layers.WALK_MASK
	if not is_in_group("damageable"):
		add_to_group("damageable")
	if not is_in_group("player"):
		add_to_group("player")
	floor_max_angle = deg_to_rad(52.0)
	floor_snap_length = 0.45
	floor_stop_on_slope = true
	slide_on_ceiling = true
	wall_min_slide_angle = deg_to_rad(12.0)
	_build()


func _build() -> void:
	if _built:
		return
	_built = true

	_capsule = CapsuleShape3D.new()
	_capsule.radius = BODY_RADIUS
	_capsule.height = STAND_HEIGHT
	_shape = CollisionShape3D.new()
	_shape.name = "Body"
	_shape.shape = _capsule
	_shape.position = Vector3(0.0, STAND_HEIGHT * 0.5, 0.0)
	add_child(_shape)

	rig = CameraRig.new()
	rig.name = "CameraRig"
	add_child(rig)
	rig.setup()
	if Game != null:
		rig.set_base_fov(Game.fov)

	_viewmodel = Viewmodel.new()
	_viewmodel.name = "Viewmodel"
	if rig.camera != null:
		rig.camera.add_child(_viewmodel)
	else:
		rig.add_child(_viewmodel)
	_viewmodel.setup()

	if weapons.is_empty():
		_default_loadout()
	_apply_stance_shape()
	_refresh_viewmodel()


func _default_loadout() -> void:
	weapons.resize(3)
	weapons[WeaponDefs.SLOT_PRIMARY] = Weapon.new(WeaponDefs.M1_GARAND, true)
	weapons[WeaponDefs.SLOT_SECONDARY] = Weapon.new(WeaponDefs.M1911, true)
	var thrown := Weapon.new(WeaponDefs.GRENADE, true)
	thrown.in_magazine = 1
	thrown.reserve = 3
	weapons[WeaponDefs.SLOT_THROWN] = thrown
	current_slot = WeaponDefs.SLOT_PRIMARY


func setup(game_world: GameWorld) -> void:
	_build()
	_world = game_world
	if _world != null:
		teleport(_world.spawn_point())
	health = MAX_HEALTH
	_alive = true
	health_changed.emit(health, MAX_HEALTH)
	bandages_changed.emit(bandages)
	_refresh_viewmodel()


func teleport(pos: Vector3) -> void:
	var target := pos
	target = Heightfield.clamp_to_bounds(target)
	target.y = pos.y
	global_position = target
	velocity = Vector3.ZERO
	_step_distance = 0.0
	_fall_speed = 0.0


# --- frame -------------------------------------------------------------------


func _unhandled_input(event: InputEvent) -> void:
	if not _alive or not _built:
		return
	if event is InputEventMouseMotion:
		if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
			rig.look((event as InputEventMouseMotion).relative)
		return
	# Wheel presses last a single event, so they are read here and not polled.
	if event.is_action_pressed("weapon_next"):
		cycle_weapon(1)
	elif event.is_action_pressed("weapon_prev"):
		cycle_weapon(-1)
	elif event.is_action_pressed("weapon_1"):
		select_slot(WeaponDefs.SLOT_PRIMARY)
	elif event.is_action_pressed("weapon_2"):
		select_slot(WeaponDefs.SLOT_SECONDARY)
	elif event.is_action_pressed("weapon_3"):
		select_slot(WeaponDefs.SLOT_PRIMARY)
	elif event.is_action_pressed("weapon_4"):
		select_slot(WeaponDefs.SLOT_SECONDARY)


func _physics_process(delta: float) -> void:
	if not _built:
		return
	_now += delta
	_tick_timers(delta)
	if not _alive:
		_dead_physics(delta)
		_update_camera(delta)
		return
	_read_intent()
	if _mounted != null:
		_mounted_physics(delta)
	else:
		_move(delta)
		_update_weapon(delta)
		_update_melee(delta)
	# Outside the branch on purpose: a pin already pulled has to keep burning
	# whatever the player is doing, or the release event is lost. See the comment
	# on _update_grenade.
	_update_grenade(delta)
	_update_health(delta)
	_update_interaction()
	_update_camera(delta)
	_clamp_to_world()


func _tick_timers(delta: float) -> void:
	_shot_noise = maxf(0.0, _shot_noise - NOISE_SHOT_DECAY * delta)
	_dry_cooldown = maxf(0.0, _dry_cooldown - delta)
	_melee_timer = maxf(0.0, _melee_timer - delta)
	_stance_locked = maxf(0.0, _stance_locked - delta)
	_mount_cooldown = maxf(0.0, _mount_cooldown - delta)
	if _bolt_timer > 0.0:
		_bolt_timer = maxf(0.0, _bolt_timer - delta)
		if not _bolt_kicked and _bolt_timer <= BOLT_TIME * 0.72:
			_bolt_kicked = true
			# Working the bolt drags the sight off target for a moment.
			rig.add_recoil(-0.014, 0.022)
			rig.shake(0.006, 0.22)
			Sfx.play_at("bolt", global_position, -3.0)


func _dead_physics(delta: float) -> void:
	velocity.x = move_toward(velocity.x, 0.0, 14.0 * delta)
	velocity.z = move_toward(velocity.z, 0.0, 14.0 * delta)
	if not is_on_floor():
		velocity.y -= _gravity * delta
	else:
		velocity.y = 0.0
	move_and_slide()


# --- intent ------------------------------------------------------------------


func _read_intent() -> void:
	var weapon := current_weapon()
	var heavy_reload := weapon != null and weapon.is_reloading \
			and WeaponDefs.reload_time(weapon.id) >= HEAVY_RELOAD_TIME

	# A gunner served an emplacement standing behind its shield, so the stance
	# keys are ignored while mounted. Without this guard, pressing X on a MG42
	# dropped the capsule to 0.60 m and the eye to 0.48 m (under the gun, behind
	# the sandbags) while the weapon kept firing from its own position, and it
	# moved the player's head hitbox a metre and a fifth down at the same time.
	if _mounted == null:
		if Input.is_action_just_pressed("prone"):
			if stance == STANCE_PRONE:
				_prone_toggled = false
			else:
				_prone_toggled = true
		if _prone_toggled and stance != STANCE_PRONE:
			_set_stance(STANCE_PRONE)
		elif not _prone_toggled:
			var wants_crouch := Input.is_action_pressed("crouch")
			_set_stance(STANCE_CROUCH if wants_crouch else STANCE_STAND)
		elif stance == STANCE_PRONE and Input.is_action_pressed("crouch"):
			_prone_toggled = false

	var can_aim := not _bandaging and _melee_timer <= 0.0
	is_aiming = can_aim and Input.is_action_pressed("aim") and current_weapon() != null \
			and current_slot != WeaponDefs.SLOT_THROWN

	var forward_input := Input.get_action_strength("move_forward") \
			- Input.get_action_strength("move_back")
	is_sprinting = Input.is_action_pressed("sprint") \
			and forward_input > 0.4 \
			and not is_aiming \
			and not _bandaging \
			and not heavy_reload \
			and stance == STANCE_STAND \
			and is_on_floor()
	if is_sprinting:
		is_aiming = false


func _set_stance(new_stance: int) -> void:
	if new_stance == stance or _stance_locked > 0.0:
		return
	var target_height := _height_of(new_stance)
	if target_height > _height_of(stance) and not _has_headroom(target_height):
		# Something above the head: stay low.
		return
	stance = new_stance
	if stance != STANCE_PRONE:
		_prone_toggled = false
	_stance_locked = STANCE_CHANGE_TIME * 0.5
	_apply_stance_shape()


func _height_of(which: int) -> float:
	match which:
		STANCE_CROUCH:
			return CROUCH_HEIGHT
		STANCE_PRONE:
			return PRONE_HEIGHT
		_:
			return STAND_HEIGHT


func _apply_stance_shape() -> void:
	_stance_height = _height_of(stance)
	if _capsule == null or _shape == null:
		return
	# A capsule cannot be shorter than its two hemispheres.
	var h := maxf(_stance_height, BODY_RADIUS * 2.0 + 0.02)
	_capsule.height = h
	_shape.position = Vector3(0.0, h * 0.5, 0.0)


func _has_headroom(target_height: float) -> bool:
	var space := get_world_3d().direct_space_state
	if space == null:
		return true
	var probe := CapsuleShape3D.new()
	probe.radius = maxf(BODY_RADIUS - 0.03, 0.05)
	probe.height = maxf(target_height, probe.radius * 2.0 + 0.02)
	var params := PhysicsShapeQueryParameters3D.new()
	params.shape = probe
	params.transform = Transform3D(Basis(),
			global_position + Vector3(0.0, probe.height * 0.5 + 0.03, 0.0))
	params.collision_mask = Layers.WALK_MASK
	params.exclude = [get_rid()]
	params.margin = 0.0
	return space.intersect_shape(params, 1).is_empty()


# --- locomotion --------------------------------------------------------------


func _move(delta: float) -> void:
	var grounded := is_on_floor()
	if grounded:
		if not _was_grounded:
			_on_landed()
		velocity.y = maxf(velocity.y, -0.1)
	else:
		velocity.y -= _gravity * delta
		_fall_speed = minf(_fall_speed, velocity.y)
	_was_grounded = grounded

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var yaw_basis := Basis(Vector3.UP, rig.rotation.y)
	var wish := yaw_basis.x * input_dir.x + yaw_basis.z * input_dir.y
	wish.y = 0.0
	if wish.length_squared() > 1.0:
		wish = wish.normalized()

	var speed := _target_speed()
	var goal := wish * speed
	var rate := GROUND_ACCEL if grounded else AIR_ACCEL
	var blend := 1.0 - exp(-rate * delta)
	velocity.x = lerpf(velocity.x, goal.x, blend)
	velocity.z = lerpf(velocity.z, goal.z, blend)

	if grounded and Input.is_action_just_pressed("jump") and not _bandaging:
		if stance != STANCE_STAND:
			# The first press stands up, the second one jumps.
			_prone_toggled = false
			_set_stance(STANCE_STAND)
		elif _melee_timer <= 0.0:
			# Half a step of gravity is removed up front: the first airborne
			# frame is integrated without it, and that bias would otherwise
			# push the apex above JUMP_HEIGHT.
			velocity.y = _jump_speed - _gravity * delta * 0.5
			_shot_noise = maxf(_shot_noise, 8.0)

	move_and_slide()
	_update_footsteps(delta, grounded)


func _target_speed() -> float:
	var base := WALK_SPEED
	match stance:
		STANCE_CROUCH:
			base = CROUCH_SPEED
		STANCE_PRONE:
			base = PRONE_SPEED
		_:
			if is_sprinting:
				base = SPRINT_SPEED * _weight_factor()
			elif is_aiming:
				base = AIM_SPEED
	if _bandaging:
		base = minf(base, CROUCH_SPEED)
	if _melee_timer > 0.0:
		base *= 0.75
	var weapon := current_weapon()
	if weapon != null and weapon.is_reloading \
			and WeaponDefs.reload_time(weapon.id) >= HEAVY_RELOAD_TIME:
		base *= 0.85
	return base


## A heavy weapon shaves a little off the sprint. The MG42 is not a sprinting
## weapon, the pistol barely costs anything.
func _weight_factor() -> float:
	var weapon := current_weapon()
	if weapon == null:
		return 1.0
	var weight := WeaponDefs.weight(weapon.id)
	return clampf(1.0 - maxf(0.0, weight - 3.0) * 0.022, 0.80, 1.0)


func _on_landed() -> void:
	var impact := absf(_fall_speed)
	_fall_speed = 0.0
	if impact > 4.0:
		rig.shake(clampf(impact * 0.0016, 0.004, 0.03), 0.22)
		_emit_step()
	if impact > 15.0:
		# Long fall: it hurts, scaled so a two storey drop is survivable.
		var hurt := (impact - 15.0) * 7.0
		take_damage(hurt, null, global_position, false)


func _update_footsteps(delta: float, grounded: bool) -> void:
	if not grounded:
		return
	var speed := Vector2(velocity.x, velocity.z).length()
	if speed < 0.5:
		_step_distance = maxf(0.0, _step_distance - delta * 0.5)
		return
	_step_distance += speed * delta
	var stride := 2.3
	if is_sprinting:
		stride = 2.9
	elif stance == STANCE_CROUCH:
		stride = 1.7
	elif stance == STANCE_PRONE:
		stride = 1.3
	if _step_distance >= stride:
		_step_distance -= stride
		_emit_step()


func _emit_step() -> void:
	var surface := _surface_here()
	_last_surface = surface
	footstep.emit(surface)
	Sfx.play_step(surface, global_position)


func _surface_here() -> String:
	if _world == null:
		return "dirt"
	var hf := _world.heightfield()
	if hf == null:
		return "dirt"
	return hf.surface_at(global_position.x, global_position.z)


func _clamp_to_world() -> void:
	var pos := global_position
	var clamped := Heightfield.clamp_to_bounds(pos)
	clamped.y = pos.y
	if not clamped.is_equal_approx(pos):
		global_position = clamped
		velocity.x *= 0.2
		velocity.z *= 0.2


# --- weapons -----------------------------------------------------------------


func _update_weapon(delta: float) -> void:
	var weapon := current_weapon()
	if weapon == null:
		return
	if weapon.is_reloading:
		if weapon.tick_reload(_now):
			_dry_attempts = 0
			ammo_changed.emit(weapon)
	if Input.is_action_just_pressed("reload"):
		_start_reload(weapon)
	if current_slot == WeaponDefs.SLOT_THROWN:
		return
	_update_trigger(weapon)


func _update_trigger(weapon: Weapon) -> void:
	var held := Input.is_action_pressed("fire")
	var just := Input.is_action_just_pressed("fire")
	if not held:
		_trigger_ready = true
		return
	if _bandaging or _melee_timer > 0.0 or _bolt_timer > 0.0 or weapon.is_reloading:
		return
	if is_sprinting:
		# Firing out of a sprint first brings the weapon back up.
		is_sprinting = false
		return
	var automatic := WeaponDefs.is_automatic(weapon.id)
	if not automatic and not _trigger_ready:
		return
	if weapon.in_magazine <= 0:
		if just or (automatic and _dry_cooldown <= 0.0):
			_dry_fire(weapon)
		_trigger_ready = false
		return
	if not weapon.can_fire(_now):
		return
	_trigger_ready = false
	_shoot(weapon)


func _dry_fire(weapon: Weapon) -> void:
	# Every distinct trigger pull counts, but the click only sounds a few times
	# a second so holding an empty automatic does not turn into a rattle.
	_dry_attempts += 1
	if _dry_cooldown <= 0.0:
		_dry_cooldown = 0.25
		Sfx.play("dry_fire", -4.0)
	# A forced reload feels like the game taking the mouse away. Two attempts
	# on an empty chamber is a clear enough intent.
	if _dry_attempts >= 2:
		_start_reload(weapon)


func _shoot(weapon: Weapon) -> void:
	if not weapon.fire(_now):
		return
	var wid := weapon.id
	var moving := Vector2(velocity.x, velocity.z).length() > 1.0
	var spread := weapon.current_spread(is_aiming, moving, stance != STANCE_STAND)
	var origin := eye_position()
	var direction := aim_direction()
	var result := Ballistics.fire(get_world_3d(), origin, direction, wid, spread, self, _rng)

	var recoil_scale := 1.0
	if is_aiming:
		recoil_scale *= 0.72
	if stance == STANCE_CROUCH:
		recoil_scale *= 0.84
	elif stance == STANCE_PRONE:
		recoil_scale *= 0.62
	var yaw_sign := 1.0 if _rng.randf() < 0.5 else -1.0
	var yaw_kick := WeaponDefs.recoil_yaw(wid) * yaw_sign * _rng.randf_range(0.55, 1.25)
	var pitch_kick := WeaponDefs.recoil_pitch(wid) * _rng.randf_range(0.85, 1.15)
	rig.add_recoil(pitch_kick * recoil_scale, yaw_kick * recoil_scale)
	rig.shake(pitch_kick * 0.22, 0.09)
	_viewmodel.play_fire()

	_spawn_shot_vfx(origin, direction, result)
	Sfx.play_shot(WeaponDefs.fire_sample(wid), global_position)
	War.record_shot(_hit_a_target(result))
	_shot_noise = NOISE_SHOT
	fired.emit(wid)
	ammo_changed.emit(weapon)

	# The Garand sings when the en bloc clip flies out on the eighth round.
	if wid == WeaponDefs.M1_GARAND and weapon.in_magazine <= 0:
		Sfx.play("garand_ping", -2.0)
	if wid == WeaponDefs.SPRINGFIELD or wid == WeaponDefs.KAR98K:
		_bolt_timer = BOLT_TIME
		_bolt_kicked = false


func _spawn_shot_vfx(origin: Vector3, direction: Vector3, result: Ballistics.HitResult) -> void:
	var vfx := _vfx()
	if vfx == null:
		return
	var muzzle := _muzzle_position(origin, direction)
	var wid := -1
	var weapon := current_weapon()
	if weapon != null:
		wid = weapon.id
	var end := origin + direction * TRACER_RANGE
	if result != null and result.hit:
		end = result.position
	vfx.muzzle_flash(muzzle, direction, 0.7 if is_aiming else 1.0)
	var tracer_speed := 260.0
	if wid >= 0:
		tracer_speed = maxf(120.0, WeaponDefs.muzzle_velocity(wid) * 0.35)
	vfx.tracer(muzzle, end, tracer_speed)
	var eject := rig.camera.global_transform.basis.x if rig.camera != null else global_transform.basis.x
	vfx.shell_casing(muzzle, eject)


func _muzzle_position(origin: Vector3, direction: Vector3) -> Vector3:
	if _viewmodel != null:
		var m := _viewmodel.muzzle_position()
		if m != Vector3.ZERO:
			return m
	return origin + direction * 0.45


func _hit_a_target(result: Ballistics.HitResult) -> bool:
	if result == null or not result.hit:
		return false
	var node := result.collider as Node
	if node == null:
		return false
	return node.is_in_group("damageable")


func _start_reload(weapon: Weapon) -> void:
	if weapon == null or weapon.is_reloading or _bandaging or _bolt_timer > 0.0:
		return
	if current_slot == WeaponDefs.SLOT_THROWN:
		return
	var duration := weapon.start_reload(_now)
	if duration <= 0.0:
		return
	_dry_attempts = 0
	is_aiming = false
	_viewmodel.play_reload(duration, WeaponDefs.reloads_per_round(weapon.id))
	Sfx.play_at(WeaponDefs.reload_sample(weapon.id), global_position, -2.0)
	_shot_noise = maxf(_shot_noise, 12.0)
	ammo_changed.emit(weapon)


func _refresh_viewmodel() -> void:
	var weapon := current_weapon()
	if _viewmodel == null:
		return
	if weapon == null:
		_viewmodel.show_weapon(WeaponDefs.NONE)
		return
	_viewmodel.show_weapon(weapon.id)


func current_weapon() -> Weapon:
	if current_slot < 0 or current_slot >= weapons.size():
		return null
	return weapons[current_slot]


func give_weapon(weapon_id: int, ammo: int) -> void:
	if weapon_id < 0 or weapon_id >= WeaponDefs.COUNT:
		return
	var slot := WeaponDefs.slot_of(weapon_id)
	if slot < 0:
		return
	if weapons.size() < 3:
		weapons.resize(3)
	var existing := weapons[slot]
	if existing != null and existing.id == weapon_id:
		existing.add_ammo(maxi(0, ammo))
		ammo_changed.emit(existing)
		return
	var weapon := Weapon.new(weapon_id, false)
	var mag := WeaponDefs.magazine(weapon_id)
	weapon.in_magazine = clampi(ammo, 0, maxi(mag, 1))
	weapon.add_ammo(maxi(0, ammo - weapon.in_magazine))
	weapons[slot] = weapon
	if slot == current_slot:
		_refresh_viewmodel()
		weapon_changed.emit(weapon)
	ammo_changed.emit(weapon)


func give_ammo(weapon_id: int, rounds: int) -> int:
	for weapon in weapons:
		if weapon != null and weapon.id == weapon_id:
			var taken := weapon.add_ammo(rounds)
			if taken > 0:
				ammo_changed.emit(weapon)
			return taken
	return 0


func give_bandage(count: int) -> void:
	var before := bandages
	bandages = clampi(bandages + count, 0, MAX_BANDAGES)
	if bandages != before:
		bandages_changed.emit(bandages)


func select_slot(slot: int) -> void:
	if slot < 0 or slot >= weapons.size() or slot == current_slot:
		return
	if weapons[slot] == null:
		return
	var previous := current_weapon()
	if previous != null and previous.is_reloading:
		previous.cancel_reload()
	current_slot = slot
	_trigger_ready = false
	_bolt_timer = 0.0
	_dry_attempts = 0
	is_aiming = false
	var weapon := current_weapon()
	_refresh_viewmodel()
	weapon_changed.emit(weapon)
	ammo_changed.emit(weapon)


func cycle_weapon(direction: int) -> void:
	if direction == 0 or weapons.is_empty():
		return
	var step := 1 if direction > 0 else -1
	# The thrown slot is not a weapon you hold, it stays out of the cycle.
	var usable := mini(weapons.size(), WeaponDefs.SLOT_THROWN)
	if usable <= 0:
		return
	var slot := current_slot
	for i in usable:
		slot = posmod(slot + step, usable)
		if weapons[slot] != null:
			select_slot(slot)
			return


# --- grenades ----------------------------------------------------------------


## Called EVERY physics frame, including while bandaging and while serving an
## emplacement.
##
## It used to bail out early in those states, and that quietly armed a suicide:
## `is_action_just_released` is true for a single physics frame, so a player who
## let go of G during a bandage had the release swallowed. The pin stayed pulled,
## `_cook_time` froze, and once the bandage finished the timer resumed and the
## "held far too long" branch threw the grenade on its own, with a fuse forced
## down to 0.4 s, a few metres from a player who had pressed nothing. Only the
## act of PULLING a new pin is blocked in those states; a live grenade always
## keeps ticking and always answers the trigger.
func _update_grenade(delta: float) -> void:
	if Input.is_action_just_pressed("grenade") and not _cooking:
		if _bandaging or _mounted != null:
			return
		if _grenade_count() <= 0:
			Sfx.play("dry_fire", -6.0)
			return
		_cooking = true
		_cook_time = 0.0
		Sfx.play("grenade_pin", -2.0)
		return
	if not _cooking:
		return
	_cook_time += delta
	if Input.is_action_just_released("grenade"):
		_throw_grenade()
	elif _cook_time >= GRENADE_FUSE - GRENADE_MIN_FUSE:
		# Held far too long: it leaves the hand whether the player likes it or not.
		_throw_grenade()


func _grenade_count() -> int:
	if weapons.size() <= WeaponDefs.SLOT_THROWN:
		return 0
	var thrown := weapons[WeaponDefs.SLOT_THROWN]
	if thrown == null:
		return 0
	return thrown.in_magazine + thrown.reserve


func _consume_grenade() -> void:
	if weapons.size() <= WeaponDefs.SLOT_THROWN:
		return
	var thrown := weapons[WeaponDefs.SLOT_THROWN]
	if thrown == null:
		return
	if thrown.in_magazine > 0:
		thrown.in_magazine -= 1
	elif thrown.reserve > 0:
		thrown.reserve -= 1
	if thrown.in_magazine <= 0 and thrown.reserve > 0:
		thrown.in_magazine = 1
		thrown.reserve -= 1
	ammo_changed.emit(thrown)


func _throw_grenade() -> void:
	_cooking = false
	var cooked := _cook_time
	_cook_time = 0.0
	if _grenade_count() <= 0:
		return
	if not ResourceLoader.exists(GRENADE_SCRIPT):
		push_warning("Player: grenade script missing, throw cancelled.")
		return
	var script := load(GRENADE_SCRIPT) as GDScript
	if script == null:
		push_warning("Player: grenade script could not be loaded.")
		return
	var instance: Object = script.new()
	var body := instance as RigidBody3D
	if body == null:
		push_warning("Player: grenade script did not produce a RigidBody3D.")
		if instance != null and not (instance is RefCounted):
			(instance as Object).free()
		return
	var scene := get_tree().current_scene
	if scene == null:
		body.free()
		return
	var direction := aim_direction()
	scene.add_child(body)
	body.global_position = eye_position() + direction * 0.55 + Vector3.UP * -0.05
	var impulse := direction * GRENADE_THROW_SPEED \
			+ Vector3.UP * 3.2 \
			+ Vector3(velocity.x, 0.0, velocity.z) * 0.45
	# Cooking is a hint the grenade may honour by itself.
	if "cook_time" in body:
		body.set("cook_time", cooked)
	body.set_meta("cook_time", cooked)
	if body.has_method("setup"):
		body.call("setup", self, impulse)
	# Whatever the grenade does with the hint, the cooked time is enforced here.
	if cooked > 0.25 and body.has_method("detonate"):
		var remaining := maxf(GRENADE_MIN_FUSE, GRENADE_FUSE - cooked)
		var timer := get_tree().create_timer(remaining, false)
		timer.timeout.connect(func() -> void:
			if is_instance_valid(body):
				body.call("detonate"))
	Sfx.play("grenade_throw", -2.0)
	_consume_grenade()
	_shot_noise = maxf(_shot_noise, 20.0)


# --- melee -------------------------------------------------------------------


func _update_melee(delta: float) -> void:
	if _melee_windup >= 0.0:
		_melee_windup -= delta
		if _melee_windup <= 0.0:
			_melee_windup = -1.0
			_swing()
		return
	if not Input.is_action_just_pressed("melee"):
		return
	if _melee_timer > 0.0 or _bandaging or _cooking:
		return
	_melee_timer = MELEE_RECOVERY
	_melee_windup = MELEE_WINDUP
	is_aiming = false
	_viewmodel.play_melee()


func _swing() -> void:
	var from := eye_position()
	var direction := aim_direction()
	var params := PhysicsRayQueryParameters3D.create(from, from + direction * MELEE_RANGE)
	params.collision_mask = Layers.BULLET_MASK
	params.exclude = [get_rid()]
	params.collide_with_areas = false
	var hit := get_world_3d().direct_space_state.intersect_ray(params)
	rig.add_recoil(-0.010, 0.014)
	rig.shake(0.010, 0.18)
	if hit.is_empty():
		return
	var point: Vector3 = hit.get("position", from)
	var node := hit.get("collider") as Node
	if node == null:
		return
	if not node.has_method("take_damage"):
		Sfx.play_at("impact_wood", point, -3.0)
		return
	var damage := MELEE_DAMAGE
	var body := node as Node3D
	if body != null:
		var facing := -body.global_transform.basis.z
		var to_player := global_position - body.global_position
		to_player.y = 0.0
		if to_player.length_squared() > 0.01:
			to_player = to_player.normalized()
			# The target is looking away: a rifle butt to the back of the neck.
			if facing.dot(to_player) < -0.35:
				damage *= MELEE_BACK_MULTIPLIER
	node.call("take_damage", damage, self, point, false)
	Sfx.play_at("impact_flesh", point, -1.0)
	_shot_noise = maxf(_shot_noise, 22.0)


# --- health ------------------------------------------------------------------


func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void:
	if not _alive or amount <= 0.0:
		return
	var scale := 1.0
	if Game != null:
		scale = Game.incoming_damage_scale()
	# `amount` ALREADY carries the head shot multiplier: Ballistics.fire computes
	# it through WeaponDefs.damage_at(id, distance, headshot) before it ever calls
	# take_damage, and it is the only caller in the project that passes
	# headshot = true. Multiplying again here made the player take 1.8 times what
	# a soldier takes from the very same bullet, and die to two rifle shots to the
	# head where the balance table asks for three. The flag is kept in the
	# signature because it is part of the shared damage contract and the HUD hit
	# marker reads it.
	var damage := amount * scale
	health = maxf(0.0, health - damage)
	_regen_timer = 0.0

	var from_direction := -aim_direction()
	var source := attacker as Node3D
	if source != null:
		from_direction = source.global_position - global_position
	elif hit_point != Vector3.ZERO:
		from_direction = hit_point - global_position
	from_direction.y = 0.0
	if from_direction.length_squared() < 0.0001:
		from_direction = -aim_direction()
	from_direction = from_direction.normalized()

	damaged.emit(damage, from_direction)
	health_changed.emit(health, MAX_HEALTH)
	rig.shake(clampf(0.008 + damage * 0.0009, 0.008, 0.045), 0.35)
	Sfx.play("hurt", -2.0, _rng.randf_range(0.94, 1.06))
	if health <= 0.0:
		_die(attacker)


func heal(amount: float) -> void:
	if not _alive or amount <= 0.0:
		return
	var before := health
	health = minf(MAX_HEALTH, health + amount)
	if health != before:
		health_changed.emit(health, MAX_HEALTH)


func revive(pos: Vector3) -> void:
	_alive = true
	health = MAX_HEALTH
	stance = STANCE_STAND
	_prone_toggled = false
	is_aiming = false
	is_sprinting = false
	_bandaging = false
	_bandage_timer = 0.0
	_cooking = false
	_melee_timer = 0.0
	_melee_windup = -1.0
	_bolt_timer = 0.0
	_shot_noise = 0.0
	_regen_timer = REGEN_DELAY
	_apply_stance_shape()
	teleport(pos)
	if _mounted != null:
		_dismount()
	health_changed.emit(health, MAX_HEALTH)
	bandages_changed.emit(bandages)
	_refresh_viewmodel()


func head_height() -> float:
	return global_position.y + _height_of(stance) - 0.30


func is_alive() -> bool:
	return _alive


func eye_position() -> Vector3:
	if rig != null and rig.camera != null:
		return rig.camera.global_position
	return global_position + Vector3.UP * (_height_of(stance) - EYE_OFFSET)


func aim_direction() -> Vector3:
	if rig == null:
		return -global_transform.basis.z
	return rig.forward()


func _die(_attacker: Node) -> void:
	if not _alive:
		return
	_alive = false
	health = 0.0
	is_aiming = false
	is_sprinting = false
	_cooking = false
	_bandaging = false
	prompt_text = ""
	if _mounted != null:
		_dismount()
	if War != null:
		War.deaths += 1
	Sfx.play("death")
	health_changed.emit(health, MAX_HEALTH)
	died.emit()


func _update_health(delta: float) -> void:
	if _bandaging:
		_bandage_timer -= delta
		if _bandage_timer <= 0.0:
			_bandaging = false
			bandages = maxi(0, bandages - 1)
			bandages_changed.emit(bandages)
			heal(BANDAGE_HEAL)
			_regen_timer = REGEN_DELAY
	elif Input.is_action_just_pressed("heal"):
		_start_bandage()

	_regen_timer += delta
	if _regen_timer >= REGEN_DELAY and health < MAX_HEALTH:
		# Creeps back to the next 25 point tier and stops there.
		var tier := minf(MAX_HEALTH, ceilf(health / REGEN_STEP) * REGEN_STEP)
		if tier > health:
			health = minf(tier, health + REGEN_RATE * delta)
			health_changed.emit(health, MAX_HEALTH)

	if health <= LOW_HEALTH:
		var severity := 1.0 - clampf(health / LOW_HEALTH, 0.0, 1.0)
		_heartbeat_timer -= delta
		if _heartbeat_timer <= 0.0:
			_heartbeat_timer = lerpf(0.95, 0.52, severity)
			Sfx.play("heartbeat", lerpf(-9.0, -2.0, severity))
		_breath_timer -= delta
		if _breath_timer <= 0.0:
			_breath_timer = lerpf(4.2, 2.1, severity)
			Sfx.play("breath", -6.0, _rng.randf_range(0.95, 1.05))
	else:
		_heartbeat_timer = 0.0
		_breath_timer = 0.0


func _start_bandage() -> void:
	if _bandaging or bandages <= 0 or health >= MAX_HEALTH:
		return
	# You do not dress a wound with a live grenade in your other hand. Throw it
	# first. (The grenade would survive this now that its fuse keeps running, but
	# refusing is the readable rule rather than a rescued edge case.)
	if _cooking:
		return
	_bandaging = true
	_bandage_timer = BANDAGE_TIME
	is_aiming = false
	is_sprinting = false
	var weapon := current_weapon()
	if weapon != null and weapon.is_reloading:
		weapon.cancel_reload()
	Sfx.play("bandage", -2.0)


# --- interaction -------------------------------------------------------------


func _update_interaction() -> void:
	_look_target = null
	prompt_text = ""

	if _mounted != null:
		prompt_text = "Quitter la position [E]"
		if Input.is_action_just_pressed("use") and _mount_cooldown <= 0.0:
			_dismount()
		return

	var from := eye_position()
	var params := PhysicsRayQueryParameters3D.create(from, from + aim_direction() * USE_RANGE)
	params.collision_mask = Layers.WALK_MASK | Layers.ENEMY | Layers.ALLY | Layers.TRIGGER
	params.exclude = [get_rid()]
	params.collide_with_areas = true
	var hit := get_world_3d().direct_space_state.intersect_ray(params)
	if hit.is_empty():
		return
	var collider := hit.get("collider") as Node
	var target := _find_interactable(collider)
	if target == null:
		return
	_look_target = target
	prompt_text = _prompt_for(target)
	if prompt_text.is_empty():
		_look_target = null
		return
	if Input.is_action_just_pressed("use"):
		_interact_with(target)


## Walks a few levels up from the collider looking for something usable.
func _find_interactable(node: Node) -> Node:
	var current := node
	var depth := 0
	while current != null and depth < 4:
		if current == self:
			return null
		if current.has_method("mount") or current.has_method("interact") \
				or current.is_in_group("pickup"):
			return current
		current = current.get_parent()
		depth += 1
	return null


func _prompt_for(target: Node) -> String:
	if target.has_meta("prompt"):
		return str(target.get_meta("prompt"))
	if target.is_in_group("pickup"):
		if target.has_meta("weapon_id"):
			var wid := int(target.get_meta("weapon_id"))
			return "Ramasser " + WeaponDefs.display_name(wid) + " [E]"
		return "Ramasser [E]"
	if target.has_method("mount"):
		if target.has_method("is_alive") and not bool(target.call("is_alive")):
			return ""
		return "Prendre la position [E]"
	if target.has_method("interact"):
		return "Utiliser [E]"
	return ""


func _interact_with(target: Node) -> void:
	if target.is_in_group("pickup") and target.has_meta("weapon_id"):
		_pick_up(target)
		used.emit(target)
		return
	if target.has_method("mount"):
		var taken := bool(target.call("mount", self))
		if taken:
			_mounted = target as Node3D
			_mount_cooldown = 0.35
			velocity = Vector3.ZERO
			is_aiming = false
			is_sprinting = false
			_prone_toggled = false
			_set_stance(STANCE_STAND)
			used.emit(target)
		return
	if target.has_method("interact"):
		target.call("interact", self)
		used.emit(target)


func _pick_up(target: Node) -> void:
	var wid := int(target.get_meta("weapon_id", WeaponDefs.NONE))
	if wid < 0 or wid >= WeaponDefs.COUNT:
		return
	var ammo := int(target.get_meta("ammo", WeaponDefs.magazine(wid)))
	give_weapon(wid, ammo)
	if target.has_meta("bandages"):
		give_bandage(int(target.get_meta("bandages")))
	Sfx.play_at("ui_click", global_position, -4.0)
	target.queue_free()


func _dismount() -> void:
	if _mounted == null:
		return
	if _mounted.has_method("dismount"):
		_mounted.call("dismount")
	_mounted = null
	_mount_cooldown = 0.35


func _mounted_physics(_delta: float) -> void:
	velocity = Vector3.ZERO
	if not is_instance_valid(_mounted):
		_mounted = null
		return
	if _mounted.has_method("is_alive") and not bool(_mounted.call("is_alive")):
		_dismount()
		return
	if _mounted.has_method("aim_at"):
		_mounted.call("aim_at", aim_direction())
	if Input.is_action_pressed("fire") and _mounted.has_method("fire_burst"):
		_mounted.call("fire_burst", self)
		_shot_noise = NOISE_SHOT
	is_aiming = Input.is_action_pressed("aim")


# --- camera ------------------------------------------------------------------


func _update_camera(delta: float) -> void:
	if rig == null:
		return
	var fov_scale := 1.0
	var weapon := current_weapon()
	if weapon != null and current_slot != WeaponDefs.SLOT_THROWN:
		fov_scale = WeaponDefs.aim_fov_scale(weapon.id)
	var eye := _height_of(stance) - EYE_OFFSET
	if not _alive:
		eye = PRONE_HEIGHT * 0.5
	rig.update(delta, velocity, is_on_floor(), is_aiming, fov_scale, eye)
	if _viewmodel == null:
		return
	if is_aiming != _was_aiming:
		_was_aiming = is_aiming
		_viewmodel.set_aiming(is_aiming)
	_viewmodel.update(delta, velocity, is_aiming)


func _vfx() -> Vfx:
	var nodes := get_tree().get_nodes_in_group("vfx")
	if nodes.is_empty():
		return null
	return nodes[0] as Vfx


# --- noise -------------------------------------------------------------------


## How far the AI can hear the player right now, in metres.
func noise_radius() -> float:
	if not _alive:
		return 0.0
	var moving := Vector2(velocity.x, velocity.z).length() > 0.45
	var movement := 0.0
	if moving:
		match stance:
			STANCE_PRONE:
				movement = NOISE_PRONE
			STANCE_CROUCH:
				movement = NOISE_CROUCH
			_:
				movement = NOISE_SPRINT if is_sprinting else NOISE_WALK
	return maxf(_shot_noise, movement)


# --- persistence -------------------------------------------------------------


func to_dict() -> Dictionary:
	var stored: Array = []
	for weapon in weapons:
		if weapon == null:
			stored.append({})
		else:
			stored.append(weapon.to_dict())
	var data := {
		"health": health,
		"bandages": bandages,
		"stance": stance,
		"slot": current_slot,
		"alive": _alive,
		"position": [global_position.x, global_position.y, global_position.z],
		"weapons": stored,
	}
	if rig != null:
		data["yaw"] = rig.yaw
		data["pitch"] = rig.pitch
	return data


func from_dict(data: Dictionary) -> void:
	_build()
	health = clampf(float(data.get("health", MAX_HEALTH)), 0.0, MAX_HEALTH)
	bandages = clampi(int(data.get("bandages", 3)), 0, MAX_BANDAGES)
	stance = clampi(int(data.get("stance", STANCE_STAND)), STANCE_STAND, STANCE_PRONE)
	_prone_toggled = stance == STANCE_PRONE
	_alive = bool(data.get("alive", true))
	_apply_stance_shape()

	var raw_position: Array = data.get("position", [])
	if raw_position.size() == 3:
		teleport(Vector3(float(raw_position[0]), float(raw_position[1]), float(raw_position[2])))
	if rig != null:
		rig.yaw = float(data.get("yaw", rig.yaw))
		rig.pitch = clampf(float(data.get("pitch", rig.pitch)),
				-CameraRig.PITCH_LIMIT, CameraRig.PITCH_LIMIT)

	var stored: Array = data.get("weapons", [])
	if not stored.is_empty():
		weapons.clear()
		weapons.resize(3)
		for i in mini(stored.size(), 3):
			var entry: Dictionary = stored[i]
			if entry.is_empty():
				continue
			var wid := int(entry.get("id", WeaponDefs.NONE))
			if wid < 0 or wid >= WeaponDefs.COUNT:
				continue
			var weapon := Weapon.new(wid, false)
			weapon.from_dict(entry)
			weapons[i] = weapon
	if weapons.is_empty():
		_default_loadout()
	current_slot = clampi(int(data.get("slot", WeaponDefs.SLOT_PRIMARY)), 0, maxi(0, weapons.size() - 1))
	if current_weapon() == null:
		current_slot = WeaponDefs.SLOT_PRIMARY

	_refresh_viewmodel()
	health_changed.emit(health, MAX_HEALTH)
	bandages_changed.emit(bandages)
	weapon_changed.emit(current_weapon())
	ammo_changed.emit(current_weapon())
