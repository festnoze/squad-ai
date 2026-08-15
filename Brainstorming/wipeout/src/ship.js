/**
 * VELOCITRON - anti-gravity craft.
 *
 * Two responsibilities:
 *  1. createShipMesh: a fully procedural racer built from lofted sections,
 *     lathes and extrusions merged into three draw calls (hull, glow, canopy).
 *     The nose points toward -Z, the group origin sits on the craft floor at
 *     its geometric centre.
 *  2. The arcade flight model, integrated in track space (s, x, h, yaw) exactly
 *     as specified in docs/CONTRACTS.md section 6.
 *
 * Nothing in the update path allocates: every scratch object lives at module
 * level and is never shared between two functions that can nest.
 */

import * as THREE from 'three';
import { PALETTE, SHIP, TRACK } from './config.js';

// ---------------------------------------------------------------------------
// Small math helpers
// ---------------------------------------------------------------------------

const MAX_DT = 1 / 30;
const RESPAWN_SPEED = 34; // m/s the craft re-enters the track with
const BUMP_RESTITUTION = 0.35;
const BUMP_PUSH = 90; // m/s^2 of gentle separation while two hulls rub

const NEUTRAL_CONTROLS = {
  thrust: 0, brake: 0, steer: 0, airLeft: 0, airRight: 0, boost: false,
};

