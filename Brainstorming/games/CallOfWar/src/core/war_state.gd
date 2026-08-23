## Autoload `War`: the global state of the campaign.
##
## Factions, sector control, run statistics, alert level. This node is pure
## data plus signals: it NEVER touches the scene tree, never looks a node up,
## never instantiates anything. That is what makes it safe to read from the
## HUD, the AI, the objective tracker and the save system at the same time.
##
## `Main` drives it with a single call to `tick(delta)` every frame.
##
## Progress here is deliberately monotonic. Capture is one way: a sector that was
## liberated stays liberated for the rest of the campaign, whatever the Wehrmacht
## does about it afterwards. A counter attack is recorded as a SEPARATE
## "contested" flag laid next to the capture, never as a cancellation of it.
## Without that split, a lost counter attack would make `captured_count` go down
## and `war_won` become reachable a second time, which would let the endgame
## screen replay itself and would make the campaign feel like it can be lost by
## walking away. See `mark_contested`.
extends Node

# Factions
const ALLIED := 0
const AXIS := 1
const NEUTRAL := 2

signal sector_captured(sector_id: int)
signal alert_changed(level: int)
signal stat_changed(key: String)
signal war_won()
## Fired when a liberated sector falls back under Axis pressure. Only raised by
## `mark_contested`, never by `clear_contested`: the map redraws from
## `is_sector_contested` anyway, and a signal named "contested" that also means
## "no longer contested" would be a trap for every listener.
signal sector_contested(sector_id: int)

## Alert levels: 0 calme, 1 soupcon, 2 recherche, 3 alerte generale.
const ALERT_CALM := 0
const ALERT_SUSPICIOUS := 1
const ALERT_SEARCHING := 2
const ALERT_FULL := 3

## Quiet seconds needed before the alert drops by one step.
const _ALERT_DECAY_SECONDS := 45.0

## Statistic keys carried by `stat_changed`.
const _KEY_KILLS := "kills"
const _KEY_HEADSHOTS := "headshots"
const _KEY_SHOTS_FIRED := "shots_fired"
const _KEY_SHOTS_HIT := "shots_hit"
const _KEY_DEATHS := "deaths"
const _KEY_OBJECTIVES := "objectives_done"
const _KEY_SILENT_CAPTURES := "silent_captures"
const _KEY_INTEL := "intel_found"
## Emitted once after a bulk load instead of one signal per field.
const _KEY_ALL := "all"

var alert_level: int = ALERT_CALM:
	set(value):
		var v: int = clampi(value, ALERT_CALM, ALERT_FULL)
		if v == alert_level:
			return
		alert_level = v
		if not _silent:
			alert_changed.emit(alert_level)

var kills: int = 0:
	set(value):
		if value == kills:
			return
		kills = value
		_stat(_KEY_KILLS)

var headshots: int = 0:
	set(value):
		if value == headshots:
			return
		headshots = value
		_stat(_KEY_HEADSHOTS)

var shots_fired: int = 0:
	set(value):
		if value == shots_fired:
			return
		shots_fired = value
		_stat(_KEY_SHOTS_FIRED)

var shots_hit: int = 0:
	set(value):
		if value == shots_hit:
			return
		shots_hit = value
		_stat(_KEY_SHOTS_HIT)

var deaths: int = 0:
	set(value):
		if value == deaths:
			return
		deaths = value
		_stat(_KEY_DEATHS)

var objectives_done: int = 0:
	set(value):
		if value == objectives_done:
			return
		objectives_done = value
		_stat(_KEY_OBJECTIVES)

## Sectors taken without ever pushing the garrison past ALERT_SEARCHING.
var silent_captures: int = 0:
	set(value):
		if value == silent_captures:
			return
		silent_captures = value
		_stat(_KEY_SILENT_CAPTURES)

## Intelligence gathered: officer documents looted plus O_RECON objectives.
var intel_found: int = 0:
	set(value):
		if value == intel_found:
			return
		intel_found = value
		_stat(_KEY_INTEL)

## Total time played, in seconds. Plain field on purpose: it moves every single
## frame, so it must never emit a signal.
var play_seconds: float = 0.0

