# Autospec

Usine logicielle pilotée par des agents : un besoin en entrée, un produit testé et vérifié en
sortie. Ce dépôt porte la **v2**, une réécriture sur la branche `refonte-v2` : un noyau séquentiel
et court, qui laisse l'agent coder avec ses outils natifs et vérifie lui-même chaque résultat.
Pourquoi et comment : [docs/REFONTE_V2.md](docs/REFONTE_V2.md). Où on en est :
[docs/STATE.md](docs/STATE.md).

## Ce que fait la v2

Un projet est un dépôt git dans son propre espace de travail. Il traverse les phases `brief`,
`plan`, `build`, `deliver`, puis s'arrête en `done`, `needs_attention`, `stopped` ou `error`.

1. **Brief.** Fourni tel quel, ou rédigé par l'agent PM à partir d'un objectif en une phrase.
2. **Plan.** L'agent PO produit epics, stories, critères d'acceptance identifiés (`US-1.AC-2`),
   dépendances, priorités et profil du produit (`lib`, `cli`, `api`, `fullstack`). **Taille
   adaptative** : une seule story quand le produit tient dans une session d'agent (environ 8
   fichiers et 8 critères), un découpage seulement au-delà.
3. **Build**, une story à la fois dans l'ordre des dépendances :
   - **QA** : l'agent QA écrit les tests d'acceptance exécutables (`tests/acceptance/test_us_<n>.py`,
     plus `frontend/src/acceptance/us_<n>.test.tsx` en fullstack). L'usine les exécute avant toute
     implémentation : ils doivent être collectés et **rouges** ; un test déjà vert grâce à une
     story précédente est gardé comme garde-fou de non-régression, et si tous le sont, la story
     est déclarée livrée sans session dev. L'usine prend ensuite leur empreinte et les commite.
   - **Dev** : une session Claude Code native (Read, Edit, Write, Glob, Grep et un Bash restreint
     par liste blanche aux commandes `uv` et `npm` du projet), confinée à l'espace de travail et
     hermétique (`--safe-mode` : ni CLAUDE.md, ni hooks, ni skills de l'utilisateur). Elle
     travaille en TDD jusqu'au vert, sans droit sur les tests d'acceptance.
   - **Vérification indépendante** par l'usine : environnement reconstruit depuis `pyproject.toml`
     et `uv.lock` (plus `npm ci`), suite complète, empreinte des tests d'acceptance inchangée,
     chaque critère couvert par au moins un test vert. Un échec relance la session dev avec la
     sortie de la vérification (3 tentatives) ; au-delà, le projet passe en `needs_attention`.
4. **Deliver** : suite complète en environnement propre puis **smoke** selon le profil (import du
   paquet, `python -m <paquet> --help`, `GET /health` 200, plus `GET /` et le build du frontend
   en fullstack).

Une panne du fournisseur ne consomme pas de tentative. Une coupure réseau est réessayée deux fois
(après 30 s puis 90 s) avant que le projet soit garé ; une limite d'usage (ou un budget atteint)
le gare tout de suite. Un projet garé est repris plus tard : à la main, ou automatiquement par le
serveur à l'heure de levée de la limite (sinon après 5 min pour le réseau, 30 min pour une limite).

## Lancer

Prérequis : Python 3.11 ou plus, `uv`, `git`, le CLI `claude` (Claude Code) connecté pour les vrais
runs, Node 24 et npm pour le profil fullstack et `frontend_v2`.

Toutes les commandes Python se lancent depuis `backend/`, venv activé :

```bash
cd backend
uv sync --extra dev
source .venv/Scripts/activate          # PowerShell : .venv/Scripts/Activate.ps1
```

### En ligne de commande

```bash
python -m autospec.core run --name "Todo CLI" --profile cli --brief-file chemin/vers/brief.md
python -m autospec.core run --name "Notes" --goal "Une API de notes avec recherche plein texte"
python -m autospec.core run --name "Demo" --goal "demo" --fake   # agents scriptés, aucun appel LLM
python -m autospec.core resume ../workspace_v2/<id-du-projet>
```

`--profile` et `--package` sont facultatifs (le PO choisit le profil, le paquet dérive du nom).
La progression s'affiche sur stderr ; la dernière ligne de stdout est un résumé JSON. Code de
sortie 0 si le projet finit en `done`, 1 sinon. Les espaces de travail vivent dans `workspace_v2/`,
l'état de l'usine dans `<projet>/.autospec/` (`state.json`, `events.jsonl`, journaux).

### Serveur et interface web

```bash
python -m autospec.core serve --port 8400          # --fake pour des agents scriptés
cd ../frontend_v2 && npm ci && npm run dev         # http://localhost:5400, /api relayé vers 8400
```

L'API HTTP vit sous `/api/v2` : projets (liste, création, détail, suppression), reprise, arrêt,
événements en flux SSE, fichiers du produit et diff par story. L'interface, en français, liste les
projets, en crée, et montre pour chacun ses stories, leurs critères et tests d'acceptance, le
journal en direct, les fichiers et les diffs. Une fois construite (`npm run build`), elle est aussi
servie par le serveur sur `/`. Contrat complet : [docs/v2/CONTRACTS.md](docs/v2/CONTRACTS.md)
section 9.

### Réglages

Variables d'environnement préfixées `AUTOSPEC2_`, toutes facultatives
(`backend/autospec/core/settings.py`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `CLAUDE_CMD` | `claude` | commande du CLI Claude Code |
| `MODEL`, `PLAN_MODEL` | `sonnet`, même modèle | modèle des agents, modèle du PM et du PO |
| `WORKSPACE_ROOT` | `workspace_v2/` | racine des espaces de travail |
| `AGENT_TIMEOUT_S` | `1800` | durée maximale d'une session d'agent (s) |
| `QA_MAX_ATTEMPTS`, `DEV_MAX_ATTEMPTS` | `2`, `3` | tentatives par story |
| `CALL_BUDGET_USD`, `PROJECT_BUDGET_USD` | `5`, `30` | plafonds de coût estimé par appel et par projet |
| `SUITE_TIMEOUT_S`, `SMOKE_TIMEOUT_S` | `600`, `60` | durées maximales de la suite et du smoke (s) |
| `FAKE_AGENTS` | `0` | agents scriptés (tests) |

### Tests

```bash
python -m pytest tests_v2 -q -p no:cacheprovider       # noyau v2 (quelques minutes : vrais uv et git)
python -m pytest bench/tests -q -p no:cacheprovider    # banc
cd ../frontend_v2 && npm test                           # interface v2
```

La suite v1 (`backend/tests`, environ 20 min) n'est plus maintenue : ne pas la lancer.

## Banc de mesure

Rien n'entre dans le noyau sans mesure. Le banc (`backend/bench`) joue cinq briefs à interface
publique fixée et juge chaque produit avec un oracle caché, en boîte noire, hors de son dépôt :
B1 slugify (lib), B2 todo (cli), B3 notes (api), B4 compteur (fullstack), B5 Relais Support
(fullstack, tiré de [01_specification.md](docs/validation/support-client/01_specification.md)).
Trois configurations : `a` (v1), `b` (harness nu : une seule session Claude Code confinée), `c` (v2).

```bash
python -m bench.briefs                          # vérifie les briefs et leurs empreintes
python -m bench.run --config c --project B1     # un run, jugé par l'oracle
python -m bench.report                          # régénère docs/bench/README.md
```

Résultats (modèle `sonnet`, novembre 2026 ; tableau complet : [docs/bench/README.md](docs/bench/README.md),
lecture : [docs/REFONTE_V2.md](docs/REFONTE_V2.md) section 11) :

| Projet | b : harness nu | c : v2 (taille adaptative) |
|---|---|---|
| B1 slugify | 0,5 min, 0,04 $, oracle 12/12 | 1,4 min, 0,18 $, oracle 12/12 |
| B2 todo | 1,0 min, 0,08 $, oracle 10/10 | 2,5 min, 0,26 $, oracle 10/10 |
| B3 notes | 0,8 min, 0,08 $, oracle 15/15 | 2,9 min, 0,26 $, oracle 15/15 |
| B4 compteur | 1,8 min, 0,11 $, oracle 8/8 | 8,2 min, 0,32 $, oracle 8/8 |
| B5 Relais Support | 16 min, 2,29 $, 33 des 35 critères automatisés | non terminé (smoke en échec, 2 interventions humaines) : 20 stories, suite 241/241, environ 11,3 $, 23 des 35 critères automatisés |

- La v1 (configuration `a`) ne démarre plus sans moteur Docker Linux.
- De B1 à B4, les deux configurations livrent un produit parfait à l'oracle ; la v2 est 2,5 à 5
  fois plus lente et plus chère, le prix de la QA indépendante et de la vérification en
  environnement propre.
- Sur B5, le harness nu fait mieux. Le run v2 n'a pas abouti : garé par une panne DNS puis repris
  (2 interventions humaines), il a construit ses 20 stories mais son smoke a échoué (il sondait
  `/health` alors que le brief fixe `/api/health`) et le projet a fini en `needs_attention`. Ses
  stories, construites par des sessions séparées, ont aussi divergé (l'assignation d'un ticket
  est refusée).
- Ce que la v2 apporte de démontré est la confiance : tests d'acceptance écrits avant et
  intouchables, preuve rejouée en environnement propre, reprise après panne.

## Arborescence

```
backend/
  autospec/core/   noyau v2 : pipeline, machine à états, agent, vérification, profils, prompts, plan, API
  bench/           banc : briefs B1 à B5, oracles cachés, run, report
  tests_v2/        tests du noyau (agents scriptés et faux CLI claude)
frontend_v2/       interface web v2 (React, Vite, TypeScript)
docs/              plan, état, contrats, résultats du banc, brief et référentiel de B5, archives
```

Le noyau v2 n'importe aucun module v1. **Héritage v1 encore présent, gelé et non maintenu** :
`backend/autospec/orchestrator`, `agents`, `api`, `validation`, `skills`, `config.py`,
`models.py`, `storage.py` et voisins, `backend/tests`, `backend/scripts`, `backend/README.md`,
`frontend/`. Il sera retiré en phase 5 ; la v1 complète reste sur le tag `v1-ref` et la branche
`v1-archive`.

## Documentation

- [docs/REFONTE_V2.md](docs/REFONTE_V2.md) : diagnostic, principes, périmètre, banc, décisions et résultats.
- [docs/STATE.md](docs/STATE.md) : état courant et journal des sessions.
- [docs/v2/CONTRACTS.md](docs/v2/CONTRACTS.md) : contrats des modules du noyau, de l'API et de l'interface.
- [docs/bench/README.md](docs/bench/README.md) : tous les runs du banc.
- [docs/archive/README.md](docs/archive/README.md) : index des documents v1 archivés.
