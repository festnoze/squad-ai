class_name KeeperInput
extends RefCounted
## The goalkeeper when the PLAYER is the one holding him (contract 2.12a).
##
## Pure and static, no nodes, dependencies limited to Field and KeeperBrain. This
## is ShotModel's opposite number for the other side of a DUEL: it turns a mouse
## aim, a moment of commitment and a position on the goal line into a dive, and it
## answers the only question the player asks during the run up, which is
## "if I go NOW, what do I still cover?".
##
## THE ARITHMETIC IS THE AI KEEPER'S, AND IT IS CRUEL
##
## A penalty takes 0.42 s to arrive, a human reflex 0.2 s, and a dive to the post
## 0.6 s. Those three numbers do not fit inside one another, and that IS the mode:
## you cannot wait until you know. The player has to bet early on an incomplete
## read, exactly as KeeperBrain.read_cues has always had to. The earlier he
## commits the more he covers; the longer he waits the more he knows and the less
## of the goal he can still reach.
##
## Nothing new is modelled for that trade. THE ENVELOPE IS A CONSEQUENCE OF
## KeeperBrain.dive_time_needed, and therefore of the reach, the dive speed and
## the extension time of the chosen level. Both keepers in a duel dive with the
## same body, and an envelope that drifted away from those curves would be a lie
## drawn on the screen.
##
## THE CLOCK
##
## `t` is seconds RELATIVE TO THE STRIKE, negative during the run up. It is
## Keeper.pose_log's clock and read_cues' commit_time clock, not a third one. A
## commit at t = -0.18 is a keeper leaving two tenths before contact, and it is
## perfectly legal.
##
## `arrival` is the instant, on that same clock, at which the ball will cross the
## line. Before the strike NOBODY KNOWS IT and the caller passes NOMINAL_FLIGHT.
## After the strike the player can SEE the ball, so handing over the real
## remaining flight time is honest, and it is what makes the envelope collapse far
## faster on a driven penalty than on a scuffed one: precisely the difference the
## player has to learn to read.
##
## WHAT IS NOT CHARGED, AND WHY
##
## KeeperBrain.reaction_time is NOT subtracted from the time available. The brain
## pays it because it decides at an instant when the body has not moved yet; the
## player has already reacted by the time he presses, and he paid his tenth of a
## second out of his own nerves. Charging it here would bill him twice. This is
## written down because the next person to read this file will want to add it in
## the name of symmetry, and that would be the wrong symmetry.

## Seconds a penalty is assumed to take from contact to the goal line for as long
## as nobody can know better, which is the whole of the run up. Not invented: it
## is what the project's own model gives for a strike at TakerAi.POWER_MEAN over
## the eleven metres.
const NOMINAL_FLIGHT := 0.42

## How far along his line the player may shuffle, metres either side of the
## middle. The SAME bound KeeperBrain.line_dance lives under, so the AI keeper and
## the player keeper occupy one strip of turf and not two.
const LINE_LIMIT := 0.9
## Metres per second that shuffle travels at.
const LINE_SPEED := 1.35

# --- Reticle mapping ---------------------------------------------------------
#
# Restated rather than imported: this module may not depend on ShotModel (see the
# dependency order of contract 2). tests/test_keeper_input.gd round trips these
# three numbers against ShotModel.aim_point, so if the taker's reticle is ever
# remapped that check fails instead of the two ends of a duel quietly aiming in
# two different languages.
const _AIM_SPAN_X := 4.40         # Field.GOAL_HALF plus ShotModel's side margin
const _AIM_BASE_Y := 0.11         # Field.BALL_RADIUS
const _AIM_TOP_Y := 3.04          # Field.GOAL_HEIGHT plus ShotModel's top margin

## Metres of goal swept by one pixel of mouse travel at sensitivity 1. Applied in
## METRES and only then converted into each axis of the reticle, so the pointer
## feels the same going sideways as it does going up: the reticle bands are not
## square, the goal is.
const _AIM_METRES_PER_PIXEL := 0.0142

# --- Where the dive is measured from -----------------------------------------

## Height of the point the reach envelope radiates from. The keeper's own home
## target: KeeperBrain reads a blind guess at this height and match_state's
## simulated keeper stands at it, so the drawn envelope is centred where the body
## actually is rather than on an invented pivot.
const _PIVOT_Y := 1.25

