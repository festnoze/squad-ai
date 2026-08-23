extends WarTest
## Campaign persistence. Every failure mode here is silent data loss, so the
## suite spends most of its effort on the unhappy paths.


func suite_name() -> String:
	return "save_manager"


const CAMPAIGN := "suite_de_test"


func _cleanup() -> void:
	SaveManager.erase(CAMPAIGN)


func test_a_missing_save_reads_as_an_empty_dictionary() -> void:
	_cleanup()
	var data := SaveManager.read(CAMPAIGN)
	check(data.is_empty(), "une sauvegarde absente doit se lire comme un dictionnaire vide")
	check(not SaveManager.has_save(CAMPAIGN), "has_save doit etre faux sans fichier")
	done()


func test_write_then_read_round_trips() -> void:
	_cleanup()
	var payload := {
		"seed": 123456,
		"war": {"kills": 17, "headshots": 4},
		"time_of_day": 0.42,
		"nested": {"list": [1, 2, 3]},
	}
	check(SaveManager.write(CAMPAIGN, payload), "l'ecriture doit reussir")
	check(SaveManager.has_save(CAMPAIGN), "has_save doit voir le fichier ecrit")
	var back := SaveManager.read(CAMPAIGN)
	check(not back.is_empty(), "la relecture ne doit pas etre vide")
	eq(int(back.get("seed", 0)), 123456, "la graine doit survivre")
	near(float(back.get("time_of_day", 0.0)), 0.42, 0.0001, "l'heure doit survivre")
	var war: Variant = back.get("war")
	check(war is Dictionary, "le bloc war doit rester un dictionnaire")
	if war is Dictionary:
		eq(int(war.get("kills", 0)), 17, "les statistiques doivent survivre")
	_cleanup()
	done()


func test_writing_twice_overwrites_instead_of_appending() -> void:
	_cleanup()
	SaveManager.write(CAMPAIGN, {"value": 1})
	SaveManager.write(CAMPAIGN, {"value": 2})
	var back := SaveManager.read(CAMPAIGN)
	eq(int(back.get("value", 0)), 2, "la seconde ecriture doit remplacer la premiere")
	_cleanup()
	done()


func test_a_corrupt_file_reads_as_empty_instead_of_crashing() -> void:
	_cleanup()
	SaveManager.write(CAMPAIGN, {"value": 1})
	var path := SaveManager.save_path(CAMPAIGN)
	var handle := FileAccess.open(path, FileAccess.WRITE)
	check(handle != null, "le fichier de sauvegarde doit etre accessible en ecriture")
	if handle != null:
		handle.store_string("{ ceci n'est pas du JSON")
		handle.close()
	var data := SaveManager.read(CAMPAIGN)
	check(data.is_empty(), "un fichier corrompu doit se lire comme vide, pas planter")
	_cleanup()
	done()


func test_a_json_array_is_rejected_as_a_save() -> void:
	# JSON.parse_string happily returns an Array. Treating it as a Dictionary
	# later would throw at the first .get() call, deep in the boot sequence.
	_cleanup()
	SaveManager.write(CAMPAIGN, {"value": 1})
	var handle := FileAccess.open(SaveManager.save_path(CAMPAIGN), FileAccess.WRITE)
	if handle != null:
		handle.store_string("[1, 2, 3]")
		handle.close()
	var data := SaveManager.read(CAMPAIGN)
	check(data.is_empty(), "un JSON qui n'est pas un objet doit etre refuse")
	_cleanup()
	done()


func test_erase_removes_the_file_and_is_safe_to_repeat() -> void:
	_cleanup()
	SaveManager.write(CAMPAIGN, {"value": 1})
	check(SaveManager.erase(CAMPAIGN), "l'effacement d'une sauvegarde existante doit reussir")
	check(not SaveManager.has_save(CAMPAIGN), "le fichier ne doit plus exister")
	# Erasing twice must not be an error the caller has to guard against.
	var second := SaveManager.erase(CAMPAIGN)
	check(second == true or second == false, "un second effacement ne doit pas planter")
	done()


func test_list_campaigns_sees_what_was_written() -> void:
	_cleanup()
	SaveManager.write(CAMPAIGN, {"value": 1})
	var names := SaveManager.list_campaigns()
	var found := false
	for name in names:
		if name.contains(CAMPAIGN):
			found = true
	check(found, "la campagne ecrite doit apparaitre dans list_campaigns()")
	_cleanup()
	done()


func test_save_path_is_inside_the_user_directory() -> void:
	var path := SaveManager.save_path(CAMPAIGN)
	check(path.begins_with("user://"), "les sauvegardes doivent rester dans user://")
	check(path.ends_with(".json"), "les sauvegardes sont du JSON")
	done()
