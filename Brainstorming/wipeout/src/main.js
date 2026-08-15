/**
 * VELOCITRON - application entry point.
 *
 * Boots the renderer, builds every subsystem in order, then runs the game loop:
 *   input -> race -> race events -> fx -> world -> camera -> hud -> audio -> post
 *
 * The whole boot is wrapped in a try/catch that routes any failure to
 * window.__fail (declared in index.html) so a broken machine shows the error
 * screen instead of a black canvas.
 */

import * as THREE from 'three';
import {
  GAME_TITLE,
  TRACK_NAME,
  PALETTE,
  TRACK,
  SHIP,
  RACE,
  CAMERA,
  AUDIO,
  DEBUG,
} from './config.js';
import { createTextures } from './textures.js';
import { createTrack } from './track.js';
import { createWorld } from './world.js';
import { createFX } from './fx.js';
import { createShip } from './ship.js';
import { createAI, updateAI } from './ai.js';
import { createRace } from './race.js';
import { createPost } from './post.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';
import { createInput } from './input.js';

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

const PILOT_NAMES = ['VOUS', 'R. KANDA', 'S. VOSS', 'A. MERIDIAN'];
const DT_MAX = 1 / 30;

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/** Frame rate independent smoothing factor for a lag of `rate` per second. */
function springK(rate, dt) {
  return 1 - Math.exp(-rate * dt);
}

function byId(id) {
  return document.getElementById(id);
}

function fail(err) {
  const message = err && err.message ? err.message : String(err);
  const where = err && err.stack ? err.stack : '';
  if (typeof window.__fail === 'function') window.__fail(message, where);
  else console.error(err);
}

/** Yield to the browser so the loading bar actually paints between steps. */
function paint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => setTimeout(resolve, 0));
  });
}

function showScreen(id) {
  const screens = document.querySelectorAll('.screen');
  for (let i = 0; i < screens.length; i++) screens[i].classList.add('hidden');
  if (id) {
    const el = byId(id);
    if (el) el.classList.remove('hidden');
  }
}

function setLoading(pct, line) {
  const fill = byId('loading-fill');
  if (fill) fill.style.width = clamp(pct, 0, 100) + '%';
  const label = byId('loading-line');
  if (label) label.textContent = line;
}

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

let renderer = null;
let scene = null;
let camera = null;
let textures = null;
let track = null;
let world = null;
let fx = null;
let post = null;
let hud = null;
let audio = null;
let input = null;
let race = null;

/** @type {Array} */
let ships = [];
/** @type {Array} */
let ais = [];
let playerShip = null;

let state = 'loading';
let stateBeforePause = 'racing';
let rafId = 0;
let lastTime = 0;
let elapsed = 0;

// Adaptive resolution. The cap only drops after two consecutive bad windows and
// climbs back after a sustained good one, so a single hiccup cannot latch the
// low resolution for the rest of the session.
const PIXEL_CAP_HIGH = 2;
const PIXEL_CAP_LOW = 1.5;
const FRAME_OUTLIER_MS = 200; // alt-tab, breakpoint or long GC, not a real frame
const FRAME_BAD_MS = 22;
const FRAME_GOOD_MS = 15;
let pixelCap = PIXEL_CAP_HIGH;
let ftAccum = 0;
let ftCount = 0;
let ftWindow = 0;
let badWindows = 0;
let goodWindows = 0;

// camera rig
let cockpit = false;
let camSnap = true;
let camShake = 0;
const camPos = new THREE.Vector3();
const camQuat = new THREE.Quaternion();
const menuAnchor = { s: 0, x: 0, h: SHIP.hoverHeight, yaw: 0, speed: 46 };
const camAnchor = { s: 0, x: 0, h: SHIP.hoverHeight, yaw: 0, speed: 0 };

// per frame edge detection on ship state (main owns these mirrors)
let prevDestroyed = [];
let prevBoosting = [];

// hud bookkeeping
let playerBestMs = null;
let deltaTimer = 0;
let countdownTimer = 0;
let lastCountdownValue = null;
let finishAnnounced = false;
let standingsTimer = 0;
const hudTimes = { current: 0, last: null, best: null };
/** @type {Array<{pos:number,name:string,gap:string,isPlayer:boolean,color:number}>} */
let standingRows = [];
/** Reused view over standingRows, sized to the number of ranked craft. */
let standingView = [];
/** @type {Array<{u:number,v:number,color:number,isPlayer:boolean}>} */
let minimapDots = [];

