## Autoload `Sfx`: the game's sound front end.
##
## Owns the procedural bank produced by `SfxLib` and two pools of players, one
## non positional (interface, player feedback) and one 3D (everything that
## happens in the world). Nothing allocates during play once the pools are warm.
##
## The `Game` autoload is resolved through the scene tree rather than by its
## global identifier: that keeps this file compilable with
## `--check-only --script`, where Godot does not register project autoloads.
extends Node

## Non positional voices. Interface and player feedback only, so a dozen is
## plenty.
const POOL_2D := 12
## Positional voices. Firefights get busy, hence the larger pool.
const POOL_3D := 24

## Beyond this distance a gunshot gets its valley echo layer.
const FAR_DISTANCE := 60.0
## Speed of sound in metres per second, used to delay the echo layer.
const SOUND_SPEED := 340.0
## Longest echo delay we are willing to schedule.
const MAX_ECHO_DELAY := 1.1

## Default 3D profile: (unit_size, max_distance, extra_db).
const DEFAULT_PROFILE := Vector3(6.0, 120.0, 0.0)
## Air absorption: distant sources lose their high end.
const AIR_FILTER_HZ := 6200.0
const AIR_FILTER_DB := -14.0

## Volume floor. Below this the master volume counts as muted.
const MUTE_EPSILON := 0.001
const MUTE_DB := -80.0

var _bank: Dictionary = {}
var _pool_2d: Array[AudioStreamPlayer] = []
var _pool_3d: Array[AudioStreamPlayer3D] = []
var _stamp_2d: PackedFloat64Array = PackedFloat64Array()
var _stamp_3d: PackedFloat64Array = PackedFloat64Array()

## Deadline past which a voice counts as free even though it still reports
## `playing`.
##
## SfxLib marks "wind" and "distant_battle" as LOOP_FORWARD, and a looping stream
## never finishes: `playing` stays true forever. The Director fires
## "distant_battle" as a one shot ambience event (once per bombardment, and nine
## times during a bomber fly over), so each one parked a positional voice for the
## rest of the session. The 24 voice pool silted up within minutes, every later
## shot and footstep had to steal a voice, and the stolen ones were stuck loops
## droning at frozen world positions. Reclaiming on a deadline fixes it for any
## looping sample, present or future.
var _expire_2d: PackedFloat64Array = PackedFloat64Array()
var _expire_3d: PackedFloat64Array = PackedFloat64Array()

## Longest a single positional or flat voice may hold its slot, in seconds. No
## sample in the bank is anywhere near this long, so it only ever bites loops.
const VOICE_MAX_SECONDS := 6.0

## Non looping copies of the looping bank entries, built on first use.
var _oneshot: Dictionary = {}
var _game: Node = null
## Bumped by stop_all so scheduled echo layers do not fire into a dead scene.
var _echo_token: int = 0
var _rng := RandomNumberGenerator.new()
## Warned once per unknown sample name, to avoid flooding the log.
var _warned: Dictionary = {}


func _ready() -> void:
	# Interface sounds must keep working while the game is paused.
	process_mode = Node.PROCESS_MODE_ALWAYS
	_rng.randomize()
	_game = get_node_or_null("/root/Game")
	_build_bank()
	_build_pools()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Non positional (UI, feedback).
