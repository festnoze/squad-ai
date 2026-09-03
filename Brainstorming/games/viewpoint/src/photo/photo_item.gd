class_name PhotoItem
extends Node3D
## A polaroid found (or re-dropped) in the world. Node origin is the center of
## the frame; it bobs and slowly turns to catch the eye. Interacting hands the
## photo to the player's placer.

var _def_id := ""
var _bob_phase := 0.0
var _visual: Node3D
var _picture_mat: StandardMaterial3D
var _snap_timer := 0.0


func setup(def_id: String) -> void:
	_def_id = def_id


func _ready() -> void:
	assert(_def_id != "", "PhotoItem needs setup(def_id) before entering the tree")
	add_to_group("photo_item")
	_bob_phase = fposmod(global_position.x * 2.1 + global_position.z * 1.3, TAU)

	_visual = Node3D.new()
	add_child(_visual)

	var frame := MeshInstance3D.new()
	var frame_mesh := BoxMesh.new()
	frame_mesh.size = Vector3(0.72, 0.82, 0.035)
	frame.mesh = frame_mesh
	frame.material_override = Materials.solid("frame")
	_visual.add_child(frame)

	_picture_mat = StandardMaterial3D.new()
	_picture_mat.albedo_texture = PhotoSnaps.get_texture(_def_id)
	_picture_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var picture_mat := _picture_mat
	for facing_sign in [1.0, -1.0]:
		var picture := MeshInstance3D.new()
		var quad := QuadMesh.new()
		quad.size = Vector2(0.66, 0.76)
		picture.mesh = quad
		picture.material_override = picture_mat
		picture.position = Vector3(0, 0, 0.019 * facing_sign)
		if facing_sign < 0.0:
			picture.rotation.y = PI
		_visual.add_child(picture)

	var area := Area3D.new()
	area.collision_layer = Layers.INTERACT
	area.collision_mask = 0
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.6
	shape.shape = sphere
	area.add_child(shape)
	add_child(area)


func _process(delta: float) -> void:
	_bob_phase = fposmod(_bob_phase + delta * 1.6, TAU)
	_visual.position.y = sin(_bob_phase) * 0.07
	_visual.rotation.y += delta * 0.8
	# The rendered picture may land after this item was built: adopt it.
	_snap_timer += delta
	if _snap_timer > 0.5:
		_snap_timer = 0.0
		var tex := PhotoSnaps.get_texture(_def_id)
		if _picture_mat.albedo_texture != tex:
			_picture_mat.albedo_texture = tex


func def_id() -> String:
	return _def_id


func interact(player: Node) -> void:
	var placer: PhotoPlacer = player.placer
	if placer.hold(_def_id):
		Rewind.retire(self)


func prompt_text(player: Node) -> String:
	var placer: PhotoPlacer = player.placer
	if placer.held_id != "":
		return "Mains pleines : posez (clic gauche) ou reposez (clic droit) votre photo"
	var def := PhotoDefs.get_def(_def_id)
	return "E : prendre la photo « %s »" % def.get("title", _def_id)
