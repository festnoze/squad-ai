/**
 * VELOCITRON - visual effects.
 *
 * Everything additive that is not part of the track or the world lives here:
 *  - one pooled THREE.Points system (2000 particles max, one draw call) used by
 *    sparks, explosions, dust and thruster embers,
 *  - a small pool of expanding shock rings (boost bursts, explosions),
 *  - per craft thruster flames (gradient cone + crossed flare quads),
 *  - per craft speed ribbons rebuilt in place every frame, camera facing.
 *
 * The scene is rendered linear with NoToneMapping into a HalfFloat target, so
 * colours above 1.0 are what feeds the bloom pass in post.js.
 *
 * Hot paths (update, emit) never allocate: every temporary is a module level
 * scratch, and no scratch is shared between two functions that can nest.
 */

import * as THREE from 'three';
import { PALETTE, SHIP } from './config.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const MAX_PARTICLES = 2000;
const TRAIL_SAMPLES = 24; // ring buffer length of a speed ribbon
const TRAIL_VERTS = TRAIL_SAMPLES * 2;
const TRAIL_MIN_STEP = 0.75; // metres between two recorded ribbon samples
const TRAIL_TELEPORT = 30; // metres, above this the ribbon is reset (respawn)
const RING_COUNT = 8;
const TAU = Math.PI * 2;

const TEX_SPARK = 0;
const TEX_SMOKE = 1;

// ---------------------------------------------------------------------------
// Palette helpers. THREE.Color converts sRGB hex to the linear working space,
// which is exactly what the HDR pipeline expects.
// ---------------------------------------------------------------------------
const _colorConv = new THREE.Color();

function linearRGB(hex, out) {
  _colorConv.setHex(hex);
  out[0] = _colorConv.r;
  out[1] = _colorConv.g;
  out[2] = _colorConv.b;
  return out;
}

const C_THRUST_CORE = linearRGB(PALETTE.thrustCore, new Float32Array(3));
const C_THRUST_TIP = linearRGB(PALETTE.thrustTip, new Float32Array(3));
const C_BOOST_CORE = linearRGB(PALETTE.boostCore, new Float32Array(3));
const C_BOOST_TIP = linearRGB(PALETTE.boostTip, new Float32Array(3));
const C_WHITE = linearRGB(PALETTE.white, new Float32Array(3));
const C_AMBER = linearRGB(PALETTE.amber, new Float32Array(3));
const C_RED = linearRGB(PALETTE.red, new Float32Array(3));
const C_CYAN = linearRGB(PALETTE.cyan, new Float32Array(3));
const C_SMOKE = linearRGB(0x2a3348, new Float32Array(3));
const C_DUST = linearRGB(0x5a6478, new Float32Array(3));

// ---------------------------------------------------------------------------
// Shaders
// ---------------------------------------------------------------------------
const PARTICLE_VERT = /* glsl */ `
attribute vec3 aColor;
attribute float aSize;
attribute float aOpacity;
attribute float aTex;
uniform float uPixelScale;
varying vec3 vColor;
varying float vOpacity;
varying float vTex;
void main() {
  vColor = aColor;
  vOpacity = aOpacity;
  vTex = aTex;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = max(0.05, -mv.z);
  gl_PointSize = clamp(aSize * uPixelScale * projectionMatrix[1][1] / dist, 0.0, 420.0);
}
`;

const PARTICLE_FRAG = /* glsl */ `
precision highp float;
uniform sampler2D uSpark;
uniform sampler2D uSmoke;
varying vec3 vColor;
varying float vOpacity;
varying float vTex;
void main() {
  vec2 uv = gl_PointCoord;
  float mask = mix(texture2D(uSpark, uv).a, texture2D(uSmoke, uv).a, vTex);
  float a = mask * vOpacity;
  if (a < 0.004) discard;
  gl_FragColor = vec4(vColor, a);
}
`;

const FLAME_VERT = /* glsl */ `
varying float vT;
void main() {
  vT = position.z;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FLAME_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uCore;
uniform vec3 uTip;
uniform float uIntensity;
uniform float uAlpha;
varying float vT;
void main() {
  float t = clamp(vT, 0.0, 1.0);
  vec3 c = mix(uCore, uTip, sqrt(t)) * uIntensity;
  float a = pow(1.0 - t, 1.6) * uAlpha;
  if (a < 0.003) discard;
  gl_FragColor = vec4(c, a);
}
`;

const RIBBON_VERT = /* glsl */ `
attribute float aAlpha;
attribute float aSide;
varying float vAlpha;
varying float vSide;
void main() {
  vAlpha = aAlpha;
  vSide = aSide;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const RIBBON_FRAG = /* glsl */ `
