extends SceneTree
## Level DESIGN audit, headless:
##
##   godot --headless --path . --script res://tools/design_audit.gd
##
## The unit suites answer "is this data well formed"; this tool answers the
## other question, the one that actually decides whether a level is any good:
## "can a player standing at the spawn, with the tools this level hands him,
## reach everything the level asks him to reach, and never lock himself out".
##
## It is geometric and conservative on purpose. It works on the level data
## alone, models the world as a set of standable rectangles, and walks them
## with the CINEMATIC BUDGET of docs/LEVELS_V2.md section 2:
##
##   jump             +1.50, horizontal reach 4.6 m
##   one crate        +1.30 to stand on, so +2.80 with the jump on top
##   two crates       +2.60, so +4.10
##   console/corniche +1.17, so +2.67
##   stairs           +4.62, so +6.12, run 7.0 m
##   walkway                 deck 9 m out, then a jump off its end: 13.6 m
##   backdrop ramp    the painted wall of a photo aimed 50 degrees up is a
##                    slope from +5.4 to +10.1, so it needs stairs to board
##
## Every number errs on the side of the PLAYER: the audit only reports what is
## out of reach even with the most generous reading of the tools available, so
## a report line is a real defect, never a maybe. Exit code is 1 when anything
## was found, so this can gate a build.

## Height gained over the surface you stand on, tool by tool, jump included.
const LIFT_JUMP := 1.50
const LIFT_ONE_CRATE := 2.80
const LIFT_TWO_CRATES := 4.10
const LIFT_CONSOLE := 2.67
const LIFT_STAIRS := 6.12
## Top of the painted ramp of a photo aimed steeply up. Its lower edge sits at
## 5.4 m, so it is only boardable from a flight of stairs: this lift counts
## only when the level hands out both.
const LIFT_BACKDROP_RAMP := 10.1

## Horizontal reach, tool by tool.
const REACH_JUMP := 4.6
## The number that decides whether a puzzle is a puzzle. Jump velocity 6.5
## against gravity 14 gives 0.929 s of flight; at the 8 m/s sprint that is
## 7.43 m of gap, cleared with no photo and no thought. A walkway deck is 8 m
## long, so NO FLAT GAP CAN EVER BE MADE MANDATORY: a crossing that has to
## resist the sprint needs a rise as well as a distance.
const REACH_SPRINT := 7.43
const REACH_STAIRS := 7.0
## A walkway deck runs from 1 m to 9 m in front of the placer, and its far end
## is a standing spot like any other: 9 m of deck plus a 4.6 m jump.
const REACH_WALKWAY := 13.6

## A prop this big on every axis or smaller is a crate: a photo of it is loose,
## so it can be dropped and stacked. Same threshold as PhotoCapture.
const CRATE_MAX := 1.6
## Interact range, so two pickups closer than this fight over the same ray.
const PICKUP_CLEARANCE := 0.7
## Above this, an item sitting on a surface is floating rather than standing.
const STANDING_SLACK := 0.5
## Eye height of the player, which is where a placement is anchored from.
const EYE_HEIGHT := 1.62
## How far the lens prints, copied from PhotoCapture.CAPTURE_DEPTH. Copied and
## not read, because PhotoCapture pulls in Rewind and therefore the Game
## autoload, which --script does not register: this tool stays autoload-free,
## exactly like the unit runner.
const LENS_DEPTH := 12.0

var _defects: Array = []
var _level := 0


func _initialize() -> void:
	print("")
	print("=== VIEWPOINT audit de level design ===")
	for i in LevelDefs.count():
		_level = i
		_audit(LevelDefs.get_def(i))
	_report()
	quit(1 if not _defects.is_empty() else 0)


func _defect(code: String, message: String) -> void:
	var def := LevelDefs.get_def(_level)
	_defects.append({
		"level": _level + 1,
		"name": def.get("name", "?"),
		"code": code,
		"message": message,
	})


# --- The world as rectangles -------------------------------------------------


