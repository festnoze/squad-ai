## One AI combatant: German by default, allied when the faction says so.
##
## Design notes, because this is the file that decides whether the game feels
## like a war or like a shooting gallery:
##
##  * No NavigationServer. The world is streamed and procedural, so there is no
##    baked navmesh anywhere. The soldier drives himself: a desired velocity
##    towards a destination, three forward whiskers for local avoidance, ground
##    following through GameWorld.ground_y() and move_and_slide() for the rest.
##    Anything that gets stuck for three seconds gives up on its destination,
##    and after three failures it snaps back to its anchor. Without that you get
##    soldiers vibrating against a wall forever.
##  * Reaction time. A soldier that just spotted the player does NOT fire on the
##    same frame: 0.35 to 0.9 s depending on rank and difficulty.
##  * Imperfect, converging aim. The first rounds of a burst are deliberately
##    off; the aim tightens while the target stays visible. A veteran converges
##    faster than a conscript. It is never 100 percent, not even at 10 m.
##  * Perception is spread over time (one sight test every 0.2 to 0.35 s with a
##    random initial offset) so sixty soldiers never raycast on the same frame.
##    Past 200 m from the player everything but locomotion is switched off.
##  * Corpse discovery rides on that same budget instead of adding to it: its
##    own 0.2 to 0.35 s tick, phase shifted from the sight tick, tests the line
##    of sight to ONE nearby friendly body per call, taken round robin from a
##    short list rebuilt about once a second. A body already reported carries a
##    marker and is skipped for good, so a battlefield littered with old corpses
##    costs nothing. Being past 200 m switches the whole thing off with the rest
##    of the perception.
class_name Soldier
extends CharacterBody3D

signal died(soldier: Soldier)
signal spotted_enemy(soldier: Soldier, target: Node3D)
signal fired_shot(soldier: Soldier)

# States
const S_IDLE := 0
const S_PATROL := 1
const S_ALERT := 2       # heard something, looking for it
const S_COMBAT := 3
const S_ADVANCE := 4
const S_COVER := 5
const S_FLANK := 6
const S_RETREAT := 7
const S_DEAD := 8
const S_SUPPRESSED := 9

# Ranks, drive health / accuracy / weapon
const R_CONSCRIPT := 0
const R_REGULAR := 1
const R_VETERAN := 2
const R_OFFICER := 3
const R_SNIPER := 4
const R_MACHINE_GUNNER := 5

# Squad roles, assigned from Squad.report_contact().
const ROLE_FREE := 0
const ROLE_FIX := 1        # pin the target down from the front
const ROLE_FLANK := 2      # go around while somebody else fixes
const ROLE_SUPPORT := 3    # stay back, cover the others

# Body metrics. The capsule is the contract: radius 0.35, height 1.75.
const BODY_RADIUS := 0.35
const BODY_HEIGHT := 1.75
const CROUCH_BODY_HEIGHT := 1.20
const EYE_STAND := 1.60
const EYE_CROUCH := 1.05
const HEAD_STAND := 1.45
const HEAD_CROUCH := 0.95

const GRAVITY := 19.6
const WALK_SPEED := 2.5
const RUN_SPEED := 5.1
const CROUCH_SPEED := 1.4
const TURN_SPEED := 7.0

# Local avoidance
const WHISKER_LENGTH := 3.0
const WHISKER_ANGLE := 0.61            # about 35 degrees
const AVOID_INTERVAL := 0.15

# Anti stuck
const STUCK_WINDOW := 3.0
const STUCK_DISTANCE := 0.5
const MAX_STUCK_FAILS := 3

const FAR_DISTANCE := 200.0
const CORPSE_SECONDS := 30.0
const SINK_SECONDS := 4.0
const SINK_SPEED := 0.32

const SEARCH_MIN := 15.0
const SEARCH_MAX := 25.0
const RALLY_RADIUS := 25.0
const SQUAD_VOICE_RANGE := 60.0
const SUPPRESS_RADIUS := 1.5
const SUPPRESS_DECAY := 0.38
const SUPPRESS_TRIGGER := 0.75

# Corpse discovery. A man lying flat in the grass is nothing like a man standing
# up, so the base range is a fraction of the normal sight range; light and
# weather still cut into it through Senses.sight_range().
const CORPSE_SIGHT_RANGE := 38.0
## Height above the body origin that is actually looked for. The ragdoll lies
## down, so aiming at the chest of a standing man would probe thin air.
const CORPSE_LOOK_HEIGHT := 0.45
## Hard cap on the short list, so a massacre never turns into a long loop.
const CORPSE_LIST_MAX := 6
## Metadata written on a body once somebody has reported it.
const CORPSE_MARK := "corpse_found"

# Escort (order_follow). The dead band between "close enough" and "too far" is
# what keeps a companion from shuffling around a player who is standing still.
const FOLLOW_MIN_DISTANCE := 2.0
const FOLLOW_STOP_FACTOR := 0.62
const FOLLOW_RUN_FACTOR := 2.6

# Contract members
var faction: int = 1         # War.AXIS or War.ALLIED
var rank: int = R_REGULAR
var state: int = S_IDLE
var health: float = 100.0
var target: Node3D = null

# Wiring
var _world: GameWorld = null
var _squad: Node3D = null                    # Squad, kept untyped to avoid a cycle
var _rng := RandomNumberGenerator.new()
var _ready_to_run := false
var _time := 0.0

# Anchors and orders
var _home := Vector3.ZERO
var _hold_pos := Vector3.ZERO
var _route: PackedVector3Array = PackedVector3Array()
var _route_index := 0
var _route_wait := 0.0
var _order_pos := Vector3.ZERO
var _has_order := false
var _role := ROLE_FREE

# Destination and locomotion
var _dest := Vector3.ZERO
var _has_dest := false
var _dest_tolerance := 1.4
var _wants_move := false
var _run := false
var _crouched := false
var _avoid_timer := 0.0
var _avoid_dir := Vector3.ZERO
var _avoid_side := 1.0
var _stuck_timer := 0.0
var _stuck_ref := Vector3.ZERO
var _stuck_fails := 0
var _face_dir := Vector3.FORWARD
var _look_timer := 0.0

# Perception
var _candidates: Array[Node3D] = []
var _scan_timer := 0.0
var _see_timer := 0.0
var _env_timer := 0.0
var _light := 1.0
var _visibility := 1.0
var _sky_node: Node = null
var _weather_node: Node = null
var _target_visible := false
var _lost_timer := 0.0
var _last_known := Vector3.ZERO
var _has_last_known := false
var _search_timer := 0.0
var _alert_cry_timer := 0.0
var _shout_timer := 0.0
var _player_hooked := false

# Corpse discovery. `_corpses` stays untyped on purpose: it holds nodes that
# free themselves on their own schedule, and an untyped Array lets every entry
# be validated before anything casts it.
var _corpses: Array = []
var _corpse_timer := 0.0
var _corpse_scan := 0.0
var _corpse_index := 0

# Stealth and intelligence
var _silent_death := false
var _home_site := -1

# Escort
var _follow_node: Node3D = null
var _follow_distance := 4.0
var _follow_angle := 0.0
var _follow_moving := false

# Combat
var _weapon_id := -1
var _weapon: Weapon = null
var _reaction_timer := 0.0
var _aim_converge := 0.0
var _burst_left := 0
var _burst_pause := 0.0
var _shots_in_burst := 0
var _reposition_timer := 0.0
var _suppression := 0.0
var _morale := 0.7
var _rallied_timer := 0.0
var _officer_timer := 0.0
var _cover: Array = []
var _cover_refresh := 0.0
var _cover_pos := Vector3.ZERO
var _has_cover := false
var _peek_timer := 0.0
var _peeking := false
var _blind_fire := false

# Which creature this soldier wears. Purely cosmetic: a zombie fights with the
# exact same brain, weapon and cover logic as a rifleman, it just looks like a
# zombie. Set before `setup()`; see `CharacterModels`.
var species: int = CharacterModels.SPECIES_SOLDIER

# Body and animation
var _body: Node3D = null
# Non-null only when the body is an imported rigged model. While it is set the
# per-limb block in `_tick_animation` is dead: those Node3D limbs do not exist
# on a skeleton, and the clips drive the pose instead.
var _anim: CharacterAnim = null
var _shape: CollisionShape3D = null
var _capsule: CapsuleShape3D = null
var _hips: Node3D = null
var _torso: Node3D = null
var _head: Node3D = null
var _arm_l: Node3D = null
var _arm_r: Node3D = null
var _leg_l: Node3D = null
var _leg_r: Node3D = null
var _weapon_node: Node3D = null
var _anim_phase := 0.0
var _body_y := 0.0

# Death
var _dead_time := 0.0
var _fall_angle := 0.0
var _fall_axis := Vector3.RIGHT
# True once a death clip has taken over the corpse, which means the tip-over in
# `_tick_dead` must keep its hands off the visual basis.
var _rig_death := false
var _far := false
var _far_timer := 0.0


func _ready() -> void:
	# Everything meaningful happens in setup(); this only keeps the node quiet
	# until the caller has wired it.
	set_physics_process(true)


## `home` is the anchor the soldier patrols around.
func setup(game_world: GameWorld, faction_id: int, soldier_rank: int, home: Vector3) -> void:
	_world = game_world
	faction = faction_id
	rank = soldier_rank
	_home = home
	_hold_pos = home
	_stuck_ref = home

	_rng.seed = int(abs(home.x * 7919.0 + home.z * 104729.0)) + Time.get_ticks_usec()

	_build_collision()
	_build_body()
	_apply_rank()

	add_to_group("damageable")
	add_to_group(_faction_group())
	set_meta("surface", "flesh")
	set_meta("faction", faction)

	collision_layer = Layers.faction_layer(faction)
	collision_mask = Layers.WALK_MASK
	floor_max_angle = deg_to_rad(58.0)
	floor_snap_length = 0.6
	floor_stop_on_slope = true
	up_direction = Vector3.UP
	motion_mode = CharacterBody3D.MOTION_MODE_GROUNDED
	wall_min_slide_angle = deg_to_rad(12.0)

	var start := home
	if _world != null:
		start.y = _world.ground_y(home.x, home.z) + 0.05
	_place(start)

	# Random offsets so sixty soldiers never think on the same frame.
	_see_timer = _rng.randf() * 0.35
	_scan_timer = _rng.randf() * 0.5
	_env_timer = _rng.randf() * 1.5
	# Deliberately shifted past the sight offset so a soldier never pays for a
	# sight test and a corpse test on the same frame.
	_corpse_timer = 0.35 + _rng.randf() * 0.35
	_corpse_scan = _rng.randf() * 0.8
	_follow_angle = _rng.randf_range(-0.7, 0.7)
	_far_timer = _rng.randf()
	_look_timer = _rng.randf_range(1.0, 3.0)
	_face_dir = Vector3(_rng.randf_range(-1.0, 1.0), 0.0, _rng.randf_range(-1.0, 1.0)).normalized()
	if _face_dir.length_squared() < 0.01:
		_face_dir = Vector3.FORWARD
	_ready_to_run = true
	_enter_state(S_IDLE)


