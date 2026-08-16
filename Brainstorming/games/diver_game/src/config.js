/**
 * ABYSSE - central tuning table.
 *
 * Every other module reads from here and nothing here imports anything, so this
 * file is the shared contract between the world, the fauna, the diver and the
 * HUD. Distances are in metres, times in seconds, angles in radians.
 *
 * The sea surface sits at y = 0. Everything playable underwater has y < 0, so
 * "depth" in the UI is simply -y.
 */

export const GAME_TITLE = 'ABYSSE';
export const GAME_SUBTITLE = 'Expedition Kaloa';
export const SAVE_KEY = 'abysse.save.v1';

// ---------------------------------------------------------------------------
// World layout
// ---------------------------------------------------------------------------

export const WORLD = {
  // Half extent of the playable square, centred on the origin.
  halfSize: 900,
  // Soft wall: past this distance from the centre the diver is pushed back.
  boundsRadius: 860,
  seaLevel: 0,
  // Deepest point of the trench. The seabed generator must never go below this.
  floorMin: -170,
  // Shallowest seabed point (the lagoon shelf next to the island).
  floorMax: -9,
  // The island sits north of the reef, its beach breaks the surface.
  island: { x: 0, z: -640, radius: 190, peak: 34 },
  // Where the submarine waits underwater, and where it docks at the island.
  subAnchor: { x: 40, z: 120, y: -26 },
  subDock: { x: -18, z: -486, y: 0.6 },
  // Where the diver stands after climbing out at the island dock.
  dockLanding: { x: -18, z: -498 },
  // The scientist and his hut.
  scientist: { x: 26, z: -560 },
  lab: { x: 44, z: -572 },
};

export const BIOMES = {
  LAGOON: 'lagoon',
  KELP: 'kelp',
  ROCKS: 'rocks',
  WRECK: 'wreck',
  ABYSS: 'abyss',
};

/**
 * Biome rings, ordered from the island outward. `world.biomeAt()` resolves a
 * point to one of these ids; fauna spawning and ambience keys off it.
 */
export const BIOME_INFO = {
  [BIOMES.LAGOON]: {
    label: 'Lagon corallien',
    depth: [6, 26],
    fogColor: 0x2fa8bd,
    fogDensity: 0.0105,
    ambient: 0.85,
  },
  [BIOMES.KELP]: {
    label: 'Foret de kelp',
    depth: [20, 50],
    fogColor: 0x1c7f8e,
    fogDensity: 0.015,
    ambient: 0.6,
  },
  [BIOMES.ROCKS]: {
    label: 'Arches rocheuses',
    depth: [32, 68],
    fogColor: 0x145f77,
    fogDensity: 0.019,
    ambient: 0.45,
  },
  [BIOMES.WRECK]: {
    label: 'Epave du Meroe',
    depth: [48, 82],
    fogColor: 0x0e4a63,
    fogDensity: 0.023,
    ambient: 0.34,
  },
  [BIOMES.ABYSS]: {
    label: 'Fosse abyssale',
    depth: [70, 170],
    fogColor: 0x04182c,
    fogDensity: 0.032,
    ambient: 0.07,
  },
};

// ---------------------------------------------------------------------------
// Colours shared across procedural meshes and the HUD
// ---------------------------------------------------------------------------

export const PALETTE = {
  surface: 0x8fe6ff,
  shallowWater: 0x3fc4d8,
  deepWater: 0x05243c,
  sand: 0xd8c9a3,
  rock: 0x5a5f63,
  darkRock: 0x33383d,
  coralPink: 0xff7ba8,
  coralOrange: 0xff9a4d,
  coralPurple: 0xa06bd6,
  kelp: 0x3f7a34,
  kelpDark: 0x24491f,
  hull: 0xf2c14e,
  hullDark: 0x2e3338,
  glass: 0x9fe8ff,
  ui: 0x7fe9ff,
  uiWarn: 0xffb648,
  uiDanger: 0xff4d5e,
  uiGood: 0x64f0a8,
  blood: 0x8a1f2c,
  bioluminescent: 0x6ff2ff,
};

// ---------------------------------------------------------------------------
// Diver
// ---------------------------------------------------------------------------

