extends ViewTest
## Solvability invariants of the twenty levels: everything the player must reach
## stands on a platform, and enough batteries exist (world + duplicable via
## photos + camera films) to charge every teleporter.
##
## The v4 rules the data has to honor as well: a visual standing cue in every
## level (there is no 3D preview anymore), showcase niches shallow enough for
## the 1.7 m interact range, and at least one level where the only tool is the
## camera (the empty sky photo as a piercing tool).

## Decorative slabs that mark where a precision placement is meant to be shot.
const MARKER_COLORS := ["teal", "accent"]
## Interact range is 1.7 m, so a niche may not be deeper than this.
const MAX_NICHE_DEPTH := 1.2
## A block at most this big on every axis comes out of the film as a loose
## crate, so it is a legitimate subject. Same threshold as PhotoCapture.
const LOOSE_MAX_EXTENT := 1.6


func suite_name() -> String:
	return "level_defs"


func _above_platform(def: Dictionary, point: Vector3, max_height: float) -> bool:
	for platform in def["platforms"]:
		var pos: Vector3 = platform["pos"]
		var size: Vector3 = platform["size"]
		var top := pos.y + size.y * 0.5
		if absf(point.x - pos.x) <= size.x * 0.5 \
				and absf(point.z - pos.z) <= size.z * 0.5 \
				and point.y >= top - 0.05 and point.y <= top + max_height:
			return true
	return false


## True when the point stands inside the volume of a cage no placement breaks.
## Cage "pos" is the center of the cage FLOOR, "size" the whole enclosure.
func _in_sealed_cage(def: Dictionary, point: Vector3) -> bool:
	for cage in def.get("cages", []):
		if not cage.get("sealed", false):
			continue
		var pos: Vector3 = cage["pos"]
		var size: Vector3 = cage["size"]
		if absf(point.x - pos.x) <= size.x * 0.5 \
				and absf(point.z - pos.z) <= size.z * 0.5 \
				and point.y >= pos.y - 0.05 and point.y <= pos.y + size.y:
			return true
	return false


## Every battery of a level, whatever list it comes from.
func _all_batteries(def: Dictionary) -> Array:
	var out: Array = []
	out.append_array(def.get("batteries", []))
	out.append_array(def.get("sealed_batteries", []))
	return out


func test_count() -> void:
	eq(LevelDefs.count(), 25, "vingt-cinq niveaux")
	check(LevelDefs.get_def(-1).is_empty(), "index negatif : vide")
	check(LevelDefs.get_def(25).is_empty(), "index hors borne : vide")
	done()


func test_structure() -> void:
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		check(def.get("name", "") != "", "niveau %d : nom" % (i + 1))
		check(def.get("subtitle", "") != "", "niveau %d : sous-titre" % (i + 1))
		check(not def.get("platforms", []).is_empty(), "niveau %d : au moins une plateforme" % (i + 1))
		check(def.has("teleporter"), "niveau %d : teleporteur" % (i + 1))
		check(def["teleporter"]["required"] > 0, "niveau %d : le teleporteur exige des piles" % (i + 1))
	done()


func test_placements() -> void:
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		check(_above_platform(def, def["spawn"], 3.0), "niveau %d : spawn au dessus d'une plateforme" % (i + 1))
		check(_above_platform(def, def["teleporter"]["pos"], 0.5), "niveau %d : teleporteur pose sur une plateforme" % (i + 1))
		for battery_pos in _all_batteries(def):
			check(_above_platform(def, battery_pos, 0.5), "niveau %d : pile posee sur une plateforme" % (i + 1))
		for photo in def["photos"]:
			check(_above_platform(def, photo["pos"], 2.0), "niveau %d : photo au dessus d'une plateforme" % (i + 1))
			check(not PhotoDefs.get_def(photo["id"]).is_empty(), "niveau %d : photo %s au catalogue" % [i + 1, photo["id"]])
		for cage in def.get("cages", []):
			check(_above_platform(def, cage["pos"], 0.5), "niveau %d : cage posee sur une plateforme" % (i + 1))
			var cage_size: Vector3 = cage["size"]
			check(cage_size.x > 0 and cage_size.y > 0 and cage_size.z > 0, "niveau %d : cage de taille positive" % (i + 1))
		var camera: Dictionary = def.get("camera", {})
		if not camera.is_empty():
			check(_above_platform(def, camera["pos"], 0.5), "niveau %d : appareil pose sur une plateforme" % (i + 1))
			check(camera["films"] > 0, "niveau %d : l'appareil a de la pellicule" % (i + 1))
			check(_has_a_subject(def), "niveau %d : l'appareil a quelque chose a photographier" % (i + 1))
	done()


