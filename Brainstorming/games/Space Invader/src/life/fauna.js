// Faune instanciee : le troisieme element a decouvrir.
//
// Deux archetypes, deux comportements :
//   - 'flyer'  : nuees de 24 individus, boids simplifie a 3 regles, entre 40 et
//                220 m au-dessus du sol, battement d'ailes en vertex shader.
//   - 'grazer' : troupeaux de 12 individus colles au sol, marche aleatoire
//                lissee par du bruit, orientation sur la normale du terrain.
//
// Espace de travail : ESPACE LOCAL PLANETE (origine = centre planete, +Y = axe
// des poles). Ce module ne connait jamais viewOrigin.
//
// Contraintes de perf : un InstancedMesh par archetype, geometries construites
// une seule fois, aucune allocation par frame (tous les vecteurs temporaires
// sont declares au niveau module), heightField echantillonne avec parcimonie
// (cache par groupe pour les nuees, 1 individu sur 4 par frame pour les
// troupeaux), et seuls les groupes a moins de 4 km de la camera sont animes.

import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { clamp, damp, hashString, mulberry32, smoothstep, tangentBasis } from '../core/math.js';
import { BIOME_ID, FAUNA_BIOMES, getPalette } from '../gen/palettes.js';
import { makeNoise2D } from '../gen/noise.js';

// ---------------------------------------------------------------------------
// Constantes de reglage
// ---------------------------------------------------------------------------

const CAPACITY = 600; // instances par archetype
const FLOCK_SIZE = 24; // individus par nuee
const HERD_SIZE = 12; // individus par troupeau
const SCATTER_COUNT = 6; // points d'ancrage demandes au pool par patch
const MAX_GROUPS_PER_PATCH = 2;

const AWAKE_DISTANCE = 4000; // m : au-dela, un groupe est fige (mais visible)
const SEARCH_DISTANCE = 5000; // m : rayon de recherche de nearest()
const FLOCK_GROUND_FRAMES = 8; // rafraichissement du rayon de sol d'une nuee
const HERD_GROUND_SLOTS = 4; // 1 individu sur 4 par frame

// Nuee : poids des 3 regles + forces de rappel.
const COHESION = 0.55;
const ALIGNMENT = 0.85;
const SEPARATION = 26.0;
const SEPARATION_DIST = 7.0;
const LEASH_RADIUS = 210; // rayon de divagation autour de l'ancre
const LEASH_FORCE = 0.09;
const ALTITUDE_FORCE = 0.42;
const ALTITUDE_DAMP = 1.35;
const ROLL_GAIN = 0.055;
const ROLL_LAMBDA = 5.0;

// Troupeau.
const HERD_RADIUS = 46; // rayon de paturage autour de l'ancre
const HERD_SPEED = 2.3; // m/s
const HERD_TURN = 2.6; // amplitude angulaire du bruit de cap
const HERD_BOB = 0.075;

/**
 * Table des creatures (asset D05). `groupSize` pilote aussi la taille des blocs
 * d'instances : un groupe occupe toujours un bloc contigu.
 */
export const CREATURE_TYPES = [
  {
    kind: 'flyer',
    name: 'Nuee volante',
    groupSize: FLOCK_SIZE,
    length: 1.9,
    scaleJitter: 0.3,
    minAltitude: 40,
    maxAltitude: 220,
    cruise: 15,
    minSpeed: 9,
    maxSpeed: 25,
    boundRadius: LEASH_RADIUS + 90,
    biomes: FAUNA_BIOMES,
  },
  {
    kind: 'grazer',
    name: 'Troupeau terrestre',
    groupSize: HERD_SIZE,
    length: 3.1,
    scaleJitter: 0.26,
    cruise: HERD_SPEED,
    boundRadius: HERD_RADIUS * 2.2,
    biomes: FAUNA_BIOMES,
  },
];

const ARCHETYPES = {
  flyer: CREATURE_TYPES[0],
  grazer: CREATURE_TYPES[1],
};

// Multiplicateurs de couleur par partie du corps (la teinte reelle vient de
// instanceColor, la geometrie ne porte qu'un contraste relatif).
const TINT_BODY = [1.0, 1.0, 1.0];
const TINT_LIMB = [0.44, 0.44, 0.48];
const TINT_HEAD = [0.82, 0.79, 0.74];
const TINT_WING = [1.18, 1.14, 1.06];

// ---------------------------------------------------------------------------
// Temporaires partages (zero allocation par frame)
// ---------------------------------------------------------------------------

const _dir = new THREE.Vector3();
const _pos = new THREE.Vector3();
const _fwd = new THREE.Vector3();
const _up = new THREE.Vector3();
const _upOrtho = new THREE.Vector3();
const _right = new THREE.Vector3();
const _basis = new THREE.Matrix4();
const _matrix = new THREE.Matrix4();
const _quat = new THREE.Quaternion();
const _quatRoll = new THREE.Quaternion();
const _scaleVec = new THREE.Vector3();
const _color = new THREE.Color();
const _tanA = { x: 0, y: 0, z: 0 };
const _tanB = { x: 0, y: 0, z: 0 };
const _zeroMatrix = new THREE.Matrix4().set(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
const AXIS_FORWARD = new THREE.Vector3(0, 0, 1);

/** Longueur d'un vecteur : plus rapide que Math.hypot dans les boucles. */
function len3(x, y, z) {
  return Math.sqrt(x * x + y * y + z * z);
}

const _nearest = { distance: 0, position: new THREE.Vector3(), kind: 'flyer' };

// ---------------------------------------------------------------------------
// Geometries
// ---------------------------------------------------------------------------

/** Prepare une partie de corps : non indexee, attributs color et aWing. */
function preparePart(geom, wing, tint) {
  const g = geom.index ? geom.toNonIndexed() : geom;
  if (g !== geom) geom.dispose();
  if (g.getAttribute('uv')) g.deleteAttribute('uv');
  if (!g.getAttribute('normal')) g.computeVertexNormals();
  const n = g.getAttribute('position').count;
  const col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    col[i * 3] = tint[0];
    col[i * 3 + 1] = tint[1];
    col[i * 3 + 2] = tint[2];
  }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  const w = new Float32Array(n);
  if (wing !== 0) w.fill(wing);
  g.setAttribute('aWing', new THREE.BufferAttribute(w, 1));
  return g;
}

