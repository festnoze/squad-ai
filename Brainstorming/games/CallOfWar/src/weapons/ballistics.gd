## Hitscan ballistics: the single place in CALL OF WAR where a bullet exists.
##
## Everything that shoots (the player, every soldier, the MG 42 nests) goes
## through `fire()`, which means dispersion, penetration, headshots, falloff
## and damage all behave identically whoever pulled the trigger. There is no
## dependency on the HUD or on the AI here, only on the physics world.
##
## Design notes worth keeping:
##   - dispersion samples a point in a disc and rebuilds an orthonormal basis
##     around the aim direction. Adding random angles to yaw and pitch instead
##     produces a square, pole pinched cone that feels wrong at high spread;
##   - penetration re raycasts from just behind the surface with the pierced
##     collider excluded, up to MAX_PENETRATIONS times. Wood, sheet metal,
##     sandbags and bodies let a strong round through, stone does not;
##   - every call on a collider is guarded by `has_method`, because this code
##     runs against terrain, trees, walls and crates just as often as against
##     soldiers.
class_name Ballistics
extends RefCounted

## Outcome of a single traced bullet.
class HitResult extends RefCounted:
	var hit: bool = false
	var position: Vector3 = Vector3.ZERO
	var normal: Vector3 = Vector3.UP
	var collider: Object = null
	var distance: float = 0.0
	var headshot: bool = false
	var surface: String = "dirt"

	## Damage actually applied by the bullet, useful for hit markers.
	var damage_dealt: float = 0.0
	## How many surfaces the bullet went through before this one.
	var penetrations: int = 0

## Longest segment traced for one bullet.
const MAX_RANGE := 600.0
## A bullet never goes through more than this many surfaces.
const MAX_PENETRATIONS := 2
## Damage kept after piercing one surface.
const PENETRATION_DAMAGE_KEEP := 0.58
## Bodies and structures an explosion looks for.
const EXPLOSION_MASK := Layers.STRUCTURE | Layers.PLAYER | Layers.ENEMY \
		| Layers.ALLY | Layers.PROP | Layers.VEHICLE
## Explosions are traced from slightly above their centre, otherwise the very
## ground they sit on blocks every single line of sight.
const EXPLOSION_LIFT := 0.30
## The line of sight ray stops this far short of the blast centre. Without it
## the exploding object itself (a grenade is still a physics body during its
## own detonation, queue_free being deferred) blocks every ray it casts.
const EXPLOSION_LOS_MARGIN := 0.55
## Upward bias given to the push of an explosion.
const EXPLOSION_LIFT_PUSH := 0.45

## The six surface names the whole project agrees on.
const SURFACES: PackedStringArray = [
	"dirt", "stone", "wood", "metal", "flesh", "water",
]

## Penetration power required to go through one surface. Anything above 1.0 is
## simply impossible with the weapons of 1942.
const _PENETRATION_COST: Dictionary = {
	"wood": 0.28,
	"metal": 0.55,
	"flesh": 0.42,
	"sandbag": 0.50,
	"dirt": 1.50,
	"stone": 1.50,
	"water": 1.50,
}

## How deep the bullet is pushed before the next trace, per surface.
const _SURFACE_THICKNESS: Dictionary = {
	"wood": 0.16,
	"metal": 0.10,
	"flesh": 0.50,
	"sandbag": 0.65,
}

# --- Firing ----------------------------------------------------------------

## Fires one bullet, applies its damage and returns where it landed.
##
## `spread` is the cone half angle in radians, `shooter` is excluded from the
## trace, and the returned HitResult is never null.
static func fire(world_3d: World3D, origin: Vector3, direction: Vector3,
		weapon_id: int, spread: float, shooter: Node, rng: RandomNumberGenerator) -> HitResult:
	var result := HitResult.new()
	if world_3d == null:
		return result
	var space := world_3d.direct_space_state
	if space == null:
		return result
	if direction.length_squared() < 0.000001:
		return result

	var dir := _spread_direction(direction.normalized(), spread, rng)
	var exclude: Array[RID] = []
	var shooter_body := shooter as CollisionObject3D
	if shooter_body != null:
		exclude.append(shooter_body.get_rid())

	var from := origin
	var travelled := 0.0
	var damage_scale := 1.0
	var pierced := 0
	var first := true

	while true:
		var to := from + dir * (MAX_RANGE - travelled)
		var query := PhysicsRayQueryParameters3D.create(from, to, Layers.BULLET_MASK, exclude)
		query.collide_with_areas = false
		query.collide_with_bodies = true
		query.hit_from_inside = false
		var raw := space.intersect_ray(query)
		if raw.is_empty():
			if first:
				result.position = to
				result.normal = -dir
				result.distance = MAX_RANGE
			break

		var point: Vector3 = raw["position"]
		var normal: Vector3 = raw["normal"]
		var collider: Object = raw.get("collider")
		var surface := surface_of(collider)
		travelled += from.distance_to(point)

		var target := _damage_target(collider)
		var headshot := _is_headshot(target, point)
		var dealt := 0.0
		if target != null:
			dealt = WeaponDefs.damage_at(weapon_id, travelled, headshot) * damage_scale
			target.call("take_damage", dealt, shooter, point, headshot)

		if first:
			result.hit = true
			result.position = point
			result.normal = normal
			result.collider = collider
			result.distance = travelled
			result.headshot = headshot
			result.surface = surface
			result.damage_dealt = dealt
			result.penetrations = 0
			first = false
		else:
			result.damage_dealt += dealt
			result.penetrations = pierced

		_spawn_impact(shooter, point, normal, surface, target != null)

		if pierced >= MAX_PENETRATIONS:
			break
		if not _can_penetrate(collider, surface, WeaponDefs.penetration(weapon_id)):
			break
		var body := collider as CollisionObject3D
		if body != null:
			exclude.append(body.get_rid())
		from = point + dir * _thickness_of(collider, surface)
		travelled += _thickness_of(collider, surface)
		damage_scale *= PENETRATION_DAMAGE_KEEP
		pierced += 1
		if travelled >= MAX_RANGE:
			break

	return result


