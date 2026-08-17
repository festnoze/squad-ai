/**
 * RESONANCE - wave surface.
 *
 * A 24x24 world-unit plane with one vertex per simulation cell (96x96). The
 * vertex shader reads a float DataTexture holding the three band fields
 * (RGB) plus a layout flag (A: 1 wall, 0.5 foam), displaces vertically and
 * hands the fragment shader per-band amplitudes. Vertices align 1:1 with
 * texels, so NearestFilter sampling is exact and float filtering support is
 * never needed.
 *
 * The fragment shader ends with the tonemapping/colorspace chunks: without
 * them a custom material renders darker and flatter than the lit meshes
 * around it (trap already hit in this repo).
 */

import * as THREE from 'three';
import { SIM_N } from '../wave.js';
import { BOARD_N } from '../board.js';

export const BAND_COLORS = [
  new THREE.Color(1.0, 0.58, 0.22),  // grave: amber
  new THREE.Color(0.16, 0.92, 0.78), // medium: turquoise
  new THREE.Color(0.55, 0.42, 1.0),  // aigu: blue violet
];

const VERT = /* glsl */ `
uniform sampler2D uField;
uniform float uHeight;
varying vec3 vAmp;
varying float vFlag;
varying vec2 vUv;
varying vec3 vNormal2;

float heightOf(vec4 s) {
  return s.a > 0.9 ? 0.0 : (s.r + s.g + s.b);
}

void main() {
  vec4 s = texture2D(uField, uv);
  vAmp = s.rgb;
  vFlag = s.a;
  vUv = uv;
  float px = 1.0 / ${SIM_N}.0;
  float h = heightOf(s) * uHeight;
  float hx = heightOf(texture2D(uField, uv + vec2(px, 0.0))) * uHeight;
  float hy = heightOf(texture2D(uField, uv + vec2(0.0, px))) * uHeight;
  // Cheap finite-difference normal in surface-local space (plane is XY).
  float cell = ${(BOARD_N / SIM_N).toFixed(4)};
  vNormal2 = normalize(vec3(h - hx, h - hy, cell * 2.0));
  vec3 pos = position;
  pos.z += h;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}
`;

const FRAG = /* glsl */ `
uniform vec3 uBandA;
uniform vec3 uBandB;
uniform vec3 uBandC;
uniform vec3 uLightDir;
varying vec3 vAmp;
varying float vFlag;
varying vec2 vUv;
varying vec3 vNormal2;

void main() {
  // Velvet-dark resting water; antinodes glow in their band's colour.
  vec3 base = vec3(0.024, 0.026, 0.046);
  float diff = max(dot(normalize(vNormal2), normalize(uLightDir)), 0.0);
  vec3 col = base * (0.6 + 0.8 * diff);

  vec3 a = abs(vAmp);
  // Quadratic toe kills the faint residual hiss (which otherwise washes the
  // whole surface pastel when three bands coexist), then a soft knee keeps
  // antinodes bright with visible gradation in the ripples.
  vec3 aa = a * a / (a + 0.05);
  vec3 glow = aa / (aa + 0.35);
  // Dominance weighting: mixed zones share their brightness instead of
  // summing to white, single-band zones are untouched.
  float sum = a.r + a.g + a.b + 0.001;
  vec3 share = 0.35 + 0.65 * (a / sum);
  col += uBandA * glow.r * share.r * 1.3;
  col += uBandB * glow.g * share.g * 1.3;
  col += uBandC * glow.b * share.b * 1.3;
  // Sparkle where the summed field is extreme (crests of interference).
  float total = a.r + a.g + a.b;
  col += vec3(0.9) * pow(clamp(total * 1.4, 0.0, 1.0), 6.0) * 0.5;

  // Slot grid: a faint line every 4 cells so placement reads at a glance.
  vec2 g = abs(fract(vUv * ${BOARD_N}.0) - 0.5);
  float line = smoothstep(0.46, 0.5, max(g.x, g.y));
  col += vec3(0.030, 0.034, 0.055) * line;

  // Foam pads read matte and dead; wall texels get their own dark slate
  // (their box mesh sits on top anyway).
  if (vFlag > 0.9) col = vec3(0.035, 0.03, 0.05);
  else if (vFlag > 0.4) col = mix(col, vec3(0.030, 0.026, 0.045), 0.85);

  gl_FragColor = vec4(col, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

export function createSurface(scene) {
  const data = new Float32Array(SIM_N * SIM_N * 4);
  const texture = new THREE.DataTexture(data, SIM_N, SIM_N, THREE.RGBAFormat, THREE.FloatType);
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;

  const material = new THREE.ShaderMaterial({
    vertexShader: VERT,
    fragmentShader: FRAG,
    uniforms: {
      uField: { value: texture },
      uHeight: { value: 0.55 },
      uBandA: { value: BAND_COLORS[0] },
      uBandB: { value: BAND_COLORS[1] },
      uBandC: { value: BAND_COLORS[2] },
      uLightDir: { value: new THREE.Vector3(0.4, 0.5, 0.75) },
    },
  });

  // SIM_N - 1 segments give exactly SIM_N vertices per side, one per texel.
  const geometry = new THREE.PlaneGeometry(BOARD_N, BOARD_N, SIM_N - 1, SIM_N - 1);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.frustumCulled = false;
  scene.add(mesh);

  /** Bake wall/foam flags into the alpha channel; call on level load. */
  function setLayout(wave) {
    for (let i = 0; i < SIM_N * SIM_N; i++) {
      data[i * 4 + 3] = wave.wall[i] ? 1.0 : (wave.damp[i] < 0.98 ? 0.5 : 0.0);
    }
    texture.needsUpdate = true;
  }

  /** Copy the three fields into the texture; call once per rendered frame. */
  function update(wave) {
    const f0 = wave.fields[0].cur;
    const f1 = wave.fields[1].cur;
    const f2 = wave.fields[2].cur;
    for (let i = 0; i < SIM_N * SIM_N; i++) {
      const j = i * 4;
      data[j] = f0[i];
      data[j + 1] = f1[i];
      data[j + 2] = f2[i];
    }
    texture.needsUpdate = true;
  }

  function dispose() {
    scene.remove(mesh);
    geometry.dispose();
    material.dispose();
    texture.dispose();
  }

  return { mesh, setLayout, update, dispose };
}
