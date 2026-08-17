import * as THREE from 'three';
import { createScene } from './render/scene.js';
import { createTextures } from './textures.js';
import { Input } from './input.js';
import { createLook, updateLook } from './camera.js';
import {
  createPlayer, updatePlayer, respawnPlayer, eyeHeight,
  toggleFlashlight, addBattery, setCheckpoint,
} from './player.js';
import { createEntity, updateEntity, breakTrail } from './entity.js';
import { buildMazeScene } from './render/maze.js';
import { createEntityMesh, updateEntityMesh } from './render/entity.js';
import { createFlashlight } from './render/flashlight.js';
import { createAudio } from './audio.js';
import { createHUD } from './hud.js';
import { LEVEL_COUNT, THEMES, getLevelDef, getLevelMaze } from './levels.js';
import { bfsDistances, worldToTile, tileToWorldCenter } from './maze.js';

const FIXED_DT = 1 / 60;
const PROGRESS_KEY = 'backrooms.progress';
const SETTINGS_KEY = 'backrooms.settings';

// -------------------------------------------------------------- persistence
function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? { ...fallback, ...parsed } : fallback;
  } catch (e) {
    return fallback;
  }
}
function saveJSON(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* storage unavailable: play on without saving */ }
}

let progress = loadJSON(PROGRESS_KEY, { levelIndex: 0, best: {} });
let settings = loadJSON(SETTINGS_KEY, { sensitivity: 0.0026, invertY: false, volume: 0.75, muted: false });

function saveProgress() { saveJSON(PROGRESS_KEY, progress); }
function saveSettings() { saveJSON(SETTINGS_KEY, settings); }

// -------------------------------------------------------------------- boot
const canvas = document.getElementById('scene');
const { renderer, scene, camera, setSize } = createScene(canvas);
scene.add(camera); // needed so the flashlight (a child of the camera) is traversed for lighting

const hud = createHUD();
hud.setLoadingLine('Construction des textures...');

const textures = createTextures(renderer);
hud.setLoadingLine('Preparation des controles...');

const input = new Input(canvas);
input.sensitivity = settings.sensitivity;
input.invertY = settings.invertY;

const look = createLook();
const audio = createAudio();
audio.setMasterVolume(settings.muted ? 0 : settings.volume);
const flashlight = createFlashlight(camera);

const ambient = new THREE.HemisphereLight(0x8892a0, 0x1a1712, 1);
scene.add(ambient);

window.addEventListener('resize', () => setSize(window.innerWidth, window.innerHeight));

// --------------------------------------------------------------- game state
let state = 'menu'; // menu | intro | playing | paused | complete | finale
let currentLevelIndex = 0;
let levelDef = null;
let maze = null;
let theme = null;
let mazeScene = null;
let player = null;
let entities = [];
let entityMeshes = [];
let levelTime = 0;
let restartedThisLevel = false;
let proximity01 = 0;
let detectedFlag = false;
let renderEyeHeight = 1.6;
let startDist = null; // BFS distance-from-start field, for the final level's colour gradient
let maxProgressDist = 1;

function idxOf(w, x, y) { return y * w + x; }

function clamp01(v) { return Math.max(0, Math.min(1, v)); }

function disposeLevel() {
  if (mazeScene) mazeScene.dispose();
  for (const m of entityMeshes) scene.remove(m);
  entityMeshes = [];
  entities = [];
  mazeScene = null;
}

const COMPASS = ['nord', 'nord-est', 'est', 'sud-est', 'sud', 'sud-ouest', 'ouest', 'nord-ouest'];
function compassHint(fromX, fromZ, toX, toZ) {
  const angle = Math.atan2(toX - fromX, -(toZ - fromZ)); // 0 = north (-Z), clockwise
  const i = Math.round(((angle < 0 ? angle + Math.PI * 2 : angle) / (Math.PI * 2)) * 8) % 8;
  return COMPASS[i];
}

