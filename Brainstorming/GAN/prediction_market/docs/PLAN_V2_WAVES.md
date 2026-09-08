# pmx v2 : the build plan in waves and parallel work packages

Companion to `docs/PRD_V2_HARD_OPTIMIZER.md`. The PRD says what; this file says in which order, by
whom (one agent per package), against which files, and what must be true before the next wave starts.

The method is the one that worked on Exchange (`GAN/Exchange/docs/ROADMAP.md`, section 1) and it is
kept as written there:

1. **One contract, written and adversarially reviewed before any implementation** (wave 0).
2. **Exclusive file ownership.** Every file has exactly one owning package. Nothing is merged by hand.
3. **Dependency layers.** A package starts only when the packages it imports are real code, or it codes
   blind against the contracted signature and an integration agent reconciles.
4. **An integration gate closes every wave.** The gate may edit any file, resolves every "contract
   issue" the packages reported, and drives the checks green: `ruff`, `mypy --strict`, `pytest`, the
   em-dash sweep, and the wave's acceptance criteria.
5. **No test passes by being weakened.** No relaxed assertion, no skip, no loosened tolerance. The gate
   audits for tests that hold against an empty journal.

Conventions for every package below:

- **Owns** lists the only files the package may create or edit. Tests for a package live in its own
  `tests/test_<package>.py` and belong to it.
- **Needs** lists the packages whose code must exist first. Packages with the same "needs" run in
  parallel.
- **Done when** is checkable by the gate without reading the code.
- Every package reports a `CONTRACT ISSUES` list at the end (empty is a valid answer).
- Every package runs `.venv/Scripts/python.exe -m pytest tests/test_<package>.py` green, `ruff check`
  and `mypy --strict` clean on its own files before reporting.

---

## Wave 0 : the contract (sequential, 1 author + 3 critics + 1 arbiter)

### C0 `docs/CONTRACTS_V2.md`

- **Owns**: `docs/CONTRACTS_V2.md`, `src/pmx/schemas/market.v2.json`, `src/pmx/schemas/news.v1.json`,
  `src/pmx/schemas/dataset.v1.json`, `src/pmx/schemas/actions.v2.json`,
  `src/pmx/schemas/journal.v2.json`. The schemas moved inside the package in wave 0 (contract 7.13 and
  ruling R29): A5 hands `actions.v2.json` to the CLI at run time and D1 validates every dataset file
  against them, and a repository-relative path does not exist in an installed `pmx`.
- **Content**: units (bp, ppm, cents, micro-Brier, milli-units) with every conversion formula; identifier
  formats; canonical ordering (markets by `resolved_at, id`; agents by `agent_id`; events by
  `(bar_ms, seq)`); canonical JSON serialisation for hashing; the RNG tree and registered substreams;
  the event catalogue with every field typed; the bar phase order (open, observe, decide, execute,
  settle, learn, hive, close); `Observation` and `Actions` field by field; the `Agent`, `Memory`,
  `Hive`, `Gateway` protocols; the fee schedules as data; the fold and claim rules; the leak rules
  (what may never appear in an observation); the module map with the owner of every file (section 13
  of the contract); the wave plan cross-reference.
- **Review**: three independent critics attack the contract for contradictions, leaks, float paths,
  ambiguous orderings and untestable statements. The arbiter resolves every finding in the text. Nothing
  else starts before this is closed.
- **Done when**: the arbiter's findings list is empty, every schema validates the demo pack fixtures,
  and every file in the module map has exactly one owner.

---

## Wave 1 : data (7 packages in parallel after C0)

All of wave 1 codes against the schemas of C0 and needs nothing else. D1 is the one package the others
import a type from; they start at the same time and code against the contracted `pmx.types` names, and
the gate reconciles.

### D1 types, schema, loader, migration

- **Owns**: `src/pmx/types.py`, `src/pmx/data/schema.py`, `src/pmx/data/loader.py`,
  `src/pmx/data/migrate_v1.py`, `data/demo_v1/` (generated), `tests/test_types_loader.py`.
