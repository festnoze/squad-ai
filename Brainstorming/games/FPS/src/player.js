import * as THREE from 'three';
import { moveAABB } from './collision.js';

const STAND_HEIGHT = 1.82;
const CROUCH_HEIGHT = 1.15;
const RADIUS = 0.36;
const GRAVITY = -24;
const JUMP_SPEED = 8.0;
const SPEED_WALK = 5.4;
const SPEED_SPRINT = 8.6;
const SPEED_CROUCH = 2.5;
const ACCEL_GROUND = 60;
const ACCEL_AIR = 14;
const FRICTION = 11;

const _delta = new THREE.Vector3();
const _wish = new THREE.Vector3();
const _center = new THREE.Vector3();
const _half = new THREE.Vector3();
const _tmp = new THREE.Vector3();

/** The player: capsule-ish AABB physics, look control, stamina-free sprint, health. */
export class Player {
  constructor(camera, colliders, audio) {
    this.camera = camera;
    this.colliders = colliders;
    this.audio = audio;

    this.position = new THREE.Vector3(); // feet
    this.velocity = new THREE.Vector3();
    this.yaw = 0;
    this.pitch = 0;
    this.recoilPitch = 0;
    this.recoilYaw = 0;

    this.height = STAND_HEIGHT;
    this.crouching = false;
    this.grounded = false;
    this.sprinting = false;
    this.moving = false;
    this.speed2D = 0;

    this.maxHealth = 100;
    this.health = 100;
    this.alive = true;
    this.timeSinceDamage = 999;
    this.lastDamageDir = new THREE.Vector3(0, 0, -1);
    this.damageFlash = 0;

    this.bobPhase = 0;
    this.bobAmount = 0;
    this.landDip = 0;
    this._wasGrounded = true;
    this._fallSpeed = 0;
    this._stepAccum = 0;

    this.kills = 0;
  }

  spawn(pos) {
    this.position.copy(pos);
    this.position.y += 0.05;
    this.velocity.set(0, 0, 0);
    this.height = STAND_HEIGHT;
    this.crouching = false;
    this.health = this.maxHealth;
    this.alive = true;
    this.recoilPitch = this.recoilYaw = 0;
    this.pitch = 0;
    this.damageFlash = 0;
    this.timeSinceDamage = 999;
    this.landDip = 0;
    this.bobPhase = 0;
  }

  get eyeY() {
    return this.position.y + this.height - 0.19 + this.bobAmount - this.landDip;
  }

  eyePosition(out = new THREE.Vector3()) {
    return out.set(this.position.x, this.eyeY, this.position.z);
  }

  forward(out = new THREE.Vector3()) {
    return out.set(0, 0, -1).applyQuaternion(this.camera.quaternion).normalize();
  }

  applyRecoil(pitchKick, yawKick) {
    this.recoilPitch += pitchKick;
    this.recoilYaw += yawKick;
  }

  damage(amount, fromPosition) {
    if (!this.alive) return;
    this.health -= amount;
    this.timeSinceDamage = 0;
    this.damageFlash = Math.min(1, this.damageFlash + amount / 45);
    if (fromPosition) {
      this.lastDamageDir.copy(fromPosition).sub(this.position).setY(0).normalize();
    }
    if (this.health <= 0) {
      this.health = 0;
      this.alive = false;
    }
  }

  heal(amount) {
    this.health = Math.min(this.maxHealth, this.health + amount);
  }

