## GOAL - the penalty taker: his body, his run up, and every bit of shot input.
##
## Why this module is built the way it is.
##
## 1. One gesture carries the whole skill of the game. Holding `strike` fills a
##    power bar over about 1.15 s while a precision marker sweeps back and forth
##    across that same bar more than twice as fast. Releasing captures BOTH the
##    power reached and the marker position, and those two numbers fight each
##    other: holding longer buys speed but forces the player to let go of a
##    marker that is moving faster and faster. The release point is what
##    `ShotModel.contact_quality` turns into a clean strike or a miscue. How fast
##    that marker sweeps is the `sweep_level` setting, the second difficulty axis
##    of the game next to the keeper's level: see `SWEEP_SCALES`.
##
## 2. The run up is not decoration. It is 0.75 s of body language, and it is the
##    only thing the keeper is allowed to read before the ball moves (see
##    `cues()`). The values reported there are measured off the real animation
##    state, never invented: the run angle, the approach speed, the plant foot
##    offset and the hip yaw are exactly what the body is doing. `feint` is the
##    player's tool to lie about them. A feint slows the approach to a crawl for
##    a third of a second, so it also delays contact: it costs time, which is a
##    real trade rather than a free scramble.
##
## 3. The body is a procedural humanoid driven by joint angles. Every segment
##    length is measured from the meshes handed back by `Meshes.humanoid_parts()`
##    at build time, and every mesh is aligned by its own AABB, so the rig stays
##    correct whatever convention those meshes use (centred or based at the
##    origin). `boot_position()` reads the real ankle node rather than a
##    hardcoded guess, which is why the contact effect lands on the ball.
##
## 4. Autoloads are reached through `get_node_or_null("/root/Game")` instead of
##    naming the singleton. Identical behaviour in game, and the file still
##    parses under `--check-only --script`, where autoloads do not exist.
class_name Shooter
extends Node3D

signal aim_changed(aim: Vector2)
signal charge_changed(power: float, marker: float)
signal run_up_started()
signal feinted(count: int)
signal struck(shot: Dictionary)

# --- Tuning -----------------------------------------------------------------

## The humanoid meshes are sized for the keeper. An outfield player is a little
## lighter and a little shorter, and the difference reads at a glance.
const BODY_SCALE := 0.97

## Seconds of held `strike` to fill the bar from 0 to 1.
const CHARGE_TIME := 1.15
## A tap shorter than this is treated as a slip and charges nothing.
const MIN_CHARGE_TIME := 0.12
## Marker sweeps per second at zero power, and the extra sweeps at full power.
const MARKER_RATE_BASE := 2.4
const MARKER_RATE_GAIN := 1.0
## Multipliers the `sweep_level` setting puts on the two rates above. This is the
## game's SECOND difficulty axis, next to the keeper's level: the keeper decides
## how hard the ball is to beat, this decides how hard the ball is to hit clean.
##
## The numbers are chosen against the time the marker actually spends inside the
## clean window, which is what the player has to react to. One crossing of the
## bar takes 1 / rate seconds and the window is 2 * ShotModel.SWEET_WIDTH of it,
## so at index 1 (the rate the game shipped with) the window is open for 92 ms on
## a soft strike and 65 ms at full power. Around that:
##   0 Lent       x0.60 -> 153 ms soft, 108 ms at full power. Comfortable, and
##                still a reaction test rather than a formality.
##   1 Normal     x1.00 -> the original feel, unchanged for anyone who liked it.
##   2 Rapide     x1.40 -> 66 ms soft, 46 ms at full power.
##   3 Fulgurant  x1.85 -> 50 ms soft, 35 ms at full power. Too short to react
##                to, but the sweep is a periodic signal, so it stays humanly
##                possible by ANTICIPATION, which is the skill being tested.
const SWEEP_SCALES: PackedFloat32Array = [0.60, 1.00, 1.40, 1.85]
## Index used when no setting can be read.
const SWEEP_DEFAULT := 1
## Centre of the clean contact window on the bar. `ShotModel.SWEET_WIDTH` is its
## half width. Exposed as a constant because the HUD has to draw the same window.
const SWEET_CENTRE := 0.72

## Seconds of run up at full approach speed, feints excluded.
const RUN_UP_TIME := 0.75
## Distance from the ball to the taker's mark, in metres.
const RUN_UP_LENGTH := 3.35
## Lateral offset of the mark. Negative is the taker's left: the angled approach
## of a right footed player.
const START_SIDE := -1.02
## Fraction of the run after which the kicking leg takes over from the cycle.
const KICK_START := 0.60
## Strides walked over the whole approach.
const STRIDES := 2.5

const FEINT_MAX := 2
## Seconds a stutter step lasts.
const FEINT_WINDOW := 0.30
## Approach speed multiplier during a stutter step.
const FEINT_SLOW := 0.12
## Past this progress the taker is committed and cannot feint any more.
const FEINT_LATEST := 0.78

## Reticle band. Wider than the mouth so shooting wide is possible, narrow
## enough that the reticle cannot be walked out to the corner flag.
const AIM_X_LIMIT := 1.35
const AIM_Y_MIN := -0.10
const AIM_Y_MAX := 1.30
## Reticle units per pixel of mouse travel, before Game.mouse_sensitivity.
const MOUSE_SCALE := 0.0018
## Reticle units per second on the keyboard aim axis.
const KEY_AIM_RATE := 0.9
## Spin units per second while a spin action is held.
const SPIN_RATE := 1.5

## Seconds of follow through animated after contact.
const FOLLOW_TIME := 0.85
## Integration step of the HUD preview arc.
const PREVIEW_STEP := 0.02

# --- The reaction ------------------------------------------------------------
#
# Mirrors of Shootout.Verdict. The autoload cannot be named at parse time in a
# file that must keep compiling under `--check-only --script`, and a verdict is
# just a small int, so the mapping is restated here rather than imported. Same
# trick, and same reason, as the block at the top of `keeper.gd`.
const _V_BUT := 0
const _V_ARRET := 1
const _V_POTEAU := 2
const _V_BARRE := 3
const _V_DEHORS := 4

## Seconds the reaction takes to come on, and how long it runs before it simply
## holds. Nothing resets it but `reset_stance`, so the taker keeps his opinion
## until he is put back on his mark for the next penalty.
const REACT_BLEND := 0.38
const REACT_TIME := 2.60

## Elbow angles of the run and the strike, radians of flexion.
##
## The sign matters and it is the opposite of the knee's. A knee folds BACKWARDS
## (the heel towards the seat) and an elbow folds FORWARDS (the hand towards the
## shoulder), so on a body facing its own -Z the knee hinges negative about X and
## the elbow hinges POSITIVE. Driving both the same way, which is what this file
## used to do, gives a runner two extra knees where his arms should be.
const ELBOW_REST := 0.34
## Flexion added per radian of FORWARD shoulder swing. A sprinter's forward arm is
## folded to about a right angle and his trailing arm is nearly straight, and that
## asymmetry is most of what makes a run cycle read from behind.
const ELBOW_DRIVE := 0.85
## ... and per radian of backward swing, which barely opens at all.
const ELBOW_TRAIL := 0.12
## How far the swinging arm crosses the chest, radians per radian of swing. Arms
## that pump in two parallel planes read as a man on a rowing machine.
const ARM_CROSS := 0.24

## Where the hands go when they go on the head: half the distance between them,
## and how far above the head joint they sit. Both are measured against the DRAWN
## head, which is twice life size (see `CharacterModels.HEAD_SCALE`).
##
## They are on the CROWN and not on the temples, and that is a readability
## decision rather than an anatomical one. The game is watched from behind the
## taker with a head that fills a good part of him: hands at the temples of a
## doubled skull are drawn INSIDE it, the gesture vanishes, and all the player
## sees is a man holding his elbows out. On top of the head they break the
## silhouette, which is the only place a gesture can be read from back there.
const HEAD_GRIP := 0.16
const HEAD_CROWN := 0.23

## Where the toes point, in the ankle joint's own frame: forward is -Z, and a
## real foot runs slightly downhill from the ankle. Aiming an imported foot dead
## level would stand the taker back on his heels.
const _TOE_FORWARD := 0.945
const _TOE_DROP := 0.325
const _TOE_SPAN := 0.20

const ALIGN_HANG := 0
const ALIGN_UP := 1
const ALIGN_CENTRE := 2
## The boot is the one part Meshes builds around its own joint (the ankle), so
## it is attached with no offset at all.
const ALIGN_ORIGIN := 3

# --- Contract state ---------------------------------------------------------

## Normalized reticle, see ShotModel.aim_point.
var aim: Vector2 = Vector2(0.0, 0.42)
var power: float = 0.0
## Sweeping precision marker on the power bar, 0..1.
var marker: float = 0.0
var side_spin: float = 0.0
var lift_spin: float = 0.0
var feints: int = 0
var charging: bool = false
var running: bool = false

## Read only mirror of SWEET_CENTRE. The HUD has to draw the same window the
## strike is resolved against, and Main reads it from here rather than guessing.
var sweet_centre: float = SWEET_CENTRE

# --- Internals --------------------------------------------------------------

var _built: bool = false
var _actions_ready: bool = false

var _rng: RandomNumberGenerator = RandomNumberGenerator.new()
var _game: Node = null
var _shootout: Node = null

