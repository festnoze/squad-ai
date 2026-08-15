// Generateurs de textures procedurales partagees.
//
// Regle du projet : zero asset binaire. Tout est calcule au chargement, soit
// depuis le bruit de gen/noise.js (DataTexture), soit dessine sur un canvas 2D
// (CanvasTexture). Les textures de donnees sont en NoColorSpace (on ne veut
// aucune conversion), celles qui portent une couleur visible sont en
// SRGBColorSpace (three convertit vers l'espace lineaire de travail).
//
// Les motifs derives du bruit sont TILEABLES : on echantillonne un bruit 4D sur
// le produit de deux cercles (tore), ce qui rend le resultat periodique en u et
// en v sans aucune couture.

import * as THREE from 'three';
import { makeNoise4D } from './noise.js';
import { clamp, saturate } from '../core/math.js';

const TAU = Math.PI * 2;

/**
 * fBm periodique en u et v (u, v dans [0,1)).
 * Le tore de rayon `radius` grandit avec l'octave : plus il est grand, plus il
 * y a de details le long du cycle.
 */
function tileableFbm(noise4, u, v, octaves, radius, gain, lacunarity) {
  let sum = 0;
  let amp = 1;
  let norm = 0;
  let r = radius;
  const au = u * TAU;
  const av = v * TAU;
  for (let o = 0; o < octaves; o++) {
    // Un dephasage par octave decorrele les couches.
    const ph = o * 1.317;
    const ca = Math.cos(au + ph) * r;
    const sa = Math.sin(au + ph) * r;
    const cb = Math.cos(av - ph) * r;
    const sb = Math.sin(av - ph) * r;
    sum += noise4(ca, sa, cb, sb) * amp;
    norm += amp;
    amp *= gain;
    r *= lacunarity;
  }
  return sum / (norm || 1);
}

