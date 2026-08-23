## A static weapon position: MG42 on its tripod behind sandbags, or a light
## anti aircraft gun.
##
## Both the AI and the player use it. An AI gunner standing next to it takes it
## over and hoses the last known position of its target. The player presses the
## use key, gets planted behind the gun, and pays for a long burst with a wider
## and wider cone plus a barrel that overheats. It is destructible (200 HP) and
## goes up when it dies.
##
## Everything is built from Meshes primitives, no binary asset anywhere.
class_name Emplacement
extends Node3D

const KIND_MG := 0
const KIND_AA := 1

signal destroyed(emplacement: Emplacement)

const MAX_HEALTH := 200.0

## Traverse limit each side: a 100 degree arc of fire in total.
const YAW_LIMIT := 0.87
const MG_PITCH_MIN := -0.30
const MG_PITCH_MAX := 0.65
const AA_PITCH_MIN := -0.12
const AA_PITCH_MAX := 1.35
const TRAVERSE_SPEED := 2.6

## Heat gauge, 0 to 1. Past 1 the barrel is cooked and refuses to fire until it
## drops back under COOL_RESUME.
const HEAT_PER_SHOT_MG := 0.030
const HEAT_PER_SHOT_AA := 0.085
const HEAT_COOL_RATE := 0.16
const HEAT_COOL_DELAY := 0.9
const COOL_RESUME := 0.35

## Cone half angle in radians: base, plus the growth for a sustained burst.
const SPREAD_BASE := 0.012
const SPREAD_GROWTH := 0.030
const SPREAD_MAX := 0.075
const BURST_DECAY := 1.6

const AA_SHELL_RADIUS := 3.2
const AA_SHELL_DAMAGE := 55.0

var kind: int = KIND_MG
var faction: int = 1
var operator_node: Node3D = null

## Barrel temperature, 0 cold to 1 cooked. Read by the HUD when mounted.
var heat := 0.0

var _world: GameWorld = null
var _health := MAX_HEALTH
var _wrecked := false
var _rng := RandomNumberGenerator.new()

var _yaw_node: Node3D = null
var _pitch_node: Node3D = null
var _muzzle: Node3D = null
var _seat: Node3D = null
var _body: StaticBody3D = null

var _yaw := 0.0
var _pitch := 0.0
var _wanted_yaw := 0.0
var _wanted_pitch := 0.0

var _queued_rounds := 0
var _shot_timer := 0.0
var _burst_time := 0.0
var _idle_time := 0.0
var _overheated := false
var _dry_timer := 0.0
var _player_mounted := false
var _shooter: Node = null
var _ai_timer := 0.0
var _ready_to_run := false


func _ready() -> void:
	set_physics_process(true)


func setup(game_world: GameWorld, emplacement_kind: int, faction_id: int) -> void:
	_world = game_world
	kind = emplacement_kind
	faction = faction_id
	_health = MAX_HEALTH
	# position, not global_position: setup() may run before the node is in the
	# tree and reading a global transform there is an error.
	_rng.seed = int(abs(position.x * 977.0 + position.z * 6151.0)) \
			+ Time.get_ticks_usec()
	add_to_group("damageable")
	add_to_group(_faction_group())
	add_to_group("usable")
	set_meta("surface", "metal")
	_build()
	_ai_timer = _rng.randf() * 0.5
	_ready_to_run = true


# ------------------------------------------------------------------ visual --

