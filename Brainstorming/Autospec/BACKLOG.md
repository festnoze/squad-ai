# Autospec — Backlog

Backlog vivant, priorisé (valeur V / complexité C, 1-5). Mis à jour entre chaque
itération du loop de développement. Règle de délégation : tâches de complexité
faible/moyenne → subagents Opus ; orchestration/intégration/conception complexe →
modèle courant.

## 🚀 Extension produit (demandée) — en cours

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

> Backlog des 16 features : épuisé. Remédiation d'audit : 3 tranches actionnables
> traitées (couverture back/front + durcissement) ; le reste est différé (design/infra).
