class_name VoxelBody
extends RefCounted
## Axis aligned box collision against the voxel grid.
##
## The project runs with zero Godot physics: gravity is applied by the player
## script and no CollisionShape3D exists anywhere. This class is the single
## place where a character box meets the block grid, and it is pure maths on
## top of VoxelWorld reads, so it never touches the scene tree.
##
## The box origin sits at the feet. For a feet position `p` the box spans
## `(p.x - radius, p.y, p.z - radius)` to `(p.x + radius, p.y + height, p.z + radius)`.
##
## Resolution order is Y, then X, then Z. Each axis advances alone, the integer
## cells the box overlaps are enumerated, and on a collision the box is snapped
## flush against the offending cell face (plus a small separation margin) while
## that axis is dropped for the rest of the move.
##
## Rules for what blocks:
##   - a cell blocks when `Blocks.collides()` is true for its id;
##   - `y < 0` always blocks (below bedrock);
##   - `y >= VoxelWorld.WORLD_HEIGHT` never blocks (open sky);
##   - a column whose chunk is not loaded blocks, which is what keeps the
##     player from falling into the void at the edge of the loaded ring.

## Pushed out by this much after a snap so the body does not sit exactly on the
## boundary and re-collide on the very next frame.
const MARGIN := 0.001

## No single sub-step advances more than this on any axis. Below one block, so a
## fast fall cannot tunnel through a one block thick floor.
const MAX_STEP := 0.45

## Sentinels returned by _extreme_blocking() when nothing blocks. Far outside
## any reachable cell coordinate.
const _NONE_LOW := 1 << 40
const _NONE_HIGH := -(1 << 40)

const _AXIS_X := 0
const _AXIS_Y := 1
const _AXIS_Z := 2

var radius: float = 0.30
var height: float = 1.80


## Moves the box by `motion`, resolving collisions one axis at a time in the
## order Y, X, Z, split into sub-steps of at most MAX_STEP units.
##
## Returns:
##   {
##     "position": Vector3,   # final feet position
##     "hit_x": bool, "hit_y": bool, "hit_z": bool,
##     "on_floor": bool,      # blocked while going down
##     "on_ceiling": bool,    # blocked while going up
##   }
func move(world: VoxelWorld, feet: Vector3, motion: Vector3) -> Dictionary:
	var pos := feet
	var hit_x := false
	var hit_y := false
	var hit_z := false
	var on_floor := false
	var on_ceiling := false

	if world == null:
		push_error("VoxelBody.move called without a world")
		return _report(pos, false, false, false, false, false)

	if not _is_finite(motion):
		push_warning("VoxelBody.move received a non finite motion, ignored")
		return _report(pos, false, false, false, false, false)

	var longest := maxf(absf(motion.x), maxf(absf(motion.y), absf(motion.z)))
	var steps := 1
	if longest > MAX_STEP:
		steps = int(ceil(longest / MAX_STEP))
	if steps < 1:
		steps = 1

	# Remaining per sub-step delta. A blocked axis is zeroed so the following
	# sub-steps stop pushing against the wall we already snapped to.
	var step := motion / float(steps)

	for _sub in steps:
		if step.y != 0.0:
			var target := pos.y + step.y
			var lo := Vector3(pos.x - radius, target, pos.z - radius)
			var hi := Vector3(pos.x + radius, target + height, pos.z + radius)
			if step.y < 0.0:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_Y, true)
				if cell == _NONE_HIGH:
					pos.y = target
				else:
					# Snap the feet onto the top face of the highest blocker.
					# minf() guards the case where the body already started
					# embedded, which must never teleport it upward.
					pos.y = minf(pos.y, float(cell + 1) + MARGIN)
					step.y = 0.0
					hit_y = true
					on_floor = true
			else:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_Y, false)
				if cell == _NONE_LOW:
					pos.y = target
				else:
					# Snap the head under the bottom face of the lowest blocker.
					pos.y = maxf(pos.y, float(cell) - height - MARGIN)
					step.y = 0.0
					hit_y = true
					on_ceiling = true

		if step.x != 0.0:
			var target := pos.x + step.x
			var lo := Vector3(target - radius, pos.y, pos.z - radius)
			var hi := Vector3(target + radius, pos.y + height, pos.z + radius)
			if step.x > 0.0:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_X, false)
				if cell == _NONE_LOW:
					pos.x = target
				else:
					pos.x = maxf(pos.x, float(cell) - radius - MARGIN)
					step.x = 0.0
					hit_x = true
			else:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_X, true)
				if cell == _NONE_HIGH:
					pos.x = target
				else:
					pos.x = minf(pos.x, float(cell + 1) + radius + MARGIN)
					step.x = 0.0
					hit_x = true

		if step.z != 0.0:
			var target := pos.z + step.z
			var lo := Vector3(pos.x - radius, pos.y, target - radius)
			var hi := Vector3(pos.x + radius, pos.y + height, target + radius)
			if step.z > 0.0:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_Z, false)
				if cell == _NONE_LOW:
					pos.z = target
				else:
					pos.z = maxf(pos.z, float(cell) - radius - MARGIN)
					step.z = 0.0
					hit_z = true
			else:
				var cell := _extreme_blocking(world, lo, hi, _AXIS_Z, true)
				if cell == _NONE_HIGH:
					pos.z = target
				else:
					pos.z = minf(pos.z, float(cell + 1) + radius + MARGIN)
					step.z = 0.0
					hit_z = true

		if step.x == 0.0 and step.y == 0.0 and step.z == 0.0:
			break

	return _report(pos, hit_x, hit_y, hit_z, on_floor, on_ceiling)


