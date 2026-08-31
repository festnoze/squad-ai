extends GoalTest
## Suite for KeeperInput (contract 2.12a).
##
## The module carries the whole feel of the DUEL keeper, so the suite proves the
## PROPERTIES the mode is built on rather than a handful of magic numbers:
##
##   - the reach envelope only ever shrinks, at every level and from every
##     position on the line, because a circle that grew back between two frames
##     would destroy the only information the player has time to read;
##   - it NEVER covers the whole goal, at any instant of the legal band, so a well
##     struck top corner stays a goal and the player's wins come from reading and
##     gambling rather than from covering everything;
##   - a late commit cannot reach a corner, which is the arithmetic the whole mode
##     exists to make the player feel;
##   - the drawn ring IS the rule: every point of it is reachable and a step
##     further out along the same ray is not;
##   - and the two halves of a duel aim in one language, checked by round tripping
##     the reticle against ShotModel and the coarse reading against
##     KeeperBrain.choose_dive itself, so a drift in either of those files fails
##     HERE instead of quietly desynchronising the two keepers.
##
## Reference measurements taken while writing it, at arrival = NOMINAL_FLIGHT and
## from the middle of the line, so the next reader knows what the gradient looks
## like rather than only that it exists:
##
##   t          -0.42   -0.20    0.00    0.10    0.21    0.23
##   Confirme    0.918   0.871   0.684   0.462   0.357   0.000
##   Legende     0.965   0.918   0.778   0.474   0.368   0.000
##
## The cliff at 0.23 s is not a bug and it is not an invention: the arm swing of
## KeeperBrain.dive_time_needed costs about 0.19 s even for a ball hanging in
## front of the chest, so a keeper who has not left by then cannot save anything,
## and the AI keeper lives under exactly the same deadline.

## Level names are only here to make a failure readable.
const LEVELS: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]
## Positions on the line the sweeps are repeated from.
const LINES: PackedFloat64Array = [-0.9, -0.45, 0.0, 0.45, 0.9]
## The two TOP corners, well inside the frame so they are real goals and not shots
## off the woodwork. Deliberately not the bottom ones: a ball along the turf is a
## genuinely easier save (KeeperBrain's travel scale is 1.06 down there against
## 0.42 up under the bar) and asserting that a low corner is unreachable would be
## asserting something false about the game.
const CORNERS: Array = [
	Vector3(3.40, 2.25, 0.0),
	Vector3(-3.40, 2.25, 0.0),
]


func suite_name() -> String:
	return "KeeperInput"


func test_dive_target_speaks_the_takers_reticle() -> void:
	# Inside the frame the two ends of a duel must map a reticle to the SAME point,
	# otherwise the taker and the keeper are aiming in two languages.
	for i in 9:
		var ax: float = lerpf(-0.7, 0.7, float(i) / 8.0)
		for j in 5:
			var ay: float = lerpf(0.1, 0.7, float(j) / 4.0)
			var mine: Vector3 = KeeperInput.dive_target(Vector2(ax, ay))
			var theirs: Vector3 = ShotModel.aim_point(Vector2(ax, ay))
			near_vec(mine, theirs, 1.0e-6,
				"la cible de plongeon doit suivre le reticule du tireur")

	# Outside it the keeper is clamped: a dive over the bar is a lost input.
	#
	# The tolerance is not slack, it is the engine: a Vector3 holds float32, so a
	# coordinate clamped to exactly Field.BALL_RADIUS comes back as
	# 0.10999999940395355 and a bare >= against the double would fail on a value
	# that is correct. Anything that compares a packed vector against a project
	# constant needs this, and it cost a red test to remember.
	const PACK := 1.0e-6
	var over: Vector3 = KeeperInput.dive_target(Vector2(1.0, 1.0))
	check(over.x <= Field.GOAL_HALF + PACK, "un plongeon ne sort jamais du poteau")
	check(over.y <= Field.GOAL_HEIGHT + PACK,
		"un plongeon ne passe jamais au dessus de la barre")
	var under: Vector3 = KeeperInput.dive_target(Vector2(-1.0, 0.0))
	check(under.x >= -Field.GOAL_HALF - PACK, "un plongeon ne sort jamais du poteau oppose")
	check(under.y >= Field.BALL_RADIUS - PACK, "un plongeon ne passe jamais sous la pelouse")
	near(over.z, 0.0, 1.0e-9, "la cible vit sur le plan de la ligne de but")
	done()


