# Revue du workflow Autospec — 2026-07-05

Revue de bout en bout du pipeline (spec → plan → architect → build → gates →
done), fondée sur un **run réel** (projet `messagerie2`, 4 rounds de build dont
3 échecs identiques), la lecture du code de `orchestrator/`, et des **tests
réels** ajoutés pour chaque défaillance observée. Les corrections sont dans le
code ; les points faibles restants sont priorisés en fin de document.

---

## 1. Cartographie du workflow

| Étape | Méthode (pipeline.py) | Gestion d'échec |
| --- | --- | --- |
| Spec (PM interview / brief) | `_aspec_phase` | AgentError non fatal ; stop propre |
| Analyze (impact feedback) | `_aanalyze_phase` | non fatal |
| Sélection langage / streams | `_aselect_language` / `_aselect_streams` | repli heuristique |
| Plan (PO mono-pass ou S1→S3) | `_aplan_phase` (+ `plan_pipeline.py`) | repli mono-pass legacy |
| Architecture (optionnel) | `_aarchitect_phase` | **silencieux** (voir P3) |
| Gate d'approbation (U4) | `_aapproval_gate` | bloque jusqu'à décision humaine |
| Build parallèle (worktrees) | `_abuild_phase[_streams]`, `_abuild_work_item` | tentatives dev (`DEV_MAX_ATTEMPTS`) + budget infra séparé (`INFRA_MAX_RETRIES`) + split-on-failure borné |
| Canari post-merge | `_apost_merge_canary` | vert / **sémantique** (revert) / **infra** (répare, conserve le merge) |
| Smoke run / Runtime acceptance | `_asmoke_phase` / `_aruntime_acceptance_phase` | bloque la livraison, pas de retry auto |
| Definition of Done | `_apply_definition_of_done` | gate déterministe, `delivery_issues` |
| Doc / Éval / Sécu / Rétro (opt.) | `_adocument/_aevaluate/_asecurity/_aretro_phase` | best-effort, non fatals |
| Watchdog fenêtre d'usage (M2) | `session_monitor.py` | stop propre + tentative remboursée + reprise auto |