# --- Coarse reading ----------------------------------------------------------
#
# The same thresholds KeeperBrain.choose_dive reports a dive with, kept here so a
# dive chosen by a human and a dive chosen by the brain are described in the same
# words by the body, the crowd, the audio and the replay. Guarded against drift by
# a cross check in the suite, which asks choose_dive itself.
const _SIDE_BAND := 0.95
const _HEIGHT_LOW_CUT := 0.85
const _HEIGHT_HIGH_CUT := 1.60

# --- Envelope sampling -------------------------------------------------------

## Grid the mouth is measured on by coverage(). Odd counts on purpose, so the dead
## centre of the goal and the mid height are both sample points.
const _COVER_COLS := 19
const _COVER_ROWS := 9
## Bisection passes used by reach_outline. Twelve halvings of a 4 m ray land
## inside a millimetre, which is far under the width of the stroke that draws it.
const _OUTLINE_PASSES := 12
const _OUTLINE_MIN_SAMPLES := 8
const _OUTLINE_MAX_SAMPLES := 256


## World point on the goal plane a normalized reticle asks for. `aim.x` -1..1 and
## `aim.y` 0..1 span the same bands ShotModel.aim_point reads, so the two ends of
## a duel aim in one language.
## Unlike the taker, the keeper is CLAMPED inside the frame: a dive aimed over the
## bar is not a decision, it is a lost input.
static func dive_target(aim: Vector2) -> Vector3:
	var ax := clampf(_finite_or(aim.x, 0.0), -1.0, 1.0)
	var ay := clampf(_finite_or(aim.y, 0.5), 0.0, 1.0)
	var x := ax * _AIM_SPAN_X
	var y := _AIM_BASE_Y + ay * (_AIM_TOP_Y - _AIM_BASE_Y)
	return Vector3(
		clampf(x, -mouth_half_x(), mouth_half_x()),
		clampf(y, mouth_floor_y(), mouth_ceiling_y()),
		0.0)


## Moves the reticle by one frame of mouse travel and clamps it back into the
## band above. `sensitivity` is Game.mouse_sensitivity.
static func move_aim(aim: Vector2, mouse_delta: Vector2, sensitivity: float) -> Vector2:
	var gain := clampf(_finite_or(sensitivity, 1.0), 0.05, 8.0) * _AIM_METRES_PER_PIXEL
	var dx := _finite_or(mouse_delta.x, 0.0) * gain / _AIM_SPAN_X
	# Screen y grows downwards while the reticle grows upwards.
	var dy := -_finite_or(mouse_delta.y, 0.0) * gain / (_AIM_TOP_Y - _AIM_BASE_Y)
	return Vector2(
		clampf(_finite_or(aim.x, 0.0) + dx, -1.0, 1.0),
		clampf(_finite_or(aim.y, 0.5) + dy, 0.0, 1.0))


## Seconds of dive left to a keeper who pushes off at `t` for a ball that reaches
## the line at `arrival`. Never negative.
static func time_available(t: float, arrival: float) -> float:
	var now := _finite_or(t, 0.0)
	var end := _finite_or(arrival, NOMINAL_FLIGHT)
	return maxf(end - now, 0.0)


## Can a keeper standing at `line_x` still have a glove ON `target` if he pushes
## off now? This is exactly
## `KeeperBrain.dive_time_needed(target, line_x, level) <= time_available(t, arrival)`,
## and it is the ONE rule everything else in this module is drawn from.
static func reachable(target: Vector3, line_x: float, t: float, arrival: float, level: int) -> bool:
	return _needed(target, line_x, level) <= time_available(t, arrival)


## Seconds to spare on that dive. Positive means reachable with room, negative is
## how late the keeper would be. The HUD colours the dive reticle with it.
##
## Unclamped on purpose, unlike time_available: a keeper who is three tenths late
## should be told he is three tenths late and not merely that he is late. The two
## still agree on the sign, because dive_time_needed is strictly positive: the arm
## swing alone costs time even for a ball hanging in front of his chest.
static func margin(target: Vector3, line_x: float, t: float, arrival: float, level: int) -> float:
	var end := _finite_or(arrival, NOMINAL_FLIGHT)
	var now := _finite_or(t, 0.0)
	return (end - now) - _needed(target, line_x, level)