func test_move_aim_stays_inside_its_band() -> void:
	var aim := Vector2(0.0, 0.5)
	for _i in 400:
		aim = KeeperInput.move_aim(aim, Vector2(40.0, -30.0), 2.0)
	between(aim.x, -1.0, 1.0, "le reticule reste dans sa bande en x")
	between(aim.y, 0.0, 1.0, "le reticule reste dans sa bande en y")

	var right: Vector2 = KeeperInput.move_aim(Vector2(0.0, 0.5), Vector2(120.0, 0.0), 1.0)
	check(right.x > 0.0, "pousser la souris a droite vise a droite")
	var down: Vector2 = KeeperInput.move_aim(Vector2(0.0, 0.5), Vector2(0.0, 120.0), 1.0)
	check(down.y < 0.5, "pousser la souris vers le bas vise plus bas")

	var slow: Vector2 = KeeperInput.move_aim(Vector2(0.0, 0.5), Vector2(120.0, 0.0), 0.5)
	check(slow.x < right.x, "une sensibilite plus basse deplace moins le reticule")

	var junk: Vector2 = KeeperInput.move_aim(Vector2(0.2, 0.6), Vector2(NAN, INF), 1.0)
	check(is_finite(junk.x) and is_finite(junk.y),
		"une souris folle ne doit pas emporter le reticule")
	done()


func test_time_available_is_never_negative() -> void:
	near(KeeperInput.time_available(0.0, 0.42), 0.42, 1.0e-9,
		"a la frappe il reste tout le vol")
	near(KeeperInput.time_available(-0.30, 0.42), 0.72, 1.0e-9,
		"partir pendant la course d'elan ajoute du temps")
	near(KeeperInput.time_available(0.42, 0.42), 0.0, 1.0e-9,
		"a l'arrivee il ne reste rien")
	eq(KeeperInput.time_available(9.0, 0.42), 0.0,
		"apres l'arrivee il ne reste toujours rien, jamais du temps negatif")
	check(is_finite(KeeperInput.time_available(NAN, NAN)),
		"une horloge folle ne doit pas produire un NaN")
	done()


func test_reachable_is_exactly_dive_time_needed() -> void:
	# The contract says this in one line, so the suite says it in one loop: the
	# whole module hangs off KeeperBrain, and any local shortcut would show here.
	for level in 4:
		for line_x in LINES:
			for i in 7:
				var x: float = lerpf(-3.5, 3.5, float(i) / 6.0)
				for j in 4:
					var y: float = lerpf(0.15, 2.30, float(j) / 3.0)
					var target := Vector3(x, y, 0.0)
					for t in [-0.4, -0.1, 0.05, 0.2]:
						var budget: float = KeeperInput.time_available(t, 0.42)
						var need: float = KeeperBrain.dive_time_needed(target, line_x, level)
						eq(KeeperInput.reachable(target, line_x, t, 0.42, level),
							need <= budget,
							"l'enveloppe doit etre exactement dive_time_needed")
	done()


func test_margin_agrees_with_reachable() -> void:
	for level in 4:
		for i in 11:
			var x: float = lerpf(-3.5, 3.5, float(i) / 10.0)
			for t in [-0.42, -0.2, 0.0, 0.15, 0.3]:
				var target := Vector3(x, 1.20, 0.0)
				var m: float = KeeperInput.margin(target, 0.0, t, 0.42, level)
				eq(m >= 0.0, KeeperInput.reachable(target, 0.0, t, 0.42, level),
					"le signe de la marge doit dire la meme chose que reachable")
				check(is_finite(m), "la marge doit rester finie")
	# Late is reported as HOW late, not merely as late.
	var early: float = KeeperInput.margin(Vector3(3.4, 2.2, 0.0), 0.0, 0.0, 0.42, 1)
	var later: float = KeeperInput.margin(Vector3(3.4, 2.2, 0.0), 0.0, 0.3, 0.42, 1)
	check(later < early, "plus on s'engage tard, plus la marge se creuse")
	done()


