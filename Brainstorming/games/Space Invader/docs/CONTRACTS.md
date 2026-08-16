# TERRAFORM ODYSSEY - Contrats de modules (source de verite)

Regles non negociables pour tout module :

1. **ES modules**, `import * as THREE from 'three'`. Aucune globale.
2. **Pas de tiret cadratin** (U+2014) dans le code, les commentaires ou les chaines. Utiliser `-`.
3. Commentaires et libelles utilisateur en **francais**, identifiants en **anglais**.
4. Un module ne lit **jamais** l'etat d'un autre module : tout passe par les
   arguments decrits ici. Pas de singleton cache, sauf `getSystem()` /
   `setSystem()` de `gen/planetSpec.js`.
5. **Rendu relatif camera** : il n'existe pas d'offset global de scene. Chaque
   frame, `SolarSystem` place les groupes de planetes a
   `absolutePosition - viewOrigin`. Tout ce qui est *dans* une planete travaille
   en **espace local planete** (origine = centre de la planete, axes = repere
   tournant de la planete). Aucun module de `render/`, `life/` ne doit connaitre
   `viewOrigin`.
6. Toute geometrie de patch a ses positions **relatives au centre du patch**
   (precision float32). Le `Mesh` est positionne au centre du patch.
7. `dispose()` obligatoire : libere geometries, materiaux, textures, workers.
8. Zero fichier binaire, zero `fetch`, zero CDN.
9. Unites : 1 unite = 1 metre. Angles en radians. Temps en secondes.

---

## Espaces de coordonnees

| Espace | Origine | Utilise par |
|---|---|---|
| **absolu** (`abs`) | le soleil | orbites, position du vaisseau, distances de nav |
| **local planete** (`local`) | centre de la planete, tourne avec elle | terrain, ocean, nuages, vie, collision |
| **vue** (`view`) | position du vaisseau (`viewOrigin`) | ce qui est envoye au GPU |

Conversions fournies par `world/planet.js` :
`planet.toLocal(abs, out)`, `planet.toAbs(local, out)`, `planet.upAt(abs, out)`.

---

## P0 - Fondations (ecrites, ne pas modifier les signatures)

### `src/core/settings.js`
```js
export const SCALE = { AU, CAM_NEAR, CAM_FAR, SUN_RADIUS, STAR_SHELL,
                       ACTIVATE_RADII, DEACTIVATE_RADII };
export const SHIP = {
  // attitude
  pitchRate, yawRate, rollRate, mouseSensitivity,
  // poussee
  thrustAtmo, thrustSpace, boostFactor, brakeFactor,
  // plafonds de vitesse "classiques"
  atmoMaxSpeed, spaceMaxSpeed,
  // pulse : acceleration libre + gouverneur de proximite
  pulseAccel, pulseMaxSpeed, pulseProximityRate, pulseMinSpeed, pulseTrackRate,
  // manoeuvrabilite et alignement automatique (touche C)
  spaceAgility, atmoAgility, alignRate,
  // vol atmospherique
  liftFactor, dragAtmo, spaceDamping, autoLevel,
  // divers
  minAltitude, landingSpeed, warpTime, gravityScale,
};
export const GAME = { SCAN_TIME, OCEAN_SCAN_ALTITUDE, TREE_SCAN_RANGE, FAUNA_SCAN_RANGE };
export const QUALITY_PRESETS = { low, medium, high, ultra };
export function getQuality(): QualityPreset;      // preset actif
export function setQuality(name: string): QualityPreset;
export function guessQuality(): string;           // preset conseille selon le materiel
```
`QualityPreset` = `{ name, maxLodDepth, patchRes, splitFactor, lifeMinLevel, workerCount,
treeDensity, faunaDensity, oceanSubdiv, cloudLayers, bloom, smaa, starCount,
heightmapSize, pixelRatio }`.

