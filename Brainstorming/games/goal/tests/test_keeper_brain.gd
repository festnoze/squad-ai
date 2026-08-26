extends GoalTest
## KeeperBrain: reaction, allonge, arrets, determinisme.
##
## This suite does not check plumbing, it checks the DESIGN CLAIMS of section
## 2.12. The module is only worth anything if the following are all true at once:
##
##   - a keeper who waits cannot reach a well placed corner, at ANY level,
##   - a keeper who gambles correctly does reach a corner at chest height, and
##     comes within a fingertip of the TOP corner without ever taking it, so a
##     well struck lucarne stays the correct answer to any keeper in the game,
##   - a shot hit straight at him is saved at every level, and so is one a metre
##     to his side once he has committed to standing his ground,
##   - he blocks with the whole of himself, forearm and shin and chest included,
##   - reading the HEIGHT is a real skill with a real ladder, not a coin flip,
##   - the levels are a real ladder on reaction, speed, reach and save rate,
##   - the dive is a continuous motion out of the standing pose, never a teleport,
##   - AND the dive is continuous IN ITS TARGET as well as in time: moving the ball
##     a centimetre moves the keeper about a centimetre. That is what section 2.12
##     bought by dropping the (side, height) enum pair, and it is checked here
##     directly, because it is the one property a regression would silently undo,
##   - a ball moving 25 cm per physics step cannot tunnel through a glove,
##   - a seed replays identically, and different seeds really do spread.
##
## The geometric tests drive the ball along a straight chord rather than through
## Aero. That is deliberate: those claims are about the KEEPER, so the ball has
## to be a fixed, fully controlled input. Over the last two metres of a penalty a
## chord and the real flight differ by centimetres anyway. The perception tests,
## which are about reading a real flight, do go through Aero.

const _STEP := 1.0 / 120.0          # the project physics step
const _SHOT_SPEED := 28.0           # a proper penalty
## A corner that is out of reach unless the keeper has already left. x is well
## inside the post (3.66), y well under the bar (2.44): this is a good penalty,
## not a freak one.
const _CORNER := Vector3(2.95, 2.15, 0.0)
## The same corner at mid height. This one IS the reward for a correct gamble:
## going high costs a keeper his ground travel, going wide at chest height does
## not, so the two corners are not the same problem at all.
const _CORNER_MID := Vector3(2.95, 1.25, 0.0)
## Straight down the throat, chest high.
const _AT_KEEPER := Vector3(0.0, 1.05, 0.0)

const _LEVELS: PackedInt32Array = [0, 1, 2, 3]

## The dive target that means "standing still", used wherever the old suite asked
## for (SIDE_CENTRE, HEIGHT_MID). At t = 0 any target gives the standing pose.
const _HOME_TARGET := Vector3(0.0, 1.25, 0.0)
## A spread of dive targets covering the whole envelope, replacing the nine boxes
## of the old enum pair. Two of them sit BETWEEN the old height bands on purpose:
## those are exactly the poses the quantised version could not produce.
const _TARGETS: Array[Vector3] = [
	Vector3(-2.95, 2.10, 0.0), Vector3(-2.95, 1.25, 0.0), Vector3(-2.95, 0.35, 0.0),
	Vector3(-1.60, 1.70, 0.0), Vector3(-0.60, 0.80, 0.0),
	Vector3(0.0, 0.30, 0.0), Vector3(0.0, 1.25, 0.0), Vector3(0.0, 2.20, 0.0),
	Vector3(0.60, 1.05, 0.0), Vector3(1.60, 0.55, 0.0),
	Vector3(2.95, 0.35, 0.0), Vector3(2.95, 1.25, 0.0), Vector3(2.95, 2.10, 0.0),
]


func suite_name() -> String:
	return "KeeperBrain"


# =============================================================================
# Helpers
# =============================================================================

## One physics step of a straight chord from the penalty spot to `target`.
## Returns [{"t": float, "from": Vector3, "to": Vector3}, ...], carried a little
## past the goal line so the crossing step is complete.
func _chord(target: Vector3, speed: float) -> Array:
	var start: Vector3 = Field.SPOT
	var delta := target - start
	var total := delta.length()
	var dir := delta / total
	var flight := total / speed
	var steps: Array = []
	var t := 0.0
	while t < flight + 0.06:
		steps.append({
			"t": t,
			"from": start + dir * (speed * t),
			"to": start + dir * (speed * (t + _STEP)),
		})
		t += _STEP
	return steps


## Sweeps a whole flight against a keeper who commits at `commit_time` seconds
## relative to contact (negative means he left before the strike).
## Returns {"saved": bool, "distance": float} where distance is the closest the
## ball ever came to a limb, radius included.
func _sweep(level: int, target: Vector3, commit_time: float, steps: Array) -> Dictionary:
	var best := INF
	var saved := false
	for entry in steps:
		var step: Dictionary = entry
		var moment: float = step["t"]
		var dive_t := maxf(moment - commit_time, 0.0)
		var pose := KeeperBrain.dive_pose(target, dive_t, level)
		var distance := KeeperBrain.save_distance(pose, step["from"], step["to"])
		if distance < best:
			best = distance
		if distance < 0.0:
			saved = true
	return {"saved": saved, "distance": best}


func _is_finite_vec(v: Vector3) -> bool:
	return is_finite(v.x) and is_finite(v.y) and is_finite(v.z)


func _pose_is_finite(pose: Dictionary) -> bool:
	for key in ["centre", "glove_left", "glove_right", "boot_left", "boot_right"]:
		if not _is_finite_vec(pose[key]):
			return false
	return is_finite(pose["lean"]) and is_finite(pose["airborne"])


func _home_pose() -> Dictionary:
	return KeeperBrain.dive_pose(_HOME_TARGET, 0.0, 1)


## The crossing estimate a keeper of this level would hold after watching
## `observed` seconds of a flight that lands on `target` after `flight` seconds.
## Built from the module's own error model rather than from a made up number, so
## the level ladder in the perception is what drives the ladder in the saves.
func _estimate_at(target: Vector3, level: int, observed: float, flight: float, rng_seed: int) -> Dictionary:
	var remaining := maxf(flight - observed, 0.0)
	var sigma: float = KeeperBrain._estimate_error(level, observed, remaining)
	var rng := RandomNumberGenerator.new()
	rng.seed = rng_seed * 31 + 7
	return {
		"point": Vector3(
			target.x + rng.randfn(0.0, sigma),
			maxf(target.y + rng.randfn(0.0, sigma * 0.7), 0.0),
			0.0),
		"time": remaining,
		"error": sigma,
	}


## The reticle that aims at a world point. The mapping belongs to ShotModel, so
## it is inverted by bisection here rather than duplicated. aim_point is monotonic
## on each axis, which is what makes the bisection legitimate.
func _reticle_for(target: Vector3) -> Vector2:
	return Vector2(_solve_reticle(true, target.x), _solve_reticle(false, target.y))


func _solve_reticle(horizontal: bool, wanted: float) -> float:
	var low := -6.0
	var high := 6.0
	for _i in 40:
		var mid := (low + high) * 0.5
		var value: float = ShotModel.aim_point(Vector2(mid, 0.5)).x
		if not horizontal:
			value = ShotModel.aim_point(Vector2(0.0, mid)).y
		if value < wanted:
			low = mid
		else:
			high = mid
	return (low + high) * 0.5


# =============================================================================
# 1. The level ladder
# =============================================================================

func test_niveaux_progressent() -> void:
	eq(KeeperBrain.LEVEL_NAMES.size(), 4, "quatre niveaux nommes")
	for level in range(1, 4):
		check(KeeperBrain.reaction_time(level) < KeeperBrain.reaction_time(level - 1),
			"le niveau %d reagit plus vite que le %d" % [level, level - 1])
		check(KeeperBrain.dive_speed(level) > KeeperBrain.dive_speed(level - 1),
			"le niveau %d plonge plus vite que le %d" % [level, level - 1])
		check(KeeperBrain.reach(level) > KeeperBrain.reach(level - 1),
			"le niveau %d a plus d'allonge que le %d" % [level, level - 1])
		check(KeeperBrain.read_skill(level) > KeeperBrain.read_skill(level - 1),
			"le niveau %d lit mieux que le %d" % [level, level - 1])

	# The design says a better keeper gambles more intelligently, not more often.
	check(KeeperBrain.gamble_chance(3) < KeeperBrain.gamble_chance(0),
		"une legende parie moins souvent qu'un debutant")

	for level in _LEVELS:
		between(KeeperBrain.reaction_time(level), 0.12, 0.40, "temps de reaction plausible")
		between(KeeperBrain.dive_speed(level), 2.0, 8.0, "vitesse de plongeon plausible")
		between(KeeperBrain.reach(level), 0.6, 1.6, "allonge plausible")
		between(KeeperBrain.gamble_chance(level), 0.0, 1.0, "probabilite de pari bornee")
		between(KeeperBrain.read_skill(level), 0.0, 1.0, "qualite de lecture bornee")

	# Out of range levels are clamped, never crash and never return garbage.
	eq(KeeperBrain.reaction_time(-7), KeeperBrain.reaction_time(0), "niveau negatif ramene au debutant")
	eq(KeeperBrain.reach(99), KeeperBrain.reach(3), "niveau trop grand ramene a la legende")
	done()


