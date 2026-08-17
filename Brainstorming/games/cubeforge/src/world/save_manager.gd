class_name SaveManager
extends RefCounted
## Chunk persistence for one world.
##
## Layout on disk:
##
##     user://saves/<world>/meta.json      world metadata (JSON)
##     user://saves/<world>/c_<cx>_<cz>.bin   ChunkData.serialize() payload
##
## Only chunks the player has edited are ever written: everything else is
## regenerated from the seed, which keeps a save at a few kilobytes.
##
## Threading: load_chunk() and has_chunk() are called from the worker threads
## while save_chunk() runs on the main thread, so the in memory index and every
## file access are guarded by a Mutex. The index is built once in _init() and
## kept in step by save_chunk() and delete_world(), so has_chunk() never touches
## the disk.

const SAVES_ROOT := "user://saves"
const CHUNK_PREFIX := "c_"
const CHUNK_SUFFIX := ".bin"
const META_FILE := "meta.json"
const TEMP_SUFFIX := ".tmp"

## Serialises the directory listing done by list_worlds(), which cannot reach
## the per instance mutex.
static var _listing_mutex := Mutex.new()

## Filesystem safe folder name of this world.
var _world_name: String = ""

## Absolute path of the world folder, trailing slash included.
var _dir: String = ""

## Set of chunk keys present on disk. Values are always true, only keys matter.
var _index: Dictionary = {}

var _mutex := Mutex.new()

## False when the folder could not be created: every operation then degrades to
## a no-op instead of spamming errors on each chunk.
var _usable: bool = false


func _init(world_name: String) -> void:
	_world_name = _sanitize_name(world_name)
	_dir = "%s/%s/" % [SAVES_ROOT, _world_name]
	_mutex.lock()
	_usable = _ensure_dir()
	if _usable:
		_build_index()
	_mutex.unlock()


# ---------------------------------------------------------------------------
# Worker thread side
# ---------------------------------------------------------------------------


## Payload of a saved chunk, empty when the chunk was never edited or when the
## file on disk turned out to be unusable.
func load_chunk(cx: int, cz: int) -> PackedByteArray:
	var empty := PackedByteArray()
	if not _usable:
		return empty
	var key := _key(cx, cz)
	_mutex.lock()
	if not _index.has(key):
		_mutex.unlock()
		return empty
	var path := _chunk_path(cx, cz)
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		# The index and the disk disagree: forget the entry so later calls skip it.
		_index.erase(key)
		_mutex.unlock()
		push_warning("SaveManager: cannot read %s" % path)
		return empty
	var payload := file.get_buffer(file.get_length())
	file.close()
	if payload.is_empty() or payload.size() % 3 != 0:
		_index.erase(key)
		_mutex.unlock()
		push_warning("SaveManager: discarding malformed chunk %s" % path)
		return empty
	_mutex.unlock()
	return payload


func has_chunk(cx: int, cz: int) -> bool:
	if not _usable:
		return false
	_mutex.lock()
	var found: bool = _index.has(_key(cx, cz))
	_mutex.unlock()
	return found


# ---------------------------------------------------------------------------
# Main thread side
# ---------------------------------------------------------------------------


## Writes one chunk payload. The write goes to a temporary file that is renamed
## over the target, so a crash in the middle cannot leave a truncated chunk that
## would later fail to deserialize.
func save_chunk(cx: int, cz: int, payload: PackedByteArray) -> void:
	if not _usable:
		return
	if payload.is_empty():
		push_warning("SaveManager: refusing to save an empty payload for chunk (%d, %d)" % [cx, cz])
		return
	var path := _chunk_path(cx, cz)
	var temp := path + TEMP_SUFFIX
	_mutex.lock()
	var file := FileAccess.open(temp, FileAccess.WRITE)
	if file == null:
		_mutex.unlock()
		push_error("SaveManager: cannot open %s for writing" % temp)
		return
	file.store_buffer(payload)
	file.close()
	if not _replace_file(temp, path):
		_mutex.unlock()
		return
	_index[_key(cx, cz)] = true
	_mutex.unlock()


func save_meta(data: Dictionary) -> void:
	if not _usable:
		return
	var path := _dir + META_FILE
	var temp := path + TEMP_SUFFIX
	var text := JSON.stringify(data, "\t")
	_mutex.lock()
	var file := FileAccess.open(temp, FileAccess.WRITE)
	if file == null:
		_mutex.unlock()
		push_error("SaveManager: cannot open %s for writing" % temp)
		return
	file.store_string(text)
	file.close()
	_replace_file(temp, path)
	_mutex.unlock()


