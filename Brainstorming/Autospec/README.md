# Autospec

> 📖 Documentation technique complète : **[how_it_works.md](./how_it_works.md)**

Usine à features pilotée par les agents **BMAD method** : depuis l'UI, tu décris
un projet ou une feature, puis le pipeline enchaîne automatiquement :

1. **PM (BMAD `pm`)** — interviewe l'utilisateur dans le chat pour clarifier le
   besoin, puis rédige un **brief produit**. Avec le bouton **Auto-spec**, le PM
   ne pose aucune question : il décide de tout lui-même. La phase spec a **deux
   modes** (toggle **💬 Interview / 🧠 Brainstorming** dans le chat) : *Interview*
   = facilitation socratique du PM dimension par dimension ; *Brainstorming* =
   l'analyste « Mary » re-questionne le besoin lui-même (DIVERGER puis CONVERGER).
2. **PO (BMAD `sm`)** — découpe le brief en **EPICs** et **user stories**
   (granularité adaptée à la complexité), chacune avec description, critères
   d'acceptance et **test d'acceptance Gherkin**, plus les **dépendances** entre
   stories (les stories indépendantes sont développées en parallèle, les
   dépendantes séquentiellement) et une **priorité kanban** (1=haute..5=basse)
   qui décide l'ordre de passage des stories indépendantes — pas de sprint,
   juste un flux priorisé.
