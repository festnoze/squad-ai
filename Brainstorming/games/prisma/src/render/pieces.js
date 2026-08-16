/**
 * PRISMA - solid objects sitting on the board.
 *
 * The factory owns every geometry and material and hands out plain Groups.
 * Removing a group from the scene therefore needs no disposal at all, which is
 * what makes rebuilding the board on each edit cheap.
 */

import * as THREE from 'three';
import { CELL } from '../grid.js';

/** Beam colours, indexed by RGB mask. Kept slightly off pure so a red beam and
 *  a magenta beam never read the same under the room light. */
export const MASK_COLOR = [
  [0.10, 0.10, 0.14],
  [1.00, 0.16, 0.22],
  [0.20, 1.00, 0.36],
  [1.00, 0.86, 0.20],
  [0.24, 0.44, 1.00],
  [1.00, 0.28, 0.92],
  [0.24, 0.96, 1.00],
  [1.00, 1.00, 1.00],
];

export function maskToColor(mask, out = new THREE.Color()) {
  const c = MASK_COLOR[mask & 7];
  return out.setRGB(c[0], c[1], c[2]);
}

/** Local +Z of a mesh maps onto this world direction after the rotation. */
const DIR_ANGLE = [Math.PI / 2, 0, -Math.PI / 2, Math.PI];

/** Angle that points the shiny face at the corner shared by faces r and r+1. */
const MIRROR_ANGLE = [Math.PI / 4, -Math.PI / 4, -3 * Math.PI / 4, 3 * Math.PI / 4];