# =============================================================================
# 2. The standing pose
# =============================================================================

func test_pose_de_repos_est_la_position_de_base() -> void:
	var home: Vector3 = Field.KEEPER_HOME
	var reference := _home_pose()

	for level in _LEVELS:
		for target in _TARGETS:
			var pose := KeeperBrain.dive_pose(target, 0.0, level)
			near_vec(pose["centre"], reference["centre"], 0.0001,
				"centre a t=0 identique quel que soit le plongeon choisi")
			near_vec(pose["glove_left"], reference["glove_left"], 0.0001,
				"gant gauche a t=0 identique (cible %v)" % target)
			near_vec(pose["glove_right"], reference["glove_right"], 0.0001,
				"gant droit a t=0 identique (cible %v)" % target)
			near_vec(pose["boot_left"], reference["boot_left"], 0.0001,
				"pied gauche a t=0 identique")
			near_vec(pose["boot_right"], reference["boot_right"], 0.0001,
				"pied droit a t=0 identique")
			near(pose["lean"], 0.0, 0.0001, "aucune inclinaison a t=0")
			near(pose["airborne"], 0.0, 0.0001, "au sol a t=0")

	# +X is the shooter's right, so it is the keeper's LEFT: glove_left lives on
	# the +X side. Everything downstream depends on that convention.
	var left: Vector3 = reference["glove_left"]
	var right: Vector3 = reference["glove_right"]
	check(left.x > home.x, "le gant gauche du gardien est du cote +X")
	check(right.x < home.x, "le gant droit du gardien est du cote -X")
	near(left.x + right.x, 2.0 * home.x, 0.0001, "stance symetrique")
	check(left.y > 0.6 and left.y < 1.4, "les gants sont a hauteur de hanche en position d'attente")
	near(float(reference["centre"].y), 0.98, 0.15, "bassin a hauteur humaine")
	done()


# =============================================================================
# 3. The dive is a motion, not a teleport
# =============================================================================

func test_pose_continue_et_bornee() -> void:
	var keys: PackedStringArray = ["centre", "glove_left", "glove_right", "boot_left", "boot_right"]
	var worst_jump := 0.0
	var worst_jump_key := ""
	var worst_reach := 0.0
	var worst_reach_key := ""
	var peak_airborne := 0.0

	for level in _LEVELS:
		for target in _TARGETS:
			var previous := KeeperBrain.dive_pose(target, 0.0, level)
			var t := _STEP
			while t <= 1.30:
				var pose := KeeperBrain.dive_pose(target, t, level)
				check(_pose_is_finite(pose), "aucun NaN dans la pose (t=%f)" % t)
				var centre: Vector3 = pose["centre"]
				for key in keys:
					var point: Vector3 = pose[key]
					var jump: float = point.distance_to(previous[key])
					if jump > worst_jump:
						worst_jump = jump
						worst_jump_key = "%s (n%d %v t=%.3f)" % [key, level, target, t]
					var span: float = point.distance_to(centre)
					if span > worst_reach:
						worst_reach = span
						worst_reach_key = "%s (n%d %v t=%.3f)" % [key, level, target, t]
					check(point.y > -0.001, "aucun membre ne passe sous la pelouse (%s)" % key)
				var air: float = pose["airborne"]
				peak_airborne = maxf(peak_airborne, air)
				between(air, 0.0, 1.0, "airborne borne a [0, 1]")
				between(float(pose["lean"]), -1.6, 1.6, "inclinaison bornee")
				check(centre.y > 0.15, "le bassin ne traverse pas la pelouse")
				previous = pose
				t += _STEP

	# One physics step at 120 Hz, so nothing may jump further than a fast limb
	# could travel in 8 ms. A teleport would blow straight through this.
	check(worst_jump < 0.12, "aucun saut de membre entre deux pas (max %f m sur %s)" % [worst_jump, worst_jump_key])
	# Every limb stays inside the reach envelope of the best keeper.
	check(worst_reach <= KeeperBrain.reach(3) + 0.001,
		"aucun membre ne depasse l'allonge (max %f m pour %f, sur %s)" % [worst_reach, KeeperBrain.reach(3), worst_reach_key])
	# And a full dive really does leave the ground.
	near(peak_airborne, 1.0, 0.02, "un vrai plongeon atteint le sommet de son arc")
	done()


## THE PROPERTY THE SIGNATURE CHANGE OF 2.12 WAS MADE FOR.
##
## The pose used to be quantised into three sides by three heights, so two balls
## 5 cm apart could produce dives 80 cm apart, and a keeper who had read the height
## to within a hand's width dived into the wrong band and missed as cleanly as one
## who had read it backwards. Now the pose is a continuous function of the target,
## and this test says so in the only way that cannot be faked: it walks the target
## across the whole mouth in 5 cm steps and checks the pose never jumps.
##
## It also checks the other half of the claim, which is that the dive actually
## FOLLOWS the target rather than merely varying smoothly with it: sliding the ball
## a metre sideways has to slide the leading glove most of a metre with it.
func test_le_plongeon_suit_la_cible_sans_marche() -> void:
	var when := 0.55
	var worst := 0.0
	var worst_at := ""

	for level in _LEVELS:
		for row in [0.25, 0.75, 1.25, 1.75, 2.25]:
			var previous := KeeperBrain.dive_pose(Vector3(-3.2, row, 0.0), when, level)
			var x := -3.15
			while x <= 3.2:
				var pose := KeeperBrain.dive_pose(Vector3(x, row, 0.0), when, level)
				for key in ["centre", "glove_left", "glove_right", "boot_left", "boot_right"]:
					var jump: float = (pose[key] as Vector3).distance_to(previous[key])
					if jump > worst:
						worst = jump
						worst_at = "%s (n%d x=%.2f y=%.2f)" % [key, level, x, row]
				previous = pose
				x += 0.05
	# 5 cm of ball may not move a limb more than 22 cm. The old quantised pose
	# would show a 0.9 m step here, which is the bug in one number, so the bar is
	# four times looser than the bug and still catches it. It is not tighter than
	# that because one honest amplification survives: near full stretch the lateral
	# half of the reach is sqrt(reach^2 - vertical^2), whose slope runs away as the
	# ball approaches the limit of the arm, so a ball 5 cm higher really does cost a
	# little over 5 cm of extra ground. That is geometry, not quantisation.
	check(worst < 0.22,
		"aucune marche dans la pose quand la cible glisse de 5 cm (max %.3f m sur %s)" % [worst, worst_at])

	worst = 0.0
	worst_at = ""
	for level in _LEVELS:
		for column in [-2.6, -1.0, 0.0, 1.0, 2.6]:
			var previous := KeeperBrain.dive_pose(Vector3(column, 0.10, 0.0), when, level)
			var y := 0.15
			while y <= 2.45:
				var pose := KeeperBrain.dive_pose(Vector3(column, y, 0.0), when, level)
				for key in ["centre", "glove_left", "glove_right", "boot_left", "boot_right"]:
					var jump: float = (pose[key] as Vector3).distance_to(previous[key])
					if jump > worst:
						worst = jump
						worst_at = "%s (n%d x=%.2f y=%.2f)" % [key, level, column, y]
				previous = pose
				y += 0.05
	check(worst < 0.22,
		"ni quand elle monte de 5 cm (max %.3f m sur %s)" % [worst, worst_at])

	# And the dive genuinely tracks the ball rather than just being smooth. Both
	# probes sit outside the reach of a standing keeper, so the body itself has to
	# move, which is the property that matters.
	for level in _LEVELS:
		var here := KeeperBrain.dive_pose(Vector3(1.6, 1.20, 0.0), 0.60, level)
		var there := KeeperBrain.dive_pose(Vector3(2.6, 1.20, 0.0), 0.60, level)
		var moved: float = (there["glove_left"] as Vector3).x - (here["glove_left"] as Vector3).x
		check(moved > 0.80,
			"niveau %d: un metre de ballon deplace le gant d'autant (%.2f m)" % [level, moved])
		var lower := KeeperBrain.dive_pose(Vector3(2.4, 0.45, 0.0), 0.60, level)
		var upper := KeeperBrain.dive_pose(Vector3(2.4, 1.85, 0.0), 0.60, level)
		var lifted: float = (upper["glove_left"] as Vector3).y - (lower["glove_left"] as Vector3).y
		check(lifted > 0.90,
			"niveau %d: et 1.4 m de hauteur leve le gant d'autant (%.2f m)" % [level, lifted])

	# The pose is a pure function of the target: the same target replays exactly.
	var a := KeeperBrain.dive_pose(Vector3(1.37, 1.62, 0.0), 0.42, 2)
	var b := KeeperBrain.dive_pose(Vector3(1.37, 1.62, 0.0), 0.42, 2)
	near_vec(a["glove_left"], b["glove_left"], 0.0, "la pose est deterministe")
	done()