## Every surface a player can stand on, as {top, min_x, max_x, min_z, max_z}.
## Platforms and decor blocks are solid boxes; a roofed cage is a box you can
## stand on as well (its roof carries collision).
func _surfaces(def: Dictionary) -> Array:
	var out: Array = []
	for platform in def.get("platforms", []):
		out.append(_surface_of(platform["pos"], platform["size"], "sol"))
	for decor in def.get("decor", []):
		var size: Vector3 = decor["size"]
		# Marker slabs are paint, not furniture: standing on one is standing on
		# the floor under it.
		if size.y <= 0.2:
			continue
		out.append(_surface_of(decor["pos"], size, "decor"))
	for erasable in def.get("erasables", []):
		out.append(_surface_of(erasable["pos"], erasable["size"], "bloc lavande"))
	for cage in def.get("cages", []):
		if not cage.get("roof", true):
			continue
		var pos: Vector3 = cage["pos"]
		var size: Vector3 = cage["size"]
		# Cage pos is the center of its FLOOR, so the roof is a full size.y up.
		out.append(_surface_of(pos + Vector3(0, size.y * 0.5, 0), size, "toit de cage"))
	return out


func _surface_of(center: Vector3, size: Vector3, kind: String) -> Dictionary:
	return {
		"top": center.y + size.y * 0.5,
		"min_x": center.x - size.x * 0.5,
		"max_x": center.x + size.x * 0.5,
		"min_z": center.z - size.z * 0.5,
		"max_z": center.z + size.z * 0.5,
		"kind": kind,
	}


## Solid volumes that swallow whatever stands inside them.
func _solids(def: Dictionary) -> Array:
	var out: Array = []
	for platform in def.get("platforms", []):
		out.append({"pos": platform["pos"], "size": platform["size"], "kind": "plateforme"})
	for decor in def.get("decor", []):
		var size: Vector3 = decor["size"]
		if size.y <= 0.2:
			continue
		out.append({"pos": decor["pos"], "size": size, "kind": "decor"})
	for erasable in def.get("erasables", []):
		out.append({"pos": erasable["pos"], "size": erasable["size"], "kind": "bloc lavande"})
	return out


## Horizontal gap between two surfaces, zero when they overlap or touch.
func _gap(a: Dictionary, b: Dictionary) -> float:
	var dx := maxf(maxf(a["min_x"] - b["max_x"], b["min_x"] - a["max_x"]), 0.0)
	var dz := maxf(maxf(a["min_z"] - b["max_z"], b["min_z"] - a["max_z"]), 0.0)
	return Vector2(dx, dz).length()


func _covers(surface: Dictionary, point: Vector3) -> bool:
	return point.x >= surface["min_x"] - 0.05 and point.x <= surface["max_x"] + 0.05 \
		and point.z >= surface["min_z"] - 0.05 and point.z <= surface["max_z"] + 0.05


# --- The tools the level hands out -------------------------------------------


## How many crates the player can drop in this level: one per "caisse" photo,
## plus one per film as long as there is something crate-sized to photograph.
func _crate_count(def: Dictionary) -> int:
	var crates := 0
	for photo in def.get("photos", []):
		if photo["id"] == "caisse":
			crates += 1
	var camera: Dictionary = def.get("camera", {})
	if not camera.is_empty() and _has_crate_model(def):
		crates += int(camera["films"])
	return crates


func _has_crate_model(def: Dictionary) -> bool:
	for group in ["decor", "erasables"]:
		for block in def.get(group, []):
			var size: Vector3 = block["size"]
			if size.x <= CRATE_MAX and size.y <= CRATE_MAX and size.z <= CRATE_MAX:
				return true
	return false


func _photo_ids(def: Dictionary) -> PackedStringArray:
	var ids := PackedStringArray()
	for photo in def.get("photos", []):
		if not ids.has(photo["id"]):
			ids.append(photo["id"])
		# A photo inside a photo is a tool too, once the outer one is placed.
		for prop in PhotoDefs.get_def(photo["id"]).get("props", []):
			if prop["kind"] == "photo" and not ids.has(prop["id"]):
				ids.append(prop["id"])
	return ids


