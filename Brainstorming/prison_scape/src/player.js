import * as THREE from 'three';
import { moveAABB } from './collision.js';

const STAND_H = 1.80;
const CROUCH_H = 1.15;
const RADIUS = 0.40;
const WALK = 4.2;
const SPRINT = 6.8;
const CROUCH_SPEED = 2.1;
const ACCEL = 42;
const GRAVITY = -22;
const JUMP = 6.6;

/**
 * The escapee. Owns movement, stance, health, inventory and the disguise -
 * everything the guards and cameras read when they decide whether to care.
 */
export class Player {
  constructor(world, camera, audio) {
    this.world = world;
    this.camera = camera;
    this.audio = audio;

    this.position = new THREE.Vector3();
    this.velocity = new THREE.Vector3();
    this.yaw = 0;
    this.pitch = 0;
    this.height = STAND_H;
    this.targetHeight = STAND_H;
    this.grounded = true;
    this.crouching = false;
    this.sprinting = false;

    this.health = 100;
    this.maxHealth = 100;
    this.alive = true;

    /** Uniform stripped from a downed guard. Cameras ignore it entirely. */
    this.disguised = false;
    this.disguiseBlownTimer = 0;

    /** How loud the player currently is, in metres a guard can hear them. */
    this.noiseRadius = 0;
    this.noiseSpike = 0;

    this.medkits = 0;
    this.headBob = 0;
    this._bobPhase = 0;
    this._stepAccum = 0;
    this._wasGrounded = true;
    this._half = new THREE.Vector3(RADIUS, STAND_H / 2, RADIUS);
    this._delta = new THREE.Vector3();
    this._wish = new THREE.Vector3();
    this.viewKick = new THREE.Vector2();
    this.damageFlash = 0;
  }

  spawn(tileVec3, yaw) {
    this.position.copy(tileVec3);
    this.position.y = STAND_H / 2 + 0.02;
    this.velocity.set(0, 0, 0);
    this.yaw = yaw;
    this.pitch = 0;
    this.height = this.targetHeight = STAND_H;
    this.health = this.maxHealth;
    this.alive = true;
    this.disguised = false;
    this.disguiseBlownTimer = 0;
    this.medkits = 0;
    this.damageFlash = 0;
    this.viewKick.set(0, 0);
  }

  /** Eye position, the origin of every shot and every line-of-sight test. */
  get eye() {
    return new THREE.Vector3(
      this.position.x,
      this.position.y + this.height * 0.5 - 0.16 + this.headBob,
      this.position.z
    );
  }

  /** Centre of mass, what guards aim at. */
  get chest() {
    return new THREE.Vector3(this.position.x, this.position.y + 0.15, this.position.z);
  }

  get forward() {
    return new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
  }

  lookDir() {
    const cp = Math.cos(this.pitch);
    return new THREE.Vector3(
      -Math.sin(this.yaw) * cp,
      Math.sin(this.pitch),
      -Math.cos(this.yaw) * cp
    ).normalize();
  }

  applyLook(dx, dy, sensitivity, invertY) {
    this.yaw -= dx * sensitivity;
    this.pitch -= dy * sensitivity * (invertY ? -1 : 1);
    const lim = Math.PI / 2 - 0.03;
    this.pitch = Math.max(-lim, Math.min(lim, this.pitch));
  }

  /** Recoil, applied to the view and decayed back over the next few frames. */
  addKick(pitchKick, yawKick) {
    this.viewKick.x += pitchKick;
    this.viewKick.y += yawKick;
  }

  damage(amount) {
    if (!this.alive) return;
    this.health -= amount;
    this.damageFlash = Math.min(1, this.damageFlash + amount / 45);
    this.audio.playerHurt();
    if (this.health <= 0) {
      this.health = 0;
      this.alive = false;
    }
  }

  heal(amount) {
    this.health = Math.min(this.maxHealth, this.health + amount);
  }

  /** Puts on a looted uniform. Cameras stop caring; guards need to get close. */
  wearUniform() {
    this.disguised = true;
    this.disguiseBlownTimer = 0;
    this.audio.disguise();
  }

  /** Firing in view of a living guard gives the game away. */
  blowDisguise() {
    if (!this.disguised) return false;
    this.disguised = false;
    return true;
  }

