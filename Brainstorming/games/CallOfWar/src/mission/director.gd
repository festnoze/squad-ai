## The living world: site garrisons, roaming patrols, alert driven
## reinforcements, friendly maquisards and the ambient noise of a war that goes
## on whether the player is watching or not.
##
## Three rules shape everything here.
##
## 1. Budget. Never more than `MAX_SOLDIERS` live soldiers nor `MAX_SQUADS`
##    squads. Squads farther than `RECYCLE_DISTANCE` and not fighting are
##    recycled, which also keeps the physics step flat.
## 2. Never spawn in front of the player. An order is only executed when its
##    position is at least `MIN_SPAWN_DISTANCE` away and either behind the
##    player, far enough to be a dot, or hidden behind something solid. An
##    order that cannot be executed waits in the queue instead of cheating.
## 3. Never build the whole world on one frame. Orders are spent one at a time,
##    `SPAWN_GAP` seconds apart, and a garrison is cut into squads of at most
##    `SQUAD_MAX_SIZE` so a twelve man site fills up over several seconds
##    instead of popping into existence. `Squad.setup()` builds its own members
##    in a single call, so four soldiers is the finest grain the contract
##    allows; the staggering happens between squads.
##
## Garrison memory. `_garrison_left` keeps, for the whole session, how many men
## a site still owes. Killing four of the six defenders of a farm and walking
## away means two men are there when you come back, not six.
##
## The Maquis layer adds three ways for the campaign to answer back.
##
##  * Counter attacks. A liberated sector may be assaulted once, announced a
##    minute and a half ahead. The assault draws on the SAME budgets as
##    everything else instead of adding to them, and losing it never cancels a
##    capture: `War.capture_sector` stays idempotent and the sector is merely
##    flagged contested, with a thinned garrison walking back in.
##  * Radio isolation. A site whose mast fell before anybody raised the alarm
##    stops being a source of reinforcement waves. That is the mechanical payoff
##    of scouting a garrison with the binoculars before touching it.
##  * Resistance caches. Every liberated sector gets one crate at its safe
##    house, five minutes of play between two uses, so resupply is a place on
##    the map rather than a menu.
class_name Director
extends Node

signal event_announced(text: String)
## A counter attack has been announced on this sector. The HUD banners it here,
## the first squad only lands `CA_WARNING` seconds later.
signal counter_attack_started(sector_id: int)
## `held` is true when the assault was broken, false when the player died or was
## simply not there. False also marks the sector contested in `War`.
signal counter_attack_resolved(sector_id: int, held: bool)

# --- Budget ----------------------------------------------------------------

const MAX_SOLDIERS := 60
const MAX_SQUADS := 14
const SQUAD_MAX_SIZE := 4
const RECYCLE_DISTANCE := 320.0
const ALLY_MAX := 10

# --- Spawn safety ----------------------------------------------------------

const MIN_SPAWN_DISTANCE := 70.0
## Beyond this the player cannot tell a soldier appeared, so the cone test is
## skipped entirely.
const VIEW_CHECK_DISTANCE := 260.0
## Cosine of the half angle considered "in front of the player" (about 70 deg).
const VIEW_DOT := 0.34
## Seconds between two spawn orders.
const SPAWN_GAP := 0.55
## An order that never becomes safe is dropped after this many seconds.
const ORDER_LIFE := 45.0

# --- Rhythm ----------------------------------------------------------------

const SITE_SCAN_GAP := 0.8
const SITE_RANGE := 700.0
const PATROL_MIN := 190.0
const PATROL_MAX := 470.0
const PATROL_POINTS := 6
const REINFORCE_GAP := 30.0
const REINFORCE_MAX_WAVES := 3
const REINFORCE_RING_MIN := 150.0
const REINFORCE_RING_MAX := 250.0
const AMBIENCE_MIN := 40.0
const AMBIENCE_MAX := 120.0
const RECYCLE_GAP := 1.0

# --- Counter attacks -------------------------------------------------------

## Odds that a captured sector earns a counter attack. Rolled once, the moment
## the sector falls, and never again for that sector.
const CA_CHANCE := 0.4
const CA_DELAY_MIN := 360.0
const CA_DELAY_MAX := 840.0
## Seconds between the radio warning and the first squad order.
const CA_WARNING := 90.0
const CA_SQUADS_MIN := 2
const CA_SQUADS_MAX := 3
## The column forms on a ring around the sector, never on its doorstep.
const CA_RING_MIN := 130.0
const CA_RING_MAX := 210.0
## A counter attack order is worth waiting for far longer than a routine one: it
## is an announced beat, not ambience, and dropping it because the player spent
## forty seconds looking that way would leave the HUD lying about an assault
## that never came.
const CA_ORDER_LIFE := 150.0
## Farther than this from the sector and the player is not defending it.
const CA_ABSENT_DISTANCE := 400.0
## Seconds of absence after which the sector falls without a shot fired.
const CA_ABSENT_SECONDS := 75.0
## Hard stop, so a stalled assault can never hold squads hostage forever.
const CA_MAX_SECONDS := 420.0
## Share of the original garrison that moves back into a lost sector.
const CA_GARRISON_SHARE := 0.5
const CA_GARRISON_MIN := 3
## Retry delay when the moment is wrong: timed objective running, player down.
const CA_RETRY := 30.0

## Counter attack states. Only WARNED and ASSAULT count as "active": before
## that nothing exists on the map and nothing has been promised to the player.
const CA_IDLE := 0
const CA_PLANNED := 1
const CA_WARNED := 2
const CA_ASSAULT := 3

# --- Resistance caches -----------------------------------------------------

## Game seconds between two uses of the same cache. Long enough that it shapes
## the round trips instead of replacing them.
const CACHE_COOLDOWN := 300.0

# --- Radio isolation -------------------------------------------------------

## How close the alert has to be to a site for that site to count as its source,
## and therefore for its destroyed mast to silence the waves.
const ISOLATION_RANGE := 260.0

# --- Ambience --------------------------------------------------------------

const PLANE_SPEED := 92.0
const PLANE_ALTITUDE := 138.0
const PLANE_RUN := 860.0
const PLANE_SOUND_GAP := 1.15

const EV_ARTILLERY := 0
const EV_PLANE := 1
const EV_CONVOY := 2
const EV_PATROL := 3
const EV_BIRDS := 4

# --- Order kinds -----------------------------------------------------------

const K_GARRISON := 0
const K_PATROL := 1
const K_REINFORCE := 2
const K_ALLY := 3
const K_OFFICER := 4
const K_COUNTER := 5


## One pending spawn. Orders are the only way anything is created.
class _Order extends RefCounted:
	var kind: int = K_PATROL
	var site_id: int = -1
	var position: Vector3 = Vector3.ZERO
	var size: int = 3
	var faction: int = 1
	var patrol: PackedVector3Array = PackedVector3Array()
	var target: Vector3 = Vector3.ZERO
	var has_target: bool = false
	var anchor: Vector3 = Vector3.ZERO
	var radius: float = 30.0
	var life: float = ORDER_LIFE
	## Part of the running counter attack, which is bookkept apart: these squads
	## are never recycled and their loss is what resolves the assault.
	var counter: bool = false


## One delayed sound or blast, so an artillery salvo is spread over seconds.
class _Cue extends RefCounted:
	var delay: float = 0.0
	var sample: String = ""
	var position: Vector3 = Vector3.ZERO
	var volume: float = 0.0
	var pitch: float = 1.0
	var blast: float = 0.0