## The highest step this level can offer over a surface, jump included.
func _max_lift(def: Dictionary) -> float:
	var lift := LIFT_JUMP
	var ids := _photo_ids(def)
	if ids.has("escalier"):
		lift = maxf(lift, LIFT_STAIRS)
	if ids.has("console") or ids.has("corniche"):
		lift = maxf(lift, LIFT_CONSOLE)
	var crates := _crate_count(def)
	if crates >= 2:
		lift = maxf(lift, LIFT_TWO_CRATES)
	elif crates == 1:
		lift = maxf(lift, LIFT_ONE_CRATE)
	# A camera can photograph a piece of ground or a wall and put it back as a
	# step, which is at least as good as one crate.
	if not def.get("camera", {}).is_empty():
		lift = maxf(lift, LIFT_ONE_CRATE)
	# The sky ramp: the painted back of a photo aimed up is a slope, but it
	# starts at 5.4 m, so it is worth nothing without stairs to board it.
	if ids.has("escalier") and _has_painted_backdrop(def):
		lift = maxf(lift, LIFT_BACKDROP_RAMP)
	return lift


## True when this level hands out something whose placement paints a backdrop
## wall: a catalog photo with one, or a camera (every shot has a sky back).
func _has_painted_backdrop(def: Dictionary) -> bool:
	if not def.get("camera", {}).is_empty():
		return true
	for id in _photo_ids(def):
		if not PhotoDefs.get_def(id).get("backdrop", {}).is_empty():
			return true
	return false


func _max_reach(def: Dictionary) -> float:
	var reach := REACH_JUMP
	var ids := _photo_ids(def)
	if ids.has("passerelle"):
		reach = maxf(reach, REACH_WALKWAY)
	if ids.has("escalier"):
		reach = maxf(reach, REACH_STAIRS)
	# A shot of anything long enough turns into a plank; the walkway is the
	# most generous thing in the game, so a camera is worth that reach.
	if not def.get("camera", {}).is_empty():
		reach = maxf(reach, REACH_WALKWAY)
	return reach


# --- Reachability ------------------------------------------------------------


## Indices of the surfaces the player can be standing on, walking out from the
## spawn. Going down is always free (falling costs nothing above kill_y);
## going up costs at most _max_lift.
func _reachable(def: Dictionary, surfaces: Array) -> Dictionary:
	return _walk(def, surfaces, _max_lift(def), _max_reach(def))


## The same walk with EMPTY HANDS: one jump, sprinting, and this time the
## walls count. Whatever this reaches is free, and a level whose whole
## solution sits inside it has no puzzle.
func _reachable_barehanded(def: Dictionary, surfaces: Array) -> Dictionary:
	return _walk(def, surfaces, LIFT_JUMP, REACH_SPRINT, _walls(def))


## The blocks that actually stop a walk: a slab tall enough not to be jumped
## (more than 1.5 m over the ground it stands on) AND wide enough to span the
## platform it sits on, so there is no walking around it. A tower or a crate
## is not a wall, it is scenery you skirt; only a full width barrier counts,
## which is exactly the thing a photo is meant to pierce.
func _walls(def: Dictionary) -> Array:
	var out: Array = []
	for solid in _solids(def):
		var pos: Vector3 = solid["pos"]
		var size: Vector3 = solid["size"]
		for platform in def.get("platforms", []):
			var p_pos: Vector3 = platform["pos"]
			var p_size: Vector3 = platform["size"]
			var p_top: float = p_pos.y + p_size.y * 0.5
			if pos.y + size.y * 0.5 <= p_top + LIFT_JUMP:
				continue
			if pos.y - size.y * 0.5 > p_top + 1.75:
				continue
			var spans_x: bool = size.x >= p_size.x * 0.9
			var spans_z: bool = size.z >= p_size.z * 0.9
			if spans_x or spans_z:
				out.append(solid)
				break
	return out


