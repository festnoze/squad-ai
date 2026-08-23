## Static balance tables for every weapon of CALL OF WAR.
##
## This file is pure data: no shooting logic, no scene access, no state. Every
## accessor is a static function reading one shared constant table, so it is
## safe to call from a worker thread and cheap to call every frame.
##
## Ammunition types matter for gameplay: two weapons sharing an `ammo_type`
## feed from the same pool, which is what makes picking up the Kar98k of a
## dead German worth doing when you already carry captured 7.92 rounds.
class_name WeaponDefs
extends RefCounted

const NONE := -1
const M1_GARAND := 0
const THOMPSON := 1
const SPRINGFIELD := 2
const M1911 := 3
const MP40 := 4
const KAR98K := 5
const MG42 := 6
const GRENADE := 7
const LUGER := 8
const KAR98K_SCOPED := 9
const COUNT := 10

# Slots
const SLOT_PRIMARY := 0
const SLOT_SECONDARY := 1
const SLOT_THROWN := 2

# Ammunition types. Weapons sharing one of these share their reserve pool.
const AMMO_3006 := 0        # .30-06 Springfield  (Garand, Springfield)
const AMMO_45ACP := 1       # .45 ACP             (Thompson, M1911)
const AMMO_9MM := 2         # 9 mm Parabellum     (MP40, Luger P08)
const AMMO_792 := 3         # 7.92x57 Mauser      (Kar98k, scoped Kar98k, MG42)
const AMMO_GRENADE := 4     # thrown ordnance
const AMMO_TYPE_COUNT := 5

## Longest distance a bullet of this game is ever traced, in metres.
const MAX_TRACE := 600.0

## Absolute floor of any falloff curve. A bullet always hurts a little.
const FALLOFF_MIN := 0.35

