# Démarrage du projet AI Project Manager

Guide pas-à-pas pour configurer et lancer le **backend** (FastAPI + SQLite) et le **frontend** (React + Vite) en local.

---

## Prérequis

Installés une fois pour toutes, pas de version très précise requise :

| Outil | Version | Vérification |
|---|---|---|
| **Python** | 3.12+ | `python --version` |
| **Node.js** | 18+ | `node --version` |
| **npm** | 9+ (vient avec Node) | `npm --version` |
| **Git** | n'importe | `git --version` |

Aucun Docker, aucune base de données à installer : la persistance est un **fichier SQLite local** (`backend/ai_pm.db`).

---

## Arborescence du projet

```
ai_project_manager/
├── PRD.md                  # Product Requirements Document
├── project_brief.md        # Brief initial
├── tasks.json              # Suivi de l'avancement (orchestration agents)
├── start.md                # Ce fichier
├── backend/                # API Python FastAPI
│   ├── app/
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── .env.example
└── frontend/               # UI React + Vite
    ├── src/
    ├── package.json
    └── vite.config.ts
```

---

## Étape 1 — Backend (FastAPI)

Tout se fait depuis le dossier `backend/`.

### 1.1 Créer et activer un virtual env

```bash
cd ai_project_manager/backend
python -m venv venv
```

**Activer** (selon ton shell) :

- **Git Bash / WSL** : `source venv/Scripts/activate`
- **PowerShell** : `venv\Scripts\Activate.ps1`
- **CMD Windows** : `venv\Scripts\activate.bat`
- **Linux / macOS** : `source venv/bin/activate`

Tu devrais voir `(venv)` en préfixe dans ton terminal.

> Règle projet : toujours activer le venv avant de lancer pytest, alembic ou uvicorn.

### 1.2 Installer `common-tools` en mode editable

`common-tools` est consommé depuis un **checkout local** du repo `ai-commun-tools`, pas depuis PyPI. Tu dois l'installer **avant** les deps du projet :

```bash
# Remplace le path par celui défini dans COMMONTOOLS_LOCAL_PATH (voir .env)
pip install -e "C:/Dev/IA/AzureDevOps/ai-commun-tools"
```

Cette étape installe `common_tools` ainsi que toutes ses dépendances transitives (LangChain, adapters OpenAI/Anthropic/Groq/Google/Ollama, etc.).

> ⚠️ Si cette étape est sautée, l'app démarre quand même et les endpoints CRUD fonctionnent, mais tout appel au chat de cadrage échouera avec un 503 (`LlmNotConfiguredError: common-tools is not installed`).

### 1.3 Installer les dépendances du projet

```bash
pip install -e ".[dev]"
```

Cette commande installe :
- Les deps runtime : FastAPI, Uvicorn, SQLAlchemy, aiosqlite, Alembic, Pydantic, pydantic-settings, `langchain-core`, httpx
- Les deps de dev : pytest, pytest-asyncio

`common-tools` n'est **pas** listé dans les deps du `pyproject.toml` parce qu'il est consommé en mode editable local (étape 1.2 ci-dessus).

### 1.4 Configurer `.env`

```bash
cp .env.example .env
```

Puis éditer `backend/.env` pour renseigner les variables :

```env
# Clé API du LLM (OpenAI par défaut, voir LLM_INFO)
OPENAI_API_KEY=sk-...

# Configuration du LLM utilisé par le ScopingAgent (lu par common-tools LlmFactory)
LLM_INFO={"type": "OpenAI", "model": "gpt-5.4-mini", "temperature": 0.0, "timeout": 120}

# Chemin local vers le package common-tools (installé en mode edit à l'étape 1.2)
COMMONTOOLS_LOCAL_PATH=C:/Dev/IA/AzureDevOps/ai-commun-tools

# URL SQLAlchemy async — fichier SQLite dans la racine backend
DATABASE_URL=sqlite+aiosqlite:///./ai_pm.db

# Origines CORS autorisées (le frontend Vite tourne sur 5173)
CORS_ORIGINS=["http://localhost:5173"]
```

`LLM_INFO` accepte n'importe quel adaptateur reconnu par `LangChainAdapterType` de common-tools :

| Provider | Exemple `LLM_INFO` |
|---|---|
| **OpenAI** | `{"type": "OpenAI", "model": "gpt-5.4-mini", "temperature": 0.0, "timeout": 120}` |
| **Anthropic** | `{"type": "Anthropic", "model": "claude-sonnet-4-5", "temperature": 0.0, "timeout": 120}` |
| **Groq** | `{"type": "Groq", "model": "llama-3.3-70b-versatile", "temperature": 0.1, "timeout": 60}` |
| **Google** | `{"type": "Google", "model": "gemini-2.0-flash", "temperature": 0.1, "timeout": 60}` |
| **Ollama** (local) | `{"type": "Ollama", "model": "llama3.1", "temperature": 0.1, "timeout": 120}` |
| **OpenRouter** | `{"type": "InferenceProvider OpenRouter", "model": "google/gemini-2.5-flash", "temperature": 0.1, "timeout": 60}` |

