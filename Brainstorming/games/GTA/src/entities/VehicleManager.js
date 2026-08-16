/**
 * Owns every vehicle in the world: parked cars, AI traffic, and whichever one the player
 * is driving.
 *
 * Traffic AI is a pure-pursuit controller over the road graph. Each car tracks its
 * position by projecting onto its current edge (rather than integrating a parameter, which
 * drifts after any collision), aims at a lookahead point in its lane, and brakes for
 * whatever a forward raycast finds. It is deliberately simple: on a grid it produces
 * convincing lane-keeping, queueing and turning without a full traffic simulation.
 */

import { Vector3, MathUtils } from 'three/webgpu';
import { Vehicle } from './Vehicle.js';
import { VEHICLE_CLASSES, TRAFFIC_COLOURS } from './VehicleMesh.js';
import { GROUP, groups } from '../physics/Physics.js';
import { PAVEMENT_WIDTH } from '../world/RoadNetwork.js';
import { makeRng } from '../core/Noise.js';
import { approachAngle } from './Player.js';
import { SkidMarks, SmokePool } from '../render/VehicleFX.js';

const DRIVABLE_CLASSES = ['sedan', 'coupe', 'suv', 'van', 'pickup', 'sports'];
const TRAFFIC_WEIGHTS = { sedan: 34, suv: 22, van: 12, pickup: 12, coupe: 12, sports: 8 };

const ENTER_DISTANCE = 3.4;

/**
 * How far back down an approach a signal is looked up at all. Purely an early-out: the
 * curve below only drops beneath a car's own target speed within v^2/(2*SIGNAL_DECEL) of
 * the stop line, which for the fastest car the city spawns (an avenue limit of 22 m/s, up
 * to 1.12x from the per-car spread) is 95 m. Anything shorter than that would present the
 * ceiling to a fast car as a step rather than a curve, which is a brake application out of
 * nowhere in the middle of a block.
 */
const SIGNAL_SIGHT = 100;
/** Deceleration the approach curve is built on, m/s^2 - a comfortable stop, not a panic. */
const SIGNAL_DECEL = 3.2;
/**
 * How far short of the stop line the braking curve aims, metres.
 *
 * A curve alone never actually stops a car: sqrt(2*a*d) only reaches zero at d = 0, and
 * this controller feeds throttle for as long as the ceiling is above the current speed, so
 * cars roll over the line at a crawl instead of waiting. Measured with the margin at zero:
 * 116 of 263 line crossings happened on a red, and only 3 of 156 approaches that met a red
 * ever came to a stop. Aiming 2.5 m short - about where the nose of a stopped car sits -
 * gives the controller somewhere to converge that is not the line itself.
 */
const SIGNAL_STOP_MARGIN = 2.5;
/**
 * Target speed commanded inside that margin. Negative, which is how this controller spells
 * "hold the brake": the target is only ever read as `target - speed`, so -3.2 asks for full
 * brake at a standstill and no throttle at all. A target of zero asks for 0.16 of brake
 * against a 0.5 m/s creep, which is not enough to hold a car on the line for ten seconds.
 */
const SIGNAL_HOLD = -3.2;
/**
 * Cap on the dead-queue exemption below.
 *
 * One red lasts at most ten seconds (the cross axis's green, amber and all-red), but the
 * exemption is not per red: a car can clear one junction and immediately meet another, and
 * with signals on every corner that chains - measured peak hold was 18 s in that build,
 * against 10 s once signals were restricted to the arterial crossings. The cap is what
 * stops the chain, or a stopped phase clock, from telling a car forever that it is waiting.
 */
const SIGNAL_HOLD_MAX = 30;

