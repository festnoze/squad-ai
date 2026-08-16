// Vegetation instanciee, streamee par patch de terrain (assets A08, A09, D04).
//
// Espace de travail : ESPACE LOCAL PLANETE (origine = centre planete, +Y = axe
// des poles). Ce module ne connait jamais viewOrigin.
//
// Principes de performance :
//  - 4 especes d'arbres + 1 rocher, chaque geometrie construite UNE fois par
//    fusion de primitives (mergeGeometries), colorees par vertex ;
//  - un InstancedMesh par espece, capacite fixe allouee au demarrage, liste
//    libre d'index (pile) et borne haute (mesh.count) pour ne jamais dessiner
//    d'instances mortes ;
//  - zero allocation et zero ecriture de matrice par frame : le balancement au
//    vent est fait dans le vertex shader (deux uniformes partages) ;
//  - nearest() ne parcourt que les patches dont le centre est a moins de 3 km.

import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { clamp, hashString, mulberry32 } from '../core/math.js';
import { getQuality } from '../core/settings.js';
import { BIOME_ID, VEGETATION_BIOMES, getPalette, isWaterBiome } from '../gen/palettes.js';

// ---------------------------------------------------------------------------
// Reglages
// ---------------------------------------------------------------------------

const TREE_CAPACITY = 4000; // instances max par espece d'arbre
const ROCK_CAPACITY = 3000;
const TREE_BASE_COUNT = 90; // candidats demandes par patch, avant densite
const TREE_COUNT_MAX = 240;
const ROCK_RATIO = 0.3;
const ROCK_COUNT_MAX = 80;
const NEAR_RANGE = 3000; // rayon de recherche de nearest(), en metres

// Base de paquetage (espece, slot) -> entier unique, pour la liste de slots
// memorisee par cle de patch.
const PACK_BASE = Math.max(TREE_CAPACITY, ROCK_CAPACITY) + 1;

// ---------------------------------------------------------------------------
// D04 - Table des especes d'arbres : biomes valides, taille, couleurs
// ---------------------------------------------------------------------------

export const TREE_SPECIES = [
  {
    key: 'conifer',
    name: 'Conifere',
    height: 20,
    biomes: [BIOME_ID.FOREST, BIOME_ID.GRASS, BIOME_ID.SNOW],
    trunkFrom: [BIOME_ID.ASH, 0.95],
    leafFrom: [BIOME_ID.FOREST, 1.0],
    doubleSide: false,
    wind: 0.018,
  },
  {
    key: 'broadleaf',
    name: 'Feuillu',
    height: 15,
    biomes: [BIOME_ID.FOREST, BIOME_ID.GRASS, BIOME_ID.SAVANNA],
    trunkFrom: [BIOME_ID.ASH, 1.25],
    leafFrom: [BIOME_ID.FOREST, 1.18],
    doubleSide: false,
    wind: 0.024,
  },
  {
    key: 'palm',
    name: 'Palmier',
    height: 12,
    biomes: [BIOME_ID.JUNGLE, BIOME_ID.BEACH, BIOME_ID.SAVANNA],
    trunkFrom: [BIOME_ID.ASH, 1.45],
    leafFrom: [BIOME_ID.JUNGLE, 1.08],
    doubleSide: true,
    wind: 0.034,
  },
  {
    key: 'cycad',
    name: 'Cycas alien',
    height: 8,
    biomes: [BIOME_ID.JUNGLE, BIOME_ID.GRASS, BIOME_ID.SAVANNA],
    trunkFrom: [BIOME_ID.ASH, 0.8],
    leafFrom: [BIOME_ID.JUNGLE, 1.35],
    doubleSide: true,
    wind: 0.03,
  },
];

const ROCK_SPECIES = {
  key: 'rock',
  name: 'Rocher',
  height: 2.6,
  trunkFrom: [BIOME_ID.ROCK, 0.9],
  leafFrom: [BIOME_ID.ROCK, 0.9],
  doubleSide: false,
  wind: 0,
};