function hexToBytes(hex) {
  const s = String(hex).replace('#', '');
  const n = parseInt(s.length === 3
    ? s[0] + s[0] + s[1] + s[1] + s[2] + s[2]
    : s.padEnd(6, '0').slice(0, 6), 16) | 0;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mixBytes(a, b, t) {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

function makeCanvas(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  return canvas;
}

// ---------------------------------------------------------------------------
// T04 - normal map de detail
// ---------------------------------------------------------------------------

const DETAIL_SEED = 0x5eed1a3b;

/**
 * Normal map tileable de micro-relief, seed fixe (toutes les planetes la
 * partagent : elle est modulee dans le shader, pas ici).
 * Le canal alpha transporte la hauteur, utile pour d'autres effets.
 *
 * @param {number} size cote de la texture (puissance de 2 conseillee)
 * @returns {THREE.DataTexture} RGBA8, normale encodee 0..255 (128 = 0)
 */
export function createDetailNormalTexture(size = 256) {
  const n = Math.max(8, size | 0);
  const noise4 = makeNoise4D(DETAIL_SEED);

  // Champ de hauteur intermediaire, [-1, 1].
  const height = new Float32Array(n * n);
  for (let j = 0; j < n; j++) {
    const v = j / n;
    for (let i = 0; i < n; i++) {
      height[j * n + i] = tileableFbm(noise4, i / n, v, 5, 2.4, 0.55, 2.03);
    }
  }

  // Derivation de la normale par differences centrees, avec repli (wrap).
  const data = new Uint8Array(n * n * 4);
  const gradScale = n / 48;
  for (let j = 0; j < n; j++) {
    const jm = ((j - 1 + n) % n) * n;
    const jp = ((j + 1) % n) * n;
    const jc = j * n;
    for (let i = 0; i < n; i++) {
      const im = (i - 1 + n) % n;
      const ip = (i + 1) % n;
      const dx = (height[jc + ip] - height[jc + im]) * 0.5 * gradScale;
      const dy = (height[jp + i] - height[jm + i]) * 0.5 * gradScale;
      let nx = -dx;
      let ny = -dy;
      let nz = 1;
      const inv = 1 / Math.hypot(nx, ny, nz);
      nx *= inv;
      ny *= inv;
      nz *= inv;
      const o = (jc + i) * 4;
      data[o] = Math.round(saturate(nx * 0.5 + 0.5) * 255);
      data[o + 1] = Math.round(saturate(ny * 0.5 + 0.5) * 255);
      data[o + 2] = Math.round(saturate(nz * 0.5 + 0.5) * 255);
      data[o + 3] = Math.round(saturate(height[jc + i] * 0.5 + 0.5) * 255);
    }
  }

  const tex = new THREE.DataTexture(data, n, n, THREE.RGBAFormat, THREE.UnsignedByteType);
  tex.name = 'detailNormal';
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 4;
  tex.colorSpace = THREE.NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------------------
// T08 - sprite radial additif
// ---------------------------------------------------------------------------

/**
 * Degrade radial pour les flares, tuyeres, particules de nuage.
 * L'alpha decroit en (1 - t)^power, la couleur passe de `inner` a `outer`.
 *
 * @param {number} size cote du canvas
 * @param {string} inner couleur au centre, 'rrggbb'
 * @param {string} outer couleur au bord, 'rrggbb'
 * @param {number} power durete de la decroissance (1 = lineaire)
 * @returns {THREE.CanvasTexture}
 */
export function createRadialSprite(size = 256, inner = 'ffffff', outer = '000000', power = 2) {
  const s = Math.max(8, size | 0);
  const canvas = makeCanvas(s, s);
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, s, s);

  const c = s * 0.5;
  const ci = hexToBytes(inner);
  const co = hexToBytes(outer);
  const grad = ctx.createRadialGradient(c, c, 0, c, c, c);
  const STEPS = 16;
  const p = Math.max(0.05, power);
  for (let k = 0; k <= STEPS; k++) {
    const t = k / STEPS;
    const rgb = mixBytes(ci, co, t);
    const a = Math.pow(1 - t, p);
    grad.addColorStop(t, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a.toFixed(4)})`);
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, s, s);

  const tex = new THREE.CanvasTexture(canvas);
  tex.name = 'radialSprite';
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------------------
// Bruit scalaire tileable
// ---------------------------------------------------------------------------

/**
 * fBm tileable sur un seul canal (R8), a echantillonner en Repeat.
 *
 * @param {number} size cote de la texture
 * @param {number} seed graine
 * @param {number} octaves nombre d'octaves
 * @returns {THREE.DataTexture}
 */
export function createNoiseTexture(size = 128, seed = 1, octaves = 4) {
  const n = Math.max(8, size | 0);
  const noise4 = makeNoise4D(seed >>> 0);
  const oct = clamp(octaves | 0, 1, 8);
  const data = new Uint8Array(n * n);
  for (let j = 0; j < n; j++) {
    const v = j / n;
    for (let i = 0; i < n; i++) {
      const f = tileableFbm(noise4, i / n, v, oct, 2.0, 0.5, 2.03);
      data[j * n + i] = Math.round(saturate(f * 0.5 + 0.5) * 255);
    }
  }

  const tex = new THREE.DataTexture(data, n, n, THREE.RedFormat, THREE.UnsignedByteType);
  tex.name = `noise${n}`;
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.generateMipmaps = true;
  tex.colorSpace = THREE.NoColorSpace;
  tex.unpackAlignment = 1;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------------------
// Rampe de couleur 1D
// ---------------------------------------------------------------------------

/**
 * Rampe horizontale de couleurs, echantillonnable en u.
 *
 * @param {Array<[number, string]>} stops paires [t (0..1), 'rrggbb']
 * @param {number} width largeur en pixels (hauteur = 1)
 * @returns {THREE.CanvasTexture}
 */
export function createGradientTexture(stops, width = 256) {
  const w = Math.max(2, width | 0);
  const list = (Array.isArray(stops) && stops.length > 0
    ? stops.slice()
    : [[0, '000000'], [1, 'ffffff']]
  )
    .map((s) => [saturate(Number(s[0]) || 0), s[1]])
    .sort((a, b) => a[0] - b[0]);

  const canvas = makeCanvas(w, 1);
  const ctx = canvas.getContext('2d');
  const grad = ctx.createLinearGradient(0, 0, w, 0);
  for (const [t, hex] of list) {
    const rgb = hexToBytes(hex);
    grad.addColorStop(t, `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`);
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, 1);

  const tex = new THREE.CanvasTexture(canvas);
  tex.name = 'gradient';
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  // Une rampe de 1 pixel de haut n'a rien a gagner d'un mipmap : il ne ferait
  // que melanger les extremites.
  tex.generateMipmaps = false;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}