## A Resistance supply cache: a couple of crates dropped at the safe house of a
## liberated sector. Not a vending machine, a place you walk back to: one use
## every `CACHE_COOLDOWN` seconds of play.
##
## It reports through a signal rather than by calling the Director back, so the
## crate never needs to know the class that built it.
class _Cache extends Node3D:
	signal used(cache: Node, user: Node)

	var site_id: int = -1
	var cooldown: float = 0.0

	## Whole minutes already written into the prompt. The player reads that meta
	## every single frame, so the label is only rebuilt when it changes.
	var _shown: int = -1

	func setup(id: int) -> void:
		site_id = id
		add_to_group("usable")
		set_meta("surface", "wood")
		_build()
		_refresh_prompt()

	func is_ready() -> bool:
		return cooldown <= 0.0

	func start_cooldown(seconds: float) -> void:
		cooldown = maxf(0.0, seconds)
		_refresh_prompt()

	func tick(delta: float) -> void:
		if cooldown <= 0.0:
			return
		cooldown = maxf(0.0, cooldown - delta)
		_refresh_prompt()

	## The player looks for `interact` on whatever he is aiming at, so this is
	## the whole contract with him. The refill itself belongs to the Director,
	## which owns the announcements.
	func interact(player: Node) -> void:
		used.emit(self, player)

	func _refresh_prompt() -> void:
		var minutes: int = int(ceil(cooldown / 60.0))
		if minutes == _shown:
			return
		_shown = minutes
		if minutes <= 0:
			set_meta("prompt", "Ravitaillement de la Résistance [E]")
		else:
			set_meta("prompt", "Cache vide, revenez dans %d min" % minutes)

	func _build() -> void:
		var wood: Material = MatLib.get_material("wood")
		var cloth: Material = MatLib.get_material("cloth")

		var big := MeshInstance3D.new()
		var big_mesh := BoxMesh.new()
		big_mesh.size = Vector3(1.15, 0.78, 0.82)
		big.mesh = big_mesh
		big.position = Vector3(0.0, 0.39, 0.0)
		big.material_override = wood
		add_child(big)

		var tarp := MeshInstance3D.new()
		var tarp_mesh := BoxMesh.new()
		tarp_mesh.size = Vector3(1.26, 0.09, 0.94)
		tarp.mesh = tarp_mesh
		tarp.position = Vector3(0.0, 0.81, 0.0)
		tarp.material_override = cloth
		add_child(tarp)

		var small := MeshInstance3D.new()
		var small_mesh := BoxMesh.new()
		small_mesh.size = Vector3(0.6, 0.42, 0.52)
		small.mesh = small_mesh
		small.position = Vector3(0.2, 1.07, -0.08)
		small.rotation.y = 0.42
		small.material_override = wood
		add_child(small)

		var body := StaticBody3D.new()
		body.name = "Coque"
		body.collision_layer = Layers.PROP
		body.collision_mask = 0
		body.set_meta("surface", "wood")
		var shape := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = Vector3(1.3, 1.3, 1.0)
		shape.shape = box
		shape.position.y = box.size.y * 0.5
		body.add_child(shape)
		add_child(body)


var _world: GameWorld = null
var _player: Player = null
var _tracker: ObjectiveTracker = null

var _squads: Array[Squad] = []
var _lone: Array[Soldier] = []
var _orders: Array[_Order] = []
var _cues: Array[_Cue] = []

## site id -> soldiers the site still owes, for the whole session.
var _garrison_left: Dictionary = {}
## site id -> Array[Squad] currently holding it.
var _garrison_squads: Dictionary = {}
## soldier instance id -> site id, so a death can be charged to a site.
var _soldier_site: Dictionary = {}
## site id -> true once its officer has been spawned (dead or alive).
var _officer_done: Dictionary = {}
## site id -> true once a friendly cell has been placed there.
var _ally_done: Dictionary = {}

## site id -> true once its radio mast fell before anybody called for help.
var _isolated: Dictionary = {}
## site id -> _Cache, one crate per liberated sector.
var _caches: Dictionary = {}

var _ca_state: int = CA_IDLE
var _ca_sector: int = -1
## Seconds left before the next transition of `_ca_state`.
var _ca_timer: float = 0.0
## Squads of the running assault. Untyped on purpose: every entry is checked
## with `is_instance_valid` BEFORE any cast, and a typed array would force the
## cast first, which is exactly how a freed squad takes the game down.
var _ca_squads: Array = []
## Counter attack orders queued and not spent yet.
var _ca_pending: int = 0
## Counter attack squads actually put on the ground.
var _ca_spawned: int = 0
## Seconds the player has spent away from the sector under assault.
var _ca_away: float = 0.0
var _ca_elapsed: float = 0.0
## sector id -> true once the dice were rolled for it. One roll per sector.
var _ca_rolled: Dictionary = {}
## Raised by the `died` signal. Polling would miss it: Main revives the player
## inside the same frame, so `is_alive()` is true again by the next tick.
var _ca_player_down: bool = false

var _rng := RandomNumberGenerator.new()
var _player_pos := Vector3.ZERO
var _last_known := Vector3.ZERO
## Site the player was parachuted next to: it always hosts a friendly cell.
var _home_site_id: int = -1

var _spawn_gap: float = 0.0
var _scan_gap: float = 0.4
var _patrol_gap: float = 25.0
var _ambience_gap: float = 22.0
var _recycle_gap: float = RECYCLE_GAP
var _wave_gap: float = 0.0
var _known_gap: float = 0.0
var _waves: int = 0

var _plane: Node3D = null
var _plane_dir := Vector3.FORWARD
var _plane_left: float = 0.0
var _plane_sound: float = 0.0

var _ready_to_run: bool = false


func _ready() -> void:
	add_to_group("director")
	set_process(false)
	set_physics_process(false)


func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void:
	_world = game_world
	_player = player_node
	_tracker = tracker
	if _world == null:
		push_error("Director.setup: world is null, the world will stay empty")
		return
	_rng.seed = int(Time.get_unix_time_from_system()) ^ 0x5F3759DF
	_player_pos = _player.global_position if _player != null else Vector3.ZERO
	_last_known = _player_pos

	var layout: Layout = _world.layout()
	if layout != null:
		var spawn: Vector2 = layout.spawn_point()
		var home: Layout.Site = layout.nearest_site(spawn.x, spawn.y)
		if home != null:
			_home_site_id = home.id
	if not War.sector_captured.is_connected(_on_sector_captured):
		War.sector_captured.connect(_on_sector_captured)
	if _player != null and is_instance_valid(_player) \
			and not _player.died.is_connected(_on_player_died):
		_player.died.connect(_on_player_died)

	_ambience_gap = _rng.randf_range(20.0, 45.0)
	_patrol_gap = _rng.randf_range(12.0, 25.0)
	_ready_to_run = true


## A liberated sector keeps no garrison: whoever was still standing pulls out.
func _on_sector_captured(sector_id: int) -> void:
	_garrison_left[sector_id] = 0
	var squads: Array = _garrison_squads.get(sector_id, [])
	for entry in squads.duplicate():
		var squad: Squad = entry
		if squad != null and is_instance_valid(squad) and squad.faction == War.AXIS:
			_release_squad(squad)
	_garrison_squads[sector_id] = []
	_roll_counter_attack(sector_id)


# ---------------------------------------------------------------------------
# Frame
# ---------------------------------------------------------------------------

func tick(delta: float) -> void:
	if not _ready_to_run or _world == null:
		return
	if _player != null and is_instance_valid(_player):
		_player_pos = _player.global_position

	_prune()

	_scan_gap -= delta
	if _scan_gap <= 0.0:
		_scan_gap = SITE_SCAN_GAP
		_scan_sites()

	_patrol_gap -= delta
	if _patrol_gap <= 0.0:
		_patrol_gap = _patrol_interval()
		_queue_patrol(false)

	_tick_reinforcements(delta)
	_tick_counter_attack(delta)
	_tick_caches(delta)

	_ambience_gap -= delta
	if _ambience_gap <= 0.0:
		_ambience_gap = _rng.randf_range(AMBIENCE_MIN, AMBIENCE_MAX)
		_fire_ambience()

	_tick_cues(delta)
	_tick_plane(delta)
	_tick_orders(delta)

	_recycle_gap -= delta
	if _recycle_gap <= 0.0:
		_recycle_gap = RECYCLE_GAP
		_recycle()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

func live_soldier_count() -> int:
	var total: int = 0
	for squad in _squads:
		if squad != null and is_instance_valid(squad):
			total += squad.alive_count()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier) and soldier.is_alive():
			total += 1
	return total + _companion_count()


