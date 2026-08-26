extends GoalTest
## Palette suite.
##
## Two things are checked here, and the first one is the reason the file exists.
##
## 1. THE ALBEDO BAND. Every surface colour must sit inside
##    `Palette.ALBEDO_MIN .. Palette.ALBEDO_MAX` on all three channels. Too
##    bright and the ACES shoulder eats the hue, so the keeper's lime jersey
##    turns into a white blob under the floodlights; too dark and the specular
##    response dies and the ball's black panels read as a hole in the screen.
##    The check walks the script's own constant map rather than a hand written
##    list, so a colour added later cannot quietly skip the test.
##
##    EXEMPT, and deliberately so: the whole "Lights and effects" block. None of
##    those is an albedo.
##      - `FLOODLIGHT`, `TRAIL_HOT`, `TRAIL_COLD`, `UI_ACCENT`, `UI_WARN`,
##        `UI_GOOD` are EMITTERS: a light colour, two additive unshaded trail
##        tints, three 2D `_draw()` colours that never meet a tonemapper. They
##        are all deliberately ABOVE the ceiling, and
##        `test_lights_sit_above_the_band` proves it, so the exemption cannot
##        quietly become a hiding place for a mistake.
##      - `SUNLIGHT` is the key light of the daylight match, an emitter, and it
##        is deliberately ABOVE the ceiling like `FLOODLIGHT`.
##      - `SKY_DAY_TOP`, `SKY_DAY_HORIZON`, `FOG_DAY` and `AMBIENT_DAY` are the
##        daylight radiances and tints. Exempt by ROLE, and checked for the two
##        properties the daylight look actually depends on by
##        `test_daylight_tints_are_bright_and_cool`.
##      - `SKY_NIGHT_TOP` and `SKY_NIGHT_HORIZON` are radiances of a night sky
##        and are deliberately BELOW the floor.
##      - `FOG_NIGHT` and `AMBIENT_NIGHT` are exempt by ROLE rather than by
##        value: a fog tint and an ambient energy colour are not reflecting
##        anything, so the band simply does not apply to them. What they do owe
##        the game is being dim, and `test_night_tints_stay_dim` checks that.
##
## 2. THE HELPERS. `vary`, `mix`, `shade` and `desaturate` are used per crowd
##    member and per texel, so they have to be deterministic and they have to
##    keep their output legal.
##
## One numerical detail runs through the whole file: `Color` stores 32 bit
## floats while `ALBEDO_MIN` and `ALBEDO_MAX` are 64 bit literals, so a channel
## written as exactly 0.03 comes back as 0.029999999. Every band comparison here
## therefore carries `EPS`. Without it the suite would fail on rounding and teach
## the next reader nothing.

## Slack for the 32 bit storage of `Color`, see the class comment.
const EPS := 0.00001

const EXEMPT_NAMES: PackedStringArray = [
	"SUNLIGHT",
	"SKY_DAY_TOP",
	"SKY_DAY_HORIZON",
	"FOG_DAY",
	"AMBIENT_DAY",
	"FLOODLIGHT",
	"SKY_NIGHT_TOP",
	"SKY_NIGHT_HORIZON",
	"FOG_NIGHT",
	"AMBIENT_NIGHT",
	"TRAIL_HOT",
	"TRAIL_COLD",
	"UI_ACCENT",
	"UI_WARN",
	"UI_GOOD",
]


func suite_name() -> String:
	return "Palette"


## Rec. 709 linear luminance, the same weighting Palette.desaturate uses.
func _luma(c: Color) -> float:
	return c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722


