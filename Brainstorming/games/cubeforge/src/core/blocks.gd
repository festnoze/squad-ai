class_name Blocks
## Central block registry for CUBEFORGE.
##
## Block ids are single bytes (0-255) stored inside chunk voxel arrays, so every
## per-block property lives in a flat Packed*Array indexed by id. The mesher
## touches these tables tens of thousands of times per chunk and cannot afford
## dictionary lookups.
##
## Cube face order is fixed everywhere in the project: +X, -X, +Y, -Y, +Z, -Z.

## How a block is shaped and drawn.
enum Kind {
	EMPTY,        ## Air. No geometry, no collision.
	SOLID,        ## Full opaque cube. Hides the faces of neighbours.
	CUTOUT,       ## Full cube, alpha-scissor texture (leaves, glass). Collides.
	CROSS,        ## Two diagonal quads (plants, torch). No collision.
	TRANSLUCENT,  ## Full cube, alpha-blended (ice). Collides.
	LIQUID,       ## Full cube, alpha-blended, animated. No collision.
}

## Draw surfaces. Every chunk mesh carries one ArrayMesh surface per entry,
## each with its own material. Empty surfaces are skipped at upload time.
enum Surface {
	OPAQUE,
	CUTOUT,
	TRANSLUCENT,
	WATER,
}

const SURFACE_COUNT := 4

const FACE_PX := 0
const FACE_NX := 1
const FACE_PY := 2
const FACE_NY := 3
const FACE_PZ := 4
const FACE_NZ := 5
const FACE_COUNT := 6

## Bit per face, used by the tint mask.
const BIT_PX := 1
const BIT_NX := 2
const BIT_PY := 4
const BIT_NY := 8
const BIT_PZ := 16
const BIT_NZ := 32
const BITS_ALL := 63
const BITS_SIDES := BIT_PX | BIT_NX | BIT_PZ | BIT_NZ

# ---------------------------------------------------------------------------
# Block ids
# ---------------------------------------------------------------------------

enum {
	AIR = 0,
	STONE,
	GRASS,
	DIRT,
	COBBLESTONE,
	STONE_BRICK,
	GRANITE,
	MARBLE,
	MOSSY_COBBLE,
	SAND,
	SANDSTONE,
	GRAVEL,
	CLAY,
	SNOW_BLOCK,
	ICE,
	OBSIDIAN,
	BEDROCK,
	COAL_ORE,
	IRON_ORE,
	GOLD_ORE,
	DIAMOND_ORE,
	OAK_LOG,
	OAK_PLANKS,
	OAK_LEAVES,
	BIRCH_LOG,
	BIRCH_PLANKS,
	BIRCH_LEAVES,
	PINE_LEAVES,
	BOOKSHELF,
	CACTUS,
	PUMPKIN,
	BRICK,
	GLASS,
	LAMP,
	WOOL_WHITE,
	WOOL_RED,
	WOOL_YELLOW,
	WOOL_GREEN,
	WOOL_BLUE,
	WATER,
	GRASS_TUFT,
	FERN,
	DEAD_BUSH,
	FLOWER_RED,
	FLOWER_YELLOW,
	SAPLING,
	TORCH,
	COUNT,
}

# ---------------------------------------------------------------------------
# Texture tiles
# ---------------------------------------------------------------------------

