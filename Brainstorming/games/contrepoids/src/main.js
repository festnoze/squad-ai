/**
 * CONTREPOIDS - entry point.
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
import { createState, moveTo, jumpTo, takeItem, dropItem, pushAnvil, DIRS } from './shaft.js';
import { createHistory } from './history.js';
import { createTextures } from './render/textures.js';
import { createRenderer, createScene, buildShaftWalls } from './render/scene.js';
import { createPlatforms } from './render/platforms.js';
import { createRopes } from './render/ropes.js';
import { createPlayer } from './render/player.js';
import { worldX, worldZ } from './render/layout.js';
import { createCameraRig } from './camera.js';
import { createInput } from './input.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';

const KEY_PROGRESS = 'contrepoids.progress';
const KEY_AUDIO = 'contrepoids.audio';
const DT_MAX = 1 / 20;
const ANIM_BASE = 0.3;
const ANIM_MAX = 0.85;

let renderer = null;
let sceneBundle = null;
let platformsView = null;
let ropesView = null;
let playerView = null;
let hud = null;
let audio = null;
let input = null;
let rig = null;

const history = createHistory();

let mode = 'loading';
let state = null;
let levelIndex = 0;
let moves = 0;
let undos = 0;
let facingDir = 2; // south, an arbitrary but stable default
let lastTime = 0;
let rafId = 0;

let progress = { unlocked: 0, best: {} };

// Transition (the single animated interpolation between "before" and "after"
// a legal action). Arrays are indexed by column id, allocated once per level
// so no frame allocates.
let beforeHeights = new Float64Array(0);
let afterHeights = new Float64Array(0);
let displayHeights = new Float64Array(0);
let animT = 1;
let animDur = ANIM_BASE;
let animKind = 'move';
let beforePlayerCol = 0;
let afterPlayerCol = 0;
let bufferedAction = null; // { kind, dir }

const scratchBeforePos = new THREE.Vector3();
const scratchAfterPos = new THREE.Vector3();
const scratchPos = new THREE.Vector3();
const scratchCenter = new THREE.Vector3();

// ---------------------------------------------------------------------------
// Storage
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
// Boot helpers
// ---------------------------------------------------------------------------

function byId(id) {
  return document.getElementById(id);
}

function setMode(next) {
  mode = next;
  bufferedAction = null;
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
  hud.setLevel(levelIndex, LEVELS.length, level.name, level.hint);
  hud.setMoves(moves, level.par);
  hud.setUndo(undos);
  hud.setHolding(state.holding);
}

function columnWorldPoint(col, h, out) {
  return platformsView.surfacePoint(col, h, out);
}

function computeBoundsCenter(out) {
  const b = platformsView.bounds;
  out.set((b.minX + b.maxX) / 2, (b.minY + b.maxY) / 2, (b.minZ + b.maxZ) / 2);
  return out;
}

function playerCurrentWorldPos(out) {
  const col = state.columns[state.playerCol];
  return columnWorldPoint(col, displayHeights[col.id], out);
}

function startLevel(index) {
  levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
  state = createState(LEVELS[levelIndex]);
  history.clear();
  moves = 0;
  undos = 0;
  facingDir = 2;
  bufferedAction = null;

  const n = state.columns.length;
  beforeHeights = new Float64Array(n);
  afterHeights = new Float64Array(n);
  displayHeights = new Float64Array(n);
  for (let i = 0; i < n; i++) displayHeights[i] = state.columns[i].h;
  animT = 1;

  platformsView.build(state);
  platformsView.setHeights(displayHeights);
  ropesView.build(state);
  ropesView.setHeights(state, displayHeights);

  const bounds = platformsView.bounds;
  buildShaftWalls(sceneBundle.shaftGroup, sceneBundle.textures, bounds);
  computeBoundsCenter(scratchCenter);
  const size = Math.max(
    bounds.maxX - bounds.minX,
    bounds.maxY - bounds.minY,
    bounds.maxZ - bounds.minZ,
    3
  );
  rig.frame(scratchCenter, size * 0.62 + 3);

  playerCurrentWorldPos(scratchPos);
  playerView.setPosition(scratchPos.x, scratchPos.y, scratchPos.z);
  playerView.setCarrying(state.holding);

  hud.clearBanner();
  hud.showScreen(null);
  hud.show();
  syncHud();
  setMode('play');
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

function snapshotHeights(target) {
  for (let i = 0; i < state.columns.length; i++) target[i] = state.columns[i].h;
}

function maxDelta() {
  let m = 0;
  for (let i = 0; i < beforeHeights.length; i++) {
    const d = Math.abs(afterHeights[i] - beforeHeights[i]);
    if (d > m) m = d;
  }
  return m;
}

function playActionAudio(kind, res) {
  let sawRope = false;
  let maxAmount = 0;
  for (let i = 0; i < res.events.length; i++) {
    const e = res.events[i];
    if (e.type === 'rope') {
      sawRope = true;
      if (e.amount > maxAmount) maxAmount = e.amount;
    }
  }
  if (kind === 'move') audio.step();
  else if (kind === 'jump') audio.jump();
  else if (kind === 'take') audio.take();
  else if (kind === 'drop') audio.drop();
  else if (kind === 'push') audio.push();
  if (sawRope) audio.pulley(maxAmount);
}

/** Runs one legal action, or buffers it if the scene is mid transition. */
function perform(kind, dir) {
  if (mode !== 'play') return;
  if (animT < 1) {
    bufferedAction = { kind, dir };
    return;
  }

  let res;
  beforePlayerCol = state.playerCol;
  snapshotHeights(beforeHeights);

  // shaft.js guarantees zero mutation when an action is illegal, so the
  // pre-action clone can always be pushed first and discarded (a no-op undo)
  // on failure, instead of needing a second code path to snapshot it.
  history.push(state);
  if (kind === 'move') res = moveTo(state, dir);
  else if (kind === 'jump') res = jumpTo(state, dir);
  else if (kind === 'take') res = takeItem(state);
  else if (kind === 'drop') res = dropItem(state);
  else res = pushAnvil(state, dir);

  if (!res.ok) {
    history.undo(state);
    audio.blocked();
    if (kind === 'move' || kind === 'jump') hud.toast('Impossible : plateforme hors de portee.');
    else if (kind === 'take') hud.toast('Rien a prendre ici.');
    else if (kind === 'drop') hud.toast('Vos mains sont vides, ou la case est occupee.');
    else hud.toast("Pas d'enclume a niveau egal dans cette direction.");
    return;
  }

  moves++;
  afterPlayerCol = state.playerCol;
  snapshotHeights(afterHeights);
  animDur = Math.min(ANIM_MAX, ANIM_BASE + maxDelta() * 0.05);
  animKind = kind;
  animT = 0;

  playerView.setCarrying(state.holding);
  playActionAudio(kind, res);
  hud.clearBanner();
  syncHud();

  if (state.status === 'won') {
    setMode('won-pending');
  }
}

