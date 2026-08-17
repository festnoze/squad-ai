/**
 * RESONANCE - orchestration: boot, game loop, state machine, actions.
 *
 * Live-edit loop like PRISMA: there is no "run" button, the wave simulation
 * runs continuously and reacts instantly to every placement. The simulation
 * advances on a fixed timestep through an accumulator, at most one step per
 * rendered frame, so the interference pattern is a pure function of the step
 * counter whatever the frame rate.
 */

import * as THREE from 'three';
import { createWave, STEP_DT } from './wave.js';
import { createBoard, CHARGE_TIME, BAND_NAMES } from './board.js';
import { LEVELS } from './levels.js';
import { createHistory } from './history.js';
import { createTextures } from './textures.js';
import { createSurface } from './render/surface.js';
import { createPieces } from './render/pieces.js';
import { createCavern } from './render/cavern.js';
import { createOrbit } from './camera.js';
import { createInput } from './input.js';
import { createHud } from './hud.js';
import { createAudio } from './audio.js';
import { worldToSlot, slotToWorldX, slotToWorldZ } from './coords.js';

const SAVE_KEY = 'resonance.progress';
const AUDIO_KEY = 'resonance.audio';

// ---------------------------------------------------------------------------
// Renderer and scene
// ---------------------------------------------------------------------------

const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 200);

const textures = createTextures();
const cavern = createCavern(scene, textures);
const surface = createSurface(scene);
const pieces = createPieces(scene, textures);
const orbit = createOrbit(camera);
const audio = createAudio();
const history = createHistory();
const wave = createWave();

// ---------------------------------------------------------------------------
// Persistent progress
// ---------------------------------------------------------------------------

function loadSave() {
  try {
    const raw = localStorage.getItem(SAVE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      if (typeof s.unlocked === 'number' && s.best) return s;
    }
  } catch (err) { void err; }
  return { unlocked: 0, best: {} };
}
const save = loadSave();
function persist() {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(save)); } catch (err) { void err; }
}

// ---------------------------------------------------------------------------
// Game state
// ---------------------------------------------------------------------------

let mode = 'title'; // title | play | pause | complete | end
let levelIndex = Math.min(save.unlocked, LEVELS.length - 1);
let board = null;
let selectedBand = 0;
let selectedFork = null;
let hoverSlot = null;
let failShown = false;
let victoryTimer = -1;
let acc = 0;
let simTime = 0;
const lastNdc = { x: 0, y: 0, valid: false };
const pickPoint = new THREE.Vector3();
const slotScratch = { x: 0, y: 0 };
// Separate store: hoverSlot must survive slotScratch being reused by clicks.
const hoverStore = { x: 0, y: 0 };

const hud = createHud({
  onBandSelect: (b) => selectBand(b),
  onPlay: () => { startGame(); },
  onResume: () => togglePause(),
  onRestart: () => { togglePause(); restart(); },
  onTitle: () => showTitle(),
  onNext: () => nextFromComplete(),
  onReplay: () => { hud.showScreen(null); mode = 'play'; restart(); },
});

// ---------------------------------------------------------------------------
// Level management
// ---------------------------------------------------------------------------

function loadLevel(idx) {
  levelIndex = idx;
  const level = LEVELS[idx];
  board = createBoard(level, wave);
  surface.setLayout(wave);
  cavern.setLayout(level);
  pieces.setBoard(board);
  history.clear();
  selectedFork = null;
  selectedBand = board.stock.findIndex((n) => n > 0);
  if (selectedBand < 0) selectedBand = 0;
  failShown = false;
  victoryTimer = -1;
  hud.showFail(false);
  hud.setLevel(level, idx, LEVELS.length, save.best[level.id]);
  hud.setStock(board.stock, selectedBand);
  hud.setPoses(board.poses);
  audio.syncForks(board.forks);
}

function showTitle() {
  mode = 'title';
  hud.showScreen('title');
  loadLevel(levelIndex);
  // Attract mode: two silent demo sources so the title backdrop lives.
  wave.setSources([
    { idx: wave.idx(30, 38), band: 0, amp: 1, phase: 0 },
    { idx: wave.idx(66, 58), band: 2, amp: 1, phase: 0 },
  ]);
}

function startGame() {
  audio.unlock();
  hud.showScreen(null);
  mode = 'play';
  loadLevel(levelIndex);
  orbit.frame();
}

