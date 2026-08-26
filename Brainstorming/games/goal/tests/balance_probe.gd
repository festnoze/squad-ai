extends Node
## GOAL - in-game balance probe.
##
##   godot --headless --path . -- --balance
##   godot --headless --path . -- --balance --balance-repeats 4 --balance-live 0
##   godot --headless --path . -- --balance --balance-live 0 --balance-seed 3
##
## The third form is the one to reach for before writing a number down anywhere:
## six of them, seeds 0 to 5, run at the same time on six cores, pooled by adding
## the raw counts the final block prints. See SEED_STRIDE for why running the
## same seeds twice proves nothing at all.
##
## Budget about a quarter of an hour for the default run, and note WHY, because
## the number is a design consequence rather than sloppiness: since the keeper
## started waiting for the last responsible moment he re-estimates the flight on
## every physics step until he pushes off, and each of those estimates integrates
## the rest of the flight through Aero. That is a few tenths of a millisecond per
## frame in the actual game, which is free, and several thousand extra integration
## steps per simulated penalty here, which is not. `--balance-repeats 1` gives the
## same tables four times faster with roughly twice the noise, and
## `--balance-live 0` drops the in game stage entirely.
##
## This probe does not assert, it MEASURES. It exists because the difficulty of
## the game cannot be tuned by reading the source: the outcome of a penalty is
## the product of ShotModel (where the ball goes), Aero (how it gets there) and
## KeeperBrain plus Keeper (whether anybody is there when it arrives). Only a
## large systematic sample says what those three actually add up to.
##
## It runs in three stages, and the split is deliberate.
##
## 1. A LIVE stage. A handful of penalties are fired through Main.fire_test_shot:
##    the real orchestrator, the real ball, the real 120 Hz physics. That is the
##    ground truth, but it costs about 1.5 s of wall clock per shot, so it can
##    only ever be a few dozen shots.
##
## 2. An OFFLINE stage. Thousands of penalties are replayed inside a handful of
##    frames, reusing the very same modules: ShotModel.resolve for the strike,
##    Aero.integrate for the flight, Field for the geometry, and THE REAL Keeper
##    NODE for the keeper, driven through exactly the calls Main makes in
##    _step_segment (reset_to_line, prepare, read_shooter, track, attempt_save).
##    Nothing about the keeper is re-implemented here, which is what makes the
##    offline numbers worth reading.
##
## 3. A PROMISE stage: PROMISE_SHOTS penalties per level fired at nothing but a
##    genuine angle of the bar, so the headline design claim of the game gets its
##    own sample instead of being read off the six shots the grids happen to drop
##    in that box.
##
## Stage 1 exists to keep stage 2 honest: the report prints the live save count
## next to the save count the offline model predicts for the very same shots. If
## those two ever drift apart, the offline table is lying and must be fixed
## before anybody tunes anything against it. The two stages are now fired at the
## SAME configurations in the same way (identical aim points, no shuffle on the
## line, clean contact), and the live stage is repeated LIVE_REPEATS times, because
## the first version compared sixteen live shots against a prediction drawn from
## jittered aims and then asked the reader to conclude something from the gap. It
## could not: sixteen shots at a true rate of one in four have a two sigma band
## seven points wide. The report now prints that band next to the two numbers, so
## a difference is either called out as real or explicitly called noise.
##
## THE SAMPLE, AND WHY THERE ARE TWO OF THEM
##
## No single distribution of aim answers the question "how hard is this keeper",
## so the probe measures two and prints both.
##
##   (a) UNIFORM OVER THE MOUTH. A seven by four grid of cells, each jittered over
##       exactly its own area, so the union is a flat draw over the whole goal.
##       This is a STRESS CASE and it is deliberately brutal: 44 % of it is hard
##       against a post and a quarter of it is in the top 60 cm, which is a
##       distribution no human being produces. It is the right sample for asking
##       whether anything is broken, and the wrong one for asking what the game
##       feels like.
##
##   (b) REALISTIC PLAYER AIM. Where people actually shoot, with human error. Five
##       clusters, weights and spreads written down in AIM_CLUSTERS below and
##       fixed: the SPREAD IS THE ERROR, there is no second fudge factor on top,
##       and the whole table is one constant so it cannot be quietly nudged until
##       the numbers flatter the keeper. This is the sample the balance targets
##       are judged on, because it is the one the player lives in.
##
## The report splits both samples back into the six angles, the two half side
## bands and the middle.
##
## Two details of the offline stage that matter:
##   - Main is parked in ACCUEIL first, so the orchestrator stops driving the
##     keeper and the HUD stops predicting arcs while we borrow the body;
##   - the keeper's own signals are disconnected from Main, otherwise every
##     simulated save would latch a verdict and scuff the turf in the real game.
##
## The probe is allowed to print: it lives under tests/.

# --- Stages ------------------------------------------------------------------

const STAGE_BOOT := 0
const STAGE_LIVE_ARM := 1
const STAGE_LIVE_FLIGHT := 2
const STAGE_LIVE_RESET := 3
const STAGE_SIM := 4
const STAGE_REPORT := 5
const STAGE_DONE := 6

# --- Mirrors of the autoload enums, cross checked against Main on boot -------

const V_BUT := 0
const V_ARRET := 1
const V_POTEAU := 2
const V_BARRE := 3
const V_DEHORS := 4
const V_COUNT := 5

## Shootout.Phase.ACCUEIL. Parking Main there stops it driving the keeper.
const PH_ACCUEIL := 0

const L_COUNT := 4
const LEVEL_LABELS: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]

## Mirrors Main.DEFAULT_SWEET_CENTRE: where the clean contact window sits on the
## power bar for a scripted shot.
const SWEET_CENTRE := 0.72

# --- Flight integration ------------------------------------------------------

## The project physics step. The offline flight uses the same one, so a save that
## happens offline happens at the same instant it would in the game.
const STEP := 1.0 / 120.0
const MAX_STEPS := 900
## Mirrors Ball.TURF_RESTITUTION / TURF_FRICTION, for the rare miscue that hits
## the turf before the line.
const TURF_RESTITUTION := 0.45
const TURF_FRICTION := 0.42

# --- The samples -------------------------------------------------------------

const SAMPLE_UNIFORM := 0
const SAMPLE_REAL := 1
const SAMPLE_COUNT := 2
const SAMPLE_LABELS: PackedStringArray = [
	"UNIFORME sur toute la lucarne (cas de stress)",
	"VISEE REALISTE de joueur (cas de reference)",
]