func test_the_envelope_only_ever_shrinks() -> void:
	# Fairness rule 5: coverage falls with t and never climbs back. A ring that
	# grew between two frames would destroy the only readable information there is.
	for level in 4:
		for line_x in LINES:
			var previous := 2.0
			for i in 30:
				var t: float = lerpf(-KeeperInput.NOMINAL_FLIGHT, 0.45, float(i) / 29.0)
				var c: float = KeeperInput.coverage(line_x, t, 0.42, level)
				between(c, 0.0, 1.0, "la couverture est une fraction")
				check(c <= previous + 1.0e-9,
					"la couverture ne doit jamais remonter (%s, ligne %.2f, t %.2f)"
						% [LEVELS[level], line_x, t])
				previous = c

	# And it does not merely fail to rise: it collapses.
	for level in 4:
		var early: float = KeeperInput.coverage(0.0, -0.30, 0.42, level)
		var strike: float = KeeperInput.coverage(0.0, 0.0, 0.42, level)
		var half: float = KeeperInput.coverage(0.0, 0.21, 0.42, level)
		check(early > 0.80, "s'engager tot doit couvrir une grande partie du but")
		check(strike < early - 0.10, "attendre la frappe coute deja du terrain")
		check(half < 0.5 * early,
			"a mi vol il ne doit rester que la moitie de ce qu'on couvrait")
		eq(KeeperInput.coverage(0.0, 0.40, 0.42, level), 0.0,
			"juste avant l'arrivee on ne couvre plus rien du tout")
	done()


func test_the_envelope_never_covers_the_whole_goal() -> void:
	# Fairness rule 2, and the promise the difficulty of the game rests on. Swept
	# over every level, every line position and the whole legal band of t.
	var worst := 0.0
	for level in 4:
		for line_x in LINES:
			for i in 22:
				var t: float = lerpf(-KeeperInput.NOMINAL_FLIGHT, 0.42, float(i) / 21.0)
				worst = maxf(worst, KeeperInput.coverage(line_x, t, 0.42, level))
	check(worst < 1.0, "l'enveloppe ne doit jamais couvrir le but entier")
	check(worst < 0.99, "et elle doit garder une vraie marge, pas un point de grille")

	# The top corners are the reason it cannot. From the middle of his line they are
	# out of reach at every level and at every legal instant, exactly as they are
	# for the AI keeper.
	for level in 4:
		for corner in CORNERS:
			for i in 15:
				var t: float = lerpf(-KeeperInput.NOMINAL_FLIGHT, 0.42, float(i) / 14.0)
				check(not KeeperInput.reachable(corner, 0.0, t, 0.42, level),
					"une lucarne bien frappee reste imprenable (%s)" % LEVELS[level])

	# And camping on a post does not buy them either: shading the line buys ONE
	# corner and sells the other, so the two are never both in reach. That is the
	# statement the line dance has to survive, and it is stronger than the one
	# above because it holds wherever the player stands.
	for level in 4:
		for line_x in LINES:
			for i in 15:
				var t: float = lerpf(-KeeperInput.NOMINAL_FLIGHT, 0.42, float(i) / 14.0)
				var both := true
				for corner in CORNERS:
					if not KeeperInput.reachable(corner, line_x, t, 0.42, level):
						both = false
				check(not both,
					"les deux lucarnes ne doivent jamais etre couvertes ensemble (%s)"
						% LEVELS[level])
	done()


func test_a_late_commit_cannot_reach_a_corner() -> void:
	# The core mechanic: commit early and reach far, commit late and cover little.
	var corner := Vector3(2.60, 1.70, 0.0)
	var middle := Vector3(0.30, 1.20, 0.0)
	for level in 4:
		check(KeeperInput.reachable(corner, 0.0, -0.30, 0.42, level),
			"partir tot doit permettre d'atteindre le coin (%s)" % LEVELS[level])
		check(not KeeperInput.reachable(corner, 0.0, 0.15, 0.42, level),
			"partir tard interdit le coin (%s)" % LEVELS[level])
		check(KeeperInput.reachable(middle, 0.0, 0.15, 0.42, level),
			"partir tard laisse encore le milieu (%s)" % LEVELS[level])
		check(not KeeperInput.reachable(middle, 0.0, 0.30, 0.42, level),
			"trop tard, meme le milieu est perdu (%s)" % LEVELS[level])

	# A ball still in the air for longer is a ball the keeper can chase further:
	# that is the difference between a driven penalty and a scuffed one, and it is
	# the reason the caller is allowed to pass the real remaining flight time.
	check(KeeperInput.reachable(corner, 0.0, 0.15, 0.80, 1),
		"une casserole lente laisse le temps d'aller chercher le coin")
	done()


