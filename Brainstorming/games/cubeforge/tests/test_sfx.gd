extends TestCase
## Procedural sound library: the shape of the generated data, never playback.
##
## The suite runs headless with no audio device, so nothing is ever played. Every
## check decodes the raw PackedByteArray of the AudioStreamWAV instead, reading
## pairs of bytes as little endian signed 16 bit values.
##
## Two properties matter far more than the rest and are the ones a synthesis bug
## breaks first:
##   - a buffer whose first or last sample is not silent clicks on every single
##     footstep, dig tick and menu press,
##   - a buffer normalised above full scale wraps around in the 16 bit
##     conversion and turns into a burst of digital noise.
## Both are asserted on every sound.

## Full scale of a signed 16 bit sample.
const FULL_SCALE := 32768.0

## Sounds required by section 4.14 of docs/CONTRACTS.md, all 28 of them.
const REQUIRED: PackedStringArray = [
	"dig_stone", "dig_dirt", "dig_grass", "dig_sand",
	"dig_wood", "dig_glass", "dig_wool", "dig_plant",
	"break_stone", "break_dirt", "break_grass", "break_sand",
	"break_wood", "break_glass", "break_wool", "break_plant",
	"place", "pop", "splash", "swim", "click", "land",
	"step_stone", "step_dirt", "step_grass", "step_sand", "step_wood", "step_snow",
]

## The eight documented material families.
const FAMILIES: PackedStringArray = [
	"stone", "dirt", "grass", "sand", "wood", "glass", "wool", "plant",
]

## A sound shorter than this is inaudible, longer than this is a bug rather than
## a sound effect.
const MIN_SECONDS := 0.010
const MAX_SECONDS := 2.0

## Peak window. Below 0.99 leaves headroom so the 16 bit conversion never wraps,
## above 0.3 keeps the sound loud enough to be heard over the rest of the mix.
const MIN_PEAK := 0.95
const MAX_PEAK := 0.99

## Number of samples inspected at each end of a buffer.
const EDGE_SAMPLES := 4

## The very first and last samples must be silent, not merely quiet.
const EDGE_ZERO := 0.001

## Tolerance for the samples just inside the edges: the attack and release ramps
## are a couple of milliseconds long, so these are still far below the peak.
const EDGE_NEAR := 0.0

## material_family lives on the Sfx autoload script (section 4.14), which has no
## class_name, so the suite reaches the static function through the script.
const SFX_PLAYER_PATH := "res://src/audio/sfx_player.gd"


func suite_name() -> String:
	return "sfx"


## Reads sample `i` of a stream as a float in -1..1.
func _sample(data: PackedByteArray, i: int) -> float:
	return float(data.decode_s16(i * 2)) / FULL_SCALE


func test_build_returns_every_required_sound() -> void:
	var lib := SfxLib.build()
	check(lib.size() >= REQUIRED.size(),
		"build() doit produire au moins %d sons (obtenu %d)" % [REQUIRED.size(), lib.size()])

	for name in REQUIRED:
		check(lib.has(name), "son manquant : %s" % name)
		if not lib.has(name):
			continue
		var stream: Variant = lib[name]
		check(stream != null, "son nul : %s" % name)
		check(stream is AudioStreamWAV, "%s doit etre un AudioStreamWAV" % name)

	# Every material family must have a dig and a break sound, otherwise
	# Sfx.play_dig() builds a name that is not in the library.
	for family in FAMILIES:
		check(lib.has("dig_" + family), "famille sans son de creusage : %s" % family)
		check(lib.has("break_" + family), "famille sans son de casse : %s" % family)
	done()


func test_streams_use_the_declared_format() -> void:
	var lib := SfxLib.build()
	eq(SfxLib.MIX_RATE, 22050, "frequence d'echantillonnage du contrat")

	for name in REQUIRED:
		if not lib.has(name):
			fail("son manquant : %s" % name)
			continue
		var stream: AudioStreamWAV = lib[name]
		eq(stream.format, AudioStreamWAV.FORMAT_16_BITS, "%s doit etre en 16 bits" % name)
		eq(stream.mix_rate, SfxLib.MIX_RATE, "%s doit etre a MIX_RATE" % name)
		eq(stream.stereo, false, "%s doit etre mono" % name)
	done()


func test_buffers_have_a_plausible_length() -> void:
	var lib := SfxLib.build()
	for name in REQUIRED:
		if not lib.has(name):
			fail("son manquant : %s" % name)
			continue
		var stream: AudioStreamWAV = lib[name]
		var data := stream.data
		check(data.size() > 0, "%s a un tampon vide" % name)
		# 16 bit samples come in pairs, so an odd byte count means a truncated
		# sample and everything after it decodes shifted by one byte.
		eq(data.size() % 2, 0, "%s doit avoir un nombre pair d'octets" % name)
		var seconds := float(data.size() / 2) / float(SfxLib.MIX_RATE)
		between(seconds, MIN_SECONDS, MAX_SECONDS, "duree de %s en secondes" % name)
	done()


