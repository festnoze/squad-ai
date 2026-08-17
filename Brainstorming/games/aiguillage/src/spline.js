/**
 * AIGUILLAGE - arc length parameterised spline, one per track segment.
 *
 * Wraps a THREE.CatmullRomCurve3 but never hands the curve out directly:
 * frames are pre sampled once at build time into flat typed arrays so that
 * `at(s, out)` is a plain lerp between two neighbours, zero allocation, no
 * per call binary search. This mirrors the approach used by VELOCITRON's
 * track.js, simplified because a train never banks: "up" is always world Y.
 */

import * as THREE from 'three';

const SPACING = 0.5; // metres between precomputed samples

export function createSpline(points) {
  const pts = points.map((p) => new THREE.Vector3(p.x, p.y || 0, p.z));
  const curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.5);
  curve.arcLengthDivisions = Math.max(200, pts.length * 60);

  const length = curve.getLength();
  const sampleCount = Math.max(2, Math.ceil(length / SPACING) + 1);
  const spacing = length / (sampleCount - 1);

  const px = new Float32Array(sampleCount);
  const py = new Float32Array(sampleCount);
  const pz = new Float32Array(sampleCount);
  const tx = new Float32Array(sampleCount);
  const ty = new Float32Array(sampleCount);
  const tz = new Float32Array(sampleCount);

  const p = new THREE.Vector3();
  const t = new THREE.Vector3();
  for (let i = 0; i < sampleCount; i++) {
    const u = length > 0 ? (i * spacing) / length : 0;
    curve.getPointAt(Math.min(1, u), p);
    curve.getTangentAt(Math.min(1, u), t).normalize();
    px[i] = p.x; py[i] = p.y; pz[i] = p.z;
    tx[i] = t.x; ty[i] = t.y; tz[i] = t.z;
  }

  const spline = {
    length,

    /** Fills and returns `out = { pos, tangent }` (both Vector3 owned by the caller). */
    at(s, out) {
      const clamped = s < 0 ? 0 : s > length ? length : s;
      const f = spacing > 0 ? clamped / spacing : 0;
      let i0 = Math.floor(f);
      if (i0 >= sampleCount - 1) i0 = sampleCount - 2;
      if (i0 < 0) i0 = 0;
      const i1 = i0 + 1;
      const frac = f - i0;
      out.pos.set(
        px[i0] + (px[i1] - px[i0]) * frac,
        py[i0] + (py[i1] - py[i0]) * frac,
        pz[i0] + (pz[i1] - pz[i0]) * frac,
      );
      out.tangent.set(
        tx[i0] + (tx[i1] - tx[i0]) * frac,
        ty[i0] + (ty[i1] - ty[i0]) * frac,
        tz[i0] + (tz[i1] - tz[i0]) * frac,
      ).normalize();
      return out;
    },

    /** Fresh array of sample points for building visible geometry (tube, sleepers...). */
    samplePoints(count) {
      const out = [];
      const n = Math.max(2, count);
      const frame = { pos: new THREE.Vector3(), tangent: new THREE.Vector3() };
      for (let i = 0; i < n; i++) {
        spline.at((i / (n - 1)) * length, frame);
        out.push(frame.pos.clone());
      }
      return out;
    },

    makeFrame() {
      return { pos: new THREE.Vector3(), tangent: new THREE.Vector3() };
    },

    dispose() {
      // No GPU resource owned directly by the spline itself.
    },
  };

  return spline;
}
