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

### ⏳ Restant (prochaines tranches)
- **Sécurité (design)** : `bypassPermissions` par défaut + exécution non sandboxée du code généré (`uv run pytest`/`python main.py`) → nécessite un vrai sandbox ; env hérité par les sous-processus (fuite de secrets).
- **Robustesse (med)** : `adispose` ne tue pas le sous-processus pytest/git en cours (`asyncio.to_thread` non annulable) ; `_force_delete_workspace` n'attrape pas `OSError` ; raffinement (juge illisible = PASS, score défaut = seuil, commit avant jugement, rollback non vérifié).
- **Frontend (med)** : priorités drag-&-drop clampées à 5 (>5 stories : ordre non distinct).
- **Couverture** : tests manquants — erreur fatale `_alifecycle`, `_arefine_code`, 409 de `/run` & `/resume-build`, composant App (WS/upsert/suppression), drag-&-drop, endpoints `/chat /pause /resume /diff /rebuild`, recover SPEC/ANALYZE/PLAN, troncature `aread_file`, `RunPanel` conditionnel.

> Backlog des 16 features : épuisé. Le présent audit a ouvert une nouvelle tranche
> « sécurité & robustesse » ci-dessus, à traiter en priorité par sévérité.