func test_le_gant_arrive_en_dernier() -> void:
	# The signature of a real dive: the body is already travelling while the arm
	# is still folded, and the leading glove is the last thing to arrive. If the
	# glove led the body it would read as a lerp, not as a save.
	var level := 3
	var target := Vector3(2.60, 1.25, 0.0)
	var t_mid := 0.5 * KeeperBrain.extension_time(level)
	var pose := KeeperBrain.dive_pose(target, t_mid, level)
	var final_pose := KeeperBrain.dive_pose(target, 0.66, level)

	var centre: Vector3 = pose["centre"]
	var final_centre: Vector3 = final_pose["centre"]
	var home: Vector3 = Field.KEEPER_HOME
	var body_progress: float = (centre.x - home.x) / maxf(final_centre.x - home.x, 0.0001)

	var arm: float = (pose["glove_left"] as Vector3).distance_to(centre)
	var final_arm: float = (final_pose["glove_left"] as Vector3).distance_to(final_centre)
	var arm_progress := arm / maxf(final_arm, 0.0001)

	check(arm_progress < body_progress,
		"le bras est en retard sur le corps a mi plongeon (%f contre %f)" % [arm_progress, body_progress])

	# The body rolls into the dive before it is extended, and rolls the right way.
	var right_lean: float = pose["lean"]
	var left_lean: float = (KeeperBrain.dive_pose(Vector3(-2.60, 1.25, 0.0), t_mid, level))["lean"]
	check(right_lean > 0.3, "le corps s'incline vers +X en plongeant a droite")
	near(left_lean, -right_lean, 0.0001, "l'inclinaison est symetrique")

	# The push comes out of the standing foot: early in the dive the body has
	# barely moved but the pelvis has already loaded.
	var early := KeeperBrain.dive_pose(target, 0.05, level)
	var early_centre: Vector3 = early["centre"]
	check(early_centre.x - home.x < 0.10, "l'appui se charge avant que le corps parte")
	check(early_centre.y < float(_home_pose()["centre"].y), "le bassin s'affaisse pendant l'appui")
	done()


# =============================================================================
# 4. The central claim: waiting is not enough
# =============================================================================

func test_gardien_qui_attend_ne_prend_pas_la_lucarne() -> void:
	var steps := _chord(_CORNER, _SHOT_SPEED)
	check(steps.size() > 40, "la trajectoire est echantillonnee")

	for level in _LEVELS:
		# Best possible case for the waiting keeper: he reads the corner
		# perfectly, and moves the instant his reaction time is up. He still
		# cannot get there, and that is the whole point of the module.
		var result := _sweep(level, _CORNER, KeeperBrain.reaction_time(level), steps)
		check(not result["saved"],
			"niveau %d: attendre ne rattrape pas la lucarne" % level)
		check(float(result["distance"]) > 0.5,
			"niveau %d: et il en est loin, pas d'un cheveu (%f m)" % [level, result["distance"]])
	done()


func test_gardien_qui_parie_juste_prend_le_coin() -> void:
	# Same shot, same side, same keeper. The only thing that changes is that he
	# left before contact. A Pro or a Legende who guesses right gets to a corner
	# at mid height, and that save is what a correct gamble buys.
	var mid_steps := _chord(_CORNER_MID, _SHOT_SPEED)
	for level in [2, 3]:
		var saved := false
		var best := INF
		var early := 0.10
		while early <= 0.24:
			var result := _sweep(level, _CORNER_MID, -early, mid_steps)
			best = minf(best, float(result["distance"]))
			if bool(result["saved"]):
				saved = true
			early += 0.01
		check(saved, "niveau %d: un pari correct sort l'arret sur un coin (meilleure distance %f)"
			% [level, best])

	# The TOP corner is a different matter, and this is the promise the whole
	# balance rests on: going up costs ground, so even a Legende who has guessed
	# the side AND the height correctly and left before contact arrives a
	# fingertip short of the angle of the bar. Close enough to be a spectacle,
	# never close enough to be a save. A well struck lucarne stays unstoppable.
	var top_steps := _chord(_CORNER, _SHOT_SPEED)
	var top_best := INF
	var top_saved := false
	var lead := 0.10
	while lead <= 0.24:
		var attempt := _sweep(3, _CORNER, -lead, top_steps)
		top_best = minf(top_best, float(attempt["distance"]))
		if bool(attempt["saved"]):
			top_saved = true
		lead += 0.01
	check(not top_saved, "meme un pari parfait ne prend pas la lucarne")
	check(top_best < 0.60, "mais il en passe tout pres (%f m), sinon ce n'est plus un spectacle" % top_best)

	# And the same gamble in the WRONG direction leaves an open goal. That swing
	# is the drama of the mode and it is not damped.
	var wrong := _sweep(3, Vector3(-_CORNER.x, _CORNER.y, 0.0), -0.20, top_steps)
	check(not wrong["saved"], "un pari du mauvais cote laisse le but grand ouvert")
	check(float(wrong["distance"]) > 2.0, "et tres largement (%f m)" % wrong["distance"])
	done()


func test_tir_sur_le_gardien_toujours_arrete() -> void:
	var steps := _chord(_AT_KEEPER, 24.0)

	for level in _LEVELS:
		var waiting := _sweep(level, _AT_KEEPER, KeeperBrain.reaction_time(level), steps)
		check(waiting["saved"], "niveau %d: un tir sur le gardien est arrete" % level)

	# Stronger still: he does not even have to move. A keeper rooted to his line
	# blocks a ball hit at his chest, which is why shooting at him is never a
	# tactic.
	var rooted := true
	var home_pose := _home_pose()
	var touched := false
	for entry in steps:
		var step: Dictionary = entry
		if KeeperBrain.save_distance(home_pose, step["from"], step["to"]) < 0.0:
			touched = true
	check(touched, "meme immobile, il bloque un ballon frappe dans son plastron")
	check(rooted, "sentinelle de lisibilite du test")
	done()


## A keeper is not two glove points and a pelvis sphere. He blocks with a
## forearm, a shin, a trailing leg and a chest, and the contact test has to know
## it, otherwise a ball at the chest of a standing man passes between a pelvis at
## 0.98 m and two gloves at 1.02 m without touching anything at all.
func test_enveloppe_de_parade_couvre_tout_le_corps() -> void:
	var home := _home_pose()

	# The hole this envelope was built to close.
	var chest := Vector3(0.22, 1.30, 0.0)
	var chest_hit := KeeperBrain.try_save(home, chest + Vector3(0.0, 0.0, 0.22), chest - Vector3(0.0, 0.0, 0.22))
	check(bool(chest_hit["saved"]), "un ballon en plein plastron est bloque, meme immobile")
	eq(chest_hit["limb"], "centre", "et c'est bien le corps qui le bloque")

	# The forearm is part of the keeper: mid dive, a ball out along the leading
	# arm is a save, credited to the glove on that side. The sample is taken well
	# past halfway on purpose, because nearer the body the arm runs inside the
	# trunk capsule and the chest is then the honest answer.
	var pose := KeeperBrain.dive_pose(Vector3(2.60, 1.25, 0.0), 0.50, 3)
	var body: Vector3 = pose["centre"]
	var glove: Vector3 = pose["glove_left"]
	var forearm: Vector3 = body.lerp(glove, 0.88)
	var arm_hit := KeeperBrain.try_save(pose, forearm + Vector3(0.0, 0.0, 0.22), forearm - Vector3(0.0, 0.0, 0.22))
	check(bool(arm_hit["saved"]), "un ballon sur l'avant bras est arrete, pas seulement sur le gant")
	eq(arm_hit["limb"], "glove_left", "et il est credite au gant de ce cote la")

	# So is the trailing leg.
	var boot: Vector3 = pose["boot_right"]
	var shin: Vector3 = body.lerp(boot, 0.82)
	var leg_hit := KeeperBrain.try_save(pose, shin + Vector3(0.0, 0.0, 0.22), shin - Vector3(0.0, 0.0, 0.22))
	check(bool(leg_hit["saved"]), "un ballon sur la jambe arriere est arrete")
	eq(leg_hit["limb"], "boot_right", "credite au pied de ce cote la")

	# Only the five names of the contract ever come back, whatever was touched.
	var allowed: PackedStringArray = ["glove_left", "glove_right", "boot_left", "boot_right", "centre", ""]
	var names_ok := true
	for level in _LEVELS:
		for target in _TARGETS:
			var probe := KeeperBrain.dive_pose(target, 0.40, level)
			var probe_centre: Vector3 = probe["centre"]
			for dx in [-1.2, -0.6, 0.0, 0.6, 1.2]:
				for dy in [-0.7, 0.0, 0.7]:
					var at := probe_centre + Vector3(dx, dy, 0.0)
					var out := KeeperBrain.try_save(probe, at + Vector3(0.0, 0.0, 0.2), at - Vector3(0.0, 0.0, 0.2))
					if not allowed.has(String(out["limb"])):
						names_ok = false
	check(names_ok, "try_save ne rend jamais un nom de membre hors contrat")

	# And the envelope is an envelope, not a wall: two metres away is two metres
	# away, whatever limb you draw between the joints.
	var far := body + Vector3(2.4, 0.0, 0.0)
	check(not bool(KeeperBrain.try_save(pose, far + Vector3(0.0, 0.0, 0.2), far - Vector3(0.0, 0.0, 0.2))["saved"]),
		"un ballon a 2.4 m du corps n'est pas arrete")
	check(KeeperBrain.save_distance(pose, far + Vector3(0.0, 0.0, 0.2), far - Vector3(0.0, 0.0, 0.2)) > 0.8,
		"et il en est loin")
	done()


