/**
 * PRISMA - orbit camera.
 *
 * No addon: a small spherical rig with critically damped follow. It exposes
 * intent methods only (orbit, zoom, frame) and never touches the DOM, so input
 * handling stays in one place.
 */

import * as THREE from 'three';

const PHI_MIN = 0.22;
const PHI_MAX = 1.32;

// Picking happens on a plane raised to roughly half a component's height:
// picking the actual floor makes tall pieces steal the cell behind them.
const PICK_HEIGHT = 0.25;

export function createOrbit(camera) {
  const target = new THREE.Vector3();
  // Three quarter view, north at the back: the ASCII of a level and what the
  // player sees then read in the same order, with no camera work at all.
  const DEFAULT_PHI = 0.72;
  const wanted = { theta: 0, phi: DEFAULT_PHI, radius: 14 };
  const now = { theta: 0, phi: DEFAULT_PHI, radius: 14 };
  let minRadius = 5;
  let maxRadius = 34;

  const raycaster = new THREE.Raycaster();
  const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -PICK_HEIGHT);
  const ndc = new THREE.Vector2();

  function frame(grid) {
    const span = Math.max(grid.w, grid.h);
    target.set(0, 0.3, 0);
    // Fit the board to the vertical field of view instead of guessing a
    // distance: a 6x6 and a 12x12 must both fill the frame the same way.
    const half = Math.tan(THREE.MathUtils.degToRad(camera.fov) * 0.5);
    wanted.radius = ((span * 0.5 + 1.15) / half) * 0.92;
    wanted.theta = 0;
    wanted.phi = DEFAULT_PHI;
    minRadius = span * 0.5 + 2;
    maxRadius = span * 2.6 + 10;
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

  function reset() {
    wanted.theta = 0;
    wanted.phi = DEFAULT_PHI;
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
    const k = 1 - Math.exp(-dt * 11);
    now.theta += (wanted.theta - now.theta) * k;
    now.phi += (wanted.phi - now.phi) * k;
    now.radius += (wanted.radius - now.radius) * k;
    apply();
  }

  /** Screen point (in normalised device coords) to a point on the pick plane. */
  function pick(ndcX, ndcY, out) {
    ndc.set(ndcX, ndcY);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.ray.intersectPlane(plane, out);
  }

  return { frame, orbit, zoom, reset, update, pick, target, state: now };
}
