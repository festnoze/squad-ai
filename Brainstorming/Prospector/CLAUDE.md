# Prospector — project instructions

Autonomous-with-human-gate freelance prospection system for Etienne Millerioux
(Lead AI Engineer). Finds full-remote AI-engineering missions, scores them,
drafts custom applications (FR/EN) with the right CV PDF, queues them for human
review, dispatches approved ones, tracks replies and follow-ups.

## Golden rules (override everything else)

1. **Nothing is ever sent without explicit human approval.** The only sending
   paths are the /dispatch skill (email via `scripts/send_email.py`, capped)
   and a human click on platform forms. No agent may email, apply, bid, DM, or
   post — anywhere, ever.
2. **Truth only in applications.** Claims must trace to `config/profile.yaml`
   or `cv/`. No invented metrics, clients, or skills.
3. **Platforms are read-only for automation** (ToS + account-ban risk).
   Browser automation may search, read, and PREFILL forms — never submit.
4. **Language rule**: missions in France → French; UK/US/English-speaking
   environments → English. Nothing else.
5. **Caps are enforced in code** (`send_email.py` daily cap, writer draft cap
   in `config/targets.yaml`) — never bypass them, never work around exit code 2.

## Architecture

- Pipeline: scouts → SQLite (`data/prospector.db`) → scorer → writer →
  `data/queue/pending/` → **/review (human)** → `approved/` → /dispatch →
  `sent/` → tracker//follow-up.
- Agents (`.claude/agents/`): scout-boards, scout-platforms, scout-linkedin,
  scout-direct, scorer, writer, tracker.
- Skills (`.claude/skills/`): /prospect (full run), /review, /dispatch,
  /follow-up, /cv-refresh.
- Deterministic core (`scripts/`): db.py (all DB access — never touch SQLite
  directly), fetch_boards.py, send_email.py, check_replies.py, render_cv.py,
  report.py, login_setup.py.
- Configs (`config/`): profile.yaml (candidate truth), targets.yaml (sources,
  queries, caps), style.md (letter rules), review-feedback.md (grows from
  rejections — writer should read it when present).

## Conventions

- Always run Python through the venv: `venv\Scripts\python.exe scripts\<x>.py`
  (activate the venv first if opening a shell session).
- All DB access goes through `scripts/db.py` CLI (JSON in/out).
- Queue files: markdown with YAML frontmatter — the frontmatter is the
  machine-readable contract between writer, review, and dispatch. Preserve it.
- Async Python functions (if ever added): prefix names with `a` (aget_x), no
  `_async` suffix.
- Secrets live in `.env` only (gitignored). Never print or log the Gmail app
  password.
- `..\CV\` (sibling folder) is the user's canonical CV project: READ-ONLY.
  Prospector's enriched copies live in `cv/`.

## State machine (missions.status)

new → scored → drafted → queued → sent → replied → interview → won | lost
Any state → ignored (eliminated or user-rejected).
