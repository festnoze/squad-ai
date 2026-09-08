# PRD: LLMargin - LLM spend optimization paid as a share of verified savings

Status: draft v1. Ambitious tier: hard to access (needs clients with real
LLM spend and the trust to touch their pipelines), but the performance-fee
model means deal sizes of 10-50k EUR each and an unbeatable sales pitch
("you pay only out of money we already saved you"). Builds directly on the
existing Dspy-er work (Langfuse + DSPy/OPRO optimization loop).

## 1. Product summary

LLMargin connects read-only to a company's LLM observability data (Langfuse,
OpenTelemetry GenAI, LiteLLM logs, or raw provider usage exports), has agents
find where money burns without buying quality, proves each optimization
against an eval harness built for the client's actual tasks, ships the
changes as reviewed pull requests, and gets paid a percentage of savings
verified against provider invoices.

The core insight: most teams overpay 30-60% through a handful of recurring,
detectable patterns (flagship models on trivial routes, prompt bloat,
absent caching, unbounded outputs, retry storms, recomputed embeddings).
Finding them is agent work. What clients actually lack is the CONFIDENCE to
change anything without breaking quality: the sellable asset is the eval
harness plus a measurement protocol, not the tricks.

## 2. Naming and domains

- Working name: **LLMargin** (LLM + margin)
- Domain candidates (verify availability, in this order):
  1. llmargin.com
  2. llmargin.dev
  3. tokentrim.dev
  4. inferencecut.com

## 3. Business model

| Phase | What | Price |
|---|---|---|
| P0 Free audit | Agents analyze 30 days of usage metadata, deliver a Savings Map: itemized, evidence-backed estimate per pattern | 0 (the sales weapon) |
| P1 Eval harness | Task-specific eval suites + golden sets + agreed quality thresholds, wired into their CI | 4,900 EUR fixed (waived above 30k EUR/month spend) |
| P2 Optimization sprints | Changes shipped as PRs, each gated by eval parity | included |
| P3 True-up | Monthly: verified savings vs the frozen baseline, invoice 25% of savings for 12 months, capped at 60k EUR per engagement | performance fee |

- Target client: companies spending >= 20k EUR/month on LLM inference
  (AI-native startups post-seed, scale-ups with genAI features, agencies
  running LLM products for clients). Below 10k/month, decline: the fee
  cannot pay for the attention.
- Money math: client at 60k EUR/month, 40% verified savings = 24k/month
  saved, fee 6k/month for 12 months = 72k, capped at 60k. Three concurrent
  engagements is a very good year for a solo operator.

## 4. Access strategy (the hard part, stated honestly)

Nobody hands pipeline access to a stranger. In order of expected yield:
1. **The P0 audit requires only metadata**, not payloads: model names,
   token counts, latencies, route labels, costs. This collapses the trust
   barrier for the first step; the Savings Map earns the deeper access.
2. **Langfuse ecosystem**: you already operate in it (Dspy-er). Publish the
   audit tooling's non-secret parts as OSS ("langfuse-cost-audit"), write
   the definitive "we cut an LLM bill 43%" teardown post with real
   (anonymized) numbers from your own projects, be present where Langfuse
   users ask cost questions.
3. **Warm intros through agencies** already delivering LLM projects: they
   have clients with runaway bills and no bandwidth; offer them a referral
   cut (10% of fees).
4. Cold outreach only to companies that publicly discuss their LLM usage
   (engineering blogs, conference talks): the message references their own
   published numbers.

## 5. Product spec: four components

C1 **Connectors + normalizer**: pull usage metadata from Langfuse API,
   OTel GenAI spans, LiteLLM proxy logs, and provider usage CSV exports
   (Anthropic/OpenAI dashboards). Normalize into one schema:
   `calls(ts, route, model, in_tokens, out_tokens, cached_tokens, cost,
   latency_ms, status, retry_of, metadata)`. "Route" = the client's logical
   task label; when absent, an agent proposes route clustering from
   available metadata for the client to confirm.