> Seule la variable `LLM_INFO` change — le code (`ScopingAgent`) reste identique puisque `common-tools` abstrait les providers derrière `Llm.ainvoke()`.

> **Sans la clé LLM**, l'application démarre quand même : les endpoints CRUD fonctionnent, seul le chat de cadrage échouera avec un 503 explicite. Pratique pour tester l'UI sans appel réseau.

### 1.5 Appliquer les migrations (créer la base SQLite)

```bash
alembic upgrade head
```

Cela crée :
- Le fichier `backend/ai_pm.db` (vide mais avec le schéma)
- Les tables `projects`, `items`, `chat_messages`

Pour repartir de zéro à tout moment :

```bash
alembic downgrade base
alembic upgrade head
# ou, plus brutal :
rm ai_pm.db && alembic upgrade head
```

### 1.6 (Optionnel) Lancer les tests

```bash
pytest -v
```

Tu devrais voir tous les tests passer (health, project CRUD, item / chat_message repositories, scoping_agent avec `_ainvoke_llm` mocké, chat_router). Les tests ne nécessitent **aucun** appel réseau ni clé LLM valide.

### 1.7 Lancer le serveur de dev

```bash
uvicorn app.main:app --reload
```

Le serveur démarre sur **`http://localhost:8000`**.

**Vérifications rapides** :

- `GET http://localhost:8000/health` → `{"status":"ok"}`
- `GET http://localhost:8000/docs` → page Swagger interactive
- `GET http://localhost:8000/api/projects` → `[]` (liste vide au premier lancement)

Laisse ce terminal ouvert, passe à l'étape 2 dans un **nouveau terminal**.

---

## Étape 2 — Frontend (React + Vite)

Tout se fait depuis le dossier `frontend/` dans un **nouveau terminal**.

### 2.1 Installer les dépendances

```bash
cd ai_project_manager/frontend
npm install
```

Environ 137 paquets, dure ~30s la première fois.

### 2.2 (Optionnel) Vérifier que TypeScript compile

```bash
npm run build
```

Si le build passe, ton setup TypeScript est bon. Tu peux ensuite reprendre `npm run dev` sans refaire ça.

### 2.3 Lancer le serveur de dev

```bash
npm run dev
```

Vite démarre sur **`http://localhost:5173`**.

Ouvre `http://localhost:5173/` dans ton navigateur. Tu devrais voir :

- L'écran d'accueil **AI Project Manager**
- Un bouton **Nouveau projet**
- Un message **Aucun projet pour l'instant** (tant que la liste est vide)

> Le frontend proxifie `/api/*` vers `http://localhost:8000` via la config Vite (`vite.config.ts`). Pas besoin de variable d'env côté front.

---

## Étape 3 — Scénario de validation end-to-end

Une fois les 2 serveurs actifs, voici un parcours rapide pour vérifier que tout tourne.

1. **Créer un projet** : clic sur **Nouveau projet**, saisir `Mon premier projet`, valider. Il apparaît dans la liste.
2. **Ouvrir le projet** : clic sur son nom → tu arrives sur `/projects/{id}`.
3. **Vérifier le layout** :
   - Header en haut avec le nom du projet + bouton **Retour**
   - Zone centrale (placeholder "Liste des User Stories (Epic 3)")
   - Chat de cadrage fixe à droite (largeur 360px)
4. **Envoyer un premier message dans le chat** (ex: `Je veux construire une app de suivi de dépenses pour moi-même`) :
   - Le message utilisateur apparaît immédiatement (optimistic update)
   - Après quelques secondes, le LLM répond
     - Soit avec des **questions de clarification** (action=`ask_question`)
     - Soit avec une **proposition de découpage** en Epic/User Story/Task (action=`propose_items`, badge "X items proposés")
5. **Itérer** : répondre aux questions, ajuster, puis valider avec un message type `ok, valide` → action=`confirm`, les items PROPOSED passent en TODO.
6. **Revenir sur la liste des projets** et rouvrir le projet : le chat recharge son historique depuis la base.
7. **Renommer un projet** depuis la liste, puis **le supprimer** (confirmation demandée).

---

## Étape 4 — Dépannage

### Backend

