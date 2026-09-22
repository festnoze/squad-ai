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

### Vague 3 (2026-09-22)

**Statut : livree et validee. Backend complet : 1328 passed, 0 failed
(757,18 s, `uv run pytest -q -p no:cacheprovider`) ; vitest : 28 fichiers,
264 passed, 0 failed ; `npx tsc --noEmit -p .` : exit 0 ; e2e Playwright :
2 passed (39,4 s) ; e2e streams : 1 passed (13,1 s). UNE correction de gate a
ete necessaire (voir plus bas) : la selection conditionnelle de l'onglet
« Vision produit » introduite avec R3 ne memorisait pas le choix quand l'onglet
etait deja actif, et le board disparaissait en plein `wait` de 60 s.**

#### Items livres

1. **R6 backend - corbeille de stories.** `DELETE /api/projects/{pid}/stories/{sid}`
   ne perd plus la story quand `SOFT_DELETE_STORIES` est ON (defaut) : elle sort
   toujours de `state.stories` et son `.feature` est toujours supprime, mais elle
   est deposee dans `ProjectState.trash` (nouveau modele `TrashedStory` :
   `story`, `deleted_at` epoch, `stripped_deps` = les `depends_on` retires chez
   les autres stories, `feature_rel_path`). La corbeille est bornee a 20 entrees
   (`pipeline.TRASH_MAX`), les plus anciennes purgees. Reponse inchangee. Flag
   OFF = suppression dure historique, a l'octet pres.
2. **R6 backend - restauration.** `Pipeline.arestore_story(sid)` remet la story
   en TODO/QUEUED (attempts, infra, requeue remis a zero, taches reinitialisees
   par `_reset_for_restore`), re-tisse les `depends_on` retires chez les stories
   encore presentes, re-ecrit le `.feature` si gherkin, consomme l'entree de
   corbeille et `_sync()`. Refus 409 pendant les phases
   spec/analyze/plan/architect/build (`_BACKLOG_BUSY_PHASES`) ou si l'id est
   repris ; 404 si la story n'est pas dans la corbeille.
3. **R6 frontend - annuler une suppression.** Le bus de toasts porte desormais
   une action optionnelle (`ToastAction`), rendue par App comme un bouton
   (`data-testid="toast-action"`, duree portee a 10 s, toast ferme au clic).
   Supprimer une US depuis son detail emet un toast de succes avec un bouton
   « Annuler » / « Undo » qui appelle `restoreStory`. Un panneau repliable
   « Corbeille » en bas du board liste `project.trash` avec un bouton
   « Restaurer » par entree.
