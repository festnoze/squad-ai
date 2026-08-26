extends GoalTest
## Adversarial suite for Aero, the flight model.
##
## Aero is the module the whole game hangs off: the keeper's mental model, the
## HUD preview, the aim assist and the ball itself all integrate through it. A
## silent sign flip or a coefficient an order of magnitude out would not crash
## anything, it would just make the game feel wrong, so the checks here are
## quantitative wherever they can be:
##
##   - the drag crisis is pinned at both thresholds, and proved monotonic and
##     continuous across the whole speed band rather than merely "about right";
##   - the Magnus direction is checked against the contract's sign convention
##     in both handednesses, so a swapped cross product cannot pass;
##   - the aerodynamic force is proved never to do positive work relative to the
##     air, spin included, which is the one law the model must never break;
##   - aim_velocity is round tripped over a grid of 90 targets by actually
##     integrating the answer back to the plane;
##   - every result is checked for NaN and infinity, including the degenerate
##     inputs (no velocity, no spin, absurd spin, negative delta, poisoned
##     vectors) that a live game will eventually hand it.

## Penalty spot, ball resting on the turf.
const SPOT := Vector3(0.0, 0.11, 11.0)
## One revolution per second, in rad/s.
const REV := TAU


func suite_name() -> String:
	return "Aero"


# --- Coefficients -----------------------------------------------------------


func test_drag_crisis_is_pinned_monotonic_and_continuous() -> void:
	# Below the crisis the boundary layer is laminar, above it is turbulent, and
	# the contract fixes both plateaus exactly.
	near(Aero.drag_coefficient(0.0, 0.0), Aero.CD_LAMINAR, 1.0e-6, "Cd a l'arret")
	near(Aero.drag_coefficient(4.0, 0.0), Aero.CD_LAMINAR, 1.0e-6, "Cd sous la crise")
	near(Aero.drag_coefficient(Aero.CRISIS_LOW, 0.0), Aero.CD_LAMINAR, 1.0e-6, "Cd au seuil bas")
	near(Aero.drag_coefficient(Aero.CRISIS_HIGH, 0.0), Aero.CD_TURBULENT, 1.0e-6, "Cd au seuil haut")
	near(Aero.drag_coefficient(45.0, 0.0), Aero.CD_TURBULENT, 1.0e-6, "Cd bien au dessus")

	# Continuity across both thresholds: no step, no kink.
	for threshold in [Aero.CRISIS_LOW, Aero.CRISIS_HIGH]:
		var below := Aero.drag_coefficient(threshold - 0.001, 0.0)
		var above := Aero.drag_coefficient(threshold + 0.001, 0.0)
		near(above, below, 1.0e-3, "Cd continu au seuil %f" % threshold)

	# Monotonically decreasing in speed, and never jumping.
	var previous := Aero.drag_coefficient(0.0, 0.0)
	var breaks := 0
	var jumps := 0
	var speed := 0.0
	while speed <= 60.0:
		var cd := Aero.drag_coefficient(speed, 0.0)
		if cd > previous + 1.0e-9:
			breaks += 1
		if absf(cd - previous) > 0.02:
			jumps += 1
		if not is_finite(cd):
			fail("Cd non fini a %f m/s" % speed)
		previous = cd
		speed += 0.05
	eq(breaks, 0, "Cd doit decroitre avec la vitesse")
	eq(jumps, 0, "Cd ne doit pas sauter entre deux echantillons")
	done()


