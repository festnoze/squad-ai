class_name Recipes
## Crafting recipe registry.
##
## A recipe is a plain Dictionary:
##   output   id produced (block or item)
##   count    units produced per craft
##   inputs   Array of [id, count] pairs, all consumed together
##   table    true when the recipe needs a crafting table nearby
##
## Hand recipes (table == false) cover the bootstrap chain: logs to planks,
## planks to sticks and to the crafting table itself, plus torches. Everything
## else requires standing next to a placed crafting table.

static var _all: Array[Dictionary] = []


static func _static_init() -> void:
	_all = [
		# --- hand recipes -----------------------------------------------------
		_make(Blocks.OAK_PLANKS, 4, [[Blocks.OAK_LOG, 1]], false),
		_make(Blocks.BIRCH_PLANKS, 4, [[Blocks.BIRCH_LOG, 1]], false),
		_make(Items.STICK, 4, [[Blocks.OAK_PLANKS, 2]], false),
		_make(Items.STICK, 4, [[Blocks.BIRCH_PLANKS, 2]], false),
		_make(Blocks.CRAFTING_TABLE, 1, [[Blocks.OAK_PLANKS, 4]], false),
		_make(Blocks.CRAFTING_TABLE, 1, [[Blocks.BIRCH_PLANKS, 4]], false),
		_make(Blocks.TORCH, 4, [[Items.STICK, 1], [Items.COAL, 1]], false),

		# --- pickaxes ----------------------------------------------------------
		_make(Items.WOOD_PICKAXE, 1, [[Blocks.OAK_PLANKS, 3], [Items.STICK, 2]], true),
		_make(Items.STONE_PICKAXE, 1, [[Blocks.COBBLESTONE, 3], [Items.STICK, 2]], true),
		_make(Items.IRON_PICKAXE, 1, [[Items.IRON_INGOT, 3], [Items.STICK, 2]], true),
		_make(Items.DIAMOND_PICKAXE, 1, [[Items.DIAMOND, 3], [Items.STICK, 2]], true),

		# --- swords -------------------------------------------------------------
		_make(Items.WOOD_SWORD, 1, [[Blocks.OAK_PLANKS, 2], [Items.STICK, 1]], true),
		_make(Items.STONE_SWORD, 1, [[Blocks.COBBLESTONE, 2], [Items.STICK, 1]], true),
		_make(Items.IRON_SWORD, 1, [[Items.IRON_INGOT, 2], [Items.STICK, 1]], true),
		_make(Items.DIAMOND_SWORD, 1, [[Items.DIAMOND, 2], [Items.STICK, 1]], true),

		# --- ranged -------------------------------------------------------------
		_make(Items.BOW, 1, [[Items.STICK, 3], [Blocks.OAK_PLANKS, 2]], true),
		_make(Items.ARROW, 4, [[Items.STICK, 1], [Blocks.GRAVEL, 1]], true),

		# --- building extras ------------------------------------------------------
		_make(Blocks.STONE_BRICK, 4, [[Blocks.STONE, 4]], true),
		_make(Blocks.BOOKSHELF, 1, [[Blocks.OAK_PLANKS, 6]], true),
		_make(Blocks.CHEST, 1, [[Blocks.OAK_PLANKS, 8]], true),
		_make(Blocks.LAMP, 2, [[Items.GOLD_INGOT, 1], [Blocks.TORCH, 1]], true),
	]


static func _make(output: int, count: int, inputs: Array, table: bool) -> Dictionary:
	return {"output": output, "count": count, "inputs": inputs, "table": table}


static func all() -> Array[Dictionary]:
	return _all


## True when the inventory holds every ingredient and can receive the output.
## Creative inventories can always craft (materials are bottomless there).
static func craftable(recipe: Dictionary, inv: Inventory) -> bool:
	if inv == null:
		return false
	if inv.creative:
		return true
	for input: Array in recipe["inputs"]:
		if inv.count_of(input[0]) < input[1]:
			return false
	return inv.has_room_for(recipe["output"])


## Consumes the ingredients and stores the output. Returns false untouched when
## the recipe is not craftable. In creative mode the output lands in the
## selected hotbar slot, because creative add() intentionally stores nothing.
static func craft(recipe: Dictionary, inv: Inventory) -> bool:
	if not craftable(recipe, inv):
		return false
	if inv.creative:
		inv.set_slot(inv.selected, recipe["output"], recipe["count"])
		return true
	for input: Array in recipe["inputs"]:
		if not inv.take(input[0], input[1]):
			return false
	inv.add(recipe["output"], recipe["count"])
	return true
