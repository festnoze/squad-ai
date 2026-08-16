// Bruit fractal seede, construit sur simplex-noise. Aucune dependance a three :
// ce module tourne aussi bien dans un worker que dans le thread principal.

import { createNoise2D, createNoise3D, createNoise4D } from 'simplex-noise';
import { mulberry32, saturate } from '../core/math.js';

export function makeNoise2D(seed) {
  return createNoise2D(mulberry32(seed));
}

export function makeNoise3D(seed) {
  return createNoise3D(mulberry32(seed));
}

export function makeNoise4D(seed) {
  return createNoise4D(mulberry32(seed));
}

/**
 * fBm generique.
 *
 * - `ridged` produit des cretes acerees (chaines de montagnes) dans [0, 1].
 * - `warp` deforme le domaine avant echantillonnage (relief plus organique,
 *   evite l'aspect "patatoide regulier" du simplex pur).
 * - `erosion` amortit les octaves hautes dans les zones deja basses, ce qui
 *   imite grossierement des vallees lissees et des cretes preservees.
 */
export class FBM {
  constructor({
    seed = 1,
    octaves = 6,
    frequency = 1,
    lacunarity = 2.03,
    gain = 0.5,
    ridged = false,
    warp = 0,
    warpFreq = 0.6,
    erosion = 0,
  } = {}) {
    this.octaves = Math.max(1, octaves | 0);
    this.frequency = frequency;
    this.lacunarity = lacunarity;
    this.gain = gain;
    this.ridged = !!ridged;
    this.warp = warp;
    this.warpFreq = warpFreq;
    this.erosion = erosion;

    this.noise = makeNoise3D(seed);
    if (warp > 0) {
      this.warpX = makeNoise3D(seed ^ 0x9e3779b9);
      this.warpY = makeNoise3D(seed ^ 0x85ebca6b);
      this.warpZ = makeNoise3D(seed ^ 0xc2b2ae35);
    }

    // Decorrelation des octaves : un decalage pseudo-aleatoire par octave.
    const rnd = mulberry32(seed ^ 0x1b873593);
    this.offsets = new Float64Array(this.octaves * 3);
    for (let i = 0; i < this.octaves * 3; i++) this.offsets[i] = rnd() * 512 - 256;

    // Normalisation d'amplitude.
    let norm = 0;
    let amp = 1;
    for (let i = 0; i < this.octaves; i++) {
      norm += amp;
      amp *= this.gain;
    }
    this.invNorm = 1 / norm;
  }

  sample(x, y, z) {
    let px = x;
    let py = y;
    let pz = z;

    if (this.warp > 0) {
      const wf = this.warpFreq;
      const w = this.warp;
      px += w * this.warpX(x * wf, y * wf, z * wf);
      py += w * this.warpY(x * wf, y * wf, z * wf);
      pz += w * this.warpZ(x * wf, y * wf, z * wf);
    }

    let sum = 0;
    let amp = 1;
    let freq = this.frequency;
    const off = this.offsets;
    const ridged = this.ridged;
    const erosion = this.erosion;

    for (let i = 0; i < this.octaves; i++) {
      const o = i * 3;
      let n = this.noise(px * freq + off[o], py * freq + off[o + 1], pz * freq + off[o + 2]);
      if (ridged) {
        n = 1 - Math.abs(n);
        n *= n;
      }
      sum += n * amp;
      amp *= this.gain;
      if (erosion > 0) {
        // Les octaves suivantes sont attenuees la ou l'accumulation est basse.
        const damp = 1 - erosion + erosion * saturate(ridged ? sum : sum * 0.5 + 0.5);
        amp *= damp;
      }
      freq *= this.lacunarity;
    }

    return sum * this.invNorm;
  }

  sampleUnit(v) {
    return this.sample(v.x, v.y, v.z);
  }
}

/**
 * Profils de relief. Chaque type de planete pioche ici.
 * `amplitude` est une fraction du rayon de la planete.
 */
