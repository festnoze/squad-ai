extends GoalTest
## The rules of a shootout, and the rival's kick, tested on a copy.
##
## src/core/match_state.gd is the `Shootout` autoload, and an autoload cannot be
## named from a suite: with `--script`, Godot does not register the singletons,
## so the mere mention of the identifier stops this file from compiling. The
## contract's answer, followed here, is to copy the pure decision helpers into
## the suite and test those. They are byte for byte the bodies of the private
## statics in match_state.gd, so a change there that is not mirrored here shows
## up as a failing expectation rather than as silence.
##
## The copy is much longer than it used to be, and deliberately so. The rival's
## kick is no longer a coin toss against a fixed goal chance, it is a whole
## penalty resolved through ShotModel, Aero, Field and KeeperBrain, and those
## four ARE reachable from here: they are `class_name` globals, not autoloads.
## So the suite runs the real thing rather than a stand in, and the numbers it
## checks are the numbers the game produces.

enum Verdict { BUT, ARRET, POTEAU, BARRE, DEHORS }

const REGULATION_SHOTS := 5
const DEFI_GOAL_POINTS := 100
const DEFI_STREAK_BONUS := 25
const DEFI_FRAME_POINTS := 25

const _RIVAL_STEP := 1.0 / 120.0
const _RIVAL_MAX_STEPS := 600
const _RIVAL_TURF_RESTITUTION := 0.45
const _RIVAL_TURF_FRICTION := 0.42
const _RIVAL_ESTIMATE_EVERY := 2

const _RIVAL_HOME_TARGET := Vector3(0.0, 1.25, 0.0)
const _RIVAL_DIVE_POSE_MAX := 1.60
const _RIVAL_LINE_BLEND := 0.16
const _RIVAL_COMMIT_MARGIN := 0.03
const _RIVAL_CONFIDENT_ERROR := 0.16

const _RIVAL_SWEET := 0.72

const _RIVAL_AIM_SPAN_X := 4.40
const _RIVAL_AIM_BASE_Y := 0.11
const _RIVAL_AIM_TOP_Y := 3.04

const _RIVAL_AIM: Array = [
	[0.30, 2.15, 0.52, 0.72, 0.34],
	[0.20, 1.20, 0.45, 0.95, 0.42],
	[0.16, 0.10, 0.52, 0.85, 0.45],
	[0.22, 2.55, 0.50, 1.82, 0.42],
	[0.12, 0.25, 0.85, 1.80, 0.38],
]
const _RIVAL_MAX_X := 4.10
const _RIVAL_MIN_Y := 0.14
const _RIVAL_MAX_Y := 2.90
const _RIVAL_POWER_MEAN := 0.80
const _RIVAL_POWER_SIGMA := 0.11
const _RIVAL_POWER_MIN := 0.45
const _RIVAL_MISCUE_CALM := 0.10
const _RIVAL_NERVE := 1.90
const _RIVAL_MISCUE_TENSE := 0.28

## KeeperBrain.Level, spelled out so the suite reads without a lookup.
const DEBUTANT := 0
const CONFIRME := 1
const PRO := 2
const LEGENDE := 3


func suite_name() -> String:
	return "Shootout (regles recopiees)"


# --------------------------------------------------------------------------
# Copies of the production helpers.
# --------------------------------------------------------------------------

static func _label(verdict: int) -> String:
	match verdict:
		Verdict.BUT:
			return "BUT !"
		Verdict.ARRET:
			return "Arret du gardien"
		Verdict.POTEAU:
			return "Poteau !"
		Verdict.BARRE:
			return "Barre transversale !"
		Verdict.DEHORS:
			return "A cote"
	return "Tir"


static func _is_goal(verdict: int) -> bool:
	return verdict == Verdict.BUT


static func _goals_in(scores: Array[int]) -> int:
	var total := 0
	for verdict in scores:
		if verdict == Verdict.BUT:
			total += 1
	return total


static func _series_decided(player_shots: int, player_goals_count: int, rival_shots: int, rival_goals_count: int) -> bool:
	if player_shots >= REGULATION_SHOTS and rival_shots >= REGULATION_SHOTS:
		return player_shots == rival_shots and player_goals_count != rival_goals_count
	var player_left := maxi(0, REGULATION_SHOTS - player_shots)
	var rival_left := maxi(0, REGULATION_SHOTS - rival_shots)
	if player_goals_count > rival_goals_count + rival_left:
		return true
	if rival_goals_count > player_goals_count + player_left:
		return true
	return false


static func _rival_under_pressure(player_goals_count: int, rival_shots: int,
		rival_goals_count: int) -> bool:
	var left_after := maxi(0, REGULATION_SHOTS - rival_shots - 1)
	return rival_goals_count + left_after < player_goals_count