## True when a colliding block overlaps the box at this feet position.
func overlaps_solid(world: VoxelWorld, feet: Vector3) -> bool:
	if world == null:
		return true
	var lo := Vector3(feet.x - radius, feet.y, feet.z - radius)
	var hi := Vector3(feet.x + radius, feet.y + height, feet.z + radius)
	return _extreme_blocking(world, lo, hi, _AXIS_Y, true) != _NONE_HIGH


## True when a liquid fills the cell holding the eyes (feet.y + eye_height).
func head_in_liquid(world: VoxelWorld, feet: Vector3, eye_height: float) -> bool:
	if world == null:
		return false
	var wy := floori(feet.y + eye_height)
	if wy < 0 or wy >= VoxelWorld.WORLD_HEIGHT:
		return false
	var wx := floori(feet.x)
	var wz := floori(feet.z)
	if not world.has_chunk_at(wx, wz):
		return false
	return Blocks.is_liquid(world.get_block(wx, wy, wz))


## Fraction of the box volume height covered by liquid, 0 to 1.
##
## Both the swim physics and the underwater overlay read this, so it has to vary
## smoothly: every overlapped cell contributes its own share of the box,
## weighted by how much of the box height it spans and by how much of the
## horizontal footprint it covers.
func submersion(world: VoxelWorld, feet: Vector3) -> float:
	if world == null or height <= 0.0 or radius <= 0.0:
		return 0.0

	var x_lo := feet.x - radius
	var x_hi := feet.x + radius
	var z_lo := feet.z - radius
	var z_hi := feet.z + radius
	var y_lo := feet.y
	var y_hi := feet.y + height

	var footprint := (x_hi - x_lo) * (z_hi - z_lo)
	if footprint <= 0.0:
		return 0.0

	var x0 := floori(x_lo)
	var x1 := ceili(x_hi) - 1
	var z0 := floori(z_lo)
	var z1 := ceili(z_hi) - 1
	var y0 := floori(y_lo)
	var y1 := ceili(y_hi) - 1

	var covered := 0.0
	for wy: int in range(y0, y1 + 1):
		if wy < 0 or wy >= VoxelWorld.WORLD_HEIGHT:
			continue
		var span := minf(y_hi, float(wy + 1)) - maxf(y_lo, float(wy))
		if span <= 0.0:
			continue
		var area := 0.0
		for wx: int in range(x0, x1 + 1):
			var ax := minf(x_hi, float(wx + 1)) - maxf(x_lo, float(wx))
			if ax <= 0.0:
				continue
			for wz: int in range(z0, z1 + 1):
				var az := minf(z_hi, float(wz + 1)) - maxf(z_lo, float(wz))
				if az <= 0.0:
					continue
				if not world.has_chunk_at(wx, wz):
					continue
				if Blocks.is_liquid(world.get_block(wx, wy, wz)):
					area += ax * az
		if area > 0.0:
			covered += span * (area / footprint)

	return clampf(covered / height, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _report(
	pos: Vector3,
	hit_x: bool,
	hit_y: bool,
	hit_z: bool,
	on_floor: bool,
	on_ceiling: bool
) -> Dictionary:
	return {
		"position": pos,
		"hit_x": hit_x,
		"hit_y": hit_y,
		"hit_z": hit_z,
		"on_floor": on_floor,
		"on_ceiling": on_ceiling,
	}


static func _is_finite(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)


## Walks the integer cells overlapped by the box spanning `lo` to `hi` and
## returns the extreme blocking cell coordinate along `axis`: the highest one
## when `want_max` is true, the lowest one otherwise. Returns _NONE_HIGH
## (want_max) or _NONE_LOW when nothing blocks.
##
## The low bound of a cell range uses floor() and the high bound ceil() - 1, so
## a box lying exactly flush against a cell boundary does not claim the cell on
## the far side of that boundary.
func _extreme_blocking(
	world: VoxelWorld,
	lo: Vector3,
	hi: Vector3,
	axis: int,
	want_max: bool
) -> int:
	var x0 := floori(lo.x)
	var x1 := ceili(hi.x) - 1
	var y0 := floori(lo.y)
	var y1 := ceili(hi.y) - 1
	var z0 := floori(lo.z)
	var z1 := ceili(hi.z) - 1
	if x1 < x0 or y1 < y0 or z1 < z0:
		return _NONE_HIGH if want_max else _NONE_LOW

	# Everything at or above the world roof is open sky, nothing below zero is.
	var scan_lo := maxi(y0, -1)
	var scan_hi := mini(y1, VoxelWorld.WORLD_HEIGHT - 1)

	var best: int = _NONE_HIGH if want_max else _NONE_LOW
	for wx: int in range(x0, x1 + 1):
		for wz: int in range(z0, z1 + 1):
			var missing: bool = not world.has_chunk_at(wx, wz)
			for wy: int in range(scan_lo, scan_hi + 1):
				if wy < 0:
					pass  # Below bedrock, always solid.
				elif missing:
					pass  # Unloaded chunk, treated as solid.
				elif not Blocks.collides(world.get_block(wx, wy, wz)):
					continue
				var c := wx
				if axis == _AXIS_Y:
					c = wy
				elif axis == _AXIS_Z:
					c = wz
				if want_max:
					if c > best:
						best = c
				elif c < best:
					best = c
	return best