func test_albedo_band() -> void:
	# `Palette` used as an expression is the TYPE, and the parser refuses a non
	# static call on it. Going through an instance gets us the Script object, and
	# with it the real constant map, so this test cannot drift out of date the
	# way a hand copied list of colour names would.
	var probe := Palette.new()
	var script: Script = probe.get_script()
	var constants: Dictionary = script.get_script_constant_map()
	check(constants.size() > 20, "la carte des constantes de Palette est vide ou tronquee")

	var tested := 0
	for key in constants:
		var entry: Variant = constants[key]
		if typeof(entry) != TYPE_COLOR:
			continue
		var colour_name := String(key)
		if EXEMPT_NAMES.has(colour_name) or colour_name.begins_with("_"):
			continue
		var c: Color = entry
		tested += 1
		var lo := minf(c.r, minf(c.g, c.b))
		var hi := maxf(c.r, maxf(c.g, c.b))
		check(lo >= Palette.ALBEDO_MIN - EPS,
			"%s sous le plancher d'albedo (%f < %f)" % [colour_name, lo, Palette.ALBEDO_MIN])
		check(hi <= Palette.ALBEDO_MAX + EPS,
			"%s au dessus du plafond d'albedo (%f > %f)" % [colour_name, hi, Palette.ALBEDO_MAX])

	check(tested >= 20, "trop peu de couleurs d'albedo verifiees (%d)" % tested)
	done()


func test_band_bounds_make_sense() -> void:
	check(Palette.ALBEDO_MIN > 0.0, "le plancher d'albedo doit etre strictement positif")
	check(Palette.ALBEDO_MAX < 1.0, "le plafond d'albedo doit rester sous 1.0")
	check(Palette.ALBEDO_MAX > Palette.ALBEDO_MIN, "bande d'albedo inversee")
	# The band stays wide because the white lines, the posts and the keeper's
	# jersey are what the player reads in a tenth of a second. It is a HARD
	# ceiling all the same: brightness is bought with light, never with albedo.
	check(Palette.ALBEDO_MAX >= 0.6, "bande trop etroite pour les blancs porteurs de l'image")
	done()


func test_lights_sit_above_the_band() -> void:
	# The emitters. Exempt because they are added to the frame, never reflected,
	# and this proves the exemption is used for what it was granted for.
	var flood := Palette.FLOODLIGHT
	check(maxf(flood.r, maxf(flood.g, flood.b)) > Palette.ALBEDO_MAX,
		"FLOODLIGHT devrait depasser la bande, c'est une couleur de lumiere")
	check(maxf(Palette.TRAIL_HOT.r, Palette.TRAIL_COLD.b) > Palette.ALBEDO_MAX,
		"les trainees additives doivent depasser la bande")
	check(maxf(Palette.UI_ACCENT.b, Palette.UI_WARN.r) > Palette.ALBEDO_MAX,
		"les couleurs d'interface doivent rester franches, hors bande")
	check(maxf(Palette.UI_GOOD.g, 0.0) > Palette.ALBEDO_MAX,
		"le vert de validation doit rester franc")
	done()


func test_daylight_tints_are_bright_and_cool() -> void:
	# The daylight set is what the game boots on, so it gets its own guard rails.
	#
	# 1. The sun is an emitter like FLOODLIGHT and must sit above the band.
	var sun := Palette.SUNLIGHT
	check(maxf(sun.r, maxf(sun.g, sun.b)) > Palette.ALBEDO_MAX,
		"SUNLIGHT devrait depasser la bande, c'est une couleur de lumiere")
	# Warm, but only just: a sun tinted hard turns the pelouse olive.
	check(sun.r > sun.b, "le soleil de fin d'apres midi doit tirer vers le chaud")
	check(sun.b > 0.8, "un soleil trop chaud vire la pelouse a l'olive")

	# 2. The daylight sky has to be clearly brighter than the night one, or the
	#    whole point of the change is lost.
	var day_luma := _luma(Palette.SKY_DAY_HORIZON)
	var night_luma := _luma(Palette.SKY_NIGHT_HORIZON)
	check(day_luma > night_luma * 5.0,
		"le ciel de jour doit etre franchement plus clair que celui de nuit (%f vs %f)"
			% [day_luma, night_luma])
	check(_luma(Palette.SKY_DAY_HORIZON) > _luma(Palette.SKY_DAY_TOP),
		"l'horizon diurne doit etre plus pale que le zenith")
	check(Palette.SKY_DAY_TOP.b > Palette.SKY_DAY_TOP.r * 2.0,
		"le zenith d'un ciel clair doit etre franchement bleu")

	# 3. The fill light and the aerial perspective are BLUE. That is what makes a
	#    daylight shadow read as a shadow instead of as darker grass.
	check(Palette.AMBIENT_DAY.b > Palette.AMBIENT_DAY.r,
		"AMBIENT_DAY doit tirer vers le bleu, c'est la lumiere du ciel")
	check(Palette.FOG_DAY.b > Palette.FOG_DAY.r,
		"FOG_DAY doit tirer vers le bleu, c'est de la perspective aerienne")
	check(_luma(Palette.AMBIENT_DAY) > _luma(Palette.AMBIENT_NIGHT) * 3.0,
		"l'ambiante de jour doit remplir les ombres bien plus que celle de nuit")
	done()


