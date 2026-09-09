# PRD v5 : agents that choose their information and discover their own rules

Extension of PRD v2 (the base), v3 (the ladder), v4 (every market). It answers a challenge raised on
2026-09-08 after the engine wave: the build so far evaluates agents honestly and generalises across
markets, but **the knowledge is written by us** (hand-coded detectors, hand-coded families) and **every
agent sees the same information**. v5 makes both into things the optimizer searches over:

1. **The sensor gene**: which information an agent consumes is part of its genome, with a cost.
2. **The hypothesis layer**: agents formulate structured rules, the engine tests them, the hive stores
   the survivors as shared, reusable insights.
3. **Minute-grid datasets with timestamped sources**, so "watch the ten minutes after a news of this
   type" is a testable statement.
4. **Workflow agents**: an agent is a small deterministic graph of steps whose structure evolves.

Nothing already built changes. `docs/CONTRACTS_V2.md` gains section 18 through amendment C1c before the
agents wave starts; the engine gets one hook (the per-agent sensor selection in the observation builder)
applied by gate G2. `docs/PLAN_V3_WAVES.md` carries the revised waves.

Written 2026-09-08. Every data source named below was probed from this machine that day.

---

## 0. What this changes about the question the product answers

v2 asked "which agent beats the market". v5 asks, in addition: **which information diet and which
discovered rules make an agent beat the market, on markets it never saw, and does that knowledge
transfer** across categories, venues and asset classes. A rule such as "political markets on Manifold
overprice the favourite by about four points in the last week" or "after a Hacker News story with more
than 200 points naming a company, its stock moves within thirty minutes" is a first-class object: it
has an author, a birth date, a test record with a confidence interval, a null, and a track record on
held-out data. Agents that produce rules which survive are rewarded; rules that survive become features
every agent may use.

---

## 1. The sensor gene

### 1.1 Sensors

A **sensor** is a named, versioned view of as-of information with a declared cost in research units per
bar. The observation builder assembles an agent's observation from its **sensor set** and nothing else;
what is not sensed is not seen. The catalogue at launch:

| Sensor | Source (verified) | Granularity | Cost |
|---|---|---|---|
| `tape` | the instrument's own bars (always on) | grid | 0 |
| `microstructure` | last trades, bid and ask where known | grid | 1 |
| `volume_profile` | volume z-scores, open interest, funding | grid | 1 |
| `cross_asset` | prices of the cluster's other markets and instruments | grid | 1 |
| `calendar` | day of week, session time, hours to close, release proximity | grid | 0 |
| `wiki_daily` | Wikipedia Current events, linked items | day, 6 h lag | 1 |
| `comments` | Manifold comments on the market | ms | 1 |
| `hn` | Hacker News stories and comments (Algolia `search_by_date`, full history, second precision; `numericFilters=created_at_i`) | s | 2 |
| `gdelt_recent` | GDELT DOC 2.0 (`seendate`, 15-minute granularity, last 3 months, one call per 5 s) | 15 min | 2 |
| `filings` | SEC EDGAR submissions, acceptance time | s | 2 |
| `macro_releases` | ALFRED vintages and the release calendar | release time | 1 |
| `wiki_asof` | point-in-time article revisions on the market's subjects | day | 3 |
| `hive_insights` | the rules of section 2 visible at `now` | bar | 1 |
| `hive_reputation` | other agents' reputations | bar | 1 |
| `memory` | the agent's own memory | bar | 0 |

Every sensor is as-of by construction (the builder applies the safety lag of the source), and the
poisoned-future test of v2 is extended to every sensor. A sensor's output is a typed, integer feature
block with a version hash; the observation records which sensors produced it, so a run replays.

### 1.2 The gene

