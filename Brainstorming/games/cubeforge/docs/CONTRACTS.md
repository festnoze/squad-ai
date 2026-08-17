# CUBEFORGE - contrats d'API

Ce document est la source de vérité. Chaque module est écrit indépendamment par
un agent différent, donc toute signature listée ici est **obligatoire** : ne
renomme rien, n'ajoute pas de paramètre, ne change pas un type de retour. Tu
peux ajouter des membres privés (préfixe `_`) et des helpers autant que tu veux.

## 0. Règles du projet

- Godot **4.7.1**, GDScript typé statiquement partout où c'est possible.
- **Zéro asset binaire.** Textures, sons et maillages sont générés par code au
  démarrage. Le seul fichier non-code est `icon.svg`.
- Aucun `class_name` en doublon. Utilise exactement celui indiqué.
- Le texte affiché au joueur est en **français**. Le code, les noms de symboles
  et les commentaires sont en **anglais**.
- **N'utilise jamais le caractère tiret cadratin** dans aucun fichier. Utilise
  un tiret simple ou des parenthèses.
- Pas de `print()` laissé dans le code de production. Pour un diagnostic
  utilise `push_warning()` ou `push_error()`.
- Vérifie ton fichier avec :
  `godot --headless --path . --check-only --script res://<chemin>.gd`
  Il doit sortir en code 0 sans `SCRIPT ERROR`.

## 1. Repères et constantes

Un bloc occupe le cube unité. Le bloc de cellule `(x, y, z)` s'étend de
`(x, y, z)` à `(x+1, y+1, z+1)` en coordonnées monde. Y est vertical.

Un chunk est une colonne complète de `16 x 96 x 16`. La hauteur du monde tient
dans un seul chunk, donc il n'y a **jamais** de streaming vertical : seul
l'anneau horizontal autour du joueur bouge.

| Constante | Valeur | Source |
|---|---|---|
| `ChunkData.SIZE_X` | 16 | `src/world/chunk_data.gd` |
| `ChunkData.SIZE_Y` | 96 | idem |
| `ChunkData.SIZE_Z` | 16 | idem |
| `ChunkData.SEA_LEVEL` | 48 | idem |