## Recruited companions are bodies in the world that this node no longer owns:
## adoption pulls the man out of his squad and reparents him under the companion
## manager, so he silently leaves the count above. Without this, the budget
## would believe it has two free slots that the physics step does not have, and
## a counter attack would spawn OVER the ceiling of sixty men instead of drawing
## on it.
func _companion_count() -> int:
	if not is_inside_tree():
		return 0
	var nodes: Array = get_tree().get_nodes_in_group("companions")
	if nodes.is_empty():
		return 0
	var manager: Node = nodes[0]
	if manager == null or not is_instance_valid(manager):
		return 0
	if not manager.has_method("members"):
		# Older or partial build of the module: the headcount is still better
		# than pretending there is nobody there.
		if manager.has_method("count"):
			return maxi(0, int(manager.call("count")))
		return 0
	var total: int = 0
	for entry in manager.call("members"):
		if entry == null or not is_instance_valid(entry):
			continue
		var man: Soldier = entry
		if not man.is_alive():
			continue
		# A freed prisoner who was then recruited is still in `_lone`, where he
		# has already been counted once. Counting him twice would shrink the
		# budget rather than protect it.
		if _lone.has(man):
			continue
		total += 1
	return total


func live_squad_count() -> int:
	return _squads.size()


## Forces a reinforcement wave towards a position. Split into small squads that
## come in from a ring around the target, never from the player's face.
func send_reinforcements(pos: Vector3, count: int) -> void:
	if _world == null or count <= 0:
		return
	var remaining: int = mini(count, MAX_SOLDIERS)
	var guard: int = 0
	while remaining > 0 and guard < 6:
		guard += 1
		var size: int = mini(remaining, SQUAD_MAX_SIZE)
		remaining -= size
		var order := _Order.new()
		order.kind = K_REINFORCE
		order.size = size
		order.faction = War.AXIS
		order.position = _ring_point(pos, REINFORCE_RING_MIN, REINFORCE_RING_MAX)
		order.target = pos
		order.has_target = true
		order.anchor = pos
		order.radius = 40.0
		_orders.append(order)


## Cuts the reinforcement waves coming from a site whose radio mast was blown.
## This is what pays for scouting: spot the mast with the binoculars, destroy it
## before anybody sees you, and the garrison you are about to hit cannot call a
## soul. Calling it twice changes nothing.
func isolate_site(site_id: int) -> void:
	if site_id < 0 or _isolated.has(site_id):
		return
	_isolated[site_id] = true
	# A counter attack that is only planned is called off with the mast: nobody
	# up the chain knows this sector needs help any more. One already announced
	# stands, the column is on the road and no radio recalls it.
	if _ca_state == CA_PLANNED and _ca_sector == site_id:
		_ca_state = CA_IDLE
		_ca_sector = -1
		_ca_timer = 0.0
	event_announced.emit("Radio détruite: la garnison de %s ne peut plus appeler de renforts."
			% _place_name(site_id))


func is_site_isolated(site_id: int) -> bool:
	return _isolated.has(site_id)


## The sector under counter attack right now, -1 when there is none. A counter
## attack that is merely planned does not count: nothing is on the map yet and
## nothing has been promised to the player.
func active_counter_attack() -> int:
	if _ca_state == CA_WARNED or _ca_state == CA_ASSAULT:
		return _ca_sector
	return -1


## Immediate trigger, for the objectives and the test probe. It skips the delay
## and the timed objective guard, because the caller is the one who decided this
## is the moment. The two hard rules stand: never the drop zone village, never
## two counter attacks at once.
func force_counter_attack(sector_id: int) -> void:
	if sector_id < 0 or sector_id == _home_site_id or _ca_state != CA_IDLE:
		return
	if _site_of(sector_id) == null:
		return
	_ca_rolled[sector_id] = true
	_ca_sector = sector_id
	_ca_state = CA_WARNED
	_ca_timer = 0.0
	_announce_counter_attack()
	_launch_counter_attack()


## Frees every spawned squad. Called on shutdown and on scene reload.
func clear_all() -> void:
	for squad in _squads:
		if squad != null and is_instance_valid(squad):
			_detach_squad(squad)
			squad.despawn()
			squad.queue_free()
	_squads.clear()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier):
			if soldier.died.is_connected(_on_soldier_died):
				soldier.died.disconnect(_on_soldier_died)
			soldier.queue_free()
	_lone.clear()
	_orders.clear()
	_cues.clear()
	_garrison_squads.clear()
	_soldier_site.clear()
	for site_id in _caches.keys():
		var raw: Variant = _caches[site_id]
		if raw == null or not is_instance_valid(raw):
			continue
		var cache: _Cache = raw
		if cache.used.is_connected(_on_cache_used):
			cache.used.disconnect(_on_cache_used)
		cache.queue_free()
	_caches.clear()
	_ca_squads.clear()
	_ca_rolled.clear()
	_isolated.clear()
	_ca_state = CA_IDLE
	_ca_sector = -1
	_ca_timer = 0.0
	_ca_pending = 0
	_ca_spawned = 0
	_ca_away = 0.0
	_ca_elapsed = 0.0
	_ca_player_down = false
	if _plane != null and is_instance_valid(_plane):
		_plane.queue_free()
	_plane = null
	_plane_left = 0.0
	if War.sector_captured.is_connected(_on_sector_captured):
		War.sector_captured.disconnect(_on_sector_captured)
	if _player != null and is_instance_valid(_player) \
			and _player.died.is_connected(_on_player_died):
		_player.died.disconnect(_on_player_died)
	_ready_to_run = false


func debug_line() -> String:
	var target: int = active_counter_attack()
	var counter: String = "aucune" if target < 0 else "secteur %d" % target
	return "Director %d soldats, %d escouades, %d ordres, alerte %s, contre-attaque %s" % [
		live_soldier_count(), _squads.size(), _orders.size(), War.alert_name(), counter]


# ---------------------------------------------------------------------------
# Garrisons
# ---------------------------------------------------------------------------

func _scan_sites() -> void:
	var layout: Layout = _world.layout()
	if layout == null:
		return
	for site in layout.sites:
		var dx: float = site.center.x - _player_pos.x
		var dz: float = site.center.y - _player_pos.z
		if dx * dx + dz * dz > SITE_RANGE * SITE_RANGE:
			continue
		var built: SiteBuilder.BuiltSite = _world.built_site(site.id)
		if built == null:
			continue
		if site.is_sector and War.is_sector_captured(site.id):
			if War.is_sector_contested(site.id):
				_hold_contested(site, built)
				continue
			_ensure_allies(site, built)
			_ensure_cache(site, built)
			continue
		# The drop zone village always hides a Resistance cell, captured or not.
		if site.id == _home_site_id:
			_ensure_allies(site, built)
		_ensure_garrison(site, built)


