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
│   └── tests/                   # 131 tests (scheduler, runner, models, pipeline, refine, API, scripted, pytest_report)
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
| `ProjectState` | racine : objectif, phase, brief, **`spec_mode`** (`"interview"` par défaut ou `"brainstorm"` — pilote la phase spec), **`budget_usd`** (plafond de coût en $, `0` = illimité) et **`budget_tokens`** (plafond de tokens, `0` = illimité), **`architecture`** (design technique courant), backlog, epics, stories, chat, feedback, **`build_guidance`** (consignes données pendant le build), **`plan_quality`** (dernier score de raffinement du plan PO, -1 = non exécuté — exposé à l'UI), **`usage`** (modèle `Usage` : coût/tokens/nombre d'appels cumulés sur tous les agents — exposé à l'UI), itération, flags |
| `Usage` | observabilité cumulée d'un projet : `cost_usd`, `input_tokens`, `output_tokens`, `agent_calls` — sommés sur chaque appel agent |
| `Epic` | regroupement de stories, rattaché à une itération |
| `UserStory` | description, **`acceptance_criteria`** (objets `AcceptanceCriterion`), **Gherkin**, **`test_plan`** (tests unitaires planifiés par le QA), `depends_on`, **`priority`** (kanban 1-5), statut, tentatives, **`quality_score`** (dernier score de raffinement du code de la story, -1 = non exécuté — exposé à l'UI) ; méthodes `tests_for_criterion` / `criterion_state` |
| `AcceptanceCriterion` | `{id, text}` — un critère d'acceptance, identifiable et reliable à des tests |
| `PlannedTest` | un test unitaire planifié par le QA : `layer` (api/façade/service/repository/llm…), description, `mocks`, `file_hint`, **`criteria`** (ids des critères couverts), **`status`** (`TestState`) |
| `TestState` | état d'un test : `nonexistent` / `red` / `green` |
| `FeatureHypothesis` | hypothèse de l'analyste : `value` 1-5, `complexity` 1-5, `rank`, statut ; `score = value / complexity` |
| `ChatMessage` | rôle (`user`/`pm`/`po`/`dev`/`analyst`/`architect`/`qa`/`critic`/`judge`/`system`) + contenu |

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

**Point essentiel : Autospec n'appelle aucun SDK LLM directement pour Claude —
il délègue au CLI Claude Code en mode headless** ; les providers hors
abonnement (OpenAI, **OpenRouter**, Ollama, Anthropic API) passent par
**LangChain** et OpenAI Codex par son propre CLI (`codex exec`), le tout
derrière une abstraction commune.

### 4.1 L'abstraction `AgentRunner` (`agents/runner.py`)

La pipeline ne connaît qu'une interface :

```python
class AgentRunner(Protocol):
    async def arun(self, prompt, system_prompt, cwd=None, session_id=None) -> AgentResult: ...
```

Implémentations (`agents/runner.py` + `agents/providers.py`) :

- **`ClaudeCliRunner`** (production) — lance le binaire `claude` en sous-processus.
- **`CodexCliRunner`** — miroir OpenAI : `codex exec --json` en headless (le
  system prompt est préfixé au prompt, sortie JSONL parsée).
- **`OpenAiRunner` / `OpenRouterRunner` / `OllamaRunner` / `AnthropicRunner`**
  (`agents/providers.py`) — providers **hors abonnement** via **LangChain**
  (`langchain-openai` / `langchain-ollama` / `langchain-anthropic`, imports
  paresseux). **OpenRouter** est un hub compatible-OpenAI : `OpenRouterRunner`
  réutilise `ChatOpenAI` avec le `base_url`/clé OpenRouter (clés lues depuis
  `OPENROUTER_API_KEY`/`OPENROUTER_BASE_URL`). Ces API de chat étant sans état ni
  outils : (a) la continuité de session est **rejouée en mémoire** par
  `session_id` ; (b) quand un `cwd` est fourni (agents Dev), un **protocole
  d'outils JSON borné** est injecté au system prompt — le modèle répond
  `{"tool": "write_files"|"read_files", ...}` pendant au plus
  `AUTOSPEC_PROVIDER_TOOL_ROUNDS` tours (chemins confinés au workspace), puis
  donne sa réponse finale. Coût estimé via `AUTOSPEC_<PROVIDER>_PRICE_IN/_OUT`
  ($/1M tokens) ; Ollama = 0. Sélection par `AUTOSPEC_AGENT_PROVIDER` ou à chaud
  via `GET/POST /api/provider` (`make_runner()` ; bascule le runner de toutes les
  pipelines vivantes ; verrouillé en mode démo).
- **Découverte de modèles à la volée** (`agents/discovery.py`,
  `GET /api/providers/{provider}/models`) — au lieu d'une liste statique, le
  sélecteur affiche les modèles **réellement joignables** : Ollama interroge le
  démon, OpenAI/Codex le endpoint `/models` avec la clé, et **OpenRouter charge
  dynamiquement les 10 modèles de programmation les plus populaires**
  (`GET {base}/models?category=programming` — l'API derrière
  `openrouter.ai/models?categories=programming&order=most-popular`). Repli sur la
  liste statique suggérée (`provider_models`) si la découverte échoue (hors-ligne,
  pas de clé).
- **`FakeRunner`** (tests unitaires) — dépile des réponses JSON pré-programmées,
  **sans aucun LLM**. C'est ce qui rend les tests déterministes et instantanés.
- **`ScriptedRunner`** (mode démo / e2e, `agents/scripted.py`) — reconnaît
  l'agent appelé d'après le prompt et renvoie un projet canné complet
  (PM→PO→QA→Dev, voire l'analyste). Activé par `AUTOSPEC_FAKE_AGENTS=1` ; la
  vérification `uv run pytest` est alors court-circuitée et l'app générée est
  lancée avec l'interpréteur courant — **tout le stack tourne sans le CLI Claude
  ni build de venv uv**, ce qui rend le lancement back+front entièrement
  vérifiable. `AUTOSPEC_DEMO_DELAY_S` ralentit les agents pour rendre les
  transitions (et la pause) observables.

Pour brancher un autre backend (SDK Anthropic, autre provider, mock), il suffit
d'écrire une classe avec la même méthode `arun` et de l'injecter via
`server.set_runner(...)`. **C'est le point d'extension propre du projet** —
c'est exactement ainsi que `OpenAiRunner`/`OllamaRunner` ont été ajoutés.

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

### 4.6 Observabilité — coût & tokens

`AgentResult` porte, en plus du texte/`session_id`, l'**usage** de l'appel parsé
du JSON du CLI : `cost_usd` (depuis `total_cost_usd`), `input_tokens` /
`output_tokens` (depuis `usage`) et `duration_ms` — robuste aux clés manquantes
(`FakeRunner`/`ScriptedRunner` renvoient un usage à zéro). La pipeline accumule
ces métriques **par projet** via un wrapper `_UsageTracker` (sa méthode `arun`
respecte le `Protocol AgentRunner`) qui enveloppe **tous** les appels agent
(`self._tracked` substitué à `self.runner`, y compris les appels critic/judge/
revise du raffinement passés à `refine.arefine`). Le total est cumulé dans
`ProjectState.usage` (modèle `Usage` : `cost_usd`, `input_tokens`,
`output_tokens`, `agent_calls`), exposé à l'UI dans l'état du projet.

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
    await self._aarchitect_phase()      # Architecte (optionnel, OFF par défaut)
    await self._abuild_phase()          # Dev ×N
    if not auto_spec: break
    await self._anext_feature_phase()   # Analyste + PM (brief suivant)
```

### 5.1 Phase SPEC — interview socratique ou brainstorming

La phase spec a **deux modes**, pilotés par `ProjectState.spec_mode`
(`"interview"` par défaut ou `"brainstorm"`). `_aspec_phase` branche selon ce
mode : persona **PM** (`pm`) pour l'interview, persona **analyste** (BMAD
`analyst`, « Mary ») pour le brainstorming. Dans les deux cas, à chaque tour
l'agent renvoie un JSON :
- `{"type": "question", "message": "..."}` → la pipeline **attend** la réponse
  utilisateur (`asyncio.Queue`), qui est injectée dans le chat puis relancée ;
- `{"type": "brief", "brief": "..."}` → le brief est stocké, on passe au PO.

**Mode interview (`pm_interview`).** Le PM mène une **facilitation socratique par
dimensions** : il questionne dimension par dimension (problème/pourquoi &
job-to-be-done, personas, périmètre MVP, hors-périmètre, contraintes, données,
vues/UX, cas limites, critères de succès), **reformule** et **confronte les
non-dits**, puis produit le brief.

**Mode brainstorming (`pm_brainstorm`).** L'analyste « Mary » **re-questionne le
besoin lui-même** en deux temps : phase **DIVERGER** (élargir l'espace des
possibles — angles, analogies, inversion du problème, JTBD alternatifs) puis
phase **CONVERGER** (choisir/prioriser selon valeur/effort/risque), avant de
produire le brief.

En **mode auto-spec**, le prompt impose au PM de **ne poser aucune question** et
de produire le brief immédiatement en décidant lui-même.

Le mode se règle via `POST /api/projects/{id}/spec-mode` (corps `{mode}`,
méthode `Pipeline.aset_spec_mode`, **422** si le mode est invalide). Côté UI, un
**toggle 💬 Interview / 🧠 Brainstorming** est affiché dans le `ChatPanel` quand
la phase est `spec`.

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
   `test_results` est une liste `[{"id", "status", "nodeids": [...]}]` : pour
   chaque test planifié (UT-x), l'agent déclare le `status` auto-évalué **et les
   nodeids pytest exacts** qu'il a écrits (`chemin/fichier.py::nom_test`) ;
5. **« Trust but verify »** : l'orchestrateur **relance lui-même `uv run pytest`**
   (`_arun_pytest`) — il ne fait pas confiance à l'auto-déclaration de l'agent.
   La commande lancée est désormais
   `uv run pytest -q --json-report --json-report-file=<tmp>` et renvoie un
   **triplet `(suite_green: bool, output: str, results: dict[nodeid → outcome])`** ;
   le rapport JSON est parsé par le module `orchestrator/pytest_report.py`
   (fonction `parse(path)`, robuste : fichier manquant/corrompu → `{}`). Le plugin
   `pytest-json-report` est ajouté aux dépendances dev du scaffold
   (`orchestrator/workspace.py`) pour produire ce rapport.

   Les états par test ne viennent donc plus de l'auto-déclaration mais de
   l'**exécution réelle**, via `_apply_test_states(story, reported, real)` : pour
   chaque test planifié on regarde les outcomes RÉELS de ses nodeids déclarés
   (`tous passed → green`, `au moins un failed/error → red`). Fallbacks : si aucun
   nodeid du test n'est trouvé dans le rapport, on retombe sur le `status`
   auto-déclaré par le Dev ; et si la **suite entière est verte**, les tests
   planifiés encore `nonexistent` (non mappés) sont passés à `green`. Autrement
   dit l'**OUTCOME** (pass/fail) vient du vrai pytest, seul le **LIEN structurel**
   (quel nodeid couvre quel UT) vient de l'agent.

   Ensuite, au niveau de la story :
   - vert → story `done` (la suite est verte, donc cohérent) ;
   - rouge → si `attempts < AUTOSPEC_DEV_MAX_ATTEMPTS`, la story repasse `todo`
     (re-tentée) ; sinon `failed` avec le tail de sortie pytest dans
     `last_error`. Les états par test, eux, reflètent le rapport réel.

   En mode démo (`AUTOSPEC_FAKE_AGENTS`), `_arun_pytest` court-circuite et renvoie
   `(True, ..., {})` (inchangé).

Quand les **skills** sont activées (§5.10), les prompts QA et Dev reçoivent en
plus un **catalogue compact de compétences** à charger à la demande, et le
workspace est ensemencé de `.claude/skills/` pour la découverte native.

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

### 5.5 Interruption : pause / reprise

En plus de l'arrêt, la pipeline expose une **pause coopérative**. Un
`asyncio.Event` (`_resume_event`) est vérifié à des **points de contrôle**
(`_checkpoint`) entre les itérations et entre les lots de stories du build :
`apause()` efface l'event (la pipeline se bloque au prochain checkpoint et
`state.paused` passe à `true`), `aresume()` le repose. `astop()` repose aussi
l'event pour qu'une pipeline en pause puisse se terminer. Les boutons **⏸ Pause /
▶ Reprendre** du front pilotent ces endpoints.

### 5.6 Harnais de raffinement — maker → critic → judge (`orchestrator/refine.py`)

Optionnellement, un **harnais générique de raffinement** améliore les artefacts
produits par les agents (le plan du PO, le code du Dev) via une **boucle
itérative à trois rôles** :

- un agent **maker** produit un artefact (le PO qui écrit les epics/US, ou le
  Dev qui écrit du code) ;
- un agent **critic** (persona `critic`) analyse l'artefact en **ReAct
  (REFLECT puis ACT)** : il le décompose en sous-aspects, raisonne, puis propose
  des améliorations **concrètes et actionnables** — il **ne réécrit pas**
  lui-même ;
- un agent **judge** (persona `judge`) **note la qualité de 0 à 100** au regard
  de critères explicites ;
- le maker **révise** ensuite l'artefact en intégrant la critique, et la boucle
  recommence.

**Arrêt déterministe — le point clé.** La boucle s'arrête dès que, **selon ce
qui survient en premier** :
- le **score du juge atteint le seuil** (`AUTOSPEC_REFINE_QUALITY_THRESHOLD`),
  ou
- le **nombre maximal d'allers-retours est atteint**
  (`AUTOSPEC_REFINE_MAX_ROUNDS`, cap dur).

Deux autres arrêts déterministes existent : **critique vide** (le critic est
satisfait → `critic_empty`) et **révision rejetée** par une garde (`rejected`).
Si la sortie du juge est **illisible**, le score est traité comme « seuil
atteint » → on s'arrête (jamais de boucle infinie).

Le cœur est la fonction `arefine(...)` qui retourne un
`RefineOutcome(text, rounds, score, stopped_reason)`, avec
`stopped_reason ∈ {threshold, max_rounds, critic_empty, rejected, disabled}`.
Les prompts (`critic_review`, `judge_quality`, `po_revise`, `dev_revise`) et les
constantes de critères vivent dans `agents/prompts.py` :
- **`PLAN_CRITERIA`** — INVEST, Gherkin testable, découpage cohérent,
  dépendances/priorités ;
- **`CODE_CRITERIA`** — SoC, DRY, cas limites, tests lisibles.

**Intégration PO** — dans `_aplan_phase`, le plan produit est passé à
`_arefine_plan` (maker = PO / persona `sm`, critères `PLAN_CRITERIA`). Un message
système annonce « Plan raffiné en N tour(s) — qualité S/100 ».

**Intégration Dev** — après qu'une story passe au **vert**, `_arefine_code`
lance une boucle critic/judge sur le code, avec une **garde par snapshot git**
dans le workspace : avant la boucle, l'état vert est commité ; chaque révision
n'est **acceptée que si `uv run pytest` reste vert** — sinon `git reset --hard`
+ `git clean -fd` pour rollback, et la version verte précédente est conservée.
Si git est indisponible, le raffinement code est **ignoré** (log). Le critic et
le juge du code tournent avec `cwd` = le workspace, donc ils **lisent les
fichiers générés**.

Les rôles de chat `critic` et `judge` (modèle `ChatRole`) sont affichés dans
l'UI : **🧐 Critique** et **⚖️ Juge**.

> **OFF par défaut** pour économiser des tokens. L'activation se fait via les
> variables `AUTOSPEC_REFINE*` (voir §11). Le helper `settings.refine_for(role)`
> = interrupteur global **ET** flag du rôle. À terme, l'activation se fera selon
> la complexité du problème ou la qualité résultante ; pour l'instant uniquement
> via ces variables.

### 5.7 Phase Architecture (optionnelle) — l'Architecte (`architect`)

Entre la phase PLAN (PO) et la phase BUILD, une **phase Architecture optionnelle**
peut produire un **design technique** qui guide le QA et le Dev. Pilotée par
l'agent BMAD **`architect`** (persona `architect`, fallback « Winston »).

- `_aarchitect_phase` : si `settings.architecture_enabled` est faux, ne fait
  rien. Sinon la phase passe à `architect` ; l'agent reçoit le brief et les
  **titres des stories planifiées de l'itération courante**, et renvoie un JSON
  `{"message": "...", "design": "<markdown court>"}` : architecture cible
  (couches/modules), composants clés, conventions de nommage, contraintes
  transverses — **pas de sur-ingénierie, juste assez pour guider
  l'implémentation**. Le design est stocké dans `state.architecture` et émis
  dans le chat (rôle `architect`).
- **Injection** : tant que `state.architecture` est non vide, un bloc
  « Contexte architecture (à respecter) » est inséré dans le prompt **QA**
  (`qa_test_plan`) et le prompt **Dev** (`dev_story`, donc aussi `dev_revise`).
- Un échec de l'agent est **non-fatal** (log + on continue sans design).

> **OFF par défaut** (même patron que le harnais de raffinement). L'activation
> se fait via `AUTOSPEC_ARCHITECTURE` (voir §11). Quand la phase est désactivée,
> `state.architecture` reste vide et aucun appel agent supplémentaire n'est fait.

### 5.8 Budget tokens/coût + arrêt automatique

Un projet peut porter un **plafond de coût et/ou de tokens** : `budget_usd`
(plafond en $) et `budget_tokens` (plafond de tokens), avec `0` = **illimité**.
Les deux sont réglables **à la création** (`POST /api/projects` accepte
`budget_usd`/`budget_tokens`) ou **après coup** via `POST /api/projects/{id}/budget`.

`Pipeline._enforce_budget()` est appelé à **chaque point de contrôle**
(`_checkpoint` : entre itérations, entre lots de stories du build, et dans la
boucle auto-spec). Dès que `state.usage` (voir §4.6) atteint le budget, la
pipeline **s'arrête proprement** (`_stop_requested`, comme un stop manuel) avec
un message « 💰 Budget atteint ». C'est la base pour, à terme, activer plus ou
moins de raffinement / d'architecture **selon le budget**.

Côté UI : un champ **« Budget max ($) »** dans `ProjectSetup`, et la jauge
d'usage du `RunPanel` affiche **« 💸 $X / $Y »** et passe en rouge
(`.over-budget`) quand le plafond est atteint.

### 5.9 Composants, impact des feedbacks, livraison & tests UI

- **Composants (E3/E4)** — avec `AUTOSPEC_COMPONENTS=1`, `_apropose_components`
  (persona `architect`, prompt `components_proposal`) tourne **juste après le
  brief** (1re itération) et remplit `ProjectState.components` (modèle
  `Component` : kind backend/frontend/database/cache/other, statut
  proposed/approved/created/rejected — les obligatoires sont pré-approuvés).
  L'utilisateur édite via `PUT /api/projects/{id}/components` (panneau 🧱) puis
  `POST .../components/setup` lance `orchestrator/setup_exec.py` en tâche de
  fond : scaffolds **idempotents** (`backend/` FastAPI, `frontend/` React+Vite,
  `docker-compose.yml` pour db/cache) ; `uv sync`/`npm install` réels seulement
  si `AUTOSPEC_SETUP_INSTALL=1` (démo-safe).
- **Analyse d'impact d'un feedback (E2)** — un message envoyé quand la pipeline
  est **dormante** (done/stopped/error) déclenche `_aimpact_analysis` en tâche
  de fond (prompt `feedback_impact`, persona `analyst`) : `update_story` (US
  **non implémentée** uniquement — todo/failed ; une US failed amendée repart en
  todo), `new_stories` (epic + US au format PO, itération courante →
  développables via « ▶ Continuer le build ») ou `none`. Le feedback reste de
  toute façon dans `state.feedback` pour l'analyste du cycle suivant.
- **Livraison (I2)** — persona `tech-writer` : `_adocument_phase` (cwd =
  workspace) écrit le **README.md du projet généré** ; automatique après chaque
  build si `AUTOSPEC_TECH_WRITER=1`, sinon à la demande (`POST /document`,
  tâche de fond). Export : `GET /export` (zip en mémoire, sans
  `.git`/`.venv`/état interne) et `POST /git-export` (`aexport_git` : repo
  garanti + `git add -A` + commit propre, renvoie le sha).
- **Watchdog fenêtre d'usage Claude (M2,
  `orchestrator/session_monitor.py`)** — actif uniquement pour le provider
  `claude` (hors démo, `AUTOSPEC_SESSION_MONITOR=1` par défaut). Le
  `_UsageTracker` intercepte chaque `AgentError` : si le message correspond à
  une **limite d'usage de session** (« usage limit reached »…), la pipeline
  s'arrête proprement (comme un stop budget) et `schedule_resume(at)` programme
  une **reprise automatique** — `at` = epoch embarqué dans l'erreur CLI, sinon
  fin du **bloc actif ccusage** (`ccusage blocks --json`), sinon
  `now + AUTOSPEC_RESUME_FALLBACK_MIN`. Le timer est persisté
  (`ProjectState.resume_at`) et **ré-armé par `recover_projects`** après un
  redémarrage (un `resume_at` passé tire immédiatement) ; à l'échéance,
  `aresume_build()` reprend les stories restantes (l'attempt de la story
  interrompue a été **remboursé**) ; si rien n'est buildable, simple message
  chat. Annulation : `POST /cancel-resume` / bouton ✕ de la bannière ⏰.
  Conformité : on **attend** le reset de la fenêtre souscrite (aucun
  contournement, pas de multiplexage de comptes).
- **Tests d'acceptance UI (E5)** — le PO marque chaque story d'un drapeau
  `ui`. Avec `AUTOSPEC_UI_TESTS=1` : le pyproject du workspace ajoute
  `pytest-playwright`, un marker `ui` et `addopts -m "not ui"` (la suite par
  défaut les exclut) ; le prompt Dev d'une story UI exige des tests Playwright
  **rejouables** dans `tests/ui/` (fixture `page`, clics/saisies, screenshots,
  assertions de rendu, fichiers déclarés dans `ui_test_files` → persistés sur
  `story.ui_tests`) ; après la suite pytest classique, `_arun_ui_tests`
  (`uv run pytest -m ui`, exit 5 « rien collecté » = vert) doit passer pour que
  la story soit DONE — sinon retry/échec comme un rouge normal.

---

### 5.10 Skills — compétences réutilisables pour QA/Dev (SK-1)

Plutôt que de gonfler les prompts, les agents QA/Dev s'appuient sur une
**bibliothèque de skills** : de petits fichiers `SKILL.md` (frontmatter
`name` + `description`, plus des `references/`) chargés **à la demande**
(divulgation progressive → prompt de base plus léger). La source est
`backend/autospec/skills/` (9 skills : `architecture` [archi backend en
**3 couches** façade → application → infrastructure, préfixe async `a`,
enregistrement], `db-entity-change`, `repo`/`service`/`endpoint-search-or-create`,
`error-code-management`, `test-generator`, `bdd-gherkin`, `skill-creator`) +
`skill-rules.json` (matrice de déclencheurs FR/EN) + un hook `skill-activation.py`.

**Livraison hybride** (`orchestrator/skills.py`) :
- **natif** — `seed_skills(ws)` copie la bibliothèque dans
  `workspace/<id>/.claude/skills/` (idempotent) ; le CLI Claude les découvre
  alors via son outil Skill natif. Le runner ajoute `--add-dir <ws>/.claude/skills`
  quand les skills sont actives ;
- **catalogue** — `catalog_block(role)` injecte un bloc compact
  (nom + description + « utile pour ») dans les prompts QA/Dev, **pour tous les
  providers** (OpenAI/Ollama qui n'ont pas d'outil Skill natif en profitent aussi).

Réglages : `AUTOSPEC_SKILLS` (interrupteur global, **OFF**) + `AUTOSPEC_SKILLS_QA`/
`_DEV` (par rôle) ; `settings.skills_for(role)` = global ET rôle (comme
`refine_for`). Quand c'est OFF, les prompts sont **strictement inchangés**.

### 5.11 Décomposition en sous-tâches parallèles (SK-2)

Pour mieux gérer la fenêtre de contexte d'une grosse story backend,
`AUTOSPEC_DECOMPOSE` (**OFF** par défaut) active un **mode décomposition** :
`_adecompose_story` demande à l'**architecte** (`prompts.decompose_story`) de
découper la story en **sous-tâches par couche** (entité → service → endpoint →
tests), mappées aux skills, **matérialisées en `Task`** sur la story (ids uniques,
`depends_on` remappés). `_abuild_phase` route alors la story via le **moteur de
worktrees parallèles existant** (`_abuild_phase_streams`, partagé avec les
streams) : chaque `Task` est construite par un **sous-agent focalisé dans son
propre worktree git** (contexte minimal = 1 couche + 1 skill), puis **fusionnée**
— la fusion + le rollup du statut de la story (`effective_status`) **agrègent** les
sous-résultats. Conservateur et non-fatal : moins de 2 sous-tâches ou une erreur
agent → la story est construite d'un bloc. En mode démo, `ScriptedRunner` renvoie
une décomposition cannée (`_DECOMPOSE`).

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

- `pyproject.toml` avec `pytest` + `pytest-bdd` + `pytest-json-report`
  (dependency-group `dev`) — ce dernier produit le rapport JSON consommé par la
  vérification « Trust but verify » (voir §5.3) ;
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

**Reprise après redémarrage (`recover_projects`, via lifespan).** Les pipelines
vivent en mémoire (`pipelines: dict[str, Pipeline]`), donc un redémarrage du
backend rendait tout projet persisté inactionnable : `GET` retombait sur
`load_state`, mais `chat`, `stop`, `pause`, `rebuild`, `force-done`, édition…
passent par le helper `_pipeline(pid)` qui ne regarde que le dict en mémoire →
**404**. Au démarrage de l'app, un gestionnaire **lifespan** (`@asynccontextmanager`,
passé à `FastAPI(lifespan=...)` — pas l'`on_event` déprécié) appelle
`recover_projects()`, qui, pour chaque état persisté pas déjà vivant,
réenregistre une `Pipeline` **dormante** (état chargé, API pilotable, mais
**aucune tâche de fond relancée** — pas de `start()`). Il **récupère** au passage
un run interrompu par le redémarrage : une phase active (`spec`/`analyze`/`plan`/
`build`) → `stopped`, les stories `in_progress` → `todo`, et les drapeaux
`running`/`paused` réinitialisés (le sous-processus de l'app a été tué). Si l'état
a changé, `pipeline._sync()` le persiste et le diffuse. Les projets restent ainsi
pilotables après un redémarrage.

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
| `POST` | `/api/projects` | crée un projet (`goal`, `name`, `auto_spec`, **`budget_usd`**, **`budget_tokens`**) et démarre la pipeline |
| `GET` | `/api/projects` | liste les projets (vivants + persistés) |
| `GET` | `/api/projects/{id}` | état complet d'un projet (live ou rechargé du disque) |
| `DELETE` | `/api/projects/{id}` | **supprime** un projet : stoppe la pipeline (`adispose`) et efface le workspace |
| `POST` | `/api/projects/{id}/chat` | envoie un message (réponse PM en phase spec, **consigne de build** en phase build/architect, sinon **feedback**) |
| `POST` | `/api/projects/{id}/spec-mode` | **change le mode de la phase spec** (corps `{mode}` : `interview`/`brainstorm` ; `Pipeline.aset_spec_mode`) ; **422** si mode invalide |
| `POST` | `/api/projects/{id}/budget` | **règle le budget** (corps `{budget_usd, budget_tokens}`, `0` = illimité ; `Pipeline.aset_budget`) |
| `POST` | `/api/projects/{id}/stop` | arrête la boucle |
| `POST` | `/api/projects/{id}/pause` | **met en pause** la pipeline (gate entre étapes) |
| `POST` | `/api/projects/{id}/resume` | **reprend** la pipeline |
| `POST` | `/api/projects/{id}/resume-build` | **continuer le build** d'un projet dormant : `aresume_build` rejoue la phase build sur les stories `todo`/`red` de l'itération courante en arrière-plan (phase `build` → `done`/`stopped`) ; **409** si la pipeline est déjà active ou s'il n'y a aucune story à construire |
| `POST` | `/api/projects/{id}/run` | lance le `main.py` du code généré |
| `POST` | `/api/projects/{id}/stop-app` | **arrête l'application générée** en cours d'exécution (no-op sûr sinon) |
| `POST` | `/api/projects/{id}/archive` | **archive** le projet (`ProjectState.archived=true`) — le masque par défaut sans le supprimer ; réponse `{ok: true}` ; **404** si inconnu |
| `POST` | `/api/projects/{id}/unarchive` | **désarchive** le projet (`ProjectState.archived=false`) ; réponse `{ok: true}` ; **404** si inconnu |
| `PATCH` | `/api/projects/{pid}/stories/{sid}` | **édite une US** (titre, description, Gherkin, priorité, critères d'acceptance — champs optionnels ; réécrit le `.feature` si le Gherkin change) |
| `POST` | `/api/projects/{pid}/stories` | **ajoute une US** à un epic (id `US-<n>` unique, itération courante, écrit son `.feature`) |
| `DELETE` | `/api/projects/{pid}/stories/{sid}` | **supprime une US** (la retire des `depends_on` des autres, efface son `.feature`) |
| `POST` | `/api/projects/{pid}/stories/reorder` | **repriorise** (kanban) un lot de stories (`{priorities: [{id, priority}]}`) |
| `POST` | `/api/projects/{pid}/stories/{sid}/rebuild` | **relance / rejoue** une US : réinitialise la story (`status=todo`, `attempts=0`, tests `nonexistent`) puis la (re)construit en arrière-plan (phase `build` → `done`/`stopped`) |
| `POST` | `/api/projects/{pid}/stories/{sid}/force-done` | **force terminé** : `status=done` et tous les tests planifiés à `green` (réponse incluant `state`) |
| `GET` | `/api/projects/{pid}/stories/{sid}/diff` | **diff git d'une story terminée** : `{ok, available, diff}` — chaque story terminée est commitée dans le repo git du workspace (commit `story <id> done`), et le diff est le `git show` de ce commit (tronqué au-delà de 200 000 caractères) ; `available=false` si aucun commit (git absent ou story non terminée) ; **404** si la story est inconnue |
| `GET` | `/api/projects/{pid}/files` | **arborescence du workspace** : `{files: [...]}` (chemins relatifs POSIX triés ; exclut `.git`/`__pycache__`/`.venv`/`node_modules`/`.pytest_cache`, `autospec-state.json`, `*.pyc`, rapports) |
| `GET` | `/api/projects/{pid}/files/raw?path=<relpath>` | **contenu d'un fichier** texte : `{path, content, truncated}` (UTF-8 tolérant, tronqué au-delà de 200 000 caractères) |
| `WS` | `/ws` | flux temps réel (`state` / `log` / `deleted`) |

> **Édition des specs.** Les quatre routes ci-dessus correspondent aux méthodes
> `Pipeline.aedit_story` / `aadd_story` / `adelete_story` / `areorder_stories`.
> Garde de sécurité : éditer ou supprimer une US au statut `in_progress` renvoie
> **409** ; une story ou un projet inconnu renvoie **404**. Chaque méthode mute
> l'état puis appelle `_sync()` (sauvegarde + diffusion WebSocket `state`), donc
> l'UI se rafraîchit automatiquement.

> **Actions par story depuis le board.** Les deux dernières routes correspondent
> aux méthodes `Pipeline.arebuild_story` et `Pipeline.aforce_done`.
> `arebuild_story` (tâche de fond `_arebuild_one`) sert à **Relancer** une story
> échouée ou à **Rejouer** une story terminée : elle renvoie **409** si la
> pipeline est active (phase ≠ `done`/`stopped`/`error`) ou si la story est
> `in_progress`, et **404** si la story est inconnue. `aforce_done` force la story
> à `done` et passe tous ses tests planifiés à `green` (réponse incluant `state`),
> renvoyant **409** si la story est `in_progress`.

> **Explorateur de code (lecture sécurisée).** `GET .../files` et
> `.../files/raw?path=` servent l'arborescence et le contenu du workspace généré
> à un explorateur côté front ; la lecture brute résout le chemin et vérifie
> qu'il reste sous le workspace (`is_relative_to`) — toute tentative de
> **path-traversal** renvoie **400**, un fichier absent **404**.

> **Archivage des projets.** `POST .../archive` et `.../unarchive` appellent
> `Pipeline.aset_archived(True/False)`, qui pose `ProjectState.archived` puis
> `_sync()` (sauvegarde + diffusion WebSocket `state`). C'est un masquage **non
> destructif** : `GET /api/projects` renvoie **tous** les projets (archivés
> inclus, avec le champ `archived` dans le payload) — c'est **le front qui masque
> les projets archivés par défaut**. Projet inconnu → **404**.

> **Persistance résiliente** : `load_state` migre les anciens formats (ex.
> `acceptance_criteria` en `list[str]` → objets) et ignore proprement un fichier
> d'état corrompu/incompatible, pour qu'il ne casse jamais la liste des projets.

Le **chat** est contextuel selon la phase (`Pipeline.asend_user_message`) :
- pendant la phase `spec`, le message **répond au PM** (file d'interview) ;
- pendant la phase `build` (ou `architect`), c'est une **consigne de build** :
  elle est rangée dans `state.build_guidance` et **injectée dans les prompts du
  Dev** (`dev_story`, donc aussi `dev_revise`) pour les **prochaines tentatives**
  de développement — un bloc « Consignes de l'utilisateur (à respecter en
  priorité) » est ajouté au prompt, sur le même patron que le contexte
  d'architecture. Les consignes sont **par itération** : `_abuild_phase` vide
  `state.build_guidance` à la fin du build pour qu'elles ne fuient pas vers
  l'itération suivante (l'analyse du cycle suivant s'appuie sur `feedback`, pas
  sur `build_guidance`) ;
- en dehors (ex. `done`), le message est rangé dans `state.feedback` et
  **consommé par l'analyste** au cycle suivant.

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

**Arrêt de l'application générée.** `POST .../stop-app` →
`Pipeline.astop_app` : si le sous-processus de l'app tourne encore
(`self._run_proc.poll() is None`), il est terminé via `terminate()` ; le thread
de streaming voit alors le process se terminer et appelle `_on_run_finished`,
qui remet `running=False` (et `_sync()`). Si aucune app ne tourne, c'est un
**no-op sûr** (simple log, jamais d'exception). `_on_run_finished` distingue
désormais trois cas pour une remontée d'erreur plus claire : échec de lancement
(`error`), terminaison normale (`code == 0`), et arrêt/échec
(`code != 0` → message renvoyant aux logs ci-dessus).

---

## 10. Le frontend (`frontend/src`)

React + Vite + TypeScript. Vite (port 5183) proxifie `/api` et `/ws` vers le
backend (port 8100). Composants :

- **`ProjectBar`** : **sélection** et **suppression** des projets (chips avec
  pastille de phase, bouton ✕ avec confirmation, bouton ＋ Nouveau).
- **`ProjectSetup`** : saisie de l'objectif + case **Auto-spec**.
- **`ChatPanel`** : conversation PM/feedback (rôles colorés).
- **`Board`** (reçoit la prop `projectId`) : EPICs → cartes US avec statut
  coloré, **badge de priorité kanban** `P1`-`P5`, détails dépliables. Chaque
  **critère d'acceptance est une ligne dépliable** avec son état (inexistant /
  rouge / vert, calculé par `criterionState`) ; en la dépliant on voit **la
  liste de ses tests d'acceptance** (avec leur état) **et le Gherkin associé**.
  Les US sont **éditables depuis le board** : chaque carte a un bouton **✏️
  Éditer** (formulaire inline — titre, description, priorité 1-5, liste éditable
  des critères d'acceptance et Gherkin) et **🗑 Supprimer** (avec confirmation) ;
  sous chaque epic, **+ Ajouter une US** ouvre un formulaire de création. La barre
  d'actions de chaque carte propose aussi des **boutons conditionnels selon le
  statut** : une story `failed` affiche **🔄 Relancer** + **✓ Forcer terminé**,
  une story `done` affiche **🔁 Rejouer**, et rien n'apparaît pour une story
  `in_progress`. Les appels passent par `api.ts` (`editStory`, `addStory`,
  `deleteStory`, `reorderStories`, `rebuildStory`, `forceDoneStory`) et l'UI se
  met à jour via l'événement WebSocket `state`.
- **`BacklogPanel`** : backlog priorisé de l'analyste (rang, V/C, statut,
  livrées).
- **`RunPanel`** : phase courante, bouton **▶ Lancer le projet**, **⏸ Pause /
  ▶ Reprendre**, **⏹ Stopper**, et logs streamés (filtrés sur le projet
  sélectionné).

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
| `AUTOSPEC_WORKSPACE_ROOT` | `./workspace` | racine des workspaces générés (isolé en e2e) |
| `AUTOSPEC_FAKE_AGENTS` | `0` | mode démo : `ScriptedRunner` + pytest court-circuité |
| `AUTOSPEC_DEMO_DELAY_S` | `0` | délai des agents scriptés (rend les transitions visibles) |
| `AUTOSPEC_ARCHITECTURE` | `0` | active la **phase Architecture optionnelle** (design injecté dans QA/Dev, OFF par défaut) |
| `AUTOSPEC_REFINE` | `0` | interrupteur **global** du harnais de raffinement (OFF par défaut) |
| `AUTOSPEC_REFINE_PO` | `1` | raffinement du plan PO (effectif seulement si le global est ON) |
| `AUTOSPEC_REFINE_DEV` | `1` | raffinement du code Dev (idem) |
| `AUTOSPEC_REFINE_MAX_ROUNDS` | `2` | cap dur d'allers-retours maker↔critic↔judge |
| `AUTOSPEC_REFINE_QUALITY_THRESHOLD` | `80` | seuil de score du juge (0-100) pour s'arrêter |
| `AUTOSPEC_AGENT_PROVIDER` | `claude` | provider d'agents (claude / codex / openai / openrouter / ollama / anthropic) |
| `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` | — / `…/api/v1` | clé + endpoint du provider **OpenRouter** (aussi `AUTOSPEC_OPENROUTER_*`) |
| `AUTOSPEC_OPENROUTER_MODEL` | (1er populaire) | modèle OpenRouter (sinon top-10 programmation chargé dynamiquement) |
| `AUTOSPEC_SKILLS` | `0` | active la **bibliothèque de skills** QA/Dev (§5.10) |
| `AUTOSPEC_SKILLS_QA` / `_DEV` | `1` / `1` | skills par rôle (effectif si le global est ON) |
| `AUTOSPEC_DECOMPOSE` | `0` | active la **décomposition en sous-tâches parallèles** (§5.11) |

---

## 12. Tests

### Tests backend (`backend/tests`)

131 tests, sans aucun appel LLM réel (grâce à `FakeRunner` / `ScriptedRunner`) :

- **`test_scheduler.py`** — dépendances, détection de cycles, sanitization,
  **ordre kanban**.
- **`test_runner.py`** — `extract_json` (prose, fences, objets imbriqués).
- **`test_models.py`** — **état d'un critère** (`criterion_state`) : inexistant,
  rouge si un test rouge, vert seulement si tous verts, story `done` ⇒ vert.
- **`test_pipeline.py`** — pipeline complète avec interview, écriture des
  `.feature`, blocage des dépendants en cas d'échec, **boucle auto-spec avec
  analyste**, priorité kanban de bout en bout, **plan de tests QA** (stocké,
  rattaché aux critères, injecté au Dev, non-fatal en cas d'échec), **états des
  tests dérivés du vrai rapport pytest** (`test_real_pytest_states_map_by_nodeid` :
  sous suite rouge, UT-1 dont le nodeid est `passed` devient vert et UT-2 dont le
  nodeid est `failed` devient rouge — le split vient purement du rapport réel),
  **pause/reprise** et stop débloquant une pause, feedback, **routage du chat**
  (un message pendant le `build` devient une consigne `build_guidance` injectée
  au Dev, hors build c'est du `feedback`) et **injection de la consigne dans le
  prompt Dev**, **invocation du raffinement PO** quand activé, **exposition des
  scores de raffinement à l'UI** (`plan_quality` stocké quand le raffinement est
  actif, `quality_score` des stories ; sentinelle -1 quand le raffinement est OFF),
  **continuer le build** d'un projet dormant (`aresume_build` rejoue le build sur
  les stories `todo`/`red` de l'itération ; **409** si pipeline active ou si aucune
  story à construire), **diff git par story** (`astory_diff` : commit `story <id>
  done` retrouvé puis `git show` exposé ; `available=false` sans commit ; `KeyError`
  si la story est inconnue), **observabilité tokens/coût** (`test_usage_is_accumulated` :
  `usage.agent_calls`/`cost_usd`/tokens cumulés sur les 4 appels PM/PO/QA/Dev ;
  `test_usage_zero_by_default` : `cost_usd=0` mais le compteur d'appels incrémente).
- **`test_pytest_report.py`** — `pytest_report.parse` : parsing nominal du
  json-report, fichier manquant → `{}`, fichier corrompu → `{}`.
- **`test_refine.py`** — **déterminisme du harnais de raffinement** : désactivé
  → artefact inchangé ; arrêt immédiat si le juge passe le seuil ; cap dur sur
  le nombre de tours ; arrêt anticipé au seuil ; **critique vide** ; **révision
  rejetée + rollback** ; **juge illisible traité comme arrêt**.
- **`test_api.py`** — création/complétion de projet, **suppression de projet**,
  arrêt pendant l'interview, validations (goal vide, projet inconnu), et
  **édition des specs** : édition titre + critères, ajout, suppression, reorder,
  **404** sur story inconnue, **409** sur story `in_progress` ; et **actions par
  story** : rebuild d'une story échouée, force-done, **409** si pipeline active,
  KeyError si story inconnue ; et **reprise après redémarrage** (`recover_projects`) :
  réenregistre les projets persistés comme pipelines dormantes en récupérant l'état
  interrompu (phase→`stopped`, story→`todo`, `running`/`paused` réinitialisés), rend
  un projet rechargé pilotable (plus de 404 sur `force-done`), et n'écrase pas un
  projet déjà vivant ; et **arrêt de l'app générée** (`stop-app`) : no-op sûr
  quand aucune app ne tourne (200 `{"ok": true}`), **404** sur projet inconnu ;
  et **archivage/désarchivage** (`archive`/`unarchive`) : `archived` passe à
  `true` puis `false`, **404** sur projet inconnu.
- **`test_scripted.py`** — le `ScriptedRunner` pilote toute la pipeline en mode
  démo (2 stories livrées, critères structurés).

```powershell
cd backend
uv run pytest
```

`green_pytest` (conftest) monkeypatche `_arun_pytest` pour simuler une suite
verte sans lancer de vrais sous-processus.

### Tests frontend (`frontend/src`)

**20 tests Vitest** (4 fichiers) : logique pure (`criterionState`), rendu du
`Board` et des panneaux.

```powershell
cd frontend
npm run test:unit
```

### Test e2e Playwright (`frontend/e2e`)

Un test bout-en-bout **hermétique** vérifie le lancement back+front et le
parcours complet dans la vraie UI. Il démarre le backend en **mode démo**
(`AUTOSPEC_FAKE_AGENTS=1`), qui **sert lui-même le frontend buildé** (donc `/api`
et `/ws` sont same-origin, sans proxy Vite), puis pilote un navigateur :
création de projet → pipeline qui peuple le board → **pause / reprise** →
dépliage d'un **critère d'acceptance** (état vert, tests + Gherkin) →
**suppression** du projet. Un `globalSetup` nettoie le workspace e2e avant chaque
run (hermétique).

```powershell
cd frontend
npm run test:e2e   # build le front puis lance Playwright (backend démo auto-démarré)
```

---

## 12b. Robustesse & sécurité

Une revue de code récente a durci plusieurs points.

**Sécurité.**
- **Anti path-traversal** dans `storage.workspace_dir` : les ids de projet
  viennent des URLs et alimentent un `rmtree` ; tout id contenant `..`, un
  séparateur de chemin ou `:` est **rejeté**.
- L'**app générée** (code non fiable) est lancée avec un **environnement
  minimal** : pas de fuite des secrets du process backend.
- **CORS** restreint aux **origines locales**.

**Robustesse.**
- `config.py` **tolère les variables d'env malformées** (plus de crash à
  l'import) : helpers `_env_bool` / `_env_int`, parsing booléen cohérent.
- Le **runner** gère `result:null`, `is_error`, un payload non-`dict` et le **CLI
  absent** (→ `AgentError`) ; `extract_json` ne lève **plus jamais**
  `JSONDecodeError`.
- Le **scheduler** ne casse que les dépendances **réellement cycliques**.
- Des **validateurs Pydantic clampent les scores 1-5** : un état legacy ou une
  sortie LLM hors-bornes ne fait plus échouer le chargement.
- L'**écriture d'état est atomique** (fichier temporaire + `rename`).

---

## 13. Points d'extension

| Besoin | Où agir |
|---|---|
| Changer de backend LLM (SDK Anthropic, autre provider) | nouvelle classe `AgentRunner` + `server.set_runner(...)` |
| Modifier le comportement d'un agent | persona BMAD dans `_bmad/bmm/agents/` ou prompt dans `agents/prompts.py` |
| Ajouter une étape au pipeline | nouvelle phase dans `PipelinePhase` + méthode `_a…_phase` dans `pipeline.py` |
| Changer la stratégie d'ordonnancement | fonctions pures de `scheduler.py` |
| Réorganiser le backlog à la main (drag & drop) | non implémenté — actuellement géré via le feedback chat repris par l'analyste |
| Vérifier individuellement chaque test planifié | implémenté : les outcomes viennent du **vrai rapport pytest** (`pytest-json-report` → `pytest_report.parse`), mappés par les nodeids déclarés par le Dev (`_apply_test_states`, voir §5.3) |
| Durcir les permissions des agents | `AUTOSPEC_PERMISSION_MODE` |

---

## 14. Résumé en une phrase

Autospec orchestre de façon **déterministe** une équipe d'**agents BMAD exécutés
via le CLI Claude Code**, où chaque agent a une responsabilité unique (décider,
spécifier, planifier, **concevoir les tests outside-in**, coder en BDD/TDD), où
l'orchestrateur **revérifie lui-même** chaque livraison par les tests, et où une
**boucle auto-spec** pilotée par un analyste fait progresser le produit en
continu — le tout visualisé en temps réel dans un board kanban.
