/**
 * OVERCLOCK - boot, state machine and the loop that turns interpreter events
 * into drone movement.
 *
 * The interpreter runs at its own pace: one step is consumed only when the
 * previous one has finished animating, which is what makes x0.5 and F10 free.
 */

import * as THREE from 'three';
import { LEVELS } from './levels.js';
import { createWarehouse, DIRS } from './warehouse.js';
import { createProgram, OPS } from './program.js';
import { createVM, STATUS_LABEL } from './vm.js';
import { createTextures } from './textures.js';
import { createScene, STEP } from './render/scene.js';
import { createDrone } from './render/drone.js';
import { createCameraRig } from './camera.js';
import { createPanel } from './ui/panel.js';
import { createHUD, medalFor } from './hud.js';
import { createAudio } from './audio.js';
import { createStorage } from './storage.js';

const HOVER = 0.52;
const DUR = {
  move: 0.42,
  turn: 0.3,
  act: 0.34,
  paint: 0.28,
  hold: 0.34,
  bump: 0.26,
  tiny: 0.1,
};

const YAW_BY_DIR = [Math.PI / 2, 0, -Math.PI / 2, Math.PI];

function $(id) {
  return document.getElementById(id);
}

function smooth(t) {
  return t * t * (3 - 2 * t);
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
const canvas = $('scene');
const stage = $('stage');

const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
  powerPreference: 'high-performance',
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 300);

const textures = createTextures(renderer);
const world = createScene(renderer, textures);
const drone = createDrone(textures);
drone.group.scale.setScalar(1.3);
world.scene.add(drone.group);
world.scene.add(drone.halo);
world.scene.add(drone.trail);

const rig = createCameraRig(camera, canvas);
const hud = createHUD();
const audio = createAudio();
const storage = createStorage();

const panel = createPanel({
  paletteEl: $('palette'),
  procsEl: $('procs'),
  onChange: onProgramChanged,
  onSound: (k) => audio.play(k),
});

// ---------------------------------------------------------------------------
// mutable state
// ---------------------------------------------------------------------------
let mode = 'title'; // title | levels | play | pause | win | end
let levelIndex = 0;
let level = LEVELS[0];
let wh = null;
let program = null;
let vm = null;

const run = {
  active: false,
  stepping: false,
  pending: false,
  speed: 1,
  endStatus: null,
};

const pose = { x: 0, y: 0, z: 0, yaw: 0 };
// Scratch for the destination of a move, never nested with `pose`.
const target = { x: 0, y: 0, z: 0 };
const anim = {
  active: false,
  kind: '',
  t: 0,
  dur: 0,
  fx: 0,
  fy: 0,
  fz: 0,
  tx: 0,
  ty: 0,
  tz: 0,
  fyaw: 0,
  tyaw: 0,
  arc: 0,
  dip: 0,
  bx: 0,
  bz: 0,
};

// ---------------------------------------------------------------------------
// level lifecycle
// ---------------------------------------------------------------------------
function cellWorldY(top) {
  return top * STEP + HOVER;
}

function poseFromModel(out) {
  out.x = world.cellX(wh.drone.x);
  out.y = cellWorldY(wh.drone.level);
  out.z = world.cellZ(wh.drone.z);
  return out;
}

function loadLevel(index) {
  levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
  level = LEVELS[levelIndex];
  wh = createWarehouse(level);
  program = createProgram(level);

  const saved = storage.programFor(level.id);
  if (saved) program.load(saved);

  world.build(wh);
  let top = 0;
  for (const t of wh.tiles) if (t.h > top) top = t.h;
  // Aim slightly below the slab tops: the columns hang down, so aiming at the
  // playfield plane would push the whole zone under the middle of the screen.
  rig.frame(world.radius, (top * STEP) / 2 - 0.4);

  panel.setLevel(level, program);
  panel.setEditable(true);

  hud.setLevel(levelIndex, LEVELS.length, level);
  hud.clearToasts();
  resetRun(false);
  onProgramChanged(false);
}

