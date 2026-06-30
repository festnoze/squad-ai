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

Les agents sont exécutés derrière l'abstraction **`AgentRunner`** :
`ClaudeCliRunner` (production, CLI Claude Code headless
`claude -p --output-format json`), `CodexCliRunner` (`codex exec`), et les
providers **hors abonnement** via **LangChain** — **`OpenAiRunner`**,
**`OpenRouterRunner`** (hub compatible-OpenAI), **`OllamaRunner`**,
**`AnthropicRunner`** (sessions rejouées en mémoire + protocole d'outils JSON
borné pour les écritures fichiers, confiné au workspace) — plus `FakeRunner`
(tests) et `ScriptedRunner` (mode démo). Sélection par `AUTOSPEC_AGENT_PROVIDER`
ou à chaud via `GET/POST /api/provider` (sélecteur 🤖 du header). Le 2ᵉ menu
**modèle** est **adaptatif et découvert à la volée** (`GET /api/providers/{p}/models`) :
Ollama/OpenAI interrogent leur endpoint, **OpenRouter charge les 10 modèles de
programmation les plus populaires** (`/models?category=programming`), avec repli
sur une liste statique. Les personas proviennent de l'installation **BMAD**
(`_bmad/bmm/agents/`), augmentées d'un override « mode programmatique » qui
neutralise les menus interactifs et impose **une seule réponse JSON**.
`GET /api/provider` expose aussi les **capacités du runner**
(`RunnerCapabilities`) : les runners CLI Claude/Codex peuvent modifier les
fichiers **et lancer le shell** dans le workspace, tandis que les providers
LangChain utilisent un protocole borné de lecture/écriture de fichiers ; les
tests, smoke runs et gates restent toujours pilotés par Autospec.

| Agent | Persona BMAD | Rôle |
|---|---|---|
| **PM** | `pm` | Mène la **phase spec** en mode *interview* (facilitation socratique) puis rédige un **brief produit**. Bouton **Auto-spec** : le PM décide seul, sans poser de question. |
| **Architecte** | `architect` | (Optionnel) Produit un **design technique** injecté dans les prompts QA/Dev. |
| **PO** | `sm` | Découpe le brief en **EPICs** et **user stories** : description, critères d'acceptance, **Gherkin**, dépendances (`depends_on`), **priorité kanban** (1-5). |
| **QA** | `qa` | Décompose le test d'acceptance **outside-in (London school)** en tests unitaires par couche (API → façade → service → repo/LLM), chacun mockant ses collaborateurs directs, rattachés aux critères. |
| **Dev** | `dev` | Un agent par story, en **BDD puis TDD** avec `pytest-bdd`. |
| **Analyste** | `analyst` | (Auto-spec) Explore le produit, formule des **hypothèses de features** scorées (valeur/complexité), les priorise, choisit la suivante. Analyse aussi l'**impact des feedbacks** (E2). |
| **Solutionneur** | `architect` | (E3, `AUTOSPEC_COMPONENTS`) Propose après le brief les **composants** du produit (backend FastAPI, frontend React, infra optionnelle) — validés/édités par l'utilisateur, matérialisés par l'**exécuteur de setup** (E4). |
| **Tech-writer** | `tech-writer` | (I2) Rédige le **README du projet généré** (présentation, lancement, tests, archi) — auto après build (`AUTOSPEC_TECH_WRITER`) ou bouton 📘. |
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

## 1bis. Phase spec : interview socratique + brainstorming

La phase spec a **deux modes**, pilotés par `ProjectState.spec_mode`
(`"interview"` par défaut, ou `"brainstorm"`). `_aspec_phase` branche selon le
mode : persona **PM** pour l'interview, persona **analyste** (BMAD `analyst`,
« Mary ») pour le brainstorming.

