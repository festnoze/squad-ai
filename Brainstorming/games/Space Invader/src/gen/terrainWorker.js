// Worker de generation de terrain.
//
// Un message = une reponse, l'`id` est toujours renvoye tel quel. Le worker
// garde le spec recu a l'init et le champ de hauteur associe : c'est LE meme
// module `heightField.js` que celui du thread principal, donc la collision et
// le maillage affiche decrivent exactement la meme surface.
//
// Tout ce qui sort d'ici est en ESPACE LOCAL PLANETE (origine = centre de la
// planete, +Y = axe des poles). Les positions de patch sont en plus relatives
// au centre du patch, pour rester precises en float32.
//
// Aucune dependance a three, aucun fetch, aucun asset.

import { createHeightField } from './heightField.js';
import {
  faceUVToUnit,
  latLonFromUnit,
  unitFromLatLon,
  tangentBasis,
  hash2,
  hashString,
  mulberry32,
  saturate,
} from '../core/math.js';
import { BIOME_ID, BIOMES, VEGETATION_BIOMES, FAUNA_BIOMES } from './palettes.js';

const DEFAULT_RES = 33;
const BIOME_COUNT = BIOMES.length;

// Biomes acceptes par type de semis.
const ROCK_BIOMES = new Set([
  BIOME_ID.ROCK,
  BIOME_ID.DESERT,
  BIOME_ID.ASH,
  BIOME_ID.SNOW,
  BIOME_ID.BEACH,
]);

const KIND_BIOMES = {
  tree: VEGETATION_BIOMES,
  fauna: FAUNA_BIOMES,
  rock: ROCK_BIOMES,
};

// Pente maximale toleree (0 = plat, 1 = falaise).
const KIND_MAX_SLOPE = {
  tree: 0.34,
  fauna: 0.3,
  rock: 0.62,
};

// Etat du worker.
let spec = null;
let heightField = null;

// Vecteurs temporaires : aucune allocation dans les boucles chaudes.
const _dir = { x: 0, y: 0, z: 0 };
const _dirC = { x: 0, y: 0, z: 0 };
const _tanA = { x: 0, y: 0, z: 0 };
const _tanB = { x: 0, y: 0, z: 0 };
const _nrm = { x: 0, y: 0, z: 0 };

// Tampons de travail reutilises, indexes par resolution.
const scratchByRes = new Map();

function getScratch(res) {
  let s = scratchByRes.get(res);
  if (s) return s;
  const e = res + 2;
  s = {
    pos: new Float64Array(e * e * 3), // positions locales planete, non centrees
    elev: new Float64Array(e * e),
  };
  if (scratchByRes.size > 3) scratchByRes.clear();
  scratchByRes.set(res, s);
  return s;
}

// ---------------------------------------------------------------------------
// Patch de terrain
// ---------------------------------------------------------------------------

/**
 * Construit la geometrie d'un patch de cube-sphere.
 *
 * Les normales sont deduites d'une grille etendue (res + 2) qui porte un anneau
 * de sommets hors patch : une seule evaluation d'elevation par sommet, et des
 * normales continues d'un patch au suivant (pas de couture visible).
 */
