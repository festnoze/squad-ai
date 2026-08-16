/**
 * Accumulates triangles into typed arrays and emits a single BufferGeometry.
 *
 * The city is built from thousands of boxes and quads. Instancing would be the obvious
 * choice, but instances share one UV mapping, which stretches a 4 m facade texture across
 * a 90 m tower. Merging instead lets every face carry world-scaled UVs, so texel density
 * is constant across the whole map, and we still end up with one draw call per material.
 */

import { BufferGeometry, BufferAttribute, Vector3, Color, SRGBColorSpace } from 'three/webgpu';

// Scratch colour used to convert hex literals into the renderer's linear working space.
const _srgb = new Color();

export class GeometryBuilder {
  constructor() {
    this.pos = [];
    this.norm = [];
    this.uv = [];
    this.col = [];
    this.idx = [];
    this._v = 0;
    // Current vertex tint, applied to everything pushed until changed. This is how one
    // merged mesh gets thousands of individually coloured buildings: the material stays
    // shared (one pipeline, one draw call) while each surface carries its own albedo
    // multiplier in the vertex stream.
    this._cr = 1; this._cg = 1; this._cb = 1;
  }

  get triangleCount() { return this.idx.length / 3; }
  get isEmpty() { return this.idx.length === 0; }

  /**
   * Set the tint for subsequent geometry.
   * @param {import('three/webgpu').Color|number} color
   * @param {number} [scale] multiplier on top, for darkening/lightening
   */
  setColor(color, scale = 1) {
    if (typeof color === 'number') {
      // Hex literals are authored in sRGB (that is how they look in a colour picker),
      // but vertex colours are consumed as raw linear values by the shader. Skipping this
      // decode is what makes hand-picked mid-tones render washed out and pale.
      _srgb.setHex(color, SRGBColorSpace);
      this._cr = _srgb.r * scale;
      this._cg = _srgb.g * scale;
      this._cb = _srgb.b * scale;
    } else {
      // three's Color is already in the working (linear) space.
      this._cr = color.r * scale;
      this._cg = color.g * scale;
      this._cb = color.b * scale;
    }
    return this;
  }

  resetColor() { this._cr = this._cg = this._cb = 1; return this; }

  _pushVertex(p, n, t) {
    this.pos.push(p.x, p.y, p.z);
    this.norm.push(n.x, n.y, n.z);
    this.uv.push(t[0], t[1]);
    this.col.push(this._cr, this._cg, this._cb);
    this._v += 1;
  }

  /**
   * Push a quad. Vertices must be given counter-clockwise when viewed from the front
   * face. UVs are supplied explicitly so callers control world-scale tiling.
   */
  quad(a, b, c, d, uvA, uvB, uvC, uvD, normal) {
    const base = this._v;
    this._pushVertex(a, normal, uvA);
    this._pushVertex(b, normal, uvB);
    this._pushVertex(c, normal, uvC);
    this._pushVertex(d, normal, uvD);
    this.idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }

  /** Push a triangle with explicit UVs and a computed normal. */
  tri(a, b, c, uvA, uvB, uvC, normal = null) {
    const n = normal ?? triNormal(a, b, c);
    const base = this._v;
    this._pushVertex(a, n, uvA);
    this._pushVertex(b, n, uvB);
    this._pushVertex(c, n, uvC);
    this.idx.push(base, base + 1, base + 2);
  }

  /**
   * Axis-aligned horizontal quad (a floor or ceiling) spanning [x0,x1] x [z0,z1] at `y`.
   * `tile` is metres per texture repeat.
   */
  ground(x0, z0, x1, z1, y, tile = 4, up = true, uvOrigin = [0, 0]) {
    const u0 = (x0 + uvOrigin[0]) / tile, u1 = (x1 + uvOrigin[0]) / tile;
    const v0 = (z0 + uvOrigin[1]) / tile, v1 = (z1 + uvOrigin[1]) / tile;
    const n = new Vector3(0, up ? 1 : -1, 0);
    const A = new Vector3(x0, y, z0);
    const B = new Vector3(x0, y, z1);
    const C = new Vector3(x1, y, z1);
    const D = new Vector3(x1, y, z0);
    if (up) this.quad(A, B, C, D, [u0, v0], [u0, v1], [u1, v1], [u1, v0], n);
    else this.quad(D, C, B, A, [u1, v0], [u1, v1], [u0, v1], [u0, v0], n);
  }

