extends Node
## Integration smoke test, run inside the real game.
##
##   godot --headless --path . -- --smoke
##
## main.gd adds this node to the live scene tree when it sees the --smoke user
## argument, then this probe waits for the world to settle and asserts that the
## subsystems really talk to each other. It exits 0 when every check holds.
##
## It deliberately runs inside the normal boot path rather than under a custom
## SceneTree via --script. Godot only registers the project autoloads as global
## identifiers for the default main loop, so a --script harness cannot even
## compile a file that mentions Game, and half the project mentions Game.

## Give up rather than hang forever if the world never finishes loading.
const TIMEOUT_SECONDS := 150.0

## Keep ticking a little after the world settles so the player has time to fall
## onto the ground and come to rest before the position is judged.
const SETTLE_EXTRA_FRAMES := 120

var _main: Node = null
var _frames := 0
var _start_msec := 0
var _settled_at := -1
var _loaded_signal_seen := false
var _failures: PackedStringArray = PackedStringArray()
var _checks := 0
var _reported := false


func setup(main_node: Node) -> void:
	_main = main_node
	_start_msec = Time.get_ticks_msec()
	var world: VoxelWorld = _main.get_node_or_null("World")
	if world != null:
		world.initial_load_finished.connect(func() -> void: _loaded_signal_seen = true)


func _process(_delta: float) -> void:
	if _reported or _main == null:
		return
	_frames += 1

	var elapsed: float = float(Time.get_ticks_msec() - _start_msec) / 1000.0
	var world: VoxelWorld = _main.get_node_or_null("World")
	var settled: bool = world != null and _loaded_signal_seen and world.pending_jobs() == 0

	if settled and _settled_at < 0:
		_settled_at = _frames

	var long_enough: bool = _settled_at >= 0 and _frames - _settled_at >= SETTLE_EXTRA_FRAMES
	if long_enough or elapsed > TIMEOUT_SECONDS:
		_reported = true
		_run_assertions(elapsed)
		_report()


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

func _check(condition: bool, message: String) -> void:
	_checks += 1
	if not condition:
		_failures.append(message)


