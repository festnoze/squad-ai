/**
 * VELOCITRON - rival pilot AI.
 *
 * A rival is a pure controller: it reads the world (its own ship state, the
 * track, the other craft) and fills the `controls` object it owns. It never
 * writes a single field of the ship physics state - `ship.js` stays the only
 * author of that.
 *
 * Two stages:
 *
 *  1. At construction, a full racing line is baked per track sample: a
 *     smoothed curvature, a target lateral offset that swings wide on corner
 *     entry and cuts to the apex, and a target speed from the classic
 *     sqrt(lateralGrip / curvature). Everything that only depends on the track
 *     is computed once and shared between the three rivals through a WeakMap;
 *     only the per-pilot noise and the skill scaling are duplicated.
 *
 *  2. Every frame, a look-ahead scan picks the speed the craft may carry right
 *     now, a PD controller aims the nose at the baked line, and a handful of
 *     rules add ship avoidance, airbrakes, turbo and the occasional mistake.
 *
 * There is no per-frame allocation: the arrays are baked once, the scratch
 * frame belongs to the AI instance (never shared, so it cannot be clobbered by
 * a nested call) and everything else is a local number.
 */

import * as THREE from 'three';
import { SHIP, RACE, TRACK } from './config.js';

const clamp = THREE.MathUtils.clamp;
const lerp = THREE.MathUtils.lerp;

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

// ---------------------------------------------------------------------------
// Tuning
// ---------------------------------------------------------------------------

// Racing line shaping
const SMOOTH_AHEAD = 60; // metres of curvature averaging, "what is coming"
const ENTRY_AHEAD = 55; // metres, how far ahead a corner starts pushing us wide
const EXIT_BEHIND = 45; // metres, how far a corner keeps pushing us wide on exit
const LINE_SMOOTH = 13; // metres, radius of the box filter applied to the line
const LINE_MARGIN = 2.5; // metres kept between the line and the wall
const K_REF = 0.013; // curvature (1/m) at which the apex offset saturates
const ENTRY_GAIN = 0.85;
const EXIT_GAIN = 0.6;

// Speed profile
/**
 * Fastest speed at which the flight model can actually hold a corner of
 * curvature `kAbs`, derived from the ship constants rather than guessed.
 *
 * The craft holds a line when the yaw it can sustain converts enough lateral
 * velocity to cancel the cornering load:
 *     speed * sin(yawMax)  >=  speed^2 * k * corneringLoad / gripLateral
 * yawMax itself depends on the speed through steerSpeedFalloff, so the balance
 * point is found by bisection. Deriving it here is what keeps the rivals from
 * braking for a limit the player does not have (or ignoring one that he does).
 */
function holdableSpeed(kAbs) {
  if (!(kAbs > 1e-5)) return SHIP.maxSpeed;
  let lo = 12;
  let hi = SHIP.maxSpeed;
  for (let i = 0; i < 24; i++) {
    const v = (lo + hi) * 0.5;
    const falloff = 1 + (SHIP.steerSpeedFalloff - 1) * Math.min(1, v / SHIP.maxSpeed);
    const yawMax = Math.min(0.9, (SHIP.steerRate * falloff) / SHIP.yawDamping);
    const need = (v * v * kAbs * SHIP.corneringLoad) / SHIP.gripLateral;
    const have = v * Math.sin(yawMax);
    if (have >= need) lo = v;
    else hi = v;
  }
  return lo;
}
const GRIP_CREST = 55; // vertical acceleration budget over a crest, m/s^2
const CREST_MIN = 0.0008; // ignore vertical curvature flatter than this
const SPEED_FLOOR = 42; // m/s, the AI never targets slower than this
const STRAIGHT_LOOK = 200; // metres scanned to decide "this is a straight"
const STRAIGHT_K = 0.0055; // curvature below which a section counts as straight

// Boost pads
const PAD_LOOK = 70; // metres of approach used to line up on a turbo plate
const PAD_PULL = 0.8; // how strongly the line is dragged onto the plate