- **Does**: bp/ppm/cents types and conversions; `Market`, `Bar`, `Trade`, `NewsItem`, `DatasetManifest`
  with pydantic validation against the JSON schemas; loading a dataset directory; seal (SHA-256 over
  canonical bytes) and verify; `migrate-v1` turning the twelve v1 files into v2 daily bars with
  `source: "reconstructed"`.
- **Done when**: the 12 demo markets load, migrated prices equal v1 cents times 100, `verify` fails on a
  one-byte change, a `reconstructed` market is refused by `seal`.

### D2 Kalshi importer

- **Owns**: `src/pmx/data/importers/kalshi.py`, `src/pmx/data/importers/_http.py` (shared throttled
  client with on-disk cache, User-Agent, backoff), `tests/test_import_kalshi.py`, `tests/fixtures/d2/`.
- **Does**: list settled markets in a window from `/markets?status=settled` and `/historical/markets`
  (respecting `/historical/cutoff`); series allow-list and the `KXMVE...` shard exclusion; fetch
  `/markets/trades` and candlesticks (`start_ts`, `end_ts`, `period_interval` in 60 or 1440) from the
  live or historical path; map to `Trade` and `Bar`, prices in bp, `currency: "usd"`; optional API key.
  All tests offline against recorded fixtures; one opt-in live smoke test behind `PMX_LIVE=1`.
- **Done when**: a fixture-backed import writes a valid v2 market with bars and trades, and the
  cutoff logic picks the historical path for a pre-cutoff market.

### D3 Manifold importer

- **Owns**: `src/pmx/data/importers/manifold.py`, `src/pmx/data/news/manifold_comments.py`,
  `tests/test_import_manifold.py`, `tests/fixtures/d3/`.
- **Does**: resolved binary markets by `resolutionTime` window from `/search-markets` (paginate);
  full bet tape from `/bets?contractId=` (paginate with `before`), `probAfter` as the trade price,
  `amount` as size, `createdTime` as `t_ms`; comments to `NewsItem(kind="comment")`; `currency:
  "mana"`; exclusion of self-resolved creator markets and of `resolution` not in `{YES, NO}`.
- **Done when**: fixture import produces bars whose closes match the bets' `probAfter` at each bar
  boundary and every comment carries a `published_at` at most the market's `resolved_at`.

### D4 Polymarket importer v2 (optional path)

- **Owns**: `src/pmx/data/importers/polymarket.py`, `tests/test_import_polymarket.py`,
  `tests/fixtures/d4/`.
- **Does**: v1 importer moved to the v2 schema, `prices-history` with `interval`, `fidelity`,
  `startTs`, `endTs`; an explicit `PMX_HTTP_PROXY` setting; the **ANJ block detector**: if the served
  certificate or the response body identifies `anj.fr`, raise `ProviderBlockedError("Polymarket is
  blocked in this jurisdiction (ANJ)")` with no retry.
- **Done when**: the block detector fires on a recorded ANJ response and the fixture import writes a
  valid market when not blocked.

### D5 Dated news archive

- **Owns**: `src/pmx/data/news/wikipedia_current_events.py`, `src/pmx/data/news/wikipedia_asof.py`,
  `src/pmx/data/news/wayback.py`, `src/pmx/data/news/gdelt.py`, `src/pmx/data/news/linker.py`,
  `data/lexicons/` (per-category for/against word lists used by `newsbayes`), `tests/test_news.py`,
  `tests/fixtures/d5/`.
- **Does**: one Wikipedia Current events page per day in the window through the MediaWiki API with a
  descriptive User-Agent (`pmx-research/<version> (contact: <email from config>)`), parsed into one
  `NewsItem` per bullet with section, wiki links and source URLs; point-in-time article fetch
  (`rvstart`, `rvdir=older`) for a subject page; Wayback CDX front-page snapshots (optional, throttled);
  GDELT DOC (optional, one request per 5 s, recent 3 months only); the deterministic **linker**
  (shared wiki links, then keyword overlap, scored, thresholded, score stored); as-of safety lag
  applied at build time as `visible_from`.
