/**
 * Procedural PBR texture generation.
 *
 * Each generator writes a height field plus albedo/roughness/AO channels, then a normal
 * map is derived from the height field with a Sobel filter. Everything tiles seamlessly
 * (the noise lattice wraps), so a single 512-1024px set covers kilometres of road or
 * facade without visible repetition once combined with per-instance UV offsets.
 *
 * Textures are cached by key: the city rebuilds materials constantly but only pays for
 * generation once.
 */

import {
  DataTexture, RGBAFormat, UnsignedByteType, RepeatWrapping, LinearFilter,
  LinearMipmapLinearFilter, SRGBColorSpace, NoColorSpace,
} from 'three/webgpu';
import { fbm2, ridged2, worley2, clamp01, smoothstep, mix } from '../core/Noise.js';

const cache = new Map();

function makeTexture(data, size, { srgb = false, aniso = 8 } = {}) {
  const tex = new DataTexture(data, size, size, RGBAFormat, UnsignedByteType);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  tex.magFilter = LinearFilter;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = aniso;
  tex.colorSpace = srgb ? SRGBColorSpace : NoColorSpace;
  tex.needsUpdate = true;
  return tex;
}

/** Sobel height -> tangent-space normal map, packed into RGB with 0.5 bias. */
function heightToNormal(height, size, strength = 2.0) {
  const out = new Uint8Array(size * size * 4);
  const at = (x, y) => height[(((y + size) % size) * size) + ((x + size) % size)];
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const tl = at(x - 1, y - 1), t = at(x, y - 1), tr = at(x + 1, y - 1);
      const l = at(x - 1, y), r = at(x + 1, y);
      const bl = at(x - 1, y + 1), b = at(x, y + 1), br = at(x + 1, y + 1);
      const dx = (tr + 2 * r + br) - (tl + 2 * l + bl);
      const dy = (bl + 2 * b + br) - (tl + 2 * t + tr);
      let nx = -dx * strength, ny = -dy * strength, nz = 1;
      const len = Math.hypot(nx, ny, nz) || 1;
      nx /= len; ny /= len; nz /= len;
      const i = (y * size + x) * 4;
      out[i] = (nx * 0.5 + 0.5) * 255;
      out[i + 1] = (ny * 0.5 + 0.5) * 255;
      out[i + 2] = (nz * 0.5 + 0.5) * 255;
      out[i + 3] = 255;
    }
  }
  return out;
}

/**
 * Cheap ambient occlusion: a wide blur of the inverted height field. Crevices in the
 * height map darken, high points stay lit. Good enough to sell macro depth.
 */
function heightToAO(height, size, radius = 4, power = 1.0) {
  const blurred = new Float32Array(size * size);
  const tmp = new Float32Array(size * size);
  const wrap = (n) => ((n % size) + size) % size;
  const k = radius * 2 + 1;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let s = 0;
      for (let d = -radius; d <= radius; d++) s += height[y * size + wrap(x + d)];
      tmp[y * size + x] = s / k;
    }
  }
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let s = 0;
      for (let d = -radius; d <= radius; d++) s += tmp[wrap(y + d) * size + x];
      blurred[y * size + x] = s / k;
    }
  }
  const ao = new Float32Array(size * size);
  for (let i = 0; i < ao.length; i++) {
    ao[i] = clamp01(0.5 + (height[i] - blurred[i]) * 2.2);
    ao[i] = Math.pow(ao[i], power);
  }
  return ao;
}

/**
 * Build a PBR set from a per-pixel shader function.
 *
 * @param {number} size texture resolution
 * @param {(x:number,y:number,u:number,v:number)=>{h:number,r:number,g:number,b:number,rough:number,metal?:number}} shade
 * @returns {{map:DataTexture, normalMap:DataTexture, roughnessMap:DataTexture, aoMap:DataTexture}}
 */
function buildPBR(size, shade, { normalStrength = 2.0, aoRadius = 4, aoPower = 1.0 } = {}) {
  const height = new Float32Array(size * size);
  const albedo = new Uint8Array(size * size * 4);
  const rough = new Float32Array(size * size);
  const metal = new Float32Array(size * size);

  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const i = y * size + x;
      const s = shade(x, y, x / size, y / size);
      height[i] = s.h;
      albedo[i * 4] = clamp01(s.r) * 255;
      albedo[i * 4 + 1] = clamp01(s.g) * 255;
      albedo[i * 4 + 2] = clamp01(s.b) * 255;
      albedo[i * 4 + 3] = 255;
      rough[i] = clamp01(s.rough);
      metal[i] = clamp01(s.metal ?? 0);
    }
  }

  const ao = heightToAO(height, size, aoRadius, aoPower);

  // Pack roughness in G, metalness in B, AO in R - the three-channel convention
  // MeshStandardMaterial reads when the same texture is bound to all three slots.
  const ormData = new Uint8Array(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    ormData[i * 4] = ao[i] * 255;
    ormData[i * 4 + 1] = rough[i] * 255;
    ormData[i * 4 + 2] = metal[i] * 255;
    ormData[i * 4 + 3] = 255;
  }

  const orm = makeTexture(ormData, size);
  return {
    map: makeTexture(albedo, size, { srgb: true }),
    normalMap: makeTexture(heightToNormal(height, size, normalStrength), size),
    roughnessMap: orm,
    metalnessMap: orm,
    aoMap: orm,
  };
}