`SCALE.AU` est l'UA de reference (420 000 u). Chaque systeme peut la mettre a
l'echelle : `star.auUnit = SCALE.AU * auScale` (Sol-1 utilise `auScale = 0.4`).
`ACTIVATE_RADII` / `DEACTIVATE_RADII` sont exprimes en multiples du rayon de la
planete et decident quand son terrain LOD est construit puis relache.

**Modele de vitesse (le seul en vigueur)** : dans le vide, l'acceleration n'est
pas bridee (`pulseAccel`) et la vitesse est bornee par le gouverneur de
proximite, `clamp(nearestDistance * pulseProximityRate, pulseMinSpeed,
pulseMaxSpeed)`. Il n'existe plus de cle `atmoCruise`, `atmoBoost`,
`spaceCruise`, `spaceBoost` ni `pulse` : les plafonds atmospherique et spatial
s'appellent `atmoMaxSpeed` et `spaceMaxSpeed`.

### `src/core/math.js`
```js
export function mulberry32(seed: number): () => number;
export function hashString(s: string): number;
export function clamp(x,a,b), saturate(x), lerp(a,b,t), mix(a,b,t), invLerp(a,b,x);
export function smoothstep(e0,e1,x), smootherstep(e0,e1,x);
export function easeInOutCubic(t), easeOutCubic(t), easeInCubic(t), easeOutExpo(t);
export const CUBE_FACES: Array<{ id, key, normal:[3], uAxis:[3], vAxis:[3] }>; // 6, tableaux simples
export function spherifyCube(x, y, z, out): out;
export function damp(current, target, lambda, dt): number;
export function formatDistance(m), formatSpeed(mps): string;
export function faceUVToUnit(faceId, u, v, out: THREE.Vector3): THREE.Vector3; // u,v dans [-1,1]
export function unitToFaceUV(dir: THREE.Vector3): { faceId, u, v };
export function latLonFromUnit(dir): { lat, lon };   // lat [-PI/2,PI/2], lon [-PI,PI]
export function unitFromLatLon(lat, lon, out): THREE.Vector3;
export function tangentBasis(unit, outTangent, outBitangent): void;
```

### `src/gen/noise.js`
```js
export function makeNoise2D(seed), makeNoise3D(seed), makeNoise4D(seed);
export class FBM {
  constructor({ seed, octaves, frequency, lacunarity, gain, ridged, warp, warpFreq, erosion });
  sample(x, y, z): number;        // ~[-1,1] (ridged: [0,1])
  sampleUnit(v: THREE.Vector3): number;
}
export function fbmFromProfile(profileName, layer, seed, extra?): FBM;  // layer: 'continents'|'mountains'|'detail'
export function getProfile(profileName): object;
export const NOISE_PROFILES: Record<string, object>;
```

### Regle du cycle jour/nuit (structurante)
Les planetes **ne tournent pas** et **n'orbitent pas** pendant une partie.
Le jour/nuit vient de la rotation de la **direction du soleil dans le repere
local** de la planete (`world/planet.js` calcule `sunDirLocal` a partir de
`spec.dayLength` et `spec.spinPhase`). Le sol ne file donc jamais sous un
vaisseau en vol stationnaire. L'axe des poles en local est **+Y** : la latitude
vaut `asin(y)`. Les modules de rendu recoivent `sunDirLocal` deja calcule et ne
doivent surtout pas essayer de le deduire eux-memes.

