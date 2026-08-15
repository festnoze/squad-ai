// Biomes et palettes. Les couleurs sont declarees en sRGB (lisible) puis
// converties en lineaire, car three travaille en espace lineaire et applique
// lui-meme la conversion de sortie.
//
// Aucune dependance a three : utilisable dans un worker.

export const BIOME_ID = {
  DEEP_OCEAN: 0,
  SHALLOW_OCEAN: 1,
  BEACH: 2,
  GRASS: 3,
  FOREST: 4,
  JUNGLE: 5,
  SAVANNA: 6,
  DESERT: 7,
  ROCK: 8,
  SNOW: 9,
  ICE: 10,
  LAVA: 11,
  ASH: 12,
};

export const BIOMES = [
  { id: 0, key: 'DEEP_OCEAN', name: 'Abysse', water: true },
  { id: 1, key: 'SHALLOW_OCEAN', name: 'Haut-fond', water: true },
  { id: 2, key: 'BEACH', name: 'Littoral', water: false },
  { id: 3, key: 'GRASS', name: 'Prairie', water: false },
  { id: 4, key: 'FOREST', name: 'Foret', water: false },
  { id: 5, key: 'JUNGLE', name: 'Jungle', water: false },
  { id: 6, key: 'SAVANNA', name: 'Savane', water: false },
  { id: 7, key: 'DESERT', name: 'Desert', water: false },
  { id: 8, key: 'ROCK', name: 'Roche nue', water: false },
  { id: 9, key: 'SNOW', name: 'Neige', water: false },
  { id: 10, key: 'ICE', name: 'Glace', water: false },
  { id: 11, key: 'LAVA', name: 'Lave', water: false },
  { id: 12, key: 'ASH', name: 'Cendres', water: false },
];

/** Biomes ou de la vegetation peut pousser. */
export const VEGETATION_BIOMES = new Set([
  BIOME_ID.GRASS,
  BIOME_ID.FOREST,
  BIOME_ID.JUNGLE,
  BIOME_ID.SAVANNA,
]);

/** Biomes ou la faune terrestre peut paitre. */
export const FAUNA_BIOMES = new Set([
  BIOME_ID.GRASS,
  BIOME_ID.FOREST,
  BIOME_ID.JUNGLE,
  BIOME_ID.SAVANNA,
  BIOME_ID.BEACH,
]);

// Ordre des couleurs : identique a BIOMES.
const SRGB_PALETTES = {
  earthlike: ['0a2a4a', '1b6fa0', 'd8c89a', '5f8f45', '2f5d2e', '1e6b34', 'a89a52', 'd2b478', '7a7268', 'f2f5f8', 'cfe6f2', 'ff5a1e', '3a3632'],
  garden: ['06283f', '1c86a8', 'e2d6a8', '6fbf52', '2f7a3c', '1f8f4a', 'b8c25a', 'cfc188', '8a7f70', 'ffffff', 'd9f0ff', 'ff6a2a', '46403a'],
  dying: ['3a4a52', '6a7a72', 'b9a888', '8a8a5e', '6a6a4a', '5e6a4a', 'a09068', 'b8a480', '6e685e', 'e8eaec', 'c8d4da', 'a04020', '4a453e'],
  oceanic: ['052033', '0f7fa8', 'cfd8b0', '56a06a', '2b6d4a', '1d7a52', '8fae6a', 'b8b888', '6a7278', 'f0f6fa', 'bfe0f0', 'ff5a1e', '38403e'],
  desert: ['2a3a3a', '4a7a6a', 'e6d2a0', 'a89a4a', '6a7a3a', '5a7a3a', 'c8a860', 'e0bd7a', '9a7a58', 'f4f0e8', 'dce8ee', 'ff6a20', '5a4a3a'],
  inferno: ['3a0c04', '7a1c06', '4a2a1a', '5a3a20', '4a2a18', '3a2214', '6a4020', '8a5228', '3a2a24', '6a5a52', '8a7a70', 'ff8c1a', '241c18'],
  volcanic: ['1a2028', '3a5a5a', '4a4038', '6a7a42', '3a5a2e', '2e5a32', '8a7a44', '9a7a50', '4a4038', 'e8e8ea', 'c8d8e0', 'ff7a12', '2a2422'],
  tundra: ['0a2438', '2a6a86', 'b8b4a0', '6a7a52', '35563c', '2e5a44', '8a8460', 'a09a78', '74706a', 'f6f9fb', 'cfe8f6', 'ff5a1e', '3e3a36'],
  glacial: ['06283c', '2f7fa8', 'cfd8de', '8aa090', '4a6a5a', '3a5a4a', '9aa090', 'b0b4b0', '7a8288', 'ffffff', 'dff2ff', 'ff5a1e', '40464a'],
  barren: ['14181c', '2a3238', '6a6660', '6e6a5e', '55524a', '4a4842', '7a7466', '8a8478', '5e5a54', 'd8dadc', 'b8c4ca', 'c04a14', '2e2c28'],
  exotic: ['170b3a', '3a2f9a', 'd8c4e0', '6fd0b8', '2f8f8a', '7a2f9a', 'b8d05a', 'c8b0d8', '6a6478', 'f4f0ff', 'd0e8ff', 'ff3a7a', '2a2438'],
};

export const PALETTE_NAMES = Object.keys(SRGB_PALETTES);

function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function hexToLinear(hex, out, offset) {
  const n = parseInt(hex, 16);
  out[offset] = srgbToLinear(((n >> 16) & 255) / 255);
  out[offset + 1] = srgbToLinear(((n >> 8) & 255) / 255);
  out[offset + 2] = srgbToLinear((n & 255) / 255);
}

const cache = new Map();

/** Palette lineaire : Float32Array(13 * 3). */
export function getPalette(name) {
  const key = SRGB_PALETTES[name] ? name : 'earthlike';
  let p = cache.get(key);
  if (p) return p;
  const list = SRGB_PALETTES[key];
  p = new Float32Array(BIOMES.length * 3);
  for (let i = 0; i < BIOMES.length; i++) hexToLinear(list[i], p, i * 3);
  cache.set(key, p);
  return p;
}

/** Palette sRGB 0..255, pratique pour dessiner une minimap sur un canvas 2D. */
export function getPaletteBytes(name) {
  const key = SRGB_PALETTES[name] ? name : 'earthlike';
  const list = SRGB_PALETTES[key];
  const out = new Uint8Array(BIOMES.length * 3);
  for (let i = 0; i < BIOMES.length; i++) {
    const n = parseInt(list[i], 16);
    out[i * 3] = (n >> 16) & 255;
    out[i * 3 + 1] = (n >> 8) & 255;
    out[i * 3 + 2] = n & 255;
  }
  return out;
}

export function biomeName(id) {
  return (BIOMES[id] || BIOMES[8]).name;
}

export function isWaterBiome(id) {
  return id === BIOME_ID.DEEP_OCEAN || id === BIOME_ID.SHALLOW_OCEAN;
}
