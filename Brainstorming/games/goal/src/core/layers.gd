class_name Layers
extends RefCounted
## Physics layer bits, in one place.
##
## Godot stores collision layers as a 32 bit mask, and a hand written literal
## like `collision_mask = 11` is unreadable and impossible to grep for. Every
## node in the game therefore builds its layer and its mask out of these
## constants, and no file anywhere else is allowed to write a raw number.
##
## The bit order mirrors [code]project.godot[/code]'s [code]layer_names[/code]
## section, so the inspector shows the same names the code uses.

const PITCH   := 1        ## the mown turf
const GOAL    := 2        ## posts and crossbar
const NET     := 4        ## the net panels
const BALL    := 8        ## the ball itself
const KEEPER  := 16       ## the keeper's body and gloves
const PROP    := 32       ## corner flags, advertising boards
const TRIGGER := 64       ## detection volumes
const TARGET  := 128      ## the Defi mode targets

## Everything the ball can physically stop or bounce on.
const BALL_MASK := PITCH | GOAL | NET | KEEPER | PROP | TARGET
## What the aim raycast from the camera is allowed to hit.
const AIM_MASK  := PITCH | GOAL | NET | TRIGGER
## Solid ground and frame a walking body collides with.
const WALK_MASK := PITCH | GOAL | PROP

## Every single bit declared above, lowest first. Used by the tests and by any
## debug view that wants to iterate the layers.
const ALL_BITS: Array[int] = [PITCH, GOAL, NET, BALL, KEEPER, PROP, TRIGGER, TARGET]


## Human readable name of a single bit, matching project.godot. Returns an empty
## string for anything that is not one of the eight declared bits.
static func bit_name(bit: int) -> String:
	match bit:
		PITCH:
			return "pitch"
		GOAL:
			return "goal"
		NET:
			return "net"
		BALL:
			return "ball"
		KEEPER:
			return "keeper"
		PROP:
			return "prop"
		TRIGGER:
			return "trigger"
		TARGET:
			return "target"
	return ""


## True when `mask` contains `bit`. Reads better at a call site than the raw
## bitwise test, and keeps the `& ` out of gameplay code.
static func has_bit(mask: int, bit: int) -> bool:
	return (mask & bit) != 0
