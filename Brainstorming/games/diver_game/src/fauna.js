/**
 * ABYSSE - fauna.js
 *
 * Everything that lives: procedural creature meshes, swim animation (GPU
 * vertex deformation), behaviours (school / drifter / solo / ambush /
 * predator), combat queries, specimen drops and population streaming.
 *
 * Public factory: createFauna(scene, world, textures) -> Fauna
 * The Creature / Specimen / Fauna shapes follow docs/CONTRACTS.md exactly.
 *
 * Only imports: three and ./config.js. No per-frame allocation in hot loops,
 * all scratch vectors are module level. Geometry is cached per species,
 * schooling fish also share pooled materials.
 */

import * as THREE from 'three';
import {
  WORLD,
  SPECIES,
  DIVER,
  DEBUG,
  RARITY_COLOR,
  clamp,
  clamp01,
  lerp,
  springK,
  makeRandom,
} from './config.js';

// ---------------------------------------------------------------------------
// Tuning constants (module local, not part of the contract)
// ---------------------------------------------------------------------------

const LOD_FULL = 60;         // full AI + parts animation inside this range
const LOD_CHEAP = 140;       // cheap integration inside this range
const FROZEN_TICK = 1.4;     // frozen creatures get a micro update this often
const DESPAWN_DIST = 260;    // beyond this, non hunting creatures despawn
const MAX_CREATURES = 160;   // hard population cap
const STREAM_RADIUS = 170;   // population is counted inside this radius
const MIN_SPAWN_DIST = 45;   // never spawn closer to the player than this
const MAX_SPAWN_DIST = 210;  // nor farther than this
const CEILING_Y = -1.5;      // creatures stay below this unless they surface
const SURFACE_Y = -0.45;     // ceiling for surfacing species (turtle)
const DEATH_TUMBLE_TIME = 1.2;
const CONTACT_PAD = 0.9;     // extra reach for contact damage checks
const SCATTER_RADIUS = 24;   // same species scatter radius when one is hit
const CHARGE_STAGGER = 2.2;  // seconds between two predator charges

// Per species population target inside STREAM_RADIUS.
const POP_TARGET = {
  clownfish: 14,
  tang: 16,
  parrotfish: 3,
  turtle: 2,
  grouper: 3,
  manta: 2,
  moray: 3,
  barracuda: 7,
  lionfish: 3,
  octopus: 2,
  reefshark: 2,
  hammerhead: 1,
  greatwhite: 1,
  jelly: 8,
  anglerfish: 1,
  giantsquid: 1,
};

// Very rare species roll this chance on every stream pass before spawning.
const RARE_CHANCE = {
  greatwhite: 0.05,
  giantsquid: 0.04,
  anglerfish: 0.12,
};

// Species allowed to approach the surface.
const SURFACERS = { turtle: true };

// ---------------------------------------------------------------------------
// Module level scratch (never allocate in per frame loops)
// ---------------------------------------------------------------------------

const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();
const _v4 = new THREE.Vector3();
const _v5 = new THREE.Vector3();
const _v6 = new THREE.Vector3();
const _q1 = new THREE.Quaternion();
const _m4 = new THREE.Matrix4();
const _up = new THREE.Vector3(0, 1, 0);
const _zero = new THREE.Vector3(0, 0, 0);

// ---------------------------------------------------------------------------
// GPU swim animation
//
// Bodies are deformed in the vertex shader through onBeforeCompile. Three
// modes exist: 'swim' (lateral travelling wave, tail heavy), 'flap' (vertical
// wing wave for rays) and 'pulse' (radial bell contraction for jellies).
// uTime is one shared uniform object so a single write animates everything.
// ---------------------------------------------------------------------------

const SHARED_TIME = { value: 0 };

const ANIM_UNIFORM_DECL = [
  'uniform float uTime;',
  'uniform float uPhase;',
  'uniform float uSpeed;',
  'uniform float uAmp;',
  'uniform float uWave;',
  'uniform float uBodyHalf;',
].join('\n');

const ANIM_CHUNKS = {
  // Lateral sine wave along the body axis (head at +z, tail at -z).
  // Amplitude grows quadratically toward the tail.
  swim: [
    'float swimT = clamp((uBodyHalf - position.z) / max(2.0 * uBodyHalf, 0.0001), 0.0, 1.0);',
    'float swimA = uAmp * (0.08 + 0.92 * swimT * swimT);',
    'transformed.x += sin(position.z * uWave + uTime * uSpeed + uPhase) * swimA;',
  ].join('\n'),
  // Vertical wing wave, amplitude grows toward the wing tips.
  flap: [
    'float wingT = clamp(abs(position.x) / max(uBodyHalf, 0.0001), 0.0, 1.0);',
    'transformed.y += sin(uTime * uSpeed + uPhase - wingT * 2.3) * uAmp * wingT * wingT;',
  ].join('\n'),
  // Bell contraction: squeeze in xz, stretch in y, synced with the drift AI.
  pulse: [
    'float pulseV = 0.5 + 0.5 * sin(uTime * uSpeed + uPhase);',
    'float squeeze = 1.0 + uAmp * (0.55 - pulseV);',
    'transformed.x *= squeeze;',
    'transformed.z *= squeeze;',
    'transformed.y *= 1.0 + uAmp * (pulseV - 0.5) * 0.8;',
  ].join('\n'),
};

/**
 * Creates a MeshStandardMaterial with a vertex deformation patch.
 * Each call returns its own material instance with its own uniforms so
 * every creature (or pool slot) can carry a distinct phase / speed / amp.
 */
function makeAnimMaterial(opts) {
  const mat = new THREE.MeshStandardMaterial({
    color: opts.color !== undefined ? opts.color : 0xffffff,
    vertexColors: !!opts.vertexColors,
    roughness: opts.roughness !== undefined ? opts.roughness : 0.72,
    metalness: 0.02,
    transparent: !!opts.transparent,
    opacity: opts.opacity !== undefined ? opts.opacity : 1,
    side: opts.side || THREE.FrontSide,
    emissive: opts.emissive !== undefined ? opts.emissive : 0x000000,
    emissiveIntensity: opts.emissiveIntensity !== undefined ? opts.emissiveIntensity : 1,
    depthWrite: opts.depthWrite !== undefined ? opts.depthWrite : true,
  });
  if (opts.map) mat.map = opts.map;
  const u = {
    uTime: SHARED_TIME,
    uPhase: { value: opts.phase || 0 },
    uSpeed: { value: opts.speed !== undefined ? opts.speed : 5 },
    uAmp: { value: opts.amp !== undefined ? opts.amp : 0.06 },
    uWave: { value: opts.wave !== undefined ? opts.wave : 2.6 },
    uBodyHalf: { value: opts.half !== undefined ? opts.half : 0.5 },
  };
  const mode = opts.mode || 'swim';
  mat.userData.u = u;
  mat.userData.animMode = mode;
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, u);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\n' + ANIM_UNIFORM_DECL)
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n' + ANIM_CHUNKS[mode]);
  };
  // One program per mode, uniforms differ per material instance.
  mat.customProgramCacheKey = () => 'abysse-fauna-' + mode;
  return mat;
}

