class_name Aero
extends RefCounted
## Flight model of the ball. Pure, static, no dependency, no node.
##
## A football does not fly on a parabola, and a penalty game built on one feels
## dead. Three forces act on the ball and all three are modelled here for real:
##
##   1. Gravity, the boring one.
##   2. Quadratic drag, with the drag crisis. The drag coefficient of a sphere
##      collapses when the boundary layer trips from laminar to turbulent, and a
##      football does that inside the speed band a striker actually uses. Below
##      CRISIS_LOW the ball drags like a beach ball, above CRISIS_HIGH it slips
##      through the air. Spin re energises the boundary layer and pushes the
##      crisis up the speed axis, which is exactly why a knuckleball (no spin,
##      high speed) flies flat and fast while a heavily curled ball arrives late.
##   3. Magnus lift from the spin, whose coefficient depends on the spin
##      parameter S = r * omega / v and saturates near S = 0.3, where the real
##      wind tunnel measurements flatten out.
##
## Reference points this model reproduces, measured over the 11 m from the
## penalty spot to the goal line:
##
##   - 30 m/s, no spin (knuckler): about 11 percent of the speed lost, 0.39 s of
##     flight. That is the real world figure for a turbulent Cd of 0.20 and it is
##     what the contract constants dictate.
##   - 30 m/s with 9 rev/s of spin: about 24 percent lost, 0.42 s of flight. The
##     spin holds the boundary layer on the laminar side of the crisis and the
##     induced drag of the lift adds on top.
##   - 25 m/s with 8 to 10 rev/s of sidespin: 0.4 to 0.7 m of lateral deviation.
##   - Backspin measurably flattens the drop, topspin measurably steepens it.
##
## Sign convention, binding: `spin` is an angular velocity vector in rad/s under
## the right hand rule, and the Magnus acceleration is along `spin x velocity`
## (the raw cross product, no sign flip). A ball leaving towards -Z with
## spin = (0, +w, 0) therefore bends towards -X, the classic right footer's curl.
##
## Everything is integrated with RK4. At 30 m/s a semi implicit Euler step at
## 120 Hz drifts several centimetres over a penalty, which is the difference
## between a post and a goal.

# --- Contract constants -----------------------------------------------------

const GRAVITY      := 9.81
const AIR_DENSITY  := 1.225
const BALL_MASS    := 0.430
const BALL_RADIUS  := 0.11
const BALL_AREA    := 0.0380         # PI * r * r
const SPIN_DECAY   := 0.045          # fraction of spin lost per second

## Drag crisis: a football's drag coefficient collapses as the boundary layer
## goes turbulent. Below CRISIS_LOW it is laminar, above CRISIS_HIGH turbulent.
const CD_LAMINAR   := 0.47
const CD_TURBULENT := 0.20
const CRISIS_LOW   := 9.0            # m/s
const CRISIS_HIGH  := 19.0           # m/s

## Fastest spin the model stays sane for, rad/s.
const MAX_SPIN     := 220.0

# --- Private tunables -------------------------------------------------------

const _EPSILON := 1.0e-9
## Below this air relative speed the aerodynamic frame is meaningless.
const _MIN_AERO_SPEED := 0.02

## Dynamic pressure divided by mass, Cd excluded: 0.5 * rho * A / m.
## Multiplying by Cd * v * v gives an acceleration in m/s2 directly. Applied
## exactly once, in acceleration(); never scale it again downstream.
const _PRESSURE_OVER_MASS := 0.5 * AIR_DENSITY * BALL_AREA / BALL_MASS

## How far up the speed axis a full MAX_SPIN rotation drags the crisis. The
## square root inside the shift means a modest game spin (8 to 10 rev/s) already
## buys most of the effect, while the last decade of spin adds little.
const _CRISIS_SPIN_SHIFT := 3.0
## Induced drag: producing lift costs drag, linearly in the spin parameter.
const _CD_SPIN_GAIN := 0.20
## Saturating lift law, Cl = _CL_MAX * tanh(S / _CL_KNEE).
const _CL_MAX := 0.25
const _CL_KNEE := 0.30
## Spin parameter beyond which nothing new happens.
const _SPIN_PARAM_MAX := 1.20

