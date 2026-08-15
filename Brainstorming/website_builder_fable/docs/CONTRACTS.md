# CONTRACTS - Website Builder Fable

Single source of truth for the 5 module agents. Where the three decision documents
(decisions-stack.md, decisions-editor.md, decisions-cms.md) disagree on details,
THIS file wins. Global rules still apply everywhere: no em-dash character (U+2014)
anywhere; Python async functions prefixed with "a" (never `_async`); venv activated
before any python/pytest command; all commands non-interactive; backend port 8300,
frontend dev port 5300, Vite proxy `/api -> http://localhost:8300`.

Reconciliation decisions (conflicts between the design docs, resolved here):
1. Block tree schema: the EDITOR document (decisions-editor.md section 1) is canonical
   for both frontend and backend renderer. Node keys are `id, type, props, style, children`
   (`style`, not `styles`). The root node is `{"id": "root", "type": "page", "props": {}, "style": {}, "children": []}`.
2. Collection list block type string is `"collectionList"` (camelCase, per the editor doc;
   NOT `collection_list` nor `collection-list`). Its props follow decisions-cms.md section 4:
   `{ collectionId, limit, itemTemplate: { title, text, image } }` (slot values are field keys or null).
3. The Page model's JSON column is named `content` and the pages API uses the field name
   `content` for the block tree (matches the editor autosave contract `PUT ... {"content": tree}`).
4. Style keys are camelCase (paddingTop, backgroundColor, ...), per decisions-editor.md 1.2.
   The server renderer consumes these camelCase keys.
5. Asset API response shape follows decisions-cms.md (fields: id, project_id, filename, path,
   url, mime, size, created_at). URL form: `/api/uploads/{project_id}/{stored_filename}`.
6. The asset library screen lives under the CMS wildcard route
   (`/projects/:projectId/cms/assets`), owned by frontend-cms (App.jsx defines only the
   three top-level routes listed in section 5 and is frozen).

---

## 1. REST API (all under /api, JSON unless stated)

Conventions: integer ids; ISO 8601 UTC timestamps with trailing "Z"; POST create -> 201 with
the created resource; PUT -> 200 with the updated resource; DELETE -> 204 empty body.
Errors: `raise HTTPException(status_code, detail="message")` -> `{"detail": "message"}`.
404 "Project not found" / "Page not found" / "Collection not found" / "Entry not found" /
"Asset not found"; 409 for slug conflicts; 400 for domain validation failures; automatic 422
keeps FastAPI's standard list shape, except entry validation which returns
`{"detail": [{"field": "<key>", "message": "..."}]}` with status 422.
The existence chain is always verified (project -> collection -> entry, etc.).

### 1.1 Projects (owner: backend-core, router app/api/projects.py)

Shapes:
- Theme: `{"primary_color": "#2563eb", "font": "system-ui", "base_spacing": 16}`
- ProjectOut: `{"id": 1, "name": "My Site", "slug": "my-site", "description": "", "theme": Theme, "created_at": "...", "updated_at": "..."}`

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | /api/projects | - | 200 [ProjectOut] |
| POST | /api/projects | `{"name" (required), "slug"?, "description"?, "theme"?}` (slug auto-derived from name when omitted) | 201 ProjectOut; 409 duplicate slug |
| GET | /api/projects/{project_id} | - | 200 ProjectOut; 404 |
| PUT | /api/projects/{project_id} | any subset of `{"name", "slug", "description", "theme"}` | 200 ProjectOut; 404; 409 |
| DELETE | /api/projects/{project_id} | - | 204 (cascades pages, collections, entries, assets incl. files) |
| GET | /api/projects/{project_id}/export | - | 200 application/zip (all rendered pages + assets/; index.html = home page, others {page_slug}.html; asset URLs rewritten to relative assets/); 404 |

### 1.2 Pages (owner: backend-core, router app/api/pages.py)

PageOut: `{"id": 1, "project_id": 1, "name": "Home", "slug": "home", "is_home": false, "content": <block tree, section 2>, "created_at": "...", "updated_at": "..."}`

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | /api/projects/{project_id}/pages | - | 200 [PageOut] |
| POST | /api/projects/{project_id}/pages | `{"name" (required), "slug"?, "is_home"?}` (content initialized to the empty root of section 2; first page of a project becomes home when is_home omitted) | 201 PageOut; 409 duplicate slug in project |
| GET | /api/projects/{project_id}/pages/{page_id} | - | 200 PageOut; 404 |
| PUT | /api/projects/{project_id}/pages/{page_id} | any subset of `{"name", "slug", "is_home", "content"}` (the editor autosave sends `{"content": tree}`; setting is_home true clears it on the previous home page) | 200 PageOut; 404; 409 |
| POST | /api/projects/{project_id}/pages/{page_id}/duplicate | - (empty body) | 201 PageOut (copy named "{name} copy", new unique slug, is_home false) |
| DELETE | /api/projects/{project_id}/pages/{page_id} | - | 204 |
| GET | /api/projects/{project_id}/pages/{page_id}/preview | - | 200 text/html (full standalone document rendered server-side); 404 |

