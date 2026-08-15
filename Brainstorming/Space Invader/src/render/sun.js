// Soleil (A12, S06, T08) : noyau emissif granule + couronne additive + lumiere
// directionnelle du systeme.
//
// Le groupe est place chaque frame en ESPACE VUE par update({ sunViewPos }).
// main.js reste maitre de light.position / light.target : on se contente de
// creer la lumiere, de l'ajouter au groupe et de moduler son intensite.

import * as THREE from 'three';
import { clamp, saturate, smoothstep } from '../core/math.js';
import { SCALE } from '../core/settings.js';

const CORE_VERT = /* glsl */ `
  uniform float uRadius;
  varying vec3 vUnit;
  varying vec3 vNormalView;
  varying vec3 vViewDir;

  void main() {
    vUnit = position / max(uRadius, 1.0);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    vNormalView = normalize(normalMatrix * normal);
    vViewDir = normalize(-mvPosition.xyz);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const CORE_FRAG = /* glsl */ `
  // <common> fournit saturate(), PI, etc. (non injecte d'office pour un
  // ShaderMaterial, contrairement aux chunks de tonemapping/colorspace).
  #include <common>

  uniform float uTime;
  uniform vec3 uColorCore;
  uniform vec3 uColorEdge;
  uniform float uIntensity;

  varying vec3 vUnit;
  varying vec3 vNormalView;
  varying vec3 vViewDir;

  float hash31(vec3 p) {
    p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }

  float vnoise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash31(i + vec3(0.0, 0.0, 0.0)), hash31(i + vec3(1.0, 0.0, 0.0)), f.x),
          mix(hash31(i + vec3(0.0, 1.0, 0.0)), hash31(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
      mix(mix(hash31(i + vec3(0.0, 0.0, 1.0)), hash31(i + vec3(1.0, 0.0, 1.0)), f.x),
          mix(hash31(i + vec3(0.0, 1.0, 1.0)), hash31(i + vec3(1.0, 1.0, 1.0)), f.x), f.y),
      f.z);
  }

  float fbm(vec3 p) {
    float s = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
      s += a * vnoise(p);
      p *= 2.03;
      a *= 0.5;
    }
    return s;
  }

  void main() {
    // Granulation : deux echelles qui derivent lentement en sens opposes.
    vec3 p = vUnit * 7.0;
    float g1 = fbm(p + vec3(0.0, uTime * 0.045, uTime * 0.02));
    float g2 = fbm(vUnit * 19.0 - vec3(uTime * 0.06, 0.0, uTime * 0.03));
    float granule = g1 * 0.72 + g2 * 0.38;

    // Assombrissement centre-bord.
    float limb = saturate(dot(normalize(vNormalView), normalize(vViewDir)));
    float darken = pow(limb, 0.55);

    vec3 col = mix(uColorEdge, uColorCore, saturate(darken * 0.85 + granule * 0.35));
    // Filaments chauds dans les sillons de la granulation.
    col += uColorEdge * pow(saturate(1.0 - granule), 3.0) * 0.45;

    float energy = uIntensity * (0.75 + granule * 0.55) * (0.45 + 0.55 * darken);
    gl_FragColor = vec4(col * energy, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`;

/**
 * Sprite radial additif genere sur canvas (T08). Aucun asset binaire.
 * `power` durcit le degrade, `tint` est une couleur sRGB 0..255.
 */
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

/** Couleur tolerante : 'fff2d8', '#fff2d8', 0xfff2d8 ou [r, g, b] lineaire. */
function toColor(value, fallback) {
  const c = new THREE.Color();
  if (typeof value === 'number' && Number.isFinite(value)) {
    c.setHex(value, THREE.SRGBColorSpace);
  } else if (typeof value === 'string' && value.length) {
    const style = /^[0-9a-f]{3,8}$/i.test(value) ? `#${value}` : value;
    try {
      c.setStyle(style, THREE.SRGBColorSpace);
    } catch (err) {
      c.setStyle(fallback, THREE.SRGBColorSpace);
    }
  } else if (Array.isArray(value) && value.length >= 3) {
    c.setRGB(value[0], value[1], value[2]);
  } else {
    c.setStyle(fallback, THREE.SRGBColorSpace);
  }
  return c;
}