function buildPatch(msg) {
  const faceId = msg.faceId | 0;
  const u0 = msg.u0;
  const v0 = msg.v0;
  const size = msg.size;
  const R = Math.max(2, (msg.res | 0) || DEFAULT_RES);
  const E = R + 2;
  const step = size / (R - 1);
  const radius = spec.radius;

  // Centre du patch : origine des positions emises.
  const uc = u0 + size * 0.5;
  const vc = v0 + size * 0.5;
  faceUVToUnit(faceId, uc, vc, _dirC);
  const elevC = heightField.elevation(_dirC.x, _dirC.y, _dirC.z);
  const rC = radius + elevC;
  const cx = _dirC.x * rC;
  const cy = _dirC.y * rC;
  const cz = _dirC.z * rC;
  const centerGeo = latLonFromUnit(_dirC);
  const centerLat = centerGeo.lat;
  const centerLon = centerGeo.lon;

  // 1) Grille etendue : positions locales planete + elevations.
  const sc = getScratch(R);
  const ep = sc.pos;
  const ee = sc.elev;
  for (let jj = 0; jj < E; jj++) {
    const v = v0 + step * (jj - 1);
    const rowBase = jj * E;
    for (let ii = 0; ii < E; ii++) {
      const u = u0 + step * (ii - 1);
      faceUVToUnit(faceId, u, v, _dir);
      const el = heightField.elevation(_dir.x, _dir.y, _dir.z);
      const r = radius + el;
      const k = rowBase + ii;
      const o = k * 3;
      ep[o] = _dir.x * r;
      ep[o + 1] = _dir.y * r;
      ep[o + 2] = _dir.z * r;
      ee[k] = el;
    }
  }

  // 2) Sommets interieurs.
  const P = 4 * (R - 1); // longueur du perimetre (boucle fermee)
  const vertexCount = R * R + P;
  const position = new Float32Array(vertexCount * 3);
  const normal = new Float32Array(vertexCount * 3);
  const color = new Float32Array(vertexCount * 3);
  const uv = new Float32Array(vertexCount * 2);
  const biomeHistogram = new Uint32Array(BIOME_COUNT);

  const invSpan = 1 / (R - 1);
  let minElev = Infinity;
  let maxElev = -Infinity;
  let waterCount = 0;
  let bound2 = 0;

  for (let j = 0; j < R; j++) {
    const ej = j + 1;
    for (let i = 0; i < R; i++) {
      const ei = i + 1;
      const k = j * R + i;
      const ek = ej * E + ei;
      const eo = ek * 3;
      const px = ep[eo];
      const py = ep[eo + 1];
      const pz = ep[eo + 2];
      const el = ee[ek];

      // Position relative au centre du patch.
      const dx = px - cx;
      const dy = py - cy;
      const dz = pz - cz;
      const o3 = k * 3;
      position[o3] = dx;
      position[o3 + 1] = dy;
      position[o3 + 2] = dz;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > bound2) bound2 = d2;

      // Normale par differences centrales sur les 4 voisins de la grille etendue.
      const oL = (ek - 1) * 3;
      const oR = (ek + 1) * 3;
      const oD = (ek - E) * 3;
      const oU = (ek + E) * 3;
      const ax = ep[oR] - ep[oL];
      const ay = ep[oR + 1] - ep[oL + 1];
      const az = ep[oR + 2] - ep[oL + 2];
      const bx = ep[oU] - ep[oD];
      const by = ep[oU + 1] - ep[oD + 1];
      const bz = ep[oU + 2] - ep[oD + 2];
      let nx = ay * bz - az * by;
      let ny = az * bx - ax * bz;
      let nz = ax * by - ay * bx;
      const nl = Math.hypot(nx, ny, nz) || 1;
      nx /= nl;
      ny /= nl;
      nz /= nl;
      // Orientation vers l'exterieur de la planete.
      if (nx * px + ny * py + nz * pz < 0) {
        nx = -nx;
        ny = -ny;
        nz = -nz;
      }
      normal[o3] = nx;
      normal[o3 + 1] = ny;
      normal[o3 + 2] = nz;

      // Couleur du biome (deja lineaire).
      const rr = radius + el;
      const invRR = 1 / (rr || 1);
      const ux = px * invRR;
      const uy = py * invRR;
      const uz = pz * invRR;
      let bid = heightField.colorAt(ux, uy, uz, el, color, o3);
      if (typeof bid !== 'number') bid = heightField.biomeId(ux, uy, uz, el);
      if (bid >= 0 && bid < BIOME_COUNT) biomeHistogram[bid]++;
      if (heightField.isWater(el)) waterCount++;
      if (el < minElev) minElev = el;
      if (el > maxElev) maxElev = el;

      const o2 = k * 2;
      uv[o2] = i * invSpan;
      uv[o2 + 1] = j * invSpan;
    }
  }

  // 3) Sens d'enroulement : deux faces du cube ont une base (u, v) gauche.
  // On le determine geometriquement sur un quad central.
  const q = Math.max(0, (R >> 1) - 1);
  const flip = !isOutward(position, q * R + q, q * R + q + 1, (q + 1) * R + q, cx, cy, cz);

  const triCount = (R - 1) * (R - 1) * 2 + P * 2;
  const index = new Uint32Array(triCount * 3);
  let t = 0;
  for (let j = 0; j < R - 1; j++) {
    for (let i = 0; i < R - 1; i++) {
      const a = j * R + i;
      const b = a + 1;
      const c = a + R + 1;
      const d = a + R;
      if (flip) {
        index[t++] = a;
        index[t++] = c;
        index[t++] = b;
        index[t++] = a;
        index[t++] = d;
        index[t++] = c;
      } else {
        index[t++] = a;
        index[t++] = b;
        index[t++] = c;
        index[t++] = a;
        index[t++] = c;
        index[t++] = d;
      }
    }
  }

  // 4) Jupe : ceinture de sommets dupliquant le bord, descendue vers le centre
  // de la planete. Masque les fissures entre niveaux de LOD voisins.
  const border = buildBorderLoop(R);
  const skirtDepth = Math.max(3, size * radius * 0.06);
  const skirtBase = R * R;
  for (let k = 0; k < P; k++) {
    const b = border[k];
    const bo = b * 3;
    const px = position[bo] + cx;
    const py = position[bo + 1] + cy;
    const pz = position[bo + 2] + cz;
    const rr = Math.hypot(px, py, pz) || 1;
    const f = (rr - skirtDepth) / rr;
    const s = skirtBase + k;
    const so = s * 3;
    const dx = px * f - cx;
    const dy = py * f - cy;
    const dz = pz * f - cz;
    position[so] = dx;
    position[so + 1] = dy;
    position[so + 2] = dz;
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 > bound2) bound2 = d2;
    normal[so] = normal[bo];
    normal[so + 1] = normal[bo + 1];
    normal[so + 2] = normal[bo + 2];
    color[so] = color[bo];
    color[so + 1] = color[bo + 1];
    color[so + 2] = color[bo + 2];
    uv[s * 2] = uv[b * 2];
    uv[s * 2 + 1] = uv[b * 2 + 1];
  }

  for (let k = 0; k < P; k++) {
    const k1 = (k + 1) % P;
    const b0 = border[k];
    const b1 = border[k1];
    const s0 = skirtBase + k;
    const s1 = skirtBase + k1;
    if (flip) {
      index[t++] = b0;
      index[t++] = s1;
      index[t++] = s0;
      index[t++] = b0;
      index[t++] = b1;
      index[t++] = s1;
    } else {
      index[t++] = b0;
      index[t++] = s0;
      index[t++] = s1;
      index[t++] = b0;
      index[t++] = s1;
      index[t++] = b1;
    }
  }

  return {
    position,
    normal,
    color,
    uv,
    index,
    center: [cx, cy, cz],
    centerLat,
    centerLon,
    boundRadius: Math.sqrt(bound2),
    minElev: minElev === Infinity ? 0 : minElev,
    maxElev: maxElev === -Infinity ? 0 : maxElev,
    biomeHistogram,
    waterFraction: waterCount / (R * R),
    faceId,
    u0,
    v0,
    size,
    res: R,
    vertexCount,
    skirtDepth,
  };
}

