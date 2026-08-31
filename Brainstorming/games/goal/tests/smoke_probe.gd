extends Node
## In-game integration probe.
##
##   godot --headless --path . -- --smoke
##
## The unit suites under tests/ run with --script, and Godot does not register
## the project autoloads in that context, so nothing that needs Game, Shootout or
## Sfx can be tested there. This file exists to cover exactly that gap: Main
## instantiates it during the real boot, calls setup(self), adds it as a child,
## and lets it drive. Everything it touches is therefore the real game, with the
## real autoloads, the real physics tick and the real scene tree.
##
## Two design rules follow from that, and both matter.
##
## 1. It never names an autoload. Main exposes the handful of `_probe_*` helpers
##    it needs, so this file stays loadable in any context. The Shootout.Verdict
##    ids are mirrored as plain integers here and cross checked against Main on
##    the first frame, so a renumbering of the enum is caught rather than
##    silently changing what "BUT" means.
##
## 2. It asserts INVARIANTS, not first-frame state. A probe that reads a value
##    one frame after boot measures the constructor, not the game. So it waits
##    for the world to be built, fires reproducible penalties through
##    Main.fire_test_shot, and only judges once a shot has actually resolved.
##
## The shots are chosen so that each one can only pass for the right reason:
##   - a full power strike into the top corner against a Debutant keeper must be
##     a goal, AND GoalFrame.net_bulge() must prove the cords really moved;
##   - a soft shot straight down the middle against a Legende must be saved;
##   - a soft shot at glove height against a Legende must be saved AND CAUGHT,
##     with the ball still in his hands when the verdict comes up;
##   - a shot aimed a metre outside the post must be DEHORS;
##   - a heavily curled shot must still produce a finite, bounded flight.
## Between every shot the ball must be back on the spot and the keeper back on
## its line, and the number of goals Shootout recorded must equal the number of
## BUT verdicts actually observed.
##
## EVERY save, whichever shot produced it, is then judged on the picture and not
## only on the scoreline, by _evaluate_save(). That assertion exists because of a
## real bug: the keeper got a hand to the ball, "Arret du gardien" came up, and
## the ball carried on into the net while the player watched. The verdict was
## right and the game looked broken. See the rebound rule in Main's header.
##
## Exits 0 when every assertion holds, 1 otherwise, after a French report.

# --- Stages ------------------------------------------------------------------

const STAGE_BOOT := 0
const STAGE_ARM := 1
const STAGE_FLIGHT := 2
const STAGE_NET := 3
const STAGE_RESET := 4
## The keeper's side of a DUEL round. The first three run in free training, where
## the series records nothing and a round can therefore be repeated as often as
## the invariants need; the last two run inside a REAL duel, which is the only
## place the bookkeeping means anything.
const STAGE_DUEL_ARM := 5
const STAGE_DUEL_FLIGHT := 6
const STAGE_DUEL_SERIES := 7
const STAGE_DUEL_TAKE := 8
const STAGE_DUEL_KEEP := 9
## Mode GARDIEN, the keeper's free training. Played UNATTENDED and through the
## real loop: see _tick_train.
const STAGE_TRAIN := 10
const STAGE_REPORT := 11
const STAGE_DONE := 12

# --- Verdict ids, mirrored from Shootout.Verdict -----------------------------

const V_BUT := 0
const V_ARRET := 1
const V_POTEAU := 2
const V_BARRE := 3
const V_DEHORS := 4
const V_ANY := -1

# --- Keeper levels, mirrored from KeeperBrain.Level --------------------------

const L_DEBUTANT := 0
const L_CONFIRME := 1
const L_PRO := 2
const L_LEGENDE := 3

# --- Budgets -----------------------------------------------------------------

## Frames given to the world builders before anything is judged.
const BOOT_FRAMES := 120
const BOOT_TIMEOUT := 60.0
const ARM_TIMEOUT := 20.0
const FLIGHT_TIMEOUT := 30.0
const RESET_TIMEOUT := 20.0
## Seconds spent watching the net after a shot resolves, so the Verlet wave has
## time to reach its deepest point.
const NET_WATCH := 0.45
## Deepest net displacement, in metres, that counts as "the net moved".
const NET_PROOF := 0.008
## How far a held ball may sit from the glove that took it, metres, measured
## against the point KeeperBrain.dive_pose asked for.
##
## Generous on purpose, and the reason is worth knowing: the keeper holds the
## ball on the hand he actually DREW, and at full stretch the arm solve stops
## short of the brain's target by up to a quarter of a metre (Keeper.MAX_STRETCH).
## Those are exactly the poses a diving save happens on. So this budget is a
## stretched arm's shortfall plus the palm offset, and it is still an order of
## magnitude tighter than the "the ball is somewhere else entirely" it exists to
## catch: a ball that flew on into the net lands metres from any glove.
const HOLD_REACH := 0.55
## How far a glove may sink into the ball it is holding, in metres. Not zero: a
## padded glove closing on a ball squashes both, and a hand drawn exactly tangent
## reads as a ball balanced on a fingertip rather than as a ball gripped. Five
## millimetres is a compression nobody can see. Thirty is the defect this exists
## to catch, where the fingers came out of the far side.
const MITT_SLACK := 0.005

# --- Mode DUEL ----------------------------------------------------------------

## Level both ends of the duel are played at. Pro rather than Legende: the point
## is to measure the MODE, and a Legende body would make the "too late" round pass
## for its athleticism rather than for the arithmetic under test.
const DUEL_LEVEL := L_PRO
## When the player commits, in seconds relative to contact. The early one is a
## genuine gamble made during the run up; the late one is the reaction a human
## cannot afford, and the whole mode lives in the gap between them.
const DUEL_EARLY := -0.30
const DUEL_LATE := 0.20
## Kept rounds played unattended in the keeper's training mode. Three, because
## the properties under test are that the mode LOOPS and that consecutive rounds
## are DIFFERENT penalties, and two rounds cannot tell a loop from a coincidence.
const TRAIN_ROUNDS := 3
const TRAIN_TIMEOUT := 120.0
## Metres two taker targets must differ by to count as two different penalties.
## A centimetre: the point is to prove the seed MOVED, not to measure how far.
const TRAIN_SPREAD := 0.01

## Seeds walked while looking for a CPU penalty the two commits disagree about.
const DUEL_SEED_START := 7_000_003
const DUEL_SEED_STRIDE := 7919
const DUEL_SEED_TRIES := 600

