# Frontières Git, tests, interruption et plans externes

Tests hors ligne, sans appel modèle payant et sans exécution du produit sur l'hôte.

- `root-boundaries-v3.xml` : 100 PASS, 1 opt-in SKIP, 211,98 s. Inclut une vraie création Git imbriquée, worktree et merge sur fichiers inertes, sans adoption du dépôt parent ; coût connu conservé après cancellation ; tests custom réellement collectés protégés.
- `review-boundaries-v4.xml` : 67 PASS, 1 opt-in SKIP, 3,93 s. Inclut refus des variantes expansives de cleanup et absence d'annonce de rollback réussi après échec de reset/clean.
- `review-plans-v1.xml` : 24 PASS, 1,06 s. Admission mécanique proposition/revue, inventaires bornés et profil de mutation associé au vrai hash de la copie. Fixtures/revues synthétiques : ne qualifie aucun produit livré.
- `native-execution-receipts-v3.xml` : 42 PASS, 8 opt-in SKIP, 1,46 s. argv/rc réellement capturés et horloges install/tests séparées.
- `native-execution-receipts-real.xml` : 8 PASS, 59,24 s, opt-in Docker actif. Suite Python verrouillée NETNONE, compilation frontend et image/cache natifs. Ne qualifie pas le produit Relais Support.
- `browser-control-boundary-v1.xml` : 18 PASS, 0,46 s. Refus de parents non possédés, réseau/ports publiés, identité de conteneur modifiée et SW/WS non confinés. Métatests du tunnel, pas une preuve de navigateur Docker exécuté.
- `native-pipeline-raccord-v3.xml` : 136 PASS, 1 opt-in SKIP, 16,64 s. Raccord collecte/revue/jugement ; journal QA atomique inter-processus ; refus de baseline empoisonnée au retry ; fixtures legacy explicitement fake et canari réel sans purge hôte. Après contre-revue du CMD, l'ordre cible devient audit natif → revue → construction image avec argv revu baked → faits natifs → jugement (replay requis).
- `full-regression-second.xml` : 2 318 PASS, 14 FAIL, 61 opt-in SKIP, 2 064,95 s (34 min 24). Résultat global non vert conservé ; corrections ciblées de fixtures et défauts sont en cours, aucune baisse de règle d'isolation pour masquer ces échecs.

Les runs intermédiaires `native-pipeline-raccord-v1.xml` (7 FAIL : import FileBroker manquant, corrigé), `review-delivery-v1.xml` (1 FAIL : fixture globale devait maintenant inclure le sujet OPS-05), puis les replays v2/v3 sont conservés. Les tests de scellés utilisent des réponses X/R synthétiques annoncées comme telles et ne constituent aucun PASS produit.

Le protocole lie désormais chaque réponse à l'empreinte complète du paquet (phase, sources, proposition, qualité, audit natif et sujet de livraison). Les approbations de livraison et d'audit nomment aussi leur empreinte exacte ; une ancienne approbation au même snapshot ne peut approuver un nouveau sujet. Une collection obtenue avec rc non nul reste un fait X et une valeur d'échec, pas un PASS d'acceptation.

La revue reste locale via deux agents GPT 6.1 sol medium distincts. Aucun export de source à Claude ni revue Claude automatique. Les reçus R portent sur les sources et les plans ; seuls les runners indépendants peuvent produire X/V. Une absence de suite, de mapping, de couverture, de fixture ou de capacité reste un défaut ou NOT_VERIFIED, jamais un succès par défaut.

La contre-revue intégrée et la nouvelle campagne de qualification complète sont encore requises ; ces résultats ne sont pas un PASS global des 57 critères ni une clôture des 26 tâches.
