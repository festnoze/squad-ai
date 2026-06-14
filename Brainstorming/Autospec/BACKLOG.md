# Autospec — Backlog

Backlog vivant, priorisé (valeur V / complexité C, 1-5). Mis à jour entre chaque
itération du loop de développement. Règle de délégation : tâches de complexité
faible/moyenne → subagents Opus ; orchestration/intégration/conception complexe →
modèle courant.

## 🚀 Extension produit (demandée) — ✅ livrée

| # | Feature | V/C | État |
|---|---------|-----|------|
| E1 | **Phase spec enrichie** — facilitation socratique par dimensions + mode 🧠 Brainstorming (persona analyste BMAD, divergence→convergence pour re-questionner le besoin) ; endpoint `/spec-mode` + toggle UI | 4/3 | ✅ tests + e2e |
| E2 | **Analyse d'impact d'un feedback** — feedback reçu pipeline dormante → agent d'impact (`feedback_impact`) qui décide : `update_story` (US non implémentée, statut todo/failed — une US failed amendée repart en todo), `new_stories` (nouvel Epic/US au format PO, buildables via « Continuer le build ») ou `none` | 4/4 | ✅ tests |
| E3 | **Proposition de composants au démarrage** — agent solutionneur (`components_proposal`, persona architect) après le brief : backend FastAPI + frontend React par défaut, infra optionnelle (PostgreSQL/Redis) ; `ProjectState.components` ; obligatoires pré-approuvés, optionnels à valider ; édition via `PUT /components` + panneau UI 🧱 ; env-gated `AUTOSPEC_COMPONENTS` | 4/4 | ✅ tests |
| E4 | **Exécuteur de setup** — `setup_exec` crée réellement les composants approuvés : `backend/` (pyproject FastAPI + app), `frontend/` (package.json React+Vite), `docker-compose.yml` (db/cache) ; idempotent (jamais d'écrasement) ; install réel (`uv sync`/`npm install`) derrière `AUTOSPEC_SETUP_INSTALL` (démo-safe) ; `POST /components/setup` | 4/5 | ✅ tests |
| E5 | **Tests d'acceptance UI Playwright** — le PO marque les US visuelles (`ui: true`) ; en mode `AUTOSPEC_UI_TESTS` le Dev écrit des tests Playwright **rejouables** dans `tests/ui/` (marker pytest `ui`, screenshots + assertions de rendu, exclus de la suite par défaut), l'orchestrateur exige `uv run pytest -m ui` vert en plus de la suite pytest-bdd avant de marquer la story done ; `story.ui_tests` versionnés dans le workspace | 5/5 | ✅ tests |
| I1 | **Budget de tokens/coût par projet + arrêt automatique** — `budget_usd`/`budget_tokens` à la création + endpoint `/budget` ; `_enforce_budget` au point de contrôle stoppe proprement auto-spec/build quand le budget est atteint ; saisie au setup + jauge « 💸 $X / $Y » | 5/2 | ✅ tests + e2e |
| I2 | **Livraison du produit généré : doc auto + export** — (a) agent **tech-writer** (persona dédiée, cwd = workspace) qui produit le README du projet généré (présentation, lancement uv, tests, archi) ; auto après build si `AUTOSPEC_TECH_WRITER=1`, sinon à la demande (`POST /document`, bouton 📘) ; (b) export : `GET /export` (zip sans .git/.venv/état) + `POST /git-export` (commit propre), boutons ⬇/🔀 | 4/3 | ✅ tests + e2e |
| M1 | **Modèle / provider configurable** — `make_runner()` : **Claude** (harness CLI), **OpenAI** et **Ollama** via **LangChain** (`langchain-openai`/`langchain-ollama`), sessions rejouées en mémoire + protocole d'outils JSON borné (write/read fichiers, confiné au workspace) pour les agents Dev ; coût estimé par prix/1M tokens (OpenAI) ; sélection env `AUTOSPEC_AGENT_PROVIDER` + endpoint `GET/POST /api/provider` (bascule à chaud des pipelines) + sélecteur 🤖 dans le header | 4/3 | ✅ tests |
| M2 | **Ordonnancement aligné sur la fenêtre d'usage Claude** — watchdog `session_monitor` (provider claude uniquement) : un appel agent qui échoue sur « usage limit reached » déclenche un **arrêt propre** + **reprise auto programmée** quand une session fraîche s'ouvre. Heure de reset : epoch de l'erreur CLI → bloc actif **ccusage** (`ccusage blocks --json`) → fallback `AUTOSPEC_RESUME_FALLBACK_MIN`. Timer persisté (`ProjectState.resume_at`), **ré-armé au restart** (recover_projects) ; l'attempt de la story interrompue est remboursé ; bannière ⏰ + annulation (`POST /cancel-resume`). **Conformité** : ordonnancement légitime du quota souscrit (on attend le reset, aucun contournement ni multiplexage). | 3/3 | ✅ tests |
| U1 | **Accueil & multi-projets actifs** — (a) la création est une **popup modale** : ouverte d'office si aucun projet (non fermable), sinon accès direct à la sélection (modale fermable via ✕/backdrop, « ＋ Nouveau ») ; (b) chips `ProjectBar` : **dot pulsant** quand des agents travaillent, **▶** (reprendre pause / resume-build) et **⏹** (stopper) par projet, progression `done/total` ; (c) plusieurs pipelines pilotées/surveillées en parallèle depuis la barre | 4/3 | ✅ tests + e2e |
| E6 | **Évaluateur de produit (boucle fermée)** — après chaque itération livrée (avant la phase `analyze`), un agent `evaluator` (persona QA/analyste) **exerce réellement le produit généré** : lancement via le mécanisme run-app existant, exploration des flux principaux par l'API et/ou Playwright (plomberie E5), et production de **findings structurés** (bugs passés sous pytest, intégrations cassées entre stories, frictions UX, manques). Les findings sont **injectés comme feedback dans la pipeline `feedback_impact` (E2)** — qui sait déjà amender une US, créer Epic/US ou écarter — pour que l'Analyste priorise des **preuves** et plus seulement des hypothèses. Env-gated `AUTOSPEC_EVALUATOR` ; findings visibles dans l'UI (panneau feedback / backlog analyste). Point d'attention : exécution de l'app non fiable (mitigation env minimal en place ; sandbox toujours différé). | 5/4 | ✅ tests + e2e |
| E7 | **Rétrospective d'usine (méta-apprentissage)** — un agent `retro` tourne au `_checkpoint` entre itérations et **consomme les signaux déjà collectés** (usage/coût par story, tentatives Dev, rouge→vert, tours et scores de raffinement, messages d'échec) pour produire : (a) des **leçons par projet** persistées dans `ProjectState.lessons` (survivent au redémarrage, composent d'itération en itération) et **injectées dans les prompts QA/Dev** (comme `build_guidance`, mais générées et durables) ; (b) des **recommandations de réglage** (rounds de raffinement, parallélisme, dépendance chroniquement en échec) remontées dans l'UI. Option : leçons partageables inter-projets. Env-gated `AUTOSPEC_RETRO`. | 4/3 | ✅ tests + e2e |

## ✅ Livré

| # | Item | Vérifié |
|---|------|---------|
| 0 | Harnais de raffinement (maker → critic → judge, arrêt déterministe seuil+cap, ReAct, env-gated) | tests + smoke |
| 1 | Édition des specs depuis le front (US/critères/Gherkin, ajout/suppression/repriorisation) | tests + e2e |
| 2 | États de tests réels depuis pytest (json-report, mapping nodeids) | tests + smoke réel |
| 3 | Actions par story (relancer/rejouer/forcer terminé) | tests + e2e |
| 4 | Reprise après redémarrage (recover_projects via lifespan) | tests + smoke boot |
| 5 | Visualiseur de code du workspace (arbre + contenu, anti path-traversal) | tests + e2e |
| 6 | Fix lancement app générée (stop-app, remontée d'erreur) | tests + smoke réel |
| 7 | Phase Architecture (BMAD `architect`, design injecté QA/Dev, env-gated) | tests + smoke |
| 8 | Guidance en cours de build (chat → `build_guidance` → prompts Dev) | tests + e2e |
| 9 | Tests unitaires frontend (Vitest, 7 tests) + CI GitHub Actions (back/front/e2e) | vitest + e2e + YAML valide |
| 10 | Afficher architecture + scores de raffinement dans l'UI (`plan_quality`/`quality_score`, panneau + badges) | tests + e2e |
| 11 | Action « continuer le build » d'un projet récupéré/dormant (`resume-build` + bouton) | tests + e2e |
| 12 | Vue diff par story (commit git « story done » + `GET .../diff` + overlay diff coloré ; fix suppression workspace git) | tests + e2e |
| 13 | Réorganisation drag-&-drop des stories sur le board (tri par priorité + poignée → `reorder`) | unit + e2e |
| 14 | Observabilité tokens/coût (`AgentResult` usage + `_UsageTracker` → `ProjectState.usage` + indicateur 💸) | tests + e2e |
| 15 | Archivage des projets (`archived` + endpoints archive/unarchive + UI bascule « Archivés ») | tests + e2e |
| 16 | Workflow CI racine monorepo (filtre paths + chemins préfixés) | YAML valide |
| 17 | Navigation hiérarchique du board (drill-down épics → epic → US + fil d'Ariane, deps d'epic dérivées des US, remplace l'expansion en drop-down) | unit Vitest |

## 🔎 Audit multi-agents (workflow `autospec-test-audit`)

67 agents en parallèle (8 dimensions + vérification adversariale) → **50 findings confirmés** (9 high, 21 medium, 20 low). Rapport complet : voir l'output du run `ww59ppihi`.

### ✅ Corrigés ce tour (high + mediums clés)
| Catégorie | Fix |
|---|---|
| Concurrence (high) | `_build_lock` sérialise la section workspace (écriture dev + pytest + commit + raffinement) — fini les pytest sur arbre mixte et les commits/diff pollués entre workers parallèles |
| Concurrence (high) | `git reset/clean` du raffinement ne tourne plus en parallèle d'un autre worker (même lock) |
| Concurrence (high) | TOCTOU `arebuild_story`/`aresume_build` : garde sur `_task` en cours + passage de phase à BUILD **synchrone** avant la tâche |
| Sécurité (high) | CORS restreint aux origines locales (plus de `*`) |
| Récupération (high+med) | `recover_projects` gère la phase ARCHITECT + remet les stories GREEN à TODO ; `/run` rejette aussi BUILD |
| Robustesse (med) | `.gitignore` dans le workspace (git n'ingère plus `.venv` ; `clean -fd` ne la détruit plus) ; `extract_json` ignore les accolades dans les chaînes ; `save_state` atomique (temp+rename) + log des chargements échoués |
| Frontend (high+med) | WS : `JSON.parse` protégé, **resync** (re-fetch) à la reconnexion, anti-résurrection d'un projet supprimé |

### ✅ Tranches de remédiation (post-audit, une à la fois)
- **Tranche 1 — couverture backend** : +12 tests (API : /chat /pause /resume /diff /rebuild, troncature `aread_file`, recover SPEC/ANALYZE/PLAN ; pipeline : erreur fatale `_alifecycle`→ERROR, fallbacks `_apply_test_states`, retry rouge→vert). Suite **102 tests**. Fix du flake de timing (timeout des helpers 5 s → 20 s).
- **Tranche 2 — couverture frontend** : +13 tests Vitest (**20**) — `RunPanel` (boutons conditionnels, usage-meter) et `App` (WS upsert/deleted + anti-résurrection). Fix : bouton « Lancer » désactivé aussi en phase `build` (cohérent avec la garde backend).
- **Tranche 3 — sécurité & robustesse backend** : l'app générée (non fiable) tourne avec un **env minimal** (plus de fuite de secrets) ; `_force_delete_workspace` gère les fichiers verrouillés → **409** au lieu de 500.

### ⏳ Différé (design / infra, faible valeur ou risque élevé)
- **Sécurité (design)** : `bypassPermissions` + exécution non sandboxée du code généré (`uv run pytest`/`python main.py`) → nécessite un vrai sandbox (gros chantier infra).
- **Robustesse (marginal)** : `adispose` ne tue pas le sous-processus pytest en vol (`to_thread` non annulable) — impact réduit depuis que la suppression renvoie 409 + retry sur fichier verrouillé.
- **Raffinement (par design)** : juge illisible = PASS borné par le cap de tours ; score défaut = seuil — choix déterministes assumés.
- **Frontend (limitation)** : priorité kanban 1-5 → au-delà de 5 stories le drag-&-drop ne distingue pas l'ordre (changer la sémantique de `priority` rippler ait sur PO/UI).

## 🐛 Bugs à corriger

| # | Bug | V/C |
|---|-----|-----|
| BUG1 ✅ | **Encodage Windows de l'app générée (crash + mojibake)** — bug en deux couches symétriques. **(1) Crash `UnicodeEncodeError`** : un `main.py` généré qui `print` un caractère non-ASCII (ex. `→` « → ») plante en code 1 car le `stdout` du Python enfant utilise par défaut **cp1252** (déduit de la locale) sous Windows. **(2) Mojibake** (`systï¿½me`, `franï¿½ais`, `ï¿½uf`) : l'enfant écrit ses accents en cp1252 mais Autospec lit le flux du sous-processus en **utf-8** (`encoding="utf-8", errors="replace"`) → désaccord d'encodage. **Angle mort** : le chemin run-app/évaluateur (E6) ne l'exerce pas (en mode `AUTOSPEC_FAKE_AGENTS`, `_aexercise_product` court-circuite l'exécution réelle ; aucun vrai `main.py` non-ASCII lancé sous Playwright). **Fix** : forcer le mode UTF-8 du Python enfant en ajoutant `PYTHONUTF8=1` et `PYTHONIOENCODING=utf-8` au dict retourné par `_minimal_env()` dans `backend/autospec/orchestrator/pipeline.py` (filtré via `_SAFE_ENV_KEYS`). Résout d'un coup le crash (encode « → » en utf-8) **et** le mojibake (enfant écrit en utf-8, cohérent avec la lecture Autospec). Couvre les deux usages : `_aexercise_product` (E6) **et** `_stream_run_output` (bouton « Lancer le projet »). Défense en profondeur optionnelle : demander au Dev/tech-writer un `sys.stdout.reconfigure(encoding="utf-8")` en tête de `main.py` (mais le fix env est plus sûr, indépendant du code généré). **Non-régression** : ajouter un test qui lance réellement un `main.py` non-ASCII sous Playwright/évaluateur. **✅ CORRIGÉ** : `PYTHONUTF8=1`+`PYTHONIOENCODING=utf-8` dans `_minimal_env`, test `test_generated_app_encoding.py`. | 5/2 |

| BUG2 ✅ | **Vite WS proxy `connect ETIMEDOUT 127.0.0.1:8100` au lancement du front** (×2) — au démarrage, le proxy WS de Vite (`/ws`) ouvre la connexion vers le backend mais celui-ci, **event loop momentanément bloqué par des I/O synchrones** (écritures `save_state` + `time.sleep` de retry pendant un build actif ; `recover_projects`/`list_states` non offloadés au boot), n'`accept()` pas le socket à temps → `ETIMEDOUT` (port en écoute mais accept *starved*, ≠ `ECONNREFUSED`). Même famille que le fix #1 (offload de `list_states` dans `GET /api/projects`, déjà fait) mais sur le **chemin WS / écriture**. **Fix** : finir d'extraire les I/O fichier synchrones de l'event loop — `save_state` via `asyncio.to_thread` ou file d'écriture (supprimer le `time.sleep` bloquant du chemin async), et offloader `recover_projects` au lifespan. Le client WS se reconnecte déjà (auto-resync) donc ça s'auto-répare, mais l'erreur pollue les logs et retarde la 1re synchro. **Non-régression** : test qui martèle `GET /api/projects` + connexion WS pendant des `_sync` répétés sans stall. **✅ CORRIGÉ (boot)** : recovery en tâche de fond (`_arecover_projects`, `list_states` offloadé) → uvicorn accepte immédiatement ; 2 tests. **✅ CORRIGÉ (chemin écriture, 2e passe)** : le vrai déclencheur restant était `_sync()` qui appelait `save_state()` **en synchrone sur l'event loop** à chaque changement d'état pendant un build (I/O fichier + `time.sleep` de retry sur verrou Windows) → accept *starved* → `ETIMEDOUT` du proxy Vite (reproduit en live : build « chat-eat » piloté au navigateur via le proxy 5183→8100). Fix : `save_state` scindé (`save_state_payload` = écriture atomique seule) ; `Pipeline._persist` sérialise le JSON sur la loop (snapshot anti-race) puis **offload l'écriture** sur un `ThreadPoolExecutor(max_workers=1)` (FIFO, jamais d'écrasement d'un snapshot plus récent) ; écriture inline quand aucune loop ne tourne (recovery sync / tests). 2 tests (`test_sync_does_not_block_the_event_loop`, `test_sync_writes_inline_without_a_running_loop`). | 5/2 |

## 💡 Idées d'évolution (proposées, non planifiées)

Issues d'une revue du produit actuel (architecture mature : pipeline complète,
multi-provider, budget, M2 watchdog, E6/E7, export). Conçues pour réutiliser les
patterns en place (persona + phase env-gated + `Finding` + `_UsageTracker` +
endpoint). Priorité par valeur V / complexité C (1-5). **Top 3 : S1, Q1, O1.**

### 🔒 Durcissement & confiance
| # | Idée | V/C |
|---|------|-----|
| S1 ✅ | **Phase de revue sécurité & supply-chain** — agent `security-reviewer` après le build (comme E6) : scan du code généré + `pip-audit`/`npm audit` des dépendances → réémission en `Finding` routés vers `feedback_impact`. Réutilise le pattern E6, comble l'angle mort « code untrusted jamais audité ». **✅ LIVRÉ** : persona `security-reviewer`, `_asecurity_phase` (audit `pip-audit`/`npm audit` + agent → `Finding` kind=security → pipeline d'impact), endpoint `POST /security-review`, env `AUTOSPEC_SECURITY_REVIEW`, 6 tests. | 5/3 |
| Q1 ✅ | **Mutation testing** — `mutmut`/`cosmic-ray` après le passage au vert pour vérifier que les tests *contraignent* vraiment le comportement (un agent peut écrire des assertions vacues). Expose un « score de robustesse des tests » par story, à côté du `quality_score`. Durcit la promesse cœur TDD/BDD. **✅ LIVRÉ** : moteur de mutation AST intégré `orchestrator/mutation.py` (sans dépendance externe), `_arun_mutation_test` (score = taux de mutants tués, env `AUTOSPEC_MUTATION`), champ `UserStory.mutation_score`, badge 🧬 dans le board, 7 tests. | 5/4 |
| Q2 ✅ | **Gate de couverture** — `pytest-cov`, seuil bloquant pour passer `done`, badge couverture par story. **✅ LIVRÉ** : `_arun_coverage` (`pytest --cov`, env `AUTOSPEC_COVERAGE`), champ `UserStory.coverage_score`, gate optionnel `AUTOSPEC_COVERAGE_GATE` (rejette une story sous le seuil), badge 📊, 3 tests. | 3/2 |
| R1 ✅ | **Vrai sandbox Docker** — le gros différé : exécuter `pytest`/`main.py` en conteneur (env minimal déjà en place) → **✅ LIVRÉ (incrément)** : module `sandbox.py` (`docker_run_cmd` : `docker run --rm --network none -v ws:/app`), config `AUTOSPEC_SANDBOX`/`_IMAGE`/`DOCKER_CMD`, `_maybe_sandbox` wrappe l'exécution non fiable (`_aexercise_product`), 4 tests. (Image avec uv à fournir pour un run réel.) | 4/5 |
| R2 ✅ | **Snapshots d'itération + rollback** — commit par itération (git workspace existe), « revenir à l'itération N » ; flag anti-régression. **✅ LIVRÉ** : commit `iteration N snapshot` par itération + `arollback`/`aiterations` + endpoints `GET /iterations` `POST /rollback` (bouton ⏪) ; module `regression.py` (`find_regressions`) + `green_tests`/`regressions` sur l'état + bannière UI + notify ; 6 tests. | 4/3 |

### 💸 Coût & modèles
| # | Idée | V/C |
|---|------|-----|
| M3 ✅ | **Routage modèle par phase** — modèle bon marché pour interview/brainstorm, modèle fort pour Dev/raffinement. `make_runner()` abstrait déjà les providers ; manque une map phase→modèle. **✅ LIVRÉ** : param `model` ajouté à tout le Protocol runner (Claude/Fake/Scripted/LangChain), `model_for_phase` (env `AUTOSPEC_MODEL_<PHASE>` → fallback `claude_model`), routage dans `_UsageTracker.arun`, 3 tests. | 4/3 |
| M4 ✅ | **Provider Anthropic API direct** (en plus du CLI harness) — usage hors poste dev (cron, cloud) sans dépendre du CLI. **✅ LIVRÉ** : `AnthropicRunner` (langchain-anthropic, `_build_model`+`_cost`), ajouté à `PROVIDERS`/`make_runner`/`provider_model` (donc au sélecteur 🤖), config `AUTOSPEC_ANTHROPIC_*`, 4 tests. | 3/3 |
| O2 ✅ | **Prévision de coût avant lancement** — estimer le coût d'une itération depuis l'historique (E7 collecte déjà tentatives/coût/story) avant de démarrer le build. **✅ LIVRÉ** : module `forecast.py` (`forecast_iteration_cost` : coût/story historique × stories restantes, fallback moyenne inter-projets), endpoint `GET /forecast`, estimation 📈 dans RunPanel, 3 tests. | 3/3 |

### 🚀 Entrée & sortie (élargir le marché)
| # | Idée | V/C |
|---|------|-----|
| B1 ✅ | **Mode brownfield** — pointer Autospec sur un repo existant pour *ajouter* des features au lieu du greenfield. **✅ LIVRÉ (incrément)** : module `brownfield.py` (`seed_workspace_from` copie le repo existant dans le workspace en excluant .git/.venv/node_modules ; `summarize_repo` produit un résumé d'arbo borné), `_abrownfield_init` au lifecycle injecte le résumé dans `architecture` (donc dans les prompts QA/Dev), champ `brownfield_path` + input UI, 5 tests. | 5/5 |
| D1 ✅ | **Déploiement du produit généré** — Dockerfile + CI générés pour le projet créé, **✅ LIVRÉ (incrément)** : module `deploy.py` génère Dockerfile + `.dockerignore` + workflow CI GitHub Actions dans le workspace (idempotent), `adeploy` + endpoint `POST /deploy` + bouton 🚀, 4 tests. (Le `docker build`/run effectif reste lié au sandbox R1.) | 4/4 |
| I3 ✅ | **Import de specs** — ingérer un doc comme brief initial. **✅ LIVRÉ (incrément)** : `spec_import.py` (`parse_spec_import`), champ `brief` à la création qui seed l'état et court-circuite l'interview PM vers le plan (`_aspec_phase`), textarea d'import dans ProjectSetup, 3 tests. (Jira/MCP et image OCR restent hors périmètre.) | 3/4 |

### 📊 Pilotage de l'usine
| # | Idée | V/C |
|---|------|-----|
| O1 ✅ | **Tracing Langfuse de chaque appel agent** — `_UsageTracker.arun` est le seam : un span par appel (persona, phase, story, tokens, coût, score critic/judge). Observabilité réelle de l'usine sans toucher au flux métier. **✅ LIVRÉ** : module `observability.py` (env `AUTOSPEC_LANGFUSE`, import paresseux, no-op gracieux), `trace_agent_call` branché dans `_UsageTracker.arun` (phase/projet/modèle/tokens/coût/durée), 3 tests. | 4/2 |
| F1 ✅ | **Bibliothèque de leçons inter-projets** — promouvoir les leçons E7 en librairie globale injectée dans tout nouveau projet. **✅ LIVRÉ** : module `orchestrator/lessons.py` (store `autospec-lessons.json`, dédup + cap, écriture atomique), alimenté par la rétro E7, `_effective_lessons` (projet + global) injecté aux 3 sites Dev/QA, env `AUTOSPEC_SHARED_LESSONS`, 5 tests. | 4/3 |
| U2 ✅ | **Dashboard factory multi-projets** — taux de succès, coût/story, tentatives moyennes, agrégés sur tous les projets. **✅ LIVRÉ** : module `metrics.py` (`compute_metrics` : taux de succès, coût/story, tentatives moy., qualité/mutation/couverture moy., findings, régressions), endpoint `GET /api/metrics`, modale 📊 Dashboard, 2 tests. | 4/3 |
| U3 ✅ | **Notifications push** — budget atteint, build terminé, erreur, reprise programmée (M2). **✅ LIVRÉ** : `_notify` sur le bus + 4 jalons backend ; toasts in-app + `Notification` navigateur (permission demandée au montage) ; 2 tests backend + 1 Vitest. | 3/1 |
| U4 ✅ | **Gates d'approbation granulaires** — valider plan / architecture *avant* le build (HITL ciblé), pas seulement la pause globale. **✅ LIVRÉ** : `_aapproval_gate` (asyncio.Event) bloque avant le build, `aapprove`/`areject` + endpoints `POST /approve` `/reject`, champ `awaiting_approval`, bannière UI dans RunPanel, env `AUTOSPEC_APPROVAL_GATES`, 4 tests. | 3/2 |

> Backlog des 16 features : épuisé. Extension produit (E1→E7 + I1/I2 + M1/M2 + U1)
> **épuisée**. Idées d'évolution (S1, Q1/Q2, R1/R2, M3/M4, O1/O2, B1, D1, I3, F1,
> U2/U3/U4) **livrées**. Bugs BUG1/BUG2 **corrigés**. Suite backend **261 tests**,
> **33 tests Vitest**, et un **scénario e2e Playwright exhaustif**
> (`autospec.spec.ts`) qui exerce TOUTES les features en une passe (composants+
> setup, budget, architecture+raffinement, board hiérarchique, pause/reprise,
> évaluateur E6, impact E2, rétrospective E7, continuer-le-build, édition, diff,
> code-viewer, doc/zip/commit, provider, multi-projets+archivage).
> Remédiation d'audit : 3 tranches traitées ; reste différé (design/infra).
> **Aucune feature en attente.**
>
> Bug corrigé pendant la passe e2e : `save_state` (écriture atomique temp→rename)
> plantait toute la pipeline sur un verrou fichier transitoire Windows (WinError 5
> — antivirus/indexeur/lecteur concurrent) → désormais **retry + meilleur effort**
> (un checkpoint manqué est rattrapé au `_sync` suivant, plus de crash). Isolation
> e2e : `global-setup` efface le bit lecture-seule des objets git avant le wipe.
>
> Passe de clôture (vérification finale) :
> - **M2 — course à la reprise auto corrigée** : `_aresume_timer` attend la fin
>   propre de la tâche lifecycle (phase quitte BUILD) avant d'appeler
>   `aresume_build`, sinon une fenêtre de reset très proche (bloc ccusage court /
>   epoch à quelques secondes) faisait rejeter la reprise par la garde
>   pipeline-active. Test `test_usage_limit_stops_then_auto_resumes` rendu
>   déterministe (epoch lointain → STOPPED durable observable, puis reprise
>   déclenchée explicitement) — fini le flake de timing sous charge.
> - **e2e aligné sur le board hiérarchique (item 17)** : navigation drill-down
>   (épics → US d'un epic → détail) via le fil d'Ariane ; l'assertion d'impact E2
>   compte désormais les **epics** « Retours utilisateur » (1→2), chaque analyse
>   d'impact planifiant un nouvel epic de feedback.