func test_spin_raises_drag_and_lift() -> void:
	# Spin re energises the boundary layer, so it pushes the crisis up the speed
	# axis: at a fixed speed a faster spin can only mean a higher Cd. That is the
	# whole "a knuckler flies flat, a curled ball arrives late" story.
	var previous_cd := Aero.drag_coefficient(30.0, 0.0)
	var previous_cl := Aero.lift_coefficient(30.0, 0.0)
	near(previous_cl, 0.0, 1.0e-9, "pas de portance sans effet")
	near(previous_cd, Aero.CD_TURBULENT, 1.0e-6, "Cd sans effet a 30 m/s")

	var rate := 2.0
	var cd_breaks := 0
	var cl_breaks := 0
	while rate <= Aero.MAX_SPIN:
		var cd := Aero.drag_coefficient(30.0, rate)
		var cl := Aero.lift_coefficient(30.0, rate)
		if cd < previous_cd - 1.0e-9:
			cd_breaks += 1
		if cl < previous_cl - 1.0e-9:
			cl_breaks += 1
		previous_cd = cd
		previous_cl = cl
		rate += 2.0
	eq(cd_breaks, 0, "Cd doit croitre avec l'effet")
	eq(cl_breaks, 0, "Cl doit croitre avec l'effet")

	# The sign of the spin cannot change a scalar coefficient.
	near(Aero.drag_coefficient(24.0, -50.0), Aero.drag_coefficient(24.0, 50.0), 1.0e-9, "Cd symetrique en effet")
	near(Aero.lift_coefficient(24.0, -50.0), Aero.lift_coefficient(24.0, 50.0), 1.0e-9, "Cl symetrique en effet")
	done()


func test_lift_saturates_and_is_bounded() -> void:
	# Real measurements flatten out near a spin parameter of 0.3, so doubling an
	# already large spin must buy almost nothing.
	var moderate := Aero.lift_coefficient(25.0, 9.0 * REV)
	var heavy := Aero.lift_coefficient(25.0, 18.0 * REV)
	var absurd := Aero.lift_coefficient(25.0, Aero.MAX_SPIN)
	check(heavy > moderate, "plus d'effet donne plus de portance")
	check(absurd - heavy < heavy - moderate, "la portance doit saturer")
	between(moderate, 0.10, 0.30, "Cl a 9 tr/s et 25 m/s")
	check(absurd < 0.40, "Cl borne meme a l'effet maximal")

	# A ball at rest has no aerodynamic frame at all.
	near(Aero.lift_coefficient(0.0, 100.0), 0.0, 1.0e-9, "pas de portance a l'arret")
	done()


# --- Forces -----------------------------------------------------------------


func test_magnus_follows_the_contract_sign() -> void:
	# The binding convention: spin = (0, +w, 0) on a ball heading towards -Z
	# bends it towards -X. This is the raw spin x velocity cross product.
	var towards_goal := Vector3(0.0, 0.0, -25.0)
	var right_curl := Aero.acceleration(towards_goal, Vector3(0.0, 60.0, 0.0), Vector3.ZERO)
	check(right_curl.x < -1.0, "effet +Y sur un tir vers -Z doit devier vers -X")

	var left_curl := Aero.acceleration(towards_goal, Vector3(0.0, -60.0, 0.0), Vector3.ZERO)
	check(left_curl.x > 1.0, "effet -Y doit devier vers +X")
	near(left_curl.x, -right_curl.x, 1.0e-5, "les deux enroules sont symetriques")

	# Backspin (+X here) lifts, topspin (-X) presses the ball down. Compared to
	# the spin free flight, not to zero, since gravity is in there too.
	var plain := Aero.acceleration(towards_goal, Vector3.ZERO, Vector3.ZERO)
	var backspin := Aero.acceleration(towards_goal, Vector3(60.0, 0.0, 0.0), Vector3.ZERO)
	var topspin := Aero.acceleration(towards_goal, Vector3(-60.0, 0.0, 0.0), Vector3.ZERO)
	check(backspin.y > plain.y + 1.0, "le retro doit porter le ballon")
	check(topspin.y < plain.y - 1.0, "le lifte doit plaquer le ballon")

	# Spin aligned with the flight (pure rifling) produces no Magnus force.
	var rifled := Aero.acceleration(towards_goal, Vector3(0.0, 0.0, -80.0), Vector3.ZERO)
	near(rifled.x, 0.0, 1.0e-6, "un effet axial ne devie pas en X")
	near(rifled.y, plain.y, 1.0e-6, "un effet axial ne devie pas en Y")
	done()


