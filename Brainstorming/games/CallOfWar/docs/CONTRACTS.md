# CALL OF WAR - contrats d'API

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
- **Maillages et sons entièrement générés par code** au démarrage. Aucun modèle
  3D, aucun fichier audio dans le dépôt.
- **Textures : photographies CC0 avec repli procédural.** Le projet a d'abord été
  écrit sans aucun asset binaire ; `assets/textures` a été ajouté ensuite pour la
  qualité visuelle. La règle qui reste vraie et qui doit le rester : `Tex` sait
  synthétiser **chaque** texture, et une photo absente n'est jamais une erreur,
  seulement un rendu plus grossier. N'écris jamais de code qui suppose qu'un
  fichier de `assets/textures` existe. Le feuillage, le blé et l'herbe ont besoin
  d'un alpha découpé : leur atlas est fusionné avec sa carte d'opacité au
  chargement par `Tex.blade_texture()`, parce que `StandardMaterial3D` n'a pas
  d'entrée d'opacité séparée.
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

## 1. Repères, unités, monde

- 1 unité Godot = **1 mètre**. Y est vertical, vers le haut.
- Le monde est un carré fini de **4096 m de côté centré sur l'origine**, donc
  x et z vont de -2048 à +2048. C'est la « poche de Normandie » du jeu.
- Le niveau de l'eau est `Heightfield.WATER_LEVEL == 2.0`. Rivières et marais s'y
  calent.
- La gravité du projet vaut 19.6 (deux fois la gravité réelle : c'est la valeur
  qui donne un saut FPS nerveux). Ne la change pas.
- Une tuile de terrain fait **64 m de côté**. La tuile `(tx, tz)` couvre
  `[tx * 64, tx * 64 + 64[` en x. Conversion : `floori(x / 64.0)`.

### Couches de collision physique (bit → nom)

| Bit | Masque | Nom | Contenu |
|---|---|---|---|
| 1 | 1 | terrain | sol des chunks |
| 2 | 2 | structure | murs, maisons, bunkers, ponts |
| 3 | 4 | player | le joueur |
| 4 | 8 | enemy | soldats allemands |
| 5 | 16 | ally | résistants et alliés |
| 6 | 32 | prop | arbres, murets, épaves, sacs de sable |
| 7 | 64 | vehicle | véhicules actifs |
| 8 | 128 | trigger | zones de déclenchement, Area3D |

Constantes fournies par `Layers` (voir 2.1). **N'écris jamais un masque en dur.**

## 2. Modules et signatures

Les sections sont ordonnées par dépendance. Un module ne peut appeler que des
modules listés **avant** lui, plus les autoloads.

---

### 2.1 `src/core/layers.gd` - `class_name Layers`

```gdscript
class_name Layers
extends RefCounted

const TERRAIN   := 1
const STRUCTURE := 2
const PLAYER    := 4
const ENEMY     := 8
const ALLY      := 16
const PROP      := 32
const VEHICLE   := 64
const TRIGGER   := 128

## Everything a bullet can stop on.
const BULLET_MASK := TERRAIN | STRUCTURE | PLAYER | ENEMY | ALLY | PROP | VEHICLE
## Everything that blocks line of sight for the AI.
const SIGHT_MASK  := TERRAIN | STRUCTURE | PROP | VEHICLE
## Solid ground and walls a walking body collides with.
const WALK_MASK   := TERRAIN | STRUCTURE | PROP | VEHICLE
```

---

### 2.2 `src/core/game.gd` - autoload `Game` (pas de `class_name`)

`extends Node`. Deux responsabilités, comme dans CUBEFORGE :

1. Installer **tout l'InputMap depuis le code** dans `_ready()`, par **keycode
   physique** (`InputEventKey.physical_keycode`) pour qu'un clavier AZERTY pilote
   ZQSD là où un QWERTY pilote WASD.
2. Détenir les réglages, bornés, persistés dans `user://settings.cfg` via
   `ConfigFile`. Un fichier absent ou corrompu n'est jamais fatal.

```gdscript
signal settings_changed()

const SETTINGS_PATH := "user://settings.cfg"

# Bornes
const MOUSE_SENSITIVITY_MIN := 0.0004
const MOUSE_SENSITIVITY_MAX := 0.010
const FOV_MIN := 60.0
const FOV_MAX := 110.0
const VIEW_DISTANCE_MIN := 4      # en tuiles de 64 m
const VIEW_DISTANCE_MAX := 14
const VOLUME_MIN := 0.0
const VOLUME_MAX := 1.0

# Proprietes (chacune avec un setter qui borne et emet settings_changed)
var mouse_sensitivity: float   # defaut 0.0024
var invert_y: bool             # defaut false
var fov: float                 # defaut 82.0
var view_distance: int         # defaut 9
var sfx_volume: float          # defaut 0.85
var music_volume: float        # defaut 0.5
var difficulty: int            # 0 facile, 1 normal, 2 veteran. defaut 1
var show_fps: bool             # defaut false
var show_debug: bool           # defaut false
var fullscreen: bool           # defaut false
var blood_effects: bool        # defaut true
var head_bob: bool             # defaut true
var campaign_seed: int         # graine du monde, tiree au hasard au 1er lancement
var campaign_name: String      # defaut "normandie"

func load_settings() -> void
func save_settings() -> void
func reset_settings() -> void
## Damage multiplier applied to the player, from `difficulty`.
## 0 -> 0.5, 1 -> 1.0, 2 -> 1.75
func incoming_damage_scale() -> float
## Enemy accuracy multiplier from `difficulty`. 0 -> 0.6, 1 -> 1.0, 2 -> 1.35
func enemy_accuracy_scale() -> float
func difficulty_name() -> String   # "Recrue" / "Soldat" / "Veteran"
```

**Actions d'entrée à enregistrer** (noms exacts, aucun autre) :

| Action | Touche / bouton |
|---|---|
| `move_forward` | W (physique, donc Z en AZERTY) + flèche haut |
| `move_back` | S + flèche bas |
| `move_left` | A (donc Q en AZERTY) + flèche gauche |
| `move_right` | D + flèche droite |
| `jump` | Espace |
| `sprint` | Maj gauche |
| `crouch` | Ctrl gauche |
| `prone` | X |
| `fire` | bouton souris gauche |
| `aim` | bouton souris droit |
| `reload` | R |
| `melee` | V |
| `grenade` | G |
| `use` | E |
| `heal` | H |
| `binoculars` | B |
| `weapon_next` | molette haut |
| `weapon_prev` | molette bas |
| `weapon_1` .. `weapon_4` | 1, 2, 3, 4 |
| `map` | M |
| `objectives` | J |
| `pause` | Échap |
| `fullscreen` | F11 |
| `screenshot` | F2 |
| `debug` | F3 |

---

### 2.3 `src/core/war_state.gd` - autoload `War` (pas de `class_name`)

`extends Node`. État global de la campagne : factions, contrôle des secteurs,
statistiques, niveau d'alerte. **Ne touche jamais aux noeuds de la scène.**

