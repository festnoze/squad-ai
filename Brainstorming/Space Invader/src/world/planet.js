// Une planete : assemble le terrain LOD, l'ocean, l'atmosphere, les nuages et
// la vie, et fournit toutes les requetes geometriques dont le vol a besoin.
//
// Deux etats :
//   - PROXY   : loin, une simple sphere ombree + un halo (12 corps a l'ecran).
//   - ACTIVE  : proche, tout l'appareillage procedural est monte.
//
// Rappel du repere : l'espace local a pour origine le centre de la planete et
// pour axe des poles +Y. La planete ne tourne PAS ; c'est la direction du soleil
// qui tourne dans ce repere (cf. _updateSunDir).

import * as THREE from 'three';
import { getQuality } from '../core/settings.js';
import { latLonFromUnit } from '../core/math.js';
import { createHeightField } from '../gen/heightField.js';
import { createTerrainPool } from '../gen/workerPool.js';
import { createPlanetMaps } from '../gen/heightmapTexture.js';
import { createDetailNormalTexture } from '../gen/textures.js';
import { createTerrainMaterial, updateTerrainMaterial } from '../render/materials/terrainMaterial.js';
import { QuadtreeTerrain } from '../render/quadtreeTerrain.js';
import { createOcean } from '../render/ocean.js';
import { createAtmosphere } from '../render/atmosphere.js';
import { createClouds } from '../render/clouds.js';
import { createGasGiant } from '../render/gasGiant.js';
import { createVegetation } from '../life/vegetation.js';
import { createFauna } from '../life/fauna.js';
import { getPalette, BIOME_ID, biomeName } from '../gen/palettes.js';

const _v1 = new THREE.Vector3();
const _v2 = new THREE.Vector3();
const _v3 = new THREE.Vector3();
const _v4 = new THREE.Vector3();
const _v5 = new THREE.Vector3();
const _q1 = new THREE.Quaternion();
const _c1 = new THREE.Color();

const PROXY_VERT = /* glsl */ `
  varying vec3 vNormalLocal;
  varying vec3 vViewDir;
  void main() {
    vNormalLocal = normalize(position);
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vViewDir = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }
`;

const PROXY_FRAG = /* glsl */ `
  uniform vec3 uSunDir;
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uAtmoColor;
  uniform float uAtmoStrength;
  varying vec3 vNormalLocal;
  varying vec3 vViewDir;

  void main() {
    vec3 n = normalize(vNormalLocal);
    float lat = abs(n.y);
    vec3 base = mix(uColorA, uColorB, smoothstep(0.35, 0.95, lat));
    float ndl = dot(n, normalize(uSunDir));
    float lit = smoothstep(-0.22, 0.32, ndl);
    vec3 col = base * (0.06 + lit * 1.15);
    // Liseré atmospherique au limbe, du cote eclaire.
    float rim = pow(1.0 - clamp(dot(n, normalize(vViewDir)), 0.0, 1.0), 2.6);
    col += uAtmoColor * rim * uAtmoStrength * max(0.0, ndl + 0.3);
    gl_FragColor = vec4(col, 1.0);
  }
`;