var _charge_time: float = 0.0
var _marker_phase: float = 0.0
## Latched sweep multiplier of the attempt being prepared, see SWEEP_SCALES. It
## is read when the stance resets and again the frame the player starts charging,
## never per frame: a difficulty changed from the pause menu applies to the next
## strike instead of making the marker jump in the middle of the current one.
var _sweep_scale: float = 1.0
var _release: float = SWEET_CENTRE
var _strike_held: bool = false
var _feint_held: bool = false

var _travel: float = 0.0
var _run_progress: float = 0.0
var _contacted: bool = false
var _follow_time: float = 0.0
var _anim_time: float = 0.0
var _feint_left: float = 0.0
var _feint_dir: float = 1.0

## Body language, all measured off the animation state.
var _run_angle: float = 0.0
var _plant_offset: float = 0.0
var _hip_yaw_base: float = 0.0
var _tell_noise: float = 0.0
var _plant_noise: float = 0.0
var _cycle_phase: float = 0.0

## --- When the COMPUTER is holding this body (DUEL, see CONTRACTS 2.20) --------
##
## The run up is ticked through the very same `advance_run_up` a human run up is
## ticked through: what changes is only WHO decides. While `_cpu` is true the
## player's keys are ignored, the approach lasts `_cpu_run_time` instead of
## RUN_UP_TIME, the feints are scripted rather than pressed, and the strike comes
## from `TakerAi.strike` rather than from the aim and power a human dialled in.
## `reset_stance()` is the only thing that hands the body back.
var _cpu: bool = false
var _cpu_plan: Dictionary = {}
var _cpu_seed: int = 0
var _cpu_level: int = 1
## Seconds the scripted approach lasts. Zero while a human is holding the body.
var _cpu_run_time: float = 0.0
## Progress values at which the scripted stutter steps fire, ascending.
var _cpu_feints: PackedFloat32Array = PackedFloat32Array()
var _cpu_feints_done: int = 0

## What he thinks of the result, and how long he has been thinking it. -1 is "the
## verdict is not in yet", which is also the state the whole run up is played in.
var _react_verdict: int = -1
var _react_t: float = 0.0
## How many of his own attempts were on the board when this one was struck, so a
## new entry appearing on it is unambiguously THIS shot's verdict.
var _scores_at_strike: int = -1

var _start_pos: Vector3 = Vector3.ZERO
var _final_pos: Vector3 = Vector3.ZERO
var _run_bend: float = 0.0

# Rig nodes.
var _body: Node3D = null
var _hips: Node3D = null
var _spine: Node3D = null
var _neck: Node3D = null
var _hip_l: Node3D = null
var _hip_r: Node3D = null
var _knee_l: Node3D = null
var _knee_r: Node3D = null
var _ankle_l: Node3D = null
var _ankle_r: Node3D = null
var _shoulder_l: Node3D = null
var _shoulder_r: Node3D = null
var _elbow_l: Node3D = null
var _elbow_r: Node3D = null
var _wrist_l: Node3D = null
var _wrist_r: Node3D = null
var _boot_marker: Node3D = null
## The imported figure, when one is installed. Null is the normal, supported
## case: the joint rig above is then what gets drawn, exactly as before.
var _model: Node3D = null
## Distance from the wrist to the centre of the imported hand, in WORLD metres.
var _hand_reach: float = 0.06
## How far the drawn skull is lifted above the head joint, in this rig's own
## units. Zero on the procedural body, which has no enlarged head to lift.
var _head_rise: float = 0.0

var _hip_height: float = 0.90
var _thigh_len: float = 0.42
var _shin_len: float = 0.42
var _foot_h: float = 0.08
var _torso_len: float = 0.56
var _upper_arm_len: float = 0.30
var _fore_arm_len: float = 0.28

# Preview cache: aim_velocity is an iterative solver, it must not run per frame
# for an unchanged aim.
var _pv_points: PackedVector3Array = PackedVector3Array()
var _pv_valid: bool = false
var _pv_aim: Vector2 = Vector2.ZERO
var _pv_power: float = -1.0
var _pv_side: float = 0.0
var _pv_lift: float = 0.0
var _pv_steps: int = 0


func _ready() -> void:
	build()


func _process(delta: float) -> void:
	if not _built:
		return
	_anim_time += delta
	if _contacted and _follow_time < FOLLOW_TIME:
		_follow_time = minf(_follow_time + delta, FOLLOW_TIME)
	if _react_verdict >= 0:
		_react_t = minf(_react_t + delta, REACT_TIME)
	elif _contacted:
		_poll_verdict()
	_apply_pose()


# --- Construction -----------------------------------------------------------

func build() -> void:
	if _built:
		return
	_built = true
	_actions_ready = InputMap.has_action(&"strike")
	_start_pos = Vector3(START_SIDE, 0.0, Field.SPOT_Z + RUN_UP_LENGTH)
	_final_pos = Vector3(-0.26, 0.0, Field.SPOT_Z + 0.46)
	_build_body()
	reset_stance()


func _build_body() -> void:
	var parts: Dictionary = _humanoid_parts()

	var m_pelvis: Mesh = _mesh_for(parts, "pelvis", _fallback_capsule(0.15, 0.24))
	var m_torso: Mesh = _mesh_for(parts, "torso", _fallback_capsule(0.17, 0.56))
	var m_head: Mesh = _mesh_for(parts, "head", _fallback_capsule(0.11, 0.24))
	var m_upper: Mesh = _mesh_for(parts, "upper_arm", _fallback_capsule(0.055, 0.30))
	var m_fore: Mesh = _mesh_for(parts, "fore_arm", _fallback_capsule(0.048, 0.28))
	var m_hand: Mesh = _mesh_for(parts, "hand", _fallback_capsule(0.045, 0.12))
	var m_thigh: Mesh = _mesh_for(parts, "thigh", _fallback_capsule(0.085, 0.44))
	var m_shin: Mesh = _mesh_for(parts, "shin", _fallback_capsule(0.065, 0.42))
	var m_foot: Mesh = _mesh_for(parts, "foot", _fallback_box(Vector3(0.10, 0.08, 0.26)))

	_thigh_len = _mesh_span(m_thigh)
	_shin_len = _mesh_span(m_shin)
	_torso_len = _mesh_span(m_torso)
	_upper_arm_len = _mesh_span(m_upper)
	_fore_arm_len = _mesh_span(m_fore)
	# The boot hangs from its own origin, so what matters is how far its sole
	# sits BELOW the ankle. Standing straight, the ankle is exactly that far off
	# the turf. Guessing this instead of measuring it is how a boot ends buried.
	_foot_h = maxf(-m_foot.get_aabb().position.y, 0.01) if m_foot != null else 0.04
	_hip_height = _thigh_len + _shin_len + _foot_h

	# An installed figure replaces every one of those proportions with its own,
	# BEFORE the joint tree below is laid out from them. The animation, the
	# inverse kinematics and boot_position() then all run on the real body, which
	# is the only way the boot meets the ball rather than passing beside it.
	var shoulder_rise: float = _torso_len * 0.90
	var shoulder_x: float = 0.185
	var hip_x: float = 0.095
	_adopt_model()
	if _model != null:
		var m: Dictionary = CharacterModels.metrics(CharacterModels.ROLE_SHOOTER)
		# Metrics are world metres and this rig is drawn at BODY_SCALE, so every
		# local length is the measurement divided back out by that factor.
		var inv: float = 1.0 / maxf(BODY_SCALE, 0.01)
		_thigh_len = _metric(m, "thigh", _thigh_len) * inv
		_shin_len = _metric(m, "shin", _shin_len) * inv
		_upper_arm_len = _metric(m, "upper_arm", _upper_arm_len) * inv
		_fore_arm_len = _metric(m, "fore_arm", _fore_arm_len) * inv
		_foot_h = _metric(m, "sole_drop", _foot_h) * inv
		_hip_height = _thigh_len + _shin_len + _foot_h
		shoulder_rise = _metric(m, "shoulder_rise", shoulder_rise) * inv - 0.04
		shoulder_x = _metric(m, "shoulder_half", shoulder_x) * inv
		hip_x = _metric(m, "hip_half", hip_x) * inv
		_torso_len = _metric(m, "torso", _torso_len) * inv - 0.04
		_hand_reach = _metric(m, "hand_reach", _hand_reach)
		# How far the DRAWN skull sits above the joint the rest of this file
		# measures against. See `HEAD_CROWN`.
		_head_rise = _metric(m, "head_rise", 0.0) * inv

	var jersey: Material = _safe_material(Mats.jersey(Palette.SHOOTER_JERSEY))
	var shorts: Material = _safe_material(Mats.jersey(Palette.SHOOTER_SHORTS))
	var skin: Material = _safe_material(Mats.skin())
	var boot: Material = _safe_material(Mats.boot())
	var hair: Material = _safe_material(Mats.jersey(Palette.HAIR))

	_body = Node3D.new()
	_body.name = "Body"
	_body.scale = Vector3.ONE * BODY_SCALE
	add_child(_body)

	_hips = _joint(_body, "Hips", Vector3(0.0, _hip_height, 0.0))
	_attach(_hips, m_pelvis, shorts, ALIGN_CENTRE, "Pelvis")

	_spine = _joint(_hips, "Spine", Vector3(0.0, 0.04, 0.0))
	_attach(_spine, m_torso, jersey, ALIGN_UP, "Torso")

	_neck = _joint(_spine, "Neck", Vector3(0.0, _torso_len, 0.0))
	_attach(_neck, m_head, skin, ALIGN_UP, "Head")
	var head_h: float = _mesh_span(m_head)
	var cap := SphereMesh.new()
	cap.radius = head_h * 0.44
	cap.height = head_h * 0.66
	cap.radial_segments = 16
	cap.rings = 8
	var hair_node: MeshInstance3D = _attach(_neck, cap, hair, ALIGN_CENTRE, "Hair")
	hair_node.position = Vector3(0.0, head_h * 0.72, 0.012)

	_shoulder_l = _joint(_spine, "ShoulderL", Vector3(-shoulder_x, shoulder_rise, 0.0))
	_shoulder_r = _joint(_spine, "ShoulderR", Vector3(shoulder_x, shoulder_rise, 0.0))
	_attach(_shoulder_l, m_upper, jersey, ALIGN_HANG, "UpperArmL")
	_attach(_shoulder_r, m_upper, jersey, ALIGN_HANG, "UpperArmR")
	_elbow_l = _joint(_shoulder_l, "ElbowL", Vector3(0.0, -_upper_arm_len, 0.0))
	_elbow_r = _joint(_shoulder_r, "ElbowR", Vector3(0.0, -_upper_arm_len, 0.0))
	_attach(_elbow_l, m_fore, skin, ALIGN_HANG, "ForeArmL")
	_attach(_elbow_r, m_fore, skin, ALIGN_HANG, "ForeArmR")
	_wrist_l = _joint(_elbow_l, "WristL", Vector3(0.0, -_fore_arm_len, 0.0))
	_wrist_r = _joint(_elbow_r, "WristR", Vector3(0.0, -_fore_arm_len, 0.0))
	_attach(_wrist_l, m_hand, skin, ALIGN_HANG, "HandL")
	_attach(_wrist_r, m_hand, skin, ALIGN_HANG, "HandR")

	_hip_l = _joint(_hips, "HipL", Vector3(-hip_x, 0.0, 0.0))
	_hip_r = _joint(_hips, "HipR", Vector3(hip_x, 0.0, 0.0))
	_attach(_hip_l, m_thigh, skin, ALIGN_HANG, "ThighL")
	_attach(_hip_r, m_thigh, skin, ALIGN_HANG, "ThighR")
	# The shorts are a short skirt of the pelvis mesh: cover the top of each
	# thigh with a scaled copy so the kit reads at distance.
	_short_leg(_hip_l, m_thigh, shorts)
	_short_leg(_hip_r, m_thigh, shorts)

	_knee_l = _joint(_hip_l, "KneeL", Vector3(0.0, -_thigh_len, 0.0))
	_knee_r = _joint(_hip_r, "KneeR", Vector3(0.0, -_thigh_len, 0.0))
	_attach(_knee_l, m_shin, skin, ALIGN_HANG, "ShinL")
	_attach(_knee_r, m_shin, skin, ALIGN_HANG, "ShinR")

	_ankle_l = _joint(_knee_l, "AnkleL", Vector3(0.0, -_shin_len, 0.0))
	_ankle_r = _joint(_knee_r, "AnkleR", Vector3(0.0, -_shin_len, 0.0))
	_attach(_ankle_l, m_foot, boot, ALIGN_ORIGIN, "BootL")
	_attach(_ankle_r, m_foot, boot, ALIGN_ORIGIN, "BootR")

	# Contact point of the kicking foot: the inside of the right boot.
	_boot_marker = _joint(_ankle_r, "BootContact", Vector3(-0.02, -_foot_h * 0.45, -0.07))

	# The joint tree keeps running when a figure is installed, because it IS the
	# animation; only its own meshes stop being drawn.
	if _model != null:
		_hide_meshes(_body)


