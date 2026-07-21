# Prospector

Semi-autonomous prospection system for full-remote freelance AI-engineering
missions (AI Engineer, Forward Deployed Engineer, GenAI/LLM/RAG roles).
It discovers missions across boards, freelance platforms, LinkedIn, and direct
company signals; scores them against the CV profile; drafts custom FR/EN
applications with the right CV PDF; **queues everything for your approval**;
sends approved ones (email end-to-end, platforms via prefill + your click);
then tracks replies and follow-ups.

Built as a Claude Code project: run the skills below inside `claude` from this
folder. Design details in [PLAN.md](PLAN.md), rules in [CLAUDE.md](CLAUDE.md).

## One-time setup

1. **Python env** (created by the installer, or redo with):
   ```powershell
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   venv\Scripts\playwright install chromium   # browsers for scraping + PDF fallback
   ```
2. **Gmail**: create the dedicated Gmail account, enable 2FA, generate an
   **App password** (Google Account → Security → App passwords), then:
   ```powershell
   copy .env.example .env    # fill GMAIL_ADDRESS + GMAIL_APP_PASSWORD
   ```
   Also put the address in `config/profile.yaml` → `identity.email`.
3. **Platform logins** (once per platform; repeat if a session expires):
   ```powershell
   venv\Scripts\python.exe scripts\login_setup.py --site malt
   venv\Scripts\python.exe scripts\login_setup.py --site linkedin
   # also: upwork, comet, freework, lehibou, wttj, contra
   ```
   Log in manually in the window that opens, then close it — the session
   persists in `browser_profile\`.
4. **CV PDFs**: `/cv-refresh` in Claude Code (or
   `venv\Scripts\python.exe scripts\render_cv.py`) → `assets/cv/*.pdf`.

## Daily use

| Command | What it does |
|---|---|
| `/prospect` | Full run: scouts → scoring → drafts into the review queue |
| `/review` | Walk pending drafts: approve / edit / reject each one |
| `/dispatch` | Send approved: emails auto (capped/day), platforms prefilled for your click |
| `/follow-up` | Scan replies, draft relances (max 2, ≥5 days apart) into the queue |
| `/cv-refresh` | Regenerate the 4 CV PDFs from `cv/` |

Typical morning: `/prospect`, coffee, `/review`, `/dispatch`. Manual runs by
design (no scheduler registered); everything is schedule-ready if you later
want Task Scheduler to run `claude -p "/prospect"`.

## Tuning

- `config/targets.yaml` — sources on/off, search queries, score threshold,
  caps (drafts/run, emails/day, follow-up policy).
- `config/profile.yaml` — the candidate truth: titles, skills, rates,
  geo/language rules, experience highlights used in letters.
- `config/style.md` — cover-message rules and examples.
- Rejecting drafts in `/review` feeds `config/review-feedback.md`, which the
  writer reads on later runs — the system learns your taste.

## Safety model

- Human approval gates every outgoing message; email is the only channel the
  system sends itself (hard daily cap in `.env`, default 5 — deliberately low
  while the Gmail account warms up).
- Platform automation is read-only + prefill: the final click is always yours
  (ToS compliance, account safety).
- Applications only claim what `config/profile.yaml` and the CVs support.

## Layout

```
config/     profile.yaml · targets.yaml · style.md
cv/         render sources: fr_short · fr_full · en_short · en_full
assets/cv/  generated PDFs (4 variants)
data/       prospector.db · queue/{pending,approved,sent,rejected}
scripts/    db · fetch_boards · send_email · check_replies · render_cv · report · login_setup
.claude/    agents (scouts, scorer, writer, tracker) · skills (the 5 commands)
```
