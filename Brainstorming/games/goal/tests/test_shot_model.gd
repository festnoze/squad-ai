extends GoalTest
## Suite for ShotModel (contract 2.11).
##
## The module decides how the game feels in the hands, so the suite checks the
## shape of every curve rather than a handful of magic values: monotonicity of
## the power bar, the concavity claim that makes maximum power a trade off, the
## plateau plus smooth fall off of the contact window, and the fact that the
## error cone is a gradient and not a coin flip.
##
## Several cases are deliberately end to end and go through Aero, because the
## claims they carry cannot be proved without integrating a flight:
##
##   - a clean centred strike at full power arrives where the reticle said,
##   - a clean strike into the top corner is framed essentially every time, which
##     is the promise the whole difficulty of the game is built on,
##   - a total miscue aimed at that same corner almost always sails past it,
##   - a total miscue aimed at the MIDDLE stays in the frame instead, arriving
##     slow, spinning and nowhere near its target, which is the shot the keeper
##     is supposed to eat rather than the shank into the stands that would feel
##     like the game cheating.
##
## Those four together are the answer to "timing the power bar does not matter".

const SEED_A := 20260824
const SEED_B := 77712345
## Distance from the spot to the goal line, metres. Local copy so the geometric
## reasoning below reads without jumping to another file.
const PENALTY_RANGE := 11.0


func suite_name() -> String:
	return "ShotModel"


func test_aim_point_maps_the_reticle() -> void:
	var centre := ShotModel.aim_point(Vector2(0.0, 0.5))
	near(centre.x, 0.0, 0.0001, "le centre du reticule doit etre en x = 0")
	near(centre.z, 0.0, 0.0001, "le reticule vit sur le plan de la ligne de but")
	between(centre.y, 1.0, 2.0, "la mi hauteur du reticule doit etre a mi but")

	var low := ShotModel.aim_point(Vector2(0.0, 0.0))
	var high := ShotModel.aim_point(Vector2(0.0, 1.0))
	check(low.y > 0.0, "viser en bas doit rester au dessus du sol")
	check(low.y < 0.25, "viser en bas doit raser la pelouse")
	check(high.y > Field.GOAL_HEIGHT, "viser en haut doit passer au dessus de la barre")
	check(high.y < Field.GOAL_HEIGHT + 1.0, "la marge au dessus de la barre reste raisonnable")

	var right := ShotModel.aim_point(Vector2(1.0, 0.5))
	var left := ShotModel.aim_point(Vector2(-1.0, 0.5))
	check(right.x > Field.GOAL_HALF, "aim.x = 1 doit sortir du cadre, c'est ainsi qu'on tire a cote")
	check(right.x < Field.GOAL_HALF + 1.5, "la marge laterale reste jouable")
	near(left.x, -right.x, 0.0001, "le reticule doit etre symetrique")

	# The post must sit inside the reticle travel, otherwise the player can never
	# aim at the corner itself.
	var corner := ShotModel.aim_point(Vector2(0.9, 0.9))
	check(corner.x > 0.0 and corner.y > 0.0, "le coin haut droit doit rester positif")
	check(_ok(corner.x) and _ok(corner.y) and _ok(corner.z), "aucune composante NaN")
	done()


func test_speed_for_power_is_monotonic() -> void:
	near(ShotModel.speed_for_power(0.0), ShotModel.MIN_SPEED, 0.0001, "puissance nulle = MIN_SPEED")
	near(ShotModel.speed_for_power(1.0), ShotModel.MAX_SPEED, 0.0001, "puissance pleine = MAX_SPEED")

	var strictly_increasing := true
	var previous := ShotModel.speed_for_power(0.0)
	for i in range(1, 101):
		var p := float(i) / 100.0
		var s := ShotModel.speed_for_power(p)
		if not _ok(s) or s <= previous:
			strictly_increasing = false
		previous = s
	check(strictly_increasing, "la vitesse doit croitre strictement avec la puissance")

	# Values outside [0, 1] must be clamped, not extrapolated.
	near(ShotModel.speed_for_power(-3.0), ShotModel.MIN_SPEED, 0.0001, "puissance negative bornee")
	near(ShotModel.speed_for_power(4.0), ShotModel.MAX_SPEED, 0.0001, "puissance excessive bornee")
	between(ShotModel.speed_for_power(0.5), 20.0, 32.0, "la mi barre doit deja etre un vrai tir")
	done()


