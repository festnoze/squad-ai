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

- **5 niveaux courts** (2 à 4 minutes chacun), des îlots flottants dans un ciel
  pastel.
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
5. Après le niveau 5, écran de victoire.

Une chute dans le vide replace le joueur au point d'apparition du niveau, sans
perte d'inventaire.

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

### 3.3 Matérialisation

À la pose :

1. L'ancre `T` = transformée globale caméra.
2. **Découpage** : les blocs effaçables (`ErasableBlock` : murs, caisses) ne
   perdent que la partie de leur volume prise dans le **frustum de la photo**
   (fov 50 degrés, carré, profondeur = distance du backdrop, ou 12 m sans
   backdrop). Le trou est l'AABB locale de l'intersection échantillonnée, et
   le reste survit en fragments (boîte moins boîte, 6 morceaux au plus),
   eux-mêmes effaçables. Un mur plus large que le cadre n'est donc percé que
   là où la photo est posée. Les objets sans découpe (cages) disparaissent
   entiers quand leur centre tombe dans le frustum. **Règle du scellé** : une
   photo dont le contenu comporte un mur pleine trame (porte) ou un backdrop
   (pile) ne découpe que jusqu'au plan de ce scellé, qui remplit exactement
   la section du frustum à cette profondeur ; tout trou creusé est donc
   refermé par le contenu, sans interstice.
3. **Instanciation** : un `PhotoContent` solide est construit depuis la
   définition et placé à `T`. Les props deviennent des `StaticBody3D`
   (couche physique `world`), les props `battery` deviennent de **vraies
   piles ramassables** (c'est le mécanisme de duplication), le backdrop
   devient un quad texturé en dégradé avec une collision fine (un mur).
4. La photo tenue est consommée.

### 3.4 Vignette

La vignette affichée sur l'objet photo dans le monde est **calculée** depuis la
définition : projection sténopé des props sur le plan photo, dessinée dans une
`Image` (dégradé de fond, rectangles colorés triés du fond vers l'avant, cadre
polaroïd). Même définition en entrée que la matérialisation : la vignette est
donc toujours cohérente avec ce qui apparaîtra.

### 3.5 Tenir, poser, reposer

- Le joueur ne tient qu'**une photo à la fois**. Interagir avec une autre photo
  les mains pleines affiche « Mains pleines ».
- Clic droit : repose la photo sous forme d'objet dans le monde, devant le
  joueur (rien n'est perdu).
- Les contenus posés appartiennent au niveau : changer de niveau les détruit.

## 4. Piles et téléporteur

- La pile est un objet ramassable (E) : compteur « portées ».
- Le téléporteur affiche « insérées / requises ». E insère toutes les piles
  portées (dans la limite du requis). Quand requis atteint, l'anneau s'allume ;
  E déclenche alors un fondu et le passage au niveau suivant.
- Une pile dupliquée par photo est une pile normale : aucune distinction.
- Invariant vérifié par test : dans chaque niveau,
  piles du monde + piles contenues dans les photos du niveau >= piles requises.

## 5. Les 5 niveaux

| # | Nom | Ce qu'il enseigne | Piles requises | Photos |
|---|-----|-------------------|----------------|--------|
| 1 | Premiers pas | Ramasser et poser : franchir un vide avec la photo « Passerelle » | 1 | passerelle |
| 2 | Copie conforme | Dupliquer : la photo « Pile » matérialise une vraie pile (et son backdrop devient un mur) | 2 | pile |
| 3 | Prendre de la hauteur | La verticalité : la photo « Escalier » permet d'atteindre une pile en hauteur | 2 | escalier |
| 4 | Effacement | Poser découpe : un mur effaçable bloque le couloir, la photo « Porte ouverte » y perce un passage et pose son propre mur | 2 | porte |
| 5 | Belvédère | Combinaison libre des trois usages : franchir, monter, dupliquer | 3 | passerelle, escalier, pile |

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
| E | Interagir (photo, pile, téléporteur) |
| Clic gauche | Poser la photo tenue |
| Molette | Pivoter la photo tenue (90 degrés, v2) |
| Clic droit | Reposer la photo tenue |
| R | Recommencer le niveau (v2) |
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
  src/world/level_defs.gd  les 5 niveaux en données
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
- `ErasableBlock` : `create(size, color) -> ErasableBlock`,
  `carve_with_frustum(anchor, fov_deg, aspect, depth) -> bool`,
  `decompose(size, hole_min, hole_max) -> Array` (statique et pure).
- Groupes de scène : `erasable` (supprimable par pose), `photo_item`,
  `battery`, `teleporter`, `placed_content`, `platform`.

## 8. Exigences vérifiables et plan de test

Harnais identique aux autres jeux Godot du dépôt :

- **Suites unitaires** (`godot --headless --path . --script res://tests/run_tests.gd`),
  sans autoload, sur les modules purs :
  - `test_photo_math` : appartenance au frustum (bords, near/far, aspect),
    symétrie de la projection, tailles de backdrop.
  - `test_photo_defs` : ids uniques, props aux genres connus, couleurs
    existantes dans la palette, positions devant la caméra (z < 0), comptage
    des piles par photo, vignette 256 x 256 non uniforme.
  - `test_level_defs` : exactement 5 niveaux, spawn au dessus d'une
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
  insertion, téléportation, puis construction des 5 niveaux sans erreur.

Critères de sortie v1 : 0 échec unitaires, sonde verte, jeu jouable de bout en
bout à la souris et au clavier.

## 9. Évolutions réservées (hors périmètre v1)

- **Appareil photo** : prendre une photo capture les nœuds dans le frustum
  courant et fabrique une définition dynamique. L'architecture est prête :
  `PhotoDefs.get_def` retourne un dictionnaire ordinaire, `PhotoContent` et la
  vignette consomment ce dictionnaire sans savoir s'il est statique ou
  capturé. Il manque uniquement le module de capture (scène -> props).
- Rotation de la photo tenue avant pose (molette).
- Rembobinage (annuler la dernière pose).
- Photocopieur d'objets, photos en noir et blanc qui décolorent le monde.
- Musique et nappes sonores (v1 : silencieuse, seules les invites UI existent).

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
