extends GoalTest
## Field: the geometry oracle. In / out, the frame, and above all the sweep.
##
## The sweep is the reason this suite exists. At 120 Hz a 30 m/s shot moves 25 cm
## per step, which is more than the diameter of a post plus a ball: a naive
## "am I overlapping right now" test misses the woodwork completely on most
## shots. Every sweep case below is written so the ball would tunnel through a
## point test but must not tunnel through this one.

const R := Field.POST_RADIUS + Field.BALL_RADIUS     # 0.17, the swept radius


func suite_name() -> String:
	return "Field (geometrie)"


func test_constants_are_consistent() -> void:
	near(Field.GOAL_HALF * 2.0, Field.GOAL_WIDTH, 0.0001, "la demi largeur est la moitie de la largeur")
	near(Field.POST_X, Field.GOAL_HALF + Field.POST_RADIUS, 0.0001, "l'axe du poteau est hors de la bouche")
	near(Field.BAR_Y, Field.GOAL_HEIGHT + Field.POST_RADIUS, 0.0001, "l'axe de la barre est au dessus du cadre")
	near(Field.SPOT.z, Field.SPOT_Z, 0.0001, "le point de penalty est a 11 m")
	near(Field.SPOT.y, Field.BALL_RADIUS, 0.0001, "le ballon pose touche la pelouse")
	check(Field.SPOT_Z < Field.BOX_DEPTH, "le point est dans la surface")
	check(Field.PITCH_MIN_Z < 0.0, "la pelouse depasse derriere la ligne de but")
	done()


func test_post_centres_are_mirrored() -> void:
	var left := Field.post_centre(-1)
	var right := Field.post_centre(1)
	near(left.x, -Field.POST_X, 0.0001, "le poteau gauche est en -X")
	near(right.x, Field.POST_X, 0.0001, "le poteau droit est en +X")
	near(left.y, right.y, 0.0001, "les deux poteaux sont a la meme hauteur")
	near(left.z, 0.0, 0.0001, "les poteaux sont sur la ligne de but")
	# The inner faces must be exactly the regulation 7.32 m apart.
	near((right.x - Field.POST_RADIUS) - (left.x + Field.POST_RADIUS), Field.GOAL_WIDTH, 0.0001,
		"l'ecart interieur vaut la largeur reglementaire")
	done()


func test_frame_membership() -> void:
	check(Field.is_within_frame(Vector3(0.0, 1.0, 0.0)), "plein centre est dans le cadre")
	check(Field.is_within_frame(Vector3(3.5, 2.4, 5.0)), "le z est ignore par le test de cadre")
	check(not Field.is_within_frame(Vector3(3.9, 1.0, 0.0)), "au dela du poteau on est hors cadre")
	check(not Field.is_within_frame(Vector3(0.0, 2.6, 0.0)), "au dessus de la barre on est hors cadre")
	check(not Field.is_within_frame(Vector3(0.0, -0.2, 0.0)), "sous la pelouse on est hors cadre")
	done()


func test_inside_mouth_needs_the_whole_ball() -> void:
	check(Field.is_inside_mouth(Vector3(0.0, 1.0, -0.2)), "le ballon entierement passe est un but")
	check(not Field.is_inside_mouth(Vector3(0.0, 1.0, -0.05)), "a cheval sur la ligne, pas encore de but")
	check(not Field.is_inside_mouth(Vector3(0.0, 1.0, 0.0)), "pile sur la ligne, pas de but")
	check(not Field.is_inside_mouth(Vector3(0.0, 1.0, 1.0)), "devant la ligne, pas de but")
	check(not Field.is_inside_mouth(Vector3(3.7, 1.0, -0.5)), "a cote du poteau, pas de but")
	check(not Field.is_inside_mouth(Vector3(0.0, 2.5, -0.5)), "au dessus de la barre, pas de but")
	check(not Field.is_inside_mouth(Vector3(0.0, 1.0, -6.0)), "derriere le filet, ce n'est plus la bouche")
	done()


