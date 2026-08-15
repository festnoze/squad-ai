// Boite a outils scalaire. AUCUNE dependance a three : ce module est importe
// par les workers, ou l'on veut un bundle minimal. Les fonctions qui ecrivent
// un vecteur acceptent n'importe quel objet `{x, y, z}` (donc aussi Vector3).

export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Melange deterministe de deux entiers, utile pour deriver des seeds. */
export function hash2(a, b) {
  let h = (a * 0x27d4eb2d) ^ (b * 0x165667b1);
  h = Math.imul(h ^ (h >>> 15), 0x2545f491);
  return (h ^ (h >>> 13)) >>> 0;
}

export const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
export const saturate = (x) => (x < 0 ? 0 : x > 1 ? 1 : x);
export const lerp = (a, b, t) => a + (b - a) * t;
export const mix = lerp;
export const invLerp = (a, b, x) => (b === a ? 0 : (x - a) / (b - a));

export function smoothstep(e0, e1, x) {
  const t = saturate((x - e0) / (e1 - e0 || 1e-9));
  return t * t * (3 - 2 * t);
}

export function smootherstep(e0, e1, x) {
  const t = saturate((x - e0) / (e1 - e0 || 1e-9));
  return t * t * t * (t * (t * 6 - 15) + 10);
}

export const easeInCubic = (t) => t * t * t;
export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
export const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));

/** Amortissement exponentiel independant du framerate. */
export function damp(current, target, lambda, dt) {
  return lerp(current, target, 1 - Math.exp(-lambda * dt));
}

// ---------------------------------------------------------------------------
// Cube-sphere
// ---------------------------------------------------------------------------
// Six faces. Un point de face est defini par (u, v) dans [-1, 1] :
//   cube = normal + uAxis * u + vAxis * v
// puis "spherifie" (formule de deformation quadratique) pour une repartition
// bien plus uniforme qu'une simple normalisation.

export const CUBE_FACES = [
  { id: 0, key: '+X', normal: [1, 0, 0], uAxis: [0, 0, -1], vAxis: [0, 1, 0] },
  { id: 1, key: '-X', normal: [-1, 0, 0], uAxis: [0, 0, 1], vAxis: [0, 1, 0] },
  { id: 2, key: '+Y', normal: [0, 1, 0], uAxis: [1, 0, 0], vAxis: [0, 0, 1] },
  { id: 3, key: '-Y', normal: [0, -1, 0], uAxis: [1, 0, 0], vAxis: [0, 0, -1] },
  { id: 4, key: '+Z', normal: [0, 0, 1], uAxis: [1, 0, 0], vAxis: [0, 1, 0] },
  { id: 5, key: '-Z', normal: [0, 0, -1], uAxis: [-1, 0, 0], vAxis: [0, 1, 0] },
];

/** Transforme un point du cube unite en point de la sphere unite. */
export function spherifyCube(x, y, z, out) {
  const x2 = x * x;
  const y2 = y * y;
  const z2 = z * z;
  out.x = x * Math.sqrt(1 - y2 * 0.5 - z2 * 0.5 + (y2 * z2) / 3);
  out.y = y * Math.sqrt(1 - z2 * 0.5 - x2 * 0.5 + (z2 * x2) / 3);
  out.z = z * Math.sqrt(1 - x2 * 0.5 - y2 * 0.5 + (x2 * y2) / 3);
  return out;
}

/** (faceId, u, v) dans [-1,1] -> direction unitaire. */
export function faceUVToUnit(faceId, u, v, out) {
  const f = CUBE_FACES[faceId];
  const n = f.normal;
  const a = f.uAxis;
  const b = f.vAxis;
  return spherifyCube(
    n[0] + a[0] * u + b[0] * v,
    n[1] + a[1] * u + b[1] * v,
    n[2] + a[2] * u + b[2] * v,
    out,
  );
}

const _tmpUV = { faceId: 0, u: 0, v: 0 };

/**
 * Inverse approche de `faceUVToUnit` (projection lineaire sur la face
 * dominante). Suffisant pour localiser un patch ou une case de carte.
 */
export function unitToFaceUV(dir) {
  const ax = Math.abs(dir.x);
  const ay = Math.abs(dir.y);
  const az = Math.abs(dir.z);
  let faceId;
  let m;
  if (ax >= ay && ax >= az) {
    faceId = dir.x >= 0 ? 0 : 1;
    m = ax;
  } else if (ay >= az) {
    faceId = dir.y >= 0 ? 2 : 3;
    m = ay;
  } else {
    faceId = dir.z >= 0 ? 4 : 5;
    m = az;
  }
  const f = CUBE_FACES[faceId];
  const inv = 1 / (m || 1e-9);
  const px = dir.x * inv;
  const py = dir.y * inv;
  const pz = dir.z * inv;
  _tmpUV.faceId = faceId;
  _tmpUV.u = f.uAxis[0] * px + f.uAxis[1] * py + f.uAxis[2] * pz;
  _tmpUV.v = f.vAxis[0] * px + f.vAxis[1] * py + f.vAxis[2] * pz;
  return _tmpUV;
}

// ---------------------------------------------------------------------------
// Coordonnees geographiques
// ---------------------------------------------------------------------------

const _latLon = { lat: 0, lon: 0 };

/** Direction unitaire -> latitude [-PI/2, PI/2] et longitude [-PI, PI]. */
export function latLonFromUnit(dir) {
  _latLon.lat = Math.asin(clamp(dir.y, -1, 1));
  _latLon.lon = Math.atan2(dir.z, dir.x);
  return _latLon;
}

export function unitFromLatLon(lat, lon, out) {
  const c = Math.cos(lat);
  out.x = c * Math.cos(lon);
  out.y = Math.sin(lat);
  out.z = c * Math.sin(lon);
  return out;
}

/** Base tangente stable autour d'une direction unitaire. */
export function tangentBasis(unit, outTangent, outBitangent) {
  // On choisit l'axe de reference le moins colineaire.
  let rx = 0;
  let ry = 1;
  let rz = 0;
  if (Math.abs(unit.y) > 0.9) {
    rx = 1;
    ry = 0;
    rz = 0;
  }
  // t = normalize(cross(r, unit))
  let tx = ry * unit.z - rz * unit.y;
  let ty = rz * unit.x - rx * unit.z;
  let tz = rx * unit.y - ry * unit.x;
  const tl = Math.hypot(tx, ty, tz) || 1;
  tx /= tl;
  ty /= tl;
  tz /= tl;
  outTangent.x = tx;
  outTangent.y = ty;
  outTangent.z = tz;
  // b = cross(unit, t)
  outBitangent.x = unit.y * tz - unit.z * ty;
  outBitangent.y = unit.z * tx - unit.x * tz;
  outBitangent.z = unit.x * ty - unit.y * tx;
  return outBitangent;
}

/** Formate une distance en unites de jeu pour l'affichage HUD. */
export function formatDistance(m) {
  if (m < 1000) return `${m.toFixed(0)} m`;
  if (m < 1e6) return `${(m / 1000).toFixed(1)} km`;
  return `${(m / 1e6).toFixed(2)} Mm`;
}

export function formatSpeed(mps) {
  if (mps < 1000) return `${mps.toFixed(0)} m/s`;
  return `${(mps / 1000).toFixed(1)} km/s`;
}
