class_name QualityGovernor
extends Node
## Keeps the frame rate up by giving away the cheapest thing first.
##
## The pocket is streamed, so the load swings hard: a wheat field at noon and a
## village under fire with two squads fighting in it are not the same frame. A
## fixed setting has to be chosen for the worst case, which wastes the other
## ninety percent of the campaign. This walks a ladder instead, one rung at a
## time, and climbs back up when the pressure is off.
##
## What it gives away, in order of how little it is missed:
##
##   1. Render scale. The 3D image is drawn smaller and upscaled; the HUD stays
##      native, so text and the compass are never touched.
##   2. Prop draw distance, which is what "fewer objects" means in practice.
##      Distant trees and hedges dissolve out rather than popping.
##   3. Shadow filtering, then shadow map size.
##   4. Anti aliasing.
##
## Deliberately NOT touched: `Game.view_distance`. It is a saved preference and
## a governor that rewrites the player's settings file behind their back is a
## bug, not a feature. Prop distance is the runtime equivalent and costs the
## same frame time.

signal level_changed(level: int)

## Rungs of the ladder, worst frame rate last.
const LEVEL_COUNT := 5

## Frame time we are aiming to stay under, in milliseconds. 16.7 ms is 60 fps.
const TARGET_MS := 16.7
## Sustained frame time above this drops a rung.
const DROP_MS := 21.0
## Sustained frame time below this earns one back.
const RAISE_MS := 13.2
## Seconds of sustained pressure before dropping. Short: a stutter the player
## can feel should be answered quickly.
const DROP_HOLD := 1.2
## Seconds of sustained headroom before climbing back. Much longer, so the
## picture does not pulse between two rungs on the edge of the threshold.
const RAISE_HOLD := 6.0
## Seconds after any change before another is allowed.
const CHANGE_COOLDOWN := 2.5
## Frames ignored after boot. The world is still streaming and the first
## seconds are never representative.
const WARMUP_FRAMES := 150

## Smoothing of the frame time average, per second. Low enough that one long
## frame cannot move the ladder on its own.
const SMOOTHING := 3.5

## Prop draw distance of each rung, in metres, and how wide the dissolve is.
const PROP_DISTANCE: PackedFloat32Array = [520.0, 430.0, 340.0, 260.0, 190.0]
const PROP_FADE := 28.0
## Render scale of each rung.
const RENDER_SCALE: PackedFloat32Array = [1.0, 0.88, 0.78, 0.68, 0.58]
## MSAA of each rung, as `Viewport.MSAA_*`.
const MSAA: PackedInt32Array = [2, 2, 1, 0, 0]
## Directional shadow soft filter quality of each rung.
const SHADOW_FILTER: PackedInt32Array = [3, 2, 1, 0, 0]
## Directional shadow map size of each rung.
const SHADOW_SIZE: PackedInt32Array = [4096, 4096, 2048, 2048, 1024]

## Group every prop batch and every loose prop node joins, so a rung change can
## reach them all without the chunks knowing this class exists.
const PROP_GROUP := "prop_batch"

## Read by the chunks when they spawn vegetation, so a tile streamed in after a
## rung change is born at the right distance instead of at the default.
static var prop_draw_distance: float = PROP_DISTANCE[0]

var _viewport: Viewport = null
var _level: int = 0
var _enabled: bool = true
var _smooth_ms: float = TARGET_MS
var _frames: int = 0
var _over: float = 0.0
var _under: float = 0.0
var _cooldown: float = 0.0
## Worst frame of the last second, which is what a stutter actually feels like.
var _worst_ms: float = 0.0
var _worst_window: float = 0.0
var _worst_shown: float = 0.0


func _ready() -> void:
	process_priority = 40
	set_process(true)


func setup(viewport: Viewport) -> void:
	_viewport = viewport
	_level = 0
	_smooth_ms = TARGET_MS
	_apply(0)


## Turns the ladder off and restores full quality. The reading stays live, so
## the debug overlay still reports the frame rate.
func set_enabled(on: bool) -> void:
	if on == _enabled:
		return
	_enabled = on
	if not on and _level != 0:
		_level = 0
		_apply(0)
		level_changed.emit(0)


func is_enabled() -> bool:
	return _enabled


