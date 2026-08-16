/**
 * ABYSSE - water surface, lighting rig and ambient particles.
 *
 * This module owns everything that makes the ocean read as an ocean:
 *   1. the animated sea surface (gerstner-like undulation, silver from below)
 *   2. the whole lighting rig (sun, hemisphere ambient, depth extinction)
 *   3. caustics projected on the seabed via textured spot lights
 *   4. god rays hanging from the surface around the camera
 *   5. marine snow, bubbles and blood clouds
 *   6. exponential fog and background colour driven by depth and biome
 *
 * Contract: createWater(scene, textures, renderer) -> Water (see CONTRACTS.md).
 */

import * as THREE from 'three';
import {
  WORLD, BIOMES, BIOME_INFO, PALETTE, FX,
  clamp01, lerp, springK,
} from './config.js';

// ---------------------------------------------------------------------------
// Module level scratch (never allocate inside the frame loop)
// ---------------------------------------------------------------------------

const _v1 = new THREE.Vector3();
const _c1 = new THREE.Color();
const _c2 = new THREE.Color();
const _c3 = new THREE.Color();

const ABYSS_BLACK = new THREE.Color(0x010409);
const SKY_FOG = new THREE.Color(0xcfeef8);
const SUN_WARM = new THREE.Color(0xfff1da);
const WHITE = new THREE.Color(0xffffff);
const SUN_DIR = new THREE.Vector3(0.42, 1, 0.26).normalize();

const FALLBACK_BIOME = BIOMES.LAGOON;

/**
 * Fog colour for a given depth and biome, written into `out`.
 * Red is absorbed first, then green, then blue; past the light falloff depth
 * everything converges to near black.
 */
