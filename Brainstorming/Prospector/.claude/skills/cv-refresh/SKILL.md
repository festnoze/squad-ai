---
name: cv-refresh
description: Regenerate the 4 CV PDFs (FR/EN × short/full) from the cv/ render sources. Use when the user says /cv-refresh, edits their CV data, or PDFs are missing/stale.
---

# /cv-refresh — rebuild the CV PDFs

## Steps

1. Sanity-check the render sources: `cv\fr_short`, `cv\fr_full`, `cv\en_short`,
   `cv\en_full` each contain an `index.html` plus the data files it references
   (grep the `<script src=` tags). Report anything missing.
2. If the user changed content upstream in `..\CV\` (the canonical CV project),
   remind them the Prospector variants are enriched COPIES: propagate their
   edit into the relevant `cv\*\data\` files here (FR first, then mirror the
   change in the EN translation — natural English, not literal).
3. Run: `venv\Scripts\python.exe scripts\render_cv.py`
   (Edge headless first, Playwright fallback — the script handles it).
4. Verify each `assets\cv\cv_*.pdf`: exists, >10KB, and is text-based — extract
   text (e.g. `venv\Scripts\python.exe -c` with pypdf if installed, else open
   one PDF and eyeball) and confirm real selectable text came out, not blank
   pages: ATS compatibility depends on it.
5. Report: 4 PDFs with sizes + page counts, any variant that failed and why.

## Rules

- Never edit `..\CV\` (the user's canonical CV project) — Prospector owns only
  its `cv\` copies.
- EN variants must contain zero French UI labels — spot-check after any edit.
