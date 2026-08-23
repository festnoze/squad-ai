class_name Items
## Registry of non-block items: tools, weapons and crafting materials.
##
## Item ids live in their own byte range (BASE..END-1), far above Blocks.COUNT,
## so a single byte still identifies any inventory content and the two
## registries can never collide. Blocks stays pure: the ore-to-item drop remap
## lives here (drop_for), not in the block table.
##
## Icons are painted by code as 16x16 pixel-art sprites scaled up with nearest
## neighbour, following the zero-binary-asset rule of the project.

enum Kind { MATERIAL, PICKAXE, SWORD, BOW, ARROW }

## Tool tiers, used for dig speed and melee damage.
enum Tier { NONE, WOOD, STONE, IRON, DIAMOND }

const BASE := 200

const STICK := 200
const COAL := 201
const IRON_INGOT := 202
const GOLD_INGOT := 203
const DIAMOND := 204
const WOOD_PICKAXE := 205
const STONE_PICKAXE := 206
const IRON_PICKAXE := 207
const DIAMOND_PICKAXE := 208
const WOOD_SWORD := 209
const STONE_SWORD := 210
const IRON_SWORD := 211
const DIAMOND_SWORD := 212
const BOW := 213
const ARROW := 214

const END := 215

## Damage dealt with the bare hand or any non-weapon item.
const HAND_DAMAGE := 1

## Bow projectile damage (the arrow item itself is just ammunition).
const BOW_ARROW_DAMAGE := 7

## One entry per item id, in id order starting at BASE.
##   name    display name (French, shown to the player)
##   kind    Kind value
##   tier    Tier value, NONE for materials
const _TABLE: Array[Dictionary] = [
	{"id": STICK, "name": "Bâton", "kind": Kind.MATERIAL, "tier": Tier.NONE},
	{"id": COAL, "name": "Charbon", "kind": Kind.MATERIAL, "tier": Tier.NONE},
	{"id": IRON_INGOT, "name": "Lingot de fer", "kind": Kind.MATERIAL, "tier": Tier.NONE},
	{"id": GOLD_INGOT, "name": "Lingot d'or", "kind": Kind.MATERIAL, "tier": Tier.NONE},
	{"id": DIAMOND, "name": "Diamant", "kind": Kind.MATERIAL, "tier": Tier.NONE},
	{"id": WOOD_PICKAXE, "name": "Pioche en bois", "kind": Kind.PICKAXE, "tier": Tier.WOOD},
	{"id": STONE_PICKAXE, "name": "Pioche en pierre", "kind": Kind.PICKAXE, "tier": Tier.STONE},
	{"id": IRON_PICKAXE, "name": "Pioche en fer", "kind": Kind.PICKAXE, "tier": Tier.IRON},
	{"id": DIAMOND_PICKAXE, "name": "Pioche en diamant", "kind": Kind.PICKAXE, "tier": Tier.DIAMOND},
	{"id": WOOD_SWORD, "name": "Épée en bois", "kind": Kind.SWORD, "tier": Tier.WOOD},
	{"id": STONE_SWORD, "name": "Épée en pierre", "kind": Kind.SWORD, "tier": Tier.STONE},
	{"id": IRON_SWORD, "name": "Épée en fer", "kind": Kind.SWORD, "tier": Tier.IRON},
	{"id": DIAMOND_SWORD, "name": "Épée en diamant", "kind": Kind.SWORD, "tier": Tier.DIAMOND},
	{"id": BOW, "name": "Arc", "kind": Kind.BOW, "tier": Tier.NONE},
	{"id": ARROW, "name": "Flèche", "kind": Kind.ARROW, "tier": Tier.NONE},
]

## Order of the item palette shown by the inventory screen, tools first so the
## row a player reaches for is the top one.
const PALETTE: PackedByteArray = [
	WOOD_PICKAXE, STONE_PICKAXE, IRON_PICKAXE, DIAMOND_PICKAXE,
	WOOD_SWORD, STONE_SWORD, IRON_SWORD, DIAMOND_SWORD,
	BOW, ARROW,
	STICK, COAL, IRON_INGOT, GOLD_INGOT, DIAMOND,
]