Le chunk `(cx, cz)` couvre les x monde `cx * 16 .. cx * 16 + 15`.
Conversion monde vers chunk : division entière **plancher** (attention aux
négatifs, `-1 / 16` vaut 0 en GDScript alors qu'il faut -1). Utilise
`VoxelWorld.chunk_of()` et `VoxelWorld.local_of()`.

Ordre des faces du cube, fixe dans tout le projet :

| Index | Nom | Normale |
|---|---|---|
| 0 | `Blocks.FACE_PX` | `+X` |
| 1 | `Blocks.FACE_NX` | `-X` |
| 2 | `Blocks.FACE_PY` | `+Y` (dessus) |
| 3 | `Blocks.FACE_NY` | `-Y` (dessous) |
| 4 | `Blocks.FACE_PZ` | `+Z` |
| 5 | `Blocks.FACE_NZ` | `-Z` |

## 2. Modules déjà écrits (à lire, pas à modifier)

### `src/core/blocks.gd` - `class_name Blocks`

Registre statique. Ne le modifie pas. API disponible :

```gdscript
Blocks.AIR, Blocks.STONE, Blocks.GRASS, ...          # ids (voir enum, Blocks.COUNT au total)
Blocks.Kind.{EMPTY,SOLID,CUTOUT,CROSS,TRANSLUCENT,LIQUID}
Blocks.Surface.{OPAQUE,CUTOUT,TRANSLUCENT,WATER}     # 0..3, Blocks.SURFACE_COUNT == 4
Blocks.TILE_NAMES: PackedStringArray                 # 53 noms, ordre = layers de l'atlas
Blocks.TILE_COUNT == 53
Blocks.TILE_PIXELS == 32                             # côté d'une tuile en pixels
Blocks.PALETTE: PackedByteArray                      # ordre de la palette créative

Blocks.kind_of(id) -> int
Blocks.surface_of(id) -> int
Blocks.tile_of(id, face) -> int                      # layer d'atlas
Blocks.tint_mask(id) -> int                          # bitmask BIT_PX..BIT_NZ des faces teintées
Blocks.is_air(id) -> bool
Blocks.is_opaque(id) -> bool                         # masque les faces voisines
Blocks.collides(id) -> bool
Blocks.is_liquid(id) -> bool
Blocks.is_cross(id) -> bool
Blocks.emission(id) -> float                         # 0..1
Blocks.is_light_source(id) -> bool
Blocks.hardness(id) -> float                         # secondes, négatif = incassable
Blocks.is_breakable(id) -> bool
Blocks.drop_of(id) -> int
Blocks.display_name(id) -> String
Blocks.is_replaceable(id) -> bool                    # air, liquide ou plante
Blocks.needs_support(id) -> bool                     # les plantes tombent sans sol
Blocks.draws_face(self_id, neighbour_id) -> bool     # test de visibilité du mesher
```

### `src/world/chunk_data.gd` - `class_name ChunkData extends RefCounted`

```gdscript
var cx: int
var cz: int
var voxels: PackedByteArray          # taille VOLUME == 24576
var solid_count: int
var modified: bool
var column_top: PackedInt32Array     # SIZE_X * SIZE_Z, index x * SIZE_Z + z, -1 si colonne vide

_init(chunk_x := 0, chunk_z := 0)
static local_index(x, y, z) -> int   # (x * SIZE_Z + z) * SIZE_Y + y
static in_bounds(x, y, z) -> bool
get_local(x, y, z) -> int            # hors bornes renvoie Blocks.AIR
set_local(x, y, z, id) -> bool       # maintient solid_count et column_top
set_local_raw(x, y, z, id) -> void   # rapide, sans bornes ni maintenance
fill_column(x, z, y_from, y_to, id) -> void   # bornes incluses, clampé
recompute_tops() -> void             # reconstruit solid_count et column_top
top_of(x, z) -> int
is_empty() -> bool
serialize() -> PackedByteArray       # RLE
deserialize(payload) -> bool
```

## 3. Contrat des données de sommets (mesher vers shaders)

C'est le point de couplage le plus délicat du projet. Le mesher et les shaders
doivent s'accorder au bit près.

Chaque surface d'`ArrayMesh` est un `Array` de taille `Mesh.ARRAY_MAX` dont
seuls ces emplacements sont remplis, les autres restent `null` :

| Emplacement | Type | Contenu |
|---|---|---|
| `Mesh.ARRAY_VERTEX` | `PackedVector3Array` | position **locale au chunk**, 0..16 en X/Z, 0..96 en Y |
| `Mesh.ARRAY_NORMAL` | `PackedVector3Array` | normale de face |
| `Mesh.ARRAY_TEX_UV` | `PackedVector2Array` | 0..1 **à l'intérieur de la tuile** |
| `Mesh.ARRAY_COLOR` | `PackedColorArray` | `rgb` = ombrage de face x lumière du ciel x AO x teinte de biome, `a` = émission 0..1 |
| `Mesh.ARRAY_CUSTOM0` | `PackedFloat32Array` | 4 flottants par sommet, voir ci-dessous |
| `Mesh.ARRAY_INDEX` | `PackedInt32Array` | triangles |

`CUSTOM0` par sommet : `x` = index de layer dans le `Texture2DArray`,
`y` = facteur d'ondulation au vent (0 = statique, 1 = plein vent),
`z` et `w` = 0 réservés.

L'upload se fait obligatoirement ainsi, sinon `CUSTOM0` est ignoré :

```gdscript
var flags := Mesh.ARRAY_CUSTOM_RGBA_FLOAT << Mesh.ARRAY_FORMAT_CUSTOM0_SHIFT
mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, flags)
```

Côté shader, `CUSTOM0` n'existe que dans `vertex()`. Passe l'index de tuile au
fragment via un `varying float`, et déclare `flat` si tu veux éviter toute
interpolation :

```glsl
varying flat float tile_layer;
void vertex() { tile_layer = CUSTOM0.x; }
void fragment() { vec4 t = texture(tiles, vec3(UV, tile_layer)); }
```

Ombrage directionnel de face à appliquer dans `ARRAY_COLOR` (le shader ne le
recalcule pas) : `+Y` 1.00, `-Y` 0.55, `+X` 0.86, `-X` 0.78, `+Z` 0.72,
`-Z` 0.66. Les quads croisés (`Kind.CROSS`) utilisent 1.00.

## 4. Modules à écrire

### 4.1 `src/core/game.gd` - autoload `Game extends Node`

Déclaré comme autoload dans `project.godot`, accessible par `Game.` partout.

```gdscript
signal settings_changed()

var mouse_sensitivity: float = 0.0022   # radians par pixel
var invert_y: bool = false
var fov: float = 78.0
var render_distance: int = 8            # en chunks, borné 3..16
var world_seed: int = 0                 # 0 = tirer au sort au premier lancement
var creative: bool = true
var sfx_volume: float = 0.8             # 0..1 linéaire
var show_debug: bool = false

func _ready() -> void                   # installe l'InputMap puis charge les réglages
func save_settings() -> void            # user://settings.cfg via ConfigFile
func load_settings() -> void
func reset_settings() -> void
```

`_ready()` doit enregistrer **par code** (jamais dans `project.godot`) toutes
les actions ci-dessous, en n'écrasant pas une action déjà présente. Utilise
`InputMap.has_action`, `InputMap.add_action`, `InputMap.action_add_event`, et
`physical_keycode` pour que les touches suivent la disposition physique
(un clavier AZERTY doit fonctionner comme un QWERTY sur ZQSD/WASD).

| Action | Entrées |
|---|---|
| `move_forward` | `KEY_W`, `KEY_UP` |
| `move_back` | `KEY_S`, `KEY_DOWN` |
| `move_left` | `KEY_A`, `KEY_LEFT` |
| `move_right` | `KEY_D`, `KEY_RIGHT` |
| `jump` | `KEY_SPACE` |
| `sprint` | `KEY_SHIFT` |
| `crouch` | `KEY_CTRL` |
| `fly_toggle` | `KEY_F` |
| `dig` | `MOUSE_BUTTON_LEFT` |
| `place` | `MOUSE_BUTTON_RIGHT` |
| `pick_block` | `MOUSE_BUTTON_MIDDLE` |
| `hotbar_next` | `MOUSE_BUTTON_WHEEL_DOWN` |
| `hotbar_prev` | `MOUSE_BUTTON_WHEEL_UP` |
| `hotbar_1` .. `hotbar_9` | `KEY_1` .. `KEY_9` |
| `inventory` | `KEY_E` |
| `debug_overlay` | `KEY_F3` |
| `pause` | `KEY_ESCAPE` |
| `screenshot` | `KEY_F2` |
| `time_forward` | `KEY_T` |

### 4.2 `src/render/atlas.gd` - `class_name VoxelAtlas`

Génère les 53 tuiles de `Blocks.TILE_NAMES` **par code**, en pixel art
`32 x 32`, et les empile dans un `Texture2DArray`. L'index de layer doit être
exactement l'index dans `Blocks.TILE_NAMES`.

```gdscript
## Construit le Texture2DArray complet. Coûteux (appelé une fois au démarrage).
static func build() -> Texture2DArray

## Image RGBA8 32x32 d'une tuile nommée, utile pour les aperçus 2D de l'interface.
static func tile_image(tile_name: String) -> Image

## Aperçu 2D d'un bloc pour la barre d'action et l'inventaire. Renvoie une
## ImageTexture carrée de `size` pixels, agrandie au plus proche voisin, tirée
## de la face de dessus pour les cubes.
static func block_preview(block_id: int, size: int = 48) -> ImageTexture
```

Le `Texture2DArray` doit être créé avec des mipmaps (`Image.generate_mipmaps()`
sur chaque calque avant `create_from_images`) : le filtrage anisotrope du
shader s'appuie dessus pour éviter le moiré à distance.

Tuiles à alpha nul partiel obligatoires : `glass` (cadre opaque, centre
totalement transparent), `oak_leaves`, `birch_leaves`, `pine_leaves` (feuillage
troué), `grass_tuft`, `fern`, `dead_bush`, `flower_red`, `flower_yellow`,
`sapling`, `torch` (silhouette sur fond transparent). Toutes les autres tuiles
sont opaques (alpha 255 partout).

Les tuiles teintées par biome (`grass_top`, `oak_leaves`, `birch_leaves`,
`grass_tuft`, `fern`, `sapling`) doivent être dessinées en **niveaux de gris
clairs proches du blanc** (luminance 0.65 à 1.0) parce que le vertex color les
multiplie. Les autres tuiles portent leur couleur définitive.

Qualité attendue : chaque tuile a du grain, pas d'aplat uni. Pour `stone` par
exemple, un bruit de valeur doux plus quelques éclats sombres ; pour
`cobblestone`, des galets distincts avec des joints sombres ; pour `brick`, un
appareil régulier avec mortier. Les tuiles doivent être **carrelables**
(tileable) : le bord droit doit raccorder le bord gauche, idem haut/bas.
Utilise un générateur déterministe (`RandomNumberGenerator` avec une graine
fixe par tuile) pour que le résultat soit identique à chaque lancement.

### 4.3 `src/render/materials.gd` - `class_name VoxelMaterials` et les 4 shaders

```gdscript
## Renvoie un Array de Blocks.SURFACE_COUNT ShaderMaterial, indexé par
## Blocks.Surface. Charge les .gdshader et branche l'atlas.
static func build(atlas: Texture2DArray) -> Array[Material]

## Matériau du contour de sélection de bloc (lignes noires, non éclairé,
## rendu par dessus la géométrie).
static func outline_material() -> Material

## Propage l'heure du jour aux matériaux qui en ont besoin (eau, vent).
static func set_time(materials: Array[Material], t: float) -> void

## Facteur global d'ondulation au vent, 0 pour figer.
static func set_wind(materials: Array[Material], strength: float) -> void
```

Fichiers à écrire dans `src/render/shaders/` :

- `voxel_opaque.gdshader` : `render_mode cull_back;`. Échantillonne
  `sampler2DArray tiles` avec
  `filter_nearest_mipmap_anisotropic, repeat_disable`.
  `ALBEDO = tex.rgb * COLOR.rgb;`
  `EMISSION = tex.rgb * COLOR.a * 2.5;`
  `ROUGHNESS = 1.0; SPECULAR = 0.0;` (le voxel mat évite les reflets plastique).
  Applique l'ondulation `CUSTOM0.y` sur `VERTEX` avec `TIME`.
- `voxel_cutout.gdshader` : comme l'opaque plus
  `render_mode cull_disabled, depth_prepass_alpha;` et
  `ALPHA = tex.a; ALPHA_SCISSOR_THRESHOLD = 0.5;`. C'est la surface du
  feuillage, du verre et des plantes, donc l'ondulation est essentielle ici.
- `voxel_translucent.gdshader` : `render_mode cull_back, blend_mix,
  depth_draw_opaque;` `ALPHA = tex.a * 0.72;` pour la glace.
- `voxel_water.gdshader` : `render_mode cull_disabled, blend_mix,
  depth_draw_opaque;`. Déplacement vertical de `VERTEX.y` par somme de deux
  sinus en fonction de `TIME` et de la position monde (amplitude 0.045),
  teinte bleu vert, `ALPHA` autour de 0.72, un peu de Fresnel via `NORMAL` et
  `VIEW` pour éclaircir les bords, `ROUGHNESS = 0.05`, `SPECULAR = 0.6`.
  L'eau doit rester visible depuis le dessous (d'où `cull_disabled`).