func _build() -> void:
	var sandbags := Node3D.new()
	sandbags.name = "Sacs"
	add_child(sandbags)
	_build_sandbags(sandbags)

	var pedestal := MeshInstance3D.new()
	pedestal.name = "Socle"
	var pedestal_radius := 0.14 if kind == KIND_MG else 0.34
	var pedestal_height := 0.62 if kind == KIND_MG else 0.92
	pedestal.mesh = _cylinder(pedestal_radius, pedestal_height, 8, "metal")
	pedestal.position.y = pedestal_height * 0.5
	add_child(pedestal)

	_yaw_node = Node3D.new()
	_yaw_node.name = "Rotation"
	_yaw_node.position.y = pedestal_height
	add_child(_yaw_node)

	_pitch_node = Node3D.new()
	_pitch_node.name = "Pointage"
	_yaw_node.add_child(_pitch_node)

	if kind == KIND_MG:
		_build_mg(_pitch_node)
	else:
		_build_aa(_pitch_node)

	_seat = Node3D.new()
	_seat.name = "Poste"
	_seat.position = Vector3(0.0, 0.0, 1.05)
	_yaw_node.add_child(_seat)

	_body = StaticBody3D.new()
	_body.name = "Coque"
	_body.collision_layer = Layers.PROP
	_body.collision_mask = 0
	_body.set_meta("surface", "metal")
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2.6, 1.3, 2.6) if kind == KIND_MG else Vector3(2.2, 1.9, 2.2)
	shape.shape = box
	shape.position.y = box.size.y * 0.5
	_body.add_child(shape)
	add_child(_body)


func _build_sandbags(host: Node3D) -> void:
	var radius := 1.55
	var count := 13
	for row in 2:
		for i in count:
			# A 210 degree horseshoe open at the back, where the gunner stands.
			var angle := PI * 0.32 + (TAU * 0.58) * float(i) / float(count - 1)
			var bag := MeshInstance3D.new()
			bag.mesh = _box(Vector3(0.62, 0.30, 0.36), "sandbag")
			bag.position = Vector3(cos(angle) * radius, 0.16 + float(row) * 0.29,
					sin(angle) * radius)
			bag.rotation.y = -angle + PI * 0.5 + (0.12 if row == 1 else -0.08)
			host.add_child(bag)


func _build_mg(host: Node3D) -> void:
	var shield := MeshInstance3D.new()
	shield.mesh = _box(Vector3(0.92, 0.46, 0.05), "metal")
	shield.position = Vector3(0.0, 0.12, -0.34)
	host.add_child(shield)

	var receiver := MeshInstance3D.new()
	receiver.mesh = _box(Vector3(0.16, 0.20, 0.78), "gun_metal")
	receiver.position = Vector3(0.0, 0.06, -0.05)
	host.add_child(receiver)

	var stock := MeshInstance3D.new()
	stock.mesh = _box(Vector3(0.10, 0.16, 0.34), "gun_wood")
	stock.position = Vector3(0.0, 0.02, 0.45)
	host.add_child(stock)

	var barrel := MeshInstance3D.new()
	barrel.mesh = _cylinder(0.045, 1.15, 8, "gun_metal")
	barrel.rotation.x = PI * 0.5
	barrel.position = Vector3(0.0, 0.08, -0.92)
	host.add_child(barrel)

	# Tripod legs, splayed backwards.
	for i in 3:
		var leg := MeshInstance3D.new()
		leg.mesh = _cylinder(0.035, 0.9, 6, "metal")
		var angle := PI * 0.5 + TAU * float(i) / 3.0
		leg.position = Vector3(cos(angle) * 0.3, -0.42, sin(angle) * 0.3)
		leg.rotation = Vector3(sin(angle) * 0.4, 0.0, -cos(angle) * 0.4)
		host.add_child(leg)

	_muzzle = Node3D.new()
	_muzzle.name = "Bouche"
	_muzzle.position = Vector3(0.0, 0.08, -1.55)
	host.add_child(_muzzle)


func _build_aa(host: Node3D) -> void:
	var cradle := MeshInstance3D.new()
	cradle.mesh = _box(Vector3(0.5, 0.34, 0.9), "gun_metal")
	cradle.position = Vector3(0.0, 0.1, 0.0)
	host.add_child(cradle)

	var shield := MeshInstance3D.new()
	shield.mesh = _box(Vector3(1.5, 0.9, 0.06), "metal")
	shield.position = Vector3(0.0, 0.3, -0.55)
	shield.rotation.x = -0.22
	host.add_child(shield)

	for side in 2:
		var barrel := MeshInstance3D.new()
		barrel.mesh = _cylinder(0.06, 2.3, 8, "gun_metal")
		barrel.rotation.x = PI * 0.5
		barrel.position = Vector3(-0.16 + 0.32 * float(side), 0.22, -1.35)
		host.add_child(barrel)

	var magazine := MeshInstance3D.new()
	magazine.mesh = _box(Vector3(0.24, 0.5, 0.22), "metal")
	magazine.position = Vector3(0.0, 0.5, 0.05)
	host.add_child(magazine)

	_muzzle = Node3D.new()
	_muzzle.name = "Bouche"
	_muzzle.position = Vector3(0.0, 0.22, -2.5)
	host.add_child(_muzzle)


