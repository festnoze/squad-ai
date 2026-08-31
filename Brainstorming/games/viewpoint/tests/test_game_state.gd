extends ViewTest
## Pure progression logic of the Game autoload, exercised on a bare instance
## (the autoload itself is not registered under --script).

const GameStateScript := preload("res://src/core/game_state.gd")


func _fresh() -> Node:
	return GameStateScript.new()


func suite_name() -> String:
	return "game_state"


func test_full_cycle() -> void:
	var game := _fresh()
	game.reset()
	game.begin_level(0, 2)
	eq(game.required_batteries, 2, "exigence enregistree")
	check(not game.can_teleport(), "pas de teleportation a vide")
	game.collect_battery()
	game.collect_battery()
	eq(game.carried_batteries, 2, "deux piles portees")
	eq(game.insert_batteries(), 2, "deux piles inserees")
	eq(game.carried_batteries, 0, "plus rien en main")
	check(game.can_teleport(), "teleporteur charge")
	check(game.has_next_level(), "il reste des niveaux")
	game.advance_level()
	eq(game.level_index, 1, "niveau suivant")
	game.free()
	done()


func test_level_count_follows_defs() -> void:
	var game := _fresh()
	game.begin_level(LevelDefs.count() - 2, 1)
	check(game.has_next_level(), "l'avant-dernier niveau a un suivant")
	game.free()
	done()


func test_insert_bounds() -> void:
	var game := _fresh()
	game.begin_level(1, 1)
	eq(game.insert_batteries(), 0, "insertion sans pile : zero")
	game.collect_battery()
	game.collect_battery()
	game.collect_battery()
	eq(game.insert_batteries(), 1, "insertion bornee au requis")
	eq(game.carried_batteries, 2, "le surplus reste porte")
	eq(game.insert_batteries(), 0, "reinsertion sur un teleporteur plein : zero")
	check(game.can_teleport(), "charge atteinte")
	game.free()
	done()


func test_begin_level_resets_batteries() -> void:
	var game := _fresh()
	game.begin_level(0, 1)
	game.collect_battery()
	game.begin_level(1, 3)
	eq(game.carried_batteries, 0, "les piles ne traversent pas les niveaux")
	eq(game.inserted_batteries, 0, "l'insertion repart de zero")
	eq(game.required_batteries, 3, "nouvelle exigence")
	check(not game.can_teleport(), "nouveau teleporteur decharge")
	game.free()
	done()


func test_last_level() -> void:
	var game := _fresh()
	game.begin_level(LevelDefs.count() - 1, 4)
	check(not game.has_next_level(), "le dernier niveau n'a pas de suivant")
	game.free()
	done()


func test_level_unlocking() -> void:
	# Bare instance (not in tree): _ready never runs, no disk progress loaded.
	var game := _fresh()
	check(game.is_level_unlocked(0), "le niveau 1 est toujours accessible")
	check(not game.is_level_unlocked(1), "le niveau 2 commence verrouille")
	check(not game.is_level_unlocked(-1), "index negatif verrouille")
	check(not game.is_level_unlocked(LevelDefs.count()), "index hors borne verrouille")
	game.begin_level(3, 2)
	check(game.is_level_unlocked(3), "atteindre un niveau le debloque")
	check(game.is_level_unlocked(2), "les niveaux precedents aussi")
	check(not game.is_level_unlocked(4), "pas les suivants")
	game.begin_level(1, 2)
	eq(game.furthest_level, 3, "rejouer un vieux niveau ne reduit pas la progression")
	game.reset()
	eq(game.furthest_level, 3, "reset ne touche pas la progression")
	game.free()
	done()


func test_progress_persistence() -> void:
	var path := "user://test_progress.cfg"
	var writer := _fresh()
	writer.furthest_level = 7
	writer.save_progress(path)
	writer.free()
	var reader := _fresh()
	eq(reader.furthest_level, 0, "instance neuve : progression vierge")
	reader.load_progress(path)
	eq(reader.furthest_level, 7, "la progression relue correspond a l'ecriture")
	reader.free()
	# A corrupt or absurd saved value is clamped into the valid level range.
	var cfg := ConfigFile.new()
	cfg.set_value("progress", "furthest_level", 999)
	cfg.save(path)
	var clamped := _fresh()
	clamped.load_progress(path)
	eq(clamped.furthest_level, LevelDefs.count() - 1, "valeur aberrante bornee au dernier niveau")
	clamped.free()
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
	done()


func test_signals() -> void:
	var game := _fresh()
	var events: Array = []
	game.batteries_changed.connect(func(c, i, r): events.append([c, i, r]))
	game.begin_level(0, 2)
	game.collect_battery()
	game.insert_batteries()
	eq(events.size(), 3, "trois emissions de batteries_changed")
	eq(events[2], [0, 1, 2], "dernier etat : 0 portee, 1 inseree, 2 requises")
	game.free()
	done()
