/**
 * Rapier3D wrapper.
 *
 * Owns the world, runs it on a fixed 1/60 step, and keeps a registry of
 * (rigidBody -> Object3D) pairs it syncs into the scene graph after each step.
 *
 * Collision groups are 16-bit membership + 16-bit filter, packed into one u32. Using
 * explicit groups keeps character/vehicle/water queries from tripping over each other.
 */

import RAPIER from '@dimforge/rapier3d-compat';
import { Quaternion, Vector3 } from 'three/webgpu';

/** membership bits */
export const GROUP = {
  STATIC: 0x0001,
  TERRAIN: 0x0002,
  BUILDING: 0x0004,
  VEHICLE: 0x0008,
  PLAYER: 0x0010,
  PED: 0x0020,
  PROP: 0x0040,
  WATER: 0x0080,
  BULLET: 0x0100,
  TRIGGER: 0x0200,
};

const ALL = 0xffff;

/** Pack membership/filter into Rapier's InteractionGroups u32. */
export const groups = (membership, filter = ALL) => ((membership & 0xffff) << 16) | (filter & 0xffff);

export const FIXED_DT = 1 / 60;

let initialised = false;

/** Load the Rapier WASM module. Safe to call repeatedly. */
export async function initPhysicsEngine() {
  if (!initialised) {
    await RAPIER.init();
    initialised = true;
  }
  return RAPIER;
}

export { RAPIER };

export class Physics {
  constructor() {
    if (!initialised) throw new Error('call initPhysicsEngine() before constructing Physics');
    this.world = new RAPIER.World({ x: 0, y: -9.81, z: 0 });
    this.world.timestep = FIXED_DT;
    // A couple more solver iterations than default: stacked buildings and 4-wheel
    // vehicles both benefit, and we have the budget.
    this.world.numSolverIterations = 6;

    this.eventQueue = new RAPIER.EventQueue(true);
    /** @type {Array<{body: any, object: any, offset?: Vector3}>} */
    this.synced = [];
    /** colliderHandle -> arbitrary owner object, for resolving collision events */
    this.owners = new Map();
    this._q = new Quaternion();
    this._v = new Vector3();
    this._contactListeners = new Set();
  }

  /* -------------------------------------------------------------- body factories */

  /** Static trimesh-free box collider, e.g. a building or a wall. */
  addStaticBox(position, halfExtents, rotationY = 0, group = GROUP.BUILDING) {
    const bodyDesc = RAPIER.RigidBodyDesc.fixed()
      .setTranslation(position.x, position.y, position.z)
      .setRotation(quatFromY(rotationY));
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.cuboid(halfExtents.x, halfExtents.y, halfExtents.z)
      .setCollisionGroups(groups(group))
      .setFriction(0.9);
    const collider = this.world.createCollider(cd, body);
    return { body, collider };
  }

  /**
   * Static box with a full rotation rather than yaw only.
   *
   * Needed by anything whose surface is pitched as well as turned - a bridge approach
   * ramp, a road on a slope. A yaw-only collider under a pitched deck is a staircase:
   * the wheel raycasts find the flat top of each box and the car hammers up it.
   */
  addStaticBoxQuat(position, halfExtents, quat, group = GROUP.BUILDING) {
    const bodyDesc = RAPIER.RigidBodyDesc.fixed()
      .setTranslation(position.x, position.y, position.z)
      .setRotation({ x: quat.x, y: quat.y, z: quat.z, w: quat.w });
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.cuboid(halfExtents.x, halfExtents.y, halfExtents.z)
      .setCollisionGroups(groups(group))
      .setFriction(0.9);
    const collider = this.world.createCollider(cd, body);
    return { body, collider };
  }

  /** Infinite-ish ground plane approximation (a very wide, thin box). */
  addGround(y = 0, halfSize = 4096, group = GROUP.TERRAIN) {
    const bodyDesc = RAPIER.RigidBodyDesc.fixed().setTranslation(0, y - 2, 0);
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.cuboid(halfSize, 2, halfSize)
      .setCollisionGroups(groups(group))
      .setFriction(1.0);
    const collider = this.world.createCollider(cd, body);
    return { body, collider };
  }

