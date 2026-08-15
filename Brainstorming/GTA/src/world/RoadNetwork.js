/**
 * The road graph.
 *
 * A non-uniform grid: streets are dense downtown and stretch out towards the suburbs,
 * with every fourth line promoted to a wide avenue. The graph is the single source of
 * truth for road geometry, block subdivision, traffic routing, pedestrian spawning and
 * the minimap, so all of those stay consistent by construction.
 *
 * Node/edge ids are stable integers - traffic AI stores ids, not object references.
 */

import { Vector2 } from 'three/webgpu';
import { makeRng } from '../core/Noise.js';

/**
 * Width of the pavement slab on each side of a road, measured inward from the block edge.
 * Exported so `City` builds its kerbs to the same figure the lane maths assumes - if these
 * two drift apart, traffic drives on the footpath.
 */
export const PAVEMENT_WIDTH = 3.2;

export const ROAD = {
  STREET: { width: 13, lanes: 1, speed: 14 },
  AVENUE: { width: 21, lanes: 2, speed: 22 },
  HIGHWAY: { width: 26, lanes: 2, speed: 34 },
};

/** Street spacing grows with distance from downtown. */
function spacingAt(distance) {
  if (distance < 300) return 74;
  if (distance < 720) return 98;
  return 132;
}

function makeLines(extent) {
  const lines = [0];
  let p = 0;
  while (p < extent) { p += spacingAt(Math.abs(p)); lines.push(Math.round(p)); }
  p = 0;
  while (p > -extent) { p -= spacingAt(Math.abs(p)); lines.unshift(Math.round(p)); }
  return lines;
}

export class RoadNetwork {
  /**
   * @param {object} opts
   * @param {number} opts.extent half-size of the road grid in metres
   * @param {(x:number,z:number)=>boolean} [opts.isLand] excludes nodes over water
   * @param {number} [opts.seed]
   */
  constructor({ extent = 1200, isLand = () => true, seed = 1337 } = {}) {
    this.extent = extent;
    this.isLand = isLand;
    this.rng = makeRng(seed);

    this.xLines = makeLines(extent);
    this.zLines = makeLines(extent);

    /** @type {Array<{id:number,x:number,z:number,ix:number,iz:number,edges:number[]}>} */
    this.nodes = [];
    /** @type {Array<{id:number,a:number,b:number,type:object,axis:'x'|'z',length:number,dirX:number,dirZ:number}>} */
    this.edges = [];
    /** @type {Array<{x0:number,z0:number,x1:number,z1:number,cx:number,cz:number,w:number,d:number}>} */
    this.blocks = [];

    this._nodeGrid = new Map(); // "ix,iz" -> node id
    this._build();
  }

  _key(ix, iz) { return `${ix},${iz}`; }

  /** True when a grid line index is a wide avenue. */
  isAvenueLine(i, lines) {
    // Anchor the pattern on the line nearest x=0 so avenues stay symmetric.
    const zeroIndex = lines.indexOf(0);
    return Math.abs(i - (zeroIndex < 0 ? 0 : zeroIndex)) % 4 === 0;
  }

