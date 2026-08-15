// Champ d'etoiles (A13) + cubemap de nebuleuse (T07, S07).
//
// Le groupe suit la camera : les etoiles restent a distance constante, elles ne
// defilent donc jamais avec le vaisseau. Aucune connaissance de viewOrigin.
// Le fond de scene est un THREE.CubeTexture generee au chargement : chaque pixel
// est echantillonne AVEC LA DIRECTION 3D correspondante, ce qui rend les six
// faces parfaitement continues sur leurs aretes.

import * as THREE from 'three';
import { mulberry32, hashString, saturate, smoothstep, clamp } from '../core/math.js';
import { FBM } from '../gen/noise.js';
import { SCALE } from '../core/settings.js';

// Classes spectrales : poids realistes (beaucoup de naines M et K, tres peu
// d'etoiles bleues) et couleurs approchees, exprimees en sRGB.
const SPECTRAL = [
  { key: 'O', weight: 0.004, rgb: [0.60, 0.69, 1.00], size: [2.2, 3.6] },
  { key: 'B', weight: 0.012, rgb: [0.72, 0.81, 1.00], size: [1.9, 3.1] },
  { key: 'A', weight: 0.030, rgb: [0.92, 0.95, 1.00], size: [1.5, 2.6] },
  { key: 'F', weight: 0.062, rgb: [1.00, 0.97, 0.92], size: [1.3, 2.3] },
  { key: 'G', weight: 0.100, rgb: [1.00, 0.93, 0.74], size: [1.1, 2.1] },
  { key: 'K', weight: 0.220, rgb: [1.00, 0.80, 0.55], size: [0.9, 1.9] },
  { key: 'M', weight: 0.572, rgb: [1.00, 0.62, 0.41], size: [0.7, 1.6] },
];

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const STAR_VERT = /* glsl */ `
  attribute vec3 aColor;
  attribute float aSize;
  attribute float aSeed;

  uniform float uTime;
  uniform float uSizeScale;
  uniform float uShellRadius;

  varying vec3 vColor;
  varying float vTwinkle;

  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;

    // Attenuation par la distance ecran (la coquille est quasi a distance fixe,
    // le facteur reste donc proche de 1 mais borne les cas extremes).
    float dist = max(-mvPosition.z, 1.0);
    float atten = clamp(uShellRadius / dist, 0.35, 2.2);

    // Scintillement leger, desynchronise par etoile.
    float tw = 0.74 + 0.26 * sin(uTime * (0.6 + aSeed * 2.7) + aSeed * 41.0);
    vTwinkle = tw;
    vColor = aColor;

    gl_PointSize = aSize * uSizeScale * atten * (0.85 + 0.3 * tw);
  }
`;

