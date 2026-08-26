class_name Scoreboard
extends Control
## The shootout table: two rows of markers, the score, the pressure line, and the
## end of match panel. Drawn by hand in `_draw`, like the rest of the interface.
##
## Why it slides instead of simply appearing: the scoreboard is shown between two
## attempts, over live action, and a panel that pops into existence reads as a
## bug while a panel that slides in reads as a broadcast graphic. The slide is
## driven by an exponential approach with an ease out back curve on top, so it
## overshoots by a couple of pixels and settles. That single detail is the whole
## difference in feel.
##
## The panel and the end screen share one visual system, declared as constants at
## the top of the file. Nothing here invents a colour or a spacing on the spot.
##
## Engine trap this file is built around: `_draw` is never re-run on its own when
## a value changes, so every setter and every animated frame calls
## `queue_redraw()`.

# ---------------------------------------------------------------- visual system

const INK := Color(0.94, 0.96, 0.99)
const INK_SOFT := Color(0.74, 0.79, 0.87)
const INK_FAINT := Color(0.52, 0.57, 0.66)
const PLATE := Color(0.035, 0.048, 0.070, 0.86)
const PLATE_HEAD := Color(0.06, 0.085, 0.125, 0.94)
const BORDER := Color(0.62, 0.72, 0.86, 0.16)
const SHADOW := Color(0.0, 0.0, 0.0, 0.55)
const SCRIM := Color(0.010, 0.016, 0.026, 1.0)

const ACCENT := Color(0.16, 0.72, 1.00)
const GOOD := Color(0.31, 0.87, 0.48)
const WARN := Color(1.00, 0.73, 0.18)
const BAD := Color(0.98, 0.33, 0.35)
const RIVAL := Color(0.99, 0.48, 0.28)

const MARGIN := 26.0
const PAD := 14.0
const PAD_S := 7.0
const GAP := 9.0
const R_S := 4.0
const R := 8.0
const R_L := 14.0

const T_MICRO := 0.66
const T_SMALL := 0.82
const T_BODY := 1.0
const T_LEAD := 1.35
const T_TITLE := 2.1
const T_HERO := 3.4

const REF_HEIGHT := 900.0

# ------------------------------------------------------------------- behaviour

## Mirrors Shootout.Mode and Shootout.REGULATION_SHOTS. Copied on purpose: the
## scoreboard must still draw when the autoload is not in the tree.
const MODE_SEANCE := 0
const MODE_ENTRAINEMENT := 1
const MODE_DEFI := 2
const MODE_NAMES: PackedStringArray = [
	"Séance de tirs au but", "Entraînement", "Défi",
]
const REGULATION_SLOTS := 5
const MAX_SLOTS := 9

## Panel travel, seconds of smoothing and the settle curve.
const SLIDE_RATE := 9.0
const RESULT_FADE := 0.35
## A marker pops in every POP_STEP seconds on the end screen.
const POP_DELAY := 0.45
const POP_STEP := 0.10
const POP_TIME := 0.22
## How long a freshly landed marker keeps its halo after it has finished popping.
const HALO_TIME := 0.9
## Period of the pulse on the marker the ACTIVE side is about to fill, seconds.
const WAIT_PULSE := 1.05

# ------------------------------------------------------------------------ state

var _font: Font = null
var _base_size: int = 16
var _clock: float = 0.0

var _shootout: Node = null

var _slide: float = 0.0
var _slide_target: float = 0.0
var _flash_left: float = 0.0

var _result_active: bool = false
var _result_won: bool = false
var _result_age: float = 0.0

var _mode: int = MODE_SEANCE
var _round: int = 0
var _player_marks: Array[int] = []
var _rival_marks: Array[int] = []
## Whose turn it is, and what is riding on the rival's next kick. Read straight
## off the Shootout autoload rather than pushed in by the orchestrator: this
## panel already re-reads the whole series on every `series_changed`, so the turn
## is just one more thing it reads. That keeps the public surface of the
## scoreboard exactly as the contract declares it.
var _rival_to_kick: bool = false
var _rival_must_score: bool = false
## Nobody is on turn once the series is over, so nothing is lit up.
var _decided: bool = false
## Seconds since the newest rival marker landed, negative when nothing is fresh.
## A shootout alternates, so the eye has to be told WHICH of the two rows just
## changed; the marker that just arrived pops, the four beside it do not.
var _rival_pip_age: float = -1.0
var _rival_seen: int = -1
var _player_goals: int = 0
var _rival_goals: int = 0
var _pressure: String = ""
var _streak: int = 0
var _best_streak: int = 0
var _defi_points: int = 0

