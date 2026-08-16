/**
 * ABYSSE - world.js
 *
 * Owns the seabed heightfield, the biomes, every static prop (rocks, arches,
 * corals, kelp, anemones, abyssal polyps), the wreck of the Meroe, the island
 * with its dock, field laboratory and scientist, plus the collision grid.
 *
 * Everything is generated from makeRandom(seed) so the world rebuilds
 * identically on every boot. No external asset, no import besides three and
 * config.js. heightAt() is a pure analytic function (noise tables sampled with
 * smooth interpolation), the display mesh samples the exact same function, so
 * physics and visuals always agree.
 */

import * as THREE from 'three';
import {
  WORLD,
  BIOMES,
  BIOME_INFO,
  PALETTE,
  clamp,
  clamp01,
  lerp,
  makeRandom,
} from './config.js';

// ---------------------------------------------------------------------------
// Module level constants and preallocated scratch (never allocate per frame)
// ---------------------------------------------------------------------------

const WORLD_SEED = 20260815;
const TAU = Math.PI * 2;

// Fixed landmark positions (world space).
const WRECK_POS = { x: 240, z: 420, yaw: 0.62 };
const WRECK_BIOME_RADIUS = 125;

/**
 * Near vertical shafts punched below the surrounding floor. They are what makes
 * depth worth exploring: each one is a landmark, and since `biomeAt` resolves
 * on depth, a hole deep enough grows its own pocket of abyssal life inside a
 * shallower zone.
 */
const DEEP_HOLES = [
  { x: -120, z: 250, r: 72, depth: -98 },   // the near pit, reachable early
  { x: -430, z: 470, r: 96, depth: -152 },  // the blue hole
  { x: 560, z: 380, r: 84, depth: -130 },
  { x: 300, z: 660, r: 124, depth: -166 },  // the deepest point of the map
];

const ARCH_DATA = [
  { x: -320, z: 330, yaw: 0.7, scale: 1.25 },
  { x: 520, z: 180, yaw: 2.3, scale: 1.0 },
  { x: -660, z: -20, yaw: 4.1, scale: 0.85 },
];

// Depth profile away from the island centre: control distances and heights.
// Smooth-stepped between control points, then noise is layered on top.
const PROFILE_D = [150, 300, 470, 620, 760, 950, 1120, 1320, 1560, 2200];
const PROFILE_H = [-9, -14, -19, -28, -42, -56, -74, -96, -118, -128];

// Scratch objects shared by the whole module (build + per frame).
const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();
const _q1 = new THREE.Quaternion();
const _q2 = new THREE.Quaternion();
const _m1 = new THREE.Matrix4();
const _color = new THREE.Color();
const _dummy = new THREE.Object3D();
const _collideOut = new THREE.Vector3();
const UP = new THREE.Vector3(0, 1, 0);

// ---------------------------------------------------------------------------
// Small maths helpers
// ---------------------------------------------------------------------------

function smoothstep(a, b, x) {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
}

/**
 * Height of the radial seabed profile at island distance d.
 *
 * Monotone cubic rather than a smoothstep per segment. smoothstep flattens to
 * zero slope at *both* ends of every segment, so each control distance became a
 * terrace: a ring of level seabed around the island every couple of hundred
 * metres, with a crease where the next slope started. It was invisible while
 * the seabed was soft and blurry, and stood out as a straight seam once the
 * relief and the normals got sharper. The Hermite form below keeps exactly the
 * same depth at every control point, so biomes and gameplay distances do not
 * move, but its slope is continuous across them.
 */
function profileDepth(d) {
  const n = PROFILE_D.length;
  if (d <= PROFILE_D[0]) return PROFILE_H[0];
  if (d >= PROFILE_D[n - 1]) return PROFILE_H[n - 1];
  let i = 1;
  while (i < n - 1 && d > PROFILE_D[i]) i++;
  const d0 = PROFILE_D[i - 1];
  const d1 = PROFILE_D[i];
  const h0 = PROFILE_H[i - 1];
  const h1 = PROFILE_H[i];
  const span = d1 - d0;
  const secant = (h1 - h0) / span;
  const before = i > 1 ? (h0 - PROFILE_H[i - 2]) / (d0 - PROFILE_D[i - 2]) : secant;
  const after = i < n - 1 ? (PROFILE_H[i + 1] - h1) / (PROFILE_D[i + 1] - d1) : secant;
  // Fritsch-Carlson limiter: tangents capped at three times the local secant,
  // which is what stops a cubic from bulging back up inside a descending step.
  const lim = 3 * Math.abs(secant);
  let m0 = (before + secant) * 0.5;
  let m1 = (secant + after) * 0.5;
  if (Math.abs(m0) > lim) m0 = Math.sign(m0) * lim;
  if (Math.abs(m1) > lim) m1 = Math.sign(m1) * lim;
  const t = (d - d0) / span;
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    (2 * t3 - 3 * t2 + 1) * h0 +
    (t3 - 2 * t2 + t) * span * m0 +
    (-2 * t3 + 3 * t2) * h1 +
    (t3 - t2) * span * m1
  );
}

// ---------------------------------------------------------------------------
// Value noise. The permutation and value tables are built ONCE from the
// seeded rng; sampling never touches the rng, so heightAt is deterministic
// and cheap (a handful of lerps per octave).
// ---------------------------------------------------------------------------

function buildNoise(rng) {
  const perm = new Uint16Array(512);
  // Unit gradient per lattice point instead of a scalar value. Value noise puts
  // every hill and hollow exactly on a lattice point, which is what gave the
  // seabed its melted, grid-aligned look; gradient noise puts them in between,
  // so ridges and hollows run at arbitrary angles.
  const gx = new Float32Array(256);
  const gy = new Float32Array(256);
  for (let i = 0; i < 256; i++) {
    const a = rng() * Math.PI * 2;
    gx[i] = Math.cos(a);
    gy[i] = Math.sin(a);
    perm[i] = i;
  }
  // Fisher-Yates shuffle of the permutation table.
  for (let i = 255; i > 0; i--) {
    const j = (rng() * (i + 1)) | 0;
    const t = perm[i];
    perm[i] = perm[j];
    perm[j] = t;
  }
  for (let i = 0; i < 256; i++) perm[i + 256] = perm[i];

  /** Smooth gradient (Perlin) noise in [0, 1]. */
  function noise2(x, y) {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const xf = x - xi;
    const yf = y - yi;
    // Quintic fade rather than smoothstep: its second derivative vanishes at
    // the lattice, so the shading has no crease along the grid lines.
    const u = xf * xf * xf * (xf * (xf * 6 - 15) + 10);
    const v = yf * yf * yf * (yf * (yf * 6 - 15) + 10);
    const X = xi & 255;
    const Y = yi & 255;
    const h00 = perm[X + perm[Y]] & 255;
    const h10 = perm[X + 1 + perm[Y]] & 255;
    const h01 = perm[X + perm[Y + 1]] & 255;
    const h11 = perm[X + 1 + perm[Y + 1]] & 255;
    const n00 = gx[h00] * xf + gy[h00] * yf;
    const n10 = gx[h10] * (xf - 1) + gy[h10] * yf;
    const n01 = gx[h01] * xf + gy[h01] * (yf - 1);
    const n11 = gx[h11] * (xf - 1) + gy[h11] * (yf - 1);
    const a = n00 + (n10 - n00) * u;
    const b = n01 + (n11 - n01) * u;
    // 2D gradient noise spans about [-sqrt(2)/2, sqrt(2)/2]; remap to [0, 1].
    return (a + (b - a) * v) * 0.7071 + 0.5;
  }

  /** Fractal brownian motion, normalised to [0, 1]. */
  function fbm(x, y, octaves) {
    let amp = 0.5;
    let freq = 1;
    let sum = 0;
    let norm = 0;
    for (let i = 0; i < octaves; i++) {
      sum += noise2(x * freq, y * freq) * amp;
      norm += amp;
      amp *= 0.5;
      freq *= 2.03;
    }
    return sum / norm;
  }

  /**
   * Ridged noise in [0, 1], crests, good for rocky terrain.
   *
   * The crest sits exactly where the absolute value folds, and a true abs()
   * folds to a zero-width edge. On a 6 m mesh that averaged away; on a 3.5 m
   * one it draws a thin seam straight across the sand. The smooth abs below
   * rounds the fold over a fixed width, so a crest reads as a ridge instead of
   * a crack, without moving it or changing its amplitude.
   */
  const RIDGE_ROUND = 0.16;

  function ridged(x, y, octaves) {
    let amp = 0.5;
    let freq = 1;
    let sum = 0;
    let norm = 0;
    for (let i = 0; i < octaves; i++) {
      const t = 2 * noise2(x * freq, y * freq) - 1;
      // sqrt(t^2 + k^2) - k equals |t| away from zero and rounds it within +/-k.
      const folded = Math.sqrt(t * t + RIDGE_ROUND * RIDGE_ROUND) - RIDGE_ROUND;
      const n = 1 - folded;
      sum += n * n * amp;
      norm += amp;
      amp *= 0.5;
      freq *= 2.11;
    }
    return sum / norm;
  }

  return { noise2, fbm, ridged };
}

// ---------------------------------------------------------------------------
// Geometry helpers (build time only, allocation is fine here)
// ---------------------------------------------------------------------------

/** Merge a list of BufferGeometries (position / normal / uv) into one. */
function mergeGeometries(geoms) {
  const list = [];
  const clones = [];
  for (const g of geoms) {
    if (!g.attributes.normal) g.computeVertexNormals();
    if (g.index) {
      const ni = g.toNonIndexed();
      list.push(ni);
      clones.push(ni);
    } else {
      list.push(g);
    }
  }
  let total = 0;
  for (const g of list) total += g.attributes.position.count;
  const pos = new Float32Array(total * 3);
  const nor = new Float32Array(total * 3);
  const uv = new Float32Array(total * 2);
  let o = 0;
  for (const g of list) {
    const n = g.attributes.position.count;
    pos.set(g.attributes.position.array, o * 3);
    if (g.attributes.normal) nor.set(g.attributes.normal.array, o * 3);
    if (g.attributes.uv) uv.set(g.attributes.uv.array, o * 2);
    o += n;
  }
  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  merged.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
  merged.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  for (const c of clones) c.dispose();
  return merged;
}

/** Displace vertices radially from the origin using the noise suite. */
function displaceRadial(geometry, noise, amp, freq, seed) {
  const p = geometry.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const y = p.getY(i);
    const z = p.getZ(i);
    const len = Math.sqrt(x * x + y * y + z * z) || 1;
    const n = noise.fbm(x * freq + seed + y * 0.71, z * freq - y * 0.53 + seed, 3);
    const s = 1 + (n - 0.5) * amp;
    p.setXYZ(i, (x / len) * len * s, (y / len) * len * s, (z / len) * len * s);
  }
  geometry.computeVertexNormals();
  return geometry;
}

/** Low poly boulder, icosahedron or dodecahedron with noisy displacement. */
function makeRockGeometry(noise, radius, seed, chunky) {
  const geo = chunky
    ? new THREE.DodecahedronGeometry(radius, 1)
    : new THREE.IcosahedronGeometry(radius, 1);
  displaceRadial(geo, noise, 0.7, 0.9 / radius, seed);
  if (chunky) geo.scale(1.15, 0.72, 1.0);
  return geo;
}

