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
const STAGE_REPORT := 5
const STAGE_DONE := 6

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
		_goto(STAGE_REPORT)
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
		_goto(STAGE_REPORT)
	else:
		_goto(STAGE_ARM)


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
	else:
		_check(true, "%s : arret en deux temps, le ballon est repousse (%.2f m du gant)"
			% [_shot_name(), reach])

	if bool(_current.get("catch", false)):
		_check(held, "%s : le gardien garde le ballon dans ses gants" % _shot_name())


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

	_check_series()

	_line("")
	for index in _observed.size():
		var name_of: String = String(_plan[index].get("name", "tir")) if index < _plan.size() else "tir"
		_line("  tir %d : %s -> %s" % [
			index + 1, name_of, String(_main.call("_probe_verdict_label", _observed[index]))])
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