## Copy of Shootout.rival_to_kick, on plain integers. `two_sided` is
## `mode == Mode.SEANCE or mode == Mode.DUEL`: the two modes with a second side.
## DUEL differs only in HOW the turn happens, never in WHEN it is owed, which is
## the property the duel tests below exist to pin down.
static func _rival_owes_a_kick(two_sided: bool, player_shots: int, player_goals_count: int,
		rival_shots: int, rival_goals_count: int) -> bool:
	if not two_sided:
		return false
	if _series_decided(player_shots, player_goals_count, rival_shots, rival_goals_count):
		return false
	return rival_shots < player_shots


## Copy of Shootout.player_keeps. It is deliberately nothing but `rival_to_kick`
## with the mode in front of it: one rule, one answer, and a duel that cannot
## drift half a round out of step with a seance.
static func _player_keeps(duel: bool, player_shots: int, player_goals_count: int,
		rival_shots: int, rival_goals_count: int) -> bool:
	if not duel:
		return false
	return _rival_owes_a_kick(true, player_shots, player_goals_count,
		rival_shots, rival_goals_count)


## Copy of Shootout.mode_label, without the autoload.
static func _mode_label(mode_id: int) -> String:
	match mode_id:
		0:
			return "Seance"
		1:
			return "Entrainement"
		2:
			return "Defi"
		3:
			return "Duel"
	return "Seance"


static func _rival_verdict(rng_seed: int, keeper_level: int, pressure: bool) -> int:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var level := clampi(keeper_level, 0, 3)
	var plan := _rival_plan(rng, pressure)
	var dance: float = 0.30 + 0.70 * rng.randf()
	return _rival_flight(plan, level, rng_seed, dance)


static func _rival_plan(rng: RandomNumberGenerator, pressure: bool) -> Dictionary:
	var draw := rng.randf()
	var chosen: Array = _RIVAL_AIM[_RIVAL_AIM.size() - 1]
	var accumulated := 0.0
	for entry in _RIVAL_AIM:
		var cluster: Array = entry
		accumulated += float(cluster[0])
		if draw <= accumulated:
			chosen = cluster
			break

	var nerve := _RIVAL_NERVE if pressure else 1.0
	var side := 1.0 if rng.randf() < 0.5 else -1.0
	var world_x := side * (float(chosen[1]) + rng.randfn(0.0, float(chosen[2]) * nerve))
	var world_y := float(chosen[3]) + rng.randfn(0.0, float(chosen[4]) * nerve)
	world_x = clampf(world_x, -_RIVAL_MAX_X, _RIVAL_MAX_X)
	world_y = clampf(world_y, _RIVAL_MIN_Y, _RIVAL_MAX_Y)

	var power := clampf(
		rng.randfn(_RIVAL_POWER_MEAN, _RIVAL_POWER_SIGMA), _RIVAL_POWER_MIN, 1.0)

	var miscue_chance := _RIVAL_MISCUE_TENSE if pressure else _RIVAL_MISCUE_CALM
	var release := _RIVAL_SWEET
	if rng.randf() < miscue_chance:
		var offset: float = rng.randf_range(0.12, 0.26)
		if rng.randf() < 0.5:
			release = _RIVAL_SWEET - offset
		else:
			release = minf(_RIVAL_SWEET + offset, 1.0)

	return {
		"aim": _rival_reticle(world_x, world_y),
		"power": power,
		"release": release,
	}


static func _rival_reticle(world_x: float, world_y: float) -> Vector2:
	return Vector2(
		world_x / _RIVAL_AIM_SPAN_X,
		(world_y - _RIVAL_AIM_BASE_Y) / (_RIVAL_AIM_TOP_Y - _RIVAL_AIM_BASE_Y))


