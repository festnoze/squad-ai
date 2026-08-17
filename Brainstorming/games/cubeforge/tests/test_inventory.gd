extends TestCase
## Inventory: the empty slot invariant, stacking order, selection wrapping,
## creative shortcuts, palette pages and the save round trip.
##
## The inventory is a small pure class, so this suite goes after the edge cases
## rather than the happy path: every mutation is re-checked against the
## invariant "a slot is either (AIR, 0) or a real block with a positive count",
## because a single drift there shows up in the interface as a phantom stack.


func suite_name() -> String:
	return "inventory"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

## Returns a description of the first invariant violation, or "" when the whole
## inventory is coherent. Collapsed into one string so a broken slot produces a
## single readable failure instead of thirty-six.
func _invariant_error(inv: Inventory) -> String:
	for slot in Inventory.TOTAL_SLOTS:
		var id: int = inv.slot_block(slot)
		var count: int = inv.slot_count(slot)
		if id == Blocks.AIR:
			if count != 0:
				return "case %d vide mais avec un compte de %d" % [slot, count]
			continue
		if id < 0 or id >= Blocks.COUNT:
			return "case %d avec un id de bloc invalide %d" % [slot, id]
		if count <= 0:
			return "case %d avec le bloc %d et un compte de %d" % [slot, id, count]
		if count > Inventory.STACK_MAX:
			return "case %d au-dela de STACK_MAX avec %d" % [slot, count]
	return ""


func _check_invariant(inv: Inventory, context: String) -> void:
	eq(_invariant_error(inv), "", "invariant de case rompu %s" % context)


## Compact fingerprint of the whole state, used to prove a rejected operation
## changed absolutely nothing.
func _signature(inv: Inventory) -> String:
	var parts: PackedStringArray = PackedStringArray()
	parts.append("sel=%d" % inv.selected)
	parts.append("creative=%s" % str(inv.creative))
	for slot in Inventory.TOTAL_SLOTS:
		parts.append("%d:%d" % [inv.slot_block(slot), inv.slot_count(slot)])
	return "|".join(parts)


## Counts both signals. A Dictionary because a GDScript lambda captures by
## value: an int counter would never be seen changing from the outside.
func _watch(inv: Inventory) -> Dictionary:
	var events: Dictionary = {"changed": 0, "selection": []}
	inv.changed.connect(func() -> void: events["changed"] = int(events["changed"]) + 1)
	inv.selection_changed.connect(func(slot: int) -> void: (events["selection"] as Array).append(slot))
	return events


func _selection_events(events: Dictionary) -> Array:
	return events["selection"] as Array


## An empty survival inventory. The constructor loads the creative palette into
## the hotbar, so stock tests have to wipe it first.
func _survival() -> Inventory:
	var inv := Inventory.new()
	inv.creative = false
	inv.clear()
	return inv


## A full 36 slot payload for from_dict.
func _payload(block_id: int, count: int) -> Dictionary:
	var blocks: Array = []
	var counts: Array = []
	for _i in Inventory.TOTAL_SLOTS:
		blocks.append(block_id)
		counts.append(count)
	return {
		"version": Inventory.SAVE_VERSION,
		"selected": 0,
		"creative": false,
		"blocks": blocks,
		"counts": counts,
	}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

func test_fresh_inventory_holds_palette_page_zero() -> void:
	var inv := Inventory.new()
	eq(Inventory.TOTAL_SLOTS, Inventory.HOTBAR_SLOTS + Inventory.STORAGE_SLOTS, "total des cases")
	eq(Inventory.TOTAL_SLOTS, 36, "36 cases au total")
	check(inv.creative, "le mode creatif est actif au demarrage")
	eq(inv.selected, 0, "la premiere case est selectionnee")

	var palette := Blocks.PALETTE
	for i in Inventory.HOTBAR_SLOTS:
		eq(inv.slot_block(i), int(palette[i]), "la case %d porte l'entree de palette" % i)
		eq(inv.slot_count(i), Inventory.STACK_MAX, "une pile de palette est pleine")
	eq(inv.selected_block(), int(palette[0]), "le bloc selectionne est la premiere entree")

	for slot in range(Inventory.HOTBAR_SLOTS, Inventory.TOTAL_SLOTS):
		eq(inv.slot_block(slot), Blocks.AIR, "la reserve demarre vide en case %d" % slot)
		eq(inv.slot_count(slot), 0, "la reserve demarre a zero en case %d" % slot)

	_check_invariant(inv, "a la construction")
	done()


