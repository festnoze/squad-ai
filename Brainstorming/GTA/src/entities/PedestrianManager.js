/**
 * Pedestrian crowd.
 *
 * Peds walk the pavement ring around city blocks, cross at junctions, and get out of the
 * way of traffic. There is no navmesh: the block perimeters the city already generated
 * *are* the walkable network, so pedestrian routes and pavement geometry cannot disagree.
 *
 * Population is a fixed pool that recycles - peds that wander far from the camera are
 * teleported to a block near it rather than simulated at distance. The player therefore
 * always sees a busy street without paying for a whole city of agents.
 *
 * Bodies are kinematic capsules: they push nothing, but cars and the player collide with
 * them, and a hit above walking speed knocks them down.
 */

import { Group, Vector3, MathUtils } from 'three/webgpu';
import { CharacterMesh } from './CharacterMesh.js';
import { GROUP, groups } from '../physics/Physics.js';
import { makeRng } from '../core/Noise.js';

const RADIUS = 0.3;
const HALF_HEIGHT = 0.5;
const WALK_SPEED = 1.25;
const FLEE_SPEED = 4.4;
const PAVEMENT_INSET = 1.6;
/** Beyond this distance from the camera a ped is recycled rather than simulated. */
const CULL_DISTANCE = 150;
/** Detail tier boundaries, in metres from the camera. */
const LOD_SHADOW = 42;
const LOD_HIDE = 92;
const SPAWN_MIN = 25;
const SPAWN_MAX = 150;

const STATE = { WALK: 'walk', FLEE: 'flee', DOWN: 'down' };

export class PedestrianManager {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {import('../world/City.js').City} city
   * @param {import('three/webgpu').Scene} scene
   */
  constructor(physics, city, scene, { count = 44, seed = 4242 } = {}) {
    this.physics = physics;
    this.city = city;
    this.scene = scene;
    this.rng = makeRng(seed);

    this.group = new Group();
    this.group.name = 'pedestrians';
    scene.add(this.group);

    /** @type {Array<object>} */
    this.peds = [];
    this.knockdowns = 0;

    this._v = new Vector3();
    this._away = new Vector3();
    this._filter = groups(GROUP.PED, GROUP.TERRAIN | GROUP.STATIC | GROUP.BUILDING);

    for (let i = 0; i < count; i++) this._create();
  }

  get count() { return this.peds.length; }

  _create() {
    const mesh = new CharacterMesh({ rand: this.rng, scale: 0.94 + this.rng() * 0.16 });
    this.group.add(mesh.root);

    const { body, collider } = this.physics.addCharacterCapsule(
      new Vector3(0, -500, 0), RADIUS, HALF_HEIGHT, GROUP.PED,
    );

    const ped = {
      mesh,
      body,
      collider,
      position: new Vector3(0, -500, 0),
      yaw: 0,
      speed: 0,
      state: STATE.WALK,
      stateTimer: 0,
      block: null,
      corner: 0,
      target: new Vector3(),
      // Slight per-ped speed variation so a crowd does not move in lockstep.
      pace: 0.82 + this.rng() * 0.42,
      active: false,
    };
    this.physics.owners.set(collider.handle, ped);
    ped.isPedestrian = true;
    this.peds.push(ped);
    return ped;
  }

  /* ------------------------------------------------------------------ placement */

  /** Pavement waypoints around a block, walked in order. */
  _cornersFor(block) {
    const i = PAVEMENT_INSET;
    return [
      new Vector3(block.x0 - i, 0, block.z0 - i),
      new Vector3(block.x1 + i, 0, block.z0 - i),
      new Vector3(block.x1 + i, 0, block.z1 + i),
      new Vector3(block.x0 - i, 0, block.z1 + i),
    ];
  }

