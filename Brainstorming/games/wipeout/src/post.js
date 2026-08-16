/**
 * VELOCITRON - hand rolled post processing stack.
 *
 * No addons at all (the three.js example modules are not vendored here), so the
 * whole chain is built from plain WebGLRenderTargets, one full screen triangle
 * and a handful of ShaderMaterials.
 *
 * Pipeline
 *   1. the scene is rendered into `sceneRT` (HalfFloat, linear, no tonemapping),
 *   2. a bright pass with a soft knee extracts the neon into a half res target,
 *   3. a "dual filter" chain downsamples that target `bloomLevels` times with a
 *      13 tap kernel, then upsamples back with a 9 tap tent filter, adding each
 *      level into the one above (wide, smooth and cheap bloom),
 *   4. one final full screen pass composites scene + bloom, applies the speed
 *      radial blur, chromatic aberration, vignette, animated grain, ACES
 *      tonemapping and a manual linear -> sRGB conversion.
 *
 * None of the custom shaders include <tonemapping_fragment> or
 * <colorspace_fragment>, so three performs no automatic conversion on them:
 * the final pass is the single place where the image becomes sRGB.
 */

import * as THREE from 'three';
import { POST } from './config.js';

// ---------------------------------------------------------------------------
// Shared GLSL
// ---------------------------------------------------------------------------

// Full screen triangle: the vertex positions are already in clip space, so the
// projection and model view matrices injected by three are simply ignored.
const VERT = /* glsl */ `
precision highp float;
varying vec2 vUv;
void main() {
  vUv = position.xy * 0.5 + 0.5;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

// Soft knee bright pass, also acting as the first (half resolution) downsample.
const FRAG_BRIGHT = /* glsl */ `
precision highp float;
uniform sampler2D tScene;
uniform vec2 uTexel;
uniform float uThreshold;
varying vec2 vUv;

vec3 knee(vec3 c) {
  float br = max(c.r, max(c.g, c.b));
  float k = uThreshold * 0.6 + 0.0001;
  float soft = clamp(br - uThreshold + k, 0.0, 2.0 * k);
  soft = soft * soft / (4.0 * k);
  return c * (max(soft, br - uThreshold) / max(br, 0.0001));
}

void main() {
  // Four bilinear taps around the destination texel: thresholding each tap
  // separately keeps single bright pixels (fireflies) from flickering.
  vec2 o = uTexel;
  vec3 sum = knee(texture2D(tScene, vUv + vec2(-o.x, -o.y)).rgb);
  sum += knee(texture2D(tScene, vUv + vec2(o.x, -o.y)).rgb);
  sum += knee(texture2D(tScene, vUv + vec2(-o.x, o.y)).rgb);
  sum += knee(texture2D(tScene, vUv + vec2(o.x, o.y)).rgb);
  gl_FragColor = vec4(sum * 0.25, 1.0);
}
`;

// 13 tap downsample kernel (the one popularised by Call of Duty / Unity bloom).
const FRAG_DOWN = /* glsl */ `
precision highp float;
uniform sampler2D tSrc;
uniform vec2 uTexel;
varying vec2 vUv;