### `src/gen/planetSpec.js`
```js
export const TEMP_CLASSES;   // 8, de 'inferno' a 'frozen'
export const PLANET_TYPES;   // 'rocky'|'ocean'|'desert'|'volcanic'|'ice'|'barren'|'gas'
export const TEMP_NORMS;     // classe -> temperature normalisee a l'equateur
export const TEMP_LABELS;    // classe -> libelle FR ('Tempere', 'Glacial', ...)
export const TYPE_LABELS;    // type -> libelle FR ('Tellurique', 'Geante gazeuse', ...)

// Constructeurs, un par systeme
export function buildSolarSystem(seedStr?: string): SolarSystemSpec;   // Odyssee, 12 corps
export function buildSolSystem(seedStr?: string): SolarSystemSpec;     // Sol-1, 8 planetes
export function generateRandomSystem(seedStr: string): SolarSystemSpec; // 8 a 12 corps

// Menu principal
export const SYSTEM_CHOICES: Array<{ id, name, summary }>;  // 'odyssey' | 'sol1' | 'random'
export function buildSystem(choice?: string, seedStr?: string): SolarSystemSpec;
export function randomSeed(): string;                // seed lisible, differente a chaque appel

// Systeme courant (seul singleton tolere)
export function getSystem(): SolarSystemSpec;   // memoise ; ?system= et ?seed= le forcent
export function setSystem(choice: string, seedStr?: string): SolarSystemSpec; // remplace le memo
export function planetById(system, id): PlanetSpec | null;
```
`SolarSystemSpec = { seed, choice?, star: { name, radius, color, intensity, coronaColor, auUnit }, planets: PlanetSpec[] }`

Le nombre de corps **n'est pas fixe** : 12 pour Odyssee, 8 pour Sol-1, 8 a 12
pour un systeme aleatoire. Aucun module ne doit supposer 12.

`buildSystem(choice, seedStr)` est le point d'entree du menu :

| `choice` | Systeme | Corps | `auScale` | Depart |
|---|---|---|---|---|
| `odyssey` | Odyssee (Helios Prime), ecrit a la main | 12 | 1 | Terra Prime |
| `sol1` | Sol-1, notre systeme solaire | 8 | 0.4 (`SOL_AU_SCALE`) | Mars |
| `random` | Genere depuis une seed | 8 a 12 | 1 | le tellurique le plus habitable |

`setSystem(choice, seedStr)` remplace le systeme memoise. C'est ce que fait
`main.js` quand le joueur valide l'ecran titre : le HUD doit alors etre
reconstruit via `hud.setSystem(system)`, puisque la liste de navigation depend
du nombre de corps.

`star.auUnit` est l'UA **du systeme** (`SCALE.AU * auScale`) : c'est elle qu'il
faut utiliser pour toute conversion UA -> unites, jamais `SCALE.AU` directement.

`PlanetSpec` (champs garantis) :
```
id, index, name, description, type, typeLabel, tempClass, tempLabel, tempNorm, tempK
isHome, viable, lifeCandidate, isGas
radius, gravity, minElevation, maxElevation, seaLevel  // metres, seaLevel = null si pas de mer
seaFraction, seaType, iceCaps, iceCapLat
orbitAU, orbitRadius, orbitPhase, orbitInclination, orbitPosition  // orbitPosition = [x,y,z] absolu
axialTilt, dayLength, spinPhase
seed, noiseProfile, palette
hasOcean, hasTrees, hasFauna                         // ce qui EXISTE reellement au sol
atmosphere: { height, densitySea, colorDay:[3], colorHorizon:[3], colorNight:[3] } | null
clouds:     { coverage, color:[3], speed, altitude } | null
gas:        { bandCount, colorA:[3], colorB:[3], colorStorm:[3], coreColor:[3], turbulence } | null
ring:       { inner, outer, color:[3], opacity } | null
```

### `src/gen/palettes.js`
```js
export const BIOMES;   // Array<{ id, key, name, water:boolean }> - 13 entrees, id === index
export const BIOME_ID; // { DEEP_OCEAN:0, SHALLOW_OCEAN:1, BEACH:2, GRASS:3, FOREST:4, JUNGLE:5,
                       //   SAVANNA:6, DESERT:7, ROCK:8, SNOW:9, ICE:10, LAVA:11, ASH:12 }
export function getPalette(paletteName): Float32Array;  // 13*3, rgb lineaire 0..1
export function buildPaletteTexture(): THREE.DataTexture; // 256x8, ligne = classe de temperature
```