/** Rock arch: half torus standing in the XY plane, displaced for a rocky look. */
function makeArchGeometry(noise, seed) {
  const geo = new THREE.TorusGeometry(10, 2.8, 10, 20, Math.PI);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const y = p.getY(i);
    const z = p.getZ(i);
    const n = noise.fbm(x * 0.35 + seed, y * 0.35 + z * 0.5, 3);
    const s = 1 + (n - 0.5) * 0.55;
    p.setXYZ(i, x * s, y * s, z * s);
  }
  geo.computeVertexNormals();
  return geo;
}

/** Brain coral: squashed sphere with bumpy displacement. */
function makeBrainCoralGeometry(noise, seed) {
  // 12x9 was 192 triangles for a 55 cm lump drawn 1500 times. At 8x6 the
  // silhouette is indistinguishable through the fog and it costs 80.
  const geo = new THREE.SphereGeometry(0.55, 8, 6);
  displaceRadial(geo, noise, 0.4, 4.2, seed);
  geo.scale(1, 0.62, 1);
  geo.translate(0, 0.22, 0);
  return geo;
}

/** Branching coral: recursive cylinder branches merged into one geometry. */
function makeBranchCoralGeometry(rng) {
  const parts = [];
  function branch(origin, dir, len, rad, depth) {
    // Open ended, and 4 sides instead of 5: the caps were interior faces buried
    // in the parent branch or facing away at the twig tips, so they were 40% of
    // this geometry drawn 1200 times for nothing.
    const seg = new THREE.CylinderGeometry(rad * 0.6, rad, len, 4, 1, true);
    seg.translate(0, len * 0.5, 0);
    _q1.setFromUnitVectors(UP, dir);
    _m1.compose(origin, _q1, _v3.set(1, 1, 1));
    seg.applyMatrix4(_m1);
    parts.push(seg);
    if (depth <= 0) return;
    const end = origin.clone().addScaledVector(dir, len * 0.94);
    const count = 2 + Math.floor(rng() * 2);
    for (let i = 0; i < count; i++) {
      const nd = dir.clone();
      nd.x += (rng() - 0.5) * 1.6;
      nd.z += (rng() - 0.5) * 1.6;
      nd.y += rng() * 0.55;
      nd.normalize();
      if (nd.y < 0.25) {
        nd.y = 0.25;
        nd.normalize();
      }
      branch(end, nd, len * (0.6 + rng() * 0.18), rad * 0.66, depth - 1);
    }
  }
  branch(new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 1, 0), 0.55, 0.1, 3);
  const merged = mergeGeometries(parts);
  for (const g of parts) g.dispose();
  return merged;
}

/** Table coral: stalk plus a wide flattened disc with a wavy rim. */
function makeTableCoralGeometry(noise, seed) {
  // Stalk open ended: both caps are buried, one in the disc and one in the sand.
  const stalk = new THREE.CylinderGeometry(0.1, 0.16, 0.55, 6, 1, true);
  stalk.translate(0, 0.27, 0);
  const top = new THREE.CylinderGeometry(1.35, 1.0, 0.16, 12, 1);
  const p = top.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i);
    const z = p.getZ(i);
    const r = Math.sqrt(x * x + z * z);
    const n = noise.fbm(x * 1.7 + seed, z * 1.7 - seed, 2);
    p.setY(i, p.getY(i) + (n - 0.5) * 0.28 * clamp01(r));
  }
  top.computeVertexNormals();
  top.translate(0, 0.6, 0);
  const merged = mergeGeometries([stalk, top]);
  stalk.dispose();
  top.dispose();
  return merged;
}

/** Sea fan: a single upright plane, alpha handled by the material. */
function makeSeaFanGeometry() {
  const geo = new THREE.PlaneGeometry(1.7, 1.5, 1, 1);
  geo.translate(0, 0.75, 0);
  return geo;
}

/** Anemone: squashed base sphere plus a crown of tentacle cones. */
function makeAnemoneGeometry(rng) {
  const parts = [];
  const base = new THREE.SphereGeometry(0.24, 7, 5);
  base.scale(1, 0.5, 1);
  base.translate(0, 0.1, 0);
  parts.push(base);
  // 16 tentacles of 32 triangles each made this 592 triangles for a hand sized
  // animal placed 520 times, more than three times the whole terrain per 1000
  // instances. 10 open ended tentacles of 16 read the same at any distance the
  // fog allows; the 1.8 cm tip hole is never resolvable.
  const tentacles = 10;
  for (let i = 0; i < tentacles; i++) {
    const len = 0.4 + rng() * 0.25;
    const t = new THREE.CylinderGeometry(0.018, 0.05, len, 4, 2, true);
    t.translate(0, len * 0.5, 0);
    const ang = (i / tentacles) * TAU + rng() * 0.4;
    const tilt = 0.25 + rng() * 0.55;
    _q1.setFromAxisAngle(_v3.set(Math.cos(ang), 0, Math.sin(ang)), tilt);
    _m1.compose(
      _v1.set(Math.cos(ang) * 0.12, 0.14, Math.sin(ang) * 0.12),
      _q1,
      _v2.set(1, 1, 1)
    );
    t.applyMatrix4(_m1);
    parts.push(t);
  }
  const merged = mergeGeometries(parts);
  for (const g of parts) g.dispose();
  return merged;
}

/** Bioluminescent tube worm cluster for the abyss. */
function makePolypGeometry(rng) {
  const parts = [];
  const tubes = 4 + Math.floor(rng() * 3);
  for (let i = 0; i < tubes; i++) {
    const h = 0.45 + rng() * 0.5;
    const ox = (rng() - 0.5) * 0.4;
    const oz = (rng() - 0.5) * 0.4;
    // Open ended: the tip sphere caps the top and the ground caps the bottom.
    const tube = new THREE.CylinderGeometry(0.045, 0.075, h, 5, 1, true);
    tube.translate(ox, h * 0.5, oz);
    parts.push(tube);
    const tip = new THREE.SphereGeometry(0.09, 5, 4);
    tip.translate(ox, h, oz);
    parts.push(tip);
  }
  const merged = mergeGeometries(parts);
  for (const g of parts) g.dispose();
  return merged;
}

/** Kelp blade: two crossed planes with height segments for the sway shader. */
function makeKelpGeometry() {
  const a = new THREE.PlaneGeometry(0.85, 7.2, 1, 4);
  a.translate(0, 3.6, 0);
  const b = a.clone();
  b.rotateY(Math.PI / 2);
  const merged = mergeGeometries([a, b]);
  a.dispose();
  b.dispose();
  return merged;
}

/** Seagrass tuft: two small crossed planes, cheaper than kelp. */
function makeSeagrassGeometry() {
  const a = new THREE.PlaneGeometry(0.42, 1.6, 1, 3);
  a.translate(0, 0.8, 0);
  const b = a.clone();
  b.rotateY(Math.PI / 2);
  const merged = mergeGeometries([a, b]);
  a.dispose();
  b.dispose();
  return merged;
}

/** Island grass and scrub tuft, crossed foliage planes. */
function makeTuftGeometry() {
  const a = new THREE.PlaneGeometry(0.95, 0.85, 1, 1);
  a.translate(0, 0.42, 0);
  const b = a.clone();
  b.rotateY(Math.PI / 2);
  const merged = mergeGeometries([a, b]);
  a.dispose();
  b.dispose();
  return merged;
}

/** Palm trunk, tapered cylinder with a baked-in bend toward +x. */
function makePalmTrunkGeometry() {
  const H = 6.2;
  const geo = new THREE.CylinderGeometry(0.13, 0.24, H, 7, 5);
  geo.translate(0, H * 0.5, 0);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const t = p.getY(i) / H;
    p.setX(i, p.getX(i) + t * t * 1.1);
  }
  geo.computeVertexNormals();
  return geo;
}

/** Palm frond: a drooping plane extending along +x, pivot at the base. */
function makePalmFrondGeometry() {
  const L = 3.0;
  const geo = new THREE.PlaneGeometry(L, 1.0, 4, 1);
  geo.translate(L * 0.5, 0, 0);
  const p = geo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const t = p.getX(i) / L;
    p.setY(i, p.getY(i) - t * t * 1.15);
  }
  geo.computeVertexNormals();
  return geo;
}

// ---------------------------------------------------------------------------
// GPU sway: a small onBeforeCompile patch so kelp, seagrass, anemones and
// foliage move without any CPU work. The weight grows with local height so
// bases stay planted; the phase is derived from the instance position.
// ---------------------------------------------------------------------------