  /** Put a ped on a random block within a ring around `focus`. */
  _place(ped, focus) {
    const blocks = this.city.network.blocks;
    for (let attempt = 0; attempt < 30; attempt++) {
      const block = blocks[Math.floor(this.rng() * blocks.length)];
      const d = Math.hypot(block.cx - focus.x, block.cz - focus.z);
      if (d < SPAWN_MIN || d > SPAWN_MAX) continue;

      const corners = this._cornersFor(block);
      const corner = Math.floor(this.rng() * 4);
      const a = corners[corner], b = corners[(corner + 1) % 4];
      const t = this.rng();
      ped.block = block;
      ped.corner = corner;
      ped.position.set(a.x + (b.x - a.x) * t, 0.18, a.z + (b.z - a.z) * t);
      ped.target.copy(b);
      ped.state = STATE.WALK;
      ped.stateTimer = 0;
      ped.active = true;
      ped.mesh.root.visible = true;
      ped.body.setTranslation(
        { x: ped.position.x, y: ped.position.y + HALF_HEIGHT + RADIUS, z: ped.position.z }, true,
      );
      return true;
    }
    return false;
  }

  _retire(ped) {
    ped.active = false;
    ped.mesh.root.visible = false;
    ped.body.setTranslation({ x: 0, y: -500, z: 0 }, true);
  }

  /* ------------------------------------------------------------------ behaviour */

  /** Knock a ped down - called when a vehicle hits them. */
  knockDown(ped, impulseDir) {
    if (ped.state === STATE.DOWN) return false;
    ped.state = STATE.DOWN;
    ped.stateTimer = 4 + this.rng() * 3;
    ped.speed = 0;
    this.knockdowns++;
    if (impulseDir) {
      // Shove them a short way in the direction of travel, then leave them prone.
      ped.position.addScaledVector(impulseDir, 1.6);
    }
    return true;
  }

  /** Make everyone within `radius` run away from `point`. */
  scatter(point, radius = 18) {
    let scattered = 0;
    for (const ped of this.peds) {
      if (!ped.active || ped.state === STATE.DOWN) continue;
      if (ped.position.distanceTo(point) > radius) continue;
      ped.state = STATE.FLEE;
      ped.stateTimer = 3.5 + this.rng() * 3;
      scattered++;
    }
    return scattered;
  }

  /**
   * @param {number} dt
   * @param {Vector3} focus camera or player position
   * @param {object} [threats] `{ player, vehicles }` used for avoidance and fleeing
   */
  update(dt, focus, threats = {}) {
    for (const ped of this.peds) {
      if (!ped.active) { this._place(ped, focus); continue; }

      const distance = Math.hypot(ped.position.x - focus.x, ped.position.z - focus.z);
      if (distance > CULL_DISTANCE) { this._retire(ped); continue; }

      this._step(ped, dt, threats);
    }
  }