var _main: Node = null
var _stage: int = STAGE_BOOT
var _stage_time: float = 0.0
var _stage_frames: int = 0

var _plan: Array[Dictionary] = []
var _shot_index: int = -1
var _current: Dictionary = {}
var _launch: Dictionary = {}

var _observed: Array[int] = []
var _net_peak: float = 0.0
var _flight_ok: bool = true
## Saves seen, and how many of them were clean catches. A run that never catches
## anything would quietly pass every assertion below, so the count is asserted.
var _saves_seen: int = 0
var _catches_seen: int = 0

## Kept rounds: what to play, what came back, and what was seen.
var _duel_plan: Array[Dictionary] = []
var _duel_index: int = -1
var _duel_live: Dictionary = {}
var _duel_seen: Array[int] = []
var _duel_series: Dictionary = {}
var _duel_rival_before: int = 0

## Keeper training: whether the session has been opened, how many penalties have
## been faced, and where each of them was aimed.
var _train_started: bool = false
var _train_seen: int = 0
var _train_targets: Array[Vector3] = []
var _duel_series_fired: bool = false
var _series_checked: bool = false

var _report: PackedStringArray = PackedStringArray()
var _checks: int = 0
var _failures: int = 0

# World bounds a legal flight can never leave. Generous on purpose: this catches
# a divergent integrator, not a slightly long clearance.
var _limit_x: float = 0.0
var _limit_y_low: float = 0.0
var _limit_y_high: float = 0.0
var _limit_z_low: float = 0.0
var _limit_z_high: float = 0.0


## Called by Main before this node is added to the tree.
func setup(main_node: Node) -> void:
	_main = main_node


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_limit_x = Field.PITCH_HALF_X + 8.0
	_limit_y_low = -3.0
	_limit_y_high = 50.0
	_limit_z_low = Field.PITCH_MIN_Z - 10.0
	_limit_z_high = Field.PITCH_MAX_Z + 10.0
	_line("")
	_line("=== GOAL - sonde d'integration ===")


func _process(delta: float) -> void:
	_stage_time += delta
	_stage_frames += 1

	if _stage == STAGE_BOOT:
		_tick_boot()
	elif _stage == STAGE_ARM:
		_tick_arm()
	elif _stage == STAGE_FLIGHT:
		_tick_flight()
	elif _stage == STAGE_NET:
		_tick_net()
	elif _stage == STAGE_RESET:
		_tick_reset()
	elif _stage == STAGE_DUEL_ARM:
		_tick_duel_arm()
	elif _stage == STAGE_DUEL_FLIGHT:
		_tick_duel_flight()
	elif _stage == STAGE_DUEL_SERIES:
		_tick_duel_series()
	elif _stage == STAGE_DUEL_TAKE:
		_tick_duel_take()
	elif _stage == STAGE_DUEL_KEEP:
		_tick_duel_keep()
	elif _stage == STAGE_TRAIN:
		_tick_train()
	elif _stage == STAGE_REPORT:
		_finish()


func _goto(stage: int) -> void:
	_stage = stage
	_stage_time = 0.0
	_stage_frames = 0


# =============================================================================
# Stages
# =============================================================================

func _tick_boot() -> void:
	if _main == null:
		_fail("Main n'a pas appele setup() sur la sonde")
		_goto(STAGE_REPORT)
		return
	if _stage_time > BOOT_TIMEOUT:
		_fail("le monde n'est pas construit apres %.0f s" % BOOT_TIMEOUT)
		_goto(STAGE_REPORT)
		return
	if not bool(_main.call("_probe_world_ready")):
		return
	if _stage_frames < BOOT_FRAMES:
		return

	_check_enum_alignment()
	_check_world_built()
	_build_plan()

	_main.call("_probe_begin_training")
	_goto(STAGE_ARM)


func _tick_arm() -> void:
	if _stage_time > ARM_TIMEOUT:
		_fail("le jeu n'est jamais revenu en phase de placement")
		_goto(STAGE_REPORT)
		return
	# Only fire from a settled state: ball on the spot, keeper on its line, no
	# flight running. Firing mid flight would measure two shots at once.
	if not bool(_main.call("_probe_ready_to_fire")):
		return
	if _stage_time < 0.2:
		return

	_shot_index += 1
	if _shot_index >= _plan.size():
		_enter_duel_section()
		return

	_current = _plan[_shot_index]
	_net_peak = 0.0
	_flight_ok = true

	_main.call("_probe_set_keeper_level", int(_current.get("level", L_CONFIRME)))
	_launch = _main.call("fire_test_shot",
		_current.get("aim", Vector2.ZERO),
		float(_current.get("power", 0.8)),
		float(_current.get("side", 0.0)),
		float(_current.get("lift", 0.0)))
	_goto(STAGE_FLIGHT)


func _tick_flight() -> void:
	_watch_flight()

	if _stage_time > FLIGHT_TIMEOUT:
		_fail("%s : le tir ne s'est jamais resolu (%.0f s)" % [_shot_name(), FLIGHT_TIMEOUT])
		_observed.append(V_DEHORS)
		_goto(STAGE_RESET)
		return

	if not bool(_main.call("_probe_shot_settled")):
		return

	_evaluate_shot()
	_goto(STAGE_NET)


func _tick_net() -> void:
	_watch_flight()
	if _stage_time < NET_WATCH:
		return
	_evaluate_net()
	_goto(STAGE_RESET)


func _tick_reset() -> void:
	_watch_flight()
	if _stage_time > RESET_TIMEOUT:
		_fail("%s : le jeu ne s'est pas remis en place apres le tir" % _shot_name())
		_goto(STAGE_REPORT)
		return

	var placement: bool = bool(_main.call("_probe_phase_is_placement"))
	if not placement:
		return
	if _stage_time < 0.15:
		return

	_evaluate_reset()
	if _shot_index + 1 >= _plan.size():
		_enter_duel_section()
	else:
		_goto(STAGE_ARM)


# =============================================================================
# Mode DUEL, from the keeper's side
# =============================================================================
#
# Five stages, and they answer five questions the mode cannot ship without:
#
#   1. does the CPU penalty actually FLY? A defended penalty must be a real
#      flight the player watches, not a dice roll dressed up as one, so the ball's
#      own log is walked exactly as it is for the player's shots;
#   2. does an early commit in the right corner SAVE a placed penalty?
#   3. does the SAME dive committed too late fail to? That pair is the whole mode:
#      you cannot wait and react, and if both commits saved, waiting would be free;
#   4. does a saved ball stay in front of the line, the way it must on a
#      player's own save (see _evaluate_save)?
#   5. does a kept round grow the CPU row by EXACTLY ONE, and never a round the
#      rules do not owe?
#
# The first four run in free training, where nothing is recorded and a round can
# be repeated as often as needed. The fifth needs a real series and gets one.

