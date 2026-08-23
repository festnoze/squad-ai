## Physics collision layer bits and the composite masks used across the project.
##
## Never write a raw bitmask anywhere else: every body, area and raycast in
## CALL OF WAR pulls its layer and mask values from here so a change stays in
## one single place.
class_name Layers
extends RefCounted

const TERRAIN   := 1
const STRUCTURE := 2
const PLAYER    := 4
const ENEMY     := 8
const ALLY      := 16
const PROP      := 32
const VEHICLE   := 64
const TRIGGER   := 128

## Everything a bullet can stop on.
const BULLET_MASK := TERRAIN | STRUCTURE | PLAYER | ENEMY | ALLY | PROP | VEHICLE
## Everything that blocks line of sight for the AI.
const SIGHT_MASK  := TERRAIN | STRUCTURE | PROP | VEHICLE
## Solid ground and walls a walking body collides with.
const WALK_MASK   := TERRAIN | STRUCTURE | PROP | VEHICLE

## Every single bit, in declaration order. Index matches BIT_NAMES.
const ALL_BITS: PackedInt32Array = [
	TERRAIN, STRUCTURE, PLAYER, ENEMY, ALLY, PROP, VEHICLE, TRIGGER,
]

## Human readable names, aligned with ALL_BITS and with project.godot.
const BIT_NAMES: PackedStringArray = [
	"terrain", "structure", "player", "enemy", "ally", "prop", "vehicle",
	"trigger",
]

## Every combatant body, whatever its faction.
const COMBATANT_MASK := PLAYER | ENEMY | ALLY
## What a soldier walking body must collide with (world plus other bodies).
const SOLDIER_MASK := TERRAIN | STRUCTURE | PROP | VEHICLE
## Static world geometry only, for ground probes.
const GROUND_MASK := TERRAIN

## Debug helper: "terrain|structure" for a composite mask, "" when mask is 0.
static func mask_to_string(mask: int) -> String:
	var parts: PackedStringArray = []
	for i in ALL_BITS.size():
		if (mask & ALL_BITS[i]) != 0:
			parts.append(BIT_NAMES[i])
	return "|".join(parts)

## True when `mask` contains every bit of `bits`.
static func mask_has(mask: int, bits: int) -> bool:
	return (mask & bits) == bits

## The collision layer a body of `faction` belongs to. `faction` uses the
## War.ALLIED / War.AXIS / War.NEUTRAL constants (0 / 1 / 2).
static func faction_layer(faction: int) -> int:
	match faction:
		1:
			return ENEMY
		0:
			return ALLY
		_:
			return PROP

## The bodies a combatant of `faction` considers hostile.
static func hostile_mask(faction: int) -> int:
	match faction:
		1:
			return PLAYER | ALLY
		0:
			return ENEMY
		_:
			return 0
