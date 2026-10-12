# REM-13 / REM-02 — qualification Linux réelle

2026-10-12, branche codex/rem-execution, base intégrée 5e512724.

## Preuves exécutées

Interpréteur de la fabrique (pas du produit) :
`C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/factory-env/Scripts/python.exe`.
Depuis worktree/backend, `PYTHONPATH=(Get-Location).Path`.

- `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_linux_validation.py` : première preuve Python **8 passed / 40.26s**. Installation uv verrouillée Linux, pytest avec rapport structuré, UID65532, aucun secret provider/socket Docker, socket Internet impossible, API FastAPI/SQLite SELECT1 par proxylocalhost, port/conteneur nettoyés.
- `... pytest tests/test_linux_validation.py -k dependency_resolver` : **2 passed / 15.48s**. uv add/no-sync/no-build et npm lock-only/ignore-scripts effectifs, scripts npm qui auraient échoué ignorés, code produit et .env absents du builder, exports manifest+lock seulement.
- `... pytest tests/test_linux_validation.py -k fullstack` : **1 passed / 216.57s**. Socle exact Python/FastAPI+pytest, React+Vitest+build, Chromium réel, frontend→API→SQLite SELECT1. Reprise runtime réussie sans venv/node_modules hôte, sans modification du source/verrou.
- Régressions bootstrap/runtime/deploy/prompts/validation sans opt-in : **132 passed, 19 skipped / 9.97s**. Les skips concernent les anciennes preuves opt-in; aucune preuve skip n'est revendiquée comme passée.
- Runtime/lifecycle Windows : **48 passed, 2 skipped / 10.40s** (test_owned_execution + test_runner_processes + runtime). Descendants/identité/sentinelles réelles restent couverts par les tests REM-01/02 intégrés.
- Brokers/validation après exclusion instructions harness : **49 passed, 5 skipped / 5.49s**.
- Patch collecte/couverture : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_linux_validation.py -k collection_and_coverage` : **1 passed, 11 deselected / 40.79s**. Collecte pytest effective de deux cas paramétrés, aucun test exécuté pendant la collecte; exécution 2/2 PASS, couverture 4/4 lignes et 2/2 branches. Fingerprint source identique collecte/exécution.
- Fullstack après ajout du contrôle TypeScript : `... pytest tests/test_linux_validation.py -k fullstack` : **1 passed, 11 deselected / 342.83s**. Nominal React/API/DB/browser et reprise positifs; erreur TypeScript volontaire TS2322 refusée avant Vite, aucun dist exporté.
- Régressions du patch : **189 passed, 23 skipped / 43.16s**, dont sentinelles Windows et descendants réellement exécutés; **10 passed, 5 skipped / 3.41s** pour les cas validation seuls sans opt-in Docker. Rapports absents/malformés et collecte custom non reconnue refusés.
- Session runtime persistante : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_runtime_session.py` : **12 passed / 78.50s**. Origine réservée avant Docker puis injectée exactement; POST mauvaise Origin refusé 403; donnée SQLite conservée après nouveau container ID, même volume/origine; observer exec isolé, aucun egress/socket Docker/secret et /app RO. Expiration exec termine le container daemon et nettoie son volume/port; listener étranger reste joignable. Identités volume remplacées refusées, création interrompue nettoyée (fakes), close non démarré idempotent.
- Régressions runtime/collecte/Windows après ce patch : **203 passed, 24 skipped / 73.87s**. Une première requête POST avec timeout client 3s a dépassé son délai sous deux builds Docker concurrents; la preuve utilise ensuite 10s bornés, le transport proxy conserve une limite 15s par connexion.
- Recette V4 avec reporters séparés : collecte/couverture réelle **1 passed, 14 deselected / 52.13s**; fullstack API/DB/Chromium + reprise + TypeScript négatif **1 passed, 14 deselected / 270.62s**. Le builder n'interroge plus le venv contenant les roues produit pour installer les reporters; base Python et target /opt/reporters distincts, --no-deps/--no-build/--no-config. La recette normalisée est aussi liée au fingerprint.
- Régénération de verrou après fusion : `AUTOSPEC_REAL_LINUX_VALIDATION=1 pytest tests/test_lock_regeneration.py` : **15 passed / 39.16s**, dont résolution uv/npm Linux réelle de manifestes modifiés, scripts npm ignorés et résolution impossible conservant l'ancien verrou exact. Les cas de verrou dangereux, manifest/lock modifié en concurrence et manifest modifié par builder refusent l'export. Tests supplémentaires de sources cachées uv/npm et locks npm legacy : **40 passed, 8 skipped / 9.14s** sur les trois modules isolation/lock/runtime (sans opt-in Docker).
- Transport supervisor Python isolé : `... pytest tests/test_runtime_session.py` : **13 passed / 95.46s**. Un socket.py produit injecté dans le stage après startup ne remplace pas le relais HTTP; /usr/local/bin/python -I et cwd container /tmp ignorent le chemin produit. La persistance/Origin/refus403/expiration/cleanup restent positifs.

