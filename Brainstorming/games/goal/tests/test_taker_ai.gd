extends GoalTest
## Suite for TakerAi (contract 2.12b).
##
## Two very different jobs live in this file.
##
## THE FIRST IS A NON REGRESSION GUARD, and it is the important one. The penalty
## choice this module carries was MOVED out of src/core/match_state.gd, and the
## four measured rows of contract 2.9 are a property of the exact order in which
## that code drew its random numbers. FROZEN_PLANS below pins the plan of five
## known seeds, calm and under pressure, plus the value the SEANCE path draws
## immediately afterwards for the keeper's line dance. If those numbers move, the
## tables of 2.9 are wrong and have to be REMEASURED (4000 kicks per level, the
## procedure is written there), not patched. They were produced by running the
## shipped _rival_plan and this module side by side over 3000 seeds: the worst
## absolute difference over aim, power, release and the dance draw was exactly 0.
##
## THE SECOND IS THE FAIRNESS OF THE DUEL. The player keeper reads this taker, so
## the suite proves the tells are genuinely LOSSY rather than merely noisy: a
## perfect reader must not be able to recover the aim, the same body language must
## be able to precede two opposite kicks, and the cues have to arrive one at a time
## through the run up so that waiting is worth something and yet never worth
## enough. It also proves the taker is deterministic per seed and varied across
## seeds, that his placements look like real penalties (aimed at corners, missing
## towards the middle), and that shading his aim away from a keeper who has left
## his post moves an INTENTION rather than hunting the far corner.

## [seed, pressure, aim, power, release, dance draw]. See the class comment before
## touching a single digit of this table.
const FROZEN_PLANS: Array = [
	[1, false, Vector2(0.26677858829498291, 0.44249656796455383),
		0.79059159755706787, 0.97248447060585019, 0.90736194849014273],
	[1, true, Vector2(0.26142477989196777, 0.58272302150726318),
		0.79059159755706787, 0.97248447060585019, 0.90736194849014273],
	[2, false, Vector2(-0.77249711751937866, 0.35424315929412842),
		0.54566299915313721, 0.71999999999999997, 0.31661270447075368],
	[2, true, Vector2(-0.93181818723678589, 0.14780607819557190),
		0.54566299915313721, 0.71999999999999997, 0.31661270447075368],
	[12345, false, Vector2(-0.47282615303993225, 0.26797965168952942),
		0.79212439060211182, 0.71999999999999997, 0.82393009066581713],
	[12345, true, Vector2(-0.45859694480895996, 0.32178932428359985),
		0.79212439060211182, 0.71999999999999997, 0.82393009066581713],
	[987654321, false, Vector2(0.14434814453125000, 0.79833072423934937),
		0.77381968498229980, 0.71999999999999997, 0.82657872438430791],
	[987654321, true, Vector2(0.32539784908294678, 0.95221841335296631),
		0.77381968498229980, 0.71999999999999997, 0.82657872438430791],
	[-55, false, Vector2(0.10990320891141891, 0.42065459489822388),
		1.00000000000000000, 0.71999999999999997, 0.69271167516708365],
	[-55, true, Vector2(0.18836157023906708, 0.57194000482559204),
		1.00000000000000000, 0.71999999999999997, 0.69271167516708365],
]

const LEVELS: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]
## Sample size of the statistical cases. Big enough for the claims made on them,
## small enough that the whole suite stays under a second.
const SAMPLE := 1500
## Slack allowed when a value that lives in a Vector3 is compared against a
## project constant: a Vector3 holds float32, so a coordinate clamped to exactly
## 2.90 reads back as 2.9000000953674316.
const PACK := 1.0e-5


func suite_name() -> String:
	return "TakerAi"


func _seed(salt: int, index: int) -> int:
	return hash(Vector2i(salt, index))


