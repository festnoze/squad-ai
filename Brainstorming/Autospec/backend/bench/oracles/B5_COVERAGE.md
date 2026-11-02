# B5 Relais Support: what the hidden oracle automates

Source of the criteria: `docs/validation/support-client/02_requirements_verification.md` (57 ids).
Oracle: `bench/oracles/B5.py`. Brief: `bench/briefs/B5-relais-support.md`.

## Summary

- **35 of 57 criteria are automated** (19 complete, 16 partial), **22 are `NOT_AUTOMATED`**.
- A `NOT_AUTOMATED` criterion is returned as a failed check (detail `NOT_AUTOMATED`): it
  stays in the denominator, so a perfect product scores at most 35/57 (61.4 %). Compare B5
  runs on the automated part (`passed / 35`); `python -m bench.report` shows the count.
- "Partial" means the oracle checks the behaviour observable from outside the product (the
  X evidence of the referential) and not its review (R) or visual (V) part. A partial pass
  is not a PASS in the sense of the referential, which requires every listed proof.

## What the oracle may touch

- HTTP only, through the interface fixed by the brief: section 7 of the specification plus
  the **bench annex** at the end of the brief.
- The `python -m relais_support create-admin` command of the annex.
- The SQLite file at `RELAIS_DB`: a read-only byte scan (SEC-03, SEC-05: no clear password,
  argon2id parameters, no raw session token) and one held exclusive lock (ARC-03).
- Never the product's code, tests, logs or Docker image.

## Why the brief has a bench annex

The specification is copied verbatim (only its two em dashes became hyphens). It leaves open
what any black-box probe needs first: the package and start command, where the database
lives, how the configured origin is set, how the first admin is created and how credentials
reach that command, whether `/auth/...` sits under `/api`, the JSON field names, where the
CSRF token is returned, and the names of the filter parameters. Without fixing them, no
authenticated criterion could be automated. The annex fixes only those, adds no route and
changes no rule; the factory receives it with the specification. `--demo` fixtures stay
unconstrained: the oracle builds its own data through the API instead.

## Run phases

1. No server: `OPS-01` (environment rebuilt by the bench), then `create-admin` without
   credentials, with credentials, and again (facts for `SEC-01`).
2. Server on `RELAIS_DB`: admin login, five accounts created through the API (2 clients,
   2 agents, a second admin), then every other automated check. At most 5 failed logins,
   under the 10 per 60 s rate limit.
3. Same database, new process: `OPS-04` and the replay part of `FUN-07`.
4. Fresh database and process: `create-admin` on a second blank base (`SEC-01`), then
   `SEC-04` (identical failures, then the rate limit with a fresh counter).

## Per criterion