Les erreurs détectées puis corrigées par les preuves réelles : npm refuse userconfig et globalconfig tous deux `/dev/null`; BuildKit traite `FROM sha256:<ID>` comme un faux repository; un lien /app/node_modules dans un bind Windows ne garantit pas un lien Linux fonctionnel. Le code utilise maintenant un digest de registre FROM, deux chemins npm distincts, et source/cache Node dans tmpfs Linux. Dépendances image-owned `/opt`, non raw-montées.

## Frontière et API

`LinuxEnvironmentManager(cache_root external,docker,timeout).ensure_lock(root,ecosystem)` pour bootstrap initial seulement; `.prepare(root,ecosystem,mode)` retourne `LinuxEnvironment(ecosystem,mode,fingerprint,image,attestation)`. Le fingerprint porte manifests+verrous+imageID/digest toolchain+platform Linux+mode+recette/reporters. Cache supprimé : rebuild depuis verrous; aucune restauration native.

`dependency_resolver(argv,*,cwd,env=None)` façade de DependencyCoordinator. Seuls ses uv add/lock --check et npm install lock-only sont admis. Stage de manifests/verrous uniquement, registres publics sans credentials, scripts/builds source désactivés. Aucun environnement supplied n'entre dans le conteneur. Export précisément manifests/verrous, coordinateur possède sérialisation et rollback.

`LinuxEnvironmentManager.regenerate_lock(root,ecosystem)->Path` est la voie explicite après fusion de manifeste. Le caller détient le verrou dependency projet. Networking dans stage de manifeste seulement (ancien lock exclu), nouvelle sortie admise/bornée avant atomic_bytes, manifest original/builder et lock original recontrôlés avant remplacement. L'ancien verrou n'est jamais supprimé préalablement; échec resolution/admission/concurrence/publication le préserve. ensure_lock conserve sa sémantique bootstrap/no-overwrite. Les config uv inconnues, URL cachées dans contraintes/overrides uv, overrides npm et lock npm legacy non structuré sont refusés avant installation/réseau.

`IsolatedValidator(cache_root external,docker,timeout).run_suite(root,ecosystem,'test',reportpath external,test_args=()) -> IsolatedSuiteResult(evidence:SuiteEvidence,output,fingerprint,image)`. Python : pytest-json-report; Node : Vitest JSON ou TAP natif. Les rapports préexistants sont supprimés du stage. Rapports absents/invalides ne sont jamais SUCCESS. `build_frontend(root)` compile via Vite directement dans Docker et retourne un dossier temporaire supervisor contenant dist uniquement; caller doit le supprimer. `run_command` ne synchronise pas librement les modifications.

`collect_python(root,reportpath external) -> (tuple(sorted pytest nodeids), IsolatedSuiteResult)` utilise pytest --collect-only et ses collectors structurés, pas une recherche regex du source. Types Function/TestCaseFunction/DoctestItem admis; comptes incohérents, erreurs ou types custom non reconnus refusés. `run_suite(...,coveragepath external,coverage_source='.')` ajoute coverage lignes/branches; l'absence ou la malformation de coverage invalide la preuve. `IsolatedSuiteResult.source_fingerprint` lie les fichiers stagés pré-exécution, `.coverage` expose le rapport. Reporters supervisor exacts : pytest-json-report 1.5.0, pytest-cov 7.0.0, coverage 7.10.6; aucune couverture des sous-processus n'est revendiquée. Si tsconfig existe, `build_frontend` impose tsc -b avant Vite. Les anciens dist ne sont jamais réutilisés.