## A keeper who correctly reads "he is going down the middle" must be able to do
## something about it. He does it by spreading, not by standing to attention.
func test_blocage_central_fait_une_etoile() -> void:
	var pose := KeeperBrain.dive_pose(_HOME_TARGET, 0.55, 3)
	var centre: Vector3 = pose["centre"]
	var gl: Vector3 = pose["glove_left"]
	var gr: Vector3 = pose["glove_right"]
	near(centre.x, 0.0, 0.0001, "un blocage central ne se deplace pas lateralement")
	check(gl.x - centre.x > 0.8, "le gant du cote +X part vraiment sur le cote (%f)" % (gl.x - centre.x))
	check(centre.x - gr.x > 0.8, "et celui du cote -X part de l'autre (%f)" % (centre.x - gr.x))

	# Feet apart too, which is what covers a ball rolled along the turf beside him.
	var low := KeeperBrain.dive_pose(Vector3(0.0, 0.42, 0.0), 0.55, 3)
	var bl: Vector3 = low["boot_left"]
	var br: Vector3 = low["boot_right"]
	check(bl.x - br.x > 0.45, "les appuis s'ecartent sur un blocage bas (%f)" % (bl.x - br.x))

	# The consequence, stated as a save on a real chord: a keeper who committed to
	# standing his ground now blocks a ball a metre to his side at mid height.
	# Committed, note, not waiting: the star takes half a second to open, so a
	# keeper who only reacts to the flight is still beaten by it. That is the
	# whole reason the module gambles.
	var near_steps := _chord(Vector3(1.02, 1.15, 0.0), 26.0)
	var blocked := _sweep(3, _HOME_TARGET, -0.15, near_steps)
	check(blocked["saved"],
		"un ballon a un metre du gardien reste au milieu est bloque (%f m)" % blocked["distance"])
	# And spreading is not diving: he gets there even starting only at his
	# reaction time, because holding the middle costs him no travel at all. That
	# asymmetry is deliberate. It is what makes standing your ground a real
	# option against a shot the read puts near the middle, instead of a polite way
	# of conceding.
	var reactive := _sweep(3, _HOME_TARGET, KeeperBrain.reaction_time(3), near_steps)
	check(bool(reactive["saved"]),
		"et il y arrive meme en partant a son temps de reaction (%f m)" % reactive["distance"])

	# But a star is not a wall. The corner is still bought by placing the ball,
	# and no amount of spreading covers it from the middle of the line.
	var corner_steps := _chord(_CORNER, _SHOT_SPEED)
	var stretched := _sweep(3, Vector3(0.0, 2.10, 0.0), -0.22, corner_steps)
	check(not stretched["saved"], "la lucarne reste hors de portee d'un gardien reste au milieu")
	check(float(stretched["distance"]) > 1.0, "et tres largement (%f m)" % stretched["distance"])
	done()


## Picking the right HEIGHT matters as much as picking the right side: a dive to
## the correct corner at the wrong height goes straight past the ball. The module
## used to have no height cue at all and read the height off the power alone,
## which meant every hard shot was read as low and every top corner was conceded
## for free. lift_hint is the honest fix, and this is its ladder.
func test_lecture_de_la_hauteur() -> void:
	var trials := 40
	var aims := 12
	var total := aims * trials
	var high_reads := PackedInt32Array([0, 0, 0, 0])
	var low_reads := PackedInt32Array([0, 0, 0, 0])

	for level in _LEVELS:
		for i in aims:
			var ax := -0.72 + 1.44 * float(i) / float(aims - 1)
			var high_cues := ShotModel.tell_cues(Vector2(ax, 0.72), 0.90, 0.0, 0.0, 0, level)
			var low_cues := ShotModel.tell_cues(Vector2(ax, 0.07), 0.90, 0.0, 0.0, 0, level)
			check(high_cues.has("lift_hint"), "tell_cues fournit l'indice de hauteur")
			for s in trials:
				var rng_seed := s * 31 + i * 7919 + level
				if int(KeeperBrain.read_cues(high_cues, level, rng_seed)["height"]) == KeeperBrain.HEIGHT_HIGH:
					high_reads[level] += 1
				if int(KeeperBrain.read_cues(low_cues, level, rng_seed)["height"]) == KeeperBrain.HEIGHT_LOW:
					low_reads[level] += 1

	check(high_reads[3] > high_reads[0],
		"une legende lit une frappe haute bien mieux qu'un debutant (%d contre %d)" % [high_reads[3], high_reads[0]])
	check(low_reads[3] > low_reads[0],
		"et une frappe au ras du sol aussi (%d contre %d)" % [low_reads[3], low_reads[0]])
	check(float(high_reads[3]) / float(total) > 0.50,
		"une legende part en haut sur une frappe haute plus d'une fois sur deux (%.2f)"
			% (float(high_reads[3]) / float(total)))
	check(float(low_reads[3]) / float(total) > 0.60,
		"et il reste bas sur une frappe basse (%.2f)" % (float(low_reads[3]) / float(total)))

	# Without the cue the keeper is blind to the height again, which is exactly
	# the state the module was in before and what this test protects against.
	var blind_high := 0
	for i in aims:
		var ax := -0.72 + 1.44 * float(i) / float(aims - 1)
		var blind_cues: Dictionary = ShotModel.tell_cues(Vector2(ax, 0.72), 0.90, 0.0, 0.0, 0, 3)
		blind_cues.erase("lift_hint")
		for s in trials:
			if int(KeeperBrain.read_cues(blind_cues, 3, s * 31 + i * 7919 + 3)["height"]) == KeeperBrain.HEIGHT_HIGH:
				blind_high += 1
	check(blind_high * 2 < high_reads[3],
		"sans indice de hauteur il redevient aveugle (%d contre %d)" % [blind_high, high_reads[3]])
	done()


## The rebalance itself, stated where it can be regression tested.
##
## Everything above checks one mechanism at a time. This one puts the whole chain
## together on a spread of placements (body language -> read -> dive choice ->
## dive -> contact) and asserts the two properties the difficulty of the game
## rests on: the ladder really is a ladder, and the top corner really is still
## the correct answer to the best keeper in the game.
##
## The ball is a straight chord rather than a real Aero flight, for the reason
## given at the top of the file: this claim is about the KEEPER, so the ball has
## to be a fully controlled input. tests/balance_probe.gd measures the same thing
## against the real flight, the real ball and the real orchestrator.
##
## One thing this deliberately does NOT model: the dive is started at the raw
## `commit_time` the read came back with, whereas the real body waits for the last
## responsible moment (see 2.19) and usually leaves later than that. So the rates
## below are the BRAIN measured on its own, and they are lower than the game's.
## That is the point of having both this and the probe.
func test_le_niveau_change_vraiment_le_taux_d_arret() -> void:
	# A spread over the whole mouth rather than a list of corners: a corner only
	# sample would sit at zero for every level and could not show a ladder at all.
	# The first two are the top corners, which the corner promise below reads.
	var targets: Array[Vector3] = [
		Vector3(-2.90, 2.05, 0.0), Vector3(2.90, 2.05, 0.0),
		Vector3(-2.90, 1.20, 0.0), Vector3(2.90, 0.35, 0.0),
		Vector3(-1.90, 1.60, 0.0), Vector3(1.90, 0.70, 0.0),
		Vector3(-1.10, 1.30, 0.0), Vector3(1.10, 0.60, 0.0),
		Vector3(0.00, 1.10, 0.0), Vector3(0.00, 2.00, 0.0),
	]
	var seeds := 14
	var attempts := targets.size() * seeds
	var saves := PackedInt32Array([0, 0, 0, 0])
	var corner_saves := PackedInt32Array([0, 0, 0, 0])
	var corner_attempts: int = 2 * seeds

	for level in _LEVELS:
		for i in targets.size():
			var target: Vector3 = targets[i]
			var steps := _chord(target, 27.0)
			var cues := ShotModel.tell_cues(_reticle_for(target), 0.88, 0.0, 0.0, 0, level)
			var flight := (target - Field.SPOT).length() / 27.0
			for s in seeds:
				var rng_seed := s * 97 + i * 7919 + level * 31
				var guess := KeeperBrain.read_cues(cues, level, rng_seed)
				var commit_time := float(guess["commit_time"])
				# A keeper who did NOT commit before the strike has watched part of
				# the flight by the time he moves, so he gets the estimate the
				# module's own perception model says he would have. Handing him an
				# empty one instead would measure the pre strike hunch alone and
				# hide the whole reactive half of the module.
				var estimate := {}
				if commit_time > 0.0:
					estimate = _estimate_at(target, level, commit_time, flight, rng_seed)
				var dive := KeeperBrain.choose_dive(estimate, guess, level, commit_time)
				var result := _sweep(level, dive["target"], commit_time, steps)
				if bool(result["saved"]):
					saves[level] += 1
					if i < 2:
						corner_saves[level] += 1

	# A ladder, not a plateau. The old module saved 3 % at every level, which is
	# what this test exists to stop happening again.
	# This sample is deliberately harsher than the one tests/balance_probe.gd
	# draws (six of its ten placements are hard against a post), so the absolute
	# rates read lower here. What matters is the shape. Adjacent levels are only
	# asked not to go backwards, because 140 attempts cannot resolve a five point
	# difference; the two step gaps are asked to be real.
	check(saves[3] > saves[2], "une legende arrete plus qu'un pro (%d contre %d)" % [saves[3], saves[2]])
	check(saves[3] > saves[1], "et bien plus qu'un confirme (%d contre %d)" % [saves[3], saves[1]])
	check(saves[2] > saves[0], "un pro arrete plus qu'un debutant (%d contre %d)" % [saves[2], saves[0]])
	check(saves[3] > saves[0] * 2,
		"l'ecart du haut au bas de l'echelle est massif (%d contre %d)" % [saves[3], saves[0]])
	# Absolute bands, not just an ordering. They are pulled up close to what the
	# module actually does now (measured by tests/balance_probe.gd on its stress
	# sample) so that a regression which quietly halves the save rate again fails
	# here instead of passing on a comfortable ordering test.
	check(float(saves[3]) / float(attempts) > 0.42,
		"une legende est un vrai adversaire (%.2f)" % (float(saves[3]) / float(attempts)))
	check(float(saves[0]) / float(attempts) < 0.30,
		"un debutant reste battable (%.2f)" % (float(saves[0]) / float(attempts)))

	# The promise that must survive the whole rebalance.
	check(float(corner_saves[3]) / float(corner_attempts) < 0.15,
		"la lucarne bien frappee bat encore une legende (%d arrets sur %d)"
			% [corner_saves[3], corner_attempts])
	check(corner_saves[0] <= corner_saves[3],
		"et elle bat aussi tous les autres niveaux")
	done()


