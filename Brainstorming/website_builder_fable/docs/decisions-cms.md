# CMS Design Document - Website Builder Fable

Source spec: `C:\Dev\squad-ai\Brainstorming\website_builder_fable\SPEC.md`
Scope: per-project CMS (collections, entries, assets), its REST API under `/api`, the binding contract for the editor's "collection list" block, and the CMS UI screens.

Decisions made by this agent (spec left them open; simplest consistent choice picked):
- Primary keys are SQLite INTEGER autoincrement (not UUIDs).
- Timestamps are ISO 8601 UTC strings with a trailing "Z" (e.g. `2026-08-01T14:03:22Z`), generated server-side.
- `Collection.fields` and `Entry.data` are stored as JSON in TEXT columns (SQLite), serialized/deserialized in the repository layer.
- Uploaded files live on disk under `backend/data/uploads/{project_id}/`; the DB stores metadata only. Files are served via a StaticFiles mount at `/api/uploads`, so the Vite proxy (`/api -> http://localhost:8300`) covers them with zero extra config.
- Deletes cascade: deleting a project deletes its collections, entries, assets (rows and files); deleting a collection deletes its entries. Deleting an asset does NOT touch entries that reference it (renderer falls back to empty).
- Collection slugs are unique per project, auto-derived from name when not provided.
- No pagination beyond a simple `limit`/`offset` query pair on entry list (local-first, single user).
- All async Python functions are prefixed with `a` (e.g. `acreate_collection`), never `_async`.

---

## 1. Data model

Three tables. SQLAlchemy (async, aiosqlite) or raw aiosqlite; either way the shapes below are authoritative.

### Table `collections`

| Column      | Type    | Constraints                                        |
|-------------|---------|----------------------------------------------------|
| id          | INTEGER | PK autoincrement                                   |
| project_id  | INTEGER | FK -> projects.id, NOT NULL, ON DELETE CASCADE     |
| name        | TEXT    | NOT NULL (e.g. "Blog Posts")                       |
| slug        | TEXT    | NOT NULL; UNIQUE(project_id, slug)                 |
| fields      | TEXT    | NOT NULL, JSON array of field descriptors, default `[]` |
| created_at  | TEXT    | NOT NULL, ISO UTC                                  |
| updated_at  | TEXT    | NOT NULL, ISO UTC                                  |

Slug rule: lowercase, `[a-z0-9-]+`, derived from name (`"Blog Posts" -> "blog-posts"`) when the client omits it; on conflict within the project return 409.

### Table `entries`

| Column        | Type    | Constraints                                       |
|---------------|---------|----------------------------------------------------|
| id            | INTEGER | PK autoincrement                                   |
| collection_id | INTEGER | FK -> collections.id, NOT NULL, ON DELETE CASCADE  |
| data          | TEXT    | NOT NULL, JSON object keyed by field `key`         |
| created_at    | TEXT    | NOT NULL, ISO UTC                                  |
| updated_at    | TEXT    | NOT NULL, ISO UTC                                  |

`data` example for a Blog Posts schema: `{"title": "Hello", "body": "<p>Hi</p>", "published": true, "date": "2026-08-01", "cover": 12, "category": "news"}`.

### Table `assets`

| Column      | Type    | Constraints                                       |
|-------------|---------|----------------------------------------------------|
| id          | INTEGER | PK autoincrement                                   |
| project_id  | INTEGER | FK -> projects.id, NOT NULL, ON DELETE CASCADE     |
| filename    | TEXT    | NOT NULL, original upload filename                 |
| path        | TEXT    | NOT NULL, relative path under uploads root, e.g. `3/a1b2c3d4_photo.png` |
| mime        | TEXT    | NOT NULL (e.g. `image/png`)                        |
| size        | INTEGER | NOT NULL, bytes                                    |
| created_at  | TEXT    | NOT NULL, ISO UTC                                  |

Stored filename on disk: `{uuid4hex[:8]}_{sanitized_original_name}` inside `backend/data/uploads/{project_id}/`. Sanitize: keep `[A-Za-z0-9._-]`, replace the rest with `-`.