## Sector ids known to the campaign, in registration order, without duplicates.
var _sectors: PackedInt32Array = PackedInt32Array()
## Set of liberated sector ids: id -> true.
var _captured: Dictionary = {}
## Set of liberated sector ids currently back under Axis pressure: id -> true.
## Strictly a decoration over `_captured`, which it never modifies.
var _contested: Dictionary = {}
## Debrief ledger: sector id -> {"seconds": float, "silent": bool}.
var _sector_results: Dictionary = {}
## Highest alert reached since the last `reset_peak_alert`. Not the same thing as
## `alert_level`, which decays back down and would otherwise hand the player a
## silent capture just for waiting out the search.
var _peak_alert: int = ALERT_CALM
## Seconds elapsed since the last alert, drives the cooldown.
var _alert_timer: float = 0.0
## True once `war_won` has fired, so it fires exactly once per campaign.
var _won: bool = false
## Suppresses signals while a bulk load is running.
var _silent: bool = false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS


## Wipes everything back to a brand new campaign. The registered sector list is
## kept: the world layout has not changed, only the progress on it.
func reset_campaign() -> void:
	_silent = true
	alert_level = ALERT_CALM
	kills = 0
	headshots = 0
	shots_fired = 0
	shots_hit = 0
	deaths = 0
	objectives_done = 0
	silent_captures = 0
	intel_found = 0
	_silent = false
	play_seconds = 0.0
	_captured.clear()
	_contested.clear()
	_sector_results.clear()
	_peak_alert = ALERT_CALM
	_alert_timer = 0.0
	_won = false
	alert_changed.emit(alert_level)
	stat_changed.emit(_KEY_ALL)


## Marks a sector as liberated. Idempotent. Emits sector_captured, and war_won
## when every registered sector is allied.
func capture_sector(sector_id: int) -> void:
	if _captured.has(sector_id):
		return
	_captured[sector_id] = true
	sector_captured.emit(sector_id)
	if _won:
		return
	if _sectors.is_empty():
		return
	for id in _sectors:
		if not _captured.has(id):
			return
	_won = true
	war_won.emit()


func is_sector_captured(sector_id: int) -> bool:
	return _captured.has(sector_id)


func captured_count() -> int:
	return _captured.size()


## Declares the sectors of the current world. Merges with what is already
## known, so calling it twice with the same layout changes nothing.
func register_sectors(ids: PackedInt32Array) -> void:
	for id in ids:
		if not _sectors.has(id):
			_sectors.append(id)


func sector_count() -> int:
	return _sectors.size()


## A sector taken back under Axis pressure after a counter attack. This is a
## state SEPARATE from capture: `capture_sector` stays idempotent and a captured
## sector stays captured, so `war_won` can never replay backwards and no counter
## can ever go down. What the player loses is the sector's quiet, not the sector.
## Contesting an id that was never liberated is meaningless, so it is ignored.
func mark_contested(sector_id: int) -> void:
	if not _captured.has(sector_id):
		return
	if _contested.has(sector_id):
		return
	_contested[sector_id] = true
	sector_contested.emit(sector_id)


func clear_contested(sector_id: int) -> void:
	_contested.erase(sector_id)


func is_sector_contested(sector_id: int) -> bool:
	return _contested.has(sector_id)


## Sorted so the map and the save file stay stable between two runs with the
## same events, which makes save diffs and screenshots comparable.
func contested_ids() -> PackedInt32Array:
	var ids: Array = []
	for id in _contested.keys():
		ids.append(int(id))
	ids.sort()
	var out: PackedInt32Array = PackedInt32Array()
	for id in ids:
		out.append(int(id))
	return out


## Highest alert level reached since the last sector capture. This, and not the
## current level, is what decides whether a capture counts as silent.
func peak_alert() -> int:
	return _peak_alert


## Starts a fresh stealth window. It resets to the CURRENT alert level, not to
## zero: if the player captures while the whole valley is hunting him, the next
## sector must not inherit an artificially clean slate, and it must not inherit
## an artificially damning one either once things have calmed down on their own.
func reset_peak_alert() -> void:
	_peak_alert = alert_level


