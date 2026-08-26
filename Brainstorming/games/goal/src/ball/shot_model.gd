class_name ShotModel
extends RefCounted
## Turns the shooter's intent into a launch velocity and a spin vector.
##
## Binding design principle: THE RETICLE SHOWS WHERE THE BALL WOULD GO WITHOUT
## SPIN. resolve() therefore solves the launch direction with Aero.aim_velocity()
## for a spin free flight, and only then attaches the spin the player dialled in.
## The ball bends away from the reticle by an amount the player learns to predict
## and that the HUD draws live, instead of the reticle quietly lying about the
## outcome. Anything else would either make the aim assist useless (the ball never
## goes where the cross is) or the spin invisible (the solver would cancel it).
##
## Everything here is pure and static, so the whole feel of the game is testable
## without a scene tree, and a replay of a seed is bit for bit reproducible.
##
## TUNING, and why these numbers
##
## speed_for_power: 14 m/s (50 km/h, a pass) to 34 m/s (122 km/h, a real penalty
## from a professional). The curve is 25 % linear plus 75 % of 1 - (1 - p)^1.8,
## which is strictly increasing (slope never drops under 0.25 of the linear one,
## so the bar never feels dead) yet clearly concave. Concretely the last 20 % of
## the bar buys 1.8 m/s while the middle 20 % buys 4.1 m/s: pushing the bar to
## the very top costs you accuracy for less than half the pace you would have
## bought in the middle. Maximum power is a real trade off, which is the point.
##
## contact_quality: flat 1.0 while the release sits inside the sweet window
## (SWEET_WIDTH = 0.11 either side of the marker), then a smoothstep down to
## exactly 0 at 0.20 from the centre. A miscue is a gradient, not a coin flip,
## but the gradient is STEEP, because timing the bar is the skill the game is
## about: at 0.135 off you keep 0.81 of a clean strike, at 0.15 you are down to
## 0.58, at 0.17 to 0.26, and past 0.20 there is nothing left at all. So the
## player gets a tenth of the bar either side of the marker for free, and then
## barely another tenth before the strike is a complete shank. The curve is still
## a smoothstep, so it is C1 and never a literal step, but it is a cliff.
##
## error_angle: the half angle of the spray cone, and the main punishment for a
## mistimed strike. Three numbers hold it up.
##
##   - A clean strike keeps a residual 0.06 deg (1.2 cm at 11 m) so no two shots
##     are ever pixel identical, far under the half degree budget.
##   - A total miscue at full power reaches 10.2 deg, which is 1.98 m of spray at
##     the 11 m of a penalty. That is a deliberate ceiling: missing a 7.32 m goal
##     from the spot while aiming dead centre needs atan(3.66 / 11) = 18.4 deg,
##     which is not a mishit but a shank into the stands and would feel like the
##     game cheating. 1.98 m instead means a scuffed shot aimed at the middle
##     often survives (slow, central, and therefore eaten by the keeper) while
##     anything aimed within two metres of a post or the bar is wrecked. Since a
##     corner is only ever 0.6 m from a post and 0.4 m under the bar, the corner
##     is exactly what a miscue can no longer buy, and playing safe down the
##     middle is what a player who does not trust his timing should do.
##   - The fall off exponent is 0.62, BELOW one, so the cone opens up violently
##     the moment the release leaves the window instead of forgiving the near
##     miss. Releasing 0.135 off already sprays 3.7 deg, that is 71 cm at 11 m,
##     which is more than the whole margin of a corner. That concavity is the
##     answer to "the power bar does not matter": now it does.
##
## The cone is also STRETCHED VERTICALLY by 2.25 and tilted up by 28 % of its
## radius on a miscue, because a scuffed football balloons, it does not bury
## itself in the turf. That asymmetry is where the last of the punishment comes
## from: the goal is 7.32 m wide and only 2.44 m tall, so height is what a
## mistimed strike can actually lose. And the strike loses 45 % of its pace and
## picks up as much as 130 rad/s of spin nobody asked for, so what does survive
## arrives slowly, spinning, and nowhere near where the reticle was pointing:
## exactly the ball a goalkeeper saves.
##
## spin_vector: 95 rad/s of curl and 75 rad/s of lift at full power, which is
## what a hard struck ball really carries (around 15 revolutions per second).
## Measured against Aero over a penalty, full curl bends the ball 66 cm sideways
## and full backspin floats it 51 cm above the reticle while full topspin drops
## it 65 cm below. Four glove widths of curve: enough to beat a keeper who
## committed early, not so much that the reticle becomes decorative.
##
## Determinism: every random draw comes from a RandomNumberGenerator seeded with
## rng_seed, in a fixed order, so the same inputs always produce byte identical
## outputs. tell_cues() has no seed at all and is a pure function of its inputs,
## with its bluff values coming from an integer hash of the quantised arguments.

