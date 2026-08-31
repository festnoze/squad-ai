class_name Hud
extends CanvasLayer
## In game overlay, drawn like a television broadcast rather than a debug panel.
##
## Everything here is painted by hand in a single `_draw`. There is no interface
## scene, no imported font and no texture: the whole overlay is vector work over
## `ThemeDB.fallback_font`. That is a deliberate constraint of the project (no
## binary asset), and it also buys a HUD that scales cleanly to any viewport.
##
## Three rules shape the layout:
##
##   1. The picture is a sunlit green pitch under a pale sky. Raw text over that
##      is unreadable, so every element carries its own contrast backing: a plate,
##      a gradient scrim at the frame edge, or at the very least a drop shadow.
##      Those backings are near solid, not the light veils a floodlit night would
##      have allowed: see the note on the colours below.
##   2. The centre of the frame belongs to the ball, and above all to the goal
##      mouth, where the ball is saved or scored. Persistent information sits at
##      the edges; the cards that report on a shot (the verdict, the figures) sit
##      in the top or the bottom band and never over the mouth, and they leave
##      again.
##   2b. Division of labour with the scoreboard (2.24): the scoreboard is the big
##      presentation panel that flashes in between two shots. The HUD only keeps a
##      small permanent series chip, and that chip fades out while the panel is on
##      screen, so the same numbers are never shown twice at once.
##   3. The power module is the input, not a readout, and it carries TWO numbers
##      that decide a penalty. They used to share one track, where a fill, a lit
##      green window and a sweeping needle all lived on the same 26 pixels, and a
##      player could not tell which of them meant power and which meant precision.
##      They are now two separate instruments on one card, deliberately drawn in
##      two different visual languages:
##        - PUISSANCE is a filled bar, a QUANTITY. Under it runs a graduation in
##          km/h, and because those graduations are evenly spaced in SPEED they
##          are not evenly spaced along the bar: they spread out towards the top,
##          which is `ShotModel.speed_for_power` being concave, drawn rather than
##          described. The stretch where an extra step of the bar buys less than
##          half of what the first steps bought is hatched and named GAIN FAIBLE.
##        - PRÉCISION is a thin pill with a moving needle, an INSTANT. Its
##          background is `ShotModel.contact_quality` itself, sampled column by
##          column, so the green gate, the amber shoulders either side of it and
##          the dead ends of the lane are the real strike quality and not a
##          decoration. The gate keeps the lit body, the posts and the pointers
##          that made it findable at a glance, and it is labelled RELÂCHEZ ICI.
##
##   4. When the player is the one in the goal (mode Duel), the whole set of
##      instruments is swapped rather than added to: `set_keeper_side()` puts the
##      reticle, the power module, the spin gauge and the trajectory arc away and
##      brings out the reach envelope, the tells, the commit prompt and the line
##      strip. The four rules that half lives under are written above the keeper
##      side constants, and the first of them is that the envelope owns the middle
##      of the frame.
##
## Engine trap this file is built around: a `Control` never redraws on its own
## when a variable changes, `queue_redraw()` must be called. And a `CanvasLayer`
## cannot draw at all, hence the `Painter` child below.
##
## Coordinates: the reticle and the trajectory preview are world points pushed
## through `Camera3D.unproject_position`, so they stick to the goal instead of
## floating in screen space.


## Immediate mode surface. The callback is stored as a `Callable` rather than as
## a typed reference back to `Hud`, which keeps the inner class free of a cyclic
## dependency on the script that declares it.
class Painter extends Control:
	var paint: Callable = Callable()

	func _draw() -> void:
		if paint.is_valid():
			paint.call(self)


# ---------------------------------------------------------------- visual system

## Ink.
const INK := Color(0.94, 0.96, 0.99)
const INK_SOFT := Color(0.78, 0.83, 0.90)
const INK_FAINT := Color(0.63, 0.68, 0.77)
## Backings. The whole set was authored against a floodlit night, where the pitch
## was dim and a 74 % plate was plenty. The match is played in full afternoon sun
## now: the turf behind these plates is the brightest thing in the picture, and a
## quarter of it coming through turns a backing into a pale green smear with the
## grass legible straight between the letters. Everything here is deeper and very
## nearly solid, and the sense of depth comes from the border and the drop shadow
## rather than from letting the pitch through.
const PLATE := Color(0.020, 0.029, 0.044, 0.94)
const PLATE_SOFT := Color(0.020, 0.029, 0.044, 0.76)
const TRACK := Color(0.008, 0.013, 0.021, 0.97)
## Bed of the timing lane. Lighter than TRACK on purpose: the lane sits on the
## card's own near black, and at TRACK it disappeared into it, so the needle read
## as travelling over nothing and the two ends of its run were invisible.
const LANE_BED := Color(0.055, 0.078, 0.115, 1.0)
## The power module's card, and the one backing that is fully OPAQUE. That module
## is what the player reads under pressure, and its sweet window is green: over
## turf the band that decides the strike was reading as camouflage. On solid near
## black it cannot.
const CARD := Color(0.013, 0.020, 0.033, 1.0)
const CARD_EDGE := Color(0.66, 0.76, 0.90, 0.40)
const BORDER := Color(0.62, 0.72, 0.86, 0.26)
const SHADOW := Color(0.0, 0.0, 0.0, 0.70)
## Meaning.
const ACCENT := Color(0.16, 0.72, 1.00)
const ACCENT_DEEP := Color(0.07, 0.34, 0.58)
const GOOD := Color(0.31, 0.87, 0.48)
const WARN := Color(1.00, 0.73, 0.18)
const BAD := Color(0.98, 0.33, 0.35)
const RIVAL := Color(0.99, 0.48, 0.28)

## Spacing, in reference pixels (multiplied by the viewport scale).
const MARGIN := 26.0
const PAD := 12.0
const PAD_S := 6.0
const GAP := 8.0
## Power bar geometry, shared with the spin gauge that docks against it.
const BAR_H := 26.0
## Height of the km/h graduation strip that runs under the power bar, and of the
## timing lane below it. The lane is deliberately much thinner than the bar: they
## are not the same kind of instrument and must not read as one.
const SCALE_H := 12.0
const LANE_H := 17.0
## Width of the timing lane as a share of the power bar's. See _power_layout.
const LANE_SPAN := 0.72
## Graduation step of the speed scale, km/h, and the step that also gets a
## number. Anything finer turns into a picket fence at the bottom of the bar.
const SPEED_TICK := 10
const SPEED_TICK_LABEL := 20
## A step of the bar is flagged as poor value once it buys less than this share
## of what the very first steps bought. It is measured off speed_for_power, never
## written down as a position, so the hatched stretch follows the real curve.
const GAIN_FLOOR := 0.5
## Columns the timing lane samples contact_quality over. Enough to look continuous
## at any width, few enough to stay a rounding error in the frame time.
const QUALITY_COLUMNS := 64
## Distance from the bottom edge of the frame to the bottom of the power card.
const BAR_LIFT := 34.0
## How far the sweeping needle overshoots the track, and the half width of its
## pointer. The card reserves room for both, so the rows above and below the
## track keep clear of the needle by construction rather than by luck.
const NEEDLE_OVER := 5.0
const NEEDLE_CAP := 5.5
## Height of the shot statistics card, in reference pixels.
const STATS_H := 54.0
## Room kept at the top of the frame for the scoreboard panel, which flashes in
## over the same seconds as the verdict banner (see 2.24).
const VERDICT_TOP_RESERVE := 178.0
## Corner radii.
const R_S := 4.0
const R := 8.0
const R_L := 13.0

## Type scale, as multipliers of `ThemeDB.fallback_font_size`.
const T_MICRO := 0.66
const T_SMALL := 0.82
const T_BODY := 1.0
const T_LEAD := 1.35
const T_TITLE := 2.0
const T_HERO := 3.8

## Reference viewport height the reference pixels above are authored against.
const REF_HEIGHT := 900.0

# ------------------------------------------------------------------- behaviour

## How much of the HUD survives `set_dimmed(true)`. Nearly nothing on purpose:
## the HUD is only dimmed when it is not in use (home menu, replay orbit, end
## screen), and a ghost of a card at 18 % over the picture reads as a rendering
## smear rather than as a faded interface.
const DIM_STRENGTH := 0.96
## The reticle fades out when nobody feeds it any more, which is exactly what
## happens the moment the ball is struck.
const AIM_HOLD := 0.25
const AIM_FADE := 0.35
## Comfortable distance from the frame, in metres, above which the reticle turns
## from "just inside" amber to a confident green.
const AIM_SAFE_MARGIN := 0.32
## Verdict banner timing, tuned against the 2.2 s VERDICT phase.
const VERDICT_IN := 0.22
const VERDICT_HOLD := 1.85
const VERDICT_OUT := 0.45
## Shot statistics panel timing.
const STATS_IN := 0.2
const STATS_HOLD := 3.6
const STATS_OUT := 0.6

## Mirrors Shootout.Mode. Copied rather than referenced so the HUD keeps drawing
## even when the autoload is absent (headless checks, isolated instancing).
const MODE_SEANCE := 0
const MODE_ENTRAINEMENT := 1
const MODE_DEFI := 2
## Appended, never inserted: the three shipped values are persisted by number.
const MODE_DUEL := 3
const MODE_GARDIEN := 4
const MODE_NAMES: PackedStringArray = ["Tirs au but", "Entraînement", "Défi", "Duel",
	"Entraînement gardien"]

## Row labels of the series chip. Short on purpose: the chip is a reminder, the
## scoreboard panel is the one that spells "ADVERSAIRE" out in full. A duel has
## two ROLES rather than two teams, and both of them are the player, so it gets
## its own pair: the second row is still the CPU's kicks, but they are the rounds
## the player stood in the goal for.
const ROW_LABELS: PackedStringArray = ["VOUS", "ADV."]
const ROW_LABELS_DUEL: PackedStringArray = ["TIREUR", "GARDIEN"]

## The line strip: the height above the turf it is projected from, how far it is
## dropped down the screen afterwards, and the room anything stacked in the middle
## of the frame leaves above it. Shared by the painter and by `_card_base`, which
## has to know where the strip landed before it can stack anything clear of it.
const STRIP_GROUND := 0.03
const STRIP_DROP := 22.0
const STRIP_CLEAR := 18.0

## Mirrors Shootout.REGULATION_SHOTS, used for layout only.
const REGULATION_SLOTS := 5
## Beyond this the strip scrolls to the most recent attempts.
const MAX_SLOTS := 9

## Fallback for Shootout.verdict_label, in Verdict order.
const VERDICT_LABELS: PackedStringArray = [
	"BUT !", "Arrêt du gardien", "Poteau !", "Barre !", "Hors cadre",
]

## Mirrors KeeperBrain.LEVEL_NAMES, for the keeper tag.
const LEVEL_NAMES: PackedStringArray = ["Débutant", "Confirmé", "Pro", "Légende"]

# ------------------------------------------------------------------ keeper side
#
# What the player sees while he is the one in the goal (mode Duel). Four rules,
# and the first of them is the mode:
#
#   1. THE ENVELOPE OWNS THE MIDDLE OF THE FRAME, and it is the only thing that
#      may. The layout rule above keeps report cards off the goal mouth because
#      the mouth is where the ball is saved; the envelope IS the mouth, drawn as
#      the part of it this body can still reach. Anywhere else on screen and the
#      player would have to look at two places at once during the four tenths of
#      a second where he has time for one.
#   2. IT SHRINKS, VISIBLY. It is restroked every frame from
#      KeeperInput.reach_outline, so it cannot drift away from the rule it draws.
#      A dashed GHOST of the same ring a moment ago is drawn behind it: the gap
#      between the two is the rate the window is closing at, which is the single
#      thing the player is deciding on, and it is legible on a frozen frame as
#      well as in motion.
#   3. THE TELLS ARE DRAWN AS TELLS, never as figures. A wedge, a foot mark, a
#      tilted bar. An unreliable cue is drawn WIDER and softer, never smaller: the
#      player has to be able to tell "I cannot read him" from "he is not going
#      there", and those are opposite pieces of information.
#   4. THE COMMIT PROMPT SAYS WHEN, NEVER WHERE. It carries the coverage left and
#      how far the window has closed, and nothing about the taker.

## Seconds between two envelope ghosts, on the HUD's own real time clock.
const REACH_GHOST_PERIOD := 0.40
## Coverage below which the envelope reads as amber, and below which it reads as
## red. Nothing about the rule, only about the ink: the numbers themselves come
## from KeeperInput.
const REACH_TIGHT := 0.30
const REACH_LOST := 0.14
## Reference size of the two keeper cards.
const TELLS_W := 280.0
const TELLS_H := 178.0
const COMMIT_W := 400.0
const COMMIT_H := 86.0
## Width of the coverage ring's own column inside the commit card. Sized off the
## word under the ring rather than off the ring: the caption is the wider of the
## two, and a column measured on the circle pushes the word out onto the turf.
const COMMIT_RING_COL := 92.0
## Half width of the mouth the tells card draws its miniature over, in metres.
const TELL_MOUTH_HALF := 4.10
## Seconds of real time after which an unfed dive reticle fades out. Longer than
## the shooting reticle's on purpose: this one is the player's only mark of where
## his own body is being sent, and a machine dropping to a frame a second must not
## take it away from him.
const DIVE_HOLD := 0.55
const DIVE_FADE := 0.40
## Seconds to spare above which a dive reads as comfortable, and below zero it is
## simply late. Read off KeeperInput.margin, which is in seconds.
const DIVE_SAFE := 0.055

# ------------------------------------------------------------------------ state

var _painter: Painter = null
var _font: Font = null
var _base_size: int = 16
var _clock: float = 0.0
## Wall clock the overlay animates on, in milliseconds. Zero until the first
## frame, which is what tells `_process` it has no previous stamp to subtract.
var _real_ms: int = 0

var _shootout: Node = null
var _game: Node = null
## The presentation panel, read only. The chip steps aside while it is showing.
var _board: Node = null

