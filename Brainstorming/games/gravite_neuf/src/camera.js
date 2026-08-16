/**
 * GRAVITE NEUF - orbit camera and gravity frame.
 *
 * Two rotations coexist. The orbit (yaw / pitch / distance) is the player's,
 * driven by the mouse. The gravity frame is a quaternion applied to the level
 * group so that the current gravity always points at the bottom of the screen;
 * a tilt slerps it over TILT_TIME, which is what makes the puzzle readable.
 *
 * The same frame is what turns a key press into a world axis: the arrows are
 * always relative to what the player sees, never to the level's own axes.
 */

import * as THREE from 'three';
import { DIRS } from './world.js';

const TILT_TIME = 0.4;
const PITCH_MIN = -1.25;
const PITCH_MAX = 1.25;

const DOWN = new THREE.Vector3(0, -1, 0);
const UP = new THREE.Vector3(0, 1, 0);

// Scratch vectors. Each name is used by exactly one function so two calls can
// never stomp on each other.
const camPos = new THREE.Vector3();
const fwdScratch = new THREE.Vector3();
const rightScratch = new THREE.Vector3();
const askScratch = new THREE.Vector3();
const tiltScratch = new THREE.Vector3();
const deltaQuat = new THREE.Quaternion();
const invQuat = new THREE.Quaternion();

function easeInOut(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export function createCameraRig(aspect) {
  const camera = new THREE.PerspectiveCamera(46, aspect, 0.5, 900);

  let yaw = 0.78;
  let pitch = 0.58;
  let dist = 20;
  let distTarget = 20;
  let distMin = 6;
  let distMax = 60;

  const worldQuat = new THREE.Quaternion();
  const fromQuat = new THREE.Quaternion();
  const toQuat = new THREE.Quaternion();
  let blend = 1;

  function placeCamera() {
    const cp = Math.cos(pitch);
    camPos.set(Math.sin(yaw) * cp, Math.sin(pitch), Math.cos(yaw) * cp).multiplyScalar(dist);
    camera.position.copy(camPos);
    camera.up.set(0, 1, 0);
    camera.lookAt(0, 0, 0);
  }

  /** Horizontal screen-forward, i.e. "into the screen" projected on the ground. */
  function horizontalForward(out) {
    out.set(-camera.position.x, 0, -camera.position.z);
    if (out.lengthSq() < 1e-6) out.set(0, 0, -1);
    return out.normalize();
  }

  function snapToAxis(v) {
    const ax = Math.abs(v.x);
    const ay = Math.abs(v.y);
    const az = Math.abs(v.z);
    if (ax >= ay && ax >= az) return v.x > 0 ? 0 : 1;
    if (ay >= ax && ay >= az) return v.y > 0 ? 2 : 3;
    return v.z > 0 ? 4 : 5;
  }

  const rig = {
    camera,
    worldQuat,
    tilting: false,
  };

  rig.frame = function frame(radius) {
    distTarget = Math.max(7, radius * 2.55);
    dist = distTarget;
    distMin = Math.max(4, radius * 1.25);
    distMax = radius * 5.5;
    placeCamera();
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

  rig.resetOrbit = function resetOrbit() {
    yaw = 0.78;
    pitch = 0.58;
  };

  /**
   * Turns a screen relative request into a level space gravity direction.
   * `action` is one of forward, back, left, right, up, down.
   */
  rig.resolveDirection = function resolveDirection(action) {
    if (action === 'up') askScratch.copy(UP);
    else if (action === 'down') askScratch.copy(DOWN);
    else {
      horizontalForward(fwdScratch);
      rightScratch.crossVectors(fwdScratch, UP).normalize();
      if (action === 'forward') askScratch.copy(fwdScratch);
      else if (action === 'back') askScratch.copy(fwdScratch).negate();
      else if (action === 'right') askScratch.copy(rightScratch);
      else askScratch.copy(rightScratch).negate();
    }
    invQuat.copy(toQuat).invert();
    askScratch.applyQuaternion(invQuat);
    return snapToAxis(askScratch);
  };

  /** Starts the roll that puts `dirIndex` at the bottom of the screen. */
  rig.setGravity = function setGravity(dirIndex, immediate) {
    const d = DIRS[dirIndex];
    tiltScratch.set(d[0], d[1], d[2]).applyQuaternion(toQuat);
    const dot = tiltScratch.dot(DOWN);
    if (dot > 0.9999) {
      if (immediate) {
        worldQuat.copy(toQuat);
        blend = 1;
      }
      return;
    }
    if (dot < -0.9999) {
      // Exact half turn: setFromUnitVectors would pick an arbitrary axis, so
      // roll around the screen right axis instead and the world tumbles forward.
      horizontalForward(fwdScratch);
      rightScratch.crossVectors(fwdScratch, UP).normalize();
      deltaQuat.setFromAxisAngle(rightScratch, Math.PI);
    } else {
      deltaQuat.setFromUnitVectors(tiltScratch, DOWN);
    }
    fromQuat.copy(worldQuat);
    toQuat.premultiply(deltaQuat);
    blend = immediate ? 1 : 0;
    if (immediate) worldQuat.copy(toQuat);
  };

  rig.reset = function reset() {
    worldQuat.identity();
    fromQuat.identity();
    toQuat.identity();
    blend = 1;
  };

  rig.update = function update(dt) {
    if (blend < 1) {
      blend = Math.min(1, blend + dt / TILT_TIME);
      worldQuat.slerpQuaternions(fromQuat, toQuat, easeInOut(blend));
    }
    rig.tilting = blend < 1;
    dist += (distTarget - dist) * Math.min(1, dt * 9);
    placeCamera();
  };

  rig.resize = function resize(nextAspect) {
    camera.aspect = nextAspect;
    camera.updateProjectionMatrix();
  };

  placeCamera();
  return rig;
}
