# PRD v2 : pmx, the hard agents optimizer

Product requirements for the second version of `pmx`, the prediction-market backtest arena in
`GAN/prediction_market`. This document says **what** and **why**. The technical contract
(`docs/CONTRACTS_V2.md`, to be written as the first work package of the plan) says **how**, and is the
source of truth for code. The wave plan and the parallelizable work packages live in
`docs/PLAN_V2_WAVES.md`.

Written 2026-09-07 after a full review of v1 (code, data, tests, UI) and live probes of every external
data source named below. Every claim about an API in this document was verified from this machine on
that date unless it says otherwise.

---

## 0. Review of v1: what exists, what is good, what blocks the goal

### 0.1 What v1 is

`pmx` v1 (about 2 200 lines, 14 green tests) replays 12 resolved markets tick by tick, lets 8 scripted
agents state a probability and a target position each tick, and scores them by life-average Brier
against the market's own Brier and by PnL after a one-cent spread. It has a tournament, a two-half
walk-forward, a read-only FastAPI on 8175, a React replay UI on 5510 and a Polymarket importer.

What is genuinely good and must be kept:

- **Reality is the referee.** No metric depends on an LLM judge. Outcomes are facts.
- **Integers only for money and probabilities** (cents, parts-per-million, micro-Brier). No float
  ever touches a score.
- **Total determinism.** A run is a pure function of `(market, agents, spread)`.
- **The honest baseline.** `market_follower` reproduces the market's Brier exactly, so "skill" has a
  zero point that cannot be argued with.
- **The `source` flag** that stops a reconstructed path from passing as a real tape.
- **The walk-forward reflex.** v1 already reports that its own train winner (`momentum`) does not win
  on the held-out half (`sharp` does). That is the right instinct; v2 makes it statistically real.

### 0.2 What blocks "a fully working hard agents optimizer"

Ranked by how much each one invalidates a result today.

1. **The data cannot carry a claim.** 12 markets, 6 to 12 control points each, hand-written paths.
   Twelve labels give zero statistical power: any leaderboard difference is noise, and the walk-forward
   verdict flips with one market. There is no volume, no bid/ask, no calendar, no news.
2. **Ticks are control points, not time.** The engine averages Brier per tick, so a two-month gap and a
   three-hour gap on election night weigh the same. The chart draws ticks equally spaced. Every score
   is therefore time-biased toward whatever the author of the path chose to sample.
3. **Agents cannot learn or remember anything.** Each agent is a pure function of one market's price
   history. There is no state across ticks beyond the history tuple, nothing carried from one market to
   the next, no parameters to search, no population, no mutation, no LLM path. Selection has nothing to
   select over except eight fixed archetypes.
4. **The observation leaks the clock.** `n_ticks` and `ticks_remaining` tell the agent exactly when the
   market ends and that the current tick is the settlement tick. Real forecasters know a close date,
   never the tick index of the last trade.
5. **The trade model is not a market.** Infinite liquidity at price plus or minus one cent, no fees, no
   bankroll, negative cash allowed, a flat 100-contract limit. PnL is therefore only a rescaled
   disagreement with the price, not money.
6. **The importer is unusable from France.** `gamma-api.polymarket.com` and `data-api.polymarket.com`
   resolve to `offre-illegale.anj.fr` (the French gambling regulator's block page, certificate
   `CN=*.anj.fr`). This is a legal block, not a network fault. A Polymarket-only data strategy is dead
   on this machine and in this jurisdiction.
7. **No persistence.** Nothing is journaled. The API recomputes every tournament per request and no run
   can be cited, diffed or replayed later.
8. **No statistics.** No confidence interval, no paired test against the baseline, no correction for
   picking the best of many agents (the selection itself creates the illusion of skill).
9. **No LLM contamination defence.** Any LLM asked about an event that resolved before its training
   cutoff already knows the answer. v1 has no LLM agents so this is latent, but it is the single
   biggest trap of the requested extension (LLM agents on the last twelve months) and it must be
   designed in from the start, see section 3.6.

---

## 1. Vision

Turn `pmx` into a **hard optimizer of forecasting agents**: a population of agents (parametric scripted
agents first, LLM prompt agents second) that forecast and trade **real, full-resolution market tapes**
from the **last twelve months**, read **the news of the time and nothing later**, **learn from every
resolution**, **share a memory** of past predictions and lessons, are **explored, selected, cloned and
mutated** across generations, and are judged **only on sealed held-out markets, after real fees, with
confidence intervals**. Beating the market is the hard case and remains the only claim worth making. A
run that proves an apparent edge is noise stays a valid, valuable outcome.

Two mechanics coexist, as in `GAN/docs/REAL_WORLD_ARENAS.md`:

- **Selection**: many agents, the world pays them, the worst die, the best clone with mutation.
- **Coop**: diverse agents forecast independently, a stacker learns whom to trust and how to combine
  them, and the ensemble is itself an agent that must beat both the market and its own members.

### 1.1 What v2 demonstrates

One table, reproducible from a seed and a sealed dataset:

- Which agent families beat the market on Brier after fees, on markets they never saw, with a
  confidence interval that excludes zero.
- Whether learning across markets (memory, recalibration) and shared memory (the hive) improve held-out
  skill against the same agents run amnesic.
- Whether evolution finds agents the hand-written archetypes did not, and whether those survive the
  sealed test.
- For LLM agents, the same numbers on the only leak-proof set: markets created after the model's
  training cutoff, plus the live forward shadow book.

### 1.2 Non-goals of v2

- No real-money trading. Polymarket is blocked in France, Kalshi is US-only, and no venue is legal for a
  French account today. v2 is paper only; the live path is a paper shadow book (section 8).