const MIN_SPEED := 14.0
const MAX_SPEED := 34.0
## Half width of the clean contact window on the power bar.
const SWEET_WIDTH := 0.11

# --- Aim mapping -------------------------------------------------------------

## Metres of reticle travel outside each post at aim.x = +/- 1.
const _AIM_SIDE_MARGIN := 0.74
## Metres of reticle travel above the bar at aim.y = 1.
const _AIM_TOP_MARGIN := 0.60
## Sanity bound on the reticle. Shooting wide is legal, shooting at the corner
## flag is a caller bug, and an unbounded target breaks the aim solver.
const _AIM_LIMIT := 3.0
## The reticle lives on the goal line plane.
const _AIM_PLANE_Z := 0.0

# --- Power curve -------------------------------------------------------------

## Share of the power curve that stays linear, so the top of the bar still moves.
const _POWER_LINEAR := 0.25
## Exponent of the saturating part. Above 1 it is concave.
const _POWER_EXPONENT := 1.8

# --- Contact -----------------------------------------------------------------

## Distance from the sweet centre at which the quality has fallen to zero.
const _MISS_WIDTH := 0.20
## Below this quality the strike is reported as a miscue to the rest of the game.
const _MISCUE_LEVEL := 0.5
## Fraction of the pace lost by a completely mishit ball. A scuffed penalty
## really does arrive at walking pace: 34 m/s becomes 21, and 14 becomes 8.7,
## which is a ball the keeper has time to see, read and catch.
##
## Held at 0.45 rather than raised, and the reason is worth recording because it
## was tried. Taking more pace off looks like the obvious way to punish a mishit
## now that the keeper waits for the last responsible moment and spends the extra
## time reading rather than lying on the turf. It is not: a slower ball has to be
## lobbed to reach the goal at all, a lobbed ball sprayed vertically lands inside
## the frame more often than a driven one, and at 0.50 a full miscue aimed at a
## CORNER was framed as often as one aimed at the middle. That kills the property
## the whole contact model is built on, which is that playing safe down the middle
## is the right answer when you do not trust your timing.
const _MISCUE_SPEED_LOSS := 0.45
## Unintended spin a scuffed contact puts on the ball, rad/s per axis. The foot
## rakes across the ball instead of through it, so it leaves with a spin nobody
## asked for and a curve the shooter cannot predict.
const _MISCUE_SPIN := 78.0
## Upward tilt of the spray cone on a miscue, as a fraction of the cone radius.
const _MISCUE_LOFT := 0.28
## Vertical stretch of the spray cone on a miscue. A mistimed strike loses HEIGHT
## control far more than it loses direction: where the boot meets the ball is what
## decides the loft, and getting under it or on top of it is the classic way a
## penalty ends up in the stand behind the goal or bobbling into the turf. The
## goal is only 2.44 m tall and 7.32 m wide, so this asymmetry is also what lets a
## miscue be genuinely punished without ever being a sideways shank into the
## corner flag.
##
## Raised from 2.00 to 2.25 as the LAST couple of points of punishment for a
## mishit, and chosen over the two obvious alternatives on purpose. Widening the
## cone itself would need over twenty degrees to matter, which is a shank into the
## stand and reads as the game cheating. Taking more pace off lobs the ball and
## quietly makes a mishit CORNER easier to frame than a mishit centre, which is
## backwards. Ballooning it is the one that is both true to a scuffed football and
## aimed at the frame rather than at the goalkeeper.
const _MISCUE_VERTICAL := 2.25

# --- Error cone --------------------------------------------------------------

## Residual spray of a perfect strike, radians (0.060 deg).
const _ERROR_CLEAN := 0.001047
## Extra spray of a total miscue at full power, radians (10.2 deg, 1.98 m at the
## 11 m of a penalty). Sized to wreck a corner without shanking a centred shot
## out of a 7.32 m goal: see the tuning notes at the top of the file.
const _ERROR_MISCUE := 0.178000
## Shape of the fall off. BELOW 1: the cone opens up at once, so leaving the
## sweet window costs accuracy immediately instead of being quietly forgiven.
const _ERROR_EXPONENT := 0.62
## Spray multiplier at zero power, so a placed shot is a little more forgiving.
const _ERROR_POWER_FLOOR := 0.34

