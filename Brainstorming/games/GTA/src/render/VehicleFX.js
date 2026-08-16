/**
 * Vehicle effects: skid marks and particle smoke.
 *
 * Both are fixed-size ring buffers written into a single pre-allocated geometry. Nothing
 * is created or destroyed while driving - a car sliding through a corner would otherwise
 * allocate hundreds of objects a second and hand the garbage collector a stutter exactly
 * when the frame budget is tightest.
 *
 * Skid marks are a ribbon: each new mark bridges the gap between where the wheel was and
 * where it is now, so a continuous streak appears no matter the frame rate or speed.
 */

import {
  Mesh, BufferGeometry, BufferAttribute, MeshBasicMaterial, MeshStandardMaterial,
  Vector3, Color, CanvasTexture, NormalBlending, DoubleSide,
} from 'three/webgpu';

/* ------------------------------------------------------------------ skid marks */

const MAX_MARKS = 2400;
const MARK_WIDTH = 0.26;
/** Minimum wheel travel before a new ribbon segment is emitted. */
const MIN_SEGMENT = 0.35;

export class SkidMarks {
  constructor(scene, { maxMarks = MAX_MARKS } = {}) {
    this.max = maxMarks;
    this.cursor = 0;
    this.count = 0;

    const positions = new Float32Array(maxMarks * 4 * 3);
    const indices = new Uint32Array(maxMarks * 6);
    for (let i = 0; i < maxMarks; i++) {
      const v = i * 4;
      const o = i * 6;
      indices[o] = v; indices[o + 1] = v + 1; indices[o + 2] = v + 2;
      indices[o + 3] = v; indices[o + 4] = v + 2; indices[o + 5] = v + 3;
    }

    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(positions, 3));
    // Intensity is carried per-vertex so a light scuff and a hard lock-up differ.
    geometry.setAttribute('color', new BufferAttribute(new Float32Array(maxMarks * 4 * 3), 3));
    // Flat upward normals: the marks lie on the road, and they need normals at all
    // because they are lit rather than unlit (see the material note below).
    const normals = new Float32Array(maxMarks * 4 * 3);
    for (let i = 1; i < normals.length; i += 3) normals[i] = 1;
    geometry.setAttribute('normal', new BufferAttribute(normals, 3));
    geometry.setIndex(new BufferAttribute(indices, 1));
    geometry.setDrawRange(0, 0);
    this.geometry = geometry;

    /*
     * Lit, not unlit. Asphalt is already almost black, so a flat black decal is invisible
     * on it - what makes a real skid mark stand out is that scrubbed rubber is *glossier*
     * than the surrounding road. A low-roughness standard material catches the sun and
     * the street lamps, which is exactly the cue we need.
     */
    this.mesh = new Mesh(geometry, new MeshStandardMaterial({
      color: new Color(0x0a0b0d),
      roughness: 0.32,
      metalness: 0.0,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
      side: DoubleSide,
      // Marks sit on the road surface; without an offset they z-fight with it.
      polygonOffset: true,
      polygonOffsetFactor: -4,
      polygonOffsetUnits: -4,
    }));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 3;
    this.mesh.name = 'skidMarks';
    scene.add(this.mesh);