## Closes the shooting side and opens the keeper's. The series bookkeeping is
## checked HERE and not in the report, because the duel section deliberately
## starts a new match and would otherwise be compared against another one's score.
func _enter_duel_section() -> void:
	if not _series_checked:
		_series_checked = true
		_check_series()
	_build_duel_plan()
	_goto(STAGE_DUEL_ARM)


func _tick_duel_arm() -> void:
	if _stage_time > ARM_TIMEOUT:
		_fail("duel : le jeu n'est jamais revenu en position de garder")
		_goto(STAGE_REPORT)
		return
	if not bool(_main.call("_probe_ready_to_fire")):
		return
	if _stage_time < 0.2:
		return

	_duel_index += 1
	if _duel_index >= _duel_plan.size():
		_goto(STAGE_DUEL_SERIES)
		return

	_current = _duel_plan[_duel_index]
	_flight_ok = true
	_main.call("_probe_set_keeper_level", int(_current.get("level", DUEL_LEVEL)))
	_duel_live = _main.call("fire_test_duel",
		int(_current.get("seed", 0)),
		_current.get("aim", Vector2.ZERO),
		float(_current.get("commit_t", DUEL_EARLY)),
		float(_current.get("line_x", 0.0)))
	_goto(STAGE_DUEL_FLIGHT)


func _tick_duel_flight() -> void:
	_watch_flight()
	if _stage_time > FLIGHT_TIMEOUT:
		_fail("%s : le penalty adverse ne s'est jamais resolu" % _shot_name())
		_duel_seen.append(V_DEHORS)
		_goto(STAGE_DUEL_ARM)
		return
	if not bool(_main.call("_probe_shot_settled")):
		return
	_evaluate_duel()
	_goto(STAGE_DUEL_ARM)


## A real duel now, because the bookkeeping only exists inside one.
func _tick_duel_series() -> void:
	_main.call("_probe_begin_duel")
	_check(not bool(_main.call("_probe_player_keeps")),
		"le duel s'ouvre sur un tour ou le joueur TIRE")
	_goto(STAGE_DUEL_TAKE)


## The player's own round, fired only to hand the turn over. Aimed wide on
## purpose: the series must stay undecided until the kept round below has been
## played and counted.
func _tick_duel_take() -> void:
	if _stage_time > ARM_TIMEOUT:
		_fail("duel : le premier tour du joueur n'a jamais pu etre tire")
		_goto(STAGE_REPORT)
		return
	if not bool(_main.call("_probe_ready_to_fire")):
		return
	if _stage_time < 0.2:
		return
	_current = {"name": "tour tire d'un vrai duel"}
	_main.call("_probe_set_keeper_level", DUEL_LEVEL)
	_main.call("fire_test_shot", _aim_wide(Field.GOAL_HALF + 1.0, 1.05), 0.85, 0.0, 0.0)
	_goto(STAGE_DUEL_KEEP)


## Waits for the turn to change hands, plays the kept round, and counts.
func _tick_duel_keep() -> void:
	_watch_flight()
	if _stage_time > FLIGHT_TIMEOUT:
		_fail("duel : le tour du gardien n'est jamais arrive")
		_goto(STAGE_REPORT)
		return

	if not _duel_series_fired:
		if not bool(_main.call("_probe_phase_is_keeper_placement")):
			return
		_check(bool(_main.call("_probe_player_keeps")),
			"apres son tir, le joueur passe dans les buts")
		_duel_rival_before = int(_main.call("_probe_rival_count"))
		_current = _duel_series
		_flight_ok = true
		_duel_series_fired = true
		_duel_live = _main.call("fire_test_duel",
			int(_duel_series.get("seed", 0)),
			_duel_series.get("aim", Vector2.ZERO),
			float(_duel_series.get("commit_t", DUEL_EARLY)),
			float(_duel_series.get("line_x", 0.0)))
		_stage_time = 0.0
		return

	if not bool(_main.call("_probe_shot_settled")):
		return
	_evaluate_duel()
	_evaluate_duel_series()
	_goto(STAGE_TRAIN)


## MODE GARDIEN, PLAYED BY NOBODY.
##
## Nothing is fired here and nothing is pressed, and that is the whole design of
## this stage. Every other kept round in this file goes through fire_test_duel,
## which jumps straight into LECTURE - so it proves a great deal about ONE round
## and nothing at all about the round after it. What a training mode is is a LOOP,
## and the only honest way to test a loop is to leave it running.
##
## So the session is opened and then left alone. Left alone it has to:
##
##   1. open IN THE GLOVES, unlike a duel, which opens on a round the player takes;
##   2. keep serving penalties, coming back to the goal line by itself after each
##      verdict, with nobody asking it to;
##   3. serve a DIFFERENT one every time. This is the one that would have failed:
##      the CPU's seed is drawn from how many kicks he has on the record, and a
##      mode where the player never takes one of his own leaves that number frozen
##      unless the kept rounds themselves advance it. A training session that
##      replayed the same penalty for ever would still loop, still score, still
##      look right, and be worthless;
##   4. never fill the player's own row, because he never takes a kick;
##   5. never end.
func _tick_train() -> void:
	_watch_flight()

	if not _train_started:
		_train_started = true
		_flight_ok = true
		_current = {"name": "entrainement gardien"}
		_main.call("_probe_set_keeper_level", DUEL_LEVEL)
		_main.call("_probe_begin_keeper_training")
		_check(bool(_main.call("_probe_player_keeps")),
			"l'entrainement gardien s'ouvre dans les buts")
		_check(int(_main.call("_probe_rival_count")) == 0,
			"une session d'entrainement s'ouvre sur un tableau vide")
		_stage_time = 0.0
		return

	if _stage_time > TRAIN_TIMEOUT:
		_fail("entrainement gardien : %d penalty(s) sur %d en %.0f s, la boucle est bloquee"
			% [_train_seen, TRAIN_ROUNDS, TRAIN_TIMEOUT])
		_goto(STAGE_REPORT)
		return

	# The row of kicks the CPU has taken IS the round counter of this mode. When it
	# grows, the round that just finished is the one `last_taker` still holds:
	# Main sets it entering LECTURE and only rebinds it on the next round.
	var faced: int = int(_main.call("_probe_rival_count"))
	if faced <= _train_seen:
		return
	_train_seen = faced
	_train_targets.append(_taker_target())
	_flight_ok = true
	if _train_seen < TRAIN_ROUNDS:
		return
	_evaluate_train()
	_goto(STAGE_REPORT)