/* ------------------------------------------------------------------ generators */

const GENERATORS = {
  /** Worn asphalt: aggregate speckle, tar patches, hairline cracks, oil sheen. */
  asphalt(size) {
    return buildPBR(size, (x, y, u, v) => {
      const grit = fbm2(u * 96, v * 96, { octaves: 4, period: 96, seed: 11 });
      const agg = worley2(u * 42, v * 42, 42, 7).f1;
      const patch = fbm2(u * 5, v * 5, { octaves: 4, period: 5, seed: 91 });
      const crack = smoothstep(0.86, 1.0, ridged2(u * 7, v * 7, { octaves: 4, period: 7, seed: 33 }));
      const oil = smoothstep(0.62, 0.9, fbm2(u * 3 + 4, v * 3, { octaves: 3, period: 3, seed: 5 }));

      let h = grit * 0.35 + (1 - agg) * 0.3 + patch * 0.2;
      h -= crack * 0.55;

      const base = 0.055 + patch * 0.045 + grit * 0.05;
      const speck = agg < 0.14 ? 0.09 : 0;
      let r = base + speck, g = base + speck * 0.96, b = base * 1.06 + speck * 0.92;
      r *= 1 - crack * 0.5; g *= 1 - crack * 0.5; b *= 1 - crack * 0.5;

      // Oil slicks read as darker + far smoother.
      const rough = mix(0.92 - grit * 0.12 - (1 - agg) * 0.08, 0.28, oil);
      r = mix(r, r * 0.55, oil); g = mix(g, g * 0.5, oil); b = mix(b, b * 0.62, oil);

      return { h, r, g, b, rough };
    }, { normalStrength: 2.6, aoRadius: 3 });
  },

  /** Poured concrete: form-work lines, air bubbles, staining, chipped edges. */
  concrete(size) {
    return buildPBR(size, (x, y, u, v) => {
      const grain = fbm2(u * 64, v * 64, { octaves: 5, period: 64, seed: 21 });
      const blotch = fbm2(u * 4, v * 4, { octaves: 4, period: 4, seed: 77 });
      const stain = smoothstep(0.55, 0.95, fbm2(u * 2.2, v * 6, { octaves: 4, period: 8, seed: 44 }));
      const bubble = worley2(u * 30, v * 30, 30, 3);
      const pit = bubble.f1 < 0.09 ? 1 : 0;

      let h = grain * 0.3 + blotch * 0.35 - pit * 0.7;
      const l = 0.5 + blotch * 0.16 + grain * 0.08 - stain * 0.14 - pit * 0.1;
      return {
        h,
        r: l * 1.0, g: l * 0.99, b: l * 0.95,
        rough: 0.78 - blotch * 0.1 + stain * 0.08,
      };
    }, { normalStrength: 1.5, aoRadius: 5 });
  },

  /** Running-bond brick with mortar recess and per-brick colour variation. */
  brick(size) {
    const rows = 16, bricksPerRow = 8;
    const mortar = 0.055;
    return buildPBR(size, (x, y, u, v) => {
      const row = Math.floor(v * rows);
      const offset = (row % 2) * 0.5;
      const bu = ((u * bricksPerRow + offset) % 1);
      const bv = (v * rows) % 1;
      const inMortar = bu < mortar * bricksPerRow || bu > 1 - mortar * bricksPerRow
        || bv < mortar * rows * 0.5 || bv > 1 - mortar * rows * 0.5;

      const brickId = Math.floor(u * bricksPerRow + offset) * 31 + row * 17;
      const tint = ((brickId * 2654435761) % 1000) / 1000;
      const grain = fbm2(u * 110, v * 110, { octaves: 4, period: 110, seed: 8 });

      if (inMortar) {
        const l = 0.44 + grain * 0.1;
        return { h: 0.15 + grain * 0.1, r: l, g: l * 0.98, b: l * 0.94, rough: 0.85 };
      }
      const warm = 0.34 + tint * 0.16;
      return {
        h: 0.72 + grain * 0.14,
        r: warm + 0.14, g: warm * 0.52 + grain * 0.04, b: warm * 0.4 + grain * 0.03,
        rough: 0.72 - grain * 0.1,
      };
    }, { normalStrength: 3.4, aoRadius: 4, aoPower: 1.2 });
  },

  /** Glass curtain wall: mullion grid, subtle pane distortion, tinted low-roughness glass. */
  curtainWall(size) {
    const cols = 8, rows = 6;
    return buildPBR(size, (x, y, u, v) => {
      const cu = (u * cols) % 1, cv = (v * rows) % 1;
      const frame = 0.07;
      const isFrame = cu < frame || cu > 1 - frame || cv < frame || cv > 1 - frame;
      const paneId = Math.floor(u * cols) * 13 + Math.floor(v * rows) * 7;
      const lit = ((paneId * 2246822519) % 100) / 100;
      const dirt = fbm2(u * 24, v * 24, { octaves: 3, period: 24, seed: 61 });

      if (isFrame) {
        const l = 0.16 + dirt * 0.05;
        return { h: 0.85, r: l, g: l * 1.02, b: l * 1.08, rough: 0.42, metal: 0.9 };
      }
      // Panes vary between near-black reflective and faintly lit interiors.
      const base = 0.035 + lit * 0.05;
      return {
        h: 0.3 + dirt * 0.05,
        r: base * 0.8, g: base * 1.0, b: base * 1.35,
        rough: 0.06 + dirt * 0.07,
        metal: 0.35,
      };
    }, { normalStrength: 2.2, aoRadius: 3 });
  },

  /** Sidewalk: square paving slabs with chamfered joints and gum stains. */
  sidewalk(size) {
    const n = 6;
    return buildPBR(size, (x, y, u, v) => {
      const su = (u * n) % 1, sv = (v * n) % 1;
      const joint = 0.035;
      const edge = Math.min(su, 1 - su, sv, 1 - sv);
      const inJoint = edge < joint;
      const slabId = Math.floor(u * n) * 23 + Math.floor(v * n) * 41;
      const tint = ((slabId * 1274126177) % 100) / 100;
      const grain = fbm2(u * 90, v * 90, { octaves: 4, period: 90, seed: 15 });
      const gum = worley2(u * 12, v * 12, 12, 19).f1 < 0.05 ? 1 : 0;

      if (inJoint) {
        const l = 0.3 + grain * 0.08;
        return { h: 0.1, r: l, g: l, b: l * 0.98, rough: 0.9 };
      }
      const l = 0.52 + tint * 0.08 + grain * 0.07 - gum * 0.28;
      return {
        h: 0.7 + grain * 0.12 + smoothstep(joint, joint * 2.4, edge) * 0.12,
        r: l, g: l * 0.995, b: l * 0.97,
        rough: 0.8 - grain * 0.08,
      };
    }, { normalStrength: 2.8, aoRadius: 4 });
  },

  /** Beach sand: fine grain with wind ripples. */
  sand(size) {
    return buildPBR(size, (x, y, u, v) => {
      const ripple = Math.sin((u * 26 + fbm2(u * 3, v * 3, { period: 3, seed: 2 }) * 6) * Math.PI * 2) * 0.5 + 0.5;
      const grain = fbm2(u * 128, v * 128, { octaves: 4, period: 128, seed: 31 });
      const dune = fbm2(u * 6, v * 6, { octaves: 4, period: 6, seed: 12 });
      const h = ripple * 0.3 + grain * 0.25 + dune * 0.45;
      const l = 0.6 + dune * 0.12 + grain * 0.08;
      return { h, r: l * 1.0, g: l * 0.9, b: l * 0.71, rough: 0.88 - grain * 0.06 };
    }, { normalStrength: 2.0, aoRadius: 3 });
  },

  /** Grass / park turf: clumped blades, dry patches, dirt showing through. */
  grass(size) {
    return buildPBR(size, (x, y, u, v) => {
      const blade = fbm2(u * 150, v * 150, { octaves: 3, period: 150, seed: 51 });
      const clump = fbm2(u * 14, v * 14, { octaves: 4, period: 14, seed: 71 });
      const dry = smoothstep(0.58, 0.9, fbm2(u * 4, v * 4, { octaves: 3, period: 4, seed: 3 }));
      const h = blade * 0.5 + clump * 0.5;
      const green = 0.2 + clump * 0.14 + blade * 0.07;
      return {
        h,
        r: mix(green * 0.5, green * 1.5, dry),
        g: mix(green * 1.25, green * 1.25, dry),
        b: mix(green * 0.35, green * 0.6, dry),
        rough: 0.9,
      };
    }, { normalStrength: 1.6, aoRadius: 5, aoPower: 1.3 });
  },

  /** Brushed / painted metal panel for vehicles, containers, guard rails. */
  metalPanel(size) {
    return buildPBR(size, (x, y, u, v) => {
      const brush = fbm2(u * 400, v * 12, { octaves: 3, period: 400, seed: 91 });
      const scuff = smoothstep(0.7, 1.0, fbm2(u * 30, v * 30, { octaves: 4, period: 30, seed: 17 }));
      const l = 0.55 + brush * 0.12 - scuff * 0.1;
      return {
        h: brush * 0.6 + scuff * 0.4,
        r: l, g: l * 1.01, b: l * 1.03,
        rough: 0.24 + brush * 0.14 + scuff * 0.35,
        metal: 1 - scuff * 0.25,
      };
    }, { normalStrength: 1.0, aoRadius: 3 });
  },

  /** Corrugated steel for warehouses and dock sheds. */
  corrugated(size) {
    return buildPBR(size, (x, y, u, v) => {
      const wave = Math.sin(u * Math.PI * 2 * 22) * 0.5 + 0.5;
      const rust = smoothstep(0.6, 0.95, fbm2(u * 8, v * 8, { octaves: 4, period: 8, seed: 41 }));
      const grime = fbm2(u * 3, v * 9, { octaves: 3, period: 9, seed: 5 });
      const l = 0.42 + wave * 0.12 - grime * 0.08;
      return {
        h: wave,
        r: mix(l, 0.36, rust), g: mix(l * 1.02, 0.17, rust), b: mix(l * 1.05, 0.09, rust),
        rough: mix(0.4, 0.92, rust),
        metal: mix(0.85, 0.15, rust),
      };
    }, { normalStrength: 4.0, aoRadius: 3 });
  },

  /** Weathered timber for docks and jetties. */
  wood(size) {
    return buildPBR(size, (x, y, u, v) => {
      const rings = fbm2(u * 3, v * 60, { octaves: 4, period: 60, seed: 23 });
      const plank = Math.floor(v * 8);
      const seam = ((v * 8) % 1 < 0.03 || (v * 8) % 1 > 0.97) ? 1 : 0;
      const tint = ((plank * 2654435761) % 100) / 100;
      const l = 0.28 + rings * 0.16 + tint * 0.06 - seam * 0.2;
      return {
        h: rings * 0.7 - seam * 0.5,
        r: l * 1.25, g: l * 1.0, b: l * 0.76,
        rough: 0.82 + rings * 0.08,
      };
    }, { normalStrength: 2.4, aoRadius: 4 });
  },

  /** Roof: gravel ballast + tar seams, seen from the air constantly in a city game. */
  roof(size) {
    return buildPBR(size, (x, y, u, v) => {
      const gravel = worley2(u * 55, v * 55, 55, 13);
      const tar = fbm2(u * 6, v * 6, { octaves: 4, period: 6, seed: 87 });
      const l = 0.2 + (1 - gravel.f1) * 0.16 + tar * 0.1 + gravel.id * 0.06;
      return {
        h: (1 - gravel.f1) * 0.7 + tar * 0.3,
        r: l, g: l * 0.98, b: l * 0.95,
        rough: 0.88,
      };
    }, { normalStrength: 3.0, aoRadius: 3 });
  },
};

