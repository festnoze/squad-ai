class_name MenuUi
extends Control
## Home screen, pause screen, settings and the controls list. One `Control`, one
## `_draw`, no interface scene and no imported font.
##
## The whole screen is an immediate mode list: `_compute_layout()` returns the
## rectangle of every row, `_draw()` paints them, and the input handlers hit test
## against the same rectangles. Layout therefore exists in exactly one place, and
## the keyboard and the mouse can never disagree about where a row is.
##
## Navigation is deliberately dual. The keyboard drives a focus index, the mouse
## moves that same index on hover, and both end up in `_activate()`. The focused
## row is marked by a plate that slides from the previous row rather than
## blinking into place, which is what makes a list feel driven rather than
## redrawn.
##
## Settings are not stored here. Every row reads its value from the `Game`
## autoload on each frame and writes back through `set_setting()`, which clamps
## and persists. The local dictionary is only a fallback for the case where the
## autoload is absent, so the screen still behaves when instanced on its own.
##
## Engine traps this file is built around: `_draw` only re-runs on
## `queue_redraw()`, and a node that must keep working while the tree is paused
## needs `PROCESS_MODE_ALWAYS` (`PROCESS_MODE_DISABLED` would kill both keyboard
## and mouse).

signal mode_chosen(mode: int)
signal resume_requested()
signal restart_requested()
signal quit_requested()

# ---------------------------------------------------------------- visual system

const INK := Color(0.94, 0.96, 0.99)
const INK_SOFT := Color(0.78, 0.83, 0.90)
## Raised for the daylight match: the old faint ink was authored against a black
## night screen, and it disappears the moment a plate sits on sunlit turf.
const INK_FAINT := Color(0.63, 0.68, 0.77)
## Solid. The pause screen sits over a sunlit pitch, and a plate that lets a
## quarter of that turf through has the grass reading between the letters of the
## list: see the note on the backings in src/ui/hud.gd.
const PLATE := Color(0.024, 0.033, 0.050, 0.97)
const TRACK := Color(0.010, 0.016, 0.026, 0.97)
const BORDER := Color(0.62, 0.72, 0.86, 0.26)
const SHADOW := Color(0.0, 0.0, 0.0, 0.55)
const BACKDROP := Color(0.012, 0.018, 0.028, 1.0)

const ACCENT := Color(0.16, 0.72, 1.00)
const ACCENT_DEEP := Color(0.07, 0.34, 0.58)
const GOOD := Color(0.31, 0.87, 0.48)
const BAD := Color(0.98, 0.33, 0.35)

const MARGIN := 30.0
const PAD := 16.0
const PAD_S := 8.0
const GAP := 5.0
const R_S := 4.0
const R := 8.0
const R_L := 16.0

const T_MICRO := 0.66
const T_SMALL := 0.82
const T_BODY := 1.05
const T_LEAD := 1.35
const T_TITLE := 2.1
const T_HERO := 4.2

const REF_HEIGHT := 900.0

## Row metrics, in reference pixels.
const ROW_H := 42.0
const VALUE_W := 190.0
const TRACK_W := 118.0
## Footer metrics: the gap between its two lines, and the tracking of the key
## list. Both are read by the layout, which sizes the footer plate from them.
const FOOT_LEAD := 7.0
const FOOT_TRACK := 1.4

## The key list, in French. Held as a constant because the layout has to measure
## it before it can size the plate it sits on.
const KEYS_LINE := "FLÈCHES : NAVIGUER  ·  ENTRÉE : VALIDER  ·  ÉCHAP : RETOUR"

# ------------------------------------------------------------------- behaviour

const PAGE_HOME := 0
const PAGE_PAUSE := 1
const PAGE_SETTINGS := 2
const PAGE_CONTROLS := 3

const KIND_ACTION := 0
const KIND_TOGGLE := 1
const KIND_SLIDER := 2
const KIND_CHOICE := 3
const KIND_INFO := 4

## Mirrors Shootout.Mode. Copied so the menu never depends on the autoload being
## registered just to lay itself out.
const MODE_SEANCE := 0
const MODE_ENTRAINEMENT := 1
const MODE_DEFI := 2

## Mirrors KeeperBrain.LEVEL_NAMES.
const LEVEL_NAMES: PackedStringArray = ["Débutant", "Confirmé", "Pro", "Légende"]

## Names of Shooter.SWEEP_SCALES, in the same order. Mirrored rather than read so
## the screen still lays itself out when no scene script is loaded.
const SWEEP_NAMES: PackedStringArray = ["Lent", "Normal", "Rapide", "Fulgurant"]

## Mirrors the defaults held by the Game autoload, used only as a fallback.
const DEFAULTS := {
	"mouse_sensitivity": 1.0,
	"master_volume": 0.8,
	"muted": false,
	"keeper_level": 1,
	"sweep_level": 1,
	"show_trajectory": true,
	"show_replay": true,
	"camera_shake": 0.7,
}