func test_aerodynamic_force_never_adds_energy() -> void:
	# The one law the model may never break: relative to the air, the drag plus
	# Magnus force can only remove kinetic energy. Magnus is perpendicular so it
	# does no work at all, drag is antiparallel so its work is negative.
	var gravity := Vector3(0.0, -Aero.GRAVITY, 0.0)
	var velocities: Array[Vector3] = [
		Vector3(0.0, 0.0, -30.0), Vector3(2.0, 6.0, -22.0), Vector3(-5.0, -3.0, -12.0),
		Vector3(0.4, 0.0, -0.6), Vector3(0.0, 14.0, 0.0), Vector3(11.0, -9.0, 4.0),
	]
	var spins: Array[Vector3] = [
		Vector3.ZERO, Vector3(0.0, 60.0, 0.0), Vector3(-40.0, 25.0, 10.0),
		Vector3(0.0, 0.0, Aero.MAX_SPIN),
	]
	var winds: Array[Vector3] = [Vector3.ZERO, Vector3(4.0, 0.0, 2.0), Vector3(-3.0, 1.0, -6.0)]

	var violations := 0
	var non_finite := 0
	for v in velocities:
		for w in spins:
			for wind in winds:
				var acc := Aero.acceleration(v, w, wind)
				if not _is_finite(acc):
					non_finite += 1
					continue
				var aero_only := acc - gravity
				if aero_only.dot(v - wind) > 1.0e-6:
					violations += 1
	eq(violations, 0, "la force aerodynamique ne doit jamais fournir d'energie")
	eq(non_finite, 0, "aucune acceleration ne doit etre NaN ou infinie")

	# Without spin the aerodynamic force is exactly antiparallel to the flow.
	var flow := Vector3(3.0, -4.0, -20.0)
	var pure_drag := Aero.acceleration(flow, Vector3.ZERO, Vector3.ZERO) - gravity
	check(pure_drag.cross(flow).length() < 1.0e-5, "sans effet la trainee est colineaire au flux")
	check(pure_drag.dot(flow) < 0.0, "sans effet la trainee freine")

	# No flow, no aerodynamics: only gravity remains.
	near_vec(Aero.acceleration(Vector3.ZERO, Vector3(0.0, 90.0, 0.0), Vector3.ZERO), gravity, 1.0e-9, "ballon a l'arret")
	done()


# --- Real flights -----------------------------------------------------------


func test_penalty_reference_flight() -> void:
	# A struck penalty carries spin. At 30 m/s with 9 rev/s the ball must lose a
	# fifth to a quarter of its speed over the 11 m and take a little over four
	# tenths of a second, which is the whole reason the keeper has to gamble.
	var spun := _shoot(30.0, Vector3(0.0, 9.0 * REV, 0.0))
	check(spun["crossed"], "le tir a 30 m/s doit franchir la ligne")
	var arrival: Vector3 = spun["velocity"]
	var loss := 1.0 - arrival.length() / 30.0
	between(loss, 0.18, 0.32, "perte de vitesse sur 11 m a 30 m/s avec effet")
	between(spun["time"], 0.38, 0.47, "duree de vol a 30 m/s avec effet")

	# The unspun knuckler sits on the turbulent side of the crisis, so it keeps
	# far more of its speed and arrives sooner. That contrast is the model.
	var knuckle := _shoot(30.0, Vector3.ZERO)
	check(knuckle["crossed"], "le tir sans effet doit franchir la ligne")
	var knuckle_speed: float = (knuckle["velocity"] as Vector3).length()
	check(knuckle_speed > arrival.length() + 2.0, "le tir sans effet garde plus de vitesse")
	check(knuckle["time"] < spun["time"], "le tir sans effet arrive plus tot")
	between(1.0 - knuckle_speed / 30.0, 0.05, 0.18, "perte de vitesse sans effet")

	# Drag alone, no spin, cannot make the ball go faster than it left.
	check(knuckle_speed < 30.0, "la trainee ne peut qu'enlever de la vitesse")
	done()


