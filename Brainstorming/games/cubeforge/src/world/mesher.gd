class_name Mesher
## Chunk mesher: hidden face removal, per vertex ambient occlusion and sky light.
##
## Runs inside a worker thread, so it never touches the scene API: everything is
## plain arithmetic over a padded copy of the chunk plus its eight horizontal
## neighbours. The one cell padding ring supplies the edge and diagonal samples
## that ambient occlusion needs, which removes every bounds test from the hot
## loop and keeps the sky light estimate identical on both sides of a chunk
## border.
##
## Winding: for every face the four corners are derived from an orthonormal
## triple (u, v, n) with u cross v == n, laid out in the loop
## (-u -v, +u -v, +u +v, -u +v). Seen from outside the block that loop runs
## counter clockwise, so corner 0 is the bottom left of the tile and corner 2 the
## top right, which is what the UV and ambient occlusion tables assume.
##
## Godot itself declares the opposite triangle order as front facing (its own
## BoxMesh emits triangles whose consecutive edge cross product points along
## -normal), so the index buffer walks the corner loop backwards: 0, 2, 1 and
## 0, 3, 2. That is what keeps the outside of the block visible under
## `render_mode cull_back`.

# ---------------------------------------------------------------------------
# Padded volume
# ---------------------------------------------------------------------------

const PAD := 1
const PW := ChunkData.SIZE_X + 2      ## 18
const PH := ChunkData.SIZE_Y + 2      ## 98
const PD := ChunkData.SIZE_Z + 2      ## 18
const PVOLUME := PW * PH * PD         ## 31752
const PSTRIDE_Y := 1
const PSTRIDE_Z := PH
const PSTRIDE_X := PH * PD

# ---------------------------------------------------------------------------
# Tuning
# ---------------------------------------------------------------------------

## Sky light attenuation per opaque block standing above the sampled cell.
const SKY_FALLOFF := 0.80
## Weight applied to the eight side columns of the sky light estimate.
const SKY_SIDE_WEIGHT := 0.72
## Floor of the sky light range, so caves never go fully black.
const SKY_AMBIENT := 0.10
const SKY_RANGE := 0.90

## Height of a liquid top face when the cell above holds no liquid.
const LIQUID_TOP := 0.88

## Diagonal quads of a cross block are inset by this much on X and Z.
const CROSS_INSET := 0.146
## Maximum deterministic offset of a cross block on X and Z.
const CROSS_JITTER := 0.18

## Wind sway factor written to CUSTOM0.y for leaf cubes.
const LEAF_WAVE := 0.35

## Ambient occlusion multiplier per occlusion level (0 = darkest corner).
const AO_LEVELS: PackedFloat32Array = [0.52, 0.70, 0.86, 1.0]

## Directional face shading, indexed by Blocks.FACE_*.
const FACE_SHADE: PackedFloat32Array = [0.86, 0.78, 1.0, 0.55, 0.72, 0.66]

const FACE_NORMALS: PackedVector3Array = [
	Vector3(1.0, 0.0, 0.0),
	Vector3(-1.0, 0.0, 0.0),
	Vector3(0.0, 1.0, 0.0),
	Vector3(0.0, -1.0, 0.0),
	Vector3(0.0, 0.0, 1.0),
	Vector3(0.0, 0.0, -1.0),
]