func _box(size: Vector3, material_key: String) -> Mesh:
	var mesh: Mesh = Meshes.box(size, material_key)
	if mesh != null:
		return mesh
	var fallback := BoxMesh.new()
	fallback.size = size
	fallback.material = MatLib.get_material(material_key)
	return fallback


func _cylinder(radius: float, height: float, sides: int, material_key: String) -> Mesh:
	var mesh: Mesh = Meshes.cylinder(radius, height, sides, material_key)
	if mesh != null:
		return mesh
	var fallback := CylinderMesh.new()
	fallback.top_radius = radius
	fallback.bottom_radius = radius
	fallback.height = height
	fallback.radial_segments = sides
	fallback.material = MatLib.get_material(material_key)
	return fallback


# ------------------------------------------------------------------- frame --

func _physics_process(delta: float) -> void:
	if not _ready_to_run:
		return
	_dry_timer = maxf(0.0, _dry_timer - delta)
	_tick_heat(delta)
	_tick_traverse(delta)
	_tick_rounds(delta)
	if _player_mounted:
		_hold_gunner()
	else:
		_tick_ai(delta)


func _tick_heat(delta: float) -> void:
	if _queued_rounds > 0:
		_idle_time = 0.0
	else:
		_idle_time += delta
		_burst_time = maxf(0.0, _burst_time - BURST_DECAY * delta)
		if _idle_time > HEAT_COOL_DELAY:
			heat = maxf(0.0, heat - HEAT_COOL_RATE * delta)
	if heat >= 1.0 and not _overheated:
		_overheated = true
		heat = 1.0
		_queued_rounds = 0
		Sfx.play_at("dry_fire", global_position, -2.0, 0.7)
		var vfx := _vfx()
		if vfx != null and _muzzle != null:
			vfx.call("smoke_column", _muzzle.global_position, 3.0)
	elif _overheated and heat <= COOL_RESUME:
		_overheated = false


func _tick_traverse(delta: float) -> void:
	if _yaw_node == null or _pitch_node == null:
		return
	var speed := clampf(TRAVERSE_SPEED * delta, 0.0, 1.0)
	_yaw = lerp_angle(_yaw, _wanted_yaw, speed)
	_pitch = lerpf(_pitch, _wanted_pitch, speed)
	_yaw_node.rotation.y = _yaw
	_pitch_node.rotation.x = _pitch


func _tick_rounds(delta: float) -> void:
	if _queued_rounds <= 0:
		return
	if _wrecked or _overheated:
		_queued_rounds = 0
		return
	_shot_timer -= delta
	while _shot_timer <= 0.0 and _queued_rounds > 0:
		_shot_timer += _shot_interval()
		_queued_rounds -= 1
		_fire_one()


func _shot_interval() -> float:
	if kind == KIND_AA:
		return 0.16
	var rpm := WeaponDefs.rpm(WeaponDefs.MG42)
	if rpm <= 0.0:
		rpm = 1200.0
	return 60.0 / rpm