## (a) Seven columns and four rows of aim, evenly spread over the mouth, each cell
## jittered over exactly its own half spacing so the union is a uniform draw.
const AIM_COLS: PackedFloat64Array = [-3.05, -2.0333, -1.0167, 0.0, 1.0167, 2.0333, 3.05]
const AIM_ROWS: PackedFloat64Array = [0.32, 0.93, 1.54, 2.15]
const JITTER_X := 0.508
const JITTER_Y := 0.305
const COL_COUNT := 7
const ROW_COUNT := 4
const CELL_COUNT := 28

## (b) WHERE PEOPLE ACTUALLY AIM, AND HOW BADLY THEY MISS.
##
## Five clusters. Each row is [weight, mean |x|, sigma x, mean y, sigma y], in
## metres, with the sign of x drawn evenly so neither post is favoured. The sigma
## IS the human error: a taker going for the top corner really does end up 40 cm
## away from it about a third of the time, and that is modelled here and nowhere
## else, so there is no second error term hiding anywhere to be tuned.
##
## The weights say that about half of all penalties are placed to a side at or
## below the waist, a fifth are half hearted half side shots, a fifth are genuine
## attempts at the angle of the bar, and the rest go down the middle, high or low.
## That shape is what makes this the reference sample: unlike (a) it puts most of
## its mass where a goalkeeper can plausibly do something, which is precisely why
## the balance targets belong on it.
##
## THIS TABLE IS THE DEFINITION OF THE REFERENCE CASE. Changing a number in it
## changes what "50 % for a Pro" means, so it is written down once, here, in the
## open, rather than being spread through the sampling code.
##
## One known bias, stated rather than hidden: with these spreads only about half a
## per cent of CLEANLY struck shots miss the frame, where real takers miss nearer
## four. The sample is therefore slightly kinder on accuracy than life, which
## makes the save rates it reports slightly HARSHER on the keeper than life, since
## a shot that misses the goal can never be saved. Widening the spreads would flatter
## him, which is exactly why they are not being widened to reach a target.
const AIM_CLUSTERS: Array = [
	# poser sur le cote, sous la taille: le penalty le plus courant
	[0.30, 2.15, 0.52, 0.72, 0.34],
	# demi-cote, sans conviction
	[0.20, 1.20, 0.45, 0.95, 0.42],
	# plein centre, a plat ou pique
	[0.16, 0.10, 0.52, 0.85, 0.45],
	# la lucarne, tentee pour de vrai
	[0.22, 2.55, 0.50, 1.82, 0.42],
	# sous la barre au milieu
	[0.12, 0.25, 0.85, 1.80, 0.38],
]
## Where the reticle stops. Beyond these the shot is simply wide or over, which is
## a legal and counted outcome: a realistic sample has to contain misses.
const REAL_MAX_X := 4.10
const REAL_MIN_Y := 0.14
const REAL_MAX_Y := 2.90

## Where the report buckets cut the mouth up.
const BAND_WIDE := 2.00       # |x| above this is an angle, hard against a post
const BAND_HALF := 0.75       # |x| above this is a half side shot
const BAND_HIGH := 1.55       # y above this is high in the goal
const BAND_LOW := 0.85        # y below this is along the turf

const ZONE_COUNT := 9
const ZONE_LABELS: PackedStringArray = [
	"lucarne G", "lucarne D",
	"mi-haut G", "mi-haut D",
	"ras sol G", "ras sol D",
	"demi-cote G", "demi-cote D",
	"plein centre",
]
## The six angles, the two half side bands, and the middle.
const ZONE_ANGLES: PackedInt32Array = [0, 1, 2, 3, 4, 5]
const ZONE_HALVES: PackedInt32Array = [6, 7]
const ZONE_MIDDLE: PackedInt32Array = [8]
## A GENUINE top corner, for the promise that a well struck one still scores. The
## "lucarne" report bucket is looser than this on purpose (it starts at 2.0 m from
## the middle), so the promise is measured against its own strict test.
const TOP_CORNER_X := 2.80
const TOP_CORNER_Y := 1.80

## ...and the promise gets its OWN sample rather than being read off whatever the
## two grids happen to drop inside that box. They drop about six shots per level
## in there, which is a two sigma band of forty points: the first version of this
## report printed "2 / 6 buts (33 %)" next to a target of 85 % and it meant
## nothing at all. These shots are fired for no other purpose, straight at a real
## top corner, hard and clean, so the headline design promise of the whole game is
## measured properly or not claimed.
##
## Raised from 80 to 240 after a reader compared two independent runs of this
## probe and called a 2.7 point difference a regression. At 80 shots the two
## sigma band on this line is 8 points wide, so 80 could not tell 85 % from
## 77 %: the figure was precise enough to quote and not precise enough to mean
## anything. 240 brings the band to 4.6 points for about eight per cent more
## wall clock, and EVERY rate this report prints now carries its own band so
## that mistake cannot be made from this output again.
const PROMISE_SHOTS := 240
const PROMISE_MIN_X := 2.80
const PROMISE_MAX_X := 3.30
const PROMISE_MIN_Y := 1.85
const PROMISE_MAX_Y := 2.25
const PROMISE_MIN_POWER := 0.86

const POWERS: PackedFloat64Array = [0.55, 0.72, 0.86, 1.0]
const POWER_COUNT := 4
## Distances from the sweet centre used for the miscue half of the sample. They
## span "just outside the window" to "completely mistimed", evenly, so no single
## severity dominates the miscue figures.
const MISCUE_OFFSETS: PackedFloat64Array = [0.135, 0.17, 0.21, 0.25, 0.29, 0.33]

const CLASS_CLEAN := 0
const CLASS_MISCUE := 1
## Repeats per cell, per power, per contact class, per level, PER SAMPLE. The
## default gives 336 clean and 336 mishit penalties per level in each of the two
## samples, which is a two sigma band of about five points on every figure in the
## tables below. Halved when the second sample was added so the whole run still
## costs the same wall clock; pass --balance-repeats to buy precision back.
const DEFAULT_REPEATS := 3
## Offline shots resolved per frame. Small enough that the process never looks
## hung, large enough that the whole sample runs without stalling the loop.
const BATCH := 96

