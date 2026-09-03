# PRD - VIEWPOINT

Document de cadrage produit. Version 1.0, 2026-08-31.

Règles d'écriture héritées des projets Godot du dépôt : texte joueur en
français, code et commentaires en anglais, jamais de tiret cadratin, aucune
signature inter-module ne change sans passer par ce document (section 7).

---

## 1. Vision

VIEWPOINT est un puzzle game 3D à la première personne inspiré de la mécanique
centrale de **Viewfinder** (Sad Owl Studios, 2023) : le joueur trouve des
photos dans le décor, les tient devant lui, et **pose** la photo dans le monde.
Au moment de la pose, le contenu de la photo **se matérialise en vrais objets
3D** alignés exactement sur le point de vue du joueur, accompagnés le cas
échéant d'une **image de fond** (backdrop) qui devient un mur physique du
décor. L'effet d'optique doit être parfait : ce que le joueur voit en
prévisualisation est, au pixel près de la géométrie, ce qui apparaît quand il
clique.

Périmètre volontairement réduit pour une v1 solide :

- **25 niveaux courts** (2 à 4 minutes chacun), des îlots flottants dans un ciel
  pastel. La v1 en livrait 5 ; la v2 a porté le compte à 15, la v3 à 20 et la
  v6 à 25 (section 10).
- **Pas d'appareil photo** : le joueur ne prend pas de photo, il ne fait que
  poser des photos trouvées. L'architecture réserve explicitement la place de
  cette évolution (section 9).
- **Navigation entre niveaux par téléporteur** : chaque niveau contient un
  téléporteur qui exige un nombre de **piles** (batteries). Les piles se
  trouvent dans le décor, ou se **dupliquent** en posant une photo qui contient
  une pile.
- Aucun asset binaire : géométrie, matériaux, vignettes de photos et ciel sont
  générés par code, comme les autres jeux Godot du dépôt.

## 2. Boucle de jeu

1. Le joueur apparaît sur un îlot, repère le téléporteur et son exigence
   (« 0 / 2 piles »).
2. Il explore, ramasse une photo (touche E). Une **prévisualisation fantôme**
   du contenu s'affiche, accrochée à sa caméra : elle bouge avec son regard.
3. Il cadre l'endroit voulu et pose (clic gauche). Le contenu devient solide :
   passerelle, escalier, pile, porte... Les objets du monde marqués
   « effaçables » qui se trouvaient dans le champ de la photo sont supprimés
   (remplacés par le contenu de la photo).
4. Il ramasse les piles, les insère dans le téléporteur (E), puis se téléporte
   (E à nouveau) vers le niveau suivant.
5. Après le niveau 25, écran de victoire.

Une chute dans le vide est la seule façon de perdre, et elle coûte le niveau
entier : passé le plan de rattrapage (`kill_y`), le niveau est **reconstruit
depuis sa définition** (poses effacées, photos consommées rendues, piles
portées remises dans le décor), exactement comme la touche R. Le joueur
signale sa chute par `Player.fell_out` et `Main` rebâtit en différé, un pas
de physique ne pouvant pas libérer ses propres corps de collision.

## 3. La mécanique photo, en détail

### 3.1 Définition d'une photo

Une photo est une **donnée déclarative** (`PhotoDefs`), pas une scène : un
identifiant, un titre, une liste de **props** exprimés dans l'espace caméra
(x droite, y haut, -z devant), et un **backdrop optionnel** (distance + couleurs).
Props supportés en v1 : `box`, `cylinder`, `battery`, `bridge` (tablier +
rambardes), `stairs` (volée de marches générée), `arch` (portique).

### 3.2 Ancre de pose et effet d'optique

L'ancre de pose est la **transformée globale complète de la caméra** au moment
du clic (position + lacet + tangage). Le fantôme de prévisualisation est un
enfant direct de la caméra avec une transformée locale identité : il occupe
donc exactement la place que le contenu solide occupera. C'est cette égalité
stricte fantôme = solide qui garantit l'effet d'optique parfait. Aucune
« correction » d'assiette n'est appliquée : poser en regardant vers le bas
donne un pont incliné, c'est un choix de gameplay assumé (et exploitable).

### 3.3 Matérialisation : le remplacement total (v4)

Toute photo est la représentation 2D d'un espace 3D : des props 3D devant un
**fond 2D peint obligatoire** (`backdrop`). Jusqu'en v6.1, `erase_depth` était
égal à la profondeur de ce fond, qui servait donc de couvercle à la découpe :
un mur plein se plantait au bout du contenu, et une passerelle de 8 m menait
dans un ciel solide à 9,5 m. Le fond se tient maintenant **trois fois plus
loin**, comme lointain de l'image, et `erase_depth` n'a pas bougé. La poser
REMPLACE tout ce qui est dans sa perspective par son contenu ; une photo
VIDE (fond seul) perce donc murs, sols et cages, et peint son fond.