## Where the CPU aimed the round that just finished, or a point off the pitch when
## Main is holding no plan, which shows up as a failure rather than as a silent
## pass.
func _taker_target() -> Vector3:
	var plan: Variant = _main.get("last_taker")
	if typeof(plan) != TYPE_DICTIONARY:
		return Vector3(99.0, 99.0, 99.0)
	var target: Variant = (plan as Dictionary).get("target", null)
	if target is Vector3:
		return target as Vector3
	return Vector3(99.0, 99.0, 99.0)


func _evaluate_train() -> void:
	_check(_train_targets.size() == TRAIN_ROUNDS,
		"l'entrainement a servi %d penalty(s) d'affilee sans qu'on lui demande rien"
			% _train_targets.size())

	# THE SEED HAS TO MOVE. Every pair, not just consecutive ones: a counter that
	# alternated between two values would pass a neighbour by neighbour check.
	var repeated: int = 0
	for i in _train_targets.size():
		for j in range(i + 1, _train_targets.size()):
			if _train_targets[i].distance_to(_train_targets[j]) <= TRAIN_SPREAD:
				repeated += 1
	_check(repeated == 0,
		"les %d penalties de l'entrainement sont tous differents (%d doublon(s))"
			% [_train_targets.size(), repeated])
	for i in _train_targets.size():
		_check(Field.is_within_frame(_train_targets[i]),
			"le penalty d'entrainement %d est cadre (%.2f m, %.2f m)"
				% [i + 1, _train_targets[i].x, _train_targets[i].y])

	_check(int(_main.call("_probe_recorded_count")) == 0,
		"un entrainement de gardien ne remplit jamais la ligne du tireur")
	_check(bool(_main.call("_probe_player_keeps")),
		"le joueur est encore dans les buts apres %d tours" % TRAIN_ROUNDS)
	_check(not bool(_main.call("_probe_is_decided")),
		"une session d'entrainement ne se decide jamais")


# =============================================================================
# Shot plan
# =============================================================================

## The plan is built from world coordinates and inverted back to reticle space,
## because the reticle mapping belongs to ShotModel and this file must not
## duplicate it. `aim_point` is monotonic on each axis, so a bisection finds the
## reticle value that aims at a given metre position.
func _build_plan() -> void:
	var top_corner: Vector2 = _aim_for(2.95, 2.02)
	var dead_centre: Vector2 = Vector2(0.0, _solve_axis(false, 0.45))
	var wide: Vector2 = _aim_wide(Field.GOAL_HALF + 1.0, 1.05)
	var curled: Vector2 = _aim_for(-2.40, 1.15)
	# Out where he has to reach for it with a hand rather than swallow it on the
	# chest: dead centre is a trunk block, which is a parry by definition.
	var glove_reach: Vector2 = _aim_for(1.60, 1.05)

	_check(Field.is_within_frame(ShotModel.aim_point(top_corner)),
		"la visee lucarne tombe bien dans le cadre")
	_check(Field.is_within_frame(ShotModel.aim_point(dead_centre)),
		"la visee centrale tombe bien dans le cadre")
	_check(not Field.is_within_frame(ShotModel.aim_point(wide)),
		"la visee hors cadre tombe bien a cote du poteau")

	_plan = [
		{
			"name": "lucarne pleine puissance contre un Debutant",
			"aim": top_corner, "power": 1.0, "side": 0.0, "lift": 0.0,
			"level": L_DEBUTANT, "expect": V_BUT, "net": true,
		},
		{
			"name": "frappe molle plein centre contre une Legende",
			"aim": dead_centre, "power": 0.03, "side": 0.0, "lift": 0.0,
			"level": L_LEGENDE, "expect": V_ARRET, "net": false,
		},
		{
			# Placed rather than hit, at hip height and out towards the post, so a
			# Legende gets there with a glove instead of blocking it with his
			# chest. That is a CATCH, and the point of this entry is that the ball
			# must be in his gloves when the verdict comes up, not in the net.
			"name": "ballon place a portee de gant contre une Legende",
			"aim": glove_reach, "power": 0.25, "side": 0.0, "lift": 0.0,
			"level": L_LEGENDE, "expect": V_ARRET, "net": false, "catch": true,
		},
		{
			"name": "tir a un metre du poteau",
			"aim": wide, "power": 0.85, "side": 0.0, "lift": 0.0,
			"level": L_CONFIRME, "expect": V_DEHORS, "net": false,
		},
		{
			"name": "enroule appuye contre un Pro",
			"aim": curled, "power": 0.82, "side": 0.85, "lift": 0.15,
			"level": L_PRO, "expect": V_ANY, "net": false,
		},
	]


