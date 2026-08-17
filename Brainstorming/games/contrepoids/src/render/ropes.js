/**
 * CONTREPOIDS - pulleys and cables.
 *
 * Every rope pair gets one fixed pulley, mounted above the taller of its two
 * butees, and two cable segments (pulley -> column A, pulley -> column B)
 * whose length and orientation are recomputed every frame from the columns'
 * current interpolated height. No soft-rope physics: the cable is always a
 * straight taut line between two known points, exactly as a real pulley rope
 * behaves when both ends are rigid platforms.
 */

import * as THREE from 'three';
import { CRAN_UNIT, PLATFORM_THICK, RIG_MARGIN, worldX, worldZ } from './layout.js';

const UP = new THREE.Vector3(0, 1, 0);
const tmpA = new THREE.Vector3();
const tmpB = new THREE.Vector3();
const tmpMid = new THREE.Vector3();
const tmpDir = new THREE.Vector3();
const tmpQuat = new THREE.Quaternion();
const tmpScale = new THREE.Vector3();
const tmpMatrix = new THREE.Matrix4();
const pulleyQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
const pulleyScale = new THREE.Vector3(1, 1, 1);
const identityQuat = new THREE.Quaternion();

export function createRopes(textures) {
  const group = new THREE.Group();

  const cableGeom = new THREE.CylinderGeometry(0.035, 0.035, 1, 6, 1, true);
  const cableMat = new THREE.MeshStandardMaterial({ map: textures.rope, roughness: 0.95, metalness: 0 });
  const pulleyGeom = new THREE.TorusGeometry(0.26, 0.09, 8, 16);
  const pulleyMat = new THREE.MeshStandardMaterial({ map: textures.iron, roughness: 0.4, metalness: 0.8 });
  const postGeom = new THREE.CylinderGeometry(0.06, 0.06, 1, 6);
  const postMat = new THREE.MeshStandardMaterial({ color: 0x3a3a3f, roughness: 0.7, metalness: 0.5 });

  let cableMesh = null;
  let pulleyMesh = null;
  let postMesh = null;
  let ropes = [];
  let rigY = [];
  let rigPos = []; // Vector3 per rope, the pulley world position

  const api = { group };

  api.build = function build(state) {
    if (cableMesh) {
      group.remove(cableMesh);
      group.remove(pulleyMesh);
      group.remove(postMesh);
      cableMesh.dispose();
      pulleyMesh.dispose();
      postMesh.dispose();
    }
    ropes = state.ropes;
    rigY = new Array(ropes.length);
    rigPos = new Array(ropes.length);

    for (let i = 0; i < ropes.length; i++) {
      const a = state.columns[ropes[i].a];
      const b = state.columns[ropes[i].b];
      const topH = Math.max(a.maxH, b.maxH);
      const y = topH * CRAN_UNIT + RIG_MARGIN;
      rigY[i] = y;
      rigPos[i] = new THREE.Vector3((worldX(a.gx) + worldX(b.gx)) / 2, y, (worldZ(a.gz) + worldZ(b.gz)) / 2);
    }

    cableMesh = new THREE.InstancedMesh(cableGeom, cableMat, Math.max(1, ropes.length * 2));
    pulleyMesh = new THREE.InstancedMesh(pulleyGeom, pulleyMat, Math.max(1, ropes.length));
    postMesh = new THREE.InstancedMesh(postGeom, postMat, Math.max(1, ropes.length));
    cableMesh.castShadow = false;
    pulleyMesh.castShadow = true;
    postMesh.castShadow = true;
    // A level with no ropes (e.g. a pure jump level) still allocates a single
    // placeholder instance above; hide it rather than showing a stray part.
    const hasRopes = ropes.length > 0;
    cableMesh.visible = hasRopes;
    pulleyMesh.visible = hasRopes;
    postMesh.visible = hasRopes;
    group.add(cableMesh, pulleyMesh, postMesh);

    for (let i = 0; i < ropes.length; i++) {
      const p = rigPos[i];
      tmpMatrix.compose(p, pulleyQuat, pulleyScale);
      pulleyMesh.setMatrixAt(i, tmpMatrix);

      tmpB.set(p.x, p.y / 2, p.z);
      tmpScale.set(1, p.y, 1);
      tmpMatrix.compose(tmpB, identityQuat, tmpScale);
      postMesh.setMatrixAt(i, tmpMatrix);
    }
    pulleyMesh.instanceMatrix.needsUpdate = true;
    postMesh.instanceMatrix.needsUpdate = true;
  };

  function placeCable(index, from, to) {
    tmpDir.subVectors(to, from);
    const len = Math.max(0.02, tmpDir.length());
    tmpMid.addVectors(from, to).multiplyScalar(0.5);
    tmpDir.normalize();
    tmpQuat.setFromUnitVectors(UP, tmpDir);
    tmpScale.set(1, len, 1);
    tmpMatrix.compose(tmpMid, tmpQuat, tmpScale);
    cableMesh.setMatrixAt(index, tmpMatrix);
  }

  /** heights: indexable by column id, current interpolated cran value. */
  api.setHeights = function setHeights(state, heights) {
    for (let i = 0; i < ropes.length; i++) {
      const rope = ropes[i];
      const colA = state.columns[rope.a];
      const colB = state.columns[rope.b];
      const p = rigPos[i];

      tmpA.set(worldX(colA.gx), heights[colA.id] * CRAN_UNIT + PLATFORM_THICK * 0.5, worldZ(colA.gz));
      placeCable(i * 2, p, tmpA);

      tmpB.set(worldX(colB.gx), heights[colB.id] * CRAN_UNIT + PLATFORM_THICK * 0.5, worldZ(colB.gz));
      placeCable(i * 2 + 1, p, tmpB);
    }
    cableMesh.instanceMatrix.needsUpdate = true;
  };

  api.dispose = function dispose() {
    if (cableMesh) {
      cableMesh.dispose();
      pulleyMesh.dispose();
      postMesh.dispose();
    }
    cableGeom.dispose();
    cableMat.dispose();
    pulleyGeom.dispose();
    pulleyMat.dispose();
    postGeom.dispose();
    postMat.dispose();
  };

  return api;
}
