class_name LevelBuilder
## Turns a LevelDefs dictionary into nodes under the given root. Everything a
## level owns lives under that root, so unloading a level is freeing the
## root's children (placed photo contents included).

const BatteryScript := preload("res://src/pickups/battery.gd")
const CameraItemScript := preload("res://src/pickups/camera_item.gd")
const PhotoItemScript := preload("res://src/photo/photo_item.gd")
const TeleporterScript := preload("res://src/world/teleporter.gd")

## Purely decorative islands floating around every level, for depth.
const DECOR_ISLANDS := [
	{"pos": Vector3(-30, -9, -25), "size": Vector3(7, 2, 6)},
	{"pos": Vector3(26, -13, -12), "size": Vector3(5, 1.6, 5)},
	{"pos": Vector3(18, -7, -38), "size": Vector3(9, 2.4, 7)},
	{"pos": Vector3(-24, -15, 10), "size": Vector3(4, 1.4, 4)},
	{"pos": Vector3(32, -10, 22), "size": Vector3(6, 2, 6)},
	{"pos": Vector3(-14, -18, 34), "size": Vector3(8, 2.2, 6)},
]


static func build(root: Node3D, def: Dictionary) -> Teleporter:
	for platform in def.get("platforms", []):
		_add_platform(root, platform["pos"], platform["size"], platform.get("soft", false))
	for decor in def.get("decor", []):
		# Decor is part of the fixed world: permanent, like the grey ground.
		var decor_block := ErasableBlock.create(decor["size"], decor.get("color", "wood"), 0.0, PackedStringArray(), false)
		root.add_child(decor_block)
		decor_block.position = decor["pos"]
	for erasable in def.get("erasables", []):
		# The "erasable" group is now only a lavender marker (readability and
		# tests): every block is carvable anyway.
		var block := ErasableBlock.create(erasable["size"], "erasable", 0.25, PackedStringArray(["erasable"]))
		root.add_child(block)
		block.position = erasable["pos"]
	for cage in def.get("cages", []):
		_add_cage(root, cage)
	for photo in def.get("photos", []):
		var item: Node3D = PhotoItemScript.new()
		item.setup(photo["id"])
		root.add_child(item)
		item.position = photo["pos"]
	for battery_pos in def.get("batteries", []):
		var battery: Node3D = BatteryScript.new()
		battery.setup(false)
		root.add_child(battery)
		battery.position = battery_pos
	for sealed_pos in def.get("sealed_batteries", []):
		# Same battery, same value to a teleporter, but no film prints it.
		var sealed_battery: Node3D = BatteryScript.new()
		sealed_battery.setup(true)
		root.add_child(sealed_battery)
		sealed_battery.position = sealed_pos
	var camera_def: Dictionary = def.get("camera", {})
	if not camera_def.is_empty():
		var camera_item: Node3D = CameraItemScript.new()
		camera_item.setup(camera_def["films"])
		root.add_child(camera_item)
		camera_item.position = camera_def["pos"]
	for island in DECOR_ISLANDS:
		_add_island(root, island["pos"], island["size"])

	var tele_def: Dictionary = def["teleporter"]
	var teleporter: Teleporter = TeleporterScript.new()
	teleporter.setup(tele_def["required"])
	root.add_child(teleporter)
	teleporter.position = tele_def["pos"]
	return teleporter


## Ground. Grey by default and PERMANENT: a photo placed over it is added to
## it, the slab stays. A "soft" platform is pale instead, and the frame carves
## it like a lavender wall: that is the whole language, said in color.
static func _add_platform(root: Node3D, pos: Vector3, size: Vector3, soft := false) -> void:
	var groups := PackedStringArray(["platform"])
	if soft:
		groups.append("erasable")
	var block := ErasableBlock.create(size, "platform_soft" if soft else "platform", 0.0, groups, soft)
	root.add_child(block)
	block.position = pos

	# Sand-colored skirt hanging under the slab, so islands read as terrain.
	# Child of the block: it vanishes with it (carved fragments have no skirt).
	var skirt := MeshInstance3D.new()
	var skirt_mesh := BoxMesh.new()
	skirt_mesh.size = Vector3(size.x * 0.9, size.y * 1.6, size.z * 0.9)
	skirt.mesh = skirt_mesh
	skirt.material_override = Materials.solid("platform_soft_side" if soft else "platform_side")
	skirt.position = Vector3(0, -size.y * 1.1, 0)
	block.add_child(skirt)


