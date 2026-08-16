// Effets de vol (S08, S09) : traits de vitesse, bouclier de rentree
// atmospherique, tuyeres du vaisseau.
//
// Ces objets sont attaches par main.js soit a la camera, soit au groupe du
// vaisseau : ils travaillent donc dans un espace LOCAL au parent et ne
// supposent aucune position absolue. Les directions recues (velocity, forward)
// sont exprimees en espace monde et ramenees en espace local via la matrice du
// parent.
//
// Aucune allocation par frame : tous les temporaires sont au niveau module.

import * as THREE from 'three';
import { clamp, saturate, smoothstep, damp } from '../core/math.js';

// --- temporaires partages ---------------------------------------------------
const _m3 = new THREE.Matrix3();
const _dir = new THREE.Vector3();
const _tmp = new THREE.Vector3();
const _up = new THREE.Vector3(0, 1, 0);

/**
 * Ramene une direction monde dans l'espace local du parent de `object3D`.
 * Sans parent, la direction est prise telle quelle. Resultat normalise.
 */
function worldDirToLocal(object3D, worldDir, out) {
  if (!worldDir) return out.set(0, 0, -1);
  out.copy(worldDir);
  const parent = object3D.parent;
  if (parent) {
    _m3.setFromMatrix4(parent.matrixWorld).invert();
    out.applyMatrix3(_m3);
  }
  const len = out.length();
  if (len > 1e-6) out.multiplyScalar(1 / len);
  else out.set(0, 0, -1);
  return out;
}

/** Sprite radial additif genere sur canvas (T08), zero asset binaire. */
function createRadialSprite(size, power, tint) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const c2d = canvas.getContext('2d');
  const img = c2d.createImageData(size, size);
  const data = img.data;
  const half = size * 0.5;
  let p = 0;
  for (let y = 0; y < size; y++) {
    const dy = (y + 0.5 - half) / half;
    for (let x = 0; x < size; x++) {
      const dx = (x + 0.5 - half) / half;
      const r = Math.min(1, Math.hypot(dx, dy));
      const a = Math.pow(1 - r, power);
      data[p] = tint[0];
      data[p + 1] = tint[1];
      data[p + 2] = tint[2];
      data[p + 3] = Math.round(saturate(a) * 255);
      p += 4;
    }
  }
  c2d.putImageData(img, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.needsUpdate = true;
  return texture;
}

// ===========================================================================
// S08 - Traits de vitesse
// ===========================================================================

const LINE_VERT = /* glsl */ `
  attribute float aFade;
  attribute float aBright;
  varying float vA;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    vA = aFade * aBright;
  }
`;