```gdscript
# Factions
const ALLIED := 0
const AXIS := 1
const NEUTRAL := 2

signal sector_captured(sector_id: int)
signal alert_changed(level: int)
signal stat_changed(key: String)
signal war_won()

## Alert levels: 0 calme, 1 soupcon, 2 recherche, 3 alerte generale.
const ALERT_CALM := 0
const ALERT_SUSPICIOUS := 1
const ALERT_SEARCHING := 2
const ALERT_FULL := 3

var alert_level: int
var kills: int
var headshots: int
var shots_fired: int
var shots_hit: int
var deaths: int
var objectives_done: int
var play_seconds: float

func reset_campaign() -> void
## Marks a sector as liberated. Idempotent. Emits sector_captured, and war_won
## when every registered sector is allied.
func capture_sector(sector_id: int) -> void
func is_sector_captured(sector_id: int) -> bool
func captured_count() -> int
func register_sectors(ids: PackedInt32Array) -> void
func sector_count() -> int
## Raises the alert to at least `level`, resets the decay timer, emits
## alert_changed when the value actually moves.
func raise_alert(level: int) -> void
## Called every frame by Main. Lets the alert cool down after ~45 s of quiet.
func tick(delta: float) -> void
func record_kill(headshot: bool) -> void
func record_shot(hit: bool) -> void
func accuracy() -> float           # 0..1, 0 si aucun tir
func to_dict() -> Dictionary
func from_dict(data: Dictionary) -> void
func alert_name() -> String        # "Calme" / "Soupcon" / "Recherche" / "Alerte generale"
```

---

### 2.4 `src/audio/sfx_lib.gd` - `class_name SfxLib`

Génère **par code** tous les échantillons. Aucun fichier audio.
Sortie : `AudioStreamWAV` mono 22050 Hz, 16 bits.

```gdscript
class_name SfxLib
extends RefCounted

## Every sample name the project may ask for. Exactly these keys.
const NAMES: PackedStringArray = [
    "rifle_m1", "rifle_kar98", "smg_thompson", "smg_mp40", "pistol_1911",
    "sniper_springfield", "mg42", "garand_ping", "dry_fire",
    "reload_in", "reload_out", "bolt", "grenade_pin", "grenade_throw",
    "explosion", "explosion_far", "artillery_incoming", "artillery_hit",
    "impact_dirt", "impact_stone", "impact_wood", "impact_metal", "impact_flesh",
    "ricochet", "whizz", "shell_casing",
    "step_grass", "step_dirt", "step_stone", "step_wood", "step_water",
    "hurt", "death", "breath", "bandage", "heartbeat",
    "german_alert", "german_shout", "german_death", "french_ok", "french_go",
    "ui_click", "ui_open", "ui_close", "objective_done", "sector_captured",
    "distant_battle", "bird", "wind",
]

## Builds every sample once. Returns name -> AudioStreamWAV.
static func build_all() -> Dictionary
## Builds a single sample by name. Returns null for an unknown name.
static func build(sample_name: String) -> AudioStreamWAV
```

---

### 2.5 `src/audio/sfx_player.gd` - autoload `Sfx` (pas de `class_name`)

`extends Node`. Pool de lecteurs. Construit la banque via `SfxLib.build_all()`
dans `_ready()`.

```gdscript
## Non positional (UI, feedback).
func play(sample_name: String, volume_db: float = 0.0, pitch: float = 1.0) -> void
## Positional 3D.
func play_at(sample_name: String, position: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> void
## Footstep dispatch on a surface name among "grass","dirt","stone","wood","water".
func play_step(surface: String, position: Vector3) -> void
## Gunshot with distance aware layering (adds a far tail beyond 60 m).
func play_shot(sample_name: String, position: Vector3) -> void
## Stops everything at once (used on scene reload).
func stop_all() -> void
func has_sample(sample_name: String) -> bool
```

Le volume global suit `Game.sfx_volume`. En mode headless
(`DisplayServer.get_name() == "headless"`) la construction de la banque doit
rester possible sans planter.

---

### 2.6 `src/render/palette.gd` - `class_name Palette`

Couleurs du jeu, en **espace linéaire déjà** (les valeurs listées sont passées
telles quelles à `albedo_color`). Piège connu : un albédo trop clair désature
dans la courbe ACES. **Garde tous les albédos entre 0.05 et 0.38.**

```gdscript
class_name Palette
extends RefCounted

const GRASS_SUMMER := Color(0.19, 0.26, 0.10)
const GRASS_DRY    := Color(0.30, 0.28, 0.13)
const WHEAT        := Color(0.34, 0.29, 0.12)
const DIRT         := Color(0.20, 0.15, 0.10)
const MUD          := Color(0.13, 0.10, 0.07)
const ROAD         := Color(0.16, 0.15, 0.14)
const STONE        := Color(0.24, 0.23, 0.21)
const STONE_DARK   := Color(0.14, 0.13, 0.12)
const CONCRETE     := Color(0.22, 0.22, 0.21)
const WOOD         := Color(0.16, 0.11, 0.07)
const WOOD_LIGHT   := Color(0.26, 0.19, 0.12)
const ROOF_SLATE   := Color(0.09, 0.10, 0.12)
const ROOF_TILE    := Color(0.24, 0.12, 0.08)
const PLASTER      := Color(0.32, 0.30, 0.26)
const LEAF_DARK    := Color(0.10, 0.17, 0.08)
const LEAF_LIGHT   := Color(0.16, 0.24, 0.10)
const WATER        := Color(0.05, 0.10, 0.12)
const METAL        := Color(0.13, 0.13, 0.14)
const RUST         := Color(0.18, 0.09, 0.05)
const FELDGRAU     := Color(0.13, 0.16, 0.13)   # uniforme allemand
const KHAKI        := Color(0.20, 0.18, 0.12)   # uniforme allie
const RESISTANCE   := Color(0.14, 0.13, 0.16)   # civils armes
const SKIN         := Color(0.30, 0.21, 0.16)
const BLOOD        := Color(0.16, 0.02, 0.02)
const TRACER       := Color(1.0, 0.62, 0.22)
const MUZZLE       := Color(1.0, 0.78, 0.38)
const FIRE         := Color(1.0, 0.42, 0.12)
const SMOKE        := Color(0.14, 0.13, 0.12)
const SNOW         := Color(0.34, 0.35, 0.38)

## Deterministic slight variation around a base colour, for scatter.
static func vary(base: Color, rng_value: float, amount: float = 0.12) -> Color
```

---

### 2.7 `src/render/textures.gd` - `class_name Tex`

Textures procédurales, mises en cache par nom. Toutes en `ImageTexture`.

```gdscript
class_name Tex
extends RefCounted

const SIZE := 256

## Cached. Known names: "grass", "dirt", "road", "stone", "wheat", "sand",
## "water_normal", "plaster", "wood", "roof_tile", "roof_slate", "concrete",
## "metal", "bark", "leaves", "noise", "cloud".
static func get_texture(texture_name: String) -> Texture2D
## Fractal value noise in [0,1]. Deterministic, no state.
static func noise2d(x: float, y: float, octaves: int = 4) -> float
static func clear_cache() -> void
```

