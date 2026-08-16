/**
 * PARADOXE - third person orbit camera.
 *
 * The yaw is not purely cosmetic: movement is camera relative, so the yaw is
 * quantised to a byte and recorded alongside the key bits. Two runs with the
 * same tape therefore steer identically even if the player nudged the mouse
 * differently while watching the replay.
 */

import * as THREE from 'three';
import { CAMERA, WORLD } from './config.js';

const TAU = Math.PI * 2;

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

export function createCameraRig(width, height) {
  const camera = new THREE.PerspectiveCamera(CAMERA.fov, width / height, CAMERA.near, CAMERA.far);

  const rig = {
    camera,
    yaw: CAMERA.yaw,
    pitch: CAMERA.pitch,
    distance: CAMERA.distance,
    focusX: 0,
    focusY: 0,
    focusZ: 0,
    shake: 0,
  };

  let started = false;

  rig.setSize = function setSize(w, h) {
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  };

  rig.reset = function reset(level, x, y, z) {
    rig.yaw = CAMERA.yaw;
    rig.pitch = CAMERA.pitch;
    rig.distance = CAMERA.distance;
    rig.focusX = x;
    rig.focusY = y + CAMERA.height;
    rig.focusZ = z;
    rig.shake = 0;
    pitchBoost = 0;
    started = false;
    void level;
  };

  /** Mouse drag orbits, wheel zooms. */
  rig.handleMouse = function handleMouse(dx, dy, wheel) {
    if (dx || dy) {
      rig.yaw -= dx * CAMERA.sensitivity;
      rig.pitch = clamp(rig.pitch + dy * CAMERA.sensitivity, CAMERA.pitchMin, CAMERA.pitchMax);
      if (rig.yaw > Math.PI) rig.yaw -= TAU;
      if (rig.yaw < -Math.PI) rig.yaw += TAU;
    }
    if (wheel) {
      const factor = wheel > 0 ? CAMERA.zoomStep : 1 / CAMERA.zoomStep;
      rig.distance = clamp(rig.distance * factor, CAMERA.distanceMin, CAMERA.distanceMax);
    }
  };

  /** Quantised yaw handed to the simulation and to the recorder. */
  rig.yawByte = function yawByte() {
    let y = rig.yaw % TAU;
    if (y < 0) y += TAU;
    return Math.round((y / TAU) * 256) & 255;
  };

  /**
   * Shortest distance to the target that keeps the camera out of the geometry.
   * Marches the ray backwards and stops before the first solid sample.
   *
   * The heights used here are the *drawn* ones, not the simulated ones: walls
   * are simulated 3.6 tall so nothing can land on them, but they are only drawn
   * 2.2 tall. Testing against 3.6 made the camera think it was buried every
   * time the player hugged a wall, and it slammed to the minimum distance.
   */
  function clearDistance(sim, tx, ty, tz, ox, oy, oz, want) {
    const steps = 16;
    for (let i = 1; i <= steps; i++) {
      const t = (i / steps) * want;
      const px = tx + ox * t;
      const py = ty + oy * t;
      const pz = tz + oz * t;
      const hv = sim.heightAt(Math.floor(px), Math.floor(pz));
      const top = hv < 0 ? -99 : hv === 3 ? WORLD.wallVisual : hv;
      if (py < top + 0.3) return Math.max(CAMERA.distanceMin, t - want / steps);
    }
    return want;
  }

  /**
   * When the straight shot is blocked, climbing is nicer than closing in: the
   * arena is small and its walls are low, so a steeper angle clears them while
   * keeping the whole puzzle in frame. The boost is smoothed so the camera
   * never snaps.
   */
  function neededPitchBoost(sim, tx, ty, tz, want) {
    for (let k = 0; k <= 6; k++) {
      const p = Math.min(CAMERA.pitchMax, rig.pitch + k * 0.11);
      const cp = Math.cos(p);
      const d = clearDistance(sim, tx, ty, tz, Math.sin(rig.yaw) * cp, Math.sin(p), Math.cos(rig.yaw) * cp, want);
      if (d >= want - 0.25) return p - rig.pitch;
      if (p >= CAMERA.pitchMax) break;
    }
    return Math.max(0, CAMERA.pitchMax - rig.pitch);
  }

  let pitchBoost = 0;

  rig.update = function update(dt, sim, tx, ty, tz) {
    const lag = 1 - Math.exp(-CAMERA.lag * dt);
    const goalY = ty + CAMERA.height;
    if (!started) {
      rig.focusX = tx;
      rig.focusY = goalY;
      rig.focusZ = tz;
      started = true;
    } else {
      rig.focusX += (tx - rig.focusX) * lag;
      rig.focusY += (goalY - rig.focusY) * lag;
      rig.focusZ += (tz - rig.focusZ) * lag;
    }

    if (sim) {
      const need = neededPitchBoost(sim, rig.focusX, rig.focusY, rig.focusZ, rig.distance);
      pitchBoost += (need - pitchBoost) * Math.min(1, dt * 5);
    } else {
      pitchBoost = 0;
    }
    const pitch = Math.min(CAMERA.pitchMax, rig.pitch + pitchBoost);
    const cp = Math.cos(pitch);
    const sp = Math.sin(pitch);
    const ox = Math.sin(rig.yaw) * cp;
    const oy = sp;
    const oz = Math.cos(rig.yaw) * cp;

    let dist = rig.distance;
    if (sim) dist = clearDistance(sim, rig.focusX, rig.focusY, rig.focusZ, ox, oy, oz, dist);

    let px = rig.focusX + ox * dist;
    let py = rig.focusY + oy * dist;
    let pz = rig.focusZ + oz * dist;
    if (py < 1.2) py = 1.2;

    if (rig.shake > 0) {
      const s = rig.shake;
      px += Math.sin(s * 71) * s * 0.22;
      py += Math.sin(s * 53) * s * 0.18;
      pz += Math.cos(s * 61) * s * 0.22;
      rig.shake = Math.max(0, rig.shake - dt * 1.8);
    }

    camera.position.set(px, py, pz);
    camera.lookAt(rig.focusX, rig.focusY, rig.focusZ);
  };

  rig.punch = function punch(amount) {
    rig.shake = Math.min(1, rig.shake + amount);
  };

  return rig;
}
