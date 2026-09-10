# pmx v2 build state

Written by integration gate G1 on 2026-09-08. This file records what is on disk, what was actually run
and what it answered. Every number below comes from a command that ran in this repository on that day;
nothing here is a plan or an intention. Gates G2 to G6 append their own sections.

Contract version `2.0` (`docs/CONTRACTS_V2.md`). Rulings R1 to R106 are in that document, sections 15.1
and 15.2.

---

## 1. What exists, wave by wave

### Wave 0, package C0: the contract

| File | State |
|---|---|
| `docs/CONTRACTS_V2.md` | on disk, 230 486 bytes, sections 1 to 16 plus rulings R1 to R106 |
| `src/pmx/schemas/market.v2.json` | on disk |
| `src/pmx/schemas/news.v1.json` | on disk |
| `src/pmx/schemas/dataset.v1.json` | on disk |
| `src/pmx/schemas/actions.v2.json` | on disk |
| `src/pmx/schemas/journal.v2.json` | on disk |
| `src/pmx/schemas/cluster.v1.json`, `opportunity.v1.json` | on disk (amendment C1) |

`src/pmx/v1/**` is the frozen v1 namespace: it still runs and no v2 package edits it.

### Wave 1, packages D1 to D7: the data layer

| Package | Files on disk |
|---|---|
| D1 types, schema, loader, migration | `src/pmx/types.py`, `src/pmx/data/schema.py`, `src/pmx/data/loader.py`, `src/pmx/data/migrate_v1.py`, `tests/test_types_loader.py` |
| D2 Kalshi importer | `src/pmx/data/importers/kalshi.py`, `src/pmx/data/importers/_http.py`, `src/pmx/data/importers/metaculus.py` (declared, token-gated, unbuilt), `tests/test_import_kalshi.py`, `tests/fixtures/d2/` |
| D3 Manifold importer | `src/pmx/data/importers/manifold.py`, `src/pmx/data/news/manifold_comments.py`, `tests/test_import_manifold.py`, `tests/fixtures/d3/` |
| D4 Polymarket importer | `src/pmx/data/importers/polymarket.py`, `tests/test_import_polymarket.py`, `tests/fixtures/d4/`. Ruling R105 keeps the provider out of a built dataset: its tape carries no size |
| D5 dated news archive | `src/pmx/data/news/wikipedia_current_events.py`, `wikipedia_asof.py`, `wayback.py`, `gdelt.py`, `linker.py`, `src/pmx/lexicons/*.json` (14 files), `tests/test_news.py`, `tests/fixtures/d5/` |
| D6 builder and data CLI | `src/pmx/data/builder.py`, `src/pmx/data/resample.py`, `src/pmx/cli_data.py`, `tests/test_builder.py` |
| D7 RNG and journal | `src/pmx/rng.py`, `src/pmx/journal.py`, `tests/test_rng_journal.py` |

`src/pmx/errors.py` (the taxonomy of section 13.1) and `src/pmx/py.typed` (ruling R99) are on disk.

### Waves 2 to 6

Nothing. `src/pmx/engine/`, `src/pmx/agents/`, `src/pmx/agents/families/`, `src/pmx/gateway/`,
`src/pmx/llm/`, `src/pmx/metrics/`, `src/pmx/optimizer/`, `src/pmx/live/` and `src/pmx/api/` exist as
docstring-only package skeletons so that `tests/test_architecture.py::test_skeleton_matches_the_module_map`
holds; they carry no module of their own yet.

---

## 2. What is green, with the real numbers

Every command was run from the repository root with `.venv\Scripts\python.exe` on 2026-09-08.

| Check | Command | Answer |
|---|---|---|
| Test suite | `-m pytest -p no:warnings -rs` | 566 collected, 562 passed, 4 skipped, 0 failed |
| Lint | `-m ruff check src tests` | `All checks passed!` |
| Types | `-m mypy --strict` | `Success: no issues found in 49 source files` |
| Em-dash sweep | `grep -rn <U+2014> src tests docs README.md` and `tests/test_architecture.py::test_no_em_dash_anywhere_in_produced_content` | no hit |

The four skipped tests are the only legal skips of the contract's rule 7: live network probes behind
`PMX_LIVE=1`, one per importer plus one news probe. No test is `xfail`, none is weakened.

`pyproject.toml` sets `[tool.mypy] files = ["src/pmx"]`, so the 49 type-checked files are the package's
own; the test files are linted by ruff but not type-checked.

Test count per file, from `-m pytest --collect-only -q`:

```
test_api.py 4       test_architecture.py 12   test_builder.py 71     test_contract_schemas.py 81
test_data_and_metrics.py 5    test_engine.py 5    test_import_kalshi.py 50
test_import_manifold.py 61    test_import_polymarket.py 41    test_news.py 57
test_rng_journal.py 118       test_types_loader.py 61
```

This count is the state at the moment this file was written; another package was landing tests in the
same tree while gate G1 ran, so re-run the three commands rather than trusting the total.

---

## 3. AC-1 on the fixture dataset (`data/datasets/ac1_fixtures/`)

Built and sealed by gate G1 from the recorded fixtures of D2, D3 and D5.

```
sealed     true
freeze     2026-09-08   interval 1440 min
window     2025-08-04 .. 2026-09-07
markets    4    yes 2   no 2
provider   kalshi=2 manifold=2
category   politics=2 sports=1 world=1
hardness   upset=1
removed    binary=0 density=0 kalshi_shards=0 min_life=0 min_trades=0
           no_leak=0 opened_early=0 resolution=0 self_resolved=0 window=0
split      train 0   validation 1   sealed 3
news       66 items, 6 linked (gdelt 38, manifold_comment 6, wikipedia_current_events 22)
files      10
hash       c4535882ac4262ecf584c8dc28b7bff175831e1d1b99c769c93f7d0f1974932f
```

- `pmx data verify --dataset data/datasets/ac1_fixtures` prints
  `verified ... c4535882...` and exits `0`.
- The one-byte test was run on a copy of the directory: flipping one byte of
  `markets/manifold-g52tSltgqh.json` makes `verify` exit `1`, print the recomputed hash beside the
  manifest hash, and name the offending file (`mismatched markets/manifold-g52tSltgqh.json`).