func test_speed_for_power_is_concave() -> void:
	# The contract claim: the last 20 % of the bar buys noticeably less speed
	# than the middle 20 %. "Noticeably" is read here as less than two thirds.
	var top_gain := ShotModel.speed_for_power(1.0) - ShotModel.speed_for_power(0.8)
	var middle_gain := ShotModel.speed_for_power(0.6) - ShotModel.speed_for_power(0.4)
	check(top_gain > 0.0, "le haut de la barre doit quand meme acheter de la vitesse")
	check(top_gain < middle_gain * 0.67, "le haut de la barre doit acheter bien moins que le milieu")

	# Concavity everywhere: every second difference is negative.
	var concave := true
	var step := 0.02
	var p := step
	while p < 1.0 - step - 0.0001:
		var a := ShotModel.speed_for_power(p - step)
		var b := ShotModel.speed_for_power(p)
		var c := ShotModel.speed_for_power(p + step)
		if (c - b) > (b - a) + 0.0001:
			concave = false
		p += step
	check(concave, "la courbe de puissance doit etre concave sur toute la barre")
	done()


func test_contact_quality_shape() -> void:
	near(ShotModel.contact_quality(0.5, 0.5), 1.0, 0.0001, "frappe pile au centre = 1.0")
	near(ShotModel.contact_quality(0.5 + ShotModel.SWEET_WIDTH, 0.5), 1.0, 0.0001, "bord de la fenetre = 1.0")
	near(ShotModel.contact_quality(0.5 - ShotModel.SWEET_WIDTH, 0.5), 1.0, 0.0001, "fenetre symetrique")
	near(ShotModel.contact_quality(0.9, 0.5), 0.0, 0.0001, "a 0.40 du centre la frappe est ratee")
	near(ShotModel.contact_quality(0.5, 0.85), 0.0, 0.0001, "symetrique de l'autre cote")

	# A miscue is a gradient, not a coin flip: strictly decreasing between the
	# window and the total miss, and never a jump.
	# The fall off is steep, so it is sampled twice as finely as the eye would:
	# over half a hundredth of the bar nothing may ever move by more than 0.09 of
	# quality. That is what keeps it a slide rather than a cliff edge, even though
	# the whole slide is only a tenth of the bar wide.
	var decreasing := true
	var bounded := true
	var previous := 1.0
	for i in range(0, 121):
		var d := float(i) / 200.0
		var q := ShotModel.contact_quality(0.5 + d, 0.5)
		if not _ok(q):
			bounded = false
		if q < 0.0 or q > 1.0:
			bounded = false
		if q > previous + 0.0001:
			decreasing = false
		if absf(q - previous) > 0.09:
			decreasing = false
		previous = q
	check(bounded, "la qualite reste dans [0, 1] et jamais NaN")
	check(decreasing, "la qualite doit decroitre doucement, sans marche d'escalier")

	# Leaving the window is punished AT ONCE, because timing the bar is the skill
	# the game is about. The gradient is still a gradient (checked just above),
	# but it is steep: barely outside is already not quite a clean strike, and
	# 0.23 off is very nearly nothing at all.
	var just_out := ShotModel.contact_quality(0.5 + 0.135, 0.5)
	between(just_out, 0.72, 0.90,
		"juste hors de la fenetre, la frappe n'est deja plus propre")
	var halfway := ShotModel.contact_quality(0.5 + 0.15, 0.5)
	between(halfway, 0.45, 0.70, "a 0.15 du centre il ne reste que la moitie de la frappe")
	var clearly_out := ShotModel.contact_quality(0.5 + 0.17, 0.5)
	check(clearly_out < 0.35, "a 0.17 du centre la frappe est franchement ratee (%f)" % clearly_out)
	var mid := ShotModel.contact_quality(0.5 + 0.23, 0.5)
	check(mid < 0.02, "a 0.23 du centre il ne reste plus rien du tout (%f)" % mid)
	done()