---

### 2.8 `src/render/materials.gd` - `class_name MatLib`

Un seul exemplaire de chaque matériau, partagé par tout le jeu (essentiel pour le
batching). Tous les matériaux sont créés à la première demande.

```gdscript
class_name MatLib
extends RefCounted

## Known keys: "terrain", "road", "water", "stone", "plaster", "wood",
## "roof_tile", "roof_slate", "concrete", "metal", "rust", "glass",
## "foliage", "bark", "wheat", "sandbag", "barbed_wire",
## "uniform_axis", "uniform_allied", "uniform_resistance", "skin",
## "tracer", "muzzle", "blood", "smoke", "flag_axis", "flag_allied",
## "gun_metal", "gun_wood", "marker", "cloth"
static func get_material(key: String) -> Material
## Flat unshaded colour material, cached per colour. For markers and vfx.
static func flat(color: Color, emissive: bool = false) -> Material
## The terrain material is vertex coloured: mesh builders must write COLOR.
static func terrain_material() -> Material
static func clear_cache() -> void
```

Contraintes de rendu (pièges déjà payés) :
- `"foliage"` et `"wheat"` : `cull_mode = CULL_DISABLED`,
  `transparency = TRANSPARENCY_ALPHA_SCISSOR`.
- `"terrain"` : `vertex_color_use_as_albedo = true`, `roughness = 0.95`,
  `metallic = 0.0`.
- Aucun métal noir dans l'ombre : garde `metallic <= 0.6` et `roughness >= 0.3`
  partout.

---

### 2.9 `src/render/sky.gd` - `class_name SkyController extends Node`

Cycle jour/nuit et ambiance. **Ne crée pas de WorldEnvironment**, il lui est
donné.

```gdscript
class_name SkyController
extends Node

signal phase_changed(is_night: bool)

## 0.0 = minuit, 0.5 = midi. Avance tout seul.
var time_of_day: float
## Real seconds for a full day. Default 1200 (20 min).
var day_length: float

func setup(env_holder: WorldEnvironment, sun: DirectionalLight3D, moon: DirectionalLight3D) -> void
func is_night() -> bool
func skip_to(new_time: float) -> void
func time_string() -> String            # "07:42"
## Sun direction, unit vector pointing FROM the sun TOWARDS the world.
func sun_direction() -> Vector3
## 0 = pitch black, 1 = full noon. Used by the AI to shorten sight range.
func light_level() -> float
## Applies the weather mood: 0 clear, 1 overcast. Called by Weather.
func set_overcast(amount: float) -> void
```

Rappels photométriques : `ambient_light_energy` est **inerte** quand
`ambient_light_sky_contribution` vaut 1.0. Pour piloter l'ambiante, baisse la
contribution du ciel vers 0.25 et passe par `ambient_light_color`. Et garde
`fog_sky_affect > 0`, sinon une barre dure apparaît à l'horizon.

---

### 2.10 `src/render/weather.gd` - `class_name Weather extends Node3D`

Pluie, brouillard, vent. Suit le joueur.

```gdscript
class_name Weather
extends Node3D

signal weather_changed(kind: int)

const CLEAR := 0
const OVERCAST := 1
const RAIN := 2
const FOG := 3
const STORM := 4

var kind: int
## 0..1, drives sound and visibility.
var intensity: float

func setup(sky: SkyController, follow: Node3D) -> void
func set_weather(new_kind: int, transition: float = 8.0) -> void
## Visibility multiplier for AI sight range, 1.0 clear down to 0.35 in a storm.
func sight_factor() -> float
func kind_name() -> String   # "Ciel degage", "Couvert", "Pluie", "Brouillard", "Orage"
## Deterministic weather roll for a given world seed and in-game hour.
static func roll(world_seed: int, hour: int) -> int
```

---

### 2.11 `src/world/layout.gd` - `class_name Layout extends RefCounted`

Plan **déterministe** du monde : où sont les villages, les fermes, les routes,
les bunkers. Construit une fois au démarrage, **immuable ensuite**, donc lisible
depuis n'importe quel thread.

```gdscript
class_name Layout
extends RefCounted

# Site kinds
const SITE_VILLAGE := 0
const SITE_FARM := 1
const SITE_CHURCH_TOWN := 2
const SITE_AIRFIELD := 3
const SITE_BUNKER := 4
const SITE_CAMP := 5
const SITE_CROSSROADS := 6
const SITE_BRIDGE := 7
const SITE_RUIN := 8

class Site extends RefCounted:
    var id: int
    var kind: int
    var center: Vector2          # world x, z
    var radius: float            # flattening / footprint radius in metres
    var ground: float            # flattened height, filled by Heightfield.bake_sites()
    var rotation: float          # radians, orientation of the layout
    var seed: int                # per site deterministic seed
    var garrison: int            # number of axis soldiers stationed here
    var display_name: String     # French, e.g. "Sainte-Colombe"
    var is_sector: bool          # true when the site is a capturable objective

var world_seed: int
var sites: Array[Site]
var roads: Array[PackedVector2Array]   # polylines in world x,z
var rivers: Array[PackedVector2Array]

func _init(new_seed: int) -> void      # builds everything, deterministic

func site_by_id(id: int) -> Site       # null if unknown
func sector_ids() -> PackedInt32Array  # ids of sites with is_sector
## Sites whose footprint may touch the given tile (64 m), cheap broad phase.
func sites_in_tile(tx: int, tz: int) -> Array[Site]
func nearest_site(x: float, z: float, kind: int = -1) -> Site
## 1.0 at the road centreline, fading to 0 at ROAD_HALF_WIDTH + ROAD_FADE.
func road_influence(x: float, z: float) -> float
## Same for rivers, used to carve the bed.
func river_influence(x: float, z: float) -> float
## Weight (0..1) and target height of the nearest flattening site.
## Returns Vector2(weight, ground_height).
func site_flatten(x: float, z: float) -> Vector2
## The player's starting point: the allied safehouse of the first village.
func spawn_point() -> Vector2

const ROAD_HALF_WIDTH := 3.5
const ROAD_FADE := 5.0
const SITE_COUNT := 22          # 22 sites, dont 8 secteurs capturables
```