export function createSun({ star, quality } = {}) {
  const s = star || {};
  const radius = typeof s.radius === 'number' && s.radius > 0 ? s.radius : SCALE.SUN_RADIUS;
  const baseIntensity = typeof s.intensity === 'number' ? s.intensity : 3.0;
  const q = quality || {};
  const detail = q.name === 'low' ? 3 : 4;

  const coreColor = toColor(s.color, '#fff2d8');
  const coronaColor = toColor(s.coronaColor, '#ffb64a');

  const object3D = new THREE.Group();
  object3D.name = 'sun';

  // --- Noyau -------------------------------------------------------------
  const coreGeometry = new THREE.IcosahedronGeometry(radius, detail);
  const coreMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uRadius: { value: radius },
      uColorCore: { value: coreColor.clone() },
      uColorEdge: { value: coronaColor.clone() },
      uIntensity: { value: 2.35 },
    },
    vertexShader: CORE_VERT,
    fragmentShader: CORE_FRAG,
    transparent: false,
    depthWrite: true,
  });
  const coreMesh = new THREE.Mesh(coreGeometry, coreMaterial);
  coreMesh.frustumCulled = false;
  object3D.add(coreMesh);

  // --- Couronne (2 sprites additifs) -------------------------------------
  const innerTex = createRadialSprite(256, 2.6, [255, 236, 190]);
  const outerTex = createRadialSprite(256, 1.35, [255, 168, 74]);

  const innerMat = new THREE.SpriteMaterial({
    map: innerTex,
    color: coreColor.clone(),
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: true,
    opacity: 0.9,
  });
  const outerMat = new THREE.SpriteMaterial({
    map: outerTex,
    color: coronaColor.clone(),
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    depthTest: true,
    opacity: 0.55,
  });

  const innerSprite = new THREE.Sprite(innerMat);
  const outerSprite = new THREE.Sprite(outerMat);
  innerSprite.renderOrder = 5;
  outerSprite.renderOrder = 4;
  innerSprite.frustumCulled = false;
  outerSprite.frustumCulled = false;
  const INNER_BASE = radius * 2.4;
  const OUTER_BASE = radius * 4.2;
  innerSprite.scale.set(INNER_BASE, INNER_BASE, 1);
  outerSprite.scale.set(OUTER_BASE, OUTER_BASE, 1);
  object3D.add(outerSprite);
  object3D.add(innerSprite);

  // --- Lumieres ----------------------------------------------------------
  // main.js pilote light.position et light.target ; la lumiere vit dans le
  // groupe (seule sa DIRECTION compte pour une DirectionalLight).
  const light = new THREE.DirectionalLight(0xfff1d6, baseIntensity);
  light.castShadow = false;
  object3D.add(light);
  object3D.add(light.target);

  const ambient = new THREE.AmbientLight(0x0a0f18, 1.0);
  object3D.add(ambient);

  let time = 0;

  return {
    object3D,
    light,
    ambient,

    update(dt, ctx) {
      const d = typeof dt === 'number' && dt > 0 ? dt : 0;
      time += d;
      coreMaterial.uniforms.uTime.value = time;

      const c = ctx || {};
      if (c.sunViewPos) object3D.position.copy(c.sunViewPos);

      // Distance au soleil : fournie, sinon deduite de la position vue.
      let dist = typeof c.distanceToSun === 'number' && c.distanceToSun > 0 ? c.distanceToSun : 0;
      if (!dist) {
        if (c.sunViewPos && c.cameraViewPos) dist = c.sunViewPos.distanceTo(c.cameraViewPos);
        else if (c.sunViewPos) dist = c.sunViewPos.length();
      }
      if (!(dist > 0)) dist = SCALE.AU;

      // Couronne un peu plus large de pres.
      const near = 1 - smoothstep(radius * 3.0, radius * 60.0, dist);
      const grow = 1 + 0.42 * near;
      const inner = INNER_BASE * grow;
      const outer = OUTER_BASE * (1 + 0.28 * near);
      innerSprite.scale.set(inner, inner, 1);
      outerSprite.scale.set(outer, outer, 1);
      // Les Sprite se tournent seuls vers la camera (billboard integre).

      // Eclairage en 1/d^2 normalise a 1 UA, borne pour rester jouable loin.
      const ratio = SCALE.AU / dist;
      const falloff = clamp(ratio * ratio, 0.25, 2.2);
      light.intensity = baseIntensity * falloff;
      coreMaterial.uniforms.uIntensity.value = 2.35 * (0.85 + 0.15 * saturate(falloff));
    },

    dispose() {
      object3D.remove(coreMesh);
      object3D.remove(innerSprite);
      object3D.remove(outerSprite);
      object3D.remove(light);
      object3D.remove(light.target);
      object3D.remove(ambient);
      coreGeometry.dispose();
      coreMaterial.dispose();
      innerMat.dispose();
      outerMat.dispose();
      innerTex.dispose();
      outerTex.dispose();
      light.dispose();
      ambient.dispose();
    },
  };
}
