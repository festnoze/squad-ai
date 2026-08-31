class_name Player
extends CharacterBody3D
## First person controller: movement, mouse look, and the interaction ray.
## The PhotoPlacer is a child of the camera with an identity transform, which
## makes the camera transform the photo placement anchor (PRD section 3.2).

const WALK_SPEED := 5.0
const SPRINT_SPEED := 8.0
const ACCEL := 12.0
const JUMP_VELOCITY := 6.5
const MOUSE_SENSITIVITY := 0.0022
const INTERACT_RANGE := 3.4
const EYE_HEIGHT := 1.62

var camera: Camera3D
var placer: PhotoPlacer
var control_enabled := false
## Prompt of whatever interactable the crosshair currently points at, polled
## by main for the HUD. Empty when nothing is in reach.
var interact_prompt := ""

var _spawn_position := Vector3.ZERO
var _spawn_yaw := 0.0
var _kill_y := -10.0
var _interact_target: Node = null


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


func _unhandled_input(event: InputEvent) -> void:
	if not control_enabled:
		return
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * MOUSE_SENSITIVITY)
		camera.rotation.x = clampf(camera.rotation.x - event.relative.y * MOUSE_SENSITIVITY, -1.45, 1.45)
	elif event.is_action_pressed("interact"):
		if _interact_target != null and is_instance_valid(_interact_target):
			_interact_target.interact(self)
	elif event.is_action_pressed("place_photo"):
		placer.place()
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

	if global_position.y < _kill_y:
		respawn()

	_update_interact_target()


func _update_interact_target() -> void:
	_interact_target = null
	interact_prompt = ""
	var from := camera.global_position
	var to := from - camera.global_basis.z * INTERACT_RANGE
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.WORLD | Layers.INTERACT, [get_rid()])
	query.collide_with_areas = true
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if hit.is_empty():
		return
	var collider: Object = hit["collider"]
	if collider is Area3D:
		var owner_node := (collider as Area3D).get_parent()
		if owner_node != null and owner_node.has_method("interact"):
			_interact_target = owner_node
			interact_prompt = owner_node.prompt_text(self)
