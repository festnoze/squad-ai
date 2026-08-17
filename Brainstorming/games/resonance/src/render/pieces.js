/**
 * RESONANCE - forks, crystals, gauges, fragments.
 *
 * Everything repeated is an InstancedMesh: crystal shells, crystal cores,
 * charge rings, forbidden decals, forks, fork halos and shatter fragments.
 * Shatter debris is instanced triangles, never THREE.Points: point size math
 * has already whitened a whole screen in this repo (world-size factor trap).
 */

import * as THREE from 'three';
import { PERIODS } from '../wave.js';
import { CHARGE_TIME } from '../board.js';
import { slotToWorldX, slotToWorldZ } from '../coords.js';
import { BAND_COLORS } from './surface.js';

const MAX_CRYSTALS = 12;
const MAX_FORKS = 12;
const MAX_FRAGS = 96;
const FORBIDDEN_COLOR = new THREE.Color(1.0, 0.22, 0.28);

// Scratch objects: module-level, used linearly, never across nested calls.
const _m = new THREE.Matrix4();
const _p = new THREE.Vector3();
const _q = new THREE.Quaternion();
const _s = new THREE.Vector3();
const _c = new THREE.Color();
const _axisY = new THREE.Vector3(0, 1, 0);

/** Concatenate indexed geometries (position + normal) under given matrices. */
function mergeGeoms(parts) {
  let vCount = 0;
  let iCount = 0;
  for (const [g] of parts) {
    vCount += g.attributes.position.count;
    iCount += g.index.count;
  }
  const pos = new Float32Array(vCount * 3);
  const nor = new Float32Array(vCount * 3);
  const idx = new Uint16Array(iCount);
  let vo = 0;
  let io = 0;
  const nm = new THREE.Matrix3();
  for (const [g, m] of parts) {
    const gp = g.attributes.position;
    const gn = g.attributes.normal;
    nm.getNormalMatrix(m);
    for (let i = 0; i < gp.count; i++) {
      _p.fromBufferAttribute(gp, i).applyMatrix4(m);
      pos.set([_p.x, _p.y, _p.z], (vo + i) * 3);
      _p.fromBufferAttribute(gn, i).applyMatrix3(nm).normalize();
      nor.set([_p.x, _p.y, _p.z], (vo + i) * 3);
    }
    for (let i = 0; i < g.index.count; i++) idx[io + i] = g.index.array[i] + vo;
    vo += gp.count;
    io += g.index.count;
    g.dispose();
  }
  const out = new THREE.BufferGeometry();
  out.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  out.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  out.setIndex(new THREE.BufferAttribute(idx, 1));
  return out;
}

function forkGeometry() {
  const mk = (g, x, y, z) => [g, new THREE.Matrix4().makeTranslation(x, y, z)];
  return mergeGeoms([
    mk(new THREE.CylinderGeometry(0.17, 0.2, 0.07, 12), 0, 0.035, 0),   // base disc
    mk(new THREE.CylinderGeometry(0.045, 0.055, 0.34, 8), 0, 0.24, 0),  // stem
    mk(new THREE.BoxGeometry(0.3, 0.09, 0.09), 0, 0.44, 0),             // crossbar
    mk(new THREE.BoxGeometry(0.07, 0.5, 0.07), -0.115, 0.72, 0),        // prong L
    mk(new THREE.BoxGeometry(0.07, 0.5, 0.07), 0.115, 0.72, 0),         // prong R
  ]);
}