  _step(ped, dt, threats) {
    if (ped.state === STATE.DOWN) {
      ped.stateTimer -= dt;
      ped.speed = 0;
      // Face-down pose, then get up and carry on.
      ped.mesh.root.rotation.z = MathUtils.lerp(ped.mesh.root.rotation.z, Math.PI / 2, dt * 6);
      ped.mesh.root.position.copy(ped.position);
      if (ped.stateTimer <= 0) {
        ped.state = STATE.FLEE;
        ped.stateTimer = 4;
        ped.mesh.root.rotation.z = 0;
      }
      return;
    }
    ped.mesh.root.rotation.z = 0;

    /* --------------------------------------------------------------- threats */
    // Anything fast and close is a reason to run. Checking the squared distance keeps
    // this cheap enough to run against every vehicle each frame.
    let fleeing = ped.state === STATE.FLEE;
    this._away.set(0, 0, 0);
    if (threats.vehicles) {
      for (const v of threats.vehicles) {
        const t = v.body.translation();
        const dx = ped.position.x - t.x, dz = ped.position.z - t.z;
        const d2 = dx * dx + dz * dz;
        if (d2 > 12 * 12) continue;
        const speed = Math.abs(v.speed ?? 0);
        if (speed < 3) continue;
        const d = Math.sqrt(d2) || 0.001;
        this._away.x += (dx / d) * (12 - d);
        this._away.z += (dz / d) * (12 - d);
        fleeing = true;
        ped.stateTimer = Math.max(ped.stateTimer, 2.2);
      }
    }

    if (fleeing) {
      ped.state = STATE.FLEE;
      ped.stateTimer -= dt;
      if (ped.stateTimer <= 0 && this._away.lengthSq() < 0.01) {
        ped.state = STATE.WALK;
      }
    }

    /* -------------------------------------------------------------- steering */
    let dirX, dirZ, speed;
    if (ped.state === STATE.FLEE && this._away.lengthSq() > 0.01) {
      this._away.normalize();
      dirX = this._away.x; dirZ = this._away.z;
      speed = FLEE_SPEED;
    } else {
      // Walk the block perimeter, advancing to the next corner on arrival.
      const dx = ped.target.x - ped.position.x;
      const dz = ped.target.z - ped.position.z;
      const d = Math.hypot(dx, dz);
      if (d < 1.4) {
        ped.corner = (ped.corner + 1) % 4;
        const corners = this._cornersFor(ped.block);
        ped.target.copy(corners[(ped.corner + 1) % 4]);
        // Occasionally hop to a neighbouring block so crowds mix instead of orbiting.
        if (this.rng() < 0.12) {
          const blocks = this.city.network.blocks;
          for (let i = 0; i < 8; i++) {
            const b = blocks[Math.floor(this.rng() * blocks.length)];
            if (Math.hypot(b.cx - ped.position.x, b.cz - ped.position.z) < 130) {
              ped.block = b;
              ped.corner = Math.floor(this.rng() * 4);
              ped.target.copy(this._cornersFor(b)[(ped.corner + 1) % 4]);
              break;
            }
          }
        }
        return;
      }
      dirX = dx / d; dirZ = dz / d;
      speed = WALK_SPEED * ped.pace;
    }

    /* ------------------------------------------------------------ separation */
    // Keep a little personal space, or the crowd clumps into a single blob.
    for (const other of this.peds) {
      if (other === ped || !other.active) continue;
      const ox = ped.position.x - other.position.x;
      const oz = ped.position.z - other.position.z;
      const d2 = ox * ox + oz * oz;
      if (d2 > 1.6 * 1.6 || d2 < 1e-4) continue;
      const d = Math.sqrt(d2);
      dirX += (ox / d) * 0.55;
      dirZ += (oz / d) * 0.55;
    }
    const len = Math.hypot(dirX, dirZ) || 1;
    dirX /= len; dirZ /= len;

    ped.speed = speed;
    ped.position.x += dirX * speed * dt;
    ped.position.z += dirZ * speed * dt;
    // Peds walk on the pavement, which the city keeps flat at a known height.
    ped.position.y = 0.18;

    ped.body.setNextKinematicTranslation({
      x: ped.position.x, y: ped.position.y + HALF_HEIGHT + RADIUS, z: ped.position.z,
    });

    const targetYaw = Math.atan2(dirX, dirZ);
    let diff = targetYaw - ped.yaw;
    while (diff > Math.PI) diff -= Math.PI * 2;
    while (diff < -Math.PI) diff += Math.PI * 2;
    ped.yaw += MathUtils.clamp(diff, -6 * dt, 6 * dt);
  }

  /**
   * Per-frame visual update.
   * @param {Vector3} [focus] camera position, for detail selection
   */
  render(dt, focus = null) {
    for (const ped of this.peds) {
      if (!ped.active) continue;
      if (focus) {
        const dx = ped.position.x - focus.x, dz = ped.position.z - focus.z;
        const d2 = dx * dx + dz * dz;
        ped.mesh.setDetail(
          d2 > LOD_HIDE * LOD_HIDE ? 2 : d2 > LOD_SHADOW * LOD_SHADOW ? 1 : 0,
        );
        if (ped.mesh.detail === 2) continue;   // hidden: skip the animation work too
      }
      ped.mesh.root.position.copy(ped.position);
      ped.mesh.root.rotation.y = ped.yaw;
      ped.mesh.update(dt, {
        speed: ped.speed,
        grounded: true,
        mode: ped.state === STATE.DOWN ? 'idle'
          : ped.speed > 2.5 ? 'run' : ped.speed > 0.15 ? 'walk' : 'idle',
      });
    }
  }

  /** Blips for the radar. */
  blips(focus, radius = 140) {
    const out = [];
    for (const ped of this.peds) {
      if (!ped.active) continue;
      if (Math.abs(ped.position.x - focus.x) > radius) continue;
      if (Math.abs(ped.position.z - focus.z) > radius) continue;
      out.push({ x: ped.position.x, z: ped.position.z, kind: 'ped', size: 1.4 });
    }
    return out;
  }
}

export { STATE as PED_STATE };