export const NOISE_PROFILES = {
  // Continents + chaines de montagnes : le profil "Terre".
  continental: {
    continents: { octaves: 5, frequency: 1.05, gain: 0.52, lacunarity: 2.05, warp: 0.35, warpFreq: 0.7 },
    mountains: { octaves: 7, frequency: 2.6, gain: 0.48, lacunarity: 2.11, ridged: true, erosion: 0.45 },
    detail: { octaves: 4, frequency: 12, gain: 0.5, lacunarity: 2.2 },
    mountainWeight: 0.62,
    detailWeight: 0.07,
    seaFraction: 0.52,
  },
  // Monde d'eau : peu de terres emergees, plateaux doux.
  oceanic: {
    continents: { octaves: 4, frequency: 0.85, gain: 0.55, lacunarity: 2.0, warp: 0.5, warpFreq: 0.5 },
    mountains: { octaves: 6, frequency: 2.2, gain: 0.45, lacunarity: 2.07, ridged: true, erosion: 0.3 },
    detail: { octaves: 4, frequency: 10, gain: 0.5, lacunarity: 2.2 },
    mountainWeight: 0.35,
    detailWeight: 0.05,
    seaFraction: 0.86,
  },
  // Dunes, plateaux, canyons.
  desertic: {
    continents: { octaves: 4, frequency: 1.3, gain: 0.5, lacunarity: 2.0, warp: 0.6, warpFreq: 1.1 },
    mountains: { octaves: 6, frequency: 4.5, gain: 0.42, lacunarity: 2.15, ridged: true, erosion: 0.6 },
    detail: { octaves: 5, frequency: 22, gain: 0.55, lacunarity: 2.2 },
    mountainWeight: 0.5,
    detailWeight: 0.14,
    seaFraction: 0.06,
  },
  // Volcanique : cones, fractures, mers de lave.
  volcanic: {
    continents: { octaves: 5, frequency: 1.6, gain: 0.48, lacunarity: 2.1, warp: 0.9, warpFreq: 1.4 },
    mountains: { octaves: 8, frequency: 3.4, gain: 0.55, lacunarity: 2.17, ridged: true, erosion: 0.15 },
    detail: { octaves: 5, frequency: 18, gain: 0.6, lacunarity: 2.3 },
    mountainWeight: 0.95,
    detailWeight: 0.16,
    seaFraction: 0.3,
  },
  // Banquise : reliefs bas, crevasses, plateaux.
  glacial: {
    continents: { octaves: 4, frequency: 1.0, gain: 0.5, lacunarity: 2.0, warp: 0.3, warpFreq: 0.8 },
    mountains: { octaves: 6, frequency: 3.0, gain: 0.4, lacunarity: 2.09, ridged: true, erosion: 0.5 },
    detail: { octaves: 5, frequency: 16, gain: 0.5, lacunarity: 2.2 },
    mountainWeight: 0.45,
    detailWeight: 0.1,
    seaFraction: 0.6,
  },
  // Monde epuise : anciens bassins oceaniques a sec.
  arid: {
    continents: { octaves: 5, frequency: 1.0, gain: 0.54, lacunarity: 2.04, warp: 0.4, warpFreq: 0.65 },
    mountains: { octaves: 7, frequency: 2.8, gain: 0.46, lacunarity: 2.12, ridged: true, erosion: 0.55 },
    detail: { octaves: 5, frequency: 15, gain: 0.52, lacunarity: 2.2 },
    mountainWeight: 0.58,
    detailWeight: 0.11,
    seaFraction: 0.1,
  },
  // Cailloux nus, crateres.
  barren: {
    continents: { octaves: 4, frequency: 1.4, gain: 0.5, lacunarity: 2.0, warp: 0.25, warpFreq: 0.9 },
    mountains: { octaves: 6, frequency: 5.0, gain: 0.45, lacunarity: 2.2, ridged: true, erosion: 0.2 },
    detail: { octaves: 5, frequency: 26, gain: 0.55, lacunarity: 2.25 },
    mountainWeight: 0.7,
    detailWeight: 0.2,
    seaFraction: 0,
  },
};

/** Instancie le FBM d'une couche d'un profil. */
export function fbmFromProfile(profileName, layer, seed, extra = {}) {
  const profile = NOISE_PROFILES[profileName] || NOISE_PROFILES.continental;
  const cfg = profile[layer] || profile.continents;
  return new FBM({ ...cfg, ...extra, seed });
}

export function getProfile(profileName) {
  return NOISE_PROFILES[profileName] || NOISE_PROFILES.continental;
}
