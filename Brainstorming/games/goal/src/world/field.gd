class_name Field
extends RefCounted
## Pure geometry of the pitch and of the goal. No nodes, no dependencies.
##
## This is the oracle everybody asks "did it go in". Keeping it free of nodes
## matters for two reasons: the keeper's mental model and the HUD preview need
## the same answers as the real ball without owning a scene, and the whole thing
## stays testable headless.
##
## Frame of reference (contract section 1): the shooter looks towards -Z, the
## goal line is the plane z = 0, the mouth is in z < 0, +X is the shooter's
## right. One unit is one metre.
##
## The frame itself is modelled as three capsules of radius POST_RADIUS: two
## vertical posts standing on the goal line and one horizontal bar joining their
## tops. Post centres sit OUTSIDE the 7.32 m mouth (the regulation width is
## measured between the inner faces), which is why POST_X is GOAL_HALF plus one
## radius. That detail is what makes a ball clipping the inside of a post go in
## and the same ball two centimetres wider come back out.

const GOAL_WIDTH   := 7.32
const GOAL_HEIGHT  := 2.44
const GOAL_HALF    := 3.66          # GOAL_WIDTH * 0.5
const POST_RADIUS  := 0.06
const NET_DEPTH    := 2.00
const NET_BACK_TOP := 2.10
const BALL_RADIUS  := 0.11
const SPOT_Z       := 11.00
const BOX_DEPTH    := 16.50
const BOX_HALF     := 20.16
const SIX_DEPTH    := 5.50
const SIX_HALF     := 9.16
const ARC_RADIUS   := 9.15
const PITCH_MIN_Z  := -6.0
const PITCH_MAX_Z  := 62.0
const PITCH_HALF_X := 34.0

## Where the ball sits before the run up.
const SPOT := Vector3(0.0, BALL_RADIUS, SPOT_Z)
## Where the keeper stands before committing.
const KEEPER_HOME := Vector3(0.0, 0.0, 0.12)

## Derived frame geometry, so nobody re-derives it wrongly.
## Distance from the centre of the goal to the AXIS of a post.
const POST_X := GOAL_HALF + POST_RADIUS         # 3.72
## Height of the crossbar AXIS. The underside of the bar is at GOAL_HEIGHT.
const BAR_Y := GOAL_HEIGHT + POST_RADIUS        # 2.50
## Length of a post from the turf to the bar axis, and of the bar itself.
const POST_LENGTH := BAR_Y
const BAR_LENGTH := POST_X * 2.0

## Anything above this is a balloon, not a shot, and anything outside the built
## area is gone. Used by is_out_of_area to stop the simulation.
const CEILING := 40.0
const FLOOR_LIMIT := -2.0

const FRAME_NONE  := 0
const FRAME_POST_LEFT  := 1     # the -X post
const FRAME_POST_RIGHT := 2     # the +X post
const FRAME_BAR   := 3

## Every part of the frame, in test order.
const FRAME_PARTS: Array[int] = [FRAME_POST_LEFT, FRAME_POST_RIGHT, FRAME_BAR]

## Below this the maths is degenerate and we bail out rather than divide.
const _EPSILON := 0.000001


## Centre of a post. `side` is -1 for the -X post, +1 for the +X post.
## The returned point is the middle of the post axis, so a capsule mesh of
## length POST_LENGTH placed there lines up with the collision model.
static func post_centre(side: int) -> Vector3:
	var sign_x := -1.0 if side < 0 else 1.0
	return Vector3(sign_x * POST_X, POST_LENGTH * 0.5, 0.0)


## True when a ball centre at this point has fully crossed the goal line into
## the mouth. Uses the ball radius, so the whole ball must be over the line.
static func is_inside_mouth(point: Vector3) -> bool:
	if point.z > -BALL_RADIUS:
		return false
	# Past the back of the net it is no longer "in the mouth", it is out of the
	# world, and treating it as a goal would hide a tunnelling bug.
	if point.z < -(NET_DEPTH + 1.0):
		return false
	return is_within_frame(point)


## True when the point is between the posts and under the bar, ignoring z.
## This is the frame test used while the ball is still travelling.
static func is_within_frame(point: Vector3) -> bool:
	if absf(point.x) > GOAL_HALF:
		return false
	return point.y >= 0.0 and point.y <= GOAL_HEIGHT


## The two endpoints of one frame part's axis, in world space.
static func _part_endpoints(part: int) -> PackedVector3Array:
	match part:
		FRAME_POST_LEFT:
			return PackedVector3Array([
				Vector3(-POST_X, 0.0, 0.0),
				Vector3(-POST_X, BAR_Y, 0.0),
			])
		FRAME_POST_RIGHT:
			return PackedVector3Array([
				Vector3(POST_X, 0.0, 0.0),
				Vector3(POST_X, BAR_Y, 0.0),
			])
		FRAME_BAR:
			return PackedVector3Array([
				Vector3(-POST_X, BAR_Y, 0.0),
				Vector3(POST_X, BAR_Y, 0.0),
			])
	return PackedVector3Array()