## The kept rounds, built around ONE CPU penalty that the two commit times
## disagree about.
##
## The seed is searched rather than written down, and the filter is
## KeeperInput's own rule (`reachable`, `margin`) rather than a guess about
## metres: this file must not restate the arithmetic it is here to check, and a
## penalty hand picked by eye would drift the day those curves are retuned.
func _build_duel_plan() -> void:
	var found: int = _find_taker_seed(DUEL_LEVEL)
	if found == 0:
		_fail("aucune graine de tireur ne donne un penalty joignable tot et hors de portee tard")
		return

	var plan: Dictionary = TakerAi.choose(found, DUEL_LEVEL, false, 0.0)
	var target: Vector3 = plan.get("target", Vector3.ZERO)
	var aim: Vector2 = TakerAi.reticle(target.x, target.y)
	_check(Field.is_within_frame(target),
		"le penalty du duel est cadre (%.2f m, %.2f m)" % [target.x, target.y])

	# THE ENVELOPE SHRINKS, and it never covers everything. Both are the contract
	# of 2.12a and both are cheap to state here on the real module, because the
	# rounds below are only meaningful if they hold.
	var early: float = KeeperInput.coverage(0.0, DUEL_EARLY, KeeperInput.NOMINAL_FLIGHT, DUEL_LEVEL)
	var late: float = KeeperInput.coverage(0.0, DUEL_LATE, KeeperInput.NOMINAL_FLIGHT, DUEL_LEVEL)
	_check(late < early,
		"attendre coute de la couverture (%.3f a l'engagement tot, %.3f tard)" % [early, late])
	_check(early < 1.0,
		"l'enveloppe ne couvre jamais tout le but (%.3f)" % early)

	_duel_plan = [
		{
			"name": "plongeon engage tot sur le bon coin",
			"seed": found, "aim": aim, "commit_t": DUEL_EARLY, "line_x": 0.0,
			"level": DUEL_LEVEL, "expect": V_ARRET,
		},
		{
			"name": "le meme plongeon engage trop tard",
			"seed": found, "aim": aim, "commit_t": DUEL_LATE, "line_x": 0.0,
			"level": DUEL_LEVEL, "expect": V_ANY, "forbid": V_ARRET,
		},
		{
			"name": "la meme graine rejouee",
			"seed": found, "aim": aim, "commit_t": DUEL_EARLY, "line_x": 0.0,
			"level": DUEL_LEVEL, "expect": V_ARRET, "same_as": 0,
		},
	]
	_duel_series = {
		"name": "tour garde d'un vrai duel",
		"seed": found, "aim": aim, "commit_t": DUEL_EARLY, "line_x": 0.0,
		"level": DUEL_LEVEL, "expect": V_ANY,
	}


## Walks the seed line for a CPU penalty an early dive reaches with room and a
## late one cannot reach at all.
func _find_taker_seed(level: int) -> int:
	var seed_value: int = DUEL_SEED_START
	for _i in DUEL_SEED_TRIES:
		if _duel_seed_fits(TakerAi.choose(seed_value, level, false, 0.0), level):
			return seed_value
		seed_value += DUEL_SEED_STRIDE
	return 0


func _duel_seed_fits(plan: Dictionary, level: int) -> bool:
	var target: Vector3 = plan.get("target", Vector3.ZERO)
	if not target.is_finite() or not Field.is_within_frame(target):
		return false
	# A mishit is a different experiment: this pair measures the clock, not the
	# taker's touch.
	if not is_equal_approx(
			float(plan.get("release", 0.0)), float(plan.get("sweet_centre", 1.0))):
		return false
	# Hit hard enough that the real flight is close to the nominal one the
	# envelope was drawn against, and placed far enough out that a late dive
	# cannot simply fall on it.
	if float(plan.get("power", 0.0)) < 0.70:
		return false
	if absf(target.x) < 1.40 or absf(target.x) > 2.40:
		return false
	if target.y < 0.30 or target.y > 1.30:
		return false
	# The dive reticle has to land on the same point the taker aimed at, or the
	# round would measure the reticle mapping instead of the mode.
	var aim: Vector2 = TakerAi.reticle(target.x, target.y)
	if KeeperInput.dive_target(aim).distance_to(target) > 0.12:
		return false
	if KeeperInput.margin(target, 0.0, DUEL_EARLY, KeeperInput.NOMINAL_FLIGHT, level) < 0.12:
		return false
	return not KeeperInput.reachable(
		target, 0.0, DUEL_LATE, KeeperInput.NOMINAL_FLIGHT, level)


func _aim_for(world_x: float, world_y: float) -> Vector2:
	return Vector2(_solve_axis(true, world_x), _solve_axis(false, world_y))


## The wide shot must be wide whatever margin ShotModel gives the reticle. The
## bisection is tried first; if the mapping saturates before that x, the reticle
## is pushed outwards by hand until the aim point leaves the frame.
func _aim_wide(world_x: float, world_y: float) -> Vector2:
	var aim: Vector2 = _aim_for(world_x, world_y)
	if not Field.is_within_frame(ShotModel.aim_point(aim)):
		return aim
	var pushed: float = 1.0
	while pushed <= 8.0:
		aim.x = pushed
		if not Field.is_within_frame(ShotModel.aim_point(aim)):
			return aim
		pushed += 0.1
	return aim


func _solve_axis(horizontal: bool, wanted: float) -> float:
	var low: float = -6.0
	var high: float = 6.0
	for _i in 60:
		var mid: float = (low + high) * 0.5
		if _axis_value(horizontal, mid) < wanted:
			low = mid
		else:
			high = mid
	return (low + high) * 0.5


func _axis_value(horizontal: bool, t: float) -> float:
	if horizontal:
		return ShotModel.aim_point(Vector2(t, 0.5)).x
	return ShotModel.aim_point(Vector2(0.0, t)).y


# =============================================================================
# Assertions
# =============================================================================

func _check_enum_alignment() -> void:
	var names: Dictionary = _main.call("_probe_verdict_names")
	_eq(int(names.get("BUT", -99)), V_BUT, "l'id du verdict BUT n'a pas bouge")
	_eq(int(names.get("ARRET", -99)), V_ARRET, "l'id du verdict ARRET n'a pas bouge")
	_eq(int(names.get("POTEAU", -99)), V_POTEAU, "l'id du verdict POTEAU n'a pas bouge")
	_eq(int(names.get("BARRE", -99)), V_BARRE, "l'id du verdict BARRE n'a pas bouge")
	_eq(int(names.get("DEHORS", -99)), V_DEHORS, "l'id du verdict DEHORS n'a pas bouge")
	_eq(int(KeeperBrain.Level.DEBUTANT), L_DEBUTANT, "le niveau Debutant n'a pas bouge")
	_eq(int(KeeperBrain.Level.LEGENDE), L_LEGENDE, "le niveau Legende n'a pas bouge")


## Proves the world exists before anything is measured against it. A probe that
## skips this happily reports "no NaN" about a scene that was never built.
func _check_world_built() -> void:
	_check(_main.get("pitch") != null, "la pelouse est construite")
	_check(_main.get("goal_frame") != null, "le but est construit")
	_check(_main.get("ball") != null, "le ballon existe")
	_check(_main.get("keeper") != null, "le gardien existe")
	_check(_main.get("shooter") != null, "le tireur existe")
	_check(_main.get("hud") != null, "le HUD existe")
	_check(int(_main.get("boot_msec")) > 0, "Main a horodate son demarrage")

	var ball: Node3D = _main.get("ball") as Node3D
	if ball != null:
		_check(ball.global_position.distance_to(Field.SPOT) < 0.35,
			"le ballon demarre sur le point de penalty")


