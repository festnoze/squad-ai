/**
 * Deterministic noise primitives used by the procedural texture/terrain generators.
 * Everything is seeded integer hashing, so a given seed always rebuilds the same world.
 */

/** Mulberry32 - small, fast, good enough for content generation. */
export function makeRng(seed = 1) {
  let a = seed >>> 0;
  return function rng() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hash2(x, y, seed) {
  let h = Math.imul(x, 374761393) ^ Math.imul(y, 668265263) ^ Math.imul(seed, 2246822519);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function hash3(x, y, seed) {
  // Returns two decorrelated values in [0,1) - used for Worley feature points.
  const a = hash2(x, y, seed);
  const b = hash2(x + 7919, y - 104729, seed ^ 0x9e3779b9);
  return [a, b];
}

const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
const lerp = (a, b, t) => a + (b - a) * t;

/** Value noise in [0,1], smooth quintic interpolation. */
export function valueNoise2(x, y, seed = 0) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = fade(xf), v = fade(yf);
  const n00 = hash2(xi, yi, seed);
  const n10 = hash2(xi + 1, yi, seed);
  const n01 = hash2(xi, yi + 1, seed);
  const n11 = hash2(xi + 1, yi + 1, seed);
  return lerp(lerp(n00, n10, u), lerp(n01, n11, u), v);
}

/** Tiling value noise - wraps on a `period` lattice so textures repeat seamlessly. */
export function tilingValueNoise2(x, y, period, seed = 0) {
  const wrap = (n) => ((n % period) + period) % period;
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = fade(xf), v = fade(yf);
  const x0 = wrap(xi), x1 = wrap(xi + 1);
  const y0 = wrap(yi), y1 = wrap(yi + 1);
  const n00 = hash2(x0, y0, seed);
  const n10 = hash2(x1, y0, seed);
  const n01 = hash2(x0, y1, seed);
  const n11 = hash2(x1, y1, seed);
  return lerp(lerp(n00, n10, u), lerp(n01, n11, u), v);
}

/** Fractal Brownian motion over tiling value noise. Returns [0,1]. */
export function fbm2(x, y, { octaves = 5, lacunarity = 2, gain = 0.5, period = 8, seed = 0 } = {}) {
  let amp = 1, freq = 1, sum = 0, norm = 0;
  let p = period;
  for (let o = 0; o < octaves; o++) {
    sum += amp * tilingValueNoise2(x * freq, y * freq, p, seed + o * 1013);
    norm += amp;
    amp *= gain;
    freq *= lacunarity;
    p *= lacunarity;
  }
  return sum / norm;
}

/** Ridged multifractal - good for mountains and cracked surfaces. */
export function ridged2(x, y, opts = {}) {
  const { octaves = 5, lacunarity = 2, gain = 0.5, period = 8, seed = 0 } = opts;
  let amp = 1, freq = 1, sum = 0, norm = 0, p = period;
  for (let o = 0; o < octaves; o++) {
    const n = tilingValueNoise2(x * freq, y * freq, p, seed + o * 7717);
    const r = 1 - Math.abs(n * 2 - 1);
    sum += amp * r * r;
    norm += amp;
    amp *= gain;
    freq *= lacunarity;
    p *= lacunarity;
  }
  return sum / norm;
}

/**
 * Tiling Worley (cellular) noise. Returns { f1, f2, id } where f1 is the distance to the
 * nearest feature point, normalised to roughly [0,1]. Used for pebbles, gravel, cracks.
 */
export function worley2(x, y, period, seed = 0) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const wrap = (n) => ((n % period) + period) % period;
  let f1 = 8, f2 = 8, id = 0;
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const cx = xi + dx, cy = yi + dy;
      const [ox, oy] = hash3(wrap(cx), wrap(cy), seed);
      const px = cx + ox, py = cy + oy;
      const d = Math.hypot(px - x, py - y);
      if (d < f1) { f2 = f1; f1 = d; id = hash2(wrap(cx), wrap(cy), seed ^ 555); }
      else if (d < f2) { f2 = d; }
    }
  }
  return { f1: Math.min(1, f1), f2: Math.min(1, f2), id };
}

export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const smoothstep = (e0, e1, x) => {
  const t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};
export const mix = lerp;
