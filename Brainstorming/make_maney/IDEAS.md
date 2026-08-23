# Agent-Driven Income Ideas for a Solo Full-Stack/AI Developer

Honest framing before the list: after 6 months, most solo projects earn 0-500 EUR/month. The ranges below assume consistent effort (10-15 h/week), actual distribution work (not just building), and some luck. Anything promising more than 2-3k EUR/month at month 6 for a solo dev is an outlier, not a plan.

---

## Category 1: Productized Services (fastest to first euro)

### 1. Legacy codebase documentation service
- **What**: Fixed-price service (e.g. 900 EUR) where Claude Code agents crawl a client's legacy repo and produce architecture docs, onboarding guides, and dependency maps, with your human review pass.
- **First step this week**: Pick one public open-source repo, generate a full doc pack with your agents, publish it as a portfolio sample, then DM 10 agencies on LinkedIn that maintain client legacy code.
- **Startup cost**: 50-100 EUR (Claude API/subscription, domain).
- **Realistic monthly revenue**: 0-2,000 EUR (2-3 clients/month if outreach works; often 0 the first 2 months).
- **Automation level**: 80% (agents do the crawling and writing; you do QA and client calls).
- **Main risk**: Nobody buys docs proactively; you must sell it as part of a migration or audit, which requires real outreach stamina.

### 2. Test-suite retrofitting for small SaaS teams
- **What**: You take a Python/JS codebase with poor coverage and deliver a pytest/vitest suite raising coverage to an agreed target, priced per module (300-800 EUR each).
- **First step this week**: Write a one-page offer with fixed pricing, then reply to 5 "our tests are a mess" posts on r/ExperiencedDevs, Indie Hackers, or relevant Slack/Discord communities.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 500-3,000 EUR once you have referrals; 0-500 EUR the first months.
- **Automation level**: 85% (agents write tests against contracts; you verify they test behavior, not implementation).
- **Main risk**: Scope creep - untestable spaghetti code turns a fixed-price job into a loss.

### 3. Dependency upgrade and framework migration sprints
- **What**: Fixed-scope "we move you from Vue 2 to Vue 3 / Python 3.8 to 3.12 / Pydantic v1 to v2" packages for small companies, run largely by headless agent pipelines with CI verification.
- **First step this week**: Script a Claude Code pipeline that does one migration type end-to-end (e.g. Pydantic v1 to v2) on a sample repo, and time it to price the offer.
- **Startup cost**: under 100 EUR.
- **Realistic monthly revenue**: 1,000-4,000 EUR at month 6 if you land 1-2 clients/month; this is real demand.
- **Automation level**: 70% (agents do bulk transforms; edge cases and CI failures need you).
- **Main risk**: One gnarly migration blows your estimate and eats a month.

### 4. AI-agent setup consulting for dev teams
- **What**: A 2-day paid engagement (1,500-3,000 EUR) where you set up Claude Code workflows, CLAUDE.md conventions, CI hooks, and agent pipelines for a team of 3-10 devs.
- **First step this week**: Write up your own multi-agent CUBEFORGE/Autospec workflow as a case study post and publish it on LinkedIn plus one dev community.
- **Startup cost**: 0-50 EUR.
- **Realistic monthly revenue**: 1,500-5,000 EUR (1-2 engagements/month); highest EUR/hour on this list but not passive.
- **Automation level**: 30% (agents prep materials; the value is you talking to humans).
- **Main risk**: It is trading time for money; income stops when you stop.

### 5. Automated code-review-as-a-service for agencies
- **What**: A monthly retainer (300-600 EUR/agency) where your pipeline runs deep AI review on every PR of the agency's client projects and posts findings, with weekly human spot-checks.
- **First step this week**: Build the GitHub App skeleton (webhook -> headless Claude review -> PR comment) on one of your own repos.
- **Startup cost**: 100-200 EUR (API costs scale with usage).
- **Realistic monthly revenue**: 300-1,500 EUR (2-4 retainers is realistic at month 6).
- **Automation level**: 90% (nearly fully automated after setup).
- **Main risk**: GitHub Copilot and native review features commoditize this fast.

---

## Category 2: Micro-SaaS (slow, but compounding)

### 6. Godot/three.js game-jam boilerplate generator
- **What**: A web tool where a game dev describes a prototype and gets a downloadable, running Godot 4 or three.js project scaffold (input, camera, save system, menu), 15-25 EUR one-time or 9 EUR/month.
- **First step this week**: Extract your CUBEFORGE/VELOCITRON scaffolding into 3 reusable templates and post them free on itch.io to test demand.
- **Startup cost**: 100-200 EUR (hosting + API).
- **Realistic monthly revenue**: 100-800 EUR (game devs are numerous but famously broke).
- **Automation level**: 90% (agents generate the scaffolds; you curate templates).
- **Main risk**: Free templates and Godot's asset library make paying feel optional.

