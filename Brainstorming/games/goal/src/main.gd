class_name Main
extends Node3D
## The orchestrator, and the only module allowed to make the others talk.
##
## Every other script in this project is deliberately deaf to its neighbours: the
## ball does not know the keeper exists, the keeper never touches the score, the
## HUD never reads the world. That isolation is what let thirteen agents write
## them in parallel, and it is what keeps each of them testable on its own. The
## price is that somebody has to hold the wires, and that somebody is this file.
##
## Three things live here and nowhere else.
##
## 1. The shot state machine. The phase table in the contract (ACCUEIL,
##    PLACEMENT, VISEE, COURSE, VOL, VERDICT, REPLAY, FIN) is driven from
##    `_enter_phase` plus a real time clock. Phase entry is idempotent and always
##    goes through `Shootout.set_phase`, so the autoload and the scene can never
##    disagree about where we are.
##
## 2. Verdict resolution. This is subtler than it looks and the order matters:
##      - a keeper touch BEFORE the line latches ARRET, and nothing later undoes
##        it;
##      - a ball whose centre crosses z = 0 between the posts and under the bar
##        with no prior touch is BUT;
##      - a frame contact only REMEMBERS a POTEAU or a BARRE, it never ends the
##        flight, because a rebound that goes in is a goal and a rebound that
##        goes away is a post;
##      - anything else, once it leaves the built area or comes to rest, is
##        DEHORS (or the remembered frame verdict).
##    Resolution is latched once and only once per shot by `_resolve`.
##
##    THE REBOUND RULE, written out because it is the one people argue about: a
##    penalty is ONE attempt and it ends at the first thing the ball touches. A
##    keeper who got a hand to it has saved it, full stop. If the parry then
##    comes back off a post, off the turf or off his own body and rolls over the
##    line, that is a rebound, and a rebound cannot be scored in a shootout. So
##    ARRET stands and no later crossing can turn it into a goal. The physics
##    agrees rather than merely being overruled: `Ball._parry` always sends a
##    deflected ball back up the pitch, so this rule almost never has to argue
##    with the picture. `tests/smoke_probe.gd` asserts both halves, the verdict
##    and the ball's final position.
##
## 3. Flight bookkeeping. Ball emits signals, but this module does NOT depend on
##    them being emitted: it re-walks `Ball.flight_log` step by step and runs the
##    same geometry (`Field.sweep_frame`, `Field.cross_goal_plane`). Signals are
##    treated as extra evidence, folded into the same latches, which are all
##    idempotent. A shot therefore resolves correctly whichever side reports the
##    contact first.
##
##    The save test is the one exception, and it belongs to the ball: only the
##    ball knows the contact fraction of the segment it is sweeping, and only
##    there can a save be turned into a catch or a parry AT the point of contact
##    instead of one frame downstream. `Ball.keeper_probe` is wired to
##    `Keeper.attempt_save` in `_wire_signals`, and the answer comes back inside
##    the same physics step. Before that wiring existed the branch was dead, the
##    ball flew straight through the keeper, and a saved penalty finished in the
##    net under a correct "Arret du gardien".
##
## Presentation is deliberately part of the job here, because it is the only
## place with enough context to time it: the brief time scale dip that makes a
## 0.4 s penalty watchable, the camera shake on a frame ding, the crowd reaction,
## the replay orbit, and the ALTERNATION of a real shootout. That last one is a
## sequence, not an event: your kick, your replay, then a beat that belongs to
## the opponent alone, announced before it is taken. See RIVAL_BEAT_SECONDS.
##
## Two command line entry points, read from `OS.get_cmdline_user_args()`:
##   -- --smoke        boots the game and hands control to tests/smoke_probe.gd
##   -- --shot <dir>   plays a scripted sequence, writes screenshots, quits
## Both exist so the build can be judged without a human in front of it.

# --- Timing ------------------------------------------------------------------

## Seconds spent on the spot before the shooter takes the aim back.
const PLACEMENT_SECONDS := 0.8
## Seconds the verdict banner stays up before the replay or the next attempt.
const VERDICT_SECONDS := 2.2
## Same, but under the smoke probe, where nobody is watching the banner.
const PROBE_VERDICT_SECONDS := 0.3
## Seconds the RIVAL'S OWN BEAT lasts, and how far into it his kick lands.
##
## A shootout is dramatic because the turns alternate under pressure, and that
## structure used to be invisible here: the CPU attempt was fired halfway
## through the player's own verdict, so a toast reading "Tir adverse : BUT !"
## appeared on top of the banner still announcing the player's own result. Two
## results, one screen, no sense of a turn changing hands.
##
## The rival now gets a beat of his own, after the player's banner and after the
## replay. It opens with the turn ANNOUNCED and nothing decided (the camera cuts
## to the television view, the scoreboard slides in with the ADVERSAIRE row lit
## and says what is at stake), and only then, RIVAL_CALL_SECONDS later, is the
## kick taken and shown. The gap is the whole point: it is the second in which a
## real shootout is unbearable.
const RIVAL_BEAT_SECONDS := 2.6
const RIVAL_CALL_SECONDS := 0.9
## Same, under the smoke probe.
const PROBE_RIVAL_BEAT_SECONDS := 0.3
const PROBE_RIVAL_CALL_SECONDS := 0.1
## A flight that has not resolved by then is declared over, whatever happened.
const FLIGHT_TIMEOUT := 8.0
## Replay playback speed, and the extra seconds held on the final frame.
const REPLAY_RATE := 0.42
const REPLAY_TAIL := 0.7
## A ball that rattles around for four seconds would give a ten second replay at
## REPLAY_RATE. Only the interesting part is worth showing.
const REPLAY_MAX_SPAN := 2.2
## How far BEFORE the strike the replay is allowed to start, in seconds of the
## shot's own clock. A keeper who gambles leaves his line before contact, and
## that early commitment is the single most watchable thing in a penalty, so the
## replay rewinds far enough to catch it. Bounded because the run up itself is
## not interesting, only its last moment before the boot arrives.
const REPLAY_LEAD_MAX := 0.75

# --- Screenshot session ------------------------------------------------------

## The reticle the scripted goal is aimed at, and the one the run up beat leans
## towards, so the approach on the still belongs to the shot on the next one.
## ShotModel.aim_point maps aim.x over Field.GOAL_HALF plus a margin and aim.y
## from the turf to above the bar, so this is roughly (2.95 m, 2.02 m): high in
## the corner and comfortably under the bar.
const RUN_UP_AIM := Vector2(0.67, 0.65)
## How far into the run up the still is taken, as a fraction of the approach.
## Just past half is mid stride, both feet clear of the plant, which is the frame
## that reads as a man running rather than as a man standing at an angle.
const RUN_UP_STILL := 0.55

# --- Cinematics --------------------------------------------------------------

## Time scale applied at the strike, and on a hard impact during the flight.
const SLOWMO_STRIKE := 0.55
const SLOWMO_IMPACT := 0.32
## Time scale units recovered per REAL second. Engine.time_scale eases back to
## 1.0 at this rate, so the dip never becomes a permanent slow motion mode.
const SLOWMO_RECOVER := 0.85

# --- Shot resolution ---------------------------------------------------------

## Seconds between the verdict being decided and the banner, so the eye sees the
## net move or the glove land before the game tells it what happened.
const RESOLVE_DELAY_GOAL := 0.55
const RESOLVE_DELAY_OTHER := 0.32
## Debounce windows, in seconds, so one physical event is not reported twice by
## the ball signal and by our own sweep of the same step.
const FRAME_CONTACT_INTERVAL := 0.08
const NET_IMPULSE_INTERVAL := 0.06
## Where the clean contact window sits on the power bar for a scripted shot.
const DEFAULT_SWEET_CENTRE := 0.72

## Real seconds the tree keeps ticking, mixer silent, before the process exits.
##
## Stopping an `AudioStreamPlayer` only marks its playback for a fade out; the
## audio server finishes that fade on its own thread and unregisters the
## playback on a LATER main thread update. Calling `SceneTree.quit()` in the
## same frame as the last sound therefore ends the process with those playbacks,
## and with the `AudioStreamWAV` each one holds, still in the object database,
## which Godot reports as "N ObjectDB instances were leaked at exit".
## Measured on the dummy driver `--headless` runs on: draining 0 ms always
## leaks, 50 ms is flaky, 100 ms was always clean. This is triple that, and it
## is spent once, at shutdown.
const AUDIO_DRAIN_SECONDS := 0.35

# --- Scene nodes, read by tests/smoke_probe.gd -------------------------------

var pitch: Pitch
var stadium: Stadium
var goal_frame: GoalFrame
var ball: Ball
var keeper: Keeper
var shooter: Shooter
var rig: CameraRig
var sky: SkyController
var crowd: Crowd
var hud: Hud
var scoreboard: Scoreboard
var menu: MenuUi

