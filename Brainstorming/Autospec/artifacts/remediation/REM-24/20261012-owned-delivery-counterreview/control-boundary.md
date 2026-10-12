# Garde Origin/Host du contrôleur usine

Base exacte : `88b79de1`. Code : `c3e146eb`, puis durcissements de configuration `26644333` et `ffc8e5ca`, contenant `api/control_boundary.py`, raccord `server.py`, tests dédiés et migration mécanique de 25 URL dans 18 fichiers de tests qui utilisent `server.app`. Aucun changement de fixture produit, pipeline, oracle, snapshot historique, manifest ou dépendance. Aucune génération ni facture LLM.

## Résultats

- Avant : `foreign-origin-before.xml`, **3 FAIL / 0,75 s**. Trois POST simples Origin produit/tiers/null atteignent un callback inerte, alors que CORS masque seulement leur réponse.
- `control-boundary-v1.xml` : **74 FAIL / 17 PASS**, 2,41 s. L'argument de test extérieur déplace la sélection du fichier de configuration pytest ; les 74 fonctions async ne sont pas exécutées. Ce run est une erreur de lancement, pas 74 bugs de sécurité. Le replay impose `-c pyproject.toml`, sans supprimer d'assertion.
- `control-boundary-v2.xml` : **91 PASS / 1,25 s**, rc0, dont les trois contre-tests extérieurs initialement rouges. HTTP ASGI, Host/DNS-rebinding/peer/headers dupliqués, Origin exact, configuration stricte, OPTIONS explicite et frontière WebSocket.
- `control-boundary-native-v3.xml` : **89 PASS / 1,25 s**, rc0. Inclut un vrai listener IPv4 loopback déjà lié avant démarrage d'Uvicorn et le vrai endpoint usine `/undeploy`, avec callback pipeline **inerte**. Les origines CLI, GUI servie same-origin et proxy dev exact passent ; produit/null/Host DNS-rebinding et GET sans Origin sont refusés avant callback. Préflight réel retourne l'origine exacte. Listener/thread arrêtés et port re-lié par une socket possédée après cleanup. Deux avertissements websockets de dépréciation sont conservés.
- `factory-control-native.json` : observations TCP réelles, statut et delta du callback, hashes du code réellement chargé, port possédé et cleanup. Pas de cookie, DB, mot de passe, action Docker ni JS produit exporté. Les en-têtes des deux modes GUI sont réellement transportés ; **aucun nouveau E2E visuel React n'est revendiqué**.
- `control-api-regression-v1.xml` : **418 PASS / 363,91 s**, rc0. Tous les modules API usine migrés, guards, workflow, provider scripté, claims/contrat, delivery, lifecycle, gouvernance, monitor et actions. Pas de test produit hôte. Les assertions/deadlines existantes ne sont pas réduites.
- `all-counterproofs-control-v4.xml` : **13 PASS / 2,75 s**, rc0. Les quatre familles de contre-exemples indépendants passent avec les vraies gardes et les seuls effets remplacés.
- Dernier code `ffc8e5ca` : `control-boundary-all-final-v5.xml`, **104 PASS / 2,48 s**, rc0. Deux assertions supplémentaires bornent l'autorité configurée sans port au port effectif du serveur et refusent un peer distant malgré configuration d'un nom loopback. Le grand replay 418 PASS porte sur `c3e146eb`, avant ces deux restrictions plus étroites ; il n'est pas réétiqueté comme exécuté sur le dernier code.
- `control-tcp-final-v6.xml` et `factory-control-native.json` sont la preuve fraîche du code final ; `factory-control-native-v4.json` conserve le précédent reçu TCP brut. Le reçu v3 initial utilisait le même nom et avait été remplacé par v4 avant versionnage : son JUnit reste conservé, mais aucun ancien JSON v3 n'est reconstruit ni prétendu présent.

Commandes depuis le backend du worktree, Python factory verrouillé :

`python -m pytest -c pyproject.toml -p no:cacheprovider -q tests/test_factory_control_boundary.py`

Le replay API vise explicitement les 18 modules migrés plus cette garde. Pour conserver le JSON TCP, définir `AUTOSPEC_CONTROL_PROOF_ROOT` sur le répertoire superviseur de preuves. Les JUnit et JSON sont conservés sans conversion Git (`-text`).

## Politique et configuration

La middleware contrôle HTTP **avant le routage**, pour GET aussi bien que mutations et OPTIONS ; WebSocket suit la même autorité et ferme à 1008 sur refus. Aucun Host `test/testserver`, bypass ASGI, header forwarded implicite ou wildcard CORS. Les duplications Host/Origin ne sont pas écrasées. Les erreurs n'échoent aucune valeur hostile.

Par défaut, seuls peer et autorités loopback attestés sont admis. L'origine du GUI servi est le triplet scheme/host/port exact du serveur. Les seuls défauts dev approuvés sont `http://localhost:5183` et `http://127.0.0.1:5183`. Vite conserve Host:5183 vers son upstream ; cette exception de port est liée exclusivement à une origine GUI explicitement approuvée, pas à tout localhost arbitraire. Un Host distant est refusé même si Origin est absent ; un peer distant ne peut se présenter avec un Host loopback sans ouverture configurée.

Deux variables publiques de configuration, lues dans l'environnement **de l'usine** uniquement :

- `AUTOSPEC_CONTROL_ORIGINS` : tableau JSON de 32 origines canoniques uniques maximum, sans path, query, fragment, userinfo ou wildcard. Remplace les défauts dev ; `[]` désactive ces défauts, en conservant le GUI servi same-origin loopback.
- `AUTOSPEC_CONTROL_HOSTS` : tableau JSON de 32 autorités littérales canoniques uniques maximum. Une ouverture LAN/custom-host doit être explicite ; un nom sans port exige toujours le port effectif du serveur, un port spécifié borne cette autorité de proxy explicitement approuvée. Une origine de GUI custom doit être configurée **séparément** : une autorité custom seule n'auto-approuve pas son Origin.

Origine absente reste autorisée pour les clients CLI locaux après validation de l'autorité et du peer. Configurer un nom loopback ne permet jamais un peer distant qui forgerait ce Host. Sur une autorité non-loopback **explicitement** ouverte, un client CLI peut également envoyer sans Origin : la configuration exprime alors la décision de l'opérateur. Ce mécanisme n'est donc pas une authentification, une politique de sécurité multi-utilisateur/LAN ou une protection contre un processus hôte hostile. L'API de fabrique reste locale par défaut.

CORS est instancié par requête avec l'unique origine déjà admise, verbes explicites et headers Content-Type/Last-Event-ID ; jamais `*`. Préflight étranger ou header/verbe inconnu ne donne aucun effet. Le GUI dev qui tomberait automatiquement sur 5184 doit être configuré explicitement ou revenir au port approuvé, pas bénéficier d'une ouverture silencieuse.

## Limites et raccord

Le parent doit cherry-pick le commit code puis ce paquet brut et rejouer ses tests communs, dont les E2E du GUI. La nouvelle garde ferme le chemin page produit → mutations du contrôleur ; elle ne qualifie aucun critère du produit et ne remplace ni la frontière Docker ni ses sondes. Les trois P1 de lifecycle déjà corrigés restent confirmés sur `88b79de1`. REM-03 opérations effectives et globale finale restent des preuves séparées ; REM-24/25 ne sont pas libérés par les seuls 418 PASS.
