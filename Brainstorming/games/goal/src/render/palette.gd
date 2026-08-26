class_name Palette
extends RefCounted
## Every colour of GOAL, in one place, already in LINEAR space.
##
## The constants below go straight into `albedo_color`, into a `COLOR` written by
## a shader, or into a `_draw()` call. Nothing here is ever converted: Godot's
## `Color(r, g, b)` literal IS linear, and the renderer does the sRGB encode on
## the way to the screen.
##
## WHY THE BAND EXISTS
## The project renders with the ACES tonemapper. ACES has a long shoulder, so a
## surface whose albedo climbs towards 1.0 loses its hue before it gains any
## brightness: a "bright red" jersey at 0.95 comes out pink-white under the
## floodlights. Keeping albedos inside `ALBEDO_MIN .. ALBEDO_MAX` leaves the
## shoulder free for the LIGHT to use, which is what actually makes the image
## look lit rather than painted.
##
## The floor matters too. Nothing in the real world reflects less than about 3 %
## of the light falling on it, and a pure black albedo kills every specular cue,
## so the ball's black panels sit at 0.04 and read as leather rather than as a
## hole in the screen.
##
## The band is wider than most daylight games would use (0.72 rather than the
## usual 0.55) because the white lines, the posts and the keeper's jersey are the
## things the player has to read in a tenth of a second. They carry the whole
## image, so they are allowed to sit right at the top of the band. The ceiling is
## a HARD limit all the same, and raising it is never the way to make the game
## brighter: past it the ACES shoulder trades hue for nothing and the crowd, the
## boards and the jersey all collapse towards the same white. Brightness comes
## from the LIGHT (see SkyController), never from the albedo.
##
## WHICH CONSTANTS OBEY THE BAND
## Everything in the Turf, Ball, Goal, Kits and Stadium sections is an ALBEDO and
## must satisfy `ALBEDO_MIN <= channel <= ALBEDO_MAX` on all three channels. This
## is checked by `tests/test_palette.gd`.
##
## The "Lights and effects" section is EXEMPT, and deliberately so:
##   SUNLIGHT             - the key light of the daylight match, fed to
##                          DirectionalLight3D.light_color.
##   FLOODLIGHT           - a light colour, fed to SpotLight3D.light_color, which
##                          is an emitter and not a reflector.
##   SKY_DAY_TOP          - sky radiance at the zenith of a clear afternoon.
##   SKY_DAY_HORIZON      - idem, the pale haze band above the stands.
##   FOG_DAY              - aerial perspective tint of the daylight match.
##   AMBIENT_DAY          - daylight ambient colour, an emitter again.
##   SKY_NIGHT_TOP        - sky radiance, far below the albedo floor on purpose.
##   SKY_NIGHT_HORIZON    - idem, the sodium haze over the stands.
##   FOG_NIGHT            - volumetric/depth fog tint, not a surface.
##   AMBIENT_NIGHT        - ambient light energy colour, an emitter again.
##   TRAIL_HOT/TRAIL_COLD - additive unshaded, they are added to the frame.
##   UI_ACCENT/UI_WARN/UI_GOOD - 2D `_draw()` colours, no tonemapping applies.
##
## Naming trap avoided here: a `class_name` is a `Script` object, so a static
## method that collides with an `Object` method is shadowed by the engine's. None
## of `vary`, `clamp_albedo`, `mix`, `shade` or `desaturate` exists on `Object`.

const ALBEDO_MIN := 0.03
const ALBEDO_MAX := 0.72

# --- Turf ------------------------------------------------------------------
## Lit blade of a mown stripe, seen with the blade tip towards the camera.
const GRASS_LIGHT := Color(0.106, 0.340, 0.118)
## The mown stripe: the same grass with the blade laid the other way, so the eye
## sees the shaded side. Same hue, roughly 60 % of the value.
const GRASS_DARK := Color(0.062, 0.213, 0.081)
## Scuffed turf around the penalty spot: soil and dead grass, yellow-brown.
const GRASS_WORN := Color(0.196, 0.203, 0.125)
## Fresh line paint. Right at the top of the band, it is a hero colour at night.
const LINE_WHITE := Color(0.700, 0.712, 0.700)