function clamp(v, lo, hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

function clamp01(v) {
  return v < 0 ? 0 : (v > 1 ? 1 : v);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

/** Returns v when it is a usable number, fallback otherwise. */
function finite(v, fallback) {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

// ---------------------------------------------------------------------------
// Geometry toolkit (build time only, never called per frame)
// ---------------------------------------------------------------------------

const MIRROR_X = new THREE.Matrix4().makeScale(-1, 1, 1);

/** Builds an indexed geometry from flat arrays and derives smooth normals. */
function makeGeometry(positions, uvs, indices) {
  const geom = new THREE.BufferGeometry();
  geom.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
  geom.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(uvs), 2));
  geom.setIndex(indices);
  geom.computeVertexNormals();
  return geom;
}

/**
 * Mirrors a geometry across the YZ plane. The normal matrix of a mirror flips
 * the normals correctly but leaves the winding inverted, so triangles are
 * re-ordered here.
 */
function mirrorGeometry(geom) {
  geom.applyMatrix4(MIRROR_X);
  const index = geom.index;
  if (index) {
    const a = index.array;
    for (let i = 0; i < a.length; i += 3) {
      const t = a[i];
      a[i] = a[i + 2];
      a[i + 2] = t;
    }
    index.needsUpdate = true;
  } else {
    for (const name of Object.keys(geom.attributes)) {
      const attr = geom.attributes[name];
      const arr = attr.array;
      const size = attr.itemSize;
      for (let i = 0; i < attr.count; i += 3) {
        for (let c = 0; c < size; c++) {
          const p = (i + 0) * size + c;
          const q = (i + 2) * size + c;
          const t = arr[p];
          arr[p] = arr[q];
          arr[q] = t;
        }
      }
      attr.needsUpdate = true;
    }
  }
  return geom;
}

/** Returns [g0, mirror(g0), g1, mirror(g1), ...] for a list of right side parts. */
function withMirror(geoms) {
  const out = [];
  for (let i = 0; i < geoms.length; i++) {
    out.push(geoms[i]);
    out.push(mirrorGeometry(geoms[i].clone()));
  }
  return out;
}

/**
 * Merges position / normal / uv geometries into one indexed geometry and
 * disposes the sources. Replaces the missing BufferGeometryUtils addon.
 */
function mergeGeometries(geoms) {
  let vertexCount = 0;
  let indexCount = 0;
  for (const g of geoms) {
    const count = g.attributes.position.count;
    vertexCount += count;
    indexCount += g.index ? g.index.count : count;
  }
  const positions = new Float32Array(vertexCount * 3);
  const normals = new Float32Array(vertexCount * 3);
  const uvs = new Float32Array(vertexCount * 2);
  const indices = vertexCount > 65535 ? new Uint32Array(indexCount) : new Uint16Array(indexCount);

  let vOffset = 0;
  let iOffset = 0;
  for (const g of geoms) {
    const pos = g.attributes.position;
    const nrm = g.attributes.normal;
    const uv = g.attributes.uv;
    const count = pos.count;
    positions.set(pos.array.subarray(0, count * 3), vOffset * 3);
    if (nrm) normals.set(nrm.array.subarray(0, count * 3), vOffset * 3);
    if (uv) uvs.set(uv.array.subarray(0, count * 2), vOffset * 2);
    if (g.index) {
      const src = g.index.array;
      for (let i = 0; i < src.length; i++) indices[iOffset + i] = src[i] + vOffset;
      iOffset += src.length;
    } else {
      for (let i = 0; i < count; i++) indices[iOffset + i] = vOffset + i;
      iOffset += count;
    }
    vOffset += count;
    g.dispose();
  }

  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  merged.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  merged.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  merged.setIndex(new THREE.BufferAttribute(indices, 1));
  merged.computeBoundingSphere();
  return merged;
}

/** Closed 2D outline extruded along its own normal, with a soft bevel. */
function extrudeOutline(points, depth, bevelSize) {
  const shape = new THREE.Shape();
  shape.moveTo(points[0][0], points[0][1]);
  for (let i = 1; i < points.length; i++) shape.lineTo(points[i][0], points[i][1]);
  shape.closePath();
  return new THREE.ExtrudeGeometry(shape, {
    depth,
    steps: 1,
    curveSegments: 2,
    bevelEnabled: true,
    bevelThickness: depth * 0.35,
    bevelSize,
    bevelOffset: 0,
    bevelSegments: 2,
  });
}

// ---------------------------------------------------------------------------
// Hull loft definition.
// The cross section is a chamfered wedge given in normalised coordinates:
// u in [-1, 1] across the half width, v in [0, 1] between floor and spine.
// It runs counter clockwise starting at the belly centreline.
// ---------------------------------------------------------------------------

const SECTION = [
  [0.00, 0.00], [0.62, 0.07], [1.00, 0.30], [0.86, 0.66], [0.40, 0.95],
  [0.00, 1.00], [-0.40, 0.95], [-0.86, 0.66], [-1.00, 0.30], [-0.62, 0.07],
];
const SEC_Z = [-2.60, -2.30, -1.90, -1.35, -0.70, 0.00, 0.70, 1.35, 1.90, 2.35, 2.60];
const SEC_HW = [0.03, 0.20, 0.40, 0.60, 0.74, 0.82, 0.86, 0.84, 0.78, 0.70, 0.66];
const SEC_Y0 = [0.30, 0.24, 0.18, 0.13, 0.10, 0.09, 0.09, 0.10, 0.12, 0.16, 0.19];
const SEC_Y1 = [0.36, 0.46, 0.62, 0.80, 0.94, 1.02, 1.04, 1.00, 0.94, 0.86, 0.80];

const HULL_LEN = SEC_Z[SEC_Z.length - 1] - SEC_Z[0];
const NACELLE_X = 1.15;
const NACELLE_Y = 0.50;
const NACELLE_Z = 1.15;

/** World position of section i at perimeter vertex k, interpolated by t toward k+1. */
function sectionPoint(i, k, t, offset, out) {
  const p0 = SECTION[k];
  const p1 = SECTION[(k + 1) % SECTION.length];
  const u = p0[0] + (p1[0] - p0[0]) * t;
  const v = p0[1] + (p1[1] - p0[1]) * t;
  const y0 = SEC_Y0[i];
  const y1 = SEC_Y1[i];
  let x = u * SEC_HW[i];
  let y = y0 + v * (y1 - y0);
  if (offset !== 0) {
    const cy = (y0 + y1) * 0.5;
    const dx = x;
    const dy = y - cy;
    const len = Math.hypot(dx, dy) || 1;
    x += (dx / len) * offset;
    y += (dy / len) * offset;
  }
  out.x = x;
  out.y = y;
  out.z = SEC_Z[i];
  return out;
}

/**
 * The shell is built one perimeter facet at a time: normals stay smooth along
 * the craft but break cleanly on the chines, which is what gives the hull its
 * faceted racer look without flat shading the whole mesh.
 */
function buildHullShell() {
  const geoms = [];
  const sections = SEC_Z.length;
  const edges = SECTION.length;
  const a = { x: 0, y: 0, z: 0 };
  const b = { x: 0, y: 0, z: 0 };

  for (let k = 0; k < edges; k++) {
    const positions = [];
    const uvs = [];
    const indices = [];
    for (let i = 0; i < sections; i++) {
      sectionPoint(i, k, 0, 0, a);
      sectionPoint(i, k, 1, 0, b);
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      const v = (SEC_Z[i] - SEC_Z[0]) / HULL_LEN;
      uvs.push(k / edges, v, (k + 1) / edges, v);
    }
    for (let i = 0; i < sections - 1; i++) {
      const i0 = 2 * i;
      indices.push(i0, i0 + 1, i0 + 3, i0, i0 + 3, i0 + 2);
    }
    geoms.push(makeGeometry(positions, uvs, indices));
  }

  // Nose point and recessed tail plate close the shell.
  geoms.push(buildCap(0, true, -0.06));
  geoms.push(buildCap(sections - 1, false, -0.10));
  return geoms;
}

function buildCap(i, isNose, zShift) {
  const positions = [];
  const uvs = [];
  const indices = [];
  const p = { x: 0, y: 0, z: 0 };
  positions.push(0, (SEC_Y0[i] + SEC_Y1[i]) * 0.5, SEC_Z[i] + zShift);
  uvs.push(0.5, 0.5);
  for (let k = 0; k < SECTION.length; k++) {
    sectionPoint(i, k, 0, 0, p);
    positions.push(p.x, p.y, p.z);
    uvs.push(0.5 + SECTION[k][0] * 0.45, 0.5 + (SECTION[k][1] - 0.5) * 0.9);
  }
  for (let k = 0; k < SECTION.length; k++) {
    const v0 = 1 + k;
    const v1 = 1 + ((k + 1) % SECTION.length);
    if (isNose) indices.push(0, v1, v0);
    else indices.push(0, v0, v1);
  }
  return makeGeometry(positions, uvs, indices);
}

/** Thin ribbon following the hull skin, used for the emissive livery stripes. */
function buildStripe(k, tA, tB, offset, first, last) {
  const positions = [];
  const uvs = [];
  const indices = [];
  const a = { x: 0, y: 0, z: 0 };
  const b = { x: 0, y: 0, z: 0 };
  const span = last - first;
  for (let i = first; i <= last; i++) {
    sectionPoint(i, k, tA, offset, a);
    sectionPoint(i, k, tB, offset, b);
    positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    const v = (i - first) / span;
    uvs.push(0, v, 1, v);
  }
  for (let i = 0; i < span; i++) {
    const i0 = 2 * i;
    indices.push(i0, i0 + 1, i0 + 3, i0, i0 + 3, i0 + 2);
  }
  return makeGeometry(positions, uvs, indices);
}

/** Outboard engine pod: a lathe with a pointed intake and a flared nozzle lip. */
function buildNacelle() {
  const profile = [
    new THREE.Vector2(0.000, -1.35),
    new THREE.Vector2(0.130, -1.26),
    new THREE.Vector2(0.240, -1.08),
    new THREE.Vector2(0.310, -0.76),
    new THREE.Vector2(0.340, -0.18),
    new THREE.Vector2(0.340, 0.45),
    new THREE.Vector2(0.320, 0.86),
    new THREE.Vector2(0.300, 1.12),
    new THREE.Vector2(0.335, 1.24),
    new THREE.Vector2(0.265, 1.30),
    new THREE.Vector2(0.245, 1.22),
  ];
  const geom = new THREE.LatheGeometry(profile, 22);
  geom.rotateX(Math.PI / 2); // lathe axis +Y becomes +Z
  geom.translate(NACELLE_X, NACELLE_Y, NACELLE_Z);
  return geom;
}

function buildWing() {
  const geom = extrudeOutline([
    [0.55, 1.30], [1.45, -0.30], [1.50, -1.15], [0.55, -1.35],
  ], 0.13, 0.04);
  geom.rotateX(-Math.PI / 2); // outline y becomes -Z, extrusion becomes +Y
  geom.translate(0, 0.40, 0);
  return geom;
}

function buildCanard() {
  const geom = extrudeOutline([
    [0.28, 1.62], [0.86, 1.20], [0.88, 0.92], [0.28, 0.82],
  ], 0.07, 0.025);
  geom.rotateX(-Math.PI / 2);
  geom.translate(0, 0.56, 0);
  geom.rotateZ(-0.13); // slight anhedral, tip down
  return geom;
}

function buildFin() {
  const geom = extrudeOutline([
    [-1.45, 0.00], [-2.05, 0.62], [-2.42, 0.64], [-2.50, 0.02],
  ], 0.07, 0.02);
  geom.rotateY(Math.PI / 2); // outline x becomes -Z, extrusion becomes +X
  geom.translate(-0.035, 0, 0);
  geom.rotateZ(-0.10); // cants the tip outboard
  geom.translate(NACELLE_X, 0.70, 0);
  return geom;
}

function buildNozzleThroat() {
  const cone = new THREE.CylinderGeometry(0.235, 0.09, 0.34, 20, 1, true);
  cone.rotateX(Math.PI / 2); // wide mouth ends up toward +Z
  cone.translate(NACELLE_X, NACELLE_Y, NACELLE_Z + 1.15);
  return cone;
}

/** Hot disc closing the narrow end of the throat, deep inside the nozzle. */
function buildNozzleCore() {
  const disc = new THREE.CircleGeometry(0.092, 20);
  disc.translate(NACELLE_X, NACELLE_Y, NACELLE_Z + 0.99);
  return disc;
}

/** Height of the belly skin at (x, z), used to sit the hover pads on it. */
function bellyY(x, z) {
  let i = 0;
  while (i < SEC_Z.length - 2 && SEC_Z[i + 1] < z) i++;
  const span = SEC_Z[i + 1] - SEC_Z[i];
  const t = clamp01(span > 0 ? (z - SEC_Z[i]) / span : 0);
  const hw = lerp(SEC_HW[i], SEC_HW[i + 1], t);
  const y0 = lerp(SEC_Y0[i], SEC_Y0[i + 1], t);
  const y1 = lerp(SEC_Y1[i], SEC_Y1[i + 1], t);
  // Between the belly centreline and the lower chine the section rises linearly.
  const u = clamp01(Math.abs(x) / (hw * SECTION[1][0]));
  return y0 + u * SECTION[1][1] * (y1 - y0);
}

function buildHoverPad(x, z, radius) {
  const pad = new THREE.CircleGeometry(radius, 14);
  pad.rotateX(Math.PI / 2); // faces -Y
  pad.translate(x, bellyY(x, z) - 0.012, z);
  return pad;
}

// ---------------------------------------------------------------------------
// Mesh
// ---------------------------------------------------------------------------

/**
 * Builds one racer. `color` is the livery hex used by the emissive trim.
 * Returns a Group whose userData carries `thrusters` and `glowMaterials`.
 */
/**
 * Adds a fresnel rim term to a standard material. On a night circuit the craft
 * is silhouetted against black asphalt, so the rim is what actually reads its
 * shape: it costs no extra light and never leaves the hull invisible.
 */
function addRimLight(material, color, strength) {
  const rimColor = new THREE.Color(color).lerp(new THREE.Color(PALETTE.white), 0.35);
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uRimColor = { value: rimColor };
    shader.uniforms.uRimStrength = { value: strength };
    shader.fragmentShader = shader.fragmentShader
      .replace(
        'void main() {',
        'uniform vec3 uRimColor;\nuniform float uRimStrength;\nvoid main() {',
      )
      .replace(
        '#include <emissivemap_fragment>',
        '#include <emissivemap_fragment>\n\tfloat rimFactor = 1.0 - saturate( dot( normalize( normal ), normalize( vViewPosition ) ) );\n\ttotalEmissiveRadiance += uRimColor * pow( rimFactor, 2.6 ) * uRimStrength;',
      );
  };
  material.customProgramCacheKey = () => 'velocitron-rim';
}

