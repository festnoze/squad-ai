/**
 * Night lighting.
 *
 * A city has thousands of light sources and a renderer can afford a handful. The trick is
 * to separate *looking* lit from *casting* light:
 *
 *  - Every lamp head and window in the city is emissive geometry. That is what you see,
 *    it costs nothing, and bloom picks it up.
 *  - A small pool of real point lights is reassigned each frame to whichever lamp posts
 *    are nearest the camera. Those are what actually light the road surface, the player
 *    and passing cars.
 *  - The player's vehicle gets two real spot lights for headlights; other traffic makes
 *    do with emissive lamps and a projected pool light.
 *
 * The pool is re-targeted rather than rebuilt, so no lights are ever created or destroyed
 * at runtime - which matters because adding a light to a scene forces a shader recompile.
 */

import { PointLight, SpotLight, Object3D, Color, MathUtils } from 'three/webgpu';

const LAMP_COLOUR = 0xffd9a0;
const HEADLIGHT_COLOUR = 0xfff2d8;

export class NightLights {
  /**
   * @param {import('three/webgpu').Scene} scene
   * @param {Array<{x:number,y:number,z:number}>} lampPositions
   */
  constructor(scene, lampPositions, { poolSize = 10 } = {}) {
    this.scene = scene;
    this.lamps = lampPositions;
    this.nightFactor = 0;

    /** @type {PointLight[]} */
    this.pool = [];
    for (let i = 0; i < poolSize; i++) {
      const light = new PointLight(new Color(LAMP_COLOUR), 0, 44, 2);
      light.castShadow = false;   // point-light shadows are far too costly at this count
      light.visible = false;
      scene.add(light);
      this.pool.push(light);
    }

    // Headlights for the player's vehicle only.
    this.headlights = [];
    this.headlightTarget = new Object3D();
    scene.add(this.headlightTarget);
    for (let i = 0; i < 2; i++) {
      const spot = new SpotLight(new Color(HEADLIGHT_COLOUR), 0, 110, 0.52, 0.42, 1.5);
      spot.castShadow = false;
      spot.visible = false;
      spot.target = this.headlightTarget;
      scene.add(spot);
      this.headlights.push(spot);
    }

    this._candidates = [];
  }

  /**
   * @param {number} nightFactor 0 = day, 1 = night
   * @param {import('three/webgpu').Vector3} focus camera position
   * @param {object|null} playerVehicle
   */
  update(nightFactor, focus, playerVehicle) {
    this.nightFactor = nightFactor;
    const active = nightFactor > 0.04;

    /* --------------------------------------------------------- street lighting */
    if (!active) {
      for (const l of this.pool) l.visible = false;
    } else {
      // Pick the nearest lamps. A partial selection is enough - we only need the closest
      // `poolSize`, not a full sort of several thousand entries.
      this._candidates.length = 0;
      const maxRange = 70;
      for (const lamp of this.lamps) {
        const dx = lamp.x - focus.x, dz = lamp.z - focus.z;
        const d2 = dx * dx + dz * dz;
        if (d2 > maxRange * maxRange) continue;
        this._candidates.push({ lamp, d2 });
      }
      this._candidates.sort((a, b) => a.d2 - b.d2);

      for (let i = 0; i < this.pool.length; i++) {
        const light = this.pool[i];
        const entry = this._candidates[i];
        if (!entry) { light.visible = false; continue; }
        light.position.set(entry.lamp.x, entry.lamp.y, entry.lamp.z);
        // Fade the outermost lights in rather than popping them on.
        const fade = 1 - MathUtils.clamp(Math.sqrt(entry.d2) / maxRange, 0, 1);
        /*
         * three's punctual lights are physical: intensity is candela and illuminance
         * falls off as 1/d^2. A lamp head is ~7 m above the pavement, so anything under
         * about 150 cd produces no visible pool of light at all.
         */
        light.intensity = 210 * nightFactor * (0.35 + fade * 0.65);
        light.visible = true;
      }
    }

    /* ---------------------------------------------------------------- headlights */
    const useHeadlights = playerVehicle && !playerVehicle.isBoat && playerVehicle.headlightsOn;
    if (!useHeadlights) {
      for (const s of this.headlights) s.visible = false;
      return;
    }

    const car = playerVehicle;
    const t = car.body.translation();
    const forward = car.forward();
    // Right vector from the forward vector, on the horizontal plane.
    const rx = -forward.z, rz = forward.x;
    const spec = car.spec;
    const halfTrack = (spec.chassis?.hx ?? 0.9) * 0.62;
    const nose = (spec.chassis?.hz ?? 2) * 0.92;

    for (let i = 0; i < 2; i++) {
      const side = i === 0 ? -1 : 1;
      const spot = this.headlights[i];
      spot.position.set(
        t.x + forward.x * nose + rx * halfTrack * side,
        t.y + 0.15,
        t.z + forward.z * nose + rz * halfTrack * side,
      );
      spot.intensity = 1400;
      spot.visible = true;
    }
    // Both spots share a target well ahead of the car, angled slightly down.
    this.headlightTarget.position.set(
      t.x + forward.x * 26, t.y - 2.2, t.z + forward.z * 26,
    );
    this.headlightTarget.updateMatrixWorld();
  }

  dispose() {
    for (const l of this.pool) l.removeFromParent();
    for (const s of this.headlights) s.removeFromParent();
    this.headlightTarget.removeFromParent();
  }
}
