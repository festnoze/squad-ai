// Geantes gazeuses : coque externe + 3 coques internes traversables + anneau.
//
// Assets couverts : A05 (coques), A06 (anneau), S05 (shader de bandes),
// T09 (DataTexture 64x512 du profil latitudinal des bandes).
//
// Tout vit en ESPACE LOCAL PLANETE : origine = centre de la planete, +Y = axe
// des poles. Le module ne connait ni viewOrigin ni la position absolue, et ne
// gere aucune collision (world/physics.js decide). Il ne fait que du rendu.
//
// Principe visuel :
//   - un profil de bandes latitudinales est precalcule en CPU (fBm 1D sur la
//     latitude, melange colorA -> colorB) et stocke dans une texture ; le
//     shader l'echantillonne a une latitude *advectee* par un fBm 3D anime ;
//   - le cisaillement zonal (chaque bande tourne a sa propre vitesse) est
//     obtenu en faisant tourner le point d'echantillonnage autour de +Y d'un
//     angle qui depend de la latitude : c'est ce qui donne l'aspect Jupiter ;
//   - un ou deux vortex fixes en (lat, lon) tournent sur eux-memes.

import * as THREE from 'three';
import { clamp, lerp, mulberry32, saturate, smoothstep } from '../core/math.js';
import { getQuality } from '../core/settings.js';
import { FBM } from '../gen/noise.js';

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Coques : rayon relatif, opacite (croissante vers le coeur), facteur de
// disparition en traversee, emission interne, dose de vortex, frequence de
// turbulence, colonne echantillonnee dans la texture de bandes.
const SHELLS = [
  { r: 1.0, opacity: 1.0, insideFade: 0.8, emissive: 0.05, storm: 0.9, freq: 1.0, column: 0.03, isOuter: true },
  { r: 0.94, opacity: 0.24, insideFade: 0.55, emissive: 0.12, storm: 0.5, freq: 1.5, column: 0.34, isOuter: false },
  { r: 0.86, opacity: 0.34, insideFade: 0.5, emissive: 0.22, storm: 0.28, freq: 2.1, column: 0.62, isOuter: false },
  { r: 0.74, opacity: 0.5, insideFade: 0.45, emissive: 0.4, storm: 0.0, freq: 2.9, column: 0.94, isOuter: false },
];

// Subdivision de l'icosphere. La valeur de reference du contrat est 6 ; on
// monte avec le preset pour eviter un limbe polygonal sur un corps de 40 km
// (le budget A05 de 40k triangles reste respecte).
const OUTER_DETAIL = { low: 8, medium: 12, high: 16, ultra: 20 };
const FBM_OCTAVES = { low: 3, medium: 4, high: 5, ultra: 5 };

const GAS_FALLBACK = {
  bandCount: 9,
  colorA: [0.78, 0.7, 0.56],
  colorB: [0.44, 0.31, 0.21],
  colorStorm: [0.85, 0.4, 0.24],
  coreColor: [1.0, 0.66, 0.36],
  turbulence: 1.0,
};

// ---------------------------------------------------------------------------
// Textures procedurales
// ---------------------------------------------------------------------------

function linearToSRGB(c) {
  return c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055;
}

/**
 * T09 : profil latitudinal des bandes, 64x512.
 * - axe vertical (v) = latitude, de -PI/2 (v=0) a +PI/2 (v=1) ;
 * - axe horizontal (u) = variante : chaque coque lit sa propre colonne, ce qui
 *   lui donne une structure de bandes differente ;
 * - RGB = couleur de bande encodee sRGB (decodee par le sampler), A = position
 *   dans le melange colorA/colorB (reutilisable comme masque).
 */
