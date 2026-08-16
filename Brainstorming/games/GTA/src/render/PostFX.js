/**
 * Post-processing chain built on three's TSL node pipeline (WebGPU-native, falls back to
 * WebGL2 through the same node graph).
 *
 * Chain: scene pass -> GTAO (ground-truth ambient occlusion) -> bloom -> SMAA -> tone map.
 *
 * Every stage is optional and wrapped, because the node passes are the most
 * backend-sensitive part of the renderer. If any of them fails to compile we degrade to
 * direct rendering rather than showing a black screen.
 */

import { PostProcessing } from 'three/webgpu';
import { pass, mrt, output, transformedNormalView, convertToTexture } from 'three/tsl';
import { ao } from 'three/addons/tsl/display/GTAONode.js';
import { bloom } from 'three/addons/tsl/display/BloomNode.js';
import { smaa } from 'three/addons/tsl/display/SMAANode.js';
import { godrays } from 'three/addons/tsl/display/GodraysNode.js';
import { bilateralBlur } from 'three/addons/tsl/display/BilateralBlurNode.js';
import { depthAwareBlend } from 'three/addons/tsl/display/depthAwareBlend.js';

/**
 * Bloom is deliberately restrained. The threshold sits above 1.0 so only genuinely
 * over-range pixels - sun glints, headlights, emissive signage - bloom at all. A lower
 * threshold catches ordinary sunlit concrete and hazes the entire city.
 */
export const QUALITY = {
  low: { ao: false, bloom: true, smaa: false, godrays: false, bloomStrength: 0.12, bloomThreshold: 1.15, scale: 0.75 },
  medium: { ao: false, bloom: true, smaa: true, godrays: false, bloomStrength: 0.16, bloomThreshold: 1.1, scale: 1.0 },
  high: { ao: true, bloom: true, smaa: true, godrays: false, bloomStrength: 0.2, bloomThreshold: 1.05, scale: 1.0 },
  ultra: {
    ao: true, bloom: true, smaa: true, bloomStrength: 0.26, bloomThreshold: 1.0, scale: 1.0,
    // Godrays are an ultra-only stage: 48 raymarch steps per pixel at half resolution is
    // by a wide margin the most expensive thing in the chain.
    godrays: true, godraysScale: 0.5, godraysSteps: 48,
  },
};

export class PostFX {
  /**
   * @param {import('three/webgpu').WebGPURenderer} renderer
   * @param {import('three/webgpu').Scene} scene
   * @param {import('three/webgpu').Camera} camera
   * @param {keyof typeof QUALITY} quality
   */
  constructor(renderer, scene, camera, quality = 'high', sunLight = null) {
    this.renderer = renderer;
    this.scene = scene;
    this.camera = camera;
    this.enabled = false;
    this.quality = quality;
    /**
     * Godrays raymarch a light's shadow map, so this has to be the shadow-casting sun.
     * Without it the stage is skipped rather than failing.
     */
    this.sunLight = sunLight;
    this._build();
  }

  _build() {
    const q = QUALITY[this.quality] ?? QUALITY.high;
    try {
      const scenePass = pass(this.scene, this.camera);
      scenePass.setMRT(mrt({ output, normal: transformedNormalView }));

      const colorNode = scenePass.getTextureNode('output');
      const depthNode = scenePass.getTextureNode('depth');
      const normalNode = scenePass.getTextureNode('normal');

      let node = colorNode;

      if (q.ao) {
        const aoPass = ao(depthNode, normalNode, this.camera);
        aoPass.resolutionScale = 0.75;
        aoPass.distanceExponent.value = 1.6;
        aoPass.radius.value = 0.5;
        aoPass.scale.value = 1.1;
        aoPass.thickness.value = 1.0;
        this.aoPass = aoPass;
        // GTAO writes occlusion to a single channel. Multiplying the whole RGBA by it
        // zeroes green and blue and turns the entire frame red - take the scalar.
        node = node.mul(aoPass.getTextureNode().r);
      }

      /*
       * Godrays: a screen-space raymarch through the sun's shadow map, so the shafts are
       * cast by the same geometry that casts the ground shadows - light spilling between
       * two towers actually lines up with the gap between them.
       *
       * Two consequences of that shadow-map dependency are worth knowing. It only works
       * at all when the sun is above the horizon, so the stage is faded out at night
       * rather than left to raymarch a map full of nothing. And the shafts stop where the
       * shadow frustum does - a 150 m follow box - which is fine, because that is the
       * only range at which you would see them anyway.
       *
       * Blurred before compositing (the raymarch is noisy by construction) and blended
       * depth-aware, which stops the shafts leaking across silhouette edges.
       */
      if (q.godrays && this.sunLight) {
        const godraysPass = godrays(depthNode, this.camera, this.sunLight);
        godraysPass.resolutionScale = q.godraysScale;
        godraysPass.raymarchSteps.value = q.godraysSteps;
        godraysPass.density.value = 0.42;
        godraysPass.maxDensity.value = 0.24;
        godraysPass.distanceAttenuation.value = 2.4;
        this.godraysPass = godraysPass;

        /*
         * `depthAwareBlend` samples all three of its inputs at offset UVs, so every one
         * has to be a *texture* node - a bare pass or an arithmetic node has no
         * `.sample()` and the shader build dies with "blendNode.sample is not a
         * function". `getTextureNode()` on the passes, `convertToTexture` on whatever
         * the AO stage left behind.
         */
        const blurred = bilateralBlur(godraysPass.getTextureNode());
        node = depthAwareBlend(
          convertToTexture(node), blurred.getTextureNode(), depthNode, this.camera,
          { blendColor: this.sunLight.color, edgeRadius: 2, edgeStrength: 2 },
        );
      }

      if (q.bloom) {
        const bloomPass = bloom(node, q.bloomStrength, 0.45, q.bloomThreshold);
        this.bloomPass = bloomPass;
        node = node.add(bloomPass);
      }

      if (q.smaa) node = smaa(node);

      this.post = new PostProcessing(this.renderer);
      this.post.outputNode = node;
      this.enabled = true;
    } catch (err) {
      console.warn('[PostFX] disabled - node pipeline failed to build:', err);
      this.enabled = false;
      this.post = null;
    }
  }

  setQuality(quality) {
    if (quality === this.quality) return;
    this.quality = quality;
    this.post?.dispose?.();
    this._build();
  }

  /**
   * Fade the godray stage with the sun. Below the horizon the shadow map holds nothing
   * to march through, and the shafts degenerate into a flat wash of moonlight colour.
   * @param {number} above 0-1, how far the sun is above the horizon
   */
  setSunElevation(above) {
    if (!this.godraysPass) return;
    this.godraysPass.density.value = 0.42 * Math.max(0, above);
  }

  /** Render one frame. Returns true if the post chain drew, false if the caller must. */
  render() {
    if (!this.enabled || !this.post) return false;
    try {
      this.post.render();
      return true;
    } catch (err) {
      console.warn('[PostFX] runtime failure, falling back to direct render:', err);
      this.enabled = false;
      return false;
    }
  }

  dispose() {
    this.post?.dispose?.();
  }
}