func _watch_flight() -> void:
	_net_peak = maxf(_net_peak, float(_main.call("_probe_net_bulge_peak")))
	var ball: Node3D = _main.get("ball") as Node3D
	if ball == null:
		return
	var point: Vector3 = ball.global_position
	if not point.is_finite() or not _in_world(point):
		_flight_ok = false


func _in_world(point: Vector3) -> bool:
	if absf(point.x) > _limit_x:
		return false
	if point.y < _limit_y_low or point.y > _limit_y_high:
		return false
	if point.z < _limit_z_low or point.z > _limit_z_high:
		return false
	return true


func _evaluate_shot() -> void:
	var verdict: int = int(_main.get("last_verdict"))
	_observed.append(verdict)

	var label: String = String(_main.call("_probe_verdict_label", verdict))
	var expected: int = int(_current.get("expect", V_ANY))
	if expected == V_ANY:
		_check(true, "%s : verdict rendu (%s)" % [_shot_name(), label])
	else:
		var expected_label: String = String(_main.call("_probe_verdict_label", expected))
		_check(verdict == expected,
			"%s : attendu %s, obtenu %s" % [_shot_name(), expected_label, label])
		if verdict != expected:
			# A bare "wrong verdict" is useless to whoever has to fix it. Say
			# where the ball actually crossed the line and what the geometry
			# thought of that point.
			for detail in _crossing_report():
				_line("         %s" % detail)

	var speed: float = float(_launch.get("speed", 0.0))
	_check(speed >= ShotModel.MIN_SPEED - 0.5 and speed <= ShotModel.MAX_SPEED + 0.5,
		"%s : vitesse de frappe plausible (%.1f km/h)" % [_shot_name(), speed * 3.6])

	_check_log()

	var ball: Node = _main.get("ball") as Node
	if ball != null:
		_check(not bool(ball.get("flying")),
			"%s : le ballon est immobilise apres le verdict" % _shot_name())

	if verdict == V_ARRET:
		_evaluate_save()
	elif bool(_current.get("catch", false)):
		_fail("%s : attendu une prise de balle, le tir n'a meme pas ete arrete" % _shot_name())


## One kept round, judged on the invariants of the mode rather than on its decor.
func _evaluate_duel() -> void:
	var verdict: int = int(_main.get("last_verdict"))
	_duel_seen.append(verdict)
	var label: String = String(_main.call("_probe_verdict_label", verdict))

	# fire_test_duel handed back a LIVE dictionary, so it must have filled in.
	_eq(int(_duel_live.get("verdict", -99)), verdict,
		"%s : le compte rendu du duel porte le verdict joue" % _shot_name())
	var taker: Dictionary = _duel_live.get("taker", {})
	var dive: Dictionary = _duel_live.get("dive", {})
	_check(not taker.is_empty(), "%s : le tireur adverse a bien ete choisi" % _shot_name())
	_check(not dive.is_empty(), "%s : le plongeon du joueur a bien ete lance" % _shot_name())
	var dive_target: Vector3 = dive.get("target", Vector3.ZERO)
	_check(Field.is_within_frame(dive_target),
		"%s : le plongeon vise un point du cadre (%.2f m, %.2f m)"
			% [_shot_name(), dive_target.x, dive_target.y])
	var cover: float = float(_duel_live.get("coverage", -1.0))
	_check(cover >= 0.0 and cover < 1.0,
		"%s : la couverture annoncee est une fraction, jamais tout le but (%.3f)"
			% [_shot_name(), cover])

	var keeper: Node = _main.get("keeper") as Node
	if keeper != null:
		_check(bool(keeper.call("committed")),
			"%s : le gardien s'est bien engage une fois" % _shot_name())

	# THE PENALTY REALLY FLEW. Same walk of the same log the player's own shots
	# get: a defended penalty is a flight, not a dice roll.
	_check_log()
	_check_replay_window()

	var expected: int = int(_current.get("expect", V_ANY))
	if expected == V_ANY:
		_check(true, "%s : verdict rendu (%s)" % [_shot_name(), label])
	else:
		var wanted: String = String(_main.call("_probe_verdict_label", expected))
		_check(verdict == expected,
			"%s : attendu %s, obtenu %s" % [_shot_name(), wanted, label])
	if _current.has("forbid"):
		var forbidden: int = int(_current["forbid"])
		_check(verdict != forbidden,
			"%s : ce plongeon ne pouvait pas arriver a temps, et pourtant %s"
				% [_shot_name(), label])

	# A save is a save on both sides of the duel, and it is judged the same way:
	# the ball never finishes behind the line under an ARRET.
	if verdict == V_ARRET:
		_evaluate_save()

	if _current.has("same_as"):
		var other: int = int(_current["same_as"])
		if other >= 0 and other < _duel_seen.size() - 1:
			_eq(verdict, _duel_seen[other],
				"%s : deux executions d'une graine rendent le meme verdict" % _shot_name())


## THE TWO LOGS MUST COVER THE SAME WINDOW. One playhead drives them both, so a
## log that stops before the other is a replay that ends with one of the two
## frozen: the keeper hanging in mid air over his own shadow while the ball is
## still moving. The keeper's has to open BEFORE contact too, because a dive
## committed during the run up is the thing worth rewinding for, and on the player
## keeper's side that recording is started by a different call from the AI's.
func _check_replay_window() -> void:
	var keeper: Node = _main.get("keeper") as Node
	var ball: Node = _main.get("ball") as Node
	if keeper == null or ball == null:
		return
	var poses: Variant = keeper.get("pose_log")
	var flight: Variant = ball.get("flight_log")
	if typeof(poses) != TYPE_ARRAY or typeof(flight) != TYPE_ARRAY:
		_fail("%s : les journaux de replay ne sont pas lisibles" % _shot_name())
		return
	var pose_log: Array = poses
	var flight_log: Array = flight
	if pose_log.is_empty() or flight_log.is_empty():
		_fail("%s : un des deux journaux de replay est vide" % _shot_name())
		return

	var first_pose: Dictionary = pose_log[0]
	var final_pose: Dictionary = pose_log[pose_log.size() - 1]
	var final_step: Dictionary = flight_log[flight_log.size() - 1]
	var pose_first: float = float(first_pose.get("t", 0.0))
	var pose_last: float = float(final_pose.get("t", 0.0))
	var ball_last: float = float(final_step.get("t", 0.0))
	_check(pose_first < 0.0,
		"%s : le gardien est enregistre AVANT la frappe (%.2f s)" % [_shot_name(), pose_first])
	# One physics step of slack: the two are appended from different nodes.
	_check(pose_last >= ball_last - 0.02,
		"%s : le journal du gardien couvre tout le vol (%.2f s contre %.2f s)"
			% [_shot_name(), pose_last, ball_last])


