/**
 * PONTS DE FORTUNE - the ravine.
 *
 * Two cliffs, a plateau on each rim, the approach roads, the stone piers and
 * steel masts a level may offer, a low mist at the bottom and a few birds.
 * Everything is generated: the cliff faces are ribbons of noise-displaced
 * vertices, rebuilt whenever the level changes.
 */

import * as THREE from 'three';
import { GRID, DECK_Y, HALF_WIDTH, RAVINE_DEPTH } from '../config.js';
import { colToX, rowToY } from '../levels.js';

const CLIFF_Z = 190; // half depth of the plateau along Z
const BACK = 260; // how far the plateau runs away from the gap
const FACE_STEPS = 22;
const Z_STEPS = 30;

function hash2(x, y) {
  let h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return h - Math.floor(h);
}

function noise2(x, y) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const sx = fx * fx * (3 - 2 * fx);
  const sy = fy * fy * (3 - 2 * fy);
  const a = hash2(ix, iy);
  const b = hash2(ix + 1, iy);
  const c = hash2(ix, iy + 1);
  const d = hash2(ix + 1, iy + 1);
  return (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy;
}

function fbm(x, y) {
  return noise2(x, y) * 0.6 + noise2(x * 2.1, y * 2.1) * 0.27 + noise2(x * 4.3, y * 4.3) * 0.13;
}

/**
 * One cliff, as a single ribbon: over the rim, down the face, then a floor
 * running back under the plateau so the ravine reads as solid from any angle.
 */
function cliffGeometry(edgeX, dir, seed) {
  const rows = FACE_STEPS + 3;
  const cols = Z_STEPS + 1;
  const pos = new Float32Array(rows * cols * 3);
  const uv = new Float32Array(rows * cols * 2);
  const idx = [];

  for (let j = 0; j < cols; j++) {
    const t = j / Z_STEPS;
    const z = -CLIFF_Z + t * CLIFF_Z * 2;
    for (let i = 0; i < rows; i++) {
      let x;
      let y;
      if (i === 0) {
        // rim, exactly at the plateau edge
        x = edgeX;
        y = DECK_Y;
      } else if (i <= FACE_STEPS) {
        const k = i / FACE_STEPS;
        const drop = Math.pow(k, 0.86);
        y = DECK_Y - drop * RAVINE_DEPTH;
        const wob = fbm(z * 0.035 + seed, k * 3.4 + seed * 2) - 0.5;
        // The face recedes as it falls, with overhangs and ledges from the noise.
        const retreat = 2.2 + drop * 13 + wob * 9 * Math.min(1, k * 3);
        x = edgeX - dir * retreat;
      } else if (i === FACE_STEPS + 1) {
        y = DECK_Y - RAVINE_DEPTH - 3;
        x = edgeX - dir * (26 + fbm(z * 0.05 + seed, 9) * 6);
      } else {
        y = DECK_Y - RAVINE_DEPTH - 4;
        x = edgeX - dir * BACK;
      }
      const o = (j * rows + i) * 3;
      pos[o] = x;
      pos[o + 1] = y;
      pos[o + 2] = z;
      const u = (j * rows + i) * 2;
      uv[u] = z * 0.02;
      uv[u + 1] = y * 0.022;
    }
  }

  for (let j = 0; j < cols - 1; j++) {
    for (let i = 0; i < rows - 1; i++) {
      const a = j * rows + i;
      const b = a + 1;
      const c = (j + 1) * rows + i;
      const d = c + 1;
      if (dir > 0) idx.push(a, b, d, a, d, c);
      else idx.push(a, d, b, a, c, d);
    }
  }

  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

function plateauGeometry(edgeX, dir) {
  const seg = 26;
  const g = new THREE.PlaneGeometry(BACK, CLIFF_Z * 2, seg, seg);
  g.rotateX(-Math.PI / 2);
  const p = g.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const lx = p.getX(i);
    const z = p.getZ(i);
    // Distance from the rim and from the road corridor; both must stay flat.
    const fromRim = (BACK * 0.5 - lx * dir) / BACK;
    const roadMask = Math.min(1, Math.max(0, (Math.abs(z) - 7) / 16));
    const bump = (fbm(lx * 0.05 + 30, z * 0.05) - 0.5) * 9;
    p.setY(i, DECK_Y + bump * Math.min(1, fromRim * 2.4) * roadMask);
  }
  g.computeVertexNormals();
  g.translate(edgeX - dir * BACK * 0.5, 0, 0);
  return g;
}

