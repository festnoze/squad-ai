# Profils source et entropie observée — remise en REVIEW

Code : `f7bf1889638dd1eb4bde7685b2ca4a1079bade21`, puis `775250a8db78d8630c3f4641f52e78745b58b36b`.

Les valeurs de contrat viennent uniquement des deux documents v0.2. Les recherches, marqueurs et libellés français résolus sont désormais des métadonnées opérationnelles de fixtures revues, pas des attentes ajoutées au brief. Les anciens champs sont rejetés structurellement, également par les fragments de génération.

Le jeton n'est plus qualifié à partir de sa longueur. Le launcher superviseur capture la primitive stdlib avant l'import de `/app`, vérifie l'identité de son symbole et de ses dépendances, laisse l'appel/retour originaux inchangés, puis observe le nombre réel d'octets demandé. Il ne conserve que les empreintes des retours complets et de leurs encodages réversibles. Le cookie HTTP effectivement reçu doit correspondre exactement à une empreinte unique. Une primitive, transformation ou capability non qualifiée reste NOT_VERIFIED, sans adaptation du contrat.

## Interface à raccorder

`InstrumentationBinding` : `entropy_module`, `entropy_attribute`, `entropy_primitive`, optionnels tous ensemble. Primitives instrumentables : `secrets.token_urlsafe`, `secrets.token_hex`, `secrets.token_bytes`, `os.urandom`. Cette liste borne le port d'observation, pas les choix cryptographiques autorisés par le brief.

`await adapter.observe("session_entropy", token_sha256=sha256(cookie.encode("utf-8")))` retourne `token_sha256`, `generator`, `nbytes` entier strict, `default_argument`, `entropy_bits`, `cryptographic`, `encoding`, `proofs`. Le X doit contenir exactement cette observation et les hashes contrat/snapshot. Le R dédié porte `SEC-05:entropy` et confirme, avec citations source, l'appel réel au CSPRNG et la propagation complète jusqu'au cookie. `PRODUCT:bindings` seul ne remplace pas cette revue. Aucun booléen déclaré par le produit n'attribue un PASS.

Instruction de revue à ajouter côté parent : « Pour le symbole d'entropie proposé, identifier la primitive réelle et son argument/default stdlib ; vérifier que l'encodage conserve tous les octets et que le cookie ne tronque/normalise/remplace pas le résultat. N'émettre `SEC-05:entropy` que pour une propagation démontrée sur le snapshot exact. Si la capacité manque, signaler NOT_VERIFIED. »

`FixtureManifest.metadata.browser_probes` contient seulement les données de pilotage revues : `search_a`, `search_b`, `search_a_marker`, `search_b_marker`, `french_action_labels`. Les sélecteurs/routes restent dans les bindings déjà revus. Aucun mot précis d'un bouton n'est ajouté à l'oracle.

Les erreurs DB génériques doivent être contrôlées, JSON, expurgées et no-store ; aucun couple 500/503 n'est imposé hors source. `DB_BUSY` garde son 503 explicite.

## Preuves exécutées

- `20261012-oracle-entropy-unit.xml` : 89 PASS, 12 opt-ins SKIP, 40,15 s, avant activation des essais Linux.
- `20261012-oracle-entropy-linux.xml` : 2 PASS, 41,73 s, vrais appels CSPRNG et cookies HTTP dans Linux NETNONE, Argon2/SQLite réels ; 32 octets nominaux et 16 octets insuffisants distingués.
- `20261012-oracle-entropy-final.xml` : 86 PASS, 121,65 s, périmètre sécurité/profils/entropie avec les deux essais Linux activés et leurs artefacts exportés.
- `20261012-oracle-shape-guards.xml` : 37 PASS, 10,54 s, refus des anciens profils et contre-exemples d'entropie.
- REM-18 `20261012-browser-restart.xml` : 18 PASS, 32,89 s, dont recréation réelle du parent ; l'ancien navigateur connecté est refusé/fermé, le nouveau parent reste vivant et un nouveau harness explicite fonctionne en NETNONE. L'API de lancement Chromium hôte est interdite dans ce contre-test.
- REM-18 `20261012-oracle-browser-counterexamples.xml` : 2 PASS, 5,91 s ; actions anglaises et réponses de recherche inversées restent détectées après déplacement des métadonnées.

Les six fichiers sous `20261012-native-entropy/{32,16}/` conservent les X/R du protocole et les observations exactes ; la preuve de cycle navigateur est sous REM-18 `20261012-browser-restart/receipt.json`. Les `.gitattributes` préservent les octets et leurs hashes sur Windows.

Les essais unitaires de primitive exécutent uniquement du code superviseur constant dans un enfant Python, pas une application générée. Les fixtures navigateur locales sont explicitement de confiance. Toute application observée par le port natif s'exécute dans le runtime Docker détenu. Aucun snapshot historique n'a été réparé et aucun appel LLM payant n'a été effectué.

## Limites et incidents corrigés

Le R des méta-fixtures teste le protocole de preuve : ce n'est pas une revue GPT indépendante d'un futur produit et il ne doit pas être recyclé pour la campagne. L'instrumentation est diagnostique/source-revue, pas une enclave résistante à un processus malveillant. Le confinement Linux repose sur Docker/kernel et ne certifie pas le sandbox interne de Chromium.

Les premières passes ont exposé trois défauts du harnais de test, corrigés avant la passe finale : nom de module dans un contre-test, argument launcher dépassant la borne RuntimeSession de 4096 caractères, appel aux mauvais noms de callbacks d'identité. Le launcher constant est maintenant compressé/segmenté et son SHA256 vérifié avant exécution dans NETNONE, sans agrandir la borne RuntimeSession. Ces changements sont des versions de l'observateur, pas des retries d'un produit historique ni une instabilité occultée.

Le port d'entropie émet ses preuves avant la sonde `cookie_modes` : une capacité de mode HTTPS/HTTP encore absente ne masque pas la mesure native. Cette absence reste NOT_VERIFIED, jamais un PASS. Les champs supplémentaires nécessaires aux campagnes demeurent des bindings source-revus ; le parent conserve le raccord coordinator/source_reviewer/pipeline.

Le candidat de faits source est dans REM-25 `source-facts-v02.json` : trois profils, quatorze ancres verbatim et hashes des deux documents vérifiés, statut REVIEW_REQUIRED. Les 57 exigences sont toujours les lignes exactes du référentiel. Ce checkpoint ne prétend pas rendre une livraison CONFORME.
