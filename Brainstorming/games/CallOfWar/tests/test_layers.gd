extends WarTest
## Collision layers. These eight bits decide what a bullet stops on and what an
## enemy can see through. A wrong mask does not crash, it just quietly makes the
## AI shoot through walls, which is much worse.


func suite_name() -> String:
	return "layers"


func test_bits_are_distinct_powers_of_two() -> void:
	var bits := [Layers.TERRAIN, Layers.STRUCTURE, Layers.PLAYER, Layers.ENEMY,
			Layers.ALLY, Layers.PROP, Layers.VEHICLE, Layers.TRIGGER]
	var seen := {}
	for bit in bits:
		check(bit > 0, "un bit de couche doit etre positif")
		check(bit & (bit - 1) == 0, "%d n'est pas une puissance de deux" % bit)
		check(not seen.has(bit), "bit de couche duplique : %d" % bit)
		seen[bit] = true
	eq(seen.size(), 8, "il doit y avoir huit couches distinctes")
	done()


func test_bullets_stop_on_solid_things() -> void:
	check(Layers.BULLET_MASK & Layers.TERRAIN != 0, "une balle doit s'arreter sur le terrain")
	check(Layers.BULLET_MASK & Layers.STRUCTURE != 0, "une balle doit s'arreter sur un mur")
	check(Layers.BULLET_MASK & Layers.ENEMY != 0, "une balle doit toucher un ennemi")
	check(Layers.BULLET_MASK & Layers.ALLY != 0, "une balle doit pouvoir toucher un allie")
	check(Layers.BULLET_MASK & Layers.PLAYER != 0, "une balle doit pouvoir toucher le joueur")
	check(Layers.BULLET_MASK & Layers.TRIGGER == 0,
			"une balle ne doit pas s'arreter sur une zone de declenchement")
	done()


func test_sight_is_blocked_by_geometry_but_not_by_people() -> void:
	# A soldier standing between the shooter and the target must not count as a
	# wall, otherwise squads never fire and simply shuffle around each other.
	check(Layers.SIGHT_MASK & Layers.TERRAIN != 0, "le terrain coupe la vue")
	check(Layers.SIGHT_MASK & Layers.STRUCTURE != 0, "un mur coupe la vue")
	check(Layers.SIGHT_MASK & Layers.PROP != 0, "un arbre coupe la vue")
	check(Layers.SIGHT_MASK & Layers.ENEMY == 0, "un soldat ne doit pas couper la vue")
	check(Layers.SIGHT_MASK & Layers.PLAYER == 0, "le joueur ne doit pas couper la vue")
	check(Layers.SIGHT_MASK & Layers.TRIGGER == 0, "une zone ne coupe pas la vue")
	done()


func test_walking_bodies_do_not_collide_with_triggers() -> void:
	check(Layers.WALK_MASK & Layers.TERRAIN != 0, "on marche sur le terrain")
	check(Layers.WALK_MASK & Layers.STRUCTURE != 0, "on se cogne aux murs")
	check(Layers.WALK_MASK & Layers.TRIGGER == 0,
			"une zone de declenchement ne doit jamais bloquer un corps qui marche")
	done()