`RuntimeSession(filtered_stage,image,command,port=8000,ecosystem='python'|'node',docker,env)` contextmanager. `origin` est le proxy TCP127.0.0.1 possédé, `host_port`, `identifier` ID immuable, `.logs()`, `.close()`. Le container garde **network=none**, nonroot, RO rootfs, capsdrop, no-new-privileges, tmpfs, limites process/mémoire/CPU; aucun port Docker publié ou réseau partagé. Le proxy utilise docker exec vers le container exact et un port interne fixe. Le driver trusted utilise Chromium frais, serviceworkers/WebSockets bloqués, origine HTTP unique, aucun source/commande produit sur host.

La session réserve désormais son socket loopback **dès construction, avant launch** : le caller doit close même sans __enter__. Options contrôlées `application_origin=True` injecte APP_ORIGIN=self.origin; `local_cookie_mode=True` injecte SESSION_COOKIE_SECURE=false seulement avec origin contrôlée; ce mode doit être explicitement relié à une config produit revue, sinon NON VERIFIABLE. `persistent_database=True` fournit `.database_url=sqlite:////var/lib/autospec-validation/support.sqlite` et `.database_path=/var/lib/autospec-validation/support.sqlite`. Un nouveau volume Docker local UUID/owner/kind/CreatedAt est initialisé par chmod/chown constant sans source ni réseau, puis monté au runtime nonroot; aucun bind DB hôte. `.restart()` garde volume/origine et remplace exactement le container ID. `.close()` supprime uniquement ce volume éphémère de validation, jamais un volume de livraison. Le montage source runtime /app est readonly. `.exec(argv,stdin='',timeout=30)->(rc,out,err)` est une API supervisor source-revue, non disponible au modèle; pas d'env/cwd host/copy-back. Timeout/cancellation arrête aussi le container daemon et ses descendants. `.is_running()` inspecte frais l'ID exact/owner puis State.Running, pas le seul exit0 du Docker client.

Bootstrap _spawn/_command historiques refusent ISOLATION_UNAVAILABLE; verify/verify_runtime utilisent uniquement l'environnement Linux, le runtime net-none et le driver trusted. Runtime acceptance ne lance plus runtime_acceptance.js (ancien lanceur de produit host). Docker delivery build utilise une recette factory nouvelle, un contexte filtré et dependencies image, jamais le Dockerfile/.dockerignore produit.

## Sources primaires / provisioning

Images officielles provisionnées explicitement, puis digest/ID vérifiés localement :
- ghcr.io/astral-sh/uv:python3.12-bookworm-slim, digest sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58.
- node:22-bookworm-slim, digest sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392.

Documentation officielle : https://docs.astral.sh/uv/guides/integration/docker/ ; https://docs.astral.sh/uv/reference/cli/ ; https://docs.docker.com/engine/network/port-publishing/ . Docker confirme qu'un bridge --internal permet encore l'accès aux services de l'hôte sur l'adresse bridge; le runtime de validation n'utilise donc aucun bridge, mais le proxy exec/net-none.

## Limites explicites

- Toolchains isolées Python/Node seulement. Go/Rust refusent infra plutôt que fallback host ou skip success.
- Registres publics PyPI/npm seulement; sources locales/git/URL/workspaces/custom indexes refusés.
- Le builder réseau ne reçoit que des manifests/verrous admis. Il ne sert jamais à exécuter le source produit. Le Docker engine et les images officielles provisionnées sont dans le périmètre trusted.
- Les rapports tests restent des sorties du produit, soumis à l'intégrité/oracle/admission supervisée du parent. Un exit0/rapport JSON n'est pas seul une preuve d'acceptation métier.
- Chromium prouve rendu/probe initial, pas tous les parcours métier Gherkin : contrat/journeys restent du ressort de l'admission parent.
- La couverture concerne les tests Python directs; les collectors pytest custom inconnus sont refusés. La validité du rapport ne remplace pas le rapprochement contractuel expected IDs/admission côté parent.
- Delivery image build trusted est raccordé; nominal livraison/persistance inter-projets relève des preuves REM-20/21 du parent, pas du test fullstack décrit ci-dessus.
- Aucun appel de modèle payant n'a été lancé.
