## Sky, sun, environment, fog and ambient light.
##
## The game is a DAYLIGHT match: a clear late afternoon, the sun low enough to
## rake long soft shadows across the six yard box, the sky filling every shadow
## it does not reach. The floodlit night look this file used to hold is still
## here and still reachable, it is simply no longer what the player sees on
## launch. One float chooses: `evening`, 0 for full night, 1 for daylight.
##
## HOW THE IMAGE IS MADE BRIGHT, in order, because the order is the whole trick.
##
## 1. LIGHT, not albedo. `Palette` caps every surface at 0.72 and that ceiling is
##    not negotiable: past it the ACES shoulder trades hue for nothing and the
##    crowd, the boards and the keeper's jersey all collapse towards the same
##    white. So the brightness comes from a real key light. `_sun` is a
##    DirectionalLight3D at daylight energy, barely off white, and thrown mostly
##    from the SIDE, which is the one azimuth that both lights the keeper's chest
##    and puts his shadow somewhere the camera can see it. See `_SUN_DIRECTION`,
##    it is the least free number in this file.
##
## 2. AMBIENT. In daylight the sky is a hundred metre area light and it is what
##    stops the shadows crushing to black. AMBIENT_SOURCE_SKY with the sky
##    contribution driven all the way to 1.0.
##
##    THE TRAP, and it has cost this team an evening: `ambient_light_energy` and
##    `ambient_light_color` are COMPLETELY INERT while
##    `ambient_light_sky_contribution` is 1.0. Two different knobs drive the fill
##    depending on the hour, and this file picks deliberately:
##      - in DAYLIGHT the fill is driven by the SKY, so the level knob is
##        `sky_energy_multiplier` on the sky material, not `ambient_light_energy`,
##        which is left at a sane value purely so a caller who lowers the
##        contribution gets something reasonable;
##      - at NIGHT there is no sky worth sampling, so the contribution is dropped
##        to 0.2 first and the explicit AMBIENT_NIGHT colour and energy take over.
##
## 3. EXPOSURE and white point. Retuned for the new light level. Daylight sits at
##    a LOWER exposure than the night match did, which sounds backwards and is
##    not: the scene now carries ten times the light, so the job of the tonemap
##    changes from lifting a dark frame to keeping a bright one off the ceiling.
##    White is pushed out to 1.7 so the sky and the sunlit paint have somewhere to
##    roll off into: the lines, the posts and the ball come out bright and still
##    holding their shading instead of clipping to flat paper.
##
## 4. FOG. Depth fog only, and it still starts at 26 m, which is past the goal
##    from every camera the game uses. In daylight it is aerial perspective and
##    nothing else: pale, blue, thin, so the far stand recedes and the near half
##    of the pitch is untouched. The volumetric fog is OFF in daylight. Its only
##    job was making the spotlight cones visible, there are no cones any more, and
##    a froxel grid nobody looks at is pure cost.
##
## 5. GLOW. The night threshold was set so only the lamp faces bloomed. Under a
##    daylight key the same threshold would catch the whole pitch and wash the
##    frame out, so it is pushed above the brightest lit surface: only the sun
##    disc and a specular hit on the ball or the posts cross it.
##
## Player facing text: none in this file.
class_name SkyController
extends Node

## Time of day, 0 = full night under the pylons, 0.5 = dusk, 1 = bright late
## afternoon daylight. The game runs at 1.0.
##
## Everything below interpolates over the two segments night -> dusk -> day, so
## any value in between is a legal look and not just the two ends. Set it before
## `build()`, or set it and call `apply()`.
##
## Returning the game to the night match takes TWO changes, not one: this value
## below 0.35, and `Mats.daylight = false` before the first material is built
## (the emission floors that keep the stands and the boards off pure black under
## spotlights are baked into cached materials, so they cannot follow a runtime
## change of this float).
var evening: float = 1.0

