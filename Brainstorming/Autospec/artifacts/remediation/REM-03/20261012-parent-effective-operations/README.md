# Contre-rejeu parent des interruptions effectives

Révision intégrée : `3a5d4a78`, core `d9b89375`. Le parent a relu les deux nouveaux fichiers test/probe puis exécuté `backend/tests/test_actual_operations_recovery.py` avec le Python factory-env, `PYTHONPATH=backend`, `AUTOSPEC_REM03_DOCKER=1` et une racine temporaire propre.

**4 PASS en 42,62 s, aucun SKIP.** CLI local constant et fusion Git réelle sur fichiers possédés ; code produit fixture exclusivement en Docker Linux NETNONE, UID65532, rootfs read-only, capabilities retirées. Le reçu brut [JUnit](rem03-parent-v1.xml) et les trois reçus [CLI](raw-v1/provider-receipt.json), [Git](raw-v1/merge-receipt.json), [smoke](raw-v1/smoke-receipt.json) conservent hashes, état durable, sorties, handles et identité Docker. Aucun appel payant/auth ni code produit hôte.

La limite de la preuve Git reste celle du rapport agent : décès après commit de fusion durable et avant finalisation orchestrateur, pas au milieu de l'algorithme interne Git. Le replay utilise les vrais raccords et la récupération dans un processus neuf, sans modifier le pipeline. Cette preuve ne vaut pas conformité des 57 exigences produit.