## Four corners per face in cell local space, in the winding order documented at
## the top of the file. Values are 0 or 1 on every axis.
const FACE_CORNERS: PackedVector3Array = [
	# +X : u = -Z, v = +Y
	Vector3(1.0, 0.0, 1.0), Vector3(1.0, 0.0, 0.0), Vector3(1.0, 1.0, 0.0), Vector3(1.0, 1.0, 1.0),
	# -X : u = +Z, v = +Y
	Vector3(0.0, 0.0, 0.0), Vector3(0.0, 0.0, 1.0), Vector3(0.0, 1.0, 1.0), Vector3(0.0, 1.0, 0.0),
	# +Y : u = +X, v = -Z
	Vector3(0.0, 1.0, 1.0), Vector3(1.0, 1.0, 1.0), Vector3(1.0, 1.0, 0.0), Vector3(0.0, 1.0, 0.0),
	# -Y : u = +X, v = +Z
	Vector3(0.0, 0.0, 0.0), Vector3(1.0, 0.0, 0.0), Vector3(1.0, 0.0, 1.0), Vector3(0.0, 0.0, 1.0),
	# +Z : u = +X, v = +Y
	Vector3(0.0, 0.0, 1.0), Vector3(1.0, 0.0, 1.0), Vector3(1.0, 1.0, 1.0), Vector3(0.0, 1.0, 1.0),
	# -Z : u = -X, v = +Y
	Vector3(1.0, 0.0, 0.0), Vector3(0.0, 0.0, 0.0), Vector3(0.0, 1.0, 0.0), Vector3(1.0, 1.0, 0.0),
]

## Padded index step towards the cell a face looks into.
const FACE_NDELTA: PackedInt32Array = [
	PSTRIDE_X, -PSTRIDE_X, PSTRIDE_Y, -PSTRIDE_Y, PSTRIDE_Z, -PSTRIDE_Z,
]
## Padded index step along the face tangent u.
const FACE_UDELTA: PackedInt32Array = [
	-PSTRIDE_Z, PSTRIDE_Z, PSTRIDE_X, PSTRIDE_X, PSTRIDE_X, -PSTRIDE_X,
]
## Padded index step along the face bitangent v.
const FACE_VDELTA: PackedInt32Array = [
	PSTRIDE_Y, PSTRIDE_Y, -PSTRIDE_Z, PSTRIDE_Z, PSTRIDE_Y, PSTRIDE_Y,
]
## Cell coordinate steps matching FACE_NDELTA, used for the sky light lookup.
const FACE_DX: PackedInt32Array = [1, -1, 0, 0, 0, 0]
const FACE_DY: PackedInt32Array = [0, 0, 1, -1, 0, 0]
const FACE_DZ: PackedInt32Array = [0, 0, 0, 0, 1, -1]

# ---------------------------------------------------------------------------
# Hoisted block tables
# ---------------------------------------------------------------------------
#
# The inner loop must never call into Blocks: every property it needs lives in a
# flat Packed array indexed by block id, plus a full id by id face visibility
# matrix. Built once, on first use, behind a mutex because several worker
# threads may enter build_mesh_data at the same time.

static var _tables_mutex := Mutex.new()
static var _lut_opaque := PackedByteArray()
static var _lut_kind := PackedByteArray()
static var _lut_surface := PackedByteArray()
static var _lut_tile := PackedInt32Array()
static var _lut_tint := PackedInt32Array()
static var _lut_emission := PackedFloat32Array()
static var _lut_wave := PackedFloat32Array()
static var _lut_smooth := PackedByteArray()
static var _lut_draws := PackedByteArray()
static var _pow_falloff := PackedFloat32Array()