function makeMast(level, col, row, textures) {
  const group = new THREE.Group();
  const top = rowToY(row);
  const legMat = new THREE.MeshStandardMaterial({
    map: textures.steel, color: 0x6f7a86, roughness: 0.55, metalness: 0.35,
  });
  const legGeo = new THREE.BoxGeometry(0.55, 1, 0.55);
  const barGeo = new THREE.BoxGeometry(1, 0.3, 0.3);
  const legs = [];
  const half = top / 2;
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      const m = new THREE.Mesh(legGeo, legMat);
      m.scale.set(1, top + 1.6, 1);
      m.position.set(sx * 1.5, half - 0.4, sz * (HALF_WIDTH + 0.5));
      m.castShadow = true;
      legs.push(m);
      group.add(m);
    }
  }
  const rungs = Math.max(2, Math.round(top / 3));
  for (let i = 1; i <= rungs; i++) {
    const y = (i / (rungs + 1)) * top;
    for (const sz of [-1, 1]) {
      const b = new THREE.Mesh(barGeo, legMat);
      b.scale.set(3.4, 1, 1);
      b.position.set(0, y, sz * (HALF_WIDTH + 0.5));
      group.add(b);
    }
    const cross = new THREE.Mesh(barGeo, legMat);
    cross.scale.set(HALF_WIDTH * 2 + 1.4, 1, 1);
    cross.rotation.y = Math.PI / 2;
    cross.position.set(0, y, 0);
    group.add(cross);
  }
  const cap = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.7, HALF_WIDTH * 2 + 2.2), legMat);
  cap.position.set(0, top + 0.4, 0);
  cap.castShadow = true;
  group.add(cap);
  group.position.set(colToX(level, col), DECK_Y, 0);
  return { group, geos: [legGeo, barGeo, cap.geometry], mats: [legMat] };
}

function makePier(level, col, row, textures) {
  const h = rowToY(row) + RAVINE_DEPTH - 1;
  const mat = new THREE.MeshStandardMaterial({
    map: textures.rock, color: 0xe6ddd0, roughness: 0.94, metalness: 0,
  });
  const geo = new THREE.CylinderGeometry(2.6, 4.2, h, 10, 1);
  const m = new THREE.Mesh(geo, mat);
  m.position.set(colToX(level, col), rowToY(row) - h * 0.5, 0);
  m.castShadow = true;
  m.receiveShadow = true;
  const capGeo = new THREE.BoxGeometry(6.2, 1.1, HALF_WIDTH * 2 + 2.6);
  const cap = new THREE.Mesh(capGeo, mat);
  cap.position.set(colToX(level, col), rowToY(row) - 0.45, 0);
  cap.castShadow = true;
  const group = new THREE.Group();
  group.add(m, cap);
  return { group, geos: [geo, capGeo], mats: [mat] };
}