## The controls list, in French. Keys are described by position, because the
## InputMap is installed by physical keycode: the same key is Z on AZERTY and W
## on QWERTY.
const CONTROLS: Array = [
	["Viser", "Souris, flèches ou ZQSD"],
	["Armer la frappe", "Clic gauche ou Espace (maintenir)"],
	["Frapper", "Relâcher quand le curseur est dans le vert"],
	["Effet gauche / droite", "A et E"],
	["Feinte pendant la course", "Maj gauche"],
	["Tir suivant", "Entrée"],
	["Revoir le tir", "R"],
	["Changer de caméra", "C"],
	["Pause", "Échap"],
	["Recommencer", "F5"],
	["Plein écran", "F11"],
]

# ------------------------------------------------------------------------ state

var _font: Font = null
var _base_size: int = 16
var _clock: float = 0.0
## Wall clock the screen animates on, in milliseconds. Zero until the first frame.
var _real_ms: int = 0

var _game: Node = null
var _sfx: Node = null

var _page: int = PAGE_HOME
var _return_page: int = PAGE_HOME
## True when the menu sits over a live match, so the pitch stays readable behind.
var _over_game: bool = false

var _focus: int = 0
var _hover: int = -1
var _dragging: int = -1
var _focus_rect: Rect2 = Rect2()

var _local_settings: Dictionary = {}
var _plate_cache: Dictionary = {}
var _built: bool = false


func _ready() -> void:
	build()


## Prepares the screen. Idempotent, and safe to call before the autoloads exist.
func build() -> void:
	_font = ThemeDB.fallback_font
	_base_size = maxi(ThemeDB.fallback_font_size, 12)
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	# The pause screen has to answer while the tree is paused.
	process_mode = Node.PROCESS_MODE_ALWAYS
	# Only the first build decides the initial visibility. build() is idempotent
	# and the orchestrator may call it after opening a page (_ready runs bottom
	# up, so a child's build can land after a parent has already opened it), and
	# hiding the screen again there would look like a dropped call.
	if not _built:
		_built = true
		visible = false
	_bind_singletons()
	set_process(true)
	queue_redraw()


func open_home() -> void:
	_over_game = false
	_open(PAGE_HOME)


func open_pause() -> void:
	_over_game = true
	_open(PAGE_PAUSE)


func open_settings() -> void:
	_return_page = _page if visible and _page != PAGE_SETTINGS else PAGE_HOME
	if not visible:
		_over_game = false
	_open(PAGE_SETTINGS)


func close() -> void:
	if not visible:
		return
	visible = false
	_dragging = -1
	queue_redraw()


func is_open() -> bool:
	return visible


# ------------------------------------------------------------------ frame loop

## Real seconds, not the frame step. This screen is up while the game is paused
## and while it is in slow motion, and neither should change how fast the focus
## plate slides: `delta` is the scaled, clamped step, wall time is neither. Same
## reasoning as the note on the clock in src/ui/hud.gd.
func _process(_delta: float) -> void:
	if not visible:
		return
	var now := Time.get_ticks_msec()
	var step := 0.0
	if _real_ms > 0:
		step = clampf(float(now - _real_ms) * 0.001, 0.0, 1.0)
	_real_ms = now
	_clock += step
	var layout := _compute_layout()
	var rows: Array = layout["rows"]
	if _focus >= 0 and _focus < rows.size():
		var target: Rect2 = rows[_focus]
		if _focus_rect.size.x <= 0.0:
			_focus_rect = target
		else:
			var w := clampf(step * 18.0, 0.0, 1.0)
			_focus_rect = Rect2(_focus_rect.position.lerp(target.position, w),
					_focus_rect.size.lerp(target.size, w))
	queue_redraw()


## Shows a page. Asking for the page that is ALREADY up leaves the focus and the
## sliding focus plate exactly where they are: the orchestrator is free to call
## `open_home()` again for reasons of its own, and a screen that resets itself
## every time it is told to stay where it is never settles.
func _open(page: int) -> void:
	var already := visible and _page == page
	_page = page
	visible = true
	_dragging = -1
	_hover = -1
	_bind_singletons()
	if already:
		queue_redraw()
		return
	# The clock only runs while the screen is up, so the stamp it left behind last
	# time is stale.
	_real_ms = Time.get_ticks_msec()
	_focus_rect = Rect2()
	_focus = _first_selectable()
	queue_redraw()


# ----------------------------------------------------------------------- layout