function fogColorInto(depth, biome, out) {
  const info = BIOME_INFO[biome] || BIOME_INFO[FALLBACK_BIOME];
  out.setHex(info.fogColor);
  const d = Math.max(0, depth);
  out.r *= Math.exp(-d * 0.016);
  out.g *= Math.exp(-d * 0.0075);
  out.b *= Math.exp(-d * 0.0042);
  const abyssT = clamp01((d - FX.lightFalloffDepth) / 50);
  if (abyssT > 0) out.lerp(ABYSS_BLACK, abyssT);
  return out;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createWater(scene, textures, renderer) {
  const group = new THREE.Group();
  group.name = 'water';
  scene.add(group);

  const disposables = [];

  // -------------------------------------------------------------------------
  // Environment map: a tiny painted equirect sky run through PMREM so the
  // surface has something silver to reflect when seen from below.
  // -------------------------------------------------------------------------

  let envRT = null;
  if (renderer) {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 32;
    const ctx2d = canvas.getContext('2d');
    const grad = ctx2d.createLinearGradient(0, 0, 0, 32);
    grad.addColorStop(0, '#f6fcff');
    grad.addColorStop(0.42, '#8fe6ff');
    grad.addColorStop(0.55, '#3fc4d8');
    grad.addColorStop(1, '#05243c');
    ctx2d.fillStyle = grad;
    ctx2d.fillRect(0, 0, 64, 32);
    const equirect = new THREE.CanvasTexture(canvas);
    equirect.mapping = THREE.EquirectangularReflectionMapping;
    equirect.colorSpace = THREE.SRGBColorSpace;
    const pmrem = new THREE.PMREMGenerator(renderer);
    envRT = pmrem.fromEquirectangular(equirect);
    equirect.dispose();
    pmrem.dispose();
    // Give the same map to every standard material in the scene. Without it,
    // anything metallic (the submarine hull, the speargun, the wreck) renders
    // as a black cutout, because a metal with nothing to reflect is black.
    // The intensity is pulled down with depth in update(), so the trench does
    // not end up lit by a sky it cannot see.
    scene.environment = envRT.texture;
    scene.environmentIntensity = 1;
  }

  // -------------------------------------------------------------------------
  // Sea surface: subdivided plane, CPU gerstner-like waves, double sided.
  // Two normal maps (normalMap + clearcoatNormalMap) scroll in different
  // directions at different scales for a layered ripple look.
  // -------------------------------------------------------------------------

  const SURFACE_SIZE = WORLD.halfSize * 2 + 240;
  const SURFACE_SEG = 110;

  const WAVES = [
    { dx: 1.0, dz: 0.3, amp: 0.5, len: 46, speed: 1.0 },
    { dx: -0.6, dz: 1.0, amp: 0.3, len: 23, speed: 1.55 },
    { dx: 0.8, dz: -0.7, amp: 0.17, len: 11, speed: 2.3 },
    { dx: -0.3, dz: -1.0, amp: 0.09, len: 6, speed: 3.1 },
  ];
  for (const w of WAVES) {
    const invLen = 1 / Math.hypot(w.dx, w.dz);
    const k = (Math.PI * 2) / w.len;
    w.kx = w.dx * invLen * k;
    w.kz = w.dz * invLen * k;
    w.w = w.speed * k * 8;
  }

  const surfaceGeo = new THREE.PlaneGeometry(SURFACE_SIZE, SURFACE_SIZE, SURFACE_SEG, SURFACE_SEG);
  surfaceGeo.rotateX(-Math.PI / 2);
  const surfPos = surfaceGeo.attributes.position;
  const surfNrm = surfaceGeo.attributes.normal;

  const normalA = textures.waterNormal.clone();
  normalA.needsUpdate = true;
  normalA.repeat.set(26, 26);
  const normalB = textures.waterNormal.clone();
  normalB.needsUpdate = true;
  normalB.repeat.set(58, 58);

  const surfaceMat = new THREE.MeshPhysicalMaterial({
    color: 0xbfe3ee,
    metalness: 0.62,
    roughness: 0.16,
    clearcoat: 1.0,
    clearcoatRoughness: 0.08,
    normalMap: normalA,
    normalScale: new THREE.Vector2(0.85, 0.85),
    clearcoatNormalMap: normalB,
    envMap: envRT ? envRT.texture : null,
    envMapIntensity: 1.55,
    transparent: true,
    opacity: 0.94,
    depthWrite: true,
    side: THREE.DoubleSide,
  });

  const surface = new THREE.Mesh(surfaceGeo, surfaceMat);
  surface.name = 'seaSurface';
  surface.renderOrder = 0;
  group.add(surface);
  disposables.push(surfaceGeo, surfaceMat, normalA, normalB);

  function updateSurface(time) {
    const pos = surfPos.array;
    const nrm = surfNrm.array;
    const w0 = WAVES[0];
    const w1 = WAVES[1];
    const w2 = WAVES[2];
    const w3 = WAVES[3];
    const t0 = time * w0.w;
    const t1 = time * w1.w;
    const t2 = time * w2.w;
    const t3 = time * w3.w;
    for (let i = 0; i < pos.length; i += 3) {
      const x = pos[i];
      const z = pos[i + 2];
      let y = 0;
      let dx = 0;
      let dz = 0;
      let ph = x * w0.kx + z * w0.kz + t0;
      let c = Math.cos(ph);
      y += w0.amp * Math.sin(ph); dx += w0.amp * w0.kx * c; dz += w0.amp * w0.kz * c;
      ph = x * w1.kx + z * w1.kz + t1;
      c = Math.cos(ph);
      y += w1.amp * Math.sin(ph); dx += w1.amp * w1.kx * c; dz += w1.amp * w1.kz * c;
      ph = x * w2.kx + z * w2.kz + t2;
      c = Math.cos(ph);
      y += w2.amp * Math.sin(ph); dx += w2.amp * w2.kx * c; dz += w2.amp * w2.kz * c;
      ph = x * w3.kx + z * w3.kz + t3;
      c = Math.cos(ph);
      y += w3.amp * Math.sin(ph); dx += w3.amp * w3.kx * c; dz += w3.amp * w3.kz * c;
      pos[i + 1] = y;
      const inv = 1 / Math.sqrt(dx * dx + dz * dz + 1);
      nrm[i] = -dx * inv;
      nrm[i + 1] = inv;
      nrm[i + 2] = -dz * inv;
    }
    surfPos.needsUpdate = true;
    surfNrm.needsUpdate = true;
  }

  // -------------------------------------------------------------------------
  // Sun disc seen through the surface: additive flare sprite along SUN_DIR.
  // -------------------------------------------------------------------------

  const flareMat = new THREE.SpriteMaterial({
    map: textures.flare,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
    depthTest: false,
    opacity: 0,
  });
  const flare = new THREE.Sprite(flareMat);
  flare.scale.set(95, 95, 1);
  flare.renderOrder = 3;
  flare.visible = false;
  group.add(flare);
  disposables.push(flareMat);

  // -------------------------------------------------------------------------
  // Lighting rig: directional sun + hemisphere ambient, both dimmed by depth.
  // -------------------------------------------------------------------------

  const sun = new THREE.DirectionalLight(SUN_WARM.getHex(), 3.0);
  sun.position.copy(SUN_DIR).multiplyScalar(260);
  group.add(sun);
  group.add(sun.target);

  const ambient = new THREE.HemisphereLight(0xbfe8f2, 0x0c2231, 0.9);
  group.add(ambient);

  // -------------------------------------------------------------------------
  // Caustics: two very wide spot lights from just above the surface, their
  // beams textured with the caustics map. Moving the light and its target in
  // small circles at different rates scrolls the projected pattern, and the
  // two layers beat against each other for the shimmer.
  // -------------------------------------------------------------------------

  function makeCausticLight(angle, intensity) {
    const light = new THREE.SpotLight(0xbfefff, intensity, 260, angle, 0.95, 0);
    light.map = textures.caustics;
    light.position.set(0, 26, 0);
    light.target.position.set(0, -140, 0);
    group.add(light);
    group.add(light.target);
    return light;
  }
  const causticA = makeCausticLight(0.85, 5.5);
  const causticB = makeCausticLight(1.2, 3.2);
  const causticBaseA = causticA.intensity;
  const causticBaseB = causticB.intensity;

  // -------------------------------------------------------------------------
  // God rays: camera facing additive planes hanging from the surface,
  // recycled inside a disc around the camera.
  // -------------------------------------------------------------------------

  const RAY_RADIUS = 55;
  const RAY_HEIGHT = 46;
  const rayGeo = new THREE.PlaneGeometry(6, RAY_HEIGHT);
  disposables.push(rayGeo);
  const raysGroup = new THREE.Group();
  raysGroup.name = 'godrays';
  group.add(raysGroup);
  const rays = [];
  for (let i = 0; i < FX.godrayCount; i++) {
    const mat = new THREE.MeshBasicMaterial({
      map: textures.godray,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      color: 0x9fd8e8,
      opacity: 0,
      side: THREE.DoubleSide,
      fog: false,
    });
    const mesh = new THREE.Mesh(rayGeo, mat);
    mesh.renderOrder = 1;
    mesh.position.set(
      (Math.random() * 2 - 1) * RAY_RADIUS,
      -RAY_HEIGHT * 0.5,
      (Math.random() * 2 - 1) * RAY_RADIUS,
    );
    mesh.scale.x = 0.7 + Math.random() * 1.7;
    raysGroup.add(mesh);
    rays.push({
      mesh,
      mat,
      phase: Math.random() * Math.PI * 2,
      speed: 0.25 + Math.random() * 0.5,
    });
    disposables.push(mat);
  }

  // -------------------------------------------------------------------------
  // Marine snow: one Points cloud wrapped around the camera.
  // -------------------------------------------------------------------------

  const MOTES = FX.motesCount;
  const MOTES_BOX = FX.motesBox;
  const MOTES_HALF = MOTES_BOX * 0.5;
  const motePositions = new Float32Array(MOTES * 3);
  const moteFall = new Float32Array(MOTES);
  const motePhase = new Float32Array(MOTES);
  const moteSway = new Float32Array(MOTES);
  const moteFreq = new Float32Array(MOTES);
  for (let i = 0; i < MOTES; i++) {
    motePositions[i * 3] = (Math.random() - 0.5) * MOTES_BOX;
    motePositions[i * 3 + 1] = (Math.random() - 0.5) * MOTES_BOX - 10;
    motePositions[i * 3 + 2] = (Math.random() - 0.5) * MOTES_BOX;
    moteFall[i] = 0.08 + Math.random() * 0.3;
    motePhase[i] = Math.random() * Math.PI * 2;
    moteSway[i] = 0.06 + Math.random() * 0.28;
    moteFreq[i] = 0.3 + Math.random() * 1.1;
  }
  const motesGeo = new THREE.BufferGeometry();
  motesGeo.setAttribute('position', new THREE.BufferAttribute(motePositions, 3));
  const motesMat = new THREE.PointsMaterial({
    size: 0.13,
    map: textures.mote,
    sizeAttenuation: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    opacity: 0.75,
  });
  const motes = new THREE.Points(motesGeo, motesMat);
  motes.frustumCulled = false;
  motes.renderOrder = 1;
  group.add(motes);
  disposables.push(motesGeo, motesMat);

  function updateMotes(dt, time, cam) {
    const p = motePositions;
    const cx = cam.x;
    const cy = cam.y;
    const cz = cam.z;
    for (let i = 0; i < MOTES; i++) {
      const i3 = i * 3;
      const s = Math.sin(time * moteFreq[i] + motePhase[i]) * moteSway[i] * dt;
      let x = p[i3] + s;
      let y = p[i3 + 1] - moteFall[i] * dt;
      let z = p[i3 + 2] + Math.cos(time * moteFreq[i] * 0.7 + motePhase[i]) * moteSway[i] * dt;
      // Wrap each axis into the box centred on the camera.
      let d = x - cx;
      d -= MOTES_BOX * Math.floor((d + MOTES_HALF) / MOTES_BOX);
      x = cx + d;
      d = y - cy;
      d -= MOTES_BOX * Math.floor((d + MOTES_HALF) / MOTES_BOX);
      y = cy + d;
      d = z - cz;
      d -= MOTES_BOX * Math.floor((d + MOTES_HALF) / MOTES_BOX);
      z = cz + d;
      p[i3] = x;
      p[i3 + 1] = y;
      p[i3 + 2] = z;
    }
    motesGeo.attributes.position.needsUpdate = true;
  }

  // -------------------------------------------------------------------------
  // Bubble pool: a single Points cloud, inactive bubbles parked far away.
  // -------------------------------------------------------------------------

  const BUBBLES = FX.bubbleCount;
  const PARKED_Y = 1e5;
  const bubblePositions = new Float32Array(BUBBLES * 3);
  const bubbleRise = new Float32Array(BUBBLES);
  const bubbleLife = new Float32Array(BUBBLES);
  const bubblePhase = new Float32Array(BUBBLES);
  const bubbleWobble = new Float32Array(BUBBLES);
  for (let i = 0; i < BUBBLES; i++) bubblePositions[i * 3 + 1] = PARKED_Y;
  let bubbleCursor = 0;

  const bubblesGeo = new THREE.BufferGeometry();
  bubblesGeo.setAttribute('position', new THREE.BufferAttribute(bubblePositions, 3));
  const bubblesMat = new THREE.PointsMaterial({
    size: 0.17,
    map: textures.bubble,
    sizeAttenuation: true,
    transparent: true,
    depthWrite: false,
    opacity: 0.9,
  });
  const bubbles = new THREE.Points(bubblesGeo, bubblesMat);
  bubbles.frustumCulled = false;
  bubbles.renderOrder = 2;
  group.add(bubbles);
  disposables.push(bubblesGeo, bubblesMat);

  function spawnBubbles(position, count, spread) {
    spread = spread || 0.2;
    for (let n = 0; n < count; n++) {
      const i = bubbleCursor;
      bubbleCursor = (bubbleCursor + 1) % BUBBLES;
      const i3 = i * 3;
      bubblePositions[i3] = position.x + (Math.random() * 2 - 1) * spread;
      bubblePositions[i3 + 1] = Math.min(-0.1, position.y + (Math.random() * 2 - 1) * spread);
      bubblePositions[i3 + 2] = position.z + (Math.random() * 2 - 1) * spread;
      bubbleRise[i] = 0.7 + Math.random() * 0.9;
      bubbleLife[i] = 14;
      bubblePhase[i] = Math.random() * Math.PI * 2;
      bubbleWobble[i] = 0.15 + Math.random() * 0.5;
    }
    bubblesGeo.attributes.position.needsUpdate = true;
  }

  function updateBubbles(dt, time) {
    let touched = false;
    for (let i = 0; i < BUBBLES; i++) {
      if (bubbleLife[i] <= 0) continue;
      const i3 = i * 3;
      bubbleLife[i] -= dt;
      bubbleRise[i] = Math.min(2.2, bubbleRise[i] + dt * 0.35);
      bubblePositions[i3] += Math.sin(time * 3.2 + bubblePhase[i]) * bubbleWobble[i] * dt;
      bubblePositions[i3 + 1] += bubbleRise[i] * dt;
      bubblePositions[i3 + 2] += Math.cos(time * 2.7 + bubblePhase[i]) * bubbleWobble[i] * dt;
      // Pop at the surface (or expire).
      if (bubblePositions[i3 + 1] >= -0.05 || bubbleLife[i] <= 0) {
        bubbleLife[i] = 0;
        bubblePositions[i3 + 1] = PARKED_Y;
      }
      touched = true;
    }
    if (touched) bubblesGeo.attributes.position.needsUpdate = true;
  }

  // -------------------------------------------------------------------------
  // Blood clouds: pooled sprites tinted PALETTE.blood, expanding and fading.
  // -------------------------------------------------------------------------

  const BLOOD_POOL = 18;
  const bloodSprites = [];
  let bloodCursor = 0;
  for (let i = 0; i < BLOOD_POOL; i++) {
    const mat = new THREE.SpriteMaterial({
      map: textures.glow,
      color: PALETTE.blood,
      transparent: true,
      depthWrite: false,
      opacity: 0,
    });
    const sprite = new THREE.Sprite(mat);
    sprite.visible = false;
    sprite.renderOrder = 2;
    group.add(sprite);
    bloodSprites.push({
      sprite,
      mat,
      life: 0,
      maxLife: 1,
      startScale: 1,
      grow: 1,
      drift: new THREE.Vector3(),
    });
    disposables.push(mat);
  }

  function spawnBlood(position, amount) {
    const n = Math.min(BLOOD_POOL, Math.max(2, Math.round(2 + amount * 0.06)));
    for (let k = 0; k < n; k++) {
      const slot = bloodSprites[bloodCursor];
      bloodCursor = (bloodCursor + 1) % BLOOD_POOL;
      slot.sprite.position.set(
        position.x + (Math.random() - 0.5) * 0.8,
        position.y + (Math.random() - 0.5) * 0.8,
        position.z + (Math.random() - 0.5) * 0.8,
      );
      slot.maxLife = 2.2 + Math.random() * 1.2;
      slot.life = slot.maxLife;
      slot.startScale = 0.6 + Math.random() * 0.9;
      slot.grow = 1.8 + Math.min(3, amount * 0.03);
      slot.drift.set(
        (Math.random() - 0.5) * 0.4,
        0.12 + Math.random() * 0.2,
        (Math.random() - 0.5) * 0.4,
      );
      slot.sprite.visible = true;
    }
  }

  function updateBlood(dt) {
    for (let i = 0; i < BLOOD_POOL; i++) {
      const slot = bloodSprites[i];
      if (slot.life <= 0) continue;
      slot.life -= dt;
      if (slot.life <= 0) {
        slot.sprite.visible = false;
        slot.mat.opacity = 0;
        continue;
      }
      const t = 1 - slot.life / slot.maxLife;
      const scale = slot.startScale + slot.grow * t;
      slot.sprite.scale.set(scale, scale, 1);
      slot.mat.opacity = 0.55 * (1 - t) * (1 - t * 0.3);
      slot.sprite.position.addScaledVector(slot.drift, dt);
    }
  }

  // -------------------------------------------------------------------------
  // Fog and background: exponential fog, smoothed every frame so biome
  // transitions and surfacing never snap.
  // -------------------------------------------------------------------------

  const startInfo = BIOME_INFO[FALLBACK_BIOME];
  scene.fog = new THREE.FogExp2(startInfo.fogColor, startInfo.fogDensity);
  const background = new THREE.Color(startInfo.fogColor);
  scene.background = background;

  // Smoothed state
  const fogCur = new THREE.Color(startInfo.fogColor);
  let densityCur = startInfo.fogDensity;
  let ambientCur = startInfo.ambient;
  let lightCur = 1;

  // -------------------------------------------------------------------------
  // Frame update
  // -------------------------------------------------------------------------

  function update(dt, ctx) {
    dt = Math.min(dt || 0, 0.1);
    const camera = ctx.camera;
    const time = ctx.time;
    const depth = Math.max(0, ctx.depth);
    const above = !!ctx.aboveWater;
    const info = BIOME_INFO[ctx.biome] || BIOME_INFO[FALLBACK_BIOME];

    // ---- targets ----------------------------------------------------------
    let targetDensity;
    let targetAmbient;
    let targetLight;
    if (above) {
      _c1.copy(SKY_FOG);
      targetDensity = 0.00045;
      targetAmbient = 1;
      targetLight = 1;
    } else {
      fogColorInto(depth, ctx.biome, _c1);
      const depthT = clamp01(depth / FX.lightFalloffDepth);
      targetDensity = info.fogDensity * lerp(0.85, 1.2, depthT);
      targetAmbient = info.ambient;
      targetLight = Math.pow(1 - depthT, 1.35);
    }

    // ---- smoothing --------------------------------------------------------
    const k = springK(2.6, dt);
    fogCur.lerp(_c1, k);
    densityCur += (targetDensity - densityCur) * k;
    ambientCur += (targetAmbient - ambientCur) * k;
    lightCur += (targetLight - lightCur) * k;

    scene.fog.color.copy(fogCur);
    scene.fog.density = densityCur;
    background.copy(fogCur);
    if (above) background.lerp(WHITE, 0.12); // bright hazy sky, no seam

    // ---- lights -----------------------------------------------------------
    let sunTarget;
    let hemiTarget;
    if (above) {
      _c2.copy(SUN_WARM);
      sunTarget = 3.1;
      hemiTarget = 0.95;
      ambient.color.setHex(0xcfeaf6);
      ambient.groundColor.setHex(0x8a7a58);
    } else {
      // Red dies first as the sun colour sinks with the camera.
      _c2.copy(SUN_WARM);
      _c2.r *= Math.exp(-depth * 0.014);
      _c2.g *= Math.exp(-depth * 0.006);
      _c2.b *= Math.exp(-depth * 0.003);
      sunTarget = 3.0 * lightCur * lerp(0.45, 1, ambientCur);
      // Underwater light is scattered in every direction, so the sky term has
      // to carry most of it. With a low hemisphere the sun alone lights only
      // the upward faces and every rock wall reads as a black cutout.
      hemiTarget = Math.max(0.05, 2.0 * lightCur * lerp(0.5, 1, ambientCur));
      _c3.copy(fogCur).lerp(WHITE, 0.35);
      ambient.color.copy(_c3);
      _c3.copy(fogCur).multiplyScalar(0.35);
      ambient.groundColor.copy(_c3);
    }
    sun.color.lerp(_c2, k);
    sun.intensity += (sunTarget - sun.intensity) * k;
    ambient.intensity += (hemiTarget - ambient.intensity) * k;

    // ---- surface ----------------------------------------------------------
    updateSurface(time);
    normalA.offset.set(time * 0.013, time * 0.019);
    normalB.offset.set(-time * 0.031, time * 0.009);
    // Slightly rougher and dimmer as daylight fades.
    surfaceMat.envMapIntensity = lerp(0.35, 1.55, Math.max(lightCur, above ? 1 : 0));
    // Reflections fade with the light, but never all the way to zero: a small
    // floor keeps metal readable under the dive lamp instead of pure black.
    scene.environmentIntensity = above ? 1 : lerp(0.028, 0.95, lightCur * ambientCur);

    // ---- sun flare through the surface -------------------------------------
    if (!above) {
      flare.visible = true;
      _v1.copy(SUN_DIR).multiplyScalar(240).add(camera.position);
      flare.position.copy(_v1);
      flareMat.opacity = 0.85 * Math.pow(1 - clamp01(depth / (FX.lightFalloffDepth * 0.8)), 1.3);
      const pulse = 95 * (1 + Math.sin(time * 0.8) * 0.04);
      flare.scale.set(pulse, pulse, 1);
    } else {
      flare.visible = false;
    }

    // ---- caustics ----------------------------------------------------------
    const causticFade = above
      ? 0
      : Math.pow(1 - clamp01(depth / FX.lightFalloffDepth), 1.5) * lerp(0.3, 1, ambientCur);
    const cs = FX.causticSpeed * 40;
    causticA.position.set(
      camera.position.x + Math.cos(time * cs * 0.16) * 7,
      26,
      camera.position.z + Math.sin(time * cs * 0.16) * 7,
    );
    causticA.target.position.set(
      camera.position.x + Math.cos(time * cs * 0.11 + 2.1) * 5,
      -140,
      camera.position.z + Math.sin(time * cs * 0.11 + 2.1) * 5,
    );
    causticA.intensity = causticBaseA * causticFade * (0.85 + 0.15 * Math.sin(time * 3.1));
    causticB.position.set(
      camera.position.x + Math.cos(time * cs * 0.23 + 4.0) * 9,
      24,
      camera.position.z + Math.sin(time * cs * 0.23 + 4.0) * 9,
    );
    causticB.target.position.set(
      camera.position.x + Math.sin(time * cs * 0.14 + 1.2) * 6,
      -140,
      camera.position.z + Math.cos(time * cs * 0.14 + 1.2) * 6,
    );
    causticB.intensity = causticBaseB * causticFade * (0.85 + 0.15 * Math.sin(time * 2.3 + 1.5));

    // ---- god rays -----------------------------------------------------------
    const rayFade = above
      ? 0
      : Math.pow(1 - clamp01(depth / (FX.lightFalloffDepth * 0.7)), 1.6) * 0.5;
    raysGroup.visible = rayFade > 0.012;
    if (raysGroup.visible) {
      for (let i = 0; i < rays.length; i++) {
        const r = rays[i];
        const m = r.mesh;
        // Recycle inside a square around the camera.
        let d = m.position.x - camera.position.x;
        d -= RAY_RADIUS * 2 * Math.floor((d + RAY_RADIUS) / (RAY_RADIUS * 2));
        m.position.x = camera.position.x + d;
        d = m.position.z - camera.position.z;
        d -= RAY_RADIUS * 2 * Math.floor((d + RAY_RADIUS) / (RAY_RADIUS * 2));
        m.position.z = camera.position.z + d;
        m.position.y = -RAY_HEIGHT * 0.5 + Math.sin(time * 0.3 + r.phase) * 1.6;
        m.rotation.y = Math.atan2(
          camera.position.x - m.position.x,
          camera.position.z - m.position.z,
        );
        r.mat.opacity = Math.max(0, rayFade * (0.4 + 0.38 * Math.sin(time * r.speed + r.phase)));
      }
    }

    // ---- particles ----------------------------------------------------------
    motes.visible = !above;
    if (!above) {
      updateMotes(dt, time, camera.position);
      // Tinted by the current fog colour so the abyss snow stays dim.
      motesMat.color.copy(fogCur).lerp(WHITE, 0.45);
    }
    updateBubbles(dt, time);
    updateBlood(dt);
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  function fogColorAt(depth, biome) {
    return fogColorInto(depth, biome, new THREE.Color());
  }

  function dispose() {
    scene.remove(group);
    scene.fog = null;
    if (scene.background === background) scene.background = null;
    for (const d of disposables) d.dispose();
    if (envRT) envRT.dispose();
  }

  return {
    group,
    sun,
    ambient,
    envMap: envRT ? envRT.texture : null,
    update,
    dispose,
    spawnBubbles,
    spawnBlood,
    fogColorAt,
  };
}