/** Geometrie non indexee a partir d'une liste plate de triangles. */
function triGeometry(verts) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts), 3));
  g.computeVertexNormals();
  return g;
}

/** Empile un triangle en respectant le sens de parcours (miroir si side < 0). */
function pushTri(out, a, b, c, side) {
  const p = side < 0 ? [a, c, b] : [a, b, c];
  for (let i = 0; i < 3; i++) {
    out.push(p[i][0], p[i][1], p[i][2]);
  }
}

/** Aile triangulaire a double face, dans le demi-espace x * side > 0. */
function wingTriangles(side) {
  const th = 0.035;
  const A = [0.08 * side, 0.02, 0.42];
  const B = [0.08 * side, 0.02, -0.3];
  const C = [0.6 * side, 0.09, 0.14];
  const D = [1.02 * side, 0.14, -0.12];
  const A2 = [A[0], A[1] - th, A[2]];
  const B2 = [B[0], B[1] - th, B[2]];
  const C2 = [C[0], C[1] - th, C[2]];
  const D2 = [D[0], D[1] - th, D[2]];
  const out = [];
  // Face superieure.
  pushTri(out, A, C, B, side);
  pushTri(out, B, C, D, side);
  // Face inferieure (sens inverse).
  pushTri(out, A2, B2, C2, side);
  pushTri(out, B2, D2, C2, side);
  return out;
}

/** Derive verticale arriere, deux faces legerement decalees. */
function finTriangles() {
  const out = [];
  const off = 0.012;
  const P = [off, 0.04, -0.86];
  const Q = [off, 0.04, -1.22];
  const R = [off, 0.46, -1.12];
  pushTri(out, P, Q, R, 1);
  const P2 = [-off, 0.04, -0.86];
  const Q2 = [-off, 0.04, -1.22];
  const R2 = [-off, 0.46, -1.12];
  pushTri(out, P2, Q2, R2, -1);
  return out;
}

/** Creature volante : corps fusele le long de +Z, deux ailes le long de X. */
function buildFlyerGeometry() {
  const parts = [];

  const nose = new THREE.ConeGeometry(0.19, 0.9, 6, 1);
  nose.rotateX(Math.PI / 2);
  nose.translate(0, 0, 0.45);
  parts.push(preparePart(nose, 0, TINT_BODY));

  const tail = new THREE.ConeGeometry(0.19, 1.05, 6, 1);
  tail.rotateX(-Math.PI / 2);
  tail.translate(0, 0, -0.52);
  parts.push(preparePart(tail, 0, TINT_BODY));

  parts.push(preparePart(triGeometry(wingTriangles(1)), 1, TINT_WING));
  parts.push(preparePart(triGeometry(wingTriangles(-1)), -1, TINT_WING));
  parts.push(preparePart(triGeometry(finTriangles()), 0, TINT_WING));

  const merged = mergeGeometries(parts, false);
  for (const p of parts) p.dispose();
  merged.computeVertexNormals(); // non indexee : normales de face (facettes)
  return merged;
}

/** Herbivore : corps, 4 pattes, encolure, tete, queue. Pieds a y = 0. */
function buildGrazerGeometry() {
  const parts = [];

  const body = new THREE.BoxGeometry(0.92, 0.86, 1.9);
  body.translate(0, 1.12, 0);
  parts.push(preparePart(body, 0, TINT_BODY));

  const legs = [
    [0.32, 0.68],
    [-0.32, 0.68],
    [0.32, -0.64],
    [-0.32, -0.64],
  ];
  for (let i = 0; i < legs.length; i++) {
    const leg = new THREE.BoxGeometry(0.17, 0.72, 0.17);
    leg.translate(legs[i][0], 0.36, legs[i][1]);
    parts.push(preparePart(leg, 0, TINT_LIMB));
  }

  const neck = new THREE.BoxGeometry(0.36, 0.36, 0.72);
  neck.rotateX(-0.5);
  neck.translate(0, 1.44, 1.12);
  parts.push(preparePart(neck, 0, TINT_BODY));

  const head = new THREE.BoxGeometry(0.42, 0.38, 0.56);
  head.translate(0, 1.74, 1.52);
  parts.push(preparePart(head, 0, TINT_HEAD));

  const queue = new THREE.BoxGeometry(0.12, 0.12, 0.64);
  queue.rotateX(0.35);
  queue.translate(0, 1.3, -1.1);
  parts.push(preparePart(queue, 0, TINT_LIMB));

  const merged = mergeGeometries(parts, false);
  for (const p of parts) p.dispose();
  merged.computeVertexNormals();
  return merged;
}

// ---------------------------------------------------------------------------
// Materiau
// ---------------------------------------------------------------------------

const VERT = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>

attribute float aWing;
attribute float aPhase;

uniform float uTime;
uniform float uFlapSpeed;
uniform float uFlapAmp;
uniform vec3 uCameraLocal;

varying vec3 vNrmLocal;
varying vec3 vTint;
varying float vDist;