## Below this the pylon spots and the night emission floors are the right call,
## above it the sun is. Shared with `Mats.daylight` and `Stadium`, which read the
## same threshold through `is_daylight()`.
const DAYLIGHT_THRESHOLD := 0.35

## Dusk, the midpoint of the interpolation. These live here rather than in
## Palette because nothing else in the game ever needs them: only the two ends
## are ever played.
const _DUSK_TOP := Color(0.09, 0.15, 0.26, 1.0)
const _DUSK_HORIZON := Color(0.46, 0.36, 0.28, 1.0)
const _DUSK_FOG := Color(0.20, 0.19, 0.21, 1.0)
const _DUSK_AMBIENT := Color(0.22, 0.24, 0.31, 1.0)

## Depth fog is not allowed to start closer than this, in metres. The goal line
## is at z = 0 and the shooting camera sits around z = 14, so 26 m keeps the
## whole frame and net crisp with a wide margin.
const _FOG_BEGIN := 26.0
const _FOG_END := 150.0

## The sun, in a stadium whose goal line is z = 0 and whose shooter looks towards
## -Z. The light TRAVELS along this vector, so the sun itself sits in the opposite
## direction: high on the shooter's RIGHT, a little way behind him.
##
## THE AZIMUTH IS THE WHOLE POINT AND IT IS NOT FREE. Every camera in this game
## looks roughly down -Z, so a sun anywhere behind the CAMERA throws every shadow
## away from it, behind the object casting it, where none of them can be seen: the
## first daylight pass came back with a perfectly lit pitch and not one shadow on
## it. A sun behind the GOAL fixes that and breaks something worse, because it
## backlights the keeper, and the keeper is the silhouette the player has to read
## in a tenth of a second.
##
## So the light is thrown mostly SIDEWAYS, with only a small lean AWAY from the
## camera. Lateral is four times the depth component, which throws the keeper's
## shadow two and a half metres out to his left and only half a metre back: fully
## in frame, drawing the ground plane along the goal line, while the sun lights
## the half of him the shooter is looking at instead of rimming his back. Height
## 0.60 of unit length is an elevation of about 37 degrees, which is late
## afternoon and makes a shadow a third longer than the thing casting it.
##
## THE SIGN OF THE Z TERM WAS WRONG, and everything above it was right. It read
## +0.18, which puts the sun BEHIND THE GOAL and sends the light towards the
## camera: precisely the case the paragraph above rules out. Every surface facing
## the shooter was then turned away from the sun, and the two that matter most are
## the keeper's chest and the entire near end stand, whose seating, aisles,
## perimeter wall and roof fascia all face down the pitch. Measured on the
## shooting camera, that stand filled the upper half of the frame at 42 of 255
## against 135 for the turf: a lit pitch under a dark bowl. Only the reverse angle
## behind the goal, which looks at the FAR stand, ever showed daylight on a stand,
## and that is what hid the sign for so long.
##
## Negating it costs nothing the comment was defending. The shadows still run
## sideways, because lateral still outweighs depth four to one: the keeper's
## shadow now falls half a metre into the goal instead of half a metre out of it,
## which no camera in the game can tell apart. What it buys is a front lit keeper,
## a front lit goal frame and a bowl that reads as afternoon from the one camera
## the player actually plays in.
const _SUN_DIRECTION := Vector3(-0.78, -0.60, -0.18)
## Angular diameter, degrees. The real sun is 0.53; this is opened up because it
## is also the penumbra control, and a stadium looks better with soft edges than
## with astronomically correct hard ones.
const _SUN_ANGULAR_SIZE := 0.9
## Shadows are the single most expensive thing in this file, so it is two PSSM
## splits and no more. What matters is WHERE the first one ends.
##
## The shooting camera stands 8.2 m behind the penalty spot, which puts the keeper
## 19.3 m away and the goal frame a shade further. The first pass of this work ran
## 110 m of range with the split at 0.16, so split one ended at 17.6 m: everything
## the player actually looks at fell into split two, which had to stretch one
## shadow map over the remaining ninety metres. The keeper cast no shadow at all
## from the only camera the game is played in, while the same keeper cast a
## perfectly good one from the goal camera six metres away, which is what made the
## bug so slow to find.
##
## 70 m still reaches past the far stand from any camera in the game, and a split
## at 0.45 puts the whole penalty area, both goals and the near stand inside the
## first map. That is the entire fix: the same two passes, aimed at the right
## thirty metres.
const _SHADOW_DISTANCE := 70.0
const _SHADOW_SPLIT := 0.45