# --- Spin --------------------------------------------------------------------

## Peak curl, rad/s. A hard curled penalty measures around 90 rad/s (14 rev/s).
const _SIDE_SPIN_MAX := 95.0
## Peak backspin or topspin, rad/s.
const _LIFT_SPIN_MAX := 75.0
## Share of the peak spin already available at zero power: a soft placed ball can
## still be curled, it just travels slower.
const _SPIN_BASE := 0.55

# --- Aim solver --------------------------------------------------------------

## The signature carries no wind slot, so the model assumes the still air of a
## covered night stadium. Kept named rather than inlined so the day a wind is
## added to the contract there is exactly one line to change.
const _WIND := Vector3.ZERO
## Mean speed over a penalty as a fraction of the launch speed, used only by the
## fallback when the real solver reports no solution.
const _FALLBACK_DRAG := 0.82

# --- Body language -----------------------------------------------------------

## Even a legend never reads the aim perfectly before contact. What is left over
## is not noise, it is a DECOY (see below), so this ceiling is expensive: at 0.90
## a Legende was still being handed a bluff worth half a metre of goal on every
## penalty, which is more than a glove is wide. Since the keeper's dive stopped
## being quantised, half a metre of bluff is exactly half a metre of miss, and the
## ceiling had to come up to 0.94 for the top of the ladder to mean anything. The
## level still gates it: a Debutant reads 0.30 of 0.94 and is guessing.
const _MAX_TELL := 0.94
## Fidelity ceiling of the HEIGHT cue, applied instead of _MAX_TELL rather than on
## top of it, and deliberately still ABOVE it: a shooter can disguise which side
## he is going far more easily than whether he is going up or down. Height is the
## most honest thing a run up gives away: a body leaning
## back over a planted foot is going to lift the ball and a shooter stood right on
## top of it is going to drive it along the turf, and unlike the side of the goal
## there is no way to disguise it late. Before this cue existed the keeper had to
## guess the height of every penalty from the power alone, which read every hard
## shot as low and conceded every top corner for free.
const _LIFT_TELL := 0.98
## Each feint multiplies the fidelity of every read by this.
const _FEINT_MUDDLE := 0.55
## Power leak at zero power, and how much more a full blooded strike leaks.
const _POWER_LEAK_BASE := 0.30
const _POWER_LEAK_GAIN := 0.62

# --- Deterministic hash ------------------------------------------------------

## 30 bits, so the mixing multiplications stay far from the int64 overflow.
const _HASH_MASK := 0x3FFFFFFF
const _HASH_MUL_A := 0x27D4EB2D
const _HASH_MUL_B := 0x165667B1
const _HASH_SEED := 0x2545F49


## World point aimed at, from the normalized reticle. `aim.x` -1..1 spans the
## mouth plus a margin, `aim.y` 0..1 spans from the ground to the bar plus a
## margin. Values outside those bands are legal: that is how you shoot wide.
static func aim_point(aim: Vector2) -> Vector3:
	var ax := clampf(_finite_or(aim.x, 0.0), -_AIM_LIMIT, _AIM_LIMIT)
	var ay := clampf(_finite_or(aim.y, 0.5), -_AIM_LIMIT, _AIM_LIMIT)
	var span_x: float = Field.GOAL_HALF + _AIM_SIDE_MARGIN
	var base_y: float = Field.BALL_RADIUS
	var top_y: float = Field.GOAL_HEIGHT + _AIM_TOP_MARGIN
	return Vector3(ax * span_x, base_y + ay * (top_y - base_y), _AIM_PLANE_Z)


## Strike speed for a charged power in [0, 1]. Not linear: the top of the bar
## buys less speed than the middle, so maximum power is a real trade off.
static func speed_for_power(power: float) -> float:
	var p := clampf(_finite_or(power, 0.0), 0.0, 1.0)
	var saturating := 1.0 - pow(1.0 - p, _POWER_EXPONENT)
	var shaped := _POWER_LINEAR * p + (1.0 - _POWER_LINEAR) * saturating
	return MIN_SPEED + (MAX_SPEED - MIN_SPEED) * shaped


