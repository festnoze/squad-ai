# Frontières Git, tests, interruption et plans externes

Tests hors ligne, sans appel modèle payant et sans exécution du produit sur l'hôte.

- `root-boundaries-v3.xml` : 100 PASS, 1 opt-in SKIP, 211,98 s. Inclut une vraie création Git imbriquée, worktree et merge sur fichiers inertes, sans adoption du dépôt parent ; coût connu conservé après cancellation ; tests custom réellement collectés protégés.
- `review-boundaries-v4.xml` : 67 PASS, 1 opt-in SKIP, 3,93 s. Inclut refus des variantes expansives de cleanup et absence d'annonce de rollback réussi après échec de reset/clean.
- `review-plans-v1.xml` : 24 PASS, 1,06 s. Admission mécanique proposition/revue, inventaires bornés et profil de mutation associé au vrai hash de la copie. Fixtures/revues synthétiques : ne qualifie aucun produit livré.

La revue reste locale via deux agents GPT 6.1 sol medium distincts. Aucun export de source à Claude ni revue Claude automatique. Les reçus R portent sur les sources et les plans ; seuls les runners indépendants peuvent produire X/V. Une absence de suite, de mapping, de couverture, de fixture ou de capacité reste un défaut ou NOT_VERIFIED, jamais un succès par défaut.

La contre-revue intégrée et la nouvelle campagne de qualification complète sont encore requises ; ces résultats ne sont pas un PASS global des 57 critères ni une clôture des 26 tâches.
