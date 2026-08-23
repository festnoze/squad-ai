# RepoAtlas Platform - "Get back control of your legacy codebase"

Status: vision + build contract v2. Supersedes the positioning of PRD.md
(which remains valid as the execution spec of the first product, the Atlas
Pack). This document defines the advanced idea: a product LADDER where each
offering de-risks and sells the next, all built on one shared technical
asset, the Codebase Fact Graph.

## 1. The reframe

Companies do not wake up wanting documentation. They wake up scared because:
- the only dev who understands billing resigned last month
- every estimate on the legacy system is a guess and every deploy a gamble
- the framework is 4 majors behind and nobody dares to upgrade
- onboarding a new dev takes 4 months of shadowing

That is a CONTROL problem, and control is what management pays real money
for. Documentation is merely the first, cheapest step of a recovery program.
The advanced idea: productize the whole recovery path.

> Positioning sentence: "RepoAtlas gives you back control of a codebase
> nobody fully understands anymore: measure it, document it, make it safe
> to change, modernize it, and keep it under control."

## 2. The product ladder

Seven products, one narrative arc (Understand -> Make safe -> Modernize ->
Evolve -> Stay in control). Each product's OUTPUT is the sales artifact for
the next.

| # | Product | What the client gets | Price | Stage |
|---|---|---|---|---|
| 1 | **Atlas Score** | Control audit of ONE system (up to 3 repos, 250 kLOC): scored report (0-100 on 6 dimensions) + 90-day recovery plan, board-readable | 1,900 EUR fixed | Understand |
| 1b | **Estate Survey** | Portfolio triage across ALL repos: per-repo mini-scores, coupling map, and a depth plan (which repos deserve deep work, which get inventory-only coverage) | 2,900 EUR + 90 EUR/repo | Understand |
| 2 | **Atlas Pack** | The documentation bundle (existing PRD.md), metered per repo | 290 EUR/repo + degressive kLOC rate (710 EUR at 30k, 1,890 at 200k, ~4,000 for a 1M monorepo) | Understand |
| 3 | **Atlas Capture** | Knowledge extraction from the remaining expert(s) before they leave: agent-led structured interviews, verified against code, woven into the docs | 2,900 EUR per expert | Understand |
| 4 | **Atlas Shield** | Safety net: characterization tests + contract tests on the riskiest hotspots, wired into CI, making the codebase safe to change | 6,000-15,000 EUR | Make safe |
| 5 | **Atlas Forge** | Modernization sprints executed by agent fleets under Shield protection: dependency upgrades, framework migrations, dead-code removal, strangler extractions; fixed price per catalog "move" | 10,000-40,000 EUR per program | Modernize |
| 6 | **Atlas Evolve** | Requirement-driven evolution: new features and intentional behavior changes delivered ON the legacy system, planned as spec diffs, executed shield-gated, priced per Behavior Change Ticket | 1,500-6,000 EUR per ticket, or capacity retainer 8,000-20,000 EUR/month | Evolve |
| 7 | **Atlas Tower** | Continuous control: monthly re-score, drift alerts, doc regeneration, dependency/CVE watch, quarterly management report | 490 EUR/month (includes 3 repos) + 60 EUR/repo, 40 EUR/repo beyond 20 | Stay in control |

Notes on the ladder mechanics:
- The Score's 90-day plan IS the quote for Shield and Forge: the audit
  literally generates the pipeline of paid work. This is the classic
  audit-then-remediate model, but agent-executed so margins survive.
- Shield before Forge is a hard rule ("no modernization without a shield").
  It is honest engineering AND it solves the killer risk of fixed-price
  migrations (a gnarly codebase blowing the estimate): the shield makes
  agent-executed changes verifiable, so fixed pricing becomes survivable.
- Tower is where the business compounds: it re-runs everything monthly
  against the fact graph and makes leaving feel like losing the map again.
- Capture is the emotional wedge: it sells itself at the exact moment a key
  developer resigns, at the height of price insensitivity. Marketing hook:
  "A senior dev's notice period is 1-3 months. That is your window."