export function createShipMesh(textures, color) {
  const tex = textures || {};
  const livery = new THREE.Color(color === undefined ? PALETTE.liveries[0] : color);

  const hullMat = new THREE.MeshStandardMaterial({
    color: 0xa8b2c4,
    map: tex.hull || null,
    normalMap: tex.hullNormal || null,
    emissive: livery,
    emissiveMap: tex.hullEmissive || null,
    emissiveIntensity: tex.hullEmissive ? 1.5 : 0.0,
    // A near black night sky means a fully metallic hull reflects nothing and
    // renders black. Keep enough diffuse for the key light to model the shape.
    metalness: 0.55,
    roughness: 0.34,
    envMapIntensity: 1.9,
  });
  if (hullMat.normalMap) hullMat.normalScale.set(1.1, 1.1);
  addRimLight(hullMat, livery, 0.8);

  const glowMat = new THREE.MeshStandardMaterial({
    color: 0x05070c,
    emissive: livery,
    emissiveIntensity: 2.4,
    metalness: 0.2,
    roughness: 0.4,
    side: THREE.DoubleSide,
  });

  const coreColor = new THREE.Color(PALETTE.thrustCore).lerp(livery, 0.35);
  const coreMat = new THREE.MeshStandardMaterial({
    color: 0x02040a,
    emissive: coreColor,
    emissiveIntensity: 3.4,
    metalness: 0.0,
    roughness: 0.5,
    side: THREE.DoubleSide,
  });

  const canopyMat = new THREE.MeshStandardMaterial({
    color: 0x0b1020,
    map: tex.cockpit || null,
    emissive: livery,
    emissiveIntensity: 0.35,
    metalness: 0.9,
    roughness: 0.08,
    envMapIntensity: 1.8,
    transparent: true,
    opacity: 0.86,
  });

  // ---- hull shell, centre parts then mirrored outboard parts ----
  const hullCentre = buildHullShell();

  // Canopy fairing and spine blister sit on the raised centreline.
  const spine = new THREE.SphereGeometry(1, 18, 8, 0, Math.PI * 2, 0, Math.PI * 0.5);
  spine.scale(0.23, 0.17, 1.05);
  spine.translate(0, 0.94, 0.85);
  hullCentre.push(spine);

  const collar = new THREE.CylinderGeometry(0.40, 0.44, 0.10, 20, 1, true);
  collar.rotateX(Math.PI / 2);
  collar.scale(1.0, 0.72, 1.0);
  collar.translate(0, 0.92, -0.55);
  hullCentre.push(collar);

  const hullRight = [buildNacelle(), buildWing(), buildCanard(), buildFin()];
  const hullGeom = mergeGeometries(hullCentre.concat(withMirror(hullRight)));

  const hull = new THREE.Mesh(hullGeom, hullMat);
  hull.castShadow = true;
  hull.receiveShadow = false;

  // ---- emissive trim ----
  const glowRight = [
    buildStripe(2, 0.15, 0.32, 0.018, 1, 9),   // flank stripe, full length
    buildStripe(4, 0.28, 0.52, 0.015, 2, 8),   // spine stripe
    buildStripe(1, 0.30, 0.52, 0.016, 0, 3),   // nose flash
    buildHoverPad(0.52, -0.95, 0.15),
    buildHoverPad(0.62, 1.25, 0.17),
  ];
  const glowGeom = mergeGeometries(withMirror(glowRight));
  const glow = new THREE.Mesh(glowGeom, glowMat);
  glow.castShadow = false;
  glow.receiveShadow = false;

  const coreGeom = mergeGeometries(withMirror([buildNozzleThroat(), buildNozzleCore()]));
  const cores = new THREE.Mesh(coreGeom, coreMat);
  cores.castShadow = false;
  cores.receiveShadow = false;

  // ---- canopy ----
  const canopyGeom = new THREE.SphereGeometry(1, 20, 10, 0, Math.PI * 2, 0, Math.PI * 0.52);
  canopyGeom.scale(0.34, 0.27, 0.86);
  canopyGeom.translate(0, 0.90, -0.60);
  const canopy = new THREE.Mesh(canopyGeom, canopyMat);
  canopy.castShadow = false;
  canopy.receiveShadow = false;

  const group = new THREE.Group();
  group.name = 'ship';
  group.add(hull, glow, cores, canopy);

  const thrusterL = new THREE.Object3D();
  thrusterL.position.set(-NACELLE_X, NACELLE_Y, NACELLE_Z + 1.32);
  const thrusterR = new THREE.Object3D();
  thrusterR.position.set(NACELLE_X, NACELLE_Y, NACELLE_Z + 1.32);
  group.add(thrusterL, thrusterR);

  group.userData.thrusters = [thrusterL, thrusterR];
  group.userData.glowMaterials = [glowMat, coreMat];
  group.userData.color = livery.getHex();
  group.userData.dispose = () => disposeShipMesh(group);
  return group;
}