static func _rival_flight(plan: Dictionary, level: int, shot_seed: int, dance: float) -> int:
	var aim: Vector2 = plan.get("aim", Vector2(0.0, 0.4))
	var power := float(plan.get("power", _RIVAL_POWER_MEAN))
	var release := float(plan.get("release", _RIVAL_SWEET))

	var shot: Dictionary = ShotModel.resolve(
		aim, power, 0.0, 0.0, release, _RIVAL_SWEET, shot_seed)
	var cues: Dictionary = ShotModel.tell_cues(aim, power, 0.0, 0.0, 0, level)
	var guess: Dictionary = KeeperBrain.read_cues(cues, level, shot_seed)

	var line_x := clampf(KeeperBrain.line_dance(dance, level, shot_seed), -1.1, 1.1)
	var lead := 0.0
	if bool(guess.get("commit", false)):
		lead = maxf(-float(guess.get("commit_time", 0.0)), 0.0)

	var position: Vector3 = Field.SPOT
	var velocity: Vector3 = shot.get("velocity", Vector3.ZERO)
	var spin: Vector3 = shot.get("spin", Vector3.ZERO)
	if not velocity.is_finite() or velocity.length() < 0.01:
		return Verdict.DEHORS

	var committed := false
	var commit_at := 0.0
	var dive_lead := 0.0
	var dive_target := _RIVAL_HOME_TARGET
	var pose := _rival_set_pose(line_x, level)
	var elapsed := 0.0

	for step in _RIVAL_MAX_STEPS:
		var stepped: Array = Aero.integrate(
			position, velocity, spin, Vector3.ZERO, _RIVAL_STEP)
		var to_point: Vector3 = stepped[0]
		var to_velocity: Vector3 = stepped[1]
		if not to_point.is_finite() or not to_velocity.is_finite():
			return Verdict.DEHORS
		var t_to := elapsed + _RIVAL_STEP
		var step_velocity := (to_point - position) / _RIVAL_STEP

		var frame: Dictionary = Field.sweep_frame(position, to_point)
		if bool(frame.get("hit", false)):
			if int(frame.get("part", Field.FRAME_NONE)) == Field.FRAME_BAR:
				return Verdict.BARRE
			return Verdict.POTEAU

		if not committed and (step % _RIVAL_ESTIMATE_EVERY) == 0:
			var may_move: bool = lead > 0.0 or t_to >= KeeperBrain.reaction_time(level)
			if may_move:
				var estimate: Dictionary = KeeperBrain.estimate_cross(
					position, step_velocity, spin, level, t_to, shot_seed)
				var dive: Dictionary = KeeperBrain.choose_dive(estimate, guess, level, t_to)
				var target: Vector3 = dive.get("target", _RIVAL_HOME_TARGET)
				var here: Vector3 = pose.get("centre", Field.KEEPER_HOME)
				var need := KeeperBrain.dive_time_needed(target, here.x, level)
				var time_left := maxf(float(estimate.get("time", 0.0)), 0.0)
				var go := time_left <= need + lead + _RIVAL_COMMIT_MARGIN
				if not go and lead <= 0.0:
					go = float(estimate.get("error", 9.0)) <= _RIVAL_CONFIDENT_ERROR
				if go:
					committed = true
					commit_at = t_to
					dive_target = target
					dive_lead = clampf(need + lead - time_left, 0.0, lead)

		if committed:
			var dive_t := maxf(t_to - commit_at + dive_lead, 0.0)
			pose = _rival_offset_pose(
				KeeperBrain.dive_pose(dive_target, minf(dive_t, _RIVAL_DIVE_POSE_MAX), level),
				line_x * exp(-dive_t / _RIVAL_LINE_BLEND))
		else:
			pose = _rival_set_pose(line_x * exp(-t_to / _RIVAL_LINE_BLEND), level)

		var save: Dictionary = KeeperBrain.try_save(pose, position, to_point)
		if bool(save.get("saved", false)):
			return Verdict.ARRET

		var cross: Dictionary = Field.cross_goal_plane(position, to_point)
		if bool(cross.get("crossed", false)):
			var point: Vector3 = cross.get("point", to_point)
			return Verdict.BUT if Field.is_within_frame(point) else Verdict.DEHORS

		if Field.is_out_of_area(to_point):
			return Verdict.DEHORS

		if to_point.y <= Field.BALL_RADIUS and to_velocity.y < 0.0:
			var reflected: Array = Aero.bounce(
				to_velocity, spin, Vector3.UP, _RIVAL_TURF_RESTITUTION, _RIVAL_TURF_FRICTION)
			to_velocity = reflected[0]
			spin = reflected[1]
			to_point.y = Field.BALL_RADIUS + 0.004

		position = to_point
		velocity = to_velocity
		spin = Aero.decay_spin(spin, _RIVAL_STEP)
		elapsed = t_to
	return Verdict.DEHORS


static func _rival_set_pose(x: float, level: int) -> Dictionary:
	var home: Dictionary = KeeperBrain.dive_pose(_RIVAL_HOME_TARGET, 0.0, level)
	var home_x := Vector3(home.get("centre", Field.KEEPER_HOME)).x
	var base := _rival_offset_pose(home, x - home_x)
	var centre: Vector3 = base.get("centre", Field.KEEPER_HOME)
	centre.y -= 0.13
	centre.z += 0.05
	return {
		"centre": centre,
		"glove_left": Vector3(base.get("glove_left", centre)) + Vector3(0.30, -0.15, 0.31),
		"glove_right": Vector3(base.get("glove_right", centre)) + Vector3(-0.30, -0.15, 0.31),
		"boot_left": Vector3(base.get("boot_left", centre)) + Vector3(0.05, 0.0, -0.02),
		"boot_right": Vector3(base.get("boot_right", centre)) + Vector3(-0.05, 0.0, -0.02),
		"lean": 0.0,
		"airborne": 0.0,
	}


static func _rival_offset_pose(source: Dictionary, dx: float) -> Dictionary:
	var shift := Vector3(dx, 0.0, 0.0)
	var centre: Vector3 = Vector3(source.get("centre", Field.KEEPER_HOME)) + shift
	return {
		"centre": centre,
		"glove_left": Vector3(source.get("glove_left", centre)) + shift,
		"glove_right": Vector3(source.get("glove_right", centre)) + shift,
		"boot_left": Vector3(source.get("boot_left", centre)) + shift,
		"boot_right": Vector3(source.get("boot_right", centre)) + shift,
		"lean": float(source.get("lean", 0.0)),
		"airborne": float(source.get("airborne", 0.0)),
	}


