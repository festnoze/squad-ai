/**
 * AIGUILLAGE - orbital camera rig.
 *
 * Pure spherical orbit around a fixed target (the yard's centre): yaw,
 * pitch, distance. No gravity trickery needed here, unlike gravite_neuf,
 * but the same shape of rig (mouse drag + wheel zoom + keyboard orbit).
 */

import * as THREE from 'three';

const PITCH_MIN = 0.18;
const PITCH_MAX = 1.45;

const camPos = new THREE.Vector3();

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

export function createCameraRig(aspect) {
  const camera = new THREE.PerspectiveCamera(48, aspect, 0.5, 3000);
  const target = new THREE.Vector3();

  let yaw = 0.65;
  let pitch = 0.62;
  let dist = 80;
  let distTarget = 80;
  let distMin = 24;
  let distMax = 400;

  function place() {
    const cp = Math.cos(pitch);
    camPos
      .set(Math.sin(yaw) * cp, Math.sin(pitch), Math.cos(yaw) * cp)
      .multiplyScalar(dist)
      .add(target);
    camera.position.copy(camPos);
    camera.up.set(0, 1, 0);
    camera.lookAt(target);
  }

  const rig = { camera, target };

  /** Frames the camera on a bounding box {minX,maxX,minZ,maxZ} in world space. */
  rig.frame = function frame(bounds) {
    target.set((bounds.minX + bounds.maxX) / 2, 0, (bounds.minZ + bounds.maxZ) / 2);
    const spanX = bounds.maxX - bounds.minX;
    const spanZ = bounds.maxZ - bounds.minZ;
    const span = Math.max(spanX, spanZ, 90);
    dist = distTarget = span * 0.95;
    distMin = Math.max(26, span * 0.24);
    distMax = span * 2.6;
    yaw = 0.65;
    pitch = 0.62;
    place();
  };

  rig.orbit = function orbit(dx, dy) {
    yaw -= dx;
    pitch = clamp(pitch + dy, PITCH_MIN, PITCH_MAX);
  };

  rig.orbitRate = function orbitRate(yawRate, pitchRate, dt) {
    yaw -= yawRate * dt;
    pitch = clamp(pitch + pitchRate * dt, PITCH_MIN, PITCH_MAX);
  };

  rig.zoom = function zoom(deltaPixels) {
    distTarget *= Math.exp(deltaPixels * 0.0018);
    distTarget = clamp(distTarget, distMin, distMax);
  };

  rig.update = function update(dt) {
    dist += (distTarget - dist) * Math.min(1, dt * 8);
    place();
  };

  rig.resize = function resize(nextAspect) {
    camera.aspect = nextAspect;
    camera.updateProjectionMatrix();
  };

  place();
  return rig;
}