## Layer order of the Texture2DArray produced by VoxelAtlas.build().
## Never reorder: the mesher writes these indices straight into vertex data.
const TILE_NAMES: PackedStringArray = [
	"stone",            # 0
	"grass_top",        # 1
	"grass_side",       # 2
	"dirt",             # 3
	"cobblestone",      # 4
	"stone_brick",      # 5
	"granite",          # 6
	"marble",           # 7
	"mossy_cobble",     # 8
	"sand",             # 9
	"sandstone_top",    # 10
	"sandstone_side",   # 11
	"gravel",           # 12
	"clay",             # 13
	"snow",             # 14
	"snow_side",        # 15
	"ice",              # 16
	"obsidian",         # 17
	"bedrock",          # 18
	"coal_ore",         # 19
	"iron_ore",         # 20
	"gold_ore",         # 21
	"diamond_ore",      # 22
	"oak_log_side",     # 23
	"oak_log_top",      # 24
	"oak_planks",       # 25
	"oak_leaves",       # 26
	"birch_log_side",   # 27
	"birch_log_top",    # 28
	"birch_planks",     # 29
	"birch_leaves",     # 30
	"pine_leaves",      # 31
	"bookshelf",        # 32
	"cactus_side",      # 33
	"cactus_top",       # 34
	"pumpkin_side",     # 35
	"pumpkin_top",      # 36
	"brick",            # 37
	"glass",            # 38
	"lamp",             # 39
	"wool_white",       # 40
	"wool_red",         # 41
	"wool_yellow",      # 42
	"wool_green",       # 43
	"wool_blue",        # 44
	"water",            # 45
	"grass_tuft",       # 46
	"fern",             # 47
	"dead_bush",        # 48
	"flower_red",       # 49
	"flower_yellow",    # 50
	"sapling",          # 51
	"torch",            # 52
]

const TILE_COUNT := 53

## Edge length in pixels of one atlas tile.
const TILE_PIXELS := 32

# ---------------------------------------------------------------------------
# Declarative table
# ---------------------------------------------------------------------------

