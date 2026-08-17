/**
 * CONTREPOIDS - column and cargo rendering.
 *
 * Every ground and platform column of a level shares two InstancedMesh draw
 * calls (the wooden/rock body and the iron ring), whatever the level size.
 * Only cargo (pierre/enclume/ballon) gets individual meshes, since a level
 * never carries more than a handful at once.
 *
 * `setHeights` is called every frame with the *current* interpolated height
 * (in crans, float) for every column id; it is the only place that writes
 * instance matrices, so the animation easing lives entirely in main.js.
 */

import * as THREE from 'three';
import { OBJ } from '../shaft.js';
import { CRAN_UNIT, PLATFORM_SIZE, PLATFORM_THICK, worldX, worldZ } from './layout.js';

const tmpPos = new THREE.Vector3();
const tmpQuat = new THREE.Quaternion();
const tmpScale = new THREE.Vector3(1, 1, 1);
const tmpMatrix = new THREE.Matrix4();
const IDLE_QUAT = new THREE.Quaternion();
const RING_QUAT = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));

export function createPlatforms(textures) {
  const group = new THREE.Group();
  const itemGroup = new THREE.Group();
  group.add(itemGroup);

  const bodyGeom = new THREE.BoxGeometry(PLATFORM_SIZE, PLATFORM_THICK, PLATFORM_SIZE);
  const ringGeom = new THREE.TorusGeometry(PLATFORM_SIZE * 0.56, 0.05, 8, 20);

  const bodyMaterial = [
    new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.88, metalness: 0.04 }),
    new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.88, metalness: 0.04 }),
    new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.82, metalness: 0.04 }),
    new THREE.MeshStandardMaterial({ map: textures.iron, roughness: 0.5, metalness: 0.7 }),
    new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.88, metalness: 0.04 }),
    new THREE.MeshStandardMaterial({ map: textures.wood, roughness: 0.88, metalness: 0.04 }),
  ];
  const ringMaterial = new THREE.MeshStandardMaterial({ map: textures.iron, roughness: 0.45, metalness: 0.75 });

  let bodyMesh = null;
  let ringMesh = null;
  let columns = [];
  const itemMeshes = new Map(); // colId -> mesh

  const pierreGeom = new THREE.IcosahedronGeometry(0.32, 0);
  const pierreMat = new THREE.MeshStandardMaterial({ map: textures.stone, roughness: 0.9, metalness: 0.02 });
  const enclumeGeom = buildEnclumeGeometry();
  const enclumeMat = new THREE.MeshStandardMaterial({ map: textures.iron, roughness: 0.4, metalness: 0.8, color: 0x8a8f97 });
  const ballonGeom = new THREE.SphereGeometry(0.34, 16, 12);
  const ballonMat = new THREE.MeshStandardMaterial({ map: textures.balloon, roughness: 0.35, metalness: 0.05 });
  const knotGeom = new THREE.ConeGeometry(0.06, 0.12, 8);
  const knotMat = new THREE.MeshStandardMaterial({ color: 0x6a4318, roughness: 0.8 });

  function buildEnclumeGeometry() {
    const geo = new THREE.BoxGeometry(0.5, 0.32, 0.28);
    return geo;
  }

  function clearItems() {
    for (const mesh of itemMeshes.values()) {
      itemGroup.remove(mesh);
      mesh.traverse((n) => {
        if (n.geometry && n.geometry !== pierreGeom && n.geometry !== enclumeGeom && n.geometry !== ballonGeom && n.geometry !== knotGeom) n.geometry.dispose();
      });
    }
    itemMeshes.clear();
  }

  function makeItemMesh(kind) {
    if (kind === OBJ.PIERRE) {
      const m = new THREE.Mesh(pierreGeom, pierreMat);
      m.castShadow = true;
      return m;
    }
    if (kind === OBJ.ENCLUME) {
      const holder = new THREE.Group();
      const base = new THREE.Mesh(enclumeGeom, enclumeMat);
      base.castShadow = true;
      holder.add(base);
      const horn = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.32, 10), enclumeMat);
      horn.rotation.z = Math.PI / 2;
      horn.position.set(0.34, 0.02, 0);
      holder.add(horn);
      return holder;
    }
    // Ballon: sphere plus a small knot underneath.
    const holder = new THREE.Group();
    const sphere = new THREE.Mesh(ballonGeom, ballonMat);
    sphere.castShadow = true;
    sphere.position.y = 0.34;
    holder.add(sphere);
    const knot = new THREE.Mesh(knotGeom, knotMat);
    knot.position.y = 0.02;
    holder.add(knot);
    return holder;
  }

  const api = {
    group,
    bounds: { minX: 0, maxX: 0, minY: 0, maxY: 0, minZ: 0, maxZ: 0 },
  };

  /** (Re)builds the instance list for a freshly loaded level. */
  api.build = function build(state) {
    if (bodyMesh) {
      group.remove(bodyMesh);
      group.remove(ringMesh);
      bodyMesh.dispose();
      ringMesh.dispose();
    }
    columns = state.columns;
    bodyMesh = new THREE.InstancedMesh(bodyGeom, bodyMaterial, columns.length);
    bodyMesh.castShadow = true;
    bodyMesh.receiveShadow = true;
    ringMesh = new THREE.InstancedMesh(ringGeom, ringMaterial, columns.length);
    ringMesh.castShadow = false;
    group.add(bodyMesh);
    group.add(ringMesh);
    clearItems();
    api.syncItems(state);
  };

  /** Rebuild cargo meshes from the current item field of every column. */
  api.syncItems = function syncItems(state) {
    const seen = new Set();
    for (let i = 0; i < state.columns.length; i++) {
      const col = state.columns[i];
      if (!col.item) continue;
      seen.add(col.id);
      let mesh = itemMeshes.get(col.id);
      if (!mesh || mesh.userData.kind !== col.item) {
        if (mesh) itemGroup.remove(mesh);
        mesh = makeItemMesh(col.item);
        mesh.userData.kind = col.item;
        itemMeshes.set(col.id, mesh);
        itemGroup.add(mesh);
      }
    }
    for (const [colId, mesh] of Array.from(itemMeshes.entries())) {
      if (!seen.has(colId)) {
        itemGroup.remove(mesh);
        itemMeshes.delete(colId);
      }
    }
  };

  /** heights: Float64Array-like indexable by column id, in crans (may be fractional). */
  api.setHeights = function setHeights(heights) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (let i = 0; i < columns.length; i++) {
      const col = columns[i];
      const x = worldX(col.gx);
      const z = worldZ(col.gz);
      const y = heights[col.id] * CRAN_UNIT;

      tmpPos.set(x, y, z);
      tmpMatrix.compose(tmpPos, IDLE_QUAT, tmpScale);
      bodyMesh.setMatrixAt(i, tmpMatrix);

      tmpPos.set(x, y + PLATFORM_THICK * 0.5 + 0.01, z);
      tmpMatrix.compose(tmpPos, RING_QUAT, tmpScale);
      ringMesh.setMatrixAt(i, tmpMatrix);

      const mesh = itemMeshes.get(col.id);
      if (mesh) {
        // Pierre and enclume meshes are centred on their own origin, so they
        // need lifting by roughly half their height to rest on the surface
        // instead of floating half-buried in the platform; the ballon holder
        // already places its sphere above its own anchor point.
        let lift = 0;
        if (col.item === OBJ.PIERRE) lift = 0.26;
        else if (col.item === OBJ.ENCLUME) lift = 0.16;
        mesh.position.set(x, y + PLATFORM_THICK * 0.5 + lift, z);
      }

      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    bodyMesh.instanceMatrix.needsUpdate = true;
    ringMesh.instanceMatrix.needsUpdate = true;
    const b = api.bounds;
    b.minX = minX; b.maxX = maxX; b.minY = minY; b.maxY = maxY; b.minZ = minZ; b.maxZ = maxZ;
  };

  /** World position (top surface) of a column at a given interpolated height. */
  api.surfacePoint = function surfacePoint(col, h, out) {
    out.set(worldX(col.gx), h * CRAN_UNIT + PLATFORM_THICK * 0.5, worldZ(col.gz));
    return out;
  };

  api.dispose = function dispose() {
    clearItems();
    if (bodyMesh) {
      bodyMesh.dispose();
      ringMesh.dispose();
    }
    bodyGeom.dispose();
    ringGeom.dispose();
    for (let i = 0; i < bodyMaterial.length; i++) bodyMaterial[i].dispose();
    ringMaterial.dispose();
    pierreGeom.dispose();
    pierreMat.dispose();
    enclumeGeom.dispose();
    enclumeMat.dispose();
    ballonGeom.dispose();
    ballonMat.dispose();
    knotGeom.dispose();
    knotMat.dispose();
  };

  return api;
}