// ---------------------------------------------------------------------------
// Vecteurs temporaires (aucune allocation dans les boucles chaudes)
// ---------------------------------------------------------------------------

const UP = new THREE.Vector3(0, 1, 0);
const _pos = new THREE.Vector3();
const _nrm = new THREE.Vector3();
const _unit = new THREE.Vector3();
const _quat = new THREE.Quaternion();
const _yaw = new THREE.Quaternion();
const _scale = new THREE.Vector3();
const _mat = new THREE.Matrix4();
const _col = new THREE.Color();
const _near = { distance: 0, position: new THREE.Vector3() };

// Matrice d'instance "morte" : echelle nulle, triangles degeneres invisibles.
const DEAD_MATRIX = new THREE.Matrix4().set(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1);

// Uniformes de vent partages par tous les materiaux de vegetation.
const windUniforms = { uTime: { value: 0 }, uWind: { value: 1 } };

// ---------------------------------------------------------------------------
// Outils de geometrie
// ---------------------------------------------------------------------------

/** Convertit en non indexe (obligatoire pour fusionner des primitives melangees). */
function toNonIndexed(geo) {
  if (!geo.index) return geo;
  const out = geo.toNonIndexed();
  geo.dispose();
  return out;
}

/** Peint une geometrie d'une couleur lineaire uniforme (attribut color). */
function paint(geo, color) {
  const n = geo.attributes.position.count;
  const arr = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    arr[i * 3] = color.r;
    arr[i * 3 + 1] = color.g;
    arr[i * 3 + 2] = color.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(arr, 3));
  geo.deleteAttribute('uv1');
  return geo;
}

/** Prepare une primitive : non indexee, transformee, coloree. */
function part(geo, color, matrix) {
  const g = toNonIndexed(geo);
  if (matrix) g.applyMatrix4(matrix);
  return paint(g, color);
}

/**
 * Bruit lisse purement fonction de la position : deux sommets dupliques a la
 * meme position recoivent le meme deplacement, donc pas de fissure.
 */
function wobble(x, y, z, seedA, seedB) {
  return (
    Math.sin(x * 2.7 + seedA) * Math.sin(y * 3.1 + seedB) * 0.6 +
    Math.sin(z * 2.3 + seedB * 1.7) * Math.sin(x * 1.9 - seedA) * 0.4
  );
}

/** Icosphere deformee (feuillage ou rocher). */
function blobGeometry(radius, detail, squashY, amount, seedA, seedB) {
  const g = toNonIndexed(new THREE.IcosahedronGeometry(radius, detail));
  const pos = g.attributes.position;
  const inv = 1 / radius;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    const z = pos.getZ(i);
    const k = 1 + wobble(x * inv, y * inv, z * inv, seedA, seedB) * amount;
    pos.setXYZ(i, x * k, y * k * squashY, z * k);
  }
  g.computeVertexNormals();
  return g;
}

/** Palme / lame : plan etire selon +X, couche a plat, avec affaissement. */
function bladeGeometry(length, width, segments, droop) {
  const g = toNonIndexed(new THREE.PlaneGeometry(length, width, segments, 1));
  g.rotateX(-Math.PI / 2); // le plan passe de XY a XZ
  g.translate(length * 0.5, 0, 0); // il part de l'origine vers +X
  const pos = g.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const t = clamp(pos.getX(i) / length, 0, 1);
    // Affaissement quadratique + pincement de la pointe.
    pos.setY(i, pos.getY(i) - t * t * droop);
    pos.setZ(i, pos.getZ(i) * (1 - t * 0.72));
  }
  g.computeVertexNormals();
  return g;
}

function trunkGeometry(rTop, rBottom, height, radial) {
  return new THREE.CylinderGeometry(rTop, rBottom, height, radial, 1, true);
}

// ---------------------------------------------------------------------------
// Constructeurs d'especes (une geometrie fusionnee par espece)
// ---------------------------------------------------------------------------

