# Autospec — Fonctionnalités développées

Application **deux-en-un** : backend Python **FastAPI** + frontend **React / Vite /
TypeScript**, gérée par **uv**, lançable via `.vscode` (compound *Full Stack —
Backend + Frontend*). Située dans `C:\Dev\squad-ai\Brainstorming\Autospec`.

Autospec est une **usine à features pilotée par des agents BMAD** : depuis l'UI,
l'utilisateur décrit un projet ou une feature ; un pipeline d'agents le
transforme en **code testé** (BDD puis TDD), de façon itérative et autonome.

> Voir aussi : [`README.md`](./README.md) (démarrage), [`how_it_works.md`](./how_it_works.md)
> (doc technique détaillée), [`BACKLOG.md`](./BACKLOG.md) (journal des items).

---

## 1. Pipeline d'agents (cœur)

Tous les agents sont exécutés via le **CLI Claude Code en mode headless**
(`claude -p --output-format json`), derrière l'abstraction **`AgentRunner`** —
3 implémentations : `ClaudeCliRunner` (production), `FakeRunner` (tests
unitaires), `ScriptedRunner` (mode démo). Les personas proviennent de
l'installation **BMAD** (`_bmad/bmm/agents/`), augmentées d'un override « mode
programmatique » qui neutralise les menus interactifs et impose **une seule
réponse JSON**.

| Agent | Persona BMAD | Rôle |
|---|---|---|
| **PM** | `pm` | Interviewe l'utilisateur dans le chat puis rédige un **brief produit**. Bouton **Auto-spec** : le PM décide seul, sans poser de question. |
| **Architecte** | `architect` | (Optionnel) Produit un **design technique** injecté dans les prompts QA/Dev. |
| **PO** | `sm` | Découpe le brief en **EPICs** et **user stories** : description, critères d'acceptance, **Gherkin**, dépendances (`depends_on`), **priorité kanban** (1-5). |
| **QA** | `qa` | Décompose le test d'acceptance **outside-in (London school)** en tests unitaires par couche (API → façade → service → repo/LLM), chacun mockant ses collaborateurs directs, rattachés aux critères. |
| **Dev** | `dev` | Un agent par story, en **BDD puis TDD** avec `pytest-bdd`. |
| **Analyste** | `analyst` | (Auto-spec) Explore le produit, formule des **hypothèses de features** scorées (valeur/complexité), les priorise, choisit la suivante. |
| **Critic / Juge** | (génériques) | Harnais de raffinement (§3). |

**Cycle de vie** : `spec (PM)` → `[architect]` → `plan (PO)` → `build (QA + Dev)`
→ `done`. En **Auto-spec**, après chaque itération livrée : `analyze (Analyste)`
→ nouveau brief → cycle suivant, **indéfiniment** jusqu'à l'arrêt manuel.

### Construction d'une story (BDD/TDD outside-in)

Chaque story est construite dans un **workspace uv autonome**
(`workspace/<id>/` : `pyproject.toml`, `features/*.feature`, `tests/steps/`,
package, `main.py`) :

1. QA produit le plan de tests outside-in (à la 1re tentative).
2. Dev écrit les **step definitions** pytest-bdd + **tous les tests unitaires du
   plan** (mocks compris) → **vérifie le rouge** → implémente couche par couche
   du haut vers le bas → **suite verte**.
3. L'orchestrateur **revérifie lui-même** (`uv run pytest`) avant de marquer la
   story *done* (« trust but verify ») ; sinon retry (`AUTOSPEC_DEV_MAX_ATTEMPTS`)
   puis échec.

### Ordonnancement (scheduler)

- Dépendances validées : détection et **cassage défensif des cycles**, purge des
  références inconnues (jamais de deadlock).
- Stories **indépendantes** développées **en parallèle** (sémaphore
  `AUTOSPEC_MAX_PARALLEL_DEVS`), par ordre de **priorité kanban**.
- Les stories dont une dépendance échoue sont marquées *failed* avec message.

---

## 2. Phase Architecture (optionnelle)

Entre PO et build, l'agent **`architect`** produit un design technique concis
(couches/modules, composants clés, conventions, contraintes transverses), stocké
dans `ProjectState.architecture` et **injecté dans les prompts QA et Dev**.
Activable par `AUTOSPEC_ARCHITECTURE`, **OFF par défaut**.

---

## 3. Harnais de raffinement (maker → critic → judge)

Boucle générique (`orchestrator/refine.py`, `arefine()`) pour améliorer un
artefact :

- un **maker** produit (plan PO ou code Dev) ;
- un **critic** raisonne en **ReAct (REFLECT puis ACT)** et propose des
  améliorations **actionnables** sans réécrire ;
- un **juge** note la qualité de **0 à 100**.