## Single source of truth for the geometry of the screen. Both `_draw` and the
## input handlers call it, which is what keeps the mouse honest.
func _compute_layout() -> Dictionary:
	# The layout now measures text, so it needs a font even when it is asked for a
	# rectangle before build() has run.
	if _font == null:
		_font = ThemeDB.fallback_font
	var s := _scale()
	var rect := Rect2(Vector2.ZERO, size)
	var items := _current_items()
	var row_h := ROW_H * s
	var gap := GAP * s
	var title_h := (176.0 if _page == PAGE_HOME else 96.0) * s
	var list_h := float(items.size()) * row_h + float(maxi(items.size() - 1, 0)) * gap
	var card_w := clampf(rect.size.x * 0.46, 400.0 * s, 720.0 * s)
	if _page == PAGE_CONTROLS:
		card_w = clampf(rect.size.x * 0.60, 480.0 * s, 860.0 * s)
	var card_h := list_h + PAD * 2.0 * s
	# The footer is a plate docked under the card, not two lines adrift on the
	# turf, so its height is measured from the two lines it actually carries and
	# its width never lets the key list run off its own backing.
	var small := float(_fs(T_SMALL, s))
	var micro := float(_fs(T_MICRO, s))
	var foot_h := PAD_S * 2.0 * s + small * 1.15 + FOOT_LEAD * s + micro * 1.15
	var foot_gap := 10.0 * s
	var foot_w := maxf(card_w, _tracked_width(KEYS_LINE, int(micro), FOOT_TRACK * s)
			+ PAD * 2.0 * s)
	foot_w = minf(foot_w, rect.size.x - MARGIN * 2.0 * s)
	var block_h := title_h + card_h + foot_gap + foot_h
	var top := maxf((rect.size.y - block_h) * 0.5, MARGIN * s)
	var card := Rect2(Vector2(rect.size.x * 0.5 - card_w * 0.5, top + title_h),
			Vector2(card_w, card_h))
	var rows: Array[Rect2] = []
	var y := card.position.y + PAD * s
	for i in items.size():
		rows.append(Rect2(Vector2(card.position.x + PAD * s, y),
				Vector2(card.size.x - PAD * 2.0 * s, row_h)))
		y += row_h + gap
	return {
		"scale": s,
		"card": card,
		"rows": rows,
		"title_top": top,
		"title_h": title_h,
		"foot": Rect2(Vector2(rect.size.x * 0.5 - foot_w * 0.5, card.end.y + foot_gap),
				Vector2(foot_w, foot_h)),
		"foot_y": card.end.y + foot_gap,
	}


## Track and value rectangles inside a row, shared by the painter and the mouse.
func _value_rects(row: Rect2, s: float) -> Dictionary:
	var value_w := VALUE_W * s
	var track_w := TRACK_W * s
	var area := Rect2(Vector2(row.end.x - value_w, row.position.y), Vector2(value_w, row.size.y))
	var track := Rect2(Vector2(area.position.x, area.get_center().y - 3.0 * s),
			Vector2(track_w, 6.0 * s))
	return {"area": area, "track": track}


func _scale() -> float:
	return clampf(size.y / REF_HEIGHT, 0.7, 1.9)


# ------------------------------------------------------------------------ items

func _current_items() -> Array[Dictionary]:
	match _page:
		PAGE_PAUSE:
			return _items_pause()
		PAGE_SETTINGS:
			return _items_settings()
		PAGE_CONTROLS:
			return _items_controls()
		_:
			return _items_home()


func _items_home() -> Array[Dictionary]:
	var items: Array[Dictionary] = [
		{"id": "mode_seance", "label": "Séance de tirs au but", "kind": KIND_ACTION,
			"hint": "Cinq tirs chacun, puis mort subite."},
		{"id": "mode_entrainement", "label": "Entraînement", "kind": KIND_ACTION,
			"hint": "Tirez sans compter, le gardien reste en place."},
		{"id": "mode_defi", "label": "Défi", "kind": KIND_ACTION,
			"hint": "Enchaînez les buts, la série fait le score."},
		{"id": "settings", "label": "Réglages", "kind": KIND_ACTION, "hint": ""},
		{"id": "controls", "label": "Commandes", "kind": KIND_ACTION, "hint": ""},
		{"id": "quit", "label": "Quitter", "kind": KIND_ACTION, "hint": ""},
	]
	return items


func _items_pause() -> Array[Dictionary]:
	var items: Array[Dictionary] = [
		{"id": "resume", "label": "Reprendre", "kind": KIND_ACTION, "hint": ""},
		{"id": "restart", "label": "Recommencer la séance", "kind": KIND_ACTION, "hint": ""},
		{"id": "settings", "label": "Réglages", "kind": KIND_ACTION, "hint": ""},
		{"id": "controls", "label": "Commandes", "kind": KIND_ACTION, "hint": ""},
		{"id": "home", "label": "Retour à l'accueil", "kind": KIND_ACTION, "hint": ""},
		{"id": "quit", "label": "Quitter", "kind": KIND_ACTION, "hint": ""},
	]
	return items