- No multi-outcome or scalar markets in the engine. Binary YES/NO only; multi-outcome events are
  imported as their binary legs.
- No LLM judge anywhere in scoring, ever.
- No web-scale news crawler. News is a dated, as-of-filtered digest from public archives (section 3.4),
  not a full-text corpus.

---

## 2. Principles (non-negotiable, inherited from Exchange and v1)

1. **Money, prices and probabilities are integers.** Prices move to **basis points** in `[1, 9999]`,
   settling at `10000` or `0`; probabilities stay in parts-per-million; Brier in micro-units; cash in
   cents. No float touches a score, a fill or a balance. Floats are legal only for provider-reported
   costs (USD of an LLM call), which never enter a journal.
2. **The journal is the only source of truth.** Every run writes an append-only JSONL journal with no
   wall clock, no floats, no LLM provider metrics; every metric is a projection of the journal; a run
   replays byte for byte from its journal and its hash is the artefact.
3. **All randomness comes from one seeded RNG tree** with named substreams. No `random.random()`, no
   `uuid4()`, no clock in the engine.
4. **The engine never calls an LLM.** Only the gateway is asynchronous; async functions carry the `a`
   prefix (`acollect_forecasts`). `run_backtest` stays synchronous.
5. **As-of is a law.** At simulated time `t` an agent sees only prices, trades, news and hive entries
   whose timestamp is at most `t` minus a safety lag. This is enforced by the observation builder, not
   by asking agents to behave, and it is tested by injecting a poisoned future item and asserting it
   never appears.
6. **The sealed test set is touched by a named claim, logged, and refused on reuse.** Selection happens
   on train and validation folds only.
7. **Code, comments and identifiers in English.** No em-dash character anywhere in produced content; a
   test sweeps the repository.
8. **No test passes by being weakened.** The integration gate audits for assertions that hold against
   an empty journal.

---

## 3. Data layer v2

### 3.1 Providers (verified 2026-09-07)

| Provider | Status from this machine | What it gives | Role in v2 |
|---|---|---|---|
| **Kalshi** (`api.elections.kalshi.com/trade-api/v2`) | Public, no auth for market data (200 on `/markets?status=settled`, `/markets/trades`, `/historical/markets`, `/historical/cutoff`) | Regulated USD markets, real trades with taker side and price, candlesticks (1 min, 1 h, 1 day) with yes bid/ask, OHLC, volume, open interest. Markets settled before the cutoff (observed `2026-07-08`) live under `/historical/...` | **Primary real-money tape.** The hardest, most efficient prices available legally as data. |
| **Manifold** (`api.manifold.markets/v0`) | Public, 200 on `/search-markets?filter=resolved`, `/bets?contractId=`, `/comments?contractId=` | Every bet with `probBefore`, `probAfter`, `amount`, `outcome`, `createdTime`; every comment with timestamp; `resolution`, `resolutionTime`, `uniqueBettorCount`, `volume` | **Primary volume tape and sparring tier.** Play money, so prices are less efficient; results are reported per provider and never pooled with Kalshi in a claim. Comments are a dated, market-specific news proxy. |
| **Polymarket** (Gamma + CLOB) | **Blocked in France by ANJ DNS hijack** (resolves to `offre-illegale.anj.fr`). `prices-history` supports `interval` (max, all, 1m, 1w, 1d, 6h, 1h), `fidelity` in minutes, `startTs`, `endTs` | Sub-cent prices, deep tapes on the biggest markets | **Optional, out-of-jurisdiction runner only.** Importer kept, given an explicit proxy setting, and made to fail with a clear "blocked by ANJ" message when the served certificate is not Polymarket's. Never on the critical path. |
| **Metaculus** | 403 without a token; a free account gives one | Community forecast history on long-horizon questions | **Optional**, behind `PMX_METACULUS_TOKEN`. Useful as a non-market forecaster baseline, not as a tradable tape. |

Every imported market records `provider`, `provider_id`, `url`, `currency` (`usd` or `mana`) and
`source: "imported"`. `reconstructed` stays a legal source for demos and tests and is never allowed in
a sealed dataset.

### 3.2 The twelve-month window and the past-only rule

- A dataset has a **freeze date** `T` (UTC date, stamped in its manifest). It contains only markets
  with `resolved_at` in `[T - 365 days, T - 1 day]`. Nothing unresolved, nothing older, nothing that
  resolved on the freeze day itself (settlement data is often still moving).
- Markets are additionally required to have **opened** inside the window or at most 90 days before it
  starts, so that the "news of the time" archive covers the whole life of each market.
- `pmx data refresh` slides the window forward to a new `T`, re-imports, re-seals. Old datasets are
  never edited; a dataset is identified by its manifest hash.
- **Quality filters** (all configurable, all reported in the manifest with counts of what they
  removed): binary only; at least 50 trades or 30 unique bettors; life of at least 7 days; at least one
  bar per day of life after resampling; no self-resolved creator markets on Manifold; no
  `KXMVE...` style multi-leg auto-generated Kalshi shards (they resolve in minutes and carry no
  forecasting content).
- **Hardness tags**, computed and stored, never used to drop: `trivial` (the market never left
  `[500, 9500]` bp), `upset` (final 30 days average price on the wrong side of 5000), `whipsaw` (more
  than four crossings of 5000), `illiquid` (median daily volume in the bottom decile). Leaderboards
  break down by tag so an agent that only wins on trivial markets is visible.
- Target size: **at least 300 Kalshi and 300 Manifold markets** after filters, across at least six
  categories, with the YES/NO balance reported. If Kalshi's twelve months yield fewer than 300 after
  filters, the manifest says so and the claim is scaled to the count.

