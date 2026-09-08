# pmx v3 : the build plan, part 2

Companion to `docs/PRD_V3_TRADING_OPTIMIZER.md`. Part 1 is `docs/PLAN_V2_WAVES.md` (waves 0 to 6). The
method is unchanged: one contract, exclusive file ownership, dependency layers, an integration gate per
wave, no weakened test. Two additions from v3:

- **A contract amendment package opens every part-2 wave.** It adds the wave's interfaces to
  `docs/CONTRACTS_V2.md` (a new numbered section plus the module map rows) and is adversarially reviewed
  by one critic before the wave's packages start.
- **An end-to-end test closes every rung.** The gate of a rung runs `tests/e2e/` in full; earlier rungs'
  tests must stay green.

Every package keeps the conventions of part 1 (Owns, Needs, Done when, contract issues, own tests only,
ruff and mypy strict on its own files).

---

## Wave 2 amendment (before the engine wave of part 1 starts)

### C1 v3 interfaces that the engine must be built against

- **Owns**: `docs/CONTRACTS_V2.md` (new section 16 "v3 interfaces" and module map rows), `src/pmx/schemas/`
  additions (`cluster.v1.json`, `opportunity.v1.json`, `features.v1.json`, `model_card.v1.json`).
- **Does**: declares the `LiquidityModel` protocol with the envelope rule and the decision-latency rule
  (an action on bar `t` fills at `t+1` open), so E2 implements `historical` behind it; declares
  `EventCluster` and `Constraint` and their manifest fields; declares the `OpportunityEvent` record;
  declares the `features.v1` vector layout and the `torch_policy` genome (weights hash plus card);
  declares the `pmx.learn`, `pmx.analysis`, `pmx.adversary`, `pmx.portfolio` module map with one owner
  per file; extends the architecture rules (no torch outside `learn/` and `adversary/train/`).
- **Review**: one critic (contradictions and leaks), then the amendment author resolves and records
  rulings in section 15.
- **Done when**: the schemas validate their fixtures, `tests/test_contract_schemas.py` is extended and
  green, every new file has one owner.

Part 1's wave 2 (E1..E5) then runs as planned, with E2 building `historical` behind `LiquidityModel`
and the runner applying the latency rule.

---

---

## Amendment C1c : discovery (v5), after gate G2 and before the agents wave

### C1c sensors, rules, minute grids, workflow genomes

- **Owns**: `docs/CONTRACTS_V2.md` (new section 18 "discovery: sensors, rules, workflows"; the rows of
  sections 13 and 14 it touches; rulings in a new section 15.10; in-place amendments of 8.3
  (observation assembled from a sensor set), 8.4 (the `propose_rule` action), 9.2 (`RuleProposed`,
  `RuleTested`, `RulePromoted`, `RuleDemoted`, `WorkflowStepExecuted`), 10.1 (`Genome.sensors`,
  `Genome.workflow`), 10.4 (`Insight` hive entries), 12.5 (diet descriptors), 12.6 (author bonus,
  rule-adjusted claims), 5.2 (the minute grid) and 7.3 (timestamped sources)), new schemas
  `src/pmx/schemas/rule.v1.json`, `sensor.v1.json`, `workflow.v1.json`, `tests/test_contract_schemas.py`
  and `tests/test_architecture.py` (extend), fixtures under `tests/fixtures/contract/`.
- **Does**: declares the sensor catalogue of PRD v5 section 1 with costs, versions and as-of lags, the
  `SensorBlock` integer feature format, the per-agent hook of the observation builder
  (`build_observation(..., sensors=genome.sensors)`), the sensor budget and its penalty rule; the `Rule`
  record and its closed vocabulary of predicates, the rule tester's procedure (train, validation,
  deflation, promotion, live record, demotion), the `Insight` hive entry and its visibility; the minute
  grid and the rule that a dataset never carries a source coarser than its grid; the workflow genome as
  a bounded DAG over a closed step catalogue with `WorkflowStepExecuted` journaling and the size cap; the
  knowledge-transfer re-test and the sensor ablation; module map rows for `src/pmx/sensors/*`,
  `src/pmx/rules/*`, `src/pmx/agents/workflow.py`, `src/pmx/data/importers/binance.py` (minute path),
  `src/pmx/data/news/hn.py`, `src/pmx/data/news/timestamped.py`, `src/pmx/cli_rules.py` with one owner each.
