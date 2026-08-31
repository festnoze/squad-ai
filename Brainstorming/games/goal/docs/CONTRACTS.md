# GOAL - contrats d'API

Ce document est la **source de vérité**. Chaque module est écrit indépendamment
par un agent différent, donc toute signature listée ici est **obligatoire** : ne
renomme rien, n'ajoute pas de paramètre, ne change pas un type de retour, ne
change pas l'ordre des paramètres. Tu peux ajouter autant de membres privés
(préfixe `_`) et de helpers que tu veux.

Si un contrat te paraît impossible à tenir, **tiens-le quand même** avec une
implémentation dégradée plutôt que de le modifier : un autre agent écrit en
parallèle du code qui appelle exactement cette signature.

## 0. Règles du projet

- Godot **4.7.1**, GDScript **typé statiquement** partout où c'est possible.
- **Le jeu est entièrement généré par code.** Maillages, textures et sons sont
  **synthétisés au démarrage**. Aucun module n'a le droit de supposer qu'un
  fichier binaire existe.
- **`assets/` est facultatif, jamais une dépendance.** Un dossier de matériaux
  photographiques et de modèles CC0 peut être présent sous `res://assets/`. C'est
  un **enrichissement** : le chemin procédural reste la vérité et reste complet.
  Règles non négociables :
  - **supprimer `assets/` doit laisser le jeu entièrement jouable**, seulement
    plus grossier. Les deux portes de non régression doivent sortir en 0 sans ce
    dossier ;
  - un fichier absent n'est **jamais** une erreur : pas de `push_error`, pas de
    substitut visible. Teste toujours avec `ResourceLoader.exists()` **avant**
    `load()`, sinon le moteur pousse une erreur sur un état parfaitement légal ;
  - un point d'entrée qui ne peut répondre qu'avec un fichier rend **`null`**, et
    l'appelant garde ce qu'il avait déjà (voir `Tex.surface_detail`) ;
  - une photographie n'entre dans le rendu que **ramenée dans la bande d'albédo**
    de 2.3. On n'éclaircit jamais le jeu en collant une photo de plein jour sur
    une surface ;
  - **un seul module a le droit de savoir qu'un `.glb` existe** :
    `src/world/character_models.gd` (voir 2.13b). C'est lui qui porte toutes les
    corrections du modèle importé (échelle, orientation, boîte de culling d'un
    maillage skinné, matériaux). Partout ailleurs on parle de corps et
    d'articulations, jamais de squelette importé, et
    **`Meshes.humanoid_parts()` reste construit et reste le repli** : c'est lui
    qui dessine le gardien et le tireur quand aucun modèle n'est installé.
- Aucun `class_name` en doublon. Utilise **exactement** celui indiqué.
- Le texte affiché au joueur est en **français**. Le code, les noms de symboles,
  les docstrings et les commentaires sont en **anglais**.
- **N'utilise jamais le caractère tiret cadratin** dans aucun fichier. Utilise un
  tiret simple ou des parenthèses.
- Pas de `print()` laissé dans le code de production. Pour un diagnostic, utilise
  `push_warning()` ou `push_error()`.
- Vérifie chaque fichier que tu écris avec :
  `godot --headless --path . --check-only --script res://<chemin>.gd`
  Il doit sortir en code 0 sans `SCRIPT ERROR`.
- Ne crée jamais un fichier qui n'est pas dans ta liste. Ne modifie jamais un
  fichier qui appartient à un autre module.
- Piège moteur connu : **un `class_name` est un objet `Script`**, donc une
  méthode statique dont le nom existe déjà sur `Script`/`Object` est masquée par
  celle du moteur. N'appelle jamais une statique `is_tool`, `get_path`,
  `get_name`, `duplicate`, `emit_signal`, `has_method`, `set_script`.
- Piège moteur connu : `Match` est trop proche du mot clé `match`. L'autoload de
  l'état de la séance s'appelle **`Shootout`**, jamais `Match`.
- Les autoloads (`Game`, `Shootout`, `Sfx`) ne sont **pas** enregistrés quand
  Godot démarre avec `--script`. Un fichier qui les mentionne ne compile pas dans
  ce contexte. Les suites de `tests/` ne doivent donc **jamais** nommer un
  autoload : tout ce qui a besoin du jeu vivant passe par `tests/smoke_probe.gd`.

## 1. Repères, unités, géométrie

- 1 unité Godot = **1 mètre**. Y est vertical, vers le haut.
- **Le tireur regarde vers -Z.** La ligne de but est le plan **z = 0**. Le
  terrain de jeu est en **z > 0**, l'intérieur du but en **z < 0**.
- L'axe X est l'axe de la largeur du but. Vu du tireur, **+X est à sa droite**
  (donc à la gauche du gardien, qui lui regarde vers +Z).
- Dimensions réglementaires, toutes en mètres :

| Grandeur | Valeur | Note |
|---|---|---|
| Largeur du but (intérieur des poteaux) | 7.32 | x de -3.66 à +3.66 |
| Hauteur du but (dessous de la barre) | 2.44 | |
| Rayon d'un poteau et de la barre | 0.06 | section ronde |
| Profondeur du filet au sol | 2.00 | panneau arrière en z = -2.00 |
| Hauteur du filet arrière | 2.10 | le toit du filet descend de la barre |
| Point de penalty | z = 11.00 | x = 0 |
| Surface de réparation | 16.50 de profond, 40.32 de large | |
| Surface de but | 5.50 de profond, 18.32 de large | |
| Arc de cercle | rayon 9.15 centré sur le point | |
| Rayon du ballon | 0.11 | |
| Masse du ballon | 0.430 kg | |

- La pelouse construite s'étend de **z = -6 à z = 62** et de **x = -34 à x = 34**.
  Au delà, ce sont les tribunes.
- Gravité du projet : **9.81**, la vraie. `Aero` applique la sienne au ballon, la
  gravité du moteur ne sert qu'aux corps physiques secondaires.
- Le pas de physique est à **120 Hz** : un tir à 30 m/s parcourt 25 cm par pas,
  ce qui est indispensable pour que la détection d'arrêt ne traverse pas un gant.

### Couches de collision physique (bit -> nom)

| Bit | Masque | Nom | Contenu |
|---|---|---|---|
| 1 | 1 | pitch | la pelouse |
| 2 | 2 | goal | poteaux et barre transversale |
| 3 | 4 | net | les panneaux de filet |
| 4 | 8 | ball | le ballon |
| 5 | 16 | keeper | le gardien |
| 6 | 32 | prop | drapeaux de corner, panneaux publicitaires |
| 7 | 64 | trigger | zones de déclenchement |
| 8 | 128 | target | cibles du mode Défi |

Constantes fournies par `Layers` (voir 2.1). **N'écris jamais un masque en dur.**

## 2. Modules et signatures

Les sections sont ordonnées par dépendance. Un module ne peut appeler que des
modules listés **avant** lui, plus les autoloads.

---

### 2.1 `src/core/layers.gd` - `class_name Layers`

```gdscript
class_name Layers
extends RefCounted

const PITCH   := 1
const GOAL    := 2
const NET      := 4
const BALL    := 8
const KEEPER  := 16
const PROP    := 32
const TRIGGER := 64
const TARGET  := 128

## Everything the ball can physically stop or bounce on.
const BALL_MASK := PITCH | GOAL | NET | KEEPER | PROP | TARGET
## What the aim raycast from the camera is allowed to hit.
const AIM_MASK  := PITCH | GOAL | NET | TRIGGER
## Solid ground and frame a walking body collides with.
const WALK_MASK := PITCH | GOAL | PROP
```

---

### 2.2 `src/world/field.gd` - `class_name Field`

Géométrie **pure** du terrain et du but : constantes et prédicats, aucun noeud,
aucune dépendance. C'est le module que tout le monde interroge pour savoir si un
ballon est entré. Testé par `tests/test_pitch_geometry.gd`.

```gdscript
class_name Field
extends RefCounted

const GOAL_WIDTH   := 7.32
const GOAL_HEIGHT  := 2.44
const GOAL_HALF    := 3.66          # GOAL_WIDTH * 0.5
const POST_RADIUS  := 0.06
const NET_DEPTH    := 2.00
const NET_BACK_TOP := 2.10
const BALL_RADIUS  := 0.11
const SPOT_Z       := 11.00
const BOX_DEPTH    := 16.50
const BOX_HALF     := 20.16
const SIX_DEPTH    := 5.50
const SIX_HALF     := 9.16
const ARC_RADIUS   := 9.15
const PITCH_MIN_Z  := -6.0
const PITCH_MAX_Z  := 62.0
const PITCH_HALF_X := 34.0

## Where the ball sits before the run up.
const SPOT := Vector3(0.0, BALL_RADIUS, SPOT_Z)
## Where the keeper stands before committing.
const KEEPER_HOME := Vector3(0.0, 0.0, 0.12)

## Centre of a post. `side` is -1 for the -X post, +1 for the +X post.
static func post_centre(side: int) -> Vector3

## True when a ball centre at this point has fully crossed the goal line into
## the mouth. Uses the ball radius, so the whole ball must be over the line.
static func is_inside_mouth(point: Vector3) -> bool

## True when the point is between the posts and under the bar, ignoring z.
## This is the frame test used while the ball is still travelling.
static func is_within_frame(point: Vector3) -> bool

## Closest point of the goal frame (both posts plus the bar) to `point`, and the
## distance to it. Returns {"point": Vector3, "distance": float, "part": int}
## where part is one of the FRAME_* constants below.
const FRAME_NONE  := 0
const FRAME_POST_LEFT  := 1     # the -X post
const FRAME_POST_RIGHT := 2     # the +X post
const FRAME_BAR   := 3
static func nearest_frame(point: Vector3) -> Dictionary

## Does a ball moving from `from` to `to` over one step touch the frame?
## Returns {"hit": bool, "part": int, "point": Vector3, "normal": Vector3, "t": float}
## `t` is the fraction of the step at contact, `normal` points away from the frame.
static func sweep_frame(from: Vector3, to: Vector3) -> Dictionary

## Does the segment cross the goal plane z = 0 travelling towards -Z?
## Returns {"crossed": bool, "point": Vector3, "t": float}
static func cross_goal_plane(from: Vector3, to: Vector3) -> Dictionary

## Signed distance from the mouth rectangle, in metres. Negative inside, positive
## outside. Used by the HUD to colour the aim reticle.
static func mouth_margin(point: Vector3) -> float

## Is the ball still in play, or has it left the built area entirely?
static func is_out_of_area(point: Vector3) -> bool

## Human readable French name of a mouth region, for the verdict text.
## Returns one of "lucarne gauche", "lucarne droite", "petit filet gauche",
## "petit filet droit", "plein centre", "au ras du sol", "hors cadre".
static func mouth_region_name(point: Vector3) -> String
```

---

### 2.3 `src/render/palette.gd` - `class_name Palette`

Toutes les constantes sont **déjà en espace linéaire** et passent directement
dans `albedo_color` / `COLOR`. Piège moteur connu : un albédo trop clair se
désature vers le blanc dans l'épaule du tonemap ACES. Les albédos restent donc
dans `0.03 .. 0.72`. La bande est large parce que le maillot du gardien et les
lignes blanches portent l'image, mais le plafond est **dur** : on n'éclaircit
jamais le jeu en montant les albédos, on l'éclaircit avec la **lumière** (voir
2.17). Monter la bande, c'est reproduire le bug de la foule blanche.

Le match se joue **de jour**, plein soleil de fin d'après midi. Les constantes
de nuit sont conservées telles quelles : le look nocturne reste accessible.

```gdscript
class_name Palette
extends RefCounted

const ALBEDO_MIN := 0.03
const ALBEDO_MAX := 0.72

# Turf
const GRASS_LIGHT
const GRASS_DARK        # the mown stripe
const GRASS_WORN        # the scuffed patch around the spot
const LINE_WHITE

# Ball
const BALL_WHITE
const BALL_BLACK

# Goal
const POST_WHITE
const NET_CORD

# Kits
const KEEPER_JERSEY     # bright, this is the readable silhouette
const KEEPER_SHORTS
const KEEPER_GLOVE
const SHOOTER_JERSEY
const SHOOTER_SHORTS
const SKIN
const HAIR
const BOOT

# Stadium
const STAND_CONCRETE
const SEAT_A
const SEAT_B
const CROWD_A
const CROWD_B
const CROWD_C
const ADVERT_A
const ADVERT_B
const STEEL

# Lights and effects (all exempt from the albedo band)
# Daylight set: what the game runs on.
const SUNLIGHT         # key light colour, above the band
const SKY_DAY_TOP      # zenith radiance of a clear afternoon
const SKY_DAY_HORIZON
const FOG_DAY          # aerial perspective tint
const AMBIENT_DAY      # skylight filling the shadows, blue
# Night set: still reachable, no longer the default.
const FLOODLIGHT       # light colour, allowed above the band
const SKY_NIGHT_TOP
const SKY_NIGHT_HORIZON
const FOG_NIGHT
const AMBIENT_NIGHT
const TRAIL_HOT
const TRAIL_COLD
const UI_ACCENT
const UI_WARN
const UI_GOOD

## Deterministic slight variation around a base colour, for scatter.
static func vary(base: Color, rng_value: float, amount: float = 0.12) -> Color
## Clamps a colour back into the safe albedo band, preserving alpha.
static func clamp_albedo(c: Color) -> Color
## Linear blend between two colours, alpha included.
static func mix(a: Color, b: Color, t: float) -> Color
## Multiplies the colour brightness, staying in the safe band.
static func shade(c: Color, factor: float) -> Color
## Pulls a colour towards its own grey.
static func desaturate(c: Color, amount: float) -> Color
```

---

### 2.4 `src/render/textures.gd` - `class_name Tex`

Toutes les textures sont **synthétisées** par `Image` + `ImageTexture`. Chaque
générateur est **mis en cache** dans un dictionnaire statique : appeler deux fois
`Tex.turf()` rend la même instance, sinon le démarrage refait le travail vingt
fois. Aucune texture ne dépasse 512x512 sauf la pelouse (1024).

Piège moteur connu : une `Image` créée sans mipmaps puis convertie en
`ImageTexture` scintille de loin. Appelle `generate_mipmaps()` avant, sur **toute**
texture vue en perspective.

Trois entrées supplémentaires (`surface_*`, en bas du bloc) lisent le dossier
**facultatif** `res://assets/textures/`. Elles rendent `null` quand il n'est pas
là, et **aucun** autre générateur ne dépend d'un fichier : voir la règle en 0.
Piège moteur connu : `Image.load_from_file()` marche sur ces chemins mais relit le
fichier source, pousse un avertissement à chaque appel et casse à l'export. Le
chemin correct est `ResourceLoader.load()` puis `Image.decompress()`, qui lit ce
que l'importateur a réellement produit.

```gdscript
class_name Tex
extends RefCounted

## Mown turf: fine blade noise plus the roller stripe pattern. 1024x1024, tiles.
static func turf() -> ImageTexture
## Normal map matching turf(). Same size, tiles.
static func turf_normal() -> ImageTexture
## Painted line paint with a slightly frayed edge, for decals. 256x256.
static func line_paint() -> ImageTexture
## The classic truncated icosahedron panel colouring, laid out for the UV of
## Meshes.ball_mesh(). Black pentagons on white, with panel seams. 512x512.
static func ball_panels() -> ImageTexture
## Ball normal map: the seams pressed in, plus fine leather grain. 512x512.
static func ball_normal() -> ImageTexture
## Net cord grid with a cut out alpha. 256x256, tiles.
## The alpha channel is 0 in the holes and 1 on the cord.
static func net() -> ImageTexture
## A block of spectators seen from the pitch: coloured specks on dark seating.
## 512x512, tiles horizontally.
static func crowd() -> ImageTexture
## Broken afternoon cumulus as an EQUIRECTANGULAR panorama, 1024x512, for
## ProceduralSkyMaterial.sky_cover. ADDITIVE: black is bare sky, there is no
## alpha, and no cloud is ever drawn below the horizon.
static func clouds() -> ImageTexture
## Perimeter advertising board, abstract blocks of colour, no readable text.
static func advert(index: int) -> ImageTexture
## Woven fabric for the jerseys, subtle. 256x256, tiles.
static func fabric() -> ImageTexture
## Soft radial falloff, white centre to transparent edge. For sprites and glow.
static func radial(size: int = 128) -> ImageTexture
## A 1x256 vertical ramp between two colours, for gradient driven shaders.
static func ramp(top: Color, bottom: Color) -> ImageTexture
## Frees every cached texture. Only the tests call this.
static func clear_cache() -> void

## --- Couche photographique facultative (voir 0) ------------------------------
## Moyenne LINEAIRE d'une texture rendue par surface_detail(). Un materiau qui en
## lie une DOIT diviser son albedo par cette valeur, sinon la surface sort deux
## fois trop sombre. Elle vaut un demi et pas un : un multiplicateur centre sur 1
## ecrete toute sa moitie claire.
const DETAIL_MEAN := 0.50

## Detail photographique neutre du jeu de materiaux <name> sous
## res://assets/textures/, ou NULL si l'asset n'est pas la.
## C'est la photo reduite a son RAPPORT a sa propre moyenne puis recentree sur
## DETAIL_MEAN : un multiplicateur tuilable qu'un materiau pose sur une couleur de
## Palette comme fabric() se pose sur un maillot. Il porte le grain et la derive
## de teinte de la vraie surface, jamais sa luminosite absolue.
static func surface_detail(name: String) -> ImageTexture
## Carte de normales importee du meme jeu, ou NULL. Convention OpenGL, +Y en haut.
static func surface_normal(name: String) -> Texture2D
## Carte ARM importee du meme jeu, ou NULL. UNE image, TROIS entrees :
## R = occlusion, G = rugosite, B = metallicite. A cabler PAR CANAL avec les
## proprietes *_texture_channel, voir Mats._wire_arm.
static func surface_arm(name: String) -> Texture2D
```

`surface_detail`, `surface_normal` et `surface_arm` rendent **`null`** quand le
dossier `assets/` n'est pas là, et c'est l'état normal, pas une panne : l'appelant
garde sa couleur plate. Tous les autres générateurs de `Tex` restent capables de
produire leur texture **sans aucun fichier**.

---

### 2.5 `src/render/materials.gd` - `class_name Mats`

Fabrique et **met en cache** chaque matériau. Même règle de cache que `Tex`.

Piège moteur connu : un `StandardMaterial3D` avec `transparency = TRANSPARENCY_ALPHA`
sur le filet trie mal contre lui même et clignote. Le filet doit utiliser
`TRANSPARENCY_ALPHA_SCISSOR` avec `alpha_scissor_threshold = 0.5`, et
`cull_mode = CULL_DISABLED` pour être visible des deux côtés.

Deuxième piège moteur, sur le même matériau : un découpage par ciseau **seul** est
un test **binaire**, sans couverture partielle, donc il crénelle à toutes les
distances. Sur une texture de corde qui ne couvre que 22 % de son image, chaque
niveau de mipmap moyenne l'alpha **vers le bas** : passé le deuxième niveau la
moyenne descend sous le seuil, le filet s'amincit avec la distance et les cordes
survivantes scintillent. Le remède est le mélange à la couverture, que le projet
peut se payer puisqu'il tourne en MSAA 4x :

```gdscript
mat.alpha_antialiasing_mode = BaseMaterial3D.ALPHA_ANTIALIASING_ALPHA_TO_COVERAGE_AND_TO_ONE
mat.alpha_antialiasing_edge = 0.25
```

À retenir : une fois ce mode actif, **la vraie coupure est `alpha_antialiasing_edge`**,
pas le seuil du ciseau. Godot remappe l'alpha en `(alpha - edge) / fwidth(alpha) + 0.5`,
une valeur qui sort très largement de 0..1, donc le test à 0.5 imposé ci dessus ne
fait plus que lire le signe de cette expression : il reste **exactement** à 0.5 et
c'est `alpha_antialiasing_edge` qui décide de l'épaisseur de la corde.

```gdscript
class_name Mats
extends RefCounted

## Which hour the materials are built for. Default `true`.
## A DOIT ETRE POSITIONNE AVANT LA PREMIERE CONSTRUCTION DE MATERIAU : tout est
## mis en cache, donc le changer ensuite ne change rien. C'est la seconde moitie
## de l'interrupteur jour/nuit, la premiere etant `SkyController.evening`.
## Il pilote les plancher d'emission (beton, sieges, panneaux, lampes) qui
## n'existent que pour empecher une surface de tomber au noir sous projecteurs.
static var daylight: bool

## Metres de pelouse couverts par une tuile de la texture de gazon.
## Meshes.pitch_plane sort ses UV en METRES, donc ce materiau est seul a decider
## de la taille physique d'une tuile, et donc de la largeur d'une bande de tonte.
## Lie a Tex._TURF_STRIPES : une periode sur quatre metres donne une bande de 2 m.
const TURF_TILE_METRES := 4.0

static func turf() -> StandardMaterial3D
static func line() -> StandardMaterial3D
static func ball() -> StandardMaterial3D
static func post() -> StandardMaterial3D
static func net() -> StandardMaterial3D
static func jersey(colour: Color) -> StandardMaterial3D
static func skin() -> StandardMaterial3D
static func glove() -> StandardMaterial3D
static func boot() -> StandardMaterial3D
static func concrete() -> StandardMaterial3D
static func seat(colour: Color) -> StandardMaterial3D
static func crowd() -> StandardMaterial3D
static func advert(index: int) -> StandardMaterial3D
static func steel() -> StandardMaterial3D
## Unshaded additive material for the flight trail and the light halos.
static func additive(colour: Color) -> StandardMaterial3D
## Unshaded flat colour, used by debug gizmos and the target rings.
static func flat(colour: Color) -> StandardMaterial3D
## Emissive lamp face for the floodlight heads.
static func lamp() -> StandardMaterial3D
static func clear_cache() -> void
```

---

### 2.6 `src/audio/sfx_lib.gd` - `class_name SfxLib`

Chaque son est **synthétisé** dans un `AudioStreamWAV` (16 bits, 44100 Hz, mono
sauf mention) et mis en cache. Aucun fichier audio dans le dépôt.

Piège moteur connu : un `AudioStreamWAV` rempli sans fondu de sortie claque à la
fin. Termine **tout** échantillon par une rampe descendante d'au moins 5 ms.
Deuxième piège : un son bouclé occupe une voix pour toujours. Seule l'ambiance de
foule a le droit d'avoir `loop_mode` non nul.

```gdscript
class_name SfxLib
extends RefCounted

## Every id below is a valid argument to stream().
const IDS: PackedStringArray = [
	"kick_soft", "kick_hard", "kick_curl", "miscue",
	"net_ripple", "post_ding", "bar_ding", "ball_bounce", "ball_roll",
	"glove_punch", "glove_catch", "keeper_grunt", "keeper_land",
	"whistle_short", "whistle_long",
	"crowd_ambience", "crowd_roar", "crowd_groan", "crowd_ooh", "crowd_clap",
	"ui_move", "ui_select", "ui_back", "charge_loop", "heartbeat",
]

## Returns the cached stream for an id, or null if the id is unknown.
static func stream(id: String) -> AudioStreamWAV
## Frees every cached stream. Only the tests call this.
static func clear_cache() -> void
```

---

### 2.7 `src/audio/sfx_player.gd` - autoload `Sfx` (pas de `class_name`)

`extends Node`. Détient une réserve de `AudioStreamPlayer` (2D non spatialisés)
et de `AudioStreamPlayer3D` (spatialisés). Une réserve épuisée **vole la voix la
plus ancienne** plutôt que de laisser tomber le son.

