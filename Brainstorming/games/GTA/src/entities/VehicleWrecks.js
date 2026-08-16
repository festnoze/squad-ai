/**
 * Burning wrecks and the blast that ends them.
 *
 * A car at zero health used to be a parked car: `applyDamage` cleared an `engineOn` flag
 * that nothing read, so a hull with no health left still drove, still let you in, and
 * still looked showroom-fresh apart from slightly darker paint. This gives it a fuse, a
 * fire, a blast radius and a charred shell.
 *
 * It lives outside `VehicleManager` deliberately. The blast has to reach the crowd and the
 * player as well as the car list, and none of that belongs in the traffic autopilot.
 *
 * Nothing here allocates per frame: the flame emitter reuses the shared smoke pool and
 * three scratch vectors, and the only object built per detonation is the one-off tally
 * returned to the caller.
 */

import { Vector3 } from 'three/webgpu';

/*
 * Blast tuning, measured with tools/probe-wreck.js against an unarmoured player:
 * 2 m costs 51 hp, 6 m costs 23 hp, 11 m and beyond costs nothing. Standing next to a
 * burning car is close to fatal, backing off two car lengths is survivable, and crossing
 * the street is safe - which is the shape that makes the fuse worth watching.
 */
const BLAST_RADIUS = 11;
const BLAST_PLAYER_DAMAGE = 70;
/** A neighbour on 20 hp four metres away takes ~29 and goes up in turn (measured). */
const BLAST_VEHICLE_DAMAGE = 55;
/**
 * Falloff exponent. Above 1 it keeps the lethal zone tight around the car and leaves the
 * fringe survivable, which is what makes "how close do I dare stand" a real question - a
 * linear falloff spreads the same total damage into a wide, mushy ring.
 */
const FALLOFF = 1.4;
/** Beyond this the flames are not worth pool slots; the blast itself still applies. */
const FX_DISTANCE = 190;

/**
 * Blast strength at a distance: 1 at the centre, 0 at the rim and beyond.
 *
 * Exported on its own because grenades and mission set pieces need the same curve without
 * needing a car to wreck first, and because a shared curve is the only way two weapons can
 * be balanced against each other.
 *
 * @param {number} distance metres from the seat of the blast
 * @param {number} radius metres at which it stops mattering
 * @param {number} [exponent] higher keeps the lethal zone tighter
 */
export function blastFalloff(distance, radius, exponent = FALLOFF) {
  if (!(distance < radius) || radius <= 0) return 0;
  return (1 - distance / radius) ** exponent;
}

export class WreckSystem {
  /**
   * @param {object} deps
   * @param {import('./VehicleManager.js').VehicleManager} deps.traffic
   * @param {import('./PedestrianManager.js').PedestrianManager} deps.peds
   * @param {import('./Player.js').Player} deps.player
   * @param {(vehicle:object)=>void} [deps.onIgnite] fired once when a car catches fire
   * @param {(point:Vector3, hit:object)=>void} [deps.onExplode]
   */
  constructor({ traffic, peds, player, onIgnite = null, onExplode = null }) {
    this.traffic = traffic;
    this.peds = peds;
    this.player = player;
    this.smoke = traffic.smoke;
    this.onIgnite = onIgnite;
    this.onExplode = onExplode;

    /** Detonations this session, for the debug overlay and for tests. */
    this.explosions = 0;
    this.burning = 0;

    this._p = new Vector3();
    this._pp = new Vector3();
    this._f = new Vector3();
    this._v = new Vector3();
  }

  /**
   * Where the game thinks the player is. `Player.update` returns early while driving and
   * the capsule is not stepped, so `player.position` is stale in a car - the same trap the
   * mission tracker and the smoke test both had to work around.
   */
  _playerPoint(out) {
    const car = this.traffic.playerVehicle;
    if (car) {
      const t = car.body.translation();
      return out.set(t.x, t.y, t.z);
    }
    return out.copy(this.player.position);
  }

