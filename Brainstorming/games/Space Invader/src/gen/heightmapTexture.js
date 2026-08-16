// Cartes planetaires equirectangulaires : heightmap (relief en metres) et
// biome-map (couleur sRGB du biome).
//
// Ces deux cartes sont la "vue de loin" de la planete : elles alimentent la
// minimap du HUD, la teinte des hauts-fonds de l'ocean, les ombres de nuages et
// tout module qui a besoin de connaitre le sol sans construire de maillage.
//
// Convention de projection (identique cote CPU et cote shader) :
//   texel (i, j) d'une carte width x height correspond a
//     lon = ((i + 0.5) / width)  * 2*PI - PI      // -PI a PI, cyclique
//     lat =  PI/2 - ((j + 0.5) / height) * PI     // +PI/2 (ligne 0) a -PI/2
//   soit, en coordonnees de texture,
//     u = lon / (2*PI) + 0.5
//     v = 0.5 - lat / PI
// Le decalage de 0.5 texel place les echantillons au centre des texels, ce qui
// correspond exactement au filtrage lineaire du GPU.
//
// La generation passe par le pool de workers (message 'heightmap'). Si aucun
// pool n'est fourni ou si la requete echoue, on retombe sur un calcul local
// via le champ de hauteur : le module reste utilisable seul.

import * as THREE from 'three';
import { clamp, saturate } from '../core/math.js';
import { BIOME_ID, BIOMES, getPaletteBytes } from './palettes.js';
import { createHeightField } from './heightField.js';

const TWO_PI = Math.PI * 2;

/**
 * @param {object} opts
 * @param {object} opts.spec PlanetSpec (spec.seaLevel doit deja etre calibre)
 * @param {object} [opts.pool] WorkerPool de terrain, optionnel
 * @param {number} [opts.size] largeur de la carte (la hauteur vaut size / 2)
 * @returns {Promise<object>} cf. docs/CONTRACTS.md P2
 */
