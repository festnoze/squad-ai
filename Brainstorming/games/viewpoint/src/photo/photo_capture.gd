class_name PhotoCapture
## The in-game camera: taking a photo captures EVERYTHING the placement
## frustum frames, including the void, into a regular photo definition, which
## then flows through the same pipeline as the static catalog (hold, raise,
## rotate, place). An empty frame yields an empty photo of sky: placed, it
## pierces the world. capture() therefore never returns {}.
##
## What is photographable: every block of the world (platforms, walls, crates,
## placed content), every cage, and every battery EXCEPT the leaden ones.
## Capture is a COPY: the originals stay where they are. Bars, walls and glass
## do not block it, the test is geometric, and that is exactly how a steel cage
## is beaten: the lens reaches through the bars even though no placement will
## ever break them.
##
## Blocks are captured BY VOLUME, exactly the way a placement carves them: the
## photo keeps the part of the block that falls inside the frame, clipped, not
## the whole block. That symmetry is what keeps the ground under your feet
## working. A block is often far bigger than the frame (a 12 m platform whose
## center is behind the player), so a center test would never copy it while a
## placement WOULD carve the framed piece away: the player would blow a hole in
## the floor and fall through his own photo. Capturing the clipped volume means
## a photo puts back precisely what its own placement removes.
##
## One accepted approximation, documented for the level design: a captured
## volume is re-expressed axis-aligned in camera space, so a wall shot at an
## angle comes back facing the player.

const CAPTURE_DEPTH := 12.0
const CAPTURE_NEAR := 0.5
const MAX_PROPS := 32
## A captured box at most this big on every axis is loose: it falls when
## placed. The test is on the ORIGINAL object, not on the clipped piece: a
## corner of ground caught in the frame is still ground, not a falling crate.
const LOOSE_MAX_EXTENT := 1.6
## Pure core: the part of a box that lies inside the photo frustum, expressed
## in camera space as {center, size}. Empty when the box is out of frame.
## to_camera maps the box's own space (origin at its center) to camera space.
##
## Analytic, in two cases, because fidelity matters more than anything else
## here: a photo has to show the objects at their real place and size.
##
## - The box fits ENTIRELY in the frame (all eight corners inside the
##   frustum, which is convex, so the whole box is): it is kept AS IT IS,
##   its own size and its own center. Nothing is estimated.
## - The box straddles the frame: the copy is the intersection of its
##   camera-space bounds with the frame, computed exactly (no sampling, so no
##   grid error and no inflating margin). This is the case of the ground under
##   the player, which a placement carves and a photo must therefore restore.
static func clip_to_frustum(size: Vector3, to_camera: Transform3D, far := CAPTURE_DEPTH) -> Dictionary:
	var lo := Vector3.INF
	var hi := -Vector3.INF
	var fully_framed := true
	for sx in [-0.5, 0.5]:
		for sy in [-0.5, 0.5]:
			for sz in [-0.5, 0.5]:
				var corner: Vector3 = to_camera * Vector3(size.x * sx, size.y * sy, size.z * sz)
				lo = lo.min(corner)
				hi = hi.max(corner)
				if not PhotoMath.point_in_frustum(corner, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, CAPTURE_NEAR, far):
					fully_framed = false
	if fully_framed:
		return {"center": to_camera * Vector3.ZERO, "size": size}

	# Depth first: outside the frame's depth range there is nothing to keep.
	lo.z = maxf(lo.z, -far)
	hi.z = minf(hi.z, -CAPTURE_NEAR)
	if hi.z <= lo.z:
		return {}
	# Then the frame itself, taken at the deepest point of the piece where the
	# frame is widest: a photo never holds anything outside its own borders.
	var half := PhotoMath.half_extent_at(-lo.z, PhotoMath.PHOTO_FOV_DEG)
	lo.x = maxf(lo.x, -half * PhotoMath.PHOTO_ASPECT)
	hi.x = minf(hi.x, half * PhotoMath.PHOTO_ASPECT)
	lo.y = maxf(lo.y, -half)
	hi.y = minf(hi.y, half)
	if hi.x <= lo.x or hi.y <= lo.y:
		return {}
	return {"center": (lo + hi) * 0.5, "size": hi - lo}


