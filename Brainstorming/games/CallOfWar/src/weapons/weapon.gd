## Runtime state of ONE weapon: what is in the magazine, what is in the pouch,
## whether it is mid reload and whether the trigger may produce a shot.
##
## This is deliberately not a node. The player carries three of these, every AI
## soldier carries one, and a dropped weapon on the ground carries one too. All
## the timing is driven by a `now` in seconds handed in by the caller, so the
## same object behaves identically under a paused tree or inside a test.
##
## Two reload flavours, taken from WeaponDefs.reloads_per_round():
##   - magazine fed: one motion, everything swaps at the end of the timer;
##   - per round: rounds go in one at a time and the player may abort at any
##     point and keep what has already been chambered.
##
## The Garand is the special case of the magazine flavour: an en bloc clip
## cannot be topped off, so reloading it early throws the leftover rounds away.
class_name Weapon
extends RefCounted

## Public state, read by the HUD and the viewmodel.
var id: int = WeaponDefs.NONE
var in_magazine: int = 0
var reserve: int = 0
var is_reloading: bool = false

## Seconds of opening and closing the action, outside the per round inserts.
const PER_ROUND_OVERHEAD := 0.55
## How fast the spread bloom of consecutive shots decays, per second.
const HEAT_DECAY := 1.7
## How much the bloom widens the cone at full heat.
const HEAT_SPREAD := 1.10
## Spread multipliers.
const MOVING_PENALTY := 1.75
const CROUCH_BONUS := 0.72
const AIM_MOVING_PENALTY := 1.35

var _next_shot_time: float = -1.0
var _reload_end: float = 0.0
var _reload_duration: float = 0.0
var _reload_start: float = 0.0
var _rounds_pending: int = 0
var _round_interval: float = 0.25
var _next_round_time: float = 0.0
## Heat sampled at the instant of the last shot, decayed from there on.
var _heat: float = 0.0
var _last_shot_msec: int = -100000


func _init(weapon_id: int, full: bool = true) -> void:
	id = weapon_id
	if not WeaponDefs.is_valid(id):
		id = WeaponDefs.NONE
		return
	if full:
		in_magazine = WeaponDefs.magazine(id)
		reserve = WeaponDefs.reserve_max(id)
	else:
		in_magazine = 0
		reserve = 0

# --- Firing ----------------------------------------------------------------

## True when the trigger can produce a shot right now. `now` is seconds.
##
## A per round reload does not block the trigger: interrupting the top off of a
## Kar98k to answer a rushing soldier is exactly what the animation is for.
func can_fire(now: float) -> bool:
	if id == WeaponDefs.NONE:
		return false
	if in_magazine <= 0:
		return false
	if is_reloading and not WeaponDefs.reloads_per_round(id):
		return false
	return now >= _next_shot_time


## Consumes a round and stamps the cooldown. Returns false when it could not.
func fire(now: float) -> bool:
	if not can_fire(now):
		return false
	if is_reloading:
		cancel_reload()
	in_magazine -= 1
	_next_shot_time = now + WeaponDefs.fire_interval(id)
	_heat = clampf(_heat_at(Time.get_ticks_msec()) + _heat_per_shot(), 0.0, 1.0)
	_last_shot_msec = Time.get_ticks_msec()
	return true


## Seconds left before the action is ready again, 0 when it already is.
func cooldown_left(now: float) -> float:
	return maxf(_next_shot_time - now, 0.0)


func is_empty() -> bool:
	return in_magazine <= 0


func is_full() -> bool:
	return in_magazine >= WeaponDefs.magazine(id)


## Rounds carried in total, magazine included.
func total_ammo() -> int:
	return in_magazine + reserve

# --- Reloading -------------------------------------------------------------

## True when the magazine is dry. The HUD turns the counter red on this.
func needs_reload() -> bool:
	return id != WeaponDefs.NONE and in_magazine <= 0


## True when a reload would actually change something and can start now.
func can_reload() -> bool:
	if id == WeaponDefs.NONE or is_reloading:
		return false
	if reserve <= 0:
		return false
	return in_magazine < WeaponDefs.magazine(id)


## Starts a reload. Returns the duration, or 0.0 when it cannot start.
func start_reload(now: float) -> float:
	if not can_reload():
		return 0.0
	is_reloading = true
	_reload_start = now
	if WeaponDefs.reloads_per_round(id):
		var missing := WeaponDefs.magazine(id) - in_magazine
		_rounds_pending = mini(missing, reserve)
		_round_interval = _per_round_interval()
		_reload_duration = PER_ROUND_OVERHEAD + float(_rounds_pending) * _round_interval
		_next_round_time = now + PER_ROUND_OVERHEAD * 0.5 + _round_interval
	else:
		_rounds_pending = 0
		_reload_duration = WeaponDefs.reload_time(id)
	_reload_end = now + _reload_duration
	return _reload_duration


## Advances the reload; call every frame. Returns true the frame it completes.
func tick_reload(now: float) -> bool:
	if not is_reloading:
		return false
	if WeaponDefs.reloads_per_round(id):
		var guard := 0
		while _rounds_pending > 0 and now >= _next_round_time and guard < 64:
			guard += 1
			in_magazine += 1
			reserve -= 1
			_rounds_pending -= 1
			_next_round_time += _round_interval
		if _rounds_pending <= 0 and now >= _reload_end:
			is_reloading = false
			return true
		return false
	if now < _reload_end:
		return false
	_apply_magazine_swap()
	is_reloading = false
	return true


