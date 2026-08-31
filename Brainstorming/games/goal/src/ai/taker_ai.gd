class_name TakerAi
extends RefCounted
## The computer's penalty taker, in pure logic (contract 2.12b).
##
## No nodes, dependencies limited to Field, ShotModel and Aero, everything
## deterministic for a given seed.
##
## THIS MODULE INVENTS NOTHING: IT MOVES HOUSE. The penalty choice it carries used
## to live in src/core/match_state.gd under the names _RIVAL_*, _rival_plan and
## _rival_reticle, and it only ever served to simulate the rival's kick of a
## SEANCE. DUEL needs the SAME taker, this time played out for real against a
## human goalkeeper. There is therefore exactly one CPU taker in this game and it
## is here; Shootout calls it instead of doing the work again.
##
## THE CONSTRAINT OF THAT MOVE IS ABSOLUTE: SEANCE DOES NOT SHIFT BY ONE SAVE.
## choose(seed, SEANCE_LEVEL, pressure, 0.0) returns exactly the plan _rival_plan
## returned for the same seed, DRAW FOR DRAW, including the ORDER in which the
## numbers leave the RandomNumberGenerator: the four measured rows of contract 2.9
## are a property of that order and of nothing else. Three rules keep it true and
## all three are load bearing:
##
##   1. the plan draws in the shipped order, from one RNG seeded with rng_seed:
##      cluster, side sign, x, y, power, miscue test, and only then the two draws
##      of a miscue;
##   2. spread(SEANCE_LEVEL) is 1.0 and feint_count is 0 there, so the level
##      multiplies nothing at that rung;
##   3. everything the level or the keeper adds (feints, run up length, the
##      reading of the keeper's position) draws from ITS OWN salted RNG, so it can
##      never move the plan stream by a single value.
##
## tests/test_taker_ai.gd freezes the plan of several known seeds. If those plans
## change, contract 2.9 is wrong and has to be REMEASURED (4000 kicks per level,
## the procedure is written in 2.9), not patched.
##
## THE TAKER HAS A LEVEL, AND SEANCE OCCUPIES ONE RUNG
##
## The shipped taker had no level: he did not need one, nobody was watching him.
## In DUEL the player READS him, so he needs a ladder, and it is made of two things
## only, like the keeper's: the QUALITY OF THE STRIKE (the spread of his aim) and
## the QUALITY OF THE LIE (what leaks through his body language). A strong taker
## does not kick harder, he places better and he shows less.
##
## WHY HE NEVER CURLS
##
## `side` and `lift` are 0 at every level, as they have always been for the rival
## kick. It is not an omission. ShotModel solves the launch for a SPIN FREE flight
## to the target and then attaches the spin, so a curl would move the ball off the
## very point the tells were built from, and the player would be reading a body
## language that pointed at a place the ball was never going. The taker's placement
## IS the whole of his intention.

enum Level { DEBUTANT = 0, CONFIRME = 1, PRO = 2, LEGENDE = 3 }

const LEVEL_NAMES: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]

## The rung SEANCE has always kicked at, and the one the tables of 2.9 were
## measured on. `spread` is 1.0 here and `feint_count` is 0 here, by definition.
const SEANCE_LEVEL := Level.CONFIRME

## WHERE HE SHOOTS, in metres on the goal line, and how badly he misses. One row
## is [weight, mean |x|, sigma x, mean y, sigma y], the sign of x drawn evenly so
## neither post is favoured. The sigma IS the error: there is no second fudge
## factor anywhere. Same table as balance_probe's AIM_CLUSTERS, deliberately, so
## the rate the simulation reports is comparable with the probe's.
##
## Half the kicks are placed to a side at or below the waist, a fifth are half
## hearted half side shots, a fifth are genuine attempts at the angle of the bar,
## the rest go down the middle. Real takers aim for corners and miss towards the
## middle, and that is exactly what a cluster mean plus a sigma produces.
const AIM_CLUSTERS: Array = [
	[0.30, 2.15, 0.52, 0.72, 0.34],
	[0.20, 1.20, 0.45, 0.95, 0.42],
	[0.16, 0.10, 0.52, 0.85, 0.45],
	[0.22, 2.55, 0.50, 1.82, 0.42],
	[0.12, 0.25, 0.85, 1.80, 0.38],
]

