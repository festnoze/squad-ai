extends GoalTest
## The net solver's mathematics, tested away from the node.
##
## GoalFrame is a Node3D that builds meshes, materials and colliders, none of
## which a headless suite can or should exercise. What actually decides whether
## the net is any good is the integrator underneath, so the contract says to copy
## that mathematics into the suite and test it here. NetSim below is a faithful
## transcription of GoalFrame's inner loop: same Verlet form, same three spring
## families, same pre-tension, damping, recovery and clamps, same impulse shape.
## When one of them changes, the other has to change with it, and one of these
## seven tests will say so.
##
## What is being proved, and why each one matters:
##
##   at rest it stays at rest    a solver that drifts on its own has a sign error
##                               somewhere, and no amount of damping hides it.
##   an impulse moves the net    the obvious one, and the guard against a net
##                               that is welded solid by an over-eager pin rule.
##   the wave propagates         the whole point of the module. A node a metre
##                               from the impact is untouched by the impulse
##                               itself and must be moved by its neighbours.
##   34 m/s does not explode     a mass spring grid hit by the fastest legal shot
##                               is exactly where a naive stiffness blows up.
##   pinned nodes never move     the boundary has to be exact, not approximate,
##                               or the net creeps off its frame over a match.
##   energy decays               position based constraints must not be able to
##                               inject energy. If this one fails, the net will
##                               eventually explode no matter what the clamps say.
##   the bulge follows the shot  a thunderbolt and a rolled shot have to look
##                               different, which is the contract's own wording.