- **Interview (`pm_interview`)** — **facilitation socratique par dimensions** : le
  PM questionne dimension par dimension (problème/pourquoi & job-to-be-done,
  personas, périmètre MVP, hors-périmètre, contraintes, données, vues/UX, cas
  limites, critères de succès), **reformule** et **confronte les non-dits**, puis
  produit le brief.
- **Brainstorming (`pm_brainstorm`)** — l'analyste « Mary » **re-questionne le
  besoin lui-même** : phase **DIVERGER** (élargir l'espace des possibles —
  angles, analogies, inversion du problème, JTBD alternatifs) puis **CONVERGER**
  (choisir/prioriser selon valeur/effort/risque).

Réglage via `POST /api/projects/{id}/spec-mode` (`{mode}`,
`Pipeline.aset_spec_mode`, **422** si invalide). UI : **toggle 💬 Interview /
🧠 Brainstorming** dans le `ChatPanel`, visible en phase `spec`.

---

## 1ter. Budget de coût + arrêt automatique

Un projet porte un **plafond de coût/tokens** : `budget_usd` (en $) et
`budget_tokens`, avec `0` = **illimité**. Réglables à la création
(`POST /api/projects` accepte `budget_usd`/`budget_tokens`) ou après coup
(`POST /api/projects/{id}/budget`).

`Pipeline._enforce_budget()` est appelé à **chaque point de contrôle**
(`_checkpoint` : entre itérations, entre lots de stories, en boucle auto-spec) :
dès que `usage` atteint le budget, la pipeline **s'arrête proprement**
(`_stop_requested`) avec un message « 💰 Budget atteint ». C'est la base pour, à
terme, doser le raffinement/l'architecture **selon le budget**.

UI : champ **« Budget max ($) »** dans `ProjectSetup` ; la jauge d'usage du
`RunPanel` affiche **« 💸 $X / $Y »** et passe en rouge (`.over-budget`) au
plafond.

---

## 1quater. Profils produit

Autospec peut démarrer un projet avec un **profil produit** explicite
(`ProjectState.product_profile`, `AUTOSPEC_PRODUCT_PROFILE`, ou champ
`product_profile` de `POST /api/projects`). Les profils regroupent les flags
qui vont ensemble plutôt que de demander à l'utilisateur de combiner des
variables bas niveau :

- `library-fast` : bibliothèque/module rapide, pas de gate runtime.
- `cli` : produit ligne de commande, tests + smoke CLI.
- `api` : backend/API, architecture + skills + smoke run.
- `web-ssr` : app web rendue serveur, smoke + runtime acceptance + UI evidence.
- `fullstack` : backend + frontend streams, composants, runtime acceptance.
- `brownfield` : extension d'un repo existant, analyse + gates sans restructurer.
- `auto` : comportement historique piloté par les flags.

Le module `orchestrator/profiles.py` normalise les alias (`lib`, `web`,
`full-stack`), rejette les profils inconnus et résout des overrides portés par
chaque `Pipeline` : un projet `fullstack` ne mute plus le singleton global ni les
projets concurrents.

---

## 2. Phase Architecture (optionnelle)

Entre PO et build, l'agent **`architect`** produit un design technique concis
(couches/modules, composants clés, conventions, contraintes transverses), stocké
dans `ProjectState.architecture` et **injecté dans les prompts QA et Dev**.
Activable par `AUTOSPEC_ARCHITECTURE`, **OFF par défaut**.

---

## 2bis. Bibliothèque de skills (SK-1)

Les agents **QA / Dev / BDD** s'appuient sur une **bibliothèque de skills**
réutilisables plutôt que sur des prompts toujours plus gros — meilleure gestion
de la **fenêtre de contexte** (divulgation progressive). Source :
`backend/autospec/skills/` — **9 skills** : `architecture` (archi backend en
**3 couches** façade → application → infrastructure, préfixe async `a`,
enregistrement des composants), `db-entity-change`,
`repo`/`service`/`endpoint-search-or-create`, `error-code-management`,
`test-generator`, `bdd-gherkin`, `skill-creator` — plus `skill-rules.json`
(déclencheurs FR/EN) et un hook `skill-activation.py`.