function buildConifer(h, trunkColor, leafColor) {
  const parts = [];
  const m = new THREE.Matrix4();
  parts.push(part(trunkGeometry(0.022 * h, 0.05 * h, 0.9 * h, 6), trunkColor, m.makeTranslation(0, 0.45 * h, 0)));
  // Cones fermes (openEnded = false) : le dessous reste opaque en FrontSide.
  const tiers = [
    [0.26, 0.215, 0.32],
    [0.46, 0.180, 0.30],
    [0.64, 0.140, 0.28],
    [0.80, 0.095, 0.24],
  ];
  for (let i = 0; i < tiers.length; i++) {
    const [y, r, len] = tiers[i];
    const cone = new THREE.ConeGeometry(r * h, len * h, 9, 1, false);
    parts.push(part(cone, leafColor, m.makeTranslation(0, (y + len * 0.5) * h, 0)));
  }
  return mergeGeometries(parts, false);
}

function buildBroadleaf(h, trunkColor, leafColor) {
  const parts = [];
  const m = new THREE.Matrix4();
  parts.push(part(trunkGeometry(0.03 * h, 0.055 * h, 0.62 * h, 6), trunkColor, m.makeTranslation(0, 0.31 * h, 0)));
  parts.push(
    part(blobGeometry(0.30 * h, 1, 0.62, 0.22, 1.7, 4.1), leafColor, m.makeTranslation(0.03 * h, 0.72 * h, -0.02 * h)),
  );
  parts.push(
    part(blobGeometry(0.21 * h, 1, 0.58, 0.26, 5.3, 2.2), leafColor, m.makeTranslation(-0.08 * h, 0.92 * h, 0.05 * h)),
  );
  return mergeGeometries(parts, false);
}

function buildPalm(h, trunkColor, leafColor) {
  const parts = [];
  const m = new THREE.Matrix4();
  const segs = 5;
  const segLen = (h * 0.78) / segs;
  const bend = 0.42;
  let px = 0;
  let py = 0;
  for (let i = 0; i < segs; i++) {
    const a0 = bend * Math.pow(i / segs, 1.3);
    const a1 = bend * Math.pow((i + 1) / segs, 1.3);
    const am = (a0 + a1) * 0.5;
    const dx = Math.sin(am);
    const dy = Math.cos(am);
    const rTop = 0.028 * h * (1 - (i + 1) / segs * 0.35);
    const rBot = 0.032 * h * (1 - (i / segs) * 0.35);
    m.makeRotationZ(-am);
    m.setPosition(px + dx * segLen * 0.5, py + dy * segLen * 0.5, 0);
    parts.push(part(trunkGeometry(rTop, rBot, segLen * 1.04, 6), trunkColor, m));
    px += dx * segLen;
    py += dy * segLen;
  }
  // Couronne de 6 palmes au sommet du tronc courbe.
  const frond = bladeGeometry(0.5 * h, 0.15 * h, 3, 0.16 * h);
  const top = new THREE.Matrix4().makeTranslation(px, py, 0);
  const rot = new THREE.Matrix4();
  const tilt = new THREE.Matrix4();
  for (let i = 0; i < 6; i++) {
    const az = (i / 6) * Math.PI * 2 + 0.3;
    rot.makeRotationY(az);
    tilt.makeRotationZ(-0.35 - (i % 2) * 0.22);
    m.copy(top).multiply(rot).multiply(tilt);
    const g = frond.clone();
    parts.push(part(g, leafColor, m));
  }
  frond.dispose();
  return mergeGeometries(parts, false);
}

