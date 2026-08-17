/**
 * MAREE - voxel world state.
 *
 * Pure data, no three.js. A level is authored as a compact top down grid (one
 * digit per column for the rock floor height, one letter per column for basin
 * membership) rather than a full stack of ASCII layers: with dozens of columns
 * per level this is far easier to author and to read back than nine repeated
 * layers of mostly-empty characters, while the runtime model underneath is
 * still a full 3D grid of cells (every column expands to `h` vertical cells).
 *
 * Column addressing: idx = z * w + x.
 */

export const VOID_FLOOR = -1;
export const NO_BASIN = -1;

/** One water level cran below the floor: the basin holds no water at all. */
export const EMPTY_LEVEL = -1;

function charFloor(ch) {
  if (ch === ' ') return VOID_FLOOR;
  const v = ch.charCodeAt(0) - 48; // '0'..'9'
  if (v < 0 || v > 9) throw new Error('Hauteur de sol invalide: "' + ch + '"');
  return v;
}

/**
 * Builds a fresh mutable state from a level definition (see levels.js for the
 * authored shape). Every array here is sized once and reused for the whole
 * level session; undo works by cloning this same shape.
 */
export function createWorld(level) {
  const w = level.w;
  const d = level.d;
  const h = level.h;
  if (level.floor.length !== d) throw new Error('Niveau ' + level.id + ': ' + level.floor.length + ' lignes au lieu de ' + d);
  if (level.basin.length !== d) throw new Error('Niveau ' + level.id + ': grille de bassins incomplete');

  const floor = new Int8Array(w * d).fill(VOID_FLOOR);
  const basinOf = new Int8Array(w * d).fill(NO_BASIN);

  for (let z = 0; z < d; z++) {
    const frow = level.floor[z];
    const brow = level.basin[z];
    if (frow.length !== w) throw new Error('Niveau ' + level.id + ': ligne de sol z=' + z + ' fait ' + frow.length + ' au lieu de ' + w);
    if (brow.length !== w) throw new Error('Niveau ' + level.id + ': ligne de bassin z=' + z + ' fait ' + brow.length + ' au lieu de ' + w);
    for (let x = 0; x < w; x++) {
      const i = z * w + x;
      floor[i] = charFloor(frow[x]);
    }
  }

  // Basin ids: stable order taken from the level's own `basins` map so index 0
  // is always the same basin across a session (levelEntries / HUD rely on it).
  const basinIds = Object.keys(level.basins);
  const basinIndexOf = {};
  for (let i = 0; i < basinIds.length; i++) basinIndexOf[basinIds[i]] = i;

  for (let z = 0; z < d; z++) {
    const brow = level.basin[z];
    for (let x = 0; x < w; x++) {
      const ch = brow[x];
      if (ch === '.' || ch === ' ') continue;
      const bi = basinIndexOf[ch];
      if (bi === undefined) throw new Error('Niveau ' + level.id + ': bassin "' + ch + '" non declare');
      basinOf[z * w + x] = bi;
    }
  }

  const basins = basinIds.map((id) => {
    const def = level.basins[id];
    const startLevel = def.level === undefined ? EMPTY_LEVEL : def.level;
    return {
      id,
      level: startLevel,
      visual: startLevel,
      min: EMPTY_LEVEL,
      max: h - 1,
      freeze: !!def.freeze,
      iceLevels: [],
      stableAt: startLevel,
      stableTime: 0,
    };
  });

  // Stone crates permanently raise the floor of their column by one cell, from
  // the very first frame: they are level geometry, not a moving body.
  const stoneAt = [];
  for (const s of level.stone || []) {
    const i = s.z * w + s.x;
    if (floor[i] === VOID_FLOOR) throw new Error('Niveau ' + level.id + ': pierre hors grille en ' + s.x + ',' + s.z);
    floor[i] += 1;
    stoneAt.push({ x: s.x, z: s.z });
  }

  // Wood crates stay data-driven and dynamic: their resting floor is recorded
  // once, but their standing height is recomputed every time water moves.
  const wood = (level.wood || []).map((wdef) => {
    const i = wdef.z * w + wdef.x;
    if (floor[i] === VOID_FLOOR) throw new Error('Niveau ' + level.id + ': bois hors grille en ' + wdef.x + ',' + wdef.z);
    return { x: wdef.x, z: wdef.z, homeFloor: floor[i] };
  });
  const woodByCol = new Map();
  for (const wobj of wood) woodByCol.set(wobj.z * w + wobj.x, wobj);

  const gates = (level.gates || []).map((g) => ({
    a: basinIndexOf[g.a],
    b: basinIndexOf[g.b],
    x: g.x,
    z: g.z,
    open: !!g.open,
  }));

  const state = {
    level,
    w,
    d,
    h,
    floor,
    basinOf,
    basins,
    stoneAt,
    wood,
    woodByCol,
    gates,
    groupOf: new Int8Array(basins.length),
    groups: [],
    start: { x: level.start.x, z: level.start.z },
    exit: { x: level.exit.x, z: level.exit.z },
    explorer: {
      x: level.start.x,
      z: level.start.z,
      h: 0,
      fromX: level.start.x,
      fromZ: level.start.z,
      fromH: 0,
      swimming: false,
      stepT: 1,
      stepDur: 0.001,
      path: null,
      pathIndex: 0,
      repathPending: true,
      submerged: 0,
      status: 'alive', // alive | won | drowned
      idleT: 0,
    },
    moves: 0,
    undos: 0,
    elapsed: 0,
  };

  rebuildGroups(state);
  return state;
}