`Genome.sensors: tuple[str, ...]` plus per-sensor parameters (windows, thresholds). The research budget
of v2 becomes the **sensor budget**: an agent pays the sum of its sensors' costs every bar, out of a
per-generation allowance; an agent whose sensors do not translate into skill loses allowance
(v2's research-penalty rule, generalised). Mutation adds, removes or re-parameterises a sensor. The
behavioural descriptors for MAP-Elites gain "information diet" (which sensor families are on), so the
archive keeps a volume-reader, a news-reader and a cross-asset-reader alive even when one dominates.

### 1.3 Why it matters for the ensemble

Diversity of information is what makes a stacker beat its members. With one shared observation the
population converges on the same view of the world; with sensor genes the coop mechanic has something
to aggregate.

---

## 2. The hypothesis layer

### 2.1 A rule

A **rule** is a structured, testable statement:

```
Rule(
  id, author_agent_id, born_at_ms,
  scope:      kinds, providers, categories, tags        # where it claims to hold
  condition:  conjunction of predicates over as-of features (sensor outputs), e.g.
              category == politics AND hours_to_close < 168 AND price_bp > 7000
              or: hn_story_points > 200 AND hn_mentions_subject AND minutes_since_story < 30
  claim:      one of
              bias(direction, magnitude_bp)              # the price is off by about this much
              drift(horizon, direction, magnitude_bp)    # the price will move this way within horizon
              volatility(horizon, factor_ppm)            # the price will move more than usual
  horizon_ms, min_support
)
```

Rules are data (`schemas/rule.v1.json`), never code. A rule's predicates come from a closed vocabulary
of feature names (the sensor blocks of section 1) and comparison operators, so a rule can be evaluated
deterministically on any bar of any dataset.

### 2.2 Who proposes rules

- **The symbolic miner** (cheap, deterministic, always on): beam search over conjunctions of up to
  three predicates on the training fold, scored by lift with the statistics module, with a support
  floor and a Bonferroni-style budget for the number of candidates tried. It finds the "Friday evening"
  and "favourite-longshot per category" kind of effect without anyone writing it.
- **Agents**: any agent may emit a `propose_rule` action (the scripted families emit rules from their
  own parameters when their memory shows a stable effect; LLM agents write rules in the vocabulary from
  their observations and lessons). Proposing costs sensor budget.
- **The detectors of v3** (rung 2) emit their findings as rules too, so hand-written analysis and
  discovered analysis live in the same ledger and are compared on the same footing.

### 2.3 How rules are tested and promoted

Every proposed rule goes through the **rule tester**, which is a projection of the dataset:

1. Evaluate the condition on every bar of the **training fold** (as-of); measure the claim (realised
   bias, drift or volatility) on the matches; report lift, block-bootstrap interval, permutation null,
   support.
2. If the claim holds on the **fit fold**, evaluate on the **replicate fold** the same way (the rolling
   pair inside evolution, the headline train / validation pair for the live book and for claims): a rule
   is **promoted** only if its claim holds out of time on the replicate fold **and** it passes
   Benjamini-Hochberg false discovery rate control at q = 0.05 within its **pre-registered hypothesis
   family**, whose candidate count is journaled (contract 18.2, decision D-R8, ruling R238; this step
   first read "the validation lower bound clears zero after deflation for the number of rules tested").
3. Promoted rules enter the **hive** as `Insight` entries with `visible_from_ms = fit_t1_ms +
   interval_ms`, the first bar strictly after the last bar the promotion read (ruling R238; the first
   form, `now + one bar`, would let a rule fit on validation outcomes be traded on the same fold), their
   test record, and a rolling **live track record** updated at every later bar where the condition
   fires (the rule keeps being scored after promotion; a rule whose live record decays is demoted).
4. The sealed test fold is never touched by the tester; a claim on the sealed test may include the
   rules an agent used, and the claim record lists them.

### 2.4 How rules are used

- The `hive_insights` sensor exposes the promoted rules that fire on the current bar, with their
  current lift and interval, as a feature block. A `rule_follower` family trades on them directly; the
  `calibrator` and `newsbayes` families take them as priors; learned policies get them as features.
- Evolution rewards the **author**: an agent whose rule is promoted and holds its live record receives
  a fitness bonus and sensor allowance; an agent whose rules keep failing pays. This is how "building
  knowledge" becomes a selected behaviour rather than a hope.
- The UI shows the **rule ledger**: every rule, its author, its condition in words, its test record,
  its live record, where it fires on a chart.

### 2.5 What is not a rule

Free text. LLM "lessons" of v2 stay as text in the hive, but only a rule in the vocabulary gets tested,
promoted and rewarded. That is deliberate: the product rewards knowledge that can be checked.

---

## 3. Minute-grid datasets and timestamped sources

### 3.1 Grids

Three grids, one per dataset (the one-grid-per-run rule of v2 holds): daily (the current `y2026`),
hourly (liquid markets and finance), and **minute** for the instruments and windows where the
sub-hour hypotheses live: Kalshi (1-minute candlesticks are published), crypto on Binance (1-minute
klines, a full year is about 525 000 bars per pair), Manifold (bets are timestamped to the millisecond
and resample to any grid).

### 3.2 Timestamped sources

Only sources with a real publication timestamp enter a minute dataset: Hacker News (second), GDELT
(15 minutes, recent three months), Manifold comments (millisecond), SEC filings (second), Binance
funding and liquidations (exact times), the release calendar (exact times). Wikipedia daily pages stay
in the daily and hourly datasets only; a minute dataset never carries a source whose timestamp is
coarser than its grid.

### 3.3 The event-study detector at minute horizons

The news-lead study of v3 runs at horizons of 1, 5, 10, 30 and 60 minutes on minute datasets, per
source and per story feature (points, comment count, subject match). Its output is a set of rules
(section 2) with their test records, which is the "if a story of this type appears, watch the next ten
minutes" statement made measurable.

---

## 4. Workflow agents

An agent is no longer only a decision function. Its genome may describe a small **directed graph of
steps** executed deterministically each bar and journaled step by step:

```
sense(sensor set) -> features -> [rules that fire] -> belief (family or policy) -> sizing (kelly, limits) -> actions
                                       |
                                  propose_rule (optional, budgeted)
```

- Steps come from a closed catalogue (sensors, feature transforms, rule application, belief families,
  sizing overlays, the propose step). Structure mutation adds, removes or rewires steps within a depth
  cap; parameter mutation acts inside steps. The v2 composition of families (`kelly(calibrator(
  newsbayes))`) is the degenerate linear case of this graph, so every existing family is a valid
  workflow.
- LLM agents are one step type (`llm_belief`) inside the same graph, with the contamination rule of v2.
- Determinism and replay are unchanged: each step's inputs and outputs are integers, and the journal
  records the executed graph per bar (`WorkflowStepExecuted` events under the size cap).
- The competition is therefore between **workflows**: which information, which rules, which belief,
  which sizing, as one heritable object.

---

## 5. Evaluation additions

- **Knowledge transfer**: a promoted rule is re-tested on the other providers, categories and asset
  classes of its scope; the ledger records where it transfers and where it does not.
- **Rule-adjusted claims**: a claim on the sealed test lists the rules the agent used and their live
  records at claim time, so a reader can tell an agent that learned from an agent that got lucky.
- **Diet ablation**: the amnesic and no-hive ablations of v2 gain a **sensor ablation**: the champion
  re-run with each sensor removed, reporting the skill drop per sensor, which is the measured value of
  each information source.

---

## 6. Acceptance criteria added by v5

- AC-26: the observation builder assembles observations from sensor sets; two agents with different
  sensor sets on the same bar receive different observations, and the poisoned-future test passes for
  every sensor in the catalogue.
- AC-27: on a fixture with a planted conditional effect (for example "category politics, last week,
  price above 7000: outcome rate 12 points below price"), the symbolic miner proposes a rule that
  matches it, the tester promotes it out of time on the replicate fold, and the same miner promotes
  nothing on the shuffled twin.
- AC-28: a minute dataset builds from Binance and Hacker News fixtures, and the minute event study
  reports the planted 10-minute drift as a rule with a positive lower bound.
- AC-29: a workflow genome with a propose step runs, journals its steps, replays to the same hash, and
  a structure mutation changes the hash.
- AC-30: the rule ledger and the sensor ablation appear in the UI for a real run.
- **E2E-5a** (`tests/e2e/test_e2e_5a_discovery.py`): fixture with planted effects, the miner and one
  agent propose rules, promotion on the rolling pair inside the training fold, an agent trades the
  promoted rule out of time on the validation fold and beats the follower there, the shuffled twin
  promotes nothing; replay holds (as corrected by contract ruling R238).

---

## 7. Risks specific to v5

| Risk | Mitigation |
|---|---|
| Rule mining is a multiple-testing machine | Every rule pays a deflation for the candidates tried in its generation; promotion needs validation, not train; live records demote decaying rules; the sealed test is never seen by the tester. |
| Rules encode the outcome through a leaky feature | Rules only use sensor blocks, which are as-of by construction and covered by the poisoned-future test; the tester refuses a predicate on a feature that is not in the sensor catalogue. |
| Sensor budget becomes a way to buy skill | Costs are per bar and per generation; an agent's fitness is net of nothing (money is money), but the allowance shrinks when sensors do not pay, so a rich diet without skill dies. |
| Minute datasets are large | One pair-year is about half a million bars; stored as integer arrays, built per instrument on demand, and the minute grid is used for the event studies and the minute agents, not for evolution of the whole population. |
| Hacker News is a narrow lens | It is one sensor among many; its value is measured by ablation like every other. |
| Workflow graphs explode the search space | Depth cap, closed step catalogue, MAP-Elites over structure descriptors, and the v2 rule that immigrants and elites bound the churn. |

---

## 8. Revision history

- 1.0, 2026-09-08: written after the user's challenge; sources probed the same day (Hacker News Algolia
  and Firebase, Binance 1-minute klines, GDELT recent, Kalshi cutoff).
- 1.1, 2026-09-09: 2.3 steps 2 and 3, AC-27 and E2E-5a corrected in place by amendment C1c (contract
  15.10, ruling R238): pre-registered families, false discovery rate control within a family, out-of-time
  replication as the primary criterion, and an insight visible from `fit_t1_ms + interval_ms`.