function doMove(action) {
  const dir = rig.resolveDirection(action);
  facingDir = dir;
  perform('move', dir);
}

function doJump() {
  perform('jump', facingDir);
}

function doAction() {
  if (mode !== 'play') return;
  if (animT < 1) {
    bufferedAction = { kind: 'action' };
    return;
  }
  if (state.holding) {
    perform('drop', 0);
  } else {
    const col = state.columns[state.playerCol];
    if (col.item) perform('take', 0);
    else perform('push', facingDir);
  }
}

function doUndo() {
  if (mode !== 'play') return;
  if (animT < 1) return;
  if (!history.undo(state)) {
    hud.toast('Rien a annuler.');
    return;
  }
  moves = Math.max(0, moves - 1);
  undos++;
  bufferedAction = null;
  setMode('play');

  snapshotHeights(afterHeights);
  beforeHeights.set(afterHeights);
  displayHeights.set(afterHeights);
  animT = 1;
  platformsView.setHeights(displayHeights);
  ropesView.setHeights(state, displayHeights);
  platformsView.syncItems(state);
  playerCurrentWorldPos(scratchPos);
  playerView.setPosition(scratchPos.x, scratchPos.y, scratchPos.z);
  playerView.setCarrying(state.holding);

  hud.clearBanner();
  audio.undo();
  syncHud();
}