## True when the straight line from a to b runs into one of the walls. The
## player can step around scenery, never through a barrier.
func _blocked(walls: Array, a: Dictionary, b: Dictionary) -> bool:
	return _crosses_wall(walls,
		Vector2((a["min_x"] + a["max_x"]) * 0.5, (a["min_z"] + a["max_z"]) * 0.5),
		Vector2((b["min_x"] + b["max_x"]) * 0.5, (b["min_z"] + b["max_z"]) * 0.5))


## The same test between two world points. Needed because a single platform
## often runs on BOTH sides of its wall (level 4 is one 28 m corridor cut in
## two), so surface connectivity alone cannot see the barrier at all.
func _crosses_wall(walls: Array, from: Vector2, to: Vector2) -> bool:
	if walls.is_empty():
		return false
	for wall in walls:
		var pos: Vector3 = wall["pos"]
		var size: Vector3 = wall["size"]
		var rect := Rect2(pos.x - size.x * 0.5, pos.z - size.z * 0.5, size.x, size.z)
		for step in 41:
			var point: Vector2 = from.lerp(to, float(step) / 40.0)
			if rect.has_point(point):
				return true
	return false


func _walk(def: Dictionary, surfaces: Array, lift: float, reach: float, walls: Array = []) -> Dictionary:
	var spawn: Vector3 = def["spawn"]
	var start: Array = []
	for i in surfaces.size():
		if _covers(surfaces[i], spawn) and surfaces[i]["top"] <= spawn.y + 0.2:
			start.append(i)
	return _walk_from(surfaces, start, lift, reach, walls)


## The same flood, from wherever you already stand. Used to answer the other
## half of the question: not "can he get there" but "can he get BACK". A
## battery at the bottom of a pit he cannot climb out of is not a battery he
## can spend, it is a reason to restart the level.
func _walk_from(surfaces: Array, start: Array, lift: float, reach: float, walls: Array = []) -> Dictionary:
	var open: Array = []
	var seen := {}
	for i in start:
		open.append(i)
		seen[i] = true
	while not open.is_empty():
		var current: int = open.pop_back()
		for i in surfaces.size():
			if seen.has(i):
				continue
			if _gap(surfaces[current], surfaces[i]) > reach:
				continue
			var climb: float = surfaces[i]["top"] - surfaces[current]["top"]
			if climb > lift:
				continue
			if _blocked(walls, surfaces[current], surfaces[i]):
				continue
			seen[i] = true
			open.append(i)
	return seen


## The surface an item stands on: the highest one under it that covers it.
func _support(surfaces: Array, point: Vector3) -> int:
	var best := -1
	for i in surfaces.size():
		if not _covers(surfaces[i], point):
			continue
		if surfaces[i]["top"] > point.y + 0.06:
			continue
		if best < 0 or surfaces[i]["top"] > surfaces[best]["top"]:
			best = i
	return best


func _inside_solid(def: Dictionary, point: Vector3, margin := 0.05) -> Dictionary:
	for solid in _solids(def):
		var pos: Vector3 = solid["pos"]
		var size: Vector3 = solid["size"]
		if absf(point.x - pos.x) < size.x * 0.5 - margin \
				and absf(point.z - pos.z) < size.z * 0.5 - margin \
				and point.y > pos.y - size.y * 0.5 + margin \
				and point.y < pos.y + size.y * 0.5 - margin:
			return solid
	return {}


## Every battery of a level, whatever list it comes from. Lead counts: it is
## worth one battery to a teleporter, which is all this tally is about.
func _all_free_batteries(def: Dictionary) -> Array:
	var out: Array = []
	out.append_array(def.get("batteries", []))
	out.append_array(def.get("sealed_batteries", []))
	return out


