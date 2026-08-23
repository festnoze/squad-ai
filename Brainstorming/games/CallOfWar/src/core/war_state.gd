## Autoload `War`: the global state of the campaign.
##
## Factions, sector control, run statistics, alert level. This node is pure
## data plus signals: it NEVER touches the scene tree, never looks a node up,
## never instantiates anything. That is what makes it safe to read from the
## HUD, the AI, the objective tracker and the save system at the same time.
##
## `Main` drives it with a single call to `tick(delta)` every frame.
extends Node

# Factions
const ALLIED := 0
const AXIS := 1
const NEUTRAL := 2

signal sector_captured(sector_id: int)
signal alert_changed(level: int)
signal stat_changed(key: String)
signal war_won()

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

## Total time played, in seconds. Plain field on purpose: it moves every single
## frame, so it must never emit a signal.
var play_seconds: float = 0.0

## Sector ids known to the campaign, in registration order, without duplicates.
var _sectors: PackedInt32Array = PackedInt32Array()
## Set of liberated sector ids: id -> true.
var _captured: Dictionary = {}
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
	_silent = false
	play_seconds = 0.0
	_captured.clear()
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


## Raises the alert to at least `level`, resets the decay timer, emits
## alert_changed when the value actually moves.
func raise_alert(level: int) -> void:
	_alert_timer = 0.0
	var wanted: int = clampi(level, ALERT_CALM, ALERT_FULL)
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
	return {
		"alert_level": alert_level,
		"kills": kills,
		"headshots": headshots,
		"shots_fired": shots_fired,
		"shots_hit": shots_hit,
		"deaths": deaths,
		"objectives_done": objectives_done,
		"play_seconds": play_seconds,
		"sectors": sector_ids,
		"captured": captured_ids,
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