void main() {
  vec3 p = position;
  vec3 nrm = normal;

  // Battement d'ailes : rotation sinusoidale autour de l'axe du corps (+Z).
  if (abs(aWing) > 0.5) {
    float a = aWing * sin(uTime * uFlapSpeed + aPhase) * uFlapAmp;
    float c = cos(a);
    float s = sin(a);
    mat2 rot = mat2(c, s, -s, c);
    p.xy = rot * p.xy;
    nrm.xy = rot * nrm.xy;
  }

  vec4 local = vec4(p, 1.0);
  mat3 im3 = mat3(1.0);
  #ifdef USE_INSTANCING
    local = instanceMatrix * local;
    im3 = mat3(instanceMatrix);
  #endif

  vNrmLocal = normalize(im3 * nrm);

  vec3 tint = color;
  #ifdef USE_INSTANCING_COLOR
    tint *= instanceColor;
  #endif
  vTint = tint;

  vDist = length(local.xyz - uCameraLocal);

  gl_Position = projectionMatrix * modelViewMatrix * local;

  #include <logdepthbuf_vertex>
}
`;

const FRAG = /* glsl */ `
// Note : three injecte deja tonemapping_pars_fragment et colorspace_pars_fragment
// dans le prefixe des ShaderMaterial. Les re-inclure provoque une redefinition.
#include <common>
#include <logdepthbuf_pars_fragment>

uniform vec3 uSunDir;
uniform vec3 uNightAmbient;
uniform vec3 uFogColor;
uniform float uFogDensity;

varying vec3 vNrmLocal;
varying vec3 vTint;
varying float vDist;