export const DIVER = {
  eyeHeight: 0.9,
  radius: 0.55,
  // Swim
  swimAccel: 26,
  swimMaxSpeed: 7.2,
  sprintMultiplier: 1.85,
  verticalAccel: 20,
  verticalMaxSpeed: 5.4,
  waterDrag: 2.9,
  // Buoyancy pushes the diver up gently when idle, so you always drift toward
  // the surface if you stop swimming.
  buoyancy: 0.65,
  // Land movement, used once you climb out at the island.
  walkSpeed: 5.4,
  walkAccel: 34,
  walkDrag: 9,
  gravity: 22,
  jumpSpeed: 7.4,
  // Look
  lookSensitivity: 0.0022,
  pitchLimit: 1.5,
  // Vitals
  // A 140 unit tank with a gentler depth penalty: the deep holes bottom out at
  // 166 m, and a round trip has to leave you a little time down there.
  maxOxygen: 140,
  // Oxygen per second at the surface, scaled by depth (see oxygenDrain()).
  oxygenBaseDrain: 0.62,
  oxygenDepthFactor: 0.011,
  oxygenSprintFactor: 2.1,
  // Head height at which the diver can breathe. Deliberately a little under the
  // waterline: at the surface the head bobs around y = 0, and getting air must
  // not depend on landing on the right side of a centimetre.
  surfaceBreathY: -0.3,
  // Refill rate in open air. Fast enough that surfacing on an empty tank reads
  // as a reset rather than a slow trickle.
  surfaceRefill: 60,
  maxHealth: 100,
  healthRegen: 1.4,
  healthRegenDelay: 7,
  // Drowning damage per second once the tank is empty.
  drownDamage: 9,
  maxStamina: 100,
  staminaDrain: 17,
  staminaRegen: 12,
  // Carrying capacity of the collection net.
  netCapacity: 6,
  // Distance at which a floating specimen is picked up.
  pickupRadius: 2.6,
  // A narrow beam on purpose: at a 72 degree field of view a wide cone lights
  // the whole screen and the trench stops feeling dark.
  lampRange: 58,
  lampAngle: 0.3,
  lampIntensity: 5.5,
};

export const CAMERA = {
  fov: 72,
  near: 0.1,
  far: 1400,
  // Extra fov added at full sprint, for a sense of thrust.
  sprintFov: 7,
  bobAmplitude: 0.05,
  bobFrequency: 5.2,
};

// ---------------------------------------------------------------------------
// Weapons
// ---------------------------------------------------------------------------

/**
 * `kind` drives how the diver module fires the weapon:
 *   projectile - spawns a travelling spear, resolved by fauna.raycast per step
 *   hitscan    - instant ray, small spread
 *   melee      - short sphere sweep in front of the diver
 */
export const WEAPONS = [
  {
    id: 'harpoon',
    name: 'Harpon',
    kind: 'projectile',
    damage: 58,
    // Spears are recovered automatically, so ammo is really "spears in the bag".
    magazine: 1,
    reserve: 12,
    reloadTime: 1.45,
    fireDelay: 0.25,
    speed: 62,
    gravity: 3.4,
    range: 90,
    spread: 0.004,
    knockback: 5.5,
    noise: 0.55,
    hint: 'Un trait, beaucoup de degats. Le cable ramene la fleche.',
  },
  {
    id: 'needler',
    name: 'Fusil a aiguilles',
    kind: 'hitscan',
    damage: 13,
    magazine: 14,
    reserve: 112,
    reloadTime: 2.1,
    fireDelay: 0.11,
    range: 46,
    spread: 0.028,
    knockback: 0.8,
    noise: 0.3,
    hint: 'Rafale rapide et courte portee. Ideal sur les bancs.',
  },
  {
    id: 'shocker',
    name: 'Baton electrique',
    kind: 'melee',
    damage: 120,
    magazine: 4,
    reserve: 10,
    reloadTime: 2.6,
    fireDelay: 0.7,
    range: 3.6,
    radius: 1.7,
    knockback: 14,
    noise: 0.9,
    // Predators hit by the shocker flee instead of pressing the attack.
    stun: 4.5,
    hint: 'Contact uniquement. Fait fuir les predateurs.',
  },
  {
    id: 'netgun',
    name: 'Lance-filet',
    kind: 'net',
    // A capture tool, not a weapon: it never wounds anything.
    damage: 0,
    magazine: 1,
    reserve: 8,
    reloadTime: 1.9,
    fireDelay: 0.55,
    speed: 30,
    gravity: 2.2,
    range: 40,
    spread: 0.01,
    knockback: 0,
    noise: 0.18,
    // Everything inside this radius of the impact is caught in the mesh.
    captureRadius: 3.2,
    // Animals up to this size go straight into the collection net. Anything
    // bigger, and anything that hunts you, only gets tangled.
    captureSize: 1.6,
    entangle: 5.5,
    hint: 'Capture vivante. Un tir dans un banc en ramene plusieurs.',
  },
];

