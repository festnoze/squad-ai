# REM-03 — Interruption des opérations effectives

Le complément demandé est exécuté, pas simplement préparé : **22 PASS / 2 SKIP en 49,87 s** sur le code `95fa62ea`, basé sur l'intégration `c35f3bf9`. Les quatre nouveaux tests sont PASS. Aucun pipeline, API, modèle ou tableau de suivi n'a été édité pour obtenir ce résultat.

Cette preuve couvre la mécanique de la fabrique demandée par la fiche REM-03 du plan de remédiation. Elle ne déclare ni un produit conforme, ni les 57 exigences de Relais Support PASS, ni la régression globale verte.

## Opérations et barrières

| Opération réelle | Point d'interruption attesté | Résultat après redémarrage réel |
| --- | --- | --- |
| `Pipeline._tracked.arun` → `_run_tracked` → CLI local constant | Le CLI a reçu le prompt par stdin et publié son empreinte ; l'activité provider était déjà enregistrée durablement. Handles de l'interpréteur usine et du CLI vérifiés dans le Job Windows exact. | `recover_projects` dans un nouveau processus donne STOPPED/interrupted, aucune tâche de fond ni timer de reprise ; usage sans reçu conservé et redispatch refusé par `COST_UNREPORTED`. |
| `Pipeline._amerge_work_item` → `_agit` → `git_boundary.run_git` | Git a réellement produit une fusion `--no-ff` à deux parents ; contribution présente, verrou détenu par T1. Barrière avant la note/finalisation de la transaction. | Commit et octets conservés ; tâches transitoires réconciliées sans augmenter les tentatives. Rejeu explicite de la même branche ne crée aucun commit supplémentaire. |
| `Pipeline._asmoke_phase` → `_smoke_run_python` → `IsolatedValidator.run_captured` | Le conteneur en cours d'exécution a émis le marqueur produit, avec UID 65532 ; image immuable, CID, propriétaire et configuration NETNONE inspectés réellement. | Projet GOVERN reconnu interrompu, tâche DONE conservée mais livraison non prête. Rejeu explicite du même snapshot retourne sans erreur ; aucune génération et aucune livraison qualifiée implicite. |

L'arrêt utilise `close_owned_process` sur le handle possédé, jamais un nom d'exécutable ou un balayage PID. Les handles OS retenus des interpréteurs sont signalés après l'arrêt. Cela couvre aussi le redirecteur `python.exe` des virtualenvs Windows : son PID n'est pas nécessairement celui du vrai interpréteur ; le test refuse donc de déduire la propriété d'une égalité PID approximative.

Le daemon Docker peut conserver le conteneur après disparition du client usine. Le probe superviseur le retire uniquement après réattestation du **CID immuable + label `autospec.run_id` exact**, puis atteste son absence. Il n'y a aucun prune, killall, sweep, montage du socket Docker ou fallback hôte. Le smoke est une fixture CLI constante, sans dépendance externe ni DB ; son lock est préparé par le résolveur manifest-only de confiance. La résolution n'exécute pas le source produit. Les images/cache de dépendances partagés ne sont pas retirés arbitrairement.

Le CLI local n'est ni Claude ni Codex : c'est un stand-in gratuit, constant, exécuté par la même frontière de propriété/lifecycle que les appels réels. Le nominal démontre un seul reçu comptabilisé, zéro coût et zéro appel non remonté. Aucun provider payant, authentification abonnement ou générateur n'a été invoqué.

## Rejeu et preuves brutes

Depuis `backend`, avec le Python de l'environnement factory verrouillé :

```powershell
$env:PYTHONPATH=(Get-Location).Path
$env:AUTOSPEC_REM03_DOCKER='1'
$env:AUTOSPEC_REM03_EVIDENCE='../artifacts/remediation/REM-03/20261012-effective-operations/raw-v4'
& 'C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe' -m pytest -c pyproject.toml tests/test_actual_operations_recovery.py tests/test_activity_remediation.py tests/test_generation_recovery_remediation.py tests/test_owned_execution.py -q --junitxml='../artifacts/remediation/REM-03/20261012-effective-operations/operations-final-v4.xml'
```