function enterLevel(index) {
  disposeLevel();
  currentLevelIndex = index;
  levelDef = getLevelDef(index);
  maze = getLevelMaze(index);
  theme = THEMES[levelDef.theme];
  mazeScene = buildMazeScene(scene, maze, levelDef, theme, textures);

  player = createPlayer(mazeScene.startWorld.x, mazeScene.startWorld.z);
  player.hasFlashlight = !!levelDef.flashlight;
  if (levelDef.flashlight) addBattery(player, 55);
  setCheckpoint(player, mazeScene.startWorld.x, mazeScene.startWorld.z);

  look.yaw = 0;
  look.pitch = 0;
  renderEyeHeight = eyeHeight(player);

  if (levelDef.entity) {
    for (let i = 0; i < levelDef.entity.count; i++) {
      const e = createEntity(levelDef.entity, maze, i);
      const mesh = createEntityMesh();
      scene.add(mesh);
      entities.push(e);
      entityMeshes.push(mesh);
    }
  }

  scene.fog = new THREE.FogExp2(theme.fog, theme.fogDensity);
  scene.background = new THREE.Color(theme.fog);
  ambient.color.setHex(theme.ambient);
  ambient.groundColor.setHex(theme.ambient);
  ambient.intensity = theme.ambientIntensity;

  const exitIdx = idxOf(maze.width, maze.exitPos.x, maze.exitPos.y);
  startDist = bfsDistances(maze.tiles, maze.width, maze.height, maze.startPos.x, maze.startPos.y);
  maxProgressDist = Math.max(1, startDist[exitIdx]);

  levelTime = 0;
  restartedThisLevel = false;

  audio.startAmbience(levelDef.theme);
  hud.setEncounters(0, levelDef.encounterLimit);
  hud.setBattery(player.hasFlashlight ? player.batteryLife / 55 : 0, player.hasFlashlight);
  hud.setLevelInfo(levelDef.name, index, LEVEL_COUNT);
  hud.setTimer(0);
  hud.setVignette(0);

  state = 'intro';
  hud.showHUD(false);
  hud.showLevelIntro(levelDef, index, LEVEL_COUNT, progress.best[index]);
}

function beginPlaying() {
  audio.resume();
  input.requestLock();
  hud.hideAll();
  hud.showHUD(true);
  state = 'playing';
}

function computeMedal(time, encounters, def) {
  if (encounters === 0 && time <= def.goldSeconds) return 'or';
  if (!restartedThisLevel) return 'argent';
  return 'bronze';
}

function medalRank(m) { return m === 'or' ? 3 : m === 'argent' ? 2 : 1; }

function updateProgressRecord(index, time, encounters, medal) {
  const prev = progress.best[index];
  if (!prev || medalRank(medal) > medalRank(prev.medal) || (medalRank(medal) === medalRank(prev.medal) && time < prev.time)) {
    progress.best[index] = { time, encounters, medal };
  }
  progress.levelIndex = Math.max(progress.levelIndex, Math.min(index + 1, LEVEL_COUNT - 1));
  saveProgress();
}

function completeLevel() {
  state = 'complete';
  input.releaseLock();
  audio.exitChime();
  audio.stopAmbience();
  const medal = computeMedal(levelTime, player.encounters, levelDef);
  const isLast = currentLevelIndex === LEVEL_COUNT - 1;
  updateProgressRecord(currentLevelIndex, levelTime, player.encounters, medal);
  hud.showHUD(false);
  hud.showLevelComplete({ time: levelTime, encounters: player.encounters, medal, isLast });
}

function finishRun() {
  let totalTime = 0;
  let totalEncounters = 0;
  let cleared = 0;
  for (const key of Object.keys(progress.best)) {
    const r = progress.best[key];
    totalTime += r.time;
    totalEncounters += r.encounters;
    cleared++;
  }
  hud.showFinale({ levelsCleared: cleared, totalEncounters, totalTime });
  state = 'finale';
}

function restartLevel() {
  restartedThisLevel = true;
  respawnPlayer(player, mazeScene.startWorld.x, mazeScene.startWorld.z);
  player.encounters = 0;
  levelTime = 0;
  mazeScene.openDoors.clear();
  for (const d of mazeScene.doors) { d.targetAngle = 0; d.openAngle = 0; d.pivot.rotation.y = d.horizontalPassage ? Math.PI / 2 : 0; }
  for (const it of mazeScene.items) { if (it.taken) { it.taken = false; it.mesh.visible = true; } }
  if (levelDef.entity) {
    for (let i = 0; i < entities.length; i++) entities[i] = createEntity(levelDef.entity, maze, i);
  }
  if (levelDef.flashlight) { player.hasFlashlight = true; player.batteryLife = 55; }
  hud.setEncounters(0, levelDef.encounterLimit);
  hud.toast('Niveau reinitialise.');
}

function pickNotebookHint(item) {
  const dir = compassHint(item.x, item.y, maze.exitPos.x, maze.exitPos.y);
  return `Carnet trouve : une note a moitie effacee parle d'un courant d'air venant du ${dir}.`;
}

function tryInteract() {
  if (mazeScene.tryOpenDoor(player.x, player.z)) { audio.doorOpen(); return; }
  const item = mazeScene.tryPickup(player.x, player.z);
  if (item) {
    audio.pickup();
    if (item.type === 'battery') {
      addBattery(player, 40);
      hud.toast('Pile ramassee : +40 secondes de lampe.');
    } else {
      hud.toast(pickNotebookHint(item));
    }
    return;
  }
  if (player.hasFlashlight) {
    const ok = toggleFlashlight(player);
    if (ok) audio.flashlightClick();
    else hud.toast('Plus de piles : la lampe reste eteinte.');
    return;
  }
  hud.toast('Rien a faire ici.');
}

