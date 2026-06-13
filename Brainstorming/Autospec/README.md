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

Un projet peut porter un **budget** (plafond de coût en $ et/ou de tokens, `0` =
illimité) réglable à la création (champ **« Budget max ($) »**) ou après coup :
à chaque point de contrôle, dès que l'usage atteint le plafond, la pipeline
**s'arrête automatiquement** (message « 💰 Budget atteint ») et la jauge d'usage
passe en rouge.

## Harnais de raffinement (optionnel)

Un **harnais de raffinement** peut améliorer les artefacts des agents via une
boucle **maker → critic → judge** : le maker produit (plan PO ou code Dev), un
agent **critic** (ReAct REFLECT/ACT) propose des améliorations actionnables sans
réécrire, et un agent **judge** note la qualité de **0 à 100**. La boucle
s'arrête de façon **déterministe** dès que le **score atteint le seuil**
(`AUTOSPEC_REFINE_QUALITY_THRESHOLD`, défaut 80) **ou** que le **cap d'allers-
retours** est atteint (`AUTOSPEC_REFINE_MAX_ROUNDS`, défaut 2), selon ce qui
survient en premier. Le raffinement du code Dev est protégé par une **garde
git** : une révision n'est gardée que si `uv run pytest` reste vert (sinon
rollback). Deux nouveaux rôles de chat apparaissent dans l'UI : **🧐 Critique**
et **⚖️ Juge**.

**OFF par défaut** (pour économiser des tokens). Activation :

```powershell
$env:AUTOSPEC_REFINE = "1"          # interrupteur global (requis)
# $env:AUTOSPEC_REFINE_PO = "1"     # raffiner le plan PO (défaut 1)
# $env:AUTOSPEC_REFINE_DEV = "1"    # raffiner le code Dev (défaut 1)
```

## Mode démo (sans Claude)

Pour faire tourner et vérifier tout le stack **sans le CLI Claude ni build de
venv uv**, lance le backend avec `AUTOSPEC_FAKE_AGENTS=1` : un agent scripté
déterministe pilote toute la pipeline (PM→PO→QA→Dev). C'est aussi ce qui
alimente le test e2e Playwright.

```powershell
# Backend en mode démo
cd backend
$env:AUTOSPEC_FAKE_AGENTS = "1"; $env:AUTOSPEC_DEMO_DELAY_S = "0.8"
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
uv run uvicorn autospec.api.server:app --reload --port 8100

# Frontend (autre terminal)
cd frontend
npm install
npm run dev   # http://localhost:5183
```

Ou dans VS Code : **Run and Debug → Full Stack (Backend + Frontend)**.

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
| `AUTOSPEC_BMAD_DIR` | `../_bmad` | Dossier d'installation BMAD |
| `AUTOSPEC_CLAUDE_CMD` | auto (`claude.cmd`) | Binaire Claude Code |
| `AUTOSPEC_CLAUDE_MODEL` | (défaut CLI) | Modèle à utiliser |
| `AUTOSPEC_PERMISSION_MODE` | `bypassPermissions` | Mode permissions des agents |
| `AUTOSPEC_MAX_PARALLEL_DEVS` | `2` | Agents dev en parallèle |
| `AUTOSPEC_DEV_MAX_ATTEMPTS` | `2` | Tentatives par story |
| `AUTOSPEC_AGENT_TIMEOUT_S` | `1800` | Timeout d'un appel agent |
| `AUTOSPEC_REFINE` | `0` | Interrupteur global du harnais de raffinement |
| `AUTOSPEC_REFINE_PO` | `1` | Raffinement du plan PO (si global ON) |
| `AUTOSPEC_REFINE_DEV` | `1` | Raffinement du code Dev (si global ON) |
| `AUTOSPEC_REFINE_MAX_ROUNDS` | `2` | Cap dur d'allers-retours maker↔critic↔judge |
| `AUTOSPEC_REFINE_QUALITY_THRESHOLD` | `80` | Seuil de score du juge pour s'arrêter |