## Milliseconds at boot, so the probe can reason about elapsed time.
var boot_msec: int
## The verdict of the last resolved shot, a Shootout.Verdict.
var last_verdict: int = Shootout.Verdict.DEHORS
## The last strike dictionary produced by ShotModel.resolve.
var last_shot: Dictionary = {}

# --- Private state -----------------------------------------------------------

var _world_env: WorldEnvironment = null
var _wired: bool = false
var _booted: bool = false
var _degraded: bool = false

## Phase actually entered by this node. Kept beside Shootout.phase so a phase
## change coming from the autoload and one coming from here cannot run the entry
## actions twice.
var _current_phase: int = -1
## Real (unscaled) seconds spent in the current phase.
var _phase_clock: float = 0.0

# Flight tracking.
var _flight_elapsed: float = 0.0
var _log_cursor: int = 0
var _last_point: Vector3 = Vector3.ZERO
var _resolved: bool = false
var _saved: bool = false
## True when the save that latched the verdict was a clean catch rather than a
## parry. Only the verdict line reads it.
var _last_save_caught: bool = false
var _crossed: bool = false
var _last_save_limb: String = ""
var _frame_verdict: int = -1
var _frame_part: int = 0
var _verdict_point: Vector3 = Vector3.ZERO
var _pending_delay: float = -1.0
var _last_frame_contact: float = -1.0
var _last_net_impulse: float = -1.0
var _net_bulge_peak: float = 0.0
var _rest_timer: float = 0.0
## Deepest point the ball reached inside the mouth, and how fast it got there.
## Used as the backstop that guarantees the net moves on a goal.
var _deepest_inside: Vector3 = Vector3.ZERO
var _deepest_velocity: Vector3 = Vector3.ZERO

# Replay. `_replay_t` is a position on the SHOT's clock, not a progress counter:
# it starts negative, at `_replay_from`, so the playback opens on the run up.
var _replay_t: float = 0.0
var _replay_from: float = 0.0
var _replay_span: float = 0.0
var _replay_centre: Vector3 = Vector3.ZERO
## Flight time at which the verdict was decided. The replay frames the keeper and
## the ball as they were at that instant, which is where the drama actually is.
var _verdict_t: float = 0.0

# Series. The VERDICT phase of a shootout is played in two beats, one per side,
# and `_verdict_beat` says which of them is on screen. See _enter_rival_beat.
const BEAT_PLAYER := 0
const BEAT_RIVAL := 1
var _player_won: bool = false
var _verdict_beat: int = BEAT_PLAYER
## Verdict of the rival's kick this round, or -1 while he has not taken it.
var _rival_verdict: int = -1
var _rival_shown: bool = false

# Input.
var _mouse_delta: Vector2 = Vector2.ZERO
var _paused: bool = false

# Entry points.
var _probe: Node = null
var _shot_dir: String = ""
## False under the probe and the screenshot session: no slow motion, no replay.
var _cinematic: bool = true
var _test_shot_index: int = 0

# --- Shutdown ----------------------------------------------------------------

## Exit code latched by quit_clean. Negative while the game is still running.
var _quit_code: int = -1
## Real seconds elapsed since the mixer was silenced.
var _quit_drain: float = 0.0


func _ready() -> void:
	boot_msec = Time.get_ticks_msec()
	process_mode = Node.PROCESS_MODE_ALWAYS

	_parse_command_line()
	_resolve_nodes()
	if _degraded:
		push_error("Main: la scene est incomplete, le jeu ne demarre pas.")
		return

	_build_world()
	_apply_settings()
	_wire_signals()
	_booted = true

	if _probe != null:
		add_child(_probe)
		return
	if not _shot_dir.is_empty():
		_run_shot_session()
		return

	_go(Shootout.Phase.ACCUEIL)


func _exit_tree() -> void:
	# A process that dies mid dip would otherwise leave the editor, or the next
	# run inside the same process, running at half speed.
	Engine.time_scale = 1.0


## Silences the mixer, then quits once the audio server has actually let go of
## its voices. THE ONLY exit path of the game: quitting on the spot strands the
## playbacks that were still sounding, see AUDIO_DRAIN_SECONDS. Idempotent, and
## safe to call from a paused tree.
func quit_clean(code: int) -> void:
	if _quit_code >= 0:
		return
	Engine.time_scale = 1.0
	var tree: SceneTree = get_tree()
	if tree == null:
		return
	# Quitting from the pause menu is a legal path, and a paused tree would never
	# tick the drain below.
	tree.paused = false
	Sfx.silence_all()
	_quit_drain = 0.0
	_quit_code = code


## Counts down AUDIO_DRAIN_SECONDS of real time with nothing playing, then ends
## the process. Nothing else runs while it drains.
func _drain_then_quit(delta: float) -> void:
	_quit_drain += delta
	if _quit_drain < AUDIO_DRAIN_SECONDS:
		return
	var tree: SceneTree = get_tree()
	if tree != null:
		tree.quit(_quit_code)


# =============================================================================
# Boot
# =============================================================================

func _parse_command_line() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var index := 0
	while index < args.size():
		var arg: String = args[index]
		if arg == "--smoke":
			_cinematic = false
			var script: Script = load("res://tests/smoke_probe.gd") as Script
			if script == null or not script.can_instantiate():
				push_error("Main: tests/smoke_probe.gd introuvable ou invalide.")
			else:
				var probe: Node = script.new() as Node
				if probe == null:
					push_error("Main: la sonde n'a pas pu etre instanciee.")
				else:
					probe.name = "SmokeProbe"
					probe.call("setup", self)
					_probe = probe
		elif arg == "--balance":
			# Same contract as --smoke: boot the real game, hand it over to a probe
			# under tests/. This one MEASURES the difficulty instead of asserting
			# it, so the keeper and the strike model can be tuned against numbers.
			_cinematic = false
			var balance_script: Script = load("res://tests/balance_probe.gd") as Script
			if balance_script == null or not balance_script.can_instantiate():
				push_error("Main: tests/balance_probe.gd introuvable ou invalide.")
			else:
				var balance: Node = balance_script.new() as Node
				if balance == null:
					push_error("Main: la sonde d'equilibrage n'a pas pu etre instanciee.")
				else:
					balance.name = "BalanceProbe"
					balance.call("setup", self)
					_probe = balance
		elif arg == "--shot":
			if index + 1 < args.size():
				index += 1
				_shot_dir = args[index]
			else:
				push_error("Main: --shot attend un dossier de destination.")
		index += 1


func _resolve_nodes() -> void:
	pitch = get_node_or_null(^"Pitch") as Pitch
	stadium = get_node_or_null(^"Stadium") as Stadium
	goal_frame = get_node_or_null(^"GoalFrame") as GoalFrame
	ball = get_node_or_null(^"Ball") as Ball
	keeper = get_node_or_null(^"Keeper") as Keeper
	shooter = get_node_or_null(^"Shooter") as Shooter
	rig = get_node_or_null(^"CameraRig") as CameraRig
	sky = get_node_or_null(^"Sky") as SkyController
	crowd = get_node_or_null(^"Crowd") as Crowd
	hud = get_node_or_null(^"Hud") as Hud
	scoreboard = get_node_or_null(^"Screens/Scoreboard") as Scoreboard
	menu = get_node_or_null(^"Screens/MenuUi") as MenuUi
	_world_env = get_node_or_null(^"WorldEnvironment") as WorldEnvironment

	var missing: PackedStringArray = PackedStringArray()
	if pitch == null: missing.append("Pitch")
	if stadium == null: missing.append("Stadium")
	if goal_frame == null: missing.append("GoalFrame")
	if ball == null: missing.append("Ball")
	if keeper == null: missing.append("Keeper")
	if shooter == null: missing.append("Shooter")
	if rig == null: missing.append("CameraRig")
	if sky == null: missing.append("Sky")
	if crowd == null: missing.append("Crowd")
	if hud == null: missing.append("Hud")
	if scoreboard == null: missing.append("Screens/Scoreboard")
	if menu == null: missing.append("Screens/MenuUi")
	if not missing.is_empty():
		push_error("Main: noeuds absents de scenes/main.tscn : %s" % ", ".join(missing))
		_degraded = true


