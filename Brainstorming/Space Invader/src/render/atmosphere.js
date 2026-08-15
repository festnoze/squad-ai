// Atmosphere planetaire : coque de diffusion simple couche.
//
// Modele : diffusion simple, profil de densite exponentiel exp(-h/H) avec
// H = atmosphere.height * 0.42. Pour chaque fragment de la coque on integre la
// profondeur optique le long du rayon de vue (camera -> fragment, prolonge
// jusqu'a la sortie de la coque ou jusqu'au sol), en ponderant chaque
// echantillon par la transmittance camera->echantillon. Cette ponderation est
// ce qui rend l'image continue au limbe : sans elle, le rayon rasant (juste
// dedans la silhouette) et le rayon tangent (juste dehors) donneraient des
// intensites dans un rapport 2, donc une marche visible.
//
// Consequences visuelles obtenues "gratuitement" :
//   - vue de l'espace : liseré fin et lumineux au limbe (trajet tangent long),
//     epaissi et rougeoyant vers le terminateur, nul cote nuit ;
//   - vue du sol : couleur uAtmoDay au zenith (trajet court) qui glisse vers
//     uAtmoHorizon a l'horizon (trajet long), uAtmoNight cote nuit ;
//   - halo de diffusion avant autour du soleil via une phase de
//     Henyey-Greenstein simplifiee melangee a une phase de Rayleigh.
//
// Tout se passe en ESPACE LOCAL PLANETE : origine = centre de la planete,
// +Y = axe des poles. Le module ne connait pas viewOrigin.
//
// Precision : les calculs du shader sont normalises par le rayon de la planete
// et l'intersection rayon/sphere utilise le pied de la perpendiculaire
// (m = o - d * dot(o, d)) au lieu de la forme b^2 - c, qui perd toute sa
// precision en float32 des que la camera est a quelques milliers de rayons.

import * as THREE from 'three';
import { clamp, lerp, smoothstep } from '../core/math.js';

// ---------------------------------------------------------------------------
// Constantes de reglage
// ---------------------------------------------------------------------------

const SCALE_HEIGHT_RATIO = 0.42; // H = height * ratio (cf. densityAt du contrat)
// Doit rester egal a SHELL_RATIO : sinon il existerait une couche ou l'on subit
// la trainee atmospherique sans qu'aucun ciel ne soit dessine.
const CUTOFF_RATIO = 1.2;
// La hauteur d'atmosphere est genereuse pour le pilotage (on veut pouvoir voler
// dedans), mais une coque a 2.2x cette hauteur donne vu de l'espace un halo
// enorme et laiteux. On la resserre : le liseré doit etre fin.
const SHELL_RATIO = 1.2; // rayon de coque = radius + height * 1.2
const SHELL_DETAIL = 4; // IcosahedronGeometry(_, 4) -> 500 triangles
// Volontairement modeste : la coque est additive, donc toute valeur trop haute
// voile le sol au lieu de colorer le ciel.
// Avec OPTICAL_SCALE correct, l'intensite peut redevenir franche : le ciel est
// alors bleu profond au zenith et lumineux vers l'horizon, ce qui est le bon
// gradient, au lieu d'un voile uniforme.
const BASE_INTENSITY = 0.95;
const NIGHT_RESIDUAL = 0.05; // la nuit ne diffuse pas exactement zero
const FOG_DENSITY_COEF = 0.24; // densite de brouillard = coef / radius

// ---------------------------------------------------------------------------
// Utilitaires
// ---------------------------------------------------------------------------