precision highp float;
uniform vec3 uColor;
varying float vAlpha;
varying float vSide;
void main() {
  float edge = 1.0 - vSide * vSide;
  float a = vAlpha * edge;
  if (a < 0.003) discard;
  gl_FragColor = vec4(uColor, a);
}
`;

// ---------------------------------------------------------------------------
// Emission parameters. Filled by the effect helpers right before emit(), which
// consumes them synchronously: no allocation, no nesting.
// ---------------------------------------------------------------------------
const P = {
  x: 0, y: 0, z: 0,
  vx: 0, vy: 0, vz: 0,
  life: 1,
  size0: 1, size1: 1,
  r0: 1, g0: 1, b0: 1,
  r1: 1, g1: 1, b1: 1,
  drag: 1, grav: 0,
  tex: TEX_SPARK,
  fadeIn: 0.08,
  intensity: 1,
};

// Scratch vectors. One family per function so that no two nesting calls can
// stomp on each other.
const _spN = new THREE.Vector3(); // sparks: normal
const _spR = new THREE.Vector3(); // sparks: random direction
const _exR = new THREE.Vector3(); // explode: random direction
const _duR = new THREE.Vector3(); // dust: random direction
const _bbPos = new THREE.Vector3(); // boostBurst: origin
const _bbDir = new THREE.Vector3(); // boostBurst: backward axis
const _bbQuat = new THREE.Quaternion(); // boostBurst: ring orientation
const _bbR = new THREE.Vector3(); // boostBurst: random direction
const _thPos = new THREE.Vector3(); // thrusters: nozzle world position
const _thDir = new THREE.Vector3(); // thrusters: backward axis
const _rbCam = new THREE.Vector3(); // ribbon: camera world position
const _rbPrev = new THREE.Vector3();
const _rbCur = new THREE.Vector3();
const _rbNext = new THREE.Vector3();
const _rbDir = new THREE.Vector3();
const _rbSide = new THREE.Vector3();
const _rbView = new THREE.Vector3();
const _tailPos = new THREE.Vector3(); // ribbon sampling: ship world position

const _flatQuat = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI * 0.5);

function randomUnit(out) {
  const u = Math.random() * 2 - 1;
  const phi = Math.random() * TAU;
  const s = Math.sqrt(Math.max(0, 1 - u * u));
  return out.set(s * Math.cos(phi), u, s * Math.sin(phi));
}

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

/**
 * Soft radial sprite used only when textures.js has not provided one. Alpha
 * carries the shape, the RGB stays white so additive blending stays neutral.
 */
function makeFallbackTexture(kind) {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(size, size);
  const data = img.data;
  const half = size * 0.5;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const dx = (x + 0.5 - half) / half;
      const dy = (y + 0.5 - half) / half;
      const r = Math.sqrt(dx * dx + dy * dy);
      let a = 0;
      if (kind === 'ring') {
        const d = Math.abs(r - 0.72) / 0.2;
        a = Math.max(0, 1 - d * d) * Math.max(0, 1 - Math.max(0, r - 1) * 8);
      } else if (kind === 'smoke') {
        a = Math.pow(Math.max(0, 1 - r), 1.6) * 0.75;
      } else {
        a = Math.pow(Math.max(0, 1 - r), 2.2);
      }
      const o = (y * size + x) * 4;
      data[o] = 255;
      data[o + 1] = 255;
      data[o + 2] = 255;
      data[o + 3] = Math.round(clamp(a, 0, 1) * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.needsUpdate = true;
  return tex;
}

// ---------------------------------------------------------------------------
// createFX
// ---------------------------------------------------------------------------
export function createFX(scene, textures) {
  const src = textures || {};
  const owned = []; // fallback textures created here, disposed here

  function pick(name, kind) {
    const tex = src[name];
    if (tex && tex.isTexture) return tex;
    const made = makeFallbackTexture(kind);
    owned.push(made);
    return made;
  }

  const texSpark = pick('spark', 'spark');
  const texSmoke = pick('smoke', 'smoke');
  const texFlare = pick('flare', 'spark');
  const texRing = pick('ring', 'ring');

  const group = new THREE.Group();
  group.name = 'fx';
  scene.add(group);

  // -- particle pool ---------------------------------------------------------
  const pPos = new Float32Array(MAX_PARTICLES * 3);
  const pCol = new Float32Array(MAX_PARTICLES * 3);
  const pSize = new Float32Array(MAX_PARTICLES);
  const pAlpha = new Float32Array(MAX_PARTICLES);
  const pTex = new Float32Array(MAX_PARTICLES);

  const vel = new Float32Array(MAX_PARTICLES * 3);
  const col0 = new Float32Array(MAX_PARTICLES * 3);
  const col1 = new Float32Array(MAX_PARTICLES * 3);
  const life = new Float32Array(MAX_PARTICLES);
  const lifeMax = new Float32Array(MAX_PARTICLES);
  const size0 = new Float32Array(MAX_PARTICLES);
  const size1 = new Float32Array(MAX_PARTICLES);
  const pDrag = new Float32Array(MAX_PARTICLES);
  const pGrav = new Float32Array(MAX_PARTICLES);
  const pFadeIn = new Float32Array(MAX_PARTICLES);
  const pIntensity = new Float32Array(MAX_PARTICLES);

  let cursor = 0;
  let aliveCount = 0;
  let dirtyLo = MAX_PARTICLES;
  let dirtyHi = -1;
  // Highest slot index ever written by emit() since the pool last drained, plus
  // one. updateParticles only walks that far instead of the whole pool, which
  // costs nothing when no effect is playing.
  let highWater = 0;

  const pGeo = new THREE.BufferGeometry();
  const attrPos = new THREE.BufferAttribute(pPos, 3).setUsage(THREE.DynamicDrawUsage);
  const attrCol = new THREE.BufferAttribute(pCol, 3).setUsage(THREE.DynamicDrawUsage);
  const attrSize = new THREE.BufferAttribute(pSize, 1).setUsage(THREE.DynamicDrawUsage);
  const attrAlpha = new THREE.BufferAttribute(pAlpha, 1).setUsage(THREE.DynamicDrawUsage);
  const attrTex = new THREE.BufferAttribute(pTex, 1).setUsage(THREE.DynamicDrawUsage);
  pGeo.setAttribute('position', attrPos);
  pGeo.setAttribute('aColor', attrCol);
  pGeo.setAttribute('aSize', attrSize);
  pGeo.setAttribute('aOpacity', attrAlpha);
  pGeo.setAttribute('aTex', attrTex);
  pGeo.setDrawRange(0, 0);

  const pMat = new THREE.ShaderMaterial({
    uniforms: {
      uSpark: { value: texSpark },
      uSmoke: { value: texSmoke },
      uPixelScale: { value: 400 },
    },
    vertexShader: PARTICLE_VERT,
    fragmentShader: PARTICLE_FRAG,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthTest: true,
    depthWrite: false,
  });

  const points = new THREE.Points(pGeo, pMat);
  points.frustumCulled = false;
  points.renderOrder = 4;
  group.add(points);

  // Point sprites are sized in device pixels, so the shader needs the height of
  // the drawing buffer, not of the window: the renderer can run at an adaptive
  // resolution. main.js drives it through setSize(w * pixelRatio, h * pixelRatio)
  // and, as soon as it does, the internal resize listener steps aside for good.
  let hostDrivesSize = false;

  function applyPixelScale(heightPx) {
    pMat.uniforms.uPixelScale.value = Math.max(1, heightPx) * 0.5;
  }

  /** widthPx / heightPx are physical pixels of the drawing buffer. */
  function setSize(widthPx, heightPx) {
    hostDrivesSize = true;
    applyPixelScale(heightPx);
  }

  // Fallback only, for a host that never calls setSize().
  function onResize() {
    if (hostDrivesSize) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    applyPixelScale(window.innerHeight * dpr);
  }
  onResize();
  window.addEventListener('resize', onResize);

  function markDirty(i) {
    if (i < dirtyLo) dirtyLo = i;
    if (i > dirtyHi) dirtyHi = i;
  }

  /** Recycles the oldest dead slot, or the oldest slot at all when saturated. */
  function pickSlot() {
    if (aliveCount < MAX_PARTICLES) {
      for (let k = 0; k < MAX_PARTICLES; k++) {
        const i = cursor;
        cursor = cursor + 1 === MAX_PARTICLES ? 0 : cursor + 1;
        if (life[i] <= 0) {
          aliveCount++;
          return i;
        }
      }
    }
    const i = cursor;
    cursor = cursor + 1 === MAX_PARTICLES ? 0 : cursor + 1;
    return i;
  }

  /** Spawns one particle from the shared P parameter block. */
  function emit() {
    const i = pickSlot();
    const i3 = i * 3;
    pPos[i3] = P.x;
    pPos[i3 + 1] = P.y;
    pPos[i3 + 2] = P.z;
    vel[i3] = P.vx;
    vel[i3 + 1] = P.vy;
    vel[i3 + 2] = P.vz;
    col0[i3] = P.r0;
    col0[i3 + 1] = P.g0;
    col0[i3 + 2] = P.b0;
    col1[i3] = P.r1;
    col1[i3 + 1] = P.g1;
    col1[i3 + 2] = P.b1;
    pCol[i3] = P.r0;
    pCol[i3 + 1] = P.g0;
    pCol[i3 + 2] = P.b0;
    life[i] = P.life;
    lifeMax[i] = P.life;
    size0[i] = P.size0;
    size1[i] = P.size1;
    pSize[i] = P.size0;
    pDrag[i] = P.drag;
    pGrav[i] = P.grav;
    pTex[i] = P.tex;
    pFadeIn[i] = P.fadeIn;
    pIntensity[i] = P.intensity;
    pAlpha[i] = P.fadeIn > 0 ? 0 : P.intensity;
    markDirty(i);
    if (i >= highWater) highWater = i + 1;
    // Effects can fire after update() in a frame: keep the draw range covering.
    if (i >= pGeo.drawRange.count) pGeo.setDrawRange(0, i + 1);
  }

  function updateParticles(dt) {
    let high = -1;
    for (let i = 0; i < highWater; i++) {
      let l = life[i];
      if (l <= 0) continue;
      const i3 = i * 3;
      l -= dt;
      if (l <= 0) {
        life[i] = 0;
        aliveCount--;
        pSize[i] = 0;
        pAlpha[i] = 0;
        markDirty(i);
        continue;
      }
      life[i] = l;

      const damp = Math.max(0, 1 - pDrag[i] * dt);
      vel[i3] *= damp;
      vel[i3 + 1] = vel[i3 + 1] * damp - pGrav[i] * dt;
      vel[i3 + 2] *= damp;
      pPos[i3] += vel[i3] * dt;
      pPos[i3 + 1] += vel[i3 + 1] * dt;
      pPos[i3 + 2] += vel[i3 + 2] * dt;

      const t = 1 - l / lifeMax[i];
      pSize[i] = size0[i] + (size1[i] - size0[i]) * t;
      pCol[i3] = col0[i3] + (col1[i3] - col0[i3]) * t;
      pCol[i3 + 1] = col0[i3 + 1] + (col1[i3 + 1] - col0[i3 + 1]) * t;
      pCol[i3 + 2] = col0[i3 + 2] + (col1[i3 + 2] - col0[i3 + 2]) * t;

      const fi = pFadeIn[i];
      const fade = t < fi ? t / fi : (1 - t) / Math.max(1e-3, 1 - fi);
      pAlpha[i] = fade * pIntensity[i];

      markDirty(i);
      high = i;
    }
    pGeo.setDrawRange(0, high + 1);
    // Pool drained: every slot is free, so the next burst restarts at slot 0 and
    // the watermark stays low instead of being pinned by the previous cursor.
    if (aliveCount <= 0) {
      highWater = 0;
      cursor = 0;
    }

    if (dirtyHi >= dirtyLo) {
      const start = dirtyLo;
      const count = dirtyHi - dirtyLo + 1;
      attrPos.clearUpdateRanges();
      attrPos.addUpdateRange(start * 3, count * 3);
      attrPos.needsUpdate = true;
      attrCol.clearUpdateRanges();
      attrCol.addUpdateRange(start * 3, count * 3);
      attrCol.needsUpdate = true;
      attrSize.clearUpdateRanges();
      attrSize.addUpdateRange(start, count);
      attrSize.needsUpdate = true;
      attrAlpha.clearUpdateRanges();
      attrAlpha.addUpdateRange(start, count);
      attrAlpha.needsUpdate = true;
      attrTex.clearUpdateRanges();
      attrTex.addUpdateRange(start, count);
      attrTex.needsUpdate = true;
      dirtyLo = MAX_PARTICLES;
      dirtyHi = -1;
    }
  }

  // -- shock ring pool -------------------------------------------------------
  const ringGeo = new THREE.PlaneGeometry(1, 1);
  const rings = [];
  for (let i = 0; i < RING_COUNT; i++) {
    const mat = new THREE.MeshBasicMaterial({
      map: texRing,
      color: new THREE.Color(1, 1, 1),
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
      toneMapped: false,
    });
    const mesh = new THREE.Mesh(ringGeo, mat);
    mesh.visible = false;
    mesh.frustumCulled = false;
    mesh.renderOrder = 3;
    group.add(mesh);
    rings.push({ mesh, mat, life: 0, lifeMax: 1, s0: 1, s1: 2, alpha: 1 });
  }

  function spawnRing(pos, quat, s0, s1, duration, cr, cg, cb, alpha) {
    let slot = rings[0];
    for (let i = 1; i < rings.length; i++) {
      if (rings[i].life < slot.life) slot = rings[i];
    }
    slot.life = duration;
    slot.lifeMax = duration;
    slot.s0 = s0;
    slot.s1 = s1;
    slot.alpha = alpha;
    slot.mat.color.setRGB(cr, cg, cb);
    slot.mat.opacity = alpha;
    slot.mesh.position.copy(pos);
    slot.mesh.quaternion.copy(quat);
    slot.mesh.scale.set(s0, s0, s0);
    slot.mesh.visible = true;
  }

  function updateRings(dt) {
    for (let i = 0; i < rings.length; i++) {
      const r = rings[i];
      if (r.life <= 0) continue;
      r.life -= dt;
      if (r.life <= 0) {
        r.life = 0;
        r.mesh.visible = false;
        continue;
      }
      const t = 1 - r.life / r.lifeMax;
      const eased = 1 - (1 - t) * (1 - t);
      const s = r.s0 + (r.s1 - r.s0) * eased;
      r.mesh.scale.set(s, s, s);
      const k = 1 - t;
      r.mat.opacity = k * k * r.alpha;
    }
  }

  // -- thruster geometry (shared) -------------------------------------------
  const flameGeo = new THREE.ConeGeometry(0.42, 1, 12, 1, true);
  flameGeo.rotateX(Math.PI * 0.5); // apex now points to +Z
  flameGeo.translate(0, 0, 0.5); // base at z = 0, apex at z = 1

  // Two crossed quads containing the flame axis, so the nozzle glow reads from
  // any angle without per frame billboarding.
  const glowGeo = new THREE.BufferGeometry();
  {
    const gv = new Float32Array([
      // quad in the XZ plane
      -0.5, 0, -0.25, 0.5, 0, -0.25, 0.5, 0, 0.75, -0.5, 0, 0.75,
      // quad in the YZ plane
      0, -0.5, -0.25, 0, 0.5, -0.25, 0, 0.5, 0.75, 0, -0.5, 0.75,
    ]);
    const gu = new Float32Array([0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1]);
    const gi = new Uint16Array([0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7]);
    glowGeo.setAttribute('position', new THREE.BufferAttribute(gv, 3));
    glowGeo.setAttribute('uv', new THREE.BufferAttribute(gu, 2));
    glowGeo.setIndex(new THREE.BufferAttribute(gi, 1));
  }

  // Static index buffer shared by every ribbon.
  const ribbonIndex = new Uint16Array((TRAIL_SAMPLES - 1) * 6);
  for (let k = 0; k < TRAIL_SAMPLES - 1; k++) {
    const o = k * 6;
    const v = k * 2;
    ribbonIndex[o] = v;
    ribbonIndex[o + 1] = v + 1;
    ribbonIndex[o + 2] = v + 2;
    ribbonIndex[o + 3] = v + 1;
    ribbonIndex[o + 4] = v + 3;
    ribbonIndex[o + 5] = v + 2;
  }

  // -- per ship records ------------------------------------------------------
  const records = [];

  function findRecord(ship) {
    for (let i = 0; i < records.length; i++) {
      if (records[i].ship === ship) return records[i];
    }
    return null;
  }

  function attach(ship) {
    if (!ship || !ship.mesh) return null;
    const existing = findRecord(ship);
    if (existing) return existing;

    const mesh = ship.mesh;
    let anchors = mesh.userData.thrusters;
    if (!Array.isArray(anchors) || anchors.length === 0) {
      // The craft did not expose nozzles: place two at the usual spot so the
      // flames still sit at the back of the hull.
      anchors = [];
      for (let i = 0; i < 2; i++) {
        const a = new THREE.Object3D();
        a.position.set(i === 0 ? -0.9 : 0.9, 0.32, SHIP.length * 0.42);
        mesh.add(a);
        anchors.push(a);
      }
      mesh.userData.thrusters = anchors;
    }

    const livery = new THREE.Color(ship.color !== undefined ? ship.color : PALETTE.liveries[0]);

    const flameMat = new THREE.ShaderMaterial({
      uniforms: {
        uCore: { value: new THREE.Color(C_THRUST_CORE[0], C_THRUST_CORE[1], C_THRUST_CORE[2]) },
        uTip: { value: new THREE.Color(C_THRUST_TIP[0], C_THRUST_TIP[1], C_THRUST_TIP[2]) },
        uIntensity: { value: 2 },
        uAlpha: { value: 1 },
      },
      vertexShader: FLAME_VERT,
      fragmentShader: FLAME_FRAG,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });

    const glowMat = new THREE.MeshBasicMaterial({
      map: texFlare,
      color: new THREE.Color(C_THRUST_CORE[0], C_THRUST_CORE[1], C_THRUST_CORE[2]),
      transparent: true,
      opacity: 1,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
      toneMapped: false,
    });

    const flames = [];
    const glows = [];
    for (let i = 0; i < anchors.length; i++) {
      const flame = new THREE.Mesh(flameGeo, flameMat);
      flame.frustumCulled = false;
      flame.renderOrder = 3;
      anchors[i].add(flame);
      flames.push(flame);

      const glow = new THREE.Mesh(glowGeo, glowMat);
      glow.frustumCulled = false;
      glow.renderOrder = 3;
      anchors[i].add(glow);
      glows.push(glow);
    }

    // Ribbon
    const rPos = new Float32Array(TRAIL_VERTS * 3);
    const rAlpha = new Float32Array(TRAIL_VERTS);
    const rSide = new Float32Array(TRAIL_VERTS);
    for (let i = 0; i < TRAIL_VERTS; i++) rSide[i] = i % 2 === 0 ? -1 : 1;
    const rGeo = new THREE.BufferGeometry();
    const rPosAttr = new THREE.BufferAttribute(rPos, 3).setUsage(THREE.DynamicDrawUsage);
    const rAlphaAttr = new THREE.BufferAttribute(rAlpha, 1).setUsage(THREE.DynamicDrawUsage);
    rGeo.setAttribute('position', rPosAttr);
    rGeo.setAttribute('aAlpha', rAlphaAttr);
    rGeo.setAttribute('aSide', new THREE.BufferAttribute(rSide, 1));
    rGeo.setIndex(new THREE.BufferAttribute(ribbonIndex, 1));
    rGeo.setDrawRange(0, 0);

    const rMat = new THREE.ShaderMaterial({
      uniforms: {
        // Additive: anything much above 1 saturates into a flat opaque slab
        // instead of reading as a glow.
        uColor: { value: livery.clone().multiplyScalar(0.95) },
      },
      vertexShader: RIBBON_VERT,
      fragmentShader: RIBBON_FRAG,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const ribbon = new THREE.Mesh(rGeo, rMat);
    ribbon.frustumCulled = false;
    ribbon.renderOrder = 3;
    ribbon.visible = false;
    group.add(ribbon);

    // Hull glow materials, so the boost can pulse them.
    const glowMats = Array.isArray(mesh.userData.glowMaterials) ? mesh.userData.glowMaterials : null;
    const glowBase = glowMats ? new Float32Array(glowMats.length) : null;
    if (glowMats) {
      for (let i = 0; i < glowMats.length; i++) {
        const m = glowMats[i];
        glowBase[i] = m && m.emissiveIntensity !== undefined ? m.emissiveIntensity : 1;
      }
    }

    const rec = {
      ship,
      anchors,
      flames,
      glows,
      flameMat,
      glowMat,
      ribbon,
      rGeo,
      rMat,
      rPos,
      rAlpha,
      rPosAttr,
      rAlphaAttr,
      trail: new Float32Array(TRAIL_SAMPLES * 3),
      head: 0,
      count: 0,
      glowMats,
      glowBase,
      boost01: 0,
      thrust01: 0,
      phase: Math.random() * TAU,
      emberAcc: 0,
      livery,
    };
    records.push(rec);
    return rec;
  }

  // -- effects ---------------------------------------------------------------

  function sparks(worldPos, normal, amount) {
    if (!worldPos) return;
    const power = clamp(amount === undefined ? 12 : amount, 1, 45);
    const count = Math.round(clamp(5 + power * 1.15, 5, 46));
    if (normal) _spN.copy(normal); else _spN.set(0, 1, 0);
    if (_spN.lengthSq() < 1e-6) _spN.set(0, 1, 0);
    _spN.normalize();

    for (let i = 0; i < count; i++) {
      randomUnit(_spR);
      // Bias the random direction towards the impact normal to form a cone.
      _spR.x += _spN.x * 1.15;
      _spR.y += _spN.y * 1.15;
      _spR.z += _spN.z * 1.15;
      _spR.normalize();
      const speed = (5 + Math.random() * 16) * (0.55 + power / 26);
      P.x = worldPos.x + _spR.x * 0.3;
      P.y = worldPos.y + _spR.y * 0.3;
      P.z = worldPos.z + _spR.z * 0.3;
      P.vx = _spR.x * speed;
      P.vy = _spR.y * speed + 2;
      P.vz = _spR.z * speed;
      P.life = 0.22 + Math.random() * 0.42;
      P.size0 = 0.22 + Math.random() * 0.3;
      P.size1 = 0.05;
      P.r0 = C_WHITE[0] * 3.4; P.g0 = C_WHITE[1] * 3.1; P.b0 = C_WHITE[2] * 2.4;
      P.r1 = C_AMBER[0] * 2.2; P.g1 = C_AMBER[1] * 0.7; P.b1 = C_AMBER[2] * 0.25;
      P.drag = 1.5;
      P.grav = 20;
      P.tex = TEX_SPARK;
      P.fadeIn = 0.05;
      P.intensity = 1;
      emit();
    }

    // A couple of dim embers that linger and drift away from the wall.
    const embers = Math.round(count * 0.25);
    for (let i = 0; i < embers; i++) {
      randomUnit(_spR);
      P.x = worldPos.x + _spN.x * 0.4;
      P.y = worldPos.y + _spN.y * 0.4 + 0.2;
      P.z = worldPos.z + _spN.z * 0.4;
      P.vx = _spN.x * 3 + _spR.x * 2.5;
      P.vy = 1.5 + Math.random() * 2.5;
      P.vz = _spN.z * 3 + _spR.z * 2.5;
      P.life = 0.7 + Math.random() * 0.7;
      P.size0 = 0.7;
      P.size1 = 2.6;
      P.r0 = C_AMBER[0] * 0.9; P.g0 = C_AMBER[1] * 0.5; P.b0 = C_AMBER[2] * 0.3;
      P.r1 = C_SMOKE[0] * 0.5; P.g1 = C_SMOKE[1] * 0.5; P.b1 = C_SMOKE[2] * 0.6;
      P.drag = 2.2;
      P.grav = -0.6;
      P.tex = TEX_SMOKE;
      P.fadeIn = 0.18;
      P.intensity = 0.55;
      emit();
    }
  }

  function explode(worldPos) {
    if (!worldPos) return;

    // Fast incandescent shell.
    for (let i = 0; i < 90; i++) {
      randomUnit(_exR);
      const speed = 12 + Math.random() * 36;
      P.x = worldPos.x + _exR.x * 0.5;
      P.y = worldPos.y + _exR.y * 0.5;
      P.z = worldPos.z + _exR.z * 0.5;
      P.vx = _exR.x * speed;
      P.vy = _exR.y * speed + 4;
      P.vz = _exR.z * speed;
      P.life = 0.45 + Math.random() * 0.7;
      P.size0 = 0.8 + Math.random() * 1.1;
      P.size1 = 0.18;
      P.r0 = C_WHITE[0] * 4.2; P.g0 = C_WHITE[1] * 3.6; P.b0 = C_WHITE[2] * 2.6;
      P.r1 = C_RED[0] * 2.4; P.g1 = C_RED[1] * 0.5; P.b1 = C_RED[2] * 0.2;
      P.drag = 1.25;
      P.grav = 9;
      P.tex = TEX_SPARK;
      P.fadeIn = 0.03;
      P.intensity = 1;
      emit();
    }

    // Lingering smoke.
    for (let i = 0; i < 34; i++) {
      randomUnit(_exR);
      const speed = 2 + Math.random() * 6;
      P.x = worldPos.x + _exR.x * 1.2;
      P.y = worldPos.y + _exR.y * 1.2;
      P.z = worldPos.z + _exR.z * 1.2;
      P.vx = _exR.x * speed;
      P.vy = Math.abs(_exR.y) * speed * 0.6 + 1.5;
      P.vz = _exR.z * speed;
      P.life = 1.4 + Math.random() * 1.3;
      P.size0 = 2.2 + Math.random() * 1.6;
      P.size1 = 9 + Math.random() * 3;
      P.r0 = C_AMBER[0] * 0.8; P.g0 = C_AMBER[1] * 0.35; P.b0 = C_AMBER[2] * 0.2;
      P.r1 = C_SMOKE[0] * 0.4; P.g1 = C_SMOKE[1] * 0.45; P.b1 = C_SMOKE[2] * 0.6;
      P.drag = 1.6;
      P.grav = -1.2;
      P.tex = TEX_SMOKE;
      P.fadeIn = 0.22;
      P.intensity = 0.7;
      emit();
    }

    spawnRing(worldPos, _flatQuat, 2, 26, 0.55, C_AMBER[0] * 2.6, C_AMBER[1] * 1.6, C_AMBER[2] * 0.8, 1);
  }

  function dust(worldPos, amount) {
    if (!worldPos) return;
    const power = clamp(amount === undefined ? 8 : amount, 1, 30);
    const count = Math.round(clamp(4 + power * 0.9, 4, 26));
    for (let i = 0; i < count; i++) {
      randomUnit(_duR);
      const speed = 2.5 + Math.random() * 5 + power * 0.12;
      P.x = worldPos.x + _duR.x * 0.6;
      P.y = worldPos.y + 0.15;
      P.z = worldPos.z + _duR.z * 0.6;
      P.vx = _duR.x * speed;
      P.vy = 1 + Math.random() * 2.5;
      P.vz = _duR.z * speed;
      P.life = 0.55 + Math.random() * 0.7;
      P.size0 = 0.8 + Math.random() * 0.6;
      P.size1 = 3 + Math.random() * 1.6;
      P.r0 = C_DUST[0] * 1.5; P.g0 = C_DUST[1] * 1.6; P.b0 = C_DUST[2] * 1.9;
      P.r1 = C_DUST[0] * 0.3; P.g1 = C_DUST[1] * 0.35; P.b1 = C_DUST[2] * 0.5;
      P.drag = 2.6;
      P.grav = 3;
      P.tex = TEX_SMOKE;
      P.fadeIn = 0.14;
      P.intensity = 0.8;
      emit();
    }
    // A few bright chips kicked up by the landing.
    const chips = Math.round(count * 0.4);
    for (let i = 0; i < chips; i++) {
      randomUnit(_duR);
      P.x = worldPos.x;
      P.y = worldPos.y + 0.1;
      P.z = worldPos.z;
      P.vx = _duR.x * (4 + Math.random() * 8);
      P.vy = 3 + Math.random() * 6;
      P.vz = _duR.z * (4 + Math.random() * 8);
      P.life = 0.25 + Math.random() * 0.3;
      P.size0 = 0.2;
      P.size1 = 0.05;
      P.r0 = C_CYAN[0] * 2.4; P.g0 = C_CYAN[1] * 2.4; P.b0 = C_CYAN[2] * 2.6;
      P.r1 = C_CYAN[0] * 0.6; P.g1 = C_CYAN[1] * 0.6; P.b1 = C_CYAN[2] * 0.8;
      P.drag = 1.4;
      P.grav = 22;
      P.tex = TEX_SPARK;
      P.fadeIn = 0.04;
      P.intensity = 1;
      emit();
    }
  }

  function boostBurst(ship) {
    if (!ship || !ship.mesh) return;
    const mesh = ship.mesh;
    _bbQuat.copy(mesh.quaternion);
    _bbDir.set(0, 0, 1).applyQuaternion(_bbQuat); // craft nose is -Z, so +Z is backward
    _bbPos.copy(mesh.position).addScaledVector(_bbDir, SHIP.length * 0.35);

    const rec = findRecord(ship);
    const lr = rec ? rec.livery : _colorConv.setHex(ship.color !== undefined ? ship.color : PALETTE.liveries[0]);
    spawnRing(_bbPos, _bbQuat, 1.6, 11, 0.4, lr.r * 2.8 + 0.6, lr.g * 2.8 + 0.5, lr.b * 2.8 + 0.4, 1);

    // Backward plume of hot gas.
    for (let i = 0; i < 26; i++) {
      randomUnit(_bbR);
      const spread = 2.2;
      P.x = _bbPos.x + _bbR.x * spread;
      P.y = _bbPos.y + _bbR.y * spread * 0.5;
      P.z = _bbPos.z + _bbR.z * spread;
      const back = 14 + Math.random() * 22;
      P.vx = _bbDir.x * back + _bbR.x * 3;
      P.vy = _bbDir.y * back + _bbR.y * 3;
      P.vz = _bbDir.z * back + _bbR.z * 3;
      P.life = 0.3 + Math.random() * 0.45;
      P.size0 = 0.9 + Math.random() * 0.8;
      P.size1 = 2.6;
      P.r0 = C_BOOST_CORE[0] * 3.2; P.g0 = C_BOOST_CORE[1] * 2.8; P.b0 = C_BOOST_CORE[2] * 2;
      P.r1 = C_BOOST_TIP[0] * 1.2; P.g1 = C_BOOST_TIP[1] * 0.5; P.b1 = C_BOOST_TIP[2] * 0.2;
      P.drag = 2.4;
      P.grav = -1;
      P.tex = TEX_SPARK;
      P.fadeIn = 0.06;
      P.intensity = 0.9;
      emit();
    }
    if (rec) rec.boost01 = 1;
  }

  // -- thrusters -------------------------------------------------------------
  function updateThrusters(rec, dt, time) {
    const ship = rec.ship;
    const boosting = (ship.boostTimer > 0 || ship.padBoostTimer > 0) ? 1 : 0;
    const rate = boosting ? 12 : 4;
    rec.boost01 += (boosting - rec.boost01) * Math.min(1, rate * dt);

    const speed01 = clamp(Math.abs(ship.speed || 0) / SHIP.maxSpeed, 0, 1.4);
    // No controls object reaches fx.update, so throttle is inferred from speed.
    const target = ship.destroyed ? 0 : clamp(0.28 + speed01 * 0.85, 0, 1.25);
    rec.thrust01 += (target - rec.thrust01) * Math.min(1, 9 * dt);

    const visible = !ship.destroyed && rec.thrust01 > 0.02;
    const flicker = 0.86 + 0.09 * Math.sin(time * 47 + rec.phase) + 0.05 * Math.sin(time * 113 + rec.phase * 2.3);
    const boost = rec.boost01;
    const len = (0.9 + rec.thrust01 * 1.25 + boost * 2.6) * flicker;
    const rad = (0.85 + rec.thrust01 * 0.35 + boost * 0.45) * (0.94 + 0.06 * flicker);

    for (let i = 0; i < rec.flames.length; i++) {
      const f = rec.flames[i];
      f.visible = visible;
      f.scale.set(rad, rad, len);
      const g = rec.glows[i];
      g.visible = visible;
      const gs = 0.72 + rec.thrust01 * 0.5 + boost * 1.1;
      g.scale.set(gs, gs, gs * (1 + boost * 0.6));
    }

    const core = rec.flameMat.uniforms.uCore.value;
    const tip = rec.flameMat.uniforms.uTip.value;
    core.setRGB(
      C_THRUST_CORE[0] + (C_BOOST_CORE[0] - C_THRUST_CORE[0]) * boost,
      C_THRUST_CORE[1] + (C_BOOST_CORE[1] - C_THRUST_CORE[1]) * boost,
      C_THRUST_CORE[2] + (C_BOOST_CORE[2] - C_THRUST_CORE[2]) * boost
    );
    tip.setRGB(
      C_THRUST_TIP[0] + (C_BOOST_TIP[0] - C_THRUST_TIP[0]) * boost,
      C_THRUST_TIP[1] + (C_BOOST_TIP[1] - C_THRUST_TIP[1]) * boost,
      C_THRUST_TIP[2] + (C_BOOST_TIP[2] - C_THRUST_TIP[2]) * boost
    );
    // Additive plus bloom: past roughly 1.5 the two nozzles merge into one
    // white blob and the craft stops reading as a shape.
    rec.flameMat.uniforms.uIntensity.value = (0.85 + rec.thrust01 * 0.6 + boost * 1.7) * flicker;
    rec.flameMat.uniforms.uAlpha.value = clamp(0.45 + rec.thrust01 * 0.35, 0, 1);

    rec.glowMat.color.copy(core).multiplyScalar(0.7 + boost * 1.0);
    rec.glowMat.opacity = clamp((0.24 + rec.thrust01 * 0.26 + boost * 0.4) * flicker, 0, 1);

    // Hull emissive pulse during boost.
    if (rec.glowMats) {
      const pulse = 1 + boost * (1.1 + 0.35 * Math.sin(time * 26 + rec.phase)) + speed01 * 0.25;
      for (let i = 0; i < rec.glowMats.length; i++) {
        const m = rec.glowMats[i];
        if (m && m.emissiveIntensity !== undefined) m.emissiveIntensity = rec.glowBase[i] * pulse;
      }
    }

    // Embers spat out of the nozzles when pushing hard.
    if (visible && rec.flames.length > 0) {
      const emitRate = boost * 34 + Math.max(0, speed01 - 0.55) * 26;
      rec.emberAcc += emitRate * dt;
      let guard = 0;
      while (rec.emberAcc >= 1 && guard < 8) {
        rec.emberAcc -= 1;
        guard++;
        const anchor = rec.anchors[(Math.random() * rec.anchors.length) | 0];
        anchor.getWorldPosition(_thPos);
        _thDir.set(0, 0, 1).applyQuaternion(ship.mesh.quaternion);
        P.x = _thPos.x;
        P.y = _thPos.y;
        P.z = _thPos.z;
        const back = 6 + Math.random() * 14 + boost * 16;
        P.vx = _thDir.x * back + (Math.random() - 0.5) * 3;
        P.vy = _thDir.y * back + (Math.random() - 0.5) * 3;
        P.vz = _thDir.z * back + (Math.random() - 0.5) * 3;
        P.life = 0.18 + Math.random() * 0.3;
        P.size0 = 0.35 + boost * 0.4;
        P.size1 = 1.4;
        P.r0 = core.r * 2.6; P.g0 = core.g * 2.6; P.b0 = core.b * 2.6;
        P.r1 = tip.r * 0.8; P.g1 = tip.g * 0.8; P.b1 = tip.b * 0.8;
        P.drag = 3;
        P.grav = -0.5;
        P.tex = TEX_SPARK;
        P.fadeIn = 0.06;
        P.intensity = 0.8;
        emit();
      }
    } else {
      rec.emberAcc = 0;
    }
  }

  // -- ribbons ---------------------------------------------------------------
  function sampleTrail(rec) {
    const ship = rec.ship;
    const mesh = ship.mesh;
    _tailPos.set(0, 0, SHIP.length * 0.45).applyQuaternion(mesh.quaternion).add(mesh.position);
    const trail = rec.trail;

    if (rec.count === 0) {
      rec.head = 0;
      trail[0] = _tailPos.x;
      trail[1] = _tailPos.y;
      trail[2] = _tailPos.z;
      rec.count = 1;
      return;
    }

    const h3 = rec.head * 3;
    const dx = _tailPos.x - trail[h3];
    const dy = _tailPos.y - trail[h3 + 1];
    const dz = _tailPos.z - trail[h3 + 2];
    const d2 = dx * dx + dy * dy + dz * dz;

    if (d2 > TRAIL_TELEPORT * TRAIL_TELEPORT) {
      rec.count = 0;
      rec.head = 0;
      trail[0] = _tailPos.x;
      trail[1] = _tailPos.y;
      trail[2] = _tailPos.z;
      rec.count = 1;
      return;
    }

    if (d2 >= TRAIL_MIN_STEP * TRAIL_MIN_STEP) {
      rec.head = rec.head + 1 === TRAIL_SAMPLES ? 0 : rec.head + 1;
      if (rec.count < TRAIL_SAMPLES) rec.count++;
      const n3 = rec.head * 3;
      trail[n3] = _tailPos.x;
      trail[n3 + 1] = _tailPos.y;
      trail[n3 + 2] = _tailPos.z;
    } else {
      // Keep the head glued to the craft between two recorded samples.
      trail[h3] = _tailPos.x;
      trail[h3 + 1] = _tailPos.y;
      trail[h3 + 2] = _tailPos.z;
    }
  }

  function readSample(rec, k, out) {
    // k = 0 is the oldest sample, k = count - 1 the newest.
    let idx = rec.head - (rec.count - 1) + k;
    idx %= TRAIL_SAMPLES;
    if (idx < 0) idx += TRAIL_SAMPLES;
    const i3 = idx * 3;
    return out.set(rec.trail[i3], rec.trail[i3 + 1], rec.trail[i3 + 2]);
  }

  function updateRibbon(rec, camera) {
    const ship = rec.ship;
    const speed01 = clamp(Math.abs(ship.speed || 0) / SHIP.maxSpeed, 0, 1.5);
    const boosted = clamp(speed01 * 1.15 + rec.boost01 * 0.5, 0, 1.5);
    const global = clamp((boosted - 0.42) / 0.42, 0, 1) * 0.42;

    if (ship.destroyed || rec.count < 3 || global <= 0.001) {
      rec.ribbon.visible = false;
      rec.rGeo.setDrawRange(0, 0);
      return;
    }

    camera.getWorldPosition(_rbCam);
    const n = rec.count;
    const wMax = SHIP.width * (0.34 + rec.boost01 * 0.16);
    const pos = rec.rPos;
    const alpha = rec.rAlpha;

    for (let k = 0; k < n; k++) {
      readSample(rec, k, _rbCur);
      if (k > 0) readSample(rec, k - 1, _rbPrev); else _rbPrev.copy(_rbCur);
      if (k < n - 1) readSample(rec, k + 1, _rbNext); else _rbNext.copy(_rbCur);

      _rbDir.copy(_rbNext).sub(_rbPrev);
      if (_rbDir.lengthSq() < 1e-8) _rbDir.set(0, 0, 1);
      _rbDir.normalize();

      _rbView.copy(_rbCam).sub(_rbCur);
      _rbSide.crossVectors(_rbDir, _rbView);
      if (_rbSide.lengthSq() < 1e-8) _rbSide.set(1, 0, 0);
      _rbSide.normalize();

      const f = k / (n - 1); // 0 at the tail, 1 at the craft
      const w = (0.08 + (wMax - 0.08) * f * f) * 0.5;
      const v0 = k * 6;
      pos[v0] = _rbCur.x - _rbSide.x * w;
      pos[v0 + 1] = _rbCur.y - _rbSide.y * w;
      pos[v0 + 2] = _rbCur.z - _rbSide.z * w;
      pos[v0 + 3] = _rbCur.x + _rbSide.x * w;
      pos[v0 + 4] = _rbCur.y + _rbSide.y * w;
      pos[v0 + 5] = _rbCur.z + _rbSide.z * w;

      const a = f * f * f * global;
      alpha[k * 2] = a;
      alpha[k * 2 + 1] = a;
    }

    rec.rPosAttr.clearUpdateRanges();
    rec.rPosAttr.addUpdateRange(0, n * 6);
    rec.rPosAttr.needsUpdate = true;
    rec.rAlphaAttr.clearUpdateRanges();
    rec.rAlphaAttr.addUpdateRange(0, n * 2);
    rec.rAlphaAttr.needsUpdate = true;
    rec.rGeo.setDrawRange(0, (n - 1) * 6);
    rec.ribbon.visible = true;
  }

  // -- frame -----------------------------------------------------------------
  let time = 0;

  function update(dt, camera, ships) {
    const step = dt > 0 ? Math.min(dt, 1 / 20) : 0;
    time += step;

    if (step > 0) {
      updateParticles(step);
      updateRings(step);
    }

    if (!ships || !camera) return;
    for (let i = 0; i < ships.length; i++) {
      const ship = ships[i];
      if (!ship || !ship.mesh) continue;
      const rec = findRecord(ship);
      if (!rec) continue;
      if (step > 0) updateThrusters(rec, step, time);
      sampleTrail(rec);
      updateRibbon(rec, camera);
    }
  }

  /**
   * Wipes every transient effect without touching the GPU resources, so a race
   * restarted through main.js does not inherit the ribbons, particles and shock
   * rings of the previous one. Safe to call before any attach().
   */
  function reset() {
    // Particles: kill the pool and push the cleared slots once, so no stale
    // vertex survives on the GPU if the draw range grows again later.
    life.fill(0);
    pSize.fill(0);
    pAlpha.fill(0);
    aliveCount = 0;
    highWater = 0;
    cursor = 0;
    dirtyLo = 0;
    dirtyHi = MAX_PARTICLES - 1;
    pGeo.setDrawRange(0, 0);

    for (let i = 0; i < rings.length; i++) {
      const r = rings[i];
      r.life = 0;
      r.mesh.visible = false;
    }

    for (let i = 0; i < records.length; i++) {
      const rec = records[i];
      rec.count = 0;
      rec.head = 0;
      rec.boost01 = 0;
      rec.thrust01 = 0;
      rec.emberAcc = 0;
      rec.ribbon.visible = false;
      rec.rGeo.setDrawRange(0, 0);
    }

    time = 0;
  }

  function dispose() {
    window.removeEventListener('resize', onResize);

    for (let i = 0; i < records.length; i++) {
      const rec = records[i];
      for (let j = 0; j < rec.flames.length; j++) {
        if (rec.flames[j].parent) rec.flames[j].parent.remove(rec.flames[j]);
        if (rec.glows[j].parent) rec.glows[j].parent.remove(rec.glows[j]);
      }
      rec.flameMat.dispose();
      rec.glowMat.dispose();
      group.remove(rec.ribbon);
      rec.rGeo.dispose();
      rec.rMat.dispose();
    }
    records.length = 0;

    for (let i = 0; i < rings.length; i++) {
      group.remove(rings[i].mesh);
      rings[i].mat.dispose();
    }
    rings.length = 0;

    group.remove(points);
    pGeo.dispose();
    pMat.dispose();
    ringGeo.dispose();
    flameGeo.dispose();
    glowGeo.dispose();

    for (let i = 0; i < owned.length; i++) owned[i].dispose();
    owned.length = 0;

    if (group.parent) group.parent.remove(group);
  }

  return {
    group,
    points,
    attach,
    update,
    sparks,
    explode,
    boostBurst,
    dust,
    setSize,
    reset,
    dispose,
    get particleCount() {
      return aliveCount;
    },
  };
}
