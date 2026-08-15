// Definition du systeme solaire. 12 corps, une etoile.
//
// Choix de conception importants :
//
// - Les planetes sont FIXES sur leur orbite pendant une partie. Le cycle
//   jour/nuit est obtenu en faisant tourner la *direction du soleil* dans le
//   repere local de la planete (cf. world/planet.js), et non la geometrie.
//   Cela evite que le sol ne file sous un vaisseau en vol stationnaire.
// - `seaFraction` est une cible de couverture ; le niveau de la mer reel est
//   calibre par `createHeightField` (quantile sur echantillonnage), puis ecrit
//   dans `spec.seaLevel`.
// - Un seul corps est `viable` (les 3 elements presents). Deux autres sont des
//   leurres a 1/3 et 2/3 pour donner envie de continuer.

import { hashString, mulberry32 } from '../core/math.js';
import { SCALE } from '../core/settings.js';

export const TEMP_CLASSES = ['inferno', 'torrid', 'hot', 'warm', 'temperate', 'cool', 'cold', 'frozen'];

export const PLANET_TYPES = ['rocky', 'ocean', 'desert', 'volcanic', 'ice', 'barren', 'gas'];

// Temperature normalisee de reference a l'equateur, par classe. Volontairement
// non lineaire : "tempere" doit rester franchement tempere une fois la baisse
// due a la latitude et a l'altitude appliquee.
export const TEMP_NORMS = {
  inferno: 1.0,
  torrid: 0.9,
  hot: 0.78,
  warm: 0.66,
  temperate: 0.56,
  cool: 0.45,
  cold: 0.34,
  frozen: 0.12,
};

export const TEMP_LABELS = {
  inferno: 'Infernal',
  torrid: 'Torride',
  hot: 'Chaud',
  warm: 'Tempere chaud',
  temperate: 'Tempere',
  cool: 'Frais',
  cold: 'Froid',
  frozen: 'Glacial',
};

export const TYPE_LABELS = {
  rocky: 'Tellurique',
  ocean: 'Oceanique',
  desert: 'Desertique',
  volcanic: 'Volcanique',
  ice: 'Glacee',
  barren: 'Sterile',
  gas: 'Geante gazeuse',
};

