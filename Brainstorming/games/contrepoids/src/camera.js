/**
 * CONTREPOIDS - orbit camera rig.
 *
 * The shaft is always vertical (world Y is always "up"), so unlike a gravity
 * puzzle this rig never reorients the world: it only orbits a target point
 * and dollies in and out. Mouse drag, mouse wheel, trackpad two-finger swipe
 * and keyboard (I/J/K/L) all drive the same yaw/pitch/distance state.
 */

import * as THREE from 'three';

const PITCH_MIN = -1.15;
const PITCH_MAX = 1.2;

const camPos = new THREE.Vector3();

export function createCameraRig(aspect) {
  const camera = new THREE.PerspectiveCamera(48, aspect, 0.4, 400);

  let yaw = 0.6;
  let pitch = 0.42;
  let dist = 14;
  let distTarget = 14;
  let distMin = 4;
  let distMax = 60;
  const target = new THREE.Vector3(0, 0, 0);
  const targetSmoothed = new THREE.Vector3(0, 0, 0);

  function placeCamera() {
    const cp = Math.cos(pitch);
    camPos.set(Math.sin(yaw) * cp, Math.sin(pitch), Math.cos(yaw) * cp).multiplyScalar(dist);
    camPos.add(targetSmoothed);
    camera.position.copy(camPos);
    camera.up.set(0, 1, 0);
    camera.lookAt(targetSmoothed);
  }

  const rig = { camera };

  /** Sets the orbit focus point and distance bounds for the loaded level. */
  rig.frame = function frame(center, radius) {
    target.copy(center);
    targetSmoothed.copy(center);
    distTarget = Math.max(6, radius * 1.9);
    dist = distTarget;
    distMin = Math.max(3, radius * 0.6);
    distMax = radius * 5 + 20;
    placeCamera();
  };

  /** Moves the orbit focus smoothly, e.g. following the player up/down the shaft. */
  rig.setFocus = function setFocus(center) {
    target.copy(center);
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

  /** Converts a screen-relative request (forward/back/left/right) into a grid
   * direction index matching shaft.js's DIRS order (east, west, south, north). */
  rig.resolveDirection = function resolveDirection(action) {
    // Horizontal forward = "into the screen" projected on the ground plane.
    const fx = -Math.sin(yaw);
    const fz = -Math.cos(yaw);
    let vx = 0;
    let vz = 0;
    if (action === 'forward') {
      vx = fx; vz = fz;
    } else if (action === 'back') {
      vx = -fx; vz = -fz;
    } else if (action === 'left') {
      vx = -fz; vz = fx;
    } else {
      vx = fz; vz = -fx;
    }
    if (Math.abs(vx) >= Math.abs(vz)) return vx > 0 ? 0 : 1; // east / west
    return vz > 0 ? 2 : 3; // south / north
  };

  rig.update = function update(dt) {
    dist += (distTarget - dist) * Math.min(1, dt * 8);
    targetSmoothed.lerp(target, Math.min(1, dt * 6));
    placeCamera();
  };

  rig.resize = function resize(nextAspect) {
    camera.aspect = nextAspect;
    camera.updateProjectionMatrix();
  };

  placeCamera();
  return rig;
}
