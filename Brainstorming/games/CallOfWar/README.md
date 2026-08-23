# CALL OF WAR - Normandie 1942

FPS en monde ouvert écrit en GDScript pour **Godot 4.7**. Été 1942, une poche de
Normandie occupée de 4 km sur 4 : bocage, champs de blé, marais, une rivière,
une falaise sur la côte est, et vingt-deux lieux tenus par la Wehrmacht. Vous
êtes un agent allié parachuté en liaison avec la Résistance. Objectif : libérer
les huit secteurs, un par un, dans l'ordre que vous voulez.

Le relief, les villages, les bâtiments, les armes et les 48 effets sonores sont
**générés par code** au démarrage : aucun fichier audio dans le dépôt.

Les **personnages** sont deux modèles glTF riggés (`assets/models`) : un soldat
en **CC0** et un zombie en **CC-BY 3.0**, tous deux de Quaternius, avec leurs
squelettes et leurs animations (voir `assets/models/CREDITS.md`, l'attribution du
zombie est obligatoire). Les soldats en boîtes d'origine restent en place comme
**repli** : supprimez `assets/models` et le jeu tourne toujours, les ennemis
redeviennent simplement anguleux. Environ trois ennemis de l'Axe sur dix portent
le modèle zombie ; c'est purement cosmétique, ils gardent la même IA et le même
fusil. Mettez `CharacterModels.ZOMBIE_SHARE` à `0.0` pour les faire disparaître.

Les **textures** sont des photographies **CC0** (Poly Haven et ambientCG, voir
`assets/textures/CREDITS.md`) : 13 matériaux en albédo, normale et AO/rugosité/
métal, plus un atlas de brins d'herbe avec alpha. Le générateur procédural
d'origine reste en place comme **repli** : supprimez `assets/textures` et le jeu
tourne toujours, il redevient simplement synthétique.

## Lancer le jeu

Sous Windows, double-cliquez sur **`run.bat`**. Il se place tout seul dans le
dossier du jeu, trouve `godot.exe` sur le `PATH` (ou aux emplacements
d'installation habituels), et ne laisse la fenêtre ouverte qu'en cas d'erreur.
Si votre Godot est ailleurs, pointez-le avec `set GODOT=C:\chemin\godot.exe`.

```bash
# ou à la main, depuis games/CallOfWar
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
| `B` | jumelles (zoom x8, télémètre, nom du site visé) |
| `1` à `4` / molette | changer d'arme |
| `M` | carte de la poche |
| `J` | journal de campagne |
| `F11` | plein écran |
| `F3` | infos de débogage (images/s, temps par image, échelon de qualité) |
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
ciel dégagé, couvert, pluie, brouillard, orage, neige. La nuit et la pluie
**raccourcissent réellement la portée de vue de l'IA** : s'infiltrer sous la
pluie change la partie.

## Le temps qu'il fait quelque part

Le largage d'ouverture se fait **sous la brume**, quelle que soit la graine :
vous arrivez à la première lumière et vous êtes censé ne pas être vu.

Passé cela, chaque lieu de la poche a **son propre ciel**, lu sur le pays où il
est bâti. La brume stagne dans les fonds de vallée et sur les marais, les bois
tiennent l'humidité, la crête boisée du nord est assez haute et assez exposée
pour recevoir la neige, et le reste de la campagne prend le mélange normand
ordinaire. Entrer dans le périmètre d'un lieu fait venir son ciel en une
vingtaine de secondes, et le quitter rend la main au tirage de campagne, qui
change d'heure en heure.

La conséquence se joue : un village de fond de vallée s'approche sous une brume
qui tient toute la journée, une crête enneigée coupe la vue des sentinelles
autant que la vôtre. Le HUD de débogage (`F3`) affiche le ciel courant et son
intensité.

La neige en Normandie l'été 1942 est un anachronisme assumé, et elle tient dans
une seule constante : passez `ALLOW_SNOW` à `false` dans
`src/render/weather.gd` et la crête reçoit de la pluie froide à la place, sans
rien changer d'autre.

## S'infiltrer

Un coup de crosse dans le dos d'une sentinelle qui ne vous a pas repéré est
**silencieux** : pas de cri, pas de bruit. Mais un soldat qui voit un cadavre
donne l'alerte, alors cachez votre approche autant que vos corps.

Détruire le **mât radio** d'un site avant d'être vu coupe ses renforts : la
garnison ne peut plus appeler personne. Repérez-le aux jumelles, sabotez-le,
puis attaquez.

Libérer un secteur sans jamais dépasser l'alerte « recherche » compte comme une
**capture silencieuse**, annoncée comme telle et créditée au rapport final.

Dans un secteur libéré, `E` sur un résistant le recrute (deux compagnons au
maximum, mort définitive). Ils **ne tirent pas** tant que l'alerte est calme et
que vous n'avez pas tiré le premier : ils ne ruineront pas votre approche.

## La guerre répond

Un secteur pris peut faire l'objet d'une **contre-attaque** annoncée 90 secondes
à l'avance. La repousser vous laisse la place et remet la caisse de
ravitaillement à zéro ; la perdre rend le secteur **contesté**, à reprendre. La
chaîne d'objectifs déjà accomplie, elle, reste acquise.

Les officiers portent des **documents** : les fouiller révèle sur la carte la
garnison restante et les ancres d'objectif de leur site. Sans cela, la carte
reste muette.

La carte (`M`) permet de **rallier un secteur libéré** sans refaire la route à
pied, quand l'alerte est calme. Les compagnons à moins de 30 m suivent.

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

## Fluidité

Le jeu ajuste sa qualité tout seul plutôt que de vous faire choisir un réglage
pour le pire cas. Cinq échelons, un pas à la fois : l'image 3D est rendue un
peu plus petite et remise à l'échelle (le HUD, lui, reste toujours net), la
végétation lointaine se dissout plus près, puis le filtrage des ombres et
l'anticrénelage tombent. Dès que la pression retombe, il remonte.

`F3` montre l'échelon courant, les images par seconde et la pire image de la
dernière seconde. Pour figer la qualité (une capture, un comparatif), décochez
« qualité adaptative » dans les réglages.

Une chose n'est **pas** touchée automatiquement : votre distance d'affichage.
C'est votre réglage, et un jeu qui réécrit vos préférences dans votre dos est
un défaut.

## Traverser la poche

Une course tenue quatre secondes sans viser, sans tirer et hors alerte passe en
allure de marche : la même distance se fait en une minute quarante au lieu de
trois minutes et demie. Elle se perd quatre fois plus vite qu'elle ne se
gagne, donc arriver au contact ne vous laisse jamais lancé.

## Structure du projet

```
src/core/       reglages, InputMap, etat de la campagne, couches de collision
src/audio/      synthese sonore par code et pool de lecteurs
src/render/     palette, textures procedurales, materiaux, ciel, meteo, qualite
src/world/      plan du monde, terrain, streaming, batiments, decor, personnages
src/player/     controleur FPS et support de camera
src/weapons/    table d'armes, balistique, effets, modele en vue subjective
src/ai/         perception, soldats, escouades, affuts, pilote d'animation
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

`run.bat` transmet ses arguments a Godot, donc `run.bat -- --smoke` et
`run.bat --headless --quit-after 120` marchent aussi, depuis n'importe ou.

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