func _fire_one() -> void:
	if _muzzle == null:
		return
	var origin := _muzzle.global_position
	var direction := -_muzzle.global_transform.basis.z
	var spread := clampf(SPREAD_BASE + _burst_time * SPREAD_GROWTH, SPREAD_BASE, SPREAD_MAX)
	if _shooter == null or not is_instance_valid(_shooter):
		_shooter = self
	var result = Ballistics.fire(get_world_3d(), origin, direction,
			WeaponDefs.MG42, spread, _shooter, _rng)
	_burst_time += _shot_interval() * 2.4
	heat = minf(1.2, heat + (HEAT_PER_SHOT_AA if kind == KIND_AA else HEAT_PER_SHOT_MG))
	Sfx.play_shot("mg42", origin)
	var vfx := _vfx()
	var landing := origin + direction * 200.0
	if result != null and bool(result.hit):
		landing = result.position
	if vfx != null:
		vfx.call("muzzle_flash", origin, direction, 1.6 if kind == KIND_AA else 1.1)
		vfx.call("tracer", origin, landing, 720.0)
	if kind == KIND_AA and result != null and bool(result.hit):
		# The AA gun fires small shells: everything close to the impact takes it.
		Ballistics.explode(get_world_3d(), landing, AA_SHELL_RADIUS,
				AA_SHELL_DAMAGE, _shooter)


## Keeps the mounted player planted behind the gun, so his camera sits where
## the sights are and he cannot walk off while still firing.
func _hold_gunner() -> void:
	if operator_node == null or not is_instance_valid(operator_node):
		dismount()
		return
	# The player controller releases the weapon by dropping the marker meta, so
	# a missing meta always means "let me go" and never a soft lock.
	if not operator_node.has_meta("mounted_emplacement"):
		dismount()
		return
	if _seat == null:
		return
	operator_node.global_position = _seat.global_position
	if "velocity" in operator_node:
		operator_node.set("velocity", Vector3.ZERO)


## An AI gunner standing next to the weapon takes it over and works over the
## last known position of whatever his squad is fighting.
func _tick_ai(delta: float) -> void:
	if _wrecked:
		return
	_ai_timer -= delta
	if _ai_timer > 0.0:
		return
	_ai_timer = 0.45
	if operator_node != null and is_instance_valid(operator_node):
		var still_valid := operator_node.has_method("is_alive") \
				and bool(operator_node.call("is_alive")) \
				and operator_node.global_position.distance_to(global_position) < 4.5
		if not still_valid:
			operator_node = null
	if operator_node == null:
		operator_node = _find_gunner()
	if operator_node == null:
		return
	var gunner := operator_node as Soldier
	if gunner == null:
		return
	if not gunner.has_known_target() or not gunner.is_engaged():
		return
	var aim_point := gunner.known_target_position() + Vector3(0.0, 1.0, 0.0)
	var direction := aim_point - _muzzle_origin()
	if direction.length() < 1.0:
		return
	aim_at(direction.normalized())
	# Only shoot once the barrel is roughly on target.
	if absf(angle_difference(_yaw, _wanted_yaw)) < 0.15:
		fire_burst(gunner)


func _find_gunner() -> Node3D:
	var tree := get_tree()
	if tree == null:
		return null
	for node in tree.get_nodes_in_group(_faction_group()):
		# Validity is tested before the cast: casting an already freed object is
		# itself the error, so the check on the result would come too late.
		if not is_instance_valid(node):
			continue
		var soldier := node as Soldier
		if soldier == null or not soldier.is_alive():
			continue
		if soldier.global_position.distance_to(global_position) > 3.5:
			continue
		if not soldier.is_engaged():
			continue
		return soldier
	return null


func _muzzle_origin() -> Vector3:
	if _muzzle != null:
		return _muzzle.global_position
	return global_position + Vector3(0.0, 1.0, 0.0)


# ------------------------------------------------------------------ public --

## Called every frame while mounted by the player, with the aim direction.
func aim_at(direction: Vector3) -> void:
	if direction.length_squared() < 0.0001:
		return
	var local := global_transform.basis.inverse() * direction.normalized()
	var yaw := atan2(-local.x, -local.z)
	_wanted_yaw = clampf(wrapf(yaw, -PI, PI), -YAW_LIMIT, YAW_LIMIT)
	var flat := Vector2(local.x, local.z).length()
	var pitch := atan2(local.y, maxf(0.05, flat))
	if kind == KIND_AA:
		_wanted_pitch = clampf(pitch, AA_PITCH_MIN, AA_PITCH_MAX)
	else:
		_wanted_pitch = clampf(pitch, MG_PITCH_MIN, MG_PITCH_MAX)