export class VehicleManager {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('../world/City.js').City} city
   * @param {import('three/webgpu').Scene} scene
   */
  constructor(physics, city, scene, { seed = 99 } = {}) {
    this.physics = physics;
    this.city = city;
    this.scene = scene;
    this.rng = makeRng(seed);

    /** @type {Vehicle[]} */
    this.vehicles = [];
    /** @type {Map<Vehicle, object>} AI state keyed by vehicle */
    this.ai = new Map();
    /** @type {Vehicle|null} */
    this.playerVehicle = null;

    this.skids = new SkidMarks(scene);
    this.smoke = new SmokePool(scene);
    /**
     * The city's signal heads, wired in by `main`. Anything answering `isSignalled(nodeId)`
     * and `signalPhase(axis)` will do, and a null leaves the autopilot exactly as it was
     * before lights existed - which is also what the elevated ring gets, since it has no
     * junctions to signal.
     * @type {{isSignalled:(n:number)=>boolean, signalPhase:(a:number)=>number}|null}
     */
    this.trafficLights = null;
    /** Collision damage events since the last frame, for audio and camera shake. */
    this.lastImpact = 0;
    /*
     * Cross-track steering gain. DEFAULT 0 - i.e. off.
     *
     * Adding an explicit Stanley-style correction on top of pure pursuit measured worse,
     * not better: gain 1.6 gave 14 of 28 cars flowing with average lane error climbing
     * past 2.5 m, where gain 0 gives 21.5 flowing and holds 1.5 m. Aiming at a point *on
     * the lane line* already pulls a drifting car back, so the extra term double-counts
     * and oscillates - badly at low speed, where the atan2 saturates. Kept tunable
     * because it is exactly the kind of change that looks right on paper and has to be
     * settled by measurement.
     */
    this.crossTrackGain = 0;

    this._v = new Vector3();
    this._target = new Vector3();
    this._fx = new Vector3();
    this._rayDir = new Vector3();
    this._rayOrigin = new Vector3();
    /*
     * The traffic obstacle scan looks for things that move: other cars, the player,
     * pedestrians. It deliberately ignores buildings, barriers and street furniture.
     *
     * Including static geometry causes a deadlock. A car sitting even slightly off its
     * lane heading points its scan ray at a wall, brakes, loses the speed it needs for
     * the steering to correct, and then brakes forever. It showed up first on the highway,
     * where crash barriers line both sides two metres from the outer lane, but the same
     * trap exists on any street with a building on the corner. Lane geometry is what keeps
     * traffic off walls; the scan is only for avoiding each other.
     */
    this._rayFilter = groups(
      GROUP.VEHICLE, GROUP.VEHICLE | GROUP.PLAYER | GROUP.PED,
    );
  }

  _pickClass() {
    let total = 0;
    for (const w of Object.values(TRAFFIC_WEIGHTS)) total += w;
    let r = this.rng() * total;
    for (const [k, w] of Object.entries(TRAFFIC_WEIGHTS)) {
      r -= w;
      if (r <= 0) return k;
    }
    return 'sedan';
  }

  _spawn(className, position, heading, opts = {}) {
    const v = new Vehicle(this.physics, {
      className,
      position,
      heading,
      colour: opts.colour ?? TRAFFIC_COLOURS[Math.floor(this.rng() * TRAFFIC_COLOURS.length)],
      livery: opts.livery ?? null,
    });
    this.vehicles.push(v);
    this.scene.add(v.group);
    return v;
  }

  /**
   * Kerbside parked cars. Placed in the outermost lane facing along the road, skipping
   * anything too close to a junction so they do not block turns.
   */
  spawnParked(count = 90) {
    const net = this.city.network;
    let placed = 0, attempts = 0;
    while (placed < count && attempts < count * 12) {
      attempts++;
      const edge = net.edges[Math.floor(this.rng() * net.edges.length)];
      if (edge.length < 34) continue;
      const forward = this.rng() < 0.5;
      // Keep clear of the junction mouths at either end.
      const margin = 14 / edge.length;
      const t = margin + this.rng() * (1 - margin * 2);
      const p = net.lanePointOnEdge(edge, t, forward, 0);
      /*
       * Nudge outward from the driving lane to the kerb. Derived from the drivable width
       * so parked cars sit against the kerb rather than up on the pavement - the previous
       * version worked off the full road width and put them among the lamp posts.
       */
      const drivable = edge.type.width / 2 - PAVEMENT_WIDTH;
      const outward = Math.max(0, drivable - 1.15 - net.laneOffset(edge.type, 0));
      const rx = -edge.dirZ * (forward ? 1 : -1), rz = edge.dirX * (forward ? 1 : -1);
      const x = p.x + rx * outward, z = p.z + rz * outward;
      if (!this.city.isFootprintClear(x, z, 2.6)) continue;
      if (this._occupied(x, z, 6.5)) continue;

      const className = this._pickClass();
      const spec = VEHICLE_CLASSES[className];
      this._spawn(className, new Vector3(x, spec.wheelRadius + 0.45, z), p.heading);
      placed++;
    }
    return placed;
  }

  /** Moving AI traffic. */
  spawnTraffic(count = 26) {
    const net = this.city.network;
    let placed = 0, attempts = 0;
    while (placed < count && attempts < count * 15) {
      attempts++;
      const edge = net.edges[Math.floor(this.rng() * net.edges.length)];
      if (edge.length < 40) continue;
      const forward = this.rng() < 0.5;
      const t = 0.15 + this.rng() * 0.7;
      const p = net.lanePointOnEdge(edge, t, forward, 0);
      if (this._occupied(p.x, p.z, 11)) continue;

      const className = this._pickClass();
      const spec = VEHICLE_CLASSES[className];
      const v = this._spawn(className, new Vector3(p.x, spec.wheelRadius + 0.45, p.z), p.heading);
      this.ai.set(v, {
        edge, forward, lane: 0,
        targetSpeed: edge.type.speed * (0.82 + this.rng() * 0.3),
        patience: 0,
        stuckTimer: 0,
      });
      placed++;
    }
    return placed;
  }

  /**
   * Traffic for an elevated road. Takes any graph exposing the RoadNetwork surface, so
   * the highway's own ring drives itself with no changes to the autopilot.
   *
   * @param {object} network graph to drive
   * @param {number} count how many cars
   */
  spawnOnNetwork(network, count = 10) {
    let placed = 0, attempts = 0;
    while (placed < count && attempts < count * 20) {
      attempts++;
      const edge = network.edges[Math.floor(this.rng() * network.edges.length)];
      const forward = true;   // a ring flows one way; head-on traffic would just deadlock
      const p = network.lanePointOnEdge(edge, this.rng(), forward, this.rng() < 0.5 ? 0 : 1);
      if (this._occupied(p.x, p.z, 13)) continue;

      const className = this._pickClass();
      const spec = VEHICLE_CLASSES[className];
      const y = (p.y ?? 0) + spec.wheelRadius + 0.6;
      const v = this._spawn(className, new Vector3(p.x, y, p.z), p.heading);
      this.ai.set(v, {
        edge, forward, lane: p.lane, network,
        targetSpeed: edge.type.speed * (0.85 + this.rng() * 0.25),
        patience: 0, stuckTimer: 0,
      });
      placed++;
    }
    return placed;
  }

  /** Police cruiser, used by the wanted system and by missions. */
  spawnPolice(position, heading) {
    return this._spawn('sedan', position, heading, { colour: 0x1b1f28, livery: 'police' });
  }

  _occupied(x, z, radius) {
    for (const v of this.vehicles) {
      const t = v.body.translation();
      if ((t.x - x) ** 2 + (t.z - z) ** 2 < radius * radius) return true;
    }
    return false;
  }

  /* ------------------------------------------------------------------ enter/exit */

  /** Nearest vehicle or boat the player could get into, or null. */
  nearestEnterable(position, maxDistance = ENTER_DISTANCE) {
    let best = null, bestScore = Infinity;
    for (const v of this.vehicles) {
      if (v === this.playerVehicle) continue;
      const t = v.body.translation();
      const d = Math.hypot(t.x - position.x, t.z - position.z);
      // Measure to the hull, not the centre, so long vehicles are reachable end-on.
      const surfaceDistance = d - v.enterRadius;
      if (surfaceDistance > maxDistance) continue;
      // Vertical check stops a rooftop car being "reachable" from the street below.
      if (Math.abs(t.y - position.y) > 4) continue;
      if (surfaceDistance < bestScore) { bestScore = surfaceDistance; best = v; }
    }
    return best;
  }

  enter(player, vehicle) {
    this.playerVehicle = vehicle;
    vehicle.occupied = true;
    vehicle.wake();
    // A parked AI car becomes the player's; drop its autopilot.
    this.ai.delete(vehicle);
    player.enterVehicle(vehicle);
  }

  exit(player) {
    const v = this.playerVehicle;
    if (!v) return;
    v.occupied = false;
    v.setInput({ throttle: 0, brake: v.isBoat ? 0 : 1, steer: 0 });
    const spot = v.exitPoint();
    // Do not drop the player inside a wall. Boats are over water, where the city's
    // building footprints are meaningless, so only cars get this check.
    if (!v.isBoat && !this.city.isFootprintClear(spot.x, spot.z, 0.5)) {
      spot.copy(v.position).add(new Vector3(0, 0.4, 0));
    }
    player.exitVehicle(spot);
    this.playerVehicle = null;
  }

  /** Register an externally-created craft (boats are built by the world, not here). */
  addVehicle(v) {
    this.vehicles.push(v);
    this.scene.add(v.group);
    return v;
  }

  /* -------------------------------------------------------------------- simulate */

  /**
   * @param {number} dt fixed step
   * @param {object|null} playerInput `{ throttle, brake, steer, handbrake }`
   */
  fixedUpdate(dt, playerInput) {
    if (this.playerVehicle && playerInput) {
      this.playerVehicle.setInput(playerInput);
      this.playerVehicle.wake();
    }
    for (const v of this.vehicles) {
      const state = this.ai.get(v);
      if (state) this._driveAI(v, state, dt);
      // Parked cars still need a physics update so they settle on their suspension.
      v.fixedUpdate(dt);
    }
  }

  /**
   * Pure-pursuit autopilot for one traffic car.
   *
   * The road graph comes from the car's own AI state, not from the city, so the same
   * controller drives the street grid and the elevated ring highway without knowing which
   * is which. Reading `this.city.network` here instead looks up highway edge indices in
   * the ground node array and steers cars at unrelated junctions a kilometre away.
   */
  /**
   * First point further along the lane with room for a car, walking onto later edges as
   * needed. Returns null if nothing within reach is clear.
   *
   * The old recovery teleported the car to `along + 0.05` on its current edge - about two
   * metres. A car is longer than that, so a vehicle wedged nose-to-tail in a pile-up was
   * being rematerialised *inside* the car it was stuck against, which is what kept the
   * pile-up alive and growing instead of clearing it. Recovery has to land somewhere
   * genuinely empty or it is just churn.
   *
   * @returns {object|null} a lane point, extended with the edge it belongs to
   */
  _clearSpotAhead(net, state, along, vehicle, reach = 140, minGap = 7) {
    let edge = state.edge;
    let forward = state.forward;
    let t = along;
    let travelled = 0;
    let guard = 0;

    while (travelled < reach && guard++ < 24) {
      t += 9 / Math.max(1, edge.length);
      if (t >= 1) {
        // Roll onto a continuation, the same way the driving code hands over.
        const nodeId = forward ? edge.b : edge.a;
        const exits = net.exitsFrom(nodeId, edge.id);
        if (!exits.length) return null;
        const next = net.edges[exits[Math.floor(this.rng() * exits.length)]];
        forward = next.a === nodeId;
        edge = next;
        t = 0;
      }
      travelled += 9;

      const p = net.lanePointOnEdge(edge, t, forward, state.lane);
      let blocked = false;
      for (const other of this.vehicles) {
        if (other === vehicle) continue;
        const q = other.position;
        // Compare in 3D: the ring passes directly over streets, and a car on the deck is
        // not blocked by one sitting on the road nine metres below it.
        if (Math.abs(q.y - (p.y ?? 0)) > 4) continue;
        if (Math.hypot(q.x - p.x, q.z - p.z) < minGap) { blocked = true; break; }
      }
      if (!blocked) return { ...p, edge, forward };
    }

    /*
     * Nothing clear within reach. Nudge forward on the current lane anyway rather than
     * returning null: on a dense city grid every candidate can be occupied, and a car
     * that is never moved is welded in place forever. Measured over 130 s, refusing to
     * teleport bled city traffic from 27 of 28 flowing down to 12. Churning is worse than
     * clearing but far better than a permanent obstacle.
     */
    const p = net.lanePointOnEdge(
      state.edge, MathUtils.clamp(along + 0.05, 0, 1), state.forward, state.lane,
    );
    return { ...p, edge: state.edge, forward: state.forward };
  }

  _driveAI(vehicle, state, dt) {
    const net = state.network ?? this.city.network;
    const pos = vehicle.position;
    const edge = state.edge;
    const a = net.nodes[edge.a], b = net.nodes[edge.b];

    // Project onto the current edge to recover progress robustly after any nudge.
    const vx = b.x - a.x, vz = b.z - a.z;
    const len2 = vx * vx + vz * vz;
    let t = ((pos.x - a.x) * vx + (pos.z - a.z) * vz) / len2;
    t = MathUtils.clamp(t, 0, 1);
    const along = state.forward ? t : 1 - t;

    // Hand over to the next edge shortly before the junction.
    if (along > 0.94) {
      const nodeId = state.forward ? edge.b : edge.a;
      const exits = net.exitsFrom(nodeId, edge.id);
      const nextId = exits[Math.floor(this.rng() * exits.length)];
      const next = net.edges[nextId];
      state.edge = next;
      state.forward = next.a === nodeId;
      /*
       * Ambient traffic re-rolls a speed for the road type it just turned onto. A scripted
       * actor keeps the speed its mission asked for: a runner told to do 26 m/s that drops
       * back to a street's 14 the moment it takes its first corner is not fleeing, it is
       * commuting, and it can never clear the escape ring its mission is judged on.
       */
      if (!state.scripted) state.targetSpeed = next.type.speed * (0.82 + this.rng() * 0.3);
      return;
    }

    // Aim at a point further along the lane; longer lookahead at speed.
    const speed = Math.abs(vehicle.speed);
    const lookahead = MathUtils.clamp(5 + speed * 0.55, 5, 15);
    const p = this._lookaheadPoint(net, state, along, lookahead);
    this._target.set(p.x, pos.y, p.z);

    const toTarget = Math.atan2(this._target.x - pos.x, this._target.z - pos.z);
    const heading = vehicle.heading;
    let error = toTarget - heading;
    while (error > Math.PI) error -= Math.PI * 2;
    while (error < -Math.PI) error += Math.PI * 2;

    /*
     * Cross-track correction (the Stanley term).
     *
     * Aiming at a lookahead point corrects *heading* but says nothing about how far the
     * car has drifted sideways out of its lane, so small errors accumulate and never
     * come back. On a street that just means sloppy lane discipline; on the elevated
     * highway, where the lane is eight metres from a drop, it means cars leaving the
     * viaduct. This measures the signed distance to the lane centreline and steers back
     * towards it, scaled down with speed so it does not oscillate at a crawl.
     */
    const here = net.lanePointOnEdge(edge, along, state.forward, state.lane);
    const offX = pos.x - here.x, offZ = pos.z - here.z;
    const lateral = offX * -here.dirZ + offZ * here.dirX;
    const crossTrack = Math.atan2(-lateral * this.crossTrackGain, Math.max(5, speed));

    const steer = MathUtils.clamp((error + crossTrack) * 1.9, -1, 1);
    state.lateral = lateral;

    // On a constrained road (the elevated deck), back the steering up with a lane-keeping
    // force so drift cannot accumulate into a barrier strike. Ground traffic does not get
    // it: wandering a metre on a street is harmless and the assist would look unnatural.
    if (state.network?.elevated && Math.abs(lateral) > 0.6) {
      const pull = MathUtils.clamp(-lateral * 0.9, -6, 6) * vehicle.spec.mass;
      vehicle.laneAssist = {
        x: -here.dirZ * pull,
        z: here.dirX * pull,
      };
    }

    /* ------------------------------------------------------- obstacle avoidance */
    /*
     * Obstacle scan, staggered across steps. One raycast per car per step is the single
     * most expensive thing the traffic AI does, and a car travelling at 30 m/s moves half
     * a metre between steps - re-scanning that often buys nothing. Staggering by vehicle
     * id also spreads the cost evenly instead of spiking on one frame.
     */
    const scanDistance = MathUtils.clamp(5 + speed * 1.5, 6, 30);
    state.scanCountdown = (state.scanCountdown ?? 0) - 1;
    if (state.scanCountdown <= 0) {
      state.scanCountdown = 3;
      vehicle.forward(this._rayDir);
      this._rayOrigin.copy(pos).addScaledVector(this._rayDir, vehicle.spec.chassis.hz + 0.3);
      this._rayOrigin.y = pos.y;
      state.lastHit = this.physics.raycast(
        this._rayOrigin, this._rayDir, scanDistance, this._rayFilter, vehicle.collider,
      );
    }
    const hit = state.lastHit;

    let targetSpeed = state.targetSpeed;
    // Slow for corners: a large heading error means a turn is coming up.
    // Corners need a real speed drop, not a nudge: a car entering a 90-degree turn at
    // 30 km/h cannot follow the lane whatever the steering says.
    targetSpeed *= MathUtils.clamp(1 - Math.abs(error) * 1.25, 0.18, 1);
    if (hit) {
      const gap = hit.distance;
      const stopGap = 4 + speed * 0.55;
      if (gap < stopGap) targetSpeed = Math.min(targetSpeed, (gap / stopGap) * speed * 0.6);
    }

    /* --------------------------------------------------------- traffic signals */
    /*
     * Stop for a red on this car's approach axis, feeding the same target-speed clamp the
     * obstacle scan uses. Two rules are what keep it from deadlocking the grid, and both
     * are the shape of failure earlier attempts at constraining this controller took:
     *
     * - the clamp only applies *before* the stop line. Past it the car is committed and
     *   drives through on whatever it has, so nothing ever parks in the middle of a
     *   junction and blocks the axis that just went green. Measured over 120 s: 5
     *   car-samples stalled past the line against 266 waiting behind it, so the queue
     *   forms where it should and the box stays clear.
     * - the ceiling is a braking curve, sqrt(2*a*d), not a switch. A switch makes the
     *   light a wall that cars arrive at flat out, brake into and end up straddling; the
     *   curve bleeds speed off over the last thirty metres the way a driver does.
     *
     * Amber is treated as red, which the curve makes reasonable rather than absurd: a car
     * a few metres out still has a ceiling of several m/s and rolls across, while one a
     * block back lifts off. Only green releases the clamp entirely.
     *
     * Highway cars are exempt by construction - `state.network` means the elevated ring,
     * which has no junctions and whose node ids are not the city's.
     *
     * Scripted actors are exempt by intent - `state.scripted` means a car a mission put on
     * the street, and the traffic obeys the lights while a runner does not. Without the
     * exemption a mission quarry queued at every red at about 14 km/h of net progress, so
     * the chase's own "the target got away" branch was unreachable code and its brief
     * ("stop him before he clears the district") described something that could not happen.
     */
    let heldAtSignal = false;
    const lights = this.trafficLights;
    if (lights && !state.network && !state.scripted) {
      const toNode = (1 - along) * edge.length;
      const nodeId = state.forward ? edge.b : edge.a;
      if (toNode < SIGNAL_SIGHT && lights.isSignalled(nodeId)
          && lights.signalPhase(edge.axis === 'x' ? 0 : 1) !== 2) {
        /*
         * The whole approach counts as held, not just the car on the line. The ones queued
         * behind it are stopped by the obstacle scan and have lifted off the throttle, so
         * without this they trip the dead-queue timer at twelve seconds and get teleported
         * forward - and `_clearSpotAhead` lands them at an arbitrary lane point, which can
         * be inside the junction box or across it.
         *
         * Narrowing this to a 45 m queue zone, and dropping the exemption for cars already
         * past the line, was tried and measured worse on every axis at once: teleports over
         * 120 s went 10 -> 21, car-samples stalled inside a junction box went 1 -> 7, and
         * city flow went 25.3 -> 23.7 of 28. Teleport churn *causes* box stalls here rather
         * than curing them, so the broad exemption stays.
         */
        heldAtSignal = true;
        const toLine = toNode - (edge.type.width / 2 + 3.5);
        if (toLine > 0) {
          const brakeTo = toLine - SIGNAL_STOP_MARGIN;
          targetSpeed = Math.min(
            targetSpeed, brakeTo > 0 ? Math.sqrt(2 * SIGNAL_DECEL * brakeTo) : SIGNAL_HOLD,
          );
        }
      }
    }

    const error2 = targetSpeed - speed;
    const throttle = MathUtils.clamp(error2 * 0.42, 0, 1);
    const brake = MathUtils.clamp(-error2 * 0.32, 0, 1);

    // Unstick cars that have been shoved into scenery.
    /*
     * A car is stuck when it is asking for throttle and going nowhere. Keying off
     * throttle rather than off target speed matters: a car queued legitimately behind
     * traffic has its target speed cut to zero by the obstacle scan and lifts off the
     * throttle, so it is correctly not treated as jammed and does not get teleported out
     * of the queue. Loosening this to "wants to move" cost a third of the city's traffic
     * flow when measured.
     */
    if (speed < 0.4 && throttle > 0.3) state.stuckTimer += dt;
    else state.stuckTimer = 0;

    /*
     * Second, slower timer for dead queues.
     *
     * The test above deliberately ignores a car that is queued behind traffic, because it
     * has lifted off the throttle and is waiting legitimately. But if the car at the head
     * of that queue is itself jammed against scenery, nobody behind it ever trips either
     * test and the whole line is parked permanently. Measured over 130 s, city traffic
     * bled from 25 of 28 flowing down to 15 exactly this way. Twelve seconds below
     * walking pace is not a queue, it is a dead one.
     */
    /*
     * A car stopped at a red is not a dead queue, so the timer freezes rather than
     * resetting - a car that was already half way to being recognised as jammed when the
     * light dropped picks up where it left off once it clears. The freeze is capped
     * (SIGNAL_HOLD_MAX) so a car genuinely wedged on a stop line still gets recovered.
     */
    state.signalHold = heldAtSignal ? (state.signalHold ?? 0) + dt : 0;
    const excused = heldAtSignal && state.signalHold < SIGNAL_HOLD_MAX;
    if (speed >= 0.6) state.deadTimer = 0;
    else if (!excused) state.deadTimer = (state.deadTimer ?? 0) + dt;
    if (state.deadTimer > 12) { state.stuckTimer = 5; state.deadTimer = 0; }

    if (state.stuckTimer > 4) {
      const spot = this._clearSpotAhead(net, state, along, vehicle);
      if (spot) {
        /*
         * Respawn at the lane's own elevation, not at ground level.
         *
         * The ground road graph is 2D and its `lanePointOnEdge` returns no `y` at all, so
         * hardcoding wheel height here was right for streets and silently wrong for the
         * elevated ring. Every highway car that tripped the stuck timer was teleported
         * off the viaduct to the road underneath, where it jammed against the piers and
         * tripped the timer again. Measured over 45 s of simulation, 11 of 12 highway
         * cars ended up on the ground at their correct ring radius - which is what gave
         * the game away.
         */
        const laneY = spot.y ?? 0;
        vehicle.body.setTranslation(
          { x: spot.x, y: laneY + vehicle.spec.wheelRadius + 0.5, z: spot.z }, true,
        );
        vehicle.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
        // Angular velocity too: a car that got flipped onto its nose in a pile-up keeps
        // its spin through a teleport and simply flips again where it lands.
        vehicle.body.setAngvel({ x: 0, y: 0, z: 0 }, true);
        vehicle.body.setRotation(
          { x: 0, y: Math.sin(spot.heading / 2), z: 0, w: Math.cos(spot.heading / 2) }, true,
        );
        state.edge = spot.edge;
        state.forward = spot.forward;
      }
      state.stuckTimer = 0;
    }

    vehicle.setInput({ throttle, brake, steer, handbrake: false });
    vehicle.headlightsOn = this._nightLights;
    vehicle.wake();
  }

  /**
   * Per-frame visual update.
   * @param {import('three/webgpu').Vector3} [focus] camera position, for LOD selection
   * @param {object} [wind] weather wind vector, drifts the smoke
   */
  render(dt, isNight = false, focus = null, wind = null, camera = null) {
    this._nightLights = isNight;
    for (const v of this.vehicles) {
      let distanceSq = 0;
      if (focus) {
        const t = v.body.translation();
        const dx = t.x - focus.x, dz = t.z - focus.z;
        distanceSq = dx * dx + dz * dz;
        if (v.setLodFromDistance) v.setLodFromDistance(distanceSq);
      }
      v.render(dt);
      // Skid marks and smoke are only worth generating near the camera; a car sliding
      // half a kilometre away would fill the ring buffer with marks nobody can see.
      if (!v.isBoat && distanceSq < 160 * 160) this._emitTyreFX(v, dt);
    }
    this.smoke.update(dt, wind, camera);
  }

  /**
   * The point the autopilot steers at, rolled forward onto the following edge when the
   * lookahead runs past the end of the current one.
   *
   * Clamping it to the current edge instead is what makes a pure-pursuit controller cut
   * corners: it aims at the end of the chord it is on, which sits inside the curve, and
   * on a closed loop that error compounds every segment until the car spirals into the
   * inside barrier. Rolling over keeps the target on the actual path.
   */
  _lookaheadPoint(net, state, along, lookahead) {
    const edge = state.edge;
    const remaining = lookahead - (1 - along) * edge.length;
    if (remaining <= 0) {
      return net.lanePointOnEdge(
        edge, MathUtils.clamp(along + lookahead / edge.length, 0, 1), state.forward, state.lane,
      );
    }

    const nodeId = state.forward ? edge.b : edge.a;
    const exits = net.exitsFrom(nodeId, edge.id);
    const next = exits.length ? net.edges[exits[0]] : null;
    if (!next) return net.lanePointOnEdge(edge, 1, state.forward, state.lane);

    const nextForward = next.a === nodeId;
    /*
     * Roll only a short way onto the next edge.
     *
     * At a right-angle junction the next edge runs perpendicular, so a target far along it
     * sits diagonally across the corner - and a pure-pursuit car drives straight at its
     * target. With a long lookahead that means straight over the corner block: cars were
     * ending up ten metres off-lane, wedged against buildings, at full throttle. Capping
     * the roll-over keeps the target just past the junction so the car turns *through* the
     * corner instead of across it.
     */
    const t = MathUtils.clamp(Math.min(remaining, 7) / next.length, 0, 1);
    return net.lanePointOnEdge(next, t, nextForward, state.lane);
  }

  /** Lay down skid marks and puff tyre smoke for whichever wheels are slipping. */
  _emitTyreFX(vehicle, dt) {
    const speed = Math.abs(vehicle.speed);
    if (speed < 1.2) return;
    vehicle.forward(this._fx);

    for (let i = 0; i < 4; i++) {
      const slip = vehicle.wheelSlip[i];
      const contact = vehicle.wheelContacts[i];
      if (!contact || slip < 0.35) continue;

      this.skids.mark(`${vehicle._id}:${i}`, contact, this._fx, slip);

      // Smoke only once the tyre is really letting go, and rate-limited by slip so a
      // gentle drift wisps while a handbrake turn billows.
      if (slip > 0.6 && this.rng() < slip * speed * dt * 0.9) {
        this.smoke.spawn(contact, {
          vx: (this.rng() - 0.5) * 1.6,
          vy: 0.7 + this.rng() * 0.9,
          vz: (this.rng() - 0.5) * 1.6,
          size: 0.7 + this.rng() * 0.7,
          life: 0.9 + this.rng() * 0.7,
          colour: 0.78,
          growth: 2.1,
        });
      }
    }

    // A wrecked engine trails smoke from the bonnet.
    if (vehicle.isSmoking && this.rng() < dt * 9) {
      const t = vehicle.body.translation();
      this._v.set(
        t.x + this._fx.x * vehicle.spec.chassis.hz * 0.8,
        t.y + 0.5,
        t.z + this._fx.z * vehicle.spec.chassis.hz * 0.8,
      );
      this.smoke.spawn(this._v, {
        vx: (this.rng() - 0.5) * 0.5, vy: 1.8, vz: (this.rng() - 0.5) * 0.5,
        size: 0.9, life: 1.8, colour: 0.28, growth: 1.9,
      });
    }
  }

  /**
   * Resolve a contact-force event into vehicle damage.
   * @param {object} a collider owner
   * @param {object} b collider owner
   * @param {number} magnitude total contact force
   */
  handleImpact(a, b, magnitude) {
    // Rapier reports force in newtons; a kerb strike is a few thousand, a real shunt is
    // tens of thousands. Below the floor it is just suspension chatter.
    if (magnitude < 9000) return;
    const damage = Math.min(38, (magnitude - 9000) / 2600);
    if (damage < 0.6) return;

    for (const owner of [a, b]) {
      if (!owner || !owner.applyDamage) continue;
      owner.applyDamage(damage);
      if (owner === this.playerVehicle) this.lastImpact = Math.max(this.lastImpact, damage);
    }
  }

  /** Cull traffic that has wandered far from the player and respawn it nearby. */
  recycle(playerPosition, radius = 700) {
    for (const [v, state] of this.ai) {
      const t = v.body.translation();
      const d = Math.hypot(t.x - playerPosition.x, t.z - playerPosition.z);
      if (d < radius) continue;
      // Re-seed onto the car's OWN network. Recycling a highway car onto a street drops
      // it off the viaduct and leaves it chasing ring waypoints from ground level.
      const net = state.network ?? this.city.network;
      // Elevated traffic circles a closed ring, so it is never truly "far away" in a way
      // that matters - and moving it would just teleport cars around in front of you.
      if (state.network) continue;
      /*
       * A scripted actor is never recycled. For ambient traffic the distance to the player
       * is only a budget question; for a mission car it IS the mission state - a chase is
       * lost by the gap - so dragging a runner that just cleared 700 m back to within 260
       * would undo the escape the player failed to prevent, and would do it invisibly.
       */
      if (state.scripted) continue;
      for (let i = 0; i < 24; i++) {
        const edge = net.edges[Math.floor(this.rng() * net.edges.length)];
        const p = net.lanePointOnEdge(edge, this.rng(), this.rng() < 0.5, 0);
        const dist = Math.hypot(p.x - playerPosition.x, p.z - playerPosition.z);
        if (dist > 90 && dist < 260 && !this._occupied(p.x, p.z, 10)) {
          const y = (p.y ?? 0) + v.spec.wheelRadius + 0.5;
          v.body.setTranslation({ x: p.x, y, z: p.z }, true);
          v.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
          v.body.setRotation(
            { x: 0, y: Math.sin(p.heading / 2), z: 0, w: Math.cos(p.heading / 2) }, true,
          );
          state.edge = p.edge;
          state.forward = p.forward;
          break;
        }
      }
    }
  }

  get count() { return this.vehicles.length; }
  get trafficCount() { return this.ai.size; }
}

export { DRIVABLE_CLASSES, approachAngle };