Modules sœurs : `streams.py` (DAG d'items), `scheduler.py` (ordonnancement),
`toolchain.py` (commandes/parseurs par langage), `workspace.py` (scaffold),
`independence.py` (claims de fichiers), `setup_exec.py` (composants).

---

## 2. Défaillances observées EN RÉEL (messagerie2) et corrections

Chaque correction est couverte par un test (fichier indiqué).

### 2.1 La venv partagée à moitié détruite passait pour un conflit de code
Un `rmtree` sur une `.venv` dont le `python.exe` est encore verrouillé (Windows)
laisse un arbre partiel que uv refuse d'utiliser **et** de recréer. Le message
uv (« not a valid Python environment ») n'était pas dans les signatures du
classifieur infra → le canari classait ce rouge **sémantique**, revertait des
merges verts et brûlait les tentatives dev de 4 tâches socle (48 blockers).
**Fix** : signatures uv ajoutées à `_looks_like_infra_failure` ;
`_purge_venv_dir` avec retries sur verrous, purge impossible signalée
bruyamment. **Tests** : `test_generation_hardening.py`
(`test_infra_classifier…`, `test_purge_venv_dir_reports_a_locked_survivor`).

### 2.2 Le reporter Vitest muet rendait les devs aveugles
`vitest run --reporter=json --outputFile=…` : sur un rouge, stdout se réduit à
« JSON report written to … ». C'est TOUT ce que recevait le dev en retry
(`previous_failure`) — il a conclu « problème de reporter, pas de code » et
re-poussé le même code deux fois → FAILED. **Fix** : double reporter
(`--reporter=default --reporter=json --outputFile.json=…`) + **digest des
échecs** extrait du rapport JSON et annexé à la sortie rouge (noms + messages,
crashs fichier inclus) ; suite vide nommée explicitement. **Tests** :
`test_frontend_toolchain.py` (`test_frontend_failure_digest…`),
`test_workflow_weakpoints.py` (digest, suite vide).

### 2.3 La guérison d'infra était réservée au backend
Le chemin « rouge sans test exécuté → répare l'env → rejoue » n'existait que
pour pytest/venv. Un `node_modules` cassé produisait un rouge frontend traité
comme un échec de code. **Fix** : `_looks_like_frontend_infra_failure`
(signatures ERR_MODULE_NOT_FOUND / « Cannot find package » / npm exec) +
auto-réparation (`npm ci` + un replay) dans `_arun_frontend_tests`, symétrique
du garde venv. **Tests** : `test_workflow_weakpoints.py` (heal + non-heal).

### 2.4 Le partage de node_modules par jonction détruisait l'install commune
La cause racine du churn : le worktree recevait une **jonction** vers le
`node_modules` principal. Or (a) `git worktree remove --force` **traverse** la
jonction et vide la cible ; (b) un agent dev qui fait `rm -rf node_modules`
(Git Bash traverse aussi les jonctions) ou `npm ci` dans son worktree détruit
l'install partagée ; (c) vitest bundle même `vite.config.ts` dans le
`.vite-temp` de la CIBLE. Résultat observé : 6 réinstalls de l'install partagée
en un build, et des suites sœurs mortes en plein vol sur « Cannot find package
'vite' ». **Fix** : (1) détachement systématique des jonctions avant toute
suppression de worktree (`_unlink_node_modules_junctions`) ; (2) **abandon du
partage par jonction** — chaque worktree reçoit une vraie install hermétique
(`npm ci`, ~20-40 s avec le cache npm). **Tests** :
`test_workflow_weakpoints.py` (test RÉEL : vrai repo git + vraie jonction +
`_aworktree_remove` → cible intacte), `test_generation_hardening.py`
(détachement), `test_frontend_node_modules.py` (install hermétique).

### 2.6 Les worktrees en %TEMP% cassaient Vite (chemin court 8.3 « ~ »)
Round 5 (backend enfin à jour) : grâce au digest (2.2), l'erreur réelle est
devenue visible — « Failed to load url C:/Users/E6FB4%7E1.MIL/…/setupTests.ts.
Does the file exist? ». Les worktrees étaient créés par `tempfile.mkdtemp()`
dans `%TEMP%`, que Windows expose en chemin court 8.3 (`E6FB4~1.MIL`) ; Vite
percent-encode le `~` en fabriquant les URLs de modules et ne recharge plus les
`setupFiles`. Preuve : la MÊME branche, la MÊME commande → verte dans un
worktree sous un chemin sans `~`. **Fix** : `_new_worktree_path()` — les
worktrees vivent dans `workspace/_worktrees/` (chemin long résolu, même volume
que le repo). **Test** : `test_workflow_weakpoints.py`
(`test_new_worktree_path_avoids_short_temp_paths`).

### 2.5 « Dépendance non satisfaite » n'indiquait pas la cause racine
T8 était « bloqué par T6, T7 » (tous deux seulement bloqués) alors que la vraie
cause était T5-S1-S1, deux niveaux plus bas — l'opérateur devait remonter la
chaîne à la main. **Fix** : `scheduler.failed_root` (BFS transitif, duck-typé
stories/items) ; les deux chemins de blocage écrivent désormais « Cause
racine : \<id\> — \<son erreur\> ». **Test** : `test_workflow_weakpoints.py`
(`test_failed_root_walks_the_dependency_chain`).

---

## 3. Points faibles restants (rethink), priorisés

**P1 — Économie des tentatives sur les feuilles socle.** Une feuille à
`DEV_MAX_ATTEMPTS=2` dont les deux rouges étaient environnementaux gèle toute
l'itération (48 items bloqués pour UNE feuille). Le budget infra séparé ne
s'applique qu'aux `AgentError` ; un rouge de suite causé par l'env consomme une
tentative dev. Reco : rembourser la tentative quand le rouge est classé infra
par le canari/self-heal (étendre la logique de refund du watchdog), et/ou une
tentative bonus pour les items à fort fan-out (`len(dependents)`).

**P2 — Aucun signal de code obsolète. ✅ IMPLÉMENTÉ.** Le backend tournait
depuis 02:02 avec du code pré-fix ; 4 rounds ont été perdus à re-jouer le même
échec sans aucun moyen de le détecter côté API (`reload=False`).
**Fix** : `GET /api/health` expose `source_stamp` (sources CHARGÉES, figé à
l'import) vs `source_stamp_now` (état du disque) — des valeurs différentes =
un fix a atterri que le processus ne fait pas encore tourner, redémarrage
requis. **Test** : `test_workflow_weakpoints.py`
(`test_health_exposes_loaded_vs_on_disk_source_stamps`). Reste possible :
écrire le stamp en tête de `build-monitor.jsonl`.

**P3 — Échec d'architecture silencieux.** `_aarchitect_phase` avale
l'AgentError et le build continue sans design ; personne n'est prévenu. Reco :
notification `warning` + trace chat (le QA/Dev perdent un contexte important).

**P4 — Dégradation silencieuse du harnais refine.** Critic/judge indisponibles
→ boucle stoppée sans signal ; la perte de qualité est invisible. Reco : event
`refine_degraded` dans le monitor.

**P5 — Gates terminaux sans re-essai.** Smoke run / DoD bloquent en
`needs_attention` sans chemin de retry automatique — c'est un choix (décision
humaine), mais `retry-failed` ne rejoue que les FAILED ; un bouton « rejouer le
gate » éviterait de relancer un build entier après une réparation manuelle.

**P6 — La racine partagée reste un point de contention.** Les runs partagés
(canari, story-level) sérialisent (`_shared_suite_lock`) et les worktrees sont
désormais hermétiques ; il reste que la racine partagée est réparée par
réinstall complète (~30 s) à chaque corruption. Acceptable, mais consigner dans
les prompts dev « ne jamais toucher aux env partagés » réduirait la source.

**P7 — Fenêtre d'usage : reprise estimée tardivement.** La reprise programmée à
08:00 alors que la fenêtre a rouvert plus tôt (reprise déclenchée par un retry
manuel). Mineur : le fallback ccusage est conservateur ; un re-sondage
périodique (ex. toutes les 30 min) raccourcirait l'attente.

---

## 4. État des tests

- Nouveaux tests réels : `backend/tests/test_workflow_weakpoints.py` (6 tests —
  vrai git + vraie jonction, digest Vitest, suite vide, self-heal, non-heal,
  cause racine) ; durcissements dans `test_generation_hardening.py`,
  `test_frontend_toolchain.py`, `test_frontend_node_modules.py`,
  `test_model_routing.py`, `test_api_provider.py`, `test_providers.py`,
  `test_session_monitor.py`, `test_codex_and_discovery.py`,
  `test_anthropic_provider.py`.
- Suite complète backend : **verte** (612+ tests) — voir CI/local.

> Rappel opérationnel : le backend est lancé avec `reload=False` — les
> corrections de ce dossier ne s'appliquent qu'après **redémarrage** du
> processus (cf. P2).
