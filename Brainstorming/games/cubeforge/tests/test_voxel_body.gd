extends TestCase
## Box against voxel grid collision (src/player/voxel_body.gd).
##
## Every number checked here is a value the player script depends on, so the
## expectations are written out in full rather than as loose bounds: the feet
## land at `top_of_block + MARGIN` and nowhere else, the side of the box stops at
## `wall - radius - MARGIN`, and the head stops at `ceiling - height - MARGIN`.
##
## About the world argument: VoxelBody type hints it as VoxelWorld and GDScript
## enforces parameter types at call time, so a hand written stand in exposing
## get_block/is_solid/has_chunk_at is rejected outright. The suite therefore
## drives a genuine VoxelWorld, built with `new()` and never `setup()`: no atlas,
## no shader compilation, no terrain generator, no worker threads. Chunk storage
## is seeded directly, which is all the two accessors VoxelBody uses
## (`get_block` and `has_chunk_at`) ever read. A column with no chunk in that
## storage is exactly the unloaded case the collision code has to treat as
## solid, so the void at the edge of the loaded ring is testable too.

## Eye offset used by the player script, reused so head_in_liquid is exercised
## with the value it really sees.
const EYE_HEIGHT := 1.62


func suite_name() -> String:
	return "voxel_body"


# ---------------------------------------------------------------------------
# World fixtures
# ---------------------------------------------------------------------------

## A VoxelWorld holding empty chunks for the given keys and nothing else. Callers
## must free() the node: VoxelWorld is a Node3D, not reference counted.
func _make_world(chunk_keys: Array) -> VoxelWorld:
	var world := VoxelWorld.new()
	for key: Vector2i in chunk_keys:
		world._chunks[key] = ChunkData.new(key.x, key.y)
		world._states[key] = VoxelWorld.State.GENERATED
		world._versions[key] = 0
	return world


## The 3 by 3 ring of chunks around the origin, all air. Wide enough that no test
## accidentally leans on the unloaded-is-solid rule.
func _air_world() -> VoxelWorld:
	var keys: Array = []
	for cx in [-1, 0, 1]:
		for cz in [-1, 0, 1]:
			keys.append(Vector2i(cx, cz))
	return _make_world(keys)


## Writes straight into the chunk data rather than through set_block, which would
## drag the mesh scheduler in for no benefit here.
func _set_block(world: VoxelWorld, wx: int, wy: int, wz: int, id: int) -> void:
	var key := Vector2i(VoxelWorld.chunk_of(wx), VoxelWorld.chunk_of(wz))
	var data: ChunkData = world._chunks.get(key)
	if data == null:
		fail("aucun chunk charge pour la cellule (%d, %d, %d)" % [wx, wy, wz])
		return
	data.set_local(VoxelWorld.local_of(wx), wy, VoxelWorld.local_of(wz), id)


func _fill_box(
	world: VoxelWorld,
	x0: int, x1: int,
	y0: int, y1: int,
	z0: int, z1: int,
	id: int
) -> void:
	for wx in range(x0, x1 + 1):
		for wy in range(y0, y1 + 1):
			for wz in range(z0, z1 + 1):
				_set_block(world, wx, wy, wz, id)


# ---------------------------------------------------------------------------
# Vertical resolution
# ---------------------------------------------------------------------------

func test_falling_stops_on_top_of_the_floor() -> void:
	var world := _air_world()
	# Floor cells 8..10, so the walkable surface is the plane y = 11.
	_fill_box(world, 6, 11, 8, 10, 6, 11, Blocks.STONE)

	var body := VoxelBody.new()
	var report := body.move(world, Vector3(8.5, 14.0, 8.5), Vector3(0.0, -4.0, 0.0))
	var pos: Vector3 = report["position"]

	check(report["on_floor"], "une chute bloquee doit lever on_floor")
	check(report["hit_y"], "une chute bloquee doit lever hit_y")
	check(not report["on_ceiling"], "tomber ne touche pas de plafond")
	check(not report["hit_x"], "aucune collision en X")
	check(not report["hit_z"], "aucune collision en Z")

	near(pos.y, 11.0 + VoxelBody.MARGIN, 1.0e-5, "les pieds se posent sur le dessus du bloc")
	check(pos.y >= 11.0, "les pieds ne penetrent jamais dans le bloc (obtenu %f)" % pos.y)
	between(pos.y - 11.0, 0.0, VoxelBody.MARGIN * 2.0,
		"les pieds restent dans la marge de separation au-dessus du bloc")
	near(pos.x, 8.5, 1.0e-6, "la chute ne deplace pas en X")
	near(pos.z, 8.5, 1.0e-6, "la chute ne deplace pas en Z")
	check(not body.overlaps_solid(world, pos), "la position d'arrivee est libre")

	world.free()
	done()