export class Planet {
  constructor({ spec, quality = getQuality() }) {
    this.spec = spec;
    this.quality = quality;
    this.heightField = createHeightField(spec); // renseigne spec.seaLevel

    this.absolutePosition = new THREE.Vector3().fromArray(spec.orbitPosition);
    this.object3D = new THREE.Group();
    this.object3D.name = `planet-${spec.id}`;
    // Inclinaison de l'axe : la seule rotation appliquee a la geometrie.
    this.object3D.quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), spec.axialTilt);
    this._invQuat = this.object3D.quaternion.clone().invert();

    this.sunDirLocal = new THREE.Vector3(1, 0, 0);
    this.sunDirWorld = new THREE.Vector3(1, 0, 0);
    this.spinAngle = spec.spinPhase;

    this._active = false;
    this._activating = false;
    this._parts = null;
    this._proxy = this._buildProxy();
    this.object3D.add(this._proxy.mesh, this._proxy.glow);

    this.fogColor = new THREE.Color(0, 0, 0);
    this.fogDensity = 0;
    this.insideGas = 0;
    this.localHour = 0;
  }

  // -------------------------------------------------------------------------
  // Proxy lointain
  // -------------------------------------------------------------------------
  _buildProxy() {
    const spec = this.spec;
    const pal = getPalette(spec.palette);
    const warm = spec.isGas ? spec.gas.colorA : sampleBiomeColor(pal, spec);
    const cold = spec.isGas
      ? spec.gas.colorB
      : [pal[BIOME_ID.SNOW * 3], pal[BIOME_ID.SNOW * 3 + 1], pal[BIOME_ID.SNOW * 3 + 2]];
    const atmo = spec.atmosphere ? spec.atmosphere.colorDay : [0.4, 0.5, 0.6];

    const material = new THREE.ShaderMaterial({
      vertexShader: PROXY_VERT,
      fragmentShader: PROXY_FRAG,
      uniforms: {
        uSunDir: { value: this.sunDirLocal },
        uColorA: { value: new THREE.Vector3(warm[0], warm[1], warm[2]) },
        uColorB: { value: new THREE.Vector3(cold[0], cold[1], cold[2]) },
        uAtmoColor: { value: new THREE.Vector3(atmo[0], atmo[1], atmo[2]) },
        uAtmoStrength: { value: spec.atmosphere ? 1.6 : 0.15 },
      },
    });
    const mesh = new THREE.Mesh(new THREE.IcosahedronGeometry(spec.radius, 4), material);
    mesh.frustumCulled = false;

    // Halo : garantit qu'une planete reste un point lumineux visible de tres loin.
    const glowMat = new THREE.SpriteMaterial({
      color: new THREE.Color().setRGB(atmo[0], atmo[1], atmo[2]),
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      map: radialSprite(),
    });
    const glow = new THREE.Sprite(glowMat);
    glow.frustumCulled = false;

    return { mesh, glow, material, glowMat };
  }

  // -------------------------------------------------------------------------
  // Activation / desactivation
  // -------------------------------------------------------------------------
  get isActive() {
    return this._active;
  }

  get isBusy() {
    return this._activating;
  }

  async activate() {
    if (this._active || this._activating) return;
    this._activating = true;
    const spec = this.spec;
    const quality = this.quality;
    try {
      if (spec.isGas) {
        // Pas de coque d'atmosphere ici : une geante gazeuse EST une
        // atmosphere. Superposer la coque de diffusion voilait completement ses
        // bandes. La densite pour la trainee reste calculee analytiquement par
        // atmosphereDensityAt().
        const gas = createGasGiant({ spec, quality });
        this._parts = { gas };
        this.object3D.add(gas.object3D);
      } else {
        const pool = await createTerrainPool(spec, quality.workerCount);
        const maps = await createPlanetMaps({ spec, pool, size: quality.heightmapSize });
        const detailNormal = createDetailNormalTexture(256);
        const material = createTerrainMaterial({
          spec,
          paletteTexture: maps.biomeTexture,
          detailNormal,
        });
        const terrain = new QuadtreeTerrain({
          spec,
          heightField: this.heightField,
          pool,
          material,
          quality,
        });
        const ocean = createOcean({ spec, maps, quality });
        const atmosphere = createAtmosphere({ spec });
        const clouds = createClouds({ spec, quality });
        const vegetation = createVegetation({ spec, heightField: this.heightField, pool, quality });
        const fauna = createFauna({ spec, heightField: this.heightField, pool, quality });

        const offReady = terrain.onPatchReady((p) => {
          vegetation.addPatch(p);
          fauna.addPatch(p);
        });
        const offRemoved = terrain.onPatchRemoved((key) => {
          vegetation.removePatch(key);
          fauna.removePatch(key);
        });

        this._parts = {
          pool,
          maps,
          detailNormal,
          material,
          terrain,
          ocean,
          atmosphere,
          clouds,
          vegetation,
          fauna,
          offReady,
          offRemoved,
        };
        this.object3D.add(
          terrain.object3D,
          ocean.object3D,
          clouds.object3D,
          vegetation.object3D,
          fauna.object3D,
          atmosphere.object3D,
        );
      }
      this._proxy.mesh.visible = false;
      this._active = true;
    } catch (err) {
      console.error(`[planet] activation de ${spec.name} impossible`, err);
      this._parts = null;
    } finally {
      this._activating = false;
    }
  }

  deactivate() {
    if (!this._active) return;
    const p = this._parts;
    this._active = false;
    this._parts = null;
    if (p) {
      if (p.offReady) p.offReady();
      if (p.offRemoved) p.offRemoved();
      for (const key of ['terrain', 'ocean', 'atmosphere', 'clouds', 'vegetation', 'fauna', 'gas']) {
        const part = p[key];
        if (!part) continue;
        if (part.object3D) this.object3D.remove(part.object3D);
        if (part.dispose) part.dispose();
      }
      if (p.maps) p.maps.dispose();
      if (p.detailNormal) p.detailNormal.dispose();
      if (p.material) p.material.dispose();
      if (p.pool) p.pool.dispose();
    }
    this._proxy.mesh.visible = true;
  }

  // -------------------------------------------------------------------------
  // Requetes geometriques
  // -------------------------------------------------------------------------

  /** Absolu -> local planete (sans rotation propre : la planete ne tourne pas). */
  toLocal(abs, out) {
    return out.copy(abs).sub(this.absolutePosition).applyQuaternion(this._invQuat);
  }

  toAbs(local, out) {
    return out.copy(local).applyQuaternion(this.object3D.quaternion).add(this.absolutePosition);
  }

  /** Verticale locale, en absolu. */
  upAt(abs, out) {
    return out.copy(abs).sub(this.absolutePosition).normalize();
  }

  distanceTo(abs) {
    return abs.distanceTo(this.absolutePosition);
  }

  /** Rayon du sol solide sous une position absolue. */
  terrainRadiusAt(abs) {
    if (this.spec.isGas) return 0;
    this.toLocal(abs, _v1).normalize();
    return this.heightField.surfaceRadius(_v1);
  }

  /** Rayon de la surface "posable" : sol, ou niveau de la mer si immerge. */
  groundRadiusAt(abs) {
    if (this.spec.isGas) return 0;
    this.toLocal(abs, _v1).normalize();
    const elev = this.heightField.elevation(_v1.x, _v1.y, _v1.z);
    const sea = this.spec.seaLevel;
    const surface = sea !== null && elev < sea ? sea : elev;
    return this.spec.radius + surface;
  }

  altitudeOf(abs) {
    const d = this.distanceTo(abs);
    if (this.spec.isGas) return d - this.spec.radius;
    return d - this.groundRadiusAt(abs);
  }

  isOverWater(abs) {
    if (this.spec.seaLevel === null || this.spec.isGas) return false;
    this.toLocal(abs, _v1).normalize();
    return this.heightField.elevation(_v1.x, _v1.y, _v1.z) < this.spec.seaLevel;
  }

  biomeIdAt(abs) {
    if (this.spec.isGas) return BIOME_ID.ASH;
    this.toLocal(abs, _v1).normalize();
    const elev = this.heightField.elevation(_v1.x, _v1.y, _v1.z);
    return this.heightField.biomeId(_v1.x, _v1.y, _v1.z, elev);
  }

  biomeNameAt(abs) {
    return biomeName(this.biomeIdAt(abs));
  }

  /** Latitude / longitude du survol, pour la minimap. */
  latLonAt(abs) {
    this.toLocal(abs, _v1).normalize();
    return latLonFromUnit(_v1);
  }

  atmosphereDensityAt(abs) {
    const parts = this._parts;
    const alt = this.altitudeOf(abs);
    if (parts && parts.atmosphere) return parts.atmosphere.densityAt(alt);
    if (!this.spec.atmosphere) return 0;
    // Repli analytique quand la planete n'est pas encore active.
    const h = this.spec.atmosphere.height;
    if (alt > h * 2) return 0;
    return Math.exp(-Math.max(0, alt) / (h * 0.42)) * this.spec.atmosphere.densitySea;
  }

  insideGasAt(abs) {
    if (!this.spec.isGas) return 0;
    const parts = this._parts;
    if (parts && parts.gas) {
      this.toLocal(abs, _v1);
      return parts.gas.insideFactorAt(_v1);
    }
    const r = this.distanceTo(abs);
    const lim = this.spec.radius * 1.02;
    if (r > lim) return 0;
    return Math.min(1, (lim - r) / (this.spec.radius * 0.5));
  }

  get vegetation() {
    return this._parts ? this._parts.vegetation : null;
  }

  get fauna() {
    return this._parts ? this._parts.fauna : null;
  }

  get maps() {
    return this._parts ? this._parts.maps : null;
  }

  get terrainStats() {
    return this._parts && this._parts.terrain ? this._parts.terrain.stats : null;
  }

  // -------------------------------------------------------------------------
  // Frame
  // -------------------------------------------------------------------------

  _updateSunDir(elapsed) {
    // Direction planete -> soleil (le soleil est a l'origine absolue).
    _v1.copy(this.absolutePosition).negate().normalize();
    // Passage en local (on annule l'inclinaison de l'axe).
    _v1.applyQuaternion(this._invQuat);
    // Rotation propre : c'est le soleil qui tourne autour de l'axe des poles.
    this.spinAngle = this.spec.spinPhase + (elapsed / this.spec.dayLength) * Math.PI * 2;
    _q1.setFromAxisAngle(UP_LOCAL, -this.spinAngle);
    this.sunDirLocal.copy(_v1).applyQuaternion(_q1).normalize();
    this.sunDirWorld.copy(this.sunDirLocal).applyQuaternion(this.object3D.quaternion);
  }

  /**
   * Heure solaire locale au point survole (0 = minuit, 12 = midi).
   * Elle depend de la longitude du joueur, pas seulement de la rotation de la
   * planete : deux points opposes ne sont jamais a la meme heure.
   */
  localHourAt(abs) {
    this.toLocal(abs, _v4);
    const shipLon = Math.atan2(_v4.z, _v4.x);
    const subsolarLon = Math.atan2(this.sunDirLocal.z, this.sunDirLocal.x);
    let hourAngle = shipLon - subsolarLon;
    // Ramene dans [-PI, PI].
    while (hourAngle > Math.PI) hourAngle -= Math.PI * 2;
    while (hourAngle < -Math.PI) hourAngle += Math.PI * 2;
    let h = 12 - (hourAngle * 12) / Math.PI;
    if (h < 0) h += 24;
    if (h >= 24) h -= 24;
    return h;
  }

  /** Hauteur du soleil sur l'horizon local, en radians (negatif = nuit). */
  sunElevationAt(abs) {
    this.upAt(abs, _v4);
    _v5.copy(this.sunDirLocal).applyQuaternion(this.object3D.quaternion);
    return Math.asin(Math.max(-1, Math.min(1, _v4.dot(_v5))));
  }

  update(dt, ctx) {
    const spec = this.spec;
    // Position en espace vue.
    this.object3D.position.copy(this.absolutePosition).sub(ctx.viewOrigin);
    this._updateSunDir(ctx.elapsed);
    this.localHour = this.localHourAt(ctx.cameraAbsPos);
    this._proxy.material.uniforms.uSunDir.value.copy(this.sunDirLocal);

    const dist = this.distanceTo(ctx.cameraAbsPos);
    // Halo : jamais plus petit que ~0.5 pour cent de la distance, pour rester repérable.
    const glowSize = Math.max(spec.radius * 2.4, dist * 0.006);
    this._proxy.glow.scale.setScalar(glowSize);
    this._proxy.glow.material.opacity = this._active ? 0 : 0.5;
    this._proxy.glow.visible = !this._active;

    if (!this._active) {
      this.fogDensity = 0;
      this.insideGas = 0;
      return;
    }

    const parts = this._parts;
    const cameraLocal = this.toLocal(ctx.cameraAbsPos, _v2);
    const altitude = this.altitudeOf(ctx.cameraAbsPos);
    const sunDot = this.upAt(ctx.cameraAbsPos, _v3).dot(
      _v1.copy(this.sunDirLocal).applyQuaternion(this.object3D.quaternion),
    );

    if (spec.isGas) {
      this.insideGas = parts.gas.insideFactorAt(cameraLocal);
      parts.gas.update(dt, {
        sunDirLocal: this.sunDirLocal,
        cameraLocal,
        insideFactor: this.insideGas,
      });
      const fog = parts.gas.fogFor(this.insideGas, _c1);
      this.fogColor.copy(fog.color);
      this.fogDensity = fog.density;
      return;
    }

    const fog = parts.atmosphere.fogParams(altitude, sunDot);
    this.fogColor.copy(fog.color);
    this.fogDensity = fog.density;

    parts.terrain.update(cameraLocal, dt);
    updateTerrainMaterial(parts.material, {
      sunDirLocal: this.sunDirLocal,
      cameraLocal,
      fogColor: this.fogColor,
      fogDensity: this.fogDensity,
      time: ctx.elapsed,
    });
    parts.ocean.update(dt, {
      sunDirLocal: this.sunDirLocal,
      cameraLocal,
      cameraAltitude: altitude,
    });
    parts.clouds.update(dt, { sunDirLocal: this.sunDirLocal, cameraLocal, altitude });
    parts.atmosphere.update(dt, { sunDirLocal: this.sunDirLocal, cameraLocal, altitude });
    parts.vegetation.update(dt, { cameraLocal, sunDirLocal: this.sunDirLocal });
    parts.fauna.update(dt, { cameraLocal, sunDirLocal: this.sunDirLocal });
  }

  /** Element de vie le plus proche, en distance absolue (metres). */
  nearestTree(abs) {
    const veg = this.vegetation;
    if (!veg) return null;
    return veg.nearest(this.toLocal(abs, _v1));
  }

  nearestFauna(abs) {
    const f = this.fauna;
    if (!f) return null;
    return f.nearest(this.toLocal(abs, _v1));
  }

  dispose() {
    this.deactivate();
    this._proxy.mesh.geometry.dispose();
    this._proxy.material.dispose();
    this._proxy.glowMat.dispose();
    if (this._proxy.glowMat.map) this._proxy.glowMat.map.dispose();
  }
}