func test_seance_plans_are_frozen() -> void:
	# The non regression guard. See the class comment.
	for entry in FROZEN_PLANS:
		var row: Array = entry
		var rng_seed: int = row[0]
		var pressure: bool = row[1]
		var expected_aim: Vector2 = row[2]
		var plan: Dictionary = TakerAi.choose(
			rng_seed, TakerAi.SEANCE_LEVEL, pressure, 0.0)
		var aim: Vector2 = plan["aim"]
		near(aim.x, expected_aim.x, 1.0e-9,
			"le plan SEANCE de la graine %d a bouge en x" % rng_seed)
		near(aim.y, expected_aim.y, 1.0e-9,
			"le plan SEANCE de la graine %d a bouge en y" % rng_seed)
		near(float(plan["power"]), float(row[3]), 1.0e-9,
			"la puissance de la graine %d a bouge" % rng_seed)
		near(float(plan["release"]), float(row[4]), 1.0e-9,
			"le relachement de la graine %d a bouge" % rng_seed)
		near(TakerAi.dance_phase(rng_seed, TakerAi.SEANCE_LEVEL, pressure), float(row[5]),
			1.0e-9, "le tirage de la danse de la graine %d a bouge" % rng_seed)

	# The two properties that DEFINE the SEANCE rung, and without which the freeze
	# above would only be an accident of these five seeds.
	near(TakerAi.spread(TakerAi.SEANCE_LEVEL), 1.0, 1.0e-12,
		"spread doit valoir exactement 1 au barreau de la SEANCE")
	for i in 200:
		eq(TakerAi.feint_count(TakerAi.SEANCE_LEVEL, _seed(4711, i)), 0,
			"le tireur de la SEANCE ne feinte jamais")
	done()


func test_the_reticle_inverts_shot_model() -> void:
	# The module aims in metres and hands ShotModel a normalized reticle, so the
	# two mappings have to be exact inverses. If ShotModel ever remaps its reticle
	# this check fails instead of the taker quietly aiming somewhere else.
	for i in 13:
		var x: float = lerpf(-TakerAi.MAX_X, TakerAi.MAX_X, float(i) / 12.0)
		for j in 9:
			var y: float = lerpf(TakerAi.MIN_Y, TakerAi.MAX_Y, float(j) / 8.0)
			var back: Vector3 = ShotModel.aim_point(TakerAi.reticle(x, y))
			near(back.x, x, 1.0e-6, "le reticule doit rendre exactement le x vise")
			near(back.y, y, 1.0e-6, "le reticule doit rendre exactement le y vise")

	# And the published target is the world point of the published aim, so callers
	# stop recomputing it and cannot disagree with the module about it.
	for i in 40:
		var s := _seed(60613, i)
		var plan: Dictionary = TakerAi.choose(s, i % 4, false, 0.0)
		var from_aim: Vector3 = ShotModel.aim_point(plan["aim"])
		var published: Vector3 = plan["target"]
		near(published.x, from_aim.x, 1.0e-6, "target doit etre le point monde de aim")
		near(published.y, from_aim.y, 1.0e-6, "target doit etre le point monde de aim")
	done()


func test_a_plan_is_deterministic_and_varied() -> void:
	var identical := 0
	var distinct := {}
	for i in 400:
		var s := _seed(777, i)
		var a: Dictionary = TakerAi.choose(s, 2, false, 0.35)
		var b: Dictionary = TakerAi.choose(s, 2, false, 0.35)
		if a["aim"] == b["aim"] and a["power"] == b["power"] and a["release"] == b["release"]:
			identical += 1
		distinct[Vector2(snappedf(a["aim"].x, 0.0001), snappedf(a["aim"].y, 0.0001))] = true
	eq(identical, 400, "la meme graine doit rendre exactement le meme penalty")
	check(distinct.size() > 380, "des graines differentes doivent tirer differemment")

	# Nothing static leaks between two kicks: interleaving two seeds must not
	# change either of them.
	var alone: Dictionary = TakerAi.choose(999, 3, true, -0.5)
	var _noise: Dictionary = TakerAi.choose(1000, 0, false, 0.9)
	var again: Dictionary = TakerAi.choose(999, 3, true, -0.5)
	eq(again["aim"], alone["aim"], "aucun etat statique ne doit survivre entre deux tirs")
	done()


