/**
 * CONTREPOIDS - discrete world model (mine shaft, platforms, ropes, objects).
 *
 * Pure data and pure functions, no three.js: the same module is imported by the
 * browser and by the offline solver that computes the par of every level.
 * Everything is integer based (crans of height, unit weights), which is what
 * makes undo a plain snapshot and the rope resolution fully deterministic.
 *
 * Columns are the vertical shafts of the mine. Each column occupies one (x,z)
 * grid cell and holds at most one item plus, optionally, the player. A column
 * is either GROUND (fixed height, never moves) or PLATFORM (moves between
 * minH and maxH, always as one side of one or more rope pairs).
 *
 * Ropes are strictly two-column pairs. A level that needs to link more than two
 * platforms chains several simple pairs through a shared column instead of
 * inventing a multi-way invariant: this file only ever implements pairs.
 */

export const KIND = { GROUND: 0, PLATFORM: 1 };

export const OBJ = { PIERRE: 'pierre', ENCLUME: 'enclume', BALLON: 'ballon' };

export const WEIGHT = { pierre: 1, enclume: 3, ballon: -1, player: 2 };

// Grid directions, (dx, dz). Order matches the label list used by the HUD/input.
export const DIRS = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
];
export const DIR = { EAST: 0, WEST: 1, SOUTH: 2, NORTH: 3 };
export const DIR_LABEL = ['est', 'ouest', 'sud', 'nord'];

/**
 * Builds a fresh mutable state from a level definition (see levels.js for the
 * authoring format: an ASCII grid of column letters plus per-letter specs).
 */
export function createState(level) {
  const rows = level.grid;
  const D = rows.length;
  const W = rows[0].length;
  for (let z = 0; z < D; z++) {
    if (rows[z].length !== W) {
      throw new Error('Niveau ' + level.name + ': ligne ' + z + ' fait ' + rows[z].length + ' caracteres au lieu de ' + W);
    }
  }

  const letterToId = {};
  const columns = [];

  for (let z = 0; z < D; z++) {
    for (let x = 0; x < W; x++) {
      const ch = rows[z][x];
      if (ch === '.') continue;
      const spec = level.columns[ch];
      if (!spec) throw new Error('Niveau ' + level.name + ': colonne inconnue "' + ch + '"');
      if (letterToId[ch] !== undefined) {
        throw new Error('Niveau ' + level.name + ': lettre "' + ch + '" utilisee deux fois dans la grille');
      }
      const id = columns.length;
      letterToId[ch] = id;
      const kind = spec.kind === 'platform' ? KIND.PLATFORM : KIND.GROUND;
      const minH = kind === KIND.PLATFORM ? spec.min : spec.h;
      const maxH = kind === KIND.PLATFORM ? spec.max : spec.h;
      columns.push({
        id,
        letter: ch,
        gx: x,
        gz: z,
        kind,
        minH,
        maxH,
        h: spec.h,
        item: null,
        ropeIds: [],
        isExit: ch === level.exit,
      });
    }
  }

  const ropes = [];
  for (let i = 0; i < level.ropes.length; i++) {
    const [la, lb] = level.ropes[i];
    const a = letterToId[la];
    const b = letterToId[lb];
    if (a === undefined || b === undefined) {
      throw new Error('Niveau ' + level.name + ': corde referencant une lettre inconnue (' + la + ',' + lb + ')');
    }
    const ropeId = ropes.length;
    ropes.push({ a, b });
    columns[a].ropeIds.push(ropeId);
    columns[b].ropeIds.push(ropeId);
  }

  if (level.items) {
    for (const letter in level.items) {
      const id = letterToId[letter];
      if (id === undefined) throw new Error('Niveau ' + level.name + ': objet sur lettre inconnue "' + letter + '"');
      columns[id].item = level.items[letter];
    }
  }

  const startId = letterToId[level.start];
  if (startId === undefined) throw new Error('Niveau ' + level.name + ': depart inconnu');
  const exitId = letterToId[level.exit];
  if (exitId === undefined) throw new Error('Niveau ' + level.name + ': sortie inconnue');

  return {
    level,
    W,
    D,
    columns,
    ropes,
    letterToId,
    playerCol: startId,
    holding: null,
    exitId,
    status: 'play',
  };
}

