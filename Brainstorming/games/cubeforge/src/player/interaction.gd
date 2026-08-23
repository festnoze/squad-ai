class_name Interaction
extends Node3D
## Targeting, breaking and placing blocks.
##
## Extends Node3D because it owns two world-space children built in code: the
## selection outline (an ImmediateMesh cube of 12 edges) and the break particle
## burst. Both are top_level so their transform never depends on where the
## parent hangs in the scene tree.
##
## Targeting uses the Amanatides and Woo grid traversal: it visits exactly the
## cells the ray crosses, in order, which is the only way to get thin blocks and
## grazing-angle faces right. The face normal is the axis of the last step,
## negated.

signal target_changed(hit: Dictionary)
## 0..1 progress of the block being dug, 0 when nothing is in progress.
signal dig_progress(ratio: float)
signal block_broken(block_id: int, cell: Vector3i)
signal block_placed(block_id: int, cell: Vector3i)
## Right click on a placed crafting table (crouch to place a block instead).
signal crafting_requested()
## Right click on a placed chest (crouch to place a block instead).
signal chest_requested(cell: Vector3i)

## Maximum interaction distance in blocks.
const REACH := 6.0

## Half edge of the selection outline cube, slightly larger than the block so
## the lines never fight the block surface in the depth buffer.
const OUTLINE_HALF := 0.502

## Placement cadence while the button is held: five blocks per second.
const PLACE_INTERVAL := 0.2

## Slack on the cadence timer. Subtracting frame deltas leaves a few nanoseconds
## of float residue behind, which would silently cost a whole frame.
const TIMER_EPSILON := 1e-5

## Particles per break burst and their lifetime, from the contract.
const BURST_COUNT := 18
const BURST_LIFETIME := 0.7

## Melee swing reach and cadence. Reach is shorter than block REACH on purpose:
## a monster inside arm's length takes the hit before the block behind it.
const ATTACK_RANGE := 3.5
const ATTACK_INTERVAL := 0.45
const BOW_INTERVAL := 0.9
const ARROW_SPEED := 26.0

## Averaged tile colour per block id. Scanning a 32x32 image costs nothing once
## but would show up in the profiler if done on every break, so it is cached for
## the whole process lifetime.
static var _tint_cache: Dictionary = {}

var _world: VoxelWorld = null
var _player: Player = null
var _inventory: Inventory = null

var _outline: MeshInstance3D = null
var _outline_mesh: ImmediateMesh = null
var _particles: GPUParticles3D = null
var _particle_process: ParticleProcessMaterial = null

## Last raycast result, kept so the outline and the signals only react to real
## changes.
var _current: Dictionary = {}
var _has_target: bool = false
var _target_cell: Vector3i = Vector3i.ZERO
var _target_id: int = Blocks.AIR

## Cached reference to the Sfx autoload. It is reached through the scene tree
## instead of by its global identifier because `godot --check-only --script`
## never registers autoloads, and a module that cannot be verified in isolation
## is a module nobody dares touch. Same node, same methods, same behaviour.
var _sfx: Node = null

var _dig_time: float = 0.0
var _dig_active: bool = false
var _reported_ratio: float = 0.0
var _place_timer: float = 0.0
var _attack_timer: float = 0.0
var _bow_timer: float = 0.0

## Combat lookup (the monster manager). Optional: without it the module works
## exactly as before, blocks only.
var _monsters: Node = null


func _ready() -> void:
	if _outline == null:
		_build_outline()
	if _particles == null:
		_build_particles()
	set_process(_world != null)


func setup(world: VoxelWorld, player: Player, inventory: Inventory) -> void:
	_world = world
	_player = player
	_inventory = inventory
	if _outline == null:
		_build_outline()
	if _particles == null:
		_build_particles()
	_clear_target()
	set_process(true)


## Wires the monster manager so left click can strike mobs and the bow can
## spawn arrows. Called by main after both modules exist.
func set_combat(monsters: Node) -> void:
	_monsters = monsters


## Read-only view of the block currently under the crosshair, same shape as
## raycast(). Empty-miss dictionary when nothing is targeted.
func current_hit() -> Dictionary:
	return _current.duplicate()


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------

func _sfx_node() -> Node:
	if _sfx == null or not is_instance_valid(_sfx):
		_sfx = null
		if is_inside_tree():
			_sfx = get_node_or_null(^"/root/Sfx")
	return _sfx


## Calls one method of the Sfx autoload, doing nothing when audio is absent
## (headless tests, or a scene built without the autoload).
func _sfx_call(method: StringName, args: Array) -> void:
	var node := _sfx_node()
	if node != null and node.has_method(method):
		node.callv(method, args)