func test_night_sky_sits_below_the_band() -> void:
	# A night sky that respected the albedo floor would be a grey ceiling: the
	# whole point of a floodlit match is that everything off the pitch is darker
	# than any real surface can be.
	var sky := Palette.SKY_NIGHT_TOP
	check(maxf(sky.r, maxf(sky.g, sky.b)) < Palette.ALBEDO_MIN,
		"SKY_NIGHT_TOP devrait passer sous le plancher, c'est un ciel de nuit")
	check(Palette.SKY_NIGHT_HORIZON.r > Palette.SKY_NIGHT_TOP.r,
		"l'horizon doit etre plus clair que le zenith, c'est le halo des tribunes")
	check(Palette.SKY_NIGHT_HORIZON.r > Palette.SKY_NIGHT_HORIZON.b,
		"le halo au dessus des tribunes doit tirer vers l'orange sodium")
	done()


func test_night_tints_stay_dim() -> void:
	# FOG_NIGHT and AMBIENT_NIGHT are exempt by role, not by value: they tint a
	# volume and an ambient term rather than a surface. What they still owe the
	# game is being dim, or the night stops being a night.
	var fog := Palette.FOG_NIGHT
	var fog_luma := fog.r * 0.2126 + fog.g * 0.7152 + fog.b * 0.0722
	check(fog_luma < 0.10, "FOG_NIGHT trop lumineux pour une nuit (%f)" % fog_luma)
	var amb := Palette.AMBIENT_NIGHT
	var amb_luma := amb.r * 0.2126 + amb.g * 0.7152 + amb.b * 0.0722
	check(amb_luma < 0.20, "AMBIENT_NIGHT trop lumineux pour une nuit (%f)" % amb_luma)
	# Both are cool: the fill under floodlights comes from the sky, not the lamps.
	check(fog.b > fog.r, "FOG_NIGHT doit tirer vers le bleu")
	check(amb.b > amb.r, "AMBIENT_NIGHT doit tirer vers le bleu")
	done()


func test_keeper_reads_brighter_than_the_shooter() -> void:
	# The readable silhouette rule: the keeper must pop out of the frame harder
	# than the shooter, or the player cannot judge a dive in a tenth of a second.
	var keeper := Palette.KEEPER_JERSEY
	var shooter := Palette.SHOOTER_JERSEY
	var keeper_luma := keeper.r * 0.2126 + keeper.g * 0.7152 + keeper.b * 0.0722
	var shooter_luma := shooter.r * 0.2126 + shooter.g * 0.7152 + shooter.b * 0.0722
	check(keeper_luma > shooter_luma * 2.0, "le maillot du gardien doit dominer celui du tireur")
	# The mown stripe is the same hue as the lit grass, only darker.
	check(Palette.GRASS_DARK.g < Palette.GRASS_LIGHT.g, "la bande tondue doit etre plus sombre")
	check(Palette.GRASS_DARK.g > Palette.GRASS_DARK.r, "la bande tondue doit rester verte")
	done()


