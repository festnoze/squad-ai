extends WarTest
## Procedural sound bank. Every sample is synthesised at boot, so a bad one is
## either silence (nobody notices until the shot feels dead) or a burst of
## clipping that hurts.


func suite_name() -> String:
	return "sfx_lib"


func test_every_declared_name_actually_builds() -> void:
	for name in SfxLib.NAMES:
		var stream := SfxLib.build(name)
		check(stream != null, "l'echantillon '%s' ne se construit pas" % name)
		if stream == null:
			continue
		check(stream.data.size() > 0, "l'echantillon '%s' est vide" % name)
	done()


func test_an_unknown_name_returns_null_instead_of_crashing() -> void:
	var stream := SfxLib.build("ceci_n_existe_pas")
	check(stream == null, "un nom inconnu doit renvoyer null")
	done()


func test_build_all_covers_the_declared_names() -> void:
	var bank := SfxLib.build_all()
	check(not bank.is_empty(), "la banque de sons est vide")
	for name in SfxLib.NAMES:
		check(bank.has(name), "'%s' manque dans la banque" % name)
	done()


func test_names_are_unique() -> void:
	var seen := {}
	for name in SfxLib.NAMES:
		check(not seen.has(name), "le nom d'echantillon '%s' est duplique" % name)
		seen[name] = true
	done()


func test_samples_have_the_expected_format() -> void:
	for name in SfxLib.NAMES:
		var stream := SfxLib.build(name)
		if stream == null:
			continue
		eq(stream.format, AudioStreamWAV.FORMAT_16_BITS,
				"'%s' doit etre en 16 bits" % name)
		check(not stream.stereo, "'%s' doit etre mono" % name)
		check(stream.mix_rate > 8000, "'%s' a une frequence trop basse" % name)
		# Two bytes per frame, mono: an odd byte count means a truncated sample.
		eq(stream.data.size() % 2, 0, "'%s' a un nombre d'octets impair" % name)
	done()


func test_samples_are_short_enough_to_boot_fast() -> void:
	# 48 samples generated at startup: if each one lasts three seconds the game
	# spends its first second building audio nobody asked for yet.
	var total_seconds := 0.0
	for name in SfxLib.NAMES:
		var stream := SfxLib.build(name)
		if stream == null:
			continue
		var frames := stream.data.size() / 2
		var seconds := float(frames) / float(maxi(stream.mix_rate, 1))
		total_seconds += seconds
		between(seconds, 0.005, 6.0, "l'echantillon '%s' dure %f s" % [name, seconds])
	check(total_seconds < 40.0,
			"la banque totalise %f s d'audio, c'est trop pour un demarrage" % total_seconds)
	done()


func test_samples_are_normalised_and_not_clipped_flat() -> void:
	# A sample that saturates for most of its length is a square wave, which is
	# what a badly enveloped noise burst sounds like: painful.
	for name in SfxLib.NAMES:
		var stream := SfxLib.build(name)
		if stream == null:
			continue
		var data := stream.data
		var frames: int = data.size() / 2
		if frames < 8:
			continue
		var peak := 0
		var saturated := 0
		var step: int = maxi(1, frames / 400)
		var examined := 0
		var i := 0
		while i < frames:
			var lo: int = data[i * 2]
			var hi: int = data[i * 2 + 1]
			var value: int = lo | (hi << 8)
			if value >= 32768:
				value -= 65536
			var magnitude: int = absi(value)
			peak = maxi(peak, magnitude)
			if magnitude > 32000:
				saturated += 1
			examined += 1
			i += step
		check(peak > 1200, "l'echantillon '%s' est quasiment muet (crete %d)" % [name, peak])
		check(float(saturated) / float(maxi(examined, 1)) < 0.35,
				"l'echantillon '%s' sature sur une grande partie de sa duree" % name)
	done()


func test_the_names_the_rest_of_the_game_relies_on_are_present() -> void:
	# These keys are hard coded in the player, the AI and the mission code.
	var required := ["garand_ping", "dry_fire", "explosion", "hurt", "death",
			"german_alert", "german_death", "objective_done", "sector_captured",
			"ui_click", "bandage", "whizz"]
	for name in required:
		check(SfxLib.NAMES.has(name), "l'echantillon obligatoire '%s' manque" % name)
	done()


func test_a_footstep_exists_for_every_surface() -> void:
	for surface in ["grass", "dirt", "stone", "wood", "water"]:
		check(SfxLib.NAMES.has("step_%s" % surface),
				"pas de son de pas pour '%s'" % surface)
	done()