func test_every_sound_starts_and_ends_silent() -> void:
	var lib := SfxLib.build()
	for name in REQUIRED:
		if not lib.has(name):
			fail("son manquant : %s" % name)
			continue
		var stream: AudioStreamWAV = lib[name]
		var data := stream.data
		var count := data.size() / 2
		if count < EDGE_SAMPLES * 2:
			fail("%s est trop court pour porter une enveloppe (%d echantillons)" % [name, count])
			continue

		# A non-zero first or last sample is a step discontinuity, which the
		# speaker reproduces as an audible click on every playback.
		check(absf(_sample(data, 0)) <= EDGE_ZERO,
			"%s doit commencer sur le silence (obtenu %f)" % [name, _sample(data, 0)])
		check(absf(_sample(data, count - 1)) <= EDGE_ZERO,
			"%s doit finir sur le silence (obtenu %f)" % [name, _sample(data, count - 1)])

		for i in EDGE_SAMPLES:
			var head := absf(_sample(data, i))
			var tail := absf(_sample(data, count - 1 - i))
			check(head <= EDGE_NEAR,
				"attaque de %s trop brutale a l'echantillon %d (obtenu %f)" % [name, i, head])
			check(tail <= EDGE_NEAR,
				"relachement de %s trop brutal a %d avant la fin (obtenu %f)" % [name, i, tail])
	done()


func test_no_sound_clips_and_all_are_audible() -> void:
	var lib := SfxLib.build()
	for name in REQUIRED:
		if not lib.has(name):
			fail("son manquant : %s" % name)
			continue
		var stream: AudioStreamWAV = lib[name]
		var data := stream.data
		var count := data.size() / 2
		var peak := 0.0
		for i in count:
			var v := absf(_sample(data, i))
			if v > peak:
				peak = v
		# Too high wraps in the 16 bit conversion and rasps, too low is inaudible
		# once the spatial attenuation and Game.sfx_volume are applied.
		between(peak, MIN_PEAK, MAX_PEAK, "crete de %s" % name)
	done()


func test_material_family_covers_every_block() -> void:
	var sfx: Script = load(SFX_PLAYER_PATH)
	check(sfx != null, "le script de l'autoload Sfx doit se charger")
	if sfx == null:
		done()
		return

	for id in Blocks.COUNT:
		var family: String = sfx.material_family(id)
		check(not family.is_empty(), "famille vide pour le bloc %d (%s)" % [id, Blocks.display_name(id)])
		check(FAMILIES.has(family),
			"famille inconnue '%s' pour le bloc %d (%s)" % [family, id, Blocks.display_name(id)])
	done()


func test_material_family_spot_checks() -> void:
	var sfx: Script = load(SFX_PLAYER_PATH)
	check(sfx != null, "le script de l'autoload Sfx doit se charger")
	if sfx == null:
		done()
		return

	# Ores are embedded in rock, so they must sound like rock and not like their
	# metal, which is the classic mistake here.
	eq(sfx.material_family(Blocks.COAL_ORE), "stone", "le charbon sonne comme la pierre")
	eq(sfx.material_family(Blocks.IRON_ORE), "stone", "le fer sonne comme la pierre")
	eq(sfx.material_family(Blocks.DIAMOND_ORE), "stone", "le diamant sonne comme la pierre")
	eq(sfx.material_family(Blocks.OAK_PLANKS), "wood", "les planches de chene sonnent comme le bois")
	eq(sfx.material_family(Blocks.BIRCH_PLANKS), "wood", "les planches de bouleau sonnent comme le bois")
	# Ice has no family of its own, and glass is the nearest brittle surface.
	eq(sfx.material_family(Blocks.ICE), "glass", "la glace sonne comme le verre")
	eq(sfx.material_family(Blocks.GLASS), "glass", "le verre sonne comme le verre")
	eq(sfx.material_family(Blocks.GRASS), "grass", "l'herbe sonne comme l'herbe")
	eq(sfx.material_family(Blocks.DIRT), "dirt", "la terre sonne comme la terre")
	eq(sfx.material_family(Blocks.SAND), "sand", "le sable sonne comme le sable")
	eq(sfx.material_family(Blocks.WOOL_RED), "wool", "la laine sonne comme la laine")
	eq(sfx.material_family(Blocks.FLOWER_RED), "plant", "une fleur sonne comme une plante")
	eq(sfx.material_family(Blocks.OAK_LEAVES), "plant", "le feuillage sonne comme une plante")
	done()
