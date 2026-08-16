# ARCADE

Console de jeux mono-origine. Un processus, un port, une page: tous les jeux de
`games/` sont servis sous la meme origine et joues dans la meme SPA.

## Lancer

Double-clic sur **`games/ARCADE.bat`** (un cran au dessus de ce dossier), ou en
ligne de commande:

```
python arcade.py
```

`ARCADE.bat` prend le venv du depot s'il existe, sinon le `python` du PATH,
sinon `py`, et garde sa fenetre ouverte si le lancement echoue. Il passe ses
arguments tels quels: `ARCADE.bat --port 9000`. `start.cmd`, dans ce dossier,
fait la meme chose pour qui est deja dedans.

Ouvre `http://localhost:8088/`. Options: `--port <n>`, `--no-open`.
Aucune dependance, bibliotheque standard Python uniquement (3.10+).

## Pourquoi pas un serveur par jeu

`games/global_launcher` demarre un serveur et un port par jeu, puis ouvre un
onglet dessus. Ca marche, mais chaque jeu ajoute un port a reserver, un
processus a surveiller et a tuer, et un etat a deviner par sonde reseau. Trois
pannes concretes en sont sorties: un service tiers squattait le port par defaut
d'un jeu et le launcher le prenait pour le jeu; les serveurs survivaient au
launcher; l'inventaire mettait cinq secondes a repondre parce qu'il sondait
chaque port en serie.

Ici il n'y a rien a allouer ni a superviser:

| | global_launcher | arcade |
| --- | --- | --- |
| Processus | 1 + 1 par jeu lance | 1 |
| Ports | 1 + 1 par jeu | 1 |
| Etat d'un jeu | sonde TCP par port | aucun etat a deviner |
| Inventaire (6 jeux) | ~5,6 s | ~0,2 s |
| Changer de jeu | demarrer un serveur, attendre le port, nouvel onglet | instantane, meme page |
| Retour a la console | fermer l'onglet | bouton, `F2`, ou Precedent |
| Collision de port | possible (deja vue) | impossible |

## Un seul jeu a la fois

C'est une propriete de structure, pas une regle appliquee a la main: la scene ne
contient qu'une iframe. En monter une autre demonte la precedente, et retirer
une iframe du DOM detruit d'un coup sa boucle `requestAnimationFrame`, son
contexte WebGL/WebGPU, son `AudioContext`, ses workers et ses ecouteurs. Aucun
jeu n'a besoin d'exposer une fonction d'arret, et aucun ne peut continuer a
tourner en fond.

Verifie: 12 cycles montage/demontage sur les 6 jeux, jamais plus d'une iframe,
zero erreur console.

## Revenir a la console

- le bouton **Console** dans la barre du haut (elle se retire seule et revient
  quand la souris remonte, ou quand le jeu relache le pointeur)
- **F2** en toutes circonstances
- **Maj+Echap**, une fois le pointeur relache (le navigateur avale `Echap` tant
  que le pointeur est verrouille, donc ce raccourci ne peut pas etre le seul)
- le bouton **Precedent** du navigateur

Le raccourci est greffe dans le document du jeu par la console. C'est possible
parce que console et jeux partagent l'origine, et ca ne demande aucune
modification des jeux.

## Detection des jeux

Un sous-dossier de `games/` est un jeu s'il livre un `index.html`, a sa racine
ou dans `dist/`. Pour chacun:

| Champ | Source, dans l'ordre |
| --- | --- |
| Nom | `arcade.json` > `launcher.json` > premier titre `#` du README > nom du dossier |
| Description | `arcade.json` > `launcher.json` > premier paragraphe du README > `description` du package.json |
| Racine servie | `dist/` si le package.json a un script `build`, sinon le dossier |
| Vignette | generee a partir de l'identifiant (aucun visuel a fournir) |

Etat actuel:

| Jeu | Route | Servi depuis |
| --- | --- | --- |
| ABYSSE (`diver_game`) | `/g/diver_game/` | dossier |
| ASHFALL - Sector 7 (`FPS`) | `/g/FPS/` | dossier |
| Liberty Horizon (`GTA`) | `/g/GTA/` | `dist/` |
| PRISON SCAPE (`prison_scape`) | `/g/prison_scape/` | dossier |
| TERRAFORM ODYSSEY (`Space Invader`) | `/g/Space Invader/` | `dist/` |
| VELOCITRON (`wipeout`) | `/g/wipeout/` | dossier |

Le scan tourne toutes les 3 secondes: un jeu ajoute, un `arcade.json` edite ou
un `dist/` fraichement construit apparaissent sans redemarrer le serveur.

## Ajouter un jeu

Deposer le dossier dans `games/`. S'il a un `index.html` et des chemins
relatifs, il apparait tout seul. Pour forcer les valeurs, poser un
`arcade.json` a la racine du jeu:

```json
{
  "name": "MON JEU",
  "description": "Une ligne de pitch.",
  "entry": "index.html",
  "accent": 210
}
```

`accent` est une teinte HSL (0-359) pour la vignette. Il n'y a pas de champ
`port` ni `command`: il n'y a plus rien a demarrer.

## Jeux avec build

Un jeu qui declare un script `build` est servi depuis son `dist/`. Deux
consequences:

- **il doit etre construit avec une base relative.** Pour Vite, `base: './'`
  dans `vite.config.js`. Sans ca les assets partent a la racine de l'origine et
  ne resolvent pas sous `/g/<id>/`. Le serveur rattrape ce cas via le `Referer`
  et le signale dans sa console, mais c'est un filet, pas une solution.
- **il faut relancer le build apres modification.** La console affiche
  `dist/ plus ancien que src/` quand le build est en retard, et
  `A construire` avec la commande exacte quand `dist/` n'existe pas.

Pour iterer sur un jeu Vite avec le rechargement a chaud, `npm run dev` dans son
dossier reste la bonne facon de faire. L'arcade sert le resultat construit, pas
le serveur de dev.

## API

- `GET /api/games` - inventaire (nom, route, pret ou non, build en retard)
- `GET /g/<id>/<chemin>` - fichiers du jeu, sans cache, hors du dossier interdit
- `GET /play/<id>` - la SPA, positionnee directement sur ce jeu

## Ce que l'arcade ne fait pas

- pas de rechargement a chaud pour les jeux a build (voir plus haut)
- pas de requetes `Range`, donc pas de streaming audio/video partiel: les jeux
  du dossier generent leur son en code, aucun n'en a besoin aujourd'hui
- les jeux partagent l'origine, donc ils partagent `localStorage`. Les jeux
  actuels prefixent deja leurs cles (`ashfall.`, `abysse.`), ce qui suffit; un
  nouveau jeu doit faire pareil.