// ---------------------------------------------------------------------------
// Species
// ---------------------------------------------------------------------------

/**
 * Species table. `body` selects the procedural mesh builder in fauna.js, the
 * rest is shared by the AI, the codex and the scoring.
 *
 *   behaviour: 'school' | 'drifter' | 'solo' | 'ambush' | 'predator'
 *   danger:    0 harmless, 1 hurts on contact, 2 actively hunts the diver
 *   rarity:    'commune' | 'peu commune' | 'rare' | 'tres rare' | 'legendaire'
 */
export const SPECIES = [
  {
    id: 'clownfish',
    name: 'Poisson-clown',
    latin: 'Amphiprion ocellaris',
    body: 'reeffish',
    biomes: [BIOMES.LAGOON],
    depth: [5, 26],
    behaviour: 'school',
    schoolSize: [9, 16],
    size: 0.34,
    speed: 3.4,
    health: 18,
    danger: 0,
    rarity: 'commune',
    value: 40,
    colors: [0xff7a1a, 0xffffff, 0x1a1a1a],
    note: 'Vit en symbiose avec les anemones. Se faufile des que la lampe le touche.',
  },
  {
    id: 'tang',
    name: 'Chirurgien bleu',
    latin: 'Paracanthurus hepatus',
    body: 'reeffish',
    biomes: [BIOMES.LAGOON, BIOMES.KELP],
    depth: [8, 34],
    behaviour: 'school',
    schoolSize: [10, 20],
    size: 0.4,
    speed: 3.9,
    health: 22,
    danger: 0,
    rarity: 'commune',
    value: 45,
    colors: [0x1f6fe0, 0x0b1c46, 0xffd42a],
    note: 'Scalpel retractile a la base de la queue. Nage en banc serre.',
  },
  {
    id: 'parrotfish',
    name: 'Poisson-perroquet',
    latin: 'Scarus ghobban',
    body: 'reeffish',
    biomes: [BIOMES.LAGOON],
    depth: [6, 30],
    behaviour: 'solo',
    schoolSize: [1, 3],
    size: 0.72,
    speed: 3.0,
    health: 42,
    danger: 0,
    rarity: 'commune',
    value: 60,
    colors: [0x2fd6a8, 0xff8fd0, 0x6be3ff],
    note: 'Broute le corail et recrache du sable. Un individu produit 90 kg de sable par an.',
  },
  {
    id: 'turtle',
    name: 'Tortue verte',
    latin: 'Chelonia mydas',
    body: 'turtle',
    biomes: [BIOMES.LAGOON, BIOMES.KELP],
    depth: [8, 42],
    behaviour: 'drifter',
    schoolSize: [1, 2],
    size: 1.35,
    speed: 2.2,
    health: 95,
    danger: 0,
    rarity: 'peu commune',
    value: 130,
    colors: [0x5f7a3a, 0x2f3d20, 0xd9c78a],
    note: 'Remonte respirer toutes les cinq minutes. Retrouve sa plage de naissance a 2000 km.',
  },
  {
    id: 'grouper',
    name: 'Merou brun',
    latin: 'Epinephelus marginatus',
    body: 'bulkfish',
    biomes: [BIOMES.KELP, BIOMES.ROCKS],
    depth: [22, 60],
    behaviour: 'solo',
    schoolSize: [1, 2],
    size: 1.15,
    speed: 2.6,
    health: 110,
    danger: 0,
    rarity: 'peu commune',
    value: 120,
    colors: [0x6b5a3e, 0x3a3122, 0xc4b183],
    note: 'Territorial. Change de sexe au cours de sa vie.',
  },
  {
    id: 'manta',
    name: 'Raie manta',
    latin: 'Mobula birostris',
    body: 'ray',
    biomes: [BIOMES.KELP, BIOMES.ROCKS],
    depth: [18, 65],
    behaviour: 'drifter',
    schoolSize: [1, 2],
    size: 3.1,
    speed: 3.2,
    health: 160,
    danger: 0,
    rarity: 'rare',
    value: 260,
    colors: [0x2a3644, 0xf0f4f8, 0x151c26],
    note: 'Sept metres d envergure. Le plus gros cerveau de tous les poissons.',
  },
  {
    id: 'moray',
    name: 'Murene',
    latin: 'Muraena helena',
    body: 'eel',
    biomes: [BIOMES.ROCKS, BIOMES.WRECK],
    depth: [26, 70],
    behaviour: 'ambush',
    schoolSize: [1, 1],
    size: 1.5,
    speed: 3.6,
    health: 70,
    danger: 1,
    contactDamage: 16,
    rarity: 'peu commune',
    value: 150,
    colors: [0x5b6b3f, 0x2b3320, 0xe0d8a8],
    note: 'Seconde machoire pharyngienne dans la gorge. Mord si on approche sa faille.',
  },
  {
    id: 'barracuda',
    name: 'Barracuda',
    latin: 'Sphyraena barracuda',
    body: 'sleekfish',
    biomes: [BIOMES.ROCKS, BIOMES.WRECK],
    depth: [20, 66],
    behaviour: 'school',
    schoolSize: [5, 9],
    size: 1.25,
    speed: 5.6,
    health: 62,
    danger: 1,
    contactDamage: 9,
    rarity: 'peu commune',
    value: 140,
    colors: [0xb9c4cc, 0x4a5560, 0xe8eef2],
    note: 'Pointe a 40 km/h sur une courte distance. Curieux jusqu a l imprudence.',
  },
  {
    id: 'lionfish',
    name: 'Rascasse volante',
    latin: 'Pterois volitans',
    body: 'lionfish',
    biomes: [BIOMES.WRECK, BIOMES.ROCKS],
    depth: [34, 74],
    behaviour: 'drifter',
    schoolSize: [1, 3],
    size: 0.62,
    speed: 1.7,
    health: 48,
    danger: 1,
    contactDamage: 22,
    rarity: 'rare',
    value: 210,
    colors: [0xd9452f, 0xf6e6cf, 0x3a1b16],
    note: 'Dix-huit epines venimeuses. Aucun predateur naturel hors de son aire d origine.',
  },
  {
    id: 'octopus',
    name: 'Poulpe commun',
    latin: 'Octopus vulgaris',
    body: 'octopus',
    biomes: [BIOMES.WRECK],
    depth: [40, 80],
    behaviour: 'solo',
    schoolSize: [1, 1],
    size: 1.0,
    speed: 3.4,
    health: 65,
    danger: 0,
    rarity: 'rare',
    value: 240,
    colors: [0x9a5a6b, 0x5a2f3d, 0xe0b9c2],
    note: 'Neuf cerveaux, trois coeurs. Change de texture de peau en 200 ms.',
  },
  {
    id: 'reefshark',
    name: 'Requin de recif',
    latin: 'Carcharhinus melanopterus',
    body: 'shark',
    biomes: [BIOMES.ROCKS, BIOMES.KELP],
    depth: [18, 66],
    behaviour: 'predator',
    schoolSize: [1, 2],
    size: 1.9,
    speed: 6.4,
    health: 150,
    danger: 2,
    contactDamage: 20,
    attackCooldown: 3.4,
    aggroRange: 46,
    rarity: 'peu commune',
    value: 200,
    colors: [0x6b7783, 0xe6ecef, 0x1d232a],
    note: 'Extremites des nageoires noires. Teste avant de mordre, mais teste fort.',
  },
  {
    id: 'hammerhead',
    name: 'Requin-marteau',
    latin: 'Sphyrna mokarran',
    body: 'hammerhead',
    biomes: [BIOMES.ROCKS, BIOMES.WRECK],
    depth: [30, 88],
    behaviour: 'predator',
    schoolSize: [1, 1],
    size: 2.9,
    speed: 6.9,
    health: 230,
    danger: 2,
    contactDamage: 28,
    attackCooldown: 3.0,
    aggroRange: 58,
    rarity: 'rare',
    value: 320,
    colors: [0x707d88, 0xeef2f5, 0x232a31],
    note: 'La tete en marteau porte des electrorecepteurs. Detecte un coeur qui bat sous le sable.',
  },
  {
    id: 'greatwhite',
    name: 'Grand requin blanc',
    latin: 'Carcharodon carcharias',
    body: 'shark',
    biomes: [BIOMES.ABYSS, BIOMES.WRECK],
    depth: [45, 140],
    behaviour: 'predator',
    schoolSize: [1, 1],
    size: 4.4,
    speed: 7.6,
    health: 420,
    danger: 2,
    contactDamage: 46,
    attackCooldown: 2.6,
    aggroRange: 72,
    rarity: 'tres rare',
    value: 520,
    colors: [0x5d6a75, 0xf3f6f8, 0x161c22],
    note: 'Detecte une goutte de sang dans 100 litres d eau. Charge depuis le bas.',
  },
  {
    id: 'jelly',
    name: 'Meduse bioluminescente',
    latin: 'Atolla wyvillei',
    body: 'jelly',
    biomes: [BIOMES.ABYSS, BIOMES.WRECK],
    depth: [55, 150],
    behaviour: 'drifter',
    schoolSize: [3, 7],
    size: 0.85,
    speed: 0.9,
    health: 26,
    danger: 1,
    contactDamage: 12,
    rarity: 'peu commune',
    value: 170,
    colors: [0x8e3aa8, 0x6ff2ff, 0xffffff],
    glow: 0x6ff2ff,
    note: 'Declenche une alarme lumineuse tournante quand on l attaque.',
  },
  {
    id: 'anglerfish',
    name: 'Baudroie abyssale',
    latin: 'Melanocetus johnsonii',
    body: 'angler',
    biomes: [BIOMES.ABYSS],
    depth: [80, 168],
    behaviour: 'ambush',
    schoolSize: [1, 1],
    size: 1.1,
    speed: 2.4,
    health: 130,
    danger: 2,
    contactDamage: 30,
    attackCooldown: 3.6,
    aggroRange: 26,
    rarity: 'tres rare',
    value: 460,
    colors: [0x1a1620, 0x2f2838, 0xffe27a],
    glow: 0xffd24a,
    note: 'Le leurre lumineux est une colonie de bacteries. Le male fusionne avec la femelle.',
  },
  {
    id: 'giantsquid',
    name: 'Calmar geant',
    latin: 'Architeuthis dux',
    body: 'squid',
    biomes: [BIOMES.ABYSS],
    depth: [85, 170],
    behaviour: 'predator',
    schoolSize: [1, 1],
    size: 5.2,
    speed: 5.4,
    health: 600,
    danger: 2,
    contactDamage: 40,
    attackCooldown: 3.2,
    aggroRange: 60,
    rarity: 'legendaire',
    value: 900,
    colors: [0xa33b4f, 0x5c1f2c, 0xffd8d8],
    glow: 0xff6a86,
    note: 'Des yeux de 27 cm, les plus grands du regne animal. Jamais filme vivant avant 2012.',
  },
];