func test_placements_look_like_real_penalties() -> void:
	var left := 0
	var right := 0
	var framed := 0
	var corners := 0
	var middle := 0
	for i in SAMPLE:
		var s := _seed(4242, i)
		var plan: Dictionary = TakerAi.choose(s, TakerAi.SEANCE_LEVEL, false, 0.0)
		var target: Vector3 = plan["target"]
		# PACK, not slack: a Vector3 holds float32, so a coordinate clamped to
		# exactly MAX_Y comes back as 2.9000000953674316 and a bare bound would
		# fail on a value that is correct.
		between(target.x, -TakerAi.MAX_X - PACK, TakerAi.MAX_X + PACK,
			"la visee reste dans sa bande en x")
		between(target.y, TakerAi.MIN_Y - PACK, TakerAi.MAX_Y + PACK,
			"la visee reste dans sa bande en y")
		if target.x < 0.0:
			left += 1
		else:
			right += 1
		if absf(target.x) < Field.GOAL_HALF and target.y < Field.GOAL_HEIGHT:
			framed += 1
		if absf(target.x) > 2.60 and target.y > 1.60:
			corners += 1
		if absf(target.x) < 0.90:
			middle += 1
	# Neither post is favoured: the sign of x is a fair coin.
	var bias := absf(float(left - right)) / float(SAMPLE)
	# Three sigma of a fair coin over this sample, so a real bias fails and the
	# fixed seeds are not being asked to land on a knife edge.
	check(bias < 0.08, "aucun poteau ne doit etre favorise (biais %.3f)" % bias)
	# Real takers aim at the frame and miss towards the middle, they do not spray.
	check(float(framed) / float(SAMPLE) > 0.93,
		"la grande majorite des penalties doit viser dans le cadre")
	# Genuine top corners exist but are the minority: that is what makes them
	# worth something when they arrive.
	between(float(corners) / float(SAMPLE), 0.04, 0.30,
		"les lucarnes doivent etre une minorite reelle")
	between(float(middle) / float(SAMPLE), 0.10, 0.45,
		"et le milieu doit rester une vraie option")
	done()


func test_pressure_spreads_the_aim_and_wrecks_the_contact() -> void:
	var wide := [0, 0]
	var miscued := [0, 0]
	for k in 2:
		var pressure := k == 1
		for i in SAMPLE:
			var s := _seed(2024, i)
			var plan: Dictionary = TakerAi.choose(s, TakerAi.SEANCE_LEVEL, pressure, 0.0)
			if absf(float(plan["target"].x)) > Field.GOAL_HALF:
				wide[k] += 1
			if absf(float(plan["release"]) - TakerAi.SWEET_CENTRE) > 0.001:
				miscued[k] += 1
	check(wide[1] > wide[0] * 3,
		"un tir a ne pas manquer doit partir bien plus souvent a cote")
	check(miscued[1] > miscued[0] * 2,
		"et etre mistime bien plus souvent")
	# The nerves are a live branch, not decoration: they have to fire hard enough
	# to be visible and not so hard that the taker stops being a footballer.
	between(float(miscued[1]) / float(SAMPLE), 0.20, 0.40,
		"la proportion de frappes ratees sous pression doit rester credible")
	between(float(wide[1]) / float(SAMPLE), 0.01, 0.20,
		"et il ne doit pas expedier tous ses penalties en tribune")
	done()