/** Le triangle (a, b, c) tourne-t-il dans le sens direct vu de l'exterieur ? */
function isOutward(position, a, b, c, cx, cy, cz) {
  const ao = a * 3;
  const bo = b * 3;
  const co = c * 3;
  const e1x = position[bo] - position[ao];
  const e1y = position[bo + 1] - position[ao + 1];
  const e1z = position[bo + 2] - position[ao + 2];
  const e2x = position[co] - position[ao];
  const e2y = position[co + 1] - position[ao + 1];
  const e2z = position[co + 2] - position[ao + 2];
  const nx = e1y * e2z - e1z * e2y;
  const ny = e1z * e2x - e1x * e2z;
  const nz = e1x * e2y - e1y * e2x;
  return nx * cx + ny * cy + nz * cz >= 0;
}

/** Indices des sommets du bord, en boucle fermee (4 * (R - 1) entrees). */
function buildBorderLoop(R) {
  const loop = new Int32Array(4 * (R - 1));
  let n = 0;
  for (let i = 0; i < R - 1; i++) loop[n++] = i; // bord bas, j = 0
  for (let j = 0; j < R - 1; j++) loop[n++] = j * R + (R - 1); // bord droit
  for (let i = R - 1; i > 0; i--) loop[n++] = (R - 1) * R + i; // bord haut
  for (let j = R - 1; j > 0; j--) loop[n++] = j * R; // bord gauche
  return loop;
}

/** Geante gazeuse : pas de sol, on renvoie un patch vide. */
function emptyPatch(msg) {
  const faceId = msg.faceId | 0;
  const size = msg.size;
  faceUVToUnit(faceId, msg.u0 + size * 0.5, msg.v0 + size * 0.5, _dirC);
  const r = spec.radius;
  const geo = latLonFromUnit(_dirC);
  return {
    position: new Float32Array(0),
    normal: new Float32Array(0),
    color: new Float32Array(0),
    uv: new Float32Array(0),
    index: new Uint32Array(0),
    center: [_dirC.x * r, _dirC.y * r, _dirC.z * r],
    centerLat: geo.lat,
    centerLon: geo.lon,
    boundRadius: 0,
    minElev: 0,
    maxElev: 0,
    biomeHistogram: new Uint32Array(BIOME_COUNT),
    waterFraction: 0,
    faceId,
    u0: msg.u0,
    v0: msg.v0,
    size,
    res: Math.max(2, (msg.res | 0) || DEFAULT_RES),
    vertexCount: 0,
    skirtDepth: 0,
    empty: true,
  };
}