## Dig speed multiplier of a pickaxe on pick-family blocks, indexed by Tier.
const _PICK_SPEED: Array[float] = [1.0, 3.0, 5.0, 7.0, 9.0]

## Melee damage of a sword, indexed by Tier.
const _SWORD_DAMAGE: Array[int] = [1, 4, 5, 6, 7]

## Melee damage of a pickaxe, indexed by Tier.
const _PICK_DAMAGE: Array[int] = [1, 2, 3, 4, 5]

# ---------------------------------------------------------------------------
# Static lookup tables
# ---------------------------------------------------------------------------

static var _kind: PackedByteArray
static var _tier: PackedByteArray
static var _display: PackedStringArray
static var _pick_blocks: Dictionary
static var _drop_map: Dictionary
static var _icon_cache: Dictionary = {}


static func _static_init() -> void:
	var count := END - BASE
	_kind = PackedByteArray()
	_kind.resize(count)
	_tier = PackedByteArray()
	_tier.resize(count)
	_display = PackedStringArray()
	_display.resize(count)

	assert(_TABLE.size() == count, "Items._TABLE must hold one entry per id")
	for pos in _TABLE.size():
		var d: Dictionary = _TABLE[pos]
		var id: int = d["id"]
		assert(id == BASE + pos, "Items._TABLE entry %d is out of order (id %d)" % [pos, id])
		_kind[pos] = d["kind"]
		_tier[pos] = d["tier"]
		_display[pos] = d["name"]

	# Blocks a pickaxe is meant for. Everything else digs at hand speed.
	_pick_blocks = {}
	for id in [Blocks.STONE, Blocks.COBBLESTONE, Blocks.STONE_BRICK, Blocks.GRANITE,
			Blocks.MARBLE, Blocks.MOSSY_COBBLE, Blocks.SANDSTONE, Blocks.OBSIDIAN,
			Blocks.COAL_ORE, Blocks.IRON_ORE, Blocks.GOLD_ORE, Blocks.DIAMOND_ORE,
			Blocks.BRICK, Blocks.ICE]:
		_pick_blocks[id] = true

	# Ore blocks yield their material item instead of the block itself. There is
	# no furnace in the game, so raw ore turns straight into ingots.
	_drop_map = {
		Blocks.COAL_ORE: COAL,
		Blocks.IRON_ORE: IRON_INGOT,
		Blocks.GOLD_ORE: GOLD_INGOT,
		Blocks.DIAMOND_ORE: DIAMOND,
	}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

static func is_item(id: int) -> bool:
	return id >= BASE and id < END


## True for any id an inventory slot may legally hold (block or item).
static func is_valid_id(id: int) -> bool:
	return (id > Blocks.AIR and id < Blocks.COUNT) or is_item(id)


static func kind_of(id: int) -> int:
	if not is_item(id):
		return Kind.MATERIAL
	return _kind[id - BASE]


## True for a tool or weapon, which is held one at a time rather than stacked.
## Deliberately NOT named is_tool: a class_name is a Script object, and
## Script.is_tool() already exists in the engine, so the built-in would shadow
## this static and fail with "expected 0 arguments".
static func is_gear(id: int) -> bool:
	match kind_of(id):
		Kind.PICKAXE, Kind.SWORD, Kind.BOW:
			return is_item(id)
		_:
			return false


static func tier_of(id: int) -> int:
	if not is_item(id):
		return Tier.NONE
	return _tier[id - BASE]


## Display name for any inventory id, block or item.
static func display_name_any(id: int) -> String:
	if is_item(id):
		return _display[id - BASE]
	if id >= 0 and id < Blocks.COUNT:
		return Blocks.display_name(id)
	return ""


# ---------------------------------------------------------------------------
# Gameplay tables
# ---------------------------------------------------------------------------

## What breaking `block_id` actually puts into the inventory. Ores yield their
## material item, every other block follows Blocks.drop_of().
static func drop_for(block_id: int) -> int:
	if _drop_map.has(block_id):
		return _drop_map[block_id]
	return Blocks.drop_of(block_id)


## Dig time divider when holding `item_id` and breaking `block_id`.
static func dig_multiplier(item_id: int, block_id: int) -> float:
	if kind_of(item_id) != Kind.PICKAXE:
		return 1.0
	if not _pick_blocks.has(block_id):
		return 1.0
	return _PICK_SPEED[tier_of(item_id)]


