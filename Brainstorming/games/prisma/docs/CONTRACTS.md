# PRISMA - contrats de modules

Signatures publiques. Un module peut ajouter des exports, jamais en changer un.

Regles globales : ES modules natifs, zero build ; three.js r169 vendorise
(`./vendor/three.module.js`, importmap `three`) ; **aucun addon
`three/examples/jsm/*`** ; zero asset binaire ; chemins relatifs uniquement ;
interface en francais, **sans accents** dans le 3D et les textures canvas ;
jamais de tiret cadratin ; commentaires utiles en anglais ; zero allocation par
frame dans `update` (scratch au niveau module, jamais partages entre deux
fonctions qui peuvent s imbriquer).

Repere : `Y` vers le haut, une case = 1 unite. Colonne `x` vers `+X` (est),
ligne `y` vers `+Z` (sud). Le plateau est centre sur l origine.

Directions : `0 = est`, `1 = sud`, `2 = ouest`, `3 = nord`.
Couleurs : masque de 3 bits, `1 = R`, `2 = V`, `4 = B`.

---

## `src/levels.js` (donnees pures)

```js
export const COLOR_R, COLOR_G, COLOR_B, COLOR_WHITE
export const PIECE_KINDS          // ['mirror','prism','filter','combiner','splitter'], ordre des touches 1..5
export const ROTATIONS            // { mirror:4, prism:3, filter:3, combiner:4, splitter:4 }
export const PIECE_LABEL, PIECE_HELP
export const LEVELS               // 14 niveaux
export function levelCount() -> number
export function inventoryTotal(level) -> number
```

Un niveau : `{ id, name, hint, inventory, optimum, rows, solution }`.
`rows` est un tableau de chaines ASCII de meme longueur. `solution` est la
disposition de reference `[[x, y, kind, rot], ...]` qui prouve `optimum`.

Legende : `.` libre, `#` mur, `> < ^ v` emetteur blanc, `R G B Y C M W` cible,
`0..3` miroir fixe deja oriente, `p` portail (apparie au suivant en ordre de
lecture).

---

## `src/grid.js` (modele, aucune dependance three)

```js
export const CELL                 // { EMPTY, WALL, EMITTER, TARGET, MIRROR, PRISM, FILTER, COMBINER, SPLITTER, PORTAL }
export const KIND_TO_CELL, CELL_TO_KIND, COLOR_NAMES
export const DX, DY               // pas par direction

export function createGrid(level) -> Grid    // leve une Error sur grille malformee
export function inBounds(grid, x, y) -> bool
export function cellAt(grid, x, y) -> Cell
export function isFree(grid, x, y) -> bool           // sol nu, posable
export function isPlaced(grid, x, y) -> bool         // composant du joueur
export function countPlaced(grid, kind) -> number
export function totalPlaced(grid) -> number
export function remaining(grid, kind) -> number
export function canPlace(grid, x, y, kind) -> 'ok' | raison en francais
export function place(grid, x, y, kind, rot) -> bool
export function remove(grid, x, y) -> bool
export function rotate(grid, x, y, step) -> bool
export function snapshot(grid) -> number[]           // pieces posees seulement
export function restore(grid, snap)
export function sameSnapshot(a, b) -> bool
export function clearPlaced(grid)
export function cellToWorldX / cellToWorldZ (grid, i) -> number
export function worldToCellX / worldToCellY (grid, w) -> number
```

`Grid = { level, w, h, cells, emitters, targets, inventory, idx(x,y) }`.
`Cell = { type, rot, mask, dir, fixed, link }` (`link` = index du portail jumeau).

---

## `src/beam.js` (propagation)

```js
export function createSolver(grid) -> { solve() -> Result, result }
```

`Result` (objet reutilise, jamais re-alloue) :

| champ | type | sens |
|---|---|---|
| `segX`, `segY` | Int16Array | case de depart du segment |
| `segDir` | Uint8Array | direction du segment |
| `segMask` | Uint8Array | couleur du segment |
| `segInt` | Float32Array | intensite |
| `count` | number | nombre de segments valides |
| `targetGot` | Uint8Array | couleur la plus riche recue par cible (retour joueur) |
| `targetLit` | Uint8Array | 1 si la cible est allumee |
| `litCount`, `totalTargets` | number | |
| `cellEnergy` | Float32Array | 4 valeurs par case (r, v, b, intensite max) |
| `truncated` | bool | budget de segments sature |
| `solved` | bool | toutes les cibles allumees |

Modele : miroir et splitter relient les faces `rot` et `rot+1` (le dos absorbe
pour le miroir, laisse passer pour le splitter) ; le prisme sort a gauche, tout
droit et a droite avec la permutation de couleurs de sa rotation ; le filtre
masque ; le combinateur additionne tout sauf ce qui entre par sa face de sortie ;
une cible s allume sur **un seul** faisceau de couleur exacte.

