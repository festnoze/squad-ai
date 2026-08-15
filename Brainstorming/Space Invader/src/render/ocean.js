// Ocean planetaire : une icosphere au rayon du niveau de la mer, deformee par
// trois vagues de Gerstner et eclairee par un shader dedie (fresnel, specular
// du soleil, profondeur lue dans la heightmap, ecume de rivage).
//
// Espace de travail : LOCAL PLANETE. Le maillage est a l'identite dans le
// groupe de la planete, donc l'espace objet du shader EST l'espace local.
// C'est pour cela qu'on n'utilise jamais `modelMatrix` ici : `uSunDir` et
// `uCameraLocal` arrivent deja en local, et le groupe parent porte l'axe de
// rotation de la planete.
//
// Trois types de mer sont geres (`spec.seaType`) : 'water', 'lava', 'ice'.

import * as THREE from 'three';
import { damp, saturate, smoothstep } from '../core/math.js';
import { BIOME_ID, getPalette } from '../gen/palettes.js';

// Profils par type de mer. Tout ce qui change entre eau, lave et glace.
const SEA_PROFILES = {
  water: {
    define: 'OCEAN_WATER',
    ampScale: 1.0,
    lenScale: 1.0,
    speed: 1.0,
    shininess: 320.0,
    fresnel0: 0.022,
    fresnelStrength: 1.0,
    specStrength: 2.6,
    opacity: 0.9,
    shoreTransparency: 0.55,
    foam: 1.0,
    emissive: 0.0,
    night: 0.09,
  },
  lava: {
    define: 'OCEAN_LAVA',
    ampScale: 2.4,
    lenScale: 2.6,
    speed: 0.26,
    shininess: 44.0,
    fresnel0: 0.05,
    fresnelStrength: 0.28,
    specStrength: 0.7,
    opacity: 0.995,
    shoreTransparency: 1.0,
    foam: 0.75,
    emissive: 1.9,
    night: 0.5,
  },
  ice: {
    define: 'OCEAN_ICE',
    ampScale: 0.0,
    lenScale: 1.0,
    speed: 0.0,
    shininess: 26.0,
    fresnel0: 0.06,
    fresnelStrength: 0.55,
    specStrength: 1.1,
    opacity: 0.985,
    shoreTransparency: 0.9,
    foam: 0.4,
    emissive: 0.0,
    night: 0.11,
  },
};

const VERT = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>

uniform float uTime;
uniform float uAgitation;
uniform vec3 uWaveAmp;
uniform vec3 uWaveLen;
uniform vec3 uWaveAngle;
uniform float uWaveSpeed;

varying vec3 vLocalPos;
varying vec3 vLocalNormal;
varying vec3 vSphereDir;
varying float vCrest;

// Une vague de Gerstner sur la sphere : la phase suit la distance parcourue le
// long de la direction tangente d, ce qui reste continu sur toute la sphere.
void addWave(
  in vec3 pos, in vec3 dir, in vec3 t, in vec3 b,
  in float amp, in float len, in float ang,
  inout vec3 disp, inout vec3 grad, inout float crest
) {
  if (amp <= 0.0 || len <= 0.0) return;
  vec3 d = t * cos(ang) + b * sin(ang);
  float k = PI2 / len;
  float omega = sqrt(9.81 * k) * uWaveSpeed;
  float phase = k * dot(pos, d) - uTime * omega;
  float s = sin(phase);
  float c = cos(phase);
  // Composante verticale (radiale) + pincement horizontal caracteristique.
  disp += dir * (amp * s) + d * (amp * 0.5 * c);
  grad += d * (amp * k * c);
  crest += s;
}