function resetRun(sound) {
  wh.reset();
  world.sync();
  vm = createVM(wh, program);
  run.active = false;
  run.stepping = false;
  run.pending = false;
  run.endStatus = null;
  anim.active = false;
  poseFromModel(pose);
  pose.yaw = YAW_BY_DIR[wh.drone.dir];
  drone.setCarrying(false);
  drone.resetTrail();
  panel.clearHighlight();
  panel.setEditable(true);
  audio.setRunning(false);
  hud.setTargets(wh.lit, wh.targets);
  hud.setStack(0);
  hud.setSteps(0);
  hud.setStatus('EDITION', '');
  if (sound) audio.play('ui');
}

function onProgramChanged(save) {
  const used = program.count();
  hud.setBudget(used, level.optimal);
  if (save !== false) storage.saveProgram(level.id, program.serialize());
}

// ---------------------------------------------------------------------------
// running
// ---------------------------------------------------------------------------
function startRun(stepping) {
  audio.resume();
  if (program.isEmpty()) {
    hud.toast('PROGRAMME VIDE', 'bad');
    audio.refuse();
    return;
  }
  resetRun(false);
  run.active = true;
  run.stepping = !!stepping;
  run.pending = !!stepping;
  panel.setEditable(false);
  audio.setRunning(!stepping);
  hud.setStatus(stepping ? 'PAS A PAS' : 'EXECUTION', 'ok');
  audio.play('start');
}

function stopRun(message) {
  if (!run.active) return;
  run.active = false;
  run.stepping = false;
  run.pending = false;
  panel.setEditable(true);
  audio.setRunning(false);
  hud.setStatus(message || 'ARRETE', 'warn');
  if (message) hud.toast(message, 'bad');
}

function finishRun(status) {
  run.active = false;
  run.stepping = false;
  run.pending = false;
  panel.setEditable(true);
  audio.setRunning(false);

  if (status === 'win') {
    const used = program.count();
    const medal = medalFor(used, level.optimal);
    const better = storage.recordWin(level.id, levelIndex, used);
    hud.setStatus('RESOLU', 'ok');
    audio.win();
    hud.setWin({
      title: 'ZONE ' + String(levelIndex + 1).padStart(2, '0') + ' RESOLUE',
      medal,
      sub: better ? 'NOUVEAU MEILLEUR PROGRAMME' : 'PROGRAMME VALIDE',
      used,
      optimal: level.optimal,
      steps: vm.steps,
      best: storage.bestFor(level.id),
      hasNext: levelIndex + 1 < LEVELS.length,
    });
    mode = 'win';
    hud.showScreen('win');
    return;
  }

  const label = STATUS_LABEL[status] || 'ARRETE';
  hud.setStatus(label, status === 'halt' ? 'warn' : 'bad');
  hud.toast(label, 'bad');
  audio.fail();
}

function beginAnim(kind, dur, opts) {
  anim.kind = kind;
  anim.t = 0;
  anim.dur = Math.max(0.02, dur / run.speed);
  anim.fx = pose.x;
  anim.fy = pose.y;
  anim.fz = pose.z;
  anim.fyaw = pose.yaw;
  anim.tx = opts && opts.tx !== undefined ? opts.tx : pose.x;
  anim.ty = opts && opts.ty !== undefined ? opts.ty : pose.y;
  anim.tz = opts && opts.tz !== undefined ? opts.tz : pose.z;
  anim.tyaw = opts && opts.tyaw !== undefined ? opts.tyaw : pose.yaw;
  anim.arc = opts && opts.arc ? opts.arc : 0;
  anim.dip = opts && opts.dip ? opts.dip : 0;
  anim.bx = opts && opts.bx ? opts.bx : 0;
  anim.bz = opts && opts.bz ? opts.bz : 0;
  anim.active = true;
}

