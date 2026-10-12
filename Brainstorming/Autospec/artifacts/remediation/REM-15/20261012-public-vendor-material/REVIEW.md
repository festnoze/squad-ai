# Revue indépendante des candidats PEM vendor — 2026-10-12

## Conclusion bornée

La matérialité publique des **neuf blocs** observés dans le reçu natif v2 est démontrée : leurs SHA256 correspondent exactement, un par un, aux constantes publiées dans le source officiel GnuTLS **3.7.9**, fichier `lib/crypto-selftests-pk.c`. Ce ne sont pas simplement des marqueurs ressemblants : les neuf empreintes portent sur les blocs complets BEGIN→END, base64 comprise. Les constantes sont utilisées comme vecteurs de self-test par `gnutls_pk_self_test` et les appels `PK_KNOWN_TEST`/tests GOST du même fichier.

Cette conclusion qualifie uniquement ces octets publics et leur contexte source de self-test. Elle ne prononce **aucun PASS SEC01 produit**, ne crée aucune R, n'exempte aucun fournisseur et ne démontre ni l'absence universelle de secrets ni l'intégrité supply-chain de toute la bibliothèque. L'utilisation éventuelle d'un de ces vecteurs publics comme credential applicatif serait une autre observation de sécurité ; ce rapport ne l'autorise pas.

La provenance complète **paquet exact→binaire exact** reste **NV** à ce stade. Le nom `libgnutls.so.30.34.3` n'est pas une preuve de version de paquet. La page Debian confirme seulement que ce chemin est livré par libgnutls30/bookworm/amd64 ; la page courante indique 3.7.9-2+deb12u7, et ne peut établir la version de l'image locale. Cette limite est distincte de la correspondance publique 9/9 démontrée.

## Périmètre et preuves locales

Revue read-only des reçus expurgés de fixture autorisée ; aucune exécution du produit, aucune connexion DB/auth réelle, aucun socket Docker applicatif, aucun upload de clef. Le seul téléchargement supplémentaire est un source public officiel, traité en mémoire et jamais sauvegardé avec son contenu de clefs. Les artefacts ne contiennent que hashes, noms de symboles, chemins et métadonnées non secrètes.

- Image scannée : `sha256:4dd335430e51fbac05c18b894d2224bf99c01672d494cebb43c18a6ca95eeeb0`.
- Archive scannée SHA256 : `0331a53b837161ee48233a1d8b44c6d3e7fa15ef851dbb21f78ca95b72ad4703`.
- Couche : `e48af84b2108a5d73effd9e16685b42ac33e7994e606398c46690918f5f3604a`.
- Fichier : `usr/lib/x86_64-linux-gnu/libgnutls.so.30.34.3`.
- SHA256 fichier : `750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3`.
- Reçu v2 SHA256 : `e448d8bca43fbddfda669534d24965043f0c071cbff7aa97b56831448ad03f25`.
- Le reçu distingue image scannée et image runtime ; ce rapport ne les confond pas.

Le détail des neuf correspondances, hashes complets et provenance du reçu se trouve dans `native-v2-public-matches.json` ; l'inventaire des dix constantes publiques source se trouve dans `upstream-3.7.9-hashes.json`.

## Sources primaires et reproductibilité

[Source officiel GnuTLS 3.7.9](https://raw.githubusercontent.com/gnutls/gnutls/3.7.9/lib/crypto-selftests-pk.c), [miroir officiel](https://github.com/gnutls/gnutls), [règle de compilation](https://raw.githubusercontent.com/gnutls/gnutls/3.7.9/lib/Makefile.am), [référence du tag](https://api.github.com/repos/gnutls/gnutls/git/ref/tags/3.7.9).

- Tag objet : `f3bf619b30950f79b0a9c92df8959a8140f0384b`.
- Commit cible : `ca61668d7764fc29fb4cc2aa396cb035e176636d`.
- SHA256 source récupéré en UTF8 : `c3d79122e072177f55dc30a98f68b949c0f36f6159a363aae9512a22a9280ed0`.
- [URL source épinglée au commit](https://raw.githubusercontent.com/gnutls/gnutls/ca61668d7764fc29fb4cc2aa396cb035e176636d/lib/crypto-selftests-pk.c).
- [Liste Debian du paquet](https://packages.debian.org/bookworm/amd64/libgnutls30/filelist), [détails Debian courants](https://packages.debian.org/bookworm/libgnutls30).

Le script `hash-public-source.ps1` reconstitue uniquement les constantes C publiques, décode les séquences LF puis calcule SHA256. Convention de comparaison scanner : octets ASCII du bloc du premier tiret BEGIN au dernier tiret END, **sans LF terminal**. Les sauts de ligne intérieurs restent inchangés. Le JSON conserve aussi le hash source-C avec LF terminal éventuel et le hash des octets DER décodés. Aucune comparaison normalisée approximative n'a été utilisée : la variante sans LF terminal correspond exactement aux neuf SHA256 des reçus.

## Correspondances

| Constante publique | Résultat SHA256 bloc v2 |
| --- | --- |
| rsa_2048_privkey | EXACT |
| ecdsa_secp192r1_privkey | EXACT |
| ecdsa_secp224r1_privkey | EXACT |
| ecdsa_secp256r1_privkey | EXACT |
| ecdsa_secp384r1_privkey | EXACT |
| ecdsa_secp521r1_privkey | EXACT |
| gost01_privkey | EXACT |
| gost12_256_privkey | EXACT |
| gost12_512_privkey | EXACT |

Le source contient aussi `dsa_2048_privkey` : dix constantes et non neuf. Le détecteur v2 annoncé ne reconnaît pas DSA PRIVATE KEY ; l'absence de DSA du reçu ne prouve donc pas son absence binaire. Le hash source public du bloc DSA sans LF terminal est `7c4c63ee462e0e700cd9e29c8e0f730b3f1b484c4abdd83f1e69fcd477c061fa`. Tout nouveau reçu incluant DSA doit être revu explicitement et ne doit pas hériter silencieusement de cette revue v2.

## Limites et décision séparée

La comparaison est indépendante du nom vendor : elle lie neuf valeurs précises au source officiel publié. Elle ne certifie pas mathématiquement toutes les clefs ; la preuve de publicité repose sur l'identité SHA256 complète, pas sur la validité cryptographique. Le décodage base64/DER-shaped du scanner n'est pas une preuve de secret réel.

Si une classification future est retenue, elle doit rester bornée au scope image, chemin exact, SHA256 fichier exact et ensemble exact des hashes revus, conserver chaque candidat classé avec ses références et rester fail-closed pour nouveaux bytes, candidats supplémentaires, autre chemin/app ou secret de contrôle. Cela ne remplace pas la R source/image indépendante exigée par SEC01. Aucune classification, whitelist ou waiver n'est implémentée par cette revue.