func test_sidespin_deviation_is_playable() -> void:
	# 25 m/s with 8 to 10 rev/s of sidespin has to bend by tens of centimetres:
	# enough to beat a keeper who read the straight line, not enough to be a
	# cartoon. And it bends towards -X for a +Y spin, per the contract.
	for revolutions in [8.0, 9.0, 10.0]:
		var flight := _shoot(25.0, Vector3(0.0, revolutions * REV, 0.0))
		check(flight["crossed"], "tir enroule a %f tr/s" % revolutions)
		var point: Vector3 = flight["point"]
		check(point.x < 0.0, "un effet +Y doit devier vers -X")
		between(absf(point.x), 0.30, 0.80, "deviation laterale a %f tr/s" % revolutions)

	# Mirror the spin, mirror the deviation.
	var right: Vector3 = (_shoot(25.0, Vector3(0.0, 9.0 * REV, 0.0))["point"] as Vector3)
	var left: Vector3 = (_shoot(25.0, Vector3(0.0, -9.0 * REV, 0.0))["point"] as Vector3)
	near(left.x, -right.x, 1.0e-4, "les deux enroules sont symetriques")

	# More spin, more bend.
	var mild: Vector3 = (_shoot(25.0, Vector3(0.0, 4.0 * REV, 0.0))["point"] as Vector3)
	check(absf(mild.x) < absf(right.x), "plus d'effet donne plus de courbe")
	done()


func test_backspin_flattens_and_topspin_dips() -> void:
	# Same strike, same speed, only the rotation axis changes. The arrival height
	# must order itself strictly: topspin lowest, backspin highest.
	var heights: Array[float] = []
	for revolutions in [-10.0, -5.0, 0.0, 5.0, 10.0]:
		var flight := _shoot(25.0, Vector3(revolutions * REV, 0.0, 0.0))
		check(flight["crossed"], "tir a %f tr/s de rotation verticale" % revolutions)
		heights.append((flight["point"] as Vector3).y)

	var strictly_rising := true
	for i in range(1, heights.size()):
		if heights[i] <= heights[i - 1] + 1.0e-4:
			strictly_rising = false
	check(strictly_rising, "la hauteur d'arrivee doit croitre du lifte vers le retro")
	check(heights[4] - heights[0] > 0.5, "l'ecart retro / lifte doit etre lisible")
	done()


func test_integrator_is_accurate_and_stable() -> void:
	# One coarse call must land where a very fine integration lands: that is what
	# lets the HUD preview a whole flight in a handful of steps without lying
	# about where the ball will be.
	var velocity := Vector3(1.0, 3.0, -27.0)
	var spin := Vector3(-20.0, 45.0, 5.0)

	var coarse := Aero.integrate(SPOT, velocity, spin, Vector3.ZERO, 0.1)
	var position := SPOT
	var current := velocity
	for _i in 400:
		var step := Aero.integrate(position, current, spin, Vector3.ZERO, 0.00025)
		position = step[0]
		current = step[1]
	near_vec(coarse[0], position, 0.001, "RK4 grossier contre RK4 fin (position)")
	near_vec(coarse[1], current, 0.01, "RK4 grossier contre RK4 fin (vitesse)")

	# The array contract: exactly two vectors, position first.
	eq(coarse.size(), 2, "integrate rend deux vecteurs")
	check(coarse[0] is Vector3 and coarse[1] is Vector3, "integrate rend des Vector3")

	# A step is a displacement, not a teleport: at 27 m/s over 1/120 s the ball
	# moves about 22 cm.
	var one_step := Aero.integrate(SPOT, velocity, spin, Vector3.ZERO, 1.0 / 120.0)
	near((one_step[0] as Vector3).distance_to(SPOT), velocity.length() / 120.0, 0.01, "longueur d'un pas a 120 Hz")
	done()


func test_spin_decays_but_never_flips() -> void:
	var spin := Vector3(0.0, 9.0 * REV, 0.0)
	var after := Aero.decay_spin(spin, 0.5)
	check(after.length() < spin.length(), "l'effet doit s'attenuer")
	check(after.dot(spin) > 0.0, "l'effet ne doit jamais changer de sens")
	near(after.length() / spin.length(), exp(-Aero.SPIN_DECAY * 0.5), 1.0e-6, "loi de decroissance")

	# Over a whole penalty the loss stays small, otherwise the curve would die
	# mid flight.
	var over_a_penalty := Aero.decay_spin(spin, 0.45)
	between(over_a_penalty.length() / spin.length(), 0.95, 1.0, "effet conserve sur un penalty")

	# A very long flight still cannot reverse or explode it.
	var long_flight := Aero.decay_spin(spin, 120.0)
	check(long_flight.length() < spin.length() * 0.01, "effet quasi nul apres deux minutes")
	check(_is_finite(long_flight), "effet fini")

	# Absurd input is clamped, not propagated.
	check(Aero.decay_spin(Vector3(0.0, 1.0e7, 0.0), 0.0).length() <= Aero.MAX_SPIN + 1.0e-6, "effet borne a MAX_SPIN")
	near_vec(Aero.decay_spin(spin, -1.0), spin, 1.0e-9, "un delta negatif ne fait rien")
	done()


