# TECH STACK DECISION - Website Builder Fable

Status: FINAL. Later agents follow this document blindly. Do not renegotiate versions, ports, paths, or conventions.

Project root: `C:/Dev/squad-ai/Brainstorming/website_builder_fable` (referred to as `<ROOT>` below). Windows machine; Bash tool is Git Bash; prefer forward slashes in all paths and commands.

Spec source: `<ROOT>/SPEC.md`.

Global rules (apply to every file and command):
- NEVER use the em-dash character (U+2014) anywhere: code, comments, docs, commit text, UI strings. Use "-" or parentheses.
- Python async functions/methods are prefixed with "a" (e.g. `aget_project`, `acreate_page`, `arender_page_html`). Never an `_async` suffix.
- Backend venv lives at `<ROOT>/backend/.venv`. Before ANY python/pytest command in Git Bash: `source "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv/Scripts/activate"`.
- All commands non-interactive (pass all flags explicitly, no wizards, no prompts).
- Backend port 8300. Frontend dev port 5300. Vite proxies `/api` to `http://localhost:8300`.

---

## 1. Backend stack and requirements.txt

Python: use the machine's default `python` (3.11+ assumed). Create venv with `python -m venv "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv"`.

Chosen libraries (all versions verified to exist on PyPI):
- FastAPI 0.115.12 (app framework, async)
- uvicorn[standard] 0.34.0 (ASGI server)
- SQLAlchemy[asyncio] 2.0.41 (ORM, async engine; the `[asyncio]` extra guarantees greenlet is installed)
- aiosqlite 0.21.0 (async SQLite driver)
- pydantic 2.11.7 (schemas / validation; FastAPI 0.115 is pydantic-v2 native)
- python-multipart 0.0.20 (required by FastAPI for multipart file uploads on the assets endpoint)
- pytest 8.3.5, pytest-asyncio 0.26.0, httpx 0.28.1 (tests)

Decision notes:
- No template engine (no jinja2). Server-side rendering is plain Python string building (section 5).
- No alembic. Schema is created at startup with `Base.metadata.create_all` via the async engine (local-first single-user tool; simplest option consistent with the spec).
- No aiofiles. Uploaded files are small local writes; write bytes synchronously inside the endpoint (acceptable for a local single-user tool; keeps the pin list minimal).
- httpx 0.28 removed the `app=` shortcut: tests MUST use `httpx.ASGITransport(app=app)` with `httpx.AsyncClient(transport=..., base_url="http://test")`.
- Zip export uses stdlib `zipfile` + `io.BytesIO` (no extra dependency).

### Full content of `backend/requirements.txt`

```
fastapi==0.115.12
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.41
aiosqlite==0.21.0
pydantic==2.11.7
python-multipart==0.0.20
pytest==8.3.5
pytest-asyncio==0.26.0
httpx==0.28.1
```

Install (Git Bash, non-interactive):

```
python -m venv "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv"
source "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv/Scripts/activate"
python -m pip install --upgrade pip
pip install -r "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/requirements.txt"
```

Run server (from `<ROOT>/backend`, venv active):

```
uvicorn app.main:app --host 127.0.0.1 --port 8300 --reload
```

### pytest configuration

Create `backend/pytest.ini`:

```
[pytest]
asyncio_mode = auto
testpaths = tests
```

With `asyncio_mode = auto`, plain `async def test_...` functions run without decorators. Test names themselves are NOT subject to the "a" prefix rule (they are pytest entry points named `test_*`); all other async functions are.

---

## 2. Backend layout

