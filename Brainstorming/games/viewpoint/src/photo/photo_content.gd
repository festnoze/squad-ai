class_name PhotoContent
extends Node3D
## Builds the 3D content of a photo definition, in one of two modes that must
## stay geometrically identical (that identity IS the optical illusion):
##
##   ghost = true  : transparent preview, no collision, parented to the camera
##   ghost = false : solid StaticBody3D props, battery props become real
##                   pickups, the backdrop becomes a physical wall
##
## Everything is expressed in the local space of this node; the placer sets the
## node's global transform to the camera anchor.

const BatteryScript := preload("res://src/pickups/battery.gd")
const PhotoItemScript := preload("res://src/photo/photo_item.gd")

var _ghost := false


func setup(def: Dictionary, ghost: bool) -> void:
	_ghost = ghost
	if not ghost:
		add_to_group("placed_content")
	for prop in def.get("props", []):
		_build_prop(prop)
	var backdrop: Dictionary = def.get("backdrop", {})
	if not backdrop.is_empty():
		_build_backdrop(backdrop)


func _build_prop(prop: Dictionary) -> void:
	for prim in PhotoDefs.expand_prop(prop):
		match prim["kind"]:
			"battery":
				_build_battery(prim)
			"photo_item":
				_build_photo_item(prim)
			"cylinder":
				_add_shape(prim, true, prop["kind"] != "stairs")
			_:
				# Stairs get their collision from a single walkable ramp below,
				# not from eight tiny step boxes the character cannot climb.
				_add_shape(prim, false, prop["kind"] != "stairs")
	if prop["kind"] == "stairs" and not _ghost:
		_build_stairs_ramp(prop)


func _add_shape(prim: Dictionary, cylinder: bool, with_collision: bool) -> void:
	var size: Vector3 = prim["size"]
	var mesh_instance := MeshInstance3D.new()
	if cylinder:
		var cyl := CylinderMesh.new()
		cyl.top_radius = size.x * 0.5
		cyl.bottom_radius = size.x * 0.5
		cyl.height = size.y
		mesh_instance.mesh = cyl
	else:
		var box := BoxMesh.new()
		box.size = size
		mesh_instance.mesh = box
	mesh_instance.material_override = _material(prim["color"])

	if _ghost or not with_collision:
		mesh_instance.position = prim["center"]
		if _ghost:
			mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mesh_instance)
		return

	var body := StaticBody3D.new()
	body.position = prim["center"]
	body.collision_layer = Layers.WORLD
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	if cylinder:
		var cyl_shape := CylinderShape3D.new()
		cyl_shape.radius = size.x * 0.5
		cyl_shape.height = size.y
		shape.shape = cyl_shape
	else:
		var box_shape := BoxShape3D.new()
		box_shape.size = size
		shape.shape = box_shape
	body.add_child(shape)
	body.add_child(mesh_instance)
	add_child(body)


func _build_battery(prim: Dictionary) -> void:
	if _ghost:
		var mesh_instance := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.16
		cyl.bottom_radius = 0.16
		cyl.height = 0.55
		mesh_instance.mesh = cyl
		mesh_instance.material_override = Materials.ghost("battery")
		mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh_instance.position = prim["center"]
		add_child(mesh_instance)
		return
	var battery: Node3D = BatteryScript.new()
	# Battery origin is its base; the primitive center is half a battery up.
	battery.position = prim["center"] - Vector3(0, 0.35, 0)
	add_child(battery)


## Photo-in-photo: the solid content materializes a real pickable PhotoItem.
func _build_photo_item(prim: Dictionary) -> void:
	if _ghost:
		var mesh_instance := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = prim["size"]
		mesh_instance.mesh = box
		mesh_instance.material_override = Materials.ghost("frame")
		mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh_instance.position = prim["center"]
		add_child(mesh_instance)
		return
	var item: Node3D = PhotoItemScript.new()
	item.setup(prim["photo_id"])
	item.position = prim["center"]
	add_child(item)


## Invisible walkable ramp along the hypotenuse of the flight. The visual
## steps' front-top edges lie exactly on this surface.
func _build_stairs_ramp(prop: Dictionary) -> void:
	var pos: Vector3 = prop["pos"]
	var size: Vector3 = prop["size"]
	var slope := atan2(size.y, size.z)
	var length := Vector2(size.y, size.z).length()
	var body := StaticBody3D.new()
	body.collision_layer = Layers.WORLD
	body.collision_mask = 0
	body.position = Vector3(pos.x, pos.y + size.y * 0.5, pos.z - size.z * 0.5)
	body.rotation.x = slope
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(size.x, 0.4, length)
	shape.shape = box
	shape.position = Vector3(0, -0.2, 0)
	body.add_child(shape)
	add_child(body)


func _build_backdrop(backdrop: Dictionary) -> void:
	var depth: float = backdrop["depth"]
	var size := PhotoMath.backdrop_size(depth, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT)
	var mesh_instance := MeshInstance3D.new()
	var quad := QuadMesh.new()
	quad.size = size
	mesh_instance.mesh = quad
	if _ghost:
		mesh_instance.material_override = Materials.ghost(backdrop.get("top", "sky_top"))
		mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh_instance.position = Vector3(0, 0, -depth)
		add_child(mesh_instance)
		return
	mesh_instance.material_override = Materials.backdrop(backdrop.get("top", "sky_top"), backdrop.get("bottom", "sky_horizon"))
	var body := StaticBody3D.new()
	body.position = Vector3(0, 0, -depth)
	body.collision_layer = Layers.WORLD
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(size.x, size.y, 0.2)
	shape.shape = box
	body.add_child(shape)
	body.add_child(mesh_instance)
	add_child(body)


func _material(key: String) -> StandardMaterial3D:
	if _ghost:
		return Materials.ghost(key)
	return Materials.solid(key)
