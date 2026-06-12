# Autospec — Comment ça marche

Documentation technique complète : architecture, cycle de vie d'un projet, rôle
de chaque agent, gestion des LLMs, ordonnancement des tâches, boucle auto-spec,
persistance, temps réel et points d'extension.

> Pour un démarrage rapide (installation, lancement), voir le [README](./README.md).

---

## 1. Vue d'ensemble

Autospec est une **usine à features pilotée par des agents BMAD**. Depuis l'UI,
on décrit un projet ou une feature ; le backend orchestre alors une chaîne
d'agents qui transforment cette intention en **code testé** :

```
Idée  ──▶  PM        ──▶  PO            ──▶  QA (par story)   ──▶  Dev (×N)        ──▶  Code livré
(chat)     brief          epics + US         décomposition         BDD puis TDD         (workspace uv)
                          + Gherkin          outside-in du          outside-in
                          + priorité         Gherkin en tests       (pytest-bdd,
                            kanban           unitaires (mocks)      rouge→vert)
                                   ▲                                                          │
                                   │                  boucle auto-spec                        │
                                   └──────  Analyste (hypothèses, scoring,  ◀─────────────────┘
                                            priorisation)
```

Le principe directeur : **chaque agent a une responsabilité unique**, et
l'orchestrateur (déterministe, non-LLM) gère l'enchaînement, les dépendances, le
parallélisme et la vérification.

---

## 2. Arborescence

```
Autospec/
├── .vscode/launch.json          # compound "Full Stack (Backend + Frontend)"
├── how_it_works.md              # ce document
├── README.md
├── backend/                     # FastAPI + orchestrateur (géré par uv)
│   ├── pyproject.toml
│   └── autospec/
│       ├── config.py            # Settings (chemins BMAD, CLI Claude, env vars)
│       ├── models.py            # Modèles Pydantic (ProjectState, Epic, UserStory…)
│       ├── storage.py           # Persistance JSON par projet
│       ├── agents/
│       │   ├── personas.py      # Chargement des personas BMAD (system prompts)
│       │   ├── prompts.py       # Prompts de tâche (PM, PO, Dev, Analyste)
│       │   └── runner.py        # AgentRunner : ClaudeCliRunner / FakeRunner
│       ├── orchestrator/
│       │   ├── pipeline.py      # Cycle de vie complet PM→PO→Dev→Analyste
│       │   ├── scheduler.py     # Dépendances + priorité kanban (fonctions pures)
│       │   ├── workspace.py     # Scaffolding du projet uv généré
│       │   └── events.py        # Bus d'événements → WebSocket
│       └── api/
│           └── server.py        # REST + WebSocket + service du frontend buildé
│   └── tests/                   # 22 tests (scheduler, runner, pipeline, API)
├── frontend/                    # React + Vite + TypeScript
│   └── src/
│       ├── App.tsx
│       ├── api.ts               # client REST + connexion WebSocket
│       ├── types.ts
│       └── components/          # ProjectSetup, ChatPanel, Board, BacklogPanel, RunPanel
└── workspace/<project-id>/      # CODE GÉNÉRÉ (un projet uv autonome par projet)
    ├── pyproject.toml           # pytest + pytest-bdd
    ├── autospec-state.json      # état persistant du projet
    ├── features/*.feature       # Gherkin (écrits depuis les US)
    ├── tests/steps/*.py         # step definitions pytest-bdd
    ├── <package>/               # le code applicatif
    └── main.py                  # point d'entrée lancé par le bouton ▶
```

---

## 3. Les modèles de domaine (`models.py`)

Tout l'état d'un projet tient dans un seul objet **`ProjectState`**, sérialisé
en JSON. Les éléments clés :