func test_slot_access_is_forgiving_out_of_range() -> void:
	var inv := Inventory.new()
	eq(inv.slot_block(-1), Blocks.AIR, "lecture negative renvoie de l'air")
	eq(inv.slot_block(Inventory.TOTAL_SLOTS), Blocks.AIR, "lecture au-dela renvoie de l'air")
	eq(inv.slot_count(-5), 0, "compte negatif hors bornes")
	eq(inv.slot_count(999), 0, "compte au-dela des bornes")

	var before := _signature(inv)
	var events := _watch(inv)
	inv.set_slot(-1, Blocks.STONE, 4)
	inv.set_slot(Inventory.TOTAL_SLOTS, Blocks.STONE, 4)
	eq(_signature(inv), before, "une ecriture hors bornes ne change rien")
	eq(events["changed"], 0, "une ecriture hors bornes n'emet pas changed")
	done()


# ---------------------------------------------------------------------------
# The empty slot invariant
# ---------------------------------------------------------------------------

func test_empty_slot_invariant_survives_every_mutation() -> void:
	var inv := _survival()
	_check_invariant(inv, "apres clear")

	# A real block with a count of zero or less must collapse to a truly empty
	# slot, never to a block carrying a count of 0.
	inv.set_slot(0, Blocks.STONE, 0)
	eq(inv.slot_block(0), Blocks.AIR, "un compte nul vide la case")
	eq(inv.slot_count(0), 0, "un compte nul laisse le compte a zero")
	_check_invariant(inv, "apres set_slot avec un compte nul")

	inv.set_slot(1, Blocks.STONE, -12)
	eq(inv.slot_block(1), Blocks.AIR, "un compte negatif vide la case")
	_check_invariant(inv, "apres set_slot avec un compte negatif")

	# And AIR must never carry a count, whatever the caller asks for.
	inv.set_slot(2, Blocks.AIR, 500)
	eq(inv.slot_count(2), 0, "de l'air ne porte jamais de compte")
	_check_invariant(inv, "apres set_slot d'air avec un compte")

	inv.set_slot(3, Blocks.STONE, Inventory.STACK_MAX + 5000)
	eq(inv.slot_count(3), Inventory.STACK_MAX, "un compte excessif est ramene a STACK_MAX")
	_check_invariant(inv, "apres set_slot au-dela de STACK_MAX")

	# An unknown block id is refused outright rather than stored.
	inv.set_slot(4, Blocks.COUNT, 3)
	eq(inv.slot_block(4), Blocks.AIR, "un id inconnu n'est pas stocke")
	inv.set_slot(5, -3, 3)
	eq(inv.slot_block(5), Blocks.AIR, "un id negatif n'est pas stocke")
	_check_invariant(inv, "apres set_slot d'un id invalide")

	# Then every other mutation in turn.
	inv.set_slot(6, Blocks.DIRT, 7)
	inv.swap_slots(6, 30)
	_check_invariant(inv, "apres swap_slots")
	inv.add(Blocks.STONE, 1234)
	_check_invariant(inv, "apres add")
	inv.consume_selected(1)
	_check_invariant(inv, "apres consume_selected")
	inv.load_palette_page(0)
	_check_invariant(inv, "apres load_palette_page")
	inv.from_dict(_payload(Blocks.GLASS, -4))
	_check_invariant(inv, "apres from_dict avec des comptes negatifs")
	inv.clear()
	_check_invariant(inv, "apres clear final")
	done()


func test_clear_empties_everything_but_keeps_the_selection() -> void:
	var inv := Inventory.new()
	inv.select(5)
	var events := _watch(inv)
	inv.clear()

	for slot in Inventory.TOTAL_SLOTS:
		eq(inv.slot_block(slot), Blocks.AIR, "la case %d est vide" % slot)
		eq(inv.slot_count(slot), 0, "la case %d est a zero" % slot)
	eq(inv.selected, 5, "clear ne bouge pas la selection")
	eq(events["changed"], 1, "clear emet changed une fois")
	eq(_selection_events(events).size(), 0, "clear n'emet pas selection_changed")
	_check_invariant(inv, "apres clear")
	done()


# ---------------------------------------------------------------------------
# add()
# ---------------------------------------------------------------------------