## The reticle stops here. Past it the kick is simply wide or over, which is a
## legal and counted outcome.
const MAX_X := 4.10
const MIN_Y := 0.14
const MAX_Y := 2.90

## Pace of a CPU penalty, as a power in [0, 1] on ShotModel's own bar.
const POWER_MEAN := 0.80
const POWER_SIGMA := 0.11
const POWER_MIN := 0.45

## How often he mistimes the strike, calm and on an elimination kick.
const MISCUE_CALM := 0.10
const MISCUE_TENSE := 0.28

## What nerves multiply the aim sigmas by. See 2.9: this is the visible version of
## a hidden goal chance, and it is why it lives in a taker rather than in a series.
const NERVE := 1.90

## Where his clean contact window sits on the power bar. The value Main uses for a
## scripted shot, so a rival kick and a probe kick are struck by one model.
const SWEET_CENTRE := 0.72

## Inverse of ShotModel.aim_point, which is affine on each axis and therefore
## invertible in closed form. Restated rather than searched for by bisection, and
## guarded by a round trip check in tests/test_taker_ai.gd: if ShotModel ever
## remaps its reticle, that check fails instead of this module quietly aiming
## somewhere else.
const AIM_SPAN_X := 4.40      # Field.GOAL_HALF plus ShotModel's side margin
const AIM_BASE_Y := 0.11      # Field.BALL_RADIUS
const AIM_TOP_Y := 3.04       # Field.GOAL_HEIGHT plus ShotModel's top margin

## How far the keeper is allowed to stray from the middle of his line, metres.
## KeeperInput.LINE_LIMIT and KeeperBrain's own dance bound, restated because this
## module may not depend on the keeper side: it is only ever handed the number.
const KEEPER_LINE_LIMIT := 0.9

# --- The ladder --------------------------------------------------------------

## Multiplier on the sigmas of AIM_CLUSTERS. 1.0 at SEANCE_LEVEL, by contract. The
## bottom rung sprays a third wider, the top rung a third tighter, which is a
## whole glove of difference at the posts and nothing at all down the middle.
const _SPREADS: PackedFloat64Array = [1.32, 1.00, 0.84, 0.68]

## How much of his real intention survives into the tells. The MIRROR of
## KeeperBrain.read_skill: there it is the reader's talent, here the writer's
## clumsiness. A Debutant telegraphs almost everything, a Legende is close to
## unreadable and the player has to gamble on the little that is left.
const _LEAKS: PackedFloat64Array = [0.88, 0.64, 0.42, 0.22]

## Odds of throwing a feint into the run up, and of throwing a second one. Zero at
## the bottom two rungs: an amateur does not have the stutter step, and CONFIRME
## must feint exactly zero times or SEANCE moves (see the header).
const _FEINT_ODDS: PackedFloat64Array = [0.0, 0.0, 0.34, 0.58]
const _SECOND_FEINT := 0.30

## Seconds of run up before contact, so the keeper side has a clock to read the
## tells against. Longer at a low level: an amateur telegraphs by dawdling.
const _RUN_UPS: PackedFloat64Array = [1.42, 1.26, 1.12, 0.98]
const _RUN_UP_JITTER := 0.14

## Metres of aim moved away from the keeper, per metre the keeper has strayed from
## the middle of his line. A weak taker does not shade at all; a Legende shades and
## it still only buys him half a metre at the very worst, an eighth of the goal
## width. Measured against a keeper camped on his limit: the mean move is 0.40 m
## and only one Legende kick in six ends up past x = -2.5. See fairness rule 3 in
## 2.12b: `shift` moves an INTENTION, it does not hunt the opposite corner.
const _SHADES: PackedFloat64Array = [0.0, 0.14, 0.30, 0.44]
const _SHADE_JITTER := 0.22
## Hard ceiling on that shading, metres, whatever the level and the jitter say.
const MAX_SHIFT := 0.55

## Fraction ADDED to the strike's own error by a keeper who dances on his line: it
## goes straight onto the odds of mistiming the contact, because that is what being
## put off actually does to a penalty taker. The mirror image of the shading above:
## the weak taker is rattled and does not shade, the strong one shades and is not
## rattled.
const _RATTLES: PackedFloat64Array = [0.30, 0.18, 0.08, 0.0]
## How much of the rattle also widens the aim, on top of the mistiming.
const _RATTLE_SPRAY := 0.60

# --- Body language -----------------------------------------------------------