```
backend/
  .venv/                      (virtualenv, never committed)
  requirements.txt
  pytest.ini
  data/                       (runtime data, gitignored; created on startup if missing)
    app.db                    (SQLite database file)
    uploads/                  (uploaded assets)
      {project_id}/           (one folder per project, files stored as {asset_id}{ext})
  app/
    __init__.py
    main.py                   (FastAPI app factory, CORS, router registration, startup schema create, /api/uploads static mount)
    db.py                     (async engine, async_sessionmaker, Base, aget_session dependency, ainit_db)
    models_core.py            (Project, Page, Asset SQLAlchemy models)
    models_cms.py             (Collection, Entry SQLAlchemy models)
    schemas.py                (all pydantic v2 request/response models)
    api/
      __init__.py
      projects.py             (router: /api/projects)
      pages.py                (router: /api/projects/{project_id}/pages, includes /preview)
      cms.py                  (router: /api/projects/{project_id}/collections and .../entries)
      assets.py               (router: /api/projects/{project_id}/assets, upload + list + delete)
    services/
      __init__.py
      render.py               (block tree JSON -> HTML string, pure functions)
      export.py               (whole-site zip build, uses render.py)
  tests/
    __init__.py
    conftest.py               (app + ASGITransport AsyncClient fixture, fresh temp SQLite per test session)
    test_projects.py
    test_pages.py
    test_cms.py
    test_assets.py
    test_render_export.py
```

Fixed decisions:
- SQLite file location: `<ROOT>/backend/data/app.db`. Database URL: `sqlite+aiosqlite:///<absolute path>`. Compute the absolute path in `db.py` as `Path(__file__).resolve().parent.parent / "data" / "app.db"` so it works regardless of CWD. Tests override it with a temp file via an env var `WBF_DB_PATH` (db.py reads `os.environ.get("WBF_DB_PATH")` first).
- Uploads folder: `<ROOT>/backend/data/uploads/{project_id}/`. Same `Path(__file__)`-relative computation, overridable via env var `WBF_UPLOADS_DIR`.
- Uploaded files are served by mounting `StaticFiles(directory=<uploads dir>)` at `/api/uploads` in `main.py`; an asset's public URL is `/api/uploads/{project_id}/{filename}` and is returned by the assets API.
- Models (SQLAlchemy 2.0 declarative, `Mapped[...]` / `mapped_column`):
  - `models_core.Project`: id (int PK), name, slug (unique), description, theme (JSON: {"primary_color","font","base_spacing"}), created_at, updated_at.
  - `models_core.Page`: id, project_id (FK, cascade delete), name, slug, is_home (bool), blocks (JSON: block tree, default `{"type":"root","children":[]}`), created_at, updated_at.
  - `models_core.Asset`: id, project_id (FK), filename, original_name, content_type, size, url, created_at.
  - `models_cms.Collection`: id, project_id (FK), name, slug, fields (JSON: ordered list of `{"key","label","type","options"}` where type is one of text|richtext|number|boolean|date|image|select), created_at, updated_at.
  - `models_cms.Entry`: id, collection_id (FK, cascade delete), data (JSON dict keyed by field key), created_at, updated_at.
  - JSON columns use `sqlalchemy.JSON` (stored as TEXT in SQLite). Enable `PRAGMA foreign_keys=ON` via an engine `connect` event in db.py so cascade deletes work.
- `db.py` exposes: `engine`, `async_session` (async_sessionmaker), `Base`, `async def aget_session()` (FastAPI dependency yielding an `AsyncSession`), `async def ainit_db()` (create data dirs + `Base.metadata.create_all`). `main.py` calls `ainit_db()` in a lifespan handler.

---

## 3. Frontend stack

React 18 + Vite 5 (JavaScript, no TypeScript: simplest option consistent with the spec). Scaffold by writing files directly (no `npm create vite` wizard). All versions verified to exist on npm.

### Full content of `frontend/package.json`

```json
{
  "name": "website-builder-fable-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@dnd-kit/core": "6.3.1",
    "@dnd-kit/sortable": "10.0.0",
    "@dnd-kit/utilities": "3.2.2",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.30.0",
    "zustand": "4.5.7"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "4.3.4",
    "vite": "5.4.19"
  }
}
```