## Barred cage. Visuals are bars with gaps (the loot inside stays visible),
## collision is four full thin walls plus an optional roof, so neither the
## player nor the interaction ray gets through. One single body: breaking the
## cage removes everything at once. pos is the center of the cage floor.
##
## Two kinds, told apart by color the way the ground is:
##   ordinary (lavender or dark) : any placement framing its center breaks it.
##   "sealed": true, steel grey  : NO placement ever breaks it. The bars still
##       do not stop the lens, so the way out of a steel cage is to photograph
##       what is inside and materialize the copy somewhere reachable.
static func _add_cage(root: Node3D, cage: Dictionary) -> void:
	var pos: Vector3 = cage["pos"]
	var size: Vector3 = cage["size"]
	var sealed: bool = cage.get("sealed", false)
	var erasable: bool = cage.get("erasable", true) and not sealed
	var roof: bool = cage.get("roof", true)
	var color := "erasable" if erasable else ("sealed" if sealed else "battery_tip")
	var material := Materials.solid(color, 0.25 if erasable else 0.0)

	var body := StaticBody3D.new()
	body.collision_layer = Layers.WORLD
	body.collision_mask = 0
	body.position = pos + Vector3(0, size.y * 0.5, 0)
	# "cage" is what the lens sees; "breakable" is what a placement may remove.
	# A steel cage is in the first group only.
	body.add_to_group("cage")
	if not sealed:
		body.add_to_group("breakable")
	body.set_meta("cage_size", size)
	body.set_meta("cage_color", color)

	# The four walls: invisible full collision + visible bars and rails.
	var faces := [
		{"offset": Vector3(size.x * 0.5 - 0.06, 0, 0), "wall": Vector3(0.12, size.y, size.z), "along_x": false},
		{"offset": Vector3(-size.x * 0.5 + 0.06, 0, 0), "wall": Vector3(0.12, size.y, size.z), "along_x": false},
		{"offset": Vector3(0, 0, size.z * 0.5 - 0.06), "wall": Vector3(size.x, size.y, 0.12), "along_x": true},
		{"offset": Vector3(0, 0, -size.z * 0.5 + 0.06), "wall": Vector3(size.x, size.y, 0.12), "along_x": true},
	]
	for face in faces:
		var shape := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = face["wall"]
		shape.shape = box
		shape.position = face["offset"]
		body.add_child(shape)
		_add_cage_bars(body, face["offset"], face["wall"], face["along_x"], material)

	if roof:
		var roof_shape := CollisionShape3D.new()
		var roof_box := BoxShape3D.new()
		roof_box.size = Vector3(size.x, 0.12, size.z)
		roof_shape.shape = roof_box
		roof_shape.position = Vector3(0, size.y * 0.5 - 0.06, 0)
		body.add_child(roof_shape)
		var roof_mesh := MeshInstance3D.new()
		var roof_box_mesh := BoxMesh.new()
		roof_box_mesh.size = Vector3(size.x, 0.1, size.z)
		roof_mesh.mesh = roof_box_mesh
		roof_mesh.material_override = material
		roof_mesh.position = Vector3(0, size.y * 0.5 - 0.05, 0)
		body.add_child(roof_mesh)

	root.add_child(body)


static func _add_cage_bars(body: StaticBody3D, offset: Vector3, wall: Vector3, along_x: bool, material: StandardMaterial3D) -> void:
	var span: float = wall.x if along_x else wall.z
	var bar_count := maxi(int(span / 0.5), 2)
	for i in bar_count + 1:
		var t := -span * 0.5 + span * float(i) / float(bar_count)
		var bar := MeshInstance3D.new()
		var bar_mesh := BoxMesh.new()
		bar_mesh.size = Vector3(0.07, wall.y, 0.07)
		bar.mesh = bar_mesh
		bar.material_override = material
		bar.position = offset + (Vector3(t, 0, 0) if along_x else Vector3(0, 0, t))
		body.add_child(bar)
	for rail_y in [wall.y * 0.5 - 0.06, -wall.y * 0.5 + 0.06]:
		var rail := MeshInstance3D.new()
		var rail_mesh := BoxMesh.new()
		rail_mesh.size = Vector3(span, 0.1, 0.1) if along_x else Vector3(0.1, 0.1, span)
		rail.mesh = rail_mesh
		rail.material_override = material
		rail.position = offset + Vector3(0, rail_y, 0)
		body.add_child(rail)


static func _add_island(root: Node3D, pos: Vector3, size: Vector3) -> void:
	var mesh_instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = size
	mesh_instance.mesh = mesh
	mesh_instance.material_override = Materials.solid("platform_side")
	mesh_instance.position = pos
	root.add_child(mesh_instance)
	var top := MeshInstance3D.new()
	var top_mesh := BoxMesh.new()
	top_mesh.size = Vector3(size.x * 1.05, 0.3, size.z * 1.05)
	top.mesh = top_mesh
	top.material_override = Materials.solid("platform")
	top.position = pos + Vector3(0, size.y * 0.5 + 0.1, 0)
	root.add_child(top)