var _camera: Camera3D = null

var _aim: Vector2 = Vector2.ZERO
var _aim_world: Vector3 = Vector3.ZERO
var _aim_on_target: bool = false
var _aim_margin: float = 1.0
var _aim_age: float = 99.0

var _power: float = 0.0
var _marker: float = 0.0
var _sweet_centre: float = 0.5
var _bar_visible: bool = false

var _side_spin: float = 0.0
var _lift_spin: float = 0.0

var _preview: PackedVector3Array = PackedVector3Array()

var _verdict: int = -1
var _verdict_detail: String = ""
var _verdict_age: float = 0.0
var _verdict_active: bool = false

var _stat_speed: float = 0.0
var _stat_curve: float = 0.0
var _stat_quality: float = 0.0
var _stats_age: float = 0.0
var _stats_active: bool = false

var _toast_text: String = ""
var _toast_left: float = 0.0
var _toast_total: float = 1.0

var _dimmed: bool = false
var _dim_amount: float = 0.0
## False until the first `set_dimmed`, which is taken instantly rather than eased.
var _dim_settled: bool = false

var _mode: int = MODE_SEANCE
var _round: int = 0
var _player_marks: Array[int] = []
var _rival_marks: Array[int] = []
var _player_goals: int = 0
var _rival_goals: int = 0
var _pressure: String = ""
var _streak: int = 0
var _best_streak: int = 0
var _defi_points: int = 0

## --- Keeper side state (mode Duel) ------------------------------------------
## True while the player is the one in the goal. The taking instruments and the
## keeping ones are mutually exclusive, and this is the switch.
var _keeping: bool = false
## The reach envelope in WORLD space, exactly as KeeperInput.reach_outline gave
## it, plus the same ring a moment ago and its age.
var _reach: PackedVector3Array = PackedVector3Array()
var _reach_ghost: PackedVector3Array = PackedVector3Array()
var _ghost_age: float = 0.0
var _coverage: float = 0.0
## The eased copy the coverage ring is drawn from, so the ring never steps.
var _cover_shown: float = 0.0
var _committed: bool = false

var _dive_target: Vector3 = Vector3.ZERO
var _dive_margin: float = 0.0
var _dive_age: float = 99.0

## The last TakerAi.tells_at dictionary. Cues only, never a plan.
var _tells: Dictionary = {}

var _commit_open: bool = false
var _commit_urgency: float = 0.0

var _line_x: float = 0.0
var _line_limit: float = 0.9

var _plate_cache: Dictionary = {}

## Speed graduations of the power bar, computed once from ShotModel: each entry
## is {"p": float (position on the bar), "kmh": int, "label": bool}.
var _speed_marks: Array[Dictionary] = []
## Where the poor value stretch of the power bar starts, see GAIN_FLOOR. 1.0
## means there is none, which is what a linear power curve would give.
var _gain_floor_at: float = 1.0


func _ready() -> void:
	build()


## Creates the drawing surface and binds the shootout state. Idempotent.
func build() -> void:
	_font = ThemeDB.fallback_font
	_base_size = maxi(ThemeDB.fallback_font_size, 12)
	# Stamped here rather than left at zero: a zero stamp makes the first frame
	# contribute nothing to the overlay clock, and on a machine rendering one frame
	# a second that is a whole second of animation thrown away.
	_real_ms = Time.get_ticks_msec()
	_measure_power_curve()
	_bind_singletons()
	if _painter != null and is_instance_valid(_painter):
		refresh_series()
		set_process(true)
		return
	_painter = Painter.new()
	_painter.name = "Painter"
	_painter.paint = Callable(self, "_paint")
	_painter.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_painter.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_painter)
	_painter.resized.connect(_on_painter_resized)
	refresh_series()
	set_process(true)


## Aim reticle position and legality.
func set_aim(aim: Vector2, world_point: Vector3, on_target: bool) -> void:
	_aim = aim
	_aim_world = world_point
	_aim_on_target = on_target
	# Field owns the truth about the mouth, so the shade of the reticle comes
	# from the real signed distance and not from a screen space guess.
	_aim_margin = Field.mouth_margin(world_point)
	_aim_age = 0.0
	_redraw()


## Power bar state. `marker` is the sweeping precision cursor.
func set_charge(power: float, marker: float, sweet_centre: float, visible_bar: bool) -> void:
	_power = clampf(power, 0.0, 1.0)
	_marker = clampf(marker, 0.0, 1.0)
	_sweet_centre = clampf(sweet_centre, 0.0, 1.0)
	_bar_visible = visible_bar
	_redraw()


func set_spin(side: float, lift: float) -> void:
	_side_spin = clampf(side, -1.0, 1.0)
	_lift_spin = clampf(lift, -1.0, 1.0)
	_redraw()


## The predicted flight, in world space. Empty hides the arc.
func set_preview(points: PackedVector3Array) -> void:
	_preview = points
	_redraw()


## The camera used to project world points to the screen.
func set_camera(camera: Camera3D) -> void:
	_camera = camera
	_redraw()


## Big centred verdict banner. A negative verdict with no detail hides it.
func show_verdict(verdict: int, detail: String) -> void:
	if verdict < 0 and detail.is_empty():
		_verdict_active = false
		_redraw()
		return
	_verdict = verdict
	_verdict_detail = detail
	_verdict_age = 0.0
	_verdict_active = true
	_redraw()


## Post shot figures: speed in km/h, curve in cm, contact quality in [0, 1].
func show_shot_stats(speed_kmh: float, curve_cm: float, quality: float) -> void:
	_stat_speed = speed_kmh
	_stat_curve = curve_cm
	_stat_quality = clampf(quality, 0.0, 1.0)
	_stats_age = 0.0
	_stats_active = true
	_redraw()


## Refreshes the shootout markers and the pressure line.
func refresh_series() -> void:
	if _shootout == null or not is_instance_valid(_shootout):
		_bind_singletons()
	var src: Node = _shootout
	if src != null and is_instance_valid(src):
		_mode = _read_int(src, &"mode", MODE_SEANCE)
		_round = _read_int(src, &"round_index", 0)
		_player_marks = _read_marks(src, &"player_scores")
		_rival_marks = _read_marks(src, &"rival_scores")
		_streak = _read_int(src, &"streak", 0)
		_best_streak = _read_int(src, &"best_streak", 0)
		_defi_points = _read_int(src, &"defi_points", 0)
		_player_goals = _count_goals(_player_marks)
		_rival_goals = _count_goals(_rival_marks)
		_pressure = _call_string(src, &"pressure_text")
	_redraw()


## Fades the whole HUD, for the replay and the menus.
func set_dimmed(dimmed: bool) -> void:
	if _dimmed == dimmed and _dim_settled:
		return
	_dimmed = dimmed
	# The very first call lands during the boot frames, where the world is still
	# being generated and the HUD only gets a handful of frames before the home
	# screen is on show. Fading from there leaves a half lit chip sitting over the
	# menu, so the first state is taken as read instead of eased into.
	if not _dim_settled:
		_dim_settled = true
		_dim_amount = 1.0 if dimmed else 0.0
	_redraw()


## Transient message, centred, in French.
func toast(text: String, seconds: float = 2.0) -> void:
	_toast_text = text
	_toast_total = maxf(seconds, 0.2)
	_toast_left = _toast_total
	_redraw()


# ----------------------------------------------------------- keeper side (Duel)

## Switches the whole HUD between the taking instruments (reticle, power, spin,
## arc) and the keeping ones (envelope, tells, commit prompt, line strip).
##
## One call, and it CLEARS the set that is leaving. Half of each is a mess, and a
## stale trajectory arc hanging over a run up the player is trying to read, or a
## stale envelope sitting on the goal while he lines up his own penalty, is
## exactly what a switch like this exists to make impossible.
## Only the CHANGE does anything. An orchestrator that called this every frame
## would otherwise wipe the envelope's ghost before every redraw, and the ghost is
## the whole of what makes the shrink readable on a still frame.
func set_keeper_side(keeping: bool) -> void:
	if _keeping == keeping:
		return
	_keeping = keeping
	_preview = PackedVector3Array()
	_bar_visible = false
	_aim_age = 99.0
	_reach = PackedVector3Array()
	_reach_ghost = PackedVector3Array()
	_ghost_age = 0.0
	_coverage = 0.0
	_cover_shown = 0.0
	_committed = false
	_tells = {}
	_commit_open = false
	_commit_urgency = 0.0
	_dive_age = 99.0
	_line_x = 0.0
	_redraw()


## The reach envelope, in world space. Called every frame: this is the drawing
## that has to shrink in front of the player.
func set_reach(outline: PackedVector3Array, coverage: float, committed: bool) -> void:
	if outline.size() < 3:
		_reach = PackedVector3Array()
		_reach_ghost = PackedVector3Array()
	else:
		# The ghost is this same ring a fixed moment ago. Snapshotting it here, off
		# the ring that was actually drawn, is what keeps the two honest: the gap
		# between them is real loss of reach and not an animation.
		if not committed and _ghost_age >= REACH_GHOST_PERIOD and _reach.size() >= 3:
			_reach_ghost = _reach
			_ghost_age = 0.0
		_reach = outline
	if committed:
		# Once he has gone, the envelope is no longer a choice, so it stops
		# advertising a trade he can no longer make.
		_reach_ghost = PackedVector3Array()
	else:
		# The coverage is FROZEN on commit rather than followed down to zero. A
		# keeper who has left his feet does not cover a shrinking share of the goal,
		# he covers the share he chose to leave on: that number is what he decided
		# with, and it is the one worth still reading while the ball is in the air.
		_coverage = clampf(coverage, 0.0, 1.0)
	_committed = committed
	_redraw()


## Where the player is aiming his dive, and the seconds to spare on it.
func set_dive_aim(target: Vector3, margin: float) -> void:
	_dive_target = target
	_dive_margin = margin if is_finite(margin) else 0.0
	_dive_age = 0.0
	_redraw()


## The taker's body language as the player is ALLOWED to read it. This is a
## TakerAi.tells_at dictionary and nothing else: everything in it is already
## degraded, and nothing in it is the truth.
func set_tells(cues: Dictionary) -> void:
	_tells = cues.duplicate()
	_redraw()


## The commit prompt. Says when, never where.
func set_commit_prompt(open: bool, urgency: float) -> void:
	_commit_open = open
	_commit_urgency = clampf(urgency, 0.0, 1.0)
	_redraw()


## Where the keeper stands on his line, and how far he may travel.
func set_line_position(line_x: float, limit: float) -> void:
	_line_x = line_x if is_finite(line_x) else 0.0
	_line_limit = maxf(limit, 0.05)
	_redraw()


# ------------------------------------------------------------------ frame loop

## The overlay runs on REAL seconds, never on the frame step it is handed.
##
## Two reasons, and the second one is a bug this file used to have in the picture.
## First, this is broadcast furniture: the strike drops `Engine.time_scale` to
## 0.55 and an impact to 0.32, and a verdict card that holds three times longer
## because the world went into slow motion is wrong. `Main` already keeps its own
## phase clock in real seconds for exactly that reason.
## Second, and worse: `delta` is the SCALED and CLAMPED step. On a machine that
## is dropping frames, one frame can cover a second of real time and still arrive
## here as a fraction of it, so an eased fade advances by almost nothing per
## second of play. The whole HUD is behind that fade, and it was being drawn at
## half opacity over a sunlit pitch for seconds on end: exactly the washed out,
## barely legible overlay a still frame catches. Real time cannot get stuck.
func _process(_delta: float) -> void:
	if _painter == null or not is_instance_valid(_painter):
		return
	var now := Time.get_ticks_msec()
	var step := 0.0
	if _real_ms > 0:
		# Capped only against a real hitch (a shader compile, a window restored
		# after a minute). The cap is deliberately LARGER than any single animation
		# here: a tighter one would throttle the overlay on a machine that renders
		# one frame a second, which is the very case this clock exists for.
		step = clampf(float(now - _real_ms) * 0.001, 0.0, 1.0)
	_real_ms = now
	_clock += step
	_aim_age += step
	_dive_age += step
	_ghost_age += step
	# The coverage ring is eased and the envelope is not: the ring is a gauge and a
	# gauge that steps reads as broken, while the envelope is the rule itself and
	# smoothing THAT would be drawing a lie.
	_cover_shown = _approach(_cover_shown, _coverage, step * 12.0)
	_dim_amount = _approach(_dim_amount, 1.0 if _dimmed else 0.0, step * 7.0)
	# Below a pixel of difference the ease is finished. Left to run on, it leaves a
	# ghost of the interface sitting over the picture for ever.
	if absf(_dim_amount - (1.0 if _dimmed else 0.0)) < 0.004:
		_dim_amount = 1.0 if _dimmed else 0.0
	_painter.modulate.a = 1.0 - DIM_STRENGTH * _dim_amount
	if _toast_left > 0.0:
		_toast_left = maxf(_toast_left - step, 0.0)
	if _verdict_active:
		_verdict_age += step
		if _verdict_age > VERDICT_IN + VERDICT_HOLD + VERDICT_OUT:
			_verdict_active = false
	if _stats_active:
		_stats_age += step
		if _stats_age > STATS_IN + STATS_HOLD + STATS_OUT:
			_stats_active = false
	_painter.queue_redraw()


func _on_painter_resized() -> void:
	_redraw()


func _redraw() -> void:
	if _painter != null and is_instance_valid(_painter):
		_painter.queue_redraw()


# --------------------------------------------------------------------- painting