Computed (not stored) `url` returned by the API: `/api/uploads/{path}` (e.g. `/api/uploads/3/a1b2c3d4_photo.png`). The backend mounts `StaticFiles(directory="backend/data/uploads")` at `/api/uploads`.

### Field descriptor shape (elements of `Collection.fields`)

```json
{
  "key": "title",
  "label": "Title",
  "type": "text",
  "required": true,
  "options": []
}
```

- `key`: machine key, `[a-z][a-z0-9_]*`, unique within the collection. Auto-derived from label in the UI (`"Cover Image" -> "cover_image"`); immutable once entries exist is NOT enforced (simplest), but the UI warns via copy in the schema builder.
- `label`: human label shown in forms and table headers.
- `type`: one of `text | richtext | number | boolean | date | image | select`.
- `required`: boolean, default false.
- `options`: list of strings; only meaningful for `select`, must be non-empty when type is `select`; stored as `[]` for other types.

The order of descriptors in the `fields` array IS the display order (schema builder reorder just rewrites the array).

---

## 2. Field types: storage and validation

All values live inside `Entry.data` (JSON). Server-side validation runs on entry create/update against the collection's current schema. Validation failures return 422 with body `{"detail": [{"field": "<key>", "message": "<human message>"}]}`.

| Type     | JSON storage in `data`                | Accepted input                                   | Validation |
|----------|----------------------------------------|--------------------------------------------------|------------|
| text     | string                                 | any string                                       | must be `str`; if required, non-empty after strip |
| richtext | string (plain HTML string)             | HTML string from the UI's simple editor          | must be `str`; if required, non-empty after stripping tags is NOT checked (keep it simple: non-empty string). No server-side sanitization in v1 (local-first single user); renderer inserts it as-is |
| number   | int or float                           | JSON number                                      | must be `int` or `float` (bool explicitly rejected); required means "key present and not null" |
| boolean  | true / false                           | JSON boolean                                     | must be `bool`; a required boolean only requires presence (false is valid) |
| date     | ISO date string `YYYY-MM-DD`           | string                                           | must parse with `datetime.date.fromisoformat` |
| image    | int (asset id) OR string (external url)| asset id number, or `http(s)://...` / `/api/uploads/...` string | if int: asset must exist and belong to the same project, else 422; if string: must be non-empty |
| select   | string                                 | string                                           | must be one of the field's `options`, else 422 |

General rules:
- Unknown keys in `data` (not in schema) are rejected with 422 (`"unknown field"`). This keeps data honest after schema edits are the user's responsibility.
- Missing optional fields are stored as absent or null; the API normalizes to `null` in responses for every schema key so the frontend form can bind without existence checks.
- Required check: key present, not null, and per-type non-empty rule above.
- Validation lives in one module: `backend/app/cms/validation.py`, function `validate_entry_data(fields: list[dict], data: dict) -> list[dict]` returning error dicts (empty list = valid). Pure sync function (no IO except the image asset check, which is done by the service before calling it: the service pre-fetches project asset ids into a set and passes it as `asset_ids: set[int]` parameter).

---

## 3. REST API (all under `/api`, JSON unless stated)

Existence chain is always verified: project must exist (404 `{"detail": "Project not found"}`), collection must exist AND belong to the project (404), entry must belong to the collection (404). Asset id in entry data must belong to the project (422, see above).

### Collections (nested under projects)

**GET `/api/projects/{project_id}/collections`** -> 200
```json
[ {"id": 1, "project_id": 3, "name": "Blog Posts", "slug": "blog-posts",
   "fields": [ {"key": "title", "label": "Title", "type": "text", "required": true, "options": []} ],
   "entry_count": 4,
   "created_at": "2026-08-01T14:03:22Z", "updated_at": "2026-08-01T14:03:22Z"} ]
```
`entry_count` is computed with one grouped COUNT query (used by the collections list screen).

**POST `/api/projects/{project_id}/collections`** -> 201
Request: `{"name": "Blog Posts", "slug": "blog-posts" (optional), "fields": [ ...field descriptors... ] (optional, default [])}`
Response: full collection object (as above, `entry_count: 0`).
Errors: 409 duplicate slug in project; 422 invalid field descriptor (bad type, bad key format, duplicate keys, select without options).