func test_the_ladder_places_better_at_the_top() -> void:
	var previous_spread := 99.0
	var previous_leak := 99.0
	for level in 4:
		var s: float = TakerAi.spread(level)
		var l: float = TakerAi.leak(level)
		between(s, 0.3, 2.0, "la dispersion doit rester credible")
		between(l, 0.0, 1.0, "la fuite est une fraction")
		check(s < previous_spread, "un tireur plus fort place mieux (%s)" % LEVELS[level])
		check(l < previous_leak, "un tireur plus fort montre moins (%s)" % LEVELS[level])
		previous_spread = s
		previous_leak = l

	# The ladder has to be visible in the kicks, not only in the tables.
	var missed := [0, 0, 0, 0]
	for level in 4:
		for i in SAMPLE:
			var s := _seed(60613, i)
			var plan: Dictionary = TakerAi.choose(s, level, false, 0.0)
			if absf(float(plan["target"].x)) > 3.30:
				missed[level] += 1
	check(missed[0] > missed[3] * 2,
		"un Debutant doit rater le cadre bien plus souvent qu'une Legende")

	# And a strong taker feints while the bottom of the ladder does not.
	var feinted := [0, 0, 0, 0]
	for level in 4:
		for i in 400:
			if TakerAi.feint_count(level, _seed(11, i)) > 0:
				feinted[level] += 1
		check(TakerAi.feint_count(level, _seed(11, 7)) <= 2, "au plus deux feintes")
	eq(feinted[0], 0, "un Debutant n'a pas le pas de feinte")
	check(feinted[3] > feinted[2], "une Legende feinte plus qu'un Pro")

	# A longer run up at the bottom: an amateur telegraphs by dawdling.
	check(TakerAi.run_up_time(0, 5) > TakerAi.run_up_time(3, 5),
		"la course d'elan doit raccourcir quand le niveau monte")
	for level in 4:
		for i in 60:
			between(TakerAi.run_up_time(level, _seed(31, i)), 0.55, 2.2,
				"la course d'elan doit rester dans des secondes credibles")
	done()


func test_the_tells_are_genuinely_lossy() -> void:
	# Fairness rule 1: the player must never be handed the truth. Measured as three
	# separate claims, because "it is noisy" is not one of them.
	var wrong_side := [0, 0, 0, 0]
	var error := [0.0, 0.0, 0.0, 0.0]
	for level in 4:
		for i in 500:
			var s := _seed(999331, i)
			var plan: Dictionary = TakerAi.choose(s, level, false, 0.0)
			var read: Dictionary = TakerAi.tells(plan, level, s)
			var truth: float = plan["aim"].x
			var hint: float = read["aim_hint"]
			check(is_finite(hint), "un indice ne doit jamais etre NaN")
			between(hint, -1.0, 1.0, "l'indice de visee reste dans sa bande")
			if signf(truth) != signf(hint):
				wrong_side[level] += 1
			error[level] += absf(truth - hint)
	# 1. A perfect reader taking the hint at face value is wrong about the SIDE of
	# the goal on a large fraction of Legende penalties.
	check(float(wrong_side[3]) / 500.0 > 0.30,
		"contre une Legende, l'indice doit se tromper de cote tres souvent")
	# 2. And the residual error is worth more than a glove: 0.30 of reticle is
	# 1.3 m of goal, four glove widths.
	check(error[3] / 500.0 > 0.30,
		"l'erreur residuelle doit valoir plus qu'un gant")
	# 3. The ladder is real: the weak taker is readable, the strong one is not.
	check(wrong_side[0] < wrong_side[3], "un Debutant doit etre bien plus lisible")
	check(error[0] < error[3], "et son indice bien plus proche de la verite")

	# The same body language must be able to precede two OPPOSITE kicks, which is
	# the property that makes the mode a gamble rather than a lookup.
	var hints: Array = []
	for i in 250:
		var s := _seed(31337, i)
		var plan: Dictionary = TakerAi.choose(s, 3, false, 0.0)
		hints.append([float(plan["aim"].x), float(TakerAi.tells(plan, 3, s)["aim_hint"])])
	var opposite := 0
	var collisions := 0
	for i in hints.size():
		for j in range(i + 1, hints.size()):
			var a: Array = hints[i]
			var b: Array = hints[j]
			if signf(a[0]) == signf(b[0]):
				continue
			opposite += 1
			if absf(a[1] - b[1]) < 0.08:
				collisions += 1
	check(opposite > 0, "l'echantillon doit contenir des tirs opposes")
	check(float(collisions) / float(opposite) > 0.02,
		"un meme indice doit pouvoir preceder deux tirs opposes")
	done()