func test_a_long_fall_does_not_tunnel_through_a_thin_floor() -> void:
	var world := _air_world()
	# A single block thick floor, the worst case for tunnelling: nothing below it
	# stops the body except the y < 0 rule, so a tunnelled body lands near zero.
	_fill_box(world, 6, 11, 10, 10, 6, 11, Blocks.STONE)

	var body := VoxelBody.new()
	var report := body.move(world, Vector3(8.5, 30.0, 8.5), Vector3(0.0, -100.0, 0.0))
	var pos: Vector3 = report["position"]

	check(report["on_floor"], "un mouvement de 100 unites doit toujours detecter le sol")
	check(pos.y > 10.0,
		"le corps ne doit pas traverser un sol d'un bloc d'epaisseur (obtenu y = %f)" % pos.y)
	near(pos.y, 11.0 + VoxelBody.MARGIN, 1.0e-4, "le sous-pas ramene les pieds sur le sol")
	check(not body.overlaps_solid(world, pos), "la position d'arrivee est libre")

	world.free()
	done()


func test_jumping_into_a_ceiling_stops_under_it() -> void:
	var world := _air_world()
	_fill_box(world, 6, 11, 8, 10, 6, 11, Blocks.STONE)
	# Ceiling slab at y = 13, so its underside is the plane y = 13.
	_fill_box(world, 6, 11, 13, 13, 6, 11, Blocks.STONE)

	var body := VoxelBody.new()
	var report := body.move(world, Vector3(8.5, 11.0, 8.5), Vector3(0.0, 3.0, 0.0))
	var pos: Vector3 = report["position"]

	check(report["on_ceiling"], "un saut bloque doit lever on_ceiling")
	check(report["hit_y"], "un saut bloque doit lever hit_y")
	check(not report["on_floor"], "monter ne pose pas au sol")

	near(pos.y, 13.0 - body.height - VoxelBody.MARGIN, 1.0e-5,
		"la tete s'arrete sous la face inferieure du plafond")
	check(pos.y + body.height <= 13.0,
		"la tete ne traverse pas le plafond (sommet a %f)" % (pos.y + body.height))
	check(not body.overlaps_solid(world, pos), "la position d'arrivee est libre")

	world.free()
	done()


# ---------------------------------------------------------------------------
# Horizontal resolution
# ---------------------------------------------------------------------------

func test_walking_into_a_wall_stops_flush() -> void:
	var world := _air_world()
	_fill_box(world, 6, 11, 4, 4, 6, 11, Blocks.STONE)
	# Wall plane at x = 10, tall enough to cover the whole box (y 5.0 to 6.8).
	_fill_box(world, 10, 10, 5, 7, 6, 11, Blocks.STONE)

	var body := VoxelBody.new()
	var report := body.move(world, Vector3(9.0, 5.0, 8.5), Vector3(2.0, 0.0, 0.0))
	var pos: Vector3 = report["position"]

	check(report["hit_x"], "entrer dans un mur doit lever hit_x")
	check(not report["hit_y"], "aucune collision verticale")
	check(not report["hit_z"], "aucune collision en Z")
	check(not report["on_floor"], "un deplacement horizontal ne pose pas au sol")

	near(pos.x, 10.0 - body.radius - VoxelBody.MARGIN, 1.0e-5,
		"le flanc de la boite s'arrete contre la face du mur")
	check(pos.x + body.radius <= 10.0,
		"la boite ne mord pas dans la cellule du mur (bord a %f)" % (pos.x + body.radius))
	near(pos.y, 5.0, 1.0e-6, "Y inchange")
	near(pos.z, 8.5, 1.0e-6, "Z inchange")
	check(not body.overlaps_solid(world, pos), "la position d'arrivee est libre")

	world.free()
	done()


func test_diagonal_into_a_corner_stops_on_both_axes() -> void:
	var world := _air_world()
	_fill_box(world, 6, 11, 4, 4, 6, 11, Blocks.STONE)
	_fill_box(world, 10, 10, 5, 6, 6, 11, Blocks.STONE)
	_fill_box(world, 6, 11, 5, 6, 10, 10, Blocks.STONE)

	var body := VoxelBody.new()
	var report := body.move(world, Vector3(9.0, 5.0, 9.0), Vector3(2.0, 0.0, 2.0))
	var pos: Vector3 = report["position"]

	check(report["hit_x"], "le coin bloque l'axe X")
	check(report["hit_z"], "le coin bloque l'axe Z")
	check(not report["hit_y"], "le coin ne bloque pas l'axe Y")

	near(pos.x, 10.0 - body.radius - VoxelBody.MARGIN, 1.0e-5, "X colle au mur du coin")
	near(pos.z, 10.0 - body.radius - VoxelBody.MARGIN, 1.0e-5, "Z colle au mur du coin")
	check(pos.x + body.radius <= 10.0, "pas de debordement en X")
	check(pos.z + body.radius <= 10.0, "pas de debordement en Z")
	check(not body.overlaps_solid(world, pos), "la position d'arrivee est libre")

	world.free()
	done()