  _build() {
    // Nodes.
    for (let iz = 0; iz < this.zLines.length; iz++) {
      for (let ix = 0; ix < this.xLines.length; ix++) {
        const x = this.xLines[ix], z = this.zLines[iz];
        if (!this.isLand(x, z)) continue;
        const id = this.nodes.length;
        this.nodes.push({ id, x, z, ix, iz, edges: [] });
        this._nodeGrid.set(this._key(ix, iz), id);
      }
    }

    // Edges between orthogonally adjacent nodes.
    const connect = (aId, bId, axis, lineIndex, lines) => {
      const a = this.nodes[aId], b = this.nodes[bId];
      const dx = b.x - a.x, dz = b.z - a.z;
      const length = Math.hypot(dx, dz);
      // The road type comes from the line the edge runs *along*.
      const type = this.isAvenueLine(lineIndex, lines) ? ROAD.AVENUE : ROAD.STREET;
      const id = this.edges.length;
      this.edges.push({
        id, a: aId, b: bId, type, axis, length,
        dirX: dx / length, dirZ: dz / length,
      });
      a.edges.push(id);
      b.edges.push(id);
    };

    for (let iz = 0; iz < this.zLines.length; iz++) {
      for (let ix = 0; ix < this.xLines.length; ix++) {
        const here = this._nodeGrid.get(this._key(ix, iz));
        if (here === undefined) continue;
        const east = this._nodeGrid.get(this._key(ix + 1, iz));
        if (east !== undefined) connect(here, east, 'x', iz, this.zLines);
        const south = this._nodeGrid.get(this._key(ix, iz + 1));
        if (south !== undefined) connect(here, south, 'z', ix, this.xLines);
      }
    }

    // Blocks: the land rectangles between four adjacent intersections, shrunk by the
    // half-widths of the bounding roads.
    for (let iz = 0; iz < this.zLines.length - 1; iz++) {
      for (let ix = 0; ix < this.xLines.length - 1; ix++) {
        const corners = [
          this._nodeGrid.get(this._key(ix, iz)),
          this._nodeGrid.get(this._key(ix + 1, iz)),
          this._nodeGrid.get(this._key(ix, iz + 1)),
          this._nodeGrid.get(this._key(ix + 1, iz + 1)),
        ];
        if (corners.some((c) => c === undefined)) continue;

        const wWest = (this.isAvenueLine(ix, this.xLines) ? ROAD.AVENUE : ROAD.STREET).width / 2;
        const wEast = (this.isAvenueLine(ix + 1, this.xLines) ? ROAD.AVENUE : ROAD.STREET).width / 2;
        const wNorth = (this.isAvenueLine(iz, this.zLines) ? ROAD.AVENUE : ROAD.STREET).width / 2;
        const wSouth = (this.isAvenueLine(iz + 1, this.zLines) ? ROAD.AVENUE : ROAD.STREET).width / 2;

        const x0 = this.xLines[ix] + wWest, x1 = this.xLines[ix + 1] - wEast;
        const z0 = this.zLines[iz] + wNorth, z1 = this.zLines[iz + 1] - wSouth;
        if (x1 - x0 < 12 || z1 - z0 < 12) continue;

        this.blocks.push({
          x0, z0, x1, z1,
          cx: (x0 + x1) / 2, cz: (z0 + z1) / 2,
          w: x1 - x0, d: z1 - z0,
        });
      }
    }
  }

  nodeAt(ix, iz) {
    const id = this._nodeGrid.get(this._key(ix, iz));
    return id === undefined ? null : this.nodes[id];
  }

  edgeById(id) { return this.edges[id]; }

  /** The other end of `edge` from `nodeId`. */
  otherEnd(edge, nodeId) { return edge.a === nodeId ? edge.b : edge.a; }

  /**
   * Lane centre offset from the road centreline, in metres, positive to the right of
   * travel direction.
   *
   * Measured against the *drivable* width, not the full road width. The pavement slab
   * runs inward from the block edge and eats `PAVEMENT_WIDTH` off each side, so a road
   * that is 13 m between kerb lines only has 3.3 m of carriageway either side of the
   * centreline. Offsetting by half the full width put cars permanently half on the
   * pavement, where they ground against kerbs, lamp posts and bins - which presented as
   * traffic mysteriously stalling at full throttle with nothing in front of it.
   */
  laneOffset(type, lane = 0) {
    const drivable = Math.max(2.4, type.width / 2 - PAVEMENT_WIDTH);
    const lanes = Math.max(1, type.lanes);
    const laneWidth = drivable / lanes;
    return laneWidth * (lane + 0.5);
  }

  /** Nearest node to a world position. Linear scan is fine for <2k nodes. */
  nearestNode(x, z) {
    let best = null, bestD = Infinity;
    for (const n of this.nodes) {
      const d = (n.x - x) ** 2 + (n.z - z) ** 2;
      if (d < bestD) { bestD = d; best = n; }
    }
    return best;
  }

