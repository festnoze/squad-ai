# Backlog spécial — `handle_project_def_and_create`

> **But.** Après l'analyse PO, insérer une capacité de **définition de solution**
> puis de **création & vérification des projets** *avant* toute injection de
> feature — pour qu'un produit livré **démarre réellement** au lieu d'être une
> collection d'unités vertes non reliées (le syndrome `messagerie2` : 19 US
> vertes, aucun serveur, aucune API).
>
> Règle de délégation identique au [BACKLOG.md](BACKLOG.md) : US de complexité
> faible/moyenne → subagents ; orchestration/conception → modèle courant.
> Tout derrière le flag **`PROJECT_DEF`** (OFF = comportement actuel inchangé).

---

## 1. Pourquoi (cause racine, au niveau du code)

Le produit ne démarre pas alors que toutes les US sont vertes parce que la
chaîne de scaffolding est **structurellement cassée en deux moitiés qui
s'ignorent**, et qu'aucune porte ne vérifie que le squelette **démarre** avant
d'y injecter des features :

| Fait constaté (code) | Fichier | Conséquence |
|---|---|---|
| `workspace.scaffold()` s'exécute **toujours** et écrit un `main.py` qui auto-découvre `features/*.py` via `register()` **puis sort** (jamais de serveur). | [orchestrator/workspace.py:47-70](backend/autospec/orchestrator/workspace.py#L47-L70) | Le point d'entrée n'est jamais un serveur ; les hooks `register()` sont appelés à l'import puis le process s'arrête (`exit 0`). |
| `setup_exec` (E4) crée un `backend/app/main.py` FastAPI **avec une route `/api/health` déjà présente**, dans un dossier **parallèle et séparé**. | [orchestrator/setup_exec.py:33-43](backend/autospec/orchestrator/setup_exec.py#L33-L43) | Deux scaffolders qui ne se connaissent pas : le serveur FastAPI de `backend/app/` n'importe **jamais** les features que le Dev écrit dans `<pkg>/features/`. |
| Le Dev câble ses features via la convention plugin `register()` — mais le template interdit d'éditer `main.py` (« conflits de merge inter-stream »). | [workspace.py:47-70](backend/autospec/orchestrator/workspace.py#L47-L70) | Personne ne fait jamais « évoluer le point d'entrée en serveur web ». Le registre de plugins n'a aucun consommateur. |
| E3/E4 (`components_proposal`/`setup_exec`) sont **gated `COMPONENTS`**, actifs seulement pour le profil `fullstack`. | [orchestrator/profiles.py:89-102](backend/autospec/orchestrator/profiles.py#L89-L102) | Hors `fullstack`, aucun serveur n'est même tenté. Et quand il l'est, il n'est **pas relié** au reste. |
| Le seul garde d'exécution (`smoke_run`) tourne **à la fin**, après livraison. | `_asmoke_phase` dans [pipeline.py](backend/autospec/orchestrator/pipeline.py) | On découvre trop tard, à la livraison, que rien ne démarre — et le gate se laissait piéger en classant l'app « CLI » (corrigé récemment via `_expects_web_app`). |

**Diagnostic.** Les briques existent déjà mais sont **fragmentées** entre
`workspace.scaffold` (toujours), `setup_exec`/E4 (gated `COMPONENTS`),
`language_selector`/L2 (gated `LANGUAGE_SELECTOR`) et `select_streams`/ST-4
(gated `STREAMS`), chacune derrière un flag différent, aucune ne produisant un
squelette **relié et prouvé-démarrable**. Ce backlog les **unifie** en une phase
cohérente et ajoute la pièce manquante : **la vérification de boot à la
naissance**, avant les features.

---

## 2. Cible — trois phases enchaînées

```
… PM (brief) → PO (US/épics) →  ┌─────────────────────────────────────────┐
                                │ A. DÉFINITION DE SOLUTION  (1 agent)      │  ← nouveau (subsume E3+L2+ST-4)
                                │    nature & complexité → projets → stacks │
                                └─────────────────────────────────────────┘
                                ┌─────────────────────────────────────────┐
                                │ B. CRÉATION DES PROJETS  (Tech Stories)  │  ← nouveau (généralise E4)
                                │    scaffold depuis template + deps de base│
                                │    + sonde health + câblage du registre   │
                                └─────────────────────────────────────────┘
                                ┌─────────────────────────────────────────┐
                                │ C. VÉRIFICATION DE BOOT  (gate)          │  ← nouveau (smoke « à la naissance »)
                                │    lance chaque projet, prouve qu'il tourne│
                                └─────────────────────────────────────────┘
… → PLAN features → BUILD features (US) → smoke → DoD → … (inchangé)
```

### A. Définition de solution — 1 agent, post-PO
L'agent (persona **architecte**, étendu) reçoit le brief + le squelette d'US et
produit un **`SolutionBlueprint`** structuré :
- **nature & complexité** de l'app (2 axes déjà présents en L2 : complexité,
  criticité) → réutilisés ;
- **liste de projets** (ex. `frontend` React, `backend` Python, `db` PostgreSQL)
  — un projet = une zone de fichiers + un toolchain + un runtime ;
- **pour chaque projet** : `language`, `framework`/stack, **deps de base**,
  **template** (cookiecutter ref si dispo), `needs_db`/`db_kind`, **sonde de
  santé** attendue (`health_probe`), `run_command`, `test_command`.

**Fondamentaux communs, opinionés mais surchargeables** (le cœur de la demande
utilisateur) :
- API **Python** → **template cookiecutter** + **uv** + **FastAPI** systématiques ;
  si BDD → **SQLAlchemy** ; sonde `GET /api/health` par défaut.
- Frontend web → **Vite + React + TS + Vitest** (aligné sur le scaffold ST-6).
- BDD → **PostgreSQL** par défaut (surchargeable en NoSQL).
- **Mais l'agent peut choisir autrement** si plus adapté (ex. **Rust + base
  NoSQL** pour un composant système/critique) — les défauts sont un point de
  départ, pas une prison. Heuristique déterministe de secours si l'agent échoue
  (comme L2 `recommend_language`).

