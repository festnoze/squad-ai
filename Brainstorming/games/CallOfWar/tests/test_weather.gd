extends WarTest
## Weather moods, the campaign roll, and the signature climate of a place.
##
## Everything under test here is a static function of its arguments, which is
## the whole point: the sky over a given campaign has to be reproducible, and
## none of it may need a running game to be checked.
##
## A few tests reach for `_params_for`, which is private. It is the mood table
## itself: an entry with a missing channel or a sight factor out of range is a
## rendering bug that no public call would report, so it is worth the reach.

const KINDS: PackedInt32Array = [
	Weather.CLEAR, Weather.OVERCAST, Weather.RAIN,
	Weather.FOG, Weather.STORM, Weather.SNOW,
]

const SEEDS: PackedInt32Array = [1942, 7, 20260823, 555111, 99, 314159, 2, 86420]


func suite_name() -> String:
	return "Weather"


# --- Identifiers -------------------------------------------------------------

func test_v1_weather_ids_never_moved() -> void:
	# Nothing persists a weather kind today, but the mood table, the HUD and the
	# climate map all index by these, and v2 added SNOW at the end of the range
	# rather than renumbering. Freeze that.
	eq(Weather.CLEAR, 0, "CLEAR reste 0")
	eq(Weather.OVERCAST, 1, "OVERCAST reste 1")
	eq(Weather.RAIN, 2, "RAIN reste 2")
	eq(Weather.FOG, 3, "FOG reste 3")
	eq(Weather.STORM, 4, "STORM reste 4")
	eq(Weather.SNOW, 5, "SNOW est ajoute en fin de plage")
	eq(Weather.KIND_COUNT, 6, "KIND_COUNT suit l'ajout")
	done()


func test_every_kind_has_its_own_name() -> void:
	var seen := {}
	for k in KINDS:
		var name: String = Weather.name_of(k)
		check(not name.is_empty(), "le ciel %d a un nom" % k)
		check(not seen.has(name), "le nom '%s' n'est utilise qu'une fois" % name)
		seen[name] = true
	eq(seen.size(), Weather.KIND_COUNT, "un nom distinct par ciel")
	done()


# --- Mood table --------------------------------------------------------------

func test_every_kind_has_a_complete_mood() -> void:
	for k in KINDS:
		var p: PackedFloat32Array = Weather._params_for(k)
		eq(p.size(), Weather._P_COUNT, "le ciel %d remplit tous les canaux" % k)
		between(p[Weather._P_OVERCAST], 0.0, 1.0, "couverture nuageuse du ciel %d" % k)
		between(p[Weather._P_RAIN], 0.0, 1.0, "pluie du ciel %d" % k)
		between(p[Weather._P_SNOW], 0.0, 1.0, "neige du ciel %d" % k)
		between(p[Weather._P_FOG_OPACITY], 0.0, 1.0, "opacite de brouillard du ciel %d" % k)
		between(p[Weather._P_FOG_RANGE], 0.05, 1.0, "portee de brouillard du ciel %d" % k)
		between(p[Weather._P_WIND], 0.0, 1.0, "vent du ciel %d" % k)
		between(p[Weather._P_COLD], 0.0, 1.0, "froid du ciel %d" % k)
		between(p[Weather._P_INTENSITY], 0.0, 1.0, "intensite du ciel %d" % k)
		# The clamp in sight_factor() bottoms out at 0.30; a table entry below
		# that would be silently raised and the intended penalty lost.
		between(p[Weather._P_SIGHT], 0.30, 1.0, "facteur de vue du ciel %d" % k)
	done()


func test_bad_kind_falls_back_to_a_clear_sky() -> void:
	for bad in [-1, Weather.KIND_COUNT, 99]:
		var p: PackedFloat32Array = Weather._params_for(bad)
		eq(p.size(), Weather._P_COUNT, "un ciel inconnu rend quand meme une humeur complete")
		eq(p[Weather._P_SIGHT], 1.0, "un ciel inconnu ne penalise pas la vue")
		eq(p[Weather._P_RAIN], 0.0, "un ciel inconnu ne fait pas pleuvoir")
		eq(p[Weather._P_SNOW], 0.0, "un ciel inconnu ne fait pas neiger")
	done()


func test_snow_is_snow_and_not_white_rain() -> void:
	var p: PackedFloat32Array = Weather._params_for(Weather.SNOW)
	eq(p[Weather._P_RAIN], 0.0, "la neige ne pilote pas l'emetteur de pluie")
	check(p[Weather._P_SNOW] > 0.5, "la neige pilote son propre emetteur")
	eq(p[Weather._P_COLD], 1.0, "la neige refroidit le brouillard a fond")
	var rain: PackedFloat32Array = Weather._params_for(Weather.RAIN)
	check(p[Weather._P_WIND] < rain[Weather._P_WIND],
			"un flocon tombe dans moins de vent qu'une goutte, sinon il file droit")
	# Only the storm and the fog cut vision harder than snow.
	check(p[Weather._P_SIGHT] < rain[Weather._P_SIGHT],
			"la neige bouche davantage la vue que la pluie")
	done()


