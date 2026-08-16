/**
 * PONTS DE FORTUNE - orchestration.
 *
 * State machine: loading -> title -> build <-> test -> replay -> win | lose.
 * The solver runs at a fixed 1/120 s with an accumulator, never at the frame
 * rate: a bridge that stands on a 144 Hz screen must stand on a 30 Hz one.
 */

import * as THREE from 'three';
import { SIM, REPLAY, CAMERA, DECK_Y, GRID, KEYS, MATERIAL_ORDER } from './config.js';
import { LEVELS } from './levels.js';
import { createBridge } from './bridge.js';
import { createConvoy } from './convoy.js';
import { createState, captureState, createRecorder } from './replay.js';
import { createTextures } from './textures.js';
import { createStage } from './render/scene.js';
import { createTerrain } from './render/terrain.js';
import { createBridgeView } from './render/bridgeview.js';
import { createVehicleView } from './render/vehicles.js';
import { createEditor } from './editor.js';
import { createHUD } from './hud.js';
import { createAudio } from './audio.js';
import { loadProgress, saveProgress, recordFor, countDone } from './storage.js';

const RECORD_STEP = 1 / REPLAY.hz;

function fail(message, where) {
  if (window.__fail) window.__fail(message, where);
  else throw new Error(message);
}

async function boot() {
  const canvas = document.getElementById('scene');
  if (!canvas) throw new Error('canvas #scene introuvable');
  const hud = createHUD();

  const tick = (pct, line) => {
    hud.setLoading(pct, line);
    return new Promise((r) => window.setTimeout(r, 16));
  };

  await tick(0.08, 'TEXTURES...');
  const textures = createTextures();

  await tick(0.32, 'SCENE...');
  const stage = createStage(canvas, textures);

  await tick(0.55, 'STRUCTURE...');
  const view = createBridgeView(stage.scene, textures);
  const vehicleView = createVehicleView(stage.scene);

  await tick(0.78, 'ATELIER...');
  const audio = createAudio();
  const progress = loadProgress();

  // ---------------------------------------------------------------- state
  let mode = 'title'; // build | test | replay | title | levels | paused | win | lose
  let paused = false;
  let levelIndex = 0;
  let level = null;
  let bridge = null;
  let terrain = null;
  let plan = null;
  let state = null;
  let convoy = null;
  let recorder = null;
  let accumulator = 0;
  let recordTimer = 0;
  let testTime = 0;
  let replayFrame = 0;
  let replayEnd = 0;
  let follow = true;
  let lastFailReason = '';
  const breakBuf = [];

  const editor = createEditor({
    canvas, stage, view, audio, hud,
    getMode: () => mode,
    onChange: refreshBuild,
    onMaterial: () => hud.setPalette(level.allow, editor.material),
  });

  audio.setVolume(progress.volume);
  hud.dom.volume.value = String(Math.round(progress.volume * 100));
  hud.dom.volumeValue.textContent = String(Math.round(progress.volume * 100));

  // ---------------------------------------------------------------- level
  function unloadLevel() {
    if (terrain) { terrain.dispose(); terrain = null; }
    plan = null;
    state = null;
    convoy = null;
    recorder = null;
    view.setPlan(null);
    view.clearEffects();
    vehicleView.setConvoy([]);
  }

  function loadLevel(index) {
    unloadLevel();
    levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
    level = LEVELS[levelIndex];
    bridge = createBridge(level);
    const rec = progress.levels[level.key];
    if (rec && rec.bridge) bridge.load(rec.bridge);
    terrain = createTerrain(stage.scene, textures, level);
    view.setLevel(level);
    view.setBridge(bridge);
    view.showGrid(true);
    editor.setLevel(level, bridge);
    stage.frameLevel(level, true);
    hud.setLevel(level, levelIndex, LEVELS.length);
    hud.setPalette(level.allow, editor.material);
    setMode('build');
    refreshBuild();
    hud.show();
    hud.showScreen(null);
  }

  function refreshBuild() {
    hud.setBudget(bridge.spent, level.budget, bridge.elements.length);
    hud.setUndoEnabled(bridge.historyDepth > 0);
    view.drawModel();
  }

  function setMode(next) {
    mode = next;
    hud.setMode(next === 'build' ? 'build' : (next === 'replay' ? 'replay' : 'test'));
    editor.enabled = next === 'build' || next === 'test' || next === 'replay';
    view.showGrid(next === 'build');
    vehicleView.setVisible(next !== 'build');
  }

  // ---------------------------------------------------------------- test
  function startTest() {
    const gaps = bridge.deckGaps();
    if (gaps.length) {
      audio.deny();
      hud.toast('IL MANQUE ' + gaps.length + ' TRONCON' + (gaps.length > 1 ? 'S' : '') + ' DE ROUTE', 'bad');
      return;
    }
    plan = bridge.buildSim();
    state = createState(plan);
    convoy = createConvoy(level, plan, level.convoy);
    recorder = createRecorder(plan, convoy.vehicles.length);
    view.setPlan(plan);
    view.clearEffects();
    vehicleView.setConvoy(convoy.vehicles);
    accumulator = 0;
    recordTimer = 0;
    testTime = 0;
    follow = true;
    lastFailReason = '';
    setMode('test');
    stage.lookAtPoint(0, DECK_Y + 2, 0, stage.fitDistance((level.right - level.left + 8) * GRID, 46),
      CAMERA.testYaw, CAMERA.testPitch);
    audio.resume();
    audio.testStart();
    hud.setTest('EN ATTENTE', 0, 0);
  }

  function backToBuild() {
    plan = null;
    state = null;
    convoy = null;
    recorder = null;
    view.setPlan(null);
    view.clearEffects();
    audio.engine(false, 0);
    audio.creak(0);
    setMode('build');
    stage.frameLevel(level, false);
    refreshBuild();
  }

  function stepTest(dt) {
    accumulator += Math.min(0.2, dt);
    let guard = 0;
    while (accumulator >= SIM.dt && guard < 40) {
      convoy.applyLoads();
      plan.sim.step(SIM.dt);
      convoy.advance(SIM.dt);
      plan.sim.drainBreaks(breakBuf);
      for (let i = 0; i < breakBuf.length; i++) {
        const b = breakBuf[i];
        if (b.kind === 'brace' || b.kind === 'traverse') continue;
        view.burst(b.x, b.y, b.z, b.kind);
        recorder.markBreak(b.x, b.y, b.z, b.kind);
        if (i < 2) audio.crack(0.5 + Math.random() * 0.5);
      }
      testTime += SIM.dt;
      recordTimer += SIM.dt;
      if (recordTimer >= RECORD_STEP) {
        recordTimer -= RECORD_STEP;
        recorder.record(plan.sim, convoy.vehicles);
      }
      accumulator -= SIM.dt;
      guard += 1;
    }
    if (guard >= 40) accumulator = 0;

    captureState(plan.sim, state);
    view.drawState(state);
    vehicleView.sync(convoy.vehicles);

    const peak = plan.sim.peakRatio();
    const status = convoy.failed ? 'RUPTURE'
      : (convoy.allDone() ? 'PASSE' : (convoy.started ? 'EN ROUTE' : 'MISE EN CHARGE'));
    hud.setTest(status, convoy.maxLoad, peak);
    audio.creak(peak);
    let onBridge = 0;
    for (let i = 0; i < convoy.vehicles.length; i++) if (convoy.vehicles[i].onBridge) onBridge += 1;
    audio.engine(convoy.started && !convoy.allDone(), Math.min(1, onBridge / 2));

    if (follow) {
      const lead = convoy.leader();
      stage.lookAtPoint(lead.x, Math.max(DECK_Y - 12, lead.y) + 2, 0);
    }

    if (convoy.failed) { onFailure(convoy.failReason); return; }
    if (convoy.allDone()) onSuccess();
  }

  function onFailure(reason) {
    lastFailReason = reason || 'LE PONT A CEDE';
    audio.collapse();
    audio.engine(false, 0);
    audio.creak(0);
    if (recorder && recorder.breakPoint.frame >= 0 && recorder.total > 4) {
      const bp = recorder.breakPoint;
      replayFrame = Math.max(recorder.firstFrame(), bp.frame - REPLAY.lead * REPLAY.hz);
      replayEnd = Math.min(recorder.total - 1, bp.frame + REPLAY.tail * REPLAY.hz);
      setMode('replay');
      follow = false;
      stage.lookAtPoint(bp.x, bp.y + 2, 0, CAMERA.replayDist, 0.42, 0.22);
      hud.setReplayNote('RALENTI ' + REPLAY.speed.toFixed(1) + 'x  -  ' + describeBreak(bp.kind));
    } else {
      showLose();
    }
  }

  function describeBreak(kind) {
    if (kind === 'cable') return 'CABLE ROMPU';
    if (kind === 'road') return 'TABLIER ROMPU';
    if (kind === 'steel') return 'ACIER ROMPU';
    if (kind === 'wood') return 'POUTRE ROMPUE';
    return 'STRUCTURE ROMPUE';
  }

  function stepReplay(dt) {
    replayFrame += dt * REPLAY.hz * REPLAY.speed;
    const done = replayFrame >= replayEnd;
    recorder.read(replayFrame, state, convoy.vehicles);
    view.drawState(state);
    vehicleView.sync(convoy.vehicles);
    if (done) showLose();
  }

  function showLose() {
    setMode('build');
    view.setPlan(null);
    view.clearEffects();
    audio.lose();
    hud.setLose(lastFailReason, 'Le pont est conserve tel quel: corrigez ce qui a lache.');
    hud.showScreen('screen-lose');
    mode = 'lose';
    editor.enabled = false;
  }

  function onSuccess() {
    const credits = bridge.budgetLeft;
    const load = Math.round(convoy.maxLoad);
    const rec = recordFor(progress, level.key);
    const improved = !rec.done || credits > rec.credits;
    rec.done = true;
    if (improved) {
      rec.credits = credits;
      rec.bridge = bridge.snapshot();
    }
    rec.load = Math.max(rec.load, load);
    progress.unlocked = Math.max(progress.unlocked, Math.min(LEVELS.length - 1, levelIndex + 1));
    saveProgress(progress);
    audio.engine(false, 0);
    audio.creak(0);
    audio.win();
    hud.setWin(level, [
      ['CREDITS RESTANTS', String(credits) + ' / ' + level.budget],
      ['CHARGE MAXIMALE', (load / 1000).toFixed(1) + ' t'],
      ['PIECES POSEES', String(bridge.elements.length)],
      ['MEILLEUR SCORE', String(rec.credits) + ' cr'],
    ], 'CONVOI PASSE', level.name);
    hud.showScreen('screen-win');
    mode = 'win';
    editor.enabled = false;
    view.setPlan(null);
    view.clearEffects();
  }

  // ---------------------------------------------------------------- screens
  function showTitle() {
    unloadLevel();
    level = null;
    bridge = null;
    hud.hide();
    hud.setProgressLine(countDone(progress), LEVELS.length);
    hud.showScreen('screen-title');
    mode = 'title';
    editor.enabled = false;
    stage.rig.goal.set(0, 0, 0);
    stage.rig.distGoal = 120;
  }

  function showLevels() {
    hud.setLevelGrid(LEVELS, progress, (i) => { audio.click(); loadLevel(i); });
    hud.showScreen('screen-levels');
    mode = 'levels';
    editor.enabled = false;
  }

  function togglePause() {
    if (mode !== 'build' && mode !== 'test' && mode !== 'replay') return;
    paused = !paused;
    if (paused) {
      hud.showScreen('screen-pause');
      editor.enabled = false;
      audio.engine(false, 0);
      audio.creak(0);
    } else {
      hud.showScreen(null);
      editor.enabled = true;
    }
  }

  // ---------------------------------------------------------------- input
  function onKey(e) {
    if (e.repeat) return;
    const code = e.code;
    if (KEYS.pause.indexOf(code) >= 0) {
      e.preventDefault();
      if (mode === 'levels') { showTitle(); return; }
      if (mode === 'win' || mode === 'lose') { hud.showScreen(null); resumeAfterScreen(); return; }
      togglePause();
      return;
    }
    if (paused || mode === 'title' || mode === 'levels') return;

    if (e.ctrlKey && KEYS.undo.indexOf(code) >= 0) {
      e.preventDefault();
      if (mode === 'build' && bridge.undo()) { audio.undo(); refreshBuild(); }
      return;
    }
    if (KEYS.test.indexOf(code) >= 0) {
      e.preventDefault();
      if (mode === 'build') startTest();
      else if (mode === 'test' || mode === 'replay') backToBuild();
      else if (mode === 'win' || mode === 'lose') { hud.showScreen(null); resumeAfterScreen(); }
      return;
    }
    if (KEYS.reset.indexOf(code) >= 0 && mode === 'build') {
      if (bridge.clear()) { audio.remove(); refreshBuild(); hud.toast('CHANTIER REMIS A ZERO'); }
      return;
    }
    if (KEYS.sideView.indexOf(code) >= 0) { stage.frameLevel(level, false); return; }
    if (KEYS.follow.indexOf(code) >= 0) {
      follow = !follow;
      hud.toast(follow ? 'CAMERA: SUIVRE LE CONVOI' : 'CAMERA: LIBRE');
      return;
    }
    if (KEYS.mute.indexOf(code) >= 0) {
      const m = audio.toggleMute();
      progress.muted = m;
      saveProgress(progress);
      hud.toast(m ? 'SON COUPE' : 'SON ACTIF');
      return;
    }
    const slot = KEYS.material.indexOf(code);
    if (slot >= 0 && mode === 'build') {
      if (editor.setMaterial(MATERIAL_ORDER[slot])) hud.setPalette(level.allow, editor.material);
    }
  }

  function resumeAfterScreen() {
    if (!level) { showTitle(); return; }
    setMode('build');
    editor.enabled = true;
    refreshBuild();
    stage.frameLevel(level, false);
  }

  window.addEventListener('keydown', onKey);
  window.addEventListener('resize', () => stage.resize());
  window.addEventListener('blur', () => {
    if (mode === 'test') audio.engine(false, 0);
  });

  // ---------------------------------------------------------------- buttons
  const b = hud.buttons;
  b.play.addEventListener('click', () => {
    audio.resume();
    audio.click();
    loadLevel(Math.min(progress.unlocked, LEVELS.length - 1));
  });
  b.levels.addEventListener('click', () => { audio.resume(); audio.click(); showLevels(); });
  b.levelsBack.addEventListener('click', () => { audio.click(); showTitle(); });
  b.test.addEventListener('click', () => { audio.resume(); startTest(); });
  b.abort.addEventListener('click', () => { audio.click(); backToBuild(); });
  b.undo.addEventListener('click', () => {
    if (mode === 'build' && bridge.undo()) { audio.undo(); refreshBuild(); }
  });
  b.clear.addEventListener('click', () => {
    if (mode === 'build' && bridge.clear()) { audio.remove(); refreshBuild(); }
  });
  b.view.addEventListener('click', () => { audio.click(); stage.frameLevel(level, false); });
  b.resume.addEventListener('click', () => { audio.click(); togglePause(); });
  b.restart.addEventListener('click', () => {
    audio.click();
    paused = false;
    hud.showScreen(null);
    bridge.clear();
    refreshBuild();
    setMode('build');
    editor.enabled = true;
  });
  b.quit.addEventListener('click', () => { audio.click(); paused = false; showLevels(); });
  b.next.addEventListener('click', () => {
    audio.click();
    if (levelIndex + 1 < LEVELS.length) loadLevel(levelIndex + 1);
    else showLevels();
  });
  b.replayLevel.addEventListener('click', () => { audio.click(); hud.showScreen(null); resumeAfterScreen(); });
  b.winLevels.addEventListener('click', () => { audio.click(); showLevels(); });
  b.retry.addEventListener('click', () => { audio.click(); hud.showScreen(null); resumeAfterScreen(); });
  b.loseLevels.addEventListener('click', () => { audio.click(); showLevels(); });

  hud.onMaterial((key) => {
    if (mode !== 'build') return;
    if (editor.setMaterial(key)) hud.setPalette(level.allow, editor.material);
  });

  hud.dom.volume.addEventListener('input', () => {
    const v = Number(hud.dom.volume.value) / 100;
    hud.dom.volumeValue.textContent = String(Math.round(v * 100));
    audio.setVolume(v);
    progress.volume = v;
    saveProgress(progress);
  });

  // ---------------------------------------------------------------- loop
  const clock = new THREE.Clock();
  function frame() {
    window.requestAnimationFrame(frame);
    // A hidden tab gets no frames at all in most browsers, but a throttled one
    // still gets a few: draining the clock and returning keeps the delta that
    // comes back with the tab from being a whole minute of simulation.
    if (document.hidden) { clock.getDelta(); return; }
    const dt = Math.min(0.05, clock.getDelta());

    if (!paused) {
      if (mode === 'test' && plan) stepTest(dt);
      else if (mode === 'replay' && recorder) stepReplay(dt);
      else if (bridge && mode !== 'test' && mode !== 'replay') view.drawModel();
    }
    if (terrain) terrain.update(dt);
    view.update(dt, mode === 'replay' ? REPLAY.speed : 1);
    stage.update(dt);
    stage.render();
  }

  await tick(1, 'PRET');
  hud.showScreen('screen-title');
  hud.setProgressLine(countDone(progress), LEVELS.length);
  hud.setMode('build');
  if (progress.muted) audio.toggleMute();
  frame();

  window.game = {
    get level() { return level; },
    get bridge() { return bridge; },
    get plan() { return plan; },
    get convoy() { return convoy; },
    get mode() { return mode; },
    LEVELS, stage, view, hud, audio, progress,
    loadLevel, startTest, backToBuild,
    /** Advance the running test or replay without waiting for frames. */
    step(seconds) {
      let t = 0;
      while (t < seconds && (mode === 'test' || mode === 'replay')) {
        if (mode === 'test') stepTest(1 / 60);
        else stepReplay(1 / 60);
        t += 1 / 60;
      }
      return mode;
    },
  };
  window.__ready = true;
}

boot().catch((e) => fail(e && e.message ? e.message : String(e), e && e.stack));