// scratch, never shared between two functions that can nest
let frameCam = null;
let frameClamp = null;
let frameEvent = null;
const _camDesired = new THREE.Vector3();
const _camPrevDesired = new THREE.Vector3();
const _camFeed = new THREE.Vector3();
const _camLook = new THREE.Vector3();
const _camUp = new THREE.Vector3();
const _camFwd = new THREE.Vector3();
const _camMat = new THREE.Matrix4();
const _camQuatTarget = new THREE.Quaternion();
const _camShakeQuat = new THREE.Quaternion();
const _camShakeAxis = new THREE.Vector3(0, 0, 1);
const _clampOffset = new THREE.Vector3();
const _evNormal = new THREE.Vector3();
/** Reused argument for audio.setEngine, mutated in place every frame. */
const engineParams = { speed01: 0, throttle01: 0, boost: false, airborne: false };

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function boot() {
  showScreen('screen-loading');
  setLoading(2, 'INITIALISATION DU RENDU...');
  await paint();

  const canvas = byId('scene');
  if (!canvas) throw new Error('Canvas #scene introuvable dans index.html');

  const gl = canvas.getContext('webgl2', {
    alpha: false,
    antialias: false,
    depth: true,
    stencil: false,
    premultipliedAlpha: true,
    preserveDrawingBuffer: false,
    powerPreference: 'high-performance',
    failIfMajorPerformanceCaveat: false,
  });
  if (!gl) throw new Error('WebGL2 indisponible sur ce navigateur');

  renderer = new THREE.WebGLRenderer({
    canvas,
    context: gl,
    antialias: false,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(pixelCap, window.devicePixelRatio || 1));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(PALETTE.night, 1);
  // The scene is rendered linear into a HalfFloat target; ACES + sRGB happen by
  // hand in the final pass of post.js.
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(
    CAMERA.fovBase,
    window.innerWidth / Math.max(1, window.innerHeight),
    CAMERA.near,
    CAMERA.far,
  );
  scene.add(camera);

  setLoading(8, 'SYNTHESE DES TEXTURES...');
  await paint();
  textures = createTextures(renderer);

  setLoading(28, 'TRACE DU CIRCUIT AKARI...');
  await paint();
  track = createTrack(textures);
  if (track.group && !track.group.parent) scene.add(track.group);
  frameCam = track.makeFrame();
  frameClamp = track.makeFrame();
  frameEvent = track.makeFrame();
  menuAnchor.s = track.startS;

  setLoading(48, 'CONSTRUCTION DE NEO KYOTO...');
  await paint();
  world = createWorld(scene, track, textures, renderer);
  if (world.group && !world.group.parent) scene.add(world.group);

  setLoading(62, 'ALLUMAGE DES EFFETS...');
  await paint();
  fx = createFX(scene, textures);

  setLoading(70, 'PREPARATION DES APPAREILS...');
  await paint();
  buildShips();

  setLoading(80, 'ETALONNAGE DU POST TRAITEMENT...');
  await paint();
  post = createPost(renderer, scene, camera);

  setLoading(88, 'INTERFACE DE COURSE...');
  await paint();
  hud = createHUD(track);
  hud.hide();

  setLoading(94, 'SYNTHESE AUDIO...');
  await paint();
  audio = createAudio();
  // audio.js already folds AUDIO.masterGain into the master node, so the
  // slider value is a plain 0..1 multiplier on top of it.
  audio.setMasterVolume(1);

  setLoading(98, 'ARMEMENT DES COMMANDES...');
  await paint();
  input = createInput(window);
  bindInput();
  bindUI();

  buildRace();
  applySize();
  resetCameraRig();

  setLoading(100, 'PRET');
  await paint();

  exposeGlobals();
  setState('menu');
  showScreen('screen-menu');

  lastTime = performance.now();
  rafId = requestAnimationFrame(loop);
  window.__ready = true;
}

function buildShips() {
  const count = 1 + RACE.rivals;
  ships = [];
  ais = [];
  for (let i = 0; i < count; i++) {
    const ship = createShip({
      track,
      textures,
      index: i,
      isPlayer: i === 0,
      name: PILOT_NAMES[i] || 'PILOTE ' + (i + 1),
      color: PALETTE.liveries[i % PALETTE.liveries.length],
    });
    if (ship.mesh && !ship.mesh.parent) scene.add(ship.mesh);
    fx.attach(ship);
    ships.push(ship);
    if (i > 0) {
      const skill = RACE.aiSkill[i - 1] !== undefined ? RACE.aiSkill[i - 1] : 0.9;
      ais.push(createAI(ship, track, skill));
    }
  }
  playerShip = ships[0];

  prevDestroyed = new Array(count).fill(false);
  prevBoosting = new Array(count).fill(false);

  standingRows = [];
  minimapDots = [];
  standingView = [];
  for (let i = 0; i < count; i++) {
    standingRows.push({
      pos: i + 1,
      name: ships[i].name,
      gap: '',
      isPlayer: i === 0,
      color: ships[i].color,
    });
    standingView.push(standingRows[i]);
    minimapDots.push({ u: 0, v: 0, color: ships[i].color, isPlayer: i === 0 });
  }
}

/**
 * Rebuild only the race layer. Textures, track, world, ships and meshes are
 * reused so restarting is instant.
 */
function buildRace() {
  for (let i = 0; i < ships.length; i++) {
    resetShipState(ships[i]);
    prevDestroyed[i] = false;
    prevBoosting[i] = false;
  }
  // createRace already ends with placeOnGrid(); calling it again here would run
  // the whole grid placement, clearEvents and updateStandings twice per start.
  race = createRace({ track, ships, ais, laps: RACE.laps });
  playerShip = race.playerShip || ships[0];
  // Drop the particles and trails left over from the previous race.
  if (fx && typeof fx.reset === 'function') fx.reset();

  playerBestMs = null;
  deltaTimer = 0;
  countdownTimer = 0;
  lastCountdownValue = null;
  finishAnnounced = false;
  standingsTimer = 0;
  camShake = 0;
  if (window.game) window.game.race = race;
}

/**
 * Reset the mutable fields of a craft. createRace / placeOnGrid runs after this
 * and overrides whatever it owns, so this only fills the gaps.
 */
function resetShipState(ship) {
  ship.speed = 0;
  ship.vLat = 0;
  ship.vh = 0;
  ship.yaw = 0;
  ship.roll = 0;
  ship.pitch = 0;
  ship.h = SHIP.hoverHeight;
  ship.shield = SHIP.shieldMax;
  ship.boostEnergy = 100;
  ship.boostTimer = 0;
  ship.padBoostTimer = 0;
  ship.lap = 0;
  ship.lastCheckpoint = -1;
  ship.finished = false;
  ship.finishTime = 0;
  ship.bestLap = null;
  ship.lapStartTime = 0;
  ship.totalProgress = 0;
  ship.destroyed = false;
  ship.respawnTimer = 0;
  if (Array.isArray(ship.lapTimes)) ship.lapTimes.length = 0;
  else ship.lapTimes = [];
  if (ship.events) {
    ship.events.wallHit = 0;
    ship.events.padHit = false;
    ship.events.land = 0;
    ship.events.shipHit = 0;
  }
  if (ship.mesh) ship.mesh.visible = true;
}

function exposeGlobals() {
  window.game = {
    track,
    ships,
    race,
    post,
    world,
    audio,
    hud,
    fx,
    renderer,
    scene,
    camera,
    state,
    input,
    textures,
    startRace,
    restartRace,
    togglePause,
    // Factories, so a console session or an automated test can drive the
    // simulation without going through the render loop.
    createAI,
    updateAI,
    ais,
    THREE,
  };
}

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

function setState(next) {
  state = next;
  if (window.game) window.game.state = next;
}

function startRace() {
  if (state === 'racing' || state === 'countdown') return;
  if (audio) audio.resume();
  buildRace();
  showScreen(null);
  hud.show();
  hud.setCountdown(null);
  hud.setDelta(null);
  hud.setLap(1, RACE.laps);
  hud.setPosition(ships.length, ships.length);
  input.releaseAll();
  resetCameraRig();
  setState('countdown');
  audio.startEngine();
  audio.startMusic();
  hud.banner(TRACK_NAME, RACE.laps + ' TOURS', 2200);
}

function restartRace() {
  setState('menu');
  startRace();
}

function togglePause() {
  if (state === 'racing' || state === 'countdown') pauseGame();
  else if (state === 'paused') resumeGame();
}

function pauseGame() {
  stateBeforePause = state;
  setState('paused');
  input.releaseAll();
  audio.stopEngine();
  showScreen('screen-pause');
}

function resumeGame() {
  if (state !== 'paused') return;
  showScreen(null);
  setState(stateBeforePause);
  audio.resume();
  audio.startEngine();
  lastTime = performance.now();
  resetFrameStats();
}

function showResults() {
  setState('results');
  audio.stopEngine();
  // Hand the free camera over where the player stopped so it does not fly
  // across the map on the first frame of the results screen.
  if (playerShip) {
    menuAnchor.s = playerShip.s;
    menuAnchor.x = 0;
    menuAnchor.h = SHIP.hoverHeight;
    menuAnchor.yaw = 0;
  }
  cockpit = false;
  const rows = buildResultRows();
  const playerRow = rows.find((r) => r.isPlayer);
  const won = !!playerRow && playerRow.pos === 1;
  const title = won ? 'VICTOIRE' : 'COURSE TERMINEE';
  // playerBestMs is fed by the lap events; fall back to the craft's own record
  // so the subtitle is never blank when a lap was actually completed.
  const bestMs = playerBestMs !== null
    ? playerBestMs
    : (playerShip ? shipBestLap(playerShip) : null);
  const best = bestMs !== null ? hud.formatTime(bestMs) : '--:--.---';
  hud.results(rows, title, TRACK_NAME + ' - MEILLEUR TOUR ' + best);
  hud.setCountdown(null);
  hud.hide();
  showScreen('screen-results');
  audio.finish(won);
}

function buildResultRows() {
  const source = Array.isArray(race.results) && race.results.length ? race.results : race.standings;
  const rows = [];
  for (let i = 0; i < source.length; i++) {
    const entry = source[i];
    const ship = entry && entry.ship ? entry.ship : entry;
    if (!ship) continue;
    const bestLap = shipBestLap(ship);
    const totalMs =
      typeof ship.finishTime === 'number' && ship.finishTime > 0 ? ship.finishTime : null;
    rows.push({
      pos: typeof entry.pos === 'number' ? entry.pos : i + 1,
      name: ship.name || 'PILOTE',
      isPlayer: !!ship.isPlayer,
      color: ship.color,
      // hud.results renders a string as-is and formats a number, so a craft
      // that never crossed the line reads ABANDON instead of --:--.---.
      time: totalMs !== null ? totalMs : 'ABANDON',
      best: bestLap,
    });
  }
  return rows;
}

function shipBestLap(ship) {
  if (typeof ship.bestLap === 'number' && isFinite(ship.bestLap) && ship.bestLap > 0) {
    return ship.bestLap;
  }
  if (Array.isArray(ship.lapTimes) && ship.lapTimes.length) {
    let best = Infinity;
    for (let i = 0; i < ship.lapTimes.length; i++) {
      if (ship.lapTimes[i] < best) best = ship.lapTimes[i];
    }
    return isFinite(best) ? best : null;
  }
  return null;
}

// ---------------------------------------------------------------------------
// UI and input bindings
// ---------------------------------------------------------------------------

function bindUI() {
  const start = byId('btn-start');
  if (start) {
    start.addEventListener('click', () => {
      audio.resume();
      startRace();
    });
  }
  const resume = byId('btn-resume');
  if (resume) resume.addEventListener('click', resumeGame);

  const restartPause = byId('btn-restart-pause');
  if (restartPause) restartPause.addEventListener('click', restartRace);

  const restart = byId('btn-restart');
  if (restart) restart.addEventListener('click', restartRace);

  const volume = byId('volume');
  const volumeValue = byId('volume-value');
  if (volume) {
    volume.value = '100';
    if (volumeValue) volumeValue.textContent = volume.value;
    volume.addEventListener('input', () => {
      const v = Number(volume.value) / 100;
      audio.setMasterVolume(clamp01(v));
      if (volumeValue) volumeValue.textContent = volume.value;
    });
  }

  // Browsers only allow audio after a gesture; the menu click is the usual one
  // but any pointer down works as a fallback.
  window.addEventListener(
    'pointerdown',
    () => {
      audio.resume();
    },
    { once: true },
  );

  window.addEventListener('resize', applySize);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (state === 'racing' || state === 'countdown') pauseGame();
      return;
    }
    // Coming back from a hidden tab: the next rAF would otherwise report the
    // whole hidden duration as one frame time.
    lastTime = performance.now();
    resetFrameStats();
  });
}

