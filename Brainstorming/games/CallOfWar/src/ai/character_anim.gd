## Drives the AnimationPlayer of an imported rigged character from the handful
## of facts the AI already computes: ground speed, whether the soldier is
## aiming, and whether he has just fired, been hit or died.
##
## Why an AnimationPlayer and not an AnimationTree: a state machine would have to
## be assembled resource by resource in code for no gain here. `play()` already
## cross-fades, `speed_scale` already syncs a walk cycle to real ground speed,
## and up to sixty of these run at once, so the cheaper node wins.
##
## The driver is deliberately tolerant of a missing clip. The zombie rig ships
## no death and no hit animation; `has()` lets `Soldier` fall back to the
## procedural tip-over rather than freeze on a pose that does not exist.
class_name CharacterAnim
extends RefCounted

## Cross-fade applied to every clip change. Long enough to hide the cut, short
## enough that a soldier snapping to his aim pose still reads as reactive.
const BLEND := 0.18

## Below this ground speed the character is treated as standing still.
const IDLE_SPEED := 0.35

## A firing clip only takes over the whole body when the soldier is roughly
## stationary; on the move the run-and-shoot cycle already sells the shot.
const FIRE_WHILE_MOVING := 1.20

var _player: AnimationPlayer = null
var _clips: Dictionary = {}
var _walk_speed := 1.4
var _run_speed := 4.6
var _current := ""
var _oneshot := 0.0
var _dead := false


## Wires a driver to a body built by `CharacterModels`. Returns null when the
## body carries no AnimationPlayer, which is the caller's cue that this is a
## procedural box soldier and the old per-limb code still applies.
static func attach(body: Node3D, species: int) -> CharacterAnim:
	if body == null:
		return null
	var player := _find(body)
	if player == null:
		return null
	var out := CharacterAnim.new()
	out._player = player
	var prefix := CharacterModels.clip_prefix(species)
	# Keep only the clips this rig really has, so every later lookup is a
	# straight dictionary hit and a gap is visible as a missing key.
	for key in CharacterModels.clips(species):
		var full: String = "%s%s" % [prefix, CharacterModels.clips(species)[key]]
		if player.has_animation(full):
			out._clips[key] = full
	var speeds := CharacterModels.reference_speeds(species)
	out._walk_speed = maxf(0.2, speeds.x)
	out._run_speed = maxf(out._walk_speed + 0.2, speeds.y)
	return out


func has(key: String) -> bool:
	return _clips.has(key)


## Suspends the whole animation node. Used for soldiers past the far-distance
## cut-off, which stop being ticked but would otherwise keep posing themselves.
func set_active(on: bool) -> void:
	if _player != null and _player.active != on:
		_player.active = on


## Picks the locomotion clip for this frame. `speed` is horizontal ground speed
## in m/s. Does nothing once dead, and yields to a running one-shot.
func locomotion(speed: float, aiming: bool, delta: float) -> void:
	if _player == null or _dead:
		return
	if _oneshot > 0.0:
		_oneshot -= delta
		return

	var key := ""
	var scale := 1.0
	if speed < IDLE_SPEED:
		key = "idle_aim" if aiming and has("idle_aim") else "idle"
	elif speed < _walk_speed * 1.6 and has("walk"):
		key = "walk"
		scale = speed / _walk_speed
	else:
		key = "run_aim" if aiming and has("run_aim") else "run"
		scale = speed / _run_speed
	_play(key, clampf(scale, 0.55, 1.85))


## One shot of the firing animation, unless the character is moving fast enough
## that the run cycle already covers it.
func fire(speed: float) -> void:
	if _player == null or _dead or speed > FIRE_WHILE_MOVING:
		return
	_oneshot_clip("fire")


func hit() -> void:
	if _player == null or _dead:
		return
	_oneshot_clip("hit")


## Plays the death clip and locks the driver. Returns false when this rig has no
## death animation, so the caller knows to run its own tip-over instead.
func die() -> bool:
	if _player == null or _dead:
		return _dead and has("death")
	_dead = true
	if not has("death"):
		return false
	_player.speed_scale = 1.0
	_player.play(_clips["death"], BLEND)
	_current = _clips["death"]
	return true


func _oneshot_clip(key: String) -> void:
	if not has(key):
		return
	var name: String = _clips[key]
	_player.speed_scale = 1.0
	_player.play(name, BLEND)
	_current = name
	_oneshot = _player.get_animation(name).length


func _play(key: String, scale: float) -> void:
	if not has(key):
		return
	var name: String = _clips[key]
	_player.speed_scale = scale
	if name == _current and _player.is_playing():
		return
	_player.play(name, BLEND)
	_current = name


static func _find(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node as AnimationPlayer
	for child in node.get_children():
		var hit := _find(child)
		if hit != null:
			return hit
	return null
