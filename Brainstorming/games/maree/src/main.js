/**
 * MAREE - entry point. Boots the renderer, wires every subsystem and owns the
 * state machine:
 *   loading -> title -> play <-> paused
 *                        |-> won -> play (next level) ... -> end
 *
 * The whole boot runs inside a try/catch that routes any failure to
 * window.__fail (declared in index.html) so a broken machine shows the reason
 * instead of a black canvas.
 */

import * as THREE from 'three';
import { LEVELS } from './levels.js';
import { createWorld, rebuildGroups, cloneWorld } from './world.js';
import { requestLevelChange, toggleGate, updateFreeze, updateVisualLevels } from './water.js';
import { createHistory } from './history.js';
import { initExplorer, requestRepath, tickExplorer } from './explorer.js';
import { createTextures } from './textures.js';
import { createSceneObjects } from './render/scene.js';
import { createWaterObjects } from './render/water.js';
import { createExplorerObject } from './render/explorer.js';
import { createCameraRig } from './camera.js';
import { createInput } from './input.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';
import { KEY_PROGRESS, KEY_AUDIO, PALETTE } from './config.js';

const DT_MAX = 1 / 20;

let renderer = null;
let scene = null;
let rig = null;
let textures = null;
let sceneObjects = null;
let waterObjects = null;
let explorerObject = null;
let hud = null;
let audio = null;
let input = null;
let raycaster = null;
const pickables = [];

const history = createHistory();

let mode = 'loading'; // loading | title | play | paused | won | end
let state = null;
let levelIndex = 0;
let selected = 0;
let moves = 0;
let elapsed = 0;
let lastTime = 0;
let rafId = 0;

let progress = { unlocked: 0, best: {} };

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
  scene.background = new THREE.Color(PALETTE.fog);
  scene.fog = new THREE.Fog(PALETTE.fog, 20, 90);

  const ambient = new THREE.AmbientLight(0x9fd0d6, 0.55);
  scene.add(ambient);

  const hemi = new THREE.HemisphereLight(0xbfe7ea, 0x1a2e30, 0.5);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xfff2d8, 1.15);
  sun.position.set(10, 18, 8);
  sun.castShadow = true;
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 80;
  sun.shadow.bias = -0.0015;
  sun.shadow.normalBias = 0.03;
  scene.add(sun);
  scene.add(sun.target);

  const fill = new THREE.DirectionalLight(0x6fc0d6, 0.35);
  fill.position.set(-10, 8, -8);
  scene.add(fill);

  return sun;
}

let sunLight = null;

