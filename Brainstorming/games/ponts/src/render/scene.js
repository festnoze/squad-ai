/**
 * PONTS DE FORTUNE - renderer, lighting and the orbit rig.
 *
 * The rig is a damped orbit around a target point. Construction sits at yaw 0,
 * which is exactly side on: the edition plane (z = 0) then projects without
 * foreshortening, so the drawn plan is as precise as a 2D editor while the
 * scene itself stays fully three dimensional.
 */

import * as THREE from 'three';
import { CAMERA, PALETTE, GRID, DECK_Y } from '../config.js';

const rayScratch = new THREE.Raycaster();
const ndc = new THREE.Vector2();
const planeZ = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
const offset = new THREE.Vector3();
const right = new THREE.Vector3();
const upv = new THREE.Vector3();

function damp(current, goal, lambda, dt) {
  return goal + (current - goal) * Math.exp(-lambda * dt);
}

export function createStage(canvas, textures) {
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, powerPreference: 'high-performance', stencil: false,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.background = textures.sky;
  scene.fog = new THREE.Fog(PALETTE.fog, 130, 640);

  // Without an environment, a metallic material has nothing to reflect and
  // renders flat black. Bake one from the same sky the background uses.
  const pmrem = new THREE.PMREMGenerator(renderer);
  pmrem.compileEquirectangularShader();
  const envTarget = pmrem.fromEquirectangular(textures.sky);
  scene.environment = envTarget.texture;
  scene.environmentIntensity = 0.85;
  pmrem.dispose();

  const camera = new THREE.PerspectiveCamera(CAMERA.fov, 1, CAMERA.near, CAMERA.far);
  camera.position.set(0, 6, 90);

  const hemi = new THREE.HemisphereLight(0xbcd4e8, 0x40382c, 1.15);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xfff0d2, 2.05);
  sun.position.set(-70, 90, 62);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 420;
  sun.shadow.bias = -0.0009;
  sun.shadow.normalBias = 0.35;
  scene.add(sun);
  scene.add(sun.target);

  const fill = new THREE.DirectionalLight(0x9fc0dd, 0.42);
  fill.position.set(64, 30, -80);
  scene.add(fill);

  const rig = {
    target: new THREE.Vector3(0, 0, 0),
    goal: new THREE.Vector3(0, 0, 0),
    dist: 90, distGoal: 90,
    yaw: 0, yawGoal: 0,
    pitch: CAMERA.buildPitch, pitchGoal: CAMERA.buildPitch,
    snap: false,
  };

  /**
   * The shadow map is clamped at its border, so anything the frustum misses
   * picks up the edge texel and paints a hard dark rectangle on the cliff.
   * Keep it generously wider than the span.
   */
  function setShadowExtent(halfSpan) {
    const c = sun.shadow.camera;
    const s = Math.max(70, halfSpan);
    c.left = -s; c.right = s; c.top = s; c.bottom = -s;
    c.updateProjectionMatrix();
  }

  /** Distance that fits a box of the given size in the current viewport. */
  function fitDistance(width, height) {
    const vFov = (CAMERA.fov * Math.PI) / 180;
    const aspect = Math.max(0.4, camera.aspect);
    const dv = height / (2 * Math.tan(vFov / 2));
    const dh = width / (2 * Math.tan(vFov / 2) * aspect);
    return Math.max(dv, dh) * 1.04;
  }

  function frameLevel(level, immediate) {
    const cx = 0;
    // Bias the centre towards the deck: the roadway is what the eye needs.
    const cy = DECK_Y + ((level.rowMax + level.rowMin) * 0.5) * GRID * 0.35;
    const w = (level.right - level.left + 4) * GRID;
    const h = (level.rowMax - level.rowMin + 1.5) * GRID;
    rig.goal.set(cx, cy, 0);
    rig.distGoal = Math.min(CAMERA.maxDist, Math.max(CAMERA.minDist, fitDistance(w, h)));
    rig.yawGoal = CAMERA.buildYaw;
    rig.pitchGoal = CAMERA.buildPitch;
    setShadowExtent(w * 0.95);
    sun.target.position.set(cx, cy, 0);
    sun.position.set(cx - 70, cy + 92, 66);
    if (immediate) {
      rig.target.copy(rig.goal);
      rig.dist = rig.distGoal;
      rig.yaw = rig.yawGoal;
      rig.pitch = rig.pitchGoal;
      applyCamera();
    }
  }

  function orbit(dx, dy) {
    rig.yawGoal = Math.max(-1.35, Math.min(1.35, rig.yawGoal + dx));
    rig.pitchGoal = Math.max(CAMERA.minPitch, Math.min(CAMERA.maxPitch, rig.pitchGoal + dy));
  }

  function zoom(steps) {
    rig.distGoal = Math.max(CAMERA.minDist, Math.min(CAMERA.maxDist, rig.distGoal * Math.pow(1.13, steps)));
  }

  function pan(dxWorld, dyWorld) {
    right.set(Math.cos(rig.yaw), 0, -Math.sin(rig.yaw));
    upv.set(0, 1, 0);
    rig.goal.addScaledVector(right, dxWorld);
    rig.goal.addScaledVector(upv, dyWorld);
    rig.goal.y = Math.max(-70, Math.min(70, rig.goal.y));
    rig.goal.x = Math.max(-260, Math.min(260, rig.goal.x));
  }

  function lookAtPoint(x, y, z, dist, yaw, pitch) {
    rig.goal.set(x, y, z || 0);
    if (dist !== undefined) rig.distGoal = Math.max(CAMERA.minDist, Math.min(CAMERA.maxDist, dist));
    if (yaw !== undefined) rig.yawGoal = yaw;
    if (pitch !== undefined) rig.pitchGoal = pitch;
  }

  function applyCamera() {
    offset.set(
      Math.sin(rig.yaw) * Math.cos(rig.pitch),
      Math.sin(rig.pitch),
      Math.cos(rig.yaw) * Math.cos(rig.pitch),
    ).multiplyScalar(rig.dist);
    camera.position.copy(rig.target).add(offset);
    camera.lookAt(rig.target);
  }

  function update(dt) {
    const k = CAMERA.lag;
    rig.target.x = damp(rig.target.x, rig.goal.x, k, dt);
    rig.target.y = damp(rig.target.y, rig.goal.y, k, dt);
    rig.target.z = damp(rig.target.z, rig.goal.z, k, dt);
    rig.dist = damp(rig.dist, rig.distGoal, k, dt);
    rig.yaw = damp(rig.yaw, rig.yawGoal, k, dt);
    rig.pitch = damp(rig.pitch, rig.pitchGoal, k, dt);
    applyCamera();
    sun.target.position.set(rig.target.x, rig.target.y, 0);
    sun.position.set(rig.target.x - 70, rig.target.y + 92, 66);
    sun.target.updateMatrixWorld();
  }

  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  /** Where a screen point lands on the edition plane z = 0. */
  function planePoint(clientX, clientY, out) {
    const rect = canvas.getBoundingClientRect();
    ndc.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    ndc.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    rayScratch.setFromCamera(ndc, camera);
    return rayScratch.ray.intersectPlane(planeZ, out);
  }

  function render() {
    renderer.render(scene, camera);
  }

  function dispose() {
    envTarget.dispose();
    renderer.dispose();
  }

  resize();

  return {
    renderer, scene, camera, sun, hemi, rig,
    frameLevel, orbit, zoom, pan, lookAtPoint, update, resize, planePoint, render, dispose,
    fitDistance,
  };
}
