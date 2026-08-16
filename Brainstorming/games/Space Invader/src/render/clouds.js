// Couches nuageuses procedurales.
//
// Une a deux coques concentriques (selon quality.cloudLayers) rendues en
// transparence. L'opacite vient d'un fBm 3D en domain warping evalue en GLSL
// (aucune texture, aucune texture 3D), seuille par spec.clouds.coverage et
// module par des bandes latitudinales douces qui imitent les cellules de
// Hadley : maximum a l'equateur (zone de convergence), creux vers 30 degres
// (ceinture subtropicale seche), second maximum vers 60 degres (fronts
// polaires).
//
// Rotation differentielle : les coques ne tournent PAS (cela desynchroniserait
// le repere local planete, ou vivent le terrain, l'ocean et la vie). C'est le
// repere d'echantillonnage du bruit qui tourne autour de l'axe des poles (+Y),
// a une vitesse legerement differente par couche.
//
// Ordre de rendu : les coques n'ecrivent pas la profondeur et sont triees
// manuellement (la plus lointaine d'abord) pour eviter le clignotement entre
// couches et avec l'atmosphere (qui passe apres, en additif).
//
// Tout est en ESPACE LOCAL PLANETE. Le module ne connait pas viewOrigin.

import * as THREE from 'three';
import { clamp, smoothstep } from '../core/math.js';

// ---------------------------------------------------------------------------
// Constantes de reglage
// ---------------------------------------------------------------------------

const SHELL_DETAIL = 5; // IcosahedronGeometry(_, 5) -> 720 triangles
const LAYER_K = [1.0, 1.55]; // multiplicateurs d'altitude par couche
const LAYER_ROT = [1.0, 1.42]; // rotation differentielle
const LAYER_SCALE = [3.2, 4.6]; // frequence de base du bruit par couche
const BASE_RENDER_ORDER = 6; // avant l'atmosphere (12)
const MAX_OPACITY = 0.94;
const TERRAIN_CLEARANCE = 1.15; // marge au-dessus du plus haut relief

// ---------------------------------------------------------------------------
// Utilitaires
// ---------------------------------------------------------------------------

function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function toLinearColor(rgb, fallback) {
  const src = Array.isArray(rgb) && rgb.length >= 3 ? rgb : fallback;
  const c = new THREE.Color();
  c.setRGB(srgbToLinear(src[0]), srgbToLinear(src[1]), srgbToLinear(src[2]));
  return c;
}

/**
 * Seuil de bruit donnant la fraction couverte demandee.
 *
 * Le fBm de valeur du shader se distribue de facon quasi normale, de moyenne
 * ~0.509 et d'ecart-type ~0.131 (mesure par rendu, en tenant compte de
 * l'epaississement oblique). On inverse donc la loi normale : le quantile est
 * approche par la fonction logistique, largement assez precis ici.
 */
function thresholdForCoverage(coverage) {
  const p = clamp(coverage, 0.002, 0.998);
  const probit = 0.5513 * Math.log(p / (1 - p));
  return clamp(0.464 - 0.131 * probit, 0.28, 0.92);
}

/** Teinte normalisee (composante max ramenee a 1) : sert a colorer sans assombrir. */
function normalizedTint(rgb, fallback) {
  const c = toLinearColor(rgb, fallback);
  const m = Math.max(c.r, c.g, c.b);
  if (m > 1e-4) c.setRGB(c.r / m, c.g / m, c.b / m);
  else c.setRGB(1, 1, 1);
  return c;
}

// ---------------------------------------------------------------------------
// Shaders
// ---------------------------------------------------------------------------

const VERT = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>

varying vec3 vPos;