function frameShadow(center, radius) {
  const r = radius + 2;
  const cam = sunLight.shadow.camera;
  cam.left = -r;
  cam.right = r;
  cam.top = r;
  cam.bottom = -r;
  cam.near = 1;
  cam.far = radius * 4 + 30;
  cam.updateProjectionMatrix();
  sunLight.position.set(center.x + r * 0.7, r * 1.4 + 6, center.z + r * 0.5);
  sunLight.target.position.copy(center);
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

function collectWaterPickables() {
  const list = [];
  waterObjects.group.traverse((obj) => {
    if (obj.userData && obj.userData.type === 'water') list.push({ object: obj, type: 'water', index: obj.userData.basin });
  });
  return list;
}

function syncHud() {
  const level = LEVELS[levelIndex];
  hud.setLevel(levelIndex, LEVELS.length, level.name, level.hint, level.par);
  hud.setMoves(moves, level.par);
  hud.setUndo(history.depth);
  hud.buildBasins(state.basins, selected, (i) => selectBasin(i));
}

function startLevel(index) {
  levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
  const level = LEVELS[levelIndex];
  state = createWorld(level);
  initExplorer(state);
  history.clear();
  moves = 0;
  selected = state.basins.length ? 0 : -1;

  sceneObjects.build(state);
  waterObjects.build(state);
  frameShadow(sceneObjects.center, sceneObjects.radius);
  rig.frame(sceneObjects.center, sceneObjects.radius);

  pickables.length = 0;
  for (let i = 0; i < sceneObjects.gates.length; i++) pickables.push({ object: sceneObjects.gates[i].holder, type: 'gate', index: i });
  for (const p of collectWaterPickables()) pickables.push(p);

  hud.clearBanner();
  hud.showScreen(null);
  hud.show();
  syncHud();
  setMode('play');
}

function medalFor(movesUsed, par) {
  const diff = movesUsed - par;
  if (diff <= 0) return 'or';
  if (diff === 1) return 'argent';
  return 'bronze';
}

function solveLevel() {
  setMode('won');
  const level = LEVELS[levelIndex];
  const best = progress.best[levelIndex];
  if (!Number.isFinite(best) || moves < best) progress.best[levelIndex] = moves;
  if (levelIndex + 1 < LEVELS.length && progress.unlocked < levelIndex + 1) progress.unlocked = levelIndex + 1;
  saveProgress();

  const medal = medalFor(moves, level.par);
  audio.win();
  byId('win-title').textContent = medal === 'or' ? 'SOLUTION PARFAITE' : 'BASSIN FRANCHI';
  byId('win-sub').textContent = moves + ' geste' + (moves > 1 ? 's' : '') + ' - par ' + level.par;
  const medalText = { or: 'Medaille d\'or : le par exact.', argent: 'Medaille d\'argent : un geste de plus que le par.', bronze: 'Medaille de bronze. Rejouez pour une meilleure medaille.' };
  byId('win-medal').textContent = medalText[medal];
  byId('btn-next').textContent = levelIndex + 1 < LEVELS.length ? 'Niveau suivant' : 'Voir le bilan';
  hud.showScreen('screen-win');
}

function showEnd() {
  setMode('end');
  let solved = 0;
  let golds = 0;
  for (let i = 0; i < LEVELS.length; i++) {
    const b = progress.best[i];
    if (!Number.isFinite(b)) continue;
    solved++;
    if (b <= LEVELS[i].par) golds++;
  }
  byId('end-stats').textContent =
    solved + ' niveaux resolus, ' + golds + ' medailles d\'or sur ' + LEVELS.length + '. ' +
    (golds === LEVELS.length ? 'Chaque bassin a ete franchi au nombre de gestes optimal.' : 'Les niveaux sans or peuvent encore etre rejoues.');
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

function selectBasin(index) {
  if (mode !== 'play' || index < 0 || index >= state.basins.length) return;
  selected = index;
  audio.select();
  syncHud();
}

/** Runs a mutation that may turn out to be a no-op, only charging a move
 * (and a history entry) when the world actually changed. */
function tryMutate(mutateFn) {
  const before = cloneWorld(state);
  const changed = mutateFn();
  if (changed) {
    history.pushSnapshot(before);
    moves++;
  }
  return changed;
}

function doLevelChange(delta) {
  if (mode !== 'play' || state.explorer.status !== 'alive') return;
  if (selected < 0) {
    hud.toast('Choisissez d\'abord un bassin.');
    return;
  }
  const changed = tryMutate(() => requestLevelChange(state, selected, delta).changed);
  if (changed) {
    audio.resume();
    if (delta > 0) audio.raise();
    else audio.lower();
    requestRepath(state);
  } else {
    hud.toast('Ce bassin est deja a ce niveau.');
  }
  syncHud();
}

function doGateToggle(gateIndex) {
  if (mode !== 'play' || state.explorer.status !== 'alive') return;
  tryMutate(() => {
    toggleGate(state, gateIndex);
    return true;
  });
  const open = state.gates[gateIndex].open;
  sceneObjects.setGateOpen(gateIndex, open);
  if (open) audio.gateOpen();
  else audio.gateClose();
  requestRepath(state);
  syncHud();
}

function doUndo() {
  if (mode !== 'play') return;
  if (!history.undo(state)) {
    hud.toast('Rien a annuler.');
    return;
  }
  moves = Math.max(0, moves - 1);
  rebuildGroups(state);
  requestRepath(state);
  for (let i = 0; i < state.gates.length; i++) sceneObjects.setGateOpen(i, state.gates[i].open);
  hud.clearBanner();
  audio.undo();
  syncHud();
}

function doRestart() {
  if (mode !== 'play' && mode !== 'paused' && mode !== 'won') return;
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
  if (command === 'undo') {
    doUndo();
    return;
  }
  if (command === 'restart') {
    doRestart();
    return;
  }
  if (mode !== 'play') return;
  if (command === 'next') doStep(1);
  else if (command === 'prev') doStep(-1);
  else if (command && command.indexOf('basin') === 0) {
    const n = Number(command.slice(5)) - 1;
    selectBasin(n);
  }
}

function onClickCanvas(clientX, clientY) {
  if (mode !== 'play' || !pickables.length) return;
  const rect = renderer.domElement.getBoundingClientRect();
  const ndc = new THREE.Vector2(
    ((clientX - rect.left) / rect.width) * 2 - 1,
    -((clientY - rect.top) / rect.height) * 2 + 1
  );
  raycaster.setFromCamera(ndc, rig.camera);
  const objects = pickables.map((p) => p.object);
  const hits = raycaster.intersectObjects(objects, true);
  if (!hits.length) return;
  let hitObj = hits[0].object;
  let match = null;
  while (hitObj && !match) {
    match = pickables.find((p) => p.object === hitObj);
    hitObj = hitObj.parent;
  }
  if (!match) return;
  if (match.type === 'gate') doGateToggle(match.index);
  else if (match.type === 'water') selectBasin(match.index);
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
    lastTime = now;
    return;
  }
  const dt = Math.min(DT_MAX, (now - lastTime) / 1000 || 0);
  lastTime = now;
  elapsed += dt;

  input.applyKeyOrbit(dt);
  rig.update(dt);

  if (mode === 'play' && state) {
    const wasAlive = state.explorer.status === 'alive';
    updateVisualLevels(state, dt);
    const iceCountsBefore = state.basins.map((b) => b.iceLevels.length);
    updateFreeze(state, dt);
    for (let i = 0; i < state.basins.length; i++) {
      if (state.basins[i].iceLevels.length > iceCountsBefore[i]) {
        audio.freeze();
        break;
      }
    }
    const stepTBefore = state.explorer.stepT;
    tickExplorer(state, dt);
    if (stepTBefore >= 1 && state.explorer.status === 'alive' && state.explorer.stepT < 1) {
      audio.step(state.explorer.swimming);
    }
    hud.updateBasinValues(state.basins, selected);
    if (wasAlive && state.explorer.status === 'won') {
      solveLevel();
    } else if (wasAlive && state.explorer.status === 'drowned') {
      audio.drown();
      hud.banner('NOYADE', 'Ctrl+Z pour annuler, R pour recommencer', false, 0);
    }
  }

  if (sceneObjects) sceneObjects.update(dt, elapsed);
  if (waterObjects && state) waterObjects.update(state, dt, elapsed);
  if (explorerObject && state) explorerObject.update(state, dt, elapsed);
  hud.update(dt);

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
  renderer.toneMappingExposure = 1.1;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  hud.setLoading(24, 'Textures');
  await paint();
  textures = createTextures();

  hud.setLoading(45, 'Scene');
  await paint();
  sunLight = buildScene();
  sceneObjects = createSceneObjects(textures);
  waterObjects = createWaterObjects(textures);
  explorerObject = createExplorerObject(textures);
  scene.add(sceneObjects.group, waterObjects.group, explorerObject.object);
  raycaster = new THREE.Raycaster();

  hud.setLoading(68, 'Camera et audio');
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
  input.onCommand(onCommand);
  input.onLevel(doLevelChange);
  input.onOrbit((dx, dy) => rig.orbit(dx, dy));
  input.onZoom((delta) => rig.zoom(delta));
  input.onClick(onClickCanvas);
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

  // The first level sits built behind the title screen so it is never a bare
  // black canvas while the menu is up.
  levelIndex = 0;
  state = createWorld(LEVELS[0]);
  initExplorer(state);
  selected = state.basins.length ? 0 : -1;
  sceneObjects.build(state);
  waterObjects.build(state);
  frameShadow(sceneObjects.center, sceneObjects.radius);
  rig.frame(sceneObjects.center, sceneObjects.radius);

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
    scene,
    renderer,
    audio,
    start: startLevel,
    raise: () => doLevelChange(1),
    lower: () => doLevelChange(-1),
    selectBasin: (i) => selectBasin(i),
    toggleGate: (i) => doGateToggle(i),
    undo: () => doUndo(),
  };
  window.__ready = true;

  lastTime = performance.now();
  rafId = requestAnimationFrame(frame);
}

boot().catch(fail);
