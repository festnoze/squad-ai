/**
 * Sky, sun, and the lighting rig that follows the player.
 *
 * Uses SkyMesh (the WebGPU/TSL port of the Preetham analytic daylight model) for the
 * background, drives a directional light from the same sun vector, and periodically bakes
 * the sky into a PMREM environment map so PBR reflections match the time of day.
 *
 * The shadow camera is small and follows the player rather than covering the whole map -
 * a 4 km city with one 4096 shadow map would give ~1 m texels; a 140 m follow frustum
 * gives ~3 cm.
 */

import {
  DirectionalLight, HemisphereLight, AmbientLight, Vector3, Color, MathUtils,
  PMREMGenerator, Scene, FogExp2, Group,
} from 'three/webgpu';
import { SkyDome } from './SkyDome.js';

/** Skydome radius. Kept comfortably inside `CameraRig`'s far plane (12000). */
export const SKY_RADIUS = 8000;

/** Key colour of the sun at a given elevation, roughly matching CIE daylight shifts. */
function sunColorForElevation(elevationDeg, out) {
  const t = MathUtils.clamp((elevationDeg + 4) / 24, 0, 1);
  // Deep orange at the horizon -> neutral white overhead.
  const dawn = new Color(0xff6a2a);
  const noon = new Color(0xfff4e2);
  return out.copy(dawn).lerp(noon, t * t);
}

export class Atmosphere {
  /**
   * @param {import('three/webgpu').Scene} scene
   * @param {import('three/webgpu').WebGPURenderer} renderer
   */
  constructor(scene, renderer) {
    this.scene = scene;
    this.renderer = renderer;

    /** Hours 0-24. 8.5 = soft morning light, good for showing off the city. */
    this.timeOfDay = 9.25;
    /** Game minutes per real second. 1 in-game day = 24 real minutes at 60. */
    this.timeScale = 60;
    this.paused = false;

    this.sunDirection = new Vector3(0, 1, 0);
    this.sunColor = new Color(0xffffff);

    this.skyDome = new SkyDome(SKY_RADIUS);
    this.sky = this.skyDome.mesh;
    scene.add(this.sky);
    // The dome paints the whole background, so the clear colour never shows.
    scene.background = null;

    this.sun = new DirectionalLight(0xffffff, 3.0);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(4096, 4096);
    this.sun.shadow.bias = -0.0006;
    this.sun.shadow.normalBias = 0.035;
    this.sun.shadow.radius = 2;
    const c = this.sun.shadow.camera;
    this.shadowExtent = 150;
    c.left = -this.shadowExtent; c.right = this.shadowExtent;
    c.top = this.shadowExtent; c.bottom = -this.shadowExtent;
    c.near = 1; c.far = 900;
    this.sunRig = new Group();
    this.sunRig.add(this.sun, this.sun.target);
    scene.add(this.sunRig);

    // Sky bounce. Hemisphere gives the vertical gradient a single ambient term can't.
    this.hemi = new HemisphereLight(0x9fc4ff, 0x4a3f33, 0.6);
    scene.add(this.hemi);
    this.ambient = new AmbientLight(0xffffff, 0.12);
    scene.add(this.ambient);

    // `?fog=off` disables atmospheric fog at construction. Node materials bake the fog
    // term in at compile time, so this has to be decided before the first render.
    this.fogEnabled = new URLSearchParams(location.search).get('fog') !== 'off';
    if (this.fogEnabled) this.scene.fog = new FogExp2(0x9fb6cc, 0.00085);

    // A second, small dome is baked into the environment map. Reusing the same analytic
    // model keeps reflections consistent with what the player can actually see.
    this._pmrem = new PMREMGenerator(renderer);
    this._envScene = new Scene();
    this._envDome = new SkyDome(500, 24, 16);
    this._envScene.add(this._envDome.mesh);
    this._envTarget = null;
    this._envDirtyAt = -1;
    this._envSupported = true;

    /** Written by `Weather`: 1 = clear skies, lower = overcast. */
    this.weatherDim = 1;
    /** 0..1 lightning flash, briefly overriding the sun. */
    this.weatherFlash = 0;
    /** Fog density multiplier from weather. */
    this.fogScale = 1;

    this.update(0, new Vector3());
  }

  /** Sun elevation/azimuth in degrees for the current hour. */
  _sunAngles() {
    const h = this.timeOfDay;
    // Sun rises ~06:00, peaks 13:00 at 64 deg, sets ~20:00. Latitude-ish curve.
    const dayT = (h - 6) / 14;
    const elevation = Math.sin(MathUtils.clamp(dayT, -0.3, 1.3) * Math.PI) * 64 - 2;
    const azimuth = 90 + dayT * 180;
    return { elevation, azimuth };
  }

