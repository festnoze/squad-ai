# Relais externe GPT — 12 octobre 2026

Décision utilisateur : aucune revue des sources via Claude Code. Claude reste le fournisseur de génération autorisé ; les revues des sources sont confiées à deux sous-agents distincts GPT 6.1 sol, raisonnement medium.

Le superviseur produit un paquet local attaché au hash du code et de l’oracle. La proposition ne vaut pas approbation. Le second reçu doit provenir d’un agent différent et citer les sources exactes. Aucune preuve d’exécution X ou navigateur V n’est produite par ces reçus R. Les preuves restent hors de la racine modifiable du produit.

Exécution locale hors réseau, Python 3.14.5 dans l’environnement de fabrique verrouillé :

`python -m pytest tests/test_external_review_handoff.py tests/test_milestone_delivery_raccord.py tests/test_source_reviewer.py tests/test_budget_tracker_reservations.py -q --tb=short --junitxml=local-gpt-review-budget-v4.xml`

Résultat : **49 PASS en 6,31 s**, code retour 0 ; JUnit ci-joint. Les reçus des tests sont fictifs et attestent seulement les mécanismes d’admission, jamais un produit réel.

Contrôles : modèle/raisonnement, deux identités distinctes, hash de code, citations, IDs exhaustifs, configuration refusée sans revue, attente bornée et annulation ; admission de jalon/finale ; journal budgétaire durable qui ne peut pas être contourné par restart/désactivation/provider absent/token-only. La voie budgétaire concurrente reste OFF pour Claude : aucun fournisseur de production qualifié par un cap USD dur.

Essais antérieurs conservés dans workspace/remediation-20261011 : v1 (9 échecs d’initialisation du dossier de revue, corrigés), v2 (28 PASS), v3 (4 échecs dus à un objet de contrat incomplet dans les nouveaux tests), v4 (49 PASS). Ni ces suites ni leur réussite ne closent les 26 tâches ou la requalification sur 57 critères.
