extends TestCase

## Preloaded by path: immune to a stale global class cache on a fresh checkout.
const MapUiScript := preload("res://src/ui/map_ui.gd")
## Static colour table of the world map (src/ui/map_ui.gd).
##
## MapUiScript.biome_color is the only pure function of the screen, and the map is
## unreadable if two biomes share a colour or if any colour carries alpha, so
## the suite pins those properties down. The biome list comes straight from
## TerrainGen.BIOME_NAMES rather than a copy, so a renamed biome fails here
## instead of silently falling into the neutral grey bucket.


func suite_name() -> String:
	return "map_ui"


func test_known_biomes_have_distinct_colors() -> void:
	eq(TerrainGen.BIOME_NAMES.size(), 10, "dix biomes attendus dans TerrainGen.BIOME_NAMES")
	var seen := {}
	for biome in TerrainGen.BIOME_NAMES:
		var c := MapUiScript.biome_color(biome)
		ne(c, MapUiScript.UNKNOWN_BIOME, "le biome connu %s ne doit pas retomber sur le gris neutre" % biome)
		var key := "%.4f_%.4f_%.4f" % [c.r, c.g, c.b]
		check(not seen.has(key), "couleur dupliquee entre %s et %s" % [biome, str(seen.get(key, ""))])
		seen[key] = biome
	eq(seen.size(), 10, "dix couleurs distinctes pour les dix biomes")
	done()


func test_unknown_biome_is_neutral_grey() -> void:
	var c := MapUiScript.biome_color("Volcan")
	near(c.r, c.g, 0.0001, "gris neutre : rouge et vert egaux")
	near(c.g, c.b, 0.0001, "gris neutre : vert et bleu egaux")
	between(c.r, 0.3, 0.7, "gris neutre : luminance moyenne")
	eq(MapUiScript.biome_color(""), c, "nom vide traite comme inconnu")
	done()


func test_all_colors_are_fully_opaque() -> void:
	for biome in TerrainGen.BIOME_NAMES:
		near(MapUiScript.biome_color(biome).a, 1.0, 0.0001, "alpha plein pour %s" % biome)
	near(MapUiScript.biome_color("Inconnu").a, 1.0, 0.0001, "alpha plein pour un nom inconnu")
	done()