- Evolve is the destination the whole ladder derisks: it taps the
  DEVELOPMENT budget (the one that pays agencies day rates), not the audit
  budget, and it is only sellable because Score, Capture, and Shield came
  first. It also closes a loop with an existing asset: the Autospec
  spec-to-code factory becomes the forward-engineering engine, pointed at
  a specification recovered from the legacy code instead of a greenfield
  brief (section 4.6).

### Pricing meters (how prices adapt to scale)

A 30k-LOC repo and a 2M-LOC, 40-repo estate are different animals, and flat
tiers would be dishonest in both directions. All prices derive from meters
measured at intake and printed on the quote:
- **kLOC** (`cloc`, vendored/generated excluded, exclusion list shared) and
  **repo count** drive Score/Survey, Pack, and Tower: a base fee per repo
  covers the real fixed overhead (intake, access, CI wiring, review
  context); degressive per-kLOC rates reflect that agents process volume
  at falling marginal cost (Pack: 14 -> 6 -> 2.50 EUR/kLOC by tranche,
  15% off repos beyond the 5th).
- **Hotspots** drive Shield (900-1,800 EUR per protected hotspot by
  complexity); **tickets and their computed impact sets** drive Evolve.
  Both meters are scale-free: an estate simply has more hotspots, the
  meter holds.
- **Estates are never quoted blind.** Above ~3 repos or 250 kLOC, the entry
  product is the Estate Survey: a metadata-level triage of every repo
  (activity, bus factor, coupling, size) producing per-repo mini-scores
  and a depth plan. Deep products then apply only to the prioritized core;
  dormant repos get inventory-level coverage inside the Survey. Depth
  where it matters is both honest engineering and what keeps estate
  quotes defensible.

Money math at modest scale: 2 Scores + 1 Pack + 1 Capture per month
(~8k EUR) + 1 Shield per quarter (~10k) + 1 Forge per quarter (~25k) +
8 Tower retainers (~10k MRR) = roughly 25-30k EUR/month within a year,
still operable solo with agent fleets plus occasional contractor review.
A single Evolve capacity retainer on top (~12k EUR/month) takes the same
book of business past 40k EUR/month; one mid-size Evolve client is worth
the entire tier-1 portfolio. Estates raise the ceiling further: a 35-repo
Estate Survey alone is ~6,000 EUR, and it feeds a multi-repo pipeline of
packs, shields, and a Tower retainer sized in repos, not vibes.

## 3. The shared asset: the Codebase Fact Graph

The architectural upgrade from v1 (one-shot pipeline) to v2 (platform):
every product reads from and writes to a persistent, versioned store of
VERIFIED facts about the client's codebase.

- Nodes: modules, files, symbols, endpoints, entities, dependencies
  (internal and external), tests, owners (from git history), documented
  claims, captured tribal knowledge, known risks.
- Every fact carries: evidence (paths, line ranges, git commits), the
  extraction date, the extractor version, and a verification status (the
  RepoAtlas G1-G4 gates from PRD.md become graph invariants).
- Stored as versioned JSON/SQLite per engagement ("fact snapshots"); a
  snapshot is taken per pipeline run.
- Why it matters commercially:
  - Atlas Score = metrics computed over the graph
  - Atlas Pack = documents rendered from the graph
  - Atlas Capture = human answers added to the graph as first-class facts
  - Atlas Shield = test targets selected by graph queries (hotspots with
    no coverage), tests linked back as protection facts
  - Atlas Forge = change plans validated against the graph, executed only
    where protection facts exist
  - Atlas Tower = DIFFING graph snapshots over time (drift = graph delta)
- The graph never leaves an engagement's encrypted store; facts, not code,
  are retained (same security posture as PRD.md section 10).

## 4. Product specs (what is new vs PRD.md)

### 4.1 Atlas Score - the control audit

Six dimensions, each 0-100, all computed by DETERMINISTIC scripts over the
repo + git history (agents only narrate; numbers are reproducible):

1. **Knowledge risk**: bus factor per module from git author entropy,
   weighted by module criticality (fan-in from the fact graph). The report
   names it plainly: "4 of your 12 modules are effectively known by one
   person; one of them left in March" (from git author activity).
2. **Change risk**: hotspot analysis, churn x cyclomatic complexity, top-10
   riskiest files with their incident potential.
3. **Safety**: test coverage ON THE HOTSPOTS (global coverage is vanity;
   coverage where change happens is safety), CI gate presence.