## The bookkeeping, which only exists inside a real duel: one kept round fills
## exactly one case of the CPU row, and it holds the verdict that was played.
func _evaluate_duel_series() -> void:
	var after: int = int(_main.call("_probe_rival_count"))
	_eq(after - _duel_rival_before, 1,
		"un tour garde fait grandir la ligne adverse d'exactement une case")

	var raw: Variant = _main.call("_probe_rival_scores")
	if typeof(raw) != TYPE_ARRAY:
		_fail("duel : la ligne adverse n'est pas lisible")
		return
	var scores: Array = raw
	if scores.is_empty():
		_fail("duel : le tour garde n'a rien enregistre")
		return
	_eq(int(scores[scores.size() - 1]), int(_main.get("last_verdict")),
		"le verdict enregistre pour l'adversaire est celui qui a ete joue")
	# And the player's own row did NOT grow: a kept round belongs to one side.
	_eq(int(_main.call("_probe_recorded_count")), 1,
		"un tour garde ne remplit jamais la ligne du joueur")


## What a save must look like ON THE PITCH, and not only on the scoreboard.
##
## Three things are asserted, and each one is a bug that was actually shipped:
##
##   1. THE BALL IS NOT BEHIND THE LINE. This is the rebound rule of Main's
##      header seen from the other end: a keeper touch is a save, a rebound
##      cannot be scored, so a ball that finishes in the net under an ARRET
##      verdict is a picture that contradicts the scoreline. It used to, every
##      time, because nothing ever wired Ball.keeper_probe and the ball simply
##      flew through him.
##   2. A CAUGHT BALL IS IN HIS HANDS. Held means held: within HOLD_REACH of the
##      glove that took it, still there when the verdict is up.
##   3. A PARRIED BALL IS GOING AWAY. Ball._parry guarantees it leaves the glove
##      travelling back up the pitch, so it can never be tamely rolling in.
func _evaluate_save() -> void:
	_saves_seen += 1
	var ball: Node3D = _main.get("ball") as Node3D
	var keeper: Node3D = _main.get("keeper") as Node3D
	if ball == null or keeper == null:
		_fail("%s : arret sans ballon ni gardien a inspecter" % _shot_name())
		return

	var final_point: Vector3 = ball.global_position
	_check(not Field.is_inside_mouth(final_point),
		"%s : un ballon arrete ne finit pas derriere la ligne (z = %.2f, x = %.2f, y = %.2f)"
			% [_shot_name(), final_point.z, final_point.x, final_point.y])

	var held: bool = bool(ball.get("held"))
	var holding: bool = bool(keeper.call("holding"))
	_eq(1 if held else 0, 1 if holding else 0,
		"%s : le ballon et le gardien sont d'accord sur la prise de balle" % _shot_name())

	var pose: Dictionary = keeper.call("pose")
	var reach: float = minf(
		final_point.distance_to(pose.get("glove_left", Vector3(99.0, 99.0, 99.0))),
		final_point.distance_to(pose.get("glove_right", Vector3(99.0, 99.0, 99.0))))

	if held:
		_catches_seen += 1
		_check(reach <= HOLD_REACH,
			"%s : le ballon capte est bien dans un gant (%.2f m du gant le plus proche)"
				% [_shot_name(), reach])
		_check_mitt_clearance()
	else:
		_check(true, "%s : arret en deux temps, le ballon est repousse (%.2f m du gant)"
			% [_shot_name(), reach])

	if bool(_current.get("catch", false)):
		_check(held, "%s : le gardien garde le ballon dans ses gants" % _shot_name())


## A HELD BALL IS HELD, NOT SPEARED. The check above puts the ball within reach of
## a glove; this one puts it OUTSIDE the glove's own solid.
##
## The two are not the same test and the difference is the bug. `hold_point`
## anchors the ball a fixed distance from the point the ARMS are solved to, while
## the drawn glove is a 20 cm padded ellipsoid centred behind that point and
## running past it, so a ball can satisfy the first check to the centimetre while
## the fingers stand several centimetres inside it.
##
## Skipped, out loud, on a body that has no mitts to measure: a checkout with no
## assets/ keeps its procedural blobs and this has nothing to say about them.
func _check_mitt_clearance() -> void:
	var reach: float = float(_main.call("_probe_mitt_reach_into_ball"))
	if reach == -INF:
		_line("  (pas de moufle a mesurer sur ce corps)")
		return
	_check(reach <= MITT_SLACK,
		"%s : les moufles ne traversent pas le ballon tenu (%.1f mm dedans)"
			% [_shot_name(), reach * 1000.0])


## The whole flight, step by step, must stay finite and inside the built world.
## This is the assertion that catches a diverging integrator, and it is checked
## on the log rather than on the final position because a flight can blow up and
## come back.
func _check_log() -> void:
	var ball: Node = _main.get("ball") as Node
	if ball == null:
		_fail("%s : pas de ballon a inspecter" % _shot_name())
		return
	var raw: Variant = ball.get("flight_log")
	if typeof(raw) != TYPE_ARRAY:
		_fail("%s : Ball.flight_log n'est pas un tableau" % _shot_name())
		return
	var trace: Array = raw
	if trace.is_empty():
		_fail("%s : aucun journal de vol enregistre" % _shot_name())
		return

	var bad: int = 0
	var farthest: float = 0.0
	for entry in trace:
		var record: Dictionary = entry
		var point: Vector3 = record.get("position", Vector3.ZERO)
		if not point.is_finite() or not _in_world(point):
			bad += 1
		else:
			farthest = maxf(farthest, point.length())
	_eq(bad, 0, "%s : %d position(s) de vol non finies ou hors du monde" % [_shot_name(), bad])
	_check(_flight_ok, "%s : le ballon n'a jamais quitte le monde construit" % _shot_name())
	_check(trace.size() >= 3,
		"%s : le vol compte au moins trois pas de physique (%d)" % [_shot_name(), trace.size()])
	_check(farthest < _limit_z_high,
		"%s : le point le plus eloigne reste plausible (%.1f m)" % [_shot_name(), farthest])