## Build order is a dependency order, not an arbitrary one: the environment
## first so nothing renders under a null sky, then the static world, then the
## actors that sit on it, then the camera that frames them, then the interface
## that projects through that camera.
func _build_world() -> void:
	sky.build()
	if _world_env != null and _world_env.environment == null:
		push_warning("Main: WorldEnvironment sans Environment apres SkyController.build().")

	pitch.build()
	goal_frame.build()
	stadium.build()
	ball.build()
	keeper.build()
	shooter.build()
	rig.build()
	crowd.build()
	hud.build()
	scoreboard.build()
	menu.build()

	# The menus must keep running while the tree is paused, otherwise the pause
	# screen freezes with no way out. Same for this node, set in _ready().
	menu.process_mode = Node.PROCESS_MODE_ALWAYS
	scoreboard.process_mode = Node.PROCESS_MODE_ALWAYS
	hud.process_mode = Node.PROCESS_MODE_ALWAYS

	ball.place_on_spot()
	keeper.reset_to_line()
	shooter.reset_stance()
	goal_frame.settle_net()
	_last_point = ball.global_position
	_refresh_camera_link()


func _apply_settings() -> void:
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(Game.master_volume, 0.0001)))
	Sfx.set_muted(Game.muted)
	Sfx.set_ambience("crowd_ambience", -20.0)
	keeper.level = Game.keeper_level


func _wire_signals() -> void:
	if _wired:
		return
	_wired = true

	ball.struck.connect(_on_ball_struck)
	ball.frame_hit.connect(_on_ball_frame_hit)
	ball.net_hit.connect(_on_ball_net_hit)
	ball.ground_hit.connect(_on_ball_ground_hit)
	ball.crossed_line.connect(_on_ball_crossed_line)
	ball.came_to_rest.connect(_on_ball_came_to_rest)

	# THE SAVE HANDSHAKE, and it is the whole reason a save now changes what the
	# ball does. Ball.keeper_probe is answered INSIDE the ball's own physics step,
	# at the exact contact fraction of the swept segment, so the ball can be
	# gathered or parried at the point of contact instead of a frame later, from
	# here, once it is already 25 cm past the glove and sometimes over the line.
	# Nothing used to assign it: the whole branch in Ball was dead code, and a
	# saved penalty carried on into the net while the scoreboard said "arret".
	ball.keeper_probe = Callable(keeper, "attempt_save")
	ball.keeper_hold = Callable(keeper, "hold_point")

	keeper.saved.connect(_on_keeper_saved)
	keeper.dive_started.connect(_on_keeper_dive_started)
	keeper.landed.connect(_on_keeper_landed)

	shooter.aim_changed.connect(_on_aim_changed)
	shooter.charge_changed.connect(_on_charge_changed)
	shooter.run_up_started.connect(_on_run_up_started)
	shooter.feinted.connect(_on_feinted)
	shooter.struck.connect(_on_shooter_struck)

	menu.mode_chosen.connect(_on_mode_chosen)
	menu.resume_requested.connect(_on_resume_requested)
	menu.restart_requested.connect(_on_restart_requested)
	menu.quit_requested.connect(_on_quit_requested)

	Shootout.phase_changed.connect(_on_phase_changed)
	Shootout.shot_recorded.connect(_on_shot_recorded)
	Shootout.series_changed.connect(_on_series_changed)
	Shootout.match_finished.connect(_on_match_finished)
	Game.settings_changed.connect(_on_settings_changed)


# =============================================================================
# Phase machine
# =============================================================================

## Asks the autoload for a phase, then runs the entry actions once.
func _go(phase: int) -> void:
	if Shootout.phase != phase:
		Shootout.set_phase(phase)
	if _current_phase != phase:
		_enter_phase(phase)


## Jumps straight to a phase, for the probe.
func force_phase(phase: int) -> void:
	_go(phase)


func _on_phase_changed(_previous: int, current: int) -> void:
	if _current_phase != current:
		_enter_phase(current)


func _enter_phase(phase: int) -> void:
	_current_phase = phase
	_phase_clock = 0.0

	if phase != Shootout.Phase.VOL:
		Engine.time_scale = 1.0

	if phase == Shootout.Phase.ACCUEIL:
		_enter_accueil()
	elif phase == Shootout.Phase.PLACEMENT:
		_enter_placement()
	elif phase == Shootout.Phase.VISEE:
		_enter_visee()
	elif phase == Shootout.Phase.COURSE:
		_enter_course()
	elif phase == Shootout.Phase.VOL:
		_enter_vol()
	elif phase == Shootout.Phase.VERDICT:
		_enter_verdict()
	elif phase == Shootout.Phase.REPLAY:
		_enter_replay()
	elif phase == Shootout.Phase.FIN:
		_enter_fin()


func _enter_accueil() -> void:
	_set_mouse_captured(false)
	menu.open_home()
	scoreboard.hide_result()
	hud.set_dimmed(true)
	hud.show_verdict(-1, "")
	hud.set_preview(PackedVector3Array())
	rig.set_view(CameraRig.View.TELE)
	_refresh_camera_link()
	crowd.set_tension(0.2)
	stadium.set_excitement(0.2)


func _enter_placement() -> void:
	# A new round always opens on the player's own beat.
	_verdict_beat = BEAT_PLAYER
	_rival_verdict = -1
	_rival_shown = false
	_set_mouse_captured(true)
	menu.close()
	scoreboard.hide_result()
	hud.set_dimmed(false)
	hud.show_verdict(-1, "")
	hud.set_preview(PackedVector3Array())

	ball.place_on_spot()
	keeper.reset_to_line()
	keeper.level = Game.keeper_level
	shooter.reset_stance()
	goal_frame.settle_net()

	_reset_flight_state()
	rig.set_view(CameraRig.View.DERRIERE)
	_refresh_camera_link()

	hud.refresh_series()
	scoreboard.refresh()
	_update_tension(0.0)


func _enter_visee() -> void:
	_set_mouse_captured(true)
	hud.set_dimmed(false)
	hud.toast(Shootout.pressure_text(), 1.6)


func _enter_course() -> void:
	crowd.hush()
	keeper.read_shooter(shooter.cues())
	hud.set_preview(PackedVector3Array())


func _enter_vol() -> void:
	_reset_flight_state()
	rig.set_view(CameraRig.View.DERRIERE)
	_refresh_camera_link()
	hud.set_preview(PackedVector3Array())
	hud.set_charge(0.0, 0.0, DEFAULT_SWEET_CENTRE, false)
	if _cinematic:
		Engine.time_scale = SLOWMO_STRIKE


func _enter_verdict() -> void:
	if _verdict_beat == BEAT_RIVAL:
		_enter_rival_beat()
		return

	Engine.time_scale = 1.0
	# A ball in the keeper's gloves is already stopped, and halting it would LET
	# GO of it: it would hang in the air on the spot the hands happened to be at
	# while he gets up and walks them away from it. The whole point of the catch
	# is that it stays in his hands through the verdict and the replay.
	if not ball.held:
		ball.halt()
	# The keeper reacts. Nothing used to call this at all, so he simply unwound
	# out of his dive whatever had just happened. It matters more now: a keeper
	# who CAUGHT the ball gets up clutching it, both gloves on it, and the hold
	# point follows those gloves, so this is also how the ball ends up held
	# against his chest instead of dangling off one outstretched hand.
	# The ball itself is the last word on whether the save was a catch: the keeper
	# decided it, but only the ball knows whether the hold actually took (a build
	# with no `keeper_hold` wired degrades a catch to a parry, and the banner must
	# not then claim he is holding something that flew past him).
	_last_save_caught = _saved and ball.held
	keeper.celebrate(last_verdict)

	var detail: String = _verdict_detail(last_verdict, _verdict_point, _last_save_limb)
	hud.show_verdict(last_verdict, detail)
	hud.show_shot_stats(
		float(last_shot.get("speed", 0.0)) * 3.6,
		ball.curve_amount() * 100.0,
		float(last_shot.get("quality", 1.0)))
	hud.refresh_series()
	scoreboard.refresh()
	scoreboard.flash(2.0)

	crowd.react(last_verdict)
	stadium.react(last_verdict)

	if Shootout.is_goal(last_verdict):
		stadium.flash_burst(26)
		rig.add_shake(_shake(0.45))
		Sfx.play("whistle_short", -3.0)
		rig.set_view(CameraRig.View.BUT)
		_refresh_camera_link()
		_update_tension(1.0)
	else:
		_update_tension(0.35)


## The rival's own moment. The player's banner comes DOWN first: two results on
## one screen was the whole reason the CPU half of a shootout was unreadable.
## Then the camera cuts to the television view, the scoreboard slides in with the
## ADVERSAIRE row lit, and Shootout.pressure_text() says whose turn it is and
## what is at stake ("Au tour de l'adversaire", "L'adversaire doit marquer").
## Nothing is decided yet: _reveal_rival takes the kick a second later.
func _enter_rival_beat() -> void:
	Engine.time_scale = 1.0
	_rival_verdict = -1
	_rival_shown = false

	# The banner goes, the figures do not: `show_shot_stats` has no "hide", and
	# re-arming it with zeros would put a 0 km/h card on screen for four seconds,
	# which is a worse lie than a card about the player's own strike quietly
	# finishing its fade. The thing that actually collided was the banner.
	hud.show_verdict(-1, "")
	hud.set_preview(PackedVector3Array())
	hud.set_dimmed(false)
	hud.toast(Shootout.pressure_text(), _rival_beat_seconds())

	rig.set_view(CameraRig.View.TELE)
	_refresh_camera_link()

	hud.refresh_series()
	scoreboard.refresh()
	scoreboard.flash(_rival_beat_seconds())

	crowd.hush()
	Sfx.play("whistle_short", -12.0)