## Per surface vertex accumulator. Packed arrays are copy on write values, so
## they can only be appended to in place through the member slots of a class
## instance; that is the whole reason this helper exists.
class SurfaceBuffer extends RefCounted:
	const UV_A := Vector2(0.0, 1.0)
	const UV_B := Vector2(1.0, 1.0)
	const UV_C := Vector2(1.0, 0.0)
	const UV_D := Vector2(0.0, 0.0)

	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var uvs := PackedVector2Array()
	var cols := PackedColorArray()
	var custom := PackedFloat32Array()
	var tris := PackedInt32Array()

	## Appends one quad. `wave_low` applies to the first two corners and
	## `wave_high` to the last two, which is what makes a cross block sway from
	## its top only. `flip` cuts the quad along the other diagonal.
	func quad(
			p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3,
			normal: Vector3,
			c0: Color, c1: Color, c2: Color, c3: Color,
			layer: float, wave_low: float, wave_high: float, flip: bool,
			smooth0: float = 0.0, smooth1: float = 0.0,
			smooth2: float = 0.0, smooth3: float = 0.0) -> void:
		var base := verts.size()

		verts.push_back(p0)
		verts.push_back(p1)
		verts.push_back(p2)
		verts.push_back(p3)

		norms.push_back(normal)
		norms.push_back(normal)
		norms.push_back(normal)
		norms.push_back(normal)

		uvs.push_back(UV_A)
		uvs.push_back(UV_B)
		uvs.push_back(UV_C)
		uvs.push_back(UV_D)

		cols.push_back(c0)
		cols.push_back(c1)
		cols.push_back(c2)
		cols.push_back(c3)

		custom.push_back(layer)
		custom.push_back(wave_low)
		custom.push_back(smooth0)
		custom.push_back(0.0)
		custom.push_back(layer)
		custom.push_back(wave_low)
		custom.push_back(smooth1)
		custom.push_back(0.0)
		custom.push_back(layer)
		custom.push_back(wave_high)
		custom.push_back(smooth2)
		custom.push_back(0.0)
		custom.push_back(layer)
		custom.push_back(wave_high)
		custom.push_back(smooth3)
		custom.push_back(0.0)

		# Corner loop order reversed, see the winding note at the top of the file.
		if flip:
			tris.push_back(base)
			tris.push_back(base + 3)
			tris.push_back(base + 1)
			tris.push_back(base + 1)
			tris.push_back(base + 3)
			tris.push_back(base + 2)
		else:
			tris.push_back(base)
			tris.push_back(base + 2)
			tris.push_back(base + 1)
			tris.push_back(base)
			tris.push_back(base + 3)
			tris.push_back(base + 2)

	func is_empty() -> bool:
		return verts.is_empty()

	## Mesh.ARRAY_MAX sized array ready for add_surface_from_arrays.
	func to_arrays() -> Array:
		var out := []
		out.resize(Mesh.ARRAY_MAX)
		out[Mesh.ARRAY_VERTEX] = verts
		out[Mesh.ARRAY_NORMAL] = norms
		out[Mesh.ARRAY_TEX_UV] = uvs
		out[Mesh.ARRAY_COLOR] = cols
		out[Mesh.ARRAY_CUSTOM0] = custom
		out[Mesh.ARRAY_INDEX] = tris
		return out


# ---------------------------------------------------------------------------
# Padded volume assembly
# ---------------------------------------------------------------------------

## px = x + 1, py = y + 1, pz = z + 1
static func padded_index(px: int, py: int, pz: int) -> int:
	return (px * PD + pz) * PH + py


## Builds the 18 x 98 x 18 padded block volume around one chunk.
##
## `neighbours` holds exactly 9 entries, index (dx + 1) * 3 + (dz + 1) with dx
## and dz in -1..1; entry 4 is the central chunk and a null entry counts as pure
## air. py 0 and py PH - 1 always stay air because nothing exists below bedrock
## or above the sky.
static func build_padded(neighbours: Array) -> PackedByteArray:
	var air_column := PackedByteArray()
	air_column.resize(PH)

	if neighbours.size() != 9:
		push_error("Mesher.build_padded: expected 9 neighbours, got %d" % neighbours.size())
		var empty := PackedByteArray()
		empty.resize(PVOLUME)
		return empty

	# The padded layout stores py contiguous, then pz, then px, so the volume can
	# be assembled column by column with plain appends and no per cell loop.
	var out := PackedByteArray()
	for px in PW:
		var dx := 0
		var sx := px - 1
		if px == 0:
			dx = -1
			sx = ChunkData.SIZE_X - 1
		elif px == PW - 1:
			dx = 1
			sx = 0
		var row := (dx + 1) * 3
		for pz in PD:
			var dz := 0
			var sz := pz - 1
			if pz == 0:
				dz = -1
				sz = ChunkData.SIZE_Z - 1
			elif pz == PD - 1:
				dz = 1
				sz = 0
			var data: ChunkData = neighbours[row + dz + 1] as ChunkData
			if data == null:
				out.append_array(air_column)
				continue
			var base := (sx * ChunkData.SIZE_Z + sz) * ChunkData.SIZE_Y
			out.push_back(Blocks.AIR)
			out.append_array(data.voxels.slice(base, base + ChunkData.SIZE_Y))
			out.push_back(Blocks.AIR)
	return out


