/**
 * PONTS DE FORTUNE - drawing the bridge.
 *
 * One instanced mesh per material, refilled every frame from whichever source
 * is current: the flat plan while building, the solver (or a replay buffer)
 * while testing. Both paths share the same beam writer, so a member looks
 * identical before and after the convoy shows up.
 *
 * Stress colouring: blue in compression, red in tension, saturation rising with
 * the ratio to capacity. That single cue is what makes a failure readable
 * before it happens.
 */

import * as THREE from 'three';
import { MATERIALS, BRACE, HALF_WIDTH, PALETTE } from '../config.js';
import { colToX, rowToY, canPlaceNode, anchorPoints } from '../levels.js';

const MAX_ELEMENTS = 340;
const MAX_NODES = 320;
const MAX_DEBRIS = 96;
const MAX_DUST = 260;

const mA = new THREE.Vector3();
const mB = new THREE.Vector3();
const dirV = new THREE.Vector3();
const upRef = new THREE.Vector3(0, 1, 0);
const sideV = new THREE.Vector3();
const normV = new THREE.Vector3();
const basis = new THREE.Matrix4();
const scaleM = new THREE.Matrix4();
const outM = new THREE.Matrix4();
const tmpColor = new THREE.Color();
const baseColor = new THREE.Color();
const hotColor = new THREE.Color();

/** Beam matrix: unit box (or unit cylinder) stretched from a to b. */
function beamMatrix(ax, ay, az, bx, by, bz, w, h, cylinder) {
  dirV.set(bx - ax, by - ay, bz - az);
  const len = dirV.length();
  if (len < 1e-5) {
    outM.makeScale(1e-4, 1e-4, 1e-4);
    outM.setPosition(ax, ay, az);
    return outM;
  }
  dirV.multiplyScalar(1 / len);
  if (Math.abs(dirV.y) > 0.999) sideV.set(1, 0, 0);
  else sideV.copy(upRef).cross(dirV).normalize();
  normV.copy(dirV).cross(sideV).normalize();
  if (cylinder) {
    // Cylinder geometry runs along +Y.
    basis.makeBasis(sideV, dirV, normV);
    scaleM.makeScale(w, len, h);
  } else {
    basis.makeBasis(dirV, normV, sideV);
    scaleM.makeScale(len, h, w);
  }
  outM.multiplyMatrices(basis, scaleM);
  outM.setPosition((ax + bx) * 0.5, (ay + by) * 0.5, (az + bz) * 0.5);
  return outM;
}

function makeInstanced(geo, mat, count, scene) {
  const m = new THREE.InstancedMesh(geo, mat, count);
  m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  m.frustumCulled = false;
  m.castShadow = true;
  m.receiveShadow = true;
  m.count = 0;
  scene.add(m);
  return m;
}