- **Done when**: a fixture day parses into items with correct sections and links, the linker's scores
  are reproducible, and a poisoned item dated after the freeze is refused by the builder's validation.

### D6 Dataset builder and CLI data commands

- **Owns**: `src/pmx/data/builder.py`, `src/pmx/data/resample.py`, `src/pmx/cli_data.py`,
  `tests/test_builder.py`.
- **Does**: `trades -> bars` on a fixed grid (60 or 1440 minutes) with vwap, zero-volume bar
  carry-forward; the window filter (`resolved_at` in `[T-365d, T-1d]`, opened at most 90 days before
  the window); the quality filters with counts; the hardness tags; the split into train, validation
  and sealed test by `resolved_at`; the manifest; `pmx data import|news fetch|build|refresh|seal|
  verify|status|migrate-v1`.
- **Done when**: from the fixtures of D2, D3 and D5 a dataset builds, seals, verifies, reports filter
  counts, and the split is chronological with no market in two folds.

### D7 Exchange ports: RNG and journal

- **Owns**: `src/pmx/rng.py`, `src/pmx/journal.py`, `tests/test_rng_journal.py`.
- **Does**: port `pxe.rng` (seed tree, named substreams) and the journal conventions (canonical
  serialisation, append, hash, replay iterator) to `pmx`, with the v2 event catalogue from C0.
- **Done when**: two runs with the same seed produce identical substream draws; a journal round-trips
  and its hash is stable across platforms (newline and encoding fixed).

### Gate G1

Runs D1 to D7 together: `pmx data build` on fixtures; then, with network, `pmx data build --provider
kalshi,manifold --freeze 2026-09-07 --out data/datasets/y2026` and reports the real counts against the
300-per-provider target (AC-1). Documents any shortfall in the manifest and in `docs/BUILD_STATE.md`.

---

## Wave 2 : engine and metrics (5 packages in parallel after G1)

### E1 calendar and observation builder (the leak boundary)

- **Owns**: `src/pmx/engine/calendar.py`, `src/pmx/engine/observation.py`, `tests/test_observation.py`.
- **Does**: the bar timeline over a dataset, open markets per bar, the `Observation` per agent per bar
  with the as-of filter on bars, trades, news and hive; the research budget accounting; the leak
  tests of PRD 6.3 (poisoned future, clock).
- **Done when**: the poisoned-future and clock tests pass and an observation serialises under the
  contract's size cap.

### E2 execution, fees, accounting

- **Owns**: `src/pmx/engine/execution.py`, `src/pmx/engine/fees.py`, `src/pmx/engine/liquidity.py`,
  `tests/test_execution.py`.
- **Does**: bankroll, cash-limited longs and shorts, market orders at the execution bar's open or quote
  with volume cap and slippage, limit orders with range crossing, per-provider fees as data with source
  and date, settlement, ruin, mark-to-market. Property tests (hypothesis) on the accounting invariant.
- **Amendment C1 (CONTRACTS_V2 section 16) changes two things before E2 starts, and both are contract,
  not preference.** First, the pricing goes behind the **`LiquidityModel` protocol** of 16.1: E2 writes
  `src/pmx/engine/liquidity.py` (the protocol, the `Fill`, `LiquidityMarketView` and `ObservedFlow`
  records, the envelope rule, the `check_envelope` function every implementation must pass, and the
  `historical` implementation, which is section 8.6 steps 1 to 4), and `Execution` computes no price of
  its own, so wave 7's `calibrated_impact` and wave 10's `adversarial_mm` plug in without touching the
  engine. Second, the **decision latency rule** of 16.2: an action decided on bar `t` executes at the
  open of bar `t + interval_ms`, so `Execution.place` queues in the decide phase and reserves nothing
  while `execute_bar` drains the previous bar's queue, prices it against the execution bar's open and
  emits every execute-phase event with `decided_at_ms`.