const LINE_FRAG = /* glsl */ `
  #include <common>
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vA;
  void main() {
    float a = saturate(vA) * uOpacity;
    if (a < 0.003) discard;
    gl_FragColor = vec4(uColor * a, a);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

const SPEEDLINE_COUNT = { low: 260, medium: 420, high: 600, ultra: 820 };

export function createSpeedLines({ quality } = {}) {
  const q = quality || {};
  const count = SPEEDLINE_COUNT[q.name] || 600;

  // Demi-cote de la boite de recyclage, en metres (espace local du parent).
  const HALF = 110;
  const SPAN = HALF * 2;

  const positions = new Float32Array(count * 6);
  const fades = new Float32Array(count * 2);
  const brights = new Float32Array(count * 2);
  // Etat des particules (centre de chaque trait).
  const px = new Float32Array(count);
  const py = new Float32Array(count);
  const pz = new Float32Array(count);
  const lenScale = new Float32Array(count);

  // Distribution initiale pseudo-aleatoire deterministe (pas de seed externe :
  // ce decor n'a pas besoin d'etre reproductible d'une partie a l'autre).
  let s = 0x9e3779b9;
  const rnd = () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  for (let i = 0; i < count; i++) {
    px[i] = (rnd() * 2 - 1) * HALF;
    py[i] = (rnd() * 2 - 1) * HALF;
    pz[i] = (rnd() * 2 - 1) * HALF;
    lenScale[i] = 0.45 + rnd() * 1.1;
    const b = 0.35 + rnd() * 0.65;
    fades[i * 2] = 1;
    fades[i * 2 + 1] = 0;
    brights[i * 2] = b;
    brights[i * 2 + 1] = b;
  }

  const geometry = new THREE.BufferGeometry();
  const posAttr = new THREE.BufferAttribute(positions, 3);
  posAttr.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute('position', posAttr);
  geometry.setAttribute('aFade', new THREE.BufferAttribute(fades, 1));
  geometry.setAttribute('aBright', new THREE.BufferAttribute(brights, 1));
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), HALF * 3);

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color().setRGB(0.72, 0.86, 1.0) },
      uOpacity: { value: 0 },
    },
    vertexShader: LINE_VERT,
    fragmentShader: LINE_FRAG,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });

  const lines = new THREE.LineSegments(geometry, material);
  lines.frustumCulled = false;

  const object3D = new THREE.Group();
  object3D.name = 'speedLines';
  object3D.add(lines);
  object3D.visible = false;

  let opacity = 0;

  return {
    object3D,

    update(dt, ctx) {
      const d = typeof dt === 'number' && dt > 0 ? dt : 0;
      const c = ctx || {};
      let speed = typeof c.speed === 'number' ? c.speed : 0;
      if (!speed && c.velocity) speed = c.velocity.length();
      const density = typeof c.density === 'number' ? c.density : 0;

      const target = smoothstep(80, 900, speed) * (0.55 + 0.45 * saturate(density * 2));
      opacity = d > 0 ? damp(opacity, target, 7, d) : target;
      material.uniforms.uOpacity.value = opacity;

      if (opacity < 0.004) {
        object3D.visible = false;
        return;
      }
      object3D.visible = true;

      worldDirToLocal(object3D, c.velocity, _dir);
      const dx = _dir.x;
      const dy = _dir.y;
      const dz = _dir.z;

      // Longueur du trait et vitesse de defilement visuelle : bornees pour que
      // le mode pulse (240 km/s) reste lisible.
      const streak = clamp(speed * 0.05, 2.5, 150);
      const rate = clamp(speed * 0.45, 10, 320) * d;

      for (let i = 0; i < count; i++) {
        let x = px[i] - dx * rate;
        let y = py[i] - dy * rate;
        let z = pz[i] - dz * rate;

        // Recyclage par enroulement de la boite (distribution preservee).
        if (x > HALF) x -= SPAN;
        else if (x < -HALF) x += SPAN;
        if (y > HALF) y -= SPAN;
        else if (y < -HALF) y += SPAN;
        if (z > HALF) z -= SPAN;
        else if (z < -HALF) z += SPAN;

        px[i] = x;
        py[i] = y;
        pz[i] = z;

        const l = streak * lenScale[i];
        const o = i * 6;
        positions[o] = x;
        positions[o + 1] = y;
        positions[o + 2] = z;
        positions[o + 3] = x + dx * l;
        positions[o + 4] = y + dy * l;
        positions[o + 5] = z + dz * l;
      }

      posAttr.needsUpdate = true;
    },

    dispose() {
      object3D.remove(lines);
      geometry.dispose();
      material.dispose();
    },
  };
}

// ===========================================================================
// S09 - Bouclier de rentree atmospherique
// ===========================================================================

const GLOW_VERT = /* glsl */ `
  varying vec3 vNormalView;
  varying vec3 vViewDir;
  varying vec2 vUv;
  void main() {
    vUv = uv;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vNormalView = normalize(normalMatrix * normal);
    vViewDir = normalize(-mvPosition.xyz);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const GLOW_FRAG = /* glsl */ `
  #include <common>
  uniform vec3 uColorHot;
  uniform vec3 uColorEdge;
  uniform float uIntensity;
  uniform float uTime;

  varying vec3 vNormalView;
  varying vec3 vViewDir;
  varying vec2 vUv;

  void main() {
    float facing = abs(dot(normalize(vNormalView), normalize(vViewDir)));
    float fres = pow(1.0 - facing, 2.2);
    // vUv.y = 0 a la base (proche du nez), 1 a la pointe.
    float along = pow(1.0 - vUv.y, 1.35);
    float flicker = 0.85 + 0.15 * sin(uTime * 37.0 + vUv.x * 24.0);
    float a = saturate(fres * 0.85 + 0.25) * along * uIntensity * flicker;
    if (a < 0.004) discard;
    vec3 col = mix(uColorEdge, uColorHot, saturate(along * 1.2));
    gl_FragColor = vec4(col * a, a);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

const SPARK_COUNT = 140;

export function createReentryGlow() {
  const object3D = new THREE.Group();
  object3D.name = 'reentryGlow';
  object3D.visible = false;

  // Coquille conique : base (large) au niveau du nez, pointe vers l'avant.
  const shellGeometry = new THREE.ConeGeometry(1, 1, 28, 1, true);
  shellGeometry.translate(0, 0.5, 0); // base a l'origine, axe +Y

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uColorHot: { value: new THREE.Color().setRGB(1.0, 0.95, 0.82) },
      uColorEdge: { value: new THREE.Color().setRGB(1.0, 0.42, 0.10) },
      uIntensity: { value: 0 },
      uTime: { value: 0 },
    },
    vertexShader: GLOW_VERT,
    fragmentShader: GLOW_FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });

  const SHELL_WIDTH = 3.4;
  const SHELL_LENGTH = 7.0;
  const shell = new THREE.Mesh(shellGeometry, material);
  shell.scale.set(SHELL_WIDTH, SHELL_LENGTH, SHELL_WIDTH);
  shell.renderOrder = 8;
  object3D.add(shell);

  // Etincelles qui filent vers l'arriere.
  const sparkTex = createRadialSprite(64, 2.2, [255, 208, 150]);
  const sparkPos = new Float32Array(SPARK_COUNT * 3);
  const sparkLife = new Float32Array(SPARK_COUNT);
  const sparkSpeed = new Float32Array(SPARK_COUNT);
  const sparkGeometry = new THREE.BufferGeometry();
  const sparkAttr = new THREE.BufferAttribute(sparkPos, 3);
  sparkAttr.setUsage(THREE.DynamicDrawUsage);
  sparkGeometry.setAttribute('position', sparkAttr);
  sparkGeometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 90);

  const sparkMaterial = new THREE.PointsMaterial({
    map: sparkTex,
    size: 0.9,
    sizeAttenuation: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    opacity: 0,
  });
  sparkMaterial.color.setRGB(1.0, 0.62, 0.28);

  const sparks = new THREE.Points(sparkGeometry, sparkMaterial);
  sparks.frustumCulled = false;
  sparks.renderOrder = 9;
  object3D.add(sparks);

  let seed = 0x1f2e3d4c;
  const rnd = () => {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = seed;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  // Respawn sur un anneau autour du nez, en espace local.
  function respawn(i, fwd) {
    const ang = rnd() * Math.PI * 2;
    const rad = 1.2 + rnd() * 2.4;
    // Base tangente simple autour de fwd.
    _tmp.set(0, 1, 0);
    if (Math.abs(fwd.y) > 0.9) _tmp.set(1, 0, 0);
    _tmp.cross(fwd).normalize();
    const bx = fwd.y * _tmp.z - fwd.z * _tmp.y;
    const by = fwd.z * _tmp.x - fwd.x * _tmp.z;
    const bz = fwd.x * _tmp.y - fwd.y * _tmp.x;
    const ca = Math.cos(ang) * rad;
    const sa = Math.sin(ang) * rad;
    const o = i * 3;
    sparkPos[o] = fwd.x * 1.4 + _tmp.x * ca + bx * sa;
    sparkPos[o + 1] = fwd.y * 1.4 + _tmp.y * ca + by * sa;
    sparkPos[o + 2] = fwd.z * 1.4 + _tmp.z * ca + bz * sa;
    sparkLife[i] = 0.25 + rnd() * 0.6;
    sparkSpeed[i] = 22 + rnd() * 48;
  }

  let intensity = 0;
  let time = 0;
  let initialized = false;

  return {
    object3D,

    update(dt, ctx) {
      const d = typeof dt === 'number' && dt > 0 ? dt : 0;
      time += d;
      material.uniforms.uTime.value = time;

      const c = ctx || {};
      const speed = typeof c.speed === 'number' ? c.speed : 0;
      const density = typeof c.density === 'number' ? c.density : 0;

      // Intensite = vitesse^2 * densite, normalisee sur une rentree "typique".
      const v = speed / 460;
      const target = saturate(v * v * saturate(density * 1.35) * 1.6);
      intensity = d > 0 ? damp(intensity, target, 5, d) : target;
      material.uniforms.uIntensity.value = intensity;
      sparkMaterial.opacity = intensity * 0.85;

      if (intensity < 0.006) {
        object3D.visible = false;
        return;
      }
      object3D.visible = true;

      const fwd = worldDirToLocal(object3D, c.forward, _dir);
      // La coquille est orientee sur l'avant et placee juste devant le nez.
      shell.quaternion.setFromUnitVectors(_up, fwd);
      shell.position.copy(fwd).multiplyScalar(0.6);
      const grow = 0.75 + 0.45 * intensity;
      shell.scale.set(SHELL_WIDTH * grow, SHELL_LENGTH * grow, SHELL_WIDTH * grow);

      if (!initialized) {
        for (let i = 0; i < SPARK_COUNT; i++) respawn(i, fwd);
        initialized = true;
      }

      // Seules les `alive` premieres etincelles sont dessinees (setDrawRange) :
      // aucune particule fantome ne s'empile a l'origine.
      const alive = Math.min(SPARK_COUNT, Math.max(8, Math.round(SPARK_COUNT * intensity)));
      sparkGeometry.setDrawRange(0, alive);
      for (let i = 0; i < alive; i++) {
        sparkLife[i] -= d;
        if (sparkLife[i] <= 0) {
          respawn(i, fwd);
          continue;
        }
        const step = sparkSpeed[i] * (0.4 + intensity) * d;
        const o = i * 3;
        sparkPos[o] -= fwd.x * step;
        sparkPos[o + 1] -= fwd.y * step;
        sparkPos[o + 2] -= fwd.z * step;
      }
      sparkAttr.needsUpdate = true;
    },

    dispose() {
      object3D.remove(shell);
      object3D.remove(sparks);
      shellGeometry.dispose();
      material.dispose();
      sparkGeometry.dispose();
      sparkMaterial.dispose();
      sparkTex.dispose();
    },
  };
}

// ===========================================================================
// Tuyeres du vaisseau
// ===========================================================================

const FLAME_VERT = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormalView;
  varying vec3 vViewDir;
  void main() {
    vUv = uv;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vNormalView = normalize(normalMatrix * normal);
    vViewDir = normalize(-mvPosition.xyz);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const FLAME_FRAG = /* glsl */ `
  #include <common>
  uniform vec3 uColorCore;
  uniform vec3 uColorTail;
  uniform float uIntensity;
  uniform float uTime;

  varying vec2 vUv;
  varying vec3 vNormalView;
  varying vec3 vViewDir;

  void main() {
    // vUv.y : 0 a la tuyere, 1 a la pointe de la flamme.
    float along = 1.0 - vUv.y;
    float facing = abs(dot(normalize(vNormalView), normalize(vViewDir)));
    float rim = 0.45 + 0.55 * pow(1.0 - facing, 1.6);
    float flicker = 0.86 + 0.14 * sin(uTime * 43.0 + vUv.y * 17.0)
                         + 0.06 * sin(uTime * 91.0 + vUv.x * 9.0);
    float a = pow(saturate(along), 1.25) * rim * uIntensity * flicker;
    if (a < 0.004) discard;
    vec3 col = mix(uColorTail, uColorCore, pow(saturate(along), 1.8));
    gl_FragColor = vec4(col * a, a);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

// Le vaisseau regarde vers -Z (convention three) : les tuyeres crachent en +Z.
const NOZZLES = [
  [-0.95, -0.1, 1.45],
  [0.95, -0.1, 1.45],
];

export function createEngineTrail() {
  const object3D = new THREE.Group();
  object3D.name = 'engineTrail';
  object3D.visible = false;

  // Cone unite : base a l'origine, axe +Z apres rotation.
  const geometry = new THREE.ConeGeometry(1, 1, 16, 1, true);
  geometry.translate(0, 0.5, 0);
  geometry.rotateX(Math.PI / 2);

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uColorCore: { value: new THREE.Color().setRGB(0.85, 0.98, 1.0) },
      uColorTail: { value: new THREE.Color().setRGB(0.12, 0.55, 1.0) },
      uIntensity: { value: 0 },
      uTime: { value: 0 },
    },
    vertexShader: FLAME_VERT,
    fragmentShader: FLAME_FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
  });

  const glowTex = createRadialSprite(128, 2.0, [190, 235, 255]);
  const glowMaterial = new THREE.SpriteMaterial({
    map: glowTex,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    opacity: 0,
  });
  glowMaterial.color.setRGB(0.55, 0.85, 1.0);

  const flames = [];
  const glows = [];
  for (let i = 0; i < NOZZLES.length; i++) {
    const flame = new THREE.Mesh(geometry, material);
    flame.position.set(NOZZLES[i][0], NOZZLES[i][1], NOZZLES[i][2]);
    flame.renderOrder = 7;
    object3D.add(flame);
    flames.push(flame);

    const glow = new THREE.Sprite(glowMaterial);
    glow.position.copy(flame.position);
    glow.renderOrder = 8;
    object3D.add(glow);
    glows.push(glow);
  }

  // Couleurs cibles : cyan au repos, blanc-violet en boost.
  const COLD_CORE = new THREE.Color().setRGB(0.82, 0.97, 1.0);
  const COLD_TAIL = new THREE.Color().setRGB(0.10, 0.50, 1.0);
  const HOT_CORE = new THREE.Color().setRGB(1.0, 0.96, 1.0);
  const HOT_TAIL = new THREE.Color().setRGB(0.62, 0.36, 1.0);

  let level = 0;
  let boostLevel = 0;
  let time = 0;

  return {
    object3D,

    update(dt, ctx) {
      const d = typeof dt === 'number' && dt > 0 ? dt : 0;
      time += d;
      material.uniforms.uTime.value = time;

      const c = ctx || {};
      const throttleRaw = typeof c.throttle === 'number' ? c.throttle : c.throttle ? 1 : 0;
      const boostRaw = typeof c.boost === 'number' ? c.boost : c.boost ? 1 : 0;
      const throttle = saturate(Math.abs(throttleRaw));
      const boost = saturate(boostRaw);

      level = d > 0 ? damp(level, throttle, 9, d) : throttle;
      boostLevel = d > 0 ? damp(boostLevel, boost, 6, d) : boost;

      const intensity = level * (0.85 + 0.65 * boostLevel);
      material.uniforms.uIntensity.value = intensity;

      if (intensity < 0.01) {
        object3D.visible = false;
        return;
      }
      object3D.visible = true;

      material.uniforms.uColorCore.value.lerpColors(COLD_CORE, HOT_CORE, boostLevel);
      material.uniforms.uColorTail.value.lerpColors(COLD_TAIL, HOT_TAIL, boostLevel);

      const flicker = 0.92 + 0.08 * Math.sin(time * 27.0);
      const length = (0.8 + 3.1 * level) * (1 + 1.15 * boostLevel) * flicker;
      const width = 0.34 + 0.16 * level + 0.1 * boostLevel;
      for (let i = 0; i < flames.length; i++) {
        flames[i].scale.set(width, width, length);
      }

      const glowSize = (0.85 + 1.5 * level + 0.9 * boostLevel) * flicker;
      glowMaterial.opacity = saturate(intensity * 0.8);
      glowMaterial.color.lerpColors(COLD_CORE, HOT_TAIL, boostLevel * 0.7);
      for (let i = 0; i < glows.length; i++) {
        glows[i].scale.set(glowSize, glowSize, 1);
      }
    },

    dispose() {
      for (let i = 0; i < flames.length; i++) object3D.remove(flames[i]);
      for (let i = 0; i < glows.length; i++) object3D.remove(glows[i]);
      flames.length = 0;
      glows.length = 0;
      geometry.dispose();
      material.dispose();
      glowMaterial.dispose();
      glowTex.dispose();
    },
  };
}
