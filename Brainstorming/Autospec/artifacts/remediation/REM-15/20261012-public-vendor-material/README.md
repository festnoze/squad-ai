# Scan natif et classification de vecteurs publics

Les détecteurs restent actifs sur l'ensemble des bytes/layers. La classification n'est autorisée que pour le type `private_key`, dans l'image, au chemin exact `usr/lib/x86_64-linux-gnu/libgnutls.so.30.34.3`, avec son SHA256 réel exact `750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3` et l'une des dix empreintes PEM indépendamment reliées aux sources publiques GnuTLS 3.7.9. Toute ambiguïté d'inventaire, copie applicative, autre fichier/image modifiée ou secret fictif connu reste un finding. Les candidats bruts et les classifications demeurent dans le reçu.

Source primaire : [GnuTLS, commit ca61668d7764fc29fb4cc2aa396cb035e176636d](https://github.com/gnutls/gnutls/blob/ca61668d7764fc29fb4cc2aa396cb035e176636d/lib/crypto-selftests-pk.c). SHA du fichier source public : `c3d79122e072177f55dc30a98f68b949c0f36f6159a363aae9512a22a9280ed0`. Aucun contenu de clé/credential n'est conservé dans les rapports, seulement les empreintes, symboles et faits de provenance.

## Reçus ciblés

- `public-crypto-scope-v1.xml` : 21 PASS pour les dix empreintes et les refus de périmètre ; métatests typés, pas scan réel.
- `root-security-raccord-unit-v1.xml` : 141 PASS, 16 SKIP opt-ins en 8,44 s ; raccord natif et classification, harness, coordinator, reviewer et joins.
- `root-security-proposal-v2.xml` : 74 PASS, 1 FAIL, 2 SKIP en 3,80 s. Le nouveau cas avec observations cookie et `auth_required=False` est correctement refusé par ValueError avant le contrôle oracle ; la fixture attendait l'autre refus AdapterUnavailable.
- `root-security-proposal-v3.xml` : 75 PASS, 2 SKIP en 3,56 s après correction du type d'erreur attendu dans le test, sans changement de production. Inclut NULL explicite / modes observés, altération de cookie invalidant R et absence d'un mode refusée.

Le reçu brut v3 a montré une régression de regex omettant quatre PEM inline complets. Il est conservé et ne vaut ni nominal dix candidats, ni PASS SEC-01. Correction intégrée `7b1ea54c` (auteur b638e381) : reconnaissance de PEM complets inline, carry33536, logs/CSRF/cookies privés des trois modes capturés avant fermeture, débordement ou logs manquants NV.

Replays distincts : auteur brut v4 **30 PASS en 179,103 s** (REM-15/20261012-native-security-observations) ; parent avec classification exacte **30 PASS en 245,137 s** (REM-15/20261012-parent-native-security). Les dix candidats source-exacts restent présents. Le négatif garde deux findings inconnus (secret fictif et PEM fictif). Addendum indépendant vérifie la partition complète et les dix empreintes PEM/DER, sans R/PASS SEC-01 produit. Parent unités intégrées : **100 PASS, 7 SKIP en 3,86 s**, dont refus d’un scan ancien externe, absence/corruption de binding et invariants de revue.

## Limites

L'identité de ces données publiques est prouvée, pas toute la chaîne package → binaire. Ce mécanisme n'approuve ni une dépendance ni l'utilisation de clés publiques d'auto-test comme credentials de l'application. La R source/image reste obligatoire ; X typé ou scan isolé ne vaut jamais R. Les heuristiques ne découvrent pas universellement les secrets inconnus ; scope absent ou bornes dépassées produit NV, jamais scan vide réputé complet.
