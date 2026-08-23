## Campaign persistence: one JSON file per campaign in `user://saves`.
##
## Everything here is static and defensive. A save file is user writable data
## that can be missing, truncated, hand edited or written by an older build, so
## no failure path is ever allowed to crash the game: `read()` answers with an
## empty dictionary and `write()` answers with `false`.
class_name SaveManager
extends RefCounted

const SAVE_DIR := "user://saves"

## Extension of a campaign file, kept in one place.
const _EXT := ".json"
## Indentation of the written JSON. Saves stay readable for debugging.
const _INDENT := "  "
## Longest accepted campaign name, so a file name never explodes.
const _NAME_MAX := 40
## Fallback campaign name, matching `Game.campaign_name` default.
const _FALLBACK_NAME := "normandie"


static func save_path(campaign: String) -> String:
	return "%s/%s%s" % [SAVE_DIR, _sanitize(campaign), _EXT]


## Serialises `data` to the campaign file. Creates `user://saves` when it is
## missing. Returns false on any failure, after a warning.
static func write(campaign: String, data: Dictionary) -> bool:
	if not _ensure_dir():
		return false
	var path: String = save_path(campaign)
	var text: String = JSON.stringify(data, _INDENT, true, true)
	var file: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		push_warning("Sauvegarde impossible: %s (code %d)." % [path, FileAccess.get_open_error()])
		return false
	file.store_string(text)
	# Explicit close so the bytes are flushed before we answer true.
	file.close()
	return true


## Reads the campaign file back. Returns an empty dictionary when the file is
## absent, unreadable, or does not hold a JSON object.
static func read(campaign: String) -> Dictionary:
	var path: String = save_path(campaign)
	if not FileAccess.file_exists(path):
		return {}
	var file: FileAccess = FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_warning("Lecture de sauvegarde impossible: %s (code %d)." % [path, FileAccess.get_open_error()])
		return {}
	var text: String = file.get_as_text()
	file.close()
	if text.strip_edges().is_empty():
		return {}
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null or typeof(parsed) != TYPE_DICTIONARY:
		push_warning("Sauvegarde corrompue, ignoree: %s." % path)
		return {}
	return parsed as Dictionary


static func has_save(campaign: String) -> bool:
	return FileAccess.file_exists(save_path(campaign))


## Deletes the campaign file. Returns true only when a file was actually
## removed, false when there was nothing to remove or the removal failed.
static func erase(campaign: String) -> bool:
	var path: String = save_path(campaign)
	if not FileAccess.file_exists(path):
		return false
	var err: int = DirAccess.remove_absolute(path)
	if err != OK:
		push_warning("Suppression de sauvegarde impossible: %s (code %d)." % [path, err])
		return false
	return true


## Every campaign that has a file on disk, sorted alphabetically.
static func list_campaigns() -> PackedStringArray:
	var names: PackedStringArray = PackedStringArray()
	if not DirAccess.dir_exists_absolute(SAVE_DIR):
		return names
	var dir: DirAccess = DirAccess.open(SAVE_DIR)
	if dir == null:
		push_warning("Dossier de sauvegardes illisible: %s." % SAVE_DIR)
		return names
	for file_name in dir.get_files():
		var name_string: String = str(file_name)
		# Godot may hand back "<name>.json.remap" in an exported build.
		if name_string.ends_with(".remap"):
			name_string = name_string.trim_suffix(".remap")
		if not name_string.ends_with(_EXT):
			continue
		var campaign: String = name_string.trim_suffix(_EXT)
		if campaign.is_empty():
			continue
		if not names.has(campaign):
			names.append(campaign)
	names.sort()
	return names


# ------------------------------------------------------------------ helpers --

## Creates `user://saves` when needed. False when the folder cannot exist.
static func _ensure_dir() -> bool:
	if DirAccess.dir_exists_absolute(SAVE_DIR):
		return true
	var err: int = DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	if err != OK and not DirAccess.dir_exists_absolute(SAVE_DIR):
		push_warning("Creation du dossier de sauvegardes impossible (code %d)." % err)
		return false
	return true


## Campaign names become file names, so only lowercase letters, digits, dash
## and underscore survive. An empty result falls back to the default campaign.
static func _sanitize(campaign: String) -> String:
	var source: String = campaign.strip_edges().to_lower()
	var cleaned: String = ""
	for i in source.length():
		var c: String = source[i]
		if c == "_" or c == "-" or c.is_valid_identifier() or (c >= "0" and c <= "9"):
			cleaned += c
	if cleaned.is_empty():
		return _FALLBACK_NAME
	if cleaned.length() > _NAME_MAX:
		cleaned = cleaned.substr(0, _NAME_MAX)
	return cleaned