# --- Sampling and plane crossing --------------------------------------------


func test_cross_plane_agrees_with_sample_flight() -> void:
	var velocity := Vector3(1.5, 2.5, -26.0)
	var spin := Vector3(-25.0, 40.0, 0.0)

	var samples := Aero.sample_flight(SPOT, velocity, spin, Vector3.ZERO, 1.0 / 240.0, 300)
	check(samples.size() == 301, "sample_flight rend steps + 1 points")
	near_vec(samples[0], SPOT, 1.0e-9, "le premier point est le depart")

	var interpolated := Vector3.ZERO
	var found := false
	for i in range(1, samples.size()):
		if samples[i].z <= 0.0 and samples[i - 1].z > 0.0:
			var t := samples[i - 1].z / (samples[i - 1].z - samples[i].z)
			interpolated = samples[i - 1].lerp(samples[i], t)
			found = true
			break
	check(found, "le vol echantillonne doit franchir z = 0")

	var crossing := Aero.cross_plane(SPOT, velocity, spin, Vector3.ZERO, 0.0, 4.0)
	check(crossing["crossed"], "cross_plane doit trouver le passage")
	near_vec(crossing["point"], interpolated, 0.005, "cross_plane doit coller a sample_flight")
	near((crossing["point"] as Vector3).z, 0.0, 1.0e-4, "le point est bien sur le plan")

	# A flight that never reaches the plane is reported as such, not guessed.
	var backwards := Aero.cross_plane(SPOT, Vector3(0.0, 5.0, 4.0), Vector3.ZERO, Vector3.ZERO, 0.0, 4.0)
	check(not backwards["crossed"], "un tir vers +Z ne franchit pas le plan")
	var too_short := Aero.cross_plane(SPOT, Vector3(0.0, 0.0, -25.0), Vector3.ZERO, Vector3.ZERO, 0.0, 0.05)
	check(not too_short["crossed"], "un budget de temps trop court ne franchit rien")

	# Every sampled point must be usable by the HUD.
	var bad := 0
	for point in samples:
		if not _is_finite(point):
			bad += 1
	eq(bad, 0, "aucun point echantillonne ne doit etre NaN")
	done()


# --- Aiming -----------------------------------------------------------------


