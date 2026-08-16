/**
 * GRAVITE NEUF - entry point.
 *
 * Boots the renderer, wires every subsystem, and owns the state machine:
 *   loading -> title -> play <-> paused
 *                        |-> won -> play (next level) ... -> end
 *
 * The whole boot runs inside a try/catch that routes any failure to
 * window.__fail (declared in index.html) so a broken machine shows the reason
 * instead of a black canvas.
 */

import * as THREE from 'three';
import { LEVELS } from './levels.js';
import { createState, DIR_LABEL } from './world.js';
import { applyGravity, settleInitial } from './gravity.js';
import { createHistory } from './history.js';
import { createTextures } from './textures.js';
import { createVoxels } from './voxels.js';
import { createSky } from './sky.js';
import { createCameraRig } from './camera.js';
import { createInput } from './input.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';

const KEY_PROGRESS = 'gravite_neuf.progress';
const KEY_AUDIO = 'gravite_neuf.audio';
const DT_MAX = 1 / 20;

let renderer = null;
let scene = null;
let rig = null;
let textures = null;
let voxels = null;
let sky = null;
let hud = null;
let audio = null;
let input = null;
let sunLight = null;

const history = createHistory();

let mode = 'loading';
let state = null;
let levelIndex = 0;
let moves = 0;
let undos = 0;
let pending = null;
let bufferedTilt = null;
let elapsed = 0;
let lastTime = 0;
let rafId = 0;

let progress = { unlocked: 0, best: {} };

// ---------------------------------------------------------------------------
// Storage. Every access is guarded: a disabled or full localStorage must never
// take the game down with it.
// ---------------------------------------------------------------------------

function loadJSON(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : fallback;
  } catch (e) {
    return fallback;
  }
}

function saveJSON(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    // Storage unavailable: progress stays in memory for this session only.
  }
}

function loadProgress() {
  const raw = loadJSON(KEY_PROGRESS, null);
  progress = {
    unlocked: raw && Number.isFinite(raw.unlocked) ? Math.max(0, Math.min(LEVELS.length - 1, raw.unlocked)) : 0,
    best: raw && raw.best && typeof raw.best === 'object' ? raw.best : {},
  };
}

function saveProgress() {
  saveJSON(KEY_PROGRESS, progress);
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

function byId(id) {
  return document.getElementById(id);
}

/** Single place where the state machine moves, so input follows it for free. */
function setMode(next) {
  mode = next;
  bufferedTilt = null;
  if (input) input.setEnabled(next === 'play');
}

function fail(err) {
  const message = err && err.message ? err.message : String(err);
  const where = err && err.stack ? err.stack : '';
  if (typeof window.__fail === 'function') window.__fail(message, where);
  else console.error(err);
}

function paint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => window.setTimeout(resolve, 0));
  });
}

function buildScene() {
  scene = new THREE.Scene();
  // The sky dome covers the frame, but a pure black clear colour would show
  // through for the one frame between a resize and the next dome draw, and it is
  // what a failed dome would leave behind. Keep the ground colour of the sky.
  scene.background = new THREE.Color(0x0a1330);

  const ambient = new THREE.AmbientLight(0x9db4dc, 0.42);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0xa8c8ff, 0x2a2438, 0.55);
  scene.add(hemi);

  sunLight = new THREE.DirectionalLight(0xfff2d8, 1.35);
  sunLight.position.set(14, 22, 12);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(1024, 1024);
  sunLight.shadow.camera.near = 1;
  sunLight.shadow.camera.far = 90;
  sunLight.shadow.bias = -0.0016;
  sunLight.shadow.normalBias = 0.035;
  scene.add(sunLight);
  scene.add(sunLight.target);

  const fill = new THREE.DirectionalLight(0x7fa4ff, 0.42);
  fill.position.set(-12, 6, -14);
  scene.add(fill);
}

function frameShadow(radius) {
  const r = radius + 1.5;
  const cam = sunLight.shadow.camera;
  cam.left = -r;
  cam.right = r;
  cam.top = r;
  cam.bottom = -r;
  cam.near = 1;
  cam.far = radius * 6 + 40;
  cam.updateProjectionMatrix();
  const dist = radius * 2.6 + 12;
  sunLight.position.set(0.52 * dist, 0.78 * dist, 0.42 * dist);
  sunLight.target.position.set(0, 0, 0);
  sunLight.target.updateMatrixWorld();
}