3. **QA (BMAD `qa`)** — avant toute implémentation, décompose le test
   d'acceptance **outside-in (London school, top-down)** : le Gherkin garde la
   vision fonctionnelle, et en dessous chaque couche reçoit ses tests unitaires
   (l'API appelle la façade, la façade le service, le service le repo/LLM…),
   chacun **mockant ses collaborateurs directs**. Granularité adaptée à la
   taille de la story (triviale → le Gherkin seul suffit).
4. **Dev (BMAD `dev`)** — un agent par story, en **BDD puis TDD outside-in**
   avec `pytest-bdd` : step definitions depuis le Gherkin → tests unitaires du
   plan QA (rouges) → implémentation couche par couche du haut vers le bas →
   suite complète verte. L'orchestrateur revérifie lui-même (`uv run pytest`)
   avant de marquer la story **done**.
5. **Boucle auto-spec** — une fois l'itération livrée, l'**Analyste (BMAD
   `analyst`)** explore le produit : il formule 3-6 **hypothèses de features**,
   les score (**valeur** 1-5 / **complexité** 1-5), les priorise (le feedback
   utilisateur passe en premier) et **décide** de la prochaine à développer.
   Le PM rédige alors le brief de cette feature, le PO écrit les US, et le
   cycle repart indéfiniment jusqu'au bouton **⏹ Stopper la boucle**. Le
   backlog priorisé de l'analyste est visible dans l'UI (panneau « Backlog de
   l'analyste »), avec l'hypothèse en cours, les proposées et les livrées.

L'UI permet de **gérer plusieurs projets** (sélection / suppression), montre le
board EPIC/US avec l'état de chaque story (todo, dev en cours, rouge, vert, done,
échec). Chaque **critère d'acceptance est une ligne dépliable** affichant son
état (**inexistant / rouge / vert** — vert seulement quand tous ses tests sont
verts) et, au clic, la liste de ses tests d'acceptance et le Gherkin associé. Les
**user stories sont éditables depuis le board** : on peut **éditer** (titre,
description, priorité, critères d'acceptance, Gherkin), **ajouter**, **supprimer**
et **reprioriser** une US directement dans l'UI. Une story peut aussi être
**relancée** (si échouée), **rejouée** (si terminée) ou **forcée terminée**
directement depuis sa carte. Un
chat (spécification puis feedback), des boutons d'**interruption** (**⏸ Pause /
▶ Reprendre**, **⏹ Stopper**) et un bouton **▶ Lancer le projet** qui exécute le
`main.py` du code généré complètent l'interface.

Les montants en dollars sont des **estimations d'usage, pas des factures**. La
facturation réelle dépend du fournisseur et du compte utilisé : l'interface ne
déduit pas si un appel est couvert par un abonnement ou facturé à l'usage.
Les données d'appels interrompus et les tarifs absents peuvent manquer au total ;
un montant de `$0` ne garantit donc pas la gratuité. Un avertissement apparaît
lorsque le backend signale des appels sans données d'usage ; les anciens
historiques ne disposent pas nécessairement de cette information.

Un projet peut porter un **budget estimatif** en dollars et/ou un seuil de tokens
(`0` désactive le garde-fou), réglable à la création pour les dollars (champ
**« Budget estimatif ($) »**) ou via l'API. Le seuil est vérifié avant chaque
appel agent et à son retour. Lorsqu'un budget est actif, les appels du projet
sont sérialisés pour ne pas allouer le même reliquat à plusieurs agents ; sans
budget, leur parallélisme est conservé. Claude Code reçoit également le
reliquat via son option native `--max-budget-usd`. Les tokens d'entrée incluent
les lectures et écritures de cache Claude.

Une erreur peut encore remonter une consommation : elle est conservée dans les
totaux du projet et de l'itération. Si un appel interrompu ne remonte aucun usage
et qu'un budget est configuré, les relances automatiques s'arrêtent jusqu'à une
reprise explicite. Ce n'est **pas un plafond de facturation** : les estimations,
l'usage non remonté et les appels déjà engagés lors d'un changement de budget
peuvent empêcher de connaître le montant exact. La jauge reste informative.

## Providers de modèles (Claude / OpenAI / Ollama)

Les agents tournent par défaut sur **claude code** (CLI Claude Code en
headless, avec l'authentification configurée localement) ; **claude** passe par
l'API Anthropic directe (clé). Deux autres providers sont disponibles via **LangChain** :
**OpenAI** (clé API) et **Ollama** (modèles locaux). Sélection par
`AGENT_PROVIDER` ou à chaud via le sélecteur 🤖 du header
(`GET/POST /api/provider`). Ces providers étant de simples API de chat, les
agents Dev y manipulent les fichiers du workspace à travers un **protocole
d'outils JSON borné** (write/read confiné au workspace) — l'orchestrateur
revérifie de toute façon la suite pytest lui-même.

Le modèle du harness Claude Code est **Sonnet par défaut** (`CLAUDE_MODEL=sonnet`).
`CLAUDE_MODEL=haiku` permet de choisir un modèle plus léger ; les overrides par
phase restent disponibles.

Sous Windows, les shims npm officiels Claude/Codex sont résolus vers leur
exécutable natif ou leur script Node, sans réinterpréter les arguments dans un
shell. Un lanceur personnalisé `.cmd`, `.bat` ou `.ps1` non reconnu est refusé :
configurer un exécutable natif avec `CLAUDE_CMD` / `CODEX_CMD` à la place.
L'arrêt d'un appel attend le nettoyage de ses processus enfants ; les sorties
sont bornées à 16 Mio par flux et les dépassements sont signalés explicitement.

## Socle technique vérifié avant les stories

`PROJECT_BOOTSTRAP=1` active par défaut une création déterministe du socle,
avant la planification PO. Le choix technique est conservé dans
`technical_stack` : les demandes explicites de l'utilisateur sont prioritaires ;
sinon la pré-analyse choisit une stack adaptée. Les templates prennent en charge
Python/FastAPI, Go, Rust, Node.js et un frontend React/Vite/TypeScript. Une stack
non prise en charge provoque un diagnostic explicite, sans substitution silencieuse.

Avec le bootstrap actif, le choix par défaut privilégie Go pour les services
standards, Python pour les petits prototypes et SQLite, Rust pour une forte
criticité. `LANGUAGE_SELECTOR=1` autorise l'architecte LLM à affiner ce choix ;
une demande explicite reste prioritaire.

Le bootstrap installe les dépendances, exécute les tests du socle et vérifie le
démarrage réel et l'accès HTTP avant d'engager les agents sur les fonctionnalités.
Pour un fullstack, il vérifie aussi l'appel frontend → backend ; le template
Python peut vérifier un aller-retour SQLite lorsqu'une base est requise.
Les socles React sont aussi chargés dans Chromium pour détecter une page blanche
ou une erreur JavaScript ; le build interdit les modules de tests/Vitest dans
le bundle de production. Installer Chromium une fois depuis `frontend/` avec
`npx playwright install chromium` (voir [les prérequis détaillés](DOCKER_DELIVERY.md)).
Un prérequis absent ou une installation impossible bloque cette étape avec son
diagnostic, sous une échéance `BOOTSTRAP_TIMEOUT_S=180`. Les checks restent
distincts des tests fonctionnels des stories. Le mode démo `FAKE_AGENTS=1`
continue de fonctionner sans installer les toolchains ni appeler Docker.

## Livraison Docker

Les templates exportés correspondent à la stack choisie : Python, Go, Rust,
Node.js, frontend statique, CLI ou bibliothèque. Les fullstacks réunissent le
frontend compilé et le backend dans une image ; un frontend seul est servi par
nginx non-root sur le port interne 8080. Les dépendances sont installées à la
construction, les secrets sont exclus du contexte et les modifications manuelles
ou réparations de Dockerfile sont préservées.

La construction et les contrôles Docker sont activés par défaut
(`DOCKER_DELIVERY=1`) pour tous les nouveaux projets, y compris les CLI et
bibliothèques. `DOCKER_DELIVERY=0` les désactive explicitement, quel que soit le
profil. Les projets importés (`brownfield`) restent sur activation explicite.
Le bouton de déploiement manuel peut
lancer la livraison à la demande. Docker doit être opérationnel : un daemon
absent est un problème d'infrastructure, pas une invitation à réparer le code.
Les services sont publiés sur `127.0.0.1`, avec limites de ressources et rollback
du conteneur précédent si le redéploiement échoue. Une CLI ou bibliothèque
produit une image, sans service HTTP permanent.

Les API/fullstacks du socle doivent satisfaire le contrat JSON de `/api/health`
en HTTP 200 ; un frontend seul doit répondre en 2xx. Les sondes entre services
contrôlent uniquement leur connectivité. SQLite utilise un volume persistant,
conservé après Undeploy ; le candidat est testé sur une base isolée. Un rollback
de conteneur ne restaure pas les migrations déjà appliquées aux données.

Voir [DOCKER_DELIVERY.md](./DOCKER_DELIVERY.md) pour le contrat, les variables
et les vérifications exécutables.

## Composants, livraison & feedback

- **Composants (E3/E4)** : avec `COMPONENTS=1`, un agent solutionneur
  propose après le brief les composants du produit (backend FastAPI + frontend
  React par défaut, PostgreSQL/Redis en optionnel). L'utilisateur les
  approuve/écarte dans le panneau 🧱, puis « Créer les composants » matérialise
  dossiers et manifests dans le workspace (`backend/`, `frontend/`,
  `docker-compose.yml`) ; l'installation réelle des dépendances reste derrière
  `SETUP_INSTALL=1`.
- **Livraison (I2)** : le bouton **📘 Doc** fait rédiger par le tech-writer le
  README du projet généré (présentation, lancement, tests, architecture) ;
  **⬇ Zip** télécharge le workspace (sans `.git`/`.venv`/état interne) ;
  **🔀 Commit** fait un commit git propre du workspace. Avec
  `TECH_WRITER=1`, la doc est régénérée après chaque build.
- **Analyse d'impact (E2)** : un feedback envoyé quand la pipeline est dormante
  est analysé automatiquement — soit il **amende une US non implémentée**
  (todo/échouée, qui repart en todo), soit il **crée un nouvel Epic/US**
  buildable via « ▶ Continuer le build », soit il est simplement noté.
- **Tests d'acceptance UI (E5)** : avec `UI_TESTS=1`, les US marquées
  `ui` par le PO reçoivent en plus des **tests Playwright rejouables**
  (`tests/ui/`, marker pytest `ui`, screenshots + assertions de rendu) ; la
  story n'est done que si `uv run pytest -m ui` est vert aussi.

## Fenêtre d'usage Claude : reprise automatique (M2)

Quand les agents tournent sur le **harness Claude** (abonnement), un appel qui
échoue sur une **limite d'usage de session** déclenche un arrêt propre de la
pipeline et programme une **reprise automatique** au moment où une session
fraîche s'ouvre : l'heure de reset est lue dans l'erreur du CLI, sinon via le
bloc de facturation actif rapporté par **ccusage** (`ccusage blocks --json`),
sinon un délai de repli. La reprise est **persistée** (`resume_at`) et
**ré-armée après un redémarrage** du backend ; la tentative de la story
interrompue n'est pas décomptée. L'UI affiche « ⏰ Reprise auto à HH:MM »
(annulable). C'est de l'ordonnancement légitime du quota souscrit : le travail
attend le reset de la fenêtre, rien n'est contourné.

## Harnais de raffinement (optionnel)

Un **harnais de raffinement** peut améliorer les artefacts des agents via une
boucle **maker → critic → judge** : le maker produit (plan PO ou code Dev), un
agent **critic** (ReAct REFLECT/ACT) propose des améliorations actionnables sans
réécrire, et un agent **judge** note la qualité de **0 à 100**. La boucle
s'arrête de façon **déterministe** dès que le **score atteint le seuil**
(`REFINE_QUALITY_THRESHOLD`, défaut 80) **ou** que le **cap d'allers-
retours** est atteint (`REFINE_MAX_ROUNDS`, défaut 2), selon ce qui
survient en premier. Le raffinement du code Dev est protégé par une **garde
git** : une révision n'est gardée que si `uv run pytest` reste vert (sinon
rollback). Deux nouveaux rôles de chat apparaissent dans l'UI : **🧐 Critique**
et **⚖️ Juge**.

**OFF par défaut** (pour économiser des tokens). Activation :

```powershell
$env:REFINE = "1"          # interrupteur global (requis)
# $env:REFINE_PO = "1"     # raffiner le plan PO (défaut 1)
# $env:REFINE_DEV = "1"    # raffiner le code Dev (défaut 1)
```

## Mode démo (sans Claude)

Pour faire tourner et vérifier tout le stack **sans le CLI Claude ni build de
venv uv**, lance le backend avec `FAKE_AGENTS=1` : un agent scripté
déterministe pilote toute la pipeline (PM→PO→QA→Dev). C'est aussi ce qui
alimente le test e2e Playwright.

```powershell
# Backend en mode démo
cd backend
$env:FAKE_AGENTS = "1"; $env:DEMO_DELAY_S = "0.8"
uv run uvicorn autospec.api.server:app --port 8100

# Test e2e (build le front + backend démo auto-démarré + navigateur piloté)
cd frontend
npm run test:e2e
```

## Architecture

```
Autospec/
├── .vscode/launch.json    # compound "Full Stack (Backend + Frontend)"
├── backend/               # FastAPI + orchestrateur (uv)
│   ├── autospec/
│   │   ├── agents/        # personas BMAD (_bmad/bmm/agents) + runner CLI Claude headless
│   │   ├── orchestrator/  # pipeline PM→PO→Dev, scheduler de dépendances, bus d'événements
│   │   └── api/           # REST + WebSocket
│   └── tests/
├── frontend/              # React + Vite + TS (board, chat, exécution)
└── workspace/<projet>/    # code généré (projet uv autonome : features/, tests/steps/, package)
```

Les agents sont exécutés via le **CLI Claude Code en mode headless**
(`claude -p --output-format json`) avec les personas BMAD installées dans
`../_bmad/bmm/agents/` comme system prompt.

## Démarrage

```powershell
# Backend
cd backend
uv sync --extra dev
uv run uvicorn autospec.api.server:app --port 8100

# Frontend (autre terminal)
cd frontend
npm install
npm run dev   # http://localhost:5183
```

Ou dans VS Code : **Run and Debug → Full Stack (Backend + Frontend)**.

Sous Windows, lancer le backend sans `--reload` ni workers multiples : le
préflight utilise les sous-processus asyncio, disponibles avec la boucle
Proactor du serveur simple. Un lancement incompatible est signalé par un
diagnostic de prérequis ; il ne déclenche pas de réparation LLM.

## Tests

```powershell
cd backend
uv run pytest
```

## CI (GitHub Actions)

Le workflow [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) tourne sur
chaque `push` et `pull_request` avec 3 jobs sur `ubuntu-latest` :

| Job | Etapes |
| --- | --- |
| **backend** | `uv sync --extra dev` → `uv run pytest -q` (dans `backend/`) |
| **frontend** | Node 20 → `npm ci` → `npm run build` → `npm run test:unit` (Vitest, dans `frontend/`) |
| **e2e** | uv + Node 20 → `uv sync` (backend, cree le `.venv` requis par Playwright) → `npm ci` → `npx playwright install --with-deps chromium` → `npm run test:e2e` (dans `frontend/`) |

> ⚠️ **Contrainte monorepo** : Autospec vit actuellement dans le monorepo
> `squad-ai`, dont le `.github` est a la racine. GitHub Actions ne declenche que
> les workflows en `<repo-root>/.github/workflows/`. C'est pourquoi un workflow
> racine **`squad-ai/.github/workflows/autospec-ci.yml`** (filtre `paths:
> ["Brainstorming/Autospec/**"]`, chemins prefixes par `Brainstorming/Autospec/`)
> declenche le CI dans le monorepo, et ne se lance QUE sur les changements
> d'Autospec. Le fichier `Autospec/.github/workflows/ci.yml` ci-dessus reste en
> place, ecrit pour fonctionner tel quel et pret pour une extraction future
> d'Autospec dans son propre depot autonome.

## Configuration (variables d'environnement)

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `BMAD_DIR` | `../_bmad` | Dossier d'installation BMAD |
| `CLAUDE_CMD` | auto (`claude.cmd`) | Binaire Claude Code |
| `CLAUDE_MODEL` | `sonnet` | Modèle du harness Claude Code ; `haiku` possible pour réduire le coût |
| `AGENT_PROVIDER` | `claude code` | Provider d'agents : `claude code` (harness CLI), `claude` (API Anthropic), `openai`, `ollama` (LangChain) |
| `OPENAI_API_KEY` | (ou `OPENAI_API_KEY`) | Clé API du provider openai |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modèle OpenAI |
| `OPENAI_BASE_URL` | api.openai.com | Endpoint OpenAI-compatible |
| `OPENAI_PRICE_IN` / `_OUT` | `0` | $/1M tokens pour estimer le coût |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Serveur Ollama local |
| `OLLAMA_MODEL` | `llama3.1` | Modèle Ollama |
| `PROVIDER_TOOL_ROUNDS` | `8` | Cap de tours du protocole d'outils fichiers (providers LangChain) |
| `COMPONENTS` | `0` | Phase « composants » (agent solutionneur après le brief) |
| `SETUP_INSTALL` | `0` | Installe réellement les deps des composants (uv sync / npm install) |
| `PROJECT_BOOTSTRAP` | `1` | Crée et vérifie le socle technique avant les stories |
| `BOOTSTRAP_TIMEOUT_S` | `180` | Échéance du bootstrap et de ses contrôles initiaux |
| `TEST_SUITE_TIMEOUT_S` | `180` | Échéance de chaque exécution de suite backend/frontend native |
| `DOCKER_DELIVERY` | `1` | Docker pour tous les nouveaux projets, CLI/bibliothèques incluses ; brownfield sur activation explicite ; `0` prioritaire sur les profils |
| `TECH_WRITER` | `0` | Tech-writer auto après chaque build (sinon bouton 📘 Doc) |
| `UI_TESTS` | `0` | Tests d'acceptance UI Playwright pour les US `ui` |
| `SESSION_MONITOR` | `1` | Watchdog fenêtre d'usage Claude (M2, provider claude uniquement) |
| `CCUSAGE_CMD` | `npx --yes ccusage` | Commande ccusage (heure de reset du bloc actif) |
| `RESUME_FALLBACK_MIN` | `60` | Délai de reprise (min) si l'heure de reset est inconnue |
| `PERMISSION_MODE` | `bypassPermissions` | Mode permissions des agents |
| `MAX_PARALLEL_DEVS` | `2` | Agents dev en parallèle |
| `DEV_MAX_ATTEMPTS` | `2` | Tentatives par story |
| `AGENT_TIMEOUT_S` | `1800` | Timeout d'un appel agent |
| `REFINE` | `0` | Interrupteur global du harnais de raffinement |
| `REFINE_PO` | `1` | Raffinement du plan PO (si global ON) |
| `REFINE_DEV` | `1` | Raffinement du code Dev (si global ON) |
| `REFINE_MAX_ROUNDS` | `2` | Cap dur d'allers-retours maker↔critic↔judge |
| `REFINE_QUALITY_THRESHOLD` | `80` | Seuil de score du juge pour s'arrêter |