func record_silent_capture() -> void:
	silent_captures += 1


func record_intel() -> void:
	intel_found += 1


## Per sector debrief entry. Recorded once per capture; a sector retaken after a
## counter attack overwrites its entry, so the debrief shows how the sector was
## finally held rather than how it was first entered.
func record_sector_result(sector_id: int, seconds: float, silent: bool) -> void:
	_sector_results[sector_id] = {
		"seconds": maxf(0.0, seconds),
		"silent": silent,
	}


## Returns {} for a sector never taken. The copy is deliberate: the debrief
## screen must not be able to rewrite the campaign ledger by editing what it
## reads.
func sector_result(sector_id: int) -> Dictionary:
	if not _sector_results.has(sector_id):
		return {}
	var entry: Dictionary = _sector_results[sector_id] as Dictionary
	return entry.duplicate()


## Raises the alert to at least `level`, resets the decay timer, emits
## alert_changed when the value actually moves.
func raise_alert(level: int) -> void:
	_alert_timer = 0.0
	var wanted: int = clampi(level, ALERT_CALM, ALERT_FULL)
	# The peak is bookkept here rather than at the call sites. Every alarm in the
	# game funnels through this one function, so no caller can forget to update
	# it and hand the player a "silent" capture they did not earn. It is raised
	# even when `wanted` changes nothing, because a redundant alarm at level 3
	# still means the garrison saw us.
	_peak_alert = maxi(_peak_alert, maxi(wanted, alert_level))
	if wanted <= alert_level:
		return
	alert_level = wanted


## Called every frame by Main. Lets the alert cool down after ~45 s of quiet.
func tick(delta: float) -> void:
	if delta <= 0.0:
		return
	play_seconds += delta
	if alert_level <= ALERT_CALM:
		_alert_timer = 0.0
		return
	_alert_timer += delta
	if _alert_timer < _ALERT_DECAY_SECONDS:
		return
	_alert_timer = 0.0
	alert_level = alert_level - 1


func record_kill(headshot: bool) -> void:
	kills += 1
	if headshot:
		headshots += 1


func record_shot(hit: bool) -> void:
	shots_fired += 1
	if hit:
		shots_hit += 1


func accuracy() -> float:
	if shots_fired <= 0:
		return 0.0
	return clampf(float(shots_hit) / float(shots_fired), 0.0, 1.0)


func to_dict() -> Dictionary:
	var captured_ids: Array = []
	for id in _captured.keys():
		captured_ids.append(int(id))
	captured_ids.sort()
	var sector_ids: Array = []
	for id in _sectors:
		sector_ids.append(int(id))
	var contested_list: Array = []
	for id in contested_ids():
		contested_list.append(int(id))
	# Written as a list of records rather than as a dictionary keyed by sector
	# id: the save goes through JSON, which turns every dictionary key into a
	# string, and a ledger that changes shape on the way to disk is a bug waiting
	# for its first reload.
	var results: Array = []
	var result_ids: Array = []
	for id in _sector_results.keys():
		result_ids.append(int(id))
	result_ids.sort()
	for id in result_ids:
		var entry: Dictionary = _sector_results[id] as Dictionary
		results.append({
			"sector": int(id),
			"seconds": float(entry.get("seconds", 0.0)),
			"silent": bool(entry.get("silent", false)),
		})
	return {
		"alert_level": alert_level,
		"kills": kills,
		"headshots": headshots,
		"shots_fired": shots_fired,
		"shots_hit": shots_hit,
		"deaths": deaths,
		"objectives_done": objectives_done,
		"silent_captures": silent_captures,
		"intel_found": intel_found,
		"play_seconds": play_seconds,
		"sectors": sector_ids,
		"captured": captured_ids,
		"contested": contested_list,
		"sector_results": results,
		"peak_alert": _peak_alert,
		"won": _won,
	}