## Longest slice of time a single RK4 evaluation is trusted with. The game steps
## at 120 Hz, so a normal call is one step and costs nothing extra; a coarse
## call from a preview or a test is split rather than allowed to wobble.
const _MAX_SUBSTEP := 1.0 / 60.0
const _MAX_SUBSTEPS := 64

## Fixed probe step of cross_plane and of the aim solver. Fixed, so two calls
## with the same arguments return bit identical results.
const _CROSS_STEP := 1.0 / 240.0
## Hard ceiling on any simulated flight, seconds.
const _MAX_FLIGHT_TIME := 20.0
## Bisection refinements once the crossing step is bracketed.
const _CROSS_REFINES := 16

## Longest sampled preview, guards against a silly `steps` argument.
const _MAX_SAMPLES := 4096

# Aim solver.
const _AIM_MAX_ITER := 12
## Stop as soon as the trial flight lands this close to the target, metres.
const _AIM_TOLERANCE := 0.005
## Still returned as a solution: 5 cm is well inside the ball radius.
const _AIM_ACCEPT := 0.05
## The target must be this far in front of the launch point, in z.
const _AIM_MIN_DEPTH := 0.25
const _AIM_MIN_SPEED := 0.5
## The launch direction always keeps at least this much of -Z, otherwise a
## runaway correction aims at the sky and the flight never reaches the plane.
const _AIM_MIN_FORWARD := 0.08
const _AIM_MAX_TIME := 6.0
## Bounds on the virtual aim point, so a diverging correction cannot run away.
const _AIM_MAX_OFFSET := 60.0

## Sphere of uniform density: the tangential impulse that just kills the contact
## slip is 2/7 of the momentum of that slip. See bounce().
const _SLIP_IMPULSE_FACTOR := 2.0 / 7.0
## Converts a tangential impulse into a spin change: R / I with I = 0.4 m R2.
const _SPIN_FROM_IMPULSE := 2.5 / (BALL_MASS * BALL_RADIUS)


# --- Coefficients -----------------------------------------------------------


## Drag coefficient at this speed. Spin re energises the boundary layer and
## pushes the crisis back up, so a heavily spun ball keeps a higher Cd: that is
## exactly why a knuckleball (no spin, high speed) flies flat and a curled ball
## slows down.
static func drag_coefficient(speed: float, spin_rate: float) -> float:
	var v := _finite_float(speed)
	if v < 0.0:
		v = -v
	var omega := clampf(absf(_finite_float(spin_rate)), 0.0, MAX_SPIN)

	# The crisis window slides up the speed axis with spin. sqrt() so that a
	# realistic strike spin already sits well up the curve.
	var shift := 1.0 + _CRISIS_SPIN_SHIFT * sqrt(omega / MAX_SPIN)
	var low := CRISIS_LOW * shift
	var high := CRISIS_HIGH * shift

	# smoothstep is C1 at both ends, so the coefficient is continuous and has no
	# kink where the crisis starts or finishes. Monotonically decreasing in v.
	var cd := lerpf(CD_LAMINAR, CD_TURBULENT, smoothstep(low, high, v))

	# Induced drag: the same circulation that lifts the ball also drags it.
	return cd + _CD_SPIN_GAIN * _spin_parameter(v, omega)


## Lift coefficient from the spin parameter S = r * omega / v. Saturates around
## S = 0.3, which is where real measurements flatten out.
static func lift_coefficient(speed: float, spin_rate: float) -> float:
	var v := absf(_finite_float(speed))
	if v < _MIN_AERO_SPEED:
		return 0.0
	var omega := clampf(absf(_finite_float(spin_rate)), 0.0, MAX_SPIN)
	return _CL_MAX * tanh(_spin_parameter(v, omega) / _CL_KNEE)