// Frame controller
const LOOK_SECONDS = 2.5;
const LOOK_MIN = 45;
const LOOK_MAX = 340;
const LOOK_TAPS = 52;
const LAT_P = 1.35; // lateral error -> desired lateral velocity, 1/s
const LAT_MAX_FRACTION = 0.28; // desired lateral velocity, fraction of speed
const YAW_P = 5.0; // yaw error -> desired yaw rate, 1/s
const AIM_SECONDS = 0.4; // the line is read this far ahead, kills the lag
const AIM_MIN = 8;
const AIM_MAX = 45;
const STEER_SATURATION = 0.86; // above this, an airbrake is added
const BRAKE_DEADBAND = 2.0; // m/s of overspeed tolerated before braking

// Rivals
const AVOID_RANGE = 25; // metres ahead scanned for other craft
const AVOID_LATERAL = 5.5; // metres of lateral overlap that counts as a threat
const AVOID_PUSH = 4.5; // metres the line is displaced at maximum urgency
const AVOID_MAX = 5.5;

// Mistakes
const MISTAKE_RATE = 10; // scaled by (1 - skill)^2, per second in a braking zone
const MISTAKE_MIN = 0.3; // seconds of suppressed braking
const MISTAKE_SPAN = 0.45;
const MISTAKE_COOLDOWN = 11; // seconds, so a rival never looks broken

// Rubber band
// A 260 m range saturated after less than two seconds of gap, so the band was
// active for nearly the whole race and it, not the driving, decided the order.
const BAND_RANGE = 900; // metres of gap for a full rubber band effect

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Deterministic PRNG so a given rival always drives the same line. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Linear read of a periodic per-sample array at a fractional index. */
function sampleRing(arr, n, idx) {
  let i0 = Math.floor(idx);
  const f = idx - i0;
  i0 = ((i0 % n) + n) % n;
  const i1 = i0 + 1 === n ? 0 : i0 + 1;
  const a = arr[i0];
  return a + (arr[i1] - a) * f;
}

/** Sum of `w` consecutive values starting at `i`, wrapping around the loop. */
function ringSum(prefix, n, i, w) {
  const end = i + w;
  if (end <= n) return prefix[end] - prefix[i];
  return prefix[n] - prefix[i] + prefix[end - n];
}

/** In place box blur of a periodic array, radius in samples. */
function ringBlur(arr, n, rawRadius, scratch) {
  const radius = Math.min(rawRadius, (n - 1) >> 1);
  if (radius < 1) return;
  const inv = 1 / (radius * 2 + 1);
  for (let i = 0; i < n; i++) {
    let sum = 0;
    for (let k = -radius; k <= radius; k++) {
      let j = i + k;
      if (j < 0) j += n;
      else if (j >= n) j -= n;
      sum += arr[j];
    }
    scratch[i] = sum * inv;
  }
  arr.set(scratch);
}

// ---------------------------------------------------------------------------
// Track baking, shared by every rival on the same track
// ---------------------------------------------------------------------------

const trackDataCache = new WeakMap();

function getTrackData(track) {
  const cached = trackDataCache.get(track);
  if (cached) return cached;
  const data = bakeTrackData(track);
  trackDataCache.set(track, data);
  return data;
}