func test_add_prefers_the_hotbar_over_the_storage() -> void:
	var inv := _survival()
	eq(inv.add(Blocks.STONE, 10), 0, "tout rentre dans un inventaire vide")
	eq(inv.slot_block(0), Blocks.STONE, "la premiere case de la barre est servie d'abord")
	eq(inv.slot_count(0), 10, "le compte de la premiere case")
	for slot in range(1, Inventory.TOTAL_SLOTS):
		eq(inv.slot_count(slot), 0, "aucune autre case n'est touchee (%d)" % slot)

	# A second block must open the next hotbar slot, still ahead of storage.
	eq(inv.add(Blocks.DIRT, 3), 0, "un second bloc rentre aussi")
	eq(inv.slot_block(1), Blocks.DIRT, "le second bloc prend la case 1")
	eq(inv.slot_count(1), 3, "le compte du second bloc")
	_check_invariant(inv, "apres deux add")
	done()


func test_add_tops_up_an_existing_stack_before_opening_a_slot() -> void:
	var inv := _survival()
	# A partial stack parked deep in the storage must still be topped up before
	# a fresh hotbar slot is opened, otherwise the inventory fragments.
	inv.set_slot(20, Blocks.STONE, 900)
	eq(inv.add(Blocks.STONE, 50), 0, "tout rentre dans la pile existante")
	eq(inv.slot_count(20), 950, "la pile de la reserve est completee")
	eq(inv.slot_block(0), Blocks.AIR, "aucune nouvelle case n'est ouverte")

	# When the top up is not enough, the overflow opens a slot, hotbar first.
	inv.set_slot(20, Blocks.STONE, Inventory.STACK_MAX - 4)
	eq(inv.add(Blocks.STONE, 10), 0, "le reste trouve une case libre")
	eq(inv.slot_count(20), Inventory.STACK_MAX, "la pile existante est saturee d'abord")
	eq(inv.slot_block(0), Blocks.STONE, "le surplus ouvre la premiere case libre")
	eq(inv.slot_count(0), 6, "le surplus est exactement ce qui restait")
	_check_invariant(inv, "apres un debordement de pile")

	# A saturated stack is skipped, not counted as room.
	inv.set_slot(31, Blocks.DIRT, Inventory.STACK_MAX)
	eq(inv.add(Blocks.DIRT, 2), 0, "la terre trouve une autre case")
	eq(inv.slot_count(31), Inventory.STACK_MAX, "une pile pleine n'est pas depassee")
	eq(inv.slot_block(1), Blocks.DIRT, "la terre ouvre la case suivante de la barre")
	eq(inv.slot_count(1), 2, "le compte de la nouvelle pile de terre")
	_check_invariant(inv, "apres avoir contourne une pile pleine")
	done()


func test_add_spills_across_several_slots() -> void:
	var inv := _survival()
	# More than one stack at once has to split, and every produced stack must
	# respect STACK_MAX.
	var amount := Inventory.STACK_MAX * 2 + 5
	eq(inv.add(Blocks.COBBLESTONE, amount), 0, "deux piles et demie rentrent")
	eq(inv.slot_count(0), Inventory.STACK_MAX, "premiere pile pleine")
	eq(inv.slot_count(1), Inventory.STACK_MAX, "seconde pile pleine")
	eq(inv.slot_count(2), 5, "le reliquat dans la troisieme case")
	eq(inv.count_of(Blocks.COBBLESTONE), amount, "le total stocke correspond")
	_check_invariant(inv, "apres un add multi-piles")
	done()


func test_add_returns_the_exact_leftover_when_full() -> void:
	var inv := _survival()
	for slot in Inventory.TOTAL_SLOTS:
		inv.set_slot(slot, Blocks.STONE, Inventory.STACK_MAX)

	# Exact leftover accounting: nine units of room, in the very last slot, and
	# fifty offered.
	inv.set_slot(Inventory.TOTAL_SLOTS - 1, Blocks.STONE, Inventory.STACK_MAX - 9)

	# Watch only from here, so the setup writes above do not pollute the count.
	var events := _watch(inv)
	eq(inv.add(Blocks.DIRT, 7), 7, "aucune case libre pour un autre bloc")
	eq(events["changed"], 0, "un add sans effet n'emet pas changed")

	eq(inv.add(Blocks.STONE, 50), 41, "seule la place disponible est prise")
	eq(inv.slot_count(Inventory.TOTAL_SLOTS - 1), Inventory.STACK_MAX, "la derniere pile est completee")
	eq(events["changed"], 1, "un add partiel emet changed une fois")

	eq(inv.add(Blocks.STONE, 100), 100, "un inventaire sature rend tout")
	eq(events["changed"], 1, "un add integralement refuse n'emet pas changed")
	_check_invariant(inv, "apres un add partiel")
	done()


