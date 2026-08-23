extends Node
## Autoload `Sfx`. Owns the synthesised sound library and a fixed pool of
## players, so the rest of the game only ever names a sound and a position.
##
## The library is built once in _ready(): SfxLib.build() synthesises the 28
## AudioStreamWAV entries, which costs a few tens of milliseconds and never
## touches the disk.
##
## Pooling is fixed size on purpose. Creating an AudioStreamPlayer3D per dig
## tick would allocate a node several times per second, so the pool is scanned
## for a free player first and falls back to plain round robin when everything
## is busy, which drops the oldest sound instead of the newest one.

## Spatialised voices, used by every world sound.
const POOL_3D := 12

## Non spatialised voices, used by the interface.
const POOL_2D := 4

## Minimum delay between two digging ticks. play_dig() is called every frame
## while the mouse button is held, so it has to rate limit itself.
const DIG_INTERVAL := 0.22

## Random pitch spread applied to material sounds so repetition never sounds
## mechanical.
const PITCH_JITTER := 0.08

## Distance in metres at which a spatial sound has fallen to unit gain. Larger
## values make sounds carry further.
const UNIT_SIZE := 12.0

const MAX_DISTANCE := 64.0

## Volume used when Game.sfx_volume is zero. linear_to_db(0.0) is negative
## infinity, which some audio drivers dislike, so it is clamped here.
const SILENCE_DB := -80.0

## Relative levels, the only place where sounds are balanced against each other
## (the buffers themselves are all normalised to the same peak).
const DIG_DB := -7.0
const BREAK_DB := -2.0
const PLACE_DB := -4.0
const STEP_DB := -11.0

var _library: Dictionary = {}
var _players_3d: Array[AudioStreamPlayer3D] = []
var _players_2d: Array[AudioStreamPlayer] = []
var _next_3d: int = 0
var _next_2d: int = 0

## Timestamp of the last digging tick, in seconds from the engine clock.
var _last_dig: float = -1000.0

var _rng := RandomNumberGenerator.new()

## Cached autoload lookup. Resolved lazily because autoload order is not
## guaranteed to put Game before Sfx.
var _game: Node = null


func _ready() -> void:
	_rng.randomize()
	_library = SfxLib.build()
	_build_pool()


func _build_pool() -> void:
	for i in POOL_3D:
		var spatial := AudioStreamPlayer3D.new()
		spatial.name = "Spatial%02d" % i
		spatial.unit_size = UNIT_SIZE
		spatial.max_distance = MAX_DISTANCE
		spatial.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		spatial.max_polyphony = 1
		spatial.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
		add_child(spatial)
		_players_3d.append(spatial)

	for i in POOL_2D:
		var flat := AudioStreamPlayer.new()
		flat.name = "Flat%02d" % i
		flat.max_polyphony = 1
		add_child(flat)
		_players_2d.append(flat)


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