void main() {
  // Coque centree sur la planete : l'espace objet EST l'espace local planete.
  vPos = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
}
`;

const FRAG = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_fragment>
// tonemapping_pars_fragment et colorspace_pars_fragment sont deja injectes par
// three dans le prefixe des ShaderMaterial : les inclure ici serait une
// redefinition (erreur de compilation).

uniform vec3 uSunDir;       // local planete, unitaire
uniform vec3 uCameraLocal;  // local planete, metres
uniform vec3 uCloudColor;   // lineaire
uniform vec3 uSunsetTint;   // teinte de terminateur, lineaire normalisee
uniform vec2 uRotCS;        // cos / sin de l'angle de rotation du bruit
uniform float uTime;
uniform float uScale;
uniform float uThreshold;
uniform float uOpacity;
uniform float uWarp;
uniform float uInside;      // 1 si la camera est sous la coque

varying vec3 vPos;

// Hash sans sinus (stable sur tous les pilotes) -> [0, 1[.
float hash13(vec3 p3) {
  p3 = fract(p3 * 0.1031);
  p3 += dot(p3, p3.zyx + 31.32);
  return fract((p3.x + p3.y) * p3.z);
}

// Bruit de valeur 3D interpole en smoothstep.
float vnoise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = x - i;
  f = f * f * (3.0 - 2.0 * f);
  float n000 = hash13(i);
  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));
  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));
  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));
  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));
  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));
  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));
  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));
  return mix(
    mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
    mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y),
    f.z
  );
}

float fbm2(vec3 p) {
  return 0.65 * vnoise(p) + 0.35 * vnoise(p * 2.11 + 5.3);
}

float fbm(vec3 p) {
  float amp = 0.5;
  float sum = 0.0;
  float norm = 0.0;
  for (int i = 0; i < CLOUD_OCTAVES; i++) {
    sum += amp * vnoise(p);
    norm += amp;
    p = p * 2.07 + vec3(13.7, 7.3, 3.9);
    amp *= 0.52;
  }
  return sum / max(norm, 1e-5);
}

// Gaussienne : evite pow() sur un argument negatif (indefini en GLSL).
float gauss(float x, float w) {
  float t = x / w;
  return exp(-t * t);
}

// Rotation autour de l'axe des poles (+Y).
vec3 spinY(vec3 v, vec2 cs) {
  return vec3(cs.x * v.x + cs.y * v.z, v.y, -cs.y * v.x + cs.x * v.z);
}

void main() {
  #include <logdepthbuf_fragment>

  vec3 n = normalize(vPos);
  vec3 toCam = uCameraLocal - vPos;
  float camDist = length(toCam);
  vec3 v = camDist > 1e-6 ? toCam / camDist : n; // fragment -> camera
  float facing = dot(n, v);

  // Vue de l'exterieur : l'hemisphere lointain de la coque est jete, sinon la
  // couche se dessine deux fois (faces avant et arriere, sans depthWrite).
  if (uInside < 0.5 && facing <= 0.0) discard;

  // Le bruit est echantillonne dans un repere tournant : la couche "avance"
  // sans que l'objet ne tourne.
  vec3 q = spinY(n, uRotCS);
  vec3 sunR = spinY(uSunDir, uRotCS);

  vec3 sp = q * uScale;
#ifdef CLOUD_WARP
  float wt = uTime * 0.35;
  vec3 wp = sp + uWarp * 2.0 * (vec3(
    fbm2(sp + vec3(0.0, 1.7, 4.2) + wt),
    fbm2(sp + vec3(5.1, 9.2, 1.3) - wt * 0.7),
    fbm2(sp + vec3(2.4, 3.8, 7.9) + wt * 0.4)
  ) - 0.5);
#else
  vec3 wp = sp + vec3(0.0, uTime * 0.12, 0.0);
#endif

  float d = fbm(wp);

  // Cellules de Hadley : le biais joue sur le SEUIL, pas sur la densite. Un
  // facteur multiplicatif decalerait la moyenne du bruit bien au-dela de son
  // ecart-type et raserait completement certaines latitudes.
  float al = abs(asin(clamp(n.y, -1.0, 1.0)));
  float bandBias =
      0.55 * gauss(al, 0.34)          // convergence equatoriale
    + 0.40 * gauss(al - 1.02, 0.30)   // fronts polaires, vers 60 deg
    - 0.45 * gauss(al - 0.52, 0.24)   // ceinture subtropicale seche, vers 30 deg
    - 0.25 * gauss(al - 1.57, 0.28);  // calottes plus seches

  // uThreshold est calibre cote JS pour que la fraction couverte suive
  // spec.clouds.coverage (cf. thresholdForCoverage).
  float thr = uThreshold - bandBias * 0.075;
  float alpha = smoothstep(thr, thr + 0.09, d);
  if (alpha <= 0.002) discard;

  // Trajet oblique plus long : la couche s'epaissit vers l'horizon.
  float grazing = max(abs(facing), 0.16);
  alpha = 1.0 - pow(max(1.0 - alpha, 0.0), 1.0 / grazing);

  // Vu de l'exterieur, on efface la toute derniere frange pour masquer la
  // silhouette polygonale de l'icosphere.
  if (uInside < 0.5) alpha *= smoothstep(0.0, 0.075, facing);

  // Auto-ombrage : un pas de bruit supplementaire vers le soleil.
  float shade = fbm2(wp + sunR * 0.42);
  float selfShadow = 1.0 - 0.42 * smoothstep(thr - 0.06, thr + 0.14, shade);

  float sd = dot(n, uSunDir);
  float lit = smoothstep(-0.22, 0.30, sd);
  float dayLight = 0.10 + 0.90 * lit; // jamais totalement noir cote nuit

  // Transluminescence : liseré lumineux sur les bords fins vus vers le soleil.
  float mu = dot(-v, uSunDir);
  float silver = pow(max(mu, 0.0), 10.0) * lit;
  float thin = 1.0 - alpha;

  vec3 col = uCloudColor * (dayLight * mix(1.0, selfShadow, lit));
  col += uCloudColor * (silver * (0.25 + 0.75 * thin) * 0.85);

  // Rougeoiement quand le soleil rase la couche.
  float lowSun = (1.0 - smoothstep(-0.02, 0.42, sd)) * lit;
  col = mix(col, col * uSunsetTint * 1.35, lowSun * 0.7);

  gl_FragColor = vec4(col, clamp(alpha, 0.0, 1.0) * uOpacity);

  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// ---------------------------------------------------------------------------
// API publique
// ---------------------------------------------------------------------------

/**
 * @param {object} params
 * @param {object} params.spec PlanetSpec (spec.clouds peut etre null)
 * @param {object} params.quality preset de qualite (cloudLayers)
 */
export function createClouds({ spec, quality }) {
  const group = new THREE.Group();
  group.name = spec ? `clouds-${spec.id}` : 'clouds';

  const cfg = spec ? spec.clouds : null;
  if (!spec || !cfg) {
    // Planete sans nuages : groupe vide mais API valide.
    group.visible = false;
    return {
      object3D: group,
      layers: [],
      update() {},
      dispose() {},
    };
  }

  const radius = spec.radius;
  const layerCount = clamp(Math.round((quality && quality.cloudLayers) || 1), 1, 2);
  const detailed = layerCount >= 2;
  const speed = Number.isFinite(cfg.speed) ? cfg.speed : 0.1;
  const coverage = clamp(Number.isFinite(cfg.coverage) ? cfg.coverage : 0.3, 0, 1);
  // Les couches se composent : 1 - (1 - c)^n. Chaque coque recoit donc une
  // couverture reduite pour que le total vu de l'espace reste spec.coverage.
  const layerCoverage = 1 - Math.pow(1 - coverage, 1 / layerCount);
  const threshold = thresholdForCoverage(layerCoverage);
  const cloudColor = toLinearColor(cfg.color, [0.94, 0.95, 0.94]);
  const sunsetTint = normalizedTint(
    spec.atmosphere ? spec.atmosphere.colorHorizon : null,
    [1.0, 0.72, 0.5],
  );

  // Altitude de base. On garantit une garde au-dessus du plus haut relief,
  // sinon la coque traverserait les montagnes.
  const baseAltitude = Math.max(1, cfg.altitude || radius * 0.025);
  const maxElev = Math.max(0, spec.maxElevation || 0);
  const clearance = Math.max(1, (maxElev * TERRAIN_CLEARANCE) / baseAltitude);

  const layers = [];

  for (let i = 0; i < layerCount; i++) {
    const altitude = baseAltitude * LAYER_K[i] * clearance;
    const layerRadius = radius + altitude;
    const geometry = new THREE.IcosahedronGeometry(layerRadius, SHELL_DETAIL);

    const uniforms = {
      uSunDir: { value: new THREE.Vector3(1, 0, 0) },
      uCameraLocal: { value: new THREE.Vector3(0, layerRadius * 2, 0) },
      uCloudColor: { value: cloudColor },
      uSunsetTint: { value: sunsetTint },
      uRotCS: { value: new THREE.Vector2(1, 0) },
      uTime: { value: 0 },
      uScale: { value: LAYER_SCALE[i] },
      uThreshold: { value: threshold },
      uOpacity: { value: 0 },
      uWarp: { value: detailed ? 0.55 : 0.3 },
      uInside: { value: 0 },
    };

    const material = new THREE.ShaderMaterial({
      name: `clouds-${spec.id}-${i}`,
      uniforms,
      vertexShader: VERT,
      fragmentShader: FRAG,
      defines: detailed
        ? { CLOUD_OCTAVES: '5', CLOUD_WARP: '1' }
        : { CLOUD_OCTAVES: '4' },
      side: THREE.DoubleSide,
      transparent: true,
      depthWrite: false,
      depthTest: true,
      blending: THREE.NormalBlending,
    });

    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `clouds-${spec.id}-${i}`;
    mesh.frustumCulled = false; // la camera peut etre a l'interieur
    mesh.renderOrder = BASE_RENDER_ORDER + i;
    group.add(mesh);

    layers.push({
      mesh,
      geometry,
      material,
      uniforms,
      altitude,
      layerRadius,
      rotFactor: LAYER_ROT[i],
      // Bande de fondu autour de la couche : evite le mur opaque en plein
      // visage quand le vaisseau la traverse.
      fadeBand: Math.max(altitude * 0.5, 40),
    });
  }

  let time = 0;
  const TWO_PI = Math.PI * 2;

  const api = {
    object3D: group,
    layers,

    /** @param {{sunDirLocal:THREE.Vector3, cameraLocal:THREE.Vector3, altitude:number}} ctx */
    update(dt, ctx) {
      if (!ctx) return;
      time += dt * speed;
      if (time > 1e6) time -= 1e6;

      const sun = ctx.sunDirLocal;
      const cam = ctx.cameraLocal;
      // L'altitude est recalculee depuis cameraLocal (source de verite) ;
      // ctx.altitude ne sert que de repli.
      const camLen = cam ? cam.length() : radius + (Number.isFinite(ctx.altitude) ? ctx.altitude : 0);
      const camAltitude = camLen - radius;

      let farthest = 0;
      let farthestDist = -1;

      for (let i = 0; i < layers.length; i++) {
        const L = layers[i];
        const u = L.uniforms;

        if (sun) u.uSunDir.value.copy(sun);
        if (cam) u.uCameraLocal.value.copy(cam);

        // Angle de rotation borne : uTime peut grandir, l'angle non.
        const angle = (time * L.rotFactor) % TWO_PI;
        u.uRotCS.value.set(Math.cos(angle), Math.sin(angle));
        u.uTime.value = time;
        u.uInside.value = camLen < L.layerRadius ? 1 : 0;

        // Fondu a la traversee.
        const dist = Math.abs(camAltitude - L.altitude);
        const fade = smoothstep(0, L.fadeBand, dist) * MAX_OPACITY;
        u.uOpacity.value = fade;
        L.mesh.visible = fade > 0.004;

        if (dist > farthestDist) {
          farthestDist = dist;
          farthest = i;
        }
      }

      // La couche la plus eloignee se dessine en premier (peinture arriere
      // vers avant), sans quoi les deux coques clignotent.
      for (let i = 0; i < layers.length; i++) {
        layers[i].mesh.renderOrder = BASE_RENDER_ORDER + (i === farthest ? 0 : 1);
      }
    },

    dispose() {
      for (const L of layers) {
        group.remove(L.mesh);
        L.geometry.dispose();
        L.material.dispose();
      }
      layers.length = 0;
    },
  };

  return api;
}