# ---------------------------------------------------------------------------
# Meshing
# ---------------------------------------------------------------------------

## Turns a padded volume into per surface vertex arrays.
##
## `tints` holds PW * PD entries, index px * PD + pz, the grass colour of the
## column. Returns:
##   {
##     "surfaces": Array,             # SURFACE_COUNT entries, null or ARRAY_MAX array
##     "lights": PackedVector3Array,  # local centres of the emissive blocks
##     "light_ids": PackedInt32Array, # block id of each light, same order
##   }
static func build_mesh_data(padded: PackedByteArray, tints: PackedColorArray) -> Dictionary:
	_ensure_tables()

	var surfaces: Array = []
	surfaces.resize(Blocks.SURFACE_COUNT)
	var lights := PackedVector3Array()
	var light_ids := PackedInt32Array()
	var result := {
		"surfaces": surfaces,
		"lights": lights,
		"light_ids": light_ids,
	}

	if padded.size() != PVOLUME:
		push_error("Mesher.build_mesh_data: padded volume holds %d bytes, expected %d"
				% [padded.size(), PVOLUME])
		return result

	var columns := PW * PD
	var has_tints := tints.size() == columns
	if not has_tints and tints.size() != 0:
		push_warning("Mesher.build_mesh_data: tints holds %d entries, expected %d"
				% [tints.size(), columns])
	var white := Color(1.0, 1.0, 1.0, 1.0)

	# One downward scan per padded column yields both the highest non air cell
	# (used to skip the empty sky) and the highest opaque cell (used by the sky
	# light estimate). Opaque implies non air, so a single pass finds both.
	var top_any := PackedInt32Array()
	top_any.resize(columns)
	var top_opaque := PackedInt32Array()
	top_opaque.resize(columns)
	var any_content := false
	for px in PW:
		var xbase := px * PSTRIDE_X
		for pz in PD:
			var cbase := xbase + pz * PSTRIDE_Z
			var t_any := -1
			var t_opaque := -1
			var py := PH - 1
			while py >= 0:
				var bid: int = padded[cbase + py]
				if bid != Blocks.AIR:
					if t_any < 0:
						t_any = py
					if _lut_opaque[bid] == 1:
						t_opaque = py
						break
				py -= 1
			var col := px * PD + pz
			top_any[col] = t_any
			top_opaque[col] = t_opaque
			if t_any >= 0:
				any_content = true

	if not any_content:
		return result

	# Sky light needs, per column, the highest opaque cell of the column itself
	# and the lowest of the eight surrounding columns. pow(0.80, d) decreases
	# with d, so the maximum over the eight side columns is reached at their
	# minimum height, which collapses the nine sample formula into two lookups.
	var side_min := PackedInt32Array()
	side_min.resize(columns)
	for px in PW:
		for pz in PD:
			var lowest := PH
			for i in 3:
				var qx := clampi(px + i - 1, 0, PW - 1)
				for j in 3:
					if i == 1 and j == 1:
						continue
					var qz := clampi(pz + j - 1, 0, PD - 1)
					var v: int = top_opaque[qx * PD + qz]
					if v < lowest:
						lowest = v
			side_min[px * PD + pz] = lowest

	var buffers: Array = []
	for s in Blocks.SURFACE_COUNT:
		buffers.append(SurfaceBuffer.new())

	var block_count := Blocks.COUNT
	var faces := Blocks.FACE_COUNT
	var liquid_kind := int(Blocks.Kind.LIQUID)
	var cross_kind := int(Blocks.Kind.CROSS)

	for px in range(1, PW - 1):
		var x := px - 1
		var fx := float(x)
		var xbase := px * PSTRIDE_X
		for pz in range(1, PD - 1):
			var col := px * PD + pz
			var column_max: int = top_any[col]
			if column_max < 1:
				continue
			var z := pz - 1
			var fz := float(z)
			var cbase := xbase + pz * PSTRIDE_Z
			var tint: Color = tints[col] if has_tints else white
			var highest: int = mini(column_max, PH - 2)
			for py in range(1, highest + 1):
				var idx := cbase + py
				var id: int = padded[idx]
				if id == Blocks.AIR:
					continue
				if id >= block_count:
					continue
				var y := py - 1
				var emission: float = _lut_emission[id]
				if emission > 0.01:
					lights.push_back(Vector3(fx + 0.5, float(y) + 0.5, fz + 0.5))
					light_ids.push_back(id)

				var kind: int = _lut_kind[id]
				var buffer: SurfaceBuffer = buffers[_lut_surface[id]]

				if kind == cross_kind:
					var plant_light := _sky_light(top_opaque, side_min, col, py)
					_emit_cross(buffer, id, x, y, z, px, py, pz, plant_light, tint)
					continue

				var fy := float(y)
				var draw_row := id * block_count
				var tile_row := id * faces
				var tint_mask: int = _lut_tint[id]
				var wave: float = _lut_wave[id]
				var top_h := 1.0
				if kind == liquid_kind and _lut_kind[padded[idx + PSTRIDE_Y]] != liquid_kind:
					top_h = LIQUID_TOP

				for face in faces:
					var nidx: int = idx + FACE_NDELTA[face]
					if _lut_draws[draw_row + padded[nidx]] == 0:
						continue

					var light := _sky_light(top_opaque, side_min,
							(px + FACE_DX[face]) * PD + pz + FACE_DZ[face], py + FACE_DY[face])
					var lit: float = FACE_SHADE[face] * light
					var cr := lit
					var cg := lit
					var cb := lit
					if (tint_mask & (1 << face)) != 0:
						cr = lit * tint.r
						cg = lit * tint.g
						cb = lit * tint.b

					# Three samples per corner: the two edge neighbours and the
					# diagonal, all taken inside the cell the face looks into.
					var ud: int = FACE_UDELTA[face]
					var vd: int = FACE_VDELTA[face]
					var su0: int = _lut_opaque[padded[nidx - ud]]
					var su1: int = _lut_opaque[padded[nidx + ud]]
					var sv0: int = _lut_opaque[padded[nidx - vd]]
					var sv1: int = _lut_opaque[padded[nidx + vd]]
					# level = 0 when both edge neighbours are opaque, else
					# 3 - (s1 + s2 + c). The right hand factor encodes the first
					# rule without a branch.
					var a0: float = AO_LEVELS[
							(3 - su0 - sv0 - _lut_opaque[padded[nidx - ud - vd]])
							* (1 - su0 * sv0)]
					var a1: float = AO_LEVELS[
							(3 - su1 - sv0 - _lut_opaque[padded[nidx + ud - vd]])
							* (1 - su1 * sv0)]
					var a2: float = AO_LEVELS[
							(3 - su1 - sv1 - _lut_opaque[padded[nidx + ud + vd]])
							* (1 - su1 * sv1)]
					var a3: float = AO_LEVELS[
							(3 - su0 - sv1 - _lut_opaque[padded[nidx - ud + vd]])
							* (1 - su0 * sv1)]

					var corner := face * 4
					var o0: Vector3 = FACE_CORNERS[corner]
					var o1: Vector3 = FACE_CORNERS[corner + 1]
					var o2: Vector3 = FACE_CORNERS[corner + 2]
					var o3: Vector3 = FACE_CORNERS[corner + 3]
					var smooth0 := 0.0
					var smooth1 := 0.0
					var smooth2 := 0.0
					var smooth3 := 0.0
					# Natural top blocks carry an optional Realistic-mode corner
					# displacement in CUSTOM0.z. The same grid corner calculation is
					# used by both chunks at a border, so no seam can open.
					var smooth_surface := _lut_smooth[id] == 1 and py == top_opaque[col] \
							and top_h >= 0.999
					if smooth_surface:
						if face == Blocks.FACE_PY:
							smooth0 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o0)
							smooth1 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o1)
							smooth2 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o2)
							smooth3 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o3)
						elif face in [Blocks.FACE_PX, Blocks.FACE_NX, Blocks.FACE_PZ, Blocks.FACE_NZ]:
							if o0.y > 0.5:
								smooth0 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o0)
							if o1.y > 0.5:
								smooth1 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o1)
							if o2.y > 0.5:
								smooth2 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o2)
							if o3.y > 0.5:
								smooth3 = _smooth_corner_delta(padded, top_opaque, px, pz, py, o3)

					buffer.quad(
							Vector3(fx + o0.x, fy + (top_h if o0.y > 0.5 else 0.0), fz + o0.z),
							Vector3(fx + o1.x, fy + (top_h if o1.y > 0.5 else 0.0), fz + o1.z),
							Vector3(fx + o2.x, fy + (top_h if o2.y > 0.5 else 0.0), fz + o2.z),
							Vector3(fx + o3.x, fy + (top_h if o3.y > 0.5 else 0.0), fz + o3.z),
							FACE_NORMALS[face],
							Color(cr * a0, cg * a0, cb * a0, emission),
							Color(cr * a1, cg * a1, cb * a1, emission),
							Color(cr * a2, cg * a2, cb * a2, emission),
							Color(cr * a3, cg * a3, cb * a3, emission),
							float(_lut_tile[tile_row + face]), wave, wave,
							(a0 + a2) > (a1 + a3), smooth0, smooth1, smooth2, smooth3)

	for s in Blocks.SURFACE_COUNT:
		var buffer: SurfaceBuffer = buffers[s]
		if buffer.is_empty():
			continue
		surfaces[s] = buffer.to_arrays()

	result["lights"] = lights
	result["light_ids"] = light_ids
	return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

