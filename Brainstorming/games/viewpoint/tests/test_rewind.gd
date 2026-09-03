extends ViewTest
## The pure playback helpers of the rewind: finding where a time falls in the
## history, and reading the state at that moment.


func suite_name() -> String:
	return "rewind"


func _sample(t: float, x: float, yaw := 0.0, held := "") -> Dictionary:
	return {
		"t": t,
		"pos": Vector3(x, 0, 0),
		"yaw": yaw,
		"pitch": 0.0,
		"carried": int(x),
		"inserted": 0,
		"required": 2,
		"films": 1,
		"held": held,
		"roll": 0,
		"bodies": {},
	}


func _history() -> Array:
	return [_sample(0.0, 0.0), _sample(1.0, 10.0, 0.0, "pile"), _sample(2.0, 20.0)]


func test_locate() -> void:
	var samples := _history()
	eq(Rewind.locate(samples, 0.0), 0, "le debut tombe sur le premier echantillon")
	eq(Rewind.locate(samples, 0.9), 0, "avant le deuxieme, on reste sur le premier")
	eq(Rewind.locate(samples, 1.0), 1, "une date exacte prend son echantillon")
	eq(Rewind.locate(samples, 1.5), 1, "entre deux, on prend le precedent")
	eq(Rewind.locate(samples, 9.0), 2, "au dela de l'historique, le dernier")
	eq(Rewind.locate(samples, -5.0), 0, "avant l'historique, le premier")
	eq(Rewind.locate([], 1.0), -1, "historique vide : aucun index")
	done()


func test_sample_between() -> void:
	var samples := _history()
	var mid := Rewind.sample_at(samples, 1.5)
	near(mid["pos"].x, 15.0, 0.001, "la position est interpolee entre deux echantillons")
	near(mid["t"], 1.5, 0.001, "la date rendue est celle demandee")
	# Discrete state does not interpolate: a photo is held or it is not.
	eq(mid["held"], "pile", "l'etat discret vient de l'echantillon precedent")
	eq(mid["carried"], 10, "les compteurs ne s'interpolent pas")
	done()


func test_sample_edges() -> void:
	var samples := _history()
	var first := Rewind.sample_at(samples, 0.0)
	near(first["pos"].x, 0.0, 0.001, "au debut, l'etat initial")
	var last := Rewind.sample_at(samples, 5.0)
	near(last["pos"].x, 20.0, 0.001, "au dela, le dernier etat connu")
	check(Rewind.sample_at([], 1.0).is_empty(), "historique vide : etat vide")
	done()


func test_yaw_takes_the_short_way() -> void:
	# Rewinding across the +PI / -PI seam must not spin the player around.
	var samples := [_sample(0.0, 0.0, -3.0), _sample(1.0, 0.0, 3.0)]
	var mid := Rewind.sample_at(samples, 0.5)
	check(absf(mid["yaw"]) > 3.0, "le lacet passe par le raccourci, pas par zero")
	done()


func test_constants() -> void:
	check(Rewind.SAMPLE_HZ >= 10.0, "au moins dix echantillons par seconde")
	check(Rewind.REWIND_SPEED > 1.0, "le rembobinage remonte plus vite que le temps")
	check(Rewind.MAX_SAMPLES >= int(Rewind.SAMPLE_HZ * 120.0), "au moins deux minutes d'historique")
	done()
