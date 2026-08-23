extends SceneTree
## Headless test runner.
##
##   godot --headless --path . --script res://tests/run_tests.gd
##
## Exits 0 when every check passes, 1 otherwise. Suites listed here that do not
## exist yet are skipped with a note rather than treated as failures, so the
## runner stays usable while modules are still being written.

const SUITES: PackedStringArray = [
	"res://tests/test_blocks.gd",
	"res://tests/test_items.gd",
	"res://tests/test_recipes.gd",
	"res://tests/test_chunk_data.gd",
	"res://tests/test_atlas.gd",
	"res://tests/test_terrain.gd",
	"res://tests/test_mesher.gd",
	"res://tests/test_voxel_body.gd",
	"res://tests/test_inventory.gd",
	"res://tests/test_sfx.gd",
	"res://tests/test_world_coords.gd",
	"res://tests/test_worlds_ui.gd",
	"res://tests/test_map_ui.gd",
	"res://tests/test_gravity.gd",
	"res://tests/test_growth.gd",
	"res://tests/test_chest_store.gd",
]


func _initialize() -> void:
	var total_checks := 0
	var total_failures := 0
	var skipped: PackedStringArray = PackedStringArray()
	var report: PackedStringArray = PackedStringArray()

	print("")
	print("=== CUBEFORGE tests ===")

	for path in SUITES:
		if not ResourceLoader.exists(path):
			skipped.append(path.get_file())
			continue

		# A script with a parse error still loads as a resource, but calling
		# new() on it is a runtime error that would abort this whole method
		# before quit(), leaving the process hanging forever. Report and move on.
		var script: Script = load(path)
		if script == null or not script.can_instantiate():
			report.append("  ECHEC  %s : script illisible ou invalide" % path.get_file())
			total_failures += 1
			continue

		var suite: TestCase = script.new()
		if suite == null:
			report.append("  ECHEC  %s : instanciation impossible" % path.get_file())
			total_failures += 1
			continue

		var method_names: PackedStringArray = PackedStringArray()
		for entry in suite.get_method_list():
			var method_name: String = entry["name"]
			if method_name.begins_with("test_"):
				method_names.append(method_name)
		method_names.sort()

		if method_names.is_empty():
			report.append("  VIDE   %s : aucune methode test_" % path.get_file())
			continue

		var suite_failures := 0
		for method_name in method_names:
			# A fresh instance per test so one case cannot leak state into the
			# next and turn a single bug into a cascade of confusing failures.
			var case: TestCase = script.new()
			case.callv(method_name, [])
			total_checks += case.checks

			# A runtime error inside a test method aborts it silently, so a
			# method that never reached its final done(), or that recorded no
			# check at all, is reported as broken rather than passing. Without
			# this, a suite whose every call fails on a missing identifier comes
			# out green.
			if case.checks == 0:
				report.append("  ECHEC  %s :: %s" % [case.suite_name(), method_name])
				report.append("         aucune verification executee (methode vide ou interrompue)")
				suite_failures += 1
			elif not case.finished:
				report.append("  ECHEC  %s :: %s" % [case.suite_name(), method_name])
				report.append("         methode interrompue avant done(), voir les erreurs ci-dessus")
				suite_failures += 1

			for message in case.failures:
				report.append("  ECHEC  %s :: %s" % [case.suite_name(), method_name])
				report.append("         %s" % message)
				suite_failures += 1

		total_failures += suite_failures
		if suite_failures == 0:
			report.append("  OK     %s (%d methodes)" % [suite.suite_name(), method_names.size()])

	for line in report:
		print(line)

	if not skipped.is_empty():
		print("")
		print("  Suites absentes : %s" % ", ".join(skipped))

	print("")
	print("  %d verifications, %d echecs" % [total_checks, total_failures])
	print("=======================")
	print("")

	quit(1 if total_failures > 0 else 0)