## Sky light of one cell of the padded volume, seam free because it reads only
## the padded column heights:
##   e = max over the 9 columns of pow(0.80, max(0, ptop - py)) * side weight
##   light = 0.10 + 0.90 * clamp(e, 0, 1)
static func _sky_light(top_opaque: PackedInt32Array, side_min: PackedInt32Array,
		col: int, py: int) -> float:
	var d_centre: int = top_opaque[col] - py
	if d_centre < 0:
		d_centre = 0
	var d_side: int = side_min[col] - py
	if d_side < 0:
		d_side = 0
	var e: float = _pow_falloff[d_centre]
	var side: float = SKY_SIDE_WEIGHT * _pow_falloff[d_side]
	if side > e:
		e = side
	if e > 1.0:
		e = 1.0
	elif e < 0.0:
		e = 0.0
	return SKY_AMBIENT + SKY_RANGE * e


## Average of the natural surface columns sharing one grid corner. Non-terrain
## tops (trees, houses, fences) contribute the current height, keeping authored
## structures perfectly square. The clamp limits smoothing to a gentle bevel;
## collision remains the conservative full voxel underneath.
static func _smooth_corner_delta(padded: PackedByteArray, top_opaque: PackedInt32Array,
		px: int, pz: int, py: int, corner: Vector3) -> float:
	var x0 := px - 1 if corner.x < 0.5 else px
	var z0 := pz - 1 if corner.z < 0.5 else pz
	var total := 0.0
	for qx in [x0, x0 + 1]:
		for qz in [z0, z0 + 1]:
			var top: int = top_opaque[qx * PD + qz]
			if top < 1:
				total += float(py)
				continue
			var top_id: int = padded[padded_index(qx, top, qz)]
			total += float(top) if _lut_smooth[top_id] == 1 else float(py)
	var target := total * 0.25
	return clampf(target - float(py), -0.42, 0.42)


