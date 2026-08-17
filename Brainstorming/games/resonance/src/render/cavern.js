/**
 * RESONANCE - crystal cavern set dressing plus per-level walls and foam pads.
 *
 * Everything static: rock ring, ceiling stalactites, ambient wall gems, board
 * frame and lights. Never pure black anywhere (readability is measured, not
 * eyeballed): the background and fog share a dark violet, and a hemisphere
 * light keeps the rock visible from every camera angle.
 */

import * as THREE from 'three';
import { BOARD_N } from '../board.js';
import { slotToWorldX, slotToWorldZ } from '../coords.js';
import { BAND_COLORS } from './surface.js';

const MAX_WALLS = 64;
const MAX_FOAMS = 64;

const _m = new THREE.Matrix4();
const _p = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3();

export function createCavern(scene, textures) {
  const group = new THREE.Group();
  scene.add(group);
  const disposables = [];

  scene.background = new THREE.Color(0x0d0b1a);
  scene.fog = new THREE.FogExp2(0x0d0b1a, 0.016);

  // Lights: hemisphere for base readability, warm key, cool rim.
  const hemi = new THREE.HemisphereLight(0x6a72a0, 0x2c2440, 2.0);
  const key = new THREE.DirectionalLight(0xffe7c8, 1.9);
  key.position.set(14, 22, 10);
  const rim = new THREE.DirectionalLight(0x8a7cff, 0.5);
  rim.position.set(-16, 10, -14);
  group.add(hemi, key, rim);

  // Ground apron under and around the wave surface. Repeats differ per mesh,
  // so those meshes get their own clone of the rock texture.
  const rockGround = textures.rock.clone();
  rockGround.repeat.set(10, 10);
  rockGround.needsUpdate = true;
  const rockShell = textures.rock.clone();
  rockShell.repeat.set(8, 2);
  rockShell.needsUpdate = true;
  disposables.push(rockGround, rockShell);

  const apronGeom = new THREE.CylinderGeometry(34, 34, 0.5, 40);
  const apronMat = new THREE.MeshStandardMaterial({ map: rockGround, roughness: 0.95 });
  const apron = new THREE.Mesh(apronGeom, apronMat);
  apron.position.y = -0.27;
  group.add(apron);
  disposables.push(apronGeom, apronMat);

  // Cavern shell: inverted cone-ish cylinder with the rock texture.
  const shellGeom = new THREE.CylinderGeometry(26, 33, 20, 36, 1, true);
  const shellMat = new THREE.MeshStandardMaterial({
    map: rockShell, roughness: 1, side: THREE.BackSide,
  });
  const shell = new THREE.Mesh(shellGeom, shellMat);
  shell.position.y = 8.5;
  group.add(shell);
  disposables.push(shellGeom, shellMat);

  // Stalactites hanging from the dark above.
  // Open ended: the base cap of a closed cone reads as a big unlit black
  // hexagon when the camera passes under it.
  const stalGeom = new THREE.ConeGeometry(0.6, 3.4, 6, 1, true);
  const stalMat = new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 1 });
  const stals = new THREE.InstancedMesh(stalGeom, stalMat, 26);
  for (let i = 0; i < 26; i++) {
    const a = (i / 26) * Math.PI * 2;
    const r = 21 + (i % 5) * 2.6;
    _p.set(Math.cos(a) * r, 16 + (i % 3) * 1.4, Math.sin(a) * r);
    _q.setFromAxisAngle(_p2AxisZ, Math.PI);
    _s.setScalar(0.8 + (i % 4) * 0.35);
    _m.compose(_p, _q, _s);
    stals.setMatrixAt(i, _m);
  }
  group.add(stals);
  disposables.push(stalGeom, stalMat);

  // Ambient gems glinting in the rock, one colour per band.
  const gemGeom = new THREE.OctahedronGeometry(0.35, 0);
  const gemMat = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
  });
  const gems = new THREE.InstancedMesh(gemGeom, gemMat, 36);
  const gemColor = new THREE.Color();
  for (let i = 0; i < 36; i++) {
    const a = (i / 36) * Math.PI * 2 + 0.2;
    const r = 24 + (i % 4) * 2;
    _p.set(Math.cos(a) * r, 1.5 + ((i * 7) % 11), Math.sin(a) * r);
    _q.setFromAxisAngle(_p2AxisZ, i);
    _s.setScalar(0.7 + (i % 3) * 0.5);
    _m.compose(_p, _q, _s);
    gems.setMatrixAt(i, _m);
    gemColor.copy(BAND_COLORS[i % 3]).multiplyScalar(0.35);
    gems.setColorAt(i, gemColor);
  }
  group.add(gems);
  disposables.push(gemGeom, gemMat);

  // Board frame: four low rock banks around the playfield.
  const half = BOARD_N / 2;
  const bankGeom = new THREE.BoxGeometry(BOARD_N + 2.4, 1.0, 1.2);
  const bankMat = new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 0.9 });
  for (let i = 0; i < 4; i++) {
    const bank = new THREE.Mesh(bankGeom, bankMat);
    const d = half + 0.6;
    if (i === 0) bank.position.set(0, 0.3, -d);
    if (i === 1) bank.position.set(0, 0.3, d);
    if (i === 2) { bank.position.set(-d, 0.3, 0); bank.rotation.y = Math.PI / 2; }
    if (i === 3) { bank.position.set(d, 0.3, 0); bank.rotation.y = Math.PI / 2; }
    group.add(bank);
  }
  disposables.push(bankGeom, bankMat);

  // --- per-level interior walls and foam pads (instanced) -------------------
  const wallGeom = new THREE.BoxGeometry(1, 1.3, 1);
  const wallMat = new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 0.85 });
  const walls = new THREE.InstancedMesh(wallGeom, wallMat, MAX_WALLS);
  walls.count = 0;
  group.add(walls);
  disposables.push(wallGeom, wallMat);

  const foamGeom = new THREE.BoxGeometry(0.98, 0.16, 0.98);
  const foamMat = new THREE.MeshStandardMaterial({ map: textures.foam, roughness: 1 });
  const foams = new THREE.InstancedMesh(foamGeom, foamMat, MAX_FOAMS);
  foams.count = 0;
  group.add(foams);
  disposables.push(foamGeom, foamMat);

  /** Rebuild wall boxes and foam pads for a level. */
  function setLayout(level) {
    let w = 0;
    for (const r of level.walls || []) {
      for (let y = r.y; y < r.y + (r.h || 1); y++) {
        for (let x = r.x; x < r.x + (r.w || 1); x++) {
          if (w >= MAX_WALLS) break;
          _p.set(slotToWorldX(x), 0.65, slotToWorldZ(y));
          _q.identity();
          _s.setScalar(1);
          _m.compose(_p, _q, _s);
          walls.setMatrixAt(w++, _m);
        }
      }
    }
    walls.count = w;
    walls.instanceMatrix.needsUpdate = true;

    let f = 0;
    for (const r of level.foams || []) {
      for (let y = r.y; y < r.y + (r.h || 1); y++) {
        for (let x = r.x; x < r.x + (r.w || 1); x++) {
          if (f >= MAX_FOAMS) break;
          _p.set(slotToWorldX(x), 0.08, slotToWorldZ(y));
          _q.identity();
          _s.setScalar(1);
          _m.compose(_p, _q, _s);
          foams.setMatrixAt(f++, _m);
        }
      }
    }
    foams.count = f;
    foams.instanceMatrix.needsUpdate = true;
  }

  function dispose() {
    scene.remove(group);
    for (const d of disposables) d.dispose();
  }

  return { setLayout, dispose };
}

const _p2AxisZ = new THREE.Vector3(0, 0, 1);
