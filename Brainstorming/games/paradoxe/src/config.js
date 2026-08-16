/**
 * PARADOXE - tuning constants.
 *
 * Every number that shapes the simulation lives here so the deterministic
 * replay stays reproducible: changing a value invalidates recordings, so the
 * whole set is versioned by SIM.version and stored progress is keyed on it.
 */

export const GAME_ID = 'paradoxe';
export const STORAGE = {
  progress: 'paradoxe.progress',
  best: 'paradoxe.best',
  options: 'paradoxe.options',
};

export const SIM = {
  version: 3,
  /** Fixed simulation step. Non negotiable: replay accuracy depends on it. */
  dt: 1 / 60,
  hz: 60,
  /** Wall clock time allowed to be spent catching up simulation in one frame. */
  maxStepsPerFrame: 6,
  /** Rewind animation length in seconds. */
  rewindTime: 0.6,
  /** Ticks of slack allowed between a recorded event and its replay. */
  eventTolerance: 22,
  /** Position drift (world units) tolerated before a clone is called blocked. */
  driftRadius: 2.2,
  /** How long the drift must last before it becomes a paradox. */
  driftTicks: 36,
  /** Below this height a body has fallen out of the arena. */
  killY: -3.5,
  maxActors: 7,
  maxCrates: 8,
};

export const PLAYER = {
  halfWidth: 0.33,
  height: 0.9,
  /** Ground acceleration and top speed. */
  accel: 46,
  airAccel: 18,
  maxSpeed: 4.35,
  groundFriction: 26,
  airFriction: 1.4,
  gravity: 22,
  /** 7.6 m/s gives a 1.31 apex: clears a 1.0 block, never a 2.0 plateau alone. */
  jumpSpeed: 7.6,
  /** Grace ticks after leaving the ground during which a jump still fires. */
  coyoteTicks: 6,
  /** Jump buffered before landing. */
  jumpBufferTicks: 7,
  /** Reach of the interact key. */
  grabRange: 1.15,
  carryHeight: 1.02,
};

export const CRATE = {
  half: 0.37,
  size: 0.74,
  gravity: 22,
};

export const WORLD = {
  cell: 1,
  /**
   * Walls collide up to 3.6 so nothing can ever land on one (the highest reach
   * is 3.31, from a clone standing on a 1 high block), but they are only drawn
   * 2.2 tall so the camera keeps a clear view. Both numbers are read from here.
   */
  wallHeight: 3.6,
  wallVisual: 2.2,
  doorHeight: 2.6,
  /** Ticks between a fragile tile being stepped on and its collapse. */
  fragileTicks: 48,
  teleportCooldown: 26,
};

export const CAMERA = {
  fov: 55,
  near: 0.1,
  far: 260,
  distance: 11.5,
  distanceMin: 6,
  distanceMax: 24,
  pitch: 0.82,
  pitchMin: 0.28,
  pitchMax: 1.32,
  yaw: -0.7,
  /** Chase smoothing, per second. */
  lag: 9,
  height: 1.1,
  sensitivity: 0.0042,
  zoomStep: 1.1,
  /** Key held orbit speed, expressed in drag pixels per second. */
  keyRotate: 430,
  /** Trackpad swipe to drag pixels. Below 1 so a swipe feels calmer than a drag. */
  swipeToDrag: 0.55,
};

/** Input bit layout. One byte per tick, plus one byte of quantised camera yaw. */
export const BIT = {
  forward: 1,
  back: 2,
  left: 4,
  right: 8,
  jump: 16,
  interact: 32,
};

export const KEYS = {
  forward: ['KeyW', 'KeyZ', 'ArrowUp'],
  back: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'KeyQ', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  jump: ['Space'],
  interact: ['KeyE'],
  // Camera orbit without a mouse. I J K L sit at the same physical spot on
  // AZERTY and QWERTY and none of the four is taken by movement, so they orbit
  // with no modifier and no hand leaving the keyboard. The numpad and the
  // page keys are there for whoever reaches for them first.
  camLeft: ['KeyJ', 'Numpad4'],
  camRight: ['KeyL', 'Numpad6'],
  camUp: ['KeyI', 'Numpad8', 'PageUp'],
  camDown: ['KeyK', 'Numpad2', 'PageDown'],
  rewind: ['KeyR'],
  restart: ['KeyT'],
  undo: ['KeyZ'], // only with Ctrl held, handled in input.js
  pause: ['Escape'],
  mute: ['KeyM'],
};

export const PALETTE = {
  bgTop: 0x0a1826,
  bgBottom: 0x05090f,
  fog: 0x0b1a26,
  floor: 0x2a4050,
  block: 0x35566a,
  wall: 0x1d2f3c,
  accent: 0x37d7ff,
  accentWarm: 0xffb347,
  player: 0x4ff2ff,
  exit: 0x7dff9e,
  crate: 0xd79a4a,
  door: 0xff5f7e,
  plate: 0xc57bff,
  fragile: 0x8fa0ad,
  /** Clone tints, newest first. Oldest clones are faded toward the last entry. */
  clones: [0x8be9ff, 0x9b8bff, 0xff8bd2, 0xffd08b, 0x8bffc4],
};

export const AUDIO = {
  master: 0.55,
};