### 7. Changelog and release-notes writer for SaaS teams
- **What**: A tool that reads a repo's merged PRs and generates customer-facing release notes plus a public changelog page, 19-49 EUR/month per product.
- **First step this week**: Build a CLI version that turns your own git log into polished release notes, and post before/after examples on X and Indie Hackers.
- **Startup cost**: 100 EUR.
- **Realistic monthly revenue**: 200-1,500 EUR (needs ~10-40 paying teams; churn is real).
- **Automation level**: 95% (fully pipeline-driven once connected).
- **Main risk**: It is a feature, not a product; Linear/GitHub could ship it natively.

### 8. French-market compliance page generator for small sites
- **What**: A tool generating legally-sensible French "mentions légales", CGV, privacy policies, and cookie banners for freelancers and TPEs, 29-79 EUR one-time, with a lawyer-reviewed template base.
- **First step this week**: List the 6 required documents for a French e-commerce TPE and price a one-time lawyer review of your base templates (this is the moat).
- **Startup cost**: 500-1,500 EUR (lawyer review is the real cost, and non-optional).
- **Realistic monthly revenue**: 200-1,000 EUR with SEO on French keywords.
- **Automation level**: 85% (generation is automated; template maintenance needs legal updates).
- **Main risk**: Liability perception - buyers may not trust a non-lawyer product, and you must word disclaimers carefully.

### 9. Uptime-plus-diagnosis monitor for indie hackers
- **What**: Monitoring that does not just ping but, on failure, has an agent read logs/response bodies and email a plain-language diagnosis ("your SSL cert expired", "DB connection pool exhausted"), 9-19 EUR/month.
- **First step this week**: Wire a FastAPI checker + headless Claude diagnosis for your own deployed projects and screenshot a real diagnosis email as marketing material.
- **Startup cost**: 100-200 EUR.
- **Realistic monthly revenue**: 100-900 EUR (crowded market; the diagnosis angle is the only wedge).
- **Automation level**: 95%.
- **Main risk**: UptimeRobot free tier is "good enough" for the target customer.

### 10. Screenshot-to-Playwright test generator
- **What**: Paste a URL and user story, get a maintained Playwright E2E test suite, sold to QA-less startups at 29-99 EUR/month.
- **First step this week**: Reuse your CDP headless harness knowledge to build a demo that generates a working test for one public site, and record a 2-minute video of it.
- **Startup cost**: 150 EUR.
- **Realistic monthly revenue**: 200-1,500 EUR.
- **Automation level**: 90%.
- **Main risk**: Flaky generated tests destroy trust after the first false alarm.

---

## Category 3: Digital Products (build once, sell forever, sell slowly)

### 11. Paid Godot 4 asset packs and plugins
- **What**: Sell polished Godot addons (voxel terrain module, save-system, mobile input pack) on the Godot Asset Store / itch.io at 10-40 EUR each, extracted from your CUBEFORGE work.
- **First step this week**: Isolate your CUBEFORGE mesher + chunk system into a standalone addon with a demo scene and publish a free lite version on itch.io.
- **Startup cost**: 0-50 EUR.
- **Realistic monthly revenue**: 50-600 EUR (asset stores follow power laws; most packs earn coffee money).
- **Automation level**: 60% (agents write code and docs; polish and support are yours).
- **Main risk**: Discovery - without devlog content driving traffic, packs sit unseen.

### 12. "Ship a game with AI agents" video course + template repo
- **What**: A 4-6 hour course showing exactly how you built CUBEFORGE with 14 agents against a CONTRACTS.md, sold at 79-149 EUR on Gumroad, template repo included.
- **First step this week**: Write the course outline and post a free 10-minute "how 14 AI agents built my voxel game" video or thread to test appetite before recording anything.
- **Startup cost**: 100-300 EUR (mic, Gumroad fees).
- **Realistic monthly revenue**: 100-1,500 EUR, front-loaded at launch then decaying without new content.
- **Automation level**: 50% (agents draft scripts and materials; your face/voice and real experience are the product).
- **Main risk**: No existing audience means launch sales of 5 copies, not 500.

### 13. Niche prompt-pipeline packs for developers
- **What**: Sell battle-tested Claude Code skill/agent configurations for specific stacks ("FastAPI 3-layer factory", like your Autospec skills) at 19-49 EUR per pack on Gumroad.
- **First step this week**: Package your existing repo-search-or-create / service-search-or-create skill set with a README and demo video, and post it in Claude Code communities.
- **Startup cost**: 0-50 EUR.
- **Realistic monthly revenue**: 50-500 EUR (small market, but you already own the inventory).
- **Automation level**: 70%.
- **Main risk**: Rapid obsolescence - Anthropic ships something that makes your pack redundant in one release.