/** Plain static material helper for fins, shells and other rigid parts. */
function makeStaticMat(opts) {
  return new THREE.MeshStandardMaterial({
    color: opts.color !== undefined ? opts.color : 0xffffff,
    vertexColors: !!opts.vertexColors,
    roughness: opts.roughness !== undefined ? opts.roughness : 0.7,
    metalness: 0.03,
    transparent: !!opts.transparent,
    opacity: opts.opacity !== undefined ? opts.opacity : 1,
    side: opts.side || THREE.DoubleSide,
    emissive: opts.emissive !== undefined ? opts.emissive : 0x000000,
    emissiveIntensity: opts.emissiveIntensity !== undefined ? opts.emissiveIntensity : 1,
    depthWrite: opts.depthWrite !== undefined ? opts.depthWrite : true,
  });
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

/** Every geometry ever built is registered here for dispose(). */
const ownedGeometries = [];

function registerGeo(geo) {
  ownedGeometries.push(geo);
  return geo;
}

/** Cache: one geometry set per species id, shared by all its individuals. */
const geoCache = new Map();

function getGeo(key, maker) {
  let g = geoCache.get(key);
  if (!g) {
    g = registerGeo(maker());
    geoCache.set(key, g);
  }
  return g;
}

/**
 * Builds a fish like body from a profile curve. The body runs along Z with
 * the head at +len/2 and the tail at -len/2. Cross sections are ellipses
 * whose half width / half height vary along the body, with an optional
 * vertical offset (belly / back line). Vertex colors come from colorFn.
 *
 * def = {
 *   len, segs, radial,
 *   width(t)  -> half width at t (t: 0 head, 1 tail),
 *   height(t) -> half height at t,
 *   yOff(t)   -> vertical centre offset (optional),
 *   color(t, ny, nx, out) -> writes THREE.Color out (optional),
 * }
 */
function buildProfileBody(def) {
  const segs = def.segs || 20;
  const radial = def.radial || 12;
  const len = def.len;
  const half = len * 0.5;
  const ringVerts = radial + 1;
  const vertCount = (segs + 1) * ringVerts;
  const positions = new Float32Array(vertCount * 3);
  const colors = new Float32Array(vertCount * 3);
  const uvs = new Float32Array(vertCount * 2);
  const indices = [];
  const col = new THREE.Color(1, 1, 1);
  let p = 0;
  let uv = 0;
  for (let i = 0; i <= segs; i++) {
    const t = i / segs;
    const z = half - t * len;
    const w = Math.max(def.width(t), 0.004);
    const h = Math.max(def.height(t), 0.004);
    const yo = def.yOff ? def.yOff(t) : 0;
    for (let j = 0; j <= radial; j++) {
      const a = (j / radial) * Math.PI * 2;
      const nx = Math.cos(a);
      const ny = Math.sin(a);
      positions[p] = nx * w;
      positions[p + 1] = ny * h + yo;
      positions[p + 2] = z;
      if (def.color) def.color(t, ny, nx, col);
      else col.setRGB(1, 1, 1);
      colors[p] = col.r;
      colors[p + 1] = col.g;
      colors[p + 2] = col.b;
      p += 3;
      uvs[uv] = t;
      uvs[uv + 1] = j / radial;
      uv += 2;
    }
  }
  for (let i = 0; i < segs; i++) {
    for (let j = 0; j < radial; j++) {
      const a = i * ringVerts + j;
      const b = a + ringVerts;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

/**
 * Builds a tapered tube along a list of points (tentacles, tails, stalks).
 * radiusFn(t) gives the radius at t (0 start, 1 tip). Optional colorFn.
 */
function buildTaperedTube(points, radiusFn, radial, colorFn) {
  const n = points.length;
  const ringVerts = radial + 1;
  const vertCount = n * ringVerts;
  const positions = new Float32Array(vertCount * 3);
  const colors = new Float32Array(vertCount * 3);
  const indices = [];
  const tangent = new THREE.Vector3();
  const normal = new THREE.Vector3(1, 0, 0);
  const binormal = new THREE.Vector3();
  const tmp = new THREE.Vector3();
  const col = new THREE.Color(1, 1, 1);
  let p = 0;
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    const prev = points[Math.max(0, i - 1)];
    const next = points[Math.min(n - 1, i + 1)];
    tangent.subVectors(next, prev).normalize();
    // Parallel transport lite: keep the previous normal, re orthogonalise.
    tmp.copy(tangent).multiplyScalar(normal.dot(tangent));
    normal.sub(tmp);
    if (normal.lengthSq() < 1e-6) normal.set(0, 1, 0).cross(tangent);
    normal.normalize();
    binormal.crossVectors(tangent, normal);
    const r = Math.max(radiusFn(t), 0.002);
    for (let j = 0; j <= radial; j++) {
      const a = (j / radial) * Math.PI * 2;
      const ca = Math.cos(a);
      const sa = Math.sin(a);
      positions[p] = points[i].x + (normal.x * ca + binormal.x * sa) * r;
      positions[p + 1] = points[i].y + (normal.y * ca + binormal.y * sa) * r;
      positions[p + 2] = points[i].z + (normal.z * ca + binormal.z * sa) * r;
      if (colorFn) colorFn(t, col);
      else col.setRGB(1, 1, 1);
      colors[p] = col.r;
      colors[p + 1] = col.g;
      colors[p + 2] = col.b;
      p += 3;
    }
  }
  for (let i = 0; i < n - 1; i++) {
    for (let j = 0; j < radial; j++) {
      const a = i * ringVerts + j;
      const b = a + ringVerts;
      indices.push(a, b, a + 1, b, b + 1, a + 1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

/** Thin fin from a closed 2D outline, in the XY plane (attach and rotate). */
function buildFin(points2d) {
  const shape = new THREE.Shape();
  shape.moveTo(points2d[0][0], points2d[0][1]);
  for (let i = 1; i < points2d.length; i++) {
    shape.lineTo(points2d[i][0], points2d[i][1]);
  }
  shape.closePath();
  return new THREE.ShapeGeometry(shape, 4);
}

// Shared unit sphere for eyes, glints, small blobs (scaled per mesh).
let UNIT_SPHERE = null;
let MAT_EYE = null;
let MAT_GLINT = null;

function ensureSharedPrimitives() {
  if (UNIT_SPHERE) return;
  UNIT_SPHERE = registerGeo(new THREE.SphereGeometry(1, 10, 8));
  MAT_EYE = new THREE.MeshStandardMaterial({ color: 0x0a0d10, roughness: 0.25, metalness: 0.1 });
  MAT_GLINT = new THREE.MeshBasicMaterial({ color: 0xffffff });
}

/** Adds one eye (dark sphere + white highlight) to a group. */
function addEye(group, x, y, z, r) {
  ensureSharedPrimitives();
  const eye = new THREE.Mesh(UNIT_SPHERE, MAT_EYE);
  eye.position.set(x, y, z);
  eye.scale.setScalar(r);
  group.add(eye);
  const glint = new THREE.Mesh(UNIT_SPHERE, MAT_GLINT);
  glint.position.set(x + (x >= 0 ? r * 0.45 : -r * 0.45), y + r * 0.35, z + r * 0.5);
  glint.scale.setScalar(r * 0.3);
  group.add(glint);
}

/** Adds both eyes symmetrically on x. */
function addEyePair(group, x, y, z, r) {
  addEye(group, x, y, z, r);
  addEye(group, -x, y, z, r);
}

// Shared unit cone for spikes and teeth (scaled per mesh).
let UNIT_CONE = null;

function ensureCone() {
  if (!UNIT_CONE) UNIT_CONE = registerGeo(new THREE.ConeGeometry(1, 1, 6));
  return UNIT_CONE;
}

/** Deterministic 2D hash in [0,1), used for speckles and blotches. */
function hash2(a, b) {
  const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
  return s - Math.floor(s);
}

/** Wraps a mesh in a pivot group so it can be animated around its base. */
function pivotAt(mesh, x, y, z) {
  const pivot = new THREE.Group();
  pivot.position.set(x, y, z);
  pivot.add(mesh);
  return pivot;
}

// ---------------------------------------------------------------------------
// Species mesh builders
//
// One builder per `species.body`. Each returns:
//   { group, parts, mats, animMats, radius }
// group    - THREE.Group, head toward +Z, origin at body centre
// parts    - CPU animated nodes (tail, pectL, pectR, jaw, lure, tentacles...)
// mats     - every material owned by this creature (flash / fade / dispose)
// animMats - materials that carry swim uniforms (uSpeed modulation)
// radius   - collision / shooting sphere radius in metres
//
// Geometry is cached per species id so every individual shares vertex data.
// ---------------------------------------------------------------------------

/** Common caudal fin pivot: outline is in XY with -x pointing tailward. */
function addTailFin(group, species, geoKey, outline, mat, halfLen, yOff) {
  const geo = getGeo(geoKey, () => buildFin(outline));
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.y = -Math.PI / 2; // shape x axis becomes body z axis
  const pivot = pivotAt(mesh, 0, yOff || 0, -halfLen);
  group.add(pivot);
  return pivot;
}

/** Common pectoral pair: small fins on the flanks, animated at the root. */
function addPectorals(group, species, geoKey, outline, mat, x, y, z) {
  const geo = getGeo(geoKey, () => buildFin(outline));
  const left = new THREE.Mesh(geo, mat);
  left.rotation.set(-0.5, -Math.PI / 2, 0.4);
  const pl = pivotAt(left, x, y, z);
  group.add(pl);
  const right = new THREE.Mesh(geo, mat);
  right.rotation.set(-0.5, Math.PI / 2, -0.4);
  right.scale.x = -1;
  const pr = pivotAt(right, -x, y, z);
  group.add(pr);
  return [pl, pr];
}

// --- reeffish: short, tall, laterally flat (clownfish, tang, parrotfish) ---

function buildReeffish(species, rng) {
  const L = species.size;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 18,
    radial: 12,
    width: (t) => 0.11 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.08), 0.8)),
    height: (t) => 0.30 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.05), 0.72)),
    color: (t, ny, nx, out) => {
      if (species.id === 'clownfish') {
        // Three white bands with dark rims over the orange body.
        const bands = [0.2, 0.5, 0.82];
        let d = 1;
        for (let i = 0; i < 3; i++) d = Math.min(d, Math.abs(t - bands[i]));
        if (d < 0.055) out.copy(c1);
        else if (d < 0.085) out.copy(c2);
        else out.copy(c0);
      } else if (species.id === 'tang') {
        // Blue body, dark painter's palette flank patch, yellow tail.
        if (t > 0.82) out.copy(c2);
        else if (t > 0.18 && t < 0.72 && ny > -0.35) out.copy(c1);
        else out.copy(c0);
      } else if (species.id === 'parrotfish') {
        // Teal scales with pink speckle and bright cheeks.
        const sp = hash2(Math.floor(t * 14), Math.floor((ny + 1) * 5));
        if (t < 0.16) out.copy(c2);
        else if (sp > 0.72) out.copy(c1);
        else out.copy(c0);
      } else {
        // Generic reef fish: dark back, light belly, accent tail.
        if (t > 0.85) out.copy(c2);
        else if (ny < -0.25) out.copy(c1);
        else out.copy(c0);
      }
      // Slight shading toward the belly for readability.
      if (ny < 0) out.multiplyScalar(1.06);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.55,
    half: L * 0.5,
    wave: 6.5 / L,
    amp: 0.05 * L,
    speed: 6 + rng() * 2,
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  const finMat = makeStaticMat({
    color: species.colors[2],
    transparent: true,
    opacity: 0.9,
    roughness: 0.5,
  });
  // Dorsal fin along the back.
  const dorsalGeo = getGeo(species.id + ':dorsal', () => buildFin([
    [-0.3 * L, 0], [0.22 * L, 0], [0.1 * L, 0.16 * L], [-0.16 * L, 0.2 * L], [-0.3 * L, 0.08 * L],
  ]));
  const dorsal = new THREE.Mesh(dorsalGeo, finMat);
  dorsal.rotation.y = -Math.PI / 2;
  dorsal.position.set(0, 0.24 * L, 0);
  group.add(dorsal);
  // Anal fin under the tail half.
  const analGeo = getGeo(species.id + ':anal', () => buildFin([
    [-0.2 * L, 0], [0.06 * L, 0], [-0.05 * L, -0.1 * L], [-0.2 * L, -0.12 * L],
  ]));
  const anal = new THREE.Mesh(analGeo, finMat);
  anal.rotation.y = -Math.PI / 2;
  anal.position.set(0, -0.2 * L, -0.08 * L);
  group.add(anal);
  const tail = addTailFin(group, species, species.id + ':tail', [
    [0, 0.02 * L], [-0.2 * L, 0.17 * L], [-0.12 * L, 0], [-0.2 * L, -0.17 * L], [0, -0.02 * L],
  ], finMat, L * 0.48, 0);
  const pect = addPectorals(group, species, species.id + ':pect', [
    [0, 0], [0.12 * L, -0.03 * L], [0.05 * L, -0.11 * L],
  ], finMat, 0.1 * L, 0, 0.16 * L);
  addEyePair(group, 0.085 * L, 0.08 * L, 0.36 * L, 0.038 * L);
  return {
    group,
    parts: { tail, pectL: pect[0], pectR: pect[1] },
    mats: [bodyMat, finMat],
    animMats: [bodyMat],
    radius: L * 0.42,
  };
}

// --- bulkfish: thick grouper with a huge head and mouth ---

function buildBulkfish(species, rng) {
  const L = species.size * 1.35; // groupers read longer than their size stat
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 20,
    radial: 14,
    // Head heavy: widest and tallest around a third of the body.
    width: (t) => 0.17 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.02 + 0.06), 0.62)),
    height: (t) => 0.20 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.02 + 0.05), 0.6)),
    yOff: (t) => -0.02 * L * Math.sin(Math.PI * t),
    color: (t, ny, nx, out) => {
      // Mottled brown blotches over a lighter base, pale belly.
      const blotch = hash2(Math.floor(t * 11), Math.floor((ny + 1) * 4 + nx));
      if (ny < -0.55) out.copy(c2);
      else if (blotch > 0.55) out.copy(c1);
      else out.copy(c0);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.8,
    half: L * 0.5,
    wave: 4.2 / L,
    amp: 0.045 * L,
    speed: 3.6 + rng(),
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  const finMat = makeStaticMat({ color: species.colors[1], roughness: 0.7, transparent: true, opacity: 0.95 });
  // Huge grumpy mouth: dark open gap plus a jutting lower jaw plate.
  const mouthMat = makeStaticMat({ color: 0x14100c, roughness: 0.9 });
  ensureSharedPrimitives();
  const mouth = new THREE.Mesh(UNIT_SPHERE, mouthMat);
  mouth.position.set(0, -0.03 * L, 0.47 * L);
  mouth.scale.set(0.1 * L, 0.055 * L, 0.05 * L);
  group.add(mouth);
  const jawGeo = getGeo(species.id + ':jaw', () => buildFin([
    [-0.09 * L, 0], [0.09 * L, 0], [0.06 * L, 0.07 * L], [-0.06 * L, 0.07 * L],
  ]));
  const jawMesh = new THREE.Mesh(jawGeo, bodyMat);
  jawMesh.rotation.x = -1.25;
  const jaw = pivotAt(jawMesh, 0, -0.08 * L, 0.44 * L);
  group.add(jaw);
  const dorsalGeo = getGeo(species.id + ':dorsal', () => buildFin([
    [-0.32 * L, 0], [0.18 * L, 0], [0.12 * L, 0.1 * L], [-0.02 * L, 0.08 * L],
    [-0.1 * L, 0.12 * L], [-0.24 * L, 0.09 * L], [-0.32 * L, 0.05 * L],
  ]));
  const dorsal = new THREE.Mesh(dorsalGeo, finMat);
  dorsal.rotation.y = -Math.PI / 2;
  dorsal.position.set(0, 0.17 * L, 0);
  group.add(dorsal);
  const tail = addTailFin(group, species, species.id + ':tail', [
    [0, 0.03 * L], [-0.16 * L, 0.14 * L], [-0.2 * L, 0], [-0.16 * L, -0.14 * L], [0, -0.03 * L],
  ], finMat, L * 0.48, 0);
  const pect = addPectorals(group, species, species.id + ':pect', [
    [0, 0], [0.16 * L, -0.02 * L], [0.1 * L, -0.12 * L],
  ], finMat, 0.15 * L, -0.04 * L, 0.14 * L);
  addEyePair(group, 0.11 * L, 0.1 * L, 0.34 * L, 0.032 * L);
  return {
    group,
    parts: { tail, pectL: pect[0], pectR: pect[1], jaw },
    mats: [bodyMat, finMat, mouthMat],
    animMats: [bodyMat],
    radius: L * 0.34,
  };
}

// --- sleekfish: long cylindrical barracuda ---

function buildSleekfish(species, rng) {
  const L = species.size * 1.15;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 24,
    radial: 10,
    // Long spindle: slow taper, pointed pike snout.
    width: (t) => 0.055 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 0.98 + 0.03), 0.5)),
    height: (t) => 0.07 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 0.98 + 0.03), 0.5)),
    color: (t, ny, nx, out) => {
      // Chrome flank, dark back, pale belly, dark bars on the upper flank.
      const bar = hash2(Math.floor(t * 16), 1) > 0.6 && ny > 0 && ny < 0.75;
      if (ny > 0.55) out.copy(c1);
      else if (ny < -0.5) out.copy(c2);
      else out.copy(c0);
      if (bar && t > 0.2 && t < 0.85) out.lerp(c1, 0.55);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.35,
    half: L * 0.5,
    wave: 5.2 / L,
    amp: 0.04 * L,
    speed: 6.5 + rng() * 2,
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  const finMat = makeStaticMat({ color: species.colors[1], transparent: true, opacity: 0.85, roughness: 0.4 });
  // Underslung jaw: barracudas lead with the lower fang row.
  const jawGeo = getGeo(species.id + ':jawfin', () => buildFin([
    [0, 0], [0.11 * L, 0.012 * L], [0.02 * L, 0.03 * L],
  ]));
  const jawMesh = new THREE.Mesh(jawGeo, finMat);
  jawMesh.rotation.y = -Math.PI / 2;
  const jaw = pivotAt(jawMesh, 0, -0.045 * L, 0.42 * L);
  group.add(jaw);
  // Two small dorsal fins far apart, the pike signature.
  const dGeo = getGeo(species.id + ':dorsal', () => buildFin([
    [-0.06 * L, 0], [0.03 * L, 0], [-0.03 * L, 0.09 * L], [-0.06 * L, 0.06 * L],
  ]));
  const d1 = new THREE.Mesh(dGeo, finMat);
  d1.rotation.y = -Math.PI / 2;
  d1.position.set(0, 0.06 * L, 0.1 * L);
  group.add(d1);
  const d2 = new THREE.Mesh(dGeo, finMat);
  d2.rotation.y = -Math.PI / 2;
  d2.position.set(0, 0.055 * L, -0.24 * L);
  group.add(d2);
  const tail = addTailFin(group, species, species.id + ':tail', [
    [0, 0.015 * L], [-0.16 * L, 0.13 * L], [-0.07 * L, 0], [-0.16 * L, -0.13 * L], [0, -0.015 * L],
  ], finMat, L * 0.49, 0);
  const pect = addPectorals(group, species, species.id + ':pect', [
    [0, 0], [0.09 * L, -0.015 * L], [0.04 * L, -0.06 * L],
  ], finMat, 0.05 * L, -0.02 * L, 0.2 * L);
  addEyePair(group, 0.045 * L, 0.025 * L, 0.37 * L, 0.026 * L);
  return {
    group,
    parts: { tail, pectL: pect[0], pectR: pect[1] },
    mats: [bodyMat, finMat],
    animMats: [bodyMat],
    radius: L * 0.3,
  };
}

// --- lionfish: banded body with a fan of venomous spines ---

function buildLionfish(species, rng) {
  const L = species.size * 1.1;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 18,
    radial: 12,
    width: (t) => 0.1 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.05), 0.7)),
    height: (t) => 0.2 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.02), 0.68)),
    color: (t, ny, nx, out) => {
      // Tight red / cream vertical banding, the venom warning livery.
      const band = Math.sin(t * 34 + ny * 0.8);
      out.copy(band > 0.1 ? c0 : c1);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.6,
    half: L * 0.5,
    wave: 5.5 / L,
    amp: 0.032 * L,
    speed: 3 + rng(),
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  const spineMat = makeStaticMat({
    color: species.colors[0],
    transparent: true,
    opacity: 0.85,
    roughness: 0.45,
  });
  // Dorsal spines: a row of long thin cones, slightly splayed.
  ensureCone();
  for (let i = 0; i < 9; i++) {
    const t = i / 8;
    const spine = new THREE.Mesh(UNIT_CONE, spineMat);
    spine.scale.set(0.008 * L, 0.3 * L * (0.65 + 0.35 * Math.sin(Math.PI * t)), 0.008 * L);
    spine.position.set(0, 0.2 * L, 0.3 * L - t * 0.55 * L);
    spine.rotation.x = -0.5 + t * 0.9;
    group.add(spine);
  }
  // Pectoral fans: wide jagged sails, the lionfish silhouette.
  const fanGeo = getGeo(species.id + ':fan', () => {
    const pts = [[0, 0]];
    const rays = 7;
    for (let i = 0; i <= rays; i++) {
      const a = -0.35 + (i / rays) * 1.9;
      const r = 0.34 * L * (i % 2 === 0 ? 1 : 0.72);
      pts.push([Math.cos(a) * r, -Math.sin(a) * r]);
    }
    return buildFin(pts);
  });
  const fanL = new THREE.Mesh(fanGeo, spineMat);
  fanL.rotation.set(0.3, -Math.PI / 2 - 0.5, 0);
  const pl = pivotAt(fanL, 0.07 * L, 0, 0.1 * L);
  group.add(pl);
  const fanR = new THREE.Mesh(fanGeo, spineMat);
  fanR.rotation.set(0.3, Math.PI / 2 + 0.5, 0);
  fanR.scale.x = -1;
  const pr = pivotAt(fanR, -0.07 * L, 0, 0.1 * L);
  group.add(pr);
  const tail = addTailFin(group, species, species.id + ':tail', [
    [0, 0.02 * L], [-0.14 * L, 0.12 * L], [-0.17 * L, 0], [-0.14 * L, -0.12 * L], [0, -0.02 * L],
  ], spineMat, L * 0.48, 0);
  addEyePair(group, 0.075 * L, 0.07 * L, 0.36 * L, 0.03 * L);
  return {
    group,
    parts: { tail, pectL: pl, pectR: pr },
    mats: [bodyMat, spineMat],
    animMats: [bodyMat],
    radius: L * 0.44,
  };
}