static func _defi_award(verdict: int, streak_before: int) -> int:
	if verdict == Verdict.BUT:
		return DEFI_GOAL_POINTS + DEFI_STREAK_BONUS * streak_before
	if verdict == Verdict.POTEAU or verdict == Verdict.BARRE:
		return DEFI_FRAME_POINTS
	return 0


## Goals out of `samples` simulated rival kicks at this level, from a fixed seed
## line so the figure is reproducible and this suite can never flake.
func _rival_goal_rate(samples: int, level: int, pressure: bool, base_seed: int) -> float:
	var goals := 0
	for i in samples:
		if _rival_verdict(base_seed + i * 7919, level, pressure) == Verdict.BUT:
			goals += 1
	return float(goals) / float(maxi(samples, 1))


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

func test_verdict_labels_are_french_and_distinct() -> void:
	var seen := PackedStringArray()
	for verdict: int in [Verdict.BUT, Verdict.ARRET, Verdict.POTEAU, Verdict.BARRE, Verdict.DEHORS]:
		var label := _label(verdict)
		check(label.length() > 2, "un verdict doit avoir un libelle lisible")
		check(not seen.has(label), "le libelle '%s' est utilise deux fois" % label)
		seen.append(label)
	eq(_label(Verdict.BUT), "BUT !", "le but se crie")
	eq(_label(99), "Tir", "un verdict inconnu ne casse pas le HUD")
	done()


func test_only_but_counts_as_a_goal() -> void:
	check(_is_goal(Verdict.BUT), "un but est un but")
	check(not _is_goal(Verdict.ARRET), "un arret n'est pas un but")
	# A shot that hits the post and goes in is recorded as BUT, so POTEAU always
	# means the frame sent it back out.
	check(not _is_goal(Verdict.POTEAU), "un poteau sorti n'est pas un but")
	check(not _is_goal(Verdict.BARRE), "une barre sortie n'est pas un but")
	check(not _is_goal(Verdict.DEHORS), "un tir a cote n'est pas un but")
	var scores: Array[int] = [Verdict.BUT, Verdict.ARRET, Verdict.BUT, Verdict.DEHORS, Verdict.BUT]
	eq(_goals_in(scores), 3, "trois buts sur cinq tirs")
	var empty: Array[int] = []
	eq(_goals_in(empty), 0, "aucun tir, aucun but")
	done()


func test_nothing_is_decided_at_the_start() -> void:
	check(not _series_decided(0, 0, 0, 0), "avant le premier tir rien n'est joue")
	check(not _series_decided(1, 1, 1, 1), "1-1 apres un tir, rien n'est joue")
	check(not _series_decided(3, 2, 3, 2), "2-2 apres trois tirs, rien n'est joue")
	check(not _series_decided(3, 2, 3, 0), "2-0 avec deux tirs restants, encore rattrapable")
	done()


func test_an_uncatchable_lead_ends_the_series_early() -> void:
	# 3-0 after three kicks each: the rival has two left, it cannot reach three.
	check(_series_decided(3, 3, 3, 0), "3-0 en trois tirs, la seance est finie")
	# The same lead one kick earlier is not enough: three left, three to catch.
	check(not _series_decided(3, 3, 2, 0), "3-0 alors que le rival a trois tirs, on continue")
	# It works in both directions.
	check(_series_decided(3, 0, 3, 3), "0-3 en trois tirs, la seance est finie aussi")
	check(_series_decided(4, 4, 4, 1), "4-1 en quatre tirs")
	check(not _series_decided(4, 3, 4, 2), "3-2 en quatre tirs, un tir peut tout changer")
	done()


func test_regulation_ends_on_a_difference() -> void:
	check(_series_decided(5, 4, 5, 3), "4-3 apres cinq tirs chacun, c'est fini")
	check(not _series_decided(5, 3, 5, 3), "3-3 apres cinq tirs chacun, mort subite")
	check(not _series_decided(5, 3, 4, 3), "il manque un tir au rival, on ne conclut pas")
	done()


func test_sudden_death_needs_the_same_number_of_kicks() -> void:
	# The whole point of the rule: the side kicking first must not win the round
	# it scores, the other side has the right to answer.
	check(not _series_decided(6, 4, 5, 3), "le tireur a un tir d'avance, on attend la reponse")
	check(_series_decided(6, 4, 6, 3), "reponse manquee, la mort subite est tranchee")
	check(not _series_decided(6, 4, 6, 4), "les deux marquent, on repart pour un tour")
	check(not _series_decided(7, 5, 7, 5), "toujours a egalite au septieme")
	check(_series_decided(9, 7, 9, 6), "cela finit toujours par tomber")
	done()


# --- Whose turn it is ------------------------------------------------------

