// S01 - materiau de terrain.
//
// UN SEUL materiau par planete, partage par tous les patches du quadtree.
// Consequence importante : le shader ne peut pas deduire la position d'un
// vertex en espace local planete a partir de `modelMatrix` (il ignore la
// transformation du groupe planete). Le centre du patch est donc pousse dans
// l'uniforme `uPatchCenter` juste avant chaque draw call, via
// `material.onBeforeRender` qui lit `mesh.userData.patchCenter`
// (voir render/quadtreeTerrain.js). `uniformsNeedUpdate` force le re-upload.
//
// Tout ce qui est calcule ici vit en ESPACE LOCAL PLANETE : uSunDir et
// uCameraLocal sont fournis deja convertis par world/planet.js.

import * as THREE from 'three';
import { BIOME_ID, getPalette } from '../../gen/palettes.js';
import { clamp } from '../../core/math.js';

const VERTEX_SHADER = /* glsl */ `
// <common> apporte isPerspectiveMatrix(), requis par le depth logarithmique.
#include <common>
#include <logdepthbuf_pars_vertex>

uniform vec3 uPatchCenter;
uniform vec3 uCameraLocal;
uniform float uPlanetRadius;

varying vec3 vLocal;
varying vec3 vGeoNormal;
varying vec3 vTint;
varying float vCamDist;
varying float vElev;

void main() {
  // Les positions du patch sont relatives a son centre (precision float32).
  vec3 local = position + uPatchCenter;
  vLocal = local;
  vGeoNormal = normalize(normal);

  #ifdef USE_COLOR
    vTint = color;
  #else
    vTint = vec3(0.5);
  #endif

  // Distance camera exacte, calculee en espace local (pas d'aller-retour vue).
  vCamDist = length(local - uCameraLocal);
  vElev = length(local) - uPlanetRadius;

  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);

  // Le moteur active logarithmicDepthBuffer : sans ce chunk, le terrain se
  // battrait en profondeur avec les materiaux integres de three.
  #include <logdepthbuf_vertex>
}
`;

const FRAGMENT_SHADER = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_fragment>

uniform vec3 uSunDir;
uniform vec3 uCameraLocal;
uniform float uPlanetRadius;
uniform float uSeaLevel;
uniform float uMaxElevation;
uniform vec3 uFogColor;
uniform float uFogDensity;
uniform float uAtmoHeight;
uniform float uTime;
uniform vec3 uNightAmbient;
uniform float uSnowLine;
uniform float uDetailScale;
uniform float uDetailStrength;
uniform vec3 uSnowColor;
uniform vec3 uRockColor;

#ifdef HAS_DETAIL
  uniform sampler2D uDetailNormal;
#endif

varying vec3 vLocal;
varying vec3 vGeoNormal;
varying vec3 vTint;
varying float vCamDist;
varying float vElev;

float sat01(float x) { return clamp(x, 0.0, 1.0); }

#ifdef HAS_DETAIL
// Perturbation triplanaire : on projette la position locale sur les trois plans
// de base et on melange selon la normale. Aucune couture entre patches puisque
// la position est continue en espace planete.
vec3 detailPerturbation(vec3 p, vec3 n) {
  vec3 w = abs(n);
  w = w * w * w * w;
  float wsum = w.x + w.y + w.z + 1e-5;
  w /= wsum;

  float s = 1.0 / max(uDetailScale, 0.001);
  vec2 tx = texture2D(uDetailNormal, p.zy * s).xy * 2.0 - 1.0;
  vec2 ty = texture2D(uDetailNormal, p.xz * s).xy * 2.0 - 1.0;
  vec2 tz = texture2D(uDetailNormal, p.xy * s).xy * 2.0 - 1.0;

  vec3 pert = vec3(0.0);
  pert += w.x * vec3(0.0, tx.y, tx.x);
  pert += w.y * vec3(ty.x, 0.0, ty.y);
  pert += w.z * vec3(tz.x, tz.y, 0.0);
  return pert;
}
#endif