function buildBandTexture(gas, seed) {
  const W = 64;
  const H = 512;
  const data = new Uint8Array(W * H * 4);
  const bandCount = Math.max(3, Math.round(gas.bandCount) || 9);

  const coarse = new FBM({
    seed: (seed ^ 0x51e2b3c7) >>> 0,
    octaves: 4,
    frequency: 1,
    gain: 0.55,
    lacunarity: 2.13,
  });
  const fine = new FBM({
    seed: (seed ^ 0x2b9d41f3) >>> 0,
    octaves: 3,
    frequency: 1,
    gain: 0.5,
    lacunarity: 2.21,
  });

  for (let x = 0; x < W; x++) {
    const cu = x / (W - 1);
    const freqMul = 0.8 + cu * 1.6; // bandes plus serrees vers le coeur
    const domain = 3.7 + cu * 6.1; // decalage de domaine par colonne
    for (let y = 0; y < H; y++) {
      const v = y / (H - 1);
      const lat = (v - 0.5) * Math.PI;
      const bx = v * bandCount * freqMul;

      const n = coarse.sample(bx, domain, 0);
      const nf = fine.sample(bx * 3.3, domain * 0.5, 1.7);
      let t = saturate(0.5 + 0.62 * n + 0.16 * nf);
      t = t * t * (3 - 2 * t); // bandes nettes, sans etre binaires
      t = saturate(t * 1.14 - 0.07);

      // Assombrissement polaire + granulation fine.
      const polar = 1 - 0.42 * Math.pow(Math.abs(Math.sin(lat)), 3);
      const shade = 0.9 + 0.2 * nf;

      const i = (y * W + x) * 4;
      for (let c = 0; c < 3; c++) {
        const lin = saturate(lerp(gas.colorA[c], gas.colorB[c], t) * polar * shade);
        data[i + c] = Math.round(255 * saturate(linearToSRGB(lin)));
      }
      data[i + 3] = Math.round(255 * t);
    }
  }

  const tex = new THREE.DataTexture(data, W, H, THREE.RGBAFormat, THREE.UnsignedByteType);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}

/** Attenuation douce autour d'une division vide (type division de Cassini). */
function gapFactor(t, center, width) {
  const d = saturate(Math.abs(t - center) / Math.max(width, 1e-4));
  return d * d * (3 - 2 * d);
}

/**
 * Profil radial de l'anneau, 512x1.
 * R = opacite, G = variation de luminosite. Donnees brutes (pas une couleur),
 * donc pas de conversion sRGB.
 */