func test_nearest_frame_finds_the_right_part() -> void:
	var right: Dictionary = Field.nearest_frame(Vector3(3.5, 1.0, 0.0))
	eq(int(right["part"]), Field.FRAME_POST_RIGHT, "le poteau droit est le plus proche")
	near(float(right["distance"]), 0.16, 0.0001, "distance a la surface du poteau droit")
	var surface: Vector3 = right["point"]
	near(surface.x, Field.GOAL_HALF, 0.0001, "la surface interieure du poteau est a 3.66")

	var left: Dictionary = Field.nearest_frame(Vector3(-3.9, 0.5, 0.0))
	eq(int(left["part"]), Field.FRAME_POST_LEFT, "le poteau gauche est le plus proche")

	var bar: Dictionary = Field.nearest_frame(Vector3(0.0, 3.0, 0.0))
	eq(int(bar["part"]), Field.FRAME_BAR, "la barre est la plus proche")
	near(float(bar["distance"]), 0.44, 0.0001, "distance a la surface de la barre")

	# Inside the tube the distance goes negative, which is what tells a caller
	# it has to push the ball back out.
	var inside: Dictionary = Field.nearest_frame(Vector3(Field.POST_X, 1.0, 0.03))
	check(float(inside["distance"]) < 0.0, "dans le poteau la distance est negative")
	done()


func test_sweep_hits_the_post_head_on() -> void:
	var hit: Dictionary = Field.sweep_frame(Vector3(Field.POST_X, 1.0, 1.0), Vector3(Field.POST_X, 1.0, -1.0))
	check(bool(hit["hit"]), "un tir sur l'axe du poteau doit toucher")
	eq(int(hit["part"]), Field.FRAME_POST_RIGHT, "c'est le poteau droit")
	near(float(hit["t"]), (1.0 - R) / 2.0, 0.002, "le contact a lieu a un rayon de l'axe")
	var normal: Vector3 = hit["normal"]
	near(normal.length(), 1.0, 0.0001, "la normale est unitaire")
	check(normal.z > 0.9, "la normale d'un choc frontal renvoie vers le tireur")
	done()


func test_sweep_normal_decides_the_deflection() -> void:
	# This is the whole point of the module. Two shots 24 cm apart, one clipping
	# the inside of the post and one the outside: the first must be sent into the
	# goal, the second away from it.
	var inside: Dictionary = Field.sweep_frame(Vector3(3.60, 1.0, 1.0), Vector3(3.60, 1.0, -1.0))
	check(bool(inside["hit"]), "un ballon a 3.60 m frotte le poteau droit")
	var n_in: Vector3 = inside["normal"]
	check(n_in.x < -0.5, "l'interieur du poteau renvoie vers le centre du but")
	check(n_in.z > 0.0, "et vers l'arriere, le ballon rebondit")

	var outside: Dictionary = Field.sweep_frame(Vector3(3.84, 1.0, 1.0), Vector3(3.84, 1.0, -1.0))
	check(bool(outside["hit"]), "un ballon a 3.84 m frotte aussi le poteau droit")
	var n_out: Vector3 = outside["normal"]
	check(n_out.x > 0.5, "l'exterieur du poteau renvoie loin du but")

	# Same story on the left post, mirrored.
	var left_inside: Dictionary = Field.sweep_frame(Vector3(-3.60, 1.0, 1.0), Vector3(-3.60, 1.0, -1.0))
	check(bool(left_inside["hit"]), "meme chose sur le poteau gauche")
	var n_left: Vector3 = left_inside["normal"]
	check(n_left.x > 0.5, "l'interieur du poteau gauche renvoie vers le centre")
	done()


func test_sweep_hits_the_bar_from_below() -> void:
	var hit: Dictionary = Field.sweep_frame(Vector3(0.0, 2.40, 1.0), Vector3(0.0, 2.40, -1.0))
	check(bool(hit["hit"]), "un tir sous la barre la touche")
	eq(int(hit["part"]), Field.FRAME_BAR, "c'est la barre")
	var normal: Vector3 = hit["normal"]
	check(normal.y < 0.0, "la barre frappee par en dessous renvoie vers le bas")
	near(normal.length(), 1.0, 0.0001, "la normale est unitaire")
	done()