## Two diagonal quads for a plant. Both are emitted with a single winding: the
## cutout material runs `cull_disabled`, so each quad already shows both sides.
static func _emit_cross(buffer: SurfaceBuffer, id: int, x: int, y: int, z: int,
		px: int, py: int, pz: int, light: float, tint: Color) -> void:
	var h := _hash3(px, py, pz)
	var jx := (float(h & 255) / 255.0 - 0.5) * (CROSS_JITTER * 2.0)
	var jz := (float((h >> 8) & 255) / 255.0 - 0.5) * (CROSS_JITTER * 2.0)

	var x0 := float(x) + CROSS_INSET + jx
	var x1 := float(x) + 1.0 - CROSS_INSET + jx
	var z0 := float(z) + CROSS_INSET + jz
	var z1 := float(z) + 1.0 - CROSS_INSET + jz
	var y0 := float(y)
	var y1 := y0 + 1.0

	# Cross quads take the +Y face shading of 1.00 and no ambient occlusion.
	var cr := light
	var cg := light
	var cb := light
	if _lut_tint[id] != 0:
		cr = light * tint.r
		cg = light * tint.g
		cb = light * tint.b
	var col := Color(cr, cg, cb, _lut_emission[id])
	var layer := float(_lut_tile[id * Blocks.FACE_COUNT + Blocks.FACE_PX])
	var up := Vector3(0.0, 1.0, 0.0)

	buffer.quad(
			Vector3(x0, y0, z0), Vector3(x1, y0, z1), Vector3(x1, y1, z1), Vector3(x0, y1, z0),
			up, col, col, col, col, layer, 0.0, 1.0, false)
	buffer.quad(
			Vector3(x1, y0, z0), Vector3(x0, y0, z1), Vector3(x0, y1, z1), Vector3(x1, y1, z0),
			up, col, col, col, col, layer, 0.0, 1.0, false)


