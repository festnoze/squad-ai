# Autospec — Backlog

Backlog vivant, priorisé (valeur V / complexité C, 1-5). Mis à jour entre chaque
itération du loop de développement. Règle de délégation : tâches de complexité
faible/moyenne → subagents Opus ; orchestration/intégration/conception complexe →
modèle courant.

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
