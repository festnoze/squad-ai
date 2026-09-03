class_name PhotoContent
extends Node3D
## Builds the 3D content of a photo definition, in one of two modes that must
## stay geometrically identical (that identity IS the optical illusion):
##
##   ghost = true  : transparent preview, no collision (legacy mode, unused by
##                   the placer since v4: the raised photo is a 2D picture)
##   ghost = false : solid props. Non-loose boxes become ErasableBlocks (the
##                   placed content is itself replaceable by the next photo),
##                   loose boxes and batteries become RigidBody3D (they fall),
##                   the backdrop becomes a thin carvable painted wall.
##   display = true: solid LOOK but inert, meshes only, no groups, no pickups.
##                   Used by PhotoSnaps to render the picture of the photo in
##                   an offscreen viewport without touching gameplay state.
##
## Everything is expressed in the local space of this node; the placer sets the
## node's global transform to the camera anchor.

const BatteryScript := preload("res://src/pickups/battery.gd")
const PhotoItemScript := preload("res://src/photo/photo_item.gd")

var _ghost := false
var _display := false


func setup(def: Dictionary, ghost: bool, display := false) -> void:
	_ghost = ghost
	_display = display and not ghost
	if not ghost and not _display:
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
	if prop["kind"] == "stairs" and not _ghost and not _display:
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

	if _ghost or _display or not with_collision:
		mesh_instance.position = prim["center"]
		if _ghost:
			mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mesh_instance)
		return

	if not cylinder:
		if prim.get("loose", false):
			_add_loose_box(prim, mesh_instance)
		else:
			# Solid box: a carvable block, so the placed content is itself
			# replaceable by the next photo.
			# Placed content joins the permanent half of the ground language,
			# unless the photo painted it lavender on purpose.
			var block := ErasableBlock.create(size, prim["color"], 0.0, PackedStringArray(), prim["color"] == "erasable")
			add_child(block)
			block.position = prim["center"]
		return

	var body := StaticBody3D.new()
	body.position = prim["center"]
	body.collision_layer = Layers.WORLD
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var cyl_shape := CylinderShape3D.new()
	cyl_shape.radius = size.x * 0.5
	cyl_shape.height = size.y
	shape.shape = cyl_shape
	body.add_child(shape)
	body.add_child(mesh_instance)
	add_child(body)


## Loose boxes (small captured objects, the catalog crate) obey gravity:
## placed upside down or over a gap, they fall. That is the point.
func _add_loose_box(prim: Dictionary, mesh_instance: MeshInstance3D) -> void:
	var size: Vector3 = prim["size"]
	var body := RigidBody3D.new()
	body.position = prim["center"]
	body.collision_layer = Layers.WORLD
	body.collision_mask = Layers.WORLD
	body.mass = clampf(size.x * size.y * size.z * 2.0, 1.0, 10.0)
	var shape := CollisionShape3D.new()
	var box_shape := BoxShape3D.new()
	box_shape.size = size
	shape.shape = box_shape
	body.add_child(shape)
	body.add_child(mesh_instance)
	add_child(body)
	Rewind.track_body(body)


func _build_battery(prim: Dictionary) -> void:
	if _ghost or _display:
		var mesh_instance := MeshInstance3D.new()
		var cyl := CylinderMesh.new()
		cyl.top_radius = 0.16
		cyl.bottom_radius = 0.16
		cyl.height = 0.55
		mesh_instance.mesh = cyl
		mesh_instance.material_override = Materials.ghost("battery") if _ghost else Materials.solid("battery", 0.8)
		if _ghost:
			mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh_instance.position = prim["center"]
		add_child(mesh_instance)
		return
	# Placed batteries are ALWAYS physical: a rigid shell carrying the real
	# pickup, so a battery placed in the air falls where gravity says.
	var body := RigidBody3D.new()
	body.position = prim["center"]
	body.collision_layer = Layers.WORLD
	body.collision_mask = Layers.WORLD
	body.mass = 1.5
	var shape := CollisionShape3D.new()
	var box_shape := BoxShape3D.new()
	box_shape.size = Vector3(0.36, 0.72, 0.36)
	shape.shape = box_shape
	body.add_child(shape)
	# FILM DOES NOT PRINT FILM. A battery that came out of a photo is leaden:
	# worth exactly one battery to a teleporter, and never a subject again.
	# Without this the economy of the whole game collapses, because a copy is
	# itself a model: with C batteries and F films a player who photographs a
	# copy next to its original walks away with C x 2^F, and no teleporter
	# requirement means anything. Reading it in the color also makes the rule
	# visible from level 2, long before a level is built on it.
	var battery: Node3D = BatteryScript.new()
	battery.setup(true)
	battery.position = Vector3(0, -0.36, 0)
	body.add_child(battery)
	add_child(body)
	Rewind.track_body(body)


## Photo-in-photo: the solid content materializes a real pickable PhotoItem.
func _build_photo_item(prim: Dictionary) -> void:
	if _ghost or _display:
		var mesh_instance := MeshInstance3D.new()
		var box := BoxMesh.new()
		box.size = prim["size"]
		mesh_instance.mesh = box
		mesh_instance.material_override = Materials.ghost("frame") if _ghost else Materials.solid("frame")
		if _ghost:
			mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mesh_instance.position = prim["center"]
		add_child(mesh_instance)
		return
	var item: Node3D = PhotoItemScript.new()
	item.setup(prim["photo_id"])
	item.position = prim["center"]
	add_child(item)


## Invisible walkable ramp along the hypotenuse of the flight, from the foot
## of the stairs to the top-back corner. It carries ALL the collision: the
## eight visual steps have none, because a character controller cannot climb
## eight small boxes. The ramp passes through the BACK-top corner of each
## step, so the step lips stand proud of it (up to 0.575 m on the catalog
## flight); that is invisible in play and is not a bug. A carvable block like
## everything else: carve_with_frustum samples in local space, so its
## rotation is handled.
func _build_stairs_ramp(prop: Dictionary) -> void:
	var pos: Vector3 = prop["pos"]
	var size: Vector3 = prop["size"]
	var slope := atan2(size.y, size.z)
	var length := Vector2(size.y, size.z).length()
	var block := ErasableBlock.create(Vector3(size.x, 0.4, length), prop.get("color", "stone"), 0.0, PackedStringArray(), false)
	block.show_mesh = false
	add_child(block)
	var pivot := Vector3(pos.x, pos.y + size.y * 0.5, pos.z - size.z * 0.5)
	block.position = pivot + Vector3(0, -0.2, 0).rotated(Vector3.RIGHT, slope)
	block.rotation.x = slope


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
	if _display:
		mesh_instance.position = Vector3(0, 0, -depth)
		add_child(mesh_instance)
		return
	# The painted wall is a thin CARVABLE block, and it has to be: it is the
	# most ephemeral thing in the world (painted sky), it appears wherever the
	# player happens to aim, and a permanent one could wall off a route with no
	# way back. Being carvable, the next photo pierces it. The gradient quad
	# hugs its front face; carved fragments fall back to the block's own flat
	# color (assumed).
	var block := ErasableBlock.create(Vector3(size.x, size.y, 0.2), backdrop.get("top", "sky_top"), 0.0, PackedStringArray(), true)
	add_child(block)
	block.position = Vector3(0, 0, -depth)
	mesh_instance.position = Vector3(0, 0, 0.101)
	block.add_child(mesh_instance)


func _material(key: String) -> StandardMaterial3D:
	if _ghost:
		return Materials.ghost(key)
	return Materials.solid(key)