function doStep() {
  const beforeDir = wh.drone.dir;
  const ev = vm.step();

  hud.setSteps(vm.steps);
  hud.setStack(vm.depth);

  if (ev.proc >= 0) panel.highlight(ev.proc, ev.slot, ev.kind === 'skip' ? 'skip' : 'exec');

  if (ev.kind === 'end') {
    run.endStatus = ev.status;
    finishRun(ev.status);
    return;
  }

  if (ev.kind === 'empty') {
    beginAnim('idle', DUR.tiny, {});
    return;
  }

  if (ev.kind === 'skip') {
    beginAnim('idle', DUR.tiny, {});
    return;
  }

  if (ev.kind === 'call') {
    if (!ev.ok) {
      drone.refuse();
      audio.refuse();
      hud.toast(ev.reason, 'bad');
      beginAnim('idle', DUR.tiny, {});
      run.endStatus = 'overflow';
      finishRun('overflow');
      return;
    }
    audio.play('call');
    beginAnim('idle', DUR.tiny, {});
    return;
  }

  // primitive instruction
  if (!ev.ok) {
    const d = DIRS[wh.drone.dir];
    drone.refuse();
    audio.refuse();
    hud.toast(ev.reason, 'bad');
    beginAnim('bump', DUR.bump, { bx: d.x * 0.22, bz: d.z * 0.22 });
    checkEndAfterAnim(ev);
    return;
  }

  switch (ev.op) {
    case 'FWD': {
      poseFromModel(target);
      audio.play('move');
      beginAnim('move', DUR.move, { tx: target.x, ty: target.y, tz: target.z });
      break;
    }
    case 'JUMP': {
      poseFromModel(target);
      audio.play('jump');
      beginAnim('move', DUR.move * 1.15, {
        tx: target.x,
        ty: target.y,
        tz: target.z,
        arc: ev.detail && ev.detail.gap ? 0.5 : 0.3,
      });
      break;
    }
    case 'LEFT':
    case 'RIGHT': {
      const delta = (wh.drone.dir - beforeDir + 4) % 4 === 1 ? -Math.PI / 2 : Math.PI / 2;
      audio.play('turn');
      beginAnim('turn', DUR.turn, { tyaw: pose.yaw + delta });
      break;
    }
    case 'ACT': {
      world.sync();
      hud.setTargets(wh.lit, wh.targets);
      audio.play('act');
      beginAnim('pulse', DUR.act, { dip: 0.14 });
      break;
    }
    case 'PAINT_R':
    case 'PAINT_G':
    case 'PAINT_B': {
      world.sync();
      audio.play('paint');
      beginAnim('pulse', DUR.paint, { dip: 0.1 });
      break;
    }
    case 'GRAB': {
      world.sync();
      drone.setCarrying(true);
      audio.play('grab');
      beginAnim('pulse', DUR.hold, { dip: 0.16 });
      break;
    }
    case 'DROP': {
      world.sync();
      drone.setCarrying(false);
      audio.play('drop');
      beginAnim('pulse', DUR.hold, { dip: 0.16 });
      break;
    }
    default:
      beginAnim('idle', DUR.tiny, {});
      break;
  }

  checkEndAfterAnim(ev);
}

/** A winning instruction still gets its animation before the screen changes. */
function checkEndAfterAnim(ev) {
  if (ev.status === 'win' || vm.status === 'win') run.endStatus = 'win';
}

function updateAnim(dt) {
  if (!anim.active) return;
  anim.t += dt;
  const raw = Math.min(1, anim.t / anim.dur);
  const k = smooth(raw);

  pose.x = anim.fx + (anim.tx - anim.fx) * k;
  pose.z = anim.fz + (anim.tz - anim.fz) * k;
  pose.y = anim.fy + (anim.ty - anim.fy) * k;
  pose.yaw = anim.fyaw + (anim.tyaw - anim.fyaw) * k;

  if (anim.arc) pose.y += Math.sin(raw * Math.PI) * anim.arc;
  if (anim.dip) pose.y -= Math.sin(raw * Math.PI) * anim.dip;
  if (anim.bx || anim.bz) {
    const push = Math.sin(raw * Math.PI);
    pose.x += anim.bx * push;
    pose.z += anim.bz * push;
  }

  if (raw >= 1) {
    anim.active = false;
    pose.x = anim.tx;
    pose.y = anim.ty;
    pose.z = anim.tz;
    pose.yaw = anim.tyaw;
    if (run.endStatus && run.active) {
      const s = run.endStatus;
      run.endStatus = null;
      finishRun(s);
    }
  }
}

