# ARC-06 — contribution navigateur native

Code `4855f299` : `validation/architecture_browser.py`, uniquement le collecteur et ses métatests. Code `acb014e6` : un nominal Docker et sa fixture constante. Base synchronisée `73eef96a`. Aucun pipeline, coordinator, source_reviewer, product_harness, oracle ni produit historique modifié.

`await collect_architecture_client(contract, harness, snapshot_hash)` observe une connexion UI réelle, un GET `/api/auth/me` initié par le frontend lors d'une nouvelle navigation et la consommation de son `display_name`, avec vérification de l'ID de l'acteur fixture. Une navigation vers un UUID absent provoque ensuite le vrai GET `/api/tickets/<uuid>` et son 404 JSON `{error:{code,message}}`. La présentation frontend est comparée au message reçu ou à un mapping code→texte opérationnel indépendamment revu. Il n'y a aucun `route.fulfill`, réponse synthétique, session injectée ni substitution d'auth.

Les attentes restent le texte ARC-06 source-exact. Les commandes/sélecteurs/pointers ne sont pas des facts normatifs. Les observations, demandes réseau, hashes des corps JSON sans contenu d'auth, screenshots expurgés, fingerprint de fixture et SHA du collecteur figurent dans les X/V. Snapshot/oracle et fixture/acteurs sont recontrôlés avant/après. Chaque attente réseau/navigation est bornée à 15 s ; la limite globale de l'observateur est 60 s, pas un nouveau seuil éliminatoire du brief.

## Interface et raccord parent

- Locator opérationnel nouveau `browser_bindings.current_user_name`, plus les bindings existants email/password/login/ticket_nav/error et routes home/ticket.
- `metadata.browser_probes.architecture_client.identity_pointer` : `/display_name` ou `/user/display_name`, explicitement revu selon le DTO réel.
- `error_presentation` : `server_message` ou `code_mapping`. Le second exige `error_messages={code:texte}` source-revu. Aucun libellé arbitraire n'est ajouté au contrat.
- Le parent demande ces valeurs dans la proposition/revue des bindings et fixtures, puis appelle le collecteur **avant** ArchitectureContractVerifier, sur son même adapter/snapshot. Aucun changement de facts ni nouveau verdict normatif.
- Publier via `store.publish_native_proof('ARC-06', Proof(**p))` ses X/V seulement si le X de contribution porte exactement `ARC-06:error_client` (complet nominal ou défaut réellement observé). Une contribution NOT_VERIFIED partielle ne satisfait pas ce tag. Les proofs sont liées aux mêmes hashes et hors racine produit.
- Ne pas fusionner le PASS étroit de cette contribution en PASS global ARC-06. Les contrôles OpenAPI/validation/DTO et les R indépendantes restent obligatoires ; ce collecteur ne crée aucune R.

## Preuves séparées, sans inflation de portée

`browser-v1.xml` : 6 PASS, 5,56 s. `browser-final-v2.xml` : **7 PASS, 11,37 s**, après le commit du collecteur. Application fixture usine explicitement de confiance : vrai HTTP TCP, vraie SQLite, vrai Argon2 et vrai Chromium hôte **local explicitement autorisé uniquement pour cette fixture**. Ces tests qualifient l'algorithme, pas le confinement d'un produit généré.

Positif : nom provenant réellement du DTO et erreur serveur consommée. Trois négatifs : mauvaise propriété `name`, corps d'erreur abandonné, mauvais acteur du DTO. Deux refus sans exécution navigateur : locator revu manquant et snapshot changé. Dernier refus : identité de fixture modifiée après navigation ; aucune X complète positive n'est publiée. Les rapports nominatifs/défectueux et screenshots sont dans `raw-v1` et `raw-v2`. Aucun mot de passe, cookie, CSRF ou base exporté.

`docker-final-v3.xml` : **1 PASS, 16,98 s**, exclusivement le nouveau nominal transport. Vrai OwnedProductHarnessSession et vrai DockerBrowserSession ; application fixture jamais importée/exécutée sur l'hôte, Chromium dans son conteneur séparé partageant seulement le namespace NETNONE du parent exact. Le test interdit `BrowserType.launch` sur l'hôte. Parent inspecté réseau `none`, navigateur `container:<CID exact>`, aucun fallback, X/V intacts du même sujet, réel GET auth/me/display_name et erreur 404 réelle. Source inchangée après ; conteneur parent absent après fermeture exacte. `raw-docker-final-v3/docker-nominal/report.json` conserve ces identités/observations et leurs preuves copiées octet pour octet.

Le premier `docker-v1.xml` est conservé : 1 FAIL, 5,51 s, nom de port d'inspection incorrect dans le test (`attest` au lieu de `inspect_configuration`), avant toute interaction navigateur. `docker-v2.xml` : 1 PASS, 16,41 s, avant ajout du verrou explicite host-launch dans le test. Ce rouge n'est ni un bug du produit ni une attente affaiblie. La garde transport finale est exécutée à nouveau dans v3, pas déduite de v2.

## Reproduction courte

Depuis backend, Python factory-env verrouillé, PYTHONPATH=backend :

```powershell
$env:AUTOSPEC_ARC_BROWSER_EVIDENCE='../artifacts/remediation/REM-17/20261012-error-client/new-meta-run'
python -m pytest -c pyproject.toml tests/test_architecture_browser.py -q
$env:AUTOSPEC_ARC_BROWSER_DOCKER='1'
$env:AUTOSPEC_ARC_BROWSER_EVIDENCE='../artifacts/remediation/REM-17/20261012-error-client/new-docker-run'
python -m pytest -c pyproject.toml tests/test_architecture_browser_docker.py -q
```

L'exécutable réellement utilisé est `C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe`. Logs et XML bruts distincts conservés ; aucune campagne, inférence payante ou nouvelle globale. Les R des bindings/fixtures de métatest sont synthétiques et déclarées telles, jamais réutilisables en campagne. Le port n'est ni une TEE ni une preuve cryptographique complète ; Docker/kernel/image de fabrique restent de confiance. Le nominal étroit ne satisfait pas à lui seul ARC-06, SEC-05 ni les 57 critères.
