/**
 * PRISMA - the beam itself, plus the dust it lights up.
 *
 * Two InstancedMesh (a tight emissive core and a wide additive halo) draw every
 * segment in two calls whatever the puzzle does. The dust is a single Points
 * cloud whose vertex shader samples a tiny board sized texture holding the beam
 * colour per cell, so motes flare up exactly where a beam passes without the CPU
 * touching a single particle.
 */

import * as THREE from 'three';
import { DX, DY, cellToWorldX, cellToWorldZ } from '../grid.js';
import { maskToColor } from './pieces.js';

const MAX_SEGMENTS = 2400;
const BEAM_Y = 0.42;
// Exactly one cell: segments tile perfectly, and any overlap would show up as a
// regular ladder of bright ticks under additive blending.
const SEG_OVERLAP = 1;
const TEX_SIZE = 16;
const DUST_COUNT = 1100;

// Scratch objects at module level: reused by setSegments, never nested.
const _mat = new THREE.Matrix4();
const _pos = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _color = new THREE.Color();

const _qAxisX = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -Math.PI / 2);
const _qAxisZ = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);

const DUST_VERT = `
uniform float uTime;
uniform sampler2D uBeam;
uniform vec2 uGrid;
uniform float uTexSize;
uniform float uScale;
attribute float aSeed;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec3 p = position;
  p.y += sin(uTime * 0.35 + aSeed * 17.0) * 0.13;
  p.x += sin(uTime * 0.21 + aSeed * 31.0) * 0.10;
  p.z += cos(uTime * 0.26 + aSeed * 11.0) * 0.10;
  vec2 g = vec2(p.x + (uGrid.x - 1.0) * 0.5, p.z + (uGrid.y - 1.0) * 0.5);
  vec2 cell = clamp(floor(g + 0.5), vec2(0.0), uGrid - vec2(1.0));
  vec4 b = texture2D(uBeam, (cell + 0.5) / uTexSize);
  float near = b.a * smoothstep(1.4, 0.15, abs(p.y - 0.42));
  float tw = 0.45 + 0.55 * sin(uTime * 2.1 + aSeed * 53.0);
  vColor = mix(vec3(0.42, 0.48, 0.82), b.rgb * 1.5, near);
  vAlpha = (0.05 + 0.08 * tw) + near * 0.5;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  // The leading factor is a radius in metres, not a pixel count. Without it a
  // mote spanned a whole grid cell and 1100 additive blobs whited out the board.
  float size = (0.026 + near * 0.07) * uScale / max(0.001, -mv.z);
  gl_PointSize = clamp(size, 1.0, 40.0);
  gl_Position = projectionMatrix * mv;
}
`;

const DUST_FRAG = `
precision mediump float;
uniform sampler2D uSprite;
varying vec3 vColor;
varying float vAlpha;
void main() {
  float a = texture2D(uSprite, gl_PointCoord).a;
  gl_FragColor = vec4(vColor * a * vAlpha, 1.0);
}
`;