// ---------------------------------------------------------------------------
// loop
// ---------------------------------------------------------------------------
let last = performance.now();

function frame(now) {
  requestAnimationFrame(frame);
  // A hidden tab must not accumulate time: the browser throttles rAF but still
  // fires it, and the first frame back would otherwise carry the whole gap.
  if (document.hidden) {
    last = now;
    return;
  }
  const dt = Math.min(1 / 30, (now - last) / 1000);
  last = now;

  updateAnim(dt);

  if (run.active && !anim.active) {
    if (!run.stepping) doStep();
    else if (run.pending) {
      run.pending = false;
      doStep();
    }
  }

  const moving = anim.active && (anim.kind === 'move' || anim.kind === 'bump');
  let tiltX = 0;
  let tiltZ = 0;
  if (anim.active) {
    const raw = Math.min(1, anim.t / anim.dur);
    const lean = Math.sin(raw * Math.PI);
    if (anim.kind === 'move') tiltX = lean * 0.22;
    else if (anim.kind === 'turn') tiltZ = lean * (anim.tyaw > anim.fyaw ? 0.16 : -0.16);
    else if (anim.kind === 'bump') tiltX = -lean * 0.2;
  }

  drone.update(dt, moving);
  drone.setPose(pose.x, pose.y + drone.bobOffset(), pose.z, pose.yaw, tiltX, tiltZ);

  if (wh) {
    const tile = wh.tileUnderDrone();
    const top = wh.topOf(tile);
    drone.setGroundY(top === null ? -1.5 : top * STEP);
  }

  world.update(dt);
  rig.update(dt);
  renderer.render(world.scene, camera);
}