func _paint(c: Control) -> void:
	if _font == null:
		return
	var rect := Rect2(Vector2.ZERO, c.size)
	if rect.size.x < 32.0 or rect.size.y < 32.0:
		return
	var s := clampf(rect.size.y / REF_HEIGHT, 0.7, 1.9)
	_paint_scrims(c, rect, s)
	_paint_series(c, rect, s)
	_paint_tags(c, rect, s)
	if _keeping:
		# Reading order on the picture: what is left of the goal, then where the
		# body is, then where the dive is aimed, then the two cards at the bottom.
		_paint_reach(c, rect, s)
		_paint_line_strip(c, rect, s)
		_paint_dive_aim(c, rect, s)
		_paint_tells(c, rect, s)
		_paint_commit(c, rect, s)
	else:
		_paint_preview(c, rect, s)
		_paint_reticle(c, rect, s)
		_paint_power(c, rect, s)
		_paint_spin(c, rect, s)
	_paint_toast(c, rect, s)
	_paint_stats(c, rect, s)
	_paint_verdict(c, rect, s)


## Two soft gradients, top and bottom. They cost nothing and they are the reason
## small type stays readable when the camera swings onto the floodlit turf.
func _paint_scrims(c: Control, rect: Rect2, s: float) -> void:
	var top := Rect2(Vector2.ZERO, Vector2(rect.size.x, 132.0 * s))
	_gradient(c, top, Color(0.0, 0.02, 0.05, 0.42), Color(0.0, 0.02, 0.05, 0.0))
	var low_h := 168.0 * s
	var low := Rect2(Vector2(0.0, rect.size.y - low_h), Vector2(rect.size.x, low_h))
	var strength := 0.30 + (0.20 if _bar_visible else 0.0)
	_gradient(c, low, Color(0.0, 0.02, 0.05, 0.0), Color(0.0, 0.02, 0.05, strength))


## The permanent series chip. Deliberately small and quiet: the scoreboard panel
## owns the full presentation of the series, this is only the glanceable reminder
## of where the shootout stands while the player is aiming. It fades out entirely
## while that panel is on screen.
func _paint_series(c: Control, rect: Rect2, s: float) -> void:
	# Steeper than a straight complement: the chip is gone well before the panel has
	# finished sliding in, so the two never read as two copies of the same numbers.
	var alpha := clampf(1.0 - _panel_presence() * 2.4, 0.0, 1.0)
	if alpha <= 0.02:
		return
	var micro := _fs(T_MICRO, s)
	var body := _fs(T_BODY, s)
	var pad := 10.0 * s
	var pip_r := 4.5 * s
	var pip_gap := 5.0 * s
	var two_rows := _two_rows()
	var labels := _row_labels()
	var rows := 2.0 if two_rows else 1.0
	var slots := mini(maxi(REGULATION_SLOTS, maxi(_player_marks.size(),
			_rival_marks.size())), MAX_SLOTS)
	var pips_w := float(slots) * pip_r * 2.0 + float(maxi(slots - 1, 0)) * pip_gap
	# The label column is measured, never guessed: a fixed column runs the longer
	# label straight into the markers as soon as the font changes.
	var label_w := maxf(_tracked_width(labels[0], micro, 0.8 * s),
			_tracked_width(labels[1], micro, 0.8 * s)) + 7.0 * s
	var tag := _series_tag()
	var score := _series_score()
	var tag_w := _tracked_width(tag, micro, 1.3 * s)
	var score_w := _text_width(score, body)
	var head_h := float(body) + 5.0 * s
	var row_h := 16.0 * s
	var w := maxf(tag_w + 18.0 * s + score_w, label_w + pips_w) + pad * 2.0
	var h := pad * 0.6 + head_h + row_h * rows + pad * 0.45
	var origin := Vector2(MARGIN * s, MARGIN * s)
	var plate_rect := Rect2(origin, Vector2(w, h))
	_plate(c, plate_rect, R * s, _fade(PLATE, alpha), _fade(BORDER, alpha), 6.0 * s)

	var head_y := origin.y + pad * 0.6
	_tracked(c, Vector2(origin.x + pad, head_y + (head_h - float(micro)) * 0.5 - 1.0 * s),
			tag, micro, _fade(INK_SOFT, alpha), 1.3 * s)
	_text(c, Vector2(plate_rect.end.x - pad - score_w, head_y - 1.0 * s), score, body,
			_fade(INK, alpha))
	var rule_y := head_y + head_h - 1.0 * s
	c.draw_line(Vector2(origin.x + pad, rule_y), Vector2(plate_rect.end.x - pad, rule_y),
			_fade(Color(BORDER.r, BORDER.g, BORDER.b, 0.34), alpha), 1.0, true)

	# The single row of a training session is the CPU'S KICKS, drawn in his colour:
	# the player takes none of his own in that mode, so the row that means anything
	# is the one he stood in front of. Same reasoning as the scoreboard panel.
	var keeping := _mode == MODE_GARDIEN
	var row_y := head_y + head_h
	_paint_series_row(c, Vector2(origin.x + pad, row_y), labels[0],
			_rival_marks if keeping else _player_marks,
			slots, pip_r, pip_gap, label_w, row_h, RIVAL if keeping else ACCENT, alpha, s)
	if two_rows:
		_paint_series_row(c, Vector2(origin.x + pad, row_y + row_h), labels[1],
				_rival_marks, slots, pip_r, pip_gap, label_w, row_h, RIVAL, alpha, s)

	# The pressure line belongs to the scoreboard. Only the Defi figures, which the
	# panel never shows, get a line of their own here.
	if _mode == MODE_DEFI:
		var line := "%d pts  ·  record %d" % [_defi_points, _best_streak]
		_note(c, Vector2(origin.x, plate_rect.end.y + GAP * s), line, _fs(T_SMALL, s),
				_fade(INK_SOFT, alpha), alpha, s)


func _paint_series_row(c: Control, origin: Vector2, label: String, marks: Array[int],
		slots: int, pip_r: float, pip_gap: float, label_w: float, row_h: float,
		tone: Color, alpha: float, s: float) -> void:
	var micro := _fs(T_MICRO, s)
	var mid := origin.y + row_h * 0.5
	# The row is told apart by the colour of its own label, which costs no width.
	_tracked(c, Vector2(origin.x, mid - _font.get_ascent(micro) * 0.62), label, micro,
			_fade(tone.lerp(INK, 0.35), alpha * 0.95), 0.8 * s)

	# Sudden death can push past the chip, so only the most recent attempts stay.
	var first := maxi(marks.size() - slots, 0)
	var x := origin.x + label_w + pip_r
	for i in slots:
		var index := first + i
		var state := 0
		if index < marks.size():
			state = 1 if _is_goal(marks[index]) else 2
		_pip(c, Vector2(x, mid), pip_r, state, tone, alpha, s)
		x += pip_r * 2.0 + pip_gap


## A shootout marker: pending ring, scored disc, or missed cross.
func _pip(c: Control, centre: Vector2, r: float, state: int, tone: Color, alpha: float,
		s: float) -> void:
	c.draw_arc(centre + Vector2(0.0, 1.0 * s), r, 0.0, TAU, 18, _fade(SHADOW, alpha),
			1.6 * s, true)
	match state:
		1:
			c.draw_circle(centre, r, _fade(tone, alpha))
			c.draw_circle(centre - Vector2(0.0, r * 0.30), r * 0.34,
					Color(1.0, 1.0, 1.0, 0.35 * alpha))
		2:
			var col := _fade(Color(BAD.r, BAD.g, BAD.b, 0.95), alpha)
			c.draw_arc(centre, r, 0.0, TAU, 20, _fade(Color(BAD.r, BAD.g, BAD.b, 0.55),
					alpha), 1.3 * s, true)
			var d := r * 0.52
			c.draw_line(centre + Vector2(-d, -d), centre + Vector2(d, d), col, 1.5 * s, true)
			c.draw_line(centre + Vector2(-d, d), centre + Vector2(d, -d), col, 1.5 * s, true)
		_:
			c.draw_arc(centre, r, 0.0, TAU, 20, _fade(Color(INK_FAINT.r, INK_FAINT.g,
					INK_FAINT.b, 0.50), alpha), 1.3 * s, true)


## True when the series has two sides worth a row of markers. A duel has two,
## like a shootout, except that both of them are the player.
func _two_rows() -> bool:
	return _mode == MODE_SEANCE or _mode == MODE_DUEL


func _row_labels() -> PackedStringArray:
	# Training has one row and it is the keeping one, so it borrows the duel's
	# second label for its first.
	if _mode == MODE_GARDIEN:
		return PackedStringArray([ROW_LABELS_DUEL[1], ROW_LABELS_DUEL[1]])
	return ROW_LABELS_DUEL if _mode == MODE_DUEL else ROW_LABELS


## Left hand tag of the chip header: where the series stands.
func _series_tag() -> String:
	if _mode == MODE_DEFI:
		return "SÉRIE %d" % _streak
	# `round_index` counts the player's OWN attempts, and he takes none in a keeper
	# session: the count comes off the row that is growing.
	if _mode == MODE_GARDIEN:
		return "TIR %d" % (_rival_marks.size() + 1)
	if _two_rows():
		if _round >= REGULATION_SLOTS:
			return "MORT SUBITE"
		return "TIR %d / %d" % [_round + 1, REGULATION_SLOTS]
	return "TIR %d" % (_round + 1)


## Right hand figure of the chip header: the one number worth a glance.
func _series_score() -> String:
	if _mode == MODE_DEFI:
		return "%d pts" % _defi_points
	# Saves out of penalties faced. A keeper is not judged on goals.
	if _mode == MODE_GARDIEN:
		return "%d / %d" % [_count_saves(_rival_marks), _rival_marks.size()]
	if _two_rows():
		return "%d - %d" % [_player_goals, _rival_goals]
	return "%d / %d" % [_player_goals, _player_marks.size()]


## How much of the scoreboard panel is currently on screen, 0 when it is away.
## Read through `has_method` so the HUD survives being instanced without it.
func _panel_presence() -> float:
	if _board == null or not is_instance_valid(_board):
		return 0.0
	if not _board.has_method(&"panel_presence"):
		return 0.0
	var v: Variant = _board.call(&"panel_presence")
	if typeof(v) == TYPE_FLOAT or typeof(v) == TYPE_INT:
		return clampf(float(v), 0.0, 1.0)
	return 0.0


func _paint_tags(c: Control, rect: Rect2, s: float) -> void:
	var micro := _fs(T_MICRO, s)
	var small := _fs(T_SMALL, s)
	var level := clampi(_read_int(_game, &"keeper_level", 1), 0, LEVEL_NAMES.size() - 1)
	var title := "GARDIEN"
	var value := LEVEL_NAMES[level]
	var pad := PAD * s
	var w := maxf(_tracked_width(title, micro, 1.6 * s), _text_width(value, small)) + pad * 2.0
	var h := pad * 1.4 + micro + small
	var origin := Vector2(rect.size.x - MARGIN * s - w, MARGIN * s)
	# Full strength plate, not the soft one: on the television framing this tag
	# lands on floodlit turf, where a 40 % backing leaves the value unreadable.
	_plate(c, Rect2(origin, Vector2(w, h)), R * s, PLATE, BORDER, 6.0 * s)
	_tracked(c, origin + Vector2(pad, pad * 0.55), title, micro, INK_FAINT, 1.6 * s)
	_text(c, origin + Vector2(pad, pad * 0.55 + micro * 1.15), value, small, INK)


## The predicted flight, projected and faded along its length. It is the only
## element allowed to sit in the middle of the frame while aiming, because it is
## the thing the player is actually reading.
func _paint_preview(c: Control, rect: Rect2, s: float) -> void:
	if _preview.size() < 2:
		return
	if not _read_bool(_game, &"show_trajectory", true):
		return
	if _camera == null or not is_instance_valid(_camera):
		return
	var pts := PackedVector2Array()
	for i in _preview.size():
		var world := _preview[i]
		if _camera.is_position_behind(world):
			break
		var p := _camera.unproject_position(world)
		if absf(p.x) > 1.0e5 or absf(p.y) > 1.0e5:
			break
		pts.append(p)
	if pts.size() < 2:
		return
	var last := float(pts.size() - 1)
	for i in pts.size() - 1:
		var t := float(i) / last
		var fade := pow(1.0 - t, 1.15)
		var col := ACCENT.lerp(WARN, clampf(t * 1.3, 0.0, 1.0))
		col.a = 0.15 + 0.65 * fade
		var width := lerpf(4.4 * s, 1.3 * s, t)
		c.draw_line(pts[i] + Vector2(0.0, 1.5 * s), pts[i + 1] + Vector2(0.0, 1.5 * s),
				Color(0.0, 0.0, 0.0, 0.22 * fade), width, true)
		c.draw_line(pts[i], pts[i + 1], col, width, true)
	var tip: Vector2 = pts[pts.size() - 1]
	c.draw_arc(tip, 5.0 * s, 0.0, TAU, 20, Color(WARN.r, WARN.g, WARN.b, 0.55), 1.6 * s, true)


func _paint_reticle(c: Control, rect: Rect2, s: float) -> void:
	if _camera == null or not is_instance_valid(_camera):
		return
	var fade := 1.0 - clampf((_aim_age - AIM_HOLD) / AIM_FADE, 0.0, 1.0)
	if fade <= 0.01:
		return
	if _camera.is_position_behind(_aim_world):
		return
	var p := _camera.unproject_position(_aim_world)
	if absf(p.x) > 1.0e5 or absf(p.y) > 1.0e5:
		return

	var tone := BAD
	if _aim_on_target:
		tone = GOOD if _aim_margin <= -AIM_SAFE_MARGIN else WARN
	tone.a = fade
	var pulse := 1.0 + 0.05 * sin(_clock * 5.0)
	var r := 15.0 * s * pulse
	var spin := _clock * 0.35

	# Shadow pass first, so the reticle reads over the white paint of the lines.
	_reticle_shape(c, p + Vector2(1.5 * s, 1.5 * s), r, Color(0.0, 0.0, 0.0, 0.35 * fade),
			2.6 * s, spin, s)
	_reticle_shape(c, p, r, tone, 2.0 * s, spin, s)
	c.draw_circle(p, 2.2 * s, Color(tone.r, tone.g, tone.b, fade))
	if not _aim_on_target:
		var warn_r := r + 7.0 * s
		c.draw_arc(p, warn_r, 0.0, TAU, 32, Color(BAD.r, BAD.g, BAD.b, 0.25 * fade),
				1.2 * s, true)