export function createBridgeView(scene, textures) {
  const geos = [];
  const mats = [];
  const boxGeo = new THREE.BoxGeometry(1, 1, 1);
  const cylGeo = new THREE.CylinderGeometry(0.5, 0.5, 1, 7, 1);
  const dotGeo = new THREE.OctahedronGeometry(0.42, 0);
  geos.push(boxGeo, cylGeo, dotGeo);

  function memberMaterial(map, rough, metal) {
    const m = new THREE.MeshStandardMaterial({
      map, color: 0xffffff, roughness: rough, metalness: metal,
    });
    mats.push(m);
    return m;
  }

  const meshes = {
    wood: makeInstanced(boxGeo, memberMaterial(textures.wood, 0.88, 0.02), MAX_ELEMENTS * 2, scene),
    steel: makeInstanced(boxGeo, memberMaterial(textures.steel, 0.44, 0.55), MAX_ELEMENTS * 2, scene),
    cable: makeInstanced(cylGeo, memberMaterial(textures.cable, 0.62, 0.25), MAX_ELEMENTS * 2, scene),
    road: makeInstanced(boxGeo, memberMaterial(textures.road, 0.9, 0.02), MAX_ELEMENTS, scene),
  };
  const traverseMat = memberMaterial(textures.steel, 0.7, 0.3);
  const traverses = makeInstanced(boxGeo, traverseMat, MAX_NODES + MAX_ELEMENTS, scene);

  // Grid joints, only while building.
  const dotMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85, fog: false });
  mats.push(dotMat);
  const dots = makeInstanced(dotGeo, dotMat, 640, scene);
  dots.castShadow = false;
  dots.receiveShadow = false;

  // Ghost of the member being drawn.
  const previewMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.6, fog: false });
  mats.push(previewMat);
  const preview = new THREE.Mesh(boxGeo, previewMat);
  preview.visible = false;
  preview.renderOrder = 3;
  preview.matrixAutoUpdate = false;
  scene.add(preview);

  // Debris and dust.
  const debrisGeo = new THREE.BoxGeometry(1, 1, 1);
  geos.push(debrisGeo);
  const debrisMat = memberMaterial(textures.wood, 0.9, 0.05);
  const debris = makeInstanced(debrisGeo, debrisMat, MAX_DEBRIS, scene);
  const debrisData = [];
  for (let i = 0; i < MAX_DEBRIS; i++) {
    debrisData.push({ life: 0, x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, rx: 0, ry: 0, rz: 0, w: 1, h: 1, l: 1, c: 0x8a5a30 });
  }
  let debrisHead = 0;

  const dustGeo = new THREE.BufferGeometry();
  const dustPos = new Float32Array(MAX_DUST * 3);
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
  geos.push(dustGeo);
  const dustMat = new THREE.PointsMaterial({
    map: textures.soft, size: 2.6, transparent: true, opacity: 0.5,
    depthWrite: false, sizeAttenuation: true, color: 0xd8d2c6,
  });
  mats.push(dustMat);
  const dust = new THREE.Points(dustGeo, dustMat);
  dust.frustumCulled = false;
  scene.add(dust);
  const dustData = [];
  for (let i = 0; i < MAX_DUST; i++) dustData.push({ life: 0, vx: 0, vy: 0, vz: 0 });
  let dustHead = 0;
  for (let i = 0; i < MAX_DUST; i++) dustPos[i * 3 + 1] = -9999;

  let level = null;
  let bridge = null;
  let plan = null;
  let hover = -1;
  const counters = { wood: 0, steel: 0, cable: 0, road: 0, traverse: 0 };

  function resetCounters() {
    counters.wood = 0; counters.steel = 0; counters.cable = 0; counters.road = 0; counters.traverse = 0;
  }

  function flushCounters() {
    meshes.wood.count = counters.wood;
    meshes.steel.count = counters.steel;
    meshes.cable.count = counters.cable;
    meshes.road.count = counters.road;
    traverses.count = counters.traverse;
    meshes.wood.instanceMatrix.needsUpdate = true;
    meshes.steel.instanceMatrix.needsUpdate = true;
    meshes.cable.instanceMatrix.needsUpdate = true;
    meshes.road.instanceMatrix.needsUpdate = true;
    traverses.instanceMatrix.needsUpdate = true;
    if (meshes.wood.instanceColor) meshes.wood.instanceColor.needsUpdate = true;
    if (meshes.steel.instanceColor) meshes.steel.instanceColor.needsUpdate = true;
    if (meshes.cable.instanceColor) meshes.cable.instanceColor.needsUpdate = true;
    if (meshes.road.instanceColor) meshes.road.instanceColor.needsUpdate = true;
    if (traverses.instanceColor) traverses.instanceColor.needsUpdate = true;
  }

  function pushMember(type, ax, ay, az, bx, by, bz, color) {
    const mesh = meshes[type];
    const i = counters[type];
    if (i >= mesh.instanceMatrix.count) return;
    const mat = MATERIALS[type];
    const w = mat.radius * 2;
    const h = type === 'road' ? 0.36 : mat.radius * 2;
    mesh.setMatrixAt(i, beamMatrix(ax, ay, az, bx, by, bz, w, h, type === 'cable'));
    mesh.setColorAt(i, color);
    counters[type] = i + 1;
  }

  function pushRoadSlab(ax, ay, az, bx, by, bz, color) {
    const mesh = meshes.road;
    const i = counters.road;
    if (i >= mesh.instanceMatrix.count) return;
    mesh.setMatrixAt(i, beamMatrix(ax, ay, az, bx, by, bz, HALF_WIDTH * 2 + 0.5, 0.42, false));
    mesh.setColorAt(i, color);
    counters.road = i + 1;
  }

  function pushTraverse(ax, ay, az, bx, by, bz) {
    const i = counters.traverse;
    if (i >= traverses.instanceMatrix.count) return;
    traverses.setMatrixAt(i, beamMatrix(ax, ay, az, bx, by, bz, BRACE.radius * 2, BRACE.radius * 2, false));
    tmpColor.setHex(BRACE.color);
    traverses.setColorAt(i, tmpColor);
    counters.traverse = i + 1;
  }

  /** Colour of a member given its stress. `ratio` 0..1, `sign` +1 tension. */
  function stressColor(type, ratio, sign, out) {
    baseColor.setHex(MATERIALS[type].color);
    if (!(ratio > 0.04)) return out.copy(baseColor);
    hotColor.setHex(sign >= 0 ? PALETTE.tension : PALETTE.compression);
    const t = Math.min(1, ratio);
    // Capped below 1: a fully tinted member would lose its material identity.
    const mix = t * t * (3 - 2 * t) * 0.78;
    out.copy(baseColor).lerp(hotColor, mix);
    if (t > 0.65) out.multiplyScalar(1 + (t - 0.65) * 2.2);
    return out;
  }

  function setLevel(lv) {
    level = lv;
    let n = 0;
    const s = new THREE.Vector3();
    const q = new THREE.Quaternion();
    const p = new THREE.Vector3();
    const anchors = anchorPoints(level);
    const isAnchor = (c, r) => {
      for (let i = 0; i < anchors.length; i++) if (anchors[i][0] === c && anchors[i][1] === r) return true;
      return false;
    };
    for (let c = level.left; c <= level.right; c++) {
      for (let r = level.rowMin; r <= level.rowMax; r++) {
        if (!canPlaceNode(level, c, r)) continue;
        if (n >= dots.instanceMatrix.count) break;
        const fixed = isAnchor(c, r);
        p.set(colToX(level, c), rowToY(r), 0);
        s.setScalar(fixed ? 1.5 : 0.62);
        outM.compose(p, q, s);
        dots.setMatrixAt(n, outM);
        // Fixed points are the ones worth spotting from across the ravine.
        tmpColor.setHex(fixed ? 0xffb648 : (r === 0 ? 0xf4efe2 : 0x9fb2c4));
        dots.setColorAt(n, tmpColor);
        n += 1;
      }
    }
    dots.count = n;
    dots.instanceMatrix.needsUpdate = true;
    if (dots.instanceColor) dots.instanceColor.needsUpdate = true;
  }

  function setBridge(b) { bridge = b; }
  function setPlan(p) { plan = p; }
  function setHover(i) { hover = i; }
  function showGrid(v) { dots.visible = v; }

  /** Build mode: everything sits exactly on the grid. */
  function drawModel() {
    resetCounters();
    if (!bridge) { flushCounters(); return; }
    const els = bridge.elements;
    for (let i = 0; i < els.length; i++) {
      const e = els[i];
      const ax = colToX(level, e.ca);
      const ay = rowToY(e.ra);
      const bx = colToX(level, e.cb);
      const by = rowToY(e.rb);
      baseColor.setHex(MATERIALS[e.type].color);
      if (i === hover) baseColor.setHex(MATERIALS[e.type].hot);
      if (e.type === 'road') {
        pushRoadSlab(ax, ay, 0, bx, by, 0, baseColor);
      } else {
        pushMember(e.type, ax, ay, -HALF_WIDTH, bx, by, -HALF_WIDTH, baseColor);
        pushMember(e.type, ax, ay, HALF_WIDTH, bx, by, HALF_WIDTH, baseColor);
      }
    }
    const nodes = bridge.nodes;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      pushTraverse(n.x, n.y, -HALF_WIDTH, n.x, n.y, HALF_WIDTH);
    }
    flushCounters();
  }

  /** Test and replay: positions come from the state buffer. */
  function drawState(state) {
    resetCounters();
    if (!plan || !bridge) { flushCounters(); return; }
    const pos = state.pos;
    const links = plan.sim.links;
    const els = bridge.elements;
    for (let i = 0; i < els.length; i++) {
      const e = els[i];
      const pairIdx = plan.elemLinks[i];
      const l0 = links[pairIdx[0]];
      const l1 = links[pairIdx[1]];
      const b0 = state.broken[pairIdx[0]];
      const b1 = state.broken[pairIdx[1]];
      if (b0 && b1) continue;
      if (e.type === 'road') {
        const src = b0 ? l1 : l0;
        const other = b0 ? l0 : l1;
        const a0 = src.a * 3;
        const a1 = other.a * 3;
        const c0 = src.b * 3;
        const c1 = other.b * 3;
        const ax = (pos[a0] + pos[a1]) * 0.5;
        const ay = (pos[a0 + 1] + pos[a1 + 1]) * 0.5;
        const az = (pos[a0 + 2] + pos[a1 + 2]) * 0.5;
        const bx = (pos[c0] + pos[c1]) * 0.5;
        const by = (pos[c0 + 1] + pos[c1 + 1]) * 0.5;
        const bz = (pos[c0 + 2] + pos[c1 + 2]) * 0.5;
        const ri = b0 ? pairIdx[1] : pairIdx[0];
        stressColor('road', state.ratio[ri], state.sign[ri], tmpColor);
        pushRoadSlab(ax, ay, az, bx, by, bz, tmpColor);
        continue;
      }
      for (let s = 0; s < 2; s++) {
        const li = pairIdx[s];
        if (state.broken[li]) continue;
        const l = links[li];
        const ia = l.a * 3;
        const ib = l.b * 3;
        stressColor(e.type, state.ratio[li], state.sign[li], tmpColor);
        pushMember(e.type, pos[ia], pos[ia + 1], pos[ia + 2], pos[ib], pos[ib + 1], pos[ib + 2], tmpColor);
      }
    }
    const tl = plan.traverses;
    for (let i = 0; i < tl.length; i++) {
      if (state.broken[tl[i]]) continue;
      const l = links[tl[i]];
      const ia = l.a * 3;
      const ib = l.b * 3;
      pushTraverse(pos[ia], pos[ia + 1], pos[ia + 2], pos[ib], pos[ib + 1], pos[ib + 2]);
    }
    flushCounters();
  }

  function setPreview(a, b, type, ok) {
    if (!a || !b || !type) { preview.visible = false; return; }
    const mat = MATERIALS[type];
    const ax = colToX(level, a[0]);
    const ay = rowToY(a[1]);
    const bx = colToX(level, b[0]);
    const by = rowToY(b[1]);
    const w = type === 'road' ? HALF_WIDTH * 2 + 0.5 : mat.radius * 2.6;
    preview.matrix.copy(beamMatrix(ax, ay, 0, bx, by, 0, w, mat.radius * 2.6, false));
    preview.matrixWorldNeedsUpdate = true;
    previewMat.color.setHex(ok ? 0x8ff0a8 : 0xff6b5a);
    preview.visible = true;
  }

  /** Spawn debris and dust where a member has just failed. */
  function burst(x, y, z, kind) {
    const mat = MATERIALS[kind] || MATERIALS.wood;
    for (let k = 0; k < 4; k++) {
      const d = debrisData[debrisHead];
      debrisHead = (debrisHead + 1) % MAX_DEBRIS;
      d.life = 2.6 + Math.random() * 1.6;
      d.x = x + (Math.random() - 0.5) * 1.6;
      d.y = y + (Math.random() - 0.5) * 1.6;
      d.z = z + (Math.random() - 0.5) * 2.4;
      d.vx = (Math.random() - 0.5) * 7;
      d.vy = 1.5 + Math.random() * 6;
      d.vz = (Math.random() - 0.5) * 5;
      d.rx = (Math.random() - 0.5) * 8;
      d.ry = (Math.random() - 0.5) * 8;
      d.rz = (Math.random() - 0.5) * 8;
      d.w = 0.14 + Math.random() * 0.2;
      d.h = 0.14 + Math.random() * 0.18;
      d.l = 0.5 + Math.random() * 1.1;
      d.c = mat.color;
    }
    for (let k = 0; k < 10; k++) {
      const i = dustHead;
      dustHead = (dustHead + 1) % MAX_DUST;
      dustPos[i * 3] = x + (Math.random() - 0.5) * 2;
      dustPos[i * 3 + 1] = y + (Math.random() - 0.5) * 2;
      dustPos[i * 3 + 2] = z + (Math.random() - 0.5) * 3;
      const p = dustData[i];
      p.life = 1.4 + Math.random() * 1.4;
      p.vx = (Math.random() - 0.5) * 3;
      p.vy = 0.6 + Math.random() * 2.4;
      p.vz = (Math.random() - 0.5) * 3;
    }
  }

  const dPos = new THREE.Vector3();
  const dQuat = new THREE.Quaternion();
  const dEul = new THREE.Euler();
  const dScale = new THREE.Vector3();
  let clock = 0;

  function update(dt, timeScale) {
    const ts = timeScale === undefined ? 1 : timeScale;
    const step = dt * ts;
    clock += step;
    let live = 0;
    for (let i = 0; i < MAX_DEBRIS; i++) {
      const d = debrisData[i];
      if (d.life <= 0) continue;
      d.life -= step;
      d.vy -= 9.81 * step;
      d.x += d.vx * step;
      d.y += d.vy * step;
      d.z += d.vz * step;
      dPos.set(d.x, d.y, d.z);
      dEul.set(d.rx * clock * 0.5, d.ry * clock * 0.5, d.rz * clock * 0.5);
      dQuat.setFromEuler(dEul);
      dScale.set(d.l, d.h, d.w);
      outM.compose(dPos, dQuat, dScale);
      debris.setMatrixAt(live, outM);
      tmpColor.setHex(d.c);
      debris.setColorAt(live, tmpColor);
      live += 1;
    }
    debris.count = live;
    debris.instanceMatrix.needsUpdate = true;
    if (debris.instanceColor) debris.instanceColor.needsUpdate = true;

    let dustDirty = false;
    for (let i = 0; i < MAX_DUST; i++) {
      const p = dustData[i];
      if (p.life <= 0) continue;
      p.life -= step;
      p.vy -= 1.2 * step;
      dustPos[i * 3] += p.vx * step;
      dustPos[i * 3 + 1] += p.vy * step;
      dustPos[i * 3 + 2] += p.vz * step;
      if (p.life <= 0) dustPos[i * 3 + 1] = -9999;
      dustDirty = true;
    }
    if (dustDirty) dustGeo.attributes.position.needsUpdate = true;
  }

  function clearEffects() {
    for (let i = 0; i < MAX_DEBRIS; i++) debrisData[i].life = 0;
    debris.count = 0;
    for (let i = 0; i < MAX_DUST; i++) {
      dustData[i].life = 0;
      dustPos[i * 3 + 1] = -9999;
    }
    dustGeo.attributes.position.needsUpdate = true;
  }

  function dispose() {
    const all = [meshes.wood, meshes.steel, meshes.cable, meshes.road, traverses, dots, debris];
    for (const m of all) { scene.remove(m); m.dispose(); }
    scene.remove(preview);
    scene.remove(dust);
    for (let i = 0; i < geos.length; i++) geos[i].dispose();
    for (let i = 0; i < mats.length; i++) mats[i].dispose();
  }

  return {
    setLevel, setBridge, setPlan, setHover, showGrid,
    drawModel, drawState, setPreview, burst, update, clearEffects, dispose,
  };
}
