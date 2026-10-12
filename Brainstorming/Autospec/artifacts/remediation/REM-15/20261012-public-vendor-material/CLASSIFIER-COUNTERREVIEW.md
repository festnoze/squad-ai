# Contre-revue lecture seule du module isolé — 2026-10-12

## Résultat et scope

Aucun P0/P1 identifié dans la politique et les données du module `backend/autospec/validation/public_crypto_fixtures.py` lu dans le worktree integration. SHA256 du module à cette lecture : `20dee7f0bb0cbb4459ff3281940c8118b715e95d8ac119c95bd31ec573b01ce6`.

Cette conclusion est une revue source du classificateur isolé, **pas** une attestation du scanner raccordé, de sa chaîne de mesures, de son reçu nominal, ni un PASS SEC01/R produit. Les tests source `backend/tests/test_public_crypto_fixtures.py` ont été lus ; le résultat 21 PASS a été communiqué par le parent, non réexécuté dans cette contre-revue.

## Vérifications

- Les dix couples hash/symbole sont identiques à l'inventaire upstream public indépendamment calculé, incluant DSA. Source URL épinglée au commit et SHA256 source corrects.
- Le module exige scope `image`, kind `private_key`, SHA256 exact du fichier et suffixe de chemin exact après séparateur `:`.
- Autre path/appcopy, autre hash fichier, digest supplémentaire non connu ou kind `known_probe_secret` restent non classés. Il n'y a pas d'exemption globale vendor.
- La classification conserve le finding initial, file hash, URL/sourcehash/symbole et limites. Elle n'émet pas de verdict produit.
- Le traitement n'est pas une décision de provenance supply-chain complète : il prouve l'identité des octets publics. Les limites documentées reflètent cette distinction.

## Conditions du raccord à contre-vérifier séparément

Le `file_sha256` passé doit provenir des mêmes octets mesurés de la même entrée de couche que le finding, jamais d'un champ déclaré par le produit ou d'une simple correspondance filename. Les observations brutes/classifiées doivent rester présentes dans le reçu. Une classification ne doit pas transformer une observation d'un known probe secret ni faire disparaître un candidat inconnu. Le module isolé ne peut prouver ces propriétés du futur appelant.

Le préfixe avant `:` n'est pas validé par cette fonction ; il appartient à la chaîne de scan fiable qui fabrique et mesure les entrées. Ce n'est pas un P0/P1 dans le scope interne décrit, mais aucune réutilisation sur des findings fournis par un produit non fiable ne serait couverte par cette conclusion.

## Point de traçabilité à corriger

Le champ `independent_review` désigne `REM-15/20261012-public-vendor-material/REVIEW.md`, alors que le rapport livré se trouve dans `workspace/remediation-20261011/vendor-key-review/REVIEW.md`. Avant raccord/livraison, rendre cette référence résoluble vers une copie durable de la revue exacte ou utiliser la référence réelle. Le nom de référence seul n'atteste pas l'existence du rapport.

## Métadonnées package reçues après la revue v2

`workspace/remediation-20261011/vendor-package-native-v2.json` rapporte Debian 12/bookworm/amd64, paquet installé `libgnutls30`, source `gnutls28`, version **3.7.9-2+deb12u5**, bibliothèque 2 197 240 octets, même SHA256 exact `750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3`. Ces métadonnées locales proviennent de dpkgstatus/osrelease/filehash via fixture NETNONE selon le collecteur ; elles établissent ce que déclare le paquet installé et l'identité locale du fichier. Elles ne constituent pas une vérification du binaire contre une archive Debian authentifiée ni une reconstruction reproductible. Cette dernière provenance complète demeure NV, sans remettre en cause l'identité publique des blobs déjà démontrée.

Le nouveau reçu natif incluant DSA est attendu. Aucune conclusion nominale du scanner sur dix candidats n'est encore prononcée par ce document.