## DETERMINISM IS NOT PRECISION, AND CONFUSING THE TWO COST A DAY.
##
## Every seed below is fixed, so two runs of this probe print the same numbers to
## the tenth. That is a feature: a change in the keeper shows up cleanly. It is
## also a trap, and somebody fell into it: two identical runs were read as two
## agreeing MEASUREMENTS, and a three point difference against a table written
## from an older build was reported as a real shift in the save envelope. It was
## not. At the default repeat count one figure carries a two sigma band of five
## points, and running the same seeds twice does not shrink it by one hundredth
## of a point.
##
## `--balance-seed K` moves the whole sample onto a different draw of the SAME
## distributions: different aim scatter, different keeper seeds, same shape. K = 0
## is the canonical run and is bit identical to what the probe has always printed.
## Several values of K are genuinely independent samples, they can be run at the
## same time on different cores, and pooling them is the only cheap way to get a
## figure tight enough to publish. That is how the table in CONTRACTS 2.9 is now
## measured, and how it has to be measured again.
const SEED_STRIDE := 2_654_435_761

# --- Live stage --------------------------------------------------------------

## World points fired for real, one set per level. A top corner, a mid height
## side, a half side and the middle: the four cases the tables care about.
const LIVE_X: PackedFloat64Array = [-2.95, 2.95, 1.60, 0.0]
const LIVE_Y: PackedFloat64Array = [2.05, 1.20, 1.25, 1.05]
const LIVE_POWER := 0.9
## How many times each live configuration is fired for real. Sixteen live shots
## could not distinguish a broken offline model from a coin, so the plan is
## repeated: 4 levels x 4 points x 3 is 48 penalties, about 70 s of wall clock.
const LIVE_REPEATS := 3
## Offline repeats used to predict the outcome of one live configuration.
const DEFAULT_LIVE_PREDICT := 48
## Main.fire_test_shot puts the keeper back on the middle of his line and never
## runs the pre strike shuffle, so the prediction must not run it either. Feeding
## the offline keeper a shuffle the live one never had was a real bias between the
## two stages and it is exactly the sort of thing this cross check exists to catch.
const LIVE_DANCE := 0.0

const BOOT_FRAMES := 90
const BOOT_TIMEOUT := 60.0
const ARM_TIMEOUT := 25.0
const FLIGHT_TIMEOUT := 30.0
const RESET_TIMEOUT := 25.0

# --- State -------------------------------------------------------------------

var _main: Node = null
var _keeper: Node = null
var _stage: int = STAGE_BOOT
var _stage_time: float = 0.0
var _stage_frames: int = 0

var _repeats: int = DEFAULT_REPEATS
var _live_predict: int = DEFAULT_LIVE_PREDICT
var _live_enabled: bool = true
## Offset added to every shot seed, so the probe draws a DIFFERENT sample of the
## same distributions. See SEED_STRIDE.
var _seed_salt: int = 0

var _live_plan: Array[Dictionary] = []
var _live_index: int = -1
var _live_saves: int = 0
var _live_goals: int = 0
var _live_done: int = 0
var _live_predicted: float = 0.0
## Variance of the live save COUNT the offline model implies, so the report can
## say whether the two stages actually disagree or merely differ.
var _live_predicted_var: float = 0.0

var _job: int = 0
var _job_total: int = 0
var _round_index_backup: int = 0
var _signals_cut: bool = false
var _sim_msec: int = 0

## [sample][level][class] -> PackedInt32Array of V_COUNT verdict counts.
var _by_class: Array = []
## [sample][level][zone] -> PackedInt32Array, clean strikes only.
var _by_zone: Array = []
## [sample][level][zone] -> PackedInt32Array, mishit strikes only.
var _by_zone_miscue: Array = []
## [sample] -> PackedInt32Array over levels. Clean, top corner, power >= 0.86:
## the shot that must keep beating a Legende.
var _corner_total: Array = []
var _corner_goals: Array = []
## The dedicated top corner promise stage, one entry per level.
var _promise_total: PackedInt32Array = PackedInt32Array()
var _promise_goals: PackedInt32Array = PackedInt32Array()
## Jobs belonging to the two aim grids. Anything past this is a promise shot.
var _grid_total: int = 0

var _report: PackedStringArray = PackedStringArray()


## Called by Main before this node is added to the tree.
func setup(main_node: Node) -> void:
	_main = main_node


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_parse_args()
	_by_class = []
	_by_zone = []
	_by_zone_miscue = []
	_corner_total = []
	_corner_goals = []
	for _sample in SAMPLE_COUNT:
		var s_class: Array = []
		var s_zone: Array = []
		var s_zone_miscue: Array = []
		var s_corner_total := PackedInt32Array()
		var s_corner_goals := PackedInt32Array()
		for _level in L_COUNT:
			var classes: Array = []
			for _c in 2:
				classes.append(_new_counts())
			s_class.append(classes)
			var zones: Array = []
			var zones_miscue: Array = []
			for _z in ZONE_COUNT:
				zones.append(_new_counts())
				zones_miscue.append(_new_counts())
			s_zone.append(zones)
			s_zone_miscue.append(zones_miscue)
			s_corner_total.append(0)
			s_corner_goals.append(0)
		_by_class.append(s_class)
		_by_zone.append(s_zone)
		_by_zone_miscue.append(s_zone_miscue)
		_corner_total.append(s_corner_total)
		_corner_goals.append(s_corner_goals)
	_promise_total = PackedInt32Array()
	_promise_goals = PackedInt32Array()
	for _level in L_COUNT:
		_promise_total.append(0)
		_promise_goals.append(0)
	_grid_total = SAMPLE_COUNT * L_COUNT * 2 * CELL_COUNT * POWER_COUNT * _repeats
	_job_total = _grid_total + L_COUNT * PROMISE_SHOTS
	print("")
	print("=== GOAL - sonde d'equilibrage ===")


## Optional tuning arguments, so the same probe can be run coarse while a number
## is being searched for and fine once it is found.
func _parse_args() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var index: int = 0
	while index < args.size():
		var arg: String = args[index]
		if arg == "--balance-repeats" and index + 1 < args.size():
			index += 1
			_repeats = clampi(int(args[index]), 1, 64)
		elif arg == "--balance-live" and index + 1 < args.size():
			index += 1
			var wanted: int = clampi(int(args[index]), 0, 200)
			_live_enabled = wanted > 0
			_live_predict = maxi(wanted, 1)
		elif arg == "--balance-seed" and index + 1 < args.size():
			index += 1
			_seed_salt = absi(int(args[index]))
		index += 1


## The seed of one shot: its place in the plan, plus the salt that moves the whole
## run onto another draw. See SEED_STRIDE.
func _shot_seed(base: int, stride: int, slot: int) -> int:
	return base + slot * stride + _seed_salt * SEED_STRIDE