À la pose :

1. L'ancre `T` = transformée globale caméra.
2. **Remplacement, deux passes** dans le **frustum de la photo** (fov 50
   degrés, carré, profondeur = `erase_depth`, qui depuis la v6.1 est bien
   plus courte que la distance du fond peint) :
   - groupe `carvable`, c'est-à-dire **la moitié éphémère du langage du sol**
     (section 3.6) : lavande et sol pâle. Chaque bloc ne perd que la partie
     de son volume prise dans le frustum. Le trou est l'AABB locale de
     l'intersection échantillonnée, et le reste survit en fragments (boîte
     moins boîte, 6 morceaux au plus), eux-mêmes découpables. Un mur plus
     large que le cadre n'est donc percé que là où la photo est posée. Le
     sol gris, les décors et les contenus déjà posés ne sont pas dans ce
     groupe : la photo **s'ajoute** à eux.
   - groupe `breakable` (les cages, TOUTES cassables, permanentes comprises ;
     la différence lavande/sombre est un indice de lore) : disparition
     entière quand le centre du corps tombe dans le frustum.
   Ne sont JAMAIS remplacés : téléporteur, piles, objets photo, appareil,
   joueur. **Règle du scellé** : quand une découpe doit être refermée, elle
   l'est par un contenu qui remplit exactement la section du frustum, sans
   interstice. Depuis la v6.1 ce scellé n'est plus le fond peint, parti au
   loin : c'est le **contenu de la photo** (`"seal": "content"`) : c'est le cas de la porte, dont les
   panneaux pavent toute la section à 6 m sauf l'ouverture. Cette photo n'a
   alors **aucun fond peint**, et c'est indispensable : un fond est un mur,
   donc un fond derrière l'ouverture boucherait la porte (il le faisait, à
   20 cm derrière, et la porte était infranchissable). Sa découpe court
   1,4 m au delà du mur pour que le sol continue de l'autre côté.
3. **Instanciation** : un `PhotoContent` solide est construit depuis la
   définition et placé à `T`. Les props box non `loose` deviennent des
   `ErasableBlock` (le contenu posé est lui-même remplaçable) ; les props
   box `loose` (petits objets, caisse) deviennent des `RigidBody3D` qui
   tombent (masse = volume x 2, bornée à [1, 10]) ; les props `battery`
   deviennent de **vraies piles ramassables** portées par une coquille
   `RigidBody3D` (masse 1,5) : posées dans le vide ou à l'envers, elles
   chutent ; les cylindres restent des `StaticBody3D` ; le backdrop devient
   un `ErasableBlock` mince (0,2 m) peint en dégradé.
4. La photo tenue est consommée.

### 3.4 Vignette et image de la photo

Deux niveaux de fidélité, même définition en entrée que la matérialisation :