func _in_any_cage(def: Dictionary, point: Vector3) -> bool:
	for cage in def.get("cages", []):
		var pos: Vector3 = cage["pos"]
		var size: Vector3 = cage["size"]
		if absf(point.x - pos.x) <= size.x * 0.5 and absf(point.z - pos.z) <= size.z * 0.5 \
				and point.y >= pos.y - 0.05 and point.y <= pos.y + size.y:
			return true
	return false


func _in_sealed_cage(def: Dictionary, point: Vector3) -> bool:
	for cage in def.get("cages", []):
		if not cage.get("sealed", false):
			continue
		var pos: Vector3 = cage["pos"]
		var size: Vector3 = cage["size"]
		if absf(point.x - pos.x) <= size.x * 0.5 and absf(point.z - pos.z) <= size.z * 0.5 \
				and point.y >= pos.y - 0.05 and point.y <= pos.y + size.y:
			return true
	return false


# --- The audit itself --------------------------------------------------------


func _audit(def: Dictionary) -> void:
	var surfaces := _surfaces(def)
	var reachable := _reachable(def, surfaces)

	# What the level asks the player to touch. A battery locked in a steel cage
	# is deliberately NOT in this list: it is a model to photograph, and the
	# unit suite already proves the level hands out a camera for it.
	# "hovers" marks the pickups that float on purpose (a photo hangs at chest
	# height so it reads as an object, not as litter): their height above the
	# ground is art direction, not a defect.
	var targets: Array = []
	for battery_pos in def.get("batteries", []):
		if not _in_sealed_cage(def, battery_pos):
			targets.append({"pos": battery_pos, "what": "une pile", "hovers": false})
	for sealed_pos in def.get("sealed_batteries", []):
		targets.append({"pos": sealed_pos, "what": "une pile plombee", "hovers": false})
	for photo in def.get("photos", []):
		targets.append({"pos": photo["pos"], "what": "la photo %s" % photo["id"], "hovers": true})
	var camera: Dictionary = def.get("camera", {})
	if not camera.is_empty():
		targets.append({"pos": camera["pos"], "what": "l'appareil photo", "hovers": true})
	targets.append({"pos": def["teleporter"]["pos"], "what": "le teleporteur", "hovers": false})

	for target in targets:
		var pos: Vector3 = target["pos"]
		var support := _support(surfaces, pos)
		if support < 0:
			_defect("VIDE", "%s flotte : aucune surface sous elle" % target["what"])
			continue
		var drop: float = pos.y - surfaces[support]["top"]
		# Everything must stay within arm's reach of its support, hovering
		# pickups included: 1.7 m is the interaction range.
		var slack: float = 1.7 if target["hovers"] else STANDING_SLACK
		if drop > slack:
			_defect("FLOTTE", "%s est a %.2f m au dessus de son appui" % [target["what"], drop])
		if not reachable.has(support):
			_defect("HORS_ATTEINTE", "%s repose sur un %s inaccessible (sommet a %.2f m, elevation max du niveau %.2f m)"
				% [target["what"], surfaces[support]["kind"], surfaces[support]["top"], _max_lift(def)])
		var swallowed := _inside_solid(def, pos + Vector3(0, 0.35, 0))
		if not swallowed.is_empty():
			_defect("ENCASTRE", "%s est prise dans un %s" % [target["what"], swallowed["kind"]])

	# Two pickups sharing the same spot fight over the interaction ray.
	for i in targets.size():
		for j in range(i + 1, targets.size()):
			var a: Vector3 = targets[i]["pos"]
			var b: Vector3 = targets[j]["pos"]
			if a.distance_to(b) < PICKUP_CLEARANCE:
				_defect("COLLE", "%s et %s se disputent le meme rayon (%.2f m d'ecart)"
					% [targets[i]["what"], targets[j]["what"], a.distance_to(b)])

	# The spawn itself.
	var spawn: Vector3 = def["spawn"]
	var spawn_solid := _inside_solid(def, spawn)
	if not spawn_solid.is_empty():
		_defect("SPAWN", "le joueur apparait dans un %s" % spawn_solid["kind"])
	if _in_sealed_cage(def, spawn):
		_defect("SPAWN", "le joueur apparait dans une cage d'acier")

	# Marker slabs: they exist to be seen and stood on, so they must lie on a
	# surface the player can reach and must not be buried.
	for decor in def.get("decor", []):
		if not ["teal", "accent"].has(decor.get("color", "")):
			continue
		var pos: Vector3 = decor["pos"]
		var support := _support(surfaces, pos + Vector3(0, 0.1, 0))
		if support < 0:
			_defect("REPERE", "un repere de pose flotte en %.1f, %.1f" % [pos.x, pos.z])
			continue
		if not reachable.has(support):
			_defect("REPERE", "un repere de pose en %.1f, %.1f est sur une surface inaccessible" % [pos.x, pos.z])
		if _in_sealed_cage(def, pos):
			_defect("REPERE", "un repere de pose est enferme dans une cage d'acier")

	# One way drops: a surface you can only leave by dying. Tolerated when the
	# teleporter is down there (the level ends), flagged otherwise.
	var lift := _max_lift(def)
	var reach := _max_reach(def)
	var tele_pos: Vector3 = def["teleporter"]["pos"]
	for i in surfaces.size():
		if not reachable.has(i):
			continue
		var trapped := true
		for j in surfaces.size():
			if i == j:
				continue
			if _gap(surfaces[i], surfaces[j]) > reach:
				continue
			if surfaces[j]["top"] - surfaces[i]["top"] <= lift:
				trapped = false
				break
		if trapped and not _covers(surfaces[i], tele_pos):
			_defect("PIEGE", "un %s a %.2f m est un cul de sac : on y descend, on n'en remonte pas"
				% [surfaces[i]["kind"], surfaces[i]["top"]])

	# TRIVIALITY. A level that hands out photos or a camera is making a promise:
	# that its tools are needed. Walk it again with empty hands, sprinting, and
	# count what a player who never touches a photo can carry to the teleporter.
	# If that already meets the requirement, the level is a corridor.
	var free_hands := _reachable_barehanded(def, surfaces)
	var walls := _walls(def)
	var spawn_flat := Vector2(spawn.x, spawn.z)
	var has_tools: bool = not def.get("photos", []).is_empty() or not def.get("camera", {}).is_empty()
	if has_tools:
		# A battery behind bars costs a photo whatever the bars are made of:
		# steel is never opened, lavender is opened by spending a placement.
		# Neither is free, so neither counts here.
		var tele_support := _support(surfaces, tele_pos)
		var tele_free: bool = tele_support >= 0 and free_hands.has(tele_support) \
			and not _crosses_wall(walls, spawn_flat, Vector2(tele_pos.x, tele_pos.z))
		var free_batteries := 0
		for battery_pos in _all_free_batteries(def):
			if _in_any_cage(def, battery_pos):
				continue
			var support := _support(surfaces, battery_pos)
			if support < 0 or not free_hands.has(support):
				continue
			if _crosses_wall(walls, spawn_flat, Vector2(battery_pos.x, battery_pos.z)):
				continue
			# And the way back, with the same empty hands.
			if tele_support >= 0 and not _walk_from(surfaces, [support], LIFT_JUMP, REACH_SPRINT, walls).has(tele_support):
				continue
			free_batteries += 1
		var required: int = def["teleporter"]["required"]
		if free_batteries >= required and tele_free:
			_defect("TRIVIALE", "%d piles sur %d requises et le teleporteur sont atteignables en sprintant, sans poser une seule photo"
				% [free_batteries, required])

	# THE LENS IGNORES DISTANCE AND OCCLUSION. It prints anything framed
	# between 0.5 m and 12 m, through bars, over ledges, across a void. So a
	# CLIMB is only a climb if what waits at the top cannot simply be shot from
	# the bottom: one photo, and the copy drops at the player's feet.
	#
	# The flag needs both halves to mean anything. The battery must sit where
	# the level clearly built a way up to it (reachable WITH the tools, not
	# barehanded), and it must be printable from a free standing spot. A
	# battery on an island no tool can reach is not a defect: shooting it from
	# across the void IS the level (that is level 19, and it must stay clean).
	#
	# Lead is the answer whenever a climb has to stay a climb: it cannot be
	# printed, so height stays height. Leaden batteries are not in this loop.
	if not def.get("camera", {}).is_empty():
		for battery_pos in def.get("batteries", []):
			# A battery behind bars is a MODEL, whatever the bars are made of:
			# reaching it was never the plan, printing it was. Level 19 is the
			# whole idea, and it must stay clean.
			if _in_any_cage(def, battery_pos):
				continue
			var support := _support(surfaces, battery_pos)
			if support < 0 or free_hands.has(support) or not reachable.has(support):
				continue
			var closest := INF
			for i in surfaces.size():
				if not free_hands.has(i):
					continue
				var stand := Vector3(
					clampf(battery_pos.x, surfaces[i]["min_x"], surfaces[i]["max_x"]),
					surfaces[i]["top"] + 1.62,
					clampf(battery_pos.z, surfaces[i]["min_z"], surfaces[i]["max_z"]))
				closest = minf(closest, stand.distance_to(battery_pos + Vector3(0, 0.35, 0)))
			if closest <= LENS_DEPTH:
				_defect("TRIVIALE", "une pile perchee a %.2f m est a %.1f m d'un sol libre : l'objectif la copie d'en bas et la montee construite pour elle devient facultative (rendez-la plombee, ou eloignez-la de plus de %.0f m)"
					% [surfaces[support]["top"], closest, LENS_DEPTH])

	# A walkway exists to cross something. If every gap this level offers is
	# already within a sprinting jump (7.43 m), the photo is scenery.
	var offers_walkway := false
	for id in _photo_ids(def):
		if id == "passerelle":
			offers_walkway = true
	if offers_walkway:
		var real_gap := 0.0
		for i in surfaces.size():
			if not free_hands.has(i):
				continue
			for j in surfaces.size():
				if i == j or free_hands.has(j):
					continue
				real_gap = maxf(real_gap, _gap(surfaces[i], surfaces[j]))
		if real_gap <= REACH_SPRINT:
			_defect("TRIVIALE", "la passerelle ne franchit rien : le plus large gouffre du niveau (%.2f m) passe au saut sprinte (%.2f m)"
				% [real_gap, REACH_SPRINT])

	# THE INTENDED SHOT, when the marker declares it. A marker says where to
	# STAND; on its own that has never been enough, because what a placement
	# actually does depends on where the player LOOKS, and no test could see
	# that. A marker may therefore carry three more fields:
	#
	#   "photo" : the id it serves        "aim" : the world point to look at
	#   "roll"  : quarter turns of the wheel (2 = the photo upside down)
	#
	# With those, the whole placement is reproducible and two things get
	# checked that used to cost a playthrough to discover.
	for decor in def.get("decor", []):
		if not decor.has("aim") or not decor.has("photo"):
			continue
		_audit_shot(def, surfaces, decor)

	# Teaching: a level that introduces nothing and repeats an earlier subtitle
	# is a filler level.
	var subtitle: String = def.get("subtitle", "")
	for j in _level:
		if LevelDefs.get_def(j).get("subtitle", "") == subtitle:
			_defect("REDITE", "sous-titre identique a celui du niveau %d" % (j + 1))


