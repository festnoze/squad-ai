/**
 * AIGUILLAGE - the rail graph: nodes, segments, switches, crossings.
 *
 * Deliberately dependency free (no `three`): trains.js is a pure simulation
 * and must never import three, so the graph it walks cannot either. Segment
 * length is estimated here with a small local Catmull-Rom sampler that
 * mirrors the real one in spline.js (which does the same work with
 * THREE.Vector3 for the renderer) - a little duplication, bought on purpose
 * so both the simulation and the renderer stay independently correct.
 *
 * Train position is `(segmentId, dir, sAbs)`:
 *   dir   = +1 travelling from segment.a to segment.b, -1 the other way
 *   sAbs  = absolute progress from node `a`, in [0, segment.length]
 * A transition (`resolveArrival`) always returns the *new* dir/sAbs pair so
 * the caller never has to reason about which end is which.
 */

// Catmull-Rom (uniform, tension 0.5) evaluated in plain numbers, matching
// THREE.CatmullRomCurve3's default 'catmullrom' type closely enough for a
// length estimate (this is not used for rendering, only for gameplay pacing).
function catmullPoint(p0, p1, p2, p3, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    0.5 *
    ((2 * p1) +
      (-p0 + p2) * t +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
      (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
  );
}

function estimateLength(points) {
  const n = points.length;
  if (n < 2) return 0;
  const SAMPLES_PER_SEG = 24;
  let length = 0;
  let prevX = points[0].x;
  let prevZ = points[0].z;
  for (let i = 0; i < n - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(n - 1, i + 2)];
    for (let s = 1; s <= SAMPLES_PER_SEG; s++) {
      const t = s / SAMPLES_PER_SEG;
      const x = catmullPoint(p0.x, p1.x, p2.x, p3.x, t);
      const z = catmullPoint(p0.z, p1.z, p2.z, p3.z, t);
      length += Math.hypot(x - prevX, z - prevZ);
      prevX = x;
      prevZ = z;
    }
  }
  return length;
}

export function createNetwork(levelDef) {
  const nodes = new Map();
  for (const n of levelDef.nodes) {
    nodes.set(n.id, { id: n.id, kind: n.kind, x: n.x, z: n.z, color: n.color || null });
  }

  const segments = new Map();
  for (const s of levelDef.segments) {
    const length = estimateLength(s.points);
    let crossing = null;
    if (s.crossing) {
      crossing = {
        sAt: s.crossing.at * length,
        offset: s.crossing.offset,
        closedFor: s.crossing.closedFor,
        period: s.crossing.period,
      };
    }
    segments.set(s.id, { id: s.id, a: s.a, b: s.b, points: s.points, length, crossing });
  }

  const switches = new Map();
  const switchByNode = new Map();
  for (const w of levelDef.switches) {
    const rec = {
      id: w.id,
      nodeId: w.nodeId,
      trunk: w.trunk,
      branches: [w.branchA, w.branchB],
      state: w.initialState || 0,
    };
    switches.set(w.id, rec);
    switchByNode.set(w.nodeId, rec);
  }

  function otherEnd(seg, nodeId) {
    return seg.a === nodeId ? seg.b : seg.a;
  }

  /** Which of the two branch slots (0/1) this segment id occupies at its switch, or -1. */
  function branchIndexOf(sw, segmentId) {
    if (sw.branches[0] === segmentId) return 0;
    if (sw.branches[1] === segmentId) return 1;
    return -1;
  }

  const network = {
    nodes,
    segments,
    switches,

    toggleSwitch(switchId) {
      const sw = switches.get(switchId);
      if (!sw) return;
      sw.state = sw.state === 0 ? 1 : 0;
    },

    setSwitchState(switchId, state) {
      const sw = switches.get(switchId);
      if (!sw) return;
      sw.state = state ? 1 : 0;
    },

    switchState(switchId) {
      const sw = switches.get(switchId);
      return sw ? sw.state : 0;
    },

    isCrossingClosed(segmentId, simTime) {
      const seg = segments.get(segmentId);
      if (!seg || !seg.crossing) return false;
      const c = seg.crossing;
      if (simTime < c.offset) return false;
      const phase = (simTime - c.offset) % c.period;
      return phase < c.closedFor;
    },

    /** Seconds until the crossing (if any) flips open/closed, or null. */
    crossingChangesIn(segmentId, simTime) {
      const seg = segments.get(segmentId);
      if (!seg || !seg.crossing) return null;
      const c = seg.crossing;
      if (simTime < c.offset) return c.offset - simTime;
      const phase = (simTime - c.offset) % c.period;
      return phase < c.closedFor ? c.closedFor - phase : c.period - phase;
    },

    /**
     * Called when a train's front reaches the far end of `segmentId` while
     * travelling in direction `dir` (+1 -> node b, -1 -> node a).
     * Returns one of:
     *   { kind:'exit', color }
     *   { kind:'siding' }
     *   { kind:'through', segmentId, dir, sAbs }
     *   { kind:'blocked' }   the arriving switch branch is not the live one
     */
    resolveArrival(segmentId, dir) {
      const seg = segments.get(segmentId);
      const nodeId = dir === 1 ? seg.b : seg.a;
      const node = nodes.get(nodeId);
      if (node.kind === 'exit') return { kind: 'exit', color: node.color };
      if (node.kind === 'siding') return { kind: 'siding' };
      if (node.kind === 'switch') {
        const sw = switchByNode.get(nodeId);
        let nextSegId = null;
        if (sw.trunk === segmentId) {
          nextSegId = sw.branches[sw.state];
        } else {
          const bi = branchIndexOf(sw, segmentId);
          if (bi === -1 || bi !== sw.state) return { kind: 'blocked' };
          nextSegId = sw.trunk;
        }
        const nextSeg = segments.get(nextSegId);
        const nextDir = nextSeg.a === nodeId ? 1 : -1;
        const nextSAbs = nextDir === 1 ? 0 : nextSeg.length;
        return { kind: 'through', segmentId: nextSegId, dir: nextDir, sAbs: nextSAbs };
      }
      // A spawn node should never be reached in valid level data; treat it as
      // a dead stop rather than crashing the simulation.
      return { kind: 'siding' };
    },

    /** True while the arrival at the far end of segmentId/dir would proceed (not queue). */
    canProceed(segmentId, dir) {
      const res = this.resolveArrival(segmentId, dir);
      return res.kind !== 'blocked';
    },

    otherEnd(segmentId, nodeId) {
      return otherEnd(segments.get(segmentId), nodeId);
    },

    dispose() {
      // Pure data, nothing to release.
    },
  };

  return network;
}