- **Done when**: the invariant holds on 1 000 generated fill sequences, a zero-volume bar fills nothing,
  `check_envelope(historical, ...)` reports no breach on a hypothesis-generated bar and order set, and no
  fill exists on the bar its action was decided on.

### E3 scoring

- **Owns**: `src/pmx/scoring.py`, `src/pmx/metrics/calibration.py`, `tests/test_scoring.py`.
- **Does**: time-weighted Brier, horizon-bucketed Brier, Brier skill, log score in micro-nats, PMV,
  reliability curve, ECE, sharpness. Integers only. Proof that on a regular grid the time-weighted
  Brier equals the mean, and that on the migrated v1 paths it differs.
- **Done when**: the identities hold in tests and the calibration module imports nothing from
  execution.

### E4 statistics

- **Owns**: `src/pmx/metrics/stats.py`, `tests/test_stats.py`.
- **Does**: block bootstrap by ISO week and by event cluster, paired difference against the baseline,
  lower bounds, permutation null on shuffled outcomes, Bonferroni-style deflation for the candidate
  count. numpy allowed here only; every reported number rounded to an integer unit.
- **Done when**: a synthetic agent with known skill gets an interval containing it, the shuffled null
  centres on zero, and deflation widens with the candidate count.

### E5 runner, projection, run store

- **Owns**: `src/pmx/engine/runner.py`, `src/pmx/metrics/projection.py`,
  `src/pmx/metrics/performance.py`, `src/pmx/metrics/behavioral.py`, `src/pmx/metrics/leaderboard.py`,
  `src/pmx/store.py` (sqlite run index), `src/pmx/cli_run.py`, `tests/test_runner.py`.
- **Does**: `run_backtest(dataset, roster, config, *, tree, journal_dir, liquidity=None, ...) ->
  RunHandle` (the literal signature is CONTRACTS_V2 12.11; the `seed` positional of this plan is
  superseded by ruling R14, because contract 6.2 forbids the runner from building its own `RngTree`, and
  the keyword-only `liquidity` is amendment C1's, because 16.1 forbids it from building its own
  `LiquidityModel` for the same reason) over the calendar, journaling
  every event of the catalogue, settlement and `learn` calls at `resolved_at`, projection of the
  journal into results, PnL and drawdown metrics, behavioural descriptors for MAP-Elites, the
  leaderboard with per-provider, per-category, per-tag, per-fold breakdowns, `pmx replay`. Codes
  against the `Agent` protocol of C0 with a scripted stub until wave 3 lands.
- **Amendment C1 (CONTRACTS_V2 16.2) puts the decision latency rule in the runner's hands**: the phase
  order and `PHASE_ORDER` are unchanged and `execute` stays after `observe`, but the decide phase now
  hands its order-producing actions to `Execution.place`, which queues them, and the execute phase drains
  the queue of `t - interval_ms`. The runner also reads `config.liquidity` and `config.liquidity_params_hash`
  into the projection, and raises `InvalidConfigError` when the model it was handed disagrees with them.
- **Done when**: a run on the demo pack journals, replays to an identical hash, the `market_follower`
  genome reproduces the market's Brier exactly (v1's identity, preserved), and no `order_placed` carries
  `decided_at_ms == t1_ms - interval_ms` (16.2: an action decided on the run's last bar has no bar to
  fill in).

### Gate G2

Full scripted-stub run on the real dataset from G1; AC-3 and AC-4 checked; determinism over 50 seeds;
`docs/BUILD_STATE.md` updated.

---

## Wave 3 : agents, memory, hive, LLM (6 packages in parallel after G2)

### A1 agent protocol, registry, the eleven scripted families

- **Owns**: `src/pmx/agents/protocol.py`, `src/pmx/agents/registry.py`,
  `src/pmx/agents/families/*.py` except `stacker.py`, `tests/test_agents_families.py`.
- **Does**: `Agent`, `Genome` (integer genes with ranges and steps), composition up to depth 3, the
  families `follower`, `trend`, `revert`, `timedecay`, `volume`, `breakout`, `newsbayes`,
  `calibrator`, `specialist`, `kelly`; genome (de)serialisation; the default roster reproducing the
  eight v1 archetypes as named genomes.
