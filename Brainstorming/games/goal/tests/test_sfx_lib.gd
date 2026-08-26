extends GoalTest
## Suite for SfxLib, the synthesised sound bank.
##
## Nothing here listens to anything, so the checks are all structural: they prove
## that every id produces a real, playable, non degenerate buffer, and that the
## two rules which cause the ugliest audio bugs in Godot are respected.
##
##   1. A stream that stops on a live sample clicks, so the last milliseconds of
##      every buffer must be far below its own peak.
##   2. A looping stream holds a voice forever, so exactly one id is allowed a
##      non zero loop_mode.
##
## A few checks also compare sounds against each other (a hard strike is louder
## than a placed one, a long whistle lasts longer than a short one, a goalpost
## rings while a boot does not). They are cheap, and they are the only automated
## guard against the whole bank collapsing into the same generic buzz.

const FULL_SCALE := 32767


func suite_name() -> String:
	return "SfxLib"


## Decoded mono samples of an id, in [-1, 1].
func _samples(id: String) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	var wav: AudioStreamWAV = SfxLib.stream(id)
	if wav == null:
		return out
	var data: PackedByteArray = wav.data
	var count := data.size() >> 1
	out.resize(count)
	for i in count:
		out[i] = float(data.decode_s16(i * 2)) / 32768.0
	return out


func _peak_of(samples: PackedFloat32Array) -> float:
	var top := 0.0
	for i in samples.size():
		top = maxf(top, absf(samples[i]))
	return top


## Root mean square over a frame range, the honest measure of "how loud is this
## part". A peak measure would be fooled by a single transient.
func _rms(samples: PackedFloat32Array, from_index: int, to_index: int) -> float:
	var a := maxi(0, from_index)
	var b := mini(samples.size(), to_index)
	if b <= a:
		return 0.0
	var acc := 0.0
	for i in range(a, b):
		acc += samples[i] * samples[i]
	return sqrt(acc / float(b - a))


func test_every_id_builds_a_sane_stream() -> void:
	eq(SfxLib.IDS.size(), 25, "la banque doit exposer 25 identifiants")

	var seen: Dictionary = {}
	for id in SfxLib.IDS:
		check(not seen.has(id), "identifiant duplique dans IDS : %s" % id)
		seen[id] = true

		var wav: AudioStreamWAV = SfxLib.stream(id)
		if wav == null:
			fail("stream() a rendu null pour %s" % id)
			continue
		eq(wav.mix_rate, 44100, "%s : frequence d'echantillonnage" % id)
		eq(wav.format, AudioStreamWAV.FORMAT_16_BITS, "%s : format 16 bits" % id)
		eq(wav.stereo, false, "%s : mono attendu" % id)
		check(wav.data.size() > 0, "%s : donnees vides" % id)
		eq(wav.data.size() % 2, 0, "%s : taille impaire pour du 16 bits" % id)
		between(wav.get_length(), 0.05, 12.0, "%s : duree plausible" % id)
	done()


func test_cache_returns_the_same_instance() -> void:
	var first: AudioStreamWAV = SfxLib.stream("net_ripple")
	var second: AudioStreamWAV = SfxLib.stream("net_ripple")
	check(first != null, "net_ripple doit exister")
	check(first == second, "deux appels doivent rendre la meme instance")

	SfxLib.clear_cache()
	var third: AudioStreamWAV = SfxLib.stream("net_ripple")
	check(third != null, "la banque doit se reconstruire apres clear_cache")
	check(third != first, "clear_cache doit avoir libere l'ancienne instance")
	eq(third.data.size(), first.data.size(), "la reconstruction doit etre deterministe")
	done()


func test_every_sample_ends_with_a_fade_out() -> void:
	var tail_frames := int(0.002 * 44100.0)
	for id in SfxLib.IDS:
		var samples := _samples(id)
		if samples.size() < tail_frames * 4:
			fail("%s : echantillon trop court pour etre analyse" % id)
			continue
		var peak := _peak_of(samples)
		var tail := _peak_of(samples.slice(samples.size() - tail_frames, samples.size()))
		check(peak > 0.0, "%s : echantillon totalement silencieux" % id)
		check(tail < peak * 0.5, "%s : la fin n'est pas amortie (fin %f, crete %f)" % [id, tail, peak])
		check(absf(samples[samples.size() - 1]) < 0.02, "%s : dernier echantillon non nul" % id)
	done()


func test_no_sample_clips_to_full_scale() -> void:
	for id in SfxLib.IDS:
		var wav: AudioStreamWAV = SfxLib.stream(id)
		if wav == null:
			fail("stream() a rendu null pour %s" % id)
			continue
		var data: PackedByteArray = wav.data
		var count := data.size() >> 1
		var worst := 0
		for i in count:
			worst = maxi(worst, absi(data.decode_s16(i * 2)))
		check(worst < FULL_SCALE, "%s : sature a pleine echelle (%d)" % [id, worst])
		check(worst > 1600, "%s : niveau trop faible pour etre audible (%d)" % [id, worst])
	done()