func test_visibility_penalties_are_ordered() -> void:
	# Clear, overcast, rain, snow, fog, storm: each one strictly worse than the
	# last. A table edit that breaks the order makes a storm easier to sneak
	# through than a shower.
	var order: PackedInt32Array = [
		Weather.CLEAR, Weather.OVERCAST, Weather.RAIN,
		Weather.SNOW, Weather.FOG, Weather.STORM,
	]
	var previous := 2.0
	for k in order:
		var sight: float = Weather._params_for(k)[Weather._P_SIGHT]
		check(sight < previous,
				"%s doit bouger la vue plus que le ciel precedent" % Weather.name_of(k))
		previous = sight
	done()


# --- Campaign roll -----------------------------------------------------------

func test_roll_is_deterministic_and_in_range() -> void:
	for s in SEEDS:
		for hour in 24:
			var first: int = Weather.roll(s, hour)
			eq(Weather.roll(s, hour), first, "la graine %d rend le meme ciel a %dh" % [s, hour])
			between(float(first), 0.0, float(Weather.KIND_COUNT - 1),
					"ciel valide pour la graine %d a %dh" % [s, hour])
	done()


func test_the_hour_wraps_instead_of_falling_off_the_table() -> void:
	for s in SEEDS:
		eq(Weather.roll(s, 24), Weather.roll(s, 0), "24h vaut minuit")
		eq(Weather.roll(s, -1), Weather.roll(s, 23), "-1h vaut 23h")
	done()


func test_the_campaign_roll_never_snows() -> void:
	# Snow reaches the sky only through a place that carries it. If the hourly
	# roll could produce it on its own, it would fall over the whole pocket at
	# random and the local climate would stop meaning anything.
	for s in SEEDS:
		for hour in 24:
			ne(Weather.roll(s, hour), Weather.SNOW,
					"la graine %d ne doit pas faire neiger a %dh toute seule" % [s, hour])
	done()


func test_the_night_stays_calm() -> void:
	# The one hard band in the distribution: between 22h and 3h the roll only
	# ever reaches its quiet branch, so neither a storm nor a fog bank can turn
	# up in the dark. Night infiltration is planned around that.
	#
	# Note that storms are NOT confined to the afternoon: the 13h-20h rule makes
	# them likelier then, but the ordinary daytime tail can still produce one in
	# the morning. That is the shipped behaviour, deliberately left alone.
	for s in SEEDS:
		for hour in [22, 23, 0, 1, 2, 3]:
			var sky: int = Weather.roll(s, hour)
			ne(sky, Weather.STORM, "pas d'orage a %dh sur la graine %d" % [hour, s])
			ne(sky, Weather.FOG, "pas de banc de brouillard a %dh sur la graine %d" % [hour, s])
	done()


func test_dawn_is_the_only_time_the_roll_makes_mist() -> void:
	for s in SEEDS:
		for hour in 24:
			if Weather.roll(s, hour) != Weather.FOG:
				continue
			check(hour >= 4 and hour <= 8,
					"la brume du tirage appartient au petit matin, pas a %dh" % hour)
	done()


# --- Local climate -----------------------------------------------------------

func test_without_a_climate_the_biased_roll_is_the_plain_roll() -> void:
	for s in SEEDS:
		for hour in 24:
			var plain: int = Weather.roll(s, hour)
			eq(Weather.roll_at(s, hour, -1), plain, "-1 rend le tirage nu")
			eq(Weather.roll_at(s, hour, Weather.KIND_COUNT), plain,
					"un climat hors plage rend le tirage nu")
			eq(Weather.roll_at(s, hour, -99), plain, "un climat absurde rend le tirage nu")
	done()


func test_a_climate_leans_the_roll_without_freezing_it() -> void:
	# The bias is a coin flip per hour, not a certainty. Both halves have to be
	# reachable, otherwise a place is either locked to one sky forever or the
	# climate does nothing at all.
	#
	# Counted over every seed rather than per seed on purpose: twenty four draws
	# at p = 0.62 swing wide enough that a single campaign can legitimately land
	# under half, and a test that fails on a fair sample is worse than no test.
	var kept := 0
	var plain := 0
	var total := 0
	for s in SEEDS:
		for hour in 24:
			total += 1
			if Weather.roll_at(s, hour, Weather.FOG) == Weather.FOG:
				kept += 1
			if Weather.roll(s, hour) == Weather.FOG:
				plain += 1
	check(kept * 2 > total, "le climat domine ses heures (%d sur %d)" % [kept, total])
	check(kept < total, "le climat ne gele pas toutes les heures")
	check(kept > plain + total / 4,
			"le biais change vraiment la donne (%d contre %d sans climat)" % [kept, plain])
	done()


func test_each_campaign_still_meets_its_local_sky() -> void:
	# Per seed this time, but only the weak claim that survives the variance:
	# every campaign sees the climate at least sometimes, and never always.
	for s in SEEDS:
		var kept := 0
		for hour in 24:
			if Weather.roll_at(s, hour, Weather.SNOW) == Weather.SNOW:
				kept += 1
		check(kept >= 8, "la graine %d voit son climat local (%d/24)" % [s, kept])
		check(kept < 24, "la graine %d ne gele pas les 24 heures" % s)
	done()