/** Frees the geometries and materials owned by a ship mesh (never its textures). */
export function disposeShipMesh(mesh) {
  if (!mesh) return;
  mesh.traverse((node) => {
    if (!node.isMesh) return;
    node.geometry.dispose();
    node.material.dispose();
  });
}

// ---------------------------------------------------------------------------
// World transform
// ---------------------------------------------------------------------------

const WORLD_UP = new THREE.Vector3(0, 1, 0);
const _fwd = new THREE.Vector3();
const _rgt = new THREE.Vector3();
const _up = new THREE.Vector3();
const _back = new THREE.Vector3();
const _basis = new THREE.Matrix4();
const _qRoll = new THREE.Quaternion();
const _qPitch = new THREE.Quaternion();

/**
 * Rebuilds worldPos / quat / mesh transform from the track state.
 * Basis = (right, up, backward) taken from the track frame rotated by yaw,
 * then rolled about the forward axis and pitched about the right axis.
 */
function applyTransform(ship, track) {
  if (!ship._frame) ship._frame = track.makeFrame();
  const frame = track.at(ship.s, ship._frame);
  track.toWorld(ship.s, ship.x, ship.h, ship.worldPos);

  const cy = Math.cos(ship.yaw);
  const sy = Math.sin(ship.yaw);
  _fwd.copy(frame.tangent).multiplyScalar(cy).addScaledVector(frame.right, sy);
  if (_fwd.lengthSq() < 1e-8) _fwd.set(0, 0, -1);
  _fwd.normalize();

  _rgt.crossVectors(_fwd, frame.up);
  if (_rgt.lengthSq() < 1e-8) _rgt.crossVectors(_fwd, WORLD_UP);
  _rgt.normalize();

  _back.copy(_fwd).negate();
  _up.crossVectors(_back, _rgt).normalize();

  _basis.makeBasis(_rgt, _up, _back);
  ship.quat.setFromRotationMatrix(_basis);
  _qRoll.setFromAxisAngle(_fwd, ship.roll);
  _qPitch.setFromAxisAngle(_rgt, ship.pitch);
  ship.quat.premultiply(_qRoll).premultiply(_qPitch);

  ship.mesh.position.copy(ship.worldPos);
  ship.mesh.quaternion.copy(ship.quat);
}

