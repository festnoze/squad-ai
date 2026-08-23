## Adaptive music bed for CALL OF WAR.
##
## The project ships zero binary assets, so the music is synthesised here exactly
## like the sound effects are in `SfxLib`: a small toolbox of primitives (grid
## locked sines with a slow tremolo, decaying sweeps, filtered noise bursts)
## recombined into four short buffers, one per musical state.
##
## Direction, from `docs/PRD.md` F2 and `docs/CONTRACTS.md` 11.3: this is an
## infiltration game in the Normandy bocage, not an action film. Silence is the
## default and music is the exception. `STATE_CALM` therefore plays a rare low
## swell and stays quiet well over eighty percent of the time, so the wind, the
## birds and a patrol two hedgerows away keep the stage to themselves. No state
## ever exposes a melody: the sustained states are pads and percussion, and the
## only stated motif is the four bar bloom that marks a liberated village.
##
## Three traps shaped the implementation.
##
## - A looping `AudioStreamWAV` never ends. `playing` stays true forever, so a
##   pooled voice handed a loop is never given back (see the long note in
##   `sfx_player.gd`, which had to reclaim voices on a deadline because of it).
##   This node consequently owns its own non positional players and stops them
##   explicitly; it never borrows from the `Sfx` pool.
## - A loop only sounds like a bed if it has no seam. Every sustained partial and
##   every tremolo below is an exact integer number of cycles per buffer, which
##   makes the last sample flow into the first one with no click and no fade
##   trickery. Transients live in their own buffer, land early enough to have
##   decayed before the seam, and get a short tail fade for the residue.
## - Synthesis is not free. Buffers are built lazily, on the first entry into a
##   state, so boot pays nothing on top of the sound bank (already some 344 ms).
##   Measured: calm 33 ms, search 37 ms, combat 44 ms, victory 33 ms, so 147 ms
##   for the whole set, spread over the session and never in a single frame. A
##   layer is paid for once and only if the campaign ever reaches it.
##
## The `Game` autoload is resolved through the scene tree rather than by its
## global identifier, like the other audio modules, so this file still compiles
## under `--check-only --script`, where Godot registers no autoload.
class_name Music
extends Node

const STATE_CALM := 0
const STATE_SEARCH := 1
const STATE_COMBAT := 2
const STATE_VICTORY := 3

signal state_changed(state: int)

# ---------------------------------------------------------------------------
# Mixing
# ---------------------------------------------------------------------------

## Dedicated bus, created on the fly because the project ships no bus layout
## resource. Falls back to the master bus if the audio server refuses it.
const BUS_NAME := "Music"
const FALLBACK_BUS := "Master"

## Cross fade between two states, in seconds. The contract asks for two to four.
const CROSSFADE := 3.0
## Bed voices. Two would be enough for a single cross fade; four leaves room for
## a state that flips twice inside one fade, plus the victory motif on top.
const VOICES := 4

## Below this the music volume counts as off: everything stops and nothing is
## synthesised, scheduled or mixed.
const MUTE_EPSILON := 0.001
const SILENT_DB := -80.0
## Used only when the `Game` autoload is absent, in a bare unit test.
const DEFAULT_VOLUME := 0.55

## Per state trim, on top of the player's setting. The pads are quiet by design;
## combat is the only layer allowed to sit near the sound effects.
const TRIM_CALM := -7.0
const TRIM_SEARCH := -6.0
const TRIM_COMBAT := -4.0
const TRIM_VICTORY := -4.0

# ---------------------------------------------------------------------------
# Calm scheduling
# ---------------------------------------------------------------------------

## One calm swell lasts this long, rise and fall included.
const CALM_PHRASE_MIN := 20.0
const CALM_PHRASE_MAX := 40.0
## Silence between two swells. Long on purpose: with a thirty second phrase and
## a hundred and ninety second gap the pad is audible around thirteen percent of
## the time, and never more than nineteen.
const CALM_GAP_MIN := 150.0
const CALM_GAP_MAX := 230.0
## Shorter first gap when calm is entered, so a session does not open on three
## full minutes of nothing.
const CALM_ENTRY_MIN := 30.0
const CALM_ENTRY_MAX := 70.0
## Share of the phrase spent rising, and again falling. The rest is the plateau.
const CALM_SLOPE := 0.45

## Length of the victory motif, and the pause before the music falls back to
## calm on its own.
const VICTORY_SECONDS := 4.8
const VICTORY_HOLD := 0.6

# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------

## Sample rates, chosen per layer against its own bandwidth rather than kept at
## the effect bank's 22050 Hz. Nothing here is bright: the pad stops at 220 Hz,
## the percussion is deliberately dull, and halving a rate halves the synthesis
## cost exactly. Godot resamples on playback, and since every layer sits far
## below its own Nyquist the interpolation images land some fifty decibels down.
const CALM_RATE := 4410
const BED_RATE := 8000
const MOTIF_RATE := 5512

## Loop lengths. Every sustained frequency below is an integer multiple of the
## reciprocal of these, which is what makes the seam inaudible.
const CALM_LOOP := 6.0
const SEARCH_LOOP := 4.8
const COMBAT_LOOP := 4.0

## Maps the inline linear congruential generator (0 .. 2^31) onto -1 .. 1.
const NOISE_SCALE := 9.31322574615e-10
## Amplitude under which a decaying voice is dropped.
const SILENCE := 0.0006

var _state: int = STATE_CALM
var _streams: Dictionary = {}
var _voices: Array[AudioStreamPlayer] = []
## Current linear gain, target gain, gain per second, and the state each voice
## carries. A state of -1 means the voice is free.
var _gain: PackedFloat32Array = PackedFloat32Array()
var _target: PackedFloat32Array = PackedFloat32Array()
var _rate: PackedFloat32Array = PackedFloat32Array()
var _carried: PackedInt32Array = PackedInt32Array()

var _calm_on: bool = false
var _calm_left: float = 0.0
var _calm_phrase: float = 0.0
var _victory_left: float = 0.0
var _muted: bool = false
var _built: bool = false
var _bus: String = FALLBACK_BUS
var _game: Node = null
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	# The pause menu owns the music slider, and the project pauses by freezing
	# the player rather than the tree, so the node must keep running there.
	process_mode = Node.PROCESS_MODE_ALWAYS
	_build_players()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

func setup() -> void:
	_build_players()
	_rng.randomize()
	_game = get_node_or_null("/root/Game")
	_state = STATE_CALM
	_muted = false
	_victory_left = 0.0
	_hush()
	_schedule_calm_entry()


## Transition douce vers un état. VICTORY est un motif court qui retombe seul.
func set_state(new_state: int) -> void:
	if new_state < STATE_CALM or new_state > STATE_VICTORY:
		return
	# Re-entering victory is legal: two villages can fall in a row, and the
	# motif then simply starts over.
	if new_state == _state and new_state != STATE_VICTORY:
		return
	_state = new_state
	_enter(new_state)
	state_changed.emit(new_state)


func state() -> int:
	return _state


## Appelé chaque frame par Main.
func tick(delta: float) -> void:
	var step: float = clampf(delta, 0.0, 0.25)
	var volume: float = _volume()
	if volume <= MUTE_EPSILON:
		# Silence means silence: no voice left running under the floor, and no
		# scheduling either, so turning the music off costs strictly nothing.
		if not _muted:
			_muted = true
			_hush()
		return
	if _muted:
		_muted = false
		_resume()
	_advance_schedule(step)
	_advance_voices(step, volume)


func stop_all() -> void:
	_hush()
	_victory_left = 0.0
	_muted = false
	_schedule_calm_entry()
	if _state != STATE_CALM:
		_state = STATE_CALM
		state_changed.emit(STATE_CALM)


static func state_name(state: int) -> String:
	match state:
		STATE_CALM:
			return "Calme"
		STATE_SEARCH:
			return "Recherche"
		STATE_COMBAT:
			return "Combat"
		STATE_VICTORY:
			return "Victoire"
	return "Inconnu"


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

func _enter(new_state: int) -> void:
	match new_state:
		STATE_CALM:
			# Calm is silence by default. The outgoing layer fades out and the
			# pad waits for its turn instead of taking over.
			_lower_all(CROSSFADE)
			_schedule_calm_entry()
		STATE_SEARCH, STATE_COMBAT:
			_calm_on = false
			_raise(new_state, CROSSFADE)
		STATE_VICTORY:
			_calm_on = false
			# The motif carries its own one second swell, so the player gain
			# only has to open; the cross fade is the outgoing bed's three
			# second decay underneath it.
			_raise(STATE_VICTORY, 0.05)
			_victory_left = VICTORY_SECONDS + VICTORY_HOLD


