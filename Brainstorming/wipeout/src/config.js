/**
 * VELOCITRON - shared tuning constants and palette.
 *
 * Every module imports from here instead of hard-coding numbers, so the whole
 * game can be re-balanced or re-skinned from one file. Units are metres,
 * seconds and radians unless the name says otherwise.
 */

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------
export const GAME_TITLE = 'VELOCITRON';
export const TRACK_NAME = 'NEO KYOTO / CIRCUIT AKARI';

// ---------------------------------------------------------------------------
// Palette. Hex integers, ready for THREE.Color / new THREE.Color(PALETTE.x).
// The look is a night circuit: near-black surfaces, saturated neon emissives.
// ---------------------------------------------------------------------------
export const PALETTE = {
  // environment
  night: 0x05060f,
  fog: 0x0a1030,
  skyLow: 0x1a1140,
  skyHigh: 0x03040c,
  ground: 0x0b0c18,
  // track surfaces
  asphalt: 0x14161f,
  asphaltEdge: 0x1d2030,
  wall: 0x0e1018,
  wallTrim: 0x2a2f45,
  // neon accents
  cyan: 0x22e0ff,
  magenta: 0xff2bd6,
  amber: 0xffb020,
  lime: 0x9dff3c,
  violet: 0x7a4dff,
  red: 0xff3b30,
  white: 0xdff6ff,
  // craft liveries, index 0 is the player
  liveries: [0x22e0ff, 0xff2bd6, 0x9dff3c, 0xffb020],
  // background city. The skyline must stay readable without ever competing
  // with the track neon, so these are dim by design.
  cityWarm: 0xffb37a, // lit window, warm interior
  cityCold: 0x9fd8ff, // lit window, cold office
  cityGreen: 0x7effc8, // lit window, third tint
  citySign: 0xff4d9e, // facade signage
  street: 0x191d2e, // avenue tarmac seen from above
  streetLight: 0xffc98a, // sodium street lighting
  rock: 0x1b1a26, // mesa and cliff base colour
  haze: 0x2a2350, // low cloud deck lit from below by the city
  moon: 0xdfe8ff,
  // thruster flame core -> tip
  thrustCore: 0xbdf3ff,
  thrustTip: 0x2b6bff,
  boostCore: 0xfff2c0,
  boostTip: 0xff7a18,
};

// ---------------------------------------------------------------------------
// Track. See track.js for the geometry contract.
// ---------------------------------------------------------------------------
export const TRACK = {
  targetLength: 4200, // approximate centreline length, metres
  sampleSpacing: 2.0, // metres between resampled frames
  halfWidthDefault: 11, // metres from centreline to wall
  halfWidthMin: 8,
  halfWidthMax: 15,
  wallHeight: 4.2,
  wallThickness: 0.6,
  roadColumns: 8, // cross-track quads per sample
  edgeStripWidth: 0.9,
  boostPadLength: 26,
  boostPadHalfWidth: 4.5,
  gantrySpacing: 240, // metres between overhead arches
  lightStripSpacing: 12, // metres between wall light pods
  checkpointCount: 3, // plus the start line, evenly spaced, anti-cheat
};

