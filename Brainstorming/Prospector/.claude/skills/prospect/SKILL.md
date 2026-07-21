---
name: prospect
description: Run the full prospection pipeline — scouts (boards, platforms, LinkedIn, direct) → scorer → writer → digest. Produces drafts in the pending review queue; sends nothing. Use when the user says /prospect or asks to hunt for missions.
---

# /prospect — full prospection run

Orchestrate one complete discovery-to-draft cycle. Nothing is ever sent by this
skill — output is drafts in `data\queue\pending\` awaiting `/review`.

## Steps

1. **Preflight** (fail fast, tell the user what's missing):
   - `venv\Scripts\python.exe scripts\db.py init` (idempotent).
   - Check `assets\cv\*.pdf` exist (else suggest `/cv-refresh`).
   - Check `browser_profile\` exists (else platform/LinkedIn scouts will be
     skipped — note it, don't block).
2. **Scout fan-out** — launch as parallel subagents (single message, multiple
   Agent calls): `scout-boards`, `scout-direct`, and if `browser_profile\`
   exists: `scout-platforms`, `scout-linkedin`. Each upserts into the DB
   itself. Collect their reports; a failed scout never aborts the run.
   Honor `enabled:` flags in `config/targets.yaml`.
3. **Score** — run the `scorer` agent (after all scouts finish).
4. **Draft** — run the `writer` agent (caps come from `config/targets.yaml`).
5. **Digest** — run `venv\Scripts\python.exe scripts\report.py`, then summarize
   for the user:
   - new missions by source, scored/passed-threshold counts,
   - drafts created (company — title — channel — language — score),
   - replies/follow-ups pending (from report.py),
   - problems (expired logins, failing sources),
   - reminder: `X drafts waiting — run /review to approve them.`

## Rules

- This skill NEVER sends applications, never clicks apply, never emails.
- Total run should stay under ~15 minutes; prefer skipping a slow source over
  blowing the budget (scouts have their own per-run caps).
- If the pending queue already holds ≥ 15 unreviewed drafts, skip the writer
  step and tell the user to /review first — drafting into a stale queue wastes
  the best missions.