func _reticle_shape(c: Control, p: Vector2, r: float, col: Color, width: float,
		phase: float, s: float) -> void:
	# Four arcs with gaps rather than a closed ring: it stays legible over busy
	# net cord and it never hides the exact pixel being aimed at.
	var span := TAU / 4.0
	var gap := deg_to_rad(22.0)
	for i in 4:
		var a0 := phase + float(i) * span + gap * 0.5
		c.draw_arc(p, r, a0, a0 + span - gap, 10, col, width, true)
	var inner := r - 5.0 * s
	var outer := r - 1.0 * s
	for i in 4:
		var a := phase + float(i) * span
		var dir := Vector2(cos(a), sin(a))
		c.draw_line(p + dir * inner, p + dir * outer, col, width * 0.8, true)


## Geometry of the whole power module: the card, the two instruments inside it,
## and the anchor the spin gauge docks against. One source of truth, read by
## every painter, so the parts can never drift apart.
##
## Reading order down the card: the PUISSANCE label and its figures, the power
## bar, the km/h graduations, then the timing lane with its needle clearance
## above and below, then the PRÉCISION label and the gate name. Each instrument
## is therefore touching its own labels and nothing else.
func _power_layout(rect: Rect2, s: float) -> Dictionary:
	var bw := clampf(rect.size.x * 0.30, 250.0 * s, 560.0 * s)
	var bh := BAR_H * s
	var pad := PAD * s
	var head_h := float(_fs(T_SMALL, s)) * 1.2
	var foot_h := float(_fs(T_MICRO, s)) * 1.2
	var scale_h := SCALE_H * s
	var lane_h := LANE_H * s
	var split := GAP * s
	# The needle only overshoots the lane now, so the power bar no longer pays for
	# a clearance it does not use, and the card grows by far less than the second
	# instrument costs.
	var clear := (NEEDLE_OVER + NEEDLE_CAP * 1.25 + 3.0) * s
	var card_w := bw + pad * 2.0
	var card_h := pad * 0.6 + head_h + bh + scale_h + split + clear + lane_h \
			+ clear + foot_h + pad * 0.6
	var card := Rect2(Vector2(rect.size.x * 0.5 - card_w * 0.5,
			rect.size.y - BAR_LIFT * s - card_h), Vector2(card_w, card_h))
	var bar := Rect2(Vector2(card.position.x + pad, card.position.y + pad * 0.6 + head_h),
			Vector2(bw, bh))
	var scale := Rect2(Vector2(bar.position.x, bar.end.y), Vector2(bw, scale_h))
	# Deliberately NARROWER than the power bar, and centred under it. Two tracks of
	# the same width stacked on top of each other invite the one reading the module
	# must never make, which is that the needle has to be lined up with the fill:
	# the two axes have nothing to do with each other. Different width, different
	# height, rounded ends instead of square: not the same instrument.
	var lane_w := bw * LANE_SPAN
	var lane := Rect2(Vector2(card.get_center().x - lane_w * 0.5, scale.end.y + split + clear),
			Vector2(lane_w, lane_h))
	return {"card": card, "bar": bar, "scale": scale, "lane": lane, "pad": pad,
			"head_h": head_h, "foot_h": foot_h}


## The input, not a readout. Everything it needs lives on ONE solid card, and the
## card is opaque for two reasons that were both measured on screen: over a
## sunlit pitch a translucent plate reads as a green smear with the grass legible
## between the letters, and the gate of the timing lane is green like the turf,
## so on grass the single most important band of the interface was camouflage.
##
## The card carries two instruments, never one. See the note at the top of the
## file for why, and what each of them is telling the truth about.
func _paint_power(c: Control, rect: Rect2, s: float) -> void:
	if not _bar_visible:
		return
	var geo := _power_layout(rect, s)
	var card: Rect2 = geo["card"]
	var pad: float = geo["pad"]
	_plate(c, card, R_L * s, CARD, CARD_EDGE, 12.0 * s)

	var micro := _fs(T_MICRO, s)
	var small := _fs(T_SMALL, s)
	var bar: Rect2 = geo["bar"]
	var lane: Rect2 = geo["lane"]

	# --- PUISSANCE: how hard, as a quantity ---------------------------------
	var head_y := card.position.y + pad * 0.6
	_tracked(c, Vector2(bar.position.x, head_y + 1.0 * s), "PUISSANCE", micro, INK_SOFT,
			1.6 * s)
	# The live speed, in the same km/h the shot report uses afterwards. It is the
	# number the bar is really buying, and watching it crawl at the top of the bar
	# is the concavity of speed_for_power told in words.
	var kmh := "%d km/h" % int(round(ShotModel.speed_for_power(_power) * 3.6))
	var pct := "%d %%" % int(round(_power * 100.0))
	var pct_w := _text_width(pct, small)
	_text(c, Vector2(bar.end.x - pct_w, head_y), pct, small, INK)
	_text(c, Vector2(bar.end.x - pct_w - GAP * s - _text_width(kmh, small), head_y),
			kmh, small, _fade(INK_SOFT, 0.95))
	_paint_power_bar(c, bar, s)
	var scale_strip: Rect2 = geo["scale"]
	_paint_speed_scale(c, scale_strip, bar, micro, s)

	# --- PRÉCISION: when, as an instant --------------------------------------
	# A hairline between the two instruments, so the card reads as two rows of one
	# panel and not as one tall gauge.
	var rule_y := scale_strip.end.y + (lane.position.y - scale_strip.end.y) * 0.42
	c.draw_line(Vector2(bar.position.x, rule_y), Vector2(bar.end.x, rule_y),
			Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.16), 1.0 * s, false)

	var half: float = ShotModel.SWEET_WIDTH
	var lo := clampf(_sweet_centre - half, 0.0, 1.0)
	var hi := clampf(_sweet_centre + half, 0.0, 1.0)
	var inside := _marker >= lo and _marker <= hi
	_paint_timing_lane(c, lane, lo, hi, inside, s)

	# Foot row: the name of the lane on the left, the instruction centred under
	# the gate it points at. Both sit right under the instrument they describe.
	var foot_y := card.end.y - pad * 0.6 - float(geo["foot_h"])
	# Left aligned on the same column as PUISSANCE: the two names of the module
	# stack, and the eye finds them in the same place every time.
	_tracked(c, Vector2(bar.position.x, foot_y + 1.0 * s), "PRÉCISION", micro, INK_SOFT,
			1.6 * s)
	var call := "RELÂCHEZ ICI"
	var cw := _tracked_width(call, micro, 1.4 * s)
	var gate_x := lane.position.x + lane.size.x * (lo + hi) * 0.5
	var min_x := bar.position.x + _tracked_width("PRÉCISION", micro, 1.6 * s) + GAP * s
	var cx := clampf(gate_x - cw * 0.5, min_x, bar.end.x - cw)
	var call_tone := GOOD.lerp(Color(1.0, 1.0, 1.0, 1.0), 0.70 if inside else 0.45)
	_tracked(c, Vector2(cx, foot_y), call, micro, call_tone, 1.4 * s)
	# A caret from the label back up to the gate, so the two are one object even
	# when the gate sits far to one side and the label had to be clamped.
	var a := 3.2 * s
	c.draw_colored_polygon(PackedVector2Array([
			Vector2(gate_x - a, foot_y - 1.0 * s), Vector2(gate_x + a, foot_y - 1.0 * s),
			Vector2(gate_x, foot_y - 4.6 * s)]), call_tone)


## The power bar itself: the track, the fill, and the hatched stretch where the
## bar has stopped paying for itself.
func _paint_power_bar(c: Control, bar: Rect2, s: float) -> void:
	_plate(c, bar, R_S * s, TRACK, Color(0.0, 0.0, 0.0, 0.0), 0.0)

	# Fill. The colour belongs to the POSITION on the bar, not to the current
	# charge: every point keeps its shade as the fill grows past it, so the bar is
	# a scale that can be learned rather than one block of colour that changes
	# meaning under the player. Deep blue to bright blue while the bar is still
	# buying speed, then a hard step to amber and on to red across the stretch that
	# is not. Interpolating one colour from blue to amber instead would spend the
	# middle of the bar in the grey both of them pass through.
	var fill_w := bar.size.x * _power
	if fill_w > 1.0:
		var floor_at := clampf(_gain_floor_at, 0.02, 1.0)
		var split := bar.size.x * floor_at
		var cheap := minf(fill_w, split)
		if cheap > 0.5:
			_gradient_h(c, Rect2(bar.position, Vector2(cheap, bar.size.y)),
					ACCENT_DEEP, ACCENT_DEEP.lerp(ACCENT, cheap / maxf(split, 1.0)))
		if fill_w > split:
			var over := (fill_w - split) / maxf(bar.size.x - split, 1.0)
			_gradient_h(c, Rect2(Vector2(bar.position.x + split, bar.position.y),
					Vector2(fill_w - split, bar.size.y)),
					WARN, WARN.lerp(BAD, clampf(over, 0.0, 1.0)))
		c.draw_rect(Rect2(bar.position, Vector2(fill_w, 2.0 * s)),
				Color(1.0, 1.0, 1.0, 0.18), true)
		c.draw_line(Vector2(bar.position.x + fill_w, bar.position.y),
				Vector2(bar.position.x + fill_w, bar.end.y), Color(1.0, 1.0, 1.0, 0.55),
				1.5 * s, true)

	# The poor value stretch, drawn OVER the fill so it is at its most visible
	# exactly when the player has charged into it. Diagonal hatching rather than a
	# flat wash: a wash reads as one more colour of the fill, hatching reads as a
	# warning laid on top of it.
	if _gain_floor_at < 0.999:
		var zone := Rect2(Vector2(bar.position.x + bar.size.x * _gain_floor_at, bar.position.y),
				Vector2(bar.size.x * (1.0 - _gain_floor_at), bar.size.y))
		c.draw_rect(zone, Color(0.0, 0.0, 0.0, 0.18), true)
		var step := 7.0 * s
		var x := zone.position.x - zone.size.y
		while x < zone.end.x:
			var x0 := maxf(x, zone.position.x)
			var y0 := zone.end.y - (x0 - x)
			var x1 := minf(x + zone.size.y, zone.end.x)
			var y1 := zone.end.y - (x1 - x)
			# Warm and LIGHT rather than black: the stretch has to read as flagged
			# even before the fill gets there, and black hatching on the empty track
			# is black on black.
			c.draw_line(Vector2(x0, y0), Vector2(x1, y1), Color(1.0, 0.86, 0.62, 0.20),
					1.6 * s, true)
			x += step
		c.draw_line(Vector2(zone.position.x, bar.position.y),
				Vector2(zone.position.x, bar.end.y), Color(WARN.r, WARN.g, WARN.b, 0.85),
				1.6 * s, true)
		var tag := "GAIN FAIBLE"
		var micro := _fs(T_MICRO, s)
		var tw := _tracked_width(tag, micro, 1.0 * s)
		if tw < zone.size.x - 6.0 * s:
			_tracked(c, Vector2(zone.get_center().x - tw * 0.5,
					zone.get_center().y - float(micro) * 0.60), tag, micro,
					Color(1.0, 0.92, 0.78, 0.92), 1.0 * s)


## The km/h graduation under the power bar. The marks are evenly spaced in SPEED,
## so where they crowd together the bar is cheap and where they spread apart it is
## expensive: that spacing IS speed_for_power, and it is the one thing about the
## power curve the player could never see before.
func _paint_speed_scale(c: Control, strip: Rect2, bar: Rect2, micro: int, s: float) -> void:
	if _speed_marks.is_empty():
		return
	var last_right := -1.0e9
	for mark in _speed_marks:
		var p := float(mark["p"])
		var x := bar.position.x + bar.size.x * p
		var major := bool(mark["label"])
		c.draw_line(Vector2(x, strip.position.y),
				Vector2(x, strip.position.y + (5.0 if major else 3.0) * s),
				Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.85 if major else 0.45),
				1.0 * s, false)
		if not major:
			continue
		var text := str(int(mark["kmh"]))
		var w := _text_width(text, micro)
		var tx := x - w * 0.5
		# The scale is only worth reading if no two numbers touch, and the ones that
		# would touch are always the crowded low end, where the story is already told
		# by the tick marks themselves.
		if tx < last_right + 4.0 * s or tx + w > strip.end.x:
			continue
		_text(c, Vector2(tx, strip.position.y + 5.0 * s), text, micro,
				Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.95), false)
		last_right = tx + w

	# The scale sits between the two instruments, so without its unit a reader can
	# take these numbers for positions on the timing lane just below rather than
	# for speeds on the power bar just above. Naming the unit at the right hand end
	# settles it, and the end is where the eye lands after reading the numbers left
	# to right. Only drawn when it fits without touching the last graduation.
	var unit := "km/h"
	var uw := _text_width(unit, micro)
	var ux := strip.end.x - uw
	if ux > last_right + 5.0 * s:
		_text(c, Vector2(ux, strip.position.y + 5.0 * s), unit, micro,
				Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.70), false)