C2 **Savings analyzers** (each one a typed, testable detector producing
   Findings with evidence and a EUR/month estimate):
   - `model_overkill`: routes where a cheaper model likely suffices
     (flagged by task shape; only PROVEN later by evals, estimates are
     labeled "pending eval")
   - `prompt_bloat`: static prompt sections dominating input tokens;
     repeated few-shot blocks; unpruned conversation history
   - `no_cache`: identical or near-identical calls (hash and simhash on
     metadata dimensions) not using provider prompt caching
   - `unbounded_output`: routes without max_tokens or with outputs far
     beyond what downstream consumes
   - `retry_storm`: retries and timeouts burning paid tokens
   - `embedding_rework`: re-embedding unchanged content
   - `dead_routes`: spend on features with no downstream reads
   Each detector's estimate methodology is documented in the Savings Map
   (auditability of the estimate is part of the sales credibility).

C3 **Eval harness generator**: per route, build the eval that makes change
   safe: golden set curated from real traffic (client approves samples),
   task-appropriate scoring (exact/schema checks where possible, LLM-judge
   with the prompt in section 7.3 where not, always with judge-agreement
   spot-checks), non-inferiority threshold agreed in writing (e.g. "candidate
   must score >= baseline - 2 points on 95% CI"). DSPy/OPRO loops (the
   Dspy-er codebase) then optimize prompts against these evals: shorter
   prompts, cheaper models, same scores.

C4 **Measurement and true-up**: the part that prevents disputes.
   - Baseline: cost per route per 1k requests, frozen over the 30 days
     before the first shipped change, at the provider prices of that window.
   - Savings: (baseline unit cost - current unit cost) x current volume,
     PRICE-NORMALIZED: provider price cuts are excluded by recomputing both
     sides at a fixed price table agreed at signature; volume growth is the
     client's, only unit costs count.
   - Verified against provider invoices monthly; the true-up report shows
     the full calculation and is contractually the invoice basis.
   - New routes added after signature are out of scope unless both agree.

## 6. Architecture

- Delivery-first: C1+C2 run as a local CLI against exported data for P0
  audits (no hosting, no data custody, runs in the client's environment if
  they prefer: `python -m llmargin.audit --source langfuse --days 30`).
  A hosted dashboard is explicitly a LATER phase, only when recurring
  monitoring for P3 makes it worth building.
- Stack: Python 3.11+, DuckDB for the normalized call table (fast local
  analytics on millions of rows), pydantic models for Findings, headless
  Claude agents (same claude_client.py pattern) for route clustering,
  prompt rewriting, and report writing; Dspy-er imported as the
  optimization engine rather than rebuilt.
- Repo layout:

```
llmargin/
  llmargin/
    connectors/     langfuse.py otel.py litellm.py provider_csv.py
    schema.py       normalized call model + DuckDB loader
    detectors/      one module per analyzer in C2, common Finding type
    evals/          harness generator, judge runner, golden set tooling
    optimize/       wrappers around Dspy-er loops, PR builder
    measure/        baseline.py trueup.py price_tables/
    report/         savings map + true-up report renderers (md + html)
  cli.py            audit / harness / optimize / trueup subcommands
  tests/            fixture traffic with planted waste patterns; every
                    detector must find its planted pattern and estimate
                    within 15% of the planted ground truth
```

## 7. Agent prompts (verbatim contracts, abbreviated set)

### 7.1 Route clusterer (C1)

```
You are grouping LLM API calls into logical routes (one route = one product
task). Call metadata sample (JSON, payloads not included):
{sample_json}
Available signals: model, token count distributions, latency, call-site
metadata keys, temporal patterns. Propose 3-15 routes. Reply ONLY with JSON:
[{"route": "<kebab-case name>", "match": {"<metadata_key>": "<value or
pattern>"}, "rationale": "<one line>", "est_share_of_cost": <0..1>}]
Shares must sum to ~1.0. Do not invent metadata keys not present in the
sample.
```

### 7.2 Prompt reducer (C3/optimize, per route)

```
You reduce the cost of an LLM prompt WITHOUT changing its behavior.
Current prompt template (input tokens: {n}):
{prompt}
Task description: {task}. Observed output uses: {output_notes}.
Produce a functionally equivalent template that is materially shorter:
remove redundancy, collapse verbose instructions, drop few-shot examples
ONLY if you flag them for eval verification. Reply ONLY with JSON:
{"prompt": "<new template>", "removed": ["<what and why>", ...],
 "risk_flags": ["<anything that could change behavior>", ...]}
Never remove: output format contracts, safety constraints, variables.
```

### 7.3 Eval judge (C3)