**Livraison hybride** (`orchestrator/skills.py`) : (a) **natif** — la bibliothèque
est **ensemencée** dans `workspace/<id>/.claude/skills/` pour la découverte native
du CLI Claude (outil Skill) ; (b) **catalogue** — un bloc compact (nom +
description) est injecté dans les prompts QA/Dev **pour tous les providers**.
Les skills de domaine sont maintenant **prescriptives** :
`skill-rules.json` marque leur `enforcement` à `required_when_applicable`, le
catalogue de prompt dit explicitement qu'elles sont **obligatoires quand
applicables**, et `orchestrator/skill_validation.py` signale une livraison
`needs_attention` si `.claude/skills` est absent, incomplet ou si une règle de
domaine est restée en simple suggestion. Réglages : `AUTOSPEC_SKILLS` (global, **OFF**) +
`AUTOSPEC_SKILLS_QA`/`_DEV`. OFF → prompts **strictement inchangés**.

## 2ter. Décomposition en sous-tâches parallèles (SK-2)

`AUTOSPEC_DECOMPOSE` (**OFF par défaut**) découpe une grosse story backend en
**sous-tâches par couche** (entité → service → endpoint → tests) via l'architecte,
matérialisées en `Task`. Chaque sous-tâche est construite par un **sous-agent
focalisé dans son propre worktree git** (contexte minimal = 1 couche + 1 skill)
**en parallèle**, puis **fusionnée** — réutilise le moteur de worktrees des streams ;
la fusion + le rollup de statut **agrègent** les sous-résultats. Non-fatal : < 2
sous-tâches ou erreur → story construite d'un bloc.

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
- **Definition of Done déterministe** : avant de déclarer une itération livrée,
  `orchestrator/delivery_gate.py` vérifie que chaque story/tâche est
  **effectivement** `done`, que les critères ont une preuve Gherkin/test plan,
  et que les stories UI ont des tests rejouables quand `AUTOSPEC_UI_TESTS=1`.
  Le verdict est persisté dans `delivery_ready` / `delivery_issues`, affiché
  dans le `RunPanel`, et place la pipeline en `needs_attention` plutôt qu'en
  `error` quand le produit est incomplet mais l'orchestrateur sain.
- **Smoke run par défaut** : après une suite verte, Autospec démarre réellement
  l'app générée (`AUTOSPEC_SMOKE_RUN=1` par défaut) ; une API/web doit ouvrir son
  port, un CLI doit sortir en code 0. Le profil `library-fast` le désactive.
- **Runtime acceptance web/fullstack** : `orchestrator/runtime_acceptance.py` +
  `backend/scripts/runtime_acceptance.js` lancent le backend et/ou le frontend
  preview, ouvrent un navigateur Playwright, vérifient qu'une page non vide est
  servie et qu'il n'y a pas d'erreur navigateur bloquante. Activé par
  `AUTOSPEC_RUNTIME_ACCEPTANCE` ou les profils `web-ssr`/`fullstack`.
- **Tests UI sans faux vert** : une story `ui=true` doit déclarer au moins un
  `ui_test_files`; `pytest -m ui` avec **aucun test collecté** ne compte plus
  comme succès.
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

### Préservation du travail vert sur conflit de merge
- En build parallèle, si un work item est **vert mais que son merge entre en
  conflit** (un sibling a modifié la même zone), `_amerge_work_item` **rebase la
  branche verte sur le HEAD à jour dans son worktree** puis re-merge → le travail
  est préservé quand les éditions ne se chevauchent pas vraiment. Sur conflit réel,
  `rebase --abort` **restaure la branche verte intacte** et l'item est requeue pour
  un rebuild depuis le HEAD à jour ; le repo reste propre (jamais d'état
  `MERGE_HEAD`/rebasing résiduel). Combiné à la sérialisation par fichiers (P1/P4),
  les conflits sont rares et le green n'est jamais silencieusement perdu.