function bakeTrackData(track) {
  const n = Math.max(8, track.sampleCount | 0);
  const length = track.length;
  const step = length / n;

  const frame = track.makeFrame();
  const curv = new Float32Array(n); // signed horizontal curvature
  const absCurv = new Float32Array(n);
  const crest = new Float32Array(n); // positive where the road tops out
  const half = new Float32Array(n);
  const limit = new Float32Array(n); // usable half width for the racing line

  for (let i = 0; i < n; i++) {
    track.at(i * step, frame);
    curv[i] = frame.curvature;
    absCurv[i] = Math.abs(frame.curvature);
    crest[i] = Math.max(0, -frame.vertCurvature);
    half[i] = frame.halfWidth;
    limit[i] = Math.max(0.6, frame.halfWidth - LINE_MARGIN);
  }

  // Prefix sums for the moving averages.
  const pCurv = new Float64Array(n + 1);
  const pAbs = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) {
    pCurv[i + 1] = pCurv[i] + curv[i];
    pAbs[i + 1] = pAbs[i] + absCurv[i];
  }

  const win = Math.min(n, Math.max(1, Math.round(SMOOTH_AHEAD / step)));
  const invWin = 1 / win;
  const smooth = new Float32Array(n); // signed, averaged over the window ahead
  const absAvg = new Float32Array(n);
  const absPeak = new Float32Array(n);
  const crestPeak = new Float32Array(n);

  for (let i = 0; i < n; i++) {
    smooth[i] = ringSum(pCurv, n, i, win) * invWin;
    absAvg[i] = ringSum(pAbs, n, i, win) * invWin;
    let peak = 0;
    let cPeak = 0;
    for (let k = 0; k < win; k++) {
      let j = i + k;
      if (j >= n) j -= n;
      if (absCurv[j] > peak) peak = absCurv[j];
      if (crest[j] > cPeak) cPeak = crest[j];
    }
    absPeak[i] = peak;
    crestPeak[i] = cPeak;
  }

  // How "straight" the next couple of hundred metres are, used for the turbo.
  const straightWin = Math.min(n, Math.max(1, Math.round(STRAIGHT_LOOK / step)));
  const straight = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let peak = 0;
    for (let k = 0; k < straightWin; k++) {
      let j = i + k;
      if (j >= n) j -= n;
      if (absCurv[j] > peak) peak = absCurv[j];
    }
    straight[i] = clamp01((STRAIGHT_K * 1.4 - peak) / STRAIGHT_K);
  }

  // Turbo plate centres, scanned once with track.padAt.
  const padX = new Float32Array(n);
  const padHas = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const s = i * step;
    const hw = half[i];
    let runStart = 0;
    let runLen = 0;
    let bestStart = 0;
    let bestLen = 0;
    let inRun = false;
    for (let x = -hw + 0.5; x <= hw - 0.5; x += 1) {
      if (track.padAt(s, x)) {
        if (!inRun) {
          inRun = true;
          runStart = x;
          runLen = 0;
        }
        runLen += 1;
      } else if (inRun) {
        inRun = false;
        if (runLen > bestLen) {
          bestLen = runLen;
          bestStart = runStart;
        }
      }
    }
    if (inRun && runLen > bestLen) {
      bestLen = runLen;
      bestStart = runStart;
    }
    if (bestLen > 0) {
      padHas[i] = 1;
      padX[i] = bestStart + (bestLen - 1) * 0.5;
    }
  }

  // Racing line, normalised in [-1, 1] before the per-pilot scaling.
  const entryOff = Math.max(1, Math.round(ENTRY_AHEAD / step));
  const exitOff = Math.max(1, Math.round(EXIT_BEHIND / step));
  const lineNorm = new Float32Array(n);

  for (let i = 0; i < n; i++) {
    const kNow = smooth[i];
    const iAhead = (i + entryOff) % n;
    const iBehind = (i - exitOff + n) % n;
    const kAhead = smooth[iAhead];
    const kBehind = smooth[iBehind];

    const mNow = clamp01(Math.abs(kNow) / K_REF);
    const mAhead = clamp01(Math.abs(kAhead) / K_REF);
    const mBehind = clamp01(Math.abs(kBehind) / K_REF);

    // Cut to the apex on the inside of the current corner (positive curvature
    // turns right, so the inside is the +x side).
    let v = Math.sign(kNow) * mNow;
    // Swing wide while a corner is still ahead, and let the exit run out wide.
    v -= ENTRY_GAIN * Math.max(0, mAhead - mNow) * Math.sign(kAhead);
    v -= EXIT_GAIN * Math.max(0, mBehind - mNow) * Math.sign(kBehind);
    lineNorm[i] = clamp(v, -1, 1);
  }

  // Drag the line onto the turbo plates when the road ahead is not a corner.
  const padWin = Math.min(n, Math.max(1, Math.round(PAD_LOOK / step)));
  const padded = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    let w = 0;
    let targetNorm = lineNorm[i];
    for (let k = 0; k < padWin; k++) {
      let j = i + k;
      if (j >= n) j -= n;
      if (padHas[j]) {
        const cornering = clamp01(absPeak[i] / K_REF);
        w = clamp01(1 - k / padWin) * (1 - cornering) * PAD_PULL;
        targetNorm = clamp(padX[j] / limit[i], -1, 1);
        break;
      }
    }
    padded[i] = lerp(lineNorm[i], targetNorm, w);
  }
  lineNorm.set(padded);

  const scratch = new Float32Array(n);
  const blurRadius = Math.max(1, Math.round(LINE_SMOOTH / step));
  ringBlur(lineNorm, n, blurRadius, scratch);
  ringBlur(lineNorm, n, blurRadius, scratch);

  // Speed profile. The curvature used mixes the average (how long the corner
  // is) and the peak (how tight its worst point is).
  const baseSpeed = new Float32Array(n);
  const widthSpan = Math.max(1, TRACK.halfWidthDefault - TRACK.halfWidthMin);
  for (let i = 0; i < n; i++) {
    const kMix = 0.55 * absAvg[i] + 0.45 * absPeak[i];
    let v = holdableSpeed(kMix);
    if (crestPeak[i] > CREST_MIN) {
      v = Math.min(v, Math.sqrt(GRIP_CREST / crestPeak[i]));
    }
    const widthFactor = lerp(0.9, 1, clamp01((half[i] - TRACK.halfWidthMin) / widthSpan));
    baseSpeed[i] = clamp(v * widthFactor, SPEED_FLOOR, SHIP.maxSpeed);
  }
  ringBlur(baseSpeed, n, Math.max(1, Math.round(8 / step)), scratch);

  return { n, step, length, limit, lineNorm, baseSpeed, straight };
}

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

