extends Node
## Autoload `Shootout`: the state machine of the series, the score, the history.
##
## This node touches no 3D node and holds no reference to one. It knows numbers
## and verdicts, nothing else. That is deliberate: the rules of a shootout are
## the part of the game a player will argue about, so they live in one file that
## can be read top to bottom and copied into a test suite without dragging a
## scene tree along.
##
## The interesting rule is is_decided(). A shootout does not run for ten kicks,
## it runs until one side cannot be caught. During the five regulation kicks a
## side is out as soon as its opponent's lead exceeds the number of kicks it has
## left, which is why real shootouts often stop at 4-1. In sudden death the
## comparison is only legal when both sides have taken the SAME number of kicks,
## otherwise the team that kicked first would win every round it scored.
##
## THE SERIES ALTERNATES, AND ONE PLACE OWNS EACH KICK.
##
## record_shot() takes the player's kick and nothing else. take_rival_kick()
## takes the rival's, once, when the rival actually owes one. That separation is
## not tidiness: before it, record_shot() appended a rival kick AND Main appended
## a second one from its verdict timer, so the CPU took TWO kicks for every one
## of the player's. Five player kicks faced ten rival kicks, the scoreboard grew
## a row twice as long as the other, and the series ended on arithmetic nobody
## watching could follow. rival_to_kick() is now the single answer to "whose turn
## is it", the scoreboard draws it, and nothing takes a kick the rules do not owe.
##
## The rival is simulated rather than played, and simulated FOR REAL: see the
## block above _rival_verdict(). It is seeded from the campaign seed, so the same
## series replays identically.

signal phase_changed(previous: int, current: int)
signal shot_recorded(record: Dictionary)
signal series_changed()
signal match_finished(player_won: bool)

enum Mode { SEANCE, ENTRAINEMENT, DEFI }
enum Phase { ACCUEIL, PLACEMENT, VISEE, COURSE, VOL, VERDICT, REPLAY, FIN }
enum Verdict { BUT, ARRET, POTEAU, BARRE, DEHORS }

## Regulation shots per side before sudden death.
const REGULATION_SHOTS := 5

## A Defi run is a fixed number of attempts, then the points are counted.
const DEFI_SHOTS := 10

## Scoring of the Defi mode. A goal is worth more when it extends a streak, and
## rattling the frame is worth something because it was nearly a goal.
const DEFI_GOAL_POINTS := 100
const DEFI_STREAK_BONUS := 25
const DEFI_FRAME_POINTS := 25

var mode: int = Mode.SEANCE
var phase: int = Phase.ACCUEIL
var round_index: int = 0              # 0 based, counts the player's own attempts
var player_scores: Array[int] = []    # one Verdict per attempt, in order
var rival_scores: Array[int] = []     # the CPU team's attempts, same encoding
var streak: int = 0                   # consecutive goals, for the Defi mode
var best_streak: int = 0
var defi_points: int = 0

## Full record dictionaries, in order. The scoreboard only needs the verdicts,
## the replay and the end screen want the rest.
var _history: Array[Dictionary] = []

## Salt mixed into every rival seed, so one campaign does not replay the same
## five rival kicks in the same order forever.
var _series_salt: int = 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_draw_salt()


## The campaign seed lives in the Game autoload. It is read through the node
## path rather than through the global identifier on purpose: naming an autoload
## in a script makes that script impossible to compile under `--script`, and
## this file is worth keeping loadable from a bare tool run.
func _draw_salt() -> void:
	var game := get_node_or_null("/root/Game")
	if game != null:
		var value: Variant = game.get("seed_value")
		if typeof(value) == TYPE_INT and int(value) != 0:
			_series_salt = int(value)
			return
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	_series_salt = (rng.randi() & 0x7FFFFFFF) | 1


# --------------------------------------------------------------------------
# Pure helpers. These are the ones tests/test_match_state.gd copies verbatim.
# --------------------------------------------------------------------------

## French label of a verdict, for the HUD.
##
## These strings are drawn on screen, so they carry their accents. The rest of
## this file (symbols, comments, anything reaching the console) stays ASCII on
## purpose: the Windows console code page mangles accented output.
static func verdict_label(verdict: int) -> String:
	match verdict:
		Verdict.BUT:
			return "BUT !"
		Verdict.ARRET:
			return "Arrêt du gardien"
		Verdict.POTEAU:
			return "Poteau !"
		Verdict.BARRE:
			return "Barre transversale !"
		Verdict.DEHORS:
			return "À côté"
	return "Tir"