# =============================================================================
# 5. Perception
# =============================================================================

func test_estimation_converge() -> void:
	var start: Vector3 = Field.SPOT
	var velocity := (_CORNER - start).normalized() * _SHOT_SPEED
	var spin := Vector3(0.0, 40.0, 0.0)

	for level in _LEVELS:
		var early := KeeperBrain.estimate_cross(start, velocity, spin, level, 0.02, 4242)
		var late := KeeperBrain.estimate_cross(start, velocity, spin, level, 0.20, 4242)
		check(float(early["error"]) > float(late["error"]),
			"niveau %d: l'estimation se resserre avec le temps de vol observe" % level)
		check(float(early["error"]) > 0.5,
			"niveau %d: apres 20 ms l'estimation ne vaut rien (%f m)" % [level, early["error"]])
		check(float(late["error"]) < 0.30,
			"niveau %d: apres 200 ms elle est bonne (%f m)" % [level, late["error"]])
		check(float(late["time"]) > 0.0, "il reste du vol a courir")
		check(_is_finite_vec(late["point"]), "point estime fini")

	# A better reader is never worse at the same instant.
	var observed := 0.08
	var previous := KeeperBrain._estimate_error(0, observed, 0.30)
	for level in range(1, 4):
		var current := KeeperBrain._estimate_error(level, observed, 0.30)
		check(current < previous, "niveau %d lit plus finement que le precedent" % level)
		previous = current

	# The error grows with how much flight is left to extrapolate.
	check(KeeperBrain._estimate_error(2, 0.10, 0.40) > KeeperBrain._estimate_error(2, 0.10, 0.10),
		"extrapoler plus loin coute plus cher")

	# A ball that is not going towards the goal yields no usable estimate.
	var away := KeeperBrain.estimate_cross(start, Vector3(0.0, 4.0, 6.0), Vector3.ZERO, 2, 0.2, 7)
	near(float(away["time"]), -1.0, 0.0001, "aucun temps d'arrivee pour un ballon qui s'eloigne")
	done()


func test_estimation_deterministe_et_dispersee() -> void:
	var start: Vector3 = Field.SPOT
	var velocity := (_CORNER - start).normalized() * _SHOT_SPEED

	var a := KeeperBrain.estimate_cross(start, velocity, Vector3.ZERO, 2, 0.05, 991)
	var b := KeeperBrain.estimate_cross(start, velocity, Vector3.ZERO, 2, 0.05, 991)
	near_vec(a["point"], b["point"], 0.0, "meme graine, meme estimation")
	near(float(a["error"]), float(b["error"]), 0.0, "meme graine, meme incertitude")

	var different := KeeperBrain.estimate_cross(start, velocity, Vector3.ZERO, 2, 0.05, 992)
	check((a["point"] as Vector3).distance_to(different["point"]) > 0.001,
		"une autre graine donne une autre lecture")

	# Real spread: some seeds read it left of the truth, some right. Without that
	# every keeper of a given level would dive identically and the mode would be
	# a single scripted animation.
	var truth := KeeperBrain.estimate_cross(start, velocity, Vector3.ZERO, 3, 9.0, 1)
	var lefts := 0
	var rights := 0
	var spread := 0.0
	for s in range(60):
		var guess := KeeperBrain.estimate_cross(start, velocity, Vector3.ZERO, 1, 0.06, s * 7 + 3)
		var point: Vector3 = guess["point"]
		check(_is_finite_vec(point), "estimation finie pour la graine %d" % s)
		var delta: float = point.x - (truth["point"] as Vector3).x
		spread = maxf(spread, absf(delta))
		if delta < 0.0:
			lefts += 1
		else:
			rights += 1
	check(lefts > 6, "certaines lectures partent a gauche de la verite (%d)" % lefts)
	check(rights > 6, "d'autres a droite (%d)" % rights)
	check(spread > 0.2, "la dispersion est reelle (%f m)" % spread)
	done()


# =============================================================================
# 6. Contact
# =============================================================================

func test_arret_sans_traversee() -> void:
	var pose := KeeperBrain.dive_pose(Vector3(2.60, 1.25, 0.0), 0.45, 3)
	var glove: Vector3 = pose["glove_left"]

	# A ball at 30 m/s covers 25 cm in a physics step. Put the glove exactly in
	# the middle of that step: an endpoint only test would see 12.5 cm at each
	# end and call it a miss on a swept test error, so this is the tunnelling
	# guard the contract asks for.
	var half := 0.5 * 30.0 * _STEP
	var quick := KeeperBrain.try_save(pose, glove + Vector3(0.0, 0.0, half), glove - Vector3(0.0, 0.0, half))
	check(quick["saved"], "un ballon a 30 m/s passant par le gant est capte")
	eq(quick["limb"], "glove_left", "et c'est bien le gant qui l'a pris")
	near(KeeperBrain.save_distance(pose, glove + Vector3(0.0, 0.0, half), glove - Vector3(0.0, 0.0, half)),
		-KeeperBrain.GLOVE_RADIUS, 0.0001, "distance d'arret egale au rayon du gant")

	# Now a step four times longer than the glove is wide, with BOTH endpoints
	# clearly outside it. Only a real segment test catches this one.
	var far := 0.32
	var tunnel := KeeperBrain.try_save(pose, glove + Vector3(0.0, 0.0, far), glove - Vector3(0.0, 0.0, far))
	check(tunnel["saved"], "un pas de %f m ne traverse pas le gant" % (2.0 * far))
	check((glove.distance_to(glove + Vector3(0.0, 0.0, far))) > KeeperBrain.GLOVE_RADIUS,
		"les deux extremites du pas sont pourtant hors du gant")

	# A ball that genuinely misses is not saved, and reports nothing touched.
	var wide := KeeperBrain.try_save(pose, glove + Vector3(1.4, 0.0, half), glove + Vector3(1.4, 0.0, -half))
	check(not wide["saved"], "un ballon qui passe a 1.4 m n'est pas arrete")
	eq(wide["limb"], "", "et aucun membre n'est credite")
	check(KeeperBrain.save_distance(pose, glove + Vector3(1.4, 0.0, half), glove + Vector3(1.4, 0.0, -half)) > 0.0,
		"la distance d'arret reste positive")
	done()


func test_normale_ecarte_du_membre() -> void:
	var pose := KeeperBrain.dive_pose(Vector3(-2.40, 0.42, 0.0), 0.40, 2)
	var glove: Vector3 = pose["glove_right"]

	# Clip the top of the glove: the deflection has to send the ball upwards.
	var offset := Vector3(0.0, KeeperBrain.GLOVE_RADIUS * 0.6, 0.0)
	var from := glove + offset + Vector3(0.0, 0.0, 0.14)
	var to := glove + offset - Vector3(0.0, 0.0, 0.14)
	var hit := KeeperBrain.try_save(pose, from, to)
	check(hit["saved"], "l'effleurement du dessus du gant est un arret")
	eq(hit["limb"], "glove_right", "membre correctement identifie")

	var normal: Vector3 = hit["normal"]
	near(normal.length(), 1.0, 0.0001, "la normale est unitaire")
	var contact: Vector3 = hit["point"]
	check(normal.dot(contact - glove) > 0.0, "la normale s'ecarte du membre touche")
	check(normal.y > 0.5, "un ballon frole par le dessus est devie vers le haut")

	# Dead centre of a limb still yields a usable normal rather than a zero vector.
	var dead := KeeperBrain.try_save(pose, glove + Vector3(0.0, 0.0, 0.1), glove - Vector3(0.0, 0.0, 0.1))
	near((dead["normal"] as Vector3).length(), 1.0, 0.0001, "normale utilisable au centre exact du gant")

	# save_distance and try_save must agree: one is the predicate of the other.
	for dx in [0.0, 0.10, 0.16, 0.30, 1.0]:
		var a := glove + Vector3(dx, 0.0, 0.2)
		var b := glove + Vector3(dx, 0.0, -0.2)
		var d := KeeperBrain.save_distance(pose, a, b)
		eq(KeeperBrain.try_save(pose, a, b)["saved"], d < 0.0,
			"try_save est exactement le predicat de save_distance (dx=%f)" % dx)
	done()


