## Campaign data table.
##
## This file holds no state and touches no node: it only knows how to turn the
## deterministic `Layout` of the world into the list of missions the player is
## offered. `ObjectiveTracker` (2.32) owns every runtime decision.
##
## Design note about positions. `build_campaign()` runs at startup, long before
## the streaming layer has built any site, so `GameWorld.built_site()` returns
## null for almost every site. An objective is therefore first placed on the
## centre of its host site, at the flattened ground height baked into
## `Layout.Site.ground`. Each objective also remembers which anchor key it wants
## (`_anchor`) and which site owns it (`_site_id`), so the tracker can snap the
## objective onto the real `SiteBuilder.BuiltSite.objective_anchors` position as
## soon as that site is streamed in. A site centre is always within its own
## radius, so the objective is never misleading in the meantime.
class_name MissionDefs
extends RefCounted

# --- Objective kinds -------------------------------------------------------

const O_CAPTURE := 0        # tenir la zone jusqu'a ce qu'il n'y ait plus d'axe
const O_DESTROY := 1        # detruire une cible (depot, canon, mat radio)
const O_RESCUE := 2         # liberer des prisonniers
const O_ASSASSINATE := 3    # tuer un officier
const O_SABOTAGE := 4       # poser une charge et s'eloigner
const O_DEFEND := 5         # tenir une position pendant N secondes
const O_RECON := 6          # atteindre un point d'observation
const O_AMBUSH := 7         # detruire un convoi

const KIND_COUNT := 8

# --- Anchor keys published by SiteBuilder.BuiltSite.objective_anchors ------

const ANCHOR_FUEL := "fuel"
const ANCHOR_RADIO := "radio"
const ANCHOR_FLAG := "flag"
const ANCHOR_CAGE := "cage"
const ANCHOR_OFFICER := "officer"
const ANCHOR_AA := "aa"

## A satellite site farther than this from its sector is not used for a chain.
const _SATELLITE_RANGE := 900.0
## Hard bounds on a sector chain, per the campaign design.
const _CHAIN_MIN := 2
const _CHAIN_MAX := 4

## Generic prefixes `Layout._decorate_name()` puts in front of a place name.
const _NAME_PREFIXES: PackedStringArray = [
	"Terrain d'aviation de ", "Carrefour de ", "Blockhaus de ", "Ruines de ",
	"Ferme de ", "Camp de ", "Pont de ",
]
## Letters that trigger the elision of "de" into "d'".
const _VOWELS := "aeiouyhéèêâîôû"


## One campaign objective. Everything above the separator is the public
## contract; the underscore members below are private extensions read only by
## `ObjectiveTracker`.
class Objective extends RefCounted:
	var id: int = -1
	var kind: int = O_CAPTURE
	var sector_id: int = -1
	var title: String = ""
	var description: String = ""
	var position: Vector3 = Vector3.ZERO
	var radius: float = 30.0
	var target_count: int = 1
	var time_limit: float = 0.0
	var reward_text: String = ""
	var prerequisite: int = -1

	# --- private extensions ------------------------------------------------
	## Site the objective physically sits on (may differ from `sector_id`).
	var _site_id: int = -1
	## Wanted key in `SiteBuilder.BuiltSite.objective_anchors`, "" when none.
	var _anchor: String = ""
	## Tag matched by `ObjectiveTracker.report_destroyed()`.
	var _tag: String = ""
	## Rank of the objective inside its sector chain, starting at 0.
	var _order: int = 0
	## True once the anchor has been snapped onto the real built site.
	var _anchor_done: bool = false

	func _to_string() -> String:
		return "Objective(%d, %s)" % [id, title]


## Internal planning step, before the texts are written.
class _Step extends RefCounted:
	var kind: int
	var host: Layout.Site
	var anchor: String

	func _init(step_kind: int, host_site: Layout.Site, anchor_key: String) -> void:
		kind = step_kind
		host = host_site
		anchor = anchor_key


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

