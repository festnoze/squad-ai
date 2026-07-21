# Prospector — Implementation Plan

> Autonomous freelance-mission prospection system for Etienne Millerioux
> (Lead AI Engineer). Finds full-remote freelance missions (AI Engineer,
> AI-augmented Software Engineer, Forward Deployed Engineer, GenAI/LLM/RAG
> roles), scores them against the CV profile, drafts a custom application in
> the right language with the right CV PDF attached, queues everything for
> human review, then dispatches via the appropriate medium and tracks
> follow-ups.

**Decisions already made (2026-07-19):**
- **Autonomy**: review queue — nothing is sent without explicit approval.
- **Sources**: FR freelance platforms, international remote boards, job
  boards + LinkedIn, direct cold outreach (all four).
- **Architecture**: Claude Code project — `.claude/agents` + `.claude/skills`
  + small deterministic Python helpers, runnable headless on a schedule.
- **Sender identity**: new dedicated Gmail account.

**Targeting rules:**
- Full remote only.
- **French** applications → missions located in France (or FR companies).
- **English** applications → UK, USA, and any country with an
  English-speaking work environment.
- Freelance/contract engagements (not permanent positions), TJM/day-rate
  compatible with a senior/lead profile.

---

## 1. Architecture overview

```
                        ┌─────────────────────────────────────────┐
                        │            /prospect (daily run)         │
                        └───────────────────┬─────────────────────┘
                                            │
      ┌──────────────┬──────────────────────┼──────────────────┬─────────────┐
      ▼              ▼                      ▼                  ▼             │
 scout-boards   scout-platforms      scout-linkedin      scout-direct        │
 (APIs/RSS/     (Malt, Comet...      (LinkedIn, WTTJ,    (companies hiring   │
  WebSearch)     via Playwright)      Indeed)             AI eng → contacts) │
      │              │                      │                  │             │
      └──────────────┴──────────┬───────────┴──────────────────┘             │
                                ▼                                            │
                          missions.db (SQLite)                               │
                          dedup + raw offers                                 │
                                │                                            │
                                ▼                                            │
                             scorer  ──── profile.yaml (CV-derived)          │
                        score ≥ threshold?                                   │
                                │                                            │
                                ▼                                            │
                             writer  ──── assets/cv/*.pdf (FR/EN × short/full)
                     cover message (FR/EN) + channel choice                  │
                                │                                            │
                                ▼                                            │
                        review queue (pending/)                              │
                     USER APPROVES / EDITS / REJECTS                         │
                                │                                            │
                                ▼                                            │
                           dispatcher                                        │
              email (Gmail SMTP) │ platform (browser prefill)                │
                                │                                            │
                                ▼                                            │
                       tracker / follow-ups / daily digest ──────────────────┘
```

## 2. Project layout

```
Prospector/
├── PLAN.md                     # this file
├── README.md                   # usage guide
├── CLAUDE.md                   # project instructions for Claude Code
├── config/
│   ├── profile.yaml            # candidate profile distilled from CV (skills, rates, keywords)
│   ├── targets.yaml            # sources, search queries FR/EN, geo rules, caps
│   └── style.md                # cover-letter voice & rules (FR + EN examples)
├── assets/
│   └── cv/
│       ├── cv_fr_short.pdf     # generated from ../CV (1-2 pages)
│       ├── cv_fr_full.pdf
│       ├── cv_en_short.pdf     # EN version (to be created)
│       └── cv_en_full.pdf
├── data/
│   ├── prospector.db           # SQLite: missions, applications, contacts, runs
│   └── queue/
│       ├── pending/            # one .md file per drafted application (human-readable)
│       ├── approved/
│       ├── sent/
│       └── rejected/
├── scripts/                    # deterministic Python helpers (venv)
│   ├── db.py                   # SQLite schema + CRUD (upsert_mission, dedup, stats)
│   ├── fetch_boards.py         # RemoteOK API, WeWorkRemotely RSS, etc.
│   ├── send_email.py           # Gmail SMTP send w/ attachment + daily cap check
│   ├── check_replies.py        # IMAP scan of the Gmail inbox → update statuses
│   ├── render_cv.py            # Playwright print-to-PDF of the HTML CVs
│   └── report.py               # daily digest generator
├── .claude/
│   ├── agents/
│   │   ├── scout-boards.md     # API/RSS/WebSearch discovery
│   │   ├── scout-platforms.md  # Playwright browsing of logged-in platforms
│   │   ├── scout-linkedin.md   # LinkedIn / WTTJ / Indeed discovery
│   │   ├── scout-direct.md     # find companies hiring AI eng + contact emails
│   │   ├── scorer.md           # rubric-based mission scoring
│   │   ├── writer.md           # cover message + channel + CV variant
│   │   └── tracker.md          # follow-ups, reply detection, digest
│   └── skills/
│       ├── prospect/           # /prospect — full pipeline orchestration
│       ├── review/             # /review — walk the pending queue, approve/edit/reject
│       ├── dispatch/           # /dispatch — send approved applications
│       ├── follow-up/          # /follow-up — relances after N days silence
│       └── cv-refresh/         # /cv-refresh — regenerate the 4 PDFs from ../CV
└── logs/
```

## 3. Data model (SQLite)

- **missions**: id, source, url, title, company, location, remote_policy,
  language (fr/en), engagement (freelance/contract/cdi), rate, description,
  stack (json), found_at, hash (dedup on url + normalized title+company),
  score, score_breakdown (json), status
  (new → scored → drafted → queued → sent → replied → interview → won/lost/ignored)
- **applications**: id, mission_id, channel (email/platform/linkedin/form),
  language, cv_variant, message_path, sent_at, followup_count,
  last_followup_at, reply_at, outcome