## Field keys of a weapon record, documented once here:
##   name        French display name shown to the player
##   slot        SLOT_PRIMARY / SLOT_SECONDARY / SLOT_THROWN
##   damage      base damage on a torso hit inside the effective range
##   hs          headshot multiplier
##   rpm         rounds per minute (cyclic rate for automatics)
##   auto        true when holding the trigger keeps firing
##   mag         magazine / clip capacity
##   reserve     maximum carried rounds outside the magazine
##   reload      seconds for a full reload (for a per round weapon, seconds for
##               the whole cycle when the weapon starts empty)
##   per_round   true when rounds are pushed in one at a time
##   sp_hip      hip fire cone half angle, radians
##   sp_aim      aimed cone half angle, radians
##   rec_p       recoil pitch kick per shot, radians
##   rec_y       recoil yaw kick per shot, radians (the sign is randomised)
##   fov         aimed field of view scale, 1.0 means no zoom at all
##   scope       true when the weapon carries a telescopic sight
##   vel         muzzle velocity in metres per second
##   fire_sfx    SfxLib sample name for the shot
##   load_sfx    SfxLib sample name for the reload
##   pen         penetration power, 0 (none) to 1 (through anything thin)
##   ammo        AMMO_* constant
##   weight      kilograms, used by the player for sprint and sway
##   axis        true for German hardware
##   eff         distance up to which damage is not reduced at all
##   far         distance at which damage reaches its floor
##   floor       damage multiplier floor, never below FALLOFF_MIN
const _DEFS: Dictionary = {
	M1_GARAND: {
		"name": "Fusil M1 Garand", "slot": SLOT_PRIMARY,
		"damage": 42.0, "hs": 2.5, "rpm": 340.0, "auto": false,
		"mag": 8, "reserve": 96, "reload": 2.6, "per_round": false,
		"sp_hip": 0.0300, "sp_aim": 0.0032, "rec_p": 0.0300, "rec_y": 0.0085,
		"fov": 0.72, "scope": false, "vel": 853.0,
		"fire_sfx": "rifle_m1", "load_sfx": "reload_in",
		"pen": 0.62, "ammo": AMMO_3006, "weight": 4.3, "axis": false,
		"eff": 120.0, "far": 320.0, "floor": 0.62,
	},
	THOMPSON: {
		"name": "Mitraillette Thompson M1A1", "slot": SLOT_PRIMARY,
		"damage": 26.0, "hs": 1.7, "rpm": 700.0, "auto": true,
		"mag": 30, "reserve": 240, "reload": 3.0, "per_round": false,
		"sp_hip": 0.0450, "sp_aim": 0.0140, "rec_p": 0.0120, "rec_y": 0.0050,
		"fov": 0.86, "scope": false, "vel": 285.0,
		"fire_sfx": "smg_thompson", "load_sfx": "reload_in",
		"pen": 0.30, "ammo": AMMO_45ACP, "weight": 4.9, "axis": false,
		"eff": 25.0, "far": 60.0, "floor": 0.42,
	},
	SPRINGFIELD: {
		"name": "Fusil de précision Springfield M1903", "slot": SLOT_PRIMARY,
		"damage": 85.0, "hs": 3.0, "rpm": 45.0, "auto": false,
		"mag": 5, "reserve": 50, "reload": 3.4, "per_round": true,
		"sp_hip": 0.0550, "sp_aim": 0.0009, "rec_p": 0.0500, "rec_y": 0.0100,
		"fov": 0.25, "scope": true, "vel": 800.0,
		"fire_sfx": "sniper_springfield", "load_sfx": "bolt",
		"pen": 0.88, "ammo": AMMO_3006, "weight": 4.0, "axis": false,
		"eff": 300.0, "far": 600.0, "floor": 0.92,
	},
	M1911: {
		"name": "Pistolet Colt M1911", "slot": SLOT_SECONDARY,
		"damage": 34.0, "hs": 2.0, "rpm": 420.0, "auto": false,
		"mag": 7, "reserve": 56, "reload": 2.1, "per_round": false,
		"sp_hip": 0.0380, "sp_aim": 0.0120, "rec_p": 0.0220, "rec_y": 0.0070,
		"fov": 0.92, "scope": false, "vel": 250.0,
		"fire_sfx": "pistol_1911", "load_sfx": "reload_in",
		"pen": 0.25, "ammo": AMMO_45ACP, "weight": 1.1, "axis": false,
		"eff": 18.0, "far": 55.0, "floor": 0.38,
	},
	MP40: {
		"name": "Mitraillette MP 40", "slot": SLOT_PRIMARY,
		"damage": 25.0, "hs": 1.7, "rpm": 550.0, "auto": true,
		"mag": 32, "reserve": 256, "reload": 2.9, "per_round": false,
		"sp_hip": 0.0400, "sp_aim": 0.0120, "rec_p": 0.0110, "rec_y": 0.0045,
		"fov": 0.86, "scope": false, "vel": 380.0,
		"fire_sfx": "smg_mp40", "load_sfx": "reload_in",
		"pen": 0.32, "ammo": AMMO_9MM, "weight": 4.0, "axis": true,
		"eff": 28.0, "far": 68.0, "floor": 0.44,
	},
	KAR98K: {
		"name": "Fusil Mauser Kar98k", "slot": SLOT_PRIMARY,
		"damage": 78.0, "hs": 2.8, "rpm": 50.0, "auto": false,
		"mag": 5, "reserve": 60, "reload": 3.2, "per_round": true,
		"sp_hip": 0.0520, "sp_aim": 0.0016, "rec_p": 0.0460, "rec_y": 0.0100,
		"fov": 0.55, "scope": false, "vel": 760.0,
		"fire_sfx": "rifle_kar98", "load_sfx": "bolt",
		"pen": 0.82, "ammo": AMMO_792, "weight": 3.9, "axis": true,
		"eff": 150.0, "far": 360.0, "floor": 0.66,
	},
	MG42: {
		"name": "Mitrailleuse MG 42", "slot": SLOT_PRIMARY,
		"damage": 30.0, "hs": 1.9, "rpm": 1200.0, "auto": true,
		"mag": 50, "reserve": 300, "reload": 5.2, "per_round": false,
		"sp_hip": 0.0700, "sp_aim": 0.0200, "rec_p": 0.0135, "rec_y": 0.0060,
		"fov": 0.90, "scope": false, "vel": 755.0,
		"fire_sfx": "mg42", "load_sfx": "reload_in",
		"pen": 0.72, "ammo": AMMO_792, "weight": 11.6, "axis": true,
		"eff": 90.0, "far": 280.0, "floor": 0.52,
	},
	GRENADE: {
		"name": "Grenade Mk 2", "slot": SLOT_THROWN,
		"damage": 130.0, "hs": 1.0, "rpm": 55.0, "auto": false,
		"mag": 1, "reserve": 6, "reload": 1.0, "per_round": true,
		"sp_hip": 0.0100, "sp_aim": 0.0040, "rec_p": 0.0000, "rec_y": 0.0000,
		"fov": 1.00, "scope": false, "vel": 18.0,
		"fire_sfx": "grenade_throw", "load_sfx": "grenade_pin",
		"pen": 0.00, "ammo": AMMO_GRENADE, "weight": 0.6, "axis": false,
		"eff": 4.0, "far": 9.0, "floor": 0.35,
	},
	LUGER: {
		"name": "Pistolet Luger P08", "slot": SLOT_SECONDARY,
		"damage": 30.0, "hs": 2.0, "rpm": 380.0, "auto": false,
		"mag": 8, "reserve": 40, "reload": 2.2, "per_round": false,
		"sp_hip": 0.0360, "sp_aim": 0.0110, "rec_p": 0.0200, "rec_y": 0.0060,
		"fov": 0.92, "scope": false, "vel": 350.0,
		"fire_sfx": "pistol_1911", "load_sfx": "reload_in",
		"pen": 0.28, "ammo": AMMO_9MM, "weight": 0.9, "axis": true,
		"eff": 20.0, "far": 58.0, "floor": 0.40,
	},
	KAR98K_SCOPED: {
		"name": "Fusil Mauser Kar98k à lunette", "slot": SLOT_PRIMARY,
		"damage": 78.0, "hs": 3.0, "rpm": 45.0, "auto": false,
		"mag": 5, "reserve": 45, "reload": 4.2, "per_round": true,
		"sp_hip": 0.0620, "sp_aim": 0.0011, "rec_p": 0.0460, "rec_y": 0.0100,
		"fov": 0.25, "scope": true, "vel": 760.0,
		"fire_sfx": "rifle_kar98", "load_sfx": "bolt",
		"pen": 0.82, "ammo": AMMO_792, "weight": 4.4, "axis": true,
		"eff": 220.0, "far": 520.0, "floor": 0.88,
	},
}