Les fichiers finaux sont `operations-final-v4.xml`, son log et les trois `raw-v4/*-receipt.json`. Chaque reçu contient les hashes des modules superviseurs réellement utilisés, le hash du worker constant, les sorties/codes retour, l'état avant crash et l'état relu après redémarrage. Le reçu smoke conserve l'inspection Docker réelle et le hash source identique avant/après, `ea2d8f09bbb4ecd1dd71dd448073b02e24c2cd67a626f536a1e94a1649853af2`.

Les deux SKIP concernent seulement `test_real_docker_nominal_and_adversarial_operations_preserve_host` et `test_real_docker_timeout_cleans_only_its_owned_container`, qui possèdent leur propre opt-in. Ils ne sont pas revendiqués exécutés par ce replay. Le nouveau `test_actual_smoke_container_death_and_same_source_explicit_recovery` est PASS, pas SKIP.

Historique conservé sans remplacement :

- `operations-v1.xml` : 2 FAIL / 1 PASS / 1 SKIP en 6,75 s. Échec du probe sur la distinction lanceur/interpréteur Windows, pas défaut produit ni assertion d'interruption satisfaite.
- `operations-v2.xml` et `raw-v2` : 3 PASS / 1 SKIP en 12,41 s, preuves CLI/Git avec membership Job exact.
- `operations-v3.xml` et `raw-v3` : les quatre opérations nouvelles sont PASS en 33,87 s, premier smoke natif complet.
- `operations-final-v4.xml` et `raw-v4` : replay sur commit stable, barrière Git bornée et attestation supplémentaire du handle usine du smoke, plus les régressions checkpoint/recovery/ownership.

Pour un nouveau replay, choisir de nouveaux suffixes et une nouvelle racine evidence afin de ne pas écraser ces reçus historiques.

## Portée et limites

- La fusion Git est interrompue **après** le commit durable du vrai Git et **avant** finalisation de la transaction orchestrateur, sous le verrou de merge. Ce n'est pas une promesse d'arrêter Git au milieu de son algorithme ou une preuve de récupération d'un index Git intrinsèquement corrompu.
- Les tests exécutent les vrais raccords des opérations et la vraie récupération API, mais pas une campagne entière de planification/build ni une reprise payante. Ils ne modifient pas le pipeline pour ajouter une barrière de production.
- Le checkpoint récupéré garde l'identité du run et la dernière phase (`build` ou `govern`). Les stages transitoires sont volontairement remis à `queued`. Aucune affirmation de conservation GUI de tous les sous-jalons perdus n'est faite ici.
- Le processus superviseur et son CLI constant sont de confiance sur l'hôte ; seul le produit fixture est exécuté en Docker. La preuve native de handles/Job est Windows. Les limites de confinement in-process d'une suite produit restent distinctes, comme documenté par REM-01.
- DONE reste indépendant de l'état de livraison. Le smoke nominal/rejoué ne devient pas un PASS de sécurité, métier, navigateur, SQLite ou de livraison finale.
- La globale historique rouge reste conservée. Ce complément propose la libération du gap de preuve opérationnelle REM-03 au coordinateur ; il n'édite pas le tableau partagé et ne clôt pas seul REM-24/25.

Les deux sources v0.2 et les facts approuvés sont restés inchangés : brief `0a99950df5ee132253fa5aefb1a8f6e4f7a4b64c1436072564be6d28195fb0f3`, référentiel `efdab8ea54208557f01abcb5324172e42b9c5cf88536611d64ba65b92564cbf4`, facts `f2b3105f207cdf4d2feb7219535146e6890d838c7b4a93a4975c6ded040644b9`.