## Replays the logged flight and reports the first crossing of z = 0, so a wrong
## verdict points at the module that got the geometry wrong rather than leaving
## the integrator to guess.
func _crossing_report() -> PackedStringArray:
	var lines: PackedStringArray = PackedStringArray()
	var ball: Node = _main.get("ball") as Node
	if ball == null:
		return lines
	var raw: Variant = ball.get("flight_log")
	if typeof(raw) != TYPE_ARRAY:
		return lines
	var trace: Array = raw
	if trace.size() < 2:
		return lines

	var first: Dictionary = trace[0]
	var last: Dictionary = trace[trace.size() - 1]
	var launch: Vector3 = first.get("position", Vector3.ZERO)
	var final_point: Vector3 = last.get("position", Vector3.ZERO)
	lines.append("depart %s, arrivee %s, %d pas" % [str(launch), str(final_point), trace.size()])

	var index: int = 1
	while index < trace.size():
		var a: Vector3 = trace[index - 1].get("position", Vector3.ZERO)
		var b: Vector3 = trace[index].get("position", Vector3.ZERO)
		if a.z > 0.0 and b.z <= 0.0:
			var cross: Dictionary = Field.cross_goal_plane(a, b)
			var point: Vector3 = cross.get("point", b)
			lines.append("plan de but franchi en %s (t = %.3f s)"
				% [str(point), float(trace[index].get("t", 0.0))])
			lines.append("is_within_frame = %s, is_inside_mouth = %s, marge = %.3f m" % [
				str(Field.is_within_frame(point)),
				str(Field.is_inside_mouth(point)),
				Field.mouth_margin(point)])
			return lines
		index += 1

	lines.append("le ballon n'a jamais franchi le plan z = 0")
	return lines


func _evaluate_net() -> void:
	if not bool(_current.get("net", false)):
		return
	_check(_net_peak > NET_PROOF,
		"%s : le filet a bouge (%.1f cm de creux)" % [_shot_name(), _net_peak * 100.0])


func _evaluate_reset() -> void:
	var ball: Node3D = _main.get("ball") as Node3D
	if ball != null:
		_check(not bool(ball.get("flying")),
			"%s : le ballon est au repos entre deux tirs" % _shot_name())
		_check(ball.global_position.distance_to(Field.SPOT) < 0.35,
			"%s : le ballon est repose sur le point (%.2f m d'ecart)"
				% [_shot_name(), ball.global_position.distance_to(Field.SPOT)])

	var keeper: Node3D = _main.get("keeper") as Node3D
	if keeper == null:
		return
	_check(not bool(keeper.get("diving")),
		"%s : le gardien ne plonge plus entre deux tirs" % _shot_name())
	var pose: Dictionary = keeper.call("pose")
	var centre: Vector3 = pose.get("centre", keeper.global_position)
	_check(absf(centre.x) <= 1.0,
		"%s : le gardien est revenu au milieu de sa ligne (x = %.2f)" % [_shot_name(), centre.x])
	_check(absf(centre.z - Field.KEEPER_HOME.z) <= 1.2,
		"%s : le gardien est revenu sur sa ligne (z = %.2f)" % [_shot_name(), centre.z])


## The series bookkeeping must agree with what actually happened on the pitch.
func _check_series() -> void:
	var goals: int = 0
	for verdict in _observed:
		if verdict == V_BUT:
			goals += 1
	var recorded: int = int(_main.call("_probe_recorded_count"))
	var counted: int = int(_main.call("_probe_player_goals"))

	_eq(recorded, _observed.size(),
		"la seance a enregistre autant de tentatives que de tirs effectues")
	_eq(counted, goals, "le nombre de buts de la seance correspond aux verdicts observes")

	var summary: Dictionary = _main.call("_probe_summary")
	_check(not summary.is_empty(), "le resume de seance n'est pas vide")

	# A plan that stopped producing saves, or a catch path that quietly died,
	# would pass every assertion above by never running any of them.
	_check(_saves_seen >= 2,
		"la serie a bien produit des arrets a inspecter (%d)" % _saves_seen)
	_check(_catches_seen >= 1,
		"le gardien a garde le ballon au moins une fois (%d prise(s) sur %d arrets)"
			% [_catches_seen, _saves_seen])


# =============================================================================
# Report
# =============================================================================

func _finish() -> void:
	if _stage == STAGE_DONE:
		return
	_stage = STAGE_DONE

	if not _series_checked:
		_series_checked = true
		_check_series()

	_line("")
	for index in _observed.size():
		var name_of: String = String(_plan[index].get("name", "tir")) if index < _plan.size() else "tir"
		_line("  tir %d : %s -> %s" % [
			index + 1, name_of, String(_main.call("_probe_verdict_label", _observed[index]))])
	for index in _duel_seen.size():
		var kept: String = "tour garde"
		if index < _duel_plan.size():
			kept = String(_duel_plan[index].get("name", kept))
		elif not _duel_series.is_empty():
			kept = String(_duel_series.get("name", kept))
		_line("  duel %d : %s -> %s" % [
			index + 1, kept, String(_main.call("_probe_verdict_label", _duel_seen[index]))])
	_check(_duel_seen.size() >= 4,
		"le mode duel a bien joue ses tours gardes (%d)" % _duel_seen.size())
	_line("")
	_line("  %d verifications, %d echecs" % [_checks, _failures])
	_line("==================================")
	_line("")

	for line in _report:
		print(line)

	# Main owns the exit, because it is the only node that knows how long the
	# audio server still needs before it lets go of its voices. Quitting from
	# here would end the process with playbacks still registered, which Godot
	# reports as leaked ObjectDB instances.
	if _main != null:
		_main.call("quit_clean", 1 if _failures > 0 else 0)
		return
	var tree: SceneTree = get_tree()
	if tree != null:
		Engine.time_scale = 1.0
		tree.quit(1 if _failures > 0 else 0)


func _shot_name() -> String:
	return String(_current.get("name", "tir %d" % (_shot_index + 1)))


func _line(text: String) -> void:
	_report.append(text)


func _check(condition: bool, message: String) -> void:
	_checks += 1
	if condition:
		_line("  OK     %s" % message)
	else:
		_failures += 1
		_line("  ECHEC  %s" % message)


func _eq(actual: int, expected: int, message: String) -> void:
	_check(actual == expected, "%s (attendu %d, obtenu %d)" % [message, expected, actual])


func _fail(message: String) -> void:
	_checks += 1
	_failures += 1
	_line("  ECHEC  %s" % message)
