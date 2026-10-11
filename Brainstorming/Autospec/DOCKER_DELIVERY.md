# Livraison Docker et socle technique

Cette page décrit le contrat implémenté. Les tests unitaires vérifient la logique
de la factory ; la compatibilité d'une image et de son application nécessite
aussi un moteur Docker opérationnel et un véritable build/run.

## Avant les fonctionnalités : vérifier le socle

`PROJECT_BOOTSTRAP=1` est activé par défaut. Après la pré-analyse et le brief,
avant le PO, le contrat persistant `technical_stack` fixe le type de produit,
le langage backend, le frontend et la base demandée. Les choix explicites de
l'utilisateur sont prioritaires. Les templates disponibles couvrent
Python/FastAPI, Go, Rust, Node.js et React/Vite/TypeScript ; un choix non supporté
produit un diagnostic explicite plutôt qu'une substitution.

Le bootstrap matérialise le socle de manière déterministe, installe ses
dépendances, teste son démarrage et les accès HTTP. Pour un fullstack, le
frontend doit atteindre le backend. Le template Python avec SQLite vérifie
aussi un accès réel à la base. Les contrôles sont bornés par
`BOOTSTRAP_TIMEOUT_S=180` et leur échec empêche d'engager les agents sur les
stories. Une toolchain ou une dépendance indisponible doit être corrigée avant
de reprendre. Le mode `FAKE_AGENTS` évite ces installations et exécutions réelles.

Pour un frontend seul, le socle crée uniquement le projet React : pas de backend
Python, de `main.py` ou de virtualenv artificiel. Les tests frontend, le build
et un accès HTTP au serveur de preview vérifient ce cas. Pour tout socle React,
le préflight ouvre aussi le bundle de production dans **Chromium réel** : le
conteneur `#root` doit être rendu et aucune erreur JavaScript ou requête échouée
ne doit être observée. En fullstack, le composant initial doit confirmer son
`fetch` frontend → API ; le contrôle API vérifie aussi SQLite quand elle est
sélectionnée. Une simple réponse HTTP 200 ne suffit donc pas pour valider une UI.

La découverte des features exclut les fichiers `.test.tsx`, `.spec.tsx` et
`.d.tsx` dès le glob d'import. Une garde supplémentaire inspecte le graphe des
modules du build et refuse les fichiers de tests ou Vitest dans le bundle de
production. Une page blanche ou une erreur du navigateur bloque avant les agents
métier. Si Playwright ou Chromium manque, le préflight remonte une panne
d'infrastructure et reste bloqué. Préparer ces dépendances depuis la racine
d'Autospec, avec les commandes PowerShell suivantes :

```powershell
cd frontend
npm ci
npx playwright install chromium
cd ..
```

Le navigateur utilise les dépendances d'Autospec, sans ajouter Playwright au
projet généré. Ce contrôle partage l'échéance globale du préflight et ses
processus sont arrêtés lors d'une annulation. Les adaptateurs de base actuellement
validés sont `none` et SQLite avec Python/FastAPI ; PostgreSQL et les autres bases
ne sont pas implicitement assimilés à SQLite.

Le provider par défaut reste le harness **Claude Code**, avec
`CLAUDE_MODEL=sonnet`. `haiku` peut être choisi explicitement pour un modèle plus
léger ; le bootstrap déterministe ne délègue pas l'écriture du socle à ce modèle.

La sélection déterministe privilégie Go pour les services standards, Python
pour les prototypes simples et SQLite, Rust pour une forte criticité.
`LANGUAGE_SELECTOR=1` permet une proposition LLM complémentaire ; les choix
explicites restent prioritaires. Une fois le socle vérifié, les prompts PO et
architecte planifient uniquement le comportement demandé, sans nouvelle tâche
de scaffolding, factory ou démarrage serveur. Un besoin minuscule reste limité
à deux stories maximum, tests compris.

## Types d'images

| Produit | Construction | Contrôle de livraison |
|---|---|---|
| Backend Python | `uv sync --no-dev`, environnement intégré | Exécution de `main.py`, HTTP et réseau |
| Backend Go | Compilation native du binaire | Démarrage, HTTP et réseau |
| Backend Rust | Compilation release d'une cible binaire | Démarrage, HTTP et réseau |
| Backend Node.js | Installation, build éventuel, dépendances de production | `npm start`, HTTP et réseau |
| Frontend seul | React/Vite avec Node 22, nginx non-root | HTTP port interne 8080 et réseau |
| Fullstack | Frontend compilé puis copié dans l'image backend | Backend servant `AUTOSPEC_STATIC_DIR`, HTTP et réseau |
| CLI | Image de la toolchain retenue, point d'entrée natif | Commande `--help` sous timeout, sans réseau |
| Bibliothèque | Package installé/compilé dans une image | Build du package, aucun service HTTP attendu |

Les CLI et bibliothèques sont des images livrables ; elles ne créent pas un
service permanent ni une URL. Le nom de l'image est `autospec/<slug>:latest`.
Les services ont le nom `autospec-<slug>` et les labels `autospec.project` et
`autospec.port`.

Les templates sont exposés par :

