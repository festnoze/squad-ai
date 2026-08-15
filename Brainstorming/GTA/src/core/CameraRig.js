/**
 * Third-person camera.
 *
 * An orbit boom around a follow target, with:
 *  - mouse/stick yaw+pitch,
 *  - a spring on the pivot so the camera lags the player slightly,
 *  - a physics raycast down the boom so the camera pulls in rather than clipping walls,
 *  - speed-driven FOV and boom stretch for vehicles.
 */

import { PerspectiveCamera, Vector3, MathUtils } from 'three/webgpu';
import { GROUP, groups } from '../physics/Physics.js';

const MODE = {
  onFoot: { distance: 4.6, height: 1.55, pitch: -0.12, fov: 62, shoulder: 0.55, lag: 14 },
  aim: { distance: 2.1, height: 1.6, pitch: -0.05, fov: 48, shoulder: 0.85, lag: 26 },
  vehicle: { distance: 8.2, height: 2.5, pitch: -0.14, fov: 66, shoulder: 0, lag: 7 },
  boat: { distance: 11.5, height: 4.2, pitch: -0.18, fov: 68, shoulder: 0, lag: 5 },
  cinematic: { distance: 7.0, height: 2.0, pitch: -0.08, fov: 40, shoulder: 0, lag: 3 },
};

export class CameraRig {
  /** @param {import('../physics/Physics.js').Physics} physics */
  constructor(physics, aspect = 16 / 9) {
    this.physics = physics;
    // Far plane must clear the skydome (9000). Near is kept off 0.1 to preserve depth
    // precision across that range.
    this.camera = new PerspectiveCamera(62, aspect, 0.25, 12000);
    this.camera.position.set(0, 5, 10);

    this.yaw = 0;
    this.pitch = -0.12;
    this.mode = 'onFoot';
    this.distanceScale = 1;
    this.sensitivity = 0.0022;
    this.invertY = false;

    this.pivot = new Vector3();
    this._targetPivot = new Vector3();
    this._desired = new Vector3();
    this._dir = new Vector3();
    this._up = new Vector3(0, 1, 0);
    this._right = new Vector3();
    this._currentDistance = MODE.onFoot.distance;
    this._fov = 62;
    this._shakeAmount = 0;
    this._shakeTime = 0;
    this._rayFilter = groups(
      GROUP.BULLET, GROUP.TERRAIN | GROUP.STATIC | GROUP.BUILDING | GROUP.PROP,
    );
  }

  setMode(mode) { if (MODE[mode]) this.mode = mode; }

  /** Apply pointer/stick deltas. */
  look(dx, dy) {
    this.yaw -= dx * this.sensitivity;
    this.pitch -= dy * this.sensitivity * (this.invertY ? -1 : 1);
    this.pitch = MathUtils.clamp(this.pitch, -1.15, 0.95);
    while (this.yaw > Math.PI) this.yaw -= Math.PI * 2;
    while (this.yaw < -Math.PI) this.yaw += Math.PI * 2;
  }

  /** Zoom the boom with the mouse wheel. */
  zoom(steps) {
    this.distanceScale = MathUtils.clamp(this.distanceScale + steps * 0.12, 0.55, 2.2);
  }

  shake(amount, duration = 0.35) {
    this._shakeAmount = Math.max(this._shakeAmount, amount);
    this._shakeTime = Math.max(this._shakeTime, duration);
  }

  /**
   * @param {number} dt
   * @param {Vector3} followPoint world point to orbit (usually the target's chest)
   * @param {number} [speed] target speed in m/s, drives FOV and boom stretch
   */
  update(dt, followPoint, speed = 0) {
    const cfg = MODE[this.mode] ?? MODE.onFoot;

    this._targetPivot.set(followPoint.x, followPoint.y + cfg.height, followPoint.z);
    // Spring the pivot so quick player movement reads as camera lag, not a rigid weld.
    const k = 1 - Math.exp(-cfg.lag * dt);
    this.pivot.lerp(this._targetPivot, k);

    // Boom direction from yaw/pitch.
    const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    this._dir.set(Math.sin(this.yaw) * cp, -sp, Math.cos(this.yaw) * cp).normalize();
    this._right.crossVectors(this._up, this._dir).normalize();

    // Faster targets get a longer boom and wider FOV: cheap but very effective speed cue.
    const speedT = MathUtils.clamp(speed / 42, 0, 1);
    const wanted = cfg.distance * this.distanceScale * (1 + speedT * 0.28);
    const fovWanted = cfg.fov + speedT * 14;
    this._fov = MathUtils.lerp(this._fov, fovWanted, 1 - Math.exp(-4 * dt));

    // Occlusion: cast from the pivot along the boom and stop short of geometry.
    let allowed = wanted;
    const hit = this.physics.raycast(this.pivot, this._dir, wanted + 0.6, this._rayFilter);
    if (hit) allowed = Math.max(0.7, hit.distance - 0.45);
    // Pull in fast, ease back out slowly, so corners do not snap the view.
    const rate = allowed < this._currentDistance ? 26 : 5;
    this._currentDistance = MathUtils.lerp(this._currentDistance, allowed, 1 - Math.exp(-rate * dt));

    this._desired.copy(this.pivot)
      .addScaledVector(this._dir, this._currentDistance)
      .addScaledVector(this._right, cfg.shoulder * this.distanceScale);

    if (this._shakeTime > 0) {
      this._shakeTime -= dt;
      const a = this._shakeAmount * (this._shakeTime > 0 ? this._shakeTime : 0);
      this._desired.x += (Math.random() - 0.5) * a;
      this._desired.y += (Math.random() - 0.5) * a;
      this._desired.z += (Math.random() - 0.5) * a;
      if (this._shakeTime <= 0) this._shakeAmount = 0;
    }

    this.camera.position.copy(this._desired);
    this.camera.lookAt(this.pivot);
    if (Math.abs(this.camera.fov - this._fov) > 0.01) {
      this.camera.fov = this._fov;
      this.camera.updateProjectionMatrix();
    }
  }

  resize(aspect) {
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  }

  /** Forward vector on the horizontal plane - the movement basis for the player. */
  get flatYaw() { return this.yaw; }
}
