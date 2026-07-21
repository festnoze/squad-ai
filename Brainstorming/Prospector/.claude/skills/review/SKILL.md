---
name: review
description: Interactively walk the pending application queue — show each draft, let the user approve/edit/reject, move files and update the DB. Use when the user says /review or wants to validate drafted applications.
---

# /review — human validation of drafted applications

Walk `data\queue\pending\` with the user. Every application requires their
explicit decision — this is the system's core safety gate.

## Steps

1. List pending drafts sorted by score (frontmatter). If empty: say so,
   suggest /prospect, stop.
2. Announce the batch: "N drafts pending — reviewing one by one."
3. Per draft, present compactly:
   - **Mission**: title — company — score — url — language — channel — CV variant.
   - **Recipient** (email channel): the `to` address and subject.
   - **Message**: full body, verbatim.
   Then ask (AskUserQuestion works well): **Approve** / **Edit** / **Reject** /
   **Skip** / **Stop review**.
4. Apply the decision:
   - **Approve** → move file to `data\queue\approved\`;
     `venv\Scripts\python.exe scripts\db.py set-status --id <mission_id> --status queued`.
   - **Edit** → apply the user's changes to the message (rewrite respecting
     `config/style.md` and their instruction), show the result, re-ask.
   - **Reject** → move to `data\queue\rejected\`; mission status `ignored`;
     ask one short question: "why?" — record the answer as a line in
     `config\review-feedback.md` (create if missing) so the writer/scorer
     improve next runs.
   - **Skip** → leave in pending.
5. Wrap up: counts per decision, then — if anything was approved — ask whether
   to run /dispatch now.

## Rules

- Never approve on the user's behalf; never batch-approve without an explicit
  "approve all" instruction from the user (and even then, still show each
  subject+recipient line first).
- Every rejection reason goes to `config\review-feedback.md` — this file is
  read by nobody automatically, but /prospect's writer step should be pointed
  to it when it exists (mention it in your wrap-up).
