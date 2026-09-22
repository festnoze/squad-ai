# Autospec - prochaines étapes (relecture du 2026-09-22)

Relecture complète du projet (README, FEATURES, BACKLOG, REFACTOR_PLAN,
WORKFLOW_REVIEW, GENERATION_FUSION_REVIEW, FACTORY_IMPROVEMENTS,
DEFECTS_RESOLUTION_PLAN, docs/ux, docs/improvement_V3, code de `orchestrator/`).

## 1. Où en est l'usine

- Pipeline complète et éprouvée en réel : certification first-shot fullstack
  (`biblio`, 2026-07-12), run supervisé `recettes` (2026-07-20) avec 24 fixes
  d'usine livrés en trois rounds, boucle observation -> gouvernance -> mémoire
  (V3, 8 features), verified swarm (waves 0-5), livraison Docker.
- Suite : 1160 tests backend, 239 Vitest, 2 specs e2e Playwright (mode démo
  hermétique, port 8123) + 1 spec e2e multi-stream (port 8124).
- Le générateur produit du code juste. Les pertes constatées viennent de la
  boucle vérification -> canari -> revert -> requeue quand l'environnement ment,
  et du fait que ces échecs non imputables au code consomment le budget dev
  (GENERATION_FUSION_REVIEW §2 : 120 suites pour 17 items, 11/11 verdicts
  canari faux positifs, 27 h pour une tâche de 15 lignes).

## 2. Ce qui restait ouvert (et n'a jamais été livré)

| Source | Item | État |
|---|---|---|
| GENERATION_FUSION_REVIEW | P0-A réparer + rejouer TOUJOURS avant de croire au sémantique (rouge sans test exécuté) | non fait |
| GENERATION_FUSION_REVIEW | P0-B budget de requeue séparé (conflit de merge / revert canari ne consomment pas une tentative dev) | non fait |
| GENERATION_FUSION_REVIEW | P1-A canari par rafale sous contention (+ bisect) | non fait |
| GENERATION_FUSION_REVIEW | P1-B ne pas garder un slot dev pendant merge + canari | non fait |
| GENERATION_FUSION_REVIEW | P1-C ordonnancer les feuilles à fort fan-out d'abord, tentative bonus | non fait |
| GENERATION_FUSION_REVIEW | P2-A 2e conflit de merge -> mode SOLO au lieu de FAILED | non fait |
| GENERATION_FUSION_REVIEW | P2-B cache npm partagé pour les installs hermétiques | non fait |
| GENERATION_FUSION_REVIEW | P3 observabilité de la boucle de fusion dans la rétro | non fait |
| WORKFLOW_REVIEW | P1 rembourser la tentative dev quand le rouge est classé infra | non fait |
| WORKFLOW_REVIEW | P3 échec d'architecture silencieux | non fait |
| WORKFLOW_REVIEW | P4 dégradation silencieuse du harnais refine | non fait |
| WORKFLOW_REVIEW | P7 re-sondage périodique de la fenêtre d'usage | non fait |
| FACTORY_IMPROVEMENTS | #4 `main.py` CLI relaie argv, smoke CLI exige une sortie non vide | non fait |
| FACTORY_IMPROVEMENTS | TS extraites sans critères d'acceptance (avertissement DoD systématique) | non fait |
| FACTORY_IMPROVEMENTS | balayage des orphelins au démarrage (`recover_projects`) | non fait |
| FACTORY_IMPROVEMENTS | commit « story done » émis sur un rollup incomplet | non fait |
| DEFECTS D11 | statut stocké des stories à tâches jamais consolidé | documenté |
| docs/ux 03 | R3 consolidation des vues, R4 extraction design system, R6 undo/soft-delete des stories | non faits (R1/R2/R5 livrés) |
| RFC po-pipeline-v2 | éval provider réel avant activation par défaut | en attente |
| Harnais de tests | la conftest n'épinglait pas REFINE / TECH_WRITER / EVALUATOR / SECURITY_REVIEW / PARTIAL_DELIVERY : le .env du poste faisait échouer `test_create_and_complete_project` | corrigé ce jour |

## 3. Plan en vagues

Règle : un lot par invocation Workflow, agents Opus, tous les items qui touchent
`pipeline.py` / `config.py` / `models.py` s'exécutent en chaîne séquentielle
(fichiers chauds), les autres en parallèle. Chaque vague se termine par une
gate qui rejoue la suite backend complète (et Vitest / Playwright quand le
frontend bouge).

### Vague 1 - ne débiter le budget dev que pour un échec imputable au code

1. P0-A : rouge sans test exécuté -> purge env + un replay AVANT tout verdict
   sémantique, même sans signature connue (canari et vérif worktree).
2. P0-B + WORKFLOW-P1 : `requeue_attempts` (budget `REQUEUE_MAX`, défaut 3)
   pour les requeues conflit de merge / revert canari / rouge classé infra ;
   `attempts` ne compte que les vraies re-générations (dev a tourné et rouge).
3. P1-C : `scheduler.rank_ready()` (fan-out transitif décroissant, puis priorité),
   tentative bonus quand le fan-out dépasse `FANOUT_BONUS_THRESHOLD` (5).
4. P1-B : les étapes MERGE_WAIT / MERGING / canari ne comptent plus dans le cap
   (plafond dur cap + 1).
5. WORKFLOW-P3 / P4 : architecte indisponible -> notification warning + chat ;
   critic/judge indisponibles -> événement monitor `refine_degraded` + chat.
6. WORKFLOW-P7 : `session_monitor.await_window()` re-sonde ccusage toutes les
   `RESUME_REPROBE_MIN` (30) minutes au lieu d'attendre le fallback.

### Vague 2 - fusion, wall-clock et finitions d'usine

1. P1-A canari par rafale : sous contention, un seul canari après la rafale,
   bisect par revert du dernier merge vers le premier si rouge.
2. P2-A mode SOLO : au 2e conflit, drain des items en vol puis rebuild seul sur
   le HEAD final avant de déclarer FAILED.
3. P2-B cache npm partagé (`--cache <workspace>/_npm-cache --prefer-offline`).
4. P3 rétro : ratio suites exécutées / items livrés, verdicts canari par type,
   requeues, exposés dans la rétro et `GET /api/metrics`.
5. FACTORY #4 : scaffold `main.py` relaie argv vers la feature CLI, smoke CLI
   exige une sortie non vide sur `--help`.
6. TS extraites : critères d'acceptance hérités (sous-ensemble du parent).
7. Balayage des orphelins de workspace au démarrage du backend.
8. Commit « story <id> done » seulement quand le rollup effectif est complet ;
   D11 : statut stocké consolidé quand toutes les tâches sont terminées.

### Vague 3 - frontend Phase 2 et visibilité des nouveaux signaux

1. R6 undo / soft-delete des stories (tombstone `deleted_at`, restore,
   exclusion scheduler, toast « Annuler »).
2. Signaux vague 1/2 dans l'UI : budget requeue, fan-out, verdicts canari dans
   le Dashboard, bannière de dégradation refine / architecte.
3. R3 : Activité par défaut dans toutes les phases, Board en lentille.
4. e2e Playwright étendu (démo hermétique) sur ces surfaces.

### Vague 4 - validation

1. Suite complète backend + Vitest + Playwright (2 harnais).
2. Run démo piloté (`scripts/build_driver.py`, agents scriptés) pour vérifier
   le bilan de calibration (requeues, canari, fan-out) sur un build multi-stream.
3. Option : un run réel court (profil cli) si le quota le permet.

## 4. Journal d'exécution

Voir la section « Journal » en bas de ce fichier, complétée à chaque vague.