## Total acceleration in m/s2: gravity plus drag plus Magnus, relative to the
## air, so `wind` shifts the whole aerodynamic frame.
static func acceleration(velocity: Vector3, spin: Vector3, wind: Vector3) -> Vector3:
	var acc := Vector3(0.0, -GRAVITY, 0.0)

	var air := _sanitize(velocity) - _sanitize(wind)
	var speed := air.length()
	if speed < _MIN_AERO_SPEED:
		# No air flow, no aerodynamic frame: only gravity is defined.
		return acc

	var omega := _clamp_spin(spin)
	# Dynamic pressure over mass, without any coefficient. Used once per term.
	var q := _PRESSURE_OVER_MASS * speed * speed

	acc -= (air / speed) * (q * drag_coefficient(speed, omega.length()))

	# Magnus. The direction is the raw cross product: spin (0, +w, 0) on a ball
	# heading towards -Z gives (-w * v, 0, 0), i.e. a curl towards -X, which is
	# the convention the whole game is written against.
	var swirl := omega.cross(air)
	var swirl_len := swirl.length()
	if swirl_len > _EPSILON:
		# |spin x air| / |air| is the part of the spin perpendicular to the
		# flow, and only that part lifts.
		var perpendicular_rate := swirl_len / speed
		acc += (swirl / swirl_len) * (q * lift_coefficient(speed, perpendicular_rate))

	return acc


# --- Integration ------------------------------------------------------------


## One RK4 step. Returns [Vector3 position, Vector3 velocity], in that order.
## RK4 and not Euler: at 30 m/s a semi implicit Euler step drifts several
## centimetres over a penalty, which is the difference between a post and a goal.
##
## A delta longer than _MAX_SUBSTEP is split internally. A null or negative
## delta is a no operation, never a NaN.
static func integrate(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, delta: float) -> Array:
	var p := _sanitize(position)
	var v := _sanitize(velocity)
	var dt := _finite_float(delta)
	if dt <= 0.0:
		return [p, v]

	var w := _clamp_spin(spin)
	var air := _sanitize(wind)

	var count := 1
	if dt > _MAX_SUBSTEP:
		count = mini(int(ceil(dt / _MAX_SUBSTEP)), _MAX_SUBSTEPS)
	var h := dt / float(count)

	for _i in count:
		var k1v := acceleration(v, w, air)
		var v2 := v + k1v * (h * 0.5)
		var k2v := acceleration(v2, w, air)
		var v3 := v + k2v * (h * 0.5)
		var k3v := acceleration(v3, w, air)
		var v4 := v + k3v * h
		var k4v := acceleration(v4, w, air)

		# The position derivative is the velocity at each stage, which is why
		# the middle stages carry their own half stepped velocity.
		p += (v + (v2 + v3) * 2.0 + v4) * (h / 6.0)
		v += (k1v + (k2v + k3v) * 2.0 + k4v) * (h / 6.0)

	return [_sanitize(p), _sanitize(v)]


## Spin bleeds off through skin friction.
static func decay_spin(spin: Vector3, delta: float) -> Vector3:
	var w := _clamp_spin(spin)
	var dt := _finite_float(delta)
	if dt <= 0.0:
		return w
	# Exponential, not linear: a fixed fraction per second is a rate, and a
	# linear law would send a long flight's spin negative.
	return w * exp(-SPIN_DECAY * dt)


## Samples a whole flight, ignoring every collision. Used by the HUD preview and
## by the keeper's mental model, never by the real ball.
##
## The first entry is the launch position itself, so a preview drawn as a
## polyline starts at the ball.
static func sample_flight(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, delta: float, steps: int) -> PackedVector3Array:
	var out := PackedVector3Array()
	var p := _sanitize(position)
	out.append(p)

	var count := clampi(steps, 0, _MAX_SAMPLES)
	var dt := _finite_float(delta)
	if count <= 0 or dt <= 0.0:
		return out

	var v := _sanitize(velocity)
	var w := _clamp_spin(spin)
	var air := _sanitize(wind)

	for _i in count:
		var next := integrate(p, v, w, air, dt)
		p = next[0]
		v = next[1]
		w = decay_spin(w, dt)
		out.append(p)

	return out


