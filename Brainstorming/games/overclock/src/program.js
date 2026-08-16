/**
 * OVERCLOCK - program model.
 *
 * A program is a fixed list of procedures, each a fixed list of slots. A slot
 * holds either null or { op, cond }. Every mutation snapshots the whole thing
 * first, which is what makes undo unlimited and free of edge cases.
 */

export const PROC_NAMES = ['PRINCIPAL', 'P1', 'P2'];

export const OPS = {
  FWD: { glyph: '▲', label: 'AVANCER', help: 'Avance d une case a la meme hauteur' },
  LEFT: { glyph: '↶', label: 'GAUCHE', help: 'Pivote d un quart de tour a gauche' },
  RIGHT: { glyph: '↷', label: 'DROITE', help: 'Pivote d un quart de tour a droite' },
  JUMP: { glyph: '⤴', label: 'SAUT', help: 'Monte d une marche, descend, ou franchit un vide' },
  ACT: { glyph: '◉', label: 'ACTIVER', help: 'Allume la cible sous le drone' },
  GRAB: { glyph: '↥', label: 'PRENDRE', help: 'Saisit la caisse posee devant' },
  DROP: { glyph: '↧', label: 'POSER', help: 'Depose la caisse devant' },
  PAINT_R: { glyph: '●', label: 'PEINDRE', help: 'Peint la dalle sous le drone en rouge', paint: 'r' },
  PAINT_G: { glyph: '●', label: 'PEINDRE', help: 'Peint la dalle sous le drone en vert', paint: 'g' },
  PAINT_B: { glyph: '●', label: 'PEINDRE', help: 'Peint la dalle sous le drone en bleu', paint: 'b' },
  CALL0: { glyph: 'PR', label: 'PRINCIPAL', help: 'Appelle PRINCIPAL', call: 0 },
  CALL1: { glyph: 'P1', label: 'P1', help: 'Appelle P1', call: 1 },
  CALL2: { glyph: 'P2', label: 'P2', help: 'Appelle P2', call: 2 },
};

export const CONDS = ['r', 'g', 'b'];

export const COND_LABEL = { r: 'ROUGE', g: 'VERT', b: 'BLEU' };

export function createProgram(level) {
  const procs = level.procs.map((n, i) => ({
    name: PROC_NAMES[i] || 'P' + i,
    slots: new Array(n).fill(null),
  }));

  const history = [];

  function snapshot() {
    return procs.map((p) => p.slots.map((s) => (s ? { op: s.op, cond: s.cond } : null)));
  }

  function apply(snap) {
    for (let i = 0; i < procs.length; i++) {
      const src = snap[i] || [];
      const dst = procs[i].slots;
      for (let j = 0; j < dst.length; j++) dst[j] = src[j] ? { op: src[j].op, cond: src[j].cond } : null;
    }
  }

  const program = {
    level,
    procs,

    get(p, i) {
      const proc = procs[p];
      return proc && i >= 0 && i < proc.slots.length ? proc.slots[i] : null;
    },

    /** Snapshot before mutating: callers never have to think about undo. */
    mark() {
      history.push(snapshot());
      // A snapshot is a handful of tiny objects, so the ceiling exists only to
      // bound a pathological session, never to limit normal editing.
      if (history.length > 5000) history.shift();
    },

    set(p, i, op, cond) {
      const proc = procs[p];
      if (!proc || i < 0 || i >= proc.slots.length) return false;
      const prev = proc.slots[i];
      if (prev && prev.op === op && prev.cond === (cond || null)) return false;
      program.mark();
      proc.slots[i] = { op, cond: cond || null };
      return true;
    },

    clear(p, i) {
      const proc = procs[p];
      if (!proc || i < 0 || i >= proc.slots.length || !proc.slots[i]) return false;
      program.mark();
      proc.slots[i] = null;
      return true;
    },

    /** Cycles null -> first allowed colour -> ... -> null. */
    cycleCond(p, i, allowed) {
      const proc = procs[p];
      if (!proc || !proc.slots[i] || !allowed || !allowed.length) return false;
      const slot = proc.slots[i];
      const idx = allowed.indexOf(slot.cond);
      program.mark();
      slot.cond = idx + 1 >= allowed.length ? null : allowed[idx + 1];
      return true;
    },

    count() {
      let n = 0;
      for (const p of procs) for (const s of p.slots) if (s) n++;
      return n;
    },

    isEmpty() {
      return program.count() === 0;
    },

    undo() {
      if (!history.length) return false;
      apply(history.pop());
      return true;
    },

    canUndo() {
      return history.length > 0;
    },

    clearAll() {
      if (program.isEmpty()) return false;
      program.mark();
      for (const p of procs) p.slots.fill(null);
      return true;
    },

    serialize() {
      return procs.map((p) => p.slots.map((s) => (s ? s.op + (s.cond ? '@' + s.cond : '') : '')));
    },

    load(data) {
      if (!Array.isArray(data)) return false;
      for (let i = 0; i < procs.length; i++) {
        const src = Array.isArray(data[i]) ? data[i] : [];
        const dst = procs[i].slots;
        for (let j = 0; j < dst.length; j++) {
          const token = typeof src[j] === 'string' ? src[j] : '';
          dst[j] = parseToken(token);
        }
      }
      history.length = 0;
      return true;
    },
  };

  return program;
}

/** 'RIGHT@r' -> { op: 'RIGHT', cond: 'r' }. Unknown tokens become empty slots. */
export function parseToken(token) {
  if (!token) return null;
  const at = token.indexOf('@');
  const op = at < 0 ? token : token.slice(0, at);
  if (!OPS[op]) return null;
  const cond = at < 0 ? null : token.slice(at + 1);
  return { op, cond: CONDS.indexOf(cond) >= 0 ? cond : null };
}