- **Vignette calculée** (`PhotoDefs.thumbnail`) : projection sténopé des props
  sur le plan photo, dessinée dans une `Image` (dégradé de fond, rectangles
  triés du fond vers l'avant, cadre polaroïd). Pure et déterministe : c'est
  elle que testent les suites, et le repli en headless.
- **Image rendue** (`PhotoSnaps`, v3) : le contenu (variante « display »,
  solide mais inerte) est rendu hors écran par une caméra carrée au fov du
  frustum de pose, sur le même ciel que le jeu. L'image de la photo EST donc
  le rendu de ce qui sera matérialisé : levée au clic droit, elle couvre la
  zone exacte de l'écran que le contenu occupera à la pose.

Depuis la v4, **il n'y a plus de fantôme 3D** : la seule prévisualisation est
cette image 2D, levée au clic droit et tournée à l'écran par la molette
(rotation du TextureRect, pivot au centre). Le résultat 3D ne se découvre
qu'à la pose. Le panneau de la photo tenue affiche une mini vignette
(110 x 110) au-dessus du titre.

### 3.5 Tenir, poser, reposer

- Le joueur ne tient qu'**une photo à la fois**. Interagir avec une autre photo
  les mains pleines affiche « Mains pleines ».
- Clic droit : repose la photo sous forme d'objet dans le monde, devant le
  joueur (rien n'est perdu).
- Les contenus posés appartiennent au niveau : changer de niveau les détruit.

### 3.6 Le langage du sol (v5.5)

Une règle que le joueur lit **à la couleur**, sans un mot d'explication :

- **le sol gris reste.** Une photo posée par dessus lui est **ajoutée** :
  la dalle ne bouge pas, le pont se pose dessus. Poser un pont ajoute un
  pont, ça ne creuse pas une tranchée.
- **le sol pâle part**, comme le lavande dont il est la teinte claire : le
  cadre le découpe. C'est le seul sol qu'une photo peut emporter, et c'est
  ce qui rend le perçage de sol lisible au lieu d'être une surprise.

Deux groupes de scène séparent les deux questions, qui n'ont rien à voir :

- `photographable` : **tout** bloc du monde, gris compris. Une photo doit
  montrer ce qui était dans le cadre, sinon l'image ment.
- `carvable` : la moitié éphémère seulement. C'est elle que la pose découpe.

Cette règle remplace l'approche v5.3, où toute photo portait une dalle de sol
pour réparer la tranchée qu'elle creusait : réparer un dégât qu'on peut
simplement ne pas causer était le mauvais bout du problème. Les photos ne
rapiècent donc plus rien (`test_no_photo_patches_the_ground`), et la porte du
niveau 4 s'ouvre sur le sol d'origine, intact.

Côté appareil, rien de particulier : la capture parcourt `photographable`,
donc un cliché montre le sol gris et, posé ailleurs, l'ajoute au monde. Une
copie posée exactement sur son original superpose deux faces coplanaires,
approximation visuelle assumée.

Niveaux : le sol pâle reste l'exception, réservé aux énigmes de perçage (le
niveau 11 « Sous le pont » en fait sa passerelle), ce que vérifie
`test_ground_language_is_taught`.

### 3.7 La matière qui dit non (v6)

Le langage du sol pose une idée que la v6 pousse jusqu'au bout : le gris est
ce qui ne bouge pas. Un cran plus loin sur la même échelle, il y a **l'acier
et le plomb**, deux refus francs, chacun visible avant d'être compris.

**L'acier.** Une cage `"sealed": true` n'est ouverte par **aucune** pose.
Elle n'entre pas dans le groupe `breakable`, seulement dans `cage`. Comme
l'objectif, lui, traverse les barreaux, la seule sortie d'une cage d'acier
est de **photographier ce qu'elle enferme et de matérialiser la copie
ailleurs**. Une pile enfermée dans l'acier n'est donc jamais un objet à
ramasser : c'est un **modèle**. Deux invariants tiennent la promesse :
`test_sealed_cages_need_a_lens` refuse un niveau qui enferme une pile sans
donner d'appareil ni de pellicule, et refuse aussi qu'une pile plombée soit
mise sous acier, combinaison qui la perdrait pour de bon.

Conséquence sur la capture : **une cage n'est plus photographiée du tout.**
Des barreaux sont un treillis, pas un volume. Copiée en bloc plein, une cage
se refermerait autour de sa propre copie de pile et rendrait insoluble le
seul puzzle qui la justifie. C'est aussi une approximation en moins dans
`PhotoCapture`, pas une de plus.

**Le plomb.** Une pile listée dans `sealed_batteries` vaut exactement une
pile pour un téléporteur, mais **aucune pellicule ne l'imprime** : elle
n'entre pas dans `copyable_battery`, le seul groupe que la capture lit. Elle
le dit sans un mot, dans le langage déjà en place : gris de plomb au lieu
d'ambre, et **inerte** là où les autres flottent et tournent.

Le plomb reste plomb à travers les mains. `Game` suit `carried_sealed`, et
`drop_battery()` repose **toujours le plomb en premier** ; sans cela il
suffirait de ramasser une pile plombée, de la reposer et de la photographier
pour la blanchir en pile ordinaire, et la mécanique ne serait qu'une
formalité. Même ordre à l'insertion, ce qui est aussi le service à rendre au
joueur : la pile copiable lui reste en main le plus longtemps possible.

**La pellicule n'imprime pas la pellicule.** Une pile qui sort d'une photo
est **plombée** : elle vaut une pile au téléporteur, et ne sera jamais un
sujet. Sans cette règle, l'économie du jeu entier s'effondrait, et pas
seulement celle des niveaux neufs : une copie était elle-même un modèle, donc
en posant une copie à côté de son original et en cadrant les deux, un joueur
repartait avec `C x 2^F` piles pour `C` piles et `F` pellicules. Aucune
exigence de téléporteur ne voulait plus rien dire. La règle se lit à la
couleur dès le niveau 2, vingt niveaux avant qu'un niveau soit bâti dessus.

Corollaire de level design, à connaître avant d'écrire un niveau :
**l'objectif n'a ni test d'occlusion ni portée autre que 12 m.** Une pile
copiable à moins de 12 m d'un endroit où le joueur peut se tenir se
photographie de là, perchée ou derrière des barreaux, et la copie tombe à ses
pieds. Une montée n'est donc une montée que si ce qui l'attend en haut est
**plombé**. C'est exactement à ça que sert le plomb, et l'audit de level
design le vérifie niveau par niveau.

**Le poids.** Rien de neuf dans le moteur, une conséquence enfin exploitée :
une caisse posée à l'endroit apparaît un mètre **sous** l'œil et se pose au
sol (sommet 1.30) ; la même photo **retournée à 180 degrés** apparaît un
mètre **au dessus** de l'œil, 2.6 m devant, et **tombe**. Viser la première
caisse permet donc d'empiler : sommet 2.60, et 4.10 avec un saut. Posée à
l'endroit, elle ne donnera jamais que 1.30. C'est le seul mouvement du jeu
qu'on ne peut pas improviser, et la sonde le vérifie en moteur (deux caisses,
sommet mesuré entre 2.3 et 2.9, la seconde bien **sur** la première).