## Spin from the player's inputs. `side` -1..1 is the curl, `lift` -1..1 is
## backspin (positive, floats the ball) to topspin (negative, dips it).
##
## Axis convention, checked against Aero: the Magnus force is proportional to
## omega x v. For a ball leaving towards -Z, a spin of (0, +w, 0) pushes it
## towards -X, so a positive `side` (curl towards +X, the shooter's right) needs
## a negative y component. A spin of (+w, 0, 0) pushes it towards +Y, so positive
## `lift` is a positive x component.
static func spin_vector(side: float, lift: float, power: float) -> Vector3:
	var s := clampf(_finite_or(side, 0.0), -1.0, 1.0)
	var l := clampf(_finite_or(lift, 0.0), -1.0, 1.0)
	var p := clampf(_finite_or(power, 0.0), 0.0, 1.0)
	var reach := _SPIN_BASE + (1.0 - _SPIN_BASE) * p
	var spin := Vector3(l * _LIFT_SPIN_MAX * reach, -s * _SIDE_SPIN_MAX * reach, 0.0)
	return _clamp_spin(spin)


## Contact quality in [0, 1] from where the bar was released. 1.0 is a clean
## strike inside the sweet window, and it falls off outside it.
static func contact_quality(release: float, sweet_centre: float) -> float:
	var r := _finite_or(release, 0.5)
	var c := _finite_or(sweet_centre, 0.5)
	var d := absf(r - c)
	if d <= SWEET_WIDTH:
		return 1.0
	if d >= _MISS_WIDTH:
		return 0.0
	var t := (d - SWEET_WIDTH) / (_MISS_WIDTH - SWEET_WIDTH)
	return clampf(1.0 - smoothstep(0.0, 1.0, t), 0.0, 1.0)


## Half angle of the error cone, in radians. A miscue at full power sprays much
## further than a miscue on a placed shot.
static func error_angle(quality: float, power: float) -> float:
	var q := clampf(_finite_or(quality, 1.0), 0.0, 1.0)
	var p := clampf(_finite_or(power, 0.0), 0.0, 1.0)
	var mishit := pow(1.0 - q, _ERROR_EXPONENT)
	var pace := _ERROR_POWER_FLOOR + (1.0 - _ERROR_POWER_FLOOR) * p
	return _ERROR_CLEAN + _ERROR_MISCUE * mishit * pace


## Full resolution of a strike. Deterministic for a given rng_seed.
## Returns {
##   "velocity": Vector3, "spin": Vector3, "quality": float,
##   "speed": float, "target": Vector3, "miscue": bool
## }
##
## Order of operations matters and is the design principle of the module: the
## direction is solved for a SPIN FREE flight to `target`, then sprayed by the
## contact error, and the spin is attached afterwards. The reported "speed" is
## always exactly the length of "velocity".
static func resolve(aim: Vector2, power: float, side: float, lift: float, release: float, sweet_centre: float, rng_seed: int) -> Dictionary:
	var p := clampf(_finite_or(power, 0.0), 0.0, 1.0)
	var target := aim_point(aim)
	var quality := contact_quality(release, sweet_centre)

	# A mishit ball also loses pace, it does not merely fly off line.
	var speed := speed_for_power(p) * (1.0 - _MISCUE_SPEED_LOSS * (1.0 - quality))
	speed = clampf(speed, MIN_SPEED * (1.0 - _MISCUE_SPEED_LOSS), MAX_SPEED)

	var from: Vector3 = Field.SPOT
	var solved: Vector3 = Aero.aim_velocity(from, target, Vector3.ZERO, _WIND, speed)
	if solved.length_squared() < 1e-6 or not _is_finite_vec(solved):
		push_warning("ShotModel: pas de solution de visee, repli balistique")
		solved = _fallback_velocity(from, target, speed)

	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed

	var wobble := 1.0 - quality
	var cone := error_angle(quality, p)
	var direction := _spray(solved, cone, wobble, rng)
	var velocity := direction * speed

	var spin := spin_vector(side, lift, p)
	if wobble > 0.0:
		# A scuffed contact rakes across the ball and leaves spin nobody asked
		# for. Three draws, always in this order, so the seed stays meaningful.
		var jitter := Vector3(
			rng.randf_range(-1.0, 1.0),
			rng.randf_range(-1.0, 1.0),
			rng.randf_range(-1.0, 1.0)
		)
		spin += jitter * (_MISCUE_SPIN * wobble)
	spin = _clamp_spin(spin)

	return {
		"velocity": velocity,
		"spin": spin,
		"quality": quality,
		"speed": speed,
		"target": target,
		"miscue": quality < _MISCUE_LEVEL,
	}