func test_a_box_flush_against_a_boundary_claims_no_cell() -> void:
	var world := _air_world()
	# Floor cells 4, walkable surface at y = 5. Wall plane at x = 10.
	_fill_box(world, 6, 11, 4, 4, 6, 11, Blocks.STONE)
	_fill_box(world, 10, 10, 5, 7, 6, 11, Blocks.STONE)

	var body := VoxelBody.new()

	# Feet exactly on the floor surface: the cell below must not count as an
	# overlap, or every standing frame would report a collision.
	check(not body.overlaps_solid(world, Vector3(8.5, 5.0, 8.5)),
		"des pieds pose a plat sur un bloc ne chevauchent pas ce bloc")

	# Side of the box exactly on the wall boundary (9.7 + 0.3 == 10.0).
	var flush := Vector3(10.0 - body.radius, 5.0, 8.5)
	check(not body.overlaps_solid(world, flush),
		"une boite affleurant la frontiere ne revendique pas la cellule d'en face")
	check(body.overlaps_solid(world, flush + Vector3(0.002, 0.0, 0.0)),
		"deux millimetres au-dela, le chevauchement est bien detecte")

	# Standing still against that wall must report nothing at all.
	var report := body.move(world, flush, Vector3.ZERO)
	var pos: Vector3 = report["position"]
	check(not report["hit_x"], "immobile contre un mur : pas de hit_x")
	check(not report["hit_y"], "immobile contre un mur : pas de hit_y")
	check(not report["hit_z"], "immobile contre un mur : pas de hit_z")
	check(not report["on_floor"], "immobile sans mouvement : pas de on_floor")
	check(not report["on_ceiling"], "immobile sans mouvement : pas de on_ceiling")
	eq(pos, flush, "un mouvement nul ne deplace pas la boite")

	world.free()
	done()


# ---------------------------------------------------------------------------
# World edges
# ---------------------------------------------------------------------------

func test_an_unloaded_chunk_blocks() -> void:
	var world := _make_world([Vector2i(0, 0)])
	check(world.has_chunk_at(8, 8), "le chunk d'origine est charge")
	check(not world.has_chunk_at(20, 8), "le chunk voisin ne l'est pas")

	var body := VoxelBody.new()
	var feet := Vector3(20.5, 30.0, 8.5)
	check(body.overlaps_solid(world, feet), "une colonne sans chunk est traitee comme solide")

	var report := body.move(world, feet, Vector3(0.0, -3.0, 0.0))
	var pos: Vector3 = report["position"]
	check(report["on_floor"], "au-dessus d'une colonne non chargee, le corps est pose")
	eq(pos, feet, "le corps ne tombe pas dans le vide du bord du monde charge")

	world.free()
	done()


func test_below_zero_blocks_and_the_sky_does_not() -> void:
	var world := _air_world()
	var body := VoxelBody.new()

	# Nothing is solid anywhere, so only the y < 0 rule can stop this fall, and
	# it must stop it right on the plane y = 0.
	var down := body.move(world, Vector3(8.5, 1.0, 8.5), Vector3(0.0, -3.0, 0.0))
	var low: Vector3 = down["position"]
	check(down["on_floor"], "le plancher du monde bloque la chute")
	near(low.y, VoxelBody.MARGIN, 1.0e-5, "les pieds s'arretent sur le plan y = 0")
	check(low.y >= 0.0, "les pieds ne passent pas sous y = 0 (obtenu %f)" % low.y)

	# The roof is open sky: a body may leave the world upward without hitting
	# anything, otherwise a creative flight would stop dead at y = 96.
	var start := float(VoxelWorld.WORLD_HEIGHT) - 1.5
	var up := body.move(world, Vector3(8.5, start, 8.5), Vector3(0.0, 3.0, 0.0))
	var high: Vector3 = up["position"]
	check(not up["on_ceiling"], "au-dessus du monde, rien ne fait plafond")
	check(not up["hit_y"], "au-dessus du monde, aucune collision verticale")
	near(high.y, start + 3.0, 1.0e-4, "le mouvement vers le ciel est integralement applique")
	check(high.y > float(VoxelWorld.WORLD_HEIGHT),
		"le corps depasse le toit du monde (obtenu %f)" % high.y)

	world.free()
	done()