// ---------------------------------------------------------------------------
// Ship state
// ---------------------------------------------------------------------------

/**
 * Creates a racer. opts = { track, textures, index, isPlayer, name, color }.
 */
export function createShip(opts) {
  const o = opts || {};
  const track = o.track || null;
  const index = o.index || 0;
  const color = o.color === undefined
    ? PALETTE.liveries[index % PALETTE.liveries.length]
    : o.color;
  const mesh = createShipMesh(o.textures, color);
  mesh.name = o.isPlayer ? 'ship-player' : 'ship-' + index;

  const ship = {
    index,
    name: o.name || (o.isPlayer ? 'JOUEUR' : 'PILOTE ' + (index + 1)),
    isPlayer: !!o.isPlayer,
    color,
    mesh,

    // track space state
    s: track ? finite(track.startS, 0) : 0,
    x: 0,
    h: SHIP.hoverHeight,
    yaw: 0,

    // velocities
    speed: 0,
    vLat: 0,
    vh: 0,

    // cosmetic attitude
    roll: 0,
    pitch: 0,

    shield: SHIP.shieldMax,
    boostEnergy: 100,
    boostTimer: 0,
    padBoostTimer: 0,

    lap: 0,
    lastCheckpoint: -1,
    finished: false,
    finishTime: null,
    lapStartTime: 0,
    lapTimes: [],
    bestLap: null,
    totalProgress: 0,

    destroyed: false,
    respawnTimer: 0,

    worldPos: new THREE.Vector3(),
    quat: new THREE.Quaternion(),

    // derived read-only helpers for hud / audio / fx
    speed01: 0,
    boostReady: true,
    airborne: false,
    onPad: false,
    boosting: false,

    events: {
      wallHit: 0,
      padHit: false,
      land: 0,
      shipHit: 0,
      boost: false,
      destroyed: false,
      respawned: false,
    },

    _frame: track ? track.makeFrame() : null,
  };

  ship.dispose = () => disposeShipMesh(mesh);

  if (track) {
    ship.totalProgress = ship.s;
    applyTransform(ship, track);
  }
  return ship;
}