// ---------------------------------------------------------------------------
// Carte equirectangulaire
// ---------------------------------------------------------------------------

/**
 * Projection equirectangulaire :
 *   x = 0 -> longitude -PI, x = width - 1 -> +PI
 *   y = 0 -> latitude +PI/2, y = height - 1 -> -PI/2
 */
function buildHeightmap(msg) {
  const w = Math.max(2, msg.width | 0);
  const h = Math.max(2, msg.height | 0);
  const n = w * h;
  const heightData = new Float32Array(n);
  const biome = new Uint8Array(n);
  const water = new Uint8Array(n);

  const HALF_PI = Math.PI * 0.5;
  const invW = 1 / (w - 1);
  const invH = 1 / (h - 1);

  for (let y = 0; y < h; y++) {
    const lat = HALF_PI - Math.PI * (y * invH);
    const rowBase = y * w;
    for (let x = 0; x < w; x++) {
      const lon = -Math.PI + 2 * Math.PI * (x * invW);
      unitFromLatLon(lat, lon, _dir);
      const el = heightField.elevation(_dir.x, _dir.y, _dir.z);
      const k = rowBase + x;
      heightData[k] = el;
      biome[k] = heightField.biomeId(_dir.x, _dir.y, _dir.z, el);
      water[k] = heightField.isWater(el) ? 1 : 0;
    }
  }

  // `height` porte les metres (contrat) ; `rows` porte la hauteur en pixels.
  return { height: heightData, biome, water, width: w, rows: h };
}

// ---------------------------------------------------------------------------
// Semis de vie
// ---------------------------------------------------------------------------

/**
 * Normale du sol et pente, par differences finies a la main (2 voisins a 1.5 m).
 * Bien moins couteux que heightField.slope(), qui refait une base tangente et
 * trois evaluations a chaque appel.
 */
function groundNormalAndSlope(ux, uy, uz, elev, out) {
  const radius = spec.radius;
  _dir.x = ux;
  _dir.y = uy;
  _dir.z = uz;
  tangentBasis(_dir, _tanA, _tanB);
  const d = 1.5 / radius;

  let ax = ux + _tanA.x * d;
  let ay = uy + _tanA.y * d;
  let az = uz + _tanA.z * d;
  let l = 1 / (Math.hypot(ax, ay, az) || 1);
  ax *= l;
  ay *= l;
  az *= l;
  const ar = radius + heightField.elevation(ax, ay, az);

  let bx = ux + _tanB.x * d;
  let by = uy + _tanB.y * d;
  let bz = uz + _tanB.z * d;
  l = 1 / (Math.hypot(bx, by, bz) || 1);
  bx *= l;
  by *= l;
  bz *= l;
  const br = radius + heightField.elevation(bx, by, bz);

  const cr = radius + elev;
  const e1x = ax * ar - ux * cr;
  const e1y = ay * ar - uy * cr;
  const e1z = az * ar - uz * cr;
  const e2x = bx * br - ux * cr;
  const e2y = by * br - uy * cr;
  const e2z = bz * br - uz * cr;

  let nx = e1y * e2z - e1z * e2y;
  let ny = e1z * e2x - e1x * e2z;
  let nz = e1x * e2y - e1y * e2x;
  const nl = Math.hypot(nx, ny, nz) || 1;
  nx /= nl;
  ny /= nl;
  nz /= nl;
  if (nx * ux + ny * uy + nz * uz < 0) {
    nx = -nx;
    ny = -ny;
    nz = -nz;
  }
  out.x = nx;
  out.y = ny;
  out.z = nz;
  return saturate(1 - (nx * ux + ny * uy + nz * uz));
}

/** Hash deterministe d'un patch : meme patch -> meme semis, toujours. */
function patchHash(faceId, u0, v0, size, kind) {
  let h = hash2(faceId + 1, hashString(kind));
  h = hash2(h, Math.round(u0 * 1048576) | 0);
  h = hash2(h, Math.round(v0 * 1048576) | 0);
  h = hash2(h, Math.round(size * 1048576) | 0);
  return h >>> 0;
}