// ---------------------------------------------------------------------------
// layout
// ---------------------------------------------------------------------------
function resize() {
  const w = Math.max(1, stage.clientWidth);
  const h = Math.max(1, stage.clientHeight);
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

window.addEventListener('resize', resize);
if (window.ResizeObserver) new ResizeObserver(resize).observe(stage);

// ---------------------------------------------------------------------------
// screens and buttons
// ---------------------------------------------------------------------------
function goPlay() {
  mode = 'play';
  hud.hideScreens();
}

function goScreen(name) {
  mode = name;
  hud.showScreen(name);
}

function openLevels() {
  // Leaving for the menu stops the machine: a run that keeps stepping behind a
  // full screen overlay would pop its own win screen over the level grid.
  if (run.active) stopRun(null);
  hud.buildLevelGrid(LEVELS, storage, (i) => {
    loadLevel(i);
    goPlay();
  });
  goScreen('levels');
}

function bind(id, fn) {
  const el = $(id);
  if (!el) return;
  el.addEventListener('click', (e) => {
    e.preventDefault();
    el.blur();
    audio.resume();
    fn();
  });
}

bind('btn-play', () => {
  loadLevel(0);
  goPlay();
});
bind('btn-continue', () => {
  loadLevel(Math.min(storage.maxIndex, LEVELS.length - 1));
  goPlay();
});
bind('btn-title-levels', openLevels);
bind('btn-levels', openLevels);
bind('btn-levels-back', () => goPlay());
bind('btn-wipe', () => {
  storage.wipe();
  hud.buildLevelGrid(LEVELS, storage, (i) => {
    loadLevel(i);
    goPlay();
  });
  hud.toast('PROGRESSION EFFACEE');
});
bind('btn-resume', () => goPlay());
bind('btn-pause-levels', openLevels);
bind('btn-pause-title', () => goScreen('title'));
bind('btn-run', () => startRun(false));
bind('btn-step', () => stepOnce());
bind('btn-stop', () => {
  if (run.active) stopRun('ARRET DEMANDE');
  else resetRun(true);
});
bind('btn-undo', () => undo());
bind('btn-reset-prog', () => clearProgram());
bind('btn-next', () => {
  if (levelIndex + 1 < LEVELS.length) {
    loadLevel(levelIndex + 1);
    goPlay();
  } else {
    hud.setEndSummary(summary());
    goScreen('end');
  }
});
bind('btn-retry', () => {
  resetRun(true);
  goPlay();
});
bind('btn-win-levels', openLevels);
bind('btn-end-levels', openLevels);
bind('btn-end-title', () => goScreen('title'));

for (const chip of document.querySelectorAll('#speed-row .chip')) {
  chip.addEventListener('click', () => {
    chip.blur();
    run.speed = Number(chip.dataset.speed) || 1;
    for (const c of document.querySelectorAll('#speed-row .chip')) c.classList.toggle('on', c === chip);
    audio.play('ui');
  });
}

const volume = $('volume');
volume.addEventListener('input', () => {
  audio.setVolume(Number(volume.value) / 100);
  $('volume-value').textContent = volume.value;
});
audio.setVolume(Number(volume.value) / 100);

function summary() {
  let gold = 0;
  for (const lv of LEVELS) {
    const best = storage.bestFor(lv.id);
    if (best !== null && best <= lv.optimal) gold++;
  }
  return gold + ' MEDAILLE(S) OR SUR ' + LEVELS.length;
}

function stepOnce() {
  if (!run.active) {
    startRun(true);
    return;
  }
  run.stepping = true;
  run.pending = true;
  audio.setRunning(false);
  hud.setStatus('PAS A PAS', 'ok');
}

function undo() {
  if (run.active) return;
  if (program.undo()) {
    panel.refresh();
    onProgramChanged();
    audio.play('clear');
  }
}

function clearProgram() {
  if (run.active) return;
  if (program.clearAll()) {
    panel.refresh();
    onProgramChanged();
    audio.play('clear');
    hud.toast('PROGRAMME EFFACE');
  }
}

// ---------------------------------------------------------------------------
// keyboard
// ---------------------------------------------------------------------------
window.addEventListener('keydown', (e) => {
  // A focused slider must keep its arrow keys, but Escape and Enter belong to
  // the game: without this the pause screen cannot be closed with the keyboard
  // once the volume slider has been touched.
  if (e.target && e.target.tagName === 'INPUT' && e.key !== 'Escape' && e.key !== 'Enter') return;
  if (e.target && e.target.tagName === 'INPUT') e.target.blur();

  if (mode !== 'play') {
    if (e.key === 'Escape') {
      e.preventDefault();
      if (mode !== 'title') goPlay();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (mode === 'title') {
        audio.resume();
        loadLevel(Math.min(storage.maxIndex, LEVELS.length - 1));
        goPlay();
      } else if (mode === 'win') {
        if (levelIndex + 1 < LEVELS.length) {
          loadLevel(levelIndex + 1);
          goPlay();
        } else {
          hud.setEndSummary(summary());
          goScreen('end');
        }
      } else goPlay();
    }
    return;
  }

  if (e.key === 'Enter') {
    e.preventDefault();
    startRun(false);
    return;
  }
  if (e.key === 'Escape') {
    e.preventDefault();
    if (run.active) stopRun('ARRET DEMANDE');
    else goScreen('pause');
    return;
  }
  if (e.key === 'F10') {
    e.preventDefault();
    stepOnce();
    return;
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) {
    e.preventDefault();
    undo();
    return;
  }
  if (!e.ctrlKey && !e.metaKey && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    clearProgram();
    return;
  }
  if (!e.ctrlKey && !e.metaKey && panel.handleKey(e)) {
    e.preventDefault();
  }
});

canvas.addEventListener('pointerdown', () => audio.resume(), { once: true });

// ---------------------------------------------------------------------------
// go
// ---------------------------------------------------------------------------
loadLevel(Math.min(storage.maxIndex, LEVELS.length - 1));
mode = 'title';
hud.showScreen('title');
resize();
requestAnimationFrame(frame);

// Debug handle, mirrors what the other games in this repo expose.
window.game = {
  LEVELS,
  world,
  drone,
  renderer,
  camera,
  hud,
  audio,
  storage,
  OPS,
  panel,
  load(i) {
    loadLevel(i);
    goPlay();
  },
  get wh() {
    return wh;
  },
  get vm() {
    return vm;
  },
  get program() {
    return program;
  },
  get levelIndex() {
    return levelIndex;
  },
};
window.__ready = true;
