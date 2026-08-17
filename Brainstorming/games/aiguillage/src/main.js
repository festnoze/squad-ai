/**
 * AIGUILLAGE - orchestration and state machine.
 *
 * States: loading -> menu -> levels -> playing -> (paused | replay | results)
 * A fixed step drives the pure simulation (trains.js); the renderer
 * interpolates nothing extra on top since trains already move continuously
 * inside that fixed step (dt is clamped, not sub-stepped, which is plenty
 * smooth for the speeds involved here).
 */

import * as THREE from 'three';
import { createTextures } from './textures.js';
import { createSceneRig } from './render/scene.js';
import { createTrackRender } from './render/track.js';
import { createTrainRender } from './render/trains.js';
import { createCameraRig } from './camera.js';
import { createInput } from './input.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';
import { createNetwork } from './network.js';
import { createTrainSim } from './trains.js';
import { createScheduler } from './schedule.js';
import { createReplay } from './replay.js';
import { LEVELS, levelCount, getLevel } from './levels.js';

const STORAGE_PROGRESS = 'aiguillage.progress';
const STORAGE_SCORES = 'aiguillage.scores';
const STORAGE_AUDIO = 'aiguillage.audio';

function loadJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed == null ? fallback : parsed;
  } catch (err) {
    return fallback;
  }
}

function saveJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (err) {
    // Storage disabled or full: silently ignore, progress just won't persist.
  }
}