/** Water normal map for `WaterMesh` - two crossed wave trains, seamless. */
export function makeWaterNormals(size = 512) {
  const key = `waterNormals:${size}`;
  if (cache.has(key)) return cache.get(key);
  const height = new Float32Array(size * size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size, v = y / size;
      const a = fbm2(u * 8, v * 8, { octaves: 5, period: 8, seed: 101 });
      const b = fbm2(v * 5 + 3, u * 5, { octaves: 4, period: 5, seed: 202 });
      height[y * size + x] = a * 0.6 + b * 0.4;
    }
  }
  const tex = makeTexture(heightToNormal(height, size, 1.4), size, { aniso: 4 });
  cache.set(key, tex);
  return tex;
}

/**
 * Get (and memoise) a PBR texture set.
 * @param {keyof typeof GENERATORS} name
 * @param {number} size
 */
export function getPBR(name, size = 512) {
  const key = `${name}:${size}`;
  if (cache.has(key)) return cache.get(key);
  const gen = GENERATORS[name];
  if (!gen) throw new Error(`Unknown texture generator: ${name}`);
  const set = gen(size);
  cache.set(key, set);
  return set;
}

export const TEXTURE_NAMES = Object.keys(GENERATORS);

export function disposeTextures() {
  for (const v of cache.values()) {
    if (v.dispose) v.dispose();
    else for (const t of Object.values(v)) t.dispose?.();
  }
  cache.clear();
}
