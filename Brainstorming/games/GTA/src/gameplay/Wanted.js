/**
 * Wanted level and police pursuit.
 *
 * Heat is a continuous value that decays over time; the star rating is just that value
 * bucketed. Crimes add heat, and the star count decides how many cruisers are dispatched
 * and how aggressively they drive. Decay only runs while the player is "cool" - out of
 * sight of any pursuing unit - which is what makes losing the police a matter of breaking
 * line of sight rather than waiting out a timer.
 *
 * Pursuit reuses the road graph: cruisers path to the player's nearest node with A*, then
 * switch to direct pursuit once they are close enough to see them.
 */

import { Vector3, MathUtils } from 'three/webgpu';
import { GROUP, groups } from '../physics/Physics.js';

/** Heat thresholds for each star. */
const STAR_THRESHOLDS = [0, 1, 2.6, 4.6, 7.2, 10.5];
const MAX_HEAT = 13;

export const CRIME = {
  PED_HIT: 1.6,
  PED_KILL: 2.4,
  VEHICLE_RAM: 0.35,
  POLICE_RAM: 1.8,
  CAR_THEFT: 0.9,
  RECKLESS: 0.06,
};

const PURSUIT_SIGHT = 140;
/** Inside this range a pursuing unit is considered to have you regardless of cover. */
const CONTACT_RANGE = 45;
/** Cooling only begins once every unit is beyond this range AND out of sight. */
const EVADE_RANGE = 75;
const DISPATCH_INTERVAL = 6;

export class WantedSystem {
  /**
   * @param {object} deps `{ physics, city, traffic, player, hud }`
   */
  constructor({ physics, city, traffic, player, hud }) {
    this.physics = physics;
    this.city = city;
    this.traffic = traffic;
    this.player = player;
    this.hud = hud;

    this.heat = 0;
    this.stars = 0;
    /** @type {Array<{vehicle: object, path: number[], pathIndex: number, seen: boolean}>} */
    this.units = [];
    this.dispatchTimer = 0;
    this.coolTimer = 0;
    this.busted = 0;
    /** Set once any unit has actually found the player during this wanted period. */
    this.engaged = false;

    this._v = new Vector3();
    this._target = new Vector3();
    this._rayDir = new Vector3();
    this._sightFilter = groups(
      GROUP.BULLET, GROUP.BUILDING | GROUP.STATIC | GROUP.TERRAIN,
    );
  }

  /** Add heat for a crime. */
  report(amount, reason = '') {
    if (amount <= 0) return;
    const before = this.stars;
    this.heat = Math.min(MAX_HEAT, this.heat + amount);
    this._recomputeStars();
    // Any fresh crime resets the cool-down window.
    this.coolTimer = 0;
    if (this.stars > before) {
      this.hud.say(
        this.stars === 1 ? 'Wanted' : `Wanted level ${this.stars}`, 2.4,
      );
      if (reason) this.lastReason = reason;
    }
  }

  _recomputeStars() {
    let stars = 0;
    for (let i = 1; i < STAR_THRESHOLDS.length; i++) {
      if (this.heat >= STAR_THRESHOLDS[i]) stars = i;
    }
    this.stars = stars;
  }

  get isWanted() { return this.stars > 0; }

  /** Player position, or their vehicle's if they are driving. */
  _playerPoint(out) {
    const car = this.traffic.playerVehicle;
    if (car) {
      const t = car.body.translation();
      return out.set(t.x, t.y, t.z);
    }
    return out.copy(this.player.position);
  }

  /**
   * Can this cruiser see the player? Blocked by buildings, except at close range - a
   * unit right behind you has not lost you just because a corner briefly intervened,
   * and a strict ray test in a dense grid means the heat drains during an active chase.
   */
  _hasSight(fromX, fromY, fromZ, target) {
    const dx = target.x - fromX, dy = (target.y + 1) - fromY, dz = target.z - fromZ;
    const distance = Math.hypot(dx, dy, dz);
    if (distance > PURSUIT_SIGHT) return false;
    if (distance < CONTACT_RANGE) return true;
    this._rayDir.set(dx / distance, dy / distance, dz / distance);
    const hit = this.physics.raycast(
      this._v.set(fromX, fromY + 1, fromZ), this._rayDir, distance - 1.5, this._sightFilter,
    );
    return !hit;
  }

  /* ------------------------------------------------------------------ dispatch */

  /** How many cruisers should be chasing at the current star level. */
  get desiredUnits() {
    return [0, 1, 2, 3, 5, 6][this.stars] ?? 0;
  }

  _dispatch(playerPoint) {
    const net = this.city.network;
    // Spawn out of sight, on a road, at a plausible response distance.
    for (let attempt = 0; attempt < 40; attempt++) {
      const edge = net.edges[Math.floor(Math.random() * net.edges.length)];
      const p = net.lanePointOnEdge(edge, Math.random(), Math.random() < 0.5, 0);
      const d = Math.hypot(p.x - playerPoint.x, p.z - playerPoint.z);
      if (d < 90 || d > 320) continue;
      // Do not drop a cruiser on top of parked traffic - it starts the chase wedged.
      if (this.traffic._occupied(p.x, p.z, 9)) continue;

      const vehicle = this.traffic.spawnPolice(
        new Vector3(p.x, 0.9, p.z), p.heading,
      );
      this.units.push({ vehicle, path: null, pathIndex: 0, seen: false, stuck: 0 });
      return true;
    }
    return false;
  }