function doRestart() {
  if (mode !== 'play' && mode !== 'paused' && mode !== 'won') return;
  audio.click();
  startLevel(levelIndex);
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

function solveLevel() {
  setMode('won');
  const level = LEVELS[levelIndex];
  const best = progress.best[levelIndex];
  if (!Number.isFinite(best) || moves < best) progress.best[levelIndex] = moves;
  if (levelIndex + 1 < LEVELS.length && progress.unlocked < levelIndex + 1) {
    progress.unlocked = levelIndex + 1;
  }
  saveProgress();

  const over = moves - level.par;
  const perfect = over <= 0;
  audio.win(perfect);
  byId('win-title').textContent = perfect ? 'SOLUTION OPTIMALE' : 'PUITS FRANCHI';
  byId('win-sub').textContent = moves + ' action' + (moves > 1 ? 's' : '') + ' - par ' + level.par;
  let medal = 'Bronze';
  if (over <= 0) medal = 'Or';
  else if (over === 1) medal = 'Argent';
  byId('win-medal').textContent = 'Medaille : ' + medal + (perfect ? ' (aucune amelioration possible)' : '.');
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
    solved + ' niveaux resolus, ' + medals + ' medailles d\'or sur ' + LEVELS.length + '. ' +
    (medals === LEVELS.length
      ? 'Chaque niveau a ete resolu avec le nombre d\'actions optimal.'
      : 'Les niveaux sans medaille d\'or peuvent encore etre resolus en moins d\'actions.');
  hud.showScreen('screen-end');
}

function goTitle() {
  setMode('title');
  hud.hide();
  hud.clearBanner();
  refreshTitleScreen();
  hud.showScreen('screen-title');
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
  if (command === 'undo') {
    doUndo();
    return;
  }
  if (command === 'restart') {
    doRestart();
    return;
  }
  if (mode !== 'play') return;
  if (command === 'jump') doJump();
  else if (command === 'action') doAction();
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

function easeInOut(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function resize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  renderer.setSize(w, h, false);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  rig.resize(w / Math.max(1, h));
}

function updateTransition(dt) {
  if (animT >= 1) return;
  animT = Math.min(1, animT + dt / animDur);
  const eased = easeInOut(animT);
  for (let i = 0; i < displayHeights.length; i++) {
    displayHeights[i] = beforeHeights[i] + (afterHeights[i] - beforeHeights[i]) * eased;
  }
  platformsView.setHeights(displayHeights);
  ropesView.setHeights(state, displayHeights);
  platformsView.syncItems(state);

  const beforeCol = state.columns[beforePlayerCol];
  const afterCol = state.columns[afterPlayerCol];
  columnWorldPoint(beforeCol, beforeHeights[beforeCol.id], scratchBeforePos);
  columnWorldPoint(afterCol, afterHeights[afterCol.id], scratchAfterPos);
  scratchPos.lerpVectors(scratchBeforePos, scratchAfterPos, eased);
  if (animKind === 'jump') {
    scratchPos.y += Math.sin(Math.PI * animT) * 0.35;
  }
  playerView.setPosition(scratchPos.x, scratchPos.y, scratchPos.z);
  if (beforePlayerCol !== afterPlayerCol) {
    const dx = worldX(afterCol.gx) - worldX(beforeCol.gx);
    const dz = worldZ(afterCol.gz) - worldZ(beforeCol.gz);
    if (Math.abs(dx) + Math.abs(dz) > 1e-4) playerView.setFacing(Math.atan2(dx, dz));
  } else {
    const [dx, dz] = DIRS[facingDir];
    playerView.setFacing(Math.atan2(dx, dz));
  }

  if (animT >= 1) {
    if (mode === 'won-pending') {
      solveLevel();
    } else if (bufferedAction) {
      const next = bufferedAction;
      bufferedAction = null;
      if (next.kind === 'action') doAction();
      else perform(next.kind, next.dir);
    }
  }
}

function frame(now) {
  rafId = requestAnimationFrame(frame);
  if (document.hidden) {
    lastTime = now;
    return;
  }
  const dt = Math.min(DT_MAX, (now - lastTime) / 1000 || 0);
  lastTime = now;

  updateTransition(dt);
  playerView.update(dt, animT < 1 && animKind === 'move');

  if (mode === 'play' || mode === 'won-pending') {
    playerCurrentWorldPos(scratchPos);
    if (animT >= 1) playerView.setPosition(scratchPos.x, scratchPos.y, scratchPos.z);
    rig.setFocus(scratchPos);
  }
  rig.update(dt);
  hud.update(dt);

  renderer.render(sceneBundle.scene, rig.camera);
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

async function boot() {
  hud = createHUD();
  hud.setLoading(6, 'Renderer');
  await paint();

  const canvas = byId('scene');
  renderer = createRenderer(canvas);
  renderer.setSize(window.innerWidth, window.innerHeight, false);

  hud.setLoading(24, 'Textures');
  await paint();
  const textures = createTextures(renderer);

  hud.setLoading(48, 'Scene');
  await paint();
  sceneBundle = createScene();
  sceneBundle.textures = textures;
  platformsView = createPlatforms(textures);
  ropesView = createRopes(textures);
  playerView = createPlayer(textures);
  sceneBundle.scene.add(platformsView.group);
  sceneBundle.scene.add(ropesView.group);
  sceneBundle.scene.add(playerView.group);

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
  input.onMove(doMove);
  input.onCommand(onCommand);
  input.onOrbit((dx, dy) => rig.orbit(dx, dy));
  input.onZoom((delta) => rig.zoom(delta));
  wireButtons();

  hud.setLoading(90, 'Niveaux');
  await paint();
  loadProgress();

  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) lastTime = performance.now();
  });
  window.addEventListener('pointerdown', () => audio.resume(), { once: true });
  window.addEventListener('keydown', () => audio.resume(), { once: true });

  startLevel(0);

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
    rig,
    scene: sceneBundle.scene,
    renderer,
    audio,
  };
  window.__ready = true;

  lastTime = performance.now();
  rafId = requestAnimationFrame(frame);
}

boot().catch(fail);