- **contacts**: id, company, name, role, email, source, used_in_application_id
- **runs**: id, started_at, finished_at, source, missions_found, new, errors

## 4. Pipeline phases

### Phase 0 — Assets (prerequisite)
1. **CV content pass**: fill the missing `description` fields of the short CV
   from `cv_full` data (no invented metrics), apply quick audit fixes
   (city-only address, GitHub link placeholder, professional summary).
2. **English CV**: translate the data files (`data/*.js`) → `CV/en/` variant
   of the data-driven CV (same HTML/CSS, EN data + EN section labels).
3. **PDF generation**: `render_cv.py` prints the 4 variants to
   `assets/cv/*.pdf` via Playwright (text-based PDFs, ATS-safe).
4. **profile.yaml**: distilled machine-readable profile — target titles,
   skills with weights, seniority, TJM range, languages, geo rules,
   exclusions — the single source of truth for scoring.

### Phase 1 — Core infrastructure
- Python venv + `scripts/db.py` with schema above, dedup logic, CLI entry
  points (`python scripts/db.py upsert|stats|list`).
- `config/targets.yaml`: per-source search queries (FR + EN keyword sets),
  score threshold, daily caps (e.g. max 10 queued/day, max 5 emails/day).
- `CLAUDE.md` + scaffolding of agents/skills.

### Phase 2 — Discovery (4 scout agents)
- **scout-boards**: RemoteOK/WWR/Remotive APIs & RSS + WebSearch on niche
  boards; no login needed; runs fully headless.
- **scout-platforms**: Playwright with a **persistent browser profile**
  (user logs in once manually to Malt, Comet, FreelanceRepublik, LeHibou,
  Upwork, Contra); agent browses new missions matching saved searches.
- **scout-linkedin**: LinkedIn Jobs (remote+contract filters), Welcome to
  the Jungle, Indeed — same persistent profile.
- **scout-direct**: WebSearch/WebFetch for AI startups/scale-ups/ESN hiring
  AI engineers; extract or infer contact emails; store in `contacts`.
- All scouts upsert into SQLite; dedup by hash; log a `runs` row.

### Phase 3 — Scoring
- **scorer** agent reads `new` missions, applies rubric from profile.yaml:
  remote-full (hard filter), language/geo rule (hard filter), stack overlap,
  title match, seniority fit, rate, red flags (staffing spam, on-site days).
  Writes score + breakdown; missions ≥ threshold move to `scored`.

### Phase 4 — Drafting
- **writer** agent per qualified mission: picks channel (platform > direct
  email > form), language (FR if France, EN otherwise), CV variant
  (short for platforms/boards, full when email allows), writes a custom
  cover message referencing 2-3 concrete CV achievements matched to the
  mission's needs, following `config/style.md`.
- Output: one markdown file in `data/queue/pending/` with YAML frontmatter
  (mission ref, channel, language, cv, to/subject if email) + message body.

### Phase 5 — Review & dispatch
- **/review**: interactive walk through pending drafts — approve / edit /
  reject; moves files between queue folders and updates DB.
- **dispatcher**:
  - email channel → `send_email.py` (Gmail SMTP app-password, PDF attached,
    respects daily cap, BCC to self).
  - platform channel → Playwright opens the mission page, prefills the
    application form and message; user does the final click (ToS-safe).
- Everything sent is archived in `queue/sent/` + DB.

### Phase 6 — Tracking & follow-ups
- **tracker** agent + `check_replies.py`: scan Gmail inbox via IMAP, match
  replies to applications, update statuses.
- **/follow-up**: after N days (default 5) without reply → draft a short
  relance into the pending queue (same review flow, max 2 follow-ups).
- Daily digest: new missions found, scores, queue state, replies, stats.

### Phase 7 — Scheduling
- Windows Task Scheduler → `claude -p "/prospect"` headless every morning;
  `/review` stays a manual interactive session (it needs the user anyway).
- Logs per run in `logs/`.

## 5. Risks & guardrails

- **Platform ToS**: no auto-submission on platforms — browser prefill +
  human click only. Review queue is mandatory for every channel.
- **Email deliverability**: fresh Gmail = warm up slowly (≤5/day first two
  weeks), personalized messages only, no attachments to unknown recipients
  when a link would do, always a real unsubscribe-friendly tone.
- **Scraping fragility**: per-source skills isolate breakage; a failing
  source logs an error in `runs` and never blocks the pipeline.
- **Rate/volume caps**: enforced in code (`send_email.py`, queue), not just
  in prompts.
- **Secrets**: Gmail app password in `.env` (gitignored), never in configs.

## 6. Milestones

| # | Deliverable | Depends on |
|---|-------------|-----------|
| M0 | 4 CV PDFs + profile.yaml + EN CV data | — |
| M1 | SQLite core + configs + scaffolding | — |
| M2 | scout-boards end-to-end (find → store → dedup) | M1 |
| M3 | scorer + writer + pending queue with real drafts | M0, M2 |
| M4 | /review + email dispatch + sent tracking | M3, Gmail account |
| M5 | scout-platforms + scout-linkedin (needs one-time manual logins) | M1 |
| M6 | scout-direct + contacts | M1 |
| M7 | tracker + follow-ups + daily digest + scheduling | M4 |

**User to-dos (blocking, only you can do them):**
1. Create the dedicated Gmail account + generate an **app password**
   (2FA → App passwords) and put it in `Prospector/.env`.
2. One-time manual login to each platform in the persistent Playwright
   profile (M5) — I'll provide a `login-setup` helper that opens the browser.
3. (Recommended) Create/point a GitHub profile URL to add to the CV.
