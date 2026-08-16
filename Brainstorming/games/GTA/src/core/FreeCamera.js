/**
 * Debug / photo-mode free camera.
 *
 * Detaches the view from the player so the world can be inspected from anywhere. Beyond
 * debugging it is the foundation for mission cutscenes: `flyTo()` drives a smooth
 * interpolation that a scripted sequence can drive frame by frame.
 *
 * Toggle in game with `P`. While active the player simulation keeps running.
 */

import { Vector3, MathUtils } from 'three/webgpu';

export class FreeCamera {
  constructor() {
    this.active = false;
    this.position = new Vector3(0, 60, 0);
    this.yaw = 0;
    this.pitch = -0.4;
    this.speed = 30;
    this.boostMultiplier = 5;
    this._target = null;
    this._lookAt = null;
    this._flight = null;
    this._forward = new Vector3();
    this._right = new Vector3();
    this._up = new Vector3(0, 1, 0);
  }

  /** Enter free-fly starting from wherever the gameplay camera currently is. */
  enable(camera) {
    this.active = true;
    this.position.copy(camera.position);
    // Recover yaw/pitch from the camera's current forward vector.
    camera.getWorldDirection(this._forward);
    this.yaw = Math.atan2(this._forward.x, this._forward.z);
    this.pitch = Math.asin(MathUtils.clamp(this._forward.y, -1, 1));
  }

  disable() { this.active = false; this._flight = null; }

  look(dx, dy, sensitivity = 0.0022) {
    this.yaw -= dx * sensitivity;
    this.pitch = MathUtils.clamp(this.pitch - dy * sensitivity, -1.5, 1.5);
  }

  /**
   * Scripted move. `duration` seconds, ease-in-out, optionally holding a look target.
   * @param {Vector3} position
   * @param {Vector3|null} lookAt
   */
  flyTo(position, lookAt = null, duration = 3) {
    this._flight = {
      from: this.position.clone(),
      to: position.clone(),
      lookAt: lookAt ? lookAt.clone() : null,
      fromYaw: this.yaw,
      fromPitch: this.pitch,
      t: 0,
      duration: Math.max(0.01, duration),
    };
    return this;
  }

  get isFlying() { return this._flight !== null; }

  /**
   * @param {number} dt
   * @param {import('three/webgpu').PerspectiveCamera} camera
   * @param {{x:number,y:number}} move
   * @param {object} flags `{ up, down, boost }`
   */
  update(dt, camera, move = { x: 0, y: 0 }, flags = {}) {
    if (this._flight) {
      const f = this._flight;
      f.t = Math.min(1, f.t + dt / f.duration);
      const e = f.t < 0.5 ? 2 * f.t * f.t : 1 - ((-2 * f.t + 2) ** 2) / 2;   // ease-in-out
      this.position.lerpVectors(f.from, f.to, e);
      if (f.lookAt) {
        this._forward.copy(f.lookAt).sub(this.position).normalize();
        this.yaw = Math.atan2(this._forward.x, this._forward.z);
        this.pitch = Math.asin(MathUtils.clamp(this._forward.y, -1, 1));
      }
      if (f.t >= 1) this._flight = null;
    } else {
      const speed = this.speed * (flags.boost ? this.boostMultiplier : 1);
      const cp = Math.cos(this.pitch);
      this._forward.set(Math.sin(this.yaw) * cp, Math.sin(this.pitch), Math.cos(this.yaw) * cp);
      this._right.crossVectors(this._forward, this._up).normalize();
      this.position.addScaledVector(this._forward, move.y * speed * dt);
      this.position.addScaledVector(this._right, move.x * speed * dt);
      if (flags.up) this.position.y += speed * dt;
      if (flags.down) this.position.y -= speed * dt;
    }

    const cp = Math.cos(this.pitch);
    this._forward.set(Math.sin(this.yaw) * cp, Math.sin(this.pitch), Math.cos(this.yaw) * cp);
    camera.position.copy(this.position);
    camera.lookAt(
      this.position.x + this._forward.x,
      this.position.y + this._forward.y,
      this.position.z + this._forward.z,
    );
  }
}