export function createPieces(scene, textures) {
  const group = new THREE.Group();
  scene.add(group);

  // --- crystals: faceted shell (lit) + additive core (charge glow) ---------
  const shellGeom = new THREE.OctahedronGeometry(0.46, 0);
  shellGeom.scale(1, 1.9, 1);
  const shellMat = new THREE.MeshStandardMaterial({
    color: 0xffffff, roughness: 0.18, metalness: 0.05, flatShading: true,
  });
  const shells = new THREE.InstancedMesh(shellGeom, shellMat, MAX_CRYSTALS);

  const coreGeom = new THREE.OctahedronGeometry(0.3, 0);
  coreGeom.scale(1, 2.1, 1);
  const coreMat = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
  });
  const cores = new THREE.InstancedMesh(coreGeom, coreMat, MAX_CRYSTALS);

  const ringGeom = new THREE.TorusGeometry(0.6, 0.05, 8, 40);
  const ringMat = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
  });
  const rings = new THREE.InstancedMesh(ringGeom, ringMat, MAX_CRYSTALS);

  const warnGeom = new THREE.PlaneGeometry(0.95, 0.95);
  const warnMat = new THREE.MeshBasicMaterial({
    map: textures.warn, transparent: true, depthWrite: false, opacity: 0.9,
  });
  const warns = new THREE.InstancedMesh(warnGeom, warnMat, MAX_CRYSTALS);

  // --- forks + halos --------------------------------------------------------
  const forkGeom = forkGeometry();
  // Low metalness on purpose: metal without an environment map renders
  // near-black in this repo's scenes (known trap).
  const forkMat = new THREE.MeshStandardMaterial({
    color: 0xffffff, roughness: 0.45, metalness: 0.15, flatShading: true,
  });
  const forks = new THREE.InstancedMesh(forkGeom, forkMat, MAX_FORKS);

  const haloGeom = new THREE.PlaneGeometry(1.5, 1.5);
  const haloMat = new THREE.MeshBasicMaterial({
    map: textures.halo, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
  });
  const halos = new THREE.InstancedMesh(haloGeom, haloMat, MAX_FORKS);

  // --- shatter fragments ----------------------------------------------------
  const fragGeom = new THREE.TetrahedronGeometry(0.11, 0);
  const fragMat = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
  });
  const frags = new THREE.InstancedMesh(fragGeom, fragMat, MAX_FRAGS);
  const fragPos = new Float32Array(MAX_FRAGS * 3);
  const fragVel = new Float32Array(MAX_FRAGS * 3);
  const fragLife = new Float32Array(MAX_FRAGS);
  const fragSpin = new Float32Array(MAX_FRAGS);
  let fragCursor = 0;

  // --- selection ring + hover frame ----------------------------------------
  const selRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.42, 0.03, 8, 32),
    new THREE.MeshBasicMaterial({
      color: 0xffffff, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
    }),
  );
  selRing.rotation.x = -Math.PI / 2;
  selRing.visible = false;

  const hover = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({
      map: textures.frame, blending: THREE.AdditiveBlending, depthWrite: false,
      transparent: true, opacity: 0.6,
    }),
  );
  hover.rotation.x = -Math.PI / 2;
  hover.visible = false;

  for (const mesh of [shells, cores, rings, warns, forks, halos, frags]) {
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.count = 0;
    group.add(mesh);
  }
  group.add(selRing, hover);

  // Force instanceColor buffers into existence before first render.
  for (const mesh of [shells, cores, rings, warns, forks, halos, frags]) {
    for (let i = 0; i < mesh.instanceMatrix.count; i++) mesh.setColorAt(i, _c.setRGB(1, 1, 1));
  }

  const resonatorGroups = [];
  let board = null;

  function makeResonator(r) {
    const g = new THREE.Group();
    const ped = new THREE.Mesh(
      new THREE.CylinderGeometry(0.16, 0.24, 0.5, 10),
      new THREE.MeshStandardMaterial({ color: 0x8a86a8, roughness: 0.4, metalness: 0.6 }),
    );
    ped.position.y = 0.25;
    const gemIn = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.14, 0),
      new THREE.MeshBasicMaterial({ color: BAND_COLORS[r.from] }),
    );
    gemIn.position.set(-0.14, 0.66, 0);
    const gemOut = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.14, 0),
      new THREE.MeshBasicMaterial({ color: BAND_COLORS[r.to] }),
    );
    gemOut.position.set(0.14, 0.66, 0);
    const hoop = new THREE.Mesh(
      new THREE.TorusGeometry(0.3, 0.03, 8, 24),
      new THREE.MeshStandardMaterial({ color: 0xccc8e8, roughness: 0.3, metalness: 0.7 }),
    );
    hoop.position.y = 0.66;
    g.add(ped, gemIn, gemOut, hoop);
    g.position.set(slotToWorldX(r.x), 0, slotToWorldZ(r.y));
    return g;
  }

  function setBoard(b) {
    board = b;
    for (const g of resonatorGroups) group.remove(g);
    resonatorGroups.length = 0;
    for (const r of b.level.resonators || []) {
      const g = makeResonator(r);
      resonatorGroups.push(g);
      group.add(g);
    }
    fragLife.fill(0);
    frags.count = 0;
    // Forbidden ground decals are static for the level.
    let w = 0;
    for (const c of b.crystals) {
      if (!c.forbidden) continue;
      _p.set(slotToWorldX(c.x), 0.05, slotToWorldZ(c.y));
      _q.setFromAxisAngle(_axisY, 0);
      _m.makeRotationX(-Math.PI / 2).setPosition(_p);
      warns.setMatrixAt(w, _m);
      warns.setColorAt(w, _c.setRGB(1, 1, 1));
      w++;
    }
    warns.count = w;
    warns.instanceMatrix.needsUpdate = true;
    if (warns.instanceColor) warns.instanceColor.needsUpdate = true;
  }

  function shatter(crystal) {
    const color = crystal.forbidden ? FORBIDDEN_COLOR : BAND_COLORS[crystal.band];
    const wx = slotToWorldX(crystal.x);
    const wz = slotToWorldZ(crystal.y);
    for (let k = 0; k < 16; k++) {
      const i = fragCursor;
      fragCursor = (fragCursor + 1) % MAX_FRAGS;
      fragPos[i * 3] = wx;
      fragPos[i * 3 + 1] = 0.6;
      fragPos[i * 3 + 2] = wz;
      const ang = (k / 16) * Math.PI * 2 + Math.random() * 0.5;
      const sp = 1.6 + Math.random() * 2.2;
      fragVel[i * 3] = Math.cos(ang) * sp;
      fragVel[i * 3 + 1] = 2.4 + Math.random() * 2.6;
      fragVel[i * 3 + 2] = Math.sin(ang) * sp;
      fragLife[i] = 1.0;
      fragSpin[i] = (Math.random() - 0.5) * 12;
      frags.setColorAt(i, color);
    }
    frags.count = MAX_FRAGS;
    if (frags.instanceColor) frags.instanceColor.needsUpdate = true;
  }

  /** Per-frame instance refresh from board state. */
  function sync(time, selectedFork, hoverSlot) {
    if (!board) return;

    // Crystals.
    let n = 0;
    for (const c of board.crystals) {
      const wx = slotToWorldX(c.x);
      const wz = slotToWorldZ(c.y);
      const color = c.forbidden ? FORBIDDEN_COLOR : BAND_COLORS[c.band];
      const frac = Math.min(1, c.charge / CHARGE_TIME);
      if (c.shattered) {
        _s.setScalar(0.0001);
      } else {
        const pulse = 1 + Math.sin(time * (6 + frac * 14)) * 0.05 * (0.3 + frac);
        _s.set(pulse, pulse, pulse);
      }
      _p.set(wx, 0.85, wz);
      _q.setFromAxisAngle(_axisY, time * 0.4 + c.x);
      _m.compose(_p, _q, _s);
      shells.setMatrixAt(n, _m);
      _c.copy(color).multiplyScalar(c.forbidden ? 0.75 : 0.9).addScalar(0.18);
      shells.setColorAt(n, _c);
      cores.setMatrixAt(n, _m);
      _c.copy(color).multiplyScalar(c.shattered ? 0 : 0.4 + frac * 1.5 + Math.sin(time * 10) * 0.08 * frac);
      cores.setColorAt(n, _c);
      // Charge gauge ring on the ground: grows brighter with charge; the
      // forbidden ring stays faintly visible so danger has an anchor.
      _p.set(wx, 0.03, wz);
      _q.setFromAxisAngle(_axisY, 0);
      const rs = 1 + frac * 0.25;
      _s.set(rs, rs, rs);
      _m.compose(_p, _q, _s);
      _m.multiply(_m2RotX);
      rings.setMatrixAt(n, _m);
      const base = c.forbidden ? 0.25 : 0.1;
      _c.copy(color).multiplyScalar(c.shattered ? 0 : base + frac * 1.3);
      rings.setColorAt(n, _c);
      n++;
    }
    shells.count = cores.count = rings.count = n;
    shells.instanceMatrix.needsUpdate = true;
    cores.instanceMatrix.needsUpdate = true;
    rings.instanceMatrix.needsUpdate = true;
    if (shells.instanceColor) shells.instanceColor.needsUpdate = true;
    if (cores.instanceColor) cores.instanceColor.needsUpdate = true;
    if (rings.instanceColor) rings.instanceColor.needsUpdate = true;

    // Forks.
    let f = 0;
    for (const fork of board.forks) {
      const wx = slotToWorldX(fork.x);
      const wz = slotToWorldZ(fork.y);
      _p.set(wx, 0, wz);
      // The fork leans a touch per phase step: a silent but visible cue.
      _q.setFromAxisAngle(_axisY, fork.phase * (Math.PI / 2));
      _s.setScalar(1);
      _m.compose(_p, _q, _s);
      forks.setMatrixAt(f, _m);
      _c.copy(BAND_COLORS[fork.band]).multiplyScalar(0.55).addScalar(0.35);
      if (fork === selectedFork) _c.addScalar(0.35);
      forks.setColorAt(f, _c);
      // Ground halo pulsing at the fork's own period.
      const omega = (Math.PI * 2 * 60) / PERIODS[fork.band];
      const pulse = 0.3 + 0.14 * Math.sin(time * omega + fork.phase * Math.PI * 0.5);
      _p.set(wx, 0.04, wz);
      _m.makeRotationX(-Math.PI / 2).setPosition(_p);
      halos.setMatrixAt(f, _m);
      _c.copy(BAND_COLORS[fork.band]).multiplyScalar(pulse);
      halos.setColorAt(f, _c);
      f++;
    }
    forks.count = halos.count = f;
    forks.instanceMatrix.needsUpdate = true;
    halos.instanceMatrix.needsUpdate = true;
    if (forks.instanceColor) forks.instanceColor.needsUpdate = true;
    if (halos.instanceColor) halos.instanceColor.needsUpdate = true;

    // Selection + hover markers.
    if (selectedFork && board.forks.includes(selectedFork)) {
      selRing.visible = true;
      selRing.position.set(slotToWorldX(selectedFork.x), 0.06, slotToWorldZ(selectedFork.y));
      const k = 1 + Math.sin(time * 5) * 0.06;
      selRing.scale.setScalar(k);
    } else {
      selRing.visible = false;
    }
    if (hoverSlot) {
      hover.visible = true;
      hover.position.set(slotToWorldX(hoverSlot.x), 0.05, slotToWorldZ(hoverSlot.y));
    } else {
      hover.visible = false;
    }
  }

  /** Fragment physics + resonator idle motion. */
  function update(dt, time) {
    let any = false;
    for (let i = 0; i < MAX_FRAGS; i++) {
      if (fragLife[i] <= 0) {
        _s.setScalar(0.0001);
        _p.set(0, -10, 0);
        _q.identity();
        _m.compose(_p, _q, _s);
        frags.setMatrixAt(i, _m);
        continue;
      }
      any = true;
      fragLife[i] -= dt * 0.9;
      fragVel[i * 3 + 1] -= dt * 7.5;
      fragPos[i * 3] += fragVel[i * 3] * dt;
      fragPos[i * 3 + 1] += fragVel[i * 3 + 1] * dt;
      fragPos[i * 3 + 2] += fragVel[i * 3 + 2] * dt;
      if (fragPos[i * 3 + 1] < 0.05) {
        fragPos[i * 3 + 1] = 0.05;
        fragVel[i * 3 + 1] *= -0.4;
      }
      const l = Math.max(0, fragLife[i]);
      _p.set(fragPos[i * 3], fragPos[i * 3 + 1], fragPos[i * 3 + 2]);
      _q.setFromAxisAngle(_axisY, time * fragSpin[i]);
      _s.setScalar(l);
      _m.compose(_p, _q, _s);
      frags.setMatrixAt(i, _m);
    }
    frags.count = any ? MAX_FRAGS : 0;
    if (any) frags.instanceMatrix.needsUpdate = true;

    for (const g of resonatorGroups) g.rotation.y = time * 0.9;
  }

  function dispose() {
    scene.remove(group);
    for (const g of [shellGeom, coreGeom, ringGeom, warnGeom, forkGeom, haloGeom, fragGeom]) g.dispose();
    for (const m of [shellMat, coreMat, ringMat, warnMat, forkMat, haloMat, fragMat]) m.dispose();
    selRing.geometry.dispose();
    selRing.material.dispose();
    hover.geometry.dispose();
    hover.material.dispose();
  }

  return { setBoard, sync, shatter, update, dispose };
}

// Rings are torus geometry in the XY plane; this constant rotation lays each
// instance flat without allocating inside sync().
const _m2RotX = new THREE.Matrix4().makeRotationX(-Math.PI / 2);