func test_the_rival_only_kicks_when_the_rules_owe_him_one() -> void:
	# Before the player has kicked at all, nobody owes anything.
	check(not _rival_owes_a_kick(true, 0, 0, 0, 0), "personne ne tire avant le premier tir")
	# The player has kicked, the rival has not: his turn, and only his.
	check(_rival_owes_a_kick(true, 1, 1, 0, 0), "le joueur a tire, c'est au rival")
	check(not _rival_owes_a_kick(true, 1, 1, 1, 1), "le rival ne tire pas deux fois de suite")
	# The other two modes have no second side at all.
	check(not _rival_owes_a_kick(false, 3, 2, 0, 0), "l'entrainement et le defi n'ont pas d'adversaire")
	# THE RULE THAT MATTERS: nobody takes a kick that cannot change the result.
	check(_series_decided(4, 4, 3, 0), "4-0 en quatre tirs contre trois : c'est plie")
	check(not _rival_owes_a_kick(true, 4, 4, 3, 0),
		"une seance deja gagnee ne donne pas un tir de plus au rival")
	check(not _rival_owes_a_kick(true, 4, 0, 3, 4),
		"une seance deja perdue non plus")
	# Sudden death: the answering kick is owed, and exactly one.
	check(_rival_owes_a_kick(true, 6, 4, 5, 3), "en mort subite le rival a droit de repondre")
	check(not _rival_owes_a_kick(true, 6, 4, 6, 3), "et une seule fois")
	done()


func test_pressure_is_the_kick_before_elimination_not_after_it() -> void:
	# 2-0, the rival about to take his third of five: scoring this one and the
	# next two still draws him level, so nothing is riding on it yet.
	check(not _rival_under_pressure(2, 2, 0), "il peut encore revenir, pas de pression")
	# Same taker one kick later: miss this one and the two he has left cannot
	# reach the player's two. He must score.
	check(_rival_under_pressure(2, 3, 0), "il doit marquer pour rester en vie")
	check(_rival_under_pressure(3, 3, 1), "mene 3-1 a une balle de la fin, il doit marquer aussi")
	# One step further and the series is simply over: the kick is never taken.
	check(_series_decided(4, 4, 3, 1), "un cran plus loin la seance est finie")
	# In sudden death, trailing by one at the same kick count is a must score.
	check(_rival_under_pressure(4, 5, 3), "en mort subite, mene d'un but, il doit marquer")
	check(not _rival_under_pressure(4, 5, 4), "a egalite en mort subite il tire pour gagner")
	done()


# --- The rival's kick, simulated -------------------------------------------

func test_the_reticle_inverse_matches_shot_model() -> void:
	# _rival_reticle restates the inverse of ShotModel.aim_point in closed form.
	# This is the guard: if that mapping ever moves, the CPU stops aiming where
	# the table says it aims, and this fails instead of the game going quietly
	# wrong.
	for pair: Array in [[0.0, 1.2], [2.95, 2.05], [-3.40, 0.30], [3.60, 0.14], [-1.10, 2.40]]:
		var world: Vector3 = ShotModel.aim_point(_rival_reticle(float(pair[0]), float(pair[1])))
		near(world.x, float(pair[0]), 0.001, "la visee du rival n'atterrit pas sur son x")
		near(world.y, float(pair[1]), 0.001, "la visee du rival n'atterrit pas sur son y")
	done()


func test_rival_simulation_is_deterministic() -> void:
	for i in 10:
		var s := 500_009 + i * 7919
		eq(_rival_verdict(s, CONFIRME, false), _rival_verdict(s, CONFIRME, false),
			"meme graine, meme niveau, meme verdict")
	# A seeded simulation must not be a constant either.
	var distinct := {}
	for i in 40:
		distinct[_rival_verdict(900_017 + i * 104_729, CONFIRME, false)] = true
	check(distinct.size() >= 2, "la simulation produit plusieurs issues")
	# The level is part of the answer: the same kick against a different keeper
	# is a different penalty, otherwise the setting would be decorative.
	var moved := 0
	for i in 24:
		var s := 700_001 + i * 15_485_863
		if _rival_verdict(s, DEBUTANT, false) != _rival_verdict(s, LEGENDE, false):
			moved += 1
	check(moved > 0, "le niveau du gardien doit changer le sort du tir adverse")
	done()


func test_rival_verdicts_stay_inside_the_enum() -> void:
	for i in 40:
		var verdict := _rival_verdict(310_007 + i * 7919, i % 4, i % 3 == 0)
		between(float(verdict), float(Verdict.BUT), float(Verdict.DEHORS),
			"verdict hors de l'enum")
	done()


