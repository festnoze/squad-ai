/**
 * RESONANCE - orbit camera rig.
 *
 * No addon: spherical coordinates around the board centre with exponential
 * smoothing. Exposes intent methods only (orbit, zoom, update, pick); all
 * event handling lives in input.js.
 */

import * as THREE from 'three';
import { BOARD_N } from './board.js';

const PHI_MIN = 0.28;
const PHI_MAX = 1.25;
// Picking happens slightly above the resting surface so raised waves do not
// steal the ray; the plane is then quantised to slots by the caller.
const PICK_HEIGHT = 0.05;

export function createOrbit(camera) {
  const target = new THREE.Vector3(0, 0.2, 0);
  const DEFAULT_PHI = 0.78; // three quarter view: the whole grid reads at once
  const wanted = { theta: 0, phi: DEFAULT_PHI, radius: 24 };
  const now = { theta: 0, phi: DEFAULT_PHI, radius: 24 };
  let minRadius = 8;
  let maxRadius = 52;

  const raycaster = new THREE.Raycaster();
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -PICK_HEIGHT);
  const ndc = new THREE.Vector2();

  function frame() {
    const span = BOARD_N;
    const half = Math.tan(THREE.MathUtils.degToRad(camera.fov) * 0.5);
    wanted.radius = ((span * 0.5 + 2.5) / half) * 0.95;
    wanted.theta = 0;
    wanted.phi = DEFAULT_PHI;
    minRadius = span * 0.45;
    maxRadius = span * 2.2;
    now.radius = wanted.radius;
    now.theta = wanted.theta;
    now.phi = wanted.phi;
    apply();
  }

  function orbit(dx, dy) {
    wanted.theta -= dx * 0.0055;
    wanted.phi = THREE.MathUtils.clamp(wanted.phi - dy * 0.0045, PHI_MIN, PHI_MAX);
  }

  function zoom(delta) {
    wanted.radius = THREE.MathUtils.clamp(wanted.radius * (1 + delta * 0.0016), minRadius, maxRadius);
  }

  function apply() {
    const sp = Math.sin(now.phi);
    camera.position.set(
      target.x + now.radius * sp * Math.sin(now.theta),
      target.y + now.radius * Math.cos(now.phi),
      target.z + now.radius * sp * Math.cos(now.theta),
    );
    camera.lookAt(target);
  }

  function update(dt) {
    const k = 1 - Math.exp(-dt * 10);
    now.theta += (wanted.theta - now.theta) * k;
    now.phi += (wanted.phi - now.phi) * k;
    now.radius += (wanted.radius - now.radius) * k;
    apply();
  }

  /** NDC point to a point on the pick plane; returns null when parallel. */
  function pick(ndcX, ndcY, out) {
    ndc.set(ndcX, ndcY);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.ray.intersectPlane(plane, out);
  }

  return { frame, orbit, zoom, update, pick, target, state: now };
}