## Instances the imported figure, when one is installed. Null is not an error:
## it is the coarser render the project falls back to, and deleting `assets/`
## entirely leaves this file behaving exactly as it did before models existed.
func _adopt_model() -> void:
	if not CharacterModels.available(CharacterModels.ROLE_SHOOTER):
		return
	var figure: Node3D = CharacterModels.build(CharacterModels.ROLE_SHOOTER)
	if figure == null:
		return
	if CharacterModels.metrics(CharacterModels.ROLE_SHOOTER).is_empty():
		figure.queue_free()
		return
	_model = figure
	_model.name = "Figure"
	add_child(_model)


func _hide_meshes(node: Node) -> void:
	if node is MeshInstance3D:
		(node as MeshInstance3D).visible = false
	for child in node.get_children():
		_hide_meshes(child)


func _metric(source: Dictionary, key: String, fallback: float) -> float:
	var value: Variant = source.get(key, null)
	var kind: int = typeof(value)
	if kind != TYPE_FLOAT and kind != TYPE_INT:
		return fallback
	var out: float = float(value)
	if not is_finite(out) or out <= 0.0:
		return fallback
	return out


func _short_leg(parent: Node3D, thigh: Mesh, mat: Material) -> void:
	var mi: MeshInstance3D = _attach(parent, thigh, mat, ALIGN_HANG, "Short")
	# Scaling happens around the instance origin, so the alignment offset has to
	# be scaled by the same factor or the shorts hang off the knee.
	mi.scale = Vector3(1.12, 0.42, 1.12)
	mi.position.y *= 0.42


func _humanoid_parts() -> Dictionary:
	var raw: Variant = Meshes.humanoid_parts()
	if raw is Dictionary:
		return raw as Dictionary
	push_warning("Shooter: Meshes.humanoid_parts() gave no dictionary, using fallbacks.")
	return {}


func _mesh_for(parts: Dictionary, key: String, fallback: Mesh) -> Mesh:
	if parts.has(key):
		var candidate: Variant = parts[key]
		if candidate is Mesh:
			return candidate as Mesh
	return fallback


func _mesh_span(mesh: Mesh) -> float:
	if mesh == null:
		return 0.30
	return maxf(mesh.get_aabb().size.y, 0.02)


func _fallback_capsule(radius: float, height: float) -> Mesh:
	var m := CapsuleMesh.new()
	m.radius = radius
	m.height = maxf(height, radius * 2.05)
	m.radial_segments = 12
	m.rings = 4
	return m


func _fallback_box(size: Vector3) -> Mesh:
	var m := BoxMesh.new()
	m.size = size
	return m


func _safe_material(mat: Material) -> Material:
	if mat == null:
		push_warning("Shooter: a material came back null, the mesh keeps its own.")
	return mat


func _joint(parent: Node3D, node_name: String, offset: Vector3) -> Node3D:
	var n := Node3D.new()
	n.name = node_name
	parent.add_child(n)
	n.position = offset
	return n