## The outline of everything still reachable, as a CLOSED ring of `samples` points
## on the goal plane, for the HUD to stroke. Found by bisecting `margin` along
## rays out of the keeper, so the drawn envelope IS the rule and cannot drift away
## from it. Empty when nothing is reachable any more.
##
## Bisection assumes the margin falls as the ray leaves the keeper, which it does:
## dive_time_needed grows with the ground the pelvis has to cover and with the
## height the glove has to climb to, and both grow along a ray. The clamp to the
## mouth is what makes the ring a picture of the GOAL rather than of the keeper.
static func reach_outline(line_x: float, t: float, arrival: float, level: int, samples: int = 48) -> PackedVector3Array:
	var ring := PackedVector3Array()
	var count := clampi(samples, _OUTLINE_MIN_SAMPLES, _OUTLINE_MAX_SAMPLES)
	var origin := _pivot(line_x)
	# The pivot is where the body IS, so the whole ring is measured from that same
	# clamped x. Reading the raw argument here and the clamped one there would draw
	# an envelope belonging to a keeper standing somewhere nobody is.
	var from_x := origin.x
	if margin(origin, from_x, t, arrival, level) < 0.0:
		return ring
	for i in count:
		var angle := TAU * float(i) / float(count)
		var dir := Vector2(cos(angle), sin(angle))
		var far := _mouth_exit(origin, dir)
		if far <= 0.0:
			ring.append(origin)
			continue
		if margin(_along(origin, dir, far), from_x, t, arrival, level) >= 0.0:
			ring.append(_along(origin, dir, far))
			continue
		var low := 0.0
		var high := far
		for _pass in _OUTLINE_PASSES:
			var mid := 0.5 * (low + high)
			if margin(_along(origin, dir, mid), from_x, t, arrival, level) >= 0.0:
				low = mid
			else:
				high = mid
		ring.append(_along(origin, dir, low))
	return ring


## Fraction of the goal mouth still reachable, 0..1. One number, so the HUD can
## shrink a ring with it and the tests can assert the property that matters: it
## FALLS as `t` rises, at every level and from every line position.
##
## Counted on a fixed grid rather than integrated from the outline, and that is
## what makes the fall monotone for free: the grid does not move, only the time
## budget does, and a point that has dropped out of the envelope never comes back.
static func coverage(line_x: float, t: float, arrival: float, level: int) -> float:
	var budget := time_available(t, arrival)
	var inside := 0
	var total := 0
	for col in _COVER_COLS:
		var fx := 0.0 if _COVER_COLS <= 1 else float(col) / float(_COVER_COLS - 1)
		var x := lerpf(-mouth_half_x(), mouth_half_x(), fx)
		for row in _COVER_ROWS:
			var fy := 0.0 if _COVER_ROWS <= 1 else float(row) / float(_COVER_ROWS - 1)
			var y := lerpf(mouth_floor_y(), mouth_ceiling_y(), fy)
			total += 1
			if _needed(Vector3(x, y, 0.0), line_x, level) <= budget:
				inside += 1
	if total <= 0:
		return 0.0
	return float(inside) / float(total)


## One frame of line dance. `input` is -1..1 from the keyboard or the mouse,
## travelling at LINE_SPEED and bounded to LINE_LIMIT. Returns the new x.
static func line_step(line_x: float, input: float, delta: float) -> float:
	var here := clampf(_finite_or(line_x, 0.0), -LINE_LIMIT, LINE_LIMIT)
	var push := clampf(_finite_or(input, 0.0), -1.0, 1.0)
	var dt := clampf(_finite_or(delta, 0.0), 0.0, 0.5)
	return clampf(here + push * LINE_SPEED * dt, -LINE_LIMIT, LINE_LIMIT)