Détail qui rend l'empilement possible : les objets libres sont des
`RigidBody3D`, pas des `ErasableBlock`. Aucune pose ne les découpe, donc une
pile de caisses survit à la photo suivante.

**Correctif de fond livré avec la v6** : le mur de fond peint était devenu
permanent alors que son propre commentaire le disait découpable. C'est la
chose la plus éphémère du jeu (du ciel peint), elle apparaît là où le joueur
vise, et permanente elle pouvait murer une route sans recours. Elle est de
nouveau `carvable` : la photo suivante la perce.

## 4. Piles et téléporteur

- La pile est un objet ramassable (E) : compteur « portées ».
- Le téléporteur affiche « insérées / requises ». E insère toutes les piles
  portées (dans la limite du requis). Quand requis atteint, l'anneau s'allume ;
  E déclenche alors un fondu et le passage au niveau suivant.
- Une pile dupliquée par photo est une pile normale : aucune distinction.
- Invariant vérifié par test : dans chaque niveau,
  piles du monde + piles contenues dans les photos du niveau >= piles requises.

## 5. Les 25 niveaux

Les cinq premiers enseignent un geste chacun, et rien d'autre. Le détail des
niveaux 6 à 25 est dans `docs/LEVELS_V2.md` (sections 4 et 4 bis) ; la donnée
elle-même fait foi (`src/world/level_defs.gd`).

| # | Nom | Ce qu'il enseigne | Piles requises | Photos |
|---|-----|-------------------|----------------|--------|
| 1 | Premiers pas | Ramasser et poser : franchir un vide avec la photo « Passerelle » | 1 | passerelle |
| 2 | Copie conforme | Dupliquer : la photo « Pile » matérialise une vraie pile (et son backdrop devient un mur) | 2 | pile |
| 3 | Prendre de la hauteur | La verticalité : la photo « Escalier » permet d'atteindre une pile en hauteur | 2 | escalier |
| 4 | Effacement | Poser découpe : un mur effaçable bloque le couloir, la photo « Porte ouverte » y perce un passage et pose son propre mur | 2 | porte |
| 5 | Belvédère | Combinaison libre des trois usages : franchir, monter, dupliquer | 3 | passerelle, escalier, pile |
| 6 à 15 | v2 | Cages, rotation, photo dans la photo, sol pâle, double volée | 2 à 5 | catalogue complet |
| 16 à 20 | v3 et v4 | L'appareil photo : la photo vide, la copie, la chute, les barreaux | 2 à 3 | pellicule |
| 21 à 25 | v6 | Les trois refus : acier, plomb, gravité | 2 à 5 | pellicule et caisses |

Chaque niveau est une **donnée déclarative** (`LevelDefs`) : plateformes,
props décoratifs, objets effaçables, photos placées, piles, téléporteur
(position + requis), point d'apparition, altitude de rattrapage (`kill_y`).

## 6. Contrôles