func test_aim_velocity_round_trips() -> void:
	# The gameplay keystone. For every reachable target the returned velocity,
	# integrated back through the very same physics, has to land on the target.
	var spins: Array[Vector3] = [
		Vector3.ZERO,
		Vector3(0.0, 9.0 * REV, 0.0),
		Vector3(-6.0 * REV, 3.0 * REV, 0.0),
	]
	var worst := 0.0
	var refused := 0
	var tried := 0
	for speed in [18.0, 24.0, 30.0]:
		for x in [-3.4, -1.7, 0.0, 1.7, 3.4]:
			for y in [0.2, 1.2, 2.3]:
				for spin in spins:
					tried += 1
					var target := Vector3(x, y, 0.0)
					var velocity := Aero.aim_velocity(SPOT, target, spin, Vector3.ZERO, speed)
					if velocity == Vector3.ZERO:
						refused += 1
						continue
					if not _is_finite(velocity):
						fail("vitesse de visee non finie pour %s" % str(target))
						continue
					near(velocity.length(), speed, 1.0e-4, "la vitesse rendue garde la norme demandee")
					var flight := Aero.cross_plane(SPOT, velocity, spin, Vector3.ZERO, 0.0, 4.0)
					if not flight["crossed"]:
						fail("la solution de visee ne franchit pas le plan pour %s" % str(target))
						continue
					worst = maxf(worst, (flight["point"] as Vector3).distance_to(target))
	eq(refused, 0, "toutes ces cibles sont atteignables")
	check(tried == 135, "la grille de visee doit etre complete")
	check(worst < 0.02, "erreur de visee maximale %f m au dessus de 2 cm" % worst)

	# Wind must be taken into account, not ignored: aiming into a crosswind has
	# to produce a different launch than aiming in still air.
	var wind := Vector3(5.0, 0.0, 0.0)
	var goal := Vector3(1.0, 1.4, 0.0)
	var calm := Aero.aim_velocity(SPOT, goal, Vector3.ZERO, Vector3.ZERO, 26.0)
	var blown := Aero.aim_velocity(SPOT, goal, Vector3.ZERO, wind, 26.0)
	check(blown != Vector3.ZERO, "une solution existe sous le vent")
	check(calm.distance_to(blown) > 0.1, "le vent doit changer la solution")
	var checked := Aero.cross_plane(SPOT, blown, Vector3.ZERO, wind, 0.0, 4.0)
	check(checked["crossed"], "la solution ventee franchit le plan")
	near_vec(checked["point"], goal, 0.02, "visee corrigee du vent")
	done()


func test_aim_velocity_refuses_the_impossible() -> void:
	# An honest ZERO beats a wild guess: Main and the keeper both branch on it.
	eq(Aero.aim_velocity(SPOT, Vector3(0.0, 1.2, 12.0), Vector3.ZERO, Vector3.ZERO, 25.0), Vector3.ZERO, "cible derriere le tireur")
	eq(Aero.aim_velocity(SPOT, Vector3(0.0, 1.2, 11.0), Vector3.ZERO, Vector3.ZERO, 25.0), Vector3.ZERO, "cible au niveau du tireur")
	eq(Aero.aim_velocity(SPOT, Vector3(0.0, 1.2, 0.0), Vector3.ZERO, Vector3.ZERO, 0.0), Vector3.ZERO, "vitesse nulle")
	eq(Aero.aim_velocity(SPOT, Vector3(0.0, 1.2, 0.0), Vector3.ZERO, Vector3.ZERO, -12.0), Vector3.ZERO, "vitesse negative")

	# Far too slow to carry that far: the ball simply cannot get there.
	var far := Vector3(0.0, 2.0, 0.0)
	eq(Aero.aim_velocity(Vector3(0.0, 0.11, 70.0), far, Vector3.ZERO, Vector3.ZERO, 6.0), Vector3.ZERO, "hors de portee a 6 m/s")

	# Poisoned inputs must not come back as poisoned vectors.
	var poisoned := Aero.aim_velocity(Vector3(NAN, 0.11, 11.0), Vector3(0.0, 1.2, 0.0), Vector3.ZERO, Vector3.ZERO, 25.0)
	check(_is_finite(poisoned), "une entree NaN ne doit pas produire une vitesse NaN")
	done()


# --- Contact ----------------------------------------------------------------