func test_error_angle_shape() -> void:
	# A clean strike is near perfect at any power: well under half a degree.
	var half_degree := deg_to_rad(0.5)
	for p in [0.0, 0.3, 0.6, 1.0]:
		var clean: float = ShotModel.error_angle(1.0, p)
		check(clean > 0.0, "meme une frappe propre garde un residu, sinon deux tirs sont identiques")
		check(clean < half_degree * 0.5, "une frappe propre doit rester tres en dessous du demi degre")

	var worst := ShotModel.error_angle(0.0, 1.0)
	var placed := ShotModel.error_angle(0.0, 0.0)
	check(worst > placed * 2.0, "une casserole a pleine puissance part bien plus loin qu'un tir place")
	check(worst < deg_to_rad(12.0), "l'erreur maximale doit rester un tir rate, pas un shoot dans les tribunes")

	# Monotone in both arguments.
	var monotone := true
	var previous := ShotModel.error_angle(1.0, 1.0)
	for i in range(1, 21):
		var q := 1.0 - float(i) / 20.0
		var a := ShotModel.error_angle(q, 1.0)
		if not _ok(a) or a < previous:
			monotone = false
		previous = a
	check(monotone, "l'erreur doit croitre quand la qualite baisse")

	var by_power := true
	previous = ShotModel.error_angle(0.0, 0.0)
	for i in range(1, 21):
		var a := ShotModel.error_angle(0.0, float(i) / 20.0)
		if not _ok(a) or a < previous:
			by_power = false
		previous = a
	check(by_power, "l'erreur doit croitre avec la puissance")

	# The concavity claim, and the whole answer to "la barre de puissance ne sert
	# a rien". The fall off exponent is below 1, so the cone opens up the moment
	# the release leaves the window instead of forgiving the near miss. A quality
	# of 0.93 is a release only 0.135 off the centre of the window, and it must
	# already spray more than a degree, which is the entire margin of a corner.
	var slight := ShotModel.error_angle(0.926, 1.0)
	check(slight > deg_to_rad(1.0),
		"une frappe a peine hors fenetre part deja de plus d'un degre (%f deg)" % rad_to_deg(slight))
	check(slight < worst * 0.4,
		"mais elle reste tres loin de la casserole complete (%f contre %f)" % [slight, worst])
	# Concave, not convex: half the quality lost costs MORE than half the cone.
	var half := ShotModel.error_angle(0.5, 1.0) - ShotModel.error_angle(1.0, 1.0)
	check(half > (worst - ShotModel.error_angle(1.0, 1.0)) * 0.5,
		"la punition est concave: perdre la moitie de la qualite coute plus de la moitie du cone")
	done()


func test_error_angle_is_big_enough_to_miss() -> void:
	# Deliberate design numbers, checked here so nobody "tidies" them away.
	# Missing a 7.32 m goal from the spot while aiming dead centre would need
	# atan(3.66 / 11) = 18.4 deg, which is not a mishit but a shank into the
	# stands. The cone is sized just under that instead: wide enough to wreck
	# anything placed near a post or the bar, narrow enough that a scuffed shot
	# aimed at the middle stays in the frame and is simply eaten by the keeper.
	var worst := ShotModel.error_angle(0.0, 1.0)
	var spray := PENALTY_RANGE * tan(worst)
	# A corner is about 0.6 m from a post and 0.4 m under the bar, so anything
	# over a metre of spray means a miscue can no longer buy a corner.
	check(spray > 1.4, "une casserole doit deplacer le ballon de plus de 1.4 m sur 11 m (%f)" % spray)
	check(spray < Field.GOAL_HALF, "une casserole ne doit pas envoyer un tir plein centre hors du cadre")
	check(worst > deg_to_rad(7.0), "plusieurs degres, pas quelques dixiemes")
	check(worst < deg_to_rad(12.0), "et jamais un shoot dans les tribunes")

	var clean_spray := PENALTY_RANGE * tan(ShotModel.error_angle(1.0, 1.0))
	check(clean_spray < 0.05, "une frappe propre doit tomber a moins de 5 cm de la cible")
	done()