**A repair was needed before this held.** The dataset on disk did not verify when this gate resumed:
`markets/kalshi-KXPRESPARTY-28-R.json` carried one flipped byte (`"close_bp":9400` in the first bar,
above that bar's `high_bp` of 4500), left behind by the earlier session's own tamper test, which had been
run in place instead of on a copy. The byte was restored to the value the manifest's per-file
`sha256` (`9401abb0...`) demands and the dataset verifies again. No manifest was rewritten: the recorded
hash was already the correct one.

---

## 4. The first real dataset (`data/datasets/y2026/`)

Built on 2026-09-08 with the real network, through the real CLI, and sealed. The command, verbatim:

```
set PMX_USER_AGENT_CONTACT=etienne.millerioux@studi.fr
.venv\Scripts\python.exe -m pmx.cli_data build ^
  --provider kalshi,manifold --freeze 2026-09-07 --window-days 365 --interval-min 1440 ^
  --keep-self-resolved --kalshi-series <the 731 tickers of data/datasets/y2026/kalshi_series.txt> ^
  --limit-per-provider 400 --min-interval-ms 350 ^
  --out data/datasets/y2026 --name y2026 --force --seal --notes "..."
```

`--keep-self-resolved` is required by ruling R101: 372 of the 400 staged Manifold markets are
`resolution_source == "creator"`, so the default filter would have removed the provider outright.
`--kalshi-series` is required by ruling R100: it is the only narrowing either Kalshi settled listing
honours.

### 4.1 What the fetch half staged

```
staged 400 kalshi markets                    -> staging/markets/kalshi.jsonl
staged 400 manifold markets                  -> staging/markets/manifold.jsonl
staged 7391 wikipedia_current_events items   -> staging/news/wikipedia_current_events.jsonl
staged 1248 manifold_comment items           -> staging/news/manifold_comment.jsonl
staged 8639 news items over 365 days
```

The Wikipedia Current events archive was fetched for the **whole** twelve-month window, 365 days, one
request per day. The HTTP cache under `data/datasets/y2026/cache/` holds 4 475 entries and 589 MB
(Kalshi 2 891, Manifold 819, Manifold comments 400, Wikipedia 365), so a rebuild opens almost no socket.
Staging is 22 MB. Ruling R106 keeps both outside the dataset hash, which walks `markets/` and `news/`
only; `kalshi_series.txt`, the 731-ticker allow-list this gate measured, sits beside them and is also
outside the hash.

### 4.2 What the build half produced

```
sealed     true
freeze     2026-09-07   interval 1440 min
window     2025-09-07 .. 2026-09-06
markets    77    yes 28   no 49
provider   manifold=77          (kalshi=0, see 5.2)
category   crypto=9 economics=1 entertainment=1 health=1 other=40 politics=7
           science=1 sports=6 tech=7 weather=1 world=3
hardness   illiquid=39  upset=8  whipsaw=3   (trivial=0)
removed    binary=0 density=25 kalshi_shards=0 min_life=12 min_trades=644
           no_leak=0 opened_early=42 resolution=0 self_resolved=0 window=0
split      train 0   validation 0   sealed 77
news       8544 items, 478 linked (wikipedia_current_events 7391, manifold_comment 1153)
           95 further items dropped (source not selected, or older than every market)
files      462       (77 market files + 385 news day files)
hash       9e153b8e22956bf2116dbb2b77040903a42fb3cfbef2c71f941325823645d712
notes      illiquid decile boundary: manifold=0 milli
```

Counted directly off the written files:

| Quantity | Value |
|---|---|
| market files | 77 |
| bars | 2 850 |
| trades | 12 961 |
| market life in days (min / median / max) | 7 / 29 / 408 |
| `resolved_at` span of the 77 markets | 2026-08-24 to 2026-09-05 |
| news day files | 385, covering 2025-06-20 to 2026-09-07 |
| news items on disk | 8 544 |

`pmx data verify --dataset data/datasets/y2026` prints
`verified data\datasets\y2026 9e153b8e...` and exits `0`.

`built_by`: `pmx_version 2.0.0-dev`, `contract_version 2.0`, `rng_algorithm_version 1.0.0`.

The 644 markets removed by `min_trades` are 400 Kalshi (all of them, see 5.2) and 244 Manifold. Section
7.6's `illiquid` boundary is reported as `manifold=0 milli`, which is what a slice whose bottom decile
has no volume at all reads as; the Kalshi slice is absent from the map because it is empty.

### 4.3 Against AC-1

AC-1 asks for "at least 300 markets per provider (or documents why fewer)". This dataset has **77
Manifold markets and 0 Kalshi markets**, so both halves fall short and this section is the required
documentation. The three reasons, in order of size, are 5.2 (the whole Kalshi provider), 5.3 (the
per-provider cap collapses the window) and the `min_trades` filter on Manifold. The rest of AC-1 holds:
the dataset is sealed, carries bars, trades, news with as-of stamps (`visible_from_ms = published_at_ms
+ 21 600 000`), hardness tags and a manifest hash; `verify` passes; a one-byte change fails it (proved on
the fixture dataset in section 3, on a copy).

---

## 5. What the real build exposed

### 5.1 Fixed in this gate (owner D2, `src/pmx/data/importers/kalshi.py`)

**A. The provider renamed every money and size field of a listing row.** `api.elections.kalshi.com`
answers `volume_fp`, `open_interest_fp`, `last_price_dollars`, `yes_bid_dollars`, `yes_ask_dollars` and
`settlement_value_dollars`; the keys the importer read (`volume`, `open_interest`, `last_price`,
`yes_bid`, `yes_ask`, `settlement_value`) are absent from the answer. Measured over the 227 381 settled
rows in the build cache: not one carries an old spelling. The effect was silent, which is worse than a
crash: every Kalshi row parsed with `volume_milli = 0`, no quote and no last price.

**B. The candlestick tape answers counts as decimal strings.** `volume` and `open_interest` come back as
`"0.00"`, `"12.50"`, `"967.75"`. Read through the integer helper they raised
`MalformedResponseError: expected an integer got='0.00'` and the whole Kalshi import died on its first
market. This is where the previous session stopped.

**C. `resolved_at` was taken from the scheduled expiration, not the settlement.** The row's
`_SETTLED_KEYS` list had no `settlement_ts`, so the first key present was `expiration_time`, which is the
*latest* expiration the contract allows. Measured over the same 227 381 rows: every row carries
`settlement_ts`, none carries any of the four older spellings, and `expiration_time` differs from
`settlement_ts` on **every single row**, typically by a week (`KXH100W-26SEP04-2.93` settled at
`2026-09-04T21:35:35Z` and expires at `2026-09-11T21:00:00Z`). A market's `resolved_at` fixes its last
bar, the window filter and the fold it lands in, so this was a systematic error in all three.

The fix reads both shapes everywhere (`_count_milli`, `_count_of`, `_either`) and puts `settlement_ts`
ahead of `expiration_time`. Five tests were added to `tests/test_import_kalshi.py`, driven through
`import_kalshi` against a transport that answers the shape the provider serves today:

```
test_a_candlestick_volume_that_arrives_as_a_decimal_string_is_a_contract_count
test_a_print_count_that_arrives_as_a_decimal_string_is_still_a_size
test_the_listing_row_reads_the_renamed_decimal_fields
test_the_settlement_instant_beats_the_scheduled_expiration
test_a_settlement_value_in_dollars_resolves_the_market
```

The recorded fixtures of `tests/fixtures/d2/` still carry the older integer shape and still parse: both
spellings are read, neither is dropped.

### 5.2 Not a code defect: Kalshi publishes no settled print tape

`GET /trade-api/v2/markets/trades?ticker=<ticker>` answers `{"cursor":"","trades":[]}` for every settled
market, however much it traded. Probed on 2026-09-07:

| Probe | Answer |
|---|---|
| `?ticker=KXRAINNYC-26JAN04-T0` (volume 5 376 236 contracts, settled 2026-01-05) | 0 trades |
| the same with `min_ts=0`, or with `min_ts`/`max_ts` spanning its life | 0 trades |
| `?limit=100` with no ticker (the exchange-wide tape) | 100 trades, all from the last 25 seconds |
| five pages of 1 000 of that tape | 5 000 trades spanning 36 seconds |
| `?ticker=<a ticker taken from that live tape>` | 100 trades, the last two minutes |
| `/markets/<ticker>/trades`, `/series/<series>/markets/<ticker>/trades`, `/historical/markets/<ticker>/trades` | HTTP 404 |

The ticker filter works; the retention does not. The public tape holds only what is trading now, so a
market that settled inside a twelve-month window has no reachable print tape. Consequence for the
contract's quality filter of 7.4 (`n_trades >= 50` **or** `unique_bettors >= 30`): Kalshi publishes no
trader count, `quality.n_trades` is `0` for every settled Kalshi market, and `min_trades` therefore
removes the **whole provider**, exactly as the creator-resolved filter does to Manifold (ruling R101).
A Kalshi-only build reports `removed ... min_trades=400` and every other filter at `0`.

This is a contract decision and not a code fix, so it was not taken here. It is the same shape as ruling
R105 but with an important difference: **the Kalshi candlestick tape does carry per-bar size**
(`volume` and `open_interest` per period), so a Kalshi market has a real, size-carrying tape at bar
resolution and can fill under section 8.6. What it cannot do is satisfy a filter written in prints.
The decision the contract owner has to take is whether `min_trades` accepts a bar-level proxy
(`quality.traded_bars`, or a `volume_milli_total` floor) for a provider that publishes no print tape, or
whether Kalshi joins Polymarket outside the built dataset.

### 5.3 The per-provider cap makes each provider a different slice of the window

With `--limit-per-provider 400` the two importers truncate the window from opposite ends, because each
one caps after building 400 markets and they walk in opposite orders:

- `import_kalshi` walks `_settled_rows` sorted **ascending** by `resolved_at`, so the 400 Kalshi markets
  all settled between 2025-09-07 and 2025-09-09: the first two days of a twelve-month window.
- the Manifold import returns the most recent resolutions, so its 400 markets all settled after
  2026-07-08 and the 77 that survive the filters settled between 2026-08-24 and 2026-09-05: thirteen
  days. Every one of them lands in the sealed test fold (`train 0, validation 0`), which section 12.7
  forbids the optimizer to read.

The cap is what this gate was asked to build with, so it was kept and is reported rather than tuned. A
dataset meant for AC-3 and the fold rules of 7.7 needs a cap applied *after* a window-spanning walk, or
no cap at all.

### 5.4 The linker's dominant term is dead on a real dataset

Section 7.6 weights shared wiki links at 600 permille and keyword overlap at 400, and `shared_links`
compares an item's `wiki_links` against the market's `wiki_subjects`. On the real data:

- `import_kalshi` and `import_polymarket` set `wiki_subjects=()` unconditionally;
- of the 400 staged Manifold markets, 392 have no `wiki_subject` and 8 have one.

So the 600-permille term is zero for effectively every real market, the score can never exceed 400, and a
link needs a keyword overlap of at least 375 permille to clear `LINK_THRESHOLD_PERMILLE = 150`. The
7 391 Wikipedia Current events items in this dataset link to no market at all: all 478 links the
manifest counts come from the 1 153 Manifold comments, which carry their market in `match_ids` by
construction and never go through the linker. The news is still carried
(the engine reads `Dataset.news_global`), but per-market news is empty, which is the input `newsbayes`
(A1) and the LLM forecaster (A5) were designed around. The same gap disables `wikipedia_asof`, whose
snapshots are keyed on `market.wiki_subjects`.

### 5.5 Kalshi listing rows no longer carry a category

Not one of the 227 381 settled rows in the build cache has a `category` field, so `_category_of` returns
the fallback and **every** Kalshi market lands in `other`. The staged 400 confirm it: `category
{'other': 400}`. The information is not entirely lost, because `_tags_of` keeps the lowercased series
ticker as a tag, but the per-category breakdown that the leaderboard (E5), the `specialist` family (A1)
and the category priors of memory (A2) read is flat for the whole provider. Mapping a series ticker to
one of the twelve categories of section 2 is a data decision for D2's `KALSHI_CATEGORIES` table and was
not taken here.

---

## 6. What is open

**Immediately next: wave 2, packages E1 to E5, five agents in parallel after this gate.**

| Package | Owns | Done when |
|---|---|---|
| E1 calendar and observation builder (the leak boundary) | `src/pmx/engine/calendar.py`, `src/pmx/engine/observation.py`, `tests/test_observation.py` | the poisoned-future and clock tests pass and an observation serialises under the contract's size cap |
| E2 execution, fees, accounting | `src/pmx/engine/execution.py`, `src/pmx/engine/fees.py`, `tests/test_execution.py` | the accounting invariant holds on 1 000 generated fill sequences and a zero-volume bar fills nothing |
| E3 scoring | `src/pmx/scoring.py`, `src/pmx/metrics/calibration.py`, `tests/test_scoring.py` | the Brier identities hold and calibration imports nothing from execution |
| E4 statistics | `src/pmx/metrics/stats.py`, `tests/test_stats.py` | a synthetic agent with known skill gets an interval containing it, the shuffled null centres on zero, deflation widens with the candidate count |
| E5 runner, projection, run store | `src/pmx/engine/runner.py`, `src/pmx/metrics/projection.py`, `performance.py`, `behavioral.py`, `leaderboard.py`, `src/pmx/store.py`, `src/pmx/cli_run.py`, `tests/test_runner.py` | a run on the demo pack journals, replays to an identical hash, and `market_follower` reproduces the market's Brier exactly |

Gate G2 then runs the full scripted-stub run on the dataset from this gate, checks AC-3 and AC-4 and
50-seed determinism, and appends its own section here.

Carried into G2 as decisions, not as work:

1. The `min_trades` filter versus a provider with no public print tape (5.2). Until it is settled, a real
   dataset is Manifold only, and every market in it lands in the sealed test fold (5.3), which is the
   one fold section 12.7 forbids the optimizer to read. **AC-3 has nothing to train on until either
   decision changes.**
2. The per-provider cap and the walk order (5.3).
3. `wiki_subjects` on Kalshi markets, without which the linker and `wikipedia_asof` cannot work (5.4).
4. A series-ticker to category mapping for Kalshi, without which every Kalshi market is `other` (5.5).

Later waves are untouched: wave 3 (A1 to A6), wave 4 (O1 to O4), wave 5 (U1 to U4), wave 6 (L1, L2).
---

## 7. The Kalshi data finish, 2026-09-08 (`data/datasets/y2026`, hash `83fbf211...`)

Rulings R167 to R170 were implemented on the morning of 2026-09-08 and the dataset was rebuilt at 08:59.
That rebuild produced 67 Manifold markets in three populated folds and **still 0 Kalshi markets**, with
`counts.n_bars_only` absent from the manifest. This section is the diagnosis of that zero, the fix, the
rebuild that followed and its real numbers.

### 7.1 Why the 08:59 rebuild had no Kalshi market

The bars-only branch of `min_trades` (R167) was implemented and reached: of the 400 staged Kalshi markets
305 carried `quality.tape_kind == "bars_only"` (the other 95 had prints, so the field stayed at its
default and is not written) and every one carried a positive `quality.volume_milli_total`. What the branch
reads was structurally zero:

| Measured on `staging/markets/kalshi.jsonl` of the 08:59 build | Value |
|---|---|
| staged Kalshi markets | 400 |
| markets with `quality.traded_bars >= min_traded_bars` (20) | 0 |
| markets with `quality.traded_bars > 0` | 0 |
| bars written over the 400 markets | 3 399 |
| bars carrying `volume_milli > 0` | 0 |
| markets whose whole bar path is one repeated close | 400 |
| median bars per market | 3 |
| markets with `life_days == 1` | 252 |

So `min_trades` removed the whole provider again (`removed min_trades=643`, of which 400 Kalshi and 243
Manifold), and `counts.n_bars_only` was absent because it was `0`: a zero is omitted from the manifest on
purpose (`DatasetCounts.to_dict`, guarded by `test_a_build_with_no_bars_only_market_says_nothing_about_it`)
so that adding the field moved no existing manifest's bytes. The absence was a symptom, not a second
defect.

**The cause was the bar grid, not the filter.** `_candle_of` keyed a candlestick period by
`end_period_ts - interval`. Kalshi's daily periods end at midnight New York, not at midnight UTC: over 200
candlestick answers sampled from the build cache, 553 sampled periods end at 04:00 UTC (EDT) and 102 at
05:00 UTC (EST), none at 00:00 UTC. `end - 1 day` is therefore never a multiple of a day and never a bar
of the grid of section 5.2, so `_bars` looked up each bar of the market's UTC grid, found no candle for any
of them, and wrote every bar as the carry-forward bar of 5.2: `open == high == low == close == vwap`,
`volume_milli = 0`, `n_trades = 0`. Every Kalshi market came out with a flat price path and
`traded_bars = 0`, whatever it had traded. The misalignment hid two smaller defects behind it: the last
period of a market ends after its last bar, so a range that stopped one interval past the last bar lost
the settling bar; and the live candlestick path (`/series/{series}/markets/{ticker}/candlesticks`, the only
path for a market settled after the historical cutoff) answers `volume_fp`, `open_interest_fp` and
`price.close_dollars`, none of which the historical spelling reads.

A second, independent cause capped what the fix could recover: the fetch budget bought tapes the filters
were certain to remove. 88 per cent of the settled rows the narrowed listing offers inside the window live
under a week, the budget took the head of each stride of the walk, and 252 of the 400 markets it bought
lived one day, which is three daily bars and cannot reach `min_traded_bars = 20` however well the candles
are keyed.

Two things the 08:59 build did **not** get wrong, checked before touching them: the walk already spanned
the window (staged settlements ran from 2025-09 to 2026-09, 12 to 56 per month, so R168's stratified cap
had every month to draw from), and the cap was not binding on either provider.

### 7.2 The fix, and the mutation that proves each part of it

The candle-grid, slack, live-field, walk-floor, life-floor and fetch-budget edits landed in
`src/pmx/data/importers/kalshi.py` during the interrupted lot 3c and were unverified (`docs/HANDOFF.md`).
They were checked here by reproducing one series from the HTTP cache and by mutating each part back to its
old behaviour:

| Mutation of `src/pmx/data/importers/kalshi.py` | Tests that fail |
|---|---|
| `t_ms=bar_of(end_ms - step_ms, ...)` back to `t_ms=end_ms - step_ms` | 3 (the Eastern grid, the settling bar, the live path) |
| `_fetch_budget` back to the head of each stride, and the `min_life_days` floor removed | 3 |
| the descending stop of `_list_rows` removed | 2 (both new, below) |
| `floor_ms` raised from `window_start_ms - KALSHI_SETTLEMENT_SLACK_MS` to `window_start_ms` | 1 (new) |

The descending walk floor of ruling R100 had **no** test: removing it left the suite green, while its real
effect is that the historical listing follows its cursor to `KALSHI_MARKETS_MAX_PAGES` and raises
`MalformedResponseError`, which loses the whole provider rather than one market. Two tests were added to
`tests/test_import_kalshi.py`, driven through `import_kalshi` against a listing that never runs out of
pages:

```
test_the_settled_walk_stops_at_the_window_floor_instead_of_reaching_the_page_cap
test_a_page_inside_the_settlement_slack_does_not_end_the_walk
```

The second one pins the floor to the window start **minus** the settlement slack, because a Kalshi market
can close before it settles and a page closing inside that band still holds markets that settled in the
window.

The reproduction, before the rebuild: `pmx data import kalshi --kalshi-series KXCPIYOY --limit 12
--min-life-days 7` against `data/datasets/y2026/cache/` staged 12 markets with `traded_bars` from 21 to 74
(median 37), `tape_kind` `bars_only` on 9 of them and `prints` on 3; an offline build of that staging kept
all 12 (`removed` all zero, `bars_only 9`).

### 7.3 The rebuild

```
PMX_USER_AGENT_CONTACT=etienne.millerioux@studi.fr
.venv\Scripts\python.exe -m pmx.cli_data build ^
  --provider kalshi,manifold --freeze 2026-09-07 --window-days 365 --interval-min 1440 ^
  --keep-self-resolved --kalshi-series <the 731 tickers of data/datasets/y2026/kalshi_series.txt> ^
  --limit-per-provider 400 --min-interval-ms 350 ^
  --out data/datasets/y2026 --name y2026 --force --seal --notes "..."
```

The cache of the earlier builds covers the listing walk of all 731 series, so the fetch half finished in
about a minute and the whole build in four; the cache now holds 7 485 entries. `pmx data verify --dataset
data/datasets/y2026` prints `verified data\datasets\y2026 83fbf21166899712...` and exits `0`.

The build ran twice (the first run's log was overwritten when the second reused the log path). Both runs
produced the same 287 markets with identical per-provider, per-category, per-fold, per-month and
per-filter counts; only the `dataset_hash` differs (`da1ca326...` then `83fbf211...`), because every
`NewsItem` carries the `fetched_at_ms` of the run that fetched it while the HTTP cache stores a response
body without its read time. **A rebuild is therefore reproducible in its markets and not in its hash**,
which matters to any claim keyed on `dataset_hash`. It is recorded here as an open item, not fixed.

### 7.4 What the rebuild produced

```
sealed     true
freeze     2026-09-07   interval 1440 min
window     2025-09-07 .. 2026-09-06
markets    287   yes 115   no 172
provider   kalshi=220   manifold=67
category   crypto=38 economics=57 entertainment=2 finance=59 other=20 politics=40
           science=1 sports=5 tech=27 weather=30 world=8
hardness   illiquid=53  trivial=12  upset=58  whipsaw=39
tape       bars_only 99   category fallback 19
removed    binary=0 density=26 kalshi_shards=0 min_life=24 min_trades=459 no_leak=0
           opened_early=1 resolution=0 self_resolved=0 window=0
split      train 111   validation 46   sealed 130
news       9049 items, 1805 linked (wikipedia_current_events 7391, manifold_comment 1658)
files      682        (287 market files + 395 news day files, 24.7 MB)
hash       83fbf21166899712e86ed7ac1cab13cfa9a9ce25201a9de6844ad4703209f554
notes      illiquid decile boundary: kalshi=0 milli, manifold=0 milli
```

Per provider, counted off the written files and off the staged payloads:

| Quantity | kalshi | manifold |
|---|---|---|
| markets kept | 220 | 67 |
| of which `tape_kind == "bars_only"` | 99 | 0 |
| of which `tape_kind == "prints"` | 121 | 67 |
| markets with at least one `wiki_subject` | 220 | 60 |
| train / validation / sealed | 69 / 32 / 119 | 42 / 14 / 11 |
| kept per window month (the 12 buckets of 7.7) | 3 4 6 6 8 10 13 19 19 13 56 63 | 2 8 1 3 3 8 10 7 10 4 6 5 |
| staged before the filters | 400 | 397 |
| removed by `min_trades` | 170 | 289 |
| removed by `density` | 9 | 17 |
| removed by `min_life` | 0 | 24 |
| removed by `opened_early` | 1 | 0 |
| `traded_bars` min / median / max | 1 / 13 / 231 | not read (prints) |
| markets with `traded_bars >= 20` | 156 | not read |

`counts.precap_per_provider_month` equals the kept counts above for both providers: 220 and 67 are under
the cap of 400, so R168's stratified sampling had nothing to draw down and every one of the twelve months
is populated on both sides. The 220 Kalshi markets pass `min_trades` through two of its three branches:
156 on the bars-only branch of R167 (`traded_bars >= 20`) and 121 on prints, because the print tape does
answer for a market that settled recently enough (the retention probe of 5.2 holds for a market settled
months ago, not for every settled market). 99 markets carry no print at all and are in the dataset only
because of R167.

Other quantities off the files:

| Quantity | Value |
|---|---|
| bars | 9 643 |
| trades | 183 789 |
| market life in days (min / median / max) | 7 / 29 / 203 |
| `resolved_at` span of the 287 markets | 2025-09-11 to 2026-09-04 |
| news day files | 395, covering 2025-06-12 to 2026-09-07 |
| news items on disk | 9 049 (7 391 Wikipedia Current events, 1 658 Manifold comments) |
| linked news items | 1 805: **792 Wikipedia items** and 1 013 comments |
| links counted per market side | kalshi 4 461, manifold 2 025 |

The Wikipedia number is the one R169 was taken for: the same archive linked to **no** market at all in
every build before this one (5.4). It links now because the renormalised weights let a market with no
`wiki_subjects` score on keyword overlap alone, and because every provider now derives subjects: 220 of
220 Kalshi markets and 60 of 67 Manifold markets carry at least one.

`counts.n_category_fallback = 19` is composed of the 19 Manifold markets the provider itself categorises as
`other`. Every one of the 220 Kalshi markets has a category from the sealed series map of R170, and the
single Kalshi `other` comes from an explicit `other` entry in that map rather than from a fallback. The
count therefore measures "landed on `other` with nothing better named" across providers rather than
Kalshi's fallback alone, which is what `DatasetCounts.n_category_fallback` documents.

### 7.5 Against AC-1, and what is still open

AC-1 asks for at least 300 markets per provider or a document saying why fewer. This dataset has 220
Kalshi and 67 Manifold, so both halves still fall short, but the reasons are now single filters rather
than a dead provider:

* Kalshi: 170 of the 400 staged markets are removed by `min_trades` (a bars-only tape with fewer than 20
  traded bars) and 9 by `density`. A larger budget is the only way to more Kalshi markets: the narrowed
  listing offers about 15 000 in-window rows that live a week or more, and 400 buys 2.6 per cent of them;
* Manifold: 289 of 397 are removed by `min_trades` (`n_trades < 50` and `unique_bettors < 30`) and 24 by
  `min_life`.

The rest of AC-1 holds: the dataset is sealed, carries bars, trades, news with as-of stamps, hardness tags
and a manifest hash, and `verify` passes.

What the four carried decisions of section 6 now read as:

1. `min_trades` versus a provider with no print tape: **settled by R167 and closed.** Both folds the
   optimizer may read are populated on both providers (train 111, validation 46), so AC-3 has something to
   train on.
2. The per-provider cap and the walk order: **settled by R168**, and not binding at 400.
3. `wiki_subjects` and the linker: **settled by R169**, measured above.
4. The Kalshi series-to-category map: **settled by R170**; one Kalshi market in 220 is `other`.

Newly open, from this section: the `dataset_hash` moves between two rebuilds of the same data because
`NewsItem.fetched_at_ms` is a wall clock (7.3). Either that field leaves the hashed files, or a claim names
the build rather than the hash.

Checked after the rebuild: `pytest` 662 passed, 4 skipped (the legal `PMX_LIVE` skips); `ruff check src
tests` clean; `mypy --strict` clean over the 49 source files of `src/pmx`.


## 8. Gate G2, 2026-09-09: the engine wave closed (`docs/CONTRACTS_V2.md` 15.3, rulings R200 to R229)

The five engine packages (E1 observation, E2 execution, E3 scoring, E4 statistics, E5 runner) were built
in parallel against sections 16 and 17 and never saw each other's code. Lot 4c reconciled them (1 023
tests green at commit `8c38cb8d`), lot 4c2 finished the redesign at the root (commit `7493d688`, 7
mutation checks), and this gate ruled on what they raised, applied what 17.9 deferred, and measured AC-3
and AC-4 on the real dataset. Everything below was measured on the tree at the end of the gate, not taken
from a report.

### 8.1 What the engine wave built

| File | Owner | Lines | Tests (file, count) |
|---|---|---|---|
| `src/pmx/engine/calendar.py` | E1 | 726 | `tests/test_observation.py`, 90 (shared with observation) |
| `src/pmx/engine/observation.py` | E1 | 1 360 | idem |
| `src/pmx/engine/execution.py` | E2 | 1 641 | `tests/test_execution.py`, 84 |
| `src/pmx/engine/liquidity.py` | E2 | 849 | idem |
| `src/pmx/engine/fees.py` | E2 | 496 | idem |
| `src/pmx/scoring.py` | E3 | 767 | `tests/test_scoring.py`, 63 |
| `src/pmx/metrics/calibration.py` | E3 | 282 | idem |
| `src/pmx/metrics/stats.py` | E4 | 703 | `tests/test_stats.py`, 44 |
| `src/pmx/engine/runner.py` | E5 | 1 927 | `tests/test_runner.py`, 40 |
| `src/pmx/metrics/projection.py` | E5 | 1 295 | idem |
| `src/pmx/metrics/leaderboard.py` | E5 | 312 | idem |
| `src/pmx/metrics/performance.py`, `behavioral.py` | E5 | 198, 142 | idem |
| `src/pmx/store.py` | E5 | 398 | idem |
| `src/pmx/cli_run.py` | E5 | 282 | idem (`pmx run backtest`, `pmx run replay`) |
| `tests/stub_roster.py` | E5 (created by the gate, R200) | 191 | not a test file: the scripted-stub roster |
| `tests/stub_roster_rng.py` | E5 (created by the gate's audit pass, R229) | 118 | idem, plus the seed-consuming `coin_flipper` |

Landed by the gates' passes in wave-1 files and measured here: `src/pmx/types.py` 3 030 lines (every
name of 17.9's first row, `BINARY_TICK_SIZE_MICRO == 100`, seven `CASH_EVENT_KINDS` with `carry`,
`RunConfig.horizons_bars` resolved in `__post_init__`, the five view caps of R208), `src/pmx/journal.py`
1 984 lines (32 event types, `oneOf` equal to `EVENT_TYPES`, `Journal.take_tail`), `src/pmx/data/sessions.py`
333 lines (rule 11's one implementation), `src/pmx/data/loader.py` 1 015 lines (the `instruments/` and
`calendars/` walk). `tests/test_types_loader.py` 77 tests, `tests/test_rng_journal.py` 65,
`tests/test_contract_schemas.py` 85, `tests/test_architecture.py` 14.

### 8.2 The four checks, verbatim

```
$ .venv/Scripts/python.exe -m pytest -p no:warnings -rs
...................                                                      [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests\test_import_kalshi.py:1264: live network probe; set PMX_LIVE=1 to run it
SKIPPED [1] tests\test_import_manifold.py:1124: set PMX_LIVE=1 to hit api.manifold.markets
SKIPPED [1] tests\test_import_polymarket.py:795: live network test; set PMX_LIVE=1 to run
SKIPPED [1] tests\test_news.py:1222: PMX_LIVE is not set
1023 passed, 4 skipped in 435.71s (0:07:15)
EXIT 0

$ .venv/Scripts/python.exe -m ruff check src tests
All checks passed!
RUFF_EXIT=0

$ .venv/Scripts/python.exe -m mypy --strict
Success: no issues found in 65 source files
MYPY_EXIT=0

em-dash sweep (U+2014, every file under src, tests, docs)
files scanned: 208
em-dash hits: 0
```

The four skips are the legal `PMX_LIVE` network probes. State at the start of the gate, for the record:
1 023 passed, ruff clean, mypy clean (lot 4c2's tree).

### 8.3 AC-3: the scripted-stub population on `data/datasets/y2026`

AC-3 asks for a run of the full scripted population that journals, replays with an identical hash and
satisfies the accounting invariant on every agent for 50 seeds. The scripted families are wave 3's and do
not exist, so the population is the **scripted-stub roster** of `tests/stub_roster.py` (ruling R200):
`contrarian` (`legacy(name=0)`, the mirror of the market price, sized by 10.5's default rule),
`limiter` (one resting limit order per open market per bar at 1 bp, `ttl_bars = 1`) and
`market_follower` (`follower(1000, 0)`, never an order). Three agents, of which two trade. Driven through
the real CLI, every seed twice into two directories, then replayed:

```
.venv/Scripts/python.exe -m pmx.cli_run backtest --dataset data/datasets/y2026 --seed <s> \
    --runs-dir <dir a|b> --roster-module tests.stub_roster --no-index --json
.venv/Scripts/python.exe -m pmx.cli_run replay <run_id> --runs-dir <dir a>
```

Dataset `y2026`, hash `83fbf21166899712...`, 287 markets (220 Kalshi, 67 Manifold), 1 440-minute bars,
window 2025-09-07 to 2026-09-06. Seeds `0..49`, eight in parallel.

| Measured | Value |
|---|---|
| seeds run | 50 of 50 |
| seeds whose two runs give the same `journal_hash` and `run_id` | 50 |
| seeds whose `pmx run replay` rebuilt `results.json` byte for byte (exit 0) | 50 |
| seeds whose accounting invariant holds for every agent, from the journal alone | 50 |
| distinct journal hashes over the seeds | 50 (one per seed, and by the `run_started` line alone: see below) |
| bars per run | 452 |
| events per run | 94803 |
| wall clock per backtest, eight in parallel | 148.5 to 465.7 s (the 60 freshly run backtests) |
| seed 0 | `r-83fbf211-0-5f754f05`, journal `9d93901cf44dd2a8...` |
| seed 49 | `r-83fbf211-49-991bb77b`, journal `44ef8c992fd038dd...` |

**What the seed changes over this roster: one line.** None of the three stubs draws from the `RngTree`
substream `reset` hands it (`tests/stub_roster.py`: `reset` counts the call and discards the `Random`),
and `pmx/engine/execution.py` and `pmx/engine/liquidity.py` draw nothing either, so the historical
liquidity model and all three agents are seed-free. Masking the run id, the seed 0 and seed 1 journals
differ in exactly 1 of their 94 803 lines, the `run_started` line that carries the seed and the
`config_hash` it enters; every one of the 50 seeds has the same 94 803 events. The 50 rows above are
therefore 50 reproductions of one run plus a config echo: they measure that the same inputs give the
same bytes on 50 config hashes, which is the half of AC-3 the stub roster can measure. The other half,
the engine under a *varying* RNG, is the measurement below.

The invariant is recomputed per agent per seed from `journal.jsonl` and nothing else: `cash_cents ==
bankroll + sum(filled.cash_delta) - sum(fee_charged.fee) + sum(settlement_applied.cash_delta) +
sum(cash_event_applied.cash_delta)` at the last `equity_marked`, `reserved_cents == 0`,
`positions_value_cents == 0` and `equity == cash + positions_value`, in integers. Every seed passes all
four checks. The driver
and its per-seed JSON are in the scratchpad (`g2d/ac3_driver.py`, `g2d/ac3/summary.json`); one seed 0
run reports `contrarian` brier 551 889, skill -319 414, pnl 40 686 cents, 284 of 287 markets traded;
`limiter` 1 market traded, pnl -1; `market_follower` skill 0, pnl 0.

How the 100 runs were taken, exactly: an earlier attempt of the driver on this same tree was killed, and
the driver reuses a run directory that already carries `results.json` and `manifest.json`, so 40 of the
100 backtests (24 of the 50 in `a`, 16 of the 50 in `b`) are that attempt's, reported with `seconds: 0.0`,
and 60 were run fresh. The hashes agreed across the two attempts on every seed, which is why the
determinism row reads 50 of 50: it compares runs taken before and after the gate's own edits to the tree.
The wall-clock row covers the 60 fresh backtests only.

**The seed-consuming roster** (added by the gate's audit pass, lot 4e). `tests/stub_roster_rng.py` is the
same three stubs plus `coin_flipper`, which draws one belief per open market per bar from the substream
`reset` hands it and sizes it by 10.5's default rule, so the seed reaches the events and not only the
header. The same protocol, same dataset, same CLI, `--roster-module tests.stub_roster_rng`, seeds `0..5`,
six in parallel:

| Measured | Value |
|---|---|
| seeds run, each twice into two directories | 6 of 6 |
| seeds whose two runs give the same `journal_hash` and `run_id` | 6 |
| seeds whose `pmx run replay` rebuilt `results.json` byte for byte (exit 0) | 6 |
| seeds whose accounting invariant holds for all four agents, from the journal alone | 6 |
| distinct journal hashes | 6 |
| events per run, by seed | 113 489, 111 860, 116 024, 110 183, 115 016, 113 126 |
| positive fills, by seed | 3 118, 3 017, 3 273, 2 803, 3 235, 3 170 |
| bars per run | 452 (unchanged: the calendar does not depend on the roster) |
| wall clock per backtest, six in parallel | 427.5 to 476.4 s |
| `contrarian` final cash, seed 0 and seed 1 | 141 949 and 142 087 cents (the fourth agent moves the book the others trade) |

The event count, the fill count and the other agents' cash all move with the seed, so this run exercises
the `RngTree` and the invariant is checked on six different books rather than on one book six times.
`tests/test_runner.py::test_a_seed_consuming_agent_makes_the_seed_change_the_journal_it_reproduces`
keeps the claim in the suite (two seeds, each run twice: same hash within a seed, different forecasts and
different fills across seeds; mutation-checked, a `coin_flipper` that ignores the substream fails it).
Driver and per-seed JSON: `<scratchpad>/lot4e/ac3_rng_driver.py`, `<scratchpad>/lot4e/ac3rng/summary.json`.

**Verdict: partial** (the gate first graded this `pass` with the limits below; its audit pass regraded it,
because AC-4's analogous gap is graded `partial` and the acceptance audit over AC-1..AC-34 reads these
verdicts at face value). What is measured is measured: determinism, replay and the invariant hold on 50
seeds of the three-stub roster and on 6 seeds of the seed-consuming roster, over the real dataset, through
the real CLI. What AC-3 asks for and this is not: (1) The population is three stubs (four with
`coin_flipper`), not the eleven scripted families of 10.5: AC-3's "full scripted population" is
measurable only after A1 lands, and the same command (`--roster-module pmx.agents.registry`, the
default) is what will measure it, at which point AC-3 is regraded. (2) Two of the three stubs trade;
`market_follower` never does, by design. (3) The three stubs are binary-only; the
continuous path of the runner is exercised by `tests/test_runner.py` on a synthetic perp and a session
instrument, not by this dataset, which carries binaries only. (4) The runs were taken on the engine as it
stands at this gate; rulings R213, R214, R217 and R221 declare shapes that will move the journal or
`results.json` of every future run when the next lot applies them (section 8.6 below), so these hashes
are evidence for this tree and not pins.

### 8.4 AC-4: the four leak families

AC-4 asks for the poisoned-future, clock, seal and shuffled-outcome tests to pass and to be part of
`pmx audit leaks`. The families, by test id (ruling R225), run by name:

```
$ .venv/Scripts/python.exe -m pytest -o addopts= -p no:warnings -v <the twelve ids of ruling R225>
tests/test_observation.py::test_the_clock_test PASSED                    [  8%]
tests/test_observation.py::test_the_poisoned_future_test PASSED          [ 16%]
tests/test_observation.py::test_the_poisoned_future_test_on_a_continuous_instrument PASSED [ 25%]
tests/test_observation.py::test_one_of_each_cluster_and_detector_record_is_refused PASSED [ 33%]
tests/test_builder.py::test_the_built_dataset_loads_seals_verifies_and_fails_on_a_changed_byte PASSED [ 41%]
tests/test_types_loader.py::test_seal_stamps_an_imported_dataset_and_rehashes_it PASSED [ 50%]
tests/test_stats.py::test_permutation_null_of_the_market_follower_is_exactly_zero PASSED [ 58%]
tests/test_stats.py::test_permutation_null_of_a_coin_flip_agent_centres_on_zero PASSED [ 66%]
tests/test_stats.py::test_permutation_null_of_a_skilled_agent_is_unmatched_and_negative PASSED [ 75%]
tests/test_stats.py::test_continuous_null_of_the_random_walk_is_exactly_zero PASSED [ 83%]
tests/test_stats.py::test_continuous_null_of_a_coin_flip_agent_centres_on_zero PASSED [ 91%]
tests/test_stats.py::test_continuous_null_of_a_directional_agent_is_unmatched_and_negative PASSED [100%]
============================= 12 passed in 3.67s ==============================
EXIT 0
```

Read, not only run: the binary poisoned-future test injects a future bar (close `7777`, volume
`987654321`), a future news item, a memory record and a hive lesson stamped after `now_ms`, another
agent's open forecast and the resolution of a market settling at this very bar, and asserts by content
match on the rendered JSON that none surfaces while a visible headline does; the continuous one injects a
`delisted_at_ms`, a `last_bar` and an unapplied dividend and asserts the applied one is shown. The clock
test is 8.3's key-set scan over `leak_scan_payload` plus the two bar-count identities and the as-of price.
The seal test changes one byte of a market file and asserts `verify_dataset_report` names that file. The
shuffled-outcome family is E4's permutation null: the market follower's null is exactly zero, a coin flip
centres on zero, a skilled agent's is unmatched and negative, and the same three on the continuous null.

**Verdict: partial.** All twelve pass. `pmx audit leaks` does not exist: section 13 gives `cli_audit.py`
to A6 (wave 3) and the `pmx` dispatch to U4, so the gate did not create the command in a file two later
packages own; ruling R225 names the twelve ids A6 mounts and the amnesic test it adds. And the
shuffled-outcome family proves the null, not PRD 6.3's population statement ("no scripted agent's skill
lower bound exceeds zero on the training set over 200 seeds"), which needs the scripted families and
O4's claim path.

### 8.5 The rulings

30 rulings, R200 to R229, in 15.3. They settle the 56 merged contract issues, the 30 cross-package
mismatches and the 23 items the reconciliation and redesign agents left. R228 was added by the audit
pass of this gate (lot 4e): merged issue I09 (`last_bar(i)` against R186's collapse of `delisted_at_ms`
into `MarketMeta.resolved_at_ms`) was settled by no ruling while 15.3 and this section claimed all 56
were settled, and `engine/calendar.py` cited "a gate G2 ruling" a reader could not find. The ruling
states what the code already did (the field is read off `Dataset.market(id).instrument`) and amends 7.2
and 17.2 in place; no behaviour moved. R229, from the same pass, records the seed-consuming roster the
AC-3 measurement gained and the regrade of AC-3 to `partial` (8.3). Seven resolved **against** the
proposed resolution: R202 (the fixture is completed, not regenerated, because regeneration would have made
E5's two reproduction tests compare a run to itself), R205 (the protocols stay structural stand-ins in the
engine rather than moving `Agent`, `Memory`, `Hive` into `pmx.types`), R207 (two error families for two
conditions rather than one), R215 (the maker fee is handled by truncating the partial fill, not by
reserving it), R219 (deflation at `ALPHA_PPM` only rather than an `alpha_ppm` field on `Interval`), R224
(both metrics files read `RANDOM_WALK_BRIER_MICRO` from `pmx.types`, the owner, not through
`pmx.scoring`), R225 (`pmx audit leaks` is A6's, not U4's). `ENGINE_VERSION` stays `2.0.0` and
`CONTRACT_VERSION` `"2.0"` (R227): no run exists whose bytes a ruling could move.

Applied in code at this gate: the one `InstrumentLike`/`CashEventLike` declaration (`engine/calendar.py`),
the runner's `MemoryLike`/`HiveLike` extending the observation's, the five view caps in `pmx.types`,
`Journal.take_tail` replacing the runner's subclass, `make_agent` and `--roster-module` in `cli_run`,
`.scratch/` in `.gitignore`, the PRD v4 1.2 correction (R189) and the PLAN_V3 F4 row (R174), and every
stale "reported as a contract issue" comment in the engine files replaced by the ruling that settled it.

One artefact outside its owner, for the record (found by the gate's audit, lot 4e): lot 4c's reconciliation
regenerated `data/demo_v1/manifest.json`, D1's generated pack, to carry R188's `filters.config.kinds:
["binary"]` (commit `8c38cb8d`, one inserted key). The file equals a fresh `migrate_v1` output today,
which `tests/test_types_loader.py::test_the_committed_demo_pack_is_what_the_migration_produces_today`
asserts, and `dataset_hash` did not move because the filters sit outside the hash. Regenerating a pack
after a schema ruling is D1's or a gate's; the edit was neither recorded nor attributed at the time, and
this sentence is that record.

### 8.6 What 17.9 still owes, and what this gate declared without applying

17.9 rows applied and verified here: `pmx.types` (R201), `market.v2.json` and `dataset.v1.json` (R201),
the loader walk (R201, R223), `pmx.data.sessions` (R203), the PRD v4 correction (R201), the journal
classes and the fixture (R202), E2's liquidity and execution names (R204, R213, R214), E4's permutation
(R219). Rows that stay open with their gate: `news.v1.json`'s widening (gate G3b), `pyproject.toml`
package-data for `data/calendars/*.json` (gate G3b), `Hive.write_forecast`'s four arguments (gate G3, A3),
`open_sealed_test(..., kind=)` and the claim record (gate G4, O1 and O4), `opportunity.v1.json` (amendment
C2).

Declared by a ruling, not yet in code, each moving the journal or `results.json` of every future run and
assigned to the next engine lot (E2 or E5, before the first claim):

| Ruling | Shape | Why it is not applied here |
|---|---|---|
| R213 | `Execution.__init__(..., t0_ms, t1_ms)` and the last-bar drain of a queued item with no later bar as `order_rejected(not_tradable)` | adds events to every journal; today 5 of 1 627 demo-pack items are dropped and `test_every_queued_item_produces_exactly_one_execute_phase_event` pins `dropped > 0` |
| R214 | `quote_bar(..., bar_prev=)` | moves the fallback base of every fill on a quoteless Kalshi bar |
| R217 | `project()` builds continuous calibration entries through `continuous_entry` | a continuous row's `ece_ppm` is `0` today |
| R221 | `PerMarket.n_quantile_forecasts`, `RunProjection.seed` | `results.json` gains two keys; `seed_of_run_id` goes |

### 8.7 Open for the next lot

* Lot 5a, amendment C1c: section 18 (sensors, rules, minute grids, workflow genomes) and the normative
  text of both reviews (D-R1..D-R14, D-S1..D-S14); the `sensors` keyword of `build_observation`, the
  `Observation.sensors` record for replay, `SensorAbsentError`, and the placement of `cash_events` and the
  hive under a sensor are C1c's (the sensor-hook report lists them).
* The four rows of 8.6 above, with the fixture and the pinned hashes regenerated in the same change.
* `pmx audit leaks` (A6) and the `pmx` dispatch (U4).
* **`run_id` does not name the population** (found by lot 4e's seed-consuming sweep). `run_id` is
  `r-<dataset_hash[:8]>-<seed>-<config_hash[:8]>` and the roster is journaled in `run_started.roster`
  but enters no hash, so the four-agent `tests.stub_roster_rng` runs of 8.3 carry the **same run ids** as
  the three-agent `tests.stub_roster` runs of the same seeds (`r-83fbf211-0-5f754f05` and the rest) with
  different journals. Two populations therefore collide in the run index and in a claim's provenance.
  Naming the roster in `config_hash` moves the run id of every future run, so it belongs to the lot that
  applies R213, R214, R217 and R221 and bumps `ENGINE_VERSION` with them (R227), and it needs a ruling
  first: nothing in 9.5 or 13.2 says a run id must identify its population.
* `dataset_hash` moving between two rebuilds of the same data (`NewsItem.fetched_at_ms`), open since
  section 7.
* The runner passes one sensor set to every agent (`sensors=None`); `sensors=genome.sensors` needs A1's
  `Genome` and C1c's declaration.

### 8.8 The audit pass of gate G2 (lot 4e, 2026-09-09): what two auditors found, and what changed

Two auditors read the gate's closure (one on the contract, one on the tests and the measurements). One
blocker, six majors and five minors survived their own verification at the file and the line; every one
of them held, and all are fixed here. Nothing was refuted.

| Finding | Where it was wrong | Fixed by |
|---|---|---|
| blocker | 10.4's `HiveView` cap table still read `bar_ms == now_ms - interval_ms`, the rule R211 superseded three sections earlier | the row now reads the instrument's previous bar, and R211's `Sections` column gains 10.4 |
| major | merged issue I09 (`last_bar(i)` against R186's collapse of `delisted_at_ms`) was settled by no ruling, while 15.3 and 8.5 claimed all 56 were settled and `engine/calendar.py` cited a gate ruling that did not exist | **R228**, amending 7.2 and 17.2 in place; `calendar.py` cites it |
| major | 8.3 presented the 50-seed sweep as 50 independent measurements when the seed enters only `run_started` over this roster | 8.3 says so in plain words and measures the seed-consuming roster (`tests/stub_roster_rng.py`, **R229**) beside it |
| major | 17.3's debit paragraph still carried R179's literal trigger, not R215's widened one | the paragraph carries R215's sentence and cites it |
| major | 8.8's fee rows assigned the Kalshi PDF re-read to E2, three lines above the paragraph giving it to D2 | both rows name D2 and cite R216 |
| major | 13.2's `ENGINE_VERSION` comment stated a trigger R227 does not apply, and R227 named a section it had not amended | 13.2 carries R227's trigger, with the paragraph that says which byte movement bumps and when |
| major | AC-3 was graded `pass` on a three-stub roster while AC-4's analogous gap is graded `partial` | AC-3 is **partial** in 8.3, with what is measured stated exactly (R229) |
| minor | the wall-clock row covered one directory of the two; 40 of the 100 runs were reused from a killed attempt and this was not disclosed | both stated in 8.3 |
| minor | R219 and R204 named sections that carried nothing of theirs | the one-line cross-reference added to 8.3, 16.4 and 16.5 |
| minor | `data/demo_v1/manifest.json` was regenerated in lot 4c with no record | recorded in 8.5 |
| minor | HANDOFF section 4 still listed two defects the gate and the data finish closed | struck and dated, pointing at sections 7 and 8 |

One defect the fix pass found on its own is open, not fixed: `run_id` does not name the population (8.7,
last bullet). It needs a ruling and a version bump, so it belongs to the next engine lot, not to an audit
pass whose brief was the record.

The four checks after every edit above:

```
$ .venv/Scripts/python.exe -m pytest -p no:warnings -rs
....................                                                     [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests\test_import_kalshi.py:1264: live network probe; set PMX_LIVE=1 to run it
SKIPPED [1] tests\test_import_manifold.py:1124: set PMX_LIVE=1 to hit api.manifold.markets
SKIPPED [1] tests\test_import_polymarket.py:795: live network test; set PMX_LIVE=1 to run
SKIPPED [1] tests\test_news.py:1222: PMX_LIVE is not set
1024 passed, 4 skipped in 524.32s (0:08:44)
EXIT 0

$ .venv/Scripts/python.exe -m ruff check src tests
All checks passed!
RUFF_EXIT=0

$ .venv/Scripts/python.exe -m mypy --strict
Success: no issues found in 65 source files
MYPY_EXIT=0

em-dash sweep (U+2014, every file under src, tests, schemas, docs, web/src)
files scanned: 220
em-dash hits: 0
```

1 024 passed is 1 023 plus the one test this pass added
(`test_a_seed_consuming_agent_makes_the_seed_change_the_journal_it_reproduces`, mutation-checked: a
`coin_flipper` whose belief ignores the substream fails it on the forecasts). No test was weakened: no
assertion was removed, no tolerance loosened, no parametrisation narrowed, nothing skipped or xfailed.

---

## 9. Amendment C1c closed, 2026-09-10: contract section 18 and the two reviews arbitrated (`docs/CONTRACTS_V2.md` 15.10, rulings R230 to R302)

Amendment C1c wrote section 18 and section 7.14, landed the twenty-eight decisions of the two reviews in
the sections they name, and recorded forty-six rulings (R230 to R275). One adversarial critic then
attacked it and raised twenty-four findings; this arbitration verified every one in the text, fixed what
held, refuted what did not, and recorded twenty-seven more rulings (R276 to R302). Everything below is
the state of the tree at the end of the arbitration, not a report taken on trust.

### 9.1 What section 18 now states

| Subsection | What it makes normative |
|---|---|
| 18.1 | the closed catalogue of fifteen sensors with PRD v5 1.1's costs verbatim, `SensorSpec` with **derived** `granularity_ms` and `lag_ms` (the maxima over the sensor's sources, R287), `SensorFeatureSpec` with an explicit **`sentinel`** field (R285), `Genome.sensors` with `tape` mandatory, the `build_observation(..., sensors=)` hook as subtraction with `SensorAbsentError`, the three nested gates, `SensorBlock` as a slice of an unchanged `features.v1` through `features_v1_index`, the per-bar sensor budget with `RULE_PROPOSAL_COST_UNITS = 1` and `SENSOR_BUDGET_UNITS_DEFAULT = 18` (R281), the deterministic sensor drop, `diet_class` as a fourth archive axis with AC-6 read as a rate over the reachable cells (R297), and the sensor ablation |
| 18.2 | `Rule`, `Predicate`, `RuleScope`, `RuleClaim` in a closed vocabulary, content-addressed and author-independent; `fires` total over the blocks it is handed plus `readable_by` as the filter (R279); the per-row measurement table for bias, drift and volatility; three authors (miner, agent, detector) with the proposal cost, its refusal and a per-generation cap (R281, R300); `HypothesisFamily` pre-registered, with `dataset_hash`, `fit_fold` and `replicate_fold` in the id (R284); the fit screen, Benjamini-Hochberg at `FDR_Q_PPM = 50_000` over `rule_permutation_p_ppm`'s `(b + 1) / (B + 1)` p-values with `permutations` scaled to the family (R282); out-of-time replication as the primary criterion on a rolling pair clipped to the training fold (R277); visibility from `fit_t1_ms + interval_ms`; the as-of live record and demotion (R276); the transfer test bounded to the promotion's own fold (R276); the author's reward; the tracked ledger with one writer per event (R294) |
| 18.3 | `INTERVALS_MIN = (1, 60, 1_440)`, `SOURCE_GRANULARITY_MS`, `SAFETY_LAG_MS_BY_SOURCE`, the fifteen-minute admission rule with partial admission per sensor (R287), `BuildConfig.instruments` as the minute build's input (R298), Hacker News through Algolia, the minute event study emitting rules |
| 18.4 | `Genome.workflow` with `None` as the linear degenerate case, nine step kinds, the bounds, `run_workflow`'s signature and `StepTrace` (R278), the `rules` step folding `claim.direction` and refusing a volatility claim (R280), `workflow_step_executed` for an explicit workflow only |
| 18.5 | `Cohort`, `COHORT_MIN_TRAIN = 30`, `usable_for_paired_test`, one cohort per market on the primary subject, **a cohort as no fold-moving unit** (R293), the unit of comparative analysis with per-cohort rows and no per-cohort claim command (R283), why a tag cannot leak, the lexicon version on the record (R301) |
| 18.6 | the knowledge-transfer re-test, the rule-adjusted claim, the sensor ablation |
| 18.7, 18.8 | the module map rows (DS2's two lexicons included, R295), architecture rule 12 (the tagger is never a model call), the identifier formats, and the deferral table naming the package and lot that applies each code change |

### 9.2 The twenty-eight decisions, where they landed

D-R1 count-quantile folds (7.7, 12.7, PRD v2 6.1 corrected in place), D-R2 cluster-aware folds (7.7,
7.8, 12.7, 13.1, 16.3), D-R3 per-bullet Wikipedia revision stamps (5.5, 7.1, 7.3), D-R4 the linker
audit (7.6, 7.8, 12.10, 12.11), D-R5 the hourly headline grid (5.2, 7.8), D-R6 the coarse contamination
label (11.5, 12.8), D-R7 the loop as a generator (12.6), D-R8 pre-registered families and FDR (9.4,
12.4, 12.6, 18.2, PRD v5 2.3 and AC-27 corrected), D-R9 two-tier fitness (9.4, 12.6, 12.11, 13),
D-R10 capacity (12.3, 12.8), D-R11 O3 deferred (12.9), D-R12 the Manifold separation (12.10 to 12.12),
D-R13 the documented universe (7.4, 7.8), D-R14 detectors before agents (14); D-S1 as corrected by
D-S11 and D-S12 (7.4, 12.7, PRD v3 AC-11 corrected), D-S2 the interface default (12.12), D-S3
`window_days` (5.6, 7.4), D-S4 `purpose` replacing `is_demo_pack` (5.6, 7.1, 12.7, 13.1), D-S5 the
showcase pack (7.1), D-S6 the controlled vocabulary (7.2, 7.14, 9.2), D-S7 the cohort (7.2, 12.3 to
12.11, 18.5), D-S8 the deterministic tagger and rule 12 (7.14, 18.7), D-S9 as corrected by D-S14 (7.8,
7.14, 12.10), D-S10 the browsable index (12.12), D-S11 and D-S12 the per-venue targets and the fallback
order (7.4), D-S13 no cohort before the fold fix (7.7, 12.7, 14, 18.5), D-S14 the measured vocabulary
(7.14, 18.5). None was left out and none was landed in a ruling only: every one is normative text in the
section its review named.

### 9.3 What the critic found, and what came of it

Twenty-four findings: eight blockers, twelve major, four minor. Twenty-three were upheld in whole or in
part; each is a ruling in 15.10.

| Finding | Verdict | Ruling |
|---|---|---|
| C1 the live record and the transfer test read rows the tester may not | upheld in part: the sealed half is refuted (18.2 already bars the tester from the sealed fold), the validation half and the as-of gap hold | R276, **against the proposal** |
| C2 the rolling pair defined twice and never clipped to the training fold | upheld | R277 |
| C3 `SensorInputs` undefined, `run_workflow` unsigned | upheld | R278 |
| C4 `fires` reads whose blocks, and what an unbought feature does | upheld | R279 |
| C5 the rule shift drops `claim.direction` and ignores `claim.kind` | upheld | R280 |
| C6 proposing is unreachable for the whole shipped roster; no allowance field on `RunConfig` | upheld | R281 |
| C7 Benjamini-Hochberg on a 1/200 grid reporting `p = 0` | upheld in substance, reasoning corrected (`k` does climb past ten) | R282, **against the proposal** |
| C8 two cohort claims collide on one `claim_id` | upheld | R283, **against the proposal** |
| C9 `family_id` collides across fold pairs | upheld | R284 |
| C10 the sentinel rule contradicts itself and reads `lo` on eleven signed features | upheld | R285 |
| C11 prose and fixture disagree on which sensors are observation-level | upheld as a comment defect | R286, **against the proposal** |
| C12 one `lag_ms` for a sensor with two sources; `macro_releases` internally false | upheld | R287 |
| C13 `PerMarket.cohort_id` reads a field `market_listed` does not carry | upheld | R288 |
| C14 `diet_class` is a function of a genome the projection cannot see | upheld | R289, **against the proposal** |
| C15 the cluster move drifts the split one way; `build.status` contradicts R270 | upheld | R290, **against the proposal** |
| C16 the showcase quarantine misses the memory and hive carry-forward | upheld | R291, **against the proposal** |
| C17 capacity has no denominator and no sign handling | upheld on three sub-claims of four, the fourth refuted with the arithmetic | R292, **beyond the proposal** |
| C18 "a cohort never crosses a fold" contradicts its own per-fold counts | upheld | R293 |
| C19 the rule path cannot call `permutation_null` | upheld | R282 |
| C20 architecture rule 8 forbids the tester what 9.3 requires of it | upheld | R294 |
| C21 two DS2 files absent from section 13; two series maps unreconciled | upheld | R295 |
| C22 the two human audits are written into a git-ignored tree | upheld | R296, **against the proposal** |
| C23 AC-6 trebled by arithmetic on a degenerate axis | upheld | R297, **against the proposal** |
| C24 the minute build's list has no field; AC-26's "every sensor set" is 2^14 | upheld | R298 |

**Refuted, in the text of the rulings.** C1's claim that the tester reads the sealed fold: 18.2's own
opening bars it under architecture rule 3, so the leak it traced runs through validation. C7's claim that
nothing can be rejected below `k = 10`: once several rules report `p = 0`, `k` climbs and non-zero
p-values are rejected, so the defect is the inadmissible `p = 0` and the coarse grid, not a floor.
C17's claim that a negative unit return returns `-1` for every scale: the old wording was satisfied at
scale 1000 and reported the unit notional as a capacity, which is worse than what the finding described.

**Nine resolutions against the proposed fix**, each with its reason in the ruling: R276 (freezing the
live window at the fold edge would make demotion impossible), R282 (redefining `permutation_null` for
every caller moves numbers gate G2 measured, and part 4 of the claim bar thresholds `null_lb_micro` and
not the p-value), R283 (a cohort segment in `claim_id` legalises a second sealed read and lets a genome
cherry-pick its cohort), R286 (the fixture is right and one comment is wrong, so `CATALOGUE_HASH` need
not move for it), R289 (a pre-C1c journal is a full-catalogue run by construction, so the descriptor is
`2` and not unknown), R290 (a train-share floor with no recourse kills a real dataset; the group-aware
cut removes the drift instead), R291 (an escape-hatch flag that no claim path may pass is a flag that
ends up passed), R296 (git cannot re-include a file under an excluded directory, so the audits move to a
top-level tree the ignore file never names), R297 (spreading the shipped roster's diets would break
section 18's own byte-identity promise). R292 goes beyond its proposal: the capacity is the notional at
the scale **below** the halving scale, because a size the edge did not survive is not a capacity.

**Four rulings answer questions the amendment flagged and the critic passed over.** R299: a
`torch_policy` genome's `required_sensors` covers every sensor with a `features_v1_index`, so a learned
policy is never fed a vector mixing measured values and sentinels. R300: `RULE_PROPOSALS_PER_GENERATION_MAX
= 20` bounds every author the way `RULE_MINER_CANDIDATES_MAX` bounds the miner, and a threshold
perturbation still enters the family's `m`. R301: a `per_cohort` row carries the `manifest.taxonomy.version`
it was cut under, and no second copy of that version is created. R302: the `(declared, <applier>)`
convention stands, the rolling-visibility question is answered by R277's clip, and the two version
constants do not move.

### 9.4 What the arbitration applied in C1c's own files

`docs/CONTRACTS_V2.md` sections 5.6, 7.1, 7.4, 7.6, 7.7, 7.8, 7.9, 7.14, 8.1, 8.4, 9.2, 9.3, 9.5, 10.4,
10.5, 12.3, 12.4, 12.5, 12.7, 12.8, 12.10, 12.11, 12.12, 13, 13.1, 16.6, 18.1 to 18.8, and 15.10
(twenty-seven new rulings plus fourteen earlier rows of the same section amended in place so that no two
rows disagree, which is ruling R136 applied to a ruling). `src/pmx/schemas/sensor.v1.json` gained the
required `sentinel`. `src/pmx/schemas/journal.v2.json` gained the optional `market_listed.cohort_id`.
`src/pmx/schemas/dataset.v1.json`'s audit path pattern became `^audits/[0-9a-f]{16}/(linker|taxonomy)\.json$`.
`tests/fixtures/contract/sensor.catalogue.json` gained seventy-five sentinels and the derived pair for
`macro_releases`, so `catalogue_hash` moved from `2bac41c5...` to
`1ac17eba640dc0875de4122dcc1eb1ec65351c687004bc4b5d194069fdebe109`; the fixture is a contract document
and not a run artefact, so nothing downstream moves with it. `tests/test_contract_schemas.py` gained the
sentinel and derived-pair assertions, the cohort-id and audits-path assertions, and the two source
tables spelled out so the fixture is checked against the contract rather than against the code; two of
its existing assertions pinned wording this arbitration changed and were corrected with it, which is a
test disagreeing with the contract and not a weakening (R232's precedent). No assertion was removed, no
tolerance loosened, no parametrisation narrowed, nothing skipped or xfailed.

### 9.5 The four checks, verbatim

```
$ .venv/Scripts/python.exe -m pytest -q -p no:warnings -rs   (addopts already carry -q, so the count
line is suppressed; counted from the progress marks: 1039 passed, 4 skipped, 0 failed)
...................................                                      [100%]
=========================== short test summary info ===========================
SKIPPED [1] tests	est_import_kalshi.py:1264: live network probe; set PMX_LIVE=1 to run it
SKIPPED [1] tests	est_import_manifold.py:1124: set PMX_LIVE=1 to hit api.manifold.markets
SKIPPED [1] tests	est_import_polymarket.py:795: live network test; set PMX_LIVE=1 to run
SKIPPED [1] tests	est_news.py:1222: PMX_LIVE is not set
PYTEST_EXIT 0

$ .venv/Scripts/python.exe -m ruff check src tests
All checks passed!
RUFF_EXIT 0

$ .venv/Scripts/python.exe -m mypy --strict
Success: no issues found in 68 source files
MYPY_EXIT 0

$ em-dash sweep (U+2014, every .py .json .md .ts .tsx .css .html .jsonl .sh .ps1 under src, tests, docs, web/src)
files scanned: 220
em-dash hits: 0

$ .venv/Scripts/python.exe -m pytest tests/test_contract_schemas.py tests/test_architecture.py -q -p no:warnings -rs
   (re-run after the last two prose edits, which are the only files any test reads at run time)
.............................                                            [100%]
PYTEST_EXIT 0
```

### 9.6 What is left to code, with its package and lot

18.8's deferral table is the full list and names an owner and a lot for every row. The rows this
arbitration added:

| What | File and owner | Lot |
|---|---|---|
| `RULE_PROPOSAL_COST_UNITS`, `SENSOR_BUDGET_UNITS_DEFAULT = 18`, `RunConfig.sensor_budget_units` and `sensor_budget_by_agent`, `SensorFeatureSpec.sentinel`, the derived `granularity_ms` and `lag_ms`, `BuildConfig.instruments`, `RULE_PERMUTATIONS_MIN`, `RULE_PERMUTATIONS_MAX`, `RULE_PROPOSALS_PER_GENERATION_MAX`, `ARCHIVE_CELLS_REACHABLE`, `SENSOR_SETS_UNDER_TEST`, `torch_policy.required_sensors` | `types.py` (D1), `sensors/catalogue.py` (S1), `agents/registry.py` (A1) | DS1 and S1 in 5b, A1 and O2 in 6 |
| `SensorInputs`, `run_workflow`'s signature, `StepTrace` | `types.py` (D1), `agents/workflow.py` (A1) | S1 and E1 in 5b and 6, A1 and E5 in 6 |
| `Rule.readable_by`, the diet-narrowed `blocks`, `InsightView.required_sensors`, the direction-and-kind filter | `rules/rule.py` (S2), `agents/hive.py` (A3), `agents/families/rule_follower.py` and `workflow.py` (A1), `engine/runner.py` (E5) | S2 in 5b, A1, A3 and E5 in 6 |
| `rule_permutation_p_ppm` | `metrics/stats.py` (E4) | S2, by section 13's agreement |
| no `--cohort`, `cohort_or_refuse`, `market_listed.cohort_id`, `diet_class` off the journal | `claims.py` (O4), `cohorts.py` (DS2), `pmx.journal` (D7), `metrics/projection.py` (E5) | DS2 in 5b, O4 and E5 in 6, the journal field with R274's lot |
| `fold_key_ms` as the cut key, `split.realised_permille`, the empty-fold and empty-rolling refusals, the clipped `Folds.rolling`, `build.status` per venue | `data/builder.py`, `loader.py` (DS1), `optimizer/folds.py` (O1) | DS1 in 5b, O1 in 6 |
| the showcase and foreign-dataset refusals on the memory carry-forward | `engine/runner.py` (E5) | the first engine lot after this amendment |
| the three-state capacity formula | `metrics/capacity.py` (O4) | lot 6 |
| the `audits/<dataset_hash[:16]>/` tree (`.gitignore` needs no change: it never names `audits/`) | `data/builder.py`, `cli_data.py` (DS1), `data/taxonomy.py` (DS2) | lot 5b, verdicts by gate G3 |

`ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"` (R275, R302). Nothing here changes a
byte of a journal a run has written, because no such run exists: the contract journal fixture is a
completed historical document (R202), and the sensor catalogue this pass regenerated is a contract
document that no run has yet read. The first lot that changes a byte of a written journal bumps both, and
R274 names it: the first engine lot after C1c, which applies R213, R214, R217, R221, the six declared
events and the optional journal fields together.

### 9.6b The unflattering part: what the document still asks a package to invent

Stated plainly, because the engine wave's 30 cross-package disagreements began as sentences like these.

* **The contents of the blocks outside `features.v1`** are still this amendment's design with no
  measurement behind their units, bounds or sentinels: 44 of the 75 features. The sentinel rule is now a
  field rather than a sentence (R285) and the bounds are stated, so S1 and FM1 cannot disagree about
  what a missing input reads; but whether `hn_story_points` at a one-day window or
  `release_revision_abs_bp` in bp of the previous vintage is the right quantity is a guess the first
  build reports against, and the catalogue's `version` and `CATALOGUE_HASH` are what a later correction
  moves.
* **The lags** in 18.1's table are defaults, not measurements. No measurement of any source's real
  publication delay exists yet, so `hn` at five minutes and `gdelt` at fifteen are as-of guesses on the
  safe side. The first minute build reports against them.
* **The scripted families' proposal rule** ("its memory's `FeatureStat` has `n >= min_support` and a
  sign it has held for `RULE_PROPOSE_STABLE_BARS = 20` bars") tells A1 when a family may propose and not
  what it proposes: the mapping from a family's own parameters to a `RuleClaim` is A1's to invent, one
  family at a time, and 18.2 says only that A1 records the per-family rule.
* **`usual_bp` for a volatility claim** is the median over every fit-fold row in the rule's scope,
  computed once per `(scope, horizon)`. On a scope with few rows that median is unstable and nothing
  says a floor on the number of rows behind it; S2 will pick one.
* **`RULE_MIN_MARKETS = 5`, `RULE_LIVE_MIN_SUPPORT = 30`, `RULE_AUTHOR_BONUS_MICRO = 5_000`,
  `RULE_AUTHOR_SENSOR_BONUS_UNITS = 2`, `SENSOR_PENALTY_UNITS = 2`, `RULE_PROPOSALS_PER_GENERATION_MAX =
  20`, the workflow bounds and the horizon boundaries** are all defaults with no measurement behind
  them, each labelled as such in the text.
* **The `comparative` detector per cohort** (R2d) has its unit and its refusal, and no statement of what
  it compares beyond "per-cohort intervals and nulls": R2d's package text is where that lives, and this
  amendment did not widen it.

### 9.7 What is open

* The four shapes gate G2 declared without applying (R213, R214, R217, R221) plus this amendment's
  journal fields and six events are still declared and optional. R274 names the lot; until it runs, a
  journal validates without them and the six events sit under `$defs` outside `oneOf`.
* `run_id` does not name the population (8.7). Neither review assigns it; R275 leaves it to R274's lot
  with the version bump.
* `news.v1.json`'s C1b widening (`edgar`, `fred`, `cboe`) stays gate G3b's, as 17.9 says.
* A `features.v2` appending the non-`features.v1` sensor blocks to a torch policy's vector belongs to
  R3a and amendment C2. R299 bounds the damage in the meantime by requiring a torch genome's diet to
  cover the whole `features.v1` layout, which is a restriction on the genome and not a widening of the
  vector.
* Nothing in section 18 has been built. Lot 5b is the first lot that reads it.