## How much of the truth each cue carries when it is fully leaked. The plant foot
## is the honest tell, the hips give a little away, the run up angle almost
## nothing: the same ordering KeeperBrain._PLANT_WEIGHT and friends read them with.
const _RUN_TRUTH := 0.55
const _PLANT_TRUTH := 0.72
const _HIP_TRUTH := 0.34
## Height is harder to disguise than side. A body leaning back over a planted foot
## is going to lift the ball whatever the taker would like the keeper to believe,
## so the height cue leaks MORE than the side one, capped at 1.
const _LIFT_BONUS := 1.18
## Each feint multiplies every fidelity by this. Two feints leave a quarter.
const _FEINT_MUDDLE := 0.52

## Fraction of the run up at which each cue has finished arriving, and the width of
## the window it fades in over. The pace of the approach is visible from the first
## stride, the plant foot and the aim only exist at the very end: that gradient is
## the entire reason waiting is worth anything at all.
const _WHEN_APPROACH := 0.22
const _WHEN_RUN_ANGLE := 0.34
const _WHEN_POWER := 0.52
const _WHEN_HIP := 0.66
const _WHEN_PLANT := 0.86
const _WHEN_AIM := 0.90
const _WHEN_LIFT := 0.94
## Kept strictly under _WHEN_APPROACH, the earliest cue: a window that opened
## before the run up started would leak information at t = -infinity.
const _CUE_FADE := 0.20

## Neutral value of the pace cue while nobody has moved yet.
const _POWER_UNKNOWN := 0.5

# --- Salts -------------------------------------------------------------------
#
# Every derived draw runs on its own stream so none of them can move the plan.

const _SALT_FEINT := 0x5F3A91
const _SALT_RUN_UP := 0x2C77E5
const _SALT_KEEPER := 0x71B4D3
const _SALT_TELLS := 0x1D9E47


## Normalized reticle for a point of the goal line. See AIM_SPAN_X.
static func reticle(world_x: float, world_y: float) -> Vector2:
	var x := _finite_or(world_x, 0.0)
	var y := _finite_or(world_y, 1.0)
	return Vector2(x / AIM_SPAN_X, (y - AIM_BASE_Y) / (AIM_TOP_Y - AIM_BASE_Y))


## Multiplier ON the sigmas of AIM_CLUSTERS for this level. 1.0 at SEANCE_LEVEL.
static func spread(level: int) -> float:
	return float(_SPREADS[_level(level)])


## How much of his real intention leaks into the tells, 0..1.
static func leak(level: int) -> float:
	return float(_LEAKS[_level(level)])


## Feints thrown into the run up, at most two. Deterministic. 0 at SEANCE_LEVEL.
static func feint_count(level: int, rng_seed: int) -> int:
	var odds := float(_FEINT_ODDS[_level(level)])
	if odds <= 0.0:
		return 0
	var rng := _rng(rng_seed, _SALT_FEINT)
	if rng.randf() >= odds:
		return 0
	if rng.randf() < _SECOND_FEINT:
		return 2
	return 1


## Seconds of run up before contact, so the keeper side has a clock to read the
## tells against. Longer at a low level: an amateur telegraphs by dawdling.
static func run_up_time(level: int, rng_seed: int) -> float:
	var base := float(_RUN_UPS[_level(level)])
	var rng := _rng(rng_seed, _SALT_RUN_UP)
	var jitter := (rng.randf() * 2.0 - 1.0) * _RUN_UP_JITTER
	return clampf(base + jitter, 0.55, 2.2)


## How the taker answers a keeper who has left the middle of his line. Returns
## {"shift": float, "rattle": float}: `shift` is metres of aim moved AWAY from the
## keeper, `rattle` a fraction ADDED to the strike's own error. `choose` already
## folds both in; it is exposed for the tests and the HUD.
##
## The ONLY thing about the keeper this module is ever given is that x. Anything
## more and the duel becomes a rock paper scissors the computer plays second in,
## which it wins every time.
static func read_keeper(keeper_x: float, level: int, rng_seed: int) -> Dictionary:
	var lv := _level(level)
	var x := clampf(_finite_or(keeper_x, 0.0), -KEEPER_LINE_LIMIT, KEEPER_LINE_LIMIT)
	if absf(x) < 0.0001:
		return {"shift": 0.0, "rattle": 0.0}
	var rng := _rng(rng_seed, _SALT_KEEPER)
	var wobble := 1.0 + (rng.randf() * 2.0 - 1.0) * _SHADE_JITTER
	var shift := clampf(-x * float(_SHADES[lv]) * wobble, -MAX_SHIFT, MAX_SHIFT)
	var rattle := clampf(
		float(_RATTLES[lv]) * (absf(x) / KEEPER_LINE_LIMIT), 0.0, 1.0)
	return {"shift": shift, "rattle": rattle}