// ---------------------------------------------------------------------------
// Flight model
// ---------------------------------------------------------------------------

/**
 * Integrates one craft for dt seconds. `controls` is the reusable object
 * described in the contract; passing null flies the craft with no input.
 * ship.events is cleared here, so callers read it after the call.
 */
export function updateShip(ship, controls, dt, track) {
  const ev = ship.events;
  ev.wallHit = 0;
  ev.padHit = false;
  ev.land = 0;
  ev.shipHit = 0;
  ev.boost = false;
  ev.destroyed = false;
  ev.respawned = false;

  if (!track) return;
  const c = controls || NEUTRAL_CONTROLS;
  const step = clamp(finite(dt, 0), 0, MAX_DT);

  // Wrecked craft: coast to a stop, then drop back on the racing line.
  if (ship.destroyed) {
    ship.respawnTimer -= step;
    ship.speed *= Math.max(0, 1 - 3 * step);
    if (ship.respawnTimer <= 0) respawnShip(ship, track);
    else applyTransform(ship, track);
    ship.speed01 = clamp01(Math.abs(ship.speed) / SHIP.maxSpeed);
    ship.totalProgress = ship.lap * track.length + ship.s;
    return;
  }

  // Turbo trigger: ignored when the tank is too low or a boost is already lit.
  if (c.boost && ship.boostTimer <= 0 && ship.boostEnergy >= SHIP.boostCost) {
    ship.boostEnergy -= SHIP.boostCost;
    ship.boostTimer = SHIP.boostDuration;
    ev.boost = true;
  }

  if (!ship._frame) ship._frame = track.makeFrame();
  const frame = track.at(ship.s, ship._frame);
  const curvature = finite(frame.curvature, 0);
  const vertCurvature = finite(frame.vertCurvature, 0);
  const roll = finite(frame.roll, 0);
  const halfWidth = finite(frame.halfWidth, TRACK.halfWidthDefault);

  const airL = c.airLeft ? 1 : 0;
  const airR = c.airRight ? 1 : 0;
  const steer = clamp(finite(c.steer, 0), -1, 1);
  const throttle = clamp01(finite(c.thrust, 0));
  const brake = clamp01(finite(c.brake, 0));
  const prevSpeed = ship.speed;

  // 1 - longitudinal
  const cap = (ship.boostTimer > 0 || ship.padBoostTimer > 0)
    ? SHIP.boostMaxSpeed
    : SHIP.maxSpeed;
  // Thrust fades out over the last 10 % before the cap. A pure soft return
  // never wins against a constant thrust and the craft settles well above it.
  const nearCap = clamp01((Math.abs(ship.speed) - cap * 0.9) / (cap * 0.1));
  let accel = SHIP.thrust * throttle * (1 - nearCap);
  accel -= SHIP.brakeForce * brake;
  if (ship.boostTimer > 0) accel += SHIP.boostAccel * (1 - nearCap);
  if (ship.padBoostTimer > 0) accel += SHIP.padBoostAccel * (1 - nearCap);
  let speed = ship.speed + accel * step;
  // Drag opposes the motion. Subtracting it unsigned makes a craft sitting on
  // the grid accelerate backwards on its own during the countdown.
  const dragAccel = (SHIP.drag * speed * speed + SHIP.rollingDrag) * step;
  if (speed > 0) speed = Math.max(0, speed - dragAccel);
  else if (speed < 0) speed = Math.min(0, speed + dragAccel);
  speed -= SHIP.airbrakeDrag * speed * (airL + airR) * 0.5 * step;
  // Soft return, so the overshoot left by an expiring boost bleeds off instead
  // of being cut dead.
  if (speed > cap) speed += (cap - speed) * Math.min(1, 2.5 * step);
  speed = Math.max(speed, SHIP.reverseSpeed);

  // 2 - heading, relative to the track tangent
  const authority = SHIP.steerRate
    * lerp(1, SHIP.steerSpeedFalloff, clamp01(Math.abs(speed) / SHIP.maxSpeed));
  let yaw = ship.yaw + steer * authority * step;
  yaw += (airR - airL) * SHIP.airbrakeYaw * step;
  yaw -= yaw * SHIP.yawDamping * step;
  yaw = clamp(yaw, -1.0, 1.0);

  // 3 - lateral drift.
  // The cornering load is what makes a corner a corner: without it the yaw
  // damping realigns the craft on the tangent for free and the whole circuit is
  // flat out with no input. Positive curvature turns right, so the load pushes
  // toward -x. The track banking cancels part of it, which is exactly why the
  // banked 180 can be taken far faster than the flat hairpin.
  const load = speed * speed * curvature * SHIP.corneringLoad
    - SHIP.gravity * Math.sin(roll);
  let vLat = ship.vLat - load * step;
  // The airbrake pushes toward the outside of the corner it opens, so it reads
  // as a drift rather than as a second steering axis.
  vLat -= (airR - airL) * SHIP.airbrakeSlide * step;
  vLat += speed * Math.sin(yaw) * SHIP.slideFromYaw * step;
  vLat -= vLat * SHIP.gripLateral * step;
  let x = ship.x + (speed * Math.sin(yaw) + vLat) * step;

  // 4 - curvilinear abscissa, corrected for the longer outer edge
  const denom = Math.max(0.25, 1 - x * curvature);
  let s = track.wrapS(ship.s + speed * Math.cos(yaw) * step / denom);

  // 5 - hover height, crests throw the craft in the air
  let vh = ship.vh - speed * speed * vertCurvature * step;
  let h = ship.h;
  if (h < SHIP.hoverHeight * 2.2) {
    vh += ((SHIP.hoverHeight - h) * SHIP.hoverStiffness - vh * SHIP.hoverDamping) * step;
  } else {
    vh -= SHIP.gravity * step;
  }
  h += vh * step;
  if (h < 0.05) {
    if (vh < -6) ev.land = -vh;
    h = 0.05;
    vh = 0;
  }

  // 6 - walls
  const limit = Math.max(0.5, halfWidth - SHIP.halfWidth);
  if (Math.abs(x) > limit) {
    const impact = Math.abs(speed * Math.sin(yaw) + vLat);
    x = (x > 0 ? 1 : -1) * limit;
    vLat = -0.22 * vLat;
    yaw *= 0.35;
    if (impact > 6) {
      speed -= speed * SHIP.wallSpeedLoss * clamp01(impact / 30);
      ship.shield -= impact * SHIP.wallDamageScale;
      ev.wallHit = impact;
    } else {
      speed -= SHIP.wallScrapeDrag * step;
      ship.shield -= impact * SHIP.wallDamageScale * 0.25 * step * 10;
      ev.wallHit = Math.max(ev.wallHit, impact * 0.3);
    }
  }

  ship.speed = speed;
  ship.yaw = yaw;
  ship.vLat = vLat;
  ship.x = x;
  ship.s = track.wrapS(s);
  ship.h = h;
  ship.vh = vh;

  // Boost pads refresh the pad timer for as long as the craft stays on them.
  const onPad = typeof track.padAt === 'function' ? !!track.padAt(ship.s, ship.x) : false;
  if (onPad) {
    ship.padBoostTimer = SHIP.padBoostDuration;
    if (!ship.onPad) ev.padHit = true;
  } else {
    ship.padBoostTimer = Math.max(0, ship.padBoostTimer - step);
  }
  ship.onPad = onPad;
  ship.boostTimer = Math.max(0, ship.boostTimer - step);
  ship.boostEnergy = Math.min(100, ship.boostEnergy + SHIP.boostRegen * step);

  // Numerical safety net: a broken frame must never poison the whole race.
  if (!Number.isFinite(ship.speed) || !Number.isFinite(ship.x)
    || !Number.isFinite(ship.h) || !Number.isFinite(ship.yaw)
    || !Number.isFinite(ship.s)) {
    respawnShip(ship, track);
    ship.totalProgress = ship.lap * track.length + ship.s;
    return;
  }

  // Destruction
  if (ship.shield <= 0) {
    ship.shield = 0;
    ship.destroyed = true;
    ship.respawnTimer = SHIP.respawnTime;
    ship.boostTimer = 0;
    ship.padBoostTimer = 0;
    ship.mesh.visible = false;
    ev.destroyed = true;
  } else if (ship.shield > SHIP.shieldMax) {
    ship.shield = SHIP.shieldMax;
  }

  // Cosmetic attitude
  const dv = step > 0 ? (ship.speed - prevSpeed) / step : 0;
  const targetRoll = clamp(steer * SHIP.bankPerSteer + ship.vLat * SHIP.bankPerSlide, -0.75, 0.75);
  const targetPitch = clamp(
    clamp(dv * SHIP.pitchPerAccel, -0.22, 0.22) + clamp(ship.vh * 0.02, -0.18, 0.18),
    -0.35, 0.35,
  );
  const bodyBlend = Math.min(1, SHIP.bodyLerp * step);
  ship.roll += (targetRoll - ship.roll) * bodyBlend;
  ship.pitch += (targetPitch - ship.pitch) * bodyBlend;

  ship.speed01 = clamp01(Math.abs(ship.speed) / SHIP.maxSpeed);
  ship.boostReady = ship.boostEnergy >= SHIP.boostCost;
  ship.boosting = ship.boostTimer > 0 || ship.padBoostTimer > 0;
  ship.airborne = ship.h > SHIP.hoverHeight * 2.2;

  applyTransform(ship, track);
  ship.totalProgress = ship.lap * track.length + ship.s;
}

