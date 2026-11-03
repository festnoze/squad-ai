# Améliorations d'usine — mission « first-shot fullstack » (11-12 juillet 2026)

**Mission** : créer des projets du plus simple au plus complexe avec Autospec,
vérifier leur état de fonctionnement réel, diagnostiquer chaque échec de
création *first shot*, corriger l'usine à chaque fois, et recommencer jusqu'à
une création full-stack réussie du premier coup.

## Projets créés et état final

| Projet | Profil | Résultat | Conteneur |
|---|---|---|---|
| `convertisseur` | cli | Livré, CLI vérifié (conversions exactes, 70 tests) | — (CLI) |
| `notes-api` | api | Livré + déployé, API CRUD vérifiée en réel | `autospec-notes-api-*` :18000 |
| `kanban` (t.1) | fullstack | Échec 1er item (→ fix #9), supprimé | — |
| `kanban2` | fullstack | Build 7/7 first-shot ; livré + déployé après fixes | `autospec-kanban2-*` :18001 |
| `coloc` | fullstack | Build 6/6 first-shot ; livré + déployé (soldes exacts) | `autospec-coloc-*` :18002 |
| `biblio` | fullstack | **✅ CERTIFICATION FIRST-SHOT RÉUSSIE** : idée → build 4/4 → smoke → runtime → DoD → image Docker → déployé, sans AUCUNE intervention externe (la pause fenêtre d'usage à 00:49 a été reprise automatiquement par le watchdog M2 — mécanisme du pipeline) | `autospec-biblio-*` :18003 |

Les QUATRE conteneurs tournent sur le réseau partagé `autospec-net`,
mutuellement joignables (matrice 4×4 vérifiée, sondes E2E fonctionnelles sur
chaque app : CRUD notes, tableau kanban, soldes de colocation exacts,
bibliothèque avec statistiques).

## Correctifs d'usine livrés (tous testés, suite backend verte)

| # | Défaut constaté (sur données réelles) | Correctif | Fichiers |
|---|---|---|---|
| 1 | Constitution : imports tiers top-level compilés avant que la dépendance existe → erreur de collecte pytest → cascade d'échecs | Garde `pytest.importorskip` auto (AST) : l'invariant skippe puis s'active à l'arrivée de la dépendance | `orchestrator/constitution.py` |
| 2 | Patches de fichiers workspace invisibles des worktrees (non commités) | Consigné : toute correction de workspace doit être commitée (les worktrees branchent sur HEAD) | — (procédure) |
| 3 | Cycle de dépendances inter-stories créé par le split-on-failure → échec en masse | Cassage défensif des cycles à l'ingestion du graphe (+ surfaçage chat/log) ; graphe brut dispo via `break_cycles=False` pour le rollback de split | `orchestrator/streams.py`, `pipeline.py` |
| 4 | `main.py` CLI silencieux + smoke « exit 0 » trivialement vert | **Reporté** (non bloquant fullstack) | — |
| 5 | Dérive de nommage : agents parallèles créant un second package top-level (`unitconv/` à côté de `convertisseur/`) | Contrainte explicite dans le prompt Dev | `agents/prompts.py` |
| 6 | Rollup trompeur : story `done` + commit « story done » avec tâches failed | Consigné (les gates utilisent `effective_status`, correct) | — |
| 7 | `arebuild_story` ne réinitialisait pas les TÂCHES (attempts épuisés, last_error périmé) → rebuild no-op | Reset complet des tâches au rebuild | `pipeline.py` |
| 8 | Les gates (smoke/runtime/docker) ne tournaient que dans le cycle de vie principal — un projet terminé par rebuild/resume y échappait | Helper `_adelivery_gates()` partagé par lifecycle, `_arebuild_one` et `aresume_build` | `pipeline.py` |
| 9 | Constitution : imports tiers NICHÉS dans les helpers (`def _client(): from fastapi...`) → échec à l'exécution, hors de portée du garde #1 | Scan AST complet (`ast.walk`) : tout import tiers, où qu'il soit, déclenche le skip module | `orchestrator/constitution.py` |
| 10 | Processus de smoke-run fuités sous Windows (superviseur uvicorn survit au taskkill du wrapper uv, respawn le worker) → gate suivant parqué « infra » | Kill par port des orphelins du workspace, en remontant à l'**ancêtre workspace le plus haut** (v2) + double-tap après le smoke | `pipeline.py` |
| 11 | Aucun moyen de rejouer les gates sur un projet dormant après réparation d'infra | `Pipeline.averify_delivery()` + `POST /api/projects/{id}/verify` | `pipeline.py`, `api/server.py` |
| 12 | Profil fullstack exigeait des tests pytest-playwright PAR STORY que le stream frontend (React/Vitest) ne peut pas produire → DoD bloquée pour TOUT projet fullstack | `ui_tests_enabled=False` en fullstack (la preuve UI = gate runtime acceptance, navigateur réel sur l'app intégrée) ; web-ssr inchangé | `orchestrator/profiles.py` |
| 13 | L'orphelin d'un AUTRE projet Autospec était « externe » pour le tueur #10 → infra-park en chaîne entre projets | Needle élargie au **workspace root** (tout processus lancé depuis `workspace/*` est à l'usine) | `pipeline.py` |
| 14 | Frontend générés avec URLs API absolues (`http://localhost:8000/...`) → CORS `localhost` vs `127.0.0.1` en mode intégré, cassé en conteneur | Contrainte « URLs relatives » dans le prompt Dev frontend + guidance renforcée du prompt de réparation | `agents/prompts.py` |
| + | `uvicorn.run(host="127.0.0.1")` prescrit par le prompt Dev → app injoignable en conteneur | `host="0.0.0.0"` prescrit (avec justification conteneur) | `agents/prompts.py` |
| + | Base SQLite de dev embarquée dans l'image Docker (`COPY . .`) | `*.db`/`*.sqlite*` ajoutés au `.dockerignore` généré | `orchestrator/deploy.py` |

## Améliorations restantes (notées, non bloquantes)

- **#4** : `main.py` CLI doit relayer argv vers la feature CLI enregistrée ;
  le smoke CLI devrait exiger une sortie non vide sur `--help`.
- Comptage de traçabilité incohérent (« 8 critères » annoncés, 6 listés —
  doublons d'IDs inter-stories comptés, liste dédupliquée).
- Commit git « story <id> done » émis sur un rollup stored-status incomplet.
- Les TS extraites n'ont pas de critères d'acceptance explicites (avertissement
  DoD systématique).
- Robustesse : un agent de réparation (bypassPermissions) peut tuer des
  processus de l'hôte (backend Autospec inclus — observé une fois) ; un
  balayage des orphelins au démarrage (`recover_projects`) compléterait le
  fix #10/#13.

## Leçons de boucle de rétroaction

1. **Progressivité des invariants** : un gate compilé tôt (constitution) doit
   s'activer progressivement (skip → actif) au rythme des dépendances livrées,
   jamais casser la collecte.
2. **Attribution stricte infra vs code** : chaque heure perdue de cette mission
   venait d'une mauvaise attribution (zombie externe → « infra » qui n'en était
   pas ; orphelin d'usine → « externe » qui n'en était pas).
3. **Symétrie des chemins** : tout chemin de complétion (lifecycle, rebuild,
   resume, verify) doit passer par LES MÊMES gates — sinon les réparations
   produisent des livraisons non vérifiées.
4. **Les prompts sont du code d'usine** : deux bugs systématiques venaient des
   prompts eux-mêmes (`host=127.0.0.1`, absence de règle d'URL relative).
