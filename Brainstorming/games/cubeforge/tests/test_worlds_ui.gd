extends TestCase
## Pure helpers of the worlds screen (src/ui/worlds_ui.gd).
##
## Only the two static functions are covered here: the widgets need a running
## scene tree and are exercised by the smoke probe instead. The helpers decide
## which folder a world lands in and which seed a text input produces, so every
## rule of their contract is pinned down: trimming, character filtering, space
## collapsing, length capping, integer passthrough, sign folding, the 31 bit
## mask, the non-zero guarantee and the determinism of the text hash.

## Loaded by path rather than through the WorldsUi global class: a stale global
## class cache would otherwise fail the compile of this suite for nothing.
const WorldsUiScript := preload("res://src/ui/worlds_ui.gd")

const SEED_MAX := 0x7FFFFFFF


func suite_name() -> String:
	return "worlds_ui"


# ---------------------------------------------------------------------------
# sanitize_world_name
# ---------------------------------------------------------------------------

func test_sanitize_trims_and_keeps_plain_names() -> void:
	eq(WorldsUiScript.sanitize_world_name("monde"), "monde", "un nom simple passe inchangé")
	eq(WorldsUiScript.sanitize_world_name("  monde  "), "monde", "les espaces de bord sont retirés")
	eq(WorldsUiScript.sanitize_world_name("Mon Monde 2"), "Mon Monde 2", "lettres, chiffres et espaces internes sont gardés")
	eq(WorldsUiScript.sanitize_world_name("a-b_c"), "a-b_c", "tirets et soulignés sont gardés")
	done()


func test_sanitize_filters_and_collapses() -> void:
	eq(WorldsUiScript.sanitize_world_name("a/b\\c:d*e"), "abcde", "les caractères spéciaux sont retirés")
	eq(WorldsUiScript.sanitize_world_name("a    b"), "a b", "les suites d'espaces sont réduites à un seul")
	eq(WorldsUiScript.sanitize_world_name("a . b"), "a b", "un caractère rejeté entre espaces ne laisse qu'un espace")
	eq(WorldsUiScript.sanitize_world_name("!!!"), "", "un nom sans caractère valide devient vide")
	eq(WorldsUiScript.sanitize_world_name(""), "", "la chaîne vide reste vide")
	eq(WorldsUiScript.sanitize_world_name("   "), "", "des espaces seuls deviennent vides")
	done()


func test_sanitize_caps_length() -> void:
	var long_name := ""
	for i in 40:
		long_name += "x"
	eq(WorldsUiScript.sanitize_world_name(long_name).length(), 24, "un nom long est tronqué à 24 caractères")
	# A space landing exactly on the cut must not survive as a trailing space.
	var spaced := "aaaaaaaaaaaaaaaaaaaaaaa bbbb"
	var cut := WorldsUiScript.sanitize_world_name(spaced)
	check(cut.length() <= 24, "la coupe respecte la limite de 24")
	ne(cut.substr(cut.length() - 1, 1), " ", "pas d'espace final après la coupe")
	done()


# ---------------------------------------------------------------------------
# parse_seed
# ---------------------------------------------------------------------------

func test_parse_seed_empty_means_zero() -> void:
	eq(WorldsUiScript.parse_seed(""), 0, "vide vaut 0 (hasard ou graine existante)")
	eq(WorldsUiScript.parse_seed("   "), 0, "des espaces seuls valent 0")
	done()


func test_parse_seed_integer_passthrough() -> void:
	eq(WorldsUiScript.parse_seed("42"), 42, "un entier positif passe tel quel")
	eq(WorldsUiScript.parse_seed("  42  "), 42, "les espaces de bord sont ignorés")
	eq(WorldsUiScript.parse_seed("-42"), 42, "un entier négatif est replié en positif")
	eq(WorldsUiScript.parse_seed("0"), 1, "zéro explicite retombe sur 1, jamais sur le hasard")
	eq(WorldsUiScript.parse_seed("2147483647"), SEED_MAX, "la borne 31 bits passe telle quelle")
	var folded := WorldsUiScript.parse_seed("2147483648")
	between(float(folded), 1.0, float(SEED_MAX), "au delà de 31 bits, le repli reste dans [1, 2^31 - 1]")
	eq(WorldsUiScript.parse_seed("2147483648"), 1, "2^31 masqué à zéro retombe sur 1")
	done()


func test_parse_seed_hash_is_deterministic() -> void:
	var first := WorldsUiScript.parse_seed("mon beau monde")
	var second := WorldsUiScript.parse_seed("mon beau monde")
	eq(first, second, "le même texte donne la même graine à chaque appel")
	between(float(first), 1.0, float(SEED_MAX), "la graine hachée est positive, non nulle, 31 bits")
	ne(WorldsUiScript.parse_seed("mon beau monde"), WorldsUiScript.parse_seed("mon autre monde"),
			"deux textes différents donnent des graines différentes")
	done()