## Queues a burst. Repeated calls while the trigger is held keep the queue fed.
func fire_burst(shooter: Node) -> void:
	if _wrecked:
		return
	if _overheated:
		if _dry_timer <= 0.0:
			_dry_timer = 0.6
			Sfx.play_at("dry_fire", global_position, -6.0, 0.8)
		return
	_shooter = shooter if shooter != null else self
	var burst := 6 if kind == KIND_MG else 2
	if _queued_rounds < burst:
		_queued_rounds = burst


## Player mounts it. Returns false when it is destroyed or already taken.
func mount(user: Node3D) -> bool:
	if _wrecked or user == null or not is_instance_valid(user):
		return false
	if operator_node != null and is_instance_valid(operator_node) and operator_node != user:
		return false
	operator_node = user
	_player_mounted = user.is_in_group("player")
	_shooter = user
	user.set_meta("mounted_emplacement", self)
	Sfx.play_at("ui_click", global_position, -8.0, 0.8)
	return true


func dismount() -> void:
	if operator_node != null and is_instance_valid(operator_node):
		if operator_node.has_meta("mounted_emplacement"):
			operator_node.remove_meta("mounted_emplacement")
		if _player_mounted and _seat != null:
			# Step back out of the sandbags instead of standing inside them.
			var out := _seat.global_position + _seat.global_transform.basis.z * 1.1
			if _world != null:
				out.y = _world.ground_y(out.x, out.z) + 0.1
			operator_node.global_position = out
	operator_node = null
	_player_mounted = false
	_queued_rounds = 0


func is_mounted() -> bool:
	return operator_node != null and is_instance_valid(operator_node)


## True while a human is behind it, used by the HUD and the player controller.
func is_player_mounted() -> bool:
	return _player_mounted and is_mounted()


## Contract shared by every damageable in the project. See section 3.
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void:
	if _wrecked or amount <= 0.0:
		return
	# Steel plate: small arms hurt it a lot less than explosives do.
	var taken := amount
	if not headshot:
		taken *= 0.75
	_health -= taken
	var vfx := _vfx()
	if vfx != null:
		vfx.call("impact", hit_point, (global_position - hit_point).normalized(), "metal")
	if _health <= 0.0:
		_destroy(attacker)


func is_alive() -> bool:
	return not _wrecked


func head_height() -> float:
	# There is no head on a machine: nothing is ever above this.
	return global_position.y + 3.0


func health() -> float:
	return maxf(0.0, _health)


func heat_ratio() -> float:
	return clampf(heat, 0.0, 1.0)


func is_overheated() -> bool:
	return _overheated


func kind_name() -> String:
	return "Mitrailleuse MG42" if kind == KIND_MG else "Canon antiaerien"


func _destroy(attacker: Node) -> void:
	_wrecked = true
	_queued_rounds = 0
	_health = 0.0
	remove_from_group("damageable")
	remove_from_group("usable")
	dismount()
	if _body != null:
		_body.collision_layer = Layers.PROP
	Ballistics.explode(get_world_3d(), global_position + Vector3(0.0, 0.8, 0.0),
			6.5, 95.0, attacker)
	Sfx.play_at("explosion", global_position, 2.0)
	var vfx := _vfx()
	if vfx != null:
		vfx.call("explosion", global_position + Vector3(0.0, 0.8, 0.0), 6.5)
		vfx.call("smoke_column", global_position + Vector3(0.0, 0.6, 0.0), 25.0)
	# The wreck stays: barrel down, gun canted over.
	if _pitch_node != null:
		_pitch_node.rotation.x = -0.55
	if _yaw_node != null:
		_yaw_node.rotation.z = _rng.randf_range(-0.35, 0.35)
		_yaw_node.position.y -= 0.15
	destroyed.emit(self)


func _faction_group() -> String:
	return "axis" if faction == War.AXIS else "allies"


func _vfx() -> Node:
	var tree := get_tree()
	if tree == null:
		return null
	return tree.get_first_node_in_group("vfx")