// --- turtle: domed scute carapace, plastron, four flippers, beaked head ---

function buildTurtle(species, rng) {
  const S = species.size;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  // Carapace: a squashed hemisphere with per vertex scute tiles.
  const shellGeo = getGeo(species.id + ':shell', () => {
    const geo = new THREE.SphereGeometry(0.42 * S, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.52);
    const pos = geo.getAttribute('position');
    const uvA = geo.getAttribute('uv');
    const colors = new Float32Array(pos.count * 3);
    const col = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      // Squash the dome and stretch it along the body axis.
      pos.setY(i, pos.getY(i) * 0.55);
      pos.setZ(i, pos.getZ(i) * 1.25);
      // Scute pattern: big hex-ish tiles, darker grout between them.
      const cu = uvA.getX(i) * 6;
      const cv = uvA.getY(i) * 3;
      const fu = cu - Math.floor(cu);
      const fv = cv - Math.floor(cv);
      const edge = Math.min(fu, 1 - fu, fv, 1 - fv);
      const tone = hash2(Math.floor(cu), Math.floor(cv));
      if (edge < 0.1) col.copy(c1);
      else col.copy(c0).lerp(c1, tone * 0.45);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  });
  const shellMat = makeStaticMat({ vertexColors: true, roughness: 0.85, side: THREE.FrontSide });
  const group = new THREE.Group();
  const shell = new THREE.Mesh(shellGeo, shellMat);
  group.add(shell);
  // Plastron: pale squashed sphere closing the underside.
  ensureSharedPrimitives();
  const skinMat = makeStaticMat({ color: species.colors[2], roughness: 0.8, side: THREE.FrontSide });
  const plastron = new THREE.Mesh(UNIT_SPHERE, skinMat);
  plastron.position.set(0, -0.02 * S, 0);
  plastron.scale.set(0.38 * S, 0.1 * S, 0.5 * S);
  group.add(plastron);
  // Head on a short neck, with a horn beak.
  const headMat = makeStaticMat({ color: species.colors[0], roughness: 0.75, side: THREE.FrontSide });
  const head = new THREE.Mesh(UNIT_SPHERE, headMat);
  head.position.set(0, 0.03 * S, 0.6 * S);
  head.scale.set(0.11 * S, 0.1 * S, 0.14 * S);
  group.add(head);
  const neck = new THREE.Mesh(UNIT_SPHERE, headMat);
  neck.position.set(0, 0.0, 0.48 * S);
  neck.scale.set(0.08 * S, 0.08 * S, 0.14 * S);
  group.add(neck);
  ensureCone();
  const beak = new THREE.Mesh(UNIT_CONE, skinMat);
  beak.position.set(0, 0.0, 0.74 * S);
  beak.rotation.x = Math.PI / 2;
  beak.scale.set(0.05 * S, 0.06 * S, 0.045 * S);
  group.add(beak);
  addEyePair(group, 0.08 * S, 0.07 * S, 0.62 * S, 0.022 * S);
  // Four flippers: big front paddles, small rear ones.
  const flipGeo = getGeo(species.id + ':flipF', () => buildFin([
    [0, 0.03 * S], [0.34 * S, -0.05 * S], [0.42 * S, -0.14 * S], [0.2 * S, -0.12 * S], [0, -0.04 * S],
  ]));
  const rearGeo = getGeo(species.id + ':flipR', () => buildFin([
    [0, 0.02 * S], [0.18 * S, -0.04 * S], [0.2 * S, -0.1 * S], [0, -0.05 * S],
  ]));
  const fl = new THREE.Mesh(flipGeo, headMat);
  fl.rotation.x = -Math.PI / 2 + 0.25;
  const pFL = pivotAt(fl, 0.3 * S, -0.03 * S, 0.3 * S);
  group.add(pFL);
  const fr = new THREE.Mesh(flipGeo, headMat);
  fr.rotation.x = -Math.PI / 2 + 0.25;
  fr.scale.x = -1;
  const pFR = pivotAt(fr, -0.3 * S, -0.03 * S, 0.3 * S);
  group.add(pFR);
  const rl = new THREE.Mesh(rearGeo, headMat);
  rl.rotation.x = -Math.PI / 2 + 0.2;
  const pRL = pivotAt(rl, 0.26 * S, -0.03 * S, -0.34 * S);
  group.add(pRL);
  const rr = new THREE.Mesh(rearGeo, headMat);
  rr.rotation.x = -Math.PI / 2 + 0.2;
  rr.scale.x = -1;
  const pRR = pivotAt(rr, -0.26 * S, -0.03 * S, -0.34 * S);
  group.add(pRR);
  return {
    group,
    parts: { pectL: pFL, pectR: pFR, rearL: pRL, rearR: pRR },
    mats: [shellMat, skinMat, headMat],
    animMats: [],
    radius: S * 0.5,
  };
}

// --- ray: flat diamond wings on a grid, whip tail, cephalic lobes ---

/** One wing sheet of the ray, sign +1 for topside, -1 for underside. */
function buildRaySheet(S, sign, color) {
  const cols = 14;
  const rows = 9;
  const positions = new Float32Array((cols + 1) * (rows + 1) * 3);
  const colors = new Float32Array((cols + 1) * (rows + 1) * 3);
  const indices = [];
  const col = new THREE.Color(color);
  let p = 0;
  for (let iz = 0; iz <= rows; iz++) {
    const tz = iz / rows;               // 0 nose, 1 rear
    const z = 0.55 * S - tz * 1.05 * S; // nose at +0.55S, rear at -0.5S
    // Diamond planform: widest a third back, tapering to nose and rear.
    const wid = 0.62 * S * Math.sin(Math.PI * Math.pow(clamp01(tz), 0.72));
    for (let ix = 0; ix <= cols; ix++) {
      const tx = ix / cols - 0.5;
      const x = tx * 2 * wid;
      // Slight camber: the body is thicker at the centreline.
      const y = sign * 0.045 * S * Math.cos(tx * Math.PI) * Math.sin(Math.PI * tz) + sign * 0.004 * S;
      positions[p] = x;
      positions[p + 1] = y;
      positions[p + 2] = z;
      colors[p] = col.r;
      colors[p + 1] = col.g;
      colors[p + 2] = col.b;
      p += 3;
    }
  }
  for (let iz = 0; iz < rows; iz++) {
    for (let ix = 0; ix < cols; ix++) {
      const a = iz * (cols + 1) + ix;
      const b = a + cols + 1;
      if (sign > 0) indices.push(a, b, a + 1, b, b + 1, a + 1);
      else indices.push(a, a + 1, b, b, a + 1, b + 1);
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setIndex(indices);
  geo.computeVertexNormals();
  return geo;
}

function buildRay(species, rng) {
  const S = species.size;
  const topGeo = getGeo(species.id + ':top', () => buildRaySheet(S, 1, species.colors[0]));
  const botGeo = getGeo(species.id + ':bot', () => buildRaySheet(S, -1, species.colors[1]));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.6,
    mode: 'flap',
    half: 0.62 * S,
    amp: 0.16 * S,
    speed: 2.1 + rng() * 0.6,
    phase: rng() * Math.PI * 2,
    side: THREE.FrontSide,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(topGeo, bodyMat));
  group.add(new THREE.Mesh(botGeo, bodyMat));
  // Whip tail: a long thin tapered tube trailing behind.
  const tailGeo = getGeo(species.id + ':tailwhip', () => {
    const pts = [];
    for (let i = 0; i <= 8; i++) {
      const t = i / 8;
      pts.push(new THREE.Vector3(0, 0.02 * S * Math.sin(t * 2.2), -0.5 * S - t * 0.85 * S));
    }
    return buildTaperedTube(pts, (t) => 0.02 * S * (1 - t * 0.9), 5, null);
  });
  const darkMat = makeStaticMat({ color: species.colors[2], roughness: 0.6, side: THREE.FrontSide });
  const tailMesh = new THREE.Mesh(tailGeo, darkMat);
  const tail = pivotAt(tailMesh, 0, 0, 0);
  group.add(tail);
  // Cephalic lobes: two forward horns framing the mouth.
  const lobeGeo = getGeo(species.id + ':lobe', () => buildFin([
    [0, 0], [0.16 * S, 0.01 * S], [0.18 * S, -0.05 * S], [0.02 * S, -0.05 * S],
  ]));
  const lobeL = new THREE.Mesh(lobeGeo, darkMat);
  lobeL.rotation.set(0, Math.PI / 2, 0.35);
  lobeL.position.set(0.1 * S, -0.01 * S, 0.56 * S);
  group.add(lobeL);
  const lobeR = new THREE.Mesh(lobeGeo, darkMat);
  lobeR.rotation.set(0, Math.PI / 2, 0.35);
  lobeR.scale.z = -1;
  lobeR.position.set(-0.1 * S, -0.01 * S, 0.56 * S);
  group.add(lobeR);
  addEyePair(group, 0.14 * S, 0.045 * S, 0.42 * S, 0.03 * S);
  return {
    group,
    parts: { tail },
    mats: [bodyMat, darkMat],
    animMats: [bodyMat],
    radius: S * 0.58,
  };
}

// --- eel: long ring chain moray with a continuous dorsal ribbon ---

function buildEel(species, rng) {
  const L = species.size * 1.7; // morays are all length
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 30,
    radial: 10,
    width: (t) => 0.045 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 0.96 + 0.04), 0.42)),
    // Laterally compressed toward the tail, like a ribbon.
    height: (t) => 0.06 * L * (1 + 0.35 * t) * Math.sin(Math.PI * Math.pow(clamp01(t * 0.96 + 0.04), 0.42)),
    color: (t, ny, nx, out) => {
      // Olive skin with pale leopard speckle, lighter throat.
      const sp = hash2(Math.floor(t * 26), Math.floor((ny + 1) * 6 + nx * 2));
      if (ny < -0.55 && t < 0.3) out.copy(c2);
      else if (sp > 0.74) out.copy(c2).lerp(c0, 0.35);
      else if (sp < 0.2) out.copy(c1);
      else out.copy(c0);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.5,
    half: L * 0.5,
    wave: 7.5 / L,
    amp: 0.1 * L,     // whole body slithers
    speed: 4 + rng(),
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  // Continuous dorsal ribbon along the back. The geometry is baked into the
  // body's local frame (not rotated on the mesh) so the shared swim material
  // bends the ribbon exactly like the body underneath it.
  const ribbonGeo = getGeo(species.id + ':ribbon', () => {
    const g = buildFin([
      [-0.48 * L, 0], [0.3 * L, 0], [0.24 * L, 0.045 * L], [-0.2 * L, 0.06 * L], [-0.48 * L, 0.03 * L],
    ]);
    g.rotateY(-Math.PI / 2);
    return g;
  });
  const ribbon = new THREE.Mesh(ribbonGeo, bodyMat);
  ribbon.position.set(0, 0.055 * L, 0);
  group.add(ribbon);
  // Open jaw full of attitude.
  const jawMat = makeStaticMat({ color: 0x1c1410, roughness: 0.9 });
  ensureSharedPrimitives();
  const maw = new THREE.Mesh(UNIT_SPHERE, jawMat);
  maw.position.set(0, -0.01 * L, 0.47 * L);
  maw.scale.set(0.028 * L, 0.02 * L, 0.03 * L);
  group.add(maw);
  const jawGeo = getGeo(species.id + ':jaw', () => buildFin([
    [0, 0], [0.06 * L, 0.006 * L], [0.01 * L, 0.02 * L],
  ]));
  const finMat = makeStaticMat({ color: species.colors[0], roughness: 0.55 });
  const jawMesh = new THREE.Mesh(jawGeo, finMat);
  jawMesh.rotation.y = -Math.PI / 2;
  jawMesh.rotation.x = 0.5;
  const jaw = pivotAt(jawMesh, 0, -0.03 * L, 0.44 * L);
  group.add(jaw);
  addEyePair(group, 0.032 * L, 0.03 * L, 0.42 * L, 0.016 * L);
  return {
    group,
    parts: { jaw },
    mats: [bodyMat, jawMat, finMat],
    animMats: [bodyMat],
    radius: L * 0.22,
  };
}

// --- octopus: bulbous mantle, big eyes, eight curling tentacles ---

