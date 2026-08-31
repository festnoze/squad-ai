## GOAL - the goalkeeper's body.
##
## This node renders a keeper, it never decides anything. Every limb position it
## draws comes from KeeperBrain.dive_pose(), and every decision it takes comes
## from KeeperBrain.read_cues() / estimate_cross() / choose_dive(). The split is
## deliberate: the brain is pure logic and is unit tested, the body is pure
## presentation and cannot be unit tested, so nothing able to change a verdict is
## allowed to live in this file.
##
## Two invariants hold the module together.
##
## 1. What you see is what saves. pose() returns exactly the dictionary that was
##    used to place the meshes this frame, shuffle offset included, and
##    attempt_save() feeds that very dictionary to KeeperBrain.try_save(). A
##    glove drawn 20 cm away from the ball can never "save" it, and a glove drawn
##    on the ball can never miss it.
##
## 2. No animation timeline. There is no keyframed dive, no tween, no hardcoded
##    curve able to drift out of phase with the 120 Hz physics. The dive is
##    dive_pose(target, t) sampled at the true elapsed flight time, the pre strike
##    shuffle is line_dance(elapsed), and even the celebration is rebuilt every
##    frame from the pose it started from.
##
## 3. He commits ONCE, at the last responsible moment. `_should_commit` is where
##    that lives and it is worth reading before anything else in this file: a
##    gamble taken during the run up buys a HEAD START, it is not an order to
##    throw himself down at contact. On a hard penalty he spends the lot; on a
##    scuffed one that takes 0.9 s to arrive he waits, watches, and dives on
##    something he has actually seen. After that he lives with his decision:
##    there is no mid air retarget, which is both honest and what keeps the top
##    corner unreachable.
##
## The one piece of real work done here is the skeleton solve. The brain hands
## over world space targets (a centre, two gloves, two boots, a roll angle and an
## airborne factor) and this file turns them into joint transforms with analytic
## two bone inverse kinematics: law of cosines for the elbow or knee angle, pole
## vector for the plane it bends in. That dozen of lines is the difference
## between a body throwing itself sideways and a puppet dragged by its hands.
##
## Frames: the keeper stands on the goal line and looks towards +Z (the shooter).
## Per the contract +X is on the shooter's right, therefore on the keeper's LEFT,
## so the keeper's right hand direction is `face.cross(up)`, which is -X when he
## stands upright. Every anchor below is expressed in that measured body frame
## rather than in world axes, so the whole skeleton keeps working while the body
## rolls through a full horizontal dive.
class_name Keeper
extends Node3D

signal saved(limb: String, point: Vector3)
signal dive_started(side: int, height: int, gambled: bool)
signal landed()

# Mirrors of Shootout.Verdict. The autoload cannot be named at parse time in a
# file that must also compile under `--check-only --script`, and a verdict is
# just a small int, so the mapping is restated here instead of imported.
const _V_BUT := 0
const _V_ARRET := 1
const _V_POTEAU := 2
const _V_BARRE := 3
const _V_DEHORS := 4

# Internal phase of the body. It never overrides the brain, it only says which
# pose builder owns the skeleton right now.
const _PHASE_IDLE := 0
const _PHASE_PREPARE := 1
const _PHASE_FLIGHT := 2
const _PHASE_CELEBRATE := 3
## Scrubbed by seek_replay(). While this phase is set the body no longer drives
## itself at all: the log is the only source of truth, so a leftover dive cannot
## fight the playhead.
const _PHASE_REPLAY := 4

## How far a limb may be pulled past its rest length before the solver gives up
## and lets the hand fall short. Real divers do stretch, a rigid chain reads as
## a mannequin, but past ~30 percent the mesh visibly tears away from the body.
const MAX_STRETCH := 1.30
## Sampling window used to differentiate line_dance() into a shuffle speed.
const DANCE_DT := 0.05

## --- the line dance, as STEPS ------------------------------------------------
##
## `KeeperBrain.line_dance` gives an x on the line and nothing else, and the body
## used to answer it by sliding: the whole figure translated sideways with both
## boots welded to the turf, which at eleven metres reads as a man on castors.
## The four numbers below turn that same x into footfalls. The step phase is
## integrated from the DISTANCE covered rather than from the clock, so the feet
## are locked to the movement the brain asked for: he cannot skate, and he cannot
## run on the spot either.
##
## Metres of line covered per full two step cycle.
const STEP_LENGTH := 0.46
## How high the swinging boot leaves the turf, metres.
const STEP_LIFT := 0.115
## How far ahead of the body the swinging boot lands, metres.
const STEP_REACH := 0.145
## Counter swing of the gloves against the feet, metres. The arms of a keeper on
## his line are never still, and this is what bends the two elbows out of phase.
const ARM_SWING := 0.075
## How far the hips drop into the set crouch at full readiness, metres. The boots
## stay on the turf, so every centimetre of this is knee flex.
const CROUCH_DEPTH := 0.135
## Time constant of the decay of the shuffle offset once the ball is struck. The
## brain's dive_pose() is expressed around the middle of the line, so the offset
## the keeper walked to has to bleed out, smoothly, early in the flight.
const LINE_BLEND := 0.16
## Beyond this the brain's dive is over. Sampling further would query it well
## outside the range it was designed for.
const DIVE_POSE_MAX := 1.60
## A dive that never leaves the ground still has to end, so the landing is
## reported at the latest at this point of the dive clock.
const LAND_TIME := 0.85
## Estimate error, in metres, under which the read is good enough to go now.
const CONFIDENT_ERROR := 0.16
## The target handed to KeeperBrain.dive_pose when nothing is being dived at:
## dead centre, chest high. At t = 0 the brain returns the standing pose whatever
## it is asked to dive at, so this only ever names the resting body.
const HOME_TARGET := Vector3(0.0, 1.25, 0.0)
## Safety added to the computed travel time when deciding the last responsible
## moment to commit. One physics step at 120 Hz is 8 ms, so this is generous.
const COMMIT_MARGIN := 0.03
## How far the keeper may fold at the waist, radians from the pelvis axis. A low
## block at his own feet needs a body doubled right over: the brain puts that
## glove a metre below the pelvis, and no arm reaches there from an upright
## chest. 1.75 rad is folded past horizontal, which is what that pose actually
## is, and it only ever engages when the arms alone cannot cover the distance.
const MAX_TORSO_BEND := 1.75
## How far a shoulder may be pushed out of its socket towards the hand, metres.
## A shoulder girdle really does protract several centimetres at full stretch,
## and the joint sits inside the chest volume, so this is free realism.
const SHOULDER_SLIDE := 0.07
## Seconds spent getting back on the feet at the start of a celebration.
const RECOVER := 0.45
## Seconds a keeper lying on the turf spends pushing himself back onto his feet
## once nobody is driving him any more. Longer than the 0.6 s a keeper who never
## went down needs, because getting up off the grass is three moves and standing
## up straight is one.
const GETUP_TIME := 1.15
## Distance from a GLOVE CENTRE to the BALL CENTRE when that glove is actually on
## the ball. One ball radius (0.11 m) plus about 5 cm of padded palm, which is
## also KeeperBrain.GLOVE_RADIUS, the radius the save test catches with: closer
## and the ball is drawn buried inside the fist, further and it hovers beside a
## hand that is no longer touching it.
##
## It used to be 0.12 and it was measured OUT OF THE MIDPOINT of the two gloves,
## which is not the same thing at all: with the hands 34 cm apart that put the
## ball 20.8 cm from both of them, so the two palms were each 5 cm short of the
## surface and a close up read as a ball stuck to the chest with the hands
## hovering beside it. See hold_point() for the geometry that fixes it.
const HOLD_OFFSET := 0.16
## Two gloves closer together than this are cradling the ball BETWEEN them, so it
## is held at their midpoint rather than off one of them.
const TWO_HAND_SPAN := 0.52
## Half the gap the two gloves are held at once the ball is WON and the body is
## free to shape itself around it (the clutch and the get up brace). Deliberately
## under HOLD_OFFSET: a pair of hands further apart than the ball is wide has no
## position left where both of them touch it, and hold_point() then has to leave
## the ball sitting between two palms that are not quite on it.
const CRADLE_HALF := HOLD_OFFSET * 0.90
## How far a glove seated on a held ball is allowed to sink into it, metres.
## A padded glove closing on a ball squashes both, and a hand drawn exactly
## tangent reads as a ball balanced on a fingertip rather than as a ball gripped.
## Kept small enough that tests/smoke_probe.gd still fails a real puncture: see
## its MITT_SLACK, which is the ceiling this has to stay under.
const GRIP_SINK := 0.004
## Impact speed, m/s, above which even a caught ball is announced with the hard
## glove slap rather than the soft gather. Purely audio.
const CATCH_LOUD_SPEED := 22.0
## Total length of a celebration before the pose is simply held.
const CELEBRATE_TIME := 2.60
## Hard ceiling on `pose_log`. At 120 Hz this is fifteen seconds of body, which
## is twice the flight timeout, so a shot can never grow the log without bound
## while still leaving room for the whole run up in front of the strike.
const POSE_LOG_MAX := 1800
## Physics steps without a seek_replay() call after which the body decides the
## replay is over and goes back to standing itself up. At 120 Hz this is a tenth
## of a second, which no rendered frame ever takes.
const REPLAY_HANDOVER := 12

## Which way a boot points, expressed in the body frame as forward and downward
## components. A real foot runs slightly downhill from the ankle, and the source
## figure is modelled that way, so treating a boot as level would tip a standing
## keeper back onto his heels. Only the direction is read.
const _TOE_FORWARD := 0.945
const _TOE_DROP := 0.325

## KeeperBrain.Level. Defaults to CONFIRME (1), same default as the settings.
var level: int = 1:
	set(value):
		var clamped := clampi(value, 0, 3)
		_level_explicit = true
		if clamped == level:
			return
		level = clamped
		_refresh_home()
## True from the frame the keeper commits until the frame he lands.
var diving: bool = false

## Pose log of the current attempt, oldest first, one entry per step. Each entry
## is a full pose dictionary ("centre", "glove_left", "glove_right", "boot_left",
## "boot_right", "lean", "airborne") plus "t", the seconds since the strike.
##
## `t` is NEGATIVE before the strike, and that is the point of the whole thing:
## recording starts when the run up starts, not at contact, so a keeper who
## gambled is caught leaving his line BEFORE the ball was even hit. That early
## commitment is the most interesting thing a replay can show.
##
## Recording runs to the END of the attempt and not to the end of the dive: the
## landing, the get up, the celebration and the wait after it are all in there.
## `Ball` logs its own tail the same way, and the two are read by ONE playhead,
## so a log that stopped earlier than the other is a replay that ends with one of
## the two frozen. See _log_tail().
##
## Parallel to Ball.flight_log, on the same clock, and read back by seek_replay().
## Cleared by reset_to_line(), which the orchestrator calls whenever it puts the
## ball back on the spot, so one attempt can never replay the previous dive.
var pose_log: Array[Dictionary] = []

# --- skeleton -----------------------------------------------------------------

## One rigid piece of the keeper. `rest` is the length the mesh actually has
## along its own Y axis, measured from its AABB, so the code never assumes how
## Meshes.humanoid_parts() chose to lay a part out: a segment is remapped onto
## [0, joint distance] and a blob is recentred on its own middle.
class _Bone extends RefCounted:
	var pivot: Node3D = null
	var mesh: MeshInstance3D = null
	var rest: float = 0.1
	var base_y: float = 0.0
	## True when the mesh has to be turned end for end to hang the right way up,
	## see _proximal_is_top().
	var flipped: bool = false

var _rig: Node3D = null
## The imported figure, when one is installed. Null is the normal, supported
## case: the procedural rig above is then the only thing on screen, and it is
## what every checkout without an `assets/` folder renders.
var _model: Node3D = null
var _b_pelvis: _Bone = null
var _b_torso: _Bone = null
var _b_head: _Bone = null
var _b_upper_l: _Bone = null
var _b_fore_l: _Bone = null
var _b_hand_l: _Bone = null
var _b_upper_r: _Bone = null
var _b_fore_r: _Bone = null
var _b_hand_r: _Bone = null
var _b_thigh_l: _Bone = null
var _b_shin_l: _Bone = null
var _b_foot_l: _Bone = null
var _b_thigh_r: _Bone = null
var _b_shin_r: _Bone = null
var _b_foot_r: _Bone = null

var _shoulder_half := 0.19
## Height of the shoulder line above the hips. This is NOT the whole torso: the
## neck carries on above the shoulders, and hanging the arms off the neck is
## both wrong to look at and 9 cm of reach thrown away.
var _shoulder_rise := 0.38
var _hip_half := 0.11
var _pelvis_lift := 0.02
var _head_lift := 0.16
## How far the DRAWN skull sits above the head joint, in this figure's own units.
## Zero on the procedural body, which has no enlarged head to lift.
var _head_rise := 0.0
var _hip_height := 0.95
var _centre_lift := 0.0
var _built := false
var _level_explicit := false

# --- state --------------------------------------------------------------------