var _plate_cache: Dictionary = {}
var _was_drawing: bool = false


func _ready() -> void:
	build()


## Prepares the surface and reads the current series. Idempotent.
func build() -> void:
	_font = ThemeDB.fallback_font
	_base_size = maxi(ThemeDB.fallback_font_size, 12)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_bind_singletons()
	refresh()
	set_process(true)


## Re-reads the shootout state and redraws.
func refresh() -> void:
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
		_rival_to_kick = _call_bool(src, &"rival_to_kick")
		_rival_must_score = _call_bool(src, &"rival_must_score")
		_decided = _call_bool(src, &"is_decided")
		# The growth of the rival row IS the event, so nobody has to announce it.
		# The first read of a series never pops (_rival_seen starts negative), and
		# a reset that shrinks the row simply re-baselines it.
		if _rival_seen >= 0 and _rival_marks.size() > _rival_seen:
			_rival_pip_age = 0.0
		elif _rival_marks.size() < _rival_seen:
			_rival_pip_age = -1.0
		_rival_seen = _rival_marks.size()
	queue_redraw()


## Slides in for a moment between two shots, then slides out.
func flash(seconds: float = 2.2) -> void:
	refresh()
	_flash_left = maxf(seconds, 0.3)
	_slide_target = 1.0
	queue_redraw()


## Full screen end of match panel.
func show_result(player_won: bool) -> void:
	refresh()
	_result_won = player_won
	_result_active = true
	_result_age = 0.0
	_flash_left = 0.0
	_slide_target = 0.0
	queue_redraw()


func hide_result() -> void:
	_result_active = false
	queue_redraw()


## How much of the sliding panel is on screen right now, 0 when it is fully away.
## Added for the HUD, which owns a small permanent series chip and fades it out
## while this panel is showing the very same numbers. Read through `has_method`,
## so neither side depends on the other being present.
func panel_presence() -> float:
	return clampf(_slide, 0.0, 1.0)


# ------------------------------------------------------------------ frame loop

func _process(delta: float) -> void:
	_clock += delta
	if _flash_left > 0.0:
		_flash_left -= delta
		if _flash_left <= 0.0:
			_flash_left = 0.0
			_slide_target = 0.0
	_slide = _approach(_slide, _slide_target, delta * SLIDE_RATE)
	if absf(_slide - _slide_target) < 0.002:
		_slide = _slide_target
	if _result_active:
		_result_age += delta
	if _rival_pip_age >= 0.0:
		_rival_pip_age += delta
		if _rival_pip_age > POP_TIME + HALO_TIME:
			_rival_pip_age = -1.0
	var drawing := _slide > 0.002 or _result_active
	if drawing or _was_drawing:
		queue_redraw()
	_was_drawing = drawing


func _draw() -> void:
	if _font == null:
		return
	var rect := Rect2(Vector2.ZERO, size)
	if rect.size.x < 32.0 or rect.size.y < 32.0:
		return
	var s := clampf(rect.size.y / REF_HEIGHT, 0.7, 1.9)
	if _slide > 0.002:
		_draw_panel(rect, s)
	if _result_active:
		_draw_result(rect, s)


# ----------------------------------------------------------------- sliding panel