```gdscript
## Non spatial one shot. `pitch` and `volume_db` are applied on top of the stream.
func play(id: String, volume_db: float = 0.0, pitch: float = 1.0) -> void
## Spatial one shot at a world position.
func play_at(id: String, position: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void
## Starts, or retargets, the single looping ambience voice. Empty id stops it.
func set_ambience(id: String, volume_db: float = -12.0) -> void
## Fades the ambience voice to a level over `seconds`.
func fade_ambience(volume_db: float, seconds: float) -> void
## Stops every voice, ambience included, and drops the stream each one held.
## Chemin d'ARRET, appele par `Main.quit_clean` et par personne d'autre.
## Piege moteur connu : `AudioStreamPlayer.stop()` ne rend PAS son objet de
## lecture tout de suite. Le serveur audio termine le fondu sur son propre fil,
## puis ne desenregistre le `AudioStreamPlayback` qu'a une mise a jour suivante
## du fil principal. Un processus qui quitte dans la meme image sort donc avec
## ces lectures, et avec le `AudioStreamWAV` que chacune retient, encore vivants
## dans la base d'objets : c'est exactement le message
## "N ObjectDB instances were leaked at exit". Faire taire le mixeur est la
## premiere moitie du remede, laisser tourner l'arbre un instant est la seconde.
## L'appel est a SENS UNIQUE : ensuite `play`, `play_at` et `set_ambience` ne
## demarrent plus rien, sinon la foule et le gardien remettraient une voix dans
## le serveur pendant les images de vidange.
func silence_all() -> void
## Master mute, driven by the settings.
func set_muted(muted: bool) -> void
```

---

### 2.8 `src/core/game.gd` - autoload `Game` (pas de `class_name`)

`extends Node`. Deux responsabilités :

1. Installer **tout l'InputMap depuis le code** dans `_ready()`, par **keycode
   physique** (`InputEventKey.physical_keycode`) pour qu'un clavier AZERTY pilote
   ZQSD là où un QWERTY pilote WASD.
2. Détenir les réglages, bornés, persistés dans `user://settings.cfg` via
   `ConfigFile`. Un fichier absent ou corrompu n'est jamais fatal.

Actions à déclarer, exactement ces noms :

| Action | Touches / boutons |
|---|---|
| `aim_left` `aim_right` `aim_up` `aim_down` | Q/A/flèche gauche, D/flèche droite, Z/W/flèche haut, S/flèche bas |
| `strike` | bouton gauche de la souris, Espace |
| `feint` | Maj gauche |
| `spin_left` `spin_right` | A et E (QWERTY : Q et E) |
| `next_shot` | Entrée, Espace |
| `replay` | R |
| `camera_cycle` | C |
| `pause` | Échap |
| `menu_accept` | Entrée, Espace |
| `menu_back` | Échap, Retour arrière |
| `restart` | F5 |
| `fullscreen` | F11 |

`fullscreen` est traité **dans `Game` lui-même**, dans `_input`, et non dans
`Main` : l'autoload tourne en `PROCESS_MODE_ALWAYS`, donc c'est le seul noeud qui
écoute à tous les instants du jeu (accueil, vol, replay, pause). `_input` et non
`_unhandled_input` : les menus et le HUD sont des `Control`, et un `Control` qui a
le focus mange la touche avant la passe « unhandled ».

Alt+Entrée n'est **pas** lié, volontairement : Godot fait correspondre une action
liée à Entrée nue même quand Alt est enfoncé, donc Alt+Entrée validerait un menu
et basculerait la fenêtre en même temps.

**Le jeu a deux axes de difficulté**, tous les deux réglables et persistés ici :
`keeper_level` décide de la difficulté à **battre le gardien**, `sweep_level`
décide de la difficulté à **frapper proprement**. Le second est un simple index
dans `Shooter.SWEEP_SCALES` (2.20) : `Game` n'écrit jamais une vitesse en dur, il
ne porte que le choix, le tireur porte les cadences. Les deux rangées sont
voisines dans la page de réglages et libellées « Difficulté : ... », pour que le
joueur voie qu'il s'agit d'une paire.

```gdscript
signal settings_changed()

const SETTINGS_PATH := "user://settings.cfg"

var mouse_sensitivity: float      # 0.2 .. 3.0, default 1.0
var master_volume: float          # 0.0 .. 1.0, default 0.8
var muted: bool                   # default false
var keeper_level: int             # KeeperBrain.Level, default 1
var sweep_level: int              # index into Shooter.SWEEP_SCALES, 0 .. 3, default 1
var show_trajectory: bool         # aim assist arc, default true
var show_replay: bool             # default true
var camera_shake: float           # 0.0 .. 1.0, default 0.7
var fullscreen: bool              # default false, persisted like any setting
var seed_value: int               # campaign seed, drawn once and kept

## Flips the window mode and persists the choice. Bound to F11.
## Borderless (WINDOW_MODE_FULLSCREEN) et non EXCLUSIVE_FULLSCREEN : l'alt-tab
## reste instantané, ce qui compte sur un portable.
func toggle_fullscreen() -> void

func load_settings() -> void
func save_settings() -> void
## Applies a setting by name with clamping, then emits settings_changed.
func set_setting(key: String, value: Variant) -> void
func get_setting(key: String) -> Variant
## Resets every setting to its default and saves.
func reset_settings() -> void
```

---

### 2.9 `src/core/match_state.gd` - autoload `Shootout` (pas de `class_name`)

`extends Node`. Machine à états de la séance, score, historique. **Ne touche à
aucun noeud 3D** : elle ne connaît que des nombres et des verdicts. C'est elle
qui décide quand la séance est finie.

#### Une séance ALTERNE, et un seul appelant possède chaque tir

`record_shot()` prend le tir **du joueur** et rien d'autre. `take_rival_kick()`
prend celui **de l'adversaire**, une seule fois, quand les règles le lui doivent.
Cette séparation n'est pas de la propreté : avant elle, `record_shot()` ajoutait
un tir adverse **et** `Main` en ajoutait un second depuis son horloge de verdict,
donc l'ordinateur tirait **deux penalties pour chaque tir du joueur**. Cinq tirs
du joueur affrontaient dix tirs adverses, une ligne du tableau grandissait deux
fois plus vite que l'autre, et la séance se terminait sur une arithmétique que
personne ne pouvait suivre.

**`rival_to_kick()` est la seule réponse à « à qui le tour »**, le tableau des
scores la dessine, et rien ne prend un tir que les règles ne doivent pas.

#### Le tir adverse est une VRAIE simulation

C'était un `randf()` contre une chance de but fixe de 0.745, et cela se lisait
comme de l'arbitraire parce que ça l'était : rien à l'écran, et rien de ce que le
joueur choisissait, ne pouvait le toucher.

C'est maintenant un penalty complet. Une visée, une puissance et une qualité de
frappe tirées d'une graine passent par `ShotModel`, le ballon vole dans `Aero` au
pas de physique du projet, le cadre et la ligne de but sont ceux de `Field`, et
**le tir est défendu par `KeeperBrain` au niveau du gardien du joueur**. Le taux
de réussite n'est écrit nulle part, c'est une **sortie** de la simulation :

| niveau | buts | arrêts | poteau/barre | hors cadre |
|---|---|---|---|---|
| Debutant | 74.4 % | 20.3 % | 3.2 % | 2.1 % |
| Confirme | 56.6 % | 37.6 % | 3.3 % | 2.5 % |
| Pro | 45.7 % | 49.1 % | 3.0 % | 2.2 % |
| Legende | 31.6 % | 64.2 % | 2.3 % | 1.9 % |

**Ces chiffres sont une mesure, pas une consigne**, et ils sont écrits avec leur
précision plutôt qu'avec des tildes. **4000 tirs par niveau**, sans pression, ce
qui donne une bande à deux sigma d'environ **1.5 point** sur les colonnes
« buts » et « arrêts » et d'un demi point sur les deux autres. Un chiffre de ce
tableau ne veut donc rien dire à mieux que le point et demi près, et deux
tableaux qui diffèrent d'un point ne diffèrent pas.

Pour les refaire : 4000 appels à `_rival_verdict(graine, niveau, false)` par
niveau, graines espacées d'un grand premier, et on compte les verdicts. C'est une
dizaine de lignes dans un `SceneTree` jetable, et cela coûte quelques minutes,
parce que ce chemin ne pilote **aucun noeud**. Une première rédaction de ce
tableau annonçait 29.8 % de buts pour Légende sur 900 tirs seulement : deux
relevés indépendants à n = 1500 et n = 4000 donnent 33-34 %, soit environ 5 sigma
d'écart. **Si tu touches à la chaîne `ShotModel` / `Aero` / `KeeperBrain`,
remesure** ; n'écris jamais ici un chiffre tiré de moins de quelques milliers de
tirs.

#### Le même gardien, mesuré deux fois

`tests/balance_probe.gd` tire le même genre de penalty sur le **vrai noeud
`Keeper`** au lieu de la ré-implémentation ci dessus, sur sa propre distribution
de visée réaliste. Les deux chemins doivent dire la même chose du même gardien,
et c'est le seul garde fou qui existe contre une divergence silencieuse entre
eux. Taux d'**arrêts sur frappe propre**, échantillon de référence :

| niveau | sonde en jeu (n = 2016) | tir adverse (n = 4000) | cible |
|---|---|---|---|
| Debutant | 21.2 % ± 1.8 | 20.3 % ± 1.3 | 20-25 % |
| Confirme | 38.2 % ± 2.2 | 37.6 % ± 1.5 | 35 % |
| Pro | 51.9 % ± 2.2 | 49.1 % ± 1.6 | 50 % |
| Legende | 63.6 % ± 2.1 | 64.2 % ± 1.5 | 62-68 % |

**PIÈGE, ET IL A COÛTÉ UNE JOURNÉE : déterminisme n'est pas précision.** La sonde
est entièrement graine fixe, donc deux exécutions rendent le même chiffre à la
décimale. Cela prouve qu'elle est déterministe. Cela ne dit **rien** de sa
précision : à son réglage par défaut, une case de ses tables tient sur 336 tirs
et porte une bande de **cinq points à deux sigma**. Un relevé unique a été lu
comme une mesure, comparé à un tableau plus ancien lui aussi tiré d'un relevé
unique, et l'écart de 2.7 points qui en est sorti a été rapporté comme une
régression de l'enveloppe de parade. Deux choses le contredisent : l'écart était
plus petit que le bruit des deux relevés comparés, et la simulation adverse, qui
ne passe par **aucun** des modules incriminés, donnait déjà la même valeur du
même gardien. Le déficit de Legende était réel, mais il était **ancien**, et il
ne venait pas de la couche d'animation.

Un dernier chiffre à ne pas maquiller : **Confirme mesure 38 % pour une cible
de 35**, trois points au dessus, soit un peu plus que sa propre bande. C'est
laissé tel quel et écrit ici plutôt que rattrapé, parce que la cible de ce niveau
est un point unique et non une fourchette, et qu'un niveau intermédiaire trois
points trop bon ne casse ni l'échelle ni une promesse. La prochaine personne qui
retouchera `_READ_SKILLS` sait donc dans quel sens elle a de la marge.

La colonne de gauche ci dessus est donc mesurée autrement : **six graines
indépendantes** (`--balance-seed 0` à `5`, exécutables en parallèle), comptes
bruts additionnés, soit 2016 penalties propres par niveau et une bande de deux
points. C'est la façon dont ce tableau doit être refait :

```
godot --headless --path . -- --balance --balance-live 0 --balance-seed K   # K = 0..5
```

et on additionne les quatre lignes du bloc « A RECOPIER DANS CONTRACTS 2.9 » que
chaque exécution imprime en dernier. Une seule graine ne suffit pas pour écrire
ici.

Deux chiffres secondaires du même relevé, pour qu'ils ne soient pas redécouverts
comme des surprises :

- **la lucarne** reste imprenable. Une vraie lucarne bien frappée est un but
  **92.2 % ± 1.4** du temps contre une Legende (1440 tirs dédiés, six graines),
  pour une promesse de conception de 80 % ;
- **les casseroles** convertissent **30.2 % ± 1.0** sur l'échantillon de
  référence, tous niveaux confondus, pour une cible de « moins de 30 % ». La
  cible est donc manquée d'un cheveu, et d'un cheveu **plus petit que la
  précision de la mesure**. C'est écrit ici plutôt que corrigé : un réglage qui
  ferait descendre ce chiffre de 0.2 point ne serait pas un réglage, ce serait un
  ajustement à du bruit.

**Conséquence, et c'est le but de tout le changement : les deux camps affrontent
le même gardien.** Le réglage de difficulté n'est plus un handicap posé sur le
joueur, c'est le **tempo** de la séance : un 4-4 ouvert contre un Debutant, un
1-1 de tranchée contre une Legende, et aucun des deux n'est truqué.

La **pression** n'est plus un pourcentage caché. Un tir qu'il faut marquer pour
rester en vie est joué avec des nerfs : la dispersion de la visée est multipliée
et la frappe est mistimée bien plus souvent. Il en sort environ sept points de
conversion en moins, et surtout des ratés d'une autre **forme** (2.2 % de tirs
hors du cadre deviennent 11.7 %). La situation est **annoncée avant le tir** par
`rival_must_score()`, que `pressure_text()` met en mots et que le tableau des
scores colore. La branche est vivante : 18.2 % des tirs adverses sur une
campagne entière.

#### Le mode DUEL : les rôles ALTERNENT

`Mode.DUEL` (libellé joueur « Duel ») est une séance où le joueur change de côté
à chaque tour. Les tours **impairs** sont exactement ce qu'ils sont aujourd'hui :
le joueur tire. Les tours **pairs**, il **garde**, et c'est `TakerAi` (2.12b) qui
tire contre lui. Cinq tirs chacun, puis mort subite, mêmes règles de football
que SEANCE.

Trois conséquences, et elles sont ce qui rend le mode presque gratuit :

- **la structure du tour ne change pas.** `rival_to_kick()` reste **la seule
  réponse à « à qui le tour »** dans les quatre modes. En DUEL, le tour que
  `rival_to_kick()` annonce est simplement **joué** au lieu d'être simulé ;
- **SEANCE ne bouge pas.** Son tir adverse reste simulé par
  `simulate_rival_shot()`, avec les mêmes graines, le même ordre de tirages et
  donc les mêmes tables mesurées ci dessus. Le seul changement dans son chemin
  est que le choix du penalty vient maintenant de `TakerAi.choose` au lieu d'un
  bloc privé, et 2.12b explique pourquoi c'est le même choix au tirage près ;
- **une seule ligne du tableau grandit par tour**, comme aujourd'hui : un tour
  gardé remplit `rival_scores` et rien d'autre, par `take_rival_kick_played()`.
  Personne d'autre n'ajoute jamais dans un tableau de scores, et c'est la règle
  qui a coûté cher une fois (voir plus haut).

**Le niveau vaut pour les deux moitiés.** `Game.keeper_level` décide de la
difficulté du gardien que le joueur affronte **et** du corps qu'il pilote quand
c'est lui le gardien (2.12a). Le joueur s'impose donc ce qu'il exige de l'autre,
et un duel contre une Legende est un duel où **les deux** gardiens sont des
Legende. C'est aussi le niveau du **tireur** adverse d'un duel, que
`duel_taker_plan` passe à `TakerAi.choose` : un seul curseur de difficulté, et il
vaut pour les quatre rôles de la séance.

#### Les tables ci dessus n'ont PAS été remesurées, et voici pourquoi

Le déménagement du tireur vers `TakerAi` (2.12b) ne touche rien de ce que les
quatre lignes mesurent, et ce n'est pas une promesse : `tests/test_match_state.gd`
garde **la copie verbatim de l'ancien `_rival_plan`** et vérifie, graine par
graine, que `TakerAi.choose(graine, SEANCE_LEVEL, pression, 0.0)` rend le même
plan **au tirage près**, puis que `TakerAi.dance_phase` rend le tirage qui suit,
à la position exacte où l'ancien code le prenait. Le reste du chemin est
inchangé : `TakerAi.strike` est l'appel `ShotModel.resolve` qui était là,
`TakerAi.cues` est l'appel `ShotModel.tell_cues` qui était là, et la boucle de vol
n'a pas bougé d'une ligne. **Si ce test tombe un jour, ce sont ces tables qui sont
fausses**, et il faut les refaire à 4000 tirs par niveau comme décrit plus haut,
pas ajuster le test.

```gdscript
signal phase_changed(previous: int, current: int)
signal shot_recorded(record: Dictionary)
signal series_changed()
signal match_finished(player_won: bool)

## DUEL and GARDIEN are APPENDED, never inserted: the shipped values are persisted
## in user://settings.cfg and read back by number.
## GARDIEN is to DUEL what ENTRAINEMENT is to SEANCE: the same round over and over
## with nothing riding on it. The player keeps EVERY round, the CPU takes every
## kick, and there is no series - only a tally of how many were stopped.
enum Mode { SEANCE, ENTRAINEMENT, DEFI, DUEL, GARDIEN }
## The two keeper side phases are APPENDED for the same reason. VOL, VERDICT and
## REPLAY are REUSED by the keeper side rather than doubled: see 2.26 for what
## each one is entered on and left on, and for why the dive is not a phase.
enum Phase { ACCUEIL, PLACEMENT, VISEE, COURSE, VOL, VERDICT, REPLAY, FIN,
	PLACEMENT_GARDIEN, LECTURE }
## Which side of a DUEL round the player is on.
enum Turn { TIREUR, GARDIEN }
enum Verdict { BUT, ARRET, POTEAU, BARRE, DEHORS }

## Regulation shots per side before sudden death.
const REGULATION_SHOTS := 5

var mode: int
var phase: int
var round_index: int              # 0 based, counts the player's own attempts
var player_scores: Array[int]     # one Verdict per attempt, in order
var rival_scores: Array[int]      # the CPU team's attempts, same encoding
var streak: int                   # consecutive goals, for the Defi mode
var best_streak: int
var defi_points: int

## French label of a verdict, for the HUD ("BUT !", "Arrêt du gardien", ...).
## Player facing, therefore accented. Only the console output stays ASCII.
static func verdict_label(verdict: int) -> String
## True when the verdict put the ball in the net, rebound included.
static func is_goal(verdict: int) -> bool

func start_match(new_mode: int) -> void
func set_phase(new_phase: int) -> void
## Records the player's attempt and advances the series. `record` carries at
## least {"verdict": int, "speed": float, "point": Vector3, "curve": float}.
## Takes the PLAYER'S kick and nothing else: the rival goes through
## take_rival_kick(), as his own beat of the presentation.
func record_shot(record: Dictionary) -> void
## Number of goals scored by each side so far.
func player_goals() -> int
func rival_goals() -> int

## True when the rival still owes a kick right now: a shootout in progress, the
## player one kick ahead, and a tie that is still alive. The single answer to
## "whose turn is it", and what the scoreboard draws.
## ALWAYS true in GARDIEN, where he is the only one who kicks: the player takes
## none of his own, so the "one kick ahead" test can never come true and the
## answer has to be given before it is asked.
func rival_to_kick() -> bool
## Number of penalties the player STOPPED, out of rival_scores. Every round he
## kept is a round the CPU took, in both keeper side modes, so this reads the
## same row in a duel and in a training session.
func keeper_saves() -> int
## True when that next rival kick has to be scored to keep the tie alive. Read by
## the HUD and the scoreboard, so the nerves the simulation applies to the kick
## are announced BEFORE it rather than hidden inside a goal chance.
func rival_must_score() -> bool
## Takes the rival's turn, ONCE, and returns the Verdict. Returns -1 when he owes
## no kick, which is the rule that matters: nobody takes a penalty that cannot
## change the result, so a decided series never plays out a dead round.
## Appends to rival_scores, emits series_changed, then match_finished when this
## kick settled it. The caller never appends anything itself.
## In DUEL this is not the path: the kick is PLAYED, see below.
func take_rival_kick() -> int

## --- Mode DUEL (voir plus haut) ----------------------------------------------

## True when the player is the goalkeeper for the beat about to be played. It is
## the mode and `rival_to_kick()` and NOTHING else, so "whose turn is it" still
## has exactly one answer, DUEL cannot drift out of step with SEANCE, and GARDIEN
## cannot drift out of step with DUEL. Always true in GARDIEN.
func player_keeps() -> bool
## True when the rival's turn is PLAYED OUT by the game rather than simulated
## behind a banner: both keeper side modes. The single answer to "is there a rival
## beat to watch", so Main never lists the modes itself.
func rival_kick_is_played() -> bool
## Which side of the duel the player is on right now, a Turn. Always
## Turn.TIREUR outside DUEL.
func turn() -> int
## The rival's turn again, but with a verdict the GAME just played out instead of
## one this file simulated: the DUEL path, where a real TakerAi penalty was
## defended by a real player. Same bookkeeping, same signals and the same
## "he owes no kick" rule as take_rival_kick(), and it returns the Verdict it
## recorded or -1 when no kick was owed and nothing was recorded.
## `verdict` is a Verdict. Anything else is refused with -1 rather than stored.
func take_rival_kick_played(verdict: int) -> int
## French label of a mode, for the menu: "Séance", "Entraînement", "Défi",
## "Duel". Player facing, therefore accented.
static func mode_label(mode: int) -> String

## Seeded simulation of one CPU attempt against the player's own keeper: a real
## penalty through TakerAi, ShotModel, Aero, Field and KeeperBrain at
## Game.keeper_level. Returns a Verdict. Deterministic for a given round and seed.
## Pure with respect to the series: it reads the score and the settings, it writes
## nothing. The SEANCE path, unchanged in behaviour by the arrival of DUEL: the
## penalty it simulates is now chosen by TakerAi.choose at TakerAi.SEANCE_LEVEL
## with the keeper in the middle of his line, which is the same choice, seed for
## seed, that this file used to make itself (see 2.12b). The keeper's own pre
## strike shuffle used to be the NEXT draw off that stream: it is now
## `TakerAi.dance_phase`, which is the same draw at the same position, and that
## is the whole reason that function is public.
func simulate_rival_shot(rng_seed: int) -> int
## The CPU penalty of the round the player is about to KEEP, so the orchestrator
## can hand the same plan to the taker's body, to the ball and to the tells. It is
## `TakerAi.choose` with this series' seed, the difficulty level and the pressure
## flag already worked out, and it is the only place that decides them. Pure: it
## writes nothing, and calling it twice for the same round gives the same plan.
## The level is `Game.keeper_level`, the same setting the keeper is built from:
## both ends of a duel are the same rung, see "Le niveau vaut pour les deux
## moitiés" above.
func duel_taker_plan(keeper_x: float) -> Dictionary
## The seed that plan was drawn with. The taker's feints, his run up length and
## the tells the player reads all have to come off the SAME number, or the run up
## on screen would belong to a different penalty from the one that arrives.
## Stable for a round, and it is what duel_taker_plan itself uses.
func duel_taker_seed() -> int
## True when neither side can catch up any more.
func is_decided() -> bool
## Free text of the situation, in French: "Marquez pour gagner", "Tir décisif",
## "Mort subite", "Égalité"... Player facing, therefore accented.
## The rival's turn comes FIRST when he owes a kick ("Au tour de l'adversaire",
## "L'adversaire doit marquer", "L'adversaire tire pour gagner"): it is the
## situation the player is watching, and saying it out loud is what makes the
## pressure the simulation applies visible instead of arithmetic nobody can see.
## In DUEL that same turn is the player's own, so the same situations are said
## from his side of it ("À vous d'arrêter", "Arrêtez pour rester en vie",
## "Arrêtez pour gagner"). The signature does not change and neither does the
## rule it reads: only the person the sentence is addressed to.
func pressure_text() -> String
## Everything the scoreboard needs, in one dictionary. Carries, among the rest,
## "rival_to_kick" and "rival_must_score", both bool, and for DUEL "player_keeps"
## (bool), "turn" (a Turn) and "mode" (a Mode).
func summary() -> Dictionary
func reset() -> void
```

---

### 2.10 `src/ball/aerodynamics.gd` - `class_name Aero`

Le coeur du jeu, et le module le plus testé. **Aucune dépendance, tout statique.**
Un ballon de football n'a pas une trajectoire parabolique : la traînée le freine
d'un tiers sur 11 mètres, et l'effet Magnus le fait tourner de plusieurs dizaines
de centimètres. C'est ce qui rend le tir intéressant, donc c'est modélisé pour de
vrai.