```
You are scoring an AI output for the task: {task_description}.
Input: {input}
Reference (known-good) output: {reference}
Candidate output: {candidate}
Score the candidate 0-10 on: does it accomplish the task as well as the
reference for a real user (format compliance, factual consistency with the
input, completeness). A different-but-equally-good answer scores high;
penalize only real regressions. Reply ONLY with JSON:
{"score": <0-10>, "regression": "<one line, or null>"}
```

### 7.4 Savings Map writer (C2 report)

```
You write an executive savings report from verified findings. Findings
(JSON, each with evidence and methodology):
{findings_json}
Client context: {context}. Currency: EUR. Write the Savings Map in
{language}: a one-paragraph summary with the total range, then one section
per finding ordered by EUR impact: what happens today (cite the numbers),
what changes, estimated monthly saving with the estimate's basis, what
could go wrong and how the eval harness de-risks it. Estimates pending
eval verification must say so. Conservative tone; ranges, not points; no
promises. Return ONLY the markdown.
```

## 8. Quality gates (non-negotiable)

G1 No optimization ships without eval parity: the PR template embeds the
   eval run (baseline vs candidate scores, threshold, sample size); the
   pipeline refuses to open a PR below threshold.
G2 Every Savings Map number traces to a computation over the DuckDB table,
   reproducible by rerunning the CLI on the same export (no hand-waved
   estimates; detectors are tested against planted fixtures).
G3 Payloads policy: prompt/output CONTENT is accessed only in P1+ with a
   signed DPA, processed in the client's environment when requested, and
   never retained after golden-set approval. P0 audits are metadata-only,
   stated on page 1 of the report.
G4 True-up math is deterministic code with the price table checked into the
   engagement repo; both parties can rerun it.
G5 Judge reliability: every LLM-judge eval includes a 20-sample human (or
   client) agreement check before it can gate a PR; below 80% agreement,
   the eval is redesigned, not used.

## 9. Milestones

- M0 (weeks 1-2): connectors + detectors running on YOUR OWN data (Dspy-er
  and Autospec Langfuse projects); fixture test suite; the CLI audit works
  end-to-end offline.
- M1 (weeks 2-3): Savings Map report polished; run it on 2 friendly
  external datasets (agency contacts) free, collect testimonial numbers.
- M2 (weeks 3-5): eval harness generator + one full optimization loop
  proven on your own project with before/after cost and score; publish the
  teardown post; OSS the audit CLI skeleton.
- M3 (weeks 5-8): outreach per section 4; goal: 2 signed P0 audits with
  >= 20k/month spend; 1 converts to a fee engagement.
- M4: contract template (measurement protocol as annex) reviewed by a
  lawyer BEFORE the first performance-fee signature.

## 10. Acceptance criteria

1. `python -m llmargin.audit --source fixtures/planted --days 30` finds all
   7 planted waste patterns and estimates each within 15% of ground truth.
2. The full P0 audit on a 2M-call export runs locally in under 10 minutes.
3. An optimization PR is blocked automatically when the candidate scores
   below the non-inferiority threshold (test with a sabotaged prompt).
4. True-up: given fixture baseline + current month + price table, the
   computed invoice amount matches the hand-computed expected value; a
   provider price cut in the fixture changes savings by exactly zero.
5. The Savings Map renders to markdown and HTML with every number linked to
   its finding id.

## 11. Non-goals (v1)

- No hosted always-on SaaS, no dashboards, no self-serve signup: this is a
  high-touch productized service with a CLI core. SaaS-ification is a
  later decision, made only from inside paying engagements.
- No GPU/self-hosting migrations, no fine-tuning or distillation projects
  in v1 (huge scope; sell as a separate engagement later).
- No provider arbitrage advice beyond eval-verified model routing.
- No claims about quality improvements: the promise is equal quality,
  lower cost; anything else muddies the measurement protocol.

## 12. Risks

- Attribution disputes eat the relationship -> the frozen baseline, fixed
  price table, and code-computed true-up (G4) exist for this; walk away
  from clients who resist the protocol at signature time.
- Provider price cuts shrink the perceived value -> price normalization
  (C4) keeps the fee fair, and cheaper tokens make clients spend on more
  volume anyway (historically true).
- Client's own team does the fixes after the free Savings Map -> acceptable
  loss (the map without the eval harness is a to-do list they will fear
  to execute); waive-the-harness-fee tactic only above 30k/month spend.
- One bad shipped regression destroys the model -> G1 and G5 exist for
  this; the first three engagements get manual review of every PR on top
  of the gates.