const STAR_FRAG = /* glsl */ `
  uniform float uAtmoFade;
  uniform float uBrightness;

  varying vec3 vColor;
  varying float vTwinkle;

  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float r = length(d) * 2.0;
    float core = exp(-r * r * 5.5);
    float halo = smoothstep(1.0, 0.12, r) * 0.30;
    float a = (core + halo) * vTwinkle * (1.0 - uAtmoFade);
    if (a < 0.004) discard;
    gl_FragColor = vec4(vColor * a * uBrightness, a);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

/** Seed tolerante : nombre, chaine ou rien. */
function normalizeSeed(seed) {
  if (typeof seed === 'number' && Number.isFinite(seed)) return seed >>> 0;
  if (typeof seed === 'string' && seed.length) return hashString(seed);
  return 0x5eed57a4;
}

/**
 * Direction (non normalisee) du centre du texel (u, v) de la face `face` d'une
 * cubemap, convention OpenGL ES (celle utilisee par textureCube). u et v sont
 * dans [-1, 1], v etant mesure du haut vers le bas de l'image (les CubeTexture
 * de three ont flipY = false).
 */
function faceDirection(face, u, v, out) {
  switch (face) {
    case 0: // +X
      out.set(1, -v, -u);
      break;
    case 1: // -X
      out.set(-1, -v, u);
      break;
    case 2: // +Y
      out.set(u, 1, v);
      break;
    case 3: // -Y
      out.set(u, -1, -v);
      break;
    case 4: // +Z
      out.set(u, -v, 1);
      break;
    default: // -Z
      out.set(-u, -v, -1);
      break;
  }
  return out;
}

/**
 * Construit les 6 faces de la nebuleuse de fond sur des canvas 2D.
 * Teintes : violet profond, bleu nuit, plus une trainee cyan le long d'un
 * "plan galactique" tire de la seed.
 */
function buildNebulaCubemap(seedNum, size) {
  const rnd = mulberry32(seedNum ^ 0x51ed3c11);
  const fbmCloud = new FBM({
    seed: seedNum ^ 0x1234567,
    octaves: 4,
    frequency: 1.05,
    lacunarity: 2.13,
    gain: 0.55,
  });
  const fbmStreak = new FBM({
    seed: seedNum ^ 0x7654321,
    octaves: 2,
    frequency: 2.4,
    lacunarity: 2.07,
    gain: 0.5,
  });

  // Normale du plan de la voie lactee : purement directionnelle, donc continue
  // d'une face a l'autre.
  let px = rnd() * 2 - 1;
  let py = rnd() * 2 - 1;
  let pz = rnd() * 2 - 1;
  const pl = Math.hypot(px, py, pz) || 1;
  px /= pl;
  py /= pl;
  pz /= pl;

  const dir = new THREE.Vector3();
  const faces = [];

  for (let f = 0; f < 6; f++) {
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const c2d = canvas.getContext('2d', { willReadFrequently: false });
    const img = c2d.createImageData(size, size);
    const data = img.data;
    let p = 0;

    for (let y = 0; y < size; y++) {
      const v = ((y + 0.5) / size) * 2 - 1;
      for (let x = 0; x < size; x++) {
        const u = ((x + 0.5) / size) * 2 - 1;
        faceDirection(f, u, v, dir);
        const inv = 1 / (Math.hypot(dir.x, dir.y, dir.z) || 1);
        const dx = dir.x * inv;
        const dy = dir.y * inv;
        const dz = dir.z * inv;

        const along = dx * px + dy * py + dz * pz;
        const band = Math.exp(-along * along * 6.5);

        const n1 = fbmCloud.sample(dx, dy, dz);
        const cloud = smoothstep(0.06, 0.78, n1 * 0.5 + 0.5 + band * 0.24);
        const tint = saturate(n1 * 0.8 + 0.5);

        const n2 = fbmStreak.sample(dx * 2.1 + 11.3, dy * 2.1 - 5.7, dz * 2.1 + 3.1);
        const ridge = saturate(1 - Math.abs(n2) * 2.3);
        const streak = ridge * ridge * ridge * band;

        const gain = cloud * (0.5 + 0.8 * band);
        // Bleu nuit -> violet profond. Le fond de l'espace doit rester SOMBRE :
        // ce sont le soleil et les planetes qui portent la lumiere, pas le
        // decor. Une nebuleuse lumineuse ecrase tout le reste de l'image.
        let r = 2 + gain * (5 + tint * 17) + streak * 13;
        let g = 3 + gain * (7 + tint * 4) + streak * 34;
        let b = 6 + gain * (20 + tint * 13) + streak * 42;

        data[p] = r > 255 ? 255 : r;
        data[p + 1] = g > 255 ? 255 : g;
        data[p + 2] = b > 255 ? 255 : b;
        data[p + 3] = 255;
        p += 4;
      }
    }

    c2d.putImageData(img, 0, 0);
    faces.push(canvas);
  }

  const texture = new THREE.CubeTexture(faces);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

/** Tire une classe spectrale selon les poids du tableau SPECTRAL. */
function pickSpectral(r) {
  let acc = 0;
  for (let i = 0; i < SPECTRAL.length; i++) {
    acc += SPECTRAL[i].weight;
    if (r <= acc) return SPECTRAL[i];
  }
  return SPECTRAL[SPECTRAL.length - 1];
}

export function createStarfield({ seed, quality } = {}) {
  const seedNum = normalizeSeed(seed);
  const q = quality || {};
  const count = Math.max(500, (q.starCount | 0) || 8000);
  // Cout de generation de la nebuleuse : ~6 echantillons de bruit par pixel.
  // 512 par face = 1.6 M pixels = ~2 s de thread principal, ce qui est trop
  // pour un chargement. On genere donc 256 par face (le fond est basse
  // frequence, l'interpolation lineaire suffit) et on ne monte a 512 qu'en
  // preset ultra, ou l'utilisateur a explicitement demande le maximum.
  const faceSize = q.name === 'ultra' ? 512 : 256;

  const rnd = mulberry32(seedNum);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);
  const seeds = new Float32Array(count);

  const shell = SCALE.STAR_SHELL;
  const tmpColor = new THREE.Color();

  for (let i = 0; i < count; i++) {
    // Spirale de Fibonacci + jitter seede : distribution uniforme sans grille
    // visible.
    const yBase = 1 - ((i + 0.5) / count) * 2;
    const y = clamp(yBase + (rnd() - 0.5) * (1.6 / count), -1, 1);
    const radial = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = GOLDEN_ANGLE * i + (rnd() - 0.5) * 0.35;

    const o = i * 3;
    positions[o] = Math.cos(theta) * radial * shell;
    positions[o + 1] = y * shell;
    positions[o + 2] = Math.sin(theta) * radial * shell;

    const cls = pickSpectral(rnd());
    // Legere variation de teinte par etoile, puis passage en espace lineaire.
    const jitter = 0.92 + rnd() * 0.16;
    tmpColor.setRGB(
      saturate(cls.rgb[0] * jitter),
      saturate(cls.rgb[1] * jitter),
      saturate(cls.rgb[2] * jitter),
      THREE.SRGBColorSpace,
    );
    colors[o] = tmpColor.r;
    colors[o + 1] = tmpColor.g;
    colors[o + 2] = tmpColor.b;

    const t = rnd();
    sizes[i] = cls.size[0] + (cls.size[1] - cls.size[0]) * t * t;
    seeds[i] = rnd();
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aColor', new THREE.BufferAttribute(colors, 3));
  geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
  geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), shell * 1.001);

  const dpr = typeof window !== 'undefined' ? Math.min(window.devicePixelRatio || 1, 2) : 1;

  const material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uAtmoFade: { value: 0 },
      uSizeScale: { value: dpr },
      uShellRadius: { value: shell },
      uBrightness: { value: 1.7 },
    },
    vertexShader: STAR_VERT,
    fragmentShader: STAR_FRAG,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: THREE.AdditiveBlending,
  });

  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  points.renderOrder = -1000;

  const object3D = new THREE.Group();
  object3D.name = 'starfield';
  object3D.renderOrder = -1000;
  object3D.matrixAutoUpdate = true;
  object3D.add(points);

  const background = buildNebulaCubemap(seedNum, faceSize);

  let time = 0;
  let fade = 0;

  /** Recopie la position camera : le ciel ne doit jamais se rapprocher. */
  function followCamera(cameraPosition) {
    if (cameraPosition) object3D.position.copy(cameraPosition);
  }

  return {
    object3D,
    background,

    update(dt, ctx) {
      const d = typeof dt === 'number' && dt > 0 ? dt : 0;
      time += d;
      material.uniforms.uTime.value = time;

      const c = ctx || {};
      followCamera(c.cameraPosition);

      // Un ciel de jour dense ne doit pas etre etoile.
      const density = typeof c.atmoDensity === 'number' ? c.atmoDensity : 0;
      const target = smoothstep(0.015, 0.30, density);
      // Lissage simple, sans allocation.
      fade += (target - fade) * (d > 0 ? Math.min(1, d * 6) : 1);
      material.uniforms.uAtmoFade.value = fade;
      points.visible = fade < 0.995;
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      background.dispose();
      object3D.remove(points);
    },
  };
}
