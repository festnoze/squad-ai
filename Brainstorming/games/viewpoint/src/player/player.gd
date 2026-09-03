class_name Player
extends CharacterBody3D
## First person controller: movement, mouse look, and the interaction ray.
## The PhotoPlacer is a child of the camera with an identity transform, which
## makes the camera transform the photo placement anchor (PRD section 3.2).

## Fired once when the player falls below the level's kill plane. Losing costs
## the whole level: main rebuilds it from its definition.
signal fell_out

const BatteryScript := preload("res://src/pickups/battery.gd")

const WALK_SPEED := 5.0
const SPRINT_SPEED := 8.0
const ACCEL := 12.0
const JUMP_VELOCITY := 6.5
const MOUSE_SENSITIVITY := 0.0022
const INTERACT_RANGE := 1.7
const EYE_HEIGHT := 1.62

var camera: Camera3D
var placer: PhotoPlacer
var control_enabled := false
## Prompt of whatever interactable the crosshair currently points at, polled
## by main for the HUD. Empty when nothing is in reach.
var interact_prompt := ""
## True while the camera is raised to the eye: the HUD frames what the shot
## would capture, and the shutter (left click) answers only in this state.
var viewfinder := false

var _level_root: Node3D
var _spawn_position := Vector3.ZERO
var _spawn_yaw := 0.0
var _kill_y := -10.0
var _interact_target: Node = null
## True between falling below kill_y and the level being rebuilt.
var _fell := false


func _ready() -> void:
	collision_layer = Layers.PLAYER
	collision_mask = Layers.WORLD

	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.35
	capsule.height = 1.75
	shape.shape = capsule
	shape.position = Vector3(0, 0.875, 0)
	add_child(shape)

	camera = Camera3D.new()
	camera.fov = 75.0
	camera.near = 0.05
	camera.far = 400.0
	camera.position = Vector3(0, EYE_HEIGHT, 0)
	add_child(camera)

	placer = PhotoPlacer.new()
	camera.add_child(placer)


func setup(level_root: Node3D) -> void:
	_level_root = level_root
	placer.setup(level_root)


func set_spawn(pos: Vector3, yaw: float, kill_y: float) -> void:
	_spawn_position = pos
	_spawn_yaw = yaw
	_kill_y = kill_y
	respawn()


func respawn() -> void:
	global_position = _spawn_position
	rotation = Vector3(0, _spawn_yaw, 0)
	camera.rotation = Vector3.ZERO
	velocity = Vector3.ZERO
	_fell = false
	viewfinder = false


func _unhandled_input(event: InputEvent) -> void:
	if not control_enabled:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * MOUSE_SENSITIVITY)
		camera.rotation.x = clampf(camera.rotation.x - event.relative.y * MOUSE_SENSITIVITY, -1.45, 1.45)
	elif event.is_action_pressed("interact"):
		if _interact_target != null and is_instance_valid(_interact_target):
			_interact_target.interact(self)
		elif Game.carried_batteries > 0:
			var kind := Game.drop_battery()
			if kind != "":
				_spawn_dropped_battery(kind == "sealed")
	elif event.is_action_pressed("place_photo"):
		if placer.held_id != "":
			placer.place()
		else:
			# The shutter only answers through the viewfinder: aim first
			# (right click), shoot second.
			capture_photo()
	elif event.is_action_pressed("raise_photo"):
		if placer.held_id != "":
			placer.raise_toggle()
		else:
			toggle_viewfinder()
	elif event.is_action_pressed("drop_photo"):
		placer.drop()
	elif event.is_action_pressed("rotate_photo_cw"):
		placer.rotate_held(1)
	elif event.is_action_pressed("rotate_photo_ccw"):
		placer.rotate_held(-1)


func _physics_process(delta: float) -> void:
	if not control_enabled:
		return

	if not is_on_floor():
		velocity.y -= 14.0 * delta
	elif Input.is_action_just_pressed("jump"):
		velocity.y = JUMP_VELOCITY

	var input_dir := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	var speed := SPRINT_SPEED if Input.is_action_pressed("sprint") else WALK_SPEED
	var target := direction * speed
	velocity.x = lerpf(velocity.x, target.x, minf(ACCEL * delta, 1.0))
	velocity.z = lerpf(velocity.z, target.z, minf(ACCEL * delta, 1.0))
	move_and_slide()

	# Falling out is losing: main rebuilds the whole level, so control is cut
	# here and the signal fires once, not on every frame of the fall.
	if global_position.y < _kill_y and not _fell:
		_fell = true
		control_enabled = false
		velocity = Vector3.ZERO
		fell_out.emit()
		return

	# The camera cannot stay at the eye once the hands are full or the film is
	# spent, whatever route emptied them.
	if viewfinder and (placer.held_id != "" or Game.camera_films <= 0):
		viewfinder = false

	_update_interact_target()


## Takes a photo with the camera. The film ALWAYS captures something: the
## frame content, possibly empty, over a painted sky backdrop. The empty photo
## is a tool (it pierces the world when placed), not a failure, so the film is
## always consumed. The new photo lands straight in hand, raised.
func capture_photo() -> bool:
	if placer.held_id != "" or Game.camera_films <= 0 or not viewfinder:
		return false
	var def := PhotoCapture.capture(camera.global_transform, get_tree())
	viewfinder = false
	Game.use_film()
	var id := PhotoDefs.register_dynamic(def)
	PhotoSnaps.request(id)
	placer.hold(id)
	placer.raise_toggle()
	return true


## Raises the camera to the eye, or lowers it. Only possible with empty hands
## and film left; returns the new state.
func toggle_viewfinder() -> bool:
	if placer.held_id != "" or Game.camera_films <= 0:
		viewfinder = false
	else:
		viewfinder = not viewfinder
	return viewfinder


## Puts one carried battery back on the ground, in front of the player. A
## battery keeps its nature through the hands: what goes down leaden comes
## back leaden.
func _spawn_dropped_battery(sealed: bool) -> void:
	var forward_plat := -global_basis.z
	forward_plat.y = 0.0
	forward_plat = forward_plat.normalized() if forward_plat.length() > 0.01 else Vector3.FORWARD
	var battery: Node3D = BatteryScript.new()
	battery.setup(sealed)
	_level_root.add_child(battery)
	battery.global_position = global_position + forward_plat * 1.2 + Vector3(0, 0.05, 0)
	Rewind.notice_spawn(battery)


func _update_interact_target() -> void:
	_interact_target = null
	interact_prompt = ""
	var from := camera.global_position
	var to := from - camera.global_basis.z * INTERACT_RANGE
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.WORLD | Layers.INTERACT, [get_rid()])
	query.collide_with_areas = true
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty():
		var collider: Object = hit["collider"]
		if collider is Area3D:
			var owner_node := (collider as Area3D).get_parent()
			if owner_node != null and owner_node.has_method("interact"):
				_interact_target = owner_node
				interact_prompt = owner_node.prompt_text(self)
	if _interact_target == null and Game.carried_batteries > 0:
		interact_prompt = "E : reposer une pile"
