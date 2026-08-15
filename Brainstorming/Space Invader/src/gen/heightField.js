// Champ de hauteur d'une planete : LA source de verite du relief.
// Le worker de terrain et le thread principal importent tous deux ce module,
// ce qui garantit que la collision, le placement de vie et le maillage affiche
// decrivent exactement la meme surface.
//
// Aucune dependance a three.

import { clamp, saturate, smoothstep, tangentBasis } from '../core/math.js';
import { FBM, getProfile } from './noise.js';
import { BIOME_ID, getPalette } from './palettes.js';

const cacheByKey = new Map();

/**
 * @param {object} spec PlanetSpec
 * @returns {HeightField}
 */
export function createHeightField(spec) {
  const key = `${spec.id}:${spec.seed}`;
  const cached = cacheByKey.get(key);
  if (cached) return cached;
  const field = new HeightField(spec);
  cacheByKey.set(key, field);
  return field;
}

class HeightField {
  constructor(spec) {
    this.spec = spec;
    const profile = getProfile(spec.noiseProfile);
    this.profile = profile;
    this.palette = getPalette(spec.palette);

    const s = spec.seed >>> 0;
    this.continents = new FBM({ ...profile.continents, seed: s });
    this.mountains = new FBM({ ...profile.mountains, seed: (s ^ 0x51df3a1b) >>> 0 });
    this.detail = new FBM({ ...profile.detail, seed: (s ^ 0x2f9a7c05) >>> 0 });
    this.humidityNoise = new FBM({
      octaves: 4,
      frequency: 1.6,
      gain: 0.55,
      lacunarity: 2.05,
      warp: 0.4,
      warpFreq: 0.9,
      seed: (s ^ 0x7ab3c11d) >>> 0,
    });
    this.tint = new FBM({ octaves: 3, frequency: 26, gain: 0.5, seed: (s ^ 0x13c9e2f7) >>> 0 });

    this.maxElevation = spec.maxElevation;
    this.minElevation = spec.minElevation;
    this.mountainWeight = profile.mountainWeight;
    this.detailWeight = profile.detailWeight;
    this.isGas = !!spec.isGas;

    const levels = this.isGas ? null : calibrateSeaLevel(this, spec);
    this.seaLevel = levels ? levels.seaLevel : null;
    this._deepThreshold = levels ? levels.deepLevel : 0;
    // On renseigne le spec pour les modules qui n'ont pas le champ de hauteur.
    spec.seaLevel = this.seaLevel;
    this.seaType = spec.seaType;
    this.hasSea = this.seaLevel !== null;

    // L'humidite vient de l'eau liquide : un monde sans mer, ou dont la mer est
    // de lave ou de glace, est sec par construction.
    this.wetness =
      spec.seaType === 'water' ? 1 : spec.seaType === 'ice' ? 0.55 : spec.seaType === 'lava' ? 0.18 : 0.12;
    // Un monde volcanique brule en cendres ; un monde sec cuit en desert.
    this._ashy = spec.type === 'volcanic' || spec.seaType === 'lava';
    // Sans eau du tout, le froid ne fait pas de banquise mais de la caillasse gelee.
    this._dryWorld = !this.hasSea || spec.seaType === 'lava';

    this._shoreBand = this.maxElevation * 0.022;
    this._t = { x: 0, y: 0, z: 0 };
    this._b = { x: 0, y: 0, z: 0 };
  }

  /** Direction unitaire -> elevation signee, en metres autour de spec.radius. */
  elevation(x, y, z) {
    if (this.isGas) return 0;

    const base = this.continents.sample(x, y, z);
    // Accentuation des plateaux continentaux et des bassins.
    const shaped = Math.sign(base) * Math.pow(Math.abs(base), 1.18);
    let elev = shaped >= 0 ? shaped * this.maxElevation * 0.62 : shaped * -this.minElevation * 0.9;

    const landMask = smoothstep(-0.02, 0.32, base);
    if (landMask > 0.001) {
      const ridge = this.mountains.sample(x, y, z); // [0,1]
      elev += ridge * ridge * this.mountainWeight * this.maxElevation * landMask;
    }

    elev += this.detail.sample(x, y, z) * this.detailWeight * this.maxElevation;

    return clamp(elev, this.minElevation, this.maxElevation * 1.15);
  }