func _draw_panel(rect: Rect2, s: float) -> void:
	var two_rows := _mode == MODE_SEANCE
	var pip_r := 8.0 * s
	var pip_gap := 7.0 * s
	# The shootout label column carries "ADVERSAIRE" plus the turn caret, which is
	# a good deal wider than the "VOUS" a single row mode needs.
	var label_w := (134.0 if two_rows else 108.0) * s
	var score_w := 52.0 * s
	var head_h := 26.0 * s
	var row_h := 36.0 * s
	var foot_h := 24.0 * s if not _pressure.is_empty() else 0.0
	var slots := mini(maxi(REGULATION_SLOTS, maxi(_player_marks.size(),
			_rival_marks.size())), MAX_SLOTS)
	var pips_w := float(slots) * pip_r * 2.0 + float(maxi(slots - 1, 0)) * pip_gap
	var body_w := label_w + pips_w + score_w + PAD * 2.0 * s
	var w := maxf(clampf(rect.size.x * 0.40, 380.0 * s, 700.0 * s), body_w)
	var h := head_h + row_h * (2.0 if two_rows else 1.0) + foot_h + PAD_S * s

	var e := _ease_out_back(_slide)
	var y := lerpf(-h - 12.0 * s, MARGIN * s, e)
	var alpha := clampf(_slide * 1.8, 0.0, 1.0)
	var panel := Rect2(Vector2(rect.size.x * 0.5 - w * 0.5, y), Vector2(w, h))
	_plate(panel, R_L * s, _fade(PLATE, alpha), _fade(BORDER, alpha), 10.0 * s)

	# Header band, square at the bottom so it reads as part of the panel.
	var head := Rect2(panel.position, Vector2(panel.size.x, head_h))
	_plate_top(head, R_L * s, _fade(PLATE_HEAD, alpha))
	var micro := _fs(T_MICRO, s)
	var name_text := MODE_NAMES[clampi(_mode, 0, MODE_NAMES.size() - 1)].to_upper()
	_tracked(Vector2(head.position.x + PAD * s, head.position.y + (head_h - micro) * 0.5),
			name_text, micro, _fade(INK_FAINT, alpha), 1.8 * s)
	var right_text := _round_tag()
	var rw := _tracked_width(right_text, micro, 1.8 * s)
	_tracked(Vector2(head.end.x - PAD * s - rw, head.position.y + (head_h - micro) * 0.5),
			right_text, micro, _fade(ACCENT, alpha), 1.8 * s)

	# Whose turn it is. Only a shootout has two sides to alternate between, so the
	# single row modes never light anything up.
	var rival_turn := two_rows and _rival_to_kick and not _decided
	var player_turn := two_rows and not _rival_to_kick and not _decided

	var row_y := panel.position.y + head_h
	_draw_row(Rect2(Vector2(panel.position.x + PAD * s, row_y),
			Vector2(panel.size.x - PAD * 2.0 * s, row_h)), "VOUS", _player_marks,
			_player_goals, slots, pip_r, pip_gap, label_w, score_w, ACCENT, alpha, -1.0, s,
			player_turn, -1.0)
	if two_rows:
		var sep_y := row_y + row_h
		draw_line(Vector2(panel.position.x + PAD * s, sep_y),
				Vector2(panel.end.x - PAD * s, sep_y), _fade(BORDER, alpha), 1.0, true)
		_draw_row(Rect2(Vector2(panel.position.x + PAD * s, sep_y),
				Vector2(panel.size.x - PAD * 2.0 * s, row_h)), "ADVERSAIRE", _rival_marks,
				_rival_goals, slots, pip_r, pip_gap, label_w, score_w, RIVAL, alpha, -1.0, s,
				rival_turn, _rival_pip_age)

	if not _pressure.is_empty():
		var small := _fs(T_SMALL, s)
		# The line is the situation in words, and it is the same sentence the HUD
		# reads out: "Au tour de l'adversaire", "L'adversaire doit marquer". It
		# takes the rival's colour when it is talking about the rival, so the text
		# and the lit row are never saying two different things.
		var foot_tone := ACCENT
		if rival_turn:
			foot_tone = WARN if _rival_must_score else RIVAL
		var pw := _tracked_width(_pressure, small, 1.2 * s)
		_tracked(Vector2(panel.get_center().x - pw * 0.5, panel.end.y - foot_h + 2.0 * s),
				_pressure, small, _fade(foot_tone, alpha), 1.2 * s)


