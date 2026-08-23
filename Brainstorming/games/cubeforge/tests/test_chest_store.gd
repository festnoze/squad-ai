extends TestCase

## Preloaded by path: immune to a stale global class cache on a fresh checkout.
const ChestStoreScript := preload("res://src/core/chest_store.gd")
## ChestStore: slot round trips, the Inventory normalisation rules, stack
## storage with overflow, chest removal, dumping into a full inventory and the
## save round trip including individually malformed entries.


func suite_name() -> String:
	return "chest_store"


const CELL := Vector3i(4, 50, -7)
const OTHER := Vector3i(-3, 12, 9)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

## An empty survival inventory. The constructor loads the creative palette into
## the hotbar, so stock tests have to wipe it first.
func _survival() -> Inventory:
	var inv := Inventory.new()
	inv.creative = false
	inv.clear()
	return inv


## Counts changed(cell) emissions. A Dictionary because a GDScript lambda
## captures by value: an int counter would never be seen changing.
func _watch(store: ChestStore) -> Dictionary:
	var events: Dictionary = {"cells": []}
	store.changed.connect(func(cell: Vector3i) -> void: (events["cells"] as Array).append(cell))
	return events


## Full and valid chest payload for from_dict, every slot holding (id, count).
func _chest_payload(id: int, count: int) -> Dictionary:
	var blocks: Array = []
	var counts: Array = []
	for _i in ChestStoreScript.SLOTS:
		blocks.append(id)
		counts.append(count)
	return {"blocks": blocks, "counts": counts}


# ---------------------------------------------------------------------------
# Slot round trip
# ---------------------------------------------------------------------------

func test_set_get_round_trip() -> void:
	var store := ChestStoreScript.new()
	var events := _watch(store)
	check(not store.has_chest(CELL), "pas de coffre avant ensure")
	eq(store.slot_block(CELL, 0), Blocks.AIR, "coffre absent lu comme AIR")
	eq(store.slot_count(CELL, 0), 0, "coffre absent lu comme compte 0")

	store.ensure(CELL)
	check(store.has_chest(CELL), "coffre présent après ensure")
	eq((events["cells"] as Array).size(), 1, "ensure a émis changed")
	eq(store.slot_block(CELL, 5), Blocks.AIR, "coffre neuf entièrement vide")

	store.set_slot(CELL, 3, Blocks.STONE, 12)
	eq(store.slot_block(CELL, 3), Blocks.STONE, "id relu après set_slot")
	eq(store.slot_count(CELL, 3), 12, "compte relu après set_slot")
	eq((events["cells"] as Array).size(), 2, "set_slot a émis changed")

	store.set_slot(CELL, 4, Items.STICK, 7)
	eq(store.slot_block(CELL, 4), Items.STICK, "un id d'objet est accepté")

	eq(store.slot_block(CELL, -1), Blocks.AIR, "index négatif lu comme AIR")
	eq(store.slot_block(CELL, ChestStoreScript.SLOTS), Blocks.AIR, "index hors plage lu comme AIR")
	eq(store.slot_count(CELL, ChestStoreScript.SLOTS), 0, "compte hors plage lu comme 0")
	done()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

func test_normalisation() -> void:
	var store := ChestStoreScript.new()

	# AIR empties, whatever the count says.
	store.set_slot(CELL, 0, Blocks.DIRT, 5)
	store.set_slot(CELL, 0, Blocks.AIR, 99)
	eq(store.slot_block(CELL, 0), Blocks.AIR, "AIR vide la case")
	eq(store.slot_count(CELL, 0), 0, "AIR remet le compte à zéro")

	# A count of zero or less empties too.
	store.set_slot(CELL, 1, Blocks.DIRT, 0)
	eq(store.slot_block(CELL, 1), Blocks.AIR, "compte nul vide la case")
	store.set_slot(CELL, 1, Blocks.DIRT, -4)
	eq(store.slot_block(CELL, 1), Blocks.AIR, "compte négatif vide la case")

	# An unknown id is rejected and the slot stays untouched.
	store.set_slot(CELL, 2, Blocks.SAND, 3)
	store.set_slot(CELL, 2, 137, 8)
	eq(store.slot_block(CELL, 2), Blocks.SAND, "id inconnu rejeté, case intacte")
	eq(store.slot_count(CELL, 2), 3, "id inconnu rejeté, compte intact")

	# Counts clamp to the shared stack maximum.
	store.set_slot(CELL, 4, Blocks.STONE, Inventory.STACK_MAX + 500)
	eq(store.slot_count(CELL, 4), Inventory.STACK_MAX, "compte plafonné à STACK_MAX")
	done()


# ---------------------------------------------------------------------------
# store_stack
# ---------------------------------------------------------------------------

func test_store_stack_top_up_then_overflow() -> void:
	var store := ChestStoreScript.new()

	# Top up the partial stack first, then spill into an empty slot.
	store.set_slot(CELL, 0, Blocks.SAND, Inventory.STACK_MAX - 10)
	var left := store.store_stack(CELL, Blocks.SAND, 25)
	eq(left, 0, "tout est entré")
	eq(store.slot_count(CELL, 0), Inventory.STACK_MAX, "la pile existante est complétée d'abord")
	eq(store.slot_block(CELL, 1), Blocks.SAND, "le surplus ouvre une case vide")
	eq(store.slot_count(CELL, 1), 15, "le surplus porte le reste")

	# A chest full to the brim returns everything as leftover.
	for i in ChestStoreScript.SLOTS:
		store.set_slot(OTHER, i, Blocks.DIRT, Inventory.STACK_MAX)
	eq(store.store_stack(OTHER, Blocks.DIRT, 40), 40, "coffre plein: tout ressort")
	eq(store.store_stack(OTHER, Blocks.STONE, 7), 7, "coffre plein: autre bloc aussi")

	# Invalid input never lands anywhere.
	eq(store.store_stack(CELL, 137, 5), 5, "id inconnu entièrement refusé")
	eq(store.store_stack(CELL, Blocks.STONE, 0), 0, "quantité nulle est un no-op")
	done()