func test_the_tells_arrive_through_the_run_up() -> void:
	var plan: Dictionary = TakerAi.choose(4242, 2, false, 0.0)
	var run_up: float = TakerAi.run_up_time(2, 4242)

	# Before he moves, nothing is known. Not a degraded read: nothing.
	var blind: Dictionary = TakerAi.tells_at(plan, 2, 4242, -run_up - 1.0)
	near(float(blind["confidence"]), 0.0, 1.0e-12, "avant la course on ne sait rien")
	for key in ["aim_hint", "lift_hint", "run_angle", "plant_offset", "hip_yaw",
			"approach_speed"]:
		near(float(blind[key]), 0.0, 1.0e-12,
			"l'indice %s doit etre neutre avant la course" % key)

	# At contact it IS the full read, key for key: the progressive version may not
	# invent anything the complete one does not say.
	var full: Dictionary = TakerAi.tells(plan, 2, 4242)
	var at_strike: Dictionary = TakerAi.tells_at(plan, 2, 4242, 0.0)
	for key in full:
		check(at_strike.has(key), "tells_at doit rendre la cle %s" % key)
		if key == "feints":
			eq(int(at_strike[key]), int(full[key]), "les feintes doivent concorder")
		else:
			near(float(at_strike[key]), float(full[key]), 1.0e-9,
				"a la frappe, %s doit valoir la lecture complete" % key)
	var late: Dictionary = TakerAi.tells_at(plan, 2, 4242, 0.35)
	near(float(late["aim_hint"]), float(full["aim_hint"]), 1.0e-9,
		"apres la frappe la lecture ne bouge plus")

	# Confidence only ever grows, and the aim arrives AFTER the pace: a keeper who
	# waits for the aim has almost no run up left to leave in.
	var previous := -1.0
	var pace_at := 2.0
	var aim_at := 2.0
	for i in 120:
		var progress: float = float(i) / 119.0
		var t: float = -run_up * (1.0 - progress)
		var read: Dictionary = TakerAi.tells_at(plan, 2, 4242, t)
		var c: float = float(read["confidence"])
		check(c >= previous - 1.0e-9, "la confiance ne doit jamais redescendre")
		previous = c
		if pace_at > 1.5 and absf(float(read["approach_speed"])) > 0.05:
			pace_at = progress
		if aim_at > 1.5 and absf(float(read["aim_hint"])) > 0.05 * absf(float(full["aim_hint"])):
			aim_at = progress
	check(pace_at < aim_at, "l'allure doit se voir avant la visee")
	check(aim_at > 0.60, "la visee ne doit fuir qu'a la toute fin de la course")
	between(float(full["confidence"]), 0.0, 1.0, "la confiance est une fraction")
	done()