### Re-décomposition adaptative sur échec
- Quand une **US ou une tâche n'arrive pas à passer au vert** après ses tentatives
  de dev, plutôt que de la marquer en échec, l'agent **architecte la ré-analyse et
  la découpe en sous-tâches plus petites** (`prompts.decompose_finer`), avec des
  **tests plus granulaires** — chacune construite par un sous-agent focalisé. Cible
  le problème de l'**unité trop grosse pour une seule session d'agent**.
- **Automatique** (`_amaybe_split_on_failure`, hook dans la branche « rouge épuisé »
  du worker) : ON par défaut (`AUTOSPEC_SPLIT_ON_FAILURE`), **borné** par
  `split_depth` / `AUTOSPEC_SPLIT_MAX_DEPTH` (jamais de récursion infinie).
- **Manuel** : bouton **✂️ Découper plus fin** sur une story/tâche en échec
  (`POST /api/projects/{id}/items/{item_id}/split`) → force la re-décomposition puis
  reprend le build. **409** si la pipeline est active ou l'unité indivisible.
- **Réécriture des dépendances** : la tâche découpée est remplacée par ses
  sous-tâches ; ses dépendants attendent désormais **toutes** les sous-tâches ; le
  floor d'indépendance (P4) s'applique aux nouvelles tâches.

### Relancer un projet *from scratch*
- Bouton **♻️ Relancer from scratch** (`RunPanel`, visible quand la pipeline est
  dormante et qu'un **brief** existe) : `Pipeline.arestart_from_scratch()`
  **efface tout le dérivé** (code généré, epics, user stories, tâches, streams,
  composants, backlog, leçons, usage…) en **conservant le brief initial** et la
  config du projet, **purge le workspace** (`storage.force_delete_workspace`,
  gère les packs git en lecture seule), puis **relance la pipeline** : la phase
  spec voyant le brief saute l'interview PM et enchaîne **planification PO →
  build global**. Endpoint `POST /api/projects/{id}/restart` ; **409** si la
  pipeline est active ou s'il n'y a aucun brief. Action destructive →
  **confirmation** côté UI.

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
  liste ne plante jamais) ; **écriture d'état atomique** (temp + `rename`).
- **Observabilité tokens/coût** : `AgentResult` porte cost/tokens/durée parsés du
  JSON du CLI ; un wrapper **`_UsageTracker`** accumule dans `ProjectState.usage`.
- **Configuration** : chargement **`.env`** (python-dotenv) + variables
  `AUTOSPEC_*` (fichier `.env.example` documenté) ; `config.py` **tolère les
  variables d'env malformées** (plus de crash à l'import : helpers
  `_env_bool`/`_env_int`, parsing booléen cohérent).

### Durcissements (sécurité & robustesse)

- **Sécurité** : garde **anti path-traversal** dans `storage.workspace_dir` (les
  ids viennent des URLs et alimentent `rmtree` ; rejet de `..`, séparateurs,
  `:`) ; l'**app générée** (non fiable) tourne avec un **env minimal** (pas de
  fuite de secrets) ; **CORS** restreint aux origines locales.
- **Robustesse** : le **runner** gère `result:null`, `is_error`, payload
  non-`dict`, CLI absent (→ `AgentError`) ; `extract_json` ne lève plus jamais
  `JSONDecodeError` ; le **scheduler** ne casse que les dépendances réellement
  cycliques ; **validateurs Pydantic** qui **clampent** les scores 1-5 (un état
  legacy / une sortie LLM hors-bornes ne fait plus échouer le chargement).

