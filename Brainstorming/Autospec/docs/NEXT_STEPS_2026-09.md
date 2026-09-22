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


### Vague 2 (2026-09-22)

**Statut : livrée et validée. Suite backend complète : 1318 passed, 0 failed
(195,99 s, `uv run pytest -q -p no:cacheprovider`). AUCUNE correction de gate
n'a été nécessaire : la suite est passée verte du premier coup, avec les 6
agents de la vague (W, S1, S2, S3, S4, M) intégrés dans le même arbre de
travail. Rappel : la vague 1 finissait à 1254 tests, la vague 2 en ajoute 64.**

#### Items livrés

1. **FUSION P1-A - canari post-merge par rafale.** Sous contention du verrou de
   merge, les merges qui arrivent ensemble forment une rafale (`_CanaryBatch` /
   `_CanaryEntry`) vérifiée par UN SEUL run de suite au lieu d'un par merge. Le
   dernier worker encore dans la phase de merge (`_merge_queue == 1`) règle la
   rafale ; les autres se garent en `BuildStage.MERGING` et attendent leur
   future. Rouge sémantique -> bisect par revert du merge le PLUS RÉCENT vers le
   plus ancien (`_abisect_canary_batch`), avec rejeu de confirmation après
   chaque revert sauf sur la plus ancienne entrée (c'est cette exception qui
   rend une rafale de taille 1 strictement identique, en coût comme en
   comportement, au chemin historique). Verdicts infra diffusés tels quels.
   Nouveaux helpers : `_anote_merge_sha`, `_acanary_verdict`,
   `_abandon_canary_batch`, `_adrain_canary_batch`, `_asettle_canary_batch`,
   `_publish_canary`. `_OwnedLock` expose désormais `waiters`.
   Nouveaux événements monitor `canary` : `batched`, `batch_green`,
   `bisect_revert`. Nouveaux compteurs `PlanCalibration.canary_batches` et
   `canary_bisect_reverts`.
2. **FUSION P2-A - rebuild SOLO en dernier recours.** Sur un échec de fusion
   PERSISTANT (conflit de merge ou revert post-canari) et une fois le budget de
   requeue épuisé, l'item n'est plus déclaré FAILED tout de suite : il obtient
   UNE reconstruction seule sur le HEAD final. `_mark_solo_retry` le remet en
   TODO/QUEUED sans consommer de budget ; le scheduler ne démarre plus rien à
   côté d'un solo en vol et fait attendre l'item solo que TOUS les workers aient
   atterri (`_solo_ids`, `_solo_running`). La tentative est dépensée au
   DÉMARRAGE (`solo_attempted = True`), donc pas de boucle possible. Le solo
   repasse par `_aresume_green_branch` + `_averify_resumed` (rebase +
   re-vérification + merge, AUCUN run dev). Nouveaux champs
   `Task.solo_attempted`, `UserStory.solo_attempted`,
   `PlanCalibration.solo_requeues`. Nouvel événement monitor `solo_retry`.
   Ordre final du repli : budget de requeue -> SOLO -> split -> FAILED.
3. **FUSION P2-B - cache npm partagé.** `_anpm_install_in` ajoute
   `--cache <workspace_root résolu>/_npm-cache --prefer-offline` à l'argv npm et
   crée le dossier à la demande ; un `OSError` sur le mkdir n'est jamais fatal
   (log + repli sur le cache npm par défaut). `node_modules` reste par worktree,
   seul le cache de téléchargement est partagé. `_npm-cache` est invisible pour
   `storage.list_states()`, comme `_worktrees`.