# ---------------------------------------------------------------------------
# remove_chest
# ---------------------------------------------------------------------------

func test_remove_chest_returns_contents() -> void:
	var store := ChestStoreScript.new()
	store.set_slot(CELL, 2, Blocks.STONE, 30)
	store.set_slot(CELL, 9, Items.COAL, 4)

	var pairs := store.remove_chest(CELL)
	eq(pairs.size(), 2, "deux piles restituées")
	check(pairs.has([Blocks.STONE, 30]), "la pile de pierre est restituée")
	check(pairs.has([Items.COAL, 4]), "la pile de charbon est restituée")
	check(not store.has_chest(CELL), "le coffre est effacé")

	eq(store.remove_chest(CELL).size(), 0, "second retrait sans coffre: vide")
	eq(store.remove_chest(OTHER).size(), 0, "retrait d'un coffre jamais créé: vide")
	done()


# ---------------------------------------------------------------------------
# dump_into
# ---------------------------------------------------------------------------

func test_dump_into_full_inventory_returns_leftover() -> void:
	var store := ChestStoreScript.new()
	var inv := _survival()
	# Saturate all 36 slots with full DIRT stacks: nothing else can enter.
	for slot in Inventory.TOTAL_SLOTS:
		inv.set_slot(slot, Blocks.DIRT, Inventory.STACK_MAX)

	store.set_slot(CELL, 0, Blocks.STONE, 10)
	store.set_slot(CELL, 1, Blocks.DIRT, 5)
	var leftover := store.dump_into(CELL, inv)
	eq(leftover, 15, "rien ne rentre: tout ressort en reliquat")
	check(not store.has_chest(CELL), "le coffre est effacé malgré le reliquat")

	# With room, everything lands and the leftover is zero.
	var empty_inv := _survival()
	store.set_slot(OTHER, 0, Blocks.STONE, 10)
	eq(store.dump_into(OTHER, empty_inv), 0, "inventaire vide: aucun reliquat")
	eq(empty_inv.count_of(Blocks.STONE), 10, "les blocs sont bien arrivés")
	check(not store.has_chest(OTHER), "le coffre vidé est effacé")
	done()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

func test_dict_round_trip() -> void:
	var store := ChestStoreScript.new()
	store.set_slot(CELL, 0, Blocks.STONE, 64)
	store.set_slot(CELL, 26, Items.DIAMOND, 3)
	store.set_slot(OTHER, 12, Blocks.OAK_PLANKS, Inventory.STACK_MAX)

	var data := store.to_dict()
	eq(data.size(), 2, "un enregistrement par coffre")
	for key: Variant in data:
		check(typeof(key) == TYPE_STRING, "les clés sont des chaînes")

	# Through real JSON, which turns every int into a float: from_dict must
	# coerce them back.
	var text := JSON.stringify(data)
	var parsed: Variant = JSON.parse_string(text)
	check(typeof(parsed) == TYPE_DICTIONARY, "le JSON se relit en Dictionary")

	var restored := ChestStoreScript.new()
	restored.from_dict(parsed as Dictionary)
	check(restored.has_chest(CELL), "premier coffre restauré")
	check(restored.has_chest(OTHER), "second coffre restauré")
	eq(restored.slot_block(CELL, 0), Blocks.STONE, "id restauré")
	eq(restored.slot_count(CELL, 0), 64, "compte restauré")
	eq(restored.slot_block(CELL, 26), Items.DIAMOND, "id d'objet restauré")
	eq(restored.slot_count(CELL, 26), 3, "compte d'objet restauré")
	eq(restored.slot_count(OTHER, 12), Inventory.STACK_MAX, "pile pleine restaurée")
	eq(restored.slot_block(CELL, 1), Blocks.AIR, "les cases vides restent vides")
	done()


func test_from_dict_skips_malformed_entries() -> void:
	var store := ChestStoreScript.new()
	var valid := _chest_payload(Blocks.AIR, 0)
	(valid["blocks"] as Array)[0] = Blocks.STONE
	(valid["counts"] as Array)[0] = 21

	var data := {
		"1:2:3": valid,
		"a:b": _chest_payload(Blocks.DIRT, 1),
		"4:5:x": _chest_payload(Blocks.DIRT, 1),
		"7:8:9": "not a dictionary",
		"10:11:12": {"blocks": [1, 2], "counts": [3, 4]},
		"13:14:15": _chest_payload(137, 5),
	}
	store.from_dict(data)

	check(store.has_chest(Vector3i(1, 2, 3)), "le coffre valide survit aux voisins corrompus")
	eq(store.slot_block(Vector3i(1, 2, 3), 0), Blocks.STONE, "son contenu est intact")
	eq(store.slot_count(Vector3i(1, 2, 3), 0), 21, "son compte est intact")
	check(not store.has_chest(Vector3i(7, 8, 9)), "valeur non-Dictionary ignorée")
	check(not store.has_chest(Vector3i(10, 11, 12)), "tableaux de mauvaise taille ignorés")
	check(not store.has_chest(Vector3i(13, 14, 15)), "id inconnu: coffre entier ignoré")
	eq(store.to_dict().size(), 1, "un seul coffre a été chargé")

	# A reload replaces the previous contents entirely.
	store.from_dict({})
	eq(store.to_dict().size(), 0, "un chargement vide efface tout")
	done()
