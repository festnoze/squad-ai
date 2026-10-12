# Addendum v4 — 2026-10-12

## Conclusion indépendante bornée

La régression P1 des quatre vecteurs EC inline/non canoniques identifiée au v3 est **corrigée à lecture source et fermée pour le scénario natif brut v4 vérifié** : dix candidats, dix hashes PEM exacts et dix hashes DER exacts correspondent au source public officiel épinglé. DSA est présent. Le contrôle image négatif conserve les deux candidats supplémentaires non publics, sans confusion avec les dix vecteurs connus.

Cette fermeture concerne le détecteur borné et les fixtures décrites, pas une qualification SEC01 d'un produit. Elle ne démontre pas l'absence universelle de secrets ni une R source/image produit. Le replay final avec classification raccordée a ensuite été lu et vérifié ci-dessous ; sa partition des candidats est conforme dans les deux fixtures.

## Source et correctif

Source public : commit GnuTLS `ca61668d7764fc29fb4cc2aa396cb035e176636d`, [fichier épinglé](https://raw.githubusercontent.com/gnutls/gnutls/ca61668d7764fc29fb4cc2aa396cb035e176636d/lib/crypto-selftests-pk.c), SHA256 UTF8 `c3d79122e072177f55dc30a98f68b949c0f36f6159a363aae9512a22a9280ed0`.

`security_observations.py` corrigé lu SHA256 `7920adf893c929cd3fb4404148d02fbd7f38137cd5a553ac7c2cc109fc843580`. La regex accepte désormais 0..128 octets whitespace de part et d'autre du corps au lieu des deux LF obligatoires, tout en exigeant wrappers complets identiques, corps borné base64 décodable et forme DER/OpenSSH. `_carry=33536` couvre 32768 octets de corps + 256 espaces maximum + wrappers ; ceci couvre la limite du pattern, contrairement à l'ancien carry33000.

Les tests source de frontières ont été lus : starts65520/32767, corps maximal32768, cas separators vide/espace/CRLF/128espaces, marker-only négatif. XML natif v4 constaté : 30 tests, 0 failure, 0 error, 0 skip, 179.103s. SHA256 XML `939cf1bd0105d5019f7b3ac112337f3ec192ab1b14900a6edbc51ce8b231b565`. L'exécution est celle du collecteur ; cette contre-revue a lu les preuves et n'a exécuté aucun produit.

## Preuve brute nominale v4

Reçu : `workspace/remediation-20261011/security-observations-native-v4/test_real_image_layer_scan_exa0/harness/evidence/security-scan-4b9a5a49706641188b0b86db66322800.json`.

- SHA256 reçu `bff3f8c1119b865558fb1b64e557df21d512420d52ed21354eb4d37b9e9f3f67`.
- Image scannée `sha256:d6746b0247761f16cdf0126a2773caa965405a4f9f883d3315f2004d54cceaeb`.
- Archive SHA256 `90a673134d1035e5dfc4625bad4215445d2a16d8caa0bc43ce030aa33bef0604`.
- Snapshot source `25fba877a1e9042dcde148a3f7f8308881bd1799aa835737432f2bbc84ac62d5`.
- Bibliothèque SHA256 inchangé `750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3`.
- Dix findings bruts `private_key` conservés, offsets/tailles/types présents ; les dix SHA256 PEM sans LF terminal et DER correspondent exactement à l'inventaire upstream de cette revue.

Le reçu est pré-classification : aucune liste public_non_credentials/detector_candidates et aucune conclusion secret-free à en tirer. Le collecteur indique preuve brute FAIL avec les dix candidats retenus ; la matérialité publique est établie séparément ici.

## Preuve brute image négative v4

Reçu : même dossier, `security-scan-386ead846e874807bfdc8869a33d4dad.json`.

- SHA256 reçu `df64550baaed601166dd6d622b5c5c93477855fa742c1e30f83d25121bfa5d12`.
- Image négative `sha256:ef68a96e73ae77eaaa4001776c2855dc721d63047f3f71afa8ddff0d4a923d98`.
- Douze findings : dix mêmes vecteurs publics exacts plus un `known_probe_secret` SHA256 `4e111b6c133aca797d58a858280b06d98a8e954f47ad7a8715a9159ec8edbf44` et un bloc RSA fictif inconnu SHA256 `a5f89664efa2894fde61a6feba27e1fd632a6a050d286c492886aa5c0a71c584` (DER `25242f688ccf9ab20d60751ab2435449f4b48b959e6d85b7c7a0f2aae96e63d5`) dans `opt/vendor/cache/native-canary`.
- Ces deux candidats supplémentaires ne correspondent pas aux hashes publics et restent explicitement observés, même hors `/app`.

Le détail expurgé des deux reçus et des correspondances se trouve dans `native-v4-public-matches.json`. Aucune vraie valeur de clef ni credential n'y figure.

## Limites conservées

Aucune whitelist vendor générale, aucune exemption applicative, aucun PASS SEC01 produit et aucune R fabriquée. Provenance complète du binaire contre paquet Debian authentifié non revendiquée. Rapport v3 conservé pour historique ; sa limite six candidats est supersédée uniquement par les preuves v4 et replay final ici.

## Replay final avec classification raccordée

XML `workspace/remediation-20261011/root-security-native-final-v1.xml` lu : **30 tests, zéro failure/error/skip**, 245.137s ; SHA256 `b9a67a5bf9948351137cca44079f17673a4af662e73cf3d0e0af5d4d088b4f4f`. Ces tests de fixture ne sont pas une acceptation produit.

Reçus dans `root-security-native-final-v1/test_real_image_layer_scan_exa0/harness/evidence/` :

- Nominal `security-scan-d1df81d82b5745f1839b38aa128e508e.json`, SHA256 `077ea3d0848d67f46f705d68701646dbe519a6972f0120596b717adbc2905a24` : dix `detector_candidates`, dix `public_non_credentials`, zéro `findings`. Image `sha256:d6746b0247761f16cdf0126a2773caa965405a4f9f883d3315f2004d54cceaeb`, même archive nominale que le v4 brut.
- Négatif `security-scan-572ac18b6633491080b863a63f286605.json`, SHA256 `16e3182247828e557002ccf5aaa72e464d045a2fba9eedbdd8f3bf7996bf3310` : douze `detector_candidates`, dix publics classés et **deux findings résiduels** (known_probe_secret + RSA fictive inconnue, hashes ci-dessus). Image `sha256:a8100195ab762a3858cac2419f1666fcd89d0e015ad4f7d5edf6281591da356c`, archive SHA256 `e36be88771d498f1f71d46a17ff8247d158a3366f7f056b0a5e686539fa5fee7`.

Pour chacun : scopes source/image/logs, complete=true, unique entrée inventaire libgnutls mesurée, même SHA256 fichier exact. Contre-vérification indépendante de chaque classe : symbole correct, hash PEM exact, hash DER exact, hash fichier égal à l'inventaire, URL source commit épinglé, hash source exact. Chaque candidat original est conservé dans la partition publics+findings avec scope/path/type/hash/offset/longueur/DER inchangés. Aucune observation brute perdue. La preuve négative reste négative après classification : deux candidats non publics ne sont pas absorbés.

Sous-inventaires expurgés et résultats de vérification : `final-classifier-replay-matches.json`. Aucun contenu PEM/credential sauvegardé. La référence `REM-15/20261012-public-vendor-material/REVIEW.md` est désormais présente dans `artifacts/remediation/` du worktree integration, clôturant le point de référence manquante de la première contre-revue.

**Conclusion de contre-revue finale dans ce scope : aucun P0/P1 restant identifié dans le correctif inline/carry ni dans le raccord borné de classification et de conservation des candidats vérifié par ces fixtures.** Le verdict nominal X de la fixture ne remplace toujours pas R/SEC01 d'un produit généré ni une revue générale supply-chain.
