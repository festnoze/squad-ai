/**
 * MAREE - the explorer's body: a small low-poly figure built from primitives
 * and animated entirely by code (a walk cycle, a swim stroke, an idle sway).
 * No skeleton, no rig: every limb is its own mesh rotated by hand each frame.
 */

import * as THREE from 'three';
import { CELL } from '../config.js';
import { colIndex, woodAt } from '../world.js';

const outPos = new THREE.Vector3();

function easeInOut(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/** Live standing height at a column: wood always tracks the smoothed water. */
function displayHeight(state, x, z, fallbackH) {
  const w = woodAt(state, x, z);
  if (!w) return fallbackH;
  const basinIdx = state.basinOf[colIndex(state, x, z)];
  const basin = state.basins[basinIdx];
  return Math.max(w.homeFloor, basin.visual);
}

function worldXZ(state, x, z) {
  return {
    x: (x - (state.w - 1) / 2) * CELL,
    z: (z - (state.d - 1) / 2) * CELL,
  };
}

export function createExplorerObject(textures) {
  const root = new THREE.Group();

  const suitMat = new THREE.MeshStandardMaterial({ map: textures.suit, roughness: 0.7 });
  const skinMat = new THREE.MeshStandardMaterial({ color: 0xe0b088, roughness: 0.6 });

  const body = new THREE.Group();
  root.add(body);

  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.32 * CELL, 0.42 * CELL, 0.2 * CELL), suitMat);
  torso.position.y = 0.5 * CELL;
  torso.castShadow = true;
  body.add(torso);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.13 * CELL, 10, 8), skinMat);
  head.position.y = 0.82 * CELL;
  head.castShadow = true;
  body.add(head);

  function limb(w, h, d, mat, originY) {
    const geom = new THREE.BoxGeometry(w, h, d);
    geom.translate(0, -h / 2, 0);
    const pivot = new THREE.Group();
    const mesh = new THREE.Mesh(geom, mat);
    mesh.castShadow = true;
    pivot.add(mesh);
    pivot.position.y = originY;
    return pivot;
  }

  const legL = limb(0.11 * CELL, 0.42 * CELL, 0.13 * CELL, suitMat, 0.42 * CELL);
  const legR = limb(0.11 * CELL, 0.42 * CELL, 0.13 * CELL, suitMat, 0.42 * CELL);
  legL.position.x = -0.08 * CELL;
  legR.position.x = 0.08 * CELL;
  body.add(legL, legR);

  const armL = limb(0.09 * CELL, 0.36 * CELL, 0.1 * CELL, skinMat, 0.68 * CELL);
  const armR = limb(0.09 * CELL, 0.36 * CELL, 0.1 * CELL, skinMat, 0.68 * CELL);
  armL.position.x = -0.22 * CELL;
  armR.position.x = 0.22 * CELL;
  body.add(armL, armR);

  let animPhase = 0;

  function update(state, dt, elapsed) {
    const e = state.explorer;
    const fromH = displayHeight(state, e.fromX, e.fromZ, e.fromH);
    const toH = displayHeight(state, e.x, e.z, e.h);
    const from = worldXZ(state, e.fromX, e.fromZ);
    const to = worldXZ(state, e.x, e.z);
    const t = e.stepT >= 1 ? 1 : easeInOut(e.stepT);
    outPos.set(from.x + (to.x - from.x) * t, 0, from.z + (to.z - from.z) * t);
    const hLerp = fromH + (toH - fromH) * t;

    const moving = e.stepT < 1;
    if (moving) animPhase += dt * (e.swimming ? 5.2 : 7.5);
    else animPhase *= 0.9;

    if (e.swimming && moving) {
      // Swimming: lean forward, ride low in the water, stroke the arms.
      root.rotation.x = -0.35;
      body.position.y = hLerp * CELL - 0.22 * CELL;
      const stroke = Math.sin(animPhase);
      armL.rotation.x = stroke * 0.9 - 0.3;
      armR.rotation.x = -stroke * 0.9 - 0.3;
      legL.rotation.x = Math.sin(animPhase + Math.PI) * 0.5;
      legR.rotation.x = Math.sin(animPhase) * 0.5;
    } else {
      root.rotation.x += (0 - root.rotation.x) * Math.min(1, dt * 8);
      body.position.y = hLerp * CELL;
      if (moving) {
        const swing = Math.sin(animPhase);
        legL.rotation.x = swing * 0.55;
        legR.rotation.x = -swing * 0.55;
        armL.rotation.x = -swing * 0.4;
        armR.rotation.x = swing * 0.4;
        body.position.y += Math.abs(Math.cos(animPhase)) * 0.02 * CELL;
      } else {
        legL.rotation.x *= 0.8;
        legR.rotation.x *= 0.8;
        armL.rotation.x *= 0.8;
        armR.rotation.x *= 0.8;
        // A gentle idle sway while the explorer waits for a safe route.
        body.position.y += Math.sin(elapsed * 1.4) * 0.01 * CELL;
      }
    }

    root.position.set(outPos.x, 0, outPos.z);
    if (Math.abs(to.x - from.x) > 0.001 || Math.abs(to.z - from.z) > 0.001) {
      const yaw = Math.atan2(to.x - from.x, to.z - from.z);
      root.rotation.y += (yaw - root.rotation.y) * Math.min(1, dt * 10);
    }
  }

  return {
    object: root,
    update,
    dispose() {
      torso.geometry.dispose();
      head.geometry.dispose();
      suitMat.dispose();
      skinMat.dispose();
      for (const p of [legL, legR, armL, armR]) p.children[0].geometry.dispose();
    },
  };
}