var _pose: Dictionary = {}
var _home: Dictionary = {}
var _guess: Dictionary = {}
var _estimate: Dictionary = {}
var _end_pose: Dictionary = {}
## Pose held at the moment the orchestrator stopped driving a flight, so a keeper
## who never dived can unwind out of his crouch instead of freezing in it, and one
## who dived can push himself off the turf. Whether he is ON the turf is latched
## with it: reading it back per frame would flip the recovery to "standing" the
## instant the get up lifted the hips past the threshold.
var _relax_from: Dictionary = {}
var _grounded_from := false
var _phase := _PHASE_IDLE
var _rng_seed := 0
var _committed := false
var _dive_side := 0
var _dive_height := 1
## The world point on the goal line the dive is aimed at. This is what the pose is
## built from; `_dive_side` and `_dive_height` are only the coarse reading of it
## that the `dive_started` signal reports.
var _dive_target := HOME_TARGET
var _dive_gambled := false
var _dive_t := 0.0
var _dive_lead := 0.0
var _commit_elapsed := 0.0
var _was_airborne := false
var _landed_sent := false
var _saved_sent := false
## The glove holding the ball, "" when nothing was caught. Set by attempt_save,
## cleared by reset_to_line, and read by hold_point() and by the celebration.
var _hold_limb := ""
var _line_x := 0.0
var _line_x_frozen := 0.0
## --- when it is the PLAYER who holds this body (mode DUEL) --------------------
## While `_player_driven` is set, track() decides nothing: the dive arrives
## through commit_dive() and the line position through set_line(). EVERYTHING
## below the decision is untouched, and that is the point of the mode: the pose,
## the save envelope, the catch, the log and the replay are the same code on both
## sides of the duel.
var _player_driven := false
## Where the caller wants this body to stand on its line. `_line_target_set` is
## what makes prepare() follow it instead of KeeperBrain.line_dance, and it is
## deliberately independent of `_player_driven`: the player picks his spot during
## the placement, before the run up hands him the rest of the body.
var _line_target := 0.0
var _line_target_set := false
## Step cycle of the line dance, one full unit per two footfalls, and the prepare
## clock the last frame, which is how the phase is integrated from a caller that
## reports an absolute elapsed time rather than a delta.
var _step_phase := 0.0
var _prepare_t := 0.0
var _idle_t := 0.0
var _celebrate_t := 0.0
var _celebrate_verdict := _V_BUT
var _celebrate_x := 0.0
var _celebrate_grounded := false
var _look_at := Vector3(0.0, 1.0, 11.0)
## Physics frame of the last prepare()/track() call. _physics_process only takes
## the body over once the orchestrator has clearly stopped driving it, and a
## frame index does that exactly, where a wall clock would misfire on a stall.
## The two frame slack makes the handover immune to node processing order.
var _driven_frame := -100
## Glove side assignment, with hysteresis: the brain's "left" and "right" are
## trusted, but if a pose ever hands them over swapped the arms would cross, so
## the assignment is re checked and only flipped when it is clearly better.
var _gloves_swapped := false
var _boots_swapped := false
## Where the two hands were actually DRAWN this frame, per pose key, after the
## side assignment above and after the arm solve stopped short of a target it
## could not reach. hold_point() anchors on these; nothing else does.
var _drawn_glove_left := Vector3.ZERO
var _drawn_glove_right := Vector3.ZERO
var _drawn_valid := false
## Pose log bookkeeping. During the run up the entries are stamped with the raw
## run up clock, because nobody knows yet when contact will happen; the first
## track() call knows, and rebases the whole log onto the strike once.
var _log_active := false
var _log_rebased := false
## Set the first time seek_replay() reads the log back. Recording is over from
## there: the body is being driven BY the log, so anything appended after that
## would be a replayed pose written back on top of the recording it came from.
## Cleared only by reset_to_line().
var _log_sealed := false
var _log_strike_at := 0.0
var _log_t := 0.0
## Physics frame of the last seek_replay() call, see REPLAY_HANDOVER.
var _replay_frame := -1000

# --- lifecycle ----------------------------------------------------------------

func _ready() -> void:
	if not _built:
		build()
	reset_to_line()


## Builds the whole figure. Idempotent: calling it twice is a no op.
func build() -> void:
	if _built:
		return
	_built = true
	if not _level_explicit:
		var settings := _autoload("Game")
		if settings != null:
			var stored: Variant = settings.get("keeper_level")
			if typeof(stored) == TYPE_INT:
				_set_level_quietly(int(stored))
	_rig = Node3D.new()
	_rig.name = "Rig"
	add_child(_rig)
	var parts := _humanoid_parts()
	var jersey: Material = _material("jersey_main")
	var shorts: Material = _material("jersey_shorts")
	var skin: Material = _material("skin")
	var glove: Material = _material("glove")
	var boot: Material = _material("boot")
	var m_pelvis := _part(parts, "pelvis")
	var m_torso := _part(parts, "torso")
	var m_head := _part(parts, "head")
	var m_upper := _part(parts, "upper_arm")
	var m_fore := _part(parts, "fore_arm")
	var m_hand := _part(parts, "hand")
	var m_thigh := _part(parts, "thigh")
	var m_shin := _part(parts, "shin")
	var m_foot := _part(parts, "foot")
	_b_pelvis = _make_bone("Pelvis", m_pelvis, shorts, true)
	_b_torso = _make_bone("Torso", m_torso, jersey, false)
	_b_head = _make_bone("Head", m_head, skin, true)
	_b_upper_l = _make_bone("UpperArmL", m_upper, jersey, false)
	_b_fore_l = _make_bone("ForeArmL", m_fore, skin, false)
	_b_hand_l = _make_bone("HandL", m_hand, glove, true)
	_b_upper_r = _make_bone("UpperArmR", m_upper, jersey, false)
	_b_fore_r = _make_bone("ForeArmR", m_fore, skin, false)
	_b_hand_r = _make_bone("HandR", m_hand, glove, true)
	_b_thigh_l = _make_bone("ThighL", m_thigh, skin, false)
	_b_shin_l = _make_bone("ShinL", m_shin, shorts, false)
	_b_foot_l = _make_bone("FootL", m_foot, boot, true)
	_b_thigh_r = _make_bone("ThighR", m_thigh, skin, false)
	_b_shin_r = _make_bone("ShinR", m_shin, shorts, false)
	_b_foot_r = _make_bone("FootR", m_foot, boot, true)
	# Body measurements are read back from the meshes, never guessed, so a change
	# of proportions in Meshes.humanoid_parts() is picked up for free.
	_shoulder_half = maxf(m_torso.get_aabb().size.x * 0.46, 0.13)
	_shoulder_rise = _widest_offset(m_torso, m_torso.get_aabb())
	_hip_half = maxf(m_pelvis.get_aabb().size.x * 0.32, 0.08)
	# The spine starts near the top of the pelvis, with enough overlap that the
	# two volumes always intersect however the hips are rolled.
	_pelvis_lift = m_pelvis.get_aabb().size.y * 0.35
	_head_lift = 0.05 + _b_head.rest * 0.5
	_hip_height = maxf(_b_foot_l.rest * 0.3 + _b_shin_l.rest + _b_thigh_l.rest, 0.4)
	_adopt_model()
	_refresh_home()
	_apply_pose(_standing_pose_at(0.0))


## Puts the imported figure on, when one is installed.
##
## Two things happen here and the order matters. The figure is instanced, and
## every proportion of the solver above is then re-measured FROM it: segment
## lengths, shoulder line, hip line. That is the whole trick. The inverse
## kinematics keep running exactly as they always did, but on the model's own
## bones, so the elbow it computes is the elbow the model has and the glove it
## computes is where the model's glove lands. Skip this and the drawn glove
## drifts several centimetres away from the glove `attempt_save` tests, which is
## the one lie this module is not allowed to tell.
##
## No model installed is not an error. It is the coarser render the project was
## built to fall back to, and the procedural rig is left visible for it.
func _adopt_model() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_KEEPER):
		return
	var figure := CharacterModels.build(CharacterModels.ROLE_KEEPER)
	if figure == null:
		return
	var m := CharacterModels.metrics(CharacterModels.ROLE_KEEPER)
	if m.is_empty():
		figure.queue_free()
		return
	_model = figure
	_model.name = "Figure"
	add_child(_model)
	# The procedural body stays built and stays solved: it is the skeleton the
	# model is aimed down. It just stops being drawn.
	_rig.visible = false

	_shoulder_half = _metric(m, "shoulder_half", _shoulder_half)
	_shoulder_rise = _metric(m, "shoulder_rise", _shoulder_rise)
	_hip_half = _metric(m, "hip_half", _hip_half)
	_head_lift = _metric(m, "head_lift", _head_lift)
	# No scale factor here, unlike Shooter: the keeper is drawn at the model's own
	# size, so the metric already arrives in this figure's units.
	_head_rise = _metric(m, "head_rise", 0.0)
	_hip_height = _metric(m, "hip_height", _hip_height)
	# The figure is anchored on its HIP MIDPOINT, which is what the brain calls
	# the body centre, so there is no pelvis offset left to add on top.
	_pelvis_lift = 0.0
	_b_torso.rest = _metric(m, "torso", _b_torso.rest)
	_set_rest(_b_upper_l, _b_upper_r, _metric(m, "upper_arm", _b_upper_l.rest))
	_set_rest(_b_fore_l, _b_fore_r, _metric(m, "fore_arm", _b_fore_l.rest))
	_set_rest(_b_thigh_l, _b_thigh_r, _metric(m, "thigh", _b_thigh_l.rest))
	_set_rest(_b_shin_l, _b_shin_r, _metric(m, "shin", _b_shin_l.rest))
	# A blob's `rest` is its full length and the solver counts half of it as
	# reach, so the measured wrist to glove centre distance is doubled here.
	_set_rest(_b_hand_l, _b_hand_r, _metric(m, "hand_reach", _b_hand_l.rest * 0.5) * 2.0)
	_set_rest(_b_foot_l, _b_foot_r, _metric(m, "foot_reach", _b_foot_l.rest * 0.5) * 2.0)


func _set_rest(left: _Bone, right: _Bone, value: float) -> void:
	var safe := maxf(value, 0.02)
	if left != null:
		left.rest = safe
	if right != null:
		right.rest = safe


