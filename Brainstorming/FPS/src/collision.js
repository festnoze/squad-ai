import * as THREE from 'three';

/**
 * Axis-aligned collision world.
 * Every solid thing in the city registers one box here. Movement is resolved
 * axis by axis so the player and the ghouls slide along walls instead of
 * sticking to them, and rays reuse the same boxes for line of sight and bullets.
 */
export class Colliders {
  constructor(cellSize = 8) {
    this.cellSize = cellSize;
    this.boxes = [];
    this.grid = new Map();
    this._stamp = 0;
    this._marks = [];
  }

  clear() {
    this.boxes.length = 0;
    this.grid.clear();
    this._marks.length = 0;
    this._stamp = 0;
  }

  _key(ix, iz) {
    return ix * 73856093 ^ iz * 19349663;
  }

  /** min/max are THREE.Vector3. meta can carry { tag } for gameplay filtering. */
  add(min, max, meta = {}) {
    const box = {
      min: min.clone(),
      max: max.clone(),
      tag: meta.tag ?? 'world',
      index: this.boxes.length,
    };
    this.boxes.push(box);
    this._marks.push(0);

    const cs = this.cellSize;
    const ix0 = Math.floor(min.x / cs);
    const ix1 = Math.floor(max.x / cs);
    const iz0 = Math.floor(min.z / cs);
    const iz1 = Math.floor(max.z / cs);
    for (let ix = ix0; ix <= ix1; ix++) {
      for (let iz = iz0; iz <= iz1; iz++) {
        const k = this._key(ix, iz);
        let bucket = this.grid.get(k);
        if (!bucket) {
          bucket = [];
          this.grid.set(k, bucket);
        }
        bucket.push(box.index);
      }
    }
    return box;
  }

  /** Convenience: register a box from a centre point and half extents. */
  addBox(center, half, meta) {
    return this.add(
      new THREE.Vector3(center.x - half.x, center.y - half.y, center.z - half.z),
      new THREE.Vector3(center.x + half.x, center.y + half.y, center.z + half.z),
      meta
    );
  }

  /** All boxes overlapping the given AABB, written into `out`. */
  query(minX, minY, minZ, maxX, maxY, maxZ, out) {
    out.length = 0;
    const cs = this.cellSize;
    const stamp = ++this._stamp;
    const ix0 = Math.floor(minX / cs);
    const ix1 = Math.floor(maxX / cs);
    const iz0 = Math.floor(minZ / cs);
    const iz1 = Math.floor(maxZ / cs);
    for (let ix = ix0; ix <= ix1; ix++) {
      for (let iz = iz0; iz <= iz1; iz++) {
        const bucket = this.grid.get(this._key(ix, iz));
        if (!bucket) continue;
        for (let i = 0; i < bucket.length; i++) {
          const idx = bucket[i];
          if (this._marks[idx] === stamp) continue;
          this._marks[idx] = stamp;
          const b = this.boxes[idx];
          // Strict overlap: surfaces that merely touch (the street plane under
          // the player's feet, for instance) must not count as a collision,
          // otherwise they get resolved as walls.
          if (b.max.y <= minY + EPS || b.min.y >= maxY - EPS) continue;
          if (b.max.x <= minX + EPS || b.min.x >= maxX - EPS) continue;
          if (b.max.z <= minZ + EPS || b.min.z >= maxZ - EPS) continue;
          out.push(b);
        }
      }
    }
    return out;
  }

  /** True when the AABB overlaps any solid. */
  overlaps(cx, cy, cz, hx, hy, hz) {
    const found = _scratchList;
    this.query(cx - hx, cy - hy, cz - hz, cx + hx, cy + hy, cz + hz, found);
    return found.length > 0;
  }

  /**
   * Closest ray/box hit. Returns null or { distance, point, normal, box }.
   * Brute force over every box: the city is a few hundred boxes and this is
   * only called for shots and periodic line-of-sight checks.
   */
  raycast(origin, dir, maxDist = 1000, filter = null) {
    let best = null;
    let bestT = maxDist;
    const invx = 1 / (dir.x || 1e-9);
    const invy = 1 / (dir.y || 1e-9);
    const invz = 1 / (dir.z || 1e-9);
    for (let i = 0; i < this.boxes.length; i++) {
      const b = this.boxes[i];
      if (filter && !filter(b)) continue;
      let t1 = (b.min.x - origin.x) * invx;
      let t2 = (b.max.x - origin.x) * invx;
      let tmin = Math.min(t1, t2);
      let tmax = Math.max(t1, t2);
      t1 = (b.min.y - origin.y) * invy;
      t2 = (b.max.y - origin.y) * invy;
      tmin = Math.max(tmin, Math.min(t1, t2));
      tmax = Math.min(tmax, Math.max(t1, t2));
      t1 = (b.min.z - origin.z) * invz;
      t2 = (b.max.z - origin.z) * invz;
      tmin = Math.max(tmin, Math.min(t1, t2));
      tmax = Math.min(tmax, Math.max(t1, t2));
      if (tmax < 0 || tmin > tmax || tmin > bestT) continue;
      const t = tmin < 0 ? 0 : tmin;
      if (t < bestT) {
        bestT = t;
        best = b;
      }
    }
    if (!best) return null;
    const point = new THREE.Vector3(
      origin.x + dir.x * bestT,
      origin.y + dir.y * bestT,
      origin.z + dir.z * bestT
    );
    return { distance: bestT, point, normal: boxNormalAt(best, point), box: best };
  }

