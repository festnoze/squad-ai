// Constantes globales et presets de qualite.
// 1 unite = 1 metre. Toutes les distances orbitales sont en metres "de jeu".

export const SCALE = {
  // Une UA de jeu. Volontairement bien plus courte qu'une vraie UA : le systeme
  // entier tient dans ~3,9 millions d'unites, de sorte qu'un trajet entre deux
  // mondes se compte en secondes et non en minutes.
  AU: 420_000,
  CAM_NEAR: 0.4,
  CAM_FAR: 6e7,
  // Diametre apparent d'environ 3,3 degres a 1 UA (le vrai soleil fait 0,53
  // degre : on exagere pour qu'il soit un astre a l'ecran, pas un point, mais
  // au-dela de 4 degres il devient une tache blanche qui mange le ciel).
  // A garder proportionnel a AU : sinon le soleil redevient un pate blanc.
  SUN_RADIUS: 12_000,
  STAR_SHELL: 2.4e7,
  // Distance a laquelle une planete devient "active" (terrain LOD construit),
  // exprimee en multiples de son rayon.
  ACTIVATE_RADII: 6.5,
  DEACTIVATE_RADII: 9.0,
};

export const SHIP = {
  // Pilotage volontairement arcade : lisible, tolerant, cinematographique.
  pitchRate: 1.15,
  // Q et D sont les touches de virage : le lacet doit etre franc, sinon le
  // vaisseau semble ne pas repondre.
  yawRate: 0.9,
  rollRate: 2.0,
  mouseSensitivity: 0.0022,

  thrustAtmo: 340,
  thrustSpace: 2600,
  boostFactor: 3.4,
  brakeFactor: 2.6,

  atmoMaxSpeed: 470,
  spaceMaxSpeed: 26_000,
  // Dans le vide, l'acceleration n'est plus bridee : le pulse pousse tres fort
  // et la vitesse n'est limitee que par le gouverneur de proximite ci-dessous.
  pulseAccel: 400_000,
  // Borne de securite purement numerique, jamais atteinte en pratique.
  pulseMaxSpeed: 2_000_000,

  // GOUVERNEUR DE PROXIMITE. La vitesse maximale dans le vide vaut la distance
  // a la surface du corps le plus proche multipliee par ce taux. Loin de tout,
  // elle est donc enorme ; en approche, elle retombe toute seule.
  // Deux consequences :
  //   - un trajet de D a d prend ln(D/d) / taux secondes (Terra Prime ->
  //     Aurelia : environ 8 s), donc rejoindre une planete est facile ;
  //   - le deplacement par frame vaut toujours ~2 pour cent de la distance au
  //     sol, ce qui rend impossible de traverser une planete entre deux frames.
  pulseProximityRate: 0.6,
  // Plancher : au ras d'un corps, on garde de quoi manoeuvrer.
  pulseMinSpeed: 1200,
  // Sous pulse, le vecteur vitesse se recale sur le nez a ce rythme. Sans cela,
  // on tourne mais on continue de deriver de cote a 500 000 u/s, ce qui rend la
  // navigation illisible.
  pulseTrackRate: 2.6,

  // Manoeuvrabilite : dans le vide (propulseurs d'attitude) et en air dense.
  spaceAgility: 1.0,
  atmoAgility: 1.4,
  // Vitesse d'alignement automatique sur la cible de navigation (touche C).
  alignRate: 3.4,

  liftFactor: 0.55,
  dragAtmo: 0.55,
  spaceDamping: 0.06,
  autoLevel: 1.15,

  minAltitude: 14,
  landingSpeed: 26,
  warpTime: 3.4,
  gravityScale: 1.0,
};

export const GAME = {
  SCAN_TIME: 1.4,
  OCEAN_SCAN_ALTITUDE: 900,
  TREE_SCAN_RANGE: 500,
  FAUNA_SCAN_RANGE: 400,
};

const BASE = {
  patchRes: 33,
  splitFactor: 2.6,
  lifeMinLevel: 5,
  heightmapSize: 512,
};

export const QUALITY_PRESETS = {
  low: {
    ...BASE,
    name: 'low',
    maxLodDepth: 6,
    patchRes: 25,
    workerCount: 2,
    treeDensity: 0.35,
    faunaDensity: 0.3,
    oceanSubdiv: 5,
    cloudLayers: 1,
    bloom: 0,
    smaa: false,
    starCount: 4000,
    heightmapSize: 256,
    pixelRatio: 1,
  },
  medium: {
    ...BASE,
    name: 'medium',
    maxLodDepth: 7,
    workerCount: 3,
    treeDensity: 0.6,
    faunaDensity: 0.6,
    oceanSubdiv: 6,
    cloudLayers: 2,
    bloom: 0.55,
    smaa: false,
    starCount: 8000,
    heightmapSize: 512,
    pixelRatio: 1,
  },
  high: {
    ...BASE,
    name: 'high',
    maxLodDepth: 8,
    workerCount: 4,
    treeDensity: 1.0,
    faunaDensity: 1.0,
    oceanSubdiv: 6,
    cloudLayers: 2,
    bloom: 0.75,
    smaa: true,
    starCount: 12000,
    heightmapSize: 768,
    pixelRatio: 1,
  },
  ultra: {
    ...BASE,
    name: 'ultra',
    maxLodDepth: 9,
    patchRes: 41,
    workerCount: 6,
    treeDensity: 1.6,
    faunaDensity: 1.4,
    oceanSubdiv: 7,
    cloudLayers: 2,
    bloom: 0.9,
    smaa: true,
    starCount: 18000,
    heightmapSize: 1024,
    pixelRatio: 1.25,
  },
};

let current = QUALITY_PRESETS.high;

export function getQuality() {
  return current;
}

export function setQuality(name) {
  if (QUALITY_PRESETS[name]) current = QUALITY_PRESETS[name];
  return current;
}

/** Preset conseille selon le materiel detecte. */
export function guessQuality() {
  const cores = navigator.hardwareConcurrency || 4;
  const mem = navigator.deviceMemory || 8;
  if (cores >= 12 && mem >= 16) return 'ultra';
  if (cores >= 8) return 'high';
  if (cores >= 4) return 'medium';
  return 'low';
}