func _items_settings() -> Array[Dictionary]:
	var items: Array[Dictionary] = [
		{"id": "mouse_sensitivity", "label": "Sensibilité de la souris", "kind": KIND_SLIDER,
			"key": "mouse_sensitivity", "min": 0.2, "max": 3.0, "step": 0.05,
			"format": "num", "hint": "Vitesse du réticule pendant la visée."},
		{"id": "master_volume", "label": "Volume", "kind": KIND_SLIDER,
			"key": "master_volume", "min": 0.0, "max": 1.0, "step": 0.05,
			"format": "pct", "hint": ""},
		{"id": "muted", "label": "Son", "kind": KIND_TOGGLE, "key": "muted",
			"invert": true, "on": "Actif", "off": "Coupé", "hint": ""},
		{"id": "keeper_level", "label": "Difficulté : gardien", "kind": KIND_CHOICE,
			"key": "keeper_level", "options": LEVEL_NAMES,
			"hint": "Il lit mieux et plonge plus vite, la physique ne change pas."},
		{"id": "sweep_level", "label": "Difficulté : curseur de frappe", "kind": KIND_CHOICE,
			"key": "sweep_level", "options": SWEEP_NAMES,
			"hint": "Plus le curseur file vite, plus la frappe nette est dure."},
		{"id": "show_trajectory", "label": "Aide à la visée", "kind": KIND_TOGGLE,
			"key": "show_trajectory", "invert": false, "on": "Affichée", "off": "Masquée",
			"hint": "Trace la courbe prévue du ballon."},
		{"id": "show_replay", "label": "Ralenti après le tir", "kind": KIND_TOGGLE,
			"key": "show_replay", "invert": false, "on": "Oui", "off": "Non", "hint": ""},
		{"id": "camera_shake", "label": "Secousses de caméra", "kind": KIND_SLIDER,
			"key": "camera_shake", "min": 0.0, "max": 1.0, "step": 0.05, "format": "pct",
			"hint": ""},
		{"id": "reset", "label": "Réinitialiser les réglages", "kind": KIND_ACTION,
			"hint": ""},
		{"id": "back", "label": "Retour", "kind": KIND_ACTION, "hint": ""},
	]
	return items


func _items_controls() -> Array[Dictionary]:
	var items: Array[Dictionary] = []
	for entry in CONTROLS:
		var pair: Array = entry
		items.append({"id": "info", "label": String(pair[0]), "kind": KIND_INFO,
			"value_text": String(pair[1]), "hint": ""})
	items.append({"id": "back", "label": "Retour", "kind": KIND_ACTION, "hint": ""})
	return items


func _first_selectable() -> int:
	var items := _current_items()
	for i in items.size():
		if int(items[i]["kind"]) != KIND_INFO:
			return i
	return 0


# ---------------------------------------------------------------------- drawing

func _draw() -> void:
	if _font == null or not visible:
		return
	var rect := Rect2(Vector2.ZERO, size)
	if rect.size.x < 32.0 or rect.size.y < 32.0:
		return
	var layout := _compute_layout()
	var s: float = layout["scale"]
	var items := _current_items()
	var rows: Array = layout["rows"]
	# There is no entrance fade any more, and `fade` is kept only because every
	# painter below takes it. A screen that is up is a screen being READ, and every
	# frame it spends translucent is a frame the sunlit pitch is legible straight
	# through the list. The entrance was also measured from the last call to
	# `_open`, and the orchestrator reopens the page it is already on often enough
	# that the fade never reached the end: the home screen simply lived at half
	# opacity. A screen is either up or it is not.
	var fade := 1.0

	_draw_backdrop(rect, s, fade)
	_draw_title(rect, layout, s, fade)

	var card: Rect2 = layout["card"]
	_plate(card, R_L * s, _fade(PLATE, fade), _fade(BORDER, fade), 14.0 * s)

	if _focus >= 0 and _focus < rows.size() and _focus_rect.size.x > 0.0:
		_draw_focus(_focus_rect, s, fade)

	for i in items.size():
		var row: Rect2 = rows[i]
		_draw_row(items[i], row, i == _focus, s, fade)

	_draw_footer(rect, layout, items, s, fade)


func _draw_backdrop(rect: Rect2, s: float, fade: float) -> void:
	if _over_game:
		draw_rect(rect, Color(BACKDROP.r, BACKDROP.g, BACKDROP.b, 0.74 * fade), true)
	else:
		draw_rect(rect, Color(BACKDROP.r, BACKDROP.g, BACKDROP.b, 0.985 * fade), true)
		# A cold floodlit glow rising from the bottom of the frame, so the home
		# screen reads as a stadium at night and not as a black rectangle.
		var glow_h := rect.size.y * 0.42
		_gradient(Rect2(Vector2(0.0, rect.size.y - glow_h), Vector2(rect.size.x, glow_h)),
				Color(ACCENT_DEEP.r, ACCENT_DEEP.g, ACCENT_DEEP.b, 0.0),
				Color(ACCENT_DEEP.r, ACCENT_DEEP.g, ACCENT_DEEP.b, 0.20 * fade))
		# The goal mouth, drawn as three thin lines low in the frame.
		var mouth_w := rect.size.x * 0.34
		var mouth_h := mouth_w * 0.333
		var base_y := rect.size.y - 24.0 * s
		var left := rect.size.x * 0.5 - mouth_w * 0.5
		var col := Color(INK.r, INK.g, INK.b, 0.05 * fade)
		draw_line(Vector2(left, base_y), Vector2(left, base_y - mouth_h), col, 3.0 * s, true)
		draw_line(Vector2(left + mouth_w, base_y), Vector2(left + mouth_w, base_y - mouth_h),
				col, 3.0 * s, true)
		draw_line(Vector2(left, base_y - mouth_h), Vector2(left + mouth_w, base_y - mouth_h),
				col, 3.0 * s, true)