- **Done when**: every family decides on every demo market without error, `follower(1000, 0)` ties the
  market, and a mutated genome stays inside its ranges.

### A2 per-agent memory

- **Owns**: `src/pmx/agents/memory.py`, `tests/test_memory.py`.
- **Does**: the calibration ledger per category and horizon, category priors, feature statistics,
  bounded lessons; `MemoryWritten` events; `--amnesic`; freeze before the sealed test.
- **Done when**: memory replays from the journal, respects its size bound, and a frozen memory refuses
  writes.

### A3 the hive

- **Owns**: `src/pmx/agents/hive.py`, `tests/test_hive.py`.
- **Does**: append-only entries with `visible_from`; forecasts visible at `resolved_at`; reputation
  computed by the engine; lesson ranking by reputation; the poisoning test; `--no-hive`;
  `HiveWritten` events; sqlite index for reads by `(now, market)`.
- **Done when**: a forecast written before resolution is invisible until `resolved_at`, and the false
  lesson from a low-reputation author ranks last.

### A4 stacker and ensembles

- **Owns**: `src/pmx/agents/families/stacker.py`, `src/pmx/agents/ensembles.py`,
  `tests/test_stacker.py`.
- **Does**: reputation-weighted extremized mean over composed members; `top_k_extremized_mean`; the
  flagged live-coop mode (off by default).
- **Done when**: on a synthetic population with one known-good member the stacker's weight on it
  converges, and the live-coop flag is off by default and changes the journal hash when on.

### A5 gateway and LLM forecaster

- **Owns**: `src/pmx/gateway/*.py`, `src/pmx/llm/forecaster.py`, `src/pmx/llm/prompts/*.md` (frame
  and dial blocks), `tests/test_gateway.py`, `tests/test_llm_forecaster.py`.
- **Does**: port Exchange's `protocol`, `claude_cli`, `budget`, `scripted` gateways; one call per
  agent per bar over all open markets; caps before the call; retries inside the bar timeout; fallback
  carries previous forecasts; `llm_trace.jsonl`; the prompt genome with seven dials; strict JSON
  output validated against `schemas/actions.v2.json`; `knowledge_cutoff` per model in config. All
  tests offline through the scripted gateway; one opt-in live smoke test.
- **Done when**: a scripted-gateway LLM agent runs a demo bar, an invalid JSON reply becomes a
  fallback with the previous forecasts, and a budget breach costs nothing.

### A6 contamination audit

- **Owns**: `src/pmx/llm/contamination.py`, `src/pmx/cli_audit.py`, `tests/test_contamination.py`.
- **Does**: `pmx audit contamination --model X`: no-context outcome queries with three paraphrases at
  temperature zero, tagging `contaminated:<model>`, the `clean` rule from `created_at` against
  `knowledge_cutoff`, and the leaderboard filter hook that A5 and E5 call; `pmx audit leaks` wrapping
  the E1 tests; `pmx audit tests` (the empty-journal audit of the gate).
- **Done when**: with a scripted gateway that "knows" a subset of outcomes, exactly that subset is
  tagged, and an LLM leaderboard row reports `n_clean`.

### Gate G3

Full population run (all families, memory on, hive on) on the real dataset; `--amnesic` and `--no-hive`
comparison runs produced (AC-5); LLM smoke on the clean subset within a 2 USD cap (AC-8 partial).

---

## Wave 4 : the optimizer (4 packages in parallel after G3)

### O1 folds and tournament

- **Owns**: `src/pmx/optimizer/folds.py`, `src/pmx/optimizer/tournament.py`, `tests/test_folds.py`.
- **Does**: rolling-origin splits by `resolved_at` (8/2/2 months default), memory and hive carried
  forward in time only, one generation as a tournament on train with validation scoring, the
  selection objective as bootstrap lower bounds (E4).
- **Done when**: no market appears in two folds, the sealed test is never read by a tournament (a
  spy dataset asserts zero reads), and the objective is the lower bound, not the point estimate.