## Returned instead of null for an unknown id, so every accessor stays total.
const _FALLBACK: Dictionary = {
	"name": "Aucune arme", "slot": SLOT_PRIMARY,
	"damage": 0.0, "hs": 1.0, "rpm": 60.0, "auto": false,
	"mag": 0, "reserve": 0, "reload": 1.0, "per_round": false,
	"sp_hip": 0.05, "sp_aim": 0.05, "rec_p": 0.0, "rec_y": 0.0,
	"fov": 1.0, "scope": false, "vel": 300.0,
	"fire_sfx": "dry_fire", "load_sfx": "reload_in",
	"pen": 0.0, "ammo": AMMO_45ACP, "weight": 0.0, "axis": false,
	"eff": 10.0, "far": 20.0, "floor": 1.0,
}

## French names of the ammunition pools, index = AMMO_* constant.
const AMMO_NAMES: PackedStringArray = [
	"Cartouches .30-06",
	"Cartouches .45 ACP",
	"Cartouches 9 mm Parabellum",
	"Cartouches 7,92 Mauser",
	"Grenades",
]

# --- Internal --------------------------------------------------------------

static func _def(id: int) -> Dictionary:
	if _DEFS.has(id):
		return _DEFS[id]
	return _FALLBACK

# --- Identity --------------------------------------------------------------

static func display_name(id: int) -> String:
	return String(_def(id)["name"])

static func slot_of(id: int) -> int:
	return int(_def(id)["slot"])

static func is_valid(id: int) -> bool:
	return _DEFS.has(id)

static func all_ids() -> PackedInt32Array:
	return PackedInt32Array([
		M1_GARAND, THOMPSON, SPRINGFIELD, M1911, MP40, KAR98K, MG42, GRENADE,
		LUGER, KAR98K_SCOPED,
	])

## Every weapon that belongs in the given slot.
static func ids_in_slot(slot: int) -> PackedInt32Array:
	var out: PackedInt32Array = []
	for id in all_ids():
		if slot_of(id) == slot:
			out.append(id)
	return out

# --- Damage ----------------------------------------------------------------

static func damage(id: int) -> float:
	return float(_def(id)["damage"])

static func headshot_multiplier(id: int) -> float:
	return float(_def(id)["hs"])

## Damage multiplier at a given distance (falloff curve).
##
## Full damage up to the effective range of the weapon, then a straight line
## down to its floor, which is reached at `far` and held for ever after. A
## submachine gun collapses fast, the Springfield barely notices the distance.
static func falloff(id: int, distance: float) -> float:
	var d: Dictionary = _def(id)
	var eff := float(d["eff"])
	if distance <= eff:
		return 1.0
	var far := float(d["far"])
	var low: float = maxf(float(d["floor"]), FALLOFF_MIN)
	if distance >= far or far <= eff:
		return low
	return lerpf(1.0, low, (distance - eff) / (far - eff))