## A save is not one outcome, it is two, and the difference is what the player
## sees: the ball is either gathered into the gloves or pushed away. This checks
## the rule that decides between them, which is the whole of catch_quality.
func test_prise_de_balle_ou_repousse() -> void:
	var pose := KeeperBrain.dive_pose(Vector3(2.60, 1.25, 0.0), 0.45, 3)
	var glove: Vector3 = pose["glove_left"]

	# The window shrinks with speed, never inverts, and shuts completely at the
	# top of the range. Those three properties are what the rule rests on.
	near(KeeperBrain.catch_window(0.0), KeeperBrain.GLOVE_RADIUS, 0.0001,
		"un ballon lent se prend avec tout le gant")
	near(KeeperBrain.catch_window(KeeperBrain.CATCH_SPEED_EASY), KeeperBrain.GLOVE_RADIUS, 0.0001,
		"la fenetre est encore entiere a la vitesse facile")
	eq(KeeperBrain.catch_window(KeeperBrain.CATCH_SPEED_MAX), 0.0,
		"au dela de la vitesse maximale plus rien ne se garde")
	eq(KeeperBrain.catch_window(999.0), 0.0, "et cela reste vrai bien au dela")
	var previous := KeeperBrain.GLOVE_RADIUS + 1.0
	for i in 40:
		var speed := float(i) * 1.0
		var window := KeeperBrain.catch_window(speed)
		check(window <= previous + 0.0001,
			"la fenetre de prise ne remonte jamais avec la vitesse (%f m/s)" % speed)
		check(window >= 0.0, "la fenetre de prise n'est jamais negative (%f m/s)" % speed)
		previous = window
	eq(KeeperBrain.catch_window(NAN), 0.0,
		"une vitesse absurde ferme la fenetre au lieu de l'ouvrir")
	eq(KeeperBrain.catch_window(-5.0), 0.0, "une vitesse negative aussi")

	# Dead centre of the palm, slowly: held.
	var slow_from := glove + Vector3(0.0, 0.0, 0.10)
	var slow_to := glove - Vector3(0.0, 0.0, 0.10)
	var slow := KeeperBrain.try_save(pose, slow_from, slow_to)
	check(slow["saved"], "le ballon lent est arrete")
	var held := KeeperBrain.catch_quality(pose, slow, 12.0)
	check(held["catch"], "un ballon lent en plein gant est capte")
	eq(held["hand"], "glove_left", "et la main qui le tient est nommee")
	check(float(held["grip"]) > 0.9, "la prise est franche au centre de la paume")

	# Same contact, at a speed nobody holds: parried.
	var fast := KeeperBrain.catch_quality(pose, slow, KeeperBrain.CATCH_SPEED_MAX + 5.0)
	check(not fast["catch"], "le meme contact a pleine vitesse n'est que repousse")
	eq(fast["hand"], "", "et personne ne le tient")

	# Fingertips rather than palm, at a middling speed: parried.
	var edge := KeeperBrain.GLOVE_RADIUS * 0.97
	var tip_from := glove + Vector3(edge, 0.0, 0.10)
	var tip_to := glove + Vector3(edge, 0.0, -0.10)
	var tip := KeeperBrain.try_save(pose, tip_from, tip_to)
	check(tip["saved"], "le bout des doigts arrete quand meme le ballon")
	check(not KeeperBrain.catch_quality(pose, tip, 26.0)["catch"],
		"mais un ballon rapide sur le bout des doigts n'est pas capte")
	check(KeeperBrain.catch_quality(pose, tip, 6.0)["catch"],
		"alors que le meme contact sur un ballon tres lent se garde")

	# The grip falls off from the middle of the palm outwards, and never leaves
	# [0, 1]: the audio and the celebration read it as a fraction.
	var last_grip := 2.0
	for k in 9:
		var dx := KeeperBrain.GLOVE_RADIUS * float(k) / 9.0
		var probe := KeeperBrain.try_save(pose,
			glove + Vector3(dx, 0.0, 0.10), glove + Vector3(dx, 0.0, -0.10))
		var quality := KeeperBrain.catch_quality(pose, probe, 8.0)
		var grip := float(quality["grip"])
		check(grip >= 0.0 and grip <= 1.0, "la prise reste dans [0, 1] (dx=%f)" % dx)
		check(grip <= last_grip + 0.0001, "la prise ne remonte pas en s'ecartant (dx=%f)" % dx)
		last_grip = grip

	# A boot, a shin or the trunk is a block, never a catch, however slow it is.
	var body: Vector3 = pose["centre"]
	var block := KeeperBrain.try_save(pose, body + Vector3(0.0, 0.0, 0.30), body - Vector3(0.0, 0.0, 0.30))
	check(block["saved"], "le corps arrete aussi le ballon")
	check(not KeeperBrain.catch_quality(pose, block, 4.0)["catch"],
		"un blocage du corps n'est jamais une prise de balle")
	var boot: Vector3 = pose["boot_right"]
	var kicked := KeeperBrain.try_save(pose, boot + Vector3(0.0, 0.0, 0.20), boot - Vector3(0.0, 0.0, 0.20))
	if bool(kicked["saved"]) and String(kicked["limb"]).begins_with("boot"):
		check(not KeeperBrain.catch_quality(pose, kicked, 4.0)["catch"],
			"un arret du pied n'est jamais une prise de balle")

	# A FOREARM block is credited to the glove it hangs off, and it still must not
	# be a catch: the contact point is re measured against the hand itself.
	var forearm := body.lerp(glove, 0.6)
	var arm_hit := KeeperBrain.try_save(pose,
		forearm + Vector3(0.0, 0.0, 0.16), forearm - Vector3(0.0, 0.0, 0.16))
	if bool(arm_hit["saved"]) and String(arm_hit["limb"]).begins_with("glove"):
		var arm_offset: float = (arm_hit["point"] as Vector3).distance_to(glove)
		if arm_offset > KeeperBrain.GLOVE_RADIUS:
			check(not KeeperBrain.catch_quality(pose, arm_hit, 5.0)["catch"],
				"un blocage de l'avant bras est credite au gant mais n'est pas une prise")

	# Nothing touched is nothing caught, and hostile input stays harmless.
	check(not KeeperBrain.catch_quality(pose, {"saved": false}, 5.0)["catch"],
		"pas de contact, pas de prise")
	check(not KeeperBrain.catch_quality(pose, {}, 5.0)["catch"],
		"un dictionnaire vide ne cree pas de prise")
	check(not KeeperBrain.catch_quality({}, slow, 5.0)["catch"],
		"une pose vide ne cree pas de prise")
	check(not KeeperBrain.catch_quality(pose,
		{"saved": true, "limb": "glove_left", "point": Vector3(NAN, 0.0, 0.0)}, 5.0)["catch"],
		"un point de contact non fini ne cree pas de prise")
	check(not KeeperBrain.catch_quality(pose,
		{"saved": true, "limb": "glove_left", "point": 3}, 5.0)["catch"],
		"un point de contact du mauvais type ne cree pas de prise")
	check(not KeeperBrain.catch_quality(pose, slow, NAN)["catch"],
		"une vitesse non finie ne cree pas de prise fantaisiste")
	done()


# =============================================================================
# 7. Reading the shooter
# =============================================================================