func test_add_ignores_zero_negative_and_air() -> void:
	var inv := _survival()
	var before := _signature(inv)
	var events := _watch(inv)

	eq(inv.add(Blocks.STONE, 0), 0, "ajouter zero ne laisse aucun reliquat")
	eq(inv.add(Blocks.STONE, -5), 0, "ajouter une quantite negative ne laisse aucun reliquat")
	eq(_signature(inv), before, "ni zero ni negatif ne modifient l'inventaire")
	eq(events["changed"], 0, "un add sans quantite n'emet pas changed")

	# An id that is not a real block cannot be stored, so it is all leftover.
	eq(inv.add(Blocks.AIR, 4), 4, "de l'air ne se stocke pas")
	eq(inv.add(Blocks.COUNT, 4), 4, "un id inconnu ne se stocke pas")
	eq(inv.add(-2, 4), 4, "un id negatif ne se stocke pas")
	eq(_signature(inv), before, "un id invalide ne modifie pas l'inventaire")
	eq(events["changed"], 0, "un id invalide n'emet pas changed")
	_check_invariant(inv, "apres des add refuses")
	done()


func test_add_is_bottomless_in_creative() -> void:
	var inv := Inventory.new()
	inv.clear()
	var before := _signature(inv)
	var events := _watch(inv)
	eq(inv.add(Blocks.STONE, 500), 0, "le creatif ne renvoie jamais de reliquat")
	eq(_signature(inv), before, "le creatif ne stocke rien")
	eq(events["changed"], 0, "un add en creatif n'emet pas changed")
	done()


# ---------------------------------------------------------------------------
# consume_selected()
# ---------------------------------------------------------------------------

func test_consume_selected_needs_stock_in_survival() -> void:
	var inv := _survival()
	inv.select(0)
	check(not inv.consume_selected(), "une case vide ne peut rien fournir")

	inv.set_slot(0, Blocks.STONE, 2)
	var events := _watch(inv)
	check(inv.consume_selected(), "un premier retrait reussit")
	eq(inv.slot_count(0), 1, "le compte descend de un")
	eq(events["changed"], 1, "un retrait emet changed")

	# An oversized request is refused whole, leaving the stack untouched.
	check(not inv.consume_selected(5), "un retrait trop gros est refuse")
	eq(inv.slot_count(0), 1, "un refus ne decremente pas")
	eq(inv.slot_block(0), Blocks.STONE, "un refus ne vide pas la case")
	eq(events["changed"], 1, "un refus n'emet pas changed")

	check(inv.consume_selected(), "le dernier bloc part")
	eq(inv.slot_block(0), Blocks.AIR, "la case se vide vraiment")
	eq(inv.slot_count(0), 0, "et son compte tombe a zero")
	_check_invariant(inv, "apres avoir vide une pile")

	check(not inv.consume_selected(), "la case vide refuse a nouveau")
	# A request of zero or less is a no-op that still reports success, so the
	# caller does not have to guard it.
	check(inv.consume_selected(0), "un retrait de zero est accepte")
	check(inv.consume_selected(-3), "un retrait negatif est accepte")
	eq(inv.slot_count(0), 0, "aucun de ces retraits ne cree du stock")
	_check_invariant(inv, "apres des retraits nuls")
	done()


func test_consume_selected_never_decrements_in_creative() -> void:
	var inv := Inventory.new()
	check(inv.creative, "l'inventaire de depart est creatif")
	var events := _watch(inv)
	var before := _signature(inv)

	check(inv.consume_selected(), "le creatif fournit toujours")
	check(inv.consume_selected(100000), "le creatif fournit meme une quantite absurde")
	eq(inv.slot_count(0), Inventory.STACK_MAX, "le creatif ne decremente pas")

	# Even an empty selected slot must answer yes in creative.
	inv.set_slot(0, Blocks.AIR, 0)
	check(inv.consume_selected(), "le creatif fournit meme sur une case vide")

	inv.set_slot(0, int(Blocks.PALETTE[0]), Inventory.STACK_MAX)
	eq(_signature(inv), before, "le creatif laisse l'etat intact")
	eq(_selection_events(events).size(), 0, "consume_selected n'emet pas selection_changed")
	_check_invariant(inv, "apres des retraits en creatif")
	done()