export function columnAt(state, gx, gz) {
  const cols = state.columns;
  for (let i = 0; i < cols.length; i++) {
    if (cols[i].gx === gx && cols[i].gz === gz) return cols[i];
  }
  return null;
}

function neighbor(state, dir) {
  const player = state.columns[state.playerCol];
  const [dx, dz] = DIRS[dir];
  return columnAt(state, player.gx + dx, player.gz + dz);
}

export function weightOf(state, colId) {
  const col = state.columns[colId];
  let w = col.item ? WEIGHT[col.item] : 0;
  if (state.playerCol === colId) w += WEIGHT.player;
  return w;
}

/** Resolves one rope pair against its current weights. Returns true if it moved. */
function resolveRope(state, ropeId, events) {
  const rope = state.ropes[ropeId];
  const a = state.columns[rope.a];
  const b = state.columns[rope.b];
  const wa = weightOf(state, rope.a);
  const wb = weightOf(state, rope.b);
  const d = wa - wb;
  if (d === 0) return false;
  let amount;
  if (d > 0) {
    amount = Math.min(d, a.h - a.minH, b.maxH - b.h);
    if (amount <= 0) return false;
    a.h -= amount;
    b.h += amount;
  } else {
    amount = Math.min(-d, a.maxH - a.h, b.h - b.minH);
    if (amount <= 0) return false;
    a.h += amount;
    b.h -= amount;
  }
  events.push({ type: 'rope', rope: ropeId, a: rope.a, b: rope.b, ah: a.h, bh: b.h, amount });
  return true;
}

/** Resolves every rope attached to a column. A weight change never cascades to
 * ropes that do not touch the column itself: only cargo/player mass changes a
 * weight, and moving a platform never changes what sits on it.
 *
 * `resolved` is a Set of rope ids shared across every resolveColumn() call made
 * for the same action: when the two columns touched by one action (e.g. the
 * player's `from` and `target` in a move/jump, or `mid`/`far` in a push) are
 * themselves the two ends of the same rope, that rope must only be resolved
 * once per action. Resolving it twice would recompute the same weight delta
 * against fresh margin and apply it a second time (see shaft.js module docs). */
function resolveColumn(state, colId, events, resolved) {
  const col = state.columns[colId];
  for (let i = 0; i < col.ropeIds.length; i++) {
    const ropeId = col.ropeIds[i];
    if (resolved.has(ropeId)) continue;
    resolved.add(ropeId);
    resolveRope(state, ropeId, events);
  }
}

function checkWin(state) {
  if (state.playerCol === state.exitId) state.status = 'won';
}

// ---------------------------------------------------------------------------
// Player actions. Each returns { ok, events }. `ok === false` means the action
// was physically impossible and must be refused without cost (lesson B: a
// legal action always executes even when it changes nothing this time).
// ---------------------------------------------------------------------------

export function canMove(state, dir) {
  const target = neighbor(state, dir);
  if (!target) return false;
  const player = state.columns[state.playerCol];
  return target.h === player.h || target.h === player.h - 1;
}

export function moveTo(state, dir) {
  if (!canMove(state, dir)) return { ok: false, events: [] };
  const events = [];
  const from = state.playerCol;
  const target = neighbor(state, dir);
  state.playerCol = target.id;
  const resolved = new Set();
  resolveColumn(state, from, events, resolved);
  resolveColumn(state, target.id, events, resolved);
  checkWin(state);
  events.unshift({ type: 'move', from, to: target.id });
  return { ok: true, events };
}

export function canJump(state, dir) {
  const target = neighbor(state, dir);
  if (!target) return false;
  const player = state.columns[state.playerCol];
  return target.h === player.h + 1;
}

export function jumpTo(state, dir) {
  if (!canJump(state, dir)) return { ok: false, events: [] };
  const events = [];
  const from = state.playerCol;
  const target = neighbor(state, dir);
  state.playerCol = target.id;
  const resolved = new Set();
  resolveColumn(state, from, events, resolved);
  resolveColumn(state, target.id, events, resolved);
  checkWin(state);
  events.unshift({ type: 'jump', from, to: target.id });
  return { ok: true, events };
}