  /** Unobstructed straight line between two points? */
  lineOfSight(from, to) {
    const dir = _v1.copy(to).sub(from);
    const dist = dir.length();
    if (dist < 0.001) return true;
    dir.multiplyScalar(1 / dist);
    const hit = this.raycast(from, dir, dist - 0.05);
    return hit === null;
  }
}

const EPS = 1e-4;
const _scratchList = [];
const _v1 = new THREE.Vector3();

/** Outward face normal of `box` at a point known to be on its surface. */
export function boxNormalAt(box, point) {
  const cx = (box.min.x + box.max.x) * 0.5;
  const cy = (box.min.y + box.max.y) * 0.5;
  const cz = (box.min.z + box.max.z) * 0.5;
  const dx = (point.x - cx) / Math.max(1e-6, box.max.x - cx);
  const dy = (point.y - cy) / Math.max(1e-6, box.max.y - cy);
  const dz = (point.z - cz) / Math.max(1e-6, box.max.z - cz);
  const ax = Math.abs(dx);
  const ay = Math.abs(dy);
  const az = Math.abs(dz);
  if (ax >= ay && ax >= az) return new THREE.Vector3(Math.sign(dx), 0, 0);
  if (ay >= az) return new THREE.Vector3(0, Math.sign(dy), 0);
  return new THREE.Vector3(0, 0, Math.sign(dz));
}

/** Ray against a single AABB given as {min,max}. Returns entry distance or -1. */
export function rayBox(origin, dir, min, max, maxDist) {
  const invx = 1 / (dir.x || 1e-9);
  const invy = 1 / (dir.y || 1e-9);
  const invz = 1 / (dir.z || 1e-9);
  let t1 = (min.x - origin.x) * invx;
  let t2 = (max.x - origin.x) * invx;
  let tmin = Math.min(t1, t2);
  let tmax = Math.max(t1, t2);
  t1 = (min.y - origin.y) * invy;
  t2 = (max.y - origin.y) * invy;
  tmin = Math.max(tmin, Math.min(t1, t2));
  tmax = Math.min(tmax, Math.max(t1, t2));
  t1 = (min.z - origin.z) * invz;
  t2 = (max.z - origin.z) * invz;
  tmin = Math.max(tmin, Math.min(t1, t2));
  tmax = Math.min(tmax, Math.max(t1, t2));
  if (tmax < 0 || tmin > tmax) return -1;
  const t = tmin < 0 ? 0 : tmin;
  return t > maxDist ? -1 : t;
}

const _cand = [];

/**
 * Slide an AABB (centre + half extents) through the world by `delta`.
 * Resolves one axis at a time and allows stepping over knee-high rubble.
 * Mutates `center`; returns { grounded, hitWall, hitCeiling }.
 */
export function moveAABB(colliders, center, half, delta, stepHeight = 0.5) {
  const result = { grounded: false, hitWall: false, hitCeiling: false };
  const hx = half.x, hy = half.y, hz = half.z;

  const queryHere = () => colliders.query(
    center.x - hx, center.y - hy, center.z - hz,
    center.x + hx, center.y + hy, center.z + hz, _cand
  );

  // --- vertical ---
  if (delta.y !== 0) {
    center.y += delta.y;
    queryHere();
    // Apply only the deepest penetration, never the sum of several boxes.
    let push = 0;
    for (let i = 0; i < _cand.length; i++) {
      const b = _cand[i];
      const p = delta.y < 0 ? b.max.y - (center.y - hy) : (center.y + hy) - b.min.y;
      if (p > push) push = p;
    }
    if (push > 0) {
      const limit = Math.abs(delta.y) + stepHeight + 0.05;
      const applied = Math.min(push, limit);
      if (delta.y < 0) {
        center.y += applied;
        result.grounded = true;
      } else {
        center.y -= applied;
        result.hitCeiling = true;
      }
    }
  }

  // --- horizontal, one axis at a time, with a step-up retry ---
  resolveAxis('x', delta.x);
  resolveAxis('z', delta.z);

  function resolveAxis(axis, amount) {
    if (amount === 0) return;
    center[axis] += amount;
    queryHere();
    if (_cand.length === 0) return;

    // Low enough to just walk up onto? (kerbs, rubble, sandbags, car bumpers)
    let highest = -Infinity;
    for (let i = 0; i < _cand.length; i++) {
      if (_cand[i].max.y > highest) highest = _cand[i].max.y;
    }
    const rise = highest - (center.y - hy);
    if (rise > 0.01 && rise <= stepHeight) {
      const savedY = center.y;
      center.y += rise + 0.02;
      queryHere();
      if (_cand.length === 0) {
        result.grounded = true;
        return;
      }
      center.y = savedY;
      queryHere();
    }

    // Otherwise slide: back out by the deepest penetration on this axis only.
    const halfA = axis === 'x' ? hx : hz;
    let push = 0;
    for (let i = 0; i < _cand.length; i++) {
      const b = _cand[i];
      const p = amount > 0
        ? (center[axis] + halfA) - b.min[axis]
        : b.max[axis] - (center[axis] - halfA);
      if (p > push) push = p;
    }
    if (push > 0) {
      // A step can only ever penetrate as deep as the step itself. Clamping
      // keeps a body that starts inside geometry from being flung across the
      // map, it just eases out over a few frames instead.
      const applied = Math.min(push, Math.abs(amount) + 0.05);
      center[axis] += amount > 0 ? -applied : applied;
      result.hitWall = true;
    }
  }

  return result;
}
