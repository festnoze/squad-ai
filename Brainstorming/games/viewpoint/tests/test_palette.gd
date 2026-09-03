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


func test_ground_language() -> void:
	# The rule the player reads without a word of explanation: grey stays,
	# pale goes. The two must be told apart at a glance, and the ephemeral one
	# must be the lighter of the two.
	check(Palette.has_color("platform"), "sol permanent defini")
	check(Palette.has_color("platform_soft"), "sol effacable defini")
	var solid := Palette.color("platform")
	var soft := Palette.color("platform_soft")
	var grey_spread: float = maxf(maxf(solid.r, solid.g), solid.b) - minf(minf(solid.r, solid.g), solid.b)
	check(grey_spread < 0.12, "le sol permanent est gris, pas colore")
	check(soft.get_luminance() > solid.get_luminance() + 0.12, "le sol effacable est nettement plus clair")
	check(Palette.color("platform_soft_side").get_luminance() > Palette.color("platform_side").get_luminance(),
		"les flancs suivent le meme langage")
	# The ephemeral ground belongs to the lavender family it shares a fate with.
	var lavender := Palette.color("erasable")
	check(soft.b > soft.g, "le sol effacable tire vers le lavande comme les murs effacables")
	check(lavender.b > lavender.g, "le lavande reste la couleur de ce qui disparait")
	done()


func test_sealed_language() -> void:
	# One step past the permanent ground: steel and lead. Same grey family, so
	# the eye files them under "this will not move", but darker, so they read
	# as a harder refusal than a plain platform.
	for key in ["sealed", "sealed_dark", "battery_sealed"]:
		check(Palette.has_color(key), "couleur %s definie" % key)
		var c := Palette.color(key)
		var spread: float = maxf(maxf(c.r, c.g), c.b) - minf(minf(c.r, c.g), c.b)
		check(spread < 0.12, "%s est un gris, pas une couleur" % key)
	check(Palette.color("sealed").get_luminance() < Palette.color("platform").get_luminance(),
		"l'acier est plus sombre que le sol permanent")
	check(Palette.color("sealed_dark").get_luminance() < Palette.color("sealed").get_luminance(),
		"les accents d'acier sont plus sombres encore")
	# A leaden battery must never be mistaken for a live one at a glance.
	var live := Palette.color("battery")
	var lead := Palette.color("battery_sealed")
	check(absf(live.r - lead.r) + absf(live.g - lead.g) + absf(live.b - lead.b) > 0.5,
		"la pile plombee ne se confond pas avec la pile vive")
	check(live.get_luminance() > lead.get_luminance() + 0.2, "la pile vive est nettement plus lumineuse")
	done()


func test_readability() -> void:
	# The erasable tint must stand out from the regular platform color, or the
	# player cannot tell what a photo can erase.
	var d := Palette.color("erasable") - Palette.color("platform")
	check(absf(d.r) + absf(d.g) + absf(d.b) > 0.1, "effacable distinct des plateformes")
	check(Palette.color("sky_top").b > Palette.color("sky_horizon").b - 0.2, "ciel bleute vers le haut")
	done()