## One side of the table. `active` lights the row up as the side whose turn it is
## and pulses the marker it is about to fill; `fresh` is the age in seconds of
## the marker that has just landed on this row, negative when none has.
func _draw_row(rect: Rect2, label: String, marks: Array[int], goals: int, slots: int,
		pip_r: float, pip_gap: float, label_w: float, score_w: float, tone: Color,
		alpha: float, pop: float, s: float, active: bool = false,
		fresh: float = -1.0) -> void:
	var micro := _fs(T_MICRO, s)
	var lead := _fs(T_LEAD, s)
	var mid := rect.position.y + rect.size.y * 0.5

	# The side that is about to kick gets a tinted bed and its own colour on the
	# label. Two rows of markers only tell a story if you can see which of them
	# is waiting to be filled.
	if active:
		draw_rect(Rect2(Vector2(rect.position.x - 4.0 * s, rect.position.y + 1.0 * s),
				Vector2(rect.size.x + 8.0 * s, rect.size.y - 2.0 * s)),
				Color(tone.r, tone.g, tone.b, 0.11 * alpha), true)

	var bar_h := rect.size.y * (0.74 if active else 0.60)
	draw_rect(Rect2(Vector2(rect.position.x, mid - bar_h * 0.5),
			Vector2((4.5 if active else 3.0) * s, bar_h)),
			_fade(tone, alpha * (1.0 if active else 0.9)), true)
	var label_x := rect.position.x + 10.0 * s
	if active:
		# A caret pointing at the row on turn: readable on a still frame, which a
		# pulse alone is not.
		var c := 3.4 * s
		draw_polygon(PackedVector2Array([
				Vector2(label_x, mid - c), Vector2(label_x + c * 1.5, mid),
				Vector2(label_x, mid + c)]),
				PackedColorArray([_fade(tone, alpha), _fade(tone, alpha), _fade(tone, alpha)]))
		label_x += c * 1.5 + 5.0 * s
	_tracked(Vector2(label_x, mid - micro * 0.62), label, micro,
			_fade(tone if active else INK_SOFT, alpha), 1.4 * s)

	# Sudden death can outgrow the strip, so only the latest attempts are shown.
	var first := maxi(marks.size() - slots, 0)
	var x := rect.position.x + label_w + pip_r
	for i in slots:
		var index := first + i
		var state := 0
		if index < marks.size():
			state = 1 if _is_goal(marks[index]) else 2
		var scale := 1.0
		var halo := 0.0
		# A negative age means "already there": the sliding panel never pops, only
		# the end screen deals its markers out one by one.
		if pop >= 0.0:
			var t := clampf((pop - POP_DELAY - float(i) * POP_STEP) / POP_TIME, 0.0, 1.0)
			if t <= 0.0:
				x += pip_r * 2.0 + pip_gap
				continue
			scale = _ease_out_back(t)
		elif fresh >= 0.0 and index == marks.size() - 1:
			# The marker this side has just filled. It pops in, then keeps a halo
			# for a moment, so a glance at the panel says which row moved.
			scale = _ease_out_back(clampf(fresh / POP_TIME, 0.0, 1.0))
			halo = 1.0 - clampf((fresh - POP_TIME) / HALO_TIME, 0.0, 1.0)
		elif active and index == marks.size():
			# The empty slot the active side is about to fill.
			halo = -(0.35 + 0.65 * (0.5 + 0.5 * sin(_clock * TAU / WAIT_PULSE)))
		_pip(Vector2(x, mid), pip_r * scale, state, tone, alpha, s, halo)
		x += pip_r * 2.0 + pip_gap

	var score := str(goals)
	var sw := _text_width(score, lead)
	_text(Vector2(rect.end.x - sw, mid - _font.get_ascent(lead) * 0.62), score, lead,
			_fade(INK, alpha))