### Principales variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `AUTOSPEC_CLAUDE_CMD` | auto (`claude.cmd`) | binaire Claude Code |
| `AUTOSPEC_CLAUDE_MODEL` | (défaut CLI) | modèle imposé aux agents |
| `AUTOSPEC_PERMISSION_MODE` | `bypassPermissions` | mode permissions des agents |
| `AUTOSPEC_MAX_PARALLEL_DEVS` | `2` | agents Dev en parallèle |
| `AUTOSPEC_DEV_MAX_ATTEMPTS` | `2` | tentatives par story |
| `AUTOSPEC_WORKSPACE_ROOT` | `./workspace` | racine des workspaces générés |
| `AUTOSPEC_PRODUCT_PROFILE` | `auto` | profil produit (`library-fast`, `cli`, `api`, `web-ssr`, `fullstack`, `brownfield`) |
| `AUTOSPEC_FAKE_AGENTS` | `0` | mode démo (agents scriptés) |
| `AUTOSPEC_DEMO_DELAY_S` | `0` | délai des agents scriptés |
| `AUTOSPEC_ARCHITECTURE` | `0` | active la phase Architecture |
| `AUTOSPEC_REFINE` / `_PO` / `_DEV` | `0` / `1` / `1` | harnais de raffinement |
| `AUTOSPEC_REFINE_MAX_ROUNDS` | `2` | cap d'allers-retours |
| `AUTOSPEC_REFINE_QUALITY_THRESHOLD` | `80` | seuil de score du juge |
| `AUTOSPEC_AGENT_PROVIDER` | `claude` | provider d'agents (claude / codex / openai / openrouter / ollama / anthropic) |
| `AUTOSPEC_OPENAI_API_KEY` / `_MODEL` / `_BASE_URL` | — | provider OpenAI (LangChain) |
| `AUTOSPEC_OPENAI_PRICE_IN` / `_OUT` | `0` | $/1M tokens (estimation de coût) |
| `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` | — / `…/api/v1` | provider **OpenRouter** (aussi `AUTOSPEC_OPENROUTER_*`) ; modèles = top-10 programmation chargé dynamiquement |
| `AUTOSPEC_OLLAMA_BASE_URL` / `_MODEL` | localhost / `llama3.1` | provider Ollama (LangChain) |
| `AUTOSPEC_PROVIDER_TOOL_ROUNDS` | `8` | cap du protocole d'outils fichiers |
| `AUTOSPEC_SKILLS` / `_QA` / `_DEV` | `0` / `1` / `1` | bibliothèque de skills QA/Dev (SK-1) |
| `AUTOSPEC_DECOMPOSE` | `0` | décomposition en sous-tâches parallèles (SK-2) |
| `AUTOSPEC_COMPONENTS` | `0` | phase composants (solutionneur) |
| `AUTOSPEC_SETUP_INSTALL` | `0` | install réelle des deps composants |
| `AUTOSPEC_TECH_WRITER` | `0` | tech-writer auto après build |
| `AUTOSPEC_UI_TESTS` | `0` | tests d'acceptance UI Playwright |
| `AUTOSPEC_SMOKE_RUN` | `1` | démarre l'app livrée avant `done` |
| `AUTOSPEC_DEFINITION_OF_DONE` | `1` | gate déterministe de livraison |
| `AUTOSPEC_DOD_STRICT_CRITERIA` | `0` | rend bloquante l'absence de preuve verte par critère |
| `AUTOSPEC_RUNTIME_ACCEPTANCE` | `0` | gate navigateur/runtime web/fullstack |
| `AUTOSPEC_RUNTIME_ACCEPTANCE_TIMEOUT_S` | `90` | timeout du gate runtime |
| `AUTOSPEC_SESSION_MONITOR` | `1` | watchdog fenêtre d'usage Claude (M2) |
| `AUTOSPEC_CCUSAGE_CMD` | `npx --yes ccusage` | commande ccusage |
| `AUTOSPEC_RESUME_FALLBACK_MIN` | `60` | repli (min) si reset inconnu |

---

## 7. API (FastAPI + WebSocket)

