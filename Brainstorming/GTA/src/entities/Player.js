/**
 * The player on foot.
 *
 * Movement uses Rapier's KinematicCharacterController: we propose a translation each
 * fixed step and Rapier slides it along walls, steps up kerbs, and reports whether we are
 * grounded. Gravity is integrated manually so jump arcs stay under our control.
 *
 * The player is a state machine (`onFoot` / `driving` / `swimming`); the vehicle takes
 * over the transform while driving.
 */

import { Group, Vector3, MathUtils } from 'three/webgpu';
import { CharacterMesh } from './CharacterMesh.js';
import { GROUP, groups } from '../physics/Physics.js';

const RADIUS = 0.34;
const HALF_HEIGHT = 0.52;          // capsule cylinder half-height; total height ~1.72 m
const EYE_HEIGHT = 1.62;
const WALK_SPEED = 2.6;
const RUN_SPEED = 6.4;
const AIM_SPEED = 1.5;
const ACCEL = 22;
const AIR_ACCEL = 4;
const GRAVITY = -22;               // punchier than real gravity, standard for action games
const JUMP_SPEED = 6.4;
const TURN_RATE = 12;

/* ----------------------------------------------------------------- swimming */
const SWIM_SPEED = 2.3;
const SWIM_FAST = 3.8;
/** How much of the body sits below the waterline while treading water. */
const SWIM_DEPTH = 1.15;
/** Feet this far under the surface starts a swim; this far above ends one. */
const ENTER_DEPTH = 1.0;
const EXIT_DEPTH = 0.45;

export const PLAYER_STATE = { ON_FOOT: 'onFoot', DRIVING: 'driving', SWIMMING: 'swimming' };

export class Player {
  /**
   * @param {import('../physics/Physics.js').Physics} physics
   * @param {Vector3} spawn
   */
  constructor(physics, spawn) {
    this.physics = physics;
    this.state = PLAYER_STATE.ON_FOOT;

    this.group = new Group();
    this.group.name = 'player';
    this.character = new CharacterMesh({ rand: () => 0.42 });
    this.group.add(this.character.root);

    const { body, collider } = physics.addCharacterCapsule(
      new Vector3(spawn.x, spawn.y + HALF_HEIGHT + RADIUS, spawn.z), RADIUS, HALF_HEIGHT,
    );
    this.body = body;
    this.collider = collider;
    physics.owners.set(collider.handle, this);
    this.controller = physics.createCharacterController(0.02);

    /** World position of the feet. */
    this.position = new Vector3().copy(spawn);
    this.velocity = new Vector3();
    this.yaw = 0;
    this.targetYaw = 0;
    this.grounded = true;
    this.speed = 0;
    this.health = 100;
    this.armour = 0;
    this.aiming = false;
    /** Set by VehicleManager while driving. */
    this.vehicle = null;

    this._desired = new Vector3();
    this._move = new Vector3();
    this._coyote = 0;
    this._jumpBuffer = 0;
    this._filter = groups(
      GROUP.PLAYER,
      GROUP.TERRAIN | GROUP.STATIC | GROUP.BUILDING | GROUP.PROP | GROUP.VEHICLE,
    );
  }

  /**
   * Give the player the water and terrain they need to swim. Passed in after
   * construction because the island and ocean are built after the player spawns.
   */
  setWorld({ ocean = null, island = null } = {}) {
    this.ocean = ocean;
    this.island = island;
  }

  get isSwimming() { return this.state === PLAYER_STATE.SWIMMING; }

  get eyePosition() {
    return this._desired.set(this.position.x, this.position.y + EYE_HEIGHT, this.position.z);
  }

  get isOnFoot() { return this.state === PLAYER_STATE.ON_FOOT; }