**GET `/api/projects/{project_id}/collections/{collection_id}`** -> 200, full collection object.

**PUT `/api/projects/{project_id}/collections/{collection_id}`** -> 200
Request: any subset of `{"name", "slug", "fields"}` (partial update semantics; omitted keys unchanged). Replacing `fields` wholesale is how the schema builder saves (add/remove/reorder all become one PUT). Existing entries are NOT migrated or revalidated (simplest); removed fields' values remain in `data` but are dropped from API responses at read time (responses only include current schema keys).
Response: full collection object.

**DELETE `/api/projects/{project_id}/collections/{collection_id}`** -> 204, cascades entries.

### Entries (nested under collections)

**GET `/api/projects/{project_id}/collections/{collection_id}/entries?limit=50&offset=0`** -> 200
```json
{"total": 4, "items": [
  {"id": 7, "collection_id": 1,
   "data": {"title": "Hello", "body": "<p>Hi</p>", "published": true, "date": "2026-08-01", "cover": 12, "category": "news"},
   "created_at": "...", "updated_at": "..."} ]}
```
Order: `created_at DESC, id DESC`. Defaults: `limit=50` (max 200), `offset=0`. `data` is normalized to include every current schema key (missing -> null) and to exclude keys no longer in the schema.

**POST `/api/projects/{project_id}/collections/{collection_id}/entries`** -> 201
Request: `{"data": { ...field key -> value... }}`
Response: full entry object. Errors: 422 validation (shape in section 2).

**GET `/api/projects/{project_id}/collections/{collection_id}/entries/{entry_id}`** -> 200, full entry object.

**PUT `/api/projects/{project_id}/collections/{collection_id}/entries/{entry_id}`** -> 200
Request: `{"data": { ... }}` (full replacement of `data`, validated as a whole; the entry form always submits the complete object, so no merge logic).
Response: full entry object. Errors: 422.

**DELETE `/api/projects/{project_id}/collections/{collection_id}/entries/{entry_id}`** -> 204.

### Assets (nested under projects)

**POST `/api/projects/{project_id}/assets`** -> 201, `multipart/form-data` with a single part named `file`.
- Accepts mime types starting with `image/` only; otherwise 415 `{"detail": "Only image uploads are supported"}`.
- Max size 10 MB; otherwise 413.
- Response:
```json
{"id": 12, "project_id": 3, "filename": "photo.png",
 "path": "3/a1b2c3d4_photo.png", "url": "/api/uploads/3/a1b2c3d4_photo.png",
 "mime": "image/png", "size": 48213, "created_at": "..."}
```

**GET `/api/projects/{project_id}/assets`** -> 200, array of asset objects (same shape, includes computed `url`), ordered `created_at DESC, id DESC`.

**DELETE `/api/projects/{project_id}/assets/{asset_id}`** -> 204. Deletes DB row and disk file (missing file is ignored). Entries referencing the id are untouched.

**File serving**: `app.mount("/api/uploads", StaticFiles(directory=<uploads root>), name="uploads")`. No per-asset GET endpoint needed.

### FastAPI layout and naming

- Routers: `backend/app/api/collections.py`, `backend/app/api/entries.py`, `backend/app/api/assets.py`, each an `APIRouter` included with prefix `/api`.
- Handlers (async, "a" prefix): `alist_collections`, `acreate_collection`, `aget_collection`, `aupdate_collection`, `adelete_collection`, `alist_entries`, `acreate_entry`, `aget_entry`, `aupdate_entry`, `adelete_entry`, `aupload_asset`, `alist_assets`, `adelete_asset`.
- Pydantic models in `backend/app/cms/schemas.py`: `FieldDescriptor`, `CollectionCreate`, `CollectionUpdate`, `CollectionOut`, `EntryCreate` (`data: dict`), `EntryOut`, `EntriesPage`, `AssetOut`. `FieldDescriptor` enforces the key regex, the type enum, and `options` non-empty for select via a model validator.

---

## 4. "Collection list" block binding

Block type string: `"collection-list"`. Stored in the page block tree like any other block.