## A shootout marker: pending ring, scored disc, missed cross.
##
## `halo` is the emphasis: POSITIVE for a marker that has just landed (a bloom
## around whatever it is), NEGATIVE for the empty slot the side on turn is about
## to fill (a pulsing ring, drawn in the row's own colour instead of the faint
## grey of a slot nobody is looking at). Zero is a marker with nothing to say.
func _pip(centre: Vector2, r: float, state: int, tone: Color, alpha: float, s: float,
		halo: float = 0.0) -> void:
	if r <= 0.5:
		return
	draw_arc(centre + Vector2(0.0, 1.4 * s), r, 0.0, TAU, 20, _fade(SHADOW, alpha),
			2.0 * s, true)
	if halo > 0.0:
		draw_circle(centre, r + 5.0 * s, Color(tone.r, tone.g, tone.b, 0.22 * halo * alpha))
		draw_arc(centre, r + 3.6 * s, 0.0, TAU, 30,
				Color(tone.r, tone.g, tone.b, 0.75 * halo * alpha), 1.8 * s, true)
	elif halo < 0.0:
		var beat := -halo
		draw_arc(centre, r + 2.2 * s, 0.0, TAU, 26,
				Color(tone.r, tone.g, tone.b, 0.55 * beat * alpha), 1.6 * s, true)
		draw_arc(centre, r, 0.0, TAU, 26,
				Color(tone.r, tone.g, tone.b, 0.85 * alpha), 2.0 * s, true)
		return
	match state:
		1:
			draw_circle(centre, r, _fade(tone, alpha))
			draw_arc(centre, r + 2.4 * s, 0.0, TAU, 26, _fade(tone, alpha * 0.30),
					1.6 * s, true)
			draw_circle(centre - Vector2(0.0, r * 0.30), r * 0.32,
					Color(1.0, 1.0, 1.0, 0.35 * alpha))
		2:
			draw_arc(centre, r, 0.0, TAU, 26, _fade(BAD, alpha * 0.9), 2.0 * s, true)
			var d := r * 0.44
			draw_line(centre + Vector2(-d, -d), centre + Vector2(d, d), _fade(BAD, alpha),
					2.0 * s, true)
			draw_line(centre + Vector2(-d, d), centre + Vector2(d, -d), _fade(BAD, alpha),
					2.0 * s, true)
		_:
			draw_arc(centre, r, 0.0, TAU, 26, _fade(INK_FAINT, alpha * 0.55), 1.6 * s, true)


# -------------------------------------------------------------------- end panel