void main() {
  #include <logdepthbuf_fragment>

  vec3 n = normalize(vNrmLocal);
  float ndl = dot(n, uSunDir);
  // Eclairage wrap : le terminateur reste lisible sur des volumes minuscules.
  float diff = clamp((ndl + 0.32) / 1.32, 0.0, 1.0);
  float night = 1.0 - smoothstep(-0.25, 0.06, ndl);

  vec3 col = vTint * (0.16 + 1.05 * diff);
  col += uNightAmbient * night * 0.35;

  float fog = 1.0 - exp(-max(vDist, 0.0) * uFogDensity);
  col = mix(col, uFogColor, clamp(fog, 0.0, 1.0));

  gl_FragColor = vec4(col, 1.0);

  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function createFaunaMaterial(spec) {
  const night = spec && spec.atmosphere ? spec.atmosphere.colorNight : [0.03, 0.04, 0.06];
  return new THREE.ShaderMaterial({
    vertexColors: true,
    uniforms: {
      uTime: { value: 0 },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uCameraLocal: { value: new THREE.Vector3() },
      uNightAmbient: { value: new THREE.Color().setRGB(night[0], night[1], night[2]) },
      uFogColor: { value: new THREE.Color().setRGB(0, 0, 0) },
      uFogDensity: { value: 0 },
      uFlapSpeed: { value: 9.2 },
      uFlapAmp: { value: 0.62 },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
  });
}

// ---------------------------------------------------------------------------
// Couleurs : contraste volontaire avec le sol
// ---------------------------------------------------------------------------

const GROUND_REF_BIOMES = [
  BIOME_ID.GRASS,
  BIOME_ID.FOREST,
  BIOME_ID.SAVANNA,
  BIOME_ID.BEACH,
  BIOME_ID.ROCK,
];

function luminance(r, g, b) {
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Couleur moyenne (lineaire) des biomes de sol ou vit la faune. */
function groundReference(palette) {
  let r = 0;
  let g = 0;
  let b = 0;
  for (let i = 0; i < GROUND_REF_BIOMES.length; i++) {
    const o = GROUND_REF_BIOMES[i] * 3;
    r += palette[o];
    g += palette[o + 1];
    b += palette[o + 2];
  }
  const inv = 1 / GROUND_REF_BIOMES.length;
  return [r * inv, g * inv, b * inv];
}

/**
 * Couleur de creature : complementaire de la reference du sol, saturation
 * poussee, puis ecart de luminance force a 0.3 minimum. Le but est purement
 * fonctionnel : etre reperable a 400 m.
 */
function contrastingColor(ref, rnd, rotate = 0) {
  let r = 1 - ref[0];
  let g = 1 - ref[1];
  let b = 1 - ref[2];
  const mean = (r + g + b) / 3;
  const boost = 1.9;
  r = clamp(mean + (r - mean) * boost + (rnd() - 0.5) * 0.12, 0.02, 1.0);
  g = clamp(mean + (g - mean) * boost + (rnd() - 0.5) * 0.12, 0.02, 1.0);
  b = clamp(mean + (b - mean) * boost + (rnd() - 0.5) * 0.12, 0.02, 1.0);

  // Rotation des canaux : les deux archetypes doivent etre distinguables.
  if (rotate === 1) {
    const t = r;
    r = b;
    b = g;
    g = t;
  }

  // Normalisation : on garde la teinte sans saturer le rendu en blanc.
  const maxc = Math.max(r, g, b);
  if (maxc > 0.86) {
    const k = 0.86 / maxc;
    r *= k;
    g *= k;
    b *= k;
  }

  const lRef = luminance(ref[0], ref[1], ref[2]);
  const l = luminance(r, g, b);
  if (Math.abs(l - lRef) < 0.3) {
    const brighter = lRef < 0.4;
    const k = brighter ? 1 + (0.3 - Math.abs(l - lRef)) * 2.6 : 0.34;
    r = clamp(r * k, 0.02, 1.0);
    g = clamp(g * k, 0.02, 1.0);
    b = clamp(b * k, 0.02, 1.0);
  }
  return [r, g, b];
}

// ---------------------------------------------------------------------------
// Allocateur de blocs d'instances
// ---------------------------------------------------------------------------

function createBlockAllocator(capacity, blockSize) {
  const total = Math.floor(capacity / blockSize);
  const free = [];
  for (let i = total - 1; i >= 0; i--) free.push(i);
  const used = new Set();
  return {
    blockSize,
    total,
    alloc() {
      if (free.length === 0) return -1;
      const b = free.pop();
      used.add(b);
      return b;
    },
    release(b) {
      if (used.delete(b)) free.push(b);
    },
    /** Nombre d'instances a soumettre au GPU (dernier bloc utilise inclus). */
    highCount() {
      let m = -1;
      for (const b of used) if (b > m) m = b;
      return (m + 1) * blockSize;
    },
    clear() {
      used.clear();
      free.length = 0;
      for (let i = total - 1; i >= 0; i--) free.push(i);
    },
  };
}

// ---------------------------------------------------------------------------
// Implementation neutre (planete sans faune)
// ---------------------------------------------------------------------------

function createEmptyFauna() {
  const object3D = new THREE.Group();
  object3D.name = 'fauna-empty';
  return {
    object3D,
    addPatch() {},
    removePatch() {},
    update() {},
    nearest() {
      return null;
    },
    get count() {
      return 0;
    },
    get stats() {
      return { groups: 0, flocks: 0, herds: 0, individuals: 0 };
    },
    dispose() {},
  };
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

/**
 * @param {object} args
 * @param {object} args.spec PlanetSpec
 * @param {object} args.heightField HeightField
 * @param {object} args.pool WorkerPool de terrain
 * @param {object} args.quality preset de qualite
 */
export function createFauna({ spec, heightField, pool, quality }) {
  if (!spec || !spec.hasFauna || !heightField) return createEmptyFauna();

  const q = quality || {};
  const lifeMinLevel = q.lifeMinLevel === undefined ? 5 : q.lifeMinLevel;
  const density = q.faunaDensity === undefined ? 1 : q.faunaDensity;

  const object3D = new THREE.Group();
  object3D.name = `fauna-${spec.id}`;

  const palette = getPalette(spec.palette);
  const ref = groundReference(palette);
  const paletteRnd = mulberry32((spec.seed ^ 0x3f7a19c5) >>> 0);
  const flyerColor = contrastingColor(ref, paletteRnd, 0);
  const grazerColor = contrastingColor(ref, paletteRnd, 1);

  const material = createFaunaMaterial(spec);
  const noise2D = makeNoise2D((spec.seed ^ 0x71b3c4d9) >>> 0);

  const meshes = {};
  const allocators = {};

  function buildArchetype(kind, geometry) {
    const arch = ARCHETYPES[kind];
    const phase = new THREE.InstancedBufferAttribute(new Float32Array(CAPACITY), 1);
    for (let i = 0; i < CAPACITY; i++) phase.array[i] = (i * 2.399963) % 6.283185;
    geometry.setAttribute('aPhase', phase);

    const mesh = new THREE.InstancedMesh(geometry, material, CAPACITY);
    mesh.name = `fauna-${kind}`;
    mesh.count = 0;
    mesh.frustumCulled = false; // instances reparties sur toute la planete
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.instanceColor = new THREE.InstancedBufferAttribute(
      new Float32Array(CAPACITY * 3).fill(1),
      3,
    );
    mesh.instanceColor.setUsage(THREE.DynamicDrawUsage);
    object3D.add(mesh);

    meshes[kind] = mesh;
    allocators[kind] = createBlockAllocator(CAPACITY, arch.groupSize);
  }

  buildArchetype('flyer', buildFlyerGeometry());
  buildArchetype('grazer', buildGrazerGeometry());

  /** @type {Map<string, {key:string, groups:Array, removed:boolean}>} */
  const patches = new Map();
  const groups = [];
  let individuals = 0;
  let frame = 0;
  let time = 0;
  let disposed = false;
  let matricesDirty = false;

  // -------------------------------------------------------------------------
  // Streaming par patch
  // -------------------------------------------------------------------------

  function hasFaunaBiome(histogram) {
    if (!histogram) return true; // pas d'info : on laisse le scatter trancher
    let total = 0;
    let good = 0;
    for (let i = 0; i < histogram.length; i++) {
      total += histogram[i];
      if (FAUNA_BIOMES.has(i)) good += histogram[i];
    }
    if (total === 0) return false;
    return good / total > 0.06;
  }

  function groupBudget(rnd) {
    const base = MAX_GROUPS_PER_PATCH * density;
    let n = Math.floor(base);
    if (rnd() < base - n) n += 1;
    return clamp(n, 0, MAX_GROUPS_PER_PATCH);
  }

  function addPatch(p) {
    if (disposed || !p || !pool || typeof pool.request !== 'function') return;
    if (p.level < lifeMinLevel) return;
    if (p.waterFraction > 0.9) return;
    if (!hasFaunaBiome(p.biomeHistogram)) return;
    if (patches.has(p.key)) return;

    const entry = { key: p.key, groups: [], removed: false };
    patches.set(p.key, entry);
    requestScatter(p, entry);
  }

  async function requestScatter(p, entry) {
    let res = null;
    try {
      res = await pool.request({
        type: 'scatter',
        faceId: p.faceId,
        u0: p.u0,
        v0: p.v0,
        size: p.size,
        count: SCATTER_COUNT,
        kind: 'fauna',
      });
    } catch (err) {
      // Pool annule ou detruit : rien a instancier.
      if (patches.get(p.key) === entry) patches.delete(p.key);
      return;
    }
    if (disposed || entry.removed || patches.get(p.key) !== entry) return;
    if (!res || !res.position || res.position.length < 3) {
      patches.delete(p.key);
      return;
    }

    const rnd = mulberry32((hashString(p.key) ^ spec.seed) >>> 0);
    const budget = groupBudget(rnd);
    if (budget === 0) return;

    const points = Math.floor(res.position.length / 3);
    let made = 0;
    for (let i = 0; i < points && made < budget; i++) {
      const biome = res.biome ? res.biome[i] : BIOME_ID.GRASS;
      if (!FAUNA_BIOMES.has(biome)) continue;
      const x = res.position[i * 3];
      const y = res.position[i * 3 + 1];
      const z = res.position[i * 3 + 2];
      const r = len3(x, y, z);
      if (!(r > 1)) continue;
      const kind = rnd() < 0.52 ? 'grazer' : 'flyer';
      const g = createGroup(kind, x, y, z, r, rnd, entry.key);
      if (g) {
        entry.groups.push(g);
        made++;
      }
    }
    if (entry.groups.length === 0) patches.delete(p.key);
  }

  function removePatch(key) {
    const entry = patches.get(key);
    if (!entry) return;
    entry.removed = true;
    patches.delete(key);
    for (let i = 0; i < entry.groups.length; i++) destroyGroup(entry.groups[i]);
    entry.groups.length = 0;
  }

  // -------------------------------------------------------------------------
  // Creation / destruction d'un groupe
  // -------------------------------------------------------------------------

  function createGroup(kind, ax, ay, az, anchorRadius, rnd, key) {
    const arch = ARCHETYPES[kind];
    const alloc = allocators[kind];
    const block = alloc.alloc();
    if (block < 0) return null;

    const n = arch.groupSize;
    const g = {
      kind,
      key,
      block,
      base: block * n,
      size: n,
      anchor: new THREE.Vector3(ax, ay, az),
      up: new THREE.Vector3(ax / anchorRadius, ay / anchorRadius, az / anchorRadius),
      center: new THREE.Vector3(ax, ay, az),
      radius: arch.boundRadius,
      groundRadius: anchorRadius,
      groundTimer: 0,
      altitude: 0,
      tangent: new THREE.Vector3(),
      bitangent: new THREE.Vector3(),
      pos: new Float32Array(n * 3),
      vel: new Float32Array(n * 3),
      dirs: new Float32Array(n * 3),
      normals: new Float32Array(n * 3),
      ground: new Float32Array(n),
      heading: new Float32Array(n),
      baseHeading: new Float32Array(n),
      speedMul: new Float32Array(n),
      roll: new Float32Array(n),
      phase: new Float32Array(n),
      scl: new Float32Array(n),
      noiseOffset: rnd() * 512,
    };

    tangentBasis(g.up, _tanA, _tanB);
    g.tangent.set(_tanA.x, _tanA.y, _tanA.z);
    g.bitangent.set(_tanB.x, _tanB.y, _tanB.z);

    for (let i = 0; i < n; i++) {
      g.phase[i] = rnd() * 6.283185;
      g.scl[i] = 1 + (rnd() - 0.5) * arch.scaleJitter;
      g.speedMul[i] = 0.7 + rnd() * 0.6;
      g.baseHeading[i] = rnd() * 6.283185;
      g.heading[i] = g.baseHeading[i];
    }

    if (kind === 'flyer') initFlock(g, arch, rnd);
    else initHerd(g, arch, rnd);

    // Couleur du groupe : teinte de base + jitter par individu.
    const bc = kind === 'flyer' ? flyerColor : grazerColor;
    const gj = 0.88 + rnd() * 0.24;
    const mesh = meshes[kind];
    for (let i = 0; i < n; i++) {
      const j = gj * (0.92 + rnd() * 0.16);
      _color.setRGB(
        clamp(bc[0] * j, 0, 1.4),
        clamp(bc[1] * j, 0, 1.4),
        clamp(bc[2] * j, 0, 1.4),
      );
      mesh.setColorAt(g.base + i, _color);
    }
    mesh.instanceColor.needsUpdate = true;

    groups.push(g);
    individuals += n;
    mesh.count = alloc.highCount();

    if (kind === 'flyer') writeFlockMatrices(g);
    else writeHerdMatrices(g);
    mesh.instanceMatrix.needsUpdate = true;

    return g;
  }

  function initFlock(g, arch, rnd) {
    g.altitude = arch.minAltitude + rnd() * (arch.maxAltitude - arch.minAltitude);
    const n = g.size;
    const baseR = g.groundRadius + g.altitude;
    const t = g.tangent;
    const b = g.bitangent;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      const su = (rnd() - 0.5) * 70;
      const sv = (rnd() - 0.5) * 70;
      const sr = (rnd() - 0.5) * 26;
      const px = g.up.x * (baseR + sr) + t.x * su + b.x * sv;
      const py = g.up.y * (baseR + sr) + t.y * su + b.y * sv;
      const pz = g.up.z * (baseR + sr) + t.z * su + b.z * sv;
      g.pos[o] = px;
      g.pos[o + 1] = py;
      g.pos[o + 2] = pz;
      // Vitesse initiale tangentielle, meme cap general pour toute la nuee.
      const h = g.baseHeading[0] + (rnd() - 0.5) * 0.5;
      const vx = t.x * Math.cos(h) + b.x * Math.sin(h);
      const vy = t.y * Math.cos(h) + b.y * Math.sin(h);
      const vz = t.z * Math.cos(h) + b.z * Math.sin(h);
      const sp = arch.cruise * (0.85 + rnd() * 0.3);
      g.vel[o] = vx * sp;
      g.vel[o + 1] = vy * sp;
      g.vel[o + 2] = vz * sp;
    }
    updateFlockCenter(g);
  }

  function initHerd(g, arch, rnd) {
    const n = g.size;
    const t = g.tangent;
    const b = g.bitangent;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      const su = (rnd() - 0.5) * HERD_RADIUS * 1.4;
      const sv = (rnd() - 0.5) * HERD_RADIUS * 1.4;
      _dir
        .set(
          g.anchor.x + t.x * su + b.x * sv,
          g.anchor.y + t.y * su + b.y * sv,
          g.anchor.z + t.z * su + b.z * sv,
        )
        .normalize();
      const gr = heightField.surfaceRadius(_dir);
      g.ground[i] = gr;
      g.pos[o] = _dir.x * gr;
      g.pos[o + 1] = _dir.y * gr;
      g.pos[o + 2] = _dir.z * gr;
      heightField.normalAt(_dir, _up);
      g.normals[o] = _up.x;
      g.normals[o + 1] = _up.y;
      g.normals[o + 2] = _up.z;
      // Direction de marche initiale.
      const h = g.heading[i];
      g.dirs[o] = t.x * Math.cos(h) + b.x * Math.sin(h);
      g.dirs[o + 1] = t.y * Math.cos(h) + b.y * Math.sin(h);
      g.dirs[o + 2] = t.z * Math.cos(h) + b.z * Math.sin(h);
    }
    updateHerdCenter(g);
  }

  function destroyGroup(g) {
    const mesh = meshes[g.kind];
    const alloc = allocators[g.kind];
    for (let i = 0; i < g.size; i++) mesh.setMatrixAt(g.base + i, _zeroMatrix);
    mesh.instanceMatrix.needsUpdate = true;
    alloc.release(g.block);
    mesh.count = alloc.highCount();
    const idx = groups.indexOf(g);
    if (idx >= 0) groups.splice(idx, 1);
    individuals -= g.size;
  }

  // -------------------------------------------------------------------------
  // Comportement : nuee (boids simplifie a 3 regles)
  // -------------------------------------------------------------------------

  function updateFlockCenter(g) {
    const n = g.size;
    const pos = g.pos;
    let cx = 0;
    let cy = 0;
    let cz = 0;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      cx += pos[o];
      cy += pos[o + 1];
      cz += pos[o + 2];
    }
    const inv = 1 / n;
    g.center.set(cx * inv, cy * inv, cz * inv);
  }

  function updateFlock(g, dt) {
    const n = g.size;
    const pos = g.pos;
    const vel = g.vel;
    const arch = ARCHETYPES.flyer;

    let cx = 0;
    let cy = 0;
    let cz = 0;
    let mvx = 0;
    let mvy = 0;
    let mvz = 0;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      cx += pos[o];
      cy += pos[o + 1];
      cz += pos[o + 2];
      mvx += vel[o];
      mvy += vel[o + 1];
      mvz += vel[o + 2];
    }
    const inv = 1 / n;
    cx *= inv;
    cy *= inv;
    cz *= inv;
    mvx *= inv;
    mvy *= inv;
    mvz *= inv;
    g.center.set(cx, cy, cz);

    // Rayon du sol : UN appel a heightField par groupe, toutes les N frames.
    g.groundTimer -= 1;
    if (g.groundTimer <= 0) {
      g.groundTimer = FLOCK_GROUND_FRAMES;
      const cl = len3(cx, cy, cz) || 1;
      _dir.set(cx / cl, cy / cl, cz / cl);
      g.groundRadius = heightField.surfaceRadius(_dir);
    }
    const targetR = g.groundRadius + g.altitude;

    const sep2 = SEPARATION_DIST * SEPARATION_DIST;

    for (let i = 0; i < n; i++) {
      const o = i * 3;
      const px = pos[o];
      const py = pos[o + 1];
      const pz = pos[o + 2];

      // 1. cohesion vers le centre du groupe
      let axf = (cx - px) * COHESION;
      let ayf = (cy - py) * COHESION;
      let azf = (cz - pz) * COHESION;

      // 2. separation a courte distance
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const oj = j * 3;
        const dx = px - pos[oj];
        const dy = py - pos[oj + 1];
        const dz = pz - pos[oj + 2];
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < sep2 && d2 > 1e-4) {
          const d = Math.sqrt(d2);
          const w = (1 - d / SEPARATION_DIST) * SEPARATION / d;
          axf += dx * w;
          ayf += dy * w;
          azf += dz * w;
        }
      }

      // 3. alignement des vitesses
      axf += (mvx - vel[o]) * ALIGNMENT;
      ayf += (mvy - vel[o + 1]) * ALIGNMENT;
      azf += (mvz - vel[o + 2]) * ALIGNMENT;

      // Rappel vers l'ancre au-dela de la laisse.
      const lx = g.anchor.x - px;
      const ly = g.anchor.y - py;
      const lz = g.anchor.z - pz;
      const ld = len3(lx, ly, lz);
      if (ld > LEASH_RADIUS) {
        const w = (LEASH_FORCE * Math.min(ld - LEASH_RADIUS, 400)) / ld;
        axf += lx * w;
        ayf += ly * w;
        azf += lz * w;
      }

      // Rappel vers l'altitude cible + amortissement radial.
      const r = len3(px, py, pz) || 1;
      const ux = px / r;
      const uy = py / r;
      const uz = pz / r;
      const err = clamp(targetR - r, -90, 90);
      const vr = vel[o] * ux + vel[o + 1] * uy + vel[o + 2] * uz;
      const kr = err * ALTITUDE_FORCE - vr * ALTITUDE_DAMP;
      axf += ux * kr;
      ayf += uy * kr;
      azf += uz * kr;

      // Integration.
      let nvx = vel[o] + axf * dt;
      let nvy = vel[o + 1] + ayf * dt;
      let nvz = vel[o + 2] + azf * dt;
      let sp = len3(nvx, nvy, nvz);
      if (sp < 1e-4) {
        nvx = g.tangent.x * arch.minSpeed;
        nvy = g.tangent.y * arch.minSpeed;
        nvz = g.tangent.z * arch.minSpeed;
        sp = arch.minSpeed;
      } else if (sp > arch.maxSpeed) {
        const k = arch.maxSpeed / sp;
        nvx *= k;
        nvy *= k;
        nvz *= k;
        sp = arch.maxSpeed;
      } else if (sp < arch.minSpeed) {
        const k = arch.minSpeed / sp;
        nvx *= k;
        nvy *= k;
        nvz *= k;
        sp = arch.minSpeed;
      }
      vel[o] = nvx;
      vel[o + 1] = nvy;
      vel[o + 2] = nvz;
      pos[o] = px + nvx * dt;
      pos[o + 1] = py + nvy * dt;
      pos[o + 2] = pz + nvz * dt;

      // Roulis : proportionnel a l'acceleration laterale (virage).
      const fx = nvx / sp;
      const fy = nvy / sp;
      const fz = nvz / sp;
      let rx = uy * fz - uz * fy;
      let ry = uz * fx - ux * fz;
      let rz = ux * fy - uy * fx;
      const rl = len3(rx, ry, rz);
      let lat = 0;
      if (rl > 1e-5) {
        rx /= rl;
        ry /= rl;
        rz /= rl;
        lat = axf * rx + ayf * ry + azf * rz;
      }
      const target = clamp(-lat * ROLL_GAIN, -0.95, 0.95);
      g.roll[i] = damp(g.roll[i], target, ROLL_LAMBDA, dt);
    }
  }

  function writeFlockMatrices(g) {
    const mesh = meshes.flyer;
    const n = g.size;
    const pos = g.pos;
    const vel = g.vel;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      _pos.set(pos[o], pos[o + 1], pos[o + 2]);
      _up.copy(_pos).normalize();
      _fwd.set(vel[o], vel[o + 1], vel[o + 2]);
      if (_fwd.lengthSq() < 1e-8) _fwd.copy(g.tangent);
      _fwd.normalize();
      _right.crossVectors(_up, _fwd);
      if (_right.lengthSq() < 1e-8) _right.copy(g.bitangent);
      _right.normalize();
      _upOrtho.crossVectors(_fwd, _right).normalize();
      _basis.makeBasis(_right, _upOrtho, _fwd);
      _quat.setFromRotationMatrix(_basis);
      _quatRoll.setFromAxisAngle(AXIS_FORWARD, g.roll[i]);
      _quat.multiply(_quatRoll);
      _scaleVec.setScalar(g.scl[i]);
      _matrix.compose(_pos, _quat, _scaleVec);
      mesh.setMatrixAt(g.base + i, _matrix);
    }
  }

  // -------------------------------------------------------------------------
  // Comportement : troupeau au sol
  // -------------------------------------------------------------------------

  function updateHerdCenter(g) {
    const n = g.size;
    const pos = g.pos;
    let cx = 0;
    let cy = 0;
    let cz = 0;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      cx += pos[o];
      cy += pos[o + 1];
      cz += pos[o + 2];
    }
    const inv = 1 / n;
    g.center.set(cx * inv, cy * inv, cz * inv);
  }

  function updateHerd(g, dt) {
    const n = g.size;
    const pos = g.pos;
    const t = g.tangent;
    const b = g.bitangent;
    const slot = frame % HERD_GROUND_SLOTS;
    const normalSlot = frame % n;

    for (let i = 0; i < n; i++) {
      const o = i * 3;
      let px = pos[o];
      let py = pos[o + 1];
      let pz = pos[o + 2];

      // Cap lisse par bruit de Perlin sur le temps.
      const nz = noise2D(g.noiseOffset + i * 4.31, time * 0.11);
      const h = g.baseHeading[i] + nz * HERD_TURN;
      let dx = t.x * Math.cos(h) + b.x * Math.sin(h);
      let dy = t.y * Math.cos(h) + b.y * Math.sin(h);
      let dz = t.z * Math.cos(h) + b.z * Math.sin(h);

      const r = len3(px, py, pz) || 1;
      let ux = px / r;
      let uy = py / r;
      let uz = pz / r;

      // Projection dans le plan tangent local.
      let d = dx * ux + dy * uy + dz * uz;
      dx -= ux * d;
      dy -= uy * d;
      dz -= uz * d;
      let dl = len3(dx, dy, dz);
      if (dl < 1e-5) {
        dx = t.x;
        dy = t.y;
        dz = t.z;
        dl = 1;
      }
      dx /= dl;
      dy /= dl;
      dz /= dl;

      // Biais vers l'ancre quand on sort de la zone de paturage.
      const lx = g.anchor.x - px;
      const ly = g.anchor.y - py;
      const lz = g.anchor.z - pz;
      const ld = len3(lx, ly, lz);
      const w = smoothstep(HERD_RADIUS, HERD_RADIUS * 1.7, ld);
      if (w > 0.001) {
        let bx = lx;
        let by = ly;
        let bz = lz;
        d = bx * ux + by * uy + bz * uz;
        bx -= ux * d;
        by -= uy * d;
        bz -= uz * d;
        const bl = len3(bx, by, bz);
        if (bl > 1e-5) {
          bx /= bl;
          by /= bl;
          bz /= bl;
          dx = dx * (1 - w) + bx * w;
          dy = dy * (1 - w) + by * w;
          dz = dz * (1 - w) + bz * w;
          const nl = len3(dx, dy, dz) || 1;
          dx /= nl;
          dy /= nl;
          dz /= nl;
        }
      }

      // Avance : certains individus s'arretent pour paitre.
      const gait = Math.max(0, 0.35 + nz * 0.9);
      const step = HERD_SPEED * g.speedMul[i] * gait * dt;
      px += dx * step;
      py += dy * step;
      pz += dz * step;

      const rl = len3(px, py, pz) || 1;
      ux = px / rl;
      uy = py / rl;
      uz = pz / rl;

      // Re-echantillonnage du sol : 1 individu sur 4 par frame.
      if (i % HERD_GROUND_SLOTS === slot) {
        _dir.set(ux, uy, uz);
        g.ground[i] = heightField.surfaceRadius(_dir);
      }
      // La normale coute 3 elevations : un seul individu par groupe et par frame.
      if (i === normalSlot) {
        _dir.set(ux, uy, uz);
        heightField.normalAt(_dir, _up);
        g.normals[o] = _up.x;
        g.normals[o + 1] = _up.y;
        g.normals[o + 2] = _up.z;
      }

      const bob = Math.sin(time * 2.4 + g.phase[i]) * HERD_BOB * (0.3 + gait);
      const surf = g.ground[i] + bob;
      pos[o] = ux * surf;
      pos[o + 1] = uy * surf;
      pos[o + 2] = uz * surf;

      // Direction de marche lissee pour l'orientation visuelle.
      g.dirs[o] = damp(g.dirs[o], dx, 4, dt);
      g.dirs[o + 1] = damp(g.dirs[o + 1], dy, 4, dt);
      g.dirs[o + 2] = damp(g.dirs[o + 2], dz, 4, dt);
    }

    updateHerdCenter(g);
  }

  function writeHerdMatrices(g) {
    const mesh = meshes.grazer;
    const n = g.size;
    const pos = g.pos;
    for (let i = 0; i < n; i++) {
      const o = i * 3;
      _pos.set(pos[o], pos[o + 1], pos[o + 2]);
      _up.set(g.normals[o], g.normals[o + 1], g.normals[o + 2]);
      if (_up.lengthSq() < 1e-8) _up.copy(_pos).normalize();
      _fwd.set(g.dirs[o], g.dirs[o + 1], g.dirs[o + 2]);
      if (_fwd.lengthSq() < 1e-8) _fwd.copy(g.tangent);
      _fwd.normalize();
      _right.crossVectors(_up, _fwd);
      if (_right.lengthSq() < 1e-8) _right.copy(g.bitangent);
      _right.normalize();
      _fwd.crossVectors(_right, _up).normalize();
      _basis.makeBasis(_right, _up, _fwd);
      _quat.setFromRotationMatrix(_basis);
      _scaleVec.setScalar(g.scl[i]);
      _matrix.compose(_pos, _quat, _scaleVec);
      mesh.setMatrixAt(g.base + i, _matrix);
    }
  }

  // -------------------------------------------------------------------------
  // Boucle
  // -------------------------------------------------------------------------

  function update(dt, ctx) {
    if (disposed) return;
    frame += 1;
    time += dt;

    const u = material.uniforms;
    u.uTime.value = time;
    let cam = null;
    if (ctx) {
      if (ctx.sunDirLocal) u.uSunDir.value.copy(ctx.sunDirLocal);
      if (ctx.cameraLocal) {
        u.uCameraLocal.value.copy(ctx.cameraLocal);
        cam = ctx.cameraLocal;
      }
      if (ctx.fogColor) u.uFogColor.value.copy(ctx.fogColor);
      if (typeof ctx.fogDensity === 'number') u.uFogDensity.value = ctx.fogDensity;
    }

    matricesDirty = false;
    for (let i = 0; i < groups.length; i++) {
      const g = groups[i];
      if (cam) {
        const dx = cam.x - g.center.x;
        const dy = cam.y - g.center.y;
        const dz = cam.z - g.center.z;
        // Sommeil : les groupes lointains restent visibles mais figes.
        if (len3(dx, dy, dz) - g.radius > AWAKE_DISTANCE) continue;
      }
      if (g.kind === 'flyer') {
        updateFlock(g, dt);
        writeFlockMatrices(g);
      } else {
        updateHerd(g, dt);
        writeHerdMatrices(g);
      }
      matricesDirty = true;
    }

    if (matricesDirty) {
      meshes.flyer.instanceMatrix.needsUpdate = true;
      meshes.grazer.instanceMatrix.needsUpdate = true;
    }
  }

  /** Individu vivant le plus proche, en metres. Objet reutilise entre appels. */
  function nearest(cameraLocal) {
    if (disposed || !cameraLocal || groups.length === 0) return null;
    let best = Infinity;
    let bestGroup = null;
    let bestIndex = -1;
    for (let gi = 0; gi < groups.length; gi++) {
      const g = groups[gi];
      const cdx = cameraLocal.x - g.center.x;
      const cdy = cameraLocal.y - g.center.y;
      const cdz = cameraLocal.z - g.center.z;
      if (len3(cdx, cdy, cdz) - g.radius > SEARCH_DISTANCE) continue;
      const pos = g.pos;
      for (let i = 0; i < g.size; i++) {
        const o = i * 3;
        const dx = cameraLocal.x - pos[o];
        const dy = cameraLocal.y - pos[o + 1];
        const dz = cameraLocal.z - pos[o + 2];
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < best) {
          best = d2;
          bestGroup = g;
          bestIndex = i;
        }
      }
    }
    if (!bestGroup) return null;
    const o = bestIndex * 3;
    _nearest.distance = Math.sqrt(best);
    _nearest.position.set(bestGroup.pos[o], bestGroup.pos[o + 1], bestGroup.pos[o + 2]);
    _nearest.kind = bestGroup.kind;
    return _nearest;
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    patches.clear();
    groups.length = 0;
    individuals = 0;
    const kinds = ['flyer', 'grazer'];
    for (let i = 0; i < kinds.length; i++) {
      const mesh = meshes[kinds[i]];
      if (!mesh) continue;
      object3D.remove(mesh);
      mesh.geometry.dispose();
      mesh.dispose();
      allocators[kinds[i]].clear();
      meshes[kinds[i]] = null;
    }
    material.dispose();
    object3D.clear();
  }

  return {
    object3D,
    addPatch,
    removePatch,
    update,
    nearest,
    get count() {
      return individuals;
    },
    get stats() {
      let flocks = 0;
      for (let i = 0; i < groups.length; i++) if (groups[i].kind === 'flyer') flocks++;
      return {
        groups: groups.length,
        flocks,
        herds: groups.length - flocks,
        individuals,
      };
    },
    dispose,
  };
}
