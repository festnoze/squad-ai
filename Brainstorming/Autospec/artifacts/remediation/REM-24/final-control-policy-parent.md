# Replay parent — frontière de contrôle et politique de génération

Révision testée : `1993356a` (source core `d9b89375`). Exécution locale du superviseur autorisée ; aucun code produit généré exécuté sur l'hôte, aucun appel LLM réel.

Commande : Python de l'environnement factory-env, `PYTHONPATH=backend`, `pytest backend/tests/test_factory_control_boundary.py backend/tests/test_generation_policy_counterreview.py backend/tests/test_persona_policy_cold_start.py backend/tests/test_owned_delivery_lifecycle_guards.py backend/tests/test_source_plan_limits.py --junitxml=final-control-policy-parent-v1.xml -q`.

Résultat : **157 PASS en 4,96 s**, zéro FAIL/SKIP. Deux avertissements de dépréciation uvicorn/websockets non bloquants. Le test TCP emploie un callback de fabrique inerte, pas un lancement de génération. Le reçu brut est [conservé ici](final-control-policy-parent-v1.xml).

Périmètre : garde Origin/Host, admission génération-seule, résolution des personas à froid, cycle de vie possédé et contraintes du plan source. Ce replay ne constitue ni une régression globale sur cette révision ni une preuve de conformité du futur produit. La quatrième globale s'exécute séparément sur `96af8140`.
