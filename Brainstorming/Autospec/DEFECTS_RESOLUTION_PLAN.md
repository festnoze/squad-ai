# Défauts observés (run supervisé « recettes », 2026-07-20) & plan de résolution

Run de référence : `recettes-9a76d8cd` - fullstack (React multi-vues + FastAPI +
SQLite), brief importé, STREAMS=1, DOCKER_DELIVERY=1, provider claude code /
opus. Résultat : 9 US construites et vérifiées (suite pytest ~120 tests verte,
Vitest vert, smoke OK, runtime navigateur OK après 2 réparations), livraison
Docker garée en infra (Docker Desktop d'une autre session Windows). Coût :
60,18 $ / 74 appels agents / ~2 h 40.

## Défauts et fixes (usine)

| # | Sévérité | Défaut observé | Cause racine | Fix |
|---|---|---|---|---|
| D1 | Majeur | TS-1-T1 (domaine pur) condamné au rouge : `tests/constitution/test_api_namespace.py` exige l'app FastAPI finale dès la 1re tâche ; 2 tentatives brûlées | Tests constitution = assertions d'état FINAL exécutées dans CHAQUE run per-task ; garde `importorskip` seulement pour les imports tiers, pas pour les imports dynamiques (`importlib` + RuntimeError) | F2 : contrat de compilation (« skip tant que la précondition n'existe pas ») dans le prompt + soupape déterministe : `tests/constitution/conftest.py` semé qui convertit en SKIP tout échec enraciné dans ImportError/ModuleNotFoundError |
| D2 | Majeur | Triche induite : le dev a livré un `main.py` avec une app duck-typée SANS FastAPI pour satisfaire le test constitution (guards warn n'ont rien bloqué) | Conséquence directe de D1 (test insatisfiable dans le scope de la tâche) | Résorbé par F2 (l'incitation disparaît) ; les guards restent en warn (choix assumé) |
| D3 | Moyen | 6 tests constitution sur 7 skippent proprement, 1 seul lève RuntimeError | Compilation incohérente (garde uniquement statique sur les imports) | F2 (même fix) |
| D4 | Moyen | Le scope guard retire à CHAQUE tâche le module `recettes/features/<task>.py` créé par le dev (convention du scaffold), 1 retrait échoué → parallélisme réduit | La décomposition architecte n'inclut pas le module d'auto-enregistrement dans les `file_globs` alors que le scaffold l'exige | F9 : prompt `decompose_story` - chaque tâche qui enregistre une feature DOIT inclure `<pkg>/features/<module>.py` dans ses file_globs |
| D5 | Majeur | Duplication de couches : 2 modèles SQLAlchemy complets (orm.py vs entities.py), 3 exceptions équivalentes ; entities.py/… finissent en code mort | Le judge (84/100 ≥ seuil 80) signalait « US trop larges + recouvrement » mais s'arrête au seuil → findings jamais persistés ni corrigés | F10 : `_arefine_plan` ajoute UNE passe de critique de collecte quand le judge s'arrête au seuil en 0 tour - les issues sont toujours persistées (panneau de revue), une critique vide = rien à signaler |
| D6 | Majeur | `recipes.db` (SQLite binaire de test) commité → 3 merges cassés (binaire, modify/delete, « local changes overwritten »), 2 tentatives 2/2 brûlées, 1 split-on-failure à tort ; intervention manuelle nécessaire | `.gitignore` généré ne couvre pas `*.db` ; les artefacts binaires de test circulent entre worktrees | F1 : `*.db` / `*.sqlite*` dans `GITIGNORE_TEMPLATE` du scaffold |
| D7 | Moyen | Retrait hors-périmètre TOUT-OU-RIEN : le binaire toxique est conservé parce qu'un AUTRE fichier était porteur de tests | Une seule passe suite-verte pour tous les fichiers | F7 : repli par-fichier (chaque retrait testé individuellement, les verts sont gardés) |
| D8 | Mineur | « conflit sur : (fichiers non identifiés) » sur l'échec pré-merge « Your local changes would be overwritten » | `_aconflict_files` ne lit que `diff --diff-filter=U` | F6 : parse aussi la liste de fichiers dans la sortie du merge |
| D9 | Moyen | Rapports de gate tronqués à 300 chars EN TÊTE → seuls les warnings DEP0190 visibles, l'erreur réelle invisible dans logs/UI | `detail[:300]` au lieu de la queue | F4 : troncature par la QUEUE (`[-600:]`) sur les événements d'échec |
| D10a | Moyen | Un `python main.py` zombie (fuité par une passe de gate) tenait :8000 ; rejouée à la main la gate sort « INFRA port occupé » | Le killTree JS (taskkill /T) ne suffit pas toujours sous Windows ; le nettoyage python n'est fait qu'AVANT les re-vérifications, pas avant la passe INITIALE | F5 : `_aensure_own_port_free` AVANT la première passe runtime aussi |
| D10b | Majeur (latent) | La boucle `_arepair_delivery` ne re-vérifie la forme infra que sur le rapport INITIAL ; un verdict `__INFRA__`/infra au verify dépêche quand même le dev suivant | Check hors boucle | F3 : re-check infra sur `new_detail` DANS la boucle → park immédiat, tentatives préservées |
| D11 | Mineur | OUTCOME/API montrent les stories backend `todo` alors que toutes leurs tâches sont done | Statut story jamais consolidé pour les stories à tâches (choix historique) | Documenté, non corrigé ici (le statut effectif est dérivé côté UI) |
| D12 | Moyen | La gate runtime a dû réparer 2 vrais trous d'intégration (montage statique frontend/dist manquant, import vitest dans le bundle prod) - 2 cycles de réparation prévisibles | Aucune exigence d'intégration backend↔frontend dans le plan/architecture fullstack | F8 : le prompt d'architecture ajoute, pour les produits web avec frontend, l'exigence « le backend sert frontend/dist à la racine (mode INTÉGRÉ) + URLs API relatives » |
| PRE-1 | Env | Docker Desktop tourne dans la session d'un AUTRE utilisateur Windows (`aze`) → pipe refusé, livraison garée (aussi la cause du biblio:18003 mort) | ACL du pipe npipe | F11 : marqueur « permission denied while trying to connect » dans `DOCKER_INFRA_MARKERS` + action humaine : relancer Docker Desktop dans la session `e.millerioux` |

Anomalie à investiguer (non traitée ici) : événement `traceability` final
`covered=0, uncovered=4, orphans=0` - vraisemblablement le matcher AC↔tests ne
voit pas les nodeids des stories frontend ; à vérifier séparément.

## Ce que le run a validé (pas de fix nécessaire)

- Park infra Docker correct (zéro tentative brûlée sur la gate docker).
- Régénération de branche verte après conflit (never-lose-green) opérationnelle.
- Split-on-failure fonctionnel (mais déclenché pour une mauvaise raison, cf. D6).
- Skills repo/service/endpoint-search-or-create : réutilisation effective
  (US-2-T2/T3, US-4-T2 ont réutilisé au lieu de dupliquer).
- Gate runtime : 2 vrais bugs d'intégration détectés et réparés par agents.
- `_aensure_own_port_free` moissonne bien les zombies (finding 10) - sur les
  re-vérifications.

## Ordre d'implémentation

F1 (gitignore) → F2 (constitution) → F3+F4+F5 (repair loop/troncature/port) →
F6+F7 (merge/scope) → F8+F9 (prompts architecture/décomposition) → F10
(critic-first plan) → F11 (marqueur docker) → tests backend complets.

---

## Round 2 - améliorations (2026-07-21, tout livré et vert)

| # | Amélioration | Livraison |
|---|---|---|
| P1 | Traceability `covered=0` : ids d'AC qualifiés par story (`US-1.AC-2`), scan des sources Vitest, convention `# AC:` injectée dans les prompts dev backend+frontend, marqueurs non qualifiés exclus des orphelins | pipeline.py `_report_traceability` + `_collect_frontend_test_sources`, prompts dev_story/_frontend |
| P2 | Statut effectif des stories à tâches : `effective_status_value` existait déjà côté API ; les 3 événements OUTCOME utilisent désormais `effective_status()` | pipeline.py |
| P3 | Fuite de process du gate JS : `reapWorkspacePortHolders(port)` en finally (win32 PowerShell / POSIX lsof, filtré sur la cmdline du workspace) | scripts/runtime_acceptance.js |
| P4 | `TEST_TAMPER_GUARD=strict` (.env) - un test QA modifié est restauré tel quel. SCOPE_GUARD reste warn : strict n'y ajoute que du marquage, l'enforcement réel est le retrait per-file (F7) | backend/.env |
| P5 | Constitution : contrainte COMPACTNESS (~40 lignes/check_code) + `CONSTITUTION_MODEL` (routage optionnel, réglé sur sonnet dans .env) | constitution.py, config.py, .env |
| P6 | Décompositions parallélisées : appels architecte en `asyncio.gather` bornés par `max_parallel_devs`, matérialisation séquentielle (ids uniques + floor d'indépendance) | pipeline.py `_adecompose_pending` |
| P7 | Anti-duplication inter-US : bloc « MODULES DÉJÀ PLANIFIÉS » (tâches des autres stories + file_globs) injecté dans le prompt de décomposition | pipeline.py `_existing_plan_block`, prompts.decompose_story |
| P8 | `PARTIAL_DELIVERY=1` (.env) : les stories vertes sont livrées même si une story échoue (P5/DoD incrémental) | backend/.env |
| P9 | Branche po-pipeline-v2 : DÉJÀ intégralement mergée dans main (0 commit propre). Éval A/B scripted exécutée : pipeline « on » gagne sur dimensionnement des feuilles (2/2 vs 0/2 au budget) et taxonomie des critères (4/4 vs 0/2), sans dégradation ; DAG égal. `PO_PIPELINE` reste off en attendant la confirmation provider réel exigée par le RFC | scripts/eval_po_pipeline.py |
| P10 | ST-17 : harnais e2e Playwright multi-stream dédié (`playwright.streams.config.ts`, port 8124, STREAMS=1, workspace hermétique) + spec `streams.spec.ts` (filtre par stream, tâches T-1/T-2, badge du stream non primaire, rollup done). `npm run test:e2e:streams` | frontend/e2e-streams/ |
| P11 | Hint actionnable quand le pipe Docker est refusé : « Docker Desktop est lancé dans la session Windows d'un autre utilisateur - relancez-le dans VOTRE session » | docker_deploy.py |
| BONUS | Bug CSS préexistant découvert par la revalidation e2e : la barre d'onglets mobile (R5) était invisible à TOUTE largeur - la règle de base `display:none` venait APRÈS l'override du media query (<1100px) dans l'ordre source. Override déplacé après la base | frontend/src/index.css |

Validation round 2 : backend 1159 pytest verts (+4 nouveaux), Vitest 239 verts,
e2e standard 2/2 verts (dont le bug CSS mobile corrigé), e2e streams 1/1 vert.