func test_count_of_and_has_room_for() -> void:
	var inv := _survival()
	eq(inv.count_of(Blocks.STONE), 0, "aucun stock au depart")
	eq(inv.count_of(Blocks.AIR), 0, "l'air ne se compte pas")
	eq(inv.count_of(Blocks.COUNT), 0, "un id inconnu ne se compte pas")
	check(inv.has_room_for(Blocks.STONE), "un inventaire vide a de la place")
	check(not inv.has_room_for(Blocks.AIR), "l'air n'a jamais de place")

	inv.set_slot(0, Blocks.STONE, 40)
	inv.set_slot(15, Blocks.STONE, 2)
	eq(inv.count_of(Blocks.STONE), 42, "le total additionne barre et reserve")

	for slot in Inventory.TOTAL_SLOTS:
		inv.set_slot(slot, Blocks.STONE, Inventory.STACK_MAX)
	check(not inv.has_room_for(Blocks.STONE), "plus de place pour de la pierre")
	check(not inv.has_room_for(Blocks.DIRT), "plus de place pour de la terre")

	# Creative answers with the sentinel STACK_MAX so the interface can hide
	# the counters entirely.
	inv.creative = true
	eq(inv.count_of(Blocks.DIRT), Inventory.STACK_MAX, "le creatif annonce STACK_MAX")
	check(inv.has_room_for(Blocks.DIRT), "le creatif a toujours de la place")
	eq(inv.count_of(Blocks.AIR), 0, "meme en creatif l'air ne compte pas")
	done()


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

func test_select_ignores_out_of_range_slots() -> void:
	var inv := Inventory.new()
	var events := _watch(inv)

	inv.select(8)
	eq(inv.selected, 8, "la derniere case de la barre est atteignable")
	eq(_selection_events(events), [8], "select emet la case atteinte")

	inv.select(-1)
	eq(inv.selected, 8, "une case negative est ignoree")
	inv.select(Inventory.HOTBAR_SLOTS)
	eq(inv.selected, 8, "la premiere case de reserve n'est pas selectionnable")
	inv.select(Inventory.TOTAL_SLOTS)
	eq(inv.selected, 8, "une case de reserve n'est pas selectionnable")
	inv.select(9999)
	eq(inv.selected, 8, "une case absurde est ignoree")
	eq(_selection_events(events), [8], "une case refusee n'emet rien")

	check(inv.selected >= 0 and inv.selected < Inventory.HOTBAR_SLOTS, "la selection reste dans la barre")
	eq(inv.selected_block(), inv.slot_block(8), "selected_block suit la selection")
	eq(events["changed"], 0, "select n'emet pas changed")
	_check_invariant(inv, "apres des selections refusees")
	done()


func test_cycle_wraps_in_both_directions() -> void:
	var inv := Inventory.new()
	var events := _watch(inv)

	inv.cycle(1)
	eq(inv.selected, 1, "un cran vers l'avant")
	inv.cycle(-1)
	eq(inv.selected, 0, "un cran vers l'arriere")

	# Wrapping down from the first slot lands on the last one.
	inv.cycle(-1)
	eq(inv.selected, Inventory.HOTBAR_SLOTS - 1, "sous zero on enroule sur la derniere case")
	# And back up over the top.
	inv.cycle(1)
	eq(inv.selected, 0, "au-dela de la derniere on enroule sur la premiere")

	# A delta larger than the hotbar must still land inside it.
	inv.cycle(Inventory.HOTBAR_SLOTS)
	eq(inv.selected, 0, "un delta d'une barre complete revient au meme endroit")
	inv.cycle(Inventory.HOTBAR_SLOTS * 3 + 4)
	eq(inv.selected, 4, "un grand delta positif enroule proprement")
	inv.cycle(-(Inventory.HOTBAR_SLOTS * 5 + 6))
	eq(inv.selected, 7, "un grand delta negatif enroule proprement")
	inv.cycle(0)
	eq(inv.selected, 7, "un delta nul ne bouge pas")

	# Every single step of a long walk in both directions stays in range.
	for step in range(-40, 41):
		inv.cycle(step)
		check(inv.selected >= 0 and inv.selected < Inventory.HOTBAR_SLOTS,
			"cycle(%d) sort de la barre (obtenu %d)" % [step, inv.selected])

	eq(events["changed"], 0, "cycle n'emet pas changed")
	var emitted := _selection_events(events)
	check(emitted.size() > 0, "cycle emet selection_changed")
	eq(emitted[emitted.size() - 1], inv.selected, "la derniere emission porte la case courante")
	done()


# ---------------------------------------------------------------------------
# swap_slots()
# ---------------------------------------------------------------------------