  /**
   * Axis-aligned box from min/max corners with world-scaled UVs.
   * @param {number} tile metres per texture repeat
   * @param {object} [opts] `{ top, bottom, sides }` face toggles, `uvOffset` for variation
   */
  box(min, max, tile = 4, { top = true, bottom = false, sides = true, uvOffset = [0, 0] } = {}) {
    const { x: x0, y: y0, z: z0 } = min;
    const { x: x1, y: y1, z: z1 } = max;
    const [ou, ov] = uvOffset;
    const T = (n) => n / tile;

    if (sides) {
      // +X and -X faces: U runs along Z, V runs along Y.
      const zx = [T(z0) + ou, T(z1) + ou];
      const yy = [T(y0) + ov, T(y1) + ov];
      this.quad(
        new Vector3(x1, y0, z1), new Vector3(x1, y0, z0), new Vector3(x1, y1, z0), new Vector3(x1, y1, z1),
        [zx[1], yy[0]], [zx[0], yy[0]], [zx[0], yy[1]], [zx[1], yy[1]], new Vector3(1, 0, 0),
      );
      this.quad(
        new Vector3(x0, y0, z0), new Vector3(x0, y0, z1), new Vector3(x0, y1, z1), new Vector3(x0, y1, z0),
        [zx[0], yy[0]], [zx[1], yy[0]], [zx[1], yy[1]], [zx[0], yy[1]], new Vector3(-1, 0, 0),
      );
      // +Z and -Z faces: U runs along X.
      const xx = [T(x0) + ou, T(x1) + ou];
      this.quad(
        new Vector3(x0, y0, z1), new Vector3(x1, y0, z1), new Vector3(x1, y1, z1), new Vector3(x0, y1, z1),
        [xx[0], yy[0]], [xx[1], yy[0]], [xx[1], yy[1]], [xx[0], yy[1]], new Vector3(0, 0, 1),
      );
      this.quad(
        new Vector3(x1, y0, z0), new Vector3(x0, y0, z0), new Vector3(x0, y1, z0), new Vector3(x1, y1, z0),
        [xx[1], yy[0]], [xx[0], yy[0]], [xx[0], yy[1]], [xx[1], yy[1]], new Vector3(0, 0, -1),
      );
    }
    if (top) this.ground(x0, z0, x1, z1, y1, tile, true, [ou * tile, ov * tile]);
    if (bottom) this.ground(x0, z0, x1, z1, y0, tile, false);
  }

  /**
   * Box rotated about Y by `yaw`, centred on `cx,cz`. Used for anything following a road
   * direction (kerbs on diagonals, jetty planks, signage).
   *
   * NOTE: this rotates local (x, z) by `x*cos - z*sin, x*sin + z*cos`, which is the
   * *opposite* sense to a standard right-handed Y rotation. A physics collider meant to
   * line up with geometry built here must therefore be given `-yaw`. Use
   * {@link colliderYaw} rather than negating by hand at each call site.
   */
  rotatedBox(cx, cy, cz, hx, hy, hz, yaw, tile = 4, opts = {}) {
    const cos = Math.cos(yaw), sin = Math.sin(yaw);
    const local = (lx, ly, lz) => new Vector3(cx + lx * cos - lz * sin, cy + ly, cz + lx * sin + lz * cos);
    const nrm = (nx, nz) => new Vector3(nx * cos - nz * sin, 0, nx * sin + nz * cos);
    const u = hx / tile * 2, v = hy / tile * 2, w = hz / tile * 2;

    const p = [
      local(-hx, -hy, -hz), local(hx, -hy, -hz), local(hx, -hy, hz), local(-hx, -hy, hz),
      local(-hx, hy, -hz), local(hx, hy, -hz), local(hx, hy, hz), local(-hx, hy, hz),
    ];
    const { top = true, bottom = false, sides = true } = opts;
    if (sides) {
      this.quad(p[3], p[2], p[6], p[7], [0, 0], [u, 0], [u, v], [0, v], nrm(0, 1));
      this.quad(p[1], p[0], p[4], p[5], [0, 0], [u, 0], [u, v], [0, v], nrm(0, -1));
      this.quad(p[2], p[1], p[5], p[6], [0, 0], [w, 0], [w, v], [0, v], nrm(1, 0));
      this.quad(p[0], p[3], p[7], p[4], [0, 0], [w, 0], [w, v], [0, v], nrm(-1, 0));
    }
    if (top) this.quad(p[4], p[7], p[6], p[5], [0, 0], [0, w], [u, w], [u, 0], new Vector3(0, 1, 0));
    if (bottom) this.quad(p[0], p[1], p[2], p[3], [0, 0], [u, 0], [u, w], [0, w], new Vector3(0, -1, 0));
  }