  /**
   * @param {number} dt seconds
   * @param {Vector3} focus world position the shadow frustum should centre on
   */
  update(dt, focus) {
    if (!this.paused) {
      this.timeOfDay = (this.timeOfDay + (dt * this.timeScale) / 3600) % 24;
    }

    const { elevation, azimuth } = this._sunAngles();
    const phi = MathUtils.degToRad(90 - elevation);
    const theta = MathUtils.degToRad(azimuth);
    this.sunDirection.setFromSphericalCoords(1, phi, theta);
    this.skyDome.update(this.sunDirection, elevation);

    // Light intensity and colour track elevation; below the horizon we fall back to
    // moonlight so the city is navigable at night.
    const above = MathUtils.clamp(elevation / 14, 0, 1);
    const night = 1 - above;
    sunColorForElevation(elevation, this.sunColor);
    if (elevation > -2) {
      this.sun.color.copy(this.sunColor);
      this.sun.intensity = (0.3 + above * 2.3) * this.weatherDim;
    } else {
      // Moonlight. Bright enough to read the streets by - a physically honest night is
      // unplayable, and street lamps only light their immediate pool.
      this.sun.color.setHex(0x8fa8d8);
      this.sun.intensity = 0.38 * this.weatherDim;
      this.sunDirection.set(0.3, 0.75, -0.4).normalize();
    }

    // The baked sky environment already supplies most of the ambient term, so the
    // fill lights stay low - otherwise midday concrete blows straight to white.
    // Overcast raises the diffuse fill even as it cuts the sun: that flat, shadowless
    // look is most of what makes a sky read as heavy rather than merely dark.
    const overcast = 1 - this.weatherDim;
    this.hemi.intensity = (0.24 + above * 0.16) * (1 + overcast * 0.8);
    this.hemi.color.setHex(0x9fc4ff).lerp(new Color(0x3a4560), night * 0.8);
    this.ambient.intensity = 0.05 + above * 0.02 + overcast * 0.06;

    // Lightning: a hard, brief lift on the ambient terms.
    if (this.weatherFlash > 0) {
      const f = this.weatherFlash;
      this.ambient.intensity += f * 2.2;
      this.hemi.intensity += f * 1.6;
    }

    // Atmospheric haze thickens at dawn/dusk and at night.
    if (this.scene.fog) {
      this.scene.fog.density = (0.00052 + night * 0.0006) * this.fogScale;
      // Match the fog to the sky's own horizon colour so distant geometry dissolves
      // into the skyline instead of into an unrelated grey.
      this.scene.fog.color.copy(this.skyDome.horizonColor);
    }

    // Keep the shadow frustum tight around the action.
    const d = this.shadowExtent * 2.4;
    this.sun.position.copy(focus).addScaledVector(this.sunDirection, d);
    this.sun.target.position.copy(focus);
    this.sun.target.updateMatrixWorld();
    this.skyDome.setCenter(focus.x, focus.z);

    // Rebake the environment a few times per in-game hour, not per frame.
    const bakeKey = Math.floor(this.timeOfDay * 4);
    if (this._envSupported && bakeKey !== this._envDirtyAt) {
      this._envDirtyAt = bakeKey;
      this._bakeEnvironment();
    }
  }

  _bakeEnvironment() {
    try {
      const { elevation } = this._sunAngles();
      this._envDome.update(this.sunDirection, elevation, true);
      const prev = this._envTarget;
      this._envTarget = this._pmrem.fromScene(this._envScene, 0.04);
      this.scene.environment = this._envTarget.texture;
      // Tuned against SkyDome's authored radiance: the dome is deliberately dimmer than
      // a physical sky, so the environment term needs to be taken at full strength.
      this.scene.environmentIntensity = 1.15;
      prev?.dispose();
    } catch (err) {
      // PMREM from a node-material scene can fail on some backends; the hemisphere
      // light still gives usable ambient so this is non-fatal.
      console.warn('[Atmosphere] environment bake unavailable, falling back to lights only:', err.message);
      this._envSupported = false;
    }
  }

  /** Formatted HH:MM for the HUD. */
  clockString() {
    const h = Math.floor(this.timeOfDay);
    const m = Math.floor((this.timeOfDay - h) * 60);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }

  get isNight() {
    const { elevation } = this._sunAngles();
    return elevation < 1.5;
  }

  /**
   * 0 in full daylight, 1 well after dark, ramping through dusk. Everything that has to
   * change at night - street lamps, lit windows, headlights - reads this one value so
   * they all cross-fade together.
   */
  get nightFactor() {
    const { elevation } = this._sunAngles();
    return MathUtils.clamp((6 - elevation) / 12, 0, 1);
  }

  dispose() {
    this._envTarget?.dispose();
    this._pmrem.dispose();
    this.skyDome.dispose();
    this._envDome.dispose();
  }
}
