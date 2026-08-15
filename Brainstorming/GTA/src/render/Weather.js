/**
 * Weather.
 *
 * Four states - clear, cloudy, rain, storm - that the sim drifts between on its own, or
 * that can be forced from the settings menu. Each state drives three things:
 *
 *  - `wetness`, which lowers roughness and raises reflectivity on the ground materials,
 *    so a wet road mirrors the street lights (by far the biggest visual payoff),
 *  - the rain volume, a box of streaks that follows the camera and wraps around it, so a
 *    few thousand drops cover the world no matter where the player goes,
 *  - the sky and fog, dimmed and thickened through `Atmosphere`.
 *
 * Rain is drawn as `LineSegments` rather than points: a streak reads as falling water at
 * any distance, where a point sprite has to be large enough to see and then looks like
 * snow.
 */

import {
  LineSegments, BufferGeometry, BufferAttribute, LineBasicMaterial, Color, Vector3,
  MathUtils, AdditiveBlending,
} from 'three/webgpu';
import { makeRng } from '../core/Noise.js';

export const WEATHER = {
  clear: { label: 'Clear', wetness: 0, rain: 0, cloud: 0, wind: 0.4, fog: 1.0 },
  cloudy: { label: 'Cloudy', wetness: 0.1, rain: 0, cloud: 0.55, wind: 1.0, fog: 1.35 },
  rain: { label: 'Rain', wetness: 0.85, rain: 0.75, cloud: 0.8, wind: 1.8, fog: 1.8 },
  storm: { label: 'Storm', wetness: 1.0, rain: 1.0, cloud: 1.0, wind: 3.4, fog: 2.4 },
};

const WEATHER_ORDER = ['clear', 'cloudy', 'rain', 'storm'];

/** Volume of rain around the camera, in metres. */
const BOX = { x: 70, y: 42, z: 70 };
const MAX_DROPS = 3200;
const FALL_SPEED = 34;

