class_name Palette
extends RefCounted

## Colour vocabulary of CALL OF WAR, Normandy 1942.
##
## Every constant below is ALREADY in linear space: the values are handed
## straight to `albedo_color` / `COLOR` without any conversion. Known engine
## trap: an albedo that is too bright desaturates towards white once it goes
## through the ACES tonemap shoulder, which kills the washed out, cold war film
## look we want. Every albedo therefore stays inside 0.05 .. 0.38.
##
## The only saturated colours in the whole game are fire, tracers and muzzle
## flashes: they are emissive, not albedo, so the rule does not apply to them.

# --- Ground and vegetation -------------------------------------------------

const GRASS_SUMMER := Color(0.19, 0.26, 0.10)
const GRASS_DRY    := Color(0.30, 0.28, 0.13)
const WHEAT        := Color(0.34, 0.29, 0.12)
const DIRT         := Color(0.20, 0.15, 0.10)
const MUD          := Color(0.13, 0.10, 0.07)
const ROAD         := Color(0.16, 0.15, 0.14)
const STONE        := Color(0.24, 0.23, 0.21)
const STONE_DARK   := Color(0.14, 0.13, 0.12)
const CONCRETE     := Color(0.22, 0.22, 0.21)
const WOOD         := Color(0.16, 0.11, 0.07)
const WOOD_LIGHT   := Color(0.26, 0.19, 0.12)
const ROOF_SLATE   := Color(0.09, 0.10, 0.12)
const ROOF_TILE    := Color(0.24, 0.12, 0.08)
const PLASTER      := Color(0.32, 0.30, 0.26)
const LEAF_DARK    := Color(0.10, 0.17, 0.08)
const LEAF_LIGHT   := Color(0.16, 0.24, 0.10)
const WATER        := Color(0.05, 0.10, 0.12)
const METAL        := Color(0.13, 0.13, 0.14)
const RUST         := Color(0.18, 0.09, 0.05)

# --- Factions and flesh ----------------------------------------------------

const FELDGRAU     := Color(0.13, 0.16, 0.13)   # uniforme allemand
const KHAKI        := Color(0.20, 0.18, 0.12)   # uniforme allie
const RESISTANCE   := Color(0.14, 0.13, 0.16)   # civils armes
const SKIN         := Color(0.30, 0.21, 0.16)
const BLOOD        := Color(0.16, 0.02, 0.02)

# --- Emissive / effects ----------------------------------------------------

const TRACER       := Color(1.0, 0.62, 0.22)
const MUZZLE       := Color(1.0, 0.78, 0.38)
const FIRE         := Color(1.0, 0.42, 0.12)
const SMOKE        := Color(0.14, 0.13, 0.12)
const SNOW         := Color(0.34, 0.35, 0.38)

# --- Albedo safety band ----------------------------------------------------

## Darkest albedo channel value the ACES curve still resolves without crushing.
const ALBEDO_MIN := 0.05
## Brightest albedo channel value before the ACES shoulder desaturates it.
const ALBEDO_MAX := 0.38

# --- Sky / lighting reference colours --------------------------------------
#
# These are LIGHT colours, not albedo, so they are allowed to exceed the band.

## Sun tint at dawn (roughly time_of_day 0.25).
const SUN_DAWN     := Color(1.00, 0.66, 0.48)
## Sun tint at noon: a cold, slightly broken white, not pure 1,1,1.
const SUN_NOON     := Color(1.00, 0.97, 0.90)
## Sun tint at dusk (roughly time_of_day 0.79).
const SUN_DUSK     := Color(1.00, 0.55, 0.28)
## Moonlight: very weak and blue.
const MOON_LIGHT   := Color(0.42, 0.52, 0.78)

## Overhead sky colour at noon, clear weather.
const SKY_TOP_DAY  := Color(0.24, 0.38, 0.58)
## Horizon colour at noon, clear weather. Hazy and desaturated.
const SKY_HZN_DAY  := Color(0.62, 0.66, 0.68)
## Overhead sky colour at night.
const SKY_TOP_NIGHT := Color(0.015, 0.022, 0.045)
## Horizon colour at night.
const SKY_HZN_NIGHT := Color(0.045, 0.055, 0.080)
## Overhead sky colour under a full Normandy overcast.
const SKY_TOP_OVERCAST := Color(0.30, 0.32, 0.35)
## Horizon colour under a full overcast.
const SKY_HZN_OVERCAST := Color(0.44, 0.45, 0.46)

## Distance fog colour, daylight. Cold and grey, close to the hazy horizon.
const FOG_DAY      := Color(0.52, 0.56, 0.58)
## Distance fog colour, night.
const FOG_NIGHT    := Color(0.045, 0.055, 0.075)

## Ambient bounce colour used when sky contribution is lowered.
const AMBIENT_DAY   := Color(0.36, 0.40, 0.46)
const AMBIENT_NIGHT := Color(0.045, 0.055, 0.085)


## Deterministic slight variation around a base colour, for scatter.
##
## `rng_value` is expected in [0, 1] but any float works: it is folded back into
## range. Three decorrelated offsets are derived from it so the variation is not
## a pure brightness ramp (that would look like banding on a field of grass).
## The result is clamped back into the safe albedo band so that a varied colour
## can never wander into the ACES shoulder.
static func vary(base: Color, rng_value: float, amount: float = 0.12) -> Color:
	var t: float = fposmod(rng_value, 1.0)
	# Three irrational multipliers keep the channels decorrelated.
	var a: float = fposmod(t * 1.0, 1.0) * 2.0 - 1.0
	var b: float = fposmod(t * 2.7182818 + 0.371, 1.0) * 2.0 - 1.0
	var c: float = fposmod(t * 4.6692016 + 0.719, 1.0) * 2.0 - 1.0
	# A shared component keeps the hue family, the per channel part adds life.
	var common: float = a * amount
	var out := Color(
		base.r * (1.0 + common) + b * amount * 0.35 * base.r,
		base.g * (1.0 + common) + c * amount * 0.35 * base.g,
		base.b * (1.0 + common) + a * amount * 0.35 * base.b,
		base.a
	)
	return clamp_albedo(out)


## Clamps a colour back into the safe albedo band, preserving alpha.
## Pure black stays black-ish rather than being lifted to a flat grey: only
## channels above zero are pushed up to ALBEDO_MIN.
static func clamp_albedo(c: Color) -> Color:
	return Color(
		clampf(c.r, 0.0, ALBEDO_MAX),
		clampf(c.g, 0.0, ALBEDO_MAX),
		clampf(c.b, 0.0, ALBEDO_MAX),
		c.a
	)


## Linear blend between two colours, alpha included.
static func mix(a: Color, b: Color, t: float) -> Color:
	var k: float = clampf(t, 0.0, 1.0)
	return Color(
		lerpf(a.r, b.r, k),
		lerpf(a.g, b.g, k),
		lerpf(a.b, b.b, k),
		lerpf(a.a, b.a, k)
	)


## Multiplies the colour brightness, staying in the safe band.
static func shade(c: Color, factor: float) -> Color:
	return clamp_albedo(Color(c.r * factor, c.g * factor, c.b * factor, c.a))


## Pulls a colour towards its own grey, for the washed out war film mood.
## `amount` 0 keeps the colour, 1 makes it fully grey.
static func desaturate(c: Color, amount: float) -> Color:
	var grey: float = c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
	var k: float = clampf(amount, 0.0, 1.0)
	return Color(
		lerpf(c.r, grey, k),
		lerpf(c.g, grey, k),
		lerpf(c.b, grey, k),
		c.a
	)