func play(sample_name: String, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var stream: AudioStreamWAV = _stream_of(sample_name)
	if stream == null:
		return
	var master: float = _master_db()
	if master <= MUTE_DB:
		return
	var player: AudioStreamPlayer = _take_2d()
	if player == null:
		return
	player.stream = stream
	player.volume_db = volume_db + master
	player.pitch_scale = clampf(pitch, 0.05, 4.0)
	player.play()


## Positional 3D.
func play_at(sample_name: String, position: Vector3, volume_db: float = 0.0,
		pitch: float = 1.0) -> void:
	var profile: Vector3 = _profile_of(sample_name)
	_play_3d(sample_name, position, volume_db + profile.z, pitch, profile.x, profile.y)


## Footstep dispatch on a surface name among "grass","dirt","stone","wood","water".
func play_step(surface: String, position: Vector3) -> void:
	var key: String = "step_" + surface
	if not _bank.has(key):
		key = "step_dirt"
	# Steps never sound twice the same: small pitch and level jitter.
	var pitch: float = _rng.randf_range(0.88, 1.12)
	var gain: float = _rng.randf_range(-3.0, 1.0)
	var profile: Vector3 = _profile_of(key)
	_play_3d(key, position, gain + profile.z, pitch, profile.x, profile.y)


## Gunshot with distance aware layering (adds a far tail beyond 60 m).
func play_shot(sample_name: String, position: Vector3) -> void:
	var profile: Vector3 = _profile_of(sample_name)
	var pitch: float = _rng.randf_range(0.965, 1.035)
	_play_3d(sample_name, position, profile.z, pitch, profile.x, profile.y)

	var distance: float = _listener_position().distance_to(position)
	if distance <= FAR_DISTANCE or not _bank.has("explosion_far"):
		return
	# Over open bocage the report comes back off the hedgerows and the far side
	# of the valley. Layer a muffled tail, delayed by the travel time.
	var delay: float = clampf(distance / SOUND_SPEED, 0.06, MAX_ECHO_DELAY)
	var fade: float = clampf((distance - FAR_DISTANCE) / 260.0, 0.0, 1.0)
	var gain: float = lerpf(-14.0, -3.0, fade)
	var tree: SceneTree = get_tree()
	if tree == null:
		return
	var timer: SceneTreeTimer = tree.create_timer(delay, true, false, true)
	timer.timeout.connect(_fire_echo.bind(_echo_token, position, gain))


## Stops everything at once (used on scene reload).
func stop_all() -> void:
	_echo_token += 1
	for player: AudioStreamPlayer in _pool_2d:
		if player.playing:
			player.stop()
	for player3d: AudioStreamPlayer3D in _pool_3d:
		if player3d.playing:
			player3d.stop()


func has_sample(sample_name: String) -> bool:
	return _bank.has(sample_name)


# ---------------------------------------------------------------------------
# Bank and pools
# ---------------------------------------------------------------------------

## Synthesises every sample. Safe in headless mode: nothing here touches the
## audio device, only buffers.
func _build_bank() -> void:
	_bank = SfxLib.build_all()
	if _bank.is_empty():
		push_error("Sfx: the procedural sound bank came out empty.")
		return
	var missing: int = 0
	for wanted: String in SfxLib.NAMES:
		if not _bank.has(wanted):
			missing += 1
	if missing > 0:
		push_warning("Sfx: %d sample(s) missing from the bank." % missing)


func _build_pools() -> void:
	_stamp_2d.resize(POOL_2D)
	_expire_2d.resize(POOL_2D)
	for i: int in POOL_2D:
		var player := AudioStreamPlayer.new()
		player.name = "Sfx2D_%d" % i
		player.bus = "Master"
		player.max_polyphony = 1
		player.process_mode = Node.PROCESS_MODE_ALWAYS
		add_child(player)
		_pool_2d.append(player)
		_stamp_2d[i] = 0.0

	_stamp_3d.resize(POOL_3D)
	_expire_3d.resize(POOL_3D)
	for i: int in POOL_3D:
		var player3d := AudioStreamPlayer3D.new()
		player3d.name = "Sfx3D_%d" % i
		player3d.bus = "Master"
		player3d.max_polyphony = 1
		player3d.process_mode = Node.PROCESS_MODE_ALWAYS
		player3d.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		player3d.unit_size = DEFAULT_PROFILE.x
		player3d.max_distance = DEFAULT_PROFILE.y
		player3d.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
		player3d.attenuation_filter_cutoff_hz = AIR_FILTER_HZ
		player3d.attenuation_filter_db = AIR_FILTER_DB
		player3d.panning_strength = 1.1
		add_child(player3d)
		_pool_3d.append(player3d)
		_stamp_3d[i] = 0.0


func _stream_of(sample_name: String) -> AudioStreamWAV:
	var stream: Variant = _bank.get(sample_name)
	if stream == null:
		if not _warned.has(sample_name):
			_warned[sample_name] = true
			push_warning("Sfx: unknown sample \"%s\"." % sample_name)
		return null
	var wav := stream as AudioStreamWAV
	if wav == null:
		return null
	# `play` and `play_at` are the only ways into this node, and both are one shot
	# by contract. SfxLib nevertheless marks a couple of ambience beds as
	# LOOP_FORWARD, and a looping stream on a pooled voice never ends: it holds
	# its slot forever. De-loop once, keep the copy, and the bank stays reusable
	# should a real looping bed API ever be added.
	if wav.loop_mode == AudioStreamWAV.LOOP_DISABLED:
		return wav
	if _oneshot.has(sample_name):
		return _oneshot[sample_name] as AudioStreamWAV
	var once := wav.duplicate() as AudioStreamWAV
	once.loop_mode = AudioStreamWAV.LOOP_DISABLED
	_oneshot[sample_name] = once
	return once


## Recycles the least recently started free player, or steals the oldest one.
func _take_2d() -> AudioStreamPlayer:
	var now: float = _now()
	var oldest: int = -1
	var oldest_time: float = INF
	for i: int in _pool_2d.size():
		if not _pool_2d[i].playing or now >= _expire_2d[i]:
			if _pool_2d[i].playing:
				_pool_2d[i].stop()
			_stamp_2d[i] = now
			_expire_2d[i] = now + VOICE_MAX_SECONDS
			return _pool_2d[i]
		if _stamp_2d[i] < oldest_time:
			oldest_time = _stamp_2d[i]
			oldest = i
	if oldest < 0:
		return null
	_pool_2d[oldest].stop()
	_stamp_2d[oldest] = now
	_expire_2d[oldest] = now + VOICE_MAX_SECONDS
	return _pool_2d[oldest]


func _take_3d() -> AudioStreamPlayer3D:
	var now: float = _now()
	var oldest: int = -1
	var oldest_time: float = INF
	for i: int in _pool_3d.size():
		if not _pool_3d[i].playing or now >= _expire_3d[i]:
			if _pool_3d[i].playing:
				_pool_3d[i].stop()
			_stamp_3d[i] = now
			_expire_3d[i] = now + VOICE_MAX_SECONDS
			return _pool_3d[i]
		if _stamp_3d[i] < oldest_time:
			oldest_time = _stamp_3d[i]
			oldest = i
	if oldest < 0:
		return null
	_pool_3d[oldest].stop()
	_stamp_3d[oldest] = now
	_expire_3d[oldest] = now + VOICE_MAX_SECONDS
	return _pool_3d[oldest]


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _play_3d(sample_name: String, position: Vector3, volume_db: float,
		pitch: float, unit_size: float, max_distance: float) -> void:
	var stream: AudioStreamWAV = _stream_of(sample_name)
	if stream == null:
		return
	var master: float = _master_db()
	if master <= MUTE_DB:
		return
	var player: AudioStreamPlayer3D = _take_3d()
	if player == null:
		return
	player.global_position = position
	player.unit_size = unit_size
	player.max_distance = max_distance
	player.stream = stream
	player.volume_db = volume_db + master
	player.pitch_scale = clampf(pitch, 0.05, 4.0)
	player.play()


## Deferred second layer of a distant gunshot. `token` guards against a scene
## reload happening between the shot and its echo.
func _fire_echo(token: int, position: Vector3, gain: float) -> void:
	if token != _echo_token:
		return
	if not is_inside_tree():
		return
	_play_3d("explosion_far", position, gain, _rng.randf_range(0.82, 0.95), 34.0, 900.0)


## Global level from `Game.sfx_volume`, in decibels. Returns MUTE_DB when the
## player has turned the sound off, so callers can skip the work entirely.
func _master_db() -> float:
	var linear: float = 0.85
	if _game != null:
		var value: Variant = _game.get("sfx_volume")
		var kind: int = typeof(value)
		if kind == TYPE_FLOAT or kind == TYPE_INT:
			linear = float(value)
	linear = clampf(linear, 0.0, 1.0)
	if linear <= MUTE_EPSILON:
		return MUTE_DB
	return linear_to_db(linear)


## Where the ears are. Falls back to the origin in headless mode, where there is
## no camera at all.
func _listener_position() -> Vector3:
	var tree: SceneTree = get_tree()
	if tree == null:
		return Vector3.ZERO
	var root: Window = tree.root
	if root == null:
		return Vector3.ZERO
	var camera: Camera3D = root.get_camera_3d()
	if camera == null:
		return Vector3.ZERO
	return camera.global_position


## Per family 3D settings: (unit_size, max_distance, extra_db). Tuned for a
## world measured in metres, where a rifle must still be heard several hundred
## metres away while a footstep dies within thirty.
func _profile_of(sample_name: String) -> Vector3:
	match sample_name:
		"rifle_m1", "rifle_kar98", "sniper_springfield":
			return Vector3(28.0, 460.0, 0.0)
		"smg_thompson", "smg_mp40", "mg42":
			return Vector3(24.0, 400.0, -1.0)
		"pistol_1911":
			return Vector3(20.0, 340.0, -1.0)
		"explosion", "artillery_hit":
			return Vector3(38.0, 620.0, 1.0)
		"explosion_far", "artillery_incoming", "distant_battle":
			return Vector3(34.0, 900.0, -4.0)
		"wind":
			return Vector3(30.0, 600.0, -8.0)
		"bird":
			return Vector3(4.0, 70.0, -6.0)
		"step_grass", "step_dirt", "step_stone", "step_wood", "step_water":
			return Vector3(1.7, 34.0, -6.0)
		"impact_dirt", "impact_stone", "impact_wood", "impact_metal", \
		"impact_flesh", "ricochet", "shell_casing":
			return Vector3(3.0, 65.0, -3.0)
		"whizz":
			return Vector3(1.4, 22.0, -2.0)
		"garand_ping", "dry_fire", "reload_in", "reload_out", "bolt", \
		"grenade_pin", "grenade_throw":
			return Vector3(2.4, 45.0, -2.0)
		"german_alert", "german_shout", "german_death", "french_ok", "french_go":
			return Vector3(7.0, 110.0, 0.0)
		"hurt", "death", "breath", "bandage", "heartbeat":
			return Vector3(3.2, 45.0, 0.0)
	return DEFAULT_PROFILE


func _now() -> float:
	return float(Time.get_ticks_msec()) * 0.001