## One entry per block id, in id order. Keys:
##   id        block constant (asserted against position, guards typos)
##   name      display name shown in the HUD and inventory
##   kind      Kind value
##   top/bot   tile name for +Y / -Y, default = side
##   side      tile name for the four vertical faces
##   hard      seconds to break by hand, -1.0 for unbreakable
##   emit      emission strength 0.0-1.0
##   drop      block id produced when broken, defaults to itself
##   tint      face bitmask receiving the biome tint, defaults to 0
const _TABLE: Array[Dictionary] = [
	{"id": AIR, "name": "Air", "kind": Kind.EMPTY, "side": "stone", "hard": -1.0},

	{"id": STONE, "name": "Pierre", "kind": Kind.SOLID, "side": "stone", "hard": 1.5, "drop": COBBLESTONE},
	{"id": GRASS, "name": "Bloc d'herbe", "kind": Kind.SOLID, "side": "grass_side", "top": "grass_top", "bot": "dirt", "hard": 0.6, "tint": BIT_PY},
	{"id": DIRT, "name": "Terre", "kind": Kind.SOLID, "side": "dirt", "hard": 0.5},
	{"id": COBBLESTONE, "name": "Pierre taillée", "kind": Kind.SOLID, "side": "cobblestone", "hard": 1.7},
	{"id": STONE_BRICK, "name": "Briques de pierre", "kind": Kind.SOLID, "side": "stone_brick", "hard": 1.7},
	{"id": GRANITE, "name": "Granite", "kind": Kind.SOLID, "side": "granite", "hard": 1.6},
	{"id": MARBLE, "name": "Marbre", "kind": Kind.SOLID, "side": "marble", "hard": 1.6},
	{"id": MOSSY_COBBLE, "name": "Pierre moussue", "kind": Kind.SOLID, "side": "mossy_cobble", "hard": 1.7},
	{"id": SAND, "name": "Sable", "kind": Kind.SOLID, "side": "sand", "hard": 0.5},
	{"id": SANDSTONE, "name": "Grès", "kind": Kind.SOLID, "side": "sandstone_side", "top": "sandstone_top", "bot": "sandstone_top", "hard": 1.2},
	{"id": GRAVEL, "name": "Gravier", "kind": Kind.SOLID, "side": "gravel", "hard": 0.6},
	{"id": CLAY, "name": "Argile", "kind": Kind.SOLID, "side": "clay", "hard": 0.6},
	{"id": SNOW_BLOCK, "name": "Bloc de neige", "kind": Kind.SOLID, "side": "snow_side", "top": "snow", "bot": "dirt", "hard": 0.4},
	{"id": ICE, "name": "Glace", "kind": Kind.TRANSLUCENT, "side": "ice", "hard": 0.6},
	{"id": OBSIDIAN, "name": "Obsidienne", "kind": Kind.SOLID, "side": "obsidian", "hard": 8.0},
	{"id": BEDROCK, "name": "Roche-mère", "kind": Kind.SOLID, "side": "bedrock", "hard": -1.0},

	{"id": COAL_ORE, "name": "Minerai de charbon", "kind": Kind.SOLID, "side": "coal_ore", "hard": 2.5},
	{"id": IRON_ORE, "name": "Minerai de fer", "kind": Kind.SOLID, "side": "iron_ore", "hard": 3.0},
	{"id": GOLD_ORE, "name": "Minerai d'or", "kind": Kind.SOLID, "side": "gold_ore", "hard": 3.0},
	{"id": DIAMOND_ORE, "name": "Minerai de diamant", "kind": Kind.SOLID, "side": "diamond_ore", "hard": 3.5},

	{"id": OAK_LOG, "name": "Rondin de chêne", "kind": Kind.SOLID, "side": "oak_log_side", "top": "oak_log_top", "bot": "oak_log_top", "hard": 1.2},
	{"id": OAK_PLANKS, "name": "Planches de chêne", "kind": Kind.SOLID, "side": "oak_planks", "hard": 1.0},
	{"id": OAK_LEAVES, "name": "Feuilles de chêne", "kind": Kind.CUTOUT, "side": "oak_leaves", "hard": 0.2, "tint": BITS_ALL},
	{"id": BIRCH_LOG, "name": "Rondin de bouleau", "kind": Kind.SOLID, "side": "birch_log_side", "top": "birch_log_top", "bot": "birch_log_top", "hard": 1.2},
	{"id": BIRCH_PLANKS, "name": "Planches de bouleau", "kind": Kind.SOLID, "side": "birch_planks", "hard": 1.0},
	{"id": BIRCH_LEAVES, "name": "Feuilles de bouleau", "kind": Kind.CUTOUT, "side": "birch_leaves", "hard": 0.2, "tint": BITS_ALL},
	{"id": PINE_LEAVES, "name": "Aiguilles de pin", "kind": Kind.CUTOUT, "side": "pine_leaves", "hard": 0.2},
	{"id": BOOKSHELF, "name": "Bibliothèque", "kind": Kind.SOLID, "side": "bookshelf", "top": "oak_planks", "bot": "oak_planks", "hard": 1.4},
	{"id": CACTUS, "name": "Cactus", "kind": Kind.SOLID, "side": "cactus_side", "top": "cactus_top", "bot": "cactus_top", "hard": 0.5},
	{"id": PUMPKIN, "name": "Citrouille", "kind": Kind.SOLID, "side": "pumpkin_side", "top": "pumpkin_top", "bot": "pumpkin_top", "hard": 0.9},
	{"id": BRICK, "name": "Briques", "kind": Kind.SOLID, "side": "brick", "hard": 1.7},
	{"id": GLASS, "name": "Verre", "kind": Kind.CUTOUT, "side": "glass", "hard": 0.3},
	{"id": LAMP, "name": "Lampe", "kind": Kind.SOLID, "side": "lamp", "hard": 0.5, "emit": 1.0},

	{"id": WOOL_WHITE, "name": "Laine blanche", "kind": Kind.SOLID, "side": "wool_white", "hard": 0.7},
	{"id": WOOL_RED, "name": "Laine rouge", "kind": Kind.SOLID, "side": "wool_red", "hard": 0.7},
	{"id": WOOL_YELLOW, "name": "Laine jaune", "kind": Kind.SOLID, "side": "wool_yellow", "hard": 0.7},
	{"id": WOOL_GREEN, "name": "Laine verte", "kind": Kind.SOLID, "side": "wool_green", "hard": 0.7},
	{"id": WOOL_BLUE, "name": "Laine bleue", "kind": Kind.SOLID, "side": "wool_blue", "hard": 0.7},

	{"id": WATER, "name": "Eau", "kind": Kind.LIQUID, "side": "water", "hard": -1.0},

	{"id": GRASS_TUFT, "name": "Touffe d'herbe", "kind": Kind.CROSS, "side": "grass_tuft", "hard": 0.05, "tint": BITS_ALL},
	{"id": FERN, "name": "Fougère", "kind": Kind.CROSS, "side": "fern", "hard": 0.05, "tint": BITS_ALL},
	{"id": DEAD_BUSH, "name": "Buisson mort", "kind": Kind.CROSS, "side": "dead_bush", "hard": 0.05},
	{"id": FLOWER_RED, "name": "Coquelicot", "kind": Kind.CROSS, "side": "flower_red", "hard": 0.05},
	{"id": FLOWER_YELLOW, "name": "Pissenlit", "kind": Kind.CROSS, "side": "flower_yellow", "hard": 0.05},
	{"id": SAPLING, "name": "Pousse d'arbre", "kind": Kind.CROSS, "side": "sapling", "hard": 0.05, "tint": BITS_ALL},
	{"id": TORCH, "name": "Torche", "kind": Kind.CROSS, "side": "torch", "hard": 0.05, "emit": 0.9},
]