func test_clamp_albedo() -> void:
	# Too bright: scaled, not per channel clamped, so the hue survives.
	var bright := Palette.clamp_albedo(Color(0.9, 0.8, 0.7, 0.5))
	near(maxf(bright.r, maxf(bright.g, bright.b)), Palette.ALBEDO_MAX, 0.0001,
		"le canal le plus clair doit atterrir sur le plafond")
	check(bright.r > bright.g and bright.g > bright.b, "l'ordre des canaux doit survivre")
	near(bright.a, 0.5, 0.0001, "l'alpha doit etre preserve")

	# Too dark: lifted onto the floor.
	var dark := Palette.clamp_albedo(Color(0.0, 0.0, 0.0, 1.0))
	near(dark.r, Palette.ALBEDO_MIN, 0.0001, "le noir doit remonter sur le plancher")
	near(dark.g, Palette.ALBEDO_MIN, 0.0001, "le noir doit remonter sur le plancher")
	near(dark.b, Palette.ALBEDO_MIN, 0.0001, "le noir doit remonter sur le plancher")

	# Already legal: untouched.
	var legal := Palette.clamp_albedo(Palette.SKIN)
	near(legal.r, Palette.SKIN.r, 0.0001, "une couleur deja legale ne doit pas bouger")
	near(legal.g, Palette.SKIN.g, 0.0001, "une couleur deja legale ne doit pas bouger")
	near(legal.b, Palette.SKIN.b, 0.0001, "une couleur deja legale ne doit pas bouger")

	# A saturated overshoot still comes back inside on every channel.
	var wild := Palette.clamp_albedo(Color(4.0, -2.0, 0.5, 1.0))
	between(wild.r, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "canal rouge borne")
	between(wild.g, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "canal vert borne")
	between(wild.b, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "canal bleu borne")
	done()


func test_vary_is_deterministic_and_legal() -> void:
	var a := Palette.vary(Palette.CROWD_A, 0.37)
	var b := Palette.vary(Palette.CROWD_A, 0.37)
	eq(a, b, "vary doit rendre exactement la meme couleur pour la meme graine")

	var c := Palette.vary(Palette.CROWD_A, 0.38)
	ne(c, a, "deux graines voisines doivent donner deux couleurs differentes")

	# Two thousand spectators, none of them illegal.
	var spread := 0.0
	for i in 200:
		var v := Palette.vary(Palette.CROWD_B, float(i) * 0.611)
		between(v.r, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "vary hors bande (rouge, i=%d)" % i)
		between(v.g, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "vary hors bande (vert, i=%d)" % i)
		between(v.b, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "vary hors bande (bleu, i=%d)" % i)
		spread += absf(v.g - Palette.CROWD_B.g)
	check(spread > 0.0, "vary ne doit pas rendre la couleur de base a l'identique")

	# A zero amount is a no-op on a colour that is already legal.
	var flat := Palette.vary(Palette.SEAT_A, 12.5, 0.0)
	near(flat.r, Palette.SEAT_A.r, 0.0001, "amount nul doit laisser la couleur intacte")
	near(flat.g, Palette.SEAT_A.g, 0.0001, "amount nul doit laisser la couleur intacte")
	near(flat.b, Palette.SEAT_A.b, 0.0001, "amount nul doit laisser la couleur intacte")

	# Alpha rides through untouched.
	var translucent := Palette.vary(Color(0.3, 0.3, 0.3, 0.25), 4.0)
	near(translucent.a, 0.25, 0.0001, "vary doit preserver l'alpha")
	done()


