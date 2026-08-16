/**
 * Analytic skydome.
 *
 * three's `SkyMesh` (the TSL port of the Preetham model) does not composite correctly in
 * this pipeline - it never reaches the framebuffer, leaving the flat background colour
 * showing through. Rather than depend on an addon's internal depth handling, this builds
 * the sky directly: a large inverted sphere whose vertex colours are evaluated on the CPU
 * from an analytic day/night model.
 *
 * Evaluating per-vertex rather than per-pixel costs about 1500 colour writes per in-game
 * minute, which is free, and it means the sky is plain data we fully control: horizon
 * glow, zenith gradient, sunset banding and the sun's own halo are all explicit.
 *
 * Values are authored in linear space at HDR scale - the sun's halo deliberately exceeds
 * 1.0 so the bloom threshold catches it.
 */

import {
  Mesh, SphereGeometry, BufferAttribute, MeshBasicMaterial, BackSide, Color, Vector3,
  AdditiveBlending, Sprite, SpriteMaterial, CanvasTexture,
} from 'three/webgpu';

const lerp = (a, b, t) => a + (b - a) * t;
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smoothstep = (e0, e1, x) => {
  const t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};

/** Palette keyframes by sun elevation, in linear HDR. */
const PALETTE = {
  night: {
    zenith: [0.006, 0.010, 0.026],
    horizon: [0.020, 0.028, 0.055],
    sunGlow: [0.10, 0.12, 0.20],
  },
  twilight: {
    zenith: [0.035, 0.055, 0.135],
    horizon: [0.42, 0.26, 0.30],
    sunGlow: [2.20, 0.70, 0.32],
  },
  sunset: {
    zenith: [0.10, 0.19, 0.44],
    horizon: [1.05, 0.62, 0.38],
    sunGlow: [5.50, 2.10, 0.75],
  },
  day: {
    zenith: [0.075, 0.185, 0.520],
    horizon: [0.62, 0.74, 0.90],
    sunGlow: [6.00, 5.20, 4.20],
  },
};

function mixPalette(a, b, t, out) {
  for (const key of ['zenith', 'horizon', 'sunGlow']) {
    out[key][0] = lerp(a[key][0], b[key][0], t);
    out[key][1] = lerp(a[key][1], b[key][1], t);
    out[key][2] = lerp(a[key][2], b[key][2], t);
  }
  return out;
}