## Pure core, unit-testable: converts world candidates into photo props,
## sorted by increasing depth and capped at MAX_PROPS. Candidates:
##   {"kind": "box", "xform": Transform3D (global), "size", "color"}
##     kept by clipped volume, like the carve
##   {"kind": "battery", "pos": Vector3 (its base)}
static func props_from(candidates: Array, anchor: Transform3D) -> Array:
	var to_anchor := anchor.affine_inverse()
	var props: Array = []
	for candidate in candidates:
		var size: Vector3 = candidate.get("size", Vector3.ZERO)
		match candidate["kind"]:
			"battery":
				var base: Vector3 = candidate["pos"]
				# A battery is a point: the test uses its visual center.
				if _frames(to_anchor * (base + Vector3(0, 0.35, 0))):
					props.append({"kind": "battery", "pos": to_anchor * base, "size": Vector3.ZERO, "color": "battery"})
			_:
				var piece := clip_to_frustum(size, to_anchor * (candidate["xform"] as Transform3D))
				if piece.is_empty():
					continue
				var prop := {"kind": "box", "pos": piece["center"], "size": piece["size"], "color": candidate.get("color", "erasable")}
				# Loose follows the ORIGINAL object, not the slice taken of it.
				if size.x <= LOOSE_MAX_EXTENT and size.y <= LOOSE_MAX_EXTENT and size.z <= LOOSE_MAX_EXTENT:
					prop["loose"] = true
				props.append(prop)
	# Closest first (-z is forward, so depth is -pos.z), capped.
	props.sort_custom(func(a, b): return -a["pos"].z < -b["pos"].z)
	if props.size() > MAX_PROPS:
		props.resize(MAX_PROPS)
	return props


static func _frames(in_camera: Vector3) -> bool:
	return PhotoMath.point_in_frustum(in_camera, PhotoMath.PHOTO_FOV_DEG, PhotoMath.PHOTO_ASPECT, CAPTURE_NEAR, CAPTURE_DEPTH)


## Scene glue: collects the photographable nodes and assembles a definition.
## ALWAYS returns a valid def: props possibly empty, always a sky backdrop.
static func capture(anchor: Transform3D, tree: SceneTree) -> Dictionary:
	var candidates: Array = []
	# Everything the eye sees is photographable, permanent ground included:
	# a picture must show what was framed. Whether a block can be CARVED is a
	# different question, answered by the ground language at placement time.
	for node in tree.get_nodes_in_group("photographable"):
		var block := node as ErasableBlock
		if block == null or not is_instance_valid(block) or block.is_queued_for_deletion():
			continue
		candidates.append({"kind": "box", "xform": block.global_transform, "size": block.block_size, "color": block.color_key})
	# Cages are deliberately ABSENT from this list. Bars are a lattice, not a
	# volume: the lens goes through them, and what the film keeps is what
	# stands behind. Copying a cage as a solid block would seal its own copied
	# contents inside, which is the exact opposite of the fantasy ("the bars do
	# not stop the objective") and would make every caged battery useless the
	# moment it was photographed.
	# Batteries are read from the copyable group only: a
	# leaden battery leaves no trace on the film. That is the one thing in the
	# world the camera cannot see, and the levels are built around it.
	for node in tree.get_nodes_in_group("copyable_battery"):
		var battery := node as Node3D
		if battery == null or not is_instance_valid(battery) or battery.is_queued_for_deletion():
			continue
		candidates.append({"kind": "battery", "pos": battery.global_position, "size": Vector3.ZERO, "color": "battery"})

	return {
		"title": "Cliche",
		"hint": "Une photo prise sur le vif. Se pose comme les autres.",
		"props": props_from(candidates, anchor),
		# The sky of a shot is scenery three times past what the film reached,
		# so it never stands in the way of what the shot puts back. The carve
		# stops at CAPTURE_DEPTH, sealed by the copy itself.
		"backdrop": {"depth": 36.0, "top": "sky_top", "bottom": "sky_horizon"},
		"erase_depth": CAPTURE_DEPTH,
	}