func _advance_schedule(delta: float) -> void:
	if _state == STATE_VICTORY:
		_victory_left -= delta
		if _victory_left <= 0.0:
			set_state(STATE_CALM)
		return
	if _state != STATE_CALM:
		return
	_calm_left -= delta
	if _calm_left > 0.0:
		return
	if _calm_on:
		_lower_all(_calm_phrase * CALM_SLOPE)
		_calm_on = false
		_calm_left = _rng.randf_range(CALM_GAP_MIN, CALM_GAP_MAX)
		return
	_calm_phrase = _rng.randf_range(CALM_PHRASE_MIN, CALM_PHRASE_MAX)
	_raise(STATE_CALM, _calm_phrase * CALM_SLOPE)
	_calm_on = true
	# The fall is commanded once the plateau is over and takes the same time as
	# the rise, so the whole swell spans the drawn phrase length.
	_calm_left = _calm_phrase * (1.0 - CALM_SLOPE)


func _schedule_calm_entry() -> void:
	_calm_on = false
	_calm_phrase = 0.0
	_calm_left = _rng.randf_range(CALM_ENTRY_MIN, CALM_ENTRY_MAX)


## Restores the audible state after the player brings the volume back up.
func _resume() -> void:
	if _state == STATE_VICTORY:
		# The motif is a one shot and its timing is long gone; drop straight
		# back to calm rather than replaying it out of context.
		set_state(STATE_CALM)
		return
	if _state == STATE_CALM:
		_calm_on = false
		_calm_left = _rng.randf_range(CALM_ENTRY_MIN * 0.4, CALM_ENTRY_MAX * 0.6)
		return
	_raise(_state, CROSSFADE)


# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------

func _build_players() -> void:
	if _built:
		return
	_built = true
	_bus = _ensure_bus()
	_gain.resize(VOICES)
	_target.resize(VOICES)
	_rate.resize(VOICES)
	_carried.resize(VOICES)
	for i: int in VOICES:
		var player := AudioStreamPlayer.new()
		player.name = "MusicVoice_%d" % i
		player.bus = _bus
		player.max_polyphony = 1
		player.volume_db = SILENT_DB
		player.process_mode = Node.PROCESS_MODE_ALWAYS
		add_child(player)
		_voices.append(player)
		_gain[i] = 0.0
		_target[i] = 0.0
		_rate[i] = 1.0
		_carried[i] = -1


## Brings a state's layer up while everything already sounding goes down.
func _raise(layer: int, fade_in: float) -> void:
	# A player outside the tree cannot start, and Godot says so loudly. The
	# state machine keeps running either way; it is the audio that waits.
	if not is_inside_tree():
		return
	var stream: AudioStreamWAV = _stream_of(layer)
	if stream == null:
		return
	_lower_all(CROSSFADE)
	var index: int = _pick_voice()
	if index < 0:
		return
	var player: AudioStreamPlayer = _voices[index]
	player.stream = stream
	player.volume_db = SILENT_DB
	_gain[index] = 0.0
	_target[index] = 1.0
	_rate[index] = 1.0 / maxf(fade_in, 0.02)
	_carried[index] = layer
	player.play()


func _lower_all(fade_out: float) -> void:
	var slope: float = 1.0 / maxf(fade_out, 0.02)
	for i: int in VOICES:
		if _carried[i] < 0:
			continue
		_target[i] = 0.0
		_rate[i] = slope


## Prefers a free voice, otherwise steals the quietest one.
func _pick_voice() -> int:
	var quietest: int = -1
	var lowest: float = INF
	for i: int in VOICES:
		if _carried[i] < 0:
			return i
		if _gain[i] < lowest:
			lowest = _gain[i]
			quietest = i
	if quietest >= 0:
		_voices[quietest].stop()
		_carried[quietest] = -1
	return quietest


func _advance_voices(delta: float, volume: float) -> void:
	for i: int in VOICES:
		if _carried[i] < 0:
			continue
		var player: AudioStreamPlayer = _voices[i]
		var g: float = _gain[i]
		var goal: float = _target[i]
		if g < goal:
			g = minf(goal, g + _rate[i] * delta)
		elif g > goal:
			g = maxf(goal, g - _rate[i] * delta)
		_gain[i] = g
		# A faded out layer, or a one shot motif that reached its end, gives its
		# voice back at once. Loops never end on their own, which is precisely
		# why this is explicit.
		if (g <= 0.0 and goal <= 0.0) or not player.playing:
			player.stop()
			player.volume_db = SILENT_DB
			_gain[i] = 0.0
			_target[i] = 0.0
			_carried[i] = -1
			continue
		player.volume_db = _to_db(g * volume) + _trim_of(_carried[i])


