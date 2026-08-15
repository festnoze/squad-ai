/**
 * Drivable boats.
 *
 * Buoyancy is solved by sampling the hull at a grid of points each step. Every submerged
 * sample pushes up with a force proportional to how deep it is, applied at its own world
 * position - so the hull naturally pitches over swells, rolls into turns, and settles at
 * the right waterline without any of it being scripted.
 *
 * On top of that sit the forces that make a boat feel like a boat rather than a floating
 * car: thrust from a stern propeller (so throttle also yaws the boat when the rudder is
 * over), heavy lateral drag (a hull resists sideways motion far more than forward), and a
 * planing term that lifts the bow as speed builds.
 */

import { Group, Mesh, Vector3, Quaternion, MathUtils } from 'three/webgpu';
import { GeometryBuilder } from '../world/GeometryBuilder.js';
import { makeCarPaint, getCarGlass, getMaterial, getFlat } from '../render/Materials.js';
import { GROUP, groups, RAPIER } from '../physics/Physics.js';

const WATER_DENSITY = 1000;
const GRAVITY = 9.81;

export const BOAT_CLASSES = {
  speedboat: {
    label: 'Speedboat',
    mass: 1150,
    hull: { hx: 1.15, hy: 0.62, hz: 3.4 },
    thrust: 26000,
    reverseThrust: 9000,
    rudder: 2.1,
    topSpeed: 32,
    // Sample grid: how many points along each hull axis contribute buoyancy.
    samples: { x: 3, z: 6 },
    // Volume is tuned so the hull floats with the deck comfortably clear.
    displacement: 2.6,
    deckColour: 0xd8d4c8,
  },
  cruiser: {
    label: 'Cruiser',
    mass: 3200,
    hull: { hx: 1.7, hy: 0.95, hz: 5.4 },
    thrust: 52000,
    reverseThrust: 18000,
    rudder: 1.5,
    topSpeed: 24,
    samples: { x: 3, z: 7 },
    displacement: 6.4,
    deckColour: 0xe2ded2,
  },
  dinghy: {
    label: 'Dinghy',
    mass: 420,
    hull: { hx: 0.85, hy: 0.42, hz: 2.1 },
    thrust: 8200,
    reverseThrust: 3200,
    rudder: 2.6,
    topSpeed: 20,
    samples: { x: 2, z: 4 },
    displacement: 1.1,
    deckColour: 0x9aa8a4,
  },
};

/* ----------------------------------------------------------------------- geometry */

const geometryCache = new Map();