## Melee damage when striking with `item_id` (any id, block or item).
static func melee_damage(item_id: int) -> int:
	match kind_of(item_id):
		Kind.SWORD:
			return _SWORD_DAMAGE[tier_of(item_id)]
		Kind.PICKAXE:
			return _PICK_DAMAGE[tier_of(item_id)]
		_:
			return HAND_DAMAGE


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------

## Preview texture for any inventory id: blocks go through the atlas, items are
## painted here. Cached per (id, size).
static func preview_any(id: int, size: int = 48) -> Texture2D:
	if not is_item(id):
		return VoxelAtlas.block_preview(id, size)
	var key := id * 4096 + size
	if _icon_cache.has(key):
		return _icon_cache[key] as Texture2D
	var img := _icon_image(id)
	img.resize(maxi(size, 8), maxi(size, 8), Image.INTERPOLATE_NEAREST)
	var tex := ImageTexture.create_from_image(img)
	_icon_cache[key] = tex
	return tex


const _HANDLE := Color(0.42, 0.28, 0.13)
const _HANDLE_DARK := Color(0.30, 0.19, 0.09)
const _WOOD_HEAD := Color(0.62, 0.44, 0.22)
const _STONE_HEAD := Color(0.54, 0.55, 0.58)
const _IRON_HEAD := Color(0.85, 0.87, 0.90)
const _DIAMOND_HEAD := Color(0.42, 0.87, 0.89)
const _GUARD := Color(0.35, 0.24, 0.12)

const _PICK_ROWS: PackedStringArray = [
	"...hhhhhhhhh....",
	"..hhhhhhhhhhh...",
	"..hhh..s..hhhh..",
	"..hh...s....hh..",
	"..h....s.....h..",
	".......s.....h..",
	"......ss........",
	"......ss........",
	"......ss........",
	".....ss.........",
	".....ss.........",
	".....ss.........",
	"....ss..........",
	"....ss..........",
	"...ss...........",
	"................",
]

const _SWORD_ROWS: PackedStringArray = [
	"............bb..",
	"...........bbbb.",
	"..........bbbb..",
	".........bbbb...",
	"........bbbb....",
	".......bbbb.....",
	"......bbbb......",
	".....bbbb.......",
	"..g.bbbb........",
	"..ggbbb.........",
	"..ggg...........",
	".sggggg.........",
	".ss..gg.........",
	"sss.............",
	"ss..............",
	"................",
]

const _BOW_ROWS: PackedStringArray = [
	"......wwww......",
	"....ww....ww....",
	"...w........w...",
	"..w..........t..",
	"..w..........t..",
	".w...........t..",
	".w...........t..",
	".w...........t..",
	".w...........t..",
	".w...........t..",
	"..w..........t..",
	"..w..........t..",
	"...w........w...",
	"....ww....ww....",
	"......wwww......",
	"................",
]

const _ARROW_ROWS: PackedStringArray = [
	"............nnn.",
	"...........nnnn.",
	"..........snnn..",
	".........sss.n..",
	"........sss.....",
	".......sss......",
	"......sss.......",
	".....sss........",
	"....sss.........",
	"...sss..........",
	"..fss...........",
	".fff............",
	".ff.............",
	"ff..............",
	"................",
	"................",
]

const _STICK_ROWS: PackedStringArray = [
	"................",
	"...........ss...",
	"..........sss...",
	".........sss....",
	"........sss.....",
	".......sss......",
	"......sss.......",
	".....sss........",
	"....sss.........",
	"...sss..........",
	"...ss...........",
	"................",
	"................",
	"................",
	"................",
	"................",
]

const _LUMP_ROWS: PackedStringArray = [
	"................",
	"................",
	"................",
	".....aaaaa......",
	"...aabbbbbaa....",
	"..abbbbcbbbba...",
	".abbbbbbbbbbba..",
	".abbcbbbbbbbba..",
	".abbbbbbbcbbba..",
	"..abbbbbbbbba...",
	"...aabbbbbaa....",
	".....aaaaa......",
	"................",
	"................",
	"................",
	"................",
]