func test_a_climate_is_stable_for_a_whole_campaign() -> void:
	for s in SEEDS:
		for site_id in 22:
			var first: int = Weather.climate_for(Heightfield.B_MEADOW, 16.0, s, site_id)
			eq(Weather.climate_for(Heightfield.B_MEADOW, 16.0, s, site_id), first,
					"le lieu %d garde son climat sur la graine %d" % [site_id, s])
			between(float(first), 0.0, float(Weather.KIND_COUNT - 1),
					"climat valide pour le lieu %d" % site_id)
	done()


func test_two_places_do_not_all_share_one_sky() -> void:
	for s in SEEDS:
		var seen := {}
		for site_id in 22:
			seen[Weather.climate_for(Heightfield.B_MEADOW, 16.0, s, site_id)] = true
		check(seen.size() >= 2,
				"la graine %d ne donne pas le meme ciel a tous les lieux de plaine" % s)
	done()


func test_standing_water_always_breeds_mist() -> void:
	for s in SEEDS:
		for site_id in 22:
			for biome in [Heightfield.B_MARSH, Heightfield.B_WATER]:
				eq(Weather.climate_for(biome, 16.0, s, site_id), Weather.FOG,
						"le marais et l'eau donnent toujours du brouillard")
	done()


func test_mist_pools_in_the_bottoms() -> void:
	for s in SEEDS:
		for site_id in 22:
			eq(Weather.climate_for(Heightfield.B_FIELD, Weather.LOW_GROUND - 0.5, s, site_id),
					Weather.FOG, "un fond de vallee retient la brume")
	done()


func test_the_high_ground_carries_snow() -> void:
	for s in SEEDS:
		for site_id in 22:
			var high: int = Weather.climate_for(
					Heightfield.B_FIELD, Weather.SNOW_ALTITUDE + 0.5, s, site_id)
			if Weather.ALLOW_SNOW:
				eq(high, Weather.SNOW, "au dessus de l'altitude de neige il neige")
			else:
				ne(high, Weather.SNOW, "neige desactivee : la crete recoit autre chose")
	done()


func test_altitude_beats_the_biome_it_stands_on() -> void:
	# A wood on the ridge is still the ridge. The altitude rule runs first on
	# purpose; this pins the precedence so a later edit cannot invert it.
	if not Weather.ALLOW_SNOW:
		check(true, "regle sans objet quand la neige est desactivee")
		done()
		return
	for biome in [Heightfield.B_FIELD, Heightfield.B_MEADOW, Heightfield.B_FOREST]:
		eq(Weather.climate_for(biome, Weather.SNOW_ALTITUDE + 4.0, 1942, 3), Weather.SNOW,
				"l'altitude prime sur le biome %d" % biome)
	done()


# --- Biome vote around a site ------------------------------------------------

func test_the_biome_vote_never_returns_a_man_made_surface() -> void:
	# The bug this guards: sampling the biome AT a site centre always came back
	# B_ROAD, because every site is flattened and roaded there. Every one of the
	# twenty two sites got the same answer and the marshes never got their mist.
	var layout := Layout.new(1942)
	var field := Heightfield.new(layout)
	for site: Layout.Site in layout.sites:
		var voted: int = Weather.site_biome(field, site.center, site.radius)
		ne(voted, Heightfield.B_ROAD, "le vote de biome ignore les routes")
		ne(voted, Heightfield.B_VILLAGE, "le vote de biome ignore les villages")
	done()


func test_the_biome_vote_sees_more_than_one_kind_of_country() -> void:
	var layout := Layout.new(1942)
	var field := Heightfield.new(layout)
	var seen := {}
	for site: Layout.Site in layout.sites:
		seen[Weather.site_biome(field, site.center, site.radius)] = true
	check(seen.size() >= 2, "les vingt deux lieux ne sont pas tous dans le meme pays")
	done()


func test_the_biome_vote_survives_a_missing_height_field() -> void:
	# Called during startup, before anything guarantees the world is built.
	var voted: int = Weather.site_biome(null, Vector2(120.0, -340.0), 48.0)
	eq(voted, Heightfield.B_MEADOW, "sans relief le vote retombe sur la prairie")
	done()


func test_a_campaign_always_offers_more_than_one_weather() -> void:
	# End to end over the real world: build the pocket, read every site's
	# climate the way Main does, and check the player will actually meet a
	# variety of skies rather than twenty two identical villages.
	for s in [1942, 7, 99]:
		var layout := Layout.new(s)
		var field := Heightfield.new(layout)
		var seen := {}
		for site: Layout.Site in layout.sites:
			var biome: int = Weather.site_biome(field, site.center, site.radius)
			var ground: float = field.height_at(site.center.x, site.center.y)
			seen[Weather.climate_for(biome, ground, s, site.id)] = true
		check(seen.size() >= 3,
				"la graine %d propose au moins trois ciels differents (%d)" % [s, seen.size()])
	done()
