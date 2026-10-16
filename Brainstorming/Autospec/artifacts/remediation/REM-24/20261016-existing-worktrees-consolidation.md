# Consolidation des worktrees — 16 octobre 2026

## Fusions intégrées

- REM-07 : reprise pré-PLAN explicitement demandée, une seule correction maker, journal `UNKNOWN` durable avant dispatch, contrôle du coût connu et blocage fail-closed des findings majeurs mal formés (`confirmed: 1` ou chaîne).
- REM-10 : revalidation du manifeste et des fichiers du socle déterministe avant l’admission au PLAN, y compris les projets sans contrat formalisé. Le test au root frontend mixte reconstruit le manifeste pour l’état réellement testé.
- REM-14 : comparaison exacte des champs titre/description affichés au GET réel, câblage frontend observable, étape auth `N/A` pour profil sans auth, validation API/DB des mêmes valeurs et redémarrage sur le même volume avec remplacement du conteneur.
- Les propositions encore non commitées du worktree `rem14-vertical-hardening` sont déjà présentes dans le code REM-14 intégré à une version plus stricte (ordre des étapes exact, preuves X/V, comparaison API/DB, restart et Argon2). Elles n’ont pas été réappliquées pour éviter de remplacer la version plus récente par leur état antérieur.

## Résultats

- REM-07 ciblé : **239 passed**.
- REM-10 ciblé : **153 passed**.
- Suite combinée après fusion REM-07/REM-10 : **311 passed**.
- Suite de régression après fusion REM-14 (browser contracts, jalons, harnais) : **75 passed, 17 skipped**; les skips sont les cas réservés aux opt-ins Docker produit, exécutés séparément ci-dessous.
- REM-14 harnais Docker réel : **24 passed en 579,10 s**. Les reçus nominal et image baked contiennent chacun les neuf étapes PASS : schema, bootstrap, Argon2, login, création navigateur, câblage frontend, GET API, commit DB et persistance après remplacement du conteneur sur le même volume.
- Réseau Docker réel : **3 passed**; navigateur Docker et redémarrage : **2 passed** (qualification antérieure conservée).
- Frontend : **321 tests passed** et build réussi (qualification antérieure conservée).
- Suite backend complète de référence avant ces dernières fusions : **3 531 passed, 107 skipped, 18 failed** en 3 972,27 s. Ce résultat n’est pas une qualification verte globale. Les échecs observés :
  - `test_calibration::{test_real_footprint_over_budget_is_counted,test_merge_requeue_and_p2b_resume_are_counted}`
  - `test_git_diff_isolation::test_own_nested_repo_returns_only_its_commits_and_rolls_back_locally`
  - `test_merge_preserve::test_resume_green_branch_rebases_then_merges`
  - `test_quality_contracts::test_TST_05_admits_twelve_actual_browser_runs_and_intact_visual_proofs`
  - `test_rem_clean_install_integration::test_real_argon2_runtime_request_and_clean_lock_validation` (deux paramètres)
  - `test_scripted::test_scripted_runner_drives_full_pipeline`
  - `test_split_on_failure::{test_exhausted_merge_conflict_tries_finer_split,test_merge_conflict_requeue_resumes_preserved_branch}`
  - `test_streams_build::{test_persistent_merge_conflict_fails_after_exhausting_retries,test_dynamic_scheduler_starts_dependent_before_slow_sibling}`
  - `test_task_actions::test_task_diff_available_after_rebuild`
  - `test_wave1_requeue_budget::{test_requeue_budget_exhausted_ends_failed,test_a_replay_that_goes_green_merges_the_item}`
  - `test_wave2_canary_batch::test_a_contended_burst_is_verified_by_a_single_canary`
  - `test_wave2_solo::test_a_a_persistent_conflict_is_rebuilt_solo_instead_of_failing`

Le rapport XML et la sortie pytest de cette suite de référence sont `backend-baseline.xml` et `backend-baseline.log` dans ce dossier. Les échecs de référence n’ont pas été attribués aux trois lots ciblés sans contre-preuve; ils empêchent cependant d’affirmer que toute la suite est sans erreur.

## Portée et limites

La suite Docker réelle valide le harnais et les preuves de capacité de la fabrique, pas la conformité d’un nouveau produit aux 57 critères. La campagne Relais Support demeure au PLAN rejeté; aucune deuxième génération ni réparation manuelle du produit n’a été exécutée. La qualification globale reste ouverte tant que les 18 tests de référence ne sont pas expliqués et que la suite intégrée n’est pas relancée sur l’état final.
