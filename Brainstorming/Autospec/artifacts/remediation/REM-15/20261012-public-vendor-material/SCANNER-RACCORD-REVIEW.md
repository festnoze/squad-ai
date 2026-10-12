# Raccord scanner — revue intermédiaire 2026-10-12

## Résultat

Pas de P0/P1 identifié dans le raccord de classification lui-même. **P1 scanner identifié et signalé au parent : régression des quatre vecteurs EC inline/non canoniques**, empêchant une conclusion nominale dix candidats à cet état. Le parent doit corriger et rejouer avant conclusion.

SHA256 `security_observations.py` lu : `549dbdb55d04d1344cbff49d8bd52b247afeaf2354cda8578ce9d003c4c96060`.

## Raccord lu

`scan()` calcule SHA256 par incréments sur l'ensemble des octets du même stream que les candidats, puis ajoute l'entrée inventaire `(scope,file,sha256)`. `scan_image()` lie le config digest à l'image ID demandée et balaie chaque fichier régulier de chaque couche sans extraction ni suivi de liens host.

`receipt()` indexe l'inventaire par `(scope,file)` et ne classifie que lorsqu'une **unique** entrée mesurée existe. Hash absent, hash modifié ou plusieurs entrées restent finding. Le classificateur exige ensuite scope image/type private_key/path précis/hash fichier précis/hash bloc précis. Known probe secret jamais classé. Le reçu sérialise inventaire, candidats originaux, candidats publics classés et findings résiduels ; le hash de preuve porte sur ces octets sérialisés. Le verdict X `passed=not findings` n'est pas une R produit et ne remplace pas la revue SEC01 obligatoire.

Tests source lus : cas hash absent/modifié/ambigu, appcopy et known_probe_secret ; leur exécution 141 PASS / 16 SKIP est rapportée par le parent, non réexécutée dans cette revue read-only. Aucun produit exécuté ici.

## Observation native brute v3

Reçu exact : `workspace/remediation-20261011/security-observations-native-v3/test_real_image_layer_scan_exa0/harness/evidence/security-scan-e84e4a7aacca4834b3f52e1f3b1341ef.json`.

SHA256 reçu : `f817635a02f3fd75e54434156b4da0dcf93beb81bccc1f79d80b36bff8eec43b`. Il contient **six** findings, non dix ; ni `detector_candidates` ni `public_non_credentials`, car observation brute pré-raccord. Image/archive/fichier restent identiques au v2.

Les six hashes PEM **et DER** correspondent exactement à RSA, DSA, EC256 et GOST01/GOST12-256/GOST12-512 du source public épinglé. Les quatre vecteurs EC192/EC224/EC384/EC521 auparavant observés au v2 ont disparu. Détails hashes/offsets dans `native-v3-interim-six.json`.

La regex courante exige un newline après BEGIN et avant END. Reproduction sur source public officiel au commit épinglé : ces quatre constantes ont `newline_after_begin=false` et `newline_before_end=false`, les six autres ont les deux vrais. Cause confirmée : exclusion des blocs inline complets par les deux séparateurs obligatoires, et non disparition du binaire ni nouveauté de provenance. Tout matériel inconnu ayant le même encodage inline pourrait aussi être omis, ce qui contredit le scan annoncé des blocs complets sur tous les octets. Le marqueur seul doit continuer à être rejeté ; rétablir les blocs complets base64/DER-shaped ne doit pas devenir un marker-only scan.

## Limites ouvertes

Nominal dix candidats et raccord natif final : **NV**, en attente de reçu rejoué après correction. Référence `independent_review` du module isolé toujours à rendre résoluble vers la revue livrée. Qualification de provenance complète paquet→binaire toujours non revendiquée. Aucun PASS SEC01 produit ni R fabriquée.
