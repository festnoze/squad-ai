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
function buildFromRaw(rawList, { seedStr, auScale = 1, star, redistribute = false }) {
  const rootSeed = hashString(seedStr);
  const rnd = mulberry32(rootSeed);
  const auUnit = SCALE.AU * auScale;

  const planets = rawList.map((raw, index) => {
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
      // Calottes polaires imposees (Mars) : sans elles, un monde froid et sec
      // n'a aucune glace, puisque l'humidite y est nulle par construction.
      iceCaps: !!raw.iceCaps,
      iceCapLat: typeof raw.iceCapLat === 'number' ? raw.iceCapLat : 0.9,

      orbitAU: raw.orbitAU,
      orbitRadius: raw.orbitAU * auUnit,
      orbitPhase:
        typeof raw.orbitPhase === 'number'
          ? raw.orbitPhase
          : (index * 2.399963) % (Math.PI * 2), // angle d'or : bonne repartition
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

  if (redistribute) redistributeLife(planets, rnd);

  return {
    seed: seedStr,
    star: {
      name: 'Helios Prime',
      color: 'fff2d8',
      coronaColor: 'ffb64a',
      intensity: 3.1,
      ...star,
      // Le soleil doit garder le meme diametre APPARENT quelle que soit
      // l'echelle du systeme, et l'eclairement se normalise sur l'UA du
      // systeme et non sur la constante globale.
      radius: SCALE.SUN_RADIUS * auScale,
      auUnit,
    },
    planets,
  };
}

/**
 * Systeme "Odyssee" : 12 corps ecrits a la main, celui de la campagne.
 * Avec la seed par defaut, Aurelia est la planete viable ; avec une autre, les
 * 3 elements sont redistribues entre les candidats.
 */
export function buildSolarSystem(seedStr = 'odyssey') {
  return buildFromRaw(RAW, {
    seedStr,
    auScale: 1,
    star: { name: 'Helios Prime' },
    redistribute: seedStr !== 'odyssey',
  });
}

// ---------------------------------------------------------------------------
// SOL-1 : notre systeme solaire
// ---------------------------------------------------------------------------
//
// Distances : demi-grands axes reels, tous multiplies par le meme facteur
// (`SOL_AU_SCALE`). Les proportions sont donc exactes, seule l'echelle absolue
// est raccourcie pour que Neptune reste atteignable en une dizaine de secondes.
// Rayons : rayons equatoriaux reels, normalises pour que la Terre vaille 6400
// unites (le meme rayon que Terra Prime, donc le meme ressenti au sol).
// Le facteur est 6400 / 6371 = 1.00455.
//
// Le joueur decolle de MARS : la Terre est le monde viable, et commencer sur
// Terre rendrait la mission gagnee d'avance.

// Facteur de raccourcissement. Venus et la Terre ne sont separees que de
// 0,277 UA, donc a cette echelle leurs spheres d'influence se recouvrent :
// c'est pourquoi SolarSystem n'active QUE la planete la plus proche et que
// currentPlanet retient elle aussi la plus proche.
const SOL_AU_SCALE = 0.4;

const SOL_RAW = [
  {
    id: 'mercure',
    name: 'Mercure',
    orbitAU: 0.387,
    radius: 2451,
    type: 'barren',
    tempClass: 'torrid',
    tempK: 440,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 3.7,
    dayLength: 900,
    axialTilt: 0.001,
    atmosphere: null,
    clouds: null,
    description:
      'Un monde de fer nu, crible de crateres, sans un souffle d\'air. Le sol passe de 430 degres au soleil a moins 170 a l\'ombre.',
  },
  {
    id: 'venus',
    name: 'Venus',
    orbitAU: 0.723,
    radius: 6080,
    type: 'rocky',
    tempClass: 'inferno',
    tempK: 737,
    palette: 'venusian',
    noiseProfile: 'volcanic',
    seaFraction: 0,
    seaType: null,
    gravity: 8.87,
    dayLength: 1200,
    axialTilt: 3.09, // rotation retrograde : la planete est litteralement a l'envers
    atmosphere: { thickness: 0.12, densitySea: 3.2, day: 'e8c070', horizon: 'c88a30', night: '2a1c08' },
    clouds: { coverage: 0.97, color: 'e8d8a0', speed: 0.22, altitude: 0.03 },
    description:
      'Sous une couverture permanente d\'acide sulfurique, 92 bars et 460 degres. La sonde qui a tenu le plus longtemps au sol y a survecu 127 minutes.',
  },
  {
    id: 'terre',
    name: 'Terre',
    orbitAU: 1.0,
    radius: 6400,
    type: 'rocky',
    tempClass: 'temperate',
    tempK: 288,
    palette: 'earthlike',
    noiseProfile: 'continental',
    seaFraction: 0.71,
    seaType: 'water',
    gravity: 9.81,
    dayLength: 468,
    axialTilt: 0.409, // 23,4 degres
    lifeCandidate: true,
    hasOcean: true,
    hasTrees: true,
    hasFauna: true,
    viable: true,
    atmosphere: { thickness: 0.091, densitySea: 1.0, day: '8ab4d8', horizon: 'cfe0e8', night: '08111c' },
    clouds: { coverage: 0.5, color: 'f4f6f8', speed: 0.1, altitude: 0.028 },
    description:
      'Le seul monde connu ou l\'eau tient a l\'etat liquide en surface. Oceans, forets, faune : les trois marqueurs y sont reunis.',
  },
  {
    id: 'mars',
    name: 'Mars',
    orbitAU: 1.524,
    radius: 3405,
    type: 'desert',
    tempClass: 'cold',
    tempK: 210,
    palette: 'martian',
    noiseProfile: 'desertic',
    seaFraction: 0,
    seaType: null,
    gravity: 3.72,
    dayLength: 480,
    axialTilt: 0.44, // 25,2 degres, tres proche de celui de la Terre
    isHome: true,
    iceCaps: true,
    iceCapLat: 0.88,
    atmosphere: { thickness: 0.07, densitySea: 0.06, day: 'c89878', horizon: 'e0b48c', night: '1a0e08' },
    clouds: { coverage: 0.08, color: 'd8c8b8', speed: 0.07, altitude: 0.03 },
    description:
      'Oxyde de fer, calottes de glace carbonique, une atmosphere cent fois trop mince. Notre base de depart.',
  },
  {
    id: 'jupiter',
    name: 'Jupiter',
    orbitAU: 5.203,
    radius: 70229,
    type: 'gas',
    tempClass: 'cool',
    tempK: 165,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 4.0,
    dayLength: 200, // la journee la plus courte du systeme : 9 h 55 reelles
    axialTilt: 0.055,
    atmosphere: null,
    clouds: null,
    gas: { bandCount: 14, colorA: 'd8c0a0', colorB: '8a5a38', colorStorm: 'c85a38', coreColor: 'ffb060', turbulence: 1.3 },
    ring: null,
    description:
      'Deux fois et demie la masse de toutes les autres planetes reunies. Pas de sol : on la traverse. La Grande Tache Rouge tourne depuis au moins trois siecles.',
  },
  {
    id: 'saturne',
    name: 'Saturne',
    orbitAU: 9.537,
    radius: 58497,
    type: 'gas',
    tempClass: 'cold',
    tempK: 134,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 3.0,
    dayLength: 220,
    axialTilt: 0.466, // 26,7 degres : c'est ce qui fait varier l'ouverture des anneaux
    atmosphere: null,
    clouds: null,
    gas: { bandCount: 9, colorA: 'e0cca0', colorB: 'a88a58', colorStorm: 'd8b878', coreColor: 'ffd090', turbulence: 0.8 },
    ring: { inner: 1.28, outer: 2.41, color: 'ded2bc', opacity: 0.5 },
    description:
      'Moins dense que l\'eau. Ses anneaux font 280 000 km de large pour quelques dizaines de metres d\'epaisseur.',
  },
  {
    id: 'uranus',
    name: 'Uranus',
    orbitAU: 19.191,
    radius: 25477,
    type: 'gas',
    tempClass: 'frozen',
    tempK: 76,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 2.6,
    dayLength: 260,
    axialTilt: 1.706, // 97,8 degres : elle roule sur son orbite
    atmosphere: null,
    clouds: null,
    gas: { bandCount: 5, colorA: 'b8e0e0', colorB: '78b0b8', colorStorm: 'd8f0f0', coreColor: '90c8d0', turbulence: 0.5 },
    ring: { inner: 1.64, outer: 2.0, color: 'a8b0b8', opacity: 0.16 },
    description:
      'Couchee sur le flanc, elle roule le long de son orbite. Geante de glaces : sous l\'hydrogene, un manteau d\'eau et d\'ammoniac.',
  },
  {
    id: 'neptune',
    name: 'Neptune',
    orbitAU: 30.07,
    radius: 24734,
    type: 'gas',
    tempClass: 'frozen',
    tempK: 72,
    palette: 'barren',
    noiseProfile: 'barren',
    seaFraction: 0,
    seaType: null,
    gravity: 2.8,
    dayLength: 250,
    axialTilt: 0.494,
    atmosphere: null,
    clouds: null,
    gas: { bandCount: 6, colorA: '4a7ad8', colorB: '2a4a9a', colorStorm: 'd8e4f8', coreColor: '5a8ae8', turbulence: 1.6 },
    ring: null,
    description:
      'Les vents les plus rapides du systeme : 2 100 km/h. Sa position a ete calculee avant d\'etre observee.',
  },
];

/** Notre systeme solaire, 8 planetes, distances et rayons a l'echelle. */
export function buildSolSystem(seedStr = 'sol1') {
  return buildFromRaw(SOL_RAW, {
    seedStr,
    auScale: SOL_AU_SCALE,
    star: { name: 'Sol', color: 'fff4e0', coronaColor: 'ffc060', intensity: 3.2 },
    redistribute: false,
  });
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

// ---------------------------------------------------------------------------
// Systeme genere aleatoirement
// ---------------------------------------------------------------------------

const SYLLABES_A = ['Kar', 'Vel', 'Thra', 'Ny', 'Ora', 'Zel', 'Mir', 'Cal', 'Dorn', 'Ise', 'Vor', 'Ael', 'Tan', 'Rhe', 'Xan', 'Lum'];
const SYLLABES_B = ['dis', 'thys', 'mera', 'vok', 'lune', 'sar', 'phos', 'tir', 'gaan', 'nea', 'dor', 'quis', 'bar', 'sela'];

function nomAleatoire(rnd, pris) {
  for (let essai = 0; essai < 40; essai++) {
    const n =
      SYLLABES_A[Math.floor(rnd() * SYLLABES_A.length)] +
      SYLLABES_B[Math.floor(rnd() * SYLLABES_B.length)];
    if (!pris.has(n)) {
      pris.add(n);
      return n;
    }
  }
  return `Corps ${pris.size + 1}`;
}

/** Classe de temperature deduite de la distance a l'etoile. */
function classeParDistance(au) {
  if (au < 0.5) return 'inferno';
  if (au < 0.8) return 'torrid';
  if (au < 1.15) return 'hot';
  if (au < 1.7) return 'temperate';
  if (au < 2.8) return 'warm';
  if (au < 5) return 'cool';
  if (au < 12) return 'cold';
  return 'frozen';
}

const ATMO_PAR_CLASSE = {
  inferno: { thickness: 0.05, densitySea: 0.4, day: 'ff8a4a', horizon: 'ff4a10', night: '2a0a04' },
  torrid: { thickness: 0.06, densitySea: 0.5, day: 'e8b070', horizon: 'c86a30', night: '241408' },
  hot: { thickness: 0.08, densitySea: 0.8, day: 'd8a878', horizon: 'e0b070', night: '1a1008' },
  temperate: { thickness: 0.091, densitySea: 1.0, day: '8ab4d8', horizon: 'd8c0a0', night: '0a1220' },
  warm: { thickness: 0.095, densitySea: 1.1, day: '7ab8d0', horizon: 'cfe0d8', night: '08111c' },
  cool: { thickness: 0.08, densitySea: 0.8, day: '90b8cc', horizon: 'd8e8f0', night: '060e18' },
  cold: { thickness: 0.07, densitySea: 0.6, day: 'a0c0d0', horizon: 'd8e8f0', night: '050c14' },
  frozen: { thickness: 0.05, densitySea: 0.3, day: 'a8c8dc', horizon: 'dceaf4', night: '040a12' },
};

/** Plus le score est bas, meilleur est le candidat au titre de monde d'origine. */
function scoreFoyer(raw) {
  const t = TEMP_NORMS[raw.tempClass] ?? 0.5;
  return Math.abs(t - 0.62) + (raw.atmosphere ? 0 : 0.5) + (raw.radius < 3200 ? 0.2 : 0);
}

/**
 * Genere un systeme complet a partir d'une seed : nombre de corps, orbites,
 * rayons, types et climats. Exactement une planete est viable, une autre sert
 * de monde d'origine epuise, et deux leurres portent 1 ou 2 des 3 elements.
 */
export function generateRandomSystem(seedStr) {
  const rnd = mulberry32(hashString(seedStr));
  const nb = 8 + Math.floor(rnd() * 5); // 8 a 12 corps
  const pris = new Set();
  const raws = [];

  // Orbites facon Titius-Bode : chaque corps est 1,35 a 1,9 fois plus loin.
  let au = 0.3 + rnd() * 0.25;
  for (let i = 0; i < nb; i++) {
    const tempClass = classeParDistance(au);
    const froid = au > 2.6;
    // Les geantes gazeuses n'apparaissent qu'au-dela de la ligne des glaces.
    const estGaz = froid && rnd() < 0.42;
    const nom = nomAleatoire(rnd, pris);
    const id = nom.toLowerCase();

    if (estGaz) {
      const teinte = rnd();
      const chaud = teinte < 0.5;
      raws.push({
        id,
        name: nom,
        orbitAU: +au.toFixed(3),
        radius: Math.round(24000 + rnd() * 52000),
        type: 'gas',
        tempClass,
        tempK: Math.round(300 / Math.sqrt(au)),
        palette: 'barren',
        noiseProfile: 'barren',
        seaFraction: 0,
        seaType: null,
        gravity: 2.2 + rnd() * 1.8,
        dayLength: Math.round(180 + rnd() * 160),
        axialTilt: rnd() * 1.2,
        atmosphere: null,
        clouds: null,
        gas: {
          bandCount: 5 + Math.floor(rnd() * 10),
          colorA: chaud ? 'd8c0a0' : 'a8c8d8',
          colorB: chaud ? '8a5a38' : '46688a',
          colorStorm: chaud ? 'c85a38' : 'd8e8f0',
          coreColor: chaud ? 'ffb060' : '70a0c8',
          turbulence: 0.5 + rnd() * 1.2,
        },
        ring: rnd() < 0.35
          ? { inner: 1.3 + rnd() * 0.3, outer: 1.9 + rnd() * 0.6, color: 'cfd8dc', opacity: 0.2 + rnd() * 0.3 }
          : null,
        description: 'Geante gazeuse : aucun sol, on la traverse de part en part.',
      });
    } else {
      // Monde tellurique. Le climat decide du profil de relief et de la palette.
      let palette = 'barren';
      let profile = 'barren';
      let seaType = null;
      let seaFraction = 0;
      if (tempClass === 'inferno' || tempClass === 'torrid') {
        palette = rnd() < 0.5 ? 'inferno' : 'desert';
        profile = palette === 'inferno' ? 'volcanic' : 'desertic';
        if (palette === 'inferno') {
          seaType = 'lava';
          seaFraction = 0.15 + rnd() * 0.25;
        }
      } else if (tempClass === 'hot') {
        palette = 'desert';
        profile = 'desertic';
      } else if (tempClass === 'temperate' || tempClass === 'warm') {
        palette = 'earthlike';
        profile = rnd() < 0.3 ? 'oceanic' : 'continental';
        seaType = 'water';
        seaFraction = profile === 'oceanic' ? 0.78 + rnd() * 0.14 : 0.42 + rnd() * 0.25;
      } else if (tempClass === 'cool' || tempClass === 'cold') {
        palette = 'tundra';
        profile = 'glacial';
        seaType = 'water';
        seaFraction = 0.3 + rnd() * 0.3;
      } else {
        palette = rnd() < 0.5 ? 'glacial' : 'barren';
        profile = palette === 'glacial' ? 'glacial' : 'barren';
        if (palette === 'glacial') {
          seaType = 'ice';
          seaFraction = 0.5 + rnd() * 0.25;
        }
      }
      const radius = Math.round(2600 + rnd() * 4600);
      raws.push({
        id,
        name: nom,
        orbitAU: +au.toFixed(3),
        radius,
        type: seaType === 'lava' ? 'volcanic' : seaFraction > 0.75 ? 'ocean' : palette === 'desert' ? 'desert' : palette === 'glacial' ? 'ice' : palette === 'barren' ? 'barren' : 'rocky',
        tempClass,
        tempK: Math.round(300 / Math.sqrt(au)),
        palette,
        noiseProfile: profile,
        seaFraction,
        seaType,
        gravity: 3.4 + (radius / 7200) * 6.6,
        dayLength: Math.round(300 + rnd() * 500),
        axialTilt: rnd() * 0.6,
        iceCaps: seaType === null && (tempClass === 'cold' || tempClass === 'frozen'),
        iceCapLat: 0.86,
        atmosphere: rnd() < 0.82 ? { ...ATMO_PAR_CLASSE[tempClass] } : null,
        clouds:
          rnd() < 0.7
            ? { coverage: 0.15 + rnd() * 0.5, color: 'e8eaec', speed: 0.06 + rnd() * 0.1, altitude: 0.028 }
            : null,
        description: 'Releve orbital incomplet : la surface reste a explorer.',
      });
    }
    au *= 1.35 + rnd() * 0.55;
  }

  // Candidats a la vie : les mondes temperes avec de l'eau liquide.
  const candidats = raws.filter((r) => r.seaType === 'water');
  if (candidats.length === 0) {
    // Aucune zone habitable tiree : on en force une au corps le plus central.
    const c = raws[Math.min(2, raws.length - 1)];
    c.seaType = 'water';
    c.seaFraction = 0.55;
    c.palette = 'earthlike';
    c.noiseProfile = 'continental';
    c.tempClass = 'temperate';
    c.atmosphere = { ...ATMO_PAR_CLASSE.temperate };
    candidats.push(c);
  }
  // On reserve D'ABORD le monde d'origine parmi les mondes a eau liquide : un
  // ancien monde habitable dont les oceans se sont retires. Sans cette reserve,
  // tous les mondes temperes partent a la vie et le joueur decolle d'un caillou
  // volcanique, ce qui ne raconte rien.
  let foyerReserve = null;
  if (candidats.length >= 2) {
    const tri = [...candidats].sort((a, b) => scoreFoyer(a) - scoreFoyer(b));
    foyerReserve = tri[0];
    const k = candidats.indexOf(foyerReserve);
    if (k >= 0) candidats.splice(k, 1);
  }

  for (let i = candidats.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [candidats[i], candidats[j]] = [candidats[j], candidats[i]];
  }

  const gagnant = candidats[0];
  gagnant.hasOcean = true;
  gagnant.hasTrees = true;
  gagnant.hasFauna = true;
  gagnant.viable = true;
  gagnant.palette = 'garden';
  gagnant.tempClass = 'temperate';
  gagnant.noiseProfile = 'continental';
  gagnant.atmosphere = { ...ATMO_PAR_CLASSE.temperate };
  gagnant.seaFraction = Math.min(0.65, Math.max(0.45, gagnant.seaFraction));
  if (candidats[1]) {
    candidats[1].hasOcean = true;
    candidats[1].hasTrees = true;
  }
  if (candidats[2]) candidats[2].hasOcean = true;

  // Monde d'origine : un tellurique epuise. Jamais le gagnant, et jamais un
  // leurre porteur de vie (on decollerait d'un monde deja a 1/3 ou 2/3).
  const sansVie = raws.filter(
    (r) => r.type !== 'gas' && !r.viable && !r.hasOcean && !r.hasTrees && !r.hasFauna,
  );
  let foyer = foyerReserve;
  if (!foyer) {
    const foyers = sansVie.length ? sansVie : raws.filter((r) => r.type !== 'gas' && !r.viable);
    foyers.sort((a, b) => scoreFoyer(a) - scoreFoyer(b));
    foyer = foyers[0] || raws[0];
  }
  foyer.isHome = true;
  foyer.hasOcean = false;
  foyer.hasTrees = false;
  foyer.hasFauna = false;
  foyer.viable = false;
  foyer.palette = 'dying';
  // Des mers residuelles, pas un ocean : c'est ce qui reste apres l'assechement.
  if (foyer.seaType === 'water') {
    foyer.seaFraction = 0.17;
    foyer.noiseProfile = 'arid';
  }
  foyer.description =
    'Notre monde. Ses oceans se sont retires et ses forets ont brule : il ne reste que de la poussiere.';

  return buildFromRaw(raws, {
    seedStr,
    auScale: 1,
    star: { name: `Etoile ${seedStr.slice(0, 8).toUpperCase()}` },
    redistribute: false,
  });
}

// ---------------------------------------------------------------------------
// Choix du systeme
// ---------------------------------------------------------------------------

export const SYSTEM_CHOICES = [
  {
    id: 'odyssey',
    name: 'Odyssee',
    summary: '12 corps ecrits a la main, du monde de lave a la geante glacee. Le systeme de la campagne.',
  },
  {
    id: 'sol1',
    name: 'Sol-1',
    summary:
      'Notre systeme solaire : 8 planetes, distances et rayons proportionnels aux valeurs reelles. Depart de Mars.',
  },
  {
    id: 'random',
    name: 'Genere aleatoirement',
    summary: '8 a 12 corps tires au sort : orbites, climats, geantes et anneaux. Une seule planete viable.',
  },
];

/** Construit un systeme a partir d'un choix de menu. */
export function buildSystem(choice = 'odyssey', seedStr) {
  if (choice === 'sol1') return buildSolSystem(seedStr || 'sol1');
  if (choice === 'random') return generateRandomSystem(seedStr || randomSeed());
  return buildSolarSystem(seedStr || 'odyssey');
}

/** Seed lisible, differente a chaque appel. */
export function randomSeed() {
  const n = Math.floor(Math.random() * 0xffffffff).toString(36);
  return `x${n}`;
}

let memo = null;

/** Systeme memoise. `?system=` et `?seed=` permettent de le forcer. */
export function getSystem() {
  if (memo) return memo;
  let choice = 'odyssey';
  let seed = null;
  if (typeof location !== 'undefined' && location.search) {
    const q = new URLSearchParams(location.search);
    if (q.get('system')) choice = q.get('system');
    if (q.get('seed')) seed = q.get('seed');
  }
  memo = buildSystem(choice, seed);
  memo.choice = choice;
  return memo;
}

/** Remplace le systeme courant (appele par le menu principal). */
export function setSystem(choice, seedStr) {
  memo = buildSystem(choice, seedStr);
  memo.choice = choice;
  return memo;
}

export function planetById(system, id) {
  return system.planets.find((p) => p.id === id) || null;
}