  elevationUnit(v) {
    return this.elevation(v.x, v.y, v.z);
  }

  /** Rayon du sol (centre planete -> surface solide). */
  surfaceRadius(v) {
    return this.spec.radius + this.elevation(v.x, v.y, v.z);
  }

  isWater(elev) {
    return this.hasSea && elev < this.seaLevel;
  }

  humidity(x, y, z) {
    const n = this.humidityNoise.sample(x, y, z) * 0.5 + 0.5;
    // Plus humide pres de l'equateur et en bord de mer, plus sec en altitude.
    const lat = Math.abs(y);
    let h = n * (1 - lat * 0.3);
    if (this.hasSea && this.seaType === 'water') {
      const elev = this.elevation(x, y, z);
      const above = (elev - this.seaLevel) / (this.maxElevation || 1);
      h += smoothstep(0.35, 0.0, above) * 0.22;
      h -= smoothstep(0.25, 0.9, above) * 0.3;
    }
    // Pas d'eau liquide, pas de pluie.
    return saturate(h * this.wetness);
  }

  /**
   * 0 = glacial, 1 = brulant.
   * La latitude et l'altitude n'agissent pas par soustraction (ce qui rendait
   * les mondes extremes incoherents aux poles) mais par interpolation vers une
   * temperature polaire proportionnelle a celle de la planete.
   */
  temperature(x, y, z, elev) {
    const base = this.spec.tempNorm;
    const lat = Math.abs(y); // y = sin(latitude) sur la sphere unite
    const polar = base * 0.42;
    let t = base + (polar - base) * (lat * lat * 0.92);
    if (!this.isGas) {
      const above = Math.max(0, (elev - (this.hasSea ? this.seaLevel : 0)) / (this.maxElevation || 1));
      t += (polar - t) * saturate(above * 0.85);
    }
    // Une variation douce pour casser les bandes latitudinales parfaites.
    t += this.humidityNoise.sample(x * 0.6 + 11.3, y * 0.6, z * 0.6) * 0.045;
    return saturate(t);
  }

  biomeId(x, y, z, elev) {
    if (this.isGas) return BIOME_ID.ASH;

    if (this.hasSea && elev < this.seaLevel) {
      if (this.seaType === 'lava') return BIOME_ID.LAVA;
      if (this.seaType === 'ice') return BIOME_ID.ICE;
      return elev < this._deepThreshold ? BIOME_ID.DEEP_OCEAN : BIOME_ID.SHALLOW_OCEAN;
    }

    const t = this.temperature(x, y, z, elev);
    const h = this.humidity(x, y, z);
    const ref = this.hasSea ? this.seaLevel : 0;
    const above = (elev - ref) / (this.maxElevation || 1);

    // Neiges eternelles et calottes.
    if (t < 0.16) {
      if (this._dryWorld) return h > 0.5 ? BIOME_ID.SNOW : BIOME_ID.ROCK;
      return h > 0.36 ? BIOME_ID.ICE : BIOME_ID.SNOW;
    }
    if (t < 0.28) {
      if (this._dryWorld) return above > 0.55 ? BIOME_ID.SNOW : BIOME_ID.ROCK;
      return above > 0.4 || h > 0.42 ? BIOME_ID.SNOW : BIOME_ID.ROCK;
    }

    // Mondes brulants.
    if (t > 0.9) {
      if (!this._ashy) return BIOME_ID.DESERT;
      return h < 0.3 ? BIOME_ID.LAVA : BIOME_ID.ASH;
    }
    if (t > 0.78) return this._ashy ? BIOME_ID.ASH : BIOME_ID.DESERT;

    // Haute montagne.
    if (above > 0.72) return t < 0.5 ? BIOME_ID.SNOW : BIOME_ID.ROCK;
    if (above > 0.52) return BIOME_ID.ROCK;

    // Littoral.
    if (this.hasSea && elev - this.seaLevel < this._shoreBand) return BIOME_ID.BEACH;

    if (h < 0.24) return this._ashy ? BIOME_ID.ASH : BIOME_ID.DESERT;
    if (h < 0.42) return BIOME_ID.SAVANNA;
    if (h < 0.58) return BIOME_ID.GRASS;
    if (h < 0.78) return BIOME_ID.FOREST;
    return t > 0.62 ? BIOME_ID.JUNGLE : BIOME_ID.FOREST;
  }