func test_the_keeper_level_visibly_changes_the_rival_conversion() -> void:
	# THE POINT OF THE WHOLE SIMULATION. The rival kicks at the PLAYER'S OWN
	# goalkeeper, so the difficulty setting is not a handicap on one side, it is
	# the tempo of the shootout: an open one against a beginner, a grind against
	# a legend. Measured rates are about 74 % and 30 %; the bands are wide enough
	# that a couple of points of tuning drift is not a failure and a broken model
	# still is.
	var easy := _rival_goal_rate(110, DEBUTANT, false, 41_000_003)
	var hard := _rival_goal_rate(110, LEGENDE, false, 41_000_003)
	between(easy, 0.58, 0.90, "le rival doit marquer souvent contre un Debutant")
	between(hard, 0.14, 0.46, "le rival doit marquer rarement contre une Legende")
	check(easy > hard + 0.20,
		"le niveau du gardien doit se voir sur la serie adverse (%.2f contre %.2f)" % [easy, hard])
	done()


func test_pressure_lowers_the_rival_conversion() -> void:
	# The two runs share their seed line, so each pair is the same taker in the
	# same state of mind except for the nerves: the spread of his aim and how
	# often he mistimes the strike. Nothing touches the goalkeeper and nothing
	# touches the arithmetic of the series.
	var calm := _rival_goal_rate(140, CONFIRME, false, 52_000_011)
	var tense := _rival_goal_rate(140, CONFIRME, true, 52_000_011)
	check(tense < calm,
		"un tir sous elimination doit se rater plus souvent (%.2f contre %.2f)" % [tense, calm])
	between(calm - tense, 0.015, 0.25, "la chute sous pression doit rester mesuree")
	done()


func test_a_nervous_taker_misses_the_frame_more_often() -> void:
	# The pressure model is nerves, not a hidden percentage, so it has to change
	# the SHAPE of the misses and not only their count: a taker under that much
	# pressure balloons it over the bar rather than picking out a corner.
	var wide_calm := 0
	var wide_tense := 0
	for i in 120:
		var s := 63_000_017 + i * 7919
		if _rival_verdict(s, CONFIRME, false) == Verdict.DEHORS:
			wide_calm += 1
		if _rival_verdict(s, CONFIRME, true) == Verdict.DEHORS:
			wide_tense += 1
	check(wide_tense > wide_calm,
		"la pression doit envoyer plus de tirs hors du cadre (%d contre %d)" % [wide_tense, wide_calm])
	done()


func test_defi_scoring_rewards_the_streak() -> void:
	eq(_defi_award(Verdict.BUT, 0), DEFI_GOAL_POINTS, "un premier but vaut le tarif de base")
	eq(_defi_award(Verdict.BUT, 3), DEFI_GOAL_POINTS + 3 * DEFI_STREAK_BONUS, "la serie augmente la mise")
	eq(_defi_award(Verdict.POTEAU, 2), DEFI_FRAME_POINTS, "le poteau rapporte un lot de consolation")
	eq(_defi_award(Verdict.BARRE, 0), DEFI_FRAME_POINTS, "la barre aussi")
	eq(_defi_award(Verdict.ARRET, 5), 0, "un arret ne rapporte rien, meme en serie")
	eq(_defi_award(Verdict.DEHORS, 5), 0, "un tir a cote non plus")
	done()


func test_a_whole_series_alternates_and_terminates() -> void:
	# Plays four hundred complete shootouts through the exact turn rule the game
	# uses: the player kicks, then the rival kicks IF AND ONLY IF
	# _rival_owes_a_kick says so. This is the regression that matters most in
	# this file, because the bug it guards against was not a wrong number, it was
	# TWO CALLERS both taking the rival's kick: the CPU took two penalties for
	# every one of the player's, the two rows of the scoreboard grew at different
	# speeds, and the series ended on arithmetic nobody watching could follow.
	#
	# A cheap deterministic stand in stands for the verdicts: this test is about
	# the ORDER of the kicks, and simulating four hundred series of real
	# penalties would cost minutes. The simulation itself is checked above.
	for run in 400:
		var player: Array[int] = []
		var rival: Array[int] = []
		var rounds := 0
		var dead_kicks := 0
		while not _series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)):
			rounds += 1
			if rounds > 60:
				break
			player.append(_cheap_verdict(run * 131 + rounds * 17))

			# The rival's turn, asked for exactly the way take_rival_kick asks.
			var owed := _rival_owes_a_kick(true, player.size(), _goals_in(player),
				rival.size(), _goals_in(rival))
			if _series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)) and owed:
				dead_kicks += 1
			if owed:
				rival.append(_cheap_verdict(run * 977 + rounds * 29 + 1))

			check(rival.size() <= player.size(), "le rival ne peut jamais avoir tire plus que le joueur")
			check(player.size() - rival.size() <= 1, "le joueur ne peut pas prendre deux tirs d'avance")
		eq(dead_kicks, 0, "aucun tir adverse apres que la seance est jouee")
		check(rounds <= 60, "une seance doit se terminer en un nombre raisonnable de tours")
		check(_series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)),
			"la boucle ne s'arrete que sur une decision")
		check(absi(player.size() - rival.size()) <= 1, "les deux series restent alternees")
		ne(_goals_in(player), _goals_in(rival), "une seance decidee n'est jamais un match nul")
	done()