## Sodium lamps hum and breathe. Two slow incommensurable sines beat against
## each other so the flicker never reads as a loop. Faded out with the daylight:
## the sun does not flicker.
const _FLICKER_A := 1.73
const _FLICKER_B := 0.41
const _FLICKER_DEPTH := 0.035

var _holder: WorldEnvironment = null
var _environment: Environment = null
var _sky: Sky = null
var _sky_material: ProceduralSkyMaterial = null
var _sun: DirectionalLight3D = null

var _time: float = 0.0
## Values animate() modulates around. Never read back from the environment: a
## multiplier applied to a value that already carries it compounds every frame.
var _sky_energy_base: float = 1.0
var _volume_density_base: float = 0.006
var _horizon_base: Color = Color(0.545, 0.655, 0.800, 1.0)
## Depth of the lamp flicker for the current hour, 0 in full daylight.
var _flicker_amount: float = 0.0
## Degrees per second the sky drifts. Cloudless daylight has nothing to drift.
var _sky_drift: float = 0.0


func _ready() -> void:
	# Main calls build() as part of its own setup, but the scene must still look
	# right if it is opened on its own, so this is idempotent and harmless.
	build()


## True when the current hour is lit by the sun rather than by the pylons. The
## stadium asks so it knows whether to switch its floodlights on.
func is_daylight() -> bool:
	return evening >= DAYLIGHT_THRESHOLD


func build() -> void:
	if _environment != null:
		apply()
		return
	_holder = _find_holder()
	if _holder == null:
		# The scene should carry a WorldEnvironment sibling. Missing one is a
		# scene authoring mistake, not a reason to run with no environment at
		# all, so one is created and parented here where it is guaranteed to be
		# safe to add (adding to the parent mid _ready is not).
		push_warning("SkyController: no WorldEnvironment sibling found, creating one.")
		_holder = WorldEnvironment.new()
		_holder.name = "WorldEnvironment"
		add_child(_holder)

	_sky_material = ProceduralSkyMaterial.new()
	_sky_material.use_debanding = true

	_sky = Sky.new()
	_sky.sky_material = _sky_material
	# Real time is required because animate() breathes the haze, and a real time
	# sky accepts EXACTLY ONE radiance size: 256. Anything else and the renderer
	# prints "Realtime Skies can only use a radiance size of 256", clamps to 256
	# anyway, and the setting was a lie. The size is therefore assigned FIRST,
	# and the process mode second: the same warning fires when a sky is switched
	# to real time while it is still carrying another size.
	_sky.radiance_size = Sky.RADIANCE_SIZE_256
	_sky.process_mode = Sky.PROCESS_MODE_REALTIME

	_environment = Environment.new()
	_environment.sky = _sky
	_holder.environment = _environment

	_build_sun()
	apply()

	# The time of day is carried by two flags, because the material emission
	# floors are baked into a cache that cannot follow a runtime change. Two flags
	# can disagree, so the disagreement is reported rather than rendered: a
	# daylight sky over night materials is a stadium whose concrete glows.
	if is_daylight() != Mats.daylight:
		push_warning(
			"SkyController: evening = %.2f but Mats.daylight = %s. Set both." %
			[evening, str(Mats.daylight)])