func test_only_the_ambience_loops() -> void:
	var looping: PackedStringArray = PackedStringArray()
	for id in SfxLib.IDS:
		var wav: AudioStreamWAV = SfxLib.stream(id)
		if wav != null and wav.loop_mode != AudioStreamWAV.LOOP_DISABLED:
			looping.append(id)
	eq(looping.size(), 1, "un seul son a le droit de boucler")
	if looping.size() == 1:
		eq(looping[0], "crowd_ambience", "seule l'ambiance de foule boucle")

	var amb: AudioStreamWAV = SfxLib.stream("crowd_ambience")
	var frames := amb.data.size() >> 1
	between(float(amb.loop_end), 1.0, float(frames), "loop_end doit tenir dans les donnees")
	check(amb.loop_begin < amb.loop_end, "loop_begin doit preceder loop_end")
	check(frames > amb.loop_end, "une queue non bouclee doit suivre loop_end")

	# The loop point must sit on a zero crossing, otherwise the mixer jumps a
	# step every six seconds and the bed ticks.
	var samples := _samples("crowd_ambience")
	check(absf(samples[amb.loop_begin]) < 0.05, "loop_begin doit tomber sur un passage par zero")
	check(absf(samples[amb.loop_end - 1]) < 0.35, "la fin de boucle doit rester proche de zero")
	done()


func test_unknown_id_returns_null() -> void:
	check(SfxLib.stream("ballon_qui_parle") == null, "un identifiant inconnu doit rendre null")
	check(SfxLib.stream("") == null, "un identifiant vide doit rendre null")
	check(SfxLib.stream("kick_hard") != null, "un identifiant connu doit rendre un flux")
	done()


func test_sounds_differ_from_each_other() -> void:
	var soft := _samples("kick_soft")
	var hard := _samples("kick_hard")
	check(_peak_of(hard) > _peak_of(soft), "la frappe puissante doit etre plus forte que la placee")
	check(hard.size() < soft.size(), "la frappe puissante doit etre plus breve")

	var short_blast: AudioStreamWAV = SfxLib.stream("whistle_short")
	var long_blast: AudioStreamWAV = SfxLib.stream("whistle_long")
	check(long_blast.get_length() > short_blast.get_length() * 2.0, "le coup de sifflet long doit durer plus longtemps")

	var amb: AudioStreamWAV = SfxLib.stream("crowd_ambience")
	for id in SfxLib.IDS:
		if id == "crowd_ambience":
			continue
		var other: AudioStreamWAV = SfxLib.stream(id)
		check(amb.get_length() > other.get_length(), "l'ambiance doit etre le plus long des sons (%s)" % id)

	# Two different ids must not be the same bytes: a copy paste in the bank
	# would otherwise pass every other check in this suite.
	var ripple: AudioStreamWAV = SfxLib.stream("net_ripple")
	var post: AudioStreamWAV = SfxLib.stream("post_ding")
	check(ripple.data != post.data, "deux sons distincts ne doivent pas partager leurs donnees")
	done()


func test_envelopes_have_the_right_shape() -> void:
	# A strike is percussive: almost all of its energy is in the first tenth.
	var hard := _samples("kick_hard")
	var head := _rms(hard, 0, hard.size() / 10)
	var tail := _rms(hard, hard.size() * 9 / 10, hard.size())
	check(head > tail * 4.0, "kick_hard doit etre percussif (tete %f, queue %f)" % [head, tail])

	# A goalpost rings on long after the impact, a boot does not.
	var ding := _samples("post_ding")
	var ding_tail := _rms(ding, ding.size() * 2 / 3, ding.size() * 9 / 10)
	check(ding_tail > _peak_of(ding) * 0.01, "post_ding doit continuer a resonner")
	check(ding_tail > tail, "le poteau doit resonner plus longtemps que la frappe")

	# The roar swells: the crowd needs a moment to react.
	var roar := _samples("crowd_roar")
	var roar_start := _rms(roar, 0, roar.size() / 20)
	var roar_middle := _rms(roar, roar.size() * 2 / 5, roar.size() / 2)
	check(roar_start < roar_middle * 0.6, "crowd_roar doit monter en puissance")

	# The groan does the opposite: it lands at once and falls away.
	var groan := _samples("crowd_groan")
	var groan_start := _rms(groan, groan.size() / 20, groan.size() / 8)
	var groan_end := _rms(groan, groan.size() * 4 / 5, groan.size())
	check(groan_start > groan_end, "crowd_groan doit retomber")
	done()
