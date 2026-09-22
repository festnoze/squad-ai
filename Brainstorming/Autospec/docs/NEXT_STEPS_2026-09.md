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

---

## Journal

### Vague 1 (2026-09-22)

**Statut : livrée et validée. Suite backend complète : 1254 passed, 0 failed
(208,9 s, `uv run pytest -q -p no:cacheprovider`). Aucune correction de gate
n'a été nécessaire.**

#### Items livrés

1. **FUSION P0-A - canari rouge sans test exécuté.** `Pipeline.
   _acanary_replay_on_empty()` : quand le canari post-merge est rouge avec zéro
   test exécuté ET sans signature infra connue, la venv du workspace est purgée
   (le runner frontend soigne lui-même son `node_modules`) et la suite rejouée
   UNE fois avant de croire au verdict `semantic`. Vert -> merge conservé,
   `infra_retries += 1`, verdict `infra_healed` ; rouge avec signature ->
   `infra_persistent` ; rouge sinon -> `semantic` (inchangé). Nouvel événement
   monitor `canary` / `verdict="empty_replay"`.
2. **FUSION P0-B - budget de requeue séparé.** Un conflit de merge ou un revert
   post-canari ne consomme plus de tentative dev : la tentative est remboursée
   (`_refund_dev_attempt`) et un budget dédié est débité
   (`_consume_requeue_budget`). Nouveaux champs `Task.requeue_attempts`,
   `UserStory.requeue_attempts`, `PlanCalibration.requeue_refunds`.
   `REQUEUE_MAX=0` rend un premier conflit terminal.
3. **WORKFLOW P1 - un rouge sans test exécuté est un échec infra.**
   `Pipeline._areplay_empty_red()` : après un run de vérification RÉEL rouge
   avec zéro test, purge de la venv du worktree puis un seul rejeu. Toujours
   vide -> remboursement de la tentative dev, `infra_attempts += 1`, requeue
   tant que `infra_max_retries` le permet. Événement monitor `empty_red` /
   `phase="replay"`. Les rouges avec de vrais échecs sont inchangés.