function buildScatter(msg) {
  const faceId = msg.faceId | 0;
  const u0 = msg.u0;
  const v0 = msg.v0;
  const size = msg.size;
  const kind = typeof msg.kind === 'string' ? msg.kind : 'tree';
  const count = Math.max(0, msg.count | 0);
  const allowed = KIND_BIOMES[kind] || VEGETATION_BIOMES;
  const maxSlope = KIND_MAX_SLOPE[kind] !== undefined ? KIND_MAX_SLOPE[kind] : 0.4;

  const position = new Float32Array(count * 3);
  const normalOut = new Float32Array(count * 3);
  const biome = new Uint8Array(count);
  const scale = new Float32Array(count);

  if (count === 0 || spec.isGas) {
    return finishScatter(position, normalOut, biome, scale, 0, faceId, u0, v0, size, kind, count);
  }

  const rnd = mulberry32(hash2(spec.seed >>> 0, patchHash(faceId, u0, v0, size, kind)));
  const radius = spec.radius;
  let accepted = 0;

  for (let n = 0; n < count; n++) {
    const u = u0 + size * rnd();
    const v = v0 + size * rnd();
    const jitter = rnd(); // consomme toujours 3 tirages : semis stable
    faceUVToUnit(faceId, u, v, _dir);
    const ux = _dir.x;
    const uy = _dir.y;
    const uz = _dir.z;
    const el = heightField.elevation(ux, uy, uz);
    if (heightField.isWater(el)) continue;
    const bid = heightField.biomeId(ux, uy, uz, el);
    if (!allowed.has(bid)) continue;
    const slope = groundNormalAndSlope(ux, uy, uz, el, _nrm);
    if (slope > maxSlope) continue;

    const r = radius + el;
    const o3 = accepted * 3;
    position[o3] = ux * r;
    position[o3 + 1] = uy * r;
    position[o3 + 2] = uz * r;
    normalOut[o3] = _nrm.x;
    normalOut[o3 + 1] = _nrm.y;
    normalOut[o3 + 2] = _nrm.z;
    biome[accepted] = bid;
    scale[accepted] = 0.7 + jitter * 0.9; // 0.7 .. 1.6
    accepted++;
  }

  return finishScatter(position, normalOut, biome, scale, accepted, faceId, u0, v0, size, kind, count);
}

function finishScatter(position, normalOut, biome, scale, accepted, faceId, u0, v0, size, kind, requested) {
  return {
    position: accepted === position.length / 3 ? position : position.slice(0, accepted * 3),
    normal: accepted === normalOut.length / 3 ? normalOut : normalOut.slice(0, accepted * 3),
    biome: accepted === biome.length ? biome : biome.slice(0, accepted),
    scale: accepted === scale.length ? scale : scale.slice(0, accepted),
    accepted,
    requested,
    faceId,
    u0,
    v0,
    size,
    kind,
  };
}

// ---------------------------------------------------------------------------
// Protocole
// ---------------------------------------------------------------------------

/** Liste des ArrayBuffers a transferer (evite toute copie). */
function transferList(payload) {
  const list = [];
  for (const key in payload) {
    const value = payload[key];
    if (ArrayBuffer.isView(value) && list.indexOf(value.buffer) === -1) list.push(value.buffer);
  }
  return list;
}

function reply(type, id, payload) {
  const message = { type, id };
  for (const key in payload) message[key] = payload[key];
  self.postMessage(message, transferList(payload));
}

self.onmessage = (event) => {
  const msg = event.data;
  if (!msg || typeof msg.type !== 'string') return;
  const id = msg.id;

  try {
    switch (msg.type) {
      case 'init': {
        spec = msg.spec;
        heightField = createHeightField(spec);
        // seaLevel est calibre par le champ de hauteur : on le renvoie pour
        // que l'appelant puisse verifier qu'il a bien la meme valeur.
        self.postMessage({ type: 'ready', id, seaLevel: heightField.seaLevel });
        break;
      }
      case 'patch': {
        requireInit();
        reply('patch', id, spec.isGas ? emptyPatch(msg) : buildPatch(msg));
        break;
      }
      case 'heightmap': {
        requireInit();
        reply('heightmap', id, buildHeightmap(msg));
        break;
      }
      case 'scatter': {
        requireInit();
        reply('scatter', id, buildScatter(msg));
        break;
      }
      default:
        self.postMessage({ type: 'error', id, message: `type de message inconnu: ${msg.type}` });
    }
  } catch (err) {
    // On ne bloque jamais le pool : toute erreur remonte comme une reponse.
    self.postMessage({
      type: 'error',
      id,
      message: (err && (err.stack || err.message)) || String(err),
    });
  }
};

function requireInit() {
  if (!heightField) throw new Error('terrainWorker: init non recu');
}