## True when the verdict put the ball in the net, rebound included. POTEAU and
## BARRE mean the frame sent the ball back OUT: a shot that hits the post and
## goes in is recorded as BUT, which is what "rebound included" means here.
static func is_goal(verdict: int) -> bool:
	return verdict == Verdict.BUT


## Goals inside a list of verdicts.
static func _goals_in(scores: Array[int]) -> int:
	var total := 0
	for verdict in scores:
		if verdict == Verdict.BUT:
			total += 1
	return total


## The actual football rule, on plain integers so it can be copied into a test.
## `player_shots` / `rival_shots` are the number of kicks TAKEN by each side.
static func _series_decided(player_shots: int, player_goals_count: int, rival_shots: int, rival_goals_count: int) -> bool:
	if player_shots >= REGULATION_SHOTS and rival_shots >= REGULATION_SHOTS:
		# Sudden death: only comparable when both have kicked the same number of
		# times, otherwise the side that kicks first wins on an incomplete round.
		return player_shots == rival_shots and player_goals_count != rival_goals_count
	var player_left := maxi(0, REGULATION_SHOTS - player_shots)
	var rival_left := maxi(0, REGULATION_SHOTS - rival_shots)
	if player_goals_count > rival_goals_count + rival_left:
		return true
	if rival_goals_count > player_goals_count + player_left:
		return true
	return false


# --------------------------------------------------------------------------
# The rival's kick, simulated for real
# --------------------------------------------------------------------------
#
# This used to be one call to randf() against a fixed 0.745 goal chance. It read
# as arbitrary from the player's seat because it WAS arbitrary: nothing on
# screen and nothing the player had chosen could touch it. The difficulty could
# be turned up to LEGENDE and the opponent still scored three out of four.
#
# It is a real penalty now. A seeded CPU aim, power and contact go through
# ShotModel, the ball flies through Aero at the project's own 120 Hz step, the
# woodwork and the goal line are Field's, and the shot is defended by
# KeeperBrain AT THE PLAYER'S OWN KEEPER LEVEL. Everything below is an INPUT to
# that simulation. The conversion rate is an OUTPUT of it and is written down
# nowhere. Measured over 900 kicks per level:
#
#   niveau      buts    arrets   poteau/barre   hors cadre
#   Debutant   74.5 %   19.5 %       3.5 %         2.5 %
#   Confirme   55.9 %   38.3 %       3.6 %         2.2 %
#   Pro        43.3 %   49.8 %       4.0 %         2.9 %
#   Legende    29.8 %   67.0 %       1.8 %         1.3 %
#
# Cross checked against tests/balance_probe.gd, which fires the same kind of
# penalty at the REAL Keeper node: on clean strikes with realistic aim it
# reports 20.5 / 35.7 / 46.7 / 62.5 percent of saves, against 19.5 / 38.3 /
# 49.8 / 67.0 here. The offline keeper below is therefore a faithful model of
# the one standing on the pitch, and the few points of difference are the tenth
# of the CPU kicks that are deliberately mishit.
#
# THE CONSEQUENCE IS THE POINT OF THE WHOLE CHANGE: both sides now face the SAME
# goalkeeper, so the difficulty setting stopped being the player's handicap and
# became the TEMPO of the shootout. A Debutant series is an open 4-4, a Legende
# series is a 1-1 grind, and neither of them is rigged.
#
# Why the loop is written here rather than reused from `Keeper`: that is a Node,
# and this file is forbidden from touching one (see the class comment). What
# follows is the same decision loop expressed against KeeperBrain alone, and the
# cross check above is what keeps the two honest.

## Physics step of the simulated kick. The project's own: a save that happens
## here happens at the instant it would happen on the pitch.
const _RIVAL_STEP := 1.0 / 120.0
## A penalty is over in well under a second. This is the runaway guard.
const _RIVAL_MAX_STEPS := 600
## Mirrors Ball.TURF_RESTITUTION / TURF_FRICTION, for a mishit that lands short.
const _RIVAL_TURF_RESTITUTION := 0.45
const _RIVAL_TURF_FRICTION := 0.42
## Physics steps between two of the keeper's re estimates of the flight. The
## real Keeper re estimates every single step, which costs about 23 ms of CPU
## per simulated penalty here; every second step costs 10 ms and moves the save
## rates by under two points (measured). Sixteen milliseconds of ball flight is
## also about as often as a human eye updates, so this is a defensible model of
## him rather than a corner cut: the alternative was a visible hitch on screen
## at the exact moment the rival's turn is announced.
const _RIVAL_ESTIMATE_EVERY := 2

