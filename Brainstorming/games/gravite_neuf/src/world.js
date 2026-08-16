/**
 * GRAVITE NEUF - voxel world state.
 *
 * Pure data, no three.js: the same module is imported by the browser and by the
 * offline solver that computes the par of every level. Everything here is
 * deterministic and integer based, which is what makes undo a simple snapshot.
 *
 * Cell addressing: idx = (y * D + z) * W + x, y grows upward.
 */

/** Static cell kinds. A cell holds exactly one of these. */
export const S = {
  EMPTY: 0,
  WALL: 1,
  EXIT: 2,
  GLUE: 3,
  SPIKE: 4,
  SWITCH_A: 5,
  SWITCH_B: 6,
  GATE_A: 7,
  GATE_B: 8,
};

/** Movable kinds. */
export const MV = { PLAYER: 0, CRATE: 1, KEY: 2 };

/** The six gravity directions, in the order used by every public API. */
export const DIRS = [
  [1, 0, 0],
  [-1, 0, 0],
  [0, 1, 0],
  [0, -1, 0],
  [0, 0, 1],
  [0, 0, -1],
];

export const DIR = { PX: 0, NX: 1, PY: 2, NY: 3, PZ: 4, NZ: 5 };

export const DIR_LABEL = ['+X', '-X', '+Y', '-Y', '+Z', '-Z'];

const CHAR_STATIC = {
  '.': S.EMPTY,
  ' ': S.EMPTY,
  '#': S.WALL,
  X: S.EXIT,
  G: S.GLUE,
  '^': S.SPIKE,
  a: S.SWITCH_A,
  b: S.SWITCH_B,
  A: S.GATE_A,
  B: S.GATE_B,
};

const CHAR_MOVABLE = {
  '@': MV.PLAYER,
  o: MV.CRATE,
  '*': MV.KEY,
};

/**
 * Blocking test for a static cell. Gates are the only kind whose answer changes
 * during a fall, hence the two booleans instead of a lookup table.
 */
export function staticBlocks(kind, gateAOpen, gateBOpen) {
  if (kind === S.WALL || kind === S.GLUE || kind === S.SPIKE) return true;
  if (kind === S.GATE_A) return !gateAOpen;
  if (kind === S.GATE_B) return !gateBOpen;
  return false;
}

/**
 * Builds a fresh mutable state from a level definition.
 * `level.layers[y][z][x]` is one legend character.
 */
export function createState(level) {
  const H = level.layers.length;
  const D = level.layers[0].length;
  const W = level.layers[0][0].length;

  for (let y = 0; y < H; y++) {
    if (level.layers[y].length !== D) {
      throw new Error('Niveau ' + level.name + ': tranche y=' + y + ' a ' + level.layers[y].length + ' lignes au lieu de ' + D);
    }
    for (let z = 0; z < D; z++) {
      if (level.layers[y][z].length !== W) {
        throw new Error('Niveau ' + level.name + ': ligne y=' + y + ' z=' + z + ' fait ' + level.layers[y][z].length + ' caracteres au lieu de ' + W);
      }
    }
  }

  const statics = new Uint8Array(W * H * D);
  const movables = [];
  let playerIndex = -1;
  let keysTotal = 0;

  for (let y = 0; y < H; y++) {
    for (let z = 0; z < D; z++) {
      const row = level.layers[y][z];
      for (let x = 0; x < W; x++) {
        const ch = row[x];
        const mk = CHAR_MOVABLE[ch];
        if (mk !== undefined) {
          if (mk === MV.PLAYER) playerIndex = movables.length;
          if (mk === MV.KEY) keysTotal++;
          movables.push({
            kind: mk,
            x,
            y,
            z,
            stuck: false,
            alive: true,
            voided: false,
            killed: 0,
            blockedBy: -1,
          });
          continue;
        }
        const sk = CHAR_STATIC[ch];
        if (sk === undefined) {
          throw new Error('Niveau ' + level.name + ': caractere inconnu "' + ch + '"');
        }
        statics[(y * D + z) * W + x] = sk;
      }
    }
  }

  if (playerIndex < 0) throw new Error('Niveau ' + level.name + ': pas de cube joueur');

  return {
    level,
    W,
    H,
    D,
    statics,
    movables,
    playerIndex,
    keysTotal,
    keysTaken: 0,
    crateLost: false,
    status: 'play',
    reason: '',
    gravity: DIR.NY,
    occ: new Int16Array(W * H * D).fill(-1),
    order: new Int32Array(movables.length),
  };
}