func _build_collision() -> void:
	_capsule = CapsuleShape3D.new()
	_capsule.radius = BODY_RADIUS
	_capsule.height = BODY_HEIGHT
	_shape = CollisionShape3D.new()
	_shape.name = "Body"
	_shape.shape = _capsule
	_shape.position = Vector3(0.0, BODY_HEIGHT * 0.5, 0.0)
	add_child(_shape)


func _build_body() -> void:
	# `soldier_body` folds the variant with % 3, so asking for 0..2 keeps the
	# three builds equally likely instead of handing build 0 a double share.
	var variant := _rng.randi_range(0, 2)
	_body = Meshes.soldier_body(faction, variant, species)
	if _body == null:
		_body = _fallback_body()
	_body.name = "Visual"
	add_child(_body)
	_anim = CharacterAnim.attach(_body, species)
	# A rigged model has no limb nodes to rotate: its pose comes from the clips.
	# Leaving these null is exactly what switches the procedural block off in
	# `_tick_animation`, which already guards every one of them.
	if _anim == null:
		_hips = _limb("Hips")
		_torso = _limb("Torso")
		_head = _limb("Head")
		_arm_l = _limb("ArmL")
		_arm_r = _limb("ArmR")
		_leg_l = _limb("LegL")
		_leg_r = _limb("LegR")
	# Both bodies carry a "Weapon": it is where the bullets leave from.
	_weapon_node = _limb("Weapon")


func _limb(limb_name: String) -> Node3D:
	if _body == null:
		return null
	if _body.name == limb_name:
		return _body
	return _body.find_child(limb_name, true, false) as Node3D


## Last resort silhouette, only used when Meshes hands back nothing. Better a
## crude box man than an invisible enemy shooting from nowhere.
func _fallback_body() -> Node3D:
	var root := Node3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(0.55, 1.2, 0.32)
	var body_mesh := MeshInstance3D.new()
	body_mesh.name = "Torso"
	body_mesh.mesh = mesh
	body_mesh.position = Vector3(0.0, 1.05, 0.0)
	body_mesh.material_override = MatLib.get_material(
			"uniform_axis" if faction == War.AXIS else "uniform_allied")
	root.add_child(body_mesh)
	var head_mesh := MeshInstance3D.new()
	head_mesh.name = "Head"
	var head_box := BoxMesh.new()
	head_box.size = Vector3(0.26, 0.28, 0.26)
	head_mesh.mesh = head_box
	head_mesh.position = Vector3(0.0, 1.78, 0.0)
	head_mesh.material_override = MatLib.get_material("skin")
	root.add_child(head_mesh)
	return root


func _apply_rank() -> void:
	health = _rank_health(rank)
	_morale = _rank_morale(rank)
	_weapon_id = _pick_weapon()
	_weapon = Weapon.new(_weapon_id, true)
	if rank == R_SNIPER or rank == R_MACHINE_GUNNER:
		_dest_tolerance = 1.0