func _draw_result(rect: Rect2, s: float) -> void:
	var alpha := clampf(_result_age / RESULT_FADE, 0.0, 1.0)
	var e := _ease_out_back(clampf(_result_age / 0.45, 0.0, 1.0))
	draw_rect(rect, Color(SCRIM.r, SCRIM.g, SCRIM.b, 0.88 * alpha), true)
	_gradient(Rect2(Vector2.ZERO, Vector2(rect.size.x, rect.size.y * 0.35)),
			Color(0.0, 0.0, 0.0, 0.35 * alpha), Color(0.0, 0.0, 0.0, 0.0))

	var two_rows := _mode == MODE_SEANCE
	var w := clampf(rect.size.x * 0.56, 460.0 * s, 860.0 * s)
	var h := (348.0 if two_rows else 292.0) * s
	var card := Rect2(Vector2(rect.size.x * 0.5 - w * 0.5,
			rect.size.y * 0.5 - h * 0.5 + lerpf(26.0 * s, 0.0, e)), Vector2(w, h))
	_plate(card, R_L * s, _fade(PLATE, alpha), _fade(BORDER, alpha), 16.0 * s)

	var tone := GOOD if _result_won else BAD
	var title := _result_title()
	var hero := _fs(T_HERO, s)
	var title_w := _tracked_width(title, hero, 3.0 * s)
	var y := card.position.y + PAD * 2.0 * s
	_tracked(Vector2(card.get_center().x - title_w * 0.5, y), title, hero, _fade(tone, alpha),
			3.0 * s)
	y += float(hero) * 1.25
	draw_rect(Rect2(Vector2(card.get_center().x - 40.0 * s, y), Vector2(80.0 * s, 2.0 * s)),
			_fade(tone, alpha * 0.8), true)
	y += 14.0 * s

	var lead := _fs(T_LEAD, s)
	var subtitle := _result_subtitle()
	var sw := _text_width(subtitle, lead)
	_text(Vector2(card.get_center().x - sw * 0.5, y), subtitle, lead, _fade(INK_SOFT, alpha))
	y += float(lead) * 1.9

	var pip_r := 9.5 * s
	var pip_gap := 8.0 * s
	var slots := mini(maxi(REGULATION_SLOTS, maxi(_player_marks.size(),
			_rival_marks.size())), MAX_SLOTS)
	var label_w := 120.0 * s
	var score_w := 56.0 * s
	var row_h := 44.0 * s
	var inner := Rect2(Vector2(card.position.x + PAD * 2.0 * s, y),
			Vector2(card.size.x - PAD * 4.0 * s, row_h))
	_draw_row(inner, "VOUS", _player_marks, _player_goals, slots, pip_r, pip_gap, label_w,
			score_w, ACCENT, alpha, _result_age, s)
	if two_rows:
		var sep_y := inner.position.y + row_h
		draw_line(Vector2(inner.position.x, sep_y), Vector2(inner.end.x, sep_y),
				_fade(BORDER, alpha), 1.0, true)
		_draw_row(Rect2(Vector2(inner.position.x, sep_y), inner.size), "ADVERSAIRE",
				_rival_marks, _rival_goals, slots, pip_r, pip_gap, label_w, score_w, RIVAL,
				alpha, _result_age, s)
		y = sep_y + row_h
	else:
		y = inner.position.y + row_h
	y += 12.0 * s

	var small := _fs(T_SMALL, s)
	for line in _result_lines():
		var lw := _text_width(line, small)
		_text(Vector2(card.get_center().x - lw * 0.5, y), line, small, _fade(INK_SOFT, alpha))
		y += float(small) * 1.5

	var micro := _fs(T_MICRO, s)
	var hint := "ENTRÉE : REJOUER      ÉCHAP : MENU"
	var hw := _tracked_width(hint, micro, 2.0 * s)
	var pulse := 0.55 + 0.45 * (0.5 + 0.5 * sin(_clock * 3.0))
	_tracked(Vector2(card.get_center().x - hw * 0.5, card.end.y - PAD * 2.0 * s - micro),
			hint, micro, _fade(INK_FAINT, alpha * pulse), 2.0 * s)


func _result_title() -> String:
	if _mode == MODE_DEFI:
		return "DÉFI TERMINÉ"
	if _mode == MODE_ENTRAINEMENT:
		return "SESSION TERMINÉE"
	return "VICTOIRE" if _result_won else "DÉFAITE"


func _result_subtitle() -> String:
	if _mode == MODE_SEANCE:
		var verb := "remportée" if _result_won else "perdue"
		return "Séance %s %d - %d" % [verb, _player_goals, _rival_goals]
	if _mode == MODE_DEFI:
		return "%d points" % _defi_points
	var attempts := _player_marks.size()
	return "%d but(s) sur %d tir(s)" % [_player_goals, attempts]


func _result_lines() -> PackedStringArray:
	var lines := PackedStringArray()
	if _best_streak > 0:
		lines.append("Meilleure série : %d" % _best_streak)
	if _mode == MODE_DEFI:
		lines.append("Série en cours : %d" % _streak)
	elif _player_marks.size() > 0:
		var pct := int(round(100.0 * float(_player_goals) / float(_player_marks.size())))
		lines.append("Réussite : %d %%" % pct)
	return lines


func _round_tag() -> String:
	if _mode != MODE_SEANCE:
		return "TIR %d" % (_round + 1)
	if _round >= REGULATION_SLOTS:
		return "MORT SUBITE"
	return "TIR %d / %d" % [_round + 1, REGULATION_SLOTS]


# ------------------------------------------------------------------- primitives