export function createTerrain(scene, textures, level) {
  const group = new THREE.Group();
  const geos = [];
  const mats = [];
  scene.add(group);

  const leftX = colToX(level, level.left);
  const rightX = colToX(level, level.right);

  const rockMat = new THREE.MeshStandardMaterial({
    map: textures.rock, color: 0xffffff, roughness: 0.95, metalness: 0, side: THREE.DoubleSide,
  });
  const grassMat = new THREE.MeshStandardMaterial({
    map: textures.grass, color: 0xcfd0b8, roughness: 1, metalness: 0,
  });
  mats.push(rockMat, grassMat);

  for (const [edge, dir, seed] of [[leftX, 1, 3.1], [rightX, -1, 17.7]]) {
    const cg = cliffGeometry(edge, dir, seed);
    const cm = new THREE.Mesh(cg, rockMat);
    cm.receiveShadow = true;
    group.add(cm);
    geos.push(cg);

    const pg = plateauGeometry(edge, dir);
    const pm = new THREE.Mesh(pg, grassMat);
    pm.receiveShadow = true;
    group.add(pm);
    geos.push(pg);
  }

  // Approach roads, flush with the deck.
  const roadMat = new THREE.MeshStandardMaterial({
    map: textures.road, color: 0xffffff, roughness: 0.92, metalness: 0,
  });
  mats.push(roadMat);
  for (const [edge, dir] of [[leftX, 1], [rightX, -1]]) {
    const len = BACK * 0.75;
    const g = new THREE.BoxGeometry(len, 0.5, HALF_WIDTH * 2 + 1.2);
    const m = new THREE.Mesh(g, roadMat);
    m.position.set(edge - dir * (len * 0.5 - 0.2), DECK_Y - 0.24, 0);
    m.receiveShadow = true;
    group.add(m);
    geos.push(g);
  }

  // Piers and masts declared by the level.
  const extras = [];
  for (let i = 0; i < level.piers.length; i++) {
    const p = makePier(level, level.piers[i][0], level.piers[i][1], textures);
    group.add(p.group);
    extras.push(p);
  }
  for (let i = 0; i < level.masts.length; i++) {
    const m = makeMast(level, level.masts[i][0], level.masts[i][1], textures);
    group.add(m.group);
    extras.push(m);
  }
  for (const e of extras) {
    for (const g of e.geos) geos.push(g);
    for (const m of e.mats) mats.push(m);
  }

  // A rock ceiling when the level caps the build height.
  if (level.ceilRow !== null) {
    const y = rowToY(level.ceilRow) + GRID * 0.85;
    const w = (level.right - level.left) * GRID + 26;
    // Deep enough to read as a rock roof, shallow enough to keep the sky.
    const g = new THREE.BoxGeometry(w, 12, 44);
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) {
      if (p.getY(i) < 0) p.setY(i, p.getY(i) + (fbm(p.getX(i) * 0.08, p.getZ(i) * 0.08) - 0.5) * 4.5);
    }
    g.computeVertexNormals();
    const m = new THREE.Mesh(g, rockMat);
    m.position.set((leftX + rightX) * 0.5, y + 6, 0);
    m.castShadow = true;
    group.add(m);
    geos.push(g);
  }

  // Dark floor far below, then mist drifting just above it. Without the floor
  // the mist reads as snow instead of as depth.
  const floorGeo = new THREE.PlaneGeometry(700, 420);
  floorGeo.rotateX(-Math.PI / 2);
  geos.push(floorGeo);
  const floorMat = new THREE.MeshStandardMaterial({
    map: textures.rock, color: 0x584f45, roughness: 1, metalness: 0,
  });
  mats.push(floorMat);
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.position.set(0, DECK_Y - RAVINE_DEPTH - 6, 0);
  group.add(floor);

  const mistMat = new THREE.MeshBasicMaterial({
    map: textures.mist, transparent: true, opacity: 0.42, depthWrite: false,
    side: THREE.DoubleSide, color: 0xdfe6e8, fog: false,
  });
  mats.push(mistMat);
  const mistGeo = new THREE.PlaneGeometry(360, 190);
  mistGeo.rotateX(-Math.PI / 2);
  geos.push(mistGeo);
  const mists = [];
  for (let i = 0; i < 3; i++) {
    const m = new THREE.Mesh(mistGeo, mistMat);
    m.position.set(0, DECK_Y - RAVINE_DEPTH + 1 + i * 6, 0);
    m.renderOrder = 2;
    group.add(m);
    mists.push(m);
  }

  // Birds, one instanced mesh of tiny V shapes.
  const birdCount = 14;
  const birdGeo = new THREE.BufferGeometry();
  birdGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([
    0, 0, 0, -1.1, 0.35, -0.5, -0.9, 0, -1.0,
    0, 0, 0, 1.1, 0.35, -0.5, 0.9, 0, -1.0,
  ]), 3));
  birdGeo.computeVertexNormals();
  geos.push(birdGeo);
  const birdMat = new THREE.MeshBasicMaterial({ color: 0x2a2f36, side: THREE.DoubleSide, fog: true });
  mats.push(birdMat);
  const birds = new THREE.InstancedMesh(birdGeo, birdMat, birdCount);
  birds.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  birds.frustumCulled = false;
  group.add(birds);

  const birdData = [];
  for (let i = 0; i < birdCount; i++) {
    birdData.push({
      r: 40 + hash2(i, 1) * 90,
      cx: (hash2(i, 2) - 0.5) * 120,
      cz: (hash2(i, 3) - 0.5) * 90,
      y: DECK_Y - 6 - hash2(i, 4) * 26,
      sp: 0.18 + hash2(i, 5) * 0.22,
      ph: hash2(i, 6) * 6.28,
      sc: 0.7 + hash2(i, 7) * 0.7,
    });
  }

  const mat4 = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const posv = new THREE.Vector3();
  const scalev = new THREE.Vector3();
  const eul = new THREE.Euler();
  let clock = 0;

  function update(dt) {
    clock += dt;
    for (let i = 0; i < birdCount; i++) {
      const b = birdData[i];
      const a = b.ph + clock * b.sp;
      posv.set(b.cx + Math.cos(a) * b.r, b.y + Math.sin(clock * 0.6 + b.ph) * 2.5, b.cz + Math.sin(a) * b.r * 0.6);
      const flap = 0.55 + Math.sin(clock * 9 + b.ph) * 0.45;
      eul.set(0, -a + Math.PI * 0.5, 0);
      quat.setFromEuler(eul);
      scalev.set(b.sc, b.sc * flap, b.sc);
      mat4.compose(posv, quat, scalev);
      birds.setMatrixAt(i, mat4);
    }
    birds.instanceMatrix.needsUpdate = true;
    for (let i = 0; i < mists.length; i++) {
      mists[i].position.x = Math.sin(clock * 0.05 + i) * 26;
      mists[i].position.z = Math.cos(clock * 0.037 + i * 2) * 18;
    }
  }

  function dispose() {
    scene.remove(group);
    for (let i = 0; i < geos.length; i++) geos[i].dispose();
    for (let i = 0; i < mats.length; i++) mats[i].dispose();
    birds.dispose();
    geos.length = 0;
    mats.length = 0;
  }

  return { group, update, dispose };
}
