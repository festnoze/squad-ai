# PRD: RepoAtlas - fixed-price legacy codebase documentation packs

Status: draft v1. This document is the build contract for the delivery
pipeline, the sales assets, and the quality gates. An agent fleet must be able
to implement everything below without further product decisions.

## 1. Product summary

RepoAtlas is a productized service: a client gives read access to a legacy
repository, and 5 business days later receives an "Atlas Pack": a complete,
verified documentation bundle (architecture, module docs, dependency map,
onboarding guide, debt register) delivered as markdown plus a self-contained
static HTML site. Delivery is executed by a headless Claude Code pipeline;
a human (the operator) does intake, a final review pass, and the client call.

The product being sold is CONFIDENCE, not text: every file path, symbol, and
claim in the pack is machine-verified against the actual code before delivery.
That verification step is the differentiator vs "we ran ChatGPT on your repo".

## 2. Naming and domains

- Working name: **RepoAtlas**
- Domain candidates (verify availability on a registrar, in this order):
  1. repoatlas.dev
  2. repoatlas.com
  3. getrepoatlas.com
  4. code-atlas.dev
- Fallback naming pattern if all taken: `atlas` + dev-word (atlasdocs.dev,
  repo-atlas.io). One domain only; no brand splitting.

## 3. Offer and pricing (metered, not tiered)

A 30k-LOC single repo and a 2M-LOC estate across 40 repositories are not
the same product at different sizes. Two realities drive cost, and the
price schedule mirrors both:
- **fixed overhead per repository** (intake, access, CI wiring, connector
  setup, review context) -> a base fee per repo;
- **volume processed by agents at steeply decreasing marginal cost** ->
  degressive per-kLOC rates.

Meters, measured at intake and printed on every quote:
- **kLOC**: source lines counted by `cloc`, vendored and generated code
  excluded (the exclusion list is shown to the client);
- **repos**: repositories in scope.

| Component | Price |
|---|---|
| Base, per repo | 290 EUR |
| First 50 kLOC of a repo | 14 EUR / kLOC |
| 50-250 kLOC | 6 EUR / kLOC |
| Above 250 kLOC | 2.50 EUR / kLOC |
| Multi-repo engagement | 15% off per-repo totals beyond the 5th repo |
| Refresh retainer | 90 EUR/month per repo, degressive at estate scale |

Worked examples (quotes always show this arithmetic):
- 30k LOC, 1 repo: 290 + 30x14 = **710 EUR** (3 business days)
- 200k LOC, 1 repo: 290 + 700 + 150x6 = **1,890 EUR** (5 business days)
- 1M LOC monorepo: 290 + 700 + 1,200 + 750x2.5 = **4,065 EUR** (10 days)
- Estates (dozens of repos): never quoted blind - an Estate Survey
  (see PLATFORM.md) triages the portfolio first, and packs are quoted
  per prioritized repo with the multi-repo discount.

Rules:
- Fixed price per quote, no hourly billing, 100% refund if the pack fails
  its own verification report (safe because the pipeline enforces it).
- Payment: 50% upfront via Stripe payment link, 50% on delivery.
- The intake `cloc` run is free and its output is the shared truth: if the
  client disputes the meter, the engagement stops before money moves.

## 4. Target customer and channel

- Primary: web agencies (5-50 devs, FR/EU) that inherit client codebases.
  Trigger moments: taking over a project, onboarding devs, pre-audit.
- Secondary: small software companies replacing a departing senior dev.
- Channel (in order of expected yield):
  1. Two PUBLIC sample packs generated from well-known OSS repos, linked
     from the landing page (this is the whole portfolio).
  2. Direct LinkedIn/email outreach to agency CTOs: 10/week, message
     template in section 10.
  3. Malt listing "Documentation de code legacy, prix fixe".

## 5. The deliverable: Atlas Pack spec

Output directory `pack/` with EXACTLY this structure (the packaging step
fails if any file is missing):

```
pack/
  index.html               self-contained site (all md rendered, sidebar nav)
  01_overview.md           what the system does, tech stack, entry points
  02_architecture.md       layers/components + 2-4 mermaid diagrams
  03_modules/<name>.md     one file per detected module (see schema below)
  04_data_model.md         entities, storage, schemas, migrations state
  05_api_surface.md        public HTTP/CLI/library surface, grouped
  06_dependencies.md       internal dep graph (mermaid) + external deps
                           with version risk notes (EOL, majors behind)
  07_onboarding.md         "your first week": setup, run, test, first safe
                           change to attempt, code tour in reading order
  08_debt_register.md      ranked list of risks/debt, each with evidence
  verification_report.md   machine-generated: claims checked, pass rates
```