# ---------------------------------------------------------------------------
# Liquids
# ---------------------------------------------------------------------------

func test_submersion_scales_with_coverage() -> void:
	var world := _air_world()
	var body := VoxelBody.new()

	near(body.submersion(world, Vector3(8.5, 10.0, 8.5)), 0.0, 1.0e-6,
		"immersion nulle a l'air libre")

	# The box footprint (8.2 to 8.8 on both axes) sits inside the single cell
	# column x = 8, z = 8, so filling the two cells it spans covers it entirely.
	_set_block(world, 8, 10, 8, Blocks.WATER)
	_set_block(world, 8, 11, 8, Blocks.WATER)
	near(body.submersion(world, Vector3(8.5, 10.0, 8.5)), 1.0, 1.0e-6,
		"immersion totale sous l'eau")

	# Feet at 10.1 with water only in the cell 10: exactly 0.9 of the 1.8 unit
	# box is covered.
	_set_block(world, 8, 11, 8, Blocks.AIR)
	var half := body.submersion(world, Vector3(8.5, 10.1, 8.5))
	near(half, 0.5, 1.0e-6, "immersion a mi-corps")
	check(half > 0.0 and half < 1.0, "une immersion partielle est strictement entre 0 et 1")

	# Water never collides, so it must not stop a fall through it.
	var report := body.move(world, Vector3(8.5, 10.1, 8.5), Vector3(0.0, -3.0, 0.0))
	check(not report["on_floor"], "l'eau n'arrete pas la chute")

	world.free()
	done()


func test_head_in_liquid_reads_the_eye_cell() -> void:
	var world := _air_world()
	var body := VoxelBody.new()
	# One layer of water, cell y = 10.
	_fill_box(world, 6, 11, 10, 10, 6, 11, Blocks.WATER)

	# Feet inside the water, eyes at 11.62 above it: the head is dry.
	var wet_feet := Vector3(8.5, 10.0, 8.5)
	check(body.submersion(world, wet_feet) > 0.0, "les pieds sont bien dans le liquide")
	check(not body.head_in_liquid(world, wet_feet, EYE_HEIGHT),
		"des pieds mouilles ne suffisent pas a immerger la tete")

	# Feet in the air below the water, eyes at 10.62 inside it: the head is wet.
	var wet_head := Vector3(8.5, 9.0, 8.5)
	eq(world.get_block(8, 9, 8), Blocks.AIR, "la cellule des pieds est bien de l'air")
	check(body.head_in_liquid(world, wet_head, EYE_HEIGHT),
		"head_in_liquid suit la cellule des yeux, pas celle des pieds")

	# Raising the water to the eye cell wets the first case too.
	_set_block(world, 8, 11, 8, Blocks.WATER)
	check(body.head_in_liquid(world, wet_feet, EYE_HEIGHT),
		"de l'eau dans la cellule des yeux immerge la tete")

	# Degenerate columns answer false rather than reading garbage.
	check(not body.head_in_liquid(world, Vector3(40.5, 10.0, 8.5), EYE_HEIGHT),
		"une colonne non chargee ne noie pas la tete")
	check(not body.head_in_liquid(world, Vector3(8.5, float(VoxelWorld.WORLD_HEIGHT) - 1.0, 8.5), EYE_HEIGHT),
		"des yeux au-dessus du monde ne sont pas dans un liquide")

	world.free()
	done()


func test_realistic_step_climbs_one_block_but_not_two() -> void:
	var world := _air_world()
	_fill_box(world, 5, 13, 10, 10, 6, 10, Blocks.STONE)
	_fill_box(world, 9, 13, 11, 11, 6, 10, Blocks.STONE)

	var body := VoxelBody.new()
	var feet := Vector3(8.4, 11.001, 8.5)
	var classic := body.move(world, feet, Vector3(1.2, -0.02, 0.0))
	var stepped := body.move_with_step(world, feet, Vector3(1.2, -0.02, 0.0), 1.001)
	check(classic["hit_x"], "la marche d'un bloc bloque le mouvement classique")
	check(stepped["stepped"], "le deplacement realiste franchit une marche d'un bloc")
	check(stepped["position"].x > classic["position"].x + 0.5,
		"le pas assiste progresse reellement au-dela de l'obstacle")
	near(stepped["position"].y, 12.001, 0.002,
		"le joueur se pose exactement sur le bloc superieur")

	_fill_box(world, 9, 13, 12, 12, 6, 10, Blocks.STONE)
	var wall := body.move_with_step(world, feet, Vector3(1.2, -0.02, 0.0), 1.001)
	check(not wall["stepped"], "un mur de deux blocs reste infranchissable")
	check(wall["position"].x < 8.71, "le mur haut conserve la collision laterale")

	world.free()
	done()