/** planetSpec fournit ses couleurs en sRGB 0..1 ; three travaille en lineaire. */
function srgbToLinear(c) {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function toLinearColor(rgb, fallback) {
  const src = Array.isArray(rgb) && rgb.length >= 3 ? rgb : fallback;
  const c = new THREE.Color();
  c.setRGB(srgbToLinear(src[0]), srgbToLinear(src[1]), srgbToLinear(src[2]));
  return c;
}

// Objets reutilises : aucune allocation dans update / skyColor / fogParams.
const _fogResult = { color: new THREE.Color(0, 0, 0), density: 0 };
const _skyFallback = new THREE.Color(0, 0, 0);

// ---------------------------------------------------------------------------
// Shaders
// ---------------------------------------------------------------------------

const VERT = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>

varying vec3 vPos;

void main() {
  // La coque est centree sur le centre de la planete : l'espace objet EST
  // l'espace local planete.
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

uniform vec3 uSunDir;        // local planete, unitaire
uniform vec3 uCameraLocal;   // local planete, metres
uniform float uPlanetRadius; // metres
uniform float uAtmoRadiusN;  // rayon de coque / rayon planete
uniform float uScaleHeightN; // H / rayon planete
uniform float uDensity;      // densite au niveau de la mer
uniform float uIntensity;
uniform float uInside;       // 1 si la camera est sous la coque
uniform vec3 uAtmoDay;
uniform vec3 uAtmoHorizon;
uniform vec3 uAtmoNight;

// Profondeur optique d'une colonne verticale au niveau de la mer.
const float OPTICAL_SCALE = 0.33;

varying vec3 vPos;

void main() {
  #include <logdepthbuf_fragment>

  float invR = 1.0 / uPlanetRadius;
  vec3 o = uCameraLocal * invR;
  vec3 p0 = vPos * invR;

  vec3 toFrag = p0 - o;
  float fragDist = length(toFrag);
  if (fragDist < 1e-7) discard;
  vec3 d = toFrag / fragDist;

  // Vue de l'exterieur : on ne garde que l'hemisphere proche de la coque.
  // Sinon les faces avant ET arriere integrent le meme rayon (double dose).
  // Vue de l'interieur, tout rayon ne touche la coque qu'une seule fois.
  if (uInside < 0.5 && dot(normalize(p0), d) > 0.0) discard;

  // Intersection stable : pied de la perpendiculaire au centre.
  float b = dot(o, d);
  vec3 m = o - d * b;
  float m2 = dot(m, m);

  float discAtmo = uAtmoRadiusN * uAtmoRadiusN - m2;
  if (discAtmo <= 0.0) discard;
  float sq = sqrt(discAtmo);
  float tEnter = max(-b - sq, 0.0);
  float tExit = -b + sq;

  // Le sol (rayon 1 en unites normalisees) coupe l'integrale.
  float discGround = 1.0 - m2;
  if (discGround > 0.0) {
    float tGround = -b - sqrt(discGround);
    if (tGround > tEnter) tExit = min(tExit, tGround);
  }

  float seg = tExit - tEnter;
  if (seg <= 0.0) discard;

  // On reparametre depuis l'entree : les additions restent petites, donc
  // precises, meme quand tEnter vaut plusieurs milliers.
  vec3 pEnter = o + d * tEnter;
  float ds = seg / float(ATMO_STEPS);

  // Phase : Rayleigh (dipolaire) + lobe avant Henyey-Greenstein simplifie.
  float mu = dot(d, uSunDir);
  float rayleigh = 0.75 * (1.0 + mu * mu);
  const float g = 0.55;
  const float g2 = g * g;
  float hg = (1.0 - g2) / pow(max(1.0 + g2 - 2.0 * g * mu, 1e-3), 1.5);
  float phase = 0.72 * rayleigh + 0.11 * hg;

  float od = 0.0;          // profondeur optique cumulee depuis la camera
  float scatter = 0.0;     // energie diffusee vers la camera, bornee a 1
  vec3 csum = vec3(0.0);

  for (int i = 0; i < ATMO_STEPS; i++) {
    vec3 p = pEnter + d * (ds * (float(i) + 0.5));
    float r = length(p);
    float rho = exp(-max(r - 1.0, 0.0) / uScaleHeightN);
    // OPTICAL_SCALE fixe la profondeur optique d'une colonne verticale au
    // niveau de la mer : sans lui, elle vaut ~0.94 et la coque devient un voile
    // laiteux opaque qui recouvre le disque de la planete. Un ciel bleu, c'est
    // une colonne d'environ 0.3.
    float dTau = rho * ds * uDensity * OPTICAL_SCALE / uScaleHeightN;

    vec3 n = p / max(r, 1e-4);
    float sd = dot(n, uSunDir);
    float dayF = smoothstep(-0.30, 0.25, sd);
    float lit = mix(NIGHT_RESIDUAL, 1.0, smoothstep(-0.32, 0.18, sd));
    // Soleil bas = long trajet dans l'atmosphere = couleur de terminateur.
    float low = 1.0 - smoothstep(-0.05, 0.45, sd);

    vec3 col = mix(uAtmoNight, uAtmoDay, dayF);
    col = mix(col, uAtmoHorizon, low * dayF * 0.85);
    // Trajet de vue long = ciel bas / liseré du limbe.
    // La teinte de terminateur ne doit apparaitre que sur des trajets vraiment
    // longs (vue au ras du sol), sinon la planete vue de l'espace se couvre
    // d'un voile beige.
    col = mix(col, uAtmoHorizon, saturate(od * 0.09) * (0.35 + 0.65 * dayF));

    float w = exp(-od) * dTau * lit;
    csum += col * w;
    scatter += w;
    od += dTau;
  }

  if (scatter <= 1e-6) discard;

  vec3 color = (csum / scatter) * (scatter * uIntensity * phase);
  // L'alpha porte l'extinction : le fond (sol, nuages, etoiles) est attenue par
  // 1 - exp(-od) alors que la lumiere diffusee, elle, s'ajoute. C'est le
  // compositing "premultiplie" du blending personnalise cote materiau, et c'est
  // ce qui evite qu'un disque planetaire vu de l'orbite soit simplement lave de
  // bleu : il est aussi assombri, comme une vraie perspective aerienne.
  gl_FragColor = vec4(color, 1.0 - exp(-od));

  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

// ---------------------------------------------------------------------------
// Implementation neutre (planete sans atmosphere, cf. Nyx)
// ---------------------------------------------------------------------------

function createNeutralAtmosphere() {
  const geometry = new THREE.BufferGeometry();
  const material = new THREE.MeshBasicMaterial({ visible: false });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = 'atmosphere-none';
  mesh.visible = false;
  mesh.frustumCulled = false;

  return {
    object3D: mesh,
    material,
    outerRadius: 0,
    scaleHeight: 0,
    update() {},
    densityAt() {
      return 0;
    },
    skyColor(sunDirLocal, cameraLocal, out) {
      const c = out || _skyFallback;
      c.setRGB(0, 0, 0);
      return c;
    },
    fogParams() {
      _fogResult.color.setRGB(0, 0, 0);
      _fogResult.density = 0;
      return _fogResult;
    },
    dispose() {
      geometry.dispose();
      material.dispose();
    },
  };
}

// ---------------------------------------------------------------------------
// API publique
// ---------------------------------------------------------------------------

/**
 * @param {object} params
 * @param {object} params.spec PlanetSpec (spec.atmosphere peut etre null)
 */
export function createAtmosphere({ spec }) {
  if (!spec || !spec.atmosphere) return createNeutralAtmosphere();

  const atmo = spec.atmosphere;
  const radius = spec.radius;
  const height = Math.max(1, atmo.height || radius * 0.08);
  const scaleHeight = height * SCALE_HEIGHT_RATIO;
  const densitySea = atmo.densitySea > 0 ? atmo.densitySea : 1;
  const outerRadius = radius + height * SHELL_RATIO;

  const colDay = toLinearColor(atmo.colorDay, [0.5, 0.68, 0.86]);
  const colHorizon = toLinearColor(atmo.colorHorizon, [0.85, 0.76, 0.64]);
  const colNight = toLinearColor(atmo.colorNight, [0.04, 0.06, 0.11]);

  const geometry = new THREE.IcosahedronGeometry(outerRadius, SHELL_DETAIL);

  const uniforms = {
    uSunDir: { value: new THREE.Vector3(1, 0, 0) },
    uCameraLocal: { value: new THREE.Vector3(0, radius + 1, 0) },
    uPlanetRadius: { value: radius },
    uAtmoRadiusN: { value: outerRadius / radius },
    uScaleHeightN: { value: scaleHeight / radius },
    uDensity: { value: densitySea },
    uIntensity: { value: BASE_INTENSITY },
    uInside: { value: 0 },
    uAtmoDay: { value: colDay },
    uAtmoHorizon: { value: colHorizon },
    uAtmoNight: { value: colNight },
  };

  const material = new THREE.ShaderMaterial({
    name: `atmosphere-${spec.id}`,
    uniforms,
    vertexShader: VERT,
    fragmentShader: FRAG,
    defines: {
      ATMO_STEPS: '8',
      NIGHT_RESIDUAL: NIGHT_RESIDUAL.toFixed(3),
    },
    side: THREE.DoubleSide,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    // Compositing en alpha premultiplie : dst * (1 - alpha) + src.
    // src = lumiere diffusee (deja en radiance), alpha = extinction du fond.
    blending: THREE.CustomBlending,
    blendEquation: THREE.AddEquation,
    blendSrc: THREE.OneFactor,
    blendDst: THREE.OneMinusSrcAlphaFactor,
    blendEquationAlpha: THREE.AddEquation,
    blendSrcAlpha: THREE.OneFactor,
    blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.name = `atmosphere-${spec.id}`;
  mesh.frustumCulled = false; // la camera peut etre a l'interieur de la coque
  mesh.renderOrder = 12; // apres le sol, l'ocean et les nuages

  // Etat scalaire reutilise.
  const cutoff = height * CUTOFF_RATIO;
  const taperStart = height * CUTOFF_RATIO * 0.75;
  const fogBase = FOG_DENSITY_COEF / radius;

  /** Densite relative (0..densitySea) a une altitude donnee, en metres. */
  function densityAt(altitude) {
    const a = altitude > 0 ? altitude : 0;
    if (a >= cutoff) return 0;
    // Coupure douce pour ne pas laisser une marche a height * 2.
    const taper = smoothstep(cutoff, taperStart, a);
    return Math.exp(-a / scaleHeight) * densitySea * taper;
  }

  /**
   * Couleur moyenne du ciel. `horizonBias` pousse vers la couleur d'horizon
   * (le brouillard est horizontal, le ciel plutot zenithal).
   */
  function composeSky(sunDot, altitude, horizonBias, gain, out) {
    const sd = clamp(sunDot, -1, 1);
    const dayF = smoothstep(-0.28, 0.24, sd);
    const low = 1 - smoothstep(-0.04, 0.42, sd);
    const warm = low * dayF * 0.85;

    let r = lerp(colNight.r, colDay.r, dayF);
    let g = lerp(colNight.g, colDay.g, dayF);
    let b = lerp(colNight.b, colDay.b, dayF);

    r = lerp(r, colHorizon.r, warm);
    g = lerp(g, colHorizon.g, warm);
    b = lerp(b, colHorizon.b, warm);

    if (horizonBias > 0) {
      r = lerp(r, colHorizon.r, horizonBias);
      g = lerp(g, colHorizon.g, horizonBias);
      b = lerp(b, colHorizon.b, horizonBias);
    }

    // Meme saturation que le shader : 1 - exp(-colonne restante).
    const column = densityAt(altitude);
    const brightness =
      (1 - Math.exp(-column)) * BASE_INTENSITY * gain * lerp(0.06, 1, dayF);

    out.setRGB(r * brightness, g * brightness, b * brightness);
    return out;
  }

  const api = {
    object3D: mesh,
    material,
    outerRadius,
    scaleHeight,

    /** @param {{sunDirLocal:THREE.Vector3, cameraLocal:THREE.Vector3, altitude:number}} ctx */
    update(dt, ctx) {
      if (!ctx) return;
      if (ctx.sunDirLocal) uniforms.uSunDir.value.copy(ctx.sunDirLocal);
      if (ctx.cameraLocal) {
        uniforms.uCameraLocal.value.copy(ctx.cameraLocal);
        uniforms.uInside.value = ctx.cameraLocal.lengthSq() < outerRadius * outerRadius ? 1 : 0;
      }
    },

    densityAt,

    /** Couleur moyenne du ciel a la position camera (lineaire). */
    skyColor(sunDirLocal, cameraLocal, out) {
      const c = out || _skyFallback;
      if (!sunDirLocal || !cameraLocal) {
        c.setRGB(0, 0, 0);
        return c;
      }
      const len = cameraLocal.length() || 1;
      const sunDot =
        (cameraLocal.x * sunDirLocal.x +
          cameraLocal.y * sunDirLocal.y +
          cameraLocal.z * sunDirLocal.z) /
        len;
      return composeSky(sunDot, len - radius, 0.25, 1, c);
    },

    /**
     * Brouillard atmospherique pour le terrain et l'ocean.
     * L'objet retourne est reutilise a chaque appel : a consommer aussitot.
     */
    fogParams(altitude, sunDot) {
      const alt = Number.isFinite(altitude) ? altitude : 0;
      const sd = Number.isFinite(sunDot) ? sunDot : 1;
      composeSky(sd, alt, 0.7, 1.25, _fogResult.color);
      _fogResult.density = fogBase * densityAt(alt);
      return _fogResult;
    },

    /** Reglage debug (lil-gui). */
    setIntensity(v) {
      uniforms.uIntensity.value = clamp(v, 0, 4);
    },

    dispose() {
      geometry.dispose();
      material.dispose();
    },
  };

  return api;
}
