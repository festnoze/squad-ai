/**
 * Height fog with forward scattering.
 *
 * `FogExp2` is uniform in every direction: it thickens with distance and nothing else. In
 * a city that is wrong in two ways. Real haze pools at ground level, so a tower should
 * emerge from it as it rises and an aerial view should look down *into* it - and haze is
 * lit by the sun, so looking towards the sun through it is bright and looking away is
 * flat. Distance-only fog gives a uniform grey that flattens the skyline and reads as a
 * draw-distance trick rather than as air.
 *
 * This replaces `scene.fog`'s shading with a `scene.fogNode`, which the node materials
 * pick up in place of the automatic one. `scene.fog` is deliberately left in place: it is
 * still the data holder that `Atmosphere` and `Weather` write density and colour into,
 * and it is still what the effect falls back to if the node fails to build.
 *
 * The height falloff itself is three's own `exponentialHeightFogFactor`, which fogs by
 * how far a fragment sits *below* a height plane. That is a per-fragment approximation
 * rather than a true integral along the view ray, and for a city it is the right
 * approximation: the thing you look at is what decides how much air is in the way.
 */

import { Color, Vector3 } from 'three/webgpu';
import { fog, exponentialHeightFogFactor, uniform, positionWorld, cameraPosition, mix, pow, max, min, float } from 'three/tsl';

export class VolumetricFog {
  /** @param {import('three/webgpu').Scene} scene */
  constructor(scene) {
    this.scene = scene;
    this.enabled = false;

    /*
     * Density is squared and multiplied by (height - y) * viewZ inside the factor, so it
     * is not in the same units as `FogExp2.density` and is far more sensitive. These
     * numbers were tuned by eye against the skyline, not converted.
     */
    this.density = uniform(float(0.0000105));
    /** Everything below this world Y is in the haze layer; above it the air is clear. */
    this.height = uniform(float(155));
    /** Hard ceiling on the fog term so distant silhouettes never dissolve completely. */
    this.maxFactor = uniform(float(0.94));

    this.color = uniform(new Color(0x9fb6cc));
    /** Colour of the haze when looking into the sun - the forward-scattering lobe. */
    this.sunColor = uniform(new Color(0xffd9a8));
    this.sunDirection = uniform(new Vector3(0, 1, 0));
    /** 0 disables the scattering tint; drops to 0 as the sun sets. */
    this.scatter = uniform(float(0.0));

    this._c = new Color();
  }

  /**
   * Install the node. Must happen before the first render: node materials bake the fog
   * term in at compile time, so switching it on later recompiles the whole city.
   */
  attach() {
    try {
      const toFragment = positionWorld.sub(cameraPosition).normalize();
      // Forward scattering: tighten the lobe with a high power so only the region
      // actually around the sun brightens, rather than the whole sunward half of the sky.
      const towardsSun = max(toFragment.dot(this.sunDirection), 0.0);
      const lobe = pow(towardsSun, 6.0).mul(this.scatter);
      const tinted = mix(this.color, this.sunColor, lobe);

      const factor = min(
        exponentialHeightFogFactor(this.density, this.height),
        this.maxFactor,
      );

      this.scene.fogNode = fog(tinted, factor);
      this.enabled = true;
    } catch (err) {
      console.warn('[VolumetricFog] disabled - node failed to build:', err);
      this.scene.fogNode = null;
      this.enabled = false;
    }
    return this;
  }

  /**
   * @param {object} state
   * @param {Color} state.horizon sky horizon colour, so haze matches the skyline
   * @param {Color} state.sun current sun colour
   * @param {Vector3} state.sunDirection
   * @param {number} state.density the `FogExp2`-scale density Atmosphere computed
   * @param {number} state.night 0-1
   * @param {number} state.wetness 0-1, from Weather
   */
  update({ horizon, sun, sunDirection, density, night = 0, wetness = 0 }) {
    if (!this.enabled) return;

    this.color.value.copy(horizon);
    // The scattering lobe borrows the sun's own colour, brightened - haze lit from
    // behind is always brighter than the light source's diffuse contribution suggests.
    this.sunColor.value.copy(sun).lerp(this._c.setRGB(1, 1, 1), 0.25);
    this.sunDirection.value.copy(sunDirection);

    /*
     * Map Atmosphere's FogExp2 density onto this node's very different scale. The two are
     * not interchangeable - the height factor multiplies by (height - y) as well as by
     * depth - so this is a fitted ratio, not a unit conversion.
     */
    this.density.value = density * 0.0052;

    // Rain fills the air: the layer deepens and the sun stops punching through it.
    this.height.value = 155 + wetness * 90;
    this.scatter.value = Math.max(0, 1 - night * 1.6) * (1 - wetness * 0.75) * 0.85;
  }
}