// Table brute. Tout ce qui est derivable est calcule dans buildSolarSystem.
const RAW = [
  {
    id: 'cindra',
    name: 'Cindra',
    orbitAU: 0.38,
    radius: 2600,
    type: 'volcanic',
    tempClass: 'inferno',
    tempK: 1180,
    palette: 'inferno',
    noiseProfile: 'volcanic',
    seaFraction: 0.34,
    seaType: 'lava',
    gravity: 4.6,
    dayLength: 342,
    axialTilt: 0.04,
    atmosphere: { thickness: 0.042, densitySea: 0.35, day: 'ff8a4a', horizon: 'ff4a10', night: '2a0a04' },
    clouds: null,
    description: 'Croute fracturee, mers de lave. La roche coule ici comme de l\'eau ailleurs.',
  },
  {
    id: 'vesk',
    name: 'Vesk',
    orbitAU: 0.68,
    radius: 3300,
    type: 'desert',
    tempClass: 'torrid',
    tempK: 690,
    palette: 'desert',
    noiseProfile: 'desertic',
    seaFraction: 0,
    seaType: null,
    gravity: 5.2,
    dayLength: 756,
    axialTilt: 0.11,
    atmosphere: { thickness: 0.056, densitySea: 0.5, day: 'e8b070', horizon: 'c86a30', night: '241408' },
    clouds: { coverage: 0.12, color: 'd8b890', speed: 0.05, altitude: 0.02 },
    description: 'Dunes de silicate a perte de vue, vents a 300 km/h. Rien n\'y tient debout.',
  },
  {
    id: 'terra-prime',
    name: 'Terra Prime',
    orbitAU: 1.0,
    radius: 6400,
    type: 'rocky',
    tempClass: 'temperate',
    tempK: 301,
    palette: 'dying',
    noiseProfile: 'arid',
    seaFraction: 0.17,
    seaType: 'water',
    gravity: 9.6,
    dayLength: 468,
    axialTilt: 0.41,
    isHome: true,
    atmosphere: { thickness: 0.091, densitySea: 1.0, day: '8ab4d8', horizon: 'd8c0a0', night: '0a1220' },
    clouds: { coverage: 0.3, color: 'e8e4dc', speed: 0.1, altitude: 0.028 },
    description: 'Notre monde. Les oceans se sont retires, les forets ont brule. Il reste des mers saumatres et de la poussiere.',
  },
  {
    id: 'ashkar',
    name: 'Ashkar',
    orbitAU: 1.34,
    radius: 3700,
    type: 'volcanic',
    tempClass: 'hot',
    tempK: 470,
    palette: 'volcanic',
    noiseProfile: 'volcanic',
    seaFraction: 0.2,
    seaType: 'lava',
    gravity: 5.8,
    dayLength: 540,
    axialTilt: 0.22,
    atmosphere: { thickness: 0.063, densitySea: 0.7, day: 'c08a60', horizon: 'e06a28', night: '18100c' },
    clouds: { coverage: 0.45, color: '5a4a44', speed: 0.14, altitude: 0.024 },
    description: 'Volcanisme permanent, ciel de cendres. Le sol est jeune de quelques siecles.',
  },
  {
    id: 'nereidia',
    name: 'Nereidia',
    orbitAU: 1.8,
    radius: 4900,
    type: 'ocean',
    tempClass: 'warm',
    tempK: 318,
    palette: 'oceanic',
    noiseProfile: 'oceanic',
    seaFraction: 0.9,
    seaType: 'water',
    gravity: 8.4,
    dayLength: 414,
    axialTilt: 0.18,
    lifeCandidate: true,
    hasOcean: true,
    atmosphere: { thickness: 0.098, densitySea: 1.15, day: '6ab0d0', horizon: 'b8dce8', night: '06121e' },
    clouds: { coverage: 0.62, color: 'f0f4f8', speed: 0.09, altitude: 0.03 },
    description: 'Un ocean global, quelques archipels volcaniques. De l\'eau, mais rien qui pousse.',
  },
  {
    id: 'selvara',
    name: 'Selvara',
    orbitAU: 2.25,
    radius: 5600,
    type: 'rocky',
    tempClass: 'temperate',
    tempK: 288,
    palette: 'earthlike',
    noiseProfile: 'continental',
    seaFraction: 0.55,
    seaType: 'water',
    gravity: 8.9,
    dayLength: 450,
    axialTilt: 0.33,
    lifeCandidate: true,
    hasOcean: true,
    hasTrees: true,
    atmosphere: { thickness: 0.091, densitySea: 1.0, day: '7ab0d8', horizon: 'cfe0d8', night: '08111c' },
    clouds: { coverage: 0.48, color: 'f2f4f2', speed: 0.1, altitude: 0.028 },
    description: 'Oceans, forets denses. Et un silence total : aucun mouvement, aucun chant, rien de vivant qui bouge.',
  },
  {
    id: 'bellatrix',
    name: 'Bellatrix',
    orbitAU: 3.1,
    radius: 34000,
    type: 'gas',
    tempClass: 'cool',
    tempK: 165,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 2.4,
    dayLength: 216,
    axialTilt: 0.05,
    atmosphere: { thickness: 0.154, densitySea: 2.4, day: 'd8b070', horizon: 'e8c890', night: '1a1208' },
    clouds: null,
    gas: { bandCount: 11, colorA: 'c8a878', colorB: '78502e', colorStorm: 'e85a3a', coreColor: 'ffb060', turbulence: 1.0 },
    ring: null,
    description: 'Geante d\'hydrogene. Pas de sol : on peut la traverser de part en part, si les turbulences le permettent.',
  },
  {
    id: 'kaelune',
    name: 'Kaelune',
    orbitAU: 3.9,
    radius: 4300,
    type: 'rocky',
    tempClass: 'cold',
    tempK: 248,
    palette: 'tundra',
    noiseProfile: 'glacial',
    seaFraction: 0.48,
    seaType: 'water',
    gravity: 7.1,
    dayLength: 612,
    axialTilt: 0.52,
    lifeCandidate: true,
    hasOcean: true,
    atmosphere: { thickness: 0.077, densitySea: 0.8, day: '90b8cc', horizon: 'd8e8f0', night: '060e18' },
    clouds: { coverage: 0.4, color: 'e0eaf0', speed: 0.12, altitude: 0.026 },
    description: 'Toundra et mers a demi prises. De l\'eau liquide sous la glace, mais la surface est nue.',
  },
  {
    id: 'aurelia',
    name: 'Aurelia',
    orbitAU: 4.7,
    radius: 6800,
    type: 'rocky',
    tempClass: 'temperate',
    tempK: 292,
    palette: 'garden',
    noiseProfile: 'continental',
    seaFraction: 0.58,
    seaType: 'water',
    gravity: 9.9,
    dayLength: 504,
    axialTilt: 0.29,
    lifeCandidate: true,
    hasOcean: true,
    hasTrees: true,
    hasFauna: true,
    viable: true,
    atmosphere: { thickness: 0.105, densitySea: 1.1, day: '74bcd8', horizon: 'e0dcb0', night: '07131c' },
    clouds: { coverage: 0.44, color: 'f6f8f4', speed: 0.09, altitude: 0.03 },
    description: 'Anomalie thermique : coeur radiogenique et serre dense. Loin du soleil, et pourtant tempere.',
  },
  {
    id: 'ogthar',
    name: 'Ogthar',
    orbitAU: 5.9,
    radius: 42000,
    type: 'gas',
    tempClass: 'cold',
    tempK: 128,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 2.8,
    dayLength: 270,
    axialTilt: 0.47,
    atmosphere: { thickness: 0.14, densitySea: 2.8, day: '90b0c8', horizon: 'b8d0e0', night: '0a1018' },
    clouds: null,
    gas: { bandCount: 8, colorA: '8aa8bc', colorB: '36506c', colorStorm: 'd8e8f0', coreColor: '70a0c8', turbulence: 1.4 },
    ring: { inner: 1.55, outer: 2.5, color: 'cfd8dc', opacity: 0.42 },
    description: 'Geante glacee ceinte d\'anneaux de glace. Traversable, mais la descente secoue.',
  },
  {
    id: 'hjalmar',
    name: 'Hjalmar',
    orbitAU: 7.3,
    radius: 4400,
    type: 'ice',
    tempClass: 'frozen',
    tempK: 118,
    palette: 'glacial',
    noiseProfile: 'glacial',
    seaFraction: 0.6,
    seaType: 'ice',
    gravity: 6.4,
    dayLength: 684,
    axialTilt: 0.14,
    atmosphere: { thickness: 0.049, densitySea: 0.3, day: 'a8c8dc', horizon: 'dceaf4', night: '040a12' },
    clouds: { coverage: 0.22, color: 'e8f2f8', speed: 0.06, altitude: 0.022 },
    description: 'Banquise globale, crevasses de plusieurs kilometres. L\'eau existe, mais pas une goutte de liquide.',
  },
  {
    id: 'nyx',
    name: 'Nyx',
    orbitAU: 9.2,
    radius: 3000,
    type: 'barren',
    tempClass: 'frozen',
    tempK: 62,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 3.4,
    dayLength: 936,
    axialTilt: 0.08,
    atmosphere: null,
    clouds: null,
    description: 'Cailloux, crateres, vide. Le soleil n\'y est qu\'une etoile un peu plus brillante.',
  },
];