/** Soft radial sprite used for the sun disc. */
function makeSunSprite() {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.22, 'rgba(255,250,235,0.92)');
  g.addColorStop(0.5, 'rgba(255,225,180,0.28)');
  g.addColorStop(1, 'rgba(255,200,140,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

export class SkyDome {
  /**
   * @param {number} radius must sit inside the camera far plane
   */
  constructor(radius = 8000, widthSegments = 40, heightSegments = 24) {
    this.radius = radius;
    const geometry = new SphereGeometry(radius, widthSegments, heightSegments);
    const count = geometry.attributes.position.count;
    geometry.setAttribute('color', new BufferAttribute(new Float32Array(count * 3), 3));

    // Cache the normalised direction of every vertex; it never changes.
    this._dirs = new Float32Array(count * 3);
    const pos = geometry.attributes.position.array;
    for (let i = 0; i < count; i++) {
      const x = pos[i * 3], y = pos[i * 3 + 1], z = pos[i * 3 + 2];
      const len = Math.hypot(x, y, z) || 1;
      this._dirs[i * 3] = x / len;
      this._dirs[i * 3 + 1] = y / len;
      this._dirs[i * 3 + 2] = z / len;
    }

    const material = new MeshBasicMaterial({
      vertexColors: true,
      side: BackSide,
      depthWrite: false,
      fog: false,
    });

    this.mesh = new Mesh(geometry, material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = -1000;
    this.mesh.name = 'skyDome';

    this.sunSprite = new Sprite(new SpriteMaterial({
      map: makeSunSprite(),
      blending: AdditiveBlending,
      depthWrite: false,
      depthTest: false,
      fog: false,
      transparent: true,
    }));
    this.sunSprite.scale.setScalar(radius * 0.09);
    this.sunSprite.renderOrder = -999;
    this.mesh.add(this.sunSprite);

    this._palette = {
      zenith: [0, 0, 0], horizon: [0, 0, 0], sunGlow: [0, 0, 0],
    };
    this._lastKey = null;
    /** Sampled zenith/horizon colours, exposed for fog tinting. */
    this.horizonColor = new Color();
    this.zenithColor = new Color();
  }

  /**
   * Recompute the vertex colours for a sun direction.
   * @param {Vector3} sunDirection normalised, world space
   * @param {number} elevationDeg sun elevation above the horizon
   * @param {boolean} [force] recompute even if the cache key is unchanged
   */
  update(sunDirection, elevationDeg, force = false) {
    // One update per in-game minute of sun movement is imperceptibly smooth.
    const key = Math.round(elevationDeg * 6);
    if (!force && key === this._lastKey) return;
    this._lastKey = key;

    // Blend the four keyframes across the elevation range.
    const p = this._palette;
    if (elevationDeg <= -8) mixPalette(PALETTE.night, PALETTE.night, 0, p);
    else if (elevationDeg < 0) mixPalette(PALETTE.night, PALETTE.twilight, smoothstep(-8, 0, elevationDeg), p);
    else if (elevationDeg < 9) mixPalette(PALETTE.twilight, PALETTE.sunset, smoothstep(0, 9, elevationDeg), p);
    else mixPalette(PALETTE.sunset, PALETTE.day, smoothstep(9, 32, elevationDeg), p);

    const sx = sunDirection.x, sy = sunDirection.y, sz = sunDirection.z;
    const colors = this.mesh.geometry.attributes.color;
    const arr = colors.array;
    const dirs = this._dirs;
    const count = colors.count;

    for (let i = 0; i < count; i++) {
      const dx = dirs[i * 3], dy = dirs[i * 3 + 1], dz = dirs[i * 3 + 2];

      // Vertical gradient. The exponent compresses the transition towards the horizon,
      // which is what makes a sky read as a dome rather than a linear ramp.
      const up = clamp01(dy);
      const grad = Math.pow(up, 0.42);
      let r = lerp(p.horizon[0], p.zenith[0], grad);
      let g = lerp(p.horizon[1], p.zenith[1], grad);
      let b = lerp(p.horizon[2], p.zenith[2], grad);

      // Sun halo: a broad Mie-like forward scatter lobe plus a tight core.
      const cosTheta = dx * sx + dy * sy + dz * sz;
      const forward = clamp01(cosTheta);
      const broad = Math.pow(forward, 4) * 0.32;
      const tight = Math.pow(forward, 90) * 0.9;
      // The glow hugs the horizon at sunrise/sunset, which is where the colour is.
      const horizonBias = 1 + (1 - up) * 1.6;
      const glow = (broad + tight) * horizonBias;
      r += p.sunGlow[0] * glow;
      g += p.sunGlow[1] * glow;
      b += p.sunGlow[2] * glow;

      // Below the horizon the dome darkens towards the ground haze.
      if (dy < 0) {
        const below = smoothstep(0, -0.35, dy);
        r = lerp(r, r * 0.35 + 0.02, below);
        g = lerp(g, g * 0.35 + 0.02, below);
        b = lerp(b, b * 0.38 + 0.03, below);
      }

      arr[i * 3] = r;
      arr[i * 3 + 1] = g;
      arr[i * 3 + 2] = b;
    }
    colors.needsUpdate = true;

    this.horizonColor.setRGB(p.horizon[0], p.horizon[1], p.horizon[2]);
    this.zenithColor.setRGB(p.zenith[0], p.zenith[1], p.zenith[2]);

    // Park the sun sprite on the dome, and fade it out once below the horizon.
    this.sunSprite.position.set(sx, sy, sz).multiplyScalar(this.radius * 0.94);
    const visible = elevationDeg > -3;
    this.sunSprite.visible = visible;
    if (visible) {
      this.sunSprite.material.opacity = clamp01(smoothstep(-3, 4, elevationDeg));
      this.sunSprite.material.color.setRGB(
        Math.min(2, p.sunGlow[0] * 0.5), Math.min(2, p.sunGlow[1] * 0.5), Math.min(2, p.sunGlow[2] * 0.5),
      );
    }
  }

  /** Keep the dome centred on the viewer so it never clips. */
  setCenter(x, z) { this.mesh.position.set(x, 0, z); }

  dispose() {
    this.mesh.geometry.dispose();
    this.mesh.material.dispose();
    this.sunSprite.material.map?.dispose();
    this.sunSprite.material.dispose();
  }
}

export { Vector3 as _Vector3 };
