# Qualification finale de la fabrique — REM-24

Décision du coordinateur, 12 octobre 2026 : **REM-00..24 libérés ; REM-25 non réalisé**. La fabrique est qualifiée pour une nouvelle campagne unique, pas le futur produit Relais Support. La clôture du programme exige encore 56 critères obligatoires PASS sur 57, avec preuves indépendantes.

## Identité et régression commune

Révision source testée dans le worktree propre `autospec-regression-snapshot` : `7b1ea54cc631a2ab8e044588e18c192e55ef261a`. Le diff Git des arbres `backend`, `frontend`, `tools` entre cette révision et `4a346e1113b7ea1ebcd01e3a48f035cb01a1f5e6` est vide ; les commits ultérieurs à 7b avant cette décision ne portent que documentation/preuves. Le JUnit ne contient pas lui-même une révision : cette attribution repose sur le lancement du coordinateur et le diff source contrôlé indépendamment. Le lanceur exige ensuite le HEAD complet propre de publication.

Commande depuis la racine Git figée, avec le Python 3.14.5 de `workspace/remediation-20261011/factory-env`, environnement verrouillé et `PYTHONPATH` pointant sur son `Brainstorming/Autospec/backend` :

```text
python -m pytest Brainstorming/Autospec/backend/tests --basetemp=C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/full-regression-fifth-snapshot-v2 --junitxml=C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/full-regression-fifth-snapshot.xml -q
```

Résultat, code retour 0 : **3 232 PASS, 100 SKIP, 0 FAIL, 0 ERROR**, 3 avertissements de dépréciation, **1 787,44 s** (29 min 47 s). XML : 3 332 cas, temps de suite 1 786,689 s. Les 100 skips sont des opt-ins Docker/navigateurs/toolchains/coûteux explicitement désactivés dans la suite globale ; aucun ne constitue un PASS et aucun fallback de dépendance manquante n'est accepté. Les probes natives critiques sont conservées séparément par tâche ; les nombres de suites ciblées ne sont pas additionnés comme des tests uniques.

- [JUnit complet](full-regression-fifth-snapshot.xml), SHA256 `c3d76d8f9c325798cb3677a07d59d4fad67b7be49518613575e99ba68493b759`.
- [Sortie complète](full-regression-fifth-snapshot.log), SHA256 `89d7327908953e9d65fc9caf00af7649fb6d1994d3d3844c4a6dbbfe438d1c30`.
- [Invocation initiale mal formée](full-regression-fifth-invocation-v1.log) : retour 4, aucun test exécuté. Correction de l'argv PowerShell et nouveau basetemp, sans changement de source/assertion.
- [Contre-revue indépendante et addendum final](FINAL-INTEGRATION-REVIEW.md) : comptes, hashes, identité source et clôture du replay contrôlés en lecture seule.

Les avertissements concernent Starlette/httpx TestClient et les API legacy websockets ; ils ne changent pas le verdict. Les globales rouges précédentes, notamment quatrième 3 044 PASS/10 FAIL/93 SKIP, restent dans `../20261012-final-integration/` et leurs preuves de correction ciblées. Elles ne sont pas réécrites en succès.

## Dépendances et preuves critiques

La [matrice DoD](../20261012-dod-launch-matrix.md) identifie deux raccords encore ouverts à sa lecture ancienne, tous deux désormais fermés :

- REM-15 : scans source/image/logs et cookies TLS/HTTP/CSRF réels, [replay parent](../../REM-15/20261012-parent-native-security/) **30 PASS, 0 SKIP, 245,137 s**, unités finales **100 PASS/7 SKIP**. [Addendum indépendant](../../REM-15/20261012-public-vendor-material/FINAL-ADDENDUM.md) : dix candidats publics PEM/DER exacts classifiés, candidats conservés, deux secrets fictifs du contrôle négatif restent findings ; pas de waiver vendor ni de R produit fabriquée.
- REM-17 : vrai DTO `display_name`, requête courante et erreur 404 réelle dans Docker NETNONE, [replay parent](../../REM-17/20261012-parent-error-client/) **1 PASS, 0 SKIP, 26,39 s** ; contribution étroite, pas PASS ARC complet supposé.

Autres preuves déterminantes déjà revues et intégrées :

- REM-01/02/06 : Docker NETNONE/non-root, exécution pytest image-owned, Jobs/handles Windows et CID exacts, faux pytest/reporters fermés ; [raccords revus](../20261012-evidence-joins/), notamment mêmes **22 tests indépendants PASS** rejoués par le parent.
- REM-03 : [CLI/Git/smoke effectifs avec crash puis reprise](../../REM-03/20261012-parent-effective-operations/), **4 PASS, 42,62 s** ; coût inconnu réel interdit le redispatch.
- REM-19/20/21 : suites/coverage/mutation/E2E scellées, image finale/CMD baked/persistance/README/audit, cache lié au moteur/source/R actuelle ; [replays finaux parent](../20261012-parent-final-replays/). Tests Autospec frontend **308 PASS**, TypeScript/Vite build PASS et trois E2E UI usine séparés.
- REM-23 : réservation concurrente implémentée/testée **76 PASS**, mais **OFF pour Claude** : aucun cap financier dur par appel qualifié. Aucune accélération ni maîtrise de facture n'est prétendue.
- REM-25 : [51 PASS offline et contre-revue du lanceur](../../REM-25/20261012-launcher-independent/), puis préflight réel `claude.ai/firstParty/Team`, Linux Docker/hashes/flags PASS ; [superviseur Windows réel](../../REM-25/20261012-native-supervisor/) rc0, 5,97 s, interception **avant tout POST**, aucun projet/provider lancé, nettoyage exact prouvé. Le lancement final doit refaire le préflight frais.

## Libération et limites

Clôture coordonnée des capacités dans l'ordre des dépendances : REM-00, 01, 02, 03, 04, 05, 06, 08, 09, 10, 11, 12, 13, 14, 07, 15, 16, 17, 18, 19, 20, 21, 22, 23, puis 24. Les preuves ciblées et replays communs satisfont la DoD de fabrique ; elles ne remplacent aucune observation du nouveau produit.

Stacks exécutables qualifiées ici : Python/FastAPI, React/TypeScript/Vite et SQLite. Go/Rust non qualifiés restent refusés, pas remplacés silencieusement. Trust explicite : hôte superviseur, kernel/daemon Docker et CLI authentifié ; ce n'est pas une preuve d'absence universelle de faille container. Scans bornés et découverte de secrets non universelle : dépassement/absence donne NOT_VERIFIED, revue source indépendante toujours requise. Les matériaux publics exacts ne constituent ni credentials ni approbation supply-chain complète du binaire.

Autorisation REM-25 existante : une nouvelle campagne, brief/référentiel v0.2 inchangés, génération seule Claude Code Sonnet via abonnement Team, plafond **40 USD estimés**, sérialisation, aucune API directe/crédit additionnel. Proposition opérationnelle et revue indépendante restent dans deux sous-agents GPT-6.1-sol medium distincts. Aucun montant estimé n'est présenté comme une facture ou un cap financier dur. Préserver campagne historique, autres projets et démonstration 18004 ; aucun code généré exécuté sur l'hôte, aucune réparation manuelle du produit pour rendre son verdict vert.