    /** Last emitted point per wheel key, so ribbons connect frame to frame. */
    this.lastPoints = new Map();
    this._a = new Vector3();
    this._b = new Vector3();
    this._side = new Vector3();
    this._up = new Vector3(0, 1, 0);
  }

  /**
   * Emit (or extend) a ribbon for one wheel.
   * @param {string} key stable per-wheel identifier
   * @param {Vector3} point contact point in world space
   * @param {Vector3} forward wheel travel direction
   * @param {number} intensity 0..1 how hard the tyre is slipping
   */
  mark(key, point, forward, intensity = 1) {
    const last = this.lastPoints.get(key);
    if (!last) {
      this.lastPoints.set(key, point.clone());
      return;
    }
    const distance = last.distanceTo(point);
    if (distance < MIN_SEGMENT) return;
    // A teleport (respawn, unstick) must not draw a mark across the whole map.
    if (distance > 12) { last.copy(point); return; }

    this._side.crossVectors(forward, this._up).normalize().multiplyScalar(MARK_WIDTH);
    if (!Number.isFinite(this._side.x)) { last.copy(point); return; }

    const base = this.cursor * 4;
    const pos = this.geometry.attributes.position.array;
    const col = this.geometry.attributes.color.array;

    const write = (slot, p, s) => {
      const o = (base + slot) * 3;
      pos[o] = p.x + s.x;
      pos[o + 1] = p.y + 0.02;
      pos[o + 2] = p.z + s.z;
    };
    this._a.copy(last);
    this._b.copy(point);
    write(0, this._a, this._side);
    write(1, this._b, this._side);
    this._side.negate();
    write(2, this._b, this._side);
    write(3, this._a, this._side);
    this._side.negate();

    const shade = 0.35 + intensity * 0.65;
    for (let v = 0; v < 4; v++) {
      const o = (base + v) * 3;
      col[o] = shade; col[o + 1] = shade; col[o + 2] = shade;
    }

    last.copy(point);
    this.cursor = (this.cursor + 1) % this.max;
    this.count = Math.min(this.count + 1, this.max);
    this.geometry.setDrawRange(0, this.count * 6);
    this.geometry.attributes.position.needsUpdate = true;
    this.geometry.attributes.color.needsUpdate = true;
  }

  /** Forget a wheel's history, e.g. when a car is teleported. */
  reset(key) { this.lastPoints.delete(key); }

  clear() {
    this.count = 0;
    this.cursor = 0;
    this.lastPoints.clear();
    this.geometry.setDrawRange(0, 0);
  }
}

/* ---------------------------------------------------------------------- smoke */

const MAX_PARTICLES = 260;

function makePuffTexture() {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,255,255,0.92)');
  g.addColorStop(0.45, 'rgba(255,255,255,0.36)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  return new CanvasTexture(canvas);
}

/**
 * Recycled particle pool for tyre smoke, engine smoke and water spray.
 *
 * Particles are camera-facing quads rather than `Points`. A textured point cloud has no
 * `uv` attribute, which the node pipeline warns about and cannot sample. Quads cost four
 * vertices each - trivial at this pool size - and give per-particle size, rotation and
 * fade for free.
 */
export class SmokePool {
  constructor(scene, { max = MAX_PARTICLES } = {}) {
    this.max = max;
    this.cursor = 0;

    this.px = new Float32Array(max * 3);
    this.vel = new Float32Array(max * 3);
    this.size = new Float32Array(max);
    this.life = new Float32Array(max);
    this.maxLife = new Float32Array(max);
    this.growth = new Float32Array(max);
    this.tint = new Float32Array(max);
    this.spin = new Float32Array(max);
    /*
     * Per-particle colour multiplier. `tint` is a single brightness, which is all grey
     * smoke ever needed; flame is not grey. The channels are allowed above 1 so a fire
     * puff lands in the bloom threshold while the smoke around it stays under it.
     */
    this.rgb = new Float32Array(max * 3);

    const positions = new Float32Array(max * 4 * 3);
    const uvs = new Float32Array(max * 4 * 2);
    const colours = new Float32Array(max * 4 * 3);
    const indices = new Uint32Array(max * 6);
    for (let i = 0; i < max; i++) {
      const v = i * 4;
      const o = i * 6;
      indices[o] = v; indices[o + 1] = v + 1; indices[o + 2] = v + 2;
      indices[o + 3] = v; indices[o + 4] = v + 2; indices[o + 5] = v + 3;
      const u = i * 8;
      uvs[u] = 0; uvs[u + 1] = 0;
      uvs[u + 2] = 1; uvs[u + 3] = 0;
      uvs[u + 4] = 1; uvs[u + 5] = 1;
      uvs[u + 6] = 0; uvs[u + 7] = 1;
    }

    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new BufferAttribute(uvs, 2));
    geometry.setAttribute('color', new BufferAttribute(colours, 3));
    geometry.setIndex(new BufferAttribute(indices, 1));
    geometry.setDrawRange(0, 0);
    this.geometry = geometry;

    this.mesh = new Mesh(geometry, new MeshBasicMaterial({
      map: makePuffTexture(),
      transparent: true,
      opacity: 0.62,
      depthWrite: false,
      vertexColors: true,
      side: DoubleSide,
      blending: NormalBlending,
    }));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 11;
    this.mesh.name = 'smoke';
    scene.add(this.mesh);

