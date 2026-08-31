extends ViewTest
## The named color table every material goes through.


func suite_name() -> String:
	return "palette"


func test_colors_defined() -> void:
	check(Palette.COLORS.size() >= 15, "au moins quinze couleurs nommees")
	for key in Palette.COLORS:
		var c: Color = Palette.COLORS[key]
		near(c.a, 1.0, 0.001, "couleur %s opaque" % key)
	done()


func test_lookup() -> void:
	check(Palette.has_color("platform"), "platform existe")
	check(not Palette.has_color("nimporte_quoi"), "cle inconnue refusee")
	eq(Palette.color("nimporte_quoi"), Color.MAGENTA, "cle inconnue rend le magenta sentinelle")
	eq(Palette.color("battery"), Palette.COLORS["battery"], "lecture directe coherente")
	done()


func test_readability() -> void:
	# The erasable tint must stand out from the regular platform color, or the
	# player cannot tell what a photo can erase.
	var d := Palette.color("erasable") - Palette.color("platform")
	check(absf(d.r) + absf(d.g) + absf(d.b) > 0.1, "effacable distinct des plateformes")
	check(Palette.color("sky_top").b > Palette.color("sky_horizon").b - 0.2, "ciel bleute vers le haut")
	done()