# ---------------------------------------------------------------------------
# Raycast
# ---------------------------------------------------------------------------

## Amanatides and Woo voxel traversal. Walks the exact sequence of cells the ray
## crosses and stops on the first targetable block. Air and liquids are skipped
## as targets but never stop the ray.
static func raycast(world: VoxelWorld, origin: Vector3, direction: Vector3, max_distance: float) -> Dictionary:
	var miss := _miss(origin)
	if world == null or max_distance <= 0.0:
		return miss
	if direction.length_squared() < 1e-12:
		return miss
	var dir := direction.normalized()

	var cell := Vector3i(floori(origin.x), floori(origin.y), floori(origin.z))

	# The cell holding the origin can already be a block (head inside a placed
	# block, or standing in foliage). Report it with the face pointing back at
	# the ray origin so the caller still gets a usable placement normal.
	var first := world.get_block(cell.x, cell.y, cell.z)
	if _is_targetable(first):
		return {
			"hit": true,
			"cell": cell,
			"normal": _normal_towards_origin(dir),
			"id": first,
			"distance": 0.0,
			"point": origin,
		}

	var step := Vector3i.ZERO
	# t_max[a] is the ray parameter at which the next boundary on axis a is
	# crossed, t_delta[a] the parameter spent crossing one full cell. A zero
	# direction component gets INF on both, so that axis never steps and never
	# divides by zero.
	var t_max := Vector3(INF, INF, INF)
	var t_delta := Vector3(INF, INF, INF)

	for axis in 3:
		var d: float = dir[axis]
		var o: float = origin[axis]
		var c: int = cell[axis]
		if d > 0.0:
			step[axis] = 1
			t_delta[axis] = 1.0 / d
			t_max[axis] = (float(c + 1) - o) / d
		elif d < 0.0:
			step[axis] = -1
			t_delta[axis] = -1.0 / d
			# When the origin sits exactly on the lower boundary this is 0.0,
			# so the traversal immediately moves into the cell behind it, which
			# is the cell a negative-direction ray really starts in.
			t_max[axis] = (float(c) - o) / d

	# Bounded by construction: every step advances at least one cell boundary,
	# and the cap keeps a degenerate direction from spinning forever.
	var max_steps := int(max_distance * 3.0) + 8
	for _i in max_steps:
		var axis := 0
		if t_max.y < t_max.x:
			axis = 1
		if t_max.z < t_max[axis]:
			axis = 2
		var t: float = t_max[axis]
		if not (t <= max_distance):
			return miss

		cell[axis] += step[axis]
		t_max[axis] += t_delta[axis]

		# Leaving the world vertically can never come back inside on a straight
		# ray, so give up early instead of walking the whole reach.
		if cell.y < 0 and step.y <= 0:
			return miss
		if cell.y >= VoxelWorld.WORLD_HEIGHT and step.y >= 0:
			return miss

		var id := world.get_block(cell.x, cell.y, cell.z)
		if _is_targetable(id):
			var normal := Vector3i.ZERO
			normal[axis] = -step[axis]
			return {
				"hit": true,
				"cell": cell,
				"normal": normal,
				"id": id,
				"distance": t,
				"point": origin + dir * t,
			}
	return miss


static func _miss(origin: Vector3) -> Dictionary:
	return {
		"hit": false,
		"cell": Vector3i.ZERO,
		"normal": Vector3i.ZERO,
		"id": Blocks.AIR,
		"distance": 0.0,
		"point": origin,
	}


## Air and liquids are see-through for targeting: the ray keeps going.
static func _is_targetable(id: int) -> bool:
	return id != Blocks.AIR and not Blocks.is_liquid(id)


## Face of the origin cell that looks back at the viewer, taken as the dominant
## axis of the ray direction.
static func _normal_towards_origin(dir: Vector3) -> Vector3i:
	var ax := absf(dir.x)
	var ay := absf(dir.y)
	var az := absf(dir.z)
	var axis := 0
	var best := ax
	if ay > best:
		axis = 1
		best = ay
	if az > best:
		axis = 2
	var normal := Vector3i.ZERO
	normal[axis] = -1 if dir[axis] > 0.0 else 1
	return normal


# ---------------------------------------------------------------------------
# Per frame
# ---------------------------------------------------------------------------

