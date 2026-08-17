/**
 * MAREE - orbit camera rig.
 *
 * A plain target-orbit camera: yaw, pitch, distance around a fixed pivot (the
 * centre of the current level's footprint). No gravity frame to fight, unlike
 * the sibling voxel puzzle this one borrows its grid model from.
 */

import * as THREE from 'three';

const PITCH_MIN = 0.18;
const PITCH_MAX = 1.4;

const camPos = new THREE.Vector3();

export function createCameraRig(aspect) {
  const camera = new THREE.PerspectiveCamera(42, aspect, 0.3, 500);

  let yaw = 0.86;
  let pitch = 0.78;
  let dist = 18;
  let distTarget = 18;
  let distMin = 5;
  let distMax = 70;
  const pivot = new THREE.Vector3();
  const pivotTarget = new THREE.Vector3();

  function place() {
    const cp = Math.cos(pitch);
    camPos.set(Math.sin(yaw) * cp, Math.sin(pitch), Math.cos(yaw) * cp).multiplyScalar(dist).add(pivot);
    camera.position.copy(camPos);
    camera.up.set(0, 1, 0);
    camera.lookAt(pivot);
  }

  const rig = { camera };

  /**
   * Frames a level footprint of the given world-space centre and radius. The
   * multiplier is 1/sin(halfFov) so a bounding sphere of that radius exactly
   * fits the vertical field of view, with a margin; a smaller factor (an
   * earlier bug here) put the camera closer than the structure's own extent
   * and clipped straight into it instead of framing the level.
   */
  rig.frame = function frame(center, radius) {
    pivotTarget.copy(center);
    pivot.copy(center);
    const halfFov = THREE.MathUtils.degToRad(camera.fov) / 2;
    const fit = 1 / Math.sin(halfFov);
    distTarget = Math.max(6, radius * fit * 1.15);
    dist = distTarget;
    distMin = Math.max(3, radius * fit * 0.5);
    distMax = radius * fit * 3 + 10;
    place();
  };

  rig.orbit = function orbit(dx, dy) {
    yaw -= dx;
    pitch += dy;
    if (pitch < PITCH_MIN) pitch = PITCH_MIN;
    if (pitch > PITCH_MAX) pitch = PITCH_MAX;
  };

  rig.zoom = function zoom(delta) {
    distTarget *= Math.exp(delta * 0.0016);
    if (distTarget < distMin) distTarget = distMin;
    if (distTarget > distMax) distTarget = distMax;
  };

  rig.update = function update(dt) {
    dist += (distTarget - dist) * Math.min(1, dt * 8);
    pivot.lerp(pivotTarget, Math.min(1, dt * 6));
    place();
  };

  rig.resize = function resize(nextAspect) {
    camera.aspect = nextAspect;
    camera.updateProjectionMatrix();
  };

  place();
  return rig;
}