function buildCycad(h, trunkColor, leafColor) {
  const parts = [];
  const m = new THREE.Matrix4();
  parts.push(part(trunkGeometry(0.09 * h, 0.13 * h, 0.34 * h, 7), trunkColor, m.makeTranslation(0, 0.17 * h, 0)));
  // Couronne de 8 lames rigides, inclinees vers le haut.
  const blade = bladeGeometry(0.72 * h, 0.11 * h, 2, 0.1 * h);
  const top = new THREE.Matrix4().makeTranslation(0, 0.33 * h, 0);
  const rot = new THREE.Matrix4();
  const tilt = new THREE.Matrix4();
  for (let i = 0; i < 8; i++) {
    const az = (i / 8) * Math.PI * 2;
    rot.makeRotationY(az);
    tilt.makeRotationZ(0.62 + (i % 3) * 0.11);
    m.copy(top).multiply(rot).multiply(tilt);
    parts.push(part(blade.clone(), leafColor, m));
  }
  blade.dispose();
  return mergeGeometries(parts, false);
}

function buildRock(h, rockColor) {
  const g = blobGeometry(h * 0.5, 1, 0.68, 0.34, 3.9, 1.4);
  g.translate(0, h * 0.16, 0);
  return paint(g, rockColor);
}

// ---------------------------------------------------------------------------
// Vent : deplacement dans le vertex shader, cout CPU nul par frame
// ---------------------------------------------------------------------------

function applyWind(material, height, amount, cacheKey) {
  if (!(amount > 0)) return;
  const invH = 1 / Math.max(1e-3, height);
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTime = windUniforms.uTime;
    shader.uniforms.uWind = windUniforms.uWind;
    shader.vertexShader =
      'uniform float uTime;\nuniform float uWind;\n' +
      shader.vertexShader.replace(
        '#include <begin_vertex>',
        [
          '#include <begin_vertex>',
          '#ifdef USE_INSTANCING',
          '{',
          '  float vegPhase = instanceMatrix[3].x * 0.021 + instanceMatrix[3].z * 0.017;',
          `  float vegH = clamp(transformed.y * ${invH.toFixed(6)}, 0.0, 1.4);`,
          `  float vegSway = sin(uTime * 1.15 + vegPhase) * ${amount.toFixed(5)} * uWind * vegH * vegH;`,
          `  transformed.x += vegSway * ${height.toFixed(3)};`,
          `  transformed.z += vegSway * ${(height * 0.6).toFixed(3)} * cos(uTime * 0.83 + vegPhase);`,
          '}',
          '#endif',
        ].join('\n'),
      );
  };
  material.customProgramCacheKey = () => cacheKey;
}

// ---------------------------------------------------------------------------
// Gestion des slots d'instances
// ---------------------------------------------------------------------------

class SpeciesMesh {
  constructor(def, geometry, capacity, colorTint) {
    this.def = def;
    this.capacity = capacity;
    this.geometry = geometry;

    this.material = new THREE.MeshLambertMaterial({
      vertexColors: true,
      flatShading: true,
      side: def.doubleSide ? THREE.DoubleSide : THREE.FrontSide,
    });
    applyWind(this.material, def.geoHeight || def.height, def.wind, `veg-${def.key}`);

    this.mesh = new THREE.InstancedMesh(geometry, this.material, capacity);
    this.mesh.name = `vegetation-${def.key}`;
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.mesh.frustumCulled = false; // les instances couvrent toute la planete
    this.mesh.count = 0;
    // Teinte par instance : multipliee avec la couleur de vertex.
    this.mesh.setColorAt(0, colorTint);
    this.mesh.instanceColor.needsUpdate = true;

    // Liste de slots libres tenue en tas-min : alloc() rend toujours le plus
    // petit index disponible, donc mesh.count reste colle au nombre reel
    // d'instances vivantes malgre les ajouts / retraits de patches.
    this.free = new Int32Array(capacity);
    for (let i = 0; i < capacity; i++) this.free[i] = i;
    this.freeCount = capacity;
    this.alive = new Uint8Array(capacity);
    this.high = 0;
    this.live = 0;
    this.dirtyMatrix = false;
    this.dirtyColor = false;
  }