  /** Couleur lineaire du sol. `out` peut etre un Float32Array ou un tableau. */
  colorAt(x, y, z, elev, out, offset = 0) {
    const id = this.biomeId(x, y, z, elev);
    const p = this.palette;
    const o = id * 3;
    // Variation locale pour eviter les grands aplats.
    const v = 0.9 + this.tint.sample(x, y, z) * 0.16;
    out[offset] = p[o] * v;
    out[offset + 1] = p[o + 1] * v;
    out[offset + 2] = p[o + 2] * v;
    return id;
  }

  /** Normale geometrique par differences finies (eps en metres). */
  normalAt(v, out) {
    const eps = Math.max(1.5, this.spec.radius * 0.00025);
    const t = this._t;
    const b = this._b;
    tangentBasis(v, t, b);
    const r = this.spec.radius;
    const d = eps / r;

    // Deux points voisins sur la sphere, projetes puis eleves.
    const ax = v.x + t.x * d;
    const ay = v.y + t.y * d;
    const az = v.z + t.z * d;
    const al = 1 / Math.hypot(ax, ay, az);
    const aux = ax * al;
    const auy = ay * al;
    const auz = az * al;
    const ar = r + this.elevation(aux, auy, auz);

    const bx = v.x + b.x * d;
    const by = v.y + b.y * d;
    const bz = v.z + b.z * d;
    const bl = 1 / Math.hypot(bx, by, bz);
    const bux = bx * bl;
    const buy = by * bl;
    const buz = bz * bl;
    const br = r + this.elevation(bux, buy, buz);

    const cr = r + this.elevation(v.x, v.y, v.z);

    // Vecteurs tangents reels
    const e1x = aux * ar - v.x * cr;
    const e1y = auy * ar - v.y * cr;
    const e1z = auz * ar - v.z * cr;
    const e2x = bux * br - v.x * cr;
    const e2y = buy * br - v.y * cr;
    const e2z = buz * br - v.z * cr;

    let nx = e1y * e2z - e1z * e2y;
    let ny = e1z * e2x - e1x * e2z;
    let nz = e1x * e2y - e1y * e2x;
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl;
    ny /= nl;
    nz /= nl;
    // Orientation vers l'exterieur.
    if (nx * v.x + ny * v.y + nz * v.z < 0) {
      nx = -nx;
      ny = -ny;
      nz = -nz;
    }
    out.x = nx;
    out.y = ny;
    out.z = nz;
    return out;
  }

  /** 0 = plat, 1 = falaise. */
  slope(x, y, z) {
    const v = { x, y, z };
    const n = { x: 0, y: 0, z: 0 };
    this.normalAt(v, n);
    return saturate(1 - (n.x * x + n.y * y + n.z * z));
  }
}

/**
 * Calibre le niveau de la mer par quantile sur un echantillonnage de Fibonacci
 * (deterministe, meme resultat dans le worker et le thread principal).
 * Renvoie aussi le seuil d'abysse : la mediane des fonds immerges, ce qui donne
 * un partage haut-fond / abysse equilibre quel que soit le relief.
 */
function calibrateSeaLevel(field, spec) {
  if (!spec.seaType || !spec.seaFraction) return null;
  const N = 1400;
  const samples = new Float64Array(N);
  const ga = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = ga * i;
    samples[i] = field.elevation(Math.cos(th) * r, y, Math.sin(th) * r);
  }
  samples.sort();
  const idx = clamp(Math.floor(spec.seaFraction * (N - 1)), 0, N - 1);
  const deepIdx = clamp(Math.floor(spec.seaFraction * 0.45 * (N - 1)), 0, N - 1);
  return { seaLevel: samples[idx], deepLevel: samples[deepIdx] };
}