## Takes the rival's kick and shows what happened, once. The clock calls it, and
## so does a player who skips the beat, so it has to be idempotent: skipping the
## presentation must never skip the KICK, or the two rows of the scoreboard would
## quietly drift apart, which is exactly the class of bug this beat replaced.
func _reveal_rival() -> void:
	if _rival_shown:
		return
	_rival_shown = true

	# Shootout owns the rule. It returns -1 when the rival owes no kick, which is
	# the case that matters: nobody takes a penalty that cannot change the result.
	var verdict: int = Shootout.take_rival_kick()
	_rival_verdict = verdict
	if verdict < 0:
		return

	var scored: bool = Shootout.is_goal(verdict)
	hud.toast("Tir adverse : %s" % Shootout.verdict_label(verdict), _rival_beat_seconds())
	# This is the HOME crowd, so it reacts to the mirror image of the verdict: the
	# visitors scoring feels the way the player being saved feels, and the keeper
	# denying them feels the way a goal feels.
	var felt_as: int = Shootout.Verdict.ARRET if scored else Shootout.Verdict.BUT
	crowd.react(felt_as)
	stadium.react(felt_as)
	Sfx.play("crowd_groan" if scored else "crowd_roar", -5.0)
	if not scored:
		stadium.flash_burst(14)
		rig.add_shake(_shake(0.2))
	_update_tension(0.2 if scored else 0.9)

	hud.refresh_series()
	scoreboard.refresh()
	scoreboard.flash(maxf(_rival_beat_seconds() - _rival_call_seconds(), 0.4))


## Hands the turn over to the rival, or goes straight on when he owes no kick
## (training, defi, or a series the player's own attempt has just settled).
func _begin_rival_beat() -> void:
	if not Shootout.rival_to_kick():
		_next_attempt()
		return
	_verdict_beat = BEAT_RIVAL
	# The phase does not change, only the beat inside it, so the entry actions
	# have to be forced.
	_current_phase = -1
	_go(Shootout.Phase.VERDICT)


## The replay covers the whole interesting window, which is wider than the
## flight: it opens on the keeper's commitment during the run up (`_replay_from`
## is negative) and runs through to the ball settling in the net.
func _enter_replay() -> void:
	hud.set_dimmed(true)
	hud.set_preview(PackedVector3Array())
	_replay_span = minf(_flight_span(), REPLAY_MAX_SPAN)
	_replay_from = -clampf(_keeper_lead(), 0.0, REPLAY_LEAD_MAX)
	_replay_t = _replay_from
	_replay_centre = _replay_focus()
	rig.set_view(CameraRig.View.REPLAY)
	_refresh_camera_link()


func _enter_fin() -> void:
	Engine.time_scale = 1.0
	_set_mouse_captured(false)
	hud.set_dimmed(true)
	hud.show_verdict(-1, "")
	scoreboard.show_result(_player_won)
	rig.set_view(CameraRig.View.TELE)
	_refresh_camera_link()
	Sfx.play("whistle_long", -2.0)
	crowd.set_tension(1.0 if _player_won else 0.25)


# =============================================================================
# Frame loop
# =============================================================================

func _process(delta: float) -> void:
	if _quit_code >= 0:
		_drain_then_quit(delta)
		return
	if not _booted:
		return

	var real_delta: float = delta / maxf(Engine.time_scale, 0.05)
	_phase_clock += real_delta
	_ease_time_scale(real_delta)
	_poll_actions()

	sky.animate(delta)

	if _current_phase == Shootout.Phase.VISEE:
		_update_visee(delta)
	elif _current_phase == Shootout.Phase.COURSE:
		shooter.advance_run_up(delta)
		keeper.prepare(_phase_clock)
	elif _current_phase == Shootout.Phase.PLACEMENT:
		keeper.prepare(_phase_clock)
		if _phase_clock >= PLACEMENT_SECONDS:
			_go(Shootout.Phase.VISEE)
	elif _current_phase == Shootout.Phase.VERDICT:
		_update_verdict()
	elif _current_phase == Shootout.Phase.REPLAY:
		_update_replay(real_delta)

	_update_camera(delta)
	_mouse_delta = Vector2.ZERO


func _physics_process(delta: float) -> void:
	if not _booted or _quit_code >= 0:
		return
	if _current_phase == Shootout.Phase.VERDICT or _current_phase == Shootout.Phase.REPLAY:
		# The Verlet net keeps swinging after the whistle, and its deepest point
		# often lands a few steps into the banner. Keep watching it, because the
		# probe uses this peak as the proof that a goal really shook the cords.
		_net_bulge_peak = maxf(_net_bulge_peak, goal_frame.net_bulge())
		return
	if _current_phase != Shootout.Phase.VOL:
		return

	_flight_elapsed += delta
	# A held ball keeps logging, because the replay wants to see it carried down,
	# but those entries are the keeper's hand and not a flight: walking them would
	# offer the goal line and the net panels a ball that a diving glove can well
	# carry over the line, and there is nothing left to judge anyway.
	if not ball.held:
		_consume_flight(delta)
	_net_bulge_peak = maxf(_net_bulge_peak, goal_frame.net_bulge())

	if _pending_delay >= 0.0:
		_pending_delay -= delta / maxf(Engine.time_scale, 0.05)
		if _pending_delay <= 0.0:
			_pending_delay = -1.0
			_commit_verdict()
		return

	if _resolved:
		return

	# A ball that has stopped moving has told us everything it is going to.
	if ball.velocity.length() < 0.45 and _flight_elapsed > 0.35:
		_rest_timer += delta
		if _rest_timer > 0.35:
			_resolve_fallback(ball.global_position)
	else:
		_rest_timer = 0.0

	if _flight_elapsed > FLIGHT_TIMEOUT:
		push_warning("Main: vol non resolu apres %.1f s, verdict force." % FLIGHT_TIMEOUT)
		_resolve_fallback(ball.global_position)


func _ease_time_scale(real_delta: float) -> void:
	if not _cinematic:
		Engine.time_scale = 1.0
		return
	if _current_phase != Shootout.Phase.VOL:
		Engine.time_scale = 1.0
		return
	Engine.time_scale = move_toward(Engine.time_scale, 1.0, SLOWMO_RECOVER * real_delta)


func _update_visee(delta: float) -> void:
	shooter.handle_aim(delta, _mouse_delta * Game.mouse_sensitivity)
	keeper.prepare(_phase_clock)
	hud.set_spin(shooter.side_spin, shooter.lift_spin)
	if Game.show_trajectory:
		hud.set_preview(shooter.preview(40))
	else:
		hud.set_preview(PackedVector3Array())
	_update_tension(shooter.power)


## The two beats of a shootout verdict, in order: the player's own result alone
## on screen, then (after the replay) the rival's turn, announced and then taken.
func _update_verdict() -> void:
	if _verdict_beat == BEAT_RIVAL:
		if not _rival_shown and _phase_clock >= _rival_call_seconds():
			_reveal_rival()
		if _phase_clock >= _rival_beat_seconds():
			_next_attempt()
		return

	if _phase_clock >= _verdict_seconds():
		if _should_replay():
			_go(Shootout.Phase.REPLAY)
		else:
			_begin_rival_beat()


## One playhead drives both bodies. The ball only knows about the flight, so its
## clock is clamped to [0, span] and it simply waits on the spot through the run
## up; the keeper takes the raw value, negative included, because that is exactly
## the part of his dive that happens before the ball moves.
func _update_replay(real_delta: float) -> void:
	_replay_t += real_delta * REPLAY_RATE
	ball.seek_replay(clampf(_replay_t, 0.0, _replay_span))
	keeper.seek_replay(_replay_t)
	rig.orbit_replay(_replay_centre, _replay_t - _replay_from)
	if _replay_t >= _replay_span + REPLAY_TAIL:
		# The replay belongs to the player's own attempt, so the rival's turn
		# comes after it and not before: you, the replay of you, then them.
		_begin_rival_beat()