Tous les shaders reçoivent l'uniforme `uniform sampler2DArray tiles`.
Ajoute `uniform float wind_strength = 1.0;` là où l'ondulation existe.

### 4.4 `src/world/terrain.gd` - `class_name TerrainGen extends RefCounted`

**Contrainte de parallélisme :** une instance est créée par thread de travail.
Une instance ne doit donc contenir que de l'état construit dans `_init` et
jamais muté ensuite. `generate()` n'écrit que dans le `ChunkData` reçu. La
génération doit être **purement déterministe** à partir de la graine : deux
appels sur le même chunk donnent le même résultat, quel que soit l'ordre.

```gdscript
enum Biome { OCEAN, BEACH, PLAINS, FOREST, TAIGA, DESERT, SAVANNA, MOUNTAINS, TUNDRA, SWAMP }

const BIOME_NAMES: PackedStringArray = [
	"Océan", "Plage", "Plaines", "Forêt", "Taïga",
	"Désert", "Savane", "Montagnes", "Toundra", "Marais",
]

func _init(world_seed: int) -> void

## Remplit entièrement data (relief, grottes, minerais, eau, décor) puis
## appelle data.recompute_tops(). Utilise data.cx et data.cz.
func generate(data: ChunkData) -> void

## Hauteur du plus haut bloc de terrain plein d'une colonne, hors décor et
## hors eau. Fonction pure de (wx, wz), valable même pour un chunk non chargé.
func surface_height(wx: int, wz: int) -> int

func biome_at(wx: int, wz: int) -> int

## Teinte multiplicative de l'herbe et du feuillage. Doit varier doucement
## d'un biome à l'autre (interpole sur les bruits, pas de frontière franche),
## sinon les chunks montrent des coutures visibles.
func grass_color_at(wx: int, wz: int) -> Color

static func biome_name(b: int) -> String

## Point d'apparition sûr : au dessus du sol, hors océan, proche de l'origine.
func spawn_point() -> Vector3
```