  /** Fixed-step: advance every fuse, feed the fires, detonate what is due. */
  update(dt) {
    const focus = this._playerPoint(this._pp);
    let burning = 0;
    for (const v of this.traffic.vehicles) {
      if (!v.wrecked || v.exploded) continue;
      burning++;
      if (!v._wreckClaimed) {
        v._wreckClaimed = true;
        // A hulk with a dead driver is not traffic any more. Left in the AI map it would
        // keep tripping the stuck-recovery timer and teleport itself around the city.
        this.traffic.ai.delete(v);
        this.onIgnite?.(v);
      }
      v.fuse -= dt;
      this._flames(v, dt, focus);
      if (v.fuse <= 0) this.detonate(v);
    }
    this.burning = burning;
  }

  /** Flame and soot from the bonnet of a burning car. */
  _flames(vehicle, dt, focus) {
    const t = vehicle.body.translation();
    const dx = t.x - focus.x, dz = t.z - focus.z;
    if (dx * dx + dz * dz > FX_DISTANCE * FX_DISTANCE) return;

    vehicle.forward(this._f);
    const nose = vehicle.spec.chassis.hz * 0.72;
    this._v.set(t.x + this._f.x * nose, t.y + 0.45, t.z + this._f.z * nose);

    if (Math.random() < dt * 20) {
      this.smoke.spawn(this._v, {
        vx: (Math.random() - 0.5) * 0.7,
        vy: 2.4 + Math.random() * 1.6,
        vz: (Math.random() - 0.5) * 0.7,
        size: 0.5 + Math.random() * 0.4,
        life: 0.32 + Math.random() * 0.22,
        colour: 1, growth: 1.1,
        r: 3.4, g: 1.25, b: 0.28,
      });
    }
    if (Math.random() < dt * 9) {
      this.smoke.spawn(this._v, {
        vx: (Math.random() - 0.5) * 0.6,
        vy: 2.2,
        vz: (Math.random() - 0.5) * 0.6,
        size: 1, life: 2.2, colour: 0.22, growth: 2.4,
        r: 0.9, g: 0.86, b: 0.84,
      });
    }
  }

  /**
   * Blow up one car: char the shell, throw the player out of it, apply the blast.
   * @returns {object} tally `{ player, vehicles, peds, ignited }`
   */
  detonate(vehicle) {
    const point = this._p.copy(vehicle.position);
    vehicle.char();
    this.explosions++;

    // Out of the seat first. Damage is applied afterwards, from where the player lands,
    // so sitting in a car when it goes is close to fatal and never silently survivable.
    if (this.traffic.playerVehicle === vehicle) this.traffic.exit(this.player);

    const hit = this.blast(point, { source: vehicle });

    // Throw the hull. A wreck that simply stops reads as a scripted state change; one that
    // gets off the ground reads as a detonation underneath it.
    const mass = vehicle.spec.mass;
    vehicle.body.applyImpulse({
      x: (Math.random() - 0.5) * mass * 1.6,
      y: mass * (5 + Math.random() * 2),
      z: (Math.random() - 0.5) * mass * 1.6,
    }, true);
    vehicle.body.applyTorqueImpulse({
      x: (Math.random() - 0.5) * mass * 1.1,
      y: (Math.random() - 0.5) * mass * 0.5,
      z: (Math.random() - 0.5) * mass * 1.1,
    }, true);

    this.onExplode?.(point, hit);
    return hit;
  }