export function canTake(state) {
  if (state.holding) return false;
  const col = state.columns[state.playerCol];
  return col.item === OBJ.PIERRE || col.item === OBJ.BALLON;
}

export function takeItem(state) {
  if (!canTake(state)) return { ok: false, events: [] };
  const col = state.columns[state.playerCol];
  const events = [];
  state.holding = col.item;
  col.item = null;
  resolveColumn(state, col.id, events, new Set());
  checkWin(state);
  events.unshift({ type: 'take', col: col.id, item: state.holding });
  return { ok: true, events };
}

export function canDrop(state) {
  if (!state.holding) return false;
  const col = state.columns[state.playerCol];
  return col.item === null;
}

export function dropItem(state) {
  if (!canDrop(state)) return { ok: false, events: [] };
  const col = state.columns[state.playerCol];
  const events = [];
  col.item = state.holding;
  const dropped = state.holding;
  state.holding = null;
  resolveColumn(state, col.id, events, new Set());
  checkWin(state);
  events.unshift({ type: 'drop', col: col.id, item: dropped });
  return { ok: true, events };
}

/** Pushes an anvil that sits on the column adjacent to the player, one further
 * cell away in the same direction, strictly at the same height on all three
 * columns (player's own column, the anvil's column, and its destination). */
export function canPush(state, dir) {
  const player = state.columns[state.playerCol];
  const mid = neighbor(state, dir);
  if (!mid || mid.item !== OBJ.ENCLUME) return false;
  const [dx, dz] = DIRS[dir];
  const far = columnAt(state, mid.gx + dx, mid.gz + dz);
  if (!far || far.item !== null) return false;
  return mid.h === player.h && far.h === player.h;
}

export function pushAnvil(state, dir) {
  if (!canPush(state, dir)) return { ok: false, events: [] };
  const [dx, dz] = DIRS[dir];
  const mid = neighbor(state, dir);
  const far = columnAt(state, mid.gx + dx, mid.gz + dz);
  const events = [];
  mid.item = null;
  far.item = OBJ.ENCLUME;
  const resolved = new Set();
  resolveColumn(state, mid.id, events, resolved);
  resolveColumn(state, far.id, events, resolved);
  checkWin(state);
  events.unshift({ type: 'push', from: mid.id, to: far.id });
  return { ok: true, events };
}

// ---------------------------------------------------------------------------
// Cloning, for undo and for the offline solver's visited-state map.
// ---------------------------------------------------------------------------

export function cloneState(state) {
  const columns = new Array(state.columns.length);
  for (let i = 0; i < state.columns.length; i++) {
    const c = state.columns[i];
    columns[i] = {
      id: c.id,
      letter: c.letter,
      gx: c.gx,
      gz: c.gz,
      kind: c.kind,
      minH: c.minH,
      maxH: c.maxH,
      h: c.h,
      item: c.item,
      ropeIds: c.ropeIds,
      isExit: c.isExit,
    };
  }
  return {
    level: state.level,
    W: state.W,
    D: state.D,
    columns,
    ropes: state.ropes,
    letterToId: state.letterToId,
    playerCol: state.playerCol,
    holding: state.holding,
    exitId: state.exitId,
    status: state.status,
  };
}

export function copyInto(dst, src) {
  for (let i = 0; i < dst.columns.length; i++) {
    dst.columns[i].h = src.columns[i].h;
    dst.columns[i].item = src.columns[i].item;
  }
  dst.playerCol = src.playerCol;
  dst.holding = src.holding;
  dst.status = src.status;
  return dst;
}

/** Compact identity of a position, used by the offline BFS solver to dedupe. */
export function hashState(state) {
  let out = state.playerCol + '|' + (state.holding || '-') + '|';
  const cols = state.columns;
  for (let i = 0; i < cols.length; i++) {
    out += cols[i].h + ',' + (cols[i].item ? cols[i].item[0] : '-') + ';';
  }
  return out;
}