4. **P5 frontend - re-verifier la livraison.** Nouveau bouton
   `data-testid="verify-delivery"` dans la RunPanel, visible seulement sur une
   phase dormante ET avec au moins une story au statut EFFECTIF `done`. Il
   appelle `POST /api/projects/{pid}/verify` et rend le resultat par une paire
   de toasts succes/erreur (pas la banniere d'erreur globale).
5. **P3 frontend - boucle de fusion au dashboard.** Nouveau bloc
   `data-testid="dashboard-fusion"` sous la grille existante, rendu uniquement
   quand `GET /api/metrics` sert la cle `fusion` (ajoutee en vague 2) : 7 cartes
   (suites par item livre, items livres, suites jouees, requeues / remboursements,
   reverts canari, rafales / reverts bisect, retries infra) plus la liste des
   verdicts canari triee par frequence (`data-testid="fusion-verdicts"`, masquee
   si l'histogramme est vide).
6. **R3 frontend - lentille initiale du workspace.** `WorkspaceViews` ne choisit
   plus sa vue avec `phase === "build"` mais avec une regle a trois etages :
   (1) le choix d'onglet explicite memorise par projet dans
   `localStorage["autospec-view:<projectId>"]` gagne ; sinon (2) « Activite » des
   qu'un build a commence ou eu lieu (`hasBuildActivity`) ; sinon (3) « Vision
   produit ». Une bascule automatique UNIQUE vers Activite a l'entree en phase
   build, desactivee des que l'operateur a choisi un onglet pour ce projet.

#### Contrats exposes

Backend :

- `TrashedStory` (`autospec/models.py`) : `{story: UserStory, deleted_at: float,
  stripped_deps: dict[str, list[str]], feature_rel_path: str}`.
- `ProjectState.trash: list[TrashedStory]` - plus ancienne en tete, plafonnee a
  20, serialisee sous la cle `trash` dans tout etat pousse (GET
  `/api/projects/{pid}` et SSE).
- `POST /api/projects/{pid}/stories/{sid}/restore` -> `{ok: true, state}` ;
  404 « Story absente de la corbeille » ; 409 pipeline active ou id repris.
- `GET /api/projects/{pid}/trash` -> `{items: [{id, title, epic_id, deleted_at}]}`,
  ordonne de la suppression LA PLUS RECENTE a la plus ancienne (l'ordre inverse
  de `state.trash`).
- `Settings.soft_delete_stories` / env `SOFT_DELETE_STORIES` (defaut 1),
  documente dans `backend/.env.example`, pose dans `backend/.env`, epingle dans
  `tests/conftest.py::tmp_workspace`.
- `Pipeline.arestore_story(sid) -> UserStory`, constantes `pipeline.TRASH_MAX`
  et `pipeline._BACKLOG_BUSY_PHASES`, helper `pipeline._reset_for_restore`.

Frontend :

- `api.ts` : `restoreStory(projectId, storyId)`, `getTrash(projectId)`,
  `verifyDelivery(projectId)`.
- `types.ts` : `TrashedStoryInfo`, `ProjectState.trash?`, `toTrashInfo()`
  (accepte la forme plate du endpoint ET la forme imbriquee de l'etat SSE),
  `FusionMetrics`, `Metrics.fusion?`.
- `toast.ts` : `ToastAction {label, onClick}`, `ToastEvent.action?`,
  `notify(level, title, body, action?)`.
- Props : `Board.trash?`, `WorkspaceViews.trash?`, `RunPanel.onVerifyDelivery`
  (REQUISE).
- `data-testid` : `toast-action`, `trash-panel`, `trash-restore-<storyId>`,
  `verify-delivery`, `dashboard-fusion`, `fusion-verdicts`.
- Cles i18n (en + fr) : `common.undo` ; `board.deletedToastTitle`,
  `deletedToastBody`, `restoredToast`, `restoreFailed`, `trashTitle`,
  `trashRestore` ; `runPanel.verifyDelivery`, `verifyDeliveryTitle` ;
  `app.verifyToastTitle`, `verifyToastBody`, `verifyToastErrorTitle` ;
  `dashboard.fusionTitle`, `fusionSuitesPerItem`, `fusionItemsDelivered`,
  `fusionSuiteRuns`, `fusionRequeues`, `fusionCanaryReverts`, `fusionBatches`,
  `fusionInfraRetries`, `fusionVerdicts`.
- `localStorage["autospec-view:<projectId>"]` -> `vision | iterations | activity
  | graph`, ecrit au clic d'onglet uniquement, lectures et ecritures en
  try/catch, valeurs inconnues ignorees.
- CSS (tokens existants uniquement, aucune animation, aucun nouveau canal
  `--attention`) : `.toast-action`, `.board-trash-wrap`, `.board-trash`,
  `.trash-list`, `.trash-row`, `.trash-title`, `.fusion-block`, `.fusion-title`,
  `.fusion-subtitle`, `.fusion-verdicts`, `.fusion-verdict-key`,
  `.fusion-verdict-count`.

#### Fichiers modifies

Backend : `autospec/models.py`, `autospec/config.py`,
`autospec/orchestrator/pipeline.py`, `autospec/api/server.py`, `.env.example`,
`.env`, `tests/conftest.py`, `tests/test_wave3_soft_delete.py` (nouveau).

Frontend : `src/api.ts`, `src/types.ts`, `src/toast.ts`, `src/App.tsx`,
`src/index.css`, `src/components/Board.tsx`, `src/components/WorkspaceViews.tsx`,
`src/components/RunPanel.tsx`, `src/components/Dashboard.tsx`,
`src/i18n/messages/common.ts`, `board.ts`, `runPanel.ts`, `app.ts`,
`dashboard.ts`.

Tests frontend : `src/toast.test.ts`, `src/App.test.tsx`,
`src/components/Board.test.tsx`, `RunPanel.test.tsx`, `WorkspaceViews.test.tsx`,
`Dashboard.test.tsx` (nouveau).

E2E : `e2e/improve-ux.spec.ts`, `e2e/autospec.spec.ts`,
`e2e-streams/streams.spec.ts`.

#### Tests ajoutes

- Backend : `tests/test_wave3_soft_delete.py`, 10 fonctions (mise en corbeille
  avec `stripped_deps`, restauration en travail neuf, frere disparu entre-temps,
  404 inconnu, 409 pendant le build, 409 id repris, corbeille bornee et purgee,
  flag OFF = suppression dure, endpoint `/trash`, endpoint `/restore` et mapping
  des erreurs).
- Vitest : 7 tests R6 (bus de toasts avec action, toast Undo apres suppression,
  echec de restauration, panneau corbeille, absence de panneau si vide, bouton
  d'action rendu par App), 11 tests P5 + P3 (visibilite du bouton de
  re-verification sur statut effectif, absence pendant le build, absence sans
  story done, grille de base du dashboard, bloc fusion, verdicts tries, verdict
  inconnu, histogramme vide, backend sans `fusion`, erreur de chargement),
  7 tests R3 (lentille par defaut selon l'activite de build, stage suffisant,
  projet en spec, choix memorise prioritaire, memorisation au clic, valeur
  illisible, bascule unique a l'entree en build).
- E2E `improve-ux.spec.ts` (3 scenarios ajoutes a la fin du parcours, apres une
  attente de phase dormante) : (a) supprimer US-2 via le bouton « Supprimer » +
  `confirm-accept`, verifier la disparition de la carte, le toast avec bouton
  « Annuler », la presence de `trash-panel`, puis cliquer Annuler et verifier le
  retour de la story dans le board ET dans l'API ; (b) `verify-delivery` visible
  sur le projet dormant, clic, toast de succes ; (c) ouverture du dashboard et
  presence de `dashboard-fusion` contenant « Boucle de fusion ». Le test unique
  de cette spec passe a `test.setTimeout(420_000)` (attente de dormance).

#### Comptes finaux

| Gate | Commande | Resultat |
| --- | --- | --- |
| Backend | `uv run pytest -q -p no:cacheprovider` | 1328 passed, 0 failed (757,18 s) |
| Types | `npx tsc --noEmit -p .` | exit 0, aucune sortie |
| Vitest | `npx vitest run` | 28 fichiers, 264 passed, 0 failed (6,2 s) |
| E2E | `npm run test:e2e` | 2 passed (39,4 s) |
| E2E streams | `npm run test:e2e:streams` | 1 passed (13,1 s) |

Rappel : la vague 2 finissait a 1318 tests backend et 239 tests vitest ; la
vague 3 ajoute 10 tests backend et 25 tests vitest.

#### Corrections de gate

1. **`gotoEpics()` ne memorisait pas la lentille.** Premier run e2e :
   `autospec.spec.ts` echouait a la ligne 157 (`story-US-1` + « Termine »,
   element introuvable apres 60 s). Cause : R3 ne cliquait l'onglet « Vision
   produit » que si `aria-selected !== "true"` ; au moment de `openEpic()` la
   phase etait encore plan/architect, donc l'onglet Vision etait DEJA actif,
   aucun clic n'etait emis, aucun choix n'etait memorise, et la bascule
   automatique a l'entree en phase build deplacait le board sous la lentille
   Activite en plein `wait`. Correctif : rendre le clic INCONDITIONNEL dans
   `gotoEpics()` (cliquer un onglet deja actif passe quand meme par
   `selectView()` et memorise le choix), applique a `e2e/autospec.spec.ts` et,
   par symetrie, a `e2e-streams/streams.spec.ts`. Aucun code applicatif touche.
2. **Coherence de contrat verifiee, aucun ecart.** Les routes appelees par
   `api.ts` (`/verify`, `/stories/{sid}/restore`, `/trash`) correspondent
   exactement a celles exposees par `server.py`, et `toTrashInfo()` couvrait
   deja les deux formes possibles de `state.trash`. Rien a corriger.

#### Points d'attention restants

1. **Ordre de la corbeille : deux conventions.** `state.trash` va de la plus
   ancienne a la plus recente, `GET /trash` renvoie l'inverse. Le panneau du
   board lit `state.trash` : il liste donc la plus ancienne en premier.
2. **`arestore_story` reinitialise aussi les TACHES de la story** (statut,
   attempts, infra, requeue, stage, recovery), au-dela de la lettre du contrat :
   sans cela une story decomposee en taches serait stockee TODO alors que
   `effective_status()` la dirait encore DONE ou FAILED.
3. **Flag OFF (`SOFT_DELETE_STORIES=0`) : le bouton « Annuler » est quand meme
   rendu** apres une suppression (le detail de story ignore l'etat du flag). Le
   clic part vers `/restore`, recoit un 404 et produit un toast d'erreur. Pour
   l'eviter il faudrait faire descendre un booleen `softDelete` jusqu'au detail.
4. **`getTrash()` est exporte mais non consomme** : le panneau est alimente par
   l'etat SSE, comme specifie. Export mort tant que rien ne le sonde.
5. **`RunPanel.onVerifyDelivery` est une prop REQUISE** : tout nouvel appelant de
   `RunPanel` casse `tsc` tant qu'il ne la passe pas.
6. **Le bouton de re-verification est plus strict que le backend** : il exige au
   moins une story au statut effectif `done`, la ou le backend n'exige que la
   dormance. Un projet dormant dont la livraison a echoue avant la premiere
   story verte n'a donc pas d'affordance ; retirer la moitie
   `effStatuses.some(done)` de `canVerifyDelivery` suffirait.
7. **`fusion.p2b_resumes` et `fusion.orphan_resets` sont types mais pas
   affiches** (7 cartes demandees, 7 cartes rendues). Deux lignes a ajouter si
   on veut les voir.
8. **Deux cartes du bloc fusion agregent deux compteurs** (« requeues /
   remboursements » et « rafales / reverts bisect ») : un selecteur e2e doit les
   lire comme une seule chaine.
9. **Un choix d'onglet explicite neutralise definitivement la bascule
   automatique** vers Activite pour ce projet (memorise en `localStorage`).
   C'est ce qui rend les e2e deterministes ; si on veut que la bascule gagne
   toujours, il faut retirer le garde `userPicked` ET trouver une autre
   strategie pour les specs.
10. **`hasBuildActivity()` lit le statut et le `current_stage` BRUTS** (pas
    `effectiveStatus` ni le stage fusionne avec les `ticks`). Une story dont
    l'etape n'existe que dans le heartbeat, encore `queued`/`todo` et hors phase
    build, ne compterait pas ; en pratique la phase est `build` a ce moment-la.
11. **Les messages 404/409 de R6 sont en francais**, comme les autres erreurs
    remontees par `_acall_pipeline` : le frontend ne doit pas filtrer sur du
    texte anglais.
12. **`ruff check --no-fix` signale `arestore_story` en C901 (11 > 10)** ;
    laisse tel quel, le fichier porte deja 28 C901 preexistants.
### Vague 5 (2026-09-22) - tache d'amorcage web

**Statut : livree. Backend complet : 1341 passed, 0 failed (361,10 s) (`uv run pytest -q -p no:cacheprovider`,
log `backend/logs/wave5_gate.log`), dont 13 nouveaux tests
`tests/test_wave5_web_wiring.py`.**

#### Defaut d'usine observe

Run reel supervise du 2026-09-22, projet fullstack « Counter webapp »
(`workspace/drv-p3-9ae648a7`, streams backend + frontend, profil `auto`). Le plan
PO a produit TS-1 (persistance, 4 taches), US-1 (GET /count + affichage) et US-2
(POST /increment + bouton). Les 8 taches sont vertes et mergees. Et pourtant :

- `main.py` n'a **jamais** ete modifie depuis le scaffold ;
- **aucun** fichier du depot ne contient la chaine « uvicorn » ;
- les features publient leurs routes dans une table partagee
  (`counter_webapp/features/_routing.py`) en attendant un « mounter » qu'aucune
  tache ne prevoit.

Le smoke run echoue donc : « le process s'est arrete (code 0) sans ecouter sur
127.0.0.1:8000 » (`main.py` affiche la banniere d'aide et sort). C'est la
reparation post-smoke (agent `integration_fix`) qui doit rattraper apres coup ce
que le plan aurait du contenir.

#### Cause

1. **Les prompts de plan disent le contraire.** `prompts._streams_plan_block`
   (bloc TECHNICAL STORIES / FICHIERS PARTAGES), `prompts.sizing_rules()` et
   `prompts.decompose_story` affirmaient tous les trois qu'« une feature cablee
   par convention n'a besoin d'AUCUNE tache d'integration ». C'est vrai pour les
   ROUTES (le scaffold auto-decouvre `<pkg>/features/<feature>.py`), c'est FAUX
   pour l'**amorcage du serveur** (app factory + `main.py` qui demarre uvicorn),
   que personne ne porte alors.
2. **La regle « `python main.py` DOIT DEMARRER LE SERVEUR » n'existait que dans
   `prompts.dev_story`**, donc uniquement pour la tache qui aurait deja `main.py`
   dans son perimetre - et le scope gate retire justement `main.py` a toutes les
   autres. Personne ne lisait la regle parce que personne n'avait le fichier.
3. **Le scaffold `MAIN_TEMPLATE`** (contrat CLI livre en vague 2) affiche une
   banniere et retourne 0 quand aucun hook ne consomme `argv`. Pour un produit
   CLI c'est le contrat ; pour un produit web c'est exactement l'echec smoke.

#### Fix

1. **Garde deterministe `Pipeline._ensure_web_wiring_task()`**
   (`autospec/orchestrator/pipeline.py`). Appelee dans `_abuild_phase` juste
   avant `_enforce_global_independence()` (donc **apres**
   `_adecompose_pending()`, la ou naissent les taches, et **avant** le floor
   d'independance, pour beneficier de la serialisation). Conditions cumulees :
   flag ON, `self._expects_web_app()` vrai (profil `api`/`web-ssr`/`fullstack`,
   ou profil `auto`/`brownfield` avec un stream frontend declare), langage
   backend `python`, et **aucune** unite du pool ne revendique `main.py` (ni un
   `files_hint` de tache, ni le texte d'une story sans taches).
   Elle ajoute alors UNE tache `<story>-WEB` :
   - hote = la **derniere** story backend du pool qui est **deja** un conteneur
     de taches (on ne transforme jamais une story feuille en conteneur) ; s'il
     n'y en a pas, une Technical Story `TS-WEB` est creee (`technical=True`,
     `contract`, `depends_on` = les stories backend du pool) ;
   - `stream` = stream primaire backend, `complexity` = `simple`,
     `estimated_files` = 3 ;
   - `files_hint` = `["main.py", "<pkg>/app.py", "pyproject.toml"]` ;
   - `depends_on` = **toutes** les autres taches backend du pool (elle ferme la
     chaine) ; les taches frontend sont exclues ;
   - `acceptance_criteria` = « `python main.py` ecoute sur 127.0.0.1:8000 et
     `GET /` repond » + « `python main.py --help` affiche l'aide sans ouvrir de
     port », plus un Gherkin minimal coherent ;
   - description explicite : `create_app()` dans `<pkg>/app.py` qui instancie
     FastAPI et monte les routes/hooks publies par les features, sert
     `frontend/dist` a la racine si present ; dans `main.py` les hooks tournent
     puis, sans argument (ou avec `serve`),
     `uvicorn.run(create_app(), host="0.0.0.0", port=8000)` ; `--help`/`-h` sans
     port ; `fastapi` + `uvicorn` declares dans `pyproject.toml`.
   Log `web-wiring` + message de chat SYSTEM « Tache d'amorcage web ajoutee au
   plan (aucune tache ne demarrait le serveur). ». **Idempotente** : la tache
   qu'elle cree revendique `main.py`, donc le deuxieme appel ne fait rien.
   Deux helpers l'accompagnent : `_claims_main_entry(glob)` et
   `_is_backend_task(task)`.
2. **Prompts** (`autospec/agents/prompts.py`). Dans `_streams_plan_block`,
   `sizing_rules()` et `decompose_story` : la phrase « aucune tache
   d'integration » est desormais **bornee aux ROUTES**, et un bloc
   « AMORCAGE WEB » rend la tache d'amorcage OBLIGATOIRE en fin de chaine
   backend, avec `main.py` / `<pkg>/app.py` / `pyproject.toml` dans ses
   `file_globs`, en precisant que l'usine l'ajoute d'office si le plan l'oublie.
   Dans `dev_story`, rappel ajoute : « SI TA TACHE PORTE `main.py` DANS SON
   PERIMETRE : `python main.py` NU DOIT DEMARRER LE SERVEUR et rester en
   ecoute ; `--help`/`-h` affiche l'aide et ne lie AUCUN port. Une banniere
   suivie d'un `return 0` est un ECHEC du smoke run. »
3. **`workspace.MAIN_TEMPLATE`** : paragraphe « WEB PRODUCT » ajoute a la
   docstring du contrat CLI (en anglais, comme le reste du template) : pour un
   produit qui doit ecouter sur un port, l'entree nue DOIT demarrer le serveur
   (contrat smoke), la banniere n'est que le comportement par defaut d'un produit
   sans serveur ; typiquement `main()` lance les hooks puis appelle
   `create_app()` du package et `uvicorn.run(app, host="0.0.0.0", port=8000)` ;
   `--help` reste sans port. **Le comportement du template est inchange**
   (`tests/test_wave2_cli_scaffold.py` reste vert a l'octet pres).

#### Flag

`Settings.web_wiring_task` / env `WEB_WIRING_TASK`, **defaut ON** (code +
`backend/.env.example` + `backend/.env`). OFF = comportement historique (la
reparation post-smoke rattrape apres coup).

**Pin conftest : `False`** (contrairement a l'usage « pin au defaut code »). La
garde AJOUTE une tache au plan des qu'un stream frontend est declare, ce qui
change le nombre d'items que les tests de streams observent : avec le pin a
`True`, `tests/test_streams_build.py::test_frontend_task_starts_only_after_backend_dep_is_merged`
et `::test_dynamic_scheduler_starts_dependent_before_slow_sibling` voient un
quatrieme item `US-1-WEB` a cote de T-A/T-B/T-C et echouent. Le module
`tests/test_wave5_web_wiring.py` reactive le flag explicitement via une fixture
`autouse`.

#### Tests

`tests/test_wave5_web_wiring.py` (13 tests) :

- le trou reel : deux taches backend sans `main.py` -> une tache `US-1-WEB`
  ajoutee, `depends_on` = les deux, `files_hint` contient `main.py`,
  `pyproject.toml` et `<pkg>/app.py`, criteres et Gherkin presents, message de
  chat SYSTEM emis ;
- idempotence (deuxieme appel = rien) ;
- profil `fullstack` sans stream frontend : garde active quand meme (intention,
  pas artefact) ;
- aucun conteneur de taches dans le pool -> Technical Story `TS-WEB` creee, les
  stories feuilles restent sans taches ;
- une tache declare deja `main.py` -> rien ; une story sans taches qui nomme
  `main.py` -> rien ;
- profil `cli` -> rien ; flag OFF -> rien ; backend Go -> rien ;
- les taches frontend ne comptent pas comme backend (ni hote, ni dependance) ;
- passage du floor d'independance : recouvrement declare sur `pyproject.toml`,
  serialisation dans le bon sens, pas de cycle, pas de crash ;
- les prompts portent le rappel (`amor` + `app factory` dans le bloc streams et
  dans `sizing_rules`, `amor` + `main.py` dans `decompose_story`, le rappel
  `main.py` dans `dev_story`) et `MAIN_TEMPLATE` porte le paragraphe
  « WEB PRODUCT ».

Suites ciblees rejouees vertes : `test_wave2_cli_scaffold.py`, `test_pipeline.py`,
`test_streams_build.py`, `test_streams_planning.py`, `test_decompose.py`,
`test_independence.py`, `test_technical_story_plan.py`, `test_plan_pipeline.py`,
`test_workspace.py`, `test_smoke_run.py`, `test_wave2_smoke_cli.py`,
`test_generated_app_encoding.py` (205 passed).

#### Points d'attention

1. **La garde ne tourne que dans la branche streams/decompose de
   `_abuild_phase`** (`if streams_enabled or decompose_enabled`). Un projet
   entierement en chemin legacy (les deux flags OFF) n'est pas couvert ; c'est
   coherent, ce chemin n'a pas de taches.
2. **Le pin conftest est a `False` alors que le defaut code est `True`** : tout
   nouveau test qui veut voir la garde doit la reactiver explicitement, et les
   tests de streams existants ne decrivent donc PAS le comportement de
   production sur ce point.
3. **`_ensure_web_wiring_task` est signalee `C901` (13 > 10) par
   `ruff check --no-fix`** ; laissee telle quelle, `pipeline.py` porte deja une
   trentaine de C901 preexistants.
4. **`complexity="simple"`** n'appartient pas a la taxonomie documentee
   (`trivial` / `standard` / `complex`) mais n'est compare nulle part a autre
   chose que `complex` et `trivial` : sans effet, a renommer si la taxonomie
   devient stricte.
5. **La garde fait confiance aux `files_hint` declares.** Une tache qui
   modifierait `main.py` sans le declarer (le scope gate le lui retirerait de
   toute facon) est invisible pour elle : la tache WEB serait ajoutee en plus.
6. **Rien ne verifie a la livraison que la tache WEB a effectivement produit un
   serveur** : c'est toujours le smoke run qui tranche. La garde deplace le
   travail du rattrapage post-smoke vers le plan, elle ne remplace pas la gate.
---

### Vague 6 (2026-09-22) - tracabilite multi-stream

**Statut : livree. Backend complet : 1350 passed, 0 failed (293,59 s)
(`uv run pytest -q -p no:cacheprovider`, log `backend/logs/wave6_gate.log`),
dont 9 nouveaux tests `tests/test_wave6_traceability_aliases.py`
(1341 avant la vague).**

#### Defaut d'usine observe

Meme run reel supervise du 2026-09-22, meme projet
(`workspace/drv-p3-9ae648a7`, streams backend + frontend, 3 stories TS-1 / US-1 /
US-2, 8 taches). A la livraison, le monitor emet :

```
traceability covered=0 uncovered=12 orphans=24
```

et le journal affiche « 24 test(s) orphelin(s) referencent un AC inexistant
(TS1-T1.AC-1, TS1-T1.AC-2, ...) ». Or les 24 tests generes sont corrects et
portent un marqueur qualifie en bonne et due forme. Le rapport de tracabilite
declarait donc, sur un build reussi, que rien n'etait couvert et que tout etait
orphelin : un signal 100 % faux, qui pollue les `delivery_issues` et rend la
gate advisory inexploitable des qu'un projet est multi-stream.

#### Cause

Deux espaces d'identifiants qui ne se rencontrent jamais.

1. Le prompt `dev_story` demande le marqueur `# AC: {story.id}.{criterion.id}`.
   En multi-stream, le **sujet de build** d'un item n'est pas la story mais la
   **tache** : `{story.id}` vaut alors `TS1-T1`, et les tests generes portent
   `TS1-T1.AC-1`.
2. `Pipeline._report_traceability` ne declarait que les ids qualifies par
   **story** : `f"{s.id}.{c.id}"` soit `TS-1.AC-1`. Aucun marqueur ne pouvait
   matcher, d'ou `covered=0` ; et chaque marqueur, absent des ids declares,
   tombait dans `orphans`.

Le filtre anti-faux-positif existant (`declared_bare`, ajoute en juillet apres
le premier defaut de deduplication globale des ids `AC-1..AC-n`) ne couvre que
les marqueurs **nus** (`AC: AC-2`). Un marqueur qualifie par une tache n'est ni
nu ni declare : il passait tout droit en orphelin.

Fait structurant : les criteres d'une tache sont un **sous-ensemble** de ceux de
sa story et portent les **memes ids nus** (`models.Task.acceptance_criteria` vs
`UserStory.acceptance_criteria`). `TS1-T1.AC-1` et `TS-1.AC-1` designent donc le
meme critere. Ce sont des alias, pas deux criteres.

#### Fix

1. **`autospec/orchestrator/traceability.py`** : nouvelle fonction pure
   `fold_aliases(report, aliases)` (exportee dans `__all__`, aucune I/O). Elle
   replie un rapport calcule sur un espace d'ids **aliase** vers les ids
   **canoniques** : un critere canonique est couvert si l'un quelconque de ses
   alias l'est ; `uncovered` = canoniques sans alias couvert ; `orphans` repris
   tels quels (un orphelin n'est par construction pas un id declare, donc il n'a
   pas de forme canonique).
2. **`autospec/orchestrator/pipeline.py`**, `_report_traceability` (~l. 5325) :
   construction d'un dictionnaire `alias -> canonique` avant l'appel :
   - pour chaque story `s` et critere `c` : `f"{s.id}.{c.id}"` vers lui-meme ;
   - pour chaque tache `t` de `s.tasks` et critere `c` de `t` :
     `f"{t.id}.{c.id}"` vers `f"{s.id}.{c.id}"` si la story declare ce `c.id`,
     sinon vers `f"{t.id}.{c.id}"` (critere a part entiere, declare tel quel).

   `coverage_report` est appele avec **l'ensemble** des ids declares
   (`set(aliases)`, story + tache), puis le resultat passe par `fold_aliases`.
   Le filtre `declared_bare` est etendu aux ids nus des criteres de taches.
   L'evenement monitor et les messages gardent leur forme exacte : les compteurs
   `covered` / `uncovered` / `orphans` portent sur les **canoniques**.

Les TS enfants (`parent_id`) n'ont pas eu besoin d'un traitement separe : une TS
est une `UserStory` a part entiere de `state.stories`, donc deja couverte par la
boucle sur les stories, et ses propres taches par la boucle imbriquee.

#### Tests

`backend/tests/test_wave6_traceability_aliases.py`, 9 tests. Deux unitaires purs
sur `fold_aliases` (repli de deux alias sur un critere ; orphelins conserves et
entrees vides tolerees), puis les cas (a) a (e) sur `_report_traceability`
(monitor capture, `_collect_test_sources` / `_collect_frontend_test_sources`
stubbes) :

| Cas | Scenario | Attendu |
| --- | --- | --- |
| a | US-1 (AC-1, AC-2), taches US1-T1 (AC-1) / US1-T2 (AC-2), marqueurs qualifies par tache | covered 2, uncovered 0, orphans 0 |
| b | marqueur qualifie par **story** (`US-1.AC-1`) | couvre toujours |
| c | marqueur `US9-T9.AC-1` inconnu | orphelin (1) |
| d | marqueur **nu** `AC-1` | ni couvert ni orphelin |
| e | tache declarant `AC-7` que la story n'a pas | declare tel quel, couvert si marque ; `US1-T2.AC-8` non marque remonte en `uncovered` + `delivery_issues` |

Plus la reproduction du run reel (3 stories, 8 taches, 24 marqueurs qualifies par
tache) : `orphans == 0` et `covered == 11` (tous les canoniques atteignables
depuis une tache), et un test-garde qui verifie que le rapport **brut** sur les
seuls ids story affiche encore la signature du defaut
(`covered=[]`, 11 uncovered, 24 orphans) : il prouve que c'est bien le repli qui
corrige, pas une modification du corpus de test.

Suites ciblees rejouees vertes : `test_wave6_traceability_aliases.py`,
`test_traceability.py` (24 passed), `test_pipeline.py`, `test_delivery_gate.py`,
`test_supervised_run_fixes.py` (91 passed).
`ruff check --no-fix` sur les deux fichiers modifies : **zero nouveau
signalement** (les 2 restants sur `traceability.py`, `RUF022` et `C901`, sont
anterieurs et identiques sur la version HEAD).

#### Verification hors-ligne sur le projet reel

Script temporaire `backend/logs/wave6_offline_check.py` (hors depot) : il charge
`workspace/drv-p3-9ae648a7/autospec-state.json`, rescanne les 34 fichiers de
test de `tests/` et `frontend/src`, et rejoue le rapport avant / apres.

```
stories 3, taches 8, fichiers de test 34, marqueurs distincts 24

AVANT (ids qualifies par story uniquement)
  declares  : 12
  covered   : 0
  uncovered : 12
  orphans   : 24

APRES (story + tache, alias replies)
  ids declares : 36 (criteres canoniques : 12)
  covered   : 9
  uncovered : 3  [US-1.AC-4, US-2.AC-4, US-2.AC-5]
  orphans   : 0

marqueurs ni declares ni nus : 0
```

L'avant reproduit **exactement** la signature observee en production
(`covered=0 uncovered=12 orphans=24`). Apres le fix, les 24 marqueurs sont tous
expliques : ils se replient sur 9 criteres canoniques (TS-1.AC-1..3 marques par
4 taches, US-1.AC-1..3 par 2 taches, US-2.AC-1..3 par 2 taches).

#### Points d'attention

1. **Les 3 `uncovered` restants sont un vrai trou, pas un bug de tracabilite.**
   `US-1.AC-4`, `US-2.AC-4` et `US-2.AC-5` sont des criteres de story qu'**aucune
   tache ne reprend** : la decomposition en taches a perdu des criteres en
   chemin. Le rapport les signale desormais correctement, et c'est le prochain
   defaut d'usine a instruire (cote decomposition, pas cote tracabilite).
2. **Le prompt `dev_story` n'a pas ete touche.** Le marqueur qualifie par la
   tache reste ce que le worker produit ; on l'accepte au lieu de le combattre.
   Corollaire : si le sujet de build change encore de nature, il faudra etendre
   le dictionnaire d'alias, pas le prompt.
3. **Un critere de tache absent de sa story est declare sous l'id de la tache.**
   C'est volontaire (cas e) mais cela veut dire qu'un id nu invente par le
   planificateur cree un critere canonique supplementaire dans le compte, sans
   equivalent dans la story.
4. **`ac_traceability_enabled` est pinne a `False` dans `conftest.py`** : les
   tests de la vague le reactivent explicitement, comme les vagues precedentes.

### Vague 7 (2026-09-22) - evaluateur : kill d'arbre au timeout

**Statut : livree. Backend complet : 1359 passed, 0 failed (286,17 s)
(`uv run pytest -q -p no:cacheprovider`, log `backend/logs/wave7_gate.log`),
dont 9 nouveaux tests `tests/test_wave7_evaluator_tree_kill.py`
(1350 avant la vague).**

#### Defaut d'usine observe

Meme run reel supervise du 2026-09-22, projet fullstack
`workspace/drv-p3-9ae648a7`. La phase evaluateur (E6) demarre a 11:23:53
(« Evaluation du produit livre (execution reelle) ») et ne rend JAMAIS la main :
le pilote atteint son plafond de 2 h a 11:32 et la session ne se termine qu'apres
un kill manuel du serveur genere a 12:08, soit 45 minutes de gel pour un timeout
cense valoir quelques dizaines de secondes. Traces de processus : le wrapper
`uv` (pid 37196) a bien disparu, mais le `python` petit-fils (pid 52764 puis
26848) ecoutait toujours sur :8000 une heure plus tard.

#### Cause

`Pipeline._aexercise_product` lancait le produit livre avec :

```python
subprocess.run(cmd, stdout=PIPE, stderr=STDOUT, timeout=settings.evaluator_run_timeout_s)
```

ou `cmd` vaut `uv run python main.py` (`toolchain.run_command`). Au
`TimeoutExpired`, `subprocess.run` tue seulement l'enfant DIRECT (`uv.exe`) puis
rappelle `communicate()` pour recuperer la sortie. Sous Windows, le petit-fils
`python` (uvicorn) survit a la mort de `uv` et garde le tube stdout HERITE
ouvert : `communicate()` bloque jusqu'a la mort de ce petit-fils, le thread
`asyncio.to_thread` ne revient jamais, la phase gele et le serveur fuit.

Le piege etait deja connu et resolu ailleurs dans le meme fichier :
`Pipeline._kill_tree` (`taskkill /T /F` sous Windows) pour `astop_app` /
`adispose`, et le smoke web fait meme un double-tap via
`_kill_workspace_port_holders`. L'evaluateur, lui, etait reste sur le raccourci
`subprocess.run(timeout=...)`.

Reproduction hors usine (3 lignes, ~30 s) : un `main.py` qui spawne
`python -c "import time; time.sleep(30)"` avec stdout herite puis dort ;
`subprocess.run(..., timeout=2)` ne revient qu'apres **30,2 s**, c'est-a-dire a
la mort du petit-fils, pas au timeout. Avec un petit-fils immortel (un serveur),
« 30 s » devient « jamais ».

#### Fix

`autospec/orchestrator/pipeline.py`, `_aexercise_product` (~l. 2570) reecrit
autour de `subprocess.Popen` (memes `cwd` / env minimal / encodage utf-8) :

1. **Lecture dans un thread DAEMON** : `readline(16384)` dans un buffer borne
   par la nouvelle constante `_EVALUATOR_OUTPUT_CAP = 200 000` caracteres (une
   app bavarde ne peut plus ni gonfler le prompt evaluateur ni saturer le tube).
   Daemon : si le petit-fils garde le tube, le thread n'empeche ni la phase ni
   le processus de se terminer.
2. **`proc.wait(timeout)`** au lieu de `communicate(timeout)` : aucune lecture de
   tube apres le timeout, donc plus rien a bloquer.
3. **Au timeout** : `self._kill_tree(proc)` (arbre complet, `taskkill /T /F` sous
   Windows), plus sous POSIX un `os.killpg(proc.pid, SIGKILL)` rendu sur par le
   `start_new_session=True` du `Popen` (`_kill_tree` n'y signale que l'enfant
   direct) ; puis `proc.wait(5)` best-effort.
4. **Dernier filet web** : si le produit est web (`_expects_web_app()`),
   `_kill_workspace_port_holders(_resolve_web_port(ws), workspace_root)`, comme
   le smoke, pour le superviseur uvicorn reload qui respawne un worker.
5. **Cas « le parent sort, le petit-fils garde le tube »** : `join(2)` puis on
   rend la main en annotant la sortie
   « (sortie tronquee : un processus detache garde le tube ouvert) » au lieu
   d'attendre indefiniment.
6. **Observabilite** : `monitor.event("evaluator_run", ok=, timed_out=,
   killed_tree=)`.

Messages inchanges (« (processus termine, code N) »,
« (toujours actif apres Ns ...) », « (lancement impossible : ...) »),
court-circuit demo (`fake_agents`) et `_maybe_sandbox` conserves.

#### Tests

`tests/test_wave7_evaluator_tree_kill.py`, 9 tests deterministes et
multi-plateformes (aucune dependance a `uv` : `toolchain.run_command` est
monkeypatche vers `[sys.executable, "main.py"]`, timeout evaluateur a 2 s) :

1. timeout avec petit-fils vivant : retour en moins de 20 s, message
   « toujours actif apres », sortie de demarrage conservee, et le **petit-fils
   est mort** apres l'appel (pid ecrit par `main.py`, verifie par `tasklist /FO
   CSV` sous Windows et `os.kill(pid, 0)` ailleurs - jamais `os.kill` sous
   Windows, qui TUE la cible quel que soit le signal) ;
2. parent qui sort en laissant un petit-fils sur le tube : retour immediat,
   code 0, marqueur de troncature ;
3. produit web : le balayage des tenanciers de port est bien appele ;
4. produit CLI : il ne l'est pas (aucun PowerShell / lsof) ;
5. cas nominal : code 0 + sortie capturee ;
6. deluge de 1 Mo : capture bornee au plafond, sans blocage ni deadlock de tube ;
7. commande introuvable : « (lancement impossible » et `ok=False` ;
8. mode demo : aucun `Popen` ;
9. `_kill_tree` passe bien par `taskkill /F /T` (Windows).

Les tests 1 et 2 echouent sur l'ancienne implementation (retour apres la mort du
petit-fils, soit 60 s ici, jamais en production).

#### Points d'attention

1. **Le meme piege subsiste dans la branche CLI du smoke**
   (`_smoke_run_python`, ~l. 9558, et `_smoke_cli_help_run`, ~l. 9590) :
   `subprocess.run([uv, run, python, main.py], stdout=PIPE, timeout=...)`. La
   branche web du smoke est deja en `Popen` + `_terminate_tree` + double-tap,
   mais la branche CLI garde le raccourci ; un `main.py` non web qui boucle ou
   qui laisse un enfant vivant gele la gate exactement de la meme facon, alors
   que son message (« boucle/serveur bloquant ? ») pretend justement couvrir ce
   cas. Non corrige dans cette vague : `tests/test_smoke_run.py` et
   `tests/test_wave2_smoke_cli.py` (9 tests) monkeypatchent `subprocess.run` sur
   ce chemin, le passage en `Popen` demande donc de reecrire leurs helpers. A
   faire en vague 8, avec le meme utilitaire partage.
2. **`runtime_acceptance.py` (~l. 135)** lance `node scripts/runtime_acceptance.js`
   avec `subprocess.run(..., timeout=timeout + 15)` et le script JS spawne
   lui-meme backend et frontend : si le script deborde, seul `node` est tue et
   ses serveurs petits-fils peuvent rejouer le meme blocage. Risque plus faible
   (le script a sa propre discipline d'arret) mais meme classe.
3. **Les autres `subprocess.run(..., timeout=)`** (pip-audit, pytest coverage,
   npm install, setup_exec, docker) lancent des commandes qui TERMINENT, pas des
   serveurs : hors perimetre.
4. **`_EVALUATOR_OUTPUT_CAP` est un plafond de capture, pas de prompt** : la
   sortie est ensuite passee telle quelle a `prompts.evaluator_probe`. Si le
   prompt doit etre reduit, c'est un reglage separe.