```python
dockerfile_text(port, kind="backend", language="python", frontend_root="frontend")
write_deploy_artifacts(ws, port=None, kind="backend", language="python", frontend_root="frontend")
```

`kind` vaut `backend`, `fullstack`, `frontend`, `cli` ou `library`. Un frontend
peut se trouver dans un sous-répertoire déclaré ou à la racine (`frontend_root="."`).
Les chemins absolus, remontées `..` et valeurs invalides sont rejetés avant écriture.
Les projets hors contrat nécessitent un template adapté ; un backend Go/Rust ne
doit jamais être classé frontend-only parce qu'il n'a pas de `main.py`.

## Artefacts sûrs et conservés

La première ligne du Dockerfile reste `# syntax=docker/dockerfile:1` pour
BuildKit. Le marqueur `# autospec:managed` est suivi d'une empreinte SHA-256 du
contenu généré. Autospec régénère seulement un artefact encore identique à sa
version générée. Une correction manuelle ou d'agent reste donc conservée même
si le marqueur est présent. Les anciens templates sont migrés uniquement si
leur contenu complet est reconnu ; un marqueur seul ne donne aucun droit
d'écrasement. La même protection s'applique à la CI et à la configuration nginx.

`.dockerignore` exclut `.env`, `.env.*`, les clés, credentials, caches et
environnements locaux. Les règles personnalisées sont conservées et une garde
de secrets est ajoutée après les éventuelles règles de réinclusion. `.gitignore`
ne protège pas à lui seul le contexte Docker.

Quand un lockfile est présent, `npm ci`, `uv sync --frozen` ou
`cargo build --locked` l'impose. Une installation échouée échoue immédiatement :
aucun `|| true` ni repli après échec de `npm ci`. Le runtime n'effectue aucune
synchronisation de dépendances. Les images tournent avec un utilisateur non-root
et les applications disposent d'un répertoire `/app/data` inscriptible.

La CI exportée correspond à la toolchain : pytest, `go test ./...`, `cargo test`
ou `npm test`, et compilation du frontend pour les produits concernés. Un
frontend-only ne reçoit pas un workflow Python.

## Déploiement, annulation et rollback

Après les gates de livraison, `docker_deploy.deploy_and_verify` construit une
image candidate. Pour un service, un conteneur candidat démarre sur un port
loopback éphémère et doit satisfaire son contrôle de santé avant de toucher au dernier
conteneur livré. Le passage au port stable conserve l'ancien conteneur comme
sauvegarde jusqu'à ce que les contrôles de santé et de réseau réussissent.
Un échec restaure la sauvegarde ; une courte interruption pendant la bascule
reste possible. Les erreurs de rollback ou nettoyage sont remontées.

Pour un socle `api` ou `fullstack`, la santé exige un HTTP 200 sur
`/api/health` et un objet JSON contenant `status="ok"`,
`service="autospec-bootstrap"` et `database="ok"` si une base est prévue,
sinon `database="none"`. Un frontend seul doit répondre en HTTP 2xx.
Les projets historiques sans contrat gardent seulement leur contrôle de
connectivité HTTP : une réponse 404/500 n'y démontre pas une application saine.

Pour SQLite, le conteneur livré monte le volume nommé
`autospec-<slug>-data` sur `/app/data`, avec
`DATABASE_URL=sqlite:////app/data/app.db`. Le label `autospec.project` est
vérifié avant réutilisation : un volume appartenant à un autre projet est
refusé. Le candidat utilise un volume temporaire isolé, nettoyé ensuite ;
ses vérifications ne modifient donc pas la base persistante du service livré.
Le conteneur final retrouve ce volume lors des redéploiements et Undeploy le
conserve volontairement. La suppression des données exige une action explicite.

Le rollback restaure l'application précédente, pas les migrations déjà
appliquées à la base par le conteneur final. Le contrôle sur une base candidate
ne valide pas une migration des données de production ; celles-ci nécessitent
une stratégie de migration et de sauvegarde adaptée.

Le conteneur est publié sur `127.0.0.1:<port>`, avec `--cap-drop ALL`,
`--security-opt no-new-privileges`, une limite de 512 Mio de mémoire, 1 CPU et
256 processus. Le réseau commun `autospec-net` sert uniquement à vérifier la
connectivité entre services. Ces restrictions ne remplacent pas une VM dédiée
si l'on souhaite exécuter du code hostile dans un environnement isolé.

Le timeout supervise le processus même s'il n'émet plus de logs. L'annulation
est propagée au thread et aux processus Docker ; la suppression attend l'arrêt
et le nettoyage avant de supprimer le workspace. Un `asyncio.Task.cancel()`
seul ne suffit pas à arrêter un processus lancé dans un thread.

Le port hôte précédent est réutilisé s'il est disponible ou appartient au
conteneur du projet ; sinon un port est choisi depuis `DOCKER_HOST_PORT_BASE`.
Une réservation verrouillée protège les déploiements concurrents de cette
instance. Une course avec un programme externe au moment du bind reste possible
et doit produire un échec explicite, jamais un faux succès.