## Rebuilds the environment for the current `evening` value.
func apply() -> void:
	if _environment == null:
		build()
		return

	var t: float = clampf(evening, 0.0, 1.0)

	_configure_sky(t)
	_configure_sun(t)
	_configure_tonemap(t)
	_configure_ambient(t)
	_configure_fog(t)
	_configure_glow(t)
	_configure_ao(t)
	_configure_adjustments(t)

	# Push the animated values once so a single apply() with no animate() still
	# produces the final look.
	animate(0.0)


## Slow drift of the haze, called every frame.
func animate(delta: float) -> void:
	if _environment == null or _sky_material == null:
		return
	_time += delta

	# Sodium discharge lamps never sit perfectly still. The flicker is applied
	# to the stored base value, not to the current one, so it cannot compound,
	# and its depth is faded to zero by the daylight: the sun does not flicker.
	var flicker: float = 1.0 + _flicker_amount * (
		0.62 * sin(_time * _FLICKER_A) + 0.38 * sin(_time * _FLICKER_B + 2.1)
	)
	_sky_material.sky_energy_multiplier = _sky_energy_base * flicker
	# The glow above the stands warms and cools as the lamps breathe. Same rule:
	# always derived from the base colour, and again faded out by daylight.
	_sky_material.sky_horizon_color = _horizon_base.lerp(
		Color(_horizon_base.r * 1.18, _horizon_base.g * 1.06, _horizon_base.b * 0.9, 1.0),
		(0.5 + 0.5 * sin(_time * _FLICKER_A * 0.5)) * (_flicker_amount / maxf(_FLICKER_DEPTH, 0.001))
	)

	# The haze itself drifts: density breathes very slightly and the whole sky is
	# rotated a fraction of a degree per second, which makes the horizon glow
	# slide behind the stands rather than sit painted on.
	if _environment.volumetric_fog_enabled:
		var breath: float = 1.0 + 0.12 * sin(_time * 0.23 + 0.7)
		_environment.volumetric_fog_density = _volume_density_base * breath
	if _sky_drift > 0.0:
		_environment.sky_rotation = Vector3(0.0, wrapf(_time * _sky_drift, 0.0, TAU), 0.0)


## --------------------------------------------------------------------------
## Internals
## --------------------------------------------------------------------------

## The scene keeps its WorldEnvironment as a sibling of this node.
func _find_holder() -> WorldEnvironment:
	var parent := get_parent()
	if parent != null:
		for child in parent.get_children():
			if child is WorldEnvironment:
				return child as WorldEnvironment
	# Fall back to a previously created child of our own, so a second build()
	# after a free and re add does not stack duplicates.
	for own_child in get_children():
		if own_child is WorldEnvironment:
			return own_child as WorldEnvironment
	return null


## Blends the night value, the dusk value and the daylight value over the two
## halves of `evening`, so the whole range is a continuous look rather than a
## switch with two positions.
func _blend(night_value: Color, dusk_value: Color, day_value: Color, t: float) -> Color:
	if t <= 0.5:
		return night_value.lerp(dusk_value, clampf(t * 2.0, 0.0, 1.0))
	return dusk_value.lerp(day_value, clampf((t - 0.5) * 2.0, 0.0, 1.0))


func _blendf(night_value: float, dusk_value: float, day_value: float, t: float) -> float:
	if t <= 0.5:
		return lerpf(night_value, dusk_value, clampf(t * 2.0, 0.0, 1.0))
	return lerpf(dusk_value, day_value, clampf((t - 0.5) * 2.0, 0.0, 1.0))


## The key light. A DirectionalLight3D on a Node parent is legal: a Node3D whose
## parent carries no transform simply becomes its own root, which is exactly what
## a sun wants.
func _build_sun() -> void:
	for child in get_children():
		if child is DirectionalLight3D:
			_sun = child as DirectionalLight3D
			return
	_sun = DirectionalLight3D.new()
	_sun.name = "Sun"
	add_child(_sun)