function applySwayPatch(material, timeUniform, opts) {
  const heightRef = opts.heightRef;
  const strength = opts.strength;
  const freq = opts.freq;
  const radial = !!opts.radial;
  const key = 'abysse-sway-' + opts.key;
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = timeUniform;
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        '#include <common>\nuniform float uTime;'
      )
      .replace(
        '#include <begin_vertex>',
        `#include <begin_vertex>
        {
          float swayW = clamp(position.y * ${(1 / heightRef).toFixed(5)}, 0.0, 1.0);
          swayW *= swayW;
          #ifdef USE_INSTANCING
            float ph = instanceMatrix[3][0] * 0.37 + instanceMatrix[3][2] * 0.43;
          #else
            float ph = 0.0;
          #endif
          ${
            radial
              ? `vec2 raddir = normalize(transformed.xz + vec2(0.0001, 0.0));
          float wig = sin(uTime * ${freq.toFixed(3)} + ph + position.y * 4.0);
          transformed.xz += raddir * wig * ${strength.toFixed(3)} * swayW;
          transformed.y += sin(uTime * ${(freq * 0.6).toFixed(3)} + ph) * ${(strength * 0.35).toFixed(3)} * swayW;`
              : `transformed.x += sin(uTime * ${freq.toFixed(3)} + ph + position.y * 0.35) * ${strength.toFixed(3)} * swayW;
          transformed.z += cos(uTime * ${(freq * 0.83).toFixed(3)} + ph * 1.7 + position.y * 0.3) * ${(strength * 0.7).toFixed(3)} * swayW;`
          }
        }`
      );
  };
  material.customProgramCacheKey = () => key;
  return material;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createWorld(scene, textures) {
  const group = new THREE.Group();
  group.name = 'world';
  scene.add(group);

  const rng = makeRandom(WORLD_SEED);
  const noise = buildNoise(rng);

  const timeUniform = { value: 0 };
  let localTime = 0;

  const ownedMaterials = [];
  function own(mat) {
    ownedMaterials.push(mat);
    return mat;
  }

  // -------------------------------------------------------------------------
  // SECTION: terrain height function
  //
  // A radial depth profile away from the island, plus layered noise, a ridged
  // band for the rocky zone, a bowl carved around the wreck, a trench in the
  // far south / outer region, and the island cone blended on top. Local
  // flatten spots keep the lab, the scientist and the dock on level ground.
  // -------------------------------------------------------------------------

  const ISLAND = WORLD.island;

  // Flatten targets: { x, z, r, h }. Applied last, smooth falloff.
  const FLATTEN = [
    { x: 35, z: -566, r: 42, h: 10.5 },   // lab and scientist plateau
    { x: -18, z: -498, r: 13, h: 1.2 },   // dock landing on the beach
    { x: -18, z: -484, r: 14, h: -3.6 },  // water pocket so the sub can berth
  ];

  function seabedAt(x, z) {
    const dxi = x - ISLAND.x;
    const dzi = z - ISLAND.z;
    const d = Math.sqrt(dxi * dxi + dzi * dzi);
    let h = profileDepth(d);

    // Broad relief, stronger with depth so the lagoon stays gentle.
    const n1 = noise.fbm(x * 0.008 + 7.3, z * 0.008 + 2.1, 4) - 0.5;
    const depthT = clamp01((-h - 12) / 60);
    h += n1 * (6 + 22 * depthT);

    // Reef scale shape. The depth ramp above deliberately keeps the lagoon
    // gentle, but "gentle" had become "billiard table": the shallow reef read
    // as a desert with no hummocks and no channels. This band restores that
    // shape without steepening anything. It fades out above 4 m so the beach
    // and the shoreline keep the profile they were authored with, and again
    // below 46 m where the broad depth relief takes over.
    const reefShape =
      smoothstep(-4, -16, h) * (1 - smoothstep(-30, -46, h));
    if (reefShape > 0.001) {
      const reef = noise.fbm(x * 0.016 + 61.7, z * 0.016 + 43.2, 3) - 0.5;
      h += reef * 6.0 * reefShape;
    }

    // Relief at swimming scale. The octave above has a 125 m wavelength: from
    // two metres above the sand that is a flat plain, whatever its amplitude.
    // These two are what the diver actually reads as ground - dune fields at
    // ~22 m and a low swell at ~11 m - and they run everywhere, including the
    // shallow lagoon that the depth ramp above leaves almost untouched.
    // Both wavelengths stay well above the 3.5 m terrain quad: at ~3 samples
    // per wave the mesh cannot reconstruct the crest and the reconstruction
    // error shows as long straight creases across the sand.
    const dune = noise.fbm(x * 0.035 + 31.4, z * 0.035 + 17.9, 3) - 0.5;
    const swell = noise.noise2(x * 0.058 + 5.1, z * 0.058 + 2.7) - 0.5;
    // Faded out on steep ground so it never fights the trench and canyon walls.
    const gentle = 1 - clamp01((-h - 96) / 60);
    h += (dune * 3.6 + swell * 1.5) * gentle;

    // Ridge and ravine band for the rocky zone.
    const band = smoothstep(680, 810, d) * (1 - smoothstep(980, 1140, d));
    if (band > 0.001) {
      const r = noise.ridged(x * 0.013 + 3.7, z * 0.013 + 9.2, 3);
      h += (r - 0.55) * 26 * band;
    }

    // Basin carved around the wreck.
    const dxw = x - WRECK_POS.x;
    const dzw = z - WRECK_POS.z;
    const dw = Math.sqrt(dxw * dxw + dzw * dzw);
    if (dw < 160) {
      const bowl = 1 - smoothstep(36, 155, dw);
      h = lerp(h, -70 + n1 * 4, bowl * 0.85);
    }

    // Trench: far south band with wavy steep walls, plus the outer ring.
    const edge = (noise.fbm(x * 0.006 + 11.7, 0.35, 2) - 0.5) * 90;
    const tz = smoothstep(600 + edge, 735 + edge, z);
    const outer = smoothstep(1450, 1750, d);
    const tr = Math.max(tz, outer);
    if (tr > 0.001) {
      h = lerp(h, WORLD.floorMin + 14 + n1 * 8, tr);
    }

    // Canyons: ridged noise used subtractively, so the deep floor is cut by
    // channels instead of being an even slope. Kept well clear of the reef so
    // the starting area stays shallow and readable.
    const canyon = smoothstep(860, 1040, d);
    if (canyon > 0.001) {
      const c = noise.ridged(x * 0.0055 + 21.3, z * 0.0055 + 4.9, 2);
      h -= Math.pow(clamp01(c), 2.2) * 38 * canyon;
    }

    // Deep holes only ever dig, never lift the floor.
    for (let i = 0; i < DEEP_HOLES.length; i++) {
      const hole = DEEP_HOLES[i];
      const dxh = x - hole.x;
      const dzh = z - hole.z;
      const dh2 = dxh * dxh + dzh * dzh;
      if (dh2 > hole.r * hole.r) continue;
      const dh = Math.sqrt(dh2);
      // Steep sided: flat rim, then a fast drop to the floor of the shaft.
      const t = 1 - smoothstep(hole.r * 0.3, hole.r, dh);
      const target = hole.depth + n1 * 4;
      if (target < h) h = lerp(h, target, t);
    }

    return clamp(h, WORLD.floorMin, WORLD.floorMax);
  }

  // Returns { h, blend } near the island, or null far away (fast out).
  function islandAt(x, z) {
    const dxi = x - ISLAND.x;
    const dzi = z - ISLAND.z;
    const d = Math.sqrt(dxi * dxi + dzi * dzi);
    if (d > 300) return null;
    const wob = (noise.fbm(x * 0.012 + 4.4, z * 0.012 + 8.8, 3) - 0.5) * 36;
    const r = d + wob;
    if (r > 260) return null;
    const s = clamp01(1 - r / 158);
    let h = ISLAND.peak * Math.pow(s, 1.45);
    h += (noise.fbm(x * 0.02 + 1.2, z * 0.02 + 5.6, 3) - 0.5) * 10 * s;
    h -= 5 * smoothstep(148, 210, r);
    h = Math.min(h, ISLAND.peak);
    return { h, blend: 1 - smoothstep(150, 240, r) };
  }

  function heightAt(x, z) {
    let h = seabedAt(x, z);
    const isl = islandAt(x, z);
    if (isl) h = lerp(h, isl.h, isl.blend);
    for (let i = 0; i < FLATTEN.length; i++) {
      const f = FLATTEN[i];
      const dx = x - f.x;
      const dz = z - f.z;
      const d2 = dx * dx + dz * dz;
      if (d2 < f.r * f.r) {
        const t = 1 - smoothstep(f.r * 0.45, f.r, Math.sqrt(d2));
        h = lerp(h, f.h, t);
      }
    }
    return h;
  }

  function slopeAt(x, z) {
    const e = 1.5;
    const hx = heightAt(x + e, z) - heightAt(x - e, z);
    const hz = heightAt(x, z + e) - heightAt(x, z - e);
    return Math.sqrt(hx * hx + hz * hz) / (2 * e);
  }

  function isLand(x, z) {
    return heightAt(x, z) > 0.2;
  }

  // -------------------------------------------------------------------------
  // SECTION: biomes
  // -------------------------------------------------------------------------

  function biomeAt(x, z) {
    const dxw = x - WRECK_POS.x;
    const dzw = z - WRECK_POS.z;
    if (dxw * dxw + dzw * dzw < WRECK_BIOME_RADIUS * WRECK_BIOME_RADIUS) {
      return BIOMES.WRECK;
    }
    const depth = -heightAt(x, z);
    if (depth < 28) return BIOMES.LAGOON;
    if (depth < 52) return BIOMES.KELP;
    if (depth < 72) return BIOMES.ROCKS;
    return BIOMES.ABYSS;
  }

  // -------------------------------------------------------------------------
  // SECTION: collision grid (spheres and capsules in a uniform XZ hash)
  // -------------------------------------------------------------------------

  const CELL = 12;
  const grid = new Map();
  let queryStamp = 0;

  function cellKey(cx, cz) {
    return (cx + 512) * 4096 + (cz + 512);
  }

  function addToGrid(c, minX, minZ, maxX, maxZ) {
    const c0 = Math.floor(minX / CELL);
    const c1 = Math.floor(maxX / CELL);
    const z0 = Math.floor(minZ / CELL);
    const z1 = Math.floor(maxZ / CELL);
    for (let cx = c0; cx <= c1; cx++) {
      for (let cz = z0; cz <= z1; cz++) {
        const key = cellKey(cx, cz);
        let cell = grid.get(key);
        if (!cell) {
          cell = [];
          grid.set(key, cell);
        }
        cell.push(c);
      }
    }
  }

  function addSphereCollider(x, y, z, r) {
    const c = { sph: true, x, y, z, r, stamp: 0 };
    addToGrid(c, x - r, z - r, x + r, z + r);
  }

  function addCapsuleCollider(ax, ay, az, bx, by, bz, r) {
    const dx = bx - ax;
    const dy = by - ay;
    const dz = bz - az;
    const len2 = dx * dx + dy * dy + dz * dz;
    const c = { sph: false, ax, ay, az, bx, by, bz, dx, dy, dz, len2, r, stamp: 0 };
    addToGrid(
      c,
      Math.min(ax, bx) - r,
      Math.min(az, bz) - r,
      Math.max(ax, bx) + r,
      Math.max(az, bz) + r
    );
  }

  function collide(position, radius) {
    let ox = 0;
    let oy = 0;
    let oz = 0;
    let hit = false;
    const px = position.x;
    const py = position.y;
    const pz = position.z;

    // Terrain: push up out of the ground.
    const ground = heightAt(px, pz);
    if (py - radius < ground) {
      oy += ground - (py - radius);
      hit = true;
    }

    // Props: visit only the grid cells overlapped by the player sphere.
    queryStamp++;
    const c0 = Math.floor((px - radius) / CELL);
    const c1 = Math.floor((px + radius) / CELL);
    const z0 = Math.floor((pz - radius) / CELL);
    const z1 = Math.floor((pz + radius) / CELL);
    for (let cx = c0; cx <= c1; cx++) {
      for (let cz = z0; cz <= z1; cz++) {
        const cell = grid.get(cellKey(cx, cz));
        if (!cell) continue;
        for (let i = 0; i < cell.length; i++) {
          const c = cell[i];
          if (c.stamp === queryStamp) continue;
          c.stamp = queryStamp;
          let qx;
          let qy;
          let qz;
          if (c.sph) {
            qx = c.x;
            qy = c.y;
            qz = c.z;
          } else {
            let t =
              ((px - c.ax) * c.dx + (py - c.ay) * c.dy + (pz - c.az) * c.dz) /
              c.len2;
            t = t < 0 ? 0 : t > 1 ? 1 : t;
            qx = c.ax + c.dx * t;
            qy = c.ay + c.dy * t;
            qz = c.az + c.dz * t;
          }
          const dx = px - qx;
          const dy = py - qy;
          const dz = pz - qz;
          const rr = c.r + radius;
          const d2 = dx * dx + dy * dy + dz * dz;
          if (d2 >= rr * rr) continue;
          const d = Math.sqrt(d2);
          if (d > 1e-5) {
            const pen = (rr - d) / d;
            ox += dx * pen;
            oy += dy * pen;
            oz += dz * pen;
          } else {
            oy += rr;
          }
          hit = true;
        }
      }
    }

    if (!hit) return null;
    _collideOut.set(ox, oy, oz);
    return _collideOut;
  }

  // -------------------------------------------------------------------------
  // SECTION: terrain mesh (single indexed BufferGeometry, vertex colours,
  // sand / beach / rock texture blend in a small shader patch)
  // -------------------------------------------------------------------------

  // 300 gave 6 m quads: wide enough that any relief below a 12 m wavelength was
  // averaged away before it ever reached the screen. 512 brings the quad to
  // 3.5 m, which is what the dune and swell octaves in seabedAt need to survive.
  // The extra triangles are paid for by the prop budget (see the geometry
  // builders above): the scene total goes down, not up.
  const RES = 512;
  const SIDE = RES + 1;
  const STEP = (WORLD.halfSize * 2) / RES;

  const terrainGeo = new THREE.BufferGeometry();
  {
    const positions = new Float32Array(SIDE * SIDE * 3);
    const uvs = new Float32Array(SIDE * SIDE * 2);
    let ptr = 0;
    let uptr = 0;
    for (let iz = 0; iz < SIDE; iz++) {
      const z = -WORLD.halfSize + iz * STEP;
      for (let ix = 0; ix < SIDE; ix++) {
        const x = -WORLD.halfSize + ix * STEP;
        positions[ptr++] = x;
        positions[ptr++] = heightAt(x, z);
        positions[ptr++] = z;
        uvs[uptr++] = x * 0.06;
        uvs[uptr++] = z * 0.06;
      }
    }
    const indices = new Uint32Array(RES * RES * 6);
    let ii = 0;
    for (let iz = 0; iz < RES; iz++) {
      for (let ix = 0; ix < RES; ix++) {
        const a = iz * SIDE + ix;
        const b = a + 1;
        const c = a + SIDE;
        const d = c + 1;
        indices[ii++] = a;
        indices[ii++] = c;
        indices[ii++] = b;
        indices[ii++] = b;
        indices[ii++] = c;
        indices[ii++] = d;
      }
    }
    terrainGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    terrainGeo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    terrainGeo.setIndex(new THREE.BufferAttribute(indices, 1));

    // Normals by central difference on the height grid rather than
    // computeVertexNormals(). For a heightfield this is the exact surface
    // normal; computeVertexNormals averages the triangle fan around each
    // vertex, and because every quad is split along the same diagonal that
    // average leans consistently one way, which shows up as a faint diagonal
    // corduroy across the whole seabed.
    const normalsArr = new Float32Array(SIDE * SIDE * 3);
    for (let iz = 0; iz < SIDE; iz++) {
      for (let ix = 0; ix < SIDE; ix++) {
        const i = iz * SIDE + ix;
        const xm = ix > 0 ? ix - 1 : ix;
        const xp = ix < SIDE - 1 ? ix + 1 : ix;
        const zm = iz > 0 ? iz - 1 : iz;
        const zp = iz < SIDE - 1 ? iz + 1 : iz;
        // Edge vertices fall back to a one-sided difference, hence the span.
        const dhx =
          (positions[(iz * SIDE + xp) * 3 + 1] - positions[(iz * SIDE + xm) * 3 + 1]) /
          ((xp - xm) * STEP);
        const dhz =
          (positions[(zp * SIDE + ix) * 3 + 1] - positions[(zm * SIDE + ix) * 3 + 1]) /
          ((zp - zm) * STEP);
        const inv = 1 / Math.sqrt(dhx * dhx + dhz * dhz + 1);
        normalsArr[i * 3] = -dhx * inv;
        normalsArr[i * 3 + 1] = inv;
        normalsArr[i * 3 + 2] = -dhz * inv;
      }
    }
    terrainGeo.setAttribute('normal', new THREE.BufferAttribute(normalsArr, 3));

    // Second pass: vertex tints plus rock / beach blend weights from the
    // heights and the computed normals.
    const colors = new Float32Array(SIDE * SIDE * 3);
    const aRock = new Float32Array(SIDE * SIDE);
    const aBeach = new Float32Array(SIDE * SIDE);
    const normals = terrainGeo.attributes.normal;
    for (let i = 0; i < SIDE * SIDE; i++) {
      const h = positions[i * 3 + 1];
      const slope = 1 - normals.getY(i);
      let rockF = smoothstep(0.12, 0.34, slope);
      let r;
      let g;
      let b;
      if (h >= 0) {
        // Beach up to grassy scrub, rockier near the peak.
        const gT = smoothstep(1.8, 8, h);
        r = lerp(1.0, 0.52, gT);
        g = lerp(0.97, 0.74, gT);
        b = lerp(0.88, 0.4, gT);
        rockF = clamp01(rockF + smoothstep(15, 26, h) * 0.5);
      } else {
        // Sand fading into dark abyssal sediment.
        const dT = clamp01((-h - 6) / 66);
        const aT = clamp01((-h - 72) / 55);
        r = lerp(0.99, lerp(0.38, 0.17, aT), dT);
        g = lerp(0.96, lerp(0.46, 0.22, aT), dT);
        b = lerp(0.87, lerp(0.53, 0.3, aT), dT);
      }
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
      aRock[i] = rockF;
      aBeach[i] = smoothstep(-2.2, 0.4, h) * (1 - rockF);
    }
    terrainGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    terrainGeo.setAttribute('aRock', new THREE.BufferAttribute(aRock, 1));
    terrainGeo.setAttribute('aBeach', new THREE.BufferAttribute(aBeach, 1));
  }

  const terrainMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.sand,
      normalMap: textures.sandNormal,
      roughnessMap: textures.sandRough,
      vertexColors: true,
      roughness: 1.0,
      metalness: 0.0,
    })
  );
  terrainMat.onBeforeCompile = (shader) => {
    shader.uniforms.uRockMap = { value: textures.rock };
    shader.uniforms.uBeachMap = { value: textures.beachSand };
    shader.uniforms.uMacro = { value: textures.noise };
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        '#include <common>\nattribute float aRock;\nattribute float aBeach;\nvarying float vRock;\nvarying float vBeach;'
      )
      .replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\nvRock = aRock;\nvBeach = aBeach;'
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        '#include <common>\nuniform sampler2D uRockMap;\nuniform sampler2D uBeachMap;\nuniform sampler2D uMacro;\nvarying float vRock;\nvarying float vBeach;'
      )
      .replace(
        '#include <map_fragment>',
        `#ifdef USE_MAP
        // The sand map covers 16 m and the world is 1800 m across, so it
        // repeats about 110 times along each axis. The fix is a very low
        // frequency lightness drift: it breaks the eye's ability to lock onto a
        // repeating patch, and unlike averaging in a second rotated lookup it
        // leaves the ripples intact. (That was tried: blending two lookups of a
        // directional pattern cancels the direction, and the rotated copy shows
        // up as long diagonal streaks of its own.)
        vec4 sandTexel = texture2D( map, vMapUv );
        float macro = texture2D( uMacro, vMapUv * 0.014 ).r;
        float macroFine = texture2D( uMacro, vMapUv * 0.11 ).r;
        sandTexel.rgb *= 0.80 + macro * 0.30 + macroFine * 0.12;
        vec4 rockTexel = texture2D( uRockMap, vMapUv * 1.6 );
        vec4 beachTexel = texture2D( uBeachMap, vMapUv * 2.1 );
        vec4 texelColor = mix( mix( sandTexel, beachTexel, vBeach ), rockTexel, vRock );
        diffuseColor *= texelColor;
        #endif`
      );
  };
  terrainMat.customProgramCacheKey = () => 'abysse-terrain';

  const terrainMesh = new THREE.Mesh(terrainGeo, terrainMat);
  terrainMesh.name = 'terrain';
  group.add(terrainMesh);

  // -------------------------------------------------------------------------
  // SECTION: shared prop materials
  // -------------------------------------------------------------------------

  const rockMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.rock,
      normalMap: textures.rockNormal,
      roughnessMap: textures.rockRough,
      roughness: 1.0,
      metalness: 0.0,
    })
  );

  const brainMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.coral,
      normalMap: textures.coralNormal,
      roughness: 0.85,
    })
  );
  const branchMat = own(
    new THREE.MeshStandardMaterial({ roughness: 0.8, metalness: 0.0 })
  );
  const tableMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.coral,
      normalMap: textures.coralNormal,
      roughness: 0.85,
    })
  );
  const fanMat = own(
    new THREE.MeshStandardMaterial({
      alphaMap: textures.foliage,
      alphaTest: 0.35,
      side: THREE.DoubleSide,
      roughness: 0.9,
    })
  );
  const anemoneMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({ roughness: 0.75 }),
      timeUniform,
      { key: 'anemone', heightRef: 0.7, strength: 0.06, freq: 1.7, radial: true }
    )
  );
  const kelpMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({
        map: textures.kelp,
        alphaTest: 0.3,
        side: THREE.DoubleSide,
        roughness: 0.9,
      }),
      timeUniform,
      { key: 'kelp', heightRef: 7.2, strength: 0.55, freq: 0.9 }
    )
  );
  const seagrassMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({
        map: textures.kelp,
        color: 0xa8e07a,
        alphaTest: 0.3,
        side: THREE.DoubleSide,
        roughness: 0.9,
      }),
      timeUniform,
      { key: 'seagrass', heightRef: 1.6, strength: 0.14, freq: 1.4 }
    )
  );
  // Broad brown seaweed: bigger, floppier and darker than the kelp of the
  // forest, so it reads as a different plant at a glance.
  const seaweedMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({
        map: textures.kelp,
        color: 0xb8935a,
        alphaTest: 0.3,
        side: THREE.DoubleSide,
        roughness: 0.86,
      }),
      timeUniform,
      { key: 'seaweed', heightRef: 3.4, strength: 0.42, freq: 1.15 }
    )
  );
  // Red algae crusting the rock, short and stiff.
  const redAlgaeMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({
        map: textures.foliage,
        color: 0xb03a5a,
        alphaTest: 0.35,
        side: THREE.DoubleSide,
        roughness: 0.92,
      }),
      timeUniform,
      { key: 'redalgae', heightRef: 1.1, strength: 0.1, freq: 1.7 }
    )
  );
  const polypMat = own(
    new THREE.MeshStandardMaterial({
      color: 0x18262f,
      emissive: PALETTE.bioluminescent,
      emissiveIntensity: 1.4,
      roughness: 0.6,
    })
  );
  const foliageMat = own(
    applySwayPatch(
      new THREE.MeshStandardMaterial({
        map: textures.foliage,
        alphaTest: 0.35,
        side: THREE.DoubleSide,
        roughness: 0.95,
      }),
      timeUniform,
      { key: 'foliage', heightRef: 0.85, strength: 0.05, freq: 1.9 }
    )
  );
  const frondMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.palmLeaf,
      alphaTest: 0.35,
      side: THREE.DoubleSide,
      roughness: 0.9,
    })
  );
  const trunkMat = own(
    new THREE.MeshStandardMaterial({ color: 0x8a6a48, roughness: 1.0 })
  );
  const rustMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.hullRust,
      roughness: 0.86,
      metalness: 0.28,
    })
  );
  const containerMat = own(
    new THREE.MeshStandardMaterial({
      map: textures.hullRust,
      roughness: 0.8,
      metalness: 0.2,
    })
  );
  const plankMat = own(
    new THREE.MeshStandardMaterial({ map: textures.plank, roughness: 0.9 })
  );
  const labWallMat = own(
    new THREE.MeshStandardMaterial({ map: textures.labWall, roughness: 0.85 })
  );

  // -------------------------------------------------------------------------
  // SECTION: generic instanced scattering with rejection sampling
  // -------------------------------------------------------------------------

  function distToWreck(x, z) {
    const dx = x - WRECK_POS.x;
    const dz = z - WRECK_POS.z;
    return Math.sqrt(dx * dx + dz * dz);
  }

  /**
   * Scatter instances of a mesh by rejection sampling.
   * opts:
   *   count           target instance count (mesh capacity)
   *   extent          half extent of the sampling square (default 870)
   *   center          optional { x, z } sampling centre (default origin)
   *   minH / maxH     accepted terrain height range
   *   maxSlope        reject steeper ground
   *   weight(biome, x, z, h) -> acceptance probability 0..1
   *   scale           [min, max] uniform xz scale
   *   scaleY          optional [min, max] independent y scale factor
   *   sink            fraction of scale sunk into the ground
   *   tilt            max random tilt in radians
   *   avoidWreckDist  reject closer than this to the wreck centre
   *   avoid           optional [{ x, z, r }] exclusion discs
   *   palette         optional array of hex colours for instanceColor
   *   collider(x, y, z, s)  optional callback registering a collider
   */
  /**
   * Place `count` instances of `mesh` by rejection sampling.
   *
   * `opts.clump = [min, max, radius]` switches from an even dusting to real
   * colonies: each accepted site seeds a small group. Reefs and kelp stands
   * grow in patches, and an even scatter over a 1800 m square reads as an
   * empty plain no matter how many instances you throw at it.
   */
  function scatterInstances(mesh, opts) {
    const count = opts.count;
    const extent = opts.extent !== undefined ? opts.extent : 870;
    const cx = opts.center ? opts.center.x : 0;
    const cz = opts.center ? opts.center.z : 0;
    const clump = opts.clump || null;
    let placed = 0;
    let guard = count * 30;
    // Instances still owed to the colony currently being grown.
    let clumpLeft = 0;
    let clumpX = 0;
    let clumpZ = 0;
    let clumpR = 0;
    while (placed < count && guard-- > 0) {
      let x;
      let z;
      if (clumpLeft > 0) {
        const a = rng() * TAU;
        const r = Math.sqrt(rng()) * clumpR;
        x = clumpX + Math.cos(a) * r;
        z = clumpZ + Math.sin(a) * r;
        clumpLeft--;
      } else {
        x = cx + (rng() * 2 - 1) * extent;
        z = cz + (rng() * 2 - 1) * extent;
      }
      if (Math.abs(x) > WORLD.halfSize - 12 || Math.abs(z) > WORLD.halfSize - 12) {
        continue;
      }
      const h = heightAt(x, z);
      if (h > opts.maxH || h < opts.minH) continue;
      if (opts.avoidWreckDist && distToWreck(x, z) < opts.avoidWreckDist) continue;
      if (opts.avoid) {
        let bad = false;
        for (let i = 0; i < opts.avoid.length; i++) {
          const a = opts.avoid[i];
          const dx = x - a.x;
          const dz = z - a.z;
          if (dx * dx + dz * dz < a.r * a.r) {
            bad = true;
            break;
          }
        }
        if (bad) continue;
      }
      const biome = biomeAt(x, z);
      const w = opts.weight(biome, x, z, h);
      if (w <= 0 || rng() > w) continue;
      if (slopeAt(x, z) > opts.maxSlope) continue;

      // First accepted site of a colony: decide how big it gets.
      if (clump && clumpLeft <= 0) {
        clumpLeft = Math.floor(lerp(clump[0], clump[1], rng()));
        clumpX = x;
        clumpZ = z;
        clumpR = clump[2];
      }

      const s = lerp(opts.scale[0], opts.scale[1], rng());
      const sy = opts.scaleY ? s * lerp(opts.scaleY[0], opts.scaleY[1], rng()) : s;
      const tilt = opts.tilt || 0;
      _dummy.position.set(x, h - (opts.sink || 0) * s, z);
      _dummy.rotation.set((rng() - 0.5) * tilt, rng() * TAU, (rng() - 0.5) * tilt);
      _dummy.scale.set(s, sy, s);
      _dummy.updateMatrix();
      mesh.setMatrixAt(placed, _dummy.matrix);
      if (opts.palette) {
        _color.setHex(opts.palette[Math.floor(rng() * opts.palette.length)]);
        _color.offsetHSL(0, 0, (rng() - 0.5) * 0.12);
        mesh.setColorAt(placed, _color);
      }
      if (opts.collider) opts.collider(x, h, z, s);
      placed++;
    }
    mesh.count = placed;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.frustumCulled = false;
    group.add(mesh);
    return mesh;
  }

  // -------------------------------------------------------------------------
  // SECTION: boulders and rock outcrops
  // -------------------------------------------------------------------------

  const rockGeoA = makeRockGeometry(noise, 1.5, 3.1, false);
  const rockGeoB = makeRockGeometry(noise, 2.3, 8.7, true);

  const rockPalette = [0xb8b8b8, 0x9aa2a8, 0x8c9096, 0xa8a094];

  scatterInstances(new THREE.InstancedMesh(rockGeoA, rockMat, 2000), {
    count: 2000,
    clump: [3, 12, 11],
    minH: -128,
    maxH: -4,
    maxSlope: 1.3,
    avoidWreckDist: 34,
    weight: (b) =>
      b === BIOMES.ROCKS ? 1 : b === BIOMES.ABYSS ? 0.3 : b === BIOMES.WRECK ? 0.45 : 0.07,
    scale: [1.1, 5.2],
    scaleY: [0.7, 1.25],
    sink: 0.34,
    tilt: 0.6,
    palette: rockPalette,
    collider: (x, h, z, s) => {
      const r = 1.5 * s * 0.85;
      if (r > 1.0) addSphereCollider(x, h + 0.6 * s, z, r);
    },
  });

  scatterInstances(new THREE.InstancedMesh(rockGeoB, rockMat, 1500), {
    count: 1500,
    clump: [3, 10, 13],
    minH: -128,
    maxH: -6,
    maxSlope: 1.3,
    avoidWreckDist: 34,
    weight: (b) =>
      b === BIOMES.ROCKS ? 1 : b === BIOMES.ABYSS ? 0.35 : b === BIOMES.KELP ? 0.18 : 0.06,
    scale: [1.2, 5.8],
    scaleY: [0.55, 1.05],
    sink: 0.4,
    tilt: 0.5,
    palette: rockPalette,
    collider: (x, h, z, s) => {
      const r = 2.3 * s * 0.8;
      if (r > 1.2) addSphereCollider(x, h + 0.5 * s, z, r);
    },
  });

  // Rocks at the island waterline.
  scatterInstances(new THREE.InstancedMesh(rockGeoA, rockMat, 120), {
    count: 120,
    clump: [2, 5, 9],
    center: { x: ISLAND.x, z: ISLAND.z },
    extent: 200,
    minH: -2.2,
    maxH: 1.6,
    maxSlope: 2.5,
    avoid: [
      { x: -18, z: -492, r: 22 }, // keep the dock corridor clear
    ],
    weight: () => 1,
    scale: [0.4, 1.4],
    scaleY: [0.7, 1.0],
    sink: 0.45,
    tilt: 0.7,
    palette: rockPalette,
    collider: (x, h, z, s) => {
      const r = 1.5 * s * 0.85;
      if (r > 0.9) addSphereCollider(x, h + 0.5 * s, z, r);
    },
  });

  // -------------------------------------------------------------------------
  // SECTION: rock arches (memorable swim-through landmarks)
  // -------------------------------------------------------------------------

  {
    const archGeo = makeArchGeometry(noise, 5.5);
    const archMesh = new THREE.InstancedMesh(archGeo, rockMat, ARCH_DATA.length);
    for (let i = 0; i < ARCH_DATA.length; i++) {
      const a = ARCH_DATA[i];
      const ground = heightAt(a.x, a.z);
      const baseY = ground - 2.2 * a.scale;
      _dummy.position.set(a.x, baseY, a.z);
      _dummy.rotation.set(0, a.yaw, (rng() - 0.5) * 0.12);
      _dummy.scale.set(a.scale, a.scale * (0.95 + rng() * 0.25), a.scale);
      _dummy.updateMatrix();
      archMesh.setMatrixAt(i, _dummy.matrix);
      _color.setHex(0xa8a8a8);
      archMesh.setColorAt(i, _color);
      // Colliders: a chain of spheres along the half torus ring.
      const cosY = Math.cos(a.yaw);
      const sinY = Math.sin(a.yaw);
      for (let k = 0; k <= 8; k++) {
        const ang = (k / 8) * Math.PI;
        const lx = Math.cos(ang) * 10 * a.scale;
        const ly = Math.sin(ang) * 10 * a.scale;
        addSphereCollider(
          a.x + lx * cosY,
          baseY + ly,
          a.z - lx * sinY,
          3.1 * a.scale
        );
      }
    }
    archMesh.instanceMatrix.needsUpdate = true;
    if (archMesh.instanceColor) archMesh.instanceColor.needsUpdate = true;
    archMesh.frustumCulled = false;
    group.add(archMesh);
  }

  // -------------------------------------------------------------------------
  // SECTION: corals, sea fans, anemones
  // -------------------------------------------------------------------------

  const coralPalette = [
    PALETTE.coralPink,
    PALETTE.coralOrange,
    PALETTE.coralPurple,
    0x4de0c8,
    0xffe08a,
  ];

  const coralWeight = (b) =>
    b === BIOMES.LAGOON ? 1 : b === BIOMES.KELP ? 0.18 : 0;

  scatterInstances(
    new THREE.InstancedMesh(makeBrainCoralGeometry(noise, 2.4), brainMat, 1500),
    {
      count: 1500,
      clump: [4, 11, 7.5],
      minH: -46,
      maxH: -7,
      maxSlope: 0.6,
      weight: coralWeight,
      scale: [0.5, 2.2],
      scaleY: [0.8, 1.1],
      sink: 0.12,
      tilt: 0.25,
      palette: coralPalette,
      collider: (x, h, z, s) => {
        if (s > 1.5) addSphereCollider(x, h + 0.3 * s, z, 0.6 * s);
      },
    }
  );

  scatterInstances(
    new THREE.InstancedMesh(makeBranchCoralGeometry(rng), branchMat, 1200),
    {
      count: 1200,
      clump: [4, 10, 6.5],
      minH: -44,
      maxH: -7,
      maxSlope: 0.55,
      weight: coralWeight,
      scale: [0.8, 2.6],
      scaleY: [0.9, 1.2],
      sink: 0.02,
      tilt: 0.2,
      palette: coralPalette,
    }
  );

  scatterInstances(
    new THREE.InstancedMesh(makeTableCoralGeometry(noise, 7.7), tableMat, 700),
    {
      count: 700,
      clump: [2, 6, 8],
      minH: -44,
      maxH: -8,
      maxSlope: 0.5,
      weight: coralWeight,
      scale: [0.7, 2.0],
      scaleY: [0.85, 1.1],
      sink: 0.03,
      tilt: 0.18,
      palette: coralPalette,
    }
  );

  scatterInstances(new THREE.InstancedMesh(makeSeaFanGeometry(), fanMat, 1600), {
    count: 1600,
    clump: [3, 8, 6],
    minH: -84,
    maxH: -9,
    maxSlope: 1.1,
    weight: (b) =>
      b === BIOMES.LAGOON ? 0.9 : b === BIOMES.KELP ? 0.5 : b === BIOMES.ROCKS ? 0.9 : b === BIOMES.WRECK ? 0.5 : 0,
    scale: [0.7, 2.2],
    scaleY: [0.9, 1.3],
    sink: 0.02,
    tilt: 0.2,
    palette: [PALETTE.coralPurple, PALETTE.coralPink, 0xd66bb8, 0x8a5adf],
  });

  scatterInstances(
    new THREE.InstancedMesh(makeAnemoneGeometry(rng), anemoneMat, 520),
    {
      count: 520,
      clump: [3, 9, 4.5],
      minH: -34,
      maxH: -7,
      maxSlope: 0.5,
      weight: (b) => (b === BIOMES.LAGOON ? 1 : 0),
      scale: [0.8, 2.0],
      scaleY: [0.9, 1.2],
      sink: 0.02,
      tilt: 0.15,
      palette: [0xff9fb8, 0xffc27a, 0xb9f0d8, 0xe8a0ff],
    }
  );

  // -------------------------------------------------------------------------
  // SECTION: kelp forest and lagoon seagrass (GPU sway)
  // -------------------------------------------------------------------------

  scatterInstances(new THREE.InstancedMesh(makeKelpGeometry(), kelpMat, 3600), {
    count: 3600,
    clump: [8, 22, 9],
    minH: -52,
    maxH: -18,
    maxSlope: 0.55,
    weight: (b) => (b === BIOMES.KELP ? 1 : 0),
    scale: [0.75, 1.25],
    scaleY: [0.7, 1.6],
    sink: 0.0,
    tilt: 0.1,
  });

  scatterInstances(
    new THREE.InstancedMesh(makeSeagrassGeometry(), seagrassMat, 4200),
    {
      count: 4200,
      clump: [10, 26, 7],
      minH: -26,
      maxH: -6,
      maxSlope: 0.5,
      weight: (b) => (b === BIOMES.LAGOON ? 1 : 0),
      scale: [0.7, 1.5],
      scaleY: [0.7, 1.5],
      sink: 0.0,
      tilt: 0.12,
    }
  );

  // Brown seaweed: everywhere the kelp forest is not, so no stretch of rock or
  // sand is completely bare.
  scatterInstances(new THREE.InstancedMesh(makeKelpGeometry(), seaweedMat, 2600), {
    count: 2600,
    clump: [6, 18, 8],
    minH: -78,
    maxH: -5,
    maxSlope: 0.95,
    weight: (b) =>
      b === BIOMES.LAGOON ? 0.7 : b === BIOMES.KELP ? 0.45 : b === BIOMES.ROCKS ? 1 : b === BIOMES.WRECK ? 0.8 : 0.15,
    scale: [0.5, 1.1],
    scaleY: [0.3, 0.7],
    sink: 0.0,
    tilt: 0.22,
    palette: [0xb8935a, 0x8f7a3f, 0x6f6a35, 0xa87c4a, 0x7d5f3a],
  });

  // Red algae on the rocky slopes, including the steep faces the rest of the
  // flora refuses.
  scatterInstances(new THREE.InstancedMesh(makeTuftGeometry(), redAlgaeMat, 2200), {
    count: 2200,
    clump: [8, 22, 5],
    minH: -96,
    maxH: -6,
    maxSlope: 1.6,
    weight: (b) =>
      b === BIOMES.ROCKS ? 1 : b === BIOMES.WRECK ? 0.7 : b === BIOMES.KELP ? 0.4 : b === BIOMES.ABYSS ? 0.25 : 0.3,
    scale: [0.6, 1.6],
    scaleY: [0.6, 1.4],
    sink: 0.05,
    tilt: 0.5,
    palette: [0xb03a5a, 0x8c2f52, 0xc2506a, 0x7a2f46, 0xd06a7a],
  });

  // -------------------------------------------------------------------------
  // SECTION: bioluminescent polyps in the abyss
  // -------------------------------------------------------------------------

  scatterInstances(new THREE.InstancedMesh(makePolypGeometry(rng), polypMat, 700), {
    count: 700,
    clump: [4, 12, 6],
    minH: -131,
    maxH: -68,
    maxSlope: 1.4,
    weight: (b) => (b === BIOMES.ABYSS ? 1 : b === BIOMES.WRECK ? 0.25 : 0),
    scale: [0.8, 2.4],
    scaleY: [0.9, 1.4],
    sink: 0.02,
    tilt: 0.25,
  });

  // -------------------------------------------------------------------------
  // SECTION: the wreck of the Meroe
  //
  // A cargo ship broken in two on the basin floor. The stern section holds a
  // swim-through hold: enter through the deck opening or the starboard gash.
  // -------------------------------------------------------------------------

  const wreckGroup = new THREE.Group();
  wreckGroup.name = 'wreck';
  const wreckBaseY = heightAt(WRECK_POS.x, WRECK_POS.z) + 0.4;
  wreckGroup.position.set(WRECK_POS.x, wreckBaseY, WRECK_POS.z);
  wreckGroup.rotation.y = WRECK_POS.yaw;
  wreckGroup.rotation.z = 0.06;
  group.add(wreckGroup);

  // Local -> world for colliders (yaw + translation only, roll is cosmetic).
  const wCos = Math.cos(WRECK_POS.yaw);
  const wSin = Math.sin(WRECK_POS.yaw);
  function wreckSphere(lx, ly, lz, r) {
    addSphereCollider(
      WRECK_POS.x + lx * wCos + lz * wSin,
      wreckBaseY + ly,
      WRECK_POS.z - lx * wSin + lz * wCos,
      r
    );
  }
  function wreckCapsule(ax, ay, az, bx, by, bz, r) {
    addCapsuleCollider(
      WRECK_POS.x + ax * wCos + az * wSin,
      wreckBaseY + ay,
      WRECK_POS.z - ax * wSin + az * wCos,
      WRECK_POS.x + bx * wCos + bz * wSin,
      wreckBaseY + by,
      WRECK_POS.z - bx * wSin + bz * wCos,
      r
    );
  }

  function addWreckBox(parent, w, h, d, x, y, z, rx, ry, rz, mat) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat || rustMat);
    mesh.position.set(x, y, z);
    mesh.rotation.set(rx || 0, ry || 0, rz || 0);
    parent.add(mesh);
    return mesh;
  }

  {
    // Stern section, local z from -22 (stern) to +22 (broken end).
    addWreckBox(wreckGroup, 14, 1.4, 44, 0, 0.9, 0);            // hull floor
    addWreckBox(wreckGroup, 1.2, 9, 44, -6.4, 5.2, 0);          // port wall
    addWreckBox(wreckGroup, 1.2, 9, 18, 6.4, 5.2, -13);         // starboard aft
    addWreckBox(wreckGroup, 1.2, 9, 14, 6.4, 5.2, 15);          // starboard fwd
    addWreckBox(wreckGroup, 14, 9, 1.4, 0, 5.2, -21.6);         // transom
    addWreckBox(wreckGroup, 14, 0.8, 16, 0, 9.6, -14);          // aft deck
    addWreckBox(wreckGroup, 14, 0.8, 16, 0, 9.6, 14);           // fwd deck
    // Hold opening between z -6 and +6 on deck, gash z -4..8 starboard.

    // Bridge superstructure at the stern.
    addWreckBox(wreckGroup, 10, 3.4, 7, 0, 11.7, -16.5);
    addWreckBox(wreckGroup, 7, 2.6, 5, 0, 14.6, -17.2);
    const winMat = own(
      new THREE.MeshStandardMaterial({
        color: 0x0c1a20,
        roughness: 0.4,
        metalness: 0.5,
      })
    );
    addWreckBox(wreckGroup, 6.4, 0.9, 0.2, 0, 15.0, -14.6, 0, 0, 0, winMat);

    // Funnel, leaning.
    const funnel = new THREE.Mesh(
      new THREE.CylinderGeometry(1.5, 1.9, 7, 10),
      rustMat
    );
    funnel.position.set(0.6, 13.2, -10.5);
    funnel.rotation.z = 0.28;
    wreckGroup.add(funnel);

    // Masts: one standing, one fallen across the deck.
    const mast1 = new THREE.Mesh(
      new THREE.CylinderGeometry(0.16, 0.3, 13, 6),
      rustMat
    );
    mast1.position.set(0, 15.8, 18);
    mast1.rotation.x = 0.18;
    wreckGroup.add(mast1);
    const mast2 = new THREE.Mesh(
      new THREE.CylinderGeometry(0.14, 0.26, 11, 6),
      rustMat
    );
    mast2.position.set(3.5, 10.4, 6);
    mast2.rotation.set(0.2, 0, 1.35);
    wreckGroup.add(mast2);

    // Broken propeller at the stern, half buried.
    const prop = new THREE.Group();
    prop.position.set(0, 2.4, -24.5);
    prop.rotation.set(0.3, 0, 0.5);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.9, 8), rustMat);
    hub.rotation.x = Math.PI / 2;
    prop.add(hub);
    for (let i = 0; i < 4; i++) {
      const blade = new THREE.Mesh(new THREE.BoxGeometry(0.7, 2.6, 0.16), rustMat);
      blade.position.set(
        Math.cos((i / 4) * TAU) * 1.5,
        Math.sin((i / 4) * TAU) * 1.5,
        0
      );
      blade.rotation.z = (i / 4) * TAU + 0.5;
      blade.rotation.y = 0.5;
      prop.add(blade);
    }
    wreckGroup.add(prop);

    // Bow section, snapped off, tilted, a few metres ahead.
    const bowGroup = new THREE.Group();
    bowGroup.position.set(6, 1.6, 34);
    bowGroup.rotation.set(0.12, 0.5, 0.55);
    const bowGeo = new THREE.BoxGeometry(12, 8, 20, 1, 1, 5);
    {
      const p = bowGeo.attributes.position;
      for (let i = 0; i < p.count; i++) {
        const t = clamp01((p.getZ(i) + 10) / 20);
        p.setX(i, p.getX(i) * (1 - 0.85 * t * t));
        p.setY(i, p.getY(i) * (1 - 0.25 * t * t));
      }
      bowGeo.computeVertexNormals();
    }
    bowGroup.add(new THREE.Mesh(bowGeo, rustMat));
    // Small forecastle block on the bow deck.
    addWreckBox(bowGroup, 4, 1.6, 4, 0, 4.6, -4);
    wreckGroup.add(bowGroup);

    // Cargo containers scattered around the hull.
    const containerGeo = new THREE.BoxGeometry(6.1, 2.6, 2.44);
    const containers = new THREE.InstancedMesh(containerGeo, containerMat, 10);
    const containerTints = [0x9a4030, 0x3a6a52, 0x51586b, 0x8a7440, 0x6b3a56];
    const containerSpots = [
      { x: -14, z: 8, yaw: 0.4, tilt: 0.14 },
      { x: -12, z: -12, yaw: 1.9, tilt: 0.08 },
      { x: 14, z: -4, yaw: 0.9, tilt: 0.2 },
      { x: 17, z: 12, yaw: 2.6, tilt: 0.1 },
      { x: -8, z: 28, yaw: 1.2, tilt: 0.24 },
      { x: 12, z: 26, yaw: 0.2, tilt: 0.12 },
      { x: -20, z: 22, yaw: 2.1, tilt: 0.16 },
      { x: 2, z: 44, yaw: 1.5, tilt: 0.3 },
      { x: -4, z: 12.5, yaw: 0.15, tilt: 0.05 }, // inside the hold
      { x: 22, z: -16, yaw: 2.9, tilt: 0.18 },
    ];
    for (let i = 0; i < containerSpots.length; i++) {
      const c = containerSpots[i];
      // Positions are local to the wreck group; ground follows the bowl.
      _dummy.position.set(c.x, 2.0, c.z);
      _dummy.rotation.set((rng() - 0.5) * c.tilt * 2, c.yaw, c.tilt);
      _dummy.scale.set(1, 1, 1);
      _dummy.updateMatrix();
      containers.setMatrixAt(i, _dummy.matrix);
      _color.setHex(containerTints[i % containerTints.length]);
      containers.setColorAt(i, _color);
      wreckSphere(c.x, 1.8, c.z, 2.3);
    }
    containers.instanceMatrix.needsUpdate = true;
    if (containers.instanceColor) containers.instanceColor.needsUpdate = true;
    containers.frustumCulled = false;
    wreckGroup.add(containers);

    // Colliders for the hull shell (openings stay clear on purpose).
    wreckCapsule(-6.4, 2.6, -19.5, -6.4, 2.6, 19.5, 2.3); // port wall low
    wreckCapsule(-6.4, 7.0, -19.5, -6.4, 7.0, 19.5, 2.3); // port wall high
    wreckCapsule(6.4, 2.6, -19.8, 6.4, 2.6, -6.2, 2.3);   // starboard aft low
    wreckCapsule(6.4, 7.0, -19.8, 6.4, 7.0, -6.2, 2.3);   // starboard aft high
    wreckCapsule(6.4, 2.6, 10.2, 6.4, 2.6, 19.8, 2.3);    // starboard fwd low
    wreckCapsule(6.4, 7.0, 10.2, 6.4, 7.0, 19.8, 2.3);    // starboard fwd high
    wreckCapsule(-3.0, 0.5, -19.5, -3.0, 0.5, 19.5, 1.5); // hold floor port
    wreckCapsule(3.0, 0.5, -19.5, 3.0, 0.5, 19.5, 1.5);   // hold floor stbd
    wreckCapsule(-3.5, 9.6, -19.5, -3.5, 9.6, -7.5, 1.7); // aft deck
    wreckCapsule(3.5, 9.6, -19.5, 3.5, 9.6, -7.5, 1.7);
    wreckCapsule(-3.5, 9.6, 7.5, -3.5, 9.6, 19.5, 1.7);   // fwd deck
    wreckCapsule(3.5, 9.6, 7.5, 3.5, 9.6, 19.5, 1.7);
    wreckSphere(0, 4.5, -22.5, 6.0);                      // transom
    wreckSphere(0, 12.5, -16.5, 5.6);                     // bridge
    wreckCapsule(0.6, 10, -10.5, 2.4, 16.4, -10.5, 1.9);  // funnel
    wreckSphere(0, 2.4, -24.5, 2.5);                      // propeller
    wreckSphere(4, 2.5, 27, 4.6);                         // bow section
    wreckSphere(7, 2.5, 34, 4.2);
    wreckSphere(10, 2.0, 40, 3.2);
  }

  // -------------------------------------------------------------------------
  // SECTION: the island - beach, palms, scrub
  // -------------------------------------------------------------------------

  const islandAvoid = [
    { x: WORLD.lab.x, z: WORLD.lab.z, r: 9 },
    { x: WORLD.scientist.x, z: WORLD.scientist.z, r: 6 },
    { x: -18, z: -492, r: 16 },
  ];

  // Grass and scrub tufts on the island slopes.
  scatterInstances(new THREE.InstancedMesh(makeTuftGeometry(), foliageMat, 1400), {
    count: 1400,
    clump: [5, 16, 8],
    center: { x: ISLAND.x, z: ISLAND.z },
    extent: 170,
    minH: 1.6,
    maxH: 30,
    maxSlope: 0.85,
    avoid: islandAvoid,
    weight: () => 1,
    scale: [0.7, 2.6],
    scaleY: [0.8, 1.6],
    sink: 0.02,
    tilt: 0.2,
  });

  // Palms: instanced trunks, then fronds fanned out at each computed top.
  {
    const PALM_COUNT = 34;
    const trunkGeo = makePalmTrunkGeometry();
    const frondGeo = makePalmFrondGeometry();
    const trunks = new THREE.InstancedMesh(trunkGeo, trunkMat, PALM_COUNT);
    const FRONDS_PER_PALM = 7;
    const fronds = new THREE.InstancedMesh(
      frondGeo,
      frondMat,
      PALM_COUNT * FRONDS_PER_PALM
    );
    let placedPalms = 0;
    let frondIdx = 0;
    let guard = 400;
    while (placedPalms < PALM_COUNT && guard-- > 0) {
      const x = ISLAND.x + (rng() * 2 - 1) * 150;
      const z = ISLAND.z + (rng() * 2 - 1) * 150;
      const h = heightAt(x, z);
      if (h < 1.8 || h > 14) continue;
      if (slopeAt(x, z) > 0.5) continue;
      let bad = false;
      for (const a of islandAvoid) {
        const dx = x - a.x;
        const dz = z - a.z;
        if (dx * dx + dz * dz < (a.r + 4) * (a.r + 4)) {
          bad = true;
          break;
        }
      }
      if (bad) continue;
      const s = 0.85 + rng() * 0.45;
      const yaw = rng() * TAU;
      _dummy.position.set(x, h - 0.15, z);
      _dummy.rotation.set((rng() - 0.5) * 0.12, yaw, (rng() - 0.5) * 0.12);
      _dummy.scale.set(s, s, s);
      _dummy.updateMatrix();
      trunks.setMatrixAt(placedPalms, _dummy.matrix);
      // Trunk collider.
      addCapsuleCollider(x, h, z, x + Math.cos(yaw) * 1.1 * s, h + 6.2 * s, z - Math.sin(yaw) * 1.1 * s, 0.35 * s);
      // Compute the world position of the bent trunk top.
      _v1.set(1.1, 6.2, 0).applyMatrix4(_dummy.matrix);
      for (let f = 0; f < FRONDS_PER_PALM; f++) {
        const fy = (f / FRONDS_PER_PALM) * TAU + rng() * 0.5;
        const droop = 0.35 + rng() * 0.5;
        _q1.setFromAxisAngle(UP, fy);
        _q2.setFromAxisAngle(_v3.set(0, 0, 1), -droop);
        _q1.multiply(_q2);
        const fs = s * (0.85 + rng() * 0.3);
        _m1.compose(_v1, _q1, _v2.set(fs, fs, fs));
        fronds.setMatrixAt(frondIdx++, _m1);
      }
      placedPalms++;
    }
    trunks.count = placedPalms;
    fronds.count = frondIdx;
    trunks.instanceMatrix.needsUpdate = true;
    fronds.instanceMatrix.needsUpdate = true;
    trunks.frustumCulled = false;
    fronds.frustumCulled = false;
    group.add(trunks);
    group.add(fronds);
  }

  // -------------------------------------------------------------------------
  // SECTION: the wooden dock
  //
  // Runs from the beach at (-18, -503) out to (-18, -489.5). The submarine
  // berths just off the end at WORLD.subDock; the flatten spot keeps the
  // water pocket 3.6 m deep there.
  // -------------------------------------------------------------------------

  {
    const dock = new THREE.Group();
    dock.name = 'dock';
    const DX = -18;
    const Z0 = -503;
    const Z1 = -489.5;
    const DECK_TOP = 1.26;
    const WIDTH = 3.4;

    // Deck planks.
    const plankCount = 8;
    const span = Z1 - Z0;
    for (let i = 0; i < plankCount; i++) {
      const z = Z0 + (i + 0.5) * (span / plankCount);
      const plank = new THREE.Mesh(
        new THREE.BoxGeometry(WIDTH, 0.1, span / plankCount - 0.12),
        plankMat
      );
      plank.position.set(DX, DECK_TOP - 0.05, z);
      dock.add(plank);
    }
    // Stringers under the planks.
    for (const sx of [-1.35, 1.35]) {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.24, span), plankMat);
      beam.position.set(DX + sx, DECK_TOP - 0.24, Z0 + span / 2);
      dock.add(beam);
    }
    // Pilings, instanced, each scaled to reach the seabed.
    const pileGeo = new THREE.CylinderGeometry(0.16, 0.18, 1, 7);
    pileGeo.translate(0, -0.5, 0); // unit height hanging below origin
    const pileZs = [Z0 + 0.8, -498.5, -494, Z1 - 0.4];
    const piles = new THREE.InstancedMesh(pileGeo, plankMat, pileZs.length * 2);
    let pi = 0;
    for (const pz of pileZs) {
      for (const sx of [-1.55, 1.55]) {
        const px = DX + sx;
        const bottom = heightAt(px, pz) - 0.8;
        const len = DECK_TOP + 0.15 - bottom;
        _dummy.position.set(px, DECK_TOP + 0.15, pz);
        _dummy.rotation.set(0, 0, 0);
        _dummy.scale.set(1, len, 1);
        _dummy.updateMatrix();
        piles.setMatrixAt(pi++, _dummy.matrix);
        addCapsuleCollider(px, bottom, pz, px, DECK_TOP + 0.1, pz, 0.28);
      }
    }
    piles.instanceMatrix.needsUpdate = true;
    piles.frustumCulled = false;
    dock.add(piles);
    // Deck underside collider so the swimming diver bumps the pier.
    addCapsuleCollider(DX, DECK_TOP - 0.35, Z0 + 1, DX, DECK_TOP - 0.35, Z1 - 0.5, 1.5);
    group.add(dock);
  }

  // -------------------------------------------------------------------------
  // SECTION: the field laboratory
  // -------------------------------------------------------------------------

  const labMesh = new THREE.Group();
  labMesh.name = 'lab';
  {
    const lg = heightAt(WORLD.lab.x, WORLD.lab.z);
    labMesh.position.set(WORLD.lab.x, lg, WORLD.lab.z);
    // Door faces the scientist / dock side.
    labMesh.rotation.y = Math.atan2(
      WORLD.scientist.x - WORLD.lab.x,
      WORLD.scientist.z - WORLD.lab.z
    );

    // Hut body.
    const hut = new THREE.Mesh(new THREE.BoxGeometry(5, 2.9, 4), labWallMat);
    hut.position.set(0, 1.45, 0);
    labMesh.add(hut);
    // Sloped roof slab.
    const roofMat = own(
      new THREE.MeshStandardMaterial({ color: 0x7a4a38, roughness: 0.9 })
    );
    const roof = new THREE.Mesh(new THREE.BoxGeometry(5.9, 0.16, 4.9), roofMat);
    roof.position.set(0, 3.18, 0);
    roof.rotation.z = 0.15;
    labMesh.add(roof);
    // Door and window.
    const darkMat = own(
      new THREE.MeshStandardMaterial({ color: 0x2a2f36, roughness: 0.8 })
    );
    const door = new THREE.Mesh(new THREE.BoxGeometry(0.95, 1.95, 0.08), darkMat);
    door.position.set(0.9, 0.98, 2.02);
    labMesh.add(door);
    const glassMat = own(
      new THREE.MeshStandardMaterial({
        color: PALETTE.glass,
        roughness: 0.15,
        metalness: 0.4,
      })
    );
    const window1 = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.85, 0.08), glassMat);
    window1.position.set(-1.2, 1.7, 2.02);
    labMesh.add(window1);
    const frame = new THREE.Mesh(new THREE.BoxGeometry(1.35, 1.05, 0.06), darkMat);
    frame.position.set(-1.2, 1.7, 1.99);
    labMesh.add(frame);
    // Radio antenna on a corner.
    const antenna = new THREE.Mesh(
      new THREE.CylinderGeometry(0.025, 0.045, 4.4, 5),
      darkMat
    );
    antenna.position.set(2.2, 4.8, -1.7);
    labMesh.add(antenna);
    for (let i = 0; i < 3; i++) {
      const bar = new THREE.Mesh(new THREE.BoxGeometry(0.5 - i * 0.12, 0.03, 0.03), darkMat);
      bar.position.set(2.2, 5.6 + i * 0.5, -1.7);
      labMesh.add(bar);
    }
    // Crates.
    const crateGeo = new THREE.BoxGeometry(0.8, 0.8, 0.8);
    const crates = new THREE.InstancedMesh(crateGeo, plankMat, 6);
    const crateSpots = [
      { x: 3.1, z: 1.2, s: 1.0 },
      { x: 3.4, z: 0.2, s: 0.8 },
      { x: 3.2, z: 0.75, s: 0.7, y: 0.82 },
      { x: -3.0, z: 1.6, s: 0.9 },
      { x: -3.2, z: -0.4, s: 1.1 },
      { x: 2.6, z: -2.6, s: 0.85 },
    ];
    for (let i = 0; i < crateSpots.length; i++) {
      const c = crateSpots[i];
      _dummy.position.set(c.x, (c.y || 0) + 0.4 * c.s, c.z);
      _dummy.rotation.set(0, rng() * TAU, 0);
      _dummy.scale.set(c.s, c.s, c.s);
      _dummy.updateMatrix();
      crates.setMatrixAt(i, _dummy.matrix);
    }
    crates.instanceMatrix.needsUpdate = true;
    crates.frustumCulled = false;
    labMesh.add(crates);
    // Folding table with field equipment.
    const table = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.06, 0.8), plankMat);
    table.position.set(-1.4, 0.85, 3.1);
    labMesh.add(table);
    for (const [lx, lz] of [[-0.75, -0.3], [0.75, -0.3], [-0.75, 0.3], [0.75, 0.3]]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.82, 5), darkMat);
      leg.position.set(-1.4 + lx, 0.41, 3.1 + lz);
      labMesh.add(leg);
    }
    const gear1 = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.22, 0.22), darkMat);
    gear1.position.set(-1.8, 0.99, 3.1);
    labMesh.add(gear1);
    const flaskMat = own(
      new THREE.MeshStandardMaterial({
        color: 0x9fe8ff,
        emissive: 0x1f5a6a,
        emissiveIntensity: 0.6,
        roughness: 0.2,
      })
    );
    const flask = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.08, 0.24, 7), flaskMat);
    flask.position.set(-1.1, 1.0, 3.0);
    labMesh.add(flask);
    const gear2 = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.08, 0.3), darkMat);
    gear2.position.set(-1.35, 0.92, 3.25);
    labMesh.add(gear2);

    group.add(labMesh);

    // Colliders: hut body plus the crate stack corners.
    addSphereCollider(WORLD.lab.x, lg + 1.5, WORLD.lab.z, 3.3);
    addSphereCollider(WORLD.lab.x + 2.6, lg + 0.5, WORLD.lab.z + 1.4, 1.0);
  }

  // -------------------------------------------------------------------------
  // SECTION: the scientist (low poly, gentle idle, faces the dock)
  // -------------------------------------------------------------------------

  const scientistMesh = new THREE.Group();
  scientistMesh.name = 'scientist';
  const scientistInner = new THREE.Group();
  let scientistHead = null;
  {
    const sg = heightAt(WORLD.scientist.x, WORLD.scientist.z);
    scientistMesh.position.set(WORLD.scientist.x, sg, WORLD.scientist.z);
    scientistMesh.rotation.y = Math.atan2(
      WORLD.dockLanding.x - WORLD.scientist.x,
      WORLD.dockLanding.z - WORLD.scientist.z
    );
    scientistMesh.add(scientistInner);

    const coatMat = own(
      new THREE.MeshStandardMaterial({ color: 0xe9eef0, roughness: 0.85 })
    );
    const skinMat = own(
      new THREE.MeshStandardMaterial({ color: 0xd9a679, roughness: 0.7 })
    );
    const pantsMat = own(
      new THREE.MeshStandardMaterial({ color: 0x2a3d55, roughness: 0.9 })
    );
    const hairMat = own(
      new THREE.MeshStandardMaterial({ color: 0x4a4038, roughness: 0.95 })
    );
    const boardMat = own(
      new THREE.MeshStandardMaterial({ color: 0xcfa96a, roughness: 0.8 })
    );

    // Legs.
    for (const sx of [-0.1, 0.1]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.08, 0.62, 6), pantsMat);
      leg.position.set(sx, 0.31, 0);
      scientistInner.add(leg);
      const foot = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.07, 0.24), hairMat);
      foot.position.set(sx, 0.04, 0.05);
      scientistInner.add(foot);
    }
    // Lab coat body.
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.24, 0.52, 4, 10), coatMat);
    body.position.set(0, 0.98, 0);
    scientistInner.add(body);
    // Arms: right holds the clipboard, left hangs.
    const armL = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.4, 3, 7), coatMat);
    armL.position.set(-0.3, 1.06, 0.02);
    armL.rotation.z = 0.25;
    scientistInner.add(armL);
    const armR = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.36, 3, 7), coatMat);
    armR.position.set(0.26, 1.12, 0.16);
    armR.rotation.set(-1.15, 0, -0.5);
    scientistInner.add(armR);
    const handR = new THREE.Mesh(new THREE.SphereGeometry(0.06, 6, 5), skinMat);
    handR.position.set(0.14, 1.16, 0.3);
    scientistInner.add(handR);
    // Clipboard.
    const board = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.32, 0.02), boardMat);
    board.position.set(0.05, 1.18, 0.32);
    board.rotation.x = -0.5;
    scientistInner.add(board);
    const sheet = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.26, 0.01), coatMat);
    sheet.position.set(0.05, 1.19, 0.335);
    sheet.rotation.x = -0.5;
    scientistInner.add(sheet);
    // Head with hair.
    scientistHead = new THREE.Group();
    scientistHead.position.set(0, 1.5, 0);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.135, 10, 8), skinMat);
    head.position.set(0, 0.02, 0);
    scientistHead.add(head);
    const hair = new THREE.Mesh(new THREE.SphereGeometry(0.135, 10, 6), hairMat);
    hair.scale.set(1.04, 0.7, 1.04);
    hair.position.set(0, 0.08, -0.02);
    scientistHead.add(hair);
    scientistInner.add(scientistHead);

    group.add(scientistMesh);
    addCapsuleCollider(
      WORLD.scientist.x,
      sg,
      WORLD.scientist.z,
      WORLD.scientist.x,
      sg + 1.5,
      WORLD.scientist.z,
      0.45
    );
  }

  // -------------------------------------------------------------------------
  // SECTION: named points exposed to the integrator
  // -------------------------------------------------------------------------

  const points = {
    subAnchor: new THREE.Vector3(WORLD.subAnchor.x, WORLD.subAnchor.y, WORLD.subAnchor.z),
    subDock: new THREE.Vector3(WORLD.subDock.x, WORLD.subDock.y, WORLD.subDock.z),
    dockLanding: new THREE.Vector3(
      WORLD.dockLanding.x,
      heightAt(WORLD.dockLanding.x, WORLD.dockLanding.z),
      WORLD.dockLanding.z
    ),
    scientist: new THREE.Vector3(
      WORLD.scientist.x,
      heightAt(WORLD.scientist.x, WORLD.scientist.z),
      WORLD.scientist.z
    ),
    lab: new THREE.Vector3(
      WORLD.lab.x,
      heightAt(WORLD.lab.x, WORLD.lab.z),
      WORLD.lab.z
    ),
  };

  // -------------------------------------------------------------------------
  // SECTION: fauna spawn points
  // -------------------------------------------------------------------------

  // Sampling rings around the island per biome (distance range), so the
  // rejection loop converges fast. Every candidate is still validated with
  // biomeAt before being accepted.
  const SPAWN_RINGS = {
    [BIOMES.LAGOON]: [230, 520],
    [BIOMES.KELP]: [500, 780],
    [BIOMES.ROCKS]: [730, 1090],
    [BIOMES.ABYSS]: [1150, 1650],
  };
  const SPAWN_FALLBACK = {
    [BIOMES.LAGOON]: { x: 0, z: -300, y: -12 },
    [BIOMES.KELP]: { x: 0, z: 20, y: -28 },
    [BIOMES.ROCKS]: { x: -280, z: 290, y: -48 },
    [BIOMES.WRECK]: { x: WRECK_POS.x, z: WRECK_POS.z, y: -56 },
    [BIOMES.ABYSS]: { x: 0, z: 820, y: -95 },
  };

  function randomSpawn(biomeId, spawnRng) {
    const info = BIOME_INFO[biomeId];
    const dMin = info.depth[0];
    const dMax = info.depth[1];
    for (let tries = 0; tries < 60; tries++) {
      let x;
      let z;
      if (biomeId === BIOMES.WRECK) {
        const ang = spawnRng() * TAU;
        const d = 25 + spawnRng() * 90;
        x = WRECK_POS.x + Math.cos(ang) * d;
        z = WRECK_POS.z + Math.sin(ang) * d;
      } else {
        const ring = SPAWN_RINGS[biomeId];
        const ang = spawnRng() * TAU;
        const d = lerp(ring[0], ring[1], Math.sqrt(spawnRng()));
        x = ISLAND.x + Math.cos(ang) * d;
        z = ISLAND.z + Math.sin(ang) * d;
      }
      if (Math.abs(x) > WORLD.boundsRadius - 20 || Math.abs(z) > WORLD.boundsRadius - 20) {
        continue;
      }
      if (biomeAt(x, z) !== biomeId) continue;
      const h = heightAt(x, z);
      if (h > -6) continue;
      const yMin = Math.max(-dMax, h + 2);
      const yMax = Math.min(-dMin, -3);
      if (yMin > yMax) continue;
      // Prefer open water a couple of metres above the seabed.
      const y = clamp(h + 2 + spawnRng() * 7, yMin, yMax);
      return new THREE.Vector3(x, y, z);
    }
    const f = SPAWN_FALLBACK[biomeId] || SPAWN_FALLBACK[BIOMES.LAGOON];
    return new THREE.Vector3(f.x, f.y, f.z);
  }

  // -------------------------------------------------------------------------
  // SECTION: per frame update (cheap: uniforms plus two tiny animations)
  // -------------------------------------------------------------------------

  function update(dt, ctx) {
    localTime += dt;
    const t = ctx && typeof ctx.time === 'number' ? ctx.time : localTime;
    timeUniform.value = t;

    // Scientist idle: slight bob, small sway, slow head turns.
    scientistInner.position.y = Math.sin(t * 1.15) * 0.02;
    scientistInner.rotation.z = Math.sin(t * 0.6) * 0.016;
    scientistInner.rotation.x = Math.sin(t * 0.83) * 0.01;
    if (scientistHead) {
      scientistHead.rotation.y = Math.sin(t * 0.37) * 0.2;
      scientistHead.rotation.x = 0.1 + Math.sin(t * 1.15) * 0.03;
    }

    // Abyssal polyps breathe softly.
    polypMat.emissiveIntensity = 1.3 + Math.sin(t * 1.7) * 0.45;
  }

  // -------------------------------------------------------------------------
  // SECTION: dispose
  // -------------------------------------------------------------------------

  function dispose() {
    scene.remove(group);
    group.traverse((obj) => {
      if (obj.isMesh && obj.geometry) obj.geometry.dispose();
    });
    for (const m of ownedMaterials) m.dispose();
    ownedMaterials.length = 0;
    grid.clear();
  }

  // -------------------------------------------------------------------------
  // Public World object (see docs/CONTRACTS.md)
  // -------------------------------------------------------------------------

  return {
    group,
    update,
    dispose,
    heightAt,
    biomeAt,
    isLand,
    collide,
    points,
    scientistMesh,
    labMesh,
    randomSpawn,
  };
}