async function boot() {
  const canvas = document.getElementById('scene');
  const hud = createHUD();
  hud.showScreen('loading');
  hud.setLoading(0.05, 'Preparation du canevas...');
  await new Promise(requestAnimationFrame);

  const audio = createAudio();
  let progress = Math.max(0, Math.min(levelCount() - 1, loadJSON(STORAGE_PROGRESS, 0)));
  let scores = loadJSON(STORAGE_SCORES, {});
  const audioPrefs = loadJSON(STORAGE_AUDIO, { volume: 0.7, muted: false });

  hud.setLoading(0.2, 'Construction des textures...');
  await new Promise(requestAnimationFrame);
  const textures = createTextures(null);

  hud.setLoading(0.4, 'Mise en place de la scene...');
  await new Promise(requestAnimationFrame);
  const sceneRig = createSceneRig(canvas, textures);
  const textureRenderer = sceneRig.renderer;
  // Rebuild textures now that a real renderer exists, for anisotropic filtering.
  textures.dispose();
  const finalTextures = createTextures(textureRenderer);

  hud.setLoading(0.6, 'Camera et commandes...');
  await new Promise(requestAnimationFrame);
  const cameraRig = createCameraRig(window.innerWidth / Math.max(1, window.innerHeight));
  const input = createInput(canvas);
  const replay = createReplay();
  const trainRender = createTrainRender(finalTextures);
  sceneRig.scene.add(trainRender.group);

  hud.setLoading(0.85, 'Chargement des postes...');
  await new Promise(requestAnimationFrame);

  audio.setMasterVolume(audioPrefs.volume);
  if (audioPrefs.muted) audio.toggleMute();
  hud.setVolume(audioPrefs.volume);
  hud.setMuted(audioPrefs.muted);

  // ---------------------------------------------------------------------
  // Mutable session state
  // ---------------------------------------------------------------------
  let state = 'menu';
  let selectedLevelIndex = progress;
  let level = null;
  let network = null;
  let sim = null;
  let scheduler = null;
  let trackRender = null;
  let spawnTimes = new Map();
  let deliveredCount = 0;
  let lateCount = 0;
  let tactical = { remaining: 0, total: 0, active: false };
  let pendingPick = null;

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    sceneRig.resize(w, h);
    cameraRig.resize(w / Math.max(1, h));
  }
  window.addEventListener('resize', resize);
  resize();

  function bestFor(index) {
    return scores[index] || null;
  }

  function refreshLevelGrid() {
    hud.setLevelGrid(LEVELS, progress, LEVELS.map((_, i) => bestFor(i)));
  }

  function selectLevel(index) {
    selectedLevelIndex = index;
    hud.setLevelDetail(getLevel(index), bestFor(index));
    const grid = document.getElementById('level-grid');
    grid.querySelectorAll('.level-card').forEach((c) => {
      c.classList.toggle('selected', Number(c.dataset.index) === index);
    });
  }

  function networkBounds(net) {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const n of net.nodes.values()) {
      minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
      minZ = Math.min(minZ, n.z); maxZ = Math.max(maxZ, n.z);
    }
    return { minX, maxX, minZ, maxZ };
  }

  function startLevel(index) {
    level = getLevel(index);
    network = createNetwork(level.network);
    sim = createTrainSim(network, {});
    scheduler = createScheduler(level.spawns);
    spawnTimes = new Map();
    deliveredCount = 0;
    lateCount = 0;
    tactical = { remaining: level.pauseBudget, total: level.pauseBudget, active: false };
    // Defensive: never let a stale pick buffered against a previous level's
    // screen coordinates survive into this one (see input.onPick above).
    pendingPick = null;

    if (trackRender) {
      sceneRig.scene.remove(trackRender.group);
      trackRender.dispose();
    }
    trackRender = createTrackRender(network, finalTextures);
    sceneRig.scene.add(trackRender.group);
    trainRender.sync([], trackRender, sim.params.coupleGap);

    cameraRig.frame(networkBounds(network));

    hud.setLevelInfo(level.name);
    hud.setTrainCount(0, level.trainCount);
    hud.setClock(0);
    hud.setTeach(level.teach);
    hud.setPauseBudget(tactical.remaining, tactical.total);
    hud.setTacticalActive(false);
    hud.hideAllScreens();
    hud.show();
    input.setEnabled(true);
    state = 'playing';
    audio.setAlarm(false);
    hud.banner(level.name, level.teach || ('Poste ' + (index + 1) + ' / ' + levelCount()), 2600);
  }

  function saveScore(index, delivered, total, stars) {
    const prev = scores[index];
    if (!prev || stars > prev.stars || (stars === prev.stars && delivered > prev.delivered)) {
      scores[index] = { delivered, total, stars };
      saveJSON(STORAGE_SCORES, scores);
    }
    if (stars > 0 && index + 1 > progress) {
      progress = Math.min(levelCount() - 1, index + 1);
      saveJSON(STORAGE_PROGRESS, progress);
    }
  }

  function finalizeResults(success) {
    // Defensive: a results screen must never carry forward a pick buffered
    // during the level that just ended (see input.onPick above).
    pendingPick = null;
    const total = level.trainCount;
    let stars = 0;
    if (success) {
      if (lateCount === 0) stars = 3;
      else if (lateCount <= Math.ceil(total * 0.34)) stars = 2;
      else stars = 1;
    }
    saveScore(level.index, deliveredCount, total, stars);
    refreshLevelGrid();
    hud.setResults({
      success,
      subtitle: success ? 'Tous les trains geres.' : 'La circulation a du etre arretee.',
      delivered: deliveredCount,
      total,
      late: lateCount,
      stars,
      hasNext: success && level.index + 1 < levelCount(),
    });
    audio.finish(success);
    hud.hideAllScreens();
    hud.showScreen('results');
    state = 'results';
  }

  function triggerFailure(kind, event) {
    if (kind === 'crash') {
      audio.crash();
      audio.setAlarm(true);
      let worldPos = new THREE.Vector3();
      const spline = trackRender.getSpline(event.segmentId);
      if (spline) {
        const frame = spline.makeFrame();
        spline.at(event.sAbs, frame);
        worldPos = frame.pos.clone();
      }
      replay.start(worldPos);
      hud.toast('Collision !');
      state = 'replay';
    } else {
      audio.chime(false);
      hud.toast('Mauvais aiguillage : train perdu');
      finalizeResults(false);
    }
  }

  function restartLevel() {
    if (!level) return;
    startLevel(level.index);
  }

  // ---------------------------------------------------------------------
  // Picking
  // ---------------------------------------------------------------------
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();

  function findParkedTrainAtSegment(segmentId) {
    for (const t of sim.trains) {
      if (t.state === 'parked' && t.segmentId === segmentId) return t.id;
    }
    return null;
  }

  function performPick(ndcX, ndcY) {
    ndc.set(ndcX, ndcY);
    raycaster.setFromCamera(ndc, cameraRig.camera);

    const switchMeshes = trackRender.switchPickables.map((p) => p.mesh);
    const hitsSwitch = raycaster.intersectObjects(switchMeshes, false);
    if (hitsSwitch.length) {
      const idx = switchMeshes.indexOf(hitsSwitch[0].object);
      const rec = trackRender.switchPickables[idx];
      network.toggleSwitch(rec.switchId);
      audio.switchClick(network.switchState(rec.switchId));
      return;
    }

    const sidingMeshes = trackRender.sidingPickables.map((p) => p.mesh);
    const hitsSiding = raycaster.intersectObjects(sidingMeshes, false);
    if (hitsSiding.length) {
      const idx = sidingMeshes.indexOf(hitsSiding[0].object);
      const rec = trackRender.sidingPickables[idx];
      let segId = null;
      for (const s of network.segments.values()) {
        if (s.a === rec.nodeId || s.b === rec.nodeId) { segId = s.id; break; }
      }
      const trainId = segId ? findParkedTrainAtSegment(segId) : null;
      if (trainId && sim.reverseTrain(trainId)) audio.switchClick(1);
      return;
    }
  }

  input.onOrbit((dx, dy) => cameraRig.orbit(dx, dy));
  input.onZoom((delta) => cameraRig.zoom(delta));
  input.onPick((x, y) => {
    if (state === 'playing' || state === 'replay') {
      // 'replay' is the only non-playing state whose full-screen overlay does
      // not block pointer events, so a click can genuinely land on the canvas
      // here. Apply it immediately (network/trackRender/sim are still the
      // live level's) instead of buffering it: buffering it would only let it
      // resurface, replayed against stale coordinates, at some unrelated
      // later pause/resume in a future level - a click must always do its
      // thing now, never a wrong thing later.
      performPick(x, y);
      return;
    }
    // Every other non-playing state shows a full-screen '.screen' overlay
    // that blocks pointer events from reaching the canvas, so this branch is
    // not expected to run; kept only as a defensive single-slot buffer.
    pendingPick = { x, y };
  });
  input.onCommand((cmd) => {
    audio.resume();
    if (cmd === 'mute') {
      const muted = audio.toggleMute();
      hud.setMuted(muted);
      audioPrefs.muted = muted;
      saveJSON(STORAGE_AUDIO, audioPrefs);
      return;
    }
    if (cmd === 'pause') {
      if (state === 'playing') {
        state = 'paused';
        hud.showScreen('pause');
      } else if (state === 'paused') {
        hud.hideAllScreens();
        state = 'playing';
        if (pendingPick) { performPick(pendingPick.x, pendingPick.y); pendingPick = null; }
      }
      return;
    }
    if (cmd === 'restart') {
      if (state === 'playing' || state === 'paused' || state === 'results') restartLevel();
      return;
    }
    if (cmd === 'pause-tactical') {
      if (state !== 'playing') return;
      if (!tactical.active && tactical.remaining <= 0) return;
      tactical.active = !tactical.active;
      hud.setTacticalActive(tactical.active);
    }
  });

  // ---------------------------------------------------------------------
  // Menu wiring
  // ---------------------------------------------------------------------
  document.getElementById('btn-play').addEventListener('click', () => {
    audio.resume();
    refreshLevelGrid();
    selectLevel(progress);
    hud.showScreen('levels');
    state = 'levels';
  });
  document.getElementById('btn-controls').addEventListener('click', () => hud.showScreen('controls'));
  document.getElementById('btn-controls-back').addEventListener('click', () => hud.showScreen('menu'));
  document.getElementById('btn-level-back').addEventListener('click', () => {
    hud.showScreen('menu');
    state = 'menu';
  });
  document.getElementById('level-grid').addEventListener('click', (e) => {
    const card = e.target.closest('.level-card');
    if (!card || card.disabled) return;
    selectLevel(Number(card.dataset.index));
  });
  document.getElementById('btn-start').addEventListener('click', () => {
    audio.resume();
    startLevel(selectedLevelIndex);
  });

  document.getElementById('btn-tactical').addEventListener('click', () => {
    if (state !== 'playing') return;
    if (!tactical.active && tactical.remaining <= 0) return;
    tactical.active = !tactical.active;
    hud.setTacticalActive(tactical.active);
  });
  document.getElementById('btn-mute-hud').addEventListener('click', () => {
    const muted = audio.toggleMute();
    hud.setMuted(muted);
    audioPrefs.muted = muted;
    saveJSON(STORAGE_AUDIO, audioPrefs);
  });
  document.getElementById('btn-escape-hud').addEventListener('click', () => {
    if (state === 'playing') { state = 'paused'; hud.showScreen('pause'); }
  });

  document.getElementById('btn-resume').addEventListener('click', () => {
    hud.hideAllScreens();
    state = 'playing';
    if (pendingPick) { performPick(pendingPick.x, pendingPick.y); pendingPick = null; }
  });
  document.getElementById('btn-restart-pause').addEventListener('click', () => restartLevel());
  document.getElementById('btn-menu-pause').addEventListener('click', () => {
    hud.hideAllScreens();
    hud.hide();
    hud.showScreen('menu');
    state = 'menu';
  });
  document.getElementById('volume').addEventListener('input', (e) => {
    const v = Number(e.target.value) / 100;
    audio.setMasterVolume(v);
    document.getElementById('volume-value').textContent = e.target.value;
    audioPrefs.volume = v;
    saveJSON(STORAGE_AUDIO, audioPrefs);
  });

  document.getElementById('btn-results-next').addEventListener('click', () => {
    if (level.index + 1 < levelCount()) startLevel(level.index + 1);
  });
  document.getElementById('btn-results-retry').addEventListener('click', () => restartLevel());
  document.getElementById('btn-results-menu').addEventListener('click', () => {
    hud.hide();
    hud.showScreen('menu');
    state = 'menu';
  });

  // ---------------------------------------------------------------------
  // Main loop
  // ---------------------------------------------------------------------
  let lastTime = performance.now();

  function frame(nowMs) {
    requestAnimationFrame(frame);
    if (document.hidden) {
      lastTime = nowMs;
      return;
    }
    let dt = (nowMs - lastTime) / 1000;
    lastTime = nowMs;
    if (dt > 1 / 15) dt = 1 / 15;
    if (dt < 0) dt = 0;

    input.pollKeyboardOrbit(dt, (yawRate, pitchRate, ddt) => cameraRig.orbitRate(yawRate, pitchRate, ddt));

    if (state === 'playing') {
      for (const due of scheduler.pending(sim.time)) {
        const id = sim.spawnTrain(due);
        if (id) {
          spawnTimes.set(id, sim.time);
          audio.whistle();
        }
      }

      if (tactical.active) {
        tactical.remaining = Math.max(0, tactical.remaining - dt);
        hud.setPauseBudget(tactical.remaining, tactical.total);
        if (tactical.remaining <= 0) {
          tactical.active = false;
          hud.setTacticalActive(false);
        }
      }
      sim.step(dt, tactical.active);

      for (const d of sim.events.delivered) {
        deliveredCount++;
        const spawnT = spawnTimes.get(d.id);
        const late = spawnT != null && sim.time - spawnT > level.graceSeconds;
        if (late) lateCount++;
        audio.chime(true);
        hud.setTrainCount(deliveredCount, level.trainCount);
      }
      let failure = null;
      if (sim.events.crashed) failure = { kind: 'crash', payload: sim.events.crashed };
      else if (sim.events.wrongExit.length) failure = { kind: 'wrongexit', payload: sim.events.wrongExit[0] };
      sim.clearEvents();
      if (failure) triggerFailure(failure.kind, failure.payload);

      trackRender.update(dt, sim.time);
      trainRender.sync(sim.trains, trackRender, sim.params.coupleGap);

      let anyCrossingClosed = false;
      for (const seg of network.segments.values()) {
        if (seg.crossing && network.isCrossingClosed(seg.id, sim.time)) { anyCrossingClosed = true; break; }
      }
      audio.setBell(anyCrossingClosed);

      hud.setClock(sim.time);

      if (state === 'playing' && scheduler.done && sim.livingCount() === 0) {
        finalizeResults(true);
      }
    } else if (state === 'replay') {
      const stillPlaying = replay.update(dt, cameraRig);
      sim.step(dt * 0.2, false);
      sim.clearEvents();
      trackRender.update(dt * 0.2, sim.time);
      trainRender.sync(sim.trains, trackRender, sim.params.coupleGap);
      if (!stillPlaying) {
        audio.setAlarm(false);
        finalizeResults(false);
      }
    }

    cameraRig.update(dt);
    audio.update(dt);
    sceneRig.render(cameraRig.camera);
  }

  hud.setLoading(1, 'Pret.');
  await new Promise((resolve) => setTimeout(resolve, 120));
  hud.showScreen('menu');
  window.game = {
    sceneRig, cameraRig, audio, hud, getLevel, levelCount,
    get network() { return network; },
    get sim() { return sim; },
    get state() { return state; },
    get trackRender() { return trackRender; },
  };
  window.__ready = true;
  requestAnimationFrame(frame);
}

boot().catch((err) => {
  if (window.__fail) window.__fail(err && err.message ? err.message : String(err), err && err.stack);
  else throw err;
});