## A faithful copy of GoalFrame's net mathematics, on a single rectangular panel.
##
## The panel is pinned all round, exactly like every panel of the real goal. The
## grid here is smaller than the real 48 x 20 back panel purely so the suite runs
## in a couple of seconds; nothing about the mathematics depends on the size.
class NetSim extends RefCounted:
	const SUBSTEP := 1.0 / 60.0
	const DAMPING := 0.982
	const PRETENSION := 0.985
	const RECOVERY := 0.015
	const STIFF_STRUCT := 1.0
	const STIFF_SHEAR := 0.55
	const STIFF_BEND := 0.22
	const MAX_NODE_SPEED := 12.0
	const IMPULSE_GAIN := 0.20
	const IMPULSE_SET := 0.006
	const IMPULSE_SET_MAX := 0.09
	const IMPULSE_SIGMA_BASE := 0.30
	const IMPULSE_SIGMA_GAIN := 0.013
	const REF_SHOT_SPEED := 34.0
	const IMPULSE_SIGMA_MAX := IMPULSE_SIGMA_BASE + IMPULSE_SIGMA_GAIN * REF_SHOT_SPEED

	var cols: int = 0
	var rows: int = 0
	var gravity: float = 1.6
	var recovery: float = RECOVERY
	var relax_passes: int = 2

	var pos: PackedVector3Array = PackedVector3Array()
	var prev: PackedVector3Array = PackedVector3Array()
	var rest: PackedVector3Array = PackedVector3Array()
	var pinned: PackedByteArray = PackedByteArray()

	var con_a: PackedInt32Array = PackedInt32Array()
	var con_b: PackedInt32Array = PackedInt32Array()
	var con_rest: PackedFloat32Array = PackedFloat32Array()
	var con_wa: PackedFloat32Array = PackedFloat32Array()
	var con_wb: PackedFloat32Array = PackedFloat32Array()

	## `tension` is the rest length as a fraction of the grid spacing. Pass 1.0 to
	## get a grid whose flat shape satisfies every constraint exactly.
	func _init(
		p_cols: int,
		p_rows: int,
		width: float,
		height: float,
		p_gravity: float,
		p_recovery: float,
		tension: float = PRETENSION
	) -> void:
		cols = p_cols
		rows = p_rows
		gravity = p_gravity
		recovery = p_recovery

		var wide := cols + 1
		var tall := rows + 1
		pos.resize(wide * tall)
		prev.resize(wide * tall)
		rest.resize(wide * tall)
		pinned.resize(wide * tall)

		for j in tall:
			for i in wide:
				var n := j * wide + i
				var p := Vector3(
					lerpf(-width * 0.5, width * 0.5, float(i) / float(cols)),
					height * float(j) / float(rows),
					0.0
				)
				pos[n] = p
				prev[n] = p
				rest[n] = p
				pinned[n] = 1 if (i == 0 or i == cols or j == 0 or j == rows) else 0

		for j in tall:
			for i in wide:
				if i < cols:
					_spring(at(i, j), at(i + 1, j), STIFF_STRUCT, tension)
				if j < rows:
					_spring(at(i, j), at(i, j + 1), STIFF_STRUCT, tension)
				if i < cols and j < rows:
					_spring(at(i, j), at(i + 1, j + 1), STIFF_SHEAR, tension)
					_spring(at(i + 1, j), at(i, j + 1), STIFF_SHEAR, tension)
				if i < cols - 1:
					_spring(at(i, j), at(i + 2, j), STIFF_BEND, 1.0)
				if j < rows - 1:
					_spring(at(i, j), at(i, j + 2), STIFF_BEND, 1.0)

	func at(i: int, j: int) -> int:
		return j * (cols + 1) + i

	func _spring(a: int, b: int, stiffness: float, tension: float) -> void:
		var a_free := pinned[a] == 0
		var b_free := pinned[b] == 0
		if not a_free and not b_free:
			return
		con_a.append(a)
		con_b.append(b)
		con_rest.append(rest[a].distance_to(rest[b]) * tension)
		if a_free and b_free:
			con_wa.append(stiffness * 0.5)
			con_wb.append(stiffness * 0.5)
		elif a_free:
			con_wa.append(stiffness)
			con_wb.append(0.0)
		else:
			con_wa.append(0.0)
			con_wb.append(stiffness)

	func spring_count() -> int:
		return con_a.size()

	func node_count() -> int:
		return pos.size()

	## One fixed substep: Verlet integration with the speed clamp, the ground
	## clamp and the tension recovery, then the relaxation passes.
	func step() -> void:
		var gravity_step := Vector3(0.0, -gravity * SUBSTEP * SUBSTEP, 0.0)
		var max_move := MAX_NODE_SPEED * SUBSTEP
		var max_move_sq := max_move * max_move

		for i in pos.size():
			if pinned[i] != 0:
				continue
			var here := pos[i]
			var move := (here - prev[i]) * DAMPING
			var move_sq := move.length_squared()
			if move_sq > max_move_sq:
				move = move * (max_move / sqrt(move_sq))
			var next := here + move + gravity_step + (rest[i] - here) * recovery
			if next.y < 0.0:
				next.y = 0.0
			prev[i] = here
			pos[i] = next

		for _pass_index in relax_passes:
			for k in con_a.size():
				var a := con_a[k]
				var b := con_b[k]
				var pa := pos[a]
				var pb := pos[b]
				var d := pb - pa
				var length := d.length()
				if length < 0.000001:
					continue
				var factor := (length - con_rest[k]) / length
				pos[a] = pa + d * (factor * con_wa[k])
				pos[b] = pb - d * (factor * con_wb[k])

	func run(steps: int) -> void:
		for _s in steps:
			step()

	## The impulse GoalFrame.net_impulse applies: a Gaussian weighted push along
	## the ball's direction, written as a velocity through the previous position
	## plus an immediate dent. `sigma_override` is only there so a test can make
	## the neighbourhood deliberately narrow.
	func impulse(centre: Vector3, direction: Vector3, speed: float, sigma_override: float = -1.0) -> int:
		var push := direction.normalized()
		var sigma := minf(IMPULSE_SIGMA_BASE + IMPULSE_SIGMA_GAIN * speed, IMPULSE_SIGMA_MAX)
		if sigma_override > 0.0:
			sigma = sigma_override
		var two_sigma_sq := 2.0 * sigma * sigma
		var reach_sq := (sigma * 3.0) * (sigma * 3.0)
		var peak_speed := clampf(speed * IMPULSE_GAIN, 0.35, MAX_NODE_SPEED)
		var peak_set := minf(speed * IMPULSE_SET, IMPULSE_SET_MAX)

		var touched := 0
		for i in pos.size():
			if pinned[i] != 0:
				continue
			var here := pos[i]
			var d_sq := here.distance_squared_to(centre)
			if d_sq > reach_sq:
				continue
			var weight := exp(-d_sq / two_sigma_sq)
			if weight < 0.004:
				continue
			var carried := here - prev[i]
			var moved := here + push * (peak_set * weight)
			pos[i] = moved
			prev[i] = moved - carried - push * (peak_speed * weight * SUBSTEP)
			touched += 1
		return touched

	## Deepest displacement from the rest shape, the same measurement as
	## GoalFrame.net_bulge().
	func bulge() -> float:
		var worst := 0.0
		for i in pos.size():
			var d := pos[i].distance_squared_to(rest[i])
			if d > worst:
				worst = d
		return sqrt(worst)

	func offset_at(i: int, j: int) -> float:
		var n := at(i, j)
		return pos[n].distance_to(rest[n])

	## Kinetic energy with unit node masses. Verlet keeps velocity in the gap
	## between the current and the previous position, so that gap is the velocity.
	func kinetic_energy() -> float:
		var total := 0.0
		var inverse := 1.0 / SUBSTEP
		for i in pos.size():
			if pinned[i] != 0:
				continue
			total += ((pos[i] - prev[i]) * inverse).length_squared()
		return total * 0.5

	func worst_pinned_drift() -> float:
		var worst := 0.0
		for i in pos.size():
			if pinned[i] == 0:
				continue
			var d := pos[i].distance_to(rest[i])
			if d > worst:
				worst = d
		return worst

	func has_bad_number() -> bool:
		for i in pos.size():
			var p := pos[i]
			if is_nan(p.x) or is_nan(p.y) or is_nan(p.z):
				return true
			if is_inf(p.x) or is_inf(p.y) or is_inf(p.z):
				return true
		return false