### 1.3 Collections and entries (owner: backend-cms, router app/api/cms.py)

Shapes (decisions-cms.md sections 1-3 are authoritative for details):
- FieldDescriptor: `{"key": "title", "label": "Title", "type": "text|richtext|number|boolean|date|image|select", "required": false, "options": []}`
- CollectionOut: `{"id", "project_id", "name", "slug", "fields": [FieldDescriptor], "entry_count", "created_at", "updated_at"}`
- EntryOut: `{"id", "collection_id", "data": {key: value}, "created_at", "updated_at"}` (data normalized: every current schema key present, missing -> null; keys not in schema excluded)

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | /api/projects/{project_id}/collections | - | 200 [CollectionOut] |
| POST | /api/projects/{project_id}/collections | `{"name" (required), "slug"?, "fields"?}` | 201 CollectionOut; 409 slug; 422 bad descriptor |
| GET | /api/projects/{project_id}/collections/{collection_id} | - | 200 CollectionOut; 404 |
| PUT | /api/projects/{project_id}/collections/{collection_id} | any subset of `{"name", "slug", "fields"}` (fields replaced wholesale) | 200 CollectionOut; 404; 409; 422 |
| DELETE | /api/projects/{project_id}/collections/{collection_id} | - | 204 (cascades entries) |
| GET | /api/projects/{project_id}/collections/{collection_id}/entries?limit=50&offset=0 | - | 200 `{"total": n, "items": [EntryOut]}` (order created_at DESC, id DESC; limit max 200) |
| POST | /api/projects/{project_id}/collections/{collection_id}/entries | `{"data": {key: value}}` | 201 EntryOut; 422 `{"detail": [{"field", "message"}]}` |
| GET | /api/projects/{project_id}/collections/{collection_id}/entries/{entry_id} | - | 200 EntryOut; 404 |
| PUT | /api/projects/{project_id}/collections/{collection_id}/entries/{entry_id} | `{"data": {...}}` (full replacement) | 200 EntryOut; 404; 422 |
| DELETE | /api/projects/{project_id}/collections/{collection_id}/entries/{entry_id} | - | 204 |

Field value storage/validation rules: decisions-cms.md section 2 (unknown keys rejected,
required rules per type, image field holds an asset id int or a url string, select value
must be in options).

### 1.4 Assets (owner: backend-cms, router app/api/assets.py)

AssetOut: `{"id": 12, "project_id": 3, "filename": "photo.png", "path": "3/a1b2c3d4_photo.png", "url": "/api/uploads/3/a1b2c3d4_photo.png", "mime": "image/png", "size": 48213, "created_at": "..."}`

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | /api/projects/{project_id}/assets | multipart/form-data, single part named `file` | 201 AssetOut; 415 non-image (`image/*` only); 413 over 10 MB |
| GET | /api/projects/{project_id}/assets | - | 200 [AssetOut] (created_at DESC, id DESC) |
| DELETE | /api/projects/{project_id}/assets/{asset_id} | - | 204 (row + disk file; entries referencing it untouched) |

File serving: main.py mounts StaticFiles at `/api/uploads` over the uploads root
(env-var overridable, see app/db.py: UPLOADS_DIR). Stored filename on disk:
`{uuid4hex[:8]}_{sanitized_original_name}` under `{uploads_root}/{project_id}/`.

### 1.5 Infrastructure endpoints (owner: scaffold, frozen)

| Method | Path | Response |
|---|---|---|
| GET | /api/health | 200 `{"status": "ok"}` |
| GET | /api/uploads/{project_id}/{filename} | static file (StaticFiles mount) |

---

## 2. Block tree JSON schema (canonical, shared editor + renderer)

Every node has exactly five keys, all always present when serialized:

```json
{
  "id": "string (nanoid(10); the root's id is the literal \"root\")",
  "type": "string (one of the block types below)",
  "props": {},
  "style": {},
  "children": []
}
```

Block types (14):
`page, section, row, column, heading, text, image, button, spacer, divider, navbar, footer, form, collectionList`

- `page` is the root only (never in palette, never selectable/deletable). A new page's
  content is `{"id": "root", "type": "page", "props": {}, "style": {}, "children": []}`.
- Containment: page accepts section/navbar/footer; section accepts
  row/heading/text/image/button/spacer/divider/form/collectionList; row accepts column only;
  column accepts the section set (nested rows allowed once); all other types are leaves.
- Default props and default style per type: decisions-editor.md section 1.3 table.
- Allowed style keys (camelCase, numbers mean px):
  `paddingTop, paddingRight, paddingBottom, paddingLeft, marginTop, marginRight, marginBottom, marginLeft, color, backgroundColor, fontSize, fontWeight, textAlign, width, maxWidth, height, borderRadius, gap`