Convention de l'effet : `spin` est un **vecteur de vitesse angulaire en rad/s**,
dirigé selon la règle de la main droite. Un tir avec `spin = (0, +w, 0)` sur un
ballon partant vers -Z est dévié vers -X (le classique enroulé du droitier).

```gdscript
class_name Aero
extends RefCounted

const GRAVITY      := 9.81
const AIR_DENSITY  := 1.225
const BALL_MASS    := 0.430
const BALL_RADIUS  := 0.11
const BALL_AREA    := 0.0380         # PI * r * r
const SPIN_DECAY   := 0.045          # fraction of spin lost per second

## Drag crisis: a football's drag coefficient collapses as the boundary layer
## goes turbulent. Below CRISIS_LOW it is laminar, above CRISIS_HIGH turbulent.
const CD_LAMINAR   := 0.47
const CD_TURBULENT := 0.20
const CRISIS_LOW   := 9.0            # m/s
const CRISIS_HIGH  := 19.0           # m/s

## Fastest spin the model stays sane for, rad/s.
const MAX_SPIN     := 220.0

## Drag coefficient at this speed. Spin re energises the boundary layer and
## pushes the crisis back up, so a heavily spun ball keeps a higher Cd: that is
## exactly why a knuckleball (no spin, high speed) flies flat and a curled ball
## slows down.
static func drag_coefficient(speed: float, spin_rate: float) -> float

## Lift coefficient from the spin parameter S = r * omega / v. Saturates around
## S = 0.3, which is where real measurements flatten out.
static func lift_coefficient(speed: float, spin_rate: float) -> float

## Total acceleration in m/s2: gravity plus drag plus Magnus, relative to the
## air, so `wind` shifts the whole aerodynamic frame.
static func acceleration(velocity: Vector3, spin: Vector3, wind: Vector3) -> Vector3

## One RK4 step. Returns [Vector3 position, Vector3 velocity], in that order.
## RK4 and not Euler: at 30 m/s a semi implicit Euler step drifts several
## centimetres over a penalty, which is the difference between a post and a goal.
static func integrate(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, delta: float) -> Array

## Spin bleeds off through skin friction.
static func decay_spin(spin: Vector3, delta: float) -> Vector3

## Samples a whole flight, ignoring every collision. Used by the HUD preview and
## by the keeper's mental model, never by the real ball.
static func sample_flight(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, delta: float, steps: int) -> PackedVector3Array

## Where and when the flight crosses the plane z = plane_z travelling towards -Z.
## Returns {"crossed": bool, "time": float, "point": Vector3, "velocity": Vector3}
static func cross_plane(position: Vector3, velocity: Vector3, spin: Vector3, wind: Vector3, plane_z: float, max_time: float) -> Dictionary

## Solves for the launch velocity of magnitude `speed` that carries the ball from
## `from` to `target`, spin and drag included. Shooting method: it fires, sees
## where it lands on the target's plane, corrects the aim, and repeats. Returns
## ZERO when no solution exists (target out of range for that speed).
static func aim_velocity(from: Vector3, target: Vector3, spin: Vector3, wind: Vector3, speed: float) -> Vector3

## Reflects a velocity off a surface, losing energy and converting part of the
## tangential slip into spin. Returns [Vector3 velocity, Vector3 spin].
## `restitution` 0.75 for the frame, 0.45 for turf, 0.12 for the net.
static func bounce(velocity: Vector3, spin: Vector3, normal: Vector3, restitution: float, friction: float) -> Array
```

---

### 2.11 `src/ball/shot_model.gd` - `class_name ShotModel`

Traduit les intentions du joueur (visée, puissance, effet, qualité de frappe) en
une vitesse et un effet de départ. **Pur et statique**, donc testable sans jeu.

Principe de conception, à respecter : **le réticule montre où le ballon irait
sans effet.** L'effet le fait dévier de cette cible. Le joueur voit la courbe
prévue en direct dans le HUD, et apprend à s'en servir.

```gdscript
class_name ShotModel
extends RefCounted

const MIN_SPEED := 14.0
const MAX_SPEED := 34.0
## Half width of the clean contact window on the power bar.
const SWEET_WIDTH := 0.11

## World point aimed at, from the normalized reticle. `aim.x` -1..1 spans the
## mouth plus a margin, `aim.y` 0..1 spans from the ground to the bar plus a
## margin. Values outside those bands are legal: that is how you shoot wide.
static func aim_point(aim: Vector2) -> Vector3

## Strike speed for a charged power in [0, 1]. Not linear: the top of the bar
## buys less speed than the middle, so maximum power is a real trade off.
static func speed_for_power(power: float) -> float

## Spin from the player's inputs. `side` -1..1 is the curl, `lift` -1..1 is
## backspin (positive, floats the ball) to topspin (negative, dips it).
static func spin_vector(side: float, lift: float, power: float) -> Vector3

## Contact quality in [0, 1] from where the bar was released. 1.0 is a clean
## strike inside the sweet window, and it falls off outside it.
static func contact_quality(release: float, sweet_centre: float) -> float

## Half angle of the error cone, in radians. A miscue at full power sprays much
## further than a miscue on a placed shot.
static func error_angle(quality: float, power: float) -> float

## Full resolution of a strike. Deterministic for a given rng_seed.
## Returns {
##   "velocity": Vector3, "spin": Vector3, "quality": float,
##   "speed": float, "target": Vector3, "miscue": bool
## }
static func resolve(aim: Vector2, power: float, side: float, lift: float, release: float, sweet_centre: float, rng_seed: int) -> Dictionary

## The cue values the keeper is allowed to read from a strike being prepared.
## Deliberately lossy: this is what leaks through body language, not the truth.
## Returns the dictionary described in 2.12 read_cues.
static func tell_cues(aim: Vector2, power: float, side: float, run_angle: float, feints: int, level: int) -> Dictionary
```

---

### 2.12 `src/keeper/keeper_brain.gd` - `class_name KeeperBrain`

Le gardien piloté par l'application, en **logique pure**. Aucun noeud, aucune
dépendance hors `Field` et `Aero`. Tout est déterministe pour une graine donnée,
ce qui rend le module testable et le replay fidèle.

Le gardien ne triche pas. Il ne connaît que ce qu'il voit : le langage corporel
avant la frappe, puis les premières fractions de seconde du vol. Un penalty à
30 m/s met **0.4 s** à arriver, et le temps de réaction humain est de 0.2 s :
c'est pour cela qu'un bon gardien **parie** avant la frappe, et qu'un tir bien
placé est imparable. Le niveau ne change jamais la physique, seulement la qualité
de la lecture, la vitesse du plongeon et l'allonge.

#### L'échelle athlétique est étroite en bas et large en haut

C'est la seule asymétrie des quatre tables de niveau et elle est voulue. Un
Debutant plonge presque aussi vite et s'allonge presque autant qu'une Legende :
ce qui le bat est qu'il ne **lit** pas la course d'élan, donc il part du mauvais
côté, à la mauvaise hauteur, au mauvais moment. Creuser l'écart athlétique en bas
donnerait un débutant qui a l'air **cassé** au lieu d'un débutant qui a l'air
**trompé**.

En haut, l'inverse s'impose. Legende est le niveau sur lequel toute l'échelle est
calée et le seul à porter une cible à deux bornes (62 à 68 % de penalties propres
arrêtés sur l'échantillon de référence). Mesuré sérieusement (2016 penalties
propres par niveau, six graines indépendantes de `tests/balance_probe.gd`), il
était à **61.2 % ± 2.2**, un cheveu sous son propre plancher, et la simulation
adverse de 2.9, qui est un tout autre code, disait **61.6 % ± 1.5** du même
gardien. Ce n'était donc pas une régression récente : ce niveau vivait sous sa
cible depuis longtemps, et personne ne l'avait vu parce que chaque relevé était
tiré d'une seule graine et portait cinq points de bruit.

Le levier perceptif ne pouvait pas le corriger : `read_skill` valait déjà 0.99
sur 1.0, et tout le chemin restant jusqu'au lecteur parfait vaut environ un point
de taux d'arrêt. Les derniers points viennent donc du corps, **une fois, en haut
seulement** : l'allonge passe de 1.35 à 1.44 m et la vitesse de plongeon de 5.35
à 5.60 m/s, ce qui fait du dernier barreau 13 cm et 0.51 m/s là où les trois
autres valent 4 à 5 cm et 0.27 m/s. Sensibilité **mesurée** avant de choisir ces
valeurs, pas devinée : un centimètre d'allonge vaut environ **0.25 point** de
taux d'arrêt et coûte environ **0.7 point** de la promesse de la lucarne, ce qui
est précisément pourquoi l'allonge ne porte pas le changement toute seule.

Résultat, remesuré exactement comme le chiffre d'avant, six graines, 2016
penalties propres : **63.6 % ± 2.1**, dans la cible. Les trois autres niveaux
sont ressortis **identiques, arrêt pour arrêt**, sur les mêmes graines : c'est la
preuve que le changement n'a touché que le barreau du haut, et c'est aussi
pourquoi les graines de cette sonde sont fixes. Le tableau complet est en 2.9.

**La promesse tient.** Une vraie lucarne bien frappée (|x| entre 2.80 et 3.30 m,
y entre 1.85 et 2.25 m, puissance au dessus de 0.86, contact propre) reste un but
contre une Legende **92.2 % ± 1.4** du temps sur la sonde en jeu et **91.2 % ±
1.6** sur la simulation adverse, pour une promesse de conception de 80 %. Elle
valait 97.8 % avant ce réglage : le coût est réel, il est chiffré, et il laisse
encore onze points de marge sur la promesse.

**LE PLONGEON EST CONTINU.** `dive_pose` prend un **point du monde**, pas un
couple d'énumérations. C'est la seule signature de ce document qui ait changé
depuis l'écriture initiale, et voici pourquoi, parce que la raison est le coeur
de la difficulté du jeu.

L'ancienne forme, `dive_pose(side: int, height: int, t: float, level: int)`,
quantifiait la parade en trois côtés par trois hauteurs. Deux hauteurs voisines
sont séparées de **0.83 m** au ballon, contre un gant de 0.16 m et un avant bras
de 0.145 m. Un gardien qui lisait la hauteur **à une main près** plongeait donc
dans la mauvaise bande et manquait le ballon **aussi proprement** qu'un gardien
qui l'avait lue à l'envers. Aucune vitesse de plongeon, aucune allonge ne rattrape
un bras qui est simplement dans la mauvaise case. La conséquence mesurée était un
taux d'arrêt bloqué autour de la moitié de la cible à tous les niveaux.

Trois propriétés découlent de la forme continue, et elles sont **contractuelles** :

1. **une lecture presque juste est une parade presque faite.** La pose est une
   fonction continue de la cible : 5 cm de ballon déplacent un membre de moins de
   22 cm, et `tests/test_keeper_brain.gd` le vérifie en balayant toute la lucarne.
2. **il s'arrête SUR le ballon.** Le déplacement du bassin est le **minimum** de
   ce que le plongeon a couvert et de ce que la cible exige, donc un gardien qui a
   correctement lu un ballon à un mètre de lui y arrive et **y reste**. Avant, il
   continuait et finissait deux mètres plus loin, ce qui est exactement pourquoi
   un penalty mou et mal frappé battait tous les niveaux de la même façon.
3. **l'intuition d'avant frappe est continue elle aussi.** `read_cues` rend une
   clé `target`, point de la ligne de but, et c'est elle que `choose_dive` vise.
   `side` et `height` survivent parce que le corps, le son et le replay parlent
   en ces termes, mais **plus rien dans la pose n'est quantifié par eux**.

```gdscript
class_name KeeperBrain
extends RefCounted

enum Level { DEBUTANT = 0, CONFIRME = 1, PRO = 2, LEGENDE = 3 }

const LEVEL_NAMES: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]

## Dive directions and dive heights. They no longer shape the pose: they are the
## coarse READING of a dive, for the body, the crowd, the audio and the replay.
const SIDE_LEFT   := -1     # towards -X
const SIDE_CENTRE := 0
const SIDE_RIGHT  := 1      # towards +X
const HEIGHT_LOW  := 0
const HEIGHT_MID  := 1
const HEIGHT_HIGH := 2

## Radius within which a glove or a boot stops the ball, metres.
const GLOVE_RADIUS := 0.16
const BOOT_RADIUS  := 0.13
const BODY_RADIUS  := 0.26

## The rest of the save envelope. A real keeper stops the ball with a trailing
## leg, a forearm and a spread trunk, not with two glove points, so the contact
## test also sweeps the OUTER part of each limb and a trunk capsule standing on
## the pelvis. All radii already fold in the 0.11 m of ball.
const FOREARM_RADIUS := 0.145
const SHIN_RADIUS    := 0.150
const TRUNK_RADIUS   := 0.310
## Length of the trunk capsule above the pelvis, metres: pelvis to the crown, so
## it includes the head, which also stops a ball.
const TRUNK_LENGTH   := 0.72
## Fraction of the way from the body centre to a glove or a boot at which the
## blocking segment starts. Closer in than that it is a shoulder or a hip, which
## is already inside the trunk capsule.
const LIMB_SPAN      := 0.38

## Seconds between seeing something and starting to move.
static func reaction_time(level: int) -> float
## Peak horizontal dive speed, m/s.
static func dive_speed(level: int) -> float
## Glove reach from the standing centre at full extension, metres.
static func reach(level: int) -> float
## Seconds a dive of this level needs before the leading glove is at full stretch.
static func extension_time(level: int) -> float
## Seconds this level needs to have a glove ON `target`, pushing off from a body
## centre standing at `from_x` on the goal line. The longer of the ground travel
## and the arm swing, both taken from the very curves dive_pose uses. This is what
## `Keeper` plans its LAST RESPONSIBLE MOMENT against, and it is why a slow scuffed
## penalty is now a different problem from a hard one: it lets the keeper wait
## instead of throwing himself down a quarter of a second before the ball arrives.
static func dive_time_needed(target: Vector3, from_x: float, level: int) -> float
## Odds the keeper commits before the strike rather than waiting, when the body
## language he just read was unmistakable. A murkier read scales this down (see
## read_cues): committing on a tell he never actually saw is not gambling, it is
## guessing, and it leaves him on the turf while the ball goes the other way.
static func gamble_chance(level: int) -> float
## How much of the shooter's real aim leaks into the cues, 0..1.
static func read_skill(level: int) -> float

## Pre strike read of the shooter's body language.
## `cues` carries: "run_angle" (-1..1), "approach_speed" (0..1),
## "plant_offset" (-1..1), "hip_yaw" (radians), "feints" (int),
## "aim_hint" (-1..1, already degraded by read_skill), "power_hint" (0..1),
## "lift_hint" (-1..1, already degraded by read_skill: -1 means the body language
## says "along the turf", +1 means "up under the bar").
## Returns {"side": int, "height": int, "target": Vector3, "confidence": float,
##          "commit": bool, "commit_time": float}
## `target` is the SAME read as a continuous point on the goal line, and it is what
## choose_dive aims at; `side` and `height` are only its coarse reading, kept for
## the body, the audio and the replay. `commit_time` is negative when the keeper
## dives BEFORE the strike, measured in seconds relative to contact.
static func read_cues(cues: Dictionary, level: int, rng_seed: int) -> Dictionary

## The keeper's running estimate of where the ball will cross the line, from the
## part of the flight seen so far. `observed` is the seconds of flight watched.
## The estimate is noisy early and converges: that is the whole tension of the
## module. Returns {"point": Vector3, "time": float, "error": float}
static func estimate_cross(ball_position: Vector3, ball_velocity: Vector3, spin: Vector3, level: int, observed: float, rng_seed: int) -> Dictionary

## Picks the dive. Called once, the frame the keeper commits.
## Returns {"side": int, "height": int, "target": Vector3, "gambled": bool}
## `target` is the point the dive is built from and the only one of the four that
## changes the pose. It is the continuous `target` of the pre strike read, blended
## towards the flight estimate by how much that estimate is worth.
## `gambled` here means "decided before contact", i.e. `elapsed <= 0`, and it is
## what makes the pre strike hunch override an estimate the keeper cannot yet have.
## `Keeper` reports its OWN gamble flag on `dive_started`, taken from whether the
## run up read committed, because since the last responsible moment landed it
## pushes off during the flight even when the decision was made before it.
static func choose_dive(estimate: Dictionary, guess: Dictionary, level: int, elapsed: float) -> Dictionary

## Keeper limb positions `t` seconds into a dive at `target`, in world space.
## `target` is a CONTINUOUS point on the goal line, and every part of the pose is
## read off it: how far the body travels, how high the pelvis goes, how much of an
## arc it describes, whether the move is a full layout or a spread block, and where
## the leading glove points. See the three contractual properties above.
## Returns {"centre": Vector3, "glove_left": Vector3, "glove_right": Vector3,
##          "boot_left": Vector3, "boot_right": Vector3,
##          "lean": float, "airborne": float}
## `lean` is the body roll in radians, `airborne` is 0 on the ground and 1 at the
## peak of the dive. At t = 0 the pose is always the standing home pose, whatever
## target is asked for, which is what lets a caller blend in and out of a dive.
static func dive_pose(target: Vector3, t: float, level: int) -> Dictionary

## Shortest distance between the ball's path over one physics step and the
## nearest keeper limb, minus that limb's radius. Negative means contact.
static func save_distance(pose: Dictionary, ball_from: Vector3, ball_to: Vector3) -> float

## Contact test plus what was hit.
## Returns {"saved": bool, "limb": String, "point": Vector3, "normal": Vector3}
## `limb` is one of "glove_left", "glove_right", "boot_left", "boot_right",
## "centre", or "" when nothing was touched.
static func try_save(pose: Dictionary, ball_from: Vector3, ball_to: Vector3) -> Dictionary

## Catching, as opposed to merely stopping. See "Une parade a deux issues" below.
## Up to CATCH_SPEED_EASY the whole glove holds the ball, from there the window
## closes linearly onto the middle of the palm, and past CATCH_SPEED_MAX nothing
## is held at all. A speed that is not a finite positive number shuts the window.
const CATCH_SPEED_EASY := 20.0
const CATCH_SPEED_MAX  := 30.0
## Fraction of GLOVE_RADIUS still catchable at CATCH_SPEED_MAX.
const CATCH_PALM_MIN   := 0.55

## Radius of the palm window at this impact speed, metres. Never negative, never
## rises with speed.
static func catch_window(impact_speed: float) -> float

## Was that save a CLEAN CATCH, or only a parry? `save` is a try_save dictionary
## and `impact_speed` the ball speed at contact, in m/s.
## Returns {"catch": bool, "grip": float, "hand": String, "offset": float}
## `hand` is the glove that holds it, or "" for a parry. `grip` is 1 at the dead
## centre of the palm and 0 at the edge of the window.
static func catch_quality(pose: Dictionary, save: Dictionary, impact_speed: float) -> Dictionary

## Where the keeper shuffles to on the line before the strike, to put the shooter
## off. Returns an x offset in metres, bounded to +/- 0.9.
static func line_dance(elapsed: float, level: int, rng_seed: int) -> float
```

#### Une parade a deux issues

Un arrêt n'est pas un résultat, c'en est **deux**, et le joueur voit la
différence : le ballon est soit **capté**, soit **repoussé**. `catch_quality`
tranche à partir du contact lui même, jamais d'un tirage, et c'est ce qui rend la
différence lisible : on **voit** pourquoi la mine dans la lucarne n'a été que
déviée alors que le ballon placé a été gobé.

Trois conditions, toutes déjà mesurées par `try_save` :