func _process(delta: float) -> void:
	_stage_time += delta
	_stage_frames += 1

	if _stage == STAGE_BOOT:
		_tick_boot()
	elif _stage == STAGE_LIVE_ARM:
		_tick_live_arm()
	elif _stage == STAGE_LIVE_FLIGHT:
		_tick_live_flight()
	elif _stage == STAGE_LIVE_RESET:
		_tick_live_reset()
	elif _stage == STAGE_SIM:
		_tick_sim()
	elif _stage == STAGE_REPORT:
		_finish()


func _goto(stage: int) -> void:
	_stage = stage
	_stage_time = 0.0
	_stage_frames = 0


# =============================================================================
# Boot
# =============================================================================

func _tick_boot() -> void:
	if _main == null:
		push_error("BalanceProbe: Main n'a pas appele setup().")
		_goto(STAGE_REPORT)
		return
	if _stage_time > BOOT_TIMEOUT:
		push_error("BalanceProbe: le monde n'est pas construit apres %.0f s." % BOOT_TIMEOUT)
		_goto(STAGE_REPORT)
		return
	if not bool(_main.call("_probe_world_ready")):
		return
	if _stage_frames < BOOT_FRAMES:
		return

	_keeper = _main.get("keeper") as Node
	if _keeper == null:
		push_error("BalanceProbe: pas de gardien dans la scene.")
		_goto(STAGE_REPORT)
		return

	_check_enums()
	_build_live_plan()
	if not _live_enabled or _live_plan.is_empty():
		_start_sim()
		return
	_main.call("_probe_begin_training")
	_goto(STAGE_LIVE_ARM)


## The offline stage mirrors the Shootout.Verdict ids as plain integers, exactly
## like the smoke probe does. A renumbering of the enum has to be caught here or
## every table below silently changes meaning.
func _check_enums() -> void:
	var names: Dictionary = _main.call("_probe_verdict_names")
	var expected := {"BUT": V_BUT, "ARRET": V_ARRET, "POTEAU": V_POTEAU,
		"BARRE": V_BARRE, "DEHORS": V_DEHORS}
	for key in expected:
		if int(names.get(key, -99)) != int(expected[key]):
			push_error("BalanceProbe: l'id du verdict %s a change, le rapport serait faux." % key)
	if int(KeeperBrain.Level.LEGENDE) != L_COUNT - 1:
		push_error("BalanceProbe: l'echelle des niveaux a change.")


# =============================================================================
# Aim mapping
# =============================================================================

## The reticle mapping belongs to ShotModel, so it is inverted by bisection here
## rather than duplicated. aim_point is monotonic on each axis.
func _aim_for(world_x: float, world_y: float) -> Vector2:
	return Vector2(_solve_axis(true, world_x), _solve_axis(false, world_y))


func _solve_axis(horizontal: bool, wanted: float) -> float:
	var low: float = -6.0
	var high: float = 6.0
	for _i in 42:
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


## Which report bucket an aimed world point falls into.
func _zone_of(world_x: float, world_y: float) -> int:
	var right: bool = world_x > 0.0
	if absf(world_x) >= BAND_WIDE:
		if world_y >= BAND_HIGH:
			return 1 if right else 0
		if world_y <= BAND_LOW:
			return 5 if right else 4
		return 3 if right else 2
	if absf(world_x) >= BAND_HALF:
		return 7 if right else 6
	return 8


# =============================================================================
# Live stage
# =============================================================================

func _build_live_plan() -> void:
	_live_plan = []
	for _pass in LIVE_REPEATS:
		for level in L_COUNT:
			for slot in LIVE_X.size():
				_live_plan.append({
					"level": level,
					"x": float(LIVE_X[slot]),
					"y": float(LIVE_Y[slot]),
				})


func _tick_live_arm() -> void:
	if _stage_time > ARM_TIMEOUT:
		push_warning("BalanceProbe: le jeu n'est jamais revenu en placement, etape en jeu abregee.")
		_start_sim()
		return
	if not bool(_main.call("_probe_ready_to_fire")):
		return
	if _stage_time < 0.2:
		return

	_live_index += 1
	if _live_index >= _live_plan.size():
		_start_sim()
		return

	var entry: Dictionary = _live_plan[_live_index]
	_main.call("_probe_set_keeper_level", int(entry["level"]))
	_main.call("fire_test_shot",
		_aim_for(float(entry["x"]), float(entry["y"])), LIVE_POWER, 0.0, 0.0)
	_goto(STAGE_LIVE_FLIGHT)


func _tick_live_flight() -> void:
	if _stage_time > FLIGHT_TIMEOUT:
		push_warning("BalanceProbe: un tir en jeu ne s'est jamais resolu.")
		_goto(STAGE_LIVE_RESET)
		return
	if not bool(_main.call("_probe_shot_settled")):
		return
	var verdict: int = int(_main.get("last_verdict"))
	_live_done += 1
	if verdict == V_ARRET:
		_live_saves += 1
	elif verdict == V_BUT:
		_live_goals += 1
	_goto(STAGE_LIVE_RESET)


func _tick_live_reset() -> void:
	if _stage_time > RESET_TIMEOUT:
		push_warning("BalanceProbe: le jeu ne s'est pas remis en place, etape en jeu abregee.")
		_start_sim()
		return
	if not bool(_main.call("_probe_phase_is_placement")):
		return
	if _stage_time < 0.15:
		return
	_goto(STAGE_LIVE_ARM)


# =============================================================================
# Offline stage
# =============================================================================

## Takes the keeper's body over: Main is parked, its handlers are unhooked, and
## the round index (which seeds the keeper) is remembered so the game is handed
## back exactly as it was found.
func _start_sim() -> void:
	if _stage == STAGE_SIM:
		return
	_main.call("force_phase", PH_ACCUEIL)
	_cut_keeper_signals()
	var series: Node = _autoload("Shootout")
	if series != null:
		var stored: Variant = series.get("round_index")
		if typeof(stored) == TYPE_INT:
			_round_index_backup = int(stored)
	if _live_enabled:
		_predict_live()
	_job = 0
	_sim_msec = Time.get_ticks_msec()
	print("  %d penalties simules hors ligne..." % _job_total)
	_goto(STAGE_SIM)


func _tick_sim() -> void:
	var budget: int = BATCH
	while budget > 0 and _job < _job_total:
		_run_job(_job)
		_job += 1
		budget -= 1
	if _job >= _job_total:
		_sim_msec = Time.get_ticks_msec() - _sim_msec
		_restore_keeper_signals()
		_restore_round_index()
		_goto(STAGE_REPORT)