## The timing lane: a thin pill whose background is the real contact_quality
## curve, with the clean gate lit inside it and the needle riding over the top.
func _paint_timing_lane(c: Control, lane: Rect2, lo: float, hi: float, inside: bool,
		s: float) -> void:
	var radius := lane.size.y * 0.5
	_plate(c, lane, radius, LANE_BED, BORDER, 0.0)

	# Quality shoulders, sampled from ShotModel itself: amber where a late release
	# still leaves something, dark where the strike is a shank. Nothing is invented
	# here, which is the whole point of drawing it.
	var col_w := lane.size.x / float(QUALITY_COLUMNS)
	for i in QUALITY_COLUMNS:
		var t := (float(i) + 0.5) / float(QUALITY_COLUMNS)
		if t >= lo and t <= hi:
			continue
		var q: float = ShotModel.contact_quality(t, _sweet_centre)
		if q <= 0.02:
			continue
		var tone := BAD.lerp(WARN, q)
		c.draw_rect(Rect2(Vector2(lane.position.x + col_w * float(i), lane.position.y),
				Vector2(col_w + 0.5, lane.size.y)),
				Color(tone.r, tone.g, tone.b, 0.16 + 0.50 * q), true)

	# The gate. Kept as a LIT GATE and not as an outline to be hunted for: a solid
	# body, a halo column overshooting the lane, two bright posts, and a brightening
	# the moment the needle is inside it.
	var band := Rect2(Vector2(lane.position.x + lane.size.x * lo, lane.position.y),
			Vector2(lane.size.x * maxf(hi - lo, 0.001), lane.size.y))
	var beat := 0.5 + 0.5 * sin(_clock * 9.0)
	var over := 7.0 * s
	var column := Rect2(Vector2(band.position.x, lane.position.y - over),
			Vector2(band.size.x, lane.size.y + over * 2.0))
	c.draw_rect(column.grow(3.0 * s), Color(GOOD.r, GOOD.g, GOOD.b,
			(0.20 if inside else 0.10) + 0.05 * beat), true)
	c.draw_rect(column, Color(GOOD.r, GOOD.g, GOOD.b, 0.30 if inside else 0.18), true)
	c.draw_rect(band, Color(GOOD.r, GOOD.g, GOOD.b, 0.92 if inside else 0.66), true)
	c.draw_rect(Rect2(band.position, Vector2(band.size.x, 2.2 * s)),
			Color(1.0, 1.0, 1.0, 0.30), true)
	# The posts stay clearly GREEN rather than going white: the needle is the white
	# thing on this lane, and two pale vertical lines side by side is exactly how a
	# player loses track of which one he is releasing on.
	var lip := GOOD.lerp(Color(1.0, 1.0, 1.0, 1.0), 0.34 if inside else 0.16)
	c.draw_rect(band, Color(lip.r, lip.g, lip.b, 1.0), false, 2.0 * s, true)
	var gate := Color(lip.r, lip.g, lip.b, 1.0 if inside else 0.85)
	c.draw_line(Vector2(band.position.x, column.position.y),
			Vector2(band.position.x, column.end.y), gate, 2.4 * s, true)
	c.draw_line(Vector2(band.end.x, column.position.y),
			Vector2(band.end.x, column.end.y), gate, 2.4 * s, true)

	# Sweeping needle, drawn last and brightest: it is what the player releases on.
	# Sheathed in black on both sides rather than shadowed to one side, because it
	# crosses the lit gate, where a plain white line all but vanishes.
	var mx := lane.position.x + lane.size.x * _marker
	var top := lane.position.y - NEEDLE_OVER * s
	var bottom := lane.end.y + NEEDLE_OVER * s
	c.draw_line(Vector2(mx, top), Vector2(mx, bottom), Color(0.0, 0.0, 0.0, 0.80), 5.6 * s, true)
	c.draw_line(Vector2(mx, top), Vector2(mx, bottom), INK, 2.4 * s, true)
	var cap := NEEDLE_CAP * s
	_needle_cap(c, Vector2(mx, top), cap, 1.0, 1.6 * s)
	_needle_cap(c, Vector2(mx, bottom), cap, -1.0, 1.6 * s)


## Reads the two facts the power bar has to tell the truth about straight off
## ShotModel, once, at build time: where each round speed lands on the bar, and
## where an extra step of bar stops being worth taking. Nothing here is a written
## down constant, so retuning the shot model retunes the drawing with it.
func _measure_power_curve() -> void:
	_speed_marks.clear()
	var lo: float = ShotModel.speed_for_power(0.0) * 3.6
	var hi: float = ShotModel.speed_for_power(1.0) * 3.6
	var kmh := int(ceil(lo / float(SPEED_TICK))) * SPEED_TICK
	while float(kmh) <= hi + 0.01 and _speed_marks.size() < 40:
		_speed_marks.append({
			"p": _power_for_speed(float(kmh)),
			"kmh": kmh,
			"label": kmh % SPEED_TICK_LABEL == 0,
		})
		kmh += SPEED_TICK

	# The reference slope is the one at the very bottom of the bar, so the flagged
	# stretch answers "compared with what the first steps bought", which is the
	# comparison a player actually makes.
	var reference := _speed_slope(0.0)
	_gain_floor_at = 1.0
	if reference > 0.0:
		var floor_slope := reference * GAIN_FLOOR
		for i in 101:
			var p := float(i) / 100.0
			if _speed_slope(p) < floor_slope:
				_gain_floor_at = p
				break


## Position on the bar of a given speed. Bisection, because speed_for_power is
## monotonic but has no closed form inverse.
func _power_for_speed(kmh: float) -> float:
	var lo := 0.0
	var hi := 1.0
	for _i in 24:
		var mid := (lo + hi) * 0.5
		if ShotModel.speed_for_power(mid) * 3.6 < kmh:
			lo = mid
		else:
			hi = mid
	return clampf((lo + hi) * 0.5, 0.0, 1.0)


## Metres per second bought by one unit of bar at this point of it.
func _speed_slope(p: float) -> float:
	var h := 0.005
	var a := clampf(p - h, 0.0, 1.0)
	var b := clampf(p + h, 0.0, 1.0)
	if is_equal_approx(a, b):
		return 0.0
	return (ShotModel.speed_for_power(b) - ShotModel.speed_for_power(a)) / (b - a)


## One solid pointer of the sweeping marker: a dark halo triangle under a bright
## one, so the needle keeps its shape over the lit sweet band. `dir` is +1 for the
## cap sitting above the track and -1 for the one below it.
func _needle_cap(c: Control, tip: Vector2, size: float, dir: float, halo: float) -> void:
	var back_y := tip.y - (size * 1.25 + halo) * dir
	c.draw_colored_polygon(PackedVector2Array([
			Vector2(tip.x - size - halo, back_y), Vector2(tip.x + size + halo, back_y),
			Vector2(tip.x, tip.y + halo * dir)]), Color(0.0, 0.0, 0.0, 0.72))
	var front_y := tip.y - size * 1.25 * dir
	c.draw_colored_polygon(PackedVector2Array([
			Vector2(tip.x - size, front_y), Vector2(tip.x + size, front_y), tip]), INK)


## Two axis gauge: horizontal is the curl, vertical is backspin over topspin.
## It docks against the power card and matches its height, so the pair reads as
## one instrument rather than as two floating widgets.
func _paint_spin(c: Control, rect: Rect2, s: float) -> void:
	if not _bar_visible:
		return
	var geo := _power_layout(rect, s)
	var card: Rect2 = geo["card"]
	var size := card.size.y
	var micro := _fs(T_MICRO, s)
	var origin := Vector2(card.end.x + GAP * s, card.position.y)
	if origin.x + size > rect.size.x - MARGIN * s:
		return
	var box := Rect2(origin, Vector2(size, size))
	_plate(c, box, R * s, CARD, CARD_EDGE, 10.0 * s)
	var head := float(micro) * 1.2 + 5.0 * s
	var plot := Rect2(Vector2(box.position.x, box.position.y + head),
			Vector2(box.size.x, box.size.y - head - 5.0 * s))
	var centre := plot.get_center()
	var half := minf(plot.size.x, plot.size.y) * 0.5 - 7.0 * s
	var grid := Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.34)
	c.draw_line(Vector2(centre.x - half, centre.y), Vector2(centre.x + half, centre.y),
			grid, 1.0 * s, true)
	c.draw_line(Vector2(centre.x, centre.y - half), Vector2(centre.x, centre.y + half),
			grid, 1.0 * s, true)
	c.draw_arc(centre, half * 0.55, 0.0, TAU, 24,
			Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.20), 1.0 * s, true)

	var tip := centre + Vector2(_side_spin, -_lift_spin) * half
	var amount := clampf(Vector2(_side_spin, _lift_spin).length(), 0.0, 1.0)
	var tone := ACCENT.lerp(WARN, amount)
	tone.a = 0.35 + 0.65 * amount
	c.draw_line(centre, tip, tone, 2.0 * s, true)
	c.draw_circle(tip, 4.2 * s, tone)
	c.draw_circle(tip, 1.7 * s, Color(1.0, 1.0, 1.0, 0.85))

	# The title sits inside the box, like every other label of the module: outside
	# it landed on the turf and vanished.
	var title_w := _tracked_width("EFFET", micro, 1.6 * s)
	_tracked(c, Vector2(box.get_center().x - title_w * 0.5, box.position.y + 4.0 * s),
			"EFFET", micro, INK_SOFT, 1.6 * s)
	var edge := Color(INK_SOFT.r, INK_SOFT.g, INK_SOFT.b, 0.85)
	_text(c, Vector2(plot.position.x + 4.0 * s, centre.y - micro * 0.5), "G", micro, edge, false)
	_text(c, Vector2(plot.end.x - 4.0 * s - _text_width("D", micro), centre.y - micro * 0.5),
			"D", micro, edge, false)
	var a := 3.4 * s
	c.draw_colored_polygon(PackedVector2Array([
			Vector2(centre.x - a, plot.position.y + 6.0 * s),
			Vector2(centre.x + a, plot.position.y + 6.0 * s),
			Vector2(centre.x, plot.position.y + 2.5 * s)]), edge)
	c.draw_colored_polygon(PackedVector2Array([
			Vector2(centre.x - a, plot.end.y - 6.0 * s),
			Vector2(centre.x + a, plot.end.y - 6.0 * s),
			Vector2(centre.x, plot.end.y - 2.5 * s)]), edge)


## Bottom edge of the broadcast stack: the line the transient cards are stacked
## up from. The power card owns the bottom of the frame while it is up, so the
## stack steps above it rather than through it.
func _card_base(rect: Rect2, s: float) -> float:
	if _bar_visible:
		var card: Rect2 = _power_layout(rect, s)["card"]
		return card.position.y - GAP * s
	if _keeping:
		# The commit prompt owns the bottom of the frame on the keeper side, exactly
		# as the power module owns it on the taking side.
		var base := rect.size.y - BAR_LIFT * s - COMMIT_H * s - GAP * s
		# AND THE LINE STRIP IS NOT LAID OUT, IT IS PROJECTED. It is drawn in world
		# space off the goal line, so it lands wherever the GARDIEN camera happens to
		# put it - which is straight through this column - and the pressure line came
		# out written across it, with the shot report half behind it underneath.
		# Anything stacked in the middle of the frame therefore starts above the
		# STRIP and not merely above the prompt.
		var strip := _strip_screen_y(s)
		if is_finite(strip):
			base = minf(base, strip - STRIP_CLEAR * s)
		# A camera that put the goal line high would otherwise push the stack off the
		# top of the frame. Half the screen is as far up as it may go.
		return maxf(base, rect.size.y * 0.5)
	return rect.size.y - MARGIN * s


## Screen y of the line strip, or INF when it cannot be projected. Read off the
## same point `_paint_line_strip` draws its middle from, so the layout and the
## drawing can never disagree about where the strip is.
func _strip_screen_y(s: float) -> float:
	var mid := _screen_of(Vector3(0.0, STRIP_GROUND, 0.04))
	if not mid.is_finite():
		return INF
	return mid.y + STRIP_DROP * s


## Height the verdict card settles at, used to stack the toast above it.
func _verdict_card_height(s: float) -> float:
	var hero := _fs(T_HERO, s)
	var h := _font.get_ascent(hero) + _font.get_descent(hero)
	if not _verdict_detail.is_empty():
		var lead := _fs(T_LEAD, s)
		h += 16.0 * s + _font.get_ascent(lead) + _font.get_descent(lead)
	return h + PAD * 2.0 * s


## Which of the two safe slots the verdict banner takes. The middle of the frame
## is where the ball is saved, scored or missed, so the banner never sits there:
## it goes above the action or below it, whichever is further from the goal mouth
## AS THE CURRENT CAMERA FRAMES IT. Behind the taker the mouth is high in the
## picture and the card drops low; from inside the net the mouth fills the bottom
## and the card rises. Projecting one world point is what keeps that honest when
## the director changes camera, which it does on every goal.
func _verdict_high(rect: Rect2) -> bool:
	if _camera == null or not is_instance_valid(_camera):
		return false
	var mouth := Vector3(0.0, Field.GOAL_HEIGHT * 0.5, 0.0)
	if _camera.is_position_behind(mouth):
		return false
	var p := _camera.unproject_position(mouth)
	if not p.is_finite() or rect.size.y <= 1.0:
		return false
	return p.y > rect.size.y * 0.5


func _paint_toast(c: Control, rect: Rect2, s: float) -> void:
	if _toast_left <= 0.0 or _toast_text.is_empty():
		return
	var elapsed := _toast_total - _toast_left
	var alpha := clampf(elapsed / 0.15, 0.0, 1.0) * clampf(_toast_left / 0.35, 0.0, 1.0) * _live()
	if alpha <= 0.01:
		return
	var size := _fs(T_BODY, s)
	var w := _text_width(_toast_text, size)
	var pad := PAD * s
	var h := float(size) + pad * 1.1
	# Stacked above whatever the shot has already put on screen, so a rival result
	# arriving during the verdict never lands on the verdict card.
	var stack := (STATS_H + GAP) * s
	if _verdict_active and not _verdict_high(rect):
		stack += _verdict_card_height(s) + GAP * s
	var box := Rect2(Vector2(rect.size.x * 0.5 - w * 0.5 - pad,
			_card_base(rect, s) - stack - GAP * s - h),
			Vector2(w + pad * 2.0, h))
	_plate(c, box, R * s, Color(PLATE.r, PLATE.g, PLATE.b, PLATE.a * alpha),
			Color(BORDER.r, BORDER.g, BORDER.b, BORDER.a * alpha), 6.0 * s)
	_text(c, Vector2(box.position.x + pad, box.position.y + pad * 0.5), _toast_text, size,
			Color(INK.r, INK.g, INK.b, alpha))