function bindInput() {
  input.onAction('pause', togglePause);
  input.onAction('camera', () => {
    if (state !== 'racing' && state !== 'countdown') return;
    cockpit = !cockpit;
    camSnap = true;
    hud.toast(cockpit ? 'CAMERA COCKPIT' : 'CAMERA POURSUITE');
  });
  input.onAction('mute', () => {
    const muted = audio.toggleMute();
    hud.toast(muted ? 'SON COUPE' : 'SON ACTIF');
  });
  input.onAction('respawn', () => {
    if (state !== 'racing' || !playerShip || !race) return;
    // race.requestRespawn only gives back a partial shield and keeps the lap
    // bookkeeping straight, unlike a raw respawnShip which is a free repair.
    if (!race.requestRespawn(playerShip)) return;
    camSnap = true;
    hud.toast('REMISE SUR PISTE');
  });
}

function applySize() {
  const w = Math.max(1, window.innerWidth);
  const h = Math.max(1, window.innerHeight);
  renderer.setPixelRatio(Math.min(pixelCap, window.devicePixelRatio || 1));
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  const pr = renderer.getPixelRatio();
  const pxW = Math.floor(w * pr);
  const pxH = Math.floor(h * pr);
  if (post) post.setSize(pxW, pxH);
  // Particle point size is expressed in device pixels, so it has to follow the
  // adaptive resolution rather than the raw devicePixelRatio.
  if (fx && typeof fx.setSize === 'function') fx.setSize(pxW, pxH);
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

function loop(now) {
  rafId = requestAnimationFrame(loop);

  const rawMs = now - lastTime;
  lastTime = now;
  adaptResolution(rawMs);

  let dt = rawMs / 1000;
  if (!(dt > 0)) dt = 0;
  if (dt > DT_MAX) dt = DT_MAX;
  // elapsed only drives the shake oscillator, so it freezes with the image.
  if (state !== 'paused') elapsed += dt;

  const running = state === 'racing' || state === 'countdown';

  if (running) {
    input.update(dt);
    race.update(dt, input.controls);
    consumeRaceEvents();
    consumeShipEvents(dt);
    syncRaceState();
  }

  const speed01 = playerShip ? clamp01(Math.abs(playerShip.speed) / SHIP.maxSpeed) : 0;
  // Cosmetic layers keep animating on the menu and the results screen, and
  // freeze completely on pause.
  const visualDt = state === 'paused' ? 0 : dt;

  fx.update(visualDt, camera, ships);
  world.update(visualDt, camera.position, speed01);
  updateCamera(visualDt, running);

  if (running) updateHUD(dt, speed01);

  if (running) {
    engineParams.speed01 = speed01;
    engineParams.throttle01 = input.controls.thrust;
    engineParams.boost = playerShip.boostTimer > 0 || playerShip.padBoostTimer > 0;
    engineParams.airborne = playerShip.h > SHIP.hoverHeight * 2.2;
    audio.setEngine(engineParams);
  }
  audio.update(running ? dt : 0);

  post.params.speed = running ? speed01 : 0;
  post.params.shake = clamp01(camShake);
  post.render(visualDt);
}

function adaptResolution(rawMs) {
  // rAF does not fire in a hidden tab, so the first frame back carries the whole
  // hidden duration. Such a sample says nothing about rendering cost: drop it.
  if (!(rawMs > 0) || rawMs > FRAME_OUTLIER_MS) return;
  ftAccum += rawMs;
  ftCount++;
  ftWindow += rawMs;
  if (ftWindow < 1000) return;
  const avg = ftAccum / Math.max(1, ftCount);

  if (avg > FRAME_BAD_MS) {
    badWindows++;
    goodWindows = 0;
  } else if (avg < FRAME_GOOD_MS) {
    goodWindows++;
    badWindows = 0;
  } else {
    badWindows = 0;
    goodWindows = 0;
  }

  if (badWindows >= 2 && pixelCap > PIXEL_CAP_LOW) {
    pixelCap = PIXEL_CAP_LOW;
    badWindows = 0;
    applySize();
  } else if (goodWindows >= 3 && pixelCap < PIXEL_CAP_HIGH) {
    pixelCap = PIXEL_CAP_HIGH;
    goodWindows = 0;
    applySize();
  }

  if (DEBUG) {
    document.title = GAME_TITLE + ' - ' + Math.round(1000 / Math.max(0.001, avg)) + ' fps';
  }
  ftAccum = 0;
  ftCount = 0;
  ftWindow = 0;
}

/** Drop the pending window so a pause or an alt-tab never pollutes the average. */
function resetFrameStats() {
  ftAccum = 0;
  ftCount = 0;
  ftWindow = 0;
  badWindows = 0;
  goodWindows = 0;
}

function syncRaceState() {
  if (race.state === 'racing' && state === 'countdown') setState('racing');
  if (race.state === 'finished' && state !== 'results') showResults();
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function consumeRaceEvents() {
  const ev = race.events;
  if (!ev) return;

  const cd = ev.countdown;
  if (cd !== null && cd !== undefined && cd !== lastCountdownValue) {
    lastCountdownValue = cd;
    if (cd > 0) {
      hud.setCountdown(String(cd));
      audio.countdownBeep(cd);
      countdownTimer = 1.2;
    } else {
      hud.setCountdown('GO');
      audio.countdownBeep(0);
      countdownTimer = 0.9;
    }
  }

  if (ev.lap) {
    const lapShip = ev.lap.ship;
    const lapTime = ev.lap.time;
    if (lapShip === playerShip && typeof lapTime === 'number') {
      const previousBest = playerBestMs;
      if (previousBest !== null) {
        hud.setDelta(lapTime - previousBest);
        deltaTimer = 5;
      } else {
        hud.setDelta(null);
      }
      if (previousBest === null || lapTime < previousBest) playerBestMs = lapTime;
      audio.lapChime(!!ev.lap.isBest);
      const lapNo = Math.min(RACE.laps, lapCountOf(playerShip) + 1);
      hud.banner(
        ev.lap.isBest ? 'MEILLEUR TOUR' : 'TOUR ' + lapNo,
        hud.formatTime(lapTime),
        1800,
      );
    }
  }

  if (ev.finish && !finishAnnounced) {
    finishAnnounced = true;
    hud.banner('ARRIVEE', TRACK_NAME, 2600);
  }

  resetRaceEvents(ev);
}

/** Events are owned by race.js but consumed here, so main clears them. */
function resetRaceEvents(ev) {
  for (const key in ev) {
    // countdown 0 means GO, so it has to fall back to null, not to 0.
    if (key === 'countdown') {
      ev[key] = null;
      continue;
    }
    const value = ev[key];
    // Array channels are owned and emptied by race.clearEvents(); nulling them
    // here makes the next `events.laps.length = 0` throw.
    if (Array.isArray(value)) {
      value.length = 0;
      continue;
    }
    if (typeof value === 'boolean') ev[key] = false;
    else if (typeof value === 'number') ev[key] = 0;
    else ev[key] = null;
  }
}

/** Ship events are reset by updateShip, main only reads them for fx and audio. */
function consumeShipEvents(dt) {
  for (let i = 0; i < ships.length; i++) {
    const ship = ships[i];
    const ev = ship.events;
    const isPlayer = ship === playerShip;

    if (ev) {
      if (ev.wallHit > 0) {
        track.at(ship.s, frameEvent);
        _evNormal.copy(frameEvent.right).multiplyScalar(ship.x >= 0 ? -1 : 1);
        const intensity = clamp01(ev.wallHit / 30);
        if (ev.wallHit > 6) {
          fx.sparks(ship.worldPos, _evNormal, 18 + Math.round(intensity * 34));
          if (isPlayer) {
            audio.impact(intensity);
            hud.hit(intensity);
            camShake = Math.min(1, camShake + 0.35 + intensity * 0.65);
          }
        } else {
          fx.sparks(ship.worldPos, _evNormal, 3);
          if (isPlayer) {
            audio.scrape(intensity);
            camShake = Math.min(0.35, camShake + intensity * dt * 4);
          }
        }
      }

      if (ev.land > 0) {
        fx.dust(ship.worldPos, 10 + Math.round(clamp01(ev.land / 24) * 26));
        if (isPlayer) {
          const power = clamp01(ev.land / 24);
          audio.impact(power * 0.7);
          camShake = Math.min(1, camShake + power * 0.5);
        }
      }

      if (ev.shipHit > 0) {
        track.at(ship.s, frameEvent);
        _evNormal.copy(frameEvent.right).multiplyScalar(ship.x >= 0 ? -1 : 1);
        fx.sparks(ship.worldPos, _evNormal, 8);
        if (isPlayer) {
          const power = clamp01(ev.shipHit / 24);
          audio.impact(power * 0.6);
          hud.hit(power * 0.6);
          camShake = Math.min(1, camShake + power * 0.35);
        }
      }

      if (ev.padHit && isPlayer) hud.toast('PLAQUE D ENERGIE');
    }

    const boosting = ship.boostTimer > 0 || ship.padBoostTimer > 0;
    if (boosting && !prevBoosting[i]) {
      fx.boostBurst(ship);
      if (isPlayer) {
        audio.boost();
        hud.boostFlash();
        camShake = Math.min(1, camShake + 0.22);
      }
    }
    prevBoosting[i] = boosting;

    if (ship.destroyed && !prevDestroyed[i]) {
      fx.explode(ship.worldPos);
      if (isPlayer) {
        audio.explosion();
        hud.hit(1);
        hud.toast('APPAREIL DETRUIT - REMISE EN PISTE');
        camShake = 1;
      }
    }
    prevDestroyed[i] = ship.destroyed;
  }
}

// ---------------------------------------------------------------------------
// Camera rig
// ---------------------------------------------------------------------------

function resetCameraRig() {
  cockpit = false;
  camSnap = true;
  camShake = 0;
}

/**
 * Spring chase camera built from the track frame rather than from the ship
 * quaternion, so a sliding craft does not swing the whole view. The rig lives in
 * track space, which keeps it above the road and inside the walls by
 * construction; a final clamp catches the spring overshoot.
 */
function updateCamera(dt, running) {
  // Pause freezes the simulation but must not move the rig: keep tracking the
  // player craft so the paused image is exactly the frame before the pause.
  // This flag never feeds the simulation, only the camera target selection.
  const follow = running || state === 'paused';
  const anchor = pickAnchor(dt, follow);

  if (cockpit && follow && playerShip && !playerShip.destroyed) {
    buildCockpitTarget();
  } else {
    buildChaseTarget(anchor);
  }

  const posK = camSnap ? 1 : springK(cockpit ? CAMERA.chaseLag * 2.2 : CAMERA.chaseLag, dt);
  const rotK = camSnap ? 1 : springK(cockpit ? CAMERA.chaseRotLag * 2.2 : CAMERA.chaseRotLag, dt);
  // Feed forward: carry the camera along with the target before correcting the
  // residual. A plain lerp toward a target moving at 140 m/s settles a long way
  // behind it (v * dt / k), which is why the craft ended up a speck on screen.
  if (camSnap) {
    _camPrevDesired.copy(_camDesired);
  }
  _camFeed.subVectors(_camDesired, _camPrevDesired);
  // dt === 0 means a frozen frame (pause): nothing moved, so nothing to carry.
  if (dt > 0 && _camFeed.lengthSq() < 2500) camPos.add(_camFeed); // ignore teleports
  _camPrevDesired.copy(_camDesired);
  camPos.lerp(_camDesired, posK);

  keepCameraInsideTrack(anchor);

  _camMat.lookAt(camPos, _camLook, _camUp);
  _camQuatTarget.setFromRotationMatrix(_camMat);
  camQuat.slerp(_camQuatTarget, rotK);
  camSnap = false;

  camera.position.copy(camPos);
  camera.quaternion.copy(camQuat);

  // impact shake, applied on top of the smoothed transform
  if (camShake > 0.0005) {
    const amp = camShake * camShake * 0.9;
    const t = elapsed * 60;
    camera.position.x += Math.sin(t * 1.7) * amp * 0.35;
    camera.position.y += Math.sin(t * 2.3 + 1.7) * amp * 0.3;
    camera.position.z += Math.sin(t * 1.9 + 3.1) * amp * 0.35;
    _camShakeQuat.setFromAxisAngle(_camShakeAxis, Math.sin(t * 2.1) * camShake * 0.05);
    camera.quaternion.multiply(_camShakeQuat);
    camShake *= Math.exp(-CAMERA.shakeDecay * dt);
    if (camShake < 0.0005) camShake = 0;
  }

  updateFov(dt, running);
}

/** Follow the player while racing or paused, fly along the circuit on the menus. */
function pickAnchor(dt, follow) {
  if (follow && playerShip) {
    camAnchor.s = playerShip.s;
    camAnchor.x = playerShip.x;
    camAnchor.h = Math.max(0, playerShip.h);
    camAnchor.yaw = playerShip.yaw;
    camAnchor.speed = playerShip.speed;
    return camAnchor;
  }
  if (state !== 'paused') {
    menuAnchor.s = track.wrapS(menuAnchor.s + menuAnchor.speed * dt);
  }
  return menuAnchor;
}

function buildChaseTarget(anchor) {
  const sBack = anchor.s - CAMERA.chaseBack;
  track.at(sBack, frameCam);

  const lateralLimit = Math.max(1, frameCam.halfWidth - 2);
  const camX = clamp(anchor.x * 0.8, -lateralLimit, lateralLimit);
  track.toWorld(sBack, camX, anchor.h + CAMERA.chaseUp, _camDesired);

  const lookX = clamp(anchor.x * 0.55 + Math.sin(anchor.yaw) * 7, -lateralLimit, lateralLimit);
  track.toWorld(anchor.s + CAMERA.chaseLookAhead, lookX, anchor.h + 1.7, _camLook);
  _camUp.copy(frameCam.up);
}

function buildCockpitTarget() {
  const ship = playerShip;
  _camFwd.set(0, 0, -1).applyQuaternion(ship.quat);
  _camUp.set(0, 1, 0).applyQuaternion(ship.quat);
  _camDesired
    .copy(ship.worldPos)
    .addScaledVector(_camFwd, -CAMERA.cockpitBack)
    .addScaledVector(_camUp, CAMERA.cockpitUp);
  _camLook.copy(_camDesired).addScaledVector(_camFwd, 60);
}

/**
 * Push the smoothed position back above the road surface and inside the walls.
 * Everything is expressed in the local frame at the camera abscissa.
 */
function keepCameraInsideTrack(anchor) {
  const sBack = anchor.s - (cockpit ? 0 : CAMERA.chaseBack);
  track.at(sBack, frameClamp);
  _clampOffset.copy(camPos).sub(frameClamp.pos);
  const localX = _clampOffset.dot(frameClamp.right);
  const localH = _clampOffset.dot(frameClamp.up);

  const minH = cockpit ? 0.5 : 1.4;
  if (localH < minH) camPos.addScaledVector(frameClamp.up, minH - localH);

  // Above the wall crest the camera is free (jumps, banked sections).
  if (localH < TRACK.wallHeight) {
    const limit = Math.max(1, frameClamp.halfWidth - 1);
    if (localX > limit) camPos.addScaledVector(frameClamp.right, limit - localX);
    else if (localX < -limit) camPos.addScaledVector(frameClamp.right, -limit - localX);
  }
}

function updateFov(dt, running) {
  const speed01 = running && playerShip ? clamp01(Math.abs(playerShip.speed) / SHIP.maxSpeed) : 0.15;
  const boosting =
    running && playerShip && (playerShip.boostTimer > 0 || playerShip.padBoostTimer > 0);
  const target =
    CAMERA.fovBase + (CAMERA.fovAtMaxSpeed - CAMERA.fovBase) * speed01 + (boosting ? 5 : 0);
  const k = springK(5, dt);
  const next = camera.fov + (target - camera.fov) * k;
  if (Math.abs(next - camera.fov) > 0.01) {
    camera.fov = next;
    camera.updateProjectionMatrix();
  }
}

// ---------------------------------------------------------------------------
// HUD feed
// ---------------------------------------------------------------------------

function lapCountOf(ship) {
  return Array.isArray(ship.lapTimes) ? ship.lapTimes.length : 0;
}

function updateHUD(dt, speed01) {
  const ship = playerShip;

  hud.setSpeed(Math.round(Math.abs(ship.speed) * 3.6), speed01);
  hud.setShield(clamp01(ship.shield / SHIP.shieldMax));
  const energy01 = clamp01(ship.boostEnergy / 100);
  hud.setBoost(energy01, ship.boostEnergy >= SHIP.boostCost);
  hud.setLap(Math.min(RACE.laps, lapCountOf(ship) + 1), RACE.laps);
  hud.speedFx(speed01);

  // timing, all derived from lapTimes so it never disagrees with race.js
  const raceMs = Math.max(0, race.time) * 1000;
  let done = 0;
  if (Array.isArray(ship.lapTimes)) {
    for (let i = 0; i < ship.lapTimes.length; i++) done += ship.lapTimes[i];
  }
  hudTimes.current = Math.max(0, raceMs - done);
  hudTimes.last =
    Array.isArray(ship.lapTimes) && ship.lapTimes.length
      ? ship.lapTimes[ship.lapTimes.length - 1]
      : null;
  hudTimes.best = playerBestMs !== null ? playerBestMs : shipBestLap(ship);
  hud.setTimes(hudTimes);

  if (deltaTimer > 0) {
    deltaTimer -= dt;
    if (deltaTimer <= 0) hud.setDelta(null);
  }
  if (countdownTimer > 0) {
    countdownTimer -= dt;
    if (countdownTimer <= 0) hud.setCountdown(null);
  }

  // standings at 10 Hz: the DOM does not need 60 rebuilds per second
  standingsTimer -= dt;
  if (standingsTimer <= 0) {
    standingsTimer = 0.1;
    updateStandings();
  }

  updateMinimap();
}

function updateStandings() {
  const standings = race.standings;
  if (!Array.isArray(standings)) return;
  const count = Math.min(standings.length, standingRows.length);
  for (let i = 0; i < count; i++) {
    const entry = standings[i];
    const ship = entry && entry.ship ? entry.ship : entry;
    const row = standingRows[i];
    row.pos = typeof entry.pos === 'number' ? entry.pos : i + 1;
    row.name = ship.name || 'PILOTE';
    row.isPlayer = ship === playerShip;
    row.color = ship.color;
    if (i === 0) row.gap = 'LEADER';
    else if (typeof entry.gap === 'number' && isFinite(entry.gap)) {
      const g = Math.abs(entry.gap);
      row.gap = '+' + (g >= 100 ? Math.round(g) : g.toFixed(1));
    } else row.gap = '';
    standingView[i] = row;
    if (row.isPlayer) hud.setPosition(row.pos, ships.length);
  }
  standingView.length = count;
  hud.setStandings(standingView);
}

function updateMinimap() {
  const pts = track.outlinePoints;
  if (!Array.isArray(pts) || !pts.length) return;
  for (let i = 0; i < ships.length; i++) {
    const ship = ships[i];
    const t = track.wrapS(ship.s) / track.length;
    let index = Math.floor(t * pts.length) % pts.length;
    if (index < 0) index += pts.length;
    const p = pts[index];
    const dot = minimapDots[i];
    dot.u = p.x;
    dot.v = p.y;
    dot.color = ship.color;
    dot.isPlayer = ship === playerShip;
  }
  hud.setMinimap(minimapDots);
}

// ---------------------------------------------------------------------------
// Go
// ---------------------------------------------------------------------------

boot().catch((err) => {
  if (rafId) cancelAnimationFrame(rafId);
  fail(err);
});
