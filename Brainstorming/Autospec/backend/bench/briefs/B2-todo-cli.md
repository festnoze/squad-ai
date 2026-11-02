---
name: Todo CLI
package: todo_cli
profile: cli
goal: Une petite application en ligne de commande de gestion de tâches, persistée dans un fichier JSON.
---
# Brief : Todo CLI

Une application Python en ligne de commande, sans dépendance d'exécution, pour gérer
une liste de tâches persistée dans un fichier JSON.

## Interface publique (contractuelle, testée telle quelle)

Paquet `todo_cli` (dossier `todo_cli/` à la racine du dépôt), exécutable par
`python -m todo_cli` (fichier `todo_cli/__main__.py`) :

```
python -m todo_cli [--db PATH] <commande> [arguments]
```

- `--db PATH` : option globale, placée avant la commande. Chemin du fichier JSON de
  persistance ; défaut : `todo.json` dans le répertoire courant.
- `--help` : affiche l'aide sur la sortie standard et sort avec le code 0.

Commandes :

| Commande | Effet | Sortie standard | Code de sortie |
|---|---|---|---|
| `add TITLE` | ajoute une tâche non faite | l'id entier de la nouvelle tâche, seul sur sa ligne | 0 |
| `list` | liste les tâches | une ligne par tâche, triées par id croissant | 0 |
| `done ID` | marque la tâche comme faite | libre | 0 |
| `remove ID` | supprime la tâche | libre | 0 |

Format d'une ligne de `list`, avec un espace entre chaque élément :

```
<id> [ ] <titre>      tâche à faire
<id> [x] <titre>      tâche faite
```

Exemple :

```
$ python -m todo_cli --db t.json add "Acheter du pain"
1
$ python -m todo_cli --db t.json add "Payer le loyer"
2
$ python -m todo_cli --db t.json done 1
$ python -m todo_cli --db t.json list
1 [x] Acheter du pain
2 [ ] Payer le loyer
```

## Règles

1. Les ids sont des entiers attribués à partir de 1, dans l'ordre d'ajout, et ne sont
   jamais réutilisés, même après la suppression d'une tâche (après suppression de la
   tâche 2 sur 1 et 2, l'ajout suivant reçoit l'id 3).
2. Le titre est enregistré sans les espaces de début et de fin.
3. Titre vide ou composé uniquement d'espaces : rien n'est enregistré, un message
   d'erreur est écrit sur la sortie d'erreur, code de sortie 2.
4. `done` ou `remove` sur un id inexistant : rien n'est modifié, un message d'erreur est
   écrit sur la sortie d'erreur, code de sortie 1.
5. Persistance : chaque commande est un processus séparé, l'état est relu puis réécrit
   dans le fichier `--db`. Le fichier est un document JSON valide, créé au premier
   enregistrement s'il n'existe pas. `list` sur un fichier absent n'affiche rien et sort
   avec le code 0.
6. Liste vide : `list` n'affiche rien (aucune ligne) et sort avec le code 0.

## Contraintes de livraison

- Projet Python géré par uv : `pyproject.toml` et `uv.lock` à jour à la racine du dépôt.
- Tests pytest dans `tests/`, lancés par `uv run pytest`, tous verts.

## Hors périmètre

Priorités, dates d'échéance, édition d'un titre, couleurs, interface interactive.
