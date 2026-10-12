# REM-16/17/18/21 — preuves natives et navigateur courantes

Révision de raccord `8023168a`, après `ad35d1ae` (ProbePack) et `f72f15e6` (collecteur ARC). Les documents v0.2 sont inchangés. Aucun appel LLM, préflight abonnement, nouvelle génération ni réparation du produit historique.

## Défauts de fabrique corrigés

1. ARC-01/09, source-only, ajoutaient un manque permanent malgré leurs R exactes intactes. Le pack consomme désormais ces R sans inventer de sonde native ; revue absente/partielle/altérée/négative reste NV/FAIL.
2. Les contributions FUN-02/06/12 mesuraient les bons gestes, sans publier les tags exacts `ui_clear/ui_draft/ui_refresh` exigés. Ces tags sont émis uniquement après les observations réelles correspondantes, pas à partir d'un verdict producteur.
3. SEC-10/12 et FUN-02/06/12 attendaient V/UI avant leur production ; la fusion conservatrice ne pouvait pas promouvoir ce NV. Le coordinateur publie un X `RID:backend` seulement quand les bytes du reçu correspondent aux observations natives complètes, recueille X/V navigateur, puis rejoue uniquement les cinq sondes serveur concernées. Un premier FAIL ou une exécution incomplète ne peut pas être sélectionné vers un succès. R demeure externe ; snapshots/oracles différents sont refusés.
4. Les chemins fixes des X ProbePack invalidaient le reçu antérieur au second passage. Des chemins UUID conservent les deux preuves.
5. ARC-06 demandait `error_client` sans producteur. La contribution du nouveau collecteur est publiée avant le pack ARC complet ; jamais son PASS étroit ne devient un PASS de toute l'architecture.

## Reçus et limites

- `probepack-after-v1.xml` : 36 PASS auteur ; rapport distinct. Contrôles de sélecteurs, R-only, complétude d'exécution et deux preuves UUID.
- `root-join-first.xml` : 53 PASS parent, métatests de raccord + ProbePack.
- `root-join-pack-v2.xml` : 210 PASS, 2 FAIL, 2 opt-ins SKIP, 263,56 s. Les deux rouges viennent uniquement du nouveau test parent plaçant le store à la racine produit alors que sa fixture conserve ses X dans la racine superviseur sœur. Le contrôle a correctement refusé la preuve hors scope ; la racine du TEST a été corrigée, pas le contrôle de production. Les autres packs/Chromium réel de fixtures de confiance passent, avec deux avertissements websockets dépréciés.
- `root-join-final-v3.xml` : 60 PASS, 3,33 s. Inclut les deux fixtures sécurité précédemment rouges après correction du setup, ainsi que le nominal/les négatifs du nouveau raccord.
- `join-counterreview-v4.xml` : 22 PASS indépendant, 2,54 s. Métatests source/API/SQLite de confiance, UI/R doubles explicitement bornés ; aucune acceptation d'un produit déduite. V1/V2 d'erreurs de setup externe sont conservés. Rapport et code indépendant copiés sans modification.
- `root-join-independent-parent-v5.xml` : les mêmes 22 contre-tests indépendants, inchangés, rejoués par le coordinateur sur le raccord intégré : 22 PASS en 3,14 s.

La suite commune reste nécessaire : la quatrième globale historique a 10 FAIL et n'est pas requalifiée par ces reçus ciblés. Les collecteurs réels ont leurs preuves Docker distinctes ; les métatests de raccord ne constituent pas les 57 PASS du futur produit. L'image/kernel/daemon superviseur restent de confiance, sans prétention de TEE.

Exécutable : `workspace/remediation-20261011/factory-env/Scripts/python.exe` (Python3.14.5, dépendances verrouillées). Commandes parent depuis `backend`, `PYTHONPATH=backend`, `python -m pytest -c pyproject.toml ... -q --junitxml=<reçu>` ; contre-tests externes avec `-o asyncio_mode=auto`. Tests superviseur locaux autorisés explicitement par l'utilisateur. Aucun credential réel ni fichier d'autre projet dans le scope.
