# REM-14 — preuve navigateur du jalon vertical

## Changements

- L’observateur navigateur exige des sélecteurs distincts pour le titre et la description de la page détail. En l’absence de ces liaisons relues, le résultat est `NOT_VERIFIED`; un contrôle de texte partiel ne peut plus produire un faux PASS.
- La preuve compare le titre et la description créés aux valeurs du GET réellement reçu, puis vérifie que l’interface affiche exactement ces valeurs.
- La fixture `wrong_detail` affiche désormais un faux suffixe et est rejetée par comparaison exacte.
- La fixture publique sans authentification ne requiert pas de liaison ou de contrôle de formulaire de connexion. La preuve marque l’étape authentification `N/A` et vérifie l’absence de POST login.
- La régression de test locale lit le reçu JSON `X`, et non la première preuve qui peut être une capture PNG `V`.

## Vérifications

- Ciblage navigateur/liaisons sans exécuter le harnais produit : **4 passed, 10 skipped, 53 deselected**. Les cas opt-in sont volontairement désactivés dans ce ciblage.
- Qualification complète du harnais Docker réel (`AUTOSPEC_REAL_PRODUCT_HARNESS=1`) : **24 passed en 579,10 s**, avec preuves copiées sous `artifacts/remediation/REM-14/20261015-completion/product-final/`.
- Les reçus `nominal/receipt.json` et `baked/receipt.json` confirment chacun les 9 étapes PASS, dont bootstrap Argon2 réel, login/création navigateur, GET API, commit DB, remplacement du conteneur et persistance sur le même volume. Les cas négatifs `lost_note` et `reset_on_start` restent FAIL comme attendu.
- La suite ciblée d’observateur navigateur reste **4 passed, 10 skipped, 53 deselected**; le harnais réel active séparément les tests Docker opt-in.
- Le premier rejeu du delta avant ces changements avait exposé un faux PASS `wrong_detail`; il n’est pas compté comme résultat du code corrigé.

## Limites

Le harnais isolé constitue une qualification de capacité de la fabrique et de ses adaptateurs. Il ne prouve pas la conformité des 57 critères d’un nouveau produit généré.