| ID | Gate | Coverage | What is checked, or why not |
|---|---|---|---|
| SEC-01 | B | partial | create-admin refused without credentials (variables absent, stdin closed), created with them, refused when an admin exists, works on a second blank base; its output never contains the password; blank base + bootstrap = exactly 1 account; no password or hash in login, `/auth/me` and account DTOs. Not checked: `--demo` fixtures (command and manifest not fixed), secrets in image or logs. |
| SEC-02 | B | complete | Normalized duplicate email -> 409, also against a deactivated account; a single account listed; two synchronized creations of one email -> one 201 and one 409. |
| SEC-03 | B | complete | Password lengths 13/14/128/129 -> 422/201/201/422; spaces and Unicode accepted and never trimmed; no truncation (a password differing only after 72 characters is refused); byte scan: no clear password, argon2id with m >= 19456 and t >= 2, as many distinct hashes as accounts (salt). |
| SEC-04 | B | partial | Fresh server: wrong password, unknown email and deactivated account give the same 401 code and message; 10 failures in the window (X-Forwarded-For varied, one success in between) then a correct login -> 429 with Retry-After. Not checked: dummy hash timing, another IP (single loopback), injectable clock. |
| SEC-05 | B | partial | Login cookie HttpOnly, SameSite=Lax, Path=/, value of at least 43 characters, a new token per login, absent from the body, Max-Age at most 8 h, raw token absent from the database file. Not checked: Secure under HTTPS, the 8 h expiry itself (needs a clock), the random generator (R), localStorage (V). |
| SEC-06 | B | complete | Logout 204 with an expired cookie and the session dead; repeated logout without a valid session -> 204 with an expired cookie, refused (403) without Origin; deactivate then reactivate: the old session stays 401 on `/auth/me`, tickets and dashboard; a new login works. |
| SEC-07 | B | partial | Valid session without, with an invalid or with another session's CSRF token -> 403 and nothing created; logout without CSRF -> 403 and the session survives; Origin absent, `null` or foreign -> 403 on login and on a mutation; anonymous mutation -> 401; CORS never reflects a foreign origin or `*` with credentials; a legitimate mutation succeeds. Not checked: the browser side (V). |
| SEC-08 | B | complete | Anonymous on the 13 business routes -> 401; client and agent on account routes -> 403, client on the directory -> 403; PUT and DELETE on a ticket and DELETE on an account are not 2xx and change nothing. |
| SEC-09 | B | complete | Alice on Bob's ticket (GET, PATCH, messages GET and POST, history) -> 404 identical to a missing id, Bob's ticket unchanged; Bob's ticket absent from Alice's list, search and dashboard; Alice reusing Bob's idempotency key gets her own ticket. |
| SEC-10 | B | partial | API: the client sees neither the content, the id nor the history events of internal notes (mixed ticket, internal-only ticket, page_size 1, list, dashboard, search); the client sees fewer history events than the staff. Not checked: HTML, browser state, account switch in the browser (V). |
| SEC-11 | B | complete | Ticket creation with owner_id, status, version, priority, assignee_id, created_at or an unknown field -> 422; client internal note -> 403; message with author_id, created_at or an unknown field -> 422; account PATCH with role or email -> 422; ticket PATCH with title, owner_id or an unknown field -> 422; account creation with an unknown field -> 422. |
| SEC-12 | B | partial | `<script>`, `<img onerror>` and apostrophes stored and returned literally in titles, descriptions, public messages, notes and display names; SQL-like search text is literal. Not checked: browser execution (V), code review of `dangerouslySetInnerHTML` and SQL (R). |
| SEC-13 | B | complete | Deactivating the last active admin -> 409; three synchronized races (two admins deactivating each other, then themselves) always leave an active admin. |
| SEC-14 | B | complete | Role and email PATCH -> 422 and unchanged; agent cannot create an account; client cannot read the directory; directory paginated, lists active agents and admins only, no client, no email of a client, no secret-looking field; a deactivated agent leaves the directory, stays listed as inactive, its message remains. |
| SEC-15 | B | partial | `Cache-Control: no-store` on login, `/auth/me`, ticket list, detail, messages, dashboard and accounts; no stack trace, SQL or private path in any error body seen during the run (including DB_BUSY). Not checked: log files (R), a forced database error other than lock contention. |
| FUN-01 | M | complete | Client creation 201 with owner from the session, open, normal, unassigned, version 1; agent and admin -> 403; title 4/5/120/121, description 19/20/5000/5001, blank and padded values, line breaks kept. |
| FUN-02 | M | partial | Each client sees exactly its own tickets, staff and admin see all, totals agree, missing id -> 404. Uses the oracle's own data instead of the 6/12 demo fixture (fixture command not fixed); the UI part (no stale sheet) is V. |
| FUN-03 | M | complete | Priority staff only and strict; assignment to a client, an inactive agent or an unknown id refused without write; to an agent, an admin or null accepted; on a closed ticket assignment changes -> 409, priority allowed; closing with an assignment change -> 409. |
| FUN-04 | B | complete | The 4x4 matrix: 5 effective transitions, 4 identities without version change, 7 forbidden transitions -> 409 without write; preconditions (assignee for in_progress, public staff reply for resolved, an internal note or a client message is not enough). |
| FUN-05 | M | complete | Client replies on its ticket, an unassigned agent replies, staff annotates; client internal note -> 403; another client -> 404; no status change; author and UTC date from the server; body 0/blank/1/5000/5001; closed ticket -> 409 for every new message. |
| FUN-06 | B | partial | Three rounds of two synchronized PATCH on one version -> one 200, one 409 VERSION_CONFLICT, one new version and one history event; three close/message races -> exactly one success, state consistent. Not checked: the database audit beyond history totals, the UI draft (V). |
| FUN-07 | B | complete | Ticket and message replays (same key and payload -> 200 same id, one object), conflicts on content, visibility and target -> 409 IDEMPOTENCY_CONFLICT, keys scoped per user, simultaneous retries -> one object, rights before replay, replay allowed after closing while a new key is refused, replays still answered after a server restart. |
| FUN-08 | B | NOT_AUTOMATED | The core of the criterion is a rollback under a fault injected between the business write and its audit, which the specification allows only through a test fixture inside the product. |
| FUN-09 | B | complete | Deactivating the assignee: its session dies, its in_progress and closed tickets become unassigned with a new version and history event, in_progress kept and listed as unassigned; reactivation reassigns nothing and revives no session; three assignment/deactivation races never leave a ticket assigned to an inactive agent. |
| FUN-10 | M | complete | ASCII case-insensitive search, exact Unicode, literal `%`, `_` and apostrophe, empty q, 100/101 characters, no search in messages or notes, scope applied before pagination. |
| FUN-11 | M | complete | 55 tickets: page_size 1/20 default/50/51/0, page 0, page beyond the end, a walk by pages of 7 without duplicate or omission, order (updated_at DESC, id DESC), AND filters (status, priority, assigned_to_me, unassigned), the two staff filters together -> 422, unknown status -> 422, client using a staff filter refused. |
| FUN-12 | M | complete | Dashboard shape, zero for a new client, client and staff totals equal to the lists and to the per-status filters, update after a mutation. |
| FUN-13 | M | complete | Identical PATCH changes neither version nor history; stale version on a no-op -> 409 VERSION_CONFLICT; missing expected_version or no field -> 422; invalid multi-field PATCH writes nothing; a public message and an internal note each add exactly one version. |
| ARC-01 | M | NOT_AUTOMATED | Architecture mapping: code review (R) only. |
| ARC-02 | B | NOT_AUTOMATED | Needs direct inserts into the database and schema inspection; the oracle only scans bytes and holds a lock. |
| ARC-03 | B | partial | With an exclusive lock held on `RELAIS_DB`, a write answers 503 DB_BUSY within 9 s, writes nothing, and the same request succeeds once released. Transaction design (R) is not reviewed; distinct connections are probed through FUN-06. |
| ARC-04 | B | NOT_AUTOMATED | The specification fixes neither a migration command nor where the schema version is visible. Persistence across a restart is covered by OPS-04. |
| ARC-05 | M | NOT_AUTOMATED | Query counting (N+1) and query plans need instrumentation inside the product. |
| ARC-06 | M | partial | Every 401/403/404/409/422/429/503 seen carries `{error: {code, message}}`; an OpenAPI document at `/openapi.json` or `/api/openapi.json` lists the 15 routes. Not checked: DTO and entity separation (R). |
| ARC-07 | M | complete | The five lists are paginated with page_size at most 50 and reject page_size 51/0 and page 0 with 422; accounts sorted by email; the ticket detail embeds no collection. |
| ARC-08 | M | partial | Ticket, message and account dates are ISO 8601 UTC with an explicit offset; messages sorted by (created_at, id). Not checked: clock-controlled expiry, independence from the local time zone. |
| ARC-09 | M | NOT_AUTOMATED | Frontend code review (R). |
| UX-01 | M | NOT_AUTOMATED | Browser journey (V). |
| UX-02 | M | NOT_AUTOMATED | Loading, empty, error and network states in a browser (V). |
| UX-03 | M | NOT_AUTOMATED | Keyboard, focus and modal behaviour (V). |
| UX-04 | M | NOT_AUTOMATED | Screenshots at 1280 and 390 px (V). |
| UX-05 | B | NOT_AUTOMATED | Browser cache and draft isolation between accounts (V); the API refusals are in SEC-08. |
| UX-06 | M | NOT_AUTOMATED | Out-of-order responses and URL state in a browser (V). |
| UX-07 | M | NOT_AUTOMATED | Double clicks and conflict dialog in a browser (V); server idempotency is in FUN-07. |
| UX-08 | M | partial | The built bundle calls relative `/api/` paths and hard-codes no backend localhost address. Not checked: the visual distinction of internal notes (V). |
| TST-01 | B | NOT_AUTOMATED | Review of the product's own tests. The bench runs them in a clean environment as M5, outside M6. |
| TST-02 | M | NOT_AUTOMATED | Requirement to test mapping review (R). |
| TST-03 | M | NOT_AUTOMATED | Coverage measurement of the product's suites with their tooling. |
| TST-04 | B | NOT_AUTOMATED | Review of the product's tests and fixtures (R). |
| TST-05 | B | NOT_AUTOMATED | Six end-to-end browser journeys (V). |
| TST-06 | M | NOT_AUTOMATED | Mutation of a copy of the product and of its tests. |
| OPS-01 | B | partial | `uv sync --locked`, `npm ci` and `npm run build` succeed from the locks in the bench's copy. Not checked: the Docker image (the bench does not run Docker). |
| OPS-02 | B | NOT_AUTOMATED | Inspection of the Docker image. |
| OPS-03 | B | partial | `GET /api/health` 200 without account data, anonymous API 401, `GET /` serves the built UI, bootstrap command works. Not checked: on the Docker image, a real browser journey. |
| OPS-04 | B | partial | A process restart on the same `RELAIS_DB` stands in for a container recreation: ticket, public message, internal note, history, accounts and idempotency keys survive. |
| OPS-05 | M | NOT_AUTOMATED | README and dependency audit review. |
| OPS-06 | D | NOT_AUTOMATED | Timing diagnostic; the bench records its own durations. |