Contraintes de contenu (à respecter, c'est ce qui donne le monde de 1942) :
- Exactement **8 sites `is_sector`** : villages et points stratégiques à libérer.
- Au moins 1 `SITE_AIRFIELD`, 2 `SITE_BUNKER`, 1 `SITE_CHURCH_TOWN`,
  3 `SITE_FARM`, 1 `SITE_BRIDGE`, 1 `SITE_CAMP` (camp de prisonniers),
  1 `SITE_RUIN`.
- Aucun site à moins de 180 m d'un autre.
- Le réseau routier relie tous les sites `is_sector` (arbre couvrant + 2 boucles).
- Noms français plausibles de Normandie, tirés d'une liste en dur.

---

### 2.12 `src/world/heightfield.gd` - `class_name Heightfield extends RefCounted`

Fonction de terrain **pure** (aucun état mutable après `_init`), donc appelable
depuis les threads de génération.

```gdscript
class_name Heightfield
extends RefCounted

const WORLD_SIZE := 4096.0
const HALF := 2048.0
const WATER_LEVEL := 2.0
const TILE_SIZE := 64.0

# Biomes
const B_FIELD := 0        # champ cultive, ble
const B_MEADOW := 1       # prairie, bocage
const B_FOREST := 2
const B_MARSH := 3
const B_ROAD := 4
const B_VILLAGE := 5
const B_WATER := 6
const B_ROCK := 7
const B_ORCHARD := 8

var world_seed: int
var layout: Layout

func _init(new_layout: Layout) -> void
## Terrain height in metres. Deterministic, thread safe, no mutating cache.
func height_at(x: float, z: float) -> float
## Surface normal from finite differences.
func normal_at(x: float, z: float) -> Vector3
func biome_at(x: float, z: float) -> int
func is_water(x: float, z: float) -> bool
## Slope in radians, 0 = flat.
func slope_at(x: float, z: float) -> float
## Surface name for footsteps: "grass","dirt","stone","wood","water".
func surface_at(x: float, z: float) -> String
## Vertex colour of the terrain at this point (already linear, 0.05..0.38).
func color_at(x: float, z: float) -> Color
## Fills every Site.ground of the layout. Called once by GameWorld.setup().
func bake_sites() -> void
## True when the position is inside the playable square minus a 32 m margin.
static func in_bounds(x: float, z: float) -> bool
## Clamps a position back inside the playable area.
static func clamp_to_bounds(pos: Vector3) -> Vector3
```

Le relief attendu : bocage normand vallonné (amplitude 25 m environ), une crête
au nord, des marais au sud-ouest, une rivière traversante, une plage et une
falaise sur le bord est. Les routes et les sites sont **aplanis** (le terrain
suit `Layout.site_flatten` et `Layout.road_influence`).

---

### 2.13 `src/world/scatter.gd` - `class_name Scatter extends RefCounted`

Décide **quoi pousse où**, de façon déterministe et sans toucher à la scène.
Appelé depuis les threads de génération.

```gdscript
class_name Scatter
extends RefCounted

# Prop kinds
const P_TREE_OAK := 0
const P_TREE_PINE := 1
const P_TREE_APPLE := 2
const P_BUSH := 3
const P_HEDGE := 4          # segment de bocage
const P_ROCK := 5
const P_GRASS_TUFT := 6
const P_WHEAT := 7
const P_FENCE := 8
const P_WRECK := 9          # epave de vehicule
const P_CRATER := 10
const P_SANDBAG := 11
const P_POLE := 12          # poteau telegraphique
const P_HAYSTACK := 13
const KIND_COUNT := 14

class Instance extends RefCounted:
    var kind: int
    var position: Vector3
    var rotation: float       # radians around Y
    var scale: float
    var tint: Color

## Every prop instance for one 64 m tile. Deterministic on (seed, tx, tz).
static func for_tile(hf: Heightfield, tx: int, tz: int) -> Array[Instance]
## True when the prop kind should get a collision body (trees, rocks, hedges).
static func has_collision(kind: int) -> bool
## Collision cylinder radius and height for a colliding kind, Vector2(r, h).
static func collision_size(kind: int, prop_scale: float) -> Vector2
## Whether the kind is drawn as a MultiMesh (true) or a full node (false).
static func is_batched(kind: int) -> bool
```

---

### 2.14 `src/world/meshes.gd` - `class_name Meshes extends RefCounted`

Bibliothèque de maillages procéduraux **partagés** (un seul exemplaire par forme,
mis en cache). Aucune dépendance à la scène.

```gdscript
class_name Meshes
extends RefCounted

## Cached prop meshes, one per Scatter kind. Returns an ArrayMesh whose
## surfaces already carry their material.
static func prop_mesh(kind: int, variant: int = 0) -> Mesh
## Simple building blocks, cached by their arguments.
static func box(size: Vector3, material_key: String) -> Mesh
static func cylinder(radius: float, height: float, sides: int, material_key: String) -> Mesh
static func sphere(radius: float, material_key: String) -> Mesh
## A humanoid body, built from boxes. `faction` is War.ALLIED / War.AXIS / War.NEUTRAL.
## Returns a Node3D whose children are named exactly:
## "Hips","Torso","Head","Helmet","ArmL","ArmR","LegL","LegR","Weapon"
static func soldier_body(faction: int, variant: int) -> Node3D
## Weapon world model (dropped or carried by AI), by weapon id from WeaponDefs.
static func weapon_model(weapon_id: int) -> Mesh
static func clear_cache() -> void
```

---

### 2.15 `src/world/structures.gd` - `class_name Structures extends RefCounted`

Constructeurs de bâtiments. Chaque fonction retourne un `Node3D` **complet** :
visuel (`MeshInstance3D`) et collision (`StaticBody3D` sur la couche
`Layers.STRUCTURE`).

```gdscript
class_name Structures
extends RefCounted

## A cover point exposed by a built structure, for the AI.
class CoverPoint extends RefCounted:
    var position: Vector3
    var normal: Vector3     # direction the cover protects FROM
    var is_high: bool       # true = standing cover, false = crouch only

## Every builder takes an RNG so a site is reproducible, and appends its cover
## points to `cover_out`. Coordinates are LOCAL to the returned node.
static func house(rng: RandomNumberGenerator, width: float, depth: float, floors: int, cover_out: Array) -> Node3D
static func barn(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func church(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func bunker(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func hangar(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func watchtower(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func sandbag_ring(rng: RandomNumberGenerator, radius: float, cover_out: Array) -> Node3D
static func trench(rng: RandomNumberGenerator, length: float, cover_out: Array) -> Node3D
static func stone_wall(rng: RandomNumberGenerator, length: float, height: float, cover_out: Array) -> Node3D
static func fuel_depot(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func aa_gun(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func radio_mast(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func prison_cage(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func ruin(rng: RandomNumberGenerator, cover_out: Array) -> Node3D
static func bridge(rng: RandomNumberGenerator, span: float, cover_out: Array) -> Node3D
```

Les bâtiments doivent être **entrables** quand c'est logique (maisons, grange,
église, bunker, hangar) : une porte au minimum, un intérieur creux, un sol.

---

### 2.16 `src/world/site_builder.gd` - `class_name SiteBuilder extends RefCounted`

Assemble un site complet à partir de `Structures`.