### `src/gen/heightField.js`
```js
export function createHeightField(spec: PlanetSpec): HeightField;
```
`HeightField` :
```js
spec
elevation(x, y, z): number         // direction UNITAIRE -> metres signes autour de spec.radius
elevationUnit(v: Vector3): number
surfaceRadius(v: Vector3): number  // spec.radius + elevation(v)
isWater(elev): boolean             // elev < seaLevel (false si seaLevel === null)
humidity(x, y, z): number          // 0..1
temperature(x, y, z, elev): number // 0..1 (0 = glacial, 1 = brulant), tient compte latitude+altitude
biomeId(x, y, z, elev): number     // BIOME_ID.*
colorAt(x, y, z, elev, out: Float32Array|Array, offset=0): void; // rgb 0..1
slope(x, y, z, eps?): number       // 0..1
normalAt(v: Vector3, out: Vector3): Vector3
```
**Determinisme absolu** : meme entree -> meme sortie, dans le worker comme
dans le thread principal. Aucune dependance a `THREE` cote calcul scalaire.
Le champ est **memoise par `id:seed`** : deux appels renvoient la meme instance.
`spec.seaLevel` est `null` a la sortie de `buildSolarSystem` et n'est renseigne
que par `createHeightField` (calibrage par quantile sur 1400 echantillons de
Fibonacci). Tout module qui a besoin de `spec.seaLevel` doit donc etre construit
**apres** le champ de hauteur (c'est ce que fait `world/planet.js`).

### `src/core/events.js`
```js
export class Emitter { on(name, cb): () => void; off(name, cb); emit(name, payload); clear(); }
```

### `src/core/input.js`
```js
export function createInput(domElement): Input;
```
`Input` : `.axes = { pitch, yaw, roll, thrust, strafe, vertical }` (chacun -1..1),
`.buttons = { boost, brake, scan, warp, map, cameraToggle, land, help, gui }`,
`.pressed(name)` (front montant, consomme), `.mouse = {dx, dy, wheel, locked}`,
`.update(dt)`, `.setLocked(bool)`, `.dispose()`.

**Schema de commandes (volontairement minimal, clavier francais)** - cinq
touches pour piloter, le reste est contextuel. `event.code` est utilise, donc la
meme table marche en AZERTY et en QWERTY :

| touche AZERTY | code | effet | axe |
|---|---|---|---|
| `Z` | KeyW | descendre | `pitch = -1` |
| `S` | KeyS | monter | `pitch = +1` |
| `Q` | KeyA | tourner a gauche | `yaw = +1` |
| `D` | KeyD | tourner a droite | `yaw = -1` |
| `Espace` | Space | poussee | `thrust = +1` |
| fleches | Arrow* | idem, mais fleche haut = monter | |
| `A` / `E` | KeyQ / KeyE | roulis (facultatif) | `roll = +/-1` |
| `Maj` | Shift* | postcombustion, vitesse pulse dans le vide | bouton `boost` |
| `Ctrl` / `X` | Control* / KeyX | freins | bouton `brake` |
| `C` | KeyC | maintenir pour aligner le nez sur la cible | bouton `align` |
| `F` `J` `M` `V` `L` `H` `G` | | analyser, saut, orbites, camera, train, aide, reglages | boutons |
| `T` / `R` | KeyT / KeyR | cible de nav suivante / precedente | gere par `main.js` |

Conventions de signe (verifiees contre `game/ship.js`) : `pitch > 0` cabre,
`yaw > 0` tourne a gauche, `roll > 0` incline a gauche. Les axes `strafe` et
`vertical` restent dans l'API mais aucune touche ne les alimente.
`game/ship.js` ajoute un **virage coordonne** : l'assiette visee s'incline dans
le virage proportionnellement a `yaw` (constante `BANK_MAX`).

---

## P1 - Terrain

### `src/gen/terrainWorker.js` (worker ES)
Protocole strict (un message = une reponse, `id` echo) :
```
<- { type:'init', spec }                                   -> { type:'ready', id }
<- { type:'patch', id, faceId, u0, v0, size, res }          -> { type:'patch', id, ...patch }
<- { type:'heightmap', id, width, height }                  -> { type:'heightmap', id, ... }
<- { type:'scatter', id, faceId, u0, v0, size, count, kind } -> { type:'scatter', id, ... }
```
`patch` (tous les typed arrays sont transferes) :
```
position: Float32Array(n*3)   // RELATIF a center, jupe incluse
normal:   Float32Array(n*3)
color:    Float32Array(n*3)
uv:       Float32Array(n*2)   // 0..1 dans le patch
index:    Uint32Array
center:   [x,y,z]             // espace local planete
boundRadius: number
minElev, maxElev: number
biomeHistogram: Uint32Array(13)
waterFraction: number         // 0..1
```
La jupe : ceinture de sommets sur le bord du patch, descendue de
`max(2, size*spec.radius*0.05)` metres vers le centre de la planete.

`heightmap` -> `{ height: Float32Array(w*h) /* metres */, biome: Uint8Array(w*h), water: Uint8Array(w*h) }`
en projection equirectangulaire (`x` = longitude -PI..PI, `y` = latitude +PI/2..-PI/2).

`scatter` -> positions candidates de vie sur le patch :
`{ position: Float32Array(k*3) /* local planete, SUR le sol */, normal: Float32Array(k*3), biome: Uint8Array(k), scale: Float32Array(k) }`
`kind` = `'tree'` (biomes FOREST/JUNGLE/GRASS/SAVANNA) ou `'rock'` ou `'fauna'`.

### `src/gen/workerPool.js`
```js
export class WorkerPool {
  constructor({ size, factory });            // factory: () => Worker
  async init(spec): Promise<void>;
  request(msg: object): Promise<object>;     // msg.id ajoute automatiquement
  cancel(id): void;                          // annule si pas encore parti
  get pending(): number; get queued(): number;
  dispose(): void;
}
export function createTerrainPool(spec, size): Promise<WorkerPool>;
```

### `src/render/materials/terrainMaterial.js`
```js
export function createTerrainMaterial({ spec, paletteTexture, detailNormal }): THREE.ShaderMaterial;
// uniforms attendus (mis a jour par world/planet.js) :
//   uSunDir (vec3, local planete), uCameraLocal (vec3), uPlanetRadius, uSeaLevel,
//   uFogColor (vec3), uFogDensity, uAtmoHeight, uTime, uNightAmbient (vec3)
export function updateTerrainMaterial(mat, { sunDirLocal, cameraLocal, fogColor, fogDensity, time }): void;
```

### `src/render/quadtreeTerrain.js`
```js
export class QuadtreeTerrain {
  constructor({ spec, heightField, pool, material, quality });
  object3D: THREE.Group;                     // espace local planete
  update(cameraLocal: THREE.Vector3, dt: number): void;
  get stats(): { nodes, meshes, pending, depth };
  onPatchReady(cb: (p: PatchInfo) => void): () => void;
  onPatchRemoved(cb: (key: string) => void): () => void;
  dispose(): void;
}
```
`PatchInfo = { key, faceId, u0, v0, size, level, center: Vector3, boundRadius, mesh, biomeHistogram, waterFraction, minElev, maxElev }`
Critere de split : `distance(cameraLocal, node.center) < node.boundRadius * splitFactor`
avec `splitFactor = 2.6`. Profondeur max `quality.maxLodDepth`. Merge avec
hysteresis (x1.25) pour eviter le clignotement. Un noeud ne s'affiche que
lorsque ses 4 enfants sont prets (pas de trou).

---

## P2 - Enveloppes planetaires

### `src/gen/heightmapTexture.js`
```js
export async function createPlanetMaps({ spec, pool, size }): Promise<{
  heightTexture: THREE.DataTexture,   // R float
  biomeTexture:  THREE.DataTexture,   // RGBA8 couleur biome
  heightData: Float32Array, biomeData: Uint8Array, waterData: Uint8Array,
  width, height,
  oceanCoverage: number,              // fraction de surface sous seaLevel
  sample(lat, lon): { elev, biome, water },
  dispose(): void
}>;
```

### `src/render/ocean.js`
```js
export function createOcean({ spec, maps, quality }): {
  object3D: THREE.Mesh;               // local planete
  update(dt, { sunDirLocal, cameraLocal, cameraAltitude }): void;
  dispose(): void;
};
```

### `src/render/atmosphere.js`
```js
export function createAtmosphere({ spec }): {
  object3D: THREE.Mesh;               // local planete, BackSide
  update(dt, { sunDirLocal, cameraLocal, altitude }): void;
  densityAt(altitude): number;                    // 0..1
  skyColor(sunDirLocal, cameraLocal, out: THREE.Color): THREE.Color;
  fogParams(altitude, sunDot): { color: THREE.Color, density: number };
  dispose(): void;
};
```

### `src/render/clouds.js`
```js
export function createClouds({ spec, quality }): {
  object3D: THREE.Group;              // local planete
  update(dt, { sunDirLocal, cameraLocal, altitude }): void;
  dispose(): void;
};
```

---

## P3 - Espace

### `src/render/starfield.js`
```js
export function createStarfield({ seed, quality }): {
  object3D: THREE.Group;              // suit la camera (position = camera.position)
  background: THREE.Texture;          // cubemap nebuleuse pour scene.background
  update(dt, { cameraPosition, atmoDensity }): void;
  dispose(): void;
};
```

### `src/render/sun.js`
```js
export function createSun({ star, quality }): {
  object3D: THREE.Group;              // place en espace vue par main.js
  light: THREE.DirectionalLight;
  update(dt, { sunViewPos, cameraViewPos, distanceToSun }): void;
  dispose(): void;
};
```

### `src/render/fx.js`
```js
export function createSpeedLines({ quality }): { object3D, update(dt, { velocity, speed, density }), dispose() };
export function createReentryGlow(): { object3D, update(dt, { speed, density, forward }), dispose() };
export function createEngineTrail(): { object3D, update(dt, { throttle, boost }), dispose() };
```

---

## P4 - Geantes gazeuses

### `src/render/gasGiant.js`
```js
export function createGasGiant({ spec, quality }): {
  object3D: THREE.Group;              // local planete (coques + anneau)
  update(dt, { sunDirLocal, cameraLocal, insideFactor }): void;
  insideFactorAt(cameraLocal): number;   // 0 dehors, 1 au coeur
  fogFor(insideFactor, out: THREE.Color): { color, density };
  dispose(): void;
};
```
Traversee : `insideFactor > 0` -> les coques passent en `DoubleSide` +
`depthWrite:false`, brouillard dense colore, turbulence appliquee par
`world/physics.js` (aucune collision solide).

---

## P5 - Vie

### `src/life/vegetation.js`
```js
export function createVegetation({ spec, heightField, pool, quality }): {
  object3D: THREE.Group;              // local planete
  addPatch(p: PatchInfo): void;       // ignore si level < quality.lifeMinLevel ou biome inadapte
  removePatch(key: string): void;
  update(dt, { cameraLocal, sunDirLocal }): void;
  nearest(cameraLocal): { distance: number, position: THREE.Vector3 } | null;
  get count(): number;
  dispose(): void;
};
```

### `src/life/fauna.js`
Meme forme que `vegetation`, plus :
```js
  nearest(cameraLocal): { distance, position, kind } | null;
```
Comportements : nuees d'oiseaux (boids simplifie, 3 regles, 24 individus par
nuee) et troupeaux au sol (marche aleatoire contrainte au sol via `heightField`).