func _configure_sun(t: float) -> void:
	if _sun == null:
		return
	# Basis.looking_at points local -Z along the given direction, and -Z is where
	# a DirectionalLight3D shines. Computed rather than look_at() so apply() works
	# before the node is in a tree.
	_sun.transform = Transform3D(
		Basis.looking_at(_SUN_DIRECTION.normalized(), Vector3.UP), Vector3.ZERO)

	# Night keeps a whisper of moonlight rather than nothing at all: with the
	# pylons aimed at the penalty area, a true zero here leaves the far half of
	# the pitch with no key at all.
	_sun.light_energy = _blendf(0.06, 0.55, 2.80, t)
	_sun.light_color = Palette.SUNLIGHT.lerp(Color(0.62, 0.72, 1.0, 1.0),
		clampf(1.0 - t * 1.6, 0.0, 1.0))
	_sun.light_specular = 1.0
	_sun.light_bake_mode = Light3D.BAKE_DISABLED
	# The disc itself is drawn into the procedural sky, which also gives the sky
	# gradient its warm side. Angular distance is the penumbra control: with the
	# project's soft shadow filter at its highest quality this is what makes a
	# shadow soften as it runs away from the object casting it.
	_sun.light_angular_distance = _SUN_ANGULAR_SIZE
	_sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY

	# Shadows only when there is a sun worth casting them.
	_sun.shadow_enabled = t >= DAYLIGHT_THRESHOLD
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_2_SPLITS
	_sun.directional_shadow_max_distance = _SHADOW_DISTANCE
	_sun.directional_shadow_split_1 = _SHADOW_SPLIT
	_sun.directional_shadow_fade_start = 0.85
	# Bias is fought against the grazing angle of a low sun: too little and the
	# turf shadow acnes, too much and the keeper's feet float. Normal bias does
	# most of the work, which is what it is for on a near flat receiver.
	_sun.shadow_bias = 0.02
	_sun.shadow_normal_bias = 0.5
	_sun.shadow_blur = 1.1
	# Shadows do not darken the fog: a shadow volume across a stadium is not a
	# thing the eye expects, and it costs a froxel pass.
	_sun.light_volumetric_fog_energy = 0.0