func test_the_drawn_ring_is_the_rule() -> void:
	var ring: PackedVector3Array = KeeperInput.reach_outline(0.0, 0.0, 0.42, 1, 32)
	eq(ring.size(), 32, "l'anneau doit rendre le nombre de points demande")
	for p in ring:
		check(is_finite(p.x) and is_finite(p.y), "aucun point d'anneau ne doit etre NaN")
		near(p.z, 0.0, 1.0e-9, "l'anneau vit sur le plan de la ligne de but")
		between(p.x, -KeeperInput.mouth_half_x() - 1.0e-6,
			KeeperInput.mouth_half_x() + 1.0e-6, "l'anneau reste dans le cadre en x")
		between(p.y, KeeperInput.mouth_floor_y() - 1.0e-6,
			KeeperInput.mouth_ceiling_y() + 1.0e-6, "l'anneau reste dans le cadre en y")
		check(KeeperInput.margin(p, 0.0, 0.0, 0.42, 1) >= -0.01,
			"tout point de l'anneau doit etre atteignable")

	# One step further out along the same ray is NOT reachable, unless the ray was
	# stopped by the frame rather than by the clock.
	var pivot := Vector3(0.0, 1.25, 0.0)
	var outside := 0
	var tested := 0
	for p in ring:
		var dir: Vector3 = (p - pivot)
		if dir.length() < 0.05:
			continue
		var beyond: Vector3 = p + dir.normalized() * 0.30
		if absf(beyond.x) > KeeperInput.mouth_half_x():
			continue
		if beyond.y > KeeperInput.mouth_ceiling_y() or beyond.y < KeeperInput.mouth_floor_y():
			continue
		tested += 1
		if not KeeperInput.reachable(beyond, 0.0, 0.0, 0.42, 1):
			outside += 1
	check(tested > 0, "il doit rester des rayons arretes par l'horloge et non par le cadre")
	eq(outside, tested, "un pas au dela de l'anneau doit etre hors de portee")

	eq(KeeperInput.reach_outline(0.0, 0.40, 0.42, 1, 32).size(), 0,
		"quand plus rien n'est atteignable l'anneau est vide")
	done()


func test_the_ring_shrinks_and_follows_the_line() -> void:
	var previous := 99.0
	for t in [-0.42, -0.20, 0.0, 0.10, 0.20]:
		var ring: PackedVector3Array = KeeperInput.reach_outline(0.0, t, 0.42, 1, 24)
		check(ring.size() > 0, "l'anneau doit exister tant qu'il reste du temps")
		var widest := 0.0
		for p in ring:
			widest = maxf(widest, absf(p.x))
		check(widest <= previous + 1.0e-6, "l'anneau ne doit jamais s'elargir")
		previous = widest

	# The line dance moves the whole envelope, which is what makes shuffling worth
	# doing: leaving the middle buys one post and sells the other.
	var left: PackedVector3Array = KeeperInput.reach_outline(-0.9, 0.0, 0.42, 1, 24)
	var right: PackedVector3Array = KeeperInput.reach_outline(0.9, 0.0, 0.42, 1, 24)
	var left_min := 99.0
	var right_max := -99.0
	var left_max := -99.0
	for p in left:
		left_min = minf(left_min, p.x)
		left_max = maxf(left_max, p.x)
	for p in right:
		right_max = maxf(right_max, p.x)
	check(left_min < -3.0, "colle a son poteau, le gardien couvre ce poteau")
	check(left_max < 2.6, "et il abandonne du terrain de l'autre cote")
	check(right_max > 3.0, "et symetriquement de l'autre cote")
	done()


func test_a_higher_level_reaches_further() -> void:
	# Fairness rule 3: both sides of a duel dive with the same body, so the ladder
	# the player picks is the ladder he is judged on.
	for t in [-0.30, -0.10, 0.0]:
		var previous := -1.0
		for level in 4:
			var c: float = KeeperInput.coverage(0.0, t, 0.42, level)
			check(c >= previous - 1.0e-9,
				"un niveau plus haut ne doit jamais couvrir moins (t %.2f)" % t)
			previous = c
	check(KeeperInput.coverage(0.0, 0.0, 0.42, 3) > KeeperInput.coverage(0.0, 0.0, 0.42, 0),
		"une Legende doit couvrir strictement plus qu'un Debutant")
	done()


