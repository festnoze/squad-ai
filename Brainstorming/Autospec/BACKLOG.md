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

## ⏳ À faire — découvert en cours de route

| # | Item | V/C | Pourquoi |
|---|------|-----|----------|
| 14 | Observabilité tokens/coût + timings par agent | 2/3 | Mesurer le coût par phase/agent, surtout avec raffinement/architecture activés |
| 15 | Gestion des projets persistés legacy au boot | 2/2 | `recover_projects` recharge tous les vieux états ; offrir un archivage/nettoyage |
| 16 | Activer le CI dans le monorepo | 1/1 | Le workflow `.github/workflows/ci.yml` n'est pas déclenché tant qu'Autospec est dans `squad-ai` ; le déplacer à la racine du dépôt (chemins préfixés) ou extraire Autospec |

> Ordre courant : 9 (planifié) puis 10→15 par valeur/complexité, réévalué à chaque
> itération.
