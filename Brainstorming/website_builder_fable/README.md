# Website Builder Fable

A local-first, single-user web application to create and manage website projects.
Each project is one website: pages are built visually in a WYSIWYG editor
(selection + drag and drop), structured content is managed through a per-project
CMS (collections, entries, image assets), and pages can be previewed as
server-rendered HTML or exported as a standalone zip of the whole site.

- Backend: Python, FastAPI (async), SQLAlchemy + SQLite (aiosqlite), port 8300
- Frontend: React 18 + Vite 5, zustand, @dnd-kit, react-router, dev port 5300
- Spec: `SPEC.md`; design decisions: `docs/decisions-stack.md`,
  `docs/decisions-editor.md`, `docs/decisions-cms.md`; module contracts: `docs/CONTRACTS.md`

## Setup (Windows)

Prerequisites: Python 3.11+, Node.js 18+.

### Backend

Git Bash:

```
cd "C:/Dev/squad-ai/Brainstorming/website_builder_fable"
python -m venv backend/.venv
source backend/.venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

PowerShell equivalent:

```
cd C:\Dev\squad-ai\Brainstorming\website_builder_fable
python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt
```

### Frontend

```
cd frontend
npm install
```

## Run

Backend (from the `backend` folder, venv active):

```
uvicorn app.main:app --host 127.0.0.1 --port 8300 --reload
```

Frontend (from the `frontend` folder):

```
npm run dev
```

Open http://localhost:5300 (Vite proxies `/api` to http://localhost:8300).

Helper scripts (PowerShell): `scripts\run_backend.ps1` and `scripts\run_frontend.ps1`.

## Tests

Backend tests (venv active, from the `backend` folder):

```
pytest -q
```

## Data

Runtime data lives in `backend/data/` (SQLite db at `backend/data/app.db`, uploaded
images under `backend/data/uploads/{project_id}/`). Both locations are overridable
with the `WBF_DB_PATH` and `WBF_UPLOADS_DIR` env vars (used by the test suite).

## Conventions

- Backend port 8300, frontend dev port 5300, all API routes under `/api`.
- Python async functions are prefixed with "a" (e.g. `aget_project`), never `_async`.
- Never use the em-dash character (U+2014) in any produced content; use "-" or parentheses.
- All commands are non-interactive.

## Status

Final smoke test (2026-08-01): everything below verified working end to end.

- Backend test suite: 86 passed, 0 failed.
- `uvicorn app.main:app --port 8300` and `npm run dev` (port 5300) both start
  with the instructions above; http://localhost:5300 serves the app and the
  Vite proxy forwards `/api` to the backend.
- Verified through the live API: project creation, page creation, saving a
  real block tree (navbar, section with heading + text + button, footer),
  collection creation with text/richtext/date fields, entry creation, and
  server-rendered page preview HTML (heading and sanitized rich text present).
- Site export as zip verified by the backend verification pass.
- Sample data: the database (`backend/data/app.db`) contains a demo project
  "Demo Site" with a Home page (navbar/section/heading/text/button/footer
  block tree) and a "Blog Posts" collection (title, body richtext,
  published_on date) holding 2 entries. Open http://localhost:5300 after
  starting both servers to browse it.
- Known quirk: Vite uses `strictPort`, so if port 5300 is already taken by a
  stale dev server, `npm run dev` exits with "Port 5300 is already in use";
  kill the old process first.