func _run_assertions(elapsed: float) -> void:
	print("")
	print("=== CUBEFORGE smoke ===")
	print("  %d images en %.1f s" % [_frames, elapsed])

	var world: VoxelWorld = _main.get_node_or_null("World")
	var player: Player = _main.get_node_or_null("Player")
	var interaction: Interaction = _main.get_node_or_null("Interaction")
	var settlements: SettlementManager = _main.get_node_or_null("Settlements")
	var sky: SkyController = _main.get_node_or_null("Sky")
	var hud: Hud = _main.get_node_or_null("Hud")
	var pause_menu: PauseMenu = _main.get_node_or_null("Screens/PauseMenu")

	_check(world != null, "le noeud World doit exister")
	_check(player != null, "le noeud Player doit exister")
	_check(interaction != null, "le noeud Interaction doit exister")
	_check(settlements != null, "le gestionnaire de villages doit exister")
	_check(sky != null, "le noeud Sky doit exister")
	_check(hud != null, "le noeud Hud doit exister")
	_check(pause_menu != null, "le menu de reglages doit exister")
	if world == null or player == null:
		return

	# --- streaming -----------------------------------------------------------
	_check(_loaded_signal_seen, "le monde doit emettre initial_load_finished")
	var loaded: int = world.loaded_chunk_count()
	print("  chunks charges : %d, taches restantes : %d" % [loaded, world.pending_jobs()])
	_check(loaded > 0, "au moins un chunk doit etre maille")

	# --- terrain plausibility ------------------------------------------------
	var spawn: Vector3 = world.spawn_point()
	print("  apparition : %s" % str(spawn))
	_check(is_finite(spawn.x) and is_finite(spawn.y) and is_finite(spawn.z),
		"le point d'apparition doit etre fini")
	_check(spawn.y > 0.0 and spawn.y < float(VoxelWorld.WORLD_HEIGHT),
		"le point d'apparition doit tenir dans la hauteur du monde")

	var sx: int = int(floor(spawn.x))
	var sz: int = int(floor(spawn.z))
	_check(world.has_chunk_at(sx, sz), "le chunk d'apparition doit etre charge")

	var ground: int = world.surface_height(sx, sz)
	print("  sol sous l'apparition : y = %d, biome : %s" % [ground, world.biome_name_at(sx, sz)])
	_check(ground > 0 and ground < VoxelWorld.WORLD_HEIGHT - 1,
		"la hauteur du sol doit etre plausible")
	_check(world.is_solid(sx, ground, sz), "le bloc de surface doit etre solide")
	# Head room at the spawn, not "air at a fixed offset above the ground": the
	# spawn column may sit under a canopy, and leaves are solid.
	_check(not world.is_solid(sx, int(floor(spawn.y)) + 1, sz),
		"le point d'apparition doit avoir de la place pour la tete")
	_check(world.get_block(sx, 0, sz) == Blocks.BEDROCK, "y = 0 doit etre de la roche-mere")

	# The vertical range must be respected at both ends rather than wrapping.
	_check(world.get_block(sx, -1, sz) == Blocks.AIR, "sous le monde doit renvoyer de l'air")
	_check(world.get_block(sx, VoxelWorld.WORLD_HEIGHT, sz) == Blocks.AIR,
		"au-dessus du monde doit renvoyer de l'air")

	# --- terrain variety and determinism -------------------------------------
	var heights := {}
	var biomes := {}
	for i in 96:
		var wx: int = i * 37 - 1700
		var wz: int = i * -53 + 1300
		heights[world.surface_height(wx, wz)] = true
		biomes[world.biome_name_at(wx, wz)] = true
	print("  %d hauteurs distinctes et %d biomes sur 96 sondes" % [heights.size(), biomes.size()])
	_check(heights.size() > 8, "le relief doit varier, pas etre un plateau")
	_check(biomes.size() > 2, "plusieurs biomes doivent exister")

	# --- settlements ---------------------------------------------------------
	var nearby_houses := 0
	var nearby_pens := 0
	var pcx := VoxelWorld.chunk_of(sx)
	var pcz := VoxelWorld.chunk_of(sz)
	for cx in range(pcx - 9, pcx + 10):
		for cz in range(pcz - 9, pcz + 10):
			if not world.has_chunk_at(cx * ChunkData.SIZE_X, cz * ChunkData.SIZE_Z):
				continue
			for house in world.houses_in_chunk(cx, cz):
				if Vector2(house.x - sx, house.z - sz).length() <= 150.0:
					nearby_houses += 1
			for pen in world.pens_in_chunk(cx, cz):
				if Vector2(pen.x - sx, pen.z - sz).length() <= 150.0:
					nearby_pens += 1
	var actor_count := settlements.get_child_count() if settlements != null else 0
	print("  maisons proches : %d, enclos : %d, habitants actifs : %d" % [
		nearby_houses, nearby_pens, actor_count])
	if nearby_houses > 0 or nearby_pens > 0:
		_check(actor_count == nearby_houses * 3 + nearby_pens * 4,
			"maisons et enclos doivent activer tous leurs habitants")

	# surface_height is queried for unloaded columns by the spawn logic and the
	# debug overlay, so it has to be a pure function and give the same answer on
	# every call.
	var repeat_ok := true
	for i in 40:
		var wx: int = i * 991 - 400
		var wz: int = i * -617 + 250
		if world.surface_height(wx, wz) != world.surface_height(wx, wz):
			repeat_ok = false
	_check(repeat_ok, "surface_height doit etre deterministe")

	# --- the mesher actually produced geometry --------------------------------
	var triangles := 0
	var chunk_nodes := 0
	for child in world.get_children():
		var mi := child as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		chunk_nodes += 1
		var m: ArrayMesh = mi.mesh as ArrayMesh
		if m == null:
			continue
		for s in m.get_surface_count():
			triangles += m.surface_get_array_index_len(s) / 3
	print("  %d chunks avec maillage, %d triangles" % [chunk_nodes, triangles])
	_check(chunk_nodes > 0, "des noeuds de chunk doivent porter un maillage")
	_check(triangles > 1000, "le mailleur doit produire de la geometrie (obtenu %d triangles)" % triangles)

	# --- editing --------------------------------------------------------------
	# Scan upward for a cell that is genuinely empty rather than assuming a fixed
	# offset above the surface is clear: a trunk or a canopy may occupy it.
	var test_y := -1
	for y in range(ground + 1, mini(ground + 24, VoxelWorld.WORLD_HEIGHT)):
		if world.get_block(sx, y, sz) == Blocks.AIR:
			test_y = y
			break
	_check(test_y > 0, "une cellule vide doit exister au-dessus du sol")
	if test_y > 0:
		_check(world.set_block(sx, test_y, sz, Blocks.LAMP), "poser un bloc doit reussir")
		_check(world.get_block(sx, test_y, sz) == Blocks.LAMP, "le bloc pose doit se relire")
		_check(world.is_solid(sx, test_y, sz), "le bloc pose doit devenir solide")
		_check(world.set_block(sx, test_y, sz, Blocks.AIR), "retirer un bloc doit reussir")
		_check(world.get_block(sx, test_y, sz) == Blocks.AIR, "la cellule doit redevenir vide")
	_check(not world.set_block(sx, -5, sz, Blocks.STONE), "ecrire sous le monde doit echouer")
	_check(not world.set_block(sx, VoxelWorld.WORLD_HEIGHT + 5, sz, Blocks.STONE),
		"ecrire au-dessus du monde doit echouer")

	# --- player ---------------------------------------------------------------
	var pos: Vector3 = player.global_position
	print("  joueur : %s, gele : %s, au sol : %s" % [str(pos), str(player.frozen), str(player.on_floor())])
	_check(is_finite(pos.x) and is_finite(pos.y) and is_finite(pos.z),
		"la position du joueur doit rester finie")
	_check(not player.frozen, "le joueur doit etre libere une fois le terrain pret")
	_check(pos.y > 0.0, "le joueur ne doit pas etre tombe sous le monde")
	_check(player.camera != null, "la camera doit exister")
	_check(player.body != null, "le corps de collision doit exister")
	# Left alone on generated ground, the player must come to rest on it rather
	# than sinking into a block or hovering.
	if not player.fly_mode:
		_check(player.on_floor(), "hors vol, le joueur doit finir pose sur le sol")
	if player.body != null:
		_check(not player.body.overlaps_solid(world, pos),
			"le joueur ne doit pas etre encastre dans un bloc")

	# Regress the shoreline transition directly while preserving the live
	# player's state. A surface swim receives a stronger, one-shot impulse than
	# the ordinary land jump, which is what clears a one-block bank.
	var saved_velocity := player.velocity
	var saved_water := player.in_water
	var saved_floor := player._on_floor
	var saved_submersion := player._submersion
	var saved_boost := player._water_exit_boosted
	var saved_water_test_fly := player.fly_mode
	player.velocity = Vector3.ZERO
	player.fly_mode = false
	player.in_water = true
	player._on_floor = false
	player._submersion = Player.WATER_EXIT_RATIO
	player._water_exit_boosted = false
	Input.action_press("jump")
	player._apply_vertical(1.0 / 60.0)
	Input.action_release("jump")
	_check(player.velocity.y > Player.JUMP_SPEED,
		"sortir de l'eau doit donner plus d'elan qu'un saut terrestre")
	_check(player._water_exit_boosted, "l'impulsion de sortie d'eau doit etre unique")
	player.velocity = saved_velocity
	player.in_water = saved_water
	player._on_floor = saved_floor
	player._submersion = saved_submersion
	player._water_exit_boosted = saved_boost
	player.fly_mode = saved_water_test_fly

	# Settings-driven flight shares the same state as the F shortcut.
	var saved_creative := Game.creative
	var saved_game_fly := Game.fly_mode
	var saved_player_fly := player.fly_mode
	Game.creative = true
	Game.fly_mode = true
	_check(player.fly_mode, "le parametre God mode doit activer le vol du joueur")
	_check(is_equal_approx(Player.FLY_SPRINT_SPEED, Player.FLY_SPEED * 5.0),
		"courir en God mode doit multiplier exactement la vitesse de vol par cinq")
	Game.fly_mode = false
	_check(not player.fly_mode, "desactiver God mode doit couper le vol")
	Game.creative = saved_creative
	Game.fly_mode = saved_game_fly
	player.fly_mode = saved_player_fly
	player._on_floor = saved_floor
	player.velocity = saved_velocity

	# The compact counter is independent from F3 and reacts immediately to its
	# persistent setting.
	var saved_show_fps := Game.show_fps
	var saved_show_debug := Game.show_debug
	var saved_debug_visible := hud._debug.visible
	hud._debug.visible = false
	Game.show_debug = false
	Game.show_fps = true
	_check(hud._fps_label != null and hud._fps_label.visible,
		"Afficher les FPS doit montrer le compteur en haut a gauche")
	_check(hud._fps_label.text.ends_with(" FPS"), "le compteur doit afficher une valeur FPS")
	Game.show_fps = saved_show_fps
	Game.show_debug = saved_show_debug
	hud._debug.visible = saved_debug_visible
	hud.refresh_settings()

	# --- raycast --------------------------------------------------------------
	var hit: Dictionary = Interaction.raycast(world, player.eye_position(), Vector3.DOWN, 32.0)
	print("  visee vers le bas : %s" % str(hit.get("hit", false)))
	_check(bool(hit.get("hit", false)), "un tir vers le bas doit toucher le sol")
	if bool(hit.get("hit", false)):
		var cell: Vector3i = hit["cell"]
		# Targetable, not necessarily solid: the first thing a downward ray meets
		# may be a plant standing on the ground, breakable but without collision.
		var target_id: int = world.get_block(cell.x, cell.y, cell.z)
		_check(target_id != Blocks.AIR, "la cellule touchee ne doit pas etre vide")
		_check(not Blocks.is_liquid(target_id), "un liquide ne doit pas etre ciblable")
		_check(hit["normal"] == Vector3i(0, 1, 0),
			"la normale d'un tir vertical doit pointer vers le haut")
		_check(float(hit["distance"]) > 0.0, "la distance doit etre positive")

	# The player now spawns inside a village house, so a ray from the eye can
	# legitimately meet the ceiling lamp. Shoot from just under the world top,
	# where nothing can exist, to verify that leaving the world reports a miss.
	var sky_origin := Vector3(player.eye_position().x, float(VoxelWorld.WORLD_HEIGHT) - 1.5, player.eye_position().z)
	var up: Dictionary = Interaction.raycast(world, sky_origin, Vector3.UP, 3.0)
	_check(not bool(up.get("hit", false)), "un tir vers le ciel ne doit rien toucher")

	# --- sky ------------------------------------------------------------------
	if sky != null:
		print("  heure : %s" % sky.time_string())
		_check(sky.time_of_day >= 0.0 and sky.time_of_day <= 1.0,
			"l'heure du jour doit rester dans 0..1")
		var before: float = sky.time_of_day
		sky.skip_to(before + 0.5)
		_check(absf(sky.time_of_day - before) > 0.1, "skip_to doit changer l'heure")
		_check(sky.time_of_day >= 0.0 and sky.time_of_day <= 1.0,
			"skip_to doit rester dans 0..1 apres enroulement")
		sky.skip_to(1.4)
		_check(sky.time_of_day >= 0.0 and sky.time_of_day <= 1.0,
			"skip_to doit enrouler une valeur superieure a 1")

	# --- inventory ------------------------------------------------------------
	var inventory: Inventory = _main.inventory
	_check(inventory != null, "l'inventaire doit exister")
	if inventory != null:
		# The hotbar content is restored from the world save, so the active slot
		# may legitimately be empty (the player quit on an empty one). What must
		# hold is that the bar is not entirely empty and every entry is a real
		# block or item.
		var filled := 0
		for slot in Inventory.HOTBAR_SLOTS:
			var id: int = inventory.slot_block(slot)
			if id == Blocks.AIR:
				continue
			filled += 1
			_check(Items.is_valid_id(id),
				"la case %d contient un id invalide (%d)" % [slot, id])
			_check(inventory.slot_count(slot) > 0,
				"la case %d contient un id sans quantite" % slot)
		_check(filled > 0, "la barre d'action ne doit pas etre entierement vide")
		inventory.select(0)
		inventory.cycle(1)
		_check(inventory.selected == 1, "la molette doit changer de case")
		inventory.cycle(-2)
		_check(inventory.selected == Inventory.HOTBAR_SLOTS - 1,
			"la molette doit s'enrouler vers le bas")
		inventory.cycle(Inventory.HOTBAR_SLOTS + 3)
		_check(inventory.selected >= 0 and inventory.selected < Inventory.HOTBAR_SLOTS,
			"un grand pas de molette doit rester dans la barre")

	# --- rendering resources --------------------------------------------------
	var atlas: Texture2DArray = world.atlas()
	_check(atlas != null, "l'atlas doit exister")
	if atlas != null:
		_check(atlas.get_layers() == Blocks.TILE_COUNT,
			"l'atlas doit avoir %d calques (obtenu %d)" % [Blocks.TILE_COUNT, atlas.get_layers()])
	var mats: Array = world.materials()
	_check(mats.size() == Blocks.SURFACE_COUNT,
		"il doit y avoir %d materiaux" % Blocks.SURFACE_COUNT)
	for i in mats.size():
		_check(mats[i] != null, "le materiau %d ne doit pas etre nul" % i)

	# --- realistic rendering -------------------------------------------------
	var saved_realistic := Game.realistic
	Game.realistic = true
	var realistic_uniforms := true
	for material in mats:
		var shader_material := material as ShaderMaterial
		if shader_material != null and not is_equal_approx(
				float(shader_material.get_shader_parameter("realistic_mode")), 1.0):
			realistic_uniforms = false
	_check(realistic_uniforms, "Realistic doit activer les shaders ameliores")
	if pause_menu != null:
		_check(pause_menu._realistic_check != null and not pause_menu._realistic_check.disabled,
			"Realistic doit avoir une case a cocher active dans les reglages")
	Game.realistic = saved_realistic

	world.shutdown()


func _report() -> void:
	print("")
	if _failures.is_empty():
		print("  %d verifications, tout passe" % _checks)
		print("=======================")
		print("")
		get_tree().quit(0)
		return
	for message in _failures:
		print("  ECHEC  %s" % message)
	print("")
	print("  %d verifications, %d echecs" % [_checks, _failures.size()])
	print("=======================")
	print("")
	get_tree().quit(1)
