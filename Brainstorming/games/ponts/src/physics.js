/**
 * PONTS DE FORTUNE - verlet solver with distance constraints.
 *
 * Pure JavaScript, no three.js: this module can be run head-less from node,
 * which is how the material capacities were tuned.
 *
 * Force measurement
 * -----------------
 * Position based dynamics has no explicit force, but the constraint impulse is
 * recoverable. When a constraint corrects node `a` by `da`, the force it had to
 * apply is `ma * da / dt^2`. Splitting a length error `e` between the two ends
 * by inverse mass gives `ma * da = e / (wa + wb)`, so accumulating
 * `e * stiff / (wa + wb)` over the relaxation passes and dividing by `dt^2`
 * yields the newtons flowing through the member. Positive is tension.
 *
 * That value is what breaks members, and what the stress colouring reads.
 */

import { SIM } from './config.js';

/**
 * @typedef {Object} SimNode
 * x,y,z current position; px,py,pz previous position (verlet velocity);
 * mass structural mass in kg; load extra kg resting on it this substep;
 * anchor true for cliff and pier attachments.
 */

export function createSim(options) {
  const opts = options || {};
  const gravity = opts.gravity !== undefined ? opts.gravity : SIM.gravity;
  const iterations = opts.iterations !== undefined ? opts.iterations : SIM.iterations;
  const damping = opts.damping !== undefined ? opts.damping : SIM.damping;

  const nodes = [];
  const links = [];
  /** Ruptures produced since the last drain, oldest first. */
  const breaks = [];

  let time = 0;
  let diverged = 0;

  function addNode(spec) {
    const n = {
      x: spec.x, y: spec.y, z: spec.z,
      px: spec.x, py: spec.y, pz: spec.z,
      sx: spec.x, sy: spec.y, sz: spec.z, // last known finite position
      mass: Math.max(SIM.minNodeMass, spec.mass || 0),
      load: 0,
      inv: 0,
      anchor: !!spec.anchor,
      owner: spec.owner !== undefined ? spec.owner : -1,
      side: spec.side !== undefined ? spec.side : 0,
      index: nodes.length,
    };
    nodes.push(n);
    return n.index;
  }

  function addLink(spec) {
    const a = nodes[spec.a];
    const b = nodes[spec.b];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dz = b.z - a.z;
    const rest = spec.rest !== undefined ? spec.rest : Math.sqrt(dx * dx + dy * dy + dz * dz);
    const l = {
      a: spec.a, b: spec.b,
      rest: Math.max(0.05, rest),
      stiff: spec.stiff,
      capT: spec.capT,
      capC: spec.capC,
      tensionOnly: !!spec.tensionOnly,
      broken: false,
      force: 0, // newtons, smoothed, + tension
      ratio: 0, // |force| / capacity in the working direction, 0..>1
      impulse: 0, // accumulator for the current substep
      owner: spec.owner !== undefined ? spec.owner : -1,
      kind: spec.kind || 'beam',
      side: spec.side !== undefined ? spec.side : 0,
      index: links.length,
    };
    links.push(l);
    return l.index;
  }

  /** Add mass carried by a vehicle. Cleared by every step. */
  function addLoad(nodeIndex, kilos) {
    const n = nodes[nodeIndex];
    if (n) n.load += kilos;
  }

  function breakLink(l, reason) {
    if (l.broken) return;
    l.broken = true;
    l.force = 0;
    l.ratio = 0;
    const a = nodes[l.a];
    const b = nodes[l.b];
    breaks.push({
      link: l.index,
      owner: l.owner,
      kind: l.kind,
      reason: reason,
      time: time,
      x: (a.x + b.x) * 0.5,
      y: (a.y + b.y) * 0.5,
      z: (a.z + b.z) * 0.5,
    });
  }

  /**
   * A node that went non finite would poison the whole structure. Restore it,
   * cut what it was holding and carry on rather than throwing.
   */
  function rescue(n) {
    diverged += 1;
    n.x = n.sx; n.y = n.sy; n.z = n.sz;
    n.px = n.sx; n.py = n.sy; n.pz = n.sz;
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      if (!l.broken && (l.a === n.index || l.b === n.index)) breakLink(l, 'diverge');
    }
  }

  const maxStep = SIM.maxNodeSpeed;

  function step(dt) {
    const gdt2 = gravity * dt * dt;
    const maxMove = maxStep * dt;

    // --- integrate ---------------------------------------------------------
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      n.inv = n.anchor ? 0 : 1 / (n.mass + n.load);
      if (n.anchor) {
        n.px = n.x; n.py = n.y; n.pz = n.z;
        continue;
      }
      let vx = (n.x - n.px) * damping;
      let vy = (n.y - n.py) * damping;
      let vz = (n.z - n.pz) * damping;
      const v2 = vx * vx + vy * vy + vz * vz;
      if (v2 > maxMove * maxMove) {
        const s = maxMove / Math.sqrt(v2);
        vx *= s; vy *= s; vz *= s;
      }
      n.px = n.x; n.py = n.y; n.pz = n.z;
      n.x += vx;
      n.y += vy - gdt2;
      n.z += vz;
    }

    // --- relax -------------------------------------------------------------
    for (let i = 0; i < links.length; i++) links[i].impulse = 0;

    for (let k = 0; k < iterations; k++) {
      for (let i = 0; i < links.length; i++) {
        const l = links[i];
        if (l.broken) continue;
        const a = nodes[l.a];
        const b = nodes[l.b];
        const w = a.inv + b.inv;
        if (w <= 0) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dz = b.z - a.z;
        let d = Math.sqrt(dx * dx + dy * dy + dz * dz);
        if (!(d > 1e-6)) continue;
        const err = d - l.rest;
        // A cable pushes nothing: shorter than rest means it simply hangs.
        if (l.tensionOnly && err <= 0) continue;
        const corr = (err * l.stiff) / d;
        const ka = a.inv / w;
        const kb = b.inv / w;
        a.x += dx * corr * ka;
        a.y += dy * corr * ka;
        a.z += dz * corr * ka;
        b.x -= dx * corr * kb;
        b.y -= dy * corr * kb;
        b.z -= dz * corr * kb;
        l.impulse += (err * l.stiff) / w;
      }
    }

    // --- measure and break --------------------------------------------------
    const invDt2 = 1 / (dt * dt);
    const smooth = SIM.forceSmooth;
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      if (l.broken) continue;
      const raw = l.impulse * invDt2;
      l.force += (raw - l.force) * smooth;
      const cap = l.force >= 0 ? l.capT : l.capC;
      if (cap <= 0) {
        l.ratio = 0;
      } else {
        l.ratio = Math.abs(l.force) / cap;
        if (l.ratio > 1) breakLink(l, l.force >= 0 ? 'traction' : 'compression');
      }
    }

    // --- divergence guard ---------------------------------------------------
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (Number.isFinite(n.x) && Number.isFinite(n.y) && Number.isFinite(n.z)
        && Math.abs(n.x) < 1e5 && Math.abs(n.y) < 1e5 && Math.abs(n.z) < 1e5) {
        n.sx = n.x; n.sy = n.y; n.sz = n.z;
      } else {
        rescue(n);
      }
      n.load = 0;
    }

    time += dt;
  }

  /** Highest stress ratio of any unbroken member, for the HUD gauge. */
  function peakRatio() {
    let m = 0;
    for (let i = 0; i < links.length; i++) {
      const l = links[i];
      if (!l.broken && l.ratio > m) m = l.ratio;
    }
    return m;
  }

  function drainBreaks(out) {
    out.length = 0;
    for (let i = 0; i < breaks.length; i++) out.push(breaks[i]);
    breaks.length = 0;
    return out;
  }

  return {
    nodes, links,
    get time() { return time; },
    get diverged() { return diverged; },
    addNode, addLink, addLoad, step, peakRatio, drainBreaks,
  };
}

/** Compression capacity falls off with length: a long strut buckles. */
export function bucklingFactor(length) {
  const r = SIM.bucklingRef / Math.max(SIM.bucklingRef, length);
  return Math.pow(r, SIM.bucklingPower);
}