| Modèle | Rôle |
|---|---|
| `ProjectState` | racine : objectif, phase, brief, backlog, epics, stories, chat, feedback, itération, flags |
| `Epic` | regroupement de stories, rattaché à une itération |
| `UserStory` | description, **`acceptance_criteria`** (objets `AcceptanceCriterion`), **Gherkin**, **`test_plan`** (tests unitaires planifiés par le QA), `depends_on`, **`priority`** (kanban 1-5), statut, tentatives ; méthodes `tests_for_criterion` / `criterion_state` |
| `AcceptanceCriterion` | `{id, text}` — un critère d'acceptance, identifiable et reliable à des tests |
| `PlannedTest` | un test unitaire planifié par le QA : `layer` (api/façade/service/repository/llm…), description, `mocks`, `file_hint`, **`criteria`** (ids des critères couverts), **`status`** (`TestState`) |
| `TestState` | état d'un test : `nonexistent` / `red` / `green` |
| `FeatureHypothesis` | hypothèse de l'analyste : `value` 1-5, `complexity` 1-5, `rank`, statut ; `score = value / complexity` |
| `ChatMessage` | rôle (`user`/`pm`/`po`/`dev`/`analyst`/`qa`/`system`) + contenu |

### Machines à états

**Phase du pipeline** (`PipelinePhase`) :
```
idle → spec → plan → build → done
              ▲                 │
              └── analyze ◀──────┘   (uniquement en mode auto-spec)
        (+ stopped / error à tout moment)
```

**Statut d'une story** (`StoryStatus`) :
```
todo → in_progress → red → green → done
                              │
                              └─(échec de revérification)→ todo (retry) → failed
```

**Statut d'une hypothèse** (`HypothesisStatus`) : `proposed → selected → done`
(ou `rejected`).