## Deterministic non negative hash, used to scatter cross blocks.
static func _hash3(a: int, b: int, c: int) -> int:
	var h: int = a * 374761393 + b * 668265263 + c * 1274126177
	h = h & 0x7fffffff
	h = (h ^ (h >> 13)) * 1274126177
	h = h & 0x7fffffff
	return h ^ (h >> 16)


static func _ensure_tables() -> void:
	_tables_mutex.lock()
	if _lut_draws.is_empty():
		_build_tables()
	_tables_mutex.unlock()


static func _build_tables() -> void:
	var count := Blocks.COUNT
	var faces := Blocks.FACE_COUNT

	var opaque := PackedByteArray()
	opaque.resize(count)
	var kind := PackedByteArray()
	kind.resize(count)
	var surface := PackedByteArray()
	surface.resize(count)
	var tile := PackedInt32Array()
	tile.resize(count * faces)
	var tint := PackedInt32Array()
	tint.resize(count)
	var emission := PackedFloat32Array()
	emission.resize(count)
	var wave := PackedFloat32Array()
	wave.resize(count)
	var smooth := PackedByteArray()
	smooth.resize(count)

	for id in count:
		opaque[id] = 1 if Blocks.is_opaque(id) else 0
		kind[id] = Blocks.kind_of(id)
		surface[id] = Blocks.surface_of(id)
		tint[id] = Blocks.tint_mask(id)
		emission[id] = Blocks.emission(id)
		for face in faces:
			tile[id * faces + face] = Blocks.tile_of(id, face)

	wave[Blocks.OAK_LEAVES] = LEAF_WAVE
	wave[Blocks.BIRCH_LEAVES] = LEAF_WAVE
	wave[Blocks.PINE_LEAVES] = LEAF_WAVE

	for id in [Blocks.STONE, Blocks.GRASS, Blocks.DIRT, Blocks.GRANITE, Blocks.MARBLE,
			Blocks.SAND, Blocks.SANDSTONE, Blocks.GRAVEL, Blocks.CLAY, Blocks.SNOW_BLOCK]:
		smooth[id] = 1

	var draws := PackedByteArray()
	draws.resize(count * count)
	for self_id in count:
		var row := self_id * count
		for other in count:
			draws[row + other] = 1 if Blocks.draws_face(self_id, other) else 0

	var falloff := PackedFloat32Array()
	falloff.resize(PH + 1)
	for d in PH + 1:
		falloff[d] = pow(SKY_FALLOFF, float(d))

	_lut_opaque = opaque
	_lut_kind = kind
	_lut_surface = surface
	_lut_tile = tile
	_lut_tint = tint
	_lut_emission = emission
	_lut_wave = wave
	_lut_smooth = smooth
	_pow_falloff = falloff
	# Assigned last: _ensure_tables uses it as the readiness flag.
	_lut_draws = draws
