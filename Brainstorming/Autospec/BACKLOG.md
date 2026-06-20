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
| 18 | Sélecteur de projet (dropdown 🗂 en tête de `ProjectBar` : option « badge phase + nom + done/total + phase », reflète/commute le projet actif, inclut toujours le projet courant même archivé/masqué ; lisible quand les chips débordent) | unit Vitest + smoke navigateur |
| 19 | Avancement & mise en valeur des epics sur le board (barre de progression + compteur done/en cours/échec par carte epic, bordure colorée par état ; US `in_progress` → halo `dev-glow` animé + spinner sur la story ET son epic, à la grille et dans l'en-tête du détail ; fallback `prefers-reduced-motion`) | unit Vitest (4) + smoke navigateur (état `working` capturé en live) |
| 20 | Relance groupée des échecs (`Pipeline.aretry_failed` réinitialise toutes les US `failed` de l'itération → TODO et relance le build via le run de resume-build ; `POST /api/projects/{id}/retry-failed` ; bouton « 🔄 Relancer les échecs (N) » dans RunPanel quand la pipeline est dormante et qu'au moins une US a échoué) | 3 tests pipeline + 3 Vitest + e2e vert |
| 21 | Lancement de l'app avec arguments CLI (`arun_app(args)` + `toolchain.run_command(lang, args)` — `--` pour cargo ; `POST /run` body `{args}` optionnel rétro-compatible ; champ « arguments (ex. auth-screen)… » dans RunPanel). Corrige le cas d'une app CLI à sous-commandes qui n'affichait que son usage quand lancée à vide. | unit toolchain + 2 Vitest |
| 22 | Relance d'une US bloquée (fix) — le bouton « 🔄 Relancer » (+ « ✓ Forcer terminé ») de la StoryDetail n'apparaissait que pour le statut `failed` ; une US `todo`/`red` restée bloquée avec une erreur (ex. orpheline d'une itération passée) n'avait AUCUN moyen d'être relancée. Désormais affichés pour toute story « bloquée » (`failed`/`red`/`todo` déjà tentée ou en erreur) quand la pipeline est dormante (`done`/`stopped`/`error`). Backend `arebuild_story` déjà compatible (toute story non `in_progress`, toutes itérations). | 2 Vitest |
| 23 | Cause racine : clôture propre d'itération — `_fail_stranded_stories` marque `failed` toute story d'une itération qui se termine restée tentée-mais-non-finie (`todo`/`red`/`in_progress` avec `attempts>0` ou `last_error`), appelé dans `_anext_feature_phase` avant l'incrément d'itération. Plus de `todo` orpheline ambiguë dans une itération passée ; statut clair + déjà couvert par « Relancer les échecs ». Les `todo` jamais tentées et les autres itérations sont laissées intactes. | 1 test pipeline + auto-spec vert |
| 24 | **Assistance au brainstorming pour idées vagues (B-IDEA)** — à la création, un agent analyste (BMAD) évalue la MATURITÉ de l'objectif : `structured` (brief clair → spécification directe) vs `vague`. Pour une idée vague : (a) hors auto-spec → on **propose** une session de brainstorming dans le chat (boutons « 🧠 Oui, on explore ensemble » / « 🤖 Non, affine en autonomie ») ; (b) si l'utilisateur **accepte** → mode `brainstorm` interactif (l'analyste pose des questions, l'utilisateur répond) ; (c) si l'utilisateur **refuse** (ou auto-spec actif) → **brainstorming autonome** où l'IA joue le porteur du projet et répond elle-même aux questions de l'analyste pendant N tours (`brainstorm_auto_rounds`), avant la synthèse du brief. **BMAD choisit lui-même les techniques** les plus adaptées au sujet, parmi le catalogue `brain-methods.csv` (61 méthodes) injecté dans le prompt. Backend : `prompts.assess_idea`/`brainstorm_auto_answer`/`pm_brainstorm(force_brief)` + `_brainstorming_catalog`, `Pipeline._abrainstorm_assist`/`_aself_brainstorm`/`aresolve_brainstorm`, état `idea_maturity`/`idea_rationale`/`brainstorm_techniques`/`awaiting_brainstorm_decision`, `POST /api/projects/{id}/brainstorm-decision`. Front : offre + boutons dans `ChatPanel`, `api.resolveBrainstorm`. Gardé derrière `AUTOSPEC_BRAINSTORM_ASSIST` (OFF par défaut → interview socratique inchangée). Support scripted (démo). | 7 tests pipeline + 4 Vitest + démo navigateur (offre → autonome → brief → suite) |

## 🎨 Streamline UI — ✅ livrée (revue UX)

Issues d'une revue UX experte de l'app en cours (35 projets réels, board `chat-eat`).
Priorité par valeur V / complexité C (1-5). À traiter une par une.

| # | Tâche | V/C | État |
|---|-------|-----|------|
| UI1 | **Grouper/replier les epics du board par itération** — sections par `iteration` (la plus récente/active dépliée, l'historique replié en résumé une-ligne avec barre de progression agrégée + état) ; auto-déplie le groupe qui passe `working` ; deps inter-itérations toujours visibles ; pas de repli s'il n'y a qu'une itération ; choix d'expansion persisté par projet. Garde le board centré sur la feature active quand l'historique s'accumule. **✅ LIVRÉ** : `EpicsView` groupe par `iteration` (sections repliables, en-tête « Itération N » + barre agrégée + spinner si working), seed sur la plus récente, auto-déplie les itérations `in_progress`, persistance `localStorage` par projet ; `EpicCard` extrait ; 3 tests. | 5/3 | ✅ |
| UI2 | **Nom de projet lisible par défaut** — dériver un nom signifiant de l'objectif au lieu du slug « todo », dédupliquer (`todo`, `todo-2`). Backend `_slug`/création + fallback. Fini les 12 chips « todo » indistinguables. **✅ LIVRÉ** : `_default_name` (1re clause de l'objectif, capée à 40c + …) + `_unique_name` (dédup « … (2) ») dans `acreate_project` ; 3 tests. | 5/2 | ✅ |
| UI3 | **Sélecteur de projet primaire + chips secondaires** — le dropdown 🗂 devient le commutateur principal ; les chips se limitent aux projets actifs/en cours (ou masquées au-delà de N) ; tri actif→dormant→terminé ; champ de recherche/filtre dans le sélecteur dès qu'il y a beaucoup de projets. **✅ LIVRÉ** : tri actif→dormant→terminé ; chips limitées aux projets en cours + sélectionné ; reste via 🗂 (« +N dans 🗂 ») ; 1 test. | 4/3 | ✅ |
| UI4 | **Panneau de logs repliable / auto-dimensionné** — la grosse boîte noire des logs ne réserve plus d'espace tant qu'il n'y a pas de logs (collapse/auto-size), récupère l'espace mort. **✅ LIVRÉ** : RunPanel `run-collapsed` (flex 0 quand vide/replié) + toggle « ▾ Logs (N) » ; le Board récupère l'espace ; 2 tests. | 4/2 | ✅ |
| UI5 | **Panneaux latéraux conditionnels/repliables** — ne rendre (ou replier en accordéon) Composants/Backlog/Architecture que s'ils ont du contenu, au lieu de 4 panneaux empilés souvent vides. **✅ LIVRÉ** : `CollapsibleSection` réutilisable (caret + repli) appliqué à Composants/Backlog/Architecture (déjà auto-masqués si vides). | 3/3 | ✅ |
| UI6 | **États vides actionnables** — remplacer « Le PO n'a pas encore produit de plan. » et le chat vide par un appel à l'action (bouton « ▶ Lancer pour générer le plan », aide de démarrage). **✅ LIVRÉ** : board vide contextuel (spinner « plan en cours » en phase planif, consigne sinon) via prop `phase` ; chat vide → message d'amorce ; 2 tests. | 4/2 | ✅ |
| UI7 | **Regrouper les actions de la RunPanel** — action primaire mise en avant (Lancer/Pause/Reprendre) + menu « ⋯ Livraison/Export » pour Doc/Zip/Commit/Rollback/Déploiement ; masquer les actions post-build tant qu'aucun build n'existe. **✅ LIVRÉ** : menu overflow « ⋯ Livraison » (popover, fermeture au clic-dehors) regroupant Doc/Zip/Commit/Rollback/Déploiement, affiché seulement hors phase active ; 2 tests + e2e adapté. | 4/3 | ✅ |
| UI8 | **Remplacer les `prompt`/`alert` natifs** — Rollback (`window.prompt`), Déploiement/Commit (`window.alert`) → modale/toast in-app cohérents avec le reste. **✅ LIVRÉ** : `pushToast` in-app pour Déploiement/Commit/Rollback ; modale de choix d'itération pour le Rollback (plus de `window.prompt`/`alert`). | 3/3 | ✅ |
| UI9 | **Hiérarchie visuelle** — élévation/espacement entre colonnes, titres de panneaux plus contrastés (moins « muted »), système de couleurs de statut appliqué de façon cohérente (chips, sélecteur, board). **✅ LIVRÉ** : variable `--title` (titres contrastés), élévation des panneaux + barre de titre, gap colonnes 16px. | 3/3 | ✅ |
| UI10 | **En-tête épuré** — regrouper provider + modèle en un contrôle compact, dégager le titre (le 🤖 flottant + 2 selects encombrent la barre de titre). **✅ LIVRÉ** : pilule compacte « 🤖 provider · modèle ▾ » ouvrant un popover (provider + modèle), dégage la barre de titre. | 2/2 | ✅ |

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

| BUG3 ✅ | **🔴 CRITIQUE — les commits du workspace polluaient le dépôt englobant** — `_agit_ensure_repo` testait `git rev-parse --is-inside-work-tree`, **vrai aussi pour un dossier imbriqué** dans un dépôt parent. Comme `workspace_root` vit par défaut dans le checkout Autospec (`Autospec/workspace`, lui-même dans le repo `squad-ai`), `git init` était **sauté** et chaque `git add -A` + `commit` (snapshot story, « story X done », snapshot d'itération, export, rollback) écrivait dans le **dépôt de l'utilisateur** — avec son **identité git globale** et en y embarquant tout son WIP non commité. Repéré en live : le diff d'une US montrait `Brainstorming/.playwright-mcp/…` et un auteur `etienne.millerioux@studi.fr`. **Fix** : ancrer sur `ws/.git` (`if (ws / ".git").exists(): return True` sinon `git init` dans le workspace) → repo **isolé** par projet, commits sous `Autospec <autospec@local>` ; respecte aussi un repo brownfield existant. **Non-régression** : `test_workspace_git_is_isolated_from_enclosing_repo` (workspace imbriqué dans un repo parent → `ws/.git` créé, 0 commit fuité dans le parent). Vérifié en live : 0 nouveau commit dans le repo utilisateur sur tout un run complet. | 5/3 |

| BUG4 ✅ | **Erreur 502 (ECONNRESET) à la création / au chat** — uvicorn ferme ses sockets keep-alive inactifs après **5 s** (défaut) ; l'agent keep-alive du proxy Vite réutilise alors un socket que le serveur vient de fermer (idle pendant que l'utilisateur remplit le formulaire) → `ECONNRESET` sur le `POST` que le proxy **ne réessaie pas** (méthode non idempotente). Reproduit de façon **déterministe** (8 s d'inactivité avant clic → 502). **Fix** : `timeout_keep_alive` généreux côté backend (`AUTOSPEC_KEEP_ALIVE_S`, défaut **600 s**) dans `server.main()` → c'est toujours le client qui ferme en premier, plus de réutilisation de socket mort. Vérifié en live : création fiable même après inactivité. | 4/2 |

| BUG5 ✅ | **`DELETE /api/projects/{id}` bloquait l'event loop** — `_force_delete_workspace` faisait un `shutil.rmtree` **synchrone sur la boucle** (lent sur Windows : packs git en lecture seule + retries `chmod`). Pendant le blocage uvicorn n'`accept()` plus → `ETIMEDOUT`/`000` côté proxy (reproduit : suppressions concurrentes qui timeout). **Fix** : `await asyncio.to_thread(_force_delete_workspace, …)`. Même famille que BUG2 (ne jamais bloquer la boucle). Vérifié en live : suppression d'un projet (avec `.git`) propre, backend resté réactif. | 3/2 |

| BUG6 ✅ | **Squelette Python parasite dans les projets Go/Rust** — `workspace.scaffold()` (qui dispatche selon le langage) était appelé **avant** `_aselect_language()`, donc au moment où le langage valait encore le défaut Python. Un projet Go se retrouvait avec `main.py`, `pyproject.toml`, le package Python et `tests/` **en plus** de `go.mod`/`main.go`. **Fix** : déplacer le `scaffold` **après** la sélection du langage dans `_alifecycle` (le `_aspec_phase` n'utilise pas le workspace ; brownfield crée déjà son dossier). Vérifié en live : un projet Go ne contient plus que `go.mod`/`main.go`/`features`/`README`. | 3/1 |

## 🧪 Benchmark de langage cible (Python / Go / Rust)

| # | Tâche | V/C | État |
|---|-------|-----|------|
| L1 | **Benchmark « quel langage pour faire coder l'IA »** — décider le(s) langage(s) cible(s) de l'app générée par Autospec sur la base de **mesures**, pas d'opinion. Le critère n'est pas « meilleur langage dans l'absolu » mais « meilleur dans une boucle de génération autonome rouge→vert » : débit de boucle (vitesse de compile + taux de blocage), correction par itération (garanties compile-time qui déchargent linter/tests), prédictibilité de génération (volume/régularité du training set). | 5/3 | 🔬 mesuré (voir `benchmarks/lang-eval/`) |
| L2 | **Sélecteur de langage backend par analyse complexité/criticité au démarrage** — **Go devient le langage backend par défaut** (cf. conclusion L1 : meilleur compromis débit-de-boucle pour l'usine). Mais au lieu d'imposer un seul langage, **à la création du projet** un analyseur (`language_selector`, persona architect — réutilise/prolonge le pattern E3 `components_proposal` qui fixe déjà `Component.technology` du backend) estime **deux axes** depuis l'objectif/brief : (a) **complexité technique** (1-5) et (b) **criticité / sensibilité aux erreurs** (1-5, coût d'une régression : financier, légal, sûreté, données). Il en **dérive le langage backend recommandé** : <br>• **Python** — projets simples / faible criticité (calculatrice, site vitrine, prototype, CRUD jetable) : génération la + fiable, pas de barrière de compile. <br>• **Go** (défaut) — appli professionnelle « sérieuse » de complexité/criticité moyenne (SaaS, back-office, API métier) : typage + débit de boucle + déploiement simple. <br>• **Rust** — complexité technique **élevée** OU criticité **élevée** (bancaire/paiement, santé, systèmes, calcul exigeant, garanties dures) : le compilateur décharge linter+tests (exhaustivité/null/erreurs/races, cf. L1 §3), correction maximale. <br>**Sortie** : recommandation + score (complexité, criticité) + **rationale** présentés à l'utilisateur, **éditable/surchargé** comme les composants E3 (l'utilisateur garde le dernier mot ; Go reste le fallback si l'analyse est ambiguë). Persister `ProjectState.backend_language` (+ scores) ; injecter dans les prompts QA/Dev + le `setup_exec` (scaffold backend selon le langage) + le `_minimal_env`/toolchain de build-test (dépend du **pré-requis L1 Niveau B** : abstraire `uv run pytest` → commande de build/test + parsing d'erreurs compilateur par langage). Env-gated `AUTOSPEC_LANGUAGE_SELECTOR` (off → Go par défaut, ou Python pour rétro-compat selon flag). Heuristique déterministe de secours si l'agent échoue (mots-clés criticité « bancaire/paiement/santé/sécurité » → Rust ; « calculatrice/démo/vitrine » → Python ; sinon Go). **✅ LIVRÉ (incrément : décision + persistance + surfaçage)** : <br>• **L2a** `BackendLanguage`{python/go/rust} + `ProjectState.backend_language`/`language_complexity`/`language_criticality`/`language_rationale` ; module `language_selector.py` (`recommend_language` heuristique déterministe : critique→rust, simple→python, sinon go) — 6 tests. <br>• **L2b** `_aselect_language` après le brief (1re itération), persona architect, env `AUTOSPEC_LANGUAGE_SELECTOR` (off → heuristique seule), fallback heuristique si l'agent échoue, message système 🧭 ; prompt `language_proposal` + reply scripté — 4 tests. <br>• **L2c** override `PUT /api/projects/{id}/language` (422 langage inconnu, 404 projet) — 1 test. <br>• **L2d** langage injecté dans les prompts QA/Dev (`_language_block`, non-python uniquement) — 1 test. <br>• **L2e** `LanguagePanel` (langage recommandé + scores complexité/criticité + rationale + dropdown override), `setLanguage` (retry idempotent), câblé dans la colonne gauche — 3 tests Vitest. <br>**✅ L2g — chaîne de build/test multi-langage (LIVRÉ)** : module `orchestrator/toolchain.py` (commande de test + parsing des résultats par langage : Python=pytest-json-report, Go=`go test ./... -json`, Rust=`cargo test`) — 7 tests ; `workspace.scaffold` dispatché par langage (Go `go.mod`+`main.go`, Rust `Cargo.toml`+`src/main.rs`, idempotent, vert dès le scaffold) — 4 tests ; `_arun_pytest` généralisé (dispatch par langage, démo court-circuitée, sandbox R1 conservé) + mutation/couverture gardées Python-only ; prompt Dev natif Go/Rust (`_dev_story_native`, pas de pytest-bdd) + QA paramétré ; run-app par langage (`go run`/`cargo run`/`uv run`). **Smoke réel** : boucle rouge→vert Go pilotée par l'orchestrateur (parse `go test -json`) + scaffolds Go/Rust qui compilent vert. Toolchains Go 1.26 / Rust 1.91 / uv présentes localement. | 5/5 | ✅ |

### Protocole de benchmark (reproductible)
**Niveau A — caractéristiques toolchain (machine, déterministe, indépendant du modèle).** Implémenter une **spec backend identique** (lib domaine « TaskBoard » : validation, types d'erreur, exhaustivité de statut, tri, stats + suite de tests équivalente) dans Python / Go / Rust, puis mesurer :
- **cold build** (depuis propre) — proxy du coût de la 1re itération + ajout de dépendance ;
- **warm/incremental build** (après touche d'1 fichier) — proxy du coût de chaque itération rouge→vert ;
- **temps d'exécution des tests** — proxy du tour de boucle ;
- **LOC** et densité de cérémonie ;
- **classe d'erreurs attrapées à la compilation** vs renvoyées au runtime (null-safety, exhaustivité, erreurs non gérées).

**Niveau B — réussite du modèle (à brancher sur la pipeline Autospec).** Sur 5–10 stories déjà vertes en Python, régénérer en Go et Rust avec le même modèle et logger par run : **taux de vert atteint**, **nb d'itérations rouge→vert**, **temps de compile cumulé**, **nb de blocages** (cap de tours atteint), **wall-clock total**. Croiser par modèle (Opus / GPT-5.x codex / Gemini 3.x) pour répondre empiriquement à « quel modèle est meilleur dans quel langage » sur _nos_ prompts. Pré-requis pipeline : abstraire la toolchain de build/test (commande + parsing des erreurs compilateur du raffinement) au-delà de `uv run pytest` — cf. `pipeline.py` / `_minimal_env`.

**Conclusion (Niveau A, mesurée ce tour) :** voir `benchmarks/lang-eval/RESULTS.md`. Synthèse : **Go = meilleur compromis débit-de-boucle** (compile quasi-instantanée, langage à petite surface → l'IA bloque peu) ; **Rust = correction maximale par itération** (le compilateur attrape null/exhaustivité/erreurs non gérées → décharge linter+tests) au prix d'un cold build lourd et d'un risque de non-convergence (borrow checker/async) ; **Python = référence** (génération la plus fiable, mais zéro garantie compile-time). Recommandation : **Go par défaut** pour la fiabilité de l'usine, **Rust en option ciblée** quand la correction du produit prime sur le débit, le tout à valider au Niveau B.

## 🧵 Refonte multi-stream (streams + tâches + parallélisme worktree) — planifiée

> **But.** Découper le travail d'une fonctionnalité en plusieurs **streams** (backend / frontend / cache / database…) pour lancer des **agents en parallèle** sur des streams indépendants, tout en reflétant les **dépendances fonctionnelles** dans les US/tâches. Permettre de gérer **intégralement un stream frontend React**. Cas d'usage cible : depuis un projet livré, demander « ajoute une UI web » → création d'un stream `frontend` + de tâches front liées par dépendance aux tâches back existantes.

### Concepts & glossaire
- **Stream** : zone de travail avec son **toolchain** (scaffold, commande de test, build, détection du « vert »), son **langage** et sa **zone de fichiers** présumée disjointe (ex. `frontend/`, package backend). Catalogue : `backend` (Python/Go/Rust — existant), `frontend` (React+Vite+Vitest — **nouveau**), `cache`, `database`. Tout projet a au moins le stream `backend`.
- **Hiérarchie (modèle HYBRIDE retenu)** : `Epic` → `UserStory` (tas **fonctionnel**) → **Tâche** (optionnelle). Une US mono-stream reste l'unité de dev (flaggée stream). Une US multi-stream se **décompose en tâches**, chacune dans **un** stream, avec dépendances inter-tâches (ex. tâche front `depends_on` tâche back). Le statut de l'US **dérive** de ses tâches quand il y en a.
- **Work item** (unité planifiable par le moteur) : une US sans tâches, **ou** une tâche. « Prêt » quand toutes ses dépendances (US↔US et tâche↔tâche) sont `done` **et mergées**.

### Décisions (validées avec l'utilisateur)
1. **Hiérarchie = Hybride** : US flaggable stream **+** tâches optionnelles quand une US couvre plusieurs streams.
2. **Frontend « vert » = Vitest (composants/unit) + build `tsc && vite build`** (parité TDD avec le backend, déterministe).
3. **Parallélisme = un worktree git isolé par tâche** (réutilise l'isolation `.git` par projet de BUG3) ; merge dans le repo du projet à la fin verte.
4. **Définition des streams = l'architecte les choisit par projet** dans le catalogue (chacun lié à un toolchain) — `backend` toujours présent. (tranché par défaut.)
5. **Rétro-compat** : tout derrière un flag `AUTOSPEC_STREAMS` (OFF = comportement actuel, 1 stream backend implicite, pas de tâches). Chaque nouvel agent doit avoir son support `ScriptedRunner` (démo/tests).

### Tâches d'implémentation (ordonnées ; dépendances entre tâches de backlog indiquées)

| # | Tâche | Livrable concret | Dép. |
|---|-------|------------------|------|
| ST-1 | **Modèle `Stream` + catalogue + `ProjectState.streams`** | `Stream{id, kind, language, toolchain_ref, file_root}` ; catalogue par défaut ; flag `AUTOSPEC_STREAMS` (OFF→backend implicite). `models.py`, `config.py`. | — |
| ST-2 | **Niveau Tâche + `UserStory.stream`** | Modèle `Task{id, story_id, stream, title, description, acceptance_criteria, gherkin, depends_on:[task_id], status, attempts, last_error, files_hint}` ; `UserStory.stream` (défaut = stream backend primaire) + `UserStory.tasks`. Statut d'US **dérivé** des tâches. Migration des états persistés (US sans stream→`backend`, sans tasks→inchangé). `models.py`. | ST-1 |
| ST-3 | **Graphe de work items + readiness** | Helper qui énumère les work items (US sans tâches ∪ tâches), calcule la « readiness » (deps `done`+mergées), **détecte les cycles** et valide la cohérence des deps inter-stream. Tests unitaires. `orchestrator/`. | ST-2 |
| ST-4 | **Sélection des streams (architecte)** | Phase architecture : agent qui choisit les streams pertinents du catalogue + langage par stream (≥ `backend`). Prompt + schema JSON + `ScriptedRunner`. `prompts.py`, `pipeline.py`, `scripted.py`. | ST-1 |
| ST-5 | **Plan multi-stream (PO)** | `po_plan` étendu : US **fonctionnelles** ; par US, soit flag mono-stream, soit **décomposition en tâches** taguées stream avec deps inter-tâches (front→back). Schema `tasks[]`+`stream`+`depends_on`. Dédup/remap d'ids adaptés. Refine du plan compatible. `prompts.py`, `pipeline.py`. | ST-2, ST-4 |
| ST-6 | **Toolchain frontend (React)** | Scaffold **Vite+React+TS+Vitest** sous le `file_root` du stream ; `test_command` = `vitest run` (reporter JSON), `build` = `tsc && vite build` ; parsing résultats (vert/rouge) + erreurs de build pour le raffinement. Étend `toolchain.py`/`workspace.py` au-delà de Python/Go/Rust. | ST-1 |
| ST-7 | **Agent Dev frontend** | Persona + prompt dev React : écrit composants + tests Vitest en boucle **rouge→vert**, « vert » = Vitest tous verts **ET** build OK. Réutilise la boucle d'`attempts`/raffinement existante. `ScriptedRunner`. `personas.py`, `prompts.py`, `pipeline.py`, `scripted.py`. | ST-6 |
| ST-8 | **Run/preview multi-process** | Bouton « Lancer » multi-stream : back + `vite preview` du front simultanément ; logs par stream. `pipeline.py` (`_stream_run_output`), `RunPanel`. | ST-6 |
| ST-9 | **Ordonnanceur parallèle stream-aware (worktree)** | Remplace la boucle de build : lance en parallèle les work items **prêts** (cap `max_parallel_devs`), **chaque dev dans son worktree git isolé** branché sur l'état courant du repo projet. `pipeline.py`. | ST-3, ST-7 |
| ST-10 | **Merge des worktrees + snapshots** | À la fin verte d'un work item : merge dans le repo projet (réutilise `_agit_*`), politique de conflit (retry → sérialisation → flag `failed` avec raison), snapshot par work item. Tests. `pipeline.py`. | ST-9 |
| ST-11 | **Dépendances inter-stream à l'exécution** | Un work item ne démarre que lorsque ses deps sont **mergées** (le contrat/API back existe dans la base dont la tâche front branche). Reflété dans la readiness (ST-3) et le scheduler (ST-9). | ST-9, ST-10 |
| ST-12 | **Board multi-stream** | Badges stream sur US/tâches ; **swimlanes**/filtre par stream ; tâches dépliables sous une US ; visualisation du parallélisme (plusieurs « dev en cours »). `Board.tsx`, `types.ts`. | ST-2 |
| ST-13 | **Détail & actions par tâche** | Détail tâche (critères, deps, stream, relance/diff/forcer terminé par tâche) à côté du détail US. `Board.tsx`/`StoryDetail`, `api.ts`, endpoints. | ST-2, ST-12 |
| ST-14 | **Indicateurs deps inter-stream & merge** | UI : US/tâche « bloquée par X » (dépendance non mergée) + état de merge (mergé/en conflit). `Board.tsx`. | ST-11, ST-12 |
| ST-15 | **Évolution de specs → nouveau stream** | Étendre `_aimpact_analysis` : un feedback type « ajoute une UI web » crée le stream `frontend` (si absent) **et** des tâches front liées par dépendance aux tâches/US back existantes, développables via « Continuer le build ». `prompts.py` (`feedback_impact`), `pipeline.py`. | ST-5, ST-9 |
| ST-16 | **Rétro-compat & flag** | `AUTOSPEC_STREAMS` OFF → comportement actuel inchangé (1 stream backend, pas de tâches, pas de worktree) ; ON → multi-stream. **Toute la suite existante reste verte.** `config.py`, garde dans `pipeline.py`. | ST-1…ST-15 |
| ST-17 | **Tests & démo e2e multi-stream** | Unitaires (graphe/readiness/cycle, décompo tâches, parsing vitest/build, merge/conflit) + démo navigateur multi-stream (back+front en parallèle, dépendance front→back respectée, merge). `tests/`, `e2e`. | ST-1…ST-16 |

### Lots de livraison conseillés (une tranche à la fois)
- **Lot 1 — Fondations modèle** : ST-1, ST-2, ST-3 (+ ST-16 garde-flag). Aucun changement de comportement (flag OFF).
- **Lot 2 — Planification multi-stream** : ST-4, ST-5. Le plan sait produire streams + tâches.
- **Lot 3 — Stream frontend** : ST-6, ST-7, ST-8. Un projet peut générer du React vert.
- **Lot 4 — Moteur parallèle** : ST-9, ST-10, ST-11. Parallélisme réel par worktree + merge.
- **Lot 5 — UI** : ST-12, ST-13, ST-14.
- **Lot 6 — Specs évolutives & e2e** : ST-15, ST-17.

### Décisions différées (à trancher au moment du lot concerné)
- Toolchains précis des streams `cache` / `database` (on livre **frontend + backend** d'abord ; cache/db = catalogue extensible).
- Politique fine de résolution des conflits de merge (au-delà de retry→sérialisation→`failed`).
- Granularité du parallélisme **intra-stream** (worktrees autorisent le parallèle même intra-stream ; à activer/limiter selon le coût de merge observé).

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