func test_the_pressure_branch_is_alive_over_a_whole_campaign() -> void:
	# The old model lowered the goal chance under elimination pressure and nobody
	# had ever checked the branch was reachable. It is: about one rival kick in
	# five over a full campaign. Anything near zero would mean the situation is
	# always caught by is_decided() first, and the model would be dead code.
	var kicks := 0
	var tense := 0
	for run in 400:
		var player: Array[int] = []
		var rival: Array[int] = []
		var rounds := 0
		while not _series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)):
			rounds += 1
			if rounds > 60:
				break
			player.append(_cheap_verdict(run * 313 + rounds * 19))
			if not _rival_owes_a_kick(true, player.size(), _goals_in(player),
					rival.size(), _goals_in(rival)):
				continue
			kicks += 1
			if _rival_under_pressure(_goals_in(player), rival.size(), _goals_in(rival)):
				tense += 1
			rival.append(_cheap_verdict(run * 751 + rounds * 23 + 1))
	check(kicks > 800, "l'echantillon de tirs adverses doit etre consequent (%d)" % kicks)
	var share := float(tense) / float(maxi(kicks, 1))
	between(share, 0.05, 0.40,
		"la pression doit etre une branche vivante, ni morte ni permanente (%.3f)" % share)
	done()


# --- Mode DUEL: the roles alternate, the rules do not ----------------------

func test_the_four_modes_all_have_a_label() -> void:
	var seen := PackedStringArray()
	for mode_id in 4:
		var label := _mode_label(mode_id)
		check(label.length() > 3, "un mode doit avoir un libelle lisible")
		check(not seen.has(label), "le libelle de mode '%s' est utilise deux fois" % label)
		seen.append(label)
	eq(_mode_label(3), "Duel", "le quatrieme mode est le duel")
	# DUEL is APPENDED and must stay at 3: the mode is persisted in the settings
	# file by NUMBER, so renumbering it restarts somebody's campaign elsewhere.
	eq(_mode_label(99), "Seance", "un mode inconnu retombe sur la seance")
	done()


func test_a_duel_alternates_taker_and_keeper() -> void:
	# The whole promise of the mode, on the rule itself rather than on a picture:
	# odd rounds the player shoots, even rounds he keeps. Nothing here is a duel
	# specific rule, and that is the point: it is rival_to_kick with the mode in
	# front of it, so a duel cannot invent a turn a seance would not owe.
	check(not _player_keeps(true, 0, 0, 0, 0), "au premier tour c'est le joueur qui tire")
	check(_player_keeps(true, 1, 1, 0, 0), "apres son tir, le joueur passe dans les buts")
	check(not _player_keeps(true, 1, 1, 1, 1), "et il ne garde pas deux tours de suite")
	check(_player_keeps(true, 2, 1, 1, 1), "troisieme tir joue, quatrieme tour garde")
	# The other three modes never hand him the gloves.
	check(not _player_keeps(false, 1, 1, 0, 0), "hors duel le joueur ne garde jamais")
	# And DUEL owes its kicks on exactly the same clock a SEANCE does.
	for shots in 5:
		eq(_player_keeps(true, shots + 1, shots, shots, shots),
			_rival_owes_a_kick(true, shots + 1, shots, shots, shots),
			"garder, c'est exactement le tour que le rival devait")
	done()


func test_a_decided_duel_never_plays_a_dead_round() -> void:
	# take_rival_kick_played answers -1 on exactly the same condition
	# take_rival_kick does, so a series already won is not followed by a penalty
	# the player would be asked to save for nothing.
	check(_series_decided(4, 4, 3, 0), "4-0 en quatre tirs contre trois : c'est plie")
	check(not _player_keeps(true, 4, 4, 3, 0), "une seance gagnee ne donne pas un tour a garder")
	check(not _player_keeps(true, 4, 0, 3, 4), "une seance perdue non plus")
	# Sudden death: the answering kick is owed, and he keeps for exactly one.
	check(_player_keeps(true, 6, 4, 5, 3), "en mort subite le joueur garde la reponse")
	check(not _player_keeps(true, 6, 4, 6, 3), "et une seule fois")
	done()


func test_a_whole_duel_alternates_sides_and_terminates() -> void:
	# The same regression this file already guards for a seance, played from both
	# ends: one line of the scoreboard per beat, never two, and never a beat after
	# the series is settled. The verdicts are the cheap stand in, because what is
	# under test is the ORDER of the turns and which side owns each of them.
	for run in 300:
		var player: Array[int] = []
		var rival: Array[int] = []
		var beats := 0
		var kept := 0
		var taken := 0
		var last_side_kept := true
		while not _series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)):
			beats += 1
			if beats > 60:
				break
			var keeping := _player_keeps(true, player.size(), _goals_in(player),
				rival.size(), _goals_in(rival))
			# Strict alternation: the same side never plays two beats running.
			check(keeping != last_side_kept, "les deux roles doivent alterner tour a tour")
			last_side_kept = keeping
			if keeping:
				kept += 1
				rival.append(_cheap_verdict(run * 977 + beats * 29 + 1))
			else:
				taken += 1
				player.append(_cheap_verdict(run * 131 + beats * 17))
			check(rival.size() <= player.size(), "le tireur adverse ne passe jamais devant")
			check(player.size() - rival.size() <= 1, "le joueur ne prend pas deux tirs d'avance")
		eq(kept, rival.size(), "chaque tour garde remplit exactement une case adverse")
		eq(taken, player.size(), "chaque tour tire remplit exactement une case du joueur")
		check(beats <= 60, "un duel doit se terminer en un nombre raisonnable de tours")
		check(_series_decided(player.size(), _goals_in(player), rival.size(), _goals_in(rival)),
			"la boucle ne s'arrete que sur une decision")
		ne(_goals_in(player), _goals_in(rival), "un duel decide n'est jamais un match nul")
	done()