  update(dt, input, opts = {}) {
    const canLook = opts.canLook !== false;
    const canMove = opts.canMove !== false && this.alive;

    // ---- look ----
    if (canLook && input.active) {
      const sens = input.sensitivity * (opts.aimSensScale ?? 1);
      this.yaw -= input.mouseDX * sens;
      this.pitch -= (input.invertY ? -1 : 1) * input.mouseDY * sens;
      const limit = Math.PI / 2 - 0.02;
      this.pitch = Math.max(-limit, Math.min(limit, this.pitch));
    }
    // recoil eases back to the resting aim
    const recover = Math.exp(-8 * dt);
    this.recoilPitch *= recover;
    this.recoilYaw *= recover;

    // ---- crouch ----
    const wantCrouch = canMove &&
      input.any('ControlLeft', 'ControlRight', 'KeyC', 'char:c');
    const targetHeight = wantCrouch ? CROUCH_HEIGHT : STAND_HEIGHT;
    if (targetHeight > this.height) {
      // only stand up if there is room above
      const grown = Math.min(targetHeight, this.height + 6 * dt);
      _center.set(this.position.x, this.position.y + grown / 2, this.position.z);
      if (!this.colliders.overlaps(_center.x, _center.y, _center.z, RADIUS - 0.02, grown / 2 - 0.02, RADIUS - 0.02)) {
        this.height = grown;
      }
    } else if (targetHeight < this.height) {
      this.height = Math.max(targetHeight, this.height - 6 * dt);
    }
    this.crouching = this.height < STAND_HEIGHT - 0.15;

    // ---- desired velocity ----
    const axis = canMove ? input.moveAxis() : { x: 0, z: 0 };
    this.moving = axis.x !== 0 || axis.z !== 0;
    this.sprinting = canMove && this.moving && axis.z > 0.1 && !this.crouching &&
      (input.down('ShiftLeft') || input.down('ShiftRight')) && !opts.aiming;

    let maxSpeed = SPEED_WALK;
    if (this.crouching) maxSpeed = SPEED_CROUCH;
    else if (this.sprinting) maxSpeed = SPEED_SPRINT;
    if (opts.aiming && !this.sprinting) maxSpeed *= 0.55;

    // Camera-relative basis: forward is (-sin yaw, 0, -cos yaw), right is
    // (cos yaw, 0, -sin yaw), matching a YXZ camera that looks down -Z.
    const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    _wish.set(axis.x * cy - axis.z * sy, 0, -(axis.x * sy + axis.z * cy));
    if (_wish.lengthSq() > 0) _wish.normalize().multiplyScalar(maxSpeed);

    const accel = this.grounded ? ACCEL_GROUND : ACCEL_AIR;
    const vx = this.velocity.x, vz = this.velocity.z;
    let dx = _wish.x - vx;
    let dz = _wish.z - vz;
    const dlen = Math.hypot(dx, dz);
    if (dlen > 1e-5) {
      const step = Math.min(dlen, accel * dt);
      this.velocity.x += (dx / dlen) * step;
      this.velocity.z += (dz / dlen) * step;
    }
    // ground friction when there is no input
    if (this.grounded && !this.moving) {
      const sp = Math.hypot(this.velocity.x, this.velocity.z);
      if (sp > 0) {
        const drop = Math.min(sp, FRICTION * dt * Math.max(sp, 2));
        const k = Math.max(0, sp - drop) / sp;
        this.velocity.x *= k;
        this.velocity.z *= k;
      }
    }

    // ---- jump ----
    if (canMove && this.grounded && input.down('Space')) {
      this.velocity.y = JUMP_SPEED * (this.crouching ? 0.72 : 1);
      this.grounded = false;
      if (this.audio) this.audio.jump();
    }

    this.velocity.y += GRAVITY * dt;
    if (this.velocity.y < -55) this.velocity.y = -55;

    // ---- integrate + collide ----
    _delta.copy(this.velocity).multiplyScalar(dt);
    _half.set(RADIUS, this.height / 2, RADIUS);
    _center.set(this.position.x, this.position.y + this.height / 2, this.position.z);
    this._fallSpeed = this.velocity.y;
    const res = moveAABB(this.colliders, _center, _half, _delta, 0.55);
    this.position.set(_center.x, _center.y - this.height / 2, _center.z);

    if (res.grounded) {
      if (!this._wasGrounded) {
        const hard = this._fallSpeed < -13;
        this.landDip = Math.min(0.28, Math.abs(this._fallSpeed) * 0.014);
        if (this.audio) this.audio.land(hard);
        if (hard) this.damage(Math.min(35, (Math.abs(this._fallSpeed) - 13) * 3.2), null);
      }
      this.velocity.y = 0;
      this.grounded = true;
    } else {
      this.grounded = false;
    }
    if (res.hitCeiling && this.velocity.y > 0) this.velocity.y = 0;
    this._wasGrounded = this.grounded;

    // ---- head bob + footsteps ----
    this.speed2D = Math.hypot(this.velocity.x, this.velocity.z);
    if (this.grounded && this.speed2D > 0.6) {
      const rate = this.sprinting ? 12.5 : this.crouching ? 6 : 9;
      this.bobPhase += dt * rate;
      const amp = this.sprinting ? 0.075 : this.crouching ? 0.02 : 0.04;
      this.bobAmount = Math.sin(this.bobPhase * 2) * amp;
      this._stepAccum += dt * rate;
      if (this._stepAccum > Math.PI) {
        this._stepAccum -= Math.PI;
        if (this.audio) this.audio.footstep(this.sprinting);
      }
    } else {
      this.bobAmount += (0 - this.bobAmount) * Math.min(1, 8 * dt);
    }
    this.landDip *= Math.exp(-9 * dt);

    // ---- health regen ----
    this.timeSinceDamage += dt;
    if (this.alive && this.timeSinceDamage > 6 && this.health < this.maxHealth) {
      this.health = Math.min(this.maxHealth, this.health + 9 * dt);
    }
    this.damageFlash = Math.max(0, this.damageFlash - dt * 1.6);

    // ---- push the camera ----
    this.camera.position.set(this.position.x, this.eyeY, this.position.z);
    const roll = -_tmp.set(this.velocity.x, 0, this.velocity.z)
      .applyAxisAngle(new THREE.Vector3(0, 1, 0), -this.yaw).x * 0.0035;
    this.camera.rotation.set(
      this.pitch + this.recoilPitch,
      this.yaw + this.recoilYaw,
      roll + Math.sin(this.bobPhase) * 0.004,
      'YXZ'
    );
  }
}

export const PLAYER_RADIUS = RADIUS;