  update(dt, input, canMove) {
    // ---------------------------------------------------------------- look
    if (input.active) {
      this.applyLook(input.mouseDX, input.mouseDY, input.sensitivity, input.invertY);
    }
    // recoil decay
    this.viewKick.multiplyScalar(Math.pow(0.0008, dt));
    if (this.viewKick.lengthSq() < 1e-8) this.viewKick.set(0, 0);

    // -------------------------------------------------------------- stance
    const wantsCrouch = canMove && input.any('ControlLeft', 'ControlRight', 'KeyC', 'char:c');
    this.crouching = wantsCrouch || this._blockedFromStanding();
    this.targetHeight = this.crouching ? CROUCH_H : STAND_H;
    const prevHeight = this.height;
    this.height += (this.targetHeight - this.height) * Math.min(1, dt * 11);
    // Grow/shrink around the feet, not the centre.
    this.position.y += (this.height - prevHeight) * 0.5;
    this._half.y = this.height / 2;

    // ------------------------------------------------------------ movement
    const axis = canMove ? input.moveAxis() : { x: 0, z: 0 };
    this.sprinting = canMove && !this.crouching && input.any('ShiftLeft', 'ShiftRight')
      && axis.z > 0.1 && this.grounded;

    const speed = this.crouching ? CROUCH_SPEED : (this.sprinting ? SPRINT : WALK);
    const sin = Math.sin(this.yaw), cos = Math.cos(this.yaw);
    this._wish.set(
      axis.x * cos - axis.z * sin,
      0,
      -axis.x * sin - axis.z * cos
    );
    if (this._wish.lengthSq() > 1e-6) this._wish.normalize().multiplyScalar(speed);

    const control = this.grounded ? 1 : 0.28;
    this.velocity.x += (this._wish.x - this.velocity.x) * Math.min(1, ACCEL * control * dt / speed || 0);
    this.velocity.z += (this._wish.z - this.velocity.z) * Math.min(1, ACCEL * control * dt / speed || 0);
    if (this._wish.lengthSq() < 1e-6 && this.grounded) {
      const damp = Math.pow(0.0005, dt);
      this.velocity.x *= damp;
      this.velocity.z *= damp;
    }

    if (canMove && this.grounded && input.pressedAny('Space')) {
      this.velocity.y = JUMP;
      this.grounded = false;
    }
    this.velocity.y += GRAVITY * dt;

    this._delta.set(this.velocity.x * dt, this.velocity.y * dt, this.velocity.z * dt);
    const res = moveAABB(this.world.colliders, this.position, this._half, this._delta, 0.55);

    if (res.grounded) {
      if (!this._wasGrounded && this.velocity.y < -6) {
        this.audio.land(this.velocity.y < -12);
        this.noiseSpike = Math.max(this.noiseSpike, 14);
      }
      this.velocity.y = 0;
    }
    if (res.hitCeiling && this.velocity.y > 0) this.velocity.y = 0;
    this.grounded = res.grounded;
    this._wasGrounded = res.grounded;

    // ---------------------------------------------------- bob, steps, noise
    const planar = Math.hypot(this.velocity.x, this.velocity.z);
    if (this.grounded && planar > 0.4) {
      this._bobPhase += dt * (this.sprinting ? 13 : this.crouching ? 6 : 9);
      this.headBob = Math.sin(this._bobPhase) * (this.sprinting ? 0.055 : 0.032);
      this._stepAccum += planar * dt;
      const stride = this.sprinting ? 2.3 : this.crouching ? 2.6 : 1.9;
      if (this._stepAccum > stride) {
        this._stepAccum = 0;
        this.audio.footstep(this.sprinting);
      }
    } else {
      this.headBob *= Math.pow(0.02, dt);
      this._bobPhase = 0;
    }

    // Guards hear sprinting from across a room and crouch-walking barely at all.
    let noise = 0;
    if (planar > 0.4) noise = this.sprinting ? 20 : this.crouching ? 3.5 : 11;
    this.noiseSpike = Math.max(0, this.noiseSpike - dt * 22);
    this.noiseRadius = Math.max(noise, this.noiseSpike);

    this.damageFlash = Math.max(0, this.damageFlash - dt * 1.6);

    this.syncCamera();
  }

  /** Standing up would clip us into geometry, so stay down. */
  _blockedFromStanding() {
    if (this.height > STAND_H - 0.05) return false;
    const cy = this.position.y - this.height / 2 + STAND_H / 2;
    return this.world.colliders.overlaps(
      this.position.x, cy, this.position.z,
      RADIUS - 0.02, STAND_H / 2 - 0.02, RADIUS - 0.02
    );
  }

  syncCamera() {
    const eye = this.eye;
    this.camera.position.copy(eye);
    this.camera.rotation.set(0, 0, 0);
    this.camera.rotation.order = 'YXZ';
    this.camera.rotation.y = this.yaw + this.viewKick.y;
    this.camera.rotation.x = this.pitch + this.viewKick.x;
    // slight roll when strafing, for weight (right vector is (cos, 0, -sin))
    const strafe = this.velocity.x * Math.cos(this.yaw) - this.velocity.z * Math.sin(this.yaw);
    this.camera.rotation.z = THREE.MathUtils.clamp(-strafe * 0.006, -0.05, 0.05);
  }
}