## Decodes one point of the sample grid and files its verdict.
func _run_job(index: int) -> void:
	if index >= _grid_total:
		_run_promise(index - _grid_total)
		return
	var rest: int = index
	var repeat: int = rest % _repeats
	rest /= _repeats
	var power_index: int = rest % POWER_COUNT
	rest /= POWER_COUNT
	var cell: int = rest % CELL_COUNT
	rest /= CELL_COUNT
	var contact: int = rest % 2
	rest /= 2
	var level: int = rest % L_COUNT
	rest /= L_COUNT
	var sample: int = rest % SAMPLE_COUNT

	var shot_seed: int = _shot_seed(1_000_003, 7919, index)
	var rng := RandomNumberGenerator.new()
	rng.seed = shot_seed

	var spot: Vector2 = _draw_aim(sample, cell, rng)
	var world_x: float = spot.x
	var world_y: float = spot.y
	var aim: Vector2 = _aim_for(world_x, world_y)
	var power: float = float(POWERS[power_index])

	var release: float = SWEET_CENTRE
	if contact == CLASS_MISCUE:
		# The severity is drawn from THREE axes of the grid, not from the repeat
		# alone: keyed on the repeat only, a run with fewer repeats than there are
		# offsets would silently sample none but the mildest mistimings and report
		# a flattering miscue figure.
		var severity: int = (repeat + power_index * 2 + cell) % MISCUE_OFFSETS.size()
		var offset: float = float(MISCUE_OFFSETS[severity])
		if SWEET_CENTRE + offset <= 1.0 and (repeat % 2) == 0:
			release = SWEET_CENTRE + offset
		else:
			release = SWEET_CENTRE - offset

	var dance: float = 0.30 + 0.70 * rng.randf()
	var verdict: int = _simulate(aim, power, 0.0, 0.0, release, level, shot_seed, dance)
	var zone: int = _zone_of(world_x, world_y)

	_bump(_by_class[sample][level][contact], verdict)
	if contact == CLASS_CLEAN:
		_bump(_by_zone[sample][level][zone], verdict)
		# The design promise, measured strictly: a genuine top corner, not merely
		# the upper outer bucket. Hard against the post and high under the bar.
		if absf(world_x) >= TOP_CORNER_X and world_y >= TOP_CORNER_Y and power >= 0.86:
			var totals: PackedInt32Array = _corner_total[sample]
			totals[level] += 1
			if verdict == V_BUT:
				var goals: PackedInt32Array = _corner_goals[sample]
				goals[level] += 1
	else:
		_bump(_by_zone_miscue[sample][level][zone], verdict)


## One shot of the top corner promise stage: a clean, hard penalty into a genuine
## angle of the bar, on both sides, at every level. Nothing here is conditioned on
## anything, so the rate it reports is the rate.
func _run_promise(slot: int) -> void:
	var level: int = slot % L_COUNT
	var shot_seed: int = _shot_seed(7_700_017, 15_485_863, slot)
	var rng := RandomNumberGenerator.new()
	rng.seed = shot_seed
	var side: float = 1.0 if (slot / L_COUNT) % 2 == 0 else -1.0
	var world_x: float = side * rng.randf_range(PROMISE_MIN_X, PROMISE_MAX_X)
	var world_y: float = rng.randf_range(PROMISE_MIN_Y, PROMISE_MAX_Y)
	var power: float = rng.randf_range(PROMISE_MIN_POWER, 1.0)
	var dance: float = 0.30 + 0.70 * rng.randf()
	var verdict: int = _simulate(
		_aim_for(world_x, world_y), power, 0.0, 0.0, SWEET_CENTRE, level, shot_seed, dance)
	_promise_total[level] += 1
	if verdict == V_BUT:
		_promise_goals[level] += 1


## One aimed world point, drawn from the sample this job belongs to.
##
## (a) UNIFORM: the cell of the grid this job owns, jittered over exactly its own
## area, so the twenty eight cells tile the mouth without overlap or gap.
##
## (b) REALISTIC: one draw from AIM_CLUSTERS, weights and spreads as written
## there. `cell` picks the cluster in a fixed rotation weighted by the table
## rather than being redrawn at random, so every run of the probe contains the
## same MIX even at a small repeat count. Only the scatter inside a cluster is
## random, which is what stops a short run from accidentally reporting a sample
## made mostly of top corners.
func _draw_aim(sample: int, cell: int, rng: RandomNumberGenerator) -> Vector2:
	if sample == SAMPLE_UNIFORM:
		var column: int = cell % COL_COUNT
		var row: int = cell / COL_COUNT
		return Vector2(
			float(AIM_COLS[column]) + rng.randf_range(-JITTER_X, JITTER_X),
			maxf(float(AIM_ROWS[row]) + rng.randf_range(-JITTER_Y, JITTER_Y), REAL_MIN_Y))

	# Deterministic weighted rotation over the clusters: cell / CELL_COUNT walks
	# the cumulative weights, so the 28 cells reproduce the table's proportions.
	var position: float = (float(cell) + 0.5) / float(CELL_COUNT)
	var chosen: Array = AIM_CLUSTERS[AIM_CLUSTERS.size() - 1]
	var accumulated: float = 0.0
	for entry in AIM_CLUSTERS:
		var cluster: Array = entry
		accumulated += float(cluster[0])
		if position <= accumulated:
			chosen = cluster
			break
	var side: float = 1.0 if rng.randf() < 0.5 else -1.0
	var x: float = side * (float(chosen[1]) + rng.randfn(0.0, float(chosen[2])))
	var y: float = float(chosen[3]) + rng.randfn(0.0, float(chosen[4]))
	return Vector2(
		clampf(x, -REAL_MAX_X, REAL_MAX_X),
		clampf(y, REAL_MIN_Y, REAL_MAX_Y))


