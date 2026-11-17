# Autospec v2 frontend

French web UI of the v2 factory (`docs/v2/CONTRACTS.md` section 9.2), built against the HTTP API
of section 9.1. React 19, Vite 8, TypeScript, plain CSS; no UI library.

```
npm ci              # from package-lock.json
npm run dev         # http://127.0.0.1:5400, proxies /api to http://127.0.0.1:8400
npm test            # vitest + Testing Library (fetch and EventSource are mocked)
npm run build       # tsc --noEmit, then dist/ (served at / by `python -m autospec.core serve`)
```

Start the API with `python -m autospec.core serve [--fake]` from `backend/`.

Layout:

- `src/api.ts`: typed client of every endpoint, field names mirror `core/models.py`.
- `src/App.tsx`, `src/route.ts`: hash routing, `#/` (projects) and `#/projects/<id>`.
- `src/useEvents.ts`: live journal, SSE on `/stream`, index-based polling of `/events?after=N`
  when the stream fails or the browser has no EventSource. A hidden tab closes its stream and
  reopens it with `?after=<cursor>` once visible (a browser allows only six HTTP/1.1
  connections per host); a 404 stops polling and the view says the project is gone.
- `src/components/ErrorBoundary.tsx`: an unexpected response shape shows a message, not a blank page.
- `src/components/`: project list and creation form, project view (phase, cost, error, automatic
  resume banner, resume / stop / delete), stories table with criteria and acceptance nodeids,
  events log, file tree with a read-only viewer, per-story diff.
- `src/test/`: fetch mock routed by `METHOD /path`, controllable fake EventSource, fixtures.

Windows: run Vite and Vitest from a long path; an 8.3 short path such as `C:\Users\E6FB4~1.MIL`
breaks them.