func test_bounce_trades_slip_for_spin_both_ways() -> void:
	var up := Vector3.UP

	# Sliding, no spin: the friction impulse must both slow the slide and spin
	# the ball up, with the sign of a ball rolling forwards.
	var slide := Aero.bounce(Vector3(8.0, -6.0, 0.0), Vector3.ZERO, up, 0.45, 0.5)
	var slide_v: Vector3 = slide[0]
	var slide_w: Vector3 = slide[1]
	near(slide_v.y, 0.45 * 6.0, 1.0e-5, "rebond normal amorti par la restitution")
	check(slide_v.x > 0.0 and slide_v.x < 8.0, "le glissement doit etre freine sans s'inverser")
	check(slide_w.z < -1.0, "un glissement vers +X doit creer un effet -Z")
	near(slide_w.z, -slide_v.x / Aero.BALL_RADIUS, 0.5, "le ballon repart en roulement")

	# No slide, heavy spin: the contact must convert the spin into a sideways
	# departure. This is why a ball comes off a post on a new line.
	var spun := Aero.bounce(Vector3(0.0, -6.0, 0.0), Vector3(0.0, 0.0, -60.0), up, 0.45, 0.5)
	var spun_v: Vector3 = spun[0]
	var spun_w: Vector3 = spun[1]
	check(spun_v.x > 0.5, "un effet -Z doit lancer le ballon vers +X")
	check(absf(spun_w.z) < 60.0, "l'effet doit avoir ete depense dans la vitesse")

	# Coulomb cap: with no friction nothing tangential can change.
	var frictionless := Aero.bounce(Vector3(8.0, -6.0, 0.0), Vector3(0.0, 0.0, -30.0), up, 0.75, 0.0)
	near((frictionless[0] as Vector3).x, 8.0, 1.0e-6, "sans frottement la composante tangentielle est intacte")
	near_vec(frictionless[1], Vector3(0.0, 0.0, -30.0), 1.0e-6, "sans frottement l'effet est intact")

	# Energy: a bounce may never give back more than it received.
	var before := Vector3(6.0, -9.0, 2.0)
	var after: Vector3 = (Aero.bounce(before, Vector3(10.0, -20.0, 5.0), up, 0.75, 0.6)[0] as Vector3)
	check(after.length() <= before.length() + 1.0e-6, "un rebond ne doit pas accelerer le ballon")

	# A contact that is already separating is left alone, and a degenerate
	# normal is refused rather than normalised into a NaN.
	var leaving := Aero.bounce(Vector3(1.0, 4.0, 0.0), Vector3.ZERO, up, 0.75, 0.5)
	near_vec(leaving[0], Vector3(1.0, 4.0, 0.0), 1.0e-9, "un ballon qui s'eloigne n'est pas renvoye")
	var degenerate := Aero.bounce(Vector3(1.0, -4.0, 0.0), Vector3.ZERO, Vector3.ZERO, 0.75, 0.5)
	check(_is_finite(degenerate[0]) and _is_finite(degenerate[1]), "une normale nulle ne produit pas de NaN")

	# The wall case, so the frame rebound is not only tested on the turf.
	var post := Aero.bounce(Vector3(0.0, -2.0, -20.0), Vector3.ZERO, Vector3(0.0, 0.0, 1.0), 0.75, 0.4)
	check((post[0] as Vector3).z > 0.0, "un ballon qui frappe le poteau doit repartir vers +Z")
	check(_is_finite(post[1]), "effet fini apres un contact sur le cadre")
	done()


# --- Robustness -------------------------------------------------------------


func test_results_are_deterministic() -> void:
	# The replay, the keeper's model and the HUD preview all re run the same
	# flight. Two identical calls must return bit identical results.
	var velocity := Vector3(0.8, 2.2, -28.0)
	var spin := Vector3(-15.0, 50.0, 3.0)
	var wind := Vector3(1.0, 0.0, -0.5)

	eq(Aero.integrate(SPOT, velocity, spin, wind, 1.0 / 120.0), Aero.integrate(SPOT, velocity, spin, wind, 1.0 / 120.0), "integrate deterministe")
	eq(Aero.sample_flight(SPOT, velocity, spin, wind, 1.0 / 120.0, 60), Aero.sample_flight(SPOT, velocity, spin, wind, 1.0 / 120.0, 60), "sample_flight deterministe")
	eq(Aero.cross_plane(SPOT, velocity, spin, wind, 0.0, 4.0), Aero.cross_plane(SPOT, velocity, spin, wind, 0.0, 4.0), "cross_plane deterministe")
	eq(Aero.aim_velocity(SPOT, Vector3(2.0, 1.4, 0.0), spin, wind, 27.0), Aero.aim_velocity(SPOT, Vector3(2.0, 1.4, 0.0), spin, wind, 27.0), "aim_velocity deterministe")
	eq(Aero.bounce(velocity, spin, Vector3.UP, 0.45, 0.5), Aero.bounce(velocity, spin, Vector3.UP, 0.45, 0.5), "bounce deterministe")

	# Sixty steps of 1/120 s must equal thirty steps of 1/60 s to well within a
	# millimetre, otherwise the replay would drift away from the live flight.
	var a := SPOT
	var av := velocity
	for _i in 60:
		var step := Aero.integrate(a, av, spin, wind, 1.0 / 120.0)
		a = step[0]
		av = step[1]
	var b := SPOT
	var bv := velocity
	for _i in 30:
		var step := Aero.integrate(b, bv, spin, wind, 1.0 / 60.0)
		b = step[0]
		bv = step[1]
	near_vec(a, b, 0.002, "le pas de temps ne doit pas changer la trajectoire")
	done()