## One whole penalty, resolved without waiting for the clock, in the order Main
## uses.
##
## The keeper is the real node: reset to its line, given the same body language
## the shooter would have leaked, then driven step by step with track() and
## attempt_save() exactly as Main._step_segment does. The ball is Aero, stepped
## at the project physics rate, in the same still air the game uses.
func _simulate(aim: Vector2, power: float, side: float, lift: float,
		release: float, level: int, shot_seed: int, dance: float) -> int:
	var shot: Dictionary = ShotModel.resolve(
		aim, power, side, lift, release, SWEET_CENTRE, shot_seed)
	var cues: Dictionary = ShotModel.tell_cues(aim, power, side, 0.0, 0, level)

	_seed_keeper(shot_seed)
	_keeper.set("level", level)
	_keeper.call("reset_to_line")
	_keeper.call("prepare", dance)
	_keeper.call("read_shooter", cues)

	var pos: Vector3 = Field.SPOT
	var vel: Vector3 = shot.get("velocity", Vector3.ZERO)
	var spin: Vector3 = shot.get("spin", Vector3.ZERO)
	if not vel.is_finite() or vel.length() < 0.01:
		return V_DEHORS

	var t: float = 0.0
	for _i in MAX_STEPS:
		var stepped: Array = Aero.integrate(pos, vel, spin, Vector3.ZERO, STEP)
		var to_pos: Vector3 = stepped[0]
		var to_vel: Vector3 = stepped[1]
		if not to_pos.is_finite() or not to_vel.is_finite():
			return V_DEHORS
		var t_to: float = t + STEP
		var step_velocity: Vector3 = (to_pos - pos) / STEP

		# 1. The frame. Unlike the game this ends the flight: a rebound that goes
		# back in is rare enough that counting it as a post keeps the table
		# readable, and it gets its own column rather than being hidden.
		var frame: Dictionary = Field.sweep_frame(pos, to_pos)
		if bool(frame.get("hit", false)):
			return V_BARRE if int(frame.get("part", 0)) == Field.FRAME_BAR else V_POTEAU

		# 2. The keeper, before the line.
		_keeper.call("track", pos, step_velocity, spin, t_to)
		var save: Dictionary = _keeper.call("attempt_save", pos, to_pos)
		if bool(save.get("saved", false)):
			return V_ARRET

		# 3. The goal plane.
		var cross: Dictionary = Field.cross_goal_plane(pos, to_pos)
		if bool(cross.get("crossed", false)):
			var point: Vector3 = cross.get("point", to_pos)
			return V_BUT if Field.is_within_frame(point) else V_DEHORS

		if Field.is_out_of_area(to_pos):
			return V_DEHORS

		# 4. The turf, for a mishit that lands before the line.
		if to_pos.y <= Field.BALL_RADIUS and to_vel.y < 0.0:
			var reflected: Array = Aero.bounce(
				to_vel, spin, Vector3.UP, TURF_RESTITUTION, TURF_FRICTION)
			to_vel = reflected[0]
			spin = reflected[1]
			to_pos.y = Field.BALL_RADIUS + 0.004

		pos = to_pos
		vel = to_vel
		spin = Aero.decay_spin(spin, STEP)
		t = t_to
	return V_DEHORS


## Runs the offline model over the very same configurations the live stage fired,
## so the report can put the two side by side.
##
## "The very same" is meant literally, and it was not before. The prediction used
## to jitter the aim by up to 18 cm and to hand the keeper a pre strike shuffle,
## neither of which the live stage does, so the two stages were measuring two
## different penalties and the gap between them could never be interpreted. Now
## the only thing that varies between the repeats is the seed, which is the only
## thing that varies live.
func _predict_live() -> void:
	_live_predicted = 0.0
	_live_predicted_var = 0.0
	if _live_plan.is_empty():
		return
	var index: int = 0
	for entry in _live_plan:
		var level: int = int(entry["level"])
		var saves: int = 0
		for k in _live_predict:
			var shot_seed: int = _shot_seed(5_100_011, 6151, index * _live_predict + k)
			var verdict: int = _simulate(
				_aim_for(float(entry["x"]), float(entry["y"])), LIVE_POWER, 0.0, 0.0,
				SWEET_CENTRE, level, shot_seed, LIVE_DANCE)
			if verdict == V_ARRET:
				saves += 1
		var rate: float = float(saves) / float(_live_predict)
		_live_predicted += rate
		# Each live shot is one Bernoulli draw at this configuration's own rate, so
		# the variance of the live TOTAL is the sum of p(1-p) over the plan. That is
		# what turns "3 against 4.2" into either a finding or a shrug.
		_live_predicted_var += rate * (1.0 - rate)
		index += 1


# =============================================================================
# Borrowing the keeper
# =============================================================================

## Main listens to the keeper. A simulated save would otherwise latch a real
## verdict, scuff the real turf and fire real sounds, so the wires come off for
## the duration of the offline stage.
func _cut_keeper_signals() -> void:
	if _keeper == null or _signals_cut:
		return
	_signals_cut = true
	for signal_name in ["saved", "dive_started", "landed"]:
		for connection in _keeper.get_signal_connection_list(signal_name):
			var target: Callable = connection["callable"]
			_keeper.disconnect(signal_name, target)


func _restore_keeper_signals() -> void:
	if _keeper == null or not _signals_cut:
		return
	_signals_cut = false
	if _main == null:
		return
	if not _keeper.is_connected("saved", Callable(_main, "_on_keeper_saved")):
		_keeper.connect("saved", Callable(_main, "_on_keeper_saved"))
	if not _keeper.is_connected("dive_started", Callable(_main, "_on_keeper_dive_started")):
		_keeper.connect("dive_started", Callable(_main, "_on_keeper_dive_started"))
	if not _keeper.is_connected("landed", Callable(_main, "_on_keeper_landed")):
		_keeper.connect("landed", Callable(_main, "_on_keeper_landed"))


## The keeper draws its own per attempt seed from the campaign seed and the round
## index. Moving the round index is the only honest way to give two simulated
## penalties two different keepers without reaching inside the node.
func _seed_keeper(value: int) -> void:
	var series: Node = _autoload("Shootout")
	if series == null:
		return
	series.set("round_index", absi(value) % 100003)


func _restore_round_index() -> void:
	var series: Node = _autoload("Shootout")
	if series == null:
		return
	series.set("round_index", _round_index_backup)


## The autoloads cannot be named by identifier in a file under tests/: they are
## not registered under --script. Looking them up by node name is null safe.
func _autoload(node_name: String) -> Node:
	var tree: SceneTree = get_tree()
	if tree == null or tree.root == null:
		return null
	return tree.root.get_node_or_null(NodePath(node_name))


# =============================================================================
# Tallies
# =============================================================================

func _new_counts() -> PackedInt32Array:
	var counts := PackedInt32Array()
	counts.resize(V_COUNT)
	counts.fill(0)
	return counts


func _bump(counts: PackedInt32Array, verdict: int) -> void:
	if verdict < 0 or verdict >= V_COUNT:
		return
	counts[verdict] += 1


func _total(counts: PackedInt32Array) -> int:
	var sum: int = 0
	for value in counts:
		sum += value
	return sum


func _share(counts: PackedInt32Array, verdict: int) -> float:
	var total: int = _total(counts)
	if total <= 0:
		return 0.0
	return 100.0 * float(counts[verdict]) / float(total)