const UP_LOCAL = new THREE.Vector3(0, 1, 0);

/** Teinte moyenne "vue de loin" : melange des biomes dominants de la palette. */
function sampleBiomeColor(pal, spec) {
  const ids = spec.seaLevel !== null && spec.seaFraction > 0.3
    ? [BIOME_ID.DEEP_OCEAN, BIOME_ID.FOREST, BIOME_ID.GRASS, BIOME_ID.DESERT]
    : [BIOME_ID.DESERT, BIOME_ID.ROCK, BIOME_ID.SAVANNA, BIOME_ID.ASH];
  let r = 0;
  let g = 0;
  let b = 0;
  for (const id of ids) {
    r += pal[id * 3];
    g += pal[id * 3 + 1];
    b += pal[id * 3 + 2];
  }
  const n = ids.length;
  return [(r / n) * 1.35, (g / n) * 1.35, (b / n) * 1.35];
}

let _sprite = null;

/** Petit degradé radial partage par tous les halos de planete. */
function radialSprite() {
  if (_sprite) return _sprite;
  const size = 128;
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, 'rgba(255,255,255,0.85)');
  grd.addColorStop(0.28, 'rgba(255,255,255,0.28)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, size, size);
  _sprite = new THREE.CanvasTexture(c);
  _sprite.colorSpace = THREE.SRGBColorSpace;
  return _sprite;
}
