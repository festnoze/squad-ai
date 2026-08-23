extends TestCase
## Consistency of the item registry: ids, names, previews, tool tables and the
## ore drop remap the interaction module relies on.


func suite_name() -> String:
	return "items"


func test_id_ranges_do_not_collide() -> void:
	check(Items.BASE > Blocks.COUNT, "les ids d'objets vivent au dessus des blocs")
	check(Items.END - 1 <= 255, "les ids d'objets tiennent dans un octet")
	check(Items.is_item(Items.STICK), "le baton est un objet")
	check(not Items.is_item(Blocks.STONE), "un bloc n'est pas un objet")
	check(not Items.is_item(Blocks.COUNT), "l'id sentinelle des blocs reste invalide")
	check(not Items.is_item(Items.END), "l'id sentinelle des objets reste invalide")
	check(Items.is_valid_id(Blocks.STONE), "un vrai bloc est un id valide d'inventaire")
	check(Items.is_valid_id(Items.BOW), "un objet est un id valide d'inventaire")
	check(not Items.is_valid_id(Blocks.AIR), "l'air n'est pas un id valide d'inventaire")
	done()


func test_every_item_has_name_and_icon() -> void:
	for id in range(Items.BASE, Items.END):
		ne(Items.display_name_any(id), "", "l'objet %d doit avoir un nom" % id)
		var tex := Items.preview_any(id, 32)
		check(tex != null, "l'objet %d doit avoir une icone" % id)
	# The dispatcher also serves blocks.
	eq(Items.display_name_any(Blocks.STONE), Blocks.display_name(Blocks.STONE),
		"le repartiteur de noms sert aussi les blocs")
	check(Items.preview_any(Blocks.STONE, 32) != null, "le repartiteur d'icones sert aussi les blocs")
	done()


func test_pickaxe_speeds() -> void:
	check(Items.dig_multiplier(Items.WOOD_PICKAXE, Blocks.STONE) > 1.0,
		"une pioche accelere le minage de la pierre")
	check(Items.dig_multiplier(Items.DIAMOND_PICKAXE, Blocks.STONE)
			> Items.dig_multiplier(Items.WOOD_PICKAXE, Blocks.STONE),
		"une meilleure pioche mine plus vite")
	eq(Items.dig_multiplier(Items.WOOD_PICKAXE, Blocks.DIRT), 1.0,
		"la pioche n'accelere pas la terre")
	eq(Items.dig_multiplier(Items.WOOD_SWORD, Blocks.STONE), 1.0,
		"une epee ne mine pas plus vite")
	eq(Items.dig_multiplier(Blocks.DIRT, Blocks.STONE), 1.0,
		"un bloc en main ne mine pas plus vite")
	done()


func test_melee_damage_ladder() -> void:
	eq(Items.melee_damage(Blocks.AIR), Items.HAND_DAMAGE, "la main nue fait 1 degat")
	eq(Items.melee_damage(Blocks.DIRT), Items.HAND_DAMAGE, "un bloc en main frappe comme la main")
	check(Items.melee_damage(Items.WOOD_SWORD) > Items.HAND_DAMAGE,
		"une epee frappe plus fort que la main")
	check(Items.melee_damage(Items.DIAMOND_SWORD) > Items.melee_damage(Items.WOOD_SWORD),
		"une meilleure epee frappe plus fort")
	check(Items.melee_damage(Items.WOOD_PICKAXE) > Items.HAND_DAMAGE,
		"une pioche frappe un peu plus fort que la main")
	check(Items.melee_damage(Items.WOOD_SWORD) > Items.melee_damage(Items.WOOD_PICKAXE),
		"l'epee reste la meilleure arme de melee")
	done()


func test_palette_holds_every_item_once() -> void:
	var seen := {}
	for id in Items.PALETTE:
		check(Items.is_item(id), "la palette d'objets contient un id invalide %d" % id)
		check(not seen.has(id), "l'objet %d apparait deux fois dans la palette" % id)
		seen[id] = true
	eq(Items.PALETTE.size(), Items.END - Items.BASE,
		"la palette expose tous les objets du registre")
	done()


## Named is_gear, not is_tool: Script.is_tool() is an engine method and would
## shadow the static on the class_name, so the call would take no argument.
func test_is_gear_separates_gear_from_materials() -> void:
	check(Items.is_gear(Items.WOOD_PICKAXE), "une pioche est un outil")
	check(Items.is_gear(Items.DIAMOND_SWORD), "une epee est un outil")
	check(Items.is_gear(Items.BOW), "un arc est un outil")
	check(not Items.is_gear(Items.ARROW), "une fleche se stocke en pile")
	check(not Items.is_gear(Items.STICK), "un baton se stocke en pile")
	check(not Items.is_gear(Blocks.STONE), "un bloc n'est pas un outil")
	check(not Items.is_gear(Blocks.AIR), "l'air n'est pas un outil")
	done()


func test_ore_drops_become_items() -> void:
	eq(Items.drop_for(Blocks.COAL_ORE), Items.COAL, "le charbon sort du minerai de charbon")
	eq(Items.drop_for(Blocks.IRON_ORE), Items.IRON_INGOT, "le fer sort du minerai de fer")
	eq(Items.drop_for(Blocks.GOLD_ORE), Items.GOLD_INGOT, "l'or sort du minerai d'or")
	eq(Items.drop_for(Blocks.DIAMOND_ORE), Items.DIAMOND, "le diamant sort du minerai de diamant")
	eq(Items.drop_for(Blocks.STONE), Blocks.COBBLESTONE, "la pierre suit la table des blocs")
	eq(Items.drop_for(Blocks.DIRT), Blocks.DIRT, "la terre se laisse ramasser telle quelle")
	done()