---

## P6 - Pilotage

### `src/world/physics.js`
```js
export function gravityAt(planet, absPos, out: THREE.Vector3): THREE.Vector3;
export function atmosphereDensity(planet, altitude): number;
export function groundContact(planet, absPos, radiusMargin): { hit: boolean, groundRadius, depth, normal };
export function turbulence(t, strength, out: THREE.Vector3): THREE.Vector3;
export function integrate(state, forces, dt): void;
```

### `src/game/ship.js`
```js
export function createShip(): {
  object3D: THREE.Group;              // visuel, place en espace vue par main.js
  state: { position: Vector3 /* abs */, velocity: Vector3, quaternion: Quaternion,
           throttle: number, boost: number, landed: boolean };
  update(dt, input, env): void;
  telemetry: { speed, altitude, thrust, gForce, verticalSpeed, mach };
  forward(out): Vector3; up(out): Vector3;
  dispose(): void;
};
```
`env = { planet|null, altitude, up: Vector3, gravity: Vector3, density, groundRadius,
insideGas, nearestDistance }`.
`nearestDistance` = distance a la **surface du corps le plus proche**, tous corps
confondus (fournie par `main.js` via `SolarSystem.nearestPlanet`), `Infinity` si
le systeme est vide. Elle alimente le **gouverneur de proximite** : dans le vide,
l'acceleration n'est pas plafonnee et la vitesse maximale vaut
`clamp(nearestDistance * SHIP.pulseProximityRate, SHIP.pulseMinSpeed, SHIP.pulseMaxSpeed)`.
C'est le seul frein en vol libre, et il garantit au passage qu'un vaisseau ne
peut jamais traverser une planete entre deux frames.
Vol atmospherique : auto-nivellement sur `up`, portance, trainee = f(densite),
poussee `SHIP.thrustAtmo`, plafond de vitesse `SHIP.atmoMaxSpeed`
(x`SHIP.boostFactor` en boost).
Vol spatial : newtonien avec amortissement doux (`SHIP.spaceDamping`), poussee
`SHIP.thrustSpace`, plafond `SHIP.spaceMaxSpeed`. En maintenant `Maj` hors
atmosphere on passe en **pulse** : acceleration `SHIP.pulseAccel`, plus aucun
plafond fixe hors du gouverneur ci-dessus, et le vecteur vitesse se recale sur
le nez a `SHIP.pulseTrackRate`.