## Aborts the reload. Rounds already chambered by a per round reload stay in.
func cancel_reload() -> void:
	is_reloading = false
	_rounds_pending = 0


## 0..1 progress of the current reload, 0 when not reloading.
func reload_progress(now: float) -> float:
	if not is_reloading or _reload_duration <= 0.0:
		return 0.0
	return clampf((now - _reload_start) / _reload_duration, 0.0, 1.0)


## Moves rounds from the pouch into the magazine.
##
## The Garand ejects a partly used en bloc clip rather than topping it off, but
## the loose rounds go back into the pouch instead of evaporating: reloading
## early costs time, never ammunition.
func _apply_magazine_swap() -> void:
	var capacity := WeaponDefs.magazine(id)
	if _is_en_bloc() and in_magazine > 0:
		reserve += in_magazine
		in_magazine = 0
	var missing := capacity - in_magazine
	var moved := mini(missing, reserve)
	reserve -= moved
	in_magazine += moved


func _is_en_bloc() -> bool:
	return id == WeaponDefs.M1_GARAND


func _per_round_interval() -> float:
	var capacity: int = maxi(WeaponDefs.magazine(id), 1)
	var body: float = maxf(WeaponDefs.reload_time(id) - PER_ROUND_OVERHEAD, 0.2)
	return body / float(capacity)

# --- Ammunition ------------------------------------------------------------

## Returns the amount actually taken, so the caller can leave the rest on the
## ground instead of vaporising it.
func add_ammo(rounds: int) -> int:
	if rounds <= 0 or id == WeaponDefs.NONE:
		return 0
	var space: int = maxi(WeaponDefs.reserve_max(id) - reserve, 0)
	var taken := mini(rounds, space)
	reserve += taken
	return taken


## "8 / 64"
func ammo_string() -> String:
	return "%d / %d" % [in_magazine, reserve]

# --- Accuracy --------------------------------------------------------------

## Cone half angle in radians for the current stance.
##
## Aiming shrinks it hard, moving opens it, crouching helps, and every shot
## adds heat that decays over about a second. Firing an MG 42 from the hip
## while sprinting is meant to be a waste of ammunition.
func current_spread(is_aiming: bool, is_moving: bool, is_crouched: bool) -> float:
	if id == WeaponDefs.NONE:
		return 0.0
	var base: float = WeaponDefs.spread_aim(id) if is_aiming else WeaponDefs.spread_hip(id)
	var factor := 1.0
	if is_moving:
		factor *= MOVING_PENALTY
		if is_aiming:
			factor *= AIM_MOVING_PENALTY
	if is_crouched:
		factor *= CROUCH_BONUS
	factor *= 1.0 + _heat_at(Time.get_ticks_msec()) * HEAT_SPREAD
	return base * factor


## Current bloom, 0 when the weapon has had time to settle.
func heat() -> float:
	return _heat_at(Time.get_ticks_msec())


func _heat_at(msec: int) -> float:
	if _last_shot_msec < 0:
		return 0.0
	var elapsed := float(msec - _last_shot_msec) / 1000.0
	return clampf(_heat - elapsed * HEAT_DECAY, 0.0, 1.0)


func _heat_per_shot() -> float:
	if WeaponDefs.is_automatic(id):
		return 0.16
	return 0.45

# --- Persistence -----------------------------------------------------------

func to_dict() -> Dictionary:
	return {
		"id": id,
		"in_magazine": in_magazine,
		"reserve": reserve,
	}


func from_dict(data: Dictionary) -> void:
	id = _read_id(data)
	in_magazine = clampi(_read_int(data, "in_magazine"), 0, WeaponDefs.magazine(id))
	reserve = clampi(_read_int(data, "reserve"), 0, WeaponDefs.reserve_max(id))
	is_reloading = false
	_rounds_pending = 0
	_heat = 0.0
	_last_shot_msec = -100000
	_next_shot_time = -1.0


## Weapon id of a saved record, always inside the id range of this build.
##
## A save can carry an id this build knows nothing about: a file written by
## another version, a corrupted entry, or simply a missing key. Propagating it
## would blow up on the first WeaponDefs.magazine() call, so anything outside
## 0 .. COUNT - 1 falls back on the Garand, which every soldier can carry.
func _read_id(data: Dictionary) -> int:
	var loaded := _read_int(data, "id", WeaponDefs.NONE)
	if loaded < 0 or loaded >= WeaponDefs.COUNT or not WeaponDefs.is_valid(loaded):
		return WeaponDefs.M1_GARAND
	return loaded


## One integer field of a saved record. JSON reads every number back as a
## float, so 4.0 has to be accepted as 4, and anything else as the fallback.
func _read_int(data: Dictionary, key: String, fallback: int = 0) -> int:
	var raw: Variant = data.get(key, fallback)
	if raw is float:
		return int(roundf(float(raw)))
	if raw is int:
		return int(raw)
	return fallback
