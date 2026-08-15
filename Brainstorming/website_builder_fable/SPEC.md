# Website Builder Fable - Product Specification

## Overview
A full web application to create and manage website projects. Each project represents one website. Users build pages visually with a WYSIWYG editor (selection + drag and drop) and manage structured content through a per-project CMS.

- Backend: Python (FastAPI, async)
- Frontend: React (Vite)
- Local-first tool, single user, SQLite storage

## Core Features

### 1. Projects management
- CRUD on projects (name, slug, description, theme settings: primary color, font, base spacing)
- Dashboard listing all projects with quick actions (open editor, open CMS, preview, delete)
- Each project owns its pages, CMS collections, and assets

### 2. WYSIWYG page editor
- Pages list per project (create, rename, duplicate, delete, set home page)
- A page is a tree of blocks stored as JSON
- Block palette with at least: section, row (columns), heading, text (rich-ish), image, button, spacer/divider, navbar, footer, form (name/email/message), collection list (binds CMS data)
- Drag and drop: from palette onto canvas, and reorder/move existing blocks within the tree
- Click to select a block: selection outline, breadcrumb of ancestors, keyboard delete/duplicate
- Properties panel for the selected block: content props (text, image url, link) and style props (colors, typography, padding/margin, alignment, width, background)
- Undo / redo
- Responsive preview switch (desktop / tablet / mobile widths)
- Autosave or explicit save of the block tree to the backend

### 3. CMS
- Per-project collections (example: Blog Posts, Team Members)
- Field types: text, richtext, number, boolean, date, image, select
- Collection schema builder UI (add/remove/reorder fields)
- Entries CRUD with a table view and an edit form generated from the schema
- The editor's "collection list" block binds a collection and renders entries with a simple item template

### 4. Assets
- Image upload endpoint and per-project asset library
- Asset picker used by image block and CMS image fields

### 5. Preview / publish
- Server-side render of a page's block tree to standalone HTML+CSS
- Preview route: GET /api/projects/{project_id}/pages/{page_id}/preview returns rendered HTML
- Export endpoint producing a zip of the whole rendered site (all pages + assets)

## Hard constraints
- Backend port 8300, frontend dev port 5300, Vite proxy /api -> http://localhost:8300
- Windows dev machine; everything must run with non-interactive commands
- Python async functions/methods prefixed with "a" (aget_project); never an _async suffix
- Never use the em-dash character (U+2014) in any produced content (code, comments, docs, UI text); use "-" or parentheses
- Backend venv at backend/.venv, activated before any python/pytest run
- Backend tests with pytest (httpx AsyncClient against the app), meaningful coverage of API routes

## Acceptance criteria
- pytest passes in backend
- npm run build passes in frontend
- Both servers start; creating a project, adding blocks in the editor, saving, creating a collection with entries, and previewing a page all work end to end through the API
- README.md documents setup and run commands for Windows