# --- Ball ------------------------------------------------------------------
const BALL_WHITE := Color(0.672, 0.682, 0.700)
const BALL_BLACK := Color(0.040, 0.042, 0.048)

# --- Goal ------------------------------------------------------------------
const POST_WHITE := Color(0.655, 0.668, 0.685)
const NET_CORD := Color(0.480, 0.505, 0.535)

# --- Kits ------------------------------------------------------------------
## Fluorescent lime. The keeper is the thing the shooter must read in a tenth of
## a second, so this is the most saturated bright colour in the whole game.
const KEEPER_JERSEY := Color(0.640, 0.715, 0.085)
const KEEPER_SHORTS := Color(0.088, 0.095, 0.115)
const KEEPER_GLOVE := Color(0.620, 0.205, 0.062)
const SHOOTER_JERSEY := Color(0.430, 0.062, 0.082)
const SHOOTER_SHORTS := Color(0.052, 0.058, 0.088)
const SKIN := Color(0.462, 0.302, 0.222)
const HAIR := Color(0.078, 0.056, 0.044)
const BOOT := Color(0.058, 0.055, 0.062)

# --- Stadium ---------------------------------------------------------------
const STAND_CONCRETE := Color(0.158, 0.155, 0.150)
const SEAT_A := Color(0.098, 0.128, 0.255)
const SEAT_B := Color(0.078, 0.100, 0.196)
## Three crowd tones, scattered by `vary()` so no two spectators match.
const CROWD_A := Color(0.335, 0.352, 0.395)
const CROWD_B := Color(0.298, 0.196, 0.152)
const CROWD_C := Color(0.152, 0.215, 0.335)
const ADVERT_A := Color(0.520, 0.098, 0.088)
const ADVERT_B := Color(0.082, 0.258, 0.455)
const STEEL := Color(0.115, 0.124, 0.140)

# --- Lights and effects (EXEMPT from the albedo band, see the class comment) --

# Daylight set. This is what the game runs on: a clear late afternoon, the sun
# low enough to rake long shadows across the six yard box and warm enough to be
# read as afternoon rather than as noon.
## Late afternoon sun. Barely off white: a sun tinted any harder turns the turf
## olive, because grass is the one surface in frame with no red in it at all.
const SUNLIGHT := Color(1.000, 0.948, 0.872)
## Zenith of a clear sky. A radiance, not a surface, so it is free to be more
## saturated than any legal albedo.
const SKY_DAY_TOP := Color(0.086, 0.228, 0.520)
## The pale band where the atmosphere thickens, just above the roofs.
const SKY_DAY_HORIZON := Color(0.545, 0.655, 0.800)
## Aerial perspective: the far stand fades towards the sky, not towards grey.
const FOG_DAY := Color(0.520, 0.625, 0.775)
## Skylight filling the shadows. Distinctly BLUE, which is what makes a daylight
## shadow read as a shadow and not as a patch of dark grass.
const AMBIENT_DAY := Color(0.380, 0.480, 0.640)

# Night set. Kept whole: the floodlit look is still reachable, it is simply no
# longer the default. See SkyController.evening.
## Metal halide floodlight: near white with the faintest warm bias.
const FLOODLIGHT := Color(1.000, 0.965, 0.905)
const SKY_NIGHT_TOP := Color(0.008, 0.011, 0.020)
## Sodium glow bounced off the underside of the cloud over the stands.
const SKY_NIGHT_HORIZON := Color(0.070, 0.058, 0.048)
const FOG_NIGHT := Color(0.042, 0.050, 0.062)
const AMBIENT_NIGHT := Color(0.100, 0.118, 0.155)
const TRAIL_HOT := Color(1.000, 0.720, 0.280)
const TRAIL_COLD := Color(0.360, 0.640, 1.000)
const UI_ACCENT := Color(0.290, 0.850, 1.000)
const UI_WARN := Color(1.000, 0.620, 0.160)
const UI_GOOD := Color(0.330, 0.940, 0.440)