## Closest point of segment [a, b] to `p`.
static func _closest_on_segment(p: Vector3, a: Vector3, b: Vector3) -> Vector3:
	var ab := b - a
	var denom := ab.length_squared()
	if denom < _EPSILON:
		return a
	var t := clampf((p - a).dot(ab) / denom, 0.0, 1.0)
	return a + ab * t


## Closest point of the goal frame (both posts plus the bar) to `point`, and the
## distance to it. Returns {"point": Vector3, "distance": float, "part": int}.
## `point` is on the SURFACE of the frame and `distance` is measured to that
## surface, so it is negative when `point` is inside the tube.
static func nearest_frame(point: Vector3) -> Dictionary:
	var best_part := FRAME_NONE
	var best_axis := Vector3.ZERO
	var best_axis_distance := INF
	for part in FRAME_PARTS:
		var ends := _part_endpoints(part)
		var candidate := _closest_on_segment(point, ends[0], ends[1])
		var d := point.distance_to(candidate)
		if d < best_axis_distance:
			best_axis_distance = d
			best_axis = candidate
			best_part = part
	var outward := point - best_axis
	if outward.length_squared() < _EPSILON:
		# Dead on the axis: any direction is as good as another, pick the one
		# facing the shooter so the caller never gets a zero vector.
		outward = Vector3(0.0, 0.0, 1.0)
	else:
		outward = outward.normalized()
	return {
		"point": best_axis + outward * POST_RADIUS,
		"distance": best_axis_distance - POST_RADIUS,
		"part": best_part,
	}


## Builds the contact answer shared by every branch of the sweep. `ball_centre`
## is where the ball centre sits at contact, `axis_point` the closest point of
## the capsule axis at that instant. The normal is the direction from the axis
## to the ball, never a guess: that is what makes an inside clip deflect into
## the goal and an outside clip deflect away.
static func _contact(ball_centre: Vector3, axis_point: Vector3, t: float, fallback: Vector3) -> Dictionary:
	var normal := ball_centre - axis_point
	if normal.length_squared() < _EPSILON:
		normal = fallback if fallback.length_squared() > _EPSILON else Vector3(0.0, 0.0, 1.0)
	normal = normal.normalized()
	return {
		"hit": true,
		"t": clampf(t, 0.0, 1.0),
		"point": axis_point + normal * POST_RADIUS,
		"normal": normal,
	}


static func _miss(from: Vector3) -> Dictionary:
	return {"hit": false, "t": 1.0, "point": from, "normal": Vector3.UP}


## Swept sphere against one sphere of radius `radius` centred on `centre`.
## Used for the capsule end caps.
static func _sweep_sphere(p0: Vector3, p1: Vector3, centre: Vector3, radius: float) -> Dictionary:
	var m := p0 - centre
	var n := p1 - p0
	var nn := n.dot(n)
	if nn < _EPSILON:
		if m.length() <= radius:
			return _contact(p0, centre, 0.0, -n)
		return _miss(p0)
	var b := m.dot(n)
	var c := m.dot(m) - radius * radius
	var disc := b * b - nn * c
	if disc < 0.0:
		return _miss(p0)
	var t := (-b - sqrt(disc)) / nn
	if t < 0.0 or t > 1.0:
		return _miss(p0)
	return _contact(p0 + n * t, centre, t, -n)