func _configure_sky(t: float) -> void:
	_environment.background_mode = Environment.BG_SKY
	# This multiplier scales the sky where it is DRAWN, and not the radiance the
	# ambient integrates. That separation is the whole reason it exists, and the
	# daylight pair below is now driven the OTHER WAY ROUND from the first pass.
	#
	# It used to sit at 1.45 over a sky energy of 1.25, which lifted the drawn sky
	# and left the fill alone. But the fill was the thing that was short: the bowl
	# in the shooter's view is lit by nothing else, since the sun rakes across it
	# and the stands cast no shadows. So the sky energy went to 1.95 and this came
	# down to 0.94 to match. Their product is 1.83 against the old 1.81, so the
	# drawn sky is the same afternoon blue it was tuned to be, pixel for pixel,
	# while the radiance the stands and the underside of the crossbar integrate is
	# half again what it was.
	_environment.background_energy_multiplier = _blendf(1.0, 1.0, 0.94, t)
	_environment.sky_rotation = Vector3.ZERO

	_sky_material.sky_top_color = _blend(
		Palette.SKY_NIGHT_TOP, _DUSK_TOP, Palette.SKY_DAY_TOP, t)
	_horizon_base = _blend(
		Palette.SKY_NIGHT_HORIZON, _DUSK_HORIZON, Palette.SKY_DAY_HORIZON, t)
	_sky_material.sky_horizon_color = _horizon_base
	# At night a low curve crushes the sodium glow into a band just above the
	# stands, which is what a city glow looks like from inside a bowl. In daylight
	# the gradient is the whole dome and wants to be broad.
	_sky_material.sky_curve = _blendf(0.08, 0.24, 0.42, t)
	# THE AMBIENT LEVEL KNOB IN DAYLIGHT. See the class comment: with the sky
	# contribution at 1.0 this multiplier, and not `ambient_light_energy`, is what
	# decides how hard the sky fills the shadows. Raised for the stadium bowl, which
	# the sun only grazes; `background_energy_multiplier` above was lowered by the
	# reciprocal so the sky the player SEES did not move at all.
	_sky_energy_base = _blendf(0.5, 1.7, 1.95, t)
	_sky_material.sky_energy_multiplier = _sky_energy_base

	# The ground half of the dome is never seen (the pitch and the stands hide
	# it) but it IS half of what the sky ambient integrates, so in daylight it
	# carries the green bounce off the turf that fills the underside of the
	# keeper and of the crossbar.
	_sky_material.ground_bottom_color = _blend(
		Color(0.012, 0.013, 0.016, 1.0),
		Color(0.030, 0.032, 0.030, 1.0),
		Color(0.075, 0.105, 0.062, 1.0), t)
	_sky_material.ground_horizon_color = _blend(
		Palette.SKY_NIGHT_HORIZON.darkened(0.55),
		_DUSK_HORIZON.darkened(0.55),
		Color(0.230, 0.270, 0.245, 1.0), t)
	_sky_material.ground_curve = _blendf(0.03, 0.1, 0.16, t)
	_sky_material.ground_energy_multiplier = _blendf(0.25, 0.5, 0.85, t)

	# Cloud. `sky_cover` is ADDED to the gradient above, and `sky_cover_modulate`
	# is what scales it, so fading the modulate to black is how the night gets a
	# bare sky: the same texture stays bound and costs nothing to leave there.
	# The clouds are part of the sky radiance, so they also warm the ambient a
	# little, which is correct and is why the fill was tuned with them present.
	if _sky_material.sky_cover == null:
		_sky_material.sky_cover = Tex.clouds()
	var cover: float = _blendf(0.0, 0.25, 1.0, t)
	_sky_material.sky_cover_modulate = Color(cover, cover, cover, 1.0)

	# The sun disc. Small and hard edged, because the only reason it exists is to
	# give the sky a warm side and a believable highlight if a camera ever swings
	# past it. sun_angle_max is degrees of halo around the disc.
	_sky_material.sun_angle_max = _blendf(1.0, 6.0, 9.0, t)
	_sky_material.sun_curve = _blendf(0.05, 0.1, 0.14, t)

	# Only the sodium night has anything to drift.
	_sky_drift = _blendf(0.0035, 0.0015, 0.0, t)


func _configure_tonemap(t: float) -> void:
	_environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	# White is where the shoulder ends. At night it sits just above 1 so the few
	# highlights roll off fast; in daylight it is pushed well out, because the
	# frame now contains a sky, sunlit white paint and a white ball, and they all
	# have to come out bright while still holding their shading. Bring this back
	# towards 1 and the lines, the posts and the ball merge into one flat sheet.
	_environment.tonemap_white = _blendf(1.1, 1.25, 1.70, t)
	# LOWER in daylight than at night, which is the right way round: the scene
	# carries an order of magnitude more light, so the tonemap's job changes from
	# lifting a dark frame to holding a bright one off the ceiling. Tuned on a
	# rendered frame so the lit turf sits in the upper middle of the range and the
	# painted lines stay clearly under the clip.
	_environment.tonemap_exposure = _blendf(0.92, 0.80, 0.58, t)