func from_dict(data: Dictionary) -> void:
	_silent = true
	alert_level = _pick_int(data, "alert_level", ALERT_CALM)
	kills = _pick_int(data, "kills", 0)
	headshots = _pick_int(data, "headshots", 0)
	shots_fired = _pick_int(data, "shots_fired", 0)
	shots_hit = _pick_int(data, "shots_hit", 0)
	deaths = _pick_int(data, "deaths", 0)
	objectives_done = _pick_int(data, "objectives_done", 0)
	# Absent in every v1 save. The fallback is the default, never an error: a v1
	# campaign simply had no silent captures and no intelligence to its name.
	silent_captures = maxi(0, _pick_int(data, "silent_captures", 0))
	intel_found = maxi(0, _pick_int(data, "intel_found", 0))
	_silent = false

	play_seconds = maxf(0.0, _pick_float(data, "play_seconds", 0.0))

	_sectors = PackedInt32Array()
	var raw_sectors: Array = _pick_array(data, "sectors")
	for value in raw_sectors:
		var id: int = int(value)
		if not _sectors.has(id):
			_sectors.append(id)

	_captured.clear()
	var raw_captured: Array = _pick_array(data, "captured")
	for value in raw_captured:
		_captured[int(value)] = true

	# Read after `_captured` on purpose, so the "contested implies captured"
	# invariant survives a hand edited or truncated save file.
	_contested.clear()
	var raw_contested: Array = _pick_array(data, "contested")
	for value in raw_contested:
		var contested_id: int = int(value)
		if _captured.has(contested_id):
			_contested[contested_id] = true

	_sector_results.clear()
	var raw_results: Array = _pick_array(data, "sector_results")
	for value in raw_results:
		if typeof(value) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = value as Dictionary
		if not entry.has("sector"):
			continue
		# JSON gives back floats where we wrote ints, and integers where we wrote
		# a whole float, so every field is converted rather than trusted.
		_sector_results[_pick_int(entry, "sector", 0)] = {
			"seconds": maxf(0.0, _pick_float(entry, "seconds", 0.0)),
			"silent": bool(entry.get("silent", false)),
		}

	# A v1 save has no peak, and its alert level is the only honest thing we know
	# about how loud the player was being. Never let the peak sit below the
	# current alert: that would describe an alarm that never happened.
	var saved_peak: int = _pick_int(data, "peak_alert", alert_level)
	_peak_alert = maxi(alert_level, clampi(saved_peak, ALERT_CALM, ALERT_FULL))

	_won = bool(data.get("won", false))
	_alert_timer = 0.0
	alert_changed.emit(alert_level)
	stat_changed.emit(_KEY_ALL)


func alert_name() -> String:
	match alert_level:
		ALERT_SUSPICIOUS:
			return "Soupcon"
		ALERT_SEARCHING:
			return "Recherche"
		ALERT_FULL:
			return "Alerte generale"
		_:
			return "Calme"


## Display name of a faction, in French, for the HUD and the map.
func faction_name(faction: int) -> String:
	match faction:
		AXIS:
			return "Wehrmacht"
		ALLIED:
			return "Allies"
		_:
			return "Civils"


# ------------------------------------------------------------------ helpers --

func _stat(key: String) -> void:
	if _silent:
		return
	stat_changed.emit(key)


func _pick_int(data: Dictionary, key: String, fallback: int) -> int:
	if not data.has(key):
		return fallback
	var value: Variant = data[key]
	var kind: int = typeof(value)
	if kind == TYPE_INT or kind == TYPE_FLOAT:
		return int(value)
	return fallback


func _pick_float(data: Dictionary, key: String, fallback: float) -> float:
	if not data.has(key):
		return fallback
	var value: Variant = data[key]
	var kind: int = typeof(value)
	if kind == TYPE_INT or kind == TYPE_FLOAT:
		return float(value)
	return fallback


func _pick_array(data: Dictionary, key: String) -> Array:
	if not data.has(key):
		return []
	var value: Variant = data[key]
	var kind: int = typeof(value)
	if kind == TYPE_ARRAY:
		return value as Array
	if kind == TYPE_PACKED_INT32_ARRAY or kind == TYPE_PACKED_INT64_ARRAY:
		var out: Array = []
		for item in value:
			out.append(int(item))
		return out
	return []