func _ensure_garrison(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	if not _garrison_left.has(site.id):
		_garrison_left[site.id] = maxi(0, site.garrison)
	var left: int = _garrison_left[site.id]
	if left <= 0:
		return
	if _pending_for(site.id):
		return

	var present: int = _garrison_alive(site.id)
	var missing: int = left - present
	if missing > 0 and _has_room(mini(missing, SQUAD_MAX_SIZE)):
		var order := _Order.new()
		order.kind = K_GARRISON
		order.site_id = site.id
		order.size = mini(missing, SQUAD_MAX_SIZE)
		order.faction = War.AXIS
		order.position = _pick_spawn(built.garrison_spawns, site)
		order.patrol = _trim_route(built.patrol_points)
		order.anchor = Vector3(site.center.x, site.ground, site.center.y)
		order.radius = maxf(20.0, site.radius * 0.8)
		_orders.append(order)
		return

	# One officer per sector, on his anchor: he is the assassination target and
	# he does not count against the garrison strength.
	if site.is_sector and not _officer_done.has(site.id) and _has_room(1):
		var anchor: Variant = built.objective_anchors.get(MissionDefs.ANCHOR_OFFICER)
		var at: Vector3 = anchor if typeof(anchor) == TYPE_VECTOR3 else _site_anchor(site)
		var officer := _Order.new()
		officer.kind = K_OFFICER
		officer.site_id = site.id
		officer.size = 1
		officer.faction = War.AXIS
		officer.position = at
		officer.anchor = at
		officer.radius = maxf(18.0, site.radius * 0.6)
		_orders.append(officer)


## A contested sector is Axis ground again, held by a thinned garrison. The
## capture itself was never taken back and neither was the objective chain: only
## the ground has to be walked over a second time. Once that garrison is gone
## the flag comes off, so the state can always be played out of, even if the
## objective layer never replays its capture step.
func _hold_contested(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	if not _garrison_left.has(site.id):
		# Reached on a reloaded save: the ledger of who still owes men does not
		# survive to disk, only the contested flag does.
		_garrison_left[site.id] = maxi(CA_GARRISON_MIN,
				int(round(float(site.garrison) * CA_GARRISON_SHARE)))
	var left: int = int(_garrison_left[site.id])
	if left <= 0 and _garrison_alive(site.id) <= 0 and not _pending_for(site.id):
		War.clear_contested(site.id)
		event_announced.emit("%s est de nouveau entre nos mains." % _place_name(site.id))
		return
	_ensure_garrison(site, built)


func _site_anchor(site: Layout.Site) -> Vector3:
	return Vector3(site.center.x, site.ground, site.center.y)


func _garrison_alive(site_id: int) -> int:
	var squads: Array = _garrison_squads.get(site_id, [])
	var total: int = 0
	for entry in squads:
		var squad: Squad = entry
		if squad != null and is_instance_valid(squad):
			total += squad.alive_count()
	for soldier in _lone:
		if soldier == null or not is_instance_valid(soldier) or not soldier.is_alive():
			continue
		if _soldier_site.get(soldier.get_instance_id(), -1) == site_id and soldier.faction == War.AXIS:
			total += 1
	return total


# ---------------------------------------------------------------------------
# Allies
# ---------------------------------------------------------------------------

func _ensure_allies(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	if _ally_done.has(site.id) or not _has_room(3):
		return
	if _ally_count() >= ALLY_MAX or _pending_for(site.id):
		return
	_ally_done[site.id] = true
	var order := _Order.new()
	order.kind = K_ALLY
	order.site_id = site.id
	order.size = _rng.randi_range(2, 3)
	order.faction = War.ALLIED
	order.position = _pick_spawn(built.garrison_spawns, site)
	order.patrol = _trim_route(built.patrol_points)
	order.anchor = _site_anchor(site)
	order.radius = maxf(25.0, site.radius * 0.9)
	_orders.append(order)


func _ally_count() -> int:
	var total: int = 0
	for squad in _squads:
		if squad != null and is_instance_valid(squad) and squad.faction == War.ALLIED:
			total += squad.alive_count()
	for soldier in _lone:
		if soldier != null and is_instance_valid(soldier) and soldier.is_alive() \
				and soldier.faction == War.ALLIED:
			total += 1
	return total


## Private extension used by `ObjectiveTracker` for a rescue: freed prisoners
## are plain allied soldiers who follow the player. They are exempt from the
## view cone rule since the player is the one opening their cage.
func _spawn_prisoners(pos: Vector3, count: int) -> Array:
	var out: Array = []
	if _world == null or count <= 0:
		return out
	var wanted: int = mini(count, 8)
	for i in wanted:
		if not _has_room(1):
			break
		var angle: float = TAU * float(i) / float(maxi(1, wanted))
		var at := pos + Vector3(cos(angle), 0.0, sin(angle)) * _rng.randf_range(1.5, 3.5)
		at.y = _world.ground_y(at.x, at.z)
		var man := _make_soldier(War.ALLIED, Soldier.R_CONSCRIPT, at, -1)
		if man == null:
			break
		man.order_move_to(_player_pos if _player != null else pos)
		out.append(man)
	if not out.is_empty():
		event_announced.emit("Les prisonniers sont libres, ramenez-les en zone amie.")
	return out


# ---------------------------------------------------------------------------
# Patrols
# ---------------------------------------------------------------------------

func _patrol_interval() -> float:
	# A calm sector is quiet; a general alert fills the roads.
	var base: float = 58.0 - 11.0 * float(War.alert_level)
	return _rng.randf_range(base * 0.7, base * 1.3)


func _queue_patrol(is_convoy: bool) -> void:
	if _squads.size() >= MAX_SQUADS - 2 or not _has_room(SQUAD_MAX_SIZE):
		return
	var route: PackedVector3Array = _road_route()
	if route.size() < 2:
		return
	var order := _Order.new()
	order.kind = K_PATROL
	order.faction = War.AXIS
	order.size = _rng.randi_range(3, SQUAD_MAX_SIZE) if is_convoy else _rng.randi_range(2, 3)
	order.position = route[0]
	order.patrol = route
	order.anchor = route[0]
	order.radius = 30.0
	_orders.append(order)
	if is_convoy:
		var layout: Layout = _world.layout()
		var near: Layout.Site = layout.nearest_site(route[0].x, route[0].z) if layout != null else null
		var place: String = near.display_name if near != null else "la vallee"
		event_announced.emit("Un convoi allemand circule sur la route de %s." % place)


## A slice of a real road, far enough from the player to be spawned on.
func _road_route() -> PackedVector3Array:
	var out := PackedVector3Array()
	var layout: Layout = _world.layout()
	if layout == null or layout.roads.is_empty():
		return out
	var candidates: Array[Vector2i] = []
	for road_index in layout.roads.size():
		var road: PackedVector2Array = layout.roads[road_index]
		for point_index in road.size():
			var p: Vector2 = road[point_index]
			var dx: float = p.x - _player_pos.x
			var dz: float = p.y - _player_pos.z
			var d: float = sqrt(dx * dx + dz * dz)
			if d >= PATROL_MIN and d <= PATROL_MAX:
				candidates.append(Vector2i(road_index, point_index))
	if candidates.is_empty():
		return out
	var pick: Vector2i = candidates[_rng.randi_range(0, candidates.size() - 1)]
	var chosen: PackedVector2Array = layout.roads[pick.x]
	var step: int = 2
	var index: int = pick.y
	var forward: bool = _rng.randf() < 0.5
	for i in PATROL_POINTS:
		if index < 0 or index >= chosen.size():
			break
		var p2: Vector2 = chosen[index]
		out.append(Vector3(p2.x, _world.ground_y(p2.x, p2.y), p2.y))
		index += step if forward else -step
	return out


func _trim_route(points: PackedVector3Array) -> PackedVector3Array:
	if points.size() <= PATROL_POINTS:
		return points
	var out := PackedVector3Array()
	var stride: int = maxi(1, points.size() / PATROL_POINTS)
	var i: int = 0
	while i < points.size() and out.size() < PATROL_POINTS:
		out.append(points[i])
		i += stride
	return out


# ---------------------------------------------------------------------------
# Reinforcements
# ---------------------------------------------------------------------------

func _tick_reinforcements(delta: float) -> void:
	if _player == null or not is_instance_valid(_player):
		return
	if War.alert_level < War.ALERT_FULL:
		_waves = 0
		_wave_gap = 8.0
		_last_known = _player_pos
		return

	_known_gap -= delta
	if _known_gap <= 0.0:
		_known_gap = 2.5
		# Last known position, not the live one: they hunt where you were.
		_last_known = _player_pos

	_wave_gap -= delta
	if _wave_gap > 0.0 or _waves >= REINFORCE_MAX_WAVES:
		return
	_wave_gap = REINFORCE_GAP
	if _alert_source_isolated():
		# The garrison that raised the alarm has no mast left. Nobody comes, and
		# the wave counter does not move either: walk into the next valley and
		# the waves start again from a site that can still call.
		return
	_waves += 1
	send_reinforcements(_last_known, 3 + _waves)
	if _waves == 1:
		event_announced.emit("Des renforts allemands convergent vers votre position.")


## Is the alert coming from a site whose radio is down? The last known position
## of the player is where the hunt is centred, so the nearest site to it is the
## one that would be picking up the telephone.
func _alert_source_isolated() -> bool:
	if _isolated.is_empty() or _world == null:
		return false
	var layout: Layout = _world.layout()
	if layout == null:
		return false
	var near: Layout.Site = layout.nearest_site(_last_known.x, _last_known.z)
	if near == null:
		return false
	var dx: float = near.center.x - _last_known.x
	var dz: float = near.center.y - _last_known.z
	if dx * dx + dz * dz > ISOLATION_RANGE * ISOLATION_RANGE:
		return false
	return _isolated.has(near.id)


## A point on a ring around `pos`, preferring one the player cannot watch.
func _ring_point(pos: Vector3, min_radius: float, max_radius: float) -> Vector3:
	var best := pos
	var best_score: float = -1.0
	var start: float = _rng.randf() * TAU
	for i in 8:
		var angle: float = start + TAU * float(i) / 8.0
		var radius: float = _rng.randf_range(min_radius, max_radius)
		var candidate := pos + Vector3(cos(angle), 0.0, sin(angle)) * radius
		candidate = Heightfield.clamp_to_bounds(candidate)
		candidate.y = _world.ground_y(candidate.x, candidate.z)
		if _spawn_safe(candidate):
			return candidate
		var score: float = candidate.distance_to(_player_pos)
		if score > best_score:
			best_score = score
			best = candidate
	return best


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

func _tick_orders(delta: float) -> void:
	if _orders.is_empty():
		return
	var index: int = _orders.size() - 1
	while index >= 0:
		var order: _Order = _orders[index]
		order.life -= delta
		if order.life <= 0.0:
			if order.counter:
				_ca_pending = maxi(0, _ca_pending - 1)
			_orders.remove_at(index)
		index -= 1

	_spawn_gap -= delta
	if _spawn_gap > 0.0 or _orders.is_empty():
		return
	for i in _orders.size():
		var order: _Order = _orders[i]
		if not _has_room(order.size):
			return
		if not _spawn_safe(order.position):
			continue
		_orders.remove_at(i)
		_execute(order)
		_spawn_gap = SPAWN_GAP
		return


func _execute(order: _Order) -> void:
	if order.kind == K_OFFICER:
		_officer_done[order.site_id] = true
		var officer := _make_soldier(order.faction, Soldier.R_OFFICER, order.position, -1)
		if officer != null:
			officer.order_hold(order.position)
			# He is not charged to the garrison strength, but the documents on
			# his body still have to name the RIGHT site on the map.
			officer.set_home_site(order.site_id)
		return

	var squad := Squad.new()
	squad.name = "Squad%d" % (Time.get_ticks_msec() & 0xFFFF)
	add_child(squad)
	squad.setup(_world, order.faction, order.position, order.size, order.patrol)
	if not squad.wiped.is_connected(_on_squad_wiped):
		squad.wiped.connect(_on_squad_wiped)
	_squads.append(squad)

	for member in squad.members:
		if member == null or not is_instance_valid(member):
			continue
		if not member.died.is_connected(_on_soldier_died):
			member.died.connect(_on_soldier_died)
		if order.site_id >= 0:
			_soldier_site[member.get_instance_id()] = order.site_id
			member.set_home_site(order.site_id)

	if order.kind == K_GARRISON or order.kind == K_ALLY:
		if order.site_id >= 0:
			var list: Array = _garrison_squads.get(order.site_id, [])
			list.append(squad)
			_garrison_squads[order.site_id] = list
		squad.order_defend(order.anchor, order.radius)
	elif order.has_target:
		squad.order_attack(order.target)

	if order.counter:
		_ca_pending = maxi(0, _ca_pending - 1)
		if _ca_state == CA_ASSAULT:
			_ca_squads.append(squad)
			_ca_spawned += 1


func _pending_for(site_id: int) -> bool:
	for order in _orders:
		if order.site_id == site_id:
			return true
	return false


func _has_room(extra: int) -> bool:
	if _squads.size() >= MAX_SQUADS:
		return false
	return live_soldier_count() + extra <= MAX_SOLDIERS


## The single most visible flaw of a badly tuned director is an enemy popping
## into existence in front of the player. This is the guard against it.
func _spawn_safe(pos: Vector3) -> bool:
	if _player == null or not is_instance_valid(_player):
		return true
	if not Heightfield.in_bounds(pos.x, pos.z):
		return false
	var distance: float = pos.distance_to(_player_pos)
	if distance < MIN_SPAWN_DISTANCE:
		return false
	if distance > VIEW_CHECK_DISTANCE:
		return true

	var eye: Vector3 = _player.eye_position()
	var to: Vector3 = pos - eye
	to.y = 0.0
	if to.length_squared() < 1.0:
		return false
	to = to.normalized()
	var facing: Vector3 = _player.aim_direction()
	facing.y = 0.0
	if facing.length_squared() < 0.01:
		return true
	facing = facing.normalized()
	if facing.dot(to) < VIEW_DOT:
		return true                     # behind him, safe

	var space: World3D = _player.get_world_3d()
	if space == null:
		return false
	# In the cone: only allowed when something solid hides the spot.
	return not Ballistics.line_of_sight(space, eye, pos + Vector3.UP * 1.6, [_player])


func _pick_spawn(points: PackedVector3Array, site: Layout.Site) -> Vector3:
	var fallback := _site_anchor(site)
	if points.is_empty():
		return fallback
	var best := fallback
	var best_score: float = -1.0
	var start: int = _rng.randi_range(0, points.size() - 1)
	for i in points.size():
		var candidate: Vector3 = points[(start + i) % points.size()]
		if _spawn_safe(candidate):
			return candidate
		var score: float = candidate.distance_to(_player_pos)
		if score > best_score:
			best_score = score
			best = candidate
	return best


func _make_soldier(faction: int, rank: int, at: Vector3, site_id: int) -> Soldier:
	var soldier := Soldier.new()
	soldier.name = "Soldier%d" % (Time.get_ticks_usec() & 0xFFFFF)
	add_child(soldier)
	# Before setup(), which is what builds the body.
	soldier.species = CharacterModels.pick_species(faction, _rng)
	soldier.setup(_world, faction, rank, at)
	if not soldier.died.is_connected(_on_soldier_died):
		soldier.died.connect(_on_soldier_died)
	if site_id >= 0:
		_soldier_site[soldier.get_instance_id()] = site_id
	_lone.append(soldier)
	return soldier


# ---------------------------------------------------------------------------
# Recycling and bookkeeping
# ---------------------------------------------------------------------------

func _prune() -> void:
	var i: int = _squads.size() - 1
	while i >= 0:
		var squad: Squad = _squads[i]
		if squad == null or not is_instance_valid(squad):
			_squads.remove_at(i)
		i -= 1
	var j: int = _lone.size() - 1
	while j >= 0:
		var soldier: Soldier = _lone[j]
		if soldier == null or not is_instance_valid(soldier):
			_lone.remove_at(j)
		j -= 1


func _recycle() -> void:
	var i: int = _squads.size() - 1
	while i >= 0:
		var squad: Squad = _squads[i]
		i -= 1
		if squad == null or not is_instance_valid(squad):
			continue
		if squad.alive_count() <= 0:
			_release_squad(squad)
			continue
		if _is_counter_squad(squad):
			# An announced assault that dissolves on its way in is a far worse
			# defect than four extra soldiers on the far side of the valley.
			continue
		if squad.center().distance_to(_player_pos) < RECYCLE_DISTANCE:
			continue
		if _engaged(squad):
			continue
		_release_squad(squad)


func _is_counter_squad(squad: Squad) -> bool:
	return _ca_squads.has(squad)


func _is_companion(man: Soldier) -> bool:
	if man == null or not is_instance_valid(man) or not is_inside_tree():
		return false
	var nodes: Array = get_tree().get_nodes_in_group("companions")
	if nodes.is_empty():
		return false
	var manager: Node = nodes[0]
	if manager == null or not is_instance_valid(manager) \
			or not manager.has_method("is_companion"):
		return false
	return bool(manager.call("is_companion", man))


## Pulls the quietest squads out until `extra` more men fit in the budget. Only
## squads that are far away, out of contact and not part of the assault are
## touched, so nothing ever vanishes where the player could notice.
func _make_room(extra: int) -> void:
	var guard: int = 0
	while not _has_room(extra) and guard < MAX_SQUADS:
		guard += 1
		var victim: Squad = _quietest_squad()
		if victim == null:
			return
		_release_squad(victim)


func _quietest_squad() -> Squad:
	var best: Squad = null
	var best_distance: float = RECYCLE_DISTANCE
	var index: int = _squads.size() - 1
	while index >= 0:
		var raw: Variant = _squads[index]
		index -= 1
		if raw == null or not is_instance_valid(raw):
			continue
		var squad: Squad = raw
		if _is_counter_squad(squad) or _engaged(squad):
			continue
		var distance: float = squad.center().distance_to(_player_pos)
		if distance > best_distance:
			best_distance = distance
			best = squad
	return best


func _engaged(squad: Squad) -> bool:
	for member in squad.members:
		if member == null or not is_instance_valid(member) or not member.is_alive():
			continue
		var state: int = member.state
		if state != Soldier.S_IDLE and state != Soldier.S_PATROL and state != Soldier.S_DEAD:
			return true
	return false


## Sends a squad away without counting its members as casualties: they are
## still alive somewhere off screen, they simply stopped being simulated.
func _release_squad(squad: Squad) -> void:
	# Adoption already pulls a companion out of `squad.members`, so recycling
	# should never be able to reach one. This is the belt to that pair of
	# braces: a recruited resistant who evaporates while the player walks is
	# one of the most visible defects there is, and it costs one loop to make
	# it impossible rather than merely unlikely.
	for entry in squad.members.duplicate():
		if entry == null or not is_instance_valid(entry):
			continue
		var member: Soldier = entry
		if _is_companion(member):
			squad.release_member(member)
	_detach_squad(squad)
	_squads.erase(squad)
	squad.despawn()
	squad.queue_free()


func _detach_squad(squad: Squad) -> void:
	if squad.wiped.is_connected(_on_squad_wiped):
		squad.wiped.disconnect(_on_squad_wiped)
	for member in squad.members:
		if member == null or not is_instance_valid(member):
			continue
		if member.died.is_connected(_on_soldier_died):
			member.died.disconnect(_on_soldier_died)
		_soldier_site.erase(member.get_instance_id())
	for site_id in _garrison_squads.keys():
		var list: Array = _garrison_squads[site_id]
		list.erase(squad)
		_garrison_squads[site_id] = list
	_ca_squads.erase(squad)


func _on_squad_wiped(squad: Squad) -> void:
	if squad != null and is_instance_valid(squad):
		_squads.erase(squad)
		squad.queue_free()


func _on_soldier_died(soldier: Soldier) -> void:
	if soldier == null:
		return
	var key: int = soldier.get_instance_id()
	if _soldier_site.has(key):
		var site_id: int = _soldier_site[key]
		if soldier.faction == War.AXIS and _garrison_left.has(site_id):
			_garrison_left[site_id] = maxi(0, int(_garrison_left[site_id]) - 1)
		_soldier_site.erase(key)
	if _tracker != null and is_instance_valid(_tracker):
		# The tracker also hears about kills from the weapon code; reporting the
		# same death twice is harmless, an objective only completes once.
		_tracker.report_kill(soldier, null)


## Going down during an assault loses the sector. The flag is read on the next
## tick, where the whole state machine lives: resolving from inside a signal
## would run while Main is still busy reviving the player.
func _on_player_died() -> void:
	if _ca_state == CA_ASSAULT:
		_ca_player_down = true


# ---------------------------------------------------------------------------
# Counter attacks
# ---------------------------------------------------------------------------

## One roll per sector, at the moment it falls. Losing the roll is final: the
## player is never told, so a sector that stays quiet is simply a sector the
## Wehrmacht wrote off.
func _roll_counter_attack(sector_id: int) -> void:
	if sector_id < 0 or sector_id == _home_site_id:
		return
	if _ca_rolled.has(sector_id):
		return
	_ca_rolled[sector_id] = true
	# Never two at once, and never against a garrison whose mast is down: there
	# is nobody left there to ask for the column.
	if _ca_state != CA_IDLE or is_site_isolated(sector_id):
		return
	if _rng.randf() >= CA_CHANCE:
		return
	_ca_sector = sector_id
	_ca_state = CA_PLANNED
	_ca_timer = _rng.randf_range(CA_DELAY_MIN, CA_DELAY_MAX)
	_ca_player_down = false


func _tick_counter_attack(delta: float) -> void:
	match _ca_state:
		CA_PLANNED:
			_ca_timer -= delta
			if _ca_timer > 0.0:
				return
			if not _can_start_counter_attack():
				_ca_timer = CA_RETRY
				return
			_ca_state = CA_WARNED
			_ca_timer = CA_WARNING
			_announce_counter_attack()
		CA_WARNED:
			_ca_timer -= delta
			if _ca_timer > 0.0:
				return
			_launch_counter_attack()
		CA_ASSAULT:
			_tick_assault(delta)


## A counter attack must never land on top of something the player is already
## racing against, and never on a player who is not there to hear the warning.
func _can_start_counter_attack() -> bool:
	if _site_of(_ca_sector) == null or is_site_isolated(_ca_sector):
		return false
	if _timed_objective_running():
		return false
	if _player == null or not is_instance_valid(_player) or not _player.is_alive():
		return false
	return true


func _timed_objective_running() -> bool:
	if _tracker == null or not is_instance_valid(_tracker):
		return false
	for entry in _tracker.active():
		var obj: MissionDefs.Objective = entry
		if obj != null and obj.time_limit > 0.0:
			return true
	return false


func _announce_counter_attack() -> void:
	_ca_player_down = false
	event_announced.emit("Contre-attaque allemande annoncée sur %s, tenez la position."
			% _place_name(_ca_sector))
	counter_attack_started.emit(_ca_sector)
	_counter_attack_radio()


## The warning is also heard, not only read: a couple of German voices carried
## over from far enough away to read as a radio net waking up rather than as a
## man shouting in the next hedge.
func _counter_attack_radio() -> void:
	if _world == null:
		return
	var direction: Vector3 = _sector_center(_ca_sector) - _player_pos
	direction.y = 0.0
	if direction.length_squared() < 1.0:
		direction = Vector3.FORWARD
	direction = direction.normalized()
	var at: Vector3 = Heightfield.clamp_to_bounds(_player_pos + direction * 150.0)
	at.y = _world.ground_y(at.x, at.z) + 1.6
	_cue("distant_battle", at, 0.2, -6.0, 0.85, 0.0)
	for i in 2:
		_cue("german_alert", at, 0.8 + float(i) * _rng.randf_range(1.1, 1.8), -9.0,
				_rng.randf_range(0.88, 1.02), 0.0)


## Two or three squads converge on the sector. They are ordered like anything
## else, one order at a time, `SPAWN_GAP` apart and only where the player cannot
## watch them appear, so the column walks in instead of materialising.
func _launch_counter_attack() -> void:
	var site: Layout.Site = _site_of(_ca_sector)
	if site == null:
		# The world has no such sector any more: nothing was ever put on the
		# ground, so nothing is taken from the player either.
		_resolve_counter_attack(true)
		return
	var center: Vector3 = _site_anchor(site)
	var wanted: int = _rng.randi_range(CA_SQUADS_MIN, CA_SQUADS_MAX)
	_ca_squads.clear()
	_ca_pending = 0
	_ca_spawned = 0
	_ca_away = 0.0
	_ca_elapsed = 0.0
	# The assault DRAWS ON the standing budgets instead of adding to them, so
	# the room it needs is made first, by pulling out squads nobody can see.
	_make_room(wanted * SQUAD_MAX_SIZE)
	for i in wanted:
		var order := _Order.new()
		order.kind = K_COUNTER
		order.counter = true
		# No site id on purpose: these men are not the garrison of the sector
		# and their deaths must not be charged to `_garrison_left`.
		order.site_id = -1
		order.size = SQUAD_MAX_SIZE
		order.faction = War.AXIS
		order.position = _ring_point(center, CA_RING_MIN, CA_RING_MAX)
		order.target = center
		order.has_target = true
		order.anchor = center
		order.radius = 45.0
		order.life = CA_ORDER_LIFE
		# Ahead of the routine queue: a farm that fills up a few seconds late
		# costs nothing, an announced assault that never shows up costs the HUD
		# its credibility.
		_orders.insert(0, order)
		_ca_pending += 1
	_ca_state = CA_ASSAULT


func _tick_assault(delta: float) -> void:
	_ca_elapsed += delta
	var alive: int = _prune_counter_squads()

	if _ca_player_down:
		_resolve_counter_attack(false)
		return

	if _player_pos.distance_to(_sector_center(_ca_sector)) > CA_ABSENT_DISTANCE:
		_ca_away += delta
	else:
		_ca_away = 0.0
	# Absent too long, or an assault that never resolved itself: either way the
	# sector was not defended and it falls.
	if _ca_away >= CA_ABSENT_SECONDS or _ca_elapsed >= CA_MAX_SECONDS:
		_resolve_counter_attack(false)
		return

	if _ca_pending <= 0 and alive <= 0:
		# Either the assault was broken, or it never found a single spot it could
		# form up on unseen. Both leave the sector in the player's hands; only
		# the first one pays.
		_resolve_counter_attack(true)


## Drops dead and freed squads and returns how many attackers are still up.
func _prune_counter_squads() -> int:
	var alive: int = 0
	var index: int = _ca_squads.size() - 1
	while index >= 0:
		# Validity is checked on the RAW entry, before any cast: assigning a
		# freed object into a typed variable is itself the error.
		var raw: Variant = _ca_squads[index]
		if raw == null or not is_instance_valid(raw):
			_ca_squads.remove_at(index)
			index -= 1
			continue
		var squad: Squad = raw
		var count: int = squad.alive_count()
		if count <= 0:
			_ca_squads.remove_at(index)
		else:
			alive += count
		index -= 1
	return alive


func _resolve_counter_attack(held: bool) -> void:
	var sector: int = _ca_sector
	# How many squads actually reached the ground, read before the state is
	# wiped: an assault nobody ever saw is not a victory to be paid for.
	var landed: int = _ca_spawned
	_drop_counter_orders()
	_ca_state = CA_IDLE
	_ca_sector = -1
	_ca_timer = 0.0
	_ca_pending = 0
	_ca_spawned = 0
	_ca_away = 0.0
	_ca_elapsed = 0.0
	_ca_player_down = false
	if sector < 0:
		_ca_squads.clear()
		return
	var place: String = _place_name(sector)
	if held:
		_ca_squads.clear()
		# The signal is emitted either way, always exactly once per announced
		# counter attack, or the HUD would keep a banner it can never take down.
		if landed > 0:
			event_announced.emit("Contre-attaque repoussée, %s tient." % place)
			# The reward for holding: the cache is worth walking to again.
			_reward_cache(sector)
	else:
		# NEVER an undo of the capture. `War.capture_sector` stays idempotent,
		# the objective chain of the sector stays earned, and what the player
		# lost is the quiet of the sector, not the sector.
		War.mark_contested(sector)
		_reoccupy(sector)
		event_announced.emit("%s retombe aux mains de la Wehrmacht." % place)
	counter_attack_resolved.emit(sector, held)


func _drop_counter_orders() -> void:
	var index: int = _orders.size() - 1
	while index >= 0:
		var order: _Order = _orders[index]
		if order.counter:
			_orders.remove_at(index)
		index -= 1


## A lost sector gets a thinned garrison back, and the survivors of the assault
## ARE that garrison: turning them around costs nothing, where despawning them
## to spawn a garrison would pay for the same men twice.
func _reoccupy(sector_id: int) -> void:
	var site: Layout.Site = _site_of(sector_id)
	if site == null:
		_ca_squads.clear()
		return
	_garrison_left[sector_id] = maxi(CA_GARRISON_MIN,
			int(round(float(site.garrison) * CA_GARRISON_SHARE)))
	# The Resistance cell goes to ground and takes its cache with it. Both come
	# back on their own once the sector is cleared again.
	_ally_done.erase(sector_id)
	_release_allies(sector_id)
	_remove_cache(sector_id)

	var center: Vector3 = _site_anchor(site)
	var radius: float = maxf(20.0, site.radius * 0.8)
	var list: Array = _garrison_squads.get(sector_id, [])
	for entry in _ca_squads:
		if entry == null or not is_instance_valid(entry):
			continue
		var squad: Squad = entry
		if squad.alive_count() <= 0:
			continue
		squad.order_defend(center, radius)
		list.append(squad)
		for member in squad.members:
			if member == null or not is_instance_valid(member):
				continue
			_soldier_site[member.get_instance_id()] = sector_id
			member.set_home_site(sector_id)
	_garrison_squads[sector_id] = list
	_ca_squads.clear()


func _release_allies(sector_id: int) -> void:
	var squads: Array = _garrison_squads.get(sector_id, [])
	for entry in squads.duplicate():
		if entry == null or not is_instance_valid(entry):
			continue
		var squad: Squad = entry
		if squad.faction == War.ALLIED:
			_release_squad(squad)


# ---------------------------------------------------------------------------
# Resistance caches
# ---------------------------------------------------------------------------

func _ensure_cache(site: Layout.Site, built: SiteBuilder.BuiltSite) -> void:
	var raw: Variant = _caches.get(site.id)
	if raw != null and is_instance_valid(raw):
		return
	var cache := _Cache.new()
	cache.name = "Cache%d" % site.id
	add_child(cache)
	cache.global_position = _cache_spot(site, built)
	cache.setup(site.id)
	cache.used.connect(_on_cache_used)
	_caches[site.id] = cache


## Beside the flag rather than on it, and always the same spot for a given
## sector, so the player learns where his supplies live.
func _cache_spot(site: Layout.Site, built: SiteBuilder.BuiltSite) -> Vector3:
	var at: Vector3 = _site_anchor(site)
	var anchor: Variant = built.objective_anchors.get(MissionDefs.ANCHOR_FLAG)
	if typeof(anchor) == TYPE_VECTOR3:
		at = anchor
	var angle: float = float(site.id) * 1.37
	var spot: Vector3 = at + Vector3(cos(angle), 0.0, sin(angle)) * 2.6
	spot = Heightfield.clamp_to_bounds(spot)
	spot.y = _world.ground_y(spot.x, spot.z)
	return spot


func _remove_cache(site_id: int) -> void:
	var raw: Variant = _caches.get(site_id)
	_caches.erase(site_id)
	if raw == null or not is_instance_valid(raw):
		return
	var cache: _Cache = raw
	if cache.used.is_connected(_on_cache_used):
		cache.used.disconnect(_on_cache_used)
	cache.queue_free()


func _reward_cache(site_id: int) -> void:
	var raw: Variant = _caches.get(site_id)
	if raw == null or not is_instance_valid(raw):
		return
	var cache: _Cache = raw
	cache.start_cooldown(0.0)


func _tick_caches(delta: float) -> void:
	if _caches.is_empty():
		return
	for site_id in _caches.keys():
		var raw: Variant = _caches[site_id]
		if raw == null or not is_instance_valid(raw):
			_caches.erase(site_id)
			continue
		var cache: _Cache = raw
		cache.tick(delta)


func _on_cache_used(cache: Node, user: Node) -> void:
	if cache == null or not is_instance_valid(cache):
		return
	var box: _Cache = cache as _Cache
	if box == null:
		return
	if user == null or not is_instance_valid(user):
		return
	var player: Player = user as Player
	if player == null:
		return
	if not box.is_ready():
		Sfx.play_at("ui_click", box.global_position, -9.0, 0.7)
		return
	var given: int = _restock(player)
	if given <= 0:
		# Nothing left to give: the cache is not spent for a wasted trip.
		Sfx.play_at("ui_click", box.global_position, -9.0, 0.9)
		return
	box.start_cooldown(CACHE_COOLDOWN)
	Sfx.play_at("reload_in", box.global_position, -2.0, 0.95)
	event_announced.emit("Cache de la Résistance: munitions et grenades au complet.")


## Fills the reserve of every weapon the player carries, grenades included,
## through the public path so the HUD hears about it. Returns how many rounds
## were actually handed over.
func _restock(player: Player) -> int:
	var given: int = 0
	for entry in player.weapons:
		if entry == null:
			continue
		var weapon: Weapon = entry
		if weapon.id == WeaponDefs.NONE:
			continue
		given += player.give_ammo(weapon.id, WeaponDefs.reserve_max(weapon.id))
	return given


# ---------------------------------------------------------------------------
# Sites
# ---------------------------------------------------------------------------

func _site_of(site_id: int) -> Layout.Site:
	if _world == null or site_id < 0:
		return null
	var layout: Layout = _world.layout()
	if layout == null:
		return null
	return layout.site_by_id(site_id)


func _sector_center(sector_id: int) -> Vector3:
	var site: Layout.Site = _site_of(sector_id)
	if site == null:
		return _player_pos
	return _site_anchor(site)


func _place_name(site_id: int) -> String:
	var site: Layout.Site = _site_of(site_id)
	if site == null or site.display_name.is_empty():
		return "ce secteur"
	return site.display_name


# ---------------------------------------------------------------------------
# Ambience
# ---------------------------------------------------------------------------

func _fire_ambience() -> void:
	if _player == null or not is_instance_valid(_player):
		return
	var roll: int = _rng.randi_range(0, 99)
	var event: int = EV_ARTILLERY
	if roll < 30:
		event = EV_ARTILLERY
	elif roll < 52:
		event = EV_PLANE
	elif roll < 70:
		event = EV_CONVOY
	elif roll < 84:
		event = EV_PATROL
	else:
		event = EV_BIRDS

	if event == EV_BIRDS and _light_level() < 0.35:
		event = EV_ARTILLERY          # no birdsong at night

	match event:
		EV_ARTILLERY:
			_event_artillery()
		EV_PLANE:
			_event_plane()
		EV_CONVOY:
			_queue_patrol(true)
		EV_PATROL:
			_event_patrol_voice()
		EV_BIRDS:
			_event_birds()


func _event_artillery() -> void:
	var angle: float = _rng.randf() * TAU
	var direction := Vector3(cos(angle), 0.0, sin(angle))
	var center: Vector3 = _player_pos + direction * _rng.randf_range(280.0, 580.0)
	center = Heightfield.clamp_to_bounds(center)
	center.y = _world.ground_y(center.x, center.z)

	Sfx.play_at("distant_battle", center, -2.0, _rng.randf_range(0.85, 1.05))
	_cue("artillery_incoming", center, 0.6, -4.0, 1.0, 0.0)

	var salvo: int = _rng.randi_range(4, 7)
	for i in salvo:
		var spread := Vector3(_rng.randf_range(-60.0, 60.0), 0.0, _rng.randf_range(-60.0, 60.0))
		var at: Vector3 = Heightfield.clamp_to_bounds(center + spread)
		at.y = _world.ground_y(at.x, at.z)
		_cue("artillery_hit", at, 1.4 + float(i) * _rng.randf_range(0.5, 1.4), 2.0,
				_rng.randf_range(0.85, 1.1), _rng.randf_range(6.0, 11.0))

	event_announced.emit("Bombardement lointain %s." % _compass_word(direction))


func _event_plane() -> void:
	if _plane_left > 0.0:
		return
	_build_plane()
	if _plane == null:
		return
	var angle: float = _rng.randf() * TAU
	_plane_dir = Vector3(cos(angle), 0.0, sin(angle))
	var side: Vector3 = _plane_dir.rotated(Vector3.UP, PI * 0.5)
	var start: Vector3 = _player_pos - _plane_dir * (PLANE_RUN * 0.5) \
			+ side * _rng.randf_range(-150.0, 150.0)
	start.y = _player_pos.y + PLANE_ALTITUDE + _rng.randf_range(-25.0, 45.0)
	_plane.global_position = start
	_plane.look_at(start + _plane_dir, Vector3.UP)
	_plane.visible = true
	_plane_left = PLANE_RUN / PLANE_SPEED
	_plane_sound = 0.0
	event_announced.emit("Un appareil traverse le ciel vers %s." % _compass_word(_plane_dir))


func _event_patrol_voice() -> void:
	var best: Squad = null
	var best_distance: float = 220.0
	for squad in _squads:
		if squad == null or not is_instance_valid(squad) or squad.faction != War.AXIS:
			continue
		if squad.alive_count() <= 0 or _engaged(squad):
			continue
		var d: float = squad.center().distance_to(_player_pos)
		if d > 70.0 and d < best_distance:
			best_distance = d
			best = squad
	if best == null:
		return
	var at: Vector3 = best.center()
	for i in 3:
		_cue("german_shout", at, float(i) * _rng.randf_range(1.2, 2.4), -6.0,
				_rng.randf_range(0.85, 1.15), 0.0)


func _event_birds() -> void:
	for i in _rng.randi_range(3, 6):
		var offset := Vector3(_rng.randf_range(-38.0, 38.0), _rng.randf_range(2.0, 9.0),
				_rng.randf_range(-38.0, 38.0))
		_cue("bird", _player_pos + offset, float(i) * _rng.randf_range(0.4, 1.6), -5.0,
				_rng.randf_range(0.9, 1.25), 0.0)


func _cue(sample: String, at: Vector3, delay: float, volume: float, pitch: float,
		blast: float) -> void:
	var cue := _Cue.new()
	cue.sample = sample
	cue.position = at
	cue.delay = delay
	cue.volume = volume
	cue.pitch = pitch
	cue.blast = blast
	_cues.append(cue)


func _tick_cues(delta: float) -> void:
	if _cues.is_empty():
		return
	var i: int = _cues.size() - 1
	while i >= 0:
		var cue: _Cue = _cues[i]
		cue.delay -= delta
		if cue.delay <= 0.0:
			Sfx.play_at(cue.sample, cue.position, cue.volume, cue.pitch)
			if cue.blast > 0.0:
				var vfx: Node = _vfx()
				if vfx != null:
					vfx.explosion(cue.position + Vector3.UP * 0.6, cue.blast)
					vfx.smoke_column(cue.position, 14.0)
			_cues.remove_at(i)
		i -= 1


func _tick_plane(delta: float) -> void:
	if _plane == null or not is_instance_valid(_plane) or _plane_left <= 0.0:
		return
	_plane_left -= delta
	_plane.global_position += _plane_dir * PLANE_SPEED * delta
	_plane_sound -= delta
	if _plane_sound <= 0.0:
		_plane_sound = PLANE_SOUND_GAP
		# No engine sample exists in the bank, so the deep rumble of the distant
		# battle is pitched right down into a droning motor.
		Sfx.play_at("distant_battle", _plane.global_position, -3.0, 0.4)
	if _plane_left <= 0.0:
		_plane.visible = false


func _build_plane() -> void:
	if _plane != null and is_instance_valid(_plane):
		return
	var root := Node3D.new()
	root.name = "AmbientPlane"
	var material: Material = MatLib.get_material("metal")

	var fuselage := MeshInstance3D.new()
	var body := BoxMesh.new()
	body.size = Vector3(2.0, 2.2, 12.0)
	fuselage.mesh = body
	fuselage.material_override = material
	root.add_child(fuselage)

	var wings := MeshInstance3D.new()
	var wing := BoxMesh.new()
	wing.size = Vector3(17.0, 0.5, 2.6)
	wings.mesh = wing
	wings.position = Vector3(0.0, 0.1, 0.6)
	wings.material_override = material
	root.add_child(wings)

	var tail := MeshInstance3D.new()
	var fin := BoxMesh.new()
	fin.size = Vector3(5.0, 0.4, 1.6)
	tail.mesh = fin
	tail.position = Vector3(0.0, 0.7, -5.2)
	tail.material_override = material
	root.add_child(tail)

	root.visible = false
	add_child(root)
	_plane = root


func _compass_word(direction: Vector3) -> String:
	var angle: float = atan2(direction.x, -direction.z)
	if angle < 0.0:
		angle += TAU
	var index: int = int(round(angle / (PI * 0.25))) % 8
	match index:
		0:
			return "au nord"
		1:
			return "au nord-est"
		2:
			return "à l'est"
		3:
			return "au sud-est"
		4:
			return "au sud"
		5:
			return "au sud-ouest"
		6:
			return "à l'ouest"
	return "au nord-ouest"


func _light_level() -> float:
	var parent: Node = get_parent()
	if parent == null:
		return 1.0
	var sky: Node = parent.get_node_or_null("Sky")
	if sky != null and sky.has_method("light_level"):
		return sky.light_level()
	return 1.0


func _vfx() -> Node:
	var nodes: Array = get_tree().get_nodes_in_group("vfx")
	if nodes.is_empty():
		return null
	return nodes[0]


func _exit_tree() -> void:
	_ready_to_run = false