func test_sweep_ignores_a_clean_shot() -> void:
	var centre: Dictionary = Field.sweep_frame(Vector3(0.0, 1.0, 1.0), Vector3(0.0, 1.0, -1.0))
	check(not bool(centre["hit"]), "plein centre ne touche rien")
	eq(int(centre["part"]), Field.FRAME_NONE, "et ne designe aucune partie")
	near(float(centre["t"]), 1.0, 0.0001, "sans contact, t vaut 1")

	var over: Dictionary = Field.sweep_frame(Vector3(0.0, 2.9, 1.0), Vector3(0.0, 2.9, -1.0))
	check(not bool(over["hit"]), "au dessus de la barre on ne touche rien")

	var wide: Dictionary = Field.sweep_frame(Vector3(4.2, 1.0, 1.0), Vector3(4.2, 1.0, -1.0))
	check(not bool(wide["hit"]), "largement a cote on ne touche rien")
	done()


func test_sweep_does_not_tunnel_through_the_post() -> void:
	# One 50 cm step, the length a very hard shot covers on a dropped frame. The
	# swept tube of the post is 34 cm across, so both ends of the step are in
	# clear air and only the sweep can see the contact.
	var from := Vector3(Field.POST_X, 1.0, 0.25)
	var to := Vector3(Field.POST_X, 1.0, -0.25)
	check(Vector3(from.x, from.y, 0.0).distance_to(from) > R, "le depart est bien hors du poteau")
	check(Vector3(to.x, to.y, 0.0).distance_to(to) > R, "l'arrivee est bien hors du poteau")
	var hit: Dictionary = Field.sweep_frame(from, to)
	check(bool(hit["hit"]), "le balayage attrape le poteau traverse en un pas")
	eq(int(hit["part"]), Field.FRAME_POST_RIGHT, "et sait quel poteau")
	near(float(hit["t"]), (0.25 - R) / 0.5, 0.002, "au bon instant du pas")
	between(float(hit["t"]), 0.0, 1.0, "la fraction de contact est dans le pas")
	done()


func test_sweep_reports_the_earliest_contact() -> void:
	# A ball crossing the whole mouth from outside the left post to outside the
	# right one must report the LEFT post, the one it reaches first.
	var hit: Dictionary = Field.sweep_frame(Vector3(-4.2, 1.0, 0.0), Vector3(4.2, 1.0, 0.0))
	check(bool(hit["hit"]), "la trajectoire traverse les deux poteaux")
	eq(int(hit["part"]), Field.FRAME_POST_LEFT, "le premier touche est le poteau gauche")
	var contact: Vector3 = hit["point"]
	check(contact.x < 0.0, "le point de contact est du cote gauche")
	done()


func test_sweep_reports_an_immediate_overlap() -> void:
	# A ball already inside the tube (a rebound resolved badly, a teleport) must
	# be reported at t = 0 with a usable normal instead of being swallowed.
	var hit: Dictionary = Field.sweep_frame(Vector3(Field.POST_X + 0.05, 1.0, 0.0), Vector3(Field.POST_X + 0.05, 1.0, -0.2))
	check(bool(hit["hit"]), "un chevauchement de depart est signale")
	near(float(hit["t"]), 0.0, 0.0001, "et il est signale a t = 0")
	var normal: Vector3 = hit["normal"]
	near(normal.length(), 1.0, 0.0001, "avec une normale unitaire")
	check(normal.x > 0.0, "qui pousse le ballon hors du poteau")
	done()


func test_goal_plane_crossing() -> void:
	var forward: Dictionary = Field.cross_goal_plane(Vector3(0.0, 1.0, 1.0), Vector3(0.0, 1.0, -1.0))
	check(bool(forward["crossed"]), "un tir vers le but franchit le plan")
	near(float(forward["t"]), 0.5, 0.0001, "a la moitie du pas")
	var point: Vector3 = forward["point"]
	near(point.z, 0.0, 0.0001, "le point est sur le plan z = 0")

	var uneven: Dictionary = Field.cross_goal_plane(Vector3(0.0, 1.0, 0.25), Vector3(0.0, 1.0, -0.75))
	near(float(uneven["t"]), 0.25, 0.0001, "la fraction suit la geometrie du pas")

	var backward: Dictionary = Field.cross_goal_plane(Vector3(0.0, 1.0, -1.0), Vector3(0.0, 1.0, 1.0))
	check(not bool(backward["crossed"]), "un ballon qui ressort ne franchit pas dans le bon sens")

	var short: Dictionary = Field.cross_goal_plane(Vector3(0.0, 1.0, 1.0), Vector3(0.0, 1.0, 0.5))
	check(not bool(short["crossed"]), "un pas qui n'atteint pas la ligne ne franchit rien")
	done()