## The payoff panel: how fast, how much it bent, how clean the contact was.
func _paint_stats(c: Control, rect: Rect2, s: float) -> void:
	if not _stats_active:
		return
	var alpha := clampf(_stats_age / STATS_IN, 0.0, 1.0)
	alpha *= 1.0 - clampf((_stats_age - STATS_IN - STATS_HOLD) / STATS_OUT, 0.0, 1.0)
	# A broadcast card leaves the frame when the HUD is dimmed for the replay: a
	# translucent leftover of it hanging over the orbit reads as a smear.
	alpha *= _live()
	if alpha <= 0.01:
		return
	var lead := _fs(T_LEAD, s)
	var micro := _fs(T_MICRO, s)
	var pad := PAD * s
	var col_w := 108.0 * s
	# Bottom of the frame, not the middle of it. Sitting just under the crossbar it
	# landed square on the keeper in the goal camera, which is the one shot the
	# player wants to see.
	var box := Rect2(Vector2(rect.size.x * 0.5 - (col_w * 3.0 + pad * 2.0) * 0.5,
			_card_base(rect, s) - STATS_H * s),
			Vector2(col_w * 3.0 + pad * 2.0, STATS_H * s))
	_plate(c, box, R * s, Color(PLATE.r, PLATE.g, PLATE.b, PLATE.a * alpha),
			Color(BORDER.r, BORDER.g, BORDER.b, BORDER.a * alpha), 8.0 * s)

	var curve_dir := ""
	if absf(_stat_curve) >= 4.0:
		curve_dir = " D" if _stat_curve > 0.0 else " G"
	var values: PackedStringArray = [
		"%d km/h" % int(round(_stat_speed)),
		"%d cm%s" % [int(round(absf(_stat_curve))), curve_dir],
		"%d %%" % int(round(_stat_quality * 100.0)),
	]
	var labels: PackedStringArray = ["VITESSE", "COURBE", "FRAPPE"]
	var tones: Array[Color] = [INK, ACCENT, GOOD.lerp(WARN, 1.0 - _stat_quality)]
	for i in 3:
		var cx := box.position.x + pad + col_w * (float(i) + 0.5)
		var value: String = values[i]
		var label: String = labels[i]
		var tone: Color = tones[i]
		tone.a = alpha
		_text(c, Vector2(cx - _text_width(value, lead) * 0.5, box.position.y + pad * 0.5),
				value, lead, tone)
		var lw := _tracked_width(label, micro, 1.4 * s)
		_tracked(c, Vector2(cx - lw * 0.5, box.position.y + pad * 0.5 + lead * 1.15), label,
				micro, Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, alpha), 1.4 * s)
		if i < 2:
			var sx := box.position.x + pad + col_w * float(i + 1)
			c.draw_line(Vector2(sx, box.position.y + 10.0 * s),
					Vector2(sx, box.end.y - 10.0 * s),
					Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.25 * alpha), 1.0 * s, true)


## The verdict plate. A contained broadcast card: it swells out of nothing, holds,
## then fades. Everything it draws lives inside its own rounded plate, rules
## included: a rule that runs off both sides of the frame reads as a debug artifact
## rather than as a design, which is exactly what it used to look like.
##
## It is contained, and it is also OUT OF THE WAY. It used to be centred at 40 %
## of the frame height, which is the goal mouth in the camera behind the taker:
## the single frame the player waits for, the keeper actually stopping the ball,
## was covered by a large opaque box. See `_verdict_high` for how the slot is
## chosen.
func _paint_verdict(c: Control, rect: Rect2, s: float) -> void:
	if not _verdict_active:
		return
	var t_in := clampf(_verdict_age / VERDICT_IN, 0.0, 1.0)
	var ease_in := _ease_out_back(t_in)
	var alpha := 1.0 - clampf((_verdict_age - VERDICT_IN - VERDICT_HOLD) / VERDICT_OUT,
			0.0, 1.0)
	alpha *= _live()
	if alpha <= 0.01:
		return
	var tone := _verdict_tone(_verdict)
	var label := _verdict_label(_verdict)
	if label.is_empty() and _verdict_detail.is_empty():
		return

	# Card and type swell together, so the text is never wider than its own plate
	# during the entrance.
	var grow := 0.90 + 0.10 * ease_in
	var hero := maxi(int(round(float(_fs(T_HERO, s)) * grow)), 12)
	var lead := maxi(int(round(float(_fs(T_LEAD, s)) * grow)), 10)
	var has_detail := not _verdict_detail.is_empty()
	var hero_h := _font.get_ascent(hero) + _font.get_descent(hero)
	var lead_h := _font.get_ascent(lead) + _font.get_descent(lead)
	var tw := _text_width(label, hero)
	var dw := _text_width(_verdict_detail, lead) if has_detail else 0.0
	var rule_w := clampf(maxf(tw, dw) * 0.30, 46.0 * s, 180.0 * s)
	var gap := 7.0 * s
	var rule_h := 2.0 * s
	var content_h := hero_h
	if has_detail:
		content_h += gap + rule_h + gap + lead_h
	var pad_x := PAD * 1.9 * s
	var pad_y := PAD * 1.0 * s
	var w := minf(maxf(maxf(tw, dw), rule_w) + pad_x * 2.0, rect.size.x - MARGIN * 2.0 * s)
	var h := content_h + pad_y * 2.0
	var centre_x := rect.size.x * 0.5
	var card_y := _card_base(rect, s) - (STATS_H + GAP) * s - h
	if _verdict_high(rect):
		card_y = VERDICT_TOP_RESERVE * s
	var card := Rect2(Vector2(centre_x - w * 0.5, card_y), Vector2(w, h))

	_plate(c, card, R_L * s, Color(0.02, 0.030, 0.048, alpha),
			Color(tone.r, tone.g, tone.b, 0.55 * alpha), 14.0 * s)
	# Two contained accents, inset by the corner radius so they follow the plate
	# instead of cutting across the picture.
	var inset := R_L * s
	var accent := Color(tone.r, tone.g, tone.b, 0.90 * alpha)
	c.draw_rect(Rect2(Vector2(card.position.x + inset, card.position.y),
			Vector2(card.size.x - inset * 2.0, 2.5 * s)), accent, true)
	c.draw_rect(Rect2(Vector2(card.position.x + inset, card.end.y - 2.5 * s),
			Vector2(card.size.x - inset * 2.0, 2.5 * s)), accent, true)
	# A light sweep travelling once across the card, like a broadcast wipe. Clipped
	# to the card, so nothing of it ever lands on the turf.
	var sweep := clampf((_verdict_age - VERDICT_IN) / 0.7, 0.0, 1.0)
	if sweep > 0.0 and sweep < 1.0:
		var sx := card.position.x + card.size.x * sweep
		var sa := sin(sweep * PI) * 0.14 * alpha
		var wipe := Rect2(Vector2(sx - 34.0 * s, card.position.y + 2.5 * s),
				Vector2(68.0 * s, card.size.y - 5.0 * s)).intersection(card)
		if wipe.size.x > 1.0:
			# Feathered on both sides, otherwise the highlight reads as a pasted
			# rectangle instead of as light travelling across the card.
			var clear := Color(1.0, 1.0, 1.0, 0.0)
			var lit := Color(1.0, 1.0, 1.0, sa)
			var half_w := wipe.size.x * 0.5
			_gradient_h(c, Rect2(wipe.position, Vector2(half_w, wipe.size.y)), clear, lit)
			_gradient_h(c, Rect2(Vector2(wipe.position.x + half_w, wipe.position.y),
					Vector2(half_w, wipe.size.y)), lit, clear)

	var y := card.position.y + pad_y
	_text(c, Vector2(centre_x - tw * 0.5, y), label, hero,
			Color(tone.r, tone.g, tone.b, alpha))
	if has_detail:
		y += hero_h + gap
		c.draw_rect(Rect2(Vector2(centre_x - rule_w * 0.5, y), Vector2(rule_w, rule_h)),
				Color(tone.r, tone.g, tone.b, 0.55 * alpha), true)
		y += rule_h + gap
		_text(c, Vector2(centre_x - dw * 0.5, y), _verdict_detail, lead,
				Color(INK_SOFT.r, INK_SOFT.g, INK_SOFT.b, alpha))


# ---------------------------------------------------------- keeper side drawing

## Projects a world point, or returns a NON FINITE vector when it cannot be drawn.
## Every keeper side drawing is anchored in the world rather than on the screen,
## because every one of them is a statement about the goal: the envelope is the
## part of the mouth this body still covers, the strip is a piece of the goal
## line, the reticle is a point on the frame. Screen space would put them
## somewhere near those things instead of on them.
func _screen_of(world: Vector3) -> Vector2:
	if _camera == null or not is_instance_valid(_camera):
		return Vector2(NAN, NAN)
	if _camera.is_position_behind(world):
		return Vector2(NAN, NAN)
	var p := _camera.unproject_position(world)
	if not p.is_finite() or absf(p.x) > 1.0e5 or absf(p.y) > 1.0e5:
		return Vector2(NAN, NAN)
	return p


func _project_ring(ring: PackedVector3Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for i in ring.size():
		var p := _screen_of(ring[i])
		if p.is_finite():
			out.append(p)
	return out


## Ink of the envelope, from how much of the mouth is left. Cyan while there is
## still a real choice, amber once the goal is bigger than the body, red when
## almost nothing is left. Green is not in this ramp on purpose: the picture
## behind it is a sunlit pitch.
func _reach_tone() -> Color:
	if _coverage <= REACH_TIGHT:
		var t := clampf((_coverage - REACH_LOST) / maxf(REACH_TIGHT - REACH_LOST, 0.01),
				0.0, 1.0)
		return BAD.lerp(WARN, t)
	return WARN.lerp(ACCENT, clampf((_coverage - REACH_TIGHT) / 0.34, 0.0, 1.0))


## THE reach envelope. Everything else on this half of the game is furniture
## around it: it is the only drawing that answers the question the player is
## actually being asked, which is "what do I still cover if I go now".
func _paint_reach(c: Control, _rect: Rect2, s: float) -> void:
	var alpha := _live()
	if alpha <= 0.01:
		return
	var live := _project_ring(_reach)
	if live.size() < 3:
		return
	var tone := _reach_tone()
	var ink := tone
	var body := 0.10
	if _committed:
		# Gone. Whatever the orchestrator still sends is drawn as a spent thing
		# rather than as a live offer; it usually sends an empty ring, which hides
		# it altogether, and that is right too.
		ink = INK_FAINT
		alpha *= 0.5
		body = 0.05

	# The same ring a moment ago, dashed. The gap between the two IS the rate the
	# window is closing at, and it is the one part of the shrink that survives on a
	# frozen frame.
	var ghost := _project_ring(_reach_ghost)
	if ghost.size() >= 3 and not _committed:
		# Dark pass under it as well: at a third of a metre outside the live ring it
		# lands on the same lit net the live one does, and a pale hairline there is
		# a hairline nobody sees.
		_stroke_dashed(c, ghost, Color(0.0, 0.0, 0.0, 0.40 * alpha), 4.0 * s)
		_stroke_dashed(c, ghost, Color(INK.r, INK.g, INK.b, 0.50 * alpha), 2.0 * s)

	c.draw_polygon(live, PackedColorArray([Color(ink.r, ink.g, ink.b, body * alpha)]))
	# There is deliberately NO second contour inside this one. An inner rim looks
	# good and reads as a second rule: with the ghost outside and a rim inside, the
	# picture carries three concentric lines and the one that matters, the live
	# edge, stops being obvious. Two lines, and they mean now and a moment ago.
	# Dark pass first: this line crosses white posts, cord netting and lit turf in
	# the same stroke, and it has to survive all three.
	_stroke_closed(c, live, Color(0.0, 0.0, 0.0, 0.55 * alpha), 5.4 * s)
	var pulse := 1.0 if _committed else 1.0 + 0.10 * sin(_clock * 6.0)
	_stroke_closed(c, live, Color(ink.r, ink.g, ink.b, 0.95 * alpha), 2.8 * s * pulse)


func _stroke_closed(c: Control, pts: PackedVector2Array, col: Color, width: float) -> void:
	if pts.size() < 2:
		return
	var loop := pts.duplicate()
	loop.append(pts[0])
	c.draw_polyline(loop, col, width, true)


## Every third segment left out. A dashed ring reads as a memory rather than as a
## second rule, which is exactly what the ghost is.
func _stroke_dashed(c: Control, pts: PackedVector2Array, col: Color, width: float) -> void:
	var n := pts.size()
	if n < 2:
		return
	for i in n:
		if i % 3 == 2:
			continue
		c.draw_line(pts[i], pts[(i + 1) % n], col, width, true)


## The strip of goal line the keeper may shuffle along, drawn UNDER the mouth so
## the dance is legible without the camera having to move to show it.
func _paint_line_strip(c: Control, _rect: Rect2, s: float) -> void:
	var alpha := _live()
	if alpha <= 0.01:
		return
	var a := _screen_of(Vector3(-_line_limit, STRIP_GROUND, 0.04))
	var b := _screen_of(Vector3(_line_limit, STRIP_GROUND, 0.04))
	var here := _screen_of(Vector3(clampf(_line_x, -_line_limit, _line_limit), STRIP_GROUND, 0.04))
	var mid := _screen_of(Vector3(0.0, STRIP_GROUND, 0.04))
	if not a.is_finite() or not b.is_finite() or not here.is_finite() or not mid.is_finite():
		return
	if a.distance_squared_to(b) < 4.0:
		return
	var drop := Vector2(0.0, STRIP_DROP * s)
	a += drop
	b += drop
	here += drop
	mid += drop
	var perp := (b - a).normalized().orthogonal() * (7.0 * s)

	c.draw_line(a, b, Color(0.0, 0.0, 0.0, 0.60 * alpha), 10.0 * s, true)
	c.draw_line(a, b, Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.55 * alpha), 4.0 * s, true)
	# The two ends of the leash, and the middle of the line.
	for stop: Vector2 in [a, b]:
		c.draw_line(stop - perp, stop + perp, Color(INK.r, INK.g, INK.b, 0.70 * alpha),
				2.0 * s, true)
	c.draw_line(mid - perp * 0.5, mid + perp * 0.5,
			Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.55 * alpha), 1.4 * s, true)

	var d := 7.0 * s
	var diamond := PackedVector2Array([here + Vector2(0.0, -d), here + Vector2(d, 0.0),
			here + Vector2(0.0, d), here + Vector2(-d, 0.0)])
	c.draw_colored_polygon(_offset_poly(diamond, Vector2(0.0, 1.5 * s)),
			Color(0.0, 0.0, 0.0, 0.55 * alpha))
	c.draw_colored_polygon(diamond, _fade(ACCENT, alpha))


