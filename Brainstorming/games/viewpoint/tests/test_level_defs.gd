extends ViewTest
## Solvability invariants of the five levels: everything the player must reach
## stands on a platform, and enough batteries exist (world + duplicable via
## photos) to charge every teleporter.


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


func test_count() -> void:
	eq(LevelDefs.count(), 15, "quinze niveaux")
	check(LevelDefs.get_def(-1).is_empty(), "index negatif : vide")
	check(LevelDefs.get_def(15).is_empty(), "index hors borne : vide")
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
		for battery_pos in def["batteries"]:
			check(_above_platform(def, battery_pos, 0.5), "niveau %d : pile posee sur une plateforme" % (i + 1))
		for photo in def["photos"]:
			check(_above_platform(def, photo["pos"], 2.0), "niveau %d : photo au dessus d'une plateforme" % (i + 1))
			check(not PhotoDefs.get_def(photo["id"]).is_empty(), "niveau %d : photo %s au catalogue" % [i + 1, photo["id"]])
		for cage in def.get("cages", []):
			check(_above_platform(def, cage["pos"], 0.5), "niveau %d : cage posee sur une plateforme" % (i + 1))
			var cage_size: Vector3 = cage["size"]
			check(cage_size.x > 0 and cage_size.y > 0 and cage_size.z > 0, "niveau %d : cage de taille positive" % (i + 1))
	done()


func test_batteries_reachable() -> void:
	# Recursive count: a photo that materializes another photo (coffret) also
	# brings the batteries of that nested photo.
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var available: int = def["batteries"].size()
		for photo in def["photos"]:
			available += PhotoDefs.battery_count_recursive(photo["id"])
		check(available >= def["teleporter"]["required"],
			"niveau %d : %d piles accessibles pour %d requises" % [i + 1, available, def["teleporter"]["required"]])
	done()


func test_kill_plane() -> void:
	for i in LevelDefs.count():
		var def := LevelDefs.get_def(i)
		var kill_y: float = def["kill_y"]
		for platform in def["platforms"]:
			var bottom: float = platform["pos"].y - platform["size"].y * 0.5
			check(kill_y < bottom, "niveau %d : kill_y sous les plateformes" % (i + 1))
	done()