/** Drops the craft back on the track at its current abscissa, fully repaired. */
export function respawnShip(ship, track) {
  if (!track) return;
  if (!Number.isFinite(ship.s)) ship.s = finite(track.startS, 0);
  ship.s = track.wrapS(ship.s);
  if (!ship._frame) ship._frame = track.makeFrame();

  const frame = track.at(ship.s, ship._frame);
  const limit = Math.max(0.5, finite(frame.halfWidth, TRACK.halfWidthDefault) - SHIP.halfWidth);
  const prevX = Number.isFinite(ship.x) ? ship.x : 0;

  ship.x = clamp(prevX * 0.35, -limit, limit);
  ship.h = SHIP.hoverHeight * 1.8;
  ship.yaw = 0;
  ship.vLat = 0;
  ship.vh = 0;
  ship.speed = RESPAWN_SPEED;
  ship.roll = 0;
  ship.pitch = 0;
  ship.shield = SHIP.shieldMax;
  ship.boostTimer = 0;
  ship.padBoostTimer = 0;
  ship.onPad = false;
  ship.boosting = false;
  ship.airborne = false;
  ship.destroyed = false;
  ship.respawnTimer = 0;
  ship.mesh.visible = true;
  ship.events.respawned = true;

  applyTransform(ship, track);
  ship.totalProgress = ship.lap * track.length + ship.s;
}

