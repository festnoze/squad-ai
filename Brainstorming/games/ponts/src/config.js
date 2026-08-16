/**
 * PONTS DE FORTUNE - tuning constants.
 *
 * Every number the rest of the game reads lives here. Units are SI: metres,
 * seconds, kilograms, newtons. One three.js unit is one metre.
 */

export const GAME_ID = 'ponts';

export const STORE = {
  progress: 'ponts.progress',
  options: 'ponts.options',
};

// --- geometry -------------------------------------------------------------
export const GRID = 4; // metres between two snap points of the edition plane
export const DECK_Y = 0; // world Y of grid row 0
export const HALF_WIDTH = 2.4; // half the roadway width; the two trusses sit at +/- this
export const RAVINE_DEPTH = 46; // metres from the deck down to the fog

// --- simulation -----------------------------------------------------------
export const SIM = {
  dt: 1 / 120, // fixed substep, never derived from the framerate
  iterations: 20, // gauss-seidel relaxation passes per substep
  gravity: 9.81,
  damping: 0.994, // verlet velocity retention per substep
  maxNodeSpeed: 70, // m/s, catches a diverging node before it becomes NaN
  forceSmooth: 0.22, // low pass on the measured link force
  minNodeMass: 45, // kg, keeps bare nodes from being infinitely nervous
  bucklingRef: 4.0, // metres; longer compression members lose capacity
  bucklingPower: 0.55,
};

/**
 * Buildable materials. `cost` is credits per metre, `capT` / `capC` are the
 * tension and compression capacities in newtons, `stiff` is the per iteration
 * relaxation factor (low = visibly springy).
 */
export const MATERIALS = {
  wood: {
    key: 'wood', name: 'BOIS', slot: 1,
    cost: 2.6, stiff: 0.62, capT: 40000, capC: 46000, density: 22,
    maxLen: 9.0, radius: 0.30, color: 0x8a5a30, hot: 0xd6a061,
    blurb: 'Bon marche. Casse vite, et encore plus vite en longue portee.',
  },
  steel: {
    key: 'steel', name: 'ACIER', slot: 2,
    cost: 7.4, stiff: 0.90, capT: 260000, capC: 290000, density: 45,
    maxLen: 9.0, radius: 0.25, color: 0x78838f, hot: 0xc3ccd6,
    blurb: 'Quatre fois plus solide que le bois. Trois fois plus cher.',
  },
  cable: {
    key: 'cable', name: 'CABLE', slot: 3,
    cost: 0.9, stiff: 0.42, capT: 150000, capC: 0, density: 6,
    maxLen: 26, radius: 0.085, color: 0xa9a289, hot: 0xe8dfbb,
    tensionOnly: true,
    blurb: 'Ne travaille qu en traction. En compression il devient mou.',
  },
  road: {
    key: 'road', name: 'ROUTE', slot: 4,
    cost: 5.0, stiff: 0.66, capT: 45000, capC: 52000, density: 45,
    maxLen: 4.4, radius: 0.34, color: 0x8b939c, hot: 0xd3dbe4,
    horizontalOnly: true,
    blurb: 'Obligatoire pour rouler. Horizontale, une case, et fragile.',
  },
};

export const MATERIAL_ORDER = ['wood', 'steel', 'cable', 'road'];

/** Internal cross bracing between the two trusses. Free, invisible in the budget. */
export const BRACE = {
  stiff: 0.86,
  capT: 900000,
  capC: 900000,
  density: 5,
  radius: 0.07,
  color: 0x5c6068,
};

export const VEHICLES = {
  car: {
    key: 'car', name: 'VOITURE', mass: 1200, length: 4.4, width: 2.0, height: 1.5,
    speed: 8.0, color: 0xc9482f, accent: 0x3d5266,
  },
  truck: {
    key: 'truck', name: 'CAMION', mass: 4800, length: 8.6, width: 2.4, height: 3.1,
    speed: 6.2, color: 0xd39a1c, accent: 0x8d7a5e,
  },
};

export const CONVOY = {
  spacing: 11, // metres between two vehicles at the start
  fallDepth: 14, // metres below the deck before a vehicle counts as lost
  timeout: 45, // seconds before a test is declared failed
  settleTime: 1.2, // seconds of free settling before the convoy starts
};

export const CAMERA = {
  fov: 42,
  near: 0.5,
  far: 2600,
  buildPitch: 0.06, // radians, nearly side on so the plan reads cleanly
  buildYaw: 0.0,
  testPitch: 0.30,
  testYaw: 0.55,
  minDist: 18,
  maxDist: 190,
  minPitch: -0.55,
  maxPitch: 1.30,
  lag: 6.5,
  replayDist: 34,
};

export const REPLAY = {
  hz: 60, // recorded frames per second
  maxFrames: 2400, // hard cap on the ring buffer (40 s)
  lead: 1.6, // seconds shown before the first rupture
  tail: 3.2, // seconds shown after it
  speed: 0.2,
};

export const PALETTE = {
  sky: 0x2b3c52,
  skyLow: 0x6d7f8c,
  fog: 0x8fa0a8,
  rock: 0x6b6257,
  rockDark: 0x3c382f,
  grass: 0x5f6b44,
  amber: 0xf0a63c,
  ink: 0xf2e9d8,
  tension: 0xff6a52,
  compression: 0x63aeff,
  neutral: 0xbfc6cf,
};

export const KEYS = {
  test: ['Space'],
  reset: ['KeyR'],
  undo: ['KeyZ'],
  pause: ['Escape'],
  sideView: ['KeyV'],
  follow: ['KeyC'],
  mute: ['KeyM'],
  material: ['Digit1', 'Digit2', 'Digit3', 'Digit4'],
};