Seules les deux directions entre le service courant et les autres services
sont sondées : `2 × (N−1)` contrôles, pas une matrice `N × N`. Une réponse
HTTP 4xx/5xx à ces sondes inter-conteneurs prouve la connectivité, y compris via
BusyBox `wget` ; elle ne satisfait pas le contrôle de santé strict du socle. Elle ne prouve
pas qu'une fonctionnalité métier est correcte ; les tests fonctionnels et la
runtime acceptance restent nécessaires.

Un daemon arrêté, une toolchain absente ou une panne d'infrastructure produit
un diagnostic et parque la pipeline en `needs_attention`. La classification
infra est conservée pendant les nouvelles vérifications de réparation. Les
défauts applicatifs sont réparés via la boucle existante et son budget
`INTEGRATION_FIX_ATTEMPTS`.

## Configuration et API

| Variable | Défaut | Rôle |
|---|---|---|
| `PROJECT_BOOTSTRAP` | `1` | Socle déterministe et préflight avant le PO |
| `BOOTSTRAP_TIMEOUT_S` | `180` | Échéance du bootstrap |
| `TEST_SUITE_TIMEOUT_S` | `180` | Échéance d'une suite backend/frontend native |
| `CLAUDE_MODEL` | `sonnet` | Modèle du harness Claude Code |
| `DOCKER_DELIVERY` | `1` | Tous les nouveaux projets, CLI/bibliothèques incluses ; brownfield sur activation explicite |
| `DOCKER_NETWORK` | `autospec-net` | Réseau partagé des services |
| `DOCKER_BUILD_TIMEOUT_S` | `600` | Timeout du build Docker |
| `DOCKER_DEPLOY_TIMEOUT_S` | `60` | Délai de santé ou vérification de CLI |
| `DOCKER_HOST_PORT_BASE` | `18000` | Début de la plage de ports hôtes |
| `DOCKER_CMD` | `docker` | Exécutable Docker |

Docker est activé par défaut pour les nouveaux projets : services web, frontend,
CLI et bibliothèques. Les projets importés (`brownfield`) restent sur activation
explicite. `DOCKER_DELIVERY=0` désactive le gate, même si le profil l'active ; une
valeur explicite reste prioritaire. Le déploiement manuel
`POST /api/projects/{id}/deploy` contourne volontairement ce flag, tout en
conservant les contrôles d'éligibilité et le mode démo. La réponse
`deploy_started` signifie qu'un travail de fond est parti, pas que le service
est déjà sain : suivre `deploy_status`, `deploy_detail` et les logs.

`POST /api/projects/{id}/undeploy` ne confirme le retrait qu'après réponse
positive de Docker. Une erreur préserve le diagnostic et ne masque pas une
ressource encore présente. Les champs de déploiement sont effacés explicitement
après retrait réussi. Le chargement réconcilie l'état persisté avec Docker afin
de ne pas afficher durablement une livraison disparue. Le volume SQLite persistant
reste conservé après Undeploy ; cette API ne supprime pas implicitement les données.

## Vérifications

```powershell
cd backend
uv run pytest tests/test_deploy.py tests/test_deploy_templates.py tests/test_docker_delivery.py -q
cd ../frontend
npm run test:unit
npm run build
```

Les tests d'intégration réels sont opt-in : ils installent des dépendances,
compilent les toolchains et peuvent télécharger les images de base. Ils
n'appellent aucun modèle. Depuis `backend`, avec Node/npm, uv, Go, Rust/Cargo,
Chromium et Docker disponibles :

```powershell
$env:AUTOSPEC_REAL_BOOTSTRAP = "1"
uv run pytest tests/test_bootstrap.py -q
Remove-Item Env:AUTOSPEC_REAL_BOOTSTRAP
$env:AUTOSPEC_REAL_DOCKER = "1"
uv run pytest tests/test_bootstrap_docker.py -q
Remove-Item Env:AUTOSPEC_REAL_DOCKER
uv run python scripts/docker_transaction_smoke.py
```

Le premier groupe couvre aussi le rendu React réel, un bundle contenant des
tests par erreur et une page blanche. Le deuxième construit les 17 variantes
d'images : API, fullstack, CLI et bibliothèque pour Python, Go, Node et Rust,
ainsi qu'un frontend seul. Les CLI sont exécutées avec `--help` par le véritable
chemin de livraison ; les bibliothèques sont compilées/installées sans ouvrir
de service. Les images sont contrôlées pour leur utilisateur non-root et
l'exclusion des secrets. Le dernier scénario vérifie qu'une candidate invalide conserve le
service précédent et que les données SQLite survivent au redéploiement et au
retrait/recréation du conteneur. Les ressources Docker de test ont des noms
uniques et leur nettoyage ne cible pas les projets utilisateur.

Avec un moteur Docker opérationnel, générer un backend puis un fullstack,
vérifier leur URL locale et leurs logs, puis lancer un second service pour
exercer les deux directions du réseau. Tester aussi un build bloqué jusqu'au
timeout, Stop pendant build, un redéploiement invalide conservant l'ancien
service, et Undeploy moteur arrêté. Les tests simulant le CLI Docker ne
remplacent pas ces builds et exécutions réels.