## Raw line of sight test, no damage. True when nothing blocks the segment.
##
## `ignore` accepts Nodes (CollisionObject3D) as well as raw RIDs, so callers
## can hand in the shooter and the target without converting anything.
static func line_of_sight(world_3d: World3D, from: Vector3, to: Vector3, ignore: Array) -> bool:
	if world_3d == null:
		return false
	var space := world_3d.direct_space_state
	if space == null:
		return false
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.SIGHT_MASK, _to_rids(ignore))
	query.collide_with_areas = false
	query.collide_with_bodies = true
	query.hit_from_inside = false
	return space.intersect_ray(query).is_empty()


## Traces a segment and returns the raw hit, or an empty HitResult. No damage,
## no effects: this is what the AI uses to test a firing position.
static func probe(world_3d: World3D, from: Vector3, to: Vector3, ignore: Array) -> HitResult:
	var result := HitResult.new()
	if world_3d == null:
		return result
	var space := world_3d.direct_space_state
	if space == null:
		return result
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.BULLET_MASK, _to_rids(ignore))
	query.collide_with_areas = false
	var raw := space.intersect_ray(query)
	if raw.is_empty():
		result.position = to
		result.distance = from.distance_to(to)
		return result
	result.hit = true
	result.position = raw["position"]
	result.normal = raw["normal"]
	result.collider = raw.get("collider")
	result.distance = from.distance_to(result.position)
	result.surface = surface_of(result.collider)
	return result

# --- Surfaces --------------------------------------------------------------

## Surface name deduced from the collider, for impact sound and decal colour.
##
## Three sources, in order of trust: an explicit `surface` metadata that any
## builder can set, the groups of the node, then its name and collision layer.
static func surface_of(collider: Object) -> String:
	if collider == null:
		return "dirt"
	var node := collider as Node
	if node == null:
		return "dirt"

	if node.has_meta("surface"):
		var meta_name := _normalise_surface(str(node.get_meta("surface")))
		if meta_name != "":
			return meta_name
	var parent := node.get_parent()
	if parent != null and parent.has_meta("surface"):
		var parent_name := _normalise_surface(str(parent.get_meta("surface")))
		if parent_name != "":
			return parent_name

	if node.is_in_group("damageable") or node.is_in_group("axis") \
			or node.is_in_group("allies") or node.is_in_group("player"):
		return "flesh"
	for group_name in SURFACES:
		if node.is_in_group(group_name):
			return group_name
	if node.is_in_group("tree"):
		return "wood"
	if node.is_in_group("sandbag"):
		return "dirt"

	var lowered := node.name.to_lower()
	if _contains_any(lowered, ["water", "river", "pond", "marsh"]):
		return "water"
	if _contains_any(lowered, ["wood", "plank", "door", "fence", "barn", "tree",
			"trunk", "crate", "beam", "hedge", "haystack", "cage"]):
		return "wood"
	if _contains_any(lowered, ["metal", "steel", "tank", "truck", "wreck", "gun",
			"hangar", "barrel", "fuel", "mast", "wire", "aa_"]):
		return "metal"
	if _contains_any(lowered, ["stone", "wall", "rock", "church", "concrete",
			"bunker", "house", "ruin", "bridge", "tower"]):
		return "stone"
	if _contains_any(lowered, ["sand", "bag", "trench", "dirt", "ground", "road"]):
		return "dirt"

	var body := collider as CollisionObject3D
	if body != null:
		var layer := body.collision_layer
		if (layer & Layers.TERRAIN) != 0:
			return "dirt"
		if (layer & Layers.VEHICLE) != 0:
			return "metal"
		if (layer & (Layers.PLAYER | Layers.ENEMY | Layers.ALLY)) != 0:
			return "flesh"
		if (layer & Layers.STRUCTURE) != 0:
			return "stone"
		if (layer & Layers.PROP) != 0:
			return "wood"
	return "dirt"


