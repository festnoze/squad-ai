/**
 * PRISMA - boot, state machine and the single frame loop.
 *
 * The beam is recomputed synchronously after every edit rather than on a timer:
 * a puzzle of this size solves in well under a millisecond, and immediate
 * feedback is the whole point of the game.
 */

import * as THREE from 'three';

import { LEVELS, PIECE_KINDS, PIECE_LABEL, ROTATIONS } from './levels.js';
import {
  createGrid,
  canPlace,
  place,
  remove,
  rotate,
  isPlaced,
  isFree,
  inBounds,
  cellAt,
  snapshot,
  restore,
  sameSnapshot,
  totalPlaced,
  remaining,
  clearPlaced,
  worldToCellX,
  worldToCellY,
  CELL_TO_KIND,
} from './grid.js';
import { createSolver } from './beam.js';
import { createTextures } from './textures.js';
import { createPieceFactory } from './render/pieces.js';
import { createBoard } from './render/board.js';
import { createBeamFX } from './render/beamfx.js';
import { createOrbit } from './camera.js';
import { createInput } from './input.js';
import { createHUD, medalFor } from './hud.js';
import { createAudio } from './audio.js';

const STORAGE_KEY = 'prisma.progress';
const CELEBRATION_MS = 1500;

const _pick = new THREE.Vector3();

// ---------------------------------------------------------------------------
// persistence
// ---------------------------------------------------------------------------

function loadProgress() {
  const fallback = { unlocked: 0, best: {} };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') return fallback;
    return {
      unlocked: Number.isInteger(data.unlocked) ? Math.max(0, Math.min(LEVELS.length - 1, data.unlocked)) : 0,
      best: data.best && typeof data.best === 'object' ? data.best : {},
    };
  } catch {
    return fallback;
  }
}

function saveProgress(progress) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch {
    /* storage disabled or full: progress is a convenience, never a requirement */
  }
}

function wipeProgress() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* nothing to do */
  }
}

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------

async function nextFrame() {
  await new Promise((resolve) => window.requestAnimationFrame(() => resolve()));
}

async function boot() {
  const canvas = document.getElementById('scene');
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(46, window.innerWidth / window.innerHeight, 0.1, 200);

  // The HUD needs generated icons that do not exist yet, so it is handed a
  // container that gets filled in place once the textures are drawn.
  const icons = {};
  const hud = createHUD(icons);
  hud.setLoading(0.08, 'Contexte graphique...');
  await nextFrame();

  const textures = createTextures(renderer);
  Object.assign(icons, textures.icons);
  hud.setLoading(0.35, 'Gravure des textures...');
  await nextFrame();

  const factory = createPieceFactory(textures);
  const board = createBoard(scene, renderer, textures, factory);
  hud.setLoading(0.62, 'Montage de la chambre...');
  await nextFrame();

  const beamfx = createBeamFX(scene, textures);
  const orbit = createOrbit(camera);
  const audio = createAudio();
  const input = createInput(canvas);
  hud.setLoading(1, 'Calibration optique...');
  await nextFrame();

  return { renderer, scene, camera, textures, factory, board, beamfx, orbit, audio, input, hud };
}

// ---------------------------------------------------------------------------
// game
// ---------------------------------------------------------------------------

