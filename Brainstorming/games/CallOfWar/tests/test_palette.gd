extends WarTest
## Palette discipline. An albedo brighter than about 0.38 in linear space blows
## past the shoulder of the ACES curve once lit and desaturates towards white,
## which is exactly how a green field ends up looking like mint paint. This suite
## keeps that mistake from creeping back in.


func suite_name() -> String:
	return "palette"


## Every surface colour of the game, excluding the deliberately emissive ones.
func _surface_colors() -> Dictionary:
	return {
		"GRASS_SUMMER": Palette.GRASS_SUMMER,
		"GRASS_DRY": Palette.GRASS_DRY,
		"WHEAT": Palette.WHEAT,
		"DIRT": Palette.DIRT,
		"MUD": Palette.MUD,
		"ROAD": Palette.ROAD,
		"STONE": Palette.STONE,
		"STONE_DARK": Palette.STONE_DARK,
		"CONCRETE": Palette.CONCRETE,
		"WOOD": Palette.WOOD,
		"WOOD_LIGHT": Palette.WOOD_LIGHT,
		"ROOF_SLATE": Palette.ROOF_SLATE,
		"ROOF_TILE": Palette.ROOF_TILE,
		"PLASTER": Palette.PLASTER,
		"LEAF_DARK": Palette.LEAF_DARK,
		"LEAF_LIGHT": Palette.LEAF_LIGHT,
		"WATER": Palette.WATER,
		"METAL": Palette.METAL,
		"RUST": Palette.RUST,
		"FELDGRAU": Palette.FELDGRAU,
		"KHAKI": Palette.KHAKI,
		"RESISTANCE": Palette.RESISTANCE,
		"SKIN": Palette.SKIN,
		"BLOOD": Palette.BLOOD,
		"SMOKE": Palette.SMOKE,
		"SNOW": Palette.SNOW,
	}


func test_no_surface_albedo_blows_out_in_aces() -> void:
	for name in _surface_colors():
		var color: Color = _surface_colors()[name]
		var brightest: float = maxf(color.r, maxf(color.g, color.b))
		between(brightest, 0.04, 0.39,
				"%s sortira delave une fois eclaire (canal max %f)" % [name, brightest])
	done()


func test_no_surface_colour_is_pure_black() -> void:
	# A pure black albedo eats every light and reads as a hole in the world.
	for name in _surface_colors():
		var color: Color = _surface_colors()[name]
		var brightest: float = maxf(color.r, maxf(color.g, color.b))
		check(brightest > 0.02, "%s est trop proche du noir absolu" % name)
	done()


func test_the_two_uniforms_are_clearly_different() -> void:
	# Telling friend from foe at 80 m is the single most important read of the
	# whole game. Feldgrau and khaki must not converge.
	var axis := Palette.FELDGRAU
	var allied := Palette.KHAKI
	var distance := Vector3(axis.r - allied.r, axis.g - allied.g, axis.b - allied.b).length()
	check(distance > 0.05,
			"feldgrau et kaki sont trop proches pour distinguer ami et ennemi (%f)" % distance)
	done()


func test_effect_colours_are_bright_on_purpose() -> void:
	# Tracers, muzzle flashes and fire are emissive, so they are allowed, and in
	# fact required, to be far brighter than any surface.
	check(Palette.TRACER.r > 0.6, "un traceur doit etre lumineux")
	check(Palette.MUZZLE.r > 0.6, "un depart de coup doit etre lumineux")
	check(Palette.FIRE.r > 0.6, "le feu doit etre lumineux")
	done()


func test_vary_stays_inside_the_safe_range() -> void:
	# Scatter tints every tree and hedge through vary(). If it can push a colour
	# past the safe ceiling, the desaturation problem comes back one tree at a
	# time instead of all at once.
	for step in 21:
		var t := float(step) / 20.0
		var tinted := Palette.vary(Palette.LEAF_DARK, t, 0.12)
		var brightest: float = maxf(tinted.r, maxf(tinted.g, tinted.b))
		between(brightest, 0.01, 0.45, "vary() a %f fait sortir la couleur des bornes" % t)
		between(tinted.a, 0.99, 1.01, "vary() ne doit pas toucher a l'alpha")
	done()


func test_vary_is_deterministic() -> void:
	var first := Palette.vary(Palette.GRASS_SUMMER, 0.37, 0.12)
	var second := Palette.vary(Palette.GRASS_SUMMER, 0.37, 0.12)
	check(first.is_equal_approx(second),
			"vary() doit etre pure : la vegetation se regenere a chaque streaming")
	done()