const COLS := 24
const ROWS := 14
const WIDTH := 3.66
const HEIGHT := 2.10


func suite_name() -> String:
	return "filet (maths Verlet)"


## A panel with no gravity, no recovery and no pre-tension starts in a state that
## satisfies every constraint exactly, so every correction is exactly zero and it
## has to stay put forever. Any drift here is a bug in the integrator itself and
## would show up in the game as a net that slowly slides off its frame.
func test_repos_reste_repos() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 0.0, 0.0, 1.0)
	check(sim.spring_count() > 1000, "la grille de test doit vraiment porter des ressorts")
	check(sim.node_count() == (COLS + 1) * (ROWS + 1), "compte de noeuds de la grille")
	near(sim.bulge(), 0.0, 1e-9, "le filet doit partir exactement au repos")

	sim.run(240)

	near(sim.bulge(), 0.0, 1e-9, "sans force exterieure le filet ne doit pas deriver")
	near(sim.kinetic_energy(), 0.0, 1e-9, "aucune energie ne doit apparaitre toute seule")
	done()


## Under real gravity the panel sags a little, as a real net does, but the
## pre-tension and the recovery term have to keep that sag far below the bulge a
## shot produces. If this margin ever closes, net_bulge() stops being able to
## prove that a goal was scored.
func test_affaissement_reste_petit() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 1.6, NetSim.RECOVERY)
	sim.run(600)

	var sag := sim.bulge()
	check(sag > 0.0, "un filet sous gravite doit s'affaisser un peu")
	check(sag < 0.06, "l'affaissement au repos doit rester tres inferieur a une bosse de but (%f m)" % sag)
	check(not sim.has_bad_number(), "aucune valeur invalide apres 600 pas de gravite")
	done()


## The obvious one, and the guard against a pin rule so eager that nothing can
## move any more. It also checks the dent is instant: the very first rendered
## frame after contact must already show something.
func test_impulsion_deplace_le_filet() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 1.6, NetSim.RECOVERY)
	near(sim.bulge(), 0.0, 1e-9, "le filet doit etre au repos avant la frappe")

	var touched := sim.impulse(Vector3(0.0, 1.05, 0.0), Vector3(0.0, 0.0, -1.0), 24.0)
	check(touched > 20, "l'impulsion doit toucher un voisinage, pas un seul noeud (%d)" % touched)
	check(sim.bulge() > 0.0, "le creux doit exister des la frappe, avant tout pas de simulation")

	sim.run(12)
	check(sim.bulge() > 0.10, "apres 0.2 s le filet doit etre nettement creuse (%f m)" % sim.bulge())
	done()


## The heart of the module. The impulse is deliberately narrow, so a node a metre
## away is provably outside it: whatever moves that node was carried there by the
## springs. The test also checks the ordering, because a wave that arrives
## everywhere at once is not a wave, it is a global offset.
func test_onde_se_propage_aux_voisins() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 0.0, 0.0)
	var centre_i := COLS / 2
	var centre_j := ROWS / 2
	var centre := sim.pos[sim.at(centre_i, centre_j)]
	var far_i := centre_i - 7
	var far_offset := sim.pos[sim.at(far_i, centre_j)].distance_to(centre)

	# 3 sigma is the cut off used by the impulse, so the far node is untouchable.
	check(far_offset > 3.0 * 0.20, "le noeud temoin doit etre hors de portee de l'impulsion")

	sim.impulse(centre, Vector3(0.0, 0.0, -1.0), 20.0, 0.20)
	near(sim.offset_at(far_i, centre_j), 0.0, 1e-9, "le noeud temoin ne doit rien recevoir de l'impulsion")
	check(sim.offset_at(centre_i, centre_j) > 0.0, "le noeud d'impact doit bouger tout de suite")

	sim.run(2)
	var early := sim.offset_at(far_i, centre_j)

	sim.run(58)
	var late := sim.offset_at(far_i, centre_j)

	check(late > 0.004, "l'onde doit avoir atteint le noeud temoin apres 1 s (%f m)" % late)
	check(late > early * 4.0, "le deplacement du temoin doit croitre quand l'onde arrive")
	done()


