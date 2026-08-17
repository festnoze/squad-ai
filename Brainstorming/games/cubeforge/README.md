# CUBEFORGE

Bac à sable voxel façon Minecraft, écrit en GDScript pour **Godot 4.7**.
Monde procédural infini, casse et pose de blocs, dix biomes, grottes, minerais,
maisons habitées, cycle jour/nuit, inventaire et sauvegarde.

**Zéro asset binaire.** Les 53 textures et les 28 effets sonores sont générés
par code au démarrage. Le seul fichier non-code du dépôt est `icon.svg`.

## Lancer le jeu

```bash
# depuis games/cubeforge
godot --path .
```

Ou ouvrir le dossier dans l'éditeur Godot et appuyer sur F5.

Le premier démarrage tire une graine de monde au hasard et la conserve dans
`user://settings.cfg`, donc le même monde revient au lancement suivant. Les
chunks que vous modifiez sont écrits dans `user://saves/monde/`.

## Commandes

| Touche | Action |
|---|---|
| `ZQSD` / `WASD` / flèches | se déplacer |
| Souris | regarder |
| `Espace` | sauter, remonter ou bondir hors de l'eau, monter en vol |
| `Maj` | courir |
| `Ctrl` | s'accroupir, descendre en vol |
| `F` | basculer le vol (mode créatif) |
| Clic gauche | casser un bloc (maintenir) |
| Clic droit | poser un bloc |
| Clic molette | copier le bloc visé |
| Molette / `1`-`9` | changer de case |
| `E` | inventaire |
| `T` | avancer l'heure |
| `F3` | infos de débogage |
| `F2` | capture d'écran (dans `user://screenshots/`) |
| `Échap` | pause et réglages |

Le menu **Réglages** contient aussi une option « Afficher les FPS » qui ajoute
un compteur compact dans le coin supérieur gauche, ainsi qu'une option « God
mode » disponible en mode créatif. Le raccourci `F` reste utilisable et maintenir
`Maj` en vol multiplie la vitesse par cinq.

Les touches sont enregistrées par code physique, donc un clavier AZERTY se
comporte comme un QWERTY : les touches de déplacement sont bien `ZQSD`.

## Ce que le monde contient

Dix biomes choisis par deux bruits indépendants de température et d'humidité :
océan, plage, plaines, forêt, taïga, désert, savane, montagnes, toundra,
marais. Le relief descend vers y 30 sous les océans et monte jusqu'à y 88 en
montagne, pour un niveau de la mer à y 48.

Sous la surface, des grottes creusées par bruit 3D à deux échelles (galeries
fines et cavernes larges), des amas de charbon, fer, or et diamant répartis par
profondeur, et des poches de granite, marbre et argile. La roche-mère à y 0 est
incassable.

En surface, des chênes et des bouleaux, des sapins en taïga, des cactus et des
buissons morts au désert, de l'herbe haute, des fougères, des coquelicots et
des pissenlits. Les arbres débordent correctement d'un chunk à l'autre : un
tronc posé près d'un bord dépose bien ses feuilles chez le voisin.

Les zones sèches et peu pentues accueillent des villages procéduraux complets :
maison en bois, atelier en pierre et briques, chemins et enclos fermé. Deux
villageois et un chien vivent autour de chaque maison tandis que cochons et
vaches restent dans l'enclos. Tous alternent marche et pause, suivent le relief
et évitent l'eau, les murs et les chunks non chargés.

## Architecture

```
src/
  core/
    blocks.gd        registre des 47 blocs, tables plates indexées par id
    game.gd          autoload : InputMap et réglages persistants
  world/
    chunk_data.gd    stockage 16 x 96 x 16, RLE pour la sauvegarde
    terrain.gd       relief, biomes, grottes, minerais, décor
    mesher.gd        maillage par faces cachées, occlusion ambiante, lumière
    chunk_node.gd    MeshInstance3D d'un chunk et ses lumières
    world.gd         streaming, pool de threads, édition de blocs
    save_manager.gd  persistance des chunks modifiés
  entities/
    settlement_manager.gd  streaming des habitants depuis les maisons
    settlement_mob.gd      modèles procéduraux et routines de marche
  render/
    atlas.gd         génération des 53 tuiles en Texture2DArray
    materials.gd     un ShaderMaterial par surface
    sky.gd           cycle jour/nuit, brouillard, ambiance
    shaders/         opaque, découpe, translucide, eau, ciel
  player/
    voxel_body.gd    collision AABB contre la grille, sans moteur physique
    player.gd        contrôleur : marche, saut, nage, vol
    interaction.gd   visée par parcours de grille, casse et pose
    inventory.gd     36 cases, barre d'action, palette créative
  ui/
    hud.gd           réticule, barre d'action, progression de casse
    debug_overlay.gd panneau F3
    inventory_ui.gd  écran d'inventaire avec glisser-déposer
    pause_menu.gd    pause et réglages
  main.gd            câblage de l'ensemble
docs/CONTRACTS.md    spécification d'API entre modules
tests/               harnais headless
```

### Streaming des chunks