export const SPECIES_BY_ID = SPECIES.reduce((acc, s) => {
  acc[s.id] = s;
  return acc;
}, {});

export const RARITY_COLOR = {
  commune: '#9fb6c2',
  'peu commune': '#64f0a8',
  rare: '#57b7ff',
  'tres rare': '#c07bff',
  legendaire: '#ffb648',
};

// ---------------------------------------------------------------------------
// Progression
// ---------------------------------------------------------------------------

export const PROGRESSION = {
  // Medals granted per brand new species handed to the scientist.
  medalPerNewSpecies: 1,
  // Medals needed before the skin picker opens.
  medalsPerSkin: 3,
  // Handing over this many distinct species at once is the milestone the brief
  // asks for, and it awards a bonus medal on top of the per-species ones.
  expeditionBonusAt: 10,
  expeditionBonusMedals: 2,
};

/**
 * Wetsuit skins. `locked: false` means available from the start. Colours feed
 * the procedural suit material in diver.js and the swatches in the HUD.
 */
export const SKINS = [
  {
    id: 'standard',
    name: 'Combinaison standard',
    locked: false,
    suit: 0x1c3f6e,
    trim: 0xf0a132,
    accent: 0x9fe8ff,
    desc: 'Neoprene 5 mm reglementaire. Rien de spectaculaire, mais elle tient chaud.',
  },
  {
    id: 'reef',
    name: 'Livree recif',
    locked: true,
    suit: 0xe4622f,
    trim: 0xfff0d0,
    accent: 0x2fd6a8,
    desc: 'Motif emprunte au poisson-clown. Les anemones vous laissent passer.',
  },
  {
    id: 'abyss',
    name: 'Peau d abysse',
    locked: true,
    suit: 0x0b1420,
    trim: 0x6ff2ff,
    accent: 0x6ff2ff,
    desc: 'Bandes bioluminescentes. Visible a trente metres dans le noir total.',
  },
  {
    id: 'tiger',
    name: 'Requin tigre',
    locked: true,
    suit: 0x4a5560,
    trim: 0x1a1f25,
    accent: 0xffd42a,
    desc: 'Rayures verticales. Les bancs de barracudas gardent leurs distances.',
  },
  {
    id: 'coral',
    name: 'Corail de feu',
    locked: true,
    suit: 0xc0243f,
    trim: 0xffb648,
    accent: 0xff7ba8,
    desc: 'Rouge qui vire au gris des quinze metres. La physique fait le camouflage.',
  },
  {
    id: 'kelp',
    name: 'Camouflage kelp',
    locked: true,
    suit: 0x2f5a2a,
    trim: 0x86a552,
    accent: 0xd6e8a0,
    desc: 'Coupe les silhouettes dans la foret. Les merous ne vous voient plus venir.',
  },
  {
    id: 'gold',
    name: 'Scaphandre dore',
    locked: true,
    suit: 0xb8912f,
    trim: 0xfff0c0,
    accent: 0xffd42a,
    desc: 'Recompense honorifique de l institut. Absolument pas discrete.',
  },
  {
    id: 'orca',
    name: 'Livree orque',
    locked: true,
    suit: 0x101418,
    trim: 0xffffff,
    accent: 0x9fe8ff,
    desc: 'Le motif du seul predateur que le grand blanc evite.',
  },
];