func test_swap_slots_exchanges_hotbar_and_storage() -> void:
	var inv := _survival()
	inv.set_slot(2, Blocks.STONE, 5)
	inv.set_slot(30, Blocks.DIRT, 700)
	var events := _watch(inv)

	inv.swap_slots(2, 30)
	eq(inv.slot_block(2), Blocks.DIRT, "la case de barre recoit la terre")
	eq(inv.slot_count(2), 700, "avec son compte")
	eq(inv.slot_block(30), Blocks.STONE, "la case de reserve recoit la pierre")
	eq(inv.slot_count(30), 5, "avec son compte")
	eq(events["changed"], 1, "un echange emet changed")

	# Swapping with an empty slot moves the emptiness, invariant included.
	inv.swap_slots(2, 9)
	eq(inv.slot_block(2), Blocks.AIR, "la case de depart devient vide")
	eq(inv.slot_count(2), 0, "et son compte tombe a zero")
	eq(inv.slot_block(9), Blocks.DIRT, "la terre a demenage")
	eq(inv.slot_count(9), 700, "sans perdre son compte")
	_check_invariant(inv, "apres un echange avec une case vide")
	eq(_selection_events(events).size(), 0, "swap_slots n'emet pas selection_changed")
	done()


func test_swap_slots_is_a_noop_on_bad_indices() -> void:
	var inv := _survival()
	inv.set_slot(0, Blocks.STONE, 5)
	inv.set_slot(9, Blocks.DIRT, 6)
	var before := _signature(inv)
	var events := _watch(inv)

	inv.swap_slots(-1, 0)
	inv.swap_slots(0, -1)
	inv.swap_slots(Inventory.TOTAL_SLOTS, 0)
	inv.swap_slots(0, Inventory.TOTAL_SLOTS)
	inv.swap_slots(-5, 9999)
	eq(_signature(inv), before, "un index hors bornes ne change rien")
	eq(events["changed"], 0, "un echange refuse n'emet pas changed")

	inv.swap_slots(0, 0)
	eq(_signature(inv), before, "echanger une case avec elle-meme ne change rien")
	eq(events["changed"], 0, "un echange sur place n'emet pas changed")
	_check_invariant(inv, "apres des echanges refuses")
	done()


# ---------------------------------------------------------------------------
# Creative palette
# ---------------------------------------------------------------------------

func test_palette_page_count_agrees_with_the_palette() -> void:
	var inv := Inventory.new()
	var size: int = Blocks.PALETTE.size()
	check(size > 0, "la palette n'est pas vide")

	# Independent ceiling division, so the test does not merely restate the
	# module's own arithmetic.
	var expected: int = int(ceil(float(size) / float(Inventory.HOTBAR_SLOTS)))
	eq(inv.palette_page_count(), expected, "nombre de pages de palette")

	var pages: int = inv.palette_page_count()
	check(pages * Inventory.HOTBAR_SLOTS >= size, "les pages couvrent toute la palette")
	check((pages - 1) * Inventory.HOTBAR_SLOTS < size, "aucune page entierement vide")
	done()


func test_load_palette_page_fills_nine_slots() -> void:
	var inv := Inventory.new()
	var palette := Blocks.PALETTE
	var pages: int = inv.palette_page_count()

	for page in pages:
		# Dirty every hotbar slot first, so a page that does not cover them all
		# has to clear the leftovers instead of leaving stale blocks behind.
		for i in Inventory.HOTBAR_SLOTS:
			inv.set_slot(i, Blocks.BEDROCK, 3)
		inv.load_palette_page(page)

		var base: int = page * Inventory.HOTBAR_SLOTS
		for i in Inventory.HOTBAR_SLOTS:
			var index: int = base + i
			if index < palette.size():
				eq(inv.slot_block(i), int(palette[index]),
					"page %d case %d porte l'entree %d" % [page, i, index])
				eq(inv.slot_count(i), Inventory.STACK_MAX,
					"page %d case %d est une pile pleine" % [page, i])
			else:
				# Last partial page: no palette entry, so the slot is emptied.
				eq(inv.slot_block(i), Blocks.AIR,
					"page %d case %d sans entree de palette est videe" % [page, i])
				eq(inv.slot_count(i), 0,
					"page %d case %d videe a un compte nul" % [page, i])
		_check_invariant(inv, "apres load_palette_page(%d)" % page)
	done()


func test_load_palette_page_leaves_storage_and_rejects_bad_pages() -> void:
	var inv := Inventory.new()
	inv.set_slot(20, Blocks.DIAMOND_ORE, 12)
	inv.load_palette_page(1)
	eq(inv.slot_block(20), Blocks.DIAMOND_ORE, "la reserve n'est pas touchee")
	eq(inv.slot_count(20), 12, "le compte de la reserve est intact")

	var before := _signature(inv)
	var events := _watch(inv)
	inv.load_palette_page(-1)
	inv.load_palette_page(inv.palette_page_count())
	inv.load_palette_page(9999)
	eq(_signature(inv), before, "une page hors bornes ne change rien")
	eq(events["changed"], 0, "une page refusee n'emet pas changed")

	inv.load_palette_page(0)
	eq(events["changed"], 1, "une page valide emet changed une fois")
	eq(_selection_events(events).size(), 0, "load_palette_page n'emet pas selection_changed")
	done()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