## The cue values the keeper is allowed to read from a strike being prepared.
## Deliberately lossy: this is what leaks through body language, not the truth.
## Returns the dictionary described in 2.12 read_cues.
##
## Three things degrade a cue. The keeper's own read skill (KeeperBrain.read_skill)
## decides how much of the truth survives, capped by _MAX_TELL so even a legend is
## guessing at the margin. Feints multiply every fidelity by _FEINT_MUDDLE each,
## which is why two feints turn the read into near noise. And power leaks by
## itself: a full blooded strike needs a long fast run up that nobody can hide,
## while a side foot placement gives almost nothing away.
##
## What replaces the truth is not zero, it is a decoy: a deterministic bluff
## value hashed from the inputs. A keeper fed a degraded cue therefore dives with
## conviction at the wrong corner rather than politely standing still.
##
## Two hints carry the aim: "aim_hint" for the side and "lift_hint" for the
## height, both already degraded by read_skill, both on their own decoy, so a
## keeper can read the side right and the height wrong, which is exactly what
## happens to a real one.
static func tell_cues(aim: Vector2, power: float, side: float, run_angle: float, feints: int, level: int) -> Dictionary:
	var ax := clampf(_finite_or(aim.x, 0.0), -1.0, 1.0)
	var ay := clampf(_finite_or(aim.y, 0.5), 0.0, 1.0)
	var p := clampf(_finite_or(power, 0.0), 0.0, 1.0)
	var s := clampf(_finite_or(side, 0.0), -1.0, 1.0)
	var run := clampf(_finite_or(run_angle, 0.0), -1.0, 1.0)
	var fk := clampi(feints, 0, 2)
	var raw_read: float = KeeperBrain.read_skill(level)
	var read := clampf(_finite_or(raw_read, 0.5), 0.0, 1.0)

	var qx := _quantise(ax)
	var qy := _quantise(ay)
	var qp := _quantise(p)
	var qs := _quantise(s)

	var scramble := pow(_FEINT_MUDDLE, float(fk))

	# Aim: the headline cue, and the one the level gates.
	var fidelity_aim := clampf(read * _MAX_TELL * scramble, 0.0, 1.0)
	var decoy_aim := _hash01(qx, qp, qs, fk, 101) * 2.0 - 1.0
	var aim_hint := clampf(ax * fidelity_aim + decoy_aim * (1.0 - fidelity_aim), -1.0, 1.0)

	# Height: same treatment as the aim, on its own decoy, with aim.y remapped
	# from the 0..1 of the reticle onto the -1..1 the keeper reads (-1 is "along
	# the turf", +1 is "up under the bar").
	var fidelity_lift := clampf(read * _LIFT_TELL * scramble, 0.0, 1.0)
	# qx belongs in this hash even though the cue is about height: without it every
	# shooter aiming at the same height bluffs identically, and a whole row of the
	# goal becomes readable or unreadable as one block.
	var decoy_lift := _hash01(qy, qx, qp, fk, 601) * 2.0 - 1.0
	var lift_truth := clampf(ay * 2.0 - 1.0, -1.0, 1.0)
	var lift_hint := clampf(lift_truth * fidelity_lift + decoy_lift * (1.0 - fidelity_lift), -1.0, 1.0)

	# Power: hard shots leak, placed shots do not.
	var leak := clampf(_POWER_LEAK_BASE + _POWER_LEAK_GAIN * p, 0.0, 1.0)
	var fidelity_power := clampf(leak * scramble * lerpf(0.65, 1.0, read), 0.0, 1.0)
	var decoy_power := _hash01(qp, qx, qy, fk, 211)
	var power_hint := clampf(lerpf(decoy_power, p, fidelity_power), 0.0, 1.0)

	# The rest is raw body language: physically true, only muddled by the feints,
	# and left to the keeper to interpret with whatever skill it has.
	var approach := clampf(0.22 + 0.72 * p + 0.10 * (_hash01(qp, qs, qy, fk, 307) * 2.0 - 1.0), 0.0, 1.0)
	var plant_noise := (_hash01(qs, qy, qx, fk, 401) * 2.0 - 1.0) * 0.10
	var plant := clampf((0.52 * ax + 0.38 * s + 0.16 * run) * scramble + plant_noise, -1.0, 1.0)
	var hip_muddle := lerpf(1.0, 0.60, float(fk) * 0.5)
	var hip_noise := (_hash01(qy, qx, qp, fk, 509) * 2.0 - 1.0) * 0.05
	var hip := clampf((0.30 * ax + 0.24 * s + 0.18 * run) * hip_muddle + hip_noise, -0.60, 0.60)

	return {
		"run_angle": run,
		"approach_speed": approach,
		"plant_offset": plant,
		"hip_yaw": hip,
		"feints": fk,
		"aim_hint": aim_hint,
		"lift_hint": lift_hint,
		"power_hint": power_hint,
	}


