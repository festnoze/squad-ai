extends ViewTest
## THE WHEEL TURNS ONE WAY. The whole promise of the game is that the raised
## picture IS the placement: what you read on the polaroid is what appears in
## the world. The roll is the one place where that promise can be broken
## silently, and it was: the HUD turned the picture clockwise (a Control, 2D y
## down, so a positive rotation reads clockwise) while the placer turned the
## world counter-clockwise (a child of the camera, whose local +z points BACK
## at the player, so a positive rotation reads counter-clockwise). The two
## agreed at 0 and 180 degrees and nowhere else, which is exactly why no level
## ever asked for 90 or 270, and why nobody noticed.
##
## These tests compare the two paths against each other rather than against a
## hand-written expectation, so the day someone flips a sign the suite says
## which of the two moved.

## The corniche slab: the one catalog prop that is off center on BOTH axes, so
## a rotation of 90 degrees moves it somewhere a 180 could not.
const SAMPLE := Vector3(1.6, -0.6, -3.2)


func suite_name() -> String:
	return "photo_placer"


## Where a feature of the picture ends up, going through the HUD: the TextureRect
## is rotated by +steps * 90 degrees in Control space (x right, y DOWN), and a
## photo-space point (x right, y UP) sits on that picture at (x, -y).
func _through_the_hud(local: Vector3, steps: int) -> Vector3:
	var on_screen := Vector2(local.x, -local.y).rotated(steps * PI * 0.5)
	return Vector3(on_screen.x, -on_screen.y, local.z)


## Where the same feature ends up in the world: the placer's own roll.
func _through_the_world(local: Vector3, steps: int) -> Vector3:
	return PhotoPlacer.roll_basis(steps) * local


func test_the_hud_and_the_world_agree() -> void:
	# The invariant that matters, on every quarter turn and on points spread
	# over the frame. Depth never changes: a roll is a roll, not a dolly.
	var samples := [
		SAMPLE,
		Vector3(0, -0.6, -3.0),
		Vector3(-1.2, 0.9, -6.0),
		Vector3(0, 0, -5.0),
	]
	for steps in 4:
		for local: Vector3 in samples:
			var hud := _through_the_hud(local, steps)
			var world := _through_the_world(local, steps)
			near(world.x, hud.x, 0.0001, "roll %d : meme abscisse a l'ecran et dans le monde" % steps)
			near(world.y, hud.y, 0.0001, "roll %d : meme hauteur a l'ecran et dans le monde" % steps)
			near(world.z, local.z, 0.0001, "roll %d : la profondeur ne bouge pas" % steps)
	done()


func test_one_step_is_clockwise() -> void:
	# Spelled out once, in numbers, so the direction is readable without
	# re-deriving it: the corniche slab starts low on the RIGHT, and one step
	# down on the wheel takes it low on the LEFT (a quarter turn clockwise).
	var turned := _through_the_world(SAMPLE, 1)
	near(turned.x, -0.6, 0.0001, "un cran : la dalle passe a gauche")
	near(turned.y, -1.6, 0.0001, "un cran : la dalle descend")
	check(turned.x < 0.0 and turned.y < SAMPLE.y, "un cran tourne dans le sens horaire")
	done()


func test_the_flip_is_the_one_levels_use() -> void:
	# Two steps mirror both axes, and THAT is the move every puzzle is built on
	# (docs/LEVELS_V2.md section 1.1): a slab low on the right comes back high
	# on the left. It reads the same in both directions of rotation, which is
	# why the levels survived the bug.
	var flipped := _through_the_world(SAMPLE, 2)
	near(flipped.x, -SAMPLE.x, 0.0001, "180 degres : le cote s'inverse")
	near(flipped.y, -SAMPLE.y, 0.0001, "180 degres : la hauteur s'inverse")
	done()


func test_four_steps_come_home() -> void:
	var identity := _through_the_world(SAMPLE, 0)
	near(identity.distance_to(SAMPLE), 0.0, 0.0001, "zero cran : rien ne bouge")
	near(_through_the_world(SAMPLE, 4).distance_to(SAMPLE), 0.0, 0.0001, "quatre crans : retour au depart")
	# posmod keeps the counter in [0, 3], so 4 is never actually stored; the
	# basis still has to behave, because restore_held feeds it a raw value.
	near(_through_the_world(SAMPLE, -1).distance_to(_through_the_world(SAMPLE, 3)), 0.0, 0.0001,
		"un cran en arriere vaut trois crans en avant")
	done()