## Attaches a mesh under a joint and aligns it by its own bounding box, so the
## rig does not care whether Meshes builds a limb centred on the origin or
## standing on it.
func _attach(parent: Node3D, mesh: Mesh, mat: Material, align: int, node_name: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.name = node_name
	mi.mesh = mesh
	if mat != null:
		mi.material_override = mat
	parent.add_child(mi)
	if mesh != null:
		var box: AABB = mesh.get_aabb()
		match align:
			ALIGN_HANG:
				mi.position.y = -box.end.y
			ALIGN_UP:
				mi.position.y = -box.position.y
			ALIGN_ORIGIN:
				mi.position.y = 0.0
			_:
				mi.position.y = -(box.position.y + box.size.y * 0.5)
	return mi


# --- Stance and reset -------------------------------------------------------

func reset_stance() -> void:
	if not _built:
		build()
		return
	aim = Vector2(0.0, 0.42)
	power = 0.0
	marker = 0.0
	side_spin = 0.0
	lift_spin = 0.0
	feints = 0
	charging = false
	running = false
	_contacted = false
	_charge_time = 0.0
	_travel = 0.0
	_run_progress = 0.0
	_follow_time = 0.0
	_feint_left = 0.0
	_feint_dir = 1.0
	_release = SWEET_CENTRE
	_react_verdict = -1
	_react_t = 0.0
	_scores_at_strike = -1
	_run_angle = 0.0
	_plant_offset = 0.0
	_hip_yaw_base = 0.0
	_pv_valid = false
	# The body goes back to the human. This is the ONLY place that clears it, as
	# the contract promises, so a half played CPU run up can never leak into the
	# next attempt.
	_cpu = false
	_cpu_plan = {}
	_cpu_seed = 0
	_cpu_run_time = 0.0
	_cpu_feints = PackedFloat32Array()
	_cpu_feints_done = 0
	_pv_power = -1.0

	_sweep_scale = _read_sweep_scale()
	_rng.seed = _attempt_seed()
	# A marker that always starts at the same place turns the timing into a rote
	# memory test, so each attempt gets its own phase.
	_marker_phase = _rng.randf() * 1.8
	_tell_noise = (_rng.randf() * 2.0 - 1.0) * 0.22
	_plant_noise = (_rng.randf() * 2.0 - 1.0) * 0.18
	_cycle_phase = _rng.randf() * 0.4
	marker = _marker_value()

	# A button already held must not charge the next penalty on its own.
	_strike_held = _pressed(&"strike")
	_feint_held = _pressed(&"feint")

	_final_pos = Vector3(-0.26, 0.0, Field.SPOT_Z + 0.46)
	_run_bend = -0.28
	_apply_pose()
	aim_changed.emit(aim)
	charge_changed.emit(power, marker)


# --- Aiming and charging ----------------------------------------------------

func handle_aim(delta: float, mouse_delta: Vector2) -> void:
	if not _built:
		return
	var before: Vector2 = aim
	var sens: float = clampf(_setting_float("mouse_sensitivity", 1.0), 0.2, 3.0)

	# Mouse drives both reticle axes. Screen y grows downwards, the reticle does
	# not, hence the sign flip.
	aim.x += mouse_delta.x * MOUSE_SCALE * sens
	aim.y -= mouse_delta.y * MOUSE_SCALE * sens
	# aim_left / aim_right are the keyboard alternative for the horizontal axis.
	aim.x += _axis(&"aim_left", &"aim_right") * KEY_AIM_RATE * delta

	aim.x = clampf(aim.x, -AIM_X_LIMIT, AIM_X_LIMIT)
	aim.y = clampf(aim.y, AIM_Y_MIN, AIM_Y_MAX)
	if not aim.is_equal_approx(before):
		_pv_valid = false
		aim_changed.emit(aim)

	# spin_left / spin_right curl the ball, aim_up / aim_down set backspin to
	# topspin. Both are held settings: they stay where the player put them until
	# the next stance reset.
	var side_before: float = side_spin
	var lift_before: float = lift_spin
	side_spin = clampf(side_spin + _axis(&"spin_left", &"spin_right") * SPIN_RATE * delta, -1.0, 1.0)
	lift_spin = clampf(lift_spin + _axis(&"aim_down", &"aim_up") * SPIN_RATE * delta, -1.0, 1.0)
	if not is_equal_approx(side_before, side_spin) or not is_equal_approx(lift_before, lift_spin):
		_pv_valid = false

	_update_charge(delta)


func _update_charge(delta: float) -> void:
	var held: bool = _pressed(&"strike")
	var pressed_edge: bool = held and not _strike_held
	var released_edge: bool = (not held) and _strike_held
	_strike_held = held

	if pressed_edge and not charging and not running:
		charging = true
		_charge_time = 0.0
		power = 0.0
		_sweep_scale = _read_sweep_scale()

	if charging:
		_charge_time += delta
		power = clampf(_charge_time / CHARGE_TIME, 0.0, 1.0)
		# The sweep speeds up with the power, so the top of the bar is genuinely
		# harder to time than the middle. The whole rate is then scaled by the
		# difficulty the player chose.
		_marker_phase += delta * marker_rate()
		marker = _marker_value()
		charge_changed.emit(power, marker)

	if released_edge and charging:
		if _charge_time < MIN_CHARGE_TIME:
			# A slip of the finger, not a penalty. Give the bar back.
			charging = false
			power = 0.0
			_charge_time = 0.0
			charge_changed.emit(power, marker)
		else:
			_begin_run_up()


## Phase units per second the marker is sweeping at right now: the base rate, the
## power gain, and the difficulty multiplier of the current attempt. One full
## crossing of the bar is one phase unit.
func marker_rate() -> float:
	return (MARKER_RATE_BASE + MARKER_RATE_GAIN * clampf(power, 0.0, 1.0)) * _sweep_scale


## Multiplier of the `sweep_level` setting, defended against a missing autoload
## and against an index the settings file could carry from another build.
func _read_sweep_scale() -> float:
	var index: int = clampi(_setting_int("sweep_level", SWEEP_DEFAULT), 0, SWEEP_SCALES.size() - 1)
	return maxf(SWEEP_SCALES[index], 0.05)


## The marker is a triangle wave: the phase runs 0 -> 2 and folds back, so the
## marker crosses the bar at a constant speed and turns around at both ends.
func _marker_value() -> float:
	var p: float = fposmod(_marker_phase, 2.0)
	return p if p <= 1.0 else 2.0 - p


func _begin_run_up() -> void:
	charging = false
	running = true
	_release = marker
	_travel = 0.0
	_run_progress = 0.0
	_contacted = false
	_follow_time = 0.0
	_feint_left = 0.0
	feints = 0

	# The stance the player has taken is now locked in, and it leaks. The run
	# angle and the plant offset follow the aim and the curl, blurred by a seeded
	# offset so a good keeper still has to guess.
	_run_angle = clampf(aim.x * 0.50 + side_spin * 0.30 + _tell_noise, -1.0, 1.0)
	_plant_offset = clampf(aim.x * 0.45 + side_spin * 0.25 + _plant_noise, -1.0, 1.0)
	_hip_yaw_base = _run_angle * 0.12
	_final_pos = Vector3(-0.26 + _plant_offset * 0.10, 0.0, Field.SPOT_Z + 0.46)
	_run_bend = -0.28 - 0.34 * _run_angle

	charge_changed.emit(power, _release)
	run_up_started.emit()


# --- Run up -----------------------------------------------------------------

func advance_run_up(delta: float) -> void:
	if not _built or not running:
		return
	# A scripted approach reads its stutter steps off the plan; a human reads his
	# off the keyboard. Never both: while the computer holds this body the feint
	# key belongs to nobody.
	if _cpu:
		_read_cpu_feint()
	else:
		_read_feint()

	var speed: float = 1.0
	if _feint_left > 0.0:
		_feint_left = maxf(_feint_left - delta, 0.0)
		speed = FEINT_SLOW
	_travel += delta * speed
	var span: float = _cpu_run_time if _cpu else RUN_UP_TIME
	_run_progress = clampf(_travel / maxf(span, 0.0001), 0.0, 1.0)
	if _run_progress >= 1.0 and not _contacted:
		_do_contact()
	_apply_pose()


## Seconds from now until contact while a CPU run up is playing, negative once it
## has struck, and zero when no scripted run up is playing at all. Main reconciles
## this with the keeper's own clock, which counts the other way.
func time_to_contact() -> float:
	if not _cpu:
		return 0.0
	return _cpu_run_time - _travel


## Hands this body to `TakerAi`. See CONTRACTS 2.20.
##
## The plan never reaches the screen through this body except as body language:
## the approach shows what `TakerAi.tells_at` says it shows and no more, which is
## what keeps the player guessing exactly as the AI keeper has to.
func run_cpu_penalty(plan: Dictionary, rng_seed: int) -> void:
	if not _built:
		build()
	if plan.is_empty():
		push_warning("Shooter: run_cpu_penalty received an empty plan, the taker stands still.")
		return

	reset_stance()
	_cpu = true
	_cpu_plan = plan.duplicate(true)
	_cpu_seed = rng_seed
	_cpu_level = int(plan.get("level", TakerAi.SEANCE_LEVEL))
	_cpu_run_time = maxf(TakerAi.run_up_time(_cpu_level, rng_seed), 0.05)

	# Feints are decided up front and fired by progress, so the approach is the
	# same every time this seed is replayed. Spread them across the window the
	# human feint is allowed in, so a scripted stutter cannot happen after the
	# point a human one would be refused.
	var count: int = clampi(TakerAi.feint_count(_cpu_level, rng_seed), 0, FEINT_MAX)
	_cpu_feints = PackedFloat32Array()
	for i in count:
		_cpu_feints.append(FEINT_LATEST * (float(i) + 1.0) / (float(count) + 1.0))
	_cpu_feints_done = 0

	# The tells at the top of the run up. `advance_run_up` refreshes them as the
	# approach plays, so what leaks grows with what the taker has committed to.
	_adopt_cpu_tells(0.0)

	charging = false
	running = true
	_contacted = false
	_travel = 0.0
	_run_progress = 0.0
	_follow_time = 0.0
	_feint_left = 0.0
	feints = 0
	_release = float(plan.get("release", SWEET_CENTRE))
	power = float(plan.get("power", 0.8))
	_final_pos = Vector3(-0.26 + _plant_offset * 0.10, 0.0, Field.SPOT_Z + 0.46)
	_run_bend = -0.28 - 0.34 * _run_angle
	run_up_started.emit()


## Copies the body language TakerAi is willing to show at this point of the run.
func _adopt_cpu_tells(t: float) -> void:
	var shown: Dictionary = TakerAi.tells_at(_cpu_plan, _cpu_level, _cpu_seed, t)
	if shown.is_empty():
		return
	_run_angle = clampf(float(shown.get("run_angle", 0.0)), -1.0, 1.0)
	_plant_offset = clampf(float(shown.get("plant_offset", 0.0)), -1.0, 1.0)
	_hip_yaw_base = float(shown.get("hip_yaw", _run_angle * 0.12))


## The scripted stutter step. Same visible effect as the human one, fired by
## progress rather than by a key.
func _read_cpu_feint() -> void:
	_adopt_cpu_tells(_run_progress)
	if _cpu_feints_done >= _cpu_feints.size():
		return
	if _feint_left > 0.0:
		return
	if _run_progress < _cpu_feints[_cpu_feints_done]:
		return
	_cpu_feints_done += 1
	feints += 1
	_feint_left = FEINT_WINDOW
	_feint_dir = -signf(_run_angle) if not is_zero_approx(_run_angle) else 1.0
	feinted.emit(feints)


func _read_feint() -> void:
	var held: bool = _pressed(&"feint")
	var edge: bool = held and not _feint_held
	_feint_held = held
	if not edge:
		return
	if feints >= FEINT_MAX or _run_progress >= FEINT_LATEST or _feint_left > 0.0:
		return
	feints += 1
	_feint_left = FEINT_WINDOW
	_feint_dir = -signf(_run_angle) if not is_zero_approx(_run_angle) else 1.0
	# A stutter step throws the tells around: the hips fake the other way and the
	# approach loses its rhythm. That is the point of the move.
	_run_angle = clampf(lerpf(_run_angle, -_run_angle * 0.6 + _tell_noise, 0.55), -1.0, 1.0)
	_plant_offset = clampf(_plant_offset * 0.55 + _plant_noise * 0.8, -1.0, 1.0)
	feinted.emit(feints)


func _do_contact() -> void:
	_contacted = true
	running = false
	_run_progress = 1.0
	_follow_time = 0.0
	_scores_at_strike = _own_scores()
	# Pose first: Main reads boot_position() from the `struck` handler and the
	# contact effect has to land on the ball, not one frame behind it.
	_apply_pose()

	# A scripted penalty resolves through TakerAi, which owns the plan and its
	# seed. Resolving it from `aim` and `power` here would be resolving a shot the
	# computer never chose, and the aim it would read is the human's leftover.
	var shot: Dictionary = TakerAi.strike(_cpu_plan, _cpu_seed) if _cpu \
		else ShotModel.resolve(
			aim, power, side_spin, lift_spin, _release, SWEET_CENTRE, _shot_seed()
		)
	if shot.is_empty():
		push_error("Shooter: the strike resolved to nothing and is lost.")
		return
	struck.emit(shot)


# --- The reaction -----------------------------------------------------------

## Tells the taker how his penalty ended, so that he can have a reaction to it:
## arms up on a goal, hands on the head on a miss, a shrug and a hard stare at
## the turf on a save. `verdict` is a Shootout.Verdict. Anything else, and any
## second call, is ignored: a man reacts to a penalty once.
##
## Calling this is OPTIONAL. The taker also finds the verdict out for himself
## (see `_poll_verdict`), so the reaction works without the orchestrator having
## to know it exists, and passing it in simply makes it land on the exact frame
## the caller wanted rather than on the frame the score changed.
func react(verdict: int) -> void:
	if _react_verdict >= 0 or verdict < _V_BUT or verdict > _V_DEHORS:
		return
	_react_verdict = verdict
	_react_t = 0.0


## Watches his own row of the scoreboard for the entry this attempt is about to
## add to it. Cheap (one property read per frame, only between contact and the
## verdict) and it keeps the reaction entirely inside this file.
func _poll_verdict() -> void:
	if _scores_at_strike < 0:
		return
	var now: int = _own_scores()
	if now <= _scores_at_strike:
		return
	var s: Node = _shootout_node()
	if s == null:
		return
	var raw: Variant = s.get("player_scores")
	if not (raw is Array):
		return
	var scores: Array = raw as Array
	if scores.is_empty():
		return
	var last: Variant = scores[scores.size() - 1]
	if typeof(last) != TYPE_INT and typeof(last) != TYPE_FLOAT:
		return
	react(int(last))


## How many attempts of his own are on the board right now. -1 is "cannot tell",
## which switches the poll off rather than making something up.
func _own_scores() -> int:
	var s: Node = _shootout_node()
	if s == null:
		return -1
	var raw: Variant = s.get("player_scores")
	if raw is Array:
		return (raw as Array).size()
	return -1


## How much of the reaction is showing, 0 to 1.
func _react_weight() -> float:
	if _react_verdict < 0:
		return 0.0
	return smoothstep(0.0, REACT_BLEND, _react_t)


# --- Reading the shooter ----------------------------------------------------

func cues() -> Dictionary:
	var level: int = _setting_int("keeper_level", 1)
	var out: Dictionary = {}
	var lossy: Variant = ShotModel.tell_cues(aim, power, side_spin, _run_angle, feints, level)
	if lossy is Dictionary:
		out = (lossy as Dictionary).duplicate()
	if not out.has("aim_hint"):
		out["aim_hint"] = 0.0
	if not out.has("power_hint"):
		out["power_hint"] = power
	# The body language itself is not a guess: it is what the taker is visibly
	# doing right now. Only the aim and the power hints are degraded.
	out["run_angle"] = _run_angle
	out["approach_speed"] = _approach_speed()
	out["plant_offset"] = _plant_offset
	out["hip_yaw"] = _hip_yaw_now()
	out["feints"] = feints
	return out


func _approach_speed() -> float:
	var base: float = lerpf(0.38, 1.0, clampf(power, 0.0, 1.0))
	base -= 0.16 * float(feints)
	if _feint_left > 0.0:
		base *= 0.35
	return clampf(base, 0.0, 1.0)


## Hip yaw as the KEEPER reads it: positive means the hips are opened towards
## +X, the shooter's right, which is the sign convention every other cue uses.
## The node rotation is the negative of this, because a Node3D facing -Z turns
## towards -X when its Y rotation goes positive.
func _hip_yaw_now() -> float:
	var open: float = smoothstep(0.30, 1.0, _run_progress)
	var yaw: float = _hip_yaw_base + aim.x * 0.26 * open
	if _feint_left > 0.0:
		yaw += _feint_dir * 0.18 * sin((1.0 - _feint_left / FEINT_WINDOW) * PI)
	return yaw


# --- Preview ----------------------------------------------------------------

func preview(steps: int) -> PackedVector3Array:
	if steps <= 0:
		return PackedVector3Array()
	if _pv_valid and steps == _pv_steps and aim.is_equal_approx(_pv_aim) \
			and is_equal_approx(power, _pv_power) \
			and is_equal_approx(side_spin, _pv_side) \
			and is_equal_approx(lift_spin, _pv_lift):
		return _pv_points

	# The preview is the shot the player would get with a perfect release: no
	# error cone, no miscue. Going through resolve() guarantees the arc and the
	# real strike come out of exactly the same solver.
	var clean: Variant = ShotModel.resolve(
		aim, power, side_spin, lift_spin, SWEET_CENTRE, SWEET_CENTRE, 0
	)
	var points: PackedVector3Array = PackedVector3Array()
	if clean is Dictionary:
		var shot: Dictionary = clean as Dictionary
		var vel: Vector3 = shot.get("velocity", Vector3.ZERO)
		var spin: Vector3 = shot.get("spin", Vector3.ZERO)
		if vel.length_squared() > 0.01:
			points = Aero.sample_flight(Field.SPOT, vel, spin, Vector3.ZERO, PREVIEW_STEP, steps)

	_pv_points = points
	_pv_valid = true
	_pv_steps = steps
	_pv_aim = aim
	_pv_power = power
	_pv_side = side_spin
	_pv_lift = lift_spin
	return _pv_points


func boot_position() -> Vector3:
	if _boot_marker != null and _boot_marker.is_inside_tree():
		return _boot_marker.global_position
	return Field.SPOT + Vector3(0.0, 0.0, 0.18)


# --- Animation --------------------------------------------------------------

## Strike phase: 0 while the taker is still just running, 1 exactly at contact,
## up to 2 at the end of the follow through. Everything below is a function of
## this one number, which is what keeps the motion continuous when a feint
## stretches the approach.
func _strike_u() -> float:
	if _contacted:
		return 1.0 + clampf(_follow_time / FOLLOW_TIME, 0.0, 1.0)
	return clampf((_run_progress - KICK_START) / (1.0 - KICK_START), 0.0, 1.0)


func _apply_pose() -> void:
	if not _built or _body == null:
		return
	var u: float = _run_progress
	var s: float = _strike_u()
	var kick: float = smoothstep(0.0, 0.30, s)
	var idle_w: float = 1.0 - smoothstep(0.0, 0.14, u)
	var run_w: float = smoothstep(0.0, 0.14, u) * (1.0 - kick)
	var cyc: float = u * STRIDES * TAU + _cycle_phase

	var thigh_l: float = 0.0
	var thigh_r: float = 0.0
	var knee_l: float = 0.06
	var knee_r: float = 0.06
	var lean: float = 0.04
	var bob: float = 0.0
	var arm_l_pitch: float = 0.0
	var arm_r_pitch: float = 0.0
	var arm_l_out: float = 0.14
	var arm_r_out: float = 0.14

	if idle_w > 0.0:
		# Waiting on his mark: breathing, a slow weight shift, eyes on the goal.
		var breath: float = sin(_anim_time * 1.7)
		var sway: float = sin(_anim_time * 0.8)
		thigh_l += (0.07 + 0.03 * sway) * idle_w
		thigh_r += (-0.06 - 0.03 * sway) * idle_w
		knee_l += (0.14 + 0.04 * sway) * idle_w
		knee_r += 0.18 * idle_w
		# A small permanent crouch: a hip parked at exactly leg length puts the
		# turf out of the solver's reach and the boots hover a centimetre up.
		bob += (-0.022 + 0.008 * breath - 0.004 * absf(sway)) * idle_w
		lean += 0.05 * idle_w
		arm_l_out += (0.06 + 0.035 * sway) * idle_w
		arm_r_out += (0.06 - 0.035 * sway) * idle_w
		# The arms are never quite still either: they answer the weight shift, so
		# the two elbows breathe open and closed a few degrees out of phase.
		arm_l_pitch += (0.05 + 0.07 * sway) * idle_w
		arm_r_pitch += (0.05 - 0.07 * sway) * idle_w

	if run_w > 0.0:
		var sc: float = sin(cyc)
		thigh_l += sc * 0.62 * run_w
		thigh_r += sin(cyc + PI) * 0.62 * run_w
		knee_l += maxf(0.0, -sin(cyc + 1.15)) * 1.05 * run_w
		knee_r += maxf(0.0, -sin(cyc + 1.15 + PI)) * 1.05 * run_w
		bob += (absf(sc) * 0.045 - 0.008) * run_w
		lean += 0.17 * run_w
		arm_l_pitch += sin(cyc + PI) * 0.72 * run_w
		arm_r_pitch += sc * 0.72 * run_w
		arm_l_out += 0.10 * run_w
		arm_r_out += 0.10 * run_w

	if kick > 0.0:
		thigh_r = lerpf(thigh_r, _kick_thigh(s), kick)
		knee_r = lerpf(knee_r, _kick_knee(s), kick)
		thigh_l = lerpf(thigh_l, _plant_thigh(s), kick)
		knee_l = lerpf(knee_l, _plant_knee(s), kick)
		lean = lerpf(lean, _strike_lean(s), kick)
		bob = lerpf(bob, _strike_bob(s), kick)
		var whip: float = smoothstep(0.35, 1.05, s)
		# The left arm flies out and back: that is the counterweight to the
		# kicking leg, and it is what makes the strike read at a glance.
		arm_l_pitch = lerpf(arm_l_pitch, -0.85 * whip, kick)
		arm_l_out = lerpf(arm_l_out, 0.25 + 1.05 * whip, kick)
		arm_r_pitch = lerpf(arm_r_pitch, 0.30 + 0.25 * whip, kick)
		arm_r_out = lerpf(arm_r_out, 0.20 + 0.35 * whip, kick)

	if _feint_left > 0.0:
		# The stutter step: the foot is chopped short and the hips fake.
		var pulse: float = sin((1.0 - _feint_left / FEINT_WINDOW) * PI)
		thigh_r += 0.45 * pulse
		knee_r += 0.80 * pulse
		lean += 0.12 * pulse
		bob -= 0.030 * pulse

	var yaw_cue: float = _hip_yaw_now()
	# The hips WHIP through the ball. It is applied here and deliberately not in
	# `_hip_yaw_now`, which is the tell the keeper reads: the snap happens after
	# the last frame he is allowed to read anything, so telling him about it would
	# be handing him the strike itself.
	var snap: float = _hip_snap(s) * kick
	_place_body(u)
	_hips.position.y = _hip_height + bob
	_hips.rotation.y = -yaw_cue + snap
	# Real shoulder to hip separation: the chest holds its line while the hips
	# open. Cheap to compute, and it is half of what makes a kick look human. The
	# chest gives back part of the snap, so it LAGS the pelvis through contact and
	# then catches up on the follow through, which is where the power reads from.
	_spine.rotation = Vector3(-lean, yaw_cue * 0.45 - snap * 0.42, _strike_side_lean(s) * kick)
	_neck.rotation.x = lean * 0.75

	_hip_r.rotation = Vector3(thigh_r, 0.0, 0.0)
	_hip_l.rotation = Vector3(thigh_l, 0.0, 0.0)
	_knee_r.rotation.x = -knee_r
	_knee_l.rotation.x = -knee_l

	# Standing on his mark, both feet are pinned to the turf by the same solver.
	# The weight shift then bends the knees for free, and no boot floats.
	if idle_w > 0.01 and is_inside_tree():
		var sway_x: float = sin(_anim_time * 0.8) * 0.02
		_ik_leg(_hip_l, _knee_l, _body.global_transform * Vector3(-0.155 + sway_x, _foot_h, 0.07), idle_w)
		_ik_leg(_hip_r, _knee_r, _body.global_transform * Vector3(0.155 + sway_x, _foot_h, -0.09), idle_w)
		_ankle_l.rotation.x = clampf(-(_hip_l.rotation.x + _knee_l.rotation.x) * 0.9, -1.0, 1.0)
		_ankle_r.rotation.x = clampf(-(_hip_r.rotation.x + _knee_r.rotation.x) * 0.9, -1.0, 1.0)

	# Both legs go under inverse kinematics for the strike itself. Joint angles
	# alone cannot put a boot on a ball that is at a fixed world position while
	# the body is still drifting forward, and "close enough" here means the
	# contact effect fires next to the ball instead of on it.
	if kick > 0.0 and is_inside_tree():
		_ik_leg(_hip_r, _knee_r, _kick_foot_target(s), kick)
		_ik_leg(_hip_l, _knee_l, _plant_foot_target(s), kick)
		# The plant foot stays flat on the turf, the kicking foot stays pointed.
		_ankle_l.rotation.x = clampf(-(_hip_l.rotation.x + _knee_l.rotation.x) * 0.9, -1.0, 1.0)
		_ankle_r.rotation.x = lerpf(_ankle_angle(s, knee_r), -0.45, kick * 0.6)
	elif idle_w <= 0.01:
		# Mid run: no foot is planted, so the ankles ride the cycle. The trailing
		# foot points as it leaves the turf and the leading one comes up under the
		# shin, which is the toe off and the heel strike of a real stride.
		_ankle_r.rotation.x = _ankle_angle(s, knee_r)
		_ankle_l.rotation.x = _run_ankle(sin(cyc), run_w)

	# Shoulders, elbows and the cross of the swing, all three off the same number.
	var elbow_l: float = _elbow_flex(arm_l_pitch)
	var elbow_r: float = _elbow_flex(arm_r_pitch)
	if kick > 0.0:
		# Through the strike the two arms do opposite things, and the elbows are
		# where that reads. The counterweight arm is flung out and FOLDS as it goes
		# (a straight arm out there is a scarecrow); the leading arm comes across
		# the chest and OPENS through contact, paying its momentum into the hips.
		var whip_arm: float = smoothstep(0.35, 1.05, s)
		elbow_l = lerpf(elbow_l, 0.50 + 0.72 * whip_arm, kick)
		elbow_r = lerpf(elbow_r, 1.05 - 0.42 * whip_arm, kick)
	_shoulder_l.rotation = Vector3(arm_l_pitch, -ARM_CROSS * arm_l_pitch, -arm_l_out)
	_shoulder_r.rotation = Vector3(arm_r_pitch, ARM_CROSS * arm_r_pitch, arm_r_out)
	_elbow_l.rotation.x = elbow_l
	_elbow_r.rotation.x = elbow_r

	# The verdict is in and he has an opinion about it. It goes on LAST, over
	# whatever the follow through left, and the arms go through inverse kinematics
	# rather than through angles because a hand on a head has to land ON the head.
	var react: float = _react_weight()
	if react > 0.0:
		_apply_reaction(react)

	_drive_model()


## How far an elbow is folded for a given shoulder swing, radians. See the note
## on `ELBOW_REST` for why the sign is positive here and negative on a knee.
func _elbow_flex(pitch: float) -> float:
	return ELBOW_REST + ELBOW_DRIVE * maxf(pitch, 0.0) + ELBOW_TRAIL * maxf(-pitch, 0.0)


## Ankle angle of a swinging foot. `phase` is the sine of that leg's cycle,
## positive with the thigh forward. Negative angles point the toes.
func _run_ankle(phase: float, weight: float) -> float:
	var w: float = clampf(weight, 0.0, 1.0)
	return -0.10 - (0.34 * maxf(-phase, 0.0) - 0.16 * maxf(phase, 0.0)) * w


## How far the pelvis has turned through the ball, radians. Positive opens the
## right hip forwards, which is the direction a right footed strike turns.
func _hip_snap(s: float) -> float:
	if s < 1.0:
		# Wound the other way first: the hips close, then they fire.
		return lerpf(-0.11, 0.24, smoothstep(0.20, 1.0, s))
	return lerpf(0.24, 0.36, smoothstep(0.0, 0.65, s - 1.0))


## What he does about the result. Everything here is a continuous function of
## `_react_t` blended in by `weight`, so it survives being started on any frame
## and it never fights the follow through it is laid over.
func _apply_reaction(weight: float) -> void:
	var t: float = _react_t
	# Shoulder height and the head, in the SPINE's own frame: that is the frame
	# the arm chain lives in, so a target written here is one the arms can reach.
	var head: Vector3 = Vector3(0.0, _torso_len + 0.17, 0.0)
	var w: float = clampf(weight, 0.0, 1.0)
	# Both feet come back under him first. Without this the kicking leg stays where
	# the follow through left it and every reaction is a man balancing on one foot
	# with his knee round his ears.
	if is_inside_tree() and _body != null:
		var stance: float = 0.155
		var settle: float = 0.02 if _react_verdict == _V_BUT else 0.0
		_ik_leg(_hip_l, _knee_l,
			_body.global_transform * Vector3(-stance, _foot_h + settle, 0.07), w)
		_ik_leg(_hip_r, _knee_r,
			_body.global_transform * Vector3(stance, _foot_h, -0.09), w)
		_ankle_l.rotation.x = lerpf(_ankle_l.rotation.x,
			clampf(-(_hip_l.rotation.x + _knee_l.rotation.x) * 0.9, -1.0, 1.0), w)
		_ankle_r.rotation.x = lerpf(_ankle_r.rotation.x,
			clampf(-(_hip_r.rotation.x + _knee_r.rotation.x) * 0.9, -1.0, 1.0), w)
	if _react_verdict == _V_BUT:
		# Both arms thrown up and open, chest out, and a couple of bounces.
		var hop: float = maxf(sin(t * 5.4), 0.0) * exp(-t * 0.8)
		var span: float = 0.42 + 0.05 * sin(t * 3.1)
		_ik_arm(_shoulder_l, _elbow_l,
			Vector3(-span, _torso_len + 0.46 + 0.05 * hop, -0.06),
			Vector3(-1.0, -0.7, 0.2), w)
		_ik_arm(_shoulder_r, _elbow_r,
			Vector3(span, _torso_len + 0.46 + 0.05 * hop, -0.06),
			Vector3(1.0, -0.7, 0.2), w)
		_spine.rotation.x = lerpf(_spine.rotation.x, 0.16, w)
		_neck.rotation.x = lerpf(_neck.rotation.x, -0.22, w)
		_hips.position.y += 0.06 * hop * w
	elif _react_verdict == _V_ARRET:
		# Hands on the hips, chest square, a slow shake of the head at the keeper.
		_ik_arm(_shoulder_l, _elbow_l, Vector3(-0.19, -0.06, 0.03),
			Vector3(-1.0, -0.1, 0.9), w)
		_ik_arm(_shoulder_r, _elbow_r, Vector3(0.19, -0.06, 0.03),
			Vector3(1.0, -0.1, 0.9), w)
		_spine.rotation.x = lerpf(_spine.rotation.x, -0.13, w)
		_neck.rotation.x = lerpf(_neck.rotation.x, -0.24, w)
		_neck.rotation.y = lerpf(_neck.rotation.y, sin(t * 2.3) * 0.30 * exp(-t * 0.5), w)
		_hips.position.y -= 0.035 * w
	else:
		# Wide, off the post, off the bar: both hands go to the head and stay there.
		# The hands are put on the SIDE of the skull rather than on the crown, and
		# HEAD_GRIP is what decides how far out that is. It has to clear the head,
		# and this head is drawn at CharacterModels.HEAD_SCALE, so a grip measured
		# off a realistic skull puts both hands INSIDE the face and the gesture
		# disappears: what the player then sees is a man holding his arms out.
		var grip: float = HEAD_GRIP + 0.012 * sin(t * 1.9)
		# `_head_rise` and not a bigger constant: the drawn skull is no longer
		# centred on the head joint, it is scaled about its own jaw and therefore
		# sits that much higher (CharacterModels `_NECK_SHOW`). Hands written against
		# the joint alone would now land on the mouth, which is a man covering his
		# face rather than a man holding his head.
		var crown: float = HEAD_CROWN + _head_rise
		_ik_arm(_shoulder_l, _elbow_l, head + Vector3(-grip, crown, 0.03),
			Vector3(-1.0, -0.6, -0.35), w)
		_ik_arm(_shoulder_r, _elbow_r, head + Vector3(grip, crown, 0.03),
			Vector3(1.0, -0.6, -0.35), w)
		_spine.rotation.x = lerpf(_spine.rotation.x, -0.22, w)
		_neck.rotation.x = lerpf(_neck.rotation.x, -0.34, w)
		_hips.position.y -= 0.055 * w


## Two link inverse kinematics for one arm, closed form, in the shoulder's own
## parent frame (the spine).
##
## `local_target` is where the WRIST has to end up and `elbow_hint` the direction
## the elbow should bulge in. The hint is turned into the hinge axis rather than
## used as a pole vector, which is the same trick `_ik_leg` uses one axis at a
## time, generalised: `axis = dir x hint` is perpendicular to the shoulder to
## wrist line by construction, so rotating that line about it by the triangle's
## own shoulder angle lands the elbow on the hint side and nowhere else.
##
## An unreachable target is clamped in distance and keeps its direction, so the
## arm simply stretches towards it instead of snapping or going NaN.
func _ik_arm(shoulder: Node3D, elbow: Node3D, local_target: Vector3,
		elbow_hint: Vector3, weight: float) -> void:
	if shoulder == null or elbow == null:
		return
	var l1: float = _upper_arm_len
	var l2: float = _fore_arm_len
	if l1 <= 0.01 or l2 <= 0.01:
		return
	var v: Vector3 = local_target - shoulder.position
	var d: float = v.length()
	if d < 0.02:
		return
	var dir: Vector3 = v / d
	d = clampf(d, absf(l1 - l2) + 0.04, (l1 + l2) * 0.995)

	var cos_elbow: float = clampf((l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2), -1.0, 1.0)
	var flex: float = PI - acos(cos_elbow)
	var cos_shoulder: float = clampf((l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d), -1.0, 1.0)
	var alpha: float = acos(cos_shoulder)

	var axis: Vector3 = dir.cross(elbow_hint)
	if axis.length_squared() < 1.0e-6:
		axis = dir.cross(Vector3.BACK)
	if axis.length_squared() < 1.0e-6:
		axis = dir.cross(Vector3.RIGHT)
	if axis.length_squared() < 1.0e-6:
		return
	axis = axis.normalized()
	var upper_dir: Vector3 = dir.rotated(axis, alpha)
	var y_axis: Vector3 = -upper_dir
	var z_axis: Vector3 = axis.cross(y_axis)
	if z_axis.length_squared() < 1.0e-6:
		return
	var want := Basis(axis, y_axis, z_axis.normalized())

	var k: float = clampf(weight, 0.0, 1.0)
	var from_q: Quaternion = shoulder.basis.get_rotation_quaternion()
	shoulder.basis = Basis(from_q.slerp(want.get_rotation_quaternion(), k))
	elbow.rotation.x = lerpf(elbow.rotation.x, -flex, k)


## Hands the imported figure the joint tree that was just animated. It is aimed
## down the very same joints, never animated a second time on its own, so the
## boot the player sees strike the ball is the boot `boot_position()` reports.
##
## Bases go over as FACING bases (+Z the way the body looks) while a Node3D
## looks down its own -Z, hence the half turn on each of the three.
func _drive_model() -> void:
	if _model == null or not is_inside_tree():
		return
	var flip: Basis = Basis(Vector3.UP, PI)
	CharacterModels.pose(_model, {
		"hips": _hips.global_position,
		"body": _hips.global_basis.orthonormalized() * flip,
		"chest": _spine.global_basis.orthonormalized() * flip,
		"head": _neck.global_basis.orthonormalized() * flip,
		"shoulder_l": _shoulder_l.global_position,
		"elbow_l": _elbow_l.global_position,
		"wrist_l": _wrist_l.global_position,
		"glove_l": _hand_centre(_wrist_l, _elbow_l),
		"shoulder_r": _shoulder_r.global_position,
		"elbow_r": _elbow_r.global_position,
		"wrist_r": _wrist_r.global_position,
		"glove_r": _hand_centre(_wrist_r, _elbow_r),
		"hip_l": _hip_l.global_position,
		"knee_l": _knee_l.global_position,
		"ankle_l": _ankle_l.global_position,
		"toe_l": _toe_target(_ankle_l),
		"hip_r": _hip_r.global_position,
		"knee_r": _knee_r.global_position,
		"ankle_r": _ankle_r.global_position,
		"toe_r": _toe_target(_ankle_r),
	})


## Centre of the hand: past the wrist, carrying on down the forearm.
func _hand_centre(wrist: Node3D, elbow: Node3D) -> Vector3:
	var at: Vector3 = wrist.global_position
	var along: Vector3 = at - elbow.global_position
	if along.length_squared() < 1.0e-8:
		along = wrist.global_basis * Vector3.DOWN
	return at + along.normalized() * _hand_reach


func _toe_target(ankle: Node3D) -> Vector3:
	var dir: Vector3 = ankle.global_basis * Vector3(0.0, -_TOE_DROP, -_TOE_FORWARD)
	if dir.length_squared() < 1.0e-8:
		return ankle.global_position + Vector3.FORWARD * _TOE_SPAN
	return ankle.global_position + dir.normalized() * _TOE_SPAN


func _place_body(u: float) -> void:
	# Ease out with a zero end velocity: the taker decelerates into the plant
	# instead of skidding through the ball.
	var e: float = 1.0 - pow(1.0 - u, 2.2)
	var p: Vector3 = _start_pos.lerp(_final_pos, e)
	p.x += sin(PI * e) * _run_bend
	_body.position = p

	# Face the way he is actually travelling, sampled off the path itself.
	var h: float = 0.02
	var e2: float = 1.0 - pow(maxf(1.0 - (u + h), 0.0), 2.2)
	var p2: Vector3 = _start_pos.lerp(_final_pos, e2)
	p2.x += sin(PI * e2) * _run_bend
	var d: Vector3 = p2 - p
	if d.length_squared() < 1.0e-6:
		d = _final_pos - _start_pos
	_body.rotation.y = atan2(-d.x, -d.z)


## Where the kicking boot has to be, in world space, as a function of the strike
## phase. The middle point is not a guess: it is the ball, so the boot meets it.
func _kick_foot_target(s: float) -> Vector3:
	var xf: Transform3D = _body.global_transform
	# Ankle at contact: just above and just behind the ball centre, so the boot
	# hanging under the ankle strikes the lower half of the ball.
	var contact: Vector3 = Vector3(0.05, Field.BALL_RADIUS + 0.045, Field.SPOT_Z + 0.075)
	if s <= 1.0:
		var back: Vector3 = xf * Vector3(0.13, 0.40, 0.58)
		var ctrl: Vector3 = xf * Vector3(0.10, 0.12, 0.22)
		return _bezier(back, ctrl, contact, clampf(s, 0.0, 1.0))
	var through: Vector3 = xf * Vector3(0.10, 0.92, -0.62)
	var ctrl2: Vector3 = xf * Vector3(0.08, 0.48, -0.30)
	return _bezier(contact, ctrl2, through, clampf(s - 1.0, 0.0, 1.0))


## Where the standing boot has to be. It is fixed in WORLD space from the moment
## it lands, which is the only way to stop the plant foot skating on the turf
## while the body keeps drifting forward through the strike.
func _plant_foot_target(s: float) -> Vector3:
	var lift: float = (1.0 - smoothstep(0.35, 0.72, s)) * 0.28
	return Vector3(
		-0.30 + _plant_offset * 0.10,
		_foot_h * BODY_SCALE + lift,
		Field.SPOT_Z + 0.30 + lift * 1.10
	)


static func _bezier(a: Vector3, b: Vector3, c: Vector3, t: float) -> Vector3:
	var u: float = 1.0 - t
	return a * (u * u) + b * (2.0 * u * t) + c * (t * t)


## Two link inverse kinematics for one leg, blended in by `weight`.
##
## The knee hinges about the leg's local X. The thigh direction is the direction
## of the hip to ankle line rotated forward by the triangle's hip angle, which is
## the closed form solution: no iteration, no jitter, and it degrades gracefully
## because an unreachable target is clamped in distance while keeping its
## direction, so the leg simply stretches towards it.
func _ik_leg(hip: Node3D, knee: Node3D, world_target: Vector3, weight: float) -> void:
	var parent := hip.get_parent() as Node3D
	if parent == null or not parent.is_inside_tree():
		return
	var l1: float = _thigh_len
	var l2: float = _shin_len
	if l1 <= 0.01 or l2 <= 0.01:
		return
	var local: Vector3 = parent.global_transform.affine_inverse() * world_target
	var v: Vector3 = local - hip.position
	var d: float = v.length()
	if d < 0.02:
		return
	var dir: Vector3 = v / d
	d = clampf(d, absf(l1 - l2) + 0.06, (l1 + l2) * 0.995)

	var cos_knee: float = clampf((l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2), -1.0, 1.0)
	var flex: float = PI - acos(cos_knee)
	var cos_hip: float = clampf((l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d), -1.0, 1.0)
	var alpha: float = acos(cos_hip)

	var axis: Vector3 = Vector3.RIGHT - dir * Vector3.RIGHT.dot(dir)
	if axis.length_squared() < 1.0e-6:
		axis = Vector3.RIGHT
	axis = axis.normalized()
	var thigh_dir: Vector3 = dir.rotated(axis, alpha)
	var y_axis: Vector3 = -thigh_dir
	var z_axis: Vector3 = axis.cross(y_axis)
	if z_axis.length_squared() < 1.0e-6:
		return
	var want := Basis(axis, y_axis, z_axis.normalized())

	var w: float = clampf(weight, 0.0, 1.0)
	var from_q: Quaternion = hip.basis.get_rotation_quaternion()
	hip.basis = Basis(from_q.slerp(want.get_rotation_quaternion(), w))
	knee.rotation.x = lerpf(knee.rotation.x, -flex, w)


func _kick_thigh(s: float) -> float:
	if s < 0.55:
		var a: float = s / 0.55
		return -0.72 * (a * a * (3.0 - 2.0 * a))
	if s < 1.0:
		# The strike itself: the hip accelerates, it does not ease.
		var b: float = (s - 0.55) / 0.45
		return lerpf(-0.72, 0.62, b * b)
	var c: float = clampf(s - 1.0, 0.0, 1.0)
	if c < 0.45:
		return lerpf(0.62, 1.05, sin(c / 0.45 * PI * 0.5))
	return lerpf(1.05, 0.10, smoothstep(0.45, 1.0, c))


func _kick_knee(s: float) -> float:
	if s < 0.55:
		var a: float = s / 0.55
		return lerpf(0.10, 1.20, a * a * (3.0 - 2.0 * a))
	if s < 1.0:
		# The whip: the shin snaps straight exactly at contact.
		var b: float = (s - 0.55) / 0.45
		return lerpf(1.20, 0.22, b * b)
	var c: float = clampf(s - 1.0, 0.0, 1.0)
	if c < 0.5:
		return lerpf(0.22, 0.85, c / 0.5)
	return lerpf(0.85, 0.20, smoothstep(0.5, 1.0, c))


func _plant_thigh(s: float) -> float:
	if s < 1.0:
		return lerpf(0.42, 0.05, smoothstep(0.0, 1.0, s))
	return lerpf(0.05, -0.12, clampf(s - 1.0, 0.0, 1.0))


func _plant_knee(s: float) -> float:
	if s < 0.7:
		return lerpf(0.26, 0.10, s / 0.7)
	if s < 1.0:
		# The plant leg absorbs the landing just before contact.
		return lerpf(0.10, 0.32, (s - 0.7) / 0.3)
	return lerpf(0.32, 0.20, clampf(s - 1.0, 0.0, 1.0))


func _strike_lean(s: float) -> float:
	if s < 1.0:
		return lerpf(0.17, 0.24, s)
	return lerpf(0.24, 0.10, clampf(s - 1.0, 0.0, 1.0))


func _strike_side_lean(s: float) -> float:
	# Leaning away from the kicking side is what opens the hip. Leaning back on
	# top of it is what sends the ball over the bar, so it follows the aim.
	var base: float = 0.16 + 0.10 * clampf(aim.y, 0.0, 1.3)
	return base * smoothstep(0.2, 1.0, s)


func _strike_bob(s: float) -> float:
	if s < 1.0:
		return lerpf(-0.010, -0.055, smoothstep(0.4, 1.0, s))
	return lerpf(-0.055, -0.015, clampf(s - 1.0, 0.0, 1.0))


func _ankle_angle(s: float, knee: float) -> float:
	# Toes pointed through the ball, then relaxed.
	if _contacted or s > 0.6:
		return -0.35 + knee * 0.20
	return -0.12


# --- Input helpers ----------------------------------------------------------

func _pressed(action: StringName) -> bool:
	if not _actions_ready:
		return false
	return Input.is_action_pressed(action)


func _axis(neg: StringName, pos: StringName) -> float:
	if not _actions_ready:
		return 0.0
	return Input.get_action_strength(pos) - Input.get_action_strength(neg)


# --- Autoload access without naming the singletons --------------------------

func _game_node() -> Node:
	if _game != null and is_instance_valid(_game):
		return _game
	if not is_inside_tree():
		return null
	_game = get_tree().root.get_node_or_null(^"Game")
	return _game


func _shootout_node() -> Node:
	if _shootout != null and is_instance_valid(_shootout):
		return _shootout
	if not is_inside_tree():
		return null
	_shootout = get_tree().root.get_node_or_null(^"Shootout")
	return _shootout


func _setting_float(key: String, fallback: float) -> float:
	var g: Node = _game_node()
	if g == null:
		return fallback
	var v: Variant = g.get(key)
	if typeof(v) == TYPE_FLOAT or typeof(v) == TYPE_INT:
		return float(v)
	return fallback


func _setting_int(key: String, fallback: int) -> int:
	var g: Node = _game_node()
	if g == null:
		return fallback
	var v: Variant = g.get(key)
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return int(v)
	return fallback


func _round_index() -> int:
	var s: Node = _shootout_node()
	if s == null:
		return 0
	var v: Variant = s.get("round_index")
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return int(v)
	return 0


## Seed of the current attempt: same campaign seed and same round give the same
## marker phase and the same tells, which is what makes a replay honest.
func _attempt_seed() -> int:
	return _mix(_setting_int("seed_value", 20260824), _round_index() * 7919 + 17)


## Seed handed to ShotModel.resolve. The release point and the feints go in, so
## two identical looking strikes with a different release do not share a spray.
func _shot_seed() -> int:
	var h: int = _attempt_seed()
	h = _mix(h, int(round(_release * 4096.0)))
	h = _mix(h, int(round(power * 4096.0)) + feints * 1013)
	return h


static func _mix(a: int, b: int) -> int:
	# Cheap 64 bit avalanche. Plain shifting exhausts the low bits and makes
	# consecutive rounds correlate, which shows up as a keeper that always dives
	# the same way.
	var h: int = (a * 0x9E3779B1) ^ (b + 0x7F4A7C15)
	h = (h ^ (h >> 15)) * 0x85EBCA6B
	h = (h ^ (h >> 13)) * 0xC2B2AE35
	return absi(h ^ (h >> 16)) & 0x7FFFFFFF
