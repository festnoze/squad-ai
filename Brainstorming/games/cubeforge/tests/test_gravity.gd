extends TestCase
## Pure helpers of the gravity manager (src/entities/gravity_manager.gd).
##
## Only the static, world-free functions are exercised here: the block filter
## and the vertical rest-cell scan, driven by a Callable getter backed by a
## Dictionary. The animated fall itself needs a live scene tree and a real
## VoxelWorld, which the smoke harness covers instead.
##
## The script is loaded through preload rather than the global class name so
## the suite never depends on the editor's class cache being fresh.

const GravityScript := preload("res://src/entities/gravity_manager.gd")


func suite_name() -> String:
	return "gravity"


## Getter over a sparse column: every cell absent from `cells` is air.
func _getter(cells: Dictionary) -> Callable:
	return func(wx: int, wy: int, wz: int) -> int:
		return int(cells.get(Vector3i(wx, wy, wz), Blocks.AIR))


func test_is_gravity_block() -> void:
	check(GravityScript.is_gravity_block(Blocks.SAND), "le sable doit subir la gravite")
	check(GravityScript.is_gravity_block(Blocks.GRAVEL), "le gravier doit subir la gravite")
	check(not GravityScript.is_gravity_block(Blocks.AIR), "l'air ne subit pas la gravite")
	check(not GravityScript.is_gravity_block(Blocks.STONE), "la pierre ne subit pas la gravite")
	check(not GravityScript.is_gravity_block(Blocks.DIRT), "la terre ne subit pas la gravite")
	check(not GravityScript.is_gravity_block(Blocks.WATER), "l'eau ne subit pas la gravite")
	check(not GravityScript.is_gravity_block(Blocks.GRASS_TUFT), "une plante ne subit pas la gravite")
	done()


func test_rest_on_first_collider() -> void:
	var cells := {Vector3i(2, 10, 3): Blocks.STONE}
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(2, 20, 3), _getter(cells))
	eq(rest, Vector3i(2, 11, 3), "le bloc doit se poser juste au dessus de la pierre")
	done()


func test_falls_through_liquids_and_plants() -> void:
	var cells := {
		Vector3i(0, 15, 0): Blocks.WATER,
		Vector3i(0, 12, 0): Blocks.GRASS_TUFT,
		Vector3i(0, 10, 0): Blocks.STONE,
	}
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(0, 20, 0), _getter(cells))
	eq(rest, Vector3i(0, 11, 0), "eau et plantes ne portent pas le bloc, il les traverse")
	done()


func test_cutout_and_translucent_support() -> void:
	var leaves := {Vector3i(4, 20, 4): Blocks.OAK_LEAVES}
	var on_leaves: Vector3i = GravityScript.scan_rest_cell(Vector3i(4, 30, 4), _getter(leaves))
	eq(on_leaves, Vector3i(4, 21, 4), "les feuilles collisionnent donc elles portent le bloc")
	var ice := {Vector3i(4, 20, 4): Blocks.ICE}
	var on_ice: Vector3i = GravityScript.scan_rest_cell(Vector3i(4, 30, 4), _getter(ice))
	eq(on_ice, Vector3i(4, 21, 4), "la glace collisionne donc elle porte le bloc")
	done()


func test_already_resting_returns_start() -> void:
	var cells := {Vector3i(5, 10, 5): Blocks.STONE}
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(5, 11, 5), _getter(cells))
	eq(rest, Vector3i(5, 11, 5), "un bloc deja soutenu ne bouge pas")
	done()


func test_empty_column_rests_at_zero() -> void:
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(-3, 40, 7), _getter({}))
	eq(rest, Vector3i(-3, 0, 7), "sans aucun collisionneur la descente s'arrete a y 0")
	done()


func test_bedrock_carries_at_one() -> void:
	var cells := {Vector3i(1, 0, 1): Blocks.BEDROCK}
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(1, 30, 1), _getter(cells))
	eq(rest, Vector3i(1, 1, 1), "la roche-mere a y 0 porte le bloc a y 1")
	done()


func test_start_at_zero_stays() -> void:
	var rest: Vector3i = GravityScript.scan_rest_cell(Vector3i(8, 0, 8), _getter({}))
	eq(rest, Vector3i(8, 0, 8), "un bloc deja a y 0 ne descend pas plus bas")
	done()
