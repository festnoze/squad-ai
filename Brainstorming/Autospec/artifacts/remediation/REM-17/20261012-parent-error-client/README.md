# ARC-06 — replay parent du collecteur réel

Révision intégrée `8023168a`. `root-arc-netnone-v1.xml` : **1 PASS en 26,39 s**. Fixture de contrôleur de confiance ; aucune conformité du futur Relais Support déduite.

Commande depuis `backend`, Python factory-env 3.14.5 verrouillé, `PYTHONPATH=backend`, opt-in `AUTOSPEC_REAL_ARCHITECTURE_BROWSER=1` : `python -m pytest tests/test_architecture_browser_native.py -q --junitxml=<reçu>`. Le test impose OwnedProductHarnessSession puis DockerBrowserSession, Linux NETNONE, réseau navigateur lié au CID exact du serveur, et interdit le lancement Chromium hôte. Les requêtes HTTP, SQLite, Argon2 et le frontend de la fixture sont réels ; aucune réponse nominale injectée.

Le dossier `docker-nominal` conserve le JSON et les deux captures intactes : identité `display_name` venant de GET `/api/auth/me`, puis erreur 404 réelle du GET ticket absent présentée par le client. Cleanup des seules ressources possédées par ce test. Le reçu étroit `ARC-06:error_client` est raccordé avant ArchitectureVerifier ; il ne remplace pas le reste du critère ARC-06 ni sa R indépendante.

La confiance dans le daemon/noyau/image du superviseur reste explicite ; cette qualification n'est pas une TEE. Aucun appel LLM, credential utilisateur, autre projet, préflight ou génération.