void main() {
  vec2 t = uTexel;
  vec3 a = texture2D(tSrc, vUv + vec2(-2.0 * t.x, 2.0 * t.y)).rgb;
  vec3 b = texture2D(tSrc, vUv + vec2(0.0, 2.0 * t.y)).rgb;
  vec3 c = texture2D(tSrc, vUv + vec2(2.0 * t.x, 2.0 * t.y)).rgb;
  vec3 d = texture2D(tSrc, vUv + vec2(-2.0 * t.x, 0.0)).rgb;
  vec3 e = texture2D(tSrc, vUv).rgb;
  vec3 f = texture2D(tSrc, vUv + vec2(2.0 * t.x, 0.0)).rgb;
  vec3 g = texture2D(tSrc, vUv + vec2(-2.0 * t.x, -2.0 * t.y)).rgb;
  vec3 h = texture2D(tSrc, vUv + vec2(0.0, -2.0 * t.y)).rgb;
  vec3 i = texture2D(tSrc, vUv + vec2(2.0 * t.x, -2.0 * t.y)).rgb;
  vec3 j = texture2D(tSrc, vUv + vec2(-t.x, t.y)).rgb;
  vec3 k = texture2D(tSrc, vUv + vec2(t.x, t.y)).rgb;
  vec3 l = texture2D(tSrc, vUv + vec2(-t.x, -t.y)).rgb;
  vec3 m = texture2D(tSrc, vUv + vec2(t.x, -t.y)).rgb;

  vec3 col = e * 0.125;
  col += (a + c + g + i) * 0.03125;
  col += (b + d + f + h) * 0.0625;
  col += (j + k + l + m) * 0.125;
  gl_FragColor = vec4(col, 1.0);
}
`;

// 9 tap tent filter used on the way back up, blended additively.
const FRAG_UP = /* glsl */ `
precision highp float;
uniform sampler2D tSrc;
uniform vec2 uTexel;
uniform float uRadius;
varying vec2 vUv;

void main() {
  vec2 t = uTexel * uRadius;
  vec3 col = texture2D(tSrc, vUv + vec2(-t.x, t.y)).rgb;
  col += texture2D(tSrc, vUv + vec2(0.0, t.y)).rgb * 2.0;
  col += texture2D(tSrc, vUv + vec2(t.x, t.y)).rgb;
  col += texture2D(tSrc, vUv + vec2(-t.x, 0.0)).rgb * 2.0;
  col += texture2D(tSrc, vUv).rgb * 4.0;
  col += texture2D(tSrc, vUv + vec2(t.x, 0.0)).rgb * 2.0;
  col += texture2D(tSrc, vUv + vec2(-t.x, -t.y)).rgb;
  col += texture2D(tSrc, vUv + vec2(0.0, -t.y)).rgb * 2.0;
  col += texture2D(tSrc, vUv + vec2(t.x, -t.y)).rgb;
  gl_FragColor = vec4(col * 0.0625, 1.0);
}
`;

// Final composite. Everything the player actually sees is decided here.
const FRAG_FINAL = /* glsl */ `
precision highp float;

#define RADIAL_TAPS 7

uniform sampler2D tScene;
uniform sampler2D tBloom;
uniform float uAspect;
uniform float uBloom;
uniform float uExposure;
uniform float uVignette;
uniform float uGrain;
uniform float uChroma;
uniform float uRadial;
uniform float uShake;
uniform float uTime;
uniform float uSeed;
varying vec2 vUv;

float hash13(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.zyx + 31.32);
  return fract((p.x + p.y) * p.z);
}

// Radial blur toward the screen centre, with the chromatic split folded into
// the same taps so the speed smear and the fringing stay coherent.
vec3 sampleScene(vec2 uv) {
  vec2 toCentre = vec2(0.5) - uv;
  float edge = clamp(length(toCentre) * 2.0, 0.0, 1.0);
  vec2 stepUv = toCentre * (uRadial * edge / float(RADIAL_TAPS - 1));
  vec2 split = -toCentre * uChroma;

  vec3 sum = vec3(0.0);
  float total = 0.0;
  for (int i = 0; i < RADIAL_TAPS; i++) {
    float fi = float(i);
    vec2 p = uv + stepUv * fi;
    float w = 1.0 - fi / float(RADIAL_TAPS);
    sum.r += texture2D(tScene, p + split).r * w;
    sum.g += texture2D(tScene, p).g * w;
    sum.b += texture2D(tScene, p - split).b * w;
    total += w;
  }
  return sum / total;
}