- **Review**: one critic (leaks through sensors and rules, multiple testing, replay of workflows,
  feasibility for A1, A3 and E1's hook), then the author resolves and records rulings.
- **Done when**: the three schemas validate their fixtures, the extended tests are green, every new file
  has one owner, and gate G2 has applied the E1 hook (the observation builder takes a sensor set) so that
  the agents wave starts against a working engine.


---

## Wave 5 (revised by v5) : agents, sensors, rules, finance data, API and market view

Runs after gate G2 and amendment C1c. Fourteen packages in parallel on Opus, two gates on Fable.

### A1 agent protocol, workflow genome, scripted families

- **Owns**: `src/pmx/agents/protocol.py`, `registry.py`, `workflow.py`, `src/pmx/agents/families/*.py`
  except `stacker.py`, `tests/test_agents_families.py`, `tests/test_workflow.py`.
- **Does**: `Agent`, `Genome` with integer genes, `sensors` and `workflow` (a bounded DAG over the closed
  step catalogue of section 18; the linear composition of v2 is its degenerate case), the families
  `follower`, `trend`, `revert`, `timedecay`, `volume`, `breakout`, `newsbayes`, `calibrator`,
  `specialist`, `kelly`, `rule_follower`, and for v4 `carry`, `basis`, `pairs`, `vol_regime`,
  `calendar`, `random_walk`; the `propose_rule` step for scripted families (a family emits a rule from
  its own parameters when its memory shows a stable effect); structure and parameter mutation; genome
  (de)serialisation; the default roster reproducing the eight v1 archetypes.
- **Done when**: every family decides on every demo market, `follower(1000, 0)` ties the market,
  `random_walk` has zero skill on a continuous fixture, a structure mutation changes the journal hash,
  and `WorkflowStepExecuted` events replay.

### A2 per-agent memory

Unchanged from part 1, plus the track record an agent keeps on its own rules.

### A3 the hive with insights

- **Owns**: `src/pmx/agents/hive.py`, `tests/test_hive.py`.
- **Does**: part 1's hive plus `Insight` entries (promoted rules with test and live records), visibility
  one bar after promotion, demotion, the reputation bonus for authors of surviving rules, the poisoning
  test extended to a false rule from a low-reputation author.

### A4 stacker and ensembles

Unchanged.

### A5 gateway and LLM forecaster

Unchanged, plus the `llm_belief` step type and rule proposals written in the rule vocabulary.

### A6 contamination audit

Unchanged.

### S1 sensors

- **Owns**: `src/pmx/sensors/*.py` (one module per sensor of the catalogue plus `catalogue.py`),
  `tests/test_sensors.py`.
- **Does**: every sensor as a pure function from the as-of dataset views to a `SensorBlock`, its cost
  and lag, the catalogue, the poisoned-future test per sensor (AC-26).

### S2 rules: vocabulary, tester, symbolic miner

- **Owns**: `src/pmx/rules/vocabulary.py`, `rule.py`, `tester.py`, `miner.py`, `src/pmx/cli_rules.py`,
  `tests/test_rules.py`, `tests/fixtures/s2/`.
- **Does**: the closed predicate vocabulary over sensor blocks, rule evaluation on any bar, the tester
  (train, validation, deflation, promotion, live record, demotion, knowledge-transfer re-test) built on
  E4's statistics, the beam-search miner with its candidate budget, `pmx rules mine|test|ledger`; the
  planted-effect fixture and its shuffled twin (AC-27).

### F1 crypto importers

Part 2 wave 3b text, plus the Binance 1-minute path and funding and liquidation times.

### F2 Yahoo, Frankfurter and ECB importers

Unchanged.

### F3 finance news and macro as-of

Unchanged.

### F4 sessions, calendars, finance universe

Unchanged, plus the minute grid in the builder hook.

### F5 Hacker News and timestamped sources

- **Owns**: `src/pmx/data/news/hn.py`, `src/pmx/data/news/timestamped.py` (the rule that a dataset never
  carries a source coarser than its grid), `tests/test_hn.py`, `tests/fixtures/f5/`.
- **Does**: Algolia `search_by_date` with `numericFilters=created_at_i` windows and `hitsPerPage`
  pagination, stories and comments, points and comment counts, subject matching through the linker;
  GDELT recent through D5's module for the minute and hourly grids; the coarser-than-grid refusal.

### U1 API v2

Unchanged, plus routes for the rule ledger and the sensor ablation.

### U2 web market and portfolio views

Unchanged, plus rule firings and per-sensor news markers on the chart.

### Gates G3 and G3b

G3 (agents, sensors, rules, API, market view): reconcile, four checks, AC-5 (amnesic and no-hive) plus
the sensor ablation, AC-26, AC-27, AC-29, LLM smoke offline. G3b (finance data): E2E-1b multi-asset, the
first hourly finance dataset (AC-21), and a minute fixture dataset from Binance and Hacker News with the
minute event study (AC-28, the data half of E2E-5a).

---

## Later waves, as revised by v5

- Wave 6 (optimizer O1..O4, live L1, gate G4): O2 adds the diet descriptors to the MAP-Elites archive,
  the author bonus and the sensor allowance to selection; O4's claims list the rules used and their live
  records; L1 runs the miner and the tester daily on open markets and publishes promoted rules with
  their hashes.
- Wave 7 (surfaces U3, U4, gate G5): U3 adds the rule ledger view, the sensor ablation view and the
  "where it fires" overlay; U4's README documents sensors, rules and grids.
  **U5 guided tour and contextual help** joins wave 7 (PRD v2 section 7.1b): owns `web/src/tour/*`
  (engine, overlay, popover, Help menu, chapter registry, en and fr copy loader), `tests/test_tour.py`
  (chapter per tab, anchor per step, copy in both languages) and the headless-Chrome tour walk of gate
  G5 with one screenshot per step into `docs/tour/`. Every view package (U2, U3 and, later, the
  opportunities, clusters, rule ledger and live views) owns its own `data-tour` anchors and its chapter
  file next to the component; a tab without a chapter fails `tests/test_tour.py`. Gate G5 verifies
  AC-31. No external service, no CDN: the engine is hand-rolled or an MIT library from npm.
- Wave 8 (realism at scale): unchanged, plus the minute datasets for the liquid crypto pairs and the
  Kalshi series with 1-minute candlesticks.
- Wave 9 (detectors): every detector emits rules into the ledger; the minute event study at 1, 5, 10,
  30 and 60 minutes per source and story feature (AC-28 on real data); the cross-domain detectors of v4.
- Wave 10 (learning): promoted rules and sensor blocks are the feature vector; the supervised floor is
  trained per sensor set; policies inherit the sensor gene.
- Wave 11 (adversary): the adversarial market maker may not read rules or sensors (it sees flow only);
  stress scenarios add sensor dropout.
- Wave 12 (portfolio, live extension): the allocator weights sub-strategies by their rules' live
  records; E2E-5a closes the discovery rung.

## Wave 7 : market realism at scale (rung 1), after gate G4 of part 1

### R1a universe and statistics

- **Owns**: `src/pmx/data/universe.py`, `src/pmx/cli_data.py` (the `stats` subcommand only, by
  agreement with D6 recorded in the contract), `tests/test_universe.py`.
- **Does**: the expanded Kalshi series allow-list by category, the Manifold quality bar, universe
  statistics by provider, category, life, liquidity decile, hardness tag, YES rate, market own Brier by
  category; the statistics enter the manifest.
- **Done when**: statistics on the fixture dataset match hand-computed values; `pmx data stats` prints
  the table.

### R1b clusters and constraints

- **Owns**: `src/pmx/data/clusters.py`, `tests/test_clusters.py`, `tests/fixtures/r1b/`.
- **Does**: the conservative cross-venue matcher with stored reasons and scores; `sum_to_one`,
  `implies`, `monotone_ladder`, `complement` constraints from Kalshi event tickers and Manifold
  duplicates; a manual override file sealed with the dataset; never visible to agents as labels.
- **Done when**: the fixture's one true cluster and one decoy pair are classified correctly and the
  reasons are stored.

### R1c calibrated impact and queue-position limits

- **Owns**: `src/pmx/engine/liquidity.py` (the `calibrated_impact` implementation; `historical` was E2's),
  `src/pmx/data/impact.py` (the calibration projection), `tests/test_liquidity.py`.
- **Does**: impact coefficients per liquidity decile from the tape, stored in the manifest; queue
  position for resting orders; the envelope enforced in one place for every implementation.
- **Done when**: two builds of the same raw data give identical coefficients; a property test shows no
  fill ever leaves the envelope.

### R1d hourly dataset and UI cluster view

- **Owns**: `web/src/components/clusters/*`, hourly build option in `src/pmx/data/builder.py` (by
  agreement with D6 recorded in the contract), `tests/test_hourly.py`.
- **Done when**: an hourly fixture dataset builds and the cluster view renders a cluster with its
  members and reasons.

### Gate G7 and E2E-1

Resolves issues, drives the four checks green, writes `tests/e2e/test_e2e_1_realism.py` if R1a to R1d
did not (the gate owns `tests/e2e/`), runs it, then attempts the real 1 000 plus 1 000 build (AC-11)
and records the numbers.

---

## Wave 8 : opportunity detection (rung 2)

### C2 amendment: detector interfaces and the analysis CLI (small)

### R2a news lead event study

- **Owns**: `src/pmx/analysis/news_lead.py`, `tests/test_news_lead.py`, `tests/fixtures/r2a/`.
- **Done when**: on a fixture with a planted post-news drift the study reports it with a positive lower
  bound and reports nothing on the shuffled twin.

### R2b cross-venue divergence

- **Owns**: `src/pmx/analysis/divergence.py`, `tests/test_divergence.py`.
- **Done when**: the planted gap is found once with size, duration and net-of-fees payoff; the
  currency label is present.

### R2c logical inconsistency

- **Owns**: `src/pmx/analysis/logic.py`, `tests/test_logic.py`.
- **Done when**: the planted ladder violation and a `sum_to_one` violation are found and the risk-free
  combination payoff is computed.

### R2d comparative analysis

- **Owns**: `src/pmx/analysis/comparative.py`, `tests/test_comparative.py`.
- **Done when**: favorite-longshot, autocorrelation by horizon, calendar effects and relative value are
  computed on fixtures with known planted values.

### R2e report, CLI and UI

- **Owns**: `src/pmx/analysis/report.py`, `src/pmx/cli_analyze.py`, `web/src/components/opportunities/*`,
  API routes for analysis in a new `src/pmx/api/routes_analysis.py`, `tests/test_analyze_cli.py`.
- **Done when**: `pmx analyze all` writes the opportunity map and the UI renders one card per detector
  with interval and null.

### Gate G8 and E2E-2

Writes or completes `tests/e2e/test_e2e_2_detectors.py`, runs `tests/e2e/` in full, runs `pmx analyze
all` on the real dataset (AC-14) and records the opportunity map numbers.

---

## Wave 9 : learned agents (rung 3)

### C3 amendment: features, learn, model cards, the torch rule

### R3a features

- **Owns**: `src/pmx/features/*.py`, `tests/test_features.py`.
- **Done when**: the vector is as-of (poisoned-future test extended), versioned, hashed, and its float
  view round-trips.

### R3b as-of embeddings at build time

- **Owns**: `src/pmx/data/embeddings.py`, `tests/test_embeddings.py`.
- **Done when**: embeddings are computed only from as-of texts, stored per item, and a stub encoder
  makes the test offline and deterministic.

### R3c supervised floor

- **Owns**: `src/pmx/learn/supervised.py`, `tests/test_supervised.py`.
- **Done when**: logistic and gradient boosting models train on the fixture fold, score on validation
  with intervals, and export as agents.

### R3d environment, PPO, evolution strategies, policies, export

- **Owns**: `src/pmx/learn/env.py`, `ppo.py`, `es.py`, `policies.py`, `export.py`, `cards.py`,
  `src/pmx/cli_learn.py`, `tests/test_learn.py`.
- **Done when**: a tiny policy trains on CPU in the test within a bounded step count, exports a weights
  file and a card, and the card's hash is stable.

### R3e the `torch_policy` family

- **Owns**: `src/pmx/agents/families/torch_policy.py`, `tests/test_torch_policy.py`.
- **Done when**: an exported policy runs as an agent through the ordinary engine, outputs are quantised
  before the journal, and the run replays without torch installed (the family loads a CPU-only
  inference path or a cached action table, as the contract decides).

### Gate G9 and E2E-3

`tests/e2e/test_e2e_3_learn.py` with the planted-signal fixture and its shuffled control; then the real
training fold on the GPU (AC-15) with numbers recorded.

---

## Wave 10 : the adversarial market maker (rung 4)

### C4 amendment: adversary interfaces, co-evolution events, stress scenarios

### R4a parametric adversarial market maker

- **Owns**: `src/pmx/adversary/mm.py`, `tests/test_adversary_mm.py`.
- **Done when**: the envelope holds under a property test and the maker reduces a fixture population's
  PnL relative to `historical`.

### R4b co-evolution loop

- **Owns**: `src/pmx/adversary/coevolution.py`, `src/pmx/cli_adversary.py`, `tests/test_coevolution.py`.
- **Done when**: three alternating generations run on fixtures, journal `AdversaryGenerationClosed`
  events, resume identically, and report the robustness gap.

### R4c stress scenarios

- **Owns**: `src/pmx/adversary/stress.py`, `tests/test_stress.py`.
- **Done when**: market bootstrap, news dropout, lag jitter and fee shocks each produce a journaled
  scenario id and change the hash; no synthetic price exists in any scenario.

### R4d learned market maker

- **Owns**: `src/pmx/adversary/train/*.py`, `tests/test_adversary_train.py`.
- **Done when**: a small policy market maker trains on CPU in the test and stays inside the envelope.

### Gate G10 and E2E-4

---

## Wave 11 : portfolio, meta-strategies, small LLM fine-tune, live extension (rungs 5 and 6)

### C5 amendment

### R5a allocator and drawdown governor: `src/pmx/portfolio/allocator.py`, `governor.py`, tests.
### R5b meta bandit and regimes: `src/pmx/portfolio/meta.py`, tests.
### R5c small LLM fine-tune family (optional, GPU): `src/pmx/learn/llm_finetune.py`, tests offline with a stub.
### R6a live detectors and learned agents: `src/pmx/live/opportunities.py`, extensions to the daily job, tests.
### R6b UI: portfolio and live opportunities views.

### Gate G11, E2E-5 and E2E-6

---

---

## Wave 2 amendment, part two : the instrument generalisation (v4), before the engine wave

### C1b every market is an instrument

- **Owns**: `docs/CONTRACTS_V2.md` (new section 17 "instruments across kinds", the rows of section 13
  and 14 it touches, rulings in a new section 15.9; amendments to sections 1, 5, 7.2, 8.5 to 8.9, 9.2 and
  12.1 to 12.3 where the binary-only wording is generalised), `src/pmx/schemas/instrument.v1.json`,
  `src/pmx/schemas/cash_event.v1.json`, `src/pmx/schemas/session_calendar.v1.json`,
  `tests/test_contract_schemas.py` and `tests/test_architecture.py` (extend), fixtures under
  `tests/fixtures/contract/`.
- **Does**: declares the six instrument kinds of `docs/PRD_V4_MULTI_ASSET.md` section 1 with
  `tick_size_micro`, `point_value_micro`, the integer conversion formulas and overflow bounds, so that a
  binary contract is exactly the v2 bp price and nothing already written changes value; the session
  calendar and the rule that a bar outside it does not exist; `CorporateAction`, `Roll` and funding as
  dated `CashEvent`s applied by execution; the per-kind fee, borrow and carry schedules as data; the
  forecast record generalised to `(horizon, up_probability_ppm, quantiles_ticks)` with the random-walk
  baseline and the directional Brier and pinball loss of PRD v4 section 3; horizon resolution events
  in the journal catalogue and the hive visibility rule one bar after the horizon; the forced flat at
  the window end; the `kinds` field of `BuildConfig` and the per-kind and per-provider claim rule.
  `Market` stays the name of the binary instrument in code, `Instrument` is the common base, and the
  contract says which fields move where.
- **Review**: one critic (contradictions with sections 8, 9, 12 and the v3 section 16; leaks through
  cash events or calendars; feasibility for E2, E3 and E5), then the author resolves and records rulings.
- **Done when**: the schemas validate their fixtures, the extended tests are green, and section 13 has
  one owner per new file.

The engine wave (E1..E5) is then built against sections 16 and 17 together: E2 owns cash events,
funding, borrow and rolls behind the same execution path; E3 owns the per-kind forecast scores and the
random-walk baseline; E5 emits the horizon resolution events.

---

## Wave 3b : finance data (superseded: folded into the revised wave 5 above; kept for the package texts F1..F4)

### F1 crypto importers

- **Owns**: `src/pmx/data/importers/binance.py`, `kraken.py`, `coinbase.py`, `bybit.py`, `tests/test_import_crypto.py`,
  `tests/fixtures/f1/`.
- **Does**: klines and trades on Binance (1 000 per call, paginate by `startTime`), Kraken OHLC (720 per
  call, `since`) and Trades, Coinbase candles (300 per call), Bybit linear klines and Binance funding
  history; mapping to `Instrument`s of kind `spot_crypto` and `perp` with the venue's tick and point
  scales; cross-venue twins declared by symbol mapping. Offline fixtures recorded from the documented
  shapes; live tests behind `PMX_LIVE`.
- **Done when**: fixture imports produce hourly bars whose closes match the fixtures, funding events land
  on their funding times, and the twins of one coin share a cluster id.

### F2 Yahoo, Frankfurter and ECB importers

- **Owns**: `src/pmx/data/importers/yahoo.py`, `frankfurter.py`, `ecb.py`, `tests/test_import_yahoo_fx.py`,
  `tests/fixtures/f2/`.
- **Does**: Yahoo chart v8 for equities, ETFs, continuous futures and FX pairs (hourly for the window,
  daily for history), with the vendor label, throttle and cache, splits and dividends from the chart
  `events` into `CorporateAction`s, the roll detection for continuous futures; Frankfurter and ECB daily
  reference rates as the official FX anchor.
- **Done when**: fixture imports produce raw series plus dated corporate actions and rolls, and the
  adjusted view of the loader matches the vendor's adjusted close on the fixture.

### F3 finance news and macro as-of

- **Owns**: `src/pmx/data/news/edgar.py`, `fred.py` (with ALFRED vintages), `release_calendar.py`,
  `cboe.py`, finance lexicons under `src/pmx/lexicons/`, `tests/test_finance_news.py`, `tests/fixtures/f3/`.
- **Does**: SEC submissions per CIK into `NewsItem(kind="filing")` with the acceptance time as
  `published_at`; ALFRED vintages so a macro observation is visible from its release, never from its
  observation date; a static FOMC, CPI and payrolls release calendar file; VIX history; the finance
  lexicons for `newsbayes`.
- **Done when**: a filing is invisible before its acceptance time in the as-of view, a macro number is
  invisible before its vintage, and the calendar validates.

### F4 sessions, calendars and the finance universe

- **Owns**: `src/pmx/data/sessions.py`, `src/pmx/data/calendars/*.json`, `src/pmx/data/universe_finance.py`,
  `tests/test_sessions_universe.py`.
- **Does**: static session calendars for crypto, FX and the US exchanges with holidays for the window;
  the universe of PRD v4 section 2.2 chosen at the window start from a dated list; the `--kinds` option
  of the builder wired through a hook D6 exposes (a contract issue if it does not).
- **Done when**: a bar outside its calendar is refused by the loader, and the universe list is
  reproducible from the dated input.

### Gate G3b and E2E-1b

Reconciles F1..F4 with the engine and the loader, drives the four checks green, writes
`tests/e2e/test_e2e_1b_multi_asset.py` (PRD v4 section 7) and runs it, then builds the first
multi-asset dataset from the network at an hourly grid (AC-21) and records the numbers.

---

## Additions to later waves for v4

- Wave 3 (agents): A1 adds the `carry`, `basis`, `pairs`, `vol_regime` and `calendar` families, and the
  random-walk baseline agent (`random_walk`, zero skill by construction on continuous kinds).
- Wave 8 (detectors): R2f cross-domain consistency (binary versus underlying, funding and basis,
  cross-venue crypto, macro releases with ALFRED clocks, post-filing drift) and E2E-2b.
- Wave 9 (learning): R3a adds the finance feature fields; crypto's hourly universe is the first GPU
  training set.
- Wave 11 (portfolio): allocation across asset classes, exposure limits per kind.
- Every leaderboard, claim and opportunity card carries the asset class and the provider.

## Summary of part 2

| Wave | Packages | Parallel | Closes |
|---|---|---|---|
| 2 amendment | C1 (+1 critic) | no | part 1 wave 2 may start |
| 7 realism | R1a R1b R1c R1d | 4 | AC-11..13, E2E-1 |
| 8 detection | C2, R2a R2b R2c R2d R2e | 5 | AC-14, E2E-2 |
| 9 learning | C3, R3a R3b R3c R3d R3e | 5 | AC-15..16, E2E-3 |
| 10 adversary | C4, R4a R4b R4c R4d | 4 | AC-17, E2E-4 |
| 11 portfolio and live | C5, R5a R5b R5c R6a R6b | 5 | E2E-5, E2E-6 |

Twenty-eight packages and five amendments on top of part 1's twenty-seven, plus amendments C1b (v4) and C1c (v5), the finance data packages F1..F5 and the discovery packages S1 and S2 of the revised wave 5. The order of waves 7 to 11
is fixed by the ladder; inside a wave everything is parallel. Wave 7 needs part 1's optimizer (gate
G4) because the robustness gap and the claims are defined on its objects; waves 8 and 9 need only wave
7; wave 10 needs 9 (the learned maker) and wave 11 needs 10.

## Architecture rules added

- Nothing outside `src/pmx/learn/` and `src/pmx/adversary/train/` imports torch, sklearn or
  sentence_transformers.
- Nothing in `src/pmx/analysis/` writes to a journal or reads a sealed test fold.
- `src/pmx/engine/liquidity.py` is the only place a fill price is computed, and every implementation
  passes the envelope check function it exports.
