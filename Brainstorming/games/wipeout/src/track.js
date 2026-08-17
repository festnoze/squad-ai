/**
 * VELOCITRON - CIRCUIT AKARI.
 *
 * The circuit is the backbone of the game: physics, AI, camera, world dressing
 * and HUD all query it. It is defined by a hand authored list of control points
 * fed to a closed centripetal Catmull-Rom curve, then resampled at constant arc
 * length into flat typed arrays so that `at()` is a plain index lookup.
 *
 * The layout, in order of travel:
 *   1. wide flat start / finish straight (~450 m)
 *   2. fast left / right chicane
 *   3. long 180 banked to 45 degrees
 *   4. climb into a 180 m tunnel that exits downhill
 *   5. launch crest
 *   6. fast banked sweeper on a viaduct over the void
 *   7. slow technical double apex, narrowed to TRACK.halfWidthMin
 *   8. run back to the line over two boost pads
 *
 * Verified offline on 2000 equal arc length samples:
 *   length 4002.0 m, min horizontal radius 70.0 m, max slope 15.07 %,
 *   min XZ self distance 147.6 m (no crossing), max |vertCurvature| 0.0102 1/m.
 */

import * as THREE from 'three';
import { TRACK, PALETTE } from './config.js';

// ---------------------------------------------------------------------------
// Hand authored control points.
// [ x, y, z, halfWidth, bankDegrees, tag ]
// The bank sign follows the turn direction (positive = right hander, which
// lifts the left edge). The raw coordinates were authored around the centre of
// a 1707 x 503 m plot, then shifted by CENTRE_* so the circuit sits on the
// world origin.
// ---------------------------------------------------------------------------
const CENTRE_X = 304.5;
const CENTRE_Z = -480.5;

const CONTROL = [
  // 1 - wide flat start / finish straight
  [-800, 0, 730, 14.0, 0, 'start'],
  [-680, 0, 730, 14.0, 0, ''],
  [-560, 0, 730, 13.5, 0, ''],
  [-440, 0, 730, 13.0, 0, ''],
  [-350, 0, 730, 12.5, -2, ''],
  // 2 - fast left / right chicane
  [-270, 0, 722, 12.0, -8, ''],
  [-190, 0, 700, 11.5, 2, ''],
  [-100, 0, 696, 11.5, 9, ''],
  [-20, 0, 718, 11.5, -4, ''],
  [60, 0, 730, 12.0, 0, ''],
  [170, 2, 730, 12.5, 0, ''],
  // 3 - long banked 180
  [300, 4, 730, 13.0, -8, ''],
  [406, 5, 707, 13.0, -26, ''],
  [492, 6, 641, 13.0, -42, ''],
  [542, 7, 545, 13.0, -45, ''],
  [541, 7, 415, 13.0, -45, ''],
  [492, 7, 319, 13.0, -40, ''],
  [406, 7, 253, 12.5, -22, ''],
  [300, 8, 230, 12.5, -8, ''],
  // 4 - climb into the tunnel, exit downhill
  [190, 14, 231, 12.5, 0, ''],
  [80, 25, 232, 12.0, 0, ''],
  [-20, 36, 233, 12.0, 0, ''],
  [-70, 42, 233, 11.0, 0, 'tunnelIn'],
  [-160, 46, 234, 11.0, 0, ''],
  [-250, 43, 235, 11.0, 0, 'tunnelOut'],
  [-340, 36, 234, 11.5, 0, ''],
  [-430, 30, 233, 12.0, 0, ''],
  [-520, 25, 232, 12.0, 0, ''],
  [-600, 22, 231, 12.0, 0, ''],
  // 5 - launch crest
  [-640, 26.8, 231, 12.0, 0, ''],
  [-670, 30.4, 231, 12.0, 0, ''],
  [-688, 31.8, 231, 12.0, 0, 'crest'],
  [-706, 30.9, 231, 12.0, 0, ''],
  [-736, 27.3, 230, 12.0, 0, ''],
  [-770, 23.2, 230, 12.0, 0, ''],
  // 6 - fast banked sweeper over the void
  [-800, 20, 230, 12.5, -6, 'viaIn'],
  [-847, 20, 231.3, 12.5, -15, ''],
  [-893.3, 20, 238.8, 12.5, -19, ''],
  [-937.9, 20, 253.4, 12.5, -20, ''],
  [-979.7, 20, 274.8, 12.5, -20, ''],
  [-1017.7, 20, 302.4, 12.5, -21, ''],
  [-1050.8, 20, 335.7, 12.5, -22, ''],
  [-1078.4, 20, 373.7, 12.5, -23, ''],
  [-1099.7, 20, 415.5, 12.5, -24, ''],
  [-1114.3, 19, 457, 11.7, -14, ''],
  [-1126.6, 17.2, 495.1, 11.1, -9, ''],
  [-1138.9, 15.4, 533.1, 10.5, -6, 'viaOut'],
  [-1142, 14.9, 542.7, 10.3, -5, ''],
  // 7 - slow technical double apex
  [-1148.8, 13.9, 563.6, 9.9, -7, ''],
  [-1154.9, 12.2, 584.7, 9.2, -12, ''],
  [-1157.6, 10.7, 606.5, 8.5, -18, ''],
  [-1155, 9.5, 628.3, 8.0, -21, ''],
  [-1147.4, 8.3, 648.9, 8.0, -16, ''],
  [-1137.1, 7.3, 668.4, 8.0, -12, ''],
  [-1125.1, 6.3, 686.7, 8.0, -10, ''],
  [-1111, 5.4, 703.6, 8.0, -14, ''],
  [-1093.9, 4.6, 717.3, 8.0, -17, ''],
  [-1073.8, 3.9, 726.1, 8.0, -21, ''],
  [-1052.1, 3.2, 729.8, 8.4, -17, ''],
  // 8 - run back to the line
  [-1030.1, 2.5, 730.2, 9.0, -10, ''],
  [-979.1, 1.7, 729.7, 10.3, -5, ''],
  [-934.1, 1.1, 729.3, 11.5, -3, ''],
  [-889.1, 0.6, 728.8, 12.6, -3, ''],
];

// Boost pad placement, as a fraction of the total length, with the lateral
// offset of the pad centre in metres. Two of them sit on the run back to the
// line as required by the layout brief.
const PAD_SPEC = [
  { at: 0.225, x: 2 },
  { at: 0.44, x: 0 },
  { at: 0.645, x: -3 },
  { at: 0.957, x: 0 },
  { at: 0.98, x: 0 },
];

const ARC_DIVISIONS = 12000;
const OUTLINE_POINTS = 240;
const DEG = Math.PI / 180;

// ---------------------------------------------------------------------------
// Small helpers (build time only)
// ---------------------------------------------------------------------------

function catmullScalar(a0, a1, a2, a3, t) {
  const v0 = (a2 - a0) * 0.5;
  const v1 = (a3 - a1) * 0.5;
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    (2 * a1 - 2 * a2 + v0 + v1) * t3 + (-3 * a1 + 3 * a2 - 2 * v0 - v1) * t2 + v0 * t + a1
  );
}