## Convenience: final damage of one bullet, falloff and headshot included.
static func damage_at(id: int, distance: float, headshot: bool) -> float:
	var value := damage(id) * falloff(id, distance)
	if headshot:
		value *= headshot_multiplier(id)
	return value

static func effective_range(id: int) -> float:
	return float(_def(id)["eff"])

static func drop_off_range(id: int) -> float:
	return float(_def(id)["far"])

static func falloff_floor(id: int) -> float:
	return maxf(float(_def(id)["floor"]), FALLOFF_MIN)

# --- Rate of fire ----------------------------------------------------------

static func rpm(id: int) -> float:
	return float(_def(id)["rpm"])

static func is_automatic(id: int) -> bool:
	return bool(_def(id)["auto"])

## Seconds between two shots.
static func fire_interval(id: int) -> float:
	var rate := rpm(id)
	if rate <= 0.0:
		return 1.0
	return 60.0 / rate

## True for the bolt actions, which need a visible cycling animation.
static func is_bolt_action(id: int) -> bool:
	return id == SPRINGFIELD or id == KAR98K or id == KAR98K_SCOPED

# --- Ammunition ------------------------------------------------------------

static func magazine(id: int) -> int:
	return int(_def(id)["mag"])

static func reserve_max(id: int) -> int:
	return int(_def(id)["reserve"])

static func reload_time(id: int) -> float:
	return float(_def(id)["reload"])

## True when rounds are pushed in one at a time (bolt actions, grenades),
## false when the whole magazine or en bloc clip is swapped in one motion.
static func reloads_per_round(id: int) -> bool:
	return bool(_def(id)["per_round"])

static func ammo_type(id: int) -> int:
	return int(_def(id)["ammo"])

## Two weapons feeding from the same pool. Picking up German ammunition for a
## captured German weapon is the whole point of this.
static func shares_ammo(id_a: int, id_b: int) -> bool:
	return ammo_type(id_a) == ammo_type(id_b)

static func ammo_type_name(ammo: int) -> String:
	if ammo < 0 or ammo >= AMMO_NAMES.size():
		return "Munitions"
	return AMMO_NAMES[ammo]

## Every weapon feeding from the given ammunition pool.
static func ids_using_ammo(ammo: int) -> PackedInt32Array:
	var out: PackedInt32Array = []
	for id in all_ids():
		if ammo_type(id) == ammo:
			out.append(id)
	return out

## How many rounds a dropped weapon or an ammo crate hands over.
static func pickup_rounds(id: int) -> int:
	return maxi(magazine(id), int(reserve_max(id) / 4))

# --- Handling --------------------------------------------------------------

static func spread_hip(id: int) -> float:
	return float(_def(id)["sp_hip"])

static func spread_aim(id: int) -> float:
	return float(_def(id)["sp_aim"])

static func recoil_pitch(id: int) -> float:
	return float(_def(id)["rec_p"])

static func recoil_yaw(id: int) -> float:
	return float(_def(id)["rec_y"])

static func aim_fov_scale(id: int) -> float:
	return float(_def(id)["fov"])

static func has_scope(id: int) -> bool:
	return bool(_def(id)["scope"])

static func muzzle_velocity(id: int) -> float:
	return float(_def(id)["vel"])

static func weight(id: int) -> float:
	return float(_def(id)["weight"])

## 0 (none) to 1 (through anything thin). Compared by Ballistics against the
## cost of the surface that was hit.
static func penetration(id: int) -> float:
	return float(_def(id)["pen"])

# --- Presentation ----------------------------------------------------------

static func fire_sample(id: int) -> String:
	return String(_def(id)["fire_sfx"])

static func reload_sample(id: int) -> String:
	return String(_def(id)["load_sfx"])

static func is_axis_weapon(id: int) -> bool:
	return bool(_def(id)["axis"])

## How far a shot can be heard, in metres. Feeds the AI hearing checks.
static func noise_radius(id: int) -> float:
	if id == GRENADE:
		return 30.0
	return clampf(60.0 + damage(id) * 1.6, 60.0, 240.0)

## Short French label for the HUD, without the model number.
static func short_name(id: int) -> String:
	match id:
		M1_GARAND:
			return "Garand"
		THOMPSON:
			return "Thompson"
		SPRINGFIELD:
			return "Springfield"
		M1911:
			return "M1911"
		MP40:
			return "MP 40"
		KAR98K:
			return "Kar98k"
		MG42:
			return "MG 42"
		GRENADE:
			return "Grenade"
		LUGER:
			return "Luger"
		KAR98K_SCOPED:
			return "Kar98k à lunette"
		_:
			return "Aucune"