func test_dict_round_trip_is_exact() -> void:
	var inv := _survival()
	inv.set_slot(0, Blocks.STONE, 999)
	inv.set_slot(3, Blocks.GLASS, 1)
	inv.set_slot(8, Blocks.WATER, 64)
	inv.set_slot(9, Blocks.LAMP, 17)
	inv.set_slot(35, Blocks.DIAMOND_ORE, 2)
	inv.select(3)
	var expected := _signature(inv)

	var data := inv.to_dict()
	eq(data["version"], Inventory.SAVE_VERSION, "la version est ecrite")
	eq((data["blocks"] as Array).size(), Inventory.TOTAL_SLOTS, "36 ids ecrits")
	eq((data["counts"] as Array).size(), Inventory.TOTAL_SLOTS, "36 comptes ecrits")
	eq(data["selected"], 3, "la selection est ecrite")
	eq(data["creative"], false, "le mode est ecrit")

	var restored := Inventory.new()
	restored.from_dict(data)
	eq(_signature(restored), expected, "l'aller-retour restitue l'etat exact")
	_check_invariant(restored, "apres from_dict")

	# The snapshot claims to be JSON friendly, and JSON turns every number into
	# a float, so the round trip has to survive that too.
	var json_data: Variant = JSON.parse_string(JSON.stringify(data))
	eq(typeof(json_data), TYPE_DICTIONARY, "le JSON se relit en dictionnaire")
	var from_json := Inventory.new()
	from_json.from_dict(json_data as Dictionary)
	eq(_signature(from_json), expected, "l'aller-retour JSON restitue l'etat exact")
	_check_invariant(from_json, "apres from_dict depuis du JSON")
	done()


func test_round_trip_of_a_creative_inventory() -> void:
	var inv := Inventory.new()
	inv.select(6)
	var expected := _signature(inv)
	var restored := Inventory.new()
	restored.creative = false
	restored.clear()
	restored.from_dict(inv.to_dict())
	eq(_signature(restored), expected, "un inventaire creatif se restaure a l'identique")
	check(restored.creative, "le drapeau creatif est restaure")
	eq(restored.selected, 6, "la selection est restauree")
	done()


func test_from_dict_rejects_malformed_input_whole() -> void:
	var inv := _survival()
	inv.set_slot(0, Blocks.STONE, 5)
	inv.select(2)
	var before := _signature(inv)
	var events := _watch(inv)

	var bad_payloads: Array = []
	# Missing keys.
	bad_payloads.append({})
	bad_payloads.append({"blocks": []})
	bad_payloads.append({"counts": []})
	# Wrong lengths.
	var short_payload := _payload(Blocks.DIRT, 4)
	short_payload["blocks"] = [Blocks.DIRT, Blocks.DIRT]
	bad_payloads.append(short_payload)
	var long_payload := _payload(Blocks.DIRT, 4)
	var too_many: Array = (long_payload["counts"] as Array).duplicate()
	too_many.append(1)
	long_payload["counts"] = too_many
	bad_payloads.append(long_payload)
	# Lists that are not lists of numbers.
	var stringy := _payload(Blocks.DIRT, 4)
	(stringy["blocks"] as Array)[7] = "pierre"
	bad_payloads.append(stringy)
	var not_a_list := _payload(Blocks.DIRT, 4)
	not_a_list["counts"] = "beaucoup"
	bad_payloads.append(not_a_list)
	var nested := _payload(Blocks.DIRT, 4)
	(nested["counts"] as Array)[0] = {"a": 1}
	bad_payloads.append(nested)
	# Unknown block ids.
	bad_payloads.append(_payload(Blocks.COUNT, 4))
	var negative_id := _payload(Blocks.DIRT, 4)
	(negative_id["blocks"] as Array)[12] = -1
	bad_payloads.append(negative_id)
	# Non finite numbers coming from a corrupted JSON file.
	var not_a_number := _payload(Blocks.DIRT, 4)
	(not_a_number["counts"] as Array)[3] = NAN
	bad_payloads.append(not_a_number)
	var infinite := _payload(Blocks.DIRT, 4)
	(infinite["counts"] as Array)[3] = INF
	bad_payloads.append(infinite)
	# Valid slots but a broken header: the module must still write nothing,
	# which is the real "no half load" check since the slots pass validation.
	var bad_selected := _payload(Blocks.DIRT, 4)
	bad_selected["selected"] = "trois"
	bad_payloads.append(bad_selected)
	var bad_creative := _payload(Blocks.DIRT, 4)
	bad_creative["creative"] = 1
	bad_payloads.append(bad_creative)

	for index in bad_payloads.size():
		var payload: Dictionary = bad_payloads[index]
		inv.from_dict(payload)
		eq(_signature(inv), before, "la charge malformee %d laisse l'inventaire intact" % index)
	eq(events["changed"], 0, "une charge rejetee n'emet pas changed")
	_check_invariant(inv, "apres des charges rejetees")
	done()