## Deterministic slight variation around a base colour, for scatter.
##
## `rng_value` is any float: the same value always yields the same colour, which
## is what lets the crowd be rebuilt identically on every boot without storing
## two thousand colours. `amount` is the full width of the variation, so 0.12
## means "up to plus or minus 6 % of brightness plus a small tint shift".
##
## The result is clamped back into the albedo band, because the whole point of
## scattering a crowd colour is to keep it a legal albedo.
static func vary(base: Color, rng_value: float, amount: float = 0.12) -> Color:
	var k := absf(rng_value)
	var ha := _hash_float(k, 0.0)
	var hb := _hash_float(k, 1.0)
	var hc := _hash_float(k, 2.0)
	var brightness := 1.0 + (ha - 0.5) * amount
	var tint := amount * 0.35
	return clamp_albedo(Color(
		base.r * brightness + (hb - 0.5) * tint,
		base.g * brightness + (hc - 0.5) * tint,
		base.b * brightness + (ha - 0.5) * tint,
		base.a))


## Clamps a colour back into the safe albedo band, preserving alpha.
##
## A naive per channel clamp desaturates: (0.9, 0.8, 0.7) would come out
## (0.72, 0.72, 0.70), a grey. So the bright case is handled by SCALING every
## channel by the same factor, which keeps the hue and the saturation, and only
## the leftovers are clamped.
static func clamp_albedo(c: Color) -> Color:
	var r := maxf(c.r, 0.0)
	var g := maxf(c.g, 0.0)
	var b := maxf(c.b, 0.0)
	var hi := maxf(r, maxf(g, b))
	if hi > ALBEDO_MAX:
		var k := ALBEDO_MAX / hi
		r = r * k
		g = g * k
		b = b * k
	var lo := minf(r, minf(g, b))
	if lo < ALBEDO_MIN:
		var lift := ALBEDO_MIN - lo
		r = r + lift
		g = g + lift
		b = b + lift
	return Color(
		clampf(r, ALBEDO_MIN, ALBEDO_MAX),
		clampf(g, ALBEDO_MIN, ALBEDO_MAX),
		clampf(b, ALBEDO_MIN, ALBEDO_MAX),
		c.a)


## Linear blend between two colours, alpha included. `t` is clamped to 0..1, so
## a caller that overshoots gets the endpoint rather than an illegal colour.
static func mix(a: Color, b: Color, t: float) -> Color:
	var k := clampf(t, 0.0, 1.0)
	return Color(
		a.r + (b.r - a.r) * k,
		a.g + (b.g - a.g) * k,
		a.b + (b.b - a.b) * k,
		a.a + (b.a - a.a) * k)


## Multiplies the colour brightness, staying in the safe band. Negative factors
## are treated as zero rather than flipping the colour inside out.
static func shade(c: Color, factor: float) -> Color:
	var f := maxf(factor, 0.0)
	return clamp_albedo(Color(c.r * f, c.g * f, c.b * f, c.a))


## Pulls a colour towards its own grey.
##
## The grey is the LINEAR luminance (Rec. 709 weights), not the average of the
## channels: the average would brighten a pure blue and darken a pure green,
## which reads as a value shift rather than as a loss of saturation.
##
## Deliberately NOT clamped to the band: this helper is also used on the fog and
## on the sky tint, which live outside it by design.
static func desaturate(c: Color, amount: float) -> Color:
	var k := clampf(amount, 0.0, 1.0)
	var grey := c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
	return Color(
		c.r + (grey - c.r) * k,
		c.g + (grey - c.g) * k,
		c.b + (grey - c.b) * k,
		c.a)


## Deterministic hash of a float into 0..1. The classic fract(sin(x) * big)
## construction: cheap, stable across runs and platforms at double precision,
## and decorrelated enough for three draws off the same seed.
static func _hash_float(value: float, salt: float) -> float:
	var s := sin(value * 127.1 + salt * 311.7 + 74.7) * 43758.5453123
	return s - floor(s)