func _draw_title(rect: Rect2, layout: Dictionary, s: float, fade: float) -> void:
	var top: float = layout["title_top"]
	var centre := rect.size.x * 0.5
	if _page == PAGE_HOME:
		var hero := _fs(T_HERO, s)
		var word := "GOAL"
		var tracking := 12.0 * s
		var w := _tracked_width(word, hero, tracking)
		_tracked(Vector2(centre - w * 0.5, top), word, hero, _fade(INK, fade), tracking)
		var rule_y := top + float(hero) * 1.18
		draw_rect(Rect2(Vector2(centre - w * 0.5, rule_y), Vector2(w, 2.0 * s)),
				_fade(ACCENT, fade * 0.9), true)
		var small := _fs(T_SMALL, s)
		var sub := "SÉANCE DE TIRS AU BUT"
		var sw := _tracked_width(sub, small, 4.0 * s)
		_tracked(Vector2(centre - sw * 0.5, rule_y + 12.0 * s), sub, small,
				_fade(INK_FAINT, fade), 4.0 * s)
		return

	var title := _fs(T_TITLE, s)
	var label := _page_title()
	var tw := _tracked_width(label, title, 5.0 * s)
	_tracked(Vector2(centre - tw * 0.5, top + 12.0 * s), label, title, _fade(INK, fade),
			5.0 * s)
	draw_rect(Rect2(Vector2(centre - tw * 0.5, top + 12.0 * s + float(title) * 1.16),
			Vector2(tw, 2.0 * s)), _fade(ACCENT, fade * 0.9), true)
	if _page == PAGE_CONTROLS:
		var micro := _fs(T_MICRO, s)
		var note := "Clavier reconnu par position : ZQSD sur AZERTY, WASD sur QWERTY."
		var nw := _text_width(note, micro)
		_text(Vector2(centre - nw * 0.5, top + 12.0 * s + float(title) * 1.16 + 10.0 * s),
				note, micro, _fade(INK_FAINT, fade))


func _page_title() -> String:
	match _page:
		PAGE_PAUSE:
			return "PAUSE"
		PAGE_SETTINGS:
			return "RÉGLAGES"
		PAGE_CONTROLS:
			return "COMMANDES"
		_:
			return "GOAL"


## The focus plate. It slides between rows, which is the only thing that makes a
## hand drawn list feel like a real menu.
func _draw_focus(rect: Rect2, s: float, fade: float) -> void:
	var pulse := 0.16 + 0.05 * sin(_clock * 3.2)
	_plate(rect.grow(2.0 * s), R * s, _fade(ACCENT, fade * pulse),
			_fade(ACCENT, fade * 0.55), 0.0)
	draw_rect(Rect2(rect.position - Vector2(3.0 * s, 0.0), Vector2(4.0 * s, rect.size.y)),
			_fade(ACCENT, fade), true)


func _draw_row(item: Dictionary, row: Rect2, focused: bool, s: float, fade: float) -> void:
	var kind := int(item["kind"])
	var body := _fs(T_BODY, s)
	var label := String(item["label"])
	var tone := INK if focused else INK_SOFT
	var slide := 8.0 * s if focused else 0.0
	var text_y := row.get_center().y - float(body) * 0.62
	_text(Vector2(row.position.x + PAD_S * s + slide, text_y), label, body, _fade(tone, fade))

	match kind:
		KIND_SLIDER:
			_draw_slider(item, row, focused, s, fade)
		KIND_TOGGLE, KIND_CHOICE:
			_draw_choice(item, row, focused, s, fade)
		KIND_INFO:
			var value := String(item["value_text"])
			var vw := _text_width(value, body)
			_text(Vector2(row.end.x - PAD_S * s - vw, text_y), value, body,
					_fade(INK, fade * 0.92))
		_:
			if focused:
				# A small chevron on the right edge marks the actionable row.
				var c := row.get_center()
				var x := row.end.x - PAD_S * s - 8.0 * s
				var a := 5.0 * s
				draw_colored_polygon(PackedVector2Array([
						Vector2(x, c.y - a), Vector2(x + a, c.y), Vector2(x, c.y + a)]),
						_fade(ACCENT, fade))


func _draw_slider(item: Dictionary, row: Rect2, focused: bool, s: float, fade: float) -> void:
	var rects := _value_rects(row, s)
	var track: Rect2 = rects["track"]
	var lo := float(item["min"])
	var hi := float(item["max"])
	var value := _setting_float(String(item["key"]), float(DEFAULTS.get(item["key"], lo)))
	var t := clampf(inverse_lerp(lo, hi, value), 0.0, 1.0)
	_plate(track, track.size.y * 0.5, _fade(TRACK, fade), Color(0.0, 0.0, 0.0, 0.0), 0.0)
	if t > 0.001:
		_plate(Rect2(track.position, Vector2(track.size.x * t, track.size.y)),
				track.size.y * 0.5, _fade(ACCENT if focused else ACCENT_DEEP, fade),
				Color(0.0, 0.0, 0.0, 0.0), 0.0)
	var knob := Vector2(track.position.x + track.size.x * t, track.get_center().y)
	draw_circle(knob + Vector2(0.0, 1.5 * s), 7.0 * s, _fade(SHADOW, fade))
	draw_circle(knob, 6.5 * s, _fade(INK if focused else INK_SOFT, fade))

	var small := _fs(T_SMALL, s)
	var text := _format_value(item, value)
	var tw := _text_width(text, small)
	_text(Vector2(row.end.x - PAD_S * s - tw, row.get_center().y - float(small) * 0.62),
			text, small, _fade(INK, fade))


