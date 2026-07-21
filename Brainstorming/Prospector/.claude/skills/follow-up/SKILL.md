---
name: follow-up
description: Detect replies, then draft polite relances for applications silent beyond the configured delay — drafts go to the pending queue for review like any application. Use when the user says /follow-up or asks about relances/replies.
---

# /follow-up — replies & relances

## Steps

1. Run the `tracker` agent: reply scan (`scripts\check_replies.py`), funnel
   stats, follow-ups due. Surface replies FIRST — a positive reply changes the
   user's day; relances can wait.
2. For each application due a relance (sent > `caps.followup_after_days` days,
   no reply, `followup_count < caps.max_followups` — from `config/targets.yaml`):
   - Re-read the ORIGINAL sent message in `data\queue\sent\` (context and
     language must match).
   - Draft the relance per the "Follow-up messages" section of
     `config/style.md` (40-70 words, one new element from profile.yaml, same CTA).
   - Write it to `data\queue\pending\<date>_<mission-id>_<company>_followup<N>.md`
     with the same frontmatter shape (channel/to/subject: `Re: <original>`).
3. Relances go through the normal `/review` → `/dispatch` cycle. Never send
   directly from here. On dispatch, bookkeeping adds:
   `db.py update-application --id N --set followup_count=<n+1>,last_followup_at=<now>`.
4. Wrap up: replies found (positive/negative/ambiguous), relances drafted,
   applications now exhausted (max follow-ups reached → suggest marking lost:
   `db.py set-status --id X --status lost` after user confirms).

## Rules

- Max `caps.max_followups` relances per application, ever. Silence after that
  is an answer.
- A reply — even a rejection — cancels all pending relances for that
  application: check the queue and remove any obsolete relance draft (tell the
  user).