/**
 * Build a rival controller.
 * @param {object} ship  the craft this AI drives (read only)
 * @param {object} track the shared track
 * @param {number} skill in [0, 1], 1 = near perfect pace
 */
export function createAI(ship, track, skill) {
  const sk = clamp(typeof skill === 'number' ? skill : 0.9, 0, 1);
  const shared = getTrackData(track);
  const n = shared.n;
  const index = ship && typeof ship.index === 'number' ? ship.index | 0 : 0;
  const rand = mulberry32((0x9e3779b9 ^ Math.imul(index + 1, 0x85ebca6b) ^ Math.round(sk * 4093)) >>> 0);

  // Per-pilot line signature: an apex aggressiveness plus a smooth periodic
  // wobble, so the three rivals never overlap perfectly.
  const apexScale = clamp(0.8 + 0.2 * sk + (rand() - 0.5) * 0.08, 0.6, 1);
  const lineAmp = 1.4 * (1.25 - 0.6 * sk);
  const speedAmp = 0.012 + 0.012 * (1 - sk);
  const h1 = 3 + index;
  const h2 = 7 + index * 2;
  const h3 = 13 + index * 3;
  const p1 = rand() * Math.PI * 2;
  const p2 = rand() * Math.PI * 2;
  const p3 = rand() * Math.PI * 2;

  const offsets = new Float32Array(n); // metres, target lateral offset
  const speeds = new Float32Array(n); // m/s, target speed
  const skillSpeed = lerp(0.74, 1.02, sk);

  for (let i = 0; i < n; i++) {
    const theta = (i / n) * Math.PI * 2;
    const wobble =
      (Math.sin(theta * h1 + p1) * 0.6 + Math.sin(theta * h2 + p2) * 0.4) * lineAmp;
    const lim = shared.limit[i];
    offsets[i] = clamp(shared.lineNorm[i] * apexScale * lim + wobble, -lim, lim);
    const vNoise = 1 + Math.sin(theta * h3 + p3) * speedAmp;
    speeds[i] = clamp(shared.baseSpeed[i] * skillSpeed * vNoise, SPEED_FLOOR * 0.7, SHIP.maxSpeed);
  }

  return {
    ship,
    track,
    skill: sk,
    index,
    shared,
    offsets,
    speeds,
    // Scratch frame owned by this instance only, never shared with anything.
    frame: track.makeFrame(),
    rand,
    // Speed reached where the road imposes no corner limit at all. Used to
    // tell "I am simply flat out" from "I am above a corner limit".
    freeSpeed: Math.min(SHIP.maxSpeed, SHIP.maxSpeed * skillSpeed * (1 - speedAmp)),
    // How late this pilot dares to brake, m/s^2 of assumed deceleration.
    brakeDecel: lerp(48, 78, sk),
    yawGain: YAW_P * (0.85 + 0.15 * sk),
    mistakeTimer: 0,
    mistakeCooldown: 2 + rand() * 6,
    mistakeChance: MISTAKE_RATE * (1 - sk) * (1 - sk),
    targetSpeed: 0, // last computed target, handy for debugging
    targetOffset: 0,
    controls: { thrust: 0, brake: 0, steer: 0, airLeft: 0, airRight: 0, boost: false },
  };
}