export function idx(state, x, y, z) {
  return (y * state.D + z) * state.W + x;
}

export function inside(state, x, y, z) {
  return x >= 0 && y >= 0 && z >= 0 && x < state.W && y < state.H && z < state.D;
}

/** Rebuilds the movable occupancy index. Called once per fall iteration. */
export function rebuildOcc(state) {
  const occ = state.occ;
  occ.fill(-1);
  const ms = state.movables;
  for (let i = 0; i < ms.length; i++) {
    const m = ms[i];
    if (!m.alive) continue;
    occ[(m.y * state.D + m.z) * state.W + m.x] = i;
  }
}

/** True when at least one live movable sits on a plate of the given group. */
export function switchOn(state, plateKind) {
  const ms = state.movables;
  const statics = state.statics;
  for (let i = 0; i < ms.length; i++) {
    const m = ms[i];
    if (!m.alive) continue;
    if (!inside(state, m.x, m.y, m.z)) continue;
    if (statics[(m.y * state.D + m.z) * state.W + m.x] === plateKind) return true;
  }
  return false;
}

/** Deep copy, cheap enough that undo can keep one per move for a whole session. */
export function cloneState(state) {
  const movables = new Array(state.movables.length);
  for (let i = 0; i < state.movables.length; i++) {
    const m = state.movables[i];
    movables[i] = {
      kind: m.kind,
      x: m.x,
      y: m.y,
      z: m.z,
      stuck: m.stuck,
      alive: m.alive,
      voided: m.voided,
      killed: m.killed,
      blockedBy: m.blockedBy,
    };
  }
  return {
    level: state.level,
    W: state.W,
    H: state.H,
    D: state.D,
    statics: state.statics,
    movables,
    playerIndex: state.playerIndex,
    keysTotal: state.keysTotal,
    keysTaken: state.keysTaken,
    crateLost: state.crateLost,
    status: state.status,
    reason: state.reason,
    gravity: state.gravity,
    occ: state.occ,
    order: state.order,
  };
}

/**
 * Copies `src` into `dst` in place. Used by undo so the render layer keeps
 * pointing at the very same movable objects instead of rebuilding its meshes.
 */
export function copyInto(dst, src) {
  for (let i = 0; i < dst.movables.length; i++) {
    const a = dst.movables[i];
    const b = src.movables[i];
    a.x = b.x;
    a.y = b.y;
    a.z = b.z;
    a.stuck = b.stuck;
    a.alive = b.alive;
    a.voided = b.voided;
    a.killed = b.killed;
    a.blockedBy = b.blockedBy;
  }
  dst.keysTaken = src.keysTaken;
  dst.crateLost = src.crateLost;
  dst.status = src.status;
  dst.reason = src.reason;
  dst.gravity = src.gravity;
  return dst;
}

/** Compact identity of a position, for the offline breadth first solver. */
export function hashState(state) {
  let out = state.gravity + '|';
  const ms = state.movables;
  for (let i = 0; i < ms.length; i++) {
    const m = ms[i];
    out += m.alive ? m.x + ',' + m.y + ',' + m.z + (m.stuck ? 's' : '') : 'x';
    out += ';';
  }
  return out;
}

/** Snapshot of every movable position, used to drive the fall animation. */
export function snapshot(state) {
  const n = state.movables.length;
  const pos = new Int16Array(n * 3);
  const alive = new Uint8Array(n);
  const stuck = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const m = state.movables[i];
    pos[i * 3] = m.x;
    pos[i * 3 + 1] = m.y;
    pos[i * 3 + 2] = m.z;
    alive[i] = m.alive ? 1 : 0;
    stuck[i] = m.stuck ? 1 : 0;
  }
  return { pos, alive, stuck };
}