## True when the surface name is one of the six the project knows.
static func is_known_surface(surface: String) -> bool:
	return SURFACES.has(surface)


static func _normalise_surface(raw: String) -> String:
	var lowered := raw.to_lower().strip_edges()
	if SURFACES.has(lowered):
		return lowered
	match lowered:
		"sandbag", "sand", "mud", "grass", "soil":
			return "dirt"
		"concrete", "rock", "brick", "plaster", "slate", "tile":
			return "stone"
		"steel", "iron", "tin":
			return "metal"
		"body", "meat", "soldier":
			return "flesh"
		_:
			return ""


static func _contains_any(text: String, needles: Array) -> bool:
	for needle in needles:
		if text.contains(str(needle)):
			return true
	return false

# --- Penetration -----------------------------------------------------------

## True when a round of `power` goes through the surface that was just hit.
static func _can_penetrate(collider: Object, surface: String, power: float) -> bool:
	if power <= 0.0:
		return false
	var key := surface
	var node := collider as Node
	if node != null:
		if node.is_in_group("sandbag"):
			key = "sandbag"
		elif node.has_meta("penetration_cost"):
			return power >= float(node.get_meta("penetration_cost"))
		elif node.is_in_group("penetrable"):
			key = "wood"
		elif node.has_meta("thin") and bool(node.get_meta("thin")):
			key = "metal"
	var cost := float(_PENETRATION_COST.get(key, 1.5))
	return power >= cost


static func _thickness_of(collider: Object, surface: String) -> float:
	var key := surface
	var node := collider as Node
	if node != null and node.is_in_group("sandbag"):
		key = "sandbag"
	return float(_SURFACE_THICKNESS.get(key, 0.20))

# --- Damage targets --------------------------------------------------------

## Walks up from the collider to the first node exposing the damage contract.
## A bunker wall, a soldier hitbox or an emplacement shield all report the
## child body as collider, never the node holding the health.
static func _damage_target(collider: Object) -> Object:
	if collider == null:
		return null
	if collider.has_method("take_damage"):
		return collider
	var node := collider as Node
	var hops := 0
	while node != null and hops < 3:
		node = node.get_parent()
		hops += 1
		if node != null and node.has_method("take_damage"):
			return node
	return null


static func _is_headshot(target: Object, point: Vector3) -> bool:
	if target == null:
		return false
	if not target.has_method("head_height"):
		return false
	return point.y > float(target.call("head_height"))

# --- Dispersion ------------------------------------------------------------

## Samples a direction inside a cone of half angle `spread` around `dir`.
##
## The offset is a uniform point of a disc of radius tan(spread), projected on
## the orthonormal basis built around the aim direction, which keeps the
## distribution round whatever the direction of fire.
static func _spread_direction(dir: Vector3, spread: float, rng: RandomNumberGenerator) -> Vector3:
	if spread <= 0.0:
		return dir
	var reference := Vector3.UP
	if absf(dir.dot(Vector3.UP)) > 0.985:
		reference = Vector3.RIGHT
	var right := dir.cross(reference).normalized()
	var up := right.cross(dir).normalized()
	var angle := _unit(rng) * TAU
	var radius := sqrt(_unit(rng)) * tan(minf(spread, 0.7))
	return (dir + right * (cos(angle) * radius) + up * (sin(angle) * radius)).normalized()


## A number in [0,1) from the caller generator, or from the global one when no
## generator was handed in. Deliberately not a cached static RandomNumberGen:
## a static Object never gets freed and shows up as a leak on exit.
static func _unit(rng: RandomNumberGenerator) -> float:
	if rng == null:
		return randf()
	return rng.randf()

# --- Explosions ------------------------------------------------------------

## Explosion damage in a radius, with square falloff and line of sight checks.
##
## Damage follows `1 - (d/r)^2`, so hugging a grenade is fatal and being at the
## rim is a scratch. A wall between the blast and a target cancels the damage
## entirely: an explosion does not go around corners in this game.
static func explode(world_3d: World3D, center: Vector3, radius: float,
		max_damage: float, source: Node) -> void:
	if world_3d == null or radius <= 0.0:
		return
	var lifted := center + Vector3.UP * EXPLOSION_LIFT
	for target in _explosion_targets(world_3d, center, radius, source):
		var node3d := target as Node3D
		if node3d == null:
			continue
		var point := node3d.global_position
		if node3d.has_method("head_height"):
			point.y = maxf(point.y, float(node3d.call("head_height")) - 0.5)
		else:
			point += Vector3.UP * 0.5
		var distance := lifted.distance_to(point)
		if distance > radius:
			continue
		if not _blast_reaches(world_3d, lifted, point, node3d, source):
			continue
		var ratio := clampf(distance / radius, 0.0, 1.0)
		var falloff := 1.0 - ratio * ratio
		if target.has_method("take_damage"):
			target.call("take_damage", max_damage * falloff, source, point, false)
		_apply_blast_push(node3d, lifted, falloff)
		_shake_viewer(node3d, falloff)


