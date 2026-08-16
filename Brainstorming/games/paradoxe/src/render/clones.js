/**
 * PARADOXE - the player and its ghosts.
 *
 * The live runner is opaque and lit; every clone is the same silhouette drawn
 * with a fresnel shell shader, tinted by age (the oldest is the faintest) and
 * split into red/green/blue rims so it reads as a recording rather than a
 * character. A short instanced afterimage trails behind each body.
 *
 * The shader is a plain ShaderMaterial: the renderer does not enable
 * logarithmicDepthBuffer, so no logdepthbuf chunk is needed.
 */

import * as THREE from 'three';
import { PALETTE, SIM } from '../config.js';

const TRAIL_PER_ACTOR = 6;
const TRAIL_SAMPLE = 2; // frames between two afterimage samples

const GHOST_VERT = `
uniform float uTime;
uniform float uGlitch;
varying vec3 vNormalW;
varying vec3 vViewDir;
varying float vHeight;
void main() {
  vec3 pos = position;
  // Horizontal tearing when the clone is close to breaking its own timeline.
  float band = step(0.5, fract(pos.y * 7.0 + uTime * 3.0));
  pos.x += uGlitch * band * (sin(uTime * 37.0 + pos.y * 20.0)) * 0.09;
  vec4 world = modelMatrix * vec4(pos, 1.0);
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vViewDir = normalize(cameraPosition - world.xyz);
  vHeight = pos.y;
  gl_Position = projectionMatrix * viewMatrix * world;
}
`;

const GHOST_FRAG = `
uniform vec3 uColor;
uniform float uOpacity;
uniform float uTime;
uniform float uGlitch;
varying vec3 vNormalW;
varying vec3 vViewDir;
varying float vHeight;
void main() {
  float d = max(dot(normalize(vNormalW), normalize(vViewDir)), 0.0);
  float f = 1.0 - d;
  // One exponent per channel: a cheap chromatic split on the silhouette rim.
  vec3 rim = vec3(pow(f, 1.35), pow(f, 1.9), pow(f, 2.6));
  float scan = 0.78 + 0.22 * sin(vHeight * 52.0 - uTime * 6.0);
  vec3 col = uColor * (0.45 + 1.5 * rim.g) + rim * 0.5;
  // A visible body, not just a wire outline: a clone is an obstacle you have to
  // read at a glance, so it keeps a solid core and gains a bright rim.
  float a = uOpacity * (0.46 + 0.6 * pow(f, 1.4)) * scan;
  a += uGlitch * 0.25 * step(0.7, fract(vHeight * 11.0 + uTime * 5.0));
  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));
}
`;

function buildFigureGeometries() {
  const body = new THREE.CapsuleGeometry(0.25, 0.3, 4, 12);
  body.translate(0, 0.4, 0);
  const head = new THREE.SphereGeometry(0.17, 14, 10);
  head.translate(0, 0.75, 0);
  const visor = new THREE.BoxGeometry(0.26, 0.075, 0.06);
  visor.translate(0, 0.77, -0.14);
  return { body, head, visor };
}