| Symptôme | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: app.xxx` | venv pas activé | Activer le venv puis relancer la commande |
| `alembic: command not found` | Deps pas installées | `pip install -e ".[dev]"` |
| `sqlite3.OperationalError: no such table` | Migration pas appliquée | `alembic upgrade head` |
| `LlmNotConfiguredError: LLM_INFO is missing or malformed` (503) | `LLM_INFO` absent ou mal formé dans `.env` | Renseigner un JSON valide (voir §1.4) puis redémarrer uvicorn |
| `LlmNotConfiguredError: common-tools is not installed` (503) | `common-tools` pas installé en editable | Refaire l'étape 1.2 : `pip install -e "${COMMONTOOLS_LOCAL_PATH}"` |
| `LlmNotConfiguredError: Could not build LLM from LLM_INFO` (503) | Clé API manquante ou modèle inconnu | Vérifier `OPENAI_API_KEY` / le champ `model` dans `LLM_INFO` |
| Port 8000 déjà pris | Autre app | `uvicorn app.main:app --reload --port 8001` et adapter le proxy Vite |

### Frontend

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Cannot find module` en TypeScript | `node_modules/` absent | `npm install` |
| `Failed to fetch /api/*` | Backend pas lancé | Lancer `uvicorn` dans un autre terminal |
| Écran blanc sur `/projects/abc` | URL invalide | Retourner à `/` via le bouton Retour |
| Les statuts ne changent pas dans l'UI | Polling pas encore implémenté (Epic 4) | Normal en V0, rafraîchir la page |

### Diagnostics Pyright dans VSCode

Si VSCode affiche plein d'erreurs `Import "app.xxx" could not be resolved` : **c'est un faux positif IDE**. Le code fonctionne à l'exécution (pytest passe, uvicorn démarre).

**Fix** : `Ctrl+Shift+P` → `Python: Restart Language Server`. Le fichier `backend/pyrightconfig.json` déclare la racine pour que Pyright résolve les imports correctement.

---

## Commandes de cycle de vie quotidien

Une fois le setup initial fait, les 2 commandes à connaître :

**Backend** (terminal 1) :
```bash
cd ai_project_manager/backend
source venv/Scripts/activate
uvicorn app.main:app --reload
```

**Frontend** (terminal 2) :
```bash
cd ai_project_manager/frontend
npm run dev
```

Et pour relancer les tests après modifications backend :
```bash
pytest -v
```

### Raccourci VSCode — lancer avec F5

Des configurations `.vscode/launch.json` sont fournies à la racine du projet. Ouvre le panneau **Run & Debug** (`Ctrl+Shift+D`), choisis une entrée dans le dropdown puis `F5` :

| Configuration | Effet |
|---|---|
| **Backend: FastAPI (uvicorn --reload)** | Démarre FastAPI avec hot-reload + debugger Python attaché (breakpoints dans `backend/app/**`) |
| **Backend: Pytest (all tests)** | Lance toute la suite pytest avec le debugger attaché |
| **Backend: Pytest (current file)** | Lance uniquement le fichier de test actuellement ouvert |
| **Frontend: Vite dev server** | Démarre Vite **et** ouvre Chrome sur `http://localhost:5173` avec les sourcemaps React/TSX |
| **Full stack: Backend + Frontend** | Compound : lance les deux en une seule pression de F5 |

Les tâches sous-jacentes sont définies dans `.vscode/tasks.json` (npm run dev, pytest, alembic, etc.) et sont aussi accessibles via `Ctrl+Shift+P` → `Tasks: Run Task`.

> ⚠️ Les launch configs pointent vers `backend/venv/Scripts/python.exe`. Si ton venv est ailleurs ou si tu préfères `uv`, adapte le champ `python` dans `.vscode/launch.json`.

---

## Architecture en un coup d'œil

```
┌──────────────────────────────────────────┐
│  Frontend React (localhost:5173)         │
│  ─ ProjectList (/) : CRUD projets        │
│  ─ ProjectView (/projects/:id) :         │
│    header + zone centrale + Chat 360px   │
└──────────────┬───────────────────────────┘
               │ fetch /api/* (proxy Vite)
               ▼
┌──────────────────────────────────────────┐
│  Backend FastAPI (localhost:8000)        │
│  ─ /api/projects (CRUD)                  │
│  ─ /api/projects/{id}/messages (chat)    │
│  ─ ScopingAgent : LLM + tool-use         │
│    → Epic / User Story / Task            │
└──────────────┬───────────────────────────┘
               │ async SQLAlchemy 2
               ▼
┌──────────────────────────────────────────┐
│  SQLite local (backend/ai_pm.db)         │
│  tables : projects, items, chat_messages │
└──────────────────────────────────────────┘
```

---

**Prochaine évolution** : branchement des vrais agents de dev/QA sur les items validés (Epic 4 → V1).