Content rules (enforced by the QA gate, section 8):
- Every module doc references at least 3 real file paths.
- Every claim of the form "X calls Y" or "X stores Y" must cite a file path.
- No hedging filler ("it seems", "probably") in final output; uncertain
  findings go to a dedicated "Open questions" section per document.
- Mermaid only for diagrams (renders in the static site and on GitHub).
- Language: match the client's (fr/en), set at intake. Never use the
  em-dash character; use "-" or parentheses.

## 6. System architecture

```
run_atlas.py (CLI orchestrator, Python 3.11+, stdlib + PyYAML only)
  stage 1 intake.py     clone/copy repo, cloc, language stats, tree map
  stage 2 mapping.py    agent: split repo into 5-20 modules (JSON)
  stage 3 readers.py    agent fan-out: one reader per module (JSON)
  stage 4 synthesis.py  agents: one per deliverable doc, consuming the
                        module JSONs (never raw code except quoted digests)
  stage 5 verify.py     script + agent QA gates (section 8)
  stage 6 site.py       render markdown to the self-contained index.html
```

- Agents are invoked as headless `claude -p` subprocesses (prompt via stdin,
  same pattern as moneyrace/llm_strategist.py). Every agent call has a
  timeout, one retry, and writes its raw output to `work/logs/` for replay.
- All intermediate state lives in `work/` as JSON; every stage is resumable
  (skip stages whose output JSON already exists, `--force` to redo).
- Config file `atlas.yaml` per engagement: client name, language, tier,
  repo path/URL, exclusions (vendored dirs, generated code), NDA note.

## 7. Agent prompts (verbatim contracts)

### 7.1 Module mapper (stage 2)

```
You are mapping a codebase into modules for documentation.
Repository file tree (depth-limited) and language statistics:
{tree}
{cloc_summary}

Split the codebase into 5 to 20 modules. A module is a coherent area a new
developer would learn as one unit (for example: "auth", "billing", "render
pipeline"). Vendored code, generated files, and lockfiles are excluded.

Reply with ONLY a JSON array. Each element:
{"name": "<kebab-case>", "title": "<human title>",
 "paths": ["<glob or dir>", ...], "guess_purpose": "<one sentence>"}
Every source directory must belong to exactly one module.
```

### 7.2 Module reader (stage 3, one call per module)

The orchestrator feeds the reader the module's file list plus file contents
in chunks (large modules: contents of the 30 most-referenced files, plus
signatures-only extraction for the rest).

```
You are documenting the module "{title}" of a legacy codebase.
Files and contents:
{contents}

Extract facts ONLY. If you are not sure of something, put it in
open_questions instead of stating it. Reply with ONLY a JSON object:
{
 "module": "{name}",
 "purpose": "<2-3 sentences>",
 "entry_points": [{"file": "<path>", "symbol": "<name>", "role": "<why it matters>"}],
 "public_api": [{"symbol": "<name>", "kind": "class|function|endpoint|cli",
                 "file": "<path>", "summary": "<one line>"}],
 "internal_dependencies": ["<other module name>", ...],
 "external_dependencies": ["<package>", ...],
 "data": [{"what": "<entity/table/file format>", "where": "<path>", "note": "<one line>"}],
 "risks": [{"claim": "<specific risk>", "evidence": "<path and why>"}],
 "key_files": [{"path": "<path>", "role": "<one line>"}],
 "open_questions": ["<thing that needs a human answer>", ...]
}
Every "file"/"path"/"where" value MUST be a path that appears in the input.
```

### 7.3 Synthesis writers (stage 4, one per deliverable)

Shared preamble for all writers:

```
You write documentation for paying clients. Input is verified JSON extracted
from their codebase; you may not invent anything not present in the input.
Write in {language}. Confident, plain prose. No filler, no hedging: anything
uncertain goes under a final "Open questions" heading. Cite file paths in
backticks. Diagrams in mermaid fenced blocks. Never use the em-dash
character; use "-" or parentheses.
```

Then per document, for example 02_architecture.md:

```
Using these module summaries:
{modules_json}
Write 02_architecture.md: the system's layers and components, how requests
or data flow through them, and where the boundaries are. Include:
- one mermaid component diagram of modules and their internal_dependencies
- one mermaid sequence or flow diagram of the single most important flow
- a "Boundaries and contracts" section listing the interfaces between modules
Return ONLY the markdown document.
```

(07_onboarding.md prompt additionally requires: environment setup derived
from actual manifest files found at intake, a "first safe change" suggestion
that references a real low-risk file, and a code tour in reading order.
08_debt_register.md prompt requires each item ranked P1/P2/P3 with its
evidence path carried over from reader risks.)

