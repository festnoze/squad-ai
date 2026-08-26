extends Node
## Autoload `Sfx`: the mixer. Owns every voice the game is allowed to use.
##
## Two pools of players are built once at boot, one non spatial (interface,
## crowd, anything that belongs to the camera) and one spatial (impacts, which
## must come from where they happened). Godot creates a real audio voice per
## player, so the pools are deliberately small and fixed.
##
## When a pool is exhausted the OLDEST voice is stolen rather than the new sound
## dropped. A penalty is a burst of near simultaneous events (boot, post, net,
## crowd) and silently losing the last one - which is usually the loudest and
## the most informative - feels like a bug to the player, while cutting a sound
## that started 300 ms ago is inaudible.
##
## Exactly one voice is reserved for the looping crowd ambience. It lives
## outside both pools so it can never be stolen, and one shot playback refuses
## any stream whose loop_mode is set: a looping stream in the one shot pool
## would squat that voice for the rest of the session.
##
## Engine note: this file deliberately never names the `Game` autoload as a
## global identifier. Godot does not register autoloads as globals when it is
## started with `--script`, so a file that named one would refuse to compile
## while the test runner is booting. The settings are read through
## `/root/Game` at run time instead, and their absence is not fatal.


## Non spatial voices: interface, crowd reactions, anything camera relative.
const FLAT_VOICES := 12
## Spatial voices: boot, post, net, gloves, turf.
const SPATIAL_VOICES := 10
## Godot treats -80 dB as silence.
const SILENCE_DB := -80.0
## Distance at which a spatial sound plays at its authored level.
const SPATIAL_UNIT := 8.0

var _flat: Array[AudioStreamPlayer] = []
var _spatial: Array[AudioStreamPlayer3D] = []
## Monotonic stamps, one per voice, used to find the oldest one to steal.
var _flat_stamp: PackedInt64Array = PackedInt64Array()
var _spatial_stamp: PackedInt64Array = PackedInt64Array()
## Authored level of each voice, before the master gain is applied. Kept so a
## mute or a volume change can be re applied without the gain being folded in
## twice.
var _flat_base: PackedFloat32Array = PackedFloat32Array()
var _spatial_base: PackedFloat32Array = PackedFloat32Array()

var _ambience: AudioStreamPlayer = null
var _ambience_id: String = ""
var _ambience_base: float = -12.0

var _fade_from: float = 0.0
var _fade_to: float = 0.0
var _fade_seconds: float = 0.0
var _fade_elapsed: float = -1.0

var _muted: bool = false
var _master: float = 0.8
var _clock: int = 0
## Latched by silence_all(). One way on purpose: it is the shutdown state, and
## the rest of the game keeps calling play() for a few frames after it.
var _silenced: bool = false


func _ready() -> void:
	# The mixer keeps running while the tree is paused, otherwise the ambience
	# cuts out the moment the pause menu opens.
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_pools()
	_bind_settings()


func _exit_tree() -> void:
	# Last resort. By the time the tree tears down it is already too late for the
	# audio server to reap anything, so the real shutdown path is
	# `Main.quit_clean`, which calls silence_all() and then keeps ticking. This
	# stays as a safety net for any teardown that never went through Main.
	silence_all()


func _process(delta: float) -> void:
	if _silenced or _fade_elapsed < 0.0:
		return
	_fade_elapsed += delta
	var t := 1.0 if _fade_seconds <= 0.0 else clampf(_fade_elapsed / _fade_seconds, 0.0, 1.0)
	_ambience_base = lerpf(_fade_from, _fade_to, t)
	_push_ambience_volume()
	if t >= 1.0:
		_fade_elapsed = -1.0


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------