function handleContact(entity) {
  player.encounters++;
  hud.flashContact();
  audio.contact();
  breakTrail(entity);
  respawnPlayer(player, player.checkpointX, player.checkpointZ);
  hud.setEncounters(player.encounters, levelDef.encounterLimit);
  if (levelDef.encounterLimit > 0 && player.encounters >= levelDef.encounterLimit) {
    hud.toast('Trop de rencontres : une reprise complete (R) est conseillee.');
  }
}

function updateInteractHint() {
  let text = null;
  for (const d of mazeScene.doors) {
    const w = tileToWorldCenter(d.x, d.y);
    if ((w.x - player.x) ** 2 + (w.z - player.z) ** 2 < 1.6 * 1.6) {
      text = d.targetAngle > 0.1 ? 'E : fermer la porte' : 'E : ouvrir la porte';
      break;
    }
  }
  if (!text) {
    for (const it of mazeScene.items) {
      if (it.taken) continue;
      const w = tileToWorldCenter(it.x, it.y);
      if ((w.x - player.x) ** 2 + (w.z - player.z) ** 2 < 1.4 * 1.4) {
        text = it.type === 'battery' ? 'E : ramasser la pile' : 'E : ramasser le carnet';
        break;
      }
    }
  }
  if (!text && player.hasFlashlight) text = player.flashlightOn ? 'E : eteindre la lampe' : 'E : allumer la lampe';
  hud.setInteractHint(text);
}

// ------------------------------------------------------------- fixed step
function fixedUpdate(dt) {
  if (state !== 'playing') return;
  player.yaw = look.yaw;
  updatePlayer(player, dt, input, maze, mazeScene.openDoors, theme.surface, true);
  if (player.stepEvent) audio.footstep(theme.surface, player.sprinting);

  levelTime += dt;

  let minDist = Infinity;
  let anyDetected = false;
  // Snapshot the pre-step player position for contact checks: handleContact()
  // teleports the player to the checkpoint mid-loop, so without this snapshot
  // a later entity's distance would be measured against the already-respawned
  // position instead of where the player actually was this tick (could spawn
  // a spurious same-tick double contact on multi-entity levels).
  const contactX = player.x;
  const contactZ = player.z;
  for (const e of entities) {
    updateEntity(e, dt, {
      maze, openDoors: mazeScene.openDoors, playerX: player.x, playerZ: player.z, noise01: player.noise01,
    });
    const d = Math.hypot(e.x - player.x, e.z - player.z);
    if (d < minDist) minDist = d;
    if (e.detectedNow) anyDetected = true;
    if (Math.hypot(e.x - contactX, e.z - contactZ) < 0.85) handleContact(e);
  }
  proximity01 = entities.length ? clamp01(1 - minDist / 11) : 0;
  detectedFlag = anyDetected;

  const distToExit = Math.hypot(player.x - mazeScene.exitWorld.x, player.z - mazeScene.exitWorld.z);
  if (distToExit < 1.1) completeLevel();
}

// ------------------------------------------------------------------ render
let lastTime = performance.now();
let accumulator = 0;

function renderFrame(alpha, dt) {
  if (state === 'playing') {
    // One-shot actions are polled once per rendered frame (not per fixed step):
    // the accumulator below can run several fixed steps per frame, and a
    // buffered press is only removed once acted on (see Input.consume), so
    // checking edge-triggered keys inside the fixed step would double-fire them.
    if (input.pressedAny('KeyE', 'char:e')) { input.consume('KeyE', 'char:e'); tryInteract(); }
    if (input.pressedAny('KeyR', 'char:r')) { input.consume('KeyR', 'char:r'); restartLevel(); }

    updateLook(look, dt, input, settings);
    const targetEye = eyeHeight(player);
    renderEyeHeight += (targetEye - renderEyeHeight) * Math.min(1, 10 * dt);
    const rx = player.prevX + (player.x - player.prevX) * alpha;
    const rz = player.prevZ + (player.z - player.prevZ) * alpha;
    camera.position.set(rx, renderEyeHeight, rz);
    camera.rotation.set(look.pitch, look.yaw, 0, 'YXZ');

    const pt = worldToTile(player.x, player.z);
    const progress01 = clamp01((startDist[idxOf(maze.width, pt.x, pt.y)] ?? 0) / maxProgressDist);
    mazeScene.update(dt, progress01);
    for (let i = 0; i < entities.length; i++) updateEntityMesh(entityMeshes[i], entities[i], alpha, dt);
    flashlight.update(dt, player.flashlightOn, 5.4);

    hud.setStamina(player.stamina);
    hud.setBattery(player.hasFlashlight ? player.batteryLife / 55 : 0, player.hasFlashlight);
    hud.setTimer(levelTime);
    hud.setVignette(Math.max(proximity01 * 0.9, detectedFlag ? 0.45 : 0));
    updateInteractHint();
    audio.update(dt, proximity01, detectedFlag);
  }
  renderer.render(scene, camera);
}