### B. Création des projets — portée par des **Tech Stories (TS)**
Work-item **Tech Story (TS)**, frère de l'US, regroupé dans un **« Épic 0 —
Fondations »**. **Bonne nouvelle : le modèle existe déjà** — `UserStory.technical`
([models.py:320](backend/autospec/models.py#L320)) marque justement les
« conteneurs non-fonctionnels ». On modélise donc une TS comme une
`UserStory(technical=True)` (surfacée « TS » dans l'UI) plutôt qu'un tout nouveau
type — moindre effort, réutilise toute la plomberie US/Task/board. Le blueprint
génère **une TS par projet** (voire par préoccupation de setup). Chaque TS,
exécutée dans la **phase de création avant le plan de features** :
1. scaffold depuis le template/stack choisi (généralise `setup_exec.execute`) ;
2. installe les **deps de base** (`uv sync` / `npm ci`, derrière `SETUP_INSTALL`) ;
3. **câble la convention de features dans le serveur** — le point d'entrée
   **devient** un serveur qui **monte** le registre `features/*.py` (fin de la
   déconnexion : une feature ajoutée plus tard est **réellement servie**) ;
4. ajoute une **sonde de santé par défaut** (`GET /api/health` pour une API,
   route `/` pour un front, `--version`/`exit 0` pour une CLI).

Les TS sont de **vrais work-items** : statut, tentatives, diff, relance,
affichage board — elles réutilisent toute la plomberie de `Task` (ST-2/ST-13).

### C. Vérification de boot — gate à la naissance
Après création, **avant** d'injecter la moindre feature : lancer chaque projet
et **prouver qu'il tourne** (API → `GET /api/health` == 200 ; front → build +
serve ; CLI → `exit 0`). Réutilise la plomberie `_smoke_run_python` /
`_expects_web_app` déjà durcie, mais **tôt**, sur le squelette. Rouge ici →
on répare le squelette (retry TS), on **n'injecte pas** de features sur un socle
mort. C'est le « canari de naissance » symétrique du canari post-merge.

---

## 3. Réconciliation avec l'existant (ne rien dupliquer)

| Existant | Ce qu'on en fait |
|---|---|
| **E3 `components_proposal`** ([prompts.py:815](backend/autospec/agents/prompts.py#L815)) | **Absorbé** dans l'agent de Définition : le `SolutionBlueprint` est le sur-ensemble de `components`. On conserve le modèle `Component` comme projection/compat. |
| **E4 `setup_exec`** ([setup_exec.py](backend/autospec/orchestrator/setup_exec.py)) | **Généralisé** en exécuteur de TS piloté par le blueprint (templates paramétrés au lieu de constantes en dur ; ajoute le câblage registre→serveur + la sonde). |
| **L2 `language_selector`** | Ses 2 scores (complexité/criticité) + `recommend_language` deviennent des **entrées** de la Définition (par projet, plus seulement backend global). |
| **ST-4 `select_streams`** | Les streams **dérivent** désormais des projets du blueprint (un projet = au moins un stream) au lieu d'être choisis séparément. |
| **`workspace.scaffold`** | Le `main.py` naïf qui sort est **remplacé** (pour un projet API) par un point d'entrée serveur qui monte le registre — fin de la double-moitié. Chemin flag-OFF **byte-identique**. |
| **`_asmoke_phase` / `_expects_web_app`** | Réutilisés par la phase C (boot à la naissance), en plus du smoke de fin. |

---

## 4. Découpage en US (ordonné ; dépendances indiquées)

> Préfixe `PDC-*` (Project Definition & Create). Chaque US doit livrer son
> support `ScriptedRunner` (démo/tests) et laisser la suite existante verte
> avec `PROJECT_DEF=0`.

### Lot 1 — Modèle & flag (fondations, aucun changement de comportement)
| # | US | Livrable concret | Dép. |
|---|-----|------------------|------|
| PDC-1 | **Modèle `SolutionBlueprint` + `Project`** | `Project{id, kind(backend/frontend/db/cache/worker), language, framework, base_deps[], template, needs_db, db_kind, health_probe, run_command, test_command, file_root}` ; `SolutionBlueprint{projects[], complexity, criticality, rationale}` ; `ProjectState.blueprint`. Migration Pydantic (défaut = None → chemin legacy). `models.py`. | — |
| PDC-2 | **Tech Story (TS) = `UserStory(technical=True)`** | Réutiliser le champ **déjà présent** `UserStory.technical` ([models.py:320](backend/autospec/models.py#L320)) : une TS porte `project_id` (nouveau champ optionnel), `kind(scaffold/wire/deps/health)`, et vit dans l'« Épic 0 — Fondations ». Helper `ProjectState.tech_stories()`. Pas de nouveau type → réutilise US/Task/board tels quels. `models.py`. | PDC-1 |
| PDC-3 | **Flag `project_def_enabled` (`PROJECT_DEF`) + phases enum** | `config.py: project_def_enabled` (OFF, convention `*_enabled`) ; override profil dans [profiles.py:89-102](backend/autospec/orchestrator/profiles.py#L89-L102) (`fullstack`/`api`/`web-ssr` → ON) ; **nouvelles valeurs `PipelinePhase`** `DEFINE`/`CREATE`/`BOOT` ([models.py:12-22](backend/autospec/models.py#L12-L22)) ; garde dans `_alifecycle` (OFF = chemin legacy byte-identique). `config.py`, `profiles.py`, `models.py`, `pipeline.py`. | PDC-1 |

### Lot 2 — Agent de Définition (phase A)
| # | US | Livrable concret | Dép. |
|---|-----|------------------|------|
| PDC-4 | **Prompt `solution_definition` + persona** | `prompts.solution_definition(state)` (architecte étendu) : entrée brief + squelette US + scores L2 → sortie JSON `SolutionBlueprint` ; **défauts opinionés** injectés dans le prompt (Python API ⇒ cookiecutter+uv+FastAPI+SQLAlchemy si BDD ; front ⇒ Vite/React/TS ; BDD ⇒ Postgres) **avec liberté de dévier** (ex. Rust+NoSQL). `prompts.py`, `scripted.py` (`_SOLUTION_DEF`). | PDC-1 |
| PDC-5 | **`_adefine_solution` (phase A) + heuristique de secours** | Insérée dans `_alifecycle` **après `_aspec_phase` (pipeline.py:2010), en remplacement de la séquence `_aselect_language`/`_aselect_streams`/`_apropose_components` (2015-2027)** quand le flag est ON : appelle l'agent, parse/valide le blueprint, **fallback déterministe** si échec (réutilise `language_selector.recommend_language` + règles par mots-clés). Persiste `state.blueprint`, `phase=DEFINE`, `_sync()`. Message système 🧩. `pipeline.py`. | PDC-4, PDC-3 |
| PDC-6 | **Absorption E3 + dérivation des streams** | Le blueprint **génère** `state.components` (projection compat E3) **et** `state.streams` (un projet ⇒ ≥1 stream) au lieu d'appels séparés `_apropose_components`/`_aselect_streams`. `pipeline.py`. | PDC-5 |

### Lot 3 — Création par Tech Stories (phase B) — **le cœur du fix**
| # | US | Livrable concret | Dép. |
|---|-----|------------------|------|
| PDC-7 | **Génération des TS depuis le blueprint** | `_agenerate_tech_stories()` : une TS `scaffold`+`health`+`wire` par projet, dans l'Épic 0, avec `depends_on` (front dépend du backend prêt). `pipeline.py`, `streams.py`. | PDC-2, PDC-5 |
| PDC-8 | **Exécuteur de scaffold paramétré (généralise `setup_exec`)** | Templates **paramétrés par le blueprint** (langage/framework/deps) au lieu des constantes en dur ; support cookiecutter (`settings.cookiecutter_*`) quand un `template` est référencé ; idempotent. `setup_exec.py`. | PDC-7 |
| PDC-9 | **Point d'entrée = serveur qui monte le registre de features** | Pour un projet API : remplacer le `main.py`-qui-sort par un point d'entrée **serveur** (`uvicorn`) qui **importe et monte** `features/*.py` (chaque feature expose un `APIRouter` via `register(app)`) → une feature développée ensuite est **réellement servie**. Aligne les deux moitiés (`workspace.scaffold` ↔ `setup_exec`). `workspace.py`, `setup_exec.py`. | PDC-8 |
| PDC-10 | **Sonde de santé par défaut, par type de projet** | API ⇒ `GET /api/health`→200 ; front ⇒ route `/` rendue ; CLI ⇒ `--version`/`exit 0` ; posée par la TS `health`. `setup_exec.py`, templates. | PDC-8 |
| PDC-11 | **Phase de création dans le lifecycle** | `_acreation_phase()` (`phase=CREATE`, `_sync()`) construit les TS via l'ordonnanceur/worktree existant (ST-9 `_abuild_phase_streams`) ; **insérée avant le `_aplan_phase` des features (pipeline.py:2033)** et remplace le `workspace.scaffold` naïf (2022) quand ON ; installs derrière `SETUP_INSTALL`. `pipeline.py`. | PDC-7, PDC-9 |

### Lot 4 — Vérification de boot (phase C)
| # | US | Livrable concret | Dép. |
|---|-----|------------------|------|
| PDC-12 | **Gate de boot à la naissance** | `_averify_projects_boot()` : lance chaque projet, prouve la sonde (API `GET /api/health`==200 via `httpx` ; front build+serve ; CLI exit 0). Réutilise `_smoke_run_python`/`_expects_web_app`. Rouge → bloque l'injection de features. `pipeline.py`. | PDC-10, PDC-11 |
| PDC-13 | **Réparation ciblée du squelette** | Rouge au boot → relance la TS fautive (budget dédié type `infra_max_retries`, ne débite pas le budget dev — cohérent avec [GENERATION_FUSION_REVIEW.md](GENERATION_FUSION_REVIEW.md) P0-B) ; message 🔧. `pipeline.py`. | PDC-12 |

### Lot 5 — UI, compat, tests
| # | US | Livrable concret | Dép. |
|---|-----|------------------|------|
| PDC-14 | **Board : Épic 0 Fondations + TS + boot** | Rendu des TS (badge « TS ») sous l'Épic 0, statut de la sonde de santé (🟢 démarre / 🔴 ne démarre pas), détail/relance par TS (réutilise `TaskDetail`/`TaskDiffViewer` ST-13). `Board.tsx`, `work.ts`, `api.ts`. | PDC-2 |
| PDC-15 | **Panneau « Solution » (édition du blueprint)** | Afficher/éditer les projets + stacks + deps avant validation (comme le panneau Composants E3, qu'il remplace) ; `PUT /api/projects/{id}/blueprint`. `server.py`, front. | PDC-5 |
| PDC-16 | **Rétro-compat & flag** | `PROJECT_DEF=0` → chemin actuel byte-identique (E3/E4/L2/ST-4 tels quels) ; `=1` → phases A/B/C. Toute la suite existante verte. `config.py`, gardes `pipeline.py`. | PDC-1…PDC-13 |
| PDC-17 | **Tests & démo e2e** | Unitaires : parsing blueprint, génération TS + deps, câblage registre→serveur, gate de boot (API health, front serve, CLI). Intégration : un projet API scaffoldé **démarre** et sert une feature ajoutée. Démo navigateur : définition → création → boot vert → features. `tests/`, `e2e`. | PDC-1…PDC-16 |

---

## 5. Lots de livraison conseillés (une tranche à la fois)
- **Lot 1** (PDC-1/2/3) — modèle + flag, zéro changement de comportement.
- **Lot 2** (PDC-4/5/6) — l'agent produit un blueprint et alimente
  components/streams (remplace 3 agents épars par 1).
- **Lot 3** (PDC-7…11) — **le fix de fond** : création par TS + point d'entrée
  serveur relié au registre de features (tue le syndrome messagerie2).
- **Lot 4** (PDC-12/13) — prouver le boot avant les features.
- **Lot 5** (PDC-14…17) — UI, compat, e2e.

> Lots 2 & 3 parallélisables par 2 agents dans des worktrees isolés (comme
> ST-lot2/lot3), mergés dans une branche d'intégration `project-def`.

---

## 6. Definition of Done du chantier
1. Avec `PROJECT_DEF=1`, un brief « API + front » produit un squelette qui
   **démarre** (`GET /api/health`==200) **avant** toute feature, et une feature
   ajoutée est **servie** sans édition manuelle du point d'entrée.
2. Le gate de boot **échoue** l'itération si le squelette ne démarre pas
   (symétrique du smoke de fin), avec réparation ciblée qui ne débite pas le
   budget dev.
3. `PROJECT_DEF=0` → suite existante **verte inchangée** (E3/E4/L2/ST-4 intacts).
4. Rejeu du cas `messagerie2` : le produit **tourne** en fin d'itération 1, sans
   feedback manuel « ajoute FastAPI/endpoints ».

---

*Contexte : ce backlog répond au constat que l'usine crée 29 US puis exige
quand même un feedback manuel pour câbler API/serveur. Voir
[WORKFLOW_REVIEW.md](WORKFLOW_REVIEW.md) et
[GENERATION_FUSION_REVIEW.md](GENERATION_FUSION_REVIEW.md) pour l'analyse amont.*