## World metadata, empty when absent or unreadable.
func load_meta() -> Dictionary:
	var out: Dictionary = {}
	if not _usable:
		return out
	var path := _dir + META_FILE
	_mutex.lock()
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_mutex.unlock()
		return out
	var text := file.get_as_text()
	file.close()
	_mutex.unlock()
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary:
		out = parsed
	elif not text.strip_edges().is_empty():
		push_warning("SaveManager: %s is not a JSON object" % path)
	return out


## Erases every file of the world and the folder itself.
func delete_world() -> void:
	_mutex.lock()
	_index.clear()
	var dir := DirAccess.open(_dir)
	if dir == null:
		_usable = false
		_mutex.unlock()
		return
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if not dir.current_is_dir():
			var err := dir.remove(entry)
			if err != OK:
				push_warning("SaveManager: cannot delete %s%s" % [_dir, entry])
		entry = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(_dir.trim_suffix("/"))
	_usable = false
	_mutex.unlock()


## Names of every world folder found under user://saves, sorted alphabetically.
static func list_worlds() -> PackedStringArray:
	var out := PackedStringArray()
	_listing_mutex.lock()
	var dir := DirAccess.open(SAVES_ROOT)
	if dir != null:
		dir.list_dir_begin()
		var entry := dir.get_next()
		while entry != "":
			if dir.current_is_dir() and entry != "." and entry != "..":
				out.append(entry)
			entry = dir.get_next()
		dir.list_dir_end()
	_listing_mutex.unlock()
	out.sort()
	return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


## Keeps only characters that behave on every filesystem, so a world called
## "Mon monde / test" cannot escape its folder.
static func _sanitize_name(raw: String) -> String:
	var out := ""
	for i in raw.length():
		var c := raw[i]
		var code := c.unicode_at(0)
		var ok := (code >= 48 and code <= 57) \
				or (code >= 65 and code <= 90) \
				or (code >= 97 and code <= 122) \
				or c == "-" or c == "_"
		if ok:
			out += c
		elif c == " " or c == ".":
			out += "_"
	out = out.lstrip("_-").rstrip("_-. ")
	if out.length() > 48:
		out = out.substr(0, 48)
	if out.is_empty():
		out = "monde"
	return out


func _ensure_dir() -> bool:
	if DirAccess.dir_exists_absolute(_dir):
		return true
	var err := DirAccess.make_dir_recursive_absolute(_dir)
	if err != OK:
		push_error("SaveManager: cannot create %s (error %d)" % [_dir, err])
		return false
	return true


## Fills the in memory index by listing the folder once. Caller holds the mutex.
func _build_index() -> void:
	_index.clear()
	var dir := DirAccess.open(_dir)
	if dir == null:
		return
	dir.list_dir_begin()
	var entry := dir.get_next()
	while entry != "":
		if not dir.current_is_dir():
			if entry.ends_with(TEMP_SUFFIX):
				# Leftover of an interrupted write, worthless and possibly truncated.
				dir.remove(entry)
			elif entry.begins_with(CHUNK_PREFIX) and entry.ends_with(CHUNK_SUFFIX):
				var body := entry.substr(CHUNK_PREFIX.length(),
						entry.length() - CHUNK_PREFIX.length() - CHUNK_SUFFIX.length())
				var parts := body.split("_", false)
				if parts.size() == 2 and parts[0].is_valid_int() and parts[1].is_valid_int():
					_index["%d_%d" % [parts[0].to_int(), parts[1].to_int()]] = true
		entry = dir.get_next()
	dir.list_dir_end()


static func _key(cx: int, cz: int) -> String:
	return "%d_%d" % [cx, cz]


func _chunk_path(cx: int, cz: int) -> String:
	return "%s%s%d_%d%s" % [_dir, CHUNK_PREFIX, cx, cz, CHUNK_SUFFIX]


## Moves `temp` over `target`. Rename refuses an existing destination on Windows,
## so the old file goes first: a crash between the two steps loses the chunk but
## never leaves a half written one. Caller holds the mutex.
func _replace_file(temp: String, target: String) -> bool:
	if FileAccess.file_exists(target):
		var err := DirAccess.remove_absolute(target)
		if err != OK:
			push_error("SaveManager: cannot replace %s (error %d)" % [target, err])
			DirAccess.remove_absolute(temp)
			return false
	var moved := DirAccess.rename_absolute(temp, target)
	if moved != OK:
		push_error("SaveManager: cannot rename %s to %s (error %d)" % [temp, target, moved])
		DirAccess.remove_absolute(temp)
		return false
	return true