```gdscript
class_name SiteBuilder
extends RefCounted

## The result of building one site.
class BuiltSite extends RefCounted:
    var site_id: int
    var node: Node3D
    var cover: Array              # Array[Structures.CoverPoint], WORLD space
    var patrol_points: PackedVector3Array
    var garrison_spawns: PackedVector3Array
    var interest_points: PackedVector3Array
    var objective_anchors: Dictionary   # String -> Vector3: "fuel","radio","flag","cage","officer","aa"

## Builds the site at its world position, terrain aligned. The returned node is
## NOT yet in the tree; the caller adds it.
static func build(site: Layout.Site, hf: Heightfield) -> BuiltSite
```

---

### 2.17 `src/world/terrain_chunk.gd` - `class_name TerrainChunk extends Node3D`

Une tuile de 64 m : maillage LOD, collision, végétation en MultiMesh.

```gdscript
class_name TerrainChunk
extends Node3D

const TILE := 64.0
## Vertex grid per LOD level, index = lod. LOD 0 is the finest.
const LOD_RES: PackedInt32Array = [32, 16, 8, 4]
const LOD_COUNT := 4

var tx: int
var tz: int
var lod: int

## Data produced off thread. Pure function, no scene access, safe on a worker.
static func build_data(hf: Heightfield, tile_x: int, tile_z: int, level: int) -> Dictionary
## Applies data built by build_data. Main thread only.
func apply(hf: Heightfield, tile_x: int, tile_z: int, level: int, data: Dictionary) -> void
## Swaps the visual LOD. Returns true when the chunk needs a rebuild because the
## data for that lod is missing.
func set_lod(new_lod: int) -> bool
## Adds/removes the HeightMapShape3D collision (only the closest ring has it).
func set_collision_enabled(enabled: bool) -> void
func has_collision() -> bool
```

Le dictionnaire de `build_data` contient au minimum les clés `"mesh_arrays"`
(Array de taille `Mesh.ARRAY_MAX`), `"heights"` (`PackedFloat32Array` de 33 x 33
pour le LOD 0, vide sinon), `"props"` (`Array[Scatter.Instance]`) et `"aabb"`
(`AABB`).

Le maillage doit avoir une **jupe** (skirt) de 3 m sur son bord pour cacher les
fissures entre LOD différents.

---

### 2.18 `src/world/world.gd` - `class_name GameWorld extends Node3D`

Streaming. Node `World` de la scène principale.

```gdscript
class_name GameWorld
extends Node3D

signal world_ready()
signal chunk_ready(tile: Vector2i)

func setup(world_seed: int) -> void
func layout() -> Layout
func heightfield() -> Heightfield
## Called every frame by Main with the player position.
func update_streaming(focus: Vector3) -> void
## Ground height under a world position (terrain only, ignores structures).
func ground_y(x: float, z: float) -> float
## Player spawn, on the ground, already offset to standing height.
func spawn_point() -> Vector3
## True once the tile under `pos` has its collision in place. Main waits on this
## before releasing the player, otherwise he falls through the world.
func is_ground_ready(pos: Vector3) -> bool
## Cover points of every loaded site, for the AI.
func cover_points_near(pos: Vector3, radius: float) -> Array
## The BuiltSite for a site id, or null when it is not streamed in.
func built_site(site_id: int) -> SiteBuilder.BuiltSite
## Joins the worker threads and frees everything. MUST be called before the
## scene is reloaded or the process hangs on exit.
func shutdown() -> void
func loaded_chunk_count() -> int
func debug_line() -> String
```

---

### 2.19 `src/weapons/weapon_defs.gd` - `class_name WeaponDefs extends RefCounted`

Table de données. Aucune logique de tir.

```gdscript
class_name WeaponDefs
extends RefCounted

const NONE := -1
const M1_GARAND := 0
const THOMPSON := 1
const SPRINGFIELD := 2
const M1911 := 3
const MP40 := 4
const KAR98K := 5
const MG42 := 6
const GRENADE := 7
const COUNT := 8

# Slots
const SLOT_PRIMARY := 0
const SLOT_SECONDARY := 1
const SLOT_THROWN := 2

static func display_name(id: int) -> String        # francais: "Fusil M1 Garand"
static func slot_of(id: int) -> int
static func damage(id: int) -> float
static func headshot_multiplier(id: int) -> float
## Damage multiplier at a given distance (falloff curve).
static func falloff(id: int, distance: float) -> float
static func rpm(id: int) -> float
static func is_automatic(id: int) -> bool
static func magazine(id: int) -> int
static func reserve_max(id: int) -> int
static func reload_time(id: int) -> float
## Partial reload (magazine fed) vs full clip (en bloc / stripper).
static func reloads_per_round(id: int) -> bool
static func spread_hip(id: int) -> float           # radians
static func spread_aim(id: int) -> float
static func recoil_pitch(id: int) -> float         # radians per shot
static func recoil_yaw(id: int) -> float
static func aim_fov_scale(id: int) -> float        # 1.0 = pas de zoom
static func has_scope(id: int) -> bool
static func muzzle_velocity(id: int) -> float
static func fire_sample(id: int) -> String         # cle SfxLib
static func reload_sample(id: int) -> String
static func penetration(id: int) -> float          # 0..1
static func ammo_type(id: int) -> int
static func weight(id: int) -> float
static func is_axis_weapon(id: int) -> bool
static func all_ids() -> PackedInt32Array
```