### O2 evolution and the MAP-Elites archive

- **Owns**: `src/pmx/optimizer/evolution.py`, `src/pmx/optimizer/archive.py`, `src/pmx/cli_evolve.py`,
  `tests/test_evolution.py`.
- **Does**: cull, rank-proportional parent draw, gaussian and structural mutation, crossover,
  immigrants, elitism, hall of fame, the MAP-Elites grid over E5's descriptors, novelty bonus,
  research-budget adjustment, `GenerationClosed`, `pmx evolve` and `pmx resume`, patience stop.
- **Done when**: a 5-generation run on the demo pack resumes from generation 3 to an identical final
  hash, and at least one cell of the archive changes occupant across generations.

### O3 prompt mutation pipeline

- **Owns**: `src/pmx/llm/mutate.py`, `tests/test_mutate.py`.
- **Does**: worst-market extraction, patch proposal through the gateway, child creation, parent versus
  child on the validation fold, promotion only on a lower-bound gain, never touching the sealed test.
  Offline with a fake proposal and scripted "prompts" whose dial is a config knob.
- **Done when**: a child that wins on train and loses on validation is rejected, and that is a test.

### O4 claims ledger

- **Owns**: `src/pmx/optimizer/claims.py`, `src/pmx/cli_claim.py`, `claims/` (generated but tracked,
  ruling R73), `tests/test_claims.py`.
- **Does**: `pmx claim <genome>`: the single sealed-test run per `(dataset hash, genome hash)`, the
  four-part verdict of PRD 6.2, the ledger file, refusal on reuse.
- **Done when**: a second identical claim is refused and the verdict fields are all present.

### Gate G4

`pmx evolve --generations 30 --population 48 --seed 7` on the real dataset (AC-6); a claim on the
champion (AC-7); the documented result in `docs/BUILD_STATE.md`, whatever its sign.

---

## Wave 5 : surfaces (4 packages in parallel, may start after G2 for U1 and U2, after G4 for U3)

### U1 API v2

- **Owns**: `src/pmx/api/*.py`, `web/src/api.ts`, `web/src/types.ts`, `tests/test_api_v2.py`. The two
  TypeScript files are the typed mirror of the route list of contract 12.12; they moved from U2 to U1 in
  wave 0 (ruling R79) because U3 needs fetchers and types in them too.
- **Does**: read routes for datasets, markets (bars, trades, news), runs, journals, results,
  generations, hive, claims, live book; `POST /runs`, `GET /jobs/{id}/events` (SSE), `POST /claims`
  behind a local token; a worker process for long jobs; every scored response carries `run_id` and
  `dataset_hash`.
- **Done when**: the v1 routes keep working on the demo pack, a job streams progress events, and an
  unauthenticated write is refused.

### U2 web: market and portfolio views

- **Owns**: `web/src/components/market/*`, `web/src/components/portfolio/*`, `web/src/util.ts`.
  It imports `web/src/api.ts` and `web/src/types.ts`, which U1 owns.
- **Does**: true time axis, candles or line with volume histogram, bid/ask band, forecast overlays,
  news markers with hover cards, the as-of news panel, outcome hidden until the cursor passes
  `resolved_at`, fill markers, equity and drawdown, calendar view per agent; canvas fallback above
  5 000 bars.
- **Done when**: AC-2 holds on a Kalshi market of the real dataset and on the demo pack.

### U3 web: leaderboard, calibration, evolution, hive, claims, dataset, live