- `collectionList` props: `{"collectionId": int|null, "limit": 6 (clamped 1..50), "itemTemplate": {"title": key|null, "text": key|null, "image": key|null}}`.
  Server rendering rules: decisions-cms.md section 4 (never 500 on stale bindings).
- The backend stores the tree opaquely in Page.content; the server renderer
  (app/services/render.py) consumes this exact schema, escapes all text via html.escape,
  and sanitizes the `text` block html to the whitelist b/i/u/em/strong/a/br/p/ul/ol/li.

---

## 3. Zustand editor store shape (frontend-editor agent)

File: `src/features/editor/editorStore.js` (JS project; the .ts shapes in
decisions-editor.md apply as documentation). Exact shape:

```
state:
  projectId: string | null
  pageId: string | null
  tree: BlockNode                  (root page node)
  selectedId: string | null
  past: BlockNode[]                (undo stack, max 50, oldest dropped)
  future: BlockNode[]              (redo stack)
  dirty: boolean
  saving: boolean
  lastSavedAt: string | null
  device: "desktop" | "tablet" | "mobile"

actions (exact names):
  loadPage(projectId, pageId)      async
  select(id)
  insertBlock(parentId, index, node)
  removeBlock(id)
  moveBlock(id, newParentId, newIndex)
  duplicateBlock(id)
  updateBlockProps(id, patch)
  updateBlockStyle(id, patch)
  undo()
  redo()
  setDevice(d)
  savePage()                       async, immediate PUT {"content": tree}
  markSaved()                      internal
```

Behavior (autosave debounce 1500 ms, history coalescing 800 ms, snapshot pattern,
DEVICE_WIDTHS = desktop 1200 / tablet 768 / mobile 375): decisions-editor.md section 4.

---

## 4. File ownership map (STRICT; do not touch files you do not own)

backend-core agent owns:
- backend/app/models_core.py
- backend/app/api/projects.py
- backend/app/api/pages.py
- backend/app/services/render.py
- backend/app/services/export.py
- backend/tests/test_projects.py
- backend/tests/test_pages.py
- backend/tests/test_render.py

backend-cms agent owns:
- backend/app/models_cms.py
- backend/app/api/cms.py
- backend/app/api/assets.py
- backend/tests/test_cms.py
- backend/tests/test_assets.py

frontend-projects agent owns:
- frontend/src/features/projects/** (everything under that folder)

frontend-editor agent owns:
- frontend/src/features/editor/** (everything under that folder)

frontend-cms agent owns:
- frontend/src/features/cms/** (everything under that folder)

NOBODY else edits (scaffold-owned, frozen; module agents may READ them):
- backend/app/main.py
- backend/app/db.py
- backend/tests/conftest.py
- backend/requirements.txt, backend/pytest.ini
- frontend/src/App.jsx
- frontend/package.json
- frontend/src/api/client.js
- frontend/src/styles.css
- frontend/vite.config.js, frontend/index.html, frontend/src/main.jsx

Shared helper modules an agent needs beyond these paths go INSIDE its owned folder
(e.g. the editor's tree utils live in src/features/editor/treeUtils.js). Backend agents
may add extra modules only under names not owned by the other agent (e.g. backend-core
may add app/schemas_core.py; backend-cms may add app/cms/validation.py and
app/schemas_cms.py). Do not both edit app/schemas.py: it does not exist; each agent
creates its own schema module.

---

## 5. Exported component contract (frontend)

App.jsx (frozen) imports exactly these default exports:

| Route | File | Export |
|---|---|---|
| `/` | frontend/src/features/projects/ProjectsPage.jsx | default export React component |
| `/projects/:projectId/editor/:pageId?` | frontend/src/features/editor/EditorPage.jsx | default export React component |
| `/projects/:projectId/cms/*` | frontend/src/features/cms/CmsPage.jsx | default export React component |

- The CMS route is a wildcard: CmsPage defines its own nested `<Routes>` for
  collections / schema / entries / entry form / assets screens
  (paths relative to /projects/:projectId/cms).
- Each page reads route params with useParams. Navigation between features uses
  react-router `Link`/`useNavigate` with the absolute paths above.
- All HTTP goes through frontend/src/api/client.js: `apiGet(path)`, `apiPost(path, data)`,
  `apiPut(path, data)`, `apiDelete(path)`, `uploadFile(path, file)`. Non-2xx rejects with
  `ApiError { status, detail }`. Paths are relative `/api/...` strings.
- Shared UI primitives are the CSS classes in src/styles.css (btn, btn-primary, btn-danger,
  input, select, textarea, field, panel, card, table, page, topbar, empty-state, muted, mono).

---

## 6. Verification commands (Git Bash, non-interactive)

Backend:
```
source "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv/Scripts/activate"
cd "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend"
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8300
```

Frontend:
```
cd "C:/Dev/squad-ai/Brainstorming/website_builder_fable/frontend"
npm run build
npm run dev
```