## A camera is only worth carrying when something in the level is worth
## printing. That used to mean a battery, and it no longer does: a level may
## hand out film purely to copy a CRATE and stack it (level 23 is built on
## exactly that, and its two batteries are leaden on purpose). So the subject
## can be either a battery a film can print, or a block small enough on every
## axis to come back as a loose crate.
func _has_a_subject(def: Dictionary) -> bool:
	if not def["batteries"].is_empty():
		return true
	for group in ["decor", "erasables"]:
		for block in def.get(group, []):
			var size: Vector3 = block["size"]
			if size.x <= LOOSE_MAX_EXTENT and size.y <= LOOSE_MAX_EXTENT and size.z <= LOOSE_MAX_EXTENT:
				return true
	return false


func test_batteries_reachable() -> void:
	# Conservative solvability count. What the player can actually hold:
	#   - every battery standing in the open, leaden ones included (lead is
	#     worth exactly as much to a teleporter, it just never becomes two);
	#   - NOT the batteries locked in a steel cage, which no placement opens:
	#     those are models to photograph, never pickups;
	#   - the batteries a placed photo materializes, following photo-in-photo
	#     chains;
	#   - one copy per film, and only when SOME battery can be printed at all
	#     (a level whose only batteries are leaden gets nothing from its films).
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var available := 0
		var copyable := 0
		for battery_pos in def["batteries"]:
			copyable += 1
			if not _in_sealed_cage(def, battery_pos):
				available += 1
		for sealed_pos in def.get("sealed_batteries", []):
			if not _in_sealed_cage(def, sealed_pos):
				available += 1
		for photo in def["photos"]:
			available += PhotoDefs.battery_count_recursive(photo["id"])
		var camera: Dictionary = def.get("camera", {})
		if not camera.is_empty() and copyable > 0:
			available += camera["films"]
		check(available >= def["teleporter"]["required"],
			"niveau %d : %d piles accessibles pour %d requises" % [i + 1, available, def["teleporter"]["required"]])
	done()


func test_sealed_cages_need_a_lens() -> void:
	# A battery inside a steel cage can only ever leave it as a copy, so the
	# level MUST hand out a camera with film. Without this the level would
	# simply be a locked box, and the test suite would happily call it solvable.
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var caged := 0
		for battery_pos in def["batteries"]:
			if _in_sealed_cage(def, battery_pos):
				caged += 1
		# A leaden battery in a steel cage is lost for good: no film prints it
		# and no placement opens the cage. It must never happen.
		for sealed_pos in def.get("sealed_batteries", []):
			check(not _in_sealed_cage(def, sealed_pos),
				"niveau %d : aucune pile plombee enfermee dans l'acier" % (i + 1))
		if caged == 0:
			continue
		var camera: Dictionary = def.get("camera", {})
		check(not camera.is_empty() and camera.get("films", 0) > 0,
			"niveau %d : une pile sous acier exige un appareil et de la pellicule" % (i + 1))
	done()


func test_new_mechanics_are_taught_alone() -> void:
	# Each refusal gets one level where it is the only new thing, before any
	# level combines them. Steel and lead are the two that need teaching; the
	# gravity of a placed crate is taught by the crate itself.
	var first_steel := -1
	var first_lead := -1
	var both := -1
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var steel := false
		for cage in def.get("cages", []):
			steel = steel or cage.get("sealed", false)
		var lead: bool = not def.get("sealed_batteries", []).is_empty()
		if steel and first_steel < 0:
			first_steel = i
		if lead and first_lead < 0:
			first_lead = i
		if steel and lead and both < 0:
			both = i
	check(first_steel >= 0, "l'acier existe quelque part")
	check(first_lead >= 0, "le plomb existe quelque part")
	check(both < 0 or both > first_steel, "l'acier est enseigne seul avant d'etre combine")
	check(both < 0 or both > first_lead, "le plomb est enseigne seul avant d'etre combine")
	done()