## Stops every voice on the spot. Used when the music is turned off and on a
## scene teardown, where nothing must survive into the next world.
func _hush() -> void:
	for i: int in _voices.size():
		var player: AudioStreamPlayer = _voices[i]
		if player.playing:
			player.stop()
		player.volume_db = SILENT_DB
		_gain[i] = 0.0
		_target[i] = 0.0
		_carried[i] = -1
	_calm_on = false


func _trim_of(layer: int) -> float:
	match layer:
		STATE_CALM:
			return TRIM_CALM
		STATE_SEARCH:
			return TRIM_SEARCH
		STATE_COMBAT:
			return TRIM_COMBAT
		STATE_VICTORY:
			return TRIM_VICTORY
	return TRIM_CALM


func _to_db(linear: float) -> float:
	if linear <= MUTE_EPSILON:
		return SILENT_DB
	return maxf(linear_to_db(linear), SILENT_DB)


## Player setting, 0 .. 1. Falls back to a sane default outside a real game.
func _volume() -> float:
	if _game == null:
		return DEFAULT_VOLUME
	var value: Variant = _game.get("music_volume")
	var kind: int = typeof(value)
	if kind != TYPE_FLOAT and kind != TYPE_INT:
		return DEFAULT_VOLUME
	return clampf(float(value), 0.0, 1.0)


## The project has no bus layout resource, so the dedicated music bus is added
## at runtime. Any failure simply leaves the music on the master bus, where the
## per voice trim still does the whole job.
func _ensure_bus() -> String:
	var index: int = AudioServer.get_bus_index(BUS_NAME)
	if index >= 0:
		return BUS_NAME
	var count: int = AudioServer.bus_count
	AudioServer.add_bus(count)
	if AudioServer.bus_count <= count:
		return FALLBACK_BUS
	AudioServer.set_bus_name(count, BUS_NAME)
	AudioServer.set_bus_send(count, FALLBACK_BUS)
	AudioServer.set_bus_volume_db(count, 0.0)
	if AudioServer.get_bus_index(BUS_NAME) < 0:
		return FALLBACK_BUS
	return BUS_NAME


# ---------------------------------------------------------------------------
# Bank
# ---------------------------------------------------------------------------

## Synthesises a layer on first use and keeps it. Nothing here touches the scene
## tree or the display server, so it is safe in headless mode.
func _stream_of(layer: int) -> AudioStreamWAV:
	if _streams.has(layer):
		return _streams[layer] as AudioStreamWAV
	var stream: AudioStreamWAV = null
	match layer:
		STATE_CALM:
			stream = _build_calm()
		STATE_SEARCH:
			stream = _build_search()
		STATE_COMBAT:
			stream = _build_combat()
		STATE_VICTORY:
			stream = _build_victory()
	if stream == null:
		push_warning("Music: could not synthesise the layer \"%s\"." % state_name(layer))
		return null
	_streams[layer] = stream
	return stream


## Calm: a very low drone that has nothing to say.
##
## An open fifth on A1 with no third at all, so the harmony never resolves into
## major or minor, plus a faint minor sixth that breathes in and out and keeps
## the whole thing uneasy. Each partial is detuned against a twin by one or two
## grid steps: the pair beats over three to six seconds instead of standing
## still, which is what turns eight sine waves into a pad.
static func _build_calm() -> AudioStreamWAV:
	var rate: int = CALM_RATE
	var grid: float = 1.0 / CALM_LOOP
	var buf: PackedFloat32Array = _buf(rate, CALM_LOOP)
	_partial(buf, rate, 330.0 * grid, 0.55, 0.00, 1.0 * grid, 0.30)
	_partial(buf, rate, 332.0 * grid, 0.40, 0.37, 2.0 * grid, 0.30)
	_partial(buf, rate, 495.0 * grid, 0.30, 0.11, 1.0 * grid, 0.35)
	_partial(buf, rate, 496.0 * grid, 0.21, 0.63, 3.0 * grid, 0.30)
	_partial(buf, rate, 660.0 * grid, 0.17, 0.25, 2.0 * grid, 0.40)
	_partial(buf, rate, 524.0 * grid, 0.10, 0.80, 1.0 * grid, 0.65)
	_partial(buf, rate, 990.0 * grid, 0.06, 0.50, 3.0 * grid, 0.55)
	_partial(buf, rate, 1320.0 * grid, 0.035, 0.90, 5.0 * grid, 0.60)
	_normalize(buf, 0.50)
	return _to_stream(buf, rate, true)