func test_lecture_des_indices() -> void:
	var cues := {
		"run_angle": 0.4,
		"approach_speed": 0.8,
		"plant_offset": 0.7,
		"hip_yaw": 0.35,
		"feints": 0,
		"aim_hint": 0.85,
		"power_hint": 0.9,
	}

	var first := KeeperBrain.read_cues(cues, 2, 1234)
	var again := KeeperBrain.read_cues(cues, 2, 1234)
	eq(first["side"], again["side"], "meme graine, meme cote choisi")
	eq(first["commit"], again["commit"], "meme graine, meme decision de pari")
	near(float(first["commit_time"]), float(again["commit_time"]), 0.0, "meme graine, meme instant de depart")

	# A shooter leaning hard to +X is read correctly more often by a better keeper.
	var correct := PackedInt32Array([0, 0, 0, 0])
	var commits := PackedInt32Array([0, 0, 0, 0])
	var trials := 240
	for level in _LEVELS:
		for s in range(trials):
			var read := KeeperBrain.read_cues(cues, level, s * 31 + level)
			between(float(read["confidence"]), 0.0, 1.0, "confiance bornee")
			check(is_finite(float(read["commit_time"])), "instant de depart fini")
			if bool(read["commit"]):
				commits[level] += 1
				check(float(read["commit_time"]) < 0.0, "un pari part avant la frappe")
			else:
				near(float(read["commit_time"]), KeeperBrain.reaction_time(level), 0.0001,
					"sinon il part a son temps de reaction")
			if int(read["side"]) == KeeperBrain.SIDE_RIGHT:
				correct[level] += 1

	check(correct[3] > correct[0],
		"une legende lit le cote bien plus souvent qu'un debutant (%d contre %d)" % [correct[3], correct[0]])
	check(float(correct[3]) / float(trials) > 0.75, "et il se trompe rarement sur un indice aussi net")

	# gamble_chance is the CEILING, and on a tell this unmistakable the keeper
	# should be near it. What he must never do is exceed his own ladder.
	for level in _LEVELS:
		var rate := float(commits[level]) / float(trials)
		check(rate <= KeeperBrain.gamble_chance(level) + 0.05,
			"niveau %d: on ne parie jamais plus souvent que gamble_chance (%.2f contre %.2f)"
				% [level, rate, KeeperBrain.gamble_chance(level)])
		check(rate > KeeperBrain.gamble_chance(level) * 0.55,
			"niveau %d: mais sur un indice aussi net il en est proche (%.2f)" % [level, rate])

	# And the other half of "smarter, not more often": with nothing to read at
	# all he keeps his powder dry and stays on his feet, because a full length
	# dive on a hunch he never had covers three metres of ground and leaves
	# everything inside it wide open.
	var blank := {"run_angle": 0.0, "approach_speed": 0.5, "plant_offset": 0.0,
		"hip_yaw": 0.0, "feints": 0, "aim_hint": 0.0, "lift_hint": 0.0, "power_hint": 0.6}
	for level in _LEVELS:
		var blind_commits := 0
		for s in range(trials):
			if bool(KeeperBrain.read_cues(blank, level, s * 53 + level)["commit"]):
				blind_commits += 1
		var blind_rate := float(blind_commits) / float(trials)
		check(blind_rate < float(commits[level]) / float(trials),
			"niveau %d: sans indice il parie beaucoup moins (%.2f contre %.2f)"
				% [level, blind_rate, float(commits[level]) / float(trials)])
	done()


## The cues come from ShotModel.tell_cues and NOT from a hand written dictionary,
## because a feint works in two places at once and only the real chain has both:
## it degrades the FIDELITY of the tell inside tell_cues, and it shrinks the READ
## inside read_cues. Fed a hand built cue with a perfect aim_hint, a Legende now
## reads through two feints without blinking, which says nothing about feints and
## everything about the fixture.
func test_feintes_retardent_et_brouillent() -> void:
	var aim := _reticle_for(Vector3(2.60, 1.20, 0.0))
	var base: Dictionary = ShotModel.tell_cues(aim, 0.85, 0.0, 0.30, 0, 3)
	var feinted: Dictionary = ShotModel.tell_cues(aim, 0.85, 0.0, 0.30, 2, 3)

	var clean_confidence := 0.0
	var muddled_confidence := 0.0
	var clean_early := 0.0
	var muddled_early := 0.0
	var clean_gambles := 0
	var muddled_gambles := 0
	var clean_correct := 0
	var muddled_correct := 0
	var trials := 200

	for s in range(trials):
		var clean := KeeperBrain.read_cues(base, 3, s * 13 + 5)
		var muddled := KeeperBrain.read_cues(feinted, 3, s * 13 + 5)
		clean_confidence += float(clean["confidence"])
		muddled_confidence += float(muddled["confidence"])
		if int(clean["side"]) == KeeperBrain.SIDE_RIGHT:
			clean_correct += 1
		if int(muddled["side"]) == KeeperBrain.SIDE_RIGHT:
			muddled_correct += 1
		if bool(clean["commit"]):
			clean_gambles += 1
			clean_early += -float(clean["commit_time"])
		if bool(muddled["commit"]):
			muddled_gambles += 1
			muddled_early += -float(muddled["commit_time"])

	check(clean_gambles > 10 and muddled_gambles > 10, "assez de paris pour comparer")
	clean_early /= float(clean_gambles)
	muddled_early /= float(muddled_gambles)

	check(muddled_confidence < clean_confidence,
		"les feintes font baisser la confiance (%f contre %f)" % [muddled_confidence, clean_confidence])
	check(muddled_correct < clean_correct,
		"et brouillent la lecture du cote (%d contre %d)" % [muddled_correct, clean_correct])
	check(muddled_early < clean_early,
		"une feinte retient le gardien plus tard (%f s contre %f s avant la frappe)" % [muddled_early, clean_early])

	# And the sharpest consequence of all: a feint does not merely send him the
	# wrong way, it talks him out of committing at all. That is what makes a feint
	# a real counter to an early commitment rather than a cosmetic one.
	check(muddled_gambles < clean_gambles,
		"une feinte dissuade le gardien de partir (%d paris contre %d)"
			% [muddled_gambles, clean_gambles])
	check(float(clean_gambles) / float(trials) <= KeeperBrain.gamble_chance(3) + 0.05,
		"et sans feinte il ne depasse jamais son propre plafond de pari")
	done()


# =============================================================================
# 8. The decision
# =============================================================================

func test_choix_du_plongeon() -> void:
	var guess := {"side": KeeperBrain.SIDE_LEFT, "height": KeeperBrain.HEIGHT_LOW,
		"confidence": 0.8, "commit": true, "commit_time": -0.18}
	var sharp := {"point": Vector3(2.90, 2.10, 0.0), "time": 0.18, "error": 0.05}
	var blurry := {"point": Vector3(2.90, 2.10, 0.0), "time": 0.38, "error": 3.0}

	# Before contact he has watched nothing, so the hunch is all he has.
	var gamble := KeeperBrain.choose_dive(sharp, guess, 3, -0.18)
	check(bool(gamble["gambled"]), "un depart avant la frappe est un pari")
	eq(gamble["side"], KeeperBrain.SIDE_LEFT, "le pari suit l'intuition, pas la verite")
	eq(gamble["height"], KeeperBrain.HEIGHT_LOW, "hauteur du pari conforme a l'intuition")

	# After contact, with a sharp read, the eyes overrule the hunch.
	var read := KeeperBrain.choose_dive(sharp, guess, 3, 0.22)
	check(not bool(read["gambled"]), "un depart apres la frappe n'est pas un pari")
	eq(read["side"], KeeperBrain.SIDE_RIGHT, "une lecture nette renverse l'intuition")
	eq(read["height"], KeeperBrain.HEIGHT_HIGH, "et corrige aussi la hauteur")
	check((read["target"] as Vector3).distance_to(sharp["point"]) < 0.5,
		"la cible colle a l'estimation quand elle est nette")

	# With a worthless read the hunch stays in charge.
	var doubt := KeeperBrain.choose_dive(blurry, guess, 3, 0.05)
	eq(doubt["side"], KeeperBrain.SIDE_LEFT, "une lecture floue laisse l'intuition decider")

	# Targets are always inside a sane band and sit on the goal line.
	for elapsed in [-0.3, 0.0, 0.1, 0.5]:
		var out := KeeperBrain.choose_dive(sharp, guess, 1, elapsed)
		var target: Vector3 = out["target"]
		check(_is_finite_vec(target), "cible finie")
		between(target.x, -4.2, 4.2, "cible dans la largeur du but")
		between(target.y, 0.0, 2.8, "cible dans la hauteur du but")
		near(target.z, 0.0, 0.0001, "la cible est sur la ligne de but")

	# An empty estimate or an empty guess must not crash and must stay sane.
	var empty := KeeperBrain.choose_dive({}, {}, 2, 0.3)
	between(float(empty["side"]), -1.0, 1.0, "cote valide sans donnee")
	between(float(empty["height"]), 0.0, 2.0, "hauteur valide sans donnee")

	# The continuous hunch overrides the coarse corner when read_cues supplied one,
	# and it is what the dive is actually aimed at.
	var fine := guess.duplicate()
	fine["target"] = Vector3(1.42, 1.71, 0.0)
	var followed := KeeperBrain.choose_dive({}, fine, 3, -0.20)
	near_vec(followed["target"], Vector3(1.42, 1.71, 0.0), 0.0001,
		"un pari suit la cible continue et non le coin arrondi")
	eq(followed["side"], KeeperBrain.SIDE_RIGHT, "le cote rapporte reste la lecture grossiere de cette cible")
	done()