function restart() {
  loadLevel(levelIndex);
  hud.toast('Niveau recommence');
}

function gotoLevel(delta) {
  const target = levelIndex + delta;
  if (target < 0 || target >= LEVELS.length) return hud.toast('Pas de niveau dans ce sens');
  if (target > save.unlocked) return hud.toast('Niveau verrouille : terminez celui-ci');
  loadLevel(target);
  return null;
}

function nextFromComplete() {
  audio.click();
  hud.showScreen(null);
  if (levelIndex + 1 >= LEVELS.length) {
    mode = 'end';
    hud.showScreen('end');
    return;
  }
  mode = 'play';
  loadLevel(levelIndex + 1);
}

// ---------------------------------------------------------------------------
// Player actions (lesson: every physically legal action executes immediately;
// only impossible ones are refused, and always with visible+audible feedback)
// ---------------------------------------------------------------------------

function selectBand(b) {
  selectedBand = b;
  hud.setStock(board.stock, selectedBand);
  audio.click();
}

function doPlace(x, y, band) {
  const r = board.place(x, y, band, 0);
  if (!r.ok) {
    hud.toast(r.reason === 'stock epuise'
      ? `Stock ${BAND_NAMES[band]} epuise`
      : `Impossible : ${r.reason}`, 'warn');
    audio.error();
    return;
  }
  history.push({ type: 'place', fork: r.fork, step: wave.t });
  selectedFork = r.fork;
  audio.place(band);
  audio.syncForks(board.forks);
  hud.setStock(board.stock, selectedBand);
  hud.setPoses(board.poses);
}

function doRemove(fork) {
  const snapshot = { x: fork.x, y: fork.y, band: fork.band, phase: fork.phase };
  const r = board.remove(fork);
  if (!r.ok) { hud.toast(r.reason, 'warn'); audio.error(); return; }
  history.push({ type: 'remove', ...snapshot, step: wave.t });
  if (selectedFork === fork) selectedFork = null;
  audio.remove();
  audio.syncForks(board.forks);
  hud.setStock(board.stock, selectedBand);
}

function doPhase(fork) {
  const from = fork.phase;
  board.setPhase(fork, fork.phase + 1);
  history.push({ type: 'phase', fork, from, step: wave.t });
  audio.tweak(fork.band);
  hud.toast(`Phase : ${fork.phase * 90} degres`);
}

function doFreq(fork) {
  // Cycle to the next band with stock available.
  let band = fork.band;
  for (let i = 1; i <= 2; i++) {
    const b = (fork.band + i) % 3;
    if (board.stock[b] > 0) { band = b; break; }
  }
  if (band === fork.band) { hud.toast('Aucune autre frequence en stock', 'warn'); audio.error(); return; }
  const from = fork.band;
  board.setBand(fork, band);
  history.push({ type: 'band', fork, from, step: wave.t });
  audio.tweak(band);
  audio.syncForks(board.forks);
  hud.setStock(board.stock, selectedBand);
  hud.toast(`Frequence : ${BAND_NAMES[band]}`);
}

function undo() {
  const entry = history.undo();
  if (!entry) { hud.toast('Rien a annuler'); return; }
  if (entry.type === 'place') {
    board.remove(entry.fork);
    if (selectedFork === entry.fork) selectedFork = null;
  } else if (entry.type === 'remove') {
    const r = board.place(entry.x, entry.y, entry.band, entry.phase);
    if (r.ok) selectedFork = r.fork;
  } else if (entry.type === 'band') {
    board.setBand(entry.fork, entry.from);
  } else if (entry.type === 'phase') {
    board.setPhase(entry.fork, entry.from);
  }
  // Undo also resurrects any crystal that shattered since that action.
  board.restoreShatteredSince(entry.step);
  audio.syncForks(board.forks);
  hud.setStock(board.stock, selectedBand);
  hud.toast('Annule');
}

function togglePause() {
  if (mode === 'play') {
    mode = 'pause';
    hud.showScreen('pause');
  } else if (mode === 'pause') {
    mode = 'play';
    hud.showScreen(null);
  }
}

function toggleMute() {
  audio.setMuted(!audio.muted);
  try { localStorage.setItem(AUDIO_KEY, audio.muted ? '1' : '0'); } catch (err) { void err; }
  hud.setMuted(audio.muted);
  hud.toast(audio.muted ? 'Son coupe' : 'Son actif');
}