## Two sigma on one printed share, in points of percentage.
##
## THIS IS THE MOST IMPORTANT NUMBER IN THE REPORT and it used not to be here.
## Every figure below is a binomial draw, so at the default repeat count a save
## rate near 60 % carries a two sigma band of about five points. A reader who
## does not see that band next to the rate will read a three point difference
## between two runs, or between a run and a table written months ago, as a
## regression, write it down as one, and send somebody off to tune a keeper that
## never moved. That happened. The band is printed next to the rate now, at the
## same width, so the comparison is impossible to get wrong.
func _two_sigma(counts: PackedInt32Array, verdict: int) -> float:
	var total: int = _total(counts)
	if total <= 0:
		return 0.0
	var p: float = float(counts[verdict]) / float(total)
	return 200.0 * sqrt(maxf(p * (1.0 - p), 0.0) / float(total))


## Two sigma on a plain goals over shots rate, in points of percentage.
func _two_sigma_rate(goals: int, total: int) -> float:
	if total <= 0:
		return 0.0
	var p: float = float(goals) / float(total)
	return 200.0 * sqrt(maxf(p * (1.0 - p), 0.0) / float(total))


func _sum_counts(source: Array) -> PackedInt32Array:
	var out := _new_counts()
	for entry in source:
		var counts: PackedInt32Array = entry
		for v in V_COUNT:
			out[v] += counts[v]
	return out


func _sum_zones(table: Array, level: int, zones: PackedInt32Array) -> PackedInt32Array:
	var out := _new_counts()
	for zone in zones:
		var counts: PackedInt32Array = table[level][zone]
		for v in V_COUNT:
			out[v] += counts[v]
	return out


func _sum_levels(table: Array, class_index: int) -> PackedInt32Array:
	var out := _new_counts()
	for level in L_COUNT:
		var counts: PackedInt32Array = table[level][class_index]
		for v in V_COUNT:
			out[v] += counts[v]
	return out


# =============================================================================
# Report
# =============================================================================

func _finish() -> void:
	if _stage == STAGE_DONE:
		return
	_stage = STAGE_DONE

	_line("")
	_line("  echantillon : %d tirs hors ligne (%d repetitions par case, graine %d), %.1f s"
		% [_job_total, _repeats, _seed_salt, float(_sim_msec) / 1000.0])

	_line("")
	_line("--- Echantillon en jeu (Main.fire_test_shot) ---")
	if _live_done > 0:
		var predicted_rate: float = _live_predicted / float(maxi(_live_plan.size(), 1))
		var expected: float = predicted_rate * float(_live_done)
		var sigma: float = sqrt(maxf(_live_predicted_var, 0.0)
			* float(_live_done) / float(maxi(_live_plan.size(), 1)))
		_line("  %d penalties tires dans le vrai jeu : %d arrets, %d buts (%.1f %% d'arrets)"
			% [_live_done, _live_saves, _live_goals, 100.0 * float(_live_saves) / float(_live_done)])
		_line("  le modele hors ligne predit %.1f arrets sur ces memes tirs (%.1f %%)"
			% [expected, 100.0 * predicted_rate])
		# Two sigma on the live COUNT. Without it the reader cannot tell a broken
		# offline model from an unlucky afternoon, which is what the first version
		# of this cross check asked them to do.
		_line("  bruit attendu sur %d tirs : +/- %.1f arrets (2 sigma), ecart observe %.1f"
			% [_live_done, 2.0 * sigma, absf(float(_live_saves) - expected)])
		if absf(float(_live_saves) - expected) > 2.0 * sigma and sigma > 0.0:
			_line("  ECART SIGNIFICATIF : le tableau hors ligne ci dessous ne decrit pas le vrai jeu.")
		else:
			_line("  ecart compatible avec le bruit : le tableau hors ligne est credible.")
	else:
		_line("  etape en jeu desactivee (--balance-live 0)")

	_line("")
	_line("--- PROMESSE : une vraie lucarne bien frappee bat le gardien ---")
	_line("  %d penalties par niveau, |x| entre %.2f et %.2f m, y entre %.2f et %.2f m,"
		% [PROMISE_SHOTS, PROMISE_MIN_X, PROMISE_MAX_X, PROMISE_MIN_Y, PROMISE_MAX_Y])
	_line("  puissance au dessus de %.2f, contact propre. Cible : plus de 85 %% de buts," % PROMISE_MIN_POWER)
	_line("  et au moins 80 %% contre une Legende, qui est la promesse du jeu.")
	for level in L_COUNT:
		var total: int = _promise_total[level]
		var goals: int = _promise_goals[level]
		var rate: float = 0.0
		if total > 0:
			rate = 100.0 * float(goals) / float(total)
		_line("  %-10s %d / %d buts (%.1f %% +/- %.1f pts)"
			% [LEVEL_LABELS[level], goals, total, rate, _two_sigma_rate(goals, total)])

	for sample in SAMPLE_COUNT:
		_report_sample(sample)

	_recap()

	_line("")
	_line("==================================")
	_line("")

	for entry in _report:
		print(entry)

	# Same reason as tests/smoke_probe.gd: Main owns the exit so the audio server
	# gets the frames it needs to release its voices before the process ends.
	if _main != null:
		_main.call("quit_clean", 0)
		return
	var tree: SceneTree = get_tree()
	if tree != null:
		Engine.time_scale = 1.0
		tree.quit(0)


## THE FOUR NUMBERS THAT GO IN THE DOCUMENT, and nothing else, on their own, at
## the bottom of a report three hundred lines long.
##
## This block exists because the reference table in CONTRACTS 2.9 has twice been
## written from the wrong place in this output: once from a sample far too small
## to carry the digits it was quoted to, and once by reading the stress sample
## instead of the reference one. The tables above are for understanding the
## keeper; THIS is the line to copy, it names the sample it comes from, it
## carries its own band, and it says out loud how many shots it stands on.
func _recap() -> void:
	var by_class: Array = _by_class[SAMPLE_REAL]
	_line("")
	_line("###############################################################")
	_line("### A RECOPIER DANS CONTRACTS 2.9 - et rien d'autre.")
	_line("### Taux d'ARRETS sur frappe PROPRE, echantillon de VISEE REALISTE.")
	_line("### Graine %d, %d repetitions par case." % [_seed_salt, _repeats])
	_line("###############################################################")
	for level in L_COUNT:
		var clean: PackedInt32Array = by_class[level][CLASS_CLEAN]
		_line("  %-10s %5.1f %% +/- %.1f pts   (%d arrets sur %d tirs propres)"
			% [LEVEL_LABELS[level], _share(clean, V_ARRET),
				_two_sigma(clean, V_ARRET), clean[V_ARRET], _total(clean)])
	_line("  La bande +/- ci dessus est celle d'UNE graine. Elle est trop large pour")
	_line("  publier une cible : relance avec --balance-seed 0..5 en parallele et")
	_line("  additionne les comptes bruts, la bande est alors deux fois et demie plus")
	_line("  serree. Un chiffre que personne ne peut refaire n'est pas une mesure.")