func test_placement_markers() -> void:
	# No 3D ghost preview since v4: each level marks at least one standing spot
	# with a thin tinted slab, otherwise a precision placement is pure guessing.
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var markers := 0
		for decor in def.get("decor", []):
			if MARKER_COLORS.has(decor.get("color", "")):
				markers += 1
				var size: Vector3 = decor["size"]
				check(size.y <= 0.2, "niveau %d : le repere est une dalle plate" % (i + 1))
		check(markers > 0, "niveau %d : au moins un repere de pose au sol" % (i + 1))
	done()


func test_camera_only_levels() -> void:
	# The empty photo is a tool, not a failure: at least one level hands out a
	# camera and NO catalog photo, so piercing has to come from a sky shot.
	var camera_only := 0
	var with_camera := 0
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var camera: Dictionary = def.get("camera", {})
		if camera.is_empty():
			continue
		with_camera += 1
		if def["photos"].is_empty():
			camera_only += 1
	check(with_camera > 0, "au moins un niveau donne un appareil photo")
	check(camera_only > 0, "au moins un niveau n'a que l'appareil pour percer")
	done()


func test_showcase_depth() -> void:
	# Interact range dropped to 1.7 m: no more picking a battery up through a
	# deep showcase. Niche panels stay within MAX_NICHE_DEPTH.
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		for decor in def.get("decor", []):
			if decor.get("color", "") != "battery_tip":
				continue
			var size: Vector3 = decor["size"]
			check(minf(size.x, size.z) <= MAX_NICHE_DEPTH,
				"niveau %d : niche de vitrine a portee de main" % (i + 1))
	done()


func test_cages_are_well_formed() -> void:
	# Any cage that is not steel breaks under a placement catching its center;
	# the lavender/dark tint is lore only. Steel is the one real difference,
	# and it is declared, not inferred.
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		for cage in def.get("cages", []):
			var size: Vector3 = cage["size"]
			check(size.x >= 1.0 and size.z >= 1.0, "niveau %d : cage assez large pour son contenu" % (i + 1))
			check(cage.has("roof"), "niveau %d : la cage declare son toit" % (i + 1))
			check(_above_platform(def, cage["pos"], 0.5), "niveau %d : cage posee sur une plateforme" % (i + 1))
			# Steel and lavender are opposites: a cage is never both.
			check(not (cage.get("sealed", false) and cage.get("erasable", false)),
				"niveau %d : une cage d'acier n'est pas lavande" % (i + 1))
	done()


func test_ground_language_is_taught() -> void:
	# The pale ground is the exception, so it has to be rare and it has to be
	# taught: exactly the levels that need a pierceable floor declare one, and
	# at least one level does, or the language would never be shown.
	var soft_levels := 0
	var soft_slabs := 0
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var here := 0
		for platform in def["platforms"]:
			if platform.get("soft", false):
				here += 1
				var size: Vector3 = platform["size"]
				check(size.x > 0 and size.y > 0 and size.z > 0, "niveau %d : sol pale de taille positive" % (i + 1))
		if here > 0:
			soft_levels += 1
			soft_slabs += here
	check(soft_levels >= 1, "au moins un niveau enseigne le sol effacable")
	check(soft_levels <= 5, "le sol effacable reste l'exception, pas la regle")
	check(soft_slabs >= soft_levels, "chaque niveau concerne a au moins une dalle pale")
	done()


func test_kill_plane() -> void:
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var kill_y: float = def["kill_y"]
		for platform in def["platforms"]:
			var bottom: float = platform["pos"].y - platform["size"].y * 0.5
			check(kill_y < bottom, "niveau %d : kill_y sous les plateformes" % (i + 1))
	done()