## Search: a heart, not a chase.
##
## Two beats per cycle, twenty five to the minute, each a lub and a softer dub a
## third of a second later. Underneath, a drone an octave below the calm pad so
## the space between beats is not dead air. The percussion lives in its own
## buffer, has decayed by the third second and is tail faded, so the loop seam
## falls in silence.
static func _build_search() -> AudioStreamWAV:
	var rate: int = BED_RATE
	var grid: float = 1.0 / SEARCH_LOOP
	var buf: PackedFloat32Array = _buf(rate, SEARCH_LOOP)
	_partial(buf, rate, 198.0 * grid, 0.16, 0.00, 1.0 * grid, 0.35)
	_partial(buf, rate, 297.0 * grid, 0.10, 0.40, 2.0 * grid, 0.40)
	_partial(buf, rate, 396.0 * grid, 0.05, 0.70, 3.0 * grid, 0.45)
	var perc: PackedFloat32Array = _buf(rate, SEARCH_LOOP)
	_heartbeat(perc, rate, 0.00, 1.00, 20101)
	_heartbeat(perc, rate, 0.36, 0.62, 20719)
	_heartbeat(perc, rate, 2.30, 0.94, 21283)
	_heartbeat(perc, rate, 2.66, 0.58, 21851)
	_tail_fade(perc, rate, 0.12)
	_mix(buf, perc, 1.0)
	_normalize(buf, 0.62)
	return _to_stream(buf, rate, true)


## Combat: pressure, still no story.
##
## Three sustained brass notes a semitone and a tritone apart. The cluster
## grinds without ever stating a chord, and it is held down to the third
## harmonic because anything brighter turns into a fanfare. Over it, eight kicks
## on the half second with alternating accents and eight dry off beat ticks, so
## the pulse is denser than the search heartbeat without becoming a groove.
static func _build_combat() -> AudioStreamWAV:
	var rate: int = BED_RATE
	var grid: float = 1.0 / COMBAT_LOOP
	var buf: PackedFloat32Array = _buf(rate, COMBAT_LOOP)
	_brass(buf, rate, 466.0 * grid, 0.30, 0.00, 1.0 * grid, 0.45)
	_brass(buf, rate, 494.0 * grid, 0.26, 0.30, 1.0 * grid, 0.55)
	_brass(buf, rate, 699.0 * grid, 0.16, 0.60, 2.0 * grid, 0.65)
	var perc: PackedFloat32Array = _buf(rate, COMBAT_LOOP)
	var accents := PackedFloat32Array([1.00, 0.46, 0.72, 0.44, 0.94, 0.46, 0.70, 0.50])
	for i: int in 8:
		_kick(perc, rate, float(i) * 0.5, accents[i], 31013 + i * 617)
		_tick(perc, rate, 0.25 + float(i) * 0.5, 0.22, 41011 + i * 733)
	_tail_fade(perc, rate, 0.09)
	_mix(buf, perc, 1.0)
	_normalize(buf, 0.72)
	return _to_stream(buf, rate, true)


## Victory: a village changing hands.
##
## F major stated from the bottom up, one note at a time over two and a half
## seconds, then a long release. Low brass and two soft drums, no cymbal and no
## flourish: this is a liberation, not a cleared level. One shot, five and a
## half seconds, and the state machine falls back to calm on its own.
static func _build_victory() -> AudioStreamWAV:
	var rate: int = MOTIF_RATE
	var buf: PackedFloat32Array = _buf(rate, VICTORY_SECONDS)
	_horn(buf, rate, 87.31, 0.34, 0.00, 1.10, 0.40)
	_horn(buf, rate, 130.81, 0.26, 0.50, 1.00, 0.38)
	_horn(buf, rate, 110.00, 0.20, 1.20, 0.90, 0.42)
	_horn(buf, rate, 174.61, 0.15, 1.95, 0.80, 0.44)
	_kick(buf, rate, 0.00, 0.55, 51043)
	_kick(buf, rate, 1.15, 0.42, 51721)
	_tail_fade(buf, rate, 1.60)
	_normalize(buf, 0.70)
	return _to_stream(buf, rate, false)


# ---------------------------------------------------------------------------
# Voicings
# ---------------------------------------------------------------------------

