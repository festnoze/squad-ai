/**
 * MAREE - static level geometry: rock terrain, baked-in stone steps, gate
 * props and the exit beacon. Everything here is built once per level (the
 * rock floor never changes after load) and instanced wherever a shape
 * repeats, keeping the whole level under a handful of draw calls.
 */

import * as THREE from 'three';
import { CELL, PALETTE } from '../config.js';
import { colIndex, VOID_FLOOR, NO_BASIN } from '../world.js';

const scratchMatrix = new THREE.Matrix4();
const scratchPos = new THREE.Vector3();
const scratchQuat = new THREE.Quaternion();
const scratchScale = new THREE.Vector3(1, 1, 1);
const scratchColor = new THREE.Color();

export function createSceneObjects(textures) {
  const group = new THREE.Group();
  let rockMesh = null;
  let stoneMesh = null;
  const gateMeshes = [];
  let exitBeacon = null;
  let exitFlag = null;
  let exitBaseY = 0;
  const owned = [];
  let radius = 10;
  const center = new THREE.Vector3();

  function clear() {
    while (group.children.length) group.remove(group.children[0]);
    for (const o of owned) {
      if (o.geometry) o.geometry.dispose();
      if (o.material) o.material.dispose();
    }
    owned.length = 0;
    gateMeshes.length = 0;
    rockMesh = null;
    stoneMesh = null;
    exitBeacon = null;
    exitFlag = null;
  }

  function placeBox(mesh, index, x, z, bottom, top, hueJitter, rand) {
    const cx = (x - (mesh.userData.w - 1) / 2) * CELL;
    const cz = (z - (mesh.userData.d - 1) / 2) * CELL;
    const h = Math.max(top - bottom, 0.001);
    scratchPos.set(cx, bottom + h / 2, cz);
    scratchScale.set(CELL * 0.98, h, CELL * 0.98);
    scratchMatrix.compose(scratchPos, scratchQuat, scratchScale);
    mesh.setMatrixAt(index, scratchMatrix);
    if (mesh.setColorAt) {
      const t = 0.88 + (rand ? rand() : 0.5) * 0.24;
      scratchColor.setRGB(t, t, t);
      mesh.setColorAt(index, scratchColor);
    }
  }

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function next() {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /** Rebuilds every static mesh for a freshly created world state. */
  function build(state) {
    clear();
    const rand = mulberry32(state.level.id.charCodeAt(0) * 977 + 13);

    const columns = [];
    const stoneCols = new Set();
    for (const s of state.stoneAt) stoneCols.add(colIndex(state, s.x, s.z));

    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (let z = 0; z < state.d; z++) {
      for (let x = 0; x < state.w; x++) {
        const i = colIndex(state, x, z);
        if (state.floor[i] === VOID_FLOOR) continue;
        minX = Math.min(minX, x);
        maxX = Math.max(maxX, x);
        minZ = Math.min(minZ, z);
        maxZ = Math.max(maxZ, z);
        columns.push({ x, z, i, dry: state.basinOf[i] === NO_BASIN, stone: stoneCols.has(i) });
      }
    }

    const geom = new THREE.BoxGeometry(1, 1, 1);
    const rockMat = new THREE.MeshStandardMaterial({ map: textures.rock, roughness: 0.95, metalness: 0.0 });
    rockMesh = new THREE.InstancedMesh(geom, rockMat, columns.length || 1);
    rockMesh.userData.w = state.w;
    rockMesh.userData.d = state.d;
    rockMesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    rockMesh.castShadow = true;
    rockMesh.receiveShadow = true;
    owned.push(rockMesh);

    const shoreMat = new THREE.MeshStandardMaterial({ map: textures.shore, roughness: 0.92, metalness: 0.0 });
    const shoreMesh = new THREE.InstancedMesh(geom, shoreMat, columns.length || 1);
    shoreMesh.userData.w = state.w;
    shoreMesh.userData.d = state.d;
    shoreMesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);
    shoreMesh.castShadow = true;
    shoreMesh.receiveShadow = true;
    owned.push(shoreMesh);
    let rockCount = 0;
    let shoreCount = 0;

    for (const col of columns) {
      const fullFloor = state.floor[col.i];
      const rockH = col.stone ? fullFloor - 1 : fullFloor;
      const mesh = col.dry ? shoreMesh : rockMesh;
      const idx = col.dry ? shoreCount++ : rockCount++;
      if (rockH > 0) placeBox(mesh, idx, col.x, col.z, 0, rockH * CELL, 0, rand);
      else placeBox(mesh, idx, col.x, col.z, -0.2 * CELL, 0, 0, rand);
    }
    rockMesh.count = rockCount;
    shoreMesh.count = shoreCount;
    rockMesh.instanceMatrix.needsUpdate = true;
    shoreMesh.instanceMatrix.needsUpdate = true;
    if (rockMesh.instanceColor) rockMesh.instanceColor.needsUpdate = true;
    if (shoreMesh.instanceColor) shoreMesh.instanceColor.needsUpdate = true;
    group.add(rockMesh, shoreMesh);

    // Stone crates: the top cell of a stone-bumped column, as its own boxes so
    // they read as placed objects rather than plain terrain.
    if (state.stoneAt.length) {
      const stoneMat = new THREE.MeshStandardMaterial({ map: textures.stone, roughness: 0.85 });
      stoneMesh = new THREE.InstancedMesh(geom, stoneMat, state.stoneAt.length);
      stoneMesh.userData.w = state.w;
      stoneMesh.userData.d = state.d;
      stoneMesh.castShadow = true;
      stoneMesh.receiveShadow = true;
      owned.push(stoneMesh);
      for (let i = 0; i < state.stoneAt.length; i++) {
        const s = state.stoneAt[i];
        const floor = state.floor[colIndex(state, s.x, s.z)];
        placeBox(stoneMesh, i, s.x, s.z, (floor - 1) * CELL, floor * CELL, 0, rand);
      }
      stoneMesh.instanceMatrix.needsUpdate = true;
      group.add(stoneMesh);
    }

    // Gates: a small valve prop per gate, coloured by open/closed state.
    const gateGeomBody = new THREE.CylinderGeometry(0.16 * CELL, 0.2 * CELL, 0.5 * CELL, 10);
    const gateGeomWheel = new THREE.TorusGeometry(0.22 * CELL, 0.05 * CELL, 8, 16);
    owned.push(gateGeomBody, gateGeomWheel);
    for (const gate of state.gates) {
      const floorHere = Math.max(1, state.floor[colIndex(state, gate.x, gate.z)]);
      const mat = new THREE.MeshStandardMaterial({ color: PALETTE.gateClosed, roughness: 0.5, metalness: 0.4 });
      owned.push(mat);
      const body = new THREE.Mesh(gateGeomBody, mat);
      const wheel = new THREE.Mesh(gateGeomWheel, mat);
      wheel.position.y = 0.32 * CELL;
      wheel.rotation.x = Math.PI / 2;
      const holder = new THREE.Group();
      holder.add(body, wheel);
      const cx = (gate.x - (state.w - 1) / 2) * CELL;
      const cz = (gate.z - (state.d - 1) / 2) * CELL;
      holder.position.set(cx, floorHere * CELL + 0.35 * CELL, cz);
      holder.userData = { type: 'gate' };
      group.add(holder);
      gateMeshes.push({ holder, body, wheel, mat });
    }

    // Exit beacon: a slim pole with a small glowing flag above the exit column.
    const exitFloor = Math.max(0, state.floor[colIndex(state, state.exit.x, state.exit.z)]);
    const poleGeom = new THREE.CylinderGeometry(0.03 * CELL, 0.03 * CELL, 1.1 * CELL, 6);
    const poleMat = new THREE.MeshStandardMaterial({ color: 0x3a3226, roughness: 0.8 });
    const flagGeom = new THREE.ConeGeometry(0.22 * CELL, 0.4 * CELL, 4);
    const flagMat = new THREE.MeshStandardMaterial({ color: PALETTE.exit, emissive: new THREE.Color(PALETTE.exit), emissiveIntensity: 0.55, roughness: 0.5 });
    owned.push(poleGeom, poleMat, flagGeom, flagMat);
    const pole = new THREE.Mesh(poleGeom, poleMat);
    const flag = new THREE.Mesh(flagGeom, flagMat);
    flag.position.y = 0.75 * CELL;
    exitBeacon = new THREE.Group();
    exitBeacon.add(pole, flag);
    const ex = (state.exit.x - (state.w - 1) / 2) * CELL;
    const ez = (state.exit.z - (state.d - 1) / 2) * CELL;
    exitBaseY = exitFloor * CELL + 0.55 * CELL;
    exitBeacon.position.set(ex, exitBaseY, ez);
    group.add(exitBeacon);
    exitFlag = flag;

    let maxFloor = 0;
    for (const col of columns) maxFloor = Math.max(maxFloor, state.floor[col.i]);
    const cx = ((minX + maxX) / 2 - (state.w - 1) / 2) * CELL;
    const cz = ((minZ + maxZ) / 2 - (state.d - 1) / 2) * CELL;
    center.set(cx, maxFloor * CELL * 0.32, cz);
    const spanX = (maxX - minX + 1) * CELL;
    const spanZ = (maxZ - minZ + 1) * CELL;
    radius = Math.max(spanX, spanZ) * 0.6 + 2;

    return { gateMeshes, exitBeacon };
  }

  function setGateOpen(gateIndex, open) {
    const g = gateMeshes[gateIndex];
    if (!g) return;
    g.mat.color.set(open ? PALETTE.gateOpen : PALETTE.gateClosed);
    g.wheel.rotation.z = open ? Math.PI * 0.3 : 0;
  }

  function update(dt, elapsed) {
    if (exitFlag) exitFlag.rotation.y = elapsed * 1.4;
    if (exitBeacon) exitBeacon.position.y = exitBaseY + Math.sin(elapsed * 2.2) * 0.05 * CELL;
  }

  return {
    group,
    build,
    setGateOpen,
    update,
    get radius() {
      return radius;
    },
    get center() {
      return center;
    },
    get gates() {
      return gateMeshes;
    },
    dispose() {
      clear();
    },
  };
}