## Mirrors of the four constants Keeper drives its own commit decision with. They
## are small numbers rather than shared state because this file may not reference
## that node; tests/test_match_state.gd copies them with the rest.
const _RIVAL_HOME_TARGET := Vector3(0.0, 1.25, 0.0)
const _RIVAL_DIVE_POSE_MAX := 1.60
const _RIVAL_LINE_BLEND := 0.16
const _RIVAL_COMMIT_MARGIN := 0.03
const _RIVAL_CONFIDENT_ERROR := 0.16

## Where the CPU taker's clean contact window sits on its own power bar. Same
## value Main uses for a scripted shot, so a rival kick and a probe kick are
## struck by the same model.
const _RIVAL_SWEET := 0.72

## Inverse of ShotModel.aim_point, which is affine on each axis and therefore
## invertible in closed form. Restated here rather than searched for by
## bisection, and guarded by a round trip check in tests/test_match_state.gd: if
## ShotModel ever remaps its reticle, that check fails instead of this file
## quietly aiming the CPU somewhere else.
const _RIVAL_AIM_SPAN_X := 4.40      # Field.GOAL_HALF + ShotModel's side margin
const _RIVAL_AIM_BASE_Y := 0.11      # Field.BALL_RADIUS
const _RIVAL_AIM_TOP_Y := 3.04       # Field.GOAL_HEIGHT + ShotModel's top margin

## WHERE THE CPU TAKER SHOOTS, in metres on the goal line, and how badly he
## misses. One row is [weight, mean |x|, sigma x, mean y, sigma y], the sign of x
## drawn evenly so neither post is favoured. The sigma IS the error: there is no
## second fudge factor anywhere.
##
## This is the same table as balance_probe's AIM_CLUSTERS, deliberately: the
## rival shoots the way the reference sample says people shoot, so the rate that
## comes out of the simulation is comparable with the one the probe reports for
## the player. Half the kicks are placed to a side at or below the waist, a fifth
## are half hearted half side shots, a fifth are genuine attempts at the angle of
## the bar, the rest go down the middle.
const _RIVAL_AIM: Array = [
	[0.30, 2.15, 0.52, 0.72, 0.34],
	[0.20, 1.20, 0.45, 0.95, 0.42],
	[0.16, 0.10, 0.52, 0.85, 0.45],
	[0.22, 2.55, 0.50, 1.82, 0.42],
	[0.12, 0.25, 0.85, 1.80, 0.38],
]
## The reticle stops here. Past it the kick is simply wide or over, which is a
## legal and counted outcome.
const _RIVAL_MAX_X := 4.10
const _RIVAL_MIN_Y := 0.14
const _RIVAL_MAX_Y := 2.90
## Pace of a CPU penalty, as a power in [0, 1] on ShotModel's own bar.
const _RIVAL_POWER_MEAN := 0.80
const _RIVAL_POWER_SIGMA := 0.11
const _RIVAL_POWER_MIN := 0.45
## How often he mistimes the strike when nothing is at stake.
const _RIVAL_MISCUE_CALM := 0.10

## NERVES, AND WHY THEY ARE A REAL THING RATHER THAN A HIDDEN PERCENTAGE.
##
## A kick that must be scored to stay in the tie really is converted worse than a
## kick to win, and the old model expressed that by quietly subtracting eleven
## points from a goal chance the player could not see. It is expressed here as
## what actually happens to a nervous penalty taker: his aim spreads (the sigmas
## of the table above are multiplied by _RIVAL_NERVE) and he mistimes the strike
## far more often (_RIVAL_MISCUE_TENSE instead of _RIVAL_MISCUE_CALM). Nothing
## touches the goalkeeper, and nothing touches the arithmetic.
##
## Measured over 900 kicks per level, the drop that comes out is about seven
## points of conversion (Confirme 55.9 % -> 49.0 %, Pro 43.3 % -> 36.7 %), and
## the SHAPE of the misses changes too: shots off the frame go from 2.2 % to
## 11.7 %, because a taker under that much pressure balloons it rather than
## picking out a corner. That is the version of the model a player can see
## happening, which is why it replaced the invisible one.
##
## It fires on about one rival kick in five over a full campaign (18.2 %
## measured over 20 000 simulated series), so it is a live branch, not decoration.
## The situation is announced BEFORE the kick, by rival_must_score(): the
## scoreboard and the HUD both say so.
const _RIVAL_NERVE := 1.90
const _RIVAL_MISCUE_TENSE := 0.28


