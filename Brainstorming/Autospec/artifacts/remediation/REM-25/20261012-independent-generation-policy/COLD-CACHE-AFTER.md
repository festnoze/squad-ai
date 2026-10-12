# AFTER indépendant du P1 nominal à cache froid

Cible source exacte : `d9b893754fbd5725529710799d15b7599b669eb8`.
Sources du parent en lecture seule, assertions/contre-tests inchangés depuis
la seule migration des deuxURL ASGI autorisées (`da81d590`). Le correctif du
cache appartient au parent, pas à l'auteur de cette contre-revue.

Verdict ciblé : **P1 cold routing résolu dans les voies reproduites**.
La construction de `_persona_role` indexe seulement les noms GENERATION_ROLES
en campagne, sans appeler les personas de revue interdites. La nouvelle map
locale est publiée par mode seulement après construction complète ; aucune
table générique ou partielle n'est réutilisée. La validation publique des NOMS
avant lru reste intacte. Aucun nouveau P0/P1 confirmé dans ce correctif ciblé.

## Replays attribuables

- `after-v3.xml` / `.log` : mêmes SIX modules, mêmes **91 IDs**, **91 PASS,
  0 FAIL, 0 SKIP, 2,92 s**, rc0. Comparaison JUnit avec after-v2 : zéro ID
  ajouté/supprimé/renommé ; assertions et source des contre-tests inchangées.
- `cold-qa-after-v3.xml` / `.log` : cas QA EXISTANT lancé SEUL dans un processus
  neuf, **1 PASS, 0,60 s**, rc0. Ce même cas était 1 FAIL sur96af8140 avec les
  mêmes I/O stubbés et assertions. Il ne dépend plus du négatif Opus ou d'un
  préwarming effectué par un autre test.
- `cold-modes-after-v3.xml` / `.log` : test_persona_policy_cold_start.py,
  **7 PASS, 0,39 s**, rc0 : QA/dev/PO-spec chacun avec/sans préwarming générique,
  et construction en échec qui ne publie pas une map partielle. Ce sont sept
  métatests du parent rejoués indépendamment, pas sept nouveaux tests écrits ici.

Le cas QA seul est un replay supplémentaire d'un ID du corpus91, pas un
nouveau test distinct. Aucun FAIL historique n'est effacé ou réétiqueté.

## Reproduction

Depuis backend, Python verrouillé
`C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe`.
Trois processus frais, chacun avec son basetemp distinct et les variables
AUTOSPEC_REAL_CLAUDE_PROBE / AUTOSPEC_REAL_LINUX_VALIDATION /
AUTOSPEC_DOCKER_BOOTSTRAP_BROWSER à0, AUTOSPEC_REAL_DOCKER_IMAGE vide :

```text
python -m pytest tests/test_generation_only_policy.py
  tests/test_generation_policy_counterreview.py tests/test_providers.py
  tests/test_api_provider.py tests/test_anthropic_provider.py
  tests/test_rem24_budget_and_cache_counterreview.py -q --tb=short

python -m pytest
  tests/test_generation_policy_counterreview.py::test_real_runner_argv_shape_pins_sonnet_and_excludes_api_keys[qa]
  -q --tb=short

python -m pytest tests/test_persona_policy_cold_start.py -q --tb=short
```

Basetemp suffixes exacts sous le workspace possédé remediation-20261011 :
`generation-policy-after-v3`, `generation-policy-cold-qa-after-v3`,
`generation-policy-cold-modes-after-v3`. JUnit et stdout sont conservés sous
les noms correspondants dans ce répertoire de preuves.

Pas de lancement campagne, auth/probe/CLI réelle, appel provider ou inférence
payante : **coût réel de génération de cette vérification = zéro**. Les vrais
chemins superviseur sont exercés avec FakeRunner/I/O CLI scriptés et ASGI
local, pas avec code produit hôte. Aucun tableau partagé, snapshot historique
ou fichier source du parent modifié ; diff source du worktree vide après test.

## Limites et suite

Ce replay qualifie le correctif du rôle/cache, pas le launcher futur ni
l'authentification Team, un budget de facturation dur ou une admission produit
56/56. L'ancienne limitation du wrapper reste explicite : un superviseur trusté
forgeant volontairement un texte dev connu est hors frontière d'autorité de
la validation de noms. Les personas textuelles restent lru_cached comme voulu.

Le launcher source final doit être fourni puis revu en lecture seule : flag
actif et OFF de revue/télémétrie AVANT import/création `_runner`, wrapper réel,
Sonnet à toutes les routes, environnement sans clés/API, coûts non réconciliés
bloquants et R externe uniquement. **Aucun démarrage autorisé par ce rapport.**
Le corpus277 n'est pas rejoué ici ; ses quatre SKIP restent non requalifiés.

## SHA256

- pipeline source : `37593f426b4ad30954db974953d50482db32b7f77461b1f62b75a72e7783a107`.
- personas source : `fb8c9c9eada05783126cdfe5b59a269ce61e53971b77ec623426c1b9611512c5`.
- contre-tests indépendants inchangés : `a50ab07b73fea76acf60ff514ae2d15e3f095c94a2bf011846f90f7116c6ffbb`.
- nouveaux tests parent : `432f2d48a0d644ecf43d1839e41fc737c56aefd0e7b0acfb808e0f9f004be05c`.
- after91 XML : `fb2a3acbdcbdb0aec4bf3c030c40a8796f32dd667edbd25290af1f940fb55076`.
- cold QA XML : `62c2b47075078bf152208a8cd3c1372f37e100100702ff68b52f0418f80dbca0`.
- cold modes XML : `6334af3c8c1316bcaba957733a84d4826b0fd2462e6330beda6ae8d1a160954a`.