  /**
   * Heightfield collider sampled from a height function.
   *
   * Rapier indexes the height matrix as `i * (ncols + 1) + j`, with i running along X and
   * j along Z. Getting this transposed mirrors the terrain about its diagonal, which is
   * invisible on a symmetric island and deeply confusing everywhere else - verified here
   * against an asymmetric probe point, not assumed.
   *
   * @param {(x:number,z:number)=>number} heightAt world-space height sampler
   * @param {number} samples grid resolution per axis (>= 2)
   * @param {number} size total width/depth in metres, centred on the origin
   */
  addHeightfieldFromFunction(heightAt, samples, size, group = GROUP.TERRAIN) {
    const n = Math.max(2, samples | 0);
    const heights = new Float32Array(n * n);
    let min = Infinity, max = -Infinity;
    for (let j = 0; j < n; j++) {
      const z = -size / 2 + (j / (n - 1)) * size;
      for (let i = 0; i < n; i++) {
        const x = -size / 2 + (i / (n - 1)) * size;
        const h = heightAt(x, z);
        heights[i * n + j] = h;
        if (h < min) min = h;
        if (h > max) max = h;
      }
    }
    // Rapier scales the height samples by scale.y, so feed it normalised heights and
    // put the real vertical range into the scale.
    const span = Math.max(1e-3, max - min);
    for (let k = 0; k < heights.length; k++) heights[k] = (heights[k] - min) / span;

    const bodyDesc = RAPIER.RigidBodyDesc.fixed().setTranslation(0, min, 0);
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.heightfield(
      n - 1, n - 1, heights, { x: size, y: span, z: size },
    )
      .setCollisionGroups(groups(group))
      .setFriction(1.0);
    const collider = this.world.createCollider(cd, body);
    return { body, collider, min, span };
  }

  /** Dynamic rigid body with one convex/box collider, wired for scene-graph sync. */
  addDynamicBox(position, halfExtents, {
    mass = 100, group = GROUP.PROP, friction = 0.7, restitution = 0.1,
    linearDamping = 0.02, angularDamping = 0.2, ccd = false,
  } = {}) {
    const bodyDesc = RAPIER.RigidBodyDesc.dynamic()
      .setTranslation(position.x, position.y, position.z)
      .setLinearDamping(linearDamping)
      .setAngularDamping(angularDamping)
      .setCcdEnabled(ccd);
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.cuboid(halfExtents.x, halfExtents.y, halfExtents.z)
      .setCollisionGroups(groups(group))
      .setFriction(friction)
      .setRestitution(restitution)
      .setMass(mass);
    const collider = this.world.createCollider(cd, body);
    return { body, collider };
  }

  /** Kinematic capsule for characters. `halfHeight` excludes the two hemispheres. */
  addCharacterCapsule(position, radius, halfHeight, group = GROUP.PLAYER) {
    const bodyDesc = RAPIER.RigidBodyDesc.kinematicPositionBased()
      .setTranslation(position.x, position.y, position.z);
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.capsule(halfHeight, radius)
      .setCollisionGroups(groups(group, ALL & ~GROUP.TRIGGER))
      .setFriction(0.0);
    const collider = this.world.createCollider(cd, body);
    return { body, collider };
  }

  /** Sensor volume that reports overlaps without pushing anything. */
  addSensorBox(position, halfExtents, owner, group = GROUP.TRIGGER) {
    const bodyDesc = RAPIER.RigidBodyDesc.fixed()
      .setTranslation(position.x, position.y, position.z);
    const body = this.world.createRigidBody(bodyDesc);
    const cd = RAPIER.ColliderDesc.cuboid(halfExtents.x, halfExtents.y, halfExtents.z)
      .setSensor(true)
      .setActiveEvents(RAPIER.ActiveEvents.COLLISION_EVENTS)
      .setCollisionGroups(groups(group));
    const collider = this.world.createCollider(cd, body);
    if (owner) this.owners.set(collider.handle, owner);
    return { body, collider };
  }