## Builds the full campaign objective list from the world layout.
## Returns Array[Objective], ordered sector by sector, closest sector first.
static func build_campaign(layout: Layout, world: GameWorld) -> Array:
	var result: Array = []
	if layout == null:
		push_error("MissionDefs.build_campaign: layout is null")
		return result

	var sector_ids: PackedInt32Array = layout.sector_ids()
	if sector_ids.is_empty():
		push_warning("MissionDefs.build_campaign: the layout exposes no sector")
		return result

	var spawn: Vector2 = layout.spawn_point()

	# Sectors, ordered by distance to the drop zone: the campaign then reads
	# like a march inland instead of a random shopping list.
	var sectors: Array = []
	for sid in sector_ids:
		var site: Layout.Site = layout.site_by_id(sid)
		if site != null:
			sectors.append(site)
	sectors.sort_custom(func(a: Layout.Site, b: Layout.Site) -> bool:
		return a.center.distance_squared_to(spawn) < b.center.distance_squared_to(spawn))

	# Every non sector site becomes a satellite of the closest sector. Those are
	# the fuel depots, radio masts and prison camps a chain can send you to.
	var satellites: Dictionary = {}
	for site in sectors:
		satellites[site.id] = []
	for site in layout.sites:
		if site.is_sector:
			continue
		var best_id: int = -1
		var best_distance: float = _SATELLITE_RANGE
		for sector in sectors:
			var d: float = site.center.distance_to(sector.center)
			if d < best_distance:
				best_distance = d
				best_id = sector.id
		if best_id >= 0:
			(satellites[best_id] as Array).append(site)

	var next_id: int = 1
	for sector in sectors:
		var rng := RandomNumberGenerator.new()
		rng.seed = _mix_seed(layout.world_seed, sector.id)
		var steps: Array = _plan_for(sector, satellites.get(sector.id, []) as Array, rng)
		var previous: int = -1
		var order: int = 0
		for step in steps:
			var obj := _make_objective(next_id, step as _Step, sector, rng, world)
			obj.prerequisite = previous
			obj._order = order
			result.append(obj)
			previous = obj.id
			next_id += 1
			order += 1

	return result


## French name of a kind, used by the journal and the map.
static func kind_name(kind: int) -> String:
	match kind:
		O_CAPTURE:
			return "Capture"
		O_DESTROY:
			return "Destruction"
		O_RESCUE:
			return "Libération"
		O_ASSASSINATE:
			return "Élimination"
		O_SABOTAGE:
			return "Sabotage"
		O_DEFEND:
			return "Défense"
		O_RECON:
			return "Reconnaissance"
		O_AMBUSH:
			return "Embuscade"
	return "Mission"


## One glyph for the HUD compass and the map pins.
## Plain capitals on purpose: the engine default font ships a narrow glyph set
## and a missing symbol would draw an empty box on the compass.
static func kind_icon(kind: int) -> String:
	match kind:
		O_CAPTURE:
			return "C"
		O_DESTROY:
			return "D"
		O_RESCUE:
			return "P"
		O_ASSASSINATE:
			return "X"
		O_SABOTAGE:
			return "S"
		O_DEFEND:
			return "T"
		O_RECON:
			return "R"
		O_AMBUSH:
			return "E"
	return "?"