4. **FUSION P3 - observabilité de la boucle de fusion.** Trois compteurs sur
   `PlanCalibration` : `suite_runs` (incrémenté DANS `_arun_pytest` et
   `_arun_frontend_tests`, après les court-circuits démo, donc jamais chez les
   appelants), `canary_verdicts` (histogramme `dict[str, int]` alimenté aux 9
   sites d'émission `monitor.event("canary", verdict=...)` plus le vert), et
   `items_delivered` (incrémenté au seul endroit où un work item devient livré).
   Propriété calculée `suites_per_item`. Exposition : nouveau bloc `fusion` dans
   `metrics.compute_metrics()` (donc dans `GET /api/metrics`, sans
   `response_model` à modifier) via le nouvel helper public
   `metrics.fusion_snapshot()` + la constante `metrics.FUSION_COUNTERS`, et le
   même bloc (itération courante seulement) dans `prompts.retro_review()`, avec
   une instruction qui interdit à l'agent rétro de transformer une boucle de
   fusion infra en leçon « code ». `pattern_detector.aggregate_signals()` a dû
   être adapté : il sommait TOUS les champs de `PlanCalibration`, ce qui plantait
   sur le premier champ de type `dict` ; il ne totalise plus que les champs
   annotés `int` et fusionne l'histogramme dans une clé sœur.
5. **FACTORY #4 - CLI générée qui parle.** `workspace.MAIN_TEMPLATE` est
   réécrit en vrai point d'entrée : `main(argv=None) -> int`, découverte des
   hooks via `features.discover()`, relais d'argv aux hooks qui l'acceptent
   (`inspect.signature`, un hook `register()` historique reste appelé sans
   argument), bannière sur `-h` / `--help` ou sur un lancement nu sans
   consommateur, code de sortie piloté par le premier `int` non nul retourné
   (les `bool` sont exclus), `SystemExit` propagé. Côté gate, nouveau sondage
   `Pipeline._smoke_cli_help_run` : la branche CLI du smoke rejoue le MÊME
   lanceur avec `--help` et exige code 0 ET une sortie standard non vide.
   Point critique : stdout et stderr sont capturés SÉPARÉMENT, sinon les lignes
   de démarrage de `uv run` (« Creating virtual environment at: .venv ») feraient
   passer n'importe quel CLI muet. La branche web n'est pas touchée.
6. **TS extraites avec critères d'acceptance.** `_technical_story_evidence`
   donne à toute Technical Story au moins un critère : ceux de la tâche en échec
   (copie PROFONDE, la TS ne peut pas muter la tâche) sinon un critère
   synthétique `<TS id>.AC-1` dérivé du contrat. La TS reçoit AUSSI un Gherkin
   technique : c'est indispensable, des critères seuls auraient troqué
   l'avertissement `no_acceptance_criteria` contre le BLOQUANT
   `no_acceptance_evidence` sur les profils qui forcent `DOD_STRICT_CRITERIA`
   (web-ssr, fullstack). Résultat : la TS ne lève plus AUCUN problème DoD.
7. **Balayage des orphelins de workspace au démarrage.**
   `Pipeline._sweep_workspace_orphans(ws_root)` réutilise les primitives de
   `_kill_workspace_port_holders` (une sonde PowerShell/CIM sur Windows,
   `ps -eo pid=,ppid=,command=` sur POSIX) mais SANS condition de port : seul un
   processus dont la ligne de commande contient la racine de workspace résolue
   est candidat, le pid courant et TOUTE sa chaîne d'ancêtres sont retirés des
   candidats AVANT quoi que ce soit, et les survivants sont repliés sur leurs
   ancêtres les plus hauts. Câblé dans `server._arecover_projects()` APRÈS
   `list_states` et AVANT `recover_projects`, via `asyncio.to_thread`, muet en
   mode `fake_agents` ou flag éteint, et incapable de faire échouer la reprise.
8. **D11 - consolidation du statut stocké d'une story décomposée.** Le statut
   stocké d'une story qui possède des tâches est consolidé exactement UNE fois,
   par la tâche qui atterrit en dernier (`_aconsolidate_story_status`, sous
   `_merge_lock`, ce qui donne la garantie d'unicité même quand plusieurs tâches
   de la même story finissent dans la même rafale P1-A). Les deux autres
   émetteurs de « story <id> done » (`_abuild_story`,
   `_amaybe_arbitrate_wrong_test`) sont gardés par `_story_rollup_incomplete`.
   `arebuild_task` annule la consolidation (`_unconsolidate_story`).

#### Flags (tous dans `autospec/config.py`, documentés dans `backend/.env` et `backend/.env.example`, épinglés dans `tests/conftest.py::tmp_workspace`)

| Champ Settings | Variable d'env | Défaut code | Épinglé en test |
| --- | --- | --- | --- |
| `canary_batch_enabled` | `CANARY_BATCH` | `True` | `True` |
| `solo_on_conflict` | `SOLO_ON_CONFLICT` | `True` | `False` |
| `npm_shared_cache` | `NPM_SHARED_CACHE` | `True` | `True` |
| `consolidate_story_status` | `CONSOLIDATE_STORY_STATUS` | `True` | `True` |
| `ts_acceptance_criteria` | `TS_ACCEPTANCE_CRITERIA` | `True` | `True` |
| `smoke_cli_help` | `SMOKE_CLI_HELP` | `True` | `True` |
| `orphan_sweep_on_boot` | `ORPHAN_SWEEP_ON_BOOT` | `True` | `False` |

Deux épinglages ne sont pas au défaut de production, et pour deux raisons
différentes :

- `solo_on_conflict` est OFF parce que le solo insère UNE reconstruction de plus
  entre le budget de requeue épuisé et la fin historique, ce qui changerait les
  comptes de merges de `test_wave1_requeue_budget.py` (2 -> 3 et 1 -> 2). Les
  tests du chemin solo activent le flag explicitement.
- `orphan_sweep_on_boot` est OFF pour une raison de SÛRETÉ, pas d'herméticité :
  le balayage lance PowerShell/`ps` et tue de vrais arbres de processus, ce
  qu'une suite de tests ne doit jamais faire.

`backend/.env` et `backend/.env.example` ne sont pas suivis par git : la
documentation des 7 variables existe sur disque mais n'apparaîtra pas dans le
commit.

#### Fichiers modifiés

- `backend/autospec/orchestrator/pipeline.py` (+757 / -18) : P1-A (rafale de
  canari, bisect, `_OwnedLock.waiters`), P2-A (solo + scheduler), P2-B (cache
  npm), P3 (`_count_suite_run`, `_count_canary`, `items_delivered`), D11
  (`_aconsolidate_story_status`, `_story_rollup_incomplete`,
  `_unconsolidate_story`), FACTORY #4 (`_smoke_cli_help_run`), critères de TS
  (`_technical_story_evidence`), balayage (`_sweep_workspace_orphans`).
- `backend/autospec/config.py` (+77) : les 7 champs ci-dessus.
- `backend/autospec/models.py` (+27) : `Task.solo_attempted`,
  `UserStory.solo_attempted`, et sur `PlanCalibration` `canary_batches`,
  `canary_bisect_reverts`, `solo_requeues`, `suite_runs`, `canary_verdicts`,
  `items_delivered`, `suites_per_item` (champ calculé).
- `backend/autospec/metrics.py` (+54 / -1) : `FUSION_COUNTERS`,
  `fusion_snapshot()`, bloc `fusion` dans `compute_metrics`.
- `backend/autospec/agents/prompts.py` (+18) : bloc `fusion` dans les signaux de
  `retro_review` + la règle « signaux de fusion ».
- `backend/autospec/orchestrator/pattern_detector.py` (+15 / -2) :
  `aggregate_signals` ne somme plus que les champs `int` et fusionne
  `canary_verdicts` dans une clé dédiée.
- `backend/autospec/api/server.py` (+33 / -1) : `_asweep_workspace_orphans`
  appelé depuis `_arecover_projects`.
- `backend/autospec/orchestrator/workspace.py` (+79 / -6) : `MAIN_TEMPLATE`
  réécrit en point d'entrée CLI, `FEATURES_INIT_TEMPLATE` documente le contrat
  de signature des hooks.
- `backend/tests/conftest.py` (+39) : épinglage des 7 flags, chacun avec le
  commentaire qui explique le choix.
- `backend/.env`, `backend/.env.example` (non suivis par git).

Aucun fichier n'a changé de convention de fin de ligne :
`backend/autospec/orchestrator/pipeline.py` est toujours 100 % CRLF (9762
lignes, 9762 CRLF, 0 LF isolé), `tests/conftest.py` aussi (213/213), et les
fichiers qui étaient LF le sont restés. Zéro tiret cadratin ajouté
(`git diff -U0 -- backend/ | grep '^+'` n'en contient aucun).

#### Tests ajoutés (9 fichiers, 64 fonctions de test)

- `tests/test_wave2_canary_batch.py` (6) : P1-A, dont une rafale de 3 merges
  RÉELLEMENT sérialisés sous `_merge_lock` vérifiée par un seul run, le bisect
  qui ne reverte que le coupable (avec le SHA capturé sous le verrou), la rafale
  abandonnée qui ne bloque personne, et deux tests unitaires de
  `_OwnedLock.waiters`.
- `tests/test_wave2_solo.py` (5) : P2-A, dont le solo qui remplace FAILED sans
  relancer de dev, le flag OFF, l'absence de boucle, et les deux invariants de
  scheduler (rien ne démarre à côté d'un solo, un solo attend que tout ait
  atterri).
- `tests/test_wave2_npm_cache.py` (3) : P2-B, argv capturé, flag OFF, racine de
  workspace relative résolue en absolu.
- `tests/test_wave2_fusion_observability.py` (7) : P3 (compteurs, site de
  comptage épinglé sur le VRAI `_arun_pytest`, `suites_per_item`) et D11
  (consolidation par la dernière tâche, flag OFF, garde de rollup, annulation
  par `arebuild_task`).
- `tests/test_wave2_metrics_fusion.py` (7) : exposition P3 dans
  `compute_metrics` et `retro_review`, tolérance aux états pré-P3, ratio calculé
  sur les TOTAUX et pas sur la moyenne des ratios.
- `tests/test_wave2_cli_scaffold.py` (11) : contrat du `main.py` généré
  (sous-processus réels, `PYTHONUTF8=1`).
- `tests/test_wave2_smoke_cli.py` (8) : sondage `--help`, dont le piège du bruit
  stderr et l'absence de sondage sur un produit web.
- `tests/test_wave2_ts_criteria.py` (6) : critères hérités/synthétiques, copie
  profonde, Gherkin technique, DoD strict silencieuse, flag OFF.
- `tests/test_wave2_orphan_sweep.py` (11) : périmètre du balayage, remontée aux
  ancêtres, protection du processus courant et de ses ancêtres, branche POSIX,
  sonde en échec, câblage au démarrage.

#### Corrections de gate

Aucune. Contrairement à la vague 1, aucun test historique n'a dû être adapté par
la gate : les deux seuls tests qui auraient contredit la nouvelle sémantique
(`test_wave1_requeue_budget.py` pour le solo,
`test_generation_hardening.py::test_semantic_conflict_is_reverted_and_requeued`
pour la rafale) ont été traités pendant la vague elle-même, l'un par un
épinglage OFF documenté, l'autre par la règle « pas de rejeu de confirmation sur
la plus ancienne entrée d'une rafale ».

#### Points d'attention restants

1. **`SMOKE_CLI_HELP` est un vrai DURCISSEMENT de gate, actif par défaut.** Un
   projet CLI dont le `main.py` ne répond rien sur `--help` échoue désormais au
   smoke alors qu'il passait avant. C'est l'effet recherché, mais un projet
   brownfield importé ou un `main.py` en boucle de démon se mettra à échouer.
   Repli : `SMOKE_CLI_HELP=0`.
2. **`REQUEUE_MAX=0` n'est plus terminal au premier conflit** quand
   `SOLO_ON_CONFLICT=1` (défaut) : l'item garde son unique rebuild solo, donc 2
   tentatives de merge au lieu d'une. Un opérateur strict doit maintenant poser
   les deux variables.
3. **LE BALAYAGE TUE DE VRAIS PROCESSUS ET EST ACTIF PAR DÉFAUT.** Sa seule
   garde est « la ligne de commande contient la racine de workspace résolue »,
   en comparaison de sous-chaîne insensible à la casse. Une `WORKSPACE_ROOT`
   trop large, ou qui est le préfixe d'un autre chemin réel, élargit d'autant la
   cible. À regarder une fois avant le premier démarrage supervisé avec ce flag.
   La remontée pid -> ppid est également sensible à la RÉUTILISATION DE PID
   (faiblesse héritée de `_kill_workspace_port_holders`, mais avec un ensemble
   de candidats bien plus large).
4. **La sonde Windows doit continuer à renvoyer la table de processus
   COMPLÈTE** (chaque pid, avec un drapeau 0/1 « dans le workspace »). Si une
   optimisation future refiltre côté CIM, la chaîne d'ancêtres n'est plus
   reconstructible et le balayage peut tuer le shell ou l'IDE qui a lancé le
   backend. Garde-fou :
   `test_the_current_process_and_its_ancestors_are_never_killed`.
5. **`os.path.realpath` (et pas `Path(...).resolve()`) dans
   `_sweep_workspace_orphans` est délibéré** : `pathlib` arbitre sur `os.name`
   au moment de l'appel, donc le test de la branche POSIX (qui monkeypatche
   `os.name`) plante sur Windows avec `UnsupportedOperation`. Ne pas
   « moderniser ».
6. **La décision de rafale repose sur `self._merge_queue > 1`, PAS sur
   `_OwnedLock.waiters`** (qui compte aussi `_aworktree_add`,
   `_arevert_head_merge`, le commit de feature et, depuis D11, la consolidation
   de story). Toute modification qui déplacerait la lecture de `contended` hors
   de sa position actuelle (dans le `try`, sans `await` entre la libération du
   verrou et la lecture) rendrait le batching à la fois faux et exposé à un
   blocage. Invariant épinglé par
   `test_a_released_lock_still_shows_its_queue_in_the_same_step`.
7. **Si la règle « pas de rejeu de confirmation sur la plus ancienne entrée »
   disparaît du bisect**, une rafale de taille 1 coûte un run de suite de plus
   et `test_generation_hardening.py::test_semantic_conflict_is_reverted_and_requeued`
   repasse au rouge (3 runs au lieu de 2).
8. **`suite_runs` compte des SUITES DEMANDÉES, pas des processus.** Un rejeu
   flaky à l'intérieur d'un `_arun_pytest`, ou Vitest + le build de production
   dans un `_arun_frontend_tests`, n'ajoutent qu'une unité. Un tableau de bord
   doit écrire « suites demandées », jamais « processus de test ».
9. **`items_delivered` n'est incrémenté que par le chemin streams.** Sur un
   projet construit par le chemin séquentiel hérité, `suites_per_item` dégénère
   en `suite_runs / 1`, et `compute_metrics` agrégeant TOUS les projets, un seul
   projet hérité gonfle le ratio global. À affiner en vague 3 (ratio par projet,
   ou exclusion des états à `items_delivered == 0`).
10. **DEUX endroits à mettre à jour pour tout nouveau compteur de
    `PlanCalibration`** : `metrics.FUSION_COUNTERS` (sinon le compteur est
    absent de `/api/metrics` et de la rétro) et le filtre « champs annotés
    `int` » de `pattern_detector.aggregate_signals` (qui DÉPOSE silencieusement
    tout champ non-`int` au lieu de planter). Les deux échouent en silence.
11. **Le contrat frontend n'est pas à jour** : `frontend/src/types.ts`
    (`export interface Metrics`) n'expose pas le bloc `fusion`. Rien ne casse,
    mais aucune UI ne peut le lire tant que l'interface n'est pas étendue. C'est
    le premier item de la vague 3.
12. **`aforce_done_task` / `aforce_done_story` ne sont pas câblés à la
    consolidation D11** : forcer manuellement la dernière tâche d'une story
    laisse le statut stocké du conteneur non consolidé et n'émet pas de commit
    de rollup. C'est le trou restant de D11.
13. **Les deux émetteurs hérités de « story <id> done » ne sont gardés que sur
    le COMMIT, pas sur `story.status = DONE`.** `_abuild_story` écrit toujours
    DONE sur un conteneur construit d'un bloc : sur le chemin hérité,
    `effective_status()` reste la source de vérité, pas le statut stocké.
14. **Les hooks de features tournent AUSSI sur `--help`** dans le `main.py`
    généré (c'est ce qu'exige le critère d'acceptance « les deux formes de hook
    sont appelées »). Une feature dont le `register()` a de vrais effets de bord
    s'exécute donc sur `python main.py --help`. Si c'est jugé dangereux, le
    changement est d'une ligne dans `MAIN_TEMPLATE`, au prix d'un test à
    assouplir.
15. **FACTORY #4 n'est clos que pour le profil Python.** `GO_MAIN_TEMPLATE` et
    `RUST_MAIN_TEMPLATE` génèrent toujours un binaire muet ; `_asmoke_phase`
    saute de toute façon les langages non-Python.
16. **`_solo_ids` n'est qu'en mémoire** (comme `_conflict_retry_ids`) : un
    arrêt/relance entre l'octroi et le lancement perd le solo en attente.
    `solo_attempted` est persisté, donc pas de second octroi après une telle
    relance ; la dégradation est le chemin historique.
17. **Le maintien du solo est fondé sur `running`, pas sur une réservation** :
    tant qu'un solo attend, le scheduler continue à démarrer d'AUTRES items
    prêts. Pas de famine en pratique (le backlog est fini et l'item solo est
    repris à chaque passe), mais il n'y a pas de compteur d'équité.
18. **`<workspace_root>/_npm-cache` doit être exclu de toute future routine
    « nettoyer la racine de workspace »**, sinon chaque projet repaie le coût de
    téléchargement.
19. **Cinq flags de production ne sont toujours pas exercés par la suite**
    (épinglés OFF dans la conftest) : `canary_replay_on_empty`,
    `empty_red_is_infra`, `resume_reprobe_min` (vague 1), `solo_on_conflict` et
    `orphan_sweep_on_boot` (vague 2). Les tests dédiés les activent
    explicitement, mais la combinaison « tout à ON » n'est jamais jouée par la
    suite : c'est le rôle du run démo de la vague 4.
20. **Toujours interdit** : `uv run ruff check` sans `--no-fix` sous
    `Brainstorming/` (le `pyproject.toml` parent pose `fix = true` et réécrit
    les fichiers en silence).