## ONE CPU penalty, decided. Deterministic for `rng_seed`.
## `pressure` is the elimination kick of 2.9. `keeper_x` is where the keeper is
## standing on his line when the taker plants his foot, in metres, and it is the
## ONLY thing about the keeper this module is ever given.
## Returns {"aim": Vector2, "power": float, "side": float, "lift": float,
##          "release": float, "sweet_centre": float, "target": Vector3,
##          "shift": float, "rattle": float, "level": int, "pressure": bool}
## `target` is the world point of `aim`, published so callers stop recomputing it.
static func choose(rng_seed: int, level: int, pressure: bool, keeper_x: float) -> Dictionary:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	return _plan_from(rng, level, pressure, keeper_x, rng_seed)


## The `elapsed` a SEANCE feeds KeeperBrain.line_dance with, drawn from the SAME
## stream and at the SAME position the shipped code drew it from: the very next
## value after the plan. It exists so the simulated kick of 2.9 keeps its measured
## tables to the save, and it is the only reason this function is public. Nothing
## in DUEL uses it: there the keeper is a player and dances with his own hands.
static func dance_phase(rng_seed: int, level: int, pressure: bool) -> float:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var _plan := _plan_from(rng, level, pressure, 0.0, rng_seed)
	return 0.30 + 0.70 * rng.randf()


## The strike itself, through ShotModel.resolve, returned unchanged: a CPU penalty
## and a player penalty are the same object everywhere downstream.
static func strike(plan: Dictionary, rng_seed: int) -> Dictionary:
	var aim: Vector2 = plan.get("aim", Vector2(0.0, 0.4))
	var power := float(plan.get("power", POWER_MEAN))
	var side := float(plan.get("side", 0.0))
	var lift := float(plan.get("lift", 0.0))
	var release := float(plan.get("release", SWEET_CENTRE))
	var sweet := float(plan.get("sweet_centre", SWEET_CENTRE))
	return ShotModel.resolve(aim, power, side, lift, release, sweet, rng_seed)


## What the AI KEEPER is allowed to read: ShotModel.tell_cues at the keeper's own
## level, exactly as SEANCE has always asked for it. Behaviour unchanged, moved
## here so both sides of a duel ask one module for the taker's body language.
##
## No run up angle and no feints, which is not an oversight: the rival kick of a
## SEANCE has never had either, and adding one here would change the four measured
## rows of 2.9 without anybody asking for it.
static func cues(plan: Dictionary, keeper_level: int) -> Dictionary:
	var aim: Vector2 = plan.get("aim", Vector2(0.0, 0.4))
	var power := float(plan.get("power", POWER_MEAN))
	var side := float(plan.get("side", 0.0))
	return ShotModel.tell_cues(aim, power, side, 0.0, 0, keeper_level)