## Complaint (b) of the rebalance, stated as a measurement: a strike released
## outside the sweet window must rarely find the frame at all, while the same
## intention struck cleanly must be reliable. This is the ShotModel half of the
## claim, so it stops at the frame and never asks whether a keeper was there.
func test_miscue_rarely_finds_the_frame() -> void:
	var aims: Array[Vector2] = [
		Vector2(0.70, 0.68), Vector2(-0.70, 0.68),
		Vector2(0.68, 0.14), Vector2(-0.68, 0.14),
		Vector2(0.45, 0.45), Vector2(-0.45, 0.45),
	]
	var powers: Array[float] = [0.6, 0.8, 1.0]
	# Releases spread over the whole outside of the window, from "barely late" to
	# "completely mistimed", so no single severity carries the figure.
	var releases: Array[float] = [0.635, 0.67, 0.71, 0.75, 0.79, 0.83]

	var clean_framed := 0
	var clean_total := 0
	var clean_offset := 0.0
	var clean_stray := 0.0
	var miscue_framed := 0
	var miscue_total := 0
	var miscue_offset := 0.0
	var miscue_stray := 0.0
	var seed_index := 0

	for aim in aims:
		for power in powers:
			for release in releases:
				seed_index += 1
				var clean := ShotModel.resolve(aim, power, 0.0, 0.0, 0.5, 0.5, SEED_A + seed_index * 7919)
				clean_total += 1
				var clean_point := _crossing(clean)
				if clean_point.z < 900.0 and Field.is_within_frame(clean_point):
					clean_framed += 1
					clean_offset += absf(clean_point.x)
					clean_stray += Vector2(clean_point.x, clean_point.y).distance_to(
						Vector2((clean["target"] as Vector3).x, (clean["target"] as Vector3).y))
				var sloppy := ShotModel.resolve(aim, power, 0.0, 0.0, release, 0.5, SEED_B + seed_index * 6151)
				miscue_total += 1
				var sloppy_point := _crossing(sloppy)
				if sloppy_point.z < 900.0 and Field.is_within_frame(sloppy_point):
					miscue_framed += 1
					miscue_offset += absf(sloppy_point.x)
					miscue_stray += Vector2(sloppy_point.x, sloppy_point.y).distance_to(
						Vector2((sloppy["target"] as Vector3).x, (sloppy["target"] as Vector3).y))

	var clean_rate := float(clean_framed) / float(clean_total)
	var miscue_rate := float(miscue_framed) / float(miscue_total)
	check(clean_rate > 0.95,
		"une frappe propre visant l'interieur du cadre y arrive presque toujours (%.1f %%)" % (clean_rate * 100.0))
	check(miscue_rate < 0.85,
		"une frappe relachee hors de la fenetre rate le cadre bien plus souvent (%.1f %%)" % (miscue_rate * 100.0))
	check(clean_rate - miscue_rate > 0.15,
		"l'ecart de cadrage entre les deux est net (%.1f contre %.1f %%)"
			% [clean_rate * 100.0, miscue_rate * 100.0])

	# And the design claim that matters most, because it is what hands the shot
	# to the keeper. A miscue that DOES stay in the frame landed nowhere near
	# where it was aimed, and on average nearer the middle of the goal: it is no
	# longer a corner, it is a ball somewhere around the goalkeeper.
	clean_offset /= float(maxi(clean_framed, 1))
	miscue_offset /= float(maxi(miscue_framed, 1))
	clean_stray /= float(maxi(clean_framed, 1))
	miscue_stray /= float(maxi(miscue_framed, 1))
	check(clean_stray < 0.05,
		"une frappe propre atterrit sur son reticule (%.3f m d'ecart)" % clean_stray)
	check(miscue_stray > 0.45,
		"une casserole cadree atterrit tres loin de sa cible (%.2f m d'ecart)" % miscue_stray)
	check(miscue_offset < clean_offset - 0.15,
		"et plus pres du milieu du but qu'une frappe propre (%.2f m contre %.2f m)"
			% [miscue_offset, clean_offset])

	# And what does get through arrives slower, which is the other half of the
	# punishment: a mishit ball is exactly the ball a keeper saves.
	var clean_speed: float = ShotModel.resolve(Vector2(0.5, 0.5), 1.0, 0.0, 0.0, 0.5, 0.5, SEED_A)["speed"]
	var sloppy_speed: float = ShotModel.resolve(Vector2(0.5, 0.5), 1.0, 0.0, 0.0, 0.85, 0.5, SEED_A)["speed"]
	check(sloppy_speed < clean_speed * 0.70,
		"une casserole perd au moins 30 %% de sa vitesse (%.1f contre %.1f m/s)" % [sloppy_speed, clean_speed])

	# ...and it carries spin nobody asked for, which is why it also curves away
	# from wherever the reticle was pointing.
	var clean_spin: Vector3 = ShotModel.resolve(Vector2(0.5, 0.5), 1.0, 0.0, 0.0, 0.5, 0.5, SEED_A)["spin"]
	var sloppy_spin: Vector3 = ShotModel.resolve(Vector2(0.5, 0.5), 1.0, 0.0, 0.0, 0.85, 0.5, SEED_A)["spin"]
	near(clean_spin.length(), 0.0, 0.001, "sans consigne d'effet, une frappe propre ne tourne pas")
	check(sloppy_spin.length() > 25.0,
		"une frappe raclee repart avec un effet parasite (%f rad/s)" % sloppy_spin.length())
	done()


func test_spin_vector_axes_and_bounds() -> void:
	var none := ShotModel.spin_vector(0.0, 0.0, 1.0)
	near(none.length(), 0.0, 0.0001, "sans consigne d'effet, aucun effet")

	# Magnus goes as omega x v. For a ball leaving towards -Z, a positive y spin
	# pushes it towards -X, so a curl towards +X needs a negative y component.
	var right_curl := ShotModel.spin_vector(1.0, 0.0, 1.0)
	check(right_curl.y < 0.0, "un effet vers +X doit avoir une composante y negative")
	near(right_curl.x, 0.0, 0.0001, "un effet lateral pur n'a pas de composante x")
	var left_curl := ShotModel.spin_vector(-1.0, 0.0, 1.0)
	near(left_curl.y, -right_curl.y, 0.0001, "l'effet lateral doit etre symetrique")

	# Backspin lifts, so its Magnus force is +Y, which needs a positive x spin.
	var back := ShotModel.spin_vector(0.0, 1.0, 1.0)
	check(back.x > 0.0, "le retro doit avoir une composante x positive")
	var top := ShotModel.spin_vector(0.0, -1.0, 1.0)
	check(top.x < 0.0, "le lifte doit avoir une composante x negative")

	# Power scales the spin but never gates it completely.
	var soft := ShotModel.spin_vector(1.0, 0.0, 0.0)
	check(soft.length() > 0.0, "un tir place doit pouvoir etre enroule")
	check(soft.length() < right_curl.length(), "un tir puissant porte plus d'effet")

	var extreme := ShotModel.spin_vector(9.0, -9.0, 4.0)
	check(extreme.length() <= Aero.MAX_SPIN + 0.001, "l'effet reste sous le plafond du modele")
	check(_ok(extreme.x) and _ok(extreme.y) and _ok(extreme.z), "aucune composante NaN")
	done()