Block `props` shape (authoritative contract between editor, properties panel, and renderer):

```json
{
  "collectionId": 1,
  "limit": 6,
  "itemTemplate": {
    "title": "title",
    "text": "excerpt",
    "image": "cover"
  }
}
```

- `collectionId`: integer id of a collection in the same project; `null` when unbound (renders a placeholder).
- `limit`: max entries to render, default 6, clamped 1..50.
- `itemTemplate`: maps the three fixed slots to field keys of the bound collection. Any slot may be `null`/absent (slot skipped). Slot semantics:
  - `title` slot: value rendered as plain text inside `<h3 class="cl-item-title">` (HTML-escaped).
  - `text` slot: if the mapped field type is `richtext`, the stored HTML string is inserted as-is inside `<div class="cl-item-text">`; any other type is HTML-escaped text (numbers/booleans/dates stringified, date as-is `YYYY-MM-DD`).
  - `image` slot: resolved to a URL: if value is an int, look up the asset and use its `/api/uploads/{path}` url (missing asset -> slot skipped); if a string, use it directly. Rendered as `<img class="cl-item-image" src="..." alt="">` (alt = title slot value if present, else empty).

Properties panel behavior in the editor: a collection dropdown (fetched from `GET .../collections`), a limit number input, and three slot dropdowns each listing the bound collection's field keys (image slot lists only `image` fields, title/text slots list any field, richtext suggested for text). Changing `collectionId` resets `itemTemplate` slots to null.

Server-side renderer (in the preview/export renderer module, function `arender_collection_list_block(block, project_id, deps) -> str`):
1. If `collectionId` is null or the collection does not exist / belongs to another project: render `<div class="collection-list collection-list-empty">No collection bound</div>` (never raise; preview must not 500 on a stale binding).
2. Fetch entries: same query as the list endpoint, `ORDER BY created_at DESC, id DESC LIMIT {limit}`.
3. Pre-fetch the project's assets into `{id: url}` once per page render (shared cache passed down, so N collection-list blocks do 1 asset query).
4. Emit:
```html
<div class="collection-list">
  <div class="cl-item"> [image?] [title?] [text?] </div>
  ... repeated per entry ...
</div>
```
5. Zero entries: emit `<div class="collection-list collection-list-empty">No entries</div>`.
6. CSS (in the exported/preview stylesheet): `.collection-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--spacing, 16px); }`, `.cl-item-image { width: 100%; height: auto; display: block; }`. Style props on the block (padding, background, etc.) apply to the outer `.collection-list` div exactly like other blocks.

Editor canvas rendering: the editor fetches up to `limit` entries client-side (same endpoints) and renders the same markup so WYSIWYG matches preview; while unbound it shows a dashed placeholder card.

---

## 5. CMS UI screens (React, under the project shell)

Route base: `/projects/:projectId/cms`. All screens live in `frontend/src/cms/`. Data access through a thin `frontend/src/api/cms.js` (or .ts) module wrapping fetch against the endpoints in section 3.

### 5.1 Collections list - `/projects/:projectId/cms`
- Table/cards of collections: name, slug, field count, `entry_count`, updated_at.
- Row actions: "Entries" (goes to 5.3), "Schema" (goes to 5.2), "Delete" (confirm dialog, then DELETE).
- "New collection" button: inline dialog with Name (required) and Slug (auto-filled from name, editable); POST then navigate to the schema builder.
- Empty state: "No collections yet" with the New collection button.

### 5.2 Schema builder - `/projects/:projectId/cms/collections/:collectionId/schema`
- Header: collection name (inline-editable) and slug (read-only display).
- Vertical list of field rows, order = `fields` array order. Each row: drag handle (reorder), Label input (typing updates `key` suggestion only while the field is new/unsaved), Key (small monospace text, editable for new fields, shown read-only with a "changing keys orphans existing values" tooltip once saved), Type picker (dropdown with the 7 types), Required checkbox, Remove button.
- When Type = select: an options editor appears in the row (tag-style list of strings, add/remove; at least one required to save).
- "Add field" button appends a row (default: type text, required false).
- Reorder: drag and drop within the list (same dnd approach as the page editor palette; plain HTML5 drag events are acceptable), or up/down arrow buttons as the simple fallback (implement the arrows; dnd optional polish).
- Save: single "Save schema" button doing `PUT .../collections/{id}` with the full `fields` array (and name if changed). Client-side validation mirrors server rules (duplicate keys, key regex, select options non-empty) and shows inline errors. Dirty-state indicator; navigating away with unsaved changes prompts confirm.

