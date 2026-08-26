extends GoalTest
## Layers: one bit per layer, no overlap, and masks that say what they mean.
##
## A collision mask bug does not crash, it just makes the ball fall through the
## world or ignore the keeper, and it is invisible in a code review. Cheap
## checks here are worth an hour of debugging later.


func suite_name() -> String:
	return "Layers"


func test_bits_are_distinct_powers_of_two() -> void:
	var seen := 0
	for bit in Layers.ALL_BITS:
		check(bit > 0, "un bit de couche doit etre positif")
		check((bit & (bit - 1)) == 0, "le bit %d n'est pas une puissance de deux" % bit)
		check((seen & bit) == 0, "le bit %d est declare deux fois" % bit)
		seen |= bit
	eq(Layers.ALL_BITS.size(), 8, "il y a huit couches")
	eq(seen, 255, "les huit bits couvrent 0..7")
	done()


func test_declared_values_match_the_project() -> void:
	# These numbers are also written in project.godot's layer_names section.
	eq(Layers.PITCH, 1, "pitch est le bit 1")
	eq(Layers.GOAL, 2, "goal est le bit 2")
	eq(Layers.NET, 4, "net est le bit 3")
	eq(Layers.BALL, 8, "ball est le bit 4")
	eq(Layers.KEEPER, 16, "keeper est le bit 5")
	eq(Layers.PROP, 32, "prop est le bit 6")
	eq(Layers.TRIGGER, 64, "trigger est le bit 7")
	eq(Layers.TARGET, 128, "target est le bit 8")
	done()


func test_ball_mask_covers_everything_solid() -> void:
	check(Layers.has_bit(Layers.BALL_MASK, Layers.PITCH), "le ballon doit voir la pelouse")
	check(Layers.has_bit(Layers.BALL_MASK, Layers.GOAL), "le ballon doit voir le cadre")
	check(Layers.has_bit(Layers.BALL_MASK, Layers.NET), "le ballon doit voir le filet")
	check(Layers.has_bit(Layers.BALL_MASK, Layers.KEEPER), "le ballon doit voir le gardien")
	check(Layers.has_bit(Layers.BALL_MASK, Layers.PROP), "le ballon doit voir les accessoires")
	check(Layers.has_bit(Layers.BALL_MASK, Layers.TARGET), "le ballon doit voir les cibles")
	# A ball colliding with its own layer would self intersect.
	check(not Layers.has_bit(Layers.BALL_MASK, Layers.BALL), "le ballon ne doit pas se voir lui meme")
	check(not Layers.has_bit(Layers.BALL_MASK, Layers.TRIGGER), "les zones de declenchement n'arretent pas le ballon")
	done()


func test_aim_and_walk_masks() -> void:
	# The aim ray must land on the goal and the turf, never on the keeper: the
	# reticle would jump around as he moves.
	check(Layers.has_bit(Layers.AIM_MASK, Layers.PITCH), "la visee touche la pelouse")
	check(Layers.has_bit(Layers.AIM_MASK, Layers.GOAL), "la visee touche le cadre")
	check(Layers.has_bit(Layers.AIM_MASK, Layers.NET), "la visee touche le filet")
	check(Layers.has_bit(Layers.AIM_MASK, Layers.TRIGGER), "la visee touche les zones")
	check(not Layers.has_bit(Layers.AIM_MASK, Layers.KEEPER), "la visee ignore le gardien")
	check(not Layers.has_bit(Layers.AIM_MASK, Layers.BALL), "la visee ignore le ballon")

	check(Layers.has_bit(Layers.WALK_MASK, Layers.PITCH), "on marche sur la pelouse")
	check(Layers.has_bit(Layers.WALK_MASK, Layers.GOAL), "on ne traverse pas un poteau")
	check(not Layers.has_bit(Layers.WALK_MASK, Layers.NET), "le filet n'arrete pas un corps")
	done()


func test_bit_names_round_trip() -> void:
	var names := PackedStringArray()
	for bit in Layers.ALL_BITS:
		var label := Layers.bit_name(bit)
		check(label != "", "le bit %d doit avoir un nom" % bit)
		check(not names.has(label), "le nom '%s' est utilise deux fois" % label)
		names.append(label)
	eq(Layers.bit_name(3), "", "un masque combine n'a pas de nom")
	eq(Layers.bit_name(0), "", "zero n'a pas de nom")
	eq(names[0], "pitch", "le premier bit est pitch")
	done()


func test_has_bit_is_a_real_test() -> void:
	check(Layers.has_bit(6, Layers.GOAL), "6 contient goal")
	check(Layers.has_bit(6, Layers.NET), "6 contient net")
	check(not Layers.has_bit(6, Layers.PITCH), "6 ne contient pas pitch")
	check(not Layers.has_bit(0, Layers.PITCH), "un masque vide ne contient rien")
	done()