## Non spatial one shot. `pitch` and `volume_db` are applied on top of the stream.
func play(id: String, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var wav := _one_shot_stream(id)
	if wav == null:
		return
	var index := _take_flat()
	if index < 0:
		return
	var voice := _flat[index]
	voice.stream = wav
	voice.pitch_scale = clampf(pitch, 0.05, 4.0)
	_flat_base[index] = volume_db
	voice.volume_db = _mixed_db(volume_db)
	_clock += 1
	_flat_stamp[index] = _clock
	voice.play()


## Spatial one shot at a world position.
func play_at(id: String, position: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var wav := _one_shot_stream(id)
	if wav == null:
		return
	var index := _take_spatial()
	if index < 0:
		return
	var voice := _spatial[index]
	voice.stream = wav
	voice.pitch_scale = clampf(pitch, 0.05, 4.0)
	voice.global_position = position
	_spatial_base[index] = volume_db
	voice.volume_db = _mixed_db(volume_db)
	_clock += 1
	_spatial_stamp[index] = _clock
	voice.play()


## Starts, or retargets, the single looping ambience voice. Empty id stops it.
func set_ambience(id: String, volume_db: float = -12.0) -> void:
	_fade_elapsed = -1.0
	_ambience_base = volume_db
	if _ambience == null or _silenced:
		return

	if id.is_empty():
		_ambience_id = ""
		_ambience.stop()
		_ambience.stream = null
		return

	var wav := SfxLib.stream(id)
	if wav == null:
		return
	if wav.loop_mode == AudioStreamWAV.LOOP_DISABLED:
		push_warning("Sfx: ambience '%s' does not loop, it will play once" % id)

	if _ambience_id != id or _ambience.stream != wav:
		_ambience_id = id
		_ambience.stream = wav
	_push_ambience_volume()
	if not _ambience.playing:
		_ambience.play()


## Fades the ambience voice to a level over `seconds`.
func fade_ambience(volume_db: float, seconds: float) -> void:
	if _ambience == null or _silenced:
		return
	if seconds <= 0.0:
		_fade_elapsed = -1.0
		_ambience_base = volume_db
		_push_ambience_volume()
		return
	_fade_from = _ambience_base
	_fade_to = volume_db
	_fade_seconds = seconds
	_fade_elapsed = 0.0


## Stops every voice, ambience included, and drops the stream each one held.
##
## Shutdown path, see `Main.quit_clean`. `AudioStreamPlayer.stop()` does NOT
## release its playback on the spot: the audio server fades the voice out on its
## own thread and only unregisters the playback on a later main thread update.
## A process that quits on the same frame therefore exits with those playbacks,
## and with the `AudioStreamWAV` each one holds, still alive in the object
## database - which is exactly what Godot reports as leaked instances. Silencing
## the mixer is the first half of the fix; the second half is letting the tree
## run for a moment afterwards.
func silence_all() -> void:
	_silenced = true
	_fade_elapsed = -1.0
	for voice in _flat:
		voice.stop()
		voice.stream = null
	for voice in _spatial:
		voice.stop()
		voice.stream = null
	if _ambience != null:
		_ambience_id = ""
		_ambience.stop()
		_ambience.stream = null


## Master mute, driven by the settings.
func set_muted(muted: bool) -> void:
	if _muted == muted:
		return
	_muted = muted
	_push_all_volumes()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _build_pools() -> void:
	for i in FLAT_VOICES:
		var voice := AudioStreamPlayer.new()
		voice.name = "Flat%d" % i
		voice.bus = &"Master"
		add_child(voice)
		_flat.append(voice)
	_flat_stamp.resize(FLAT_VOICES)
	_flat_stamp.fill(0)
	_flat_base.resize(FLAT_VOICES)
	_flat_base.fill(0.0)

	for i in SPATIAL_VOICES:
		var voice := AudioStreamPlayer3D.new()
		voice.name = "Spatial%d" % i
		voice.bus = &"Master"
		# Inverse distance is the physically honest law and it keeps a boot
		# audible from the television camera thirty metres away.
		voice.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		voice.unit_size = SPATIAL_UNIT
		voice.max_distance = 140.0
		voice.panning_strength = 1.0
		voice.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
		add_child(voice)
		_spatial.append(voice)
	_spatial_stamp.resize(SPATIAL_VOICES)
	_spatial_stamp.fill(0)
	_spatial_base.resize(SPATIAL_VOICES)
	_spatial_base.fill(0.0)

	_ambience = AudioStreamPlayer.new()
	_ambience.name = "Ambience"
	_ambience.bus = &"Master"
	_ambience.volume_db = SILENCE_DB
	add_child(_ambience)


## Reads the settings through the scene tree rather than through the `Game`
## global, see the file header.
func _bind_settings() -> void:
	var game := get_node_or_null(^"/root/Game")
	if game == null:
		return
	if game.has_signal("settings_changed") and not game.is_connected("settings_changed", _on_settings_changed):
		game.connect("settings_changed", _on_settings_changed)
	_on_settings_changed()


func _on_settings_changed() -> void:
	var game := get_node_or_null(^"/root/Game")
	if game == null:
		return
	var volume: Variant = game.get("master_volume")
	if typeof(volume) == TYPE_FLOAT or typeof(volume) == TYPE_INT:
		_master = clampf(float(volume), 0.0, 1.0)
	var muted: Variant = game.get("muted")
	if typeof(muted) == TYPE_BOOL:
		_muted = bool(muted)
	_push_all_volumes()


## The single place where the master gain meets an authored level. Every voice
## goes through it, so the gain can never be applied twice down the chain.
func _mixed_db(base_db: float) -> float:
	if _muted or _master <= 0.001:
		return SILENCE_DB
	return clampf(base_db + linear_to_db(_master), SILENCE_DB, 24.0)


func _push_ambience_volume() -> void:
	if _ambience != null:
		_ambience.volume_db = _mixed_db(_ambience_base)


func _push_all_volumes() -> void:
	for i in _flat.size():
		_flat[i].volume_db = _mixed_db(_flat_base[i])
	for i in _spatial.size():
		_spatial[i].volume_db = _mixed_db(_spatial_base[i])
	_push_ambience_volume()


func _one_shot_stream(id: String) -> AudioStreamWAV:
	if _silenced:
		# The mixer is shutting down. The crowd, the keeper and the whistle all
		# keep asking for sounds during the drain frames, and starting a voice
		# now would put a fresh playback back into the audio server, which is
		# precisely what silence_all() just emptied.
		return null
	var wav := SfxLib.stream(id)
	if wav == null:
		# SfxLib already reported the unknown id, no need to say it twice.
		return null
	if wav.loop_mode != AudioStreamWAV.LOOP_DISABLED:
		push_warning("Sfx: '%s' loops, it must go through set_ambience" % id)
		return null
	return wav


## Index of a free voice, or of the oldest busy one, which is then stopped.
func _take_flat() -> int:
	if _flat.is_empty():
		return -1
	var oldest := 0
	var oldest_stamp := _flat_stamp[0]
	for i in _flat.size():
		if not _flat[i].playing:
			return i
		if _flat_stamp[i] < oldest_stamp:
			oldest_stamp = _flat_stamp[i]
			oldest = i
	_flat[oldest].stop()
	return oldest


func _take_spatial() -> int:
	if _spatial.is_empty():
		return -1
	var oldest := 0
	var oldest_stamp := _spatial_stamp[0]
	for i in _spatial.size():
		if not _spatial[i].playing:
			return i
		if _spatial_stamp[i] < oldest_stamp:
			oldest_stamp = _spatial_stamp[i]
			oldest = i
	_spatial[oldest].stop()
	return oldest