func _report() -> void:
	if _defects.is_empty():
		print("  aucun defaut de level design sur %d niveaux" % LevelDefs.count())
		print("=======================================")
		print("")
		return
	var current := -1
	for defect in _defects:
		if defect["level"] != current:
			current = defect["level"]
			print("")
			print("  Niveau %d - %s" % [current, defect["name"]])
		print("    [%s] %s" % [defect["code"], defect["message"]])
	print("")
	print("  %d defauts sur %d niveaux" % [_defects.size(), LevelDefs.count()])
	print("=======================================")
	print("")


## Replays one declared placement and checks the two things that decide whether
## it was worth making.
func _audit_shot(def: Dictionary, surfaces: Array, marker: Dictionary) -> void:
	var photo_id: String = marker["photo"]
	var photo := PhotoDefs.get_def(photo_id)
	if photo.is_empty():
		_defect("REPERE", "un repere annonce la photo %s, absente du catalogue" % photo_id)
		return
	var pos: Vector3 = marker["pos"]
	var support := _support(surfaces, pos + Vector3(0, 0.1, 0))
	if support < 0:
		return
	var eye := Vector3(pos.x, surfaces[support]["top"] + EYE_HEIGHT, pos.z)
	var aim: Vector3 = marker["aim"]
	if eye.distance_to(aim) < 0.5:
		_defect("REPERE", "un repere vise un point ou se tient deja le joueur")
		return

	# The anchor: the camera looking at the aim point, rolled by the wheel.
	var basis := Transform3D().looking_at(aim - eye, Vector3.UP).basis
	basis = basis.rotated(-basis.z.normalized(), int(marker.get("roll", 0)) * PI * 0.5)
	var anchor := Transform3D(basis, eye)

	# A. THE PAINTED WALL IS SOLID, and it stands at the photo's own depth,
	# square across the line of sight. So whatever the shot is aimed AT must be
	# nearer than that wall, or the placement seals it away: that is how a
	# battery ends up walled in, and how a flight of stairs ends up facing a
	# cliff of sky 1.2 m above its last step.
	var backdrop: Dictionary = photo.get("backdrop", {})
	if not backdrop.is_empty():
		var depth: float = backdrop["depth"]
		var to_aim: float = eye.distance_to(aim)
		if to_aim > depth:
			_defect("EMMURE", "la pose de %s vise a %.1f m alors que son fond peint se plante a %.1f m : la cible finit derriere un mur plein"
				% [photo_id, to_aim, depth])

	# A bis. AND SO MUST EVERYTHING THE SHOT IS SUPPOSED TO WIN. Aiming short
	# of the wall is not enough: the wall is as wide as the frame, so a battery
	# standing behind its plane and inside its span is sealed away by the very
	# placement meant to reach it. This is the failure that costs a whole level
	# and shows nothing on screen until it is too late.
	if not backdrop.is_empty():
		var wall_depth: float = backdrop["depth"]
		var half := PhotoMath.half_extent_at(wall_depth, PhotoMath.PHOTO_FOV_DEG)
		var to_anchor := anchor.affine_inverse()
		for battery_pos in _all_free_batteries(def):
			var local: Vector3 = to_anchor * (battery_pos + Vector3(0, 0.35, 0))
			if -local.z <= wall_depth:
				continue
			if absf(local.x) <= half * PhotoMath.PHOTO_ASPECT and absf(local.y) <= half:
				_defect("EMMURE", "la pose de %s depuis ce repere plante son mur a %.1f m devant une pile qui est a %.1f m : elle devient inaccessible"
					% [photo_id, wall_depth, -local.z])

	# B. THE PROPS MUST LAND SOMEWHERE THEY EXIST. Grey ground and decor are
	# permanent, so a slab that materializes inside one of them is simply a
	# photo thrown away, with nothing on screen to say so.
	var buried := 0
	var total := 0
	for prim in PhotoDefs.expand_props(photo):
		if prim["kind"] == "battery" or prim["kind"] == "photo_item":
			continue
		if prim.get("loose", false):
			continue
		total += 1
		if not _inside_solid(def, anchor * (prim["center"] as Vector3), 0.15).is_empty():
			buried += 1
	if total > 0 and buried == total:
		_defect("ENTERRE", "la pose de %s depuis ce repere materialise tout son contenu a l'interieur d'un bloc permanent : la photo est perdue"
			% photo_id)
	elif buried > 0:
		_defect("ENTERRE", "la pose de %s depuis ce repere enterre %d de ses %d elements dans un bloc permanent"
			% [photo_id, buried, total])