### `src/game/camera.js`
```js
export function createCameraRig({ camera }): {
  update(dt, { ship, env, input }): void;
  setMode(mode: 'chase'|'cockpit'|'orbit'): void;
  get mode(): string;
  shake(amount: number): void;
  dispose(): void;
};
```

---

## P7 - Jeu

### `src/game/strings.js`
```js
export const STR: Record<string, string>;   // tous les libelles FR
```

### `src/core/audio.js`
```js
export function createAudio(): {
  resume(): Promise<void>;
  engine(throttle, boost, density): void;
  wind(speed, density): void;
  play(name: 'scan'|'found'|'win'|'warp'|'alarm'|'ui'|'enterAtmo'): void;
  setMuted(bool): void;
  dispose(): void;
};
```

### `src/game/discovery.js`
```js
export function createDiscovery({ audio, strings }): {
  update(dt, ctx): void;
  progressFor(planetId): { ocean, trees, fauna, scanning: { key, progress } | null };
  get won(): boolean; get winReport(): object|null;
  onDiscover(cb: (e: { planetId, key }) => void): () => void;
  onWin(cb: (report) => void): () => void;
  reset(): void;
};
```
`ctx = { planet, altitude, overWater, biomeId, nearestTree, nearestFauna, scanPressed, dtScaled }`.
Regle : un element se valide apres `SCAN_TIME = 1.4 s` de proximite continue
(ocean : altitude < 900 m au-dessus d'eau ; arbres : distance < 500 m ;
faune : distance < 400 m). Victoire des que les 3 sont valides sur une meme planete.