# --- The taker moved out, and moved out WITHOUT MOVING ---------------------

func test_the_moved_taker_is_the_same_taker() -> void:
	# THE ONE GUARD THAT MATTERS FOR THE MOVE. The choice of penalty left this
	# file for TakerAi so that a duel and a seance kick with one taker. That is
	# only free if the moved code draws the SAME numbers in the SAME order: the
	# four measured rows of conversion in CONTRACTS 2.9 are a property of that
	# order and of nothing else. `_rival_plan` below is the shipped body, kept
	# here verbatim, and it is now the reference the production module is held to.
	for i in 24:
		var s := 880_003 + i * 7919
		var pressure := i % 3 == 0
		var rng := RandomNumberGenerator.new()
		rng.seed = s
		var mine := _rival_plan(rng, pressure)
		# The very next draw after the plan: the keeper's shuffle used to come off
		# this same stream, at this exact position.
		var dance := 0.30 + 0.70 * rng.randf()

		var theirs: Dictionary = TakerAi.choose(s, TakerAi.SEANCE_LEVEL, pressure, 0.0)
		var wanted: Vector2 = mine["aim"]
		var got: Vector2 = theirs.get("aim", Vector2(9.0, 9.0))
		near(got.x, wanted.x, 0.000001, "la visee du tireur deplace a bouge en x")
		near(got.y, wanted.y, 0.000001, "la visee du tireur deplace a bouge en y")
		near(float(theirs.get("power", 9.0)), float(mine["power"]), 0.000001,
			"la puissance du tireur deplace a bouge")
		near(float(theirs.get("release", 9.0)), float(mine["release"]), 0.000001,
			"la qualite de frappe du tireur deplace a bouge")
		near(float(theirs.get("side", 9.0)), 0.0, 0.000001,
			"le tireur d'une seance n'enroule pas")
		near(float(theirs.get("lift", 9.0)), 0.0, 0.000001,
			"le tireur d'une seance ne leve pas non plus")
		near(float(theirs.get("sweet_centre", 9.0)), _RIVAL_SWEET, 0.000001,
			"la fenetre de frappe propre a bouge")
		near(TakerAi.dance_phase(s, TakerAi.SEANCE_LEVEL, pressure), dance, 0.000001,
			"la danse du gardien ne sort plus au meme endroit du tirage")
	done()


func test_the_taker_only_ever_sees_the_keepers_x() -> void:
	# The line dance is worth doing, and it is not worth everything. A shade is
	# bounded and small against the width of the goal: a taker who always went to
	# the opposite corner would make the dance all powerful, which is the mirror
	# of the defect it exists to fix.
	var middle: Dictionary = TakerAi.read_keeper(0.0, TakerAi.Level.PRO, 4_242_001)
	near(float(middle.get("shift", 9.0)), 0.0, 0.000001,
		"un gardien au milieu ne deplace aucune intention")
	near(float(middle.get("rattle", 9.0)), 0.0, 0.000001,
		"et il ne trouble personne non plus")
	for level in 4:
		for x: float in [-0.9, -0.4, 0.4, 0.9]:
			var read: Dictionary = TakerAi.read_keeper(x, level, 4_242_001 + level)
			var shift := float(read.get("shift", 99.0))
			check(absf(shift) <= TakerAi.MAX_SHIFT + 0.000001,
				"le decalage de visee doit rester borne (%.2f m)" % shift)
			check(absf(shift) < Field.GOAL_HALF,
				"un decalage plus large que le but rendrait la danse toute puissante")
			between(float(read.get("rattle", 99.0)), 0.0, 1.0,
				"le trouble du tireur est une fraction")
	done()


## A deterministic verdict at roughly the conversion the simulation produces,
## used only where this suite is testing the ORDER of the kicks rather than
## their outcome. It is not a model of anything and nothing else may use it.
static func _cheap_verdict(key: int) -> int:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(key)
	var roll := rng.randf()
	if roll < 0.56:
		return Verdict.BUT
	if roll < 0.90:
		return Verdict.ARRET
	if roll < 0.96:
		return Verdict.DEHORS
	return Verdict.POTEAU