func test_resolve_outputs_are_bounded() -> void:
	var aims: Array[Vector2] = [
		Vector2(0.0, 0.45), Vector2(0.8, 0.85), Vector2(-0.75, 0.12), Vector2(1.4, 0.5),
	]
	var powers: Array[float] = [0.0, 0.4, 0.75, 1.0]
	var releases: Array[float] = [0.5, 0.62, 0.8, 0.98]

	var bounded := true
	var forward := true
	var speed_matches := true
	var spin_ok := true
	var flags_ok := true
	var index := 0
	for aim in aims:
		for i in powers.size():
			var power: float = powers[i]
			var release: float = releases[i]
			var shot := ShotModel.resolve(aim, power, 0.6, -0.3, release, 0.5, SEED_A + index)
			index += 1

			var velocity: Vector3 = shot["velocity"]
			var spin: Vector3 = shot["spin"]
			var quality: float = shot["quality"]
			var speed: float = shot["speed"]
			var target: Vector3 = shot["target"]
			var miscue: bool = shot["miscue"]

			if not (_ok_vec(velocity) and _ok_vec(spin) and _ok_vec(target)):
				bounded = false
			if not (_ok(quality) and _ok(speed)):
				bounded = false
			if quality < 0.0 or quality > 1.0:
				bounded = false
			# A total miscue now bleeds 38 % of the pace, so the floor sits below
			# MIN_SPEED on purpose: a scuffed placed shot really does arrive at
			# walking pace, and that is exactly why the keeper eats it.
			if speed > ShotModel.MAX_SPEED + 0.001 or speed < ShotModel.MIN_SPEED * 0.6:
				bounded = false
			if absf(velocity.length() - speed) > 0.001:
				speed_matches = false
			if velocity.z >= 0.0:
				forward = false
			if spin.length() > Aero.MAX_SPIN + 0.001:
				spin_ok = false
			if quality >= 1.0 and miscue:
				flags_ok = false
			if quality <= 0.0 and not miscue:
				flags_ok = false

	check(bounded, "toutes les sorties de resolve restent finies et dans leurs bornes")
	check(speed_matches, "la vitesse annoncee doit etre exactement la norme du vecteur")
	check(forward, "le ballon doit toujours partir vers le but (-Z)")
	check(spin_ok, "l'effet resolu reste sous Aero.MAX_SPIN")
	check(flags_ok, "le drapeau miscue doit suivre la qualite")
	done()


func test_resolve_is_deterministic() -> void:
	var first := ShotModel.resolve(Vector2(0.35, 0.6), 0.85, 0.4, 0.2, 0.77, 0.5, SEED_A)
	var second := ShotModel.resolve(Vector2(0.35, 0.6), 0.85, 0.4, 0.2, 0.77, 0.5, SEED_A)
	eq(second["velocity"], first["velocity"], "meme graine, meme vitesse au bit pres")
	eq(second["spin"], first["spin"], "meme graine, meme effet au bit pres")
	eq(second["quality"], first["quality"], "meme graine, meme qualite")
	eq(second["speed"], first["speed"], "meme graine, meme norme")
	eq(second["target"], first["target"], "meme graine, meme cible")
	eq(second["miscue"], first["miscue"], "meme graine, meme verdict de frappe")

	# A different seed must move a mishit strike, otherwise the cone is dead.
	var other := ShotModel.resolve(Vector2(0.35, 0.6), 0.85, 0.4, 0.2, 0.77, 0.5, SEED_B)
	ne(other["velocity"], first["velocity"], "une autre graine doit changer une frappe ratee")
	eq(other["speed"], first["speed"], "la graine ne doit pas changer la vitesse")
	done()