## Puts the replay playhead on an exact point of the shot's clock and redraws
## everything from it. Only the screenshot session uses this: waiting a number of
## real seconds and hoping the playhead has travelled far enough lands on a
## different moment on every machine, because the replay advances with the frame
## delta and the frame rate is not a constant.
func _seek_replay_to(t: float) -> void:
	_replay_t = t
	ball.seek_replay(clampf(t, 0.0, _replay_span))
	keeper.seek_replay(t)
	rig.orbit_replay(_replay_centre, t - _replay_from)


## The instant the dive is at full stretch, read out of the keeper's own pose log:
## the last sample still clearly off the turf. Not the top of the arc, which is
## earlier and still a folded body, but the moment the arm is out and the legs
## are trailing, which is the one that looks like a dive on a still.
func _replay_dive_still_t() -> float:
	var trace: Array[Dictionary] = keeper.pose_log
	var best_air: float = 0.0
	for entry in trace:
		best_air = maxf(best_air, float(entry.get("airborne", 0.0)))
	if best_air <= 0.01:
		# He never left the ground. The crossing is then the only moment worth a
		# frame, because that is where he and the ball were closest.
		return _verdict_t
	var floor_air: float = best_air * 0.6
	var out: float = _replay_span * 0.5
	for entry in trace:
		if float(entry.get("airborne", 0.0)) >= floor_air:
			out = float(entry.get("t", out))
	return out


## How far before the strike the keeper's own recording reaches, in seconds.
func _keeper_lead() -> float:
	var trace: Array[Dictionary] = keeper.pose_log
	if trace.is_empty():
		return 0.0
	return maxf(-float(trace[0].get("t", 0.0)), 0.0)


## What the replay orbits around. The drama of a penalty is the RELATIONSHIP
## between the keeper and the ball, so the camera is centred half way between
## them as they were when the verdict was decided, not on the ball alone: orbit
## the ball and a save shows a glove entering frame from off screen.
func _replay_focus() -> Vector3:
	var focus: Vector3 = _verdict_point
	var body: Vector3 = _keeper_centre_at(_verdict_t)
	if body != Vector3.ZERO:
		focus = (focus + body) * 0.5
	focus.y = clampf(focus.y, 0.85, 2.0)
	return focus


## Where the keeper's body was `t` seconds after the strike, from his pose log.
## Returns ZERO when nothing was recorded.
func _keeper_centre_at(t: float) -> Vector3:
	var trace: Array[Dictionary] = keeper.pose_log
	if trace.is_empty():
		return Vector3.ZERO
	var found: Dictionary = trace[0]
	for entry in trace:
		if float(entry.get("t", 0.0)) > t:
			break
		found = entry
	var centre: Variant = found.get("centre", null)
	if typeof(centre) != TYPE_VECTOR3:
		return Vector3.ZERO
	var out: Vector3 = centre
	return out


func _update_camera(delta: float) -> void:
	if _current_phase == Shootout.Phase.REPLAY:
		return
	var flying: bool = _current_phase == Shootout.Phase.VOL and ball.flying
	rig.track(ball.global_position, flying, delta)


func _update_tension(extra: float) -> void:
	var progress: float = clampf(
		float(Shootout.round_index) / float(maxi(Shootout.REGULATION_SHOTS, 1)), 0.0, 1.0)
	var level: float = clampf(0.25 + 0.45 * progress + 0.3 * clampf(extra, 0.0, 1.0), 0.0, 1.0)
	crowd.set_tension(level)
	stadium.set_excitement(level)


# =============================================================================
# Flight bookkeeping and verdict resolution
# =============================================================================

func _reset_flight_state() -> void:
	_flight_elapsed = 0.0
	_log_cursor = 0
	_last_point = ball.global_position
	_resolved = false
	_saved = false
	_last_save_caught = false
	_crossed = false
	_last_save_limb = ""
	_frame_verdict = -1
	_frame_part = 0
	_verdict_point = Field.SPOT
	_verdict_t = 0.0
	_pending_delay = -1.0
	_last_frame_contact = -1.0
	_last_net_impulse = -1.0
	_net_bulge_peak = 0.0
	_rest_timer = 0.0
	_deepest_inside = Vector3.ZERO
	_deepest_velocity = Vector3.ZERO


## Walks every physics step the ball actually took since the last frame. The log
## is preferred over the node position because it never skips a step, and a
## skipped step at 30 m/s is 25 cm of tunnelling straight through a glove.
func _consume_flight(delta: float) -> void:
	var trace: Array[Dictionary] = ball.flight_log
	if trace.size() >= 2:
		if _log_cursor < 1:
			_log_cursor = 1
		while _log_cursor < trace.size():
			var previous: Dictionary = trace[_log_cursor - 1]
			var current: Dictionary = trace[_log_cursor]
			var from_point: Vector3 = previous.get("position", _last_point)
			var to_point: Vector3 = current.get("position", from_point)
			var t_from: float = float(previous.get("t", 0.0))
			var t_to: float = float(current.get("t", t_from + delta))
			var step_spin: Vector3 = previous.get("spin", ball.spin)
			_step_segment(from_point, to_point, maxf(t_to - t_from, 0.0001), t_to, step_spin)
			_last_point = to_point
			_log_cursor += 1
		return

	# Fallback: no usable log, sample the node itself.
	var here: Vector3 = ball.global_position
	_step_segment(_last_point, here, delta, _flight_elapsed, ball.spin)
	_last_point = here


func _step_segment(from_point: Vector3, to_point: Vector3, dt: float, t_now: float, spin: Vector3) -> void:
	if not from_point.is_finite() or not to_point.is_finite():
		push_error("Main: position de ballon non finie, vol interrompu.")
		_resolve(Shootout.Verdict.DEHORS, Field.SPOT)
		return
	if from_point.distance_squared_to(to_point) < 1.0e-10:
		return

	var step_velocity: Vector3 = (to_point - from_point) / maxf(dt, 0.0001)

	# 1. The frame. It never ends the flight, it only leaves a memory.
	var frame: Dictionary = Field.sweep_frame(from_point, to_point)
	if bool(frame.get("hit", false)):
		var contact: Vector3 = frame.get("point", to_point)
		_register_frame(int(frame.get("part", Field.FRAME_NONE)), contact, step_velocity.length())

	# 2. The keeper, before the line and before the plane test.
	#
	# The dive itself is driven from here, every logged step, because the pose the
	# ball is about to be tested against has to be the pose of this instant.
	#
	# The SAVE TEST is not run from here any more. The ball asks the keeper
	# directly, inside its own physics step (see _wire_signals), which is the only
	# place the contact fraction of a swept segment is known and therefore the only
	# place a save can stop the ball where it was actually touched. Asking a second
	# time from here would test a segment the ball has already resolved, against a
	# pose that has moved on since. The fallback below only exists for a build
	# where the handshake was never wired: without it a save would simply vanish.
	if not _resolved and not _crossed:
		if keeper.track(from_point, step_velocity, spin, t_now):
			_on_keeper_committed()
		if not ball.keeper_probe.is_valid():
			var save: Dictionary = keeper.attempt_save(from_point, to_point)
			if bool(save.get("saved", false)):
				_register_save(String(save.get("limb", "")), save.get("point", to_point))

	# 3. The goal plane.
	if not _crossed:
		var cross: Dictionary = Field.cross_goal_plane(from_point, to_point)
		if bool(cross.get("crossed", false)):
			_crossed = true
			var point: Vector3 = cross.get("point", to_point)
			_verdict_point = point
			if Field.is_within_frame(point) and not _saved:
				_register_goal(point)

	# 4. The net, so the wave starts from the real point of contact. The
	# thresholds are deliberately generous (about 25 cm short of the cords):
	# at 30 m/s that is 8 ms of anticipation, invisible on screen, and it keeps
	# the wave from being missed entirely when the ball module stops the ball a
	# few centimetres shy of where this module expects the panel to be.
	if to_point.z < -Field.BALL_RADIUS and Field.is_within_frame(to_point):
		if to_point.z < _deepest_inside.z:
			_deepest_inside = to_point
			_deepest_velocity = step_velocity
		var back: bool = to_point.z <= -(Field.NET_DEPTH - Field.BALL_RADIUS - 0.28)
		var side: bool = absf(to_point.x) >= Field.GOAL_HALF - Field.BALL_RADIUS - 0.24
		if back or side:
			_register_net(to_point, step_velocity, t_now)

	# 5. Out of the built world.
	if Field.is_out_of_area(to_point) and not _resolved:
		_resolve_fallback(to_point)


