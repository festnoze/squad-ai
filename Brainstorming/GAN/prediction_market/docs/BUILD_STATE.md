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