## The dive the player just launched. Called ONCE, the frame he commits.
## Returns {"target": Vector3, "side": int, "height": int, "committed_at": float,
##          "reachable": bool, "coverage": float, "margin": float}
## `target` is the continuous point the pose is built from and the only one of the
## three that changes it; `side` and `height` are its coarse reading, for the
## body, the crowd, the audio and the replay, exactly as KeeperBrain.choose_dive
## reports them. The dictionary is shaped so that `Keeper` can be driven from it
## without knowing whether a brain or a human chose it.
static func commit(aim: Vector2, line_x: float, t: float, arrival: float, level: int) -> Dictionary:
	var target := dive_target(aim)
	var x := clampf(_finite_or(line_x, 0.0), -LINE_LIMIT, LINE_LIMIT)
	var when := _finite_or(t, 0.0)
	return {
		"target": target,
		"side": coarse_side(target),
		"height": coarse_height(target),
		"committed_at": when,
		"reachable": reachable(target, x, when, arrival, level),
		"coverage": coverage(x, when, arrival, level),
		"margin": margin(target, x, when, arrival, level),
	}


## Coarse reading of a continuous target, for the body and the audio. The same
## thresholds KeeperBrain reads it with, kept in one place so a dive reported by
## the two modules is reported the same way.
static func coarse_side(target: Vector3) -> int:
	var x := _finite_or(target.x, 0.0)
	if x > _SIDE_BAND:
		return KeeperBrain.SIDE_RIGHT
	if x < -_SIDE_BAND:
		return KeeperBrain.SIDE_LEFT
	return KeeperBrain.SIDE_CENTRE


static func coarse_height(target: Vector3) -> int:
	var y := _finite_or(target.y, _PIVOT_Y)
	if y < _HEIGHT_LOW_CUT:
		return KeeperBrain.HEIGHT_LOW
	if y > _HEIGHT_HIGH_CUT:
		return KeeperBrain.HEIGHT_HIGH
	return KeeperBrain.HEIGHT_MID


# --- The mouth, as the envelope sees it --------------------------------------
#
# A ball CENTRE at these bounds is a ball whose whole body is still inside the
# frame, which is the same rule Field.is_inside_mouth applies. Public because the
# HUD strokes the same rectangle the coverage is counted on, and two rectangles
# that disagreed by a ball radius would make the drawn ring look wrong at the
# posts.

static func mouth_half_x() -> float:
	return maxf(Field.GOAL_HALF - Field.BALL_RADIUS, 0.1)


static func mouth_floor_y() -> float:
	return Field.BALL_RADIUS


static func mouth_ceiling_y() -> float:
	return maxf(Field.GOAL_HEIGHT - Field.BALL_RADIUS, Field.BALL_RADIUS + 0.1)


# --- Private helpers ---------------------------------------------------------

## The one call into KeeperBrain, funnelled through here so there is exactly one
## place where the two keepers of a duel could ever stop sharing a body.
static func _needed(target: Vector3, line_x: float, level: int) -> float:
	var x := _finite_or(line_x, 0.0)
	var safe := Vector3(
		_finite_or(target.x, 0.0),
		_finite_or(target.y, _PIVOT_Y),
		0.0)
	var seconds: float = KeeperBrain.dive_time_needed(safe, x, level)
	if not is_finite(seconds):
		return INF
	return maxf(seconds, 0.0)


static func _pivot(line_x: float) -> Vector3:
	return Vector3(clampf(_finite_or(line_x, 0.0), -LINE_LIMIT, LINE_LIMIT), _PIVOT_Y, 0.0)


static func _along(origin: Vector3, dir: Vector2, distance: float) -> Vector3:
	return Vector3(origin.x + dir.x * distance, origin.y + dir.y * distance, 0.0)


## Distance from `origin` to the edge of the mouth rectangle along `dir`. Zero
## when the ray leaves immediately, which only happens if the pivot is already on
## the boundary.
static func _mouth_exit(origin: Vector3, dir: Vector2) -> float:
	var best := INF
	best = minf(best, _slab(origin.x, dir.x, -mouth_half_x(), mouth_half_x()))
	best = minf(best, _slab(origin.y, dir.y, mouth_floor_y(), mouth_ceiling_y()))
	if not is_finite(best):
		return 0.0
	return maxf(best, 0.0)


## How far a ray at `here` moving at `step` per unit stays inside [low, high].
static func _slab(here: float, step: float, low: float, high: float) -> float:
	if absf(step) < 1e-9:
		return INF
	if step > 0.0:
		return (high - here) / step
	return (low - here) / step


static func _finite_or(value: float, fallback: float) -> float:
	if is_nan(value) or is_inf(value):
		return fallback
	return value
