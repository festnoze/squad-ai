class_name Crowd
extends Node
## The crowd, as a sound source. It plays nothing itself: it decides what the
## stadium should be doing and asks `Sfx` for it.
##
## Three behaviours, in order of importance:
##
## 1. A bed whose level follows the tension. A shootout is not loud all the way
##    through - it swells before a decisive kick and drops back afterwards - and
##    the difference between a first round penalty and a sudden death one is
##    carried almost entirely by this single number.
## 2. Reactions. A verdict fires a shaped sequence, not one sample: a goal is a
##    roar that turns into applause half a second later, a post is a gasp that
##    settles into a groan. Sequencing two beds is what makes the crowd sound
##    like people rather than like a button.
## 3. The hush. Just before the strike the ambience is ducked hard and fast,
##    then allowed back up. Silence is the loudest tool available here, and the
##    held breath is what makes the following roar land.
##
## Everything is expressed in decibels because that is what the mixer takes, and
## the module never touches a voice directly: only `Sfx` owns voices.


## Mirrors Shootout.Verdict. Kept as local constants so this module depends on
## nothing but the mixer, which also means the enum values are visible right
## here when reading the reaction table below.
const VERDICT_BUT := 0
const VERDICT_ARRET := 1
const VERDICT_POTEAU := 2
const VERDICT_BARRE := 3
const VERDICT_DEHORS := 4

const AMBIENCE_ID := "crowd_ambience"

## Bed level at tension 0 and at tension 1.
const CALM_DB := -25.0
const TENSE_DB := -10.0
## Level held while the crowd holds its breath.
const HUSH_DB := -36.0
## Extra level while a reaction is still ringing out.
const REACTION_BOOST_DB := 6.0

const HUSH_DUCK_SECONDS := 0.22
const HUSH_HOLD_SECONDS := 1.9
const HUSH_RELEASE_SECONDS := 0.95
const REACTION_HOLD_SECONDS := 4.0

var _tension: float = 0.0
var _hush_left: float = 0.0
var _boost_left: float = 0.0
var _murmur_left: float = 5.0
var _started: bool = false
## Queued one shots: {"id": String, "delay": float, "db": float, "pitch": float}.
var _pending: Array[Dictionary] = []
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	_rng.seed = 5514877


func _process(delta: float) -> void:
	# Nothing happens before build(): the node may well be in the tree while the
	# rest of the stadium is still being assembled.
	if not _started:
		return
	_advance_pending(delta)

	if _hush_left > 0.0:
		_hush_left -= delta
		if _hush_left <= 0.0:
			_hush_left = 0.0
			_apply_level(HUSH_RELEASE_SECONDS)

	if _boost_left > 0.0:
		_boost_left -= delta
		if _boost_left <= 0.0:
			_boost_left = 0.0
			_apply_level(1.6)

	_murmur_left -= delta
	if _murmur_left <= 0.0:
		_murmur()


func build() -> void:
	if not _started:
		_started = true
		_rng.seed = 5514877
	_pending.clear()
	_hush_left = 0.0
	_boost_left = 0.0
	_murmur_left = _murmur_interval()
	Sfx.set_ambience(AMBIENCE_ID, _bed_db())


## Tension in [0, 1], drives the ambience level and the murmur.
func set_tension(level: float) -> void:
	var wanted := clampf(level, 0.0, 1.0)
	if is_equal_approx(wanted, _tension):
		return
	_tension = wanted
	if _hush_left <= 0.0:
		# Slow on purpose: a crowd that jumps to a new level every time a number
		# changes sounds like a fader, not like people.
		_apply_level(1.3)


## One off reaction to a Shootout.Verdict.
func react(verdict: int) -> void:
	# A reaction cancels the held breath: whatever happened, they are breathing
	# again.
	_hush_left = 0.0
	_boost_left = REACTION_HOLD_SECONDS

	match verdict:
		VERDICT_BUT:
			Sfx.play("crowd_roar", 0.0, _rng.randf_range(0.97, 1.03))
			_queue("crowd_clap", 0.75, -3.0, _rng.randf_range(0.98, 1.04))
			_queue("crowd_clap", 2.30, -9.0, _rng.randf_range(0.94, 1.0))
		VERDICT_ARRET:
			# The keeper is the other side's: the home crowd deflates, then
			# gives the save its due.
			Sfx.play("crowd_groan", -1.0, _rng.randf_range(0.97, 1.03))
			_queue("crowd_clap", 1.15, -11.0, 1.0)
		VERDICT_POTEAU, VERDICT_BARRE:
			# Woodwork: everyone rises, then realises it stayed out.
			Sfx.play("crowd_ooh", 0.0, _rng.randf_range(1.0, 1.06))
			_queue("crowd_groan", 0.60, -5.0, _rng.randf_range(0.95, 1.0))
		VERDICT_DEHORS:
			Sfx.play("crowd_ooh", -4.0, _rng.randf_range(0.94, 1.0))
			_queue("crowd_groan", 0.35, -1.0, _rng.randf_range(0.96, 1.02))
		_:
			push_warning("Crowd: unknown verdict %d" % verdict)
			_boost_left = 0.0
			return

	_apply_level(0.35)
	_murmur_left = maxf(_murmur_left, REACTION_HOLD_SECONDS + 1.5)


## The held breath just before a strike.
func hush() -> void:
	_pending.clear()
	_boost_left = 0.0
	_hush_left = HUSH_HOLD_SECONDS
	_murmur_left = maxf(_murmur_left, HUSH_HOLD_SECONDS + 1.0)
	Sfx.fade_ambience(HUSH_DB, HUSH_DUCK_SECONDS)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

## Bed level for the current state, before any fade.
func _bed_db() -> float:
	if _hush_left > 0.0:
		return HUSH_DB
	var level: float = lerpf(CALM_DB, TENSE_DB, _tension * _tension * (3.0 - 2.0 * _tension))
	if _boost_left > 0.0:
		level += REACTION_BOOST_DB
	return level


func _apply_level(seconds: float) -> void:
	Sfx.fade_ambience(_bed_db(), seconds)


func _queue(id: String, delay: float, db: float, pitch: float) -> void:
	_pending.append({"id": id, "delay": delay, "db": db, "pitch": pitch})


func _advance_pending(delta: float) -> void:
	if _pending.is_empty():
		return
	var still_waiting: Array[Dictionary] = []
	for entry in _pending:
		var left: float = float(entry["delay"]) - delta
		if left > 0.0:
			entry["delay"] = left
			still_waiting.append(entry)
		else:
			Sfx.play(String(entry["id"]), float(entry["db"]), float(entry["pitch"]))
	_pending = still_waiting


## Seconds until the next background murmur. A tense crowd never quite settles,
## a calm one only stirs now and then.
func _murmur_interval() -> float:
	var base: float = lerpf(11.0, 4.0, _tension)
	return base * _rng.randf_range(0.7, 1.45)


func _murmur() -> void:
	_murmur_left = _murmur_interval()
	if _hush_left > 0.0 or _boost_left > 0.0:
		return
	# Well under the bed: this is meant to be noticed only in the way a real
	# stadium is never twice the same for two seconds running.
	var db: float = lerpf(-27.0, -19.0, _tension) + _rng.randf_range(-2.0, 2.0)
	if _rng.randf() < 0.35 + 0.3 * _tension:
		Sfx.play("crowd_clap", db - 3.0, _rng.randf_range(0.88, 1.08))
	else:
		Sfx.play("crowd_ooh", db, _rng.randf_range(0.82, 1.02))