## The fastest shot the game can produce, straight into the net, for ten seconds
## of simulation. This is the case where an explicit spring solver stiff enough to
## look like cord would diverge; position based constraints must simply refuse to.
func test_stable_a_pleine_puissance() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 1.6, NetSim.RECOVERY)
	sim.impulse(Vector3(0.3, 1.05, 0.0), Vector3(0.15, -0.1, -1.0), 34.0)

	var worst := 0.0
	for _s in 600:
		sim.step()
		var b := sim.bulge()
		if b > worst:
			worst = b

	check(not sim.has_bad_number(), "aucun NaN ni infini apres 600 pas a 34 m/s")
	check(worst > 0.15, "un tir a 34 m/s doit vraiment creuser le filet (%f m)" % worst)
	check(worst < 1.5, "le creux doit rester borne, pas exploser (%f m)" % worst)
	check(sim.bulge() < 0.10, "le filet doit etre revenu pres du repos au bout de 10 s (%f m)" % sim.bulge())
	done()


## The boundary is exact by construction, not by convergence: a pinned node is
## never written to. Over a whole match the smallest creep would walk the cloth
## off its frame, so the tolerance here is zero, not epsilon.
func test_noeuds_epingles_ne_bougent_jamais() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 1.6, NetSim.RECOVERY)
	sim.impulse(Vector3(0.0, 1.05, 0.0), Vector3(0.0, 0.0, -1.0), 34.0)
	sim.run(120)
	eq(sim.worst_pinned_drift(), 0.0, "un noeud epingle ne doit jamais bouger d'un iota")

	# A second hit while the first wave is still running, which is what a ball
	# rattling around inside the goal actually does.
	sim.impulse(Vector3(-0.8, 0.7, -0.1), Vector3(-0.4, 0.2, -1.0), 18.0)
	sim.run(180)
	eq(sim.worst_pinned_drift(), 0.0, "les bords restent fixes meme apres un second impact")
	check(not sim.has_bad_number(), "deux impacts enchaines ne doivent rien casser")
	done()


## With no gravity there is nothing feeding the panel, so the only thing that can
## make its energy rise is the solver inventing it. Position based constraints
## cannot, by construction, and this test is what says so out loud: if it ever
## fails, every clamp in the module is papering over a divergence.
func test_energie_decroit() -> void:
	var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 0.0, 0.0)
	sim.impulse(Vector3(0.0, 1.05, 0.0), Vector3(0.0, 0.0, -1.0), 28.0)
	var injected := sim.kinetic_energy()

	var window_early := 0.0
	var window_middle := 0.0
	var window_late := 0.0
	var peak := 0.0
	for s in 400:
		sim.step()
		var e := sim.kinetic_energy()
		if e > peak:
			peak = e
		if s < 50:
			window_early += e
		elif s >= 150 and s < 200:
			window_middle += e
		elif s >= 350:
			window_late += e

	check(injected > 0.0, "l'impulsion doit bien injecter de l'energie")
	check(window_middle < window_early, "l'energie doit decroitre entre le debut et le milieu")
	check(window_late < window_middle, "l'energie doit continuer a decroitre jusqu'a la fin")
	check(window_late < window_early * 0.01, "au bout de 6 s il ne doit presque plus rien rester")
	# The small allowance covers the immediate dent the impulse applies: that is
	# stored as potential energy in the stretched springs and part of it becomes
	# kinetic on the first steps. Anything beyond it would be the solver creating
	# energy out of nothing, which is the one thing this solver must never do.
	check(
		peak < injected * 1.2,
		"l'energie ne doit jamais depasser ce qui a ete injecte (%f contre %f)" % [peak, injected]
	)
	check(not sim.has_bad_number(), "pas de valeur invalide pendant la dissipation")
	done()


## "Un boulet dechire le filet, un tir mou le froisse a peine", says the brief.
## The peak bulge has to be a real function of the impact speed, and monotone, or
## every goal looks the same.
func test_bosse_suit_la_vitesse() -> void:
	var speeds: PackedFloat32Array = [5.0, 12.0, 24.0, 34.0]
	var peaks: PackedFloat32Array = PackedFloat32Array()

	for speed in speeds:
		var sim := NetSim.new(COLS, ROWS, WIDTH, HEIGHT, 1.6, NetSim.RECOVERY)
		sim.impulse(Vector3(0.0, 1.05, 0.0), Vector3(0.0, 0.0, -1.0), speed)
		var worst := 0.0
		for _s in 60:
			sim.step()
			worst = maxf(worst, sim.bulge())
		peaks.append(worst)

	check(peaks[0] < 0.15, "un tir a 5 m/s ne doit que froisser le filet (%f m)" % peaks[0])
	check(peaks[3] > 0.30, "un tir a 34 m/s doit vraiment le dechirer (%f m)" % peaks[3])
	for n in 3:
		check(
			peaks[n + 1] > peaks[n] * 1.15,
			"la bosse doit croitre nettement avec la vitesse (%f puis %f)" % [peaks[n], peaks[n + 1]]
		)
	done()