void main() {
  #include <logdepthbuf_fragment>

  vec3 radial = normalize(vLocal);
  vec3 N = normalize(vGeoNormal);
  vec3 albedo = vTint;

  // -- micro-relief, attenue avec la distance pour tuer l'aliasing ----------
  #ifdef HAS_DETAIL
    float fadeNear = uDetailScale * 6.0;
    float fadeFar = uDetailScale * 70.0;
    float detailFade = 1.0 - smoothstep(fadeNear, fadeFar, vCamDist);
    if (detailFade > 0.002) {
      vec3 pert = detailPerturbation(vLocal, N);
      N = normalize(N + pert * (uDetailStrength * detailFade));
    }
  #endif

  // -- pente : 1 = plat, 0 = falaise ---------------------------------------
  float flatness = sat01(dot(N, radial));
  float steep = 1.0 - smoothstep(0.70, 0.94, flatness);

  // Roche apparente sur les pentes fortes : cela souligne enormement le relief.
  albedo = mix(albedo, uRockColor, steep * 0.6);

  // -- neige d'altitude ----------------------------------------------------
  float ref = uSeaLevel;
  float above = (vElev - ref) / max(uMaxElevation, 1.0);
  float lat = abs(radial.y);
  // La ligne de neige descend vers les poles.
  float line = uSnowLine - lat * lat * 0.55;
  float snow = smoothstep(line, line + 0.20, above);
  // La neige ne tient pas sur les parois verticales.
  snow *= smoothstep(0.55, 0.82, flatness);
  albedo = mix(albedo, uSnowColor, sat01(snow) * 0.88);

  // -- eclairage -----------------------------------------------------------
  vec3 L = normalize(uSunDir);
  float ndl = dot(N, L);
  float lambert = max(ndl, 0.0);
  float wrapped = sat01(ndl * 0.5 + 0.5);
  // Melange lambert / wrap : terminateur doux, sans plat total cote nuit.
  float diffuse = mix(lambert, wrapped * wrapped, 0.32);

  // Nuit geometrique : un point de l'autre cote de la planete reste noir meme
  // si sa normale locale regarde le soleil.
  // Terminateur large : le crepuscule dure, ce qui evite de basculer d'un coup
  // dans le noir absolu quand on longe la ligne jour/nuit.
  float dayFactor = smoothstep(-0.30, 0.22, dot(radial, L));
  diffuse *= dayFactor;

  // Lumiere rebond depuis le sol + ciel : tres faible, juste pour que les
  // faces a l'ombre ne soient pas des trous noirs.
  float upness = dot(N, radial) * 0.5 + 0.5;
  vec3 bounce = albedo * (0.11 * (1.0 - upness) + 0.05 * upness) * dayFactor;

  vec3 lit = albedo * diffuse + bounce + albedo * uNightAmbient;

  // -- brouillard atmospherique -------------------------------------------
  if (uFogDensity > 0.0) {
    float fogAmount = 1.0 - exp(-vCamDist * uFogDensity);
    // Les sommets qui depassent la couche basse sont moins voiles.
    float hRef = max(uAtmoHeight * 0.35, 1.0);
    float hFall = exp(-max(vElev - ref, 0.0) / hRef);
    fogAmount *= mix(1.0, hFall, 0.55);
    lit = mix(lit, uFogColor, sat01(fogAmount));
  }

  gl_FragColor = vec4(lit, 1.0);

  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function paletteColor(palette, biomeId, out) {
  const o = biomeId * 3;
  // La palette est deja en lineaire (cf. gen/palettes.js).
  return out.setRGB(palette[o], palette[o + 1], palette[o + 2], THREE.LinearSRGBColorSpace);
}

/**
 * Materiau de terrain d'une planete. A creer APRES le champ de hauteur
 * (spec.seaLevel doit etre renseigne).
 *
 * @param {object} args
 * @param {object} args.spec PlanetSpec
 * @param {THREE.Texture|null} [args.paletteTexture] rampe de palette (optionnelle)
 * @param {THREE.Texture|null} [args.detailNormal] normal map de detail (optionnelle)
 * @returns {THREE.ShaderMaterial}
 */
export function createTerrainMaterial({ spec, paletteTexture = null, detailNormal = null } = {}) {
  const s = spec || {};
  const radius = s.radius || 1000;
  const maxElevation = s.maxElevation || radius * 0.05;
  const seaLevel = typeof s.seaLevel === 'number' ? s.seaLevel : 0;
  const atmoHeight = s.atmosphere ? s.atmosphere.height || 0 : 0;

  const palette = getPalette(s.palette);
  const snowColor = paletteColor(palette, BIOME_ID.SNOW, new THREE.Color());
  const rockColor = paletteColor(palette, BIOME_ID.ROCK, new THREE.Color());

  // Ambiant de nuit : teinte du ciel nocturne de la planete, tres assombrie.
  const nightAmbient = new THREE.Color(0.012, 0.014, 0.02);
  if (s.atmosphere && s.atmosphere.colorNight) {
    const c = s.atmosphere.colorNight;
    // Les couleurs du spec sont declarees en sRGB : on convertit.
    nightAmbient.setRGB(c[0], c[1], c[2], THREE.SRGBColorSpace);
  }
  // Plancher de lumiere stellaire : une nuit totalement noire rend le vol
  // impossible et n'a rien de plus realiste (il y a toujours les etoiles).
  nightAmbient.addScalar(0.05);

  // Ligne de neige : fraction de maxElevation. Un monde infernal ne voit jamais
  // de neige (> 1), un monde glacial en est couvert (< 0).
  const tempNorm = typeof s.tempNorm === 'number' ? s.tempNorm : 0.5;
  const snowLine = clamp(tempNorm * 1.45 - 0.08, -0.25, 1.7);

  const material = new THREE.ShaderMaterial({
    name: `terrain:${s.id || 'unknown'}`,
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    vertexColors: true,
    side: THREE.FrontSide,
    fog: false,
    lights: false,
    transparent: false,
    depthWrite: true,
    depthTest: true,
    defines: detailNormal ? { HAS_DETAIL: '' } : {},
    uniforms: {
      uSunDir: { value: new THREE.Vector3(0, 0, 1) },
      uCameraLocal: { value: new THREE.Vector3(0, radius * 2, 0) },
      uPlanetRadius: { value: radius },
      uSeaLevel: { value: seaLevel },
      uFogColor: { value: new THREE.Color(0, 0, 0) },
      uFogDensity: { value: 0 },
      uAtmoHeight: { value: atmoHeight },
      uTime: { value: 0 },
      uNightAmbient: { value: nightAmbient },
      uSnowLine: { value: snowLine },
      uDetailScale: { value: 40 },
      uDetailStrength: { value: 0.85 },
      // Uniformes complementaires (hors liste minimale du contrat).
      uMaxElevation: { value: maxElevation },
      uSnowColor: { value: snowColor },
      uRockColor: { value: rockColor },
      uPatchCenter: { value: new THREE.Vector3() },
      uDetailNormal: { value: detailNormal },
    },
  });

  // La rampe de palette n'est pas echantillonnee ici : les couleurs de biome
  // arrivent deja en lineaire dans l'attribut 'color' produit par le worker.
  // On garde la reference pour les modules qui en ont besoin (minimap, ocean).
  material.userData.paletteTexture = paletteTexture;
  material.userData.detailNormal = detailNormal;
  material.userData.isTerrainMaterial = true;

  // Centre du patch pousse juste avant le draw call de chaque mesh.
  material.onBeforeRender = (renderer, scene, camera, geometry, object) => {
    const center = object && object.userData ? object.userData.patchCenter : null;
    if (!center) return;
    const u = material.uniforms.uPatchCenter.value;
    if (u.x !== center.x || u.y !== center.y || u.z !== center.z) {
      u.copy(center);
    }
    // Un materiau partage : il faut forcer le re-upload a chaque mesh.
    material.uniformsNeedUpdate = true;
  };

  return material;
}

/**
 * Mise a jour par frame (appelee par world/planet.js).
 * Tous les champs sont optionnels : ce qui manque est laisse tel quel.
 */
export function updateTerrainMaterial(mat, { sunDirLocal, cameraLocal, fogColor, fogDensity, time } = {}) {
  if (!mat || !mat.uniforms) return;
  const u = mat.uniforms;
  if (sunDirLocal && u.uSunDir) u.uSunDir.value.copy(sunDirLocal).normalize();
  if (cameraLocal && u.uCameraLocal) u.uCameraLocal.value.copy(cameraLocal);
  if (fogColor && u.uFogColor) u.uFogColor.value.copy(fogColor);
  if (typeof fogDensity === 'number' && u.uFogDensity) u.uFogDensity.value = fogDensity;
  if (typeof time === 'number' && u.uTime) u.uTime.value = time;
}