// ---------------------------------------------------------------------------
// Ship to ship collisions
// ---------------------------------------------------------------------------

let _collFrame = null;
let _collTrack = null;

function collisionFrame(track) {
  if (_collTrack !== track) {
    _collFrame = track.makeFrame();
    _collTrack = track;
  }
  return _collFrame;
}

function clampInsideWalls(ship, track, frame) {
  const f = track.at(ship.s, frame);
  const limit = Math.max(0.5, finite(f.halfWidth, TRACK.halfWidthDefault) - SHIP.halfWidth);
  ship.x = clamp(ship.x, -limit, limit);
}

/**
 * Symmetric separation plus a lateral impulse exchange for every overlapping
 * pair. Called once per frame by race.js, after all the ships were updated.
 */
export function resolveShipCollisions(ships, track, dt) {
  if (!ships || ships.length < 2 || !track) return;
  // Sustained contact is a rate, not an impulse: without the timestep a pair
  // rubbing side by side injects sixty pushes and sixty damage ticks a second,
  // and the whole thing scales with the frame rate.
  const step = Number.isFinite(dt) && dt > 0 ? Math.min(dt, 1 / 20) : 1 / 60;
  const frame = collisionFrame(track);

  for (let i = 0; i < ships.length; i++) {
    const a = ships[i];
    if (!a || a.destroyed) continue;
    for (let j = i + 1; j < ships.length; j++) {
      const b = ships[j];
      if (!b || b.destroyed) continue;

      const ds = track.deltaS(a.s, b.s);
      if (!Number.isFinite(ds) || Math.abs(ds) >= SHIP.length) continue;
      const dx = b.x - a.x;
      if (Math.abs(dx) >= SHIP.width) continue;

      const dir = dx >= 0 ? 1 : -1;
      const overlap = SHIP.width - Math.abs(dx);
      a.x -= dir * overlap * 0.5;
      b.x += dir * overlap * 0.5;

      const aLat = a.speed * Math.sin(a.yaw) + a.vLat;
      const bLat = b.speed * Math.sin(b.yaw) + b.vLat;
      const rel = bLat - aLat;
      let impact = Math.abs(rel);
      // A real collision is an impulse and stays one; a pair that is already
      // parting is just rubbing, so its push and its damage are per second.
      const closing = rel * dir < 0;
      if (closing) {
        const impulse = -(1 + BUMP_RESTITUTION) * rel * 0.5;
        a.vLat -= impulse;
        b.vLat += impulse;
      } else {
        a.vLat -= dir * BUMP_PUSH * step;
        b.vLat += dir * BUMP_PUSH * step;
        impact *= 0.35;
      }
      impact += Math.abs(a.speed - b.speed) * 0.25;

      if (impact > 1.5) {
        const damage = closing
          ? impact * SHIP.shipDamageScale
          : impact * SHIP.shipRubScale * step;
        a.shield -= damage;
        b.shield -= damage;
        a.events.shipHit = Math.max(a.events.shipHit, impact);
        b.events.shipHit = Math.max(b.events.shipHit, impact);
        const scrub = closing
          ? Math.min(impact * 0.12, 6)
          : Math.min(impact * 0.12, 6) * step * 6;
        a.speed = Math.max(a.speed - scrub, SHIP.reverseSpeed);
        b.speed = Math.max(b.speed - scrub, SHIP.reverseSpeed);
      }

      clampInsideWalls(a, track, frame);
      clampInsideWalls(b, track, frame);
      applyTransform(a, track);
      applyTransform(b, track);
    }
  }
}