function clickAt(nx, ny, button) {
  if (mode !== 'play') return;
  if (!orbit.pick(nx, ny, pickPoint)) return;
  if (!worldToSlot(pickPoint.x, pickPoint.z, slotScratch)) return;
  const { x, y } = slotScratch;
  const fork = board.forkAt(x, y);
  if (button === 0) {
    if (fork) { selectedFork = fork; audio.click(); } else doPlace(x, y, selectedBand);
  } else if (button === 2) {
    if (fork) { selectedFork = fork; doPhase(fork); } else if (selectedFork) doPhase(selectedFork);
    else hud.toast('Selectionnez un diapason pour changer sa phase');
  } else if (button === 1) {
    if (fork) doRemove(fork);
    else hud.toast('Rien a retirer ici');
  }
}

function hoveredFork() {
  return hoverSlot ? board.forkAt(hoverSlot.x, hoverSlot.y) : null;
}

function onAction(name) {
  if (mode === 'title') {
    if (name === 'confirm') startGame();
    if (name === 'mute') toggleMute();
    return;
  }
  if (mode === 'complete') {
    if (name === 'confirm' || name === 'next') nextFromComplete();
    if (name === 'restart') { hud.showScreen(null); mode = 'play'; restart(); }
    return;
  }
  if (mode === 'end') {
    if (name === 'confirm' || name === 'pause') showTitle();
    return;
  }
  if (mode === 'pause') {
    if (name === 'pause' || name === 'confirm') togglePause();
    if (name === 'mute') toggleMute();
    if (name === 'restart') { togglePause(); restart(); }
    return;
  }
  // mode === 'play'
  switch (name) {
    case 'band0': selectBand(0); break;
    case 'band1': selectBand(1); break;
    case 'band2': selectBand(2); break;
    case 'freq': {
      const f = selectedFork || hoveredFork();
      if (f) doFreq(f); else hud.toast('Selectionnez un diapason (clic) puis F');
      break;
    }
    case 'phase': {
      const f = selectedFork || hoveredFork();
      if (f) doPhase(f); else hud.toast('Selectionnez un diapason (clic) puis G');
      break;
    }
    case 'delete': {
      const f = hoveredFork() || selectedFork;
      if (f) doRemove(f); else hud.toast('Aucun diapason vise');
      break;
    }
    case 'undo': undo(); break;
    case 'restart': restart(); break;
    case 'next': gotoLevel(1); break;
    case 'prev': gotoLevel(-1); break;
    case 'pause': togglePause(); break;
    case 'mute': toggleMute(); break;
    default: break;
  }
}

const input = createInput(canvas, {
  gesture: () => audio.unlock(),
  orbit: (dx, dy) => orbit.orbit(dx, dy),
  hover: (nx, ny) => { lastNdc.x = nx; lastNdc.y = ny; lastNdc.valid = true; },
  click: clickAt,
  wheel: (nx, ny, dy) => {
    // Over the selected fork the wheel retunes it; anywhere else it zooms.
    if (mode === 'play' && selectedFork && orbit.pick(nx, ny, pickPoint)
      && worldToSlot(pickPoint.x, pickPoint.z, slotScratch)
      && slotScratch.x === selectedFork.x && slotScratch.y === selectedFork.y) {
      doFreq(selectedFork);
      return;
    }
    orbit.zoom(dy);
  },
  action: onAction,
});

// ---------------------------------------------------------------------------
// Simulation step + win/fail logic
// ---------------------------------------------------------------------------

function stepSim() {
  wave.step();
  const shattered = board.tick();
  simTime += STEP_DT;
  if (shattered) {
    pieces.shatter(shattered);
    audio.shatter(shattered.band);
    if (shattered.forbidden) audio.fail();
  }
  const st = board.status();
  if (st.failed && !failShown) {
    failShown = true;
    hud.showFail(true);
    victoryTimer = -1;
  } else if (!st.failed && failShown) {
    failShown = false;
    hud.showFail(false);
  }
  if (mode === 'play') {
    if (st.won && victoryTimer < 0) victoryTimer = 0.9;
    if (!st.won) victoryTimer = -1;
  }
}