export async function createPlanetMaps({ spec, pool, size = 512 } = {}) {
  if (!spec) throw new Error('createPlanetMaps: spec manquant');

  const width = Math.max(32, Math.round(size) | 0);
  const height = Math.max(16, Math.round(width / 2));

  let raw = null;
  if (pool && typeof pool.request === 'function') {
    try {
      const res = await pool.request({ type: 'heightmap', width, height });
      if (res && res.height && res.biome && res.water) {
        raw = {
          heightData: toFloat32(res.height, width * height),
          biomeData: toUint8(res.biome, width * height),
          waterData: toUint8(res.water, width * height),
        };
      }
    } catch (err) {
      // Le pool peut etre absent, sature ou avoir ete detruit : on recalcule.
      raw = null;
    }
  }
  if (!raw) raw = await computeMapsLocally(spec, width, height);

  const { heightData, biomeData, waterData } = raw;

  // ---------------------------------------------------------------------
  // Statistiques : bornes de relief et couverture oceanique
  // ---------------------------------------------------------------------
  let minElev = Infinity;
  let maxElev = -Infinity;
  let waterWeight = 0;
  let totalWeight = 0;

  for (let j = 0; j < height; j++) {
    const lat = Math.PI * 0.5 - ((j + 0.5) / height) * Math.PI;
    // Ponderation par cos(latitude) : une ligne polaire couvre bien moins de
    // surface qu'une ligne equatoriale.
    const w = Math.cos(lat);
    const row = j * width;
    let rowWater = 0;
    for (let i = 0; i < width; i++) {
      const k = row + i;
      const e = heightData[k];
      if (e < minElev) minElev = e;
      if (e > maxElev) maxElev = e;
      if (waterData[k]) rowWater++;
    }
    waterWeight += (rowWater / width) * w;
    totalWeight += w;
  }
  if (!isFinite(minElev)) minElev = 0;
  if (!isFinite(maxElev)) maxElev = 0;
  const oceanCoverage = totalWeight > 0 ? saturate(waterWeight / totalWeight) : 0;

  // ---------------------------------------------------------------------
  // Texture de relief : R32F, valeurs en metres (non normalisees)
  // ---------------------------------------------------------------------
  const heightTexture = new THREE.DataTexture(
    heightData,
    width,
    height,
    THREE.RedFormat,
    THREE.FloatType,
  );
  heightTexture.name = `heightmap-${spec.id}`;
  heightTexture.colorSpace = THREE.NoColorSpace;
  heightTexture.wrapS = THREE.RepeatWrapping; // longitude cyclique
  heightTexture.wrapT = THREE.ClampToEdgeWrapping; // latitude bornee aux poles
  heightTexture.minFilter = THREE.LinearFilter;
  heightTexture.magFilter = THREE.LinearFilter;
  heightTexture.generateMipmaps = false;
  heightTexture.flipY = false;
  heightTexture.needsUpdate = true;

  // ---------------------------------------------------------------------
  // Biome-map : RGBA8 sRGB, prete pour un putImageData sur la minimap
  // ---------------------------------------------------------------------
  const rgba = buildBiomeRGBA(spec, heightData, biomeData, waterData, width, height, minElev, maxElev);

  const biomeTexture = new THREE.DataTexture(
    new Uint8Array(rgba.buffer, rgba.byteOffset, rgba.length),
    width,
    height,
    THREE.RGBAFormat,
    THREE.UnsignedByteType,
  );
  biomeTexture.name = `biomemap-${spec.id}`;
  biomeTexture.colorSpace = THREE.SRGBColorSpace;
  biomeTexture.wrapS = THREE.RepeatWrapping;
  biomeTexture.wrapT = THREE.ClampToEdgeWrapping;
  biomeTexture.minFilter = THREE.LinearFilter;
  biomeTexture.magFilter = THREE.LinearFilter;
  biomeTexture.generateMipmaps = false;
  biomeTexture.flipY = false;
  biomeTexture.needsUpdate = true;

  // ImageData reutilisable par la minimap (canvas 2D). Hors navigateur, on
  // renvoie un objet de meme forme.
  let imageData;
  try {
    imageData = typeof ImageData !== 'undefined'
      ? new ImageData(rgba, width, height)
      : { data: rgba, width, height };
  } catch (err) {
    imageData = { data: rgba, width, height };
  }

  // ---------------------------------------------------------------------
  // Echantillonnage
  // ---------------------------------------------------------------------
  // Objet de sortie reutilise (comme latLonFromUnit dans core/math.js) :
  // aucune allocation, meme appele a chaque frame. A lire immediatement.
  const sampleOut = { elev: 0, biome: BIOME_ID.ROCK, water: false };

  function sample(lat, lon) {
    const la = clamp(lat, -Math.PI * 0.5, Math.PI * 0.5);
    // Longitude ramenee dans [0,1) puis en coordonnee de texel.
    let fu = (lon / TWO_PI + 0.5) % 1;
    if (fu < 0) fu += 1;
    const x = fu * width - 0.5;
    const y = (0.5 - la / Math.PI) * height - 0.5;

    let x0 = Math.floor(x);
    const tx = x - x0;
    x0 = ((x0 % width) + width) % width;
    const x1 = (x0 + 1) % width;

    let y0 = Math.floor(y);
    const ty = y - y0;
    y0 = clamp(y0, 0, height - 1);
    const y1 = clamp(y0 + 1, 0, height - 1);

    const r0 = y0 * width;
    const r1 = y1 * width;
    const h00 = heightData[r0 + x0];
    const h10 = heightData[r0 + x1];
    const h01 = heightData[r1 + x0];
    const h11 = heightData[r1 + x1];
    // Bilineaire pour l'elevation (grandeur continue).
    const top = h00 + (h10 - h00) * tx;
    const bot = h01 + (h11 - h01) * tx;
    sampleOut.elev = top + (bot - top) * ty;

    // Le biome et le drapeau d'eau sont des categories : plus proche voisin.
    const nx = tx < 0.5 ? x0 : x1;
    const ny = ty < 0.5 ? r0 : r1;
    sampleOut.biome = biomeData[ny + nx];
    sampleOut.water = waterData[ny + nx] !== 0;
    return sampleOut;
  }

  let disposed = false;

  return {
    heightTexture,
    biomeTexture,
    heightData,
    biomeData,
    waterData,
    width,
    height,
    oceanCoverage,
    minElev,
    maxElev,
    imageData,
    sample,
    dispose() {
      if (disposed) return;
      disposed = true;
      heightTexture.dispose();
      biomeTexture.dispose();
    },
  };
}