// ---------------------------------------------------------------------------
// Per frame
// ---------------------------------------------------------------------------

/**
 * Drive one rival for one frame.
 * @param {object} ai      value returned by createAI
 * @param {number} dt      seconds
 * @param {object} context { ships, playerProgress, raceTime, state }
 * @returns {object} the controls object owned by this AI
 */
export function updateAI(ai, dt, context) {
  const c = ai.controls;
  const ship = ai.ship;
  const track = ai.track;
  const shared = ai.shared;
  const n = shared.n;

  c.thrust = 0;
  c.brake = 0;
  c.steer = 0;
  c.airLeft = 0;
  c.airRight = 0;
  c.boost = false;

  const state = context && context.state ? context.state : 'racing';
  if (state === 'countdown' || ship.destroyed || ship.finished) {
    ai.mistakeTimer = 0;
    return c;
  }

  // Timers first, they gate the braking logic below.
  if (ai.mistakeTimer > 0) ai.mistakeTimer -= dt;
  else if (ai.mistakeCooldown > 0) ai.mistakeCooldown -= dt;

  const frame = track.at(ship.s, ai.frame);
  const sp = ship.speed;
  const idxScale = n / shared.length;
  const idx0 = ship.s * idxScale;

  // --- target speed ------------------------------------------------------
  // Scan the next `speed * 2.5` seconds. For a sample `d` metres ahead the
  // speed we may carry right now is the braking curve sqrt(v^2 + 2*a*d): the
  // minimum of that curve over the window is the real target, and it collapses
  // to the plain minimum target speed at d = 0.
  const lookDist = clamp(Math.abs(sp) * LOOK_SECONDS, LOOK_MIN, LOOK_MAX);
  const taps = Math.max(4, Math.min(LOOK_TAPS, Math.round(lookDist / shared.step)));
  const tapStep = lookDist / taps;
  const twoA = 2 * ai.brakeDecel;
  let target = Infinity;
  for (let k = 0; k <= taps; k++) {
    const d = k * tapStep;
    const v = sampleRing(ai.speeds, n, idx0 + d * idxScale);
    const allowed = Math.sqrt(v * v + twoA * d);
    if (allowed < target) target = allowed;
  }
  // Flat out: nothing in the window is a corner limit, so there is nothing to
  // brake for even when the craft is coasting down from a turbo overspeed.
  const noCorner = target >= ai.freeSpeed - 0.5;

  // --- rubber band -------------------------------------------------------
  const playerProgress =
    context && typeof context.playerProgress === 'number' ? context.playerProgress : null;
  if (playerProgress !== null && RACE.rubberBand > 0) {
    const gap = playerProgress - ship.totalProgress; // > 0 when the AI is behind
    // totalProgress is owned by race.js and is already zero at the start line,
    // so the finish is a whole number of laps, with no track.startS to add.
    const finishProgress = RACE.laps * shared.length;
    const remaining = finishProgress - ship.totalProgress;
    // The band is cut for the whole final lap: the last lap has to be decided
    // by the driving, not by an assist nudging the rivals onto the player.
    const endgame = remaining >= 0 && remaining < shared.length;
    if (!endgame) {
      target *= 1 + clamp(gap / BAND_RANGE, -1, 1) * RACE.rubberBand;
    }
  }
  target = clamp(target, SPEED_FLOOR * 0.6, SHIP.maxSpeed * (1 + RACE.rubberBand));

  // While a turbo is burning on a straight, let the craft run to the boost cap
  // instead of fighting its own overspeed with the brakes.
  const straightness = sampleRing(shared.straight, n, idx0);
  const boosting = ship.boostTimer > 0 || ship.padBoostTimer > 0;
  if (boosting && straightness > 0.5) {
    target = Math.max(target, Math.min(SHIP.boostMaxSpeed, target + 60 * straightness));
  }
  ai.targetSpeed = target;

  // --- racing line, read slightly ahead to remove the controller lag ------
  const aimDist = clamp(Math.abs(sp) * AIM_SECONDS, AIM_MIN, AIM_MAX);
  let targetX = sampleRing(ai.offsets, n, idx0 + aimDist * idxScale);

  // --- lateral avoidance -------------------------------------------------
  let avoid = 0;
  let blocked = 0;
  const ships = context && context.ships ? context.ships : null;
  if (ships) {
    for (let i = 0; i < ships.length; i++) {
      const other = ships[i];
      if (other === ship || other.destroyed) continue;
      const ds = track.deltaS(ship.s, other.s);
      const dx = other.x - ship.x;
      const adx = Math.abs(dx);
      if (ds > 0 && ds < AVOID_RANGE && adx < AVOID_LATERAL) {
        // Only worth avoiding something we are actually catching.
        if (sp > other.speed - 3) {
          const urgency = (1 - ds / AVOID_RANGE) * (1 - adx / AVOID_LATERAL);
          let side = dx >= 0 ? -1 : 1;
          // Do not dive into a wall to overtake: pick the roomy side.
          const room = frame.halfWidth - SHIP.halfWidth - 1;
          if (side < 0 && ship.x < -room * 0.75) side = 1;
          else if (side > 0 && ship.x > room * 0.75) side = -1;
          avoid += side * AVOID_PUSH * urgency;
          if (ds < 11 && adx < 2.6) blocked = Math.max(blocked, urgency);
        }
      } else if (Math.abs(ds) < SHIP.length * 1.3 && adx < SHIP.width * 1.6) {
        // Side by side: hold station away from the other hull.
        avoid += (dx >= 0 ? -1 : 1) * 2.4 * (1 - adx / (SHIP.width * 1.6));
      }
    }
  }
  targetX += clamp(avoid, -AVOID_MAX, AVOID_MAX);
  const hardLimit = Math.max(0.5, frame.halfWidth - SHIP.halfWidth - 0.6);
  targetX = clamp(targetX, -hardLimit, hardLimit);
  ai.targetOffset = targetX;

  // --- longitudinal ------------------------------------------------------
  const dv = target - sp;
  if (dv > 1.5) {
    c.thrust = 1;
  } else if (dv > -BRAKE_DEADBAND) {
    c.thrust = clamp01((dv + BRAKE_DEADBAND) / (BRAKE_DEADBAND + 1.5));
  } else {
    c.thrust = 0;
  }

  let wantBrake = 0;
  if (dv < -BRAKE_DEADBAND && !noCorner) wantBrake = clamp01((-dv - BRAKE_DEADBAND) / 12);

  // A rival occasionally brakes too late. The mistake is armed only in a real
  // braking zone, so it always shows: the craft runs wide and has to recover.
  if (
    ai.mistakeTimer <= 0 &&
    ai.mistakeCooldown <= 0 &&
    wantBrake > 0.35 &&
    ai.rand() < ai.mistakeChance * dt
  ) {
    ai.mistakeTimer = MISTAKE_MIN + ai.rand() * MISTAKE_SPAN;
    ai.mistakeCooldown = MISTAKE_COOLDOWN + ai.rand() * 12;
  }
  if (ai.mistakeTimer > 0) {
    wantBrake = 0;
    c.thrust = Math.max(c.thrust, 0.55);
  }
  c.brake = wantBrake;

  // Blocked nose to tail: back off rather than ram the craft ahead.
  if (blocked > 0) c.thrust *= 1 - 0.55 * blocked;

  // Stuck (spun, reversing, freshly respawned): just get going again.
  if (sp < 6 && c.brake === 0) c.thrust = 1;

  // --- steering, PD on the lateral error ---------------------------------
  const vRef = Math.max(Math.abs(sp), 18);
  const latErr = targetX - ship.x;
  const latMax = clamp(LAT_MAX_FRACTION * Math.abs(sp), 6, 34);
  // P term: the lateral velocity we would like to have.
  const desiredLat = clamp(LAT_P * latErr, -latMax, latMax);
  // Converting it into a heading subtracts the drift already present, so the
  // yaw error below is exactly the D term on the current lateral velocity:
  // vRef * (sin(yawTarget) - sin(yaw)) = desiredLat - (speed*sin(yaw) + vLat).
  const sinNeeded = clamp((desiredLat - ship.vLat) / vRef, -0.55, 0.55);
  const yawTarget = Math.asin(sinNeeded);
  const yawErr = yawTarget - ship.yaw;

  const authority =
    SHIP.steerRate * lerp(1, SHIP.steerSpeedFalloff, clamp01(Math.abs(sp) / SHIP.maxSpeed));
  // The integrator damps yaw back to the tangent every frame, so the command
  // has to pay for that damping before it can turn: this is what stops the
  // controller from oscillating around the line.
  const wantYawRate = ai.yawGain * yawErr + ship.yaw * SHIP.yawDamping;
  const steerRaw = wantYawRate / authority;

  // --- airbrakes ---------------------------------------------------------
  let airLeft = 0;
  let airRight = 0;
  // One airbrake injects SHIP.airbrakeYaw rad/s, which is more than the rudder
  // can cancel at racing speed, so it is only opened when the steering has run
  // out AND the demanded yaw rate is high enough that the airbrake will not
  // overshoot it. Anything less and the craft would snap into the outside wall.
  const airbrakeYawFloor = SHIP.airbrakeYaw - authority * 0.9;
  if (Math.abs(steerRaw) > STEER_SATURATION && Math.abs(wantYawRate) > airbrakeYawFloor) {
    if (wantYawRate > 0) airRight = 1;
    else airLeft = 1;
  } else if (c.brake > 0.4) {
    // Pure braking: both airbrakes out. Symmetric, so heavy drag and no yaw.
    airLeft = 1;
    airRight = 1;
  }
  if (ai.mistakeTimer > 0) {
    airLeft = 0;
    airRight = 0;
  }
  c.airLeft = airLeft;
  c.airRight = airRight;

  // Recompute the steering knowing what the airbrakes already contribute to
  // the yaw rate, otherwise the two commands fight and the craft weaves.
  const airYaw = (airRight - airLeft) * SHIP.airbrakeYaw;
  c.steer = clamp((wantYawRate - airYaw) / authority, -1, 1);

  // --- turbo -------------------------------------------------------------
  if (
    ship.boostEnergy >= 99 &&
    straightness > 0.55 &&
    Math.abs(sp) > SHIP.maxSpeed * 0.55 &&
    c.brake === 0 &&
    ai.mistakeTimer <= 0 &&
    Math.abs(ship.x - targetX) < 4
  ) {
    c.boost = true;
  }

  return c;
}