Notes: `@dnd-kit/sortable` 10.0.0 is the release line compatible with `@dnd-kit/core` 6.3.1; `@dnd-kit/utilities` is included because sortable transforms need `CSS.Transform.toString`. Zustand v4 API: `create((set, get) => ...)` hooks; use it for the editor store (block tree, selection, undo/redo stacks as arrays of serialized trees).

### Full content of `frontend/vite.config.js`

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5300,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8300',
        changeOrigin: true
      }
    }
  }
})
```

Other fixed frontend decisions:
- Entry: `frontend/index.html` -> `frontend/src/main.jsx` -> `<App />` with `createBrowserRouter` (react-router v6, data router API not required; plain `<RouterProvider>` or `<BrowserRouter>` with `<Routes>` is fine; pick `<BrowserRouter>` for simplicity).
- Routes: `/` (dashboard), `/projects/:projectId/editor/:pageId?`, `/projects/:projectId/cms`, `/projects/:projectId/assets`.
- All backend calls go through relative `/api/...` fetch URLs so the Vite proxy handles them; no hardcoded host in frontend code.
- Install and build (non-interactive): `cd "C:/Dev/squad-ai/Brainstorming/website_builder_fable/frontend" && npm install && npm run build`.

---

## 4. API conventions

- Every route is under `/api`. Routers are declared with prefixes and included from `main.py`: `app.include_router(projects.router, prefix="/api")` etc.
- Plural resource names, nested under their owner:
  - `GET/POST /api/projects`, `GET/PUT/DELETE /api/projects/{project_id}`
  - `GET/POST /api/projects/{project_id}/pages`, `GET/PUT/DELETE /api/projects/{project_id}/pages/{page_id}`, `POST /api/projects/{project_id}/pages/{page_id}/duplicate`, `GET /api/projects/{project_id}/pages/{page_id}/preview` (returns HTML), `GET /api/projects/{project_id}/export` (returns zip)
  - `GET/POST /api/projects/{project_id}/collections`, `GET/PUT/DELETE /api/projects/{project_id}/collections/{collection_id}`
  - `GET/POST /api/projects/{project_id}/collections/{collection_id}/entries`, `GET/PUT/DELETE .../entries/{entry_id}`
  - `GET/POST /api/projects/{project_id}/assets` (POST is multipart/form-data with field name `file`), `DELETE /api/projects/{project_id}/assets/{asset_id}`
- JSON request/response bodies everywhere except: asset upload (multipart), preview (text/html), export (application/zip via `Response` or `StreamingResponse`).
- IDs are integers. Timestamps are ISO 8601 strings in responses. POST create returns 201 with the created resource; DELETE returns 204 with empty body; PUT returns 200 with the updated resource.
- Error shape: the FastAPI default, kept deliberately. All handler-raised errors use `raise HTTPException(status_code=..., detail="message")`, producing `{"detail": "message"}`. 404 for missing resources ("Project not found", "Page not found", ...), 409 for slug conflicts, 400 for domain validation failures (e.g. unknown field key in an entry). Automatic 422 validation errors keep FastAPI's standard `{"detail": [{loc, msg, type}, ...]}` list shape. Frontend treats any non-2xx as an error and reads `detail` (string or array).
- CORS: add `CORSMiddleware` allowing `http://localhost:5300` (harmless with the proxy, useful if the frontend is ever opened directly).

---

## 5. Server-side preview rendering (services/render.py)

Pure Python, zero template engine. The renderer walks the page's block tree JSON and returns a complete HTML document string.