// ---------------------------------------------------------------------------
// Level lifecycle
// ---------------------------------------------------------------------------

function levelEntries() {
  const out = [];
  for (let i = 0; i < LEVELS.length; i++) {
    const best = progress.best[i];
    out.push({
      name: LEVELS[i].name,
      unlocked: i <= progress.unlocked,
      best: Number.isFinite(best) ? best : null,
      par: LEVELS[i].par,
    });
  }
  return out;
}

function refreshTitleScreen() {
  hud.buildLevelGrid(levelEntries(), (i) => {
    audio.resume();
    audio.click();
    startLevel(i);
  });
  const btn = byId('btn-play');
  const solvedAny = Object.keys(progress.best).length > 0;
  btn.textContent = solvedAny ? 'Reprendre au niveau ' + (progress.unlocked + 1) : 'Commencer';
}

function syncHud() {
  const level = LEVELS[levelIndex];
  hud.setLevel(levelIndex, LEVELS.length, level.name, level.hint, level.par);
  hud.setMoves(moves, level.par);
  hud.setKeys(state.keysTaken, state.keysTotal);
  hud.setUndo(undos);
  hud.setGravity(DIR_LABEL[state.gravity], state.gravity);
}

function startLevel(index) {
  levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
  state = createState(LEVELS[levelIndex]);
  settleInitial(state);
  history.clear();
  moves = 0;
  undos = 0;
  pending = null;

  voxels.build(state);
  frameShadow(voxels.radius);
  rig.reset();
  rig.resetOrbit();
  rig.frame(voxels.radius);
  sky.setDirection(state.gravity, true);

  hud.clearBanner();
  hud.showScreen(null);
  hud.show();
  syncHud();
  setMode('play');
}

function finishAnimation() {
  const res = pending;
  pending = null;
  if (!res) return;

  let sawKey = false;
  let sawSpike = false;
  let sawVoid = false;
  let sawGlue = false;
  for (let i = 0; i < res.events.length; i++) {
    const e = res.events[i];
    if (e.type === 'key') sawKey = true;
    else if (e.type === 'spike') sawSpike = true;
    else if (e.type === 'void') sawVoid = true;
    else if (e.type === 'glue') sawGlue = true;
  }

  if (sawGlue) audio.glue();
  if (sawKey) audio.key();
  if (sawSpike) audio.spike();
  if (sawVoid) audio.voidFall();
  if (res.moved && !sawSpike && !sawVoid) audio.land(0.6);

  voxels.syncStatics(state);
  syncHud();

  if (state.status === 'won') {
    solveLevel();
    return;
  }
  if (state.status === 'lost') {
    // A key pressed during the fatal fall must not fire into a dead board.
    bufferedTilt = null;
    hud.banner('PERDU', state.reason + '  -  Ctrl+Z pour annuler, R pour recommencer', false, 0);
    audio.fail();
    return;
  }
  if (state.crateLost) {
    state.crateLost = false;
    hud.toast('Une caisse est perdue dans le vide.');
  }
}

function solveLevel() {
  setMode('won');
  const level = LEVELS[levelIndex];
  const best = progress.best[levelIndex];
  if (!Number.isFinite(best) || moves < best) progress.best[levelIndex] = moves;
  if (levelIndex + 1 < LEVELS.length && progress.unlocked < levelIndex + 1) {
    progress.unlocked = levelIndex + 1;
  }
  saveProgress();

  const perfect = moves <= level.par;
  audio.win(perfect);
  byId('win-title').textContent = perfect ? 'SOLUTION OPTIMALE' : 'NIVEAU RESOLU';
  byId('win-sub').textContent = moves + ' coup' + (moves > 1 ? 's' : '') + ' - par ' + level.par;
  byId('win-medal').textContent = perfect
    ? 'Medaille obtenue : impossible de faire mieux.'
    : 'Le par est de ' + level.par + ' coups. Rejouez pour la medaille.';
  byId('btn-next').textContent = levelIndex + 1 < LEVELS.length ? 'Niveau suivant' : 'Voir le bilan';
  hud.showScreen('screen-win');
}

function showEnd() {
  setMode('end');
  let medals = 0;
  let solved = 0;
  for (let i = 0; i < LEVELS.length; i++) {
    const b = progress.best[i];
    if (!Number.isFinite(b)) continue;
    solved++;
    if (b <= LEVELS[i].par) medals++;
  }
  byId('end-stats').textContent =
    solved + ' niveaux resolus, ' + medals + ' medailles sur ' + LEVELS.length + '. ' +
    (medals === LEVELS.length
      ? 'Chaque niveau a ete resolu en un nombre de coups optimal. Rien a ajouter.'
      : 'Les niveaux sans medaille peuvent encore etre resolus en moins de coups.');
  hud.showScreen('screen-end');
}