## One simulated rival kick. Seeded, therefore reproducible.
##
## `keeper_level` is a KeeperBrain.Level, and it is the PLAYER'S setting: the
## rival kicks at the same goalkeeper the player does. `pressure` is the
## elimination kick described above.
static func _rival_verdict(rng_seed: int, keeper_level: int, pressure: bool) -> int:
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed
	var level := clampi(keeper_level, 0, 3)
	var plan := _rival_plan(rng, pressure)
	# The keeper has been shuffling on his line since the taker put the ball
	# down. Where that shuffle has carried him is part of the penalty.
	var dance: float = 0.30 + 0.70 * rng.randf()
	return _rival_flight(plan, level, rng_seed, dance)


## The CPU's intention: where he is aiming, how hard, and how well he strikes it.
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


## Normalized reticle for a point of the goal line. See _RIVAL_AIM_SPAN_X.
static func _rival_reticle(world_x: float, world_y: float) -> Vector2:
	return Vector2(
		world_x / _RIVAL_AIM_SPAN_X,
		(world_y - _RIVAL_AIM_BASE_Y) / (_RIVAL_AIM_TOP_Y - _RIVAL_AIM_BASE_Y))


## The kick itself: one whole penalty, resolved in the order Main resolves a
## real one. The frame ends the flight here, where in the game a rebound can
## still go in; a rebound off the woodwork straight back into the net is rare
## enough that counting it as a post keeps this readable, and POTEAU already
## means "the frame sent it back out" everywhere else in the file.
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

		# 1. The woodwork.
		var frame: Dictionary = Field.sweep_frame(position, to_point)
		if bool(frame.get("hit", false)):
			if int(frame.get("part", Field.FRAME_NONE)) == Field.FRAME_BAR:
				return Verdict.BARRE
			return Verdict.POTEAU

		# 2. The keeper decides. He is blind for his own reaction time unless he
		# already committed during the run up, and then he holds until the last
		# responsible moment, exactly as Keeper._should_commit does.
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

		# 3. The keeper's body. The shuffle he walked to bleeds out of the pose
		# early in the flight, which is what Keeper does with LINE_BLEND.
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

		# 4. The goal line.
		var cross: Dictionary = Field.cross_goal_plane(position, to_point)
		if bool(cross.get("crossed", false)):
			var point: Vector3 = cross.get("point", to_point)
			return Verdict.BUT if Field.is_within_frame(point) else Verdict.DEHORS

		if Field.is_out_of_area(to_point):
			return Verdict.DEHORS

		# 5. The turf, for a scuffed kick that lands before the line.
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


## The coiled pose the keeper holds between the strike and his commit, standing
## at `x` on his line. Mirrors Keeper._set_pose over the brain's standing pose.
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


## Slides a whole pose sideways by `dx`. It ADDS, it does not snap the body to a
## position: a dive that gets snapped back onto the middle of the line never
## travels anywhere, and a keeper who never travels saves nothing but the shots
## already aimed at him. That mistake, made once while this was being written,
## cost the Legende keeper twenty five points of save rate.
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


## True when the side that has taken `rival_shots` kicks and scored
## `rival_goals_count` cannot survive missing the next one. Pure, so the suite
## can copy it: it is the exact condition the nerves above key on.
##
## It is one step short of the elimination condition in _series_decided, and that
## is the whole point: _series_decided fires when the tie is ALREADY lost, this
## fires on the kick that decides whether it will be.
static func _rival_under_pressure(player_goals_count: int, rival_shots: int,
		rival_goals_count: int) -> bool:
	var left_after := maxi(0, REGULATION_SHOTS - rival_shots - 1)
	return rival_goals_count + left_after < player_goals_count