1. **c'est une main.** `limb` nomme le gant même pour un blocage de l'avant bras
   (le segment d'avant bras est crédité au gant auquel il pend), donc le point de
   contact est **remesuré contre le gant lui même** : au delà de `GLOVE_RADIUS`
   c'est un bras, et un bras repousse. Un pied, un tibia ou le tronc est un
   blocage par définition, jamais une prise.
2. **c'est dans la paume**, et la taille de la paume dépend de la vitesse :
   `catch_window`.
3. **c'est assez lent pour être tenu.**

Mesuré sur 900 penalties tirés au hasard par niveau : entre **21 % et 29 % des
arrêts** sont des prises de balle, le reste étant repoussé. Environ 35 à 40 % des
arrêts sont un contact de main, et la fenêtre de paume en garde les deux tiers.
Ce sont des **mesures**, pas des consignes : si tu touches à `dive_pose`, à
l'enveloppe de parade ou aux constantes ci dessus, remesure.

Le module ne fait que **rendre le verdict physique** ; qui tient le ballon et où
il finit sont l'affaire de 2.18 et 2.19.

---

### 2.12a `src/keeper/keeper_input.gd` - `class_name KeeperInput`

Le gardien quand c'est **le joueur** qui le tient, en logique pure. Aucun noeud,
aucune dépendance hors `Field` et `KeeperBrain`. C'est le pendant de `ShotModel`
pour l'autre camp du mode DUEL (2.9) : il traduit une visée à la souris, un
instant d'engagement et une position sur la ligne en un plongeon, et il répond à
la seule question que le joueur se pose pendant la course d'élan : **si je pars
maintenant, qu'est ce que je couvre encore ?**

#### L'arithmétique est celle du gardien de l'application, et elle est cruelle

Un penalty met **0.42 s** à arriver, un réflexe humain **0.2 s**, et un plongeon
au poteau **0.6 s**. Les trois chiffres ne rentrent pas les uns dans les autres,
et c'est le sujet du mode : **on ne peut pas attendre de savoir**. Le joueur doit
parier tôt, sur une lecture incomplète, exactement comme `KeeperBrain.read_cues`
le fait depuis toujours. Plus il s'engage tôt, plus il couvre ; plus il attend,
plus il en sait et moins il en couvre. Ce marché est déjà l'âme du jeu, et ce
module existe pour que le joueur le sente **de l'autre côté**.

Rien de neuf n'est modélisé pour cela. **L'enveloppe est une conséquence de
`KeeperBrain.dive_time_needed`**, donc de `reach`, `dive_speed` et
`extension_time` du niveau choisi : les deux camps du duel plongent avec le même
corps, et une enveloppe qui divergerait de ces courbes serait un mensonge dessiné
à l'écran.

#### L'horloge, et ce qui est connu à chaque instant

`t` est en secondes **relatives à la frappe**, négatif pendant la course d'élan.
C'est l'horloge de `Keeper.pose_log` et celle de `read_cues.commit_time`, pas une
troisième. Un engagement à `t = -0.18` est un gardien qui part deux dixièmes
avant le contact, et il est parfaitement légal.

`arrival` est l'instant, sur la même horloge, où le ballon franchira la ligne.
Avant la frappe **personne ne le connaît**, et l'appelant passe donc
`NOMINAL_FLIGHT`. Après la frappe le joueur **voit** le ballon, donc lui passer le
temps de vol restant réel est honnête : c'est ce qui fait rétrécir l'enveloppe
beaucoup plus vite sur une frappe sèche que sur une casserole, ce qui est
précisément la différence que le joueur doit apprendre à lire.

#### Ce qui n'entre PAS dans le budget, et pourquoi

`KeeperBrain.reaction_time` **n'est pas retranché** du temps disponible. Le
cerveau se l'applique parce qu'il décide à un instant où le corps ne bouge pas
encore ; le joueur, lui, a déjà réagi quand il appuie, et il a payé son dixième de
seconde avec ses propres nerfs. L'ajouter ici reviendrait à le lui facturer deux
fois. C'est écrit parce que la prochaine personne qui lira ce fichier aura envie
de l'ajouter au nom de la symétrie, et que ce serait la mauvaise symétrie.

```gdscript
class_name KeeperInput
extends RefCounted

## Seconds a penalty is assumed to take from contact to the goal line for as long
## as nobody can know better, which is the whole of the run up. Not invented: it
## is what the project's own model gives for a strike at TakerAi.POWER_MEAN over
## the eleven metres.
const NOMINAL_FLIGHT := 0.42

## How far along his line the player may shuffle, metres either side of the
## middle. The SAME bound KeeperBrain.line_dance lives under, so the AI keeper and
## the player keeper occupy one strip of turf and not two.
const LINE_LIMIT := 0.9
## Metres per second that shuffle travels at.
const LINE_SPEED := 1.35

## World point on the goal plane a normalized reticle asks for. `aim.x` -1..1 and
## `aim.y` 0..1 span the same bands ShotModel.aim_point reads, so the two ends of
## a duel aim in one language.
## Unlike the taker, the keeper is CLAMPED inside the frame: a dive aimed over the
## bar is not a decision, it is a lost input.
static func dive_target(aim: Vector2) -> Vector3

## Moves the reticle by one frame of mouse travel and clamps it back into the
## band above. `sensitivity` is Game.mouse_sensitivity.
static func move_aim(aim: Vector2, mouse_delta: Vector2, sensitivity: float) -> Vector2

## Seconds of dive left to a keeper who pushes off at `t` for a ball that reaches
## the line at `arrival`. Never negative.
static func time_available(t: float, arrival: float) -> float

## Can a keeper standing at `line_x` still have a glove ON `target` if he pushes
## off now? This is exactly
## `KeeperBrain.dive_time_needed(target, line_x, level) <= time_available(t, arrival)`,
## and it is the ONE rule everything else in this module is drawn from.
static func reachable(target: Vector3, line_x: float, t: float, arrival: float, level: int) -> bool

## Seconds to spare on that dive. Positive means reachable with room, negative is
## how late the keeper would be. The HUD colours the dive reticle with it.
static func margin(target: Vector3, line_x: float, t: float, arrival: float, level: int) -> float

## The outline of everything still reachable, as a CLOSED ring of `samples` points
## on the goal plane, for the HUD to stroke. Found by bisecting `margin` along
## rays out of the keeper, so the drawn envelope IS the rule and cannot drift away
## from it. Empty when nothing is reachable any more.
static func reach_outline(line_x: float, t: float, arrival: float, level: int, samples: int = 48) -> PackedVector3Array

## Fraction of the goal mouth still reachable, 0..1. One number, so the HUD can
## shrink a ring with it and the tests can assert the property that matters: it
## FALLS as `t` rises, at every level and from every line position.
static func coverage(line_x: float, t: float, arrival: float, level: int) -> float

## One frame of line dance. `input` is -1..1 from the keyboard or the mouse,
## travelling at LINE_SPEED and bounded to LINE_LIMIT. Returns the new x.
static func line_step(line_x: float, input: float, delta: float) -> float

## The dive the player just launched. Called ONCE, the frame he commits.
## Returns {"target": Vector3, "side": int, "height": int, "committed_at": float,
##          "reachable": bool, "coverage": float, "margin": float}
## `target` is the continuous point the pose is built from and the only one of the
## three that changes it; `side` and `height` are its coarse reading, for the
## body, the crowd, the audio and the replay, exactly as KeeperBrain.choose_dive
## reports them. The dictionary is shaped so that `Keeper` can be driven from it
## without knowing whether a brain or a human chose it.
static func commit(aim: Vector2, line_x: float, t: float, arrival: float, level: int) -> Dictionary

## Coarse reading of a continuous target, for the body and the audio. The same
## thresholds KeeperBrain reads it with, kept in one place so a dive reported by
## the two modules is reported the same way.
static func coarse_side(target: Vector3) -> int
static func coarse_height(target: Vector3) -> int

## The mouth as the envelope sees it: the rectangle of ball CENTRES whose whole
## body is still inside the frame, the same rule Field.is_inside_mouth applies.
## Public because the HUD strokes the rectangle the coverage is counted on, and
## two rectangles disagreeing by one ball radius would make the drawn ring look
## wrong at the posts.
static func mouth_half_x() -> float
static func mouth_floor_y() -> float
static func mouth_ceiling_y() -> float
```

#### Le dégradé mesuré, et la falaise qui le termine

Relevé à `arrival = NOMINAL_FLIGHT`, depuis le milieu de la ligne. Ce sont des
**mesures**, pas des consignes : si tu touches à `KeeperBrain.dive_time_needed`,
à `reach` ou à `dive_speed`, elles bougent et il faut les refaire.

| `t` | -0.42 | -0.20 | 0.00 | 0.10 | 0.21 | 0.23 |
|---|---|---|---|---|---|---|
| Debutant | 0.906 | 0.825 | 0.602 | 0.450 | 0.357 | 0.000 |
| Confirme | 0.918 | 0.871 | 0.684 | 0.462 | 0.357 | 0.000 |
| Pro | 0.942 | 0.883 | 0.684 | 0.462 | 0.357 | 0.000 |
| Legende | 0.965 | 0.918 | 0.778 | 0.474 | 0.368 | 0.000 |

Deux choses à ne pas redécouvrir comme des surprises :

- **la falaise à 0.23 s n'est pas un bug.** Le balancé du bras coûte environ
  **0.19 s** dans `dive_time_needed`, même pour un ballon suspendu devant la
  poitrine. Un gardien qui n'est pas parti à cet instant là ne sauve plus rien, et
  **le gardien de l'application vit sous exactement la même échéance** : c'est son
  « dernier moment responsable ». L'anneau disparaît d'un coup parce que le
  plongeon disparaît d'un coup ;
- **les lucarnes basses ne sont pas des lucarnes.** Un ballon au ras du sol est
  une parade franchement plus facile (l'échelle de déplacement de `KeeperBrain`
  vaut 1.06 en bas contre 0.42 sous la barre). La promesse de la règle d'équité 2
  porte sur les **lucarnes hautes**, et c'est ce que la suite vérifie.

Le maximum relevé de `coverage` sur toute la bande légale, tous niveaux et toutes
positions de ligne confondus, est **0.965**. C'est ce qui tient la règle 2, et ce
sont les quatre coins hauts qui le tiennent.

#### Les règles d'équité, et elles ne se négocient pas

Elles sont le miroir de celles sous lesquelles vit le gardien de l'application, et
le mode meurt sans elles.

1. **Le joueur ne voit jamais la vérité.** Ni la visée, ni la puissance, ni
   l'effet du tireur n'entrent dans quoi que ce soit que ce module rende. Les
   indices passent par `TakerAi.tells` (2.12b) et sont **volontairement**
   dégradés. Un chemin qui laisserait fuir la cible réelle ne rendrait pas le mode
   plus facile, il le supprimerait.
2. **Une lucarne bien frappée reste imprenable.** L'enveloppe est calculée sur les
   courbes mêmes qui laissent 92 % des vraies lucarnes entrer contre une Legende
   (2.12). Elle ne doit donc jamais couvrir le but entier, à aucun instant, à
   aucun niveau : `coverage(...)` reste **strictement sous 1** pour tout
   `t >= -NOMINAL_FLIGHT`, et `tests/test_keeper_input.gd` le balaye. Les
   victoires du joueur doivent venir d'une lecture et d'un pari, jamais d'une
   couverture totale.
   La règle porte sur le budget d'avant frappe, `arrival = NOMINAL_FLIGHT` : c'est
   le seul instant où personne ne sait rien et où le joueur pourrait donc être
   tenté de tout couvrir. Après la frappe, une **casserole** qui met 0.8 s à
   arriver laisse évidemment le temps d'aller partout, et c'est honnête plutôt
   qu'un trou dans la règle : le joueur **voit** ce ballon lent, et c'est
   exactement la différence qu'il doit apprendre à lire.
   Ce qui tient la règle, ce sont les **coins hauts** : ils sont hors de portée
   depuis le milieu de la ligne à tous les niveaux et à tout instant légal, et
   surtout **les deux ne sont jamais couverts ensemble**, où que le gardien se
   place. Danser sur sa ligne achète une lucarne et vend l'autre.
3. **Les deux camps ont le même corps.** `reach`, `dive_speed`, `extension_time` et
   `dive_time_needed` viennent de `KeeperBrain` au niveau choisi, jamais d'une
   constante recopiée ici. Le niveau reste le réglage `Game.keeper_level`, et il
   vaut pour **les deux moitiés** du duel : ce que le joueur exige du gardien
   adverse, il se l'impose.
4. **Le temps de réaction n'est pas facturé** (voir ci dessus).
5. **L'enveloppe rétrécit, elle ne remonte jamais.** `coverage` est monotone
   décroissante en `t` à `arrival` fixé. C'est ce qui rend le dessin lisible : un
   cercle qui repousserait d'une image sur l'autre détruirait la seule information
   que le joueur a le temps de lire.
   C'est **gratuit par construction** et il faut le garder ainsi : `coverage`
   compte une **grille fixe** de la bouche du but plutôt que d'intégrer l'aire de
   l'anneau. La grille ne bouge pas, seul le budget de temps bouge, donc un point
   sorti de l'enveloppe n'y rentre jamais. Une version qui intégrerait le contour
   perdrait la propriété sur le bruit de la bissection.

---

### 2.12b `src/ai/taker_ai.gd` - `class_name TakerAi`

Le tireur de l'ordinateur, en **logique pure**. Aucun noeud, dépendances `Field`,
`ShotModel` et `Aero`. Tout est déterministe pour une graine donnée.

**Ce module n'invente rien : il déménage.** Le choix de penalty qu'il porte vivait
dans `src/core/match_state.gd`, sous les noms `_RIVAL_*`, `_rival_plan` et
`_rival_reticle`, et ne servait qu'à simuler le tir adverse d'une SEANCE. DUEL a
besoin du **même** tireur, cette fois joué pour de vrai contre un gardien humain.
Il n'y a donc qu'un tireur d'ordinateur dans ce jeu et il est ici ; `Shootout`
l'appelle au lieu de le refaire.

**La contrainte de ce déménagement est absolue : SEANCE ne bouge pas d'un
arrêt.** `TakerAi.choose(graine, SEANCE_LEVEL, pression, 0.0)` doit rendre
exactement le plan que `_rival_plan` rendait pour la même graine, **tirage pour
tirage**, y compris l'ORDRE dans lequel les nombres sortent du
`RandomNumberGenerator` : les quatre lignes mesurées de 2.9 sont une propriété de
cet ordre et de rien d'autre. `tests/test_taker_ai.gd` fige le plan de plusieurs
graines connues. Si ces plans changent, 2.9 est faux et doit être **remesuré**
(4000 tirs par niveau, la procédure est écrite en 2.9), pas rafistolé.

#### Le tireur a un niveau, et SEANCE en occupe un barreau

Le tireur expédié n'avait pas de niveau : il n'en avait pas besoin, personne ne le
regardait. En DUEL le joueur le **lit**, donc il lui faut une échelle, et elle est
faite de deux choses seulement, comme celle du gardien : la **qualité de la
frappe** (la dispersion de la visée) et la **qualité du mensonge** (ce qui fuit
dans le langage corporel). Un tireur fort ne frappe pas plus fort, il place mieux
et il montre moins.

`SEANCE_LEVEL` est le barreau sur lequel le tireur expédié tombe exactement :
`spread(SEANCE_LEVEL)` vaut **1.0** et `feint_count` y rend **0**, ce qui est la
définition du non changement ci dessus.

```gdscript
class_name TakerAi
extends RefCounted

enum Level { DEBUTANT = 0, CONFIRME = 1, PRO = 2, LEGENDE = 3 }
const LEVEL_NAMES: PackedStringArray = ["Debutant", "Confirme", "Pro", "Legende"]
## The rung SEANCE has always kicked at, and the one the tables of 2.9 were
## measured on. `spread` is 1.0 here and `feint_count` is 0 here, by definition.
const SEANCE_LEVEL := Level.CONFIRME

## WHERE HE SHOOTS, in metres on the goal line, and how badly he misses. One row
## is [weight, mean |x|, sigma x, mean y, sigma y], the sign of x drawn evenly so
## neither post is favoured. The sigma IS the error: there is no second fudge
## factor anywhere. Same table as balance_probe's AIM_CLUSTERS, deliberately, so
## the rate the simulation reports is comparable with the probe's.
const AIM_CLUSTERS: Array
## The reticle stops here. Past it the kick is simply wide or over, which is a
## legal and counted outcome.
const MAX_X := 4.10
const MIN_Y := 0.14
const MAX_Y := 2.90
## Pace of a CPU penalty, as a power in [0, 1] on ShotModel's own bar.
const POWER_MEAN := 0.80
const POWER_SIGMA := 0.11
const POWER_MIN := 0.45
## How often he mistimes the strike, calm and on an elimination kick.
const MISCUE_CALM := 0.10
const MISCUE_TENSE := 0.28
## What nerves multiply the aim sigmas by. See 2.9: this is the visible version
## of a hidden goal chance, and it is why it lives in a taker rather than in a
## series.
const NERVE := 1.90
## Where his clean contact window sits on the power bar. The value Main uses for
## a scripted shot, so a rival kick and a probe kick are struck by one model.
const SWEET_CENTRE := 0.72

## Inverse of ShotModel.aim_point, which is affine on each axis and therefore
## invertible in closed form. Restated rather than searched for by bisection, and
## guarded by a round trip check in tests/test_taker_ai.gd: if ShotModel ever
## remaps its reticle, that check fails instead of this module quietly aiming
## somewhere else.
const AIM_SPAN_X := 4.40      # Field.GOAL_HALF plus ShotModel's side margin
const AIM_BASE_Y := 0.11      # Field.BALL_RADIUS
const AIM_TOP_Y := 3.04       # Field.GOAL_HEIGHT plus ShotModel's top margin
static func reticle(world_x: float, world_y: float) -> Vector2

## Hard ceiling on the shading of read_keeper, metres, whatever the level says.
const MAX_SHIFT := 0.55
## How far the keeper is allowed to stray, metres. KeeperInput.LINE_LIMIT and
## KeeperBrain's own dance bound, restated because this module may not depend on
## the keeper side: it is only ever handed the number.
const KEEPER_LINE_LIMIT := 0.9

## Multiplier ON the sigmas of AIM_CLUSTERS for this level. 1.0 at SEANCE_LEVEL.
static func spread(level: int) -> float
## How much of his real intention leaks into the tells, 0..1. The MIRROR of
## KeeperBrain.read_skill: there it is the reader's talent, here the writer's
## clumsiness. A hard taker leaks less and feints more, and that is the whole of
## what makes him hard to keep against.
static func leak(level: int) -> float
## Feints thrown into the run up, at most two. Deterministic. 0 at SEANCE_LEVEL.
static func feint_count(level: int, rng_seed: int) -> int
## Seconds of run up before contact, so the keeper side has a clock to read the
## tells against. Longer at a low level: an amateur telegraphs by dawdling.
static func run_up_time(level: int, rng_seed: int) -> float

## ONE CPU penalty, decided. Deterministic for `rng_seed`.
## `pressure` is the elimination kick of 2.9. `keeper_x` is where the keeper is
## standing on his line when the taker plants his foot, in metres, and it is the
## ONLY thing about the keeper this module is ever given.
## Returns {"aim": Vector2, "power": float, "side": float, "lift": float,
##          "release": float, "sweet_centre": float, "target": Vector3,
##          "shift": float, "rattle": float, "level": int, "pressure": bool}
## `target` is the world point of `aim`, published so callers stop recomputing it.
static func choose(rng_seed: int, level: int, pressure: bool, keeper_x: float) -> Dictionary

## The `elapsed` a SEANCE feeds KeeperBrain.line_dance with, drawn from the SAME
## stream and at the SAME position the shipped code drew it from: the very next
## value after the plan. It exists so the simulated kick of 2.9 keeps its measured
## tables to the save, and that is the only reason it is public. Nothing in DUEL
## uses it: there the keeper is a player and dances with his own hands.
##
## Without it the move of 2.12b would have been silently lossy. The shipped
## _rival_verdict drew the plan and then the dance from ONE generator, so a taker
## that seeded its own would have left match_state unable to reach that next
## value, the line dance of every simulated kick would have changed, and the four
## rows of 2.9 with it. Nobody would have noticed until a rebalance.
static func dance_phase(rng_seed: int, level: int, pressure: bool) -> float

## The strike itself, through ShotModel.resolve, returned unchanged: a CPU
## penalty and a player penalty are the same object everywhere downstream.
static func strike(plan: Dictionary, rng_seed: int) -> Dictionary

## What the AI KEEPER is allowed to read: ShotModel.tell_cues at the keeper's own
## level, exactly as SEANCE has always asked for it. Behaviour unchanged, moved
## here so both sides of a duel ask one module for the taker's body language.
static func cues(plan: Dictionary, keeper_level: int) -> Dictionary

## What the PLAYER keeper is allowed to read, which is a different question: the
## lossiness comes from the TAKER's level (`leak`) and never from the reader's.
## Returns the cue dictionary described in 2.12 read_cues, plus:
##   "feints" int, "run_up" float (seconds), "confidence" float 0..1
## Every hint in it is ALREADY degraded. Nothing in it is the truth, and a caller
## that needs the truth is holding the plan.
static func tells(plan: Dictionary, level: int, rng_seed: int) -> Dictionary

## The same dictionary as `tells`, but as it stands `t` seconds from contact, `t`
## negative during the run up: the cues arrive one by one as the taker gets
## closer, so a keeper who commits early has genuinely seen less. This is what the
## HUD draws frame by frame, and it is the entire reason waiting is worth
## anything at all.
static func tells_at(plan: Dictionary, level: int, rng_seed: int, t: float) -> Dictionary

## How the taker answers a keeper who has left the middle of his line. Returns
## {"shift": float, "rattle": float}: `shift` is metres of aim moved AWAY from the
## keeper, `rattle` a fraction ADDED to the strike's own error. A weak taker is
## rattled and does not shade, a strong one shades and is not rattled, which is
## what makes the line dance worth doing against one and dangerous against the
## other. `choose` already folds both in; it is exposed for the tests and the HUD.
static func read_keeper(keeper_x: float, level: int, rng_seed: int) -> Dictionary
```

#### Les règles d'équité du tireur

1. **Les indices mentent, et c'est le contrat.** `tells` ne rend jamais une
   valeur dont la cible se déduise. L'angle de course, le pied d'appui,
   l'ouverture des hanches et l'allure sont des fonctions **bruitées** du plan, et
   l'amplitude du bruit est `1 - leak(level)`. Deux tirs identiques doivent
   pouvoir se lire différemment, et un même indice doit pouvoir précéder deux
   tirs opposés.
2. **Le tireur ne voit du gardien que son x.** `read_keeper` ne prend rien
   d'autre : ni l'engagement, ni la visée du plongeon, ni le niveau du joueur.
   Autrement le duel devient un pierre feuille ciseaux où l'ordinateur joue en
   second, et il gagne toujours.
3. **Un beau penalty reste un but.** `shift` est borné et petit devant la largeur
   du but. Il déplace une **intention**, il ne cherche pas le coin opposé à tous
   les coups : un tireur qui viserait systématiquement là où le gardien n'est pas
   rendrait la danse sur la ligne toute puissante, ce qui est exactement le défaut
   inverse de celui qu'on corrige.
4. **La graine décide tout.** Aucun `randf()` global, aucune horloge, aucun état
   statique entre deux tirs. Deux exécutions de la même graine rendent le même
   penalty, sinon le replay ment et 2.9 cesse d'être mesurable.

#### Le tireur n'enroule jamais, et ce n'est pas un oubli

`side` et `lift` valent **0 à tous les niveaux**, comme ils l'ont toujours valu
pour le tir adverse. `ShotModel` résout la trajectoire **sans effet** vers la
cible puis attache l'effet par dessus, donc un enroulé déplacerait le ballon hors
du point même à partir duquel les indices sont fabriqués : le joueur lirait un
langage corporel qui désigne un endroit où le ballon ne va pas. **Le placement du
tireur est toute son intention.** Un niveau se lit dans sa dispersion et dans son
mensonge, jamais dans un effet ajouté.

#### Comment le non changement de SEANCE a été vérifié

Le `_rival_plan` expédié et `TakerAi.choose` ont été exécutés **côte à côte sur
3000 graines**, moitié sous pression, en comparant la visée, la puissance, le
relâchement **et** le tirage de la danse qui suit. Écart absolu maximal :
**exactement 0**. `tests/test_taker_ai.gd` fige ensuite cinq graines connues, calme
et sous pression, avec ce tirage de danse, plus les deux propriétés qui
*définissent* le barreau (`spread(SEANCE_LEVEL) == 1.0`, `feint_count` nul sur 200
graines) : sans elles le gel ne serait qu'un accident de ces cinq graines.

#### L'échelle, mesurée

Toutes ces lignes sont des **mesures**, sur 1500 à 2000 penalties par case. Si tu
touches aux tables du module, refais les.

| niveau | `spread` | `leak` | feinte | % de tirs passé `abs(x) = 3.30` | indice de visée du mauvais côté |
|---|---|---|---|---|---|
| Debutant | 1.32 | 0.88 | jamais | 4.0 % | 4 % |
| Confirme | 1.00 | 0.64 | jamais | 1.8 % | 18 % |
| Pro | 0.84 | 0.42 | 36 % | 1.0 % | 37 % |
| Legende | 0.68 | 0.22 | 59 % | 0.3 % | 44 % |

Deux conséquences à ne pas perdre de vue :

- **la pression est une vraie branche.** Au barreau de la SEANCE, un tir à ne pas
  manquer passe de 8.8 % à 27.7 % de frappes mistimées et de 0.5 % à 4.8 % de
  tirs hors du cadre. C'est la version visible du pourcentage caché d'autrefois ;
- **la danse sur la ligne est un marché, pas une arme.** Contre une Legende campée
  à 0.9 m, la visée bouge de **0.40 m en moyenne** et seul **un tir sur six**
  finit passé `x = -2.5`. Contre un Debutant elle ne bouge pas du tout, mais le
  tireur mistime bien plus souvent. Un tireur qui chercherait le coin opposé à
  tous les coups rendrait la danse toute puissante, ce que la règle 3 interdit.

---

### 2.13 `src/world/meshes.gd` - `class_name Meshes`

Toute la géométrie du jeu, générée par code. Statique, mise en cache quand le
maillage n'a pas de paramètre.

Le ballon n'est **pas** une `SphereMesh` : c'est un **icosaèdre tronqué**
(12 pentagones, 20 hexagones), subdivisé puis projeté sur la sphère, avec des UV
qui collent à `Tex.ball_panels()`. C'est ce qui permet de **voir** le ballon
tourner en vol, et donc de lire l'effet. Ce détail porte tout le rendu du jeu.

Piège moteur connu : un maillage construit avec `SurfaceTool` sans appeler
`generate_normals()` sort tout noir. Et `generate_tangents()` est obligatoire dès
qu'un matériau porte une carte de normales.

```gdscript
class_name Meshes
extends RefCounted

## Truncated icosahedron, spherified, radius Field.BALL_RADIUS, with UVs.
## `subdivisions` 2 gives a smooth ball, 0 gives a visible faceted one.
static func ball_mesh(subdivisions: int = 2) -> ArrayMesh
## A goal post or the crossbar: a capped cylinder along `axis`, length `length`.
static func post_mesh(length: float, radius: float, axis: Vector3) -> ArrayMesh
## A flat quad in the XY plane, centred, with UVs. For nets and adverts.
static func quad(width: float, height: float, uv_tiles: Vector2 = Vector2.ONE) -> ArrayMesh
## A box with proper UVs and tangents. SurfaceTool, not BoxMesh: BoxMesh has no
## usable UV for a tiling material.
static func box(size: Vector3, uv_scale: float = 1.0) -> ArrayMesh
## A capsule along Y, for limbs and torsos.
static func capsule(radius: float, height: float) -> ArrayMesh
## A tapered limb segment: a cone frustum from `r0` to `r1` over `length`, along Y.
static func limb(r0: float, r1: float, length: float) -> ArrayMesh
## The pitch surface: a subdivided plane so the light and the fog have vertices
## to work with. Spans x in [-half_x, half_x], z in [min_z, max_z].
static func pitch_plane(half_x: float, min_z: float, max_z: float, step: float) -> ArrayMesh
## A flat ribbon following a polyline at a fixed height, for painted lines.
static func line_strip(points: PackedVector3Array, width: float, closed: bool) -> ArrayMesh
## A circle arc as a painted line ribbon.
static func arc_strip(centre: Vector3, radius: float, from_angle: float, to_angle: float, width: float, segments: int) -> ArrayMesh
## Stadium stand: a raked block of steps rising away from the pitch.
static func stand(width: float, rows: int, row_depth: float, row_rise: float) -> ArrayMesh
## Floodlight pylon head: a truss frame carrying a grid of lamp faces.
static func floodlight_head(columns: int, rows: int) -> ArrayMesh
## A ring lying in the XY plane, for the Defi mode targets.
static func ring(inner: float, outer: float, segments: int = 48) -> ArrayMesh
## Every mesh of a procedural humanoid, keyed by part name. Keys:
## "pelvis", "torso", "head", "upper_arm", "fore_arm", "hand",
## "thigh", "shin", "foot". Sized for a 1.88 m keeper; scale for the shooter.
static func humanoid_parts() -> Dictionary
static func clear_cache() -> void
```

---

### 2.13b `src/world/character_models.gd` - `class_name CharacterModels`

**Le seul module du jeu qui sait qu'un glTF existe** (règle de 0). Il charge la
figure humaine rigguée de `assets/models/player.glb` (CC0, 31 370 triangles,
163 os), la corrige, la **recoupe**, la colorie et la **pose**. Le gardien et le
tireur sortent du même fichier et ne diffèrent que par le rôle. Le maillage
utilisé à l'écran fait **31 968 triangles** : le fichier en compte 31 370 et les
coutures redécoupées (voir plus bas) en ajoutent 598. Le fichier lui-même n'est
jamais réécrit.

`Meshes.humanoid_parts()` **reste le corps de référence** : si le modèle est
absent, `available()` rend `false`, `build()` rend `null`, et `Keeper` comme
`Shooter` dessinent leur humanoïde procédural comme avant. Supprimer `assets/`
ne casse rien.

Corrections portées **ici et nulle part ailleurs** :

- **Échelle.** Le modèle est authoré à 1.80 m, pieds en y = 0, racine à
  l'échelle (1, 1, 1). `build()` le remet à la taille du rôle et re-normalise la
  racine si un ré-export réintroduisait une armature en centimètres.
- **Orientation.** La figure **regarde vers +Z**. Le gardien regarde vers +Z
  (voir 1) donc il ne tourne pas ; le tireur regarde vers -Z donc son noeud de
  rig porte un demi tour.
- **Boîte de culling.** Un maillage skinné garde la boîte de sa pose de
  référence, qui est celle d'un homme debout. Un gardien en pleine extension en
  sort et le moteur le supprimerait à l'image la plus importante du jeu.
  `build()` pose donc un `custom_aabb` volontairement **large**. Une boîte serrée
  est exactement la façon dont un personnage disparaît.
- **Coutures de la tenue.** La tenue est une **coque** posée sur le corps, et
  cette coque n'est que **trois morceaux** : le tronc (qui doit donner le
  maillot, les deux manches et le short) et un morceau par jambe (qui doit
  donner une chaussette et une chaussure). Le fichier découpait ces morceaux
  **triangle par triangle**, en testant les poids d'os et la hauteur, et ce test
  change d'avis d'un triangle au suivant : d'où un escalier en dents de scie en
  travers du col et des deux épaules, une épaule avec manche et l'autre sans
  (les poids gauche et droite diffèrent à la sixième décimale), des encoches
  rectangulaires de la couleur du short remontées dans l'ourlet du maillot, et
  la même chose entre chaussette et chaussure. Les **sept ouvertures** de la
  coque (encolure, deux poignets, deux jambes de short, deux hauts de
  chaussette) étaient ouvertes de la même façon et sont donc dentelées **dans le
  fichier lui-même**.
  `build()` refait toute la découpe avant de peindre quoi que ce soit :
  - une frontière de vêtement est une **surface analytique**, et un triangle à
    cheval est **coupé dessus**, jamais poussé d'un côté. Un vote au centroïde
    laisse encore une dent de scie d'un triangle de haut, soit un centimètre sur
    cette coque ;
  - la paire de manches vient d'**un seul plan miroité** en x, donc les deux
    côtés ne peuvent pas différer ;
  - l'encolure est recoupée par un **plancher plat qui remonte sur chaque
    épaule** (`_COLLAR_RISE`) et non par une forme ronde : une forme ronde est
    parallèle au sternum juste là où le tissu porte le creux de la fourchette
    sternale, et elle y mord un V. La remontée n'est pas décorative : un plancher
    plat seul est une **fente à deux murs verticaux**, et le tissu qu'il coupe est
    une nappe presque horizontale sur le trapèze qui continue de monter au delà
    des murs, donc chaque mur laissait un **long lambeau pointu de maillot dressé
    sur l'épaule**. En laissant le plancher grimper, la coupe court le long de la
    nappe jusqu'à en rencontrer le haut et il ne reste rien à laisser derrière ;
  - chaque seuil est **mesuré sur les arêtes ouvertes de ce maillage** au
    chargement, jamais écrit en dur, donc un ré-export garde ses coutures là où
    son propre corps les met.
  Le résultat est mis en cache une fois et partagé par les deux figures.
  Contrepartie assumée : le maillage reconstruit perd les LOD et le maillage
  d'ombre simplifié que l'importateur avait produits. Deux personnages, c'est le
  bon échange.