  alloc() {
    if (this.freeCount === 0) return -1;
    const heap = this.free;
    const idx = heap[0];
    // Retrait de la racine du tas-min.
    const last = heap[--this.freeCount];
    if (this.freeCount > 0) {
      heap[0] = last;
      let i = 0;
      for (;;) {
        const l = i * 2 + 1;
        const r = l + 1;
        let m = i;
        if (l < this.freeCount && heap[l] < heap[m]) m = l;
        if (r < this.freeCount && heap[r] < heap[m]) m = r;
        if (m === i) break;
        const t = heap[i];
        heap[i] = heap[m];
        heap[m] = t;
        i = m;
      }
    }
    this.alive[idx] = 1;
    this.live++;
    if (idx + 1 > this.high) this.high = idx + 1;
    return idx;
  }

  release(idx) {
    if (idx < 0 || idx >= this.capacity || !this.alive[idx]) return;
    this.alive[idx] = 0;
    this.live--;
    // Insertion dans le tas-min.
    const heap = this.free;
    let i = this.freeCount++;
    heap[i] = idx;
    while (i > 0) {
      const parent = (i - 1) >> 1;
      if (heap[parent] <= heap[i]) break;
      const t = heap[parent];
      heap[parent] = heap[i];
      heap[i] = t;
      i = parent;
    }
    this.mesh.setMatrixAt(idx, DEAD_MATRIX);
    this.dirtyMatrix = true;
    if (idx + 1 === this.high) {
      let h = idx;
      while (h > 0 && !this.alive[h - 1]) h--;
      this.high = h;
    }
  }

  flush() {
    if (this.mesh.count !== this.high) this.mesh.count = this.high;
    if (this.dirtyMatrix) {
      this.mesh.instanceMatrix.needsUpdate = true;
      this.dirtyMatrix = false;
    }
    if (this.dirtyColor && this.mesh.instanceColor) {
      this.mesh.instanceColor.needsUpdate = true;
      this.dirtyColor = false;
    }
  }

  dispose() {
    this.geometry.dispose();
    this.material.dispose();
    this.mesh.dispose();
  }
}

// ---------------------------------------------------------------------------
// Fabrique publique
// ---------------------------------------------------------------------------

/**
 * @param {object} args
 * @param {object} args.spec PlanetSpec
 * @param {object} args.heightField HeightField (validation du sol)
 * @param {object} args.pool WorkerPool de terrain (requetes 'scatter')
 * @param {object} args.quality preset de qualite
 */
