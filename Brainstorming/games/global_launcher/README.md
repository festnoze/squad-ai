# GLOBAL LAUNCHER

Console de lancement des jeux du dossier `games/`. Elle liste les jeux presents
dans les sous-dossiers voisins, demarre le serveur web de celui qu'on choisit
s'il ne tourne pas deja, et ouvre le jeu dans un nouvel onglet.

## Lancer

```
python launcher.py
```

(ou double-clic sur `start.cmd` sous Windows)

Le launcher ecoute sur `http://localhost:8099/` et ouvre lui-meme cet onglet.
Options: `--port <n>` pour changer son port, `--no-open` pour ne pas ouvrir le
navigateur.

Aucune dependance: bibliotheque standard Python uniquement (3.10+).

## Ce qu'il fait au clic sur "Jouer"

1. Si le port du jeu repond deja (serveur lance a la main ou dans une session
   precedente), il ouvre simplement l'onglet.
2. Sinon, si le jeu est un projet npm sans `node_modules`, il lance `npm install`.
3. Il demarre la commande de serveur du jeu dans son propre dossier.
4. Il attend que le port reponde, puis pointe l'onglet deja ouvert vers le jeu.

L'onglet est ouvert des le clic (et non apres la reponse du serveur) pour ne pas
etre bloque par le bloqueur de fenetres du navigateur.

"Arreter" tue l'arborescence de processus du serveur lance par le launcher. Les
serveurs demarres en dehors du launcher sont marques "deja en ligne" et ne sont
pas tues. Quitter le launcher (Ctrl+C) arrete tous les serveurs qu'il a lances.

## Detection des jeux

Un sous-dossier de `games/` est considere comme un jeu s'il contient un
`index.html` a sa racine. Pour chacun, le launcher deduit:

| Champ | Source, dans l'ordre |
| --- | --- |
| Nom | `launcher.json` > premier titre `#` du README > nom du dossier |
| Description | `launcher.json` > premier paragraphe du README > `description` du package.json |
| Port | `launcher.json` > `--port`/`http.server` du script npm > `port` de vite.config.js > `DEFAULT_PORT` de serve.py > `localhost:xxxx` du README > 8200+n |
| Commande | `launcher.json` > script npm `dev`/`start`/`serve`/`preview` > `serve.py` > `python -m http.server` |
| Visuel | `launcher.json` > `cover.png`, `docs/screenshot.png`, `shots/smoke.png`... |

Etat actuel de la detection:

| Jeu | Port | Commande |
| --- | --- | --- |
| ASHFALL - Sector 7 (`FPS`) | 8094 | `python serve.py 8094` |
| Liberty Horizon (`GTA`) | 8092 | `npm run dev` (vite) |
| PRISON SCAPE (`prison_scape`) | 8091 | `python -m http.server 8091` |
| VELOCITRON (`wipeout`) | 8093 | `python serve.py 8093` |
| ABYSSE (`diver_game`) | 8095 | `python serve.py 8095` |
| TERRAFORM ODYSSEY (`Space Invader`) | 5310 | `npm run dev` (vite) |

## Ajouter un jeu

Deposer le dossier du jeu dans `games/`. S'il a un `index.html` et une commande
de serveur reconnaissable, il apparait tout seul (la liste est rescannee toutes
les quelques secondes, sans redemarrer le launcher).

Pour forcer les valeurs, poser un `launcher.json` a la racine du jeu:

```json
{
  "name": "MON JEU",
  "description": "Une ligne de pitch.",
  "port": 8096,
  "command": "python serve.py 8096",
  "entry": "index.html",
  "cover": "docs/cover.png"
}
```

## API

Le launcher expose aussi une petite API JSON, pratique pour scripter:

- `GET /api/games` - liste des jeux avec leur etat (`stopped`, `installing`, `starting`, `running`, `external`, `error`)
- `POST /api/launch` `{"id": "wipeout"}` - demarre si besoin
- `POST /api/stop` `{"id": "wipeout"}` - arrete le serveur lance par le launcher
- `GET /api/logs?id=wipeout` - 200 dernieres lignes de sortie du serveur
- `GET /api/cover?id=wipeout` - visuel du jeu