func _process(delta: float) -> void:
	if _world == null or _player == null:
		return

	if _place_timer > 0.0:
		_place_timer = maxf(_place_timer - delta, 0.0)
	if _attack_timer > 0.0:
		_attack_timer = maxf(_attack_timer - delta, 0.0)
	if _bow_timer > 0.0:
		_bow_timer = maxf(_bow_timer - delta, 0.0)

	# A visible mouse means a menu is open: no targeting, no editing.
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		if _has_target:
			_clear_target()
		_stop_dig()
		return

	var hit := raycast(_world, _player.eye_position(), _player.look_direction(), REACH)
	_update_target(hit)

	if Input.is_action_pressed("dig"):
		var held := Blocks.AIR
		if _inventory != null:
			held = _inventory.selected_block()
		if Items.kind_of(held) == Items.Kind.BOW:
			# The bow replaces digging entirely: click to shoot.
			_stop_dig()
			if Input.is_action_just_pressed("dig"):
				_try_shoot()
		else:
			var mob := _mob_under_crosshair()
			if mob != null:
				_stop_dig()
				if _attack_timer <= 0.0:
					_attack(mob, held)
			else:
				_tick_dig(delta)
	else:
		_stop_dig()

	if Input.is_action_just_pressed("place"):
		_place_timer = 0.0
		_try_place()
	elif Input.is_action_pressed("place") and _place_timer <= TIMER_EPSILON:
		_try_place()


## Detects target changes and keeps the outline in step. The ImmediateMesh is
## only rebuilt here, never per frame.
func _update_target(hit: Dictionary) -> void:
	var hit_now: bool = hit["hit"]
	var cell: Vector3i = hit["cell"]
	var id: int = hit["id"]
	var changed: bool = hit_now != _has_target or (hit_now and (cell != _target_cell or id != _target_id))

	_current = hit
	if not changed:
		return

	# Any change of cell (or of the block sitting in it) invalidates the dig in
	# progress, including a change to nothing at all.
	if not hit_now or cell != _target_cell or id != _target_id:
		_stop_dig()

	_has_target = hit_now
	_target_cell = cell
	_target_id = id

	if hit_now:
		_rebuild_outline(cell)
		_outline.visible = true
	else:
		_outline.visible = false

	target_changed.emit(hit)


func _clear_target() -> void:
	_has_target = false
	_target_cell = Vector3i.ZERO
	_target_id = Blocks.AIR
	var origin := Vector3.ZERO
	if _player != null:
		origin = _player.eye_position()
	_current = _miss(origin)
	if _outline != null:
		_outline.visible = false
	target_changed.emit(_current)


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------

## Living monster crossed by the view ray, but only if it is closer than the
## targeted block: a mob hiding behind a wall stays safe.
func _mob_under_crosshair() -> Node:
	if _monsters == null or not _monsters.has_method("ray_pick"):
		return null
	var reach := ATTACK_RANGE
	if _has_target:
		reach = minf(reach, float(_current["distance"]))
	return _monsters.call("ray_pick", _player.eye_position(), _player.look_direction(), reach)


func _attack(mob: Node, held_id: int) -> void:
	_attack_timer = ATTACK_INTERVAL
	if mob.has_method("take_damage"):
		mob.call("take_damage", Items.melee_damage(held_id), _player.global_position)


## Shoots one arrow with the bow. Survival consumes one ARROW item; creative
## quivers are bottomless (Inventory.take always succeeds there).
func _try_shoot() -> void:
	if _bow_timer > 0.0 or _monsters == null or not _monsters.has_method("spawn_arrow"):
		return
	if _inventory == null or not _inventory.take(Items.ARROW, 1):
		return
	_bow_timer = BOW_INTERVAL
	var direction := _player.look_direction()
	var origin := _player.eye_position() + direction * 0.35
	_monsters.call("spawn_arrow", origin, direction * ARROW_SPEED, true)
	_sfx_call(&"play", ["pop", -2.0, 1.5])


# ---------------------------------------------------------------------------
# Breaking
# ---------------------------------------------------------------------------

func _tick_dig(delta: float) -> void:
	if not _has_target:
		_stop_dig()
		return
	var id := _world.get_block(_target_cell.x, _target_cell.y, _target_cell.z)
	if id != _target_id:
		# The world changed under the crosshair, restart from scratch.
		_stop_dig()
		_target_id = id
		return
	if not Blocks.is_breakable(id):
		# Bedrock and water make no progress at all.
		_stop_dig()
		return

	_dig_active = true
	_dig_time += delta
	var hard := Blocks.hardness(id)
	# A pickaxe of the right family divides the dig time by its tier speed.
	if _inventory != null:
		hard /= Items.dig_multiplier(_inventory.selected_block(), id)
	if hard <= 0.001:
		_break_target(id)
		return

	if _dig_time >= hard:
		_break_target(id)
		return

	_report_ratio(clampf(_dig_time / hard, 0.0, 1.0))
	_sfx_call(&"play_dig", [id, _cell_centre(_target_cell)])