## What the PLAYER keeper is allowed to read, which is a different question: the
## lossiness comes from the TAKER's level (`leak`) and never from the reader's.
## Returns the cue dictionary described in 2.12 read_cues, plus:
##   "feints" int, "run_up" float (seconds), "confidence" float 0..1
## Every hint in it is ALREADY degraded. Nothing in it is the truth, and a caller
## that needs the truth is holding the plan.
##
## What replaces the truth is not zero, it is a DECOY, exactly as in
## ShotModel.tell_cues: a keeper handed a degraded cue dives with conviction at the
## wrong corner instead of politely standing still. That is what makes the mode a
## gamble rather than a coin flip, and it is why a perfect reader still cannot
## recover the aim from these numbers.
static func tells(plan: Dictionary, level: int, rng_seed: int) -> Dictionary:
	var lv := _level(level)
	var aim: Vector2 = plan.get("aim", Vector2(0.0, 0.4))
	var ax := clampf(_finite_or(aim.x, 0.0), -1.0, 1.0)
	var ay := clampf(_finite_or(aim.y, 0.5), 0.0, 1.0)
	var power := clampf(_finite_or(float(plan.get("power", POWER_MEAN)), POWER_MEAN), 0.0, 1.0)
	var feints := feint_count(lv, rng_seed)
	var run_up := run_up_time(lv, rng_seed)

	var scramble := pow(_FEINT_MUDDLE, float(feints))
	var fidelity := clampf(leak(lv) * scramble, 0.0, 1.0)
	var fidelity_lift := clampf(leak(lv) * _LIFT_BONUS * scramble, 0.0, 1.0)

	var rng := _rng(rng_seed, _SALT_TELLS)
	var decoy_aim := rng.randf() * 2.0 - 1.0
	var decoy_lift := rng.randf() * 2.0 - 1.0
	var decoy_power := rng.randf()
	var decoy_run := rng.randf() * 2.0 - 1.0
	var decoy_plant := rng.randf() * 2.0 - 1.0
	var decoy_hip := rng.randf() * 2.0 - 1.0
	var decoy_pace := rng.randf() * 2.0 - 1.0

	var lift_truth := clampf(ay * 2.0 - 1.0, -1.0, 1.0)
	var aim_hint := clampf(ax * fidelity + decoy_aim * (1.0 - fidelity), -1.0, 1.0)
	var lift_hint := clampf(
		lift_truth * fidelity_lift + decoy_lift * (1.0 - fidelity_lift), -1.0, 1.0)
	var power_hint := clampf(power * fidelity + decoy_power * (1.0 - fidelity), 0.0, 1.0)

	var run_angle := clampf(
		ax * _RUN_TRUTH * fidelity + decoy_run * (1.0 - fidelity), -1.0, 1.0)
	var plant := clampf(
		ax * _PLANT_TRUTH * fidelity + decoy_plant * (1.0 - fidelity), -1.0, 1.0)
	var hip := clampf(
		(ax * _HIP_TRUTH * fidelity + decoy_hip * 0.6 * (1.0 - fidelity)), -0.60, 0.60)
	# The pace of the approach fades towards a DECOY PACE and never towards zero.
	# Multiplying the truth by the fidelity instead would have made a Legende
	# always amble in and a Debutant always charge, which leaks the level rather
	# than the shot and is exactly the wrong thing to leak.
	var pace_truth := clampf(0.22 + 0.72 * power, 0.0, 1.0)
	var pace_decoy := clampf(0.22 + 0.72 * (decoy_pace * 0.5 + 0.5), 0.0, 1.0)
	var approach := clampf(lerpf(pace_decoy, pace_truth, fidelity), 0.0, 1.0)

	return {
		"run_angle": run_angle,
		"approach_speed": approach,
		"plant_offset": plant,
		"hip_yaw": hip,
		"feints": feints,
		"aim_hint": aim_hint,
		"lift_hint": lift_hint,
		"power_hint": power_hint,
		"run_up": run_up,
		"confidence": fidelity,
	}


## The same dictionary as `tells`, but as it stands `t` seconds from contact, `t`
## negative during the run up: the cues arrive one by one as the taker gets closer,
## so a keeper who commits early has genuinely seen less. This is what the HUD
## draws frame by frame, and it is the entire reason waiting is worth anything.
##
## At t >= 0 it is `tells` itself, value for value. At t <= -run_up nothing has
## happened yet and every cue sits at its neutral value with a confidence of zero.
static func tells_at(plan: Dictionary, level: int, rng_seed: int, t: float) -> Dictionary:
	var full := tells(plan, level, rng_seed)
	var run_up := float(full.get("run_up", 1.0))
	var now := _finite_or(t, 0.0)
	var progress := 1.0
	if run_up > 0.0:
		progress = clampf(1.0 + now / run_up, 0.0, 1.0)

	var w_approach := _arrived(progress, _WHEN_APPROACH)
	var w_run := _arrived(progress, _WHEN_RUN_ANGLE)
	var w_power := _arrived(progress, _WHEN_POWER)
	var w_hip := _arrived(progress, _WHEN_HIP)
	var w_plant := _arrived(progress, _WHEN_PLANT)
	var w_aim := _arrived(progress, _WHEN_AIM)
	var w_lift := _arrived(progress, _WHEN_LIFT)

	var seen := (w_approach + w_run + w_power + w_hip + w_plant + w_aim + w_lift) / 7.0

	return {
		"run_angle": float(full["run_angle"]) * w_run,
		"approach_speed": float(full["approach_speed"]) * w_approach,
		"plant_offset": float(full["plant_offset"]) * w_plant,
		"hip_yaw": float(full["hip_yaw"]) * w_hip,
		"feints": int(full["feints"]),
		"aim_hint": float(full["aim_hint"]) * w_aim,
		"lift_hint": float(full["lift_hint"]) * w_lift,
		"power_hint": lerpf(_POWER_UNKNOWN, float(full["power_hint"]), w_power),
		"run_up": run_up,
		"confidence": float(full["confidence"]) * seen,
	}