func _offset_poly(pts: PackedVector2Array, by: Vector2) -> PackedVector2Array:
	var out := PackedVector2Array()
	for i in pts.size():
		out.append(pts[i] + by)
	return out


## Where the dive is aimed, coloured by the seconds it has to spare. Deliberately
## a different shape from the shooting reticle: four corner brackets, a thing that
## closes on the ball, rather than the four arcs that mean "I am aiming here".
func _paint_dive_aim(c: Control, _rect: Rect2, s: float) -> void:
	var fade := 1.0 - clampf((_dive_age - DIVE_HOLD) / DIVE_FADE, 0.0, 1.0)
	fade *= _live()
	if fade <= 0.01:
		return
	var p := _screen_of(_dive_target)
	if not p.is_finite():
		return
	var tone := BAD
	if _dive_margin >= DIVE_SAFE:
		tone = ACCENT
	elif _dive_margin >= 0.0:
		tone = WARN
	if _committed:
		tone = tone.lerp(INK, 0.35)
		fade *= 0.85

	if not _committed:
		# A faint line from the body to the point being asked for. It says "this is
		# the dive", and it disappears the moment the dive is no longer a question.
		var chest := _screen_of(Vector3(clampf(_line_x, -_line_limit, _line_limit), 0.95, 0.05))
		if chest.is_finite():
			c.draw_line(chest, p, Color(tone.r, tone.g, tone.b, 0.18 * fade), 2.0 * s, true)

	var r := 16.0 * s * (1.0 + 0.04 * sin(_clock * 5.5))
	var arm := 7.0 * s
	_bracket_shape(c, p + Vector2(1.5 * s, 1.5 * s), r, arm,
			Color(0.0, 0.0, 0.0, 0.45 * fade), 3.4 * s)
	_bracket_shape(c, p, r, arm, Color(tone.r, tone.g, tone.b, fade), 2.4 * s)
	c.draw_circle(p, 2.6 * s, Color(tone.r, tone.g, tone.b, fade))


func _bracket_shape(c: Control, p: Vector2, r: float, arm: float, col: Color,
		width: float) -> void:
	for i in 4:
		var sx := 1.0 if (i % 2) == 0 else -1.0
		var sy := 1.0 if i < 2 else -1.0
		var corner := p + Vector2(r * sx, r * sy)
		c.draw_line(corner, corner - Vector2(arm * sx, 0.0), col, width, true)
		c.draw_line(corner, corner - Vector2(0.0, arm * sy), col, width, true)


# --- The tells ---------------------------------------------------------------
#
# What the taker is doing with his body, and NOTHING else. Three drawing rules
# that are the reason this panel is honest:
#
#   - it is MIRRORED. The keeper faces +Z, so world +X is on his LEFT, and every
#     diagram here is laid out the way he sees it. A plan view that put +X on the
#     right would be a diagram of a different penalty from the one on screen.
#   - a MISSING cue is not drawn. TakerAi.tells_at leaks the run up one piece at a
#     time, so an empty slot here means "he has not shown you that yet", which is
#     a true and useful thing to see filling up.
#   - an UNRELIABLE cue is drawn WIDER, never fainter and never smaller. The wedge
#     opens, the smear spreads. "I cannot read him" and "he is not going there"
#     have to look like different sentences.
#
# The one interpretation this panel allows itself is the tendency strip, and its
# weights are written down here rather than hidden: the plant foot carries a real
# penalty read, the hips less, the run up angle least. It is a HUNCH drawn as a
# smear a metre and a half wide, it is often wrong, and it is never a figure.
const TELL_W_PLANT := 0.72
const TELL_W_HIP := 0.52
const TELL_W_RUN := 0.44
## Metres of smear the tendency carries even at full confidence, and how much more
## it carries at none.
const TELL_BLUR_MIN := 0.85
const TELL_BLUR_MAX := 3.10


func _paint_tells(c: Control, rect: Rect2, s: float) -> void:
	var alpha := _live()
	if alpha <= 0.01 or _tells.is_empty():
		return
	var pad := PAD * s
	var w := TELLS_W * s
	var h := TELLS_H * s
	var box := Rect2(Vector2(MARGIN * s, rect.size.y - BAR_LIFT * s - h), Vector2(w, h))
	_plate(c, box, R * s, _fade(CARD, alpha), _fade(CARD_EDGE, alpha), 10.0 * s)

	var micro := _fs(T_MICRO, s)
	var conf := clampf(_cue_f("confidence", 0.35), 0.0, 1.0)
	_tracked(c, box.position + Vector2(pad, pad * 0.55), "LECTURE", micro,
			_fade(INK_FAINT, alpha), 1.6 * s)

	# Feints are the one cue that is a COUNT, so it is the one cue drawn as a word.
	var feints := int(round(_cue_f("feints", 0.0)))
	if feints > 0:
		var chip_text := "FEINTE" if feints == 1 else "%d FEINTES" % feints
		var cw := _tracked_width(chip_text, micro, 1.2 * s) + pad
		var chip := Rect2(Vector2(box.end.x - pad - cw, box.position.y + pad * 0.35),
				Vector2(cw, float(micro) + 7.0 * s))
		_plate(c, chip, R_S * s, Color(WARN.r * 0.35, WARN.g * 0.28, 0.06, 0.85 * alpha),
				_fade(Color(WARN.r, WARN.g, WARN.b, 0.5), alpha), 0.0)
		_tracked(c, chip.position + Vector2(pad * 0.5, 3.5 * s), chip_text, micro,
				_fade(WARN, alpha), 1.2 * s)

	var strip := Rect2(Vector2(box.position.x + pad, box.position.y + pad * 0.55 + micro * 1.6),
			Vector2(box.size.x - pad * 2.0, 26.0 * s))
	_paint_tell_strip(c, strip, conf, alpha, s)

	var plan := Rect2(Vector2(strip.position.x, strip.end.y + 9.0 * s),
			Vector2(strip.size.x, box.end.y - pad * 0.7 - (strip.end.y + 9.0 * s)))
	if plan.size.y > 20.0 * s:
		_paint_tell_plan(c, plan, conf, alpha, s)


## The tendency strip: a miniature of the mouth with a smear where the body
## language points. It is the only place this panel interprets anything, so the
## smear is never narrower than TELL_BLUR_MIN and the mouth behind it is drawn to
## scale, which is what stops it reading as a target.
func _paint_tell_strip(c: Control, strip: Rect2, conf: float, alpha: float, s: float) -> void:
	_plate(c, strip, R_S * s, _fade(TRACK, alpha), Color(0.0, 0.0, 0.0, 0.0), 0.0)
	var to_px := strip.size.x / (TELL_MOUTH_HALF * 2.0)
	var mid_x := strip.get_center().x
	# Mirrored: world +X is the keeper's left, so it is the strip's left.
	var post_dx := Field.GOAL_HALF * to_px
	for sign_x: float in [-1.0, 1.0]:
		var x := mid_x + sign_x * post_dx
		c.draw_line(Vector2(x, strip.position.y + 2.0 * s), Vector2(x, strip.end.y - 2.0 * s),
				Color(INK_SOFT.r, INK_SOFT.g, INK_SOFT.b, 0.55 * alpha), 1.6 * s, true)
	c.draw_line(Vector2(mid_x, strip.end.y - 4.0 * s), Vector2(mid_x, strip.end.y - 1.0 * s),
			Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.5 * alpha), 1.2 * s, true)

	var has_body := _tells.has("plant_offset") or _tells.has("hip_yaw") \
			or _tells.has("run_angle")
	if not has_body:
		return
	var bias := TELL_W_PLANT * clampf(_cue_f("plant_offset", 0.0), -1.0, 1.0)
	bias += TELL_W_HIP * clampf(sin(_cue_f("hip_yaw", 0.0)) / 0.55, -1.0, 1.0)
	bias += TELL_W_RUN * clampf(_cue_f("run_angle", 0.0), -1.0, 1.0)
	bias = clampf(bias / (TELL_W_PLANT + TELL_W_HIP + TELL_W_RUN), -1.0, 1.0)
	var read_x := bias * Field.GOAL_HALF * 0.92
	var blur := lerpf(TELL_BLUR_MAX, TELL_BLUR_MIN, conf)
	# Drawn mirrored, and as a pair of gradients rather than as a box: a hard edge
	# would read as a boundary the ball respects, and stacked slabs read as steps
	# nobody meant.
	var cx := mid_x - read_x * to_px
	var cy := strip.get_center().y
	var band_h := strip.size.y - 6.0 * s
	var half := blur * to_px
	var lit := Color(WARN.r, WARN.g, WARN.b, 0.42 * alpha)
	var clear := Color(WARN.r, WARN.g, WARN.b, 0.0)
	var top := cy - band_h * 0.5
	var l0 := maxf(cx - half, strip.position.x + 1.0 * s)
	var r0 := minf(cx + half, strip.end.x - 1.0 * s)
	if cx > l0:
		_gradient_h(c, Rect2(Vector2(l0, top), Vector2(cx - l0, band_h)), clear, lit)
	if r0 > cx:
		_gradient_h(c, Rect2(Vector2(cx, top), Vector2(r0 - cx, band_h)), lit, clear)
	c.draw_line(Vector2(cx, cy - band_h * 0.5), Vector2(cx, cy + band_h * 0.5),
			Color(WARN.r, WARN.g, WARN.b, 0.85 * alpha), 1.8 * s, true)


## The run up seen from above, the way the keeper sees it: the goal line across
## the bottom, the ball on its spot, the taker coming down at it.
func _paint_tell_plan(c: Control, plan: Rect2, conf: float, alpha: float, s: float) -> void:
	var micro := _fs(T_MICRO, s)
	var ball := Vector2(plan.get_center().x, plan.end.y - 15.0 * s)
	var line_y := plan.end.y - 3.0 * s
	c.draw_line(Vector2(plan.position.x + 12.0 * s, line_y),
			Vector2(plan.end.x - 12.0 * s, line_y),
			Color(INK_SOFT.r, INK_SOFT.g, INK_SOFT.b, 0.40 * alpha), 2.0 * s, true)
	_tracked(c, plan.position, "ÉLAN", micro, _fade(INK_FAINT, alpha * 0.8), 1.2 * s)

	# The approach. A wedge for where it might be coming from, a line for the best
	# guess, chevrons for how fast he is arriving.
	if _tells.has("run_angle"):
		var run := clampf(_cue_f("run_angle", 0.0), -1.0, 1.0)
		# Mirrored: a run up from the +X side arrives on the keeper's left.
		var axis := deg_to_rad(-run * 42.0) - PI * 0.5
		var spread := deg_to_rad(9.0 + 27.0 * (1.0 - conf))
		var reach := plan.size.y * 0.78
		var wedge := PackedVector2Array([ball])
		for i in 9:
			var a := axis - spread + spread * 2.0 * float(i) / 8.0
			wedge.append(ball + Vector2(cos(a), sin(a)) * reach)
		c.draw_colored_polygon(wedge, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.13 * alpha))
		var tip := ball + Vector2(cos(axis), sin(axis)) * reach
		c.draw_line(tip, ball, Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.85 * alpha), 2.0 * s, true)
		if _tells.has("approach_speed"):
			var pace := clampf(_cue_f("approach_speed", 0.5), 0.0, 1.0)
			var marks := 1 + int(round(pace * 2.0))
			var dir := (ball - tip).normalized()
			var side := dir.orthogonal() * (5.0 * s)
			for i in marks:
				var t := 0.34 + 0.20 * float(i)
				var p := tip.lerp(ball, t)
				c.draw_line(p - side - dir * (5.0 * s), p,
						Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.75 * alpha), 1.8 * s, true)
				c.draw_line(p + side - dir * (5.0 * s), p,
						Color(ACCENT.r, ACCENT.g, ACCENT.b, 0.75 * alpha), 1.8 * s, true)

	# The hips, as a bar through the ball. Turned hips are the cue that arrives
	# last and lies least, so it is drawn hard even when everything else is fuzzy.
	if _tells.has("hip_yaw"):
		var yaw := clampf(_cue_f("hip_yaw", 0.0), -1.2, 1.2)
		var bar := Vector2(cos(-yaw), sin(-yaw)) * (17.0 * s)
		c.draw_line(ball - bar, ball + bar, Color(INK.r, INK.g, INK.b, 0.75 * alpha),
				2.6 * s, true)

	# The plant foot, with its own uncertainty smeared sideways.
	if _tells.has("plant_offset"):
		var plant := clampf(_cue_f("plant_offset", 0.0), -1.0, 1.0)
		var span := plan.size.x * 0.30
		var fx := ball.x - plant * span
		var fy := ball.y + 7.0 * s
		var smear := span * 0.55 * (1.0 - conf) + 3.0 * s
		c.draw_line(Vector2(fx - smear, fy), Vector2(fx + smear, fy),
				Color(GOOD.r, GOOD.g, GOOD.b, 0.30 * alpha), 5.0 * s, true)
		c.draw_rect(Rect2(Vector2(fx - 3.4 * s, fy - 5.0 * s), Vector2(6.8 * s, 10.0 * s)),
				Color(GOOD.r, GOOD.g, GOOD.b, 0.90 * alpha), true)

	# The ball last, so nothing is drawn over the thing everything else is about.
	c.draw_circle(ball, 4.6 * s, Color(INK.r, INK.g, INK.b, 0.95 * alpha))


