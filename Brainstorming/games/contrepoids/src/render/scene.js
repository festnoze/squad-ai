/**
 * CONTREPOIDS - renderer bootstrap, lights and shaft walls.
 *
 * The mine shaft is lit like a real pit: no daylight, a couple of warm torch
 * point lights and a cool ambient fill so shadow sides never go pure black.
 * The background is a dark tinted fog colour, never 0x000000, so a stalled
 * frame or an empty clear never reads as a broken canvas.
 */

import * as THREE from 'three';
import { SPACING } from './layout.js';

const FOG_COLOR = 0x0c1016;

export function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  return renderer;
}

export function createScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(FOG_COLOR);
  scene.fog = new THREE.FogExp2(FOG_COLOR, 0.028);

  const ambient = new THREE.AmbientLight(0x35404f, 0.65);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0x3a4a58, 0x120e0a, 0.5);
  scene.add(hemi);

  // A soft, distant key light so vertical faces read without a harsh sun.
  const key = new THREE.DirectionalLight(0xffe2ba, 0.55);
  key.position.set(8, 20, 10);
  key.castShadow = false;
  scene.add(key);

  const torches = [];
  for (let i = 0; i < 4; i++) {
    const torch = new THREE.PointLight(0xffab5c, 6.5, 16, 2);
    torch.position.set(0, 0, 0);
    scene.add(torch);
    torches.push(torch);
  }

  const shaftGroup = new THREE.Group();
  scene.add(shaftGroup);

  return { scene, ambient, hemi, key, torches, shaftGroup };
}

/** Builds a loose ring of rock-wall panels around a level's bounding box. */
export function buildShaftWalls(shaftGroup, textures, bounds) {
  for (let i = shaftGroup.children.length - 1; i >= 0; i--) {
    const child = shaftGroup.children[i];
    shaftGroup.remove(child);
    if (child.geometry) child.geometry.dispose();
    if (child.material) child.material.dispose();
  }

  const cx = (bounds.minX + bounds.maxX) / 2;
  const cz = (bounds.minZ + bounds.maxZ) / 2;
  const halfW = Math.max(bounds.maxX - bounds.minX, SPACING * 2) / 2 + SPACING * 2.2;
  const halfD = Math.max(bounds.maxZ - bounds.minZ, SPACING * 2) / 2 + SPACING * 2.2;
  const wallHeight = Math.max(bounds.maxY - bounds.minY, 4) + 14;
  const wallY = (bounds.maxY + bounds.minY) / 2;

  const material = new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 0.95, metalness: 0.02 });
  const geomNS = new THREE.PlaneGeometry(halfW * 2 + 4, wallHeight);
  const geomEW = new THREE.PlaneGeometry(halfD * 2 + 4, wallHeight);

  const north = new THREE.Mesh(geomNS, material);
  north.position.set(cx, wallY, cz - halfD);
  north.receiveShadow = true;
  shaftGroup.add(north);

  const south = new THREE.Mesh(geomNS.clone(), material);
  south.position.set(cx, wallY, cz + halfD);
  south.rotation.y = Math.PI;
  south.receiveShadow = true;
  shaftGroup.add(south);

  const west = new THREE.Mesh(geomEW, material);
  west.position.set(cx - halfW, wallY, cz);
  west.rotation.y = Math.PI / 2;
  west.receiveShadow = true;
  shaftGroup.add(west);

  const east = new THREE.Mesh(geomEW.clone(), material);
  east.position.set(cx + halfW, wallY, cz);
  east.rotation.y = -Math.PI / 2;
  east.receiveShadow = true;
  shaftGroup.add(east);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(halfW * 2 + 4, halfD * 2 + 4),
    new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 1, metalness: 0 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(cx, bounds.minY - 3.2, cz);
  floor.receiveShadow = true;
  shaftGroup.add(floor);

  return { cx, cz, halfW, halfD, wallY, wallHeight };
}