## Where and when the flight crosses the plane z = plane_z travelling towards -Z.
## Returns {"crossed": bool, "time": float, "point": Vector3, "velocity": Vector3}
##
## Uses the same fixed probe step and the same spin decay as sample_flight, so
## the two always agree, then brackets the crossing step and bisects it.
static func cross_plane(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, plane_z: float, max_time: float) -> Dictionary:
	var p := _sanitize(position)
	var v := _sanitize(velocity)
	var result := {"crossed": false, "time": 0.0, "point": p, "velocity": v}

	var target_z := _finite_float(plane_z)
	if p.z <= target_z:
		# Already on the far side: this flight never crosses towards -Z.
		return result

	var limit := clampf(_finite_float(max_time), 0.0, _MAX_FLIGHT_TIME)
	if limit <= 0.0:
		return result

	var w := _clamp_spin(spin)
	var air := _sanitize(wind)
	var elapsed := 0.0

	while elapsed < limit:
		var step: float = minf(_CROSS_STEP, limit - elapsed)
		if step <= _EPSILON:
			break
		var next := integrate(p, v, w, air, step)
		var np: Vector3 = next[0]

		if np.z <= target_z and np.z < p.z:
			var lo := 0.0
			var hi := step
			for _i in _CROSS_REFINES:
				var mid := (lo + hi) * 0.5
				var probe := integrate(p, v, w, air, mid)
				var probe_p: Vector3 = probe[0]
				if probe_p.z <= target_z:
					hi = mid
				else:
					lo = mid
			var hit := integrate(p, v, w, air, hi)
			result["crossed"] = true
			result["time"] = elapsed + hi
			result["point"] = hit[0]
			result["velocity"] = hit[1]
			return result

		p = np
		v = next[1]
		w = decay_spin(w, step)
		elapsed += step

	return result


# --- Aiming -----------------------------------------------------------------


## Solves for the launch velocity of magnitude `speed` that carries the ball from
## `from` to `target`, spin and drag included. Shooting method: it fires, sees
## where it lands on the target's plane, corrects the aim, and repeats. Returns
## ZERO when no solution exists (target out of range for that speed).
##
## The unknown is a virtual aim point on the target's plane. Because the map
## from that point to the landing point is the identity plus a slowly varying
## drop, feeding the miss straight back into the aim point converges in three or
## four iterations for anything a striker would attempt. A correction that stops
## improving is halved, and a run that never gets inside _AIM_ACCEPT is reported
## honestly as ZERO rather than as a wild guess.
static func aim_velocity(from: Vector3, target: Vector3, spin: Vector3, wind: Vector3, speed: float) -> Vector3:
	var origin := _sanitize(from)
	var goal := _sanitize(target)
	var launch_speed := _finite_float(speed)
	if launch_speed < _AIM_MIN_SPEED:
		return Vector3.ZERO
	# The whole solver measures the miss on the plane z = target.z, crossed
	# towards -Z. A target level with or behind the launch point has no such
	# crossing, so there is nothing to solve.
	if origin.z - goal.z < _AIM_MIN_DEPTH:
		return Vector3.ZERO

	var w := _clamp_spin(spin)
	var air := _sanitize(wind)
	var plane_z := goal.z

	var aim := goal
	var best_dir := Vector3.ZERO
	var best_miss := INF
	var previous_miss := INF
	var scale := 1.0

	for _i in _AIM_MAX_ITER:
		var dir := _launch_direction(origin, aim)
		if dir == Vector3.ZERO:
			break

		var flight := cross_plane(origin, dir * launch_speed, w, air, plane_z, _AIM_MAX_TIME)
		if not flight["crossed"]:
			# Too steep or too slow to reach the plane at all: pull the virtual
			# aim point back towards the straight line and try again.
			aim = aim.lerp(goal, 0.5)
			scale *= 0.5
			continue

		var point: Vector3 = flight["point"]
		var miss := goal - point
		var distance := miss.length()
		if distance < best_miss:
			best_miss = distance
			best_dir = dir
		if distance <= _AIM_TOLERANCE:
			break

		# A correction that made things worse means the local slope is not the
		# identity any more (very lofted shots): damp instead of oscillating.
		if distance > previous_miss:
			scale *= 0.5
		previous_miss = distance

		aim += miss * scale
		aim.x = clampf(aim.x, goal.x - _AIM_MAX_OFFSET, goal.x + _AIM_MAX_OFFSET)
		aim.y = clampf(aim.y, goal.y - _AIM_MAX_OFFSET, goal.y + _AIM_MAX_OFFSET)
		aim.z = plane_z

	if best_miss <= _AIM_ACCEPT and best_dir != Vector3.ZERO:
		return best_dir * launch_speed
	return Vector3.ZERO


