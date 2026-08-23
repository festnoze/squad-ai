extends WarTest
## Runtime weapon state. The reload and fire cadence logic is where an off by one
## turns into a rifle that fires nine rounds from an eight round clip, or a
## reload that never finishes.


func suite_name() -> String:
	return "weapon"


func _garand() -> Weapon:
	return Weapon.new(WeaponDefs.M1_GARAND, true)


func test_a_full_weapon_starts_loaded() -> void:
	var weapon := _garand()
	eq(weapon.in_magazine, WeaponDefs.magazine(WeaponDefs.M1_GARAND),
			"une arme creee pleine doit avoir son chargeur plein")
	check(weapon.reserve > 0, "une arme creee pleine doit avoir de la reserve")
	check(not weapon.needs_reload(), "une arme pleine n'a pas besoin de recharger")
	done()


func test_firing_consumes_exactly_one_round() -> void:
	var weapon := _garand()
	var before := weapon.in_magazine
	var now := 0.0
	check(weapon.can_fire(now), "une arme pleine doit pouvoir tirer")
	check(weapon.fire(now), "le tir doit reussir")
	eq(weapon.in_magazine, before - 1, "un tir consomme exactement une cartouche")
	done()


func test_cadence_blocks_a_second_shot_in_the_same_instant() -> void:
	var weapon := _garand()
	check(weapon.fire(0.0), "premier tir")
	check(not weapon.can_fire(0.0), "deux tirs dans le meme instant sont impossibles")
	var interval := 60.0 / WeaponDefs.rpm(WeaponDefs.M1_GARAND)
	check(weapon.can_fire(interval + 0.01),
			"apres l'intervalle de cadence, l'arme doit pouvoir retirer")
	done()


func test_an_empty_magazine_cannot_fire() -> void:
	var weapon := _garand()
	var now := 0.0
	var interval := 60.0 / WeaponDefs.rpm(WeaponDefs.M1_GARAND)
	var guard := 0
	while weapon.in_magazine > 0 and guard < 200:
		weapon.fire(now)
		now += interval
		guard += 1
	eq(weapon.in_magazine, 0, "le chargeur doit finir vide")
	check(not weapon.can_fire(now + 10.0), "un chargeur vide ne tire pas")
	check(weapon.needs_reload(), "un chargeur vide demande un rechargement")
	done()


func test_reload_refills_from_the_reserve_without_creating_ammo() -> void:
	var weapon := _garand()
	var interval := 60.0 / WeaponDefs.rpm(WeaponDefs.M1_GARAND)
	var now := 0.0
	for i in 3:
		weapon.fire(now)
		now += interval
	var total_before := weapon.in_magazine + weapon.reserve

	var duration := weapon.start_reload(now)
	check(duration > 0.0, "le rechargement doit annoncer une duree")
	check(weapon.is_reloading, "l'arme doit se declarer en rechargement")

	# Drive the reload to completion the way the player does, frame by frame.
	var completed := false
	var elapsed := 0.0
	while elapsed < duration * 4.0 + 1.0:
		elapsed += 0.05
		if weapon.tick_reload(now + elapsed):
			completed = true
			if not weapon.is_reloading:
				break
	check(completed, "le rechargement doit finir par se terminer")
	check(not weapon.is_reloading, "l'arme ne doit plus etre en rechargement a la fin")

	var total_after := weapon.in_magazine + weapon.reserve
	eq(total_after, total_before, "un rechargement ne cree ni ne detruit de munitions")
	check(weapon.in_magazine <= WeaponDefs.magazine(WeaponDefs.M1_GARAND),
			"le chargeur ne peut pas depasser sa capacite")
	done()


func test_reload_is_refused_without_reserve() -> void:
	var weapon := Weapon.new(WeaponDefs.M1_GARAND, false)
	weapon.in_magazine = 0
	weapon.reserve = 0
	check(not weapon.can_reload(), "sans reserve, on ne peut pas recharger")
	near(weapon.start_reload(0.0), 0.0, 0.0001,
			"un rechargement impossible doit renvoyer une duree nulle")
	done()


func test_reserve_is_capped() -> void:
	var weapon := _garand()
	weapon.reserve = 0
	var taken := weapon.add_ammo(100000)
	check(taken <= 100000, "on ne peut pas prendre plus que ce qu'on donne")
	check(weapon.reserve <= WeaponDefs.reserve_max(WeaponDefs.M1_GARAND),
			"la reserve ne peut pas depasser son plafond")
	done()


func test_spread_ranking_matches_the_stance() -> void:
	var weapon := Weapon.new(WeaponDefs.THOMPSON, true)
	var hip_moving := weapon.current_spread(false, true, false)
	var hip_still := weapon.current_spread(false, false, false)
	var aim_still := weapon.current_spread(true, false, false)
	var aim_crouched := weapon.current_spread(true, false, true)
	check(hip_moving >= hip_still, "courir disperse au moins autant que rester immobile")
	check(hip_still >= aim_still, "viser doit resserrer par rapport a la hanche")
	check(aim_crouched <= aim_still, "s'accroupir doit resserrer encore")
	check(aim_crouched >= 0.0, "la dispersion ne peut pas etre negative")
	done()


func test_serialisation_round_trips() -> void:
	var weapon := Weapon.new(WeaponDefs.THOMPSON, true)
	weapon.fire(0.0)
	weapon.reserve = 42
	var data := weapon.to_dict()
	var restored := Weapon.new(WeaponDefs.M1911, false)
	restored.from_dict(data)
	eq(restored.id, weapon.id, "l'identifiant d'arme doit survivre a la sauvegarde")
	eq(restored.in_magazine, weapon.in_magazine, "le chargeur doit survivre")
	eq(restored.reserve, weapon.reserve, "la reserve doit survivre")
	done()


func test_ammo_string_is_readable() -> void:
	var weapon := _garand()
	var text := weapon.ammo_string()
	check(text.length() > 0, "le compteur de munitions ne doit pas etre vide")
	check(text.contains(str(weapon.in_magazine)),
			"le compteur doit montrer le contenu du chargeur")
	done()