## Points a Defi attempt is worth, given the streak BEFORE the attempt.
static func _defi_award(verdict: int, streak_before: int) -> int:
	if verdict == Verdict.BUT:
		return DEFI_GOAL_POINTS + DEFI_STREAK_BONUS * streak_before
	if verdict == Verdict.POTEAU or verdict == Verdict.BARRE:
		return DEFI_FRAME_POINTS
	return 0


# --------------------------------------------------------------------------
# Series
# --------------------------------------------------------------------------

func start_match(new_mode: int) -> void:
	reset()
	mode = clampi(new_mode, Mode.SEANCE, Mode.DEFI)
	_draw_salt()
	series_changed.emit()
	set_phase(Phase.PLACEMENT)


func set_phase(new_phase: int) -> void:
	var wanted := clampi(new_phase, Phase.ACCUEIL, Phase.FIN)
	if wanted != new_phase:
		push_warning("Shootout: phase invalide %d." % new_phase)
	if wanted == phase:
		return
	var previous := phase
	phase = wanted
	phase_changed.emit(previous, phase)


## Records the player's attempt and advances the series.
func record_shot(record: Dictionary) -> void:
	if not record.has("verdict"):
		push_error("Shootout: record_shot sans verdict, tir ignore.")
		return
	var verdict := clampi(int(record["verdict"]), Verdict.BUT, Verdict.DEHORS)

	player_scores.append(verdict)
	_history.append(record)

	var awarded := _defi_award(verdict, streak)
	if is_goal(verdict):
		streak += 1
		best_streak = maxi(best_streak, streak)
	else:
		streak = 0
	if mode == Mode.DEFI:
		defi_points += awarded

	shot_recorded.emit(record)

	round_index = player_scores.size()
	series_changed.emit()

	# The rival is NOT kicked here. He takes his turn through take_rival_kick(),
	# as his own beat of the presentation, because a shootout is two alternating
	# turns and both of them have to be visible. See the class comment.
	#
	# The phase is NOT forced here either. Main owns the presentation order
	# (verdict banner, replay, the rival's turn, then the result screen), this
	# node only says when the series is over.
	if is_decided():
		match_finished.emit(player_goals() >= rival_goals())


## True when the rival still owes a kick right now: a shootout in progress, the
## player one kick ahead, and a tie that is still alive. This is the single
## answer to "whose turn is it", and the scoreboard draws it.
func rival_to_kick() -> bool:
	if mode != Mode.SEANCE:
		return false
	if is_decided():
		return false
	return rival_scores.size() < player_scores.size()


## True when the rival's NEXT kick has to be scored to keep the tie alive. Read
## by the HUD and the scoreboard, so the pressure the simulation applies is
## announced before it is applied rather than hidden inside a goal chance.
func rival_must_score() -> bool:
	if not rival_to_kick():
		return false
	return _rival_under_pressure(player_goals(), rival_scores.size(), rival_goals())


## Takes the rival's turn, once. Returns the Verdict, or -1 when he owes no kick,
## which is the case the rules care about: NOBODY TAKES A KICK THAT CANNOT
## CHANGE THE RESULT, so a series already decided ends here rather than playing
## out a dead round.
##
## Appends to rival_scores, then emits series_changed, and match_finished if this
## kick settled it. The caller never appends anything itself.
func take_rival_kick() -> int:
	if not rival_to_kick():
		return -1
	var verdict := simulate_rival_shot(_rival_seed())
	rival_scores.append(verdict)
	series_changed.emit()
	if is_decided():
		match_finished.emit(player_goals() >= rival_goals())
	return verdict


func player_goals() -> int:
	return _goals_in(player_scores)


func rival_goals() -> int:
	return _goals_in(rival_scores)


## Seed of the rival's next kick: stable for a given salt and round.
func _rival_seed() -> int:
	return hash(Vector2i(_series_salt, rival_scores.size() + 1))


## Seeded simulation of one CPU attempt against the player's own keeper.
##
## Pure with respect to the series: it reads the score and the settings, it never
## writes anything. take_rival_kick() is what turns the answer into a kick.
##
## The old model carried a third modifier for sudden death. It is gone, and not
## by accident: in sudden death every kick is either one that must be scored to
## survive, which the pressure flag below already catches, or one to win, which
## is not a kick under pressure at all. The separate constant was subtracting
## three points from both cases without distinguishing them.
func simulate_rival_shot(rng_seed: int) -> int:
	var pressure := _rival_under_pressure(
		player_goals(), rival_scores.size(), rival_goals())
	return _rival_verdict(rng_seed, _keeper_level(), pressure)


