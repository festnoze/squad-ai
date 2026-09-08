# Idea ranking across IDEAS.md, IDEAS2.md and ideas3.md

Scored on 6 September 2026. One row per distinct idea: direct duplicates across the
three lists are merged and every source is named in the Source column; cousins
(same buyer, different deliverable) keep their own row. The two tier-2 ventures
(ActProof, LLMargin) are included because they descend from IDEAS.md.

Scores are judgment calls, not measurements:

- **Realism (1-5)**: does a solo operator with no audience actually get paid for this
  within 6 months? Accounts for demand evidence, competition, legal exposure, and
  the counter-arguments raised in ideas3.md.
- **Ease (1-5)**: how much stands between today and a first paid delivery? 5 means
  the pipeline or inventory already exists in this repo; 1 means capital, licenses,
  partners, or a long sales cycle come first.
- **Score**: realism + ease, the sort key. Ties are broken by the upper revenue bound.
- **EUR/month at month 6**: the realistic range from the source document (ideas3
  figures are its repeat price times 2 to 4 clients). Tier S <= 600, M <= 1,500,
  L <= 3,000, XL above.
- **Bucket**: Do now (8+), Next (7), Later (6), Skip for now (5 and below).

| # | Idea | Source | Realism | Ease | Score | EUR/month at month 6 | Tier | Bucket | Main caveat |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Malt/Upwork fixed-price gigs with agent leverage | IDEAS #15 | 5 | 4 | 9 | 1,000-4,000 | XL | Do now | Fastest real cash; bidding time competes with building; no asset |
| 2 | Reviews and Google Business Profile management | IDEAS2 #2 | 4 | 5 | 9 | 500-3,000 | L | Do now | Thin moat: Google suggests replies for free; multi-site owners stack |
| 3 | AI-agent setup consulting for dev teams | IDEAS #4 | 4 | 4 | 8 | 1,500-5,000 | XL | Do now | Highest EUR/hour of all lists; stops when you stop |
| 4 | Tender watch, qualification briefs, bid drafting | IDEAS2 #4 + ideas3 #3 | 4 | 4 | 8 | 700-4,000 | XL | Do now | Both lists rank it; qualify first (350/month), draft as upsell (500-1,500 per bid) |
| 5 | Catalog preparation for specialist distributors | ideas3 #1 (cousin: IDEAS2 #11) | 4 | 4 | 8 | 1,500-3,000 | L | Do now | Demoable before system access; ten supplier formats = bespoke repair |
| 6 | Test-suite retrofitting for small SaaS teams | IDEAS #2 | 4 | 4 | 8 | 500-3,000 | L | Do now | Scope creep on untestable code turns fixed price into a loss |
| 7 | Marketplace listing optimization for existing sellers | IDEAS2 #11 | 4 | 4 | 8 | 500-3,000 | L | Do now | Judged on conversion within 30 days |
| 8 | Verified B2B lead lists | IDEAS2 #18 | 4 | 4 | 8 | 500-3,000 | L | Do now | Document the GDPR legal basis on every list |
| 9 | Quote follow-up and invoice reminders for trades | IDEAS2 #3 + ideas3 #2 | 4 | 4 | 8 | 400-2,000 | L | Do now | Incremental jobs hard to prove; debt collection is regulated, stay on reminders |
| 10 | Legacy codebase documentation packs (RepoAtlas) | IDEAS #1 + ventures/repoatlas | 3 | 5 | 8 | 0-2,000 | L | Do now | Engine, verify gates and website already built; nobody buys docs proactively |
| 11 | Job search concierge for career changers | IDEAS2 #17 | 3 | 5 | 8 | 300-1,500 | M | Do now | CV pipeline exists; ten packages a month is heavy outreach |
| 12 | Prompt-pipeline and skill packs for developers | IDEAS #13 | 3 | 5 | 8 | 50-500 | S | Do now | Inventory already owned; one Anthropic release can obsolete it |
| 13 | Dependency upgrade and framework migration sprints | IDEAS #3 | 4 | 3 | 7 | 1,000-4,000 | XL | Next | Real corporate demand; one gnarly migration eats a month |
| 14 | Local business automation packages (French TPE) | IDEAS #18 | 4 | 3 | 7 | 500-2,500 | L | Next | Face-to-face sales in French; support burden forever |
| 15 | Real estate listing packs for independent agents | IDEAS2 #13 | 3 | 4 | 7 | 400-2,500 | L | Next | Agents pay per lead already; label every retouched image |
| 16 | Product-image cleanup and catalog imagery | IDEAS2 #14 + ideas3 #5 | 3 | 4 | 7 | 300-2,000 | L | Next | Cleanup only at first; never regenerate the product pixels |
| 17 | Webinar-to-sales-material packs | ideas3 #9 | 3 | 4 | 7 | 600-1,800 | L | Next | OpusClip does the editing for cheap; selection and meaning are the value |
| 18 | Automated code review retainers for agencies | IDEAS #5 | 3 | 4 | 7 | 300-1,500 | M | Next | Copilot and native review commoditize it |
| 19 | Niche B2B newsletter with agent research desk | IDEAS2 #6 | 3 | 4 | 7 | 0-1,500 | M | Next | Slow, but the only asset nobody can revoke; ideas3 defers it |
| 20 | Competitor-change briefs for niche distributors | ideas3 #8 | 3 | 4 | 7 | 500-1,250 | M | Next | 3 h/month, research shareable across clients; low price per client |
| 21 | Bug-bounty and open-source bounty hunting | IDEAS #17 | 3 | 4 | 7 | 100-1,000 | M | Next | Piecework against every other AI-equipped dev |
| 22 | Paid Godot asset packs and plugins | IDEAS #11 | 3 | 4 | 7 | 50-600 | S | Next | CUBEFORGE inventory exists; discovery is the problem |
| 23 | Corporate micro-training from company documents | IDEAS2 #16 (cousin: ideas3 #7) | 3 | 3 | 6 | 500-4,000 | XL | Later | Not Qualiopi-eligible; sell as documentation tooling |
| 24 | Short-term rental co-hosting (messaging and pricing) | IDEAS2 #12 | 3 | 3 | 6 | 300-2,500 | L | Later | Check-in window needs a human on call |
| 25 | AI phone receptionist / managed inbound reception | IDEAS2 #1 + ideas3 #10 | 3 | 3 | 6 | 300-2,500 | L | Later | IDEAS2 ranked it first, ideas3 last: availability burden; overflow-only, vendor billed to client |
| 26 | Exam-prep question banks for vocational diplomas | IDEAS2 #15 | 3 | 3 | 6 | 200-2,000 | L | Later | B2B license scales; employer conflict of interest to check |
| 27 | Reviewed training-video localization | ideas3 #4 (cousin: IDEAS2 #8) | 3 | 3 | 6 | 800-1,600 | L | Later | Native reviewer cost can invalidate the margin |
| 28 | Changelog and release-notes writer (Shiplog) | IDEAS #7 + ventures/shiplog | 3 | 3 | 6 | 200-1,500 | M | Later | PRD written; a feature, not a product |
| 29 | Meeting notes and follow-up desk for consultants | IDEAS2 #19 | 2 | 4 | 6 | 200-1,500 | M | Later | Otter, Fireflies, Granola bundle it |
| 30 | White-label browser mini-game licensing | IDEAS #14 | 2 | 4 | 6 | 0-1,500 | M | Later | Six games exist; the agency buyer is hard to reach |
| 31 | Interview-to-SOP packs | ideas3 #7 | 3 | 3 | 6 | 650-1,300 | M | Later | Project revenue, not recurring; owner must attend interviews |
| 32 | KDP workbooks and study guides, disclosed | IDEAS2 #9 | 2 | 4 | 6 | 50-600 | S | Later | Disclosure mandatory; undisclosed volume bans the account |
| 33 | Etsy digital planners, disclosed | IDEAS2 #10 | 2 | 4 | 6 | 50-500 | S | Later | Saturated; AI tag required since 2026 |
| 34 | Grant and subsidy application service | IDEAS2 #5 | 3 | 2 | 5 | 500-3,000 | L | Skip for now | Stale program database is worse than nothing; ideas3 defers it |
| 35 | Pre-accounting and receipt triage for micro-entrepreneurs | IDEAS2 #20 | 2 | 3 | 5 | 300-2,000 | L | Skip for now | Pennylane, Indy, Tiime already do it at the same price |
| 36 | Support knowledge and exception management for shops | ideas3 #6 | 3 | 2 | 5 | 500-1,500 | M | Skip for now | Needs an agency partner; native helpdesk AI may suffice |
| 37 | Podcast localization into French | IDEAS2 #8 | 2 | 3 | 5 | 200-1,500 | M | Skip for now | Voice-clone consent and labeling per host |
| 38 | Uptime monitor with agent diagnosis | IDEAS #9 | 2 | 3 | 5 | 100-900 | M | Skip for now | UptimeRobot free tier is good enough |
| 39 | Game-jam boilerplate generator | IDEAS #6 | 2 | 3 | 5 | 100-800 | M | Skip for now | Game devs are numerous and broke |
| 40 | Original-curation video channel | IDEAS2 #7 | 2 | 3 | 5 | 0-800 | M | Skip for now | YouTube inauthentic-content policy; volume is a liability |
| 41 | LLMargin: LLM spend optimization on % of savings | ventures/llmargin | 2 | 2 | 4 | 0-10,000 | XL | Skip for now | 10-60k per engagement, needs clients above 20k/month spend and pipeline trust |
| 42 | Screenshot-to-Playwright test generator | IDEAS #10 | 2 | 2 | 4 | 200-1,500 | M | Skip for now | One flaky test destroys trust |
| 43 | Course: ship a game with AI agents | IDEAS #12 | 2 | 2 | 4 | 100-1,500 | M | Skip for now | No audience means 5 copies, not 500 |
| 44 | French compliance page generator | IDEAS #8 | 2 | 2 | 4 | 200-1,000 | M | Skip for now | Lawyer review 500-1,500 EUR is the real cost |
| 45 | ActProof: EU AI Act compliance engine | ventures/actproof | 2 | 1 | 3 | 0-5,000 | XL | Skip for now | Sell through DPO consultancies and law firms; long regulatory sales cycle |
| 46 | Micro-acquisition and revival of abandoned SaaS | IDEAS #16 | 2 | 1 | 3 | 100-800 | M | Skip for now | 1-5k capital; the market may be dead, not the owner tired |

