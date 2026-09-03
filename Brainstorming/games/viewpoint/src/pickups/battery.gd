class_name Battery
extends Node3D
## Collectible battery. Node origin is the BASE of the battery so level defs
## can place it directly on a floor. Batteries duplicated from photos use this
## exact same script: a copy is a normal battery.
##
## A SEALED battery ("pile plombee") is worth exactly as much to a teleporter,
## but film does not print it: it is absent from the "copyable_battery" group
## the camera reads, so framing it copies nothing. It says so without a word,
## in the language the ground already speaks: it is leaden grey instead of
## amber, and it is inert (it neither bobs nor turns while the others do).

var _bob_phase := 0.0
var _visual: Node3D
## Set before the node enters the tree; groups and look follow from it.
var sealed := false


## Level data calls this for the batteries listed under "sealed_batteries".
func setup(is_sealed: bool) -> void:
	sealed = is_sealed


func _ready() -> void:
	add_to_group("battery")
	if not sealed:
		# The only group the camera reads: a leaden battery is invisible to film.
		add_to_group("copyable_battery")
	_bob_phase = fposmod(global_position.x * 1.7 + global_position.z * 2.3, TAU)

	_visual = Node3D.new()
	add_child(_visual)

	var body := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.16
	cyl.bottom_radius = 0.16
	cyl.height = 0.5
	body.mesh = cyl
	body.material_override = Materials.solid("battery_sealed") if sealed else Materials.solid("battery", 0.8)
	body.position = Vector3(0, 0.35, 0)
	_visual.add_child(body)

	var tip := MeshInstance3D.new()
	var tip_mesh := CylinderMesh.new()
	tip_mesh.top_radius = 0.06
	tip_mesh.bottom_radius = 0.06
	tip_mesh.height = 0.08
	tip.mesh = tip_mesh
	tip.material_override = Materials.solid("sealed_dark" if sealed else "battery_tip")
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
	if sealed:
		# Dead weight: no float, no spin. Seen next to a live battery, the
		# difference is immediate.
		return
	_bob_phase = fposmod(_bob_phase + delta * 2.0, TAU)
	_visual.position.y = 0.08 + sin(_bob_phase) * 0.06
	_visual.rotation.y += delta * 1.2


func interact(_player: Node) -> void:
	Game.collect_battery(sealed)
	# A physically placed battery lives inside a rigid shell: free the shell,
	# not just the battery, or an empty physics husk would remain.
	var parent := get_parent()
	if parent is RigidBody3D:
		Rewind.retire(parent)
	else:
		Rewind.retire(self)


func prompt_text(_player: Node) -> String:
	return "E : ramasser la pile plombee" if sealed else "E : ramasser la pile"