/** Circular box blur, used to take the edge off the per control point values. */
function smoothCircular(src, radius, passes) {
  const n = src.length;
  let a = src;
  const b = new Float32Array(n);
  for (let p = 0; p < passes; p++) {
    for (let i = 0; i < n; i++) {
      let sum = 0;
      for (let k = -radius; k <= radius; k++) sum += a[(i + k + n * 2) % n];
      b[i] = sum / (radius * 2 + 1);
    }
    a.set(b);
  }
  return a;
}

/**
 * Accumulates triangles from several sources into one BufferGeometry so the
 * whole circuit renders in a handful of draw calls.
 */
class MeshBuilder {
  constructor(withColour) {
    this.pos = [];
    this.nor = [];
    this.uv = [];
    this.col = withColour ? [] : null;
    this.idx = [];
  }

  get count() {
    return this.pos.length / 3;
  }

  vertex(x, y, z, nx, ny, nz, u, v, cr, cg, cb) {
    const i = this.pos.length / 3;
    this.pos.push(x, y, z);
    this.nor.push(nx, ny, nz);
    this.uv.push(u, v);
    if (this.col) this.col.push(cr, cg, cb);
    return i;
  }

  quad(a, b, c, d) {
    this.idx.push(a, b, c, a, c, d);
  }

  /** Appends a primitive geometry transformed by `matrix`. */
  addGeometry(geom, matrix, colour) {
    const g = geom.clone();
    g.applyMatrix4(matrix);
    const pos = g.attributes.position;
    const nor = g.attributes.normal;
    const uv = g.attributes.uv;
    const base = this.pos.length / 3;
    for (let i = 0; i < pos.count; i++) {
      this.pos.push(pos.getX(i), pos.getY(i), pos.getZ(i));
      if (nor) this.nor.push(nor.getX(i), nor.getY(i), nor.getZ(i));
      else this.nor.push(0, 1, 0);
      if (uv) this.uv.push(uv.getX(i), uv.getY(i));
      else this.uv.push(0, 0);
      if (this.col) {
        if (colour) this.col.push(colour.r, colour.g, colour.b);
        else this.col.push(1, 1, 1);
      }
    }
    if (g.index) {
      for (let i = 0; i < g.index.count; i++) this.idx.push(base + g.index.getX(i));
    } else {
      for (let i = 0; i < pos.count; i++) this.idx.push(base + i);
    }
    g.dispose();
  }

  build() {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.pos), 3));
    g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(this.nor), 3));
    g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(this.uv), 2));
    if (this.col) {
      g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(this.col), 3));
    }
    const array =
      this.count > 65535 ? new Uint32Array(this.idx) : new Uint16Array(this.idx);
    g.setIndex(new THREE.BufferAttribute(array, 1));
    g.computeBoundingSphere();
    return g;
  }
}

function neon(hex, intensity) {
  return new THREE.Color(hex).multiplyScalar(intensity);
}

// ---------------------------------------------------------------------------
// createTrack
// ---------------------------------------------------------------------------

