class_name PhotoPlacer
extends Node3D
## Holds the photo the player carries and turns it into world geometry.
##
## This node is a child of the player camera with an identity local transform,
## so its global transform IS the placement anchor. The ghost preview is built
## as a direct child: it therefore occupies exactly the volume the solid
## content will occupy at the moment of the click. That strict equality is the
## whole optical illusion (PRD section 3.2), so nothing here ever offsets or
## re-levels the anchor.

const PhotoItemScript := preload("res://src/photo/photo_item.gd")
const PhotoContentScript := preload("res://src/photo/photo_content.gd")

var held_id := ""
## Roll of the held photo around the view axis, in 90 degree steps. Applied to
## this node itself, so the ghost AND the anchor rotate together and the
## ghost = solid equality survives rotation untouched.
var roll_steps := 0

var _level_root: Node3D
var _ghost: Node3D


func setup(level_root: Node3D) -> void:
	_level_root = level_root


func hold(id: String) -> bool:
	if held_id != "" or PhotoDefs.get_def(id).is_empty():
		return false
	held_id = id
	_set_roll(0)
	_ghost = PhotoContentScript.new()
	_ghost.setup(PhotoDefs.get_def(id), true)
	add_child(_ghost)
	return true


## Rotates the held photo by steps of 90 degrees (mouse wheel).
func rotate_held(direction: int) -> void:
	if held_id == "":
		return
	_set_roll(posmod(roll_steps + direction, 4))


## Materializes the held photo at the current camera anchor: erases erasable
## world objects caught in the photo frustum, then builds the solid content.
func place() -> bool:
	if held_id == "":
		return false
	var def := PhotoDefs.get_def(held_id)
	var anchor := global_transform

	# Carvable blocks (walls, crates) lose only the part of their volume caught
	# in the photo frustum and survive as fragments; objects without a carve
	# (cages) still vanish whole when their center is framed. The group list is
	# a snapshot, so fragments spawned during the loop are not re-visited.
	var depth: float = def.get("erase_depth", PhotoMath.DEFAULT_ERASE_DEPTH)
	var to_anchor := anchor.affine_inverse()
	for node in get_tree().get_nodes_in_group("erasable"):
		var erasable := node as Node3D
		if erasable == null or not is_instance_valid(erasable):
			continue
		if erasable.has_method("carve_with_frustum"):
			erasable.carve_with_frustum(anchor, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, depth)
			continue
		var local := to_anchor * erasable.global_position
		if PhotoMath.point_in_frustum(local, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, 0.0, depth):
			erasable.queue_free()

	var content: Node3D = PhotoContentScript.new()
	content.setup(def, false)
	_level_root.add_child(content)
	content.global_transform = anchor

	_clear_held()
	return true


## Puts the held photo back into the world as a pickable item, in front of
## the player, so no photo is ever lost.
func drop() -> bool:
	if held_id == "":
		return false
	var camera := get_parent() as Node3D
	var flat_forward := -camera.global_basis.z
	flat_forward.y = 0.0
	flat_forward = flat_forward.normalized() if flat_forward.length() > 0.01 else Vector3.FORWARD
	var item: Node3D = PhotoItemScript.new()
	item.setup(held_id)
	_level_root.add_child(item)
	item.global_position = camera.global_position + flat_forward * 1.4 - Vector3(0, 0.4, 0)
	_clear_held()
	return true


func held_title() -> String:
	if held_id == "":
		return ""
	return PhotoDefs.get_def(held_id).get("title", held_id)


func _clear_held() -> void:
	held_id = ""
	_set_roll(0)
	if is_instance_valid(_ghost):
		_ghost.queue_free()
	_ghost = null


func _set_roll(steps: int) -> void:
	roll_steps = steps
	rotation = Vector3(0, 0, steps * PI * 0.5)