**Projets** : `POST /api/projects` (accepte aussi `product_profile`),
`GET /api/projects`, `GET|DELETE
/api/projects/{id}`, `/chat`, `/spec-mode`, `/budget`, `/stop`, `/pause`,
`/resume`, `/run`, `/stop-app`, `/resume-build`, `/archive`, `/unarchive`,
`/files`, `/files/raw?path=`, `PUT /components`, `POST /components/setup`,
`POST /document`, `GET /export` (zip), `POST /git-export`.

**Provider** : `GET|POST /api/provider` (bascule claude/codex/openai/openrouter/
ollama/anthropic à chaud ; verrouillé en mode démo ; renvoie aussi
`capabilities`) ;
`GET /api/providers/{provider}/models` (découverte live des modèles — top-10
programmation pour OpenRouter, repli statique).

**Watchdog M2** : `POST /api/projects/{id}/cancel-resume` (annule la reprise
auto programmée après épuisement de la fenêtre d'usage Claude — détection sur
l'erreur CLI, heure de reset via epoch/ccusage/fallback, timer persisté
`resume_at` ré-armé au restart, bannière ⏰ dans le `RunPanel`).

**Stories** : `PATCH /…/stories/{sid}`, `POST /…/stories`, `DELETE
/…/stories/{sid}`, `/…/stories/reorder`, `/…/stories/{sid}/rebuild`,
`/…/stories/{sid}/force-done`, `/…/stories/{sid}/diff`.

**Temps réel** : WebSocket `/ws`. Le backend **sert aussi le frontend buildé**
(`frontend/dist`) en same-origin.

Gardes : `404` (inconnu), `409` (action interdite : pipeline active, story
`in_progress`…), `422` (validation), `400` (path-traversal).

---

## 8. Qualité, tests & CI

- **Backend — 463 tests pytest** : scheduler, runner, modèles, pipeline,
  providers, composants, streams/worktrees, DoD, delivery state, profils produit,
  runtime acceptance, skills prescriptives, smoke run, sécurité, observabilité,
  reprise, API et e2e feature factory déterministe.
- **Frontend — 136 tests Vitest** : logique pure (`criterionState`,
  `effectiveStatus`), rendu `Board`, `RunPanel`, `ProjectBar`, activité LLM,
  workspace/code viewer, API client, composants et `App`.
- **e2e — 1 test Playwright** hermétique (backend mode démo servant la SPA
  buildée, same-origin) : création → board peuplé → pause/reprise → critère
  (vert + tests + Gherkin) → suppression.
- **CI GitHub Actions** : workflow auto-contenu `Autospec/.github/workflows/ci.yml`
  + workflow racine monorepo `squad-ai/.github/workflows/autospec-ci.yml` (filtre
  `paths: Brainstorming/Autospec/**`) — 3 jobs : **backend** (pytest),
  **frontend** (build + vitest), **e2e** (Playwright).
- **Golden Projects** : `.github/workflows/golden-projects.yml` (manuel +
  nightly) lance une batterie déterministe : feature factory réelle, smoke,
  runtime acceptance, DoD, profils, skills, streams, frontend toolchain et
  contrats frontend.

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
│       ├── agents/              # personas, prompts, runner, providers/capabilities
│       ├── orchestrator/        # pipeline, scheduler, workspace, refine,
│       │                        # delivery_gate/state, profiles, runtime_acceptance,
│       │                        # skill_validation, pytest_report, events
│       └── api/server.py        # REST + WS + service SPA
├── frontend/src/                # App, api, types, components/ (Board, ProjectBar,
│                                # RunPanel, ChatPanel, CodeViewer, …), e2e/
└── workspace/<id>/              # CODE GÉNÉRÉ (projet uv autonome + repo git)
```

**État** : pipeline renforcée par des gates de livraison déterministes, profils
produit, skills validées, runtime acceptance et batterie golden ; les suites
locales vérifiées sont vertes (**463 backend**, **136 frontend**, golden locale
**71 tests**).
