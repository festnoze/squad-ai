# PRD: Shiplog - customer-facing release notes and hosted changelog pages

Status: draft v1. This document is the build contract for the MVP. An agent
fleet must be able to implement it without further product decisions.

## 1. Product summary

Shiplog turns merged pull requests into polished, customer-facing release
notes and publishes them on a hosted public changelog page. Target user: a
bootstrapped SaaS team (1-10 devs) whose public changelog is months stale
because writing it is nobody's job.

Flow: install the GitHub App -> pick a repo -> when a release/tag is
published (or on manual trigger), Shiplog collects the merged PRs since the
previous tag, classifies them, rewrites them in the customer's language and
tone, saves a DRAFT, and emails an edit link. One click publishes to
`<domain>/c/<slug>` (plus RSS and an embeddable widget) and optionally back
into the GitHub Release body.

The wedge vs writing it manually or pasting into ChatGPT: zero-effort
recurrence (it happens on every release, automatically) plus a hosted page
that is always current.

## 2. Naming and domains

- Working name: **Shiplog**
- Domain candidates (verify availability, in this order):
  1. shiplog.dev
  2. shiplog.app
  3. getshiplog.com
  4. shipnotes.dev
  5. mergenotes.dev
- Public changelog URLs live on the product domain: `https://<domain>/c/<slug>`.
  Custom domains are explicitly out of scope for v1 (see non-goals).

## 3. Pricing and gating

| Plan | Price | Limits |
|---|---|---|
| Free | 0 | 1 project, manual trigger only, "Powered by Shiplog" badge, last 10 releases shown |
| Pro | 19 EUR/month per project (or 190 EUR/year) | auto-trigger on release, no badge, full history, RSS + widget, publish-to-GitHub-Release |

- Billing: Stripe Checkout + customer portal, one subscription per project.
- Downgrade behavior: project reverts to Free limits, published pages stay up.
- Free plan exists purely as a demo funnel; every public Free page carries
  the badge linking to the landing page (that is the growth loop).

## 4. Architecture and stack

Conventions follow the user's existing projects (FastAPI + small frontend):

- Backend: **FastAPI on port 8400**, Python 3.11+, SQLAlchemy + SQLite in
  dev / Postgres in prod, Jinja2 server-rendered pages (public changelog AND
  the minimal dashboard: no SPA, no build step).
- LLM: Anthropic API, model `claude-sonnet-5`, temperature 0.2, two-stage
  pipeline (classify then write), all calls logged with token counts.
- GitHub: GitHub App (not OAuth app). Permissions: `contents:read`,
  `pull_requests:read`, `metadata:read`, and `contents:write` ONLY used for
  the optional publish-to-Release feature. Webhook events: `release`
  (published), `installation`, `installation_repositories`.
- Email: any SMTP relay behind a `send_email(to, subject, html)` interface;
  provider choice is a config value, not code.
- Repo layout:

```
shiplog/
  app/
    main.py            FastAPI app factory, routers mounted
    settings.py        env-driven config (pydantic-settings)
    db.py entities.py  SQLAlchemy models (section 5)
    github_client.py   App JWT, installation tokens, PR fetching
    generator/
      collect.py       PRs between two tags -> RawChange list
      classify.py      LLM stage 1 (prompt in section 7.1)
      write.py         LLM stage 2 (prompt in section 7.2)
      pipeline.py      orchestration + cost logging + retries
    routers/
      webhooks.py      /webhooks/github, /webhooks/stripe
      dashboard.py     login, project list, draft edit, settings
      public.py        /c/{slug}, /c/{slug}/rss.xml, /c/{slug}/embed.js
    templates/         jinja: public page, dashboard, draft email
  tests/               section 10
  landing/             static one-pager
```

## 5. Data model

- `users(id, github_login, github_id, email, created_at)`
- `installations(id, github_installation_id, account_login, user_id)`
- `projects(id, installation_id, repo_full_name, slug UNIQUE, display_name,
  config_json, plan ENUM(free, pro), stripe_customer_id NULL,
  stripe_subscription_id NULL, created_at)`
