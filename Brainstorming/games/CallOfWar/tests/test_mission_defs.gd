extends WarTest
## Objective metadata. build_campaign() needs a live GameWorld, so it is
## exercised by the smoke probe instead; what this suite covers is the pure part
## the HUD and the journal read on every frame.


func suite_name() -> String:
	return "mission_defs"


func _all_kinds() -> PackedInt32Array:
	return PackedInt32Array([MissionDefs.O_CAPTURE, MissionDefs.O_DESTROY,
			MissionDefs.O_RESCUE, MissionDefs.O_ASSASSINATE, MissionDefs.O_SABOTAGE,
			MissionDefs.O_DEFEND, MissionDefs.O_RECON, MissionDefs.O_AMBUSH])


func test_kind_constants_are_distinct() -> void:
	var seen := {}
	for kind in _all_kinds():
		check(not seen.has(kind), "constante de type d'objectif dupliquee : %d" % kind)
		seen[kind] = true
	eq(seen.size(), 8, "il doit y avoir huit types d'objectifs distincts")
	done()


func test_every_kind_has_a_french_label() -> void:
	var labels := {}
	for kind in _all_kinds():
		var label := MissionDefs.kind_name(kind)
		check(label.strip_edges() != "", "le type %d n'a pas de libelle" % kind)
		check(not labels.has(label), "le libelle '%s' sert pour deux types" % label)
		labels[label] = true
	done()


func test_every_kind_has_a_single_character_icon() -> void:
	# The compass and the journal draw this glyph in a fixed size box, so a two
	# character icon overflows its slot.
	for kind in _all_kinds():
		var icon := MissionDefs.kind_icon(kind)
		eq(icon.length(), 1, "l'icone du type %d doit tenir en un caractere" % kind)
	done()


func test_an_unknown_kind_degrades_gracefully() -> void:
	# The journal iterates over saved data, which may contain a kind from an
	# older build. It must not crash on it.
	var label := MissionDefs.kind_name(-1)
	check(label is String, "kind_name doit toujours renvoyer une chaine")
	var icon := MissionDefs.kind_icon(9999)
	check(icon is String, "kind_icon doit toujours renvoyer une chaine")
	done()


func test_an_objective_can_be_built_and_carries_its_fields() -> void:
	var obj := MissionDefs.Objective.new()
	obj.id = 3
	obj.kind = MissionDefs.O_SABOTAGE
	obj.title = "Assecher la Wehrmacht"
	obj.description = "Le depot alimente la colonne blindee."
	obj.position = Vector3(12.0, 4.0, -30.0)
	obj.radius = 25.0
	obj.target_count = 1
	obj.prerequisite = -1
	eq(obj.id, 3, "l'identifiant doit se conserver")
	eq(obj.kind, MissionDefs.O_SABOTAGE, "le type doit se conserver")
	check(obj.title != "", "le titre doit se conserver")
	check(obj.radius > 0.0, "un objectif a besoin d'un rayon")
	done()