### 3.3 Full tapes: trades, bars, and the schema v2

Raw provider data are irregular trades. The engine consumes **regular bars**.

- `trades`: the raw prints as imported, `(t_ms, price_bp, size_milli, side)`. Kept for the chart and
  for the fill model, never edited.
- `bars`: resampled OHLC on a fixed grid, `interval` in `{60, 1440}` minutes, with `open, high, low,
  close, vwap` in bp, `volume_milli` (contracts, or mana for Manifold), `n_trades`, and when the
  provider gives them `yes_bid_bp`, `yes_ask_bp`, `open_interest`. Bars with no trades repeat the last
  close and carry `volume_milli = 0`, so "no trading happened" is visible to agents and to the fill
  model.
- Market metadata: `id, provider, provider_id, url, question, description, category, tags, currency,
  created_at, close_at, resolved_at, resolution (0/1), resolution_source, n_bars, first_price_bp,
  last_price_bp, hardness_tags`.
- The v1 file schema is migrated by `pmx data migrate-v1`: cents become bp times 100, control points
  become a `bars` list at daily interval with `volume_milli = 0` and `source: "reconstructed"`. The 12
  v1 markets stay as a demo pack, excluded from any sealed dataset.
- JSON schemas ship in `schemas/market.v2.json`, `schemas/news.v1.json`, `schemas/dataset.v1.json`,
  `schemas/journal.v2.json`, and the loader validates against them.

### 3.4 Dated news of the time

The goal is not a news corpus; it is a **dated, as-of-filterable context** so that an agent at time `t`
can read what a careful human could have read at `t`.

| Source | Verified | Coverage | Use |
|---|---|---|---|
| **Wikipedia Portal:Current events**, one page per day, via the MediaWiki API (`action=parse`) | 200 with a descriptive User-Agent that carries a contact address (403 without) | Every day, back years, human-curated headlines with links to the original press articles | **Primary.** One `NewsItem` per bullet: `published_at` (the page day, 23:59 UTC as a conservative bound), `headline`, `section` (armed conflicts, politics, business, science, sport...), `wiki_links`, `source_urls`. |
| **Manifold comments** on the market itself | 200 | Per market, timestamped | Market-specific discussion as of `t`, `kind: "comment"`. |
| **Wayback Machine CDX** for front pages of major outlets | 200 | Snapshots per day back years | Optional headline snapshots; text extracted from the archived HTML, `kind: "frontpage"`. Rate-limited, cached, best effort. |
| **GDELT DOC 2.0** | 429 unless one request per 5 s; documented 3-month rolling window | Recent three months only | Optional enrichment of the most recent slice, throttled at 5 s, `kind: "article"`. Never required. |
| **Wikipedia article revisions as of a date** (`prop=revisions&rvstart=`) | 200 | Any article, any date | **Point-in-time background knowledge**: the article on the market's subject as it stood at `t`, not as it stands now. Fetched lazily per market for the LLM agents' context. |

Rules:

- Every `NewsItem` has `published_at` (UTC ms), `fetched_at`, `source`, `kind`, `url`, `text`, and
  `match_ids` (markets it is linked to). Linking is deterministic: shared wiki links between the
  market's subject page and the item, then keyword overlap with the market question and tags, scored
  and thresholded, stored with the score so it is auditable.
- The news archive is frozen with the dataset and enters the manifest hash. Agents cannot fetch live.
- **As-of with a safety lag** of 6 hours by default (a Wikipedia bullet for day D is treated as
  readable from D+1 06:00 UTC). The lag is a dataset parameter, logged.
- News is attached to the dataset, not to a run, so two runs on the same dataset read the same world.

### 3.5 The dataset manifest and the seal

`data/datasets/<name>/manifest.json` records: freeze date, window, providers, filter counts, hardness
tag counts, news sources and their fetch dates, safety lag, the split (section 6.1), and a SHA-256 over
the canonical serialisation of every market and news file. `pmx data seal` computes it; `pmx data
verify` recomputes and refuses any run on a dataset whose hash does not match. A sealed dataset is
immutable by convention and by test.

### 3.6 LLM contamination: the trap, named

The Claude models available today have a training cutoff of June 2026. A dataset frozen on 2026-09-07
covers 2025-09 to 2026-09, so **about three quarters of it is inside the model's knowledge**. Any LLM
agent "forecasting" those markets is recalling, not forecasting, and any prompt telling it to pretend
otherwise is not evidence.

v2 handles this structurally:

1. **Scripted and parametric agents are the backtest population.** They have no knowledge cutoff and no
   contamination problem. The optimizer's core claim is made with them.
2. **Every LLM model carries a declared `knowledge_cutoff`** in configuration. A market is `clean` for a
   model only if `created_at` is after that cutoff. Leaderboards for LLM agents are computed on clean
   markets only and say so in every row.
3. **Contamination audit** (`pmx audit contamination --model X`): for each market, ask the model for
   the outcome with the question alone and no context, three paraphrases, temperature zero. A market
   where the model is right and confident above a threshold is tagged `contaminated:<model>` and
   excluded from that model's scores even if it is nominally clean (cutoff dates are approximate).
4. **The live forward shadow book** (section 8) is the only fully leak-proof arena for LLM agents, and
   it is the arena where LLM claims are made.

---

## 4. Engine v2

### 4.1 Time, calendar, and the multi-market world

- The engine runs a **calendar of bars**, not a per-market tick list. A run has `t0`, `t1`, an
  `interval` (60 or 1440 minutes) and processes every bar timestamp in order. At each bar every market
  that is open (`created_at <= t < close_at`) is visible; markets settle at their `resolved_at` bar.