func _register_frame(part: int, point: Vector3, speed: float) -> void:
	if part == Field.FRAME_NONE:
		return
	if _last_frame_contact >= 0.0 and _flight_elapsed - _last_frame_contact < FRAME_CONTACT_INTERVAL:
		return
	_last_frame_contact = _flight_elapsed
	_frame_part = part
	if part == Field.FRAME_BAR:
		_frame_verdict = Shootout.Verdict.BARRE
		Sfx.play_at("bar_ding", point, clampf(-14.0 + speed * 0.4, -14.0, 2.0))
	else:
		_frame_verdict = Shootout.Verdict.POTEAU
		Sfx.play_at("post_ding", point, clampf(-14.0 + speed * 0.4, -14.0, 2.0))
	Sfx.play("crowd_ooh", -6.0)
	rig.add_shake(_shake(0.6))
	if _cinematic:
		Engine.time_scale = minf(Engine.time_scale, SLOWMO_IMPACT)


func _register_save(limb: String, point: Vector3) -> void:
	if _saved or _resolved:
		return
	_saved = true
	_last_save_limb = limb
	# Whether the ball was gathered or pushed away is the keeper's own answer, and
	# he has already set it by the time this runs: `saved` is emitted from the end
	# of attempt_save, after the catch is decided.
	_last_save_caught = keeper.holding()
	# The contact sound belongs to the keeper, who is the only one who knows
	# whether it was a catch, a punch or a boot. Playing a second one from here
	# doubled every save, and it played the punch on a catch and the catch on a
	# boot, which is exactly backwards.
	rig.add_shake(_shake(0.5))
	if _cinematic:
		Engine.time_scale = minf(Engine.time_scale, SLOWMO_IMPACT)
	_resolve(Shootout.Verdict.ARRET, point)


func _register_goal(point: Vector3) -> void:
	if _resolved:
		return
	rig.add_shake(_shake(0.3))
	_resolve(Shootout.Verdict.BUT, point)


func _register_net(point: Vector3, velocity: Vector3, t_now: float) -> void:
	if _last_net_impulse >= 0.0 and t_now - _last_net_impulse < NET_IMPULSE_INTERVAL:
		return
	_last_net_impulse = t_now
	goal_frame.net_impulse(point, velocity)
	Sfx.play_at("net_ripple", point, -4.0)


## Latches the verdict once. Later evidence is ignored on purpose: a save before
## the line stays a save even if the loose ball rolls in afterwards.
func _resolve(verdict: int, point: Vector3) -> void:
	if _resolved:
		return
	_resolved = true
	last_verdict = verdict
	_verdict_point = point
	_verdict_t = _flight_elapsed
	_pending_delay = RESOLVE_DELAY_GOAL if Shootout.is_goal(verdict) else RESOLVE_DELAY_OTHER


## The end of a flight nobody claimed: a remembered frame contact if there was
## one, DEHORS otherwise.
func _resolve_fallback(point: Vector3) -> void:
	if _resolved:
		return
	if _frame_verdict >= 0:
		_resolve(_frame_verdict, point)
	else:
		_resolve(Shootout.Verdict.DEHORS, point)


func _commit_verdict() -> void:
	# The rippling net is the reward for a goal, so it is not allowed to be
	# missed. If the ball ended up inside the mouth and the cords never moved,
	# the panels and the ball disagreed by a few centimetres: push the wave from
	# the deepest point the ball actually reached.
	if Shootout.is_goal(last_verdict) and _deepest_inside.z < -Field.BALL_RADIUS:
		if goal_frame.net_bulge() < 0.002:
			goal_frame.net_impulse(_deepest_inside, _deepest_velocity)
			_net_bulge_peak = maxf(_net_bulge_peak, goal_frame.net_bulge())

	var record: Dictionary = {
		"verdict": last_verdict,
		"speed": float(last_shot.get("speed", ball.velocity.length())),
		"point": _verdict_point,
		"curve": ball.curve_amount(),
		"quality": float(last_shot.get("quality", 1.0)),
		"region": Field.mouth_region_name(_verdict_point),
		"net_bulge": _net_bulge_peak,
		"limb": _last_save_limb,
	}
	Shootout.record_shot(record)
	_go(Shootout.Phase.VERDICT)


func _verdict_seconds() -> float:
	return PROBE_VERDICT_SECONDS if _probe != null else VERDICT_SECONDS


func _rival_beat_seconds() -> float:
	return PROBE_RIVAL_BEAT_SECONDS if _probe != null else RIVAL_BEAT_SECONDS


func _rival_call_seconds() -> float:
	return PROBE_RIVAL_CALL_SECONDS if _probe != null else RIVAL_CALL_SECONDS


func _should_replay() -> bool:
	if _probe != null or not _shot_dir.is_empty():
		return false
	if not Game.show_replay:
		return false
	return _flight_span() > 0.12


func _flight_span() -> float:
	var trace: Array[Dictionary] = ball.flight_log
	if trace.is_empty():
		return 0.0
	var last: Dictionary = trace[trace.size() - 1]
	return maxf(float(last.get("t", 0.0)), 0.0)


## Where a round ends. `is_decided()` is asked for every mode, not just SEANCE:
## a Defi run also ends on it, and it is always false for free training.
func _next_attempt() -> void:
	if Shootout.phase == Shootout.Phase.FIN:
		return
	if Shootout.is_decided():
		_player_won = Shootout.player_goals() >= Shootout.rival_goals()
		_go(Shootout.Phase.FIN)
		return
	_go(Shootout.Phase.PLACEMENT)


## The line under the verdict banner. It is drawn on screen, so it is written in
## accented French. Console output (push_warning, push_error) stays ASCII: the
## Windows console code page turns accents into noise.
func _verdict_detail(verdict: int, point: Vector3, limb: String) -> String:
	if verdict == Shootout.Verdict.BUT:
		return "Dans la %s" % Field.mouth_region_name(point)
	if verdict == Shootout.Verdict.ARRET:
		if _last_save_caught:
			return "Captée dans les gants"
		if limb == "glove_left" or limb == "glove_right":
			return "Détournée du gant"
		if limb == "boot_left" or limb == "boot_right":
			return "Repoussée du pied"
		if limb == "centre":
			return "Bloquée sur le corps"
		return "Le gardien s'est couché du bon côté"
	if verdict == Shootout.Verdict.POTEAU:
		if _frame_part == Field.FRAME_POST_LEFT:
			return "Poteau gauche"
		return "Poteau droit"
	if verdict == Shootout.Verdict.BARRE:
		return "Sur la barre transversale"
	return "À côté : %s" % Field.mouth_region_name(point)


func _shake(amount: float) -> float:
	# Game.camera_shake is applied once, here. Nothing downstream re-applies it.
	return clampf(amount, 0.0, 1.0) * clampf(Game.camera_shake, 0.0, 1.0)


# =============================================================================
# Signal handlers
# =============================================================================

func _on_ball_struck(velocity: Vector3, spin: Vector3) -> void:
	var speed: float = velocity.length()
	var quality: float = float(last_shot.get("quality", 1.0))
	var id: String = "kick_hard"
	if bool(last_shot.get("miscue", false)) or quality < 0.45:
		id = "miscue"
	elif absf(spin.y) > 40.0:
		id = "kick_curl"
	elif speed < 22.0:
		id = "kick_soft"
	Sfx.play_at(id, ball.global_position, -1.0)
	pitch.add_scuff(Vector3(ball.global_position.x, 0.0, ball.global_position.z), 0.34)
	rig.add_shake(_shake(0.18))


func _on_ball_frame_hit(part: int, point: Vector3, speed: float) -> void:
	_register_frame(part, point, speed)


func _on_ball_net_hit(point: Vector3, velocity: Vector3) -> void:
	_register_net(point, velocity, _flight_elapsed)


func _on_ball_ground_hit(point: Vector3, speed: float) -> void:
	if speed > 2.0:
		Sfx.play_at("ball_bounce", point, clampf(-18.0 + speed * 0.5, -18.0, -2.0))
	pitch.add_scuff(Vector3(point.x, 0.0, point.z), 0.18)


## The `inside` flag is taken as a hint, never as the answer. `Field` offers two
## different tests and they disagree exactly here: `is_inside_mouth` demands the
## WHOLE ball past the line, which is false by definition at the plane itself,
## while `is_within_frame` asks the question that actually decides a goal (is
## this point between the posts and under the bar). A ball reporting its own
## crossing naturally uses the first one, so trusting the flag turned every top
## corner goal into a miss. The frame test is applied here instead.
func _on_ball_crossed_line(point: Vector3, inside: bool) -> void:
	if _crossed:
		return
	_crossed = true
	_verdict_point = point
	if (inside or Field.is_within_frame(point)) and not _saved:
		_register_goal(point)


func _on_ball_came_to_rest() -> void:
	if _current_phase == Shootout.Phase.VOL:
		_resolve_fallback(ball.global_position)


func _on_keeper_saved(limb: String, point: Vector3) -> void:
	_register_save(limb, point)


func _on_keeper_dive_started(_side: int, _height: int, gambled: bool) -> void:
	Sfx.play("keeper_grunt", -8.0)
	if gambled:
		rig.add_shake(_shake(0.12))