  /** Truncated cone / cylinder along +Y, for lamp posts, pillars, trunks, bollards. */
  cylinder(cx, cy, cz, radius, height, segments = 10, tile = 2, capTop = true, topRadius = null) {
    const rTop = topRadius ?? radius;
    const base = this._v;
    const circumference = 2 * Math.PI * radius;
    const slope = new Vector3();
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      const nx = Math.cos(a), nz = Math.sin(a);
      const u = (i / segments) * (circumference / tile);
      // Side normal tilts outward/inward when the radii differ.
      slope.set(nx * height, radius - rTop, nz * height).normalize();
      this._pushVertex(
        { x: cx + nx * radius, y: cy, z: cz + nz * radius }, slope, [u, 0],
      );
      this._pushVertex(
        { x: cx + nx * rTop, y: cy + height, z: cz + nz * rTop }, slope, [u, height / tile],
      );
    }
    for (let i = 0; i < segments; i++) {
      const a = base + i * 2;
      this.idx.push(a, a + 2, a + 3, a, a + 3, a + 1);
    }
    if (capTop && rTop > 0.001) {
      const up = { x: 0, y: 1, z: 0 };
      const centre = this._v;
      this._pushVertex({ x: cx, y: cy + height, z: cz }, up, [0.5, 0.5]);
      const ring = this._v;
      for (let i = 0; i <= segments; i++) {
        const a = (i / segments) * Math.PI * 2;
        this._pushVertex(
          { x: cx + Math.cos(a) * rTop, y: cy + height, z: cz + Math.sin(a) * rTop }, up,
          [0.5 + Math.cos(a) * 0.5, 0.5 + Math.sin(a) * 0.5],
        );
      }
      for (let i = 0; i < segments; i++) this.idx.push(centre, ring + i, ring + i + 1);
    }
  }

  /**
   * Low-poly UV sphere, optionally squashed. Tree canopies, bushes, domes.
   * `jitter` displaces each ring radially for an organic, non-CG silhouette.
   */
  blob(cx, cy, cz, radius, { rings = 5, segments = 8, squashY = 1, jitter = 0, rand = Math.random } = {}) {
    const base = this._v;
    const n = new Vector3();
    for (let r = 0; r <= rings; r++) {
      const v = r / rings;
      const phi = v * Math.PI;
      const ringR = Math.sin(phi) * radius * (1 + (jitter ? (rand() - 0.5) * jitter : 0));
      const y = Math.cos(phi) * radius * squashY;
      for (let s = 0; s <= segments; s++) {
        const u = s / segments;
        const theta = u * Math.PI * 2;
        const x = Math.cos(theta) * ringR, z = Math.sin(theta) * ringR;
        n.set(x, y / (squashY || 1), z).normalize();
        this._pushVertex({ x: cx + x, y: cy + y, z: cz + z }, n, [u * 2, v * 2]);
      }
    }
    const stride = segments + 1;
    for (let r = 0; r < rings; r++) {
      for (let s = 0; s < segments; s++) {
        const a = base + r * stride + s;
        this.idx.push(a, a + stride, a + stride + 1, a, a + stride + 1, a + 1);
      }
    }
  }

  /** Pitched (gable) roof over a footprint, used for suburban houses. */
  gableRoof(x0, z0, x1, z1, y, height, tile = 2, alongX = true) {
    const mid = alongX ? (z0 + z1) / 2 : (x0 + x1) / 2;
    const apex = y + height;
    if (alongX) {
      const A = new Vector3(x0, y, z0), B = new Vector3(x1, y, z0);
      const C = new Vector3(x1, apex, mid), D = new Vector3(x0, apex, mid);
      const E = new Vector3(x1, y, z1), F = new Vector3(x0, y, z1);
      const slope = Math.hypot((z1 - z0) / 2, height);
      const uw = (x1 - x0) / tile, uh = slope / tile;
      this.quad(A, B, C, D, [0, 0], [uw, 0], [uw, uh], [0, uh], new Vector3(0, height, -(z1 - z0) / 2).normalize());
      this.quad(E, F, D, C, [0, 0], [uw, 0], [uw, uh], [0, uh], new Vector3(0, height, (z1 - z0) / 2).normalize());
      // Gable end triangles.
      this.tri(new Vector3(x0, y, z0), new Vector3(x0, apex, mid), new Vector3(x0, y, z1),
        [0, 0], [0.5, uh], [1, 0], new Vector3(-1, 0, 0));
      this.tri(new Vector3(x1, y, z1), new Vector3(x1, apex, mid), new Vector3(x1, y, z0),
        [0, 0], [0.5, uh], [1, 0], new Vector3(1, 0, 0));
    } else {
      const A = new Vector3(x0, y, z0), B = new Vector3(x0, y, z1);
      const C = new Vector3(mid, apex, z1), D = new Vector3(mid, apex, z0);
      const E = new Vector3(x1, y, z1), F = new Vector3(x1, y, z0);
      const slope = Math.hypot((x1 - x0) / 2, height);
      const uw = (z1 - z0) / tile, uh = slope / tile;
      this.quad(B, A, D, C, [0, 0], [uw, 0], [uw, uh], [0, uh], new Vector3(-(x1 - x0) / 2, height, 0).normalize());
      this.quad(F, E, C, D, [0, 0], [uw, 0], [uw, uh], [0, uh], new Vector3((x1 - x0) / 2, height, 0).normalize());
      this.tri(new Vector3(x0, y, z1), new Vector3(mid, apex, z1), new Vector3(x1, y, z1),
        [0, 0], [0.5, uh], [1, 0], new Vector3(0, 0, 1));
      this.tri(new Vector3(x1, y, z0), new Vector3(mid, apex, z0), new Vector3(x0, y, z0),
        [0, 0], [0.5, uh], [1, 0], new Vector3(0, 0, -1));
    }
  }

  /** Finalise into a BufferGeometry. The builder is left intact for reuse. */
  build(computeBounds = true) {
    const g = new BufferGeometry();
    g.setAttribute('position', new BufferAttribute(new Float32Array(this.pos), 3));
    g.setAttribute('normal', new BufferAttribute(new Float32Array(this.norm), 3));
    g.setAttribute('uv', new BufferAttribute(new Float32Array(this.uv), 2));
    g.setAttribute('color', new BufferAttribute(new Float32Array(this.col), 3));
    const IndexArray = this._v > 65535 ? Uint32Array : Uint16Array;
    g.setIndex(new BufferAttribute(new IndexArray(this.idx), 1));
    if (computeBounds) {
      g.computeBoundingSphere();
      g.computeBoundingBox();
    }
    return g;
  }
}

/**
 * Convert a yaw passed to {@link GeometryBuilder#rotatedBox} into the yaw a physics
 * collider needs to occupy the same space. The two use opposite rotation senses, and a
 * mismatch puts colliders somewhere the player cannot see them - which presents as
 * objects resting on thin air.
 */
export const colliderYaw = (builderYaw) => -builderYaw;

function triNormal(a, b, c) {
  const ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z;
  const vx = c.x - a.x, vy = c.y - a.y, vz = c.z - a.z;
  const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
  const len = Math.hypot(nx, ny, nz) || 1;
  return new Vector3(nx / len, ny / len, nz / len);
}