void main() {
  vec3 dir = normalize(position);
  vSphereDir = dir;

  // Base tangente locale. La reference +Y ne degenere qu'exactement aux poles,
  // ce qui evite toute couture visible sur la mer.
  vec3 t = cross(vec3(0.0, 1.0, 0.0), dir);
  float tl = length(t);
  t = tl > 1e-4 ? t / tl : vec3(1.0, 0.0, 0.0);
  vec3 b = cross(dir, t);

  vec3 disp = vec3(0.0);
  vec3 grad = vec3(0.0);
  float crest = 0.0;
  float a = uAgitation;
  addWave(position, dir, t, b, uWaveAmp.x * a, uWaveLen.x, uWaveAngle.x, disp, grad, crest);
  addWave(position, dir, t, b, uWaveAmp.y * a, uWaveLen.y, uWaveAngle.y, disp, grad, crest);
  addWave(position, dir, t, b, uWaveAmp.z * a, uWaveLen.z, uWaveAngle.z, disp, grad, crest);

  vec3 p = position + disp;
  vLocalPos = p;
  vLocalNormal = normalize(dir - grad);
  vCrest = crest / 3.0;

  vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mvPosition;

  #include <logdepthbuf_vertex>
}
`;

const FRAG = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_fragment>

uniform float uTime;
uniform vec3 uSunDir;
uniform vec3 uCameraLocal;
uniform sampler2D uHeightMap;
uniform float uSeaRadius;
uniform float uSeaLevel;
uniform float uMaxElevation;
uniform vec3 uDeepColor;
uniform vec3 uShallowColor;
uniform vec3 uFoamColor;
uniform vec3 uSkyColor;
uniform float uOpacity;
uniform float uNight;
uniform float uAgitation;
uniform float uFresnel0;
uniform float uFresnelStrength;
uniform float uSpecStrength;
uniform float uShininess;
uniform float uEmissive;
uniform float uFoamAmount;
uniform float uShoreAlpha;

varying vec3 vLocalPos;
varying vec3 vLocalNormal;
varying vec3 vSphereDir;
varying float vCrest;

void main() {
  #include <logdepthbuf_fragment>

  vec3 n = normalize(vLocalNormal);
  vec3 dir = normalize(vSphereDir);
  vec3 toEye = uCameraLocal - vLocalPos;
  vec3 v = normalize(toEye);

  // Elevation du fond, lue dans la heightmap equirectangulaire.
  float lat = asin(clamp(dir.y, -1.0, 1.0));
  float lon = atan(dir.z, dir.x);
  vec2 mapUv = vec2(lon / PI2 + 0.5, 0.5 - lat / PI);
  float floorElev = texture2D(uHeightMap, mapUv).r;
  float depth = max(0.0, uSeaLevel - floorElev);

  // Hauts-fonds : melange vers la couleur claire quand le fond remonte.
  float range = max(25.0, uMaxElevation * 0.12);
  float shallow = 1.0 - saturate(depth / range);
  shallow = shallow * shallow;

  // Eclairage. Le terminateur est pilote par la sphere, pas par la normale de
  // vague, sinon les cretes s'allumeraient en pleine nuit.
  float sunSphere = dot(dir, uSunDir);
  float dayLight = smoothstep(-0.12, 0.20, sunSphere);
  float diff = saturate(dot(n, uSunDir) * 0.85 + 0.15);

  vec3 base = mix(uDeepColor, uShallowColor, shallow);
  vec3 col = base * (0.14 + 0.86 * diff) * mix(uNight, 1.0, dayLight);

  // Fresnel de Schlick : reflet du ciel au ras de l'eau.
  float fres = uFresnel0 + (1.0 - uFresnel0) * pow(1.0 - saturate(dot(n, v)), 5.0);
  vec3 sky = uSkyColor * mix(uNight * 1.4, 1.0, dayLight);
  col = mix(col, sky, saturate(fres * uFresnelStrength));

  // Specular Blinn-Phong dur : le chemin de lumiere du soleil sur la mer.
  vec3 h = normalize(v + uSunDir);
  float spec = pow(saturate(dot(n, h)), uShininess) * uSpecStrength * dayLight;
  col += uFoamColor * spec;

  // Ecume : bande de rivage animee + un peu de mousse sur les cretes.
  // (smoothstep exige edge0 < edge1 : on inverse le resultat.)
  float band = 1.0 - smoothstep(0.0, 8.0, depth);
  float ripple = 0.5 + 0.5 * sin(depth * 0.9 - uTime * 2.4);
  float foam = band * (0.5 + 0.5 * ripple);
  foam += saturate(vCrest - 0.72) * 1.4 * uAgitation * shallow;
  foam = saturate(foam * uFoamAmount);
  col = mix(col, uFoamColor * mix(uNight * 2.0, 1.0, dayLight), foam);

  #ifdef OCEAN_LAVA
  // Lave : emission propre, visible de nuit et attrapee par le bloom.
  float pulse = 0.62 + 0.38 * sin(uTime * 0.6 + dir.x * 41.0) * sin(uTime * 0.43 + dir.z * 33.0);
  col += uShallowColor * (uEmissive * pulse * (0.45 + 0.55 * shallow));
  #endif

  // Transparence : plus lisible en haut-fond (on devine la plage), quasi
  // opaque au large, renforcee par le fresnel et l'ecume.
  float alpha = mix(uOpacity, uOpacity * uShoreAlpha, shallow);
  alpha = saturate(alpha + fres * 0.3 + foam * 0.45);

  gl_FragColor = vec4(col, alpha);

  // Tone mapping et espace de sortie : ces deux chunks sont neutres quand le
  // rendu passe par le composer (OutputPass s'en charge) et actifs quand on
  // rend directement a l'ecran (preset low, sans bloom).
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

/**
 * @param {object} opts
 * @param {object} opts.spec PlanetSpec (spec.seaLevel doit etre calibre)
 * @param {object} [opts.maps] resultat de createPlanetMaps
 * @param {object} [opts.quality] preset de qualite
 */
export function createOcean({ spec, maps, quality } = {}) {
  const seaLevel = spec ? spec.seaLevel : null;
  const hasSea = !!spec && !spec.isGas && typeof seaLevel === 'number' && isFinite(seaLevel);

  if (!hasSea) {
    // Pas de mer : on renvoie quand meme un objet valide et inerte.
    const empty = new THREE.Group();
    empty.name = spec ? `ocean-none-${spec.id}` : 'ocean-none';
    return {
      object3D: empty,
      update() {},
      dispose() {},
    };
  }

  const prof = SEA_PROFILES[spec.seaType] || SEA_PROFILES.water;
  const palette = getPalette(spec.palette);
  const seaRadius = spec.radius + seaLevel;

  // ---------------------------------------------------------------------
  // Geometrie
  // ---------------------------------------------------------------------
  // `oceanSubdiv` est un niveau de qualite (5 a 7), pas un nombre de segments :
  // on le traduit en subdivision d'icosphere pour tenir le budget de ~40k tris
  // annonce dans docs/ASSETS.md (detail = 40 -> 20 * 41^2 = 33 620 triangles).
  const subdiv = quality && typeof quality.oceanSubdiv === 'number' ? quality.oceanSubdiv : 6;
  const detail = Math.round(Math.min(64, Math.max(8, subdiv * 8 - 8)));
  const geometry = new THREE.IcosahedronGeometry(seaRadius, detail);
  // Le shader recalcule tout depuis `position` : ces deux attributs sont du
  // poids mort en memoire GPU.
  geometry.deleteAttribute('uv');
  geometry.deleteAttribute('normal');

  // ---------------------------------------------------------------------
  // Couleurs
  // ---------------------------------------------------------------------
  const deepColor = new THREE.Color();
  const shallowColor = new THREE.Color();
  const foamColor = new THREE.Color();
  const skyColor = new THREE.Color();

  if (prof.define === 'OCEAN_LAVA') {
    setLinear(deepColor, palette, BIOME_ID.LAVA);
    setLinear(shallowColor, palette, BIOME_ID.LAVA);
    deepColor.multiplyScalar(0.28);
    shallowColor.multiplyScalar(1.35);
    foamColor.setRGB(1.0, 0.72, 0.28, THREE.LinearSRGBColorSpace);
  } else if (prof.define === 'OCEAN_ICE') {
    setLinear(deepColor, palette, BIOME_ID.ICE);
    setLinear(shallowColor, palette, BIOME_ID.ICE);
    deepColor.multiplyScalar(0.82);
    shallowColor.multiplyScalar(1.1);
    foamColor.setRGB(0.95, 0.98, 1.0, THREE.LinearSRGBColorSpace);
  } else {
    setLinear(deepColor, palette, BIOME_ID.DEEP_OCEAN);
    setLinear(shallowColor, palette, BIOME_ID.SHALLOW_OCEAN);
    shallowColor.multiplyScalar(1.15);
    foamColor.setRGB(0.92, 0.97, 1.0, THREE.LinearSRGBColorSpace);
  }

  // Couleur du reflet : le ciel de la planete, ou une lueur stellaire faible
  // si le monde n'a pas d'atmosphere.
  const atmo = spec.atmosphere;
  if (atmo && atmo.colorDay) {
    // planetSpec fournit des composantes sRGB : on laisse three convertir.
    skyColor.setRGB(atmo.colorDay[0], atmo.colorDay[1], atmo.colorDay[2], THREE.SRGBColorSpace);
  } else {
    skyColor.setRGB(0.06, 0.08, 0.12, THREE.LinearSRGBColorSpace);
  }

  // ---------------------------------------------------------------------
  // Vagues
  // ---------------------------------------------------------------------
  const ampBase = Math.max(0.12, spec.radius * 0.00015) * prof.ampScale;
  const lenBase = Math.max(6, spec.radius * 0.0051) * prof.lenScale;

  const heightMap = maps && maps.heightTexture ? maps.heightTexture : null;
  // Sans carte, on simule un fond profond et uniforme (aucun haut-fond).
  const fallbackMap = heightMap ? null : makeFallbackHeightMap(spec, seaLevel);

  const uniforms = {
    uTime: { value: 0 },
    uSunDir: { value: new THREE.Vector3(0, 0, 1) },
    uCameraLocal: { value: new THREE.Vector3(0, seaRadius * 2, 0) },
    uHeightMap: { value: heightMap || fallbackMap },
    uSeaRadius: { value: seaRadius },
    uSeaLevel: { value: seaLevel },
    uMaxElevation: { value: Math.max(1, spec.maxElevation || spec.radius * 0.05) },
    uDeepColor: { value: deepColor },
    uShallowColor: { value: shallowColor },
    uFoamColor: { value: foamColor },
    uSkyColor: { value: skyColor },
    uOpacity: { value: prof.opacity },
    uNight: { value: prof.night },
    uAgitation: { value: 1 },
    uWaveAmp: { value: new THREE.Vector3(ampBase, ampBase * 0.62, ampBase * 0.34) },
    uWaveLen: { value: new THREE.Vector3(lenBase, lenBase * 0.47, lenBase * 0.21) },
    uWaveAngle: { value: new THREE.Vector3(0.0, 2.1, 4.35) },
    uWaveSpeed: { value: prof.speed },
    uFresnel0: { value: prof.fresnel0 },
    uFresnelStrength: { value: prof.fresnelStrength },
    uSpecStrength: { value: prof.specStrength },
    uShininess: { value: prof.shininess },
    uEmissive: { value: prof.emissive },
    uFoamAmount: { value: prof.foam },
    uShoreAlpha: { value: prof.shoreTransparency },
  };

  const defines = {};
  defines[prof.define] = '';

  const material = new THREE.ShaderMaterial({
    name: `ocean-${spec.id}`,
    uniforms,
    defines,
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: true,
    depthTest: true,
    side: THREE.FrontSide,
    toneMapped: true,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = `ocean-${spec.id}`;
  mesh.frustumCulled = true;
  mesh.renderOrder = 2;
  mesh.matrixAutoUpdate = false;
  mesh.updateMatrix();

  // ---------------------------------------------------------------------
  // Boucle
  // ---------------------------------------------------------------------
  // Etat lisse pour eviter tout a-coup, et aucune allocation par frame.
  let time = 0;
  let agitation = 1;
  let opacity = prof.opacity;
  let targetAgitation = 1;
  let targetOpacity = prof.opacity;
  const altNear = Math.max(60, spec.radius * 0.004);
  const altFar = Math.max(altNear * 4, spec.radius * 0.09);
  const calmSea = prof.ampScale <= 0;

  function update(dt, ctx) {
    const d = Math.min(Math.max(dt || 0, 0), 0.1);
    time += d;
    uniforms.uTime.value = time;

    if (ctx) {
      if (ctx.sunDirLocal) {
        uniforms.uSunDir.value.copy(ctx.sunDirLocal);
        const l = uniforms.uSunDir.value.length();
        if (l > 1e-6) uniforms.uSunDir.value.multiplyScalar(1 / l);
      }
      if (ctx.cameraLocal) uniforms.uCameraLocal.value.copy(ctx.cameraLocal);
      if (typeof ctx.cameraAltitude === 'number') {
        // 1 au ras des flots, 0 en orbite : la mer se calme et se lisse.
        const close = 1 - smoothstep(altNear, altFar, ctx.cameraAltitude);
        targetAgitation = calmSea ? 0 : 0.06 + 0.94 * close;
        targetOpacity = prof.opacity * (0.9 + 0.1 * close);
      }
    }

    agitation = damp(agitation, targetAgitation, 2.5, d);
    opacity = damp(opacity, targetOpacity, 3.0, d);
    uniforms.uAgitation.value = saturate(agitation);
    uniforms.uOpacity.value = opacity;
  }

  let disposed = false;

  return {
    object3D: mesh,
    update,
    dispose() {
      if (disposed) return;
      disposed = true;
      geometry.dispose();
      material.dispose();
      // La heightmap appartient a `maps` : on ne detruit que notre secours.
      if (fallbackMap) fallbackMap.dispose();
      if (mesh.parent) mesh.parent.remove(mesh);
    },
  };
}

// -------------------------------------------------------------------------
// Interne
// -------------------------------------------------------------------------

function setLinear(color, palette, biomeId) {
  const o = biomeId * 3;
  // getPalette renvoie deja du lineaire.
  color.setRGB(palette[o], palette[o + 1], palette[o + 2], THREE.LinearSRGBColorSpace);
  return color;
}

/** Heightmap 1x1 de secours : un fond uniforme bien en dessous du niveau de la mer. */
function makeFallbackHeightMap(spec, seaLevel) {
  const deep = seaLevel - Math.max(120, Math.abs(spec.maxElevation || spec.radius * 0.05) * 0.5);
  const tex = new THREE.DataTexture(
    new Float32Array([deep]),
    1,
    1,
    THREE.RedFormat,
    THREE.FloatType,
  );
  tex.name = 'ocean-fallback-heightmap';
  tex.colorSpace = THREE.NoColorSpace;
  tex.minFilter = THREE.NearestFilter;
  tex.magFilter = THREE.NearestFilter;
  tex.generateMipmaps = false;
  tex.needsUpdate = true;
  return tex;
}