func _rank_health(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 70.0
		R_REGULAR:
			return 100.0
		R_VETERAN:
			return 120.0
		R_OFFICER:
			return 110.0
		R_SNIPER:
			return 80.0
		R_MACHINE_GUNNER:
			return 130.0
	return 100.0


func _rank_morale(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 0.42
		R_REGULAR:
			return 0.66
		R_VETERAN:
			return 0.92
		R_OFFICER:
			return 1.0
		R_SNIPER:
			return 0.78
		R_MACHINE_GUNNER:
			return 0.8
	return 0.7


## Best case cone half angle in radians once the aim has fully settled.
func _rank_spread(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 0.052
		R_REGULAR:
			return 0.034
		R_VETERAN:
			return 0.021
		R_OFFICER:
			return 0.030
		R_SNIPER:
			return 0.0075
		R_MACHINE_GUNNER:
			return 0.044
	return 0.035


## How fast the aim tightens, in convergence units per second.
func _rank_converge(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 0.45
		R_REGULAR:
			return 0.85
		R_VETERAN:
			return 1.55
		R_OFFICER:
			return 1.05
		R_SNIPER:
			return 1.9
		R_MACHINE_GUNNER:
			return 0.6
	return 0.9


func _rank_reaction(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 0.86
		R_REGULAR:
			return 0.66
		R_VETERAN:
			return 0.44
		R_OFFICER:
			return 0.60
		R_SNIPER:
			return 0.54
		R_MACHINE_GUNNER:
			return 0.72
	return 0.65


func _rank_sight(value: int) -> float:
	match value:
		R_CONSCRIPT:
			return 105.0
		R_REGULAR:
			return 130.0
		R_VETERAN:
			return 150.0
		R_OFFICER:
			return 130.0
		R_SNIPER:
			return 260.0
		R_MACHINE_GUNNER:
			return 145.0
	return 130.0


## Comfortable engagement distance, drives the repositioning.
func _preferred_range() -> Vector2:
	match rank:
		R_SNIPER:
			return Vector2(60.0, 220.0)
		R_MACHINE_GUNNER:
			return Vector2(18.0, 90.0)
		R_OFFICER:
			# Officers carry a pistol on both sides now. A pistol duel at sixty
			# metres is a pantomime, so he closes in with the men he leads.
			if _is_pistol(_weapon_id):
				return Vector2(8.0, 30.0)
			return Vector2(22.0, 60.0)
	if _weapon_id == WeaponDefs.MP40 or _weapon_id == WeaponDefs.THOMPSON:
		return Vector2(6.0, 32.0)
	if _is_pistol(_weapon_id):
		return Vector2(4.0, 18.0)
	return Vector2(14.0, 75.0)


func _is_pistol(id: int) -> bool:
	return id == WeaponDefs.M1911 or id == WeaponDefs.LUGER


func _pick_weapon() -> int:
	var axis: bool = faction == War.AXIS
	match rank:
		R_CONSCRIPT:
			return WeaponDefs.KAR98K if axis else WeaponDefs.M1_GARAND
		R_REGULAR:
			if _rng.randf() < 0.4:
				return WeaponDefs.MP40 if axis else WeaponDefs.THOMPSON
			return WeaponDefs.KAR98K if axis else WeaponDefs.M1_GARAND
		R_VETERAN:
			return WeaponDefs.MP40 if axis else WeaponDefs.THOMPSON
		R_OFFICER:
			# The table now carries the Luger, so the German officer finally
			# gets the sidearm of his own army. The MP40 he was handed instead
			# was only ever a stopgap for the missing entry, and it mattered
			# because the player can walk up to the body and pick the weapon up.
			# Allied officers keep the M1911.
			return WeaponDefs.LUGER if axis else WeaponDefs.M1911
		R_SNIPER:
			# A German marksman without a scope was the same stopgap. The scoped
			# Kar98k shares its ammunition with the plain one, so nothing about
			# the loot economy changes.
			return WeaponDefs.KAR98K_SCOPED if axis else WeaponDefs.SPRINGFIELD
		R_MACHINE_GUNNER:
			return WeaponDefs.MG42 if axis else WeaponDefs.THOMPSON
	return WeaponDefs.KAR98K


func _faction_group() -> String:
	return "axis" if faction == War.AXIS else "allies"


func _hostile_groups() -> PackedStringArray:
	if faction == War.AXIS:
		return PackedStringArray(["player", "allies"])
	return PackedStringArray(["axis"])


# ---------------------------------------------------------------- main loop --

func _physics_process(delta: float) -> void:
	if not _ready_to_run:
		return
	if state == S_DEAD:
		_tick_dead(delta)
		return
	_time += delta
	_tick_far(delta)
	_tick_timers(delta)
	_tick_weapon(delta)
	if not _far:
		_tick_perception(delta)
	_tick_state(delta)
	_tick_locomotion(delta)
	if not _far:
		_tick_animation(delta)


func _tick_far(delta: float) -> void:
	_far_timer -= delta
	if _far_timer > 0.0:
		return
	_far_timer = 0.9 + _rng.randf() * 0.4
	var player := _player_node()
	if player == null:
		_far = false
	else:
		var d := global_position.distance_squared_to(player.global_position)
		_far = d > FAR_DISTANCE * FAR_DISTANCE
	# Sixty skeletons is what the imported models really cost. Past the cut-off
	# the AnimationPlayer is switched off outright, not merely left unticked:
	# unlike the procedural limbs it would otherwise keep posing itself. A
	# corpse mid death clip is exempt, or it would freeze halfway down.
	if _anim != null and not _rig_death:
		_anim.set_active(not _far)


func _tick_timers(delta: float) -> void:
	_reaction_timer = maxf(0.0, _reaction_timer - delta)
	_burst_pause = maxf(0.0, _burst_pause - delta)
	_alert_cry_timer = maxf(0.0, _alert_cry_timer - delta)
	_shout_timer = maxf(0.0, _shout_timer - delta)
	_rallied_timer = maxf(0.0, _rallied_timer - delta)
	_suppression = maxf(0.0, _suppression - SUPPRESS_DECAY * delta)
	if not _target_visible:
		_lost_timer += delta
	if rank == R_OFFICER:
		_officer_timer -= delta
		if _officer_timer <= 0.0:
			_officer_timer = 2.0
			_rally_nearby()


func _tick_weapon(delta: float) -> void:
	if _weapon == null:
		return
	if _weapon.is_reloading:
		_weapon.tick_reload(_now())
	# The AI never runs completely dry: a soldier standing around with an empty
	# rifle reads as a bug, not as a challenge.
	if _weapon.reserve <= 0:
		_weapon.add_ammo(WeaponDefs.magazine(_weapon_id) * 3)


# --------------------------------------------------------------- perception --

func _tick_perception(delta: float) -> void:
	_scan_timer -= delta
	if _scan_timer <= 0.0:
		_scan_timer = 0.45 + _rng.randf() * 0.25
		_refresh_candidates()
	_env_timer -= delta
	if _env_timer <= 0.0:
		_env_timer = 2.0 + _rng.randf()
		_refresh_environment()
	_corpse_timer -= delta
	if _corpse_timer <= 0.0:
		_corpse_timer = 0.2 + _rng.randf() * 0.15
		_check_for_corpses()
	_see_timer -= delta
	if _see_timer > 0.0:
		return
	_see_timer = 0.2 + _rng.randf() * 0.15
	_look_for_targets()


func _refresh_candidates() -> void:
	_candidates.clear()
	var tree := get_tree()
	if tree == null:
		return
	for group_name in _hostile_groups():
		for node in tree.get_nodes_in_group(group_name):
			# Validity is tested before the cast: casting an already freed
			# object is itself the error, so a check on the cast result would
			# come too late.
			if not is_instance_valid(node):
				continue
			var body := node as Node3D
			if body == null:
				continue
			if body == self:
				continue
			if body.has_method("is_alive") and not bool(body.call("is_alive")):
				continue
			if global_position.distance_squared_to(body.global_position) > 300.0 * 300.0:
				continue
			_candidates.append(body)
	_hook_player_fire()


## Listens to the player firing so a near miss can suppress this soldier. There
## is no bullet event bus in the project, so the segment is rebuilt from the
## player eye and aim direction, and the point to segment distance decides.
func _hook_player_fire() -> void:
	if _player_hooked:
		return
	var player := _player_node()
	if player == null or not player.has_signal("fired"):
		return
	if not player.is_connected("fired", Callable(self, "_on_player_fired")):
		player.connect("fired", Callable(self, "_on_player_fired"))
	_player_hooked = true


func _on_player_fired(_fired_weapon: int) -> void:
	if state == S_DEAD or _far or faction != War.AXIS:
		return
	var player := _player_node()
	if player == null:
		return
	var from := player.global_position
	if player.has_method("eye_position"):
		from = player.call("eye_position")
	var dir := -player.global_transform.basis.z
	if player.has_method("aim_direction"):
		dir = player.call("aim_direction")
	var to := from + dir.normalized() * 260.0
	var chest := global_position + Vector3(0.0, 1.0, 0.0)
	if chest.distance_to(from) < 3.0:
		return
	if _point_segment_distance(chest, from, to) > SUPPRESS_RADIUS:
		return
	suppress(0.5)
	if target == null:
		alert_to(from, 0.8)


func _refresh_environment() -> void:
	if _sky_node == null or not is_instance_valid(_sky_node):
		_sky_node = _find_scene_node("Sky", "sky")
	if _weather_node == null or not is_instance_valid(_weather_node):
		_weather_node = _find_scene_node("Weather", "weather")
	_light = 1.0
	if _sky_node != null and _sky_node.has_method("light_level"):
		_light = float(_sky_node.call("light_level"))
	_visibility = 1.0
	if _weather_node != null and _weather_node.has_method("sight_factor"):
		_visibility = float(_weather_node.call("sight_factor"))


func _find_scene_node(node_name: String, group_name: String) -> Node:
	var tree := get_tree()
	if tree == null:
		return null
	var by_group := tree.get_first_node_in_group(group_name)
	if by_group != null:
		return by_group
	var scene := tree.current_scene
	if scene == null:
		return null
	return scene.get_node_or_null(NodePath(node_name))


func _look_for_targets() -> void:
	var eye := eye_position()
	var facing := _facing()
	var base_range := _rank_sight(rank)
	var best: Node3D = null
	var best_score := -1.0e9
	for candidate in _candidates:
		if not is_instance_valid(candidate):
			continue
		if candidate.has_method("is_alive") and not bool(candidate.call("is_alive")):
			continue
		var point := _aim_point_of(candidate)
		if not Senses.can_see(self, eye, facing, candidate, point, base_range,
				_light, _visibility):
			continue
		var distance := global_position.distance_to(candidate.global_position)
		var score := 400.0 - distance
		if candidate.is_in_group("player"):
			score += 140.0
		if candidate == target:
			score += 70.0          # hysteresis, no flickering between targets
		if score > best_score:
			best_score = score
			best = candidate
	if best != null:
		_see_target(best)
	else:
		_target_visible = false


func _see_target(seen: Node3D) -> void:
	var fresh := target != seen or _lost_timer > 3.0
	target = seen
	_last_known = seen.global_position
	_has_last_known = true
	_target_visible = true
	_lost_timer = 0.0
	if fresh:
		_on_fresh_contact(seen)
	if state == S_IDLE or state == S_PATROL or state == S_ALERT or state == S_ADVANCE:
		_enter_state(S_COMBAT)


func _on_fresh_contact(seen: Node3D) -> void:
	_reaction_timer = maxf(_reaction_timer, _reaction_time())
	_aim_converge = 0.0
	_burst_pause = maxf(_burst_pause, 0.15)
	spotted_enemy.emit(self, seen)
	if _alert_cry_timer <= 0.0:
		_alert_cry_timer = 6.0
		Sfx.play_at(_voice_sample("alert"), global_position, -2.0,
				_rng.randf_range(0.94, 1.07))
	if faction == War.AXIS:
		War.raise_alert(War.ALERT_FULL)
	_broadcast_contact(seen)


func _broadcast_contact(seen: Node3D) -> void:
	if _squad != null and is_instance_valid(_squad) and _squad.has_method("report_contact"):
		_squad.call("report_contact", seen, seen.global_position)
		return
	# Lone wolf: shout to whoever is close enough to hear it.
	for friend in _friends_near(SQUAD_VOICE_RANGE * 0.6):
		if friend.has_method("notice_enemy"):
			friend.call("notice_enemy", seen)


# ------------------------------------------------------- corpse discovery --

## The counterweight to the silent takedown. Killing quietly costs nothing on
## its own, so what makes infiltration a game is that the bodies stay where they
## fell and somebody eventually walks past one.
##
## Cost control, because this runs on up to sixty soldiers: it is skipped
## outright for anybody who already has something to shoot at, the candidate
## list is rebuilt roughly once a second instead of every tick, and a single
## line of sight is traced per call. Sixty soldiers with ten bodies on the map
## therefore cost sixty rays every quarter of a second, not six hundred.
func _check_for_corpses() -> void:
	if not is_unaware():
		return
	if _time >= _corpse_scan:
		_corpse_scan = _time + 0.9 + _rng.randf() * 0.5
		_refresh_corpses()
	if _corpses.is_empty():
		return
	_corpse_index = wrapi(_corpse_index + 1, 0, _corpses.size())
	# The entry is read into a Variant and validated BEFORE anything casts it.
	# These are nodes in the middle of freeing themselves, and casting an
	# already freed object is itself the error: a check on the cast result would
	# come far too late.
	var entry: Variant = _corpses[_corpse_index]
	if not is_instance_valid(entry):
		_corpses.remove_at(_corpse_index)
		return
	var corpse := entry as Node3D
	if corpse == null or corpse.has_meta(CORPSE_MARK):
		_corpses.remove_at(_corpse_index)
		return
	if not _corpse_in_sight(corpse):
		return
	_report_corpse(corpse)


## Rebuilds the short list of friendly bodies worth looking at. Bodies already
## reported by anybody are dropped here, which is what keeps the cost flat as
## the campaign piles up casualties.
func _refresh_corpses() -> void:
	_corpses.clear()
	_corpse_index = 0
	var tree := get_tree()
	if tree == null:
		return
	var squared := CORPSE_SIGHT_RANGE * CORPSE_SIGHT_RANGE
	for node in tree.get_nodes_in_group(_faction_group()):
		# Validity is tested before the cast: casting an already freed object is
		# itself the error, so a check on the cast result would come too late.
		# A corpse frees itself half a minute after it falls, so this loop is
		# exactly where a freed node shows up.
		if not is_instance_valid(node):
			continue
		var body := node as Node3D
		if body == null or body == self:
			continue
		if body.has_meta(CORPSE_MARK):
			continue
		if not body.has_method("is_alive") or bool(body.call("is_alive")):
			continue
		if global_position.distance_squared_to(body.global_position) > squared:
			continue
		_corpses.append(body)
		if _corpses.size() >= CORPSE_LIST_MAX:
			return


## True line of sight to a body on the ground, not a plain distance test: a
## corpse behind a wall is not seen.
##
## `Senses.can_see` cannot serve here. It deliberately refuses any target whose
## `is_alive()` reads false, which is every corpse in the project. So the shared
## rules are applied by hand instead: the range comes from
## `Senses.sight_range()` so light and weather still count, the cone is the
## shared `Senses.FOV_HALF`, and the occlusion is one ray on `Layers.SIGHT_MASK`.
func _corpse_in_sight(corpse: Node3D) -> bool:
	var eye := eye_position()
	var point := corpse.global_position + Vector3(0.0, CORPSE_LOOK_HEIGHT, 0.0)
	var to_body := point - eye
	var distance := to_body.length()
	if distance < 0.05:
		return true
	if distance > Senses.sight_range(CORPSE_SIGHT_RANGE, _light, _visibility):
		return false
	if distance > Senses.PERIPHERAL_RADIUS:
		var facing := _facing()
		if facing.length_squared() < 0.000001:
			return false
		if (to_body / distance).dot(facing.normalized()) < cos(Senses.FOV_HALF):
			return false
	var world := get_world_3d()
	if world == null:
		return false
	var space := world.direct_space_state
	if space == null:
		return false
	var query := PhysicsRayQueryParameters3D.create(eye, point, Layers.SIGHT_MASK)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	var excluded: Array[RID] = [get_rid()]
	var corpse_body := corpse as CollisionObject3D
	if corpse_body != null:
		excluded.append(corpse_body.get_rid())
	query.exclude = excluded
	return space.intersect_ray(query).is_empty()


## Finding a body: shout, go and look, put everybody within earshot on the spot
## where it lies, and push the campaign alert up a notch. The marker written on
## the body makes this happen exactly once for that body, whoever walks past it
## afterwards.
##
## The squad is warned with `alert_to` rather than `Squad.report_contact`:
## `report_contact` wants a live enemy, it stores the node as the squad contact
## and hands it to `notice_enemy`, which would lock the whole squad onto a
## corpse as a target it can never see, never shoot and never let go of. What
## the squad has to be told here is a position, and that is what `alert_to`
## carries.
func _report_corpse(corpse: Node3D) -> void:
	corpse.set_meta(CORPSE_MARK, true)
	var at := corpse.global_position
	_last_known = at
	_has_last_known = true
	_search_timer = maxf(_search_timer, _rng.randf_range(SEARCH_MIN, SEARCH_MAX))
	var to_body := at - global_position
	to_body.y = 0.0
	if to_body.length() > 0.2:
		_face_dir = to_body.normalized()
	if state == S_IDLE or state == S_PATROL:
		_enter_state(S_ALERT)
	if _alert_cry_timer <= 0.0:
		_alert_cry_timer = 6.0
		Sfx.play_at(_voice_sample("alert"), global_position, -3.0,
				_rng.randf_range(0.94, 1.07))
	for friend in _friends_near(SQUAD_VOICE_RANGE):
		if friend.has_method("alert_to"):
			friend.call("alert_to", at, 0.85)
	# Only the German side owns the campaign alert level, exactly as in
	# `alert_to` and `_on_fresh_contact`: a maquisard finding one of his own has
	# no way of putting a garrison on edge.
	if faction == War.AXIS:
		War.raise_alert(War.ALERT_SEARCHING)


# ------------------------------------------------------------ state machine --

func _enter_state(new_state: int) -> void:
	if state == new_state or state == S_DEAD:
		return
	state = new_state
	_has_dest = false
	_wants_move = false
	_blind_fire = false
	_stuck_timer = 0.0
	_stuck_ref = global_position
	match state:
		S_IDLE:
			_crouched = false
			_run = false
			_look_timer = _rng.randf_range(1.2, 3.0)
		S_PATROL:
			_crouched = false
			_run = false
		S_ALERT:
			_crouched = rank != R_OFFICER
			_run = false
			if _search_timer <= 0.0:
				_search_timer = _rng.randf_range(SEARCH_MIN, SEARCH_MAX)
		S_COMBAT:
			_run = false
			_crouched = _rng.randf() < 0.35
			_reposition_timer = _rng.randf_range(0.8, 2.2)
		S_COVER:
			_crouched = true
			_peeking = false
			_peek_timer = _rng.randf_range(0.6, 1.6)
		S_ADVANCE:
			_run = _morale > 0.55
			_crouched = false
		S_FLANK:
			_run = true
			_crouched = false
			_pick_flank_destination()
		S_RETREAT:
			_run = true
			_crouched = false
		S_SUPPRESSED:
			_crouched = true
			_run = false
			_peek_timer = _rng.randf_range(0.8, 1.8)
		S_DEAD:
			_crouched = false


func _tick_state(delta: float) -> void:
	_apply_stance()
	match state:
		S_IDLE:
			_state_idle(delta)
		S_PATROL:
			_state_patrol(delta)
		S_ALERT:
			_state_alert(delta)
		S_COMBAT:
			_state_combat(delta)
		S_ADVANCE:
			_state_advance(delta)
		S_COVER:
			_state_cover(delta)
		S_FLANK:
			_state_flank(delta)
		S_RETREAT:
			_state_retreat(delta)
		S_SUPPRESSED:
			_state_suppressed(delta)


func _state_idle(delta: float) -> void:
	# Escorting comes first: a companion at rest keeps station on his man
	# instead of standing on the anchor he was created with.
	if _follow_node != null and _tick_follow(delta):
		return
	if _has_order:
		_go_to(_order_pos, 1.2)
		if global_position.distance_to(_order_pos) < 1.6:
			_has_order = false
		return
	if not _route.is_empty():
		_enter_state(S_PATROL)
		return
	var anchor := _hold_pos
	if global_position.distance_to(anchor) > 3.0:
		_go_to(anchor, 1.2)
		return
	_has_dest = false
	# Standing guard: sweep the surroundings instead of staring at a wall.
	_look_timer -= delta
	if _look_timer <= 0.0:
		_look_timer = _rng.randf_range(2.0, 4.5)
		var angle := _rng.randf_range(-PI, PI)
		_face_dir = Vector3(sin(angle), 0.0, cos(angle))


func _state_patrol(delta: float) -> void:
	if _route.is_empty():
		_enter_state(S_IDLE)
		return
	if _route_wait > 0.0:
		_route_wait -= delta
		_has_dest = false
		return
	_route_index = wrapi(_route_index, 0, _route.size())
	var point := _route[_route_index]
	_go_to(point, 1.8)
	if global_position.distance_to(Vector3(point.x, global_position.y, point.z)) < 1.9:
		_route_index = wrapi(_route_index + 1, 0, _route.size())
		_route_wait = _rng.randf_range(0.4, 2.0)
		_has_dest = false


func _state_alert(delta: float) -> void:
	if _target_visible and target != null:
		_enter_state(S_COMBAT)
		return
	_search_timer -= delta
	if _search_timer <= 0.0:
		_has_last_known = false
		_search_timer = 0.0
		_enter_state(S_PATROL if not _route.is_empty() else S_IDLE)
		return
	if not _has_last_known:
		_enter_state(S_IDLE)
		return
	var flat_distance := _flat_distance(_last_known)
	if flat_distance > 3.0:
		# Careful approach: crouched, weapon up, no sprint into the unknown.
		_go_to(_last_known, 2.0)
		_face_dir = (_last_known - global_position).normalized()
	else:
		_has_dest = false
		_look_timer -= delta
		if _look_timer <= 0.0:
			_look_timer = _rng.randf_range(1.2, 2.6)
			var sweep := _rng.randf_range(-1.3, 1.3)
			_face_dir = _face_dir.rotated(Vector3.UP, sweep)
			# Nervous soldiers drift around the noise instead of freezing.
			if _rng.randf() < 0.5:
				var offset := Vector3(_rng.randf_range(-6.0, 6.0), 0.0,
						_rng.randf_range(-6.0, 6.0))
				_go_to(_last_known + offset, 1.5)


func _state_combat(delta: float) -> void:
	if target == null or not is_instance_valid(target):
		target = null
		_enter_state(S_ALERT)
		return
	if _should_retreat():
		_enter_state(S_RETREAT)
		return
	if _suppression > SUPPRESS_TRIGGER:
		_enter_state(S_SUPPRESSED)
		return
	if _weapon != null and _weapon.needs_reload() and not _weapon.is_reloading:
		# Reloading in the open is how conscripts die. Duck first when possible.
		if _seek_cover(_threat_point(), 22.0):
			_enter_state(S_COVER)
			return
		_begin_reload()
	if not _target_visible:
		if _lost_timer > 1.3:
			_enter_state(S_ADVANCE)
		else:
			_face_dir = (_last_known - global_position).normalized()
		return

	_face_dir = (target.global_position - global_position).normalized()
	_aim_converge = minf(1.0, _aim_converge + _rank_converge(rank) * delta
			* (1.25 if _rallied_timer > 0.0 else 1.0))
	_try_fire(false)
	_occasional_shout()

	# Movement: sidestep, close in or back off depending on the weapon.
	_reposition_timer -= delta
	if _reposition_timer <= 0.0:
		_reposition_timer = _rng.randf_range(1.6, 3.4)
		if _role == ROLE_FLANK and rank == R_VETERAN and _rng.randf() < 0.7:
			_enter_state(S_FLANK)
			return
		if rank == R_SNIPER or rank == R_MACHINE_GUNNER:
			_has_dest = false          # posted weapons stay posted
			return
		if _rng.randf() < 0.35 and _seek_cover(_threat_point(), 18.0):
			_enter_state(S_COVER)
			return
		_pick_combat_step()


func _pick_combat_step() -> void:
	if target == null:
		return
	var to_target := target.global_position - global_position
	to_target.y = 0.0
	var distance := to_target.length()
	if distance < 0.5:
		return
	var forward := to_target / distance
	var side := forward.cross(Vector3.UP)
	var band := _preferred_range()
	var step := side * _rng.randf_range(2.5, 6.0) * (1.0 if _rng.randf() < 0.5 else -1.0)
	if distance > band.y:
		step += forward * _rng.randf_range(5.0, 12.0)
	elif distance < band.x:
		step -= forward * _rng.randf_range(3.0, 7.0)
	_go_to(global_position + step, 1.3)
	_run = distance > band.y


func _state_advance(delta: float) -> void:
	if _target_visible and target != null:
		_enter_state(S_COMBAT)
		return
	if _suppression > SUPPRESS_TRIGGER:
		_enter_state(S_SUPPRESSED)
		return
	if _weapon != null and _weapon.needs_reload() and not _weapon.is_reloading:
		_begin_reload()
	if _has_order:
		_go_to(_order_pos, 1.6)
		if _flat_distance(_order_pos) < 2.0:
			_has_order = false
			_enter_state(S_ALERT)
		return
	if not _has_last_known:
		_enter_state(S_PATROL if not _route.is_empty() else S_IDLE)
		return
	_search_timer = maxf(_search_timer, 1.0)
	var distance := _flat_distance(_last_known)
	if distance < 2.5:
		_search_timer = _rng.randf_range(SEARCH_MIN, SEARCH_MAX)
		_enter_state(S_ALERT)
		return
	# Bound from cover to cover instead of walking a straight line.
	if not _has_dest:
		var stage := _intermediate_cover(_last_known)
		_go_to(stage, 1.6)
	_face_dir = (_last_known - global_position).normalized()
	if _lost_timer > 30.0:
		_has_last_known = false


## A waypoint on the way to `goal` that uses a cover point when one lies
## roughly in the right direction, so the advance zigzags like a real bound.
func _intermediate_cover(goal: Vector3) -> Vector3:
	var best := goal
	var best_score := -1.0e9
	var here := global_position
	var goal_distance := here.distance_to(goal)
	for point in _cover:
		var pos: Vector3 = point.position
		var to_point := pos - here
		var d := to_point.length()
		if d < 3.0 or d > minf(28.0, goal_distance):
			continue
		if pos.distance_to(goal) > goal_distance - 2.0:
			continue        # not actually progressing
		var score := 30.0 - pos.distance_to(goal) * 0.4 - d * 0.2
		if bool(point.is_high):
			score += 4.0
		if score > best_score:
			best_score = score
			best = pos
	return best


func _state_cover(delta: float) -> void:
	if _should_retreat():
		_enter_state(S_RETREAT)
		return
	if not _has_cover:
		_enter_state(S_COMBAT if _target_visible else S_ADVANCE)
		return
	var distance := _flat_distance(_cover_pos)
	if distance > 1.4:
		_go_to(_cover_pos, 1.0)
		return
	_has_dest = false
	if target != null and is_instance_valid(target):
		_face_dir = (_threat_point() - global_position).normalized()
	if _weapon != null and _weapon.needs_reload() and not _weapon.is_reloading:
		_crouched = true
		_peeking = false
		_begin_reload()
		_peek_timer = maxf(_peek_timer, WeaponDefs.reload_time(_weapon_id))
		return
	_peek_timer -= delta
	if _peek_timer <= 0.0:
		_peeking = not _peeking
		_peek_timer = _rng.randf_range(0.8, 1.6) if _peeking else _rng.randf_range(1.0, 2.2)
		if _peeking:
			_aim_converge = maxf(0.0, _aim_converge - 0.35)
	_crouched = not _peeking
	if _peeking:
		_aim_converge = minf(1.0, _aim_converge + _rank_converge(rank) * delta)
		if _target_visible:
			_try_fire(false)
			_occasional_shout()
		elif _has_last_known and _lost_timer < 6.0 and _rng.randf() < 0.25:
			_try_fire(true)
	if not _target_visible and _lost_timer > 8.0:
		_enter_state(S_ADVANCE)


func _state_flank(delta: float) -> void:
	if _suppression > SUPPRESS_TRIGGER:
		_enter_state(S_SUPPRESSED)
		return
	if _target_visible and target != null:
		var distance := global_position.distance_to(target.global_position)
		if distance < _preferred_range().y * 0.8:
			_enter_state(S_COMBAT)
			return
		_try_fire(false)
	if not _has_dest:
		_pick_flank_destination()
	if _flat_distance(_dest) < 2.2:
		_enter_state(S_COMBAT if _target_visible else S_ADVANCE)
		return
	if _lost_timer > 22.0:
		_enter_state(S_ADVANCE)


func _pick_flank_destination() -> void:
	var anchor := _last_known if _has_last_known else global_position
	if target != null and is_instance_valid(target):
		anchor = target.global_position
	var to_anchor := anchor - global_position
	to_anchor.y = 0.0
	if to_anchor.length() < 1.0:
		to_anchor = Vector3.FORWARD
	var side := to_anchor.normalized().cross(Vector3.UP)
	var sign_side := 1.0 if _rng.randf() < 0.5 else -1.0
	var lateral := side * sign_side * _rng.randf_range(12.0, 26.0)
	_go_to(anchor + lateral - to_anchor.normalized() * _rng.randf_range(4.0, 12.0), 2.0)


func _state_retreat(delta: float) -> void:
	var threat := _threat_point()
	if not _has_dest or _flat_distance(_dest) < 2.5:
		var away := global_position - threat
		away.y = 0.0
		if away.length() < 1.0:
			away = -_facing()
		var goal := global_position + away.normalized() * 18.0
		# Fall back towards friendly ground when there is any.
		if _home.distance_to(global_position) > 6.0:
			goal = goal.lerp(_home, 0.4)
		_go_to(goal, 2.0)
	# Fire back over the shoulder now and then.
	if _target_visible and _rng.randf() < 0.03:
		_face_dir = (threat - global_position).normalized()
		_try_fire(false)
	else:
		_face_dir = velocity
		_face_dir.y = 0.0
	if global_position.distance_to(threat) > 45.0 or _friends_near(14.0).size() >= 2:
		_morale = minf(1.0, _morale + 0.25)
		if _seek_cover(threat, 25.0):
			_enter_state(S_COVER)
		else:
			_enter_state(S_ALERT)


func _state_suppressed(delta: float) -> void:
	_crouched = true
	_has_dest = false
	if _has_cover and _flat_distance(_cover_pos) > 1.5:
		_go_to(_cover_pos, 1.0)
	elif not _has_cover and _seek_cover(_threat_point(), 14.0):
		_go_to(_cover_pos, 1.0)
	_face_dir = (_threat_point() - global_position).normalized()
	if _weapon != null and _weapon.needs_reload() and not _weapon.is_reloading:
		_begin_reload()
	_peek_timer -= delta
	if _peek_timer <= 0.0:
		_peek_timer = _rng.randf_range(0.9, 2.0)
		# Blind fire: head down, weapon over the sandbags, no accuracy at all.
		_try_fire(true)
	if _suppression < 0.3:
		_enter_state(S_COMBAT if _target_visible else S_COVER if _has_cover else S_ALERT)


func _should_retreat() -> bool:
	if rank == R_VETERAN or rank == R_MACHINE_GUNNER:
		return health < _rank_health(rank) * 0.18 and _friends_near(18.0).is_empty()
	var threshold := 0.3
	if rank == R_CONSCRIPT:
		threshold = 0.45
	if _morale < 0.3:
		threshold += 0.15
	return health < _rank_health(rank) * threshold and _friends_near(20.0).is_empty()


func _occasional_shout() -> void:
	if _shout_timer > 0.0:
		return
	_shout_timer = _rng.randf_range(7.0, 16.0)
	if _rng.randf() < 0.55:
		Sfx.play_at(_voice_sample("shout"), global_position, -4.0,
				_rng.randf_range(0.93, 1.08))


func _voice_sample(kind: String) -> String:
	if faction == War.AXIS:
		match kind:
			"alert":
				return "german_alert"
			"shout":
				return "german_shout"
			_:
				return "german_death"
	match kind:
		"alert":
			return "french_go"
		"shout":
			return "french_ok"
		_:
			return "death"


# -------------------------------------------------------------------- fire --

func _reaction_time() -> float:
	var base := _rank_reaction(rank)
	var accuracy := maxf(0.3, Game.enemy_accuracy_scale())
	var value := base * _rng.randf_range(0.85, 1.2) / accuracy
	value *= lerpf(1.25, 0.9, clampf(_morale, 0.0, 1.0))
	return clampf(value, 0.35, 1.4)


func _burst_size() -> int:
	if not WeaponDefs.is_automatic(_weapon_id):
		return 1
	if rank == R_MACHINE_GUNNER:
		return _rng.randi_range(8, 16)
	return _rng.randi_range(3, 6)


func _burst_gap() -> float:
	if not WeaponDefs.is_automatic(_weapon_id):
		# Working a bolt takes a moment, and so does re acquiring the sights.
		return _rng.randf_range(1.0, 1.8) * (0.7 if rank == R_VETERAN else 1.0)
	if rank == R_MACHINE_GUNNER:
		return _rng.randf_range(0.8, 1.8)
	return _rng.randf_range(0.4, 1.2)


## Cone half angle for the next shot. Never zero: the AI must never be perfect.
func _shot_spread(distance: float, blind: bool) -> float:
	var spread := lerpf(_rank_spread(rank) * 4.2, _rank_spread(rank),
			clampf(_aim_converge, 0.0, 1.0))
	if _shots_in_burst == 0:
		spread *= 1.9                                  # first round of a burst
	spread *= 1.0 + clampf((distance - 25.0) / 110.0, 0.0, 1.3)
	spread *= 1.0 + _target_lateral_speed() * 0.10
	spread *= 1.0 + _suppression * 0.9
	spread *= lerpf(1.55, 0.85, clampf(_morale, 0.0, 1.0))
	if _rallied_timer > 0.0:
		spread *= 0.82
	if _crouched:
		spread *= 0.85
	if Vector2(velocity.x, velocity.z).length() > 0.6:
		spread *= 1.4
	if blind:
		spread *= 3.4
	spread /= maxf(0.3, Game.enemy_accuracy_scale())
	return maxf(0.0045, spread)


func _target_lateral_speed() -> float:
	if target == null or not is_instance_valid(target):
		return 0.0
	if not ("velocity" in target):
		return 0.0
	var vel: Vector3 = target.get("velocity")
	var to_target := target.global_position - global_position
	to_target.y = 0.0
	if to_target.length() < 0.1:
		return 0.0
	var side := to_target.normalized().cross(Vector3.UP)
	return absf(vel.dot(side))


func _try_fire(blind: bool) -> void:
	if _weapon == null or _reaction_timer > 0.0 or _burst_pause > 0.0:
		return
	if _weapon.is_reloading:
		return
	if _weapon.needs_reload():
		_begin_reload()
		return
	var aim_point := Vector3.ZERO
	if _target_visible and target != null and is_instance_valid(target):
		aim_point = _aim_point_of(target)
	elif blind and _has_last_known:
		aim_point = _last_known + Vector3(0.0, 1.0, 0.0)
	else:
		return
	var muzzle := _muzzle_position()
	var to_aim := aim_point - muzzle
	var distance := to_aim.length()
	if distance < 0.3:
		return
	var direction := to_aim / distance
	# Never shoot through a friend standing in the way.
	if not blind and _friendly_in_line(muzzle, direction, distance):
		_reposition_timer = minf(_reposition_timer, 0.2)
		return
	var now := _now()
	if not _weapon.can_fire(now):
		return
	if not _weapon.fire(now):
		return
	if _burst_left <= 0:
		_burst_left = _burst_size()
		_shots_in_burst = 0
	var spread := _shot_spread(distance, blind or not _target_visible)
	var result = Ballistics.fire(get_world_3d(), muzzle, direction, _weapon_id,
			spread, self, _rng)
	_shots_in_burst += 1
	_burst_left -= 1
	if _burst_left <= 0:
		_burst_pause = _burst_gap()
		_shots_in_burst = 0
	if _anim != null:
		_anim.fire(Vector2(velocity.x, velocity.z).length())
	Sfx.play_shot(WeaponDefs.fire_sample(_weapon_id), muzzle)
	var vfx := _vfx()
	if vfx != null:
		vfx.call("muzzle_flash", muzzle, direction, 1.0)
		var end_point := muzzle + direction * 120.0
		if result != null and bool(result.hit):
			end_point = result.position
		# The sniper gives himself away with a bright tracer, as asked.
		if rank == R_SNIPER or WeaponDefs.is_automatic(_weapon_id) or _rng.randf() < 0.3:
			vfx.call("tracer", muzzle, end_point, WeaponDefs.muzzle_velocity(_weapon_id))
	fired_shot.emit(self)
	_suppress_along(muzzle, muzzle + direction * 140.0)


## A shot that goes past somebody at less than 1.5 m pins him down. Cheap point
## to segment test, throttled so it never runs more than a few times a second.
func _suppress_along(from: Vector3, to: Vector3) -> void:
	if _far:
		return
	var tree := get_tree()
	if tree == null:
		return
	for group_name in _hostile_groups():
		for node in tree.get_nodes_in_group(group_name):
			if not is_instance_valid(node):
				continue
			var body := node as Node3D
			if body == null:
				continue
			if not body.has_method("suppress"):
				continue
			var chest := body.global_position + Vector3(0.0, 1.0, 0.0)
			if _point_segment_distance(chest, from, to) <= SUPPRESS_RADIUS:
				body.call("suppress", 0.4)


func _friendly_in_line(from: Vector3, direction: Vector3, distance: float) -> bool:
	for friend in _friends_near(minf(distance, 40.0)):
		var chest := friend.global_position + Vector3(0.0, 1.0, 0.0)
		var to_friend := chest - from
		var along := to_friend.dot(direction)
		if along <= 0.5 or along >= distance:
			continue
		if (to_friend - direction * along).length() < 0.8:
			return true
	return false


func _begin_reload() -> void:
	if _weapon == null or _weapon.is_reloading or not _weapon.can_reload():
		return
	var duration := _weapon.start_reload(_now())
	if duration <= 0.0:
		return
	Sfx.play_at(WeaponDefs.reload_sample(_weapon_id), global_position, -6.0)
	_aim_converge = maxf(0.0, _aim_converge - 0.5)
	_burst_pause = maxf(_burst_pause, duration)


func _muzzle_position() -> Vector3:
	var forward := _facing()
	if _weapon_node != null and is_instance_valid(_weapon_node):
		return _weapon_node.global_position + forward * 0.35
	return eye_position() + forward * 0.4 - Vector3(0.0, 0.12, 0.0)


func _aim_point_of(node: Node3D) -> Vector3:
	if node.has_method("head_height"):
		var head_y := float(node.call("head_height"))
		return Vector3(node.global_position.x, head_y - 0.25, node.global_position.z)
	return node.global_position + Vector3(0.0, 1.2, 0.0)


func _threat_point() -> Vector3:
	if target != null and is_instance_valid(target):
		return target.global_position
	if _has_last_known:
		return _last_known
	return global_position - _facing() * 10.0


# -------------------------------------------------------------- locomotion --

func _go_to(pos: Vector3, tolerance: float) -> void:
	_dest = pos
	if _world != null:
		_dest.y = _world.ground_y(pos.x, pos.z)
	_dest = Heightfield.clamp_to_bounds(_dest)
	_dest_tolerance = tolerance
	_has_dest = true


## One escort step. Returns false when there is nobody left to follow, so the
## caller falls back on the ordinary at rest behaviour.
##
## Two things make this read as an escort rather than as a magnet. The soldier
## aims at a slot beside the man he follows, rotated by a small angle drawn once
## at creation, so two companions do not end up in the same footprint. And the
## band between "start walking" and "stop walking" is wide: he sets off only
## past `_follow_distance`, and stops well inside it, which is what keeps him
## from shuffling in circles around somebody standing still.
func _tick_follow(delta: float) -> bool:
	if not is_instance_valid(_follow_node):
		_follow_node = null
		_follow_moving = false
		return false
	var lead := _follow_node.global_position
	var flat := _flat_distance(lead)
	if _follow_moving:
		if flat <= _follow_distance * FOLLOW_STOP_FACTOR:
			_follow_moving = false
	elif flat > _follow_distance:
		_follow_moving = true

	if not _follow_moving:
		# Close enough. Stand still and watch the surroundings instead of
		# treading on the heels of the man in front.
		_run = false
		_has_dest = false
		_look_timer -= delta
		if _look_timer <= 0.0:
			_look_timer = _rng.randf_range(1.6, 3.4)
			var angle := _rng.randf_range(-PI, PI)
			_face_dir = Vector3(sin(angle), 0.0, cos(angle))
		return true

	var back := global_position - lead
	back.y = 0.0
	if back.length() < 0.5:
		back = -_facing()
		back.y = 0.0
	if back.length() < 0.01:
		back = Vector3.BACK
	var slot := back.normalized().rotated(Vector3.UP, _follow_angle)
	var goal := lead + slot * (_follow_distance * FOLLOW_STOP_FACTOR)
	_crouched = false
	_run = flat > _follow_distance * FOLLOW_RUN_FACTOR
	_go_to(goal, maxf(1.0, _follow_distance * 0.3))
	var to_goal := goal - global_position
	to_goal.y = 0.0
	if to_goal.length() > 0.2:
		_face_dir = to_goal.normalized()
	return true


func _flat_distance(pos: Vector3) -> float:
	return Vector2(pos.x - global_position.x, pos.z - global_position.z).length()


func _current_speed() -> float:
	if _crouched:
		return CROUCH_SPEED
	if _run:
		return RUN_SPEED * lerpf(0.85, 1.0, clampf(_morale, 0.0, 1.0))
	return WALK_SPEED


func _tick_locomotion(delta: float) -> void:
	_wants_move = false
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = -1.0        # keeps the snap glued to slopes

	var planar := Vector3.ZERO
	if _has_dest:
		var to_dest := Vector3(_dest.x - global_position.x, 0.0, _dest.z - global_position.z)
		var distance := to_dest.length()
		if distance <= _dest_tolerance:
			_has_dest = false
		else:
			var direction := to_dest / distance
			direction = _avoid(direction, delta)
			planar = direction * _current_speed()
			_wants_move = true
			if _face_dir.length_squared() < 0.01 or state == S_PATROL or state == S_ADVANCE:
				_face_dir = direction
	velocity.x = planar.x
	velocity.z = planar.z
	move_and_slide()
	_ground_guard()
	_tick_stuck(delta)
	_tick_facing(delta)


## Three whiskers from the eyes: forward, forward left, forward right. When the
## middle one is blocked, steer towards the side that has the most room. The
## chosen side sticks for a moment so the soldier does not oscillate.
func _avoid(direction: Vector3, delta: float) -> Vector3:
	_avoid_timer -= delta
	if _avoid_timer > 0.0 and _avoid_dir.length_squared() > 0.01:
		return _avoid_dir
	_avoid_timer = AVOID_INTERVAL
	var world := get_world_3d()
	if world == null:
		_avoid_dir = direction
		return direction
	var space := world.direct_space_state
	if space == null:
		_avoid_dir = direction
		return direction
	var from := global_position + Vector3(0.0, 1.05, 0.0)
	var centre := _whisker(space, from, direction)
	if centre >= WHISKER_LENGTH:
		_avoid_dir = direction
		return direction
	var left_dir := direction.rotated(Vector3.UP, WHISKER_ANGLE)
	var right_dir := direction.rotated(Vector3.UP, -WHISKER_ANGLE)
	var left := _whisker(space, from, left_dir)
	var right := _whisker(space, from, right_dir)
	if left < 1.2 and right < 1.2:
		# Dead end: turn hard on the side we already committed to.
		_avoid_dir = direction.rotated(Vector3.UP, _avoid_side * 1.6).normalized()
		return _avoid_dir
	if left >= right:
		_avoid_side = 1.0
		_avoid_dir = left_dir.lerp(direction, 0.2).normalized()
	else:
		_avoid_side = -1.0
		_avoid_dir = right_dir.lerp(direction, 0.2).normalized()
	return _avoid_dir


func _whisker(space: PhysicsDirectSpaceState3D, from: Vector3, direction: Vector3) -> float:
	var to := from + direction.normalized() * WHISKER_LENGTH
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.SIGHT_MASK)
	query.exclude = [get_rid()]
	var hit := space.intersect_ray(query)
	if hit.is_empty():
		return WHISKER_LENGTH
	var point: Vector3 = hit.get("position", to)
	return from.distance_to(point)


## Keeps a soldier from falling through a chunk whose collision is not streamed
## in yet. Only fires while actually falling, so a soldier in a trench or in a
## cellar is left alone.
func _ground_guard() -> void:
	if _world == null:
		return
	if is_on_floor() or velocity.y > -2.0:
		return
	var ground := _world.ground_y(global_position.x, global_position.z)
	if global_position.y < ground - 0.5:
		var fixed := global_position
		fixed.y = ground + 0.05
		global_position = fixed
		velocity.y = 0.0


func _tick_stuck(delta: float) -> void:
	if not _wants_move:
		_stuck_timer = 0.0
		_stuck_ref = global_position
		return
	_stuck_timer += delta
	if _stuck_timer < STUCK_WINDOW:
		return
	var travelled := Vector2(global_position.x - _stuck_ref.x,
			global_position.z - _stuck_ref.z).length()
	_stuck_timer = 0.0
	_stuck_ref = global_position
	if travelled >= STUCK_DISTANCE:
		_stuck_fails = 0
		return
	_stuck_fails += 1
	_has_dest = false
	_avoid_dir = Vector3.ZERO
	_avoid_side = -_avoid_side
	if _stuck_fails >= MAX_STUCK_FAILS:
		_stuck_fails = 0
		_teleport_home()


func _teleport_home() -> void:
	var pos := _home
	# An escort's anchor is wherever the man he follows stands right now.
	# Snapping a companion back to a village he left ten minutes ago would just
	# lose him for good.
	if _follow_node != null and is_instance_valid(_follow_node):
		pos = _follow_node.global_position
	if _world != null:
		pos.y = _world.ground_y(pos.x, pos.z) + 0.1
	_place(Heightfield.clamp_to_bounds(pos))
	velocity = Vector3.ZERO
	_has_dest = false
	_route_wait = 0.5


func _place(pos: Vector3) -> void:
	if is_inside_tree():
		global_position = pos
	else:
		position = pos


func _tick_facing(delta: float) -> void:
	var flat := Vector3(_face_dir.x, 0.0, _face_dir.z)
	if flat.length_squared() < 0.0004:
		return
	flat = flat.normalized()
	var wanted := atan2(-flat.x, -flat.z)
	rotation.y = lerp_angle(rotation.y, wanted, clampf(TURN_SPEED * delta, 0.0, 1.0))


func _apply_stance() -> void:
	if _capsule == null:
		return
	var wanted_height := CROUCH_BODY_HEIGHT if _crouched else BODY_HEIGHT
	if not is_equal_approx(_capsule.height, wanted_height):
		_capsule.height = wanted_height
		_shape.position.y = wanted_height * 0.5


# --------------------------------------------------------------- animation --

func _tick_animation(delta: float) -> void:
	if _body == null or not is_instance_valid(_body):
		return
	var horizontal := Vector2(velocity.x, velocity.z).length()
	if _anim != null:
		_tick_rig(horizontal, delta)
		return
	_anim_phase += delta * (2.4 + horizontal * 2.1)
	var amplitude := clampf(horizontal / RUN_SPEED, 0.0, 1.0)
	var swing := sin(_anim_phase) * 0.78 * amplitude

	if _leg_l != null:
		_leg_l.rotation.x = swing + (0.55 if _crouched else 0.0)
	if _leg_r != null:
		_leg_r.rotation.x = -swing + (0.55 if _crouched else 0.0)

	var aiming := _target_visible and (state == S_COMBAT or state == S_COVER
			or state == S_FLANK or state == S_RETREAT)
	var aim_pitch := 0.0
	if target != null and is_instance_valid(target):
		var to_target := target.global_position - eye_position()
		var flat := Vector2(to_target.x, to_target.z).length()
		aim_pitch = atan2(to_target.y, maxf(0.2, flat))
		aim_pitch = clampf(aim_pitch, -0.7, 0.7)

	if _arm_r != null:
		if aiming or state == S_ALERT or state == S_SUPPRESSED:
			_arm_r.rotation.x = lerpf(_arm_r.rotation.x, -1.45 + aim_pitch, 8.0 * delta)
			_arm_r.rotation.z = lerpf(_arm_r.rotation.z, -0.12, 8.0 * delta)
		else:
			_arm_r.rotation.x = lerpf(_arm_r.rotation.x, -swing * 0.55, 8.0 * delta)
			_arm_r.rotation.z = lerpf(_arm_r.rotation.z, 0.0, 8.0 * delta)
	if _arm_l != null:
		if aiming or state == S_ALERT or state == S_SUPPRESSED:
			_arm_l.rotation.x = lerpf(_arm_l.rotation.x, -1.25 + aim_pitch, 8.0 * delta)
			_arm_l.rotation.z = lerpf(_arm_l.rotation.z, 0.22, 8.0 * delta)
		else:
			_arm_l.rotation.x = lerpf(_arm_l.rotation.x, swing * 0.55, 8.0 * delta)
			_arm_l.rotation.z = lerpf(_arm_l.rotation.z, 0.0, 8.0 * delta)

	if _torso != null:
		var twist := 0.0
		if target != null and is_instance_valid(target):
			var local := to_local(target.global_position)
			twist = clampf(atan2(-local.x, -local.z), -0.9, 0.9)
		_torso.rotation.y = lerpf(_torso.rotation.y, twist, 6.0 * delta)
		_torso.rotation.x = lerpf(_torso.rotation.x,
				(0.35 if _crouched else 0.0) + (0.2 if aiming else 0.0), 6.0 * delta)
	if _head != null:
		_head.rotation.x = lerpf(_head.rotation.x, -aim_pitch * 0.6, 6.0 * delta)
	if _weapon_node != null and _weapon_node.get_parent() == _body:
		_weapon_node.rotation.x = lerpf(_weapon_node.rotation.x,
				aim_pitch if aiming else -0.35, 8.0 * delta)

	var wanted_y := -0.42 if _crouched else 0.0
	_body_y = lerpf(_body_y, wanted_y, 8.0 * delta)
	_body.position.y = _body_y


## Imported model: the clips own the pose, so the only thing left to choose is
## which clip, and to keep the crouch offset the capsule applies anyway.
##
## Known gap: neither rig ships a crouch pose. The body is sunk by the same
## 0.42 m the box soldier used, which keeps the head near the crouched headshot
## line, but the feet go under the ground and the legs stay straight. Fixing it
## properly needs a crouch clip, not more code here.
func _tick_rig(speed: float, delta: float) -> void:
	var aiming := _target_visible and (state == S_COMBAT or state == S_COVER
			or state == S_FLANK or state == S_RETREAT)
	_anim.locomotion(speed, aiming or state == S_ALERT or state == S_SUPPRESSED,
			delta)
	var wanted_y := -0.42 if _crouched else 0.0
	_body_y = lerpf(_body_y, wanted_y, 8.0 * delta)
	_body.position.y = _body_y


# ------------------------------------------------------------------ damage --

## Contract shared by every damageable in the project. See section 3.
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void:
	if state == S_DEAD or amount <= 0.0:
		return
	health -= amount
	_suppression = minf(2.0, _suppression + 0.35)
	_morale = maxf(0.0, _morale - (0.12 if headshot else 0.06))
	_aim_converge = maxf(0.0, _aim_converge - 0.4)
	var vfx := _vfx()
	if vfx != null:
		var normal := Vector3.UP
		if attacker != null and attacker is Node3D:
			normal = ((attacker as Node3D).global_position - hit_point).normalized()
		vfx.call("blood", hit_point, normal)
	if health <= 0.0:
		_die(attacker)
		return
	if _anim != null and not _far:
		_anim.hit()
	Sfx.play_at("hurt", global_position, -6.0, _rng.randf_range(0.9, 1.1))
	# Being shot at from an unseen direction is the classic way of learning
	# where the enemy is.
	# Validity is tested before the cast: casting an already freed object is
	# itself the error, so a check on the cast result would come too late.
	var source: Node3D = null
	if is_instance_valid(attacker):
		source = attacker as Node3D
	if source != null:
		_last_known = source.global_position
		_has_last_known = true
		_search_timer = _rng.randf_range(SEARCH_MIN, SEARCH_MAX)
		if target == null and _is_hostile(source):
			target = source
			_reaction_timer = maxf(_reaction_timer, _reaction_time() * 0.8)
	if state == S_IDLE or state == S_PATROL:
		if _seek_cover(_threat_point(), 16.0):
			_enter_state(S_COVER)
		else:
			_enter_state(S_ALERT)
	elif _should_retreat():
		_enter_state(S_RETREAT)


func _is_hostile(node: Node3D) -> bool:
	for group_name in _hostile_groups():
		if node.is_in_group(group_name):
			return true
	return false


func _die(killer: Node) -> void:
	health = 0.0
	target = null
	_target_visible = false
	_has_dest = false
	state = S_DEAD
	velocity = Vector3.ZERO
	remove_from_group("damageable")
	collision_layer = 0
	collision_mask = Layers.TERRAIN
	_dead_time = 0.0
	_fall_angle = 0.0
	_follow_node = null
	_follow_moving = false
	_corpses.clear()
	var roll := _rng.randf_range(-0.5, 0.5)
	_fall_axis = Vector3(1.0, 0.0, roll).normalized()
	if _rng.randf() < 0.5:
		_fall_axis = -_fall_axis
	# A rig with a death clip plays it and keeps the last frame. One without,
	# like the zombie, says so and leaves the tip-over below to do the job.
	if _anim != null:
		_anim.set_active(true)
		_rig_death = _anim.die()
	if _silent_death:
		# A takedown from behind: barely a groan, twelve decibels down, so the
		# kill still reads on screen without carrying past a couple of metres.
		Sfx.play_at("hurt", global_position, -12.0, _rng.randf_range(0.88, 0.98))
	else:
		Sfx.play_at(_voice_sample("death"), global_position, -1.0,
				_rng.randf_range(0.92, 1.06))
	_drop_weapon()
	if rank == R_OFFICER:
		_drop_intel()
		# Morale only shatters over an officer somebody actually saw go down.
		# A knife in the dark takes no spine out of anybody, which is the whole
		# point of doing it in the dark.
		if not _silent_death:
			_panic_nearby()
	died.emit(self)


## Killing the officer takes the spine out of the conscripts around him.
func _panic_nearby() -> void:
	for friend in _friends_near(RALLY_RADIUS):
		if not friend.has_method("shatter_morale"):
			continue
		friend.call("shatter_morale", 0.5)


## Called on nearby friends when their officer dies.
func shatter_morale(amount: float) -> void:
	if state == S_DEAD:
		return
	_morale = maxf(0.0, _morale - amount)
	if rank == R_CONSCRIPT and _morale < 0.35:
		_enter_state(S_RETREAT)


## Officers keep the men steady: more morale, tighter aim, in a 25 m radius.
func _rally_nearby() -> void:
	if _far:
		return
	for friend in _friends_near(RALLY_RADIUS):
		if friend.has_method("receive_rally"):
			friend.call("receive_rally", 0.04)


## Called by a nearby officer.
func receive_rally(amount: float) -> void:
	if state == S_DEAD:
		return
	_morale = minf(1.0, _morale + amount)
	_rallied_timer = 3.5


func _drop_weapon() -> void:
	if _weapon_id < 0:
		return
	var pickup := Node3D.new()
	pickup.name = "ArmeAuSol"
	pickup.add_to_group("pickup")
	pickup.set_meta("weapon_id", _weapon_id)
	var rounds := WeaponDefs.magazine(_weapon_id)
	if _weapon != null:
		rounds = maxi(1, _weapon.in_magazine + mini(_weapon.reserve,
				WeaponDefs.magazine(_weapon_id)))
	pickup.set_meta("ammo", rounds)
	pickup.set_meta("surface", "metal")
	var mesh := MeshInstance3D.new()
	mesh.mesh = Meshes.weapon_model(_weapon_id)
	mesh.rotation = Vector3(0.0, 0.0, PI * 0.5)
	pickup.add_child(mesh)
	var area := Area3D.new()
	area.collision_layer = Layers.TRIGGER
	area.collision_mask = Layers.PLAYER
	var area_shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.9
	area_shape.shape = sphere
	area.add_child(area_shape)
	pickup.add_child(area)
	var host := get_parent()
	var tree := get_tree()
	if tree != null and tree.current_scene != null:
		host = tree.current_scene
	if host == null:
		pickup.free()
		return
	var pos := global_position
	if _world != null:
		pos.y = _world.ground_y(pos.x, pos.z) + 0.08
	host.add_child.call_deferred(pickup)
	pickup.set_deferred("global_position", pos)
	pickup.set_deferred("rotation", Vector3(0.0, _rng.randf_range(-PI, PI), 0.0))


## An officer carries his orders on him. The map case lands beside his weapon
## and carries the id of the site he was posted to, which is what the player
## cashes in to reveal that garrison. The site stays on the node rather than on
## a lookup table so a body can outlive the squad that spawned it.
func _drop_intel() -> void:
	var pickup := Node3D.new()
	pickup.name = "DocumentsOfficier"
	pickup.add_to_group("pickup")
	pickup.set_meta("intel_site", home_site())
	pickup.set_meta("prompt", "Ramasser les documents [E]")
	pickup.set_meta("surface", "wood")
	var mesh := MeshInstance3D.new()
	mesh.mesh = Meshes.box(Vector3(0.28, 0.07, 0.20), "cloth")
	mesh.position = Vector3(0.0, 0.035, 0.0)
	pickup.add_child(mesh)
	var area := Area3D.new()
	area.collision_layer = Layers.TRIGGER
	area.collision_mask = Layers.PLAYER
	var area_shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = 0.8
	area_shape.shape = sphere
	area.add_child(area_shape)
	pickup.add_child(area)
	var host := get_parent()
	var tree := get_tree()
	if tree != null and tree.current_scene != null:
		host = tree.current_scene
	if host == null:
		pickup.free()
		return
	# Beside the weapon, not under it, so both prompts stay reachable.
	var angle := _rng.randf_range(-PI, PI)
	var pos := global_position + Vector3(cos(angle), 0.0, sin(angle)) * 0.75
	if _world != null:
		pos.y = _world.ground_y(pos.x, pos.z) + 0.05
	host.add_child.call_deferred(pickup)
	pickup.set_deferred("global_position", pos)
	pickup.set_deferred("rotation", Vector3(0.0, _rng.randf_range(-PI, PI), 0.0))


## Simplified ragdoll: the body tips over with a damped rotation, lies there for
## thirty seconds, then sinks into the ground and frees itself. A real ragdoll
## would need a joint skeleton and would explode on streamed collision.
func _tick_dead(delta: float) -> void:
	_dead_time += delta
	if _dead_time < 2.5:
		if not is_on_floor():
			velocity.y -= GRAVITY * delta
		else:
			velocity.y = 0.0
		velocity.x = move_toward(velocity.x, 0.0, 6.0 * delta)
		velocity.z = move_toward(velocity.z, 0.0, 6.0 * delta)
		move_and_slide()
	if _body != null and is_instance_valid(_body):
		if not _rig_death:
			_fall_angle = lerpf(_fall_angle, PI * 0.48, clampf(4.0 * delta, 0.0, 1.0))
			_body.transform.basis = Basis(_fall_axis, _fall_angle)
		if _dead_time > CORPSE_SECONDS:
			_body.position.y = _body_y - (_dead_time - CORPSE_SECONDS) * SINK_SPEED
	if _dead_time > CORPSE_SECONDS + SINK_SECONDS:
		queue_free()


# ------------------------------------------------------------------- cover --

## Picks the best cover point protecting from `threat`. Returns false when
## nothing usable is in range, in which case the caller must keep fighting.
func _seek_cover(threat: Vector3, max_distance: float) -> bool:
	_refresh_cover()
	var best := Vector3.ZERO
	var best_score := -1.0e9
	for point in _cover:
		var pos: Vector3 = point.position
		var distance := global_position.distance_to(pos)
		if distance > max_distance:
			continue
		var to_threat := threat - pos
		to_threat.y = 0.0
		if to_threat.length() < 4.0:
			continue                       # cover right under the enemy nose
		var normal: Vector3 = point.normal
		if normal.length_squared() < 0.001:
			continue
		var protection := normal.normalized().dot(to_threat.normalized())
		if protection < 0.15:
			continue                       # this side is exposed
		var score := protection * 40.0 - distance * 1.1
		if bool(point.is_high):
			score += 8.0
		score -= pos.distance_to(_home) * 0.04
		if score > best_score:
			best_score = score
			best = pos
	if best_score <= -1.0e8:
		_has_cover = false
		return false
	_cover_pos = best
	_has_cover = true
	return true


func _refresh_cover() -> void:
	if _world == null:
		return
	if _time < _cover_refresh:
		return
	_cover_refresh = _time + 4.0
	var found := _world.cover_points_near(global_position, 35.0)
	if not found.is_empty():
		_cover = found


func _cover_valid() -> bool:
	return _has_cover


# ------------------------------------------------------------------ orders --

func set_patrol_route(points: PackedVector3Array) -> void:
	_route = points
	_route_index = 0
	_route_wait = 0.0
	if not _route.is_empty() and (state == S_IDLE or state == S_PATROL):
		_enter_state(S_PATROL)


func set_cover_points(points: Array) -> void:
	_cover = points
	_cover_refresh = _time + 6.0


func order_move_to(pos: Vector3) -> void:
	if state == S_DEAD:
		return
	_order_pos = pos
	_has_order = true
	_hold_pos = pos
	if state == S_IDLE or state == S_PATROL or state == S_ALERT:
		_enter_state(S_ADVANCE)
	_go_to(pos, 1.6)


func order_hold(pos: Vector3) -> void:
	if state == S_DEAD:
		return
	_hold_pos = pos
	_home = pos
	_has_order = false
	# Holding a position is the explicit opposite of escorting somebody, and it
	# is exactly what a companion is told when the player toggles his order.
	# `order_move_to` on the other hand is only a detour: it leaves the escort
	# standing, so a companion sent somewhere falls back in behind afterwards.
	_follow_node = null
	_follow_moving = false
	_route = PackedVector3Array()
	if state == S_IDLE or state == S_PATROL or state == S_ADVANCE or state == S_FLANK:
		_enter_state(S_IDLE)
		_go_to(pos, 1.2)


## Follows a moving node instead of a fixed point. This is what makes a
## resistance companion useful: nothing about the combat behaviour changes, only
## the destination the soldier falls back on when nothing is happening. Pass
## null to stop escorting; `order_hold` does the same explicitly.
@warning_ignore("shadowed_variable")
func order_follow(target: Node3D, distance: float) -> void:
	if state == S_DEAD:
		return
	if target == null or not is_instance_valid(target) or target == self:
		_follow_node = null
		_follow_moving = false
		return
	_follow_node = target
	_follow_distance = maxf(FOLLOW_MIN_DISTANCE, distance)
	_follow_moving = false
	_has_order = false
	# A patrol route and an escort cannot both own the destination.
	_route = PackedVector3Array()
	_route_index = 0
	_route_wait = 0.0
	if state == S_PATROL or state == S_ADVANCE or state == S_FLANK:
		_enter_state(S_IDLE)


func alert_to(pos: Vector3, certainty: float) -> void:
	if state == S_DEAD:
		return
	if state == S_COMBAT and _target_visible:
		return                     # busy with something a lot more concrete
	var sure := clampf(certainty, 0.0, 1.0)
	_last_known = pos
	_has_last_known = true
	_search_timer = maxf(_search_timer, lerpf(SEARCH_MIN, SEARCH_MAX, sure))
	_face_dir = (pos - global_position).normalized()
	if state == S_IDLE or state == S_PATROL:
		_enter_state(S_ALERT)
	if sure >= 0.8 and faction == War.AXIS:
		War.raise_alert(War.ALERT_SEARCHING)


func notice_enemy(enemy: Node3D) -> void:
	if state == S_DEAD or enemy == null or not is_instance_valid(enemy):
		return
	if target == enemy and _target_visible:
		return
	target = enemy
	_last_known = enemy.global_position
	_has_last_known = true
	_lost_timer = 0.0
	_search_timer = _rng.randf_range(SEARCH_MIN, SEARCH_MAX)
	# Second hand information: slower to act on than seeing it yourself.
	_reaction_timer = maxf(_reaction_timer, _reaction_time() * 1.35)
	_aim_converge = 0.0
	if state != S_COMBAT and state != S_COVER and state != S_SUPPRESSED \
			and state != S_RETREAT and state != S_FLANK:
		_enter_state(S_ADVANCE)


## Rounds cracking past pin a soldier down: he stays behind cover, fires blind
## and stops advancing until it lets up.
func suppress(amount: float) -> void:
	if state == S_DEAD or amount <= 0.0:
		return
	_suppression = clampf(_suppression + amount, 0.0, 2.0)
	_aim_converge = maxf(0.0, _aim_converge - amount * 0.5)
	if _suppression < SUPPRESS_TRIGGER:
		return
	if state == S_COVER or state == S_SUPPRESSED or state == S_RETREAT:
		return
	if rank == R_VETERAN and _rng.randf() < 0.4:
		return                      # veterans hold their nerve more often
	_enter_state(S_SUPPRESSED)


## Set by Squad when it hands out roles.
func set_role(new_role: int) -> void:
	_role = new_role


func set_squad(squad_node: Node3D) -> void:
	_squad = squad_node


func known_target_position() -> Vector3:
	return _last_known if _has_last_known else global_position


func has_known_target() -> bool:
	return _has_last_known


func is_engaged() -> bool:
	return state == S_COMBAT or state == S_COVER or state == S_ADVANCE \
			or state == S_FLANK or state == S_SUPPRESSED


# ---------------------------------------------------- stealth and intel --

## True while this soldier has spotted nobody at all: standing guard, walking a
## route, or poking at a noise with nothing in his sights. That window is the
## only one in which a takedown from behind can stay quiet.
##
## Anybody in combat or behind cover is out, and so is anybody holding a target,
## whatever his state says. A target reference left over from a body that has
## since been freed does not count: it is nothing he can still see.
func is_unaware() -> bool:
	if state == S_DEAD:
		return false
	if target != null and is_instance_valid(target):
		return false
	return state == S_IDLE or state == S_PATROL or state == S_ALERT


## Takes the cry and the noise out of this soldier's death. The player calls it
## just BEFORE the killing blow of a takedown from behind, never after. Without
## it the man screams and hands the garrison the position of the knife.
##
## No effect on a soldier who is already dead: the death has already been heard.
func silence_death() -> void:
	if state == S_DEAD:
		return
	_silent_death = true


## Site this soldier belongs to, written by the Director when it spawns him.
## Feeds the intelligence the player takes off an officer's body.
func set_home_site(site_id: int) -> void:
	_home_site = site_id


func home_site() -> int:
	return _home_site


# ------------------------------------------------------------------ probes --

func head_height() -> float:
	return global_position.y + (HEAD_CROUCH if _crouched else HEAD_STAND)


func is_alive() -> bool:
	return state != S_DEAD and health > 0.0


func eye_position() -> Vector3:
	return global_position + Vector3(0.0, EYE_CROUCH if _crouched else EYE_STAND, 0.0)


func state_name() -> String:
	match state:
		S_IDLE:
			return "Repos"
		S_PATROL:
			return "Patrouille"
		S_ALERT:
			return "En alerte"
		S_COMBAT:
			return "Combat"
		S_ADVANCE:
			return "Progression"
		S_COVER:
			return "A couvert"
		S_FLANK:
			return "Debordement"
		S_RETREAT:
			return "Repli"
		S_DEAD:
			return "Hors de combat"
		S_SUPPRESSED:
			return "Cloue au sol"
	return "Inconnu"


func faction_name() -> String:
	match faction:
		War.AXIS:
			return "Axe"
		War.ALLIED:
			return "Allie"
	return "Neutre"


func rank_name() -> String:
	match rank:
		R_CONSCRIPT:
			return "Conscrit"
		R_REGULAR:
			return "Soldat"
		R_VETERAN:
			return "Veteran"
		R_OFFICER:
			return "Officier"
		R_SNIPER:
			return "Tireur d'elite"
		R_MACHINE_GUNNER:
			return "Mitrailleur"
	return "Soldat"


func weapon_id() -> int:
	return _weapon_id


func morale() -> float:
	return _morale


func suppression() -> float:
	return _suppression


func debug_line() -> String:
	return "%s %s %s pv=%d moral=%.2f" % [faction_name(), rank_name(),
			state_name(), roundi(health), _morale]


# ----------------------------------------------------------------- helpers --

func _facing() -> Vector3:
	return -global_transform.basis.z


func _now() -> float:
	return float(Time.get_ticks_msec()) * 0.001


func _player_node() -> Node3D:
	var tree := get_tree()
	if tree == null:
		return null
	var node := tree.get_first_node_in_group("player")
	if node == null:
		return null
	return node as Node3D


func _vfx() -> Node:
	var tree := get_tree()
	if tree == null:
		return null
	return tree.get_first_node_in_group("vfx")


func _friends_near(radius: float) -> Array[Node3D]:
	var result: Array[Node3D] = []
	var tree := get_tree()
	if tree == null:
		return result
	var squared := radius * radius
	for node in tree.get_nodes_in_group(_faction_group()):
		if not is_instance_valid(node):
			continue
		var body := node as Node3D
		if body == null or body == self:
			continue
		if body.has_method("is_alive") and not bool(body.call("is_alive")):
			continue
		if global_position.distance_squared_to(body.global_position) <= squared:
			result.append(body)
	return result


static func _point_segment_distance(point: Vector3, from: Vector3, to: Vector3) -> float:
	var segment := to - from
	var length_squared := segment.length_squared()
	if length_squared < 0.0001:
		return point.distance_to(from)
	var t := clampf((point - from).dot(segment) / length_squared, 0.0, 1.0)
	return point.distance_to(from + segment * t)