4. **FUSION P1-C - chemin critique et bonus de tentative.** `streams.fanout()`
   (fan-out transitif par work item, tolérant aux cycles) et
   `scheduler.rank_ready()` (ordonne les items READY par fan-out décroissant,
   puis priorité, puis ordre topologique ; n'écarte jamais un item) sont câblés
   dans `_abuild_phase_streams`. `scheduler.fanout_bonus_attempts()` donne UNE
   tentative dev de plus (`_max_attempts_for`) et UN requeue de fusion de plus
   (`_requeue_max_for`) aux items qui bloquent au moins
   `FANOUT_BONUS_THRESHOLD` items. Readiness, plancher d'indépendance, mode
   strict après conflit et plafond `max_parallel_devs` sont intacts.
5. **FUSION P1-B - plus de slot dev tenu pendant le merge.**
   `Pipeline._holds_dev_slot()` + `_DEV_SLOT_STAGES` : MERGE_WAIT / MERGING /
   DONE / FAILED ne comptent plus dans le remplissage des slots, sous un
   plafond DUR de `max_parallel_devs + 1` workers en vol. Le plancher
   d'indépendance voit toujours TOUS les workers en vol. Complément
   indispensable : l'événement `Pipeline._slot_released` (posé par `_set_stage`
   à chaque sortie des étapes dev, attendu à côté des workers dans le
   `asyncio.wait` de fin de passe), sans quoi la libération serait inerte (la
   boucle ne se réveillait que sur le retour complet d'un worker).
6. **WORKFLOW P3 / P4 - dégradations silencieuses.** `_aarchitect_phase` émet
   désormais une notification `warning` + un message chat quand l'architecte est
   indisponible. `Pipeline._note_refine_degraded()` émet l'événement monitor
   `refine_degraded` (champs `role`, `reason`) + un message chat quand le
   critique du harnais refine est indisponible (`stopped_reason ==
   "critic_error"`), pour les rôles `po` et `dev`.
7. **WORKFLOW P7 - reprise de fenêtre d'usage re-sondée.**
   `session_monitor.await_window()` dort par tranches et re-sonde ccusage ;
   elle n'accepte une nouvelle estimation que si elle est strictement plus
   proche ET strictement future, donc l'attente ne peut que raccourcir. Câblée
   dans `pipeline._aresume_timer` (minutes converties en secondes), avec
   re-sondage forcé à 0 quand `session_monitor.monitor_active()` est faux, donc
   aucun sous-processus ccusage depuis un run de test ou un provider non-claude.

#### Flags (tous dans `autospec/config.py`, documentés dans `backend/.env` et `backend/.env.example`, épinglés dans `tests/conftest.py::tmp_workspace`)

| Champ Settings | Variable d'env | Défaut code | Épinglé en test |
| --- | --- | --- | --- |
| `canary_replay_on_empty` | `CANARY_REPLAY_ON_EMPTY` | `True` | `False` |
| `requeue_max` | `REQUEUE_MAX` | `3` (min 0) | `3` |
| `empty_red_is_infra` | `EMPTY_RED_IS_INFRA` | `True` | `False` |
| `fanout_first_enabled` | `FANOUT_FIRST` | `True` | `True` |
| `fanout_bonus_threshold` | `FANOUT_BONUS_THRESHOLD` | `5` (min 0) | `5` |
| `slot_release_on_merge` | `SLOT_RELEASE_ON_MERGE` | `True` | `True` |
| `resume_reprobe_min` | `RESUME_REPROBE_MIN` | `30` min (min 0) | `0` |

`backend/.env` et `backend/.env.example` ne sont pas suivis par git : la
documentation des variables existe sur disque mais n'apparaîtra pas dans le
commit.

#### Fichiers modifiés

- `backend/autospec/config.py` (+61) : les 7 champs ci-dessus.
- `backend/autospec/models.py` (+9) : `requeue_attempts` (Task, UserStory),
  `requeue_refunds` (PlanCalibration).
- `backend/autospec/orchestrator/pipeline.py` (+452 / -21) : `_holds_dev_slot`,
  `_DEV_SLOT_STAGES`, `_slot_released`, `_refund_dev_attempt`,
  `_consume_requeue_budget`, `_note_suite_outcome`, `_areplay_empty_red`,
  `_fanout_bonus_for`, `_max_attempts_for`, `_requeue_max_for`,
  `_acanary_replay_on_empty`, `_note_refine_degraded`, câblage de
  `rank_ready`/`fanout` et de `await_window`.
- `backend/autospec/orchestrator/scheduler.py` (+88) : `rank_ready`,
  `fanout_bonus_attempts`.
- `backend/autospec/orchestrator/streams.py` (+18) : `fanout`.
- `backend/autospec/orchestrator/session_monitor.py` (+54) : `await_window`.
- `backend/tests/conftest.py` (+30) : épinglage des 7 flags.
- `backend/tests/test_streams_build.py` (+19 / -6) : DEUX tests historiques
  adaptés à la sémantique P0-B (un conflit ne consomme plus de tentative dev).
- `backend/.env`, `backend/.env.example` (non suivis par git).

#### Tests ajoutés (7 fichiers, 80 fonctions de test)

- `tests/test_wave1_canary_replay.py` (8) : P0-A.
- `tests/test_wave1_silent_degradation.py` (5, dont une paramétrée x4) :
  WORKFLOW P3 / P4.
- `tests/test_wave1_requeue_budget.py` (9) : P0-B + WORKFLOW P1.
- `tests/test_wave1_rank_ready.py` (21) : `fanout`, `rank_ready`,
  `fanout_bonus_attempts` (fonctions pures).
- `tests/test_wave1_fanout.py` (13) : câblage P1-C dans le pipeline.
- `tests/test_wave1_slot_release.py` (14, dont une paramétrée sur les 9
  `BuildStage`) : P1-B + câblage P7.
- `tests/test_wave1_reprobe.py` (10) : `await_window`.

#### Points d'attention restants

1. **Ne JAMAIS lancer `uv run ruff check` sous `Brainstorming/`** sans
   `--no-fix` : le `pyproject.toml` parent pose `[tool.ruff] fix = true`, donc
   un simple `check` RÉÉCRIT les fichiers en silence (un passage a reformaté
   214 lignes de `pipeline.py` et supprimé des `# noqa: BLE001`).
2. **Trois défauts de production ne sont pas exercés par la suite** :
   `canary_replay_on_empty`, `empty_red_is_infra` et `resume_reprobe_min` sont
   épinglés OFF dans la conftest (les tests dédiés les activent explicitement).
   C'est volontaire : ces flags ajoutent un second run de suite ou un
   sous-processus, ce qui ferait basculer des dizaines de tests existants.
3. **Le rejeu vert court-circuite les gates internes à `_arun_item_dev`** (UI
   tests, gate de couverture, refine dev, mutation testing) : quand un rouge
   vide repasse au vert, l'item part directement en commit + merge. Acceptable
   (ces gates n'avaient aucun verdict non plus), mais à connaître.
4. **La protection « rouge vide » est inerte si aucun run RÉEL n'a été
   observé** (clé `_empty_red` absente, cas des tests qui stubbent
   `_arun_item_dev`). Tout futur appelant qui contourne
   `_arun_item_dev`/`_averify_resumed` n'en bénéficiera pas.
5. **`refine.arefine` ne remonte jamais `stopped_reason == "critic_error"`
   aujourd'hui** (seul `arefine_critic_first` le fait, et son unique appelant
   est `plan_pipeline.py`, hors périmètre). `_note_refine_degraded` est donc
   défensif sur les chemins `_arefine_plan` / `_arefine_code` : à finir de
   câbler.
6. **La libération de slot n'achète qu'UN worker de plus** (`cap + 1` en vol au
   total). Avec une file de merge longue, le build sérialise toujours derrière
   le verrou de merge ; un vrai pool de merge est un chantier séparé.
7. **`fanout(graph)` est en O(N x E)** et tourne une fois par passe de
   scheduler (donc une fois par slot libéré). C'est l'étape Python la plus
   chère de la boucle sur un gros plan ; elle est sautée quand les deux flags
   P1-C sont éteints.
8. **Coût de l'événement `_slot_released`** : avec P1-B actif, une étape
   terminale (DONE/FAILED) déclenche aussi l'événement, soit UNE passe de
   scheduler supplémentaire (un `build_work_graph`) juste avant le retour du
   worker. Mesurable mais faible ; nul quand le flag est éteint.
9. **Le chemin hérité `_abuild_story`** (streams désactivés) ne reçoit ni
   libération de slot ni bonus de fan-out : il garde sa sémaphore et
   `dev_max_attempts`. Il bénéficie en revanche du rejeu « rouge vide ».
10. **Deux assertions temporelles** de `test_wave1_slot_release.py` (12 tours
    de boucle d'événements) pourraient donner un faux VERT sous charge extrême
    (jamais un faux rouge) ; le plafond dur est doublé par les tests unitaires
    déterministes de `_holds_dev_slot`.
11. **Le repli `semantic` après un rejeu raté rapporte la sortie du PREMIER
    run** (`output[-1500:]`), pas celle du rejeu. Le verdict est correct, seul
    le diagnostic affiché est le plus ancien.