func test_line_step_is_bounded_and_paced() -> void:
	near(KeeperInput.line_step(0.0, 1.0, 0.1), KeeperInput.LINE_SPEED * 0.1, 1.0e-9,
		"la danse sur la ligne avance a LINE_SPEED")
	near(KeeperInput.line_step(0.0, -1.0, 0.1), -KeeperInput.LINE_SPEED * 0.1, 1.0e-9,
		"et dans l'autre sens aussi")
	var x := 0.0
	for _i in 200:
		x = KeeperInput.line_step(x, 1.0, 0.05)
	near(x, KeeperInput.LINE_LIMIT, 1.0e-9, "elle bute sur LINE_LIMIT")
	x = 0.0
	for _i in 200:
		x = KeeperInput.line_step(x, -1.0, 0.05)
	near(x, -KeeperInput.LINE_LIMIT, 1.0e-9, "et sur l'autre bord")
	near(KeeperInput.line_step(0.4, 0.0, 0.1), 0.4, 1.0e-9, "sans entree, il ne bouge pas")
	check(is_finite(KeeperInput.line_step(NAN, INF, NAN)),
		"des entrees folles ne doivent pas emporter le gardien hors de sa ligne")
	between(KeeperInput.line_step(5.0, 1.0, 1.0), -KeeperInput.LINE_LIMIT,
		KeeperInput.LINE_LIMIT, "une position deja hors bornes est ramenee dedans")
	done()


func test_commit_describes_the_dive_the_body_can_play() -> void:
	var dive: Dictionary = KeeperInput.commit(Vector2(0.55, 0.42), 0.3, -0.12, 0.42, 2)
	for key in ["target", "side", "height", "committed_at", "reachable", "coverage", "margin"]:
		check(dive.has(key), "commit doit rendre la cle %s" % key)
	var target: Vector3 = dive["target"]
	near_vec(target, KeeperInput.dive_target(Vector2(0.55, 0.42)), 1.0e-9,
		"la cible du plongeon est celle du reticule")
	near(float(dive["committed_at"]), -0.12, 1.0e-9, "l'instant d'engagement est rendu tel quel")
	near(float(dive["coverage"]), KeeperInput.coverage(0.3, -0.12, 0.42, 2), 1.0e-9,
		"la couverture annoncee est celle du module")
	eq(bool(dive["reachable"]), KeeperInput.reachable(target, 0.3, -0.12, 0.42, 2),
		"l'accessibilite annoncee est celle du module")

	# The coarse reading has to be the one KeeperBrain itself would report, or the
	# body, the crowd and the replay describe a player dive differently from an AI
	# one. Asked of choose_dive directly, so a drift over there fails HERE.
	for i in 13:
		var x: float = lerpf(-3.4, 3.4, float(i) / 12.0)
		for j in 7:
			var y: float = lerpf(0.15, 2.30, float(j) / 6.0)
			var p := Vector3(x, y, 0.0)
			var theirs: Dictionary = KeeperBrain.choose_dive({}, {"target": p}, 1, -1.0)
			eq(KeeperInput.coarse_side(p), int(theirs["side"]),
				"le cote grossier doit etre celui de KeeperBrain")
			eq(KeeperInput.coarse_height(p), int(theirs["height"]),
				"la hauteur grossiere doit etre celle de KeeperBrain")
	done()


func test_nothing_produces_a_nan() -> void:
	var junk: Array = [NAN, INF, -INF, 1.0e30, -1.0e30]
	for bad in junk:
		var v: float = bad
		var target := Vector3(v, v, v)
		check(is_finite(KeeperInput.margin(target, v, v, v, 1)),
			"margin doit rester finie sur des entrees folles")
		check(is_finite(KeeperInput.coverage(v, v, v, 1)),
			"coverage doit rester finie sur des entrees folles")
		check(is_finite(KeeperInput.time_available(v, v)),
			"time_available doit rester finie sur des entrees folles")
		var aim := Vector2(v, v)
		var point: Vector3 = KeeperInput.dive_target(aim)
		check(is_finite(point.x) and is_finite(point.y) and is_finite(point.z),
			"dive_target doit rester finie sur des entrees folles")
		var dive: Dictionary = KeeperInput.commit(aim, v, v, v, 9)
		check(is_finite(float(dive["margin"])) and is_finite(float(dive["coverage"])),
			"commit doit rester fini sur des entrees folles")
		var ring: PackedVector3Array = KeeperInput.reach_outline(v, v, v, -3, 12)
		for p in ring:
			check(is_finite(p.x) and is_finite(p.y),
				"reach_outline doit rester finie sur des entrees folles")
	# An out of range level must be handled, not crash: the settings are clamped
	# elsewhere but this module is called from a HUD that reads them raw.
	check(is_finite(KeeperInput.coverage(0.0, 0.0, 0.42, 99)),
		"un niveau hors bornes doit etre ramene, pas propage")
	done()