func _draw_choice(item: Dictionary, row: Rect2, focused: bool, s: float, fade: float) -> void:
	var rects := _value_rects(row, s)
	var area: Rect2 = rects["area"]
	var box := Rect2(Vector2(area.position.x + 18.0 * s, row.get_center().y - 12.0 * s),
			Vector2(area.size.x - 36.0 * s - PAD_S * s, 24.0 * s))
	var text := _choice_text(item)
	var tone := GOOD if _choice_is_on(item) else INK_SOFT
	if int(item["kind"]) == KIND_CHOICE:
		tone = INK
	_plate(box, R_S * s, _fade(TRACK, fade * 0.8), _fade(BORDER, fade), 0.0)
	var small := _fs(T_SMALL, s)
	var tw := _text_width(text, small)
	_text(Vector2(box.get_center().x - tw * 0.5, box.get_center().y - float(small) * 0.62),
			text, small, _fade(tone, fade))
	var arrow := _fade(ACCENT if focused else INK_FAINT, fade)
	var a := 5.0 * s
	var cy := box.get_center().y
	draw_colored_polygon(PackedVector2Array([
			Vector2(box.position.x - 7.0 * s, cy), Vector2(box.position.x - 1.0 * s, cy - a),
			Vector2(box.position.x - 1.0 * s, cy + a)]), arrow)
	draw_colored_polygon(PackedVector2Array([
			Vector2(box.end.x + 7.0 * s, cy), Vector2(box.end.x + 1.0 * s, cy - a),
			Vector2(box.end.x + 1.0 * s, cy + a)]), arrow)


## The hint for the focused row and the key list. Both used to be low alpha ink
## laid straight onto the pitch at the very bottom of the frame: on a daylight
## match that is white on bright turf, and it reads as text belonging to nothing.
## They now share a plate docked under the card, so they are visibly part of the
## same object as the list they describe, and they carry their own contrast the
## way every other element of the interface already does.
func _draw_footer(rect: Rect2, layout: Dictionary, items: Array[Dictionary], s: float,
		fade: float) -> void:
	var foot: Rect2 = layout["foot"]
	var centre := rect.size.x * 0.5
	var small := _fs(T_SMALL, s)
	var micro := _fs(T_MICRO, s)
	var hint := ""
	if _focus >= 0 and _focus < items.size():
		hint = String(items[_focus].get("hint", ""))
	_plate(foot, R * s, _fade(PLATE, fade), _fade(BORDER, fade), 12.0 * s)
	# A stub of accent on the leading edge, the same mark the focused row carries,
	# which is what says "this line is about that row".
	draw_rect(Rect2(Vector2(foot.position.x, foot.position.y + foot.size.y * 0.24),
			Vector2(3.0 * s, foot.size.y * 0.52)), _fade(ACCENT, fade * 0.8), true)
	var y := foot.position.y + PAD_S * s
	if not hint.is_empty():
		var hw := _text_width(hint, small)
		_text(Vector2(centre - hw * 0.5, y), hint, small, _fade(INK_SOFT, fade))
	y += float(small) * 1.15 + FOOT_LEAD * s
	var kw := _tracked_width(KEYS_LINE, micro, FOOT_TRACK * s)
	_tracked(Vector2(centre - kw * 0.5, y), KEYS_LINE, micro, _fade(INK_FAINT, fade),
			FOOT_TRACK * s)


# ------------------------------------------------------------------------ input

func _unhandled_input(event: InputEvent) -> void:
	if not visible:
		return
	if _pressed(event, ["aim_up", "ui_up"], [KEY_UP, KEY_W, KEY_Z], true):
		_move_focus(-1)
		_consume()
		return
	if _pressed(event, ["aim_down", "ui_down"], [KEY_DOWN, KEY_S], true):
		_move_focus(1)
		_consume()
		return
	if _pressed(event, ["aim_left", "ui_left"], [KEY_LEFT, KEY_A, KEY_Q], true):
		_adjust(_focus, -1)
		_consume()
		return
	if _pressed(event, ["aim_right", "ui_right"], [KEY_RIGHT, KEY_D], true):
		_adjust(_focus, 1)
		_consume()
		return
	if _pressed(event, ["menu_accept", "ui_accept"], [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE],
			false):
		_activate(_focus, Vector2(-1.0, -1.0))
		_consume()
		return
	if _pressed(event, ["menu_back", "pause", "ui_cancel"], [KEY_ESCAPE, KEY_BACKSPACE],
			false):
		_back()
		_consume()