- `releases(id, project_id, tag, previous_tag, status ENUM(draft, published),
  raw_changes_json, notes_md, notes_html_cached, generation_cost_tokens,
  created_at, published_at NULL)`
- `events(id, project_id, kind, payload_json, created_at)` - audit trail of
  webhooks and pipeline runs, for debugging.

`config_json` per project (all editable in dashboard settings):

```json
{
  "language": "en",            
  "tone": "friendly-professional",
  "product_name": "Acme",
  "audience": "non-technical customers",
  "sections": {"feature": "New", "improvement": "Improved",
               "fix": "Fixed", "breaking": "Breaking changes"},
  "include_pr_links": false,
  "auto_generate_on_release": true,
  "publish_to_github_release": false,
  "excluded_labels": ["internal", "chore", "dependencies"]
}
```

## 6. Behavior contracts

### 6.1 Collection (`collect.py`)

- Input: project, new tag, previous tag (previous = latest earlier tag by
  commit date; if none, the last 50 merged PRs).
- Output: `RawChange` list: `{pr_number, title, body_first_400_chars,
  labels, files_changed_count, merged_at, author_login}`.
- Merged PRs only, between the two tags' commits (compare API). PRs with an
  excluded label are dropped before the LLM ever sees them.
- Hard cap 120 PRs per release; beyond that, keep the 120 with the highest
  files_changed_count and record the truncation in `events`.

### 6.2 Generation (`pipeline.py`)

- Stage 1 classify -> stage 2 write. Each stage: one retry on invalid JSON /
  empty output, then fail the release into an "error" event and email the
  owner a plain apology with a manual-trigger link. NEVER auto-publish.
- Output is always a DRAFT. Auto-publish does not exist in v1, even for Pro:
  the human click is the quality gate.
- Determinism aids: PRs sorted by pr_number in prompts; prompts contain no
  timestamps.
- Cost logging: token counts per stage stored on the release row. Target
  cost per release <= 0.15 EUR at 40 PRs.

### 6.3 Publishing (`public.py`)

- `/c/{slug}`: server-rendered page, newest release first, anchors per
  release (`#v1-2-0`), OpenGraph tags, mobile-friendly, badge iff plan=free.
  Cache: `notes_html_cached` rendered at publish time; the route is a plain
  DB read (fast without a cache layer).
- `/c/{slug}/rss.xml`: last 20 published releases.
- `/c/{slug}/embed.js`: injects a "What's new" panel (shadow DOM, no CSS
  leakage) showing the last 5 releases; Pro only.
- Publish-to-GitHub-Release (Pro, opt-in): replaces the Release body with
  the notes plus a footer link to the page.

## 7. LLM prompts (verbatim contracts)

### 7.1 Classifier (stage 1)

```
You classify merged pull requests for a customer-facing changelog.
Product: {product_name}. Audience: {audience}.
Pull requests (JSON):
{raw_changes_json}

For each PR decide:
- category: one of "feature", "improvement", "fix", "breaking", "internal"
- customer_visible: true only if a customer could notice or care
- one_line: one plain-language sentence of the change, written for the
  audience above (no branch names, no dev jargon, no PR numbers)

Reply with ONLY a JSON array:
[{"pr_number": <int>, "category": "<...>", "customer_visible": <bool>,
  "one_line": "<...>"}]
Every input PR must appear exactly once. When in doubt between "internal"
and something else, prefer "internal": a shorter honest changelog beats a
padded one.
```

### 7.2 Writer (stage 2)

```
You write release notes that customers actually read.
Product: {product_name}. Audience: {audience}. Language: {language}.
Tone: {tone}. Version: {tag}.
Classified changes (only customer_visible ones are included):
{classified_json}
Section titles to use, in this order, omitting empty ones:
{sections_json}

Rules:
- Markdown only. Start with a single intro sentence summarizing the release
  (skip it if there are fewer than 3 changes).
- Group items under the section titles. One bullet per change, benefit
  first ("You can now..." rather than "Added...").
- Merge near-duplicate items into one bullet.
- "Breaking changes" items must state what the user has to do.
- {pr_links_rule}
- No hype words (game-changer, revolutionary), no exclamation marks, no
  emoji unless tone is "playful". Never use the em-dash character; use "-"
  or parentheses.
Return ONLY the markdown document, no preamble.
```