## Every distinct damageable node whose body sits inside the blast sphere.
static func _explosion_targets(world_3d: World3D, center: Vector3, radius: float,
		source: Node) -> Array:
	var found: Array = []
	var seen: Dictionary = {}

	var space := world_3d.direct_space_state
	if space != null:
		var sphere := SphereShape3D.new()
		sphere.radius = radius
		var query := PhysicsShapeQueryParameters3D.new()
		query.shape = sphere
		query.transform = Transform3D(Basis.IDENTITY, center)
		query.collision_mask = EXPLOSION_MASK
		query.collide_with_areas = false
		query.collide_with_bodies = true
		for entry in space.intersect_shape(query, 32):
			var target := _damage_target(entry.get("collider"))
			if target == null:
				continue
			var key := target.get_instance_id()
			if seen.has(key):
				continue
			seen[key] = true
			found.append(target)

	# Belt and braces: a damageable whose body is not on a scanned layer (a
	# radio mast, a fuel dump) still has to take the blast.
	if source != null and source.is_inside_tree():
		var tree := source.get_tree()
		if tree != null:
			for node in tree.get_nodes_in_group("damageable"):
				var node3d := node as Node3D
				if node3d == null:
					continue
				if node3d.global_position.distance_to(center) > radius + 1.5:
					continue
				var key2 := node3d.get_instance_id()
				if seen.has(key2):
					continue
				seen[key2] = true
				found.append(node3d)
	return found


## Line of sight from the target back towards the blast, stopping short of the
## centre so whatever exploded does not shield everybody from itself.
static func _blast_reaches(world_3d: World3D, center: Vector3, point: Vector3,
		target: Node3D, source: Node) -> bool:
	var span := center - point
	var length := span.length()
	if length <= EXPLOSION_LOS_MARGIN:
		return true
	var stop := point + span.normalized() * (length - EXPLOSION_LOS_MARGIN)
	return line_of_sight(world_3d, point, stop, [target, source])


static func _apply_blast_push(node3d: Node3D, from: Vector3, falloff: float) -> void:
	var body := node3d as CharacterBody3D
	if body == null:
		return
	var away := node3d.global_position - from
	if away.length_squared() < 0.0001:
		away = Vector3.UP
	away = away.normalized()
	away.y = maxf(away.y, EXPLOSION_LIFT_PUSH)
	body.velocity += away.normalized() * (9.0 * falloff)


## Shakes the camera of anything that owns a rig, without ever naming the
## camera class: the player is simply the node that has one.
static func _shake_viewer(node3d: Node3D, falloff: float) -> void:
	var rig: Object = node3d.get("rig")
	if rig == null:
		return
	if not rig.has_method("shake"):
		return
	rig.call("shake", 0.05 * falloff, 0.35 + 0.45 * falloff)

# --- Visual feedback -------------------------------------------------------

## Asks the shared Vfx node for an impact burst on world geometry.
##
## Deliberately narrow: a hit that reached something damageable is left alone,
## because a hit body plays its own blood and its own reaction, and a tracer is
## drawn by whoever pulled the trigger from the muzzle he actually owns. This
## is the only feedback nobody else can produce, since only Ballistics knows
## where a bullet stopped in the world.
static func _spawn_impact(shooter: Node, point: Vector3, normal: Vector3,
		surface: String, on_target: bool) -> void:
	if on_target or surface == "flesh":
		return
	var vfx := _find_vfx(shooter)
	if vfx == null:
		return
	vfx.call("impact", point, normal, surface)


static func _find_vfx(shooter: Node) -> Node:
	if shooter == null or not shooter.is_inside_tree():
		return null
	var tree := shooter.get_tree()
	if tree == null:
		return null
	var nodes := tree.get_nodes_in_group("vfx")
	if nodes.is_empty():
		return null
	return nodes[0] as Node

# --- Helpers ---------------------------------------------------------------

static func _to_rids(ignore: Array) -> Array[RID]:
	var out: Array[RID] = []
	for entry in ignore:
		if entry is RID:
			out.append(entry)
			continue
		var body := entry as CollisionObject3D
		if body != null:
			out.append(body.get_rid())
	return out