func _gui_input(event: InputEvent) -> void:
	if not visible:
		return
	var s := _scale()
	var motion := event as InputEventMouseMotion
	if motion != null:
		if _dragging >= 0:
			_drag_slider(_dragging, motion.position, s)
			accept_event()
			return
		var index := _row_at(motion.position)
		if index != _hover:
			_hover = index
			if index >= 0 and index != _focus:
				_focus = index
				_play("ui_move")
			queue_redraw()
		return
	var button := event as InputEventMouseButton
	if button == null:
		return
	if button.button_index == MOUSE_BUTTON_LEFT:
		if button.pressed:
			var index := _row_at(button.position)
			if index >= 0:
				_focus = index
				var item := _current_items()[index]
				if int(item["kind"]) == KIND_SLIDER:
					var track: Rect2 = _value_rects(_row_rect(index), s)["track"]
					if track.grow(10.0 * s).has_point(button.position):
						_dragging = index
						_drag_slider(index, button.position, s)
						accept_event()
						return
				_activate(index, button.position)
		else:
			_dragging = -1
		accept_event()
		return
	if button.pressed and (button.button_index == MOUSE_BUTTON_WHEEL_UP
			or button.button_index == MOUSE_BUTTON_WHEEL_DOWN):
		var index := _row_at(button.position)
		if index >= 0:
			_focus = index
			_adjust(index, 1 if button.button_index == MOUSE_BUTTON_WHEEL_UP else -1)
		accept_event()


## True when the event fires one of the named actions, or one of the raw keys.
## Both keycode and physical keycode are tested so the fallback works on AZERTY
## and QWERTY alike, and so the menu still answers before Game installs its map.
func _pressed(event: InputEvent, actions: Array, keys: Array, allow_echo: bool) -> bool:
	for entry in actions:
		var action := StringName(entry)
		if InputMap.has_action(action) and event.is_action_pressed(action, allow_echo):
			return true
	var key := event as InputEventKey
	if key == null or not key.pressed:
		return false
	if key.echo and not allow_echo:
		return false
	return keys.has(key.keycode) or keys.has(key.physical_keycode)


func _consume() -> void:
	var vp := get_viewport()
	if vp != null:
		vp.set_input_as_handled()


func _row_at(point: Vector2) -> int:
	var rows: Array = _compute_layout()["rows"]
	var items := _current_items()
	for i in rows.size():
		if i < items.size() and int(items[i]["kind"]) == KIND_INFO:
			continue
		var r: Rect2 = rows[i]
		if r.has_point(point):
			return i
	return -1


func _row_rect(index: int) -> Rect2:
	var rows: Array = _compute_layout()["rows"]
	if index >= 0 and index < rows.size():
		return rows[index]
	return Rect2()


func _move_focus(direction: int) -> void:
	var items := _current_items()
	if items.is_empty():
		return
	var index := _focus
	for _step in items.size():
		index = wrapi(index + direction, 0, items.size())
		if int(items[index]["kind"]) != KIND_INFO:
			break
	if index != _focus:
		_focus = index
		_play("ui_move")
		queue_redraw()


func _activate(index: int, at: Vector2) -> void:
	var items := _current_items()
	if index < 0 or index >= items.size():
		return
	var item := items[index]
	var kind := int(item["kind"])
	if kind == KIND_INFO:
		return
	if kind == KIND_SLIDER:
		_adjust(index, 1)
		return
	if kind == KIND_TOGGLE or kind == KIND_CHOICE:
		var direction := 1
		if at.x >= 0.0:
			var area: Rect2 = _value_rects(_row_rect(index), _scale())["area"]
			if at.x < area.get_center().x:
				direction = -1
		_adjust(index, direction)
		return

	var id := String(item["id"])
	match id:
		"mode_seance":
			_play("ui_select")
			close()
			mode_chosen.emit(MODE_SEANCE)
		"mode_entrainement":
			_play("ui_select")
			close()
			mode_chosen.emit(MODE_ENTRAINEMENT)
		"mode_defi":
			_play("ui_select")
			close()
			mode_chosen.emit(MODE_DEFI)
		"settings":
			_play("ui_select")
			_return_page = _page
			_open(PAGE_SETTINGS)
		"controls":
			_play("ui_select")
			_return_page = _page
			_open(PAGE_CONTROLS)
		"resume":
			_play("ui_back")
			close()
			resume_requested.emit()
		"restart":
			_play("ui_select")
			close()
			restart_requested.emit()
		"home":
			_play("ui_back")
			_over_game = false
			_open(PAGE_HOME)
		"reset":
			_play("ui_select")
			_reset_settings()
		"back":
			_back()
		"quit":
			_play("ui_select")
			quit_requested.emit()
		_:
			push_warning("MenuUi: entrée de menu inconnue '%s'" % id)


func _back() -> void:
	match _page:
		PAGE_SETTINGS, PAGE_CONTROLS:
			_play("ui_back")
			_open(_return_page)
		PAGE_PAUSE:
			_play("ui_back")
			close()
			resume_requested.emit()
		_:
			_play("ui_back")