Filets obligatoires : table de visite `(case, direction, couleur)` et budget dur
de 2400 segments. Les combinateurs sont resolus par iteration jusqu au point
fixe (monotone, donc convergente).

---

## `src/textures.js`

```js
export function createTextures(renderer) -> Textures
```

`Textures = { tile, panel, glow, ring, portal, env, icons, dispose() }`.
`env` est equirectangulaire et sert de sonde de lumiere (PMREM) : sans elle les
miroirs metalliques rendent noir mat. `icons` est un objet
`{ kind: dataURL }` consomme par le HUD en `background-image`.

---

## `src/render/pieces.js`

```js
export const MASK_COLOR
export function maskToColor(mask, out?) -> THREE.Color
export function createPieceFactory(textures) -> Factory
```

`Factory.build(cell, ghost?) -> THREE.Group | null` construit le visuel d une
case (mur, emetteur, cible, portail, composant).
`Factory.buildKind(kind, rot, ghost?) -> THREE.Group | null` construit un
composant hors plateau (apercu fantome).
`Factory.setEnvironment(envMap)` cable le PMREM sur tous les materiaux
standard. `Factory.dispose()` libere tout : la fabrique possede chaque geometrie
et chaque materiau, retirer un groupe de la scene ne libere donc rien.

---

## `src/render/board.js`

```js
export function createBoard(scene, renderer, textures, factory) -> Board
board.setGrid(grid)          // change de niveau, reconstruit sol et decor
board.refresh()              // diffe le modele et ne reconstruit que ce qui a change
board.setTargetStates(result)
board.setHover(x, y, valid)  // x null = masquer
board.setGhost(kind, rot, visible)
board.setSelection(x, y)     // x null = masquer
board.update(dt, camera, time)
board.dispose()
board.root
```

---

## `src/render/beamfx.js`

```js
export function createBeamFX(scene, textures) -> FX
fx.setGrid(grid)             // recree le volume de poussiere autour du plateau
fx.setSegments(result)       // deux InstancedMesh + la texture de plateau du shader
fx.setPixelScale(heightPx)
fx.update(dt)
fx.dispose()
```

---

## `src/camera.js`

```js
export function createOrbit(camera) -> Orbit
orbit.frame(grid)            // cadre le plateau, angles par defaut lisibles
orbit.orbit(dx, dy) / orbit.zoom(delta) / orbit.reset()
orbit.update(dt)
orbit.pick(ndcX, ndcY, out) -> Vector3 | null
orbit.target, orbit.state
```

---

## `src/input.js`

```js
export function createInput(element) -> Input
input.on(name, fn)           // 'hover'(ndcX,ndcY) 'orbit'(dx,dy) 'wheel'(delta)
                             // 'primary' 'secondary' 'tertiary' 'delete'
                             // 'undo' 'restart' 'pause' 'kind'(0..4)
                             // 'mute' 'help' 'recenter'
input.setEnabled(v)
input.dispose()
```

Le module ne decide jamais du sens d un clic : il rapporte ou est le pointeur et
quel bouton a ete relache sans glisser. `main.js` possede la signification.

---

## `src/hud.js` (DOM pur)

```js
export const MEDALS
export function medalFor(used, optimum) -> Medal
export function createHUD(icons) -> HUD
hud.show() / hide() / showScreen(name) / hideScreens()
hud.setLoading(pct, line)
hud.setLevel(number, level)
hud.setStats(lit, total, pieces)
hud.setTargets(grid, result)
hud.buildInventory(level, onSelect)      // une fois par niveau
hud.updateInventory(grid, selectedKind)
hud.setHint(text, sticky?) / toast(text, warn?) / banner(title, sub, ms)
hud.setMuted(bool)
hud.buildLevelGrid(levels, progress, currentIndex, onPick)
hud.setWin({ medal, used, optimum, levelName, isLast, improved })
hud.setPauseSub(text) / setEndStats(text)
```

Les identifiants DOM sont figes par `index.html`. `createHUD` leve une `Error`
si un identifiant manque.

---

## `src/audio.js`

```js
export function createAudio() -> Audio
audio.resume()                       // premier geste utilisateur
audio.setVolume(v01) / getVolume() / toggleMute() -> bool / isMuted() -> bool
audio.place() remove() rotate() select() refuse() undo()
audio.lit(index) unlit() solved() levelStart()
audio.dispose()
```

Web Audio pur, aucun fichier son. Le pad d ambiance est persistant et n est
jamais recree, uniquement rampe.

---

## `src/main.js`

Boot : renderer WebGL2 -> HUD -> textures -> fabrique -> plateau -> effets ->
camera -> audio -> entrees, puis ecran titre.

Etats : `title`, `levels`, `play`, `pause`, `win`, `end`.
Boucle : `requestAnimationFrame`, `dt` clampe a 50 ms, ordre camera -> plateau ->
faisceau -> rendu. Le faisceau est recalcule **a chaque edition**, jamais dans la
boucle de rendu.

Expose `window.game` pour la console et `window.__ready` une fois le titre
affiche.