function buildOctopus(species, rng) {
  const S = species.size;
  const c0 = new THREE.Color(species.colors[0]);
  const c2 = new THREE.Color(species.colors[2]);
  const group = new THREE.Group();
  const skinMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.85,
    mode: 'pulse',      // gentle whole body breathing
    amp: 0.05,
    speed: 1.6 + rng() * 0.5,
    phase: rng() * Math.PI * 2,
  });
  // Mantle: an egg tilted backward.
  const mantleGeo = getGeo(species.id + ':mantle', () => {
    const geo = new THREE.SphereGeometry(0.3 * S, 14, 10);
    const pos = geo.getAttribute('position');
    const colors = new Float32Array(pos.count * 3);
    const col = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      pos.setY(i, pos.getY(i) * 1.35);
      const mottle = hash2(Math.floor(pos.getX(i) * 30 / S), Math.floor(pos.getY(i) * 30 / S));
      col.copy(c0);
      if (mottle > 0.7) col.lerp(c2, 0.3);
      colors[i * 3] = col.r;
      colors[i * 3 + 1] = col.g;
      colors[i * 3 + 2] = col.b;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    return geo;
  });
  const mantle = new THREE.Mesh(mantleGeo, skinMat);
  mantle.position.set(0, 0.22 * S, -0.14 * S);
  mantle.rotation.x = 0.5;
  group.add(mantle);
  // Head bulge between mantle and arms, carrying the big eyes.
  ensureSharedPrimitives();
  const headMat = makeStaticMat({ color: species.colors[0], roughness: 0.85, side: THREE.FrontSide });
  const head = new THREE.Mesh(UNIT_SPHERE, headMat);
  head.position.set(0, 0.08 * S, 0.08 * S);
  head.scale.set(0.2 * S, 0.16 * S, 0.18 * S);
  group.add(head);
  addEyePair(group, 0.16 * S, 0.13 * S, 0.12 * S, 0.05 * S);
  // Eight tentacles, each its own cached curl so they read organic.
  const tentacles = [];
  const tentRng = makeRandom(4217);
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2 + 0.2;
    const geo = getGeo(species.id + ':tent' + i, () => {
      const pts = [];
      const curl = 0.6 + tentRng() * 0.9;
      const droop = 0.5 + tentRng() * 0.4;
      for (let k = 0; k <= 10; k++) {
        const s = k / 10;
        const reach = (0.1 + 0.78 * s) * S;
        const lift = -droop * 0.42 * S * Math.sin(Math.PI * Math.min(1, s * 1.15))
          + 0.3 * S * Math.pow(s, 3) * Math.sin(s * 6 * curl) * 0.35;
        pts.push(new THREE.Vector3(Math.cos(a) * reach, -0.04 * S + lift, Math.sin(a) * reach));
      }
      return buildTaperedTube(pts, (t) => 0.052 * S * (1 - t * 0.92) + 0.004 * S, 6, (t, col) => {
        col.copy(c0).lerp(c2, 0.2 + 0.3 * t);
      });
    });
    const mesh = new THREE.Mesh(geo, skinMat);
    const pivot = pivotAt(mesh, 0, 0, 0);
    pivot.userData.baseAngle = a;
    group.add(pivot);
    tentacles.push(pivot);
  }
  return {
    group,
    parts: { tentacles },
    mats: [skinMat, headMat],
    animMats: [skinMat],
    radius: S * 0.55,
  };
}

// --- shark family: torpedo body, countershading, crescent tail ---

function buildSharkBase(species, rng, hammer) {
  const L = species.size * 1.45;
  const c0 = new THREE.Color(species.colors[0]); // back
  const c1 = new THREE.Color(species.colors[1]); // belly
  const c2 = new THREE.Color(species.colors[2]); // fin tips / dark accents
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 24,
    radial: 12,
    // Torpedo: girth peaks a third back, long pointed snout, thin caudal peduncle.
    width: (t) => 0.085 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 0.97 + 0.03), 0.62)) * (1 - 0.35 * Math.pow(t, 3)),
    height: (t) => 0.1 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 0.97 + 0.03), 0.6)) * (1 - 0.3 * Math.pow(t, 3)),
    yOff: (t) => 0.012 * L * Math.sin(Math.PI * t),
    color: (t, ny, nx, out) => {
      // Classic countershading with a soft blend at the lateral line.
      if (ny > 0.25) out.copy(c0);
      else if (ny < -0.15) out.copy(c1);
      else out.copy(c0).lerp(c1, (0.25 - ny) / 0.4);
      // Darker snout tip and subtle back mottling.
      if (t < 0.06) out.lerp(c2, 0.25);
      if (ny > 0.4 && hash2(Math.floor(t * 18), Math.floor(nx * 3)) > 0.8) out.lerp(c2, 0.18);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.62,
    half: L * 0.5,
    wave: 3.6 / L,
    amp: 0.045 * L,
    speed: 3.2 + rng(),
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  const finMat = makeStaticMat({ color: species.colors[0], roughness: 0.6 });
  const tipMat = makeStaticMat({ color: species.colors[2], roughness: 0.6 });
  // Tall triangular first dorsal, small second dorsal.
  const dorsalGeo = getGeo(species.id + ':dorsal', () => buildFin([
    [-0.1 * L, 0], [0.08 * L, 0], [-0.06 * L, 0.17 * L], [-0.1 * L, 0.1 * L],
  ]));
  const dorsal = new THREE.Mesh(dorsalGeo, species.id === 'reefshark' ? tipMat : finMat);
  dorsal.rotation.y = -Math.PI / 2;
  dorsal.position.set(0, 0.085 * L, 0.02 * L);
  group.add(dorsal);
  const dorsal2Geo = getGeo(species.id + ':dorsal2', () => buildFin([
    [-0.035 * L, 0], [0.025 * L, 0], [-0.025 * L, 0.05 * L],
  ]));
  const dorsal2 = new THREE.Mesh(dorsal2Geo, finMat);
  dorsal2.rotation.y = -Math.PI / 2;
  dorsal2.position.set(0, 0.055 * L, -0.3 * L);
  group.add(dorsal2);
  // Crescent heterocercal tail: big upper lobe, smaller lower lobe.
  const tail = addTailFin(group, species, species.id + ':tail', [
    [0, 0.01 * L], [-0.16 * L, 0.19 * L], [-0.1 * L, 0.05 * L], [-0.045 * L, 0],
    [-0.11 * L, -0.11 * L], [0, -0.01 * L],
  ], finMat, L * 0.49, 0.01 * L);
  const pect = addPectorals(group, species, species.id + ':pect', [
    [0, 0], [0.2 * L, -0.045 * L], [0.1 * L, -0.09 * L],
  ], finMat, 0.07 * L, -0.045 * L, 0.16 * L);
  // Gill slits: five flattened dark blobs hugging each flank.
  ensureSharedPrimitives();
  const gillMat = makeStaticMat({ color: species.colors[2], roughness: 0.9, side: THREE.FrontSide });
  for (let sgn = -1; sgn <= 1; sgn += 2) {
    for (let i = 0; i < 5; i++) {
      const gz = 0.24 * L - i * 0.022 * L;
      const gill = new THREE.Mesh(UNIT_SPHERE, gillMat);
      gill.position.set(sgn * 0.074 * L, 0.012 * L, gz);
      gill.scale.set(0.004 * L, 0.03 * L, 0.007 * L);
      gill.rotation.z = sgn * 0.2;
      group.add(gill);
    }
  }
  if (hammer) {
    // Cephalofoil: the wide flattened T head with eyes at the tips.
    const foilGeo = getGeo(species.id + ':foil', () => {
      const geo = new THREE.SphereGeometry(1, 12, 6);
      const pos = geo.getAttribute('position');
      const colors = new Float32Array(pos.count * 3);
      for (let i = 0; i < pos.count; i++) {
        // Flatten vertically, stretch across, keep a leading edge sweep.
        const x = pos.getX(i);
        pos.setX(i, x * 0.19 * L);
        pos.setY(i, pos.getY(i) * 0.022 * L);
        pos.setZ(i, pos.getZ(i) * 0.045 * L - Math.abs(x) * 0.03 * L);
        const cc = Math.abs(x) > 0.6 ? c0 : c0;
        colors[i * 3] = cc.r;
        colors[i * 3 + 1] = cc.g;
        colors[i * 3 + 2] = cc.b;
      }
      geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      geo.computeVertexNormals();
      return geo;
    });
    const foil = new THREE.Mesh(foilGeo, bodyMat);
    foil.position.set(0, 0.01 * L, 0.46 * L);
    group.add(foil);
    addEyePair(group, 0.185 * L, 0.012 * L, 0.45 * L, 0.024 * L);
  } else {
    addEyePair(group, 0.06 * L, 0.035 * L, 0.4 * L, 0.022 * L);
  }
  return {
    group,
    parts: { tail, pectL: pect[0], pectR: pect[1] },
    mats: [bodyMat, finMat, tipMat, gillMat],
    animMats: [bodyMat],
    radius: L * 0.28,
  };
}

// --- jelly: translucent pulsing bell, trailing tentacles, inner glow ---

function buildJelly(species, rng, textures) {
  const S = species.size;
  const glow = new THREE.Color(species.glow || species.colors[1]);
  const group = new THREE.Group();
  const bellGeo = getGeo(species.id + ':bell', () => {
    const geo = new THREE.SphereGeometry(0.42 * S, 16, 10, 0, Math.PI * 2, 0, Math.PI * 0.58);
    const pos = geo.getAttribute('position');
    for (let i = 0; i < pos.count; i++) pos.setY(i, pos.getY(i) * 0.8);
    geo.computeVertexNormals();
    return geo;
  });
  const bellMat = makeAnimMaterial({
    color: species.colors[0],
    roughness: 0.3,
    mode: 'pulse',
    amp: 0.22,
    speed: 2.4 + rng() * 0.7,
    phase: rng() * Math.PI * 2,
    transparent: true,
    opacity: 0.42,
    side: THREE.DoubleSide,
    depthWrite: false,
    emissive: species.glow || species.colors[1],
    emissiveIntensity: 0.35,
  });
  const bell = new THREE.Mesh(bellGeo, bellMat);
  group.add(bell);
  // Inner glow sprite: the bioluminescent alarm, tinted with species.glow.
  const glowMat = new THREE.SpriteMaterial({
    map: textures.glow,
    color: glow,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    opacity: 0.85,
  });
  const glowSprite = new THREE.Sprite(glowMat);
  glowSprite.scale.setScalar(0.55 * S);
  glowSprite.position.y = 0.1 * S;
  group.add(glowSprite);
  // Trailing tentacles: thin translucent streamers.
  const tentMat = makeStaticMat({
    color: species.colors[1],
    transparent: true,
    opacity: 0.5,
    roughness: 0.4,
    depthWrite: false,
  });
  const tentacles = [];
  const tRng = makeRandom(9311);
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    const geo = getGeo(species.id + ':tent' + (i % 4), () => {
      const pts = [];
      const sway = tRng() * 2 - 1;
      for (let k = 0; k <= 8; k++) {
        const s = k / 8;
        pts.push(new THREE.Vector3(
          sway * 0.12 * S * Math.sin(s * 3),
          -s * 1.1 * S,
          0.06 * S * Math.sin(s * 4 + sway)
        ));
      }
      return buildTaperedTube(pts, (t) => 0.012 * S * (1 - t * 0.8), 4, null);
    });
    const mesh = new THREE.Mesh(geo, tentMat);
    const pivot = pivotAt(mesh, Math.cos(a) * 0.24 * S, -0.05 * S, Math.sin(a) * 0.24 * S);
    pivot.userData.baseAngle = a;
    group.add(pivot);
    tentacles.push(pivot);
  }
  return {
    group,
    parts: { tentacles, glowSprite },
    mats: [bellMat, glowMat, tentMat],
    animMats: [bellMat],
    radius: S * 0.5,
    upright: true, // jellies keep the bell up instead of facing velocity
  };
}

// --- angler: nightmare head, needle teeth, glowing lure on a stalk ---