export function createVegetation({ spec, heightField, pool, quality } = {}) {
  const q = quality || getQuality();
  const object3D = new THREE.Group();
  object3D.name = 'vegetation';

  const hasTrees = !!(spec && spec.hasTrees) && !(spec && spec.isGas);
  const hasRocks = !!spec && !spec.isGas;
  const usable = !!pool && typeof pool.request === 'function' && (hasTrees || hasRocks);

  if (!usable) return neutralVegetation(object3D);

  const palette = getPalette(spec.palette);
  const paletteColor = (biomeId, gain, out) => {
    const o = (biomeId | 0) * 3;
    return out.setRGB(
      clamp(palette[o] * gain, 0, 1),
      clamp(palette[o + 1] * gain, 0, 1),
      clamp(palette[o + 2] * gain, 0, 1),
    );
  };

  const trunkColor = new THREE.Color();
  const leafColor = new THREE.Color();
  const tint = new THREE.Color(1, 1, 1);

  // --- Construction des especes (une seule fois) --------------------------
  const builders = {
    conifer: buildConifer,
    broadleaf: buildBroadleaf,
    palm: buildPalm,
    cycad: buildCycad,
  };

  /** @type {SpeciesMesh[]} */
  const species = [];
  const treeSpeciesCount = hasTrees ? TREE_SPECIES.length : 0;

  if (hasTrees) {
    for (const def of TREE_SPECIES) {
      paletteColor(def.trunkFrom[0], def.trunkFrom[1], trunkColor);
      paletteColor(def.leafFrom[0], def.leafFrom[1], leafColor);
      const geo = builders[def.key](def.height, trunkColor, leafColor);
      geo.computeBoundingBox();
      const local = { ...def, geoHeight: geo.boundingBox ? geo.boundingBox.max.y : def.height };
      species.push(new SpeciesMesh(local, geo, TREE_CAPACITY, tint));
    }
  }

  // Le rocher existe sur tout monde rocheux, meme sans arbres.
  let rockIndex = -1;
  if (hasRocks) {
    paletteColor(ROCK_SPECIES.trunkFrom[0], ROCK_SPECIES.trunkFrom[1], trunkColor);
    const geo = buildRock(ROCK_SPECIES.height, trunkColor);
    rockIndex = species.length;
    species.push(new SpeciesMesh({ ...ROCK_SPECIES, geoHeight: ROCK_SPECIES.height }, geo, ROCK_CAPACITY, tint));
  }

  for (const s of species) object3D.add(s.mesh);

  // --- Table biome -> especes candidates ----------------------------------
  const byBiome = [];
  for (let i = 0; i < 13; i++) byBiome.push([]);
  for (let i = 0; i < treeSpeciesCount; i++) {
    for (const b of TREE_SPECIES[i].biomes) byBiome[b].push(i);
  }
  const anyTree = [];
  for (let i = 0; i < treeSpeciesCount; i++) anyTree.push(i);

  // --- Etat de streaming ---------------------------------------------------
  const records = new Map(); // key -> record
  const lifeMinLevel = q.lifeMinLevel != null ? q.lifeMinLevel : 5;
  const density = q.treeDensity != null ? q.treeDensity : 1;
  const seaLevel = spec.seaLevel;
  let disposed = false;
  let liveTrees = 0;

  function makeRecord(p) {
    // On accepte un center Vector3 ou un simple tableau [x,y,z].
    const c = p.center;
    const cx = c ? (c.x !== undefined ? c.x : c[0] || 0) : 0;
    const cy = c ? (c.y !== undefined ? c.y : c[1] || 0) : 0;
    const cz = c ? (c.z !== undefined ? c.z : c[2] || 0) : 0;
    return {
      key: p.key,
      cx,
      cy,
      cz,
      radius: p.boundRadius || 0,
      slots: [], // entiers packes : speciesIndex * PACK_BASE + slot
      treePos: null, // Float32Array(n*3), positions d'arbres pour nearest()
      treeN: 0,
      pending: 0,
      dead: false,
    };
  }

  /** Fractions utiles du patch, deduites de l'histogramme de biomes. */
  function analyse(p) {
    const hist = p.biomeHistogram;
    let total = 0;
    let veg = 0;
    let land = 0;
    if (hist && hist.length >= 13) {
      for (let i = 0; i < 13; i++) {
        const c = hist[i];
        if (!c) continue;
        total += c;
        if (isWaterBiome(i)) continue;
        if (i === BIOME_ID.LAVA) continue;
        land += c;
        if (VEGETATION_BIOMES.has(i)) veg += c;
      }
    }
    if (total === 0) {
      const water = p.waterFraction != null ? p.waterFraction : 0;
      return { veg: 0, land: 1 - water };
    }
    return { veg: veg / total, land: land / total };
  }

  function addPatch(p) {
    if (disposed || !p || !p.key) return;
    if ((p.level | 0) < lifeMinLevel) return;
    if (records.has(p.key)) return;

    const frac = analyse(p);
    if (frac.land < 0.02) return; // patch integralement eau / lave

    const base = density * TREE_BASE_COUNT;
    let treeCount = 0;
    if (hasTrees && frac.veg > 0.001) {
      const favourable = frac.veg > 0.35;
      treeCount = Math.min(TREE_COUNT_MAX, Math.round(base * (favourable ? 1 : 0.2)));
    }
    let rockCount = 0;
    if (rockIndex >= 0 && frac.land > 0.05) {
      rockCount = Math.min(ROCK_COUNT_MAX, Math.round(base * ROCK_RATIO * (frac.land > 0.5 ? 1 : 0.5)));
    }
    if (treeCount <= 0 && rockCount <= 0) return;

    const rec = makeRecord(p);
    records.set(p.key, rec);

    if (treeCount > 0) requestScatter(rec, p, 'tree', treeCount);
    if (rockCount > 0) requestScatter(rec, p, 'rock', rockCount);
  }

  function requestScatter(rec, p, kind, count) {
    rec.pending++;
    pool
      .request({ type: 'scatter', faceId: p.faceId, u0: p.u0, v0: p.v0, size: p.size, count, kind })
      .then((res) => {
        rec.pending--;
        if (disposed || rec.dead || !records.has(rec.key)) return;
        place(rec, res, kind);
      })
      .catch(() => {
        rec.pending--;
      });
  }

  /** Pose les instances renvoyees par le worker. */
  function place(rec, res, kind) {
    if (!res || !res.position) return;
    const position = res.position;
    const normal = res.normal;
    const biome = res.biome;
    const sc = res.scale;
    const k = Math.floor(position.length / 3);
    if (k <= 0) return;

    const rnd = mulberry32((hashString(rec.key + kind) ^ (spec.seed >>> 0)) >>> 0);
    const isRock = kind === 'rock';

    let treeArr = null;
    let treeN = rec.treeN;
    if (!isRock) {
      const need = treeN + k;
      treeArr = new Float32Array(need * 3);
      if (rec.treePos && treeN > 0) treeArr.set(rec.treePos.subarray(0, treeN * 3));
    }

    for (let i = 0; i < k; i++) {
      const o = i * 3;
      _pos.set(position[o], position[o + 1], position[o + 2]);
      const len = _pos.length();
      if (!(len > 1)) continue; // position aberrante

      // Normale du sol : fournie par le worker, sinon deduite du champ.
      if (normal) {
        _nrm.set(normal[o], normal[o + 1], normal[o + 2]);
      } else {
        _nrm.set(0, 0, 0);
      }
      if (_nrm.lengthSq() < 0.25) {
        _unit.copy(_pos).multiplyScalar(1 / len);
        if (heightField && heightField.normalAt) heightField.normalAt(_unit, _nrm);
        else _nrm.copy(_unit);
      } else {
        _nrm.normalize();
      }

      // Rien dans l'eau : filtre rapide par biome, puis verification exacte
      // pour les arbres via le champ de hauteur (LA reference commune worker /
      // thread principal).
      const b = biome ? biome[i] : BIOME_ID.GRASS;
      if (biome && isWaterBiome(b)) continue;
      if (!isRock && heightField && seaLevel !== null && seaLevel !== undefined) {
        _unit.copy(_pos).multiplyScalar(1 / len);
        const elev = heightField.elevationUnit(_unit);
        if (heightField.isWater(elev)) continue;
      }

      // Choix de l'espece selon le biome renvoye.
      let sIdx;
      if (isRock) {
        sIdx = rockIndex;
      } else {
        const list = byBiome[b] && byBiome[b].length ? byBiome[b] : anyTree;
        if (!list.length) continue;
        sIdx = list[Math.floor(rnd() * list.length)];
      }
      const sp = species[sIdx];
      if (!sp) continue;
      const slot = sp.alloc();
      if (slot < 0) continue; // capacite saturee

      // Echelle : suggestion du worker x variation deterministe.
      let s = sc ? sc[i] : 1;
      if (!(s > 0)) s = 1;
      s = clamp(s, 0.35, 3) * (0.82 + rnd() * 0.42);
      if (isRock) s *= 0.75 + rnd() * 1.1;
      s = clamp(s, 0.4, 2.6);

      // Orientation : +Y de l'arbre aligne sur la normale, puis lacet aleatoire.
      _quat.setFromUnitVectors(UP, _nrm);
      _yaw.setFromAxisAngle(UP, rnd() * Math.PI * 2);
      _quat.multiply(_yaw);
      _scale.setScalar(s);
      // On enfonce legerement la base pour eviter tout flottement visible.
      _pos.addScaledVector(_nrm, -sp.def.geoHeight * s * 0.018 - 0.05);
      _mat.compose(_pos, _quat, _scale);
      sp.mesh.setMatrixAt(slot, _mat);
      const v = 0.86 + rnd() * 0.26;
      _col.setRGB(v, v * (0.97 + rnd() * 0.06), v * (0.95 + rnd() * 0.1));
      sp.mesh.setColorAt(slot, _col);
      sp.dirtyMatrix = true;
      sp.dirtyColor = true;

      rec.slots.push(sIdx * PACK_BASE + slot);

      if (!isRock && treeArr) {
        const t = treeN * 3;
        treeArr[t] = _pos.x;
        treeArr[t + 1] = _pos.y;
        treeArr[t + 2] = _pos.z;
        treeN++;
        liveTrees++;
      }
    }

    if (!isRock && treeArr) {
      rec.treePos = treeArr;
      rec.treeN = treeN;
    }
  }

  function removePatch(key) {
    const rec = records.get(key);
    if (!rec) return;
    rec.dead = true;
    records.delete(key);
    for (let i = 0; i < rec.slots.length; i++) {
      const packed = rec.slots[i];
      const sIdx = Math.floor(packed / PACK_BASE);
      const slot = packed - sIdx * PACK_BASE;
      const sp = species[sIdx];
      if (sp) sp.release(slot);
    }
    rec.slots.length = 0;
    liveTrees -= rec.treeN;
    if (liveTrees < 0) liveTrees = 0;
    rec.treePos = null;
    rec.treeN = 0;
  }

  function update(dt, ctx) {
    if (disposed) return;
    windUniforms.uTime.value += dt || 0;
    // Le vent faiblit dans le vide : on se sert de la densite si elle est
    // fournie, sinon on garde une brise constante.
    if (ctx && typeof ctx.windFactor === 'number') {
      windUniforms.uWind.value = clamp(ctx.windFactor, 0, 2);
    }
    for (let i = 0; i < species.length; i++) species[i].flush();
  }

  function nearest(cameraLocal) {
    if (disposed || !cameraLocal || liveTrees === 0) return null;
    const cx = cameraLocal.x;
    const cy = cameraLocal.y;
    const cz = cameraLocal.z;
    let bestSq = Infinity;
    let bx = 0;
    let by = 0;
    let bz = 0;

    for (const rec of records.values()) {
      if (rec.treeN === 0 || !rec.treePos) continue;
      // Rejet grossier par patch : centre + rayon englobant.
      const dxc = rec.cx - cx;
      const dyc = rec.cy - cy;
      const dzc = rec.cz - cz;
      const reach = NEAR_RANGE + rec.radius;
      if (dxc * dxc + dyc * dyc + dzc * dzc > reach * reach) continue;
      const arr = rec.treePos;
      const n = rec.treeN;
      for (let i = 0; i < n; i++) {
        const o = i * 3;
        const dx = arr[o] - cx;
        const dy = arr[o + 1] - cy;
        const dz = arr[o + 2] - cz;
        const d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < bestSq) {
          bestSq = d2;
          bx = arr[o];
          by = arr[o + 1];
          bz = arr[o + 2];
        }
      }
    }
    if (bestSq === Infinity) return null;
    _near.distance = Math.sqrt(bestSq);
    _near.position.set(bx, by, bz);
    return _near;
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    records.clear();
    for (const s of species) {
      object3D.remove(s.mesh);
      s.dispose();
    }
    species.length = 0;
    liveTrees = 0;
  }

  return {
    object3D,
    addPatch,
    removePatch,
    update,
    nearest,
    get count() {
      let n = 0;
      for (let i = 0; i < species.length; i++) n += species[i].live;
      return n;
    },
    get treeCount() {
      return liveTrees;
    },
    dispose,
  };
}

/** Implementation neutre : monde sans vegetation ni rochers (geante gazeuse). */
function neutralVegetation(object3D) {
  return {
    object3D,
    addPatch() {},
    removePatch() {},
    update() {},
    nearest() {
      return null;
    },
    get count() {
      return 0;
    },
    get treeCount() {
      return 0;
    },
    dispose() {},
  };
}