- Block tree shape (canonical, shared with the frontend editor): every block is `{"id": str, "type": str, "props": dict, "styles": dict, "children": [blocks]}`. The page root is `{"type": "root", "children": [...]}`. Types: `section`, `row`, `column`, `heading`, `text`, `image`, `button`, `spacer`, `divider`, `navbar`, `footer`, `form`, `collection_list`.
- Public API of `render.py`:
  - `def render_styles(styles: dict) -> str` - maps the style props dict (camelCase or snake_case keys as stored by the editor; pick snake_case keys like `background_color`, `padding`, `text_align`, `font_size`, `width`, `margin`) to a CSS inline declaration string. Only whitelisted keys are emitted; values are sanitized (reject `;`, `}`, newlines).
  - `def render_block(block: dict, ctx: RenderContext) -> str` - dispatch on `block["type"]` via a dict of small per-type functions; unknown types render an HTML comment `<!-- unknown block: type -->` and their children.
  - `async def arender_page_html(session, project, page) -> str` - the only async entry point; it prefetches CMS entries for every `collection_list` block in the tree (one query per bound collection), builds a `RenderContext` (theme, entries by collection id, asset base url), then calls the sync tree walk and wraps the result in a full document: `<!doctype html><html><head><meta charset>...<style>` (a tiny reset plus theme CSS custom properties: `--primary-color`, `--font`, `--base-spacing` from `project.theme`) `</style></head><body>...</body></html>`.
- All text content passes through `html.escape` before interpolation. The `text` block's rich-ish content is stored as a restricted HTML subset produced by the editor; the renderer sanitizes it by escaping everything except a whitelist of tags (`b, i, u, em, strong, a, br, p, ul, ol, li`) implemented with a small regex-free `html.parser.HTMLParser` subclass in render.py (stdlib only).
- Layout blocks: `section` renders `<section style="...">children</section>`; `row` renders a flex container `display:flex;gap:...`; `column` renders a flex child. `collection_list` renders `<div class="collection-list">` with one item per entry, substituting `{{field_key}}` placeholders in its simple item template prop against the entry's `data` dict (escaped).
- Images reference asset URLs as stored (`/api/uploads/{project_id}/{filename}`). The preview endpoint returns this HTML directly with `HTMLResponse`.
- `services/export.py`: `async def aexport_site_zip(session, project) -> bytes` renders every page with `arender_page_html`, rewrites asset URLs from `/api/uploads/{project_id}/` to relative `assets/`, writes `index.html` (home page) plus `{page_slug}.html` and copies the project's upload files into `assets/` inside an in-memory `zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED)`, returns the bytes; the endpoint responds with `Response(content=..., media_type="application/zip", headers={"Content-Disposition": "attachment; filename={slug}.zip"})`.

---

## 6. Testing conventions (backend)

- `tests/conftest.py`: set `WBF_DB_PATH` and `WBF_UPLOADS_DIR` env vars to a tmp location BEFORE importing `app.main`; provide an async `client` fixture: `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`; call `ainit_db()` in the fixture setup.
- Run tests (Git Bash): `source "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv/Scripts/activate" && cd "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend" && pytest -q`.
- Coverage expectation: at least one happy-path and one error-path (404/409/400) test per router, plus a render test (block tree in, HTML substrings out) and an export test (zip opens, contains index.html).

## Decisions log (open questions I resolved myself)
1. Project root resolves to `C:/Dev/squad-ai/Brainstorming/website_builder_fable` (the literal "undefined" in the task was an unsubstituted variable; SPEC.md lives there).
2. No alembic, no jinja2, no aiofiles, no TypeScript: simplest options consistent with the spec.
3. CMS field definitions stored as a JSON list on Collection (no Field table); entry values stored as a JSON dict on Entry.
4. Error shape is FastAPI's default `{"detail": ...}`.
5. SQLite at `backend/data/app.db`, uploads at `backend/data/uploads/{project_id}/`, both env-var overridable for tests, uploads served at `/api/uploads` via StaticFiles.
6. Zustand v4 (4.5.7) rather than v5: mature v4 hook API, matches the "zustand" requirement with the least churn.
7. Integer primary keys, ISO 8601 timestamps, 201/200/204 status conventions as stated above.