func _metric(source: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = source.get(key, null)
	var kind := typeof(value)
	if kind != TYPE_FLOAT and kind != TYPE_INT:
		return fallback
	var out := float(value)
	if not is_finite(out) or out <= 0.0:
		return fallback
	return out


## Back to the middle of the line, standing, ready for a new attempt.
func reset_to_line() -> void:
	# Every dive_started is answered by exactly one landed, even when the dive is
	# cut short by the next attempt: a listener pairing the two never hangs.
	_close_dive()
	_phase = _PHASE_IDLE
	_committed = false
	diving = false
	_dive_t = 0.0
	_dive_lead = 0.0
	_commit_elapsed = 0.0
	_dive_side = 0
	_dive_height = 1
	_dive_target = HOME_TARGET
	_dive_gambled = false
	_was_airborne = false
	_landed_sent = false
	_saved_sent = false
	_hold_limb = ""
	_line_x = 0.0
	_line_x_frozen = 0.0
	_player_driven = false
	_line_target = 0.0
	_line_target_set = false
	_step_phase = 0.0
	_prepare_t = 0.0
	_idle_t = 0.0
	_celebrate_t = 0.0
	_guess = {}
	_estimate = {}
	_end_pose = {}
	_relax_from = {}
	_grounded_from = false
	_gloves_swapped = false
	_boots_swapped = false
	_drawn_valid = false
	_clear_pose_log()
	_look_at = Vector3(0.0, 1.1, Field.SPOT_Z)
	_rng_seed = _draw_seed()
	_apply_pose(_standing_pose_at(0.0))


## Body language phase. `elapsed` is the time since the shooter took his mark.
## The shuffle along the line is the brain's line_dance(); everything else here
## is derived from it, including the weight shift, which is just the keeper
## leaning into his own sideways speed.
func prepare(elapsed: float) -> void:
	_driven_frame = Engine.get_physics_frames()
	_phase = _PHASE_PREPARE
	_relax_from = {}
	_look_at = Vector3(0.0, 1.15, Field.SPOT_Z)
	var t := maxf(elapsed, 0.0)
	# The step phase is integrated from the DISTANCE actually covered, not from the
	# clock: one cycle per STEP_LENGTH of line, so the feet never skate and never
	# run on the spot. `elapsed` restarts at zero on every phase change (placement,
	# aim, run up all drive prepare from their own clock), which the clamp turns
	# into a dt of zero rather than into a lurch.
	var dt := clampf(t - _prepare_t, 0.0, 0.2)
	_prepare_t = t

	# THE PLAYER HAS ALREADY GONE. A keeper who gambles leaves BEFORE contact, so
	# his dive starts here, in the middle of the taker's run up, and finishes in
	# track() after the strike. It is the same dive_pose sampled on the same clock;
	# only the moment it was decided is on this side of the ball.
	if _player_driven and _committed:
		_dive_t += dt
		_apply_dive_pose()
		_log_prepare(t)
		return

	var dance := 0.0
	var dance_speed := 0.0
	if _line_target_set:
		# Somebody outside is holding the line. He has already been rate limited
		# (KeeperInput.line_step), so this body does not limit him a second time:
		# it simply walks the distance he asked for, and the footfalls below are
		# integrated from that distance like any other.
		dance = clampf(_line_target, -1.1, 1.1)
		if dt > 0.0001:
			dance_speed = (dance - _line_x) / dt
	else:
		dance = KeeperBrain.line_dance(t, level, _rng_seed)
		var dance_back: float = KeeperBrain.line_dance(maxf(t - DANCE_DT, 0.0), level, _rng_seed)
		dance_speed = (dance - dance_back) / DANCE_DT
	_step_phase = fposmod(_step_phase + absf(dance_speed) * dt / STEP_LENGTH, 1.0)
	var readiness := clampf(t / 1.1, 0.0, 1.0)
	# A keeper who has already decided to gamble leans that way before the ball
	# is even struck. The bias is small: it is a tell the shooter can read back.
	# A player driven body never leans it: nothing has read anything for him, and
	# a lean he did not choose would be a tell about a decision he has not made.
	var bias := 0.0
	if not _player_driven and bool(_guess.get("commit", false)) \
			and _num(_guess, "commit_time", 0.0) < 0.0:
		bias = float(_int_of(_guess, "side", 0)) * 0.24 * readiness
	_line_x = clampf(dance + bias, -1.1, 1.1)
	_line_x_frozen = _line_x
	var base := _standing_pose_at(_line_x)
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	# How much of a STRIDE this is rather than a stand. Below a few centimetres a
	# second he is not walking, he is breathing, and the step cycle folds away
	# rather than shuffling the boots about on the spot.
	var stride := smoothstep(0.06, 0.55, absf(dance_speed))
	var travel := signf(dance_speed)
	var cyc := _step_phase * TAU
	var swing_l := maxf(sin(cyc), 0.0) * stride
	var swing_r := maxf(-sin(cyc), 0.0) * stride
	# The set crouch. Deeper than a stand by design: the hips drop towards the
	# boots, the two bone solve turns that into bent knees, and a bent knee is the
	# single thing that separates a goalkeeper from a man waiting for a bus.
	var crouch := 0.05 + CROUCH_DEPTH * readiness
	# Breathing, and a slow transfer of weight from one foot to the other. Both
	# fade as he sets, because a keeper about to face a penalty stops fidgeting.
	var idle := 1.0 - 0.55 * readiness
	var breath := sin(t * 2.1) * 0.011 * idle
	var shift := sin(t * 0.62) * (1.0 - stride)
	var bob := sin(t * 5.3) * 0.010 * idle
	# Hips rise between the steps and dip as each foot lands, twice per cycle.
	bob += sin(cyc * 2.0) * 0.017 * stride
	var sway := clampf(-dance_speed * 0.07, -0.19, 0.19) + shift * 0.055
	var out := 0.15 + 0.13 * readiness
	var fwd := 0.10 + 0.15 * readiness
	var lift := 0.03 + 0.06 * readiness
	centre.y += bob + breath - crouch
	var gl: Vector3 = _vec(base, "glove_left", centre) + Vector3(out, lift - crouch, fwd)
	var gr: Vector3 = _vec(base, "glove_right", centre) + Vector3(-out, lift - crouch, fwd)
	# The arms answer the feet. One glove rides up and forward while the other
	# drops and pulls back, which is a counter swing, and it is what puts a bend
	# in one elbow and takes it out of the other on every single step.
	var arm := (swing_l - swing_r) * ARM_SWING
	gl += Vector3(arm * 0.35, arm, arm * 0.65)
	gr -= Vector3(arm * 0.35, arm, arm * 0.65)
	gl.y += breath * 1.3
	gr.y += breath * 1.3
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	# A real side step: the trailing foot leaves the turf, swings across in the
	# direction of travel and lands, while the other one stays planted. Lifting a
	# boot towards a hip is also what folds that knee, so the step is where most
	# of the leg articulation on the line comes from.
	bl.y += swing_l * STEP_LIFT
	br.y += swing_r * STEP_LIFT
	bl.x += travel * swing_l * STEP_REACH
	br.x += travel * swing_r * STEP_REACH
	bl.z += swing_l * STEP_LIFT * 0.30
	br.z += swing_r * STEP_LIFT * 0.30
	# The stance widens as he sets, and the weight rocks between the two feet.
	bl.x += 0.05 * readiness - shift * 0.018
	br.x += -0.05 * readiness - shift * 0.018
	_apply_pose(_pose_dict(centre, gl, gr, bl, br, sway, 0.0))
	_log_prepare(t)


## Records one pre strike frame, on the RUN UP's own clock. Only the run up is
## worth keeping: prepare() also runs during the placement and the aim, and nobody
## wants ten seconds of a keeper standing still, so the log is only ever active
## between read_shooter()/set_player_driven() and the strike.
func _log_prepare(t: float) -> void:
	if not _log_active or _log_rebased:
		return
	_log_strike_at = maxf(t, 0.0)
	_append_pose_log(_log_strike_at)


## Feeds the brain the shooter's tells. Called once, at the start of the run up,
## and again after every feint, so this is also where the pose log starts: it is
## the earliest moment the body has anything worth replaying. A second call (a
## feint) must NOT restart it, or the recording would lose the approach.
func read_shooter(cues: Dictionary) -> void:
	_guess = KeeperBrain.read_cues(cues, level, _rng_seed)
	if typeof(_guess) != TYPE_DICTIONARY:
		_guess = {}
	_phase = _PHASE_PREPARE
	_relax_from = {}
	if not _log_active:
		_clear_pose_log()
		_log_active = true


## Called every physics step of the flight. Returns true on the single frame the
## keeper commits to a dive.
##
## Three things gate the decision. The reaction time, which the keeper may never
## cheat: he is blind for reaction_time(level) seconds after contact. The last
## responsible moment, which is the real algorithm here: he waits as long as the
## estimated travel time to the predicted crossing point allows, because every
## extra frame of watching sharpens the estimate. And confidence: once the
## brain's reported error is small enough, waiting buys nothing, so he goes.
##
## The fourth path bypasses all of it. If read_cues() came back committed with a
## negative commit_time, the keeper decided before the strike, so the dive is
## already `-commit_time` seconds old on the very first frame of the flight: the
## lead is pushed straight into the dive clock rather than faked with an offset.
func track(ball_position: Vector3, ball_velocity: Vector3, spin: Vector3, elapsed: float) -> bool:
	_driven_frame = Engine.get_physics_frames()
	_phase = _PHASE_FLIGHT
	_relax_from = {}
	_look_at = ball_position
	var t := maxf(elapsed, 0.0)
	# First frame of the flight: contact just happened, so the run up entries can
	# finally be put on the shot's own clock and turn negative.
	if not _log_rebased:
		_rebase_pose_log()

	# THE PLAYER DECIDES, OR HE HAS ALREADY DECIDED, OR HE NEVER WILL. Nothing in
	# this branch reads the ball: a human keeper gets no free frame of hindsight
	# just because the engine is happy to hand it to him. The dive clock is
	# ABSOLUTE (`t` minus the instant he pressed, which is negative when he went
	# early), so a dive that started in the run up carries straight through the
	# strike without a seam and without drifting off the frames prepare() ran.
	if _player_driven:
		if _committed:
			_dive_t = maxf(t - _commit_elapsed, 0.0)
			_apply_dive_pose()
		else:
			_apply_pose(_set_pose(t))
		_append_pose_log(t)
		return false

	var committed_now := false
	if not _committed:
		var lead := 0.0
		if bool(_guess.get("commit", false)):
			lead = maxf(-_num(_guess, "commit_time", 0.0), 0.0)
		var est: Dictionary = KeeperBrain.estimate_cross(
			ball_position, ball_velocity, spin, level, t, _rng_seed)
		if typeof(est) == TYPE_DICTIONARY:
			_estimate = est
		var may_move: bool = lead > 0.0 or t >= KeeperBrain.reaction_time(level)
		if may_move and _should_commit(_estimate, t, lead):
			_commit(_estimate, t, lead)
			committed_now = true
	if _committed:
		_dive_t = maxf(t - _commit_elapsed + _dive_lead, 0.0)
		_apply_dive_pose()
	else:
		_apply_pose(_set_pose(t))
	_append_pose_log(t)
	return committed_now


## Save test for one ball step. Emits `saved` on contact, at most once per shot
## so a deflection that grazes a second limb cannot be scored twice.
##
## The answer carries THREE extra keys on top of KeeperBrain.try_save, and they
## are what turns a verdict into a physical outcome:
##   "catch" true when the ball was gathered rather than pushed away,
##   "grip"  how comfortably (1 dead centre of the palm, 0 at the edge),
##   "hand"  which glove holds it, "" for a parry.
## They come straight from KeeperBrain.catch_quality, so the rule is unit tested
## and this file only reports it. A caller that ignores them still gets exactly
## the dictionary it used to get.
##
## Once a contact has been reported, every later call answers "no contact" for
## the rest of the attempt. The keeper is not a wall the loose ball can keep
## bouncing off: he touched it once, that is the save, and what happens next is
## the ball's business.
func attempt_save(ball_from: Vector3, ball_to: Vector3) -> Dictionary:
	var missed := {
		"saved": false, "limb": "", "point": ball_to, "normal": Vector3.BACK,
		"catch": false, "grip": 0.0, "hand": "",
	}
	if _saved_sent:
		return missed
	var result: Dictionary = KeeperBrain.try_save(_pose, ball_from, ball_to)
	if typeof(result) != TYPE_DICTIONARY:
		return missed
	if not bool(result.get("saved", false)):
		result["catch"] = false
		result["grip"] = 0.0
		result["hand"] = ""
		return result

	_saved_sent = true
	var limb := String(result.get("limb", ""))
	var point: Vector3 = _vec(result, "point", ball_to)
	var step_speed := (ball_to - ball_from).length() * float(maxi(Engine.physics_ticks_per_second, 1))
	var verdict: Dictionary = KeeperBrain.catch_quality(_pose, result, step_speed)
	var caught := bool(verdict.get("catch", false))
	result["catch"] = caught
	result["grip"] = float(verdict.get("grip", 0.0))
	result["hand"] = String(verdict.get("hand", ""))
	if caught:
		_hold_limb = String(verdict.get("hand", limb))
		# A gathered ball makes almost no noise, and a ball taken cleanly out of a
		# hard shot makes a lot: same catch, two different sounds.
		if step_speed > CATCH_LOUD_SPEED:
			_play_sfx("glove_catch", point, 1.0, randf_range(0.92, 0.99))
		else:
			_play_sfx("glove_catch", point, -2.0, randf_range(0.99, 1.06))
	elif limb.begins_with("glove"):
		_play_sfx("glove_punch", point, 0.0, randf_range(0.96, 1.05))
	else:
		# A boot or a chest block is a dull thud, not a glove slap.
		_play_sfx("ball_bounce", point, 1.0, randf_range(0.78, 0.88))
	saved.emit(limb, point)
	return result


## True while a caught ball is sitting in this keeper's hands.
func holding() -> bool:
	return not _hold_limb.is_empty()


## Where a caught ball sits right now, in world space, for the pose currently on
## screen. A held ball is drawn from this and nothing else, so it follows the
## hand through the rest of the dive, the landing and the celebration instead of
## being parented to a bone that the procedural fallback does not even have.
##
## THE BALL IS ALWAYS EXACTLY HOLD_OFFSET FROM THE GLOVE THAT TOOK IT. That is
## the whole function: it only ever chooses a DIRECTION out of that hand, never a
## distance, so the palm that caught it is on it in every frame of the dive, the
## landing and the celebration.
##
## The direction is a blend of two.
##  - THE CRADLE. When the second glove is within reach of the same ball there is
##    a direction that puts BOTH glove centres at HOLD_OFFSET: half the span
##    along the line joining them, then Pythagoras square to that line. A fixed
##    push out of the midpoint cannot do that, because the distance it lands at
##    is the HYPOTENUSE of the push and the half span: 12 cm out of a 34 cm pair
##    leaves the ball 20.8 cm from both hands, five centimetres short of contact
##    on each, and at close range that reads as a ball stuck to the chest with
##    the hands hovering beside it.
##  - THE ONE HANDED HOLD, out of the body and towards the shooter, because a
##    ball held against the chest is still held in FRONT of it.
##
## `wide` crossfades between them by how far the pair is from being able to close
## on the ball at all, so a keeper whose arms open through a dive never sees the
## ball jump from between his hands onto one of them.
func hold_point() -> Vector3:
	var centre: Vector3 = _vec(_pose, "centre", Field.KEEPER_HOME)
	if _hold_limb.is_empty():
		return centre
	var other_key := "glove_right" if _hold_limb == "glove_left" else "glove_left"
	var hand: Vector3 = _drawn_glove(_hold_limb, centre)
	var other: Vector3 = _drawn_glove(other_key, hand)
	var span := hand.distance_to(other)
	var half := span * 0.5
	var wide := clampf((span - HOLD_OFFSET * 2.0)
		/ maxf(TWO_HAND_SPAN - HOLD_OFFSET * 2.0, 0.01), 0.0, 1.0)
	var away := hand.lerp(other, 0.5).lerp(hand, wide) - centre
	if away.length_squared() < 0.000001:
		away = Vector3.BACK
	away = (away.normalized() * 0.6 + Vector3.BACK * 0.4).normalized()
	var axis := Vector3.ZERO
	if span > 0.000001:
		axis = (other - hand) / span
	var square := away - axis * away.dot(axis)
	if square.length_squared() < 0.000001:
		square = away
	else:
		square = square.normalized()
	var cradle := axis * half + square * sqrt(maxf(HOLD_OFFSET * HOLD_OFFSET - half * half, 0.0))
	var offset := cradle.lerp(away * HOLD_OFFSET, wide)
	if offset.length_squared() < 0.000001:
		offset = away * HOLD_OFFSET
	var wanted := hand + offset.normalized() * HOLD_OFFSET
	return _seat_on_glove(wanted, hand)


## Moves a wanted ball position onto the surface of the glove that is really
## DRAWN, and returns it unchanged when there is no drawn glove to sit on.
##
## HOLD_OFFSET measures out of the point the ARMS ARE SOLVED TO. That point is not
## the glove: on an imported figure the padded solid is centred behind it, runs
## well past it, and `CharacterModels.pose` is allowed to fall short of it on an
## over extended arm. The three add up. A close up of a clean catch showed the
## ball hanging in space with the glove seven centimetres away from it, while
## every distance this file computes was correct to the millimetre - they were
## just distances to a point nothing was drawn at.
##
## So the ball is seated on the SOLID instead. The direction is still the one
## chosen above, out of the body and towards the shooter or square between the two
## hands; only the distance is re-read, off the glove that is actually on screen.
## The glove is a flat PAD and its radius is read on all three of its axes. A
## spheroid that folds the width of the palm and its thickness into one number
## seats the ball on the thin side 33 mm off the leather, which is the gap this
## function exists to close and not a rounding.
func _seat_on_glove(wanted: Vector3, hand: Vector3) -> Vector3:
	var solid := _hold_solid(hand)
	if solid.is_empty():
		return wanted
	var centre: Vector3 = solid["centre"]
	var out := wanted - centre
	if out.length_squared() < 0.000001:
		out = wanted - _vec(_pose, "centre", Field.KEEPER_HOME)
	if out.length_squared() < 0.000001:
		return wanted
	# THE DIRECTION IS LEFT ALONE, and that was tried the other way round. Swinging
	# it square to the fingers so the ball lands on the PALM is the anatomically
	# right hold and it draws a worse picture: the seat that satisfies it on a
	# clutch pose is up against the chest, so the ball rose into the jersey and sat
	# on the upper edge of a glove pointing somewhere else. Putting the palm on the
	# ball needs the WRIST to roll, and rolling the glove alone twists it off the
	# arm it is attached to. Until the wrist can carry it, contact in the direction
	# the body already wanted is the honest half of the fix.
	var dir := out.normalized()
	var radius := _glove_radius(solid, dir)
	if radius <= 0.0:
		return wanted
	return centre + dir * maxf(radius + Field.BALL_RADIUS - GRIP_SINK, 0.001)


## Distance from the centre of a glove solid to its surface, in direction `dir`.
## The standard ellipsoid radius: the three axes are orthogonal, so the direction
## cosines against them are all that is needed.
func _glove_radius(solid: Dictionary, dir: Vector3) -> float:
	var total: float = 0.0
	for pair in [["axis", "along"], ["across", "half_across"], ["through", "half_through"]]:
		var semi: float = float(solid.get(pair[1], 0.0))
		if semi <= 0.0001:
			return 0.0
		var cosine: float = dir.dot(solid.get(pair[0], Vector3.ZERO))
		total += (cosine / semi) * (cosine / semi)
	if total <= 0.0:
		return 0.0
	return 1.0 / sqrt(total)


## Whichever of the two drawn gloves is nearer the hand that took the ball.
##
## Nearer, rather than the matching side, on purpose: this file already swaps its
## own gloves (`_gloves_swapped`) and the model has its own left and right, so a
## name carried across the two is one more mapping to keep in step. The two gloves
## are never close enough on a save for the nearest to be the wrong one.
func _hold_solid(hand: Vector3) -> Dictionary:
	if _model == null:
		return {}
	var best: Dictionary = {}
	var best_gap: float = 1.0e9
	for left in [true, false]:
		var solid := CharacterModels.mitt_solid(_model, left)
		if solid.is_empty():
			continue
		var gap: float = hand.distance_to(solid["centre"])
		if gap < best_gap:
			best_gap = gap
			best = solid
	return best


## The drawn position of one glove, or the pose's own value when the rig has not
## been solved yet (a keeper outside the tree, or a build without a body).
func _drawn_glove(key: String, fallback: Vector3) -> Vector3:
	if not _drawn_valid:
		return _vec(_pose, key, fallback)
	var point := _drawn_glove_left if key == "glove_left" else _drawn_glove_right
	if not point.is_finite():
		return _vec(_pose, key, fallback)
	return point


## Current pose dictionary, in world space. This is the exact data the meshes
## were placed from, and the exact data attempt_save() tests against.
func pose() -> Dictionary:
	return _pose.duplicate()


# --- when it is the PLAYER who holds this body (mode DUEL) ---------------------
#
# Three calls and a query, and between them they change exactly one thing: WHO
# picks the dive and WHEN. Everything under that decision is the code that was
# already here. The pose is KeeperBrain.dive_pose, the save volume is the same
# pose(), the catch is KeeperBrain.catch_quality, the log is the same log and the
# replay reads it the same way. A duel is symmetric because there is only one
# goalkeeper in this file and both sides borrow him.

## Hands this body to the player, or takes it back.
##
## Called TWICE on the way into a kept round, and the second call is not
## redundant: it is where the POSE LOG STARTS, exactly as read_shooter() starts it
## on the AI side. The first call (on the placement) opens the line to the player
## so he can pick his spot; the second (at the start of the run up) is the moment
## worth replaying, and recording anything earlier would splice two different
## clocks into one log and leave it out of order.
func set_player_driven(keeping: bool) -> void:
	_player_driven = keeping
	if not keeping:
		return
	# A player driven body reads nothing, so it must not carry a stale hunch: the
	# lean bias in prepare() and the fallback target in _commit_window both key on
	# this, and a leftover would have him tipping his weight towards a corner
	# nobody chose.
	_guess = {}
	_line_target_set = true
	_clear_pose_log()
	_log_active = true
	_prepare_t = 0.0


## Where this body stands on its line, in metres. It WALKS there, on the same
## footfalls the AI line dance uses, because a keeper who slides sideways with
## both boots welded to the turf looks worse than one who does nothing at all.
##
## Rate limiting belongs to the caller (KeeperInput.line_step): limiting it again
## here would put the drawn body behind the position every other module believes
## he occupies, and the reach envelope on screen would be drawn around a keeper
## who is not there.
func set_line(line_x: float) -> void:
	_line_target = clampf(line_x, -1.1, 1.1)
	_line_target_set = true


## Launches the dive the player just committed to. `dive` is the dictionary
## KeeperInput.commit returned, which carries the very keys KeeperBrain.choose_dive
## returns, so `dive_started`, the pose log and the replay never learn where the
## decision came from.
##
## A NO OP AFTER THE FIRST CALL OF AN ATTEMPT. A keeper commits once, on both
## sides of the duel, and there is no correction in flight for either of them:
## that is what keeps the top corner unreachable and it is not negotiable just
## because a human is holding the button.
##
## `committed_at` is the instant of the press on the SHOT's clock, negative during
## the run up, and it is stored as the dive's origin rather than "now": the dive
## has to be `-committed_at` seconds old at contact, which is the entire reward
## for going early.
func commit_dive(dive: Dictionary) -> void:
	if _committed or not _player_driven:
		return
	if typeof(dive) != TYPE_DICTIONARY or dive.is_empty():
		push_warning("Keeper: commit_dive sans plongeon exploitable, appel ignore.")
		return
	_dive_side = clampi(_int_of(dive, "side", 0), -1, 1)
	_dive_height = clampi(_int_of(dive, "height", 1), 0, 2)
	_dive_target = _vec(dive, "target", HOME_TARGET)
	var at := _num(dive, "committed_at", 0.0)
	if not is_finite(at):
		at = 0.0
	_commit_elapsed = at
	# "Gambled" means the same thing on both sides: decided before contact.
	_dive_gambled = at <= 0.0
	_dive_lead = 0.0
	_dive_t = 0.0
	_committed = true
	diving = true
	_was_airborne = false
	_landed_sent = false
	dive_started.emit(_dive_side, _dive_height, _dive_gambled)
	_play_sfx("keeper_grunt", _vec(_pose, "centre", Field.KEEPER_HOME), -3.0, randf_range(1.0, 1.12))


## True once this attempt's dive has been launched, whoever launched it.
func committed() -> bool:
	return _committed


## Reaction after the verdict. Procedural, short, and rebuilt every frame from
## the pose the keeper actually ended the dive in, so a keeper who ends up flat
## on the turf gets up from there instead of teleporting to a standing idle.
func celebrate(verdict: int) -> void:
	_end_pose = _pose.duplicate()
	_celebrate_verdict = verdict
	_celebrate_t = 0.0
	_phase = _PHASE_CELEBRATE
	# The verdict can land before the body does, and the celebration takes the
	# skeleton over, so the dive would otherwise never report its landing. The
	# signal is guaranteed to fire exactly once per dive, here at the latest.
	_close_dive()
	diving = false
	var centre: Vector3 = _vec(_end_pose, "centre", Field.KEEPER_HOME)
	_celebrate_x = clampf(centre.x, -2.4, 2.4)
	_celebrate_grounded = _is_grounded(_end_pose)
	if verdict == _V_ARRET:
		_play_sfx("keeper_grunt", centre, 1.0, randf_range(0.94, 1.02))
	elif verdict == _V_POTEAU or verdict == _V_BARRE or verdict == _V_DEHORS:
		_play_sfx("keeper_grunt", centre, -6.0, 0.82)


## Scrubs the body to the pose recorded `t` seconds after the strike.
##
## `t` is on the same clock as Ball.seek_replay, so driving both from one value
## keeps the dive and the ball in lockstep. Negative values are legal and show
## the pre strike commitment; past the end of the log the last pose is held.
##
## The two bracketing samples are INTERPOLATED rather than snapped to, because a
## replay is watched at 0.42x and at a slow motion crawl: a nearest sample lookup
## would step the keeper through the dive at 120 discrete poses per second, and
## on a slow scrub that reads as a stutter rather than as a body in the air.
##
## Does nothing when the log is empty, so a shot with nothing recorded simply
## leaves the keeper where he is instead of snapping him to a default pose.
func seek_replay(t: float) -> void:
	var count := pose_log.size()
	if count == 0:
		return
	# The playhead owns the skeleton from here: _physics_process must not carry an
	# unfinished dive on top of it, or the two would fight over the same bones.
	_phase = _PHASE_REPLAY
	_log_sealed = true
	_driven_frame = Engine.get_physics_frames()
	_replay_frame = _driven_frame
	var first: Dictionary = pose_log[0]
	if count == 1 or t <= _num(first, "t", 0.0):
		_apply_pose(_pose_of(first))
		return
	var last: Dictionary = pose_log[count - 1]
	if t >= _num(last, "t", 0.0):
		_apply_pose(_pose_of(last))
		return
	# Binary search rather than a scan: this runs every rendered frame against a
	# log that can hold well over a thousand entries.
	var low := 0
	var high := count - 1
	while high - low > 1:
		var mid := (low + high) / 2
		if _num(pose_log[mid], "t", 0.0) <= t:
			low = mid
		else:
			high = mid
	var before: Dictionary = pose_log[low]
	var after: Dictionary = pose_log[high]
	var t0 := _num(before, "t", 0.0)
	var t1 := _num(after, "t", t0)
	var w := 0.0
	if t1 - t0 > 0.000001:
		w = clampf((t - t0) / (t1 - t0), 0.0, 1.0)
	_apply_pose(_blend_pose(_pose_of(before), _pose_of(after), w))


# --- pose log -----------------------------------------------------------------

func _clear_pose_log() -> void:
	pose_log.clear()
	_log_active = false
	_log_rebased = false
	_log_sealed = false
	_log_strike_at = 0.0
	_log_t = 0.0


## Appends the pose currently on screen. What is logged is exactly what was
## drawn, same as pose(): a replay that showed a different body from the one that
## saved the ball would be a lie.
func _append_pose_log(t: float) -> void:
	if _log_sealed:
		return
	_log_active = true
	_log_t = t
	if pose_log.size() >= POSE_LOG_MAX:
		return
	var entry: Dictionary = _pose.duplicate()
	entry["t"] = t
	pose_log.append(entry)


## Moves the run up entries onto the shot's clock. They were stamped with the run
## up clock, which starts at zero at the start of the approach; the strike
## happened at `_log_strike_at` on that clock, so everything before it becomes
## negative and everything after keeps counting from contact.
func _rebase_pose_log() -> void:
	_log_rebased = true
	_log_active = true
	if _log_strike_at != 0.0:
		for entry in pose_log:
			entry["t"] = _num(entry, "t", 0.0) - _log_strike_at
	_log_t = 0.0


## A clean pose dictionary out of a log entry, without the "t" stamp.
func _pose_of(entry: Dictionary) -> Dictionary:
	return _shift_pose(entry, Vector3.ZERO)


# --- driving ------------------------------------------------------------------

func _physics_process(delta: float) -> void:
	if not _built:
		return
	var quiet := Engine.get_physics_frames() - _driven_frame >= 2
	if _phase == _PHASE_REPLAY:
		# seek_replay() owns the skeleton while it is being scrubbed, and it is
		# scrubbed from _process, so several physics steps can pass between two
		# calls: the idle handover only fires once the playhead has clearly gone
		# away. Without that slack the keeper would relax in the middle of his own
		# replay, every other frame.
		if Engine.get_physics_frames() - _replay_frame < REPLAY_HANDOVER:
			return
		# Nobody is scrubbing any more. Unwind out of the frozen pose the same way
		# a keeper who watched the ball go past does.
		_phase = _PHASE_FLIGHT
		_relax_from = {}
		return
	if _phase == _PHASE_CELEBRATE:
		_celebrate_t = minf(_celebrate_t + delta, CELEBRATE_TIME)
		_apply_pose(_celebration_pose(_celebrate_t))
		_log_tail(delta)
		return
	if not quiet:
		return
	if _committed and not _landed_sent:
		# The verdict landed before the body did. Carry the dive to its end so it
		# never freezes in mid air. This is still part of the shot, so it is still
		# recorded: the replay wants the landing, not a dive cut off in the air.
		_dive_t += delta
		_apply_dive_pose()
		_log_tail(delta)
		return
	if _phase == _PHASE_FLIGHT:
		# The attempt is over and nobody is driving him any more. He comes out of
		# the set position if he is still on his feet, and gets up off the turf if
		# he is not, instead of holding whatever shape the dive left him in.
		if _relax_from.is_empty():
			_relax_from = _pose.duplicate()
			_grounded_from = _is_grounded(_relax_from)
			_idle_t = 0.0
		_idle_t += delta
		_apply_pose(_recover_pose(_idle_t))
		_log_tail(delta)
		if _idle_t >= (GETUP_TIME if _grounded_from else 0.6):
			_phase = _PHASE_IDLE
			_relax_from = {}
			_grounded_from = false
		return
	if _phase == _PHASE_IDLE:
		_idle_t += delta
		_apply_pose(_idle_pose(_idle_t))
		_log_tail(delta)


## Keeps recording the body for the whole tail of the attempt: the landing, the
## get up, the celebration, the wait afterwards. Everything the strike started.
##
## THE TWO LOGS HAVE TO COVER THE SAME WINDOW, and this is the half of that
## promise the body owes. `Ball` carries on logging long after the keeper has
## stopped being driven - into the net, through the bounces, and for the whole
## hold when the ball was caught - while the body used to stop recording at the
## end of the dive, which `dive_pose` leaves at the top of a layout with the hips
## a metre and a half up. `seek_replay` then clamped to that last sample, so the
## tail of every goal replay was a man frozen in mid air with his shadow on the
## grass below him while the ball was still visibly moving.
##
## Cheap, too: POSE_LOG_MAX caps the whole thing at fifteen seconds of body, and
## `reset_to_line` throws it away at the start of the next attempt.
func _log_tail(delta: float) -> void:
	if not _log_active or not _log_rebased:
		return
	_append_pose_log(_log_t + delta)


## Reports the end of a dive, once, whoever noticed it first.
func _close_dive() -> void:
	if not _committed or _landed_sent:
		return
	_landed_sent = true
	diving = false
	landed.emit()


## The two numbers the commit decision turns on: how much flight the ball has
## left, and how long this keeper still needs to have a glove on the point he
## would dive at. Both are HIS OWN estimates, never the truth, and the dive he
## would choose right now comes back with them so the caller does not solve it
## twice.
##
## `time` in the estimate is the flight still to run, per the contract of 2.12, so
## it is used as it stands. Subtracting `elapsed` from it, as this used to, counted
## the watched part of the flight twice and made him leave early on every shot he
## had been watching for a while.
func _commit_window(est: Dictionary, elapsed: float) -> Dictionary:
	var time_left := 0.0
	if not est.is_empty():
		time_left = maxf(_num(est, "time", 0.0), 0.0)
	var dive: Dictionary = KeeperBrain.choose_dive(est, _guess, level, elapsed)
	if typeof(dive) != TYPE_DICTIONARY:
		dive = {}
	var target: Vector3 = _vec(dive, "target", HOME_TARGET)
	var here: Vector3 = _vec(_pose, "centre", Field.KEEPER_HOME)
	return {
		"time_left": time_left,
		"need": KeeperBrain.dive_time_needed(target, here.x, level),
		"dive": dive,
	}


## The last responsible moment, and the one place the pre strike gamble is turned
## into physics rather than into an order.
##
## A keeper who decided during the run up that he is going right has NOT decided
## to be on the turf 0.2 s before contact. He has decided to allow himself that
## much of a head start IF the ball needs it. So the gamble does not short circuit
## the decision any more, it widens it by `lead`: he leaves when the flight left is
## down to what the dive costs him, plus his head start, and not a frame sooner.
##
## That is the whole fix for the flat save rate on scuffed penalties. A ball
## mishit to 12 m/s is on the line in 0.9 s, so a keeper who threw himself
## sideways at contact was finished, face down, a quarter of a second before it
## arrived, whatever his level. Now he waits, and the extra 0.3 s of watching is
## exactly where his perception ladder finally gets to do some work.
func _should_commit(est: Dictionary, elapsed: float, lead: float) -> bool:
	var window := _commit_window(est, elapsed)
	var time_left := float(window["time_left"])
	var need := float(window["need"])
	if time_left <= need + lead + COMMIT_MARGIN:
		return true
	if lead > 0.0:
		# He is going, but late is free and late is better: every frame he holds
		# sharpens the estimate he is going to dive on.
		return false
	return _num(est, "error", 9.0) <= CONFIDENT_ERROR


func _commit(est: Dictionary, elapsed: float, lead: float) -> void:
	var window := _commit_window(est, elapsed)
	var dive: Dictionary = window["dive"]
	_dive_side = clampi(_int_of(dive, "side", 0), -1, 1)
	_dive_height = clampi(_int_of(dive, "height", 1), 0, 2)
	_dive_target = _vec(dive, "target", HOME_TARGET)
	_dive_gambled = lead > 0.0
	_commit_elapsed = elapsed
	# How much of the head start the flight actually called for. A hard penalty
	# leaves in 0.41 s and a full length dive costs more than that, so he spends
	# the lot; a scuffed one gives him all the time he needs, so he spends none of
	# it and simply pushes off at the right moment. It is never MORE than he
	# decided to allow himself during the run up.
	_dive_lead = clampf(float(window["need"]) + lead - float(window["time_left"]), 0.0, lead)
	_dive_t = _dive_lead
	_committed = true
	diving = true
	_was_airborne = false
	_landed_sent = false
	dive_started.emit(_dive_side, _dive_height, _dive_gambled)
	_play_sfx("keeper_grunt", _vec(_pose, "centre", Field.KEEPER_HOME), -3.0, randf_range(1.0, 1.12))


func _apply_dive_pose() -> void:
	var sampled: Dictionary = KeeperBrain.dive_pose(
		_dive_target, minf(_dive_t, DIVE_POSE_MAX), level)
	if typeof(sampled) != TYPE_DICTIONARY or sampled.is_empty():
		return
	var shift := Vector3(_line_x_frozen * exp(-_dive_t / LINE_BLEND), 0.0, 0.0)
	var built := _shift_pose(sampled, shift)
	_apply_pose(built)
	var air := _num(built, "airborne", 0.0)
	if air > 0.3:
		_was_airborne = true
	var down := (_was_airborne and air <= 0.05) or _dive_t >= LAND_TIME
	if down and not _landed_sent:
		_play_sfx("keeper_land", _vec(built, "centre", Field.KEEPER_HOME), -2.0, randf_range(0.92, 1.06))
		_close_dive()


## The coiled pose held between the strike and the commit: still shuffling out of
## the last step, weight forward, gloves up, eyes on the ball.
func _set_pose(elapsed: float) -> Dictionary:
	var shift := _line_x_frozen * exp(-elapsed / LINE_BLEND)
	var base := _standing_pose_at(shift)
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	centre.y -= 0.13
	centre.z += 0.05
	var gl: Vector3 = _vec(base, "glove_left", centre) + Vector3(0.30, -0.02, 0.26)
	var gr: Vector3 = _vec(base, "glove_right", centre) + Vector3(-0.30, -0.02, 0.26)
	var bl: Vector3 = _vec(base, "boot_left", centre) + Vector3(0.05, 0.0, -0.02)
	var br: Vector3 = _vec(base, "boot_right", centre) + Vector3(-0.05, 0.0, -0.02)
	return _pose_dict(centre, gl, gr, bl, br, 0.0, 0.0)


## Standing idle: a breath, and a slow transfer of weight from one foot to the
## other. Only ever used when nothing else drives the body.
##
## The weight shift is not decoration. The hips come down onto whichever leg is
## carrying, and the other heel lifts, so at any instant ONE knee is bent and one
## is not, and the pair swap over about every six seconds. A figure standing dead
## level on two straight legs is the thing that makes a game look unfinished.
func _idle_pose(t: float) -> Dictionary:
	var base := _standing_pose_at(_line_x)
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var breath := sin(t * 1.7) * 0.012
	var shift := sin(t * 0.53)
	var settle := 0.038 + 0.022 * absf(shift)
	centre.y += breath - settle
	centre.x += shift * 0.022
	var gl: Vector3 = _vec(base, "glove_left", centre) \
		+ Vector3(0.03 + shift * 0.014, breath * 1.4 - settle + shift * 0.032, 0.03)
	var gr: Vector3 = _vec(base, "glove_right", centre) \
		+ Vector3(-0.03 + shift * 0.014, breath * 1.4 - settle - shift * 0.032, 0.03)
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	bl.x += 0.030
	br.x -= 0.030
	# The unloaded heel comes off the turf, which is where that leg's knee and
	# ankle get their bend from.
	bl.y += maxf(-shift, 0.0) * 0.020
	br.y += maxf(shift, 0.0) * 0.020
	return _pose_dict(centre, gl, gr, bl, br, sin(t * 0.8) * 0.02 + shift * 0.045, 0.0)


## Getting back up, `t` seconds after the body stopped being driven.
##
## Two situations, one function, because they are the same situation with more or
## less horizontal in it: a keeper who stayed on his feet simply comes out of his
## crouch, a keeper lying flat has to PUSH first. `_relax_from` is whatever pose
## the attempt ended in, so he always gets up from where he actually is.
func _recover_pose(t: float) -> Dictionary:
	if _relax_from.is_empty():
		return _idle_pose(t)
	if not _grounded_from:
		return _blend_pose(_relax_from, _idle_pose(t), _smooth(clampf(t / 0.6, 0.0, 1.0)))
	# Down. Plant a hand, drive the hips up over a folded knee, then stand: the
	# two beats overlap, which is what stops it reading as two separate moves.
	var push := _smooth(clampf(t / (GETUP_TIME * 0.45), 0.0, 1.0))
	var rise := _smooth(clampf((t - GETUP_TIME * 0.38) / (GETUP_TIME * 0.62), 0.0, 1.0))
	var braced := _blend_pose(_relax_from, _brace_pose(_relax_from), push)
	return _blend_pose(braced, _idle_pose(t), rise)


## The pose a keeper passes through on his way off the turf: the down side glove
## planted on the grass under the shoulder, the far arm pushing, the hips lifted
## over a folded near knee and the trailing leg swept underneath.
##
## A keeper who CAUGHT the ball never plants the hand holding it, for the obvious
## reason: `hold_point` follows the drawn glove, so planting it would drive the
## ball into the turf. He brings both hands to his chest instead, which is what
## anybody does with a ball they have just won.
func _brace_pose(from: Dictionary) -> Dictionary:
	var centre: Vector3 = _vec(from, "centre", Field.KEEPER_HOME)
	var lean := _num(from, "lean", 0.0)
	var side := 1.0 if lean >= 0.0 else -1.0
	var ground := minf(_vec(from, "boot_left", centre).y, _vec(from, "boot_right", centre).y)
	var hips := Vector3(centre.x, maxf(_hip_height * 0.54, ground + 0.30), centre.z)
	var gl := hips + Vector3(0.30 * side, ground - hips.y + 0.07, 0.30)
	var gr := hips + Vector3(-0.24 * side, 0.12, 0.18)
	if holding():
		var rise: float = _b_torso.rest * 0.45 if _b_torso != null else 0.25
		var chest := hips + Vector3(0.0, rise, 0.20)
		gl = chest + Vector3(CRADLE_HALF, 0.0, 0.02)
		gr = chest + Vector3(-CRADLE_HALF, 0.0, 0.02)
	var bl := Vector3(hips.x + 0.20 * side, ground, hips.z - 0.14)
	var br := Vector3(hips.x - 0.17 * side, ground, hips.z + 0.19)
	return _pose_dict(hips, gl, gr, bl, br, lean * 0.45, 0.0)


## True when a pose has the body on the grass rather than on its feet.
func _is_grounded(source: Dictionary) -> bool:
	return _vec(source, "centre", Field.KEEPER_HOME).y < _hip_height * 0.75 \
		or absf(_num(source, "lean", 0.0)) > 0.7


func _smooth(w: float) -> float:
	var k := clampf(w, 0.0, 1.0)
	return k * k * (3.0 - 2.0 * k)


# --- celebration --------------------------------------------------------------

func _celebration_pose(t: float) -> Dictionary:
	var base := _standing_pose_at(_celebrate_x)
	var target := {}
	if _celebrate_verdict == _V_ARRET:
		# A keeper holding the ball does not pump his fists at the crowd, he gets
		# up clutching it. The hold point is read off the pose every frame, so
		# this is also what keeps the ball in his hands through the recovery.
		target = _pose_clutch(base, t) if holding() else _pose_fists(base, t)
	elif _celebrate_verdict == _V_BUT:
		if _celebrate_grounded:
			var up_again := clampf(1.0 - maxf(t - 1.2, 0.0) / 0.9, 0.0, 1.0)
			target = _blend_pose(_pose_hips(base, t), _pose_turf(base, t), up_again)
		else:
			target = _pose_hips(base, t)
	elif _celebrate_verdict == _V_POTEAU or _celebrate_verdict == _V_BARRE:
		target = _pose_head_hold(base, t)
	else:
		target = _pose_hips(base, t)
	if _end_pose.is_empty():
		return target
	# The recovery is longer when he has to get off the grass first: a keeper flat
	# on his side does not snap upright into a fist pump in a fifth of a second.
	var span := (GETUP_TIME * 0.75) if _celebrate_grounded else RECOVER
	var start := _end_pose
	if _celebrate_grounded:
		# Through the brace, same three beat push as `_recover_pose`, so a save and
		# a goal both end the dive by actually getting up rather than by rising.
		start = _blend_pose(_end_pose, _brace_pose(_end_pose),
			_smooth(clampf(t / (span * 0.5), 0.0, 1.0)))
	return _blend_pose(start, target, _smooth(clampf(t / span, 0.0, 1.0)))


## Both fists pumped at the crowd, with a hop on each pump. The two arms are
## deliberately a beat out of phase and the knees ride the hop, so the shoulders,
## the elbows and the knees are all doing something: a symmetrical celebration
## with straight legs reads as a scarecrow in a breeze.
func _pose_fists(base: Dictionary, t: float) -> Dictionary:
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var decay := exp(-t * 0.9)
	var beat := clampf(t - 0.15, 0.0, 2.2) * TAU * 1.05
	var pump := (0.5 - 0.5 * cos(beat)) * decay
	var offbeat := (0.5 - 0.5 * cos(beat - 0.55)) * decay
	var shoulder := _b_torso.rest if _b_torso != null else 0.55
	var hop := maxf(pump, offbeat)
	centre.y += 0.05 * hop - 0.045 * (1.0 - hop)
	var gl := centre + Vector3(0.30 + 0.05 * pump, shoulder * 0.65 + 0.42 * pump, 0.18)
	var gr := centre + Vector3(-0.30 - 0.05 * offbeat, shoulder * 0.65 + 0.42 * offbeat, 0.18)
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	bl.y += 0.07 * pump
	br.y += 0.07 * offbeat
	bl.x += 0.05
	br.x -= 0.05
	return _pose_dict(centre, gl, gr, bl, br,
		sin(t * 3.1) * 0.05 * decay + (pump - offbeat) * 0.06, 0.14 * hop)


## The ball hugged to the chest, both gloves on it, one small shake of the fists
## once he is back on his feet. This is the pose a caught penalty ends in, and
## the two gloves are deliberately inside TWO_HAND_SPAN of each other so that
## hold_point() cradles the ball between them.
func _pose_clutch(base: Dictionary, t: float) -> Dictionary:
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var shoulder := _b_torso.rest if _b_torso != null else 0.55
	# A single settling shake, then he simply stands there holding it.
	var shake := sin(clampf(t - RECOVER, 0.0, 1.4) * TAU * 0.85) * exp(-maxf(t - RECOVER, 0.0) * 1.6)
	var chest := centre + Vector3(0.0, shoulder * 0.52 + 0.02 * shake, 0.20)
	var gl := chest + Vector3(CRADLE_HALF, 0.0, 0.02)
	var gr := chest + Vector3(-CRADLE_HALF, 0.0, 0.02)
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	return _pose_dict(centre, gl, gr, bl, br, sin(t * 1.5) * 0.03, 0.0)


## Hands on hips, chest down: the resigned look after conceding.
func _pose_hips(base: Dictionary, t: float) -> Dictionary:
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var sag := 0.04 * clampf(t, 0.0, 1.0)
	centre.y -= sag
	var gl := centre + Vector3(0.32, 0.03, -0.03)
	var gr := centre + Vector3(-0.32, 0.03, -0.03)
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	return _pose_dict(centre, gl, gr, bl, br, sin(t * 1.3) * 0.03, 0.0)


## Down on the turf, one palm flat on the grass, head low.
func _pose_turf(base: Dictionary, t: float) -> Dictionary:
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var kneel := _hip_height * 0.44
	centre.y = kneel
	centre.z += 0.06
	var side := signf(_celebrate_x) if absf(_celebrate_x) > 0.05 else 1.0
	var gl := centre + Vector3(0.34 * side, -kneel + 0.05, 0.34)
	var gr := centre + Vector3(-0.22 * side, 0.06, 0.10)
	var ground := _vec(base, "boot_left", centre).y
	var bl := Vector3(centre.x + 0.20, ground, centre.z - 0.10)
	var br := Vector3(centre.x - 0.20, ground, centre.z + 0.16)
	return _pose_dict(centre, gl, gr, bl, br, 0.12 * side + sin(t * 1.1) * 0.02, 0.0)


## Both hands on the head: the near miss.
func _pose_head_hold(base: Dictionary, t: float) -> Dictionary:
	var centre: Vector3 = _vec(base, "centre", Field.KEEPER_HOME)
	var shoulder := _b_torso.rest if _b_torso != null else 0.55
	# `_head_rise` and not a bigger constant: the drawn skull is no longer centred
	# on the head joint, it is scaled about its own jaw and therefore sits that
	# much higher (CharacterModels `_NECK_SHOW`). Hands written against the joint
	# alone land on the mouth, which reads as a man covering his face rather than
	# a man holding his head. Same correction Shooter already applies.
	var crown := shoulder + _head_lift * 0.9 + _head_rise
	var gl := centre + Vector3(0.19, crown, 0.04)
	var gr := centre + Vector3(-0.19, crown, 0.04)
	var bl: Vector3 = _vec(base, "boot_left", centre)
	var br: Vector3 = _vec(base, "boot_right", centre)
	return _pose_dict(centre, gl, gr, bl, br, sin(t * 1.9) * 0.04, 0.0)


# --- pose plumbing ------------------------------------------------------------

func _refresh_home() -> void:
	var home: Dictionary = KeeperBrain.dive_pose(HOME_TARGET, 0.0, level)
	if typeof(home) != TYPE_DICTIONARY or home.is_empty():
		push_warning("Keeper: KeeperBrain.dive_pose returned no standing pose, using a fallback.")
		home = _fallback_home()
	_home = home.duplicate()
	# Safety net for a centre expressed at ground level rather than at the hips.
	# It is applied to the drawing only, never to the pose used for saves, so it
	# can never move the save volume away from what the brain intended.
	var hc: Vector3 = _vec(_home, "centre", Field.KEEPER_HOME)
	_centre_lift = 0.0
	if hc.y < 0.35:
		_centre_lift = _hip_height - hc.y


func _fallback_home() -> Dictionary:
	var base := Field.KEEPER_HOME
	var centre := Vector3(base.x, _hip_height, base.z)
	return _pose_dict(
		centre,
		centre + Vector3(0.34, 0.12, 0.10),
		centre + Vector3(-0.34, 0.12, 0.10),
		Vector3(base.x + 0.16, 0.06, base.z),
		Vector3(base.x - 0.16, 0.06, base.z),
		0.0, 0.0)


## The brain's own standing pose, slid sideways to `x` on the line.
func _standing_pose_at(x: float) -> Dictionary:
	if _home.is_empty():
		_refresh_home()
	var home_x := _vec(_home, "centre", Field.KEEPER_HOME).x
	return _shift_pose(_home, Vector3(x - home_x, 0.0, 0.0))


func _shift_pose(source: Dictionary, shift: Vector3) -> Dictionary:
	var centre: Vector3 = _vec(source, "centre", Field.KEEPER_HOME) + shift
	return _pose_dict(
		centre,
		_vec(source, "glove_left", centre) + shift,
		_vec(source, "glove_right", centre) + shift,
		_vec(source, "boot_left", centre) + shift,
		_vec(source, "boot_right", centre) + shift,
		_num(source, "lean", 0.0),
		_num(source, "airborne", 0.0))


func _blend_pose(a: Dictionary, b: Dictionary, w: float) -> Dictionary:
	var k := clampf(w, 0.0, 1.0)
	var ca: Vector3 = _vec(a, "centre", Field.KEEPER_HOME)
	var cb: Vector3 = _vec(b, "centre", Field.KEEPER_HOME)
	return _pose_dict(
		ca.lerp(cb, k),
		_vec(a, "glove_left", ca).lerp(_vec(b, "glove_left", cb), k),
		_vec(a, "glove_right", ca).lerp(_vec(b, "glove_right", cb), k),
		_vec(a, "boot_left", ca).lerp(_vec(b, "boot_left", cb), k),
		_vec(a, "boot_right", ca).lerp(_vec(b, "boot_right", cb), k),
		lerpf(_num(a, "lean", 0.0), _num(b, "lean", 0.0), k),
		lerpf(_num(a, "airborne", 0.0), _num(b, "airborne", 0.0), k))


func _pose_dict(centre: Vector3, gl: Vector3, gr: Vector3, bl: Vector3, br: Vector3,
		lean: float, airborne: float) -> Dictionary:
	return {
		"centre": centre,
		"glove_left": gl,
		"glove_right": gr,
		"boot_left": bl,
		"boot_right": br,
		"lean": lean,
		"airborne": airborne,
	}


func _apply_pose(new_pose: Dictionary) -> void:
	_pose = new_pose
	_update_rig()


# --- skeleton solve -----------------------------------------------------------

func _update_rig() -> void:
	if _b_pelvis == null or not is_inside_tree():
		return
	var centre: Vector3 = _vec(_pose, "centre", Field.KEEPER_HOME) + Vector3(0.0, _centre_lift, 0.0)
	var gl: Vector3 = _vec(_pose, "glove_left", centre)
	var gr: Vector3 = _vec(_pose, "glove_right", centre)
	var bl: Vector3 = _vec(_pose, "boot_left", centre)
	var br: Vector3 = _vec(_pose, "boot_right", centre)
	var lean := _num(_pose, "lean", 0.0)
	# The body up axis is measured from the pose itself: feet to hips is the
	# spine, whatever the body is doing. That is sign convention proof, and in a
	# dive (head leading, legs trailing) it is exactly the axis the body rolls
	# around. The declared `lean` is blended in so a flat dive still shows a
	# rolled chest even when the legs happen to line up with the torso.
	var foot_mid := (bl + br) * 0.5
	var spine := centre - foot_mid
	var up_pose := Vector3.UP
	if spine.length() > 0.25:
		up_pose = spine.normalized()
	# The roll axis is Vector3.FORWARD and not Vector3.BACK: the brain reports a
	# positive `lean` for a dive towards +X, so the head has to tip towards +X,
	# and a right handed rotation of UP about -Z is what does that. Get this
	# backwards and the two terms of the blend fight each other.
	var up := (up_pose * 0.7 + Vector3.UP.rotated(Vector3.FORWARD, lean) * 0.3)
	if up.length_squared() < 0.0001:
		up = Vector3.UP
	up = up.normalized()
	var right := Vector3.BACK.cross(up)
	if right.length_squared() < 0.0001:
		right = Vector3.LEFT
	right = right.normalized()
	var face := up.cross(right).normalized()
	var left := -right
	var body_basis := Basis(up.cross(face), up, face)
	var hip_mid := centre + up * _pelvis_lift
	_place_blob(_b_pelvis, centre, body_basis)

	# The chest gets its own axis. The pelvis is where the brain put it and the
	# legs answer to that, but a waist bends, and here it has to: on a low block
	# the brain puts the gloves a metre BELOW the pelvis, which no arm reaches
	# from an upright chest. Two passes of "bend only as far as the arms still
	# fall short" close the gap without ever bending a body already comfortable.
	var chest_up := up
	var glove_mid := (gl + gr) * 0.5
	var arm_span := (_b_upper_l.rest + _b_fore_l.rest + _b_hand_l.rest * 0.5) * MAX_STRETCH * 0.98
	for _pass in 2:
		var short_by := (hip_mid + chest_up * _shoulder_rise).distance_to(glove_mid) - arm_span
		if short_by <= 0.001:
			break
		var want := glove_mid - hip_mid
		if want.length() < 0.05:
			break
		var want_dir := want.normalized()
		var bend_axis := chest_up.cross(want_dir)
		if bend_axis.length_squared() < 0.000001:
			break
		# Arc over radius: how far the shoulder line must swing to close the gap,
		# capped by how far a waist actually goes.
		var swing := minf(chest_up.angle_to(want_dir), short_by / maxf(_shoulder_rise, 0.05))
		swing = minf(swing, maxf(MAX_TORSO_BEND - up.angle_to(chest_up), 0.0))
		if swing <= 0.0001:
			break
		chest_up = chest_up.rotated(bend_axis.normalized(), swing).normalized()
	var chest_right := Vector3.BACK.cross(chest_up)
	if chest_right.length_squared() < 0.0001:
		chest_right = right
	chest_right = chest_right.normalized()
	var chest_face := chest_up.cross(chest_right).normalized()
	var chest_left := -chest_right

	var shoulder_mid := hip_mid + chest_up * _shoulder_rise
	# Side assignment with hysteresis, so the arms can never end up crossed. It is
	# taken on the SQUARE shoulder line, before the twist below turns it, so the
	# articulation can never talk the solver into swapping an arm mid dive.
	_gloves_swapped = _pick_sides(shoulder_mid + chest_left * _shoulder_half,
		shoulder_mid + chest_right * _shoulder_half, gl, gr, _gloves_swapped)
	var glove_left := gr if _gloves_swapped else gl
	var glove_right := gl if _gloves_swapped else gr

	# --- articulation, see the block comment above `_arm_pole` --------------------
	var ext_l := _reach_ratio(shoulder_mid, glove_left, arm_span)
	var ext_r := _reach_ratio(shoulder_mid, glove_right, arm_span)
	# The chest TURNS INTO the leading arm. A keeper who throws a glove at a post
	# without turning his chest after it is a mannequin on a hinge, and the twist
	# is what puts the far shoulder behind him where a diver's actually goes.
	var twist := clampf((ext_l - ext_r) * CHEST_TWIST, -CHEST_TWIST, CHEST_TWIST)
	if absf(twist) > 0.0005:
		chest_right = chest_right.rotated(chest_up, -twist).normalized()
		chest_face = chest_up.cross(chest_right).normalized()
		chest_left = -chest_right
	# ... and the shoulder line ROLLS, the reaching shoulder rising or dropping
	# towards its own glove. That roll is most of what a spectator reads as "he
	# stretched": the arm alone only gets longer, the shoulder is what leans.
	var roll := clampf(
		_shoulder_lift(shoulder_mid, glove_left, chest_up, ext_l)
		- _shoulder_lift(shoulder_mid, glove_right, chest_up, ext_r),
		-1.0, 1.0) * _shoulder_half * SHOULDER_ROLL

	var neck := hip_mid + chest_up * _b_torso.rest
	var head_centre := neck + chest_up * _head_lift
	_place_segment(_b_torso, hip_mid, neck, chest_face)
	_place_blob(_b_head, head_centre, _head_basis(head_centre, chest_up, chest_face))

	var sh_l := shoulder_mid + chest_left * _shoulder_half + chest_up * roll
	var sh_r := shoulder_mid + chest_right * _shoulder_half - chest_up * roll
	sh_l = _protract(sh_l, glove_left, arm_span)
	sh_r = _protract(sh_r, glove_right, arm_span)
	var arm_l := _solve_chain(sh_l, glove_left,
		_arm_pole(sh_l, glove_left, chest_up, chest_face, chest_left, arm_span),
		_b_upper_l, _b_fore_l, _b_hand_l, chest_up)
	var arm_r := _solve_chain(sh_r, glove_right,
		_arm_pole(sh_r, glove_right, chest_up, chest_face, chest_right, arm_span),
		_b_upper_r, _b_fore_r, _b_hand_r, chest_up)
	# Where the gloves REALLY ended up. At full stretch the solver stops the hand
	# short of the point the brain asked for (see MAX_STRETCH), so the two differ
	# by up to a quarter of a metre on exactly the dives a save happens on. A ball
	# held on the brain's point would hang in the air past the fingertips, which
	# is precisely what a screenshot showed, so the hold is anchored on the drawn
	# hand instead. Only the drawing is affected: the save volume is still the
	# brain's, and this file never moves it.
	if _gloves_swapped:
		_drawn_glove_left = arm_r["end"]
		_drawn_glove_right = arm_l["end"]
	else:
		_drawn_glove_left = arm_l["end"]
		_drawn_glove_right = arm_r["end"]
	_drawn_valid = true

	var hip_l := hip_mid + left * _hip_half
	var hip_r := hip_mid + right * _hip_half
	_boots_swapped = _pick_sides(hip_l, hip_r, bl, br, _boots_swapped)
	var boot_left := br if _boots_swapped else bl
	var boot_right := bl if _boots_swapped else br
	# Knees bulge forwards, which is what stops the legs bending like a bird's, and
	# they splay out as they fold, which is what a crouch and a push off both do.
	var leg_span := _b_thigh_l.rest + _b_shin_l.rest + _b_foot_l.rest * 0.5
	var leg_l := _solve_chain(hip_l, boot_left,
		_leg_pole(hip_l, boot_left, up, face, left, leg_span),
		_b_thigh_l, _b_shin_l, _b_foot_l, up, face)
	var leg_r := _solve_chain(hip_r, boot_right,
		_leg_pole(hip_r, boot_right, up, face, right, leg_span),
		_b_thigh_r, _b_shin_r, _b_foot_r, up, face)

	if _model == null:
		return
	# The imported figure is aimed down the chains that were just solved, never
	# down a second solve of its own: same shoulders, same elbows, same gloves.
	# The rest lengths those chains were solved with were measured off the model
	# in _adopt_model, so it reaches the same points the meshes above reach.
	#
	# The feet need one correction. The solver treats a boot as a blob hung on the
	# end of the shin line, which is fine for a capsule and wrong for a foot: a
	# real ankle sits ABOVE and BEHIND the middle of the boot, never in line with
	# it. So the ankle handed over is walked BACK from the boot along the foot's
	# own direction, and the toes are then aimed straight at the boot the brain
	# asked for. The boot lands exactly where the save test believes it is, and
	# the ankle ends up where an ankle belongs.
	var foot_dir := (face * _TOE_FORWARD - up * _TOE_DROP).normalized()
	var foot_reach := _b_foot_l.rest * 0.5
	var boot_l: Vector3 = leg_l["end"]
	var boot_r: Vector3 = leg_r["end"]
	CharacterModels.pose(_model, {
		"hips": hip_mid,
		"body": Basis(up.cross(face), up, face),
		"chest": Basis(chest_up.cross(chest_face), chest_up, chest_face),
		"head": _head_basis(head_centre, chest_up, chest_face),
		"shoulder_l": sh_l,
		"elbow_l": arm_l["joint"],
		"wrist_l": arm_l["wrist"],
		"glove_l": arm_l["end"],
		"shoulder_r": sh_r,
		"elbow_r": arm_r["joint"],
		"wrist_r": arm_r["wrist"],
		"glove_r": arm_r["end"],
		"hip_l": hip_l,
		"knee_l": leg_l["joint"],
		"ankle_l": boot_l - foot_dir * foot_reach,
		"toe_l": boot_l,
		"hip_r": hip_r,
		"knee_r": leg_r["joint"],
		"ankle_r": boot_r - foot_dir * foot_reach,
		"toe_r": boot_r,
	})


# --- procedural articulation --------------------------------------------------
#
# THE POSE SAYS WHERE THE GLOVES AND THE BOOTS ARE. It says nothing at all about
# the shoulders, the elbows and the knees, and until this block existed the two
# bone solve bent all six of them in ONE fixed plane, for every pose in the game:
# elbows always back and down, knees always dead ahead. The body moved and the
# joints did not, which is exactly what reads as a puppet dragged by its hands.
#
# Everything below decides those three joints, and it decides them from THE POSE
# ITSELF and from nothing else. No clock, no phase flag, no stored state. Two
# properties follow, and both of them are the reason it is written this way.
#
#  1. THE REPLAY ARTICULATES. `seek_replay` interpolates two logged poses and
#     hands the result to `_apply_pose`, so a pure function of that result gives
#     a scrubbed body the same shoulders, elbows and knees as the live one, at
#     any speed, forwards, backwards, and through the slow motion dip.
#  2. IT CANNOT CHANGE A SAVE. `attempt_save` tests `_pose`, which nothing here
#     touches, and the analytic solve's END POINT is a function of the root, the
#     target and the two segment lengths alone: a pole vector picks the PLANE the
#     joint bends in and cannot move the end of the chain by a millimetre. Every
#     number in this block moves an elbow or a knee. None can move a glove.
#
# The one exception to (2) is deliberate and bounded: the twist and the roll move
# the SHOULDERS, so an arm that was already at full stretch can end up a few
# centimetres shorter or longer than it was. It is bounded by `SHOULDER_ROLL`
# times the shoulder half width, the drawn hand is what `hold_point` anchors on,
# and the save volume is still the brain's untouched pose.

## How far the chest turns towards the leading arm, radians. Positive is the
## LEFT shoulder coming forward, which is what the left arm reaching means.
const CHEST_TWIST := 0.34
## How far the shoulder line rolls, as a fraction of the shoulder half width.
## 0.40 of 19 cm is about 7.5 cm of shoulder travel at a full one armed stretch.
const SHOULDER_ROLL := 0.40
## Height under which an elbow or a knee is close enough to the turf that the
## joint is pushed up out of it, metres, and how hard it is pushed.
const GROUND_GUARD := 0.55
const GROUND_PUSH := 0.85


## How far out of its socket an arm or a leg is reaching, 0 folded to 1 straight.
## Clamped a little past 1: a stretched limb is still a straight limb.
func _reach_ratio(root: Vector3, target: Vector3, span: float) -> float:
	return clampf(root.distance_to(target) / maxf(span, 0.05), 0.0, 1.2)


## Which way, and how hard, one shoulder is being pulled by its own glove. +1 is
## a glove straight overhead at full stretch, -1 one at his boots.
func _shoulder_lift(shoulder_mid: Vector3, glove: Vector3, chest_up: Vector3, ext: float) -> float:
	var to_glove := glove - shoulder_mid
	if to_glove.length_squared() < 0.000001:
		return 0.0
	return clampf(to_glove.normalized().dot(chest_up), -1.0, 1.0) * clampf(ext, 0.0, 1.0)


## Where the ELBOW goes, as a pole vector for the two bone solve.
##
## Three terms, in the order a shoulder actually uses them:
##
##  - the elbow lives BEHIND the arm, and further behind the straighter the arm
##    is. That is the term that makes the glove ARRIVE LAST: while the brain's
##    extension curve is still winding the hand out, the elbow is swinging from
##    tucked to trailing, so the forearm unfolds late instead of the whole arm
##    travelling out rigid;
##  - a folded arm puts its elbow OUT and DOWN, which is the keeper's set shape
##    and also how he carries a caught ball into his chest;
##  - and no elbow is ever driven through the turf. A keeper flat on his side has
##    his shoulder 30 cm off the grass, and the pole is lifted towards world up
##    by however close to the ground the pair is, so the arm folds over the top
##    of the body rather than under it.
func _arm_pole(shoulder: Vector3, glove: Vector3, chest_up: Vector3, chest_face: Vector3,
		chest_side: Vector3, span: float) -> Vector3:
	var ext := _reach_ratio(shoulder, glove, span)
	var tuck := 1.0 - smoothstep(0.30, 0.96, ext)
	var pole := -chest_face * (0.55 + 0.50 * minf(ext, 1.0)) \
		+ chest_side * (0.18 + 0.90 * tuck) \
		- chest_up * (0.12 + 0.55 * tuck)
	var low := clampf((GROUND_GUARD - minf(shoulder.y, glove.y)) / GROUND_GUARD, 0.0, 1.0)
	if low > 0.0:
		pole += Vector3.UP * (GROUND_PUSH * low)
	return pole


## Where the KNEE goes. Same idea as `_arm_pole` and the same guarantee.
##
## A straight leg has its knee dead ahead, and the more it folds the further the
## knee splays outwards: that is a crouch, that is the load of a push off, and it
## is the difference between a keeper coiled on his line and one standing to
## attention. The world up term keeps a trailing leg's knee out of the grass on a
## full length dive for the same reason the arm has one.
func _leg_pole(hip: Vector3, boot: Vector3, up: Vector3, face: Vector3,
		side: Vector3, span: float) -> Vector3:
	var ext := _reach_ratio(hip, boot, span)
	var fold := 1.0 - smoothstep(0.55, 0.99, ext)
	var pole := face * (0.55 + 0.45 * minf(ext, 1.0)) \
		+ side * (0.10 + 0.70 * fold) \
		+ up * 0.06
	var low := clampf((GROUND_GUARD - minf(hip.y, boot.y)) / GROUND_GUARD, 0.0, 1.0)
	if low > 0.0:
		pole += Vector3.UP * (GROUND_PUSH * 0.6 * low)
	return pole


## Last few centimetres of reach: at full stretch the shoulder itself travels
## towards the hand. Only ever used when the arm is already out of length, so a
## relaxed pose keeps its shoulders exactly where the chest put them.
func _protract(shoulder: Vector3, target: Vector3, span: float) -> Vector3:
	var to_target := target - shoulder
	var over := to_target.length() - span
	if over <= 0.0 or to_target.length_squared() < 0.000001:
		return shoulder
	return shoulder + to_target.normalized() * minf(over, SHOULDER_SLIDE)


## Two bone analytic IK plus the end blob (a glove or a boot).
##
## By default the blob is aimed along the second bone, which is what a glove is:
## a mitt carrying on past the wrist. A boot is not. Meshes authors it upright,
## sole under +Y and toes towards -Z, so passing `end_dir` switches the blob to
## an upright placement in the body frame with its toes pointing that way. Aim a
## boot like a limb and the keeper stands on his heels with his toes in the air.
##
## Returns the three world points it solved, {"joint", "wrist", "end"}, so an
## imported figure can be aimed down the very same chain. Handing the model the
## solve rather than a second one of its own is what keeps the drawn glove and
## the saving glove the same object.
func _solve_chain(root: Vector3, target: Vector3, pole: Vector3, b1: _Bone, b2: _Bone,
		blob: _Bone, roll: Vector3, end_dir: Vector3 = Vector3.ZERO) -> Dictionary:
	var l1 := b1.rest
	# The target is the CENTRE of the glove or boot, not the wrist or the ankle,
	# because that is what the brain's save radii are measured from. Half of the
	# blob therefore counts as reach in the solve, and the wrist is placed back
	# along the solved forearm afterwards.
	var l2 := b2.rest + blob.rest * 0.5
	var solved := _solve_two_bone(root, target, l1, l2, pole)
	var joint: Vector3 = solved["joint"]
	var end_point: Vector3 = solved["end"]
	var stretch: float = solved["stretch"]
	var fore := end_point - joint
	if fore.length_squared() < 0.000001:
		fore = (target - root)
	if fore.length_squared() < 0.000001:
		fore = -roll
	var fore_dir := fore.normalized()
	var wrist := joint + fore_dir * (b2.rest * stretch)
	_place_segment(b1, root, joint, pole)
	_place_segment(b2, joint, wrist, pole)
	var blob_basis := _orient(fore_dir, roll)
	if end_dir.length_squared() > 0.000001:
		blob_basis = _upright_basis(roll, end_dir)
	_place_blob(blob, end_point, blob_basis)
	return {"joint": joint, "wrist": wrist, "end": end_point}


## Law of cosines. Returns {"joint", "end", "stretch"}.
## `pole` only fixes the plane the joint bends in: its component along the root
## to target axis is removed, so any vector roughly on the correct side works.
func _solve_two_bone(root: Vector3, target: Vector3, l1: float, l2: float, pole: Vector3) -> Dictionary:
	var to_target := target - root
	var dist := to_target.length()
	var dir := Vector3.DOWN
	if dist > 0.000001:
		dir = to_target / dist
	var rest_reach := maxf(l1 + l2, 0.001)
	var stretch := 1.0
	if dist > rest_reach:
		stretch = minf(dist / rest_reach, MAX_STRETCH)
	var a := l1 * stretch
	var b := l2 * stretch
	var reach := a + b
	var end_point := target
	if dist > reach:
		end_point = root + dir * reach
		dist = reach
	var folded := absf(a - b) + 0.002
	if dist < folded:
		dist = folded
		end_point = root + dir * folded
	var cos_theta := clampf((dist * dist + a * a - b * b) / (2.0 * a * maxf(dist, 0.000001)), -1.0, 1.0)
	var sin_theta := sqrt(maxf(1.0 - cos_theta * cos_theta, 0.0))
	var side_dir := pole - dir * pole.dot(dir)
	if side_dir.length_squared() < 0.000001:
		side_dir = Vector3.BACK - dir * Vector3.BACK.dot(dir)
	if side_dir.length_squared() < 0.000001:
		side_dir = Vector3.RIGHT - dir * Vector3.RIGHT.dot(dir)
	side_dir = side_dir.normalized()
	var joint := root + dir * (a * cos_theta) + side_dir * (a * sin_theta)
	return {"joint": joint, "end": end_point, "stretch": stretch}


## Keeps the shortest of the two possible side assignments, and only flips when
## the other one is better by a clear margin, so nothing pops mid dive. The
## brain's own left and right are trusted by default; this only catches a pose
## that would otherwise draw the keeper with his arms crossed over his chest.
func _pick_sides(anchor_l: Vector3, anchor_r: Vector3, target_l: Vector3, target_r: Vector3,
		current: bool) -> bool:
	var straight := anchor_l.distance_to(target_l) + anchor_r.distance_to(target_r)
	var crossed := anchor_l.distance_to(target_r) + anchor_r.distance_to(target_l)
	if current:
		return not (straight + 0.30 < crossed)
	return crossed + 0.30 < straight


func _head_basis(head_centre: Vector3, up: Vector3, face: Vector3) -> Basis:
	var look := _look_at - head_centre
	if look.length() < 0.6:
		return Basis(up.cross(face), up, face)
	var wanted := (face * 0.5 + look.normalized() * 0.5)
	if wanted.length_squared() < 0.0001:
		return Basis(up.cross(face), up, face)
	var side := wanted.normalized().cross(up)
	if side.length_squared() < 0.0001:
		return Basis(up.cross(face), up, face)
	side = side.normalized()
	var forward := up.cross(side).normalized()
	return Basis(up.cross(forward), up, forward)


## Places a bone so its mesh spans exactly from `from` to `to`, whatever the
## mesh's own layout along Y. The stretch is applied to the mesh only, which is
## a leaf, so a non uniform scale can never shear a rotated child.
func _place_segment(bone: _Bone, from: Vector3, to: Vector3, roll: Vector3) -> void:
	if bone == null or bone.pivot == null:
		return
	var delta := to - from
	var seg_len := delta.length()
	if seg_len < 0.0005:
		delta = Vector3.UP * 0.001
		seg_len = 0.001
	bone.pivot.global_transform = Transform3D(_orient(delta / seg_len, roll), from)
	var s := seg_len / maxf(bone.rest, 0.0001)
	if bone.flipped:
		# Turned end for end with a real half turn about X rather than a negative
		# Y scale: a mirrored basis would invert the winding and the part would
		# render inside out.
		var turned := Basis(Vector3(1.0, 0.0, 0.0), Vector3(0.0, -1.0, 0.0), Vector3(0.0, 0.0, -1.0))
		bone.mesh.transform = Transform3D(
			turned * Basis.from_scale(Vector3(1.0, s, 1.0)),
			Vector3(0.0, seg_len + bone.base_y * s, 0.0))
		return
	bone.mesh.transform = Transform3D(
		Basis.from_scale(Vector3(1.0, s, 1.0)),
		Vector3(0.0, -bone.base_y * s, 0.0))


func _place_blob(bone: _Bone, at: Vector3, b: Basis) -> void:
	if bone == null or bone.pivot == null:
		return
	bone.pivot.global_transform = Transform3D(b, at)


## Orthonormal basis standing on `up_axis` and facing `forward`, for parts that
## are authored the way a body wears them rather than along a bone. Godot models
## look down -Z, hence the sign: the mesh's own -Z ends up along `forward`.
func _upright_basis(up_axis: Vector3, forward: Vector3) -> Basis:
	var y := up_axis
	if y.length_squared() < 0.000001:
		y = Vector3.UP
	y = y.normalized()
	var f := forward - y * forward.dot(y)
	if f.length_squared() < 0.000001:
		f = Vector3.BACK - y * Vector3.BACK.dot(y)
	if f.length_squared() < 0.000001:
		f = Vector3.RIGHT - y * Vector3.RIGHT.dot(y)
	var z := -f.normalized()
	return Basis(y.cross(z), y, z)


## Orthonormal basis whose +Y is `dir_y` and whose +Z leans towards `roll`.
func _orient(dir_y: Vector3, roll: Vector3) -> Basis:
	var y := dir_y
	if y.length_squared() < 0.000001:
		y = Vector3.UP
	y = y.normalized()
	var z := roll - y * roll.dot(y)
	if z.length_squared() < 0.000001:
		z = Vector3.BACK - y * Vector3.BACK.dot(y)
	if z.length_squared() < 0.000001:
		z = Vector3.RIGHT - y * Vector3.RIGHT.dot(y)
	z = z.normalized()
	return Basis(y.cross(z), y, z)


# --- construction helpers -----------------------------------------------------

func _make_bone(bone_name: String, mesh: Mesh, mat: Material, is_blob: bool) -> _Bone:
	var bone := _Bone.new()
	bone.pivot = Node3D.new()
	bone.pivot.name = bone_name
	_rig.add_child(bone.pivot)
	bone.mesh = MeshInstance3D.new()
	bone.mesh.name = bone_name + "Mesh"
	bone.mesh.mesh = mesh
	if mat != null:
		bone.mesh.material_override = mat
	bone.mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	bone.pivot.add_child(bone.mesh)
	var box := mesh.get_aabb()
	bone.base_y = box.position.y
	bone.rest = maxf(box.size.y, 0.02)
	if not is_blob:
		bone.flipped = _proximal_is_top(mesh, box)
	if is_blob:
		# A blob is recentred on its own middle once and for all: only its pivot
		# ever moves afterwards.
		bone.mesh.transform = Transform3D(Basis.IDENTITY, -box.get_center())
	return bone


## Height above the base of the widest slice of a mesh. On the torso that is the
## shoulder line, which is where arms belong: the neck carries on above it, and
## hanging the arms off the top of the mesh both looks wrong and throws away
## nearly 10 cm of reach on every dive.
func _widest_offset(mesh: Mesh, box: AABB) -> float:
	var faces := mesh.get_faces()
	var fallback := box.size.y * 0.8
	if faces.is_empty() or box.size.y < 0.001:
		return fallback
	var slices := 12
	var total := PackedFloat32Array()
	var count := PackedInt32Array()
	total.resize(slices)
	count.resize(slices)
	var axis_x := box.get_center().x
	var axis_z := box.get_center().z
	for v in faces:
		var idx := clampi(int((v.y - box.position.y) / box.size.y * float(slices)), 0, slices - 1)
		total[idx] += Vector2(v.x - axis_x, v.z - axis_z).length()
		count[idx] += 1
	var best := -1.0
	var best_y := fallback
	for i in slices:
		if count[i] == 0:
			continue
		var mean := total[i] / float(count[i])
		if mean > best:
			best = mean
			best_y = (float(i) + 0.5) / float(slices) * box.size.y
	return best_y


## Which end of a segment mesh should be pinned to the joint it hangs from.
##
## Limbs taper: a thigh is thick at the hip and thin at the knee, a torso is
## broad at the hips and narrow at the neck. Meshes.limb() lays its parts out
## with the wide end at +Y (a limb hanging down from its joint) while the torso
## is laid out hips first at -Y, so a fixed rule would get one of the two wrong
## and the keeper would end up with pin shoulders and balloon elbows. Measuring
## the two end radii picks the right end every time, and keeps working if the
## mesh library ever changes its mind.
func _proximal_is_top(mesh: Mesh, box: AABB) -> bool:
	var faces := mesh.get_faces()
	if faces.is_empty() or box.size.y < 0.001:
		return false
	var band := box.size.y * 0.08
	var low_r := 0.0
	var low_n := 0
	var high_r := 0.0
	var high_n := 0
	var axis_x := box.get_center().x
	var axis_z := box.get_center().z
	for v in faces:
		var radius := Vector2(v.x - axis_x, v.z - axis_z).length()
		if v.y <= box.position.y + band:
			low_r += radius
			low_n += 1
		elif v.y >= box.position.y + box.size.y - band:
			high_r += radius
			high_n += 1
	if low_n == 0 or high_n == 0:
		return false
	return (high_r / float(high_n)) > (low_r / float(low_n)) * 1.05


func _humanoid_parts() -> Dictionary:
	var parts: Dictionary = Meshes.humanoid_parts()
	if typeof(parts) != TYPE_DICTIONARY:
		push_warning("Keeper: Meshes.humanoid_parts did not return a dictionary.")
		return {}
	return parts


## A part of the figure, with a primitive stand in if the library is missing one.
## The keeper is the readable silhouette of the whole game: he has to render even
## if a part goes missing, and a missing mesh must be loud, not invisible.
func _part(parts: Dictionary, key: String) -> Mesh:
	var value: Variant = parts.get(key, null)
	if value is Mesh:
		var mesh: Mesh = value
		if mesh.get_surface_count() > 0 and mesh.get_aabb().size.length() > 0.001:
			return mesh
	push_warning("Keeper: humanoid part '%s' is missing, using a primitive." % key)
	return _fallback_part(key)


func _fallback_part(key: String) -> Mesh:
	match key:
		"pelvis":
			return _prim_box(Vector3(0.34, 0.22, 0.22))
		"torso":
			return _prim_capsule(0.17, 0.56)
		"head":
			return _prim_capsule(0.105, 0.24)
		"upper_arm":
			return _prim_capsule(0.055, 0.31)
		"fore_arm":
			return _prim_capsule(0.048, 0.28)
		"hand":
			return _prim_box(Vector3(0.13, 0.20, 0.07))
		"thigh":
			return _prim_capsule(0.082, 0.46)
		"shin":
			return _prim_capsule(0.062, 0.44)
		"foot":
			return _prim_box(Vector3(0.10, 0.26, 0.08))
	return _prim_capsule(0.06, 0.2)


func _prim_capsule(radius: float, total_height: float) -> Mesh:
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = maxf(total_height, radius * 2.05)
	mesh.radial_segments = 12
	mesh.rings = 4
	return mesh


func _prim_box(size: Vector3) -> Mesh:
	var mesh := BoxMesh.new()
	mesh.size = size
	return mesh


func _material(kind: String) -> Material:
	match kind:
		"jersey_main":
			return Mats.jersey(Palette.KEEPER_JERSEY)
		"jersey_shorts":
			return Mats.jersey(Palette.KEEPER_SHORTS)
		"skin":
			return Mats.skin()
		"glove":
			return Mats.glove()
		"boot":
			return Mats.boot()
	return null


# --- small utilities ----------------------------------------------------------

func _set_level_quietly(value: int) -> void:
	var was := _level_explicit
	level = value
	_level_explicit = was


## The autoloads cannot be named by identifier here: this file has to keep
## parsing under `--check-only --script`, where autoloads are not registered.
## Looking them up by node name costs one dictionary probe and is null safe.
func _autoload(singleton_name: String) -> Node:
	if not is_inside_tree():
		return null
	var tree := get_tree()
	if tree == null or tree.root == null:
		return null
	return tree.root.get_node_or_null(NodePath(singleton_name))


func _play_sfx(id: String, at: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var bank := _autoload("Sfx")
	if bank == null:
		return
	bank.call("play_at", id, at, volume_db, pitch)


## One seed per attempt, drawn from the campaign seed and the round index, so a
## replay of the same attempt shuffles, reads and dives exactly the same way.
func _draw_seed() -> int:
	var base := 12345
	var settings := _autoload("Game")
	if settings != null:
		var stored: Variant = settings.get("seed_value")
		if typeof(stored) == TYPE_INT:
			base = int(stored)
	var round_index := 0
	var series := _autoload("Shootout")
	if series != null:
		var stored_round: Variant = series.get("round_index")
		if typeof(stored_round) == TYPE_INT:
			round_index = int(stored_round)
	return absi(base * 7919 + round_index * 104729 + level * 131)


func _vec(source: Dictionary, key: String, fallback: Vector3) -> Vector3:
	var value: Variant = source.get(key, null)
	if typeof(value) == TYPE_VECTOR3:
		var out: Vector3 = value
		return out
	return fallback


func _num(source: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = source.get(key, null)
	var kind := typeof(value)
	if kind == TYPE_FLOAT or kind == TYPE_INT:
		return float(value)
	return fallback


func _int_of(source: Dictionary, key: String, fallback: int) -> int:
	var value: Variant = source.get(key, null)
	var kind := typeof(value)
	if kind == TYPE_INT or kind == TYPE_FLOAT:
		return int(value)
	return fallback