function goTitle() {
  setMode('title');
  hud.hide();
  hud.clearBanner();
  refreshTitleScreen();
  hud.showScreen('screen-title');
}

// ---------------------------------------------------------------------------
// Player actions
// ---------------------------------------------------------------------------

function doTilt(action) {
  if (mode !== 'play') return;
  if (state.status === 'lost') {
    // Nothing a tilt can do brings back a dead cube, a destroyed key or a glued
    // player. Racking up moves on a dead board only made the counter lie.
    hud.toast('Niveau perdu : Ctrl+Z pour annuler, R pour recommencer.');
    return;
  }
  if (voxels.busy || rig.tilting) {
    // Hold the request instead of dropping it. A key pressed during the roll
    // used to vanish, which read as "the game ignores me" far more often than
    // the half second of animation would suggest.
    bufferedTilt = action;
    return;
  }
  bufferedTilt = null;
  const dir = rig.resolveDirection(action);

  // Asking for the direction gravity already points at changes strictly nothing,
  // so it costs neither a move nor a history entry.
  if (dir === state.gravity) {
    hud.toast('La gravite pointe deja dans cette direction.');
    return;
  }

  history.push(state);
  const res = applyGravity(state, dir);

  // A tilt that moves nothing is still a legal turn. Refusing it stranded the
  // player: once the structure was settled against every reachable face, every
  // key was rejected and the level looked broken. The world always rolls now.
  moves++;
  hud.clearBanner();
  if (res.moved) {
    audio.tilt(dir);
  } else {
    audio.blocked();
    hud.toast('Rien ne bouge dans cette direction, mais le monde a bascule.');
  }
  rig.setGravity(dir, false);
  sky.setDirection(dir, false);
  voxels.setGravityFace(dir);
  voxels.play(res.steps);
  pending = res;
  syncHud();
}

function doUndo() {
  if (mode !== 'play' || voxels.busy || rig.tilting) return;
  if (!history.undo(state)) {
    hud.toast('Rien a annuler.');
    return;
  }
  moves = Math.max(0, moves - 1);
  undos++;
  pending = null;
  bufferedTilt = null;
  voxels.applyState(state);
  voxels.syncStatics(state);
  rig.setGravity(state.gravity, false);
  sky.setDirection(state.gravity, false);
  voxels.setGravityFace(state.gravity);
  hud.clearBanner();
  audio.undo();
  syncHud();
}

function doRestart() {
  if (mode !== 'play' && mode !== 'paused') return;
  audio.click();
  startLevel(levelIndex);
}

function doStep(delta) {
  const target = levelIndex + delta;
  if (target < 0 || target >= LEVELS.length) return;
  if (target > progress.unlocked) {
    hud.toast('Niveau encore verrouille.');
    return;
  }
  audio.click();
  startLevel(target);
}

function togglePause() {
  if (mode === 'play') {
    setMode('paused');
    byId('pause-sub').textContent = 'Niveau ' + (levelIndex + 1) + ' - ' + LEVELS[levelIndex].name;
    hud.showScreen('screen-pause');
  } else if (mode === 'paused') {
    setMode('play');
    hud.showScreen(null);
  }
}

function onCommand(command) {
  audio.resume();
  if (command === 'pause') {
    togglePause();
    return;
  }
  if (command === 'mute') {
    const muted = audio.toggleMute();
    saveJSON(KEY_AUDIO, { volume: audio.getVolume(), muted });
    hud.toast(muted ? 'Son coupe.' : 'Son actif.');
    return;
  }
  if (mode !== 'play') return;
  if (command === 'undo') doUndo();
  else if (command === 'restart') doRestart();
  else if (command === 'next') doStep(1);
  else if (command === 'prev') doStep(-1);
}

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