## The player's own keeper level, a KeeperBrain.Level. Read through the node path
## for the same reason _draw_salt does it: naming an autoload makes this file
## impossible to compile under `--script`, and it is worth keeping loadable from
## a bare tool run. Falls back to CONFIRME, the settings default.
func _keeper_level() -> int:
	var game := get_node_or_null("/root/Game")
	if game != null:
		var value: Variant = game.get("keeper_level")
		if typeof(value) == TYPE_INT:
			return clampi(int(value), 0, 3)
	return 1


## True when neither side can catch up any more.
func is_decided() -> bool:
	match mode:
		Mode.SEANCE:
			return _series_decided(player_scores.size(), player_goals(), rival_scores.size(), rival_goals())
		Mode.DEFI:
			return player_scores.size() >= DEFI_SHOTS
	# Training never ends: the player leaves through the menu.
	return false


## Free text of the situation, in French. Player facing, therefore accented.
func pressure_text() -> String:
	if mode == Mode.ENTRAINEMENT:
		return "Entraînement libre"
	if mode == Mode.DEFI:
		if is_decided():
			return "Défi terminé : %d points" % defi_points
		return "Défi : tir %d sur %d" % [player_scores.size() + 1, DEFI_SHOTS]

	if is_decided():
		return "Séance terminée" if player_goals() != rival_goals() else "Égalité"

	var taken := player_scores.size()
	var mine := player_goals()
	var theirs := rival_goals()
	var rival_left := maxi(0, REGULATION_SHOTS - rival_scores.size())
	var mine_left_after := maxi(0, REGULATION_SHOTS - taken - 1)

	# The rival's turn is a situation of its own and it comes first, because it
	# is the one the player is watching. Saying "l'adversaire doit marquer" out
	# loud is what makes the nerves the simulation applies to that kick visible
	# instead of being a number nobody can see.
	if rival_to_kick():
		if rival_must_score():
			return "L'adversaire doit marquer"
		if theirs + 1 > mine + mine_left_after and taken >= REGULATION_SHOTS:
			return "L'adversaire tire pour gagner"
		return "Au tour de l'adversaire"

	if taken >= REGULATION_SHOTS and rival_scores.size() >= REGULATION_SHOTS:
		return "Mort subite"
	if mine + 1 > theirs + rival_left:
		return "Marquez pour gagner"
	if mine + mine_left_after < theirs:
		return "Tir décisif"
	if mine == theirs:
		return "Égalité %d - %d" % [mine, theirs]
	if mine > theirs:
		return "Vous menez %d - %d" % [mine, theirs]
	return "Vous êtes mené %d - %d" % [mine, theirs]


## Everything the scoreboard needs, in one dictionary.
func summary() -> Dictionary:
	var mine := player_goals()
	var theirs := rival_goals()
	return {
		"mode": mode,
		"phase": phase,
		"round": round_index,
		"player": player_scores.duplicate(),
		"rival": rival_scores.duplicate(),
		"player_goals": mine,
		"rival_goals": theirs,
		"player_shots": player_scores.size(),
		"rival_shots": rival_scores.size(),
		"regulation": REGULATION_SHOTS,
		"sudden_death": player_scores.size() >= REGULATION_SHOTS and rival_scores.size() >= REGULATION_SHOTS,
		"rival_to_kick": rival_to_kick(),
		"rival_must_score": rival_must_score(),
		"decided": is_decided(),
		"player_won": mine >= theirs,
		"streak": streak,
		"best_streak": best_streak,
		"points": defi_points,
		"pressure": pressure_text(),
		"history": _history.size(),
	}


## Every record kept so far, newest last. The end screen walks it.
func history() -> Array[Dictionary]:
	return _history.duplicate()


func reset() -> void:
	round_index = 0
	player_scores.clear()
	rival_scores.clear()
	_history.clear()
	streak = 0
	best_streak = 0
	defi_points = 0
	set_phase(Phase.ACCUEIL)
	series_changed.emit()