function buildAngler(species, rng, textures) {
  const L = species.size * 1.15;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const glow = new THREE.Color(species.glow || species.colors[2]);
  const bodyGeo = getGeo(species.id + ':body', () => buildProfileBody({
    len: L,
    segs: 18,
    radial: 12,
    // Almost all head: girth peaks right behind the mouth then collapses.
    width: (t) => 0.17 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.05 + 0.1), 0.42)) * (1 - 0.55 * t),
    height: (t) => 0.2 * L * Math.sin(Math.PI * Math.pow(clamp01(t * 1.05 + 0.1), 0.42)) * (1 - 0.5 * t),
    color: (t, ny, nx, out) => {
      const warty = hash2(Math.floor(t * 16), Math.floor((ny + 1) * 6));
      out.copy(warty > 0.72 ? c1 : c0);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.9,
    half: L * 0.5,
    wave: 4.5 / L,
    amp: 0.04 * L,
    speed: 2.6 + rng(),
    phase: rng() * Math.PI * 2,
  });
  const group = new THREE.Group();
  group.add(new THREE.Mesh(bodyGeo, bodyMat));
  // Gaping mouth: dark cavity plus two rows of needle teeth.
  ensureSharedPrimitives();
  ensureCone();
  const mawMat = makeStaticMat({ color: 0x0a0508, roughness: 1 });
  const maw = new THREE.Mesh(UNIT_SPHERE, mawMat);
  maw.position.set(0, -0.02 * L, 0.4 * L);
  maw.scale.set(0.13 * L, 0.1 * L, 0.06 * L);
  group.add(maw);
  const toothMat = makeStaticMat({ color: 0xf5f0dc, roughness: 0.3, side: THREE.FrontSide });
  const jawMesh = new THREE.Group();
  for (let i = 0; i < 7; i++) {
    const x = (i / 6 - 0.5) * 0.2 * L;
    const up = new THREE.Mesh(UNIT_CONE, toothMat);
    up.position.set(x, 0.075 * L, 0.02 * L);
    up.rotation.x = Math.PI - 0.35; // hanging down, tilted inward
    up.scale.set(0.008 * L, 0.07 * L * (0.7 + 0.3 * Math.sin(i * 2.1)), 0.008 * L);
    jawMesh.add(up);
    if (i < 6) {
      const dn = new THREE.Mesh(UNIT_CONE, toothMat);
      dn.position.set(x + 0.012 * L, -0.055 * L, 0.02 * L);
      dn.rotation.x = 0.3;
      dn.scale.set(0.008 * L, 0.06 * L * (0.7 + 0.3 * Math.cos(i * 1.7)), 0.008 * L);
      jawMesh.add(dn);
    }
  }
  const jaw = pivotAt(jawMesh, 0, -0.02 * L, 0.38 * L);
  group.add(jaw);
  // Illicium: forehead stalk arcing forward, ending in the glowing lure.
  const stalkGeo = getGeo(species.id + ':stalk', () => {
    const pts = [];
    for (let k = 0; k <= 8; k++) {
      const s = k / 8;
      pts.push(new THREE.Vector3(0, 0.16 * L + 0.24 * L * Math.sin(s * 2.1), 0.3 * L + s * 0.32 * L));
    }
    return buildTaperedTube(pts, (t) => 0.012 * L * (1 - t * 0.7), 4, null);
  });
  const stalkMat = makeStaticMat({ color: species.colors[1], roughness: 0.8, side: THREE.FrontSide });
  const stalkMesh = new THREE.Mesh(stalkGeo, stalkMat);
  const lureMat = new THREE.SpriteMaterial({
    map: textures.glow,
    color: glow,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const lureSprite = new THREE.Sprite(lureMat);
  lureSprite.scale.setScalar(0.45 * L);
  lureSprite.position.set(0, 0.31 * L, 0.62 * L);
  // A real light so the lure carves a halo in the trench (few anglers alive).
  const lureLight = new THREE.PointLight(glow.getHex(), 2.6, 16, 2);
  lureLight.position.copy(lureSprite.position);
  const lure = new THREE.Group();
  lure.add(stalkMesh);
  lure.add(lureSprite);
  lure.add(lureLight);
  group.add(lure);
  addEyePair(group, 0.1 * L, 0.08 * L, 0.3 * L, 0.028 * L);
  return {
    group,
    parts: { jaw, lure, lureLight },
    mats: [bodyMat, mawMat, toothMat, stalkMat, lureMat],
    animMats: [bodyMat],
    radius: L * 0.36,
  };
}

// --- squid: 5 metres of mantle, huge eyes, arms and feeding tentacles ---

function buildSquid(species, rng) {
  const S = species.size;
  const c0 = new THREE.Color(species.colors[0]);
  const c1 = new THREE.Color(species.colors[1]);
  const c2 = new THREE.Color(species.colors[2]);
  const group = new THREE.Group();
  // Mantle: long torpedo pointing backward (arms forward at +Z).
  const mantleGeo = getGeo(species.id + ':mantle', () => buildProfileBody({
    len: 0.72 * S,
    segs: 16,
    radial: 12,
    width: (t) => 0.1 * S * Math.sin(Math.PI * Math.pow(clamp01(1 - t), 0.55)),
    height: (t) => 0.1 * S * Math.sin(Math.PI * Math.pow(clamp01(1 - t), 0.55)),
    color: (t, ny, nx, out) => {
      const fleck = hash2(Math.floor(t * 22), Math.floor((ny + 1) * 7));
      out.copy(fleck > 0.8 ? c1 : c0);
      if (ny < -0.4) out.lerp(c2, 0.25);
    },
  }));
  const bodyMat = makeAnimMaterial({
    vertexColors: true,
    roughness: 0.55,
    half: 0.36 * S,
    wave: 6 / S,
    amp: 0.02 * S,
    speed: 2.2 + rng() * 0.6,
    phase: rng() * Math.PI * 2,
  });
  const mantle = new THREE.Mesh(mantleGeo, bodyMat);
  mantle.position.z = -0.28 * S;
  group.add(mantle);
  // Rear fin: a wide rhombus at the mantle tip.
  const finGeo = getGeo(species.id + ':fin', () => buildFin([
    [0.1 * S, 0], [-0.06 * S, 0.16 * S], [-0.14 * S, 0], [-0.06 * S, -0.16 * S],
  ]));
  const finMat = makeStaticMat({ color: species.colors[0], roughness: 0.55 });
  const rearFin = new THREE.Mesh(finGeo, finMat);
  rearFin.rotation.x = -Math.PI / 2;
  rearFin.position.set(0, 0, -0.56 * S);
  group.add(rearFin);
  // Head with the biggest eyes in the animal kingdom.
  ensureSharedPrimitives();
  const headMat = makeStaticMat({ color: species.colors[0], roughness: 0.6, side: THREE.FrontSide });
  const head = new THREE.Mesh(UNIT_SPHERE, headMat);
  head.position.set(0, 0, 0.12 * S);
  head.scale.set(0.09 * S, 0.09 * S, 0.08 * S);
  group.add(head);
  addEyePair(group, 0.075 * S, 0.01 * S, 0.13 * S, 0.045 * S);
  // Eight arms forward, plus two much longer clubbed feeding tentacles.
  const tentacles = [];
  const tRng = makeRandom(7789);
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2 + 0.39;
    const geo = getGeo(species.id + ':arm' + i, () => {
      const pts = [];
      const wobble = tRng() * 2 - 1;
      for (let k = 0; k <= 9; k++) {
        const s = k / 9;
        const spread = 0.075 * S * (1 - s * 0.55);
        pts.push(new THREE.Vector3(
          Math.cos(a) * spread + wobble * 0.03 * S * Math.sin(s * 5),
          Math.sin(a) * spread,
          0.16 * S + s * 0.42 * S
        ));
      }
      return buildTaperedTube(pts, (t) => 0.026 * S * (1 - t * 0.85) + 0.003 * S, 5, (t, col) => {
        col.copy(c0).lerp(c2, t * 0.3);
      });
    });
    const mesh = new THREE.Mesh(geo, bodyMat);
    const pivot = pivotAt(mesh, 0, 0, 0);
    pivot.userData.baseAngle = a;
    group.add(pivot);
    tentacles.push(pivot);
  }
  const clubMat = makeStaticMat({ color: species.colors[2], roughness: 0.5, side: THREE.FrontSide });
  for (let i = 0; i < 2; i++) {
    const sgn = i === 0 ? 1 : -1;
    const geo = getGeo(species.id + ':feed' + i, () => {
      const pts = [];
      for (let k = 0; k <= 10; k++) {
        const s = k / 10;
        pts.push(new THREE.Vector3(
          sgn * (0.05 * S + 0.05 * S * Math.sin(s * 2.6)),
          -0.02 * S - 0.04 * S * Math.sin(s * 3.1),
          0.16 * S + s * 0.8 * S
        ));
      }
      return buildTaperedTube(pts, (t) => 0.016 * S * (1 - t * 0.6), 5, (t, col) => {
        col.copy(c0).lerp(c1, t * 0.4);
      });
    });
    const mesh = new THREE.Mesh(geo, bodyMat);
    // Clubbed end of the feeding tentacle.
    const club = new THREE.Mesh(UNIT_SPHERE, clubMat);
    club.position.set(sgn * 0.1 * S, -0.055 * S, 0.96 * S);
    club.scale.set(0.02 * S, 0.03 * S, 0.06 * S);
    const pivot = pivotAt(mesh, 0, 0, 0);
    pivot.add(club);
    pivot.userData.baseAngle = sgn * 0.5;
    group.add(pivot);
    tentacles.push(pivot);
  }
  return {
    group,
    parts: { tentacles },
    mats: [bodyMat, finMat, headMat, clubMat],
    animMats: [bodyMat],
    radius: S * 0.4,
  };
}

// --- registry ---

const BUILDERS = {
  reeffish: buildReeffish,
  bulkfish: buildBulkfish,
  sleekfish: buildSleekfish,
  lionfish: buildLionfish,
  turtle: buildTurtle,
  ray: buildRay,
  eel: buildEel,
  octopus: buildOctopus,
  shark: (s, r, t) => buildSharkBase(s, r, false),
  hammerhead: (s, r, t) => buildSharkBase(s, r, true),
  jelly: buildJelly,
  angler: buildAngler,
  squid: buildSquid,
};

// ---------------------------------------------------------------------------
// Material pooling for schooling fish
//
// Geometry is already shared per species through geoCache. For school species
// we additionally cycle through a small pool of material sets so 16 tangs use
// 4 material instances (4 distinct swim phases) instead of 16.
// ---------------------------------------------------------------------------

const MAT_POOL_SIZE = 4;
const matPools = new Map(); // speciesId -> { sets: [{mats, animMats}], next }

function acquirePooledMats(species, res) {
  let pool = matPools.get(species.id);
  if (!pool) {
    pool = { sets: [], next: 0 };
    matPools.set(species.id, pool);
  }
  if (pool.sets.length < MAT_POOL_SIZE) {
    // This creature's freshly built materials become a pool slot.
    pool.sets.push({ mats: res.mats, animMats: res.animMats });
    res.pooled = true;
    return res;
  }
  const set = pool.sets[pool.next];
  pool.next = (pool.next + 1) % pool.sets.length;
  const remap = new Map();
  for (let i = 0; i < res.mats.length; i++) remap.set(res.mats[i], set.mats[i]);
  res.group.traverse((o) => {
    if ((o.isMesh || o.isSprite) && remap.has(o.material)) o.material = remap.get(o.material);
  });
  for (const m of res.mats) m.dispose();
  res.mats = set.mats;
  res.animMats = set.animMats;
  res.pooled = true;
  return res;
}

/** Builds the full visual for one creature of a species. */
function buildCreatureMesh(species, rng, textures) {
  const builder = BUILDERS[species.body];
  let res = builder(species, rng, textures);
  if (species.behaviour === 'school') res = acquirePooledMats(species, res);
  return res;
}

// ---------------------------------------------------------------------------
// Fauna factory
// ---------------------------------------------------------------------------