function wireButtons() {
  const click = (id, fn) => {
    const node = byId(id);
    if (node) {
      node.addEventListener('click', () => {
        audio.resume();
        audio.click();
        fn();
      });
    }
  };

  click('btn-play', () => startLevel(progress.unlocked));
  click('btn-clear', () => {
    progress = { unlocked: 0, best: {} };
    saveProgress();
    refreshTitleScreen();
    hud.toast('Progression effacee.');
  });
  click('btn-resume', () => togglePause());
  click('btn-restart-pause', () => startLevel(levelIndex));
  click('btn-title-pause', goTitle);
  click('btn-next', () => {
    if (levelIndex + 1 < LEVELS.length) startLevel(levelIndex + 1);
    else showEnd();
  });
  click('btn-replay', () => startLevel(levelIndex));
  click('btn-title-win', goTitle);
  click('btn-title-end', goTitle);

  const volume = byId('volume');
  const volumeValue = byId('volume-value');
  volume.addEventListener('input', () => {
    const v = Number(volume.value);
    volumeValue.textContent = String(v);
    audio.setVolume(v / 100);
    audio.resume();
    saveJSON(KEY_AUDIO, { volume: v / 100, muted: audio.muted });
  });
}

// ---------------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------------

function resize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  renderer.setSize(w, h, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  rig.resize(w / Math.max(1, h));
}

function frame(now) {
  rafId = requestAnimationFrame(frame);
  if (document.hidden) {
    // A backgrounded tab must not bank time: the clamp below already caps a
    // single frame, but resetting the clock keeps the very first frame after the
    // return identical to any other one.
    lastTime = now;
    return;
  }
  const dt = Math.min(DT_MAX, (now - lastTime) / 1000 || 0);
  lastTime = now;
  elapsed += dt;

  rig.update(dt);
  voxels.group.quaternion.copy(rig.worldQuat);
  voxels.update(dt, elapsed);
  sky.update(dt, elapsed);
  hud.update(dt);

  if (pending && !voxels.busy) finishAnimation();
  if (bufferedTilt && mode === 'play' && !pending && !voxels.busy && !rig.tilting) {
    const queued = bufferedTilt;
    bufferedTilt = null;
    doTilt(queued);
  }

  renderer.render(scene, rig.camera);
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

async function boot() {
  hud = createHUD();
  hud.setLoading(6, 'Renderer');
  await paint();

  const canvas = byId('scene');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.22;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  hud.setLoading(24, 'Textures');
  await paint();
  textures = createTextures(renderer);

  hud.setLoading(48, 'Scene');
  await paint();
  buildScene();
  sky = createSky(scene);
  voxels = createVoxels(textures);
  scene.add(voxels.group);

  hud.setLoading(70, 'Camera et interface');
  await paint();
  rig = createCameraRig(window.innerWidth / Math.max(1, window.innerHeight));
  audio = createAudio();
  const audioPrefs = loadJSON(KEY_AUDIO, null);
  if (audioPrefs) {
    if (Number.isFinite(audioPrefs.volume)) audio.setVolume(audioPrefs.volume);
    if (audioPrefs.muted) audio.setMuted(true);
  }
  const volume = byId('volume');
  volume.value = String(Math.round(audio.getVolume() * 100));
  byId('volume-value').textContent = volume.value;

  input = createInput(canvas);
  input.onTilt(doTilt);
  input.onCommand(onCommand);
  input.onOrbit((dx, dy) => rig.orbit(dx, dy));
  input.onZoom((delta) => rig.zoom(delta));
  wireButtons();

  hud.setLoading(90, 'Niveaux');
  await paint();
  loadProgress();

  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', () => {
    // Coming back from a hidden tab: the clock restarts here, never on a stale
    // timestamp from before the tab went away.
    if (!document.hidden) lastTime = performance.now();
  });
  window.addEventListener('pointerdown', () => audio.resume(), { once: true });
  window.addEventListener('keydown', () => audio.resume(), { once: true });

  // The first level is built once so the structure is already behind the menu.
  state = createState(LEVELS[0]);
  settleInitial(state);
  voxels.build(state);
  frameShadow(voxels.radius);
  rig.frame(voxels.radius);
  sky.setDirection(state.gravity, true);

  hud.setLoading(100, 'Pret');
  await paint();
  resize();
  goTitle();

  window.game = {
    get state() {
      return state;
    },
    get levelIndex() {
      return levelIndex;
    },
    get moves() {
      return moves;
    },
    get mode() {
      return mode;
    },
    LEVELS,
    voxels,
    rig,
    scene,
    renderer,
    audio,
    tilt: doTilt,
    undo: doUndo,
    start: startLevel,
  };
  window.__ready = true;

  lastTime = performance.now();
  rafId = requestAnimationFrame(frame);
}

boot().catch(fail);
