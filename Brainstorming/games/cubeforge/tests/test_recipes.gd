extends TestCase
## Recipe registry coherence plus the craft transaction itself, exercised on a
## real survival inventory.


func suite_name() -> String:
	return "recipes"


func _survival_inventory() -> Inventory:
	var inv := Inventory.new()
	inv.creative = false
	inv.clear()
	return inv


func test_registry_is_coherent() -> void:
	var recipes := Recipes.all()
	check(recipes.size() >= 15, "le livre de recettes est fourni")
	var has_hand := false
	var has_table := false
	for recipe in recipes:
		check(Items.is_valid_id(recipe["output"]), "sortie invalide pour %s" % str(recipe))
		check(int(recipe["count"]) >= 1, "quantite produite invalide")
		var inputs: Array = recipe["inputs"]
		check(inputs.size() >= 1, "une recette a besoin d'ingredients")
		for input: Array in inputs:
			check(Items.is_valid_id(input[0]), "ingredient invalide %s" % str(input))
			check(int(input[1]) >= 1, "quantite d'ingredient invalide")
		if bool(recipe["table"]):
			has_table = true
		else:
			has_hand = true
	check(has_hand, "il existe des recettes a la main")
	check(has_table, "il existe des recettes d'etabli")
	done()


func test_bootstrap_chain_exists_by_hand() -> void:
	# From a felled tree the player must reach the crafting table without one.
	var hand_outputs := {}
	for recipe in Recipes.all():
		if not bool(recipe["table"]):
			hand_outputs[int(recipe["output"])] = true
	check(hand_outputs.has(Blocks.OAK_PLANKS), "les planches se font a la main")
	check(hand_outputs.has(Items.STICK), "les batons se font a la main")
	check(hand_outputs.has(Blocks.CRAFTING_TABLE), "la table se fait a la main")
	done()


func test_craft_consumes_and_produces() -> void:
	var inv := _survival_inventory()
	inv.set_slot(0, Blocks.OAK_LOG, 3)
	var planks_recipe := _find(Blocks.OAK_PLANKS, [[Blocks.OAK_LOG, 1]])
	check(not planks_recipe.is_empty(), "recette des planches trouvee")
	check(Recipes.craftable(planks_recipe, inv), "recette possible avec un rondin")
	check(Recipes.craft(planks_recipe, inv), "la fabrication reussit")
	eq(inv.count_of(Blocks.OAK_LOG), 2, "un rondin consomme")
	eq(inv.count_of(Blocks.OAK_PLANKS), 4, "quatre planches produites")
	done()


func test_craft_refuses_missing_ingredients() -> void:
	var inv := _survival_inventory()
	inv.set_slot(0, Blocks.OAK_PLANKS, 2)
	var pick := _find(Items.WOOD_PICKAXE, [])
	check(not pick.is_empty(), "recette de la pioche trouvee")
	check(not Recipes.craftable(pick, inv), "pioche impossible sans batons ni assez de planches")
	check(not Recipes.craft(pick, inv), "la fabrication echoue proprement")
	eq(inv.count_of(Blocks.OAK_PLANKS), 2, "rien n'a ete consomme")
	eq(inv.count_of(Items.WOOD_PICKAXE), 0, "rien n'a ete produit")
	done()


func test_full_tool_craft() -> void:
	var inv := _survival_inventory()
	inv.set_slot(0, Blocks.OAK_PLANKS, 3)
	inv.set_slot(1, Items.STICK, 2)
	var pick := _find(Items.WOOD_PICKAXE, [])
	check(Recipes.craft(pick, inv), "la pioche en bois se fabrique")
	eq(inv.count_of(Items.WOOD_PICKAXE), 1, "une pioche produite")
	eq(inv.count_of(Blocks.OAK_PLANKS), 0, "les planches sont consommees")
	eq(inv.count_of(Items.STICK), 0, "les batons sont consommes")
	done()


func test_inventory_take() -> void:
	var inv := _survival_inventory()
	inv.set_slot(0, Items.STICK, 3)
	inv.set_slot(10, Items.STICK, 5)
	check(not inv.take(Items.STICK, 9), "prelever plus que le stock echoue")
	eq(inv.count_of(Items.STICK), 8, "le stock est intact apres un refus")
	check(inv.take(Items.STICK, 6), "prelever dans plusieurs cases reussit")
	eq(inv.count_of(Items.STICK), 2, "le stock restant est correct")
	# Storage empties before the hotbar.
	eq(inv.slot_count(0), 2, "la barre d'action garde ses objets en dernier")
	eq(inv.slot_count(10), 0, "la reserve se vide d'abord")
	done()


func _find(output: int, inputs_hint: Array) -> Dictionary:
	for recipe in Recipes.all():
		if int(recipe["output"]) != output:
			continue
		if inputs_hint.is_empty():
			return recipe
		var inputs: Array = recipe["inputs"]
		if inputs.size() == inputs_hint.size() and str(inputs) == str(inputs_hint):
			return recipe
	return {}
