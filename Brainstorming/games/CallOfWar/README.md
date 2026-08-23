# CALL OF WAR - Normandie 1942

FPS en monde ouvert écrit en GDScript pour **Godot 4.7**. Été 1942, une poche de
Normandie occupée de 4 km sur 4 : bocage, champs de blé, marais, une rivière,
une falaise sur la côte est, et vingt-deux lieux tenus par la Wehrmacht. Vous
êtes un agent allié parachuté en liaison avec la Résistance. Objectif : libérer
les huit secteurs, un par un, dans l'ordre que vous voulez.

Le relief, les villages, les bâtiments, les corps, les armes et les 48 effets
sonores sont **générés par code** au démarrage : aucun modèle 3D, aucun fichier
audio dans le dépôt.

Les **textures** sont des photographies **CC0** (Poly Haven et ambientCG, voir
`assets/textures/CREDITS.md`) : 13 matériaux en albédo, normale et AO/rugosité/
métal, plus un atlas de brins d'herbe avec alpha. Le générateur procédural
d'origine reste en place comme **repli** : supprimez `assets/textures` et le jeu
tourne toujours, il redevient simplement synthétique.

## Lancer le jeu

```bash
# depuis games/CallOfWar
godot --path .
```

Ou ouvrir le dossier dans l'éditeur Godot et appuyer sur F5.

Le premier démarrage tire une graine de campagne au hasard et la conserve dans
`user://settings.cfg`, donc la même Normandie revient au lancement suivant. La
progression (secteurs libérés, objectifs, inventaire, statistiques) est écrite
dans `user://saves/normandie.json`.

## Commandes

| Touche | Action |
|---|---|
| `ZQSD` / `WASD` / flèches | se déplacer |
| Souris | regarder |
| `Maj` | courir |
| `Ctrl` | s'accroupir |
| `X` | se coucher |
| `Espace` | sauter |
| Clic gauche | tirer |
| Clic droit | viser (lunette sur la Springfield) |
| `R` | recharger |
| `V` | coup de crosse |
| `G` | grenade (maintenir pour la « cuisiner ») |
| `E` | interagir, ramasser une arme, prendre une mitrailleuse |
| `H` | pansement |
| `B` | jumelles |
| `1` à `4` / molette | changer d'arme |
| `M` | carte de la poche |
| `J` | journal de campagne |
| `F11` | plein écran |
| `F3` | infos de débogage |
| `F2` | capture d'écran (dans `user://screenshots/`) |
| `Échap` | pause et réglages |

Les touches sont liées par **keycode physique** : un clavier AZERTY pilote ZQSD
exactement là où un QWERTY pilote WASD, sans rien configurer.

## Le monde

Un carré de 4096 m centré sur l'origine, entièrement procédural et déterministe
à partir de la graine de campagne. Il est découpé en tuiles de 64 m chargées et
déchargées autour du joueur, avec quatre niveaux de détail et la collision
seulement sur l'anneau proche.

Vingt-deux lieux y sont posés par échantillonnage de Poisson (jamais moins de
180 m entre deux) : villages de pierre à toits d'ardoise, bourg à clocher,
fermes à cour fermée, aérodrome de campagne, bunkers et tranchées, camp de
prisonniers, barrages routiers, un pont sur la rivière, un village en ruines.
Un réseau routier les relie et aplanit le terrain sous lui.

Huit de ces lieux sont des **secteurs capturables**. Le reste est du décor
défendu, du ravitaillement et des embuscades.

Cycle jour/nuit complet (vingt minutes pour un jour) et météo déterministe :
ciel dégagé, couvert, pluie, brouillard, orage. La nuit et la pluie **raccourcis-
sent réellement la portée de vue de l'IA** : s'infiltrer sous la pluie change la
partie.

## Le combat

Sept armes d'époque plus la grenade Mk2 : M1 Garand, Thompson M1928, Springfield
M1903A4 à lunette, Colt M1911, et côté allemand la MP40, le Kar98k et la MG42 en
affût, toutes ramassables sur les corps. Les munitions sont partagées par
calibre, donc prendre un Kar98k sur un mort vous ouvre les caisses de 7.92.

Balistique par rayon avec dispersion en cône, atténuation des dégâts avec la
distance, tirs à la tête, et **pénétration** des cloisons fines. Les traceurs
voyagent à la vitesse de l'arme au lieu d'apparaître instantanément, ce qui rend
les échanges de tirs lisibles.

## L'ennemi

Les soldats allemands se déplacent sans navmesh (le monde est streamé) : pilotage
direct, suivi du terrain, évitement par rayons, et une garde anti-blocage qui
empêche les soldats de vibrer contre un mur.

Six rangs, du conscrit au mitrailleur, chacun avec sa santé, son arme et sa
précision. Ils ont un **temps de réaction**, une précision qui converge au lieu
d'être parfaite au premier coup, ils tirent par rafales, se mettent à couvert,
flanquent, se laissent supprimer par des balles qui passent près, et gardent en
mémoire votre dernière position connue pendant une vingtaine de secondes avant
d'abandonner. Un officier tué fait paniquer les conscrits autour de lui.

Ils ne sont pas omniscients : cône de vision, ligne de vue réelle, portée
réduite la nuit et sous la pluie.

## Structure du projet

```
src/core/       reglages, InputMap, etat de la campagne, couches de collision
src/audio/      synthese sonore par code et pool de lecteurs
src/render/     palette, textures procedurales, materiaux, ciel, meteo
src/world/      plan du monde, fonction de terrain, streaming, batiments, decor
src/player/     controleur FPS et support de camera
src/weapons/    table d'armes, balistique, effets, modele en vue subjective
src/ai/         perception, soldats, escouades, affuts
src/mission/    objectifs de campagne, suivi, director
src/ui/         HUD, carte, journal, menu pause
src/save/       persistance JSON
```

`docs/CONTRACTS.md` est la **source de vérité** des interfaces entre modules. Le
projet a été bâti par douze agents travaillant en parallèle, chacun sur un
module, tous écrivant contre ce document. Ne change jamais une signature qui y
figure sans mettre le document à jour.

## Tester sans ouvrir l'éditeur

```bash
# suites unitaires (fonctions pures : terrain, armes, layout, sons)
godot --headless --path . --script res://tests/run_tests.gd

# controle d'integration : compile tout le projet et revele les identifiants manquants
godot --headless --path . --editor --quit

# sonde d'integration dans le vrai jeu (monde, joueur, armes, campagne, IA)
godot --headless --path . -- --smoke

# captures d'ecran automatiques de chaque type de lieu
godot --path . -- --shot C:/chemin/de/sortie
```

Le harnais de test refuse de compter comme réussie une méthode qui n'a exécuté
aucune vérification ou qui n'a pas atteint son `done()` final : sans ces deux
garde-fous, une suite dont tous les appels échouent ressort verte, parce que
GDScript n'a pas d'exceptions et qu'une erreur d'exécution interrompt la méthode
en rendant silencieusement la main.

Piège à connaître : avec `--script <MainLoop>`, Godot n'enregistre pas les
autoloads du projet, donc tout fichier mentionnant `Game`, `War` ou `Sfx` refuse
de compiler dans ce contexte. Les suites sont donc chargées par `load()` à
l'exécution, et tout ce qui a besoin du jeu qui tourne passe par la sonde
`--smoke`, montée dans le vrai chemin de démarrage.