| Entrée | Action |
|--------|--------|
| ZQSD / WASD (touches physiques) | Se déplacer |
| Souris | Regarder |
| Espace | Sauter |
| Maj | Courir |
| E | Interagir (photo, pile, appareil, téléporteur), portée 1,7 m ; sans cible avec une pile portée : reposer une pile devant soi (v4) |
| Clic gauche | Poser la photo tenue ; mains vides, **appareil à l'œil** : déclencher (la pellicule capture TOUT, même le vide ; le film est toujours consommé, v4) |
| Clic droit | Photo en main : la lever / la baisser (l'image 2D s'affiche sur la zone exacte que le frustum couvre à l'écran, tournée selon la molette ; plus de prévisualisation 3D, le résultat se découvre à la pose). Mains vides avec de la pellicule : lever / baisser l'appareil, qui encadre à l'écran ce que le cliché retiendrait (v4.2) |
| Molette | Pivoter la photo tenue (90 degrés) ; levée, l'image tourne à l'écran (v4) |
| F | Reposer la photo tenue (v3, remplace l'ancien clic droit) |
| R (maintenu) | Rembobiner le temps (v5) : tant que la touche est tenue, le niveau remonte son historique à 2,5 s par seconde ; relâcher fait de cet instant le nouveau présent. Une chute dans le vide, elle, reconstruit le niveau entier (v4) |
| F11 | Plein écran |
| Échap | Menu / reprendre |
| Entrée | Commencer (menu) |

## 7. Architecture et contrats de module

Arborescence :

```
games/viewpoint/
  project.godot            autoload Game, couches physiques, fenêtre
  scenes/main.tscn         squelette minimal, tout le reste est construit en code
  src/main.gd              câblage, chargement des niveaux, fondu, sonde --smoke
  src/core/game_state.gd   autoload « Game » : progression, piles, InputMap
  src/core/layers.gd       constantes de couches physiques
  src/render/palette.gd    couleurs nommées du jeu
  src/render/materials.gd  fabrique de matériaux (cache, variantes fantômes)
  src/photo/photo_math.gd  frustum, projection sténopé, taille du backdrop
  src/photo/photo_defs.gd  définitions des photos + vignettes calculées
  src/photo/photo_content.gd  construit props/backdrop (fantôme ou solide)
  src/photo/photo_item.gd  la photo posable trouvée dans le monde
  src/photo/photo_placer.gd  tenir, prévisualiser, effacer, matérialiser
  src/pickups/battery.gd   la pile ramassable
  src/world/teleporter.gd  socle, anneau, insertion, départ
  src/world/level_defs.gd  les 25 niveaux en données
  src/world/level_builder.gd  construit un niveau depuis sa définition
  src/player/player.gd     contrôleur FPS + visée d'interaction
  src/ui/hud.gd            réticule, compteur de piles, invites, bannière, fondu
  src/ui/menu.gd           titre, pause, victoire
  tests/                   harnais (voir section 8)
```

Contrats (signatures gelées, toute évolution passe par ce fichier) :

- `Game` (autoload) : `reset()`, `begin_level(index: int, required: int)`,
  `collect_battery()`, `insert_batteries() -> int`, `can_teleport() -> bool`,
  `has_next_level() -> bool`, `advance_level()`,
  `is_level_unlocked(index) -> bool`, `load_progress(path)` /
  `save_progress(path)` (progression persistée dans `user://progress.cfg`,
  `furthest_level: int` ; `reset()` n'y touche pas). Signaux :
  `batteries_changed(carried, inserted, required)`, `level_started(index)`.
- `PhotoDefs` : `all_ids() -> PackedStringArray`, `get_def(id) -> Dictionary`,
  `battery_count(id) -> int`, `battery_count_recursive(id) -> int` (suit les
  props `photo` imbriques, garde anti-cycle), `thumbnail(id) -> ImageTexture`.
- `PhotoMath` : `point_in_frustum(local, fov_deg, aspect, near, far) -> bool`,
  `half_extent_at(depth, fov_deg) -> float`,
  `project_point(local, fov_deg, aspect) -> Vector2`,
  `backdrop_size(depth, fov_deg, aspect) -> Vector2`.
- `PhotoContent` : `setup(def: Dictionary, ghost: bool)`.
- `PhotoPlacer` : `setup(level_root)`, `hold(id) -> bool`, `place() -> bool`,
  `drop() -> bool`, `rotate_held(direction: int)` (roulis par pas de 90
  degres, remis a zero a chaque prise/pose), `held_id: String`,
  `roll_steps: int`.
- `PhotoItem` : `setup(def_id)`, `interact(player)`, `prompt_text(player)`.
- `Battery` : `interact(player)`, `prompt_text(player)`.
- `Teleporter` : `setup(required)`, `interact(player)`, `prompt_text(player)`.
  Signal : `depart_requested`.
- `LevelDefs` : `count() -> int`, `get_def(index) -> Dictionary`.
- `LevelBuilder` : `build(root: Node3D, def: Dictionary)`.
- `ErasableBlock` : `create(size, color, emissive := 0.0,
  extra_groups := PackedStringArray()) -> ErasableBlock` (v4 : groupe
  `carvable` + extra_groups, les fragments héritent couleur/émission/groupes),
  `carve_with_frustum(anchor, fov_deg, aspect, depth) -> bool`,
  `decompose(size, hole_min, hole_max) -> Array` (statique et pure).
- `PhotoCapture` (v3, v4, v5.1) : `capture(anchor, tree) -> Dictionary` (ne
  retourne JAMAIS vide : fond ciel à 12 m, props triés par profondeur,
  plafond 32), `props_from(candidates, anchor) -> Array` et
  `clip_to_frustum(size, to_camera, far) -> Dictionary` (pures, testées).
- `PhotoSnaps` (v3, nœud sous Main) : `get_texture(id) -> Texture2D`
  (statique, repli sur `PhotoDefs.thumbnail`), `request(id)`.
- `CameraItem` : `setup(films)`, `interact(player)`, `prompt_text(player)`.
- `Game` gagne en v3 : `camera_films`, `add_films(n)`, `use_film() -> bool`,
  signal `films_changed(films)`.
- `PhotoPlacer` gagne en v3 : `raise_toggle()`, `raised: bool`.
- `Player` gagne en v3 : `capture_photo() -> bool` (v4 : consomme toujours un
  film ; le signal `capture_failed` est supprimé ; v4.2 : refuse hors viseur),
  `toggle_viewfinder() -> bool` et `viewfinder: bool` (v4.2). `INTERACT_RANGE` = 1,7 m
  (v4) ; E sans cible avec une pile portée la repose devant le joueur ;
  signal `fell_out` émis une seule fois par chute, la main coupée jusqu'à la
  reconstruction du niveau.
- `Game` gagne en v4 : `drop_battery() -> bool` (borné à zéro, décrémente,
  émet `batteries_changed`).
- `Hud` (v4) : `set_photo_view(texture, roll_steps := 0)` (image levée
  tournée), `set_held(title, texture := null, raised := false)` (petite carte
  inclinée en bas à droite, masquée pendant que la photo est levée).
- `Rewind` (v5, nœud sous Main) : voir section 12 pour le détail. En bref
  `setup`, `begin_level`, `start_rewind` / `step_rewind` / `stop_rewind`,
  `is_rewinding`, `available_seconds`, `sample_count`, `event_count`, et les
  statiques `retire`, `notice_spawn`, `track_body`. **Toute destruction en
  cours de niveau passe par `Rewind.retire`, jamais par `queue_free`.**
- `PhotoCard` (v4) : `Control` qui dessine la carte tenue en perspective
  (`tilt_z`, `tilt_x`, `card_size`, `view_distance`) ; une `Control` ne
  tournant que sur Z, le quad texturé est projeté et subdivisé à la main.
- `LevelDefs` : clé optionnelle `camera: {pos, films}` par niveau.
- Groupes de scène (v4) : `carvable` (tout bloc-boîte, découpable par pose),
  `breakable` (cages, cassées entières par le frustum), `erasable` (marqueur
  lavande, lisibilité et tests uniquement), `photo_item`, `battery`,
  `teleporter`, `placed_content`, `platform`.

## 8. Exigences vérifiables et plan de test

Harnais identique aux autres jeux Godot du dépôt :

- **Suites unitaires** (`godot --headless --path . --script res://tests/run_tests.gd`),
  sans autoload, sur les modules purs :
  - `test_photo_math` : appartenance au frustum (bords, near/far, aspect),
    symétrie de la projection, tailles de backdrop.
  - `test_photo_defs` : ids uniques, props aux genres connus, couleurs
    existantes dans la palette, positions devant la caméra (z < 0), comptage
    des piles par photo, vignette 256 x 256 non uniforme.
  - `test_level_defs` : exactement 25 niveaux, spawn au dessus d'une
    plateforme, téléporteur présent, photos référencées existantes,
    **piles accessibles >= piles requises** pour chaque niveau, kill_y sous
    toutes les plateformes.
  - `test_palette` et `test_materials` : couleurs définies, cache stable,
    variante fantôme transparente.
  - `test_game_state` : cycle complet ramasser/insérer/téléporter en logique
    pure, bornes (insertion sans pile, téléportation sans charge).
- **Sonde d'intégration** (`godot --headless --path . -- --smoke`) dans le vrai
  chemin de démarrage : niveau 1 construit, joueur au sol, ramassage d'une
  photo, pose, contenu matérialisé et effaçables effacés, pile ramassée,
  insertion, téléportation, puis construction des 25 niveaux sans erreur.

- **Audit de level design** (`godot --headless --path . --script res://tools/design_audit.gd`),
  ajouté en v6. Les suites répondent « cette donnée est-elle bien formée » ;
  l'audit répond à l'autre question, celle qui décide si un niveau vaut
  quelque chose : « un joueur au spawn, avec les outils que ce niveau lui
  donne, atteint-il tout ce qu'on lui demande, sans jamais s'enfermer ».

  Il modélise le monde en rectangles où l'on tient debout, puis les parcourt
  avec le **budget cinématique** de `LEVELS_V2.md` section 2 (saut +1.50 et
  4.6 m de portée, une caisse +2.80, deux caisses +4.10, console +2.67,
  escalier +6.12, passerelle 13.6 m de portée en comptant le saut depuis son
  extrémité, rampe de fond peint jusqu'à 10.1 m mais uniquement quand le
  niveau donne aussi un escalier pour l'aborder). Chaque nombre penche du
  côté du **joueur** : l'audit ne signale que ce qui reste hors d'atteinte
  avec la lecture la plus généreuse des outils, donc une ligne de rapport est
  un vrai défaut, jamais un doute.

  **La pose déclarée (v6).** Un repère disait seulement où se tenir, ce qui
  n'a jamais suffi : ce qu'une pose fait dépend d'où le joueur **regarde**, et
  aucun test ne pouvait le voir. Un repère peut donc porter trois champs de
  plus, `"photo"` (l'id qu'il sert), `"aim"` (le point visé) et `"roll"` (les
  crans de molette). La pose devient reproductible, et deux choses qui
  coûtaient une partie à découvrir se vérifient : que la cible est **devant**
  le mur de fond peint et non derrière, et que le contenu ne se matérialise
  pas **à l'intérieur** d'un bloc permanent. Cinq bloquants sur six trouvés
  par la revue humaine étaient de cette famille.

  Codes : `VIDE` et `FLOTTE` (objet sans appui ou hors de portée du sien),
  `EMMURE` et `ENTERRE` (la pose déclarée scelle sa cible ou s'enterre),
  `HORS_ATTEINTE` (l'élévation du niveau n'y suffit pas), `ENCASTRE`,
  `COLLE` (deux ramassables qui se disputent le même rayon), `SPAWN`,
  `REPERE` (marque de pose enterrée ou inaccessible), `PIEGE` (cul de sac
  d'où l'on ne remonte pas), `REDITE`. Sortie 1 dès qu'il trouve quelque
  chose, donc utilisable en garde-fou.

Critères de sortie v1 : 0 échec unitaires, sonde verte, jeu jouable de bout en
bout à la souris et au clavier.

## 9. Évolutions réservées, état

- **Appareil photo : LIVRÉ (v3, étendu v4, restreint v6).** `PhotoCapture.capture`
  transforme TOUT le monde cadré (blocs `photographable`, piles
  `copyable_battery`) en définition dynamique enregistrée par
  `PhotoDefs.register_dynamic` (« cliche_N », purgée au changement de
  niveau). Props triés par profondeur croissante, plafonnés à 32 ; une boîte
  d'au plus 1,6 m sur les trois axes est marquée `loose` (elle tombera à la
  pose). La capture retourne TOUJOURS un def valide : props éventuellement
  vides et fond ciel à 12 m ; la photo vide est un outil de perçage, pas un
  échec, et le film est toujours consommé (le signal `capture_failed` a
  disparu). La capture est une **copie** (les originaux restent), le test
  est géométrique (les barreaux ne bloquent pas : c'est le puzzle du niveau
  19). L'appareil est un objet ramassable (`CameraItem`) qui charge la
  pellicule du niveau (`Game.camera_films`).

  **Capture volumétrique (v5.1).** Les blocs sont copiés **par volume,
  découpés au cadre**, exactement comme une pose les découpe : la photo garde
  la part du bloc qui tombe dans le cadre, pas le bloc entier. C'est ce qui
  fait tenir le sol sous les pieds. Un bloc est souvent bien plus grand que
  le cadre (une plateforme de 12 m dont le centre est derrière le joueur) :
  un test au centre ne l'aurait jamais copiée, alors qu'une pose, elle,
  découpe le morceau cadré. Le joueur se creusait un trou dans son propre
  plancher et tombait au travers de sa photo. En capturant le volume découpé,
  une photo remet exactement ce que sa propre pose enlève.

  Le découpage est **analytique, jamais échantillonné** (v5.2) : la fidélité
  prime, une photo doit montrer les objets à leur vraie place et à leur vraie
  taille. Deux cas :

  - **l'objet tient entièrement dans le cadre** (ses huit coins sont dans le
    frustum, qui est convexe, donc tout l'objet l'est) : il est copié **tel
    quel**, sa taille et son centre exacts, rien n'est estimé ;
  - **l'objet déborde du cadre** : la copie est l'intersection exacte de ses
    bornes en espace caméra avec le cadre (pas de grille, donc ni erreur de
    pas ni marge ajoutée). C'est le cas du sol sous les pieds.

  Deux approximations restent assumées, et seulement dans le second cas : le
  morceau revient réaligné sur les axes caméra, et les cages sont copiées
  entières sur le test de centre qui décide aussi de leur destruction. La clé
  `loose` suit l'objet d'origine, pas la tranche : un coin de sol reste du
  sol. Vérifié de bout en bout par la sonde : photographier un objet puis
  poser le cliché depuis le point de vue de la prise superpose la copie à
  l'original à moins d'un centimètre.
- **Viseur : LIVRÉ (v4.2).** L'appareil se porte à l'œil au clic droit
  (mains vides, pellicule restante) : le HUD encadre le carré que le cliché
  retiendrait, assombrit le hors champ, et **seul ce mode arme le
  déclencheur**. `Player.viewfinder`, `Player.toggle_viewfinder() -> bool`,
  `Hud.set_viewfinder(active)`. Le viseur se referme au déclenchement, à la
  chute et quand la pellicule est épuisée.
- **Rotation de la photo (molette) : LIVRÉ (v2).**
- **Photo levée : LIVRÉ (v3).** Clic droit lève la photo : l'image (rendue
  par `PhotoSnaps`, section 3.4) couvre à l'écran exactement la zone du
  frustum de pose ; poser pendant la levée révèle le contenu 3D identique.
- **Rembobinage : LIVRÉ (v5).** Voir section 12.
- Restent réservés : photos en noir et blanc qui décolorent le monde, musique
  et nappes sonores.

## 10. v2 : niveaux 6 a 15 (livree)

Extension concue et specifiee dans `docs/LEVELS_V2.md` : rotation de la photo
a la molette (roulis de l'ancre par pas de 90 degres), cages a barreaux
(effacables lavande ou permanentes sombres, avec ou sans toit), photos
imbriquees (prop `photo` qui materialise un PhotoItem ramassable), poses en
tangage assumees (passerelle piquee, backdrop-plancher), et touche R pour
recommencer le niveau courant (filet anti-blocage). Quatre photos ajoutees au
catalogue : console, corniche, caisse, coffret. Le budget cinematique complet
(hauteurs et portees qui fondent chaque puzzle) est la section 2 de
LEVELS_V2.md ; c'est lui qui fait foi pour tout nouveau niveau.

## 11. Direction artistique

Pastel et propre, lisible sans texture : plateformes crème aux flancs sable,
accents corail et sarcelle, piles ambre émissives, téléporteur indigo, ciel
dégradé bleu clair vers blanc avec brume douce. Les photos sont des polaroïds
au cadre blanc. Objets effaçables en lavande grisée, signalés par un léger
scintillement d'émission.

## 12. v5 : le rembobinage (livré)

Maintenir R remonte le temps du niveau. La difficulté n'est pas l'interface,
c'est de savoir remettre le monde dans un état passé alors que poser une
photo **détruit** (découpe des blocs, casse des cages) et **crée** (fragments,
contenu, copies). Deux pistes, parce qu'un niveau change de deux façons très
différentes :

- **Le mouvement**, continu : le joueur et les corps rigides libres (caisses,
  piles posées). Échantillonné à 20 Hz sur l'horloge **physique** (delta fixe,
  donc l'historique veut dire la même chose quel que soit le nombre d'images
  par seconde), rejoué à l'envers avec interpolation des positions. Les
  compteurs (piles, pellicule) et la photo tenue voyagent dans le même
  échantillon.
- **La structure**, discrète et rare : une photo posée, un mur découpé, une
  cage cassée, une pile ramassée. Enregistrée en événements horodatés.

La clé du côté structurel : **pendant une partie, plus rien n'est réellement
détruit**. `Rewind.retire(node)` sort le nœud de l'arbre vers un **cimetière
orphelin** (un `Node` volontairement non ajouté à la scène). Le nœud quitte
ainsi tous les groupes et la physique, exactement comme une libération, mais
reste intact : défaire, c'est le remettre où il était. Les nœuds ne meurent
pour de bon que lorsque leur événement sort de la fenêtre d'historique
(6000 échantillons, environ cinq minutes), ce qui est aussi le moment où la
mémoire est rendue.

Contrats : `Rewind.setup(player, level_root)`, `begin_level()` (l'historique
appartient au niveau), `start_rewind()` / `step_rewind(delta)` /
`stop_rewind()` (relâcher tronque le futur rembobiné : cet instant devient le
présent), `is_rewinding()`, `available_seconds()`, `sample_count()`,
`event_count()`, et les statiques `retire(node)`, `notice_spawn(node)`,
`track_body(body)`. Pures et testées unitairement : `locate(samples, t)` et
`sample_at(samples, t)` (l'état continu s'interpole, l'état discret non : une
pile est ramassée à un instant, jamais à moitié). `Game.restore_counters(...)`
et `PhotoPlacer.restore_held(...)` remettent respectivement les compteurs et
la main. Côté joueur, le contrôle est coupé pendant le rembobinage et le HUD
affiche `set_rewinding(actif, secondes)`.

Note de conception : R ne recommence plus le niveau instantanément. Ce n'est
pas une perte, l'historique remonte jusqu'au début du niveau ; et une chute
dans le vide, elle, reconstruit toujours tout (section 2).