- **Silhouette.** Le fichier source est le maillage **de base** de MakeHuman,
  volontairement androgyne, et le mesurer dit exactement pourquoi il se lisait
  comme une femme. En demi largeurs, torse sans les bras : hanches 0.199, bassin
  large 0.224, taille 0.152, poitrine 0.162. **La partie la plus large de ce
  corps était le bassin**, et ce seul rapport est ce que l'oeil lit comme
  féminin, avant le visage et avant les cheveux. `build()` fait donc passer le
  maillage importé par une **passe de mise en forme dans la pose de référence**,
  avant la redécoupe des coutures : profil de largeur et de profondeur en
  fonction de la hauteur (épaules et poitrine élargies, nuque épaissie, hanches
  et bassin resserrés, taille redressée) plus un **gonflement radial** des
  membres autour des segments du squelette de repos.
  Deux règles dictent les nombres, et les deux ont été apprises en mesurant une
  image :
  - le profil met x à l'échelle **autour de l'axe du corps**, donc à une hauteur
    où le corps est *deux jambes* il **écarte les jambes** au lieu d'épaissir
    l'une ou l'autre. Le short pend exactement sur une telle hauteur et c'est à
    lui que l'oeil compare les épaules : sous la taille le profil reste donc à un
    ou en dessous, et tout le volume des jambes vient du gonflement radial ;
  - une épaule se lit **carrée** ou **tombante** selon la pente du contour, qui
    vaut `x'(y) * w(y) + x(y) * w'(y)`. Le second terme est la seule prise que
    cette passe ait dessus et il n'est positif que tant que `w` **monte encore** :
    la courbe grimpe donc jusqu'au sommet du trapèze avant de retomber dans la
    nuque.
  Résultat mesuré sur le maillage dessiné, en demi largeurs, dans les unités du
  modèle : **maillot le plus large 0.396 contre short le plus large 0.225**, soit
  un rapport de **1.76** contre **1.48** pour le profil précédent (0.348 contre
  0.235) ; sur la bande d'épaule (y 1.42 à 1.48, manches comprises) 0.415 contre
  0.338, et sur la bande de hanche (y 0.78 à 0.94) 0.215 contre 0.224.
  Trois propriétés en font une passe de sommets et non des échelles d'os :
  - une échelle d'os **se propage aux enfants** : élargir une clavicule gonfle
    le bras qui y pend et épaissir une vertèbre gonfle la tête, donc chacune
    demande une contre échelle, posée sur les articulations mêmes que la
    cinématique inverse écrit ;
  - la déformation doit toucher les **sept surfaces à l'identique**. La tenue est
    une coque posée 6 mm au dessus de la peau ; déformer la peau et la coque
    différemment fait sortir le corps du maillot en semis de pixels. Une
    fonction pure de la position de référence est identique sur les deux **par
    construction**, ce qu'aucune retouche par surface ne peut promettre ;
  - **elle ne déplace jamais un sommet en hauteur.** Seuls x et z bougent. Toutes
    les hauteurs dont ce fichier dépend (ourlet, col, haut de chaussette, et
    surtout la semelle sur laquelle le rig se pose) sont donc inchangées au bit
    près, et aucune mise en forme ne peut planter une chaussure dans la pelouse.
  Les deux garde fous sont testés : un décalage de coque de 6 mm ne peut pas
  perdre plus de 20 % de sa longueur nulle part sur le corps, et le jacobien de
  la passe reste franchement positif partout, donc le corps ne se replie jamais
  sur lui même.