// ---------------------------------------------------------------------------
// Craft handling. Arcade anti-gravity model, tuned for the track-space
// integrator described in CONTRACTS.md.
// ---------------------------------------------------------------------------
export const SHIP = {
  length: 5.2,
  width: 3.0,
  height: 1.3,
  halfWidth: 1.5, // collision half width against the walls

  hoverHeight: 1.25,
  hoverStiffness: 42, // spring accel per metre of error
  hoverDamping: 9,
  gravity: 26,

  thrust: 78, // m/s^2 at full throttle, scaled by the speed curve
  brakeForce: 62,
  reverseSpeed: -14,
  drag: 0.00072, // quadratic, applied to forward speed
  rollingDrag: 1.4, // linear
  maxSpeed: 148, // m/s, ~533 km/h
  boostMaxSpeed: 196, // m/s, ~705 km/h

  steerRate: 1.9, // rad/s of yaw authority at low speed
  steerSpeedFalloff: 0.3, // fraction of authority kept at max speed
  steerRamp: 4.5, // how fast the keyboard axis reaches full lock, per second
  yawDamping: 3.4, // how hard the craft snaps back to the track tangent
  gripLateral: 5.6, // lateral velocity bleed per second
  slideFromYaw: 0.42, // how much yaw converts into lateral drift
  // Centrifugal load, as a fraction of v^2 * curvature. This is the constant
  // that decides how much a corner costs; at 0 the whole circuit is flat out.
  corneringLoad: 0.8,

  airbrakeYaw: 1.0, // extra yaw rate while an airbrake is held
  airbrakeDrag: 0.32, // fraction of speed bled per second on a full airbrake
  airbrakeSlide: 25, // outward lateral push, m/s^2

  boostAccel: 96,
  boostDuration: 1.9, // seconds per activation
  boostCost: 34, // energy units per activation, out of 100
  boostRegen: 7.5, // energy per second
  padBoostDuration: 1.35,
  padBoostAccel: 120,

  shieldMax: 100,
  wallDamageScale: 0.34, // damage per m/s of impact speed into a wall
  wallSpeedLoss: 0.45, // fraction of speed lost on a hard hit
  wallScrapeDrag: 26,
  shipDamageScale: 0.14, // shield per m/s on a genuine hull to hull impact
  shipRubScale: 6, // shield per second while two hulls stay in contact
  respawnTime: 2.2,

  // cosmetic body attitude
  bankPerSteer: 0.5, // radians of roll at full steer
  bankPerSlide: 0.02,
  pitchPerAccel: 0.012,
  bodyLerp: 6.5,
};

// ---------------------------------------------------------------------------
// Race rules
// ---------------------------------------------------------------------------
export const RACE = {
  laps: 3,
  rivals: 3,
  gridSpacing: 12, // metres between grid rows
  gridStagger: 5.5, // lateral offset between the two grid columns
  countdown: 4.0, // seconds, 3 / 2 / 1 / GO
  aiSkill: [0.94, 0.9, 0.86], // per rival, 1 = matches the player's best line
  rubberBand: 0.04, // catch-up assist, fraction of speed
};

// ---------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------
export const CAMERA = {
  fovBase: 74,
  fovAtMaxSpeed: 96,
  near: 0.2,
  far: 9000,
  chaseBack: 11.5,
  chaseUp: 4.0,
  chaseLookAhead: 16,
  chaseLag: 9, // position spring
  chaseRotLag: 7,
  cockpitBack: -0.6,
  cockpitUp: 1.05,
  shakeDecay: 4.5,
};

// ---------------------------------------------------------------------------
// Post processing
// ---------------------------------------------------------------------------
export const POST = {
  bloomThreshold: 1.0,
  bloomStrength: 0.8,
  bloomRadius: 1.0,
  bloomLevels: 5,
  chromaBase: 0.0008,
  chromaAtSpeed: 0.0032,
  vignette: 0.42,
  grain: 0.03,
  // A strong radial blur reads as a smear rather than as speed, and it eats
  // the track detail the player needs to place the craft.
  radialBlurAtSpeed: 0.14,
  exposure: 1.05,
};

// ---------------------------------------------------------------------------
// Controls. AZERTY first: Z accelerate, S brake, Q/D steer, A/E airbrakes.
// QWERTY equivalents are accepted so the game is playable on both layouts.
// Values are KeyboardEvent.code strings.
// ---------------------------------------------------------------------------
export const KEYS = {
  thrust: ['KeyZ', 'KeyW', 'ArrowUp'],
  brake: ['KeyS', 'ArrowDown'],
  left: ['KeyQ', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  // A and E sit either side of ZQSD on AZERTY; Shift works on any layout.
  airbrakeLeft: ['KeyA', 'ShiftLeft'],
  airbrakeRight: ['KeyE', 'ShiftRight'],
  boost: ['Space'],
  respawn: ['KeyR'],
  camera: ['KeyC'],
  mute: ['KeyM'],
  pause: ['Escape', 'KeyP'],
};

export const AUDIO = {
  masterGain: 0.55,
  musicGain: 0.32,
  engineGain: 0.3,
  bpm: 148,
};

export const DEBUG = new URLSearchParams(location.search).has('debug');