func test_resolve_survives_hostile_input() -> void:
	var cases: Array[Dictionary] = [
		{"aim": Vector2(NAN, NAN), "power": NAN, "side": NAN, "lift": NAN, "release": NAN, "sweet": NAN},
		{"aim": Vector2(INF, -INF), "power": INF, "side": -INF, "lift": INF, "release": INF, "sweet": 0.5},
		{"aim": Vector2(1e9, -1e9), "power": -5.0, "side": 12.0, "lift": -12.0, "release": -40.0, "sweet": 900.0},
	]
	var survived := true
	for c in cases:
		var shot := ShotModel.resolve(
			c["aim"], c["power"], c["side"], c["lift"], c["release"], c["sweet"], -991
		)
		var velocity: Vector3 = shot["velocity"]
		var spin: Vector3 = shot["spin"]
		if not (_ok_vec(velocity) and _ok_vec(spin) and _ok_vec(shot["target"])):
			survived = false
		if not (_ok(shot["quality"]) and _ok(shot["speed"])):
			survived = false
		if velocity.length() < 1.0:
			survived = false
	check(survived, "aucune entree aberrante ne doit produire un NaN ni un ballon immobile")

	# A negative seed is a legal seed, and must still be reproducible.
	var a := ShotModel.resolve(Vector2(0.1, 0.5), 0.5, 0.0, 0.0, 0.9, 0.5, -123456)
	var b := ShotModel.resolve(Vector2(0.1, 0.5), 0.5, 0.0, 0.0, 0.9, 0.5, -123456)
	eq(b["velocity"], a["velocity"], "une graine negative reste deterministe")
	done()


func test_clean_max_power_strike_reaches_the_frame() -> void:
	# The headline promise of the module: aim at the middle of the goal, hit the
	# window, pull the bar all the way, and the ball arrives where the reticle
	# said it would.
	var aim := Vector2(0.0, 0.41)
	var shot := ShotModel.resolve(aim, 1.0, 0.0, 0.0, 0.5, 0.5, SEED_A)
	near(shot["quality"], 1.0, 0.0001, "une frappe dans la fenetre est propre")
	eq(shot["miscue"], false, "une frappe propre n'est pas une casserole")
	near(shot["speed"], ShotModel.MAX_SPEED, 0.001, "pleine barre et frappe propre = vitesse maximale")

	var velocity: Vector3 = shot["velocity"]
	var spin: Vector3 = shot["spin"]
	near(spin.length(), 0.0, 0.001, "sans consigne d'effet et sans casserole, aucun effet")

	var hit: Dictionary = Aero.cross_plane(Field.SPOT, velocity, spin, Vector3.ZERO, 0.0, 2.0)
	check(bool(hit["crossed"]), "un tir a pleine puissance doit atteindre la ligne de but")
	if bool(hit["crossed"]):
		var point: Vector3 = hit["point"]
		check(Field.is_within_frame(point), "un tir propre plein centre doit etre cadre")
		var target: Vector3 = shot["target"]
		near(point.x, target.x, 0.30, "le ballon doit arriver la ou le reticule visait, en x")
		near(point.y, target.y, 0.30, "le ballon doit arriver la ou le reticule visait, en y")
		var flight: float = hit["time"]
		between(flight, 0.30, 0.75, "un penalty a pleine puissance met environ une demi seconde")
	done()


func test_full_miscue_at_full_power_wrecks_a_corner() -> void:
	# Aimed just inside the top corner: 0.29 m from the post and 0.17 m under the
	# bar. A clean strike lands there every time. A total miscue sprays 1.7 m and
	# balloons, so that same intention now almost always ends up in the stand
	# behind the goal, which is the point: the corner is bought with timing.
	var aim := Vector2(0.74, 0.70)
	var missed := 0
	var framed := 0
	var finite := true
	for i in 32:
		var shot := ShotModel.resolve(aim, 1.0, 0.0, 0.0, 0.95, 0.5, SEED_B + i * 7919)
		if not (_ok_vec(shot["velocity"]) and _ok_vec(shot["spin"])):
			finite = false
			continue
		if i == 0:
			near(shot["quality"], 0.0, 0.0001, "relacher a 0.45 de la fenetre est une casserole totale")
			eq(shot["miscue"], true, "une qualite nulle doit lever le drapeau miscue")
			check(shot["speed"] < ShotModel.MAX_SPEED * 0.70, "une casserole perd aussi beaucoup de vitesse")
		if _framed(shot):
			framed += 1
		else:
			missed += 1

	check(finite, "aucune casserole ne produit de trajectoire infinie")
	check(missed >= 18,
		"une casserole a pleine puissance dans la lucarne sort le plus souvent (%d / 32)" % missed)
	check(framed <= 14, "et elle est rarement cadree (%d / 32)" % framed)

	# The same aim struck cleanly must be reliable. This is the promise the whole
	# rebalance is not allowed to break: a corner remains the correct answer.
	var clean_framed := 0
	for i in 32:
		var clean := ShotModel.resolve(aim, 1.0, 0.0, 0.0, 0.5, 0.5, SEED_B + i * 6151)
		if _framed(clean):
			clean_framed += 1
	check(clean_framed >= 31,
		"la meme intention frappee proprement est cadree (%d / 32)" % clean_framed)

	# The deliberate ceiling on the cone. A scuffed shot aimed at the MIDDLE is
	# not a sideways shank into the corner flag: the goal is 7.32 m wide and the
	# spray is 1.98 m, so what beats it is the bar and the turf, not the posts.
	# It therefore survives far more often than the same mishit aimed at a corner,
	# and when it does survive it arrives slowly, centrally and spinning, which is
	# the shot a keeper eats. Aiming at the middle stays the safe answer for a
	# player who does not trust his timing, and that choice is the whole point.
	var centred := Vector2(0.0, 0.42)
	var centred_framed := 0
	for i in 32:
		var shot := ShotModel.resolve(centred, 1.0, 0.0, 0.0, 0.95, 0.5, SEED_A + i * 7919)
		if _framed(shot):
			centred_framed += 1
	check(centred_framed >= 10,
		"une casserole plein centre survit souvent au cadre (%d / 32)" % centred_framed)
	check(centred_framed > framed,
		"et bien plus souvent que la meme casserole visant la lucarne (%d contre %d)"
			% [centred_framed, framed])
	done()