func _stop_dig() -> void:
	if _dig_active:
		_sfx_call(&"stop_dig", [])
	_dig_active = false
	_dig_time = 0.0
	_report_ratio(0.0)


func _break_target(id: int) -> void:
	var cell := _target_cell
	if not _world.set_block(cell.x, cell.y, cell.z, Blocks.AIR):
		_stop_dig()
		return

	# Ore blocks yield their material item (coal, ingots, diamond), the rest
	# follows the plain block drop table.
	var drop := Items.drop_for(id)
	if drop != Blocks.AIR and _inventory != null:
		_inventory.add(drop, 1)

	var centre := _cell_centre(cell)
	_burst(id, centre)
	_sfx_call(&"stop_dig", [])
	_sfx_call(&"play_break", [id, centre])

	_dig_active = false
	_dig_time = 0.0
	_report_ratio(0.0)
	block_broken.emit(id, cell)

	# Force a fresh target next frame: the cell is empty now.
	_target_id = Blocks.AIR
	_has_target = false
	if _outline != null:
		_outline.visible = false


func _report_ratio(ratio: float) -> void:
	if is_equal_approx(ratio, _reported_ratio):
		return
	_reported_ratio = ratio
	dig_progress.emit(ratio)


# ---------------------------------------------------------------------------
# Placing
# ---------------------------------------------------------------------------

func _try_place() -> void:
	if not _has_target or _inventory == null:
		return

	# Interacting with a placed crafting table beats placing a block, unless
	# the player crouches to build against it.
	if _target_id == Blocks.CRAFTING_TABLE and not Input.is_action_pressed("crouch"):
		_place_timer = PLACE_INTERVAL
		crafting_requested.emit()
		return

	# Same rule for a placed chest: right click opens it, crouch builds against.
	if _target_id == Blocks.CHEST and not Input.is_action_pressed("crouch"):
		_place_timer = PLACE_INTERVAL
		chest_requested.emit(_target_cell)
		return

	var block: int = _inventory.selected_block()
	# Items (tools, materials) cannot be placed in the world.
	if block <= Blocks.AIR or block >= Blocks.COUNT:
		return

	var normal: Vector3i = _current["normal"]
	var cell := _target_cell + normal
	if cell.y < 0 or cell.y >= VoxelWorld.WORLD_HEIGHT:
		return
	if not _world.has_chunk_at(cell.x, cell.z):
		return
	if not Blocks.is_replaceable(_world.get_block(cell.x, cell.y, cell.z)):
		return
	# A plant only survives on top of something solid.
	if Blocks.needs_support(block) and not _world.is_solid(cell.x, cell.y - 1, cell.z):
		return
	# Anti-suffocation: never seal the player inside a solid block.
	if Blocks.collides(block) and _player_overlaps(cell):
		return

	if not _inventory.consume_selected(1):
		return
	if not _world.set_block(cell.x, cell.y, cell.z, block):
		# Put the item back, the write was refused (unloaded chunk).
		_inventory.add(block, 1)
		return

	_place_timer = PLACE_INTERVAL
	_sfx_call(&"play_place", [block, _cell_centre(cell)])
	block_placed.emit(block, cell)


## True when the player box overlaps the cell. The box has its origin at the
## feet, like VoxelBody, and uses the live crouch height.
func _player_overlaps(cell: Vector3i) -> bool:
	if _player == null or _player.body == null:
		return false
	var feet: Vector3 = _player.global_position if _player.is_inside_tree() else _player.position
	var r: float = _player.body.radius
	var h: float = _player.body.height
	var lo := Vector3(feet.x - r, feet.y, feet.z - r)
	var hi := Vector3(feet.x + r, feet.y + h, feet.z + r)
	var cell_lo := Vector3(cell)
	var cell_hi := cell_lo + Vector3.ONE
	# A shared face is not an overlap, hence the small epsilon.
	const EPS := 0.001
	if hi.x <= cell_lo.x + EPS or lo.x >= cell_hi.x - EPS:
		return false
	if hi.y <= cell_lo.y + EPS or lo.y >= cell_hi.y - EPS:
		return false
	if hi.z <= cell_lo.z + EPS or lo.z >= cell_hi.z - EPS:
		return false
	return true