func _configure_ambient(t: float) -> void:
	_environment.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	_environment.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	# ORDER MATTERS, AND SO DOES WHICH KNOB IS BEING DRIVEN.
	#
	# While the sky contribution is 1.0 the two lines below it are completely
	# inert. That is DELIBERATE in daylight: the fill is the sky, and its level is
	# `sky_energy_multiplier`, set in _configure_sky. At night the contribution is
	# dropped to 0.2 first and only then do the explicit colour and energy below
	# reach the shadowed side of the keeper.
	_environment.ambient_light_sky_contribution = _blendf(0.2, 0.6, 1.0, t)
	_environment.ambient_light_color = _blend(
		Palette.AMBIENT_NIGHT, _DUSK_AMBIENT, Palette.AMBIENT_DAY, t)
	_environment.ambient_light_energy = _blendf(0.55, 1.15, 1.6, t)

	# Every global illumination feature stays off. The sun plus a sky ambient is
	# the entire lighting budget of this game, and SDFGI over a stadium bowl would
	# cost more than everything else in the frame put together.
	_environment.sdfgi_enabled = false
	_environment.ssil_enabled = false
	_environment.ssr_enabled = false


func _configure_fog(t: float) -> void:
	var day: float = clampf((t - 0.5) * 2.0, 0.0, 1.0)

	# --- Depth fog: distance only, and it starts well past the goal. ---
	_environment.fog_enabled = true
	_environment.fog_mode = Environment.FOG_MODE_DEPTH
	_environment.fog_light_color = _blend(
		Palette.FOG_NIGHT, _DUSK_FOG, Palette.FOG_DAY, t)
	_environment.fog_light_energy = 1.0
	# In daylight the sun scatters forward through the haze, so looking down sun
	# the far stand washes out more than looking up sun. At night there is no sun
	# and no lobe to fake.
	_environment.fog_sun_scatter = _blendf(0.0, 0.06, 0.18, t)
	# MUCH thinner in daylight. The night value is tuned to swallow the far stand
	# into the dark; the same density under a bright sky is a grey sheet over the
	# whole bowl that fights every other decision in this file.
	_environment.fog_density = _blendf(0.85, 0.6, 0.16, t)
	_environment.fog_aerial_perspective = _blendf(0.12, 0.2, 0.42, t)
	# At night the sky is already the right colour and fogging it would grey out
	# the dark the lamps depend on. In daylight the fog IS the sky colour, so a
	# little sky affect ties the far stand into the horizon instead of cutting it
	# out against it.
	_environment.fog_sky_affect = _blendf(0.0, 0.1, 0.3, t)
	_environment.fog_depth_begin = _FOG_BEGIN
	_environment.fog_depth_end = _FOG_END
	# Curve above 1 keeps the near half of that range almost clear, so the fade
	# happens deep in the stands rather than across the penalty area.
	_environment.fog_depth_curve = 1.5
	# Pure depth fog: no height term, otherwise the ball would fade as it rose.
	_environment.fog_height = 0.0
	_environment.fog_height_density = 0.0

	# --- Volumetric fog: only ever there to make the light cones visible. ---
	# There are no cones in daylight, so the whole froxel grid is switched off
	# rather than turned down: it is the single largest saving available here.
	_environment.volumetric_fog_enabled = day < 0.5
	if not _environment.volumetric_fog_enabled:
		return
	_volume_density_base = _blendf(0.006, 0.0025, 0.0, t)
	_environment.volumetric_fog_density = _volume_density_base
	_environment.volumetric_fog_albedo = Palette.FOG_NIGHT
	_environment.volumetric_fog_emission = Color(0.0, 0.0, 0.0, 1.0)
	_environment.volumetric_fog_emission_energy = 0.0
	_environment.volumetric_fog_gi_inject = 0.0
	# Slightly forward scattering, so a cone seen towards its lamp is brighter
	# than the same cone seen from behind.
	_environment.volumetric_fog_anisotropy = 0.28
	_environment.volumetric_fog_length = 96.0
	_environment.volumetric_fog_detail_spread = 2.0
	_environment.volumetric_fog_ambient_inject = 0.15
	_environment.volumetric_fog_sky_affect = 0.0
	# Reprojection is what makes this affordable: it lets the froxel grid be
	# sampled sparsely and accumulated over frames.
	_environment.volumetric_fog_temporal_reprojection_enabled = true
	_environment.volumetric_fog_temporal_reprojection_amount = 0.9