// ---------------------------------------------------------------------------
// Submarine
// ---------------------------------------------------------------------------

export const SUB = {
  // Distance at which the interaction prompt appears.
  interactRadius: 11,
  // Refill rates while docked at the sub. Ammo is per second and applies to
  // every weapon on the rack, magazine and reserve alike, not just the one in
  // hand: leaving the dock with a holstered stun baton still empty is exactly
  // the trap the submarine is supposed to spare you.
  oxygenRefill: 34,
  healthRefill: 16,
  ammoRefill: 14,
  // Seconds of the ascend/descend cinematic.
  transitTime: 3.4,
  hullLength: 17,
  hullRadius: 2.9,
};

// ---------------------------------------------------------------------------
// Ambience and effects
// ---------------------------------------------------------------------------

export const FX = {
  // Floating particulate ("marine snow") kept in a box around the camera.
  motesCount: 2600,
  motesBox: 46,
  bubbleCount: 220,
  godrayCount: 22,
  causticSpeed: 0.055,
  // Depth at which the sunlight has fully faded out.
  lightFalloffDepth: 96,
};

export const AUDIO = {
  masterVolume: 0.75,
  musicVolume: 0.42,
  sfxVolume: 0.85,
};

export const DEBUG = {
  // Set to true to spawn every species right next to the start point.
  spawnAll: false,
  showStats: false,
  freeFly: false,
};

// ---------------------------------------------------------------------------
// Small shared helpers (kept here so every module agrees on the maths)
// ---------------------------------------------------------------------------

export function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

export function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

export function lerp(a, b, t) {
  return a + (b - a) * t;
}

/** Frame rate independent smoothing for an exponential approach. */
export function springK(rate, dt) {
  return 1 - Math.exp(-rate * dt);
}

/** Deterministic pseudo random generator so the world rebuilds identically. */
export function makeRandom(seed) {
  let s = seed >>> 0 || 1;
  return function random() {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
}

/** Oxygen drained per second at a given depth. */
export function oxygenDrain(depth, sprinting) {
  const base = DIVER.oxygenBaseDrain * (1 + Math.max(0, depth) * DIVER.oxygenDepthFactor);
  return sprinting ? base * DIVER.oxygenSprintFactor : base;
}