- **Owns**: `web/src/components/board/*`, `web/src/components/evolution/*`,
  `web/src/components/hive/*`, `web/src/components/claims/*`, `web/src/components/dataset/*`,
  `web/src/components/live/*`, `web/src/App.tsx`, `web/src/styles.css`, `web/index.html`,
  `web/src/main.tsx`, `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, and the four v1
  components (`Leaderboard.tsx`, `MarketReplay.tsx`, `PriceChart.tsx`, `WalkForwardView.tsx`), which U3
  deletes in the same commit that lands `board/`.
- **Does**: leaderboard v2 with intervals, breakdowns and the deflated verdict; reliability curves and
  horizon buckets; generations, gene drift, the MAP-Elites grid, hall of fame, resume; hive browser;
  claims ledger; dataset panel with verify; the live book view.
- **Done when**: every view renders from the API of a real run without a console error and the
  baseline row is pinned.

### U4 CLI v2, run.bat, README, docs

- **Owns**: `src/pmx/cli.py`, `run.bat`, `README.md`, `docs/BUILD_STATE.md`, `pyproject.toml`.
- **Does**: the full command tree of PRD 7.3 wired to the packages, `run.bat` with the optional live
  job, the README rewritten for v2 with the honesty section (AC-10), version bump to 2.0.0.
- **Done when**: every command in the README runs as written on a fresh clone with the demo pack.

### Gate G5

End-to-end from `run.bat`: data status, a backtest, an evolution job launched from the UI and followed
over SSE, a claim shown in the ledger view. AC-2 and AC-10 checked.

---

## Wave 6 : the live forward shadow book (2 packages after G3 and U1)

### L1 live jobs

- **Owns**: `src/pmx/live/*.py`, `src/pmx/cli_live.py`, `live/` (generated), `tests/test_live.py`.
- **Does**: fetch open eligible markets from Kalshi and Manifold through `list_open_kalshi` and
  `list_open_manifold`, which return `OpenMarket` (contract 7.12, added in wave 0 because both importers
  are specified for settled markets only), build today's as-of observation from
  the live Current events page and comments, run the champion set (scripted and LLM), append hashed
  forecasts to `live/forecasts.jsonl` before resolution, poll resolutions daily, score with E3 and E4,
  a Windows Task Scheduler entry created by `pmx live install`.
- **Done when**: a forecast file entry cannot be altered without breaking its hash, and a resolved
  fixture market is scored identically to the backtest path.

### L2 live view

- Folded into U3 (`web/src/components/live/*`) once L1's API routes exist; listed here for the gate.

### Gate G6

The daily job runs for seven days on the scheduler; the live book shows pending and resolved markets
(AC-9). First live numbers, with intervals, recorded in `docs/BUILD_STATE.md`.

---

## Summary

| Wave | Packages | Parallel | Gate checks |
|---|---|---|---|
| 0 contract | C0 (author, 3 critics, arbiter) | no | findings list empty, one owner per file |
| 1 data | D1 D2 D3 D4 D5 D6 D7 | 7 | AC-1, real dataset built and sealed |
| 2 engine | E1 E2 E3 E4 E5 | 5 | AC-3, AC-4, 50-seed determinism |
| 3 agents | A1 A2 A3 A4 A5 A6 | 6 | AC-5, AC-8 partial |
| 4 optimizer | O1 O2 O3 O4 | 4 | AC-6, AC-7 |
| 5 surfaces | U1 U2 U3 U4 | 4 (U1, U2 early) | AC-2, AC-10 |
| 6 live | L1 (L2 in U3) | 1 | AC-9 |

Twenty-seven packages, six gates. The critical path is C0, D1, E1 and E5, A1, O1 and O2, U3, L1. The
scripted optimizer on Kalshi and Manifold (waves 0 to 4 without A5, A6 and O3) is the core deliverable;
the LLM packages and the live wave can slip without invalidating it.

## Ordering rules the gates enforce

- Nothing in `src/pmx/engine` or `src/pmx/agents` imports from `src/pmx/gateway` or `src/pmx/llm`.
- Nothing in `src/pmx/metrics/calibration.py` imports from `src/pmx/engine/execution.py`.
- Nothing outside `src/pmx/optimizer/claims.py` reads the sealed test fold.
- Nothing outside `src/pmx/metrics/stats.py` imports numpy.
- Nothing in `src/pmx` outside `gateway`, `llm`, `live` and `data/importers` opens a socket.
- Every one of these is a test in `tests/test_architecture.py`, owned by the gate.