## The two numbers 2.12 exposes so the body can plan a dive instead of guessing
## when to leave. Both are physics, not tables: extension_time is the arm, and
## dive_time_needed is the longer of the arm and the ground.
func test_temps_necessaire_au_plongeon() -> void:
	for level in _LEVELS:
		var ext := KeeperBrain.extension_time(level)
		between(ext, 0.25, 0.70, "un bras sort en un temps plausible")
		# Nothing to travel: the arm alone decides, and a spread is quicker than a
		# full length dive because there is nowhere to go.
		var here := KeeperBrain.dive_time_needed(Vector3(0.0, 1.20, 0.0), 0.0, level)
		var post := KeeperBrain.dive_time_needed(Vector3(3.30, 1.20, 0.0), 0.0, level)
		check(here < ext, "tenir le milieu coute moins que l'extension complete (%f)" % here)
		check(post > here, "aller au poteau coute plus cher que rester chez soi")
		between(post, 0.20, 1.20, "et cela reste un temps de plongeon, pas un voyage")
		# Starting closer to the ball is cheaper. That is why the shuffle matters.
		var shifted := KeeperBrain.dive_time_needed(Vector3(3.30, 1.20, 0.0), 1.00, level)
		check(shifted < post, "partir de plus pres coute moins cher (%f contre %f)" % [shifted, post])
		# The angle of the bar is the expensive one, because going up costs ground.
		check(KeeperBrain.dive_time_needed(Vector3(3.00, 2.20, 0.0), 0.0, level)
			> KeeperBrain.dive_time_needed(Vector3(3.00, 1.20, 0.0), 0.0, level),
			"la lucarne coute plus cher que le meme coin a hauteur de poitrine")
		# Hostile inputs stay finite.
		check(is_finite(KeeperBrain.dive_time_needed(Vector3(NAN, NAN, NAN), NAN, level)),
			"temps fini sur une cible corrompue")

	# A better keeper needs less time for the same ball, which is the athletic half
	# of the ladder stated where it can be regression tested.
	var slow := KeeperBrain.dive_time_needed(Vector3(3.00, 1.20, 0.0), 0.0, 0)
	var quick := KeeperBrain.dive_time_needed(Vector3(3.00, 1.20, 0.0), 0.0, 3)
	check(quick < slow, "une legende met moins de temps qu'un debutant (%f contre %f)" % [quick, slow])
	done()


## The pre strike read now carries a CONTINUOUS point, and a point is only worth
## anything if it is calibrated: a hunch that says "chest high" has to come out at
## chest height and not half a goal above it. That calibration lives in two
## constants and it was wrong on the first attempt, so it is measured here end to
## end, straight through ShotModel.tell_cues, rather than asserted from the source.
func test_intuition_continue_est_calibree() -> void:
	var trials := 120
	for level in [2, 3]:
		for spot in [Vector3(-2.60, 0.55, 0.0), Vector3(0.0, 1.25, 0.0),
				Vector3(1.80, 1.95, 0.0), Vector3(2.90, 0.80, 0.0)]:
			var reticle := _reticle_for(spot)
			var cues := ShotModel.tell_cues(reticle, 0.88, 0.0, 0.0, 0, level)
			var mean_x := 0.0
			var mean_y := 0.0
			for s in trials:
				var read := KeeperBrain.read_cues(cues, level, s * 131 + 17)
				check(read.has("target"), "read_cues fournit une cible continue")
				var point: Vector3 = read["target"]
				check(_is_finite_vec(point), "cible finie")
				near(point.z, 0.0, 0.0001, "la cible est sur la ligne de but")
				mean_x += point.x
				mean_y += point.y
			mean_x /= float(trials)
			mean_y /= float(trials)
			check(absf(mean_x - spot.x) < 0.75,
				"niveau %d: l'intuition vise en moyenne le bon cote de %v (x=%.2f)" % [level, spot, mean_x])
			check(absf(mean_y - spot.y) < 0.45,
				"niveau %d: et la bonne hauteur (y=%.2f pour %.2f)" % [level, mean_y, spot.y])

	# It is a hunch, not a grid: two nearby aims give two nearby hunches, where the
	# old (side, height) pair snapped both onto the same corner.
	var spread := 0.0
	var previous := 0.0
	var x := -0.80
	var first := true
	while x <= 0.80:
		var cues := ShotModel.tell_cues(Vector2(x, 0.45), 0.88, 0.0, 0.0, 0, 3)
		var point: Vector3 = KeeperBrain.read_cues(cues, 3, 909)["target"]
		if not first:
			spread = maxf(spread, absf(point.x - previous))
		previous = point.x
		first = false
		x += 0.05
	check(spread > 0.02, "l'intuition bouge vraiment avec la visee (%f)" % spread)
	check(spread < 2.0, "sans sauter d'un poteau a l'autre pour 5 cm de visee (%f)" % spread)
	done()


# =============================================================================
# 9. Theatre on the line
# =============================================================================

func test_danse_sur_la_ligne() -> void:
	near(KeeperBrain.line_dance(0.0, 3, 5), 0.0, 0.0001, "immobile avant de commencer")
	near(KeeperBrain.line_dance(-1.0, 3, 5), 0.0, 0.0001, "aucun deplacement pour un temps negatif")

	var extremes := PackedFloat64Array([0.0, 0.0, 0.0, 0.0])
	for level in _LEVELS:
		var t := 0.0
		while t < 4.0:
			var x := KeeperBrain.line_dance(t, level, 77)
			check(is_finite(x), "position finie")
			between(x, -0.9, 0.9, "la danse reste dans les 90 cm autorises")
			extremes[level] = maxf(extremes[level], absf(x))
			t += 0.02
	check(extremes[3] > 0.10, "une legende bouge vraiment sur sa ligne (%f m)" % extremes[3])
	check(extremes[3] > extremes[0], "et plus qu'un debutant (%f contre %f)" % [extremes[3], extremes[0]])

	near(KeeperBrain.line_dance(1.3, 2, 42), KeeperBrain.line_dance(1.3, 2, 42), 0.0,
		"la danse est deterministe")
	check(absf(KeeperBrain.line_dance(1.3, 2, 42) - KeeperBrain.line_dance(1.3, 2, 43)) > 0.0001,
		"une autre graine donne une autre danse")

	# It starts from the middle of the goal and eases in rather than snapping.
	check(absf(KeeperBrain.line_dance(0.02, 3, 77)) < 0.05, "le depart est progressif")
	done()


# =============================================================================
# 10. Hostile inputs
# =============================================================================

func test_aucun_nan_sur_entrees_hostiles() -> void:
	var nan_value := 0.0 / 0.0
	var inf_value := INF

	var pose := KeeperBrain.dive_pose(Vector3(nan_value, inf_value, nan_value), nan_value, 77)
	check(_pose_is_finite(pose), "une pose reste finie avec un temps NaN et une cible absurde")
	near_vec(pose["centre"], _home_pose()["centre"], 0.0001, "un temps NaN retombe sur la pose de repos")

	var negative := KeeperBrain.dive_pose(Vector3(2.0, 1.0, 0.0), -3.0, 2)
	near_vec(negative["centre"], _home_pose()["centre"], 0.0001, "un temps negatif aussi")

	var wild := KeeperBrain.dive_pose(Vector3(-900.0, 900.0, 900.0), 0.5, 1)
	check(_pose_is_finite(wild), "une cible hors du stade reste une pose finie")
	check((wild["centre"] as Vector3).distance_to(Field.KEEPER_HOME) < 6.0,
		"et elle ne le teleporte pas dans les tribunes")

	var far := KeeperBrain.dive_pose(Vector3(3.0, 2.10, 0.0), 40.0, 3)
	check(_pose_is_finite(far), "une pose tres tardive reste finie")
	check((far["centre"] as Vector3).distance_to(Field.KEEPER_HOME) < 6.0,
		"et le gardien ne glisse pas jusqu'a l'infini")

	var broken := KeeperBrain.estimate_cross(Vector3(nan_value, 0.0, 11.0), Vector3(0.0, 0.0, -28.0),
		Vector3(inf_value, 0.0, 0.0), 2, nan_value, 3)
	check(_is_finite_vec(broken["point"]), "estimation finie malgre un etat de ballon corrompu")
	check(is_finite(float(broken["error"])), "incertitude finie")

	var empty_read := KeeperBrain.read_cues({}, 2, 8)
	between(float(empty_read["confidence"]), 0.0, 1.0, "confiance bornee sans aucun indice")
	check(is_finite(float(empty_read["commit_time"])), "instant de depart fini sans indice")

	var poisoned := KeeperBrain.read_cues({"aim_hint": nan_value, "power_hint": inf_value,
		"plant_offset": "gauche", "feints": 99}, 3, 8)
	between(float(poisoned["confidence"]), 0.0, 1.0, "confiance bornee sur des indices corrompus")
	check(int(poisoned["side"]) >= -1 and int(poisoned["side"]) <= 1, "cote valide malgre tout")

	var bad_pose := {"centre": Vector3(nan_value, 0.0, 0.0), "glove_left": "rien"}
	var attempt := KeeperBrain.try_save(bad_pose, Vector3(0.0, 1.0, 0.5), Vector3(0.0, 1.0, -0.5))
	check(not bool(attempt["saved"]), "une pose corrompue n'arrete rien")
	check(is_finite(KeeperBrain.save_distance(bad_pose, Vector3(0.0, 1.0, 0.5), Vector3(0.0, 1.0, -0.5))),
		"distance d'arret finie sur une pose corrompue")

	var still := KeeperBrain.try_save(_home_pose(), Vector3(0.0, 0.98, 0.12), Vector3(0.0, 0.98, 0.12))
	check(bool(still["saved"]), "un segment de longueur nulle sur le plastron est bien un contact")
	near((still["normal"] as Vector3).length(), 1.0, 0.0001, "normale unitaire meme sur un segment nul")
	done()
