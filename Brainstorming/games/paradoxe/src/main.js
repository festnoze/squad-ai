/**
 * PARADOXE - boot, state machine, main loop.
 *
 * The loop is split in two clocks on purpose:
 *   - the simulation advances in fixed 1/60 s steps from an accumulator,
 *   - the renderer interpolates between the last two steps.
 * Everything the player does is pushed into a tape at the same fixed rate, so a
 * rewind can hand that tape to a clone and get the exact same run back.
 */

import * as THREE from 'three';
import { SIM, PALETTE, STORAGE } from './config.js';
import { LEVELS } from './levels.js';
import { createSim } from './sim.js';
import { createRecording, pushTick, markPos, pushEvent, sealRecording, isMarkingEvent } from './recorder.js';
import { createParadoxWatch } from './paradox.js';
import { createInput } from './input.js';
import { createCameraRig } from './camera.js';
import { createTextures } from './textures.js';
import { createArena } from './render/scene.js';
import { createActors } from './render/clones.js';
import { createHUD } from './hud.js';
import { createTimeline } from './timeline.js';
import { createAudio } from './audio.js';

const BODY_COUNT = SIM.maxActors + SIM.maxCrates;
const DT = SIM.dt;

const prevPos = new Float32Array(BODY_COUNT * 3);
const curPos = new Float32Array(BODY_COUNT * 3);
const rpos = new Float32Array(BODY_COUNT * 3);
const mouseOut = { dx: 0, dy: 0, wheel: 0 };
const traceOut = { x: 0, y: 0, z: 0 };

function fail(message, where) {
  const s = document.getElementById('screen-error');
  const t = document.getElementById('error-text');
  if (!s || !t) return;
  t.textContent = String(message || 'Erreur inconnue') + (where ? '\n' + where : '');
  document.querySelectorAll('.screen').forEach((el) => el.classList.add('hidden'));
  s.classList.remove('hidden');
}

function loadJson(key, fallbackValue) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallbackValue;
    const parsed = JSON.parse(raw);
    return parsed === null || parsed === undefined ? fallbackValue : parsed;
  } catch (e) {
    void e;
    return fallbackValue;
  }
}

function saveJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    void e;
  }
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