### `src/game/hud.js`
```js
export function createHUD({ system, strings }): {
  setTelemetry(t): void;
  setPlanetInfo(spec|null, { localHour, atmoDensity, biomeName, altitude }): void;
  setSystem(system: SolarSystemSpec): void;   // rebatit la liste de nav apres un changement de systeme
  setNavList(items: Array<{ id, name, distance, type, tempClass, progress, active }>): void;
  setTarget(planetId: string|null): void;     // designe la cible active sans attendre setNavList
  setProgress(p: { ocean, trees, fauna, scanning }): void;
  setMinimap({ biomeTexture|imageData, lat, lon, markers }): void;
  setAttitude({ roll, pitch, up }): void;
  setPlanetLabels(items: Array<{ id, name, x, y, distance, visible, active }>|null): void;
  toast(text, kind?): void;
  showTitle(cb: (choix: { quality: string, system: string }) => void): void; hideTitle(): void;
  showWin(report): void;
  setHint(text): void;
  tick(dt): void;
  dispose(): void;
  // Extras (hors contrat minimal, mais exportes et utilises par main.js)
  setHelpVisible(visible: boolean): void;
  toggleHelp(): boolean;                      // renvoie le nouvel etat visible
  setLoading(text: string|null): void;        // null masque l'ecran de chargement
  strings: Record<string, string>;            // les libelles effectivement utilises
};
```
`setPlanetLabels` place les etiquettes de corps (`H10`) en espace profond :
`x` et `y` sont des **pixels ecran deja projetes par l'appelant**, le HUD ne
connait ni camera ni `viewOrigin`. Passer `null` ou une liste vide masque tout.