Attendu du relief : `ChunkData.SEA_LEVEL` vaut 48. Le terrain descend vers 30
dans les océans et monte jusqu'à 88 dans les montagnes. Somme d'octaves de
`FastNoiseLite` pour l'altitude, deux bruits basse fréquence indépendants pour
température et humidité qui choisissent le biome, un bruit de « relief » qui
module l'amplitude pour que les plaines restent plates et les montagnes
déchiquetées.

Contenu obligatoire :
- Strate : `BEDROCK` sur y 0 (plus quelques taches jusqu'à y 3), `STONE` en
  profondeur, 3 à 5 blocs de couverture selon le biome (`DIRT` puis `GRASS`,
  `SAND` puis `SANDSTONE` au désert et sur les plages, `SNOW_BLOCK` sur
  `DIRT` en toundra, `GRAVEL` en montagne haute).
- `WATER` dans toute cellule vide de `y <= SEA_LEVEL`.
- `ICE` en surface de l'eau en toundra.
- Grottes : bruit 3D à seuil, creusé uniquement sous la surface. Deux échelles,
  des galeries fines et des cavernes larges. Ne perce jamais le bedrock.
- Minerais en amas : `COAL_ORE` (fréquent, y 5..70), `IRON_ORE` (y 5..55),
  `GOLD_ORE` (rare, y 4..30), `DIAMOND_ORE` (très rare, y 2..16). Amas de 3 à 9
  blocs. `GRANITE`, `MARBLE` et `CLAY` en poches plus larges.
- Décor : chênes (tronc `OAK_LOG` 4..7 haut, houppier `OAK_LEAVES`), bouleaux
  (`BIRCH_LOG` plus hauts et plus fins), sapins en taïga (cône de
  `PINE_LEAVES` sur `OAK_LOG`), cactus au désert, `DEAD_BUSH` au désert,
  `GRASS_TUFT` et `FERN` densément en plaines et forêt, `FLOWER_RED` et
  `FLOWER_YELLOW` en plaines, `PUMPKIN` rare.
- **Débordement inter-chunks :** un arbre planté près d'un bord doit poser ses
  feuilles dans le chunk voisin. Implémente `generate()` en décorant la
  fenêtre 3x3 de chunks autour de `(cx, cz)` et en découpant les écritures aux
  bornes du chunk courant. La position et l'espèce de chaque arbre viennent
  d'un hachage déterministe de `(wx, wz, seed)`, jamais d'un
  `RandomNumberGenerator` partagé, sinon les deux chunks voisins ne
  s'accordent pas sur l'arbre et il apparaît coupé.

### 4.5 `src/world/mesher.gd` - `class_name Mesher`

Maillage par élimination de faces cachées, avec occlusion ambiante par sommet
et lumière du ciel. Tourne dans un thread de travail : **aucun appel à l'API
scène**, uniquement du calcul sur des tableaux.

Volume rembourré d'une cellule dans les six directions, ce qui donne au mesher
les voisins diagonaux dont l'occlusion ambiante a besoin sans aucun test de
bornes dans la boucle chaude.

```gdscript
const PAD := 1
const PW := ChunkData.SIZE_X + 2    # 18
const PH := ChunkData.SIZE_Y + 2    # 98
const PD := ChunkData.SIZE_Z + 2    # 18
const PVOLUME := PW * PH * PD       # 31752
const PSTRIDE_Y := 1
const PSTRIDE_Z := PH
const PSTRIDE_X := PH * PD

## px = x + 1, py = y + 1, pz = z + 1
static func padded_index(px: int, py: int, pz: int) -> int:
	return (px * PD + pz) * PH + py

## neighbours a exactement 9 entrées, index (dx + 1) * 3 + (dz + 1) avec
## dx et dz dans -1..1. L'entrée 4 est le chunk central. Une entrée null est
## traitée comme entièrement remplie d'air.
static func build_padded(neighbours: Array) -> PackedByteArray

## tints a PW * PD entrées, index px * PD + pz, couleur d'herbe de la colonne.
## Renvoie :
##   {
##     "surfaces": Array,             # SURFACE_COUNT entrées, null ou tableau ARRAY_MAX
##     "lights": PackedVector3Array,  # centres locaux des blocs émissifs
##     "light_ids": PackedInt32Array, # id de bloc de chaque lumière, même ordre
##   }
static func build_mesh_data(padded: PackedByteArray, tints: PackedColorArray) -> Dictionary
```

Géométrie :
- Cubes (`SOLID`, `CUTOUT`, `TRANSLUCENT`, `LIQUID`) : une face est émise quand
  `Blocks.draws_face(self_id, neighbour_id)` est vrai. Enroulement antihoraire
  vu de l'extérieur pour que `cull_back` garde la bonne face.
- `LIQUID` : la face de dessus est abaissée à `y + 0.88` quand la cellule au
  dessus n'est pas du liquide, sinon `y + 1.0`. Cela creuse la surface de l'eau.
- `CROSS` : deux quads en diagonale, encastrés de 0.146 sur X et Z, de
  `y` à `y + 1`. Décale le motif de plus ou moins 0.18 en X et Z selon un
  hachage de la position monde pour casser la régularité. `CUSTOM0.y` vaut 1.0
  sur les sommets du haut et 0.0 sur ceux du bas, ce qui fait onduler la plante
  par le sommet sans décoller le pied du sol. Émets les deux faces (le matériau
  est en `cull_disabled`).
- Pour les cubes, `CUSTOM0.y` vaut 0 partout sauf sur les feuilles
  (`OAK_LEAVES`, `BIRCH_LEAVES`, `PINE_LEAVES`) où il vaut 0.35.

Occlusion ambiante, méthode standard à trois échantillons par coin. Pour un
coin donné, `s1` et `s2` sont les deux voisins d'arête et `c` le voisin
diagonal, chacun comptant 1 si `Blocks.is_opaque()` :

```
niveau = 0 si (s1 et s2)  sinon  3 - (s1 + s2 + c)
facteur = [0.52, 0.70, 0.86, 1.0][niveau]
```

Anti-crevasse obligatoire : si `ao(v0) + ao(v2) > ao(v1) + ao(v3)`, découpe le
quad selon l'autre diagonale, sinon l'interpolation crée un artefact en biais
bien visible sur les coins de terrain.

Lumière du ciel, sans coutures parce qu'elle ne dépend que du volume rembourré :
calcule d'abord `ptop[px * PD + pz]`, le plus haut `py` dont le bloc vérifie
`Blocks.is_opaque()`. Pour une face, prends la cellule d'air dans laquelle elle
regarde, puis

```
e = max sur les 9 colonnes (dx, dz) de -1..1 de
      pow(0.80, max(0, ptop(px + dx, pz + dz) - py)) * (1.0 si dx == dz == 0 sinon 0.72)
lumière = 0.10 + 0.90 * clamp(e, 0.0, 1.0)
```

Couleur finale d'un sommet :
`rgb = ombrage_de_face * lumière * facteur_ao * teinte`, où `teinte` vaut
`tints[...]` si le bit de la face est dans `Blocks.tint_mask(id)`, sinon blanc.
`a = Blocks.emission(id)`.

Budget : viser moins de 40 ms par chunk. Sors des boucles au plus tôt avec
`ChunkData.column_top`, n'alloue pas dans la boucle chaude, et utilise
l'arithmétique d'index plutôt que des appels de fonction par cellule.

### 4.6 `src/world/chunk_node.gd` - `class_name ChunkNode extends MeshInstance3D`

```gdscript
var cx: int
var cz: int

## Positionne le noeud, mémorise les matériaux (indexés par Blocks.Surface).
func setup(chunk_x: int, chunk_z: int, surface_materials: Array[Material]) -> void

## Construit l'ArrayMesh depuis la sortie de Mesher.build_mesh_data et
## remplace les lumières. Appel main thread uniquement.
func apply(mesh_data: Dictionary) -> void

## Libère maillage et lumières, prêt pour réutilisation par le pool du monde.
func release() -> void
```

`apply()` doit sauter les surfaces vides, appeler `add_surface_from_arrays`
avec le drapeau `CUSTOM0` du paragraphe 3, et assigner
`set_surface_override_material(i, ...)` dans l'ordre réel des surfaces créées
(attention : si la surface 0 est vide, la surface eau devient l'index 0 du
maillage). Crée une `OmniLight3D` par entrée de `lights`, énergie 1.6 et
portée 9.0 pour `LAMP` (couleur `Color(1.0, 0.95, 0.82)`), énergie 1.1 et
portée 7.0 pour `TORCH` (couleur `Color(1.0, 0.72, 0.36)`).
Limite à 32 lumières par chunk, les plus hautes d'abord, pour ne pas saturer
le rendu.

### 4.7 `src/world/save_manager.gd` - `class_name SaveManager extends RefCounted`

Persistance des chunks modifiés dans `user://saves/<world_name>/`, un fichier
`c_<cx>_<cz>.bin` par chunk, contenant la sortie de `ChunkData.serialize()`.

```gdscript
func _init(world_name: String) -> void   # crée le dossier au besoin

## Appelé depuis les threads de travail : doit être protégé par un Mutex.
func load_chunk(cx: int, cz: int) -> PackedByteArray   # vide si absent
func has_chunk(cx: int, cz: int) -> bool

## Appelé depuis le thread principal.
func save_chunk(cx: int, cz: int, payload: PackedByteArray) -> void
func save_meta(data: Dictionary) -> void                # JSON dans meta.json
func load_meta() -> Dictionary                          # vide si absent
func delete_world() -> void
static func list_worlds() -> PackedStringArray
```

Tiens un index en mémoire des chunks présents sur disque, rempli une fois dans
`_init` avec `DirAccess`, pour que `has_chunk()` ne touche pas le disque à
chaque appel depuis les threads.

### 4.8 `src/player/voxel_body.gd` - `class_name VoxelBody extends RefCounted`

Collision AABB contre la grille de voxels. **N'utilise pas** le moteur physique
de Godot : la gravité du projet est à zéro et aucun `CollisionShape3D` n'existe.

La boîte du personnage a son origine **aux pieds** : elle va de
`(p.x - radius, p.y, p.z - radius)` à `(p.x + radius, p.y + height, p.z + radius)`.

```gdscript
var radius: float = 0.30
var height: float = 1.80

## Déplace la boîte de `motion`, en résolvant les collisions axe par axe dans
## l'ordre Y, X, Z. Découpe en sous-pas d'au plus 0.45 unité pour interdire la
## traversée à grande vitesse. Renvoie :
##   {
##     "position": Vector3,   # position finale des pieds
##     "hit_x": bool, "hit_y": bool, "hit_z": bool,
##     "on_floor": bool,      # bloqué en descendant
##     "on_ceiling": bool,    # bloqué en montant
##   }
func move(world: VoxelWorld, feet: Vector3, motion: Vector3) -> Dictionary

## Vrai si un bloc solide chevauche la boîte à cette position.
func overlaps_solid(world: VoxelWorld, feet: Vector3) -> bool

## Vrai si un liquide couvre la cellule des yeux (feet.y + eye_height).
func head_in_liquid(world: VoxelWorld, feet: Vector3, eye_height: float) -> bool

## Fraction de la boîte immergée, 0..1. Sert à la poussée et au rendu.
func submersion(world: VoxelWorld, feet: Vector3) -> float
```

Une cellule bloque si `Blocks.collides(id)`. Applique une marge de 0.001 en
sortie de résolution pour éviter que le corps reste collé et re-collisionne au
pas suivant. Un chunk non chargé doit être traité comme **solide** afin que le
joueur ne tombe pas dans le vide au bord du monde chargé.

### 4.9 `src/player/player.gd` - `class_name Player extends Node3D`

Crée ses enfants par code dans `_ready()` : un `Node3D` nommé `Head` à
`(0, 1.62, 0)` puis une `Camera3D` enfant du Head. Aucune scène `.tscn`.

```gdscript
signal entered_water()
signal left_water()
signal fly_mode_changed(active: bool)
signal footstep(block_id: int)

var camera: Camera3D            # créée dans _ready
var head: Node3D
var velocity: Vector3
var fly_mode: bool = false
var in_water: bool = false
var body: VoxelBody
var frozen: bool = true         # vrai jusqu'à ce que le terrain sous le joueur existe

func setup(world: VoxelWorld) -> void
func teleport(feet_position: Vector3) -> void
func eye_position() -> Vector3
func look_direction() -> Vector3
func horizontal_speed() -> float
func on_floor() -> bool
```

Comportement :
- Souris capturée : `Game.mouse_sensitivity`, tangage borné à plus ou moins
  89 degrés, `Game.invert_y` respecté. Ne tourne pas quand la souris est
  visible (menu ouvert).
- Marche 4.6 u/s, sprint 6.8, accroupi 2.0. Accélération au sol 12 u/s²,
  contrôle en l'air réduit à 30 %.
- Saut : vitesse initiale 8.4 avec gravité 26.0, ce qui donne un saut d'environ
  1.25 bloc, franchissable sur un bloc unique. Vitesse de chute plafonnée à 55.
- Nage : gravité divisée par 5, remontée à vitesse constante en maintenant
  `jump`, vitesse horizontale à 60 %, amortissement fort. Émet `entered_water`
  et `left_water`, joue `splash` à l'entrée.
- Vol (`fly_toggle`) : gravité coupée, montée sur `jump`, descente sur
  `crouch`, vitesse 12 u/s et 22 en sprint. Autorisé seulement si
  `Game.creative`.
- Accroupi : `body.height` passe à 1.45 et l'oeil descend en douceur.
  Refuse de se relever si un bloc est au dessus.
- Ballant de tête : oscillation d'amplitude 0.045 proportionnelle à la vitesse
  horizontale, coupée en vol. Le champ de vision passe de `Game.fov` à
  `Game.fov + 6` en sprint, interpolé.
- `frozen` reste vrai tant que `world.has_chunk_at()` est faux sous le joueur.
  Gelé, le joueur n'est soumis ni à la gravité ni aux entrées.
- Émet `footstep(block_id)` avec l'id du bloc **sous** les pieds à chaque
  0.9 unité parcourue au sol, pour que le HUD et l'audio réagissent.

### 4.10 `src/player/interaction.gd` - `class_name Interaction extends Node3D`

Casse, pose, ciblage. Étend `Node3D` parce qu'il porte le contour de sélection
et l'émetteur de particules.

```gdscript
signal target_changed(hit: Dictionary)
signal dig_progress(ratio: float)          # 0..1, 0 quand rien n'est en cours
signal block_broken(block_id: int, cell: Vector3i)
signal block_placed(block_id: int, cell: Vector3i)

const REACH := 6.0

func setup(world: VoxelWorld, player: Player, inventory: Inventory) -> void

## Parcours de grille de Amanatides et Woo. Renvoie :
##   {
##     "hit": bool,
##     "cell": Vector3i,      # bloc touché
##     "normal": Vector3i,    # face touchée, dirigée vers l'extérieur
##     "id": int,
##     "distance": float,
##     "point": Vector3,      # point d'impact exact
##   }
## Ignore les blocs non ciblables (air, liquide).
static func raycast(world: VoxelWorld, origin: Vector3, direction: Vector3, max_distance: float) -> Dictionary
```

Règles :
- Maintenir `dig` casse le bloc visé en `Blocks.hardness()` secondes. Changer
  de cible remet la progression à zéro. Un bloc non cassable ne progresse pas.
  À la casse, `Blocks.drop_of()` entre dans l'inventaire.
- `place` pose `inventory.selected_block()` dans la cellule
  `cell + normal`, seulement si `Blocks.is_replaceable()` y est vrai, si la
  boîte du joueur ne chevauche pas la cellule après pose, et si le stock est
  suffisant hors mode créatif. Cadence limitée à 5 poses par seconde en maintien.
- Une plante (`Blocks.needs_support()`) ne se pose que sur une cellule solide.
- Contour de sélection : `MeshInstance3D` avec un `ImmediateMesh` de 12 arêtes
  d'un cube légèrement dilaté (0.502 de demi-côté), matériau
  `VoxelMaterials.outline_material()`. Caché quand rien n'est visé.
- Particules de casse : `GPUParticles3D` en rafale unique de 18 particules,
  petits quads non éclairés teintés de la couleur moyenne de la tuile du bloc
  (via `VoxelAtlas.tile_image`), gravité vers le bas, durée 0.7 s.
- Joue les sons via l'autoload `Sfx` : `Sfx.play_dig(block_id, position)` en
  boucle pendant le creusage, `Sfx.play_break(block_id, position)` à la casse,
  `Sfx.play_place(block_id, position)` à la pose.

### 4.11 `src/player/inventory.gd` - `class_name Inventory extends RefCounted`

```gdscript
signal changed()
signal selection_changed(slot: int)

const HOTBAR_SLOTS := 9
const STORAGE_SLOTS := 27
const STACK_MAX := 999

var creative: bool = true
var selected: int = 0            # 0..8

func selected_block() -> int
func select(slot: int) -> void
func cycle(delta: int) -> void   # enroule sur 0..8
func slot_block(slot: int) -> int    # 0..8 barre, 9..35 réserve
func slot_count(slot: int) -> int
func set_slot(slot: int, block_id: int, count: int) -> void
func swap_slots(a: int, b: int) -> void
func add(block_id: int, amount: int = 1) -> int      # renvoie le reliquat
func consume_selected(amount: int = 1) -> bool
func count_of(block_id: int) -> int
func has_room_for(block_id: int) -> bool
func clear() -> void

## Remplit la barre d'action avec la page `page` de Blocks.PALETTE.
func load_palette_page(page: int) -> void
func palette_page_count() -> int

func to_dict() -> Dictionary
func from_dict(data: Dictionary) -> void
```

En créatif, `consume_selected()` réussit toujours sans décrémenter et `add()`
renvoie 0. `select()` et `cycle()` émettent `selection_changed`. Toute autre
mutation émet `changed`. Au démarrage, la barre contient la page 0 de la
palette.

### 4.12 Interface, `src/ui/`

Toutes les widgets sont construites par code, aucune scène `.tscn`, aucune
police externe (la police par défaut de Godot suffit). Style : panneaux sombres
translucides `Color(0.06, 0.07, 0.09, 0.78)`, bordure 2 px
`Color(0.85, 0.88, 0.92, 0.25)`, coins droits (esthétique voxel), texte
`Color(0.94, 0.96, 0.98)`.

#### `src/ui/hud.gd` - `class_name Hud extends CanvasLayer`

```gdscript
func setup(world: VoxelWorld, player: Player, inventory: Inventory, interaction: Interaction, sky: SkyController) -> void
func show_toast(text: String, seconds: float = 1.6) -> void
func set_paused(paused: bool) -> void
```

Contient : réticule central (deux traits croisés en `blend_mode` différence
pour rester visible sur tout fond), barre d'action de 9 cases avec aperçu de
bloc (`VoxelAtlas.block_preview`) et compteur en créatif masqué, surbrillance
de la case active, nom du bloc sélectionné qui apparaît 1.6 s au changement,
anneau de progression de creusage autour du réticule, voile bleu quand la tête
est sous l'eau, et un message central « Génération du monde... » avec le
nombre de chunks restants tant que `world` n'a pas émis
`initial_load_finished`.

#### `src/ui/debug_overlay.gd` - `class_name DebugOverlay extends Control`

Basculé par `debug_overlay`, caché par défaut. Affiche en haut à gauche, en
police monospace : images par seconde, position monde à deux décimales, chunk
courant, biome, hauteur du sol, bloc visé et sa distance, nombre de chunks
chargés et de tâches en attente, heure du jour, mode (créatif ou survie, vol),
mémoire vidéo et nombre de triangles dessinés
(`Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)`).

```gdscript
func setup(world: VoxelWorld, player: Player, interaction: Interaction, sky: SkyController) -> void
```

#### `src/ui/inventory_ui.gd` - `class_name InventoryUi extends Control`

Basculé par `inventory`, libère la souris à l'ouverture et la recapture à la
fermeture. Grille 9 x 3 de la réserve au dessus de la barre d'action, plus, en
créatif, la palette complète de `Blocks.PALETTE` en grille de 9 colonnes,
cliquable pour affecter la case sélectionnée. Glisser déposer entre cases via
`swap_slots`. Infobulle avec `Blocks.display_name` au survol.

```gdscript
signal closed()
func setup(inventory: Inventory) -> void
func open() -> void
func close() -> void
func is_open() -> bool
```

#### `src/ui/pause_menu.gd` - `class_name PauseMenu extends Control`

Basculé par `pause`. Libère la souris, met le monde en pause logique (le
streaming continue, mais le joueur ne bouge plus). Boutons « Reprendre »,
« Réglages », « Sauvegarder », « Quitter ». Le panneau Réglages expose, avec
des `HSlider` et `CheckBox` reliés à l'autoload `Game` : sensibilité souris,
champ de vision, distance d'affichage, inverser l'axe Y, volume, mode créatif.
Chaque changement appelle `Game.save_settings()`.

```gdscript
signal resume_requested()
signal quit_requested()
signal save_requested()
func open() -> void
func close() -> void
func is_open() -> bool
```

### 4.13 `src/render/sky.gd` - `class_name SkyController extends Node`

```gdscript
signal night_changed(is_night: bool)

var time_of_day: float = 0.30     # 0 minuit, 0.25 aube, 0.5 midi, 0.75 crépuscule
var day_length: float = 600.0     # secondes pour un cycle complet
var paused: bool = false

func setup(env: WorldEnvironment, sun: DirectionalLight3D, moon: DirectionalLight3D) -> void
func is_night() -> bool
func time_string() -> String      # "06:24"
func skip_to(t: float) -> void
func sun_direction() -> Vector3
```

Écrit `src/render/shaders/sky.gdshader` (`shader_type sky;`) avec : dégradé
zénith vers horizon piloté par des uniformes de couleur, disque solaire doux et
halo, lune avec un croissant, champ d'étoiles par hachage de `EYEDIR` qui
n'apparaît que la nuit et scintille lentement, bande de nuages procéduraux
(fbm sur `EYEDIR.xz / EYEDIR.y`) qui défilent doucement.

`setup()` crée l'`Environment` et le `Sky` par code. Anime au fil du temps :
rotation et couleur du soleil (orangé au ras de l'horizon, blanc au zénith),
énergie de la lumière, lune en contre-lumière bleutée la nuit, couleur et
densité du brouillard accordées à l'horizon, luminosité ambiante. La nuit doit
être sombre mais jouable. Émet `night_changed` aux transitions.
`Game.render_distance` doit piloter la distance de brouillard pour masquer le
bord du monde chargé.

### 4.14 Audio, `src/audio/`

#### `src/audio/sfx_lib.gd` - `class_name SfxLib`

Synthèse pure, aucun fichier audio. Chaque son est un `AudioStreamWAV` en
16 bits mono à 22050 Hz, construit en remplissant un `PackedByteArray`.

```gdscript
const MIX_RATE := 22050

## Renvoie un Dictionary nom -> AudioStreamWAV, tous les sons ci-dessous.
static func build() -> Dictionary
```

Noms obligatoires : `dig_stone`, `dig_dirt`, `dig_grass`, `dig_sand`,
`dig_wood`, `dig_glass`, `dig_wool`, `dig_plant`, `break_stone`, `break_dirt`,
`break_grass`, `break_sand`, `break_wood`, `break_glass`, `break_wool`,
`break_plant`, `place`, `pop`, `splash`, `swim`, `click`, `land`,
`step_stone`, `step_dirt`, `step_grass`, `step_sand`, `step_wood`, `step_snow`.

Recettes : les sons de matériau sont des bruits filtrés courts (30 à 90 ms)
avec une enveloppe percussive. `dig_stone` bruit blanc passe-bande medium plus
un clic sec, `dig_dirt` bruit passe-bas sourd, `dig_grass` bruit passe-haut
bruissant, `dig_sand` bruit très aigu qui décroît vite, `dig_wood` bruit
passe-bande plus une résonance vers 220 Hz, `dig_glass` clic aigu métallique,
`dig_wool` bruit très sourd et doux. Les `break_*` sont les `dig_*` en plus
long et plus fort, `break_glass` étant un éclat aigu avec une traîne de
tintements. `splash` est un souffle de bruit qui monte puis descend, `swim` un
remous grave et doux, `pop` un sinus court avec pitch qui monte, `click` un
clic très bref, `land` un choc mat grave. Applique une enveloppe
attaque-décroissance sur chaque son pour éviter les clics de bord, et normalise
sans saturer.

#### `src/audio/sfx_player.gd` - autoload `Sfx extends Node`

Construit la bibliothèque dans `_ready()` et gère un pool de lecteurs.

```gdscript
func play(sound: String, volume_db: float = 0.0, pitch: float = 1.0) -> void
func play_at(sound: String, position: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void

## Choisit le bon son de matériau depuis l'id de bloc.
func play_dig(block_id: int, position: Vector3) -> void       # limité à 1 toutes les 0.22 s
func play_break(block_id: int, position: Vector3) -> void
func play_place(block_id: int, position: Vector3) -> void
func play_step(block_id: int, position: Vector3) -> void
func stop_dig() -> void

## Famille de matériau d'un bloc : "stone", "dirt", "grass", "sand", "wood",
## "glass", "wool" ou "plant".
static func material_family(block_id: int) -> String
```

Pool de 12 `AudioStreamPlayer3D` plus 4 `AudioStreamPlayer` non spatialisés,
réutilisés en tourniquet. Applique `Game.sfx_volume`. Ajoute une variation de
hauteur aléatoire de plus ou moins 8 % sur les sons de matériau pour éviter la
répétition mécanique. `unit_size` autour de 12 et
`attenuation_model` linéaire pour que les sons portent correctement.

## 5. Modules écrits par l'orchestrateur

Tu n'as pas à les écrire, mais tu peux compter sur leur API.

### `src/world/world.gd` - `class_name VoxelWorld extends Node3D`

```gdscript
signal chunk_ready(cx: int, cz: int)
signal block_changed(cell: Vector3i, old_id: int, new_id: int)
signal initial_load_finished()

const WORLD_HEIGHT := ChunkData.SIZE_Y

static func chunk_of(w: int) -> int      # division plancher par 16
static func local_of(w: int) -> int      # modulo positif 16

func setup(world_seed: int, world_name: String) -> void
func get_block(wx: int, wy: int, wz: int) -> int
func set_block(wx: int, wy: int, wz: int, id: int) -> bool
func is_solid(wx: int, wy: int, wz: int) -> bool
func has_chunk_at(wx: int, wz: int) -> bool
func surface_height(wx: int, wz: int) -> int
func biome_name_at(wx: int, wz: int) -> String
func update_streaming(center: Vector3) -> void
func pending_jobs() -> int
func loaded_chunk_count() -> int
func materials() -> Array[Material]
func atlas() -> Texture2DArray
func spawn_point() -> Vector3
func save_all() -> void
func shutdown() -> void
```

`get_block()` renvoie `Blocks.AIR` hors de la plage verticale ou dans un chunk
non chargé. Utilise `has_chunk_at()` pour distinguer les deux cas.

### `src/main.gd` et `scenes/main.tscn`

Le noeud racine instancie et relie tout : monde, joueur, interaction,
inventaire, HUD, ciel. Il appelle `setup()` sur chacun dans le bon ordre.

## 6. Tests

`tests/run_tests.gd` étend `SceneTree` et s'exécute par
`godot --headless --path . --script res://tests/run_tests.gd`.
Il sort en code 0 si tout passe. Ajoute tes propres cas dans
`tests/test_<module>.gd` en suivant le motif du fichier existant, et déclare
le fichier dans la liste de `run_tests.gd`.