## Swept sphere (implicit, the ball) against one capsule axis [a, b].
## `radius` must already be the sum of the ball radius and the capsule radius,
## which turns the problem into a segment against a capsule surface.
##
## Classic three part test: the infinite cylinder around the axis, then either
## end cap when the cylinder solution falls outside the axis band. The earliest
## time the ball enters the infinite cylinder is always at or before the time it
## enters the capsule, because a point inside an end cap is by construction
## within `radius` of the axis line, so this ordering is exact and not an
## approximation.
static func _sweep_capsule(p0: Vector3, p1: Vector3, a: Vector3, b: Vector3, radius: float) -> Dictionary:
	var d := b - a
	var m := p0 - a
	var n := p1 - p0
	var dd := d.dot(d)
	if dd < _EPSILON:
		return _sweep_sphere(p0, p1, a, radius)

	# Already touching at the start of the step: report an immediate contact so
	# a ball that somehow began inside the tube is pushed out instead of being
	# swallowed by it.
	var start_axis := _closest_on_segment(p0, a, b)
	if p0.distance_to(start_axis) <= radius:
		return _contact(p0, start_axis, 0.0, -n)

	var nn := n.dot(n)
	if nn < _EPSILON:
		return _miss(p0)

	var md := m.dot(d)
	var nd := n.dot(d)
	var ka := dd * nn - nd * nd
	if ka < _EPSILON:
		# The step runs parallel to the axis: only the caps can be reached.
		var cap_a := _sweep_sphere(p0, p1, a, radius)
		var cap_b := _sweep_sphere(p0, p1, b, radius)
		if bool(cap_a["hit"]) and bool(cap_b["hit"]):
			return cap_a if float(cap_a["t"]) <= float(cap_b["t"]) else cap_b
		if bool(cap_a["hit"]):
			return cap_a
		return cap_b

	var kb := dd * m.dot(n) - nd * md
	var kc := dd * (m.dot(m) - radius * radius) - md * md
	var disc := kb * kb - ka * kc
	if disc < 0.0:
		return _miss(p0)
	# ka is positive here, so this root is the smaller one, the entry.
	var t := (-kb - sqrt(disc)) / ka
	if t > 1.0 or t < 0.0:
		return _miss(p0)
	var proj := md + t * nd
	if proj < 0.0:
		return _sweep_sphere(p0, p1, a, radius)
	if proj > dd:
		return _sweep_sphere(p0, p1, b, radius)
	return _contact(p0 + n * t, a + d * (proj / dd), t, -n)


## Does a ball moving from `from` to `to` over one step touch the frame?
## Returns {"hit": bool, "part": int, "point": Vector3, "normal": Vector3, "t": float}
## `t` is the fraction of the step at contact, `normal` points away from the frame.
static func sweep_frame(from: Vector3, to: Vector3) -> Dictionary:
	var result := {
		"hit": false,
		"part": FRAME_NONE,
		"point": to,
		"normal": Vector3.UP,
		"t": 1.0,
	}
	var best_t := INF
	var radius := POST_RADIUS + BALL_RADIUS
	for part in FRAME_PARTS:
		var ends := _part_endpoints(part)
		var contact := _sweep_capsule(from, to, ends[0], ends[1], radius)
		if not bool(contact["hit"]):
			continue
		var t := float(contact["t"])
		if t < best_t:
			best_t = t
			result = {
				"hit": true,
				"part": part,
				"point": contact["point"],
				"normal": contact["normal"],
				"t": t,
			}
	return result


## Does the segment cross the goal plane z = 0 travelling towards -Z?
## Returns {"crossed": bool, "point": Vector3, "t": float}
static func cross_goal_plane(from: Vector3, to: Vector3) -> Dictionary:
	if from.z <= 0.0 or to.z > 0.0:
		return {"crossed": false, "point": to, "t": 1.0}
	var travel := from.z - to.z
	if travel < _EPSILON:
		return {"crossed": false, "point": to, "t": 1.0}
	var t := clampf(from.z / travel, 0.0, 1.0)
	return {"crossed": true, "point": from.lerp(to, t), "t": t}


## Signed distance from the mouth rectangle, in metres. Negative inside, positive
## outside. Used by the HUD to colour the aim reticle.
static func mouth_margin(point: Vector3) -> float:
	var dx := absf(point.x) - GOAL_HALF
	var dy := absf(point.y - GOAL_HEIGHT * 0.5) - GOAL_HEIGHT * 0.5
	# Standard rectangle signed distance: the outside part is a real distance in
	# the corner region, the inside part is the distance to the nearest edge.
	var outside := Vector2(maxf(dx, 0.0), maxf(dy, 0.0)).length()
	var inside := minf(maxf(dx, dy), 0.0)
	return outside + inside


## Is the ball still in play, or has it left the built area entirely?
static func is_out_of_area(point: Vector3) -> bool:
	if absf(point.x) > PITCH_HALF_X:
		return true
	if point.z < PITCH_MIN_Z or point.z > PITCH_MAX_Z:
		return true
	return point.y > CEILING or point.y < FLOOR_LIMIT


## Human readable French name of a mouth region, for the verdict text.
## Left and right are the SHOOTER's, because the player is the shooter: aiming
## left must be described as left.
static func mouth_region_name(point: Vector3) -> String:
	if not is_within_frame(point):
		return "hors cadre"
	var left := point.x < 0.0
	var wide := absf(point.x) >= GOAL_HALF * 0.5
	var high := point.y >= GOAL_HEIGHT * 0.62
	var low := point.y <= GOAL_HEIGHT * 0.3
	if wide and high:
		# "lucarne" is feminine, "filet" is masculine. French grammar is part of
		# the contract here, the HUD prints these strings as they are.
		return "lucarne gauche" if left else "lucarne droite"
	if wide:
		return "petit filet gauche" if left else "petit filet droit"
	if low:
		return "au ras du sol"
	return "plein centre"