## One sustained brass note: fundamental plus two harmonics under a single slow
## tremolo, since one note is one breath.
##
## The three harmonics share a pass rather than calling `_partial` three times.
## The loop bookkeeping and the tremolo are the expensive half of that inner
## loop, so folding a note into one pass costs a third of what three passes do,
## and this is the layer that decides the worst frame of the whole module.
##
## The harmonics stay integer multiples of the fundamental, so a note that loops
## keeps looping. `freq * 3` must stay under the Nyquist rate.
static func _brass(buf: PackedFloat32Array, rate: int, freq: float, amp: float,
		phase: float, lfo_hz: float, depth: float) -> void:
	var n: int = buf.size()
	if n <= 0 or amp <= 0.0:
		return
	var w: float = TAU * freq / float(rate)
	var p: float = TAU * phase
	var c1: float = 2.0 * cos(w)
	var c2: float = 2.0 * cos(2.0 * w)
	var c3: float = 2.0 * cos(3.0 * w)
	# Quarter turn apart, so the three harmonics do not all peak together and
	# the note keeps a rounded top instead of a spike.
	var p2: float = p + PI * 0.5
	var p3: float = p + PI
	var x1_prev: float = sin(p)
	var x1_cur: float = sin(p + w)
	var x2_prev: float = sin(p2)
	var x2_cur: float = sin(p2 + 2.0 * w)
	var x3_prev: float = sin(p3)
	var x3_cur: float = sin(p3 + 3.0 * w)
	var a2: float = 0.50
	var a3: float = 0.26
	var d: float = clampf(depth, 0.0, 1.0)
	var base: float = amp * (1.0 - d * 0.5)
	var swing: float = amp * d * 0.5
	var lw: float = TAU * lfo_hz / float(rate)
	var l_two_cos: float = 2.0 * cos(lw)
	var l_prev: float = 0.0
	var l_cur: float = sin(lw)
	for i: int in n:
		buf[i] += (x1_prev + x2_prev * a2 + x3_prev * a3) * (base + swing * l_prev)
		var x1_next: float = c1 * x1_cur - x1_prev
		x1_prev = x1_cur
		x1_cur = x1_next
		var x2_next: float = c2 * x2_cur - x2_prev
		x2_prev = x2_cur
		x2_cur = x2_next
		var x3_next: float = c3 * x3_cur - x3_prev
		x3_prev = x3_cur
		x3_cur = x3_next
		var l_next: float = l_two_cos * l_cur - l_prev
		l_prev = l_cur
		l_cur = l_next


## One slowly swelling horn note for the motif: same three harmonics, folded
## into one pass for the same reason, under a single attack and release.
static func _horn(buf: PackedFloat32Array, rate: int, freq: float, amp: float,
		at: float, attack: float, decay: float) -> void:
	var n: int = buf.size()
	var i0: int = int(at * float(rate))
	if i0 >= n or amp <= 0.0:
		return
	var w: float = TAU * freq / float(rate)
	var c1: float = 2.0 * cos(w)
	var c2: float = 2.0 * cos(2.0 * w)
	var c3: float = 2.0 * cos(3.0 * w)
	var x1_prev: float = 0.0
	var x1_cur: float = sin(w)
	var x2_prev: float = 0.0
	var x2_cur: float = sin(2.0 * w)
	var x3_prev: float = 0.0
	var x3_cur: float = sin(3.0 * w)
	var k: float = _decay_step(rate, decay)
	var atk: float = maxf(attack, 0.0) * float(rate)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var i: int = i0
	var t: float = 0.0
	while i < n:
		var e: float = env
		if t < atk:
			# Squared rise: a horn leans into a note, it does not ramp.
			var u: float = t * inv_atk
			e *= u * u
		buf[i] += (x1_prev + x2_prev * 0.42 + x3_prev * 0.18) * e
		var x1_next: float = c1 * x1_cur - x1_prev
		x1_prev = x1_cur
		x1_cur = x1_next
		var x2_next: float = c2 * x2_cur - x2_prev
		x2_prev = x2_cur
		x2_cur = x2_next
		var x3_next: float = c3 * x3_cur - x3_prev
		x3_prev = x3_cur
		x3_cur = x3_next
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## A chest beat: a short downward thump, a body tone and a dull skin slap.
static func _heartbeat(buf: PackedFloat32Array, rate: int, at: float, amp: float,
		noise_seed: int) -> void:
	_sweep(buf, rate, 78.0, 42.0, 0.20, 0.85 * amp, 11.0, at, 0.006)
	_tone(buf, rate, 55.0, 0.42 * amp, 10.0, at, 0.010)
	_noise(buf, rate, noise_seed, 0.30 * amp, 24.0, 900.0, 140.0, 0.20, at, 0.003)