# --- Private -----------------------------------------------------------------

## The plan, drawn on a caller supplied stream so dance_phase can carry on reading
## the very same one. THE ORDER OF THE DRAWS IN HERE IS THE CONTRACT: cluster,
## side sign, x, y, power, miscue test, then the two draws of a miscue. See the
## header before touching a line of it.
static func _plan_from(rng: RandomNumberGenerator, level: int, pressure: bool,
		keeper_x: float, rng_seed: int) -> Dictionary:
	var lv := _level(level)
	var answer := read_keeper(keeper_x, lv, rng_seed)
	var shift := float(answer.get("shift", 0.0))
	var rattle := float(answer.get("rattle", 0.0))

	var draw := rng.randf()
	var chosen: Array = AIM_CLUSTERS[AIM_CLUSTERS.size() - 1]
	var accumulated := 0.0
	for entry in AIM_CLUSTERS:
		var cluster: Array = entry
		accumulated += float(cluster[0])
		if draw <= accumulated:
			chosen = cluster
			break

	var nerve := NERVE if pressure else 1.0
	nerve *= spread(lv) * (1.0 + _RATTLE_SPRAY * rattle)
	var sign_x := 1.0 if rng.randf() < 0.5 else -1.0
	var world_x := sign_x * (float(chosen[1]) + rng.randfn(0.0, float(chosen[2]) * nerve))
	var world_y := float(chosen[3]) + rng.randfn(0.0, float(chosen[4]) * nerve)
	world_x = clampf(world_x + shift, -MAX_X, MAX_X)
	world_y = clampf(world_y, MIN_Y, MAX_Y)

	var power := clampf(rng.randfn(POWER_MEAN, POWER_SIGMA), POWER_MIN, 1.0)

	var miscue_chance := MISCUE_TENSE if pressure else MISCUE_CALM
	miscue_chance = clampf(miscue_chance + rattle, 0.0, 1.0)
	var release := SWEET_CENTRE
	if rng.randf() < miscue_chance:
		var offset: float = rng.randf_range(0.12, 0.26)
		if rng.randf() < 0.5:
			release = SWEET_CENTRE - offset
		else:
			release = minf(SWEET_CENTRE + offset, 1.0)

	var aim := reticle(world_x, world_y)
	return {
		"aim": aim,
		"power": power,
		"side": 0.0,
		"lift": 0.0,
		"release": release,
		"sweet_centre": SWEET_CENTRE,
		"target": Vector3(world_x, world_y, 0.0),
		"shift": shift,
		"rattle": rattle,
		"level": lv,
		"pressure": pressure,
	}


## How much of a cue has arrived at this point of the run up. Smooth, so nothing
## the HUD draws ever pops into existence between two frames.
static func _arrived(progress: float, when: float) -> float:
	return clampf(smoothstep(when - _CUE_FADE, when, progress), 0.0, 1.0)


static func _level(level: int) -> int:
	if level < 0 or level > 3:
		return int(SEANCE_LEVEL)
	return level


## A stream of its own, so a derived draw can never move the plan stream. Mixed
## with plain arithmetic rather than hash(Vector2i(...)): a seed wider than 32 bits
## would be silently truncated by the vector, and callers hand this whatever their
## own campaign salt produced.
const _MIX_A := 0x9E3779B1
const _MIX_B := 0x27D4EB2D
const _MIX_MASK := 0x7FFFFFFFFFFF

static func _rng(rng_seed: int, salt: int) -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	var mixed := (rng_seed ^ (salt * _MIX_A)) & _MIX_MASK
	mixed = (mixed * _MIX_B) & _MIX_MASK
	rng.seed = mixed ^ salt
	return rng


static func _finite_or(value: float, fallback: float) -> float:
	if is_nan(value) or is_inf(value):
		return fallback
	return value