- **Tête.** Les **deux** figures portent une tête agrandie (`HEAD_SCALE`, 2.0).
  Le jeu se regarde depuis onze mètres derrière le tireur, avec un gardien haut
  de quatre vingts pixels : à cette taille une tête aux bonnes proportions est
  une vignette et les deux personnages se lisent comme des mannequins. C'est le
  registre de tout le rendu, et c'est pourquoi les corps ci dessus sont mis en
  forme **massifs** plutôt que réalistes.
  **Le pivot de cet agrandissement est le plancher du crâne, pas l'articulation.**
  `set_bone_pose_scale` met à l'échelle autour de l'origine de l'os, et
  l'articulation de tête de ce rig est à y = 1.636, à hauteur d'oreille : 0.164 de
  crâne au dessus, 0.072 de mâchoire en dessous. Doubler autour de ce point
  descendait donc la mâchoire de 7.2 cm aussi sûrement qu'il montait le sommet de
  16.4, le menton arrivait sous la base du cou et **dans** le maillot, et le col
  avait été recoupé sur un corps à tête normale. Mesuré de près sur les deux
  figures : mâchoire devant le col, coin de peau pincé à côté, et **aucun cou**.
  L'os est donc **levé** (`_NECK_SHOW`) d'exactement de quoi ramener le menton où
  le fichier le dessinait, plus un peu, avant d'être mis à l'échelle : le crâne ne
  grandit plus que vers le haut, le col qui lui va lui va de nouveau, et il reste
  un cou visible. La figure gagne en hauteur ce que le crâne gagne, et cela se
  paye **au sommet, jamais aux pieds** : `pose()` place le rig par les hanches.
  Deux conséquences pour les appelants :
  - une cible mesurée depuis l'articulation de tête qui doit atterrir **sur** la
    tête (les mains sur la tête d'un tireur qui vient de manquer) doit y ajouter
    `metrics()["head_rise"]` ;
  - l'emprise de l'os de tête sur les poids de peau est **effacée** en dessous du
    haut du tissu et rendue pleine au dessus de la mâchoire. Sans cela le col du
    maillot, qui hérite des poids du corps sur lequel la coque a été modelée,
    était doublé avec le crâne et s'ouvrait en entonnoir déchiré autour du cou.
    C'est, comme la mise en forme, **une seule fonction de la position de
    référence appliquée aux sept surfaces**, donc la coque et la peau ne peuvent
    pas être en désaccord dessus.
- **Cheveux.** Le fichier n'en porte aucun et l'atlas UV de MakeHuman n'offre
  aucun moyen d'en peindre, donc une calotte est ajoutée ici : deux crânes chauves
  identiques sont la seule façon dont ce modèle a l'air **pire** que les boîtes
  qu'il remplace. Elle n'est plus une sphère aplatie posée sur le sommet, elle est
  une **coque des triangles du crâne lui même**, poussés de `_HAIR_THICK` le long
  de leurs propres normales. Trois raisons, et elles sont mesurées :
  - la sphère était centrée **cinq centimètres derrière** le crâne qu'elle devait
    couvrir (z = -0.008 pour une boîte crânienne centrée sur z = +0.044 dans le
    repère de l'os de tête). Elle débordait donc de sept centimètres à l'arrière
    et s'arrêtait à z = +0.087 quand le front court jusqu'à z = +0.148 : la bande
    entre les deux **était** le ruban de cuir chevelu nu que l'audit a trouvé sur
    les deux figures ;
  - aucune sphère mise à l'échelle ne répare cela. Un ellipsoïde dont l'équateur
    est assez haut pour être des cheveux courts est un ellipsoïde dont l'équateur
    dépasse de trois centimètres d'un crâne qui se rétrécit vers le sommet : un
    bord de chapeau. Une coque du crâne le suit **par construction**, à ce
    ré-export comme au suivant, et ne peut déborder nulle part ;
  - **le bord n'est plus un bord.** L'épaisseur descend jusqu'à `_HAIR_BITE` **sous**
    la peau dessinée (`_SKIN_SHRINK`) à la naissance des cheveux, donc le rebord
    de la calotte est enterré dans le cuir chevelu et la limite visible est la
    **courbe d'intersection** des deux surfaces. Une frontière qui est une
    intersection ne peut ni montrer une marche ni laisser un jour.
  La hauteur est **divisée par deux**, ce qui était la demande : la calotte se
  tient 11 mm au dessus du cuir chevelu dessiné là où la sphère se tenait 22 mm au
  dessus du sommet, et le bas de la naissance des cheveux est passé de 0.23 à 0.56
  de la hauteur du crâne. Elle est lue par **azimut** autour de la boîte crânienne
  et non par hauteur (haute sur le front, basse à la tempe, un peu remontée à la
  nuque) : une hauteur seule dessine un bonnet de bain. Tous les seuils sont des
  **fractions de la hauteur de crâne mesurée**, jamais des centimètres.
- **Visage et cou.** La tête est une surface à part de la peau du corps parce que
  l'atlas de MakeHuman range des morceaux de cou sur les texels du visage. Sur le
  gardien les deux surfaces ne diffèrent pas que par leurs UV : l'une échantillonne
  la **photographie** d'un visage et l'autre est un `Palette.SKIN` plat, donc leur
  frontière est une **marche de teinte**, et le test étant par triangle, une marche
  en dents de scie d'un centimètre. Posée à la base du cou elle passait un
  centimètre sous le bord du col, ce qui a l'air sûr et ne l'est pas : un col est
  une **ouverture**, et toute caméra au dessus du gardien regarde dedans. La
  coupure est donc descendue de `_FACE_SEAM_DROP` **sous le point le plus bas du
  bord du col**, mesuré sur le tissu lui même : tout ce que le col peut montrer est
  d'une seule surface et d'un seul teint, et la couture est enterrée sous l'étoffe.
- **Mains.** Le modèle porte une main anatomique à cinq doigts écartés, longs et
  fins, la même sur les deux figures : peinte en orange elle se lit comme une
  **serre** dès qu'on s'approche. Un gant de gardien est l'objet inverse, un
  tampon large et plat sans écart entre les doigts. La surface de main est donc
  **éteinte** et un solide est accroché à chaque poignet à la place : un ellipsoïde
  aplati, couché dans le repère mesuré de la main (direction des doigts et normale
  de paume relevées sur le maillage), rembourré pour le gardien, plus court et plus
  rond pour le tireur, dont les mains courent fermées. Les tailles sont des
  **fractions de la main mesurée** et jamais des centimètres.
  `hand_reach` n'est **pas** touché : c'est lui que `Keeper` et `Shooter` visent et
  lui qui décide où le gant dessiné se pose, donc le solide est dessiné **autour**
  de ce point. Mesure de contrôle après la passe complète : `hand_reach` a bougé de
  **0.05 mm**.
  Éteinte par **fondu** et non par ciseau, et la différence est une ombre : une
  surface au ciseau reste opaque pour la carte d'ombres, donc la main éteinte
  projetait toujours cinq ombres de doigts **sur le gant** posé par dessus.
- **Allonge des bras.** `Keeper` couvre une cible hors de portée en **mettant à
  l'échelle** ses deux os de bras, jusqu'à 30 % (`Keeper.MAX_STRETCH`), et
  l'épinglage reproduisait cela fidèlement : 30 % d'un bras de 51 cm font 15 cm
  d'étirement de peau, soit des bras en caoutchouc avec une main au bout en
  pleine extension. `pose()` **plafonne** l'étirement dessiné à 12 % par os et
  fait payer le reste par la **ceinture scapulaire**, qui glisse jusqu'à 6 cm
  vers le gant, la clavicule en emportant les deux tiers pour que le deltoïde
  voyage avec elle. Ce qui reste n'est pas payé, volontairement : un gardien qui
  n'atteint pas le ballon doit être **dessiné ne l'atteignant pas**.
  **Aucun arrêt ne change.** `KeeperBrain.try_save` se mesure sur la pose du
  cerveau, jamais sur le squelette dessiné, et l'équilibrage est mesuré sur cette
  pose : c'est une correction de rendu et rien d'autre.
- **Coudes.** Un coude résolu à **exactement 180 degrés** n'est pas un bras, c'est
  un tube, et les deux solveurs en produisent honnêtement à pleine extension parce
  que la solution fermée à deux segments au maximum d'allonge **est** une droite.
  `pose()` rouvre donc tout coude plus tendu que `_ELBOW_MIN_BEND` (sept degrés),
  en gardant les deux longueurs et le plan que l'appelant avait choisi. Le prix est
  arithmétique et il est minuscule : sept degrés sur un bras d'un demi mètre
  raccourcissent la portée épaule-poignet de **neuf dixièmes de millimètre**, et le
  gant est déplacé d'autant et pas davantage, contre un rayon de gant de 16 cm.
- **Matériaux.** Sept surfaces (`skin`, `gloves_or_skin`, `jersey`,
  `sleeves_long`, `shorts`, `socks`, `boots`), reconnues par
  `Material.resource_name` et jamais par leur index, repeintes en couleurs
  `Palette` posées en surcharge sur le `MeshInstance3D`. Deux d'entre elles sont
  **éteintes** plutôt que peintes : `gloves_or_skin` sur les deux rôles (voir
  **Mains**) et `sleeves_long` sur le tireur, dont le maillot s'arrête au biceps.
  La géométrie éteinte reste en place, parce que c'est d'elle que `hand_reach` est
  mesuré et que c'est contre cette mesure que les bras sont résolus. Le modèle ne porte
  **aucune texture d'albédo** et **aucun clip d'animation** : il n'en existe pas
  en CC0 pour ce rig. Ce n'est pas un manque, c'est l'architecture du jeu, qui
  **pose** ses corps depuis `KeeperBrain.dive_pose` au lieu de jouer une
  timeline.
- **Ombres.** Le personnage **projette** son ombre (elle le pose sur la pelouse)
  mais ne la **reçoit pas** : le kit est une coque d'un millimètre d'épaisseur
  et se couvrait d'acné d'auto ombrage, mesuré en rendant la même image avec la
  projection coupée.

```gdscript
class_name CharacterModels
extends RefCounted

const MODEL_DIR := "res://assets/models"
const PLAYER_FILE := "player.glb"

const ROLE_KEEPER := 0
const ROLE_SHOOTER := 1

## On screen heights, metres.
const KEEPER_HEIGHT := 1.88
const SHOOTER_HEIGHT := 1.82

## How much bigger than life the head is drawn, on BOTH figures. The second name
## is the one the keeper shipped with and is kept as an alias.
const HEAD_SCALE := 2.0
const KEEPER_HEAD_SCALE := HEAD_SCALE

## True when a model is installed and loadable. Cached, misses included, so an
## asset-less checkout costs one filesystem probe for the whole session.
static func available(role: int) -> bool

## Builds one figure, or null when no model is installed, which is the caller's
## cue to keep its procedural body. The returned Node3D already carries the
## scale, the facing, the cull box and the kit.
static func build(role: int) -> Node3D

## Everything a caller needs to size its own rig to the model, in metres, at the
## role's final on screen scale. Empty when no model is installed. Measured from
## the imported skeleton and mesh at load time, never hardcoded.
## Keys: "scale", "height", "hip_height", "shoulder_half", "shoulder_rise",
## "hip_half", "torso", "head_lift", "head_rise", "upper_arm", "fore_arm",
## "hand_reach", "thigh", "shin", "foot_reach", "sole_drop" (floats) and "anchor"
## (Vector3, in the model's own unscaled units).
## "head_rise" is how far the DRAWN skull sits above the head joint, because the
## enlarged head is scaled about its jaw and not about the joint. Add it to any
## target measured off the head joint that has to land ON the head.
## The anchor of a figure is its HIP MIDPOINT, which is what
## KeeperBrain.dive_pose calls the body centre.
static func metrics(role: int) -> Dictionary

## The padded glove hung off each wrist, as the three SEMI AXES of the solid in
## the role's drawn units. Keys "along" (down the fingers), "girth" (the larger
## of the two across the palm), "back" (how far the CENTRE of the solid sits
## BEHIND the hand centre the arms are solved to). Empty with no model.
## This is the glove a role is BUILT with, and it is a FLAT PAD: on the keeper,
## 105 mm along, 52 mm across, 19 mm through.
static func mitt_shape(role: int) -> Dictionary

## Where a BUILT figure's glove has actually ENDED UP, in WORLD space, once it has
## been posed. Keys "centre" (Vector3), "axis" / "across" / "through" (unit
## Vector3, orthogonal), "along" / "half_across" / "half_through" (floats).
## Empty with no model, or before the figure is in the tree.
##
## THIS IS NOT `mitt_shape` AND THE DIFFERENCE IS LOAD BEARING. `Keeper` solves
## its arms against `hand_reach`; `_add_mitts` draws the glove around a point of
## its own; and `pose()` bounds how far an over extended arm may follow its
## target at all. A caller that wants to put a ball IN the glove has to ask where
## the glove is, not where the arm was aimed. Keeper.hold_point does exactly that.
##
## All THREE semi axes are published because the glove is flat. Folding the width
## of the palm and its thickness into one radius and taking the larger seats a
## ball 33 mm off the leather.
static func mitt_solid(figure: Node3D, left: bool) -> Dictionary

## Poses a figure from world space joints. Every key is optional.
## Bases are FACING bases: +Y up, +Z the direction the figure looks. A caller
## whose body faces -Z (the Godot node convention) turns its basis half a circle
## about its own Y first.
##   "hips"  Vector3   "body" / "chest" / "head"  Basis
##   "shoulder_l" "elbow_l" "wrist_l" "glove_l"   Vector3, and the same in _r
##   "hip_l" "knee_l" "ankle_l" "toe_l"           Vector3, and the same in _r
## Every limb bone is PINNED on the joint the caller solved, position included,
## so the figure reproduces the caller's inverse kinematics to the millimetre.
## That is what keeps the drawn glove and the glove KeeperBrain.try_save tests
## the same object.
## The ONE exception is an arm the caller stretched past what an arm does: the
## drawn stretch is capped at 12 percent per bone and the shoulder girdle slides
## up to 6 cm towards the glove to pay for it, so at full dive extension the
## glove can be drawn up to about 3 cm short of the one the save test used. That
## is deliberate and it changes no save: see "Allonge des bras" above.
static func pose(figure: Node3D, joints: Dictionary) -> void

static func clear_cache() -> void
```

---

### 2.14 `src/world/pitch.gd` - `class_name Pitch` extends Node3D

Construit la pelouse, les marquages peints et la collision du sol dans
`_ready()`. Rien d'autre. Les lignes sont des **maillages plats posés 1 cm au
dessus** de la pelouse, pas des décalques : un décalque sur un sol quasi plat
z fight, un ruban surélevé jamais.

```gdscript
class_name Pitch
extends Node3D

## Builds turf, markings and the ground collider. Idempotent.
func build() -> void
## Height of the turf under a world point. Flat for now, but the ball asks
## through this so a cambered pitch stays possible.
func ground_height(x: float, z: float) -> float
## Marks the turf where the ball was struck or where the keeper landed.
func add_scuff(position: Vector3, radius: float) -> void
```

---

### 2.15 `src/world/goal_frame.gd` - `class_name GoalFrame` extends Node3D

Poteaux, barre, et surtout **le filet, simulé**. Le filet est une grille masse
ressort intégrée en Verlet : quand le ballon le frappe, l'onde part du point
d'impact et se propage. C'est la récompense visuelle du but, elle doit être
bonne.

Grille : panneau arrière 48 x 20, toit 48 x 12, deux côtés 12 x 20. Les bords
attachés au cadre et au sol sont épinglés, le reste est libre.

```gdscript
class_name GoalFrame
extends Node3D

## Builds posts, bar, net grids and the frame colliders. Idempotent.
func build() -> void
## Pushes the net at a world point, as if hit by a ball carrying `velocity`.
func net_impulse(point: Vector3, velocity: Vector3) -> void
## Steps the Verlet net. Called from _physics_process, exposed for the tests.
func step_net(delta: float) -> void
## Deepest current displacement of the net, metres. The tests use it to prove the
## net actually moves, and the smoke probe uses it to prove a goal was scored.
func net_bulge() -> float
## Resets the net to rest instantly.
func settle_net() -> void
```

---

### 2.16 `src/world/stadium.gd` - `class_name Stadium` extends Node3D

Tribunes, foule, projecteurs, panneaux publicitaires, drapeaux de corner. Tout
en `MultiMeshInstance3D` ou en maillages fusionnés : le stade ne doit pas coûter
plus de quelques dizaines d'appels de dessin.

Les projecteurs sont **quatre pylônes** aux coins, chacun portant une grille de
lampes émissives, plus **un `DirectionalLight3D` par pylône est interdit** : ce
sont des `SpotLight3D` visant le rond central, ombres actives sur deux d'entre
eux seulement (le coût des ombres est la première dépense du jeu).

```gdscript
class_name Stadium
extends Node3D

func build() -> void
## Crowd excitement in [0, 1]: drives the spectator animation and the ambience.
func set_excitement(level: float) -> void
## One off crowd reaction. `verdict` is a Shootout.Verdict value.
func react(verdict: int) -> void
## Camera flashes ripple through the stands. Called on a goal.
func flash_burst(count: int) -> void
```

---

### 2.17 `src/render/sky.gd` - `class_name SkyController` extends Node

Le ciel, **le soleil**, l'environnement, le brouillard et la lumière ambiante.

Le jeu se joue **de jour** : fin d'après midi dégagée, ciel bleu avec des cumulus
(`Tex.clouds()` en `sky_cover`), soleil bas de côté qui étire des ombres douces
en travers de la surface de réparation. Le look nocturne sous projecteurs reste
entièrement atteignable, il n'est simplement plus celui du lancement.

Ce module **possède le seul `DirectionalLight3D` du jeu**, créé dans `build()`
comme enfant de ce noeud. C'est la clé de tout l'éclairage, et c'est aussi le seul
budget d'ombres du jeu : deux cascades PSSM sur 70 m, première coupe à 0.45. Le
contrat de 2.16 interdit toujours un `DirectionalLight3D` **par pylône** ; un
soleil unique n'est pas un pylône.

**L'azimut du soleil n'est pas libre.** Toutes les caméras regardent vers -Z : un
soleil derrière la caméra jette chaque ombre derrière l'objet, invisible, et un
soleil derrière le but met le gardien à contre jour. La lumière part donc
essentiellement **de côté**.

Piège moteur connu, et il décide de quel bouton on tourne : `ambient_light_energy`
et `ambient_light_color` sont **sans effet** tant que
`ambient_light_sky_contribution` vaut 1.0. De jour la contribution EST à 1.0 et le
niveau du remplissage se règle donc par `sky_energy_multiplier` du ciel ; de nuit
la contribution tombe à 0.2 d'abord, et seulement ensuite la couleur ambiante
explicite agit.

```gdscript
class_name SkyController
extends Node

## Above this, the sun is the key light and the pylons are off. Below it, the
## night wiring and the night emission floors are the right call.
const DAYLIGHT_THRESHOLD := 0.35

## Time of day: 0 = full night under the pylons, 0.5 = dusk, 1 = bright late
## afternoon daylight. The game runs at 1.0. Everything interpolates over the two
## segments night -> dusk -> day, so any value in between is a legal look.
##
## Going back to the night match takes TWO changes: this value below the
## threshold, AND `Mats.daylight = false` before the first material is built.
## A mismatch is reported by build() with push_warning.
var evening: float

## True when the current hour is lit by the sun rather than by the pylons.
func is_daylight() -> bool

func build() -> void
## Rebuilds the environment, the sky and the sun for the current `evening`.
func apply() -> void
## Slow drift of the haze and the lamp flicker, called every frame. Both fade to
## nothing in full daylight.
func animate(delta: float) -> void
```

---

### 2.18 `src/ball/ball.gd` - `class_name Ball` extends Node3D

Le ballon. **Intégration maison** via `Aero`, pas de `RigidBody3D` : le moteur
n'a ni traînée quadratique ni effet Magnus, et un penalty sans Magnus n'est pas
un penalty. Les collisions sont testées à la main par balayage, contre le cadre
(`Field.sweep_frame`), le sol, le filet et le gardien.

`_physics_process` fait, dans cet ordre, à 120 Hz :
1. un pas `Aero.integrate`,
2. `Field.sweep_frame` sur le segment parcouru, rebond éventuel,
3. le passage du plan de but, le filet, le sol,
4. **le test d'arrêt du gardien**, sur ce qui reste du segment,
5. la rotation visuelle du maillage selon `spin`.

Le gardien est interrogé **en dernier**, et ce n'est pas la même chose que « le
gardien passe après ». Tous les autres tests ne font que **raccourcir** le
segment ; la question posée au gardien a un **effet de bord**, puisque y répondre
est ce qui lui fait revendiquer l'arrêt, jouer son son et verrouiller le verdict.
On la lui pose donc une fois le segment ramené à la part du trajet que le ballon
atteint vraiment, et s'il l'a touché là il **gagne d'office** : son contact est
dans une fenêtre qui s'arrête déjà à la première chose solide.

#### UN ARRÊT EST UN ÉVÉNEMENT PHYSIQUE

C'est ce module qui en fait un. La réponse du gardien porte un drapeau `catch`
(voir 2.12 et 2.19), et les deux issues n'ont rien à voir :

- une **PRISE DE BALLE** termine le vol. Le ballon s'arrête net, son effet tombe
  à zéro et il est **tenu** : à partir de ce pas il n'est plus intégré du tout,
  il se pose simplement là où `keeper_hold` dit que les gants sont, à chaque pas
  de physique, pendant tout le reste du plongeon, la réception et la
  célébration. Un ballon intégré sortirait de la main en une image, et c'est
  pourquoi `held` est un **état** et non une vitesse nulle ;
- un **RENVOI** remet le ballon en jeu, avec un **plancher** : quoi qu'en dise la
  réflexion, un ballon repoussé repart **toujours vers le terrain** (au moins
  `PARRY_MIN_Z` en +Z), et la quantité de mouvement retirée à la direction -Z
  est rendue **sur les côtés et vers le haut**, là où va un dégagement du poing.
  Un gant qui effleure le ballon et le laisse dériver dans le filet, c'est
  exactement l'image qui fait passer un verdict ARRET correct pour un bug.

Avant tout cela le ballon ne demandait jamais rien au gardien : **rien
n'affectait `keeper_probe`**, toute la branche était du code mort, et un penalty
arrêté continuait sa route dans les buts pendant que le tableau affichait
« Arrêt du gardien ». C'est le bug que ce chapitre existe pour interdire.

```gdscript
class_name Ball
extends Node3D

signal struck(velocity: Vector3, spin: Vector3)
signal frame_hit(part: int, point: Vector3, speed: float)
signal net_hit(point: Vector3, velocity: Vector3)
signal ground_hit(point: Vector3, speed: float)
signal crossed_line(point: Vector3, inside: bool)
signal came_to_rest()

## Minimum speed back up the pitch, m/s, a parried ball leaves the glove with,
## and how the momentum taken out of -Z is paid back (sideways, upwards).
const PARRY_MIN_Z := 2.6
const PARRY_SPREAD := 0.60
const PARRY_LIFT := 0.42

var velocity: Vector3
var spin: Vector3
var flying: bool
## True while the ball is in the keeper's gloves. `flying` is false at the same
## time: a held ball is not in flight, it is furniture attached to a hand.
var held: bool
## Filled while flying, one entry per physics step: {"t", "position", "spin"},
## AND for the whole of a hold, so a caught ball replays as caught.
var flight_log: Array[Dictionary]
## Synchronous keeper query, `func(from: Vector3, to: Vector3) -> Dictionary`,
## answered inside the same physics step. `Main` wires it to Keeper.attempt_save.
var keeper_probe: Callable
## Where the gloves are, `func() -> Vector3`, asked every physics step while the
## ball is held. `Main` wires it to Keeper.hold_point. Unset, a catch degrades to
## a parry rather than leaving the ball hanging in the air.
var keeper_hold: Callable

func build() -> void
## Puts the ball back on the spot, at rest, log cleared, hold released.
func place_on_spot() -> void
## Launches it. Starts the flight log and emits `struck`.
func strike(new_velocity: Vector3, new_spin: Vector3) -> void
## Freezes the ball where it is, without clearing the log. A held ball is LET GO
## and left exactly where the gloves had it, which is why `Main` does not halt a
## ball the keeper is holding: it would hang in the air while he stands up.
func halt() -> void
## Puts the ball in the gloves and keeps it there. `anchor` is a
## `func() -> Vector3` giving the point it sits at, asked again every physics
## step: nothing is parented, so this works identically on the imported figure
## and on the procedural fallback. Ends the flight (`flying` false, `held` true)
## and emits `came_to_rest`.
func hold(anchor: Callable) -> void
## Seconds since the strike, 0 when not flying.
func flight_time() -> float
## Lateral deviation from a spin free flight, in metres. The HUD shows it as the
## "curve" figure after the shot.
func curve_amount() -> float
## Replays a logged position. `t` is seconds since the strike.
func seek_replay(t: float) -> void
## The predicted path from the current state, for the HUD preview.
func predict(velocity_guess: Vector3, spin_guess: Vector3, steps: int) -> PackedVector3Array
```

---

### 2.19 `src/keeper/keeper.gd` - `class_name Keeper` extends Node3D

Le corps du gardien : un humanoïde procédural dont les membres suivent les
positions rendues par `KeeperBrain.dive_pose`. Il ne décide de rien lui même,
il exécute et il rend.

Il **enregistre aussi son propre mouvement**, dans `pose_log`, exactement comme
le ballon enregistre `flight_log` : c'est ce qui permet au replay de rejouer le
plongeon en même temps que le vol. L'enregistrement commence au **départ de la
course d'élan**, pas à la frappe, parce qu'un gardien qui parie bouge **avant**
le contact et que ce pari anticipé est ce que le joueur veut revoir. Il s'arrête
à la **fin de la tentative** et non à la fin du plongeon (voir le point 3
ci dessous), et la tête de lecture le **scelle** : rejouer un journal n'y écrit
jamais rien.

**LE DERNIER MOMENT RESPONSABLE.** C'est la seule décision que ce module prenne,
et elle mérite d'être écrite ici plutôt que d'être découverte dans le code.

Un pari d'avant frappe est une **décision**, pas un ordre de partir tout de
suite. Le gardien qui, pendant la course d'élan, a décidé qu'il irait à droite
n'a pas décidé d'être par terre deux dixièmes avant le contact : il s'est autorisé
**au plus** cette avance, si le ballon l'exige. Alors `track` attend, à chaque pas,
que le vol restant estimé descende à `KeeperBrain.dive_time_needed(...)` plus son
avance autorisée, et **seulement alors** il pousse. L'avance réellement consommée
vaut `need + lead - vol restant`, bornée à `lead` : elle vaut tout sur un penalty
frappé à 30 m/s, et **rien du tout** sur une casserole qui met 0.9 s à arriver.

Sans cela, un ballon mal frappé arrivait sur un gardien déjà à plat depuis un
quart de seconde, à tous les niveaux identiquement : c'est précisément pourquoi
l'échelle de niveau n'existait pas sur les casseroles. En attendant, il regarde
0.3 s de vol de plus, son estimation converge, et **c'est là que sa perception
sert à quelque chose**. Le gardien ne voit jamais rien de plus qu'avant ; il
choisit seulement mieux le moment de quitter sa ligne.

Corollaire : le gardien s'engage **une fois**. Il n'y a pas de correction en
vol. Une fois qu'il a poussé, il vit avec ce qu'il a lu, ce qui est à la fois
honnête et ce qui garde la lucarne imprenable.

**IL TOUCHE LE BALLON UNE FOIS.** Dès qu'un contact a été signalé,
`attempt_save` répond « rien touché » pour le reste de la tentative. Le gardien
n'est pas un mur contre lequel le ballon perdu peut rebondir en boucle : il l'a
touché une fois, c'est l'arrêt, et la suite regarde le ballon.

**ET IL LE GARDE, QUAND IL PEUT.** Un contact de gant dans la paume, sur un
ballon assez lent, est une **prise de balle** (`KeeperBrain.catch_quality`, 2.12).
Le ballon est alors tenu, et `hold_point()` dit où : c'est `Ball` qui vient le
lire à chaque pas de physique. Trois conséquences valent d'être écrites ici.

1. **Le point de prise est la main DESSINÉE, pas celle que le cerveau a
   demandée.** À pleine extension le solveur arrête la main en deçà de la cible
   (`MAX_STRETCH`), et l'écart monte à un quart de mètre sur exactement les
   plongeons où l'on arrête un penalty. Un ballon tenu sur le point du cerveau
   flotte au delà du bout des doigts. Le volume de parade, lui, reste celui du
   cerveau : ce module ne le déplace jamais.
2. **Deux gants proches se referment ensemble** sur le ballon (`TWO_HAND_SPAN`),
   qui se pose entre les deux et non contre l'un des deux. Et il se pose
   **dessus**, ce qui se calcule et ne se règle pas : `HOLD_OFFSET` est la
   distance d'un **centre de gant** au **centre du ballon** quand la paume le
   touche (un rayon de ballon plus une paume rembourrée, soit le
   `KeeperBrain.GLOVE_RADIUS` avec lequel l'arrêt est jugé). Le décalage appliqué
   au milieu des deux gants en est donc **déduit par Pythagore** sur le demi
   écart, et pris **perpendiculairement** à la ligne des deux gants : les deux
   centres de gant tombent alors exactement à `HOLD_OFFSET` du ballon. Un
   décalage fixe donnait l'hypoténuse et non le côté - 12 cm poussés hors d'une
   paire écartée de 34 cm mettent le ballon à 20.8 cm des deux mains, cinq
   centimètres trop loin, et de près cela se lit comme un ballon collé au torse
   avec les mains posées à côté. Les poses qui **serrent** le ballon (la prise
   contre la poitrine, l'appui du relevé) écartent leurs gants de
   `CRADLE_HALF`, sous `HOLD_OFFSET`, parce qu'une paire de mains plus large que
   le ballon n'a aucune position où les deux le touchent.
3. **Un gardien enregistre toute la fin de sa tentative**, pas seulement son
   plongeon : la réception, le relevé, la célébration, l'attente ensuite
   (`_log_tail`). `Ball` journalise de son côté le ballon jusque dans le filet et
   pendant toute une prise, et les deux journaux sont lus par **une seule** tête
   de lecture : ils doivent donc couvrir la même fenêtre. Celui qui s'arrête le
   premier est **gelé** pour toute la queue du replay, et `dive_pose` finit un
   plongeon haut les hanches à un mètre et demi du sol : sans cela, la fin de
   chaque replay de but montrait un homme figé en l'air, son ombre par terre en
   dessous de lui, pendant que le ballon bougeait encore.

`celebrate(ARRET)` sur une prise de balle n'est pas un salut à la foule : il se
relève en **serrant le ballon** contre lui, les deux gants dessus, ce qui est
aussi ce qui amène le ballon contre sa poitrine au lieu de le laisser pendre au
bout d'un bras tendu.

#### La couche d'animation : épaules, coudes, genoux

`dive_pose` dit où sont les **gants** et les **crampons**. Elle ne dit rien des
épaules, des coudes et des genoux, et jusqu'ici la cinématique inverse pliait ces
six articulations dans **un seul plan fixe**, pour toutes les poses du jeu :
coudes toujours en arrière et en bas, genoux toujours droit devant. Le corps
bougeait, les articulations non, ce qui est exactement ce qu'on lit comme une
marionnette tirée par les mains.

La couche ajoutée est de **deux natures**, et la distinction est contractuelle.

1. **L'ARTICULATION**, qui décide ces trois articulations et rien d'autre
   (`_arm_pole`, `_leg_pole`, `CHEST_TWIST`, `SHOULDER_ROLL`). Elle est une
   **fonction pure de la pose courante** : aucune horloge, aucun état, aucun
   drapeau de phase. Deux propriétés en découlent et ce sont les raisons de
   l'écrire ainsi.
   - **Le replay s'articule.** `seek_replay` interpole deux poses du journal et
     appelle le même code de rendu : une fonction pure du résultat donne au corps
     rembobiné les mêmes épaules, coudes et genoux qu'au corps vivant, à
     n'importe quelle vitesse, en avant, en arrière, et dans le ralenti.
   - **Elle ne peut pas changer un arrêt.** `try_save` teste `pose()`, que rien
     ici ne touche, et le **bout** d'une chaîne à deux os ne dépend que de sa
     racine, de sa cible et de ses deux longueurs : un vecteur de pôle choisit le
     **plan** dans lequel l'articulation plie, et rien de plus.
2. **LES POSES**, là où le cerveau se tait : la garde et la danse sur la ligne
   (`prepare`), l'attente (`_idle_pose`), le relevé (`_recover_pose`) et les
   célébrations. Elles écrivent bien le dictionnaire de pose, et elles sont donc
   toutes **journalisées**, donc rejouées telles quelles.

Ce qui a été ajouté, nommément :

- **la garde**, qui respire et transfère son poids d'un pied sur l'autre. Les
  hanches descendent de `CROUCH_DEPTH` vers les crampons qui, eux, ne bougent
  pas : chaque centimètre est donc de la **flexion de genou**, et un genou plié
  est la seule chose qui sépare un gardien d'un homme qui attend le bus ;
- **la danse sur la ligne devient des PAS**. `KeeperBrain.line_dance` ne donne
  qu'un x, et le corps y répondait en glissant, les deux crampons soudés au
  gazon. La phase de pas est intégrée sur la **distance parcourue**
  (`STEP_LENGTH`), jamais sur l'horloge : il ne peut donc ni patiner ni courir
  sur place. Le pied arrière décolle (`STEP_LIFT`), passe devant (`STEP_REACH`)
  et se repose ; les gants contre balancent (`ARM_SWING`), ce qui plie un coude
  et déplie l'autre à chaque pas ;
- **le plongeon** garde exactement la trajectoire du cerveau. Ce qui change est
  la façon d'y aller : le buste **tourne dans le bras qui mène** (`CHEST_TWIST`),
  la ligne d'épaules **roule** vers le gant qui va le plus loin (`SHOULDER_ROLL`),
  et le coude quitte sa position repliée d'autant plus tard que le bras est
  encore court, si bien que l'avant bras se déplie en dernier et que **le gant
  arrive le dernier** ;
- **le relevé** : un gardien resté debout se déplie, un gardien à plat **pousse**
  (`_recover_pose`, `_brace_pose`, `GETUP_TIME`) - un gant planté dans l'herbe,
  les hanches montées sur un genou replié, puis debout. Un gardien qui **tient**
  le ballon ne plante jamais la main qui le tient, pour la raison évidente que
  `hold_point` suit le gant dessiné.

**La seule exception à la propriété (1)**, et elle est bornée et voulue : la
torsion et le roulis déplacent les **épaules**, donc un bras déjà en pleine
extension peut finir quelques centimètres plus court ou plus long. C'est borné
par `SHOULDER_ROLL` fois la demi largeur d'épaules, la main **dessinée** reste ce
sur quoi `hold_point` s'ancre, et le volume de parade reste la pose intouchée du
cerveau.

**Pourquoi le volume de parade ne peut pas bouger.** `attempt_save` teste
`_pose`, le dictionnaire que `_apply_pose` a reçu du cerveau. `_update_rig`, la
torsion du buste, le roulis d'épaules et `_protract` le **lisent** pour placer
des os et n'y réécrivent jamais rien. C'est une garantie de **structure**, elle
se vérifie en lisant le fichier, et c'est la seule qui vaille pour une couche de
dessin.

Cette section a longtemps ajouté « Mesuré : `tests/balance_probe.gd` rend les
mêmes tables avant et après ». **La phrase est retirée, elle était fausse deux
fois.** La sonde n'a jamais été relancée sur les deux versions ; et l'eût elle
été, elle n'aurait rien démontré. Une case de ses tables porte une bande de
**cinq points à deux sigma** au réglage par défaut, donc elle est incapable de
distinguer « rien n'a bougé » de « deux points ont bougé ». Une sonde
déterministe rend deux fois le même chiffre : cela prouve qu'elle est
déterministe, pas que le chiffre est précis. Voir `SEED_STRIDE` en tête de
`tests/balance_probe.gd`, et la façon dont les tables de 2.9 sont mesurées
maintenant.

```gdscript
class_name Keeper
extends Node3D

signal saved(limb: String, point: Vector3)
## `side` and `height` are the COARSE reading of the dive, for the crowd, the
## audio and the replay. The pose itself is built from a continuous target that
## this signal deliberately does not carry: nobody downstream needs it.
signal dive_started(side: int, height: int, gambled: bool)
signal landed()

## The animation layer, see "epaules, coudes, genoux" above. All of it is drawing
## only: none of these can move a glove or a boot away from the brain's pose.
const CHEST_TWIST := 0.34      # radians the chest turns into the leading arm
const SHOULDER_ROLL := 0.40    # shoulder roll, as a fraction of the half width
const STEP_LENGTH := 0.46      # metres of line per two step cycle
const STEP_LIFT := 0.115       # how high the swinging boot leaves the turf
const STEP_REACH := 0.145      # how far ahead of the body it lands
const ARM_SWING := 0.075       # glove counter swing against the feet
const CROUCH_DEPTH := 0.135    # hip drop of the set crouch, all of it knee flex
const GETUP_TIME := 1.15       # seconds to push off the turf back onto his feet

## Glove centre to ball centre when the palm is ON the ball, and how far apart
## the two gloves are held once the ball is won. See point 2 above.
const HOLD_OFFSET := 0.16
const TWO_HAND_SPAN := 0.52
const CRADLE_HALF := HOLD_OFFSET * 0.90

var level: int
var diving: bool
## Filled from the start of the run up to the end of the dive, one entry per
## step, oldest first. Each entry is a full pose dictionary ("centre",
## "glove_left", "glove_right", "boot_left", "boot_right", "lean", "airborne")
## plus "t", the seconds since the strike. `t` is NEGATIVE before the strike:
## that part of the log is the keeper committing during the run up. Same clock
## as Ball.flight_log, and cleared by reset_to_line(). Recording carries on to
## the END of the attempt (the landing, the get up, the celebration, the hold),
## so both logs cover the same window and neither replay ends frozen.
var pose_log: Array[Dictionary]

func build() -> void
## Back to the middle of the line, standing, ready.
func reset_to_line() -> void
## Body language phase: shuffles, crouches, watches the run up.
func prepare(elapsed: float) -> void
## Feeds the brain the shooter's tells. Called once, at the start of the run up.
func read_shooter(cues: Dictionary) -> void
## Called every physics step while the ball flies. Returns true the frame the
## keeper commits to a dive, which is the LAST RESPONSIBLE MOMENT described above
## and not simply the first frame he is allowed to move.
func track(ball_position: Vector3, ball_velocity: Vector3, spin: Vector3, elapsed: float) -> bool
## Save test for one ball step. Emits `saved` on contact, at most once per shot,
## and answers "nothing touched" for the rest of the attempt afterwards.
## Returns the KeeperBrain.try_save dictionary plus THREE keys that turn the
## verdict into a physical outcome, straight out of KeeperBrain.catch_quality:
##   "catch" bool  the ball was gathered rather than pushed away,
##   "grip"  float 1 dead centre of the palm, 0 at the edge of the window,
##   "hand"  String which glove holds it, "" for a parry.
func attempt_save(ball_from: Vector3, ball_to: Vector3) -> Dictionary
## True while a caught ball is sitting in this keeper's hands.
func holding() -> bool
## Where a caught ball sits right now, in world space, for the pose on screen.
## Anchored on the DRAWN hand, see the three points above. Ball.keeper_hold is
## wired to this. Returns the body centre when nothing is being held.
##
## The DIRECTION out of the hand is this file's own (the cradle and the one handed
## hold below). The DISTANCE is read off `CharacterModels.mitt_solid`, so the ball
## rests on the surface of the glove that is really drawn instead of at a fixed
## offset from a point nothing is drawn at. Without that the ball hung up to 70 mm
## clear of the leather on a clean catch while every distance in this file was
## right to the millimetre. A body with no model keeps the fixed offset.
## tests/smoke_probe.gd measures the contact on every catch (MITT_SLACK).
func hold_point() -> Vector3
## Current pose dictionary, for the tests and the replay.
func pose() -> Dictionary
## Reaction after the verdict: arms up, fists on the turf, hands on hips, or the
## ball clutched to the chest when he caught it. Called by Main on entering the
## VERDICT phase.
func celebrate(verdict: int) -> void
## Replays a logged pose. `t` is seconds since the strike, on the same clock as
## Ball.seek_replay, so driving both from one value keeps the dive and the ball
## in lockstep. Negative `t` is legal and shows the pre strike commitment. The
## two bracketing samples of `pose_log` are INTERPOLATED, so the playback stays
## smooth at any speed, slow motion included. A no op when the log is empty.
func seek_replay(t: float) -> void

## --- Quand c'est le JOUEUR qui tient ce corps (mode DUEL, 2.9) ---------------
## Hands this body to the player. While `keeping` is true, `track()` decides
## nothing and returns false: the dive arrives through commit_dive() and the line
## position through set_line(). Everything below the decision is unchanged, which
## is the point: the pose, the save envelope, the catch, the log and the replay
## are the same code on both sides of the duel. Cleared by reset_to_line().
## CALLED TWICE ON THE WAY IN, and the second call is not redundant: it is where
## the POSE LOG STARTS, exactly as read_shooter() starts it on the AI side. The
## first call (on the placement) opens the line to the player so he can pick his
## spot; the second (at the start of the run up) is the moment worth replaying,
## and recording anything earlier would splice two different clocks into one log
## and leave it out of order.
func set_player_driven(keeping: bool) -> void
## Where this body stands on its line, in metres, driven by KeeperInput.line_step.
## It WALKS there, with the same steps the AI line dance uses (see STEP_LENGTH):
## a player who slides with welded boots looks worse than one who does nothing.
## The RATE LIMIT belongs to the caller (KeeperInput.LINE_SPEED) and is not
## applied a second time here: a body drawn behind the position every other module
## believes it occupies would put the reach envelope around a keeper who is not
## there. It also works OUTSIDE `set_player_driven`, which is what lets the player
## take his spot during the placement, before the run up hands him the rest.
func set_line(line_x: float) -> void
## Launches the dive the player committed to. `dive` is the KeeperInput.commit
## dictionary, which carries the very keys KeeperBrain.choose_dive returns, so
## `dive_started`, `pose_log` and the replay are untouched by where it came from.
## A no op after the first call of an attempt: a keeper commits ONCE, on both
## sides of the duel, and there is no correction in flight for either of them.
## `committed_at` is read as the dive's ORIGIN on the shot's clock and not as
## "now": a dive launched at -0.18 has to be 0.18 s old at contact, which is the
## entire reward for going early, and it is also why the dive clock is absolute
## and therefore identical whatever the frame rate did during the run up.
func commit_dive(dive: Dictionary) -> void
## True once this attempt's dive has been launched, whoever launched it.
func committed() -> bool
```

---

### 2.20 `src/player/shooter.gd` - `class_name Shooter` extends Node3D

Le tireur : le corps vu de dos, la course d'élan, et **toute la saisie du tir**.
C'est lui qui possède la visée, la puissance, l'effet et la feinte, et qui
produit le dictionnaire de frappe via `ShotModel.resolve`.

Déroulé d'un tir :
`VISEE` la souris déplace le réticule, `strike` maintenu remplit la barre de
puissance, un curseur de précision balaye sa propre piste de temps. Relâcher
lance `COURSE`. Pendant la course, `feint` fait une feinte de frappe (au plus
deux), qui retarde et brouille la lecture du gardien. Au contact, `resolve`
produit la frappe.

**La vitesse du curseur est un réglage**, `sweep_level` (2.8), et c'est le second
axe de difficulté du jeu. Le tireur est seul à connaître les cadences : le
réglage n'est qu'un index dans `SWEEP_SCALES`. Le facteur est **verrouillé** au
début de la charge, jamais relu par image, sinon un réglage changé depuis la
pause ferait sauter le curseur au milieu d'une frappe.

#### Le corps : épaules, coudes, genoux, et une réaction

Le tireur est **la seule personne que le joueur regarde en permanence** : il
remplit le bas de l'écran pendant toute la visée et toute la course. Ce que ses
articulations font compte donc plus ici que partout ailleurs.

- **Le coude plie dans le BON SENS.** Un genou se plie vers l'arrière (le talon
  vers la fesse), un coude vers l'avant (la main vers l'épaule) : sur un corps
  qui regarde son propre -Z, le genou tourne **négativement** autour de X et le
  coude **positivement**. Les deux étaient pilotés dans le même sens, ce qui
  donnait au coureur deux genoux de plus à la place des bras. `_elbow_flex` porte
  la règle : `ELBOW_REST` au repos, plus `ELBOW_DRIVE` par radian de balancier
  **avant** et seulement `ELBOW_TRAIL` par radian de balancier arrière, ce qui
  est l'asymétrie d'un sprinteur et l'essentiel de ce qui fait lire une foulée
  vue de dos. Les bras croisent aussi la poitrine (`ARM_CROSS`) : deux bras qui
  pompent dans deux plans parallèles, c'est un rameur.
- **Les hanches fouettent à travers le ballon.** `_hip_snap` referme le bassin
  puis le fait tourner à travers le contact et au delà, et le buste **rend** une
  partie de ce fouetté, donc il RETARDE sur le bassin au contact et le rattrape
  dans l'accompagnement. C'est de là que vient la puissance à l'oeil.
  **Ce fouetté n'entre jamais dans `cues()`** : il arrive après la dernière image
  que le gardien a le droit de lire, et le lui donner reviendrait à lui donner la
  frappe.
- **Le coup de pied garde ses genoux.** Les deux jambes passent en cinématique
  inverse au moment de la frappe (elles y étaient déjà : c'est la seule façon de
  poser le crampon SUR un ballon fixe pendant que le corps dérive encore), et les
  deux coudes font maintenant des choses opposées : le bras contrepoids est jeté
  dehors et **se replie** en volant, le bras qui mène traverse la poitrine et
  **s'ouvre** au contact.
- **L'attente n'est plus figée** : la respiration et le transfert de poids
  existaient, les bras les suivent désormais, donc les deux coudes s'ouvrent et
  se ferment de quelques degrés en décalé.

**Et il réagit au verdict.** `react(verdict)` est le point d'entrée public, et
son appel est **facultatif** : le tireur trouve aussi le résultat tout seul en
regardant sa propre ligne du tableau des scores grandir (une lecture de propriété
par image, seulement entre le contact et le verdict). Passer le verdict fait
seulement tomber la réaction sur l'image exacte que l'appelant voulait. Trois
réactions, toutes des fonctions continues du temps, mélangées par dessus
l'accompagnement, et qui **ramènent d'abord les deux pieds sous lui** - sans quoi
la jambe de frappe reste où l'accompagnement l'a laissée et chaque réaction est
un homme en équilibre sur un pied :
- **BUT** : les deux bras jetés en l'air et ouverts, la poitrine dehors, deux
  petits rebonds ;
- **ARRET** : les mains sur les hanches, la tête basse, un lent hochement ;
- **POTEAU / BARRE / DEHORS** : les deux mains sur la tête, et elles y restent.

Les bras de ces trois poses passent par `_ik_arm`, une cinématique inverse à deux
os en forme close, et non par des angles : une main sur une tête doit **atterrir
sur la tête**. `_ik_arm` prend la direction dans laquelle le coude doit sortir et
en fait l'**axe de charnière** (`axis = dir x hint`), ce qui est perpendiculaire à
la ligne épaule-poignet par construction ; une cible hors de portée est bornée en
distance et garde sa direction, donc le bras s'étire vers elle au lieu de claquer.

Les mains vont sur le **sommet du crâne** (`HEAD_GRIP`, `HEAD_CROWN`) et non sur
les tempes, et c'est une décision de **lisibilité**, pas d'anatomie : la tête est
dessinée au double de la taille réelle (`CharacterModels.HEAD_SCALE`), donc des
mains posées aux tempes sont dessinées **dedans**, le geste disparaît, et tout ce
que le joueur voit est un homme qui écarte les coudes. La hauteur du geste ajoute
`metrics()["head_rise"]` à `HEAD_CROWN` : le crâne agrandi est mis à l'échelle
autour de sa mâchoire et non autour de son articulation (voir 2.13b), donc des
mains écrites contre l'articulation seule atterriraient sur la bouche.

```gdscript
class_name Shooter
extends Node3D

## Multipliers of the marker sweep rate, indexed by the `sweep_level` setting.
## Index 1 is the rate the game shipped with. The window of a clean strike is
## open 153 ms at index 0 and 50 ms at index 3, on a soft strike.
const SWEEP_SCALES: PackedFloat32Array = [0.60, 1.00, 1.40, 1.85]
const SWEEP_DEFAULT := 1

## The body, see "epaules, coudes, genoux" above. The elbow hinges POSITIVE about
## X and a knee hinges negative: an elbow folds forwards, a knee folds back.
const ELBOW_REST := 0.34       # flexion of a hanging arm
const ELBOW_DRIVE := 0.85      # extra flexion per radian of FORWARD swing
const ELBOW_TRAIL := 0.12      # ... and per radian of backward swing
const ARM_CROSS := 0.24        # how far a swinging arm crosses the chest
const HEAD_GRIP := 0.16        # half the span of the two hands on the head
const HEAD_CROWN := 0.23       # how far above the head joint they sit
const REACT_BLEND := 0.38      # seconds the reaction takes to come on
const REACT_TIME := 2.60       # seconds it runs before it simply holds

signal aim_changed(aim: Vector2)
signal charge_changed(power: float, marker: float)
signal run_up_started()
signal feinted(count: int)
signal struck(shot: Dictionary)

## Normalized reticle, see ShotModel.aim_point.
var aim: Vector2
var power: float
## Sweeping precision marker on the power bar, 0..1.
var marker: float
var side_spin: float
var lift_spin: float
var feints: int
var charging: bool
var running: bool

func build() -> void
## Back behind the ball, idle, inputs cleared.
func reset_stance() -> void
## Aim and charge handling. Only called during Phase.VISEE.
func handle_aim(delta: float, mouse_delta: Vector2) -> void
## Advances the run up, fires `struck` at contact. Only during Phase.COURSE.
func advance_run_up(delta: float) -> void
## Body language the keeper is allowed to read, right now.
func cues() -> Dictionary
## The predicted flight for the current aim and charge, for the HUD arc.
func preview(steps: int) -> PackedVector3Array
## Where the shooter's boot is, for the contact effect.
func boot_position() -> Vector3
## Tells the taker how his penalty ended so he can react to it: arms up on a
## goal, hands on the head on a miss, hands on the hips on a save. `verdict` is a
## Shootout.Verdict. Anything else, and any second call, is ignored: a man reacts
## to a penalty once, and `reset_stance()` is what clears it for the next one.
## CALLING THIS IS OPTIONAL. The taker also finds the verdict out for himself by
## watching his own row of the scoreboard, so the reaction works without the
## orchestrator knowing it exists; passing it in only makes it land on the exact
## frame the caller wanted.
func react(verdict: int) -> void
## Phase units per second the marker is sweeping at right now: base rate, power
## gain and the difficulty multiplier of the attempt. One crossing of the bar is
## one phase unit.
func marker_rate() -> float

## --- Quand c'est l'ORDINATEUR qui tient ce corps (mode DUEL, 2.9) ------------
## Hands this body to TakerAi. `plan` is the dictionary TakerAi.choose returned.
## The run up plays out on its own clock (TakerAi.run_up_time) with its own
## feints, `feinted` fires as it always did, and `struck` fires at contact
## carrying TakerAi.strike's dictionary, so nothing downstream learns that a
## human was not holding the controls. Player input is ignored until
## reset_stance().
## The plan NEVER reaches the screen through this body except as body language:
## what the run up shows is what TakerAi.tells_at says it shows, and no more.
func run_cpu_penalty(plan: Dictionary, rng_seed: int) -> void
## Seconds from now until contact while a CPU run up is playing, negative once it
## has struck, zero when no run up is playing. This is the clock 2.12a calls `t`,
## and it is the only one: Main reads it and passes it on.
func time_to_contact() -> float
```

---

### 2.21 `src/player/camera_rig.gd` - `class_name CameraRig` extends Node3D

La caméra. Quatre cadrages côté tireur, cyclés par `camera_cycle` : derrière le
tireur, la caméra de but (derrière le filet, face au tireur), la caméra de
télévision (haute et latérale), et l'orbite de replay. Un cinquième cadrage
appartient au mode DUEL et n'est **pas** dans le cycle (voir plus bas).

Piège moteur connu : une caméra qui suit avec un ressort critique **sans borne de
vitesse** décroche sur un ballon à 30 m/s et donne le mal de mer. La vitesse
angulaire de suivi est plafonnée.

#### `View.GARDIEN`, et ce qu'il doit rendre lisible

Le cadrage du mode DUEL : **derrière le gardien et un peu au dessus**, regardant
le terrain et le tireur qui arrive. Il n'est pas décoratif, c'est le seul
instrument de lecture du mode, et il porte trois obligations :

- **il suit la ligne.** Le gardien danse sur sa ligne, donc la caméra le suit en
  x, et elle le suit **amortie** : une caméra collée au bassin donne un but qui
  glisse latéralement à chaque pas, et un but qui bouge est un but qu'on ne peut
  pas viser ;
- **il donne la hauteur.** Un ballon qui arrive de face est, en projection, un
  disque qui grossit et rien d'autre : la hauteur ne se lit que si la caméra est
  **au dessus** de la ligne d'yeux, assez pour que la pelouse serve de règle sous
  le ballon. C'est ce que « un peu au dessus » veut dire, et c'est mesurable :
  depuis ce cadrage, un tir au ras du sol et un tir à mi hauteur ne doivent pas
  se projeter au même endroit de l'écran à mi vol ;
- **il ne cache pas la course d'élan.** Les indices de `TakerAi.tells` sont des
  choses que le tireur **fait avec son corps** ; un cadrage où il n'est qu'une
  silhouette de vingt pixels rend tout le module inutile.

Il n'entre pas dans `cycle_view()` : c'est le cadrage d'une phase et non un choix
de confort, et le joueur qui cyclerait hors de lui pendant une lecture perdrait
le tour. `Main` le pose et le retire avec la phase, et `cycle_view()` **refuse de
le quitter** plutôt que de sauter au cadrage suivant : la touche `camera_cycle`
est un réflexe, et un réflexe ne doit pas pouvoir coûter un tour.

**Les trois obligations ci dessus sont tenues par trois nombres, et ils sont
mesurés.** Le cadrage est à **7.20 m derrière la ligne de but, 3.90 m de haut**,
visant `(0, 1.35, 0)`, avec un objectif de **40 degrés** vertical. Ce qu'ils
donnent, calculé sur ce cadrage :

- les poteaux tiennent dans l'image avec de la marge, en 16:9 **comme en 4:3** ;
- un ballon au ras du sol et un ballon à 1.20 m se projettent **11 % de la hauteur
  d'image** l'un de l'autre à mi vol, soit une centaine de pixels en 900p : la
  hauteur se lit ;
- le tireur fait **14 % de la hauteur d'image** et ses pieds tombent **9 % au
  dessus de la tête du gardien**, donc les deux corps ne se confondent jamais.

Reculer, descendre ou élargir touche à ces trois chiffres à la fois : si tu
déplaces ce cadrage, remesure les trois.

La caméra regarde à travers le filet, et c'est **inévitable** : le but est une
boîte fermée par l'arrière, donc tout objectif placé derrière le gardien voit le
panneau arrière ou le toit. `View.BUT` vit avec depuis toujours. C'est pour cela
que l'enveloppe est tracée avec un liseré sombre sous son trait clair.

```gdscript
class_name CameraRig
extends Node3D

## GARDIEN is APPENDED and is NOT part of the cycle: see above.
enum View { DERRIERE, BUT, TELE, REPLAY, GARDIEN }

var view: int
var shake: float

func build() -> void
func set_view(new_view: int) -> void
## Cycles the four shooting side views. GARDIEN is skipped: it belongs to a
## phase, not to a preference, and it is set by Main. Called while GARDIEN is up
## it does NOTHING, rather than cycling out of the only framing the keeper side
## can be played from.
func cycle_view() -> void
## Follows the ball, or holds the aim framing when it is not flying.
func track(target: Vector3, flying: bool, delta: float) -> void
## Where the player keeper is standing on his line, in metres, so the GARDIEN
## framing follows the line dance. DAMPED, and deliberately slower than the
## shuffle: a camera welded to the pelvis slides the whole goal sideways under the
## dive reticle at every step, and a goal that moves is a goal nobody can aim at.
## A no op in every other view.
func follow_line(line_x: float, delta: float) -> void
## One off impulse, damped over time. `amount` 0..1.
func add_shake(amount: float) -> void
## Slow orbit for the replay, `t` seconds into the replay.
func orbit_replay(centre: Vector3, t: float) -> void
## The active Camera3D, for the HUD's world to screen projection.
func camera() -> Camera3D
```

---

### 2.22 `src/audio/crowd.gd` - `class_name Crowd` extends Node

La foule sonore : une ambiance bouclée dont le niveau suit la tension, plus des
réactions ponctuelles. Se contente d'appeler `Sfx`, ne joue rien elle même.

```gdscript
class_name Crowd
extends Node

func build() -> void
## Tension in [0, 1], drives the ambience level and the murmur.
func set_tension(level: float) -> void
## One off reaction to a Shootout.Verdict.
func react(verdict: int) -> void
## The held breath just before a strike.
func hush() -> void
```

---

### 2.23 `src/ui/hud.gd` - `class_name Hud` extends CanvasLayer

Le HUD de jeu : réticule de visée, module de frappe (puissance **et** précision,
voir plus bas), indicateur d'effet, arc de trajectoire prévu, score de la séance,
verdict, et les statistiques du tir (vitesse en km/h, courbe en cm).

Tout est dessiné avec `_draw` sur un `Control` plein écran : aucune scène
d'interface, aucune police importée. La police est celle par défaut du projet.

Piège moteur connu : un `Control` qui dessine doit appeler `queue_redraw()`, et
`_draw` n'est **jamais** rappelé tout seul quand une variable change.

Trois règles de mise en page, **non négociables**, parce qu'elles décident de ce
que le joueur voit à l'instant qui compte :

- **Le milieu de l'image appartient à la bouche du but.** C'est là que le ballon
  est arrêté ou marqué. Aucune carte de compte rendu (bannière de verdict, chiffres
  du tir) n'a le droit d'y être. Elles vont dans la bande haute ou dans la bande
  basse, et la bannière choisit laquelle en **projetant le centre de la bouche du
  but avec la caméra courante** : bouche haute dans l'image (caméra derrière le
  tireur) -> carte en bas ; bouche basse (caméra depuis l'intérieur du but, celle
  de tous les buts) -> carte en haut. La bande haute réserve la place du tableau
  de 2.24, qui clignote sur les mêmes secondes.
- **Le match se joue de jour.** Les fonds des plaques sont quasi opaques. Une
  plaque qui laisse passer un quart d'une pelouse en plein soleil rend une bouillie
  verte avec le gazon lisible entre les lettres. La fenêtre de frappe est verte
  elle aussi : sur du gazon elle sert de camouflage, d'où la carte **opaque** du
  module de puissance, qui porte aussi ses propres libellés au lieu de les poser
  sur l'herbe.
- **Puissance et précision sont deux instruments, jamais un seul.** Ils tenaient
  sur une même piste de 26 pixels (un remplissage, une fenêtre verte allumée, un
  curseur qui balaye), et le joueur ne pouvait pas dire lequel des trois voulait
  dire quoi : il *devinait* ce que faisait le curseur. La carte porte donc deux
  langages visuels distincts, et chacun **dit la vérité sur le modèle de tir** :
  - **PUISSANCE** est une barre remplie, une *quantité*, avec la vitesse en km/h
    en direct. Une graduation en km/h court dessous : elle est régulière **en
    vitesse**, donc irrégulière **le long de la barre**, et cet écartement *est*
    la concavité de `ShotModel.speed_for_power`. La portion où un pas de barre
    achète moins de la moitié de ce que les premiers pas achetaient est hachurée
    et nommée « GAIN FAIBLE ». Le seuil est **mesuré** sur `speed_for_power`, il
    n'est jamais écrit en dur : retoucher le modèle retouche le dessin.
  - **PRÉCISION** est une piste fine à curseur, un *instant*. Son fond est
    `ShotModel.contact_quality` échantillonné colonne par colonne, donc les
    épaulements ambrés autour de la porte verte sont la vraie qualité de frappe.
    La porte reste une **porte allumée** (corps plein, montants, halo qui déborde,
    et elle s'éclaircit quand le curseur est dedans) et elle est libellée
    « RELÂCHEZ ICI ». Elle est volontairement **plus étroite** que la barre de
    puissance et centrée : deux pistes de même largeur superposées suggèrent
    d'aligner le curseur sur le remplissage, ce qui n'a aucun sens.
- **Le HUD s'anime en secondes RÉELLES** (`Time.get_ticks_msec`), jamais sur le
  `delta` d'image. Le `delta` est mis à l'échelle par `Engine.time_scale` (la
  frappe descend à 0.55) et écrêté : un fondu piloté par lui n'avance presque pas
  sur une machine qui perd des images, et tout le HUD est derrière ce fondu.

#### Le côté gardien : l'enveloppe est l'instrument principal

Quand le joueur garde (mode DUEL, 2.9), le HUD change d'instrument. Quatre règles
de plus, du même rang que les quatre ci dessus.

- **L'ENVELOPPE A LE DROIT D'ÊTRE AU MILIEU DE L'IMAGE, et elle est la seule.**
  La première règle ci dessus interdit le centre aux cartes de compte rendu parce
  que le centre appartient à la bouche du but. L'enveloppe **est** la bouche du
  but : c'est le dessin de ce que le corps du joueur couvre encore, projeté sur
  le cadre lui même. La mettre ailleurs reviendrait à demander au joueur de
  regarder deux endroits à la fois pendant les quatre dixièmes de seconde où il
  n'a le temps d'en regarder qu'un.
- **Elle RÉTRÉCIT, visiblement, et c'est tout le mode.** Elle est redessinée à
  chaque image depuis `KeeperInput.reach_outline`, donc elle ne peut pas mentir
  sur la règle. Le joueur doit **voir** le cercle se refermer pendant la course
  d'élan et se refermer plus vite pendant le vol, parce que c'est cette image qui
  lui apprend, sans une ligne de texte, qu'attendre coûte. C'est la chose la plus
  importante de l'écran pendant `LECTURE` et rien n'a le droit de la recouvrir.
- **Les indices sont des indices, jamais des chiffres.** `TakerAi.tells_at` rend
  des valeurs bruitées, et le HUD les dessine **comme telles** : une inclinaison,
  une flèche, une largeur, jamais « visée : 2.1 m ». Un nombre affiché est lu
  comme une vérité, et ce module n'en a aucune à donner. Un indice faiblement
  fiable se dessine **plus flou**, pas plus petit : le joueur doit distinguer
  « je ne sais pas » de « il ne va pas là ».
- **L'invite d'engagement dit QUAND, pas OÙ.** Elle annonce que la fenêtre est
  ouverte et à quel point elle se ferme, et elle ne suggère jamais un côté.

#### Comment ces quatre règles sont tenues à l'écran

Quatre décisions de dessin en découlent. Elles sont ici parce qu'un autre module
en dépend, pas pour décrire des pixels.

- **Le fantôme de l'enveloppe.** Le trait vif est l'enveloppe **maintenant** ; un
  trait pointillé pâle derrière lui est **la même enveloppe 0.40 s plus tôt**.
  L'écart entre les deux est la vitesse à laquelle la fenêtre se ferme, et c'est
  la seule partie du rétrécissement qui survive à une image **figée** : en
  mouvement le joueur voit le cercle se refermer, sur une capture il voit de
  combien. Il n'y a **que ces deux traits** : un troisième contour intérieur avait
  l'air d'un instrument et rendait le trait vif indistinct.
- **La couverture est GELÉE à l'engagement.** `set_reach` ignore le `coverage`
  reçu tant que `committed` est vrai. Un gardien parti ne couvre pas une part
  décroissante du but, il couvre **celle qu'il a choisie en partant** : c'est le
  chiffre avec lequel il a décidé, et c'est celui qui vaut encore d'être lu
  pendant que le ballon vole. L'orchestrateur peut donc envoyer ce qu'il veut
  (`Main` envoie zéro et une enveloppe vide), l'anneau garde la vérité du pari.
- **Les schémas du panneau d'indices sont en MIROIR.** Le gardien regarde vers
  +Z, donc **+X est à sa gauche** et apparaît à **gauche de l'écran** (2.21). Le
  plan de la course d'élan et la miniature de la bouche du but sont donc dessinés
  x inversé. Un schéma non miroir décrirait un autre penalty que celui qui est à
  l'écran.
- **Ce que le HUD lit de `TakerAi.tells_at`, et ce qu'il refuse de lire.** Il ne
  dessine que le **langage du corps** : `run_angle` (l'angle de la course, en
  éventail dont l'ouverture est l'incertitude), `plant_offset` (le pied d'appui,
  avec sa bavure latérale), `hip_yaw` (la barre des hanches), `approach_speed`
  (les chevrons d'allure), `feints` (le seul indice qui soit un **compte**, donc
  le seul écrit en toutes lettres) et `confidence`, qui ne se dessine pas : c'est
  lui qui **élargit** tous les autres. `aim_hint`, `lift_hint` et `power_hint`
  sont **délibérément ignorés** : ce sont des lectures déjà faites, et les
  afficher reviendrait à jouer le mode à la place du joueur. Une clé **absente**
  n'est pas dessinée, ce qui est exactement le bon message : le panneau se remplit
  pendant la course d'élan, et le joueur voit l'information arriver.
  Le seul endroit où le HUD **interprète** est la bande de tendance en haut du
  panneau : une bavure large d'au moins 0.85 m sur une miniature du but à
  l'échelle, pondérée `0.72` pied d'appui, `0.52` hanches, `0.44` course. C'est un
  **pressentiment**, il a souvent tort, et il n'est jamais un chiffre.
  Convention de signe, celle de `ShotModel.tell_cues` : un indice **positif** dit
  « vers +X ».

```gdscript
class_name Hud
extends CanvasLayer

func build() -> void
## Aim reticle position and legality.
func set_aim(aim: Vector2, world_point: Vector3, on_target: bool) -> void
## Power bar state. `marker` is the sweeping precision cursor.
func set_charge(power: float, marker: float, sweet_centre: float, visible_bar: bool) -> void
func set_spin(side: float, lift: float) -> void
## The predicted flight, in world space. Empty hides the arc.
func set_preview(points: PackedVector3Array) -> void
## The camera used to project world points to the screen.
func set_camera(camera: Camera3D) -> void
## Big centred verdict banner. Empty text hides it.
func show_verdict(verdict: int, detail: String) -> void
## Post shot figures: speed in km/h, curve in cm, contact quality.
func show_shot_stats(speed_kmh: float, curve_cm: float, quality: float) -> void
## Refreshes the shootout markers and the pressure line.
func refresh_series() -> void
## Fades the whole HUD, for the replay and the menus.
func set_dimmed(dimmed: bool) -> void
## Transient message, centred, in French.
func toast(text: String, seconds: float = 2.0) -> void

## --- Côté gardien, mode DUEL (voir plus haut) --------------------------------

## Switches the whole HUD between the taking instruments (reticle, power, spin,
## arc) and the keeping ones (envelope, tells, commit prompt, line strip). One
## call, because the two sets are mutually exclusive and half of each is a mess.
## Switching CLEARS the set that leaves, so no arc and no envelope can survive
## into the other half of the duel. Only the change does anything: called every
## frame it would wipe the envelope's ghost before every redraw.
func set_keeper_side(keeping: bool) -> void
## The reach envelope, in WORLD space: the closed ring KeeperInput.reach_outline
## returned, plus how much of the mouth it still covers (0..1) and whether the
## dive is already launched. An empty outline hides it. Called every frame: this
## is the drawing that has to shrink in front of the player.
## `coverage` is IGNORED while `committed`: see "la couverture est gelée" above.
func set_reach(outline: PackedVector3Array, coverage: float, committed: bool) -> void
## Where the player is aiming his dive and whether it is still inside the
## envelope. `target` is the world point KeeperInput.dive_target gave, `margin`
## the seconds to spare from KeeperInput.margin, which is what colours it.
func set_dive_aim(target: Vector3, margin: float) -> void
## The taker's body language as the player is ALLOWED to read it: the dictionary
## TakerAi.tells_at returned, nothing else, never the plan. Empty hides the panel.
func set_tells(cues: Dictionary) -> void
## The commit prompt. `open` is whether pressing does anything at all, `urgency`
## 0..1 how far the window has closed. Says when, never where.
func set_commit_prompt(open: bool, urgency: float) -> void
## Where the keeper stands on his line, in metres, and the bound he may travel to
## (KeeperInput.LINE_LIMIT). Drawn as a strip under the goal, so the shuffle is
## legible without moving the camera.
func set_line_position(line_x: float, limit: float) -> void
```

---

### 2.24 `src/ui/scoreboard.gd` - `class_name Scoreboard` extends Control

Le tableau de la séance : les deux séries de pastilles, le score, la ligne de
pression ("Marquez pour gagner"), et l'écran de fin. Dessiné en `_draw`.

#### En DUEL, les deux rangées sont des RÔLES et non deux équipes

Le tableau ne change pas de forme, il change de **légende**. `Mode.DUEL` ouvre les
deux rangées comme `Mode.SEANCE`, et la seconde porte toujours `rival_scores` :
un tour que le joueur a **gardé** est un tour que l'ordinateur a **tiré**, c'est
la même case. Ce qui change est ce qui est écrit dessus, parce qu'en duel les
deux rangées sont le joueur, et un tableau qui dirait « VOUS » et « ADVERSAIRE »
mentirait sur la moitié de la séance :

- rangée haute « **VOUS TIREUR** », badge ballon ;
- rangée basse « **VOUS GARDIEN** », badge gant.

Le reste est inchangé et suffit : `rival_to_kick()` reste la seule réponse à « à
qui le tour », donc la rangée éclairée et le chevron désignent déjà le rôle du
tour qui vient, et `pressure_text()` le dit en toutes lettres depuis le côté du
joueur. La chronologie se lit sans numéroter quoi que ce soit, puisque les tours
alternent : la n-ième pastille de chaque rangée est le n-ième tour de ce rôle.

L'écran de fin ajoute une ligne que seul ce mode peut écrire : **« Arrêts : N sur
M »**, comptés sur `Verdict.ARRET` dans `rival_scores`. C'est le travail du joueur
comme gardien, et c'est la moitié du duel que le score seul ne raconte pas.

```gdscript
class_name Scoreboard
extends Control

func build() -> void
func refresh() -> void
## Slides in for a moment between two shots, then slides out.
func flash(seconds: float = 2.2) -> void
## Full screen end of match panel.
func show_result(player_won: bool) -> void
func hide_result() -> void
```

---

### 2.25 `src/ui/menu.gd` - `class_name MenuUi` extends Control

L'accueil, la pause et les réglages. Dessiné en `_draw`, navigable au clavier et
à la souris. C'est aussi lui qui affiche les commandes.

Deux règles de mise en page :

- **Rien ne flotte sur la pelouse.** La ligne d'aide de la rangée sélectionnée et
  la liste des touches sont sur une **plaque amarrée sous la carte**, de sa
  largeur, et non posées en blanc translucide au bas de l'image. Le fond des
  plaques est quasi opaque, pour la même raison qu'en 2.23.
- **Pas de fondu d'ouverture.** Un écran affiché est un écran qu'on lit. En prime
  l'orchestrateur a le droit de redemander la page déjà ouverte : `open_home()`
  sur la page courante ne réinitialise donc **ni** le focus **ni** l'animation.

L'accueil propose désormais **cinq** modes, `Shootout.Mode` au complet, libellés
par `Shootout.mode_label`. `mode_chosen` ne change pas : elle porte déjà un entier
et `Mode.DUEL` comme `Mode.GARDIEN` en sont. La ligne d'aide de la rangée « Duel »
doit dire ce que le mode fait, parce qu'il est le seul dont le nom ne l'annonce
pas : « Vous tirez, puis vous gardez : les rôles alternent. »

« Entraînement gardien » se range **sous Duel** et non sous Entraînement, parce
que c'est le Duel qu'il entraîne : un joueur qui vient de se faire battre cinq
fois dans les gants cherche la réponse à côté du mode qui l'a battu.

Le côté gardien ne déclare **aucune touche** nouvelle (2.26) : les trois entrées
du tireur changent de métier. La page **Commandes** ne les liste pas pour autant.
Elle porte à leur place une rangée d'action, **« Duel, gardien : touches et
règles »**, qui ouvre une page à elle (`PAGE_KEEPER`, titre `GARDIEN`) où les
trois entrées figurent en tête de l'explication.

**La hauteur de la page est un budget, pas un détail.** Elle est mesurée depuis le
nombre de rangées, et à 900 px de référence quinze rangées sont tout ce qu'elle
peut prendre. Les trois lignes gardien plus la rangée d'action en faisaient
seize : « Retour » sortait par le bas et la plaque de pied de page disparaissait
entièrement de l'écran. Avant d'ajouter une rangée ici, la regarder.

**Les touches n'ont jamais été la difficulté.** Elles sont trois, ce sont celles
du tireur, et elles figurent déjà dans la liste au-dessus. Ce qu'un joueur qui
arrive dans un tour gardé ignore, c'est ce qu'est l'anneau bleu, pourquoi il
rétrécit sous ses yeux, et que le mode est construit pour qu'**attendre de savoir
soit perdre**. Rien de tout cela ne se lit sur une liste de touches, et un joueur
à qui on ne l'a pas dit joue le tour comme un test de réflexes, le perd, et en
conclut que le gardien est cassé.

La page réutilise les deux colonnes de `CONTROLS` et n'a donc **pas de peintre à
elle** : à gauche ce que le joueur VOIT, à droite ce que ça VEUT DIRE. Sa carte
est un peu plus large que celle des touches, parce que sa colonne de droite porte
des phrases et non des noms de touches. Elle se rejoint depuis les Commandes et
d'un seul endroit, donc `_back` y code son retour en dur au lieu de toucher à
`_return_page`, qui retient encore d'où la liste des touches a été ouverte.

Les trois nombres qu'elle cite sont les vrais et ne sont pas décoratifs :
`KeeperInput.NOMINAL_FLIGHT`, le temps de réaction que `KeeperBrain` paie, et un
plongeon complet jusqu'au poteau.

```gdscript
class_name MenuUi
extends Control

signal mode_chosen(mode: int)
signal resume_requested()
signal restart_requested()
signal quit_requested()

func build() -> void
func open_home() -> void
func open_pause() -> void
func open_settings() -> void
func close() -> void
func is_open() -> bool
```

---

### 2.26 `src/main.gd` - `class_name Main` extends Node3D

L'orchestrateur. Il possède la machine à états du tir, câble tous les signaux,
et c'est **le seul** module autorisé à faire dialoguer les autres.

Champs publics, requis par `tests/smoke_probe.gd` :

```gdscript
class_name Main
extends Node3D

var pitch: Pitch
var stadium: Stadium
var goal_frame: GoalFrame
var ball: Ball
var keeper: Keeper
var shooter: Shooter
var rig: CameraRig
var sky: SkyController
var crowd: Crowd
var hud: Hud
var scoreboard: Scoreboard
var menu: MenuUi

## Milliseconds at boot, so the probe can reason about elapsed time.
var boot_msec: int
## The verdict of the last resolved shot, a Shootout.Verdict.
var last_verdict: int
## The last strike dictionary produced by ShotModel.resolve.
var last_shot: Dictionary

## The plan TakerAi.choose produced for the round the player is keeping, and the
## dive KeeperInput.commit produced from his own press. Both empty outside a
## keeper side round, and both are what the probe reads to prove the mode ran.
var last_taker: Dictionary
var last_dive: Dictionary

## Real seconds the tree keeps ticking, mixer silent, before the process exits.
## Voir `Sfx.silence_all` : une voix arretee reste enregistree dans le serveur
## audio pendant quelques images, et un `quit()` immediat la laisse derriere lui.
## Mesure sur le pilote muet de `--headless` : 0 ms fuit toujours, 50 ms est
## instable, 100 ms est toujours propre. La constante vaut le triple.
const AUDIO_DRAIN_SECONDS := 0.35

## Forces a whole shot from code, bypassing the input. The probe uses it to fire
## reproducible penalties. Returns the strike dictionary.
func fire_test_shot(aim: Vector2, power: float, side: float, lift: float) -> Dictionary
## Forces a whole KEEPER side round from code, the mirror of fire_test_shot: the
## CPU taker of `rng_seed` kicks, and the player keeper standing at `line_x`
## commits at `commit_t` (seconds relative to contact, negative before it) to the
## dive `aim` asks for. Plays out the real flight against the real save test, so
## the probe measures the mode rather than a re-implementation of it.
## Returns {"verdict": int, "taker": Dictionary, "dive": Dictionary,
##          "saved": bool, "catch": bool, "coverage": float}
## THE DICTIONARY IS THE LIVE ONE. A penalty has no verdict until it has been
## played, and playing it takes a second of real physics, so this call LAUNCHES
## the round and hands back the dictionary it will fill in. Godot dictionaries are
## references: the caller keeps the handle and reads it once the flight has
## settled (`_probe_shot_settled`). "verdict" is -1 until then, the same "no
## verdict yet" the rest of this file uses. `pressure` is deliberately false
## rather than read off the series, so one seed is one penalty whatever the score
## was at the time.
func fire_test_duel(rng_seed: int, aim: Vector2, commit_t: float, line_x: float) -> Dictionary
## Jumps straight to a phase, for the probe.
func force_phase(phase: int) -> void
## Fait taire le mixeur puis quitte une fois que le serveur audio a vraiment
## lache ses voix. C'est LE SEUL chemin de sortie du jeu : les sondes de
## `tests/` ne doivent plus appeler `SceneTree.quit()` elles memes, elles
## passent par `_main.call("quit_clean", code)`. Idempotent, et sur d'emploi
## depuis un arbre en pause.
func quit_clean(code: int) -> void
```

Séquence d'une phase, gérée par `Main` :

| Phase | Entrée | Sortie |
|---|---|---|
| `ACCUEIL` | menu ouvert, caméra TELE | un mode est choisi |
| `PLACEMENT` | ballon sur le point, gardien sur sa ligne, caméra DERRIERE | 0.8 s écoulées |
| `VISEE` | le tireur prend la main | `strike` relâché |
| `COURSE` | course d'élan, le gardien lit | contact |
| `VOL` | le ballon vole, le gardien plonge | verdict atteint ou ballon au repos |
| `VERDICT` | banderole, réaction de la foule, score | 2.2 s écoulées |
| `REPLAY` | orbite sur le vol **et** le plongeon enregistrés, depuis la course d'élan | fin du replay ou touche |
| `FIN` | tableau de résultat | rejouer ou quitter |

#### Le tour où le joueur garde (mode DUEL)

Deux phases de plus, et **deux seulement**. Elles remplacent `PLACEMENT`, `VISEE`
et `COURSE` ; `VOL`, `VERDICT` et `REPLAY` sont **repris tels quels**, et c'est
voulu : un ballon en vol, un verdict et un replay sont les mêmes objets des deux
côtés du duel, et les doubler serait deux fois le même code avec un bug de
décalage dans l'un des deux.

| Phase | Entrée | Sortie |
|---|---|---|
| `PLACEMENT_GARDIEN` | ballon sur le point, joueur au milieu de sa ligne, caméra GARDIEN, **la danse sur la ligne est déjà rendue au joueur** | 0.8 s écoulées |
| `LECTURE` | le tireur CPU est choisi (`Shootout.duel_taker_plan`), la course d'élan se joue, les indices fuient image par image, la danse continue, l'engagement est autorisé | contact |
| `VOL` | le ballon vole, le plongeon du joueur se déroule, le test d'arrêt est celui de `Keeper` | verdict atteint ou ballon au repos |
| `VERDICT` | banderole, foule, score, `take_rival_kick_played` | 2.2 s écoulées |

**Le plan est choisi à l'entrée de `LECTURE` et pas plus tôt**, et c'est ce qui
donne des dents à la danse sur la ligne. `TakerAi.read_keeper` veut la position du
gardien « quand le tireur pose son pied d'appui », mais la course d'élan elle même
est dessinée à partir du plan : il faut donc le connaître avant de la lancer. Le
seul instant qui satisfasse les deux est **le dernier regard du tireur avant de se
retourner**, c'est à dire l'instant où la course commence. Le joueur passe donc
`PLACEMENT_GARDIEN` à choisir son coin de ligne, le tireur le lit là, et pendant
`LECTURE` le joueur peut encore bouger : cela ne change plus l'intention du tireur
(elle est prise), seulement son **enveloppe** à lui, ce qui est le vrai marché.

**Ce que le joueur a le droit de savoir sur l'arrivée du ballon.** Avant la
frappe, `KeeperInput.NOMINAL_FLIGHT`, parce que personne ne peut savoir mieux.
Après la frappe, le **vrai temps de vol restant**, calculé une fois par
`Aero.cross_plane` sur la frappe réelle : le joueur voit le ballon, donc le lui
donner est honnête, et c'est ce qui referme l'enveloppe bien plus vite sur une
mine que sur une casserole.

**Le plongeon n'est pas une phase, et c'est structurel.** Un gardien qui parie
part **avant** le contact : son plongeon commence donc dans `LECTURE` et se
termine dans `VOL`, à cheval sur la frappe, exactement comme `Keeper.pose_log`
enregistre des `t` négatifs depuis toujours. En faire une phase obligerait à
l'entrer deux fois, ou à interdire l'engagement anticipé, qui est le mécanisme
central du mode.

**Le clavier et la souris changent de rôle, pas de nom.** Aucune action nouvelle
n'est déclarée dans `Game` (2.8) : `strike` engage le plongeon, la souris déplace
la cible de plongeon au lieu du réticule de tir, `aim_left` / `aim_right` sont la
danse sur la ligne. Un mode qui ajouterait quatre touches à apprendre pendant
qu'on regarde un tireur courir n'en serait pas un.

**Ce que `Main` a le droit de transmettre, et rien d'autre.** Le plan du tireur
(`Shootout.duel_taker_plan`) reste **dans `Main`** jusqu'au contact. Ce qui
descend vers `Hud` est `TakerAi.tells_at`, jamais le plan ; ce qui descend vers
`TakerAi.read_keeper` est le `line_x` du gardien, jamais sa cible de plongeon ni
son engagement. C'est l'orchestrateur qui tient les deux règles d'équité de 2.12a
et 2.12b, parce que c'est le seul module qui voie les deux côtés à la fois.

---

## 3. Tests

`tests/test_case.gd` (`class_name GoalTest`) et `tests/run_tests.gd` existent
déjà, ne les modifie pas. Chaque suite hérite de `GoalTest`, expose des méthodes
`test_*`, et **chaque méthode finit par `done()`**.

Rappel : une suite ne doit **jamais** nommer `Game`, `Shootout` ni `Sfx`, sinon
elle ne compile pas sous `--script`.

| Fichier | Couvre |
|---|---|
| `tests/test_layers.gd` | `Layers` : bits distincts, masques cohérents |
| `tests/test_palette.gd` | `Palette` : bande d'albédo respectée, helpers |
| `tests/test_pitch_geometry.gd` | `Field` : dedans/dehors, poteaux, balayage |
| `tests/test_aero.gd` | `Aero` : conservation, traînée, Magnus, visée inverse |
| `tests/test_keeper_brain.gd` | `KeeperBrain` : réaction, allonge, arrêts, déterminisme |
| `tests/test_keeper_input.gd` | `KeeperInput` : enveloppe décroissante, jamais tout le but, danse bornée |
| `tests/test_taker_ai.gd` | `TakerAi` : plans figés par graine, réticule inverse, indices bruités |
| `tests/test_match_state.gd` | logique de séance **recopiée** dans la suite, pas l'autoload |
| `tests/test_meshes.gd` | `Meshes` : normales, tangentes, comptes de sommets |
| `tests/test_sfx_lib.gd` | `SfxLib` : tous les ids, fondu de sortie, boucle unique |
| `tests/test_shot_model.gd` | `ShotModel` : bornes, qualité, déterminisme |
| `tests/test_net.gd` | maths du filet **recopiées**, pas le noeud |
| `tests/balance_probe.gd` | sonde d'équilibrage en jeu (mesure, n'assertit pas) |

`tests/smoke_probe.gd` tourne dans le vrai jeu :
`godot --headless --path . -- --smoke`. Il tire une série de penalties
reproductibles via `Main.fire_test_shot` et vérifie les invariants : un tir dans
la lucarne à pleine puissance contre un débutant est un but, un tir au centre
mou contre une légende est arrêté, la somme des verdicts est cohérente avec le
score, le filet bouge quand le ballon entre, aucune trajectoire ne part à
l'infini.

Il couvre aussi le mode DUEL, par `Main.fire_test_duel`, et sur les invariants du
mode plutôt que sur son décor : un plongeon engagé tôt dans le bon coin arrête un
penalty placé, le même plongeon engagé trop tard ne l'arrête pas, une lucarne bien
frappée passe quel que soit l'engagement, un tour gardé fait grandir
`rival_scores` d'exactement une case, et deux exécutions de la même graine rendent
le même verdict.

`tests/balance_probe.gd` tourne lui aussi dans le vrai jeu :
`godot --headless --path . -- --balance`. Il ne vérifie rien, il **mesure** :
il tire un échantillon uniforme sur toute la surface du but, à quatre puissances,
en frappe propre et en casserole, contre les quatre niveaux, puis imprime les
taux d'arrêt, de but, de poteau et de hors cadre par niveau, par qualité de
frappe et par placement. Chaque taux est imprimé avec sa **bande à deux sigma**,
parce que sans elle un écart de bruit se lit comme une régression. Trois options
facultatives : `--balance-repeats N` (répétitions par case), `--balance-live N`
(0 désactive l'échantillon tiré réellement via `Main.fire_test_shot`, qui sert à
prouver que le modèle hors ligne dit la même chose que le jeu) et
`--balance-seed K` (**un autre tirage des mêmes distributions** ; plusieurs
valeurs de K sont des échantillons indépendants, lançables en parallèle, et c'est
la seule façon d'obtenir un chiffre publiable, voir 2.9).

## 4. Ce qui fait la qualité de ce jeu

Trois choses portent tout le reste. Si tu écris un de ces modules, soigne le.

1. **L'aérodynamique.** La traînée et l'effet Magnus, pour de vrai. Un ballon qui
   décrit une parabole est un ballon mort.
2. **Le gardien.** Il ne triche pas, il lit et il parie. On doit pouvoir le
   feinter, et il doit parfois deviner juste et sortir un arrêt réflexe.
3. **Le filet.** L'onde qui part du point d'impact est la récompense du but.