function hexToRgb(hex) {
  const n = parseInt(hex, 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function buildAtmosphere(raw, radius) {
  if (!raw) return null;
  return {
    height: radius * raw.thickness,
    thickness: raw.thickness,
    densitySea: raw.densitySea,
    colorDay: hexToRgb(raw.day),
    colorHorizon: hexToRgb(raw.horizon),
    colorNight: hexToRgb(raw.night),
  };
}

function buildClouds(raw, radius) {
  if (!raw) return null;
  return {
    coverage: raw.coverage,
    color: hexToRgb(raw.color),
    speed: raw.speed,
    altitude: radius * raw.altitude,
  };
}

function buildGas(raw) {
  if (!raw) return null;
  return {
    bandCount: raw.bandCount,
    colorA: hexToRgb(raw.colorA),
    colorB: hexToRgb(raw.colorB),
    colorStorm: hexToRgb(raw.colorStorm),
    coreColor: hexToRgb(raw.coreColor),
    turbulence: raw.turbulence,
  };
}

function buildRing(raw) {
  if (!raw) return null;
  return { inner: raw.inner, outer: raw.outer, color: hexToRgb(raw.color), opacity: raw.opacity };
}

/**
 * Construit le systeme. Avec la seed par defaut, Aurelia est la planete viable.
 * Avec une autre seed, les 3 elements sont redistribues entre les candidats
 * (toujours exactement un gagnant, et des leurres a 1/3 et 2/3).
 */
export function buildSolarSystem(seedStr = 'odyssey') {
  const rootSeed = hashString(seedStr);
  const rnd = mulberry32(rootSeed);

  const planets = RAW.map((raw, index) => {
    const radius = raw.radius;
    const isGas = raw.type === 'gas';
    const spec = {
      id: raw.id,
      index,
      name: raw.name,
      description: raw.description,
      type: raw.type,
      typeLabel: TYPE_LABELS[raw.type],
      tempClass: raw.tempClass,
      tempLabel: TEMP_LABELS[raw.tempClass],
      tempK: raw.tempK,
      tempNorm: TEMP_NORMS[raw.tempClass] ?? 0.5,
      isHome: !!raw.isHome,
      viable: !!raw.viable,
      lifeCandidate: !!raw.lifeCandidate,

      radius,
      gravity: raw.gravity,
      maxElevation: radius * (isGas ? 0 : 0.05),
      minElevation: radius * (isGas ? 0 : -0.035),
      seaFraction: raw.seaFraction,
      seaType: raw.seaType,
      seaLevel: null, // calibre par createHeightField

      orbitAU: raw.orbitAU,
      orbitRadius: raw.orbitAU * SCALE.AU,
      orbitPhase: (index * 2.399963) % (Math.PI * 2), // angle d'or : bonne repartition
      orbitInclination: (rnd() - 0.5) * 0.14,
      axialTilt: raw.axialTilt,
      dayLength: raw.dayLength,
      spinPhase: rnd() * Math.PI * 2,

      seed: (rootSeed ^ hashString(raw.id)) >>> 0,
      noiseProfile: raw.noiseProfile,
      palette: raw.palette,

      hasOcean: !!raw.hasOcean,
      hasTrees: !!raw.hasTrees,
      hasFauna: !!raw.hasFauna,

      atmosphere: buildAtmosphere(raw.atmosphere, radius),
      clouds: buildClouds(raw.clouds, radius),
      gas: buildGas(raw.gas),
      ring: buildRing(raw.ring),
      isGas,
    };
    spec.orbitPosition = [
      Math.cos(spec.orbitPhase) * spec.orbitRadius,
      Math.sin(spec.orbitInclination) * spec.orbitRadius * 0.05,
      Math.sin(spec.orbitPhase) * spec.orbitRadius,
    ];
    return spec;
  });

  if (seedStr !== 'odyssey') redistributeLife(planets, rnd);

  return {
    seed: seedStr,
    star: {
      name: 'Helios Prime',
      radius: SCALE.SUN_RADIUS,
      color: 'fff2d8',
      coronaColor: 'ffb64a',
      intensity: 3.1,
    },
    planets,
  };
}

/** Redistribue les 3 elements entre les candidats pour une seed non par defaut. */
function redistributeLife(planets, rnd) {
  const candidates = planets.filter((p) => p.lifeCandidate);
  for (const p of candidates) {
    p.hasOcean = false;
    p.hasTrees = false;
    p.hasFauna = false;
    p.viable = false;
  }
  // Melange de Fisher-Yates.
  for (let i = candidates.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [candidates[i], candidates[j]] = [candidates[j], candidates[i]];
  }
  const winner = candidates[0];
  winner.hasOcean = true;
  winner.hasTrees = true;
  winner.hasFauna = true;
  winner.viable = true;
  winner.palette = 'garden';
  // La planete gagnante doit avoir assez de terres emergees pour que les arbres
  // et la faune soient trouvables sans y passer la soiree.
  if (winner.seaFraction < 0.4) winner.seaFraction = 0.55;
  if (winner.seaFraction > 0.72) winner.seaFraction = 0.62;
  if (winner.tempClass !== 'temperate') {
    winner.tempClass = 'temperate';
    winner.tempLabel = TEMP_LABELS.temperate;
    winner.tempNorm = TEMP_NORMS.temperate;
    winner.tempK = 289;
  }
  if (candidates[1]) {
    candidates[1].hasOcean = true;
    candidates[1].hasTrees = true;
  }
  if (candidates[2]) candidates[2].hasOcean = true;
}

let memo = null;

/** Systeme memoise. Seed lue dans `?seed=` si presente. */
export function getSystem() {
  if (memo) return memo;
  let seed = 'odyssey';
  if (typeof location !== 'undefined' && location.search) {
    const q = new URLSearchParams(location.search).get('seed');
    if (q) seed = q;
  }
  memo = buildSolarSystem(seed);
  return memo;
}

export function planetById(system, id) {
  return system.planets.find((p) => p.id === id) || null;
}