## Reads one cue. A cue that has not leaked yet is simply absent, and the caller
## checks for that: this only supplies the fallback for a cue that is there but
## unusable.
func _cue_f(key: String, fallback: float) -> float:
	if not _tells.has(key):
		return fallback
	var v: Variant = _tells[key]
	if typeof(v) != TYPE_FLOAT and typeof(v) != TYPE_INT:
		return fallback
	var f := float(v)
	return f if is_finite(f) else fallback


## The commit prompt: how much of the goal is still covered, and how much of the
## window is left. It says WHEN, and there is deliberately nothing in it that
## could be read as a side.
func _paint_commit(c: Control, rect: Rect2, s: float) -> void:
	var alpha := _live()
	if alpha <= 0.01:
		return
	var pad := PAD * s
	var w := COMMIT_W * s
	var h := COMMIT_H * s
	var box := Rect2(Vector2(rect.size.x * 0.5 - w * 0.5, rect.size.y - BAR_LIFT * s - h),
			Vector2(w, h))
	_plate(c, box, R * s, _fade(CARD, alpha), _fade(CARD_EDGE, alpha), 12.0 * s)

	var micro := _fs(T_MICRO, s)
	var small := _fs(T_SMALL, s)
	var tone := _reach_tone()

	# The coverage ring, in its own column so its caption cannot spill onto the
	# turf. Same number as the envelope, in a shape that survives being glanced at
	# rather than read.
	var ring_r := 19.0 * s
	var cap := "COUVERTURE"
	var cap_w := _tracked_width(cap, micro, 1.0 * s)
	var col1 := maxf(COMMIT_RING_COL * s, cap_w + 8.0 * s)
	var block_h := ring_r * 2.0 + 4.0 * s + float(micro)
	var ring_c := Vector2(box.position.x + 10.0 * s + col1 * 0.5,
			box.position.y + (box.size.y - block_h) * 0.5 + ring_r)
	c.draw_arc(ring_c, ring_r, 0.0, TAU, 40,
			Color(INK_FAINT.r, INK_FAINT.g, INK_FAINT.b, 0.28 * alpha), 4.0 * s, true)
	var span := TAU * clampf(_cover_shown, 0.0, 1.0)
	if span > 0.001:
		c.draw_arc(ring_c, ring_r, -PI * 0.5, -PI * 0.5 + span, 44,
				Color(tone.r, tone.g, tone.b, 0.95 * alpha), 4.6 * s, true)
	var pct := "%d %%" % int(round(_cover_shown * 100.0))
	_text(c, ring_c - Vector2(_text_width(pct, micro) * 0.5, float(micro) * 0.62), pct, micro,
			_fade(INK, alpha))
	_tracked(c, Vector2(ring_c.x - cap_w * 0.5, ring_c.y + ring_r + 4.0 * s), cap, micro,
			_fade(INK_FAINT, alpha), 1.0 * s)

	var col_x := box.position.x + 10.0 * s + col1 + 10.0 * s
	var col_w := box.end.x - pad * 0.9 - col_x
	if col_w < 40.0 * s:
		return

	var prompt := "PATIENTEZ"
	var prompt_tone := INK_FAINT
	if _committed:
		prompt = "ENGAGÉ"
		prompt_tone = INK_SOFT
	elif _commit_open:
		prompt = "PLONGEZ  ·  CLIC OU ESPACE"
		prompt_tone = ACCENT.lerp(BAD, clampf(_commit_urgency * 1.15, 0.0, 1.0))
	var beat := 1.0
	if _commit_open and not _committed:
		# The nearer the window is to shut, the harder the prompt beats. Rate, not
		# words: there is no room to read a sentence at this point in the round.
		beat = 0.72 + 0.28 * sin(_clock * (7.0 + 9.0 * _commit_urgency))
	# The column is centred in the card on its own measured height, so the three
	# rows sit level with the ring beside them instead of drifting up the plate.
	var col_h := float(small) * 1.15 + 6.0 * s + 9.0 * s + 5.0 * s + float(micro)
	var col_y := box.position.y + (box.size.y - col_h) * 0.5
	_text(c, Vector2(col_x, col_y), prompt, small,
			Color(prompt_tone.r, prompt_tone.g, prompt_tone.b, alpha * beat))

	# The window itself, emptying from the left.
	var bar := Rect2(Vector2(col_x, col_y + float(small) * 1.15 + 6.0 * s),
			Vector2(col_w, 9.0 * s))
	_plate(c, bar, R_S * s, _fade(TRACK, alpha), Color(0.0, 0.0, 0.0, 0.0), 0.0)
	var left := clampf(1.0 - _commit_urgency, 0.0, 1.0)
	var bar_tone := ACCENT.lerp(BAD, clampf(_commit_urgency, 0.0, 1.0))
	if _committed:
		bar_tone = INK_FAINT
	if left > 0.002:
		c.draw_rect(Rect2(bar.position, Vector2(bar.size.x * left, bar.size.y)),
				Color(bar_tone.r, bar_tone.g, bar_tone.b, 0.92 * alpha), true)
	else:
		c.draw_line(Vector2(bar.position.x, bar.get_center().y),
				Vector2(bar.end.x, bar.get_center().y), _fade(BAD, alpha * 0.8), 1.6 * s, true)
	var foot := "FENÊTRE D'ENGAGEMENT"
	_tracked(c, Vector2(col_x, bar.end.y + 4.0 * s), foot, micro, _fade(INK_FAINT, alpha),
			1.1 * s)


# ------------------------------------------------------------------- primitives

func _plate(c: Control, rect: Rect2, radius: float, fill: Color, border: Color,
		shadow: float) -> void:
	var key := "%d|%s|%s|%d" % [int(round(radius)), fill.to_html(), border.to_html(),
			int(round(shadow))]
	var box: StyleBoxFlat = _plate_cache.get(key, null)
	if box == null:
		box = StyleBoxFlat.new()
		box.bg_color = fill
		box.set_corner_radius_all(int(round(radius)))
		if border.a > 0.003:
			box.set_border_width_all(1)
			box.border_color = border
		if shadow > 0.5:
			box.shadow_size = int(round(shadow))
			box.shadow_color = SHADOW
			box.shadow_offset = Vector2(0.0, 2.0)
		_plate_cache[key] = box
	c.draw_style_box(box, rect)


## Vertex coloured quad rather than a stack of slices: sliced gradients leave
## visible seams wherever two translucent bands overlap by a pixel.
func _gradient(c: Control, rect: Rect2, top: Color, bottom: Color) -> void:
	var points := PackedVector2Array([
		rect.position, Vector2(rect.end.x, rect.position.y), rect.end,
		Vector2(rect.position.x, rect.end.y)])
	c.draw_polygon(points, PackedColorArray([top, top, bottom, bottom]))


## Same idea, left to right.
func _gradient_h(c: Control, rect: Rect2, left: Color, right: Color) -> void:
	var points := PackedVector2Array([
		rect.position, Vector2(rect.end.x, rect.position.y), rect.end,
		Vector2(rect.position.x, rect.end.y)])
	c.draw_polygon(points, PackedColorArray([left, right, right, left]))


## Draws a string from its top left corner, with a drop shadow. Returns the width.
func _text(c: Control, top_left: Vector2, text: String, size: int, colour: Color,
		shadow: bool = true) -> float:
	if text.is_empty():
		return 0.0
	var base := Vector2(top_left.x, top_left.y + _font.get_ascent(size))
	if shadow:
		c.draw_string(_font, base + Vector2(1.5, 1.5), text, HORIZONTAL_ALIGNMENT_LEFT,
				-1.0, size, Color(0.0, 0.0, 0.0, SHADOW.a * colour.a))
	c.draw_string(_font, base, text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size, colour)
	return _text_width(text, size)


## Letter spaced small caps, used for every label. Tracking is what makes a
## fallback font look deliberate instead of accidental.
func _tracked(c: Control, top_left: Vector2, text: String, size: int, colour: Color,
		tracking: float) -> float:
	var x := top_left.x
	var base_y := top_left.y + _font.get_ascent(size)
	for i in text.length():
		var ch := text.substr(i, 1)
		c.draw_string(_font, Vector2(x + 1.2, base_y + 1.2), ch, HORIZONTAL_ALIGNMENT_LEFT,
				-1.0, size, Color(0.0, 0.0, 0.0, SHADOW.a * colour.a))
		c.draw_string(_font, Vector2(x, base_y), ch, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size,
				colour)
		x += _text_width(ch, size) + tracking
	return x - top_left.x


func _note(c: Control, top_left: Vector2, text: String, size: int, colour: Color,
		alpha: float, s: float) -> void:
	var pad := PAD_S * s
	var w := _text_width(text, size)
	_plate(c, Rect2(top_left, Vector2(w + pad * 2.0, size + pad * 1.4)), R_S * s,
			_fade(PLATE_SOFT, alpha), Color(0.0, 0.0, 0.0, 0.0), 4.0 * s)
	_text(c, top_left + Vector2(pad, pad * 0.7), text, size, colour)


## 1 while the HUD is in use, 0 once it has been dimmed away. Transient cards
## multiply their own alpha by it so they leave the frame instead of lingering.
func _live() -> float:
	return clampf(1.0 - _dim_amount, 0.0, 1.0)


func _fade(colour: Color, alpha: float) -> Color:
	return Color(colour.r, colour.g, colour.b, colour.a * clampf(alpha, 0.0, 1.0))


func _text_width(text: String, size: int) -> float:
	return _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size).x


func _tracked_width(text: String, size: int, tracking: float) -> float:
	if text.is_empty():
		return 0.0
	return _text_width(text, size) + tracking * float(text.length() - 1)


func _fs(scale: float, s: float) -> int:
	return maxi(int(round(float(_base_size) * scale * s)), 9)


func _approach(current: float, target: float, rate: float) -> float:
	return current + (target - current) * clampf(rate, 0.0, 1.0)


func _ease_out_back(t: float) -> float:
	var u := clampf(t, 0.0, 1.0) - 1.0
	return 1.0 + 2.70158 * u * u * u + 1.70158 * u * u


func _verdict_tone(verdict: int) -> Color:
	match verdict:
		0:
			return GOOD
		1:
			return ACCENT
		2, 3:
			return WARN
		_:
			return BAD


func _verdict_label(verdict: int) -> String:
	if _shootout != null and is_instance_valid(_shootout) \
			and _shootout.has_method(&"verdict_label"):
		var v: Variant = _shootout.call(&"verdict_label", verdict)
		if v is String and not (v as String).is_empty():
			return v as String
	if verdict >= 0 and verdict < VERDICT_LABELS.size():
		return VERDICT_LABELS[verdict]
	return ""


func _is_goal(verdict: int) -> bool:
	if _shootout != null and is_instance_valid(_shootout) \
			and _shootout.has_method(&"is_goal"):
		var v: Variant = _shootout.call(&"is_goal", verdict)
		if v is bool:
			return v as bool
	return verdict == 0


func _count_goals(marks: Array[int]) -> int:
	var total := 0
	for m in marks:
		if _is_goal(m):
			total += 1
	return total


## Shootout.Verdict.ARRET, mirrored rather than read: this file has to draw with
## no autoload in the tree. Only the keeper training figure uses it.
const VERDICT_ARRET := 1


## Saves, which is NOT "everything that was not a goal": a penalty off the post or
## wide of the frame was missed by the taker and stopped by nobody.
func _count_saves(marks: Array[int]) -> int:
	var total := 0
	for m in marks:
		if m == VERDICT_ARRET:
			total += 1
	return total


# ------------------------------------------------------------------- autoloads

## The autoloads are looked up by path instead of by name. That keeps this file
## compiling under `--check-only --script`, where no autoload is registered, and
## it lets the HUD be instanced on its own without taking the whole game down.
func _bind_singletons() -> void:
	# build() is allowed to run before the node is parented, and get_tree() on a
	# node outside the tree is an engine error rather than a null.
	if not is_inside_tree():
		return
	var tree := get_tree()
	if tree == null:
		return
	var root := tree.root
	if root == null:
		return
	_shootout = root.get_node_or_null(^"Shootout")
	_game = root.get_node_or_null(^"Game")
	var parent := get_parent()
	if parent != null and is_instance_valid(parent):
		_board = parent.get_node_or_null(^"Screens/Scoreboard")
	if _shootout != null and _shootout.has_signal(&"series_changed") \
			and not _shootout.is_connected(&"series_changed", Callable(self, "refresh_series")):
		_shootout.connect(&"series_changed", Callable(self, "refresh_series"))


func _read_int(obj: Object, key: StringName, fallback: int) -> int:
	if obj == null or not is_instance_valid(obj):
		return fallback
	var v: Variant = obj.get(key)
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return int(v)
	return fallback


func _read_bool(obj: Object, key: StringName, fallback: bool) -> bool:
	if obj == null or not is_instance_valid(obj):
		return fallback
	var v: Variant = obj.get(key)
	if typeof(v) == TYPE_BOOL:
		return bool(v)
	return fallback


func _read_marks(obj: Object, key: StringName) -> Array[int]:
	var out: Array[int] = []
	if obj == null or not is_instance_valid(obj):
		return out
	var v: Variant = obj.get(key)
	if v is Array:
		for e in (v as Array):
			if typeof(e) == TYPE_INT or typeof(e) == TYPE_FLOAT:
				out.append(int(e))
	return out


func _call_string(obj: Object, method: StringName) -> String:
	if obj == null or not is_instance_valid(obj) or not obj.has_method(method):
		return ""
	var v: Variant = obj.call(method)
	if v is String:
		return v as String
	return ""
