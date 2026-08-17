class_name ChunkData
extends RefCounted
## Voxel storage for one chunk column.
##
## A chunk is a 16 x 96 x 16 box of block ids. The whole world height fits in a
## single chunk so vertical streaming never happens: only the horizontal ring
## around the player moves.
##
## Index layout puts Y contiguous, which matters because almost every hot loop
## in the project walks columns (terrain fill, height scans, sky light).
##
##     index = (x * SIZE_Z + z) * SIZE_Y + y

const SIZE_X := 16
const SIZE_Y := 96
const SIZE_Z := 16
const VOLUME := SIZE_X * SIZE_Y * SIZE_Z

## Stride between two cells along each axis.
const STRIDE_Y := 1
const STRIDE_Z := SIZE_Y
const STRIDE_X := SIZE_Y * SIZE_Z

## Water fills every empty cell at or below this height during generation.
const SEA_LEVEL := 48

## Chunk coordinates. World position of the cell (0, 0, 0) is
## (cx * SIZE_X, 0, cz * SIZE_Z).
var cx: int
var cz: int

var voxels: PackedByteArray

## Count of non-air cells. Zero means the chunk needs no mesh at all.
var solid_count: int = 0

## Set when the player edits the chunk, cleared once it has been written to disk.
var modified: bool = false

## Highest non-air cell per column, -1 when the column is empty. Sized
## SIZE_X * SIZE_Z, indexed x * SIZE_Z + z. Maintained by fill helpers and
## set_local; recompute_tops() rebuilds it from scratch.
var column_top: PackedInt32Array


func _init(chunk_x: int = 0, chunk_z: int = 0) -> void:
	cx = chunk_x
	cz = chunk_z
	voxels = PackedByteArray()
	voxels.resize(VOLUME)
	column_top = PackedInt32Array()
	column_top.resize(SIZE_X * SIZE_Z)
	column_top.fill(-1)


static func local_index(x: int, y: int, z: int) -> int:
	return (x * SIZE_Z + z) * SIZE_Y + y


static func in_bounds(x: int, y: int, z: int) -> bool:
	return x >= 0 and x < SIZE_X and y >= 0 and y < SIZE_Y and z >= 0 and z < SIZE_Z


## Reads a cell in chunk-local coordinates. Out of range returns AIR, which lets
## callers probe freely without guarding every access.
func get_local(x: int, y: int, z: int) -> int:
	if x < 0 or x >= SIZE_X or y < 0 or y >= SIZE_Y or z < 0 or z >= SIZE_Z:
		return Blocks.AIR
	return voxels[(x * SIZE_Z + z) * SIZE_Y + y]


## Writes a cell in chunk-local coordinates and keeps solid_count and
## column_top in step. Returns false when the coordinates are out of range.
func set_local(x: int, y: int, z: int, id: int) -> bool:
	if x < 0 or x >= SIZE_X or y < 0 or y >= SIZE_Y or z < 0 or z >= SIZE_Z:
		return false
	var idx := (x * SIZE_Z + z) * SIZE_Y + y
	var old: int = voxels[idx]
	if old == id:
		return true
	voxels[idx] = id
	if old == Blocks.AIR:
		solid_count += 1
	elif id == Blocks.AIR:
		solid_count -= 1

	var col := x * SIZE_Z + z
	var top: int = column_top[col]
	if id != Blocks.AIR:
		if y > top:
			column_top[col] = y
	elif y == top:
		# The removed cell was the column peak, walk down to the next one.
		var scan := y - 1
		var base := col * SIZE_Y
		while scan >= 0 and voxels[base + scan] == Blocks.AIR:
			scan -= 1
		column_top[col] = scan
	return true


## Fast unchecked write used by the terrain generator, which already knows its
## coordinates are valid. Does not touch solid_count or column_top: call
## recompute_tops() once the chunk is fully generated.
func set_local_raw(x: int, y: int, z: int, id: int) -> void:
	voxels[(x * SIZE_Z + z) * SIZE_Y + y] = id


## Fills a vertical run [y_from, y_to] of one column. Both ends inclusive.
## Clamps to the chunk, so callers may pass out of range heights.
func fill_column(x: int, z: int, y_from: int, y_to: int, id: int) -> void:
	var lo: int = maxi(y_from, 0)
	var hi: int = mini(y_to, SIZE_Y - 1)
	if lo > hi:
		return
	var base := (x * SIZE_Z + z) * SIZE_Y
	for y in range(lo, hi + 1):
		voxels[base + y] = id


## Rebuilds solid_count and column_top from the voxel array.
func recompute_tops() -> void:
	var count := 0
	for x in SIZE_X:
		for z in SIZE_Z:
			var col := x * SIZE_Z + z
			var base := col * SIZE_Y
			var top := -1
			for y in SIZE_Y:
				if voxels[base + y] != Blocks.AIR:
					count += 1
					top = y
			column_top[col] = top
	solid_count = count


## Highest non-air cell of a column, -1 when empty. Out of range returns -1.
func top_of(x: int, z: int) -> int:
	if x < 0 or x >= SIZE_X or z < 0 or z >= SIZE_Z:
		return -1
	return column_top[x * SIZE_Z + z]


func is_empty() -> bool:
	return solid_count == 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

## Run length encoding of the voxel array. Runs are (id: u8, length: u16) pairs
## written little endian, which shrinks a typical chunk from 24 KB to a few
## hundred bytes because columns are long uniform stretches.
func serialize() -> PackedByteArray:
	var out := StreamPeerBuffer.new()
	out.big_endian = false
	var i := 0
	while i < VOLUME:
		var id: int = voxels[i]
		var run := 1
		while i + run < VOLUME and voxels[i + run] == id and run < 65535:
			run += 1
		out.put_u8(id)
		out.put_u16(run)
		i += run
	return out.data_array


## Rebuilds voxel contents from serialize() output. Returns false when the
## payload is malformed, leaving the chunk untouched.
func deserialize(payload: PackedByteArray) -> bool:
	if payload.size() % 3 != 0:
		return false
	var fresh := PackedByteArray()
	fresh.resize(VOLUME)
	var reader := StreamPeerBuffer.new()
	reader.big_endian = false
	reader.data_array = payload
	var cursor := 0
	while reader.get_available_bytes() >= 3:
		var id := reader.get_u8()
		var run := reader.get_u16()
		if run <= 0 or cursor + run > VOLUME:
			return false
		if id != Blocks.AIR:
			for k in run:
				fresh[cursor + k] = id
		cursor += run
	if cursor != VOLUME:
		return false
	voxels = fresh
	recompute_tops()
	return true