func test_read_keeper_shades_away_and_rattles() -> void:
	for level in 4:
		var still: Dictionary = TakerAi.read_keeper(0.0, level, 7)
		near(float(still["shift"]), 0.0, 1.0e-12,
			"un gardien au milieu ne doit rien changer")
		near(float(still["rattle"]), 0.0, 1.0e-12,
			"et ne doit deranger personne")

		var plus: Dictionary = TakerAi.read_keeper(0.9, level, 7)
		var minus: Dictionary = TakerAi.read_keeper(-0.9, level, 7)
		check(float(plus["shift"]) <= 0.0, "on vise a l'oppose du gardien")
		check(float(minus["shift"]) >= 0.0, "et symetriquement")
		near(float(plus["shift"]), -float(minus["shift"]), 1.0e-9,
			"la lecture du gardien doit etre symetrique")
		check(absf(float(plus["shift"])) <= TakerAi.MAX_SHIFT,
			"le decalage est borne (fairness 3)")
		between(float(plus["rattle"]), 0.0, 1.0, "l'enervement est une fraction")

	# The trade that makes the line dance interesting: the weak taker is rattled
	# and does not shade, the strong one shades and is not rattled.
	var weak: Dictionary = TakerAi.read_keeper(0.9, 0, 7)
	var strong: Dictionary = TakerAi.read_keeper(0.9, 3, 7)
	near(float(weak["shift"]), 0.0, 1.0e-9, "un Debutant ne sait pas replacer sa visee")
	check(float(weak["rattle"]) > 0.2, "mais il se laisse deranger")
	check(absf(float(strong["shift"])) > 0.25, "une Legende replace sa visee")
	near(float(strong["rattle"]), 0.0, 1.0e-9, "et ne se laisse pas deranger")

	# Half the shuffle buys half the answer: it is a gradient, not a switch.
	var half: Dictionary = TakerAi.read_keeper(0.45, 3, 7)
	check(absf(float(half["shift"])) < absf(float(strong["shift"])),
		"un pas de cote doit peser moins qu'un pas complet")
	done()


func test_the_taker_moves_an_intention_not_a_corner() -> void:
	# Fairness rule 3: shading must not turn the line dance into a punishment.
	var moved := 0.0
	var far_corner := 0
	var closer := 0
	for i in SAMPLE:
		var s := _seed(31, i)
		var centred: Dictionary = TakerAi.choose(s, 3, false, 0.0)
		var shaded: Dictionary = TakerAi.choose(s, 3, false, 0.9)
		var a: float = centred["target"].x
		var b: float = shaded["target"].x
		moved += absf(b - a)
		check(absf(b - a) <= TakerAi.MAX_SHIFT + 1.0e-6,
			"le decalage ne doit jamais depasser MAX_SHIFT")
		if b < -2.5:
			far_corner += 1
		if b > a:
			closer += 1
	var mean := moved / float(SAMPLE)
	between(mean, 0.05, 0.55, "le decalage moyen doit rester petit devant le but")
	check(float(far_corner) / float(SAMPLE) < 0.40,
		"le tireur ne doit pas viser systematiquement le coin oppose")
	check(closer < SAMPLE / 4,
		"et il ne doit surtout pas viser vers le gardien")

	# Against a Debutant the dance buys the other half of the trade: no shading at
	# all, but a taker who mistimes the strike far more often. That has to be a
	# MEASURABLE consequence, otherwise the shuffle is decoration at the bottom of
	# the ladder.
	var calm_miscues := 0
	var danced_miscues := 0
	for i in SAMPLE:
		var s := _seed(1234, i)
		var flat: Dictionary = TakerAi.choose(s, 0, false, 0.9)
		var base: Dictionary = TakerAi.choose(s, 0, false, 0.0)
		near(float(flat["shift"]), 0.0, 1.0e-12, "un Debutant ne replace jamais sa visee")
		check(float(flat["rattle"]) > 0.0, "mais il paie l'enervement")
		if absf(float(base["release"]) - TakerAi.SWEET_CENTRE) > 0.001:
			calm_miscues += 1
		if absf(float(flat["release"]) - TakerAi.SWEET_CENTRE) > 0.001:
			danced_miscues += 1
	check(danced_miscues > calm_miscues + SAMPLE / 20,
		"danser sur sa ligne doit vraiment deranger un tireur faible")
	done()