vec3 acesFilm(vec3 x) {
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

vec3 linearToSRGB(vec3 c) {
  c = max(c, vec3(0.0));
  vec3 lo = c * 12.92;
  vec3 hi = 1.055 * pow(c, vec3(0.41666667)) - 0.055;
  return mix(lo, hi, step(vec3(0.0031308), c));
}

void main() {
  // Camera shake is a sub-pixel scale UV wobble, cheaper and steadier than
  // moving the camera itself.
  vec2 wobble = vec2(sin(uTime * 57.3) + sin(uTime * 31.1) * 0.5,
                     cos(uTime * 43.7) + cos(uTime * 26.3) * 0.5);
  vec2 uv = clamp(vUv + wobble * uShake * 0.004, vec2(0.0005), vec2(0.9995));

  vec3 col = sampleScene(uv);
  col += texture2D(tBloom, uv).rgb * uBloom;

  // Vignette while still in linear light, so it darkens like a real lens.
  float d = length((uv - 0.5) * vec2(uAspect, 1.0));
  col *= mix(1.0, smoothstep(1.05, 0.28, d), uVignette);

  col = acesFilm(col * uExposure);

  vec3 display = linearToSRGB(clamp(col, 0.0, 1.0));

  // Grain has to be added in display space. In linear light the sRGB curve is
  // near vertical around zero, so a tiny linear offset turns into heavy visible
  // noise over the black asphalt that covers most of this image.
  float n = hash13(vec3(gl_FragCoord.xy, uSeed * 977.0)) - 0.5;
  float luma = dot(display, vec3(0.2126, 0.7152, 0.0722));
  display += n * uGrain * (0.35 + luma * 0.65);

  gl_FragColor = vec4(clamp(display, 0.0, 1.0), 1.0);
}
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTarget(w, h, depth) {
  const rt = new THREE.WebGLRenderTarget(Math.max(1, w), Math.max(1, h), {
    format: THREE.RGBAFormat,
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    wrapS: THREE.ClampToEdgeWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
    depthBuffer: depth === true,
    stencilBuffer: false,
    generateMipmaps: false,
  });
  rt.texture.name = depth === true ? 'post.sceneRT' : 'post.bloomRT';
  rt.texture.colorSpace = THREE.NoColorSpace; // linear HDR, converted by hand
  rt.texture.generateMipmaps = false;
  return rt;
}

function makePassMaterial(fragment, uniforms) {
  return new THREE.ShaderMaterial({
    uniforms,
    vertexShader: VERT,
    fragmentShader: fragment,
    depthTest: false,
    depthWrite: false,
    transparent: false,
    lights: false,
    fog: false,
    toneMapped: false,
  });
}

// ---------------------------------------------------------------------------
// createPost
// ---------------------------------------------------------------------------

/**
 * Build the post processing chain.
 *
 * @param {THREE.WebGLRenderer} renderer
 * @param {THREE.Scene} scene
 * @param {THREE.Camera} camera
 * @returns {{ render: (dt: number) => void, setSize: (w: number, h: number) => void,
 *             params: object, dispose: () => void }}
 */
export function createPost(renderer, scene, camera) {
  // A single 3 vertex triangle covering the whole screen, shared by every pass.
  const quadGeometry = new THREE.BufferGeometry();
  quadGeometry.setAttribute(
    'position',
    new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3)
  );

  const quadCamera = new THREE.Camera();
  const quadScene = new THREE.Scene();
  const quad = new THREE.Mesh(quadGeometry, null);
  quad.frustumCulled = false;
  quadScene.add(quad);

  const brightUniforms = {
    tScene: { value: null },
    uTexel: { value: new THREE.Vector2(1 / 1920, 1 / 1080) },
    uThreshold: { value: POST.bloomThreshold },
  };
  const downUniforms = {
    tSrc: { value: null },
    uTexel: { value: new THREE.Vector2(1 / 960, 1 / 540) },
  };
  const upUniforms = {
    tSrc: { value: null },
    uTexel: { value: new THREE.Vector2(1 / 480, 1 / 270) },
    uRadius: { value: POST.bloomRadius },
  };
  const finalUniforms = {
    tScene: { value: null },
    tBloom: { value: null },
    uAspect: { value: 16 / 9 },
    uBloom: { value: POST.bloomStrength },
    uExposure: { value: POST.exposure },
    uVignette: { value: POST.vignette },
    uGrain: { value: POST.grain },
    uChroma: { value: POST.chromaBase },
    uRadial: { value: 0 },
    uShake: { value: 0 },
    uTime: { value: 0 },
    uSeed: { value: 0 },
  };

  const brightMaterial = makePassMaterial(FRAG_BRIGHT, brightUniforms);
  const downMaterial = makePassMaterial(FRAG_DOWN, downUniforms);
  const upMaterial = makePassMaterial(FRAG_UP, upUniforms);
  const finalMaterial = makePassMaterial(FRAG_FINAL, finalUniforms);
  upMaterial.blending = THREE.AdditiveBlending;
  upMaterial.transparent = true;

  /** Mutable each frame by main.js. Everything in POST plus speed and shake. */
  const params = {
    enabled: true,
    bloomThreshold: POST.bloomThreshold,
    bloomStrength: POST.bloomStrength,
    bloomRadius: POST.bloomRadius,
    bloomLevels: POST.bloomLevels, // structural, applied on the next setSize
    chromaBase: POST.chromaBase,
    chromaAtSpeed: POST.chromaAtSpeed,
    vignette: POST.vignette,
    grain: POST.grain,
    radialBlurAtSpeed: POST.radialBlurAtSpeed,
    exposure: POST.exposure,
    speed: 0, // 0..1, driven by main.js
    shake: 0, // 0..1, driven by main.js
  };

  /** @type {THREE.WebGLRenderTarget|null} */
  let sceneRT = null;
  /** @type {THREE.WebGLRenderTarget[]} */
  const bloomRT = [];
  /** Pixel size of each bloom level, kept in sync with bloomRT. */
  const bloomSize = [];

  let width = 0;
  let height = 0;
  let levels = 0; // bloom level count the current targets were built for
  let time = 0;
  let grainSeed = 0.31;

  function disposeBloomTargets() {
    for (let i = 0; i < bloomRT.length; i++) bloomRT[i].dispose();
    bloomRT.length = 0;
    bloomSize.length = 0;
  }

  /**
   * Resize every target. `w` and `h` are physical (drawing buffer) pixels.
   *
   * This is wired to the window resize event, which fires continuously while a
   * window edge is dragged. Reallocating six HalfFloat targets per event stalls
   * the driver, so an unchanged request only refreshes the cheap uniforms.
   */
  function setSize(w, h) {
    const nextWidth = Math.max(1, Math.floor(w));
    const nextHeight = Math.max(1, Math.floor(h));
    const wanted = Math.max(1, Math.min(8, Math.floor(params.bloomLevels)));

    width = nextWidth;
    height = nextHeight;
    finalUniforms.uAspect.value = width / height;
    if (camera && camera.isPerspectiveCamera) {
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    if (sceneRT && nextWidth === sceneRT.width && nextHeight === sceneRT.height && wanted === levels) {
      return;
    }
    levels = wanted;

    if (sceneRT) sceneRT.dispose();
    sceneRT = makeTarget(width, height, true);

    disposeBloomTargets();
    let lw = width;
    let lh = height;
    for (let i = 0; i < wanted; i++) {
      lw = Math.floor(lw / 2);
      lh = Math.floor(lh / 2);
      if (lw < 2 || lh < 2) break;
      bloomRT.push(makeTarget(lw, lh, false));
      bloomSize.push(lw, lh);
    }
    if (bloomRT.length === 0) {
      // Degenerate window: keep one tiny level so the composite stays valid.
      bloomRT.push(makeTarget(1, 1, false));
      bloomSize.push(1, 1);
    }
  }

  /** Render `material` full screen into `target` (null = default framebuffer). */
  function blit(material, target, additive) {
    quad.material = material;
    renderer.setRenderTarget(target);
    renderer.autoClear = additive !== true;
    renderer.render(quadScene, quadCamera);
  }

  function render(dt) {
    const step = Number.isFinite(dt) ? dt : 0;
    time = (time + step) % 1000;
    grainSeed = (grainSeed + 0.6180339887) % 1;

    const prevAutoClear = renderer.autoClear;
    const prevTarget = renderer.getRenderTarget();

    // 1 - scene into the linear HDR buffer.
    renderer.autoClear = true;
    renderer.setRenderTarget(sceneRT);
    renderer.clear();
    renderer.render(scene, camera);

    if (params.enabled === false) {
      finalUniforms.tScene.value = sceneRT.texture;
      finalUniforms.tBloom.value = bloomRT[0].texture;
      finalUniforms.uBloom.value = 0;
    } else {
      // 2 - bright pass into the half resolution level 0.
      brightUniforms.tScene.value = sceneRT.texture;
      brightUniforms.uTexel.value.set(1 / width, 1 / height);
      brightUniforms.uThreshold.value = params.bloomThreshold;
      blit(brightMaterial, bloomRT[0], false);

      // 3a - progressive downsample, 13 tap kernel.
      for (let i = 1; i < bloomRT.length; i++) {
        downUniforms.tSrc.value = bloomRT[i - 1].texture;
        downUniforms.uTexel.value.set(1 / bloomSize[(i - 1) * 2], 1 / bloomSize[(i - 1) * 2 + 1]);
        blit(downMaterial, bloomRT[i], false);
      }

      // 3b - upsample back up, 9 tap tent, accumulating additively.
      upUniforms.uRadius.value = params.bloomRadius;
      for (let i = bloomRT.length - 1; i > 0; i--) {
        upUniforms.tSrc.value = bloomRT[i].texture;
        upUniforms.uTexel.value.set(1 / bloomSize[i * 2], 1 / bloomSize[i * 2 + 1]);
        blit(upMaterial, bloomRT[i - 1], true);
      }

      finalUniforms.tScene.value = sceneRT.texture;
      finalUniforms.tBloom.value = bloomRT[0].texture;
      // Each level contributes roughly the same energy, so normalise by count.
      finalUniforms.uBloom.value = params.bloomStrength / bloomRT.length;
    }

    // 4 - composite to the screen.
    const speed = params.speed < 0 ? 0 : params.speed > 1 ? 1 : params.speed;
    const shake = params.shake < 0 ? 0 : params.shake > 1 ? 1 : params.shake;
    finalUniforms.uExposure.value = params.exposure;
    finalUniforms.uVignette.value = params.vignette;
    finalUniforms.uGrain.value = params.grain;
    finalUniforms.uChroma.value = params.chromaBase + params.chromaAtSpeed * speed;
    finalUniforms.uRadial.value = params.radialBlurAtSpeed * speed;
    finalUniforms.uShake.value = shake;
    finalUniforms.uTime.value = time;
    finalUniforms.uSeed.value = grainSeed;

    renderer.setRenderTarget(null);
    blit(finalMaterial, null, false);

    renderer.autoClear = prevAutoClear;
    renderer.setRenderTarget(prevTarget);
  }

  function dispose() {
    if (sceneRT) {
      sceneRT.dispose();
      sceneRT = null;
    }
    disposeBloomTargets();
    brightMaterial.dispose();
    downMaterial.dispose();
    upMaterial.dispose();
    finalMaterial.dispose();
    quadGeometry.dispose();
    quad.material = null;
    quadScene.remove(quad);
  }

  // Initial sizing from the renderer's current drawing buffer.
  const initial = new THREE.Vector2();
  renderer.getDrawingBufferSize(initial);
  setSize(initial.x, initial.y);

  return { render, setSize, params, dispose };
}