4. **Currency**: dependency freshness, EOL runtimes, majors behind, open
   CVEs (OSV/pip-audit/npm audit).
5. **Legibility**: doc existence and doc-vs-code drift, naming consistency,
   dead code ratio (static reachability + optional usage traces).
6. **Exit cost**: a EUR estimate of onboarding time and key-person loss,
   derived from dimensions 1-5 with a documented formula. This number is
   what unlocks management budgets.

Deliverable: 15-page report (board-readable, one page per dimension plus
the 90-day recovery plan with priced next steps) plus the raw metrics JSON.
Delivery target: 48h, >= 80% margin, because it is nearly fully automated.

### 4.2 Atlas Capture - knowledge extraction

The flow (1-2 weeks elapsed, ~4h of the expert's time total):
1. Agents read the fact graph and generate TARGETED questions, each anchored
   to real code: "in `payment_retry.py`, retries stop after 3 days; the
   constant is unexplained. Why 3 days, and what breaks if it changes?"
   Generic questions ("describe the architecture") are forbidden by prompt.
2. Interview sessions: async form or recorded call (operator-led, 2x60min);
   answers transcribed.
3. Agents verify each answer against the code where verifiable, mark the
   rest as "testimony", and weave everything into the Pack docs as
   attributed knowledge notes ("per J. Martin, 2026-08: ...").
4. Unanswered high-risk questions ship as a named risk list: the honest
   residue is itself valuable ("these 9 questions now have no owner").

### 4.3 Atlas Shield - the safety net

- Target selection is a graph query: hotspots (dimension 2) with low safety
  (dimension 3), ranked; client approves the list and the per-target price.
- For each target: characterization tests capturing CURRENT behavior
  (golden-master/approval style: feed recorded or synthesized inputs,
  snapshot outputs), not desired behavior; plus contract tests at module
  boundaries the Pack identified.
- Tests must FAIL when behavior changes (mutation-check: the pipeline
  mutates the target and asserts red) - this gate is what makes the Shield
  real rather than theatrical, and it is the anti-"test-qui-passe-a-vide"
  lesson already learned in CUBEFORGE.
- Ships as PRs to the client's CI, with a Shield coverage report added to
  the fact graph.

### 4.4 Atlas Forge - modernization under protection

- A catalog of fixed-price "moves", each a rehearsed agent pipeline:
  dependency major upgrade, framework migration (start with the 3 stacks
  most seen in Scores), dead-code removal with usage evidence, module
  extraction (strangler fig), test-framework consolidation.
- Every move: only executes where Shield facts exist; every agent-produced
  change must keep the Shield green in CI; human review on every PR for the
  first engagements.
- Pricing per move from the catalog, quoted directly inside the Score's
  90-day plan.

### 4.5 Atlas Tower - continuous control (the SaaS)

- Monthly: re-ingest, new fact snapshot, graph diff -> drift report
  ("bus factor worsened in `billing` after these 14 PRs by a single
  author"; "3 new dependencies, 1 already a major behind"; "docs for
  `auth` are now stale: 23 facts changed").
- Doc regeneration as review PRs to the client's docs repo.
- Quarterly management PDF: score trend, risks opened/closed, exit cost
  trend. The chart going the right way is the renewal pitch.
- This is the only product needing a hosted multi-tenant app; everything
  before it runs as local pipelines. Build it LAST, after retainer demand
  is proven by clients asking "can you just keep doing this monthly?".

### 4.6 Atlas Evolve - from reverse engineering to forward engineering

The rung the ladder was building toward: once a system is understood (fact
graph), its tribal knowledge captured, and its hotspots made safe to change
(Shield), it can be EVOLVED: new requirements delivered on the legacy
system itself, incrementally, without the rewrite nobody can afford. This
is where reverse engineering turns into forward engineering.

**The Recovered Specification.** A generated, human-editable VIEW over the
fact graph: a behavior catalog per module, one entry per observable rule:

```
BHV-142: when a payment fails 3 times within 3 days, the subscription is
suspended. [evidence: src/billing/payment_retry.py:88] [pinned by: CT-217]
[knowledge: per J. Martin 2026-08, the 3-day window mirrors the PSP's own
retry policy; changing one without the other double-charges]
```

Every behavior links its code evidence, the characterization test that pins
it, and any captured knowledge attached to it. The spec regenerates from
the graph after every change; human annotations survive regeneration by ID.
The spec extractor ships early (as a Pack deliverable from Phase B), so by
the time Evolve is sold, the client's spec already exists: the pitch
becomes "you have the spec of your own system for the first time in years;
now edit it".

**Behavior Change Tickets (BCT).** New requirements never go straight to
code. A planning agent converts each requirement into spec edits: behaviors
added, changed, or removed, each becoming a ticket: {from_behavior (or
none), to_behavior, acceptance criteria, retired characterization tests and
their replacements, affected modules (a GRAPH QUERY, so the impact set is
computed rather than guessed), risk class, fixed price}. The client signs
the ticket list: they review BEHAVIOR DIFFS, not code diffs. That sentence
is the product's headline.

**The execution loop per ticket:**
1. Write the acceptance test for to_behavior; confirm it is RED on the
   base branch (the red run is stored as evidence).
2. Plan the change from the graph's impact set.
3. Agents implement. The Shield must stay green EXCEPT the characterization
   tests the ticket explicitly retires; each retired test is replaced by
   the new acceptance test, and the mapping is recorded on the ticket.
4. Graph, spec, and Pack docs regenerate; the client reviews the spec diff.
5. Ticket closes when acceptance is green, the Shield is green, and the
   spec diff matches what was signed.

**Clean definitions the client understands:** Forge = spec-invariant change
(same behaviors, better internals). Evolve = spec-changing change (new
behaviors, on purpose, one ticket at a time). Any change to a pinned
behavior WITHOUT a ticket is by definition a bug, and CI blocks it (G11).
This vocabulary alone is worth money: it ends the "is this a bug or did we
change it?" arguments that poison legacy maintenance.

**Why this is the big-money rung.** Score, Pack, and Shield tap audit and
quality budgets (thousands). Evolve taps the development budget (the one
that pays agencies 500-900 EUR/day) with a promise no agency makes: fixed
price per behavior change, machine-verified non-regression on every
behavior NOT in the ticket, and documentation that is current by
construction after every change. The flywheel: each cycle updates graph,
spec, docs, and Shield, so the system never decays back out of control,
and Tower charts the trend. Control, once regained, compounds.

**Reuse.** The forward-engineering side adapts the existing Autospec
factory (PM/PO/Dev spec-to-code agents): Autospec generates code from a
spec for greenfield projects; Evolve is the same engine pointed at a
recovered spec, executing inside a Shield. RepoAtlas (reverse) and
Autospec (forward) close into one loop.

**Hard sales gate.** Evolve is only sold on systems that have been through
Score + Shield, and a ticket only starts if its impact set has Shield
coverage. Selling evolution without the safety net is how fixed prices
die; the ladder IS the derisking.

## 5. New agent prompts (additions to PRD.md section 7)

### 5.1 Interview question generator (Capture)

```
You prepare interview questions for the developer who knows this legacy
codebase best, to capture knowledge before it is lost. Verified facts and
open questions from the analysis:
{facts_and_open_questions_json}
Generate 15-25 questions. HARD RULES:
- Every question must anchor to a specific file, symbol, constant, or
  decision visible in the facts (cite the path in the question).
- Ask about intent, history, and hazards ("why", "what breaks if", "what
  almost happened"), never about what the code literally does (we can read).
- Rank by risk: knowledge that, if lost, is most expensive to rediscover.
Reply ONLY with JSON:
[{"rank": <int>, "anchor": "<path or symbol>", "question": "<text>",
  "why_it_matters": "<one line>"}]
```

### 5.2 Answer verifier (Capture)

```
You verify an expert's statement about their codebase against the code.
Statement: "{answer}" (about {anchor}).
Relevant code excerpt:
{excerpt}
Reply ONLY with JSON: {"status": "corroborated|contradicted|unverifiable",
"note": "<one line>"}. "contradicted" requires the excerpt to actually
conflict; memory being imprecise about details is "unverifiable".
```

### 5.3 Characterization test writer (Shield)

```
You write characterization tests that pin down the CURRENT behavior of
legacy code, so it can be changed safely later. Target: {symbol} in {path}.
Code and its direct dependencies:
{code}
Sample inputs (recorded or synthesized, client-approved):
{inputs_json}
Write {framework} tests that:
- assert what the code DOES today, including behavior that looks like a bug
  (mark those with a comment "characterization: possibly unintended")
- cover the branches reachable from the sample inputs
- use golden/approval snapshots for complex outputs
- never assert on private internals, only observable behavior
Return ONLY the test file content.
```

### 5.4 Score narrator (Score)

```
You write one section of a codebase control audit for a non-technical
executive. Dimension: {dimension}. Computed metrics (deterministic, do not
recompute or adjust):
{metrics_json}
Write in {language}, max 350 words: what the numbers mean for the business
(estimation reliability, hiring, incident risk, exit cost), the single most
important finding with its evidence, and what the 90-day plan does about
it. Numbers must be quoted exactly as given. No fear-mongering adjectives;
the numbers carry the weight. Return ONLY the markdown.
```

### 5.5 Behavior extractor (Evolve, builds the Recovered Specification)

```
You extract the observable behaviors of a module into a specification
catalog. Module facts, code excerpts, and existing tests:
{inputs}
List every externally observable behavior in given/when/then form, one
entry per rule, including edge cases and error paths. Reply ONLY with JSON:
[{"behavior": "<given/when/then, one sentence>",
  "evidence": ["<path:line>", ...],
  "pinned_by": ["<existing test name>", ...],
  "confidence": "code_verified|inferred",
  "note": "<ambiguity worth a human question, or null>"}]
Behaviors are facts from the inputs, never intentions. If a behavior looks
unintended, record it anyway with a note; deciding is not your job.
```

### 5.6 Requirement-to-ticket planner (Evolve)

```
You convert a client requirement into Behavior Change Tickets against a
recovered specification. Requirement (client's words): "{requirement}"
Relevant spec entries: {spec_entries_json}
Impact set from the fact graph: {impact_json}
Reply ONLY with JSON:
[{"from_behavior": "<BHV-id, or null if this is a new behavior>",
  "to_behavior": "<given/when/then>",
  "acceptance_criteria": ["<testable criterion>", ...],
  "retires_tests": ["<CT-id>", ...],
  "affected_modules": ["<module>", ...],
  "risk": "low|medium|high",
  "open_questions": ["<what the client must decide first>", ...]}]
Split until each ticket is independently shippable and testable. A ticket
with open_questions is a draft: it cannot be priced or started until they
are answered. Never merge two behavior changes into one ticket.
```

## 6. Quality gates (additions)

- G6 **Score reproducibility**: re-running the audit on the same commit
  yields identical numbers (all metrics are pure functions; agents narrate
  but never compute).
- G7 **Shield mutation gate**: a characterization test suite is only
  delivered if planted mutations in each target turn CI red (the
  test-that-passes-empty is the product's death; this gate is automated).
- G8 **Capture integrity**: every knowledge note in the docs carries its
  attribution, date, and verification status; contradicted statements are
  surfaced to the expert, never silently dropped or silently kept.
- G9 **Forge non-regression**: no Forge PR merges with a red Shield;
  no Forge move is sold on a target without Shield facts.
- G10 **Spec fidelity**: every spec behavior carries evidence, and on
  Shield-covered modules at least one pinning test; a sampled audit of 15
  behaviors per regeneration must show zero unsupported entries (same
  method as the Pack's G4 fact spot-check).
- G11 **No silent behavior change**: CI blocks any PR that modifies or
  deletes a characterization test without referencing a signed BCT id;
  the retired-test-to-acceptance-test mapping lives on the ticket. This is
  the contractual line between "bug" and "change".
- G12 **Acceptance-first**: an Evolve PR may only open after its acceptance
  test exists and was recorded RED on the base branch; the red run is
  attached to the ticket as evidence.

## 7. Market position (who else is in this space)

- CodeScene: hotspot and behavioral analysis SaaS - a tool the client must
  learn and staff. Atlas Score borrows the churn-x-complexity idea but
  sells the interpreted OUTCOME with a plan, not a dashboard.
- CAST, vFunction: enterprise application intelligence and replatforming,
  6-7 figure engagements, ignores the 10-200 dev mid-market entirely.
- Moderne/OpenRewrite: recipe-based mass refactoring - the closest analog
  to Forge; it is a platform for teams who staff the work. Forge is the
  same idea delivered as an outcome, with the Shield as the differentiated
  safety story.
- Dev agencies and ESNs: the incumbents for "evolve the legacy system"
  budgets, at 500-900 EUR/day, with no non-regression guarantee and docs
  that die the day the mission ends. Atlas Evolve competes on outcome
  pricing per behavior change, machine-verified non-regression, and
  documentation current by construction.
- The gap being claimed: outcome-priced, agent-executed, human-reviewed
  legacy recovery for mid-market EU companies, with knowledge capture
  (nobody productizes the departing-dev moment) and spec-diff-reviewed
  evolution (nobody lets the client sign behavior diffs instead of
  trusting code reviews).

## 8. Roadmap (sequenced by cash, not by architecture)

- **Phase A (weeks 1-6)**: Atlas Score + Atlas Pack. The Score is mostly
  deterministic scripts (fast to build, easiest to trust); the Pack exists
  per PRD.md. Fact graph v1 = the JSON store both share. Sell immediately;
  Capture can be delivered semi-manually from week 4 (the question
  generator is trivial once the graph exists; the interview is human).
- **Phase B (weeks 6-14)**: Atlas Shield (test writer + mutation gate).
  First Shield sold to a Pack/Score client at cost if needed: the case
  study ("we made their scariest module safe to change, here is the
  mutation report") is worth more than the first margin.
- **Phase C (weeks 14-26)**: Atlas Forge catalog, starting with the single
  most-requested move from Phase A/B clients (do not guess the catalog;
  let the Scores reveal it).
- **Phase D (month 6+)**: Atlas Tower, built only on demonstrated pull
  (>= 3 clients asking for recurring re-runs). Until then, Tower is a
  manual monthly re-run sold as a retainer, which is fine.
- **Phase E (month 8+)**: Atlas Evolve, only for clients that have been
  through Score + Shield. The behavior extractor (5.5) ships earlier, in
  Phase B/C, as a Pack deliverable, so active clients already own their
  recovered spec by then. Start with ONE low-risk paid pilot ticket at an
  existing client; the Autospec factory is adapted, not rebuilt. Evolve is
  the last rung on purpose: it carries the most delivery risk and deserves
  the most accumulated safety.

## 9. Acceptance criteria for the v2 platform core

1. Fact graph: two snapshots of the same repo at different commits diff
   into a human-readable drift report in under 5 minutes.
2. Atlas Score on a 100k LOC repo: complete scored report in under 2 hours
   unattended, identical numbers on re-run (G6 test).
3. Every number in a rendered Score report appears verbatim in the metrics
   JSON (script-checked, no narrator-invented figures).
4. Shield pipeline on a chosen target: generated tests pass on HEAD, and
   each of 5 planted mutations turns them red (G7 test).
5. A Capture round-trip: facts -> >= 15 anchored questions -> mock answers
   -> verification statuses -> knowledge notes present in the regenerated
   Pack with attribution (G8 test).
6. All of the above reuse the same claude_client.py, verification gates,
   and evidence conventions as PRD.md (one platform, not five scripts).
7. Recovered spec: a module's behavior catalog regenerates after a code
   change with human annotations preserved by ID, and a G10 sampled audit
   passes with zero unsupported behaviors.
8. G11 gate test: a PR deleting a characterization test WITHOUT a BCT
   reference is blocked in CI; the identical PR with the reference passes.
9. Evolve loop test on a fixture repo: one BCT goes red-acceptance ->
   implementation -> green acceptance + green Shield -> regenerated spec
   whose diff contains exactly the ticket's behavior change and nothing
   else.

## 10. Non-goals (v2)

- No self-serve SaaS before Tower demand is proven; no dashboards before
  clients ask for them twice.
- No rewrite engagements ("we will rebuild it in X"): Forge modernizes in
  place; rewrites are where fixed prices go to die.
- No US enterprise sales; EU mid-market until the ladder is proven.
- No claim of replacing senior engineers: the operator reviews everything;
  the pitch is control and safety, never "no humans needed".