func test_cues_and_strike_stay_shot_models_own() -> void:
	# The AI keeper's read must be BYTE for byte what SEANCE has always asked for,
	# or the tables of 2.9 move without anybody touching a kick.
	for i in 60:
		var s := _seed(8080, i)
		var plan: Dictionary = TakerAi.choose(s, TakerAi.SEANCE_LEVEL, i % 2 == 0, 0.0)
		for keeper_level in 4:
			var mine: Dictionary = TakerAi.cues(plan, keeper_level)
			var theirs: Dictionary = ShotModel.tell_cues(
				plan["aim"], float(plan["power"]), float(plan["side"]), 0.0, 0, keeper_level)
			# Key by key rather than dictionary against dictionary: Godot compares
			# two Dictionaries by REFERENCE, so `==` between these two would be
			# false however identical their contents, and the check would be a
			# guaranteed failure rather than a guard.
			eq(mine.keys().size(), theirs.keys().size(),
				"cues doit rendre les memes cles que ShotModel.tell_cues")
			for key in theirs:
				check(mine.has(key), "cues doit rendre la cle %s" % key)
				if key == "feints":
					eq(int(mine[key]), int(theirs[key]),
						"cues doit rendre les memes feintes que ShotModel")
				else:
					eq(float(mine[key]), float(theirs[key]),
						"cues doit etre exactement ShotModel.tell_cues (%s)" % key)

		# And the strike is ShotModel.resolve, unchanged, so a CPU penalty and a
		# player penalty are the same object everywhere downstream.
		var shot: Dictionary = TakerAi.strike(plan, s)
		var expected: Dictionary = ShotModel.resolve(
			plan["aim"], float(plan["power"]), float(plan["side"]), float(plan["lift"]),
			float(plan["release"]), float(plan["sweet_centre"]), s)
		eq(shot["velocity"], expected["velocity"], "strike doit etre ShotModel.resolve")
		eq(shot["spin"], expected["spin"], "l'effet aussi")
		var velocity: Vector3 = shot["velocity"]
		check(velocity.is_finite(), "un penalty ne doit jamais partir en NaN")
		check(velocity.length() > 5.0, "ni a l'arret")
		check(velocity.z < 0.0, "un penalty part vers le but")
	done()


func test_nothing_produces_a_nan() -> void:
	var junk: Array = [NAN, INF, -INF, 1.0e30, -1.0e30]
	for bad in junk:
		var v: float = bad
		var answer: Dictionary = TakerAi.read_keeper(v, 2, 3)
		check(is_finite(float(answer["shift"])) and is_finite(float(answer["rattle"])),
			"read_keeper doit rester fini sur des entrees folles")
		var plan: Dictionary = TakerAi.choose(17, 2, false, v)
		var target: Vector3 = plan["target"]
		check(target.is_finite(), "un plan doit rester fini sur des entrees folles")
		var read: Dictionary = TakerAi.tells_at(plan, 2, 17, v)
		for key in read:
			if key == "feints":
				continue
			check(is_finite(float(read[key])),
				"la cle %s des indices doit rester finie" % key)
		var r: Vector2 = TakerAi.reticle(v, v)
		check(is_finite(r.x) and is_finite(r.y), "reticle doit rester fini")

	# A broken plan dictionary must degrade, not crash: the orchestrator hands this
	# whatever a replay or a save file produced.
	var empty: Dictionary = TakerAi.tells({}, 2, 5)
	check(is_finite(float(empty["aim_hint"])), "un plan vide doit rendre des indices finis")
	var junk_plan: Dictionary = TakerAi.tells({"aim": Vector2(NAN, NAN), "power": NAN}, 3, 5)
	check(is_finite(float(junk_plan["aim_hint"])), "un plan fou doit rendre des indices finis")
	var shot: Dictionary = TakerAi.strike({}, 5)
	var velocity: Vector3 = shot["velocity"]
	check(velocity.is_finite(), "un plan vide doit quand meme partir quelque part")

	# Out of range levels are clamped rather than propagated.
	for level in [-9, 4, 99]:
		var plan: Dictionary = TakerAi.choose(21, level, false, 0.0)
		between(int(plan["level"]), 0, 3, "un niveau hors bornes doit etre ramene")
		check(float(plan["power"]) > 0.0, "et le penalty doit rester jouable")
	done()