func test_degenerate_inputs_stay_finite() -> void:
	var spin := Vector3(-15.0, 50.0, 3.0)

	# Ball at rest, no spin: pure gravity, nothing else defined.
	near_vec(Aero.acceleration(Vector3.ZERO, Vector3.ZERO, Vector3.ZERO), Vector3(0.0, -Aero.GRAVITY, 0.0), 1.0e-9, "ballon immobile")

	# Absurd spin is clamped, not propagated as an absurd force.
	var huge := Aero.acceleration(Vector3(0.0, 0.0, -30.0), Vector3(0.0, 1.0e9, 0.0), Vector3.ZERO)
	check(_is_finite(huge), "un effet enorme ne doit pas produire de NaN")
	check(huge.length() < 400.0, "un effet enorme doit rester borne")

	# Negative and null deltas are no operations.
	var back_in_time := Aero.integrate(SPOT, Vector3(0.0, 0.0, -20.0), spin, Vector3.ZERO, -0.5)
	near_vec(back_in_time[0], SPOT, 1.0e-9, "un delta negatif ne bouge pas le ballon")
	near_vec(back_in_time[1], Vector3(0.0, 0.0, -20.0), 1.0e-9, "un delta negatif ne change pas la vitesse")
	var frozen := Aero.integrate(SPOT, Vector3(0.0, 0.0, -20.0), spin, Vector3.ZERO, 0.0)
	near_vec(frozen[0], SPOT, 1.0e-9, "un delta nul ne bouge pas le ballon")

	# Poisoned vectors are cleaned at the door.
	var poisoned := Aero.integrate(Vector3(NAN, 0.0, 5.0), Vector3(0.0, INF, -10.0), spin, Vector3.ZERO, 1.0 / 120.0)
	check(_is_finite(poisoned[0]) and _is_finite(poisoned[1]), "une entree empoisonnee ne sort pas empoisonnee")

	# Silly sampling arguments.
	eq(Aero.sample_flight(SPOT, Vector3(0.0, 0.0, -20.0), spin, Vector3.ZERO, 0.01, 0).size(), 1, "zero pas rend le seul point de depart")
	eq(Aero.sample_flight(SPOT, Vector3(0.0, 0.0, -20.0), spin, Vector3.ZERO, 0.01, -50).size(), 1, "un nombre de pas negatif est refuse")
	eq(Aero.sample_flight(SPOT, Vector3(0.0, 0.0, -20.0), spin, Vector3.ZERO, -0.01, 10).size(), 1, "un delta negatif ne produit pas de vol")

	# A very long unbounded flight must stay finite rather than run to infinity.
	var long_flight := Aero.sample_flight(SPOT, Vector3(0.0, 25.0, -25.0), spin, Vector3.ZERO, 1.0 / 60.0, 600)
	var bad := 0
	for point in long_flight:
		if not _is_finite(point) or point.length() > 1.0e5:
			bad += 1
	eq(bad, 0, "un vol long doit rester fini")

	# Coefficients survive nonsense too.
	check(is_finite(Aero.drag_coefficient(-30.0, -1.0e9)), "Cd fini sur des entrees absurdes")
	check(is_finite(Aero.lift_coefficient(1.0e9, 1.0e9)), "Cl fini sur des entrees absurdes")
	done()


# --- Helpers ----------------------------------------------------------------


## One straight strike from the spot towards the goal line, no wind.
func _shoot(speed: float, spin: Vector3) -> Dictionary:
	return Aero.cross_plane(SPOT, Vector3(0.0, 0.0, -speed), spin, Vector3.ZERO, 0.0, 4.0)


func _is_finite(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)