  /**
   * Damage everything around a point. Exposed on its own so anything else that needs a
   * bang (a mission set piece, a future grenade) does not have to wreck a car first.
   *
   * @param {Vector3} point
   * @param {object} [opts]
   * @returns {{player:number, vehicles:number, peds:number, ignited:number}}
   */
  blast(point, {
    radius = BLAST_RADIUS,
    playerDamage = BLAST_PLAYER_DAMAGE,
    vehicleDamage = BLAST_VEHICLE_DAMAGE,
    source = null,
  } = {}) {
    const hit = { player: 0, vehicles: 0, peds: 0, ignited: 0 };

    const pp = this._playerPoint(this._pp);
    const fp = blastFalloff(Math.hypot(pp.x - point.x, pp.y - point.y, pp.z - point.z), radius);
    if (fp > 0) {
      hit.player = playerDamage * fp;
      this.player.damage(hit.player);
    }

    for (const v of this.traffic.vehicles) {
      if (v === source || v.isBoat) continue;
      const t = v.body.translation();
      const dx = t.x - point.x, dy = t.y - point.y, dz = t.z - point.z;
      const d = Math.hypot(dx, dy, dz);
      const f = blastFalloff(d, radius);
      if (f === 0) continue;
      hit.vehicles++;
      // Shove it away from the seat of the blast, and up: a flat impulse just slides cars
      // along the road, which looks like a nudge rather than a shockwave.
      const inv = f * v.spec.mass * 4.5 / Math.max(0.6, d);
      v.body.applyImpulse({ x: dx * inv, y: Math.abs(dy) * inv + f * v.spec.mass * 2.2, z: dz * inv }, true);
      // A neighbour only goes up in turn if it was already badly hurt - a healthy car at
      // 6 m takes about a fifth of the damage, so chains need a reason, not just proximity.
      // `applyDamage` reports the wrecking hit only, so a hull caught in a second blast is
      // not counted twice and cannot restart its own fuse.
      if (v.applyDamage(vehicleDamage * f)) hit.ignited++;
    }

    const pedRadius = radius * 1.1;
    for (const ped of this.peds.peds) {
      if (!ped.active) continue;
      const d = Math.hypot(ped.position.x - point.x, ped.position.z - point.z);
      if (d > pedRadius) continue;
      this._v.set(ped.position.x - point.x, 0, ped.position.z - point.z);
      if (this._v.lengthSq() < 1e-4) this._v.set(1, 0, 0);
      this._v.normalize();
      if (this.peds.knockDown(ped, this._v)) hit.peds++;
    }
    this.peds.scatter(point, radius * 2.6);

    this._burst(point);
    return hit;
  }

  /** The fireball itself: a hot core that fades fast under a slow column of soot. */
  _burst(point) {
    for (let i = 0; i < 16; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.random() * 1.8;
      this._v.set(point.x + Math.cos(a) * r, point.y + 0.4 + Math.random() * 0.8, point.z + Math.sin(a) * r);
      this.smoke.spawn(this._v, {
        vx: Math.cos(a) * (2 + Math.random() * 4),
        vy: 3 + Math.random() * 4,
        vz: Math.sin(a) * (2 + Math.random() * 4),
        size: 1.4 + Math.random() * 1.4,
        life: 0.45 + Math.random() * 0.3,
        colour: 1, growth: 3.4,
        r: 3.6, g: 1.4, b: 0.3,
      });
    }
    for (let i = 0; i < 14; i++) {
      const a = Math.random() * Math.PI * 2;
      this._v.set(
        point.x + Math.cos(a) * Math.random() * 2.4,
        point.y + 0.6,
        point.z + Math.sin(a) * Math.random() * 2.4,
      );
      this.smoke.spawn(this._v, {
        vx: Math.cos(a) * (1 + Math.random() * 2),
        vy: 1.8 + Math.random() * 2.4,
        vz: Math.sin(a) * (1 + Math.random() * 2),
        size: 1.6 + Math.random() * 1.2,
        life: 2.4 + Math.random() * 1.6,
        colour: 0.2, growth: 3,
        r: 0.85, g: 0.82, b: 0.8,
      });
    }
  }

  /** Seconds left on the player's own car, or 0 - drives the bail-out prompt. */
  get playerFuse() {
    const car = this.traffic.playerVehicle;
    return car && car.wrecked && !car.exploded ? Math.max(0, car.fuse) : 0;
  }
}

export { BLAST_RADIUS, BLAST_PLAYER_DAMAGE, BLAST_VEHICLE_DAMAGE };