function buildRingTexture(seed) {
  const W = 512;
  const data = new Uint8Array(W * 4);
  const rnd = mulberry32((seed ^ 0x1c9f5b73) >>> 0);
  const coarse = new FBM({ seed: (seed ^ 0x6d5a1e37) >>> 0, octaves: 4, frequency: 1, gain: 0.55, lacunarity: 2.07 });
  const fine = new FBM({ seed: (seed ^ 0x3e17b9c5) >>> 0, octaves: 3, frequency: 1, gain: 0.5, lacunarity: 2.19 });

  // Trois divisions vides, placees de facon deterministe par la seed.
  const gaps = [
    { c: 0.18 + rnd() * 0.08, w: 0.02 + rnd() * 0.02 },
    { c: 0.46 + rnd() * 0.12, w: 0.03 + rnd() * 0.025 },
    { c: 0.76 + rnd() * 0.08, w: 0.012 + rnd() * 0.015 },
  ];

  for (let i = 0; i < W; i++) {
    const t = i / (W - 1);
    const n = coarse.sample(t * 9.5, 3.1, 0);
    const nf = fine.sample(t * 31.0, -2.4, 1.1);
    let a = saturate(0.52 + 0.55 * n + 0.22 * nf);
    a = smoothstep(0.3, 0.86, a);
    for (let g = 0; g < gaps.length; g++) a *= gapFactor(t, gaps[g].c, gaps[g].w);
    // Fondu des bords interne et externe.
    a *= smoothstep(0, 0.05, t) * (1 - smoothstep(0.92, 1.0, t));

    const bright = saturate(0.45 + 0.55 * (0.5 + 0.5 * nf));
    const o = i * 4;
    data[o] = Math.round(255 * saturate(a));
    data[o + 1] = Math.round(255 * bright);
    data[o + 2] = 0;
    data[o + 3] = 255;
  }

  const tex = new THREE.DataTexture(data, W, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  tex.colorSpace = THREE.NoColorSpace;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------------------
// Vortex
// ---------------------------------------------------------------------------

/** Un ou deux vortex, fixes en (lat, lon), avec rotation interne. */
function buildVortices(gas, seed) {
  const rnd = mulberry32((seed ^ 0x77aa33bb) >>> 0);
  const count = gas.turbulence >= 1.1 ? 2 : 1;
  const out = [];
  for (let i = 0; i < 2; i++) {
    if (i >= count) {
      out.push({ lat: 0, lon: 0, rx: 0.1, ry: 0.1, spin: 0, strength: 0, swirl: 6 });
      continue;
    }
    const hemi = rnd() < 0.5 ? -1 : 1;
    out.push({
      lat: hemi * (0.18 + rnd() * 0.42),
      lon: (rnd() * 2 - 1) * Math.PI,
      rx: 0.22 + rnd() * 0.26,
      ry: 0.075 + rnd() * 0.08,
      spin: (rnd() < 0.5 ? -1 : 1) * (0.05 + rnd() * 0.09) * (0.6 + gas.turbulence * 0.5),
      strength: i === 0 ? 0.95 : 0.55 + rnd() * 0.3,
      swirl: 5 + rnd() * 5,
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// GLSL
// ---------------------------------------------------------------------------

const NOISE_GLSL = /* glsl */ `
// Hash sans sin (stable sur tous les pilotes) + bruit de gradient 3D.
vec3 hash33(vec3 p) {
  p = fract(p * vec3(0.1031, 0.1030, 0.0973));
  p += dot(p, p.yxz + 33.33);
  return -1.0 + 2.0 * fract((p.xxy + p.yxx) * p.zyx);
}

float gnoise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = p - i;
  vec3 u = f * f * (3.0 - 2.0 * f);
  float n000 = dot(hash33(i + vec3(0.0, 0.0, 0.0)), f - vec3(0.0, 0.0, 0.0));
  float n100 = dot(hash33(i + vec3(1.0, 0.0, 0.0)), f - vec3(1.0, 0.0, 0.0));
  float n010 = dot(hash33(i + vec3(0.0, 1.0, 0.0)), f - vec3(0.0, 1.0, 0.0));
  float n110 = dot(hash33(i + vec3(1.0, 1.0, 0.0)), f - vec3(1.0, 1.0, 0.0));
  float n001 = dot(hash33(i + vec3(0.0, 0.0, 1.0)), f - vec3(0.0, 0.0, 1.0));
  float n101 = dot(hash33(i + vec3(1.0, 0.0, 1.0)), f - vec3(1.0, 0.0, 1.0));
  float n011 = dot(hash33(i + vec3(0.0, 1.0, 1.0)), f - vec3(0.0, 1.0, 1.0));
  float n111 = dot(hash33(i + vec3(1.0, 1.0, 1.0)), f - vec3(1.0, 1.0, 1.0));
  float nx00 = mix(n000, n100, u.x);
  float nx10 = mix(n010, n110, u.x);
  float nx01 = mix(n001, n101, u.x);
  float nx11 = mix(n011, n111, u.x);
  return 1.4 * mix(mix(nx00, nx10, u.y), mix(nx01, nx11, u.y), u.z);
}

float fbm3(vec3 p) {
  float sum = 0.0;
  float amp = 0.5;
  float norm = 0.0;
  vec3 q = p;
  for (int i = 0; i < FBM_OCT; i++) {
    sum += amp * gnoise(q);
    norm += amp;
    amp *= 0.5;
    q *= 2.07;
  }
  return sum / max(norm, 1e-5);
}
`;

const SHELL_VERT = /* glsl */ `
varying vec3 vLocal;

void main() {
  // Les coques sont centrees sur l'origine locale : position EST la position
  // en espace local planete.
  vLocal = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const SHELL_FRAG = /* glsl */ `
precision highp float;

uniform vec3 uSunDir;        // direction vers le soleil, espace local planete
uniform vec3 uCameraLocal;
uniform float uTime;
uniform float uInside;
uniform sampler2D uBandTex;
uniform vec3 uColorStorm;
uniform vec3 uCoreColor;
uniform float uTurbulence;
uniform float uShear;
uniform vec4 uVortex0;   // lat, lon, rayon longitudinal, rayon latitudinal
uniform vec4 uVortex0B;  // spin, force, frequence de swirl, libre
uniform vec4 uVortex1;
uniform vec4 uVortex1B;

uniform float uBandColumn;
uniform float uFreq;
uniform float uYStretch;
uniform float uOpacity;
uniform float uInsideFade;
uniform float uEmissive;
uniform float uStormMix;

varying vec3 vLocal;

const float PI = 3.141592653589793;

${NOISE_GLSL}

vec3 rotY(vec3 p, float a) {
  float c = cos(a);
  float s = sin(a);
  return vec3(c * p.x + s * p.z, p.y, c * p.z - s * p.x);
}

// Masque d'un vortex en coordonnees (lat, lon), avec rotation interne
// differentielle (plus rapide au centre).
float vortexMask(float lat, float lon, vec4 v, vec4 vb, out float swirl) {
  swirl = 0.0;
  if (vb.y <= 0.0) return 0.0;

  float dlat = lat - v.x;
  float dlon = lon - v.y;
  dlon = atan(sin(dlon), cos(dlon));            // repli propre sur [-PI, PI]
  vec2 p = vec2(dlon * cos(v.x), dlat);          // corrige la convergence des meridiens

  float a = uTime * vb.x;
  float c = cos(a);
  float s = sin(a);
  vec2 pr = vec2(c * p.x - s * p.y, s * p.x + c * p.y);
  vec2 e = vec2(pr.x / max(v.z, 1e-3), pr.y / max(v.w, 1e-3));
  float d = length(e);
  if (d > 1.3) return 0.0;

  float a2 = uTime * vb.x * (2.4 - 1.7 * clamp(d, 0.0, 1.0));
  float c2 = cos(a2);
  float s2 = sin(a2);
  vec2 pr2 = vec2(c2 * p.x - s2 * p.y, s2 * p.x + c2 * p.y);
  swirl = gnoise(vec3(pr2 * vb.z, uTime * 0.05)) * 0.7
        + gnoise(vec3(pr2 * vb.z * 2.3, uTime * 0.09)) * 0.3;

  return (1.0 - smoothstep(0.45, 1.0, d)) * vb.y;
}

void main() {
  vec3 n = normalize(vLocal);
  float lat = asin(clamp(n.y, -1.0, 1.0));
  float lon = atan(n.z, n.x);

  // Cisaillement zonal : la vitesse de rotation alterne avec la latitude, ce
  // qui etire les motifs en bandes et cree des cisailles entre zones.
  float spin = uShear * (0.35 + 0.9 * cos(lat * 4.0));
  vec3 q = rotY(n, uTime * spin);

  // Domaine anisotrope : variation rapide en latitude, lente en longitude.
  vec3 sp = vec3(q.x, q.y * uYStretch, q.z) * uFreq;
  float t1 = fbm3(sp + vec3(0.0, uTime * 0.02, 0.0));
  float t2 = gnoise(sp * 2.7 + vec3(7.3, 1.7, -4.1));

  float adv = (t1 * 0.72 + t2 * 0.28) * 0.055 * uTurbulence;
  float latT = clamp(lat / PI + 0.5 + adv, 0.002, 0.998);

  vec4 band = texture2D(uBandTex, vec2(uBandColumn, latT));
  vec3 col = band.rgb * (1.0 + 0.22 * (t1 * 0.6 + t2 * 0.4));

  // Vortex.
  float sw0;
  float sw1;
  float m0 = vortexMask(lat, lon, uVortex0, uVortex0B, sw0);
  float m1 = vortexMask(lat, lon, uVortex1, uVortex1B, sw1);
  float vm = clamp((m0 + m1) * uStormMix, 0.0, 1.0);
  if (vm > 0.001) {
    float vs = (m0 * sw0 + m1 * sw1) / max(m0 + m1, 1e-3);
    vec3 storm = uColorStorm * (0.75 + 0.5 * vs);
    col = mix(col, storm, vm * 0.9);
  }

  // Eclairage : terminateur adouci + halo au limbe.
  float ndl = dot(n, uSunDir);
  float lightT = smoothstep(-0.25, 0.35, ndl);
  vec3 viewDir = normalize(uCameraLocal - vLocal);
  float fres = 1.0 - abs(dot(n, viewDir));
  fres = fres * fres * fres;

  vec3 lit = col * (0.045 + 0.955 * lightT);
  lit += col * fres * 0.5 * lightT;
  // Emission interne : plus on plonge, plus le coeur rougeoie.
  lit += uCoreColor * uEmissive * uInside;

  float alpha = uOpacity * (1.0 - uInsideFade * uInside);
  gl_FragColor = vec4(lit, clamp(alpha, 0.0, 1.0));
}
`;

const RING_VERT = /* glsl */ `
varying vec3 vRingLocal;
varying float vRingRadius;

void main() {
  vRingRadius = length(position.xy);
  // RingGeometry vit dans le plan XY ; le mesh porte rotation.x = -PI/2, donc
  // (x, y, 0) devient (x, 0, -y) en espace local planete.
  vRingLocal = vec3(position.x, 0.0, -position.y);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const RING_FRAG = /* glsl */ `
precision highp float;

uniform sampler2D uRingTex;
uniform vec3 uRingColor;
uniform vec3 uSunDir;
uniform vec3 uCameraLocal;
uniform float uInner;
uniform float uOuter;
uniform float uPlanetRadius;
uniform float uOpacity;

varying vec3 vRingLocal;
varying float vRingRadius;

void main() {
  float t = (vRingRadius - uInner) / max(uOuter - uInner, 1.0);
  if (t < 0.0 || t > 1.0) discard;

  vec4 prof = texture2D(uRingTex, vec2(clamp(t, 0.002, 0.998), 0.5));
  float a = prof.r;
  if (a < 0.004) discard;

  // Ombre de la planete : le point est-il derriere elle par rapport au soleil ?
  float along = dot(vRingLocal, uSunDir);
  vec3 perp = vRingLocal - uSunDir * along;
  float dist = length(perp);
  float shadow = 1.0;
  if (along < 0.0) {
    shadow = mix(0.09, 1.0, smoothstep(uPlanetRadius * 0.94, uPlanetRadius * 1.07, dist));
  }

  // Vue rasante : plus d'epaisseur optique traversee.
  vec3 viewDir = normalize(uCameraLocal - vRingLocal);
  float graze = 1.0 - abs(viewDir.y);
  a *= mix(1.0, 1.55, graze * graze);

  vec3 col = uRingColor * (0.35 + 0.65 * prof.g) * shadow;
  gl_FragColor = vec4(col, clamp(a * uOpacity, 0.0, 1.0));
}
`;

// ---------------------------------------------------------------------------
// Fabrique
// ---------------------------------------------------------------------------

/**
 * @param {object} args
 * @param {object} args.spec PlanetSpec (spec.gas et spec.ring peuvent etre null)
 * @param {object} [args.quality] preset de qualite
 */
export function createGasGiant({ spec, quality } = {}) {
  const q = quality || getQuality();
  const radius = spec && spec.radius > 0 ? spec.radius : 30000;
  const seed = (spec && spec.seed) >>> 0 || 1;
  const gas = normalizeGas(spec && spec.gas);
  const ringSpec = normalizeRing(spec && spec.ring);

  const detail = OUTER_DETAIL[q && q.name] || 12;
  const innerDetail = Math.max(6, detail - 6);
  const octaves = FBM_OCTAVES[q && q.name] || 4;

  const bandTexture = buildBandTexture(gas, seed);
  const vortices = buildVortices(gas, seed);
  const turbulence = clamp(gas.turbulence, 0.1, 3);

  const group = new THREE.Group();
  group.name = `gasGiant:${(spec && spec.id) || 'unknown'}`;

  // Uniforms partages entre les 4 coques : un seul objet par valeur, donc une
  // seule ecriture par frame.
  const shared = {
    uSunDir: { value: new THREE.Vector3(0, 1, 0) },
    uCameraLocal: { value: new THREE.Vector3(0, 0, radius * 4) },
    uTime: { value: 0 },
    uInside: { value: 0 },
    uBandTex: { value: bandTexture },
    uColorStorm: { value: new THREE.Vector3(gas.colorStorm[0], gas.colorStorm[1], gas.colorStorm[2]) },
    uCoreColor: { value: new THREE.Vector3(gas.coreColor[0], gas.coreColor[1], gas.coreColor[2]) },
    uTurbulence: { value: turbulence },
    uShear: { value: 0.01 + 0.008 * turbulence },
    uVortex0: { value: new THREE.Vector4(vortices[0].lat, vortices[0].lon, vortices[0].rx, vortices[0].ry) },
    uVortex0B: { value: new THREE.Vector4(vortices[0].spin, vortices[0].strength, vortices[0].swirl, 0) },
    uVortex1: { value: new THREE.Vector4(vortices[1].lat, vortices[1].lon, vortices[1].rx, vortices[1].ry) },
    uVortex1B: { value: new THREE.Vector4(vortices[1].spin, vortices[1].strength, vortices[1].swirl, 0) },
  };

  const geometries = [];
  const materials = [];
  const shells = [];

  for (let i = 0; i < SHELLS.length; i++) {
    const cfg = SHELLS[i];
    const geo = new THREE.IcosahedronGeometry(radius * cfg.r, cfg.isOuter ? detail : innerDetail);
    const mat = new THREE.ShaderMaterial({
      vertexShader: SHELL_VERT,
      fragmentShader: SHELL_FRAG,
      defines: { FBM_OCT: String(cfg.isOuter ? octaves : Math.max(2, octaves - 2)) },
      uniforms: {
        ...shared,
        uBandColumn: { value: cfg.column },
        uFreq: { value: Math.max(3, gas.bandCount) * 0.3 * cfg.freq },
        uYStretch: { value: 3.0 },
        uOpacity: { value: cfg.opacity },
        uInsideFade: { value: cfg.insideFade },
        uEmissive: { value: cfg.emissive },
        uStormMix: { value: cfg.storm },
      },
      // Toujours `transparent` : la bascule de traversee ne touche alors que
      // des etats GL purs (side, depthWrite), jamais la cle de programme, donc
      // aucune recompilation de shader en plein vol. Hors traversee, la coque
      // externe ecrit la profondeur et sort a alpha = 1 : elle se comporte
      // exactement comme un materiau opaque.
      transparent: true,
      depthWrite: cfg.isOuter,
      depthTest: true,
      side: THREE.FrontSide,
      blending: THREE.NormalBlending,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = `${group.name}:shell${i}`;
    mesh.frustumCulled = false; // la coque englobe souvent la camera
    mesh.renderOrder = i;
    mesh.visible = cfg.isOuter;
    group.add(mesh);
    geometries.push(geo);
    materials.push(mat);
    shells.push({ cfg, mesh, mat });
  }

  // ------------------------------------------------------------------ anneau
  let ringTexture = null;
  if (ringSpec) {
    const inner = radius * ringSpec.inner;
    const outer = radius * ringSpec.outer;
    ringTexture = buildRingTexture(seed);
    const geo = new THREE.RingGeometry(inner, outer, 192, 1);
    const mat = new THREE.ShaderMaterial({
      vertexShader: RING_VERT,
      fragmentShader: RING_FRAG,
      uniforms: {
        uRingTex: { value: ringTexture },
        uRingColor: { value: new THREE.Vector3(ringSpec.color[0], ringSpec.color[1], ringSpec.color[2]) },
        uSunDir: shared.uSunDir,
        uCameraLocal: shared.uCameraLocal,
        uInner: { value: inner },
        uOuter: { value: outer },
        uPlanetRadius: { value: radius },
        uOpacity: { value: ringSpec.opacity },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      blending: THREE.NormalBlending,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = `${group.name}:ring`;
    mesh.rotation.x = -Math.PI / 2; // plan equatorial (+Y = axe des poles)
    mesh.renderOrder = 6;
    group.add(mesh);
    geometries.push(geo);
    materials.push(mat);
  }

  // ---------------------------------------------------------------- etats
  const insideLimit = radius * 1.02;
  const insideSpan = radius * 0.5;
  let insideState = -1; // -1 inconnu, 0 dehors, 1 en traversee
  let time = 0;

  function applyInside(inside) {
    const s = inside > 0 ? 1 : 0;
    if (s === insideState) return;
    insideState = s;
    for (let i = 0; i < shells.length; i++) {
      const { cfg, mesh, mat } = shells[i];
      if (s === 1) {
        // En traversee : on doit voir a travers, pas se cogner a un mur blanc.
        mat.side = THREE.DoubleSide;
        mat.depthWrite = false;
        mesh.visible = true;
      } else {
        mat.side = THREE.FrontSide;
        mat.depthWrite = cfg.isOuter;
        // Les coques internes sont invisibles depuis l'exterieur de toute
        // facon : on economise le remplissage.
        mesh.visible = cfg.isOuter;
      }
    }
  }
  applyInside(0);

  const fogResult = { color: null, density: 0 };

  const api = {
    object3D: group,

    /** @param {number} dt @param {object} ctx { sunDirLocal, cameraLocal, insideFactor } */
    update(dt, ctx) {
      // L'horloge avance plus vite sur une geante turbulente.
      time += dt * (0.4 + 0.6 * turbulence);
      shared.uTime.value = time;

      const sun = ctx && ctx.sunDirLocal;
      if (sun) {
        shared.uSunDir.value.set(sun.x, sun.y, sun.z);
        const len = shared.uSunDir.value.length();
        if (len > 1e-6) shared.uSunDir.value.multiplyScalar(1 / len);
      }

      const cam = ctx && ctx.cameraLocal;
      if (cam) shared.uCameraLocal.value.set(cam.x, cam.y, cam.z);

      let inside;
      if (ctx && typeof ctx.insideFactor === 'number') inside = saturate(ctx.insideFactor);
      else inside = cam ? api.insideFactorAt(cam) : 0;
      shared.uInside.value = inside;
      applyInside(inside);
    },

    /** 0 dehors, monte vers 1 en approchant du coeur. */
    insideFactorAt(cameraLocal) {
      if (!cameraLocal) return 0;
      const r = Math.hypot(cameraLocal.x, cameraLocal.y, cameraLocal.z);
      if (r > insideLimit) return 0;
      return saturate((insideLimit - r) / insideSpan);
    },

    /**
     * Brouillard de traversee : colorA en peripherie -> coreColor au coeur.
     * Densite par metre, calibree pour quelques kilometres de visibilite a
     * l'entree et quelques centaines de metres au coeur.
     */
    fogFor(insideFactor, out) {
      const t = saturate(insideFactor || 0);
      const e = Math.pow(t, 0.75);
      const target = out || new THREE.Color();
      target.setRGB(
        lerp(gas.colorA[0], gas.coreColor[0], e),
        lerp(gas.colorA[1], gas.coreColor[1], e),
        lerp(gas.colorA[2], gas.coreColor[2], e),
      );
      const density = (0.0009 + 0.0051 * Math.pow(t, 1.7)) * smoothstep(0, 0.05, t);
      fogResult.color = target;
      fogResult.density = density;
      return fogResult;
    },

    dispose() {
      group.clear();
      for (let i = 0; i < geometries.length; i++) geometries[i].dispose();
      for (let i = 0; i < materials.length; i++) materials[i].dispose();
      geometries.length = 0;
      materials.length = 0;
      shells.length = 0;
      bandTexture.dispose();
      if (ringTexture) ringTexture.dispose();
    },
  };

  return api;
}

// ---------------------------------------------------------------------------
// Normalisation des specs (robustesse aux specs incompletes)
// ---------------------------------------------------------------------------

function rgbOr(value, fallback) {
  if (Array.isArray(value) && value.length >= 3) {
    return [Number(value[0]) || 0, Number(value[1]) || 0, Number(value[2]) || 0];
  }
  return fallback.slice();
}

function normalizeGas(gas) {
  const g = gas || GAS_FALLBACK;
  return {
    bandCount: Math.max(3, Math.round(Number(g.bandCount)) || GAS_FALLBACK.bandCount),
    colorA: rgbOr(g.colorA, GAS_FALLBACK.colorA),
    colorB: rgbOr(g.colorB, GAS_FALLBACK.colorB),
    colorStorm: rgbOr(g.colorStorm, GAS_FALLBACK.colorStorm),
    coreColor: rgbOr(g.coreColor, GAS_FALLBACK.coreColor),
    turbulence: Number.isFinite(Number(g.turbulence)) ? Number(g.turbulence) : 1,
  };
}

function normalizeRing(ring) {
  if (!ring) return null;
  const inner = Number(ring.inner);
  const outer = Number(ring.outer);
  if (!Number.isFinite(inner) || !Number.isFinite(outer) || outer <= inner) return null;
  return {
    inner: Math.max(1.05, inner),
    outer: Math.max(inner + 0.05, outer),
    color: rgbOr(ring.color, [0.8, 0.83, 0.85]),
    opacity: Number.isFinite(Number(ring.opacity)) ? clamp(Number(ring.opacity), 0, 1) : 0.4,
  };
}