func test_mix() -> void:
	var a := Color(0.1, 0.2, 0.3, 0.4)
	var b := Color(0.5, 0.6, 0.7, 0.8)

	eq(Palette.mix(a, b, 0.0), a, "t = 0 doit rendre la premiere couleur")
	eq(Palette.mix(a, b, 1.0), b, "t = 1 doit rendre la seconde couleur")

	var half := Palette.mix(a, b, 0.5)
	near(half.r, 0.3, 0.0001, "melange au milieu, canal rouge")
	near(half.g, 0.4, 0.0001, "melange au milieu, canal vert")
	near(half.b, 0.5, 0.0001, "melange au milieu, canal bleu")
	near(half.a, 0.6, 0.0001, "melange au milieu, alpha")

	# Overshoot is clamped rather than extrapolated into an illegal colour.
	eq(Palette.mix(a, b, 2.0), b, "t > 1 doit etre borne")
	eq(Palette.mix(a, b, -1.0), a, "t < 0 doit etre borne")
	done()


func test_shade() -> void:
	var base := Palette.GRASS_LIGHT

	var darker := Palette.shade(base, 0.5)
	check(darker.g < base.g, "un facteur inferieur a 1 doit assombrir")
	between(darker.r, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "shade doit rester dans la bande")
	between(darker.g, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "shade doit rester dans la bande")
	between(darker.b, Palette.ALBEDO_MIN - EPS, Palette.ALBEDO_MAX + EPS, "shade doit rester dans la bande")

	var lighter := Palette.shade(base, 1.5)
	check(lighter.g > base.g, "un facteur superieur a 1 doit eclaircir")

	# A wild gain lands on the ceiling instead of blowing out.
	var blown := Palette.shade(base, 40.0)
	near(maxf(blown.r, maxf(blown.g, blown.b)), Palette.ALBEDO_MAX, 0.0001,
		"un gain enorme doit se poser sur le plafond")

	# A negative factor is treated as zero, never as a colour inversion.
	var dead := Palette.shade(base, -3.0)
	near(dead.r, Palette.ALBEDO_MIN, 0.0001, "un facteur negatif doit tomber sur le plancher")

	near(Palette.shade(Color(0.2, 0.3, 0.4, 0.33), 1.0).a, 0.33, 0.0001, "shade doit preserver l'alpha")
	done()


func test_desaturate() -> void:
	var base := Palette.SHOOTER_JERSEY

	var untouched := Palette.desaturate(base, 0.0)
	near(untouched.r, base.r, 0.0001, "amount nul ne doit rien changer")
	near(untouched.g, base.g, 0.0001, "amount nul ne doit rien changer")
	near(untouched.b, base.b, 0.0001, "amount nul ne doit rien changer")

	var grey := Palette.desaturate(base, 1.0)
	near(grey.r, grey.g, 0.0001, "amount plein doit rendre un gris")
	near(grey.g, grey.b, 0.0001, "amount plein doit rendre un gris")
	# The grey is the Rec. 709 luminance, not the channel average: a red jersey
	# must go DARK grey, not mid grey.
	var luma := base.r * 0.2126 + base.g * 0.7152 + base.b * 0.0722
	near(grey.r, luma, 0.0001, "le gris doit etre la luminance lineaire")

	var half := Palette.desaturate(base, 0.5)
	var spread_base := maxf(base.r, maxf(base.g, base.b)) - minf(base.r, minf(base.g, base.b))
	var spread_half := maxf(half.r, maxf(half.g, half.b)) - minf(half.r, minf(half.g, half.b))
	check(spread_half < spread_base, "desaturer doit reduire l'ecart entre les canaux")
	check(spread_half > 0.0, "une desaturation partielle ne doit pas tout aplatir")

	# Overshoot is clamped, and alpha rides through.
	var over := Palette.desaturate(Color(0.6, 0.1, 0.1, 0.7), 4.0)
	near(over.r, over.b, 0.0001, "amount > 1 doit se comporter comme 1")
	near(over.a, 0.7, 0.0001, "desaturate doit preserver l'alpha")

	# It works above the band too, which is why it is not clamped: the sky and
	# the fog are legitimate arguments.
	var hazy := Palette.desaturate(Palette.FLOODLIGHT, 1.0)
	check(hazy.r > Palette.ALBEDO_MAX, "desaturate ne doit pas ramener une lumiere dans la bande")
	done()