## Marker colour used by the tracker when it asks `Vfx.add_marker()`.
## Private extension, not part of the contract.
static func _marker_color(kind: int) -> Color:
	match kind:
		O_CAPTURE:
			return Color(0.32, 0.78, 1.0)
		O_DESTROY:
			return Color(1.0, 0.46, 0.16)
		O_RESCUE:
			return Color(0.42, 1.0, 0.52)
		O_ASSASSINATE:
			return Color(1.0, 0.28, 0.30)
		O_SABOTAGE:
			return Color(1.0, 0.74, 0.22)
		O_DEFEND:
			return Color(0.66, 0.58, 1.0)
		O_RECON:
			return Color(0.85, 0.90, 0.96)
		O_AMBUSH:
			return Color(1.0, 0.60, 0.42)
	return Color(1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# Chain planning
# ---------------------------------------------------------------------------

static func _plan_for(sector: Layout.Site, sats: Array, rng: RandomNumberGenerator) -> Array:
	var steps: Array = []

	# A satellite mission opens the chain roughly two times out of three: it
	# gives the sector a periphery instead of a single blob of buildings.
	var opener: _Step = _satellite_step(sats, rng)
	if opener != null and rng.randf() < 0.68:
		steps.append(opener)

	var kind: int = sector.kind
	if kind == Layout.SITE_AIRFIELD:
		steps.append(_Step.new(O_SABOTAGE, sector, ANCHOR_FUEL))
		steps.append(_Step.new(O_DESTROY, sector, ANCHOR_AA))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_BUNKER:
		steps.append(_Step.new(O_DESTROY, sector, ANCHOR_AA))
		steps.append(_Step.new(O_SABOTAGE, sector, ANCHOR_RADIO))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_CAMP:
		steps.append(_Step.new(O_RECON, sector, ""))
		steps.append(_Step.new(O_RESCUE, sector, ANCHOR_CAGE))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_CHURCH_TOWN:
		steps.append(_Step.new(O_RECON, sector, ""))
		steps.append(_Step.new(O_ASSASSINATE, sector, ANCHOR_OFFICER))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
		steps.append(_Step.new(O_DEFEND, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_CROSSROADS:
		steps.append(_Step.new(O_AMBUSH, sector, ""))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
		steps.append(_Step.new(O_DEFEND, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_BRIDGE:
		steps.append(_Step.new(O_RECON, sector, ""))
		steps.append(_Step.new(O_SABOTAGE, sector, ""))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_RUIN:
		steps.append(_Step.new(O_RECON, sector, ""))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
		steps.append(_Step.new(O_DEFEND, sector, ANCHOR_FLAG))
	elif kind == Layout.SITE_FARM:
		steps.append(_Step.new(O_DESTROY, sector, ANCHOR_FUEL))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
	else:
		# Village and anything unexpected: decapitate, then take the place.
		if rng.randf() < 0.5:
			steps.append(_Step.new(O_ASSASSINATE, sector, ANCHOR_OFFICER))
		else:
			steps.append(_Step.new(O_DESTROY, sector, ANCHOR_RADIO))
		steps.append(_Step.new(O_CAPTURE, sector, ANCHOR_FLAG))
		if rng.randf() < 0.55:
			steps.append(_Step.new(O_DEFEND, sector, ANCHOR_FLAG))

	# Trim from the middle: the opener and the final capture always survive.
	while steps.size() > _CHAIN_MAX:
		steps.remove_at(1)
	while steps.size() < _CHAIN_MIN:
		steps.insert(0, _Step.new(O_RECON, sector, ""))
	return steps


static func _satellite_step(sats: Array, rng: RandomNumberGenerator) -> _Step:
	if sats.is_empty():
		return null
	var site: Layout.Site = sats[rng.randi_range(0, sats.size() - 1)]
	var kind: int = site.kind
	if kind == Layout.SITE_FARM:
		return _Step.new(O_DESTROY, site, ANCHOR_FUEL)
	if kind == Layout.SITE_BUNKER:
		return _Step.new(O_DESTROY, site, ANCHOR_AA)
	if kind == Layout.SITE_CAMP:
		return _Step.new(O_RESCUE, site, ANCHOR_CAGE)
	if kind == Layout.SITE_AIRFIELD:
		return _Step.new(O_SABOTAGE, site, ANCHOR_FUEL)
	if kind == Layout.SITE_CROSSROADS:
		return _Step.new(O_AMBUSH, site, "")
	if kind == Layout.SITE_BRIDGE:
		return _Step.new(O_SABOTAGE, site, "")
	if kind == Layout.SITE_RUIN:
		return _Step.new(O_RECON, site, "")
	if kind == Layout.SITE_CHURCH_TOWN or kind == Layout.SITE_VILLAGE:
		return _Step.new(O_ASSASSINATE, site, ANCHOR_OFFICER)
	return _Step.new(O_DESTROY, site, ANCHOR_RADIO)


static func _make_objective(new_id: int, step: _Step, sector: Layout.Site,
		rng: RandomNumberGenerator, world: GameWorld) -> Objective:
	var obj := Objective.new()
	obj.id = new_id
	obj.kind = step.kind
	obj.sector_id = sector.id
	obj._site_id = step.host.id
	obj._anchor = step.anchor
	obj._tag = "%s_%d" % [step.anchor if not step.anchor.is_empty() else "site", step.host.id]
	obj.position = _site_position(step.host, world)
	obj.radius = _radius_for(step.kind, step.host)
	obj.target_count = _targets_for(step.kind, rng)
	obj.time_limit = _time_for(step.kind, rng)

	var variant: int = rng.randi_range(0, 2)
	var minutes: int = int(round(obj.time_limit / 60.0))
	obj.title = _fill(_titles(step.kind, step.anchor)[variant], step.host, sector,
			obj.target_count, minutes)
	obj.description = _fill(_descriptions(step.kind, step.anchor)[variant], step.host,
			sector, obj.target_count, minutes)
	var rewards: PackedStringArray = _rewards(step.kind, step.anchor)
	obj.reward_text = _fill(rewards[variant % rewards.size()], step.host, sector,
			obj.target_count, minutes)
	return obj


static func _site_position(site: Layout.Site, world: GameWorld) -> Vector3:
	var y: float = site.ground
	if world != null and absf(y) < 0.001:
		# `bake_sites()` has not run yet, ask the streaming layer instead.
		y = world.ground_y(site.center.x, site.center.y)
	return Vector3(site.center.x, y, site.center.y)


static func _radius_for(kind: int, site: Layout.Site) -> float:
	match kind:
		O_CAPTURE:
			return clampf(site.radius * 0.9, 30.0, 60.0)
		O_DEFEND:
			return clampf(site.radius * 0.8, 26.0, 50.0)
		O_ASSASSINATE:
			return clampf(site.radius, 45.0, 90.0)
		O_RESCUE:
			return 22.0
		O_AMBUSH:
			return 38.0
		O_DESTROY:
			return 14.0
		O_SABOTAGE:
			return 12.0
		O_RECON:
			return 14.0
	return 25.0


static func _targets_for(kind: int, rng: RandomNumberGenerator) -> int:
	match kind:
		O_RESCUE:
			return rng.randi_range(3, 6)
		O_AMBUSH:
			return rng.randi_range(3, 5)
	return 1


static func _time_for(kind: int, rng: RandomNumberGenerator) -> float:
	if kind == O_DEFEND:
		return float(rng.randi_range(150, 240))
	return 0.0


static func _mix_seed(world_seed: int, site_id: int) -> int:
	var h: int = world_seed ^ (site_id * 0x9E3779B1)
	h = (h ^ (h >> 15)) * 0x85EBCA6B
	h = (h ^ (h >> 13)) * 0xC2B2AE35
	return absi(h ^ (h >> 16))


## Placeholders understood by the text pools:
## `{lieu}`   short place name ("Osmanville" for "Terrain d'aviation de Osmanville")
## `{de}`     the same name introduced by de / d' / du, correctly elided
## `{secteur}` and `{de_secteur}` the same two for the sector the chain belongs to
## `{site}`   the full decorated name, kept for anything that wants the site kind
## `{nb}` `{min}` counts
static func _fill(template: String, host: Layout.Site, sector: Layout.Site,
		count: int, minutes: int) -> String:
	var lieu: String = _short_name(host.display_name)
	var secteur: String = _short_name(sector.display_name)
	return template.format({
		"site": host.display_name,
		"lieu": lieu,
		"de": _of_name(lieu),
		"secteur": secteur,
		"de_secteur": _of_name(secteur),
		"nb": count,
		"min": maxi(1, minutes),
	})


## Strips the generic prefix `Layout` glues in front of a place name, so a title
## reads "Nettoyer Mandeville" instead of "Nettoyer Camp de Mandeville".
static func _short_name(display: String) -> String:
	for prefix in _NAME_PREFIXES:
		if display.begins_with(prefix):
			return display.substr(prefix.length())
	return display


## "de Lestre", "d'Osmanville", "du Molay". French elision matters here: the
## texts are read by the player on every mission screen.
static func _of_name(place: String) -> String:
	if place.is_empty():
		return "de la zone"
	if place.begins_with("Le "):
		return "du " + place.substr(3)
	if place.begins_with("Les "):
		return "des " + place.substr(4)
	var first: String = place.substr(0, 1).to_lower()
	if _VOWELS.contains(first):
		return "d'" + place
	return "de " + place


# ---------------------------------------------------------------------------
# French mission texts
#
# Three variants per kind, picked with the per site RNG so a campaign always
# reads the same for a given world seed. The tone rotates between radio orders
# from London, notes passed by the Resistance and raw intelligence reports.
# ---------------------------------------------------------------------------

static func _titles(kind: int, anchor: String) -> PackedStringArray:
	match kind:
		O_CAPTURE:
			return PackedStringArray([
				"Hisser les couleurs sur {lieu}",
				"Nettoyer {lieu}",
				"{lieu} doit tomber",
			])
		O_DEFEND:
			return PackedStringArray([
				"Tenir {lieu}",
				"Le contre-choc",
				"{min} minutes debout",
			])
		O_RESCUE:
			return PackedStringArray([
				"Les hommes de la cage",
				"Avant le peloton",
				"Sortir {nb} camarades {de}",
			])
		O_ASSASSINATE:
			return PackedStringArray([
				"L'homme au ceinturon noir",
				"Le Hauptmann {de}",
				"Décapiter la garnison",
			])
		O_RECON:
			return PackedStringArray([
				"Le point haut {de}",
				"Relever leurs positions",
				"Un croquis vaut un régiment",
			])
		O_AMBUSH:
			return PackedStringArray([
				"Le convoi de six heures",
				"Rien ne passe à {lieu}",
				"Embuscade sur la route {de}",
			])
		O_SABOTAGE:
			if anchor == ANCHOR_RADIO:
				return PackedStringArray([
					"Charge au pied du mât",
					"Couper la voix de l'occupant",
					"Le silence {de}",
				])
			if anchor == ANCHOR_FUEL:
				return PackedStringArray([
					"Charge sous les cuves",
					"Assécher la Wehrmacht",
					"Le feu d'artifice {de}",
				])
			return PackedStringArray([
				"Une mèche et deux minutes",
				"Faire sauter {lieu}",
				"Le plastic {de}",
			])
		O_DESTROY:
			if anchor == ANCHOR_RADIO:
				return PackedStringArray([
					"Faire taire {lieu}",
					"Le mât {de}",
					"Plus un mot vers Caen",
				])
			if anchor == ANCHOR_AA:
				return PackedStringArray([
					"Ouvrir le ciel",
					"La batterie {de}",
					"Un couloir pour Londres",
				])
			return PackedStringArray([
				"Assécher la Wehrmacht",
				"Le dépôt {de}",
				"Rien pour leurs moteurs",
			])
	return PackedStringArray(["Mission à {lieu}", "Objectif {de}", "Ordre pour {lieu}"])


static func _descriptions(kind: int, anchor: String) -> PackedStringArray:
	match kind:
		O_CAPTURE:
			return PackedStringArray([
				"La garnison {de} tient encore chaque carrefour et chaque grange du village. Prenez la place, puis restez debout au milieu jusqu'à ce que plus un feldgrau ne bouge.",
				"Londres veut {lieu} avant la fin de la semaine, et Londres n'aime pas attendre. Il faudra la nettoyer maison par maison, il n'y a pas d'autre chemin.",
				"Le drapeau à croix gammée flotte toujours sur la mairie {de}. Descendez-le, et ne laissez personne le rehisser derrière vous.",
			])
		O_DEFEND:
			return PackedStringArray([
				"La garnison voisine contre-attaque sur {lieu} pour reprendre ce qu'elle vient de perdre. Tenez la position {min} minutes, le maquis remonte par la route de l'ouest.",
				"Ils reviendront, et ils reviendront en nombre : c'est toujours ainsi après une place perdue. Restez dans le périmètre {de} et ne cédez pas un mur.",
				"On vous laisse {min} minutes de mitraille avant que les nôtres arrivent. Ne quittez pas {lieu}, un secteur abandonné est un secteur reperdu.",
			])
		O_RESCUE:
			return PackedStringArray([
				"{nb} maquisards attendent le peloton derrière les barbelés {de}, condamnés depuis mardi. Ouvrez les cages et ramenez-les jusqu'à une position amie.",
				"La Résistance a fait passer un mot : {nb} des nôtres sont parqués à {lieu} et le train part à l'aube. Faites sauter les cadenas et escortez-les hors du secteur.",
				"Le camp {de} garde {nb} prisonniers dont deux opérateurs radio que nous ne pouvons pas perdre. Libérez-les, puis guidez-les vers nos lignes sans les semer en route.",
			])
		O_ASSASSINATE:
			return PackedStringArray([
				"Un officier de la Feldgendarmerie tient {lieu} d'une main de fer et connaît déjà trois noms de notre réseau. Message de Londres : supprimez-le avant qu'il n'en connaisse un quatrième.",
				"Le commandant de la garnison {de} inspecte ses postes chaque jour, toujours à la même heure, toujours au même endroit. Un homme régulier est un homme mort.",
				"Sans lui, la garnison {de_secteur} sera une troupe sans tête pendant deux jours pleins. Trouvez l'officier, et ne le manquez pas du premier coup.",
			])
		O_RECON:
			return PackedStringArray([
				"Grimpez au point d'observation {de} et relevez tout ce qui bouge en contrebas. Rien à faire sauter ce matin, seulement à regarder et à retenir.",
				"Nous attaquons {secteur} à l'aveugle tant que personne n'est monté là-haut. Prenez position, comptez les pièces, comptez les hommes, et redescendez entier.",
				"Un croquis des défenses {de} vaut mieux qu'un régiment de plus. Montez, observez, et surtout ne tirez pas : ce point de vue doit rester le nôtre.",
			])
		O_AMBUSH:
			return PackedStringArray([
				"Un convoi de ravitaillement traverse {lieu} chaque matin, escorte comprise. Laissez entrer la tête de colonne dans le carrefour, puis ne laissez rien en repartir.",
				"La route {de} nourrit toute la garnison {de_secteur} depuis trois semaines. Coupez-la une bonne fois, et ils mangeront leurs chevaux.",
				"Le renseignement annonce {nb} véhicules et leur escorte à {lieu}. Choisissez votre haie, laissez-les s'engager, et ouvrez le feu au dernier moment.",
			])
		O_SABOTAGE:
			if anchor == ANCHOR_RADIO:
				return PackedStringArray([
					"Le mât radio {de} relaie jusqu'à Caen chaque mouvement signalé dans la poche. Placez la charge au pied du pylône, puis reculez de vingt-cinq mètres avant la détonation.",
					"On ne démolit pas un pylône à la carabine, il faut du plastic et de la patience. Posez-le, allumez la mèche, et n'essayez pas d'admirer le travail de trop près.",
					"Coupez le relais {de} et la garnison {de_secteur} deviendra sourde pour la nuit entière. Charge au pied du mât, puis dégagez, le souffle porte loin.",
				])
			if anchor == ANCHOR_FUEL:
				return PackedStringArray([
					"Les cuves {de} remplissent les Panzer qui remontent vers la côte. Posez la charge contre la cuve maîtresse et éloignez-vous, le carburant part d'un seul bloc.",
					"Le dépôt {de} est gardé, éclairé, et parfaitement inflammable. Une charge suffira, à condition d'être à vingt-cinq mètres quand elle parlera.",
					"Londres veut du feu sur {lieu} avant l'aube, assez haut pour être vu de la mer. Amorcez, décrochez, et laissez la nuit s'occuper du reste.",
				])
			return PackedStringArray([
				"L'ouvrage {de} tient tout le passage du secteur {de_secteur}. Fixez la charge sur le point porteur, puis reculez de vingt-cinq mètres et attendez.",
				"Deux bâtons de plastic bien placés valent une compagnie de sapeurs. Posez-les à {lieu}, dégagez, et le passage sera coupé pour un mois.",
				"C'est un travail de patience et de nerfs : on amorce sous leur nez, on s'en va sans courir. La charge est prête, {lieu} vous attend.",
			])
		O_DESTROY:
			if anchor == ANCHOR_RADIO:
				return PackedStringArray([
					"Le mât radio {de} porte les ordres de la division jusqu'aux postes de la côte. Réduisez-le en ferraille et la garnison mettra une heure à demander de l'aide.",
					"Tant que {lieu} émet, chaque coup de feu que vous tirez est signalé en dix minutes. Détruisez l'installation, le reste du secteur deviendra respirable.",
					"Notre opérateur a repéré l'antenne depuis la crête : elle est haute, elle est seule, elle est à vous. Faites-la tomber.",
				])
			if anchor == ANCHOR_AA:
				return PackedStringArray([
					"La Flak {de} interdit tout largage au-dessus du bocage depuis le printemps. Détruisez la pièce et la RAF fera le reste dès la nuit prochaine.",
					"Nos avions contournent {secteur} de vingt kilomètres à cause de cette batterie. Ouvrez-nous un couloir, nous vous enverrons des armes par le ciel.",
					"Le canon {de} a abattu deux appareils en un mois, dont un équipage entier. Réglez cette dette, servant par servant.",
				])
			return PackedStringArray([
				"Le dépôt {de} alimente la colonne blindée qui remonte vers la côte. Faites-le sauter avant l'aube, ils ne comprendront même pas d'où c'est venu.",
				"Sans essence, un Panzer n'est qu'un tas de tôle garé au bord d'un champ. Les cuves {de} sont l'objectif, le reste n'est que décor.",
				"Le renseignement donne {lieu} plein à ras bord depuis le convoi de mardi. Cela fait beaucoup de carburant pour un seul allumage.",
			])
	return PackedStringArray([
		"Un ordre est arrivé de Londres pour {lieu}. Exécutez-le et rendez compte.",
		"La Résistance signale une occasion à {lieu}. Ne la laissez pas passer.",
		"Le secteur {de_secteur} attend un geste de notre part. Faites-le à {lieu}.",
	])


static func _rewards(kind: int, anchor: String) -> PackedStringArray:
	match kind:
		O_CAPTURE:
			return PackedStringArray([
				"Le secteur {de_secteur} passera sous contrôle allié.",
				"Le maquis pourra installer une base sûre à {lieu}.",
				"Une position de repli de plus entre la côte et nous.",
			])
		O_DEFEND:
			return PackedStringArray([
				"{lieu} restera aux mains du maquis.",
				"La contre-attaque brisée, le secteur tiendra seul.",
			])
		O_RESCUE:
			return PackedStringArray([
				"Les prisonniers libérés grossiront les rangs du maquis.",
				"Deux opérateurs radio de plus pour le réseau.",
			])
		O_ASSASSINATE:
			return PackedStringArray([
				"La garnison perdra sa tête et ses ordres.",
				"Les patrouilles du secteur seront désorganisées pendant deux jours.",
			])
		O_RECON:
			return PackedStringArray([
				"Les défenses du secteur apparaîtront sur votre carte.",
				"L'attaque suivante ne se fera plus à l'aveugle.",
			])
		O_AMBUSH:
			return PackedStringArray([
				"La garnison {de_secteur} sera coupée de son ravitaillement.",
				"Munitions et vivres récupérés sur la route.",
			])
		O_SABOTAGE:
			if anchor == ANCHOR_FUEL:
				return PackedStringArray([
					"La colonne blindée restera clouée sur place plusieurs jours.",
					"Plus une goutte d'essence dans le secteur.",
				])
			return PackedStringArray([
				"Le passage sera coupé pour un mois au moins.",
				"Leurs liaisons seront à refaire entièrement.",
			])
		O_DESTROY:
			if anchor == ANCHOR_AA:
				return PackedStringArray([
					"Londres pourra parachuter armes et explosifs sur la poche.",
					"Le ciel du secteur sera de nouveau à nous.",
				])
			if anchor == ANCHOR_RADIO:
				return PackedStringArray([
					"Sans relais, la garnison mettra une heure à demander des renforts.",
					"Vos prochains coups de feu ne seront plus signalés.",
				])
			return PackedStringArray([
				"Leurs blindés rouleront au ralenti, quand ils rouleront.",
				"Le ravitaillement en carburant du secteur est coupé.",
			])
	return PackedStringArray([
		"Un pas de plus vers la libération {de_secteur}.",
	])