export function createBeamFX(scene, textures) {
  const coreGeo = new THREE.CylinderGeometry(1, 1, 1, 7, 1, true);
  const haloGeo = new THREE.CylinderGeometry(1, 1, 1, 7, 1, true);

  const coreMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    toneMapped: false,
    transparent: true,
    opacity: 0.95,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });
  const haloMat = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    toneMapped: false,
    transparent: true,
    opacity: 0.15,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  const core = new THREE.InstancedMesh(coreGeo, coreMat, MAX_SEGMENTS);
  const halo = new THREE.InstancedMesh(haloGeo, haloMat, MAX_SEGMENTS);
  for (const m of [core, halo]) {
    m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    m.frustumCulled = false;
    m.count = 0;
    m.renderOrder = 5;
    scene.add(m);
  }
  halo.renderOrder = 4;

  // Board sized beam map consumed by the dust shader.
  const beamData = new Uint8Array(TEX_SIZE * TEX_SIZE * 4);
  const beamTex = new THREE.DataTexture(beamData, TEX_SIZE, TEX_SIZE, THREE.RGBAFormat);
  beamTex.magFilter = THREE.NearestFilter;
  beamTex.minFilter = THREE.NearestFilter;
  beamTex.needsUpdate = true;

  const dustGeo = new THREE.BufferGeometry();
  const dustPos = new Float32Array(DUST_COUNT * 3);
  const dustSeed = new Float32Array(DUST_COUNT);
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3));
  dustGeo.setAttribute('aSeed', new THREE.BufferAttribute(dustSeed, 1));

  const dustMat = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uBeam: { value: beamTex },
      uSprite: { value: textures.glow },
      uGrid: { value: new THREE.Vector2(8, 8) },
      uTexSize: { value: TEX_SIZE },
      uScale: { value: 400 },
    },
    vertexShader: DUST_VERT,
    fragmentShader: DUST_FRAG,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const dust = new THREE.Points(dustGeo, dustMat);
  dust.frustumCulled = false;
  dust.renderOrder = 3;
  scene.add(dust);

  let grid = null;
  let time = 0;

  /** Rebuilds the dust volume around a new board. Level load only. */
  function setGrid(nextGrid) {
    grid = nextGrid;
    dustMat.uniforms.uGrid.value.set(grid.w, grid.h);
    const spanX = grid.w + 1.5;
    const spanZ = grid.h + 1.5;
    for (let i = 0; i < DUST_COUNT; i++) {
      dustPos[i * 3] = (Math.random() - 0.5) * spanX;
      dustPos[i * 3 + 1] = 0.08 + Math.random() * 2.4;
      dustPos[i * 3 + 2] = (Math.random() - 0.5) * spanZ;
      dustSeed[i] = Math.random() * 6.283;
    }
    dustGeo.attributes.position.needsUpdate = true;
    dustGeo.attributes.aSeed.needsUpdate = true;
    beamData.fill(0);
    beamTex.needsUpdate = true;
    core.count = 0;
    halo.count = 0;
  }

  function setSegments(res) {
    if (!grid) return;
    const n = Math.min(res.count, MAX_SEGMENTS);

    for (let i = 0; i < n; i++) {
      const dir = res.segDir[i];
      const ax = cellToWorldX(grid, res.segX[i]);
      const az = cellToWorldZ(grid, res.segY[i]);
      const bx = cellToWorldX(grid, res.segX[i] + DX[dir]);
      const bz = cellToWorldZ(grid, res.segY[i] + DY[dir]);
      const intensity = res.segInt[i];

      _pos.set((ax + bx) * 0.5, BEAM_Y, (az + bz) * 0.5);
      _quat.copy(dir === 0 || dir === 2 ? _qAxisX : _qAxisZ);
      maskToColor(res.segMask[i], _color);

      const rCore = 0.028 + 0.026 * intensity;
      _scale.set(rCore, SEG_OVERLAP, rCore);
      _mat.compose(_pos, _quat, _scale);
      core.setMatrixAt(i, _mat);
      core.setColorAt(i, _color);

      const rHalo = 0.05 + 0.07 * intensity;
      _scale.set(rHalo, SEG_OVERLAP, rHalo);
      _mat.compose(_pos, _quat, _scale);
      halo.setMatrixAt(i, _mat);
      _color.multiplyScalar(0.35 + 0.65 * intensity);
      halo.setColorAt(i, _color);
    }

    core.count = n;
    halo.count = n;
    core.instanceMatrix.needsUpdate = true;
    halo.instanceMatrix.needsUpdate = true;
    if (core.instanceColor) core.instanceColor.needsUpdate = true;
    if (halo.instanceColor) halo.instanceColor.needsUpdate = true;

    // Board map for the dust shader.
    beamData.fill(0);
    const energy = res.cellEnergy;
    // The map is TEX_SIZE wide: a wider board would wrap onto the next row and
    // light dust in the wrong place, so it is clamped rather than aliased.
    const maxX = Math.min(grid.w, TEX_SIZE);
    const maxY = Math.min(grid.h, TEX_SIZE);
    for (let y = 0; y < maxY; y++) {
      for (let x = 0; x < maxX; x++) {
        const src = (y * grid.w + x) * 4;
        const a = energy[src + 3];
        if (a <= 0) continue;
        const dst = (y * TEX_SIZE + x) * 4;
        beamData[dst] = Math.min(255, Math.round(energy[src] * 255));
        beamData[dst + 1] = Math.min(255, Math.round(energy[src + 1] * 255));
        beamData[dst + 2] = Math.min(255, Math.round(energy[src + 2] * 255));
        beamData[dst + 3] = Math.min(255, Math.round(a * 255));
      }
    }
    beamTex.needsUpdate = true;
  }

  /** `heightPx` is the framebuffer height, so the factor is three.js' own 0.5. */
  function setPixelScale(heightPx) {
    dustMat.uniforms.uScale.value = heightPx * 0.5;
  }

  function update(dt) {
    time += dt;
    dustMat.uniforms.uTime.value = time;
    // A slow breath on the halo reads as a live beam without any per instance work.
    haloMat.opacity = 0.13 + 0.04 * Math.sin(time * 2.4);
    coreMat.opacity = 0.82 + 0.08 * Math.sin(time * 3.7);
  }

  function dispose() {
    scene.remove(core, halo, dust);
    coreGeo.dispose();
    haloGeo.dispose();
    coreMat.dispose();
    haloMat.dispose();
    dustGeo.dispose();
    dustMat.dispose();
    beamTex.dispose();
  }

  return { setGrid, setSegments, setPixelScale, update, dispose, group: core };
}