function frame(now) {
  requestAnimationFrame(frame);
  if (document.hidden) { lastTime = now; return; }
  let dt = (now - lastTime) / 1000;
  lastTime = now;
  dt = Math.min(dt, 0.25);
  accumulator += dt;
  let steps = 0;
  while (accumulator >= FIXED_DT && steps < 8) {
    fixedUpdate(FIXED_DT);
    accumulator -= FIXED_DT;
    steps++;
  }
  const alpha = accumulator / FIXED_DT;
  renderFrame(alpha, dt);
  input.endFrame();
}

// ------------------------------------------------------------------- input
document.addEventListener('keydown', (e) => {
  if (e.code === 'Escape' && state === 'playing') {
    state = 'paused';
    input.releaseLock();
    audio.stopAmbience();
    hud.showHUD(false);
    hud.showPause(settings.sensitivity, settings.invertY, settings.volume);
  } else if (e.code === 'KeyM' || e.key?.toLowerCase() === 'm') {
    if (state === 'playing' || state === 'paused') {
      settings.muted = audio.toggleMute();
      saveSettings();
      syncMuteButton();
    }
  }
});

function syncMuteButton() {
  const btn = document.getElementById('btn-mute');
  btn.textContent = settings.muted ? '\u{1F507}' : '\u{1F50A}';
  btn.classList.toggle('muted', settings.muted);
}

document.getElementById('btn-mute').addEventListener('click', () => {
  settings.muted = audio.toggleMute();
  saveSettings();
  syncMuteButton();
});

document.getElementById('btn-start').addEventListener('click', () => {
  enterLevel(Math.min(progress.levelIndex, LEVEL_COUNT - 1));
});

document.getElementById('btn-reset-progress').addEventListener('click', () => {
  progress = { levelIndex: 0, best: {} };
  saveProgress();
  document.getElementById('menu-continue-hint').textContent = 'Progression effacee.';
});

document.getElementById('btn-intro-start').addEventListener('click', beginPlaying);

document.getElementById('btn-resume').addEventListener('click', () => {
  audio.startAmbience(levelDef.theme);
  input.requestLock();
  hud.showHUD(true);
  hud.hideAll();
  state = 'playing';
});

document.getElementById('btn-restart-pause').addEventListener('click', () => {
  restartLevel();
  audio.startAmbience(levelDef.theme);
  input.requestLock();
  hud.showHUD(true);
  hud.hideAll();
  state = 'playing';
});

document.getElementById('btn-quit-pause').addEventListener('click', () => {
  disposeLevel();
  audio.stopAmbience();
  input.releaseLock();
  hud.showHUD(false);
  hud.showScreen('menu');
  state = 'menu';
});

document.getElementById('btn-next-level').addEventListener('click', () => {
  enterLevel(Math.min(currentLevelIndex + 1, LEVEL_COUNT - 1));
});

document.getElementById('btn-finish-run').addEventListener('click', finishRun);

document.getElementById('btn-back-to-menu').addEventListener('click', () => {
  disposeLevel();
  hud.showScreen('menu');
  state = 'menu';
});

const sensSlider = document.getElementById('sens-slider');
sensSlider.addEventListener('input', () => {
  settings.sensitivity = Number(sensSlider.value) / 10000;
  input.sensitivity = settings.sensitivity;
  document.getElementById('sens-value').textContent = settings.sensitivity.toFixed(4);
  saveSettings();
});
document.getElementById('invert-y').addEventListener('change', (e) => {
  settings.invertY = e.target.checked;
  input.invertY = settings.invertY;
  saveSettings();
});
document.getElementById('volume-slider').addEventListener('input', (e) => {
  settings.volume = Number(e.target.value) / 100;
  if (!settings.muted) audio.setMasterVolume(settings.volume);
  saveSettings();
});

canvas.addEventListener('click', () => {
  if (state === 'playing' && !input.locked) input.requestLock();
});

// ---------------------------------------------------------------- boot end
hud.setLoadingLine('Pret.');
const hint = document.getElementById('menu-continue-hint');
if (progress.levelIndex > 0) {
  hint.textContent = `Reprise au Niveau ${progress.levelIndex + 1} / ${LEVEL_COUNT}.`;
}
hud.showScreen('menu');
syncMuteButton();

requestAnimationFrame(frame);