func _on_keeper_landed() -> void:
	Sfx.play_at("keeper_land", keeper.global_position, -8.0)
	pitch.add_scuff(Vector3(keeper.global_position.x, 0.0, maxf(keeper.global_position.z, 0.05)), 0.5)


func _on_keeper_committed() -> void:
	# Nothing audible here: the keeper announces itself through dive_started.
	# The hook exists so the camera can tighten the moment the dive begins.
	rig.add_shake(_shake(0.08))


func _on_aim_changed(aim: Vector2) -> void:
	var world_point: Vector3 = ShotModel.aim_point(aim)
	hud.set_aim(aim, world_point, Field.is_within_frame(world_point))


func _on_charge_changed(power: float, marker: float) -> void:
	hud.set_charge(power, marker, _sweet_centre(), true)


func _on_run_up_started() -> void:
	_go(Shootout.Phase.COURSE)


func _on_feinted(count: int) -> void:
	# A feint is new body language, so the keeper is allowed to read it again.
	keeper.read_shooter(shooter.cues())
	hud.toast("Feinte %d" % count, 0.9)
	Sfx.play("crowd_ooh", -10.0)


func _on_shooter_struck(shot: Dictionary) -> void:
	_begin_flight(shot)


func _on_mode_chosen(mode: int) -> void:
	Sfx.play("ui_select")
	_paused = false
	get_tree().paused = false
	Shootout.start_match(mode)
	menu.close()
	scoreboard.hide_result()
	Sfx.play("whistle_long", -4.0)
	_current_phase = -1
	_go(Shootout.Phase.PLACEMENT)


func _on_resume_requested() -> void:
	_set_paused(false)


func _on_restart_requested() -> void:
	_set_paused(false)
	Shootout.reset()
	Shootout.start_match(Shootout.mode)
	scoreboard.hide_result()
	_current_phase = -1
	_go(Shootout.Phase.PLACEMENT)


func _on_quit_requested() -> void:
	quit_clean(0)


func _on_shot_recorded(_record: Dictionary) -> void:
	hud.refresh_series()
	scoreboard.refresh()


func _on_series_changed() -> void:
	hud.refresh_series()
	scoreboard.refresh()


## The series is over. WHEN the end panel appears is a presentation decision and
## it belongs to the phase machine, not to the autoload: the rival's own kick can
## settle the tie, and cutting to the result screen on top of the banner
## announcing that kick would put two things on screen at once, which is the
## collision the rival beat exists to remove. The flag is latched here; the phase
## is reached through _next_attempt, once the beat has been read.
func _on_match_finished(player_won: bool) -> void:
	_player_won = player_won


func _on_settings_changed() -> void:
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(Game.master_volume, 0.0001)))
	Sfx.set_muted(Game.muted)
	keeper.level = Game.keeper_level


# =============================================================================
# Input
# =============================================================================

func _input(event: InputEvent) -> void:
	var motion := event as InputEventMouseMotion
	if motion != null:
		_mouse_delta += motion.relative


func _poll_actions() -> void:
	if Input.is_action_just_pressed("pause"):
		if menu.is_open() and _paused:
			_set_paused(false)
		elif _can_pause():
			_set_paused(true)
		return

	if menu.is_open():
		return

	if Input.is_action_just_pressed("camera_cycle"):
		rig.cycle_view()
		_refresh_camera_link()
		Sfx.play("ui_move", -6.0)

	if Input.is_action_just_pressed("restart"):
		_on_restart_requested()

	if _current_phase == Shootout.Phase.REPLAY:
		if Input.is_action_just_pressed("next_shot") or Input.is_action_just_pressed("replay"):
			_begin_rival_beat()
	elif _current_phase == Shootout.Phase.VERDICT:
		if Input.is_action_just_pressed("next_shot") and _phase_clock > 0.5:
			if _verdict_beat == BEAT_RIVAL:
				# Skipping the presentation must never skip the kick.
				_reveal_rival()
				_next_attempt()
			elif _should_replay():
				_go(Shootout.Phase.REPLAY)
			else:
				_begin_rival_beat()
	elif _current_phase == Shootout.Phase.FIN:
		if Input.is_action_just_pressed("next_shot"):
			menu.open_home()
			_go(Shootout.Phase.ACCUEIL)


func _can_pause() -> bool:
	return _current_phase == Shootout.Phase.PLACEMENT \
		or _current_phase == Shootout.Phase.VISEE \
		or _current_phase == Shootout.Phase.VERDICT \
		or _current_phase == Shootout.Phase.REPLAY


func _set_paused(paused: bool) -> void:
	_paused = paused
	get_tree().paused = paused
	if paused:
		menu.open_pause()
		_set_mouse_captured(false)
		Sfx.fade_ambience(-30.0, 0.3)
	else:
		menu.close()
		_set_mouse_captured(_current_phase != Shootout.Phase.ACCUEIL and _current_phase != Shootout.Phase.FIN)
		Sfx.fade_ambience(-20.0, 0.5)


## True when there is no window and no rendering: the mouse cannot be captured
## and nothing can be screenshotted.
func _headless() -> bool:
	return DisplayServer.get_name() == "headless"


func _set_mouse_captured(captured: bool) -> void:
	if _headless():
		return
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _refresh_camera_link() -> void:
	var camera: Camera3D = rig.camera()
	if camera == null:
		push_warning("Main: CameraRig.camera() est nul, le HUD ne peut pas projeter.")
		return
	camera.current = true
	hud.set_camera(camera)


## The shooter owns the clean contact window; the HUD needs to draw it. There is
## no getter in the contract, so we read the property when it exists and fall
## back to the scripted value otherwise.
func _sweet_centre() -> float:
	if shooter != null and "sweet_centre" in shooter:
		return float(shooter.get("sweet_centre"))
	return DEFAULT_SWEET_CENTRE


# =============================================================================
# Scripted shots
# =============================================================================

func _begin_flight(shot: Dictionary) -> void:
	last_shot = shot
	_current_phase = -1
	_go(Shootout.Phase.VOL)

	var velocity: Vector3 = shot.get("velocity", Vector3.ZERO)
	var spin: Vector3 = shot.get("spin", Vector3.ZERO)
	if not velocity.is_finite() or velocity.length() < 0.01:
		push_error("Main: frappe sans vitesse exploitable, tir annule.")
		_resolve(Shootout.Verdict.DEHORS, Field.SPOT)
		return

	ball.strike(velocity, spin)
	_last_point = ball.global_position
	_log_cursor = 0


## Forces a whole shot from code, bypassing the input. The probe uses it to fire
## reproducible penalties. Returns the strike dictionary.
func fire_test_shot(aim: Vector2, power: float, side: float, lift: float) -> Dictionary:
	_test_shot_index += 1
	var rng_seed: int = 1_402_000 + _test_shot_index * 7919

	# release == sweet_centre: a scripted shot is always a clean contact, so the
	# probe measures the keeper and the geometry, never the strike randomness.
	var shot: Dictionary = ShotModel.resolve(
		aim,
		clampf(power, 0.0, 1.0),
		clampf(side, -1.0, 1.0),
		clampf(lift, -1.0, 1.0),
		DEFAULT_SWEET_CENTRE,
		DEFAULT_SWEET_CENTRE,
		rng_seed)

	ball.place_on_spot()
	keeper.reset_to_line()
	shooter.reset_stance()
	goal_frame.settle_net()
	hud.show_verdict(-1, "")

	# The keeper gets the body language it would have read during the run up,
	# otherwise a scripted penalty faces a keeper with no opinion at all.
	var cues: Dictionary = ShotModel.tell_cues(aim, power, side, 0.0, 0, keeper.level)
	keeper.read_shooter(cues)

	_begin_flight(shot)
	return shot


# =============================================================================
# Probe support (private, used only by tests/smoke_probe.gd)
# =============================================================================

func _probe_begin_training() -> void:
	Shootout.reset()
	Shootout.start_match(Shootout.Mode.ENTRAINEMENT)
	_current_phase = -1
	_go(Shootout.Phase.PLACEMENT)


## Set in memory only, never through Game.set_setting: a test harness must not
## write the difficulty it happens to be probing into the player's saved
## settings file.
func _probe_set_keeper_level(level: int) -> void:
	var bounded: int = clampi(level, 0, 3)
	Game.keeper_level = bounded
	keeper.level = bounded


func _probe_world_ready() -> bool:
	return _booted and rig.camera() != null


func _probe_phase() -> int:
	return _current_phase


func _probe_phase_is_verdict() -> bool:
	return _current_phase == Shootout.Phase.VERDICT


func _probe_phase_is_placement() -> bool:
	return _current_phase == Shootout.Phase.PLACEMENT


