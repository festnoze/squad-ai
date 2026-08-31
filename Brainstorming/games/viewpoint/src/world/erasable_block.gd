class_name ErasableBlock
extends StaticBody3D
## An erasable box that supports PARTIAL erasure: instead of vanishing whole,
## the part of its volume caught in a placed photo's frustum is carved out and
## the remainder survives as smaller ErasableBlocks (themselves carvable).
##
## The cut is box-minus-box: the hole is the axis-aligned bounding box (in
## this block's local space) of the sampled frustum intersection, and the
## remainder decomposes into at most 6 slabs. The AABB over-approximates the
## hole when the photo is placed at an angle, which errs on the generous side
## for the player (the opening is at least as big as the frame).

const SAMPLE_SPACING := 0.15
const MAX_STEPS := 36
const MIN_FRAGMENT := 0.08

var block_size := Vector3.ONE
var color_key := "erasable"


static func create(size: Vector3, color: String) -> ErasableBlock:
	var block := ErasableBlock.new()
	block.block_size = size
	block.color_key = color
	return block


func _ready() -> void:
	add_to_group("erasable")
	collision_layer = Layers.WORLD
	collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = block_size
	shape.shape = box
	add_child(shape)
	var mesh_instance := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = block_size
	mesh_instance.mesh = mesh
	mesh_instance.material_override = Materials.solid(color_key, 0.25)
	add_child(mesh_instance)


## Carves the intersection with the photo frustum out of this block.
## Returns true when the block was modified (fragmented or fully removed).
func carve_with_frustum(anchor: Transform3D, fov_deg: float, aspect: float, depth: float) -> bool:
	var to_anchor := anchor.affine_inverse()
	var steps := Vector3i(_axis_steps(block_size.x), _axis_steps(block_size.y), _axis_steps(block_size.z))
	var spacing := Vector3(
		block_size.x / (steps.x - 1),
		block_size.y / (steps.y - 1),
		block_size.z / (steps.z - 1)
	)
	var box_min := -block_size * 0.5

	var found := false
	var lo := Vector3.INF
	var hi := -Vector3.INF
	for ix in steps.x:
		for iy in steps.y:
			for iz in steps.z:
				var local := box_min + Vector3(ix * spacing.x, iy * spacing.y, iz * spacing.z)
				var in_anchor := to_anchor * (global_transform * local)
				if PhotoMath.point_in_frustum(in_anchor, fov_deg, aspect, 0.0, depth):
					found = true
					lo = lo.min(local)
					hi = hi.max(local)
	if not found:
		return false

	# Grow by half a sample step so no film thinner than the sampling grid
	# survives along the hole borders.
	var hole_min := lo - spacing * 0.51
	var hole_max := hi + spacing * 0.51

	var pieces := decompose(block_size, hole_min, hole_max)
	var parent := get_parent()
	for piece in pieces:
		var fragment := ErasableBlock.create(piece["size"], color_key)
		parent.add_child(fragment)
		fragment.global_transform = global_transform.translated_local(piece["center"])
	queue_free()
	return true


## Pure geometry: the box of the given size (centered on the origin) minus the
## hole AABB, decomposed into at most 6 slabs {center, size}. Degenerate slabs
## thinner than MIN_FRAGMENT are dropped. Public and static for the tests.
static func decompose(size: Vector3, hole_min: Vector3, hole_max: Vector3) -> Array:
	var box_min := -size * 0.5
	var box_max := size * 0.5
	var lo := hole_min.clamp(box_min, box_max)
	var hi := hole_max.clamp(box_min, box_max)
	var pieces: Array = []
	# Left / right of the hole, full height and thickness.
	_push_piece(pieces, box_min, Vector3(lo.x, box_max.y, box_max.z))
	_push_piece(pieces, Vector3(hi.x, box_min.y, box_min.z), box_max)
	# Below / above the hole, within its x span.
	_push_piece(pieces, Vector3(lo.x, box_min.y, box_min.z), Vector3(hi.x, lo.y, box_max.z))
	_push_piece(pieces, Vector3(lo.x, hi.y, box_min.z), Vector3(hi.x, box_max.y, box_max.z))
	# In front / behind the hole, within its x and y span.
	_push_piece(pieces, Vector3(lo.x, lo.y, box_min.z), Vector3(hi.x, hi.y, lo.z))
	_push_piece(pieces, Vector3(lo.x, lo.y, hi.z), Vector3(hi.x, hi.y, box_max.z))
	return pieces


static func _push_piece(pieces: Array, a: Vector3, b: Vector3) -> void:
	var piece_size := b - a
	if piece_size.x < MIN_FRAGMENT or piece_size.y < MIN_FRAGMENT or piece_size.z < MIN_FRAGMENT:
		return
	pieces.append({"center": (a + b) * 0.5, "size": piece_size})


static func _axis_steps(dim: float) -> int:
	return clampi(int(ceil(dim / SAMPLE_SPACING)) + 1, 2, MAX_STEPS)