## Order of the creative block palette, page by page of nine.
const PALETTE: PackedByteArray = [
	GRASS, DIRT, STONE, COBBLESTONE, STONE_BRICK, SAND, SANDSTONE, GRAVEL, CLAY,
	GRANITE, MARBLE, MOSSY_COBBLE, BRICK, OBSIDIAN, SNOW_BLOCK, ICE, GLASS, LAMP,
	OAK_LOG, OAK_PLANKS, OAK_LEAVES, BIRCH_LOG, BIRCH_PLANKS, BIRCH_LEAVES, PINE_LEAVES, BOOKSHELF, CACTUS,
	PUMPKIN, WOOL_WHITE, WOOL_RED, WOOL_YELLOW, WOOL_GREEN, WOOL_BLUE, COAL_ORE, IRON_ORE, GOLD_ORE,
	DIAMOND_ORE, TORCH, GRASS_TUFT, FERN, FLOWER_RED, FLOWER_YELLOW, DEAD_BUSH, SAPLING, WATER,
]

# ---------------------------------------------------------------------------
# Flat lookup tables
# ---------------------------------------------------------------------------

static var _kind: PackedByteArray
static var _surface: PackedByteArray
static var _tile: PackedInt32Array      ## COUNT * FACE_COUNT entries
static var _tint_mask: PackedInt32Array
static var _opaque: PackedByteArray     ## hides neighbouring faces
static var _collides: PackedByteArray
static var _merges: PackedByteArray     ## no face drawn between two of the same id
static var _emission: PackedFloat32Array
static var _hardness: PackedFloat32Array
static var _drop: PackedByteArray
static var _display: PackedStringArray
static var _tile_index: Dictionary      ## tile name -> layer

