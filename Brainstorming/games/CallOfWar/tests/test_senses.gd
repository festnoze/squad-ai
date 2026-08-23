extends WarTest
## AI perception. The whole feel of the game depends on these numbers: too
## generous and the Germans are omniscient snipers, too stingy and they walk
## past the player at arm's length.


func suite_name() -> String:
	return "senses"


func test_sight_range_shrinks_at_night() -> void:
	var day := Senses.sight_range(120.0, 1.0, 1.0)
	var dusk := Senses.sight_range(120.0, 0.4, 1.0)
	var night := Senses.sight_range(120.0, 0.0, 1.0)
	check(day > dusk, "on voit plus loin en plein jour qu'au crepuscule")
	check(dusk > night, "on voit plus loin au crepuscule qu'en pleine nuit")
	check(night > 0.0, "meme de nuit, un soldat voit a bout portant")
	check(night < day * 0.6, "la nuit doit vraiment reduire la portee de vue")
	done()


func test_sight_range_shrinks_in_bad_weather() -> void:
	var clear := Senses.sight_range(120.0, 1.0, 1.0)
	var storm := Senses.sight_range(120.0, 1.0, 0.35)
	check(storm < clear, "l'orage doit reduire la portee de vue")
	check(storm > 0.0, "la portee de vue ne tombe jamais a zero")
	done()


func test_sight_range_is_monotonic_in_light() -> void:
	var previous := 0.0
	for step in 11:
		var light := float(step) / 10.0
		var range_value := Senses.sight_range(120.0, light, 1.0)
		check(range_value >= previous - 0.001,
				"la portee de vue diminue quand la lumiere augmente (a %f)" % light)
		check(is_finite(range_value), "portee de vue non finie")
		previous = range_value
	done()


func test_hearing_is_a_simple_radius() -> void:
	var ear := Vector3(0.0, 1.6, 0.0)
	check(Senses.can_hear(ear, Vector3(5.0, 0.0, 0.0), 20.0),
			"un bruit de 20 m doit s'entendre a 5 m")
	check(not Senses.can_hear(ear, Vector3(60.0, 0.0, 0.0), 20.0),
			"un bruit de 20 m ne doit pas s'entendre a 60 m")
	check(not Senses.can_hear(ear, Vector3(5.0, 0.0, 0.0), 0.0),
			"un bruit de rayon nul ne s'entend pas")
	done()


func test_hearing_boundary_is_not_inverted() -> void:
	var ear := Vector3.ZERO
	var near_point := Vector3(9.9, 0.0, 0.0)
	var far_point := Vector3(10.1, 0.0, 0.0)
	check(Senses.can_hear(ear, near_point, 10.0), "juste dedans doit s'entendre")
	check(not Senses.can_hear(ear, far_point, 10.0), "juste dehors ne doit pas s'entendre")
	done()


func test_the_vision_cone_is_a_cone_and_not_a_sphere() -> void:
	# A soldier must not see through the back of his own helmet. This is checked
	# on the constant rather than on can_see, which needs a physics world.
	between(Senses.FOV_HALF, 0.5, 1.6,
			"le demi angle du cone de vision est invraisemblable")
	check(Senses.FOV_HALF < PI * 0.5,
			"un demi angle superieur a 90 degres donne une vision arriere")
	done()