## A harder, faster war drum for the combat bed and the motif.
static func _kick(buf: PackedFloat32Array, rate: int, at: float, amp: float,
		noise_seed: int) -> void:
	_sweep(buf, rate, 96.0, 46.0, 0.16, 0.90 * amp, 13.0, at, 0.004)
	_noise(buf, rate, noise_seed, 0.34 * amp, 30.0, 1500.0, 220.0, 0.14, at, 0.002)


## A dry off beat, just enough to fill the gap between two kicks.
static func _tick(buf: PackedFloat32Array, rate: int, at: float, amp: float,
		noise_seed: int) -> void:
	_noise(buf, rate, noise_seed, amp, 46.0, 1800.0, 600.0, 0.09, at, 0.001)


# ---------------------------------------------------------------------------
# Synthesis primitives
# ---------------------------------------------------------------------------

## Allocates a silent buffer of the requested length in seconds.
static func _buf(rate: int, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(maxi(1, int(seconds * float(rate))))
	out.fill(0.0)
	return out


## One pole low pass coefficient for a cut off in Hz.
static func _lp_alpha(rate: int, cutoff_hz: float) -> float:
	var c: float = clampf(cutoff_hz, 15.0, float(rate) * 0.45)
	return clampf(1.0 - exp(-TAU * c / float(rate)), 0.0, 1.0)


## Per sample multiplier equivalent to an exponential decay of `rate_np` nepers
## per second advanced by one sample.
static func _decay_step(rate: int, rate_np: float) -> float:
	return exp(-rate_np / float(rate))


## Adds a sustained sine with a slow tremolo. Both the carrier and the tremolo
## run on a two term sine recurrence, one multiply per sample instead of a call
## into `sin()`, which is what keeps a six second pad in the low tens of
## milliseconds.
##
## For the buffer to loop, `freq` and `lfo_hz` must both be integer multiples of
## the reciprocal of its length; the phase offset is free, since the phase still
## advances by a whole number of turns over one cycle.
static func _partial(buf: PackedFloat32Array, rate: int, freq: float, amp: float,
		phase: float, lfo_hz: float, depth: float) -> void:
	var n: int = buf.size()
	if n <= 0 or amp <= 0.0:
		return
	var w: float = TAU * freq / float(rate)
	var two_cos: float = 2.0 * cos(w)
	var p: float = TAU * phase
	var s_prev: float = sin(p)
	var s_cur: float = sin(p + w)
	var d: float = clampf(depth, 0.0, 1.0)
	var base: float = amp * (1.0 - d * 0.5)
	var swing: float = amp * d * 0.5
	var lw: float = TAU * lfo_hz / float(rate)
	var l_two_cos: float = 2.0 * cos(lw)
	var l_prev: float = 0.0
	var l_cur: float = sin(lw)
	for i: int in n:
		buf[i] += s_prev * (base + swing * l_prev)
		var s_next: float = two_cos * s_cur - s_prev
		s_prev = s_cur
		s_cur = s_next
		var l_next: float = l_two_cos * l_cur - l_prev
		l_prev = l_cur
		l_cur = l_next


## Adds a decaying sine with a linear attack, starting at `at` seconds.
static func _tone(buf: PackedFloat32Array, rate: int, freq: float, amp: float,
		decay: float, at: float, attack: float) -> void:
	var n: int = buf.size()
	var i0: int = int(at * float(rate))
	if i0 >= n or amp <= 0.0:
		return
	var w: float = TAU * freq / float(rate)
	var two_cos: float = 2.0 * cos(w)
	var s_prev: float = 0.0
	var s_cur: float = sin(w)
	var k: float = _decay_step(rate, decay)
	var atk: float = maxf(attack, 0.0) * float(rate)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var i: int = i0
	var t: float = 0.0
	while i < n:
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += s_prev * e
		var s_next: float = two_cos * s_cur - s_prev
		s_prev = s_cur
		s_cur = s_next
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## Adds a decaying sine gliding from `f0` to `f1` over `glide` seconds, then
## holding at `f1`. The downward thump of every drum in this file.
static func _sweep(buf: PackedFloat32Array, rate: int, f0: float, f1: float,
		glide: float, amp: float, decay: float, at: float, attack: float) -> void:
	var n: int = buf.size()
	var i0: int = int(at * float(rate))
	if i0 >= n or amp <= 0.0:
		return
	var steps: float = maxf(glide, 0.001) * float(rate)
	var inv: float = TAU / float(rate)
	var f: float = f0 * inv
	var df: float = (f1 - f0) * inv / steps
	var k: float = _decay_step(rate, decay)
	var atk: float = maxf(attack, 0.0) * float(rate)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var ph: float = 0.0
	var i: int = i0
	var t: float = 0.0
	while i < n:
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += sin(ph) * e
		ph += f
		if t < steps:
			f += df
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## Adds a low passed noise burst whose cut off glides from `cut_start` to
## `cut_end` over `glide` seconds, under an exponential decay. Inlining the
## generator instead of calling `RandomNumberGenerator` per sample is what makes
## the noise cheaper than the sines around it.
static func _noise(buf: PackedFloat32Array, rate: int, noise_seed: int, amp: float,
		decay: float, cut_start: float, cut_end: float, glide: float,
		at: float, attack: float) -> void:
	var n: int = buf.size()
	var i0: int = int(at * float(rate))
	if i0 >= n or amp <= 0.0:
		return
	var steps: float = maxf(glide, 0.001) * float(rate)
	var a: float = _lp_alpha(rate, cut_start)
	var da: float = (_lp_alpha(rate, cut_end) - a) / steps
	var k: float = _decay_step(rate, decay)
	var atk: float = maxf(attack, 0.0) * float(rate)
	var inv_atk: float = 0.0 if atk < 1.0 else 1.0 / atk
	var env: float = amp
	var y: float = 0.0
	var st: int = (noise_seed & 0x7fffffff) | 1
	var i: int = i0
	var t: float = 0.0
	while i < n:
		st = (st * 1103515245 + 12345) & 0x7fffffff
		y += a * (float(st) * NOISE_SCALE - 1.0 - y)
		if t < steps:
			a += da
		var e: float = env
		if t < atk:
			e *= t * inv_atk
		buf[i] += y * e
		env *= k
		if env < SILENCE and t > atk:
			break
		i += 1
		t += 1.0


## Adds `src` scaled by `gain` into `dst`.
static func _mix(dst: PackedFloat32Array, src: PackedFloat32Array, gain: float) -> void:
	var n: int = mini(dst.size(), src.size())
	for i: int in n:
		dst[i] += src[i] * gain


## Linear fade over the last `seconds` of the buffer. Used on the percussion
## layers so their residue reaches exactly zero at the loop seam, and on the
## victory motif as its release.
static func _tail_fade(buf: PackedFloat32Array, rate: int, seconds: float) -> void:
	var n: int = buf.size()
	var f: int = mini(int(seconds * float(rate)), n)
	if f <= 1:
		return
	for i: int in f:
		buf[n - f + i] *= 1.0 - float(i) / float(f - 1)


## Scales the buffer so its loudest sample reaches `peak`.
static func _normalize(buf: PackedFloat32Array, peak: float) -> void:
	var n: int = buf.size()
	var top: float = 0.0
	for i: int in n:
		var v: float = buf[i]
		if v < 0.0:
			v = -v
		if v > top:
			top = v
	if top < 0.000001:
		return
	var g: float = peak / top
	for i: int in n:
		buf[i] *= g


## Packs float samples into signed 16 bit little endian PCM.
##
## Looping streams are flagged LOOP_FORWARD, which means they never end and
## never free their player by themselves. That is safe here and nowhere else:
## these players belong to this node and `_advance_voices` stops them.
static func _to_stream(buf: PackedFloat32Array, rate: int, looping: bool) -> AudioStreamWAV:
	var n: int = buf.size()
	var bytes := PackedByteArray()
	bytes.resize(n * 2)
	var j: int = 0
	for i: int in n:
		var v: float = buf[i] * 32767.0
		if v > 32767.0:
			v = 32767.0
		elif v < -32767.0:
			v = -32767.0
		var s: int = int(v)
		if s < 0:
			s += 65536
		bytes[j] = s & 255
		bytes[j + 1] = (s >> 8) & 255
		j += 2
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = rate
	stream.stereo = false
	stream.data = bytes
	if looping:
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = n
	else:
		stream.loop_mode = AudioStreamWAV.LOOP_DISABLED
	return stream