func test_mouth_margin_signs() -> void:
	near(Field.mouth_margin(Vector3(0.0, Field.GOAL_HEIGHT * 0.5, 0.0)), -Field.GOAL_HEIGHT * 0.5, 0.0001,
		"au centre, la marge vaut la distance au bord le plus proche")
	check(Field.mouth_margin(Vector3(0.0, 1.0, 0.0)) < 0.0, "dedans, la marge est negative")
	near(Field.mouth_margin(Vector3(4.0, 1.22, 0.0)), 0.34, 0.0001, "a droite du poteau, marge positive")
	near(Field.mouth_margin(Vector3(0.0, 3.0, 0.0)), 0.56, 0.0001, "au dessus de la barre, marge positive")
	# The corner region is a real distance, not a max of the two axes.
	near(Field.mouth_margin(Vector3(4.0, 3.0, 0.0)), sqrt(0.34 * 0.34 + 0.56 * 0.56), 0.0001,
		"dans le coin, la marge est la distance euclidienne")
	done()


func test_out_of_area() -> void:
	check(not Field.is_out_of_area(Field.SPOT), "le point de penalty est en jeu")
	check(not Field.is_out_of_area(Vector3(0.0, 1.0, -1.0)), "l'interieur du but est en jeu")
	check(Field.is_out_of_area(Vector3(0.0, 1.0, Field.PITCH_MIN_Z - 1.0)), "derriere la pelouse on est sorti")
	check(Field.is_out_of_area(Vector3(0.0, 1.0, Field.PITCH_MAX_Z + 1.0)), "trop loin devant on est sorti")
	check(Field.is_out_of_area(Vector3(Field.PITCH_HALF_X + 1.0, 1.0, 10.0)), "sur le cote on est sorti")
	check(Field.is_out_of_area(Vector3(0.0, 100.0, 10.0)), "un ballon en orbite est sorti")
	done()


func test_region_names_are_the_contract_ones() -> void:
	var allowed := PackedStringArray([
		"lucarne gauche", "lucarne droite", "petit filet gauche", "petit filet droit",
		"plein centre", "au ras du sol", "hors cadre",
	])
	var samples := PackedVector3Array([
		Vector3(-3.0, 2.1, -0.5), Vector3(3.0, 2.1, -0.5),
		Vector3(-3.0, 0.3, -0.5), Vector3(3.0, 0.3, -0.5),
		Vector3(0.0, 1.2, -0.5), Vector3(0.0, 0.2, -0.5), Vector3(5.0, 1.0, -0.5),
	])
	for sample in samples:
		check(allowed.has(Field.mouth_region_name(sample)), "region inconnue pour %s" % str(sample))
	eq(Field.mouth_region_name(Vector3(-3.0, 2.1, -0.5)), "lucarne gauche", "haut a gauche")
	eq(Field.mouth_region_name(Vector3(3.0, 2.1, -0.5)), "lucarne droite", "haut a droite")
	eq(Field.mouth_region_name(Vector3(-3.0, 0.3, -0.5)), "petit filet gauche", "bas a gauche")
	eq(Field.mouth_region_name(Vector3(3.0, 0.3, -0.5)), "petit filet droit", "bas a droite")
	eq(Field.mouth_region_name(Vector3(0.0, 1.2, -0.5)), "plein centre", "milieu")
	eq(Field.mouth_region_name(Vector3(0.0, 0.2, -0.5)), "au ras du sol", "au sol")
	eq(Field.mouth_region_name(Vector3(5.0, 1.0, -0.5)), "hors cadre", "hors du cadre")
	done()