export class Weather {
  /**
   * @param {import('three/webgpu').Scene} scene
   * @param {import('./Atmosphere.js').Atmosphere} atmosphere
   */
  constructor(scene, atmosphere, { seed = 31337 } = {}) {
    this.scene = scene;
    this.atmosphere = atmosphere;
    this.rng = makeRng(seed);

    this.current = 'clear';
    this.target = 'clear';
    /** Blend between `current` and `target`, 0..1. */
    this.blend = 1;
    this.transitionSpeed = 0.06;
    /** Seconds until the next automatic weather roll. */
    this.nextChange = 90 + this.rng() * 180;
    this.auto = true;

    this.wetness = 0;
    this.rainAmount = 0;
    this.cloud = 0;
    this.wind = new Vector3(0.4, 0, 0.2);
    this.lightning = 0;
    this._lightningTimer = 0;

    /* ------------------------------------------------------------ rain volume */
    const positions = new Float32Array(MAX_DROPS * 6);
    this.drops = new Float32Array(MAX_DROPS * 3);
    for (let i = 0; i < MAX_DROPS; i++) {
      this.drops[i * 3] = (this.rng() - 0.5) * BOX.x;
      this.drops[i * 3 + 1] = this.rng() * BOX.y;
      this.drops[i * 3 + 2] = (this.rng() - 0.5) * BOX.z;
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute('position', new BufferAttribute(positions, 3));
    geometry.setDrawRange(0, 0);
    this.rainMesh = new LineSegments(geometry, new LineBasicMaterial({
      color: new Color(0xaac4d8),
      transparent: true,
      opacity: 0.42,
      depthWrite: false,
      blending: AdditiveBlending,
      fog: false,
    }));
    this.rainMesh.frustumCulled = false;
    this.rainMesh.name = 'rain';
    this.rainMesh.renderOrder = 12;
    scene.add(this.rainMesh);

    this._centre = new Vector3();
    this.onLightning = null;
  }

  get label() { return WEATHER[this.target].label; }

  /** Force a weather state. Disables the automatic cycle until re-enabled. */
  set(kind, { auto = false } = {}) {
    if (!WEATHER[kind]) return;
    this.current = this.blend >= 1 ? this.target : this.current;
    this.target = kind;
    this.blend = 0;
    this.auto = auto;
  }

  cycle() {
    const i = WEATHER_ORDER.indexOf(this.target);
    this.set(WEATHER_ORDER[(i + 1) % WEATHER_ORDER.length]);
  }

  /**
   * @param {number} dt
   * @param {Vector3} focus camera position
   */
  update(dt, focus) {
    /* -------------------------------------------------------------- transition */
    if (this.blend < 1) this.blend = Math.min(1, this.blend + dt * this.transitionSpeed);

    if (this.auto) {
      this.nextChange -= dt;
      if (this.nextChange <= 0) {
        this.nextChange = 120 + this.rng() * 240;
        // Weighted so clear and cloudy dominate; storms are an event, not a default.
        const roll = this.rng();
        const next = roll < 0.42 ? 'clear' : roll < 0.72 ? 'cloudy' : roll < 0.93 ? 'rain' : 'storm';
        this.set(next, { auto: true });
      }
    }

    const a = WEATHER[this.current];
    const b = WEATHER[this.target];
    const t = this.blend;
    this.wetness = MathUtils.lerp(a.wetness, b.wetness, t);
    this.rainAmount = MathUtils.lerp(a.rain, b.rain, t);
    this.cloud = MathUtils.lerp(a.cloud, b.cloud, t);
    const wind = MathUtils.lerp(a.wind, b.wind, t);
    this.fogScale = MathUtils.lerp(a.fog, b.fog, t);
    this.wind.set(wind * 0.8, 0, wind * 0.45);

    /* --------------------------------------------------------------- lightning */
    this.lightning = Math.max(0, this.lightning - dt * 6);
    if (this.rainAmount > 0.9) {
      this._lightningTimer -= dt;
      if (this._lightningTimer <= 0) {
        this._lightningTimer = 4 + this.rng() * 14;
        this.lightning = 1;
        this.onLightning?.();
      }
    }

    /* ------------------------------------------------------------------- rain */
    const count = Math.floor(MAX_DROPS * this.rainAmount);
    const geometry = this.rainMesh.geometry;
    geometry.setDrawRange(0, count * 2);
    if (count === 0) {
      this.rainMesh.visible = false;
    } else {
      this.rainMesh.visible = true;
      this._centre.set(focus.x, focus.y, focus.z);
      const positions = geometry.attributes.position.array;
      const fall = FALL_SPEED * dt;
      const streak = 0.9 + this.rainAmount * 1.4;

      for (let i = 0; i < count; i++) {
        const o = i * 3;
        this.drops[o + 1] -= fall;
        this.drops[o] += this.wind.x * dt * 8;
        this.drops[o + 2] += this.wind.z * dt * 8;

        // Wrap the drop back to the top of the box, and keep it inside laterally. The
        // box is relative to the camera, so this is all the "streaming" rain needs.
        if (this.drops[o + 1] < 0) {
          this.drops[o + 1] += BOX.y;
          this.drops[o] = (this.rng() - 0.5) * BOX.x;
          this.drops[o + 2] = (this.rng() - 0.5) * BOX.z;
        }
        if (this.drops[o] > BOX.x / 2) this.drops[o] -= BOX.x;
        if (this.drops[o] < -BOX.x / 2) this.drops[o] += BOX.x;
        if (this.drops[o + 2] > BOX.z / 2) this.drops[o + 2] -= BOX.z;
        if (this.drops[o + 2] < -BOX.z / 2) this.drops[o + 2] += BOX.z;

        const x = this._centre.x + this.drops[o];
        const y = this._centre.y - BOX.y / 2 + this.drops[o + 1];
        const z = this._centre.z + this.drops[o + 2];
        const p = i * 6;
        positions[p] = x;
        positions[p + 1] = y;
        positions[p + 2] = z;
        // The streak leans with the wind, which is what sells a storm over a drizzle.
        positions[p + 3] = x - this.wind.x * streak * 0.5;
        positions[p + 4] = y + streak;
        positions[p + 5] = z - this.wind.z * streak * 0.5;
      }
      geometry.attributes.position.needsUpdate = true;
      geometry.attributes.position.addUpdateRange(0, count * 6);
      this.rainMesh.material.opacity = 0.18 + this.rainAmount * 0.38;
    }
  }

  /**
   * Apply weather to the world's materials and lighting. Called once per frame with the
   * material handles that should respond to rain.
   *
   * @param {Array<import('three/webgpu').Material>} groundMaterials
   */
  applyTo(groundMaterials) {
    const wet = this.wetness;
    for (const m of groundMaterials) {
      if (!m) continue;
      if (m.userData.dryRoughness === undefined) {
        m.userData.dryRoughness = m.roughness;
        m.userData.dryEnv = m.envMapIntensity;
        m.userData.dryColor = m.color.clone();
      }
      /*
       * Wet asphalt gets *darker*, not lighter. Water fills the surface pores, so less
       * light scatters back diffusely - the surface loses albedo and gains a sharp
       * specular instead. Dropping roughness alone (without darkening) just makes the
       * road look like polished concrete.
       */
      m.roughness = MathUtils.lerp(m.userData.dryRoughness, 0.11, wet);
      m.envMapIntensity = MathUtils.lerp(m.userData.dryEnv, m.userData.dryEnv * 1.8 + 0.4, wet);
      m.color.copy(m.userData.dryColor).multiplyScalar(1 - wet * 0.55);
    }

    // Overcast skies are dimmer and flatter; a lightning flash briefly overrides both.
    const atmo = this.atmosphere;
    const dim = 1 - this.cloud * 0.62;
    atmo.weatherDim = dim;
    atmo.weatherFlash = this.lightning;
    if (atmo.scene.fog) atmo.fogScale = this.fogScale;
  }

  dispose() {
    this.rainMesh.geometry.dispose();
    this.rainMesh.material.dispose();
    this.rainMesh.removeFromParent();
  }
}