- Agents therefore see and hold **many markets at once** and manage one bankroll across them. Capital
  allocation, correlation between markets (five markets on one election) and time budgeting are part of
  the skill, and part of what is scored.
- Sequential learning is honest by construction: a market's outcome enters memory only at its
  `resolved_at` bar (section 5.3).

### 4.2 The observation

Per agent per bar, one `Observation` (contract in `CONTRACTS_V2.md`):

- `now` (UTC ms) and the calendar facts a human knows: `close_at` per market (public on every venue),
  never `resolved_at`, never a bar index or a bar count.
- Per open market: metadata, the last `N` bars (window configurable, default 90 daily or 168 hourly),
  the last trades if the agent asks for microstructure, current best bid/ask when known, volume stats.
- `news`: the as-of digest, ranked by link score, capped (default 20 items per market, 50 global).
- `portfolio`: cash, positions, unrealised equity, fees paid, open limit orders.
- `memory`: the agent's own memory handle (section 5.3) and the hive view as of `now` (section 5.4).
- Never: outcome, future bars, future news, hive entries stamped after `now`, other agents' current
  forecasts (they arrive in the hive only after resolution).

### 4.3 Actions

Per market: `prob_ppm` (always required, scored by Brier even when the agent does not trade), and one
of `hold`, `target_position` (contracts, signed), `limit_order(side, price_bp, size, ttl_bars)`, or
`abstain` (explicit no-position; recorded because abstention is a strategy and is analysed).
Per agent: an optional `research` request (more news, deeper history, a point-in-time Wikipedia
article) that costs a configurable **research budget** unit, so exploration has a price and its value
can be measured; and `notes` (free text, at most 500 characters) that go to the agent's memory and,
after resolution, to the hive.

### 4.4 Execution and accounting

- **Bankroll**: every agent starts each run with `bankroll_cents` (default 100 000, that is 1 000 USD).
  Cash cannot go negative; a short YES is a long NO paid at `10000 - price`. An agent at zero equity is
  frozen for the rest of the run (`ruined`), which is both a metric and a selection event.
- **Fills against real liquidity**: a market order fills at the bar's `vwap` (or the quoted ask/bid when
  present) plus a slippage of `k` bp per contract beyond a `volume_cap` fraction of the bar's volume
  (default 10 percent); the remainder is not filled and is reported. A bar with zero volume fills
  nothing. Limit orders fill only if the bar's range crosses the limit and volume allows.
- **Fees per provider**, encoded as config with a source link and a date: Kalshi taker fee as a function
  of price and size per its published schedule; Polymarket zero on standard markets; Manifold zero.
  Fees are integers in cents and are journaled per fill.
- **Settlement** at `resolved_at`: positions pay `10000` or `0` bp per contract. Invariant tested by
  property tests: `final_cash == bankroll + sum(fill cash flows) - fees + settlement` for every agent,
  every seed.
- Equity is marked to the last close each bar for the drawdown series.

### 4.5 Scoring

All in integers, all projections of the journal, all reported per agent, per provider, per category,
per hardness tag, per fold.

Forecasting:

- **Time-weighted Brier**: the integral of the per-bar Brier over the market's life divided by the life
  length, so an hour weighs an hour. On a regular grid it equals the mean; on the migrated v1 paths it
  removes the control-point bias.
- **Horizon-bucketed Brier** at 30, 7, 2 and 0 days before `close_at`: who is right early.
- **Brier skill score** versus the market's own price on the same bars (v1's `skill_vs_market`,
  kept), and versus the fixed 5000 bp forecast.
- **Log score** (integer micro-nats, clamped at 1 percent and 99 percent) as a secondary metric that
  punishes confident wrongness harder.
- **Calibration**: reliability curve in 10 bins, expected calibration error, sharpness. Decoupled from
  PnL by construction: the calibration module never reads a fill.
- **Price-move value (PMV)**: `sign(prob - price_t) * (price_{t+h} - price_t)` at `h` in `{1, 7}`
  days. Did the market move toward the agent before resolution? A signal on every bar, long before
  the label, which densifies selection the way closing-line value does for sports.

Trading:

- PnL after fees in cents; return on bankroll; max drawdown; a Sharpe-like ratio on daily equity
  changes (integer basis-point mean over integer bp standard deviation, reported as milli-units);
  turnover; fill ratio; fees paid; `ruined` flag; abstention rate.

Statistics (section 6.2): bootstrap confidence intervals over markets, paired against
`market_follower`, block-bootstrapped by ISO week to respect correlated markets; a permutation null
that shuffles outcomes across markets and re-scores, so any metric that survives outcome shuffling is
exposed as not being about outcomes.

### 4.6 Journal and runs

`runs/<run_id>/` holds `manifest.json` (dataset hash, config, seed, agent roster with genomes),
`journal.jsonl` (events: `BarOpened`, `ForecastRecorded`, `OrderPlaced`, `Filled`, `FeeCharged`,
`Settled`, `MemoryWritten`, `HiveWritten`, `AgentRuined`, `GenerationClosed`...), `journal.sha256`,
`results.json` (the projection), and for LLM runs `llm_trace.jsonl` (cost, latency, tokens, verbatim
text: outside the hash by construction). `pmx replay <run_id>` rebuilds `results.json` from the journal
and asserts equality. The event catalogue is in the contract and mirrors Exchange's conventions so the
two projects can share tooling.

---

## 5. Agents v2: exploration, selection, action, knowledge, shared memory

### 5.1 The agent protocol

