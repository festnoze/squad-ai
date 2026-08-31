class_name Teleporter
extends Node3D
## Level exit. Displays "inserted / required" batteries, accepts battery
## insertion, and once charged fires depart_requested on the next interaction.
## Node origin is the center of the pad, on the floor.

signal depart_requested

var _required := 0
var _ring: MeshInstance3D
var _cells: Array[MeshInstance3D] = []
var _label: Label3D
var _spin := 0.0


func setup(required: int) -> void:
	_required = required


func _ready() -> void:
	add_to_group("teleporter")

	var pad := MeshInstance3D.new()
	var pad_mesh := CylinderMesh.new()
	pad_mesh.top_radius = 1.3
	pad_mesh.bottom_radius = 1.5
	pad_mesh.height = 0.22
	pad.mesh = pad_mesh
	pad.material_override = Materials.solid("teleporter")
	pad.position = Vector3(0, 0.11, 0)
	add_child(pad)

	_ring = MeshInstance3D.new()
	var ring_mesh := TorusMesh.new()
	ring_mesh.inner_radius = 1.05
	ring_mesh.outer_radius = 1.25
	_ring.mesh = ring_mesh
	_ring.material_override = Materials.solid("teleporter_ring", 0.15)
	_ring.position = Vector3(0, 2.3, 0)
	add_child(_ring)

	# Battery cells on a side pillar, one per required battery, lit when filled.
	var pillar := StaticBody3D.new()
	pillar.collision_layer = Layers.WORLD
	pillar.collision_mask = 0
	pillar.position = Vector3(1.9, 0.0, 0)
	var pillar_shape := CollisionShape3D.new()
	var pillar_box := BoxShape3D.new()
	pillar_box.size = Vector3(0.4, 1.4, 0.4)
	pillar_shape.shape = pillar_box
	pillar_shape.position = Vector3(0, 0.7, 0)
	pillar.add_child(pillar_shape)
	var pillar_mesh := MeshInstance3D.new()
	var pillar_box_mesh := BoxMesh.new()
	pillar_box_mesh.size = Vector3(0.4, 1.4, 0.4)
	pillar_mesh.mesh = pillar_box_mesh
	pillar_mesh.material_override = Materials.solid("stone")
	pillar_mesh.position = Vector3(0, 0.7, 0)
	pillar.add_child(pillar_mesh)
	add_child(pillar)

	for i in _required:
		var cell := MeshInstance3D.new()
		var cell_mesh := BoxMesh.new()
		cell_mesh.size = Vector3(0.44, 0.18, 0.44)
		cell.mesh = cell_mesh
		cell.material_override = Materials.solid("battery_tip")
		cell.position = Vector3(1.9, 1.55 + i * 0.24, 0)
		add_child(cell)
		_cells.append(cell)

	_label = Label3D.new()
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.font_size = 64
	_label.pixel_size = 0.006
	_label.outline_size = 12
	_label.position = Vector3(0, 3.2, 0)
	add_child(_label)

	var area := Area3D.new()
	area.collision_layer = Layers.INTERACT
	area.collision_mask = 0
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 1.8
	shape.shape = sphere
	shape.position = Vector3(0, 1.2, 0)
	area.add_child(shape)
	add_child(area)

	Game.batteries_changed.connect(_refresh)
	_refresh(Game.carried_batteries, Game.inserted_batteries, Game.required_batteries)


func _process(delta: float) -> void:
	var charged := Game.can_teleport()
	_spin += delta * (2.2 if charged else 0.5)
	_ring.rotation.y = _spin
	_ring.position.y = 2.3 + (sin(_spin * 1.5) * 0.12 if charged else 0.0)


func _refresh(_carried: int, inserted: int, _req: int) -> void:
	for i in _cells.size():
		var filled := i < inserted
		_cells[i].material_override = Materials.solid("battery", 1.2) if filled else Materials.solid("battery_tip")
	if Game.can_teleport():
		_label.text = "PRET"
		_label.modulate = Palette.color("teleporter_ring")
		_ring.material_override = Materials.solid("teleporter_ring", 2.0)
	else:
		_label.text = "%d / %d piles" % [inserted, _required]
		_label.modulate = Color.WHITE
		_ring.material_override = Materials.solid("teleporter_ring", 0.15)


func interact(_player: Node) -> void:
	if Game.insert_batteries() > 0:
		return
	if Game.can_teleport():
		depart_requested.emit()


func prompt_text(_player: Node) -> String:
	if Game.can_teleport():
		return "E : se teleporter"
	if Game.carried_batteries > 0:
		return "E : inserer les piles"
	var missing := Game.required_batteries - Game.inserted_batteries
	return "Il manque %d pile%s" % [missing, "s" if missing > 1 else ""]