/** Hull: a lofted V-section that narrows and rises towards the bow. */
function buildBoatGeometry(className) {
  if (geometryCache.has(className)) return geometryCache.get(className);
  const spec = BOAT_CLASSES[className];
  const { hx, hy, hz } = spec.hull;

  const hull = new GeometryBuilder();
  const deck = new GeometryBuilder();
  const trim = new GeometryBuilder();

  // Stations from stern (-hz) to bow (+hz): half-width, keel depth, gunwale height.
  const stations = [
    { z: -hz, hw: hx * 0.86, keel: -hy * 0.55, top: hy },
    { z: -hz * 0.55, hw: hx * 1.0, keel: -hy * 0.95, top: hy * 1.02 },
    { z: 0.0, hw: hx * 1.0, keel: -hy * 1.0, top: hy * 1.05 },
    { z: hz * 0.45, hw: hx * 0.88, keel: -hy * 0.9, top: hy * 1.12 },
    { z: hz * 0.8, hw: hx * 0.58, keel: -hy * 0.62, top: hy * 1.2 },
    { z: hz, hw: hx * 0.14, keel: -hy * 0.22, top: hy * 1.3 },
  ];

  const V = (x, y, z) => new Vector3(x, y, z);
  for (let i = 0; i < stations.length - 1; i++) {
    const a = stations[i], c = stations[i + 1];
    // Topsides: gunwale down to the keel line, both flanks.
    for (const side of [1, -1]) {
      const n = new Vector3(side, 0.35, 0).normalize();
      const p0 = V(a.hw * side, a.top, a.z);
      const p1 = V(0.06 * side, a.keel, a.z);
      const p2 = V(0.06 * side, c.keel, c.z);
      const p3 = V(c.hw * side, c.top, c.z);
      if (side > 0) hull.quad(p0, p3, p2, p1, [0, 0], [1, 0], [1, 1], [0, 1], n);
      else hull.quad(p0, p1, p2, p3, [0, 0], [0, 1], [1, 1], [1, 0], n);
    }
    // Deck.
    deck.quad(
      V(-a.hw, a.top, a.z), V(a.hw, a.top, a.z), V(c.hw, c.top, c.z), V(-c.hw, c.top, c.z),
      [0, 0], [1, 0], [1, 1], [0, 1], new Vector3(0, 1, 0),
    );
  }
  // Transom.
  const s0 = stations[0];
  hull.quad(
    V(-s0.hw, s0.top, s0.z), V(-0.06, s0.keel, s0.z), V(0.06, s0.keel, s0.z), V(s0.hw, s0.top, s0.z),
    [0, 0], [0, 1], [1, 1], [1, 0], new Vector3(0, 0, -1),
  );

  // Gunwale rail so the deck has an edge.
  for (const side of [1, -1]) {
    for (let i = 0; i < stations.length - 1; i++) {
      const a = stations[i], c = stations[i + 1];
      const cx = (a.hw + c.hw) / 2 * side;
      const cz = (a.z + c.z) / 2;
      const len = Math.abs(c.z - a.z) / 2;
      const yaw = Math.atan2((c.hw - a.hw) * side, c.z - a.z);
      trim.rotatedBox(cx, (a.top + c.top) / 2 + 0.06, cz, 0.09, 0.09, len, -yaw, 1);
    }
  }

  // Windscreen / console for the larger classes.
  const glass = new GeometryBuilder();
  if (className !== 'dinghy') {
    const cz = hz * 0.05;
    const w = hx * 0.72;
    trim.box(V(-w, hy * 1.05, cz - 0.7), V(w, hy * 1.05 + 0.75, cz + 0.7), 1.2);
    glass.quad(
      V(-w, hy * 1.05 + 0.75, cz + 0.7), V(w, hy * 1.05 + 0.75, cz + 0.7),
      V(w * 0.86, hy * 1.05 + 1.35, cz + 0.25), V(-w * 0.86, hy * 1.05 + 1.35, cz + 0.25),
      [0, 0], [1, 0], [1, 1], [0, 1], new Vector3(0, 0.5, 1).normalize(),
    );
  }
  if (className === 'cruiser') {
    // Cabin box forward of the console.
    trim.box(V(-hx * 0.8, hy * 1.05, hz * 0.18), V(hx * 0.8, hy * 1.05 + 1.5, hz * 0.72), 1.6);
  }

  const set = {
    hull: hull.build(),
    deck: deck.build(),
    trim: trim.isEmpty ? null : trim.build(),
    glass: glass.isEmpty ? null : glass.build(),
    spec,
  };
  geometryCache.set(className, set);
  return set;
}

/* -------------------------------------------------------------------------- boat */