## Plays a sound without spatialisation, for interface feedback.
func play(sound: String, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var stream := _stream_of(sound)
	if stream == null:
		return
	var player := _acquire_2d()
	player.stream = stream
	player.pitch_scale = clampf(pitch, 0.05, 4.0)
	player.volume_db = _mix_db(volume_db)
	player.play()


## Plays a sound at a world position through the spatial pool.
func play_at(sound: String, position: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void:
	var stream := _stream_of(sound)
	if stream == null:
		return
	var player := _acquire_3d()
	player.stream = stream
	player.global_position = position
	player.pitch_scale = clampf(pitch, 0.05, 4.0)
	player.volume_db = _mix_db(volume_db)
	player.play()


## Digging feedback. Called every frame while `dig` is held, so it plays at most
## one tick every DIG_INTERVAL seconds.
func play_dig(block_id: int, position: Vector3) -> void:
	var now := _now()
	if now - _last_dig < DIG_INTERVAL:
		return
	_last_dig = now
	play_at("dig_" + material_family(block_id), position, DIG_DB, _jitter())


## Clears the digging rate limit so the next dig starts on its first frame.
func stop_dig() -> void:
	_last_dig = -1000.0


func play_break(block_id: int, position: Vector3) -> void:
	play_at("break_" + material_family(block_id), position, BREAK_DB, _jitter())


func play_place(block_id: int, position: Vector3) -> void:
	# One shared thump, pitched by material so wool lands lower than glass.
	play_at("place", position, PLACE_DB, _place_pitch(block_id) * _jitter())


func play_step(block_id: int, position: Vector3) -> void:
	play_at("step_" + _step_family(block_id), position, STEP_DB, _jitter())


# ---------------------------------------------------------------------------
# Material mapping
# ---------------------------------------------------------------------------

## Material family of a block: "stone", "dirt", "grass", "sand", "wood",
## "glass", "wool" or "plant". Every id of Blocks is covered; anything
## unexpected falls back to "stone".
static func material_family(block_id: int) -> String:
	match block_id:
		Blocks.DIRT, Blocks.GRAVEL, Blocks.CLAY, Blocks.SNOW_BLOCK:
			return "dirt"
		Blocks.GRASS:
			return "grass"
		Blocks.SAND:
			return "sand"
		Blocks.STONE, Blocks.COBBLESTONE, Blocks.STONE_BRICK, Blocks.GRANITE, \
		Blocks.MARBLE, Blocks.MOSSY_COBBLE, Blocks.SANDSTONE, Blocks.OBSIDIAN, \
		Blocks.BEDROCK, Blocks.BRICK, Blocks.LAMP, Blocks.COAL_ORE, \
		Blocks.IRON_ORE, Blocks.GOLD_ORE, Blocks.DIAMOND_ORE:
			return "stone"
		Blocks.OAK_LOG, Blocks.OAK_PLANKS, Blocks.BIRCH_LOG, Blocks.BIRCH_PLANKS, \
		Blocks.BOOKSHELF, Blocks.PUMPKIN, Blocks.CRAFTING_TABLE, Blocks.CHEST:
			return "wood"
		Blocks.GLASS, Blocks.ICE:
			return "glass"
		Blocks.WOOL_WHITE, Blocks.WOOL_RED, Blocks.WOOL_YELLOW, \
		Blocks.WOOL_GREEN, Blocks.WOOL_BLUE:
			return "wool"
		Blocks.OAK_LEAVES, Blocks.BIRCH_LEAVES, Blocks.PINE_LEAVES, Blocks.CACTUS, \
		Blocks.GRASS_TUFT, Blocks.FERN, Blocks.DEAD_BUSH, Blocks.FLOWER_RED, \
		Blocks.FLOWER_YELLOW, Blocks.SAPLING, Blocks.TORCH:
			return "plant"
	return "stone"


## Footstep variant. There is no step_wool, step_glass or step_plant sound, so
## soft and hard materials are folded onto the nearest existing surface, and
## snow gets its own crunch.
static func _step_family(block_id: int) -> String:
	if block_id == Blocks.SNOW_BLOCK:
		return "snow"
	var family := material_family(block_id)
	match family:
		"wool":
			return "dirt"
		"glass":
			return "stone"
		"plant":
			return "grass"
	return family


## Slight pitch bias of the shared `place` thump per material family.
static func _place_pitch(block_id: int) -> float:
	match material_family(block_id):
		"wool":
			return 0.80
		"dirt", "sand":
			return 0.92
		"grass":
			return 0.96
		"wood":
			return 1.00
		"glass":
			return 1.22
		"plant":
			return 1.14
	return 1.06


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

func _stream_of(sound: String) -> AudioStreamWAV:
	if not _library.has(sound):
		push_warning("Sfx: unknown sound '%s'" % sound)
		return null
	return _library[sound]


func _jitter() -> float:
	return _rng.randf_range(1.0 - PITCH_JITTER, 1.0 + PITCH_JITTER)


func _now() -> float:
	return float(Time.get_ticks_msec()) * 0.001


## Applies the user volume as a decibel offset on top of the caller's level.
func _mix_db(volume_db: float) -> float:
	var linear := _sfx_volume()
	if linear <= 0.001:
		return SILENCE_DB
	return volume_db + linear_to_db(linear)


func _sfx_volume() -> float:
	if _game == null or not is_instance_valid(_game):
		_game = get_node_or_null("/root/Game")
	if _game == null:
		return 1.0
	var value: Variant = _game.get("sfx_volume")
	if value == null:
		return 1.0
	return clampf(float(value), 0.0, 1.0)


## Next spatial voice: the first idle one starting from the cursor, otherwise
## plain round robin so a burst of sounds still cycles instead of stacking on
## one player.
func _acquire_3d() -> AudioStreamPlayer3D:
	for i in POOL_3D:
		var index: int = (_next_3d + i) % POOL_3D
		var candidate := _players_3d[index]
		if not candidate.playing:
			_next_3d = (index + 1) % POOL_3D
			return candidate
	var fallback := _players_3d[_next_3d]
	_next_3d = (_next_3d + 1) % POOL_3D
	return fallback


func _acquire_2d() -> AudioStreamPlayer:
	for i in POOL_2D:
		var index: int = (_next_2d + i) % POOL_2D
		var candidate := _players_2d[index]
		if not candidate.playing:
			_next_2d = (index + 1) % POOL_2D
			return candidate
	var fallback := _players_2d[_next_2d]
	_next_2d = (_next_2d + 1) % POOL_2D
	return fallback