export function createTrack(textures, options) {
  const tex = textures || {};
  const opts = options || {};
  const control = Array.isArray(opts.control) && opts.control.length >= 8 ? opts.control : CONTROL;
  const centreX = Array.isArray(opts.centre) ? Number(opts.centre[0]) || 0 : CENTRE_X;
  const centreZ = Array.isArray(opts.centre) ? Number(opts.centre[1]) || 0 : CENTRE_Z;
  const padSpec = Array.isArray(opts.pads) && opts.pads.length ? opts.pads : PAD_SPEC;
  const accentPrimary = opts.primary === undefined ? PALETTE.cyan : opts.primary;
  const accentSecondary = opts.secondary === undefined ? PALETTE.magenta : opts.secondary;
  const wallColor = opts.wall === undefined ? PALETTE.wall : opts.wall;
  const wallTrim = opts.wallTrim === undefined ? PALETTE.wallTrim : opts.wallTrim;
  const surface = opts.surface || {};
  const wallSurface = opts.wallSurface || {};
  const geometries = [];
  const materials = [];
  const group = new THREE.Group();
  group.name = 'circuit';

  const keepGeometry = (g) => {
    geometries.push(g);
    return g;
  };
  const keepMaterial = (m) => {
    materials.push(m);
    return m;
  };

  // -- curve ---------------------------------------------------------------
  const cpCount = control.length;
  const cpPoints = new Array(cpCount);
  const cpHalfWidth = new Float32Array(cpCount);
  const cpBank = new Float32Array(cpCount);
  const tagIndex = {};
  for (let i = 0; i < cpCount; i++) {
    const c = control[i];
    cpPoints[i] = new THREE.Vector3(c[0] + centreX, c[1], c[2] + centreZ);
    cpHalfWidth[i] = THREE.MathUtils.clamp(c[3], TRACK.halfWidthMin, TRACK.halfWidthMax);
    cpBank[i] = c[4] * DEG;
    if (c[5]) tagIndex[c[5]] = i;
  }
  const curve = new THREE.CatmullRomCurve3(cpPoints, true, 'centripetal', 0.5);

  // -- arc length table ----------------------------------------------------
  const arc = new Float64Array(ARC_DIVISIONS + 1);
  const walk = new THREE.Vector3();
  const walkPrev = new THREE.Vector3();
  curve.getPoint(0, walkPrev);
  let acc = 0;
  for (let i = 1; i <= ARC_DIVISIONS; i++) {
    curve.getPoint(i / ARC_DIVISIONS, walk);
    acc += walk.distanceTo(walkPrev);
    arc[i] = acc;
    walkPrev.copy(walk);
  }
  const length = acc;
  const sampleCount = Math.max(32, Math.round(length / TRACK.sampleSpacing));
  const spacing = length / sampleCount;

  /** Curve parameter of a given arc length, by search in the table. */
  const paramAt = (() => {
    let cursor = 0;
    return (distance) => {
      if (distance <= arc[cursor]) cursor = 0;
      while (cursor < ARC_DIVISIONS && arc[cursor + 1] < distance) cursor++;
      const seg = arc[cursor + 1] - arc[cursor];
      const w = seg > 1e-9 ? (distance - arc[cursor]) / seg : 0;
      return (cursor + w) / ARC_DIVISIONS;
    };
  })();

  // -- resampled tables ----------------------------------------------------
  const posA = new Float32Array(sampleCount * 3);
  const tanA = new Float32Array(sampleCount * 3);
  const upA = new Float32Array(sampleCount * 3);
  const rightA = new Float32Array(sampleCount * 3);
  let hwA = new Float32Array(sampleCount);
  let rollA = new Float32Array(sampleCount);
  const curvA = new Float32Array(sampleCount);
  const vCurvA = new Float32Array(sampleCount);
  const paramA = new Float64Array(sampleCount);

  const tmp = new THREE.Vector3();
  for (let i = 0; i < sampleCount; i++) {
    const t = paramAt(i * spacing);
    paramA[i] = t;
    curve.getPoint(t, tmp);
    posA[i * 3] = tmp.x;
    posA[i * 3 + 1] = tmp.y;
    posA[i * 3 + 2] = tmp.z;
    // half width and bank follow the same Catmull-Rom parameter as the curve
    const p = t * cpCount;
    let seg = Math.floor(p);
    const w = p - seg;
    seg = ((seg % cpCount) + cpCount) % cpCount;
    const a0 = (seg - 1 + cpCount) % cpCount;
    const a2 = (seg + 1) % cpCount;
    const a3 = (seg + 2) % cpCount;
    hwA[i] = catmullScalar(cpHalfWidth[a0], cpHalfWidth[seg], cpHalfWidth[a2], cpHalfWidth[a3], w);
    rollA[i] = catmullScalar(cpBank[a0], cpBank[seg], cpBank[a2], cpBank[a3], w);
  }
  const blurRadius = Math.max(1, Math.round(7 / spacing));
  hwA = smoothCircular(hwA, blurRadius, 2);
  rollA = smoothCircular(rollA, blurRadius, 3);
  for (let i = 0; i < sampleCount; i++) {
    hwA[i] = THREE.MathUtils.clamp(hwA[i], TRACK.halfWidthMin, TRACK.halfWidthMax);
  }

  // -- tangents (central difference on the resampled polyline) -------------
  const vA = new THREE.Vector3();
  const vB = new THREE.Vector3();
  for (let i = 0; i < sampleCount; i++) {
    const prev = (i - 1 + sampleCount) % sampleCount;
    const next = (i + 1) % sampleCount;
    vA.set(
      posA[next * 3] - posA[prev * 3],
      posA[next * 3 + 1] - posA[prev * 3 + 1],
      posA[next * 3 + 2] - posA[prev * 3 + 2],
    ).normalize();
    tanA[i * 3] = vA.x;
    tanA[i * 3 + 1] = vA.y;
    tanA[i * 3 + 2] = vA.z;
  }

  // -- parallel transport of the up vector ---------------------------------
  // computeFrenetFrames twists on the straights, so the frame is carried along
  // the curve instead, then the residual torsion of the closed loop is spread
  // uniformly over every sample so the ribbon has no seam.
  const quat = new THREE.Quaternion();
  const upWork = new THREE.Vector3();
  const tanCur = new THREE.Vector3();
  const tanPrev = new THREE.Vector3();
  const rightWork = new THREE.Vector3();

  tanCur.fromArray(tanA, 0);
  upWork.set(0, 1, 0).addScaledVector(tanCur, -tanCur.y);
  if (upWork.lengthSq() < 1e-6) upWork.set(0, 0, 1);
  upWork.normalize();
  upA[0] = upWork.x;
  upA[1] = upWork.y;
  upA[2] = upWork.z;

  for (let i = 1; i < sampleCount; i++) {
    tanPrev.fromArray(tanA, (i - 1) * 3);
    tanCur.fromArray(tanA, i * 3);
    quat.setFromUnitVectors(tanPrev, tanCur);
    upWork.fromArray(upA, (i - 1) * 3).applyQuaternion(quat);
    // re-orthogonalise against drift
    upWork.addScaledVector(tanCur, -upWork.dot(tanCur)).normalize();
    upA[i * 3] = upWork.x;
    upA[i * 3 + 1] = upWork.y;
    upA[i * 3 + 2] = upWork.z;
  }

  // closing residual, measured by transporting the last frame back onto the first
  tanPrev.fromArray(tanA, (sampleCount - 1) * 3);
  tanCur.fromArray(tanA, 0);
  quat.setFromUnitVectors(tanPrev, tanCur);
  upWork.fromArray(upA, (sampleCount - 1) * 3).applyQuaternion(quat);
  upWork.addScaledVector(tanCur, -upWork.dot(tanCur)).normalize();
  vA.fromArray(upA, 0);
  let residual = Math.acos(THREE.MathUtils.clamp(upWork.dot(vA), -1, 1));
  vB.crossVectors(upWork, vA);
  if (vB.dot(tanCur) < 0) residual = -residual;

  for (let i = 0; i < sampleCount; i++) {
    tanCur.fromArray(tanA, i * 3);
    upWork.fromArray(upA, i * 3);
    // untwist, then apply the authored bank as a roll about the tangent
    quat.setFromAxisAngle(tanCur, residual * (i / sampleCount) + rollA[i]);
    upWork.applyQuaternion(quat).normalize();
    rightWork.crossVectors(tanCur, upWork).normalize();
    upWork.crossVectors(rightWork, tanCur).normalize();
    upA[i * 3] = upWork.x;
    upA[i * 3 + 1] = upWork.y;
    upA[i * 3 + 2] = upWork.z;
    rightA[i * 3] = rightWork.x;
    rightA[i * 3 + 1] = rightWork.y;
    rightA[i * 3 + 2] = rightWork.z;
  }

  // -- curvatures ----------------------------------------------------------
  for (let i = 0; i < sampleCount; i++) {
    const prev = (i - 1 + sampleCount) % sampleCount;
    const next = (i + 1) % sampleCount;
    const hx0 = tanA[prev * 3];
    const hz0 = tanA[prev * 3 + 2];
    const l0 = Math.hypot(hx0, hz0) || 1;
    const hx1 = tanA[next * 3];
    const hz1 = tanA[next * 3 + 2];
    const l1 = Math.hypot(hx1, hz1) || 1;
    const cx = tanA[i * 3];
    const cz = tanA[i * 3 + 2];
    const lc = Math.hypot(cx, cz) || 1;
    // right hand normal of the horizontal tangent, matching frame.right
    const rx = -cz / lc;
    const rz = cx / lc;
    curvA[i] = ((hx1 / l1 - hx0 / l0) * rx + (hz1 / l1 - hz0 / l0) * rz) / (2 * spacing);
    vCurvA[i] = (tanA[next * 3 + 1] - tanA[prev * 3 + 1]) / (2 * spacing);
  }

  // -- abscissa of the tagged control points -------------------------------
  const sOfParam = (t) => {
    const f = THREE.MathUtils.clamp(t, 0, 1) * ARC_DIVISIONS;
    const i = Math.min(ARC_DIVISIONS - 1, Math.floor(f));
    return arc[i] + (arc[i + 1] - arc[i]) * (f - i);
  };
  const tagS = {};
  for (const key in tagIndex) tagS[key] = sOfParam(tagIndex[key] / cpCount);

  const startS = tagS.start !== undefined ? tagS.start : 0;

  // -- public query API ----------------------------------------------------
  function wrapS(s) {
    let v = s % length;
    if (v < 0) v += length;
    return v;
  }

  function deltaS(a, b) {
    let d = wrapS(b) - wrapS(a);
    const half = length * 0.5;
    if (d > half) d -= length;
    else if (d < -half) d += length;
    return d;
  }

  function indexOf(s) {
    let i = Math.floor(s / spacing);
    if (i < 0) i = 0;
    else if (i >= sampleCount) i = sampleCount - 1;
    return i;
  }

  function at(s, frame) {
    const w = wrapS(s);
    const i0 = indexOf(w);
    const i1 = i0 + 1 === sampleCount ? 0 : i0 + 1;
    const t = w / spacing - i0;
    const a = i0 * 3;
    const b = i1 * 3;
    frame.s = w;
    frame.pos.set(
      posA[a] + (posA[b] - posA[a]) * t,
      posA[a + 1] + (posA[b + 1] - posA[a + 1]) * t,
      posA[a + 2] + (posA[b + 2] - posA[a + 2]) * t,
    );
    frame.tangent
      .set(
        tanA[a] + (tanA[b] - tanA[a]) * t,
        tanA[a + 1] + (tanA[b + 1] - tanA[a + 1]) * t,
        tanA[a + 2] + (tanA[b + 2] - tanA[a + 2]) * t,
      )
      .normalize();
    frame.up
      .set(
        upA[a] + (upA[b] - upA[a]) * t,
        upA[a + 1] + (upA[b + 1] - upA[a + 1]) * t,
        upA[a + 2] + (upA[b + 2] - upA[a + 2]) * t,
      )
      .normalize();
    frame.right.crossVectors(frame.tangent, frame.up).normalize();
    frame.up.crossVectors(frame.right, frame.tangent).normalize();
    frame.halfWidth = hwA[i0] + (hwA[i1] - hwA[i0]) * t;
    frame.curvature = curvA[i0] + (curvA[i1] - curvA[i0]) * t;
    frame.vertCurvature = vCurvA[i0] + (vCurvA[i1] - vCurvA[i0]) * t;
    frame.roll = rollA[i0] + (rollA[i1] - rollA[i0]) * t;
    return frame;
  }

  function makeFrame() {
    return {
      s: 0,
      pos: new THREE.Vector3(),
      tangent: new THREE.Vector3(0, 0, -1),
      up: new THREE.Vector3(0, 1, 0),
      right: new THREE.Vector3(1, 0, 0),
      halfWidth: TRACK.halfWidthDefault,
      curvature: 0,
      vertCurvature: 0,
      roll: 0,
    };
  }

  // Reads the tables directly so that no scratch object is shared with `at`.
  function toWorld(s, x, h, outVec3) {
    const w = wrapS(s);
    const i0 = indexOf(w);
    const i1 = i0 + 1 === sampleCount ? 0 : i0 + 1;
    const t = w / spacing - i0;
    const a = i0 * 3;
    const b = i1 * 3;
    let rx = rightA[a] + (rightA[b] - rightA[a]) * t;
    let ry = rightA[a + 1] + (rightA[b + 1] - rightA[a + 1]) * t;
    let rz = rightA[a + 2] + (rightA[b + 2] - rightA[a + 2]) * t;
    let ux = upA[a] + (upA[b] - upA[a]) * t;
    let uy = upA[a + 1] + (upA[b + 1] - upA[a + 1]) * t;
    let uz = upA[a + 2] + (upA[b + 2] - upA[a + 2]) * t;
    const rl = Math.hypot(rx, ry, rz) || 1;
    rx /= rl;
    ry /= rl;
    rz /= rl;
    const ul = Math.hypot(ux, uy, uz) || 1;
    ux /= ul;
    uy /= ul;
    uz /= ul;
    outVec3.set(
      posA[a] + (posA[b] - posA[a]) * t + rx * x + ux * h,
      posA[a + 1] + (posA[b + 1] - posA[a + 1]) * t + ry * x + uy * h,
      posA[a + 2] + (posA[b + 2] - posA[a + 2]) * t + rz * x + uz * h,
    );
    return outVec3;
  }

  function halfWidthAt(s) {
    const w = wrapS(s);
    const i0 = indexOf(w);
    const i1 = i0 + 1 === sampleCount ? 0 : i0 + 1;
    const t = w / spacing - i0;
    return hwA[i0] + (hwA[i1] - hwA[i0]) * t;
  }

  // -- boost pads ----------------------------------------------------------
  const padHalfLength = TRACK.boostPadLength * 0.5;
  const padHalfWidth = TRACK.boostPadHalfWidth;
  const boostPads = padSpec.map((spec) => {
    const s = wrapS(spec.at * length);
    const limit = halfWidthAt(s) - padHalfWidth - 1.2;
    return {
      s,
      x: THREE.MathUtils.clamp(spec.x, -limit, limit),
      length: TRACK.boostPadLength,
      halfWidth: padHalfWidth,
    };
  });

  function padAt(s, x) {
    for (let i = 0; i < boostPads.length; i++) {
      const pad = boostPads[i];
      if (Math.abs(deltaS(pad.s, s)) > padHalfLength) continue;
      if (Math.abs(x - pad.x) <= padHalfWidth) return true;
    }
    return false;
  }

  // -- checkpoints ---------------------------------------------------------
  const checkpoints = [];
  const cpTotal = Math.max(1, TRACK.checkpointCount | 0);
  for (let i = 1; i <= cpTotal; i++) {
    checkpoints.push(wrapS(startS + (length * i) / (cpTotal + 1)));
  }
  checkpoints.sort((a, b) => a - b);

  // -- minimap outline -----------------------------------------------------
  const outlinePoints = [];
  {
    let minX = Infinity;
    let maxX = -Infinity;
    let minZ = Infinity;
    let maxZ = -Infinity;
    for (let i = 0; i < sampleCount; i++) {
      const x = posA[i * 3];
      const z = posA[i * 3 + 2];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (z < minZ) minZ = z;
      if (z > maxZ) maxZ = z;
    }
    const cx = (minX + maxX) * 0.5;
    const cz = (minZ + maxZ) * 0.5;
    const scale = 1 / Math.max((maxX - minX) * 0.5, (maxZ - minZ) * 0.5, 1);
    for (let i = 0; i < OUTLINE_POINTS; i++) {
      const idx = Math.round((i / OUTLINE_POINTS) * sampleCount) % sampleCount;
      outlinePoints.push({
        x: (posA[idx * 3] - cx) * scale,
        y: (posA[idx * 3 + 2] - cz) * scale,
      });
    }
  }

  // =========================================================================
  // Geometry
  // =========================================================================
  const buildVec = new THREE.Vector3();
  const buildRight = new THREE.Vector3();
  const buildUp = new THREE.Vector3();
  const buildTan = new THREE.Vector3();
  const buildBack = new THREE.Vector3();
  const buildMatrix = new THREE.Matrix4();

  const wrapIndex = (i) => ((i % sampleCount) + sampleCount) % sampleCount;

  /** World position of a point on the road cross section. */
  function surfacePoint(i, lateral, height, out) {
    const k = wrapIndex(i) * 3;
    out.set(
      posA[k] + rightA[k] * lateral + upA[k] * height,
      posA[k + 1] + rightA[k + 1] * lateral + upA[k + 1] * height,
      posA[k + 2] + rightA[k + 2] * lateral + upA[k + 2] * height,
    );
    return out;
  }

  /** Basis matrix at a sample: local X = right, Y = up, Z = backward. */
  function frameMatrix(i, lateral, height, along, out) {
    const k = wrapIndex(i) * 3;
    buildRight.fromArray(rightA, k);
    buildUp.fromArray(upA, k);
    buildTan.fromArray(tanA, k);
    buildBack.copy(buildTan).multiplyScalar(-1);
    out.makeBasis(buildRight, buildUp, buildBack);
    surfacePoint(i, lateral, height, buildVec).addScaledVector(buildTan, along);
    out.setPosition(buildVec);
    return out;
  }

  const setRepeat = (texture) => {
    if (!texture) return null;
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    return texture;
  };

  // --- road surface -------------------------------------------------------
  const columns = Math.max(2, TRACK.roadColumns | 0);
  const rows = sampleCount + 1;
  // whole number of texture tiles so the asphalt has no seam at the start line
  const roadTileLength = Math.max(8, Number(surface.tileLength) || 32);
  const roadTiles = Math.max(1, Math.round(length / roadTileLength));
  const vPerMetre = roadTiles / length;
  {
    const road = new MeshBuilder(false);
    for (let r = 0; r < rows; r++) {
      const i = r % sampleCount;
      const k = i * 3;
      const hw = hwA[i];
      const v = r * spacing * vPerMetre;
      for (let c = 0; c <= columns; c++) {
        const lateral = ((c / columns) * 2 - 1) * hw;
        surfacePoint(i, lateral, 0, buildVec);
        road.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          upA[k],
          upA[k + 1],
          upA[k + 2],
          lateral / 8,
          v,
        );
      }
    }
    for (let r = 0; r < rows - 1; r++) {
      for (let c = 0; c < columns; c++) {
        const a = r * (columns + 1) + c;
        road.quad(a, a + 1, a + columns + 2, a + columns + 1);
      }
    }
    const mat = keepMaterial(
      new THREE.MeshStandardMaterial({
        // White: the tarmac colour is already baked into the road map, and
        // multiplying it by PALETTE.asphalt a second time squared it into black.
        color: surface.color === undefined ? 0xffffff : surface.color,
        map: setRepeat(tex.road || null),
        normalMap: setRepeat(tex.roadNormal || null),
        roughnessMap: setRepeat(tex.roadRough || null),
        roughness: surface.roughness === undefined ? 1.0 : surface.roughness,
        metalness: surface.metalness === undefined ? 0.12 : surface.metalness,
        envMapIntensity: surface.envMapIntensity === undefined ? 0.45 : surface.envMapIntensity,
      }),
    );
    if (mat.normalMap) {
      const normalScale = surface.normalScale === undefined ? 0.85 : surface.normalScale;
      mat.normalScale.set(normalScale, normalScale);
    }
    const mesh = new THREE.Mesh(keepGeometry(road.build()), mat);
    mesh.name = 'road';
    mesh.receiveShadow = true;
    group.add(mesh);
  }

  // --- emissive edge strips and centre line -------------------------------
  {
    const strips = new MeshBuilder(true);
    const edgeColour = neon(accentPrimary, 3.1);
    const centreColour = neon(PALETTE.white, 0.5);
    const stripWidth = TRACK.edgeStripWidth;
    const lift = 0.03;
    const bands = [
      { inner: (hw) => -hw, outer: (hw) => -hw + stripWidth, colour: edgeColour },
      { inner: (hw) => hw - stripWidth, outer: (hw) => hw, colour: edgeColour },
      { inner: () => -0.18, outer: () => 0.18, colour: centreColour },
    ];
    for (let bandIndex = 0; bandIndex < bands.length; bandIndex++) {
      const band = bands[bandIndex];
      const base = strips.count;
      for (let r = 0; r < rows; r++) {
        const i = r % sampleCount;
        const k = i * 3;
        const hw = hwA[i];
        const u = (r * spacing) / 8;
        surfacePoint(i, band.inner(hw), lift, buildVec);
        strips.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          upA[k],
          upA[k + 1],
          upA[k + 2],
          u,
          0.02,
          band.colour.r,
          band.colour.g,
          band.colour.b,
        );
        surfacePoint(i, band.outer(hw), lift, buildVec);
        strips.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          upA[k],
          upA[k + 1],
          upA[k + 2],
          u,
          0.98,
          band.colour.r,
          band.colour.g,
          band.colour.b,
        );
      }
      for (let r = 0; r < rows - 1; r++) {
        const a = base + r * 2;
        strips.quad(a, a + 1, a + 3, a + 2);
      }
    }
    const mat = keepMaterial(
      new THREE.MeshBasicMaterial({
        map: tex.edgeStrip || null,
        vertexColors: true,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -4,
      }),
    );
    const mesh = new THREE.Mesh(keepGeometry(strips.build()), mat);
    mesh.name = 'edgeStrips';
    mesh.renderOrder = 2;
    group.add(mesh);
  }

  // --- walls --------------------------------------------------------------
  const wallHeight = TRACK.wallHeight;
  const wallThickness = TRACK.wallThickness;
  const wallSkirt = 1.8;
  {
    const walls = new MeshBuilder(false);
    const normal = new THREE.Vector3();
    for (let side = -1; side <= 1; side += 2) {
      const base = walls.count;
      for (let r = 0; r < rows; r++) {
        const i = r % sampleCount;
        const k = i * 3;
        const hw = hwA[i];
        const u = (r * spacing) / 8;
        const inner = side * hw;
        const outer = side * (hw + wallThickness);
        // inner face, facing the racing line
        normal.set(-side * rightA[k], -side * rightA[k + 1], -side * rightA[k + 2]);
        surfacePoint(i, inner, 0, buildVec);
        walls.vertex(buildVec.x, buildVec.y, buildVec.z, normal.x, normal.y, normal.z, u, 0);
        surfacePoint(i, inner, wallHeight, buildVec);
        walls.vertex(buildVec.x, buildVec.y, buildVec.z, normal.x, normal.y, normal.z, u, 1);
        // capping face
        surfacePoint(i, inner, wallHeight, buildVec);
        walls.vertex(buildVec.x, buildVec.y, buildVec.z, upA[k], upA[k + 1], upA[k + 2], u, 0.98);
        surfacePoint(i, outer, wallHeight, buildVec);
        walls.vertex(buildVec.x, buildVec.y, buildVec.z, upA[k], upA[k + 1], upA[k + 2], u, 1.0);
        // outer face plus a skirt that hides the edge of the ribbon
        normal.set(side * rightA[k], side * rightA[k + 1], side * rightA[k + 2]);
        surfacePoint(i, outer, wallHeight, buildVec);
        walls.vertex(buildVec.x, buildVec.y, buildVec.z, normal.x, normal.y, normal.z, u, 1);
        surfacePoint(i, outer, -wallSkirt, buildVec);
        walls.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          normal.x,
          normal.y,
          normal.z,
          u,
          -wallSkirt / wallHeight,
        );
      }
      for (let r = 0; r < rows - 1; r++) {
        const a = base + r * 6;
        const b = a + 6;
        if (side > 0) {
          walls.quad(a, a + 1, b + 1, b);
          walls.quad(a + 2, a + 3, b + 3, b + 2);
          walls.quad(a + 4, a + 5, b + 5, b + 4);
        } else {
          walls.quad(b, b + 1, a + 1, a);
          walls.quad(b + 2, b + 3, a + 3, a + 2);
          walls.quad(b + 4, b + 5, a + 5, a + 4);
        }
      }
    }
    const mat = keepMaterial(
      new THREE.MeshStandardMaterial({
        color: wallColor,
        map: setRepeat(tex.wall || null),
        normalMap: setRepeat(tex.wallNormal || null),
        emissive: new THREE.Color(0xffffff),
        emissiveMap: setRepeat(tex.wallEmissive || null),
        emissiveIntensity: tex.wallEmissive ? 2.6 : 0,
        roughness: wallSurface.roughness === undefined ? 0.72 : wallSurface.roughness,
        metalness: wallSurface.metalness === undefined ? 0.45 : wallSurface.metalness,
        envMapIntensity: wallSurface.envMapIntensity === undefined ? 0.58 : wallSurface.envMapIntensity,
      }),
    );
    if (mat.normalMap) {
      const normalScale = wallSurface.normalScale === undefined ? 1.0 : wallSurface.normalScale;
      mat.normalScale.set(normalScale, normalScale);
    }
    const mesh = new THREE.Mesh(keepGeometry(walls.build()), mat);
    mesh.name = 'walls';
    mesh.receiveShadow = true;
    group.add(mesh);
  }

  // --- tunnel -------------------------------------------------------------
  const tunnelFrom = tagS.tunnelIn !== undefined ? tagS.tunnelIn : -1;
  const tunnelTo = tagS.tunnelOut !== undefined ? tagS.tunnelOut : -1;
  const inTunnel = (s) => tunnelFrom >= 0 && s > tunnelFrom - 6 && s < tunnelTo + 6;
  if (tunnelFrom >= 0 && tunnelTo > tunnelFrom) {
    const shell = new MeshBuilder(false);
    const rings = new MeshBuilder(false);
    const radial = 18;
    const first = Math.floor(tunnelFrom / spacing);
    const last = Math.ceil(tunnelTo / spacing);
    const tunnelRows = last - first + 1;
    const normal = new THREE.Vector3();
    // The vault springs from below road level so its feet meet the viaduct
    // deck instead of floating beside it.
    const vaultFrom = -10 * DEG;
    const vaultSpan = 200 * DEG;
    // Radius clears the half width plus the full wall height, and the top
    // outer corner of both walls, with margin on top of that.
    const vaultRadius = (i) => {
      const hw = hwA[wrapIndex(i)] + wallThickness;
      return Math.max(hw + wallHeight + 0.6, Math.hypot(hw, wallHeight) + 1.2);
    };
    for (let r = 0; r < tunnelRows; r++) {
      const i = first + r;
      const k = wrapIndex(i) * 3;
      const radius = vaultRadius(i);
      const v = (r * spacing) / 8;
      for (let c = 0; c <= radial; c++) {
        const angle = vaultFrom + (c / radial) * vaultSpan;
        const lateral = -Math.cos(angle) * radius;
        const height = Math.sin(angle) * radius;
        surfacePoint(i, lateral, height, buildVec);
        // inward normal
        normal
          .set(
            -(rightA[k] * -Math.cos(angle) + upA[k] * Math.sin(angle)),
            -(rightA[k + 1] * -Math.cos(angle) + upA[k + 1] * Math.sin(angle)),
            -(rightA[k + 2] * -Math.cos(angle) + upA[k + 2] * Math.sin(angle)),
          )
          .normalize();
        shell.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          normal.x,
          normal.y,
          normal.z,
          (angle * radius) / 8,
          v,
        );
      }
    }
    for (let r = 0; r < tunnelRows - 1; r++) {
      for (let c = 0; c < radial; c++) {
        const a = r * (radial + 1) + c;
        shell.quad(a, a + radial + 1, a + radial + 2, a + 1);
      }
    }
    // luminous rings clipped just inside the vault
    // A band is 2 samples long, so at one ring every 13 m a third of the vault
    // was lit surface and the tunnel read as a strobing wall rather than as a
    // row of hoops.
    const ringStep = Math.max(2, Math.round(22 / spacing));
    const ringHalf = Math.max(1, Math.round(0.5 / spacing));
    for (let i = first + ringStep; i < last - 1; i += ringStep) {
      const base = rings.count;
      const radius = vaultRadius(i) - 0.28;
      for (let e = 0; e <= 1; e++) {
        const j = i + (e === 0 ? -ringHalf : ringHalf);
        const k = wrapIndex(j) * 3;
        for (let c = 0; c <= radial; c++) {
          const angle = vaultFrom + (c / radial) * vaultSpan;
          const lateral = -Math.cos(angle) * radius;
          const height = Math.sin(angle) * radius;
          surfacePoint(j, lateral, height, buildVec);
          normal
            .set(
              -(rightA[k] * -Math.cos(angle) + upA[k] * Math.sin(angle)),
              -(rightA[k + 1] * -Math.cos(angle) + upA[k + 1] * Math.sin(angle)),
              -(rightA[k + 2] * -Math.cos(angle) + upA[k + 2] * Math.sin(angle)),
            )
            .normalize();
          rings.vertex(
            buildVec.x,
            buildVec.y,
            buildVec.z,
            normal.x,
            normal.y,
            normal.z,
            c / radial,
            e,
          );
        }
      }
      for (let c = 0; c < radial; c++) {
        const a = base + c;
        rings.quad(a, a + radial + 1, a + radial + 2, a + 1);
      }
    }
    const shellMat = keepMaterial(
      new THREE.MeshStandardMaterial({
        color: wallColor,
        map: setRepeat(tex.wall || null),
        normalMap: setRepeat(tex.wallNormal || null),
        // No light reaches inside the vault, so without a faint self lit term
        // the shell is pure black and the rings blow out against it. No
        // emissiveMap here on purpose: wallEmissive is black everywhere except
        // its neon band rows, so masking with it would leave the vault black
        // again. The flat term has to cover the whole shell, kept well under
        // the bloom threshold so it reads as bounced light, not as a source.
        // A fully saturated violet is near maximum in the blue channel, so even
        // a small intensity paints the vault a solid mid violet. A muted hue
        // makes the number mean what it looks like.
        emissive: 0x6a5a9a,
        emissiveIntensity: 0.12,
        roughness: 0.85,
        metalness: 0.35,
        envMapIntensity: 0.1,
        side: THREE.DoubleSide,
      }),
    );
    const shellMesh = new THREE.Mesh(keepGeometry(shell.build()), shellMat);
    shellMesh.name = 'tunnel';
    shellMesh.receiveShadow = true;
    group.add(shellMesh);

    const ringMat = keepMaterial(
      new THREE.MeshBasicMaterial({
        // Above ~1 the rings saturate to flat white and swallow the whole
        // frame once the bloom picks them up.
        color: neon(accentPrimary, 0.4),
        side: THREE.DoubleSide,
        toneMapped: false,
      }),
    );
    const ringMesh = new THREE.Mesh(keepGeometry(rings.build()), ringMat);
    ringMesh.name = 'tunnelRings';
    group.add(ringMesh);
  }

  // --- wall light pods ----------------------------------------------------
  {
    const podStep = Math.max(1, Math.round(TRACK.lightStripSpacing / spacing));
    const podGeo = keepGeometry(new THREE.BoxGeometry(0.18, 0.26, 2.2));
    const slots = [];
    for (let i = 0; i < sampleCount; i += podStep) slots.push(i);
    const primary = [];
    const accent = [];
    for (let n = 0; n < slots.length; n++) {
      for (let side = -1; side <= 1; side += 2) {
        const i = slots[n];
        const lateral = side * (hwA[wrapIndex(i)] - 0.11);
        const m = new THREE.Matrix4();
        frameMatrix(i, lateral, 2.36, 0, m);
        (n % 5 === 0 ? accent : primary).push(m);
      }
    }
    const podSets = [
      { list: primary, colour: neon(accentPrimary, 2.6), name: 'podsPrimary' },
      { list: accent, colour: neon(accentSecondary, 2.2), name: 'podsSecondary' },
    ];
    for (const set of podSets) {
      if (!set.list.length) continue;
      const mat = keepMaterial(
        new THREE.MeshBasicMaterial({ color: set.colour, toneMapped: false }),
      );
      const mesh = new THREE.InstancedMesh(podGeo, mat, set.list.length);
      for (let n = 0; n < set.list.length; n++) mesh.setMatrixAt(n, set.list[n]);
      mesh.instanceMatrix.needsUpdate = true;
      mesh.name = set.name;
      mesh.frustumCulled = false;
        group.add(mesh);
    }
  }

  // --- gantries and the start line arch -----------------------------------
  {
    const structure = new MeshBuilder(false);
    const glow = new MeshBuilder(true);
    const postGeo = new THREE.BoxGeometry(1.5, 1, 1.5);
    const beamGeo = new THREE.BoxGeometry(1, 1.1, 1.6);
    const braceGeo = new THREE.BoxGeometry(1, 0.55, 0.8);
    const barGeo = new THREE.BoxGeometry(1, 0.32, 0.34);
    const podGeo = new THREE.BoxGeometry(0.9, 0.5, 0.9);
    const m = new THREE.Matrix4();
    const scale = new THREE.Matrix4();
    const glowColour = neon(accentPrimary, 2.8);
    const glowAccent = neon(accentSecondary, 2.4);

    const addGantry = (i, height, accent) => {
      const hw = hwA[wrapIndex(i)];
      const span = hw + wallThickness + 1.1;
      for (let side = -1; side <= 1; side += 2) {
        frameMatrix(i, side * span, height * 0.5, 0, m);
        scale.makeScale(1, height, 1);
        structure.addGeometry(postGeo, m.multiply(scale));
        frameMatrix(i, side * (span - 1.5), height - 1.6, 0, m);
        scale.makeScale(3.4, 1, 1);
        structure.addGeometry(braceGeo, m.multiply(scale));
      }
      frameMatrix(i, 0, height, 0, m);
      scale.makeScale(span * 2 + 1.5, 1, 1);
      structure.addGeometry(beamGeo, m.multiply(scale));
      // emissive bar slung under the beam plus two corner pods
      frameMatrix(i, 0, height - 0.72, 0, m);
      scale.makeScale(span * 2 - 1.2, 1, 1);
      glow.addGeometry(barGeo, m.multiply(scale), accent ? glowAccent : glowColour);
      for (let side = -1; side <= 1; side += 2) {
        frameMatrix(i, side * (span - 0.4), height - 0.55, 0, m);
        glow.addGeometry(podGeo, m, accent ? glowAccent : glowColour);
      }
    };

    const gantryStep = Math.max(4, Math.round(TRACK.gantrySpacing / spacing));
    let count = 0;
    for (let i = gantryStep; i < sampleCount; i += gantryStep) {
      const s = i * spacing;
      if (inTunnel(s)) continue;
      if (Math.abs(deltaS(startS, s)) < 60) continue;
      addGantry(i, 8.6, count % 3 === 2);
      count++;
    }
    // taller arch straddling the start / finish line
    addGantry(Math.round(startS / spacing), 12.4, false);

    postGeo.dispose();
    beamGeo.dispose();
    braceGeo.dispose();
    barGeo.dispose();
    podGeo.dispose();

    const structureMat = keepMaterial(
      new THREE.MeshStandardMaterial({
        color: wallTrim,
        roughness: 0.42,
        metalness: 0.78,
        envMapIntensity: 0.7,
      }),
    );
    const structureMesh = new THREE.Mesh(keepGeometry(structure.build()), structureMat);
    structureMesh.name = 'gantries';
    structureMesh.castShadow = true;
    structureMesh.receiveShadow = true;
    group.add(structureMesh);

    const glowMat = keepMaterial(
      new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false }),
    );
    const glowMesh = new THREE.Mesh(keepGeometry(glow.build()), glowMat);
    glowMesh.name = 'gantryGlow';
    group.add(glowMesh);
  }

  // --- boost pads ---------------------------------------------------------
  {
    const pads = new MeshBuilder(false);
    const padRows = Math.max(4, Math.round(TRACK.boostPadLength / spacing));
    for (const pad of boostPads) {
      const base = pads.count;
      const startIndex = pad.s / spacing - padRows * 0.5;
      for (let r = 0; r <= padRows; r++) {
        const i = wrapIndex(Math.round(startIndex + r));
        const k = i * 3;
        const v = r / padRows;
        for (let c = 0; c <= 1; c++) {
          const lateral = pad.x + (c * 2 - 1) * pad.halfWidth;
          surfacePoint(i, lateral, 0.03, buildVec);
          pads.vertex(
            buildVec.x,
            buildVec.y,
            buildVec.z,
            upA[k],
            upA[k + 1],
            upA[k + 2],
            c,
            v,
          );
        }
      }
      for (let r = 0; r < padRows; r++) {
        const a = base + r * 2;
        pads.quad(a, a + 1, a + 3, a + 2);
      }
    }
    const mat = keepMaterial(
      new THREE.MeshBasicMaterial({
        map: tex.boostPad || null,
        color: neon(PALETTE.white, 2.4),
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -4,
        polygonOffsetUnits: -6,
        toneMapped: false,
      }),
    );
    const mesh = new THREE.Mesh(keepGeometry(pads.build()), mat);
    mesh.name = 'boostPads';
    mesh.renderOrder = 3;
    group.add(mesh);
  }

  // --- start / finish chequered strip -------------------------------------
  {
    const strip = new MeshBuilder(false);
    const stripLength = 4;
    const stripRows = Math.max(2, Math.round(stripLength / spacing));
    const startIndex = startS / spacing - stripRows * 0.5;
    const cols = 12;
    for (let r = 0; r <= stripRows; r++) {
      const i = wrapIndex(Math.round(startIndex + r));
      const k = i * 3;
      const hw = hwA[i] - 0.05;
      const v = (r * spacing) / 4;
      for (let c = 0; c <= cols; c++) {
        const lateral = ((c / cols) * 2 - 1) * hw;
        surfacePoint(i, lateral, 0.02, buildVec);
        strip.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          upA[k],
          upA[k + 1],
          upA[k + 2],
          lateral / 4,
          v,
        );
      }
    }
    for (let r = 0; r < stripRows; r++) {
      for (let c = 0; c < cols; c++) {
        const a = r * (cols + 1) + c;
        strip.quad(a, a + 1, a + cols + 2, a + cols + 1);
      }
    }
    const mat = keepMaterial(
      new THREE.MeshStandardMaterial({
        map: setRepeat(tex.checker || null),
        color: 0xffffff,
        emissive: new THREE.Color(0xffffff),
        emissiveMap: setRepeat(tex.checker || null),
        emissiveIntensity: 0.35,
        roughness: 0.55,
        metalness: 0.05,
        polygonOffset: true,
        polygonOffsetFactor: -3,
        polygonOffsetUnits: -5,
      }),
    );
    const mesh = new THREE.Mesh(keepGeometry(strip.build()), mat);
    mesh.name = 'startLine';
    mesh.renderOrder = 1;
    group.add(mesh);
  }

  // --- road decals: sector markers and pad approach chevrons --------------
  {
    const decals = new MeshBuilder(false);
    const inset = 0.004;
    const addDecal = (s, lateral, halfWidth, decalLength, u0, u1, v0, v1) => {
      const base = decals.count;
      const decalRows = Math.max(2, Math.round(decalLength / spacing));
      const startIndex = s / spacing - decalRows * 0.5;
      for (let r = 0; r <= decalRows; r++) {
        const i = wrapIndex(Math.round(startIndex + r));
        const k = i * 3;
        const v = v0 + (v1 - v0) * (r / decalRows);
        for (let c = 0; c <= 1; c++) {
          surfacePoint(i, lateral + (c * 2 - 1) * halfWidth, 0.025, buildVec);
          decals.vertex(
            buildVec.x,
            buildVec.y,
            buildVec.z,
            upA[k],
            upA[k + 1],
            upA[k + 2],
            c === 0 ? u0 : u1,
            v,
          );
        }
      }
      for (let r = 0; r < decalRows; r++) {
        const a = base + r * 2;
        decals.quad(a, a + 1, a + 3, a + 2);
      }
    };
    // sector quadrants of the roadDetail atlas: 1 = top right, 2 and 3 below
    const sectorUV = [
      [0.5, 1, 0.5, 1],
      [0, 0.5, 0, 0.5],
      [0.5, 1, 0, 0.5],
    ];
    for (let c = 0; c < checkpoints.length && c < 3; c++) {
      const q = sectorUV[c];
      addDecal(
        wrapS(checkpoints[c] + 14),
        0,
        3.4,
        6.8,
        q[0] + inset,
        q[1] - inset,
        q[2] + inset,
        q[3] - inset,
      );
    }
    for (const pad of boostPads) {
      for (let n = 1; n <= 2; n++) {
        addDecal(
          wrapS(pad.s - padHalfLength - n * 13),
          pad.x,
          2.6,
          5.2,
          0 + inset,
          0.5 - inset,
          0.5 + inset,
          1 - inset,
        );
      }
    }
    const mat = keepMaterial(
      new THREE.MeshBasicMaterial({
        map: tex.roadDetail || null,
        color: neon(PALETTE.white, 1.25),
        transparent: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -3,
        polygonOffsetUnits: -5,
        toneMapped: false,
      }),
    );
    const mesh = new THREE.Mesh(keepGeometry(decals.build()), mat);
    mesh.name = 'roadDecals';
    mesh.renderOrder = 2;
    group.add(mesh);
  }

  // --- viaduct: underside deck and support pylons -------------------------
  // The whole ribbon flies over the void: world.js drops its ground plane far
  // below the lowest point of the circuit, so the pylons are driven well past
  // that level and read as anchored whatever the world does above it.
  {
    let lowest = Infinity;
    for (let i = 0; i < sampleCount; i++) lowest = Math.min(lowest, posA[i * 3 + 1]);
    const pylonBase = lowest - 70;

    const support = new MeshBuilder(false);
    const columnGeo = new THREE.CylinderGeometry(2.1, 4.6, 1, 6, 1, false);
    const capGeo = new THREE.BoxGeometry(1, 1.4, 3.4);
    const plinthGeo = new THREE.CylinderGeometry(6.2, 7.4, 3.2, 6, 1, false);
    const m = new THREE.Matrix4();
    const scale = new THREE.Matrix4();

    // continuous plate closing the underside of the ribbon
    const normal = new THREE.Vector3();
    for (let r = 0; r < rows; r++) {
      const i = r % sampleCount;
      const k = i * 3;
      const hw = hwA[i] + wallThickness;
      normal.set(-upA[k], -upA[k + 1], -upA[k + 2]);
      for (let c = 0; c <= 1; c++) {
        surfacePoint(i, (c * 2 - 1) * hw, -wallSkirt - 0.05, buildVec);
        support.vertex(
          buildVec.x,
          buildVec.y,
          buildVec.z,
          normal.x,
          normal.y,
          normal.z,
          c,
          (r * spacing) / 8,
        );
      }
    }
    for (let r = 0; r < rows - 1; r++) {
      const a = r * 2;
      support.quad(a, a + 2, a + 3, a + 1);
    }

    const pylonStep = Math.max(4, Math.round(46 / spacing));
    for (let i = 0; i < sampleCount; i += pylonStep) {
      surfacePoint(i, 0, -wallSkirt - 0.35, buildVec);
      const top = buildVec.y;
      const height = top - pylonBase;
      const anchorX = buildVec.x;
      const anchorZ = buildVec.z;
      // the column stays vertical in world space, the deck above it can bank
      m.makeTranslation(anchorX, (top + pylonBase) * 0.5, anchorZ);
      scale.makeScale(1, height, 1);
      support.addGeometry(columnGeo, m.multiply(scale));
      m.makeTranslation(anchorX, pylonBase + 1.6, anchorZ);
      support.addGeometry(plinthGeo, m);
      frameMatrix(i, 0, -wallSkirt - 0.45, 0, m);
      scale.makeScale(hwA[wrapIndex(i)] * 2 + 3, 1, 1);
      support.addGeometry(capGeo, m.multiply(scale));
    }
    columnGeo.dispose();
    capGeo.dispose();
    plinthGeo.dispose();

    const mat = keepMaterial(
      new THREE.MeshStandardMaterial({
        color: wallColor,
        map: setRepeat(tex.wall || null),
        roughness: 0.8,
        metalness: 0.4,
        envMapIntensity: 0.4,
      }),
    );
    const mesh = new THREE.Mesh(keepGeometry(support.build()), mat);
    mesh.name = 'viaduct';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);
  }


  // -- teardown ------------------------------------------------------------
  function dispose() {
    for (const g of geometries) g.dispose();
    for (const m of materials) m.dispose();
    geometries.length = 0;
    materials.length = 0;
    group.clear();
  }

  return {
    length,
    sampleCount,
    spacing,
    group,
    startS,
    checkpoints,
    boostPads,
    outlinePoints,
    makeFrame,
    at,
    wrapS,
    deltaS,
    toWorld,
    halfWidthAt,
    padAt,
    dispose,
  };
}