export function createPieceFactory(textures) {
  const geo = {
    plate: new THREE.BoxGeometry(0.78, 0.44, 0.045),
    plateBack: new THREE.BoxGeometry(0.8, 0.46, 0.05),
    edge: new THREE.BoxGeometry(0.84, 0.06, 0.1),
    prism: new THREE.CylinderGeometry(0.32, 0.32, 0.46, 3, 1),
    bead: new THREE.SphereGeometry(0.055, 8, 6),
    filterBody: new THREE.CylinderGeometry(0.29, 0.29, 0.4, 16, 1, true),
    filterRim: new THREE.TorusGeometry(0.3, 0.035, 6, 20),
    ringFlat: new THREE.TorusGeometry(0.33, 0.045, 8, 24),
    arrow: new THREE.ConeGeometry(0.11, 0.24, 4),
    stem: new THREE.BoxGeometry(0.06, 0.06, 0.22),
    wall: new THREE.BoxGeometry(1, 0.92, 1),
    base: new THREE.CylinderGeometry(0.36, 0.4, 0.09, 16),
    stalk: new THREE.CylinderGeometry(0.07, 0.1, 0.3, 8),
    emitterBody: new THREE.BoxGeometry(0.62, 0.5, 0.7),
    muzzle: new THREE.CylinderGeometry(0.13, 0.17, 0.24, 12),
    lens: new THREE.SphereGeometry(0.21, 16, 12),
    targetRing: new THREE.TorusGeometry(0.3, 0.05, 8, 24),
    quad: new THREE.PlaneGeometry(1, 1),
    disc: new THREE.CircleGeometry(0.36, 24),
  };

  const mat = {
    chrome: new THREE.MeshStandardMaterial({
      color: 0xdfe8f6,
      metalness: 0.95,
      roughness: 0.12,
      envMapIntensity: 1.5,
    }),
    dark: new THREE.MeshStandardMaterial({ color: 0x2b3145, metalness: 0.3, roughness: 0.8 }),
    frame: new THREE.MeshStandardMaterial({ color: 0x555f7d, metalness: 0.7, roughness: 0.35 }),
    glass: new THREE.MeshStandardMaterial({
      color: 0x9f7bff,
      metalness: 0.1,
      roughness: 0.08,
      transparent: true,
      opacity: 0.45,
      emissive: 0x2a1350,
      envMapIntensity: 1.2,
      side: THREE.DoubleSide,
    }),
    halfSilver: new THREE.MeshStandardMaterial({
      color: 0xb9e6ff,
      metalness: 0.75,
      roughness: 0.15,
      transparent: true,
      opacity: 0.5,
      envMapIntensity: 1.6,
      side: THREE.DoubleSide,
    }),
    amber: new THREE.MeshStandardMaterial({
      color: 0xffc35c,
      metalness: 0.6,
      roughness: 0.3,
      emissive: 0x8a5200,
      emissiveIntensity: 1,
    }),
    wall: new THREE.MeshStandardMaterial({
      color: 0x59617f,
      map: textures.panel,
      metalness: 0.25,
      roughness: 0.85,
    }),
    wallCap: new THREE.MeshStandardMaterial({
      color: 0x8fa2d8,
      emissive: 0x27306a,
      metalness: 0.4,
      roughness: 0.5,
    }),
    emitter: new THREE.MeshStandardMaterial({ color: 0x3f4864, metalness: 0.65, roughness: 0.4 }),
    muzzle: new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false }),
    portalRing: new THREE.MeshStandardMaterial({
      color: 0xb07cff,
      emissive: 0x6a2fd0,
      emissiveIntensity: 1.4,
      metalness: 0.5,
      roughness: 0.3,
    }),
    portalFace: new THREE.MeshBasicMaterial({
      map: textures.portal,
      color: 0xc79bff,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      toneMapped: false,
    }),
  };

  // One material family per colour mask, built lazily.
  const tinted = new Map();
  function tintFamily(mask) {
    let fam = tinted.get(mask);
    if (fam) return fam;
    const col = maskToColor(mask);
    fam = {
      solid: new THREE.MeshStandardMaterial({
        color: col.clone().multiplyScalar(0.55),
        emissive: col.clone().multiplyScalar(0.22),
        metalness: 0.4,
        roughness: 0.35,
        transparent: true,
        opacity: 0.62,
        side: THREE.DoubleSide,
      }),
      rim: new THREE.MeshStandardMaterial({
        color: col.clone(),
        emissive: col.clone().multiplyScalar(0.75),
        emissiveIntensity: 1.2,
        metalness: 0.5,
        roughness: 0.3,
      }),
      lensOff: new THREE.MeshStandardMaterial({
        color: col.clone().multiplyScalar(0.3),
        emissive: col.clone().multiplyScalar(0.1),
        metalness: 0.2,
        roughness: 0.5,
      }),
      lensOn: new THREE.MeshBasicMaterial({ color: col.clone(), toneMapped: false }),
      flare: new THREE.MeshBasicMaterial({
        map: textures.glow,
        color: col.clone(),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
      face: new THREE.MeshBasicMaterial({
        map: textures.ring,
        color: col.clone(),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
        side: THREE.DoubleSide,
      }),
      bead: new THREE.MeshBasicMaterial({ color: col.clone(), toneMapped: false }),
    };
    tinted.set(mask, fam);
    return fam;
  }

  const ghostMats = new Map();
  function asGhost(m) {
    let g = ghostMats.get(m);
    if (g) return g;
    g = m.clone();
    g.transparent = true;
    g.opacity = (m.opacity !== undefined && m.transparent ? m.opacity : 1) * 0.4;
    g.depthWrite = false;
    ghostMats.set(m, g);
    return g;
  }

  function mesh(geometry, material, ghost) {
    return new THREE.Mesh(geometry, ghost ? asGhost(material) : material);
  }

  // ---- individual builders -------------------------------------------------

  /** Foot and stalk. Component groups sit at beam height, so the mount is built
   *  in negative local Y and reaches down to the floor slab. */
  function addMount(group, ghost) {
    const base = mesh(geo.base, mat.frame, ghost);
    base.position.y = -0.34;
    const stalk = mesh(geo.stalk, mat.frame, ghost);
    stalk.position.y = -0.2;
    group.add(base, stalk);
  }

  function buildMirror(rot, ghost) {
    const g = new THREE.Group();
    const back = mesh(geo.plateBack, mat.dark, ghost);
    back.position.z = -0.035;
    const face = mesh(geo.plate, mat.chrome, ghost);
    const rim = mesh(geo.edge, mat.frame, ghost);
    rim.position.y = -0.24;
    g.add(back, face, rim);
    addMount(g, ghost);
    g.position.y = 0.42;
    g.rotation.y = MIRROR_ANGLE[rot];
    return g;
  }

  function buildSplitter(rot, ghost) {
    const g = new THREE.Group();
    const face = mesh(geo.plate, mat.halfSilver, ghost);
    const rim = mesh(geo.edge, mat.frame, ghost);
    rim.position.y = -0.24;
    const rim2 = mesh(geo.edge, mat.frame, ghost);
    rim2.position.y = 0.24;
    g.add(face, rim, rim2);
    addMount(g, ghost);
    g.position.y = 0.42;
    g.rotation.y = MIRROR_ANGLE[rot];
    return g;
  }

  function buildPrism(rot, ghost) {
    const g = new THREE.Group();
    const body = mesh(geo.prism, mat.glass, ghost);
    body.rotation.y = Math.PI / 6;
    g.add(body);
    const perm = [
      [1, 2, 4],
      [2, 4, 1],
      [4, 1, 2],
    ][rot];
    for (let i = 0; i < 3; i++) {
      const bead = mesh(geo.bead, tintFamily(perm[i]).bead, ghost);
      const a = (i / 3) * Math.PI * 2 + Math.PI / 2;
      bead.position.set(Math.cos(a) * 0.24, 0.26, Math.sin(a) * 0.24);
      g.add(bead);
    }
    addMount(g, ghost);
    g.position.y = 0.42;
    return g;
  }

  function buildFilter(rot, ghost) {
    const g = new THREE.Group();
    const fam = tintFamily([1, 2, 4][rot]);
    const body = mesh(geo.filterBody, fam.solid, ghost);
    g.add(body);
    for (const y of [0.2, -0.2]) {
      const rim = mesh(geo.filterRim, fam.rim, ghost);
      rim.rotation.x = Math.PI / 2;
      rim.position.y = y;
      g.add(rim);
    }
    addMount(g, ghost);
    g.position.y = 0.42;
    return g;
  }

  function buildCombiner(rot, ghost) {
    const g = new THREE.Group();
    const ring = mesh(geo.ringFlat, mat.amber, ghost);
    ring.rotation.x = Math.PI / 2;
    g.add(ring);
    const ring2 = mesh(geo.ringFlat, mat.amber, ghost);
    ring2.scale.setScalar(0.62);
    g.add(ring2);
    const stem = mesh(geo.stem, mat.amber, ghost);
    stem.position.set(0, 0, 0.3);
    const tip = mesh(geo.arrow, mat.amber, ghost);
    tip.position.set(0, 0, 0.46);
    tip.rotation.x = Math.PI / 2;
    const head = new THREE.Group();
    head.add(stem, tip);
    head.rotation.y = DIR_ANGLE[rot];
    g.add(head);
    addMount(g, ghost);
    g.position.y = 0.42;
    return g;
  }

  function buildWall() {
    const g = new THREE.Group();
    const body = new THREE.Mesh(geo.wall, mat.wall);
    body.position.y = 0.46;
    body.castShadow = true;
    body.receiveShadow = true;
    const cap = new THREE.Mesh(geo.quad, mat.wallCap);
    cap.rotation.x = -Math.PI / 2;
    cap.position.y = 0.925;
    cap.scale.setScalar(0.98);
    g.add(body, cap);
    return g;
  }

  function buildEmitter(cell) {
    const g = new THREE.Group();
    const body = new THREE.Mesh(geo.emitterBody, mat.emitter);
    body.position.y = 0.3;
    body.castShadow = true;
    const muzzle = new THREE.Mesh(geo.muzzle, mat.muzzle);
    muzzle.rotation.x = Math.PI / 2;
    muzzle.position.set(0, 0.42, 0.42);
    const halo = new THREE.Mesh(geo.quad, tintFamily(7).flare);
    halo.position.set(0, 0.42, 0.5);
    halo.scale.setScalar(0.85);
    const head = new THREE.Group();
    head.add(muzzle, halo);
    head.rotation.y = DIR_ANGLE[cell.dir];
    const base = new THREE.Mesh(geo.base, mat.frame);
    base.position.y = 0.05;
    g.add(body, head, base);
    g.userData.billboards = [halo];
    return g;
  }

  function buildTarget(cell) {
    const fam = tintFamily(cell.mask);
    const g = new THREE.Group();
    const base = new THREE.Mesh(geo.base, mat.frame);
    base.position.y = 0.05;
    const lens = new THREE.Mesh(geo.lens, fam.lensOff);
    lens.position.y = 0.42;
    lens.scale.y = 0.8;
    const ring = new THREE.Mesh(geo.targetRing, fam.rim);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.16;
    const face = new THREE.Mesh(geo.quad, fam.face);
    face.rotation.x = -Math.PI / 2;
    face.position.y = 0.115;
    face.scale.setScalar(0.95);
    const flare = new THREE.Mesh(geo.quad, fam.flare);
    flare.position.y = 0.42;
    flare.scale.setScalar(0.1);
    g.add(base, lens, ring, face, flare);
    g.userData.lens = lens;
    g.userData.lensOn = fam.lensOn;
    g.userData.lensOff = fam.lensOff;
    g.userData.flare = flare;
    g.userData.spin = face;
    g.userData.billboards = [flare];
    return g;
  }

  function buildPortal() {
    const g = new THREE.Group();
    const ring = new THREE.Mesh(geo.ringFlat, mat.portalRing);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.12;
    ring.scale.setScalar(1.2);
    const face = new THREE.Mesh(geo.disc, mat.portalFace);
    face.rotation.x = -Math.PI / 2;
    face.position.y = 0.08;
    g.add(ring, face);
    g.userData.spin = face;
    return g;
  }

  /** Builds the visual for one board cell, or null when there is nothing to show. */
  function build(cell, ghost = false) {
    switch (cell.type) {
      case CELL.WALL:
        return buildWall();
      case CELL.EMITTER:
        return buildEmitter(cell);
      case CELL.TARGET:
        return buildTarget(cell);
      case CELL.PORTAL:
        return buildPortal();
      case CELL.MIRROR:
        return buildMirror(cell.rot, ghost);
      case CELL.PRISM:
        return buildPrism(cell.rot, ghost);
      case CELL.FILTER:
        return buildFilter(cell.rot, ghost);
      case CELL.COMBINER:
        return buildCombiner(cell.rot, ghost);
      case CELL.SPLITTER:
        return buildSplitter(cell.rot, ghost);
      default:
        return null;
    }
  }

  const KIND_BUILD = {
    mirror: buildMirror,
    prism: buildPrism,
    filter: buildFilter,
    combiner: buildCombiner,
    splitter: buildSplitter,
  };

  function buildKind(kind, rot, ghost = false) {
    const fn = KIND_BUILD[kind];
    return fn ? fn(rot, ghost) : null;
  }

  function setEnvironment(envMap) {
    for (const m of Object.values(mat)) {
      if (m.isMeshStandardMaterial) {
        m.envMap = envMap;
        m.needsUpdate = true;
      }
    }
  }

  function dispose() {
    for (const g of Object.values(geo)) g.dispose();
    for (const m of Object.values(mat)) m.dispose();
    for (const fam of tinted.values()) for (const m of Object.values(fam)) m.dispose();
    for (const m of ghostMats.values()) m.dispose();
    tinted.clear();
    ghostMats.clear();
  }

  return { build, buildKind, setEnvironment, dispose, materials: mat, geometries: geo };
}
