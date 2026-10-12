# Replay parent de sécurité native — 7b1ea54c

Python factory-env 3.14.5 verrouillé, Docker Linux 29.5.3 ; sources intégrées figées `7b1ea54cc631a2ab8e044588e18c192e55ef261a`, ni inference, ni source produit sur l’hôte. Commande depuis `backend`, `PYTHONPATH=backend`, `AUTOSPEC_REAL_SECURITY_OBSERVATIONS=1` : `python -m pytest tests/test_security_observations_native.py -q --basetemp=<racine neuve possédée> --junitxml=<reçu>`.

- `root-security-native-final-v1.xml` : **30 PASS, aucun SKIP/FAIL/error, 245,137 s**. Cinq cas natifs réels et 25 métatests de contrôleur.
- `root-security-final-unit-v4.xml` : **100 PASS, 7 SKIP opt-ins, 3,86 s** sur security_observations/public_crypto/coordinator/source_reviewer.

Les trois conditions de cookies ont de vrais requests et handshake TLS, SQLite séparées, Argon2 et ASGI non mockés, même code/image, trois CID distincts. La fixture fautive `insecure-production` est reconnue ; la fuite fictive production-only cookie/CSRF reste détectée après fermeture de son conteneur. Le dépassement 4 MB refuse un scan complet. Autre négatif : HTTP503 avec secret avant les 130 dernières lignes et dans la réponse, détecté en logs/artefacts, alors que l’ancien tail100 ne le voit pas.

L’image finale est sauvée/scannée entièrement, tous layers sans extraction/exec host, exact digest et source-label ; image étrangère refusée avant scan. Nominal : **dix detector_candidates, dix public_non_credentials source-exacts, zéro finding**. Négatif dérivé identifié : **douze candidats, dix classes publiques, deux findings inconnus** ; l’image/tag UUID de contrôle est nettoyée seule, après attestation d’identité. Aucune exclusion générale vendor. Candidats, inventories, offsets et hashes conservés dans les JSON expurgés ; aucun cache, DB, clé TLS ni stdout privé copié ici.

Revue indépendante : REM-15/20261012-public-vendor-material/FINAL-ADDENDUM.md. Fermeture de la régression dans ces fixtures seulement ; aucun PASS SEC-01 produit, aucune R source/image fabriquée. Confiance kernel/daemon/image superviseur explicite ; heuristiques bornées, pas découverte universelle. La suite commune et la nouvelle génération/évaluation 57 IDs restent séparées.