## One notch left or right on a value row.
func _adjust(index: int, direction: int) -> void:
	var items := _current_items()
	if index < 0 or index >= items.size():
		return
	var item := items[index]
	var kind := int(item["kind"])
	var key := String(item.get("key", ""))
	match kind:
		KIND_SLIDER:
			var lo := float(item["min"])
			var hi := float(item["max"])
			var step := float(item["step"])
			var value := _setting_float(key, float(DEFAULTS.get(key, lo)))
			value = clampf(snappedf(value + step * float(direction), step), lo, hi)
			_write_setting(key, value)
			_play("ui_move")
		KIND_TOGGLE:
			_write_setting(key, not _setting_bool(key, bool(DEFAULTS.get(key, false))))
			_play("ui_select")
		KIND_CHOICE:
			var options: PackedStringArray = item["options"]
			if options.is_empty():
				return
			var current := _setting_int(key, int(DEFAULTS.get(key, 0)))
			_write_setting(key, wrapi(current + direction, 0, options.size()))
			_play("ui_move")
		_:
			return
	queue_redraw()


func _drag_slider(index: int, point: Vector2, s: float) -> void:
	var items := _current_items()
	if index < 0 or index >= items.size():
		return
	var item := items[index]
	if int(item["kind"]) != KIND_SLIDER:
		return
	var track: Rect2 = _value_rects(_row_rect(index), s)["track"]
	if track.size.x <= 0.0:
		return
	var t := clampf((point.x - track.position.x) / track.size.x, 0.0, 1.0)
	var lo := float(item["min"])
	var hi := float(item["max"])
	var step := float(item["step"])
	var value := clampf(snappedf(lerpf(lo, hi, t), step), lo, hi)
	_write_setting(String(item["key"]), value)
	queue_redraw()


# --------------------------------------------------------------------- settings

func _choice_text(item: Dictionary) -> String:
	if int(item["kind"]) == KIND_CHOICE:
		var options: PackedStringArray = item["options"]
		var key := String(item["key"])
		var index := clampi(_setting_int(key, int(DEFAULTS.get(key, 0))), 0,
				maxi(options.size() - 1, 0))
		return options[index] if not options.is_empty() else ""
	return String(item["on"]) if _choice_is_on(item) else String(item["off"])


## For a toggle, "on" means the pleasant state, which is not always the raw
## value: `muted` is displayed as "Son : Actif" when it is false.
func _choice_is_on(item: Dictionary) -> bool:
	if int(item["kind"]) != KIND_TOGGLE:
		return false
	var key := String(item["key"])
	var raw := _setting_bool(key, bool(DEFAULTS.get(key, false)))
	return not raw if bool(item.get("invert", false)) else raw


func _format_value(item: Dictionary, value: float) -> String:
	if String(item.get("format", "num")) == "pct":
		return "%d %%" % int(round(value * 100.0))
	return "%.2f" % value


func _write_setting(key: String, value: Variant) -> void:
	if key.is_empty():
		return
	_local_settings[key] = value
	if _game != null and is_instance_valid(_game) and _game.has_method(&"set_setting"):
		_game.call(&"set_setting", key, value)


func _reset_settings() -> void:
	_local_settings.clear()
	if _game != null and is_instance_valid(_game) and _game.has_method(&"reset_settings"):
		_game.call(&"reset_settings")
	else:
		for key in DEFAULTS:
			_local_settings[key] = DEFAULTS[key]
	queue_redraw()


func _setting_raw(key: String) -> Variant:
	if _game != null and is_instance_valid(_game):
		var v: Variant = _game.get(StringName(key))
		if v != null:
			return v
	if _local_settings.has(key):
		return _local_settings[key]
	return null


func _setting_float(key: String, fallback: float) -> float:
	var v: Variant = _setting_raw(key)
	if typeof(v) == TYPE_FLOAT or typeof(v) == TYPE_INT:
		return float(v)
	return fallback


func _setting_int(key: String, fallback: int) -> int:
	var v: Variant = _setting_raw(key)
	if typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT:
		return int(v)
	return fallback


func _setting_bool(key: String, fallback: bool) -> bool:
	var v: Variant = _setting_raw(key)
	if typeof(v) == TYPE_BOOL:
		return bool(v)
	return fallback


# ------------------------------------------------------------------- primitives

func _plate(rect: Rect2, radius: float, fill: Color, border: Color, shadow: float) -> void:
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
			box.shadow_offset = Vector2(0.0, 4.0)
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
		draw_string(_font, Vector2(x + 1.4, base_y + 1.4), ch, HORIZONTAL_ALIGNMENT_LEFT,
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


# ------------------------------------------------------------------- autoloads

## Autoloads are resolved by path, never by identifier: none of them exists when
## a file is compiled with `--check-only --script`, and the menu must survive
## being instanced on its own.
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
	_game = root.get_node_or_null(^"Game")
	_sfx = root.get_node_or_null(^"Sfx")
	if _game != null and _game.has_signal(&"settings_changed") \
			and not _game.is_connected(&"settings_changed", Callable(self, "queue_redraw")):
		_game.connect(&"settings_changed", Callable(self, "queue_redraw"))


func _play(id: String) -> void:
	if _sfx != null and is_instance_valid(_sfx) and _sfx.has_method(&"play"):
		_sfx.call(&"play", id)
