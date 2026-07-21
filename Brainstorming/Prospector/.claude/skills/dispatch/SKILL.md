---
name: dispatch
description: Send approved applications — emails via Gmail SMTP with the right CV PDF attached; platform/LinkedIn applications via browser prefill for the user's final click. Use when the user says /dispatch or asks to send approved applications.
---

# /dispatch — send what the user approved

Process `data\queue\approved\` only. Files in `pending\` are untouchable.

## Steps

1. List approved drafts. If empty: say so, stop.
2. Group by channel and announce the plan (N emails, M platform prefills...).
3. **Email channel** — per draft:
   - Extract body (below the `## Message` heading) to a temp file (scratchpad).
   - `venv\Scripts\python.exe scripts\send_email.py --to <to> --subject <subject>
     --body-file <tmp> --attach assets\cv\<cv>.pdf --bcc-self`
   - The script hard-enforces the daily cap: on exit code 2 (cap reached),
     STOP sending emails, report how many remain for tomorrow.
   - On success: move file to `data\queue\sent\`;
     `db.py update-application --id <app_id> --set sent_at=<now>`;
     `db.py set-status --id <mission_id> --status sent`.
4. **Platform / LinkedIn / form channels** — per draft:
   - Open the mission URL in a HEADED Playwright window on `browser_profile\`
     (small scratchpad script), navigate to the application form, prefill the
     message text (and upload the CV PDF if the form takes one).
   - Tell the user: "Prefilled — please review in the opened window and click
     send yourself." WAIT for their confirmation in chat.
   - Confirmed sent → same bookkeeping as email (move file, update DB).
     Not sent → move the file back to `pending\` and say why.
5. Wrap up: sent counts by channel, failures, cap status, remaining approved.

## Rules

- NEVER auto-click the final submit on any platform — ToS + account safety.
  The human clicks. Email is the only channel the system sends end-to-end.
- One email at a time; stop immediately on SMTP errors and report (never retry
  a send blindly — double-sending to a prospect is worse than not sending).
- Respect the cap even if the user asks to exceed it in passing; if they
  explicitly insist, tell them to raise DAILY_EMAIL_CAP in `.env` themselves.
- Never edit message content at dispatch time — content was frozen at review.
