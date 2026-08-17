/**
 * MAREE - shared constants.
 *
 * One place for the numbers that both the pure simulation and the render layer
 * need to agree on, so a grid coordinate always maps to the same world position
 * whichever module reads it.
 */

// One grid cell in world units. Also the vertical rise of one water "cran".
export const CELL = 1.7;

// The explorer occupies three vertical cells for submersion classification:
// feet, torso/neck, head. This is what "water reaches the neck" (cran+1) and
// "fully submerged" (cran+2 and above) are measured against in world.js.
export const BODY_CELLS = 3;

// Simulation seconds a basin must hold one level before it freezes solid.
export const FREEZE_HOLD_TIME = 2.0;

// Simulation seconds the explorer can stay fully submerged before drowning.
export const DROWN_TIME = 3.0;

// Visual water level catches up to the logical target at this many crans per
// second, so every single step change takes about half a second on screen.
export const WATER_VISUAL_SPEED = 2.0;

// One walk/swim step between two adjacent columns takes this long.
export const WALK_STEP_TIME = 0.42;
export const SWIM_STEP_TIME = 0.62;

export const KEY_PROGRESS = 'maree.progress';
export const KEY_AUDIO = 'maree.audio';

export const PALETTE = {
  rock: 0x6b6558,
  rockDark: 0x4a463c,
  wood: 0xb98a52,
  stone: 0x565a5f,
  ice: 0xbfe7ea,
  waterShallow: 0x2fb2c6,
  waterDeep: 0x0d3c56,
  exit: 0xffce4a,
  gateClosed: 0xaa4a3a,
  gateOpen: 0x4ad06a,
  fog: 0x0a1c22,
};