## Reading the table

**Do now (12 ideas).** Everything with a score of 8 or more shares one shape:
a buyer who already spends money on the problem, a deliverable you can show before
getting access, and a pipeline that is reading plus verification. Two coding ideas
(Malt gigs, agent-setup consulting) score highest on realism because the demand is
proven, but they are time-for-money. The non-coding ideas in this bucket (catalog
preparation, tenders, quote follow-up, listing optimization, lead lists, review
management) are the ones that can become subscriptions.

**Money vs score.** The largest tickets (LLMargin, ActProof, migration sprints,
corporate micro-training) sit in the middle or bottom of the table: high ceiling,
low probability, or long sales cycle. The table is sorted by probability of getting
paid, not by ceiling. Read the Tier column when choosing between two ideas with the
same score.

**Disagreements resolved.** The AI phone receptionist was IDEAS2's first pick and
ideas3's last. It is scored 3/3 here: the demand is real, the availability burden
on a part-time operator is real too. The newsletter is kept at 7 despite ideas3
deferring it, because it is the only row that builds distribution for every other row.

**Suggested sequence.** One "Do now" service for cash within weeks (tenders or
catalog preparation, both reuse the RepoAtlas verify pattern), the newsletter in the
background for distribution, and no platform-volume play (KDP, Etsy, YouTube) as a
plan. Revisit the XL rows once the first service pays for its own runway.