**Arrêt déterministe par deux moyens** : le **score atteint le seuil**
(`AUTOSPEC_REFINE_QUALITY_THRESHOLD`, déf. 80) **ou** le **cap d'allers-retours**
est atteint (`AUTOSPEC_REFINE_MAX_ROUNDS`, déf. 2) — selon ce qui survient en
premier. Arrêts additionnels : critique vide (`critic_empty`), révision rejetée
(`rejected`), juge illisible (traité comme arrêt).

- **PO** : raffinement du plan (critères INVEST/Gherkin/découpage).
- **Dev** : raffinement du code protégé par une **garde git** — une révision
  n'est gardée que si `uv run pytest` reste vert (sinon `git reset --hard` +
  `git clean -fd`).

**OFF par défaut** (`AUTOSPEC_REFINE`, `_PO`, `_DEV`). Rôles de chat **🧐 Critic**
et **⚖️ Juge** ; scores exposés à l'UI (`plan_quality`, `quality_score`).

---

## 4. Vérifiabilité & exécution

- **États de tests RÉELS depuis pytest** : `_arun_pytest` lance pytest avec
  **`pytest-json-report`** et renvoie `(suite_verte, sortie, {nodeid: outcome})`.
  L'état par test (inexistant/rouge/vert) est fondé sur l'**exécution réelle**,
  mappé aux tests planifiés via les **nodeids déclarés** par le Dev.
- **Mode démo** (`AUTOSPEC_FAKE_AGENTS=1`) : le `ScriptedRunner` déterministe
  pilote **tout le stack sans CLI Claude ni build de venv uv** ; base du test
  e2e hermétique.
- **Lancement de l'app générée** : bouton **▶ Lancer le projet** (exécute
  `main.py`, logs streamés en WebSocket) ; bouton **■ Arrêter l'app**
  (`stop-app`, termine le sous-processus).
- **Spécificité Windows** : les sous-processus (pytest, git, app) tournent dans
  des **threads worker** (le `SelectorEventLoop` d'uvicorn ne supporte pas les
  sous-processus asyncio).

---

## 5. Gestion des projets & interaction depuis le front

### Multi-projets
- **Sélection**, **suppression** (efface le workspace, gère les fichiers `.git`
  en lecture seule), **archivage** non destructif (masquage par défaut, bascule
  **« Archivés (N) »**, désarchivage).
- **Reprise après redémarrage** : `recover_projects()` (lifespan) réenregistre
  les projets persistés en **pipelines dormantes** et récupère un état
  interrompu (phase active→`stopped`, stories `in_progress`→`todo`).

### Édition des specs
- Éditer **titre / description / critères / Gherkin / priorité** d'une US ;
  **ajouter** / **supprimer** une US ; **drag-&-drop** pour reprioriser le board
  (tri par priorité + poignée → endpoint `reorder`).

### Actions par story
- **🔄 Relancer** (story échouée), **🔁 Rejouer** (story terminée), **✓ Forcer
  terminé** — avec **garde de concurrence** (409 si pipeline active ou story
  `in_progress`).
- **▶ Continuer le build** d'un projet dormant (reprend la phase build sur les
  stories `todo`/`red`).

### Interruption
- **⏸ Pause / ▶ Reprendre** (gate coopératif `_checkpoint` entre étapes/lots),
  **⏹ Stopper** (débloque aussi une pause/interview).

### Chat (interaction)
- Phase **spec** → réponses au PM.
- Phase **build/architect** → le message devient une **guidance** injectée à la
  prochaine tentative du Dev (`build_guidance`).
- Sinon → **feedback** repris par l'analyste au cycle suivant.

### Visualisation (board & panneaux)
- **Board** EPIC/US : statut coloré (todo/dev/rouge/vert/done/échec), badges
  **priorité `P1-P5`** et **qualité `⚙ N/100`**, **critères d'acceptance
  dépliables** (état inexistant/rouge/vert — vert si **tous** leurs tests sont
  verts) affichant la liste des tests + le Gherkin.
- **Backlog de l'analyste** (rang, valeur/complexité, statut).
- **Architecture & qualité** (design technique courant + score du plan).
- **Indicateur d'usage 💸** (coût $ / tokens / nombre d'appels agents).
- **Explorateur de code 📁** (arborescence + contenu du workspace, **anti
  path-traversal**).
- **Vue diff par story 📊** (`git show` du commit « story done », coloration
  +/-).
- Temps réel via **WebSocket** (`state` / `log` / `deleted`, reconnexion auto).

---

## 6. Robustesse & observabilité

- **Persistance résiliente** : `storage` **migre** les anciens formats (ex.
  critères `str` → objets) et **ignore** proprement les fichiers corrompus (la
  liste ne plante jamais).
