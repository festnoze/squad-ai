class_name Battery
extends Node3D
## Collectible battery. Node origin is the BASE of the battery so level defs
## can place it directly on a floor. Batteries duplicated from photos use this
## exact same script: a copy is a normal battery.

var _bob_phase := 0.0
var _visual: Node3D


func _ready() -> void:
	add_to_group("battery")
	_bob_phase = fposmod(global_position.x * 1.7 + global_position.z * 2.3, TAU)

	_visual = Node3D.new()
	add_child(_visual)

	var body := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.16
	cyl.bottom_radius = 0.16
	cyl.height = 0.5
	body.mesh = cyl
	body.material_override = Materials.solid("battery", 0.8)
	body.position = Vector3(0, 0.35, 0)
	_visual.add_child(body)

	var tip := MeshInstance3D.new()
	var tip_mesh := CylinderMesh.new()
	tip_mesh.top_radius = 0.06
	tip_mesh.bottom_radius = 0.06
	tip_mesh.height = 0.08
	tip.mesh = tip_mesh
	tip.material_override = Materials.solid("battery_tip")
	tip.position = Vector3(0, 0.64, 0)
	_visual.add_child(tip)

	var area := Area3D.new()
	area.collision_layer = Layers.INTERACT
	area.collision_mask = 0
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.55
	shape.shape = sphere
	shape.position = Vector3(0, 0.35, 0)
	area.add_child(shape)
	add_child(area)


func _process(delta: float) -> void:
	_bob_phase = fposmod(_bob_phase + delta * 2.0, TAU)
	_visual.position.y = 0.08 + sin(_bob_phase) * 0.06
	_visual.rotation.y += delta * 1.2


func interact(_player: Node) -> void:
	Game.collect_battery()
	queue_free()


func prompt_text(_player: Node) -> String:
	return "E : ramasser la pile"