## True while the world is in a settled, pre strike state: the ball is on the
## spot and no flight is running, so a scripted penalty can be fired safely.
func _probe_ready_to_fire() -> bool:
	if _current_phase != Shootout.Phase.PLACEMENT and _current_phase != Shootout.Phase.VISEE:
		return false
	return not ball.flying


func _probe_shot_settled() -> bool:
	return _resolved and _pending_delay < 0.0 and _current_phase == Shootout.Phase.VERDICT


func _probe_net_bulge_peak() -> float:
	return _net_bulge_peak


func _probe_recorded_count() -> int:
	return Shootout.player_scores.size()


func _probe_player_goals() -> int:
	return Shootout.player_goals()


func _probe_summary() -> Dictionary:
	return Shootout.summary()


func _probe_verdict_label(verdict: int) -> String:
	return Shootout.verdict_label(verdict)


func _probe_verdict_names() -> Dictionary:
	return {
		"BUT": Shootout.Verdict.BUT,
		"ARRET": Shootout.Verdict.ARRET,
		"POTEAU": Shootout.Verdict.POTEAU,
		"BARRE": Shootout.Verdict.BARRE,
		"DEHORS": Shootout.Verdict.DEHORS,
	}


# =============================================================================
# Screenshot session
# =============================================================================

## Plays a short scripted sequence and writes one PNG per beat, then quits. It
## exists so a build can be looked at without a human driving it.
func _run_shot_session() -> void:
	var directory: String = _shot_dir
	if DirAccess.make_dir_recursive_absolute(directory) != OK and not DirAccess.dir_exists_absolute(directory):
		push_error("Main: impossible de creer le dossier de captures %s" % directory)
		quit_clean(1)
		return

	_go(Shootout.Phase.ACCUEIL)
	await _wait(1.2)
	await _capture(directory, 1, "accueil")

	Shootout.start_match(Shootout.Mode.SEANCE)
	menu.close()
	_current_phase = -1
	_go(Shootout.Phase.PLACEMENT)
	await _wait(1.4)
	await _capture(directory, 2, "visee")

	# The run up. Every scripted penalty below goes through fire_test_shot, which
	# resets the stance and starts the flight on the spot, so the session used to
	# photograph a shooter standing with his arms hanging on every single still
	# and quietly claimed that was all his body ever did. He has a whole approach
	# animation - elbows and knees swinging through a stride - and this beat plays
	# THAT, through the real COURSE phase and the real advance_run_up, and stops
	# it before the boot arrives so the strike below stays the scripted one.
	await _run_up_beat()
	await _capture(directory, 3, "course")
	_end_run_up_beat()

	# ShotModel.aim_point maps aim.x over Field.GOAL_HALF plus a margin and aim.y
	# from the turf to above the bar, so (0.67, 0.65) is roughly (2.95 m, 2.02 m):
	# high in the corner, and comfortably under the bar.
	fire_test_shot(RUN_UP_AIM, 1.0, 0.0, 0.0)
	await _wait(0.22)
	await _capture(directory, 4, "vol")
	# On the verdict, not on a stopwatch. A penalty is watched in slow motion and
	# the previous PNG takes half a second to encode, so a fixed wait resolved the
	# shot on one machine and photographed a ball still in the air on the next,
	# with the three stills after it describing an attempt that was never even
	# recorded. This is the same lesson as _seek_replay_to, one beat earlier.
	await _wait_until_settled(10.0)
	await _wait(0.5)
	await _capture(directory, 5, "but")

	rig.set_view(CameraRig.View.BUT)
	_refresh_camera_link()
	await _wait(0.6)
	await _capture(directory, 6, "camera_but")

	# The replay is forced rather than waited for, so the session exercises the
	# orbit path on a known flight instead of depending on the settings. The
	# playhead is then parked on the top of the dive: a still taken after N real
	# seconds lands wherever the frame rate happens to have carried it, which is a
	# different moment on every machine, and usually not the interesting one.
	force_phase(Shootout.Phase.REPLAY)
	await _wait(0.4)
	_seek_replay_to(_replay_dive_still_t())
	await _capture(directory, 7, "replay")

	_current_phase = -1
	_go(Shootout.Phase.PLACEMENT)
	await _wait(1.0)
	_probe_set_keeper_level(KeeperBrain.Level.LEGENDE)
	# Placed at hip height and out towards the post rather than hammered down the
	# middle: a Legende gets a GLOVE to that one instead of blocking it with his
	# chest, and a glove on a placed ball is a clean catch. The still is meant to
	# show the ball ending up in the keeper's hands, which is the thing worth
	# photographing about a save. ShotModel.aim_point maps this reticle to about
	# (1.60 m, 1.05 m).
	fire_test_shot(Vector2(0.364, 0.321), 0.25, 0.0, 0.0)
	await _wait_until_settled(10.0)
	await _wait(0.5)
	await _capture(directory, 8, "arret")

	# The last still is the television view, and it deliberately lands inside the
	# RIVAL'S BEAT: the previous attempt left the CPU owing a kick, so this frame
	# carries the opponent's turn, his result and the two rows of the scoreboard
	# at once. That is the half of a shootout this session had no picture of.
	#
	# It waits on the STATE and not on a number of seconds, for the same reason
	# _seek_replay_to exists: the beat is driven by the frame clock, and encoding
	# the previous PNG alone eats half a second of it, so "wait N seconds" lands
	# on a different moment on every machine.
	rig.set_view(CameraRig.View.TELE)
	_refresh_camera_link()
	await _wait_for_rival_result(12.0)
	await _wait(0.4)
	await _capture(directory, 9, "tele")

	quit_clean(0)


## Plays the first half of a real run up and leaves the shooter in mid stride.
##
## `Shooter.running` is the flag `advance_run_up` gates on and COURSE is the
## phase that calls it once per frame, so this is the same approach the player
## drives, taken through the same code, with nothing scripted about the body.
## Aim and power are set first because the run angle, the plant offset and the
## body lean are all read off them: a run up towards a corner leans differently
## from one down the middle, and the still is meant to show that.
##
## The beat is measured in ELAPSED SECONDS OF RUN UP rather than waited on a
## timer, because it must stop before the boot arrives: contact would fire a shot
## the session never asked for, on top of the scripted one below.
func _run_up_beat() -> void:
	shooter.reset_stance()
	shooter.aim = RUN_UP_AIM
	shooter.power = 1.0
	shooter.running = true
	_current_phase = -1
	_go(Shootout.Phase.COURSE)
	var budget: float = Shooter.RUN_UP_TIME * RUN_UP_STILL
	while budget > 0.0 and shooter.running:
		await get_tree().process_frame
		budget -= maxf(get_process_delta_time(), 0.001)


## Puts him back on his mark, so the scripted strike that follows starts from the
## stance every other beat of the session starts from.
func _end_run_up_beat() -> void:
	shooter.running = false
	shooter.reset_stance()


func _wait(seconds: float) -> void:
	await get_tree().create_timer(seconds, true, false, true).timeout


## Blocks the screenshot session until the player's shot has actually resolved
## and the verdict is up.
func _wait_until_settled(timeout: float) -> void:
	var spent: float = 0.0
	while spent < timeout:
		if _probe_shot_settled():
			return
		await get_tree().process_frame
		spent += maxf(get_process_delta_time(), 0.001)
	push_warning("Main: le tir ne s'est pas resolu avant la capture.")


## Blocks the screenshot session until the rival's kick is actually on screen.
func _wait_for_rival_result(timeout: float) -> void:
	var spent: float = 0.0
	while spent < timeout:
		if _verdict_beat == BEAT_RIVAL and _rival_shown:
			return
		await get_tree().process_frame
		spent += maxf(get_process_delta_time(), 0.001)
	push_warning("Main: le tir adverse n'est pas arrive avant la capture.")


func _capture(directory: String, index: int, label: String) -> void:
	# RenderingServer.frame_post_draw is never emitted by the headless driver, so
	# awaiting it there would hang the session for ever instead of failing. The
	# sequence itself still runs headless, which makes --shot a usable end to end
	# smoke test of the whole shootout flow even with nothing to look at.
	if _headless():
		push_warning("Main: rendu headless, capture %d (%s) ignoree." % [index, label])
		await get_tree().process_frame
		return

	await RenderingServer.frame_post_draw
	var viewport: Viewport = get_viewport()
	if viewport == null:
		return
	var texture: Texture2D = viewport.get_texture()
	if texture == null:
		push_warning("Main: pas de texture de viewport, capture ignoree.")
		return
	var image: Image = texture.get_image()
	if image == null:
		push_warning("Main: capture vide (rendu headless ?).")
		return
	var path: String = directory.path_join("goal_%02d_%s.png" % [index, label])
	if image.save_png(path) != OK:
		push_error("Main: echec de l'ecriture de %s" % path)
