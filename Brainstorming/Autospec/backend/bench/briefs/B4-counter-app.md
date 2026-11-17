---
name: Counter webapp
package: counter_app
profile: fullstack
goal: Une mini application web compteur : API FastAPI persistée en SQLite et page React servie par le même processus.
---
# Brief : application web compteur

Une petite application web complète : une API FastAPI qui gère un compteur persisté en
SQLite, et une page React (Vite, TypeScript) servie par le même processus FastAPI.

## Interface publique (contractuelle, testée telle quelle)

Backend :

- Paquet `counter_app` (dossier `counter_app/` à la racine du dépôt).
- `python -m counter_app` démarre le serveur HTTP (uvicorn) sur l'hôte `127.0.0.1` et le
  port donné par la variable d'environnement `PORT` (défaut `8000`).
- La valeur est persistée dans le fichier SQLite désigné par la variable
  d'environnement `COUNTER_DB` (défaut `counter.db` dans le répertoire courant) et
  survit à un redémarrage du serveur avec le même `COUNTER_DB`.

| Méthode et chemin | Réponse |
|---|---|
| `GET /health` | 200 `{"status": "ok"}` |
| `GET /api/counter` | 200 `{"value": n}` ; `n` vaut 0 au premier démarrage |
| `POST /api/counter/increment` | 200 `{"value": n}`, la nouvelle valeur (ancienne + 1) |
| `POST /api/counter/reset` | 200 `{"value": 0}` |
| `GET /` | 200, la page HTML construite du frontend |

Frontend :

- Application React + Vite en TypeScript dans `frontend/`, avec `package.json` et
  `package-lock.json`. `npm ci` puis `npm run build` produisent `frontend/dist/`.
- Le serveur FastAPI sert `frontend/dist/index.html` sur `GET /` (page qui contient
  `<div id="root">`) et les fichiers construits de `frontend/dist/` (par exemple
  `/assets/...`), sans serveur séparé.
- La page affiche la valeur courante du compteur, un bouton « +1 » qui appelle
  `POST /api/counter/increment` et un bouton « Remise à zéro » qui appelle
  `POST /api/counter/reset`, puis affiche la valeur renvoyée.

## Contraintes de livraison

- Projet Python géré par uv : `pyproject.toml` et `uv.lock` à jour à la racine du dépôt,
  `fastapi` et `uvicorn` déclarés comme dépendances d'exécution.
- Tests pytest dans `tests/` (`uv run pytest`) et tests du frontend, tous verts.

## Hors périmètre

Plusieurs compteurs, authentification, temps réel, déploiement Docker.
