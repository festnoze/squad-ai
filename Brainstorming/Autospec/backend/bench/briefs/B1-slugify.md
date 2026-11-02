---
name: Slugify lib
package: slugify_lib
profile: lib
goal: Une petite bibliothèque Python de slugification de chaînes.
---
# Brief : bibliothèque slugify

Une bibliothèque Python minimale, sans dépendance d'exécution, qui transforme une
chaîne de caractères en slug d'URL.

## Interface publique (contractuelle, testée telle quelle)

- Paquet importable : `slugify_lib`, dossier `slugify_lib/` à la racine du dépôt.
- Fonction : `slugify(text: str, max_length: int | None = None) -> str`, importable par
  `from slugify_lib import slugify`.

## Règles

1. Les accents sont retirés : décomposition Unicode NFKD, puis suppression de tout ce
   qui n'est pas ASCII (`é` devient `e`, `Ç` devient `c`, `€` disparaît).
2. Le résultat est en minuscules.
3. Seuls les caractères `a-z` et `0-9` sont conservés. Toute suite d'autres caractères
   (espaces, ponctuation, tiret bas `_`, symboles) devient un seul tiret `-`.
4. Jamais de tiret en début ni en fin de résultat.
5. Une entrée vide, ou qui ne contient aucun caractère conservé, renvoie `""`.
6. `max_length` (optionnel, entier strictement positif ; `None` = pas de limite) : si le
   slug dépasse `max_length` caractères, il est tronqué sur une frontière de mot (un mot
   est une suite de caractères entre deux tirets). On garde le plus long préfixe fait de
   mots entiers dont la longueur ne dépasse pas `max_length`, sans tiret final. Si le
   premier mot dépasse à lui seul `max_length`, il est coupé à exactement `max_length`
   caractères. Un slug déjà assez court est renvoyé inchangé.

## Exemples

| Appel | Résultat |
|---|---|
| `slugify("Hello, World!")` | `"hello-world"` |
| `slugify("  Étude   de  CAS ")` | `"etude-de-cas"` |
| `slugify("")` | `""` |
| `slugify("snake_case v2.0")` | `"snake-case-v2-0"` |
| `slugify("Hello beautiful world", max_length=15)` | `"hello-beautiful"` |
| `slugify("Hello beautiful world", max_length=12)` | `"hello"` |
| `slugify("Anticonstitutionnellement", max_length=10)` | `"anticonsti"` |

## Contraintes de livraison

- Projet Python géré par uv : `pyproject.toml` et `uv.lock` à jour à la racine du dépôt.
- Le paquet est importable depuis la racine du dépôt.
- Tests pytest dans `tests/`, lancés par `uv run pytest`, tous verts.

## Hors périmètre

Interface en ligne de commande, configuration, translittération des alphabets non
latins.