Un chunk est une colonne complète de 16 x 96 x 16, donc la hauteur du monde
tient dans un seul chunk et il n'y a jamais de streaming vertical : seul
l'anneau horizontal autour du joueur bouge.

Le cycle de vie est `MISSING` puis `GENERATING`, `GENERATED`, `MESHING`,
`LIVE`. La génération ne dépend que du chunk lui-même et se parallélise
librement. Le maillage a besoin des huit chunks voisins parce que l'occlusion
ambiante échantillonne les diagonales, donc un chunk n'est mis en file d'attente
de maillage qu'une fois tout son voisinage 3x3 généré. C'est la raison pour
laquelle le rayon de génération dépasse d'un chunk le rayon visible.

Les threads de travail lisent les données de chunk et appellent le générateur,
mais ne touchent jamais l'arbre de scène. Le volume rembourré est copié sous
mutex, puis le maillage coûteux tourne verrou relâché. Seul le thread principal
modifie les voxels, et uniquement depuis `set_block`.

### Maillage

Élimination des faces cachées sur un volume rembourré d'une cellule dans les six
directions, ce qui donne les voisins diagonaux dont l'occlusion ambiante a
besoin sans aucun test de bornes dans la boucle chaude.

Chaque chunk produit jusqu'à quatre surfaces (opaque, découpe, translucide,
eau), chacune avec son matériau. L'index de tuile voyage dans `CUSTOM0.x`, le
facteur d'ondulation au vent dans `CUSTOM0.y`, et l'ombrage directionnel de face
multiplié par la lumière du ciel, l'occlusion ambiante et la teinte de biome est
précalculé dans `COLOR.rgb`. Le shader ne réombrage jamais.

La lumière du ciel est une approximation volontairement locale : la décroissance
sous le plus haut bloc opaque de la colonne, prise au maximum sur les neuf
colonnes voisines. Elle ne dépend que du volume rembourré, donc elle est
identique de part et d'autre d'une frontière de chunk et ne produit aucune
couture, contrairement à une propagation par inondation limitée au chunk.

### Collision

Aucun `CollisionShape3D`, aucun `RigidBody3D`, la gravité du projet est à zéro.
Le joueur est une boîte alignée aux axes déplacée par
`VoxelBody.move()`, qui résout les collisions axe par axe dans l'ordre Y, X, Z
contre la grille de voxels, en sous-pas d'au plus 0,45 unité pour interdire la
traversée à grande vitesse. C'est la même approche que Minecraft, et elle rend
la casse et la pose de blocs immédiatement cohérentes avec la physique sans
reconstruire de forme de collision.

Un chunk non chargé est traité comme solide, ce qui empêche le joueur de tomber
dans le vide au bord de l'anneau chargé.

## Tests

```bash
# compilation de tout le projet : révèle les identifiants manquants entre modules
godot --headless --path . --editor --quit

# tests unitaires
godot --headless --path . --script res://tests/run_tests.gd

# test d'intégration : démarre le vrai jeu, laisse le monde se générer, puis vérifie
# streaming, terrain, édition de blocs, joueur, visée, ciel, inventaire et atlas
godot --headless --path . -- --smoke

# vérification syntaxique d'un seul fichier
godot --headless --path . --check-only --script res://src/world/mesher.gd

# captures d'écran : neuf points de vue et moments de la journée, pour juger le rendu
godot --path . -- --shot C:/chemin/de/sortie

# sonde libre : ajoute n'importe quel script comme noeud du vrai jeu
godot --path . -- --probe res://tests/ma_sonde.gd
```

Tous les harnais sortent en code 0 quand tout passe.

### Pourquoi le test d'intégration tourne dans le vrai jeu

Avec `--script`, Godot n'enregistre pas les autoloads du projet comme identifiants
globaux au moment de la compilation. Tout fichier mentionnant `Game` refuse alors de
compiler, et la moitié du projet le mentionne. Le test d'intégration est donc un noeud
sonde que `main.gd` ajoute à l'arbre quand il voit l'argument `--smoke`, ce qui a
l'avantage secondaire de tester le vrai chemin de démarrage. Les suites unitaires, elles,
sont chargées dynamiquement à l'exécution, donc elles ne rencontrent pas le problème.

### Écrire une suite de tests

Une suite étend `TestCase`, redéfinit `suite_name()`, et expose une méthode par propriété
nommée `test_quelque_chose`. **Chaque méthode de test doit appeler `done()` en dernière
instruction.** GDScript n'a pas d'exceptions : une erreur d'exécution interrompt la méthode
et rend la main au runner sans aucun signal, donc une suite dont tous les appels échouent
ressortirait verte. Le runner refuse toute méthode qui n'a pas atteint `done()` ou qui n'a
enregistré aucune vérification.

## Conventions

- Le texte affiché au joueur est en français, le code et les commentaires en
  anglais.
- `docs/CONTRACTS.md` est la source de vérité des interfaces entre modules.
- Aucune scène `.tscn` en dehors de `scenes/main.tscn` : toutes les hiérarchies
  de noeuds, y compris l'interface, sont construites par code.
- Typage statique partout où c'est possible.
