# Quatrième régression et diagnostic des dix échecs

Snapshot propre figé `96af8140ab8886c07936576344f36039dc0d6434`. Python factory-env 3.14.5, `PYTHONPATH=backend`, racine pytest temporaire propre, opt-ins natifs Linux non activés pour cette globale. Aucun appel LLM réel ni exécution produit hôte. Commande : `pytest backend/tests --basetemp=<racine nouvelle> --junitxml=full-regression-fourth-snapshot.xml -q`.

Résultat brut conservé : **3 044 PASS, 10 FAIL, 93 SKIP en 1 931,01 s**. Voir [JUnit](full-regression-fourth-snapshot.xml) et [log](full-regression-fourth-snapshot.log). La globale est rouge ; un replay ciblé ne la réécrit pas en verte.

## Diagnostic et corrections

- Sept FAIL dans `test_generation_policy_counterreview.py` : les deux URLs `offline.test` des fixtures sont désormais refusées par la garde Host. Migration à loopback sans exception de production ni assertion supprimée : `928723a4`. Les sept cas ont été contre-rejoués dans le corpus 91 PASS et le replay parent 157 PASS, conservés séparément. Une autre panne à froid de routage QA a été découverte indépendamment puis corrigée par `d9b89375` ; les processus frais et assertions inchangées sont documentés sous REM-25.
- `test_failed_call_is_captured` et `test_dev_refine_failure_keeps_story_done` : timeout à 90 s, reproduit sur la cible intégrée par [replay-v1](global-fourth-failures-replay-v1.xml), 2 FAIL / 1 PASS en 215,37 s. Cause : `FakeRunner`, stand-in local sans provider, lève une erreur sans reçu lorsque sa file est vide ; le nouveau garde coût inconnu refuse alors légitimement tout redispatch. Ce n'est pas un délai Git à masquer par une nouvelle augmentation du timeout. Les deux contre-exemples minimaux sont RED dans [before](fake-runner-receipt-before-v1.xml), avec le négatif provider non attesté déjà PASS.
- Correction limitée à `FakeRunner` : son épuisement porte maintenant un reçu explicite zéro coût/token, puisqu'aucun provider n'est appelé. Aucun provider réel ni garde `COST_UNREPORTED` n'est assoupli.
- `test_dynamic_scheduler_starts_dependent_before_slow_sibling` : timeout extérieur 40 s dans la globale. Le même test, mêmes délais et assertions, passe dans les deux replays ciblés ; aucune correction fonctionnelle ou augmentation de son délai. Une sensibilité à la charge est observée ; une causalité unique n'est pas démontrée.

Rejeu après correction : [replay-v2](global-fourth-failures-replay-v2.xml), **65 PASS en 34,14 s**. Inclut les trois échecs pipeline/scheduler exacts, les trois nouveaux contre-tests de reçu et six modules usage/budget/cleanup/recovery/activity. Le négatif « erreur provider réel sans reçu » conserve un unique dispatch puis bloque par `COST_UNREPORTED`. Ce sont des superviseurs locaux et des doubles inertes, pas une génération payante.

## Limites de qualification

Les 93 SKIP restent distincts des probes natives effectivement exécutées ailleurs (53 tests pytest isolé parent, reprise Docker REM-03 4/4, navigateurs/images/DB documentés par tâche). Aucune conformité du futur produit n'est déduite. Les nouveaux collecteurs SEC/ARC et le lanceur REM-25 postérieurs à ce snapshot nécessitent leurs propres contre-replays et intégration. Une nouvelle globale sur la révision finale reste à réaliser pour annoncer une globale verte.