  _retire(unit) {
    const i = this.units.indexOf(unit);
    if (i >= 0) this.units.splice(i, 1);
    // Hand the cruiser back to normal traffic rather than deleting it, so the streets
    // keep a police presence after a chase ends.
    this.traffic.ai.set(unit.vehicle, {
      edge: this.city.network.edges[0], forward: true, lane: 0,
      targetSpeed: 16, patience: 0, stuckTimer: 0,
    });
    const near = this.city.network.nearestOnRoad(
      unit.vehicle.position.x, unit.vehicle.position.z,
    );
    if (near) {
      const state = this.traffic.ai.get(unit.vehicle);
      state.edge = near.edge;
      state.forward = true;
    }
  }

  /* ------------------------------------------------------------------- update */

  update(dt) {
    const playerPoint = this._playerPoint(this._target);

    if (!this.isWanted) {
      // Cool off: heat bleeds away and any remaining units disengage.
      this.heat = Math.max(0, this.heat - dt * 0.5);
      this.engaged = false;
      while (this.units.length) this._retire(this.units[0]);
      return;
    }

    /* ------------------------------------------------------------- cool-down */
    let anySight = false;
    let nearest = Infinity;
    for (const unit of this.units) {
      const t = unit.vehicle.body.translation();
      unit.seen = this._hasSight(t.x, t.y, t.z, playerPoint);
      if (unit.seen) anySight = true;
      nearest = Math.min(nearest, Math.hypot(t.x - playerPoint.x, t.z - playerPoint.z));
    }
    if (anySight) this.engaged = true;
    // Evading means genuinely breaking away, not just ducking behind one building while
    // a cruiser sits on your bumper - and you cannot evade police who have not found you
    // yet, or the level would expire while units were still en route.
    const evading = this.engaged && !anySight && nearest > EVADE_RANGE;
    if (evading) this.coolTimer += dt;
    else this.coolTimer = 0;

    if (this.coolTimer > 8 + this.stars * 2.5) {
      this.heat = Math.max(0, this.heat - dt * 0.55);
      this._recomputeStars();
    }

    /* -------------------------------------------------------------- dispatch */
    this.dispatchTimer -= dt;
    if (this.dispatchTimer <= 0) {
      this.dispatchTimer = DISPATCH_INTERVAL;
      if (this.units.length < this.desiredUnits) this._dispatch(playerPoint);
      else if (this.units.length > this.desiredUnits) this._retire(this.units[this.units.length - 1]);
    }

    for (const unit of [...this.units]) this._drive(unit, dt, playerPoint);
  }