async function start() {
  const ctx = await boot();
  const { renderer, scene, camera, factory, board, beamfx, orbit, audio, input, hud } = ctx;

  const progress = loadProgress();

  let levelIndex = 0;
  let level = null;
  let grid = null;
  let solver = null;
  let result = null;

  let state = 'title';
  let celebrating = false;
  let celebrationToken = 0;
  let selectedKind = 'mirror';
  const pendingRot = {};
  for (const kind of PIECE_KINDS) pendingRot[kind] = 0;

  let hoverCell = null;
  let hoverNdc = null;
  const undoStack = [];
  let prevLit = null;

  // ---- solving -------------------------------------------------------------

  function refreshBeam(playCues = true) {
    result = solver.solve();
    board.refresh();
    board.setTargetStates(result);
    beamfx.setSegments(result);
    hud.setStats(result.litCount, result.totalTargets, totalPlaced(grid));
    hud.setTargets(grid, result);
    hud.updateInventory(grid, selectedKind);

    if (playCues && prevLit) {
      for (let i = 0; i < result.targetLit.length; i++) {
        if (result.targetLit[i] && !prevLit[i]) audio.lit(i);
        else if (!result.targetLit[i] && prevLit[i]) audio.unlit();
      }
    }
    prevLit = Uint8Array.from(result.targetLit);

    if (result.truncated) hud.toast('Trajet trop complexe, faisceau tronque', true);
    if (result.solved && state === 'play' && !celebrating) celebrate();
  }

  function pushUndo() {
    const snap = snapshot(grid);
    const top = undoStack[undoStack.length - 1];
    if (top && sameSnapshot(top, snap)) return;
    undoStack.push(snap);
  }

  function undo() {
    if (celebrating) return;
    if (undoStack.length === 0) {
      hud.toast('Rien a annuler');
      return;
    }
    restore(grid, undoStack.pop());
    audio.undo();
    refreshBeam();
  }

  // ---- level lifecycle -----------------------------------------------------

  function loadLevel(index, { announce = true } = {}) {
    levelIndex = Math.max(0, Math.min(LEVELS.length - 1, index));
    level = LEVELS[levelIndex];
    grid = createGrid(level);
    solver = createSolver(grid);
    undoStack.length = 0;
    prevLit = null;
    celebrating = false;
    // Invalidates any celebration timer still pending from the level we leave:
    // without this it fires on the new board and locks it behind a win panel.
    celebrationToken++;
    hoverCell = null;

    board.setGrid(grid);
    beamfx.setGrid(grid);
    orbit.frame(grid);

    selectedKind = PIECE_KINDS.find((k) => (level.inventory[k] || 0) > 0) || 'mirror';
    for (const kind of PIECE_KINDS) pendingRot[kind] = 0;

    hud.setLevel(levelIndex + 1, level);
    hud.buildInventory(level, (kind) => selectKind(kind));
    hud.setHint(level.hint);
    hud.show();
    hud.hideScreens();
    board.setHover(null);
    board.setSelection(null);

    state = 'play';
    input.setEnabled(true);
    refreshBeam(false);
    if (announce) {
      hud.banner(level.name, `Chambre ${String(levelIndex + 1).padStart(2, '0')}`, 1500);
      audio.levelStart();
    }
  }

  function restartLevel() {
    if (celebrating) return;
    if (totalPlaced(grid) > 0) pushUndo();
    clearPlaced(grid);
    audio.remove();
    hud.toast('Chambre remise a zero');
    refreshBeam(false);
  }

  function celebrate() {
    celebrating = true;
    const token = ++celebrationToken;
    const used = totalPlaced(grid);
    const medal = medalFor(used, level.optimum);
    const previous = progress.best[level.id];
    const improved = previous === undefined || used < previous;
    if (improved) progress.best[level.id] = used;
    progress.unlocked = Math.max(progress.unlocked, Math.min(LEVELS.length - 1, levelIndex + 1));
    saveProgress(progress);

    audio.solved();
    hud.banner('Cibles allumees', `${medal.label} - ${used} composant${used > 1 ? 's' : ''}`, CELEBRATION_MS);

    const isLast = levelIndex === LEVELS.length - 1;
    window.setTimeout(() => {
      if (token !== celebrationToken || state !== 'play') return;
      hud.setWin({ medal, used, optimum: level.optimum, levelName: level.name, isLast, improved });
      document.getElementById('btn-next').textContent = isLast ? 'Bilan final' : 'Chambre suivante';
      state = 'win';
      hud.showScreen('win');
    }, CELEBRATION_MS);
  }

  function showEnd() {
    let golds = 0;
    let total = 0;
    for (const lv of LEVELS) {
      const best = progress.best[lv.id];
      if (best === undefined) continue;
      total += best;
      if (best <= lv.optimum) golds++;
    }
    const perfect = LEVELS.reduce((sum, lv) => sum + lv.optimum, 0);
    hud.setEndStats(
      `${golds} medailles d or sur ${LEVELS.length}. ${total} composants poses au total, contre ${perfect} pour un parcours parfait.`,
    );
    state = 'end';
    hud.hide();
    hud.showScreen('end');
  }

  // ---- interaction ---------------------------------------------------------

  function selectKind(kind) {
    if ((level.inventory[kind] || 0) <= 0) {
      hud.toast(`${PIECE_LABEL[kind]} indisponible dans cette chambre`, true);
      audio.refuse();
      return;
    }
    selectedKind = kind;
    audio.select();
    hud.updateInventory(grid, selectedKind);
    updateHoverVisuals();
  }

  function cellFromNdc(x, y) {
    if (x === null || !grid) return null;
    if (!orbit.pick(x, y, _pick)) return null;
    const cx = worldToCellX(grid, _pick.x);
    const cy = worldToCellY(grid, _pick.z);
    if (!inBounds(grid, cx, cy)) return null;
    return { x: cx, y: cy };
  }

  function updateHoverVisuals() {
    if (!grid) return;
    if (!hoverCell) {
      board.setHover(null);
      board.setSelection(null);
      board.setGhost(null, 0, false);
      return;
    }
    const { x, y } = hoverCell;
    const placed = isPlaced(grid, x, y);
    const free = isFree(grid, x, y);
    const canDrop = free && canPlace(grid, x, y, selectedKind) === 'ok';
    board.setHover(x, y, placed || canDrop);
    board.setSelection(placed ? x : null, y);
    board.setGhost(selectedKind, pendingRot[selectedKind], canDrop);
  }

  function onPrimary() {
    audio.resume(); // a click on the board is a user gesture like any other
    if (celebrating || state !== 'play' || !hoverCell) return;
    const { x, y } = hoverCell;
    if (isPlaced(grid, x, y)) {
      const kind = CELL_TO_KIND[cellAt(grid, x, y).type];
      selectedKind = kind;
      pendingRot[kind] = cellAt(grid, x, y).rot;
      audio.select();
      hud.updateInventory(grid, selectedKind);
      updateHoverVisuals();
      return;
    }
    const verdict = canPlace(grid, x, y, selectedKind);
    if (verdict !== 'ok') {
      audio.refuse();
      hud.toast(
        verdict === 'stock epuise'
          ? `Plus de ${PIECE_LABEL[selectedKind].toLowerCase()} disponible`
          : `Impossible ici : ${verdict}`,
        true,
      );
      return;
    }
    pushUndo();
    place(grid, x, y, selectedKind, pendingRot[selectedKind]);
    audio.place();
    refreshBeam();
    updateHoverVisuals();
  }

  function onSecondary() {
    if (celebrating || state !== 'play' || !hoverCell) return;
    const { x, y } = hoverCell;
    if (isPlaced(grid, x, y)) {
      pushUndo();
      rotate(grid, x, y, 1);
      audio.rotate();
      refreshBeam();
      updateHoverVisuals();
      return;
    }
    // On a free cell the rotation applies to what is about to be dropped.
    pendingRot[selectedKind] = (pendingRot[selectedKind] + 1) % ROTATIONS[selectedKind];
    audio.rotate();
    updateHoverVisuals();
  }

  function onDelete() {
    if (celebrating || state !== 'play' || !hoverCell) return;
    const { x, y } = hoverCell;
    if (!isPlaced(grid, x, y)) return;
    pushUndo();
    remove(grid, x, y);
    audio.remove();
    refreshBeam();
    updateHoverVisuals();
  }

  function onWheel(delta) {
    if (state === 'play' && !celebrating && hoverCell && isPlaced(grid, hoverCell.x, hoverCell.y)) {
      pushUndo();
      rotate(grid, hoverCell.x, hoverCell.y, delta > 0 ? 1 : -1);
      audio.rotate();
      refreshBeam();
      updateHoverVisuals();
      return;
    }
    orbit.zoom(delta);
  }

  function togglePause() {
    // Pausing mid celebration would swallow the win panel: the timer refuses to
    // fire outside 'play' and nothing would ever bring it back.
    if (celebrating && state === 'play') return;
    if (state === 'play') {
      state = 'pause';
      const left = PIECE_KINDS.filter((k) => (level.inventory[k] || 0) > 0)
        .map((k) => `${PIECE_LABEL[k]} ${remaining(grid, k)}`)
        .join(' - ');
      hud.setPauseSub(`${level.name} - ${left}`);
      hud.showScreen('pause');
    } else if (state === 'pause') {
      state = 'play';
      hud.hideScreens();
    } else if (state === 'levels' && level) {
      // Backing out of the level list after a win returns to the win panel,
      // never to a board that is already solved and would look stuck.
      state = celebrating ? 'win' : 'play';
      if (celebrating) hud.showScreen('win');
      else hud.hideScreens();
      hud.show();
    }
  }

  function openLevels() {
    state = 'levels';
    hud.buildLevelGrid(LEVELS, progress, levelIndex, (i) => {
      audio.resume();
      loadLevel(i);
    });
    hud.showScreen('levels');
  }

  // ---- input wiring --------------------------------------------------------

  input.on('hover', (x, y) => {
    hoverNdc = x === null ? null : [x, y];
    if (state !== 'play' && state !== 'pause') {
      hoverCell = null;
      updateHoverVisuals();
      return;
    }
    hoverCell = cellFromNdc(x, y);
    updateHoverVisuals();
  });
  input.on('orbit', (dx, dy) => orbit.orbit(dx, dy));
  input.on('wheel', onWheel);
  input.on('primary', onPrimary);
  input.on('secondary', onSecondary);
  input.on('tertiary', onDelete);
  input.on('delete', onDelete);
  input.on('undo', undo);
  input.on('restart', () => {
    if (state === 'play') restartLevel();
  });
  input.on('pause', togglePause);
  input.on('kind', (i) => {
    if (state !== 'play') return;
    const kind = PIECE_KINDS[i];
    if (kind) selectKind(kind);
  });
  input.on('mute', () => hud.setMuted(audio.toggleMute()));
  input.on('help', () => {
    if (level) hud.setHint(level.hint);
  });
  input.on('recenter', () => orbit.reset());

  // ---- buttons -------------------------------------------------------------

  function bind(id, fn) {
    const node = document.getElementById(id);
    if (!node) throw new Error(`Bouton #${id} absent de index.html`);
    node.addEventListener('click', () => {
      audio.resume();
      fn();
    });
    return node;
  }

  bind('btn-play', () => loadLevel(progress.unlocked));
  bind('btn-levels', openLevels);
  bind('btn-levels-back', () => {
    if (!level) {
      state = 'title';
      hud.showScreen('title');
      return;
    }
    state = celebrating ? 'win' : 'play';
    if (celebrating) hud.showScreen('win');
    else hud.hideScreens();
    hud.show();
  });
  bind('btn-wipe', () => {
    wipeProgress();
    progress.unlocked = 0;
    progress.best = {};
    hud.buildLevelGrid(LEVELS, progress, levelIndex, (i) => loadLevel(i));
    hud.toast('Progression effacee');
  });
  bind('btn-resume', togglePause);
  bind('btn-restart-pause', () => {
    state = 'play';
    hud.hideScreens();
    restartLevel();
  });
  bind('btn-levels-pause', openLevels);
  bind('btn-next', () => {
    if (levelIndex === LEVELS.length - 1) showEnd();
    else loadLevel(levelIndex + 1);
  });
  bind('btn-retry', () => loadLevel(levelIndex, { announce: false }));
  bind('btn-win-levels', openLevels);
  bind('btn-end-levels', openLevels);
  bind('btn-undo', undo);
  bind('btn-restart', restartLevel);
  bind('btn-menu', openLevels);
  bind('btn-mute', () => hud.setMuted(audio.toggleMute()));

  const volume = document.getElementById('volume');
  const volumeValue = document.getElementById('volume-value');
  volume.addEventListener('input', () => {
    const v = Number(volume.value);
    volumeValue.textContent = String(v);
    audio.setVolume(v / 100);
  });
  audio.setVolume(Number(volume.value) / 100);

  // ---- resize and loop -----------------------------------------------------

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(w, h, false);
    beamfx.setPixelScale(h * renderer.getPixelRatio());
    if (hoverNdc) {
      hoverCell = cellFromNdc(hoverNdc[0], hoverNdc[1]);
      updateHoverVisuals();
    }
  }
  window.addEventListener('resize', resize);
  resize();

  let last = performance.now();
  let time = 0;
  function frame(nowMs) {
    window.requestAnimationFrame(frame);
    const dt = Math.min(0.05, (nowMs - last) / 1000);
    last = nowMs;
    time += dt;

    orbit.update(dt);
    if (grid) {
      board.update(dt, camera, time);
      beamfx.update(dt);
    }
    renderer.render(scene, camera);
  }

  // ---- entry ---------------------------------------------------------------

  hud.setMuted(audio.isMuted());
  hud.hide();
  document.getElementById('btn-play').textContent =
    progress.unlocked > 0 || Object.keys(progress.best).length > 0 ? 'Continuer' : 'Commencer';
  state = 'title';
  hud.showScreen('title');

  window.requestAnimationFrame(frame);

  window.game = {
    get grid() {
      return grid;
    },
    get result() {
      return result;
    },
    get level() {
      return level;
    },
    loadLevel,
    progress,
    renderer,
    scene,
    camera,
    board,
    beamfx,
    orbit,
    audio,
    hud,
    factory,
    LEVELS,
  };
  window.__ready = true;
}

start().catch((err) => {
  if (window.__fail) window.__fail(err && err.message ? err.message : String(err), err && err.stack);
  else throw err;
});