    this._right = new Vector3();
    this._up = new Vector3();
    this._a = new Vector3();
    this._b = new Vector3();
    this._active = 0;
  }

  /**
   * @param {Vector3} position
   * @param {object} [opts]
   */
  spawn(position, {
    vx = 0, vy = 1.2, vz = 0, size = 0.9, life = 1.1, colour = 0.72, growth = 1.6,
    r = 1, g = 1, b = 1.03,
  } = {}) {
    const i = this.cursor;
    this.cursor = (this.cursor + 1) % this.max;
    const o = i * 3;
    this.px[o] = position.x;
    this.px[o + 1] = position.y;
    this.px[o + 2] = position.z;
    this.vel[o] = vx;
    this.vel[o + 1] = vy;
    this.vel[o + 2] = vz;
    this.size[i] = size;
    this.life[i] = life;
    this.maxLife[i] = life;
    this.growth[i] = growth;
    this.tint[i] = colour;
    this.spin[i] = (Math.random() - 0.5) * 1.6;
    this.rgb[o] = r;
    this.rgb[o + 1] = g;
    this.rgb[o + 2] = b;
  }

  /**
   * @param {number} dt
   * @param {object|null} wind
   * @param {import('three/webgpu').Camera|null} camera billboards face this
   */
  update(dt, wind = null, camera = null) {
    const pos = this.geometry.attributes.position.array;
    const col = this.geometry.attributes.color.array;

    // Billboard basis from the camera. Without one the quads stay world-aligned, which
    // still reads acceptably from a distance.
    if (camera) {
      this._right.setFromMatrixColumn(camera.matrixWorld, 0).normalize();
      this._up.setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    } else {
      this._right.set(1, 0, 0);
      this._up.set(0, 1, 0);
    }

    let active = 0;
    for (let i = 0; i < this.max; i++) {
      const base = i * 4;
      if (this.life[i] <= 0) {
        // Collapse retired quads so they cover no pixels.
        for (let v = 0; v < 4; v++) {
          const p = (base + v) * 3;
          pos[p] = 0; pos[p + 1] = -1000; pos[p + 2] = 0;
        }
        continue;
      }
      active++;
      this.life[i] -= dt;
      const o = i * 3;
      if (this.life[i] <= 0) continue;

      // Smoke rises, slows, spreads and fades.
      this.vel[o + 1] += 0.6 * dt;
      this.vel[o] *= 1 - dt * 1.4;
      this.vel[o + 2] *= 1 - dt * 1.4;
      if (wind) {
        this.vel[o] += wind.x * dt * 0.6;
        this.vel[o + 2] += wind.z * dt * 0.6;
      }
      this.px[o] += this.vel[o] * dt;
      this.px[o + 1] += this.vel[o + 1] * dt;
      this.px[o + 2] += this.vel[o + 2] * dt;
      this.size[i] += this.growth[i] * dt;

      const t = this.life[i] / this.maxLife[i];
      const half = this.size[i] * 0.5;
      const angle = this.spin[i] * (1 - t);
      const c = Math.cos(angle), sn = Math.sin(angle);
      // Rotate the billboard basis in screen space so puffs are not all identical.
      this._a.copy(this._right).multiplyScalar(c).addScaledVector(this._up, sn).multiplyScalar(half);
      this._b.copy(this._up).multiplyScalar(c).addScaledVector(this._right, -sn).multiplyScalar(half);

      const cx = this.px[o], cy = this.px[o + 1], cz = this.px[o + 2];
      const corner = (v, sx, sy) => {
        const p = (base + v) * 3;
        pos[p] = cx + this._a.x * sx + this._b.x * sy;
        pos[p + 1] = cy + this._a.y * sx + this._b.y * sy;
        pos[p + 2] = cz + this._a.z * sx + this._b.z * sy;
      };
      corner(0, -1, -1);
      corner(1, 1, -1);
      corner(2, 1, 1);
      corner(3, -1, 1);

      // Per-particle fade lives in the vertex colour; the material has one global opacity.
      const fade = t * t * this.tint[i];
      const cr = fade * this.rgb[o], cg = fade * this.rgb[o + 1], cb = fade * this.rgb[o + 2];
      for (let v = 0; v < 4; v++) {
        const p = (base + v) * 3;
        col[p] = cr; col[p + 1] = cg; col[p + 2] = cb;
      }
    }

    this._active = active;
    this.geometry.setDrawRange(0, this.max * 6);
    this.geometry.attributes.position.needsUpdate = true;
    this.geometry.attributes.color.needsUpdate = true;
  }

  get activeCount() { return this._active; }
}