  /** Pursuit driving: A* to the player's road node, direct pursuit once in sight. */
  _drive(unit, dt, playerPoint) {
    const car = unit.vehicle;
    const net = this.city.network;
    const pos = car.position;
    const distance = Math.hypot(pos.x - playerPoint.x, pos.z - playerPoint.z);

    // Give up on anything that has fallen hopelessly behind.
    if (distance > 520) { this._retire(unit); return; }

    let aimX, aimZ;
    if (unit.seen && distance < 70) {
      // Straight for the target - ramming is the point at higher star levels.
      aimX = playerPoint.x;
      aimZ = playerPoint.z;
    } else {
      /*
       * Follow the road graph. Repath only when the goal actually moves to a different
       * junction, never on a timer: a timed repath restarts the route from whichever
       * node is currently nearest, which - for a car mid-way along an edge - is usually
       * the one it just left. The cruiser then turns around, and repeats, and never
       * closes. That is exactly what "stuck at 230 m forever" looks like.
       */
      const goal = net.nearestNode(playerPoint.x, playerPoint.z);
      if (!unit.path || unit.pathIndex >= unit.path.length || unit.goalId !== goal.id) {
        const from = net.nearestNode(pos.x, pos.z);
        unit.path = from && goal ? net.findPath(from.id, goal.id) : null;
        unit.goalId = goal.id;
        unit.pathIndex = 1;
      }

      let node = unit.path && net.nodes[unit.path[unit.pathIndex]];
      // Skip ahead if the following waypoint is already closer - stops the car doubling
      // back to touch a node it has effectively passed.
      const after = unit.path && net.nodes[unit.path[unit.pathIndex + 1]];
      if (node && after
        && Math.hypot(after.x - pos.x, after.z - pos.z)
         < Math.hypot(node.x - pos.x, node.z - pos.z)) {
        unit.pathIndex++;
        node = after;
      }
      if (node) {
        if (Math.hypot(node.x - pos.x, node.z - pos.z) < 14) unit.pathIndex++;
        aimX = node.x;
        aimZ = node.z;
      } else {
        aimX = playerPoint.x;
        aimZ = playerPoint.z;
      }
    }

    const heading = car.heading;
    let error = Math.atan2(aimX - pos.x, aimZ - pos.z) - heading;
    while (error > Math.PI) error -= Math.PI * 2;
    while (error < -Math.PI) error += Math.PI * 2;

    const speed = Math.abs(car.speed);
    // Higher star levels drive harder.
    const aggression = 0.6 + this.stars * 0.11;
    const targetSpeed = MathUtils.clamp(
      (unit.seen ? 34 : 26) * aggression * (1 - Math.abs(error) * 0.6), 4, 44,
    );
    const delta = targetSpeed - speed;

    car.setInput({
      throttle: MathUtils.clamp(delta * 0.4, 0, 1),
      brake: MathUtils.clamp(-delta * 0.3, 0, 1),
      steer: MathUtils.clamp(error * 1.8, -1, 1),
      handbrake: false,
    });
    car.headlightsOn = true;
    car.wake();

    // Unstick cruisers wedged against scenery or traffic. Kept short: a pursuit unit
    // stalled against a parked car is the difference between a chase and a stalemate.
    if (speed < 0.6) unit.stuck += dt; else unit.stuck = 0;
    if (unit.stuck > 2.5) {
      const near = net.nearestOnRoad(pos.x, pos.z);
      if (near) {
        const lane = net.lanePointOnEdge(near.edge, near.t, true, 0);
        car.body.setTranslation({ x: lane.x, y: 1.0, z: lane.z }, true);
        car.body.setLinvel({ x: 0, y: 0, z: 0 }, true);
        car.body.setRotation(
          { x: 0, y: Math.sin(lane.heading / 2), z: 0, w: Math.cos(lane.heading / 2) }, true,
        );
      }
      // Force a fresh route: the old one starts from where it was jammed.
      unit.path = null;
      unit.stuck = 0;
    }

    // Close enough for long enough with no escape: busted.
    if (unit.seen && distance < 6 && speed < 3 && !this.traffic.playerVehicle) {
      unit.bustTimer = (unit.bustTimer ?? 0) + dt;
      if (unit.bustTimer > 2.5) this._bust();
    } else {
      unit.bustTimer = 0;
    }

    this._shootAt(unit, dt, distance);
  }

  /**
   * Return fire.
   *
   * Until this existed, vehicle collisions were the *only* thing in the game that could
   * take a point of health off the player - police could ram you and arrest you but never
   * hurt you, which made a five-star wanted level a chase with no stakes.
   *
   * Officers only open fire from three stars up, and only once a unit has actually seen
   * the player: being shot by a car that has not found you yet reads as a bug, not as
   * danger. The shot is a raycast so cover genuinely works, and the fire rate is per unit
   * so a bigger response is a heavier one.
   */
  _shootAt(unit, dt, distance) {
    unit.fireTimer = (unit.fireTimer ?? this.rng?.() ?? 0.7) - dt;
    if (this.stars < 3 || !unit.seen || distance > 34 || distance < 3) return;
    if (unit.fireTimer > 0) return;
    unit.fireTimer = 0.55 + Math.random() * 0.7;

    const p = this.player.position;
    const t = unit.vehicle.body.translation();
    // Fire from just above the cruiser's roofline towards the player's chest.
    this._from ??= new Vector3();
    this._dir ??= new Vector3();
    this._from.set(t.x, t.y + 1.1, t.z);
    this._dir.set(p.x - this._from.x, (p.y + 0.9) - this._from.y, p.z - this._from.z).normalize();

    // Exclude the shooter's own cruiser: the muzzle sits just above its roof and the ray
    // otherwise clips the bodywork it is fired from, so the officer takes cover behind
    // his own car and almost never gets a shot away.
    const hit = this.physics.raycast(
      this._from, this._dir, distance + 2,
      groups(GROUP.PED, GROUP.PLAYER | GROUP.BUILDING | GROUP.PROP | GROUP.TERRAIN | GROUP.VEHICLE),
      unit.vehicle.collider,
    );
    // Anything solid in the way is cover. Only a clear line reaches the player.
    if (hit && hit.collider !== this.player.collider) return;

    // Accuracy falls off with range so a sprint for cover is worth making.
    const aim = MathUtils.clamp(1 - distance / 44, 0.15, 0.85);
    if (Math.random() > aim) { this.onShot?.(this._from, false); return; }
    this.player.damage(7 + Math.random() * 5);
    this.onShot?.(this._from, true);
  }

  _bust() {
    this.busted++;
    this.hud.say('Busted', 4);
    this.clear();
    this.onBusted?.();
  }

  /** Drop all heat and disengage - used by respawn and by cheats. */
  clear() {
    this.heat = 0;
    this.stars = 0;
    this.engaged = false;
    this.coolTimer = 0;
    while (this.units.length) this._retire(this.units[0]);
  }

  /** Radar blips for active pursuit units. */
  get blips() {
    return this.units.map((u) => {
      const t = u.vehicle.body.translation();
      return { x: t.x, z: t.z, kind: 'wanted', size: 3.5, pin: true };
    });
  }
}
