# Autospec

> 📖 Documentation technique complète : **[how_it_works.md](./how_it_works.md)**

Usine à features pilotée par les agents **BMAD method** : depuis l'UI, tu décris
un projet ou une feature, puis le pipeline enchaîne automatiquement :

1. **PM (BMAD `pm`)** — interviewe l'utilisateur dans le chat pour clarifier le
   besoin, puis rédige un **brief produit**. Avec le bouton **Auto-spec**, le PM
   ne pose aucune question : il décide de tout lui-même.
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
verts) et, au clic, la liste de ses tests d'acceptance et le Gherkin associé. Un
chat (spécification puis feedback) et un bouton **▶ Lancer le projet** qui
exécute le `main.py` du code généré complètent l'interface.

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
