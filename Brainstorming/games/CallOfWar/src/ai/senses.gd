## Shared perception rules for every AI combatant.
##
## The whole point of this file is that the AI is NOT omniscient. A soldier
## only sees what a real pair of eyes could see: something inside a forward
## cone, close enough for the current light and weather, with nothing solid in
## between. A crouched target hides better than a standing one, a running one
## gives itself away, and a pitch black night cuts the useful range to about a
## fifth of the daylight value.
##
## Everything here is static and side effect free so it can be called from any
## soldier, any frame, without allocating state.
class_name Senses
extends RefCounted

## Sight cone half angle in radians (about 60 degrees each side).
const FOV_HALF := 1.05

## Hard ceiling: nothing is ever spotted past this, whatever the modifiers.
const ABSOLUTE_MAX_RANGE := 420.0
## Nothing is ever spotted closer than this either (used as a floor so a
## soldier is never blind in a storm at midnight).
const MINIMUM_RANGE := 6.0
## Inside this radius the observer notices a target even outside its cone:
## breathing, footsteps and shadows work at arm's length.
const PERIPHERAL_RADIUS := 3.2

## Fraction of the base range still usable in total darkness.
const NIGHT_FLOOR := 0.20
## Extra range multiplier a moving target gives away, at full sprint.
const MOTION_BONUS := 0.30

## Stance identifiers, matching Player.stance (0 stand, 1 crouch, 2 prone).
const STANCE_STAND := 0
const STANCE_CROUCH := 1
const STANCE_PRONE := 2

## How much of the sight range survives for each stance.
const STANCE_FACTOR: PackedFloat32Array = [1.0, 0.62, 0.38]

## Vertical offset of the second line of sight attempt: when the chest is
## covered the head may still poke out above a wall.
const SECOND_PROBE_UP := 0.38


## Can the observer see `target` right now? Accounts for distance, cone, line of
## sight, light level and weather.
##
## `eye` is the observer eye position in world space, `facing` its forward
## vector, `target_point` the point actually looked for (usually the chest).
## `light` comes from SkyController.light_level(), `visibility` from
## Weather.sight_factor().
static func can_see(observer: Node3D, eye: Vector3, facing: Vector3,
		target: Node3D, target_point: Vector3, max_range: float,
		light: float, visibility: float) -> bool:
	if observer == null or target == null:
		return false
	if not is_instance_valid(observer) or not is_instance_valid(target):
		return false
	if not observer.is_inside_tree():
		return false
	if target.has_method("is_alive") and not bool(target.call("is_alive")):
		return false

	var to_target := target_point - eye
	var distance := to_target.length()
	if distance < 0.05:
		return true

	var usable := sight_range(max_range, light, visibility)
	usable *= stance_factor(target)
	usable *= motion_factor(target)
	if distance > usable:
		return false

	if distance > PERIPHERAL_RADIUS:
		var flat_facing := facing
		if flat_facing.length_squared() < 0.000001:
			return false
		flat_facing = flat_facing.normalized()
		var direction := to_target / distance
		if direction.dot(flat_facing) < cos(FOV_HALF):
			return false

	if _segment_clear(observer, target, eye, target_point):
		return true
	# Second chance a bit higher: a head above a low wall is still a head.
	return _segment_clear(observer, target, eye,
			target_point + Vector3(0.0, SECOND_PROBE_UP, 0.0))


## Sight range in metres for a given light level and weather factor.
##
## `light` is 0 (pitch black) to 1 (full noon), `visibility` is 1 for a clear
## sky down to about 0.35 in a storm.
static func sight_range(base_range: float, light: float, visibility: float) -> float:
	var lit := clampf(light, 0.0, 1.0)
	var seen := clampf(visibility, 0.05, 1.0)
	# sqrt() keeps dusk usable instead of dropping off a cliff at sunset.
	var light_factor := NIGHT_FLOOR + (1.0 - NIGHT_FLOOR) * sqrt(lit)
	var result := maxf(0.0, base_range) * light_factor * seen
	return clampf(result, MINIMUM_RANGE, ABSOLUTE_MAX_RANGE)


## Did the observer hear a noise of `radius` metres emitted at `at`?
static func can_hear(ear: Vector3, at: Vector3, radius: float) -> bool:
	if radius <= 0.0:
		return false
	return ear.distance_squared_to(at) <= radius * radius


## Sight range multiplier coming from the target stance. Reads `stance` when
## the target exposes it (Player), then `is_crouched` (Soldier), else standing.
static func stance_factor(target: Node3D) -> float:
	if target == null:
		return 1.0
	if "stance" in target:
		var raw: int = clampi(int(target.get("stance")), 0, STANCE_FACTOR.size() - 1)
		return STANCE_FACTOR[raw]
	if "is_crouched" in target and bool(target.get("is_crouched")):
		return STANCE_FACTOR[STANCE_CROUCH]
	return 1.0


## Sight range multiplier coming from the target motion: standing still in a
## hedge is a lot safer than running across a field.
static func motion_factor(target: Node3D) -> float:
	if target == null:
		return 1.0
	if not ("velocity" in target):
		return 1.0
	var vel: Vector3 = target.get("velocity")
	var horizontal := Vector2(vel.x, vel.z).length()
	return 1.0 + MOTION_BONUS * clampf(horizontal / 6.0, 0.0, 1.0)


## How loud a walking body is, in metres of hearing radius. Kept here so the
## soldier and the director agree on the numbers.
static func step_noise_radius(speed: float, crouched: bool) -> float:
	var base := clampf(speed * 3.4, 0.0, 26.0)
	if crouched:
		base *= 0.45
	return base


## True when nothing solid blocks the segment. Bodies (player, soldiers) are
## not part of SIGHT_MASK so a crowd never blinds anybody.
static func _segment_clear(observer: Node3D, target: Node3D, from: Vector3,
		to: Vector3) -> bool:
	var world := observer.get_world_3d()
	if world == null:
		return false
	var space := world.direct_space_state
	if space == null:
		return false
	var query := PhysicsRayQueryParameters3D.create(from, to, Layers.SIGHT_MASK)
	query.collide_with_areas = false
	query.collide_with_bodies = true
	var excluded: Array[RID] = []
	var observer_body := observer as CollisionObject3D
	if observer_body != null:
		excluded.append(observer_body.get_rid())
	var target_body := target as CollisionObject3D
	if target_body != null:
		excluded.append(target_body.get_rid())
	query.exclude = excluded
	return space.intersect_ray(query).is_empty()