export function createFauna(scene, world, textures) {
  const group = new THREE.Group();
  group.name = 'fauna';
  scene.add(group);

  const rng = makeRandom(1379);
  const creatures = [];
  const specimens = [];
  const schools = [];
  let uidCounter = 1;
  let timeNow = 0;
  let nextChargeAt = 0;
  const lastCamDir = new THREE.Vector3(0, 0, -1);
  const lastPlayerPos = new THREE.Vector3(0, -10, 0);

  /** Calls a user callback defensively: never throws into the sim loop. */
  function emit(cb, a, b) {
    if (typeof cb !== 'function') return;
    try {
      cb(a, b);
    } catch (err) {
      console.error('[fauna] callback error', err);
    }
  }

  // -------------------------------------------------------------------------
  // Spawning
  // -------------------------------------------------------------------------

  /** Ceiling for a species: surfacers may kiss the surface, others stay down. */
  function ceilingFor(species) {
    return SURFACERS[species.id] ? SURFACE_Y : CEILING_Y;
  }

  /** Clamps a target y between the terrain and the species ceiling. */
  function clampDepthY(species, x, z, y) {
    const floor = world.heightAt(x, z) + 1.2;
    const lo = Math.max(floor, -(species.depth[1]));
    const hi = Math.min(ceilingFor(species), -(species.depth[0]) + 6);
    return clamp(y, lo, Math.max(lo, hi));
  }

  function spawnCreature(species, pos, school) {
    const res = buildCreatureMesh(species, rng, textures);
    const object = res.group;
    object.position.copy(pos);
    object.rotation.y = rng() * Math.PI * 2;
    group.add(object);
    const creature = {
      // --- contract fields ---
      uid: uidCounter++,
      speciesId: species.id,
      species,
      object,
      position: object.position,
      velocity: new THREE.Vector3((rng() - 0.5) * 0.5, 0, (rng() - 0.5) * 0.5),
      health: species.health,
      maxHealth: species.health,
      alive: true,
      state: 'idle',
      radius: res.radius,
      danger: species.danger,
      // --- internals ---
      parts: res.parts,
      mats: res.mats,
      animMats: res.animMats,
      pooled: !!res.pooled,
      upright: !!res.upright,
      home: pos.clone(),
      school: school || null,
      mode: 'patrol',
      modeT: rng() * 3,
      stunT: 0,
      fleeT: 0,
      cooldownT: rng() * 2,
      contactT: 0,
      investigateT: 0,
      phase: rng() * Math.PI * 2,
      wander: pos.clone(),
      wanderT: 0,
      orbitDir: rng() < 0.5 ? -1 : 1,
      deathT: 0,
      hitPopT: 0,
      frozenT: rng() * FROZEN_TICK,
      pendingSpecimen: null,
      distToPlayer: 999,
    };
    if (school) school.members.push(creature);
    creatures.push(creature);
    return creature;
  }

  /** Spawns a whole group (school, pair or single) of a species around pos. */
  function spawnGroup(species, pos) {
    const lo = species.schoolSize[0];
    const hi = species.schoolSize[1];
    const count = lo + Math.floor(rng() * (hi - lo + 1));
    let school = null;
    if (species.behaviour === 'school') {
      school = {
        members: [],
        center: pos.clone(),
        target: pos.clone(),
        avgVel: new THREE.Vector3(),
        retargetT: 0,
        fleeT: 0,
        fleeDir: new THREE.Vector3(1, 0, 0),
      };
      schools.push(school);
    }
    const spread = species.behaviour === 'school' ? 2.5 + count * 0.25 : 5;
    for (let i = 0; i < count; i++) {
      if (creatures.length >= MAX_CREATURES) break;
      _v1.set(
        pos.x + (rng() - 0.5) * spread,
        pos.y + (rng() - 0.5) * spread * 0.5,
        pos.z + (rng() - 0.5) * spread
      );
      _v1.y = clampDepthY(species, _v1.x, _v1.z, _v1.y);
      spawnCreature(species, _v1, school);
    }
  }

  /** Picks a spawn point for a species near the player, out of close sight. */
  function pickSpawnPos(species, playerPos, biome) {
    for (let attempt = 0; attempt < 10; attempt++) {
      const p = world.randomSpawn(biome, rng);
      if (!p) continue;
      _v2.set(p.x - playerPos.x, 0, p.z - playerPos.z);
      const d = _v2.length();
      if (d < MIN_SPAWN_DIST || d > MAX_SPAWN_DIST) continue;
      // Prefer points outside the player's forward cone.
      if (attempt < 6 && d < 90) {
        _v2.multiplyScalar(1 / d);
        if (_v2.dot(lastCamDir) > 0.55) continue;
      }
      const targetDepth = lerp(species.depth[0], species.depth[1], rng());
      const y = clampDepthY(species, p.x, p.z, -targetDepth);
      return _v3.set(p.x, y, p.z);
    }
    return null;
  }

  // -------------------------------------------------------------------------
  // Specimens
  // -------------------------------------------------------------------------

  function makeSpecimen(species, pos) {
    const rarity = new THREE.Color(RARITY_COLOR[species.rarity] || '#ffffff');
    const object = new THREE.Group();
    object.position.copy(pos);
    const mats = [];
    // Soft glowing capsule shell.
    const capGeo = getGeo('specimen:capsule', () => new THREE.CapsuleGeometry(0.34, 0.34, 4, 12));
    const capMat = makeStaticMat({
      color: 0xffffff,
      transparent: true,
      opacity: 0.22,
      roughness: 0.15,
      emissive: rarity.getHex(),
      emissiveIntensity: 0.8,
      depthWrite: false,
      side: THREE.FrontSide,
    });
    mats.push(capMat);
    const capsule = new THREE.Mesh(capGeo, capMat);
    object.add(capsule);
    // Tiny live version of the species floating inside.
    const mini = buildCreatureMesh(species, rng, textures);
    const miniScale = 0.24 / Math.max(mini.radius, 0.001);
    mini.group.scale.setScalar(Math.min(miniScale, 1));
    // Turn off the angler's real light inside the capsule.
    if (mini.parts && mini.parts.lureLight) mini.parts.lureLight.intensity = 0;
    object.add(mini.group);
    // Rotating rarity ring.
    const ringGeo = getGeo('specimen:ring', () => new THREE.TorusGeometry(0.52, 0.028, 6, 26));
    const ringMat = new THREE.MeshBasicMaterial({
      color: rarity,
      transparent: true,
      opacity: 0.9,
      depthWrite: false,
    });
    mats.push(ringMat);
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    object.add(ring);
    // Long range glow sprite so it reads through the fog and the dark.
    const glowMat = new THREE.SpriteMaterial({
      map: textures.glow,
      color: rarity,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.9,
    });
    mats.push(glowMat);
    const glow = new THREE.Sprite(glowMat);
    glow.scale.setScalar(2.6);
    object.add(glow);
    // A small rarity coloured light, capped so we never stack too many.
    let light = null;
    if (specimens.length < 8) {
      light = new THREE.PointLight(rarity.getHex(), 1.4, 9, 2);
      object.add(light);
    }
    object.visible = false; // revealed when the death tumble finishes
    group.add(object);
    const specimen = {
      uid: uidCounter++,
      speciesId: species.id,
      species,
      object,
      position: object.position,
      value: species.value,
      collected: false,
      // internals
      _mats: mats,
      _mini: mini,
      _ring: ring,
      _bob: rng() * Math.PI * 2,
      _riseTo: Math.min(pos.y + 2.4, -2.2),
      _spin: 0.6 + rng() * 0.5,
    };
    specimens.push(specimen);
    return specimen;
  }

  function disposeSpecimenVisual(sp) {
    group.remove(sp.object);
    for (const m of sp._mats) m.dispose();
    if (sp._mini && !sp._mini.pooled) {
      for (const m of sp._mini.mats) m.dispose();
    }
  }

  // -------------------------------------------------------------------------
  // Steering and environment helpers
  // -------------------------------------------------------------------------

  /** Smoothly turns the velocity toward a desired direction and speed. */
  function steer(c, dirX, dirY, dirZ, speed, dt, rate) {
    const len = Math.sqrt(dirX * dirX + dirY * dirY + dirZ * dirZ);
    if (len < 1e-5) return;
    const k = springK(rate, dt);
    const inv = speed / len;
    c.velocity.x += (dirX * inv - c.velocity.x) * k;
    c.velocity.y += (dirY * inv - c.velocity.y) * k;
    c.velocity.z += (dirZ * inv - c.velocity.z) * k;
  }

  /** Keeps a creature off the seabed, under the ceiling, inside the bounds. */
  function applyEnvironment(c, dt, full) {
    const px = c.position.x;
    const pz = c.position.z;
    // Terrain: look a little ahead so creatures climb slopes early.
    const aheadX = px + c.velocity.x * 1.1;
    const aheadZ = pz + c.velocity.z * 1.1;
    const h = Math.max(world.heightAt(px, pz), world.heightAt(aheadX, aheadZ));
    const minY = h + c.radius + 0.9;
    if (c.position.y < minY) {
      c.velocity.y += (minY - c.position.y) * 6 * dt;
      if (c.position.y < minY - 0.5) c.position.y += (minY - 0.5 - c.position.y) * Math.min(1, 5 * dt);
    }
    // Ceiling.
    const ceil = ceilingFor(c.species) - c.radius * 0.5;
    if (c.position.y > ceil) {
      c.position.y = ceil;
      if (c.velocity.y > 0) c.velocity.y *= -0.3;
    }
    // Soft world bounds: steer back toward the centre.
    const r2 = px * px + pz * pz;
    const softR = WORLD.boundsRadius - 30;
    if (r2 > softR * softR) {
      const r = Math.sqrt(r2);
      const push = (r - softR) * 0.4;
      c.velocity.x -= (px / r) * push * dt * 8;
      c.velocity.z -= (pz / r) * push * dt * 8;
    }
    // Solid props (rocks, wreck, island): only for the full LOD tier.
    if (full) {
      const fix = world.collide(c.position, c.radius);
      if (fix) {
        c.position.add(fix);
        c.velocity.addScaledVector(fix, 2.5);
      }
    }
  }

  /** Orients the mesh: fish face their velocity, jellies stay upright. */
  function orient(c, dt, rate) {
    if (c.upright) {
      // Gentle bell sway around upright.
      c.object.rotation.x = Math.sin(timeNow * 0.6 + c.phase) * 0.12;
      c.object.rotation.z = Math.cos(timeNow * 0.5 + c.phase) * 0.12;
      return;
    }
    _v4.copy(c.velocity);
    _v4.y *= 0.75; // fish bank less vertically than they climb
    if (_v4.lengthSq() < 1e-4) return;
    _v4.normalize();
    _m4.lookAt(_v4, _zero, _up); // +Z of the object ends up along _v4
    _q1.setFromRotationMatrix(_m4);
    c.object.quaternion.slerp(_q1, springK(rate, dt));
  }

  /** Feeds swim speed into the GPU uniforms (tail beats faster when rushing). */
  function setSwimIntensity(c, dt) {
    const sp = c.velocity.length();
    const norm = clamp01(sp / Math.max(c.species.speed, 0.1));
    for (let i = 0; i < c.animMats.length; i++) {
      const u = c.animMats[i].userData.u;
      if (!u) continue;
      const targetSpeed = (c.upright ? 2.2 : 3.2) + norm * 7;
      u.uSpeed.value += (targetSpeed - u.uSpeed.value) * Math.min(1, dt * 3);
    }
  }

  /** CPU part animation: tails, fins, tentacles, lure, jaw. Full LOD only. */
  function animateParts(c, dt) {
    const p = c.parts;
    if (!p) return;
    const sp = clamp01(c.velocity.length() / Math.max(c.species.speed, 0.1));
    const t = timeNow;
    if (p.tail) p.tail.rotation.y = Math.sin(t * (4 + sp * 6) + c.phase) * (0.22 + sp * 0.25);
    if (p.pectL) {
      const flap = Math.sin(t * 2.6 + c.phase) * 0.28;
      p.pectL.rotation.z = flap;
      p.pectR.rotation.z = -flap;
      if (p.rearL) {
        p.rearL.rotation.z = -flap * 0.6;
        p.rearR.rotation.z = flap * 0.6;
      }
    }
    if (p.tentacles) {
      for (let i = 0; i < p.tentacles.length; i++) {
        const tp = p.tentacles[i];
        tp.rotation.x = Math.sin(t * 1.4 + c.phase + i * 0.9) * 0.14;
        tp.rotation.z = Math.cos(t * 1.1 + c.phase + i * 1.3) * 0.12;
      }
    }
    if (p.lure) {
      // The illicium swings like a slow pendulum to hypnotise prey.
      p.lure.rotation.z = Math.sin(t * 1.3 + c.phase) * 0.3;
      p.lure.rotation.x = Math.cos(t * 0.9 + c.phase) * 0.15;
      if (p.lureLight) p.lureLight.intensity = 2.2 + Math.sin(t * 5 + c.phase) * 0.8;
    }
    if (p.jaw) {
      // The jaw gapes during an attack, otherwise breathes slightly.
      const opening = (c.mode === 'charge' || c.mode === 'lunge') ? 0.7 : 0.08 + Math.sin(t * 1.8 + c.phase) * 0.05;
      p.jaw.rotation.x += (opening - p.jaw.rotation.x) * Math.min(1, dt * 8);
    }
    // Hit reaction pop: a quick scale pulse, works for pooled materials too.
    if (c.hitPopT > 0) {
      c.hitPopT -= dt;
      const s = 1 + Math.max(0, c.hitPopT) * 0.9;
      c.object.scale.setScalar(s);
      if (c.hitPopT <= 0) c.object.scale.setScalar(1);
    }
  }

  /** Repicks a wander target around an anchor within the species depth band. */
  function repickWander(c, anchor, range) {
    const a = rng() * Math.PI * 2;
    const r = range * (0.3 + rng() * 0.7);
    c.wander.set(anchor.x + Math.cos(a) * r, anchor.y + (rng() - 0.5) * range * 0.5, anchor.z + Math.sin(a) * r);
    c.wander.y = clampDepthY(c.species, c.wander.x, c.wander.z, c.wander.y);
    c.wanderT = 5 + rng() * 8;
  }

  // -------------------------------------------------------------------------
  // Behaviour: school (boids)
  // -------------------------------------------------------------------------

  /** Per school bookkeeping: centre, average velocity, wander target, panic. */
  function updateSchools(dt, ctx) {
    for (let i = schools.length - 1; i >= 0; i--) {
      const s = schools[i];
      // Compact away dead members in place.
      let w = 0;
      for (let j = 0; j < s.members.length; j++) {
        if (s.members[j].alive) s.members[w++] = s.members[j];
      }
      s.members.length = w;
      if (w === 0) {
        schools.splice(i, 1);
        continue;
      }
      s.center.set(0, 0, 0);
      s.avgVel.set(0, 0, 0);
      for (let j = 0; j < w; j++) {
        s.center.add(s.members[j].position);
        s.avgVel.add(s.members[j].velocity);
      }
      s.center.multiplyScalar(1 / w);
      s.avgVel.multiplyScalar(1 / w);
      // Group wander target.
      s.retargetT -= dt;
      if (s.retargetT <= 0) {
        const sp = s.members[0].species;
        const a = rng() * Math.PI * 2;
        const r = 14 + rng() * 30;
        s.target.set(s.center.x + Math.cos(a) * r, s.center.y + (rng() - 0.5) * 10, s.center.z + Math.sin(a) * r);
        s.target.y = clampDepthY(sp, s.target.x, s.target.z, s.target.y);
        // Keep targets inside the world.
        const tr = Math.hypot(s.target.x, s.target.z);
        const maxR = WORLD.boundsRadius - 60;
        if (tr > maxR) {
          s.target.x *= maxR / tr;
          s.target.z *= maxR / tr;
        }
        s.retargetT = 7 + rng() * 9;
      }
      // Panic: the player got too close, is noisy, or just fired.
      if (ctx.playerVisible) {
        _v1.subVectors(s.center, ctx.playerPos);
        const d = _v1.length();
        const panicRadius = 6 + ctx.noise * 12;
        if (d < panicRadius && d > 1e-4) {
          s.fleeT = 2.2;
          s.fleeDir.copy(_v1).multiplyScalar(1 / d);
        }
      }
      if (s.fleeT > 0) s.fleeT -= dt;
    }
  }

  function updateSchoolMember(c, dt, ctx, full) {
    const s = c.school;
    const sp = c.species;
    if (!s) {
      updateDrifter(c, dt, ctx, full);
      return;
    }
    const fleeing = s.fleeT > 0 || c.fleeT > 0;
    c.state = fleeing ? 'flee' : 'idle';
    if (!full) {
      // Cheap tier: head for the group target with a personal sine offset.
      _v1.subVectors(s.target, c.position);
      _v1.x += Math.sin(timeNow * 0.9 + c.phase) * 3;
      _v1.y += Math.sin(timeNow * 0.7 + c.phase * 2) * 1.2;
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * (fleeing ? 1.7 : 0.7), dt, 2.2);
      return;
    }
    // Boids: separation, alignment, cohesion, target pull, panic flee.
    let sepX = 0;
    let sepY = 0;
    let sepZ = 0;
    const sepDist = Math.max(sp.size * 2.2, 0.7);
    const sepSq = sepDist * sepDist;
    for (let j = 0; j < s.members.length; j++) {
      const o = s.members[j];
      if (o === c) continue;
      const dx = c.position.x - o.position.x;
      const dy = c.position.y - o.position.y;
      const dz = c.position.z - o.position.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < sepSq && d2 > 1e-6) {
        const f = (sepSq - d2) / sepSq / Math.sqrt(d2);
        sepX += dx * f;
        sepY += dy * f;
        sepZ += dz * f;
      }
    }
    _v1.subVectors(s.target, c.position).normalize();          // group goal
    _v2.subVectors(s.center, c.position).multiplyScalar(0.12); // cohesion
    _v3.copy(s.avgVel).multiplyScalar(0.22);                   // alignment
    let dirX = _v1.x + _v2.x + _v3.x + sepX * 2.2;
    let dirY = _v1.y + _v2.y + _v3.y + sepY * 2.2;
    let dirZ = _v1.z + _v2.z + _v3.z + sepZ * 2.2;
    let speed = sp.speed * (0.62 + 0.18 * Math.sin(timeNow * 0.8 + c.phase));
    if (fleeing) {
      dirX = s.fleeDir.x * 3 + sepX;
      dirY = s.fleeDir.y * 1.2 + 0.3;
      dirZ = s.fleeDir.z * 3 + sepZ;
      speed = sp.speed * 1.85;
      c.state = 'flee';
    }
    steer(c, dirX, dirY, dirZ, speed, dt, fleeing ? 5 : 3.2);
  }

  // -------------------------------------------------------------------------
  // Behaviour: drifter
  // -------------------------------------------------------------------------

  function updateDrifter(c, dt, ctx, full) {
    const sp = c.species;
    c.state = c.fleeT > 0 ? 'flee' : 'idle';
    c.wanderT -= dt;
    if (c.wanderT <= 0) repickWander(c, c.position, 22);
    if (sp.body === 'jelly') {
      // Pulse cycle: each bell contraction pushes the jelly up and along.
      const u = c.animMats.length ? c.animMats[0].userData.u : null;
      const pulseSpeed = u ? u.uSpeed.value : 2.4;
      const contraction = Math.max(0, Math.sin(timeNow * pulseSpeed + (u ? u.uPhase.value : c.phase)));
      c.velocity.y += (contraction * 1.5 - 0.55) * dt;
      // Lazy lateral drift toward the wander point.
      const dx = c.wander.x - c.position.x;
      const dz = c.wander.z - c.position.z;
      c.velocity.x += clamp(dx, -1, 1) * 0.12 * dt;
      c.velocity.z += clamp(dz, -1, 1) * 0.12 * dt;
      // Stay inside the species depth band.
      const hi = -(sp.depth[0]);
      const lo = -(sp.depth[1]);
      if (c.position.y > hi) c.velocity.y -= dt * 0.8;
      if (c.position.y < lo) c.velocity.y += dt * 0.8;
      c.velocity.multiplyScalar(1 - Math.min(1, dt * 0.5));
    } else {
      // Turtles, mantas, lionfish: slow cruise with a vertical bob.
      _v1.subVectors(c.wander, c.position);
      _v1.y += Math.sin(timeNow * 0.7 + c.phase) * 0.8;
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 0.62, dt, 1.6);
    }
    // Gently veer away if the player bumps into them.
    if (full && ctx.playerVisible) {
      _v2.subVectors(c.position, ctx.playerPos);
      const d = _v2.length();
      if (d < 3.2 && d > 1e-4) {
        c.velocity.addScaledVector(_v2, (3.2 - d) * dt * 3 / d);
      }
    }
  }

  // -------------------------------------------------------------------------
  // Behaviour: solo (territorial patrol, curious at range)
  // -------------------------------------------------------------------------

  function updateSolo(c, dt, ctx, full) {
    const sp = c.species;
    c.state = c.fleeT > 0 ? 'flee' : 'idle';
    const distP = c.distToPlayer;
    if (c.mode !== 'investigate' && c.mode !== 'backoff') c.mode = 'patrol';
    if (c.mode === 'patrol') {
      c.wanderT -= dt;
      if (c.wanderT <= 0) repickWander(c, c.home, 13);
      _v1.subVectors(c.wander, c.position);
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 0.55, dt, 1.8);
      if (full && ctx.playerVisible && distP < 19 && distP > 7) {
        c.mode = 'investigate';
        c.investigateT = 5 + rng() * 5;
      }
    } else if (c.mode === 'investigate') {
      // Curious: approach the diver, but keep a respectful distance.
      c.investigateT -= dt;
      _v1.subVectors(ctx.playerPos, c.position);
      const d = Math.max(_v1.length(), 1e-4);
      if (d > 7.5) steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 0.7, dt, 2.2);
      else if (d < 5) steer(c, -_v1.x, -_v1.y * 0.4, -_v1.z, sp.speed * 0.8, dt, 2.6);
      else steer(c, -_v1.z * c.orbitDir, 0, _v1.x * c.orbitDir, sp.speed * 0.45, dt, 2);
      if (c.investigateT <= 0 || !ctx.playerVisible || d > 26) {
        c.mode = 'backoff';
        c.investigateT = 3;
      }
    } else {
      // Drift back toward home ground.
      c.investigateT -= dt;
      _v1.subVectors(c.home, c.position);
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 0.6, dt, 1.8);
      if (c.investigateT <= 0 || _v1.lengthSq() < 4) c.mode = 'patrol';
    }
  }

  // -------------------------------------------------------------------------
  // Behaviour: ambush (moray in its hole, angler with its lure)
  // -------------------------------------------------------------------------

  function updateAmbush(c, dt, ctx, full) {
    const sp = c.species;
    const aggro = (sp.aggroRange || 8) * (1 + ctx.noise * 0.4 + ctx.bleeding * 0.8);
    if (c.mode !== 'lunge' && c.mode !== 'retreat') c.mode = 'wait';
    if (c.mode === 'wait') {
      c.state = c.fleeT > 0 ? 'flee' : 'idle';
      // Nearly still: a soft sway, pinned against the den.
      _v1.subVectors(c.home, c.position);
      steer(c, _v1.x, _v1.y, _v1.z, Math.min(sp.speed * 0.5, _v1.length() * 2), dt, 3);
      c.velocity.x += Math.sin(timeNow * 0.8 + c.phase) * 0.05 * dt;
      // Hard anchor: never drift far from the hole while waiting.
      if (_v1.lengthSq() > 9) c.position.addScaledVector(_v1, Math.min(1, dt * 2));
      if (full && ctx.playerVisible && c.cooldownT <= 0 && c.distToPlayer < aggro) {
        c.mode = 'lunge';
        c.modeT = 0;
        c.state = 'attack';
      }
    } else if (c.mode === 'lunge') {
      c.state = 'attack';
      c.modeT += dt;
      _v1.subVectors(ctx.playerPos, c.position);
      const d = _v1.length();
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 2.1, dt, 7);
      if (d < c.radius + DIVER.radius + 0.7) {
        emit(fauna.onDiverAttacked, c, sp.contactDamage || 10);
        c.cooldownT = sp.attackCooldown || 3;
        c.mode = 'retreat';
      } else if (c.modeT > 2.4 || d > aggro * 1.6 || !ctx.playerVisible) {
        c.mode = 'retreat';
        c.cooldownT = Math.max(c.cooldownT, 1.2);
      }
    } else {
      // Retreat: slide back into the den tail first.
      c.state = 'idle';
      _v1.subVectors(c.home, c.position);
      steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 1.2, dt, 4);
      if (_v1.lengthSq() < 1.4) c.mode = 'wait';
    }
  }

  // -------------------------------------------------------------------------
  // Behaviour: predator (patrol, aware, circle, charge, bite, reset)
  // -------------------------------------------------------------------------

  function updatePredator(c, dt, ctx, full) {
    const sp = c.species;
    const aggro = sp.aggroRange * (1 + ctx.noise * 0.6 + ctx.bleeding * 1.2);
    const distP = c.distToPlayer;
    const seen = ctx.playerVisible && distP < aggro;
    c.modeT += dt;
    switch (c.mode) {
      case 'patrol': {
        c.state = 'idle';
        c.wanderT -= dt;
        if (c.wanderT <= 0) repickWander(c, c.position, 34);
        _v1.subVectors(c.wander, c.position);
        steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 0.5, dt, 1.6);
        if (full && seen) {
          c.mode = 'aware';
          c.modeT = 0;
        }
        break;
      }
      case 'aware': {
        // Turn toward the diver and close in slowly, sizing it up.
        c.state = 'hunt';
        _v1.subVectors(ctx.playerPos, c.position);
        steer(c, _v1.x, _v1.y * 0.6, _v1.z, sp.speed * 0.65, dt, 2.4);
        if (!ctx.playerVisible || distP > aggro * 1.5) {
          c.mode = 'patrol';
        } else if (c.modeT > 2.2 || distP < 20) {
          c.mode = 'circle';
          c.modeT = 0;
          c.circleR = Math.min(Math.max(distP, 11), 17);
          c.circleHold = 3 + rng() * 4;
        }
        break;
      }
      case 'circle': {
        // Orbit the diver, closing slowly: the tension builder.
        c.state = 'hunt';
        c.circleR = Math.max(7.5, c.circleR - dt * 0.75);
        _v1.subVectors(c.position, ctx.playerPos);
        _v1.y = 0;
        const d = Math.max(_v1.length(), 1e-4);
        // Tangential direction plus a radial correction toward the ring.
        const tx = -_v1.z * c.orbitDir;
        const tz = _v1.x * c.orbitDir;
        const radial = (c.circleR - d) * 0.35;
        const dy = (ctx.playerPos.y + Math.sin(timeNow * 0.5 + c.phase) * 2 - c.position.y) * 0.4;
        steer(c, tx / d + (_v1.x / d) * radial, dy, tz / d + (_v1.z / d) * radial, sp.speed * 0.85, dt, 3);
        if (!ctx.playerVisible || distP > aggro * 1.7) {
          c.mode = 'patrol';
        } else if (c.modeT > c.circleHold && c.cooldownT <= 0 && timeNow >= nextChargeAt) {
          // Stagger charges so a pack never rushes all at once.
          nextChargeAt = timeNow + CHARGE_STAGGER;
          c.mode = 'charge';
          c.modeT = 0;
        }
        break;
      }
      case 'charge': {
        // Full speed straight run at where the diver is about to be.
        c.state = 'attack';
        _v1.copy(ctx.playerPos).addScaledVector(ctx.playerVel, 0.3).sub(c.position);
        steer(c, _v1.x, _v1.y, _v1.z, sp.speed * 1.9, dt, 6.5);
        const reach = c.radius + DIVER.radius + 0.8;
        if (distP < reach && ctx.playerVisible) {
          // Bite: deal damage, then veer off hard.
          emit(fauna.onDiverAttacked, c, sp.contactDamage || 15);
          _v2.subVectors(c.position, ctx.playerPos).normalize();
          _v2.y += 0.4;
          c.velocity.copy(_v2).multiplyScalar(sp.speed * 1.4);
          c.cooldownT = sp.attackCooldown || 3;
          c.mode = 'reset';
          c.modeT = 0;
        } else if (c.modeT > 3 || !ctx.playerVisible) {
          c.mode = 'reset';
          c.modeT = 0;
          c.cooldownT = Math.max(c.cooldownT, 1.5);
        }
        break;
      }
      case 'reset':
      default: {
        // Swing wide while the attack cooldown runs down.
        c.state = 'hunt';
        _v1.subVectors(c.position, ctx.playerPos);
        _v1.y *= 0.3;
        steer(c, _v1.x - _v1.z * c.orbitDir * 0.8, _v1.y, _v1.z + _v1.x * c.orbitDir * 0.8, sp.speed * 0.9, dt, 2.5);
        if (c.cooldownT <= 0) {
          if (seen) {
            c.mode = 'circle';
            c.modeT = 0;
            c.circleR = Math.min(Math.max(distP, 11), 17);
            c.circleHold = 2 + rng() * 3;
          } else {
            c.mode = 'patrol';
          }
        }
        break;
      }
    }
  }

  // -------------------------------------------------------------------------
  // Death and damage
  // -------------------------------------------------------------------------

  /**
   * Gives a dying creature its own material instances so the fade never
   * touches pooled school materials or the shared eye materials.
   */
  function unshareForDeath(c) {
    const cloned = new Map();
    c.object.traverse((o) => {
      if (!o.isMesh && !o.isSprite) return;
      const m = o.material;
      if (!m) return;
      let cl = cloned.get(m);
      if (!cl) {
        const shared = c.pooled || m === MAT_EYE || m === MAT_GLINT;
        cl = shared ? m.clone() : m;
        cloned.set(m, cl);
      }
      o.material = cl;
    });
    c.mats = [];
    for (const m of cloned.values()) {
      if (c.mats.indexOf(m) === -1) c.mats.push(m);
    }
    c.pooled = false;
    for (const m of c.mats) {
      m.transparent = true;
      m.depthWrite = false;
      m.userData.baseOpacity = m.opacity;
    }
  }

  function kill(c, silent) {
    c.alive = false;
    c.state = 'dead';
    c.deathT = 0;
    unshareForDeath(c);
    if (!silent) emit(fauna.onKill, c);
    const specimen = makeSpecimen(c.species, c.position);
    c.pendingSpecimen = specimen;
    return specimen;
  }

  /**
   * Non lethal capture, used by the net gun.
   *
   * No blood and no death throes: the animal is out of the water at once, and
   * its specimen capsule appears immediately where it was, so a net capture
   * reads exactly like every other catch. Pass `magnetTo` (a live Vector3, in
   * practice the diver's position) and the capsule drifts over to it and
   * reports through `onSpecimenArrived` instead of waiting to be swum into.
   */
  function capture(c, magnetTo) {
    if (!c || !c.alive) return null;
    const specimen = kill(c, true);
    // Tells updateDeath not to reveal it a second time at the corpse.
    specimen._captured = true;
    // Skip the tumble, the body is gone on the next update.
    c.deathT = DEATH_TUMBLE_TIME;
    specimen.object.position.copy(c.position);
    specimen._baseY = c.position.y;
    specimen._riseTo = c.position.y;
    specimen.object.visible = true;
    if (magnetTo) {
      specimen._magnet = magnetTo;
      specimen._magnetSpeed = 2.5;
    }
    emit(fauna.onSpecimenSpawn, specimen);
    return specimen;
  }

  /** Let a magneted specimen go: it floats where it is, like any other. */
  function releaseSpecimen(sp) {
    if (!sp) return;
    sp._magnet = null;
    sp._baseY = sp.object.position.y;
    sp._riseTo = clamp(sp.object.position.y + 1.6, sp.object.position.y, -2.2);
  }

  /** Death tumble: sink, roll, fade; returns true once the body is gone. */
  function updateDeath(c, dt) {
    c.deathT += dt;
    c.velocity.multiplyScalar(1 - Math.min(1, dt * 1.6));
    c.velocity.y = Math.min(c.velocity.y, -0.55);
    c.position.addScaledVector(c.velocity, dt);
    c.object.rotateZ(dt * 2.3);
    c.object.rotateX(dt * 0.7);
    const fade = clamp01(1 - c.deathT / DEATH_TUMBLE_TIME);
    for (let i = 0; i < c.mats.length; i++) {
      const m = c.mats[i];
      m.opacity = (m.userData.baseOpacity !== undefined ? m.userData.baseOpacity : 1) * fade;
    }
    if (c.parts && c.parts.lureLight) c.parts.lureLight.intensity = 2.2 * fade;
    if (c.deathT < DEATH_TUMBLE_TIME) return false;
    // Body gone: reveal the specimen where the corpse settled.
    group.remove(c.object);
    for (const m of c.mats) m.dispose();
    const sp = c.pendingSpecimen;
    if (sp && !sp.collected && !sp._captured) {
      const floorY = world.heightAt(c.position.x, c.position.z) + 0.9;
      sp.object.position.set(c.position.x, Math.max(c.position.y, floorY), c.position.z);
      sp._riseTo = clamp(sp.object.position.y + 2.4, floorY, -2.2);
      sp._baseY = sp.object.position.y;
      sp.object.visible = true;
      emit(fauna.onSpecimenSpawn, sp);
    }
    return true;
  }

  function damage(creature, amount, opts) {
    opts = opts || {};
    if (!creature || !creature.alive) return { killed: false, specimen: null };
    creature.health -= amount;
    creature.hitPopT = 0.22;
    // Knockback along the shot direction.
    if (opts.from && opts.knockback) {
      _v1.subVectors(creature.position, opts.from);
      if (_v1.lengthSq() > 1e-6) {
        _v1.normalize();
        creature.velocity.addScaledVector(_v1, opts.knockback);
      }
    }
    // Electric stun: predators lose the plot for a while.
    if (opts.stun) {
      creature.stunT = Math.max(creature.stunT, opts.stun);
      creature.state = 'stunned';
    }
    // Nearby same species scatter: a school explodes when one fish is hit.
    const scatterSq = SCATTER_RADIUS * SCATTER_RADIUS;
    for (let i = 0; i < creatures.length; i++) {
      const o = creatures[i];
      if (!o.alive || o === creature || o.speciesId !== creature.speciesId) continue;
      if (o.danger === 2) continue; // packs of predators do not panic
      if (o.position.distanceToSquared(creature.position) < scatterSq) {
        o.fleeT = Math.max(o.fleeT, 2.2 + rng() * 1.5);
      }
    }
    if (creature.school) {
      creature.school.fleeT = Math.max(creature.school.fleeT, 2.5);
      _v1.subVectors(creature.position, opts.from || lastPlayerPos);
      if (_v1.lengthSq() > 1e-6) creature.school.fleeDir.copy(_v1.normalize());
    }
    if (creature.health <= 0) {
      const specimen = kill(creature);
      return { killed: true, specimen };
    }
    // Reaction of the survivor.
    if (creature.danger === 2 && !opts.stun) {
      if (creature.health < creature.maxHealth * 0.32) {
        creature.fleeT = Math.max(creature.fleeT, 5);
        creature.mode = 'patrol';
      } else if (creature.mode === 'patrol' || creature.mode === 'aware') {
        creature.mode = 'circle';
        creature.modeT = 0;
        creature.circleR = 14;
        creature.circleHold = 1.5 + rng() * 2;
      }
    } else if (creature.danger < 2) {
      creature.fleeT = Math.max(creature.fleeT, 3);
    }
    return { killed: false, specimen: null };
  }

  // -------------------------------------------------------------------------
  // Combat queries
  // -------------------------------------------------------------------------

  function raycast(origin, direction, maxDist) {
    _v5.copy(direction).normalize();
    let best = null;
    let bestDist = maxDist;
    for (let i = 0; i < creatures.length; i++) {
      const c = creatures[i];
      if (!c.alive) continue;
      // Broad phase: creature must be within range of the origin at all.
      _v1.subVectors(c.position, origin);
      const reach = bestDist + c.radius;
      if (_v1.lengthSq() > reach * reach) continue;
      // Ray vs sphere.
      const t = _v1.dot(_v5);
      if (t < -c.radius) continue;
      const dSq = _v1.lengthSq() - t * t;
      const rSq = c.radius * c.radius;
      if (dSq > rSq) continue;
      const hitT = Math.max(t - Math.sqrt(rSq - dSq), 0);
      if (hitT < bestDist) {
        bestDist = hitT;
        best = c;
      }
    }
    if (!best) return null;
    const point = new THREE.Vector3().copy(_v5).multiplyScalar(bestDist).add(origin);
    return { creature: best, point, distance: bestDist };
  }

  function sphereHit(center, radius) {
    const out = [];
    for (let i = 0; i < creatures.length; i++) {
      const c = creatures[i];
      if (!c.alive) continue;
      const reach = radius + c.radius;
      if (c.position.distanceToSquared(center) <= reach * reach) out.push(c);
    }
    return out;
  }

  function scanTarget(camera, maxDist) {
    camera.getWorldDirection(_v5);
    camera.getWorldPosition(_v6);
    let best = null;
    let bestScore = Infinity;
    for (let i = 0; i < creatures.length; i++) {
      const c = creatures[i];
      if (!c.alive) continue;
      _v1.subVectors(c.position, _v6);
      const d = _v1.length();
      if (d > maxDist || d < 0.5) continue;
      const cosA = _v1.dot(_v5) / d;
      if (cosA <= 0) continue;
      const off = Math.acos(Math.min(1, cosA));
      const cone = 0.1 + Math.atan(c.radius / d);
      if (off > cone) continue;
      const score = off * 60 + d * 0.15; // favour centred, then close
      if (score < bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return best;
  }

  function nearestThreat(pos) {
    let best = null;
    let bestD = Infinity;
    for (let i = 0; i < creatures.length; i++) {
      const c = creatures[i];
      if (!c.alive || c.danger !== 2) continue;
      if (c.state !== 'hunt' && c.state !== 'attack') continue;
      const d = c.position.distanceTo(pos);
      if (d < bestD) {
        bestD = d;
        best = c;
      }
    }
    return best ? { creature: best, distance: bestD } : null;
  }

  function collect(specimen) {
    if (!specimen || specimen.collected) return;
    specimen.collected = true;
    disposeSpecimenVisual(specimen);
    const idx = specimens.indexOf(specimen);
    if (idx !== -1) specimens.splice(idx, 1);
  }

  // -------------------------------------------------------------------------
  // Streaming
  // -------------------------------------------------------------------------

  function removeCreature(index) {
    const c = creatures[index];
    group.remove(c.object);
    if (!c.pooled) {
      for (const m of c.mats) m.dispose();
    }
    creatures.splice(index, 1);
  }

  function stream(playerPos) {
    // 1) Despawn far creatures that are not busy hunting the diver.
    for (let i = creatures.length - 1; i >= 0; i--) {
      const c = creatures[i];
      if (!c.alive) continue;
      if (c.state === 'hunt' || c.state === 'attack') continue;
      if (c.position.distanceToSquared(playerPos) > DESPAWN_DIST * DESPAWN_DIST) {
        removeCreature(i);
      }
    }
    // 2) Count live individuals per species around the player.
    const counts = {};
    const streamSq = STREAM_RADIUS * STREAM_RADIUS;
    for (let i = 0; i < creatures.length; i++) {
      const c = creatures[i];
      if (!c.alive) continue;
      if (c.position.distanceToSquared(playerPos) <= streamSq) {
        counts[c.speciesId] = (counts[c.speciesId] || 0) + 1;
      }
    }
    // 3) Top up species compatible with the local biome and depth.
    const biome = world.biomeAt(playerPos.x, playerPos.z);
    const depth = -playerPos.y;
    for (let i = 0; i < SPECIES.length; i++) {
      if (creatures.length >= MAX_CREATURES - 4) break;
      const species = SPECIES[i];
      if (species.biomes.indexOf(biome) === -1) continue;
      if (depth < species.depth[0] - 28 || depth > species.depth[1] + 28) continue;
      const target = POP_TARGET[species.id] || 2;
      if ((counts[species.id] || 0) >= target) continue;
      // The legends stay legendary.
      const rare = RARE_CHANCE[species.id];
      if (rare !== undefined && rng() > rare) continue;
      const pos = pickSpawnPos(species, playerPos, biome);
      if (!pos) continue;
      spawnGroup(species, pos);
    }
  }

  // -------------------------------------------------------------------------
  // Per frame update
  // -------------------------------------------------------------------------

  const safeCtx = {
    time: 0,
    camera: null,
    playerPos: new THREE.Vector3(0, -10, 0),
    playerVel: new THREE.Vector3(),
    playerVisible: false,
    lampOn: false,
    noise: 0,
    bleeding: 0,
  };

  function updateCreature(c, dt, ctx, full) {
    c.contactT -= dt;
    c.cooldownT -= dt;
    if (c.stunT > 0) {
      // Stunned: drift, twitch, sink a little.
      c.state = 'stunned';
      c.stunT -= dt;
      c.velocity.multiplyScalar(1 - Math.min(1, dt * 2.2));
      c.velocity.y -= dt * 0.35;
      c.object.rotation.z = Math.sin(timeNow * 9 + c.phase) * 0.15;
      if (c.stunT <= 0) {
        c.fleeT = 6;
        c.mode = 'patrol';
      }
    } else if (c.fleeT > 0) {
      // Panic flight away from the diver.
      c.fleeT -= dt;
      c.state = 'flee';
      _v1.subVectors(c.position, ctx.playerPos);
      _v1.y *= 0.4;
      _v1.x += Math.sin(timeNow * 1.7 + c.phase) * 2;
      _v1.z += Math.cos(timeNow * 1.5 + c.phase) * 2;
      steer(c, _v1.x, _v1.y, _v1.z, c.species.speed * 1.6, dt, 3.5);
      if (c.fleeT <= 0) c.mode = 'patrol';
    } else {
      switch (c.species.behaviour) {
        case 'school':
          updateSchoolMember(c, dt, ctx, full);
          break;
        case 'drifter':
          updateDrifter(c, dt, ctx, full);
          break;
        case 'solo':
          updateSolo(c, dt, ctx, full);
          break;
        case 'ambush':
          updateAmbush(c, dt, ctx, full);
          break;
        case 'predator':
          updatePredator(c, dt, ctx, full);
          break;
        default:
          updateDrifter(c, dt, ctx, full);
          break;
      }
    }
    applyEnvironment(c, dt, full);
    // Integrate, with a hard speed cap.
    const maxSp = c.species.speed * 2.2;
    const spSq = c.velocity.lengthSq();
    if (spSq > maxSp * maxSp) c.velocity.multiplyScalar(maxSp / Math.sqrt(spSq));
    c.position.addScaledVector(c.velocity, dt);
    orient(c, dt, c.state === 'attack' ? 8 : 3.5);
    setSwimIntensity(c, dt);
    if (full) {
      animateParts(c, dt);
      // Passive contact damage for the venomous and the bitey (danger 1).
      if (c.danger === 1 && ctx.playerVisible && c.contactT <= 0) {
        const reach = c.radius + DIVER.radius + 0.35;
        if (c.distToPlayer < reach) {
          emit(fauna.onDiverAttacked, c, c.species.contactDamage || 8);
          c.contactT = 1.8;
        }
      }
    }
  }

  function update(dt, ctx) {
    dt = Math.min(dt || 0, 0.05);
    ctx = ctx || safeCtx;
    if (ctx.playerPos) safeCtx.playerPos.copy(ctx.playerPos);
    if (ctx.playerVel) safeCtx.playerVel.copy(ctx.playerVel);
    safeCtx.time = ctx.time !== undefined ? ctx.time : safeCtx.time + dt;
    safeCtx.camera = ctx.camera || safeCtx.camera;
    safeCtx.playerVisible = !!ctx.playerVisible;
    safeCtx.lampOn = !!ctx.lampOn;
    safeCtx.noise = ctx.noise || 0;
    safeCtx.bleeding = ctx.bleeding || 0;
    timeNow = safeCtx.time;
    SHARED_TIME.value = timeNow; // one write animates every GPU swim material
    if (safeCtx.camera) safeCtx.camera.getWorldDirection(lastCamDir);
    lastPlayerPos.copy(safeCtx.playerPos);

    updateSchools(dt, safeCtx);

    for (let i = creatures.length - 1; i >= 0; i--) {
      const c = creatures[i];
      c.distToPlayer = c.position.distanceTo(safeCtx.playerPos);
      if (!c.alive) {
        if (updateDeath(c, dt)) creatures.splice(i, 1);
        continue;
      }
      if (c.distToPlayer <= LOD_FULL) {
        updateCreature(c, dt, safeCtx, true);
      } else if (c.distToPlayer <= LOD_CHEAP) {
        updateCreature(c, dt, safeCtx, false);
      } else {
        // Frozen tier: a micro tick now and then keeps them plausible.
        c.frozenT -= dt;
        if (c.frozenT <= 0) {
          c.frozenT = FROZEN_TICK;
          c.velocity.multiplyScalar(0.9);
          c.position.addScaledVector(c.velocity, FROZEN_TICK * 0.5);
          applyEnvironment(c, FROZEN_TICK, false);
          if (c.state === 'attack') c.state = 'hunt';
        }
      }
    }

    // Specimens: rise gently, hold depth, bob, spin their ring.
    for (let i = 0; i < specimens.length; i++) {
      const sp = specimens[i];
      if (!sp.object.visible) continue;
      // A netted capsule is reeled in rather than left to float.
      if (sp._magnet) {
        _v1.subVectors(sp._magnet, sp.object.position);
        const d = _v1.length();
        sp._ring.rotation.z += dt * sp._spin * 3;
        sp._mini.group.rotation.y += dt * 1.8;
        if (d < 1.2) {
          sp._magnet = null;
          emit(fauna.onSpecimenArrived, sp);
          continue;
        }
        sp._magnetSpeed = Math.min(16, sp._magnetSpeed + dt * 26);
        sp.object.position.addScaledVector(_v1.multiplyScalar(1 / d), sp._magnetSpeed * dt);
        continue;
      }
      sp._bob += dt;
      if (sp._baseY === undefined) sp._baseY = sp.object.position.y;
      sp._baseY += (sp._riseTo - sp._baseY) * Math.min(1, dt * 0.5);
      sp.object.position.y = sp._baseY + Math.sin(sp._bob * 1.6) * 0.14;
      sp._ring.rotation.z += dt * sp._spin;
      sp._mini.group.rotation.y += dt * 0.55;
    }
  }

  // -------------------------------------------------------------------------
  // Dispose
  // -------------------------------------------------------------------------

  function dispose() {
    scene.remove(group);
    // Dispose every material still referenced under the fauna group.
    const seen = new Set();
    group.traverse((o) => {
      if ((o.isMesh || o.isSprite) && o.material && !seen.has(o.material)) {
        seen.add(o.material);
        o.material.dispose();
      }
    });
    for (const pool of matPools.values()) {
      for (const set of pool.sets) {
        for (const m of set.mats) {
          if (!seen.has(m)) m.dispose();
        }
      }
    }
    matPools.clear();
    for (const g of ownedGeometries) g.dispose();
    ownedGeometries.length = 0;
    geoCache.clear();
    if (MAT_EYE) {
      MAT_EYE.dispose();
      MAT_GLINT.dispose();
      MAT_EYE = null;
      MAT_GLINT = null;
    }
    UNIT_SPHERE = null;
    UNIT_CONE = null;
    creatures.length = 0;
    specimens.length = 0;
    schools.length = 0;
  }

  // -------------------------------------------------------------------------
  // Public object
  // -------------------------------------------------------------------------

  const fauna = {
    group,
    creatures,
    specimens,
    update,
    dispose,
    raycast,
    sphereHit,
    damage,
    scanTarget,
    nearestThreat,
    collect,
    capture,
    releaseSpecimen,
    stream,
    onDiverAttacked: null,
    onKill: null,
    onSpecimenSpawn: null,
    onSpecimenArrived: null,
  };

  // Debug boot: one of every species in a ring around the sub anchor.
  if (DEBUG.spawnAll) {
    const anchor = WORLD.subAnchor;
    for (let i = 0; i < SPECIES.length; i++) {
      const species = SPECIES[i];
      const a = (i / SPECIES.length) * Math.PI * 2;
      const r = 9 + (i % 4) * 4;
      _v1.set(anchor.x + Math.cos(a) * r, anchor.y, anchor.z + Math.sin(a) * r);
      _v1.y = clampDepthY(species, _v1.x, _v1.z, anchor.y);
      spawnCreature(species, _v1, null);
    }
  }

  return fauna;
}