func _configure_glow(t: float) -> void:
	_environment.glow_enabled = true
	_environment.glow_normalized = false
	_environment.glow_intensity = _blendf(0.7, 0.6, 0.42, t)
	_environment.glow_strength = 1.0
	_environment.glow_mix = 0.05
	_environment.glow_bloom = 0.0
	_environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_SCREEN
	# THE WHOLE POINT OF THE THRESHOLD, and it has to move with the hour.
	#
	# At night the lamp faces emit at 6 and cross it while painted lines at albedo
	# 0.7 never do. Under a daylight key that same painted line is ten times
	# brighter than it was, so a threshold of 1.35 would catch the lines, the
	# posts, the ball and most of the turf, and the frame would come back as soup.
	# In daylight it sits above the brightest LIT surface in the game: only the
	# sun disc in the sky and a specular hit on the ball or the posts get through.
	_environment.glow_hdr_threshold = _blendf(1.35, 1.7, 3.1, t)
	_environment.glow_hdr_scale = 2.0
	_environment.glow_hdr_luminance_cap = 12.0

	# Only the wide levels: a broad soft halo, no tight fringe on every
	# contrasting edge. set_glow_level() is ZERO based even though the inspector
	# labels the same slots "glow_levels/1" to "glow_levels/7", so index 0 here is
	# level 1 there and index 7 is out of bounds.
	_environment.set_glow_level(0, 0.0)   # level 1, sharpest
	_environment.set_glow_level(1, 0.1)   # level 2
	_environment.set_glow_level(2, 0.5)   # level 3
	_environment.set_glow_level(3, 1.0)   # level 4
	_environment.set_glow_level(4, 1.0)   # level 5
	_environment.set_glow_level(5, 0.6)   # level 6
	_environment.set_glow_level(6, 0.25)  # level 7, widest


func _configure_ao(t: float) -> void:
	# Subtle: its job is the contact shadow where a boot meets the turf and the
	# crease under the crossbar, not a dirty ring around everything.
	_environment.ssao_enabled = true
	_environment.ssao_radius = 0.7
	# Turned DOWN in daylight. Screen space occlusion attenuates the ambient
	# term, and the daylight ambient is now the brightest fill in the game: the
	# same intensity that read as a whisper at night reads as soot under the
	# stands and around every seat in the ground.
	_environment.ssao_intensity = _blendf(1.1, 1.0, 0.75, t)
	_environment.ssao_power = 1.6
	_environment.ssao_detail = 0.4
	_environment.ssao_horizon = 0.07
	_environment.ssao_sharpness = 0.98
	# Direct light is allowed to erase almost all of it, which is physically the
	# right call and stops the lit side of the keeper looking grimy.
	_environment.ssao_light_affect = 0.1
	_environment.ssao_ao_channel_affect = 0.0


func _configure_adjustments(t: float) -> void:
	_environment.adjustment_enabled = true
	_environment.adjustment_brightness = 1.0
	# Contrast is applied by Godot as mix(0.5, colour, contrast), so anything
	# above 1 pushes the bottom of the range down towards the clip. That was
	# affordable at night, where almost nothing lived down there on purpose. In
	# daylight the shadows under the roof and inside the net DO live down there
	# and must keep their detail, so contrast is held at 1.
	_environment.adjustment_contrast = _blendf(1.06, 1.02, 1.0, t)
	# Saturation is the one place a small lift is worth it in daylight: it is what
	# takes the turf from a correct green to a vivid one, and it costs nothing
	# because no albedo in the game is near enough to the ceiling to posterise.
	_environment.adjustment_saturation = _blendf(1.08, 1.0, 1.16, t)

	# The lamp flicker only exists while there are lamps. Fully faded by dusk.
	_flicker_amount = _blendf(_FLICKER_DEPTH, _FLICKER_DEPTH * 0.4, 0.0, t)