  /**
   * Fixed-step simulation.
   * @param {number} dt fixed timestep
   * @param {{x:number,y:number}} moveInput analog move in camera space
   * @param {number} cameraYaw radians
   * @param {object} flags `{ sprint, jump, aiming }`
   */
  fixedUpdate(dt, moveInput, cameraYaw, flags = {}) {
    if (this.state === PLAYER_STATE.DRIVING) return;

    const { sprint = false, jump = false, aiming = false } = flags;
    this.aiming = aiming;

    /* -------------------------------------------------------------- water check */
    // Hysteresis on entry and exit: a single threshold makes the player flicker between
    // wading and swimming in the shallows, where the surface oscillates with the swell.
    this.waterDepth = this.ocean
      ? this.ocean.heightAt(this.position.x, this.position.z) - this.position.y
      : -Infinity;
    const wasSwimming = this.state === PLAYER_STATE.SWIMMING;
    if (!wasSwimming && this.waterDepth > ENTER_DEPTH) {
      this.state = PLAYER_STATE.SWIMMING;
      this.enteredWaterThisStep = true;
      this.velocity.y = Math.max(this.velocity.y, -2);
    } else if (wasSwimming && this.waterDepth < EXIT_DEPTH) {
      this.state = PLAYER_STATE.ON_FOOT;
      this.leftWaterThisStep = true;
    } else {
      this.enteredWaterThisStep = false;
      this.leftWaterThisStep = false;
    }

    // Camera-relative movement basis.
    const sin = Math.sin(cameraYaw), cos = Math.cos(cameraYaw);
    const wishX = moveInput.x * cos + moveInput.y * sin;
    const wishZ = -moveInput.x * sin + moveInput.y * cos;
    const wishLen = Math.hypot(wishX, wishZ);

    if (this.state === PLAYER_STATE.SWIMMING) {
      return this._swim(dt, wishX, wishZ, wishLen, sprint);
    }

    const maxSpeed = aiming ? AIM_SPEED : sprint ? RUN_SPEED : WALK_SPEED;
    const accel = this.grounded ? ACCEL : AIR_ACCEL;

    // Horizontal velocity approaches the wish vector; friction when there is no input.
    const targetX = wishLen > 0.01 ? (wishX / wishLen) * maxSpeed * Math.min(1, wishLen) : 0;
    const targetZ = wishLen > 0.01 ? (wishZ / wishLen) * maxSpeed * Math.min(1, wishLen) : 0;
    const blend = 1 - Math.exp(-accel * dt);
    this.velocity.x += (targetX - this.velocity.x) * blend;
    this.velocity.z += (targetZ - this.velocity.z) * blend;

    // Jump with a short coyote window and input buffer - forgiving without feeling loose.
    this._coyote = this.grounded ? 0.12 : Math.max(0, this._coyote - dt);
    this._jumpBuffer = jump ? 0.14 : Math.max(0, this._jumpBuffer - dt);
    if (this._jumpBuffer > 0 && this._coyote > 0) {
      this.velocity.y = JUMP_SPEED;
      this._coyote = 0;
      this._jumpBuffer = 0;
      this.grounded = false;
    } else if (this.grounded && this.velocity.y < 0) {
      this.velocity.y = -1.0;   // keep pressed into the ground for reliable snapping
    } else {
      this.velocity.y += GRAVITY * dt;
      this.velocity.y = Math.max(this.velocity.y, -55);
    }

    this._move.set(this.velocity.x * dt, this.velocity.y * dt, this.velocity.z * dt);
    this.controller.computeColliderMovement(this.collider, this._move, undefined, this._filter);
    const corrected = this.controller.computedMovement();
    const wasGrounded = this.grounded;
    this.grounded = this.controller.computedGrounded();

    // If the solver clipped vertical motion, kill the vertical velocity so we do not
    // accumulate downward speed while resting or ram upward into a ceiling.
    if (Math.abs(corrected.y - this._move.y) > 1e-4) {
      if (this._move.y < 0) this.velocity.y = this.grounded ? 0 : this.velocity.y * 0.2;
      else this.velocity.y = 0;
    }
    if (!wasGrounded && this.grounded) this.landedThisStep = true;
    else this.landedThisStep = false;

    const t = this.body.translation();
    const nx = t.x + corrected.x, ny = t.y + corrected.y, nz = t.z + corrected.z;
    this.body.setNextKinematicTranslation({ x: nx, y: ny, z: nz });
    this.position.set(nx, ny - HALF_HEIGHT - RADIUS, nz);

    this.speed = Math.hypot(this.velocity.x, this.velocity.z);

    // Face the direction of travel, or the camera when aiming.
    if (aiming) this.targetYaw = cameraYaw;
    else if (this.speed > 0.35) this.targetYaw = Math.atan2(this.velocity.x, this.velocity.z);
    const before = this.yaw;
    this.yaw = approachAngle(this.yaw, this.targetYaw, TURN_RATE * dt);
    this.turnRate = (this.yaw - before) / dt;
  }