# --- Contact ----------------------------------------------------------------


## Reflects a velocity off a surface, losing energy and converting part of the
## tangential slip into spin. Returns [Vector3 velocity, Vector3 spin].
## `restitution` 0.75 for the frame, 0.45 for turf, 0.12 for the net.
##
## The tangential half is what makes the game readable: the contact point of a
## sphere moves at v_t - R * (omega x n), and the friction impulse fights that
## slip whichever way it points. A ball arriving flat with no spin leaves the
## post spinning; a ball arriving with heavy sidespin leaves the post on a new
## line even though it came in square. Both fall out of the same expression.
static func bounce(velocity: Vector3, spin: Vector3, normal: Vector3, restitution: float, friction: float) -> Array:
	var v := _sanitize(velocity)
	var w := _clamp_spin(spin)
	var n := _sanitize(normal)
	if n.length_squared() < _EPSILON:
		return [v, w]
	n = n.normalized()

	var approach := v.dot(n)
	if approach >= 0.0:
		# Already separating: no impulse to apply, and inventing one here would
		# let a grazing contact pump energy into the ball.
		return [v, w]

	var e := clampf(_finite_float(restitution), 0.0, 1.0)
	var mu := clampf(_finite_float(friction), 0.0, 4.0)

	var v_normal := n * approach
	var v_tangent := v - v_normal

	# Velocity of the material point in contact with the surface.
	var slip := v_tangent - w.cross(n) * BALL_RADIUS

	# Normal impulse magnitude, then the tangential impulse that would exactly
	# kill the slip, capped by Coulomb friction.
	var normal_impulse := BALL_MASS * (1.0 + e) * absf(approach)
	var tangent_impulse := slip * (-_SLIP_IMPULSE_FACTOR * BALL_MASS)
	var cap := mu * normal_impulse
	if tangent_impulse.length() > cap:
		tangent_impulse = tangent_impulse.normalized() * cap

	var out_velocity := v_tangent + tangent_impulse / BALL_MASS - n * (e * approach)
	var out_spin := w - n.cross(tangent_impulse) * _SPIN_FROM_IMPULSE

	return [_sanitize(out_velocity), _clamp_spin(out_spin)]


# --- Private helpers --------------------------------------------------------


## Spin parameter S = r * omega / v, bounded. Zero when there is no flow.
static func _spin_parameter(speed: float, spin_rate: float) -> float:
	if speed < _MIN_AERO_SPEED:
		return 0.0
	return clampf(BALL_RADIUS * spin_rate / speed, 0.0, _SPIN_PARAM_MAX)


## A non finite scalar anywhere in the pipeline poisons every later frame, so it
## is caught at the door rather than debugged in the trajectory.
static func _finite_float(value: float) -> float:
	if is_finite(value):
		return value
	return 0.0


static func _sanitize(v: Vector3) -> Vector3:
	if is_finite(v.x) and is_finite(v.y) and is_finite(v.z):
		return v
	return Vector3(_finite_float(v.x), _finite_float(v.y), _finite_float(v.z))


## Sanitised and bounded to MAX_SPIN, direction preserved.
static func _clamp_spin(spin: Vector3) -> Vector3:
	var w := _sanitize(spin)
	var rate := w.length()
	if rate > MAX_SPIN:
		return w * (MAX_SPIN / rate)
	return w


## Unit launch direction towards a virtual aim point, kept far enough from the
## goal plane's own plane that the flight is guaranteed to reach it.
static func _launch_direction(origin: Vector3, aim: Vector3) -> Vector3:
	var dir := aim - origin
	if dir.length_squared() < _EPSILON:
		return Vector3.ZERO
	dir = dir.normalized()
	if dir.z > -_AIM_MIN_FORWARD:
		dir.z = -_AIM_MIN_FORWARD
		if dir.length_squared() < _EPSILON:
			return Vector3(0.0, 0.0, -1.0)
		dir = dir.normalized()
	return dir