static func _static_init() -> void:
	_tile_index = {}
	for i in TILE_NAMES.size():
		_tile_index[TILE_NAMES[i]] = i

	_kind = PackedByteArray()
	_kind.resize(COUNT)
	_surface = PackedByteArray()
	_surface.resize(COUNT)
	_tile = PackedInt32Array()
	_tile.resize(COUNT * FACE_COUNT)
	_tint_mask = PackedInt32Array()
	_tint_mask.resize(COUNT)
	_opaque = PackedByteArray()
	_opaque.resize(COUNT)
	_collides = PackedByteArray()
	_collides.resize(COUNT)
	_merges = PackedByteArray()
	_merges.resize(COUNT)
	_emission = PackedFloat32Array()
	_emission.resize(COUNT)
	_hardness = PackedFloat32Array()
	_hardness.resize(COUNT)
	_drop = PackedByteArray()
	_drop.resize(COUNT)
	_display = PackedStringArray()
	_display.resize(COUNT)

	assert(_TABLE.size() == COUNT, "Blocks._TABLE must hold exactly one entry per id")

	for pos in _TABLE.size():
		var d: Dictionary = _TABLE[pos]
		var id: int = d["id"]
		assert(id == pos, "Blocks._TABLE entry %d is out of order (id %d)" % [pos, id])

		var kind: Kind = d["kind"]
		var side: String = d["side"]
		var top: String = d.get("top", side)
		var bot: String = d.get("bot", side)

		_kind[id] = kind
		_surface[id] = _surface_for_kind(kind)
		_tint_mask[id] = d.get("tint", 0)
		_opaque[id] = 1 if kind == Kind.SOLID else 0
		_collides[id] = 1 if kind in [Kind.SOLID, Kind.CUTOUT, Kind.TRANSLUCENT] else 0
		# Any non-opaque cube hides the shared face against an identical
		# neighbour, which removes the interior of leaf clusters and lakes.
		_merges[id] = 1 if kind in [Kind.CUTOUT, Kind.TRANSLUCENT, Kind.LIQUID] else 0
		_emission[id] = d.get("emit", 0.0)
		_hardness[id] = d["hard"]
		_drop[id] = d.get("drop", id)
		_display[id] = d["name"]

		var base := id * FACE_COUNT
		_tile[base + FACE_PX] = _layer(side)
		_tile[base + FACE_NX] = _layer(side)
		_tile[base + FACE_PY] = _layer(top)
		_tile[base + FACE_NY] = _layer(bot)
		_tile[base + FACE_PZ] = _layer(side)
		_tile[base + FACE_NZ] = _layer(side)

static func _layer(tile_name: String) -> int:
	assert(_tile_index.has(tile_name), "Unknown atlas tile '%s'" % tile_name)
	return _tile_index[tile_name]

static func _surface_for_kind(kind: Kind) -> int:
	match kind:
		Kind.SOLID:
			return Surface.OPAQUE
		Kind.CUTOUT, Kind.CROSS:
			return Surface.CUTOUT
		Kind.TRANSLUCENT:
			return Surface.TRANSLUCENT
		Kind.LIQUID:
			return Surface.WATER
		_:
			return Surface.OPAQUE

# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

static func kind_of(id: int) -> int:
	return _kind[id]

static func surface_of(id: int) -> int:
	return _surface[id]

## Atlas layer for one face of one block.
static func tile_of(id: int, face: int) -> int:
	return _tile[id * FACE_COUNT + face]

static func tint_mask(id: int) -> int:
	return _tint_mask[id]

static func is_air(id: int) -> bool:
	return id == AIR

## True when the block completely hides the faces of its neighbours.
static func is_opaque(id: int) -> bool:
	return _opaque[id] == 1

## True when a character collides with the block.
static func collides(id: int) -> bool:
	return _collides[id] == 1

static func is_liquid(id: int) -> bool:
	return _kind[id] == Kind.LIQUID

static func is_cross(id: int) -> bool:
	return _kind[id] == Kind.CROSS

static func emission(id: int) -> float:
	return _emission[id]

static func is_light_source(id: int) -> bool:
	return _emission[id] > 0.01

## Seconds needed to break the block by hand. Negative means unbreakable.
static func hardness(id: int) -> float:
	return _hardness[id]

static func is_breakable(id: int) -> bool:
	return id != AIR and _hardness[id] >= 0.0

static func drop_of(id: int) -> int:
	return _drop[id]

static func display_name(id: int) -> String:
	return _display[id]

## True when a block can be placed into the cell currently holding `id`.
static func is_replaceable(id: int) -> bool:
	return id == AIR or _kind[id] == Kind.LIQUID or _kind[id] == Kind.CROSS

## Cross blocks need something solid underneath to survive.
static func needs_support(id: int) -> bool:
	return _kind[id] == Kind.CROSS

## Face visibility test used by the mesher. `self_id` is the block owning the
## face, `neighbour_id` the block the face points at.
static func draws_face(self_id: int, neighbour_id: int) -> bool:
	if neighbour_id == AIR:
		return true
	if _opaque[neighbour_id] == 1:
		return false
	if neighbour_id == self_id and _merges[self_id] == 1:
		return false
	return true