### 7.4 QA fact-checker (stage 5b)

```
You are auditing documentation claims against source code. Claim:
"{claim}" (from {doc}). Relevant source excerpt:
{excerpt}
Reply ONLY with JSON: {"verdict": "supported|unsupported|unclear",
"reason": "<one line>"}
```

## 8. Quality gates (the moat - all must pass before delivery)

G1 **Path existence (script)**: every backticked path and every `path` field
    in generated docs must exist in the repo. Threshold: 100%. Dead paths
    fail the build and re-trigger the offending writer with the error list.
G2 **Symbol existence (script)**: every documented symbol in public_api must
    be found by grep in its claimed file. Threshold: 98%.
G3 **Coverage (script)**: every module from stage 2 has a doc; every doc in
    section 5's structure exists and is non-trivial (>= 40 lines).
G4 **Fact spot-check (agent)**: sample 15 random causal claims ("X calls Y",
    "X stores Y in Z"), run the QA fact-checker with the real code excerpt.
    Threshold: >= 13 supported, 0 unsupported (unclear is tolerated).
G5 **Verification report**: G1-G4 results written to
    `verification_report.md`, shipped IN the pack. This page is also a sales
    asset: it is what justifies the refund guarantee.

## 9. Repo layout to build

```
repoatlas/
  run_atlas.py            CLI: --repo, --config atlas.yaml, --out, --force
  atlas/                  intake.py mapping.py readers.py synthesis.py
                          verify.py site.py prompts.py claude_client.py
  templates/site/         index.html shell + css (no external assets)
  samples/                config for 2 public OSS sample packs
  landing/                one-page static site (section 10)
  tests/                  unit tests: verify.py gates against fixture docs
                          with planted dead paths/symbols; prompts render;
                          resumability (stage skip) works
```

`claude_client.py`: single function `run_agent(prompt, timeout, expect_json)`
wrapping the subprocess call, with logging, retry-once, and JSON extraction
(find first `{`/`[` to last `}`/`]`), mirroring moneyrace/llm_strategist.py.

## 10. Sales assets (also built by agents)

- **Landing page** (static, 1 page): headline "Your legacy codebase,
  documented and verified in 5 days. Fixed price."; the 3 tiers; links to
  both sample packs; the verification-report explanation; a Stripe payment
  link per tier; a Calendly-style link placeholder; FAQ (security: runs
  locally or in client CI, no code retained; NDA on request).
- **Two sample packs**: run the full pipeline on two recognizable OSS repos
  of different stacks (one Python backend, one JS frontend), publish under
  `/samples/` with a banner "generated by the exact pipeline you would buy".
- **Outreach message** (template, FR + EN, <= 90 words): references the
  sample pack for the prospect's stack, offers the Starter tier at a
  first-client price (290 EUR) in exchange for a testimonial.

## 11. Milestones

- M0 (days 1-3): pipeline runs end-to-end on one OSS repo; gates G1-G3 pass.
- M1 (days 4-6): G4-G5 done; both sample packs generated and reviewed.
- M2 (days 7-9): landing page live on the chosen domain, Stripe links wired.
- M3 (weeks 2-4): 10 outreach messages/week; goal: 1 paying client by
  week 4 at 290-490 EUR.

## 12. Acceptance criteria

1. `python run_atlas.py --repo <oss_repo> --config samples/a.yaml` produces
   a complete pack (section 5 structure) with a passing verification report,
   unattended, in under 45 minutes for a 50k LOC repo.
2. Killing the run mid-stage and re-running resumes without redoing
   completed stages.
3. Planting a fake path in a generated doc makes G1 fail the build (test).
4. Total API cost per Starter-tier pack <= 15 EUR (measured and logged).
5. index.html opens offline in a browser with working nav and rendered
   mermaid diagrams.

## 13. Non-goals (v1)

- No web app, no client portal, no accounts: delivery is a zip + hosted copy.
- No automatic repo ingestion from GitHub App permissions (manual
  clone/upload at intake is fine and reassures security-minded clients).
- No docs-as-a-service continuous mode beyond the monthly refresh re-run.
- No translation of code comments, no code modification of any kind.

## 14. Risks

- "Docs are not bought proactively" -> always sell against a trigger event
  (takeover, onboarding, audit); outreach template must ask about the
  trigger, not pitch documentation in the abstract.
- Hallucinated content reaching a client -> gates G1-G4 are the mitigation;
  the refund guarantee is capped exposure.
- A repo too gnarly for the pipeline -> intake stage prints a feasibility
  score (language coverage, vendored ratio); below threshold, decline or
  quote manually. Never silently deliver a thin pack.