- **Observabilité tokens/coût** : `AgentResult` porte cost/tokens/durée parsés du
  JSON du CLI ; un wrapper **`_UsageTracker`** accumule dans `ProjectState.usage`.
- **Configuration** : chargement **`.env`** (python-dotenv) + variables
  `AUTOSPEC_*` (fichier `.env.example` documenté).

### Principales variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `AUTOSPEC_CLAUDE_CMD` | auto (`claude.cmd`) | binaire Claude Code |
| `AUTOSPEC_CLAUDE_MODEL` | (défaut CLI) | modèle imposé aux agents |
| `AUTOSPEC_PERMISSION_MODE` | `bypassPermissions` | mode permissions des agents |
| `AUTOSPEC_MAX_PARALLEL_DEVS` | `2` | agents Dev en parallèle |
| `AUTOSPEC_DEV_MAX_ATTEMPTS` | `2` | tentatives par story |
| `AUTOSPEC_WORKSPACE_ROOT` | `./workspace` | racine des workspaces générés |
| `AUTOSPEC_FAKE_AGENTS` | `0` | mode démo (agents scriptés) |
| `AUTOSPEC_DEMO_DELAY_S` | `0` | délai des agents scriptés |
| `AUTOSPEC_ARCHITECTURE` | `0` | active la phase Architecture |
| `AUTOSPEC_REFINE` / `_PO` / `_DEV` | `0` / `1` / `1` | harnais de raffinement |
| `AUTOSPEC_REFINE_MAX_ROUNDS` | `2` | cap d'allers-retours |
| `AUTOSPEC_REFINE_QUALITY_THRESHOLD` | `80` | seuil de score du juge |

---

## 7. API (FastAPI + WebSocket)

**Projets** : `POST /api/projects`, `GET /api/projects`, `GET|DELETE
/api/projects/{id}`, `/chat`, `/stop`, `/pause`, `/resume`, `/run`, `/stop-app`,
`/resume-build`, `/archive`, `/unarchive`, `/files`, `/files/raw?path=`.

**Stories** : `PATCH /…/stories/{sid}`, `POST /…/stories`, `DELETE
/…/stories/{sid}`, `/…/stories/reorder`, `/…/stories/{sid}/rebuild`,
`/…/stories/{sid}/force-done`, `/…/stories/{sid}/diff`.

**Temps réel** : WebSocket `/ws`. Le backend **sert aussi le frontend buildé**
(`frontend/dist`) en same-origin.

Gardes : `404` (inconnu), `409` (action interdite : pipeline active, story
`in_progress`…), `422` (validation), `400` (path-traversal).

---

## 8. Qualité, tests & CI

- **Backend — 82 tests pytest** : `test_scheduler`, `test_runner`, `test_models`,
  `test_pipeline` (interview, dépendances, auto-spec, kanban, plan QA, états
  réels, pause/reprise, rebuild/force-done, resume-build, guidance, architecture,
  usage, diff git…), `test_refine` (déterminisme du harnais), `test_scripted`,
  `test_pytest_report`, `test_api`.
- **Frontend — 7 tests Vitest** : logique pure `criterionState`, rendu `Board`.
- **e2e — 1 test Playwright** hermétique (backend mode démo servant la SPA
  buildée, same-origin) : création → board peuplé → pause/reprise → critère
  (vert + tests + Gherkin) → suppression.
- **CI GitHub Actions** : workflow auto-contenu `Autospec/.github/workflows/ci.yml`
  + workflow racine monorepo `squad-ai/.github/workflows/autospec-ci.yml` (filtre
  `paths: Brainstorming/Autospec/**`) — 3 jobs : **backend** (pytest),
  **frontend** (build + vitest), **e2e** (Playwright).

---

## 9. Architecture du code

```
Autospec/
├── .vscode/launch.json          # compound "Full Stack (Backend + Frontend)"
├── backend/                     # FastAPI + orchestrateur (uv)
│   └── autospec/
│       ├── config.py            # Settings + chargement .env
│       ├── models.py            # ProjectState, Epic, UserStory, PlannedTest, Usage…
│       ├── storage.py           # persistance JSON + migration
│       ├── agents/              # personas, prompts, runner (CLI/Fake/Scripted)
│       ├── orchestrator/        # pipeline, scheduler, workspace, refine,
│       │                        # pytest_report, events (WebSocket)
│       └── api/server.py        # REST + WS + service SPA
├── frontend/src/                # App, api, types, components/ (Board, ProjectBar,
│                                # RunPanel, ChatPanel, CodeViewer, …), e2e/
└── workspace/<id>/              # CODE GÉNÉRÉ (projet uv autonome + repo git)
```

**État** : 8 features initiales + 16 items de backlog livrés et vérifiés ; les
3 suites de tests (82 backend, 7 frontend, 1 e2e) sont vertes.