### 14. Paid template gallery of browser mini-games for agencies
- **What**: License your three.js game codebases (racing, diving, puzzle) as white-label templates that marketing agencies rebrand for client campaigns, 200-500 EUR per license.
- **First step this week**: Put your 6 existing games behind a demo gallery page with a "license this" button and email 10 French digital agencies that do advergames.
- **Startup cost**: 50-150 EUR (domain, gallery hosting).
- **Realistic monthly revenue**: 0-1,500 EUR (lumpy: some months 0, some months 2 licenses).
- **Automation level**: 75% (agents handle reskinning requests; sales are manual).
- **Main risk**: Agencies build in-house or use Unity ad-game shops; the buyer is hard to reach.

---

## Category 4: Marketplaces and Arbitrage (opportunistic)

### 15. Upwork/Malt fixed-price gigs with agent leverage
- **What**: Take well-scoped freelance jobs (scrapers, dashboards, API integrations) on Malt/Upwork at market rates, deliver in a fraction of the time using agent pipelines, and pocket the spread.
- **First step this week**: Create a Malt profile targeted at "automatisation Python / FastAPI" and apply to 5 fixed-price jobs under 1,000 EUR to build reviews.
- **Startup cost**: 0-30 EUR.
- **Realistic monthly revenue**: 1,000-4,000 EUR once reviews accumulate; near 0 the first month.
- **Automation level**: 70% (delivery is agent-heavy; bidding and client comms are you).
- **Main risk**: Race-to-the-bottom pricing and time spent bidding instead of building.

### 16. Micro-acquisition and revival of abandoned micro-SaaS
- **What**: Buy a small neglected product (1,000-5,000 EUR on Acquire.com or via direct outreach), use agents to fix bugs, modernize, and relaunch, keeping its existing MRR.
- **First step this week**: Create an Acquire.com account and shortlist 5 listings under 5,000 EUR with real (even tiny) revenue and a stack you know.
- **Startup cost**: 1,000-5,000 EUR (the acquisition).
- **Realistic monthly revenue**: 100-800 EUR MRR inherited plus whatever you grow; slow.
- **Automation level**: 75% (revival work is agent-friendly; due diligence is not).
- **Main risk**: Buying a product that was abandoned because the market is dead, not because the owner was tired.

### 17. Bug-bounty / open-source bounty hunting with agent triage
- **What**: Use agents to scan and triage issues on Algora/Polar bounty boards and low-tier bug-bounty programs, then fix the ones where you have edge (Python, Godot, web).
- **First step this week**: Register on Algora, filter bounties in Python/TypeScript under 500 USD, and attempt one this weekend with a Claude Code pipeline.
- **Startup cost**: 0 EUR.
- **Realistic monthly revenue**: 100-1,000 EUR, highly variable, effectively piecework.
- **Automation level**: 60% (agents draft fixes; maintainers demand human-quality PRs and review responsiveness).
- **Main risk**: Competition from every other AI-equipped dev doing exactly this; payouts per hour can be poor.

### 18. Local business automation packages (French TPE market)
- **What**: Sell 500-1,500 EUR fixed automations to local businesses (quote generators, appointment reminders, invoice chasing via email) built as small FastAPI apps your agents crank out.
- **First step this week**: Ask 3 non-tech business owners you personally know what task they redo every week, and quote one of them a fixed price.
- **Startup cost**: 50-100 EUR.
- **Realistic monthly revenue**: 500-2,500 EUR (plus small maintenance retainers of 30-80 EUR/month that stack).
- **Automation level**: 75% (build is agent work; sales are face-to-face and in French).
- **Main risk**: Support burden - non-technical clients call you for everything, forever.

---

## Top 3 picks for this profile

1. **#3 Dependency/framework migration sprints** - real, recurring corporate demand, plays exactly to headless Claude Code pipelines with CI verification, and clients pay for outcomes rather than your time on a chair.
2. **#15 Malt/Upwork arbitrage** - the fastest path to actual revenue for someone with strong delivery skills and no audience; it funds everything else while agent leverage keeps your effective hourly rate high.
3. **#11 + #12 combined (Godot assets + the "built by agents" course)** - you already own the raw material (CUBEFORGE, the 14-agent workflow, the test harness learnings); packaging existing work is the cheapest product launch you will ever get, and the course markets the assets.

Common thread: start with a service to get cash flowing (weeks), let the agent pipelines you build for clients become the products (months), and treat anything promising passive income before month 6 with suspicion.