**État d'un critère d'acceptance** (dérivé de ses tests, `criterion_state`) :
**vert** seulement si tous ses tests sont verts (et qu'il en a au moins un),
**rouge** si au moins un test est rouge, sinon **inexistant**. Une story `done`
a une suite entièrement verte → tous ses critères sont verts.

---

## 4. Gestion des LLMs

**Point essentiel : Autospec n'appelle aucune API ni SDK LLM directement. Il
délègue tout au CLI Claude Code en mode headless**, derrière une abstraction.

### 4.1 L'abstraction `AgentRunner` (`agents/runner.py`)

La pipeline ne connaît qu'une interface :

```python
class AgentRunner(Protocol):
    async def arun(self, prompt, system_prompt, cwd=None, session_id=None) -> AgentResult: ...
```

Deux implémentations :

- **`ClaudeCliRunner`** (production) — lance le binaire `claude` en sous-processus.
- **`FakeRunner`** (tests) — dépile des réponses JSON pré-programmées, **sans
  aucun LLM**. C'est ce qui rend les 22 tests déterministes et instantanés.

Pour brancher un autre backend (SDK Anthropic, autre provider, mock), il suffit
d'écrire une classe avec la même méthode `arun` et de l'injecter via
`server.set_runner(...)`. **C'est le point d'extension propre du projet.**

### 4.2 Comment un appel est fait

`ClaudeCliRunner.arun` construit cette commande :

```
claude -p --output-format json
       --permission-mode bypassPermissions
       --append-system-prompt <persona BMAD>
       [--model <modèle>]        # seulement si AUTOSPEC_CLAUDE_MODEL est défini
       [--resume <session_id>]   # pour continuer une conversation
```

- le **prompt de tâche** est envoyé sur **stdin** ;
- la sortie est lue en JSON (`{"result": ..., "session_id": ...}`) ;
- `extract_json()` extrait le premier objet JSON même si l'agent l'entoure de
  prose ou de fences markdown (parsing par comptage d'accolades) ;
- un **timeout** (`AUTOSPEC_AGENT_TIMEOUT_S`, 1800 s par défaut) tue le process
  s'il bloque ; toute sortie non-zéro lève `AgentError`.

### 4.3 Ce qui différencie les agents

Tous les agents partagent **le même backend LLM**. Ils ne diffèrent que par :

1. **La persona = system prompt** (`agents/personas.py`) — le fichier BMAD
   correspondant (`_bmad/bmm/agents/{pm,sm,dev,analyst,qa}.md`) **plus un override
   « mode programmatique »** qui désactive les menus interactifs de BMAD,
   interdit greetings/questions de menu, et force **une seule réponse JSON**.
   Si un fichier persona est absent, un fallback texte court est utilisé.
2. **Le prompt de tâche** (`agents/prompts.py`) — le message user spécifique à
   l'étape (interview PM, plan PO, story Dev, exploration Analyste).

### 4.4 Sessions

Seul le **PM en interview** maintient une session continue : son `session_id`
est conservé et repassé en `--resume` pour garder le contexte de la
conversation de spécification d'un tour à l'autre. PO, Dev et Analyste sont
appelés en **one-shot** sans état.

### 4.5 Authentification

**Aucune clé API n'est gérée par Autospec.** C'est l'authentification du CLI
Claude Code déjà installé et connecté sur la machine (compte/abonnement) qui est
utilisée. Si le CLI n'est pas authentifié, les agents échouent.

> Sous Windows, `AUTOSPEC_CLAUDE_CMD` résout automatiquement `claude.cmd` (et
> non le `claude` qui est un `.ps1` non exécutable par un subprocess).

---

## 5. Le cycle de vie d'un projet (`orchestrator/pipeline.py`)

Une instance `Pipeline` par projet. Tout le cycle tourne dans **une tâche
asyncio de fond** (`_alifecycle`). L'API ne fait qu'envoyer des messages et lire
l'état.

```python
workspace.scaffold(state)               # crée le projet uv généré
brief = await self._aspec_phase()       # PM
while not stop_requested:
    await self._aplan_phase()           # PO
    await self._abuild_phase()          # Dev ×N
    if not auto_spec: break
    await self._anext_feature_phase()   # Analyste + PM (brief suivant)
```

### 5.1 Phase SPEC — le PM (`pm`)

Le PM interviewe l'utilisateur via le chat. À chaque tour il renvoie un JSON :
- `{"type": "question", "message": "..."}` → la pipeline **attend** la réponse
  utilisateur (`asyncio.Queue`), qui est injectée dans le chat puis relancée ;
- `{"type": "brief", "brief": "..."}` → le brief est stocké, on passe au PO.

En **mode auto-spec**, le prompt impose au PM de **ne poser aucune question** et
de produire le brief immédiatement en décidant lui-même.

### 5.2 Phase PLAN — le PO (`sm`)

Le PO reçoit le brief et renvoie un JSON `epics[]` → `stories[]`. Chaque story
porte description, `acceptance_criteria`, **Gherkin**, `depends_on` et
**`priority`** (kanban). L'orchestrateur :
1. crée les `Epic`/`UserStory` (priorité bornée 1-5) ;
2. **nettoie les dépendances** (`scheduler.sanitize_dependencies`) : supprime
   les références inconnues / auto-références et **casse les cycles**
   défensivement pour qu'aucun deadlock ne soit possible ;
3. **écrit les fichiers `.feature`** depuis le Gherkin (`write_feature_files`).

### 5.3 Phase BUILD — QA puis Dev

C'est le cœur BDD/TDD. La boucle d'ordonnancement (voir §6) sélectionne les
stories **prêtes** et lance jusqu'à `AUTOSPEC_MAX_PARALLEL_DEVS` agents en
parallèle (sémaphore). Pour chaque story (`_abuild_story`) :

1. statut `in_progress`, `attempts += 1` ;
2. **décomposition outside-in des tests par le QA (`qa`)** — uniquement à la
   première tentative (`_adesign_tests`) : à partir du Gherkin (qui garde la
   vision fonctionnelle de bout en bout), l'architecte QA dérive **avant toute
   implémentation** les tests unitaires de chaque couche, en **London school /
   top-down** : l'API appelle-t-elle bien la façade ? la façade le service ?
   le service le repository ou le client LLM ? Chaque test **mocke ses
   collaborateurs directs** et est **rattaché aux critères d'acceptance** qu'il
   couvre (via leurs ids). La **granularité s'adapte à la taille de la
   story** : une story triviale peut n'avoir aucun test unitaire (le Gherkin
   suffit), une grosse story est décomposée couche par couche. Le plan
   (`test_plan`) est stocké sur la story, affiché dans le board, et injecté
   dans le prompt du Dev. Un échec du QA est **non-fatal** : le Dev part alors
   du Gherkin seul ;
3. un agent Dev est lancé **dans le répertoire du workspace** (`cwd=ws`). Son
   prompt impose le processus outside-in : écrire les **step definitions
   pytest-bdd** liées au `.feature` → écrire **tous les tests unitaires du plan
   QA** (du plus externe au plus interne, mocks compris, sans rien implémenter)
   → lancer pytest et **vérifier l'échec (rouge)** → implémenter le minimum
   **couche par couche du haut vers le bas** → relancer jusqu'au **vert**
   complet ;
4. l'agent renvoie `{"status", "summary", "files", "test_results"}` où
   `test_results` donne l'**état final de chaque test du plan** (green/red) ;
   ces états sont reportés sur les `PlannedTest` (`_apply_test_results`) ;
5. **« Trust but verify »** : l'orchestrateur **relance lui-même `uv run pytest`**
   (`_arun_pytest`) — il ne fait pas confiance à l'auto-déclaration de l'agent :
   - vert → story `done`, et **tous les tests de la story passent à `green`**
     (la suite est verte, donc cohérent) ;
   - rouge → si `attempts < AUTOSPEC_DEV_MAX_ATTEMPTS`, la story repasse `todo`
     (re-tentée) ; sinon `failed` avec le tail de sortie pytest dans
     `last_error`. Les états par test rapportés par l'agent sont conservés.

L'état de chaque **critère** se déduit de ses tests (voir §3) : le board affiche
chaque critère comme une ligne dépliable (inexistant / rouge / vert).

Les stories qui dépendaient d'une story `failed` sont marquées `failed` avec un
message explicite (pas de deadlock, pas d'attente infinie).

### 5.4 Phase ANALYZE + brief suivant — l'Analyste (`analyst`) puis le PM

En mode auto-spec, après chaque itération livrée (`_anext_feature_phase`) :

1. **`_aanalyze_phase`** : l'hypothèse `selected` de l'itération qui vient de
   finir passe `done`. L'analyste reçoit l'historique (US livrées/échouées,
   hypothèses déjà livrées à ne pas reproposer, backlog restant, **feedback
   utilisateur**) et renvoie :
   ```json
   {"message": "...", "hypotheses": [{"id","title","rationale","value","complexity"}], "selected": "FH-x"}
   ```
   Les hypothèses sont **ordonnées par priorité** (kanban, pas de sprint), le
   feedback utilisateur primant sur tout. Le backlog priorisé est persisté dans
   `state.backlog` et affiché dans l'UI.
2. **Le PM** rédige ensuite le brief de **l'hypothèse choisie**
   (`pm_brief_for_feature`), l'itération est incrémentée, le feedback consommé
   est vidé, et le cycle PLAN→BUILD repart.

La responsabilité reste découpée : **l'analyste décide _quoi_**, le PM rédige le
brief, le PO écrit les US.

La boucle continue **indéfiniment** jusqu'au bouton ⏹ (`astop`), qui pose un
flag, débloque une éventuelle interview en attente et laisse l'étape courante se
terminer proprement (phase finale `stopped`).

---

## 6. Ordonnancement : dépendances + kanban (`orchestrator/scheduler.py`)

Fonctions pures, entièrement testées unitairement.

- **`validate_dependencies`** : détecte les ids inconnus et les **cycles** (DFS
  itératif à coloriage).
- **`sanitize_dependencies`** : purge les références invalides et casse les
  cycles restants (sécurité anti-deadlock).
- **`ready_stories`** : stories `todo` dont **toutes** les dépendances sont
  `done`. **Ordre kanban** : triées par `priority` croissante (1 = haute), à
  égalité par ordre de déclaration. → Sur les lots **sans dépendance**, c'est la
  priorité qui décide qui passe en développement d'abord.
- **`pending_stories`** : stories encore actives (todo/in_progress/red/green),
  utilisé pour savoir quand la phase BUILD est terminée.

Il n'y a **pas de notion de sprint** — uniquement un flux continu priorisé.

---

## 7. Le workspace généré (`orchestrator/workspace.py`)

Chaque projet a son propre **projet uv autonome** dans `workspace/<id>/`,
scaffoldé de façon idempotente :

- `pyproject.toml` avec `pytest` + `pytest-bdd` (dependency-group `dev`) ;
- le package Python (nom dérivé du nom de projet, slugifié) ;
- `features/`, `tests/steps/`, `main.py` (point d'entrée par défaut).

Les `.feature` sont (ré)écrits à chaque planification depuis le Gherkin des US.
Les agents Dev n'écrivent **que** dans ce répertoire et ne touchent jamais aux
`.feature` ni à `autospec-state.json` (contrainte du prompt).

---

## 8. État, persistance et temps réel

### Persistance (`storage.py`)
À chaque changement notable, `_sync()` écrit `autospec-state.json` dans le
workspace et publie l'état sur le bus. Au démarrage, `list_states()` recharge
les projets existants.

### Bus d'événements (`orchestrator/events.py`)
Un `EventBus` in-process fan-out vers les abonnés WebSocket. Deux types
d'événements :
- `{"type": "state", "state": <ProjectState complet>}` — après chaque `_sync()` ;
- `{"type": "log", "source": "...", "line": "..."}` — logs des agents Dev et de
  l'exécution de l'app.

Les consommateurs lents (queue pleine) sont **désabonnés** plutôt que de bloquer
la pipeline.

---

## 9. L'API (`api/server.py`)

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/projects` | crée un projet (`goal`, `name`, `auto_spec`) et démarre la pipeline |
| `GET` | `/api/projects` | liste les projets (vivants + persistés) |
| `GET` | `/api/projects/{id}` | état complet d'un projet (live ou rechargé du disque) |
| `DELETE` | `/api/projects/{id}` | **supprime** un projet : stoppe la pipeline (`adispose`) et efface le workspace |
| `POST` | `/api/projects/{id}/chat` | envoie un message (réponse PM en phase spec, sinon **feedback**) |
| `POST` | `/api/projects/{id}/stop` | arrête la boucle |
| `POST` | `/api/projects/{id}/run` | lance le `main.py` du code généré |
| `WS` | `/ws` | flux temps réel (`state` / `log` / `deleted`) |

> **Persistance résiliente** : `load_state` migre les anciens formats (ex.
> `acceptance_criteria` en `list[str]` → objets) et ignore proprement un fichier
> d'état corrompu/incompatible, pour qu'il ne casse jamais la liste des projets.

Le **chat** est contextuel : pendant la phase `spec` un message répond au PM ;
en dehors, il est rangé dans `state.feedback` et **consommé par l'analyste** au
cycle suivant.

En production, si `frontend/dist` existe, FastAPI **sert le frontend buildé**
(SPA) directement sur `/`.

### Exécution des sous-processus — spécificité Windows

`arun_app` et `_arun_pytest` n'utilisent **pas** les sous-processus asyncio :
sous Windows, uvicorn tourne sur un `SelectorEventLoop` qui lève
`NotImplementedError` pour `create_subprocess_exec` (seul le `ProactorEventLoop`
les supporte). Les child processes sont donc exécutés **dans un thread worker**
via le module `subprocess` :
- `_arun_pytest` → `subprocess.run` dans `asyncio.to_thread` ;
- `arun_app` → `subprocess.Popen` dans un thread qui streame la sortie ligne par
  ligne vers la loop avec `loop.call_soon_threadsafe(self._log, ...)`.

C'est insensible au type de loop et multiplateforme — et ça reste valable quel
que soit le mode de lancement (le `launch.json` démarre `python -m uvicorn`
directement, donc on ne peut pas régler la policy d'event loop en amont).

---

## 10. Le frontend (`frontend/src`)

React + Vite + TypeScript. Vite (port 5183) proxifie `/api` et `/ws` vers le
backend (port 8100). Composants :

- **`ProjectBar`** : **sélection** et **suppression** des projets (chips avec
  pastille de phase, bouton ✕ avec confirmation, bouton ＋ Nouveau).
- **`ProjectSetup`** : saisie de l'objectif + case **Auto-spec**.
- **`ChatPanel`** : conversation PM/feedback (rôles colorés).
- **`Board`** : EPICs → cartes US avec statut coloré, **badge de priorité
  kanban** `P1`-`P5`, détails dépliables. Chaque **critère d'acceptance est une
  ligne dépliable** avec son état (inexistant / rouge / vert, calculé par
  `criterionState`) ; en la dépliant on voit **la liste de ses tests
  d'acceptance** (avec leur état) **et le Gherkin associé**.
- **`BacklogPanel`** : backlog priorisé de l'analyste (rang, V/C, statut,
  livrées).
- **`RunPanel`** : phase courante, bouton **▶ Lancer le projet**, bouton **⏹
  Stopper la boucle**, et logs streamés (filtrés sur le projet sélectionné).

`App.tsx` maintient la **liste des projets** et l'**id sélectionné** ; les
événements WebSocket `state` font un upsert dans la liste, `deleted` retire le
projet, `log` est filtré par projet à l'affichage.

`App.tsx` ouvre une connexion WebSocket (`connectEvents`) avec **reconnexion
automatique** ; chaque event `state` remplace l'état du projet courant, chaque
event `log` est appendé (fenêtre glissante de 500 lignes).

---

## 11. Configuration (`config.py`)

Variables d'environnement (toutes optionnelles) :

| Variable | Défaut | Rôle |
|---|---|---|
| `AUTOSPEC_BMAD_DIR` | `../_bmad` | dossier d'installation BMAD |
| `AUTOSPEC_CLAUDE_CMD` | auto (`claude.cmd`/`.exe`) | binaire Claude Code |
| `AUTOSPEC_CLAUDE_MODEL` | (défaut du CLI) | modèle imposé aux agents |
| `AUTOSPEC_PERMISSION_MODE` | `bypassPermissions` | mode permissions des agents |
| `AUTOSPEC_AGENT_TIMEOUT_S` | `1800` | timeout d'un appel agent |
| `AUTOSPEC_MAX_PARALLEL_DEVS` | `2` | agents Dev en parallèle |
| `AUTOSPEC_DEV_MAX_ATTEMPTS` | `2` | tentatives par story |
| `AUTOSPEC_UV_CMD` | `uv` | binaire uv pour le workspace généré |

---

## 12. Tests (`backend/tests`)

30 tests, sans aucun appel LLM réel (grâce à `FakeRunner`) :

- **`test_scheduler.py`** — dépendances, détection de cycles, sanitization,
  **ordre kanban**.
- **`test_runner.py`** — `extract_json` (prose, fences, objets imbriqués).
- **`test_models.py`** — **état d'un critère** (`criterion_state`) : inexistant,
  rouge si un test rouge, vert seulement si tous verts, story `done` ⇒ vert.
- **`test_pipeline.py`** — pipeline complète avec interview, écriture des
  `.feature`, blocage des dépendants en cas d'échec, **boucle auto-spec avec
  analyste**, priorité kanban de bout en bout, **plan de tests QA** (stocké,
  rattaché aux critères, injecté au Dev, non-fatal en cas d'échec), **états des
  tests** propagés, stockage du feedback.
- **`test_api.py`** — création/complétion de projet, **suppression de projet**,
  arrêt pendant l'interview, validations (goal vide, projet inconnu).

```powershell
cd backend
uv run pytest
```

`green_pytest` (conftest) monkeypatche `_arun_pytest` pour simuler une suite
verte sans lancer de vrais sous-processus.

---

## 13. Points d'extension

| Besoin | Où agir |
|---|---|
| Changer de backend LLM (SDK Anthropic, autre provider) | nouvelle classe `AgentRunner` + `server.set_runner(...)` |
| Modifier le comportement d'un agent | persona BMAD dans `_bmad/bmm/agents/` ou prompt dans `agents/prompts.py` |
| Ajouter une étape au pipeline | nouvelle phase dans `PipelinePhase` + méthode `_a…_phase` dans `pipeline.py` |
| Changer la stratégie d'ordonnancement | fonctions pures de `scheduler.py` |
| Réorganiser le backlog à la main (drag & drop) | non implémenté — actuellement géré via le feedback chat repris par l'analyste |
| Vérifier individuellement chaque test planifié | les états viennent du rapport de l'agent Dev + verify globale ; un mapping node-pytest ↔ `PlannedTest` serait nécessaire pour une vérif fichier par fichier |
| Durcir les permissions des agents | `AUTOSPEC_PERMISSION_MODE` |

---

## 14. Résumé en une phrase

Autospec orchestre de façon **déterministe** une équipe d'**agents BMAD exécutés
via le CLI Claude Code**, où chaque agent a une responsabilité unique (décider,
spécifier, planifier, **concevoir les tests outside-in**, coder en BDD/TDD), où
l'orchestrateur **revérifie lui-même** chaque livraison par les tests, et où une
**boucle auto-spec** pilotée par un analyste fait progresser le produit en
continu — le tout visualisé en temps réel dans un board kanban.