### 5.3 Entries table - `/projects/:projectId/cms/collections/:collectionId/entries`
- Table columns: first 4 schema fields (in order) plus Updated. Cell rendering by type: text/select as-is (truncated 80 chars), richtext as tag-stripped truncated text, number/date as-is, boolean as a check/cross glyph, image as a 40px thumbnail (resolved via the project asset list, cached).
- Row click opens the entry form (5.4). Row hover shows a Delete icon (confirm dialog).
- "New entry" button opens the entry form in create mode.
- Pagination: simple Prev/Next using `limit=50` and `offset`, with "X-Y of total".
- Empty state: "No entries yet".

### 5.4 Entry form - `/projects/:projectId/cms/collections/:collectionId/entries/:entryId` (and `/new`)
- Generated entirely from the schema `fields` array, in order. Widget per type:
  - text: `<input type="text">`
  - richtext: minimal rich editor: a `contentEditable` div with a small toolbar (bold, italic, H2, bullet list, link) using `document.execCommand`; value read/written as the HTML string. (Decision: no external editor dependency; execCommand is deprecated but universally working and keeps the build dependency-free.)
  - number: `<input type="number">` (empty -> null)
  - boolean: checkbox
  - date: `<input type="date">` (value already ISO `YYYY-MM-DD`)
  - image: thumbnail preview + "Choose image" button opening the shared Asset Picker modal (5.5a) + "Use URL" toggle revealing a text input for external urls + Clear button. Stored value: asset id (number) or url string.
  - select: `<select>` from `options`, with an empty choice when not required.
- Required fields marked with `*`; 422 responses map `detail[].field` to inline errors under the matching widget.
- Buttons: Save (POST or PUT, then back to table), Cancel (back, confirm if dirty), Delete (edit mode only).

### 5.5 Asset library - `/projects/:projectId/assets`
- Responsive grid of image cards: thumbnail (the `/api/uploads/...` url), filename, human-readable size, upload date; Delete icon with confirm.
- "Upload" button opening the native file picker (`accept="image/*"`, multiple allowed; uploads sequentially, each a separate POST) plus drag-and-drop of files onto the grid area doing the same.
- Upload progress: simple per-file spinner card; on success the card becomes the asset card; on error a toast with the API detail message.
- Empty state: "No assets yet" with the Upload button.

### 5.5a Asset Picker (shared modal component, not a route)
- Used by: CMS image field (5.4) and the page editor's image block properties panel.
- Same grid as 5.5 plus an Upload button inside the modal; clicking an asset selects it and closes the modal, returning the full asset object `{id, url, filename}` to the caller. Caller decides what to store (CMS field stores `id`; the editor image block stores `url`).

### Navigation
- The project dashboard's "open CMS" action routes to `/projects/:projectId/cms`.
- Within a project, a left sidebar (or top tabs) exposes: Pages (editor), CMS, Assets. CMS screens show a breadcrumb: Project name > CMS > Collection name > (Schema | Entries | Entry).

---

## Testing notes for downstream agents
- Backend pytest (httpx `AsyncClient` + `ASGITransport` against the app, per spec) must cover: collection CRUD incl. 409 duplicate slug and 422 bad field descriptors; entry CRUD incl. one 422 per field type violation, unknown-key rejection, required enforcement, select option enforcement, cross-project image asset rejection; asset upload happy path (multipart), non-image 415, list, delete; entry list normalization (removed schema field disappears from responses, missing optional returns null); collection cascade delete removes entries.
- Always activate the venv first in Git Bash: `source "C:/Dev/squad-ai/Brainstorming/website_builder_fable/backend/.venv/Scripts/activate"`.
- Never use the em-dash character anywhere in produced files.