`{pr_links_rule}` = "End each bullet with the PR link in parentheses." when
`include_pr_links` else "Do not mention PR numbers or links.".

If every change is classified internal: no draft is created; the owner gets
a short email saying this release had no customer-visible changes (this
honesty is a feature; never fabricate content to fill a page).

## 8. Dashboard (minimal, server-rendered)

- Login: "Sign in with GitHub" (App installation flow doubles as signup).
- Pages: project list -> project view (releases + statuses, settings form
  for config_json fields, plan/upgrade button) -> draft editor: a textarea
  with the markdown, live preview pane, Publish and Regenerate buttons.
- The draft-ready email links straight into the editor. Editor is
  deliberately a textarea, not a rich editor: users are devs.

## 9. Milestones

- M0 (days 1-2): `collect.py` + generation pipeline as a CLI against any
  public repo (`python -m app.generator.pipeline --repo x/y --tag v1.2.0`);
  prompts tuned on 3 real repos.
- M1 (days 3-6): GitHub App wired (webhooks, installation flow), drafts
  created on release, draft email + editor working.
- M2 (days 7-9): public page, RSS, publish flow, Free-plan badge.
- M3 (days 10-13): Stripe (checkout, webhook, gating), embed.js, landing
  page ("paste your repo, see your last release rewritten" live demo box,
  rate-limited, 3/day per IP).
- M4 (week 3+): launch: Show HN / r/SaaS / Indie Hackers posts written from
  the "our own changelog, generated by itself" angle; Shiplog's own repo
  must be its first public project (dogfooding proof).

## 10. Test plan

- Unit: collect.py PR-range selection against a fixture of GitHub API
  responses (no network); excluded-labels filtering; the 120-PR cap.
- Unit: prompt rendering (all config permutations produce valid prompts;
  pr_links_rule switches correctly).
- Unit: pipeline failure paths (invalid JSON from stage 1 retries once, then
  errors without creating a draft).
- Integration: webhook signature verification (reject bad HMAC), release
  event -> draft row created; Stripe webhook -> plan flips.
- E2E (against a scratch GitHub repo in CI): tag push -> draft -> publish ->
  public page renders and RSS validates.
- LLM regression fixture: 1 canned classified_json -> writer output checked
  for structural rules (sections order, no PR numbers when disabled,
  no em-dash character).

## 11. Acceptance criteria

1. Installing the App on a repo and publishing a GitHub release yields a
   draft email within 3 minutes, unattended.
2. Publishing a draft makes `/c/{slug}` and the RSS feed reflect it
   immediately; the page scores >= 90 on Lighthouse (it is static HTML).
3. Free plan hard-blocks a second project and auto-trigger; upgrading via
   Stripe unlocks both without a restart.
4. Generation cost per release is logged and <= 0.15 EUR for a 40-PR release.
5. A release where all PRs are internal creates NO draft and sends the
   "nothing customer-visible" email.
6. The whole app runs locally with `uvicorn app.main:app --port 8400` and
   SQLite, with GitHub/Stripe/LLM behind interfaces that have fake
   implementations for dev mode.

## 12. Non-goals (v1)

- No custom domains for changelog pages, no themes beyond light/dark.
- No auto-publish without a human click, no scheduled digests, no email
  subscriptions for end customers (RSS covers it).
- No GitLab/Bitbucket, no monorepo multi-changelog splitting.
- No team roles/permissions: one GitHub account owns a project.
- No analytics beyond a page-view counter per release.

## 13. Risks

- "Feature, not a product" (GitHub/Linear could ship this): acceptable at
  this price point; the hosted page + audience-tuned writing is the moat,
  and total build cost is ~2 weeks.
- Churn after novelty: the badge growth loop and yearly plan (190 EUR)
  are the mitigations; measure publish-rate per project as THE health metric.
- LLM output embarrassing a customer: drafts-only publishing, the honesty
  rule (internal-only releases produce nothing), and the no-hype prompt
  rules are the mitigations.