func test_tell_cues_bounds_and_degradation() -> void:
	var keys: PackedStringArray = [
		"run_angle", "approach_speed", "plant_offset", "hip_yaw",
		"feints", "aim_hint", "lift_hint", "power_hint",
	]
	var cues := ShotModel.tell_cues(Vector2(0.6, 0.7), 0.9, 0.3, -0.4, 1, KeeperBrain.Level.PRO)
	for key in keys:
		check(cues.has(key), "tell_cues doit fournir la cle %s" % key)

	var bounded := true
	for ax in [-1.0, -0.4, 0.0, 0.55, 1.0]:
		for p in [0.0, 0.5, 1.0]:
			for f in [0, 1, 2]:
				for level in [0, 1, 2, 3]:
					var c := ShotModel.tell_cues(Vector2(ax, 0.6), p, -0.2, 0.3, f, level)
					if not _in(c["run_angle"], -1.0, 1.0):
						bounded = false
					if not _in(c["approach_speed"], 0.0, 1.0):
						bounded = false
					if not _in(c["plant_offset"], -1.0, 1.0):
						bounded = false
					if not _in(c["hip_yaw"], -1.6, 1.6):
						bounded = false
					if not _in(c["aim_hint"], -1.0, 1.0):
						bounded = false
					if not _in(c["lift_hint"], -1.0, 1.0):
						bounded = false
					if not _in(c["power_hint"], 0.0, 1.0):
						bounded = false
					if typeof(c["feints"]) != TYPE_INT or int(c["feints"]) != f:
						bounded = false
	check(bounded, "tous les indices doivent rester dans leurs bornes et finis")

	# lift_hint is the cue that lets the keeper pick a HEIGHT. Averaged over the
	# whole travel of the reticle, a legend must read it far better than a
	# beginner, otherwise every top corner is conceded for free whatever else the
	# keeper is good at.
	var lift_error_low := 0.0
	var lift_error_high := 0.0
	for i in 40:
		var ay := float(i) / 39.0
		var truth := ay * 2.0 - 1.0
		lift_error_low += absf(float(ShotModel.tell_cues(Vector2(0.2, ay), 0.8, 0.0, 0.0, 0, 0)["lift_hint"]) - truth)
		lift_error_high += absf(float(ShotModel.tell_cues(Vector2(0.2, ay), 0.8, 0.0, 0.0, 0, 3)["lift_hint"]) - truth)
	check(lift_error_high < lift_error_low * 0.7,
		"une legende lit la hauteur bien mieux qu'un debutant (%f contre %f)" % [lift_error_high, lift_error_low])

	# And a feint muddles the height exactly as it muddles the side.
	var lift_clean := 0.0
	var lift_feinted := 0.0
	for i in 40:
		var ay := float(i) / 39.0
		var truth := ay * 2.0 - 1.0
		lift_clean += absf(float(ShotModel.tell_cues(Vector2(0.2, ay), 0.8, 0.0, 0.0, 0, 3)["lift_hint"]) - truth)
		lift_feinted += absf(float(ShotModel.tell_cues(Vector2(0.2, ay), 0.8, 0.0, 0.0, 2, 3)["lift_hint"]) - truth)
	check(lift_feinted > lift_clean, "deux feintes brouillent aussi la lecture de la hauteur")

	# Feints scramble the read: averaged over many aims, two feints leave a much
	# worse aim_hint than none.
	var read: float = KeeperBrain.read_skill(KeeperBrain.Level.LEGENDE)
	var error_none := 0.0
	var error_two := 0.0
	for i in 40:
		var ax := -1.0 + 2.0 * float(i) / 39.0
		error_none += absf(float(ShotModel.tell_cues(Vector2(ax, 0.5), 0.8, 0.0, 0.0, 0, 3)["aim_hint"]) - ax)
		error_two += absf(float(ShotModel.tell_cues(Vector2(ax, 0.5), 0.8, 0.0, 0.0, 2, 3)["aim_hint"]) - ax)
	if read > 0.05:
		check(error_two > error_none, "deux feintes doivent brouiller la lecture de la visee")
	else:
		fail("KeeperBrain.read_skill rend zero pour une legende, la degradation est intestable")

	# A hard strike leaks more of its power than a placed one.
	var leak_hard := 0.0
	var leak_soft := 0.0
	for i in 40:
		var jitter := float(i) / 400.0
		leak_hard += absf(float(ShotModel.tell_cues(Vector2(jitter, 0.5), 0.95, 0.0, 0.0, 0, 2)["power_hint"]) - 0.95)
		leak_soft += absf(float(ShotModel.tell_cues(Vector2(jitter, 0.5), 0.25, 0.0, 0.0, 0, 2)["power_hint"]) - 0.25)
	check(leak_hard < leak_soft, "un tir puissant doit trahir sa puissance plus qu'un tir place")

	# THE CEILING ON THE AIM TELL, MEASURED, because the whole top of the keeper
	# ladder now rests on it.
	#
	# What a degraded cue leaves behind is not noise, it is a DECOY: a plausible,
	# confident, wrong value. Since KeeperBrain stopped quantising its dive, every
	# unit of that decoy is a unit of goal the keeper dives past, and the reticle
	# spans 4.40 m of goal per unit of aim.x. So the ladder cannot be steeper at the
	# top than this ceiling allows, and these two bounds pin it from both sides: a
	# Legende must be genuinely sharp, and must still be guessing at the margin.
	var legend_error := 0.0
	var beginner_error := 0.0
	for i in 40:
		var ax := -1.0 + 2.0 * float(i) / 39.0
		legend_error += absf(float(ShotModel.tell_cues(Vector2(ax, 0.5), 0.85, 0.0, 0.0, 0, 3)["aim_hint"]) - ax)
		beginner_error += absf(float(ShotModel.tell_cues(Vector2(ax, 0.5), 0.85, 0.0, 0.0, 0, 0)["aim_hint"]) - ax)
	legend_error /= 40.0
	beginner_error /= 40.0
	check(legend_error < 0.11,
		"une legende lit la visee a mieux qu'un dixieme de but pres (%f)" % legend_error)
	check(legend_error > 0.005,
		"mais jamais parfaitement : il reste du bluff meme au sommet (%f)" % legend_error)
	check(beginner_error > legend_error * 3.0,
		"et un debutant est plusieurs fois plus mauvais (%f contre %f)" % [beginner_error, legend_error])

	# Pure function: no seed, no global random state, same body language twice.
	var a := ShotModel.tell_cues(Vector2(-0.3, 0.4), 0.7, 0.5, 0.2, 1, 1)
	var b := ShotModel.tell_cues(Vector2(-0.3, 0.4), 0.7, 0.5, 0.2, 1, 1)
	eq(b["aim_hint"], a["aim_hint"], "tell_cues doit etre une fonction pure")
	eq(b["power_hint"], a["power_hint"], "tell_cues doit etre une fonction pure")
	done()


# --- Local helpers -----------------------------------------------------------


## Where this strike crosses the goal line, flown through Aero with no keeper and
## no frame in the way. Returns a point with z = 1000 when it never gets there.
func _crossing(shot: Dictionary) -> Vector3:
	var hit: Dictionary = Aero.cross_plane(
		Field.SPOT, shot["velocity"], shot["spin"], Vector3.ZERO, 0.0, 2.5)
	if not bool(hit["crossed"]):
		return Vector3(0.0, 0.0, 1000.0)
	return hit["point"]


## True when this strike ends up between the posts and under the bar.
func _framed(shot: Dictionary) -> bool:
	var point := _crossing(shot)
	if point.z > 900.0:
		return false
	return Field.is_within_frame(point)


func _ok(value: float) -> bool:
	return not (is_nan(value) or is_inf(value))


func _ok_vec(v: Vector3) -> bool:
	return _ok(v.x) and _ok(v.y) and _ok(v.z)


func _in(value: Variant, low: float, high: float) -> bool:
	var f := float(value)
	if not _ok(f):
		return false
	return f >= low and f <= high
