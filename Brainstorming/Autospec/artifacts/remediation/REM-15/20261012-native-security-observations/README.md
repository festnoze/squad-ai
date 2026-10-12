# Collecteurs natifs SEC-01 / SEC-05 / SEC-15

Code : `ed51575e077d2f4bb8e52a3f4210db39a2017d62`, puis correctif ciblé
`b638e381ced3e7e84c4c5508e2f4184676aa5c1c`. Source basée sur73eef96a ;
aucun edit pipeline/source_reviewer/manifests/tableau/snapshot historique.
La classification publique vendor du parent n'est PAS incluse dans ces commits.

## Décision / faits

Raccords fonctionnels disponibles : `EvidenceAdapter.observe` appelle le port
natif aux points exacts SEC-01/05/15, publie ses X et l'observation obtenue,
sans réutiliser une narration externe. SEC-15 collecte après ses parcours
négatifs ; l'image de SEC-01 vient du reçu delivery_build qualifié pour le
snapshot exact, pas de l'image de dépendances montée sous le runtime.

- Final natif v4 : **30 PASS / 179,13 s**, aucun SKIP. HTTP/TLS/SQLite/Argon2,
  Docker NETNONE et image réellement exécutés ; aucun nominal mocké.
- Unités finales v5 + ports existants : **46 PASS / 16 SKIP / 6,06 s**.
  Ces opt-in non exécutés restent des SKIP, pas des PASS natifs.
- Les 3 conditions de cookie donnent Secure true / false / true pour la
  fixture nominale, avec TLSv1.3 réel en HTTPS ; le défaut insecure-production
  est observé false / false / false. Trois containers/DB distincts par essai,
  même source et image. Cookie/CSRF bruts restent en mémoire privée seulement,
  supprimés du payload avant preuve ; seuls attributs/SHA sont persistés.
- La fuite propre aux modes prod est retrouvée après fermeture des children :
  capture complète de leurs logs/outputs avant close, puis scan dynamique.
  La borne4MiB dépassée donne AdapterUnavailable/NV, jamais scan vide.
- Le secret de la première ligne suivi de130 lignes est retrouvé par logs
  complets ; l'ancien tail100 ne le voit plus. Les réponses négatives sont
  scannées en mémoire avant expurgation, sans conserver leur secret brut.
- L'image réelle contient **10 blocs PEM** dans libgnutls : le reçu RAW reste
  passed=False/findings non vides. Le métatest PASS prouve cette détection,
  PAS une image clean ni l'admission SEC-01. Une contre-image COPY vendor/cache
  avec secret fictif connu + bloc PEM structuré reste également FAIL.

Les replays rouges sont conservés : v1 18PASS/2FAIL (racine artefacts absente,
heuristiques trop larges) ; v2 19PASS/2FAIL (root-dot broker, image réellement
porteuse de PEM) ; v3 24PASS/1FAIL (contre-image FROM ID interprété comme nom
registry). Le rawv3 ne contient que6PEM : la régression LF obligatoire a perdu
quatre EC et a été corrigée, pas maquillée par changement de seuil. La preuve
finale vérifie les dix hashes du source officiel3.7.9, LF terminal exclu.

## Port stable / raccord parent

`ReviewedProductBindings.security_observations` est nullable, source-scellé :

```text
cookie_name, fixture_case, actor, app_module, app_attribute
modes = {https, http_local_explicit, http_without_exception}
  -> {environment: dict[str,str], tls: bool}
artifact_roots: array[str] relative à l'evidence_root possédé
```

Env exact source-revu : valeurs non secrètes bornées ; pas PATH/DB/APP_ORIGIN,
credentials, clés API ou injection de processus. Le parent possède l'ajout du
champ obligatoire nullable au schema proposition et le module
`validation/security_observations.py` dans le paquet `_protocol` de revue.
La structure est vérifiée par SecurityObservationBindings ; un ancien port
absent doit être explicitement null dans les propositions nouvelles.