function completeLevel() {
  const level = LEVELS[levelIndex];
  const forks = board.forks.length;
  const medal = forks <= level.par ? 'or' : forks === level.par + 1 ? 'argent' : 'bronze';
  const prev = save.best[level.id];
  const rank = { or: 3, argent: 2, bronze: 1 };
  if (!prev || rank[medal] > rank[prev.medal] || (medal === prev.medal && forks < prev.forks)) {
    save.best[level.id] = { forks, medal };
  }
  save.unlocked = Math.max(save.unlocked, Math.min(levelIndex + 1, LEVELS.length - 1));
  persist();
  audio.win();
  mode = 'complete';
  hud.showComplete({
    name: level.name, medal, forks, par: level.par,
    poses: board.poses, isLast: levelIndex + 1 >= LEVELS.length,
  });
}

// ---------------------------------------------------------------------------
// Main loop
// ---------------------------------------------------------------------------

let last = performance.now();
let lumResolve = null;

document.addEventListener('visibilitychange', () => {
  // Re-arm the clock on tab return so the accumulator never sees a huge dt.
  if (!document.hidden) last = performance.now();
});

window.addEventListener('resize', () => {
  renderer.setSize(window.innerWidth, window.innerHeight);
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
});

function measureLuminance() {
  return new Promise((resolve) => { lumResolve = resolve; });
}

function readLuminance() {
  const gl = renderer.getContext();
  const w = gl.drawingBufferWidth;
  const h = gl.drawingBufferHeight;
  const buf = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i += 4) {
    sum += 0.2126 * buf[i] + 0.7152 * buf[i + 1] + 0.0722 * buf[i + 2];
  }
  return sum / (w * h);
}

function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) { last = now; return; } // sleep while hidden
  const dt = Math.min((now - last) / 1000, 0.1);
  last = now;

  input.update(dt);
  orbit.update(dt);

  const simulate = mode === 'play' || mode === 'title' || mode === 'complete';
  if (simulate) {
    acc += dt;
    if (acc >= STEP_DT) {
      stepSim();
      // At most one step per rendered frame; cap the leftover so a hiccup
      // never turns into a catch-up spiral.
      acc = Math.min(acc - STEP_DT, STEP_DT);
    }
  }

  if (victoryTimer > 0 && mode === 'play') {
    victoryTimer -= dt;
    if (victoryTimer <= 0) completeLevel();
  }

  // Hover tracking follows the camera even when the pointer rests.
  if (mode === 'play' && lastNdc.valid
    && orbit.pick(lastNdc.x, lastNdc.y, pickPoint)
    && worldToSlot(pickPoint.x, pickPoint.z, hoverStore)) {
    hoverSlot = hoverStore;
  } else {
    hoverSlot = null;
  }

  // Danger voice follows the most charged forbidden crystal.
  let danger = 0;
  if (board) {
    for (const c of board.crystals) {
      if (c.forbidden && !c.shattered) danger = Math.max(danger, c.charge / CHARGE_TIME);
    }
  }
  audio.setDanger(danger);

  surface.update(wave);
  pieces.sync(simTime, selectedFork, mode === 'play' ? hoverSlot : null);
  pieces.update(dt, simTime);
  renderer.render(scene, camera);

  if (lumResolve) {
    const r = lumResolve;
    lumResolve = null;
    r(readLuminance());
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

try {
  if (localStorage.getItem(AUDIO_KEY) === '1') audio.setMuted(true);
} catch (err) { void err; }
hud.setMuted(audio.muted);
orbit.frame();
showTitle();
requestAnimationFrame(frame);

// Automation hooks for the repo's headless tests.
window.game = {
  get mode() { return mode; },
  get levelIndex() { return levelIndex; },
  get board() { return board; },
  wave,
  levels: LEVELS,
  start: startGame,
  loadLevel: (i) => loadLevel(i),
  place: (x, y, band, phase = 0) => { doPlace(x, y, band); if (phase && board.forkAt(x, y)) board.setPhase(board.forkAt(x, y), phase); },
  removeAt: (x, y) => { const f = board.forkAt(x, y); if (f) doRemove(f); },
  undo,
  restart,
  status: () => board.status(),
  slotToWorld: (x, y) => [slotToWorldX(x), slotToWorldZ(y)],
  measureLuminance,
};
window.__ready = true;