async function boot() {
  const canvas = document.getElementById('scene');
  const hud = createHUD();
  hud.showScreen('screen-loading');

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  hud.setLoading(0.15, 'textures');
  await nextFrame();
  const textures = createTextures(renderer);

  hud.setLoading(0.5, 'systemes');
  await nextFrame();

  const cameraRig = createCameraRig(window.innerWidth, window.innerHeight);
  const input = createInput(canvas);
  input.setEnabled(false);
  const audio = createAudio();
  const timeline = createTimeline(hud.els.timeline);
  const watch = createParadoxWatch();

  // ---------------------------------------------------------------- state
  const state = {
    phase: 'menu',
    levelIndex: 0,
    level: null,
    sim: null,
    arena: null,
    actors: null,
    recordings: [],
    liveRec: null,
    accumulator: 0,
    alpha: 0,
    elapsed: 0,
    rewindT: 0,
    rewindFrom: 0,
    commitOnRewind: true,
    lastTickSound: 0,
    prevDoor: null,
    prevPlate: null,
    prevButton: null,
  };

  const progress = { unlocked: 0 };
  const stored = loadJson(STORAGE.progress, null);
  if (stored && typeof stored.unlocked === 'number' && stored.version === SIM.version) {
    progress.unlocked = Math.max(0, Math.min(LEVELS.length - 1, stored.unlocked));
  }
  let best = loadJson(STORAGE.best, null);
  if (!best || best.version !== SIM.version || !Array.isArray(best.clones)) {
    best = { version: SIM.version, clones: new Array(LEVELS.length).fill(null) };
  }
  while (best.clones.length < LEVELS.length) best.clones.push(null);

  function saveProgress() {
    saveJson(STORAGE.progress, { version: SIM.version, unlocked: progress.unlocked });
    saveJson(STORAGE.best, best);
  }

  function solvedCount() {
    let n = 0;
    for (let i = 0; i < LEVELS.length; i++) if (best.clones[i] !== null && best.clones[i] !== undefined) n++;
    return n;
  }

  function refreshMenu() {
    const n = solvedCount();
    hud.setMenuProgress(
      n === 0
        ? 'Aucun niveau resolu - ' + LEVELS.length + ' arenes vous attendent'
        : n + ' / ' + LEVELS.length + ' niveaux resolus',
    );
    hud.els['btn-play'].textContent = progress.unlocked > 0 || n > 0 ? 'REPRENDRE' : 'COMMENCER';
  }

  // ---------------------------------------------------------------- level
  function disposeLevel() {
    if (state.actors) state.actors.dispose();
    if (state.arena) state.arena.dispose();
    state.actors = null;
    state.arena = null;
  }

  function copyPositions(sim, out) {
    for (let i = 0; i < BODY_COUNT; i++) {
      const b = sim.bodies[i];
      out[i * 3] = b.x;
      out[i * 3 + 1] = b.y;
      out[i * 3 + 2] = b.z;
    }
  }

  function loadLevel(index) {
    disposeLevel();
    state.levelIndex = index;
    state.level = LEVELS[index];
    state.sim = createSim(state.level);
    state.arena = createArena(state.level, textures, renderer);
    state.actors = createActors(state.arena.scene, textures);
    state.recordings = [];
    state.prevDoor = new Uint8Array(state.level.doors.length);
    state.prevPlate = new Uint8Array(state.level.plates.length);
    state.prevButton = new Uint8Array(state.level.buttons.length);
    hud.setLevel(index, LEVELS.length, state.level.name, state.level.hint);
    cameraRig.reset(state.level, state.level.spawn.x + 0.5, 0, state.level.spawn.z + 0.5);
    startRun(true);
    hud.setHudVisible(true);
    hud.showScreen(null);
    timeline.resize();
  }

  function startRun(fresh) {
    const sim = state.sim;
    sim.reset(state.recordings);
    watch.reset(state.recordings);
    state.liveRec = createRecording(state.level.ticks);
    state.accumulator = 0;
    state.alpha = 0;
    state.rewindT = 0;
    state.lastTickSound = 0;
    state.prevDoor.fill(0);
    state.prevPlate.fill(0);
    state.prevButton.fill(0);
    copyPositions(sim, prevPos);
    copyPositions(sim, curPos);
    rpos.set(curPos);
    state.phase = 'playing';
    input.setEnabled(true);
    hud.setClones(state.recordings.length, state.level.maxClones);
    if (!fresh) {
      const n = state.recordings.length;
      if (n > 0) hud.banner('PASSE ' + (n + 1), n + (n > 1 ? ' clones en scene' : ' clone en scene'), 1200);
    } else {
      hud.banner(state.level.name, 'Passe 1 - ' + state.level.seconds + ' secondes', 1800);
    }
  }

  function beginRewind(commit, reasonToast) {
    if (state.phase !== 'playing') return;
    state.phase = 'rewinding';
    state.rewindT = 0;
    state.rewindFrom = state.sim.tick;
    state.commitOnRewind = commit;
    input.setEnabled(false);
    audio.play('rewind');
    cameraRig.punch(0.35);
    if (reasonToast) hud.toast(reasonToast, 'warn');
  }

  function finishRewind() {
    hud.setRewind(0);
    if (!state.commitOnRewind) {
      startRun(false);
      return;
    }
    if (state.recordings.length >= state.level.maxClones) {
      state.phase = 'fail';
      input.setEnabled(false);
      hud.setHudVisible(true);
      hud.setFail(
        'Trop de clones',
        'Ce niveau autorise ' + state.level.maxClones + ' clones. Il faut mieux repartir le travail.',
        state.recordings.length > 0,
      );
      hud.showScreen('screen-fail');
      audio.play('fail');
      return;
    }
    state.recordings.push(sealRecording(state.liveRec));
    audio.play('clone');
    startRun(false);
  }

  function onParadox(failure) {
    state.phase = 'fail';
    input.setEnabled(false);
    audio.play('paradox');
    cameraRig.punch(0.8);
    hud.flash('bad');
    hud.setFail('Paradoxe temporel', failure.text + ' La ligne de temps ne tient plus.', state.recordings.length > 0);
    hud.showScreen('screen-fail');
  }

  function onWin() {
    state.phase = 'win';
    input.setEnabled(false);
    audio.play('win');
    const used = state.recordings.length;
    const medal = used <= state.level.medalClones;
    if (medal) audio.play('medal');
    const previous = best.clones[state.levelIndex];
    const isBest = previous === null || previous === undefined || used < previous;
    if (isBest) best.clones[state.levelIndex] = used;
    if (state.levelIndex + 1 > progress.unlocked) progress.unlocked = Math.min(LEVELS.length - 1, state.levelIndex + 1);
    saveProgress();
    hud.setWin(
      state.level.name,
      used,
      medal,
      isBest ? null : previous === 0 ? 'sans clone' : previous + (previous > 1 ? ' clones' : ' clone'),
    );
    hud.els['btn-next'].textContent = state.levelIndex + 1 < LEVELS.length ? 'NIVEAU SUIVANT' : 'FIN';
    hud.showScreen('screen-win');
  }

  function undoClone() {
    if (state.recordings.length === 0) return false;
    state.recordings.pop();
    audio.play('ui');
    hud.showScreen(null);
    hud.setHudVisible(true);
    startRun(false);
    hud.toast('Dernier clone annule', '');
    return true;
  }

  function restartLevel() {
    state.recordings = [];
    hud.showScreen(null);
    hud.setHudVisible(true);
    startRun(true);
  }

  function goMenu() {
    state.phase = 'menu';
    input.setEnabled(false);
    hud.setHudVisible(false);
    refreshMenu();
    hud.showScreen('screen-menu');
  }

  // ---------------------------------------------------------------- audio
  function routeEvents(sim) {
    const evs = sim.frameEvents;
    for (let i = 0; i < evs.length; i++) {
      const ev = evs[i];
      if (ev.actor === 0) {
        if (isMarkingEvent(ev.key)) pushEvent(state.liveRec, ev.tick, ev.key);
      } else if (ev.actor > 0) {
        watch.onEvent(ev.actor, ev.key, ev.tick);
      }
      const key = ev.key;
      if (key === 'jump' && ev.actor === 0) audio.play('jump');
      else if (key.startsWith('grab')) audio.play('grab');
      else if (key.startsWith('drop')) audio.play('drop');
      else if (key === 'refuse' && ev.actor === 0) {
        audio.play('refuse');
        hud.toast('Rien a prendre ou pas la place de poser', 'warn');
      } else if (key.startsWith('tp')) audio.play('teleport');
      else if (key === 'crack') audio.play('crack');
      else if (key === 'collapse') {
        audio.play('collapse');
        cameraRig.punch(0.25);
      } else if (key === 'fall' && ev.actor === 0) audio.play('fail');
    }
    for (let i = 0; i < state.prevDoor.length; i++) {
      const v = sim.doorOpen[i];
      if (v !== state.prevDoor[i]) {
        audio.play(v ? 'doorOpen' : 'doorClose');
        state.prevDoor[i] = v;
      }
    }
    for (let i = 0; i < state.prevPlate.length; i++) {
      const v = sim.plateOn[i];
      if (v !== state.prevPlate[i]) {
        if (v) audio.play('plate');
        state.prevPlate[i] = v;
      }
    }
    for (let i = 0; i < state.prevButton.length; i++) {
      const v = sim.buttonOn[i];
      if (v !== state.prevButton[i]) {
        audio.play(v ? 'buttonOn' : 'buttonOff');
        state.prevButton[i] = v;
      }
    }
  }

  // ---------------------------------------------------------------- loop
  function stepSimulation() {
    const sim = state.sim;
    const level = state.level;
    let steps = 0;
    while (state.accumulator >= DT && steps < SIM.maxStepsPerFrame && state.phase === 'playing') {
      state.accumulator -= DT;
      steps++;
      copyPositions(sim, prevPos);
      const bits = input.bits;
      const yawByte = cameraRig.yawByte();
      pushTick(state.liveRec, bits, yawByte);
      sim.step(bits, yawByte);
      const p = sim.actors[0];
      markPos(state.liveRec, p.x, p.y, p.z);
      routeEvents(sim);
      copyPositions(sim, curPos);

      const failure = watch.update(sim);
      if (failure) {
        onParadox(failure);
        return;
      }
      if (sim.status === 'win') {
        onWin();
        return;
      }
      if (sim.status === 'fell') {
        beginRewind(false, 'Chute: la passe est annulee');
        return;
      }
      if (sim.status === 'timeout') {
        beginRewind(true, 'Temps ecoule');
        return;
      }
      const remaining = (level.ticks - sim.tick) / 60;
      if (remaining <= 3 && Math.floor(remaining) !== state.lastTickSound) {
        state.lastTickSound = Math.floor(remaining);
        audio.play('tick');
      }
    }
    if (steps >= SIM.maxStepsPerFrame) state.accumulator = 0;
    state.alpha = state.accumulator / DT;
  }

  function buildRenderPositions() {
    if (state.phase === 'rewinding') {
      const t = Math.max(0, Math.round(state.rewindFrom * (1 - state.rewindT)));
      for (let i = 0; i < BODY_COUNT; i++) {
        state.sim.traceAt(t, i, traceOut);
        rpos[i * 3] = traceOut.x;
        rpos[i * 3 + 1] = traceOut.y;
        rpos[i * 3 + 2] = traceOut.z;
      }
      return;
    }
    const a = state.phase === 'playing' ? state.alpha : 1;
    for (let i = 0; i < BODY_COUNT * 3; i++) rpos[i] = prevPos[i] + (curPos[i] - prevPos[i]) * a;
  }

  let lastTime = performance.now();
  function frame(nowMs) {
    requestAnimationFrame(frame);
    // Asleep in a background tab: no simulation, no render, and above all no
    // accumulated time. A hidden tab throttles rAF to about 1 Hz, so without
    // this the first visible frame would try to catch up seconds of physics.
    if (document.hidden) {
      lastTime = nowMs;
      state.accumulator = 0;
      return;
    }
    let dt = (nowMs - lastTime) / 1000;
    lastTime = nowMs;
    if (!(dt > 0)) dt = 0;
    if (dt > 0.1) dt = 0.1;
    state.elapsed += dt;

    // The camera stays free in every phase: looking around a frozen arena while
    // paused or after a paradox is how you work out what went wrong.
    input.consumeMouse(mouseOut, dt);
    cameraRig.handleMouse(mouseOut.dx, mouseOut.dy, mouseOut.wheel);

    handleCommands();

    if (state.phase === 'playing') {
      state.accumulator += dt;
      stepSimulation();
    } else if (state.phase === 'rewinding') {
      state.rewindT += dt / SIM.rewindTime;
      hud.setRewind(Math.min(1, state.rewindT));
      if (state.rewindT >= 1) finishRewind();
    }

    if (state.arena) {
      buildRenderPositions();
      const px = rpos[0];
      const py = rpos[1];
      const pz = rpos[2];
      cameraRig.update(dt, state.sim, px, Number.isNaN(py) ? 0 : py, pz);
      state.arena.update(state.sim, rpos, dt, state.elapsed);
      state.actors.sync(state.sim, rpos, state.elapsed, watch.stress, state.phase !== 'rewinding');
      state.arena.sun.position.set(px + 9, 20, pz + 7);
      state.arena.sun.target.position.set(px, 0, pz);
      state.arena.sun.target.updateMatrixWorld();
      renderer.render(state.arena.scene, cameraRig.camera);
    }

    if (state.level) {
      const remaining = Math.max(0, (state.level.ticks - state.sim.tick) / 60);
      hud.setTimer(remaining, remaining / state.level.seconds);
      timeline.draw(state.level, state.recordings, state.sim.tick, state.phase === 'rewinding' ? state.rewindT : 0);
    }
    hud.update(dt);
  }

  // ---------------------------------------------------------------- input
  function handleCommands() {
    if (input.pressed('mute')) {
      const m = audio.toggleMute();
      hud.toast(m ? 'Son coupe' : 'Son actif', '');
    }
    const undo = input.pressed('undo');
    const restart = input.pressed('restart');
    const rewind = input.pressed('rewind');
    const pause = input.pressed('pause');

    if (state.phase === 'playing') {
      if (pause) {
        state.phase = 'paused';
        input.setEnabled(false);
        hud.showScreen('screen-pause');
        audio.play('ui');
        return;
      }
      if (rewind) beginRewind(true, null);
      else if (restart) restartLevel();
      else if (undo) {
        if (!undoClone()) hud.toast('Aucun clone a annuler', 'warn');
      }
      return;
    }
    if (state.phase === 'paused') {
      if (pause) resumeFromPause();
      else if (restart) restartLevel();
      return;
    }
    if (state.phase === 'fail') {
      if (restart) restartLevel();
      else if (undo) undoClone();
      return;
    }
    if (state.phase === 'win') {
      if (restart) restartLevel();
      return;
    }
  }

  function resumeFromPause() {
    state.phase = 'playing';
    input.setEnabled(true);
    hud.showScreen(null);
    state.accumulator = 0;
  }

  // ---------------------------------------------------------------- wiring
  hud.els['btn-play'].addEventListener('click', () => {
    audio.resume();
    audio.play('ui');
    audio.startAmbient();
    loadLevel(progress.unlocked);
  });
  hud.els['btn-levels'].addEventListener('click', () => {
    audio.resume();
    audio.play('ui');
    hud.buildLevelGrid(LEVELS, progress.unlocked, best.clones, (i) => {
      audio.startAmbient();
      loadLevel(i);
    });
    hud.showScreen('screen-levels');
  });
  hud.els['btn-levels-back'].addEventListener('click', () => {
    audio.play('ui');
    goMenu();
  });
  hud.els['btn-resume'].addEventListener('click', () => {
    audio.play('ui');
    resumeFromPause();
  });
  hud.els['btn-restart-level'].addEventListener('click', () => {
    audio.play('ui');
    restartLevel();
  });
  hud.els['btn-pause-menu'].addEventListener('click', () => {
    audio.play('ui');
    goMenu();
  });
  hud.els['btn-next'].addEventListener('click', () => {
    audio.play('ui');
    if (state.levelIndex + 1 < LEVELS.length) {
      loadLevel(state.levelIndex + 1);
    } else {
      state.phase = 'end';
      hud.setHudVisible(false);
      let medals = 0;
      for (let i = 0; i < LEVELS.length; i++) {
        const b = best.clones[i];
        if (b !== null && b !== undefined && b <= LEVELS[i].medalClones) medals++;
      }
      hud.setEnd(medals + ' medaille' + (medals > 1 ? 's' : '') + ' sur ' + LEVELS.length + ' arenes.');
      hud.showScreen('screen-end');
    }
  });
  hud.els['btn-replay'].addEventListener('click', () => {
    audio.play('ui');
    restartLevel();
  });
  hud.els['btn-fail-retry'].addEventListener('click', () => {
    audio.play('ui');
    restartLevel();
  });
  hud.els['btn-fail-undo'].addEventListener('click', () => {
    audio.play('ui');
    undoClone();
  });
  hud.els['btn-end-menu'].addEventListener('click', () => {
    audio.play('ui');
    goMenu();
  });

  function onResize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    cameraRig.setSize(w, h);
    timeline.resize();
  }
  window.addEventListener('resize', onResize);

  // Some browsers suspend rAF outright while hidden, so the guard inside
  // frame() never gets to run: reset the clock here as well.
  function onVisibility() {
    if (document.hidden) return;
    lastTime = performance.now();
    state.accumulator = 0;
    input.releaseAll();
  }
  document.addEventListener('visibilitychange', onVisibility);

  hud.setLoading(1, 'pret');
  await nextFrame();
  hud.setHudVisible(false);
  refreshMenu();
  hud.showScreen('screen-menu');

  window.game = {
    get sim() {
      return state.sim;
    },
    state,
    LEVELS,
    renderer,
    cameraRig,
    audio,
    hud,
    watch,
    palette: PALETTE,
  };
  window.__ready = true;

  requestAnimationFrame((t) => {
    lastTime = t;
    frame(t);
  });
}

boot().catch((err) => fail(err && err.message ? err.message : String(err), err && err.stack));
