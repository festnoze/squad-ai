---
name: Notes API
package: notes_api
profile: api
goal: Une API HTTP de prise de notes (FastAPI + SQLite) avec CRUD, validation et recherche.
---
# Brief : Notes API

Une API HTTP de prise de notes en Python, avec FastAPI et une base SQLite fichier.

## Interface publique (contractuelle, testée telle quelle)

- Paquet `notes_api` (dossier `notes_api/` à la racine du dépôt).
- `python -m notes_api` démarre le serveur HTTP (uvicorn) sur l'hôte `127.0.0.1` et le
  port donné par la variable d'environnement `PORT` (défaut `8000`).
- La base SQLite est le fichier désigné par la variable d'environnement `NOTES_DB`
  (défaut `notes.db` dans le répertoire courant), créée au démarrage si elle n'existe
  pas. Les données survivent à un redémarrage du serveur avec le même `NOTES_DB`.

Une note est un objet JSON :

```json
{"id": 1, "title": "Courses", "body": "lait, pain", "created_at": "2026-11-02T10:00:00+00:00"}
```

- `id` : entier attribué par le serveur, croissant.
- `title` : chaîne obligatoire de 1 à 120 caractères ; une chaîne vide ou plus longue
  que 120 caractères est refusée.
- `body` : chaîne, éventuellement vide ; vaut `""` si elle est absente.
- `created_at` : date et heure de création au format ISO 8601, fixée à la création.

Routes :

| Méthode et chemin | Corps | Succès | Erreurs |
|---|---|---|---|
| `GET /health` | | 200 `{"status": "ok"}` | |
| `POST /notes` | `{"title", "body"}` | 201, la note créée | 422 si titre invalide |
| `GET /notes` | | 200, tableau JSON des notes triées par `id` croissant | |
| `GET /notes?q=terme` | | 200, seulement les notes dont le titre ou le corps contient `terme`, sans tenir compte de la casse, triées par `id` | |
| `GET /notes/{id}` | | 200, la note | 404 si absente |
| `PUT /notes/{id}` | `{"title", "body"}` | 200, la note modifiée (même `id`, même `created_at`) | 404 si absente, 422 si titre invalide |
| `DELETE /notes/{id}` | | 204, corps vide | 404 si absente |

Une note supprimée n'est plus listée et `GET /notes/{id}` renvoie alors 404.

## Contraintes de livraison

- Projet Python géré par uv : `pyproject.toml` et `uv.lock` à jour à la racine du dépôt,
  `fastapi` et `uvicorn` déclarés comme dépendances d'exécution.
- Tests pytest dans `tests/`, lancés par `uv run pytest`, tous verts.

## Hors périmètre

Authentification, pagination, étiquettes, interface web.