## Throws away the pressure gathered so far, without moving the ladder.
##
## Called while the world is still priming and the player is frozen. Those
## frames are dominated by streaming and mesh building, not by what is on
## screen, and letting them count drives the ladder straight to its worst rung
## for a load the player was never going to see anyway.
func defer() -> void:
	_over = 0.0
	_under = 0.0
	_smooth_ms = TARGET_MS
	_worst_ms = 0.0
	_worst_window = 0.0
	_cooldown = maxf(_cooldown, 0.5)


func level() -> int:
	return _level


func fps() -> float:
	if _smooth_ms <= 0.001:
		return 0.0
	return 1000.0 / _smooth_ms


func frame_ms() -> float:
	return _smooth_ms


## Worst frame of the last full second, in milliseconds.
func worst_ms() -> float:
	return _worst_shown


## One line for the debug overlay.
func debug_line() -> String:
	var state := "auto" if _enabled else "fixe"
	return "IMAGES  %.0f fps   %.1f ms   pire %.1f ms   qualite %d/%d %s   echelle %.2f" % [
		fps(), _smooth_ms, _worst_shown, _level, LEVEL_COUNT - 1, state,
		RENDER_SCALE[_level]]


func _process(delta: float) -> void:
	var raw_ms: float = delta * 1000.0
	_frames += 1

	# Exponential average, framed in seconds so it behaves the same whatever the
	# frame rate happens to be.
	var k: float = clampf(delta * SMOOTHING, 0.0, 1.0)
	_smooth_ms += (raw_ms - _smooth_ms) * k

	_worst_ms = maxf(_worst_ms, raw_ms)
	_worst_window += delta
	if _worst_window >= 1.0:
		_worst_shown = _worst_ms
		_worst_ms = 0.0
		_worst_window = 0.0

	if not _enabled or _frames < WARMUP_FRAMES:
		return

	if _cooldown > 0.0:
		_cooldown -= delta
		return

	if _smooth_ms > DROP_MS:
		_over += delta
		_under = 0.0
	elif _smooth_ms < RAISE_MS:
		_under += delta
		_over = 0.0
	else:
		_over = 0.0
		_under = 0.0

	if _over >= DROP_HOLD and _level < LEVEL_COUNT - 1:
		_step(_level + 1)
	elif _under >= RAISE_HOLD and _level > 0:
		_step(_level - 1)


func _step(to: int) -> void:
	_level = clampi(to, 0, LEVEL_COUNT - 1)
	_over = 0.0
	_under = 0.0
	_cooldown = CHANGE_COOLDOWN
	# The average is about to stop describing anything: reset it to the target
	# so the very next reading cannot immediately trigger another step on
	# evidence gathered under the previous settings.
	_smooth_ms = TARGET_MS
	_apply(_level)
	level_changed.emit(_level)


func _apply(lv: int) -> void:
	prop_draw_distance = PROP_DISTANCE[lv]
	_push_prop_distance()

	if _viewport != null and is_instance_valid(_viewport):
		_viewport.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
		_viewport.scaling_3d_scale = RENDER_SCALE[lv]
		_viewport.msaa_3d = MSAA[lv] as Viewport.MSAA

	# Shadow settings are renderer wide, not per viewport.
	RenderingServer.directional_soft_shadow_filter_set_quality(
			SHADOW_FILTER[lv] as RenderingServer.ShadowQuality)
	RenderingServer.directional_shadow_atlas_set_size(SHADOW_SIZE[lv], true)


## Pushes the current distance onto every prop already in the world.
##
## Walked by group rather than by asking the world for its chunks: props live
## several levels down inside a tile, and the chunk has no reason to know that
## a quality ladder exists.
func _push_prop_distance() -> void:
	var tree := get_tree()
	if tree == null:
		return
	for node in tree.get_nodes_in_group(PROP_GROUP):
		var geo := node as GeometryInstance3D
		if geo == null or not is_instance_valid(geo):
			continue
		apply_to(geo)


## Sets the distance fade of one prop instance. Static so a chunk can call it on
## a node it has just spawned, without holding a reference to the governor.
static func apply_to(geo: GeometryInstance3D) -> void:
	geo.visibility_range_end = prop_draw_distance
	geo.visibility_range_end_margin = PROP_FADE
	# Dissolve rather than pop. SELF because the props have no LOD chain to
	# hand over to; there is nothing behind them to fade in.
	geo.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