export class Boat {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('../world/Ocean.js').Ocean} ocean
   */
  constructor(physics, ocean, {
    className = 'speedboat', position = new Vector3(), heading = 0, colour = 0xb8453a,
    island = null,
  } = {}) {
    this.physics = physics;
    this.ocean = ocean;
    this.island = island;
    this.className = className;
    this.spec = BOAT_CLASSES[className];

    const set = buildBoatGeometry(className);
    this.group = new Group();
    this.group.name = `boat_${className}`;
    const hullMesh = new Mesh(set.hull, makeCarPaint(colour));
    hullMesh.castShadow = true;
    const deckMesh = new Mesh(set.deck, getFlat(this.spec.deckColour, { roughness: 0.7 }));
    deckMesh.castShadow = true;
    deckMesh.receiveShadow = true;
    this.group.add(hullMesh, deckMesh);
    if (set.trim) this.group.add(new Mesh(set.trim, getMaterial('wood')));
    if (set.glass) this.group.add(new Mesh(set.glass, getCarGlass()));

    const { hx, hy, hz } = this.spec.hull;
    const bodyDesc = RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(position.x, position.y, position.z)
      .setRotation({ x: 0, y: Math.sin(heading / 2), z: 0, w: Math.cos(heading / 2) })
      // Water damping is applied explicitly below; keep the built-in damping low.
      .setLinearDamping(0.12)
      .setAngularDamping(0.9);
    this.body = physics.world.createRigidBody(bodyDesc);

    /*
     * Boats deliberately do NOT collide with the terrain heightfield or with city kerbs.
     * A hull resting on a broad collision surface fights the buoyancy solver - contact
     * resolution pins it at whatever depth it first touched, so heavy hulls hang above
     * the waterline instead of settling into it. Vertical position is owned entirely by
     * buoyancy, with `_applyGrounding` below providing an explicit run-aground rule.
     * Piers, sea walls and other craft are still solid.
     */
    const colliderDesc = RAPIER.ColliderDesc.cuboid(hx, hy, hz)
      .setCollisionGroups(groups(
        GROUP.VEHICLE,
        GROUP.VEHICLE | GROUP.PLAYER | GROUP.PED | GROUP.BUILDING | GROUP.PROP,
      ))
      .setFriction(0.35)
      .setRestitution(0.15)
      .setMass(this.spec.mass);
    this.collider = physics.world.createCollider(colliderDesc, this.body);
    physics.owners.set(this.collider.handle, this);

    // Precompute hull sample points in local space.
    this.samplePoints = [];
    const { x: nx, z: nz } = this.spec.samples;
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < nz; j++) {
        const u = nx === 1 ? 0 : (i / (nx - 1)) * 2 - 1;
        const v = nz === 1 ? 0 : (j / (nz - 1)) * 2 - 1;
        // Taper the sample grid towards the bow to match the hull shape.
        const taper = 1 - Math.max(0, v) * 0.55;
        this.samplePoints.push(new Vector3(u * hx * 0.85 * taper, -hy * 0.55, v * hz * 0.9));
      }
    }
    this.sampleVolume = this.spec.displacement / this.samplePoints.length;

    this.throttle = 0;
    this.reverse = 0;
    this.steer = 0;
    this.speed = 0;
    this.occupied = false;
    this.health = 100;

    this._q = new Quaternion();
    this._pos = new Vector3();
    this._world = new Vector3();
    this._force = new Vector3();
    this._forward = new Vector3();
    this._right = new Vector3();
    this._up = new Vector3();
    this._vel = new Vector3();
    this._pointVel = new Vector3();
    this._r = new Vector3();
    this._angVel = new Vector3();

    this.submersion = 0;
    this.group.position.copy(position);
  }

  /** Marks this as a watercraft for the shared vehicle manager. */
  get isBoat() { return true; }

  /** Half-length used for proximity checks; cars expose the same property. */
  get enterRadius() { return this.spec.hull.hz; }

  get position() {
    const t = this.body.translation();
    return this._pos.set(t.x, t.y, t.z);
  }

  get speedKmh() { return Math.abs(this.speed) * 3.6; }
  get gearLabel() { return this.reverse > 0.05 ? 'R' : this.throttle > 0.05 ? 'F' : 'N'; }

  get heading() {
    const r = this.body.rotation();
    this._q.set(r.x, r.y, r.z, r.w);
    this._forward.set(0, 0, 1).applyQuaternion(this._q);
    return Math.atan2(this._forward.x, this._forward.z);
  }

  setInput({ throttle = 0, brake = 0, steer = 0 }) {
    this.throttle = MathUtils.clamp(throttle, 0, 1);
    this.reverse = MathUtils.clamp(brake, 0, 1);
    this.steer = MathUtils.clamp(steer, -1, 1);
  }

  /** Fixed-step hydrodynamics. */
  fixedUpdate(dt) {
    /*
     * Rapier force accumulators are PERSISTENT: `addForce` / `addForceAtPoint` /
     * `addTorque` keep applying every step until explicitly reset (unlike impulses,
     * which are one-shot). Without this reset the buoyancy applied while the hull is in
     * the water is re-applied for the rest of the session, so boats accelerate upward
     * without bound and fly away.
     */
    // A moored boat that has settled and gone to sleep needs no buoyancy solve. The
    // `false` is `wakeUp`: passing `true` would wake it again every step and keep the
    // whole fleet permanently simulated.
    if (!this.occupied && this.body.isSleeping()) return;
    this.body.resetForces(false);
    this.body.resetTorques(false);

    const t = this.body.translation();
    const r = this.body.rotation();
    this._q.set(r.x, r.y, r.z, r.w);
    const lv = this.body.linvel();
    this._vel.set(lv.x, lv.y, lv.z);
    const av = this.body.angvel();
    this._angVel.set(av.x, av.y, av.z);

    this._forward.set(0, 0, 1).applyQuaternion(this._q);
    this._right.set(1, 0, 0).applyQuaternion(this._q);
    this._up.set(0, 1, 0).applyQuaternion(this._q);
    this.speed = this._vel.dot(this._forward);

    /* ------------------------------------------------------------- buoyancy */
    let submergedSamples = 0;
    for (const local of this.samplePoints) {
      this._world.copy(local).applyQuaternion(this._q).add({ x: t.x, y: t.y, z: t.z });
      const depth = this.ocean.heightAt(this._world.x, this._world.z) - this._world.y;
      if (depth <= 0) continue;
      submergedSamples++;

      // Archimedes, clamped so a briefly-plunged bow does not launch the boat.
      const displaced = Math.min(depth, 1.2) * this.sampleVolume;
      const lift = WATER_DENSITY * GRAVITY * displaced;

      // Velocity of this specific point, so drag damps rotation as well as translation.
      this._r.copy(this._world).sub({ x: t.x, y: t.y, z: t.z });
      this._pointVel.copy(this._angVel).cross(this._r).add(this._vel);
      // Vertical drag is what stops the hull oscillating like a spring.
      const verticalDrag = -this._pointVel.y * 900 * Math.min(1, depth);

      this._force.set(0, lift + verticalDrag, 0);
      this.body.addForceAtPoint(
        { x: this._force.x, y: this._force.y, z: this._force.z },
        { x: this._world.x, y: this._world.y, z: this._world.z },
        true,
      );
    }
    this.submersion = submergedSamples / this.samplePoints.length;
    const inWater = this.submersion > 0.05;

    this._applyGrounding(t);

    if (!inWater) return;   // airborne after a jump: let gravity do its thing

    /* ------------------------------------------------------------ propulsion */
    const drive = this.throttle * this.spec.thrust - this.reverse * this.spec.reverseThrust;
    if (Math.abs(drive) > 1) {
      // Thrust acts at the stern, so steering while under power swings the tail out -
      // the characteristic way a boat turns.
      const sternLocal = this._r.set(0, -this.spec.hull.hy * 0.3, -this.spec.hull.hz * 0.92)
        .applyQuaternion(this._q);
      const throttled = Math.abs(this.speed) > this.spec.topSpeed && drive > 0 ? drive * 0.12 : drive;
      this._force.copy(this._forward).multiplyScalar(throttled * this.submersion);
      this.body.addForceAtPoint(
        { x: this._force.x, y: this._force.y, z: this._force.z },
        { x: t.x + sternLocal.x, y: t.y + sternLocal.y, z: t.z + sternLocal.z },
        true,
      );
    }

    /* ---------------------------------------------------------------- rudder */
    // Rudder authority needs water flowing past it: no speed, no steering.
    const flow = MathUtils.clamp(Math.abs(this.speed) / 6, 0, 1);
    const power = Math.max(this.throttle, this.reverse * 0.6);
    const turn = this.steer * this.spec.rudder * this.spec.mass * 2.2
      * (0.35 + flow * 0.65) * (0.4 + power * 0.6) * Math.sign(this.speed >= 0 ? 1 : -1);
    this.body.addTorque({ x: 0, y: -turn, z: 0 }, true);

    /* ------------------------------------------------------------------ drag */
    // Anisotropic drag: a hull slips forward and resists sideways hard.
    const vForward = this._vel.dot(this._forward);
    const vRight = this._vel.dot(this._right);
    const dragForward = -vForward * Math.abs(vForward) * 22 * this.submersion;
    const dragLateral = -vRight * Math.abs(vRight) * 420 * this.submersion
      - vRight * 900 * this.submersion;
    this._force.copy(this._forward).multiplyScalar(dragForward)
      .addScaledVector(this._right, dragLateral);
    this.body.addForce({ x: this._force.x, y: this._force.y, z: this._force.z }, true);

    // Angular drag, and a righting moment that keeps the boat upright.
    this.body.addTorque({
      x: -this._angVel.x * this.spec.mass * 1.6,
      y: -this._angVel.y * this.spec.mass * 0.9,
      z: -this._angVel.z * this.spec.mass * 1.6,
    }, true);
    const tilt = this._up.y;   // 1 upright, 0 on its side
    if (tilt < 0.999) {
      const righting = this._right.clone().cross(new Vector3(0, 1, 0));
      void righting;
      // Torque proportional to how far the hull's up-axis has fallen from vertical.
      this.body.addTorque({
        x: -this._up.z * this.spec.mass * 14 * this.submersion,
        y: 0,
        z: this._up.x * this.spec.mass * 14 * this.submersion,
      }, true);
    }

    /* ---------------------------------------------------------------- planing */
    // Above a threshold the hull rises and the bow lifts.
    if (vForward > 6) {
      const plane = MathUtils.clamp((vForward - 6) / 12, 0, 1);
      this.body.addForce({ x: 0, y: plane * this.spec.mass * 4.2, z: 0 }, true);
      const bow = this._forward.clone().multiplyScalar(this.spec.hull.hz * 0.8);
      this.body.addForceAtPoint(
        { x: 0, y: plane * this.spec.mass * 2.6, z: 0 },
        { x: t.x + bow.x, y: t.y + bow.y, z: t.z + bow.z },
        true,
      );
    }
  }

  /**
   * Run-aground constraint. Because boats ignore the terrain collider, beaching is
   * handled here: a soft spring pushes the hull up off the sea bed and scrubs speed,
   * which reads as grinding to a halt on sand rather than bouncing off a wall.
   */
  _applyGrounding(t) {
    if (!this.island) return;
    const bed = this.island.heightAt(t.x, t.z);
    const keel = t.y - this.spec.hull.hy;
    const penetration = bed - keel;
    this.aground = penetration > 0;
    if (!this.aground) return;

    const push = Math.min(penetration, 1.5) * this.spec.mass * 26;
    const damp = -this.body.linvel().y * this.spec.mass * 4;
    this.body.addForce({ x: 0, y: push + damp, z: 0 }, true);

    // Friction against the bottom: heavy longitudinal and lateral scrub.
    const lv = this.body.linvel();
    const scrub = Math.min(1, penetration * 2) * this.spec.mass * 3.2;
    this.body.addForce({ x: -lv.x * scrub * 0.1, y: 0, z: -lv.z * scrub * 0.1 }, true);
  }

  render() {
    const t = this.body.translation();
    const r = this.body.rotation();
    this.group.position.set(t.x, t.y, t.z);
    this.group.quaternion.set(r.x, r.y, r.z, r.w);
  }

  /** Where to put the player when they step off. */
  exitPoint(out = new Vector3()) {
    const r = this.body.rotation();
    this._q.set(r.x, r.y, r.z, r.w);
    const side = out.set(-(this.spec.hull.hx + 0.6), this.spec.hull.hy, 0).applyQuaternion(this._q);
    const t = this.body.translation();
    return out.set(t.x + side.x, t.y + side.y, t.z + side.z);
  }

  cameraFocus(out = new Vector3()) {
    const t = this.body.translation();
    return out.set(t.x, t.y + 0.8, t.z);
  }

  wake() { this.body.wakeUp(); }

  dispose() {
    this.physics.owners.delete(this.collider.handle);
    this.physics.world.removeRigidBody(this.body);
    this.group.removeFromParent();
  }
}

export function disposeBoatGeometry() {
  for (const set of geometryCache.values()) {
    set.hull.dispose();
    set.deck.dispose();
    set.trim?.dispose();
    set.glass?.dispose();
  }
  geometryCache.clear();
}