# --- Private helpers ---------------------------------------------------------


## Rotates `direction` inside a cone of half angle `cone`, uniformly over the
## disc so the spray is not bunched at the centre, then tilts the whole cone
## upwards in proportion to the mishit.
static func _spray(direction: Vector3, cone: float, mishit: float, rng: RandomNumberGenerator) -> Vector3:
	var forward := direction.normalized()
	if forward.length_squared() < 0.5:
		forward = Vector3(0.0, 0.0, -1.0)
	var right := forward.cross(Vector3.UP)
	if right.length_squared() < 1e-8:
		right = Vector3.RIGHT
	right = right.normalized()
	var up := right.cross(forward).normalized()

	var azimuth := rng.randf() * TAU
	var radius := absf(cone) * sqrt(rng.randf())
	# The cone is a disc for a clean strike and an upright ellipse for a mishit:
	# see _MISCUE_VERTICAL. Renormalising afterwards keeps it a direction.
	var stretch := lerpf(1.0, _MISCUE_VERTICAL, clampf(mishit, 0.0, 1.0))
	var offset := (right * cos(azimuth) + up * (sin(azimuth) * stretch)) * sin(radius)
	var out := forward * cos(radius) + offset
	if mishit > 0.0:
		out = out.rotated(right, absf(cone) * _MISCUE_LOFT * mishit)
	out = out.normalized()
	if out.length_squared() < 0.5:
		return forward
	return out


## Used only when the shooting solver gives up. A plain ballistic aim corrected
## for the drop over the flight, with the average speed knocked down by drag so
## the ball does not systematically land short.
static func _fallback_velocity(from: Vector3, target: Vector3, speed: float) -> Vector3:
	var delta := target - from
	var flat := Vector3(delta.x, 0.0, delta.z)
	var range_m := flat.length()
	if range_m < 0.01 or speed < 0.01:
		return Vector3(0.0, 0.0, -1.0) * maxf(speed, MIN_SPEED)
	var travel := range_m / maxf(speed * _FALLBACK_DRAG, 0.01)
	var rise: float = delta.y + 0.5 * Aero.GRAVITY * travel * travel
	var dir := (flat + Vector3(0.0, rise, 0.0)).normalized()
	if dir.length_squared() < 0.5:
		dir = Vector3(0.0, 0.0, -1.0)
	return dir * speed


static func _clamp_spin(spin: Vector3) -> Vector3:
	if not _is_finite_vec(spin):
		return Vector3.ZERO
	var rate := spin.length()
	var ceiling: float = Aero.MAX_SPIN
	if rate > ceiling and rate > 0.0:
		return spin * (ceiling / rate)
	return spin


static func _finite_or(value: float, fallback: float) -> float:
	if is_nan(value) or is_inf(value):
		return fallback
	return value


static func _is_finite_vec(v: Vector3) -> bool:
	if is_nan(v.x) or is_nan(v.y) or is_nan(v.z):
		return false
	return not (is_inf(v.x) or is_inf(v.y) or is_inf(v.z))


## Quantised to a thousandth so a float that differs only in its last bit still
## hashes to the same bluff. Body language does not change because of an epsilon.
static func _quantise(value: float) -> int:
	return int(round(clampf(_finite_or(value, 0.0), -8.0, 8.0) * 1000.0))


static func _hash_step(state: int, value: int) -> int:
	var h := (state ^ (value & _HASH_MASK)) & _HASH_MASK
	h = (h * _HASH_MUL_A) & _HASH_MASK
	h = (h ^ (h >> 15)) & _HASH_MASK
	h = (h * _HASH_MUL_B) & _HASH_MASK
	return (h ^ (h >> 13)) & _HASH_MASK


## Deterministic value in [0, 1) from five integers. tell_cues() has no seed in
## its signature, so its bluff values are hashed from the arguments instead: same
## body, same tell, every time, without a global random state.
static func _hash01(a: int, b: int, c: int, d: int, salt: int) -> float:
	var h := _hash_step(_HASH_SEED, salt)
	h = _hash_step(h, a)
	h = _hash_step(h, b)
	h = _hash_step(h, c)
	h = _hash_step(h, d)
	return float(h) / float(_HASH_MASK + 1)