`ProductHarness.collect_security_observation(name, scope=None, image_id=None)`
retourne `(value, list[Proof X])`. Port exposé à l'adapter superviseur via
`native_security_observation`. `RuntimeSession.capture_security_logs` lit tous
les logs de l'ID owned courant, byte/time-bound ; `scan_security_image` exporte
l'ID immuable source-labelled vers un temporaire possédé, lit config+toutes
layers/fichiers réguliers sans extraction ni suivi de lien, puis supprime
l'archive. Receipts listent chaque scope/fichier/SHA et provenance image/logs.

OpenSSL génère clé/cert TLS uniquement dans /tmp du child NETNONE, avant import
produit Linux. La requête vérifie le cert local et relève la vraie version TLS.
Ce launcher ASGI ciblé vérifie la configuration cookie, pas le CMD de livraison.
Un mode ne produisant pas de header/login exploitable reste NV, pas Secure=True
inventé ; notamment un refus HTTP sans exception n'est pas déclaré défaut produit.

## Limites / sécurité

Détecteurs : secrets fictifs connus déjà fournis/générés en mémoire sur TOUS
octets/layers ; PEM complet base64/DER-shaped, y compris sans LF et traversant
65536-byte chunks (body32768, carry33536). Assignment/Argon2 heuristiques sont
limitées source/application/logs/artifacts, comme explicitement approuvé. Ce
n'est PAS l'absence universelle de secrets inconnus dans vendors. Les PEM de
vendors ne sont jamais ignorés par lieu/message d'exemple ; aucune whitelist.

La lecture DB supplémentaire de password_hash a été refusée par auto-review :
NON effectuée/contournée. Ce collecteur ne l'ajoute pas ; les ports DB antérieurs
du harnais restent hors cette extension. Les scans de /tmp/certs éphémères,
credentials réels et autres projets sont exclus. Aucune clé PEM brute/DB/source
produit n'est copiée ici : seulement reçus X expurgés, logs de tests et metadata
public package. Aucun provider/auth Claude/inférence/génération ; coût réel de
génération de cette validation = zéro.

X ne crée aucune R. SEC exige encore ses revues indépendantes exactes ; le
parent traite séparément la classification publique des dix vecteurs. Aucun
PASS produit57/56 ni permission de lancer la campagne n'est déduit de ces tests.

## Reproduction et inventaire vendor

Depuis backend, Python verrouillé factory-env, opt-in
AUTOSPEC_REAL_SECURITY_OBSERVATIONS=1, AUTOSPEC_REAL_PRODUCT_HARNESS=0 :
`python -m pytest tests/test_security_observations_native.py -q --tb=short`.
Basetemp original workspace/remediation-20261011/security-observations-native-v4.
Le replay unité utilise flag0 et ajoute test_product_harness.py/test_runtime_session.py.

RAW10 : native-v4/test_real_image_layer_scan_exa0/harness/evidence/
security-scan-4b9a5a49706641188b0b86db66322800.json ; SHA256
`bff3f8c1119b865558fb1b64e557df21d512420d52ed21354eb4d37b9e9f3f67`.

Image : `sha256:d6746b0247761f16cdf0126a2773caa965405a4f9f883d3315f2004d54cceaeb` ;
snapshot fixture : `25fba877a1e9042dcde148a3f7f8308881bd1799aa835737432f2bbc84ac62d5`.
Debian12/bookworm amd64, libgnutls30/source gnutls28 version3.7.9-2+deb12u5.
Fichier `/usr/lib/x86_64-linux-gnu/libgnutls.so.30.34.3`,2197240bytes, SHA256
`750be5c0ce95061563e1561019e382823eb1e011ffe7980e9e005eeafd82efa3`.
Le reçu RAW contient les dix SHA PEM/DER, offsets, longueurs et types, aucun
contenu PEM. vendor-package-native-v4.json atteste package/OS/fichier sur CET
image par script constant -I NETNONE (sans import produit ni credential).