export function createActors(scene, textures) {
  const geos = buildFigureGeometries();
  const disposables = [geos.body, geos.head, geos.visor];

  const playerMat = new THREE.MeshStandardMaterial({
    color: PALETTE.player,
    roughness: 0.32,
    metalness: 0.18,
    emissive: PALETTE.player,
    emissiveIntensity: 0.45,
  });
  const playerHeadMat = new THREE.MeshStandardMaterial({
    color: 0xe8fbff,
    roughness: 0.24,
    metalness: 0.1,
    emissive: PALETTE.player,
    emissiveIntensity: 0.28,
  });
  const visorMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  disposables.push(playerMat, playerHeadMat, visorMat);

  const rigs = [];
  for (let i = 0; i < SIM.maxActors; i++) {
    const group = new THREE.Group();
    const isPlayer = i === 0;
    let mat;
    if (isPlayer) {
      mat = null;
    } else {
      mat = new THREE.ShaderMaterial({
        uniforms: {
          uColor: { value: new THREE.Color(PALETTE.clones[(i - 1) % PALETTE.clones.length]) },
          uOpacity: { value: 0.7 },
          uTime: { value: 0 },
          uGlitch: { value: 0 },
        },
        vertexShader: GHOST_VERT,
        fragmentShader: GHOST_FRAG,
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      disposables.push(mat);
    }
    const bodyMesh = new THREE.Mesh(geos.body, isPlayer ? playerMat : mat);
    const headMesh = new THREE.Mesh(geos.head, isPlayer ? playerHeadMat : mat);
    const visorMesh = new THREE.Mesh(geos.visor, isPlayer ? visorMat : mat);
    if (isPlayer) {
      bodyMesh.castShadow = true;
      headMesh.castShadow = true;
    }
    group.add(bodyMesh, headMesh, visorMesh);
    group.visible = false;
    scene.add(group);

    rigs.push({ group, mat, bodyMesh, headMesh, visorMesh, yaw: 0, history: new Float32Array(TRAIL_PER_ACTOR * 3), filled: 0 });
  }

  // Shared afterimage: one draw call for every ghost trail in the arena.
  const trailGeo = new THREE.CapsuleGeometry(0.22, 0.26, 3, 8);
  trailGeo.translate(0, 0.38, 0);
  const trailMat = new THREE.MeshBasicMaterial({
    transparent: true,
    opacity: 1,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    map: null,
  });
  disposables.push(trailGeo, trailMat);
  const trail = new THREE.InstancedMesh(trailGeo, trailMat, SIM.maxActors * TRAIL_PER_ACTOR);
  trail.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  trail.instanceColor = new THREE.InstancedBufferAttribute(
    new Float32Array(SIM.maxActors * TRAIL_PER_ACTOR * 3),
    3,
  );
  trail.count = 0;
  trail.frustumCulled = false;
  scene.add(trail);

  // Every body gets a ring on the floor beneath it. Finding who stands where is
  // most of the reading work in this game, and a ring survives being behind a
  // wall far better than any amount of contrast on the body itself.
  const markerGeo = new THREE.RingGeometry(0.36, 0.52, 28);
  markerGeo.rotateX(-Math.PI / 2);
  disposables.push(markerGeo);
  for (let i = 0; i < rigs.length; i++) {
    const isPlayer = i === 0;
    const mat = new THREE.MeshBasicMaterial({
      color: isPlayer ? PALETTE.player : PALETTE.clones[(i - 1) % PALETTE.clones.length],
      transparent: true,
      opacity: isPlayer ? 0.55 : 0.3,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    disposables.push(mat);
    const ring = new THREE.Mesh(markerGeo, mat);
    ring.visible = false;
    ring.frustumCulled = false;
    scene.add(ring);
    rigs[i].ring = ring;
    rigs[i].ringMat = mat;
  }

  const playerLight = new THREE.PointLight(PALETTE.player, 2.4, 7.5, 2);
  playerLight.visible = false;
  scene.add(playerLight);

  const mat4 = new THREE.Matrix4();
  const pos = new THREE.Vector3();
  const scl = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const color = new THREE.Color();
  quat.identity();

  let sampleCounter = 0;
  void textures;

  const api = {
    trail,
  };

  /**
   * @param {object} sim simulation
   * @param {Float32Array} rpos interpolated positions, 3 floats per body index
   * @param {number} elapsed seconds since boot
   * @param {function} stressOf (cloneIndex) -> 0..1 paradox pressure
   * @param {boolean} sampleTrail advance the afterimage this frame
   */
  api.sync = function sync(sim, rpos, elapsed, stressOf, sampleTrail) {
    const advance = sampleTrail !== false && (sampleCounter++ % TRAIL_SAMPLE === 0);
    let trailCount = 0;
    const newest = sim.actorCount - 1;

    for (let i = 0; i < SIM.maxActors; i++) {
      const rig = rigs[i];
      const a = sim.actors[i];
      if (!a || !a.active || a.fallen) {
        rig.group.visible = false;
        rig.ring.visible = false;
        rig.filled = 0;
        if (i === 0) playerLight.visible = false;
        continue;
      }
      const x = rpos[i * 3];
      const y = rpos[i * 3 + 1];
      const z = rpos[i * 3 + 2];
      rig.group.visible = true;
      rig.group.position.set(x, y, z);

      // Face the movement direction, falling back to the camera yaw when idle.
      const targetYaw = Math.atan2(a.faceX, a.faceZ) + Math.PI;
      // Shortest signed angle, wrapped with a modulo rather than a while loop:
      // a per frame loop must never depend on its input staying in range.
      const TWO_PI = Math.PI * 2;
      const d = (((targetYaw - rig.yaw + Math.PI) % TWO_PI) + TWO_PI) % TWO_PI - Math.PI;
      rig.yaw += d * 0.25;
      rig.group.rotation.y = rig.yaw;

      const bob = a.grounded ? Math.sin(elapsed * 9 + i) * 0.012 : 0;
      rig.group.position.y = y + bob;

      const hv = sim.heightAt(Math.floor(x), Math.floor(z));
      const ground = hv < 0 || hv > 2 ? y : hv;
      rig.ring.visible = true;
      rig.ring.position.set(x, ground + 0.035, z);
      if (i === 0) {
        const beat = 1 + Math.sin(elapsed * 3.4) * 0.06;
        rig.ring.scale.set(beat, 1, beat);
        rig.ringMat.opacity = 0.42 + Math.sin(elapsed * 3.4) * 0.12;
        playerLight.visible = true;
        playerLight.position.set(x, y + 0.7, z);
      } else {
        rig.ringMat.opacity = a.frozen ? 0.16 : 0.3;
      }

      if (i > 0 && rig.mat) {
        const age = newest > 1 ? (newest - i) / (newest - 1) : 0;
        rig.mat.uniforms.uOpacity.value = 0.78 - age * 0.34 - (a.frozen ? 0.12 : 0);
        rig.mat.uniforms.uTime.value = elapsed;
        rig.mat.uniforms.uGlitch.value = stressOf ? stressOf(i - 1) : 0;
      }

      if (advance) {
        for (let k = TRAIL_PER_ACTOR - 1; k > 0; k--) {
          rig.history[k * 3] = rig.history[(k - 1) * 3];
          rig.history[k * 3 + 1] = rig.history[(k - 1) * 3 + 1];
          rig.history[k * 3 + 2] = rig.history[(k - 1) * 3 + 2];
        }
        rig.history[0] = x;
        rig.history[1] = y;
        rig.history[2] = z;
        if (rig.filled < TRAIL_PER_ACTOR) rig.filled++;
      }

      const base = i === 0 ? PALETTE.player : PALETTE.clones[(i - 1) % PALETTE.clones.length];
      for (let k = 1; k < rig.filled; k++) {
        const t = k / TRAIL_PER_ACTOR;
        pos.set(rig.history[k * 3], rig.history[k * 3 + 1], rig.history[k * 3 + 2]);
        const dx = pos.x - x;
        const dz = pos.z - z;
        if (dx * dx + dz * dz < 0.0009) continue;
        const s = 1 - t * 0.6;
        scl.set(s, s, s);
        mat4.compose(pos, quat, scl);
        trail.setMatrixAt(trailCount, mat4);
        color.setHex(base).multiplyScalar((1 - t) * 0.22);
        trail.setColorAt(trailCount, color);
        trailCount++;
      }
    }

    trail.count = trailCount;
    if (trailCount > 0) {
      trail.instanceMatrix.needsUpdate = true;
      if (trail.instanceColor) trail.instanceColor.needsUpdate = true;
    }
  };

  api.dispose = function dispose() {
    for (let i = 0; i < rigs.length; i++) {
      scene.remove(rigs[i].group);
      scene.remove(rigs[i].ring);
    }
    scene.remove(playerLight);
    scene.remove(trail);
    trail.dispose();
    for (let i = 0; i < disposables.length; i++) disposables[i].dispose();
    disposables.length = 0;
  };

  return api;
}