An agent is a stateful object with a stable `agent_id`, a `family`, a `genome` (parameters, or a prompt
plus dials), and four methods: `observe(obs)`, `decide() -> Actions`, `learn(resolution_event)` called
at each settlement the agent held or forecast, and `snapshot() -> dict` (its memory, journaled so a run
replays). Scripted agents are synchronous and pure given `(genome, memory, observation, rng
substream)`; LLM agents route through the gateway (section 5.6). `explain()` returns the reasons the
UI shows (for scripted agents a feature dump, for LLM agents the model's rationale).

### 5.2 Parametric scripted families (free, deterministic)

The eight v1 archetypes become **genomes** rather than constants, and new families join. Every gene is
an integer in a declared range with a declared mutation step. All genes are visible in the UI.

| Family | Genes (examples) | Idea |
|---|---|---|
| `follower` | `shrink_permille`, `edge_min_bp` | Believe the price, optionally shrunk to 5000. Baseline at shrink 1000, edge_min 0 reproduces the market exactly. |
| `trend` | `lookback_bars`, `lean_bp_per_bp`, `confirm_bars` | Momentum and `sharp` unified. |
| `revert` | `half_life_bars`, `fade_permille`, `band_bp` | Mean reversion toward a moving anchor rather than a coin flip. |
| `timedecay` | `longshot_fade_bp`, `days_ref` | Favorite-longshot correction that grows as `close_at` nears (longshots die near the close). |
| `volume` | `vol_lookback`, `conviction_per_vol` | Trust a move more when it came on volume; fade thin moves. |
| `breakout` | `range_bars`, `trigger_bp`, `hold_bars` | Range breakouts on bars. |
| `newsbayes` | `prior_permille`, `lexicon_id`, `weight_per_hit`, `decay_bars` | A deterministic lexicon (per category, shipped as data) scores as-of headlines for or against; posterior update from the market prior. This is the free "reads the news" agent. |
| `calibrator` | `bins`, `min_n`, `shrink_to_prior` | Wraps any other family and recalibrates its output with a binned table learned from resolved markets (section 5.3). |
| `specialist` | `category`, `inner_family`, `outside_mode` | Trades only its category, follows the market elsewhere. |
| `kelly` | `kelly_permille`, `max_position_pct`, `min_edge_bp` | Sizing overlay: any belief, Kelly-fraction sizing on the bankroll. |
| `stacker` | `k`, `window_markets`, `extremize_permille` | Coop: weights the members it is composed with by their rolling hive reputation and extremizes the mean. Reputation comes only from resolved markets, so it never copies a live forecast. |

Families compose: a `kelly(calibrator(newsbayes))` is one genome. Composition depth is capped (3).

### 5.3 Learning across markets: the agent's own memory

At every settlement the agent receives `(market, its own forecasts over the life, outcome, its PnL)`
and may update a **memory** that persists across markets and across runs of the same agent id:

- a **calibration ledger** per category and per horizon bucket: counts of forecasts in each bin and
  the observed YES rate, used by `calibrator`;
- **category priors**: base rates of YES per category and per hardness tag as seen so far;
- **feature statistics** for `trend`, `volume`, `newsbayes` (for example the realised sign of moves
  after a lexicon hit);
- **lessons**: for LLM agents, a bounded list of short text post-mortems the model itself writes at
  settlement ("I overweighted the poll bump in three of four politics markets").

Memory is journaled (`MemoryWritten`) so a run replays, is bounded in size (contract constant), and can
be reset (`--amnesic`) to measure exactly what learning buys. Memory produced in a training fold may be
carried into validation; memory is **frozen** before the sealed test (the test never teaches).

### 5.4 Shared memory: the hive

An append-only knowledge base shared by the whole population, with strict as-of visibility:

- **Entries**: `ForecastRecord` (agent, market, bar, prob) written at each bar but **visible only after
  the market resolves**; `Resolution` (market, outcome, the market's life-average price); `Lesson`
  (agent, text, evidence market ids); `Reputation` (rolling Brier and PnL per agent per category,
  computed by the engine, not declared by agents).
- **Visibility rule**: an entry stamped `visible_from` is readable at `now >= visible_from`. Forecasts
  become visible at the market's `resolved_at`, so nobody copies a live forecast; lessons are visible
  the bar after they are written.
- **Use**: `stacker` reads reputation; `calibrator` may pool the whole population's resolved forecasts
  when its own history is thin; LLM agents get the top lessons by reputation in their context; the
  evolution loop reads reputation to pick parents.
- **Poisoning defence**: lessons carry the author's reputation and are ranked by it; a test writes a
  deliberately false lesson from a low-reputation agent and asserts its rank.
- The hive is journaled (`HiveWritten`), replays, and has an **amnesic switch** so "does sharing help"
  is an experiment, not an assumption.

### 5.5 Exploration

- **Parameter exploration**: gaussian mutation on genes with per-gene step, occasional gene reset,
  uniform crossover between two parents, all from the seeded RNG.
- **Structural exploration**: mutation may swap a family in a composition or add an overlay (`kelly`,
  `calibrator`), within the depth cap.
- **MAP-Elites archive** over behavioural descriptors computed by the engine: turnover decile,
  contrarian-ness (mean signed distance from price), average holding horizon, category coverage,
  abstention rate. Each cell keeps its best genome, so diversity is preserved and the UI shows a grid.
- **Novelty pressure**: a child whose descriptor vector lands in an empty cell gets a survival bonus
  for one generation.
- **Research budget**: agents that spend `research` units and do not convert them into skill lose the
  budget in the next generation; the value of exploration is measured, not assumed.

### 5.6 LLM agents

- **Gateway**: the Claude Code CLI, one subprocess per agent per bar covering every open market at
  once, with USD and token caps checked before the call, retries inside the bar timeout, fallback to
  "carry previous forecasts" on failure, trace to `llm_trace.jsonl`. This is Exchange's
  `pxe.gateway` design and the contract says which parts are copied verbatim.
- **Models**: `claude-haiku-4-5` for a cheap population, `claude-sonnet-5` as default, `claude-fable-5-1`
  for an elite seat. Each with its declared `knowledge_cutoff`.
- **Prompt genome**: a fixed system frame plus dials, each an integer level: `base_rate_discipline`,
  `news_weight`, `contrarian_appetite`, `kelly_fraction`, `memory_reliance`, `hive_reliance`,
  `verbosity`. Dials are text blocks selected by level, so mutation is discrete and journaled.
- **Context**: the observation rendered as compact text; the as-of news digest; the agent's lessons;
  the top hive lessons; the point-in-time Wikipedia article if requested through `research`.
- **Output**: strict JSON validated against `schemas/actions.v2.json`; invalid output is a fallback,
  never a crash.
- **Contamination**: scored only on `clean` and not `contaminated:<model>` markets (section 3.6);
  every LLM leaderboard row displays `n_clean`.

### 5.7 Selection and evolution

A **generation** is one tournament of the population on the training folds of the dataset. Then:

1. Rank by the **selection objective**, configurable and logged: default is time-weighted Brier skill
   versus the market with a PnL-after-fees tie-break, both as bootstrap lower bounds, not point
   estimates (an agent is ranked by what it can defend, not by its best case).
2. **Cull** the bottom `cull_pct` (default 30 percent) and every `ruined` agent.
3. **Clone with mutation** from parents drawn with probability proportional to rank (not to raw
   score, which over-rewards one lucky market), respecting the MAP-Elites cells.
4. **Immigrants**: `immigrant_pct` (default 10 percent) fresh random genomes.
5. **Elitism**: the top `elite_n` survive unchanged; a **hall of fame** keeps the best genome ever per
   family with the run id that produced it.
6. **LLM prompt mutation** (section 5.8) runs for LLM agents in the same step.
7. `GenerationClosed` is journaled with the whole population state, so any generation can be resumed.

Termination: `max_generations`, or no improvement of the validation-fold lower bound for `patience`
generations. Population, budgets and every rate are config, and the config is in the run manifest.

### 5.8 Prompt mutation for LLM agents

Mirrors Exchange's planned `pxe.evolve`: extract the champion's worst markets, feed their traces to a
patch-proposal call (itself through the gateway, on `claude-sonnet-5`), produce a child prompt, run the
child and the parent on the same validation fold, **promote only on a held-out gain** with a
confidence bound, and never on the sealed test. Built and tested offline with a fake proposal call and
scripted "prompts" whose dial is a config knob, so the gate is provably impossible to bypass.

### 5.9 Ensembles as first-class agents

The `stacker` family and a fixed `top_k_extremized_mean` are agents like any other: they are ranked,
they can be culled, and their claim on the sealed test is that they beat both the market and each of
their members. If they do not, that is reported as such.

---

## 6. Evaluation protocol

### 6.1 Splits

Markets are ordered by `resolved_at`. The dataset is split into **rolling-origin folds**: with a
twelve-month window, months 1 to 8 are training, months 9 and 10 validation, months 11 and 12 the
**sealed test**. Rolling variants (train 1..k, validate k+1) are used for the patience criterion.
Memory and hive states carry forward in time only. The sealed test is never used for any decision;
`pmx claim` runs it once per named claim, writes `claims/<claim_id>.json` with the dataset hash, the
genome, the results and the confidence intervals, and refuses a second claim with the same genome on
the same dataset.

### 6.2 What counts as beating the market (the hard bar)

An agent is said to beat the market on a dataset only if, on the sealed test, on markets it never saw:

- its time-weighted Brier skill versus the market has a 95 percent block-bootstrap lower bound above
  zero, over at least 60 markets;
- its PnL after fees is positive with the same bound;
- the same statement holds after **deflation** for the number of agents that were compared to reach
  it (the contract fixes the method: a Bonferroni-style correction on the family-wise count of
  candidates evaluated on validation, logged by the optimizer);
- the permutation null (outcomes shuffled) gives a skill lower bound at or below zero for that agent.

Anything short of that is reported as "no demonstrated edge", which is the expected result for most
agents and a result the product treats as first-class.

### 6.3 Anti-leak tests that ship with the product

- The poisoned-future test: a future bar, a future news item and a future hive entry are injected; the
  observation builder must never surface them (asserted by content match).
- The clock test: an observation never contains a bar count, a bar index relative to the end, or
  `resolved_at`.
- The shuffled-outcome test: with outcomes permuted, no scripted agent's skill lower bound exceeds
  zero on the training set over 200 seeds.
- The amnesic test: `--amnesic` and `--no-hive` produce a different journal hash and the difference in
  skill is reported, so learning is measured rather than assumed.
- The seal test: a byte changed in any dataset file makes `pmx data verify` fail and any run refuse to
  start.

---

## 7. Surfaces: UI, API, CLI

### 7.1 Web UI v2 (React, port 5510)

- **Market view**: a true time axis; candlesticks or line per bar with a volume histogram; bid/ask band
  when known; agent forecast overlays; **news markers** on the axis with hover cards (headline, source,
  link) and a scrolling **as-of news panel** that only ever shows items readable at the cursor; the
  outcome hidden until the cursor passes `resolved_at`; per-agent equity, position, fills as markers.
- **Portfolio view**: one agent across all its open markets on a calendar, equity and drawdown curves,
  fees, ruin events.
- **Leaderboard v2**: per provider, per category, per hardness tag, per fold; confidence intervals as
  bars; the baseline row pinned; the deflated verdict column; LLM rows with `n_clean`.
- **Calibration view**: reliability curves and horizon buckets per agent.
- **Evolution view**: generations on the x axis, population skill distribution, gene drift, the
  MAP-Elites grid with cell occupancy, the hall of fame, resume from generation `g`.
- **Hive browser**: lessons ranked by reputation, forecasts per market after resolution, reputation
  over time.
- **Claims ledger**: every sealed-test claim with its verdict, never editable.
- **Dataset panel**: window, freeze date, filters and what they removed, seal hash, verify button.
- **Live shadow book** (section 8): open markets, today's forecasts sealed with their hash, pending
  resolutions, realised score so far.

### 7.2 API v2 (FastAPI, port 8175)

Read: datasets, markets with bars and trades and news, runs, journals, results, generations, hive,
claims, live book. Write (local only, token-guarded): `POST /runs` (backtest or evolution) returning a
job id, `GET /jobs/{id}/events` as server-sent events for progress, `POST /claims`. Long jobs run in a
worker process; the API never blocks on a generation. Every response that carries a score also carries
the run id and dataset hash it came from.

### 7.3 CLI v2

`pmx data import kalshi|manifold|polymarket|metaculus`, `pmx data news fetch`, `pmx data build`,
`pmx data seal|verify|status|migrate-v1`, `pmx backtest`, `pmx tournament`, `pmx evolve`, `pmx resume`,
`pmx replay`, `pmx claim`, `pmx audit contamination|leaks|tests`, `pmx live forecast|resolve|score`,
`pmx api serve`. `run.bat` starts the API, the UI and, optionally, the live daily job.

---

## 8. The live forward shadow book

The leak-proof arena, and the bridge to the world:

- Daily job: fetch currently open Kalshi and Manifold markets matching the dataset filters; build the
  as-of observation from live news (today's Wikipedia Current events page, comments); every agent in
  the current champion set forecasts; forecasts are journaled with a hash of `(agent, market, prob,
  timestamp)` published to `live/forecasts.jsonl` **before** resolution and never edited after.
- On resolution (polled daily), score exactly as in backtest; the live leaderboard grows one market at a
  time and reports its own confidence intervals.
- LLM agents run here with no contamination caveat. This is where "can selected, aggregated LLM
  forecasters beat the market" gets its honest answer, one resolution at a time.
- Paper only in v2. The same loop would drive a real account with no redesign; that is a legal question
  before it is a technical one, and it is out of scope.

---

## 9. Architecture

```
src/pmx/
  types.py                 Market, Bar, Trade, NewsItem, Observation, Actions, Genome, events (bp, ppm, cents)
  rng.py                   seeded RNG tree, named substreams (copied from Exchange's pxe.rng)
  journal.py               JSONL append, canonical serialisation, sha256, replay
  scoring.py               Brier (time-weighted, horizon), log score, PMV, integers only
  data/
    schema.py              pydantic models for market.v2, news.v1, dataset.v1
    loader.py              load and validate, dataset manifest, seal and verify
    resample.py            trades -> bars on a fixed grid
    importers/{kalshi,manifold,polymarket,metaculus}.py
    news/{wikipedia_current_events,wikipedia_asof,wayback,gdelt,manifold_comments,linker}.py
    builder.py             window filter, quality filters, hardness tags, split, manifest
    migrate_v1.py
  engine/
    calendar.py            bar timeline, open markets per bar
    observation.py         as-of builder (the leak boundary)
    execution.py           fills, slippage, volume caps, fees, bankroll, settlement
    fees.py                per-provider schedules with source and date
    runner.py              run_backtest over a calendar, journaling every event
  agents/
    protocol.py            Agent, Genome, Memory, Actions
    families/{follower,trend,revert,timedecay,volume,breakout,newsbayes,calibrator,specialist,kelly,stacker}.py
    memory.py              per-agent memory, bounded, journaled
    hive.py                shared memory with as-of visibility and reputation
    registry.py            family registry, composition, genome (de)serialisation
  gateway/
    protocol.py, claude_cli.py, budget.py, prompt.py, scripted.py   (Exchange design)
  llm/
    forecaster.py          LLM agent, prompt genome and dials, JSON output validation
    contamination.py       audit and tagging per model
    mutate.py              prompt patch proposal, A/B, held-out promotion gate
  metrics/
    projection.py          journal -> rows
    calibration.py, performance.py, behavioral.py, stats.py (bootstrap, permutation, deflation)
    leaderboard.py
  optimizer/
    folds.py               rolling-origin splits, sealed test
    tournament.py          one generation
    evolution.py           cull, clone, mutate, immigrants, elites, MAP-Elites archive, resume
    claims.py              the claims ledger
  live/
    fetch_open.py, forecast_job.py, resolve_job.py, book.py
  api/
    app.py, routes_read.py, routes_jobs.py, sse.py, worker.py
  cli.py
schemas/                   market.v2.json, news.v1.json, dataset.v1.json, actions.v2.json, journal.v2.json
data/
  demo_v1/                 the 12 migrated reconstructed markets (never sealed)
  datasets/<name>/         markets/, news/, manifest.json
runs/<run_id>/             manifest.json, journal.jsonl, journal.sha256, results.json, llm_trace.jsonl
claims/                    one file per sealed-test claim
live/                      forecasts.jsonl, resolutions.jsonl
web/                       React 19 + Vite + TypeScript, port 5510
```

Stack: Python 3.12, pydantic 2, FastAPI, uvicorn, httpx; stdlib `sqlite3` for the run index and the
hive index (no ORM); React 19 and Vite; charts hand-drawn in SVG as in v1, with a canvas fallback for
tapes above 5 000 bars. No numpy in the scoring path (integers), numpy allowed only in the statistics
module for the bootstrap, with results rounded to integers before they are reported.

---

## 10. Acceptance criteria (product level)

- **AC-1 Data**: `pmx data build --provider kalshi,manifold --freeze 2026-09-07` produces a sealed dataset
  with at least 300 markets per provider (or documents why fewer), bars, trades, news with as-of
  stamps, hardness tags and a manifest hash; `verify` passes; a one-byte change fails it.
- **AC-2 Chart**: the UI shows a Kalshi market on a true time axis with candles, volume, news markers
  and the as-of panel, and the outcome stays hidden until the cursor passes `resolved_at`.
- **AC-3 Engine**: a run of the full scripted population on the dataset journals, replays with an
  identical hash, and satisfies the accounting invariant on every agent for 50 seeds.
- **AC-4 Leak**: the poisoned-future, clock, seal and shuffled-outcome tests pass and are part of `pmx
  audit leaks`.
- **AC-5 Learning**: `--amnesic` and `--no-hive` runs are produced and the skill deltas reported with
  confidence intervals in the leaderboard, whatever their sign.
- **AC-6 Evolution**: `pmx evolve --generations 30 --population 48 --seed 7` completes, resumes from
  any generation with an identical continuation, fills at least 40 percent of the MAP-Elites cells,
  and records a hall of fame.
- **AC-7 Claim**: `pmx claim` on the champion writes a ledger entry with the four-part verdict of
  section 6.2 and refuses a second identical claim.
- **AC-8 LLM**: a `claude-haiku-4-5` population runs one generation on the clean subset within a
  configured USD cap, every row shows `n_clean`, and the contamination audit tags at least the markets
  the model answers correctly with no context.
- **AC-9 Live**: the daily job forecasts every open eligible market, publishes hashed forecasts before
  resolution, and scores resolved ones; the UI shows the live book.
- **AC-10 Honesty**: the README states which results are on play money, which are on real-money
  tapes, which LLM results are on clean markets only, and the whole test suite (target above 200
  tests, property tests included) is green with no skipped test.

---

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Polymarket blocked by ANJ in France | No Polymarket tape on this machine; possible legal exposure of running it | Kalshi and Manifold primary; Polymarket importer optional, proxy-only, with an explicit block detector and a README note. No real money anywhere. |
| Kalshi historical cutoff and possible future auth on historical endpoints | Import may need a key | Importer supports both live and `/historical` paths and an optional API key; the dataset caches everything so a build is done once. |
| Kalshi settled list is dominated by auto-generated multi-leg shards | Dataset polluted with minute-long markets | Series allow-list plus the life and trade-count filters; counts of removed markets in the manifest. |
| Manifold is play money | Easier to beat, weaker claim | Provider-separated leaderboards; a claim names its provider; Kalshi is the headline. |
| LLM contamination | Fake skill | Clean-market rule, contamination audit, live shadow book as the only LLM claim arena. |
| Wikipedia and Wayback rate limits and robot policy | Fetch failures | Descriptive User-Agent with contact, on-disk cache, exponential backoff, throttles in config, builds are incremental. |
| GDELT throttle and 3-month window | Thin recent news | Optional only; the Wikipedia portal is the primary and covers the full window. |
| Selection bias makes the champion look skilled | False claim | Deflation for the number of candidates, sealed test, bootstrap lower bounds, permutation null. |
| Correlated markets inflate confidence | Narrow intervals | Block bootstrap by week and by event cluster (markets sharing an event ticker or a wiki subject). |
| LLM cost | Budget overrun | Caps before every call, cheap model for populations, one call per agent per bar covering all markets, offline fakes for all tests. |
| Scope | The plan is large | Waves with gates; the scripted optimizer on Kalshi and Manifold is the core deliverable; LLM and live are later waves that can slip without invalidating the core. |

---

## 12. KPIs of success

- A sealed Kalshi dataset of at least 300 markets built and verified.
- At least one scripted family with a defensible (section 6.2) edge, or a documented negative result
  with intervals for every family, on the sealed test.
- The measured value of memory and of the hive, with intervals, whatever the sign.
- An evolution run that improves the validation lower bound over the hand-written archetypes by at
  least 0.005 Brier skill, or a documented failure to do so.
- A live shadow book with at least 30 resolved markets by the end of the first month of operation.

---

## 13. Open questions

1. Kalshi historical endpoints: do they remain public without a key for the full twelve months? The
   probe today shows public access; the importer must degrade gracefully.
2. Bar interval for the headline claim: hourly bars are truer to the tape but ten times the compute
   and the news granularity is daily. Proposal: daily bars for evolution, hourly for the final claim on
   the champion.
3. Should abstention be rewarded in the selection objective (a Brier-only agent that never trades has
   zero PnL and no ruin risk)? Proposal: no; Brier skill leads, PnL breaks ties, and abstention rate is
   displayed.
4. Whether to allow the `stacker` to read other agents' live forecasts within the same generation
   (true coop) rather than only after resolution. Proposal: a flagged mode, off by default, because it
   creates herding and information cascades that are interesting but confound the claim.
5. Metaculus: worth the token for a community-forecast baseline column? Proposal: yes, as a later
   optional importer.

---

## 14. Revision history

- 1.0, 2026-09-07: first version, after the v1 review and live probes of Kalshi, Manifold, Polymarket
  (blocked), Metaculus (token required), Wikipedia (Current events and revisions), Wayback CDX and
  GDELT (throttled).
