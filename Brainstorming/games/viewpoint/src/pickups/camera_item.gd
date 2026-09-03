class_name CameraItem
extends Node3D
## The camera pickup. Grabbing it loads the level's film into Game: each shot
## (left click with empty hands) captures the framed lavender world into a new
## photo. Node origin is the base of the pedestal it floats over.

var _films := 1
var _bob_phase := 0.0
var _visual: Node3D


func setup(films: int) -> void:
	_films = films


func _ready() -> void:
	add_to_group("camera_item")
	_bob_phase = fposmod(global_position.x * 1.3 + global_position.z * 2.7, TAU)

	_visual = Node3D.new()
	add_child(_visual)

	var body := MeshInstance3D.new()
	var body_mesh := BoxMesh.new()
	body_mesh.size = Vector3(0.55, 0.34, 0.28)
	body.mesh = body_mesh
	body.material_override = Materials.solid("battery_tip")
	body.position = Vector3(0, 0.55, 0)
	_visual.add_child(body)

	var lens := MeshInstance3D.new()
	var lens_mesh := CylinderMesh.new()
	lens_mesh.top_radius = 0.11
	lens_mesh.bottom_radius = 0.11
	lens_mesh.height = 0.14
	lens.mesh = lens_mesh
	lens.material_override = Materials.solid("teal", 0.4)
	lens.rotation.x = PI * 0.5
	lens.position = Vector3(0, 0.55, -0.2)
	_visual.add_child(lens)

	var flash := MeshInstance3D.new()
	var flash_mesh := BoxMesh.new()
	flash_mesh.size = Vector3(0.12, 0.08, 0.1)
	flash.mesh = flash_mesh
	flash.material_override = Materials.solid("accent")
	flash.position = Vector3(0.18, 0.76, 0)
	_visual.add_child(flash)

	var area := Area3D.new()
	area.collision_layer = Layers.INTERACT
	area.collision_mask = 0
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.6
	shape.shape = sphere
	shape.position = Vector3(0, 0.55, 0)
	area.add_child(shape)
	add_child(area)


func _process(delta: float) -> void:
	_bob_phase = fposmod(_bob_phase + delta * 1.8, TAU)
	_visual.position.y = 0.06 + sin(_bob_phase) * 0.05
	_visual.rotation.y += delta * 1.0


func interact(_player: Node) -> void:
	Game.add_films(_films)
	Rewind.retire(self)


func prompt_text(_player: Node) -> String:
	return "E : prendre l'appareil photo (pellicule : %d)" % _films