## One whole set of tables for one of the two samples. Both are printed, always,
## and in the same shape, so the stress case and the reference case can be read
## against each other rather than one of them being quoted on its own.
func _report_sample(sample: int) -> void:
	var by_class: Array = _by_class[sample]
	var by_zone: Array = _by_zone[sample]
	var by_zone_miscue: Array = _by_zone_miscue[sample]

	_line("")
	_line("###############################################################")
	_line("### ECHANTILLON %d : %s" % [sample + 1, SAMPLE_LABELS[sample]])
	if sample == SAMPLE_REAL:
		_line("### C'est CET echantillon que les cibles d'equilibrage jugent.")
		_line("### Distribution : voir AIM_CLUSTERS en tete de fichier.")
	else:
		_line("### Cas de stress : 44 % des tirs colles a un poteau, aucun humain")
		_line("### ne tire comme cela. A lire comme une borne basse, pas une cible.")
	_line("###############################################################")

	_line("")
	_line("--- Bilan par niveau, frappes PROPRES (relachees dans la fenetre) ---")
	_line("  cibles d'equilibrage : Debutant 20-25 %, Confirme 35 %, Pro 50 %, Legende 62-68 %")
	_line("  la colonne +/- est le bruit a 2 sigma sur le taux d'arrets de la ligne :")
	_line("  un ecart plus petit qu'elle n'est PAS un changement de reglage.")
	_line("  niveau      tirs   arrets     buts   poteau/barre   hors cadre        +/-")
	for level in L_COUNT:
		var clean: PackedInt32Array = by_class[level][CLASS_CLEAN]
		_line("%s   %5.1f pts" % [_row(LEVEL_LABELS[level], clean), _two_sigma(clean, V_ARRET)])

	_line("")
	_line("--- Bilan par niveau, CASSEROLES (relachees hors de la fenetre) ---")
	_line("  niveau      tirs   arrets     buts   poteau/barre   hors cadre")
	for level in L_COUNT:
		_line(_row(LEVEL_LABELS[level], by_class[level][CLASS_MISCUE]))

	_line("")
	_line("--- Bilan par niveau, tout l'echantillon ---")
	_line("  niveau      tirs   arrets     buts   poteau/barre   hors cadre")
	for level in L_COUNT:
		_line(_row(LEVEL_LABELS[level], _sum_counts(by_class[level])))

	var all_clean: PackedInt32Array = _sum_levels(by_class, CLASS_CLEAN)
	var all_miscue: PackedInt32Array = _sum_levels(by_class, CLASS_MISCUE)
	_line("")
	_line("--- Propre contre casserole, tous niveaux confondus ---")
	_line(_row("propres", all_clean))
	_line(_row("casserole", all_miscue))
	_line("  une casserole marque %.1f %% du temps +/- %.1f pts (cible : moins de 30 %%)"
		% [_share(all_miscue, V_BUT), _two_sigma(all_miscue, V_BUT)])

	_line("")
	_line("--- Arrets par placement, frappes propres (%) ---")
	var header: String = "  niveau     "
	for zone in ZONE_COUNT:
		header += "%13s" % ZONE_LABELS[zone]
	_line(header)
	for level in L_COUNT:
		var row: String = "  %-10s " % LEVEL_LABELS[level]
		for zone in ZONE_COUNT:
			row += "%12.1f%%" % _share(by_zone[level][zone], V_ARRET)
		_line(row)

	_line("")
	_line("--- Buts par placement, frappes propres (%) ---")
	_line(header)
	for level in L_COUNT:
		var row: String = "  %-10s " % LEVEL_LABELS[level]
		for zone in ZONE_COUNT:
			row += "%12.1f%%" % _share(by_zone[level][zone], V_BUT)
		_line(row)

	_line("")
	_line("--- Buts par placement, casseroles (%) ---")
	_line(header)
	for level in L_COUNT:
		var row: String = "  %-10s " % LEVEL_LABELS[level]
		for zone in ZONE_COUNT:
			row += "%12.1f%%" % _share(by_zone_miscue[level][zone], V_BUT)
		_line(row)

	_line("")
	_line("--- Regroupements, frappes propres (arrets % / buts %) ---")
	_line("  niveau        six angles      deux mi-cotes      plein centre")
	for level in L_COUNT:
		var angles: PackedInt32Array = _sum_zones(by_zone, level, ZONE_ANGLES)
		var halves: PackedInt32Array = _sum_zones(by_zone, level, ZONE_HALVES)
		var middle: PackedInt32Array = _sum_zones(by_zone, level, ZONE_MIDDLE)
		_line("  %-10s  %5.1f / %5.1f      %5.1f / %5.1f      %5.1f / %5.1f" % [
			LEVEL_LABELS[level],
			_share(angles, V_ARRET), _share(angles, V_BUT),
			_share(halves, V_ARRET), _share(halves, V_BUT),
			_share(middle, V_ARRET), _share(middle, V_BUT)])

	_line("")
	_line("--- Vraie lucarne dans CET echantillon (|x| >= %.1f m, y >= %.1f m) ---"
		% [TOP_CORNER_X, TOP_CORNER_Y])
	_line("  (peu de tirs y tombent : la promesse est jugee sur son etape dediee plus haut)")
	var totals: PackedInt32Array = _corner_total[sample]
	var goals: PackedInt32Array = _corner_goals[sample]
	for level in L_COUNT:
		var total: int = totals[level]
		var scored: int = goals[level]
		var rate: float = 0.0
		if total > 0:
			rate = 100.0 * float(scored) / float(total)
		_line("  %-10s %d / %d buts (%.1f %%)" % [LEVEL_LABELS[level], scored, total, rate])


func _row(label: String, counts: PackedInt32Array) -> String:
	return "  %-10s %6d   %6.1f%%  %6.1f%%   %8.1f%%   %8.1f%%" % [
		label, _total(counts),
		_share(counts, V_ARRET), _share(counts, V_BUT),
		_share(counts, V_POTEAU) + _share(counts, V_BARRE),
		_share(counts, V_DEHORS)]


func _line(text: String) -> void:
	_report.append(text)
