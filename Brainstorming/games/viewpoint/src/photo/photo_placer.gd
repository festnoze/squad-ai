class_name PhotoPlacer
extends Node3D
## Holds the photo the player carries and turns it into world geometry.
##
## This node is a child of the player camera with an identity local transform,
## so its global transform IS the placement anchor. Since v4 there is NO 3D
## ghost preview: the player raises the 2D picture (right click), rotates it
## (wheel), and only discovers the 3D result at placement. Placing REPLACES
## everything caught in the photo frustum (up to the backdrop depth) by the
## photo content: an empty sky photo pierces the world.

const PhotoItemScript := preload("res://src/photo/photo_item.gd")
const PhotoContentScript := preload("res://src/photo/photo_content.gd")

var held_id := ""
## Roll of the held photo around the view axis, in 90 degree steps. Applied to
## this node itself, so the anchor rotates with the picture shown on the HUD.
var roll_steps := 0
## True while the photo is raised to the eye (right click): the HUD shows the
## picture, rotated by roll_steps, over the exact screen region the placement
## frustum covers.
var raised := false

var _level_root: Node3D


func setup(level_root: Node3D) -> void:
	_level_root = level_root


func hold(id: String) -> bool:
	if held_id != "" or PhotoDefs.get_def(id).is_empty():
		return false
	held_id = id
	_set_roll(0)
	return true


## Rotates the held photo by steps of 90 degrees (mouse wheel).
func rotate_held(direction: int) -> void:
	if held_id == "":
		return
	_set_roll(posmod(roll_steps + direction, 4))


## Raises or lowers the held photo (right click). Raised, the player sees the
## PICTURE aligned on the frustum, rotated by the current roll.
func raise_toggle() -> void:
	if held_id == "":
		return
	raised = not raised


## Materializes the held photo at the current camera anchor: REPLACES what the
## photo frustum reaches, then builds the solid content.
func place() -> bool:
	if held_id == "":
		return false
	var def := PhotoDefs.get_def(held_id)
	var anchor := global_transform

	# Replacement, two passes before instancing. Pass 1: every carvable block
	# (platforms, decor, lavender, placed content, backdrops) loses the part of
	# its volume caught in the frustum and survives as fragments. Pass 2: every
	# breakable body (cages) whose center falls in the frustum vanishes whole.
	# Never replaced: teleporter, batteries, photo items, camera, player.
	# The group lists are snapshots, so fragments spawned during the loop are
	# not re-visited.
	var depth: float = def.get("erase_depth", PhotoMath.DEFAULT_ERASE_DEPTH)
	var to_anchor := anchor.affine_inverse()
	for node in get_tree().get_nodes_in_group("carvable"):
		var block := node as ErasableBlock
		if block == null or not is_instance_valid(block) or block.is_queued_for_deletion():
			continue
		block.carve_with_frustum(anchor, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, depth)
	for node in get_tree().get_nodes_in_group("breakable"):
		var body := node as Node3D
		if body == null or not is_instance_valid(body) or body.is_queued_for_deletion():
			continue
		var local := to_anchor * body.global_position
		if PhotoMath.point_in_frustum(local, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, 0.0, depth):
			Rewind.retire(body)

	var content: Node3D = PhotoContentScript.new()
	content.setup(def, false)
	_level_root.add_child(content)
	content.global_transform = anchor
	Rewind.notice_spawn(content)

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
	Rewind.notice_spawn(item)
	_clear_held()
	return true


func held_title() -> String:
	if held_id == "":
		return ""
	return PhotoDefs.get_def(held_id).get("title", held_id)


## Puts the hand back where a rewind snapshot found it: a photo placed a
## moment ago is in hand again, lowered.
func restore_held(id: String, roll: int) -> void:
	if held_id != id:
		held_id = id
		raised = false
	_set_roll(roll)


func _clear_held() -> void:
	held_id = ""
	raised = false
	_set_roll(0)


func _set_roll(steps: int) -> void:
	roll_steps = steps
	basis = roll_basis(steps)


## THE ONE DIRECTION OF THE WHEEL. A step down turns the picture 90
## degrees CLOCKWISE as the player sees it, and that has to be true of the
## world as well as of the HUD, or the promise of the game is broken: what
## you see raised is what you place.
##
## The sign is not a matter of taste. This node is a child of the camera,
## which looks down its own -z, so local +z points BACK at the player. A
## positive rotation about an axis aimed at the viewer reads
## counter-clockwise, which is the opposite of what a Control does on the
## HUD (2D y is down, so a positive rotation reads clockwise there). Hence
## the minus: it is what makes the two agree.
static func roll_basis(steps: int) -> Basis:
	return Basis(Vector3(0, 0, 1), -steps * PI * 0.5)