const _INGOT_ROWS: PackedStringArray = [
	"................",
	"................",
	"................",
	"................",
	"....aaaaaaaa....",
	"...abbbbbbbba...",
	"..abbbbbbbbbba..",
	".abbbbbbbbbbbba.",
	".aaaaaaaaaaaaaa.",
	".acccccccccccca.",
	"..accccccccccca.",
	"...aaaaaaaaaaa..",
	"................",
	"................",
	"................",
	"................",
]

const _GEM_ROWS: PackedStringArray = [
	"................",
	"................",
	"....aaaaaaaa....",
	"...abbcbbbbba...",
	"..abbbbbbbcbba..",
	".abcbbbbbbbbbba.",
	"..abbbbbbbbbba..",
	"...abbbbcbbba...",
	"....abbbbbba....",
	".....abbbba.....",
	"......abba......",
	".......aa.......",
	"................",
	"................",
	"................",
	"................",
]


static func _icon_image(id: int) -> Image:
	var img := Image.create_empty(16, 16, false, Image.FORMAT_RGBA8)
	img.fill(Color(0.0, 0.0, 0.0, 0.0))
	match id:
		STICK:
			_paint(img, _STICK_ROWS, {"s": _HANDLE})
		COAL:
			_paint(img, _LUMP_ROWS, {"a": Color(0.05, 0.05, 0.06),
					"b": Color(0.16, 0.16, 0.18), "c": Color(0.34, 0.34, 0.38)})
		IRON_INGOT:
			_paint(img, _INGOT_ROWS, {"a": Color(0.45, 0.47, 0.52),
					"b": Color(0.87, 0.89, 0.92), "c": Color(0.66, 0.68, 0.73)})
		GOLD_INGOT:
			_paint(img, _INGOT_ROWS, {"a": Color(0.55, 0.40, 0.08),
					"b": Color(0.98, 0.83, 0.28), "c": Color(0.80, 0.62, 0.14)})
		DIAMOND:
			_paint(img, _GEM_ROWS, {"a": Color(0.14, 0.42, 0.48),
					"b": Color(0.45, 0.88, 0.90), "c": Color(0.90, 1.0, 1.0)})
		WOOD_PICKAXE:
			_paint(img, _PICK_ROWS, {"h": _WOOD_HEAD, "s": _HANDLE})
		STONE_PICKAXE:
			_paint(img, _PICK_ROWS, {"h": _STONE_HEAD, "s": _HANDLE})
		IRON_PICKAXE:
			_paint(img, _PICK_ROWS, {"h": _IRON_HEAD, "s": _HANDLE})
		DIAMOND_PICKAXE:
			_paint(img, _PICK_ROWS, {"h": _DIAMOND_HEAD, "s": _HANDLE})
		WOOD_SWORD:
			_paint(img, _SWORD_ROWS, {"b": _WOOD_HEAD, "g": _GUARD, "s": _HANDLE_DARK})
		STONE_SWORD:
			_paint(img, _SWORD_ROWS, {"b": _STONE_HEAD, "g": _GUARD, "s": _HANDLE_DARK})
		IRON_SWORD:
			_paint(img, _SWORD_ROWS, {"b": _IRON_HEAD, "g": _GUARD, "s": _HANDLE_DARK})
		DIAMOND_SWORD:
			_paint(img, _SWORD_ROWS, {"b": _DIAMOND_HEAD, "g": _GUARD, "s": _HANDLE_DARK})
		BOW:
			_paint(img, _BOW_ROWS, {"w": _WOOD_HEAD, "t": Color(0.88, 0.88, 0.84)})
		ARROW:
			_paint(img, _ARROW_ROWS, {"n": _STONE_HEAD, "s": _HANDLE,
					"f": Color(0.90, 0.90, 0.86)})
		_:
			# Unknown item id: magenta checker so the mistake is visible in game.
			for y in 16:
				for x in 16:
					if ((x >> 2) + (y >> 2)) & 1:
						img.set_pixel(x, y, Color(0.9, 0.0, 0.9))
	return img


static func _paint(img: Image, rows: PackedStringArray, palette: Dictionary) -> void:
	for r in rows.size():
		var line: String = rows[r]
		for c in mini(line.length(), 16):
			var ch := line[c]
			if palette.has(ch):
				img.set_pixel(c, r, palette[ch])