func test_from_dict_normalises_out_of_range_values() -> void:
	var inv := Inventory.new()
	# An excessive selection is clamped rather than refused, and counts are
	# normalised to the invariant instead of being stored as given.
	var payload := _payload(Blocks.STONE, Inventory.STACK_MAX + 1000)
	payload["selected"] = 42
	inv.from_dict(payload)
	eq(inv.selected, Inventory.HOTBAR_SLOTS - 1, "une selection trop grande est ramenee dans la barre")
	eq(inv.slot_count(0), Inventory.STACK_MAX, "un compte trop grand est ramene a STACK_MAX")

	payload["selected"] = -7
	inv.from_dict(payload)
	eq(inv.selected, 0, "une selection negative est ramenee a zero")

	# A real block with a count of zero, and AIR with a count, both collapse to
	# a properly empty slot.
	var mixed := _payload(Blocks.STONE, 0)
	(mixed["blocks"] as Array)[5] = Blocks.AIR
	(mixed["counts"] as Array)[5] = 12
	mixed["selected"] = 0
	inv.from_dict(mixed)
	for slot in Inventory.TOTAL_SLOTS:
		eq(inv.slot_block(slot), Blocks.AIR, "la case %d est vide apres normalisation" % slot)
		eq(inv.slot_count(slot), 0, "la case %d est a zero apres normalisation" % slot)
	_check_invariant(inv, "apres from_dict normalisant les valeurs")
	done()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

func test_selection_changed_comes_only_from_select_and_cycle() -> void:
	var inv := _survival()
	var events := _watch(inv)

	inv.set_slot(0, Blocks.STONE, 4)
	inv.swap_slots(0, 12)
	inv.add(Blocks.DIRT, 3)
	inv.set_slot(0, Blocks.DIRT, 3)
	inv.consume_selected(1)
	inv.clear()
	inv.load_palette_page(0)
	inv.from_dict(_payload(Blocks.STONE, 2))
	eq(_selection_events(events).size(), 0, "aucune mutation n'emet selection_changed")

	inv.select(4)
	eq(_selection_events(events), [4], "select emet selection_changed")
	inv.cycle(2)
	eq(_selection_events(events), [4, 6], "cycle emet selection_changed")
	done()


func test_changed_comes_from_every_other_mutation() -> void:
	var inv := _survival()
	var events := _watch(inv)
	var seen := 0

	inv.set_slot(0, Blocks.STONE, 4)
	seen += 1
	eq(events["changed"], seen, "set_slot emet changed")

	inv.swap_slots(0, 12)
	seen += 1
	eq(events["changed"], seen, "swap_slots emet changed")

	eq(inv.add(Blocks.DIRT, 3), 0, "l'ajout de terre reussit")
	seen += 1
	eq(events["changed"], seen, "add emet changed")

	inv.select(1)
	check(inv.selected_block() == Blocks.DIRT or inv.selected_block() == Blocks.AIR,
		"la case 1 est bien celle ouverte par add")
	inv.set_slot(inv.selected, Blocks.DIRT, 3)
	seen += 1
	check(inv.consume_selected(1), "le retrait reussit")
	seen += 1
	eq(events["changed"], seen, "consume_selected emet changed")

	inv.clear()
	seen += 1
	eq(events["changed"], seen, "clear emet changed")

	inv.load_palette_page(0)
	seen += 1
	eq(events["changed"], seen, "load_palette_page emet changed")

	inv.from_dict(_payload(Blocks.STONE, 2))
	seen += 1
	eq(events["changed"], seen, "from_dict emet changed")

	# And select / cycle must stay out of it.
	inv.select(0)
	inv.cycle(3)
	eq(events["changed"], seen, "ni select ni cycle n'emettent changed")
	done()