  /**
   * Swimming. Buoyancy holds the body at a fixed depth rather than integrating gravity,
   * so the player bobs with the swell instead of sinking; horizontal movement still goes
   * through the character controller, which keeps jetties, hulls and sea walls solid.
   */
  _swim(dt, wishX, wishZ, wishLen, sprint) {
    const maxSpeed = sprint ? SWIM_FAST : SWIM_SPEED;
    const targetX = wishLen > 0.01 ? (wishX / wishLen) * maxSpeed * Math.min(1, wishLen) : 0;
    const targetZ = wishLen > 0.01 ? (wishZ / wishLen) * maxSpeed * Math.min(1, wishLen) : 0;
    // Water is draggy: acceleration and deceleration are both slow and symmetrical.
    const blend = 1 - Math.exp(-3.2 * dt);
    this.velocity.x += (targetX - this.velocity.x) * blend;
    this.velocity.z += (targetZ - this.velocity.z) * blend;

    // A spring towards the waterline, critically damped enough not to porpoise.
    const surface = this.ocean.heightAt(this.position.x, this.position.z);
    const desiredY = surface - SWIM_DEPTH;
    const error = desiredY - this.position.y;
    this.velocity.y = MathUtils.clamp(error * 7 - this.velocity.y * 0.25, -4, 4);

    this._move.set(this.velocity.x * dt, this.velocity.y * dt, this.velocity.z * dt);
    this.controller.computeColliderMovement(this.collider, this._move, undefined, this._filter);
    const corrected = this.controller.computedMovement();
    const t = this.body.translation();
    const nx = t.x + corrected.x, ny = t.y + corrected.y, nz = t.z + corrected.z;
    this.body.setNextKinematicTranslation({ x: nx, y: ny, z: nz });
    this.position.set(nx, ny - HALF_HEIGHT - RADIUS, nz);

    this.grounded = false;
    this.speed = Math.hypot(this.velocity.x, this.velocity.z);
    if (this.speed > 0.25) this.targetYaw = Math.atan2(this.velocity.x, this.velocity.z);
    const before = this.yaw;
    this.yaw = approachAngle(this.yaw, this.targetYaw, 5 * dt);
    this.turnRate = (this.yaw - before) / dt;
  }

  /** Per-frame visual update (runs at render rate, not fixed rate). */
  render(dt) {
    if (this.state === PLAYER_STATE.DRIVING) {
      this.group.visible = false;
      return;
    }
    this.group.visible = true;
    this.group.position.copy(this.position);
    this.group.rotation.y = this.yaw;

    // Swimming lays the body out prone at the surface. The rig is authored standing, so
    // it gets pitched forward and lifted by roughly the height of the torso.
    const swimPitch = this.state === PLAYER_STATE.SWIMMING ? 1.15 : 0;
    this.character.root.rotation.x = MathUtils.lerp(
      this.character.root.rotation.x, swimPitch, 1 - Math.exp(-8 * dt),
    );
    this.character.root.position.y = MathUtils.lerp(
      this.character.root.position.y,
      this.state === PLAYER_STATE.SWIMMING ? 0.55 : 0,
      1 - Math.exp(-8 * dt),
    );

    const mode = this.state === PLAYER_STATE.SWIMMING ? 'swim'
      : !this.grounded ? (this.velocity.y > 0.5 ? 'jump' : 'fall')
        : this.speed > WALK_SPEED + 0.6 ? 'run'
          : this.speed > 0.2 ? 'walk' : 'idle';

    this.character.update(dt, {
      speed: this.speed, grounded: this.grounded, turnRate: this.turnRate ?? 0, mode,
    });
  }

  /** Hide the body and hand control to a vehicle. */
  enterVehicle(vehicle) {
    this.state = PLAYER_STATE.DRIVING;
    this.vehicle = vehicle;
    this.velocity.set(0, 0, 0);
    // Park the capsule far below the map so it cannot collide while we are in a car.
    this.body.setNextKinematicTranslation({ x: 0, y: -500, z: 0 });
    this.character.update(1 / 60, { mode: 'drive' });
  }

  /** Place the player back on their feet next to the vehicle they left. */
  exitVehicle(worldPosition) {
    this.state = PLAYER_STATE.ON_FOOT;
    this.vehicle = null;
    this.position.copy(worldPosition);
    this.body.setTranslation(
      { x: worldPosition.x, y: worldPosition.y + HALF_HEIGHT + RADIUS, z: worldPosition.z }, true,
    );
    this.body.setNextKinematicTranslation(
      { x: worldPosition.x, y: worldPosition.y + HALF_HEIGHT + RADIUS, z: worldPosition.z },
    );
    this.velocity.set(0, 0, 0);
    this.grounded = false;
  }

  /** Hard reposition, used by respawn and mission teleports. */
  teleport(position, yaw = this.yaw) {
    this.position.copy(position);
    this.yaw = this.targetYaw = yaw;
    this.velocity.set(0, 0, 0);
    this.body.setTranslation(
      { x: position.x, y: position.y + HALF_HEIGHT + RADIUS, z: position.z }, true,
    );
  }

  damage(amount) {
    const toArmour = Math.min(this.armour, amount * 0.65);
    this.armour -= toArmour;
    this.health = Math.max(0, this.health - (amount - toArmour));
    return this.health <= 0;
  }

  heal(amount) { this.health = Math.min(100, this.health + amount); }
}

/** Shortest-arc angle approach, wrapping correctly across +/-pi. */
export function approachAngle(current, target, maxDelta) {
  let diff = target - current;
  while (diff > Math.PI) diff -= Math.PI * 2;
  while (diff < -Math.PI) diff += Math.PI * 2;
  return current + MathUtils.clamp(diff, -maxDelta, maxDelta);
}
