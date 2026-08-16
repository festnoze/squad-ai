/**
 * PONTS DE FORTUNE - the bridge model.
 *
 * The player edits a flat plan: joints on a grid, members between them. This
 * module owns that plan, its cost, its legality rules and its unlimited undo.
 * It also knows how to inflate the plan into a three dimensional structure for
 * the solver: every drawn member becomes two parallel members (one per truss)
 * plus cross bracing, which is what gives the bridge a real width and lets it
 * fail sideways instead of staying a flat cartoon.
 *
 * No three.js here on purpose: the model is testable from node.
 */

import { MATERIALS, HALF_WIDTH, BRACE } from './config.js';
import { createSim, bucklingFactor } from './physics.js';
import { colToX, rowToY, canPlaceNode, anchorPoints } from './levels.js';

const TYPE_ORDER = ['wood', 'steel', 'cable', 'road'];

function keyOf(col, row) {
  return col + ':' + row;
}

export function createBridge(level) {
  /** @type {Array<{a:string,b:string,ca:number,ra:number,cb:number,rb:number,type:string,len:number,cost:number}>} */
  let elements = [];
  /** @type {Array<{col:number,row:number,anchor:boolean,x:number,y:number,key:string}>} */
  let nodes = [];
  let nodeIndex = new Map();
  let spent = 0;
  const history = [];

  const anchors = anchorPoints(level);
  const anchorSet = new Set(anchors.map((a) => keyOf(a[0], a[1])));

  function lengthOf(ca, ra, cb, rb) {
    const dx = colToX(level, cb) - colToX(level, ca);
    const dy = rowToY(rb) - rowToY(ra);
    return Math.sqrt(dx * dx + dy * dy);
  }

  function costOf(type, len) {
    return Math.max(1, Math.round(len * MATERIALS[type].cost));
  }

  function rebuild() {
    nodes = [];
    nodeIndex = new Map();
    spent = 0;
    for (let i = 0; i < anchors.length; i++) touch(anchors[i][0], anchors[i][1]);
    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      touch(e.ca, e.ra);
      touch(e.cb, e.rb);
      spent += e.cost;
    }
  }

  function touch(col, row) {
    const k = keyOf(col, row);
    let idx = nodeIndex.get(k);
    if (idx !== undefined) return idx;
    idx = nodes.length;
    nodes.push({
      col, row, key: k,
      anchor: anchorSet.has(k),
      x: colToX(level, col),
      y: rowToY(row),
    });
    nodeIndex.set(k, idx);
    return idx;
  }

  function findElement(ca, ra, cb, rb) {
    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      if ((e.ca === ca && e.ra === ra && e.cb === cb && e.rb === rb)
        || (e.ca === cb && e.ra === rb && e.cb === ca && e.rb === ra)) return i;
    }
    return -1;
  }

  /**
   * Legality of a member the player is about to draw.
   * Always returns a reason string in French: the HUD shows it as is.
   */
  function evaluate(ca, ra, cb, rb, type) {
    const mat = MATERIALS[type];
    const res = { ok: false, reason: '', len: 0, cost: 0 };
    if (!mat) { res.reason = 'materiau inconnu'; return res; }
    if (level.allow.indexOf(type) < 0) { res.reason = 'materiau indisponible sur ce chantier'; return res; }
    if (ca === cb && ra === rb) { res.reason = 'meme point'; return res; }
    if (!canPlaceNode(level, ca, ra) || !canPlaceNode(level, cb, rb)) {
      res.reason = level.ceilRow !== null && (ra > level.ceilRow || rb > level.ceilRow)
        ? 'interdit au dessus du plafond'
        : 'hors de la zone constructible';
      return res;
    }
    const len = lengthOf(ca, ra, cb, rb);
    res.len = len;
    res.cost = costOf(type, len);
    if (len > mat.maxLen + 1e-6) { res.reason = 'trop long pour ce materiau'; return res; }
    if (mat.horizontalOnly) {
      if (ra !== 0 || rb !== 0) { res.reason = 'la route se pose au niveau du tablier'; return res; }
      if (Math.abs(ca - cb) !== 1) { res.reason = 'la route relie deux cases voisines'; return res; }
    }
    if (findElement(ca, ra, cb, rb) >= 0) { res.reason = 'deja construit ici'; return res; }
    if (res.cost > budgetLeft()) { res.reason = 'budget insuffisant'; return res; }
    res.ok = true;
    return res;
  }

  function budgetLeft() {
    return level.budget - spent;
  }

  function snapshot() {
    const out = new Array(elements.length);
    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      out[i] = [e.ca, e.ra, e.cb, e.rb, TYPE_ORDER.indexOf(e.type)];
    }
    return out;
  }

  function restore(data) {
    elements = [];
    for (let i = 0; i < data.length; i++) {
      const d = data[i];
      const type = TYPE_ORDER[d[4]];
      if (!type) continue;
      const len = lengthOf(d[0], d[1], d[2], d[3]);
      elements.push({
        ca: d[0], ra: d[1], cb: d[2], rb: d[3], type, len, cost: costOf(type, len),
      });
    }
    rebuild();
  }

  function pushHistory() {
    history.push(snapshot());
    if (history.length > 4000) history.shift();
  }

  function add(ca, ra, cb, rb, type) {
    const check = evaluate(ca, ra, cb, rb, type);
    if (!check.ok) return check;
    pushHistory();
    elements.push({ ca, ra, cb, rb, type, len: check.len, cost: check.cost });
    rebuild();
    return check;
  }

  function removeAt(index) {
    if (index < 0 || index >= elements.length) return null;
    pushHistory();
    const e = elements[index];
    elements.splice(index, 1);
    rebuild();
    return e;
  }

  function undo() {
    if (!history.length) return false;
    restore(history.pop());
    return true;
  }

  function clear() {
    if (!elements.length) return false;
    pushHistory();
    elements = [];
    rebuild();
    return true;
  }

  function load(data) {
    if (!Array.isArray(data)) return false;
    history.length = 0;
    restore(data);
    return true;
  }

  /** Deck completeness: the convoy needs every roadway cell from left to right. */
  function deckGaps() {
    const missing = [];
    for (let c = level.left; c < level.right; c++) {
      if (findElement(c, 0, c + 1, 0) < 0) missing.push(c);
    }
    return missing;
  }

  /**
   * Inflate the plan into a solver instance.
   * Returns the sim plus the lookup tables the renderer and the convoy need.
   */
  function buildSim() {
    const sim = createSim({});
    const mass = new Float64Array(nodes.length);

    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      const m = MATERIALS[e.type].density * e.len * 0.5; // per truss, split on both ends
      mass[nodeIndex.get(keyOf(e.ca, e.ra))] += m * 0.5;
      mass[nodeIndex.get(keyOf(e.cb, e.rb))] += m * 0.5;
    }

    // Two physics nodes per plan joint, one per truss.
    const pair = new Int32Array(nodes.length * 2);
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      pair[i * 2] = sim.addNode({
        x: n.x, y: n.y, z: -HALF_WIDTH, mass: mass[i], anchor: n.anchor, owner: i, side: 0,
      });
      pair[i * 2 + 1] = sim.addNode({
        x: n.x, y: n.y, z: HALF_WIDTH, mass: mass[i], anchor: n.anchor, owner: i, side: 1,
      });
    }

    const elemLinks = new Array(elements.length);
    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      const mat = MATERIALS[e.type];
      const ia = nodeIndex.get(keyOf(e.ca, e.ra));
      const ib = nodeIndex.get(keyOf(e.cb, e.rb));
      const capC = mat.capC * bucklingFactor(e.len);
      const common = {
        stiff: mat.stiff, capT: mat.capT, capC, tensionOnly: !!mat.tensionOnly,
        owner: i, kind: e.type,
      };
      const l0 = sim.addLink(Object.assign({ a: pair[ia * 2], b: pair[ib * 2], side: 0 }, common));
      const l1 = sim.addLink(Object.assign({ a: pair[ia * 2 + 1], b: pair[ib * 2 + 1], side: 1 }, common));
      elemLinks[i] = [l0, l1];

      // Shear bracing between the two trusses. Free, unbreakable in practice,
      // and the only reason the deck does not fold like paper sideways.
      const brace = {
        stiff: BRACE.stiff, capT: BRACE.capT, capC: BRACE.capC, owner: i, kind: 'brace',
      };
      sim.addLink(Object.assign({ a: pair[ia * 2], b: pair[ib * 2 + 1], side: 2 }, brace));
      sim.addLink(Object.assign({ a: pair[ia * 2 + 1], b: pair[ib * 2], side: 3 }, brace));
    }

    // Cross members holding the two trusses apart at every joint.
    const traverses = [];
    for (let i = 0; i < nodes.length; i++) {
      traverses.push(sim.addLink({
        a: pair[i * 2], b: pair[i * 2 + 1], rest: HALF_WIDTH * 2,
        stiff: BRACE.stiff, capT: BRACE.capT, capC: BRACE.capC, owner: i, kind: 'traverse', side: 4,
      }));
    }

    // Roadway cells, sorted left to right, with the physics nodes under them.
    const deck = [];
    for (let i = 0; i < elements.length; i++) {
      const e = elements[i];
      if (e.type !== 'road') continue;
      const lo = Math.min(e.ca, e.cb);
      const hi = Math.max(e.ca, e.cb);
      const iLo = nodeIndex.get(keyOf(lo, 0));
      const iHi = nodeIndex.get(keyOf(hi, 0));
      deck.push({
        element: i, col: lo,
        n0: [pair[iLo * 2], pair[iLo * 2 + 1]],
        n1: [pair[iHi * 2], pair[iHi * 2 + 1]],
        links: elemLinks[i],
      });
    }
    deck.sort((a, b) => a.col - b.col);

    return { sim, pair, elemLinks, traverses, deck, nodeCount: nodes.length };
  }

  rebuild();

  return {
    level,
    get elements() { return elements; },
    get nodes() { return nodes; },
    get spent() { return spent; },
    get budgetLeft() { return budgetLeft(); },
    get historyDepth() { return history.length; },
    nodeIndexOf(col, row) {
      const i = nodeIndex.get(keyOf(col, row));
      return i === undefined ? -1 : i;
    },
    isAnchor(col, row) { return anchorSet.has(keyOf(col, row)); },
    anchors,
    evaluate, add, removeAt, findElement, undo, clear, load, snapshot,
    deckGaps, buildSim, costOf, lengthOf,
  };
}