# ---------------------------------------------------------------------------
# Selection outline
# ---------------------------------------------------------------------------

func _build_outline() -> void:
	_outline_mesh = ImmediateMesh.new()
	_outline = MeshInstance3D.new()
	_outline.name = "SelectionOutline"
	_outline.mesh = _outline_mesh
	_outline.top_level = true
	_outline.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_outline.visible = false
	var mat := VoxelMaterials.outline_material()
	if mat != null:
		_outline.material_override = mat
	else:
		push_warning("Interaction: no outline material, selection cube will be untextured")
	add_child(_outline)


## Rebuilds the 12 edges of the highlight cube around `cell`. Called only when
## the target cell changes.
func _rebuild_outline(cell: Vector3i) -> void:
	_outline.position = _cell_centre(cell)
	var s := OUTLINE_HALF
	_outline_mesh.clear_surfaces()
	_outline_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	for i in 2:
		var a := s if i == 1 else -s
		for j in 2:
			var b := s if j == 1 else -s
			# Four edges along each axis.
			_outline_mesh.surface_add_vertex(Vector3(-s, a, b))
			_outline_mesh.surface_add_vertex(Vector3(s, a, b))
			_outline_mesh.surface_add_vertex(Vector3(a, -s, b))
			_outline_mesh.surface_add_vertex(Vector3(a, s, b))
			_outline_mesh.surface_add_vertex(Vector3(a, b, -s))
			_outline_mesh.surface_add_vertex(Vector3(a, b, s))
	_outline_mesh.surface_end()


# ---------------------------------------------------------------------------
# Break particles
# ---------------------------------------------------------------------------

func _build_particles() -> void:
	_particle_process = ParticleProcessMaterial.new()
	_particle_process.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	_particle_process.emission_box_extents = Vector3(0.3, 0.3, 0.3)
	_particle_process.direction = Vector3(0.0, 1.0, 0.0)
	_particle_process.spread = 65.0
	_particle_process.initial_velocity_min = 1.1
	_particle_process.initial_velocity_max = 3.2
	_particle_process.gravity = Vector3(0.0, -14.0, 0.0)
	_particle_process.damping_min = 0.3
	_particle_process.damping_max = 1.4
	_particle_process.scale_min = 0.55
	_particle_process.scale_max = 1.25
	_particle_process.angular_velocity_min = -240.0
	_particle_process.angular_velocity_max = 240.0
	_particle_process.color = Color(0.7, 0.7, 0.7)

	var quad := QuadMesh.new()
	quad.size = Vector2(0.12, 0.12)
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.vertex_color_use_as_albedo = true
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	mat.billboard_keep_scale = true
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.disable_receive_shadows = true
	quad.material = mat

	_particles = GPUParticles3D.new()
	_particles.name = "BreakParticles"
	_particles.top_level = true
	_particles.local_coords = false
	_particles.one_shot = true
	_particles.explosiveness = 1.0
	_particles.amount = BURST_COUNT
	_particles.lifetime = BURST_LIFETIME
	_particles.emitting = false
	_particles.process_material = _particle_process
	_particles.draw_pass_1 = quad
	add_child(_particles)


## Single 18 particle burst tinted with the average colour of the block tile.
func _burst(block_id: int, centre: Vector3) -> void:
	if _particles == null:
		return
	_particle_process.color = _block_tint(block_id)
	_particles.position = centre
	_particles.emitting = false
	_particles.restart()
	_particles.emitting = true


## Average of the opaque pixels of the block top tile, cached per block id.
static func _block_tint(block_id: int) -> Color:
	if _tint_cache.has(block_id):
		return _tint_cache[block_id]
	var tint := Color(0.72, 0.72, 0.72)
	var layer := Blocks.tile_of(block_id, Blocks.FACE_PY)
	if layer >= 0 and layer < Blocks.TILE_NAMES.size():
		var img := VoxelAtlas.tile_image(Blocks.TILE_NAMES[layer])
		if img != null and not img.is_empty():
			var r := 0.0
			var g := 0.0
			var b := 0.0
			var n := 0
			for y in img.get_height():
				for x in img.get_width():
					var c := img.get_pixel(x, y)
					if c.a > 0.5:
						r += c.r
						g += c.g
						b += c.b
						n += 1
			if n > 0:
				var inv := 1.0 / float(n)
				tint = Color(r * inv, g * inv, b * inv)
	_tint_cache[block_id] = tint
	return tint


static func _cell_centre(cell: Vector3i) -> Vector3:
	return Vector3(cell) + Vector3(0.5, 0.5, 0.5)