`showTitle` rappelle son callback avec un **objet** et non une chaine : l'ecran
titre laisse choisir la qualite *et* le systeme. `system` vaut un `id` de
`SYSTEM_CHOICES` (`'odyssey'`, `'sol1'`, `'random'`). L'integrateur passe ce
choix a `setSystem()` de `gen/planetSpec.js`, puis rebatit le HUD avec
`hud.setSystem(nouveauSysteme)` : la liste de navigation ne suppose aucun
nombre de corps.

### `src/core/engine.js`
```js
export function createEngine({ canvas }): {
  renderer, scene, camera, composer, clock,
  viewOrigin: THREE.Vector3,
  toView(abs: Vector3, out: Vector3): Vector3,
  onFrame(cb: (dt: number, elapsed: number) => void): () => void,
  start(): void, stop(): void,
  setBloom(strength): void,
  gui, stats,
  dispose(): void
};
```

---

## Verification

- `npm run build` doit passer sans erreur ni avertissement d'import non resolu.
- `node scripts/check-modules.mjs` (`npm run check`) : parse chaque fichier de
  `src/` (`node --check`).
- `node scripts/list-exports.mjs` : liste les exports reels de chaque module.
  C'est la reference pour relire ce document ; tout ecart est un bug de doc.
- `node scripts/probe-systems.mjs` : construit les trois systemes du menu et
  echoue si un systeme n'a pas exactement une planete viable et un monde
  d'origine distinct, ou si deux spheres de desactivation se recouvrent
  (mesure sur la **distance 3D reelle** entre `orbitPosition`, pas sur la
  difference de rayons orbitaux).
- `node scripts/probe-flight.mjs` : rejoue le modele de vol hors navigateur pour
  Odyssee **et** Sol-1 (dont Mars -> Terre et Mars -> Neptune) et echoue si un
  trajet depasse le budget de temps ou si le pas par frame depasse la fraction
  admise de la distance au sol.
- `node scripts/probe-planets.mjs` : echantillonne le relief et les biomes.
- Aucun `console.error` / exception au chargement de la page.
- 55+ FPS en preset `high` sur GPU integre recent, camera au sol.