  createCharacterController(offset = 0.02) {
    const cc = this.world.createCharacterController(offset);
    cc.setApplyImpulsesToDynamicBodies(true);
    cc.enableAutostep(0.45, 0.25, true);
    cc.enableSnapToGround(0.5);
    cc.setMaxSlopeClimbAngle((50 * Math.PI) / 180);
    cc.setMinSlopeSlideAngle((38 * Math.PI) / 180);
    return cc;
  }

  createVehicleController(chassisBody) {
    return this.world.createVehicleController(chassisBody);
  }

  /* ---------------------------------------------------------------------- queries */

  /**
   * Cast a ray and return `{ point, normal, distance, collider }` or null.
   * @param {Vector3} origin
   * @param {Vector3} dir normalised
   */
  raycast(origin, dir, maxDistance = 100, filterGroups = groups(GROUP.BULLET), excludeCollider = null) {
    const ray = new RAPIER.Ray(
      { x: origin.x, y: origin.y, z: origin.z },
      { x: dir.x, y: dir.y, z: dir.z },
    );
    const hit = this.world.castRayAndGetNormal(
      ray, maxDistance, true, undefined, filterGroups, excludeCollider ?? undefined,
    );
    if (!hit) return null;
    return {
      distance: hit.timeOfImpact,
      point: new Vector3().copy(origin).addScaledVector(dir, hit.timeOfImpact),
      normal: new Vector3(hit.normal.x, hit.normal.y, hit.normal.z),
      collider: hit.collider,
      owner: this.owners.get(hit.collider?.handle) ?? null,
    };
  }

  /** Ground height under a point, or null if nothing within `maxDrop`. */
  groundHeight(x, z, from = 200, maxDrop = 400) {
    const hit = this.raycast(
      new Vector3(x, from, z), new Vector3(0, -1, 0), maxDrop,
      groups(GROUP.BULLET, GROUP.TERRAIN | GROUP.STATIC | GROUP.BUILDING | GROUP.PROP),
    );
    return hit ? hit.point.y : null;
  }

  /* ------------------------------------------------------------------- simulation */

  /** Register a rigid body whose transform should be copied onto an Object3D. */
  bind(body, object, offset = null) {
    this.synced.push({ body, object, offset });
  }

  unbind(object) {
    const i = this.synced.findIndex((s) => s.object === object);
    if (i >= 0) this.synced.splice(i, 1);
  }

  onContact(fn) { this._contactListeners.add(fn); return () => this._contactListeners.delete(fn); }

  /** Advance one fixed step and drain the event queue. */
  step() {
    this.world.step(this.eventQueue);
    if (this._contactListeners.size) {
      this.eventQueue.drainCollisionEvents((h1, h2, started) => {
        const a = this.owners.get(h1) ?? null;
        const b = this.owners.get(h2) ?? null;
        for (const fn of this._contactListeners) fn(a, b, started, h1, h2);
      });
      this.eventQueue.drainContactForceEvents((event) => {
        const a = this.owners.get(event.collider1()) ?? null;
        const b = this.owners.get(event.collider2()) ?? null;
        const mag = event.totalForceMagnitude();
        for (const fn of this._contactListeners) fn(a, b, 'force', mag);
      });
    }
  }

  /** Copy physics transforms onto the bound Object3Ds. Call once per render frame. */
  sync() {
    for (const s of this.synced) {
      const t = s.body.translation();
      const r = s.body.rotation();
      this._q.set(r.x, r.y, r.z, r.w);
      s.object.quaternion.copy(this._q);
      if (s.offset) {
        this._v.copy(s.offset).applyQuaternion(this._q);
        s.object.position.set(t.x + this._v.x, t.y + this._v.y, t.z + this._v.z);
      } else {
        s.object.position.set(t.x, t.y, t.z);
      }
    }
  }

  removeBody(body) {
    this.world.removeRigidBody(body);
  }

  dispose() {
    this.eventQueue.free();
    this.world.free();
  }
}

/** Quaternion literal for a yaw-only rotation, in Rapier's plain-object form. */
export function quatFromY(yaw) {
  const h = yaw * 0.5;
  return { x: 0, y: Math.sin(h), z: 0, w: Math.cos(h) };
}