func _plate(rect: Rect2, radius: float, fill: Color, border: Color, shadow: float) -> void:
	var key := "f|%d|%s|%s|%d" % [int(round(radius)), fill.to_html(), border.to_html(),
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
			box.shadow_offset = Vector2(0.0, 3.0)
		_plate_cache[key] = box
	draw_style_box(box, rect)


## Same plate, rounded on the top corners only, for header bands.
func _plate_top(rect: Rect2, radius: float, fill: Color) -> void:
	var key := "t|%d|%s" % [int(round(radius)), fill.to_html()]
	var box: StyleBoxFlat = _plate_cache.get(key, null)
	if box == null:
		box = StyleBoxFlat.new()
		box.bg_color = fill
		box.corner_radius_top_left = int(round(radius))
		box.corner_radius_top_right = int(round(radius))
		box.corner_radius_bottom_left = 0
		box.corner_radius_bottom_right = 0
		_plate_cache[key] = box
	draw_style_box(box, rect)


## Vertex coloured quad rather than a stack of slices: sliced gradients leave a
## visible seam wherever two translucent bands overlap by a pixel.
func _gradient(rect: Rect2, top: Color, bottom: Color) -> void:
	var points := PackedVector2Array([
		rect.position, Vector2(rect.end.x, rect.position.y), rect.end,
		Vector2(rect.position.x, rect.end.y)])
	draw_polygon(points, PackedColorArray([top, top, bottom, bottom]))


func _text(top_left: Vector2, text: String, size: int, colour: Color) -> float:
	if text.is_empty():
		return 0.0
	var base := Vector2(top_left.x, top_left.y + _font.get_ascent(size))
	draw_string(_font, base + Vector2(1.5, 1.5), text, HORIZONTAL_ALIGNMENT_LEFT, -1.0,
			size, Color(0.0, 0.0, 0.0, SHADOW.a * colour.a))
	draw_string(_font, base, text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size, colour)
	return _text_width(text, size)


func _tracked(top_left: Vector2, text: String, size: int, colour: Color,
		tracking: float) -> float:
	var x := top_left.x
	var base_y := top_left.y + _font.get_ascent(size)
	for i in text.length():
		var ch := text.substr(i, 1)
		draw_string(_font, Vector2(x + 1.2, base_y + 1.2), ch, HORIZONTAL_ALIGNMENT_LEFT,
				-1.0, size, Color(0.0, 0.0, 0.0, SHADOW.a * colour.a))
		draw_string(_font, Vector2(x, base_y), ch, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size,
				colour)
		x += _text_width(ch, size) + tracking
	return x - top_left.x


func _text_width(text: String, size: int) -> float:
	return _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, size).x


func _tracked_width(text: String, size: int, tracking: float) -> float:
	if text.is_empty():
		return 0.0
	return _text_width(text, size) + tracking * float(text.length() - 1)


func _fs(scale: float, s: float) -> int:
	return maxi(int(round(float(_base_size) * scale * s)), 9)


func _fade(c: Color, alpha: float) -> Color:
	return Color(c.r, c.g, c.b, c.a * clampf(alpha, 0.0, 1.0))


func _approach(current: float, target: float, rate: float) -> float:
	return current + (target - current) * clampf(rate, 0.0, 1.0)


func _ease_out_back(t: float) -> float:
	var u := clampf(t, 0.0, 1.0) - 1.0
	return 1.0 + 2.70158 * u * u * u + 1.70158 * u * u


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


# ------------------------------------------------------------------- autoloads

## Looked up by path rather than by the `Shootout` identifier: no autoload is
## registered under `--check-only --script`, and a scoreboard instanced on its
## own must not take the tree down with it.
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
	if _shootout != null and _shootout.has_signal(&"series_changed") \
			and not _shootout.is_connected(&"series_changed", Callable(self, "refresh")):
		_shootout.connect(&"series_changed", Callable(self, "refresh"))


func _read_int(obj: Object, key: StringName, fallback: int) -> int:
	if obj == null or not is_instance_valid(obj):
		return fallback
	var v: Variant = obj.get(key)
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return int(v)
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


func _call_bool(obj: Object, method: StringName) -> bool:
	if obj == null or not is_instance_valid(obj) or not obj.has_method(method):
		return false
	var v: Variant = obj.call(method)
	return v is bool and (v as bool)


func _call_string(obj: Object, method: StringName) -> String:
	if obj == null or not is_instance_valid(obj) or not obj.has_method(method):
		return ""
	var v: Variant = obj.call(method)
	if v is String:
		return v as String
	return ""