export function colIndex(state, x, z) {
  return z * state.w + x;
}

export function inBounds(state, x, z) {
  return x >= 0 && z >= 0 && x < state.w && z < state.d;
}

export function isVoid(state, x, z) {
  if (!inBounds(state, x, z)) return true;
  return state.floor[colIndex(state, x, z)] === VOID_FLOOR;
}

export function woodAt(state, x, z) {
  return state.woodByCol.get(colIndex(state, x, z)) || null;
}

/**
 * Classifies how deep `level` (a basin's filled-up-to cran, EMPTY_LEVEL when
 * dry) sits relative to a standing surface at height `h`. The explorer is
 * three cells tall (feet / neck / head, see config.js): shallow water at his
 * feet is still walking, water at his neck is swimming (safe), and anything
 * that would cover his head is excluded from the path graph entirely.
 */
export function classify(h, level) {
  if (level < h) return 'dry';
  if (level === h) return 'shallow';
  if (level === h + 1) return 'swim';
  return 'drown';
}

/**
 * All standing surfaces available at a column right now: the ground (rock,
 * baked-in stone, or a floating wood crate riding the current water) plus any
 * ice plane this basin has ever formed. Land columns (no basin) are always
 * dry. Returns [] for a void column.
 */
export function standableHeights(state, x, z) {
  if (isVoid(state, x, z)) return [];
  const i = colIndex(state, x, z);
  const floor = state.floor[i];
  const basinIdx = state.basinOf[i];
  if (basinIdx === NO_BASIN) return [{ h: floor, basin: NO_BASIN, kind: 'ground' }];

  const basin = state.basins[basinIdx];
  const out = [];
  const wood = state.woodByCol.get(i);
  if (wood) {
    out.push({ h: Math.max(wood.homeFloor, basin.level), basin: basinIdx, kind: 'wood' });
  } else {
    out.push({ h: floor, basin: basinIdx, kind: 'ground' });
  }
  for (const iceY of basin.iceLevels) {
    out.push({ h: iceY, basin: basinIdx, kind: 'ice' });
  }
  return out;
}

/** Best resting node for a column at level load: the plain dry ground entry. */
export function groundNode(state, x, z) {
  const nodes = standableHeights(state, x, z);
  for (const n of nodes) if (n.kind !== 'ice') return n;
  return nodes[0] || null;
}

// ---------------------------------------------------------------------------
// Basin connectivity (open gates merge basins into one shared level)
// ---------------------------------------------------------------------------

/** Recomputes state.groupOf / state.groups from the current gate states. */
export function rebuildGroups(state) {
  const n = state.basins.length;
  const parent = new Int8Array(n);
  for (let i = 0; i < n; i++) parent[i] = i;
  function find(i) {
    while (parent[i] !== i) {
      parent[i] = parent[parent[i]];
      i = parent[i];
    }
    return i;
  }
  function union(a, b) {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[ra] = rb;
  }
  for (const g of state.gates) if (g.open) union(g.a, g.b);

  const groupIdOf = new Map();
  const groups = [];
  for (let i = 0; i < n; i++) {
    const root = find(i);
    let gid = groupIdOf.get(root);
    if (gid === undefined) {
      gid = groups.length;
      groupIdOf.set(root, gid);
      groups.push([]);
    }
    state.groupOf[i] = gid;
    groups[gid].push(i);
  }
  state.groups = groups;
}

// ---------------------------------------------------------------------------
// Snapshot / restore, for history.js
// ---------------------------------------------------------------------------

export function cloneWorld(state) {
  return {
    basins: state.basins.map((b) => ({ ...b, iceLevels: b.iceLevels.slice() })),
    gates: state.gates.map((g) => ({ ...g })),
    explorer: { ...state.explorer },
    moves: state.moves,
    undos: state.undos,
  };
}

export function copyInto(state, snap) {
  for (let i = 0; i < state.basins.length; i++) {
    const dst = state.basins[i];
    const src = snap.basins[i];
    dst.level = src.level;
    dst.visual = src.visual;
    dst.freeze = src.freeze;
    dst.iceLevels = src.iceLevels.slice();
    dst.stableAt = src.stableAt;
    dst.stableTime = src.stableTime;
  }
  for (let i = 0; i < state.gates.length; i++) state.gates[i].open = snap.gates[i].open;
  Object.assign(state.explorer, snap.explorer);
  state.moves = snap.moves;
  state.undos = snap.undos;
  rebuildGroups(state);
}
