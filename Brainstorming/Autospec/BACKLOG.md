# Autospec — Backlog

Backlog vivant, priorisé (valeur V / complexité C, 1-5). Mis à jour entre chaque
itération du loop de développement. Règle de délégation : tâches de complexité
faible/moyenne → subagents Opus ; orchestration/intégration/conception complexe →
modèle courant.

## 🚀 Extension produit (demandée) — en cours

| # | Feature | V/C | État |
|---|---------|-----|------|
| E1 | **Phase spec enrichie** — facilitation socratique par dimensions + mode 🧠 Brainstorming (persona analyste BMAD, divergence→convergence pour re-questionner le besoin) ; endpoint `/spec-mode` + toggle UI | 4/3 | ✅ tests + e2e |
| E2 | **Analyse d'impact d'un feedback** — quand l'utilisateur donne un feedback / demande un changement, analyser l'état du projet pour décider : METTRE À JOUR une US non implémentée, ou ANALYSER une nouvelle tâche → créer Epic/US | 4/4 | ⏳ à faire |
| E3 | **Proposition de composants au démarrage** — un agent solutionneur propose les composants (défaut : backend Python+FastAPI, frontend React ; optionnels : DB PostgreSQL, cache Redis…) ; l'utilisateur valide/édite ; `ProjectState.components` | 4/4 | ⏳ à faire |
| E4 | **Exécuteur de setup** — étape qui crée réellement les composants : dossiers backend/frontend, venv, install des deps, manifests ; install réel derrière un flag (démo-safe) | 4/5 | ⏳ à faire (dépend de E3) |
| E5 | **Tests d'acceptance UI pilotés par Playwright** — pour les US à dimension **visuelle/UI**, la boucle d'implémentation lance un **navigateur** (Playwright), effectue clics/saisies, capture des screenshots et **assert sur le rendu**, en complément du pytest-bdd backend actuel (qui teste du code Python, pas d'UI/réseau). Les tests d'acceptance UI sont **stockés sous forme rejouable** (comme des tests unitaires, versionnés dans le workspace) pour pouvoir être relancés. Le QA route une US vers ce mode quand elle est UI ; prérequis : composant frontend généré (E3/E4) | 5/5 | ⏳ à faire (dépend de E3/E4) |
| I1 | **Budget de tokens/coût par projet + arrêt automatique** — `budget_usd`/`budget_tokens` à la création + endpoint `/budget` ; `_enforce_budget` au point de contrôle stoppe proprement auto-spec/build quand le budget est atteint ; saisie au setup + jauge « 💸 $X / $Y » | 5/2 | ✅ tests + e2e |
| I2 | **Livraison du produit généré : doc auto + export** — (a) agent **tech-writer** (persona BMAD existante) qui, après le build, produit README + instructions de lancement + résumé d'archi pour le **projet généré** ; (b) export : endpoint zip téléchargeable et/ou `git init` + commit propre du workspace (voire push/PR). Ferme la chaîne « généré → utilisable ». | 4/3 | ⏳ à faire |
| M1 | **Modèle / provider configurable** — pouvoir choisir le modèle et le provider (par projet ou global) : **Claude** via le harness CLI (déjà `AUTOSPEC_CLAUDE_MODEL`), **OpenAI** (Codex/GPT) via clé API, **modèles locaux via Ollama**. Implémentation propre via le point d'extension existant `AgentRunner` : ajouter `OpenAiRunner` et `OllamaRunner` à côté de `ClaudeCliRunner`, sélection par config/env + endpoint ; usage/coût adaptés par provider. | 4/3 | ⏳ à faire |
| M2 | **Ordonnancement aligné sur la fenêtre d'usage Claude** — planifier (cron/loop) le démarrage d'exécutions autonomes au moment où la fenêtre d'usage de l'abonnement Claude est disponible / vient de se réinitialiser, afin d'utiliser efficacement le quota souscrit plutôt que de le laisser inutilisé ou de buter en milieu de tâche. **Contrainte de conformité** : uniquement par ordonnancement légitime, dans le respect de la politique d'usage Anthropic (pas de contournement de limites, pas de multiplexage de comptes) — c'est de la planification, pas du dépassement de quota. | 3/3 | ⏳ à faire |
| U1 | **Accueil & multi-projets actifs** — (a) au lancement : afficher la **popup de création** par défaut si AUCUN projet n'existe, sinon ouvrir directement l'interface sur la **sélection de projet** (l'accueil/setup reste accessible via « ＋ Nouveau ») ; (b) **bouton play/stop par projet** dans la `ProjectBar` pour activer/suspendre et **surveiller** d'un coup d'œil les projets en cours d'auto-développement/auto-amélioration (indicateur d'activité par chip) ; (c) **plusieurs projets lancés en parallèle** — chaque projet a sa propre pipeline (déjà le cas backend), l'UI doit refléter et piloter plusieurs pipelines actives simultanément (état/avancement par chip, sans masquer les autres). | 4/3 | ⏳ à faire |

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