// -------------------------------------------------------------------------
// Interne
// -------------------------------------------------------------------------

function toFloat32(src, n) {
  if (src instanceof Float32Array && src.length === n) return src;
  const out = new Float32Array(n);
  const m = Math.min(n, src.length || 0);
  for (let i = 0; i < m; i++) out[i] = src[i];
  return out;
}

function toUint8(src, n) {
  if (src instanceof Uint8Array && src.length === n) return src;
  const out = new Uint8Array(n);
  const m = Math.min(n, src.length || 0);
  for (let i = 0; i < m; i++) out[i] = src[i];
  return out;
}

/** Cede la main au navigateur pour ne pas geler la page pendant un long calcul. */
function yieldToHost() {
  return new Promise((resolve) => {
    if (typeof setTimeout === 'function') setTimeout(resolve, 0);
    else resolve();
  });
}

/**
 * Calcul local (sans worker) des trois plans de la carte. Deterministe et
 * identique a ce que produit le worker, puisque la source est le meme
 * champ de hauteur.
 */
async function computeMapsLocally(spec, width, height) {
  const field = createHeightField(spec);
  const n = width * height;
  const heightData = new Float32Array(n);
  const biomeData = new Uint8Array(n);
  const waterData = new Uint8Array(n);

  for (let j = 0; j < height; j++) {
    const lat = Math.PI * 0.5 - ((j + 0.5) / height) * Math.PI;
    const cl = Math.cos(lat);
    const sl = Math.sin(lat);
    const row = j * width;
    for (let i = 0; i < width; i++) {
      const lon = ((i + 0.5) / width) * TWO_PI - Math.PI;
      const x = cl * Math.cos(lon);
      const y = sl;
      const z = cl * Math.sin(lon);
      const elev = field.elevation(x, y, z);
      const k = row + i;
      heightData[k] = elev;
      biomeData[k] = field.biomeId(x, y, z, elev);
      waterData[k] = field.isWater(elev) ? 1 : 0;
    }
    // Toutes les 24 lignes, on rend la main (chargement non bloquant).
    if ((j & 23) === 23) await yieldToHost();
  }

  return { heightData, biomeData, waterData };
}

/**
 * Construit le plan RGBA de la biome-map. L'eau profonde est assombrie et le
 * relief emerge est legerement eclairci avec l'altitude : la minimap reste
 * lisible meme sur une planete monochrome.
 */
function buildBiomeRGBA(spec, heightData, biomeData, waterData, width, height, minElev, maxElev) {
  const bytes = getPaletteBytes(spec.palette);
  const count = BIOMES.length;
  const out = new Uint8ClampedArray(width * height * 4);

  const seaLevel = typeof spec.seaLevel === 'number' ? spec.seaLevel : 0;
  const depthSpan = Math.max(1, seaLevel - minElev);
  const landSpan = Math.max(1, maxElev - seaLevel);

  for (let k = 0, p = 0; k < heightData.length; k++, p += 4) {
    let id = biomeData[k];
    if (id >= count) id = BIOME_ID.ROCK;
    const o = id * 3;
    const elev = heightData[k];

    let f;
    if (id === BIOME_ID.DEEP_OCEAN || id === BIOME_ID.SHALLOW_OCEAN) {
      // Plus c'est profond, plus c'est sombre.
      const dn = saturate((seaLevel - elev) / depthSpan);
      f = 0.86 - 0.36 * dn;
    } else if (id === BIOME_ID.LAVA) {
      f = 1.06;
    } else if (waterData[k]) {
      // Mer gelee : a peine assombrie, elle doit rester blanche.
      f = 0.94;
    } else {
      const above = saturate((elev - seaLevel) / landSpan);
      f = 0.9 + 0.3 * above;
    }

    out[p] = bytes[o] * f;
    out[p + 1] = bytes[o + 1] * f;
    out[p + 2] = bytes[o + 2] * f;
    out[p + 3] = 255;
  }
  return out;
}