  /**
   * Nearest point on the road network to a world position.
   * @returns {{edge:object, t:number, x:number, z:number, distance:number}|null}
   */
  nearestOnRoad(x, z) {
    let best = null, bestD = Infinity;
    for (const e of this.edges) {
      const a = this.nodes[e.a], b = this.nodes[e.b];
      const vx = b.x - a.x, vz = b.z - a.z;
      const len2 = vx * vx + vz * vz;
      let t = ((x - a.x) * vx + (z - a.z) * vz) / len2;
      t = t < 0 ? 0 : t > 1 ? 1 : t;
      const px = a.x + vx * t, pz = a.z + vz * t;
      const d = (px - x) ** 2 + (pz - z) ** 2;
      if (d < bestD) { bestD = d; best = { edge: e, t, x: px, z: pz, distance: Math.sqrt(d) }; }
    }
    return best;
  }

  /** Random position in a driving lane, plus the heading to face. */
  randomLanePoint() {
    const e = this.edges[Math.floor(this.rng() * this.edges.length)];
    const forward = this.rng() < 0.5;
    return this.lanePointOnEdge(e, this.rng(), forward, 0);
  }

  /**
   * Point in a lane along an edge.
   * @param {object} e edge
   * @param {number} t 0..1 along the edge
   * @param {boolean} forward travelling a->b when true
   * @param {number} lane 0 = innermost
   */
  lanePointOnEdge(e, t, forward, lane = 0) {
    const a = this.nodes[e.a], b = this.nodes[e.b];
    const from = forward ? a : b, to = forward ? b : a;
    const dx = to.x - from.x, dz = to.z - from.z;
    const len = Math.hypot(dx, dz);
    const ux = dx / len, uz = dz / len;
    // Right-hand side of travel in a Y-up, right-handed system.
    const rx = -uz, rz = ux;
    const off = this.laneOffset(e.type, lane);
    return {
      x: from.x + dx * t + rx * off,
      z: from.z + dz * t + rz * off,
      heading: Math.atan2(ux, uz),
      dirX: ux, dirZ: uz,
      edge: e, forward, lane,
    };
  }

  /** Continuations from `node` arriving via `fromEdgeId`, excluding a U-turn. */
  exitsFrom(nodeId, fromEdgeId) {
    const node = this.nodes[nodeId];
    const out = [];
    for (const eid of node.edges) {
      if (eid === fromEdgeId) continue;
      out.push(eid);
    }
    return out.length ? out : node.edges.slice();
  }

  /** A* shortest path between two node ids, returned as a node id array. */
  findPath(startId, goalId) {
    if (startId === goalId) return [startId];
    const goal = this.nodes[goalId];
    const h = (n) => Math.hypot(n.x - goal.x, n.z - goal.z);
    const open = [startId];
    const cameFrom = new Map();
    const g = new Map([[startId, 0]]);
    const f = new Map([[startId, h(this.nodes[startId])]]);
    const closed = new Set();

    while (open.length) {
      open.sort((p, q) => (f.get(p) ?? Infinity) - (f.get(q) ?? Infinity));
      const current = open.shift();
      if (current === goalId) {
        const path = [current];
        let c = current;
        while (cameFrom.has(c)) { c = cameFrom.get(c); path.unshift(c); }
        return path;
      }
      closed.add(current);
      for (const eid of this.nodes[current].edges) {
        const e = this.edges[eid];
        const next = this.otherEnd(e, current);
        if (closed.has(next)) continue;
        const tentative = (g.get(current) ?? Infinity) + e.length;
        if (tentative < (g.get(next) ?? Infinity)) {
          cameFrom.set(next, current);
          g.set(next, tentative);
          f.set(next, tentative + h(this.nodes[next]));
          if (!open.includes(next)) open.push(next);
        }
      }
    }
    return null;
  }

  /** Bounding box of the whole network. */
  get bounds() {
    return {
      minX: this.xLines[0], maxX: this.xLines[this.xLines.length - 1],
      minZ: this.zLines[0], maxZ: this.zLines[this.zLines.length - 1],
    };
  }
}

export const _v2 = new Vector2();