Équilibrage attendu (respecte l'esprit, ajuste les chiffres si besoin) :
Garand 8 coups semi-auto 42 dmg, Thompson 30 coups 700 rpm 26 dmg, Springfield 5
coups verrou 85 dmg lunette x4, M1911 7 coups 34 dmg, MP40 32 coups 550 rpm
25 dmg, Kar98k 5 coups verrou 78 dmg, MG42 1200 rpm 30 dmg.

---

### 2.20 `src/weapons/ballistics.gd` - `class_name Ballistics extends RefCounted`

Le tir. Aucune dépendance à l'interface ni à l'IA.

```gdscript
class_name Ballistics
extends RefCounted

class HitResult extends RefCounted:
    var hit: bool
    var position: Vector3
    var normal: Vector3
    var collider: Object
    var distance: float
    var headshot: bool
    var surface: String       # "dirt","stone","wood","metal","flesh","water"

## Fires one bullet. `spread` is the cone half angle in radians. Applies damage
## to whatever it hits (anything exposing take_damage) and returns where it
## landed. `shooter` is excluded from the raycast.
static func fire(world_3d: World3D, origin: Vector3, direction: Vector3,
        weapon_id: int, spread: float, shooter: Node, rng: RandomNumberGenerator) -> HitResult
## Raw line of sight test, no damage. True when nothing blocks the segment.
static func line_of_sight(world_3d: World3D, from: Vector3, to: Vector3, ignore: Array) -> bool
## Surface name deduced from the collider, for impact sound and decal colour.
static func surface_of(collider: Object) -> String
## Explosion damage in a radius, with falloff and line of sight checks.
static func explode(world_3d: World3D, center: Vector3, radius: float,
        max_damage: float, source: Node) -> void
```

Une tête est touchée quand le point d'impact est au-dessus de
`collider.head_height()` si le collider expose cette méthode, sinon jamais.

---

### 2.21 `src/weapons/vfx.gd` - `class_name Vfx extends Node3D`

Node `Vfx` de la scène, dans le groupe `"vfx"`. Effets visuels mutualisés,
**pool** obligatoire (aucune allocation par balle après la montée en régime).

```gdscript
class_name Vfx
extends Node3D

func setup() -> void
func tracer(from: Vector3, to: Vector3, speed: float) -> void
func muzzle_flash(at: Vector3, direction: Vector3, size: float = 1.0) -> void
func impact(at: Vector3, normal: Vector3, surface: String) -> void
func blood(at: Vector3, normal: Vector3) -> void
func explosion(at: Vector3, radius: float) -> void
func smoke_column(at: Vector3, seconds: float) -> void
func shell_casing(at: Vector3, direction: Vector3) -> void
## A floating world space marker (objective diamond). Returns its id.
func add_marker(at: Vector3, color: Color, label: String) -> int
func move_marker(marker_id: int, at: Vector3) -> void
func remove_marker(marker_id: int) -> void
func clear_all() -> void
```

---

### 2.22 `src/weapons/weapon.gd` - `class_name Weapon extends RefCounted`

État runtime d'**une** arme. Pas un noeud.

```gdscript
class_name Weapon
extends RefCounted

var id: int
var in_magazine: int
var reserve: int
var is_reloading: bool

func _init(weapon_id: int, full: bool = true) -> void
## True when the trigger can produce a shot right now. `now` is seconds.
func can_fire(now: float) -> bool
## Consumes a round and stamps the cooldown. Returns false when it could not.
func fire(now: float) -> bool
func needs_reload() -> bool
func can_reload() -> bool
## Starts a reload. Returns the duration, or 0.0 when it cannot start.
func start_reload(now: float) -> float
## Advances the reload; call every frame. Returns true the frame it completes.
func tick_reload(now: float) -> bool
func cancel_reload() -> void
func add_ammo(rounds: int) -> int      # returns the amount actually taken
func ammo_string() -> String           # "8 / 64"
func current_spread(is_aiming: bool, is_moving: bool, is_crouched: bool) -> float
func to_dict() -> Dictionary
func from_dict(data: Dictionary) -> void
```

---

### 2.23 `src/player/camera_rig.gd` - `class_name CameraRig extends Node3D`

Recul, balancement, visée, secousses. Enfant du joueur, créé par lui.

```gdscript
class_name CameraRig
extends Node3D

var camera: Camera3D
var yaw: float
var pitch: float

func setup() -> void
## Mouse look. Applies Game.mouse_sensitivity and Game.invert_y.
func look(relative: Vector2) -> void
## Adds a recoil kick. Both in radians.
func add_recoil(pitch_kick: float, yaw_kick: float) -> void
## Per frame update: recoil recovery, bob, sway, aim transition.
func update(delta: float, velocity: Vector3, is_grounded: bool, is_aiming: bool,
        aim_fov_scale: float, stance_height: float) -> void
## Camera shake, e.g. explosions. `amount` in radians.
func shake(amount: float, seconds: float) -> void
## Where a bullet leaves from and where it goes.
func aim_ray() -> Transform3D
func forward() -> Vector3
func set_base_fov(fov: float) -> void
```

---

### 2.24 `src/player/player.gd` - `class_name Player extends CharacterBody3D`

Contrôleur FPS, santé, armes. **Dans les groupes `"damageable"` et `"player"`.**
Couche `Layers.PLAYER`, masque `Layers.WALK_MASK`.

```gdscript
class_name Player
extends CharacterBody3D

signal health_changed(current: float, maximum: float)
signal died()
signal weapon_changed(weapon: Weapon)
signal ammo_changed(weapon: Weapon)
signal damaged(amount: float, from_direction: Vector3)
signal footstep(surface: String)
signal fired(weapon_id: int)
signal used(target: Node)
signal bandages_changed(count: int)

const MAX_HEALTH := 100.0
const STAND_HEIGHT := 1.80
const CROUCH_HEIGHT := 1.20
const PRONE_HEIGHT := 0.60
const EYE_OFFSET := 0.12          # eyes below the top of the capsule

var health: float
var rig: CameraRig
var weapons: Array[Weapon]        # index = WeaponDefs.SLOT_*
var current_slot: int
var bandages: int
var is_aiming: bool
var is_sprinting: bool
var stance: int                   # 0 debout, 1 accroupi, 2 couche

func setup(game_world: GameWorld) -> void
func teleport(pos: Vector3) -> void
## Contract shared by every damageable in the project. See section 3.
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void
func heal(amount: float) -> void
func revive(pos: Vector3) -> void
func head_height() -> float
func is_alive() -> bool
func eye_position() -> Vector3
func aim_direction() -> Vector3
func current_weapon() -> Weapon   # may be null
func give_weapon(weapon_id: int, ammo: int) -> void
func give_ammo(weapon_id: int, rounds: int) -> int
func give_bandage(count: int) -> void
func select_slot(slot: int) -> void
func cycle_weapon(direction: int) -> void
func noise_radius() -> float      # how far the AI can hear the player right now
func to_dict() -> Dictionary
func from_dict(data: Dictionary) -> void
```

Le joueur ne gère **pas** l'affichage de l'arme : c'est `Viewmodel` (2.25), que
le joueur crée et pilote.

---

### 2.25 `src/weapons/viewmodel.gd` - `class_name Viewmodel extends Node3D`

Le modèle d'arme en vue première personne. Enfant de la caméra.

```gdscript
class_name Viewmodel
extends Node3D

func setup() -> void
func show_weapon(weapon_id: int) -> void
func play_fire() -> void
func play_reload(seconds: float, per_round: bool) -> void
func play_melee() -> void
func set_aiming(aiming: bool) -> void
## Muzzle position in world space, where the flash and tracer start.
func muzzle_position() -> Vector3
func update(delta: float, velocity: Vector3, is_aiming: bool) -> void
```

---

### 2.26 `src/weapons/grenade.gd` - `class_name Grenade extends RigidBody3D`

```gdscript
class_name Grenade
extends RigidBody3D

const FUSE := 3.6

func setup(thrower: Node, impulse: Vector3) -> void
func detonate() -> void
```

Elle explose via `Ballistics.explode(world_3d, position, 9.0, 130.0, thrower)`,
joue le son et demande l'effet à `Vfx` par le groupe `"vfx"`.

---

### 2.27 `src/ai/senses.gd` - `class_name Senses extends RefCounted`

Perception partagée par tous les combattants IA.

```gdscript
class_name Senses
extends RefCounted

## Sight cone half angle in radians (about 60 degrees each side).
const FOV_HALF := 1.05

## Can the observer see `target` right now? Accounts for distance, cone, line of
## sight, light level and weather.
static func can_see(observer: Node3D, eye: Vector3, facing: Vector3,
        target: Node3D, target_point: Vector3, max_range: float,
        light: float, visibility: float) -> bool
## Sight range in metres for a given light level and weather factor.
static func sight_range(base_range: float, light: float, visibility: float) -> float
## Did the observer hear a noise of `radius` metres emitted at `at`?
static func can_hear(ear: Vector3, at: Vector3, radius: float) -> bool
```

---

### 2.28 `src/ai/soldier.gd` - `class_name Soldier extends CharacterBody3D`

Le combattant, allemand ou allié selon sa faction. **Groupes obligatoires :
`"damageable"`, plus `"axis"` ou `"allies"` selon la faction.**

```gdscript
class_name Soldier
extends CharacterBody3D

signal died(soldier: Soldier)
signal spotted_enemy(soldier: Soldier, target: Node3D)
signal fired_shot(soldier: Soldier)

# States
const S_IDLE := 0
const S_PATROL := 1
const S_ALERT := 2       # a entendu quelque chose, cherche
const S_COMBAT := 3
const S_ADVANCE := 4
const S_COVER := 5
const S_FLANK := 6
const S_RETREAT := 7
const S_DEAD := 8
const S_SUPPRESSED := 9

# Ranks, drive health / accuracy / weapon
const R_CONSCRIPT := 0
const R_REGULAR := 1
const R_VETERAN := 2
const R_OFFICER := 3
const R_SNIPER := 4
const R_MACHINE_GUNNER := 5

var faction: int         # War.AXIS ou War.ALLIED
var rank: int
var state: int
var health: float
var target: Node3D

## `home` is the anchor the soldier patrols around.
func setup(game_world: GameWorld, faction_id: int, soldier_rank: int, home: Vector3) -> void
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void
func head_height() -> float
func is_alive() -> bool
func eye_position() -> Vector3
func set_patrol_route(points: PackedVector3Array) -> void
func set_cover_points(points: Array) -> void
func order_move_to(pos: Vector3) -> void
func order_hold(pos: Vector3) -> void
func alert_to(pos: Vector3, certainty: float) -> void
func notice_enemy(enemy: Node3D) -> void
func suppress(amount: float) -> void
func state_name() -> String
func faction_name() -> String
```

Locomotion : **pas de NavigationServer**. Pilotage direct (`move_and_slide`) avec
suivi du terrain par `GameWorld.ground_y`, évitement local par trois rayons
(whiskers) devant le soldat, contournement des murs par glissement. Un soldat
coincé plus de 3 s se retéléporte sur son point d'ancrage.

---

### 2.29 `src/ai/squad.gd` - `class_name Squad extends Node3D`

Groupe de 3 à 6 soldats au comportement coordonné.

```gdscript
class_name Squad
extends Node3D

signal wiped(squad: Squad)

var faction: int
var members: Array[Soldier]

func setup(game_world: GameWorld, faction_id: int, spawn: Vector3, size: int, patrol: PackedVector3Array) -> void
func alive_count() -> int
## Shared knowledge: one member seeing the player alerts everyone in the squad.
func report_contact(enemy: Node3D, at: Vector3) -> void
func order_attack(pos: Vector3) -> void
func order_defend(pos: Vector3, radius: float) -> void
func despawn() -> void
func center() -> Vector3
```

---

### 2.30 `src/ai/emplacement.gd` - `class_name Emplacement extends Node3D`

Nid de MG42 ou canon anti-aérien. Utilisable par l'IA **et** par le joueur
(touche `use`). Dans le groupe `"damageable"`.

```gdscript
class_name Emplacement
extends Node3D

const KIND_MG := 0
const KIND_AA := 1

signal destroyed(emplacement: Emplacement)

var kind: int
var faction: int
var operator_node: Node3D

func setup(game_world: GameWorld, emplacement_kind: int, faction_id: int) -> void
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void
func is_alive() -> bool
## Player mounts it. Returns false when it is destroyed or already taken.
func mount(user: Node3D) -> bool
func dismount() -> void
func is_mounted() -> bool
## Called every frame while mounted by the player, with the aim direction.
func aim_at(direction: Vector3) -> void
func fire_burst(shooter: Node) -> void
func head_height() -> float
```

---

### 2.31 `src/mission/mission_defs.gd` - `class_name MissionDefs extends RefCounted`

Table de données des objectifs. Aucune logique.

```gdscript
class_name MissionDefs
extends RefCounted

# Objective kinds
const O_CAPTURE := 0        # tenir la zone jusqu'a ce qu'il n'y ait plus d'axe
const O_DESTROY := 1        # detruire une cible (depot, canon, mat radio)
const O_RESCUE := 2         # liberer des prisonniers
const O_ASSASSINATE := 3    # tuer un officier
const O_SABOTAGE := 4       # poser une charge et s'eloigner
const O_DEFEND := 5         # tenir une position pendant N secondes
const O_RECON := 6          # atteindre un point d'observation
const O_AMBUSH := 7         # detruire un convoi

class Objective extends RefCounted:
    var id: int
    var kind: int
    var sector_id: int          # Layout.Site.id
    var title: String           # francais
    var description: String     # francais
    var position: Vector3
    var radius: float
    var target_count: int
    var time_limit: float       # 0 = pas de limite
    var reward_text: String
    var prerequisite: int       # id d'un autre objectif, -1 si aucun

## Builds the full campaign objective list from the world layout.
static func build_campaign(layout: Layout, world: GameWorld) -> Array
static func kind_name(kind: int) -> String       # francais
static func kind_icon(kind: int) -> String       # un seul caractere pour le HUD
```

---

### 2.32 `src/mission/objectives.gd` - `class_name ObjectiveTracker extends Node`

Suit l'avancement. Node `Objectives` de la scène.

```gdscript
class_name ObjectiveTracker
extends Node

signal objective_started(obj: MissionDefs.Objective)
signal objective_progress(obj: MissionDefs.Objective, current: int, total: int)
signal objective_completed(obj: MissionDefs.Objective)
signal objective_failed(obj: MissionDefs.Objective)
signal campaign_completed()

func setup(game_world: GameWorld, player_node: Player) -> void
func active() -> Array                  # Array[MissionDefs.Objective]
func current() -> MissionDefs.Objective # la plus proche active, ou null
func all_objectives() -> Array
func is_done(objective_id: int) -> bool
func start(objective_id: int) -> void
## Called by the rest of the game to feed progress.
func report_kill(victim: Node, killer: Node) -> void
func report_destroyed(tag: String, position: Vector3) -> void
func report_rescued(count: int) -> void
func report_player_in_zone(objective_id: int, inside: bool) -> void
func progress_of(objective_id: int) -> Vector2   # (current, total)
func to_dict() -> Dictionary
func from_dict(data: Dictionary) -> void
```

---

### 2.33 `src/mission/director.gd` - `class_name Director extends Node`

Peuple le monde : garnisons des sites, patrouilles dynamiques, renforts selon le
niveau d'alerte, ambiance (bombardier qui passe, artillerie lointaine).

```gdscript
class_name Director
extends Node

signal event_announced(text: String)

func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void
## Called every frame by Main.
func tick(delta: float) -> void
func live_soldier_count() -> int
func live_squad_count() -> int
## Forces a reinforcement wave towards a position (used by objectives).
func send_reinforcements(pos: Vector3, count: int) -> void
## Frees every spawned squad. Called on shutdown.
func clear_all() -> void
func debug_line() -> String
```

Budget : jamais plus de **60 soldats vivants** ni **14 escouades** simultanément.
Les escouades à plus de 320 m du joueur et hors combat sont recyclées.

---

### 2.34 `src/ui/hud.gd` - `class_name Hud extends CanvasLayer`

```gdscript
class_name Hud
extends CanvasLayer

func setup(player_node: Player, tracker: ObjectiveTracker, sky_ctl: SkyController,
        weather_node: Weather, game_world: GameWorld) -> void
func show_toast(text: String, seconds: float = 2.2) -> void
## Big centred banner, for a captured sector or a failed mission.
func show_banner(title: String, subtitle: String, seconds: float = 3.5) -> void
func flash_damage(from_direction: Vector3) -> void
func flash_hitmarker(killed: bool, headshot: bool) -> void
func set_paused(paused: bool) -> void
func set_prompt(text: String) -> void      # "" pour cacher l'invite d'action
func refresh_settings() -> void
```

Contenu attendu : réticule dynamique (s'ouvre avec la dispersion), vignette rouge
de santé plus une jauge discrète, compteur de munitions, grenades, boussole en
haut avec les objectifs, objectif courant à gauche, indicateur de direction des
dégâts, niveau d'alerte, chronomètre d'objectif, compteur FPS optionnel, et le
masque noir de lunette quand l'arme a une lunette et que le joueur vise.

---

### 2.35 `src/ui/map_ui.gd` - `class_name MapUi extends Control`

Carte plein écran (touche M). Dessinée en `_draw()`, pas de texture.

```gdscript
class_name MapUi
extends Control

signal closed()

func setup(game_world: GameWorld, player_node: Player, tracker: ObjectiveTracker) -> void
func open() -> void
func close() -> void
func is_open() -> bool
```

---

### 2.36 `src/ui/objectives_ui.gd` - `class_name ObjectivesUi extends Control`

Journal des missions (touche J).

```gdscript
class_name ObjectivesUi
extends Control

signal closed()
signal objective_selected(objective_id: int)

func setup(tracker: ObjectiveTracker) -> void
func open() -> void
func close() -> void
func is_open() -> bool
```

---

### 2.37 `src/ui/pause_menu.gd` - `class_name PauseMenu extends Control`

```gdscript
class_name PauseMenu
extends Control

signal resume_requested()
signal save_requested()
signal restart_requested()
signal quit_requested()

func setup() -> void
func open() -> void
func close() -> void
func is_open() -> bool
```

Onglets : Reprendre, Réglages (sensibilité, inversion Y, FOV, distance de vue,
volumes, difficulté, plein écran, FPS, sang, bob de caméra), Statistiques (kills,
précision, secteurs), Sauvegarder, Recommencer, Quitter.

---

### 2.38 `src/save/save_manager.gd` - `class_name SaveManager extends RefCounted`

```gdscript
class_name SaveManager
extends RefCounted

const SAVE_DIR := "user://saves"

static func save_path(campaign: String) -> String
static func write(campaign: String, data: Dictionary) -> bool
static func read(campaign: String) -> Dictionary     # {} quand absent
static func has_save(campaign: String) -> bool
static func erase(campaign: String) -> bool
static func list_campaigns() -> PackedStringArray
```

---

## 3. Contrat de dégâts (le plus important)

Tout ce qui peut être touché est dans le groupe `"damageable"` et expose
**exactement** :

```gdscript
func take_damage(amount: float, attacker: Node, hit_point: Vector3, headshot: bool) -> void
func is_alive() -> bool
func head_height() -> float     # Y monde au dessus duquel c'est la tete
```

`Ballistics` teste `has_method("take_damage")` avant d'appeler, donc un objet qui
oublie une de ces méthodes est simplement invulnérable au lieu de planter. Écris
les trois.

## 4. Contrat des effets visuels

`Vfx` est dans le groupe `"vfx"`. N'importe quel module obtient l'instance par :

```gdscript
var vfx_nodes := get_tree().get_nodes_in_group("vfx")
if not vfx_nodes.is_empty():
    (vfx_nodes[0] as Vfx).impact(point, normal, surface)
```

Ne stocke jamais une référence à `Vfx` prise dans `_ready()` : le noeud peut
apparaître après toi.

## 5. Arbre de la scène principale (`scenes/main.tscn`)

```
Main                      Node3D          src/main.gd
├─ World                  Node3D          src/world/world.gd        (GameWorld)
├─ Player                 CharacterBody3D src/player/player.gd      (Player)
├─ WorldEnvironment       WorldEnvironment
├─ Sun                    DirectionalLight3D
├─ Moon                   DirectionalLight3D
├─ Sky                    Node            src/render/sky.gd         (SkyController)
├─ Weather                Node3D          src/render/weather.gd     (Weather)
├─ Vfx                    Node3D          src/weapons/vfx.gd        (Vfx)
├─ Director               Node            src/mission/director.gd   (Director)
├─ Objectives             Node            src/mission/objectives.gd (ObjectiveTracker)
├─ Hud                    CanvasLayer     src/ui/hud.gd             (Hud)
└─ Screens                CanvasLayer
   ├─ MapUi               Control         src/ui/map_ui.gd
   ├─ ObjectivesUi        Control         src/ui/objectives_ui.gd
   └─ PauseMenu           Control         src/ui/pause_menu.gd
```

`main.gd` fait le câblage et **rien d'autre** : il appelle `setup()` sur chaque
sous-système dans l'ordre des dépendances, route les entrées globales (pause,
carte, journal, plein écran, capture), et sauvegarde avant de quitter.

Ordre de `setup()` imposé :
`world` → `sky` → `weather` → `vfx` → `player` → `objectives` → `director` →
`hud` → écrans.

## 6. Harnais de test

- `tests/test_case.gd` (`class_name WarTest`) : classe de base, mêmes garde-fous
  que CUBEFORGE (`done()` obligatoire en dernière instruction, au moins une
  vérification par méthode).
- `tests/run_tests.gd` : `SceneTree` headless,
  `godot --headless --path . --script res://tests/run_tests.gd`.
- `tests/smoke_probe.gd` : sonde d'intégration dans le vrai jeu,
  `godot --headless --path . -- --smoke`.
- `main.gd` doit exposer les trois crochets `--smoke`, `--shot <dossier>` et
  `--probe res://...`, comme CUBEFORGE.

**Piège à connaître** : avec `--script <MainLoop>`, Godot n'enregistre pas les
autoloads du projet, donc tout fichier qui mentionne `Game`, `War` ou `Sfx`
refuse de compiler dans ce contexte. Les suites unitaires doivent donc être
chargées par `load()` **à l'exécution**, et tout test qui a besoin des autoloads
passe par la sonde `--smoke`.
